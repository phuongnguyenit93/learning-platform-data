# `setAsText`, `getAsText`, and Internal Value State in `PropertyEditor`

## 1. What Is `PropertyEditor` Used For?

`java.beans.PropertyEditor` is an interface in the JavaBeans API that allows converting and editing a property's value. In Spring Framework, `PropertyEditor` implementations are commonly used in property access and data binding infrastructure to convert string-based data (such as request parameters) into Java values like `Date`, enums, or custom value objects.

A very important point: `PropertyEditor` **is stateful**. Rather than being designed as a pure function `String -> T`, the editor holds its **current value** internally. The `setAsText(String)` method accepts a string, parses it, and typically calls `setValue(Object)` to store the value; `getAsText()` reads the current value via `getValue()` and outputs a string.

```text
Input text "42"
       |
       v
editor.setAsText("42")
       |
       v
parse String -> Integer(42)
       |
       v
editor.setValue(42)            <-- internal state inside editor
       |
       +--> editor.getValue()  -> Integer(42)
       |
       +--> editor.getAsText() -> "42"
```

In this article, distinguish between **text representation**, **the value stored inside the editor**, and **the final value assigned by the binder to the property**. They are related, yet not three identical objects.

## 2. Four Key Methods

| API | Role | Key takeaways |
| --- | --- | --- |
| `setAsText(String text)` | Accepts a string and asks the editor to convert it to a value | May throw `IllegalArgumentException` when parsing fails |
| `getAsText()` | Returns the string representation of the current value | May be a canonical string, not necessarily identical to the original input |
| `setValue(Object value)` | Sets the value held by the editor | Defined by `PropertyEditor`, typically backed by `PropertyEditorSupport` |
| `getValue()` | Retrieves the current value | May return `null` if no value has been set or it was set to `null` |

`PropertyEditor` also declares APIs for JavaBeans design-time support such as tags/custom editors and property change listeners. In Spring data binding, the four methods above are usually central. When writing custom editors, most applications extend `java.beans.PropertyEditorSupport` instead of implementing every method of `PropertyEditor` manually.

### `setAsText` does not return a value

The API signature is `void setAsText(String text)`, **not** `T convert(String text)`. The proper usage is:

```java
editor.setAsText("42");
Object result = editor.getValue();
```

The parsed value is kept in the editor's state. If the text is invalid, the implementation should report the error explicitly; it should not silently keep an old value and mislead the caller into thinking the parse succeeded.

### `getAsText` is not always a strict byte-for-byte inverse

For instance, input `"00042"` may be parsed into integer `42`, and then `getAsText()` returns `"42"`. This is **representation normalization**. There is no guarantee that `getAsText()` must preserve whitespace, leading zeros, or every detail of the original string.

## 3. Runnable Java 17+ Example: Product Code Editor

The example below uses only the JDK's JavaBeans API, **requiring no Spring dependency**. Create `PropertyEditorStateDemo.java`:

```java
import java.beans.PropertyEditorSupport;

public class PropertyEditorStateDemo {
    public record ProductCode(String value) {}

    public static class ProductCodeEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            if (text == null) {
                setValue(null);
                return;
            }
            String normalized = text.trim().toUpperCase();
            if (!normalized.matches("P-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
            setValue(new ProductCode(normalized));
        }

        @Override
        public String getAsText() {
            ProductCode code = (ProductCode) getValue();
            return code == null ? "" : code.value();
        }
    }

    public static void main(String[] args) {
        ProductCodeEditor editor = new ProductCodeEditor();
        editor.setAsText(" p-0042 ");

        System.out.println(editor.getValue());
        System.out.println(editor.getAsText());

        editor.setValue(new ProductCode("P-0007"));
        System.out.println(editor.getAsText());

        editor.setAsText(null);
        System.out.println(editor.getValue() == null);
    }
}
```

Compile and run with JDK 17+:

```bash
javac PropertyEditorStateDemo.java
java PropertyEditorStateDemo
```

Exact stdout:

```text
ProductCode[value=P-0042]
P-0042
P-0007
true
```

State progression over time:

1. Upon creation, the editor has no value yet; `PropertyEditorSupport` starts with `null`.
2. `setAsText(" p-0042 ")` trims whitespace, converts to uppercase, validates the pattern, and sets the value to `ProductCode("P-0042")`.
3. `getValue()` returns that record, while `getAsText()` returns `"P-0042"`.
4. `setValue(new ProductCode("P-0007"))` **directly replaces** the state; `getAsText()` immediately outputs `"P-0007"` without running `setAsText` again.
5. `setAsText(null)` by convention in this implementation clears the state; each custom editor may choose a different rule, provided it is consistent and documented.

Do not treat an editor as a stateless, immutable conversion function. Its state can change through both `setAsText` and `setValue`.

## 4. How Does Editor State Affect Reuse?

`PropertyEditorSupport` holds a mutable value; an editor may retain the parse result of a previous call. For example:

```java
var editor = new PropertyEditorStateDemo.ProductCodeEditor();
editor.setAsText("P-0001");
System.out.println(editor.getAsText());  // P-0001
editor.setAsText("P-0002");
System.out.println(editor.getAsText());  // P-0002
```

This snippet illustrates state and assumes the example class in section 3 has been compiled. `getAsText()` always describes the **current value**, not input history. Reusing an editor sequentially is possible within a controlled flow, but you should not use a mutable editor instance as a singleton shared across multiple requests or threads.

### Thread-safety and lifecycle

- Do not assume `PropertyEditorSupport` is thread-safe. Many editors hold an internal value and lack synchronization suitable for independent requests.
- A singleton editor bean can create race conditions: request A calls `setAsText`, request B overwrites the value, and request A reads corrupted data from `getValue()`.
- With Spring, let the binder/property access create editor instances with the appropriate lifecycle or use an appropriate editor factory/registrar mechanism; never casually share an editor holding state.
- If you only need stateless conversion logic, Spring `Converter<S,T>` or `Formatter<T>` is usually a more reusable abstraction.

## 5. Integrating with Spring `DataBinder`

`DataBinder` can register an editor for a type and apply it during property binding. Suppose a form contains a `ProductCode` property:

```java
public class ProductForm {
    private PropertyEditorStateDemo.ProductCode code;

    public PropertyEditorStateDemo.ProductCode getCode() { return code; }
    public void setCode(PropertyEditorStateDemo.ProductCode code) {
        this.code = code;
    }
}
```

This is a sample class using the same `ProductCode` declared in the main example. Registration snippet inside a Java method with a `form` variable:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(form, "productForm");
binder.registerCustomEditor(
        PropertyEditorStateDemo.ProductCode.class,
        new PropertyEditorStateDemo.ProductCodeEditor());

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", " p-0042 ");
binder.bind(values);

System.out.println(form.getCode());
System.out.println(binder.getBindingResult().hasErrors());
```

Expected output when classes, dependencies, and binder are configured properly:

```text
ProductCode[value=P-0042]
false
```

Processing flow: `DataBinder` looks up property `code` of type `ProductCode`, uses `ProductCodeEditor` to convert the String to a value, and assigns the value via the setter. Any conversion error is recorded as a binding error per the binder mechanism. Registering a custom editor does not automatically run business validation.

This is an **integration snippet**, not a standalone program: it requires `ProductForm`, the main example class, and compatible Spring modules on the classpath. For standard types, Spring already provides default conversions/editors; there is no need to write a custom editor for every property.

## 6. Registering by Type or by Property Path

Spring allows registering an editor by target type and, in supported APIs, by a specific property path:

```java
binder.registerCustomEditor(ProductCode.class, new ProductCodeEditor());
binder.registerCustomEditor(ProductCode.class, "primaryCode",
        new ProductCodeEditor());
```

This snippet assumes `ProductCode` and `ProductCodeEditor` are imported from the main example and the target object has a matching `primaryCode` property. The first call applies to properties of type `ProductCode` within the binder's scope; the second scopes the editor to property path `primaryCode`.

Path-based scoping is useful when two fields share the same Java type but require different input/display formats. However, avoid overusing path-specific editors to the point where conversion arbitrarily depends on hard-to-maintain field names.

## 7. Distinguishing Parse, Print, and Validation

| Operation | Entry point | Output |
| --- | --- | --- |
| Parse text to value | `setAsText(text)` | Side effect on `getValue()` or exception |
| Format current value to text | `getAsText()` | `String` |
| Set value directly | `setValue(value)` | Updates editor state |
| Data binding | `DataBinder.bind(PropertyValues)` | Target populated and `BindingResult` records errors |
| Validation | `Validator.validate(...)` | Business errors in `Errors` |

A product code may be syntactically valid as `"P-0042"` yet not exist in the database; that is a **business rule**, which generally should not go into `PropertyEditor`. The editor should handle representation parsing/formatting, leaving existence, authorization, or data state checks to validators/services.

### When text has invalid format

```java
var editor = new PropertyEditorStateDemo.ProductCodeEditor();
try {
    editor.setAsText("wrong");
} catch (IllegalArgumentException ex) {
    System.out.println("Invalid code");
}
```

Output:

```text
Invalid code
```

This snippet uses the example class from section 3. Because `setAsText` throws an exception **before** `setValue`, the old state remains intact if the editor already held a previous value. When the binder encounters a conversion exception, error reporting and skipping assignment belong to the binder; avoid continuing to read the stale value of a manually reused editor after a failed parse.

## 8. Comparing with Spring `Converter` and `Formatter`

Spring provides conversion APIs that do not require internal mutable values:

```java
import org.springframework.core.convert.converter.Converter;

public class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase();
        if (!normalized.matches("P-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid code");
        }
        return new ProductCode(normalized);
    }
}
```

This is an illustrative class with `ProductCode` defined/imported as in section 3, not standalone by itself. `Converter<String, ProductCode>` has a `convert` method that returns the value directly without holding a "current value" via `setValue/getValue`. Therefore, a stateless converter can usually be shared more safely as long as the implementation stores no other mutable state.

`Formatter<T>` provides `parse(String, Locale)` and `print(T, Locale)` to handle locale-dependent representations (such as dates and currency). For new code, consider `Converter` or `Formatter` instead of mutable editors; still, `PropertyEditor` continues to appear in JavaBeans and Spring binding, especially in legacy codebases.

## 9. Common Pitfalls

- **Treating `setAsText` as returning an object:** it returns `void`; you must retrieve the result via `getValue()`.
- **Assuming `getAsText` returns the exact raw input:** implementations may normalize, trim, or reformat the value.
- **Forgetting to call `setValue` in a custom `setAsText`:** the editor never updates its state after parsing, so the binder may receive null or a stale value.
- **Calling `getAsText` when no value is set:** unconditional casting can trigger `NullPointerException`; handle null safely.
- **Sharing a mutable editor across multiple requests:** risk of state mixing and race conditions.
- **Swallowing parse errors while keeping the old value:** callers may think the new input succeeded; throw an explicit exception and do not rely on a stale editor.
- **Passing a different type into `setValue`:** `PropertyEditorSupport` accepts `Object`; custom `getAsText` casts may fail if the value is of the wrong type.
- **Confusing conversion errors with validation:** valid syntax does not guarantee the data is valid under business rules.
- **Giving editors too many responsibilities:** querying a database or calling external services during parsing makes binding hard to test and manage performance.

## 10. Design and Testing Checklist

1. Clearly define valid strings, normalization rules, and null/blank handling.
2. Inside `setAsText`, after parsing, update state using `setValue`.
3. Inside `getAsText`, read `getValue()` and produce a stable representation.
4. Test `setAsText` on valid input, invalid input, null, and test direct `setValue`.
5. Decide whether `getAsText` normalizes input; do not demand character-for-character round-tripping if that is not the contract.
6. Never share unsynchronized stateful editor instances across concurrent threads.
7. When integrating with Spring, register editors before `bind` and verify `BindingResult`.
8. Prefer `Converter`/`Formatter` when pure or locale-aware conversion is needed.

**Remember:** `setAsText` converts a string into a value and stores it in the editor's internal state; `getAsText` reads that state to output a string. Understanding this mutability prevents improper editor reuse, catches parse errors early, and keeps Spring data binding safe and consistent.
