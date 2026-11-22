# Enum: values(), valueOf(), name(), and ordinal() in Java

> **Java Core → Class/Object → Enum**  
> **Main scope:** four APIs `values()`, `valueOf()`, `name()`, `ordinal()`, how they relate to identity and enum constant order.  
> **Environment:** Java 17+; standalone examples with `javac`/`java` commands and fixed stdout.

## 1. Overview: four operations do four different things

An `enum` is a special type representing a set of named constants declared in source:

~~~java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}
~~~

With `Direction`:

| API | Primary purpose | Example and result |
| --- | --- | --- |
| `Direction.values()` | Get an **array containing all enum constants**, in declaration order | `[NORTH, EAST, SOUTH, WEST]` |
| `Direction.valueOf("EAST")` | Look up a constant by its **exact declared name** | `Direction.EAST` |
| `Direction.EAST.name()` | Read the **identifier name** of a constant | `"EAST"` |
| `Direction.EAST.ordinal()` | Read the **position** in declaration order, starting from 0 | `1` |

These operations **do not create additional enum constant instances**. `values()` creates/returns a new array containing references to existing constants; `valueOf()` returns the corresponding existing constant; `name()` returns a String name; `ordinal()` returns a primitive int.

Specifically:

- `name()` uses the exact name declared in source, **independent of any `toString()` override**.
- `valueOf()` matches by exact name, is **case-sensitive**, and does not automatically use a display label.
- `ordinal()` is a position dependent on declaration order, **not a stable business/database ID**.
- `values()` returns a separate array on each call, yet **the elements are still references to canonical enum constants**.

These are the first rules to distinguish when building menus, handling input, storing enums in a database, using switch statements, collections, or tests.

## 2. Starting from identity and the set of constants

In Java, an enum constant is an object with a fixed reference identity within a runtime enum class. With:

~~~java
Direction a = Direction.NORTH;
Direction b = Direction.NORTH;
~~~

`a == b` is true. Both references point to the same `Direction.NORTH`, not two separate objects sharing the same content.

### 2.1. `values()` does not recreate instances

~~~java
Direction[] first = Direction.values();
Direction[] second = Direction.values();

System.out.println(first == second);   // false
System.out.println(first[0] == second[0]); // true
~~~

**A new array** and **new enum instances** are two different things. `first != second` because `values()` returns a separate array; `first[0] == second[0]` because both elements point to the same constant NORTH.

### 2.2. `valueOf()` also returns the canonical constant

~~~java
Direction parsed = Direction.valueOf("NORTH");
System.out.println(parsed == Direction.NORTH); // true
~~~

`valueOf` looks up a declared constant; it does not invoke the enum constructor to create a new object.

### 2.3. `null` is not an enum constant

An enum-typed variable is a reference variable, so it can hold null:

~~~java
Direction value = null;
~~~

This **does not add a "null value" to `Direction.values()`**. Calling an instance method such as `value.name()` or `value.ordinal()` on a null variable will throw a `NullPointerException`; handle null according to the contract of the API you design.

### 2.4. Enum and `==` comparison

Because constants are canonical objects, using `==` to compare two enum references of appropriate type is usually simple, clear, and safe even when one operand is null:

~~~java
Direction direction = null;
System.out.println(direction == Direction.NORTH); // false
~~~

Conversely, calling `direction.equals(Direction.NORTH)` will throw an NPE if direction is null. `Enum.equals` is final and compares by identity; it cannot be overridden to change equality semantics.

## 3. `values()` — getting constants in declaration order

`values()` is an **implicitly declared static method for each enum type** according to Java language rules. For `Direction`, the equivalent signature is:

~~~java
public static Direction[] values()
~~~

You call it using the **enum class name**:

~~~java
Direction[] all = Direction.values();
~~~

### 3.1. The order is declaration order

If you declare:

~~~java
enum State {
    NEW, ACTIVE, PAUSED, CLOSED
}
~~~

then `State.values()` returns references in the order:

~~~text
[NEW, ACTIVE, PAUSED, CLOSED]
~~~

It does not sort alphabetically, nor rely on `toString()`, database ID, or hash order.

This order is precisely the order that `ordinal()` reflects.

### 3.2. The array can be modified, without changing the enum declaration

~~~java
State[] values = State.values();
values[0] = State.CLOSED;
~~~

This line is **valid** because array elements can be reassigned. However, it only modifies the array held by the caller. The next call to `State.values()` still puts `NEW` at index 0. You do not modify the static enum constants, change ordinals, or insert additional constants.

### 3.3. Repeated calls to `values()` and allocation

Java language rules require returning a separate array on each call. For small enums, the cost is usually negligible. However, in a hot loop calling `values()` millions of times, creating many arrays can incur allocation overhead.

If you only need to iterate over the set of constants repeatedly, you can keep a private cached array **without exposing write access to that array**. For a public API, you should not directly return a cached mutable array; callers could replace elements and corrupt the cache contents.

Intentional design example:

~~~java
enum Mode {
    OFF, ON;

    private static final Mode[] CACHE = values();

    static int count() {
        return CACHE.length;
    }
}
~~~

This is a declaration fragment; the `count()` method only returns the size without exposing the array. If you want an immutable public List for reuse, you can create:

~~~java
private static final java.util.List<Mode> ALL =
        java.util.List.of(values());
~~~

With the Mode enum in the fragment, `List.of(values())` receives the array unpacked into varargs elements; the List holds the constants and disallows structural mutation. Note that keeping a fixed List is also an API/design choice: it avoids copying on every use while ensuring no mutable backing array is exposed.

### 3.4. Do not use `values()` as a dynamic registry

Even if users add new names through a form, `values()` still returns the set of values declared in the enum source. If states need to be registered at runtime, you must use another abstraction such as a record/value class, a Map registry, or interface implementations.

## 4. Complete program 1 — four APIs and two levels of identity

Create the file **`EnumCoreMethodsDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumCoreMethodsDemo {
    enum Direction {
        NORTH, EAST, SOUTH, WEST
    }

    public static void main(String[] args) {
        Direction[] first = Direction.values();
        Direction[] second = Direction.values();

        System.out.println("All = " + Arrays.toString(first));
        System.out.println("Name = " + Direction.EAST.name());
        System.out.println("Ordinal = " + Direction.EAST.ordinal());
        System.out.println("Parsed = " + Direction.valueOf("WEST"));
        System.out.println("Same constant = "
                + (Direction.valueOf("NORTH") == Direction.NORTH));

        System.out.println("Different arrays = " + (first != second));
        System.out.println("Same elements = "
                + (first[0] == second[0]));

        first[0] = Direction.SOUTH;
        System.out.println("First array changed = "
                + Arrays.toString(first));
        System.out.println("New values unchanged = "
                + Direction.values()[0]);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EnumCoreMethodsDemo.java
java EnumCoreMethodsDemo
~~~

**Exact stdout:**

~~~text
All = [NORTH, EAST, SOUTH, WEST]
Name = EAST
Ordinal = 1
Parsed = WEST
Same constant = true
Different arrays = true
Same elements = true
First array changed = [SOUTH, EAST, SOUTH, WEST]
New values unchanged = NORTH
~~~

### 4.1. Reading the three comparisons carefully

- `first != second`: **array identity** is different.
- `first[0] == second[0]`: **enum constant identity** is the same.
- `Direction.valueOf("NORTH") == Direction.NORTH`: the lookup returns the canonical constant.

### 4.2. Why does the first array have SOUTH in two positions?

Initially, first is [NORTH, EAST, SOUTH, WEST]. Assigning `first[0] = Direction.SOUTH` turns first into [SOUTH, EAST, SOUTH, WEST]. Arrays allow repeated references. However, the enum declaration still has four distinct named constants; a new `Direction.values()` call still follows declaration order.

### 4.3. Why not print hashCode?

`Enum.hashCode()` is identity-based, yet its numeric value does not produce fixed output suitable for teaching enum methods. Tests should use `==` identity and declaration order rather than comparing hash codes.

## 5. `valueOf(String)` — exact lookup by name

Each enum type has an implicitly declared static method `valueOf(String)`. For example:

~~~java
Direction direction = Direction.valueOf("SOUTH");
~~~

The result is `Direction.SOUTH`, **not** a new Direction object.

### 5.1. Exact name, case-sensitive

`Direction.valueOf("EAST")` is valid. `Direction.valueOf("east")` does not automatically uppercase, and `Direction.valueOf("East")` does not automatically convert to EAST either.

If the name does not match a declared constant, the method throws **`IllegalArgumentException`**.

### 5.2. No automatic trimming

`Direction.valueOf("EAST ")` does not match `EAST` because of the trailing space. If input from a form/API contains whitespace, you need to normalize it explicitly before lookup, when business rules allow.

### 5.3. Null argument

`Direction.valueOf(null)` throws **`NullPointerException`**; it does not return null, does not return a special constant, and does not automatically pick a default value.

### 5.4. `valueOf()` uses `name()`, not `toString()`

If a constant overrides `toString()` to display "Undelivered", you still have to use the declared name such as `PENDING` when calling `valueOf`.

### 5.5. No partial lookup

`valueOf("RE")` does not automatically select `RED` or `READ` by prefix; `valueOf` is not a fuzzy parser and does not support aliases, lower-case, Vietnamese translations, or wildcards.

### 5.6. Exceptions are part of the contract

When input is untrusted, do not assume every string is valid. An API can:

- Let `IllegalArgumentException` propagate if invalid input is a programming error.
- Catch the exception and return `Optional<E>` if an unknown value is a normal case.
- Convert it into a domain validation error for HTTP 400.
- Map aliases through an explicit map to support external codes.
- Reject null with `Objects.requireNonNull` or return Optional.empty depending on the design.

Avoid catching all `RuntimeException`s and treating them as invalid input: this can mask bugs other than enum parsing.

## 6. `Enum.valueOf(Class<T>, String)` — the generic variant

In addition to `Direction.valueOf(String)` provided by the compiler for each enum, Java has a static generic method on `java.lang.Enum`:

~~~java
Direction result =
        Enum.valueOf(Direction.class, "EAST");
~~~

Conceptual form of the method:

~~~java
public static <T extends Enum<T>> T valueOf(
        Class<T> enumClass, String name)
~~~

Both APIs return the same constant when arguments are valid:

~~~java
Direction a = Direction.valueOf("EAST");
Direction b = Enum.valueOf(Direction.class, "EAST");
System.out.println(a == b); // true
~~~

### 6.1. When to use each form?

- **Enum type is known at compile time:** `Direction.valueOf("EAST")` is readable and concise.
- **Writing a generic utility for any enum type:** `Enum.valueOf(enumType, input)` is useful when you have a `Class<E>` token.

### 6.2. Type parameter and type safety

The `E extends Enum<E>` bound allows a generic utility to preserve the result type `E`, without needing to cast from Object. Do not unnecessarily erase type information with raw `Class` or unchecked casts.

### 6.3. Null class token

`Enum.valueOf(null, "EAST")` does not have a valid enum Class; do not use a null class token. A generic parser should validate the `Class<E>` argument. For a non-enum Class passed in via raw/unchecked code, the API cannot function as a valid enum lookup.

## 7. Complete program 2 — valid parsing, unknown, case, and null

Create the file **`EnumValueOfDemo.java`**:

~~~java
public class EnumValueOfDemo {
    enum Mode {
        READ_ONLY, EDIT
    }

    public static void main(String[] args) {
        Mode direct = Mode.valueOf("EDIT");
        Mode generic = Enum.valueOf(Mode.class, "READ_ONLY");

        System.out.println("Direct = " + direct);
        System.out.println("Generic = " + generic);
        System.out.println("Canonical = "
                + (direct == Mode.EDIT));

        try {
            Mode.valueOf("edit");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lowercase rejected");
        }

        try {
            Mode.valueOf("UNKNOWN");
        } catch (IllegalArgumentException ex) {
            System.out.println("Unknown rejected");
        }

        try {
            Mode.valueOf(null);
        } catch (NullPointerException ex) {
            System.out.println("Null rejected");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumValueOfDemo.java
java EnumValueOfDemo
~~~

**Exact stdout:**

~~~text
Direct = EDIT
Generic = READ_ONLY
Canonical = true
Lowercase rejected
Unknown rejected
Null rejected
~~~

### 7.1. Why catch specific exceptions?

`"edit"` and `"UNKNOWN"` are non-null Strings that do not match named constants, so `IllegalArgumentException` is used. `null` is a distinct invalid argument, so the code catches `NullPointerException`. The demo prints custom **stable** messages instead of printing raw exception messages that may vary across JVMs.

### 7.2. Default `toString()`

In the demo, Mode does not override toString, so `System.out.println(direct)` prints "EDIT". The next section will show that the printed name can differ from `name()` if toString is overridden.

### 7.3. Normalization must be intentional

If you want user input `" edit "` to be interpreted as EDIT, you can process it as:

~~~java
Mode parsed =
        Mode.valueOf(
                input.trim().toUpperCase(java.util.Locale.ROOT));
~~~

This is a **fragment**, assuming input is non-null and this style of normalization fits the domain. `Locale.ROOT` gives uppercasing more stable linguistic behavior than the default locale; however, normalization does not turn an unknown value into a valid one and can cause collisions when aliases differ. External protocol encoding can use a separate code mapping instead of relying on source names.

## 8. `name()` — declared name of an enum constant

`name()` is a **final instance method** inherited from `java.lang.Enum`. It returns the **exact identifier name** under which the constant was declared in source.

~~~java
enum Transport {
    TRAIN, BUS, AIRPLANE
}
~~~

`Transport.TRAIN.name()` returns `"TRAIN"`. For `Transport.AIRPLANE.name()`, the result is `"AIRPLANE"`.

### 8.1. Name is an identifier, not a display label

Enum names usually follow the uppercase + underscore naming convention, whereas the UI may need Vietnamese text, spaces, accents, or locale-dependent text. You should not force the UI display name to match the identifier.

You can add a `label` field:

~~~java
enum DeliveryStatus {
    PENDING("Chưa giao"),
    DELIVERED("Đã giao");

    private final String label;

    DeliveryStatus(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}
~~~

`DeliveryStatus.PENDING.name()` is still `"PENDING"`, while `label()` returns `"Chưa giao"`.

### 8.2. `name()` cannot be overridden

`Enum.name()` is declared final. An enum cannot redefine the `name()` method with the same signature to change the text:

~~~java
enum Broken {
    A;

    @Override
    public String name() { // Intentionally does not compile.
        return "Alias";
    }
}
~~~

If you want a custom name, use `label()`, `code()`, `displayName()`, or override `toString()` when appropriate.

### 8.3. Long-term text storage requires considering versioning

Using `name()` in a database/file is acceptable if you treat **the constant name as a protocol identifier and do not rename it arbitrarily**. If you rename an enum constant after the old string has already been persisted, `valueOf(oldName)` will fail when reading old data.

For external data with stability requirements, an explicit stable code field is usually safer:

~~~java
PENDING("P", "Chưa giao")
~~~

The Java constant name can be refactored while the stable code remains preserved according to the contract. Choosing between name and code must be consistent and have a migration strategy.

### 8.4. `name()` differs from `getDeclaringClass()`

`name()` tells you the **constant name**. `getDeclaringClass()` tells you the **enum type declaring the constant**. If a constant has its own class body, the constant's runtime class may be an anonymous subclass; that does not change `name()`.

## 9. `toString()` can differ from `name()`

By default, `Enum.toString()` returns the same content as `name()`. However, `toString()` is **not final** and can be overridden in an enum.

This is a major reason developers mistakenly use `valueOf(displayLabel)`.

### 9.1. Complete program 3 — name, display label, and valueOf

Create the file **`EnumNameToStringDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumNameToStringDemo {
    enum DeliveryStatus {
        PENDING("Chưa giao"),
        DELIVERED("Đã giao");

        private final String label;

        DeliveryStatus(String label) {
            this.label = label;
        }

        String label() {
            return label;
        }

        @Override
        public String toString() {
            return label;
        }
    }

    public static void main(String[] args) {
        DeliveryStatus status = DeliveryStatus.PENDING;

        System.out.println("name = " + status.name());
        System.out.println("toString = " + status.toString());
        System.out.println("label = " + status.label());
        System.out.println("values display = "
                + Arrays.toString(DeliveryStatus.values()));

        System.out.println("valueOf name = "
                + DeliveryStatus.valueOf("DELIVERED").name());

        try {
            DeliveryStatus.valueOf("Đã giao");
        } catch (IllegalArgumentException ex) {
            System.out.println("Display text rejected");
        }

        System.out.println("same name and display = "
                + status.name().equals(status.toString()));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumNameToStringDemo.java
java EnumNameToStringDemo
~~~

**Exact stdout:**

~~~text
name = PENDING
toString = Chưa giao
label = Chưa giao
values display = [Chưa giao, Đã giao]
valueOf name = DELIVERED
Display text rejected
same name and display = false
~~~

### 9.2. Which method does `Arrays.toString(values())` call?

`Arrays.toString(Object[])` builds a string from the representations of its elements, in this case using `toString()` on the enum constants. Therefore, the output consists of the labels, **not** the name() identifiers.

To get the list of identifier names, iterate and call `name()` directly:

~~~java
for (DeliveryStatus s : DeliveryStatus.values()) {
    System.out.println(s.name());
}
~~~

This is a fragment using the enum declared in the demo.

### 9.3. Why does `valueOf("Đã giao")` fail?

`valueOf` looks up the constant name `PENDING` or `DELIVERED`. It does not look up the string returned by `toString()`. If user input is a Vietnamese label, parse it through an application-defined mapping (and consider duplicate labels, localization, and case sensitivity).

### 9.4. When should you override `toString()`?

It can be useful for debug-friendly output or human-readable descriptions. However, if another library/API relies on `toString()` as an identifier (not the standard contract of `valueOf`), overriding it can cause surprises. Separating `name()`, `code()`, and `displayName()` explicitly is usually easier to maintain.

## 10. `ordinal()` — declaration position, starting from 0

`ordinal()` is a final instance method of `Enum`, returning an `int` corresponding to the **zero-based position** in the enum declaration.

With:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

results:

- `Priority.LOW.ordinal() == 0`
- `Priority.MEDIUM.ordinal() == 1`
- `Priority.HIGH.ordinal() == 2`

Relationship with `values()`:

~~~java
Priority[] all = Priority.values();

for (int i = 0; i < all.length; i++) {
    System.out.println(all[i].ordinal() == i);
}
~~~

Each line prints `true` for a normal enum declaration. The index in the values array in declaration order is the ordinal.

### 10.1. Not the number of instances created

`ordinal()` is not an instance count, not a constructor call count, and not a random ID. It is assigned according to the **constant declaration order** and does not change during execution for the same runtime enum type.

### 10.2. Changing the order changes the ordinal

Version 1:

~~~java
enum StatusV1 {
    OPEN, CLOSED
}
~~~

Version 2:

~~~java
enum StatusV2 {
    PENDING, OPEN, CLOSED
}
~~~

StatusV1.OPEN has ordinal 0; StatusV2.OPEN has ordinal 1.

This poses a risk if you persist `ordinal()` to a database: after upgrading and inserting a new constant, old data can map to a different status.

### 10.3. ordinal cannot be overridden

`Enum.ordinal()` is final. You cannot set a fixed custom ordinal by overriding the method. If you want a stable numeric code, create a `private final int code` and a `code()` method.

### 10.4. Purpose of ordinal in libraries

Ordinal is useful for **internal representations** such as enum-indexed arrays, `EnumSet`/`EnumMap`, and certain algorithms tied to declaration order when lifecycle/versioning is controlled. However, exposed persistence/public protocols should use stable identifiers or explicit mappings.

### 10.5. `compareTo()` uses natural order

Enum `compareTo` is based on relative ordinal order within the same enum type, not alphabetical string comparison. An enum constant at an earlier index is considered smaller in natural enum order.

Do not use `ordinal()` to infer business ranking if declaration order is not defined as the business order. An explicit weight/priority field can be clearer.

## 11. Complete program 4 — ordinal changes across version declarations

Create the file **`EnumOrdinalVersionDemo.java`**:

~~~java
public class EnumOrdinalVersionDemo {
    enum StatusV1 {
        OPEN("O"), CLOSED("C");

        private final String code;

        StatusV1(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    enum StatusV2 {
        PENDING("P"), OPEN("O"), CLOSED("C");

        private final String code;

        StatusV2(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        System.out.println("V1 OPEN ordinal = "
                + StatusV1.OPEN.ordinal());
        System.out.println("V2 OPEN ordinal = "
                + StatusV2.OPEN.ordinal());
        System.out.println("V1 OPEN code = "
                + StatusV1.OPEN.code());
        System.out.println("V2 OPEN code = "
                + StatusV2.OPEN.code());
        System.out.println("V2 PENDING ordinal = "
                + StatusV2.PENDING.ordinal());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumOrdinalVersionDemo.java
java EnumOrdinalVersionDemo
~~~

**Exact stdout:**

~~~text
V1 OPEN ordinal = 0
V2 OPEN ordinal = 1
V1 OPEN code = O
V2 OPEN code = O
V2 PENDING ordinal = 0
~~~

### 11.1. Why use two enum types in the demo?

Java cannot simultaneously run two different source definitions of the same enum class in a simple compilation. The demo uses StatusV1 and StatusV2 to **simulate** changes in order/constants between two versions.

The persistence takeaway remains the same: relying on index 0 of the previous version can cause data to map incorrectly in the next version, whereas code "O" still preserves the meaning OPEN if you maintain stable codes.

### 11.2. Stable codes also carry versioning responsibility

An explicit field `code="O"` is only stable if developers commit to not changing it or have a clear migration. Java does not automatically guarantee the uniqueness/stability of arbitrary business codes; you need to validate duplicates and write tests.

## 12. Relationship between `values()` and `ordinal()`

There is a fundamental invariant:

For every constant c in enum E, `E.values()[c.ordinal()] == c` holds true when using a fresh array from values in declaration order.

This is the foundation that allows EnumSet/EnumMap to represent data compactly.

### 12.1. Complete program 5 — iteration and EnumSet/EnumMap

Create the file **`EnumIterationCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumIterationCollectionsDemo {
    enum Stage {
        NEW, RUNNING, DONE
    }

    public static void main(String[] args) {
        for (Stage stage : Stage.values()) {
            System.out.println(
                    stage.name() + ":" + stage.ordinal());
        }

        EnumSet<Stage> selected =
                EnumSet.of(Stage.DONE, Stage.NEW);

        EnumMap<Stage, Integer> order =
                new EnumMap<>(Stage.class);
        order.put(Stage.DONE, 3);
        order.put(Stage.RUNNING, 2);
        order.put(Stage.NEW, 1);

        System.out.println("Set = " + selected);
        System.out.println("Map = " + order);
        System.out.println("Index matches = "
                + (Stage.values()[Stage.RUNNING.ordinal()]
                        == Stage.RUNNING));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumIterationCollectionsDemo.java
java EnumIterationCollectionsDemo
~~~

**Exact stdout:**

~~~text
NEW:0
RUNNING:1
DONE:2
Set = [NEW, DONE]
Map = {NEW=1, RUNNING=2, DONE=3}
Index matches = true
~~~

### 12.2. Why do Set/Map have that order?

`EnumSet` and `EnumMap` iterate in natural enum order, i.e., **declaration order**, not insertion order. `EnumSet.of(DONE, NEW)` still displays [NEW, DONE]. `EnumMap` also iterates over keys in enum order.

This differs from HashMap/HashSet, where you should not rely on a stable iteration order unless the collection type has an appropriate contract.

### 12.3. Scope limitations

An `EnumMap<Stage,Integer>` has keys belonging to the Stage enum itself. You cannot add a dynamic Stage constant. If the requirement is arbitrary strings, an ordinary Map keyed by stable codes may be more appropriate.

## 13. Parsing by name differs from parsing by business code

In a real-world domain, an API might receive:

~~~text
"ready"
"in_progress"
"done"
~~~

while Java enum constants have names:

~~~java
READY, RUNNING, DONE
~~~

You should not force external identifiers to be written identically to Java enum names, especially when dealing with mobile clients, multi-version APIs, legacy databases, or localization.

### 13.1. Using an explicit code field

~~~java
enum WorkflowState {
    READY("ready"),
    RUNNING("in_progress"),
    DONE("done");

    private final String code;

    WorkflowState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

This is a declaration fragment. Each constant has a stable external code managed by the application. The code `"in_progress"` is not the same as `RUNNING.name()`, nor the same as `RUNNING.ordinal()`.

### 13.2. Lookup map after constants are initialized

You can create `Map<String,WorkflowState>` in static initialization:

~~~java
private static final Map<String, WorkflowState> BY_CODE;

static {
    Map<String, WorkflowState> map = new HashMap<>();
    for (WorkflowState state : values()) {
        if (map.putIfAbsent(state.code, state) != null) {
            throw new IllegalStateException("Duplicate code");
        }
    }
    BY_CODE = Map.copyOf(map);
}
~~~

This is an enum-member fragment, with `Map`/`HashMap` imports. Building the lookup after the constants are initialized avoids dependency-order surprises. `Map.copyOf` gives an unmodifiable map structure via BY_CODE; Strings/enums are also suitable as immutable map keys/values.

### 13.3. Unknown input must be handled explicitly

If the external code is not in the map, you can return `Optional.empty()`, a domain error, or another explicit UNKNOWN representation if the data model has one. Do not use `valueOf()` to "create a custom enum case".

### 13.4. Null input and Map lookup

Do not assume every Map implementation accepts `get(null)`. For example, unmodifiable maps from `Map.copyOf` do not support null keys. If the parser contract treats null as missing, check for null **before lookup**.

## 14. Complete program 6 — looking up stable codes with Optional

Create the file **`EnumStableCodeDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class EnumStableCodeDemo {
    enum WorkflowState {
        READY("ready"),
        RUNNING("in_progress"),
        DONE("done");

        private final String code;
        private static final Map<String, WorkflowState> BY_CODE;

        static {
            Map<String, WorkflowState> map = new HashMap<>();

            for (WorkflowState state : values()) {
                WorkflowState old =
                        map.putIfAbsent(state.code, state);
                if (old != null) {
                    throw new IllegalStateException("Duplicate code");
                }
            }

            BY_CODE = Map.copyOf(map);
        }

        WorkflowState(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }

        static Optional<WorkflowState> fromCode(String code) {
            if (code == null) {
                return Optional.empty();
            }
            return Optional.ofNullable(BY_CODE.get(code));
        }
    }

    public static void main(String[] args) {
        System.out.println("Name = "
                + WorkflowState.RUNNING.name());
        System.out.println("Code = "
                + WorkflowState.RUNNING.code());
        System.out.println("Lookup = "
                + WorkflowState.fromCode("in_progress"));
        System.out.println("Unknown = "
                + WorkflowState.fromCode("RUNNING"));
        System.out.println("Null = "
                + WorkflowState.fromCode(null));
        System.out.println("Canonical = "
                + (WorkflowState.fromCode("done").orElseThrow()
                        == WorkflowState.DONE));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
~~~

**Exact stdout:**

~~~text
Name = RUNNING
Code = in_progress
Lookup = Optional[RUNNING]
Unknown = Optional.empty
Null = Optional.empty
Canonical = true
~~~

### 14.1. Why is `fromCode("RUNNING")` Optional.empty?

BY_CODE uses `"in_progress"` as the key for WorkflowState.RUNNING. `"RUNNING"` is `name()`, not `code()`. The `fromCode` method does not automatically fall back to Java identifiers.

### 14.2. Why does `Optional[RUNNING]` not display the external code?

`Optional.toString()` represents the contained enum object using `toString()`; the enum in the demo does not override toString, so it displays `RUNNING`. Do not infer that Optional uses the String code map key.

### 14.3. Checking for duplicate codes

The static initializer uses `putIfAbsent` to detect two constants carrying the same code. Without this check, Map.put could silently overwrite, causing an external code input to no longer resolve uniquely.

### 14.4. Trade-off

A lookup map takes slightly more memory, yet provides direct lookup by external code without scanning values() every time. For small enums and infrequent parsing, a simple for loop may also suffice; the choice depends on clarity, validation, and workload.

## 15. Variant using `Class<E>` for generic code

When a framework handles many different enum types, we can write a generic utility with `Class<E>`.

`Class.getEnumConstants()` returns an array of the enum constants of the corresponding enum class, or null if the Class does not represent an enum type. This is useful when you have a type token at runtime instead of knowing `SomeEnum.values()` directly at compile time.

### 15.1. Complete program 7 — generic utility

Create the file **`EnumGenericUtilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class EnumGenericUtilityDemo {
    enum Role {
        VIEWER, EDITOR
    }

    enum Severity {
        LOW, HIGH
    }

    static <E extends Enum<E>> List<String> names(Class<E> type) {
        E[] constants = type.getEnumConstants();
        if (constants == null) {
            throw new IllegalArgumentException("Not an enum class");
        }

        List<String> result = new ArrayList<>();
        for (E value : constants) {
            result.add(value.name());
        }
        return List.copyOf(result);
    }

    static <E extends Enum<E>> E lookup(
            Class<E> type, String name) {
        return Enum.valueOf(type, name);
    }

    public static void main(String[] args) {
        System.out.println("Roles = " + names(Role.class));
        System.out.println("Severities = " + names(Severity.class));

        Role chosen = lookup(Role.class, "EDITOR");
        System.out.println("Role = " + chosen);
        System.out.println("Same instance = "
                + (chosen == Role.EDITOR));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumGenericUtilityDemo.java
java EnumGenericUtilityDemo
~~~

**Exact stdout:**

~~~text
Roles = [VIEWER, EDITOR]
Severities = [LOW, HIGH]
Role = EDITOR
Same instance = true
~~~

### 15.2. Why is `<E extends Enum<E>>` needed?

The generic bound lets Java preserve the association between type E and the enum class Class<E>. The `lookup` method returns the exact type E via compile-time type inference, avoiding raw casts. It does not allow an arbitrary non-enum class to pass as a valid generic parameter.

### 15.3. Return value of `names`

The method collects `name()` into a List and uses `List.copyOf` to return an unmodifiable List snapshot. If it returned an ArrayList directly, the caller could mutate the List yet still could not change the enum declaration; however, an immutable return API signals to the caller that it is a fixed descriptive list.

### 15.4. Not every generic API should use reflection

If you are only handling one specific enum, calling `Role.values()` or `Role.valueOf(...)` directly is more readable. `Class<E>` and `getEnumConstants()` are appropriate when the code genuinely needs to handle multiple enum types.

## 16. Constant-specific class bodies do not break `name()` and `ordinal()`

An enum constant can declare its own class body to override an instance method:

~~~java
enum Operation {
    PLUS {
        @Override
        String symbol() {
            return "+";
        }
    },
    TIMES {
        @Override
        String symbol() {
            return "*";
        }
    };

    abstract String symbol();
}
~~~

The Java compiler may generate anonymous constant-specific subclasses. `PLUS.getClass()` is then not necessarily equal to `Operation.class`, yet:

- `PLUS.name()` is still `"PLUS"`.
- `PLUS.ordinal()` is still 0.
- `TIMES.name()` is still `"TIMES"`.
- `TIMES.ordinal()` is still 1.
- `Operation.values()` still returns the two constants in declaration order.
- `Operation.valueOf("PLUS")` still returns the canonical PLUS constant.
- `PLUS.getDeclaringClass()` is still `Operation.class`.

**Do not confuse a constant's runtime implementation class with its declaring enum type.**

### 16.1. What is `getDeclaringClass()` used for?

`Enum.getDeclaringClass()` returns the Class object of the enum type that actually declared the constant. When a constant has a class body, `getClass()` returns the anonymous subclass, so `getDeclaringClass()` is more reliable for identifying the constant's enum type.

### 16.2. Subclasses cannot be used to add names/ordinals

Clients cannot create an arbitrary subclass and add `PLUS2`. The set of enum constants remains closed in the declaration, so the methods above have fixed semantics for each compiled enum version.

## 17. Complete program 8 — constant-specific behavior and metadata

Create the file **`EnumConstantBodyMethodsDemo.java`**:

~~~java
public class EnumConstantBodyMethodsDemo {
    enum Operation {
        PLUS {
            @Override
            String symbol() {
                return "+";
            }
        },
        TIMES {
            @Override
            String symbol() {
                return "*";
            }
        };

        abstract String symbol();
    }

    public static void main(String[] args) {
        Operation plus = Operation.PLUS;

        System.out.println("name = " + plus.name());
        System.out.println("ordinal = " + plus.ordinal());
        System.out.println("symbol = " + plus.symbol());
        System.out.println("same class = "
                + (plus.getClass() == Operation.class));
        System.out.println("declaring class = "
                + plus.getDeclaringClass().getSimpleName());
        System.out.println("parsed identity = "
                + (Operation.valueOf("PLUS") == plus));
        System.out.println("values length = "
                + Operation.values().length);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumConstantBodyMethodsDemo.java
java EnumConstantBodyMethodsDemo
~~~

**Exact stdout:**

~~~text
name = PLUS
ordinal = 0
symbol = +
same class = false
declaring class = Operation
parsed identity = true
values length = 2
~~~

### 17.1. There are two different kinds of "names"

`plus.name()` returns the named constant PLUS. `plus.getDeclaringClass().getSimpleName()` returns the enum type name Operation. If the goal is to store a reference containing both the enum type and the enum constant name, inspect both instead of using the raw runtime subclass name.

### 17.2. Avoid hard-coding synthetic class names

The compiler may generate class files like `Operation$1` for a constant body, yet synthetic artifact names are not a stable public API. Do not persist or compare them in business code.

### 17.3. Why is ordinal still 0?

Ordinal follows **the constant's position in the declaration**, independent of whether the constant has its own class body or overrides a method.

## 18. Combining the four APIs with switch in Java 17

An enum type has a set of declared constants that makes `switch` readable and able to exhaustively cover all cases.

~~~java
enum Signal {
    STOP, WAIT, GO
}

static String instruction(Signal signal) {
    return switch (signal) {
        case STOP -> "stop";
        case WAIT -> "wait";
        case GO -> "move";
    };
}
~~~

These are declaration/method fragments (not yet a standalone file). `switch` uses enum constant cases, without needing `ordinal()` or `name()` as an intermediate key.

### 18.1. Do not switch on ordinal if you want readability

Code such as:

~~~java
switch (signal.ordinal()) {
    case 0 -> ...
    case 1 -> ...
}
~~~

is error-prone when constants are reordered. Switch directly on enum values. If you need custom stable numeric codes, parse the code into an enum first and then switch on the enum.

### 18.2. With a switch expression, exhaustive cases are required

In Java 17, a switch expression on an enum may not require `default` if it covers every constant according to the compiler's exhaustiveness rules. If you add a new constant in a later version, recompiling the code can require adding a new case. This is a benefit of an enum as a closed set of cases.

### 18.3. Null still needs to be handled

`null` is not an enum constant. In Java 17, a switch expression with null is not handled as a regular enum constant case and typically throws a `NullPointerException` if null has not been checked. If the API allows a missing value, handle it before the switch.

## 19. Complete program 9 — switching on an enum, without using ordinal

Create the file **`EnumSwitchDemo.java`**:

~~~java
public class EnumSwitchDemo {
    enum Signal {
        STOP, WAIT, GO
    }

    static String instruction(Signal value) {
        if (value == null) {
            return "missing";
        }

        return switch (value) {
            case STOP -> "stop";
            case WAIT -> "wait";
            case GO -> "move";
        };
    }

    public static void main(String[] args) {
        for (Signal value : Signal.values()) {
            System.out.println(
                    value.name() + " => " + instruction(value));
        }

        System.out.println("Null => " + instruction(null));
        System.out.println("Parse => "
                + instruction(Signal.valueOf("GO")));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumSwitchDemo.java
java EnumSwitchDemo
~~~

**Exact stdout:**

~~~text
STOP => stop
WAIT => wait
GO => move
Null => missing
Parse => move
~~~

### 19.1. Why do case names not need `Signal.STOP`?

In a switch on an enum type, case labels have syntax specifically for enum constants. The compiler knows the type from the switch expression, so you can write `case STOP`.

### 19.2. Why not write `case 0`?

Signal is an enum type, not an int. `ordinal()` is a field-like method returning an int for metadata/ordering; it does not turn an enum into a numeric primitive.

## 20. Pitfalls with an enum that has no constants

Java allows declaring an enum **with no constants**:

~~~java
enum Empty {
    ;
}
~~~

`Empty.values()` returns an array of length 0. `Empty.valueOf("ANY")` will throw IllegalArgumentException because there are no named constants. There is no valid `Empty` instance on which to call `name()` or `ordinal()`.

### 20.1. Why do empty enums exist?

In some patterns, an empty enum can serve as a non-instantiable namespace/container for static utility methods or as a type defined before variants exist, yet for the purpose of business enumerated states, an empty enum is usually not useful.

### 20.2. Do not assume a first element always exists

`E.values()[0]` can throw ArrayIndexOutOfBoundsException if enum E is empty. When writing generic enum utilities, check the length before accessing the first element or handle the empty case.

### 20.3. Cannot call `new Empty()` to create the first constant

Empty is an enum and is still subject to restrictions on instance creation; you cannot add elements with new.

## 21. Static initialization and `values()`

Enum constants are initialized in a special order when enum class initialization occurs. With field metadata in constructors and static lookup maps, it is necessary to understand initialization ordering.

### 21.1. Building a map after constants exist

A correct pattern:

~~~java
enum Code {
    A("a"),
    B("b");

    final String text;
    private static final java.util.Map<String, Code> LOOKUP;

    static {
        java.util.Map<String, Code> tmp = new java.util.HashMap<>();
        for (Code c : values()) {
            tmp.put(c.text, c);
        }
        LOOKUP = java.util.Map.copyOf(tmp);
    }

    Code(String text) {
        this.text = text;
    }
}
~~~

The static block runs after enum constant initialization, so `values()` can be used to build the table.

### 21.2. Do not access the enum's own nonconstant static field from a constructor

Java has a special restriction: an enum constructor/instance initializer/instance variable initializer must not directly reference a static field of the enum itself unless the field is a constant variable.

Intentionally does not compile:

~~~java
enum Bad {
    A, B;

    static int created;

    Bad() {
        created++; // Illegal reference to static field from enum initializer.
    }
}
~~~

If you need the count of constants, `values().length` in a static context is the clear way. If you need a mutable runtime metric, choose a holder/service with a lifecycle and concurrency policy instead of forcing the enum constructor to interfere with its own static field.

### 21.3. Avoid static initialization cycles

Although the rules guard against some situations, static initialization can become complex if multiple classes/enums call each other before class initialization completes. Keep metadata constructors simple, keep fields immutable when possible, and build lookup tables after constants.

## 22. Performance and cost of the four APIs

| API | Typical cost implications | What to do |
| --- | --- | --- |
| `values()` | Creates an array containing references to all constants, copies the list of refs in O(n) | For hot paths and large enums, consider caching an immutable view |
| `valueOf(name)` | Looks up in enum constants metadata/map, returns existing constant | Use directly for exact-name lookup |
| `name()` | Returns the constant's String name metadata | Use when you need the declared identifier |
| `ordinal()` | Returns the position int metadata | Use internally for declaration order, avoid as a persistence ID |

Do not optimize prematurely. Enums are usually small; `values()` in setup code, tests, or UI operations is not a hotspot to worry about. Prioritize correctness and clarity first.

### 22.1. `values()` in nested loops

If you need to iterate multiple times, you can:

~~~java
Direction[] directions = Direction.values();
for (int i = 0; i < 100; i++) {
    for (Direction direction : directions) {
        // Do something with each direction.
    }
}
~~~

This is a fragment. It only calls values once. However, do not expose the `directions` mutable array in a public API if you want to prevent callers from modifying the order/contents of the refs.

### 22.2. `name()` is not free localization

If you map name to a translation every time the UI renders, you can use `ResourceBundle`/a localization service per locale. An enum name is only a stable identifier in compiled source until a developer changes the code.

### 22.3. `ordinal()` does not offer enough speed to justify sacrificing schema stability

Although ordinal is a convenient int for array indexing, using it as an external ID can cause costly migration bugs when constants are reordered. Choose an explicit code whenever data crosses the boundary of a compiled code version.

## 23. Common mistakes and how to fix them

1. **Thinking `values()` returns a List.** It actually returns an `E[]` array; use `Arrays.asList`/`List.of` when appropriate List semantics are needed.
2. **Thinking `values()` creates new enum objects.** It returns a new array containing canonical references.
3. **Modifying the `values()` array and thinking the enum declaration changed.** Only the caller-owned array is modified.
4. **Thinking `valueOf()` parses lowercase automatically.** Exact case-sensitive match.
5. **Thinking `valueOf()` trims input.** No; spaces make the string different.
6. **Passing null to `valueOf()` and expecting it to return null.** It throws NullPointerException.
7. **Thinking `valueOf("UNKNOWN")` creates an unknown enum constant.** No; IllegalArgumentException.
8. **Passing a label from `toString()` into `valueOf()`.** Lookup uses the declared name().
9. **Assuming `name()` can be overridden.** It is final.
10. **Assuming `ordinal()` can be overridden into a business ID.** It is final.
11. **Using ordinal as a database ID.** Reordering or inserting constants changes the mapping.
12. **Unconditionally using `toString()` as a stable protocol ID.** It can be overridden/localized.
13. **Using `name()` as a protocol but renaming constants without migration.** Old data may fail to parse.
14. **Using `ordinal()` to switch.** Switching directly on enum values is clearer and less error-prone.
15. **Thinking `ordinal()` is the number of times an enum instance was created.** It is the declaration position.
16. **Thinking `EnumSet`/`EnumMap` iterate in insertion order.** They use natural enum order.
17. **Using `HashMap` and expecting natural enum order.** Choose EnumMap if keys are enums and the semantics fit.
18. **Assuming `getClass() == E.class` is true for every constant.** Constant-specific bodies have anonymous subclasses.
19. **Not using `getDeclaringClass()` when you need the enum declaring type.** That is the API for that exact purpose.
20. **Trying to create an enum with `new` in a factory.** Impossible; only existing constants can be selected.
21. **Forgetting that an enum variable can be null.** `name()/ordinal()` on null throws NPE.
22. **Calling `values()[0]` on an empty enum.** Can throw ArrayIndexOutOfBoundsException.
23. **Returning a mutable cached values array to callers.** Can corrupt the application cache.
24. **Not checking for duplicate stable codes in a lookup map.** The parser may map incorrectly.
25. **Using Map.copyOf and calling get(null) without checking.** Those unmodifiable maps do not accept a null key.
26. **Catching all RuntimeExceptions when parsing.** This easily hides other bugs; catch specifically IllegalArgumentException for unknown values and handle null separately.
27. **Creating heavy allocations to micro-optimize in the wrong place.** Use profiling if performance is a real requirement.
28. **Not considering source versioning when adding/renaming constants.** Exhaustive switches and persisted names need review.
29. **Thinking generic Enum.valueOf and E.valueOf have different lookup semantics.** Both return the canonical constant by declared name.
30. **Not distinguishing between enum name, display text, external stable code, and ordinal.** Four concepts serve four different needs.

## 24. API decision table by scenario

| Scenario | Appropriate choice | Avoid confusion |
| --- | --- | --- |
| Displaying all enum choices on a form | `E.values()` to iterate over constants | Values returns an array, not a runtime registry |
| Reading a value written by code/config using the exact Java constant name | `E.valueOf(name)` | Must be exact and case-sensitive |
| Writing a parser supporting multiple enum types | `Enum.valueOf(Class<E>, name)` | Needs a type token and validation |
| Getting the source identifier name for logging/debugging | `constant.name()` | Not a localized display label |
| Displaying a user-friendly name | `label()/displayName()` or localization | Do not rely on name/ordinal |
| Sorting by declaration order | `values()`/natural enum ordering | Order changes if the declaration is reordered |
| Using ordinal to index an internal table of the same enum version | `constant.ordinal()` when truly needed | Do not persist ordinal long-term |
| Persisting a stable ID across deployments | Explicit `code()`/mapping | Do not use ordinal |
| Parsing a stable external code | `fromCode` via a Map | Do not depend on source enum names |
| Comparing for the same constant | `==` | No need for value-based custom equals |
| Enum constant with its own class body | `getDeclaringClass()` for the declaring enum | `getClass()` can differ |
| Empty set of constants | `values().length == 0` | Do not access values()[0] |

## 25. Practice exercises with answers

**Question 1.** How many elements does `enum E {A, B, C}` have in `E.values()`?

**Answer:** Three, in order A, B, C according to declaration order.

**Question 2.** What is `E.A.ordinal()`?

**Answer:** 0.

**Question 3.** What is `E.C.ordinal()`?

**Answer:** 2.

**Question 4.** What does calling `E.values() == E.values()` return?

**Answer:** False, because each call returns a separate array object.

**Question 5.** What does `E.values()[0] == E.A` return?

**Answer:** True.

**Question 6.** Does modifying `E[] arr = E.values(); arr[0]=E.C;` change the declaration?

**Answer:** No, only the array arr is modified; a new values() call still starts with A.

**Question 7.** What does `E.valueOf("B") == E.B` return?

**Answer:** True.

**Question 8.** Does `E.valueOf("b")` automatically uppercase to B?

**Answer:** No, it throws IllegalArgumentException.

**Question 9.** Does `E.valueOf(" B ")` automatically trim?

**Answer:** No; it does not match the name and throws IllegalArgumentException.

**Question 10.** Does `E.valueOf(null)` return null?

**Answer:** No, it throws NullPointerException.

**Question 11.** Does `E.valueOf("UNKNOWN")` create a new enum constant?

**Answer:** No, it throws IllegalArgumentException.

**Question 12.** What does `E.A.name()` return?

**Answer:** The String "A", which is the declared constant identifier.

**Question 13.** Can `name()` be overridden to return a label?

**Answer:** No, the method is final.

**Question 14.** Can `toString()` be overridden?

**Answer:** Yes; in that case `toString()` can differ from `name()`.

**Question 15.** If toString returns "Đẹp", does `valueOf("Đẹp")` look up that constant?

**Answer:** No, if "Đẹp" is not the declared constant name itself. `valueOf` uses the declared name.

**Question 16.** Is `ordinal()` the chronological creation order of objects?

**Answer:** No, it is the zero-based declaration index.

**Question 17.** If a new constant is inserted at the beginning of an enum, do the ordinals of subsequent constants change?

**Answer:** Yes, when the new enum version is compiled.

**Question 18.** Should ordinal be used as a permanent DB code?

**Answer:** No, use an explicit stable code if persistence is needed.

**Question 19.** Does `Enum.valueOf(E.class, "B")` return the same object as `E.valueOf("B")`?

**Answer:** Yes, the same canonical constant.

**Question 20.** When writing a generic enum utility, what does `<T extends Enum<T>>` help with?

**Answer:** It preserves type safety between the Class<T> token and the looked-up value T.

**Question 21.** Does `EnumMap` iterate in insertion order?

**Answer:** No; it uses natural enum order according to declaration order.

**Question 22.** In what order does `EnumSet.of(C, A)` typically iterate in `enum E{A,B,C}`?

**Answer:** [A, C].

**Question 23.** Can a constant-specific enum class body cause `constant.getClass()` to differ from E.class?

**Answer:** Yes, due to the compiler-generated anonymous subclass.

**Question 24.** When you need the enum type of a constant, what should you use?

**Answer:** `constant.getDeclaringClass()`.

**Question 25.** Does `name()` of a constant with its own body change according to the subclass name?

**Answer:** No, it is still the named constant.

**Question 26.** Is `ordinal()` of a constant with its own body reset by the anonymous subclass?

**Answer:** No, it still follows the order of constants in the declaring enum.

**Question 27.** For an empty enum, what does `values().length` return?

**Answer:** 0.

**Question 28.** For an empty enum, is `values()[0]` valid?

**Answer:** It can compile, yet throws ArrayIndexOutOfBoundsException at runtime.

**Question 29.** Does using `List.copyOf` on a list containing mutable element objects deep-copy the objects?

**Answer:** No. It is a structural copy, so mutable elements must be considered separately.

**Question 30.** Does using a stable code field exempt you from checking uniqueness?

**Answer:** No, code uniqueness/migration is a business invariant that must be ensured.

**Question 31.** Why should you not catch a broad RuntimeException when parsing?

**Answer:** It can mask other code bugs; distinguish between an unknown name and null/input validation.

**Question 32.** If you want to display a Vietnamese enum label and persist a stable code, can you use `ordinal()` for them as well?

**Answer:** You should not; create separate `displayName` and `code` fields, and keep ordinal for the declaration position.

## 26. Hands-on exercises with hints

### Exercise 1 — reading metadata without changing constants

Write the enum `MonthPart {START, MIDDLE, END}` and use `values()` to print them in order. Inspect `name()` and `ordinal()`. Next, replace the first element in the array returned by values; call values a second time and explain why the source constants do not change.

**Hint:** Separate the identity of the array from the identity of the enum constant. Use `==` to test references and `Arrays.toString` to list values.

### Exercise 2 — parser accepting case-insensitive input

Write `parseMode(String input)` that accepts `" on "` and returns `Mode.ON`. Test null/blank/unknown inputs. Do not change the semantics of `Mode.valueOf`; normalize **before** calling it and handle invalid values separately.

**Hint:** `trim()`, `toUpperCase(Locale.ROOT)`, and try/catch `IllegalArgumentException`. If input=null, reject or return Optional.empty according to the contract.

### Exercise 3 — stable external code

Write the enum `PaymentState` with names `PENDING`/`PAID`/`FAILED` and stable codes `P`/`D`/`F`. Create a lookup Map, validate duplicate codes, and try refactoring display labels without changing the code mapping.

**Hint:** The static Map is built after the constants; each code is an immutable String field.

### Exercise 4 — ordinal regression test

Create a test for the enum `Severity`, asserting `Severity.HIGH.ordinal()==2` when the order is LOW, MEDIUM, HIGH. Next, insert INFO before LOW. Observe the test fail; replace the persistence use case with an explicit stable code.

**Hint:** Do not rely on an ordinal test as the basis for a business ID if you want the declaration order to be changeable.

### Exercise 5 — enum with constant-specific bodies

Create an Operation enum with ADD/SUB having their own apply methods. Print `name()`, `ordinal()`, `getClass()==Operation.class`, and `getDeclaringClass()==Operation.class`. Explain which part reflects constant identity and which part reflects the compiler-generated implementation class.

**Hint:** A constant-specific body does not add new named enum instances.

## 27. Checklist for using enum APIs in projects

1. Have you distinguished `values()` returning an array from `valueOf()` returning one constant?
2. Do you understand that `values()` returns a new array while its elements are canonical references?
3. Do you use `==` when checking for the same enum constant?
4. Do you handle nullable enum variables before calling name()/ordinal()?
5. Do you rely on the declaration order of values within the appropriate scope?
6. Do you avoid mutating a cached mutable array in a way that affects the global cache?
7. Are you aware that `valueOf()` performs an exact case-sensitive lookup?
8. Do you trim/normalize input only when the business contract allows it?
9. Do you handle an unknown name with IllegalArgumentException properly?
10. Do you handle a null name explicitly?
11. Do you use `Enum.valueOf(Class<E>,name)` when a generic utility needs a type token?
12. Do you distinguish `name()` from `toString()` and display labels?
13. Do you avoid trying to override the final methods name()/ordinal()?
14. Do you remember that ordinal starts at 0 and changes when constants are reordered?
15. Do you avoid using ordinal as a stable DB ID?
16. Do you have explicit stable codes if an external protocol requires them?
17. Do you validate duplicate codes/unknown codes in the code-map parser?
18. Do you distinguish EnumMap/EnumSet iteration order from HashMap/HashSet?
19. Do you switch directly on the enum instead of on ordinal?
20. Are you aware that a constant-specific subclass makes getClass differ from getDeclaringClass?
21. Do you handle empty enums when writing generic utilities?
22. Do you avoid persisting compiler synthetic class names?
23. Do you consider versioning when renaming/adding enum constants?
24. Do you avoid unprofiled micro-optimization for values()?
25. Do you have unit tests for exact names, codes, unknown/null inputs, and ordinal migration risks?

## 28. Conclusion

The four familiar enum APIs have four clear responsibilities:

- **`values()`:** lists the named constants in declaration order; returns **a new array** containing **references to the existing constants**.
- **`valueOf(name)`:** looks up the exact **declared constant name**; returns the canonical enum instance, is case-sensitive, throws IllegalArgumentException on unknown values, and throws NullPointerException on null.
- **`name()`:** gets the constant's identifier name; a final method, unaffected by overriding toString.
- **`ordinal()`:** gets the zero-based declaration position; a final method, useful for ordering/implementation details yet **not a stable external ID**.

Do not conflate **source name**, **display label**, **external stable code**, **declaration index**, and **runtime object identity** into one concept. For the UI, use labels/localization; for parsing declared names, use valueOf; for long-term storage, choose a validated stable code; for iterating over constants, use values; and for natural enum order, understand ordinal properly without letting it leak into a fragile database contract.

That is how to use enums in a way that is both valid in Java 17+ syntax and easy to maintain as source code and application data change over time.
