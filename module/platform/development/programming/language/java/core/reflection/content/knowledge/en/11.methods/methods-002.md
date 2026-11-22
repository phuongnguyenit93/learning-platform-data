# Method Reflection: parameter types, `throws` types, and generic variants

When using Java Reflection to inspect a method signature, there are **two perspectives to distinguish**:

1. **Runtime type after type erasure** (*erased/raw runtime type*) — represented by `Class<?>`. This is the type the JVM uses to determine the method descriptor and check arguments when invoking via reflection.
2. **Generic type declared in source code** (*generic signature*) — represented by `java.lang.reflect.Type` and its subtypes. This is metadata for documentation tools, mapping libraries, injection, and type-contract inspection.

For example, a parameter `List<? super T>` has **runtime type** `java.util.List` but **generic type** `ParameterizedType` representing `List<? super T>`. A `T...` parameter can be a `Number[]` array at runtime if `T extends Number`, while the generic signature still represents `T[]`.

On a `java.lang.reflect.Method` object, the four core APIs are:

| Metadata to read | After erasure | Preserves generic signature |
| --- | --- | --- |
| Method parameters | `getParameterTypes(): Class<?>[]` | `getGenericParameterTypes(): Type[]` |
| Declared `throws` types | `getExceptionTypes(): Class<?>[]` | `getGenericExceptionTypes(): Type[]` |
| Return type (for comparison) | `getReturnType(): Class<?>` | `getGenericReturnType(): Type` |
| Type parameters declared by the method itself | — | `getTypeParameters(): TypeVariable<Method>[]` |

**Key takeaway:** The APIs containing `Generic` are used to *describe* declared types. They do not recover the generic type arguments of arbitrary objects at runtime, do not automatically inspect the contents of a collection, and do not alter Java's type erasure rules.

## 1. Obtaining the right `Method` object before analyzing its signature

Consider a method declared as follows:

~~~java
public <T extends Number & Comparable<T>, E extends Exception>
java.util.List<? extends T> query(
        java.util.List<? super T> destination, T... values)
        throws java.io.IOException, E {
    // Method body
    return java.util.Collections.emptyList();
}
~~~

This is a **signature illustration snippet**, not a standalone Java class. It includes:

- **Two method parameters:** `List<? super T> destination` and `T... values`.
- **Two type parameters declared by the method:** `T`, `E`; `T` has two bounds (`Number`, `Comparable<T>`); `E` has bound `Exception`.
- **Generic return type:** `List<? extends T>`.
- **Two types in the `throws` clause:** `IOException` and `E`.

To look up the method using reflection, `getDeclaredMethod` requires **the name + the parameter types after erasure**; do not pass `List<? super T>` or `T[]` as generic expressions. With a `Service` class containing this method:

~~~java
Method method = Service.class.getDeclaredMethod(
        "query",
        java.util.List.class,
        Number[].class
);
~~~

`T` has its first bound as `Number`, so `T...` has the runtime array type `Number[]`. If you look it up using `Object[].class` or `Integer[].class`, it will not match the descriptor and you will get `NoSuchMethodException`.

Distinguishing lookup methods:

- `getDeclaredMethod(name, parameterTypes...)`: looks up a method declared **directly** on the inspected class/interface, including non-public methods; does not automatically search inherited methods.
- `getMethod(name, parameterTypes...)`: looks up a **public method** via the corresponding lookup mechanism, taking inherited public methods into account.
- Two methods with the same name and different parameter lists are overloads; Reflection looks up by **erased parameter types**, not by return type for caller-side overload selection.
- `Class.getDeclaredMethods()` does not guarantee source-code order; if displaying a list of methods to users, sort by name and normalized signature.

## 2. `getParameterTypes()`: runtime parameter types

API declaration:

~~~java
Class<?>[] parameters = method.getParameterTypes();
~~~

Each element is a `Class` object representing a **formal parameter type after erasure**. For `query`, for example:

~~~text
java.util.List
java.lang.Number[]
~~~

Here:

- `List<? super T>` is erased to `List`.
- `T...` takes array form when compiled; `T extends Number & Comparable<T>` erases to its first bound `Number`, so the result is `Number[]`.
- `getParameterTypes()` does not reveal `? super T`, the name `T`, or additional bounds.
- Primitive types remain primitive tokens, such as `int.class`; array parameters like `String[]` remain the array class `String[].class`.

This `Class<?>[]` is suitable for comparing descriptors, identifying overloaded methods, or preparing Reflection arguments. It **does not prove** that an actual `List` instance contains elements of the expected generic type.

### Trailing varargs parameter

`T... values` is represented by the JVM as an **array parameter**. Information on whether "this is a varargs declaration" is retrieved separately via `Method.isVarArgs()`:

~~~java
boolean declaredVarargs = method.isVarArgs();
~~~

For example, `void a(String[] names)` and `void b(String... names)` both have parameter type `String[].class`, yet only `b` has `isVarArgs() == true`. With `Method.invoke`, you must respect the number of formal parameters and the erased array type; do not assume Reflection automatically packs an argument list using regular Java varargs syntax.

## 3. `getGenericParameterTypes()`: parameter types with generic metadata

Declaration:

~~~java
Type[] genericParameters = method.getGenericParameterTypes();
~~~

For `query`, `Type.getTypeName()` respectively yields:

~~~text
java.util.List<? super T>
T[]
~~~

These are not two ordinary `Class` objects:

- `List<? super T>` is a **`ParameterizedType`** with raw type `List.class` and one type argument that is a **`WildcardType`** containing lower bound `T`.
- `T[]` is a **`GenericArrayType`** because the array component is type variable `T`. `getGenericComponentType()` returns the corresponding `TypeVariable`.
- If a parameter type is declared directly as `T` (without an array), the `Type[]` element can itself be a `TypeVariable`.
- If a parameter is `String`, `int`, or `String[]` without a generic component, the result is typically a `Class` object.

Therefore, **do not cast every `Type` to `Class<?>`**:

~~~java
Type generic = method.getGenericParameterTypes()[0];

if (generic instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
}
~~~

This is a metadata-inspection snippet that can be placed inside a method; the `method` variable must be initialized beforehand. When inspecting `arguments[0]` of `List<? super T>`, we encounter `WildcardType`:

~~~java
Type argument = ((ParameterizedType) generic)
        .getActualTypeArguments()[0];

if (argument instanceof WildcardType wildcard) {
    Type[] lower = wildcard.getLowerBounds(); // Contains T in this example.
    Type[] upper = wildcard.getUpperBounds(); // Object when there is no explicit extends bound.
}
~~~

**`? super T` and `? extends T` are not the same:** a wildcard's lower bound describes the side "allowed to accept" a type, whereas an upper bound describes the side "upper-bounded" in the type relationship. Reflection reads this signature, but does not replicate full compiler type-checking logic.

## 4. Variants of `Type` to recognize

`java.lang.reflect.Type` is the common interface for several signature forms:

| Declaration form | Common `Type` kind | What to inspect? |
| --- | --- | --- |
| `String`, `int`, `String[]` | `Class<?>` | `getTypeName()`, `isArray()`, `getComponentType()` when appropriate |
| `List<String>` | `ParameterizedType` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` when it is a nested type |
| `T` | `TypeVariable<?>` | `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `T[]` | `GenericArrayType` | `getGenericComponentType()` |
| `? extends Number` / `? super T` | `WildcardType` | `getUpperBounds()` / `getLowerBounds()` |

**Classification example:**

~~~java
static String kind(Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof ParameterizedType) return "ParameterizedType";
    if (type instanceof TypeVariable<?>) return "TypeVariable";
    if (type instanceof GenericArrayType) return "GenericArrayType";
    if (type instanceof WildcardType) return "WildcardType";
    return "Other Type";
}
~~~

This is an illustrative method requiring `import java.lang.reflect.*`. In practice, a `ParameterizedType` can further contain `ParameterizedType`, `WildcardType`, `TypeVariable`, or `GenericArrayType`. To build the full generic signature tree, you must process it **recursively**, not just print raw types.

### Does the type variable live on the method or on the class?

Two signatures may both use the name `T` while coming from different declaration sources:

~~~java
class Container<T> {
    T read() { return null; }         // T belongs to the class.
    <U> U convert(U input) { return input; } // U belongs to the method.
}
~~~

For `read`, `getGenericReturnType()` can be a `TypeVariable` **declared by `Container`**; `read.getTypeParameters()` returns an empty array because the method declares no new type variables. For `convert`, `getTypeParameters()` contains `U`, and `U.getGenericDeclaration()` points to the `convert` method itself. Do not confuse metadata of a class-level type parameter with a method-level type parameter.

**Important limitation:** when running `Container<String>`, Java Reflection on `Method` does not automatically infer that "`T` is now `String`" from an instance. To substitute a class's type variable with a concrete type argument, you must analyze the `ParameterizedType` context from a generic superclass/interface or a suitable type token; much of this information is erased at runtime.

## 5. `getExceptionTypes()`: types in the `throws` clause after erasure

API declaration:

~~~java
Class<?>[] exceptionTypes = method.getExceptionTypes();
~~~

Given:

~~~java
<T extends Number & Comparable<T>, E extends Exception>
void query(T item) throws java.io.IOException, E { }
~~~

`getExceptionTypes()` returns the classes:

~~~text
java.io.IOException
java.lang.Exception
~~~

Reason: `E` is erased to its first bound `Exception`. If a method declares `<X extends IOException> void fail() throws X`, the raw type will be `IOException.class`.

Important notes:

- This is the **list of exception types declared in `throws`**, not the list of every exception the method *might actually throw*.
- A method without a `throws` clause → empty array, even though it can still throw unchecked exceptions such as `NullPointerException` or `IllegalArgumentException`.
- Java allows declaring an unchecked exception in `throws`; Reflection will record it if present in the signature.
- `Error` or unchecked exceptions can arise outside the declaration; do not use `getExceptionTypes()` to prove "the method never fails".
- `getExceptionTypes()` does not tell you the type variable name or the relationship between that type variable and the method's parameters.

## 6. `getGenericExceptionTypes()`: preserving `throws E`

API:

~~~java
Type[] genericExceptions = method.getGenericExceptionTypes();
~~~

For `query(...) throws IOException, E`, the two elements have signatures:

~~~text
java.io.IOException
E
~~~

Of these, the first element is typically `Class<IOException>`, and the second is a `TypeVariable` named `E`. You can access the bounds:

~~~java
for (Type type : method.getGenericExceptionTypes()) {
    if (type instanceof TypeVariable<?> variable) {
        System.out.println(variable.getName());
        System.out.println(java.util.Arrays.toString(variable.getBounds()));
    }
}
~~~

If `E extends Exception`, the bound is `Exception.class`; if `X extends IOException`, the bound is `IOException.class`.

### Why is generic `throws` useful?

Declaration:

~~~java
static <X extends Exception> void propagate(X problem) throws X {
    throw problem;
}
~~~

This is a **standalone illustrative method**, placed inside a class to compile. It tells the compiler that the exception type passed in and the exception type that can be thrown are linked by the **same type variable `X`**. After erasure, Reflection's `getExceptionTypes()` only has `Exception.class`; `getGenericExceptionTypes()` still represents `X`. API analysis libraries can use this metadata to display a more accurate contract.

**Do not confuse generic `throws` with `List<IOException>` in throws:** Java does not allow parameterizing an exception class such as `SomeException<T> extends Exception`, because a generic class cannot directly or indirectly inherit from `Throwable`. A type variable with an exception bound (`<E extends Exception> ... throws E`) is the valid mechanism for declaring generic throws.

### What happens to exceptions when Reflection invokes a method?

`Method.invoke(receiver, args...)` does not pass checked exceptions of the called method directly to the caller like a normal Java call. If the method body throws an exception, `invoke` wraps it in **`InvocationTargetException`**; you can inspect `getCause()`. In addition, Reflection itself can throw `IllegalAccessException`, `IllegalArgumentException`, or other call-related errors. The `getGenericExceptionTypes()` list only describes the **signature of the target method**, and does not replace the exception contract of `Method.invoke`.

## 7. `getTypeParameters()` and erasure with multiple bounds

API:

~~~java
TypeVariable<Method>[] variables = method.getTypeParameters();
~~~

With:

~~~java
<T extends Number & Comparable<T>, E extends Exception>
~~~

we get:

- `T.getName()` → `"T"`.
- `T.getBounds()` → `Number` and `Comparable<T>`; the first bound is the class `Number`, and the second bound is a parameterized interface.
- `E.getName()` → `"E"`.
- `E.getBounds()` → `Exception.class`.

The rule for **erasure of a type variable** uses the leftmost (first) bound. If only `<T>` is declared, the implicit upper bound is `Object`, so the erasure of `T` is `Object`. Having multiple bounds does not mean the JVM has a concrete "intersection type" as a parameter; the descriptor uses erasure according to JLS rules.

`getTypeParameters()` returns only type variables declared by the **method**. It does not represent every type variable appearing in the parameters: they may also be declared by the enclosing class.

## 8. Complete runnable Java 17+ example comparing all four APIs

Create a single file **`MethodSignatureDemo.java`**. The example intentionally uses:

- Parameterized type `List<? super T>`.
- Generic array `T...` erasing to `Number[]`.
- Wildcard return `List<? extends T>`.
- Generic `throws IOException, E` and method `fail` declaring `throws X`.
- Inspecting bounds of `T` and `E`.
- `Parameter.isNamePresent()` to detect whether parameter names were saved during compilation.

~~~java
import java.io.IOException;
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.Collectors;

public class MethodSignatureDemo {
    static class Service {
        @SafeVarargs
        public final <T extends Number & Comparable<T>, E extends Exception>
        List<? extends T> query(List<? super T> destination, T... values)
                throws IOException, E {
            for (T value : values) {
                destination.add(value);
            }
            return Collections.emptyList();
        }

        public void text(String[] names) throws IOException { }

        public <X extends IOException> void fail(X problem) throws X {
            throw problem;
        }
    }

    private static String types(Type[] xs) {
        return Arrays.stream(xs).map(Type::getTypeName).collect(Collectors.joining(" | "));
    }

    private static String classes(Class<?>[] xs) {
        return Arrays.stream(xs).map(Class::getTypeName).collect(Collectors.joining(" | "));
    }

    public static void main(String[] args) throws Exception {
        Method m = Service.class.getDeclaredMethod("query", List.class, Number[].class);
        System.out.println("params raw: " + classes(m.getParameterTypes()));
        System.out.println("params generic: " + types(m.getGenericParameterTypes()));
        System.out.println("return raw: " + m.getReturnType().getTypeName());
        System.out.println("return generic: " + m.getGenericReturnType().getTypeName());
        System.out.println("throws raw: " + classes(m.getExceptionTypes()));
        System.out.println("throws generic: " + types(m.getGenericExceptionTypes()));
        System.out.println("vars: " + Arrays.stream(m.getTypeParameters()).map(TypeVariable::getName)
                .collect(Collectors.joining(" | ")));

        for (TypeVariable<Method> variable : m.getTypeParameters()) {
            System.out.println("bound " + variable.getName() + ": " + types(variable.getBounds()));
        }

        System.out.println("isVarArgs: " + m.isVarArgs());
        System.out.println("second is GenericArrayType: "
                + (m.getGenericParameterTypes()[1] instanceof GenericArrayType));
        System.out.println("first is ParameterizedType: "
                + (m.getGenericParameterTypes()[0] instanceof ParameterizedType));
        System.out.println("names present: "
                + Arrays.stream(m.getParameters()).allMatch(Parameter::isNamePresent));

        Method fail = Service.class.getDeclaredMethod("fail", IOException.class);
        System.out.println("fail raw throws: " + classes(fail.getExceptionTypes()));
        System.out.println("fail generic throws: " + types(fail.getGenericExceptionTypes()));
    }
}
~~~

Compile in the file's directory using **JDK 17 or later**. Omit `-parameters` in the first command to verify the case where parameter names are **not stored**:

~~~bash
javac --release 17 -Xlint:all MethodSignatureDemo.java
java MethodSignatureDemo
~~~

**Exact stdout** (compiled/run with the command above):

~~~text
params raw: java.util.List | java.lang.Number[]
params generic: java.util.List<? super T> | T[]
return raw: java.util.List
return generic: java.util.List<? extends T>
throws raw: java.io.IOException | java.lang.Exception
throws generic: java.io.IOException | E
vars: T | E
bound T: java.lang.Number | java.lang.Comparable<T>
bound E: java.lang.Exception
isVarArgs: true
second is GenericArrayType: true
first is ParameterizedType: true
names present: false
fail raw throws: java.io.IOException
fail generic throws: X
~~~

Observations on easily misunderstood points:

1. `getParameterTypes()` erased `List<? super T>` to `List` and `T[]` to `Number[]`, while `getGenericParameterTypes()` kept the signature with the wildcard/type variable.
2. `getExceptionTypes()` returned `Exception` for `E`, whereas `getGenericExceptionTypes()` returned the type variable `E`. The `fail` method is similar, erasing `X` to `IOException`.
3. `getTypeParameters()` and `getBounds()` preserved the constraint `T extends Number & Comparable<T>`.
4. `isVarArgs()` confirmed the `...` in source; `getParameterTypes()` only sees the array type.
5. `names present: false` because the `javac` command above did **not** use `-parameters`. This is parameter-name metadata from the class file, **independent** of whether the generic signature is retained.

If recompiled with:

~~~bash
javac --release 17 -parameters MethodSignatureDemo.java
java MethodSignatureDemo
~~~

then the `names present` line will become `true` for the two parameters of `query`, while the type analysis lines above remain unchanged. With other build tools, this result depends on the compiler options of the **class file actually executed**, not on the names displayed in the IDE.

## 9. The `Parameter` API, parameter names, and annotations

`Method.getParameters()` returns a `Parameter[]` array; each element contains metadata for one formal parameter:

~~~java
for (Parameter parameter : method.getParameters()) {
    String name = parameter.getName();
    boolean realName = parameter.isNamePresent();
    Class<?> erased = parameter.getType();
    Type generic = parameter.getParameterizedType();
    boolean varargsParameter = parameter.isVarArgs();
}
~~~

The snippet above is illustrative, requiring `import java.lang.reflect.*` and providing `method`. Related APIs:

- `Parameter.getType()` corresponds to the `Class<?>` perspective; `getParameterizedType()` corresponds to the `Type` perspective.
- `Parameter.getName()` may return a synthesized name such as `arg0` if metadata is absent; **do not treat that name as the name declared in source**. Use `isNamePresent()` to check whether the real name is recorded in the class file.
- `Parameter.isImplicit()` / `isSynthetic()` reflect certain parameters generated by the compiler/language conventions, such as constructors of non-static inner classes or enum constructors. For special bytecode cases, distinguish formal parameters in the class file from the list a developer sees in source.
- `Method.getParameterAnnotations()` and `Parameter.getAnnotations()` return annotations on parameters according to appropriate retention rules. **Type-use** annotations may require the `getAnnotatedParameterTypes()` API to see the declaration location on the type itself (`List<@SomeAnno String>`).

Metadata of **generic method signatures** and **runtime-visible annotations** are two separate sources of information; do not infer generic types solely from an annotation.

## 10. Limitations and common pitfalls

### 10.1. Looking up a Method by generic argument

**Wrong idea:** wanting to retrieve `process(List<String>)`, so calling `getDeclaredMethod` with type `List<String>`. Java has no `List<String>.class` literal. Runtime method lookup uses erased parameter types, so for a `List<String>` parameter you normally just pass `List.class`.

You cannot declare two overloads differing only in `List<String>` vs. `List<Integer>` because both have the same erasure `List` (name clash). Reflection does not recover overloads that the language forbids declaring.

### 10.2. Casting `Type` to `Class<?>`

`(Class<?>) method.getGenericParameterTypes()[0]` can throw `ClassCastException` if the element is a `ParameterizedType`. Check with `instanceof` and handle the appropriate `Type` variant. In nested generic structures, you may need to recursively traverse type arguments and bounds.

### 10.3. Assuming `throws` is all actual exceptions

`getExceptionTypes()` and `getGenericExceptionTypes()` only record the **`throws` declaration**. There is no guarantee the method will throw all those exceptions, nor any guarantee it will not throw other unchecked exceptions. Reflection `Method.invoke` also has the `InvocationTargetException` wrapper class.

### 10.4. Confusing `TypeVariable` with a resolved type

`T extends Number` does not mean Reflection always knows `T` is specifically `Integer`. `T` can exist in `Type` metadata without knowing the type argument in an actual call context. If runtime data validation is needed, an appropriate separate boundary/validator is still required.

### 10.5. Treating `T...` as an arbitrary parameter list

At the method descriptor level, varargs is still **a single trailing array parameter**. `Method.isVarArgs()` helps determine how it is expressed in source, but `getParameterTypes()` returns an array class. Reflection invocation requires arguments matching the erased formal parameter array.

### 10.6. Expecting parameter names to always be present

`-g` and debug information do not completely substitute for retrieving names via `Parameter.isNamePresent()`; use `javac -parameters` when public reflection parameter names are needed. Compilers/build tools may generate bridge/synthetic methods; when scanning APIs, consider `Method.isBridge()`, `Method.isSynthetic()`, and the declaring class context.

### 10.7. Failing to handle malformed metadata

When a generic signature is invalid or a type reference in metadata cannot be resolved, the `getGeneric...` APIs can throw errors such as `GenericSignatureFormatError`, `TypeNotPresentException`, or `MalformedParameterizedTypeException` depending on the case. These are class-file/generic-metadata issues, distinct from a missing method (`NoSuchMethodException`). An introspection tool processing third-party classes should report contextual errors rather than silently replacing malformed generic signatures with guessed types.

## 11. API selection checklist by question

| Question you need answered | Appropriate API |
| --- | --- |
| "What formal parameter types does the method have at runtime?" | `getParameterTypes()` |
| "Does the method have `List<? super T>` or `T[]` in its signature?" | `getGenericParameterTypes()` |
| "What exception types does the method declare after erasure?" | `getExceptionTypes()` |
| "Which type variable is `throws E` bound to?" | `getGenericExceptionTypes()` + `TypeVariable.getBounds()` |
| "What `T, E` with what bounds does the method declare?" | `getTypeParameters()` |
| "Are the real formal parameter names preserved in the class file?" | `getParameters()` + `isNamePresent()` |
| "Is the last parameter declared with `...`?" | `isVarArgs()` |
| "Does the return type have wildcards or generic arguments?" | `getGenericReturnType()` |

When building a reflection tool for methods, the safe workflow is: **identify the `Method` using erased parameter types → read raw `Class<?>[]` metadata to understand the descriptor → read the `Type[]` arrays to understand the generic signature → classify each `Type` and resolve type variables in the proper declaring context**. When displaying reports, clearly state which values are *erased* and which are *generic declarations*.

### Official references

- [Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `getParameterTypes`, `getGenericParameterTypes`, `getExceptionTypes`, `getGenericExceptionTypes`, `getTypeParameters`.
- [Java SE 21 — `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html).
- [Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html).
- [Java Language Specification `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) and [`8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4).