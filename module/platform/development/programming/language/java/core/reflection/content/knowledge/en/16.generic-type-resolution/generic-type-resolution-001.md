# Type Erasure and the Visibility Limits of List<String> on an Instance in Java Reflection

## 1. Does a List<String> object store String as a runtime type?

Suppose in Java 17+ we have:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

In source code, the compiler treats `List<String>` and `List<Integer>` as two different generic types to check the validity of `add`, `get`, and assignments. However, when two variables hold objects created from a normal `new ArrayList<>()`, Java only has **one runtime class `java.util.ArrayList`** for both.

```java
System.out.println(names.getClass() == numbers.getClass()); // true
```

**Type erasure** is the mechanism by which the compiler transforms many generic representations into their corresponding JVM types without creating a separate class for each type argument. Therefore, from an ordinary instance such as `new ArrayList<String>()`, `getClass()` does not tell you the type argument `String` of the source expression. Element order, the class of each element, or even whether the list is empty does not reveal the **original generic declaration**.

It is important to distinguish:

- **Runtime class of an instance:** `instance.getClass()` returns `ArrayList.class` (or the actual implementation class).
- **Generic signature of a declaration:** `Field.getGenericType()` or `Method.getGenericReturnType()` can read `List<String>` from class-file metadata if the field/method is declared that way.
- **Data inside a collection:** iterating over elements and calling `element.getClass()` only reveals the classes of the current non-`null` elements, not the type argument declared in the source.

**The generic information of a declaration may remain; a type argument attached specifically to an ordinary ArrayList instance is not automatically preserved.** This is the most important boundary when using Reflection.

## 2. What does type erasure do at compile time?

At compile time, Java generics help check type safety. When generating JVM class files, the compiler applies erasure:

1. An unbounded type parameter, such as `T` in `class Box<T>`, typically has an erasure of `Object`.
2. A type parameter with an upper bound such as `T extends Number` has an erasure of `Number`. If there are multiple bounds, the erasure rule uses the leftmost bound.
3. The compiler may insert casts wherever a value retrieved from a generic API needs to be treated as a specific type.
4. The compiler may generate bridge methods to preserve proper overriding/polymorphism after erasure.
5. Certain generic declarations still carry a `Signature` attribute in the class file so Reflection and class-file inspection tools can parse them.

For example:

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
```

After erasure, the `List.get(int)` method has a bytecode-level return type of `Object`. The compiler inserts the necessary check/cast so that the value assigned to `String first` satisfies the source type requirement. The runtime object `"An"` is still an actual `String`; erasure **does not erase the class of the element**. What is no longer stored on an ordinary `ArrayList` object is "it was created with `<String>`".

Therefore, a program can maintain generic type safety if all code is properly type-checked, yet can suffer **heap pollution** if it intentionally goes through raw types/unchecked operations or bytecode that does not uphold those rules.

## 3. What can Reflection see?

| Question | Appropriate API | Limitation |
| --- | --- | --- |
| What class is the object? | `object.getClass()` | Cannot read `<String>` from an ordinary `ArrayList` instance |
| Does the object implement List? | `object instanceof List<?>` or `List.class.isInstance(object)` | Does not determine the element generic type |
| What type is the field declared with? | `field.getType()` | Gives the erased type, such as `List.class` |
| With what type arguments is the field declared? | `field.getGenericType()` | Gives metadata of the *field declaration*, not runtime contents |
| What generic return type is the method declared with? | `method.getGenericReturnType()` | Not the concrete type of the object returned by the current invocation |
| What generic parameters does the method accept? | `method.getGenericParameterTypes()` | Reflects the declared signature, not the actual arguments |
| What generic superclass does the class declare? | `clazz.getGenericSuperclass()` | May return a type variable `E` or a concrete type argument depending on the declaration |
| What generic interfaces does the class declare? | `clazz.getGenericInterfaces()` | Only describes the generic declarations of the class |
| What class is each current element? | `element.getClass()` if non-`null` | Does not prove the list was declared as `List<String>` |

For example, a field declared as `List<String> names` can have `getGenericType()` return `java.util.List<java.lang.String>`. If the field currently points to `new LinkedList<String>()`, `Field.getType()` is still `List.class`, `Field.getGenericType()` still describes `List<String>`, while `field.get(instance).getClass()` gives `LinkedList.class`. Those are **three different kinds of information**.

Local variables inside a method such as `List<String> local` are not provided a direct Java core Reflection API equivalent to `Field.getGenericType()` to query that variable's declared type from the object it references. Debug/bytecode metadata may contain other data, but it is not a runtime property accessible from each object.

## 4. Complete Java 17+ program, verified output

Save the file `ErasureInstanceDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.List;

public class ErasureInstanceDemo {
    static class Holder {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
    }
    static class Box<T> {
        T value;
    }
    static class StringBox extends Box<String> {}

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void pollute(List<String> strings) {
        List raw = strings;
        raw.add(42);
    }

    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
        System.out.println("same runtime class = "
                + (names.getClass() == numbers.getClass()));
        System.out.println("runtime class = " + names.getClass().getName());
        System.out.println("ArrayList generic superclass = "
                + names.getClass().getGenericSuperclass().getTypeName());

        Field field = Holder.class.getDeclaredField("names");
        System.out.println("field raw type = " + field.getType().getTypeName());
        Type generic = field.getGenericType();
        System.out.println("field generic type = " + generic.getTypeName());
        System.out.println("field arg = " + ((ParameterizedType) generic)
                .getActualTypeArguments()[0].getTypeName());

        Type anonSuperclass = new ArrayList<String>() {}
                .getClass().getGenericSuperclass();
        System.out.println("anonymous superclass = "
                + anonSuperclass.getTypeName());

        Type boxFieldType = Box.class.getDeclaredField("value").getGenericType();
        System.out.println("Box.value generic type = " + boxFieldType.getTypeName());
        System.out.println("Box type parameter = "
                + ((TypeVariable<?>) boxFieldType).getName());
        System.out.println("StringBox superclass = "
                + StringBox.class.getGenericSuperclass().getTypeName());

        List<String> polluted = new ArrayList<>();
        polluted.add("ok");
        pollute(polluted);
        System.out.println("size after raw add = " + polluted.size());
        System.out.println("second element runtime = "
                + ((List<?>) polluted).get(1).getClass().getSimpleName());
        try {
            String invalid = polluted.get(1);
            System.out.println(invalid);
        } catch (ClassCastException ex) {
            System.out.println("read as String = ClassCastException");
        }
        System.out.println("List<String> instanceof List<?> = "
                + (polluted instanceof List<?>));
    }
}
```

Compile targeting Java 17; run on JDK 17 or higher:

```bash
javac --release 17 ErasureInstanceDemo.java
java ErasureInstanceDemo
```

Exact stdout from compiling/running on JDK 24 with `--release 17`:

```text
same runtime class = true
runtime class = java.util.ArrayList
ArrayList generic superclass = java.util.AbstractList<E>
field raw type = java.util.List
field generic type = java.util.List<java.lang.String>
field arg = java.lang.String
anonymous superclass = java.util.ArrayList<java.lang.String>
Box.value generic type = T
Box type parameter = T
StringBox superclass = ErasureInstanceDemo$Box<java.lang.String>
size after raw add = 2
second element runtime = Integer
read as String = ClassCastException
List<String> instanceof List<?> = true
```

Analysis:

1. Two objects created from `new ArrayList<>()` share the same runtime `Class<?>`. Parameterized types on local variables do not cause the JVM to create separate classes.
2. `ArrayList.class` declares the generic superclass `AbstractList<E>`; when read from an ordinary instance, `E` is the **type variable of the declaration**, not the `String` bound to the variable.
3. Field `Holder.names` directly declares `List<String>`, so `Field.getGenericType()` can read the generic signature; `Field.getType()` only returns the raw `List`.
4. `new ArrayList<String>() {}` creates an **anonymous subclass** and records the `extends ArrayList<String>` relationship in metadata. Therefore, `ArrayList<String>` can be read from the **generic superclass of the anonymous subclass**.
5. Field `Box<T>.value` is declared with the type variable `T`. Reflection directly on `Box.value` sees `T`. `StringBox extends Box<String>` carries the `T → String` mapping in the superclass relationship metadata; Reflection does not automatically rewrite the field type when querying `Box.class`.
6. `pollute` intentionally uses a raw List to add an `Integer` into the object referenced through `List<String>`. The list itself remains a valid runtime List. The error occurs later, when code tries to use the element as a `String` and the compiler-inserted cast fails.

Do not use `@SuppressWarnings` as a way to "fix" heap pollution. This annotation only suppresses compiler warnings at the point intentionally demonstrating an unchecked operation; it does not change runtime checks.

## 5. getGenericType returns Type, not always Class<?>

Generic reflection APIs return the `java.lang.reflect.Type` interface. The concrete value may belong to several families:

- `Class<?>`: a type with a runtime class such as `String.class`, `List.class`, `int.class`, `String[].class`.
- `ParameterizedType`: declarations like `List<String>`, `Map<String, Integer>`; exposes `getRawType()` and `getActualTypeArguments()`.
- `TypeVariable<?>`: a type parameter not yet replaced by a concrete type, such as `T` in `Box<T>`. `getBounds()` gives its bounds.
- `WildcardType`: a wildcard component such as `? extends Number` or `? super Integer`, exposing upper/lower bounds.
- `GenericArrayType`: an array type whose component in the signature is a non-reifiable generic type such as `T[]`.

Therefore, you should not unconditionally write:

```java
ParameterizedType generic = (ParameterizedType) field.getGenericType();
```

It is only valid if `field.getGenericType()` is actually a `ParameterizedType`. For `String title` or a raw `List values`, the result may be a `Class<?>`. For `T value` in `Box<T>`, the result is a `TypeVariable<?>`. A blind cast will throw `ClassCastException`.

A checked metadata-reading utility that compiles on Java 17:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public final class GenericFieldInspector {
    private GenericFieldInspector() {}

    public static void describe(Field field) {
        Type declared = field.getGenericType();
        System.out.println("declared type: " + declared.getTypeName());
        if (declared instanceof ParameterizedType pt) {
            System.out.println("raw: " + pt.getRawType().getTypeName());
            for (Type arg : pt.getActualTypeArguments()) {
                System.out.println("argument: " + arg.getTypeName());
            }
        }
    }
}
```

This is a standalone utility class that compiles when saved to `GenericFieldInspector.java` but **has no `main`**. Call `describe` from another program with a looked-up `Field`. The utility analyzes the declared type; it does not inspect the elements currently inside a collection.

For `Map<String, List<Integer>>`, the second argument of `Map` is itself a `ParameterizedType`. Thus a complete generic resolution tool must traverse the **Type tree**. For `List<? extends Number>`, the argument is a `WildcardType`, not literally `Number.class`. Never blindly cast every element of `getActualTypeArguments()` to `Class<?>`.

## 6. Type variables, inheritance, and limits of inference

Example:

```java
class Box<T> {
    T value;
}
class StringBox extends Box<String> { }
```

`Box.class.getDeclaredField("value").getGenericType()` returns `T` because the field **is declared on Box**. Meanwhile, `StringBox.class.getGenericSuperclass()` describes `Box<String>`. To infer the type used for `value` in the context of `StringBox`, a framework must resolve the type variable mapping itself, potentially across multiple superclass/interface levels.

If a generic declaration is `class Holder<T extends Number>`, then the erasure of `T` relates to `Number`, yet the metadata may still represent `T` when calling `getGenericType()`. You must distinguish the **erased type used by the JVM** from the **generic declaration read by Reflection via Signature**.

You cannot use `getClass()` of the field value to automatically infer this mapping: if the field holds `null`, there is not even a runtime class, and an object may be a subclass of the declared type.

## 7. Where do anonymous subclasses and type tokens store generic metadata?

Compare:

```java
ArrayList<String> ordinary = new ArrayList<>();
ArrayList<String> captured = new ArrayList<String>() {};
```

`ordinary.getClass()` is `ArrayList.class`; the generic superclass on `ArrayList` is `AbstractList<E>`. `captured.getClass()` is a **distinct anonymous subclass**, with metadata declaring `extends ArrayList<String>`; therefore `captured.getClass().getGenericSuperclass()` can return the `ParameterizedType` for `ArrayList<String>`.

The type token technique leverages the idea of declaring a subclass containing a concrete generic parameter:

```java
abstract class TypeRef<T> {
    final java.lang.reflect.Type type =
            ((java.lang.reflect.ParameterizedType)
                getClass().getGenericSuperclass())
                .getActualTypeArguments()[0];
}

// Place the statements below inside a method, with import java.util.List:
TypeRef<List<String>> ref = new TypeRef<List<String>>() {};
System.out.println(ref.type.getTypeName());
// java.util.List<java.lang.String>
```

This is **illustrative code**, not a standalone runnable file: the instantiation of `ref` must be placed inside a method and requires importing `List`. The cast in `TypeRef` assumes the caller creates a **direct anonymous subclass with a parameterized superclass**, and does not automatically handle multi-level inheritance or raw subclasses.

**A type token does not read a hidden generic type from an ordinary ArrayList instance.** It holds the `Type` from **code explicitly declared in the anonymous subclass**. When a framework receives `TypeRef<List<String>>` alongside a list object, the type token is *supplementary metadata provided by the caller*. The runtime collection can still be polluted with elements of the wrong type, and validation is still needed when processing untrusted data.

## 8. Checking each actual element differs from identifying List<String>

If you receive `Object unknown` from an API, you can verify that it is currently a list containing only `String`s at the time of iteration:

```java
import java.util.List;

public final class ListContents {
    private ListContents() {}

    public static boolean containsOnlyStrings(Object unknown) {
        if (!(unknown instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }
}
```

This is a utility class that compiles with Java 17, without `main`. The example policy treats `null` elements as invalid; another application might want to allow `null`.

However, a `true` result **does not prove** the source type `List<String>`:

- A `List<Object>` might also currently contain only `String`s.
- An empty list returns `true` even though there are no elements to verify; the source generic argument cannot be inferred.
- The list may be mutated after checking or modified concurrently.
- Runtime elements may be subtypes of the declared type; observing runtime types does not reveal the overall generic declaration.
- `(List<String>) someObject` is an unchecked cast in typical contexts and does not automatically check every element. A `ClassCastException` may only surface when accessing an element.

For serialization, JSON mapping, or data binding, you should **use the declared generic Type/schema provided by the caller** to decide the target element type to convert to, then validate the corresponding values. You should not just take `instance.getClass()` and guess.

## 9. instanceof, generic arrays, and reifiability

In Java, `List<String>` is generally **non-reifiable**: the type argument `String` is not individually verified by the JVM for a runtime List. The following operations are illegal in ordinary Java code:

```java
// Invalid; commented out so the sample code does not cause a compile error:
// if (obj instanceof List<String>) { }
// Class<?> type = List<String>.class;
// List<String>[] xs = new List<String>[4];
```

`obj instanceof List<?>` is valid because `List<?>` is a reifiable form: it only checks whether the object implements List. For arrays like `String[]`, the JVM preserves the runtime component type (`getClass().getComponentType() == String.class`). `List<?>[]` can be created, but each element in the array is only checked to be a List, without a specific generic argument.

Do not confuse **array covariance** with **generic invariance**. `String[]` can be assigned to `Object[]` and throw `ArrayStoreException` if an element of the wrong type is written, whereas `List<String>` is not a subtype of `List<Object>`. This helps explain why Java forbids directly creating `new List<String>[...]`: runtime arrays check the component class, whereas the generic parameter `String` has been erased.

Another manifestation of erasure is that you cannot declare two overloads differing only in generic arguments:

```java
// The two overloads below, if placed in the same class, will cause a name clash:
// void handle(List<String> strings) {}
// void handle(List<Integer> numbers) {}
```

Because both are erased to a JVM signature with a single `List` parameter, there is no way to dispatch an overload based on `<String>` or `<Integer>` at runtime.

## 10. Checklist for Reflection tool authors

1. **If you need the runtime class**, call `getClass()` and accept that it only reflects the implementation, not reconstructing `List<String>`.
2. **If you need the generic declaration**, identify the *declaration site*: field, method return/parameter, constructor parameter, generic superclass, or interface. Use the corresponding `getGeneric...` API.
3. **If you are holding a Type**, inspect the variant `Class`/`ParameterizedType`/`TypeVariable`/`WildcardType`/`GenericArrayType` before casting. For nested generic types, traverse the Type tree.
4. **If the generic type is T**, analyze the inheritance hierarchy and map the TypeVariable by context. Do not use the class of a field's value to conclude its declaration.
5. **If you need a runtime type token**, require the caller to declare it explicitly or use the API's generic declaration. Do not assume an ordinary `new ArrayList<String>()` automatically creates a token.
6. **If you need data guarantees**, define a schema and validate every element; watch out for empty lists, nulls, raw types, unchecked casts, and concurrency.
7. **If diagnosing a class file**, you can use `javap -v` to inspect the `Signature` attribute. Verify the exact artifact and classloader in use; toolchains/obfuscation can affect metadata.
8. **If simply calling generic APIs from ordinary Java code**, prefer compiler type checking. Reflection is appropriate when schemas and type metadata are only determined at runtime.

## 11. Common pitfalls

| Claim | Fact |
| --- | --- |
| "`List<String>` and `List<Integer>` create two different runtime classes" | Ordinary `new ArrayList<>()` for both still has the runtime class `ArrayList` |
| "`getClass()` reveals the type argument `String`" | It only gives the runtime implementation class |
| "`Field.getGenericType()` proves all elements are Strings" | It only describes the declared type of the field |
| "`getGenericType()` can always be cast to `ParameterizedType`" | It may be `Class`, `TypeVariable`, or another `Type` kind |
| "Inspecting the first element reveals the original generic type" | Fails for empty lists, nulls, subtypes, or lists declared as `List<Object>` |
| "Anonymous subclasses give every ArrayList a runtime type argument" | The generic signature only lives in the superclass declaration of that specific subclass |
| "`instanceof List<String>` is valid" | Use `instanceof List<?>`; the `String` generic argument cannot be checked |
| "An unchecked cast to `List<String>` validates all elements" | No; type pollution may only surface when reading |
| "`T extends Number` is erased to Object in all cases" | Erasure uses the bound, which in this example is `Number` |
| "A type token guarantees collection data conforms to the schema" | A type token describes the declared type; data must be validated separately |

## 12. Self-check questions

**Question 1.** `List<String> a = new ArrayList<>(); List<Integer> b = new ArrayList<>();`. What is `a.getClass() == b.getClass()`? **`true`** (same runtime class `ArrayList`).

**Question 2.** A field `List<String> names` has two ways to read it: `getType()` and `getGenericType()`. How do they differ? **`getType()` returns the raw `List.class`; `getGenericType()` can return a `ParameterizedType` describing `List<String>`**.

**Question 3.** Does a list containing only `String`s prove it was declared as `List<String>`? **No**. `List<Object>`, `List<CharSequence>`, or a raw list can also contain only Strings.

**Question 4.** What does an anonymous `new ArrayList<String>() {}` retain? **The generic signature `extends ArrayList<String>` in the anonymous subclass's class**; not automatic metadata on an ordinary `ArrayList` object.

**Question 5.** When `Box<T>.value` is read from `Box.class` in the example program, does it return `String` or `T`? **`T`**. Resolving it to `String` in the context of `StringBox` requires analyzing the superclass metadata.

**Question 6.** Why can a `ClassCastException` happen when reading from `List<String>`? A raw/unchecked operation may insert an `Integer` into the list; the cast inserted by the compiler when reading it as a String fails.

**Question 7.** Can an empty list prove its type argument from its elements? **No**. There are no elements to inspect.

**Question 8.** What does `obj instanceof List<?>` tell you? **Only that the object is a List at runtime**, without verifying the element type.

## 13. Official references

- [Java Language Specification 17, Section 4.6: Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
- [Java Language Specification 17, Section 4.7: Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
- [Java SE 17 Javadoc: Type](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 17 Javadoc: ParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 17 Javadoc: Field.getGenericType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 Javadoc: Class generic superclass and interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [JVM Specification 17, Section 4.7.9: Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9)
