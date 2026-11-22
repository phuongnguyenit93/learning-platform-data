# Record component order and canonical constructors

When instantiating a record with Reflection, finding the right parameter types only solves half the problem. You also have to put **the right value in the right position**. If two components have the same type, swapping them can create an object that is valid by type yet wrong in meaning.

The canonical constructor (*canonical constructor*) is the constructor tied to all components declared in the record header. Component order determines the parameter order of this constructor. Thanks to that relationship, a data mapping tool can look up the constructor and order arguments on a sound basis.

This article uses Java 17 or later and focuses on the relationship between component metadata, constructor signatures, and the data used to instantiate objects.

## 1. What does a record's header determine?

With the declaration:

```java
record Trip(String origin, String destination, int transfers) {
}
```

The canonical constructor accepts three parameters in order:

| Position | Component | Parameter type | Value meaning |
| --- | --- | --- | --- |
| `0` | `origin` | `String` | Departure point |
| `1` | `destination` | `String` | Destination |
| `2` | `transfers` | `int` | Number of transfers |

This relationship of name, type, and order belongs to [the record canonical constructor rules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.1). If no explicit canonical constructor is declared, the compiler provides it.

A record can have other constructors to support more convenient ways of creating objects. Therefore, do not pick `getDeclaredConstructors()[0]` or pick just any constructor whose parameter count looks suitable. You must find **the exact sequence of parameter types in header order**.

In particular, both positions `origin` and `destination` are `String`. Reflection cannot tell which string is the departure point or the destination from data type alone. The responsibility of binding the right value to the component name belongs to the mapping code.

## 2. Finding the canonical constructor from metadata

`Class.getRecordComponents()` preserves component declaration order. Take `getType()` of each component in that order to build a `Class<?>[]`, then pass that type sequence to `getDeclaredConstructor(...)`.

Process:

1. Verify the type is a record; the component result is non-`null`.
2. Preserve the order of the `RecordComponent[]` array.
3. Convert each component to `Class<?>` using `getType()`.
4. Look up the constructor with that exact sequence of types.

[The `Class.getRecordComponents()` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()) describes both the ordering rule and how to apply it to find the canonical constructor.

Do not sort components by name before the lookup step. An order that looks nice for display is not necessarily a valid parameter order.

`getDeclaredConstructor` looks up by parameter types; it does not select an overload from actual values the way a `new` call written in source code does.

## 3. Standalone Java 17+ experiment

The program includes these cases: a record with a compact canonical constructor, a secondary constructor, map-formatted data, primitive parameters, an empty record, a generic record, and a varargs component.

Save the entire code into **`RecordConstructorDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public class RecordConstructorDemo {
    public record Trip(String origin, String destination, int transfers) {
        public Trip {
            origin = Objects.requireNonNull(origin, "origin").strip();
            destination = Objects.requireNonNull(destination, "destination").strip();
            if (transfers < 0) {
                throw new IllegalArgumentException("transfers must be nonnegative");
            }
        }

        public Trip(String origin, String destination) {
            this(origin, destination, 0);
        }
    }

    public record Empty() {
    }

    public record Bundle<T>(T content) {
    }

    public record Labels(String... values) {
    }

    public static <R extends Record> Constructor<R> canonicalConstructor(
            Class<R> recordType) throws NoSuchMethodException {
        Objects.requireNonNull(recordType, "recordType");
        RecordComponent[] components = recordType.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected a record declaration");
        }
        Class<?>[] parameterTypes = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        return recordType.getDeclaredConstructor(parameterTypes);
    }

    public static <R extends Record> R constructFromMap(
            Class<R> recordType, Map<String, ?> values)
            throws ReflectiveOperationException {
        Objects.requireNonNull(values, "values");
        Constructor<R> constructor = canonicalConstructor(recordType);
        RecordComponent[] components = recordType.getRecordComponents();
        Object[] arguments = new Object[components.length];
        for (int i = 0; i < components.length; i++) {
            String name = components[i].getName();
            if (!values.containsKey(name)) {
                throw new IllegalArgumentException("Missing component: " + name);
            }
            arguments[i] = values.get(name);
        }
        if (values.size() != components.length) {
            throw new IllegalArgumentException("Unexpected component keys");
        }
        return constructor.newInstance(arguments);
    }

    @FunctionalInterface
    private interface CheckedAction {
        void run() throws ReflectiveOperationException;
    }

    private static void attempt(String label, CheckedAction action) {
        try {
            action.run();
            System.out.println(label + " -> success");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> InvocationTargetException, cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (ReflectiveOperationException | IllegalArgumentException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Constructor<Trip> constructor = canonicalConstructor(Trip.class);
        System.out.println("Components = "
                + Arrays.stream(Trip.class.getRecordComponents())
                        .map(RecordComponent::getName).toList());
        System.out.println("Canonical parameters = "
                + Arrays.stream(constructor.getParameterTypes())
                        .map(Class::getTypeName).toList());

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("destination", "Hue");
        input.put("transfers", 1);
        input.put("origin", " Hanoi ");
        System.out.println("Input key order = " + input.keySet());
        System.out.println("From map = " + constructFromMap(Trip.class, input));
        System.out.println("Same-type swap = "
                + constructor.newInstance("Hue", "Hanoi", 1));

        attempt("wrapper lookup", () -> Trip.class.getDeclaredConstructor(
                String.class, String.class, Integer.class));
        attempt("missing no-arg", () -> Trip.class.getDeclaredConstructor());
        attempt("null primitive", () -> constructor.newInstance("Hanoi", "Hue", null));
        attempt("validation failure", () -> constructor.newInstance("Hanoi", "Hue", -1));
        attempt("missing key", () -> constructFromMap(
                Trip.class, Map.of("origin", "Hanoi")));

        Constructor<Empty> emptyConstructor = canonicalConstructor(Empty.class);
        System.out.println("Empty parameter count = "
                + emptyConstructor.getParameterCount());
        System.out.println("Empty instance = " + emptyConstructor.newInstance());

        Constructor<?> bundleConstructor = canonicalConstructor(Bundle.class);
        System.out.println("Bundle parameters = "
                + Arrays.stream(bundleConstructor.getParameterTypes())
                        .map(Class::getTypeName).toList());
        System.out.println("Bundle instance = " + bundleConstructor.newInstance("book"));

        Constructor<Labels> labelsConstructor = canonicalConstructor(Labels.class);
        Labels labels = labelsConstructor.newInstance(
                (Object) new String[]{"x", "y"});
        System.out.println("Labels parameter = "
                + labelsConstructor.getParameterTypes()[0].getTypeName());
        System.out.println("Labels constructor isVarArgs = "
                + labelsConstructor.isVarArgs());
        System.out.println("Labels values = " + Arrays.toString(labels.values()));

        attempt("base Record", () -> canonicalConstructor(Record.class));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordConstructorDemo.java
java RecordConstructorDemo
```

Output:

```text
Components = [origin, destination, transfers]
Canonical parameters = [java.lang.String, java.lang.String, int]
Input key order = [destination, transfers, origin]
From map = Trip[origin=Hanoi, destination=Hue, transfers=1]
Same-type swap = Trip[origin=Hue, destination=Hanoi, transfers=1]
wrapper lookup -> NoSuchMethodException
missing no-arg -> NoSuchMethodException
null primitive -> IllegalArgumentException
validation failure -> InvocationTargetException, cause=IllegalArgumentException
missing key -> IllegalArgumentException
Empty parameter count = 0
Empty instance = Empty[]
Bundle parameters = [java.lang.Object]
Bundle instance = Bundle[content=book]
Labels parameter = java.lang.String[]
Labels constructor isVarArgs = true
Labels values = [x, y]
base Record -> IllegalArgumentException
```

`attempt()` is an experiment helper: it prints the error type so the program can continue observing other cases. It is not an error-handling contract for a complete data mapping library.

## 4. Two sequences to keep in sync: parameter types and argument values

The `canonicalConstructor` method builds the type sequence `[String.class, String.class, int.class]` from `Trip`'s metadata. That is the basis for finding the right constructor.

The `constructFromMap` method builds another sequence: **the argument values**. This sequence must also follow component order, not the key iteration order of the map.

In the experiment, data was inserted in the order:

```text
destination → transfers → origin
```

However, the mapping method looks up the values of `origin`, `destination`, `transfers` in sequence, so the constructor receives:

```text
" Hanoi " → "Hue" → 1
```

The compact canonical constructor strips leading and trailing whitespace from the strings, so the final result is `Trip[origin=Hanoi, destination=Hue, transfers=1]`.

### Why does swapping two values of the same type not raise an error?

The call `constructor.newInstance("Hue", "Hanoi", 1)` still matches the `(String, String, int)` signature. It creates the reversed trip in a type-valid way.

This is a semantic error that Reflection's type checks cannot detect on their own. If reading data by component name, use that name as the key and place the value at the component's exact index.

Do not build arguments with `values.values().toArray()` and hope the map order always matches the header. Even a map that preserves insertion order can be populated in a different order, as shown by the data in the example.

### Distinguishing a missing key from a `null` value

The sample code uses `containsKey(name)` before `get(name)`. This distinguishes having no data for a component from the caller intentionally passing `null`.

The sample method requires all component names and rejects extra keys. This is the sample method's mapping policy, not automatic Reflection behavior. After collecting the arguments, whether a `null` value is accepted still depends on the parameter type and checks inside the constructor.

## 5. Compact constructors still have all parameters

The declaration `public Trip { ... }` in the program is a **compact canonical constructor**. Omitting the parameter list in source syntax does not turn it into a no-argument constructor.

Reflection still sees the `(String, String, int)` signature. The compact body uses the parameter variables corresponding to the header to validate or normalize data; assigning the component fields is completed according to record rules. See [compact canonical constructors in the JLS](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.2).

In the experiment:

- `origin` and `destination` are normalized with `strip()`.
- Negative `transfers` is rejected.
- The secondary constructor taking two strings calls `this(origin, destination, 0)`.

Whether the canonical constructor is compiler-provided, written in full, or written compactly, the lookup approach based on component metadata still applies. There is no need to guess which syntax form the author used in source code.

The `Trip` record has no no-argument constructor. Therefore, `Trip.class.getDeclaredConstructor()` throws `NoSuchMethodException`, even though it has another secondary constructor.

## 6. Signature lookup differs from argument conversion on invocation

These are two steps with different rules.

### On lookup

`int.class` and `Integer.class` are two different types. Because the `transfers` component has type `int`, looking up with `Integer.class` does not find the canonical constructor and throws `NoSuchMethodException`.

Therefore, do not build the signature by calling `argument.getClass()` on each value: the value `1` inside `Object[]` is an `Integer`, whereas the constructor actually takes `int`. A `null` value does not even have `getClass()` to call.

Build the signature from `RecordComponent.getType()`, because it describes the **declared type**, not the runtime class of the current argument.

### On invocation

`Constructor.newInstance(Object... arguments)` accepts values in object form. For an `int` parameter, an `Integer` object can be unboxed to pass into the constructor. The API also has rules for allowed primitive conversions, but it does not automatically parse numeric strings into numbers or arbitrarily narrow types. See [the `Constructor.newInstance` contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).

In the experiment, passing `null` for the `int` position causes `IllegalArgumentException` before the constructor body executes. Passing `"1"` instead of a numeric value is also not a configurable conversion performed automatically by Reflection.

A real-world mapping library needs an explicit data conversion step before calling the constructor; the algorithm in this article only handles binding names to positions and invoking the constructor.

## 7. Errors before invocation vs. errors from inside the constructor

Two cases in the output need to be distinguished:

| Experiment | Output | Did the constructor run its validation logic? |
| --- | --- | --- |
| Passing `null` for `int` `transfers` | `IllegalArgumentException` | Did not enter the body |
| Passing `transfers = -1` | `InvocationTargetException`, cause is `IllegalArgumentException` | Entered and actively rejected |

In the second case, `InvocationTargetException` is the wrapper of the Reflection call. `getCause()` gives the exception that the constructor actually threw.

A tool invoking constructors should preserve this information when reporting errors. An "invalid argument type" message does not accurately explain the case where data entered the constructor but violated a business invariant.

You should also separate constructor-not-found errors, lack-of-access errors, and data-validation errors. Do not use one generic message that leaves users unsure whether to fix structure, access permissions, or input values.

## 8. Special cases

### Empty records

`Empty` has the header `()`. Component metadata has length `0`, so the parameter type sequence is also empty. The canonical constructor is the no-argument constructor and can be invoked with `newInstance()`.

This follows from the record's structure, not a rule that every record has a no-argument constructor.

### Generic records

`Bundle<T>(T content)` has `T` with no more specific bound, so the parameter type used for lookup is `Object.class`. The printed result `[java.lang.Object]` confirms this.

`RecordComponent.getGenericType()` is useful for analyzing generic declarations, but `getDeclaredConstructor(...)` requires `Class<?>[]`. Therefore, the algorithm uses [the component type from `getType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html#getType()). Do not replace the declared type sequence with the class of the `"book"` value, namely `String.class`.

### Varargs components

`Labels(String... values)` has one component with type `String[]`. The canonical constructor has **one array parameter**, and `isVarArgs()` returns `true`.

Distinguish the target constructor's array from the varargs mechanism of `Constructor.newInstance(Object...)` itself. In the example:

```java
Labels labels = labelsConstructor.newInstance(
        (Object) new String[]{"x", "y"});
```

This is an excerpt from the full program. The `(Object)` cast turns the entire `String[]` into **one argument**. An equivalent representation is passing an outer argument array containing exactly one string-array element.

Do not pass two separate strings and assume Reflection will wrap them into the constructor's `String[]`. Calling code must prepare the exact argument count and array shape.

### Base class and access permissions

The `<R extends Record>` bound does not exclude `Record.class` itself, so the method still checks whether component metadata is non-`null`. The `base Record` experiment is rejected before the constructor lookup step.

`getDeclaredConstructor` finds non-public constructors as well, but finding one does not automatically grant permission to invoke it. The example uses public nested records so the calls are valid in their context. When applying to types from another package or module, handle access permissions according to the application's contract rather than blindly opening every constructor.

## 9. Application checklist

| Check item | Right basis |
| --- | --- |
| Is it a record? | `isRecord()` or non-`null` component array |
| What is the canonical parameter order? | Order of `getRecordComponents()` |
| What type is used for lookup? | `RecordComponent.getType()` |
| Which constructor is canonical? | Constructor matching the entire type sequence from the header |
| Which value goes in which position? | Bind by component name then place at the corresponding index |
| Missing value or intentionally passed `null`? | Check key existence separately from value |
| Where did the error come from? | Separate lookup errors, Reflection invocation, and the cause of `InvocationTargetException` |
| Is there a compact constructor? | Compact syntax does not change the header-based signature |

### Self-check

1. Why does swapping `origin` and `destination` not cause a type error?
2. Why can `Integer.class` not replace `int.class` in the constructor lookup step?
3. If a data map preserves key insertion order, why is it still necessary to order arguments by metadata?
4. Why is the compact constructor of `Trip` not looked up with an empty type sequence?
5. How can you distinguish an `int` parameter refusing `null` from a constructor actively rejecting a negative value?
6. Why does `Labels` have one constructor parameter even though an object can hold multiple strings?

The relationship to maintain throughout is **component order → parameter type order → argument value order**. When these three sequences stay synchronized, creating records via Reflection can be clearly verified and explained.
