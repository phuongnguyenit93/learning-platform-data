# CustomEditorConfigurer in Spring Framework Bean Configuration

## 1. The Problem: From Configuration Strings to Typed Java Properties

In the Spring IoC container, a bean often receives properties via bean definitions. For example, an XML file might write `<property name="currency" value="usd"/>`. The source value is the string `"usd"`, yet the bean's setter expects a `CurrencyCode` object. Spring must **perform type conversion** before invoking the setter.

If this is an application-defined type with no compatible built-in converter, you can implement a JavaBeans `PropertyEditor` and register it with the container using **`CustomEditorConfigurer`**.

`CustomEditorConfigurer` resides in package `org.springframework.beans.factory.config` and implements `BeanFactoryPostProcessor` and `Ordered`. It registers custom `PropertyEditor`s with `BeanFactory` so the container can use them during **bean creation and configuration**. These editors participate in JavaBeans property conversion inside the container.

Illustrative example:

```text
Bean definition:
    currency = " usd "
          |
          v
Spring ApplicationContext
    + CustomEditorConfigurer
          |
          v
PropertyEditor<CurrencyCode>
  " usd " -> CurrencyCode("USD")
          |
          v
BeanWrapper / property population
          |
          v
PaymentSettings.setCurrency(CurrencyCode("USD"))
```

**Core point of the topic:** `CustomEditorConfigurer` configures conversion for **bean creation** inside the container. It **does not automatically register editors for `DataBinder` or `WebDataBinder` instances handling forms/HTTP requests**. If you need the same editor in the web layer, you must register it on the appropriate binder, usually via a reusable `PropertyEditorRegistrar`.

## 2. Components and Responsibility Boundaries

| Component | Role | Scope |
| --- | --- | --- |
| `java.beans.PropertyEditor` | Reads/writes values and converts `String` to a concrete Java type via `setAsText(...)` | Single editor, stateful |
| `PropertyEditorSupport` | Utility base class for building editors; holds value via `setValue(...)`/`getValue()` | Per editor instance |
| `PropertyEditorRegistry` | `registerCustomEditor(...)` API binding an editor to a type or property path | Specific BeanWrapper or DataBinder |
| `PropertyEditorRegistrar` | Encapsulates logic to instantiate and register editors on a passed-in registry | Reusable across multiple registries |
| `CustomEditorConfigurer` | `BeanFactoryPostProcessor` registering editors/registrars with a bean factory | Bean creation of an IoC container |
| `BeanWrapper` | Converts and writes bean properties during population | One target bean |
| `DataBinder` / `WebDataBinder` | Receives input data, converts types, binds, collects errors | Object/request binding |
| `ConversionService` / `Converter` | Modern type conversion mechanism, easy to share and typically stateless | Multiple contexts when integrated |

Bean configuration flow differs from request-handling flow:

```text
A. Spring container:
   ApplicationContext.refresh()
     -> BeanFactoryPostProcessor (CustomEditorConfigurer)
     -> register editors/registrars into BeanFactory
     -> BeanFactory creates PaymentSettings
     -> PropertyEditor converts string value
     -> setter receives CurrencyCode

B. HTTP form:
   Request
     -> WebDataBinder
     -> editors registered ON the binder
     -> bind onto model attribute
     -> BindingResult/validation
     -> controller

A does not automatically register editors for B.
The same PropertyEditorRegistrar can be reused in both places.
```

`CustomEditorConfigurer` is not a `@Component` executing business logic, not a `BeanPostProcessor` running after every setter, and not a manager of all application-wide `Converter`s. Its early execution belongs to the `BeanFactoryPostProcessor` lifecycle.

## 3. Key APIs of `CustomEditorConfigurer`

Common configuration methods:

```java
CustomEditorConfigurer configurer = new CustomEditorConfigurer();

configurer.setPropertyEditorRegistrars(
    new PropertyEditorRegistrar[] { new CurrencyCodeRegistrar() }
);

// Or register an editor class for the Java type:
Map<Class<?>, Class<? extends PropertyEditor>> customEditors =
    Map.of(CurrencyCode.class, CurrencyCodeEditor.class);

configurer.setCustomEditors(customEditors);
```

This is an **illustrative fragment**, assuming `CurrencyCode`, `CurrencyCodeRegistrar`, and `CurrencyCodeEditor` exist with matching imports.

### 3.1. `setPropertyEditorRegistrars(...)`

The parameter is a `PropertyEditorRegistrar[]` array. Each registrar implements:

```java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

Here, the registrar **creates a new editor** when applied to a registry. Spring recommends this approach because JavaBeans editors are stateful (e.g., `PropertyEditorSupport` holds `getValue()`) and must not accidentally share one editor instance across concurrent beans/requests.

One registrar can register **multiple editors**, such as `CurrencyCodeEditor` and `LocaleTagEditor`. It can also be reused when configuring `DataBinder`, since both binders and BeanWrappers expose the `PropertyEditorRegistry` API appropriately.

### 3.2. `setCustomEditors(...)`

This describes a map of **target type -> editor class**, not target type -> pre-instantiated editor object:

```java
Map<Class<?>, Class<? extends PropertyEditor>> editorTypes =
    new HashMap<>();

editorTypes.put(CurrencyCode.class, CurrencyCodeEditor.class);
configurer.setCustomEditors(editorTypes);
```

Important points:

- The key is `Class<?>` of the **type to convert** (`CurrencyCode.class`).
- The value is `Class<? extends PropertyEditor>` of the **editor class** (`CurrencyCodeEditor.class`).
- The editor must be instantiable by the container, typically requiring an accessible no-argument constructor.
- Never put a singleton `new CurrencyCodeEditor()` into this map; neither does it match the method signature, nor is sharing editor state safe.
- If an editor needs dependencies or custom construction logic, use `PropertyEditorRegistrar` to control instantiation.

In XML configuration, class names can be written as strings and resolved by Spring. In Java code, the map must use `Class` objects as declared in the signature.

### 3.3. `setOrder(...)`

The configurer implements `Ordered`, so priority can be set when multiple `BeanFactoryPostProcessor`s exist:

```java
configurer.setOrder(100);
```

Ordering does not replace conflict resolution between editors. If multiple configurations register for the same type, unify responsibilities and test which editor is actually used. Do not use ordering as an arbitrary workaround for duplicated designs.

## 4. Creating a `PropertyEditor` for an Application Type

Suppose the application stores currency codes as normalized three-uppercase-letter values, e.g., `"usd"` -> `CurrencyCode("USD")`.

Model:

```java
public record CurrencyCode(String value) {}
```

This is a data-holding record. A record by itself **does not** teach Spring how to convert `"usd"` into the record; proper conversion is required if a bean definition supplies a `String` while the setter expects `CurrencyCode`.

Editor:

```java
public class CurrencyCodeEditor extends PropertyEditorSupport {

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "Currency code must not be blank"
            );
        }

        String code = text.strip().toUpperCase(Locale.ROOT);

        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three letters"
            );
        }

        setValue(new CurrencyCode(code));
    }

    @Override
    public String getAsText() {
        CurrencyCode value = (CurrencyCode) getValue();
        return value == null ? "" : value.value();
    }
}
```

This snippet describes the editor class, requiring imports for `java.beans.PropertyEditorSupport` and `java.util.Locale`, plus `CurrencyCode`. Given input `" usd "`, `setAsText` strips whitespace, uppercases it, and calls `setValue` to store `CurrencyCode("USD")`.

`getAsText` converts the current value back into a string, useful in read/display scenarios, though not every bean creation flow calls it automatically.

**Do not use `setAsText` to run expensive database queries or business side effects** during bean initialization. When an editor encounters malformed input, throw an informative exception; the container usually wraps the failure in a bean creation exception, while a binder may record a conversion error in `BindingResult` depending on context.

## 5. Why Is `PropertyEditorRegistrar` Usually Preferred?

A registrar packages registration logic for multiple registries:

```java
public final class CurrencyCodeRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
            CurrencyCode.class,
            new CurrencyCodeEditor()
        );
    }
}
```

This is a fragment, requiring imports for `org.springframework.beans.PropertyEditorRegistrar` and `org.springframework.beans.PropertyEditorRegistry`.

Using a registrar brings three direct benefits:

1. **Creates fresh editors per registration.** `PropertyEditorSupport` holds internal state; an editor that handled `"USD"` may still retain a `CurrencyCode`. Never share it uncontrolled across threads or requests.
2. **Reuses registration logic.** The same registrar can serve the bean factory and a specific `WebDataBinder` without duplicating `registry.registerCustomEditor(...)`.
3. **Keeps conversion separate from business classes.** The model knows `CurrencyCode`; the registrar focuses on converting configuration data into that type.

With `PropertyEditorRegistrar`, each time a registry applies the registrar, the code creates a new editor. Do not assume a brand-new editor instance is created for every single field assignment; the specific lifecycle of a registry/BeanWrapper may cover multiple conversions within one bean creation pass.

## 6. Complete Java 17 Example Running with `ApplicationContext`

The following example uses Spring's `AnnotationConfigApplicationContext` and **bean definitions via `RootBeanDefinition`**. We declare two `PaymentSettings` beans receiving different configuration strings, while registering `CustomEditorConfigurer` as a `BeanFactoryPostProcessor`. When the context refreshes, the converter runs while Spring populates properties.

This is a **real bean-definition conversion** example, not Java code manually calling `new CurrencyCode(...)` inside a factory method.

### 6.1. Directory structure

```text
custom-editor-demo/
├── pom.xml
└── src/main/java/example/CustomEditorDemo.java
```

File `pom.xml` (Java 17, Spring Framework 6.2.14):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>custom-editor-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</groupId>
      <version>6.2.14</version>
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
        <configuration>
          <mainClass>example.CustomEditorDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

File `src/main/java/example/CustomEditorDemo.java`:

```java
package example;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;
import org.springframework.beans.factory.config.CustomEditorConfigurer;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class CustomEditorDemo {

    public record CurrencyCode(String value) {}

    public static class CurrencyCodeEditor extends PropertyEditorSupport {

        @Override
        public void setAsText(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                    "Currency code must not be blank"
                );
            }
            String normalized =
                text.strip().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException(
                    "Currency code must contain three letters"
                );
            }
            setValue(new CurrencyCode(normalized));
        }

        @Override
        public String getAsText() {
            CurrencyCode code = (CurrencyCode) getValue();
            return code == null ? "" : code.value();
        }
    }

    public static class CurrencyCodeRegistrar
            implements PropertyEditorRegistrar {

        @Override
        public void registerCustomEditors(
                PropertyEditorRegistry registry) {
            registry.registerCustomEditor(
                CurrencyCode.class,
                new CurrencyCodeEditor()
            );
        }
    }

    public static class PaymentSettings {

        private CurrencyCode currency;

        public PaymentSettings() {}

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static void main(String[] args) {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            RootBeanDefinition configurerDefinition =
                new RootBeanDefinition(CustomEditorConfigurer.class);

            configurerDefinition.getPropertyValues().add(
                "propertyEditorRegistrars",
                new PropertyEditorRegistrar[] {
                    new CurrencyCodeRegistrar()
                }
            );

            context.registerBeanDefinition(
                "customEditorConfigurer",
                configurerDefinition
            );

            RootBeanDefinition first =
                new RootBeanDefinition(PaymentSettings.class);
            first.getPropertyValues().add("currency", " usd ");

            RootBeanDefinition second =
                new RootBeanDefinition(PaymentSettings.class);
            second.getPropertyValues().add("currency", " eur ");

            context.registerBeanDefinition("first", first);
            context.registerBeanDefinition("second", second);

            context.refresh();

            PaymentSettings firstBean =
                context.getBean("first", PaymentSettings.class);
            PaymentSettings secondBean =
                context.getBean("second", PaymentSettings.class);

            System.out.println(
                "first=" + firstBean.getCurrency().value()
            );
            System.out.println(
                "second=" + secondBean.getCurrency().value()
            );
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected business output on `stdout` (excluding dependency download logs or Maven warnings if present):

```text
first=USD
second=EUR
```

**Exact explanation of what happens:**

- `CustomEditorConfigurer` is declared via a `RootBeanDefinition` with property `propertyEditorRegistrars`. Because it is a `BeanFactoryPostProcessor`, the context invokes it to register the editor with the bean factory during `refresh()`.
- Both `first` and `second` are `PaymentSettings` with property `currency` defined as raw strings. Spring sees the setter expects `CurrencyCode` and uses the registered editor.
- `CurrencyCodeEditor.setAsText` turns `" usd "` into `CurrencyCode("USD")` and likewise for `" eur "`.
- The runnable code has only **one public top-level class `CustomEditorDemo`**; the rest are nested public static types so everything fits in a single `CustomEditorDemo.java` file.
- Spring's `spring-context` brings in the needed `spring-beans` and `spring-core` modules.
- There is no database, HTTP request, `@Controller`, or `DataBinder` in the example. The bean factory itself performs conversion when creating beans.

If you replace `" usd "` with `"invalid-code"`, the editor throws `IllegalArgumentException` and bean instantiation fails, producing a bean creation exception. Do not tightly couple assertions to exact exception message strings across versions without inspecting the cause chain.

## 7. Configuring via `@Bean` in Annotation-Based Java Configuration

In a Spring application using annotation-based configuration, you can declare the configurer as a `@Bean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.factory.config.CustomEditorConfigurer;

@Configuration(proxyBeanMethods = false)
public class EditorConfiguration {

    @Bean
    public static CustomEditorConfigurer customEditorConfigurer() {
        CustomEditorConfigurer configurer =
            new CustomEditorConfigurer();

        configurer.setPropertyEditorRegistrars(
            new PropertyEditorRegistrar[] {
                new CurrencyCodeRegistrar()
            }
        );
        return configurer;
    }
}
```

This is **integration code**: it requires `CurrencyCodeRegistrar` in the corresponding package/import and `EditorConfiguration` scanned or registered in the application context. A `@Bean` returning a `BeanFactoryPostProcessor` should be a **static method** so it is created early enough without prematurely instantiating the `@Configuration` class itself; static declaration is the standard recommendation for factory post-processor beans.

This example only **registers the editor with the container**. To prove conversion works, there must be a bean whose property the container actually populates from `String` to `CurrencyCode`. If in Java you write:

```java
@Bean
PaymentSettings paymentSettings() {
    PaymentSettings settings = new PaymentSettings();
    settings.setCurrency(new CurrencyCode("USD"));
    return settings;
}
```

you constructed `CurrencyCode` manually, so the editor never needs to run. Do not treat the result of that snippet as proof that `CustomEditorConfigurer` worked.

### 7.1. XML configuration with `propertyEditorRegistrars`

For applications using Spring XML:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
        <property name="propertyEditorRegistrars">
            <list>
                <bean class="example.CurrencyCodeRegistrar"/>
            </list>
        </property>
    </bean>

    <bean id="paymentSettings" class="example.PaymentSettings">
        <property name="currency" value="usd"/>
    </bean>
</beans>
```

This is a **standalone XML pattern assuming top-level classes**, meaning `example.CurrencyCodeRegistrar` and `example.PaymentSettings` exist as public classes with the described names and setters. For the nested classes from section 6's demo, direct usage requires JVM binary names with `$` (e.g., `example.CustomEditorDemo$PaymentSettings`) or extracting classes into separate files.

An XML-configured application loads this file via `ClassPathXmlApplicationContext` or an equivalent context. When all classes and beans are defined properly, `currency` in `paymentSettings` receives the object converted from `"usd"`.

### 7.2. XML with `customEditors`

Another option is declaring **editor classes** by type:

```xml
<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="customEditors">
        <map>
            <entry key="example.CurrencyCode"
                   value="example.CurrencyCodeEditor"/>
        </map>
    </property>
</bean>
```

Requires `example.CurrencyCodeEditor` implementing `PropertyEditor` with an appropriate constructor. The `value` in XML is a **class name**, not a pre-existing singleton editor object.

When editors need dependencies, there are many editors, or they must be reused across other binder types, prefer `PropertyEditorRegistrar`.

## 8. Why Must a Single Editor Instance Never Be Shared as a Global Singleton?

`PropertyEditorSupport` stores conversion state via `setValue()`/`getValue()`, and sometimes format/context state too. If two requests or two beans use the same editor instance without concurrency isolation, values can overwrite each other unexpectedly.

Design mistake:

```java
// Illustration of editor sharing to avoid:
private static final CurrencyCodeEditor SHARED =
    new CurrencyCodeEditor();

void configure(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(CurrencyCode.class, SHARED);
}
```

This snippet is **not a standalone runnable component**: it illustrates a static editor instance attached to multiple registries. Never write a registrar like this.

Right direction:

```java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

The registrar itself can be stored as a singleton holding no mutable state, while each registration into a registry creates a new editor. That avoids needing global synchronization around `PropertyEditorSupport`.

Do not infer that an editor is always completely thread-safe merely because it sits in `CustomEditorConfigurer`. When using editors inside an application context, understand which component creates instances and when reuse occurs.

## 9. Critical Boundary: Container Bean Creation vs. HTTP Data Binding

Per Spring's Javadoc, editors registered via `CustomEditorConfigurer` **do not automatically apply to data binding**. BeanFactory registration serves bean definitions, whereas `DataBinder`/`WebDataBinder` has its own registry.

Suppose a controller receives a request:

```text
POST /payments
Content-Type: application/x-www-form-urlencoded

currency=usd
```

If the handler accepts:

```java
@PostMapping("/payments")
public String submit(
    @ModelAttribute("paymentForm") PaymentForm form,
    BindingResult errors
) {
    if (errors.hasErrors()) {
        return "payment-form";
    }
    return "saved";
}
```

even with a `CustomEditorConfigurer` bean in the context, **do not assume** that editor will be applied to `PaymentForm.currency`. Binding must be configured in MVC.

### 9.1. Reusing a registrar with `@InitBinder`

Integration code example:

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("paymentForm")
public void configurePaymentForm(WebDataBinder binder) {
    currencyCodeRegistrar.registerCustomEditors(binder);
}
```

Here `currencyCodeRegistrar` is an application-provided field/dependency of type `PropertyEditorRegistrar`, typically the very same reusable registrar. `WebDataBinder` exposes custom editor registration via the `DataBinder` API.

You can also register directly:

```java
@InitBinder("paymentForm")
public void configurePaymentForm(WebDataBinder binder) {
    binder.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

These two snippets are **two alternatives**; both cannot sit side by side with the same signature in one controller. Putting both in the same class causes duplicate method signatures and fails compilation.

`PaymentForm` must have matching properties/constructors, `CurrencyCode` and the editor must be accessible, and `BindingResult` must immediately follow the `@ModelAttribute` parameter. `@InitBinder` itself does not validate write permissions; Bean Validation or business validation must still run per contract.

### 9.2. Binding outside MVC

`DataBinder` in Spring Core can share the same registrar:

```java
PaymentForm target = new PaymentForm();
DataBinder binder = new DataBinder(target, "paymentForm");

new CurrencyCodeRegistrar().registerCustomEditors(binder);

MutablePropertyValues params = new MutablePropertyValues();
params.add("currency", "usd");

binder.bind(params);
BindingResult result = binder.getBindingResult();
```

This is a **fragment requiring matching classes and imports**. It illustrates direct binder registration: it neither needs nor uses a `CustomEditorConfigurer` bean. `PaymentForm` needs `CurrencyCode` getters/setters or compatible binding mode. On success, `currency` receives `CurrencyCode("USD")`; when conversion fails, inspect `result.getFieldErrors()`. Defining `CustomEditorConfigurer` does not replace calling `registerCustomEditor(...)` here.

### 9.3. Is `@RequestBody` different?

Yes. When processing JSON such as:

```json
{"currency": "usd"}
```

`@RequestBody` usually relies on Jackson/`HttpMessageConverter` to deserialize the body into objects. A JavaBeans `PropertyEditor` registered with the bean factory **does not automatically configure** Jackson. To convert JSON strings into custom types, use the JSON mapper/deserializer's own configuration or custom serialization setup.

## 10. `ConversionService`: When Should a More Modern Mechanism Be Used?

Spring supports both historic JavaBeans `PropertyEditor` and the `Converter<S,T>`, `ConverterFactory`, `GenericConverter` APIs with `ConversionService`. In newer applications, when the task is simply transforming a `String` into another type without needing JavaBeans editor semantics, `Converter` is usually clearer and easier to test.

Example:

```java
import org.springframework.core.convert.converter.Converter;

public final class CurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        String code =
            source.strip().toUpperCase(Locale.ROOT);

        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Invalid currency code"
            );
        }
        return new CurrencyCode(code);
    }
}
```

This is a **fragment**; it requires `CurrencyCode` and `Locale`, plus registering the converter on the right `ConversionService`. Converters of this style hold no `getValue()` state like `PropertyEditorSupport`, making stateless implementations easy to share.

Registration options:

- For a bean factory: `ConfigurableBeanFactory.setConversionService(...)` or configuring an appropriate conversion service in the context.
- For Spring MVC: `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` for request-binding converters/formatters.
- For Spring Boot: per the conversion/formatter mechanism used by each module; **never** assume every `ConversionService` across layers is one instance receiving identical registrations.

Adopting `Converter` does not require removing all legacy `PropertyEditor`s. When a framework or bean definition requires a JavaBeans editor, `CustomEditorConfigurer` remains a useful tool.

## 11. Lifecycle and Debugging

### 11.1. Why must `BeanFactoryPostProcessor` run early?

The bean factory must know how to convert values **before instantiating beans that depend on the editor**. `CustomEditorConfigurer.postProcessBeanFactory(...)` runs after bean definitions are loaded and before regular singleton beans are instantiated. Therefore, in an `ApplicationContext`, declaring it as a `BeanFactoryPostProcessor` bean lets the container discover it automatically.

If an application uses a low-level `BeanFactory` without running `ApplicationContext`'s lifecycle, merely defining a configurer bean definition does not ensure the processor executes. You must invoke the `BeanFactoryPostProcessor` registration and execution step before creating target beans.

### 11.2. Distinguishing missing editor errors from format errors

If Spring does not know how to convert `String` to `CurrencyCode`, you may encounter `TypeMismatchException` or a conversion-related bean creation exception. If the editor is present yet `"xxx-too-long"` fails the three-letter pattern, the error originates inside `setAsText`. Inspect the cause chain, property name, and configuration value; do not lump every failure into "bean wasn't scanned".

Useful debugging steps:

1. Verify `CustomEditorConfigurer` is registered in the **exact application context** managing the target bean.
2. Verify the setter's property type is indeed `CurrencyCode`; a different class name or classloader prevents registry matching.
3. Verify the registrar actually registers `CurrencyCode.class` with a new editor instance.
4. Verify the property value actually arrives as a string from the bean definition; if it is already a `CurrencyCode`, the editor is not invoked.
5. Check errors inside `setAsText`; log causes safely without leaking sensitive data.
6. When debugging form requests, check `@InitBinder`/`DataBinder` or MVC's `ConversionService`, since BeanFactory's configurer does not apply automatically.
7. When debugging JSON, check `@RequestBody`'s mapper/deserializer.
8. With parent/child context hierarchies, identify which bean factory creates the bean and which context holds the post-processor.

### 11.3. Do constructor injection and `@Bean` methods always trigger editors?

No. `CustomEditorConfigurer` is used when the **bean factory** needs to convert property values during bean creation. In a hand-written `@Bean` method `return new PaymentSettings(new CurrencyCode("USD"))`, Java already constructs the right type, with no `String` to `CurrencyCode` step. For constructor arguments in bean definitions, factory conversion can also participate when raw values need converting, though you should test the specific bean creation path.

### 11.4. Multiple registration mechanisms at once

If the same `CurrencyCode` type is registered via editor class map, registrar, and conversion service, converter/editor selection depends on context, type/property path, and Spring's conversion resolution. Avoid conflicting conversion definitions. Keeping one clear registration source per boundary makes behavior easier to observe and test.

## 12. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Putting a `PropertyEditor` object in `customEditors` | Wrong mapping type, risks sharing editor state | Use `Class<? extends PropertyEditor>` or `PropertyEditorRegistrar` |
| Editor lacks a suitable constructor | Container fails to instantiate editor | Use an editor class with a valid constructor or a registrar creating instances explicitly |
| Registrar holds a reused singleton editor | Values bleed across conversions, concurrency risks | `new Editor()` inside `registerCustomEditors` |
| Configuring only `CustomEditorConfigurer` and expecting MVC binding to work | `WebDataBinder` lacks the expected editor | Register via `@InitBinder` or MVC conversion service |
| Using editor for JSON `@RequestBody` | Jackson ignores BeanFactory editors by default | Use appropriate JSON deserializer/mapper |
| Not validating input in `setAsText` | Malformed values slip into beans | Validate syntax and throw an appropriate exception |
| Creating bean in Java with typed value and assuming editor ran | Test fails to verify conversion | Use a bean definition with a `String` property and verify the result |
| Declaring non-static `@Bean` for factory post-processor carelessly | Configuration may initialize prematurely | Prefer static `@Bean` for `BeanFactoryPostProcessor` |
| Relying on editor to check user permissions | Editor only converts types, does not authorize | Check permissions/state and business validation in services |
| Registering in a different context | Target bean does not see the editor | Identify the exact context and bean factory responsible |
| Editor class uses shared mutable static fields | State mixes across requests/beans | Fresh editor per registry, avoid global mutable state |

## 13. Project Implementation Checklist

- Is the bean's target type clear? Does a string from a bean definition need conversion to a custom class?
- Is `CustomEditorConfigurer` declared as a `BeanFactoryPostProcessor` in the right context?
- Can a reusable `PropertyEditorRegistrar` replace hard-to-manage editor maps?
- Does the registrar create a fresh editor per registry rather than accidentally sharing stateful editors?
- Does `setAsText` convert types and report sensible errors on empty/malformed strings?
- Do the target bean's setter/constructor match the configured property?
- Do tests construct beans from **actual String values** rather than passing pre-built typed objects?
- Does it need to run in the bean factory or HTTP `DataBinder`? If both, is it registered at both boundaries?
- Could modern `ConversionService` replace the editor for a simple conversion type?
- Does API design distinguish `@RequestBody` JSON from `@ModelAttribute` forms?
- Have converter errors, bean creation errors, and multi-context scenarios been tested?

## 14. Self-Check Exercises

### Exercise 1. Identifying boundaries

An application configures `CustomEditorConfigurer` for `CurrencyCode`, and then a controller receives `@ModelAttribute PaymentForm` with a `CurrencyCode currency` field. Will `currency=usd` automatically bind?

**Answer:** No. Bean factory editors do not automatically apply to request binders. Register the same editor via `@InitBinder` or configure `ConversionService` in MVC, then test it.

### Exercise 2. Choosing a registration mechanism

A `TimeZoneEditor` requires constructor arguments and handles several specialized time zone codes. Choose `customEditors` or `propertyEditorRegistrars`?

**Answer:** `PropertyEditorRegistrar` is better suited because it can instantiate the editor with dependencies/arguments and register it on the registry, avoiding the factory's no-arg constructor requirement.

### Exercise 3. Predicting output

`CurrencyCodeEditor` uses `source.strip().toUpperCase(Locale.ROOT)`. A bean definition sets `currency=" eur "`, and the setter accepts `CurrencyCode`. The configurer is properly registered. What does `getCurrency().value()` return?

**Answer:** `"EUR"`. The editor normalizes the string before the bean factory assigns the property.

### Exercise 4. Spotting concurrency bugs

A registrar contains `private final CurrencyCodeEditor editor = new CurrencyCodeEditor();` and registers that same instance on every `registerCustomEditors` call. Is this recommended?

**Answer:** No. `PropertyEditorSupport` holds state; the registrar should create `new CurrencyCodeEditor()` on each registration so editors are never shared across registries.

### Exercise 5. When is an editor unnecessary?

`@Bean PaymentSettings paymentSettings() { return new PaymentSettings(new CurrencyCode("USD")); }`. Even with the configurer present, is `String` to `CurrencyCode` conversion needed in this call?

**Answer:** No. Java already creates the correctly typed object directly in the method; to test the editor, use a string property value in a bean definition.

## 15. Official References

- Spring Framework Javadoc — [`CustomEditorConfigurer`, Spring 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/factory/config/CustomEditorConfigurer.html): `setPropertyEditorRegistrars`, `setCustomEditors`, lifecycle, and notes regarding `DataBinder`.
- Spring Framework Reference — [Data Binding and Custom PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): property conversion and registering additional editors.
- Spring Framework Javadoc — [`PropertyEditorRegistrar`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html): applying registrars to `PropertyEditorRegistry`.
- Spring Framework Javadoc — [`PropertyEditorRegistry`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html): registering editors by type/path.
- Spring Framework Javadoc — [`ConfigurableBeanFactory`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): `addPropertyEditorRegistrar`, `registerCustomEditor`.
- Spring Framework Reference — [Extensibility with BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): factory post-processing lifecycle.
- Spring Framework Reference — [Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): registering editors/converters for web data binding.
- Spring Framework Reference — [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter` and `ConversionService`.
