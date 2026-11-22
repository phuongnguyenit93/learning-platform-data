# 2.1 Obtaining Class via class literal, getClass, and Class.forName

Java represents each type loaded by the JVM with a `java.lang.Class` object. From that object, Reflection can read the name, superclass, interfaces, methods, fields, constructors, annotations, and more. The three common ways to obtain a `Class` are **class literal (`SomeType.class`)**, **`object.getClass()`**, and **`Class.forName(...)`**. They all provide type metadata, but differ in **when the type is determined**, **whether an existing object is required**, **how the class loader is chosen**, and **the impact on class initialization**.

## 1. Foundation: declared type, actual type, and the Class object

For example, `Number number = Integer.valueOf(42);`: the variable has a **declared type** of `Number`, while the existing instance has a **runtime class** of `Integer`. `Number.class` and `Integer.class` describe two different types respectively. Having `Class<Integer>` does not mean an `Integer` instance has been created via a constructor.

Within a defining class loader, one runtime type corresponds to one `Class` object. Two lookups of the same type in the same context will return the same `Class` object; therefore `a == b` is meaningful for checking **type identity**. Conversely, the same binary name defined by two different *defining class loaders* can be two separate types that cannot be automatically cast to each other.

It is also necessary to separate three related phases: **loading** loads the definition, **linking** verifies/prepares and may resolve references, and **initialization** executes static initialization (`static` field initializers and `static { ... }`). Obtaining a `Class` does not mean the static initializer has run.

## 2. Class literal: SomeType.class

When the type name is already known directly in Java code, use a class literal:

~~~java
Class<String> textType = String.class;
Class<Integer> boxedType = Integer.class;
Class<String[]> arrayType = String[].class;
Class<?> primitiveType = int.class;
Class<?> voidType = void.class;
~~~

This is an expression that can be used with classes, interfaces, enums, annotations, arrays, primitives, and `void`. The compiler checks the type name and compile-time dependencies; **no instance is needed**. For example, when an API requires a type token, `String.class` is clearer and more type-safe than entering the string name `"java.lang.String"`.

A class literal **does not automatically trigger initialization** of the referenced class. The JVM may still need to load or resolve type information; do not equate that with running `static { ... }`.

Notes:

- `int.class` and `Integer.class` are two `Class` objects for the **primitive type** and **wrapper**; `getName()` returns `int` or `java.lang.Integer`.
- `String[].class` describes an array type; `String[].class.getName()` returns `[Ljava.lang.String;`, while `getTypeName()` displays a more readable form.
- Do not write `T.class` if `T` is a generic parameter, or `List<String>.class`: generic types have type erasure. Use `List.class` if you only need the raw runtime class, or `java.lang.reflect.Type`/`ParameterizedType` if you need to store parameterized type structure.
- `SomeType.class` is the natural choice when the type is fixed, for example registering a serializer, mapper, annotation processor, or passing a type to a Reflection API.

Example of a type token with a generic method (the illustrative snippet needs to be placed inside a class to compile):

~~~java
static <T> T checkedCast(Class<T> expected, Object value) {
    return expected.cast(value);
}
// Call: String s = checkedCast(String.class, "Java");
~~~

`Class.cast` performs a runtime check and throws `ClassCastException` if `value` is incompatible, instead of an unchecked cast.

## 3. Object.getClass(): the actual class of an instance

`getClass()` is a `public final` method inherited from `Object`. It does not take a type name, and instead returns the exact **runtime class of the calling object**, even when the reference variable is declared with a superclass or interface:

~~~java
Number n = Integer.valueOf(42);
Class<? extends Number> runtime = n.getClass();

System.out.println(runtime.getName());           // java.lang.Integer
System.out.println(n.getClass() == Number.class); // false
~~~

`n` has static type `Number` but holds an `Integer`, so `getClass()` returns `Integer.class`. With `List<String> list = new ArrayList<>();`, the result is `ArrayList.class`, not `List.class`; the generic argument `String` is also not present in the actual runtime `Class` object.

Important limitations:

1. **There must be a non-`null` instance**. Calling `getClass()` on a `null` reference causes a `NullPointerException`.
2. It only observes the current type; it does not look up a class by string, does not require choosing a class loader, and does not actively initialize another class. When creating an instance with `new`, that class has normally already had to be initialized.
3. `obj.getClass() == Parent.class` requires the class to be **exactly** `Parent`; a subclass instance makes this expression false. If you want to accept subclasses, use `obj instanceof Parent` or `Parent.class.isInstance(obj)`.
4. For an array instance, `new String[0].getClass() == String[].class` is `true`.

## 4. Class.forName: finding a class when only the type name is known at runtime

When the class name comes from a configuration file, plugin data, or metadata external to the source code, use:

~~~java
Class<?> resolved = Class.forName("java.lang.String");
System.out.println(resolved == String.class); // true (same defining loader)
~~~

`Class.forName(String name)` returns `Class<?>` because the compiler cannot infer a specific type from a string. This overload uses the class loader associated with the class **calling `forName`** and requires **initialize = true**. This means if the target class has not been initialized yet, the JVM will run its static initializer. The call can throw `ClassNotFoundException` (a checked exception), and initialization can also fail.

To **choose the class loader** and **defer initialization**, use the three-parameter overload:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.example.Plugin", false, loader);
~~~

- `name` must be the **binary name** of the class to find.
- `initialize = false`: does not actively initialize the class when finding it; `true` requests initialization if needed.
- `loader`: the class loader to load/find the class. `null` requests the bootstrap class loader; it does not mean “automatically pick an appropriate loader”.

**Class loader matters:** the single-parameter overload does not automatically use the **thread context class loader**; in a plugin container, application server, or multi-loader environment, pass the right loader when needed. Two loaders can define the same `com.example.Plugin` as two different classes, even though `getName()` is identical. This difference explains many unexpected `ClassCastException` errors.

**Name syntax:** `java.util.ArrayList` is a valid binary name. Nested classes use `$` such as `com.example.Outer$Inner`, not `Outer.Inner`. For arrays, the name representation uses the form `[Ljava.lang.String;` or `[[I`; `Class.forName("java.lang.String[]")` is not a valid array name. You cannot use `Class.forName("int")` to get a primitive class; use `int.class`.

Java 9+ also has `Class.forName(Module module, String name)`, which differs from the overloads above: it **does not initialize the class**, and can return `null` when the class cannot be found in the module. When using this overload, you must check for `null` before proceeding.

## 5. Runnable example: three ways to obtain Class and initialization order

Create the file **ClassLookupDemo.java** (Java 17+):

~~~java
public class ClassLookupDemo {
    static class LazyType {
        static {
            System.out.println("LazyType <clinit>");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        // Class literal does not run the static initializer of LazyType yet.
        Class<LazyType> literal = LazyType.class;
        System.out.println("literal: " + literal.getName());

        // false: finds the class without initializing the target class yet.
        Class<?> deferred = Class.forName(
                "ClassLookupDemo$LazyType",
                false,
                ClassLookupDemo.class.getClassLoader());
        System.out.println("same object: " + (literal == deferred));

        // getClass returns the runtime class of an existing instance.
        Number number = Integer.valueOf(42);
        Class<? extends Number> runtime = number.getClass();
        System.out.println("runtime: " + runtime.getName());

        // The single-parameter overload requests initialization of LazyType.
        Class<?> initialized = Class.forName("ClassLookupDemo$LazyType");
        System.out.println("init same object: " + (literal == initialized));

        System.out.println("primitive: " + int.class.getName());
        System.out.println("array: " + String[].class.getName());
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac ClassLookupDemo.java
java ClassLookupDemo
~~~

Stdout from a run in a fresh JVM:

~~~text
literal: ClassLookupDemo$LazyType
same object: true
runtime: java.lang.Integer
LazyType <clinit>
init same object: true
primitive: int
array: [Ljava.lang.String;
~~~

Because `LazyType.class` does not initialize the class, the program prints the class name first. `forName(..., false, loader)` returns the exact same `Class` object and still does not print `<clinit>`. `getClass()` gives `Integer` because the concrete object is an `Integer`. Only when reaching `Class.forName("ClassLookupDemo$LazyType")` does the JVM execute the static initializer, printing `LazyType <clinit>` once. Initialization **does not create a second `Class` object**.

If `LazyType` has already been initialized by a previous thread or piece of code, `forName(..., true, ...)` does not re-run the static initializer. You should not rely on a static initializer to perform work intended to run multiple times.

## 6. Quick comparison and decision guide

| Criterion | `MyType.class` | `obj.getClass()` | `Class.forName(...)` |
| --- | --- | --- | --- |
| Input | Type name written in source | Existing instance | Binary name string; loader can be passed |
| When is the type known? | At compile time | At runtime, based on instance | At runtime, based on config/name |
| Instance required? | No | Yes, and non-`null` | No |
| Commonly used result type | `Class<MyType>` | `Class<? extends X>` | `Class<?>` |
| Triggers target class initialization? | No, from the literal alone | No, from calling the method alone | 1-param overload: yes; 3-param: per `initialize` |
| Notable errors | Compile error if type name is wrong | `NullPointerException` | `ClassNotFoundException`, linking/initialization errors |
| Example | API accepting `String.class` | Observing runtime class of a proxy | Plugin implementation class chosen from config |

**Choosing the right tool:** When the type name is already known in source, prefer a class literal so the compiler checks it. When you need to reflect the actual instance, use `getClass()`. When the type is genuinely decided by configuration/runtime, use `forName` and deliberately choose both the loader and initialization timing. Changing `MyType.class` into a fixed string `Class.forName("...")` usually just adds runtime failure paths.

## 7. Real-world scenario: checking a plugin type before creating an instance

Suppose the class name implementing the `Converter` interface is stored in configuration. You need to find the class, verify that it implements the interface, and then create an instance using reflection. Below is a **complete, self-contained runnable program**, requiring no external libraries.

Create the file **ConverterDemo.java**:

~~~java
import java.util.Locale;

public class ConverterDemo {
    public interface Converter {
        String convert(String input);
    }

    public static final class UpperConverter implements Converter {
        public UpperConverter() {
        }

        @Override
        public String convert(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        String nameFromConfig = "ConverterDemo$UpperConverter";

        Class<?> found = Class.forName(
                nameFromConfig, false, ConverterDemo.class.getClassLoader());

        Class<? extends Converter> checked = found.asSubclass(Converter.class);
        Converter converter = checked.getDeclaredConstructor().newInstance();

        System.out.println(converter.convert("java"));
    }
}
~~~

~~~bash
javac ConverterDemo.java
java ConverterDemo
~~~

Stdout:

~~~text
JAVA
~~~

Explanation: `found` is `Class<?>` because a runtime name does not provide a generic type token. `asSubclass(Converter.class)` checks whether the type is assignable to `Converter` and returns `Class<? extends Converter>`; if incompatible, it throws `ClassCastException`. `getDeclaredConstructor().newInstance()` executes the constructor and may trigger class initialization at this point. A no-arg constructor must exist and be accessible; when using JPMS, `exports`, `opens`, and module/package accessibility determine valid reflection operations.

**Security note:** Do not arbitrarily take class names from untrusted input and initialize them: static initializers and constructors can execute code. Restrict accepted implementations, manage class loaders, and choose an appropriate plugin mechanism such as `ServiceLoader` when needed. `asSubclass` helps with type checking; it is **not a security sandbox**.

## 8. Common errors, causes, and fixes

| Error / symptom | Cause | How to handle |
| --- | --- | --- |
| `NullPointerException` at `getClass()` | The object is currently `null` | Check for `null` or use a type token from a trusted source |
| `ClassNotFoundException` | String name not found via the loader used | Check binary name, dependencies, classpath/module path, and loader |
| `Class.forName("int")` does not work | Primitives cannot be looked up by this string name | Use `int.class` |
| `Class.forName("Outer.Inner")` cannot find nested class | Nested class name is not a valid binary name | Use `Outer$Inner` with the appropriate package |
| `NoClassDefFoundError` or `LinkageError` | Missing dependency or linking/version error at runtime | Inspect the *cause*, check dependencies/classpath, not just the name string |
| `ExceptionInInitializerError` | Static initializer encountered an error | Check the logic inside the `static` block and the root cause |
| `ClassCastException` when casting or using `asSubclass` | Incompatible runtime class; sometimes two loaders are involved | Verify interface, subclass, and defining loader |
| `getDeclaredConstructor().newInstance()` fails | Constructor does not exist, is inaccessible, or throws an exception | Provide an appropriate constructor, check access/module permissions and the cause exception |
| `obj.getClass() == Base.class` is `false` while `obj instanceof Base` is `true` | The object actually belongs to a subclass | Choose an **exact class** check or an **inheritance relationship** check according to intent |

`ClassNotFoundException` is a **checked exception** of the string-name overload, forcing a `try/catch` or `throws` declaration. `NoClassDefFoundError`, on the other hand, is an **Error**, usually related to a type that was referenced but could not be defined/linked in the actual context. You should not catch `Throwable` and ignore everything, as that can hide important deployment errors.

Also do not confuse `getName()` with a human-readable name for every kind of type. For example, `String[].class.getName()` returns `[Ljava.lang.String;`. If displaying to learners or users, `getTypeName()` is usually more suitable.

## 9. Self-check questions and answers

1. Given `Object value = "Hello";`, is `value.getClass() == Object.class` true? **False**: the runtime class is `String.class`.
2. Does `Sample.class` automatically run the `static` block of `Sample`? **No**, not just from taking the class literal.
3. `Class.forName("pkg.Plugin", false, loader)` returned a `Class`. Can an instance be created afterward? **Yes**, if a constructor is found and accessible; during instance creation, initialization may occur.
4. Why can you not write `List<String>.class`? Because generic parameters do not create separate runtime classes after **type erasure**; use `List.class` or `Type` metadata when needed.
5. How does `obj.getClass() == Parent.class` differ from `obj instanceof Parent`? The first expression requires **the exact class `Parent`**, while the second accepts objects of subclasses.
6. Are two classes with the same `getName()` guaranteed to be the same type? **Not necessarily**; you must also consider the defining class loader.
7. When a plugin is not in the caller class's loader, which overload should be used? **`Class.forName(name, initialize, explicitLoader)`** with the appropriate class loader.

## 10. Key takeaways

- `T.class` specifies the type in source, is checked by the compiler, and needs no instance.
- `obj.getClass()` returns the runtime class of an existing instance and throws an error if the reference is `null`.
- `Class.forName(name)` looks up by runtime name, uses the caller's loader, and requests initialization.
- `Class.forName(name, false, loader)` allows controlling the loader and deferring initialization to check the type first.
- `Class` is the starting point of Reflection; it **does not imply** an instance has been created, the static initializer has run, or all members are accessible.

The three ways to obtain `Class` correspond to three different questions: **“Which type do I know at coding time?”**, **“Which class is this object actually?”**, and **“Which type does a class name decided at runtime point to?”**. Distinguishing them clearly helps design reflection, dependency injection, serializers, and plugin architectures more accurately.
