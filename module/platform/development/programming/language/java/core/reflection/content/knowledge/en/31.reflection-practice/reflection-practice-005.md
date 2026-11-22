# Practice: Building a Tiny Data Mapper via Accessors or Record Components

## 1. Problem Statement and Expected Result

Suppose an application needs to convert a Java object into a data table shaped like `Map<String, Object>`. That map can be used for controlled logging, generating display data, converting to another DTO, or serving as a first step toward serialization. For classes known in advance, an explicit conversion method is usually the simplest option; this practice exercise focuses on the case where **structure must be discovered at runtime via Reflection**, while still constraining scope and handling errors clearly.

We will write a **one-way** mapper:

```text
Java object
    |
    |-- record?  --> RecordComponent[] --> getAccessor() --> Method.invoke(...)
    |
    +-- JavaBean? --> PropertyDescriptor[] --> getReadMethod() --> Method.invoke(...)
    |
    v
Map<String, Object>  (key = component/property name, value = accessor result)
```

Example inputs include:

- `Invoice` is a **record** with two components, `code` and `total`.
- `CustomerView` is a **readable JavaBean-style class** with getters `getName()` and `isActive()`.
- The mapper accepts **only two allowlisted types**; it does not read arbitrary classes whose names are sent by a user.
- The resulting map is sorted by key name for easy testing and cannot be modified through the returned `Map` API.

Expected output:

```text
record = {code=INV-7, total=80}
bean = {active=true, name=Lan}
```

**Intentionally small scope:** reads only top-level properties, keeping Java-typed values as-is; does not read private fields directly, does not construct objects from a map, does not recurse into nested objects, does not handle cycles, does not auto-convert types, and **does not generate JSON**. `Map.toString()` is a Java debug printout representation, not valid JSON.

## 2. Understanding the Two Accessor Models Before Writing the Mapper

### Record components

Since Java 16, a record is syntax describing a class designed to carry data with a fixed set of components. For example:

```java
public record Invoice(String code, int total) {}
```

The compiler provides the corresponding accessors: `code()` and `total()`. They **are not JavaBeans getters named `getCode()` or `getTotal()`**. Therefore, do not assume the JavaBeans Introspector will automatically find record properties properly.

Reflection provides:

- `type.isRecord()`: checks whether the class is a record.
- `type.getRecordComponents()`: retrieves the declared `RecordComponent`s in header component order.
- `component.getName()`: component name, e.g., `"code"`.
- `component.getType()`: declared type, e.g., `String.class` or `int.class`.
- `component.getAccessor()`: the corresponding accessor `Method` object; can be called with `Method.invoke(receiver)`.

Conceptual example:

```java
RecordComponent[] parts = Invoice.class.getRecordComponents();
for (RecordComponent part : parts) {
    Method accessor = part.getAccessor();
    // Object value = accessor.invoke(invoice);
}
```

This is an **illustrative code snippet requiring imports and enclosing context**, not a standalone runnable file. Primitive types such as `int` are boxed to `Integer` when stored as `Object` in the map.

Records typically generate private final fields and public accessors; the mapper uses accessors **instead of** enabling access to private fields. However, a record's "shallow immutability" does not guarantee referenced data inside is immutable: if a component holds a mutable `List`, the map will hold a reference to that same list object.

### JavaBean properties

For ordinary classes:

```java
public static final class CustomerView {
    private final String name;
    private final boolean active;

    public CustomerView(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public String getName() { return name; }
    public boolean isActive() { return active; }
}
```

By JavaBeans convention:

- `getName()` represents the `name` property.
- `isActive()` represents the boolean `active` property.
- Read-only properties **are still valid** even if the class has no setters.
- An arbitrary method `calculate()` is not automatically a JavaBean property.
- `getClass()` is inherited from `Object`; internal class metadata should not be included in the data map.

`java.beans.Introspector.getBeanInfo(type, Object.class)` discovers properties by convention and excludes metadata belonging to the `Object` superclass. Each `PropertyDescriptor` has `getName()`, `getPropertyType()`, and `getReadMethod()`. The read method can be null if a property is write-only; the mapper skips that case.

Unlike record components, a JavaBean is a **naming and metadata convention**, not a mandatory class syntax. Property names do not necessarily match field names: a getter may compute a value instead of reading a field directly, and may have side effects or throw exceptions.

**Module note:** `java.beans.Introspector` belongs to the `java.desktop` JDK module, not `java.base`. In applications with a `module-info.java` file, `requires java.desktop;` is needed when using this JavaBeans API; ordinary classpath applications running on a full JDK do not need that declaration.

## 3. Concrete Contract of the Mini Mapper

We choose a simple interface:

```java
Map<String, Object> toMap(Object source);
```

Contract:

1. `source == null` is rejected with `NullPointerException` with message `"source"`.
2. The source type is checked against an **allowlist** consisting of `Invoice.class` and `CustomerView.class`; other types are rejected with `IllegalArgumentException`. This keeps Reflection within a controlled scope.
3. For a record, only retrieve components returned by `getRecordComponents()` and invoke their corresponding accessors.
4. For a JavaBean, only retrieve readable properties from `PropertyDescriptor` returned by Introspector, without looking up private fields.
5. Getters can fail. The mapper **does not swallow errors**; instead it throws `IllegalStateException` and preserves the original `cause`.
6. `null` values are allowed in the map because `TreeMap` is used (unlike `Map.copyOf`, which forbids nulls).
7. The result is wrapped with `Collections.unmodifiableMap(...)`. Callers cannot add, remove, or replace entries through that map; this does not deeply freeze objects stored as values.

This exercise uses property name keys (`String`), so there are no null keys. The key order of `TreeMap` is string natural ordering, not the record declaration order or the order returned by Reflection/Introspector.

## 4. Complete Runnable Program on Java 17+

Create a file named **`TinyMapperDemo.java`** with the following content:

```java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class TinyMapperDemo {
    public record Invoice(String code, int total) {}

    public static final class CustomerView {
        private final String name;
        private final boolean active;

        public CustomerView(String name, boolean active) {
            this.name = name;
            this.active = active;
        }

        public String getName() {
            return name;
        }

        public boolean isActive() {
            return active;
        }
    }

    public static Map<String, Object> toMap(Object source) {
        Objects.requireNonNull(source, "source");
        Class<?> type = source.getClass();

        // Do not execute arbitrary getters on classes from untrusted sources.
        if (type != Invoice.class && type != CustomerView.class) {
            throw new IllegalArgumentException(
                    "Unsupported: " + type.getName());
        }

        Map<String, Object> result = new TreeMap<>();

        if (type.isRecord()) {
            for (RecordComponent component : type.getRecordComponents()) {
                result.put(
                        component.getName(),
                        read(component.getAccessor(), source));
            }
        } else {
            try {
                for (PropertyDescriptor property :
                        Introspector.getBeanInfo(type, Object.class)
                                .getPropertyDescriptors()) {
                    Method accessor = property.getReadMethod();
                    if (accessor != null) {
                        result.put(property.getName(),
                                read(accessor, source));
                    }
                }
            } catch (IntrospectionException ex) {
                throw new IllegalStateException(
                        "Invalid bean metadata", ex);
            }
        }

        return Collections.unmodifiableMap(result);
    }

    private static Object read(Method accessor, Object receiver) {
        try {
            return accessor.invoke(receiver);
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException(
                    "Inaccessible: " + accessor.getName(), ex);
        } catch (InvocationTargetException ex) {
            throw new IllegalStateException(
                    "Accessor failed: " + accessor.getName(),
                    ex.getCause());
        }
    }

    public static void main(String[] args) {
        System.out.println("record = "
                + toMap(new Invoice("INV-7", 80)));
        System.out.println("bean = "
                + toMap(new CustomerView("Lan", true)));
    }
}
```

Compile and run from the exact directory containing the file:

```bash
javac -encoding UTF-8 TinyMapperDemo.java
java TinyMapperDemo
```

Output:

```text
record = {code=INV-7, total=80}
bean = {active=true, name=Lan}
```

Why does it produce this output?

**For record** `new Invoice("INV-7", 80)`: `isRecord()` returns `true`, and the loop fetches both `code` and `total` components. `getAccessor()` leads to `code()` returning `"INV-7"` and `total()` returning `80`. `TreeMap` keeps keys in alphabetical order, so `code` appears before `total`.

**For JavaBean** `new CustomerView("Lan", true)`: this type is not a record, so `Introspector` is used. `getName()` is read as `name=Lan` and `isActive()` as `active=true`. We only collect readable properties and exclude `class` from `Object.getClass()` thanks to the `Object.class` stop class. `TreeMap` orders `active` before `name`.

**Why does `read(...)` use two separate catch blocks?** When the caller lacks permission, `Method.invoke` can throw `IllegalAccessException`. When the accessor **is called** and throws an exception itself, Reflection wraps that exception in `InvocationTargetException`; `getCause()` retrieves the underlying error. The mapper wraps it in `IllegalStateException`, rather than returning a map with a missing key that hides bugs.

The classes in this example are public nested types and public accessors; `setAccessible(true)` is unnecessary. With classes/modules elsewhere, package visibility or module exports can make a method appear public yet remain inaccessible to the caller. Do not turn `setAccessible(true)` into the default workaround.

## 5. Walking Through the Mapping Flow

### Step 1: decide the metadata kind

`type.isRecord()` is the specialized check for records. When `true`, use `getRecordComponents()` instead of guessing `getXxx()` names. When `false`, this exercise uses JavaBeans conventions for an allowed type.

These are **two separate mapping paths**. Do not mix them ad hoc — for example, on a record, both calling `getRecordComponents()` and scanning `getMethods()` to guess extra properties: that risks duplicate keys or invoking methods outside the data contract.

### Step 2: keep only invokable accessors

For records, `RecordComponent.getAccessor()` returns the corresponding accessor method. For JavaBeans, `PropertyDescriptor.getReadMethod()` can be null, so it must be checked.

Do not directly grab every `Method` from `getMethods()` and strip the `get` prefix yourself, as that easily mishandles `isXxx`, capitalized properties, write-only properties, overloads, and JavaBeans naming edge cases. `Introspector` already handles a major portion of resolving this convention.

### Step 3: invoke with the right receiver

Both record accessors and JavaBean getters here are **no-argument instance methods**:

```java
Object value = accessor.invoke(source);
```

This snippet illustrates usage once `accessor: Method` and `source` are available. The argument `source` is the receiver, not a getter parameter. If the receiver has the wrong type, invocation fails. Primitive values such as `int`/`boolean` are boxed when returned as `Object`.

### Step 4: build the map by property name

Record component names come from `getName()`. JavaBean property names come from `PropertyDescriptor.getName()`, **without needing** to hand-write logic stripping `get`/`is` and lowercasing.

The map uses `TreeMap<String,Object>` for stable display ordering. When a real serializer needs to preserve record declaration order, `LinkedHashMap` is a better fit; the sample program's output intentionally **sorts alphabetically** to make tests unambiguous.

### Step 5: return a map that cannot be mutated directly

`Collections.unmodifiableMap(result)` prevents callers from calling `put/remove` on the returned map. Note that if values are mutable lists/maps/objects, mutating inside those values can still occur. If you need a deeply immutable snapshot for multi-threaded sharing or long-term storage, you must define proper copying/serialization rather than assuming the map wrapper does that.

## 6. Testing Errors and Verifying the Contract

With the complete program above, you can append the following statements **at the end of `main`** to test error branches:

```java
try {
    toMap(new Object());
} catch (IllegalArgumentException ex) {
    System.out.println("unsupported = true");
}

try {
    toMap(null);
} catch (NullPointerException ex) {
    System.out.println("null = true");
}

Map<String, Object> immutable = toMap(new Invoice("INV-8", 90));
try {
    immutable.put("extra", 1);
} catch (UnsupportedOperationException ex) {
    System.out.println("readOnlyMap = true");
}
```

This snippet **is not a standalone runnable program**; place it inside `main` of `TinyMapperDemo` while keeping the existing imports. When integrated properly, the program additionally prints:

```text
unsupported = true
null = true
readOnlyMap = true
```

These examples demonstrate three clear boundaries:

- Arbitrary types are not introspected automatically; the mapper rejects them before Reflection invokes any accessor.
- Null cannot be passed as the source object.
- Callers cannot use `put` to modify the resulting map.

In real systems, use unit tests/assertions instead of only observing printed lines. Also test objects with properties returning null, getters throwing exceptions, classes in other modules, classes holding mutable references, and schema version changes.

## 7. Extending Mapping Without Breaking the Contract

### a) Mapping multiple types via a managed registry

The allowlist in the example fits two preset classes. As the number of types grows, you can manage registered adapters:

```java
interface ObjectMapper<T> {
    Map<String, Object> toMap(T source);
}
```

This is an **illustrative interface declaration**. A registry keyed by `Class<?>` can point each type to an explicit mapper; unregistered types are rejected. When you genuinely need Reflection to support arbitrary records/JavaBeans, place allowlist rules for classes/packages, properties, annotations, and privacy right at the registry boundary.

### b) Selecting only properties approved for disclosure

Not every public getter should be exported. For instance, `getPasswordHash()`, `getAccessToken()`, or `getInternalNotes()` may exist on a class without being meant for clients. Real serializers should therefore have a property allowlist or opt-in annotations, dedicated DTOs, explicit transforms/redaction, and data-protection tests.

**Reflection helps find members, not decide whether a member may be disclosed.** A log/map containing sensitive data is still a leak even when every Reflection call is valid.

### c) Direct fields and accessors have different meanings

Calling `Field.get(...)` reads a declared field; calling `Method.invoke(...)` on a getter executes accessor logic. A getter can compute values, check permissions, lazy-load data, or throw exceptions. In many domains, using accessors matches how the API contract exposes data; however, with expensive getters, mapping everything can trigger many DB queries (*N+1 queries*) or side effects.

Distinguish "reading a value" from "executing a getter": a mapper that automatically invokes getters is unsafe on unknown objects.

### d) Records carry data, but are not automatically a JSON schema

`RecordComponent.getAccessor()` provides Java-style names. If JSON names differ from Java names, or if you need versioning, nullability, nested conversion, dates/times, enum encoding, polymorphism, default values, and schema evolution, you need additional mapping rules.

A record like `record User(String firstName, List<String> roles)` does not automatically become schema-compliant JSON simply by dropping values into a map. You need a converter with contracts for nested types and nulls, or a properly configured serialization library.

### e) Reverse mapping

Constructing a record from a map requires locating the **canonical constructor** with the exact component types and order, fetching values by name, checking nulls for primitives, coercing/converting types, handling unknown/missing keys, and invoking the constructor. For a JavaBean, you must know which constructor/setters/builders are permitted. That is a separate task, far more prone to data errors than reading.

Do not implement reverse mapping by grabbing all private fields and calling `setAccessible(true)` to assign them arbitrarily: that can break invariants, hit final-field/module restrictions, and bypass validation. When deserialization is needed in production, use explicit DTOs/constructors or a schema-aware library.

## 8. Common Reflection Errors

| Error | Where it can occur | Cause / how to handle |
| --- | --- | --- |
| `IllegalAccessException` | `Method.invoke` | Accessor or enclosing class is inaccessible; check visibility/modules and call site |
| `InvocationTargetException` | `Method.invoke` | Getter was invoked and threw an error itself; inspect `getCause()` |
| `IntrospectionException` | `Introspector.getBeanInfo` | Could not introspect JavaBeans metadata as requested |
| `IllegalArgumentException` | Allowlist check or invoking method with wrong receiver | Sample intentionally rejects unregistered classes; distinguish from Reflection argument-type errors |
| `NullPointerException` | `Objects.requireNonNull(source)` | Missing source object |
| `UnsupportedOperationException` | Caller calls `put` on returned map | Resulting map is structurally unmodifiable |
| Duplicate/missing property | Broken mapper design or missing accessor | Use `RecordComponent`/`PropertyDescriptor` properly and define filtering policy |
| Unexpectedly mutated values | Getter has side effects or returns mutable object | Do not treat returned values as a deeply immutable snapshot |

Never catch `Exception` and silently skip a failing property. When a mapper quietly omits a field, callers can receive a map that **looks successful** yet is missing critical data. If the product requires best-effort mapping, explicitly define a result type carrying per-field errors; this exercise chooses **fail-fast** so errors are not hidden.

## 9. Performance and Lifecycle Boundaries

Calling `getRecordComponents()` or `Introspector.getBeanInfo(...)` generally should not be repeated needlessly inside a loop processing many objects of the same type. You can cache metadata/accessor lists per `Class<?>` or retain a schema-level mapping plan.

However, caching must account for class loaders: a static `Map<Class<?>, ...>` with strong references can pin classes from plugins/redeploys in memory. For class-keyed metadata, `ClassValue<T>` is an appropriate option; component-scoped caches can also be simpler. `Introspector` also maintains an internal cache; when managing dynamic classes, consider `Introspector.flushFromCaches(type)` at the right lifecycle point.

Within this practice exercise, no cache is added to keep the code readable. Add caching only after profiling shows metadata discovery is a hotspot. In production applications, compare Reflection mappers against explicit mappers, benchmark after JIT warmup, and measure getter costs too.

## 10. Practice Extensions

1. Create `record Point(int x, int y)`. Allowlist that record in the mapper, print the result, and explain the key order when using `TreeMap`.
2. Add a JavaBean with `getTitle()`, `isPublished()`, and a `calculateChecksum()` method. Why does the third method not become a valid JavaBeans property by convention?
3. Add a getter returning null. Demonstrate that the result still retains the key with a null value, and explain why switching to `Map.copyOf(...)` would fail.
4. Add a getter that intentionally throws `IllegalStateException("offline")`. Verify that the mapper does not swallow the error and preserves the original cause from `InvocationTargetException`.
5. Try calling `toMap(new Object())`. Explain why an allowlist matters when source data is untrusted.
6. Replace `TreeMap` with `LinkedHashMap`. For records, check how component declaration order affects map iteration order.
7. Add an allowlist of permitted property names to the mapper; do not export properties such as `passwordHash` or `secretKey` even if their getters are public.
8. Discuss why reverse mapping `Map → record` requires additional constructor checks, type conversion, missing-key handling, and validation. Write a clear API proposal before coding.

### Acceptance Checklist

- The program compiles and runs on Java 17+.
- Records use `getRecordComponents()` and `getAccessor()`, while JavaBeans use `Introspector` and `getReadMethod()`.
- `setAccessible(true)` is not used to bypass Java access control.
- The `class` property from `Object.getClass()` is not exposed.
- Results for both types match the published output.
- Null input and unregistered types are handled explicitly.
- Accessor errors preserve their cause for diagnosis.
- Limitations regarding nested objects, nulls, data security, and access control are clearly documented.

**Target outcome:** build a small-scale one-way mapper using accessors/record components; read metadata accurately for both Java models, invoke accessors safely, handle Reflection errors, and know when to replace a mini mapper with an explicit API or dedicated serialization tool.