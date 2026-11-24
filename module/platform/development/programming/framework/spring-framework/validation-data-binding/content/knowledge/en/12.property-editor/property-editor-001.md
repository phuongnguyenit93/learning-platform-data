# PropertyEditor and PropertyEditorSupport in the JavaBeans Standard

In JavaBeans, a property has a **concrete data type** (for example `LocalDate`, `URL`, or a custom product code), but configuration tools or user interfaces may receive it as **text**. The `java.beans.PropertyEditor` interface is the standard JDK contract for an object to support editing/representing a property value. The `java.beans.PropertyEditorSupport` class provides a skeleton implementation for that contract.

Spring Framework uses the JavaBeans `PropertyEditor` mechanism in **data binding** and bean configuration. When a string enters a Java property, Spring can ask the corresponding editor to parse `String -> Object`; when a value needs to be represented as text, the editor can support `Object -> String`. An editor is not a Bean, not a Bean's getter/setter, and not a Validator.

This article focuses on JavaBeans origins, method contracts, how to write an editor using `PropertyEditorSupport`, how to register it in `BeanWrapper`/`DataBinder`/Spring MVC, stateful lifecycle, and choosing between legacy editors and modern `Converter`/`Formatter`. The main examples use Java 17+, Maven, and Spring Framework 6.2.x.

## 1. The Problem PropertyEditor Solves

Suppose a form has a `productCode` field of Java type `ProductCode`:

```java
public record ProductCode(String value) {}
```

This is a data type, not a `String`. Meanwhile, the user enters the text `"ab-012"`. Before calling the setter `setProductCode(ProductCode)`, the application needs rules:

1. Trim leading and trailing whitespace.
2. Normalize letters to uppercase.
3. Validate the `AA-999` syntax.
4. Create a new `ProductCode`.
5. When displaying, convert `ProductCode("AB-012")` into the text `"AB-012"`.

```text
                     JavaBeans PropertyEditor

                     setAsText(String)
"ab-012"  --------------------------------->  ProductCode("AB-012")
                     setValue(Object)             |
                                                   |
"AB-012"  <---------------------------------  getValue()
                     getAsText()
```

With a stateful editor, `setAsText(...)` does not return the object via its return value: it **sets the value inside the editor** (usually via `setValue(...)`). The caller reads it back with `getValue()`. Conversely, `setValue(...)` supplies a typed value; `getAsText()` provides the text representation of the current value.

**Important:** `PropertyEditor` itself does not know which properties are allowed to be modified or who has permission to modify them. It is a **value conversion/editing mechanism**, not an authorization or business validation tool.

## 2. How Does a JavaBeans Property Differ from a Java Field?

By JavaBeans convention, a property is typically represented by a getter/setter:

```java
public final class ProductForm {
    private ProductCode productCode;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }
}
```

The class above is an example of a mutable JavaBean; `ProductCode` is defined externally. When Spring `BeanWrapper` processes the `productCode` property, it can use JavaBeans introspection to see that the setter requires type `ProductCode`. If the input is a `String`, the system can invoke a registered editor to create a `ProductCode` and pass it to the setter.

Three objects should not be conflated:

| Component | Responsibility |
| --- | --- |
| `ProductForm` (target bean) | Holds data, provides getter/setter |
| `ProductCode` (value object) | Represents a typed product code |
| `ProductCodeEditor` (property editor) | Converts text to `ProductCode` and vice versa |

The name `PropertyEditor` comes from the JavaBeans infrastructure for property editing tools, including GUI tools. It **does not mean** every editor must have a graphical interface, and certainly not a source code editor like an IDE.

## 3. The java.beans.PropertyEditor Contract

`PropertyEditor` resides in package `java.beans`, part of JDK module `java.desktop`. When using a full JDK, no extra Spring dependency is needed just to reference this standard JavaBeans interface.

| Group | API | Meaning |
| --- | --- | --- |
| Typed value | `setValue(Object)`, `getValue()` | Updates/reads the value state the editor is editing |
| Text conversion | `setAsText(String)`, `getAsText()` | Parses text and retrieves text representation |
| State changes | `addPropertyChangeListener(...)`, `removePropertyChangeListener(...)` | Registers/unregisters listeners for value changes |
| Enumerated options | `getTags()` | Finite set of text choices, if any |
| Paint options | `isPaintable()`, `paintValue(Graphics, Rectangle)` | For JavaBeans GUI tools |
| UI options | `supportsCustomEditor()`, `getCustomEditor()` | Returns a custom GUI component, if supported |
| Java initializer generation | `getJavaInitializationString()` | Provides a Java code expression representing the value |
 
This interface is broader than Spring MVC requires. Most editors used for input binding only need to handle `setAsText`, `getAsText`, and store the value via `setValue`/`getValue`.

Key contracts:

- `setAsText(String)` has a `void` return type. If the text is not in a valid format, the editor may throw `IllegalArgumentException`.
- `getAsText()` returns a `String` representing the current value; it may return `null` if the value cannot be represented as text. If it returns a non-null string, the editor should be able to parse that string back via `setAsText(...)`.
- `setValue(Object)` and `getValue()` operate on the value held by the editor, which is **not synonymous** with directly writing or reading a field of a target bean.
- `getTags()` is useful when there are only a few choices for a property, but it does not perform permission checks/validation on its own.
- `getJavaInitializationString()` is used for **Java code** generation tools, not for JSON serialization or SQL.
- `getCustomEditor()` refers to `java.awt.Component`. That is an optional capability in JavaBeans GUI systems; it is not an HTML/React/Thymeleaf component.

According to the JavaBeans API, a PropertyEditor should usually have a no-argument constructor so tools can instantiate it. In Spring applications, some specific editors also have constructors taking options and are explicitly created during registration.

## 4. What Does PropertyEditorSupport Help With?

`PropertyEditorSupport`:

```java
public class PropertyEditorSupport implements PropertyEditor {
    // JDK class that already implements the interface methods.
}
```

The snippet above is a conceptual outline, **not the full JDK source code**. The real class has two common constructors:

```java
new PropertyEditorSupport();
new PropertyEditorSupport(source);
```

It holds the value state, supports listeners, and provides default implementations for the other methods. This means when writing an editor for a domain type, you usually only need to **extend `PropertyEditorSupport` and override `setAsText` and `getAsText`**.

Structural example:

```java
public final class ProductCodeEditor extends PropertyEditorSupport {
    @Override
    public void setAsText(String text) throws IllegalArgumentException {
        ProductCode parsed = parseProductCode(text);
        setValue(parsed);
    }

    @Override
    public String getAsText() {
        ProductCode current = (ProductCode) getValue();
        return current == null ? "" : current.value();
    }
}
```

This is **sketch code**, not yet complete: the `parseProductCode` method and `ProductCode` class must be defined; the runnable version is in section 6.

`PropertyEditorSupport` **does not automatically know** how to parse every domain type. If you do not override `setAsText`, do not expect the base class to convert an arbitrary string into a `ProductCode`. The benefit of this class is not having to write value storage and listener mechanics yourself when the application only needs parse/print logic.

### An editor's setValue/getValue is not a Bean's setter/getter

`editor.setValue(productCode)` only changes the **editor's state**. It is not equivalent to `form.setProductCode(productCode)`. Spring `BeanWrapper`/`DataBinder` will use the converted value to assign to the target in a separate step.

```text
setAsText("ab-012")
        |
        v
ProductCodeEditor.setValue(new ProductCode("AB-012"))
        |
        v
ProductCodeEditor.getValue()
        |
        v
BeanWrapper invokes form.setProductCode(ProductCode)
```

Therefore, running the editor directly is a great way to unit test parsing rules, but **not sufficient** to prove the editor is properly registered with Spring's binder.

## 5. Parse and Print: Rules That Need Clear Design

A good text editor needs a concrete semantic contract:

| Concern | Question to answer |
| --- | --- |
| Whitespace | Is `" ab-012 "` accepted? |
| Letter case | Does `"ab-012"` become `"AB-012"`? |
| Empty input | Return `null` or report an error? |
| Invalid text | Which exception is thrown? |
| Output format | Preserve exact input or normalize to a canonical form? |
| Reversibility | Does `setAsText(getAsText())` preserve the semantic value? |
| Locale | Do the rules depend on region/language? |
| Sensitive data | Could values accidentally leak via exceptions/logs/UI? |

The `ProductCode` example in this article has the following rules:

- Code must match **two ASCII Latin letters**, a `-` hyphen, and **three ASCII digits**.
- `"ab-012"` and `" AB-012 "` are normalized to `"AB-012"`.
- `null` or whitespace-only strings represent **no value** (`null`); checking "required input" belongs to a validator if business rules require it.
- `"AB12"` and `"ABC-012"` are invalid and throw `IllegalArgumentException`.
- `getAsText()` returns the empty string `""` for `null`, and returns the canonical code for parsed values.
- Uppercase normalization uses `Locale.ROOT` to avoid depending on the server's locale.

**Not every editor should "turn invalid input into null".** If non-empty text violates syntax, it should be rejected explicitly so the system can report a conversion error. Silently turning `"???"` into `null` easily causes data loss and hides the real cause.

## 6. Complete Java 17+ Example: PropertyEditorSupport and Spring DataBinder

The example demonstrates three ways of using the same editor:

1. Calling the JavaBeans editor **directly** to see how `setAsText`/`getAsText`/`getValue` work.
2. Registering the editor on `BeanWrapper` to write a typed property from a `String`.
3. Registering the editor on `DataBinder` to see invalid input become a binding error in `BindingResult`.

Maven project structure:

```text
property-editor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── PropertyEditorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>property-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/PropertyEditorDemo.java`:

```java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class PropertyEditorDemo {

    // Internal data type; the form setter accepts ProductCode, not String.
    public record ProductCode(String value) {}

    public static final class ProductCodeEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) throws IllegalArgumentException {
            if (text == null || text.isBlank()) {
                setValue(null);
                return;
            }

            String canonical = text.trim().toUpperCase(Locale.ROOT);
            if (!canonical.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "ProductCode must match AA-999");
            }

            setValue(new ProductCode(canonical));
        }

        @Override
        public String getAsText() {
            ProductCode current = (ProductCode) getValue();
            return current == null ? "" : current.value();
        }
    }

    public static class PurchaseForm {
        private ProductCode productCode;
        private String customerName;

        public PurchaseForm() {}

        public ProductCode getProductCode() { return productCode; }
        public void setProductCode(ProductCode code) {
            this.productCode = code;
        }

        public String getCustomerName() { return customerName; }
        public void setCustomerName(String name) {
            this.customerName = name;
        }
    }

    private static void directEditorExample() {
        ProductCodeEditor editor = new ProductCodeEditor();
        editor.setAsText(" ab-012 ");

        ProductCode parsed = (ProductCode) editor.getValue();
        System.out.println("direct.value=" + parsed.value());
        System.out.println("direct.text=" + editor.getAsText());

        editor.setValue(new ProductCode("XY-777"));
        System.out.println("manual.text=" + editor.getAsText());
    }

    private static void beanWrapperExample() {
        PurchaseForm form = new PurchaseForm();

        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(form);
        wrapper.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());

        // For the customerName property only: trim whitespace when writing.
        wrapper.registerCustomEditor(
                String.class, "customerName",
                new StringTrimmerEditor(false));

        wrapper.setPropertyValue("productCode", "cd-345");
        wrapper.setPropertyValue("customerName", "  Linh  ");

        System.out.println("bean.code=" +
                form.getProductCode().value());
        System.out.println("bean.customer=" +
                form.getCustomerName());
    }

    private static void dataBinderExample() {
        PurchaseForm form = new PurchaseForm();
        DataBinder binder = new DataBinder(form, "purchaseForm");
        binder.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("productCode", "wrong");
        binder.bind(values);

        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("productCode");

        System.out.println("bind.errorCount=" + result.getErrorCount());
        System.out.println("bind.field=" +
                (error == null ? "<none>" : error.getField()));
        System.out.println("bind.code=" +
                (error == null ? "<none>" : error.getCode()));
        System.out.println("bind.bindingFailure=" +
                (error != null && error.isBindingFailure()));
    }

    public static void main(String[] args) {
        directEditorExample();
        beanWrapperExample();
        dataBinderExample();
    }
}
```

Run from the `property-editor-demo` directory, requiring JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=PropertyEditorDemo
```

Lines produced by `System.out.println` according to the example's logic:

```text
direct.value=AB-012
direct.text=AB-012
manual.text=XY-777
bean.code=CD-345
bean.customer=Linh
bind.errorCount=1
bind.field=productCode
bind.code=typeMismatch
bind.bindingFailure=true
```

**Explanation:**

1. `editor.setAsText(" ab-012 ")` runs the normalization logic and then calls `setValue(new ProductCode("AB-012"))`. `getValue()` returns `ProductCode`, while `getAsText()` returns the string.
2. `editor.setValue(new ProductCode("XY-777"))` directly replaces the typed value held by the editor; the next `getAsText()` call is based on the new value.
3. `BeanWrapper` receives a registration for `ProductCode.class`. When calling `setPropertyValue("productCode", "cd-345")`, the editor helps convert the type before assigning to `PurchaseForm`'s setter.
4. `StringTrimmerEditor(false)` is registered **only** for the `customerName` property; `"  Linh  "` becomes `"Linh"`. The `false` argument indicates that an empty string after trimming stays an empty string, not `null`.
5. The `DataBinder` case supplies the text `"wrong"`, which is invalid against pattern `AA-999`. The editor throws `IllegalArgumentException`; during normal binding flow, the binder collects the type conversion failure into a `FieldError` with general code `typeMismatch` and `isBindingFailure() == true`.
6. The `typeMismatch` error code can have multiple candidate detailed codes in `error.getCodes()`. The output only prints `getCode()`, avoiding dependence on message resolver variations.
7. The example **does not call `binder.validate()`**, so the error here belongs to binding, not constraint validation.

The program above is complete according to the stated file structure. If you change the editor, message resolver configuration, or use a different Spring version, re-run it to verify exact behavior and stdout.

## 7. Using an Editor Directly: State, Null, and Round-Trip

An editor can be created without Spring:

```java
ProductCodeEditor editor = new ProductCodeEditor();

editor.setAsText("ab-012");
ProductCode first = (ProductCode) editor.getValue();

editor.setValue(first);
String printed = editor.getAsText();
```

This snippet depends on the two classes defined in section 6, illustrating **both directions**: text -> object and object -> text. It is the best place to verify small rules before plugging into Spring.

### The round-trip rule

When an editor supports text, verify:

```text
parse(" ab-012 ") = ProductCode("AB-012")
print(ProductCode("AB-012")) = "AB-012"
parse(print(ProductCode("AB-012"))) = ProductCode("AB-012")
```

The last line compares by **semantic value**, without requiring the raw input text bytes to remain unchanged. Uppercase normalization is an intentional transformation; if the UI needs to preserve the original user input verbatim, a separate model must be designed.

### Null and empty input

In the example, `null`/blank passed to `setAsText` is represented as `null`. This does not mean the property is allowed to be omitted by business rules. If `productCode` is required, use an appropriate validator, such as `@NotNull` in Jakarta Bean Validation, after binding.

If the input has invalid characters or wrong length, the editor throws `IllegalArgumentException`. Do not simply `catch` and `setValue(null)` for every error; that approach can cause a malformed code to be mistaken for the user entering nothing.

### Note on setValue(Object)

`setValue` accepts `Object` per the interface contract. If a caller arbitrarily invokes:

```java
editor.setValue("raw string");
```

and the custom editor's `getAsText()` casts to `ProductCode`, a `ClassCastException` can occur. The code above is **something to avoid**, not a valid operation in the demo. JavaBeans editors must be invoked by callers with the right value type; a custom editor may override `setValue` to check the type early when design requires it. Spring typically selects the editor by property type, but code calling an editor directly still needs to obey the contract.

## 8. Registering Editors in Spring: Scope Must Be Exact

Spring implements the `org.springframework.beans.PropertyEditorRegistry` interface in components like `BeanWrapper` and `DataBinder`. There are two important registration forms:

```java
registry.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

registry.registerCustomEditor(
        String.class, "customerName",
        new StringTrimmerEditor(true));
```

This is an illustrative snippet with `registry` of type `PropertyEditorRegistry` and existing editors/types.

| Registration form | Scope | When to choose |
| --- | --- | --- |
| `registerCustomEditor(ProductCode.class, editor)` | Properties of type `ProductCode` in that registry/binder | Same rule across a domain type |
| `registerCustomEditor(String.class, "customerName", editor)` | Specific property path in that registry/binder | Trim/format only one field |
| `registerCustomEditor(null, "somePath", editor)` | Matched by property path | Use only when type resolution is well understood; specify type for collections |
| `PropertyEditorRegistrar` | One place registering multiple editors into a passed registry | Need to reuse configuration across multiple binders/beans |

Do not register an editor for all `String`s if only one field needs processing. A `StringTrimmerEditor(true)` registered globally can turn whitespace-only strings into `null` on every field within that scope; that may be the intended behavior for some forms, but surprising on other fields.

### Registration by nested property path

Spring supports paths such as `customer.address.zip`. For collections, `registerCustomEditor(requiredType, propertyPath, editor)` has specific property path matching logic; do not confuse registration syntax with specific element access syntax.

For example, the `PropertyEditorRegistry` documentation describes registering an editor for elements `items[n].quantity` using a path like `items.quantity`, using an appropriate type to clarify whether the editor applies to the element or the whole collection. When this scoping matters, test both index 0 and indices greater than 0 in a real project.

For collections/arrays, distinguish an editor meant for the **list/array itself** from an editor meant for **each element**. Specify the exact type and avoid registering overlapping editors on the same path that lead to confusing results.

## 9. Integration with BeanWrapper

`BeanWrapper` is the class operating at the JavaBean property level:

```java
PurchaseForm form = new PurchaseForm();

BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(form);
wrapper.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

wrapper.setPropertyValue("productCode", "ab-012");
ProductCode code =
        (ProductCode) wrapper.getPropertyValue("productCode");
```

This snippet uses the `PurchaseForm` and `ProductCodeEditor` classes from section 6. `getPropertyValue` returns the **typed value**, namely `ProductCode`, rather than calling `getAsText` by default to produce a string.

The nature of the two operations:

- **Setting a value from text:** `setPropertyValue` looks up the property type, uses the appropriate editor/conversion, and invokes the setter.
- **Reading an existing value:** `getPropertyValue` returns the property value; if you want text for the UI, use an appropriate editor or formatter in a separate step.

### BeanWrapper does not automatically validate all constraints

The editor only confirms that the input has a form convertible to `ProductCode`. Checking whether that code exists in the catalog, whether the user is permitted to buy it, or whether stock quantity is sufficient belongs to separate **validation/business logic**.

Thus, an editor may validly return `ProductCode("AB-012")` while the order is still invalid.

## 10. Integration with DataBinder and BindingResult

`DataBinder` operates on a target with a set of `PropertyValues`; it can turn conversion errors into error data in `BindingResult` instead of forcing the presentation layer to decode every exception itself.

```java
PurchaseForm form = new PurchaseForm();
DataBinder binder = new DataBinder(form, "purchaseForm");

binder.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

MutablePropertyValues input = new MutablePropertyValues();
input.add("productCode", "bad");

binder.bind(input);

BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("productCode")) {
    // Retrieve the FieldError, typeMismatch code, and inform the user to fix the syntax.
}
```

This snippet also depends on classes from section 6. It **does not require** calling `binder.validate()` to obtain type conversion errors; validation is a separate phase if you configure a validator.

Distinction:

| Scenario | Mechanism | Symptom |
| --- | --- | --- |
| `"ab-012"` parses | Editor creates `ProductCode` | Setter receives object |
| `"wrong"` fails to parse | Editor throws `IllegalArgumentException`; binder catches standard binding error | `FieldError`/`typeMismatch` |
| `""` converted by editor to `null` | Conversion result for "no value" | Not necessarily `hasErrors()` |
| `null` violates `@NotNull` | Validator/Bean Validation after binding | Constraint error when validation runs |
| `ProductCode("AB-012")` does not exist in DB | Business rule | Separate service/validator error |
| Client sends field name outside allowlist | Binding policy | May appear in `getSuppressedFields()`, not automatically a `FieldError` |

**Note:** on the `BeanWrapper.setPropertyValue(...)` API directly, conversion errors usually surface as property access/type conversion exceptions; `BindingResult` belongs to `DataBinder`, not the return value of `PropertyEditor.setAsText`.

If the data contains secrets, do not log `FieldError.getRejectedValue()` directly. It may hold raw input from the client.

## 11. Using in Spring MVC via @InitBinder

In Spring MVC handling `@ModelAttribute`, a **new** editor can be created **for each binder**:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("purchaseForm")
void initPurchaseBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            ProductCode.class, new ProductCodeEditor());

    binder.registerCustomEditor(
            String.class, "customerName",
            new StringTrimmerEditor(true));
}
```

This is **a method inside a suitably scoped controller or controller advice**, not a complete Spring MVC class. You must import `ProductCode`, `ProductCodeEditor`, and `StringTrimmerEditor` from application code.

An illustrative controller:

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class PurchaseController {

    @InitBinder("purchaseForm")
    void initBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());
    }

    @PostMapping("/purchases")
    String submit(
            @ModelAttribute("purchaseForm") PurchaseForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "purchase-form";
        }

        // Process business logic after the input has been thoroughly validated.
        return "purchase-success";
    }
}
```

This is an **illustrative integration snippet**, requiring full imports for `WebDataBinder`/`InitBinder`, domain classes, Spring MVC, view resolver, and application logic. It is not a standalone file; the view names are only examples.

**Important note:** `BindingResult` should appear immediately after the corresponding `@ModelAttribute` parameter. `@InitBinder` creates a registration for a specific binder flow; a custom editor does not automatically apply to all other controllers.

### @RequestBody JSON does not use the same default path

For controllers receiving JSON with `@RequestBody`, an HTTP message converter (usually Jackson) reads JSON and creates objects. Form binding's `@InitBinder`/`PropertyEditor` **does not automatically replace JSON serializers/deserializers**.

If a JSON API needs `ProductCode` from a string, design dedicated JSON mapping (such as a Jackson deserializer or suitable constructor/creator). Do not expect merely registering an editor to change the JSON response format via `@ResponseBody`.

## 12. PropertyEditorRegistrar: Packaging Configuration, Creating Fresh Editors

When multiple binders need the same set of editors, the `org.springframework.beans.PropertyEditorRegistrar` interface allows centralizing the registration work:

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class PurchaseEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());
        registry.registerCustomEditor(
                String.class, "customerName",
                new StringTrimmerEditor(true));
    }
}
```

This is a shared class; project classes/types must be imported. Using the registrar with `BeanWrapper`:

```java
PurchaseEditorRegistrar registrar = new PurchaseEditorRegistrar();

BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(new PurchaseForm());

registrar.registerCustomEditors(wrapper);
```

Using the registrar with `DataBinder`:

```java
DataBinder binder =
        new DataBinder(new PurchaseForm(), "purchaseForm");

registrar.registerCustomEditors(binder);
```

**Why is a registrar important?** `PropertyEditorSupport` holds the value being edited; one editor may be used sequentially for multiple properties and its state mutates each time. When a registrar is invoked for a registry, **create a new editor instance inside** as shown in the code; do not create a `static final ProductCodeEditor` and share it across binders/requests.

A registrar itself can be a singleton if it holds no mutable editor state. Each time `registerCustomEditors` is called, it still creates fresh editors for the new registry.

### CustomEditorConfigurer in Spring IoC

If the problem is **converting properties when the Spring container creates beans**, rather than HTTP forms, Spring provides `CustomEditorConfigurer` to configure editors/registrars for an `ApplicationContext` or `BeanFactory`.

Illustrative XML configuration example:

```xml
<bean id="purchaseEditorRegistrar"
      class="example.PurchaseEditorRegistrar"/>

<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="propertyEditorRegistrars">
        <list>
            <ref bean="purchaseEditorRegistrar"/>
        </list>
    </property>
</bean>
```

This is a **Spring XML snippet**, requiring namespaces/root document and actual class paths. Two scopes must be distinguished:

- **Container bean property conversion:** when instantiating/configuring beans in the IoC container.
- **Web MVC form binding:** when binding requests into a model attribute.

Registering an editor via `CustomEditorConfigurer` for a bean factory **does not guarantee** an MVC controller will use that editor. If the need is in forms, register it on the appropriate `WebDataBinder` or use appropriate MVC configuration.

## 13. Lifecycle, State, and Thread Safety

Unlike a pure-function converter, `PropertyEditorSupport` has **mutable state**: `setValue` changes the value held by the editor; `getValue` reads that state. If a single editor instance is used concurrently for different requests, there is a risk:

```text
Request A: editor.setAsText("AB-001")
Request B: editor.setAsText("CD-002")
Request A: editor.getValue()  -> may see "CD-002"
```

This is an illustration of a race condition, not a standalone Java program. Therefore:

1. Do not make a mutable `ProductCodeEditor` a singleton shared across multiple requests.
2. With `@InitBinder`, create `new ProductCodeEditor()` for the request's binder.
3. With `PropertyEditorRegistrar`, create a new editor instance on each registration call.
4. If shared parsing logic is needed, put it in a **stateless** utility/service; new editors can call that utility.
5. Do not store references to an editor's state in another component without clear lifecycle management.
6. Concurrency tests should focus on data/domain immutability and ensuring each binder gets its own editor.

Spring documentation emphasizes that registrars create new editors for each bean creation/binding pass to avoid synchronizing shared editors. Allocating small objects is usually cheaper than hard-to-reproduce race condition bugs.

### PropertyChangeListener and events

`PropertyEditor` has an `addPropertyChangeListener` mechanism; `PropertyEditorSupport` provides listener storage and `firePropertyChange()`. This capability supports tools observing value changes, especially in the JavaBeans GUI world.

```java
import java.beans.PropertyChangeListener;

ProductCodeEditor editor = new ProductCodeEditor();
PropertyChangeListener listener = event -> {
    // A value being edited by the editor has changed.
};
editor.addPropertyChangeListener(listener);
editor.setAsText("ab-012");
editor.removePropertyChangeListener(listener);
```

This is an illustrative snippet using the editor from section 6. Do not implement HTTP request APIs by attaching long-lived listeners to a singleton editor. An editor's property change event is **different from** Spring application events, entity/domain events, and transaction events.

The `PropertyEditorSupport(Object source)` constructor specifies the source of the event; this source object is not a target that the editor is allowed to mutate arbitrarily. `getSource()` helps identify the event source, rather than replacing how `DataBinder` assigns properties.

## 14. GUI Methods Rarely Used on the Web

Because of its JavaBeans heritage, `PropertyEditor` has several methods related to GUI property editing tools:

| Method | When it is useful | Should not be mistaken for |
| --- | --- | --- |
| `getTags()` | A selectable set of values, like finite text choices | Spring MVC HTML select auto-generating it |
| `isPaintable()/paintValue(...)` | JavaBeans GUI tools wanting to draw the value | Frontend HTML/canvas rendering |
| `supportsCustomEditor()/getCustomEditor()` | Desktop tools wanting a custom AWT component | React/Thymeleaf component |
| `getJavaInitializationString()` | Code-generation tools producing Java code to recreate the value | JSON string, SQL, or user-entered text |

An editor used for Spring server-side binding can omit these GUI capabilities. There is no need to override all of them just to parse a `String`. When building an HTML dropdown, declare options in the appropriate view/model layer and validate the value on the server; `getTags()` does not replace authorization or validation.

### Simple getTags example

```java
@Override
public String[] getTags() {
    return new String[] {"NEW", "ACTIVE", "DISABLED"};
}
```

This is a **method that could be placed in a custom editor for a status**, not part of `ProductCodeEditor` in section 6. If using a tag list, `setAsText` should accept the corresponding tags, and `getAsText` should represent the current state as one of those tags.

## 15. Some Built-in Spring PropertyEditors

Spring includes implementations in package `org.springframework.beans.propertyeditors`. Notable examples:

| Editor | Purpose | Notes |
| --- | --- | --- |
| `StringTrimmerEditor` | Trims strings; optionally turns empty into `null` | Usually must be **registered manually** |
| `CustomDateEditor` | Converts strings with `java.text.DateFormat` to `Date` | Use proper format/leniency; manage instances as non-thread-safe |
| `CustomNumberEditor` | Converts strings to the appropriate `Number` type | Controls empty numbers, numeric type, and formatting |
| `ClassEditor` | Converts a class name to `Class` | Belongs to configuration-support editors |
| `URLEditor` | Converts a string to `URL` | Does not verify the URL is safe for network connections |
| `ByteArrayPropertyEditor` | Converts a string to a byte array per editor rules | Does not arbitrarily decode every encoding by default |

**Not every editor is registered by default for every binder/container**. For instance, Spring documentation notes that `StringTrimmerEditor` is not registered by default; it must be configured explicitly.

In particular, `CustomDateEditor` commonly uses a `DateFormat` with mutable state. If multiple threads share one `SimpleDateFormat` instance, results can be unstable. For new code using `java.time`, consider `Formatter`/`ConversionService` and modern date types instead of legacy editors unless compatibility requires them.

### String trimming example in MVC

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
```

This is an MVC method, requiring imports for `WebDataBinder`, `InitBinder`, and `StringTrimmerEditor`. When registered for **the entire `String` type** in this binder, every `String` property the editor applies to may be trimmed, and empty text becomes `null`. Before applying it form-wide, make sure every field's contract accepts that transformation.

## 16. PropertyEditor vs. Converter and Formatter

Modern Spring has two related abstractions:

- `Converter<S,T>` in `org.springframework.core.convert.converter`: converts types in a defined direction, e.g., `String -> ProductCode`, holds no state like `PropertyEditorSupport`, and does not receive `Locale` via the convert method.
- `Formatter<T>` in `org.springframework.format`: implements `Parser<T>` and `Printer<T>`, supporting `Locale` for text input/display.
- `ConversionService`/`FormattingConversionService`: infrastructure for registering and executing converters/formatters; integrates with binders/frameworks when properly configured.

Comparison:

| Aspect | PropertyEditor / PropertyEditorSupport | Converter | Formatter |
| --- | --- | --- | --- |
| Origin | JavaBeans in JDK | Spring Core | Spring Format |
| Typical direction | Text <-> Object via state | Type S -> T | Text <-> T |
| Receives Locale directly? | `setAsText` does not receive Locale | `convert` does not receive Locale | `parse/print` has Locale |
| Mutable state | Yes in `PropertyEditorSupport` | Usually stateless | Usually stateless |
| Configuration | `registerCustomEditor` | `ConverterRegistry` | `FormatterRegistry` |
| Strengths | Legacy JavaBeans/IoC and existing binders | General-purpose type conversion | Dates, numbers, UI i18n |
| Caveats | Do not share editor instances; lifecycle | Conversion does not imply validation | Locale/pattern must be consistent |

**When to choose an editor?**

- The project already has a JavaBeans `PropertyEditor`/Spring `DataBinder` setup.
- You need registration specific to one property path with editor semantics.
- Compatibility with legacy frameworks or proven custom editors.

**When to choose converter/formatter for new code?**

- You need type conversion shared across many places without editor state.
- You need locale-aware formatting, such as monetary amounts and dates, via `Formatter`.
- You want centralized application via `ConversionService`/`FormattingConversionService`.

There is no reason to **mass-rewrite working editors** merely because newer APIs exist. However, when designing new modules, stateless options are usually easier to test, reason about concurrency, and share.

### Turning an editor into a converter: comparison example

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        String code = source.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "ProductCode must match AA-999");
        }
        return new ProductCode(code);
    }
}
```

This is an illustrative class; `ProductCode` must be imported in the project. It performs **one-way** conversion `String -> ProductCode`. If the application also needs `ProductCode -> String`, you can register a reverse converter or use `Formatter<ProductCode>` for the UI. A single editor inherently expresses both directions via `setAsText/getAsText`.

## 17. Validation and Security: Editors Do Not Decide Everything

Even when the editor parses `"AB-012"` into `ProductCode`, business questions remain:

- Does this code exist in the catalog?
- Does the code belong to a tenant/account the user is allowed to operate on?
- Is the user permitted to assign the `productCode` field?
- Are there quota/rate/input-size limits?
- Could error messages leak sensitive data?

Those checks belong to validation, authorization, request limits, and service/domain layers. Do not put expensive database queries or data-writing behavior into `setAsText` by default: editors may be invoked in unexpected binding/conversion situations, causing hard-to-control side effects.

### Preventing mass assignment

A request may contain property names outside the contract. Even with a valid editor for a type, whether the user is allowed to edit that field must be decided separately. With Spring `DataBinder`:

```java
DataBinder binder = new DataBinder(form, "purchaseForm");

binder.setAllowedFields("productCode", "customerName");
binder.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());
```

This snippet belongs in code with a `form` variable of type `PurchaseForm`. `setAllowedFields` restricts which properties are allowed to bind in the property-binding branch; the editor only handles conversion when the field is allowed.

If the request carries excluded fields, inspect `binder.getBindingResult().getSuppressedFields()`. Suppressed fields are **not necessarily** counted in `hasErrors()`, so if an API requires a strict input schema, check them separately.

### Input limits

A string-parsing editor does not control parameter counts, property path depth, or HTTP body size. Those constraints must be enforced at the corresponding HTTP/binding layer. If only code `AA-999` is needed, fixed regex logic as in the example is both clear and avoids overly complex data processing; request size limits should still be enforced upstream.

### Errors should not echo raw exceptions verbatim

In the example, the exception has the technical message `ProductCode must match AA-999`. In a real UI, map the `typeMismatch` error code along with the field context to a user-friendly message such as "Product code must be in the form AB-123", via `MessageSource` or the application's error response mechanism.

In particular, do not return stack traces or full sensitive rejected values to clients.

## 18. Testing Editors in Isolation and Through Binders

Tests should be split into two levels:

### Level 1: unit tests of the editor

For `ProductCodeEditor`, verify:

| Input/action | Expectation |
| --- | --- |
| `setAsText("ab-012")` | `getValue()` is `ProductCode("AB-012")` |
| `setAsText(" AB-012 ")` | Value equivalent to `"AB-012"` |
| `setAsText("")` | `getValue() == null` |
| `setAsText("   ")` | `getValue() == null` |
| `setAsText("ABC-012")` | `IllegalArgumentException` |
| `setAsText("AB12")` | `IllegalArgumentException` |
| `setValue(new ProductCode("XY-777"))` | `getAsText()` is `"XY-777"` |
| `setAsText(getAsText())` on a valid value | Preserves semantic value |

With JUnit Jupiter:

```java
ProductCodeEditor editor = new ProductCodeEditor();

editor.setAsText("ab-012");
org.junit.jupiter.api.Assertions.assertEquals(
        new ProductCode("AB-012"), editor.getValue());

org.junit.jupiter.api.Assertions.assertEquals(
        "AB-012", editor.getAsText());

org.junit.jupiter.api.Assertions.assertThrows(
        IllegalArgumentException.class,
        () -> editor.setAsText("invalid"));
```

This is a **JUnit snippet**, requiring the JUnit Jupiter dependency and the classes from section 6. It is not yet a complete test class.

### Level 2: integration tests with BeanWrapper/DataBinder

Verify:

1. Is `registerCustomEditor(...)` called for the right type `ProductCode`?
2. With `BeanWrapper.setPropertyValue("productCode", "ab-012")`, does the target receive an object of the right type?
3. With `DataBinder.bind(...)` and invalid input, does `BindingResult` have the expected field/error code?
4. If an editor applies only to the `customerName` field, are other String fields unaffected?
5. If a validator runs after binding, are parse errors and business errors distinguished?
6. If binders are created for multiple requests, are editor instances unexpectedly shared?
7. With `null`/empty input, does `@NotNull` validation run as intended?
8. With input outside `allowedFields`, are `getSuppressedFields()` handled?

A passing direct parse test **does not prove** Spring has registered the editor. Conversely, testing only binder error counts does not confirm canonicalization regex works in all cases. Both are needed.

### Testing i18n when using formatting

The editor in the example uses `Locale.ROOT` so output is consistent across dev machines and CI. For locale-dependent numbers/dates, do not implicitly rely on `Locale.getDefault()` in code and depend on one machine's output. Choose an explicit contract; if per-request formatting is needed, `Formatter<T>` accepting `Locale` directly is usually more suitable.

## 19. Common Errors and Troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| `setAsText("AB-012")` does not change value | Forgot `setValue(...)` in override | Call `setValue(parsed)` after parsing |
| `getAsText()` returns strange data | Did not override or wrong type cast | Explicitly override printing from `getValue()` |
| Editor works directly but not on submit | Not registered on the right `WebDataBinder` | Use `@InitBinder` for the right model |
| BeanWrapper still throws `TypeMismatchException` | Registered type/path mismatch | Check `registerCustomEditor` and property type |
| Form has `typeMismatch` error | Text could not be parsed | Check parser, message, and safe rejected value handling |
| Empty input reports no error | Editor turns empty into `null` without validator | Use `@NotNull` or a validator when required |
| Same editor mixes values across requests | Shared mutable singleton editor | Create a new editor per registry/binder |
| Trimming one field alters other fields | Editor registered for all `String.class` | Register by property path if needed |
| Editor does not apply to `@RequestBody` | JSON uses message converters | Configure dedicated JSON mapping |
| Error swallowed, target becomes `null` | Parser treats any bad input as empty | Only return null for explicitly defined empty states |
| Wrong locale displayed | PropertyEditor has no locale parameter | Consider `Formatter` and context locale |
| Business logic pushed into editor | Editor does too much beyond conversion | Keep editor pure conversion, validate separately |
| CustomEditorConfigurer has no effect on MVC | Registered in bean factory, not MVC binder | Configure in the right place of usage |
| API logs raw BindingResult | May expose `rejectedValue` | Log only filtered field/code |

### Quick debugging checklist

1. Identify the exact flow: Spring IoC bean creation, `BeanWrapper`, `@ModelAttribute`, or `@RequestBody`.
2. Check the **actual property type** and path; for example, does the setter accept `ProductCode` or `String`?
3. Run `editor.setAsText(text)` directly with the failing input; inspect `getValue()`.
4. Check `registerCustomEditor`: is registration happening on the right registry?
5. Verify a fresh editor is created for each binder/registry.
6. Inspect `BindingResult.getFieldError("productCode")` and `getCodes()`.
7. Distinguish `hasErrors()` from `getSuppressedFields()`.
8. Evaluate business rules such as code existence only after conversion.
9. Verify the UI resolves messages through an appropriate resolver instead of printing raw exceptions.

## 20. Self-Check Questions

**1. Are `PropertyEditor` and `PropertyEditorSupport` Spring classes?**  
No. They belong to the JDK's `java.beans` package. Spring integrates them to convert property values during IoC/binding.

**2. What type does `setAsText(String)` return?**  
`void`. It must update the editor's state (typically with `setValue(...)`); the caller reads back the object via `getValue()`.

**3. Why does `PropertyEditorSupport` make writing editors shorter?**  
It already provides value storage, listener management, and default interface implementations. Typically you only need to override the needed parse/print logic.

**4. When calling `editor.setValue(new ProductCode(...))`, is the target JavaBean automatically updated?**  
No. That call only updates the editor's state; `BeanWrapper`/`DataBinder` is the component that pushes the value into the target's setter.

**5. An `@InitBinder` is declared, yet the controller receives `@RequestBody` JSON; will the editor necessarily run?**  
No. JSON is usually processed through an HTTP message converter, requiring separate deserialization configuration if needed.

**6. Why should you not use a singleton `PropertyEditorSupport` across all requests?**  
Because the editor holds mutable state. Sharing it can cause race conditions and cross-request value contamination. Create new instances per registry/binder.

**7. How do `StringTrimmerEditor(true)` and `StringTrimmerEditor(false)` differ?**  
After trimming, `true` turns an empty string into `null`; `false` keeps the empty string. Both should be registered at the appropriate scope.

**8. Does `getAsText()` guarantee JSON responses will use the same format?**  
No. It is part of the JavaBeans editor and does not alter JSON serializers on its own.

**9. If an editor parses a code, does that mean the code is valid for placing an order?**  
No. Parsing validates syntax/representation; usage permissions, catalog existence, and business conditions must be checked separately.

**10. One field of type `String` needs individual trimming; how should it be registered?**  
Use the overload with `propertyPath`, such as `registerCustomEditor(String.class, "customerName", new StringTrimmerEditor(true))`, avoiding broad application if undesired.

**11. When should `Formatter<T>` be preferred over `PropertyEditorSupport`?**  
When parsing/printing by `Locale` and integrating Spring's formatting mechanism for UI are needed. Editors remain appropriate when JavaBeans compatibility or a specific binder requires them.

**12. Is `getJavaInitializationString()` a result meant for storing in a database?**  
No. It serves code-generation tools that produce a Java code expression capable of initializing the current value.

## Summary

- `PropertyEditor`: **JDK JavaBeans contract** for typed values and text representation/editing.
- `PropertyEditorSupport`: **stateful utility class**, convenient when writing custom editors.
- `setAsText -> setValue -> getValue`: **parse text into an object**.
- `setValue -> getAsText`: **represent an object as text**.
- `BeanWrapper` and `DataBinder`: **bind editors to properties**; `DataBinder` can collect binding errors in `BindingResult`.
- `registerCustomEditor`: specifies **type** and optionally **property path**; configuration must sit in the proper usage scope.
- `PropertyEditorRegistrar`: groups registrations and **creates new editor instances**, avoiding shared mutable state.
- `Converter`/`Formatter`: modern Spring APIs that can be simpler and better suited for new code, especially with i18n.
- Conversion does not replace **validation**, **authorization**, **input limits**, or **JSON deserialization**.

## Official References

- [Oracle Java 17 — java.beans.PropertyEditor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html)
- [Oracle Java 17 — java.beans.PropertyEditorSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html)
- [Oracle Java 17 — JavaBeans package summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/package-summary.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Framework 6.2 — PropertyEditorRegistry API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework 6.2 — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — PropertyEditorRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework 6.2 — Spring Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
