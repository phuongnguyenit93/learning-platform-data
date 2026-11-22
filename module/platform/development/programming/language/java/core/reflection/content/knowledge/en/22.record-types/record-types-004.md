# Instantiating records via constructor instead of modifying final fields

## 1. A record is complete upon creation

A record describes data using **record components** in its declaration header. Each component corresponds to a `private final` instance field and an accessor method.

Example:

~~~java
record Member(String name, int level) {
}
~~~

This is a record declaration, not a program with `main`. Its canonical constructor takes `String name` and `int level` in order.

A common object-creation pattern with JavaBeans is creating an object first and assigning properties afterward. That mindset does not fit record components: data must be passed through the constructor so the object is fully initialized.

When the record class is only known at runtime, Reflection still follows the same model:

1. Read the components in declaration order.
2. Identify the canonical constructor.
3. Prepare all arguments.
4. Invoke the constructor to obtain a new record.

Do not use writing to a `final` field as a step to "finish" an already-created record. Beyond Reflection API restrictions, that approach also bypasses the place where data validation and normalization rules are concentrated.

## 2. Canonical constructor and compact constructor

The **canonical constructor** has parameter types corresponding to the components, preserving the order in the record header.

For `record Member(String name, int level)`, the type list is:

~~~text
String.class, int.class
~~~

A record can declare its canonical constructor in full form or in a shorthand form called a **compact constructor**. The compact form is suitable for parameter validation and normalization:

~~~java
public record Member(String name, int level) {
    public Member {
        name = java.util.Objects.requireNonNull(name, "name").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is blank");
        }
        if (level < 1) {
            throw new IllegalArgumentException("level must be positive");
        }
    }
}
~~~

This is a standalone illustrative declaration separate from the short declaration in the previous section; do not place both with the same name in the same scope.

Inside the compact constructor body, `name` and `level` are implicit parameters. You can reassign the parameters to normalize them. After the body completes normally, compiler-provided code initializes the fields from the corresponding parameters.

Do not write `this.name = ...` in a compact constructor to assign component fields manually. If you use the full canonical constructor form, the assignment rules differ; do not mix the two declaration styles.

Reflection finds the canonical constructor with the same parameter type list even when it is declared in compact form. Invoking this constructor still runs all validation and normalization checks.

Records are not automatically given a default no-argument constructor according to the rules for ordinary classes. If another author-written constructor exists, it must delegate through a valid record constructor chain. Therefore, do not assume every record can be instantiated with a no-argument call and populated later.

## 3. Runnable example: finding and invoking the canonical constructor

Save as `RecordConstructorDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

public class RecordConstructorDemo {
    public record Member(String name, int level) {
        public Member {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (level < 1) {
                throw new IllegalArgumentException("level must be positive");
            }
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Member> type = Member.class;
        RecordComponent[] components = type.getRecordComponents();

        Class<?>[] parameterTypes = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);

        Constructor<Member> constructor =
                type.getDeclaredConstructor(parameterTypes);

        System.out.println("components="
                + Arrays.stream(components)
                      .map(RecordComponent::getName)
                      .collect(Collectors.joining(",")));
        System.out.println("signature="
                + Arrays.stream(parameterTypes)
                      .map(Class::getSimpleName)
                      .collect(Collectors.joining(",")));

        Member member = constructor.newInstance(" Lan ", 3);
        System.out.println("name=" + member.name());
        System.out.println("level=" + member.level());
        System.out.println("sameAsDirect="
                + member.equals(new Member("Lan", 3)));

        try {
            constructor.newInstance("   ", 3);
        } catch (InvocationTargetException exception) {
            Throwable cause = exception.getCause();
            System.out.println("constructorCause="
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        }

        try {
            constructor.newInstance("Lan", "3");
        } catch (IllegalArgumentException exception) {
            System.out.println("arguments="
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 RecordConstructorDemo.java
java RecordConstructorDemo
~~~

Output:

~~~text
components=name,level
signature=String,int
name=Lan
level=3
sameAsDirect=true
constructorCause=IllegalArgumentException:name is blank
arguments=IllegalArgumentException
~~~

Points to observe:

- `getRecordComponents()` returns components in the order of the record header. No need to guess from field order.
- `getType()` provides the types to find the right constructor: an `int` component needs `int.class`, not `Integer.class`.
- `newInstance(" Lan ", 3)` executes the compact constructor, so the resulting name is `Lan`.
- A whitespace-only string is rejected by the constructor. Errors from the constructor body are wrapped in `InvocationTargetException`.
- The string `"3"` is not automatically converted to an `int` number. This is a Reflection argument error, reported with `IllegalArgumentException` before a valid constructor call occurs.

Looking up the constructor and passing arguments are two steps with different rules. Lookup uses the `Class` objects of the exact declared types; at invocation time, Reflection can unbox an `Integer` value to pass to an `int` parameter, such as the number `3` in the example.

## 4. Component names determine argument positions when input is a Map

The canonical constructor is tied to component order in the header. If you have `record Address(String city, String street) {}`, swapping the two strings is still type-valid yet produces an address with the wrong meaning. With input data that has property names, pick values by **component name**, then place them at the exact index:

~~~java
// Code snippet inside a method: type is the record's Class<?>,
// source is a Map<String, ?>; type.isRecord() has already been checked.
RecordComponent[] components = type.getRecordComponents();
Object[] arguments = new Object[components.length];
for (int i = 0; i < components.length; i++) {
    String name = components[i].getName();
    if (!source.containsKey(name)) {
        throw new IllegalArgumentException("Missing component: " + name);
    }
    arguments[i] = source.get(name);
}
~~~

This snippet only prepares the arguments. Looking up and invoking the canonical constructor using `RecordComponent.getType()` was illustrated in section 3; a complete mapper must also check for unknown keys and convert values to the right types before invoking.

Do not take `source.values().toArray()` as arguments: Map iteration order is not the ordering contract of a record header. `containsKey` also distinguishes a missing name from a key that is present with a `null` value. If a component has a primitive type, `null` cannot be a valid argument; whereas `null` for a reference type may be rejected by the constructor itself.

## 5. Why does setAccessible(true) not resolve record final fields?

Final fields declared in a record belong to the group of **final fields that cannot be modified by Field.set** according to the Reflection contract. `setAccessible(true)` does not turn them into writable fields.

The accessible flag relates to Java access control checks. Access permission and modifiability of a record's final field are two different conditions.

Save as `RecordFinalFieldDemo.java`:

~~~java
import java.lang.reflect.Field;

public class RecordFinalFieldDemo {
    public record Note(String text) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Note note = new Note("before");
        Field field = Note.class.getDeclaredField("text");

        field.setAccessible(true);
        System.out.println("read=" + field.get(note));

        try {
            field.set(note, "after");
        } catch (IllegalAccessException exception) {
            System.out.println("write="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("value=" + note.text());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 RecordFinalFieldDemo.java
java RecordFinalFieldDemo
~~~

Output on JDK 17:

~~~text
read=before
write=IllegalAccessException
value=before
~~~

The example is placed in the same outer class so enabling accessibility does not hit another library's module boundaries. Even when accessibility is enabled and the field can be read, the write operation is still rejected.

Do not interpret this error as "needing to call setAccessible one more time." With records, the right initialization path is finding and invoking the appropriate constructor. If different data is needed, create a new record through the constructor so the record's rules continue to be enforced.

## 6. Updating data by creating a new value

A record represents an already-initialized set of data. If you want to change a component, create a new value, keeping the remaining components as needed.

The following snippet is a method placed in the scope of `RecordConstructorDemo`, using the `Member` record from the first example:

~~~java
static Member withLevel(Member current, int nextLevel) {
    return new Member(current.name(), nextLevel);
}
~~~

The call still goes through the constructor, so `nextLevel < 1` is rejected. The `current` object keeps its old value.

If the type is only known at runtime, the principle is the same: retrieve existing data using the appropriate accessors, replace the input value to be changed, order by components, and invoke the canonical constructor to create a new object. Do not directly mutate fields of the old object.

This matters for **invariants**. For example, a time-range record might require the start instant not to be after the end instant. Passing all data through the constructor allows checking relationships between components before returning a valid object.

Constructors do not automatically create business rules: the record's author must write them if needed. Reflection only guarantees the call goes through the chosen constructor; it does not know on its own what data makes sense in the application.

## 7. Details that easily cause errors when calling constructors

### 7.1. Finding the exact declared type

`getDeclaredConstructor` and `getConstructor` search by the parameter type list, not by "close match." For an `int level` component, searching with `Integer.class` will not find that canonical constructor.

When invoking `Constructor.newInstance`, primitive values are represented in `Object[]` by boxed objects. Reflection supports appropriate invocation conversions, but it is not an arbitrary converter from strings or every numeric type.

For example, `Integer` can be unboxed for `int`; `null` cannot provide a value for an `int` parameter. Do not rely on Reflection to automatically parse `"42"` into a number.

### 7.2. An array-typed component is still one argument

`Constructor.newInstance` takes `Object...`. If a record has a `String[]` component, avoid accidentally passing the array's elements as multiple arguments.

Illustrative example inside a method that has a matching constructor:

~~~java
Object[] arguments = {new String[] {"A", "B"}};
Object record = constructor.newInstance(arguments);
~~~

The `constructor` variable here is a `Constructor<?>` of a record with a single `String[]` component. The outer array has one slot, so the call receives exactly one argument, which is the string array.

Building `Object[] arguments` by component in the Map-mapping example also preserves this structure. For a varargs component in the record header, the canonical constructor still has the corresponding array-typed parameter; prepare one array value at that argument position.

### 7.3. Finding a constructor does not mean permission to invoke it

`getDeclaredConstructor` can find non-public constructors, yet the call is still subject to access checks. The record and constructor in the first example are both public, so disabling access checks is unnecessary.

With non-public types or different module boundaries, design a valid access path for the library or use a provided factory API. Do not treat seeing metadata as proof that every call site has permission to instantiate.

### 7.4. Component finality is not deep immutability

If a component holds a reference to a mutable collection, `final` does not automatically make that collection immutable. The constructor can make an appropriate copy if the record contract needs to keep data stable.

Illustrative declaration, with `import java.util.List`:

~~~java
record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
~~~

The copying step runs when going through the constructor, including when called via Reflection. This is another reason to place data normalization on the initialization path rather than trying to assign fields afterward. `List.copyOf` is not a deep copy of every object that might reside inside a data structure.

## 8. Distinguishing error categories

| Error | Common meaning in this flow |
| --- | --- |
| `NoSuchMethodException` | The type list does not match a constructor, or searching for a public constructor when no matching public constructor exists |
| `IllegalAccessException` when invoking a constructor | Not permitted to access the constructor from the call site |
| `IllegalArgumentException` from Reflection | Wrong argument count or a value cannot be converted to the parameter type |
| `InvocationTargetException` | The constructor was invoked and its body threw an exception; inspect `getCause()` |
| `IllegalAccessException` from `Field.set` on a final component | Using a field-write path unsupported for records |

If the constructor rejects data, do not ignore the error and attempt to create the object by writing fields. That defeats the exact constraint the record is protecting.

When reporting errors in a data mapper, preserve the record name, the relevant component name when identifiable, and the root cause from the constructor. Do not replace every error with a single generic message that leaves users unsure whether a type or a data rule failed.

## 9. Self-check

1. Why use `getRecordComponents()` to build the canonical constructor parameter list instead of using `getDeclaredFields()` order?
2. For an `int` component, is looking up the constructor with `Integer.class` right?
3. If a compact constructor strips whitespace from a name, does calling via Reflection execute that step?
4. How does `InvocationTargetException` differ from `IllegalArgumentException` caused by wrong argument types?
5. Does successfully enabling `setAccessible(true)` allow modifying a record's `final` field?
6. When wanting a component to have a new value, should you mutate the old object or create a new object?

Answers:

1. Components have an ordering contract from the record header; Reflection field order is not a source for inferring constructor order.
2. No; search by `int.class`. Unboxing values at invocation time is a different rule.
3. Yes; `Constructor.newInstance` actually invokes the constructor.
4. The first exception wraps an error from the constructor body; an argument error can prevent a valid invocation from taking place at all.
5. No; a record's `final` component field does not become writable through `Field.set`.
6. Create a new object through the constructor, keeping the other components and reapplying necessary checks.

## References

- [JLS 17 — Record Constructors and Compact Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4).
- [Java 17 — Class.getRecordComponents and finding the canonical constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()).
- [Java 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
- [Java 17 — AccessibleObject and unmodifiable final fields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#setAccessible(boolean)).
