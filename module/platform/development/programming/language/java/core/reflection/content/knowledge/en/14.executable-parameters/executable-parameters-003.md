# `getParameterTypes()` vs. `getGenericParameterTypes()` in Java Reflection

## 1. Goal: Distinguishing Runtime Parameter Types and Generic Signatures

When using Reflection on `Method` or `Constructor<?>`, two methods both describe the parameters of an *executable* but return different representations:

- **`getParameterTypes()`** returns `Class<?>[]`: the actual classes/types according to the **erased signature** (the types the JVM uses as parameter descriptors). It is suitable for looking up methods/constructors by signature and handling runtime types.
- **`getGenericParameterTypes()`** returns `java.lang.reflect.Type[]`: parameter types according to the **generic information in the declaration** when metadata is present. It can reflect `List<String>`, `T`, `T[]`, `? extends Number`…, rather than just erased types.

Both are members of the superclass `java.lang.reflect.Executable`, so they work for both **`Method` and `Constructor`**. The arrays are returned in parameter order, though there is an important exception for constructors with implicit parameters (section 7).

| Criterion | `getParameterTypes()` | `getGenericParameterTypes()` |
| --- | --- | --- |
| Return type | `Class<?>[]` | `Type[]` |
| `List<String>` | `List.class` | `ParameterizedType` representing `List<String>` |
| `T extends Number` | `Number.class` (erasure of `T`) | `TypeVariable` representing `T` |
| `T[]` | `Number[].class` if erasure of `T` is `Number` | `GenericArrayType` for `T[]` |
| `String[]` | `String[].class` | Typically `Class` representing `String[]` |
| Wildcard awareness | No wildcards remain in `Class<?>` | Wildcards reside inside `ParameterizedType`, accessed via `WildcardType` |
| Overload selection / lookup | **Right API**: use erased `Class<?>` objects to find methods | Cannot pass `Type[]` directly into `getDeclaredMethod(...)` |
| Describing generics for schema/serialization | No generic arguments | Can extract generic arguments/bounds from the signature |
| Dependence on generic signature metadata | Does not require `Signature` metadata for erased parameter types | Detailed generic information depends on the generic signature stored in the class file |

**Do not interpret `getGenericParameterTypes()` as "getting the real type of the object being passed in"**. Both read the **declaration of the method/constructor**, not the data of parameter instances at application runtime.

## 2. Root Cause: Type Erasure in Java

Java generics primarily perform compile-time type checking. After compilation, JVM method descriptors use types with most generic information removed (**type erasure**). Example declarations:

```java
void save(java.util.List<String> values) {}
void accept(T number) {}
```

This is an **illustrative snippet**, and `T` must be declared at the class or method level. If `T extends Number`, the erased type of `T` is `Number`. `List<String>` has erased type `List`. The `String` part and type variable `T` can be written into the class file's generic signature attribute, enabling Reflection to reconstruct `Type` with richer detail.

Core rules:

1. `List<String>` and `List<Integer>` have the **same erased type `List`**; therefore, you cannot have two overloads differing only in these two generic arguments.
2. For `<T extends Number & Comparable<T>>`, the erasure of `T` is the **first bound** `Number`. For a type variable with no explicit bound, the implicit bound is `Object`.
3. If the parameter type is `T[]`, after erasure `T` becomes its first bound, so the parameter descriptor is an array of that bound type. The generic form can still be `GenericArrayType`.
4. `String...` is varargs parameter syntax; in the JVM, the corresponding parameter type is **`String[]`**. `Executable.isVarArgs()` indicates whether the executable is declared as varargs.
5. `getGenericParameterTypes()` does not guarantee every `Type` is a `ParameterizedType`: non-generic types such as `int`, `String`, or `String[]` are usually still represented by `Class<?>`.

Thus the two APIs do not conflict: one provides the type list for the **runtime signature**, while the other preserves the **generic semantics of the declaration** when data is available.

## 3. Complete, Compilable, and Runnable Java 17+ Example

Create the file **`ParameterKindsDemo.java`** with the following code (without a `package` declaration):

```java
import java.lang.reflect.*;
import java.util.*;

public class ParameterKindsDemo {
    public ParameterKindsDemo(List<Integer> values) {}

    public static <T extends Number & Comparable<T>> void analyze(
            List<String> names,
            Map<String, ? extends Number> scores,
            T value,
            T[] history,
            List<? super Integer> sink,
            String... tags) {}

    private static String kind(Type type) {
        if (type instanceof Class<?>) return "Class";
        if (type instanceof ParameterizedType) return "ParameterizedType";
        if (type instanceof TypeVariable<?>) return "TypeVariable";
        if (type instanceof GenericArrayType) return "GenericArrayType";
        if (type instanceof WildcardType) return "WildcardType";
        return "Other";
    }

    private static void describe(Executable executable) {
        System.out.println("member: " + (executable instanceof Method
                ? executable.getName() : "<init>"));
        System.out.println("varargs: " + executable.isVarArgs());
        Class<?>[] erased = executable.getParameterTypes();
        Type[] generic = executable.getGenericParameterTypes();
        for (int i = 0; i < erased.length; i++) {
            System.out.println(i + ": " + erased[i].getTypeName()
                    + " | " + generic[i].getTypeName()
                    + " | " + kind(generic[i]));
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterKindsDemo.class.getDeclaredMethod(
                "analyze", List.class, Map.class, Number.class,
                Number[].class, List.class, String[].class);
        describe(method);
        Constructor<ParameterKindsDemo> constructor =
                ParameterKindsDemo.class.getDeclaredConstructor(List.class);
        describe(constructor);

        ParameterizedType map = (ParameterizedType)
                method.getGenericParameterTypes()[1];
        WildcardType wildcard = (WildcardType) map.getActualTypeArguments()[1];
        System.out.println("upper bound: "
                + Arrays.toString(wildcard.getUpperBounds()));
        TypeVariable<Method> t = method.getTypeParameters()[0];
        System.out.println("T bounds: " + Arrays.toString(t.getBounds()));
    }
}
```

In the directory containing the file, run:

```bash
javac ParameterKindsDemo.java
java ParameterKindsDemo
```

**Verified output:**

```text
member: analyze
varargs: true
0: java.util.List | java.util.List<java.lang.String> | ParameterizedType
1: java.util.Map | java.util.Map<java.lang.String, ? extends java.lang.Number> | ParameterizedType
2: java.lang.Number | T | TypeVariable
3: java.lang.Number[] | T[] | GenericArrayType
4: java.util.List | java.util.List<? super java.lang.Integer> | ParameterizedType
5: java.lang.String[] | java.lang.String[] | Class
member: <init>
varargs: false
0: java.util.List | java.util.List<java.lang.Integer> | ParameterizedType
upper bound: [class java.lang.Number]
T bounds: [class java.lang.Number, java.lang.Comparable<T>]
```

**Line-by-line analysis:**

- Parameter 0: `List<String>` is erased to `List`. `getParameterTypes()[0]` returns `List.class`; `getGenericParameterTypes()[0]` is a `ParameterizedType` retaining the type argument `String`.
- Parameter 1: `Map<String, ? extends Number>` is erased to `Map`. The generic form keeps both type arguments; the second is a `WildcardType` with upper bound `Number`.
- Parameter 2: `T` is erased to `Number` via its first bound. The generic form is a `TypeVariable` named `T`.
- Parameter 3: `T[]` has erasure `Number[]`, while the generic form is a `GenericArrayType` whose component type is `T`.
- Parameter 4: `List<? super Integer>` is erased to `List`, but the generic form preserves the wildcard with lower bound `Integer`.
- Parameter 5: `String...` is `String[]` in both results, and `isVarArgs()` is `true`. Not every `Type` in the generic array is a complex generic construct.
- Constructor taking `List<Integer>`: the two APIs behave the same as on a method; the constructor has a `ParameterizedType` for this parameter.
- `method.getTypeParameters()[0]` retrieves the **type variable declared by the method `<T ...>`**. `getBounds()` reports the two bounds `Number` and `Comparable<T>`, while erasure takes the first bound.

The concrete implementation class names of `ParameterizedType` or `TypeVariable` are decided by the JDK; the example only prints stable `Type` **interfaces** instead of relying on internal names like `ParameterizedTypeImpl`.

## 4. Working Properly with the `Type` Model

`java.lang.reflect.Type` is the common interface. The forms to understand:

| `Type` Form | Declared Type Example | How to Analyze |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]`, raw `List` | `Class#getName()`, `isArray()`, `getComponentType()` |
| `ParameterizedType` | `List<String>`, `Map<String, List<Integer>>` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `TypeVariable<?>` | `T` in `<T extends Number>` | `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `GenericArrayType` | `T[]`, `List<String>[]` in valid signatures | `getGenericComponentType()` |
| `WildcardType` | `? extends Number`, `? super Integer` | `getUpperBounds()`, `getLowerBounds()` |

A `WildcardType` typically appears **inside the type arguments of a `ParameterizedType`** (e.g., `List<? super Integer>`), not necessarily as a `Type` returned directly for a formal parameter; Java does not allow declaring a parameter whose standalone type is `?`.

Example inspecting generic arguments in `Map<String, ? extends Number>` based on `method` from the program in section 3:

```java
Type parameter = method.getGenericParameterTypes()[1];

if (parameter instanceof ParameterizedType p) {
    System.out.println(p.getRawType().getTypeName()); // java.util.Map
    for (Type argument : p.getActualTypeArguments()) {
        System.out.println(argument.getTypeName());
    }
}
```

This is a **code snippet placed inside a method**. The two arguments are `java.lang.String` and `? extends java.lang.Number`, respectively. If you need to read bounds, check `argument instanceof WildcardType` and then use `getUpperBounds()`/`getLowerBounds()`. Do not cast a wildcard directly to `Class<?>`.

For `T[]`, if `type instanceof GenericArrayType array`, inspect `array.getGenericComponentType()`: here it is type variable `T`. If the parameter type was originally a regular array like `String[]`, `type instanceof Class<?> clazz` and `clazz.isArray()` is true; these are two different handling paths.

### Raw Types and Missing Detailed Generic Information

If a parameter is declared as **`List values`** (raw type), `getGenericParameterTypes()` may return a `Class` corresponding to `List.class`. There is no `String`/`Integer` to infer. If the class file lacks or does not retain appropriate generic metadata, the API cannot recover type arguments from runtime data. You must supply a separate schema, `Type` token, or metadata if logic depends on generic arguments.

Do not use the `type.getTypeName()` string as the sole input to parse generics: string formatting is convenient for display, but to build a reliable schema you should traverse the `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType` structures.

## 5. Looking Up Executables: Use Erased Types

`Class.getDeclaredMethod(String, Class<?>...)` and `Class.getMethod(String, Class<?>...)` accept **`Class<?>` of the formal parameter types**, not `ParameterizedType` objects. In the section 3 example, the correct lookup call is:

```java
Method method = ParameterKindsDemo.class.getDeclaredMethod(
        "analyze",
        List.class,
        Map.class,
        Number.class,
        Number[].class,
        List.class,
        String[].class);
```

This is a **code snippet** that can be placed inside a method declared with `throws NoSuchMethodException`. Passing `Number.class`/`Number[].class` for `T`/`T[]` matches the erasure of the bounded variable; `String[].class` is the correct descriptor for varargs `String...`. `List<String>.class` or `List<Integer>.class` **do not exist in Java class literal syntax**.

For example, the following two declarations in the same class are **invalid**, because they share the same name and erasure:

```java
// Compile error illustration: name clash (do not place both in an actual class)
void handle(List<String> values) {}
void handle(List<Integer> values) {}
```

If you are writing a method overload selector, do not compare generic arguments as though the JVM distinguishes two overloads with the same erased signature. Use `Class<?>[]` for lookup, then inspect `Type[]` for business policies (such as validation/serialization).

### Generic Signatures Are Not Dynamic Data Type Checks

Suppose `void save(List<String> values)` is declared. `getGenericParameterTypes()[0]` may describe `List<String>`, but that does not mean runtime verifies every element inside a `List` is always a `String`. With raw types, unchecked casts, or reflection, actual data may not conform to the Java source generic intent. A serializer library wishing to verify data must validate values and enforce its own policy.

## 6. `Parameter`, Parameter Names, and Type-Use Annotations

In addition to the two arrays above, `Executable` also provides:

- `getParameters()` → `Parameter[]`: metadata of each formal parameter, name (if present), modifiers, implicit/synthetic status.
- `Parameter.getType()` → `Class<?>` (erased).
- `Parameter.getParameterizedType()` → `Type` (generic information of that parameter).
- `getAnnotatedParameterTypes()` → `AnnotatedType[]`: type-use annotations at the parameter type site (for example, `@NonNull` placed on a type use if the annotation supports `ElementType.TYPE_USE` and is retained at runtime).
- `getParameterCount()` → number of formal parameters in the executable model.
- `isVarArgs()` → distinguishes varargs declarations from regular array parameters.
- `getTypeParameters()` → `TypeVariable<?>[]` declared on the executable (distinct from the `Type[]` array of parameters).

**Compiling with `javac -parameters`** writes source parameter names into the class file so `Parameter.getName()` can provide actual names (under appropriate conditions), and `isNamePresent()` indicates whether names are present. It **is not a flag that enables generic signatures**. `getGenericParameterTypes()` can still read generic signatures from normally compiled bytecode when that metadata exists.

For example, if `method.getParameters()[0].getName()` returns a name like `arg0`, you cannot conclude that the parameter's generic type has disappeared; name metadata and generic metadata are two separate mechanisms.

## 7. Subtle Pitfall: Implicit Parameters in Inner Class Constructors

Some constructors have **implicit or synthetic parameters** generated by the compiler, especially constructors of non-static inner classes. The Javadoc for `Executable.getGenericParameterTypes()` warns that **the number of elements may differ from `getParameterTypes()`**, depending on whether the class file has generic information: when generic information is present, the API may report only the parameters explicitly declared in source; implicit/synthetic parameters may not appear in the generic array.

Here is a standalone Java 17+ example. Create the file **`InnerReflectionDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class InnerReflectionDemo {
    class Inner {
        Inner(List<String> names) {}
    }

    public static void main(String[] args) {
        Constructor<?> c = Inner.class.getDeclaredConstructors()[0];
        System.out.println("raw count: " + c.getParameterTypes().length);
        System.out.println("generic count: " + c.getGenericParameterTypes().length);

        for (Class<?> type : c.getParameterTypes()) {
            System.out.println("raw: " + type.getTypeName());
        }
        for (Type type : c.getGenericParameterTypes()) {
            System.out.println("generic: " + type.getTypeName());
        }
    }
}
```

Run:

```bash
javac InnerReflectionDemo.java
java InnerReflectionDemo
```

Verified output with standard `javac`:

```text
raw count: 2
generic count: 1
raw: InnerReflectionDemo
raw: java.util.List
generic: java.util.List<java.lang.String>
```

Class `Inner` is a non-static inner class, so the JVM constructor receives a **reference to an instance of `InnerReflectionDemo`** for the enclosing instance; this parameter is not written in the source constructor `Inner(List<String> names)`. Thus `getParameterTypes()` lists two runtime parameters (`InnerReflectionDemo` and `List`), while the generic signature describes the explicitly declared parameter `List<String>`.

**Consequence:** Do not assume `getParameterTypes()[i]` always corresponds to `getGenericParameterTypes()[i]` on every executable; the `for` loop in the section 3 example **was written for methods/constructors without implicit parameters**, not as a general-purpose generic analyzer for all constructors. Before pairing by index, check array lengths and implicit/synthetic parameters; if per-parameter metadata is needed, consider `getParameters()` along with `Parameter.getParameterizedType()` and the class's compilation characteristics. Cases such as enum constructors, inner classes, or tool-generated bytecode must be handled specifically rather than guessing index alignment.

Because of this metadata discrepancy, a general Reflection-based program should avoid assuming the two arrays have equal lengths. `ArrayIndexOutOfBoundsException` or assigning the wrong generic type to the enclosing instance can occur if you blindly loop up to `getParameterTypes().length` and read `generic[i]`.

## 8. Edge Cases and Exceptions When Reading Generic Signatures

Generic Reflection APIs rely on compiled/provided signature metadata. Per the Javadoc of `Executable.getGenericParameterTypes()`, several errors can occur when reading invalid or inconsistent bytecode signatures:

| Exception / Error | Cause |
| --- | --- |
| `GenericSignatureFormatError` | The generic signature in the class file does not conform to the JVM format |
| `TypeNotPresentException` | The generic signature references a type that cannot be found |
| `MalformedParameterizedTypeException` | A parameterized type in the signature cannot be instantiated under the reflection model |

These do not occur during normal Java compilation on a consistent classpath/module path, but they are relevant when handling legacy bytecode, bytecode generators, shading, version mismatches, or missing libraries. Do not use `catch (Exception)` to silently treat any malformed signature as "non-generic"; `GenericSignatureFormatError` is an `Error`, not an `Exception`.

Other notes:

- `getDeclaredMethods()` can see compiler-generated **bridge/synthetic methods**. When inferring source APIs, check `Method.isBridge()`/`isSynthetic()`; a bridge method has a different erased signature from the source method.
- A raw type in a signature may simply be represented by `Class<?>`; `getGenericParameterTypes()` does not promise to return `ParameterizedType` for every parameter.
- For `TypeVariable`, bounds of a method/class are declared independently; the same name `T` in two methods is not necessarily the same declaration. You can use `getGenericDeclaration()` to see which declaration owns the type variable.
- `getGenericParameterTypes()` preserves generic information still present in the **declaration**; it cannot reconstruct `List<String>` from a `List<?>` passed by a caller or infer `String` from current elements.

## 9. Workflow When Building a Framework

1. **Determine the goal:** do you need to find an executable/invoke a method by JVM signature, or understand the generic contract for JSON conversion, binding, or validation?
2. **Look up the executable using erased types:** use `getDeclaredMethod(name, Class<?>...)`, `getDeclaredConstructor(Class<?>...)`, or list and filter. For overloads, the number/types of erased formal parameters are key facts.
3. **Read the generic contract:** call `getGenericParameterTypes()` (or `Parameter.getParameterizedType()` if per-parameter metadata is needed) and inspect `Type` according to its actual kind.
4. **Handle type variables, wildcards, and generic arrays:** traverse the `Type` structure; do not cast every `Type` to `Class<?>`. If you need to resolve `T` in a concrete subclass, you must have **contextual bindings** from generic superclasses/interfaces or a type token; Reflection does not automatically substitute `T` with call-site type arguments.
5. **Be careful with implicit parameters:** if it is a special constructor, do not align the two arrays by index before confirming correspondence.
6. **Validate real inputs at runtime:** generic signatures describe declarations, while actual data requires separate validation.
7. **Report metadata errors transparently:** handle invalid signatures or missing dependencies; do not construct wrong schemas when generic information is insufficient.

Examples of choosing the right API:

| Goal | Prefer |
| --- | --- |
| Find a method with parameter `List<String>` in a class | `getDeclaredMethod("name", List.class)` |
| Determine declared list element type | `getGenericParameterTypes()` then read `ParameterizedType.getActualTypeArguments()` |
| Find bounds of `T extends Number` | `TypeVariable.getBounds()` |
| Check whether a method has varargs | `Executable.isVarArgs()` |
| Analyze type-use annotations | `getAnnotatedParameterTypes()` |
| Get source parameter names if metadata remains | `getParameters()` and `Parameter.isNamePresent()` |
| Invoke method with arguments at runtime | Prepare objects matching erased types then call `Method.invoke(...)`; do not use `ParameterizedType` as a runtime `Class` |

## 10. Common Pitfalls and Self-Check Exercises

| Misconception | Correct Understanding |
| --- | --- |
| "The two APIs only differ in array return type; the information is the same." | One gives erased `Class<?>`; the other provides `Type` structures describing the generic declaration. |
| "`getGenericParameterTypes()[0]` is always a `ParameterizedType`." | It can be `Class`, `TypeVariable`, or `GenericArrayType`, depending on the declaration. |
| "`getParameterTypes()` gives `List<String>`." | The result is `List.class`; generic arguments are erased. |
| "You can cast `Type` to `Class<?>` for every parameter." | Casting fails on parameterized types, type variables, and generic arrays. |
| "Both arrays always have the same length." | Inner class constructors with implicit parameters can cause different sizes. |
| "`-parameters` is what makes generic Reflection work." | That flag mainly stores **parameter names**, not a general requirement for storing generic signatures. |
| "`List<String>` metadata proves every element in a runtime List is a String." | Generic types on declarations do not replace runtime data validation. |
| "You can overload `handle(List<String>)` and `handle(List<Integer>)`." | Both signatures have the same erasure and clash in the same declaration scope. |

**Exercise 1.** Given `void f(List<? extends CharSequence> x, int[] y)`. Predict the two arrays from `getParameterTypes()` and `getGenericParameterTypes()`, and explain why `int[]` is usually `Class<?>` in both.

**Exercise 2.** Given `<T extends Serializable & Comparable<T>> void f(T x, T[] xs)`. Predict the erasure of both parameters and how to retrieve both bounds. `Serializable` is the first bound in this declaration.

**Exercise 3.** Use `ParameterizedType` to extract `String` from `List<String>`, then replace the parameter with `List<? super Integer>` and inspect the lower bounds of `WildcardType`.

**Exercise 4.** Create a non-static inner class with a constructor taking `List<String>`, run the section 7 example, and explain the difference in element counts.

**Exercise 5.** Write lookup logic for the `analyze` method in section 3 using `getDeclaredMethod` without any generic `Type`, then use `getGenericParameterTypes` to display the full list of declared types.

**Remember:** `getParameterTypes()` gives **`Class<?>[]` for the erased signature**, whereas `getGenericParameterTypes()` gives **`Type[]` reflecting the generic signature when metadata is present**. Choose the API according to your goal, inspect the `Type` forms properly, and especially never assume the two arrays always map 1:1 in constructors with implicit parameters.

## 11. Official References

- [Java SE 17 Javadoc — `Executable.getParameterTypes` and `getGenericParameterTypes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html) — semantics, notes on implicit parameters, and exceptions when reading signatures.
- [Java SE 17 Javadoc — `ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html) — `getActualTypeArguments`, `getRawType`.
- [Java SE 17 Javadoc — `TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html) — `getName`, `getBounds`, and declaration.
- [Java SE 17 Javadoc — `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html) — generic component type.
- [Java SE 17 Javadoc — `WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html) — upper/lower bounds.
- [Java SE 17 Javadoc — `Class.getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredMethod(java.lang.String,java.lang.Class...)) — looking up methods by a list of `Class<?>`.
- [Java Language Specification `4.6 Erasure`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6) — generic type erasure rules.
