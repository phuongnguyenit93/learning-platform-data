# Mapping Input Values Using Explicit Conversion Rules

## 1. The problem in tools using Java Reflection

A tool invoking methods via reflection may receive input from a CLI, HTTP request, configuration, or form. Data sources typically pass **strings** to the tool (e.g., `"3"`, `"true"`, `"2026-10-24"`), whereas Java methods require actual types like `int`, `boolean`, `LocalDate`, or an enum.

Example target method:

```java
public String create(int count, boolean urgent, LocalDate due,
                     Priority priority, BigDecimal budget) {
    // Business logic.
}
```

The tool cannot simply pass strings straight into `Method.invoke`:

```java
// WRONG if method expects int, boolean, LocalDate, Priority, BigDecimal:
method.invoke(target, "3", "true", "2026-10-24", "HIGH", "125.50");
```

`Method.invoke` **does not parse strings into business types**. For supplied arguments, reflection can apply certain compatible primitive **unboxing/widening** conversions, but it does not automatically know that `"3"` means an integer, `"HIGH"` means an enum, or which format a date string follows. Letting the system guess implicitly makes behavior hard to test, hard to report errors on, and prone to safety issues.

**Lesson goal:** build an explicit conversion mechanism from **input values** to **target parameter types**, validating and reporting errors before actually invoking the method. This is a reflection tool design technique, not a guide to overriding Java's conversion system.

After this lesson, you can:

- Retrieve parameter types via `Method.getParameterTypes()`, checking count and order.
- Declare an allowed conversion rule table (allowlist) instead of guessing by class name strings.
- Distinguish `null` data, empty strings, the literal string `"null"`, and parsed values.
- Separate **conversion errors** from **exceptions thrown by business logic**.
- Handle more complex scopes such as overloaded methods, varargs, generics, enums, and method-call authorization.
- Design testable, extensible results and errors without introducing unpredictable conversions.

## 2. Mapping pipeline: from input to Method parameters

A clear pipeline should follow these steps:

```text
Raw input (strings or already parsed data)
        |
        v
Identify permitted method to invoke
        |
        v
Method.getParameterTypes() -> type at each position
        |
        v
Check argument count, nullability, and rules per type
        |
        v
Convert + validate with contextual errors
        |
        v
Converted Object[]
        |
        v
Method.invoke(target, convertedArgs)
```

Each position `i` corresponds to exactly one `parameterTypes[i]` and one input value `rawValues[i]`. In Java, parameter indices start at **0**. If the application wants to display "1st parameter", it can convert `i + 1` when building messages.

Two APIs to know:

```java
Class<?>[] types = method.getParameterTypes();
int count = method.getParameterCount();
```

`getParameterTypes()` returns types **after type erasure**. For example, `List<String>` and `List<Integer>` both have runtime parameter type `List.class`. `getGenericParameterTypes()` can help read generic declarations at metadata level, though it does not automatically parse or validate generic contents.

`method.getParameters()` can provide parameter metadata. However, meaningful source names are normally only available if compiled with `-parameters`; otherwise names like `arg0` may appear. Tools must not blindly depend on parameter names without verifying metadata availability.

## 3. Conversion rules must be declared explicitly

First decide **what input forms are supported**. The illustrative example below accepts `String[]` from a text data source. This is an intentional choice; if receiving JSON, the tool must distinguish JSON number/boolean/null tokens from JSON strings before mapping.

Sample policy table:

| Target type | Permitted rule | Valid example | Rejected example |
| --- | --- | --- | --- |
| `String` | Keep text verbatim, no auto-trim | `"  A  "` | No automatic reformatting |
| `int` / `Integer` | `Integer.valueOf(raw)`; check `int` range | `"3"`, `"-8"` | `"3.5"`, out-of-range number |
| `long` / `Long` | `Long.valueOf(raw)`; check `long` range | `"9876543210"` | Value exceeding `long` |
| `boolean` / `Boolean` | Accept **only exact** `"true"` or `"false"` | `"true"` | `"yes"`, `"TRUE"` |
| `LocalDate` | `LocalDate.parse(raw)` per default ISO-8601 | `"2026-10-24"` | `"24/10/2026"` |
| An allowed enum, e.g., `Priority` | `Priority.valueOf(raw)`; matches constant name | `"HIGH"` | `"High"` |
| `BigDecimal` | `new BigDecimal(raw)` per Java decimal syntax | `"125.50"` | `"12,50"` with comma |

This is a **sample policy**, not a Java limitation. An application may choose different rules such as case-insensitivity or allowing whitespace, provided they are documented, tested, and applied consistently. For currency, `BigDecimal` is usually more suitable than `double` to avoid binary rounding errors in decimal arithmetic; rules on scale, rounding, and currency must be defined separately in the business layer.

**Avoid implicit guessing conversions:**

- Do not call `String.valueOf(x)` on arbitrary data only to re-guess its type later.
- Do not treat any string other than `"true"` as `false`. `Boolean.parseBoolean("yes")` returns `false`, failing this article's strict policy.
- Do not parse dates with multiple formats without a clear precedence order.
- Do not instantiate arbitrary classes via `Class.forName(raw)` or invoke arbitrary methods by user-supplied names.
- Do not equate "castable" with "semantically valid"; for example, converting `long` to `int` can lose data.

## 4. Complete Java 17+ example: explicit conversion and Method invocation

Create file `ExplicitMappingDemo.java`:

```java
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ExplicitMappingDemo {
    enum Priority { LOW, HIGH }

    public static class TaskService {
        public String create(int count, boolean urgent, LocalDate due,
                             Priority priority, BigDecimal budget) {
            return String.format(Locale.ROOT,
                    "count=%d urgent=%s due=%s priority=%s budget=%s",
                    count, urgent, due, priority, budget.toPlainString());
        }
    }

    static Object[] mapArguments(Method method, String[] rawValues) {
        Class<?>[] types = method.getParameterTypes();
        if (rawValues.length != types.length) {
            throw new IllegalArgumentException(
                    "expected " + types.length + " arguments, got " + rawValues.length);
        }

        Object[] converted = new Object[types.length];
        for (int i = 0; i < types.length; i++) {
            try {
                converted[i] = convert(rawValues[i], types[i]);
            } catch (IllegalArgumentException | DateTimeParseException ex) {
                throw new IllegalArgumentException(
                        "argument " + i + " must be " + types[i].getTypeName(), ex);
            }
        }
        return converted;
    }

    static Object convert(String raw, Class<?> type) {
        if (raw == null) {
            if (type.isPrimitive()) {
                throw new IllegalArgumentException("primitive cannot be null");
            }
            return null;
        }
        if (type == String.class) return raw;
        if (type == int.class || type == Integer.class) return Integer.valueOf(raw);
        if (type == long.class || type == Long.class) return Long.valueOf(raw);
        if (type == boolean.class || type == Boolean.class) {
            if (raw.equals("true")) return true;
            if (raw.equals("false")) return false;
            throw new IllegalArgumentException("boolean must be true or false");
        }
        if (type == LocalDate.class) return LocalDate.parse(raw);
        if (type == Priority.class) return Priority.valueOf(raw);
        if (type == BigDecimal.class) return new BigDecimal(raw);
        throw new IllegalArgumentException("unsupported type: " + type.getTypeName());
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Method method = TaskService.class.getMethod("create",
                int.class, boolean.class, LocalDate.class,
                Priority.class, BigDecimal.class);
        String[] raw = {"3", "true", "2026-10-24", "HIGH", "125.50"};
        Object result = method.invoke(new TaskService(), mapArguments(method, raw));
        System.out.println(result);

        try {
            mapArguments(method,
                    new String[]{"3", "yes", "2026-10-24", "HIGH", "125.50"});
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        try {
            mapArguments(method, new String[]{null, "true", "2026-10-24", "HIGH", "125.50"});
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ExplicitMappingDemo.java
java ExplicitMappingDemo
```

Stdout **verified by running the Java program**:

```text
count=3 urgent=true due=2026-10-24 priority=HIGH budget=125.50
rejected: argument 1 must be boolean
rejected: argument 0 must be int
```

Analysis:

1. `getMethod("create", int.class, boolean.class, LocalDate.class, Priority.class, BigDecimal.class)` locates **one exact signature** on `TaskService`, avoiding guessing overloads from user strings.
2. `getParameterTypes()` returns five types in declaration order; `rawValues.length` must equal five.
3. `convert` branches explicitly on **target `Class<?>`**, not string-based class names.
4. `"3"` is parsed into `Integer`; when `Method.invoke` calls the method expecting `int`, the wrapper is unboxed validly.
5. Booleans only accept `"true"/"false"`; `"yes"` fails at parameter index `1`, before invoking the business method.
6. `LocalDate.parse` handles ISO dates; `Priority.valueOf` accepts a specific enum constant; `BigDecimal` stores `125.50` and `toPlainString()` preserves decimal representation.
7. The first parameter of type `int` cannot accept `null`; the error is caught before reflection invocation.

**Intentional limitations of the example:** currently only `String`, `int/Integer`, `long/Long`, `boolean/Boolean`, `LocalDate`, the `Priority` enum, and `BigDecimal` are permitted. Any other type is rejected. It can be extended per concrete policy, though it should never silently "accept every class". The example also treats `raw == null` as **true absence of value**; the string `"null"` remains a four-character string and does not automatically become null.

## 5. Primitives and wrappers: nullability checks

Reflection distinguishes `int.class` from `Integer.class`:

- `int.class.isPrimitive()` returns `true`; `null` cannot be passed to a primitive `int` parameter.
- `Integer.class.isPrimitive()` returns `false`; `null` may be passed at the call level, though the business method may still reject it if absent values are unacceptable.
- `Method.invoke` typically takes an `Object[]`; an `int` value is represented via `Integer` in that array and unboxed by reflection as needed.
- Certain valid **primitive widening** conversions exist during reflection invoke, yet conversions carrying business meaning should still be specified by the mapping layer. Reflection does not perform arbitrary narrowing or parse `String` into `int`.

Risk table:

| Input | Target type | Decision |
| --- | --- | --- |
| `null` | `int` | Reject immediately |
| `null` | `Integer` | Allowed at the example converter layer; business logic decides validity |
| `"0"` | `int` | Parse to `Integer.valueOf("0")`, unbox at invocation |
| `"2147483648"` | `int` | Reject as out of range |
| `""` | `int` | Parse failure; do not default to `0` |
| `""` | `String` | Preserve empty string |
| `"null"` | `String` | Preserve literal string; do not convert to `null` |

Do not substitute defaults like `0`, `false`, or `LocalDate.now()` for invalid input without an explicit contract requirement; doing so can make the system perform wrong actions.

## 6. Designing good errors and testing every rule

A good converter should return a **strongly typed success result**, or an error containing at minimum:

- Parameter position (`index`) or confirmed parameter name.
- Required target type (`Class.getTypeName()`).
- Concise error code: wrong argument count, unsupported type, invalid format, out of range, null not allowed.
- Preserved root cause (`cause`) for internal diagnostics.

Example using `IllegalArgumentException` wrapping the root cause:

```java
try {
    converted[i] = convert(rawValues[i], types[i]);
} catch (IllegalArgumentException | DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "argument " + i + " must be " + types[i].getTypeName(), ex);
}
```

This snippet is extracted from the complete example. Preserving `cause` distinguishes `NumberFormatException` from `DateTimeParseException` without exposing an internal stack trace to the end user.

**Do not automatically include sensitive input contents in error messages**: the tool may be processing access tokens, emails, or personal data. Record sufficient position/type info while applying an appropriate logging policy.

Test in these categories:

| Category | Test cases |
| --- | --- |
| Valid | Boundary values of `int/long`, boolean `true/false`, ISO dates, valid enums |
| Invalid format | `"12.5"` into `int`, `"yes"` into boolean, date `"31/12/2026"` |
| Out of range | Numbers greater than `Integer.MAX_VALUE` or less than `Integer.MIN_VALUE` |
| Null/empty | `null` into primitive, empty string into number, literal string `"null"` |
| Wrong count | Missing/extra arguments |
| Unsupported type | `UUID`, `List`, custom classes without a registered converter |
| Business rule violation | Validly parsed type violating constraints such as `count < 0` |
| Target exception | Target method throwing after the conversion step |

Note that `convert` is only responsible for checking specified type/syntax; **business validation** such as positive prices, maximum quantities, or valid deadlines requires a separate step. Successful parsing does not mean the input is authorized for use.

## 7. Separating conversion errors from Method.invoke errors

After the mapper returns a valid `Object[]`, the reflection call can still fail because:

- Access to the method is denied, throwing `IllegalAccessException`.
- The `target` object does not match the instance method or arguments are incompatible at call time, causing `IllegalArgumentException`.
- The target method itself throws an exception, wrapped in `InvocationTargetException`.

An illustrative snippet handling the invocation layer (requires importing `java.lang.reflect.InvocationTargetException` and `Method`):

```java
try {
    Object[] args = mapArguments(method, rawValues);
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    // Error from the business method itself.
    throw ex.getCause();
}
```

This snippet belongs in a method declaring `throws Throwable`; access/conversion exceptions must be handled at the appropriate caller layer. **Never treat `InvocationTargetException` as a parse error**: the target already ran and threw the exception itself. Separating these two error categories determines whether to tell the user to fix input or fix business logic.

In production code, instead of catching all `Exception` and returning a single generic message, classify errors by code, log at the right level, and show users only appropriate details.

## 8. Overloads, varargs, enums, and generics

### 8.1. Overloaded methods

`getMethod` selects by name and **exact parameter type list**:

```java
// If create(int) and create(String) exist:
Method m = SomeService.class.getMethod("create", int.class);
```

Never resolve overloads by "picking the first method with the same name" from `getMethods()`: return order is not a contract for overload selection, and the same string `"123"` could be valid for both `String` and `int`. If dynamic overload resolution is forced upon you, define explicit precedence and ambiguity-detection rules; if two methods match equally without a clear rule, **report ambiguity** instead of guessing.

### 8.2. Varargs

A method `send(String... messages)` has a final parameter of type `String[]` at the reflection level. `Method.isVarArgs()` identifies the declaration, while `getParameterTypes()` still shows the array in the last position.

When using `Method.invoke`, build an array of the proper type for the varargs parameter and place it as **one element** of the `Object[]` arguments passed to the method. The simple mapper in the example does not automatically collect multiple strings into an array; if needed, explicitly define varargs mapping, reject missing required arguments, and distinguish a single array from multiple arguments.

### 8.3. Enums

`Enum.valueOf(...)` is case-sensitive and throws `IllegalArgumentException` when no matching constant exists. The example only supports `Priority`, and does not open conversion privileges to arbitrary enums on the classpath.

To support additional enums, register the permitted enums and, when needed, map friendly names to constants via an explicit configuration table. Never load classes or constants arbitrarily from untrusted input.

### 8.4. Collections and generics

`List<String>` cannot be fully determined from `getParameterTypes()` alone due to type erasure. Mapping a JSON list to a typed list of elements requires rules reading `getGenericParameterTypes()` or a dedicated schema, per-element validation, null policies, and size limits.

In real-world tool design, explicit schemas/DTOs are usually clearer than guessing generics in every reflection case. In particular, do not allow reflecting into every private field just to construct objects from input.

## 9. Extending with a controlled converter registry

As supported types grow, replace the `if` chain with a registry pairing **target type** and **conversion function**:

```java
// Illustrative snippet in a class that imports Map, Class, Function.
Map<Class<?>, java.util.function.Function<String, ?>> converters = Map.of(
        String.class, raw -> raw,
        Integer.class, Integer::valueOf,
        Long.class, Long::valueOf,
        LocalDate.class, LocalDate::parse
);
```

The illustrative registry above only registers wrapper/reference types; when receiving primitives, add a mapping step `int.class -> Integer.class`, `long.class -> Long.class` per policy. Similarly, enums or parameterized converters may need a richer contextual API. This snippet is **not** a complete mapper and does not handle nulls/booleans/errors; the section 4 example is the standalone runnable program.

A solid design should include these components:

1. **Allowlist of accessible methods/classes** independent of converters. Being able to parse a type does not mean permission to invoke any method accepting that type.
2. **Converter registry** supporting only registered types, with dedicated tests and documented formatting rules.
3. **Validation layer** checking business constraints after parsing and before invocation.
4. **Invocation layer** receiving only normalized data and distinguishing reflection errors from target-thrown errors.
5. **Error reporting** providing position, type name, error code, and cause for debugging without leaking sensitive data.

A shared schema can be used for command line, request body, and configuration, though each source still needs its own initial parser (e.g., JSON numbers differ from JSON strings).

## 10. Common design mistakes

1. **Calling `Method.invoke(target, strings...)` and expecting the JVM to parse strings:** reflection does not do that.
2. **Relying on `Object.toString()` to convert every type:** loses data structure and formatting may depend on locale.
3. **Using `Boolean.parseBoolean` for strict requirements:** any value other than `"true"` silently becomes `false`.
4. **Automatically trimming or altering decimal separators:** original `String` data may need to stay intact; normalization must be declared explicitly.
5. **Picking the first overload by name:** causes unstable failures when adding overloads or running on another JVM.
6. **Allowing `null` into primitives:** must be caught before invoke.
7. **Failing to separate parsing from business validation:** `"-1"` may parse validly to `int`, yet `count = -1` is still invalid.
8. **Putting raw values directly into error logs:** risks exposing sensitive data.
9. **Automatically accepting every accessible class/constructor/field:** turns the converter into an overly privileged and hard-to-audit extension point.
10. **Assuming runtime generics retain full type arguments:** requires a schema or controlled generic metadata inspection.

## 11. Self-check

**Question 1.** Target expects `int`, raw value is `"007"`. How should conversion behave? 

If policy chooses `Integer.valueOf` as in the sample, the string parses to integer `7`; there is no "preserve leading zeros" for `int`. If leading zeros carry business meaning, the target type should probably be `String`.

**Question 2.** Why is `Boolean.parseBoolean("yes")` unsuitable for a strict boolean policy?

Because per API behavior it returns `false` for any value not equal to `"true"`; invalid input is misinterpreted as a valid value. Check the allowed literals list before converting.

**Question 3.** If a user enters `"2026-02-30"`, what will `LocalDate.parse` do?

The date does not exist so parsing fails (typically `DateTimeParseException`); the mapper must report the position/type error and not invoke the business method.

**Question 4.** Two overloads `save(int)` and `save(String)` could both accept the string `"123"` under two policies. Which should be called?

It cannot be decided from the input alone. You must define overload selection rules; if missing, report ambiguity or require the caller to specify the exact signature.

**Question 5.** `getParameterTypes()` returns `List.class`; is that enough to assert elements must be `String`?

No. Java erasure removes most type arguments at the `Class<?>` level; use a separate schema or generic metadata if needed.

**Question 6.** Why preserve the original cause when wrapping mapping errors?

To distinguish causes like out-of-range integers, wrong enum names, or invalid date syntax, while the user-facing layer can still return a stable message free of sensitive data.

## 12. Key takeaway

**Explicit mapping = know target types upfront, declare allowed conversions, validate inputs, and only then invoke reflection.** A robust tool does not try to "guess every input correctly"; it provides a conversion contract that can be explained, tested, and extended. `Method.getParameterTypes()` provides runtime parameter types; the converter handles parsing; validation enforces business constraints; `Method.invoke` merely performs the call.

JDK 17 Documentation:

- [Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Method.getParameterTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getParameterTypes())
- [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [Boolean](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html)
- [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)