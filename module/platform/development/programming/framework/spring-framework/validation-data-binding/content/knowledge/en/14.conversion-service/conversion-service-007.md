# Integrating ConversionService with DataBinder and BeanFactory in Spring Framework

## 1. Goal: Sharing One Type Conversion Mechanism Across Two Layers

In a Spring application, input strings often need to be converted into Java types before being assigned to an object. For example, `"usd"` needs to become `CurrencyCode("USD")`; `"21"` becomes `Integer.valueOf(21)`; or a date string becomes `LocalDate`.

**`ConversionService`** is Spring's unified type-conversion API. It separates conversion logic from call sites, allowing strongly typed converters to be registered and reused across multiple contexts. This topic focuses on two integration points:

- **`BeanFactory` / `ApplicationContext`:** converting bean configuration values, property values, or constructor arguments while the container creates beans.
- **`DataBinder` / `WebDataBinder`:** converting form/request data into a target object, working alongside property binding, constructor binding, and `BindingResult`.

The same `ConversionService` can be attached to both places, yet each place still needs to be configured properly. Registering a `Converter` on one instance does not mean every `BeanFactory` and every `DataBinder` in the application automatically sees that instance.

Throughout this guide we use the `CurrencyCode` type:

```text
" usd "
   |
   v
Converter<String, CurrencyCode>
   |
   +-------------------------------+
   |                               |
   v                               v
BeanFactory                    DataBinder
bean definition                form input
   |                               |
   v                               v
PaymentSettings.currency       PaymentForm.currency
   |                               |
   +---------- CurrencyCode("USD")+
```

## 2. Core Components and Responsibilities

| Component | Responsibility | Integration point |
| --- | --- | --- |
| `Converter<S,T>` | Converts one source type to one target type | Registered with `ConverterRegistry` |
| `ConverterFactory<S,R>` | Creates converters for multiple target types in a hierarchy | `ConversionService` |
| `GenericConverter` | Converts based on source/target `TypeDescriptor` pairs, supporting complex types | `ConversionService` |
| `ConversionService` | API to query capability and execute conversion | BeanFactory, DataBinder, Spring components |
| `ConverterRegistry` | SPI to register/unregister converters | Implemented by e.g. `DefaultConversionService` |
| `TypeDescriptor` | Describes types more richly than `Class`, including generics and annotations | Converting collections, arrays, Maps, properties |
| `ConfigurableBeanFactory` | Allows attaching a ConversionService to convert property/constructor values | Bean creation |
| `DataBinder` | Binds data to a target and records binding errors | Data binding |
| `WebDataBinder` | Web-specialized binder extending `DataBinder` | Spring MVC/WebFlux binding |

Two common calls:

```java
beanFactory.setConversionService(conversionService);
binder.setConversionService(conversionService);
```

Both accept the same `ConversionService` API type, yet they configure **two different managing objects**. `ConfigurableBeanFactory.setConversionService` governs conversion when the bean factory resolves configuration values. `DataBinder.setConversionService` governs the service the binder uses when binding a target.

Do not confuse `ConversionService` with `PropertyEditor`:

- `PropertyEditor` is a stateful JavaBeans API, typically handling text data via `setAsText`/`getAsText`.
- `Converter` is a Spring API with explicit source/target types, usually stateless.
- Spring still supports PropertyEditor; when no matching `ConversionService` is present, the system may fall back to the traditional editor mechanism.
- There is no need to implement both for the same conversion if a converter fully meets the requirement.

## 3. Writing a Converter Used by Both BeanFactory and DataBinder

### 3.1. Target Type

```java
public record CurrencyCode(String value) {}
```

This record models a small value object. It does not convert strings into currency codes itself; that belongs to the converter.

### 3.2. Converter

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToCurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                "Currency code must not be blank"
            );
        }

        String normalized =
            source.strip().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three letters"
            );
        }

        return new CurrencyCode(normalized);
    }
}
```

This converter class can be used standalone once the proper imports and `CurrencyCode` record are added. Logic:

1. Reject null/empty/blank strings per the example contract.
2. Use `strip()` to remove leading/trailing whitespace.
3. Use `Locale.ROOT` for consistent uppercasing independent of the machine's default locale.
4. Check for exactly three ASCII letters A–Z.
5. Return a new `CurrencyCode`.

`Converter.convert` is called with a non-null source per Spring ConversionService's contract; depending on the caller flow's null/empty policy, the converter might not be invoked for null. Checking blank in the example expresses the rule clearly, though it is not a full validator against the real ISO currency list. If codes must be validated against an approved catalog, check against the product's accepted code set.

**Converters should be stateless and thread-safe.** `ConversionService` is designed to be configured at startup and shared across threads. Do not store request state, shared mutable buffers, or user-specific data inside a converter.

## 4. Creating and Registering ConversionService

### 4.1. Using `DefaultConversionService` in Java

```java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    new StringToCurrencyCodeConverter()
);
```

`DefaultConversionService` pre-registers common converters for String, numbers, enums, collections, and many basic types. We add our custom converter with `addConverter`. It is also a `ConverterRegistry` for direct registration.

If the application only creates converters for one specific context, it can instantiate its own service. Avoid mutating the registry after multiple threads have begun using it; register converters during application configuration and keep the configuration stable.

### 4.2. Registering in ApplicationContext Under the Conventional Bean Name

In a Spring ApplicationContext, a `ConversionService` registered under the bean name `conversionService` is recognized by the framework as the context's default conversion service.

Java configuration example:

```java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(
            new StringToCurrencyCodeConverter()
        );
        return service;
    }
}
```

This is a configuration fragment; import `@Configuration`, `@Bean`, `ConversionService`, and `DefaultConversionService`. Because the `@Bean` method is named `conversionService`, the default bean name matches Spring's convention. When the container uses this conversion service, custom converters participate in converting property/constructor values.

It can also be configured in XML:

```xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToCurrencyCodeConverter"/>
        </set>
    </property>
</bean>
```

This is an example for a top-level class `example.StringToCurrencyCodeConverter` with a suitable constructor; the application must load the XML file in the right context. `ConversionServiceFactoryBean` creates a service from the declared converters.

### 4.3. Manual Registration on BeanFactory

At a lower level, the `ConfigurableBeanFactory` API lets you attach the service directly:

```java
ConfigurableListableBeanFactory beanFactory =
    context.getBeanFactory();

beanFactory.setConversionService(conversionService);
```

This fragment depends on the context and lifecycle timing. You must set the conversion service **before beans requiring conversion are created**. In normal applications, using a bean named `conversionService` is the standard configuration; calling this manually is useful in integration examples or when working with a bean factory at a low level.

Do not confuse `beanFactory.setConversionService` with `binder.setConversionService`. The same service can be passed to both, yet they are two independent configuration targets.

## 5. Integrating ConversionService with BeanFactory

### 5.1. Bean Definition Containing a String Property Value

Suppose:

```java
public static class PaymentSettings {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
```

When a bean definition contains `currency = " usd "`, the setter requires `CurrencyCode`. BeanFactory must convert the value before invoking the setter. With the registered service:

```text
RootBeanDefinition:
  beanClass = PaymentSettings
  property "currency" = " usd "
          |
          v
BeanFactory resolves property value
          |
          v
ConversionService.convert(String, CurrencyCode)
          |
          v
CurrencyCode("USD")
          |
          v
PaymentSettings.setCurrency(...)
```

Conversion occurs when the container populates the bean. If the converter throws an exception, bean creation can fail; Spring wraps the failure in a bean-creation exception, and the cause chain preserves the conversion cause.

### 5.2. With Constructor Arguments

BeanFactory also performs type conversion for constructor arguments in a bean definition when a configured value must be converted to a constructor parameter. For example:

```java
public class PaymentSettings {
    private final CurrencyCode currency;

    public PaymentSettings(CurrencyCode currency) {
        this.currency = currency;
    }

    public CurrencyCode getCurrency() {
        return currency;
    }
}
```

If the bean definition passes a String value into a constructor argument of type `CurrencyCode`, the bean factory's conversion service can participate in resolving the argument. The outcome also depends on constructor metadata and the bean definition supplying enough information for Spring to identify the target type/argument accurately.

Conversion does not apply if a Java `@Bean` factory method already constructs the object of the right type directly:

```java
return new PaymentSettings(new CurrencyCode("USD"));
```

The snippet above constructs `CurrencyCode` directly; there is no String to convert.

### 5.3. Distinguishing from PropertyEditor

Traditional BeanFactory setups can use JavaBeans PropertyEditor to convert properties. When an appropriate `ConversionService` is configured, it serves as the preferred unified conversion mechanism. If an application still has custom editors, test precedence behavior for specific properties/types and avoid registering conflicting rules in both systems for the same type.

## 6. Integrating ConversionService with DataBinder

### 6.1. Attaching the Service to a Binder

`DataBinder` provides the API:

```java
PaymentForm form = new PaymentForm();
DataBinder binder = new DataBinder(form, "paymentForm");

binder.setConversionService(conversionService);
```

Once configured, the binder uses the service while binding `PropertyValues` into the target. In Spring MVC, `WebDataBinder` inherits this API so a service can be attached in `@InitBinder` or MVC's built-in conversion service can be used.

Sample input data:

```text
currency=eur
```

The expected result is that `form.getCurrency()` returns `CurrencyCode("EUR")` if the form has a writable property and the binder has received the converter.

### 6.2. Binding Data and Checking BindingResult

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("currency", "eur");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Return errors to the UI or calling layer
}
```

This is a fragment requiring imports for `MutablePropertyValues` and `BindingResult`. `DataBinder.bind` performs property binding; it does not invoke constructor binding. If you want constructor binding, the API flow is `binder.construct(valueResolver)`. These are two distinct operations even though both use the conversion service.

If the converter rejects `"invalid"`, DataBinder can record a field error in `BindingResult` instead of forcing the caller to catch exceptions directly every time. Inspect `result.getFieldErrors("currency")` and `result.hasErrors()` before using the target. Configuration errors or target-instantiation failures can still throw exceptions depending on the scenario.

### 6.3. WebDataBinder in Spring MVC

Integration example:

```java
@Controller
public class PaymentController {

    @InitBinder("paymentForm")
    void configure(WebDataBinder binder) {
        binder.setConversionService(conversionService);
    }

    @PostMapping("/payments")
    String submit(
            @ModelAttribute("paymentForm") PaymentForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "payment-form";
        }
        paymentService.save(form);
        return "redirect:/payments";
    }
}
```

This fragment requires a controller with `conversionService` and `paymentService` dependencies, a form model, and appropriate imports. `@InitBinder` applies only to the binder for the matching model attribute. In a standard MVC configuration, the framework usually already provides a formatting/conversion service; avoid creating a separate service inside every controller when it can be configured centrally at the MVC layer.

Using `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` lets you register converters/formatters for MVC. This mechanism brings conversion into the web environment; it does not replace separate configuration for a standalone `BeanFactory` created outside the MVC context.

## 7. Same Converter Across Both Flows: Runnable Java 17 Example

The example below demonstrates a single `StringToCurrencyCodeConverter` registered once on `DefaultConversionService`, with the **exact same service instance** attached to:

1. BeanFactory via `ConfigurableBeanFactory.setConversionService` to populate a bean from a bean definition.
2. DataBinder via `DataBinder.setConversionService` to bind a form object from `MutablePropertyValues`.

### 7.1. Project Structure

```text
conversion-integration-demo/
├── pom.xml
└── src/main/java/example/ConversionIntegrationDemo.java
```

`pom.xml` (Java 17 and Spring Framework 6.2.14):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>conversion-integration-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
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
          <mainClass>example.ConversionIntegrationDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/ConversionIntegrationDemo.java`:

```java
package example;

import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

public class ConversionIntegrationDemo {

    public record CurrencyCode(String value) {}

    public static final class StringToCurrencyCodeConverter
            implements Converter<String, CurrencyCode> {

        @Override
        public CurrencyCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Currency code is blank");
            }
            String code =
                source.strip().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException(
                    "Currency code must have three letters"
                );
            }
            return new CurrencyCode(code);
        }
    }

    public static class PaymentSettings {
        private CurrencyCode currency;

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static class PaymentForm {
        private CurrencyCode currency;

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
            new DefaultConversionService();
        conversionService.addConverter(
            new StringToCurrencyCodeConverter()
        );

        try (GenericApplicationContext context =
                 new GenericApplicationContext()) {

            ConfigurableListableBeanFactory beanFactory =
                context.getDefaultListableBeanFactory();

            // Integration #1: bean definition -> BeanFactory.
            beanFactory.setConversionService(conversionService);

            RootBeanDefinition definition =
                new RootBeanDefinition(PaymentSettings.class);
            definition.getPropertyValues().add("currency", " usd ");
            context.registerBeanDefinition("paymentSettings", definition);

            context.refresh();

            PaymentSettings settings =
                context.getBean("paymentSettings", PaymentSettings.class);

            // Integration #2: request-like values -> DataBinder.
            PaymentForm form = new PaymentForm();
            DataBinder binder = new DataBinder(form, "paymentForm");
            binder.setConversionService(conversionService);

            MutablePropertyValues values = new MutablePropertyValues();
            values.add("currency", " eur ");
            binder.bind(values);

            BindingResult result = binder.getBindingResult();

            if (result.hasErrors()) {
                throw new IllegalStateException(
                    "Binding failed: " + result.getAllErrors()
                );
            }

            System.out.println(
                "bean=" + settings.getCurrency().value()
            );
            System.out.println(
                "binder=" + form.getCurrency().value()
            );
            System.out.println("errors=" + result.hasErrors());
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Expected `stdout` when Maven prints no extra logs:

```text
bean=USD
binder=EUR
errors=false
```

Analysis:

- Line `bean=USD` proves the bean factory used the service to convert `" usd "` from the bean definition into `CurrencyCode` before the setter was called.
- Line `binder=EUR` proves DataBinder used that same conversion service to convert the value in `MutablePropertyValues`.
- Line `errors=false` shows the binder recorded no conversion errors in the valid scenario.
- Nowhere did code manually construct `new CurrencyCode("USD")` to assign to the bean; conversion ran through the registered converter.
- The example uses `GenericApplicationContext` and registers the bean definition before `refresh()`. BeanFactory is configured with the service before the `PaymentSettings` bean is created.

To test binder errors, replace `" eur "` with `"not-valid"`. The converter throws `IllegalArgumentException`; the binder normally records a type mismatch error in `BindingResult`. The demo intentionally throws `IllegalStateException` upon seeing errors to show the application does not proceed with a broken form. For bean definitions, converter failure occurs during bean creation and can cause `context.refresh()` to fail.

## 8. ConversionService with Collections, Maps, and TypeDescriptor

### 8.1. Why `Class<?>` Is Sometimes Not Enough

Basic API:

```java
conversionService.canConvert(String.class, Integer.class);
Integer age = conversionService.convert("21", Integer.class);
```

Easy to use when source and target are concrete single types. However, for `List<Integer>` and `List<String>`, both share runtime class `List.class`. Passing `List.class` alone does not describe the generic element type.

`TypeDescriptor` supplies metadata such as element types, map key/value types, and annotations on fields/properties. From this, Spring can convert each element to the exact target type.

### 8.2. Converting Generic Collections

Example:

```java
List<Integer> input = List.of(1, 2, 3);

List<String> output = (List<String>) conversionService.convert(
    input,
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class)
    ),
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(String.class)
    )
);
```

This is an illustrative fragment; it needs imports for `TypeDescriptor` and `List`, plus an appropriate generic cast/suppression because the metadata overload returns Object. With default converters registered, output is the list `"1"`, `"2"`, `"3"`. Each element conversion uses the appropriate `Integer → String` converter.

### 8.3. Arrays and Maps

`DefaultConversionService` provides several basic collection/array converters and reuses element converters when proper metadata is available. For Maps, both key and value types must be described; when converting Maps with different generics, use source/target `TypeDescriptor`s instead of relying on raw `Map.class`.

Example describing a Map's type descriptor:

```java
TypeDescriptor source = TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(String.class),
    TypeDescriptor.valueOf(Integer.class)
);
```

This fragment describes `Map<String, Integer>`; it does not execute conversion on its own unless passed with a source object and target descriptor to `convert(...)`.

### 8.4. When Is GenericConverter Needed?

Use `GenericConverter` when conversion depends on both source/target type metadata, nested generics, annotations, or property context. The interface takes a set of `ConvertiblePair` and the `convert(Object, TypeDescriptor, TypeDescriptor)` method. It is a flexible option, though more complex than `Converter<S,T>`. For a simple type like String → CurrencyCode, `Converter` suffices.

Do not write a custom collection converter solely to convert `List<S>` to `List<T>` if a scalar element converter and the default collection converters already handle it. Leverage the built-in conversion infrastructure before writing custom composite converters.

## 9. Common Configuration Patterns

| Configuration pattern | BeanFactory | DataBinder | When to use |
| --- | --- | --- | --- |
| `conversionService` bean in ApplicationContext | Context adopts it as conversion service | Can be used if binder is configured accordingly by MVC/context | Context-managed Spring applications |
| `ConfigurableBeanFactory.setConversionService` | Attaches directly to specific factory | Does not configure other binders automatically | Custom factories / low-level demos |
| `DataBinder.setConversionService` | Does not alter factory | Attaches to specific binder | Standalone binders outside MVC |
| `@InitBinder` | Does not alter factory | Attaches or customizes WebDataBinder | MVC controller, per attribute |
| `WebMvcConfigurer.addFormatters` | Does not configure standalone bean factories by default | Registers converters/formatters for MVC | Shared conversion at Spring MVC layer |
| `PropertyEditorRegistrar` | Can integrate via bean factory | Can be reused on binders | Legacy code compatibility |

### 9.1. Java Configuration with a Shared Converter

A Spring application can configure:

```java
@Configuration
public class AppConversionConfiguration {

    @Bean
    ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(
            new StringToCurrencyCodeConverter()
        );
        return service;
    }
}
```

When a Spring context detects a bean named `conversionService`, the service is used for framework conversion. In dedicated MVC setups, `FormattingConversionService`/`FormatterRegistry` may be the place to register additional formatters/converters depending on application type and MVC configuration.

### 9.2. Spring MVC Explicit Formatter Registration

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            new StringToCurrencyCodeConverter()
        );
    }
}
```

This is an MVC fragment requiring imports for `WebMvcConfigurer`, `FormatterRegistry`, and `Configuration`. If the converter is already in MVC's shared conversion service, do not register it twice. This targets web conversion/formatting; standalone bean factories still need the service configured in their corresponding context.

## 10. Coordinating PropertyEditor and ConversionService

Spring allows both systems to coexist. For legacy types not yet migrated to converters, custom `PropertyEditor`s may be kept in certain registries. However, having different conversion rules for the same type can make behavior hard to predict.

Actual precedence depends on property accessors, type converters, and custom editors registered by type/path. Therefore:

- Prefer stateless converters for general-purpose type conversion.
- Only use property-specific editors when stateful or JavaBeans-specific semantics are genuinely required.
- Do not register two rules for the same target with different normalization/validation without arbitration tests.
- Do not assume a `ConversionService` eliminates every `PropertyEditor` in the application; both APIs can coexist.
- For stateful editors, create fresh instances per registry/binder and avoid sharing mutable singletons.

## 11. Common Errors and Diagnostics

### 11.1. Registering the Converter on the Wrong Service

You call `conversionService.addConverter(...)` on instance A, while the binder is configured with instance B. Consequently, the binder reports it cannot convert. Compare the exact references passed to `setConversionService`, rather than merely checking that the converter class exists in source code.

### 11.2. Attaching the Service Too Late

If a bean was already created before calling `beanFactory.setConversionService(...)`, conversion for that creation has already occurred. Configure the service before `refresh()` or before target beans are instantiated; in standard contexts, use the conventionally named `conversionService` bean.

### 11.3. Converter Type Mismatch

`Converter<String, CurrencyCode>` does not automatically handle `Object → CurrencyCode` or `String → another type`. Inspect source/target descriptors and register converters for the right pairs. For hierarchy-based conversions, check `ConverterFactory` or `GenericConverter`.

### 11.4. Container Type Issues Due to Lost Generics

`List.class` does not say whether elements are `Integer` or `String`. For generic conversion, use `TypeDescriptor`; in bean property binding, property metadata normally tells Spring the generic type. When calling convert APIs manually, the caller must supply the corresponding descriptors.

### 11.5. Converter Throws an Exception

A converter should signal invalid input with an appropriate unchecked exception, typically `IllegalArgumentException`. In DataBinder, the error can become a FieldError; during bean creation, conversion failure can prevent the bean from being created. Never swallow exceptions and return a bogus default object.

### 11.6. Assuming Converters Validate Business Objects

Converters are only responsible for transforming data representation/type. `CurrencyCode("USD")` has valid shape per the example, yet whether the account is authorized to trade USD, what exchange rate applies, or whether the payment method supports USD is separate business logic. Validate after conversion or in the service layer.

### 11.7. Confusing with JSON Deserialization

`@RequestBody` normally uses `HttpMessageConverter` and a JSON mapper. ConversionService does not automatically replace Jackson deserializers. For custom JSON scalars, configure the JSON mapper appropriately or write a deserializer; converters may still be used in other binding steps.

### 11.8. Mutating the Registry While Multiple Threads Are Active

`ConversionService` is designed to be stateless and shared after configuration. Registering new converters while requests are running can cause unpredictable behavior. Finalize the registry at startup and treat it as immutable during operation.

## 12. Testing Integration Across Both Boundaries

You should have at least three groups of tests:

1. **BeanFactory test:** register converter/service, create a bean from a bean definition containing a String, verify the setter receives the right type/value.
2. **DataBinder test:** create a target, attach the service, bind property values, verify the target and `BindingResult`.
3. **Failure test:** pass malformed strings, verify the binder records appropriate errors and bean creation fails as expected.

Short binder test example:

```java
@Test
void dataBinderUsesCurrencyConverter() {
    DefaultConversionService service =
        new DefaultConversionService();
    service.addConverter(new StringToCurrencyCodeConverter());

    PaymentForm form = new PaymentForm();
    DataBinder binder = new DataBinder(form);
    binder.setConversionService(service);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("currency", " usd ");
    binder.bind(values);

    assertFalse(binder.getBindingResult().hasErrors());
    assertEquals("USD", form.getCurrency().value());
}
```

This is a test fragment using JUnit 5 and the demo classes. It requires corresponding imports/fixtures; the test verifies DataBinder conversion, not BeanFactory integration. Both boundaries must be tested separately because configuring one side does not guarantee the other works automatically.

## 13. Checklist for Choosing and Configuring Correctly

- Are you converting at **BeanFactory** or at **DataBinder**? If both, have you attached the service to both places?
- Is the bean named `conversionService` in the right ApplicationContext?
- If working at a low level, were `ConfigurableBeanFactory` and `DataBinder` configured before use?
- Does the converter have clear source/target types and remain stateless and thread-safe?
- Are null/blank/malformed inputs handled consistently and tested?
- For generic Lists/Maps/arrays, is `TypeDescriptor` needed to supply metadata?
- Are legacy `PropertyEditor`s registered alongside converters for the same type causing conflicts?
- Have you separated type conversion from validation and authorization?
- For JSON `@RequestBody`, have you verified the actual mapper/deserializer pipeline?
- Have you written separate tests for bean definitions, binders, and error cases?

## 14. Self-Check Exercises

### Exercise 1 — Identify the Right Registration Point

A `String → CurrencyCode` converter was added to `DefaultConversionService A`. A bean factory is configured with `DefaultConversionService B`. A DataBinder is configured with A. Which flow uses the converter?

**Answer:** DataBinder uses A so it sees the converter; the bean factory uses B so it does not automatically see A's converter. Either register the converter on B or attach service A to the bean factory as well.

### Exercise 2 — Predict the Output

The converter strips whitespace and uppercases. A bean definition contains `currency=" eur "`. The setter accepts `CurrencyCode`. What is the value?

**Answer:** `CurrencyCode("EUR")` if the bean factory has the right ConversionService attached and conversion succeeds.

### Exercise 3 — Why Is TypeDescriptor Needed?

A method calls `convert(inputList, List.class)` with `List<Integer>` expecting `List<String>`. Why is Class alone insufficient?

**Answer:** the runtime class of both is `List.class`. `TypeDescriptor.collection(...)` is needed to describe the source/target element types so Spring converts each element.

### Exercise 4 — Does Conversion Replace Validation?

The string `"USD"` converts to `CurrencyCode("USD")` successfully. Can we conclude the current transaction is allowed to use USD?

**Answer:** No. The converter only normalizes/converts the type; transaction permissions and business rules must be checked at the service/domain layer.

## 15. Official References

- Spring Framework Reference — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `Converter`, registries, default service, and `TypeDescriptor`.
- Spring Framework Reference — [Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, property binding, and conversion.
- Spring Framework Javadoc — [ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): `setConversionService` and how bean factories use type conversion.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `setConversionService` and binding mechanics.
- Spring Framework Javadoc — [DefaultConversionService](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html): default converters, registry, and conversion support.
- Spring Framework Reference — [Conversion and Formatting in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): configuring converters/formatters at the MVC layer.
