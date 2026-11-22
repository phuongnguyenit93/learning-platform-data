# Identifying enums with isEnum and retrieving constants with getEnumConstants

## 1. Two different questions when you only have a Class

An enum represents a set of named constants, such as `LOW`, `NORMAL`, `HIGH`. When the type name is known directly in source code, you can call `Priority.values()` to iterate over the constants. However, a form generator, configuration reader, or data model inspector might only receive a `Class<?>` at runtime.

In that case, two methods on `Class` answer two questions:

- `isEnum()`: does this `Class` object describe a **class declared as an enum**?
- `getEnumConstants()`: what are the **actual enum constant objects** of that class?

Do not merge the two questions into one. Identifying a class as an enum is different from retrieving its constant objects. In particular, retrieving the constants may cause the enum to be initialized if it has not been initialized previously.

This lesson uses Java 17 or later and focuses on the two APIs above. Looking up constants by name, reading annotations on constants, or accessing fields inside an enum are different needs.

## 2. Contracts to remember

| API | Return type | Meaning |
| --- | --- | --- |
| `Class.isEnum()` | `boolean` | `true` when the class is declared as an enum |
| `Class<T>.getEnumConstants()` | `T[]` | Array of constants in **declaration order**, or `null` if the class is not an enum |

Two easily confused results:

- **Not an enum:** `getEnumConstants()` returns `null`.
- **Is an enum with no constants:** the method returns an array of length `0`.

An empty enum is valid, for example a standalone declaration:

~~~java
enum Empty {
}
~~~

Do not infer "not an enum" merely from having no elements. You must distinguish an empty array from `null`.

Common cases, assuming `enum Priority { LOW, NORMAL, HIGH }` is declared:

| Class object | isEnum() | getEnumConstants() |
| --- | --- | --- |
| `Priority.class` | `true` | Three constants `LOW`, `NORMAL`, `HIGH` |
| `Empty.class` | `true` | Empty array |
| `String.class` | `false` | `null` |
| `Enum.class` | `false` | `null` |
| `Priority[].class` | `false` | `null` |

`java.lang.Enum` is the common base class of enums, but it is not itself a class declared with the `enum` syntax. An array containing enums is also an array type, not an enum.

## 3. Complete example: identifying, listing, and handling an empty enum

Save as `EnumInspectionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class EnumInspectionDemo {
    enum Priority {
        LOW, NORMAL, HIGH
    }

    enum Empty {
    }

    static List<String> enumNames(Class<?> type) {
        Objects.requireNonNull(type, "type");
        if (!type.isEnum()) {
            throw new IllegalArgumentException("Expected an enum class");
        }

        List<String> names = new ArrayList<>();
        for (Object value : type.getEnumConstants()) {
            Enum<?> constant = (Enum<?>) value;
            names.add(constant.name());
        }
        return List.copyOf(names);
    }

    public static void main(String[] args) {
        Class<?> type = Priority.class;
        Object[] constants = type.getEnumConstants();

        System.out.println("isEnum=" + type.isEnum());
        System.out.println("constants=" + constants.length);
        for (Object value : constants) {
            Enum<?> constant = (Enum<?>) value;
            System.out.println(constant.name() + ":" + constant.ordinal());
        }

        System.out.println("sameFirst=" + (constants[0] == Priority.LOW));

        Priority[] typed = Priority.class.getEnumConstants();
        System.out.println("typedSecond=" + typed[1].name());

        System.out.println("empty.isEnum=" + Empty.class.isEnum());
        System.out.println("empty.length="
                + Empty.class.getEnumConstants().length);
        System.out.println("String.isEnum=" + String.class.isEnum());
        System.out.println("String.constants="
                + String.class.getEnumConstants());
        System.out.println("Enum.isEnum=" + Enum.class.isEnum());
        System.out.println("array.isEnum=" + Priority[].class.isEnum());
        System.out.println("names=" + enumNames(type));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 EnumInspectionDemo.java
java EnumInspectionDemo
~~~

Exact output:

~~~text
isEnum=true
constants=3
LOW:0
NORMAL:1
HIGH:2
sameFirst=true
typedSecond=NORMAL
empty.isEnum=true
empty.length=0
String.isEnum=false
String.constants=null
Enum.isEnum=false
array.isEnum=false
names=[LOW, NORMAL, HIGH]
~~~

What the program demonstrates:

1. Iterating with `getEnumConstants()` preserves the order `LOW`, `NORMAL`, `HIGH`, matching the declaration order.
2. The first element is `Priority.LOW` itself, not a new copy of that constant.
3. With `Class<Priority>`, the result is typed as `Priority[]`. With `Class<?>`, you can iterate through `Object[]` and then handle elements according to the enum contract.
4. An empty enum can still be identified with `isEnum()`.
5. The `enumNames` method rejects non-enum inputs, rather than turning invalid input into an empty list that is hard to distinguish.

The cast to `Enum<?>` in `enumNames` relies on the condition already checked: `type` is an enum class and the elements are retrieved directly from `type.getEnumConstants()`. Do not apply that cast to an arbitrary `Object[]` array.

In `main`, `type` is assigned directly from `Priority.class`, so the program knows for certain that the result is non-`null`. If you receive `Class<?>` from elsewhere, check it as `enumNames` does before iterating.

## 4. Declaration order, names, and labels

`getEnumConstants()` returns constants in **declaration order**. `ordinal()` is the zero-based position; `name()` returns the declared name, whereas `toString()` may be overridden to produce a display label. Therefore, tools that need exact name keys should use `name()`, and tools that need a different order must sort the results themselves for display.

Do not store `ordinal()` as a durable business code: adding or reordering constants can change positions. Sorting the `getEnumConstants()` array locally also does not change the actual order of the enum. The next lesson examines sorting, ordering, and the difference between an empty array and `null` in detail.

## 5. When an enum constant has a constant-specific class body

An enum constant can declare a constant-specific class body to override behavior; the runtime class of the object is then an **anonymous subclass**, so `constant.getClass().isEnum()` can return `false`. This does not negate the fact that the object is an enum constant. Once you have an `Enum<?>`, use `constant.getDeclaringClass()` to obtain the **declaring enum class** and then call `getEnumConstants()`.

Standalone example of the difference:

~~~java
enum Mode {
    FAST {
        @Override public String toString() { return "Fast mode"; }
    },
    SAFE
}

Enum<?> constant = Mode.FAST;
System.out.println(constant.getClass().isEnum());          // false
System.out.println(constant.getDeclaringClass().isEnum()); // true
System.out.println(constant.getDeclaringClass() == Mode.class); // true
~~~

The statements after the `Mode` declaration are an illustrative snippet that must be placed inside an appropriate method or block; the `SAFE` case without its own body will have `Mode` as its runtime class. If you receive an arbitrary `Object value`, first check `value instanceof Enum<?> constant` to recognize constants with their own class bodies as well.

If you want to inspect the constant-specific implementation, `getClass()` is still useful. If you want to classify and list the **common enum type**, use `getDeclaringClass()`; a separate lesson on constant-specific class bodies analyzes this relationship further along with the difference between `Enum.getDeclaringClass()` and `Class.getDeclaringClass()`.

## 6. Retrieving constants can initialize the enum

`isEnum()` is a type classification step. `getEnumConstants()` must provide the actual constants; if the enum has not been initialized yet, retrieving the constants can trigger initialization, including creating the constants and executing `static` blocks.

Save as `EnumInitializationDemo.java`:

~~~java
public class EnumInitializationDemo {
    enum Level {
        FIRST, SECOND;

        static {
            System.out.println("Level initialized");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> type = Class.forName(
                "EnumInitializationDemo$Level",
                false,
                EnumInitializationDemo.class.getClassLoader());

        System.out.println("isEnum=" + type.isEnum());
        System.out.println("before constants");
        Object[] constants = type.getEnumConstants();
        System.out.println("count=" + constants.length);
    }
}
~~~

Compile and run in a new process:

~~~bash
javac --release 17 EnumInitializationDemo.java
java EnumInitializationDemo
~~~

Output:

~~~text
isEnum=true
before constants
Level initialized
count=2
~~~

The `false` argument to `Class.forName` in the example requests loading the class without initializing it yet. The name with `$` here is the exact binary name of the nested enum in the demo class, not an algorithm for deriving an enum name from a constant.

The line `Level initialized` appears when retrieving the constants. Therefore, a tool that only wants to classify types can stop at `isEnum()`; if it needs the list of constant objects, it must accept that retrieving values carries initialization semantics.

If the enum has already been initialized successfully earlier, retrieving the constants again does not recreate each constant or rerun `static` blocks on each call. If initialization fails, the program may receive an initialization error; do not equate that error with the `null` result reserved for non-enum classes.

This example also shows why you should not describe every Reflection API starting with `get` as completely side-effect-free.

## 7. Choosing the right API for each situation

**Specific type already known in source code:** call `Priority.values()` to iterate directly. There is no need to look up the `values` method via Reflection and call `Method.invoke`.

**Only a Class available at runtime:** use `isEnum()` and `getEnumConstants()`. This is the case when a form builder receives a property's type without knowing in advance which enum is used.

**Already holding a constant:** use `getDeclaringClass()` to normalize to the enum class, especially when the constant has a constant-specific class body.

**Need option names:** convert each constant with `Enum.name()` if declared names are needed; generate display labels using your own rules if the application requires localization or human-readable labels.

**Need metadata of the fields declaring constants:** that is a different task from retrieving values. `getDeclaredFields()` may include both regular fields and compiler-generated fields; do not replace calling `getEnumConstants()` by iterating over every field and assuming they are all enum constants.

The results of these two APIs also do not tell you that every option is permitted in every business scenario. For example, a state present in an enum is not necessarily a state allowed to be transitioned to from the current state. Type enumeration and business rule validation must be kept distinct.

## 8. Mistakes to avoid

| Mistake | Consequence or fix |
| --- | --- |
| Calling `getEnumConstants().length` on an unchecked Class | May hit `NullPointerException` when the class is not an enum |
| Treating an empty array as proof of not being an enum | Misses enums that have no constants |
| Assuming `Enum.class.isEnum()` must be `true` | Confuses the base class with a declared enum class |
| Using `constant.getClass().isEnum()` for every constant | Misses constants with their own class body; get `getDeclaringClass()` |
| Using `toString()` as the declared name | May receive an overridden string |
| Using `ordinal()` as a stable code by default | Codes can change when declaration order changes |
| Assuming retrieving constants only reads metadata | Overlooks enum initialization |
| Casting every result to a specific enum like `Priority[]` | Can fail type-wise when the input Class is another enum |
| Iterating all fields to obtain the list of constants | Mixes in other fields and loses the ordering contract of `getEnumConstants()` |

If your method accepts `Class<?>`, decide on a clear contract: reject non-enum classes, or return a result with a state that distinguishes "not an enum" from "empty enum". Do not silently merge the two cases if calling code needs to distinguish them.

## 9. Self-check

1. Is `Empty.class.isEnum()` `true` or `false` if the enum has no constants?
2. Does `String.class.getEnumConstants()` return an empty array or `null`?
3. When a constant overrides `toString()` in a constant-specific class body, why can `getClass().isEnum()` be `false`?
4. To retrieve both `FAST` and `SAFE` while holding `Mode.FAST`, which API should you start with?
5. Does retrieving the list of constants guarantee that no initialization code runs?

Answers:

1. `true`; an empty enum is still an enum, while the constants array has length 0.
2. `null`, because `String` is not an enum class.
3. The runtime class is then an anonymous subclass of the enum, not the declared enum class.
4. `Mode.FAST.getDeclaringClass()`, then call `getEnumConstants()` on the returned class.
5. No. If the enum has not been initialized yet, retrieving the constants can trigger initialization.

Keep three concepts separate: the declared enum class, the runtime class of a constant, and the set of constant objects. `isEnum()`, `getDeclaringClass()`, and `getEnumConstants()` address those three parts with distinct contracts.

## Reference documentation

- [Java 17 — Class.isEnum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isEnum()).
- [Java 17 — Class.getEnumConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getEnumConstants()).
- [Java 17 — Enum and getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()).
- [JLS 17 — Enum, constant-specific class bodies, and values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
- [JLS 17 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
