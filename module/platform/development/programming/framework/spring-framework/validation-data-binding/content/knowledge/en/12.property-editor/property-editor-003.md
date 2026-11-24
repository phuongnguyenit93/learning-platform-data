# Registering PropertyEditor by Type or Property Path in Spring Framework

## 1. Why Choose an Editor Registration Scope?

When Spring binds external input into a JavaBean, incoming values are usually strings, while target properties may be `LocalDate`, `Integer`, `Date`, custom domain types, or collections. **PropertyEditor** is the JavaBeans mechanism that converts a text representation into a Java value acceptable to a setter or constructor.

Spring supports **two custom editor registration scopes**:

1. **By type (`requiredType`):** one editor is used for properties of that matching type within that registry/binder's scope.
2. **By path (`propertyPath`):** one editor is attached to a specific property, such as `"delivery.shipOn"`, to handle it differently from other properties of the same type.

Example model with two `LocalDate` fields:

```text
OrderForm
├── createdOn: LocalDate       <-- ISO string: 2026-11-02
└── delivery: Delivery
    └── shipOn: LocalDate      <-- day/month/year string: 03/11/2026
```

If one editor is registered for all of `LocalDate.class`, both fields use the same conversion rule. However, `shipOn` requires a different format from `createdOn`. We can register a general editor for `LocalDate` and a **dedicated editor for the `delivery.shipOn` path**. When binding that exact path, the property-specific editor takes precedence over the general type-based editor.

This is built-in behavior of **Spring PropertyEditorRegistry**, usable via `BeanWrapperImpl`, `DataBinder`, or `WebDataBinder`. It differs from validation annotations: editors handle **representation/data type conversion**, while validators check **business/constraint validity**.

## 2. Core API: PropertyEditorRegistry

The `org.springframework.beans.PropertyEditorRegistry` interface declares two key overloads:

```java
void registerCustomEditor(
        Class<?> requiredType,
        java.beans.PropertyEditor propertyEditor);

void registerCustomEditor(
        Class<?> requiredType,
        String propertyPath,
        java.beans.PropertyEditor propertyEditor);
```

The signatures above are simplified for illustration, omitting nullable annotations. Notable implementations include `BeanWrapperImpl`, `DataBinder`, and `WebDataBinder`.

| Call | Registration scope | Use case |
| --- | --- | --- |
| `registerCustomEditor(LocalDate.class, editor)` | All `LocalDate` properties handled by that registry | All dates follow the same ISO format |
| `registerCustomEditor(LocalDate.class, "delivery.shipOn", editor)` | Only `delivery.shipOn` | Delivery date uses `dd/MM/uuuu` |
| `registerCustomEditor(String.class, "displayName", editor)` | Only the `displayName` string | Trim/normalize display name |
| `registerCustomEditor(String.class, editor)` | Every `String` property | Default string normalization, if truly desired |
| `registerCustomEditor(null, "delivery.shipOn", editor)` | Path-based registration without declaring type | Valid for scalar cases with an explicit path; specify type when known |

**`requiredType`** is the Java type of the property, or of the collection element when registering per element. **`propertyPath`** is the property name relative to **the object being bound/wrapped**, not a URL and without prepending the model attribute name.

For example, if the target bean is `orderForm` in a controller, the right path name is typically:

```text
delivery.shipOn
```

Do not turn it into `orderForm.delivery.shipOn` just because `@ModelAttribute("orderForm")` has that name. The path must match the property structure the binder actually sees.

With the two-argument overload, `requiredType` is required and no path is specified. With the three-argument overload, Spring allows type or path according to API rules. For collections/arrays, **always specify the type** so Spring knows whether the editor converts the whole collection or individual elements.

### Registry scope

Registering on `new BeanWrapperImpl(bean)` affects only that wrapper. Registering on `new DataBinder(bean)` affects only that binder. Registering inside a Spring MVC `@InitBinder` method applies to binders within the relevant controller/model attribute scope. It does not automatically become an application-wide parsing rule or a Jackson JSON conversion rule.

## 3. Which Editor Does Spring Pick When Both Type and Path Exist?

Suppose two registrations exist:

```java
wrapper.registerCustomEditor(
        LocalDate.class, new IsoDateEditor());

wrapper.registerCustomEditor(
        LocalDate.class, "delivery.shipOn",
        new DayMonthYearEditor());
```

When Spring needs to convert `createdOn` (also a `LocalDate`), there is no registration specific to `createdOn`, so it uses `IsoDateEditor` by type. When converting `delivery.shipOn`, a path-specific registration exists, so `DayMonthYearEditor` is chosen.

Practical mental model:

```text
convert(raw="2026-11-02", target=LocalDate, path="createdOn")
  -> look up specific editor for path "createdOn": none
  -> look up editor by type LocalDate: IsoDateEditor
  -> LocalDate(2026-11-02)

convert(raw="03/11/2026", target=LocalDate, path="delivery.shipOn")
  -> look up specific editor for path: DayMonthYearEditor
  -> LocalDate(2026-11-03)
```

**A specific path can override a general type rule during lookup.** Do not rely on `HashMap` key order of inputs or field declaration order to guess which editor is chosen. Verify with binding results and tests whenever you register multiple rules.

Spring's mechanism distinguishes custom-registered editors from **default editors** provided out of the box by `BeanWrapperImpl` and configured conversion services. A custom editor chosen for a specific property can alter that property's default behavior. Thus, the broader the type registration, the wider its impact.

## 4. Runnable Java 17+ Example: One General Editor, One Path Editor

This example uses **Spring Framework 6.2.x**, Java 17+, and Maven, without Spring Boot or an HTTP server. The goal is to see two `LocalDate` properties accept two different formats while still being stored as the same Java type.

### 4.1. pom.xml

Create `pom.xml` in the Maven project directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>property-editor-scope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-beans` provides `BeanWrapperImpl` and pulls in the required Spring Core dependencies. `spring-boot-starter-web` is not needed to use the wrapper directly.

### 4.2. A complete Java file

Create `src/main/java/demo/EditorScopeDemo.java`:

```java
package demo;

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.BeanWrapperImpl;

public class EditorScopeDemo {

    public static class Delivery {
        private LocalDate shipOn;

        public Delivery() {}

        public LocalDate getShipOn() {
            return shipOn;
        }

        public void setShipOn(LocalDate shipOn) {
            this.shipOn = shipOn;
        }
    }

    public static class OrderForm {
        private LocalDate createdOn;
        private Delivery delivery = new Delivery();

        public OrderForm() {}

        public LocalDate getCreatedOn() {
            return createdOn;
        }

        public void setCreatedOn(LocalDate createdOn) {
            this.createdOn = createdOn;
        }

        public Delivery getDelivery() {
            return delivery;
        }

        public void setDelivery(Delivery delivery) {
            this.delivery = delivery;
        }
    }

    public static class IsoDateEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text.trim()));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : value.toString();
        }
    }

    public static class DayMonthYearEditor
            extends PropertyEditorSupport {

        private static final DateTimeFormatter FORMAT =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text.trim(), FORMAT));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : value.format(FORMAT);
        }
    }

    public static void main(String[] args) {
        OrderForm form = new OrderForm();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(form);

        // Applies to LocalDate properties in general.
        wrapper.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        // Applies only to this nested property.
        wrapper.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());

        wrapper.setPropertyValue("createdOn", "2026-11-02");
        wrapper.setPropertyValue(
                "delivery.shipOn", "03/11/2026");

        System.out.println(
                "createdOn=" + form.getCreatedOn());
        System.out.println(
                "delivery.shipOn="
                        + form.getDelivery().getShipOn());
        System.out.println(
                "sameTarget="
                        + (wrapper.getWrappedInstance() == form));
    }
}
```

### 4.3. Run command and output

In the directory containing `pom.xml`, with Maven and JDK 17+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.EditorScopeDemo
```

Stdout from `main` (excluding Maven logs):

```text
createdOn=2026-11-02
delivery.shipOn=2026-11-03
sameTarget=true
```

Why:

1. Both `createdOn` and `delivery.shipOn` are `LocalDate` with JavaBeans getters/setters.
2. For `createdOn`, the `LocalDate.class` type rule picks `IsoDateEditor`. The ISO string parses to `2026-11-02`.
3. For `delivery.shipOn`, the path rule picks `DayMonthYearEditor`. The string `03/11/2026` is parsed as day/month/year, yielding `2026-11-03`.
4. `Delivery` is already initialized inside `OrderForm`, so the nested property has an intermediate object; the example does not need auto-grow enabled.
5. `sameTarget=true` shows that the wrapper mutates the `form` object directly rather than creating a copy.

Here `PropertyEditorSupport.setAsText(...)` is responsible for converting the string into the target value via `setValue(...)`. `getAsText()` supports the reverse direction when a component needs a text representation of the object; the example's output calls `LocalDate.toString()` directly so it does not depend on `getAsText()`.

**Example limitation:** `LocalDate.parse(...)` will throw an error on malformed strings. The program intentionally uses valid data to illustrate editor selection. When handling web input, use `WebDataBinder` to collect type conversion errors into `BindingResult` in the appropriate context.

## 5. Registering Directly on DataBinder and Reading BindingResult

In applications accepting multiple inputs, `DataBinder` combines property binding, type conversion, and error recording. You do not need to catch exceptions manually for every setter while binding multiple fields.

The snippet below **belongs inside a method**, using `OrderForm`, `IsoDateEditor`, and `DayMonthYearEditor` from the example above:

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

OrderForm form = new OrderForm();
DataBinder binder = new DataBinder(form, "orderForm");

// Allow only the two example keys when using untrusted input sources.
binder.setAllowedFields("createdOn", "delivery.shipOn");

binder.registerCustomEditor(
        java.time.LocalDate.class, new IsoDateEditor());
binder.registerCustomEditor(
        java.time.LocalDate.class, "delivery.shipOn",
        new DayMonthYearEditor());

binder.bind(new MutablePropertyValues(Map.of(
        "createdOn", "2026-11-02",
        "delivery.shipOn", "03/11/2026")));

BindingResult errors = binder.getBindingResult();

if (errors.hasErrors()) {
    System.out.println("Binding failed");
} else {
    System.out.println(form.getCreatedOn());
    System.out.println(form.getDelivery().getShipOn());
}
```

Expected output of the `else` branch:

```text
2026-11-02
2026-11-03
```

This snippet needs imports for the nested `EditorScopeDemo` classes adjusted to wherever the code lives; it is a snippet that **does not compile standalone** unless placed inside a class/method with those types. The main flow is **register before calling `bind(...)`**, then read `BindingResult`.

If `"delivery.shipOn"` receives `"31/02/2026"`, the day/month/year editor cannot parse it into a valid date. During property binding, `DataBinder` typically records a `FieldError` with a code related to `typeMismatch`. Checking it:

```java
BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("delivery.shipOn")) {
    System.out.println("Invalid delivery date");
}
```

This is also an in-method snippet. `DataBinder` records binding errors; **that does not mean Bean Validation has run** for constraints like `@NotNull` or `@Future`. To check constraints, configure and invoke a validator (or use `@Valid` in MVC) separately.

## 6. Registering via @InitBinder in Spring MVC

When using Spring MVC, `WebDataBinder` is created by the framework to bind request parameters onto `@ModelAttribute`. Instead of constructing a binder manually, place editor configuration in an `@InitBinder` method.

Controller example (this is an **integration pattern**; `OrderForm` and the editor classes live in the project as in section 4, requiring the corresponding Spring MVC/validation dependencies):

```java
import java.time.LocalDate;

import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class OrderController {

    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "createdOn", "delivery.shipOn");

        binder.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        binder.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());
    }

    @PostMapping("/orders")
    public String save(
            @ModelAttribute("orderForm") OrderForm orderForm,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "order-form";
        }

        // Service continues processing if the form is valid.
        return "order-success";
    }
}
```

**Proper application:** Place `OrderController` in `OrderController.java` in an appropriate package, add imports/definitions for `OrderForm`, `IsoDateEditor`, `DayMonthYearEditor`, and the views `order-form` / `order-success`. In this example, `BindingResult` sits **immediately after** the `@ModelAttribute` parameter to receive binding errors. You need `@Valid` and a validation provider to run Jakarta Bean Validation; a property editor itself only converts types.

A form may submit:

```text
createdOn=2026-11-02&delivery.shipOn=03%2F11%2F2026
```

Keys must match the declared property paths. `@InitBinder("orderForm")` targets only binders for the model attribute named `"orderForm"` within the controller's context; `@InitBinder` without a name has broader scope inside the controller. `@ControllerAdvice` can declare shared `@InitBinder` methods across multiple controllers, though care is needed regarding model names and multi-request impact.

Note: `@ModelAttribute` editors are used in form/query data binding; **`@RequestBody` JSON** typically goes through an `HttpMessageConverter`, such as Jackson, rather than automatically using these editors to parse individual JSON properties.

## 7. Nested Paths and Indexed Properties: Names Must Match

Paths can be:

| Property path | Target |
| --- | --- |
| `startDate` | `startDate` property on the target object |
| `delivery.shipOn` | `shipOn` property on the `delivery` bean |
| `customer.address.postalCode` | Multi-level nested property |
| `items[0].quantity` | Field of element at index 0 |
| `items[2].quantity` | Field of element at index 2 |
| `settings[region]` | Map value by key |
| `tags` | Entire collection/list if `tags` is a collection property |

For lists, there is an important detail in `PropertyEditorRegistry`'s Javadoc:

> To register an editor for `items[n].quantity` at every index `n`, you can use the path name `items.quantity`.

Example:

```java
binder.registerCustomEditor(
        Integer.class, "items.quantity",
        new CustomNumberEditor(Integer.class, false));
```

This snippet requires importing `org.springframework.beans.propertyeditors.CustomNumberEditor`, inside a method with `binder`. This registration expresses applying the rule to the `quantity` field of elements in `items` (assuming matching types and model structure); Spring has canonical/path-matching logic that strips indices. Do not invent asterisk syntax `items[*].quantity` or literal `items[n].quantity` as registration strings if the API does not define wildcards that way. For complex path variants, verify with unit tests on the Spring version you run.

### Editor for the collection or editor for elements?

Suppose `OrderForm` has `List<LocalDate> holidays`. Two completely different requirements exist:

1. Parse **one input string or object** into the **entire `List<LocalDate>`**.
2. Parse **each element string** into a `LocalDate` inside the list.

Specify `requiredType` and the corresponding path clearly:

```java
// Editor must be able to create the whole List; this is an API illustration.
binder.registerCustomEditor(
        java.util.List.class, "holidays", wholeListEditor);

// Editor must create a LocalDate for each element.
binder.registerCustomEditor(
        java.time.LocalDate.class, "holidays",
        oneDateEditor);
```

The two lines above are **two alternative designs**, not registered simultaneously for the same `holidays`. The variables `wholeListEditor`/`oneDateEditor` represent project-defined `PropertyEditor` implementations; this is not a standalone Java snippet. According to Spring documentation, if a path points to an array/collection, the editor can apply to **the whole collection** or **its elements**, depending on `requiredType`. Spring warns that **only one custom editor is supported per property path**, so do not register both the collection type and the element type on the same path.

In particular, **do not pass `requiredType = null` for an array/collection** because it becomes ambiguous whether the editor targets the container or the element.

## 8. Built-in PropertyEditors Worth Knowing

Not every editor must be written from scratch with `PropertyEditorSupport`. Spring provides many editors in package `org.springframework.beans.propertyeditors`:

| Editor | Purpose | Notes |
| --- | --- | --- |
| `StringTrimmerEditor` | Trims leading/trailing whitespace; can convert empty strings to `null` | Not registered by default |
| `CustomDateEditor` | Parses/formats `java.util.Date` with `DateFormat` | Register when needed; distinct from `LocalDate` |
| `CustomNumberEditor` | Parses/formats several `Number` subclasses | Can customize number handling |
| `CustomBooleanEditor` | Parses booleans with customizable rules | Spring has a default editor that can be overridden |
| `CustomCollectionEditor` | Converts a collection to a target collection type | Pay attention to element/collection types |
| `ClassEditor` | Converts a class name to `Class<?>` | Typically available by default |
| `LocaleEditor` | Parses/formats `Locale` | Typically available by default |
| `PatternEditor` | Parses regex `Pattern` | Supported by default in some contexts |

Example trimming only a `displayName` property:

```java
import org.springframework.beans.propertyeditors.StringTrimmerEditor;

// Inside @InitBinder or a method with binder:
binder.registerCustomEditor(
        String.class, "displayName",
        new StringTrimmerEditor(true));
```

`true` means that after trimming, an empty string becomes `null`. Scoping by path avoids automatically trimming other `String` properties where the application needs exact whitespace preserved, such as passwords or strings with meaningful spaces.

If you want to trim all `String`s on a binder:

```java
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(false));
```

`false` keeps an empty string after trimming as `""` instead of converting it to `null`. However, such a broad registration affects many properties, so evaluate the semantics of each field. **Do not assume every string should be trimmed.**

### Legacy Date and modern Date/Time API

Spring's `CustomDateEditor` works with `java.util.Date`; do not use `CustomDateEditor` to directly parse a `LocalDate` property. For `java.time.LocalDate`, prefer `Formatter` or `Converter` (and `@DateTimeFormat` when web integration fits), or a custom editor like in the main example if you specifically need the PropertyEditor API.

Example date editor for `java.util.Date` in a controller:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import org.springframework.beans.propertyeditors.CustomDateEditor;

SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd");
formatter.setLenient(false);

binder.registerCustomEditor(
        Date.class, "birthDate",
        new CustomDateEditor(formatter, true));
```

This snippet belongs inside an `@InitBinder` method (requiring a valid `binder`). `true` allows empty values instead of requiring a date; invalid date formats still yield appropriate errors. `SimpleDateFormat` has mutable state, so create a separate instance per binder instead of sharing a singleton across requests.

## 9. PropertyEditorRegistrar for Reusing Configuration

If multiple controllers need the same set of rules, duplicating `registerCustomEditor(...)` calls becomes hard to maintain. Spring provides the `PropertyEditorRegistrar` interface:

```java
package demo;

import java.time.LocalDate;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class OrderEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(
            PropertyEditorRegistry registry) {

        registry.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        registry.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());
    }
}
```

The snippet above is a **sample class** requiring the two custom editor classes defined in the project; if the editors are nested classes inside `EditorScopeDemo`, import or qualify them. `OrderEditorRegistrar` does not run `bind(...)` itself: it only registers editors on the passed-in registry.

In a controller:

```java
private final PropertyEditorRegistrar editors;

public OrderController(PropertyEditorRegistrar editors) {
    this.editors = editors;
}

@InitBinder("orderForm")
void initBinder(WebDataBinder binder) {
    editors.registerCustomEditors(binder);
    binder.setAllowedFields("createdOn", "delivery.shipOn");
}
```

This is a snippet of `@Controller` class members; you must configure a bean implementing `PropertyEditorRegistrar` and inject it via the constructor. **Rule to uphold:** a registrar can be reused, but each call to `registerCustomEditors` should **create new editor instances** to avoid sharing state across binders/requests. Spring emphasizes this in its official documentation as well.

`CustomEditorConfigurer` can integrate registrars/editors into the **IoC BeanFactory** when configuring bean properties. That is the **bean configuration** scope, distinct from registering on `WebDataBinder` for HTTP requests. Do not assume container-level registration automatically makes every `@ModelAttribute` binder and JSON converter apply the same rules.

## 10. Scope and Lifecycle: Which Binder Owns Each Editor?

`java.beans.PropertyEditor` is a stateful API. Implementations typically store the current value via `setValue(...)` / `getValue()`; many editors also hold formatters or parse settings.

This leads to the following principles:

- Create fresh editors when constructing a new `BeanWrapperImpl` or `DataBinder`; inside `@InitBinder`, create editors per binder.
- Do not hold a shared mutable `PropertyEditorSupport` in a singleton controller and hand it to every request.
- Do not pass the same mutable `SimpleDateFormat` into multiple editors across concurrent requests.
- A `PropertyEditorRegistrar` object can be reused if the registrar holds no mutable editor instances and instantiates fresh editors on each registration.
- Do not treat a custom editor as a singleton bean merely because it converts between String and a common type.

Example of **what not to do**:

```java
// Flawed design sharing mutable state across concurrent requests:
private static final DayMonthYearEditor SHARED_EDITOR =
        new DayMonthYearEditor();

@InitBinder
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, SHARED_EDITOR);
}
```

This is an illustrative anti-pattern requiring a controller class/method context. A fresh editor per registration is easier to reason about safely:

```java
@InitBinder
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, new DayMonthYearEditor());
}
```

Even though `DateTimeFormatter` itself is immutable and shareable, **`PropertyEditorSupport`** remains a stateful object. Thus, holding a `static final DateTimeFormatter` does not mean you should hold a `static final` editor.

## 11. How Do Editor, Converter, and Formatter Differ?

Spring supports multiple data conversion layers:

| Mechanism | Main API | Usage orientation |
| --- | --- | --- |
| JavaBeans `PropertyEditor` | `setAsText`, `getAsText`, `setValue` | Legacy/custom binders or very specific rules |
| Spring `Converter<S,T>` | `T convert(S source)` | Converts one source type to one target type, usually stateless |
| Spring `Formatter<T>` | `parse(String, Locale)`, `print(T, Locale)` | Locale-aware parsing/formatting |
| `ConversionService` | `convert(...)`, `canConvert(...)` | Registry executing conversions reused across layers |
| `@DateTimeFormat` / `@NumberFormat` | Annotation on field/parameter | Format hints with compatible formatting infrastructure |

**When to keep using PropertyEditor?** When the system already uses `PropertyEditorRegistry`/`@InitBinder`, has path-specific requirements, relies on legacy custom editors that should be preserved, or has specialized parse logic belonging to one binder.

**When to prefer Formatter/Converter?** When writing new code needing conversion reused across layers, locale awareness, or centralized registration in `FormattingConversionService`. To give `delivery.shipOn` a different format without writing an editor, you can also consider `@DateTimeFormat` directly on the property or a custom formatter mechanism as needed.

**Do not describe `PropertyEditor` as an equally safely shareable `Converter`.** `Converter` is usually written statelessly, whereas `PropertyEditor` usually holds a mutable value. Similarly, `PropertyEditor#getAsText()` does not automatically turn into a Jackson JSON serializer.

### When ConversionService and custom editors coexist

Resolution mechanics can depend on type, path, matching converters, and binder configuration. A custom editor registered for a specific path is usually a highly specific match for that property. When conflicts arise between type-based and path-based conversions, verify with tests on the exact Spring version you run rather than vaguely assuming registration order always decides everything.

## 12. Binding Errors and Inspecting FieldError

An editor parsing an invalid string may raise an exception. With `BeanWrapperImpl.setPropertyValue(...)` directly, callers typically receive a Spring Beans/property access exception. With `DataBinder.bind(...)`, type/property conversion failures are usually recorded as `FieldError`s in `BindingResult`.

Example:

```text
createdOn=2026-11-02
delivery.shipOn=31/02/2026
```

With the editors in the example, `31/02/2026` is a nonexistent calendar date. `LocalDate.parse` cannot produce a `LocalDate`; in a properly configured binder, the result can be a `typeMismatch` error on `delivery.shipOn`.

Useful methods:

```java
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    result.getFieldErrors().forEach(error -> {
        System.out.println("field=" + error.getField());
        System.out.println("code=" + error.getCode());
        System.out.println(
                "bindingFailure=" + error.isBindingFailure());
    });
}
```

This snippet must be placed in a method with a `binder` variable of type `DataBinder`. Do not print `getRejectedValue()` to production logs because it may contain sensitive input. For web forms, responses should include safe field names and messages resolved via `MessageSource` or the API's error DTO.

**Format conversion does not replace validation:** `@NotNull`, `@Past`, `@Future`, and business constraints must be checked by Bean Validation or a Spring Validator. An editor only attempts to parse and assign the value to a property. A value that converts successfully can still violate business rules.

## 13. Safety When Using Field-Specific Editors

Using a field-specific editor can reduce unintended side effects compared to broad type-wide registration. However, **an editor is not an access control filter** and does not restrict which fields a client is allowed to bind.

Suppose a bean has:

```text
OrderForm
├── createdOn
├── delivery.shipOn
├── approved
├── price
└── role
```

Registering an editor only for `delivery.shipOn` **does not prevent** a client from trying to send `approved=true` or `role=ADMIN` if the model has writable properties and the binder allows binding them. For untrusted input:

1. Use request DTOs containing only fields the client is allowed to submit.
2. Restrict property binding, e.g., `binder.setAllowedFields("createdOn", "delivery.shipOn")`.
3. Validate data structure and bound nesting depth/indices for nested/collection inputs.
4. Enforce authorization in the service layer before updating real entities.
5. Never let a custom editor perform arbitrary external I/O based on request strings, such as opening files, fetching URLs, or running uncontrolled database queries.
6. Avoid parsing sensitive data and logging raw inputs or exceptions containing raw inputs.

An editor should only convert data; authorization and business state decisions belong to the service/authorization layers.

## 14. Common Configuration Mistakes and Troubleshooting

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Field-specific editor does not run | Wrong `propertyPath` or extra model name prefix | Compare property name relative to target, e.g. `delivery.shipOn` |
| Two fields of the same type parse identically | Only type editor registered, missing field-specific editor | Register the three-argument overload |
| General editor alters unexpected fields | Used `String.class` / `Date.class` on a binder with many properties | Narrow by path or use annotations/formatters |
| Error with nested path | Intermediate bean is `null` or property is not writable | Initialize child object or configure appropriate auto-grow |
| CustomDateEditor does not apply to LocalDate | Editor targets `java.util.Date` | Write a matching-type editor or use a Java Time formatter |
| Used `items[*].quantity` but did not match | Assumed wildcard syntax | Follow Javadoc example, use `items.quantity` and test indexed properties |
| Collection elements are not parsed | Registered editor for container instead of element | Check `requiredType`/generic type/path |
| Registered two editors on same collection path | API supports only one custom editor per path | Choose design for either the collection or the element |
| Requests share the same editor | Mutable editor was reused | Instantiate a fresh editor in `@InitBinder`/registrar |
| Invalid date does not produce desired validation message | Only parsing exists, missing message codes/validator | Inspect `BindingResult`, configure messages/validation |
| JSON request ignores `@InitBinder` editor | Body is parsed by HTTP message converter | Configure Jackson for JSON |
| Registered after binding finished | Conversion already ran | Register editors before `bind(...)` |
| No setter exists | Property is not writable | Check JavaBean getters/setters |
| Only `getAsText` implemented, no `setAsText` | Missing String -> value logic | Implement the needed conversion direction |
| Editor throws `IllegalArgumentException` on bad input | Invalid format/value | Let binder handle the error and return a clear response |
| Assumed type editor applies system-wide | Registry belongs only to current binder/wrapper | Identify BeanFactory/MVC/binder scope |

For controllers, use integration tests submitting real forms to verify path-based binding behavior, because verifying an editor directly with `BeanWrapperImpl` does not prove every `@RequestBody` or controller route will use it.

## 15. Testing Both Registration Scopes Properly

A solid test suite should cover at least:

| Test | Input | Expected result |
| --- | --- | --- |
| Type-based editor | `createdOn=2026-11-02` | `LocalDate 2026-11-02` |
| Path-based editor | `delivery.shipOn=03/11/2026` | `LocalDate 2026-11-03` |
| Wrong format for path | `delivery.shipOn=2026-11-03` | Rejected by the DMY editor in the example |
| Nonexistent date | `delivery.shipOn=31/02/2026` | Type conversion error |
| Uninitialized nested object | `delivery=null` | Requires proper initialization/auto-grow |
| Other properties of same type | Add `cancelledOn=2026-11-04` | Uses registry's default type editor if no path-specific editor exists |
| Collection element | `items[0].quantity=2` | Element editor chosen by matching path/type |
| No state leakage | Multiple independent binders/requests | Editor instances and results per binder remain independent |
| Mass assignment | Also send `approved=true` | Binder/DTO does not write disallowed fields |

### Self-checking at registration point

`BeanWrapperImpl` and corresponding registries also provide editor lookup:

```java
import java.beans.PropertyEditor;
import java.time.LocalDate;

PropertyEditor forCreated =
        wrapper.findCustomEditor(
                LocalDate.class, "createdOn");

PropertyEditor forDelivery =
        wrapper.findCustomEditor(
                LocalDate.class, "delivery.shipOn");
```

Inside a method of the runnable example, `forCreated` and `forDelivery` are the two editors found for their respective path/type. You can assert with `instanceof` or run inputs in two different formats. This is a **snippet** assuming an already configured `wrapper` variable; it is not a standalone program.

Checking `findCustomEditor` alone is not enough to confirm end-to-end conversion succeeds: execute `setPropertyValue(...)`/`DataBinder.bind(...)` against a DTO with actual getters/setters and verify the final target state.

### Testing messages and locales

If the application supports multiple locales, test regional formats and translated error messages. Use `Formatter` if parsing truly depends on the request-driven `Locale`, rather than hardcoding one format in a singleton editor for all users.

## 16. Checklist for Applying in a Spring Project

1. **Identify target:** verify property name and Java type, writable getters/setters, and initialized nested objects.
2. **Choose scope:** type if all properties of that type share the rule; path if one property needs a distinct rule.
3. **Choose overload:** `registerCustomEditor(Class, editor)` or `registerCustomEditor(Class, propertyPath, editor)`.
4. **For collections:** clarify whether the editor converts the container or each element; do not register conflicting editors on the same path.
5. **Register in the right place:** `BeanWrapperImpl` or `DataBinder` directly; `@InitBinder` for web forms; `PropertyEditorRegistrar` for reuse.
6. **Instantiate fresh editors per binder:** especially with stateful `PropertyEditorSupport` and mutable `SimpleDateFormat`.
7. **Register before binding:** do not wait until after fields have been converted.
8. **Inspect errors:** check `BindingResult` and message codes for type-mismatch inputs, then run validation separately if configured.
9. **Restrict client-accepted fields:** use DTOs and `setAllowedFields(...)` when using property binding.
10. **Test both type and path:** happy path, path-specific override, bad data, nested/indexed input, multi-request isolation, and security.
11. **Consider newer tools:** `Converter`/`Formatter`/`ConversionService` if conversion logic is broadly reusable or locale-aware.

## 17. Key Takeaways

**Type-based registration** has broad scope within a registry: `registerCustomEditor(LocalDate.class, editor)` applies to matching date properties. **Path-based registration** is more precise: `registerCustomEditor(LocalDate.class, "delivery.shipOn", editor)` targets only the delivery date in the object graph. When multiple formats are needed across fields of the same type, combining both scopes preserves a general rule alongside deliberate exceptions.

Editors handle value conversion; binder scope determines where registrations apply; DTOs/allowed fields determine which fields are accepted; validators and authorization determine what data is valid and permitted. Understanding these boundaries avoids letting a custom editor affect an entire form or fail to run due to a mismatched property path.

## References

- [Spring Framework — PropertyEditorRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework — PropertyEditorRegistrySupport API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistrySupport.html)
- [Spring Framework — Data Binding / PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — PropertyEditorRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework — StringTrimmerEditor API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html)
- [Spring Framework — CustomDateEditor API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/propertyeditors/CustomDateEditor.html)
