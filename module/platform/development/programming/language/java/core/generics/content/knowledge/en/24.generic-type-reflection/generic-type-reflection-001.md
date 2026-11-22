# `Class<T>` as Explicitly Passed Type Information in Java Generics

## 1. When Compile-Time `T` Is Not Enough for Runtime

In Java, a type variable like `T` helps the compiler check and link input and output types. For example:

~~~java
static <T> T identity(T input) {
    return input;
}
~~~

The call `identity("Java")` returns a value with static type String, while `identity(7)` returns Integer. No runtime token is needed because the algorithm only forwards a reference that has already been checked at compile time.

However, if a method receives an `Object` from a legacy API, configuration, or reflection and must **verify the class requested by the caller at runtime**, the generic type variable `T` does not provide that class on its own.

~~~java
// INTENTIONALLY WRONG for runtime checking purposes:
static <T> T unchecked(Object input) {
    return (T) input; // Unchecked warning; concrete class of T is unknown.
}
~~~

In the **type erasure** model, `T` can be erased to Object or the erasure of its first bound. There is no separate runtime class for each call `T=String` or `T=Integer` for `(T) input` to actually prove the exact concrete type.

A design that solves this need lets the **caller pass a Class object**:

~~~java
static <T> T checked(Object input, Class<T> expected) {
    return expected.cast(input);
}
~~~

Caller:

~~~java
String word = checked("Java", String.class);
Integer number = checked(42, Integer.class);
~~~

In source code, `Class<T>` links the token to the return type `T`. At runtime, `expected.cast` uses the actual class provided to check the object.

**This is the essence of a class token:** `Class<T>` represents a class/interface/array type with a concrete runtime identity; it does not make Java Generics fully reified.

## 2. Distinguishing `T`, `Class<T>`, `Class<?>`, and `Type`

| Symbol | Role | When it is useful |
| --- | --- | --- |
| `<T>` | Type parameter declaration. | When an API needs to preserve type relationships across positions. |
| `T` | Type variable in a generic method/class. | Compile-time type checking, type inference. |
| `Class<T>` | Class token whose type argument is linked to T. | Checking the class of an Object or a class selected at runtime. |
| `Class<?>` | Class token whose type argument is unknown. | Reading class/plugin metadata whose concrete type is not yet verified. |
| `Class<? extends Base>` | Token belonging to Base or a subtype. | APIs using the class of a Base implementation. |
| `java.lang.reflect.Type` | Interface describing declared types, possibly containing nested type arguments. | Analyzing `List<String>`, `Map<String,List<Integer>>` from metadata. |

Correspondingly:

~~~java
Class<String> textToken = String.class;
Class<Integer> numberToken = Integer.class;
Class<?> unknown = textToken;
Class<? extends Number> numeric = Integer.class;
~~~

`Class<T>` still follows **invariance**:

~~~java
// Invalid:
// Class<CharSequence> parent = String.class;

// Valid:
Class<? extends CharSequence> parent = String.class;
~~~

A runtime Class object is **not** a separate class generated for each parameterized type. `Class<String>` describes the token of class String. It does **not** mean that every `ArrayList<String>` instance carries a String token inside it.

### Prohibited Operations on Type Variables

~~~java
// The following expressions intentionally do not compile when T is a type variable:
// T.class
// new T()
// new T[10]
// input instanceof T
~~~

These constructs require a runtime type in a way that cannot be derived directly from an unreified `T`. Pass `Class<T>` if a runtime class is needed; pass a factory if object creation is needed.

## 3. Appropriate Usage Boundary: External Data as `Object`

A practical example is reading configuration or decoded data from a map:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("user", "Ada");
values.put("count", 17);
~~~

A typed API needs to make clear:
1. Does the key exist?
2. Is null accepted?
3. Does the value belong to the exact class the caller requested?
4. If valid, what static type will the result have?

~~~java
static <T> T require(
        Map<String, ?> values,
        String key,
        Class<T> expected) {

    Objects.requireNonNull(expected, "expected");

    if (!values.containsKey(key)) {
        throw new IllegalArgumentException("missing: " + key);
    }

    Object candidate = Objects.requireNonNull(
            values.get(key), "null: " + key);

    return expected.cast(candidate);
}
~~~

Caller:

~~~java
String user = require(values, "user", String.class);
Integer count = require(values, "count", Integer.class);
~~~

Because the same type parameter T appears in `Class<T>` and the return type, the caller receives a compiler-checked type without manual casting.

Errors are separated according to the **example API** contract:
- Missing key → IllegalArgumentException.
- Key present but null → NullPointerException.
- Right key but wrong class → ClassCastException.
- Right type → returns value of type T.

**Note:** `Class.cast(null)` itself returns null. It is `Objects.requireNonNull` that enforces the null policy in the example, not `Class<T>` rejecting null on its own.

### Why Can't `(T) candidate` Replace `expected.cast(candidate)`?

Casting to the type variable `T` after erasure does not have the String or Integer class available to perform an exact check. A type mismatch might only surface at the caller when the result is used as a String. `Class.cast` uses the actual passed-in token to check and fail at the boundary, closer to the source of bad data.

Also do not confuse casting with **data conversion**: `String.class.cast(17)` does not produce the string `"17"`. If a parser/converter is needed, use `String.valueOf`, `Integer.parseInt`, or dedicated business logic.

## 4. A Generic Object Proactively Holding a Token to Enforce an Invariant

A generic object may receive data from both typed sources and Object sources. If it must accept untyped input, a token stored in the object serves as a practical constraint:

~~~java
static final class Slot<T> {
    private final Class<T> token;
    private T value;

    Slot(Class<T> token) {
        this.token = Objects.requireNonNull(token);
    }

    void setUnknown(Object input) {
        value = token.cast(input);
    }

    T get() {
        return value;
    }
}
~~~

Call site:

~~~java
Slot<String> slot = new Slot<>(String.class);
slot.setUnknown("ready");

try {
    slot.setUnknown(123);
} catch (ClassCastException ex) {
    // Input does not belong to runtime class String.
}
~~~

Each Slot instance has the **same runtime class** as a generic class, yet individual instances can hold **different tokens** passed by their callers. The token is not metadata that the JVM automatically infers from `Slot<String>`.

Because the cast is performed **before** the field assignment completes, a failure in `setUnknown(123)` leaves the value `"ready"` unchanged. This is a good postcondition to test.

Do not turn every setter into `setUnknown(Object)` just because a class token is available: a `void set(T value)` setter remains the better design when the API only serves normal typed callers. Tokens are useful at points **intentionally open to untyped data**.

## 5. Complete Java 17 Program: Checking, Retaining a Token, and Validating a List

Save as **ClassTokenFoundations.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public class ClassTokenFoundations {
    static <T> T require(
            Map<String, ?> values,
            String key,
            Class<T> expected) {

        Objects.requireNonNull(expected, "expected");

        if (!values.containsKey(key)) {
            throw new IllegalArgumentException("missing: " + key);
        }

        Object candidate = Objects.requireNonNull(
                values.get(key), "null: " + key);

        return expected.cast(candidate);
    }

    static <T> List<T> checkedCopy(
            List<?> source,
            Class<T> expected) {

        List<T> output = new ArrayList<>();

        for (Object value : source) {
            output.add(expected.cast(
                    Objects.requireNonNull(value, "null element")));
        }

        return List.copyOf(output);
    }

    static <T> T create(Supplier<? extends T> factory) {
        return factory.get();
    }

    static final class Slot<T> {
        private final Class<T> token;
        private T value;

        Slot(Class<T> token) {
            this.token = Objects.requireNonNull(token);
        }

        void setUnknown(Object value) {
            this.value = token.cast(value);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Map<String, Object> config = new HashMap<>();
        config.put("user", "Ada");
        config.put("count", 17);

        System.out.println(
                "user=" + require(config, "user", String.class));
        System.out.println(
                "count=" + require(config, "count", Integer.class));

        try {
            require(config, "count", String.class);
        } catch (ClassCastException ex) {
            System.out.println("bad-token=" +
                    ex.getClass().getSimpleName());
        }

        Slot<String> message = new Slot<>(String.class);
        message.setUnknown("ready");

        try {
            message.setUnknown(12);
        } catch (ClassCastException ex) {
            System.out.println("slot-reject=" +
                    ex.getClass().getSimpleName());
        }

        System.out.println("slot=" + message.get());
        System.out.println("verified=" +
                checkedCopy(List.of("a", "b"), String.class));

        try {
            checkedCopy(List.of("a", 8), String.class);
        } catch (ClassCastException ex) {
            System.out.println("list-reject=" +
                    ex.getClass().getSimpleName());
        }

        System.out.println(
                "nullCast=" + (String.class.cast(null) == null));
        System.out.println(
                "nullInstance=" + String.class.isInstance(null));
        System.out.println(
                "subtype=" +
                Number.class.isAssignableFrom(Integer.class));
        System.out.println(
                "factory=" + create(
                        () -> new StringBuilder("made")));
        System.out.println(
                "sameRuntime=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass()));
    }
}
~~~

Compile/run without any libraries outside the JDK:

~~~bash
javac --release 17 -Xlint:all ClassTokenFoundations.java
java ClassTokenFoundations
~~~

**Verified stdout:**

~~~text
user=Ada
count=17
bad-token=ClassCastException
slot-reject=ClassCastException
slot=ready
verified=[a, b]
list-reject=ClassCastException
nullCast=true
nullInstance=false
subtype=true
factory=made
sameRuntime=true
~~~

**Reading the output by checkpoints:**

- `bad-token`: the map holds an Integer, but the caller requests String; the token catches the mismatch right at the boundary.
- `slot-reject`/`slot=ready`: The token in Slot<String> blocks invalid writes and preserves the postcondition.
- `verified`/`list-reject`: When the source is a `List<?>` with an unknown element type, checking **each element** against the token and creating a copy protects the result.
- `nullCast`/`nullInstance`: The APIs have different null behaviors; design a dedicated null policy.
- `subtype`: `Number.class.isAssignableFrom(Integer.class)` has the proper assignability direction.
- `factory`: Supplier creates an object without reflection.
- `sameRuntime`: two direct parameterizations of ArrayList share the same runtime class, without reifying String/Integer.

## 6. Limitation: `List.class` Checks Only the Container, Not the Elements

Java allows:

~~~java
List<String> words = List.of("a", "b");
List<Integer> numbers = List.of(1, 2);

boolean a = List.class.isInstance(words);
boolean b = List.class.isInstance(numbers);
~~~

Both `a` and `b` are `true`. The runtime token `List.class` only identifies the container type; it does not know whether elements follow the generic argument String or Integer.

You cannot write:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// Class<List<String>> token = List<String>.class;
// boolean ok = someObject instanceof List<String>;
~~~

`List<String>` is a **non-reifiable parameterized type**; there is no separate class literal for it.

To validate `List<?>` input data by element type, use a loop:

~~~java
static <T> List<T> checkedCopy(
        List<?> source, Class<T> type) {

    List<T> result = new ArrayList<>();

    for (Object element : source) {
        result.add(type.cast(
                Objects.requireNonNull(element)));
    }

    return List.copyOf(result);
}
~~~

This method verifies each element directly and builds a new list. `List.copyOf` rejects null and returns a list that cannot be modified through standard mutation APIs; however, this is a **shallow copy** if the elements themselves are mutable.

For nested generic types such as `List<List<String>>`, a `List.class` token only checks the raw List of each element, **not** the deeper Strings. Nested structures require an appropriate schema-based validator/decoder.

### `Collections.checkedList` Checks a Different Kind of Operation

The JDK provides:

~~~java
List<String> checked = Collections.checkedList(
        new ArrayList<>(), String.class);
~~~

The wrapper uses the String token to check **mutations going through the wrapper**. It does not automatically validate existing elements when the wrapper is created, nor can it prevent mutations through an alias that writes directly to the backing list.

- **Validated copy:** suited for external data that you want to check completely once and own as an independent copy.
- **Checked wrapper:** suited for blocking mis-typed writes through a view equipped with a class token.

Do not confuse these two tools with full reification of generic type arguments.

## 7. When Is `Class<T>` Unnecessary?

A generic method may not need any runtime type at all:

~~~java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }
    return values.get(0);
}
~~~

`Class<T>` is unnecessary because the compiler already has the relationship between the List's type argument and the result T.

Similarly, if the caller **knows how to create the object**, a factory callback is usually simpler:

~~~java
static <T> T create(
        java.util.function.Supplier<? extends T> factory) {

    return factory.get();
}

// StringBuilder builder = create(StringBuilder::new);
~~~

If the class is genuinely chosen only at runtime and its constructor must be invoked via reflection, `Class<T>` can be appropriate:

~~~java
static <T> T createByClass(Class<T> type)
        throws ReflectiveOperationException {

    return type.getDeclaredConstructor().newInstance();
}
~~~

However, a no-argument constructor must exist, be accessible under access/module rules, and the class must be instantiable. A `Class<T>` does not prove those facts and cannot bypass reflection access permissions on its own.

### Choosing by Task

| Task | Appropriate Parameter |
| --- | --- |
| Only preserve the same T between input/output | Ordinary generic `<T>` |
| Runtime requires an object belonging to the caller-specified class | `Class<T>` |
| Caller supplies how to create the instance | `Supplier<? extends T>` |
| Runtime selects a class and then checks constructor/plugin | `Class<?>`, subtype check step, reflection |
| Need nested generic declaration `Map<String,List<Integer>>` | `java.lang.reflect.Type` / type reference / schema |

## 8. Operations on Class Tokens Differ from Operations on Objects

Three common questions:

~~~java
Class<?> pluginClass = Class.forName(className);
~~~

1. "Does this **object** belong to class X?" — use `X.isInstance(object)`, or `X.cast(object)` when a typed result is needed.
2. "Is this runtime **class** a subtype of Base?" — use `pluginClass.asSubclass(Base.class)` to obtain a properly bounded token if valid, or `Base.class.isAssignableFrom(pluginClass)` for a boolean check.
3. "Can this class be **instantiated** via a constructor?" — check the constructor/access and handle reflection exceptions separately; `asSubclass` does not create objects.

`asSubclass` operates on a **class token**, not by casting an instance. `Class.cast` operates on an **actual object**, without inspecting nested generic arguments.

When a class name comes from an untrusted plugin/config, you must enforce an allowlist policy, class loader, module access, and side-effect controls. Type safety is not synonymous with security policy.

### `Class<?>` Means Unknown Type Info, Not Raw `Class`

If the type argument is unknown at compile time, use `Class<?>`. Do not use raw `Class` just to escape the type checker. If an API needs to state "class of a subtype of Number", use `Class<? extends Number>`; `Class<Number>` will not automatically accept `Integer.class` due to generic invariance.

## 9. `Class<T>` Differs from `Type` Metadata

Suppose a field is declared as:

~~~java
class Model {
    List<String> names;
}
~~~

Reflection has two views:

~~~java
Field f = Model.class.getDeclaredField("names");

Class<?> erasedClass = f.getType();
java.lang.reflect.Type declared = f.getGenericType();
~~~

`getType()` returns the runtime/erased class List. `getGenericType()` can return a `ParameterizedType` for the declaration `List<String>` when generic Signature metadata is present.

`Type` is the common interface used by constructs such as `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType` to describe declarations. It does **not** have a `cast` method like `Class<T>` for all kinds of types.

A super type token such as `new TypeRef<List<String>>() {}` can store metadata declared in an anonymous subclass. That does **not** make an object `new ArrayList<String>()` reveal `String` via `getClass()`, nor does it automatically resolve an unbound `T` in a generic method.

When building a schema/serializer, you must branch properly on the `Type` kind, resolve bindings across the hierarchy where applicable, and perform separate data validation. This `Class<T>` lesson only helps determine **when a concrete runtime class is sufficient and when it is not**.

## 10. Three Misconceptions About Runtime Type Safety

### Misconception A — "`Class.cast` converts data types"

No. `Integer.class.cast("17")` does not parse the string "17" into a number; if the actual type is wrong, it throws ClassCastException. Conversion requires an appropriate parser/mapper.

### Misconception B — "`Class<T>` knows the generic arguments of each collection"

No. `List.class` does not know whether an ArrayList was declared as `List<String>` or `List<Integer>` in source code. You need Type metadata from a declaration and/or per-element validation.

### Misconception C — "Getting `Class<?>` from a class name string means it is trustworthy"

No. Two classes with the same name loaded by different class loaders may not have the same runtime identity. And an untrusted class may have constructor/initialization side effects. Rely on actual Class identity and subtype relationships, along with an appropriate allowlist/policy.

## 11. Questions and Exercises to Check Understanding

**1.** What type does `String.class` have in source code?

**Answer:** `Class<String>`, which is a class token that can be passed to a generic method accepting `Class<T>`.

**2.** Can `Class<String>` be assigned to `Class<CharSequence>`?

**Answer:** No, because of generic invariance. Use `Class<? extends CharSequence>` if you want to accept subtype tokens like String.class.

**3.** Can you write `T.class` inside a generic method?

**Answer:** No. A type variable T does not carry a runtime class literal on its own. Accept a token parameter if you truly need the runtime class.

**4.** What do `String.class.cast(null)` and `String.class.isInstance(null)` return?

**Answer:** null and false, respectively. The API must define a null policy if null should be rejected.

**5.** A map has `count=17`, and the caller requests `String.class`. What happens in `require`?

**Answer:** ClassCastException at the runtime class check. Class.cast does not turn an Integer into a string.

**6.** If the actual object is a `List<Integer>`, does `List.class.isInstance(object)` return true?

**Answer:** Yes. It only checks that the object implements List, not the Integer type argument.

**7.** How do you bring a `List<?>` from an untrusted source into an API returning `List<String>`?

**Answer:** Check each element with String.class and build a typed copy with clear null/mutability/ownership policies.

**8.** Once you have `Class<T>`, is `new T()` valid?

**Answer:** No. Use reflection with an appropriate constructor or a factory callback. Not every class has a no-arg constructor or the required access permissions.

**9.** What advantage does `Supplier<T>` have when the caller knows how to create the object?

**Answer:** No reflection is needed, the constructor is compiler-checked at the call site, and the API is simpler.

**10.** Does `getGenericType()` on a field declared as List<String> prove that the current list object only contains Strings?

**Answer:** No. That is declaration metadata, not runtime payload validation.

**11.** How do you narrow a `Class<?>` returned by a plugin loader into a subtype of Service?

**Answer:** Use `discovered.asSubclass(Service.class)` or an equivalent check, then handle constructor/access/security separately.

**12.** Why shouldn't class names be compared as Strings as proof of subtyping?

**Answer:** Runtime type identity and subtyping also depend on the class loader and actual inheritance relationships, not just the binary name.

## 12. Design Checklist and Conclusion

- [ ] Include `Class<T>` in an API only when **runtime genuinely needs the class object**.
- [ ] Keep the generic type variable `T` distinct from the Class token supplied by the caller.
- [ ] Place class checks right at the boundary receiving `Object`/legacy data.
- [ ] Define policies for missing keys, null, wrong class, and conversion.
- [ ] Use `Class<?>` when the type argument is unknown, avoiding raw `Class`.
- [ ] Use a bounded class token if you need to restrict subtype classes.
- [ ] With `List<?>`, `List.class` does not validate the type of the elements.
- [ ] Choose validated copy or checked wrapper according to the task, and control aliases.
- [ ] If you only need a factory, consider `Supplier<? extends T>`.
- [ ] If nested type declarations are needed, use `Type`/TypeRef and dedicated resolution/validation logic.
- [ ] Do not infer generic arguments from `obj.getClass()` on a normal collection instance.
- [ ] When loading classes at runtime, verify class loader, access, trust, and subtype contract.

**Takeaway:** `Class<T>` is an **explicit** bridge between the generic type relationship checked by javac and the concrete class that the JVM can verify. It does not "un-erase" erased generic arguments, does not make `T.class` legal, and does not automatically validate nested collections. Use tokens specifically **where data is untyped**, and keep ordinary generic APIs where the compiler already guarantees the full contract.

### Official References

- [Java 17 Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java 17 Type API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html)
- [JLS `4.6 Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
- [JLS `4.7 Reifiable types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
