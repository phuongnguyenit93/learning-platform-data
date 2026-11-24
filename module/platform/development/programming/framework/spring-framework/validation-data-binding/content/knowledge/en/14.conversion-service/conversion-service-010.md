# ConverterNotFoundException, ConversionFailedException, and TypeMismatchException in Spring

When Spring converts a value from a source type to a target type, errors can occur at several distinct stages. Three common exceptions are:

- **`ConverterNotFoundException`**: `ConversionService` could not find a matching converter for the source type → target type pair.
- **`ConversionFailedException`**: Spring found and invoked a conversion path, yet the actual conversion **failed at runtime**.
- **`TypeMismatchException`**: assigning a **value to a bean property** failed due to a type mismatch. This is a property-access layer exception; in some cases it wraps an underlying conversion error.

Important point: these three names **do not belong to the same inheritance branch**. The first two exceptions belong to the `org.springframework.core.convert` package; the third belongs to `org.springframework.beans` and is a subclass of `PropertyAccessException`. In binding flows, conversion-layer errors may be wrapped or translated into property-access/field errors for the application to handle.

This guide shows how to distinguish the root cause accurately, read the exception chain, reproduce the errors using Java 17+ and `ConversionService`/`BeanWrapper`/`DataBinder`, and choose the appropriate fix.

## 1. Where the Three Exceptions Sit in Spring's Architecture

They can be classified as follows:

~~~text
org.springframework.core.convert
          |
          v
   ConversionException
       /          \
      v            v
ConverterNotFoundException   ConversionFailedException


org.springframework.beans
          |
          v
      BeansException
          |
          v
  PropertyAccessException
          |
          v
   TypeMismatchException
          |
          v
 ConversionNotSupportedException (a specific subclass)
~~~

This is an abridged diagram showing the relevant relationships:

| Exception | Package | Direct superclass | Primary meaning |
| --- | --- | --- | --- |
| `ConverterNotFoundException` | `org.springframework.core.convert` | `ConversionException` | No matching converter exists to fulfill the request |
| `ConversionFailedException` | `org.springframework.core.convert` | `ConversionException` | A conversion path exists, yet the converter/conversion failed |
| `TypeMismatchException` | `org.springframework.beans` | `PropertyAccessException` | Unable to assign a value of the type required by the bean property |

**Do not assume `TypeMismatchException` extends `ConversionException`.** The two hierarchies are separate. During a bean property assignment, Spring may translate a conversion error into a property-access error, which is an **error-handling wrapping/forwarding** relationship rather than class inheritance.

An important subclass is `ConversionNotSupportedException`: it extends `TypeMismatchException` and describes the situation where no suitable editor/converter exists for a bean property. Meanwhile, `ConverterNotFoundException` is a `ConversionService` error during converter lookup. The two names sound similar, yet belong to different packages and processing layers.

## 2. ConverterNotFoundException — No Conversion Path Found

### 2.1. When Does It Occur?

`ConverterNotFoundException` is thrown when `ConversionService` is asked to convert a type pair, yet finds no matching converter to handle it:

~~~java
conversionService.convert(source, TargetType.class);
~~~

For example, given a domain type:

~~~java
public record CustomerReference(String value) {
}
~~~

If the application asks to convert `String` to `CustomerReference` yet the current `ConversionService` has no corresponding converter, editor, or convention conversion, Spring does not know how to construct the target object.

This example assumes `CustomerReference` lacks a matching constructor/factory that the default conversion mechanism can use automatically. If the type had `valueOf(String)`, `of(String)`, or a constructor taking `String`, a default/convention converter might handle it and the exception would not occur.

### 2.2. Reading Exception Details

`ConverterNotFoundException` provides:

- `getSourceType()`: `TypeDescriptor` of the requested source type.
- `getTargetType()`: `TypeDescriptor` of the target type.
- `getMessage()`: diagnostic error description.

These details reveal **which type pair lacks a conversion path**, making registry inspection faster than reading just a single stack trace line.

For instance, the message may indicate "No converter found capable of converting from type [java.lang.String] to type [CustomerReference]". Exact wording can change across versions; avoid asserting exact message strings in tests without good reason.

### 2.3. How to Fix It

**Adding an appropriate Converter** is the standard solution:

~~~java
public final class StringToCustomerReferenceConverter
        implements Converter<String, CustomerReference> {

    @Override
    public CustomerReference convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Reference is required");
        }
        return new CustomerReference(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This is an **illustrative class snippet** requiring imports for `org.springframework.core.convert.converter.Converter`, `java.util.Locale`, and the domain record. A converter only receives non-null values under the `ConversionService` contract; the `source == null` check in the example is defensive redundancy, while the empty-value policy is a business choice.

Then register it in the registry:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCustomerReferenceConverter());

CustomerReference reference =
        service.convert(" ab-123 ", CustomerReference.class);
~~~

The snippet above is illustrative code requiring the Spring imports and declared converter. `DefaultConversionService` preserves standard converters while allowing custom converters to be added.

**Verify exact source/target types:** sometimes an application has registered a converter, yet the type signatures do not match—for example, only `Converter<String, Long>` exists while the data needs `String -> CustomerReference`. Likewise, a converter for `List<String>` does not automatically handle every `String -> List<CustomerReference>` case if generic element/type descriptors are not properly described.

Checklist:

1. What are the actual source/target types? Read `getSourceType()` and `getTargetType()`.
2. Was the converter added to the exact `ConversionService` being used?
3. Was the converter configured in the right Spring `ApplicationContext` or binder?
4. Do the generic signature/`TypeDescriptor` accurately describe collection, map, annotation, and nested types?
5. Is another conversion path missing in the middle of a multi-step conversion?

## 3. ConversionFailedException — Converter Exists Yet Conversion Fails

### 3.1. How It Differs from ConverterNotFoundException

When Spring finds a converter, yet during conversion encounters an invalid value or a failure inside converter logic, `ConversionFailedException` may be thrown.

Example:

~~~java
Integer quantity = conversionService.convert("abc", Integer.class);
~~~

A default `ConversionService` can convert `String` to `Integer`. Therefore this is **not** a missing-converter error. The error occurs when the number converter tries to parse `"abc"` and fails (typically with `NumberFormatException` in the cause chain).

Another example is a custom converter throwing `IllegalArgumentException` when a code violates a formatting rule.

### 3.2. Readable Details

`ConversionFailedException` extends `ConversionException` and exposes:

- `getSourceType()`: source type.
- `getTargetType()`: target type.
- `getValue()`: the input value that caused the failure.
- `getCause()`: the root cause or exception thrown by the converter.

When debugging, inspect **source type, target type, value, and cause**. Values in logs should be considered for masking if they could contain personal data, tokens, passwords, or sensitive information.

### 3.3. Common Scenarios

| Source value | Target type | Likely failure reason |
| --- | --- | --- |
| `"abc"` | `Integer` | Not a valid integer representation |
| `"2026-19-45"` | `LocalDate` | Invalid day/month components |
| `"maybe"` | `Boolean` | Does not match active boolean parsing rules |
| `"AB-12"` | `CustomerReference` | Custom converter requires `AA-999` format |
| Collection with bad element | `List<Integer>` | One element could not convert to target type |

Not every bad value surfaces as the exact same exception class across every API. Direct `ConversionService` calls usually throw `ConversionFailedException` when conversion execution fails; bean binding may wrap the error in another exception or record it in `BindingResult`.

### 3.4. How to Fix It

- **Fix the source data:** check input, formatting, value range, and locale.
- **Fix the converter:** handle parsing rules, basic representation validation, and meaningful exceptions.
- **Add error messages:** preserve type-mismatch details so the UI indicates which field is invalid.
- **Do not swallow errors:** never silently return a default value if data loss corrupts business logic.
- **Distinguish conversion from validation:** the string `"15"` can convert to integer 15 successfully while still failing business rule `quantity >= 20`.

A `Converter` should normally throw `IllegalArgumentException` to report invalid source input; `ConversionService` wraps the conversion failure in `ConversionFailedException` and preserves the cause. Converters should not perform database queries or complex permission checks; those belong in services/validators.

## 4. TypeMismatchException — Error Assigning a Value to a Bean Property

### 4.1. Difference from Standalone ConversionService Errors

`TypeMismatchException` belongs to `org.springframework.beans` and extends `PropertyAccessException`. It is used when assigning a value to a bean property fails because it does not match the type the property requires.

JavaBean example:

~~~java
public class ProductForm {
    private int quantity;

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

When using `BeanWrapper`:

~~~java
ProductForm form = new ProductForm();
BeanWrapper wrapper = new BeanWrapperImpl(form);

wrapper.setPropertyValue("quantity", "ten");
~~~

`quantity` requires `int`, while `"ten"` cannot be converted into an integer. During property access, the failure may be surfaced as `TypeMismatchException` or an appropriate subclass.

Key distinction: here the application is not merely asking `ConversionService` "please convert String to Integer." The application is **performing a bean property assignment**, so Spring reports the error in the context of property access.

### 4.2. Useful Getters

`TypeMismatchException` and its superclass `PropertyAccessException` provide data to identify:

- The value that could not be assigned.
- The required type.
- The related property/event (depending on the constructor/exception origin).
- The cause chain if conversion or the setter threw an error.

In a specific exception instance, available getter APIs depend on the subclass and overload used. Do not assume every subclass populates the exact same set of metadata.

### 4.3. ConversionNotSupportedException Is Another Subclass

An important class to recognize:

`org.springframework.beans.ConversionNotSupportedException` **extends `TypeMismatchException`** and describes the case where no suitable editor/converter exists for a bean property. It differs from `org.springframework.core.convert.ConverterNotFoundException`:

| Exception class | Layer | Meaning |
| --- | --- | --- |
| `ConverterNotFoundException` | `ConversionService` | No converter found for type pair |
| `ConversionNotSupportedException` | Bean property access | No suitable editor/converter when assigning bean property |
| `ConversionFailedException` | `ConversionService` | Conversion ran but failed |
| `TypeMismatchException` | Bean property access | Value does not match property type; can be superclass of specialized errors |

Therefore, when a log merely says "conversion not supported", check the **full package name** and exception chain rather than relying only on the partial class name.

## 5. Quick Comparison via Diagnostic Questions

| Question | Likely exception |
| --- | --- |
| Spring does not know how to convert source type to target type? | `ConverterNotFoundException` |
| Spring knows how to convert, yet a specific value makes the converter fail? | `ConversionFailedException` |
| Spring is assigning a value to a bean property and the type does not fit? | `TypeMismatchException` or subclass |
| Bean property has no suitable editor/converter? | Possibly `ConversionNotSupportedException` |

The deciding question is: **at which step did the failure happen?**

~~~text
Source value + target type
           |
           v
Find conversion path?
   | No                  | Yes
   v                     v
ConverterNotFound     Execute conversion
                          |
                     success?
                     |      |
                    No     Yes
                     |      |
                     v      v
             ConversionFailed  converted value
                                   |
                                   v
                         assign bean property
                                   |
                              type/access OK?
                                |      |
                               No     Yes
                                |      |
                                v      v
                        TypeMismatch  property updated
~~~

This is a conceptual diagram. In actual Spring code, binders/accessors may use `PropertyEditor`, `ConversionService`, type descriptors, and adapters. The diagram clarifies responsibilities rather than documenting every internal overload.

## 6. Java 17+ Example: Reproducing All Three Error Types

The following example runs with Java 17+ and Spring Framework. It uses:

1. `DefaultConversionService` to reproduce a missing converter.
2. `DefaultConversionService` to reproduce an existing converter failing to parse.
3. `BeanWrapperImpl` to assign a malformed string to an `int` property.
4. `DataBinder` to inspect errors recorded in `BindingResult`.

### 6.1. Maven Dependency

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-conversion-exceptions-demo</artifactId>
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

`spring-context` brings in the required Spring modules such as `spring-beans` and `spring-core`. In Spring Boot applications, use Boot's parent/BOM to manage Spring module versions together. Version `6.2.19` is pinned for a reproducible example, not as an instruction to upgrade a single module independently inside Boot.

### 6.2. Complete Source Code

Save at `src/main/java/example/ConversionExceptionDemo.java`:

~~~java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.TypeMismatchException;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

public class ConversionExceptionDemo {

    // Target type has no String constructor or valueOf/of/from.
    public record CustomerReference(String value) {
    }

    public static class ProductForm {
        private int quantity;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    private static void converterNotFound(
            DefaultConversionService service) {
        try {
            service.convert("ABC-123", CustomerReference.class);
        } catch (ConverterNotFoundException ex) {
            System.out.println(
                    "missing=" + ex.getClass().getSimpleName());
            System.out.println(
                    "missing.source=" + ex.getSourceType().getType().getSimpleName());
            System.out.println(
                    "missing.target=" + ex.getTargetType().getType().getSimpleName());
        }
    }

    private static void conversionFailed(
            DefaultConversionService service) {
        try {
            service.convert("not-a-number", Integer.class);
        } catch (ConversionFailedException ex) {
            System.out.println(
                    "failed=" + ex.getClass().getSimpleName());
            System.out.println(
                    "failed.source=" + ex.getSourceType().getType().getSimpleName());
            System.out.println(
                    "failed.target=" + ex.getTargetType().getType().getSimpleName());
            System.out.println(
                    "failed.cause=" + ex.getCause().getClass().getSimpleName());
        }
    }

    private static void propertyMismatch() {
        ProductForm form = new ProductForm();
        BeanWrapper wrapper = new BeanWrapperImpl(form);

        try {
            wrapper.setPropertyValue("quantity", "ten");
        } catch (TypeMismatchException ex) {
            System.out.println(
                    "beanProperty=" + ex.getClass().getSimpleName());
            System.out.println(
                    "beanProperty.required=" +
                    ex.getRequiredType().getSimpleName());
        }
    }

    private static void dataBinderResult() {
        ProductForm form = new ProductForm();
        DataBinder binder = new DataBinder(form, "productForm");

        binder.setAllowedFields("quantity");
        binder.bind(
                new org.springframework.beans.MutablePropertyValues()
                        .add("quantity", "ten"));

        BindingResult result = binder.getBindingResult();

        System.out.println("binder.hasErrors=" + result.hasErrors());
        System.out.println(
                "binder.field=" + result.getFieldError("quantity").getField());
        System.out.println(
                "binder.errorCode=" + result.getFieldError("quantity").getCode());
    }

    public static void main(String[] args) {
        DefaultConversionService service = new DefaultConversionService();

        converterNotFound(service);
        conversionFailed(service);
        propertyMismatch();
        dataBinderResult();
    }
}
~~~

The classes are used for specific purposes:

- `CustomerReference` has no mechanism to be created from `String` in this example, so the default conversion service lacks a matching conversion path.
- `Integer` has a default conversion path; the string `"not-a-number"` causes parsing execution to fail.
- `BeanWrapperImpl` receives `"ten"` to assign to property `int quantity`; the exception is caught as `TypeMismatchException`.
- `DataBinder` receives the same value yet records the error in `BindingResult`, so the caller can read the field error instead of relying on an exception thrown out of a controller.

### 6.3. Compile and Run Commands

Structure:

~~~text
spring-conversion-exceptions-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ConversionExceptionDemo.java
~~~

In the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.ConversionExceptionDemo
~~~

Expected output printed by the program (excluding Maven logs):

~~~text
missing=ConverterNotFoundException
missing.source=String
missing.target=CustomerReference
failed=ConversionFailedException
failed.source=String
failed.target=Integer
failed.cause=NumberFormatException
beanProperty=TypeMismatchException
beanProperty.required=int
binder.hasErrors=true
binder.field=quantity
binder.errorCode=typeMismatch
~~~

The values above reflect the API/flow of the example in Spring Framework 6.2; exact detail messages or cause names in other applications may vary as converters, editors, and configurations differ. If re-implementing on another version or with custom converters, run tests against the exact actual dependencies.

## 7. Why Might DataBinder Not Throw an Exception Outward?

A common misconception is: "If conversion fails, the controller will definitely receive a `ConversionFailedException`." That is not always true.

`DataBinder` is designed to record binding errors in `BindingResult`. When assigning an individual property fails, the binder can turn the failure into a `FieldError` (commonly carrying code `typeMismatch`) so the controller or presentation layer can display the error on the corresponding field.

Example:

~~~java
DataBinder binder = new DataBinder(form, "productForm");
binder.bind(propertyValues);

BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("quantity")) {
    // Display/format error for the quantity field.
}
~~~

This is a **snippet** using existing `form` and `propertyValues` variables. For diagnostic inspection, use:

~~~java
result.getFieldErrors("quantity");
result.getFieldError("quantity").getCode();
result.getFieldError("quantity").getRejectedValue();
result.getFieldError("quantity").getDefaultMessage();
~~~

Not every binding error is `typeMismatch`. There may be non-existent fields, suppressed fields due to allowed/disallowed fields, nested path errors, or exceptions inside setters. Inspect `FieldError`, `ObjectError`, and rejected values selectively.

In Spring MVC, if an `@ModelAttribute` has errors and no `BindingResult` immediately follows it for the controller to handle, the framework can throw a web-layer exception depending on the case. In REST APIs, applications may map errors to HTTP 400. Still, never expose stack traces or internal messages to clients.

## 8. Distinguishing by Usage of ConversionService, BeanWrapper, and DataBinder

| API being called | Purpose | Error form typically encountered |
| --- | --- | --- |
| `ConversionService.convert(source, targetType)` | Convert one value for a type pair | `ConverterNotFoundException` or `ConversionFailedException` |
| `BeanWrapper.setPropertyValue(name, value)` | Convert type and assign one bean property | `TypeMismatchException`, `NotWritablePropertyException`, other accessor errors |
| `DataBinder.bind(PropertyValues)` | Bind a set of inputs to target and record binding errors | `BindingResult` with `FieldError`/`ObjectError` |
| Spring MVC `@ModelAttribute` | Bind request parameters into model object | `BindingResult` or web exception depending on signature/controller/config |
| Spring MVC `@RequestParam` | Convert a request parameter to a method argument | `MethodArgumentTypeMismatchException` or related web error |
| JSON `@RequestBody` | Deserialize body via message converter/Jackson | Message read/deserialization error; do not assume `ConverterNotFoundException` |

**Read the exact API before writing catch blocks.** Do not catch `ConversionException` around an entire request and ignore `BindingResult`, as the binder may have already handled the error to let the application redisplay the form. Conversely, when calling `ConversionService` directly, you must decide whether to catch the exception or let an upper layer handle it.

## 9. Handling Errors by Goal

### 9.1. When a Converter Is Missing

Check `ConversionService` configuration and register the converter:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCustomerReferenceConverter());
~~~

If the app uses Spring Boot, register converters via the appropriate web/conversion configuration mechanism (e.g., `Converter` bean, `Formatter`, or `WebMvcConfigurer#addFormatters`). Do not instantiate a separate `DefaultConversionService` inside a controller expecting Spring MVC to automatically use that instance.

### 9.2. When a Converter Fails on a Value

Inspect the input data and cause chain. If input has invalid format, return a field error with an understandable message. If the converter has a bug or technical exception, log internally with a request correlation ID without sending stack traces to clients.

### 9.3. When Bean Property Type Mismatch Occurs

Check:

- What type does the target Java property declare?
- What type is the source value and is its format valid?
- Is there a matching editor/converter on the right binder/accessor?
- Does the setter throw exceptions or perform its own checks?
- Is the nested path valid and does the child object exist?

If data arrives via `DataBinder`, read `BindingResult` to respond per field. If using `BeanWrapper` directly, catch `PropertyAccessException`/specific subclass in the calling layer capable of deciding the next action.

### 9.4. Do Not Collapse Every Error into One Message

For example, "Invalid data" may suffice for the client, yet internal diagnostics should preserve:

- source/target types;
- field or property path;
- rejected value (redacted if sensitive);
- exception class/cause;
- request ID or correlation ID;
- converter/configuration version when relevant.

Never log secrets or entire sensitive payloads just to see the rejected value.

## 10. Common Pitfalls and Edge Cases

### Confusing ConverterNotFound with ConversionFailed

- `ConverterNotFound`: no matching conversion path exists.
- `ConversionFailed`: a processing path exists, yet data/logic caused it to fail.

If you add an empty converter or a catch-all converter that always throws an exception, the system turns a "not found" error into "failed" while data still goes unhandled. Build converters with clear source/target types and test both valid and invalid data.

### Confusing ConversionFailed with TypeMismatch

When calling `ConversionService` directly, errors belong to the conversion layer. When assigning to a property, errors may be surfaced as `TypeMismatchException`. If you see one exception wrapping another, read both the outer exception and its cause to see what the outer operation was and what the inner conversion error was.

### Using a Converter with the Wrong Generic Types

`Converter<String, Long>` is not a converter for `String -> Integer`. Register in the right registry and specify the right target types; for collections, maps, and generic DTOs, inspect `TypeDescriptor` to determine generic element/key/value types.

### Null Values and Primitives

A `null` value may not convert to primitives such as `int` or `boolean` because primitives cannot hold null. Consider wrappers `Integer`/`Boolean` when a field can be left blank, then let validation decide whether it is required.

### Locale and Date/Number Formatting

`"1,25"` may represent a decimal number in one locale and mean something else in another. Use `Formatter`/explicitly configured locales, avoiding converters that guess global formats.

### Setter Throws Its Own Exception

Even when conversion succeeds, a setter may still throw an exception due to object invariants. In that case, do not conclude the error is `ConverterNotFoundException`; inspect `MethodInvocationException`, `PropertyAccessException`, or the corresponding cause chain.

### No Converter Exists, Yet PropertyEditor Does

Bean property access may use a registered `PropertyEditor` even though direct `ConversionService` knows no conversion. Therefore, a failed `conversionService.convert(...)` call does not prove `BeanWrapper` elsewhere will fail; the two registries/mechanisms may differ.

### No Spring Converter, Yet Jackson Can Deserialize

`@RequestBody` JSON normally uses Jackson/HTTP message converters. Jackson module/deserializer configuration and `ConversionService` are not the same registry. Do not try to fix `ConverterNotFoundException` in MVC by adding a Jackson deserializer if the real endpoint uses `@ModelAttribute`.

## 11. Self-Check Questions

1. What common superclass do `ConverterNotFoundException` and `ConversionFailedException` share?
2. Why is `TypeMismatchException` not a subclass of `ConversionException`?
3. If `DefaultConversionService.convert("abc", Integer.class)` fails, is the reason closer to "converter not found" or "converter execution failed"?
4. When calling `BeanWrapper.setPropertyValue("quantity", "ten")`, why can the error appear at the `PropertyAccessException` layer?
5. Why can `DataBinder.bind(...)` record errors in `BindingResult` instead of throwing an exception outward?
6. When seeing `ConversionNotSupportedException`, how does its package help distinguish it from `ConverterNotFoundException`?
7. If a numeric string is syntactically valid yet exceeds business limits, is that a conversion failure or a validation failure?
8. Why is it necessary to inspect both the exception cause and rejected field when handling errors in production?

**Remember:** `ConverterNotFoundException` = no conversion path found; `ConversionFailedException` = conversion path exists but failed at runtime; `TypeMismatchException` = bean property assignment type mismatch. Identify **which API is being called and which layer raised the error**, inspect type/field/cause, and only then decide whether to register a converter, fix input data, handle property access, or return validation errors.

## Official References

- [Spring Framework Javadoc — ConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionException.html)
- [Spring Framework Javadoc — ConverterNotFoundException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConverterNotFoundException.html)
- [Spring Framework Javadoc — ConversionFailedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionFailedException.html)
- [Spring Framework Javadoc — TypeMismatchException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/TypeMismatchException.html)
- [Spring Framework Javadoc — PropertyAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyAccessException.html)
- [Spring Framework Javadoc — ConversionNotSupportedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/ConversionNotSupportedException.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)