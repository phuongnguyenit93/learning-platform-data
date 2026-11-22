# getParameters and Parameter in Java Reflection

## 1. Goal: Reading Method and Constructor Parameters with Reflection

When building routing, dependency injection, validation, serializer, or API analysis tools, finding a `Method` or `Constructor<?>` is not enough: we also need to know how many parameters it accepts, the type of each parameter, their order, annotations, parameter names (if metadata is available), and whether the last parameter is varargs.

Java places that information in `java.lang.reflect.Executable` and `java.lang.reflect.Parameter`:

- `Method` and `Constructor<?>` both inherit from `Executable`.
- `Executable.getParameters()` returns a `Parameter[]` array, in the exact parameter order of the executable at the Reflection level.
- Each `Parameter` represents **one parameter of a specific executable**. `getDeclaringExecutable()` lets you trace back to the method/constructor that owns the parameter.
- `Parameter` provides `getName()`, `isNamePresent()`, `getType()`, `getParameterizedType()`, `getAnnotatedType()`, `getAnnotations()`, `getAnnotation(...)`, `getModifiers()`, `isImplicit()`, `isSynthetic()`, and `isVarArgs()`.

A parameter named `id`, with type `List<String>`, and annotation `@NotNull` represents three **distinct** layers of metadata. If a class is compiled without name information, Reflection can still know the types, order, and annotations; you should not infer that `getParameters()` returns an empty array.

## 2. Distinguishing Common Lookup APIs

| API | Result | When to Use |
| --- | --- | --- |
| `Executable.getParameterCount()` | Number of parameters seen by Reflection. | Check count before matching arguments. |
| `Executable.getParameters()` | `Parameter[]`, ordered from left to right. | Need name, annotation, modifier, varargs, and generic type for each parameter. |
| `Executable.getParameterTypes()` | `Class<?>[]` containing erased types. | Build Reflection signatures or match runtime arguments. |
| `Executable.getGenericParameterTypes()` | `Type[]`, which may be `ParameterizedType`/`TypeVariable`/`GenericArrayType`. | Need generic declarations. |
| `Executable.getParameterAnnotations()` | `Annotation[][]`, annotations declared on each formal parameter. | When processing multiple parameters by index; `Parameter.getAnnotations()` is more convenient. |
| `Executable.isVarArgs()` | Whether the executable declares varargs at the bytecode level. | Distinguish regular `String[]` from `String...`. |
| `Parameter.getDeclaringExecutable()` | `Method` or `Constructor<?>` owning the parameter. | Build error messages with full context. |
| `Parameter.getName()` | Name read from metadata if present, or fallback name such as `arg0`. | Display; only treat as a source name when `isNamePresent() == true`. |
| `Parameter.getParameterizedType()` | `Type` of that specific parameter, preserving generic declaration. | Analyze `List<String>`, `T`, etc. |
| `Parameter.getAnnotatedType()` | `AnnotatedType` for annotations on the **type use** of the parameter. | Inspect `@Target(TYPE_USE)`. |

`getParameterTypes()` does not contain names or annotations; `getParameters()` provides individual `Parameter` objects but **does not read Java source code itself**. Metadata is generated from the class file/runtime.

## 3. The `-parameters` Compiler Flag and Parameter Names

By default, `javac` **does not necessarily** write parameter names into the class file as Reflection metadata. When the `MethodParameters` attribute containing names is absent, `getParameters()` still returns `Parameter` objects, while:

- `getName()` is typically `arg0`, `arg1`, `arg2`… by position.
- `isNamePresent()` returns `false`.
- `getType()`, `getParameterizedType()`, and parameter annotations are still accessible if their corresponding metadata is stored.

Compiling with `javac -parameters` instructs the compiler to store formal parameter names and modifiers in the class file:

~~~bash
javac -parameters -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

When the class has valid metadata, `getName()` returns the actual compiled name (such as `recipient`), and `isNamePresent() == true`. The `-parameters` flag is a **build-time** option, not `java -parameters` at runtime.

Distinguishing `-parameters` and `-g`:

- `-parameters` writes the `MethodParameters` attribute so Core Reflection can retrieve parameter names.
- `-g`/`-g:vars` controls debug information such as local-variable tables; debug variable names can serve a debugger, but do **not** automatically substitute for `-parameters` for `Parameter.getName()`.
- After obfuscation, transformation, or building with another compiler, metadata may be altered or stripped. Runtime code must check `isNamePresent()` directly rather than guessing from the development environment.

Practical example: a router wanting to auto-map query parameters to Java names can use `isNamePresent()` to decide; if `false`, require an annotation stating the name explicitly or a mapping configuration, instead of exposing the string `arg0` as a public API name.

### Is Name Metadata Required?

No. An executable can still be invoked without stored source names. Parameter names are **not** part of the JVM signature; for example, two methods with the same name and parameter types that differ only in Java variable names cannot be overloaded. Therefore, parameter names are considered metadata for reflection/tooling, not an identifier of method-call behavior.

`getParameters()` can also throw `MalformedParametersException` when `MethodParameters` information in the class file is invalid. When dealing with transformed bytecode or classes from untrusted sources, include a metadata error-handling branch rather than silently assuming valid names.

## 4. Standalone Java 17+ Example: Method, Constructor, Varargs, Annotations, and Generics

Create the file `ParameterMetadataDemo.java`. No Spring or external libraries required.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class ParameterMetadataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Name {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeMark {}

    static class Service {
        Service(String title) {}

        static void dispatch(
                @Name("user") @TypeMark String recipient,
                final int retries,
                String... labels) {
        }

        static <T extends Number> void aggregate(List<T> numbers, T seed) {
        }
    }

    public static void main(String[] args) throws Exception {
        Method dispatch = Service.class.getDeclaredMethod(
                "dispatch", String.class, int.class, String[].class);

        System.out.println("dispatch parameters="
                + dispatch.getParameterCount());
        Parameter[] parameters = dispatch.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter parameter = parameters[i];
            Name annotation = parameter.getAnnotation(Name.class);
            System.out.println(i + ": name=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent()
                    + ", type=" + parameter.getType().getSimpleName()
                    + ", generic=" + parameter.getParameterizedType().getTypeName()
                    + ", varargs=" + parameter.isVarArgs()
                    + ", label=" + (annotation == null ? "-" : annotation.value())
                    + ", typeMark=" + parameter.getAnnotatedType()
                            .isAnnotationPresent(TypeMark.class));
        }

        Method aggregate = Service.class.getDeclaredMethod(
                "aggregate", List.class, Number.class);
        Parameter[] generic = aggregate.getParameters();
        System.out.println("generic first="
                + generic[0].getParameterizedType().getTypeName());
        System.out.println("generic second="
                + generic[1].getParameterizedType().getTypeName());
        System.out.println("erased second="
                + generic[1].getType().getTypeName());

        Constructor<Service> constructor =
                Service.class.getDeclaredConstructor(String.class);
        Parameter title = constructor.getParameters()[0];
        System.out.println("constructor name=" + title.getName()
                + ", present=" + title.isNamePresent());
        System.out.println("owner is constructor="
                + (title.getDeclaringExecutable() == constructor));
    }
}
~~~

Compile **without** `-parameters`:

~~~bash
javac -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Typical output with Java 17/21 `javac` when parameter name attributes are not stored:

~~~text
dispatch parameters=3
0: name=arg0, present=false, type=String, generic=java.lang.String, varargs=false, label=user, typeMark=true
1: name=arg1, present=false, type=int, generic=int, varargs=false, label=-, typeMark=false
2: name=arg2, present=false, type=String[], generic=java.lang.String[], varargs=true, label=-, typeMark=false
generic first=java.util.List<T>
generic second=T
erased second=java.lang.Number
constructor name=arg0, present=false
owner is constructor=true
~~~

Then **recompile the same source** (overwriting the generated class file), but with `-parameters`:

~~~bash
javac -parameters -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

The output becomes:

~~~text
dispatch parameters=3
0: name=recipient, present=true, type=String, generic=java.lang.String, varargs=false, label=user, typeMark=true
1: name=retries, present=true, type=int, generic=int, varargs=false, label=-, typeMark=false
2: name=labels, present=true, type=String[], generic=java.lang.String[], varargs=true, label=-, typeMark=false
generic first=java.util.List<T>
generic second=T
erased second=java.lang.Number
constructor name=title, present=true
owner is constructor=true
~~~

Key takeaways from the example:

- `getParameters()` always sees three `dispatch` parameters in both compilations; **only the name metadata changes**.
- `@Name("user")` on the formal parameter is retrieved via `Parameter.getAnnotation(Name.class)`; it does not depend on having source names.
- `@TypeMark` is an annotation on the **type use**, and must be retrieved via `getAnnotatedType()`; do not confuse it with annotations attached directly to the parameter declaration.
- `String... labels` is `String[]` in bytecode, so `getType().getSimpleName()` displays `String[]`; `Parameter.isVarArgs()` confirms the last parameter of a varargs executable.
- `aggregate(List<T>, T)` returns `List<T>` and `T` in generic metadata; the erasure of `T extends Number` is `Number`. When looking up the method with `getDeclaredMethod`, pass `List.class` and `Number.class`, not `T` or `List<T>`.
- `getDeclaringExecutable()` returns the corresponding constructor; in the example, the reflected constructor object is compared with `==` and evaluates to true for the `Parameter` belonging to that same `Constructor`.

**Reproducibility note:** The two `javac` commands above run sequentially, with the second regenerating the class file with the `MethodParameters` attribute. If using a build tool with incremental compilation, ensure all code needing metadata is actually recompiled with the corresponding option.

## 5. What Does `Parameter` Tell Us Besides Names?

### 5.1. Declared Type, Generic Type, and Type Annotations

These APIs return different information:

- `getType()`: erased `Class<?>`; for example `List<String>` becomes `List.class`, `T extends Number` becomes `Number.class`, `String...` becomes `String[].class`.
- `getParameterizedType()`: `java.lang.reflect.Type` which may contain `ParameterizedType` (e.g., `List<T>`), `TypeVariable` (`T`), `WildcardType`, or `GenericArrayType`. It is not necessarily a `Class<?>`.
- `getAnnotatedType()`: carries `TYPE_USE` annotations in the type declaration, which can combine with specialized annotated types for generic/nested components.

Do not cast directly with `(Class<?>) parameter.getParameterizedType()`; the cast can throw `ClassCastException` if the actual `Type` is a `ParameterizedType` or `TypeVariable`.

### 5.2. Annotations on Parameters and Annotations on Types

The two forms may look similar in source code:

~~~java
// Illustrative annotation declaration snippet, not a standalone class.
void process(@ParamLabel("id") String id) {}
void processType(@TypeConstraint String id) {}
~~~

When an annotation has `@Target(PARAMETER)`, `Parameter.getAnnotation(...)` or `getDeclaredAnnotations()` reads the annotation on the formal parameter declaration. When an annotation has `@Target(TYPE_USE)`, use `Parameter.getAnnotatedType()` and then `getAnnotation(...)` on the `AnnotatedType`. An annotation may be designed for both targets; in that case, you must understand the annotation placement structure and framework semantics. `@Retention(RUNTIME)` is required so Reflection can access the corresponding annotation at runtime.

`getAnnotations()` and `getDeclaredAnnotations()` on `Parameter` return annotation metadata of the parameter itself; `getAnnotationsByType(...)` handles the appropriate repeatable annotation mechanism. Do not confuse these with annotations on the executable (`Method.getAnnotations()`) or on the declaring class.

### 5.3. Modifiers, Implicit/Synthetic, and Varargs

- `Parameter.getModifiers()` and `Modifier.isFinal(...)` report modifiers of the formal parameter **if the relevant metadata is present**; do not assume every compiler stores them identically when `-parameters` is omitted.
- `isImplicit()` describes a parameter **implicitly declared in source** per language rules; `isSynthetic()` is a parameter that neither appears directly nor is implicitly declared in the source model, generated by the compiler. These flags depend on class file information and how the compiler emits bytecode.
- `isVarArgs()` describes a varargs parameter (typically the last parameter of a method/constructor whose `isVarArgs()==true`). It does not merely check whether the type is an array: a method taking a regular `String[]` gives `isVarArgs()==false`.

**Do not infer that `isImplicit()==false` or `isSynthetic()==false` proves a parameter exists verbatim in source.** Some compilers/bytecode transformers do not store full metadata; there are also hidden parameters in constructors of nested classes, enums, and special constructs.

## 6. Constructor Parameters: Not Everything Matches Source

`Constructor<?>` is also an `Executable`, so calling `getParameters()` works the same as on `Method`. However, constructors of certain class forms have implicit/compiler-added parameters:

1. **Non-static inner member class:** the constructor usually takes an extra parameter to carry the enclosing instance. For `Outer.Inner`, the constructor's type list via Reflection may begin with `Outer.class` even though the source does not write such a variable name.
2. **Enum:** the bytecode constructor has extra parameters managed by the runtime/compiler, such as name and ordinal; do not treat it as a user-callable constructor API to instantiate new enums. Reflection forbids using `Constructor.newInstance` to create enum constants.
3. **Record canonical constructor:** the parameter list corresponds to the record components; the compiler/JLS has specific metadata rules for canonical constructors. Do not conflate this case with "whether the compiler always includes source parameter names".
4. **Anonymous/local class:** the bytecode constructor may have parameters for captured variables or the enclosing context. Details depend on the compiler.

Valid source fragment example:

~~~java
class Outer {
    class Inner {
        Inner(int number) {}
    }
}
~~~

With `javac`, looking up the Reflection constructor of the inner class typically requires `getDeclaredConstructor(Outer.class, int.class)`. `getParameterCount()` will include the outer parameter, so the result can differ from the number of formal parameters written in the constructor source. To map parameters to user data, you need a policy to identify and exclude special runtime parameters; **do not hardcode** always skipping index 0 for every constructor.

## 7. Using `Parameter` in Framework Design

Suppose a controller has the method:

~~~java
// Framework API illustration fragment; annotation is assumed to be defined.
void find(@RequestKey("id") String id, int page) {}
~~~

A binder can follow this check order:

1. Read `Method.getParameters()`; each element gives its position and direct type.
2. If the parameter has an annotation specifying the request name explicitly, use the annotation's value because that is the API contract.
3. If there is no annotation, only use `getName()` when `isNamePresent()==true`. If metadata is missing, report a configuration error or require the user to declare the name. Do not treat `arg0` as a public HTTP/JSON name.
4. Determine the type via `getType()` and `getParameterizedType()`; use explicit converters for `String -> int`, `List<T>`, enums, and nullability. `Parameter` **does not** perform conversion itself.
5. Account for `isVarArgs()` when preparing arguments for a varargs method; at the Reflection level, the varargs parameter has an array type (`String[]`), and an appropriate array object must be prepared when calling `Method.invoke`.
6. Assemble the arguments array in parameter order. Catch resolution, type conversion, access, and invocation errors separately.

Do not use parameter names as cache keys independent of class/method: two overloads can share the parameter name `value` while differing in types; source metadata may also change after refactoring. A reliable method key must be based on the executable, declaring class, and parameter types.

### When Is `getParameters()` Not Needed?

If you only need to identify the overload `run(String, int)`, you can usually use `getDeclaredMethod("run", String.class, int.class)` or `getParameterTypes()`. If you only need the count, `getParameterCount()` is clearer. Only allocate/iterate `Parameter[]` when you need **per-parameter** properties (name, annotations, generics, modifiers, varargs).

## 8. Limitations and Common Mistakes

| Misconception | Consequence and Fix |
| --- | --- |
| "Without `-parameters`, `getParameters()` returns `[]`." | False: parameters from the signature are still seen; usually only names become `arg0`… |
| "`getName()` is always the source name." | False: you must check `isNamePresent()`. |
| "`-g:vars` is enough for Core Reflection parameter names." | False: use `-parameters` for `MethodParameters` metadata. |
| "`getType()` preserves `List<String>`." | False: use `getParameterizedType()` for generic metadata. |
| "Parameter annotations and type-use annotations are the same." | False: distinguish `getAnnotation(...)` from `getAnnotatedType()`. |
| "Varargs in Reflection is not an array." | False: `String...` has type `String[]`; check `isVarArgs()` as well. |
| "The parameter count on a constructor always equals what is written in source." | Not true for certain inner/enum/local/anonymous classes. |
| "An overridden method always keeps the parent's parameter names." | False: the subclass declaration can use different names; names do not participate in overriding/signatures. |
| "`Parameter` automatically coerces passed-in data types." | False: `Parameter` only describes metadata; the converter/invoker must handle arguments. |
| "`isSynthetic()==false` proves the programmer wrote the parameter." | False: metadata flags have limitations and depend on the compiler. |

### Meaningful Exception Handling

- `getDeclaredMethod(...)` / `getDeclaredConstructor(...)` can throw `NoSuchMethodException` if the erased parameter types are wrong.
- `getParameters()` can throw `MalformedParametersException` due to malformed parameter name/modifier attributes in the class file.
- When analyzing `getParameterizedType()`, you may encounter `GenericSignatureFormatError`, `TypeNotPresentException`, or `MalformedParameterizedTypeException` on invalid/unresolvable generic signatures.
- When invoking the executable after analyzing metadata, check access, argument count/types, and exceptions thrown by the method/constructor itself; that is a separate layer from reading `Parameter`.

Do not catch everything and treat missing metadata as meaning the constructor/method does not exist. In bytecode analysis tools, report the class source, executable, parameter index, and error type separately for investigation.

## 9. Verification Exercises

1. Compile the demo twice, without and with `-parameters`; verify that only `getName()` and `isNamePresent()` change, while types, generics, and annotations remain intact.
2. Replace `dispatch(String... labels)` with `dispatch(String[] labels)`, adjust the lookup signature accordingly, and observe `isVarArgs()`.
3. Add a `List<? extends Number> amounts` parameter and print `getParameterizedType().getTypeName()`; inspect the difference compared to `getType()`.
4. Create two overloads `load(String id)` and `load(int id)`; demonstrate that the name `id` is not enough to distinguish them.
5. Put a `@Target(PARAMETER)` annotation on a parameter and a `@Target(TYPE_USE)` annotation on the parameter's type; read each via the appropriate API.
6. Create an inner member class `Outer.Inner` with constructor `Inner(int id)`; inspect the runtime parameter type list and count.
7. Write a small binder: prefer an explicit name annotation, fall back to `getName()` only when `isNamePresent()` is true, and report a clear error if the name is missing.
8. Try a generic method with `<T extends Number>`; compare `getType()` and `getParameterizedType()` for `T`.

## 10. References

- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html): `getParameters()`, `getParameterTypes()`, `getGenericParameterTypes()`, and `getParameterAnnotations()`.
- [Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): names, annotations, generic types, implicit/synthetic/varargs, declaring executable.
- [javac Java 17 — Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-parameters` option to record formal parameter names for Reflection access.
- [Java Language Specification 17 — `8.4.1 Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): formal parameters, modifiers, varargs.
- [JVM Specification 17 — MethodParameters Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.24): parameter name/attribute metadata in class files.

**Core principle:** `getParameters()` reveals the **runtime parameters of an executable**, while `Parameter.getName()` is only reliable as a source name when metadata is present and `isNamePresent()` confirms it. Use `getType()` for the erased type, `getParameterizedType()` for generics, `getAnnotatedType()` for type annotations, and `getAnnotation(...)` for parameter annotations.
