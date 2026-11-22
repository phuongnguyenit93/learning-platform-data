# Identifying records with `isRecord()` and `getRecordComponents()`

A general-purpose tool does not always know an application's data types in advance. When receiving a `Class<?>`, the tool may need to distinguish records from ordinary classes, find the names of data components, and read values from an object.

Java provides two starting points: **`isRecord()` determines whether a type is a record**, and **`getRecordComponents()` describes the components declared in the record header**. From that description, a program can find the corresponding accessor method to read the data.

These APIs have existed since Java 16; the examples in this article use Java 17 or later and do not require preview features.

## 1. What are records and record components?

Consider the declaration:

```java
record Ticket(String title, int priority, boolean ready) {
}
```

`title`, `priority`, and `ready` are three **record components**. They are declared in the header between the parentheses, in that order.

For each component, the record has a corresponding data field and a public accessor method. For example, the `title` component is associated with the `title` field and the `title()` method. This is the relationship in [Java's record model](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).

In Reflection, three objects each have their own role:

| Metadata object | What does it describe? |
| --- | --- |
| `RecordComponent` | A component in the record header |
| `Field` | A data field of the class |
| `Method` | A method, including the record's accessor |

`RecordComponent` is not the `title` value of a specific object. It describes that the record type has a component named `title`, what type it has, and which accessor it uses.

## 2. The two APIs on `Class<?>`

Signatures:

```java
public boolean isRecord()
public RecordComponent[] getRecordComponents()
```

These are signatures for API lookup, not methods you need to implement yourself.

According to [the `Class.getRecordComponents()` contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()), the resulting array preserves the declaration order in the header. If it is a record with no components, the array has length `0`; if it is not a record, the result is `null`.

| Type under inspection | `isRecord()` | `getRecordComponents()` |
| --- | --- | --- |
| Record with components | `true` | Array of component metadata |
| Record with an empty header | `true` | Empty array |
| Ordinary class, interface, enum, array type, or primitive type | `false` | `null` |
| The base class `java.lang.Record` itself | `false` | `null` |

Therefore, do not access `.length` or iterate directly over the result without handling the `null` case. At the same time, do not treat an empty array as evidence that a type is not a record.

You can check `isRecord()` first to branch by type kind, or obtain the array once and then check for `null`. In a tool that only reads record components, the second approach often keeps the condition and the needed data in one place.

## 3. Reading information from `RecordComponent`

Each element provides the following information via [the `RecordComponent` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html):

| Method | Information obtained |
| --- | --- |
| `getName()` | Component name |
| `getType()` | Type represented as a `Class<?>` |
| `getGenericType()` | Declared type represented as a `Type`, including generic information if any |
| `getAccessor()` | `Method` object of the accessor method |
| `getDeclaringRecord()` | Record class that declares the component |

For example, for the component `List<String> labels`, `getType()` gives `List.class`, while `getGenericType()` represents `List<String>`. The declared type metadata and the value held inside an object are two different layers of information.

## 4. Complete experiment on Java 17+

The program below contains a record with data, an empty record, a generic record, and an ordinary class with a structure similar to a record. It both reads the type's metadata and reads values from objects.

Save the entire code into **`RecordInspectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class RecordInspectionDemo {
    public record Ticket(
            String title, int priority, boolean ready, List<String> labels) {
        public static final String KIND = "ticket";
    }

    public record Marker() {
    }

    public record Box<T>(T value) {
    }

    public static final class PlainTicket {
        private final String title;

        public PlainTicket(String title) {
            this.title = title;
        }

        public String title() {
            return title;
        }
    }

    private static void describe(Class<?> type) {
        System.out.println(type.getSimpleName() + " isRecord = " + type.isRecord());
        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            System.out.println("components = null");
            return;
        }
        System.out.println("component count = " + components.length);
        for (RecordComponent component : components) {
            System.out.println(component.getName()
                    + " | type=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | accessor=" + component.getAccessor().getName());
        }
    }

    public static Map<String, Object> readRecord(Object value)
            throws ReflectiveOperationException {
        Objects.requireNonNull(value, "value");
        Class<?> type = value.getClass();
        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected record: " + type.getName());
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (RecordComponent component : components) {
            Object componentValue = component.getAccessor().invoke(value);
            result.put(component.getName(), componentValue);
        }
        return result;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        describe(Ticket.class);
        System.out.println("Declared fields, sorted = "
                + Arrays.stream(Ticket.class.getDeclaredFields())
                        .map(field -> field.getName())
                        .sorted()
                        .toList());

        Ticket ticket = new Ticket(
                "Import", 2, true, List.of("java", "reflection"));
        System.out.println("Read values = " + readRecord(ticket));
        System.out.println("First component owner = "
                + Ticket.class.getRecordComponents()[0]
                        .getDeclaringRecord().getSimpleName());
        System.out.println("ready accessor parameters = "
                + Ticket.class.getRecordComponents()[2]
                        .getAccessor().getParameterCount());
        try {
            Ticket.class.getMethod("isReady");
        } catch (NoSuchMethodException ex) {
            System.out.println("isReady lookup = " + ex.getClass().getSimpleName());
        }

        describe(Marker.class);
        System.out.println("Read empty record = " + readRecord(new Marker()));
        describe(PlainTicket.class);
        describe(Record.class);

        describe(Box.class);
        Box<String> box = new Box<>("hello");
        System.out.println("Read generic record = " + readRecord(box));
        System.out.println("Box runtime class = "
                + (box.getClass() == Box.class));

        try {
            readRecord(new PlainTicket("Import"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Read ordinary class = " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordInspectionDemo.java
java RecordInspectionDemo
```

Output:

```text
Ticket isRecord = true
component count = 4
title | type=java.lang.String | generic=java.lang.String | accessor=title
priority | type=int | generic=int | accessor=priority
ready | type=boolean | generic=boolean | accessor=ready
labels | type=java.util.List | generic=java.util.List<java.lang.String> | accessor=labels
Declared fields, sorted = [KIND, labels, priority, ready, title]
Read values = {title=Import, priority=2, ready=true, labels=[java, reflection]}
First component owner = Ticket
ready accessor parameters = 0
isReady lookup = NoSuchMethodException
Marker isRecord = true
component count = 0
Read empty record = {}
PlainTicket isRecord = false
components = null
Record isRecord = false
components = null
Box isRecord = true
component count = 1
value | type=java.lang.Object | generic=T | accessor=value
Read generic record = {value=hello}
Box runtime class = true
Read ordinary class = IllegalArgumentException
```

## 5. Understanding the experiment output

### Component order comes from the header

`Ticket`'s header declares `title`, `priority`, `ready`, `labels`. The loop follows that exact order. `priority` is not placed first just because its type is `int`, and `labels` is not placed first alphabetically.

This order is useful when presenting data structures, matching data with the canonical constructor signature, or preserving column order as declared. When using metadata for long-term storage formats, structural changes still need to be managed; reordering components in source code is not an invisible change to tools that depend on position.

### Static fields are not record components

`Ticket` has a static field `KIND`. Therefore, the field list printed in the experiment includes `KIND` along with the four fields corresponding to the components. The `getRecordComponents()` array contains only the four components in the header.

The field list was **intentionally sorted by name** before printing, so the line `[KIND, labels, priority, ready, title]` cannot be used as evidence of Reflection's default order.

If the goal is to understand the record's structure, retrieve the component list directly. Do not retrieve all fields and assume every field is a component or rely on field order.

### Empty records and non-record classes

`Marker` has the header `()`, so `isRecord()` returns `true`, the component count is `0`, and the value-reading method produces an empty map `{}`.

`PlainTicket` has a `title` field and a `title()` method, yet it is still an ordinary class. It does not become a record just by naming its method following the same convention. The result is `isRecord()` equal to `false` and the component array equal to `null`.

`Record.class` produces the same result: it is the base class, not a concrete record with a header. Do not use the class name, the presence of an accessor, or an overly broad inheritance check as a substitute for `isRecord()`.

## 6. Metadata does not hold an object's values on its own

`describe(Ticket.class)` does not need to create a `Ticket`, because it only reads the type structure. Conversely, to know what `title` currently equals, you need an object, such as the `ticket` variable in the example.

The `readRecord` method follows this process:

1. Reject `null` objects.
2. Obtain the runtime class with `value.getClass()`.
3. Obtain component metadata and reject non-record classes.
4. Retrieve the accessor from each `RecordComponent`.
5. Invoke the accessor on the exact `value` object and store the result by component name.

`LinkedHashMap` in the experiment preserves insertion order, so the `Read values` output line has the same order as the header.

The core line is:

```java
Object componentValue = component.getAccessor().invoke(value);
```

This is an excerpt from the full method already shown in the program. `component` is the metadata, and `value` is the target object receiving the call. The return type of the reflective call is `Object`; for primitive components such as `int` or `boolean`, the result is boxed into its corresponding wrapper object.

### Record accessors do not use JavaBean prefixes

`ready` in the example has the accessor `ready()`, not `getReady()` or `isReady()`. The line `isReady lookup = NoSuchMethodException` proves you should not prepend prefixes yourself when looking up a record's default accessor.

`getAccessor()` returns the exact corresponding `Method`, saving tools from guessing names. The naming rules, empty parameter list, and return type of an accessor are defined in [the JLS on record members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3).

### Calling an accessor is still calling a method

A record can declare an explicit accessor. Therefore, calling an accessor executes that method's behavior, rather than always reading the raw data field directly. Tools must understand their own data-reading contract.

The example uses public nested records so accessors can be called without opening special access. When used with records from elsewhere, class, package, and module access rules can still affect the call. Finding metadata does not automatically grant permission to cross all access boundaries.

`readRecord` declares `throws ReflectiveOperationException` so callers know the reflective call can fail. In real code, distinguish access errors from exceptions thrown by the accessor and preserve the cause information; do not silently skip a component when reading fails.

## 7. Generic records and type information limits

`Box<T>(T value)` produces:

- `getType()` of `value` is `Object` because `T` has no more specific bound.
- `getGenericType()` represents the type variable `T` in the declaration.
- Reading the object `new Box<String>("hello")` yields the value `hello`.

That does not mean `Box.class`'s metadata changes `T` to `String` per object. The expression `box.getClass() == Box.class` still evaluates to `true`. The same class metadata is shared across different type argument assignments of `Box`.

If a library needs to know the concrete type arguments of a usage context, it must receive additional type information from that context. Looking only at the contained value or at `getClass()` is not a general solution for recovering full generic information.

Distinguish two questions when designing a tool:

- What is the **declared** type of the component?
- What is the value of the component on the **object under inspection**?

The two questions complement each other; neither replaces the other.

## 8. Application and common pitfalls

This pair of APIs is suitable for tools that display data structures, map by component name, validate data, or libraries that need a separate handling branch for records. It avoids inferring type kinds from class shape.

| Common pitfall | Correct handling |
| --- | --- |
| Calling `.length` on the result for an ordinary class | Check for `null` or branch using `isRecord()` |
| Treating an empty record as not a record | Distinguish an empty array from `null` |
| Treating `Record.class` as a concrete record | Use the result of `isRecord()` |
| Taking all fields as record components | Use `getRecordComponents()` for header structure |
| Sorting components yourself and assuming it is declaration order | Preserve the API's order when header order is needed |
| Treating `RecordComponent` as an instance's data | Call the accessor on an appropriate object |
| Prepending `get` or `is` prefixes yourself | Use `getAccessor()` |
| Assuming reading metadata implies permission to call every accessor | Handle access restrictions and reflective invocation errors |
| Assuming an object's generics replace `T` in class metadata | Distinguish declared types from type argument context |

Records also do not automatically make the entire inner object graph immutable. If a component references mutable data, a reading tool should not arbitrarily modify that data just because it obtained it through an accessor.

### Self-check

1. Why does `Marker.class.getRecordComponents()` return an empty array, whereas `PlainTicket.class.getRecordComponents()` returns `null`?
2. Does adding a static field to `Ticket` increase the number of components?
3. How does swapping the order of `priority` and `ready` in the header affect the metadata output?
4. Why is having `Class<?>` sufficient to describe a component, yet insufficient to know the value of `title`?
5. For `Box<String>`, why is the declared generic type of `value` still `T`?

Grasp the flow: **identify the record → retrieve component metadata in header order → choose type information or the accessor → read the value on the right object when needed**.
