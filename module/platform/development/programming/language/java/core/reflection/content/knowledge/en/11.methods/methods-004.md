# Overloads and signatures required to look up methods with Java Reflection

## 1. Problem: one name can refer to multiple methods

In Java, **method overloading** allows multiple methods with the same name in a class if **their parameter type lists differ**. Differences can be in the number, types, or order of parameters.

```java
class Example {
    void send(String text) { }
    void send(int number) { }
    void send(String text, int times) { }
    void send(int times, String text) { }
}
```

These are four different methods. All four share the name `send` but have parameter type lists respectively:

- `(String)`
- `(int)`
- `(String, int)`
- `(int, String)`

With Reflection, **knowing only the name `send` is not enough** to identify an overload. You need the exact method name and **a `Class<?>[]` list describing the declared parameter types, in exact order**.

The **method signature** concept in the Java Language Specification (§8.4.2) mainly comprises the method name and parameter types per language rules; **the return type is not used for overloading**. When referring to the *lookup key* of `Class.getMethod`/`getDeclaredMethod`, what must be passed directly is the **name** and **`Class<?>...` of the parameters after erasure**.

## 2. Which API is used to look up methods?

Two common calls:

```java
Class<?> type = Example.class;

// Find a public method, including inherited public methods.
java.lang.reflect.Method method1 =
        type.getMethod("send", String.class, int.class);

// Find a method declared directly in Example, regardless of modifiers.
java.lang.reflect.Method method2 =
        type.getDeclaredMethod("send", String.class, int.class);
```

| API | Scope | Arguments required | If not found |
| --- | --- | --- | --- |
| `getMethod(String name, Class<?>... parameterTypes)` | `public` methods on the class, related interfaces, and inherited `public` methods per API rules | Exact name and parameter type list | `NoSuchMethodException` |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | Methods declared directly in the inspected class/interface, including `private`, `protected`, package-private, and `public` | Exact name and parameter type list | `NoSuchMethodException` |
| `getMethods()` | Array of `public` `Method`s within the API's search scope | Takes no name/signature | Array may be empty |
| `getDeclaredMethods()` | Array of directly declared methods, unfiltered by modifier | Takes no name/signature | Array may be empty |

**Example:** For `void send(String, int)`, looking up `getDeclaredMethod("send", String.class, int.class)` will match; reversing the order to `(int.class, String.class)` is a different overload. Java **does not look for the "closest matching" method** if the `Class` list does not match.

A method with **no parameters** is looked up via `getMethod("ping")` or `getMethod("ping", new Class<?>[0])`. Do not add `Object.class` to substitute for an empty list.

### `getMethod` also differs from `getDeclaredMethod` in inheritance scope

If `Child extends Parent` and only `Parent` declares `public void action(Number value)`:

- `Child.class.getMethod("action", Number.class)` finds the inherited `public` method.
- `Child.class.getDeclaredMethod("action", Number.class)` throws `NoSuchMethodException` if `Child` does not declare or override that method itself.
- If an overload is `private`, `getMethod` will not find that overload, even with the right name/parameters. `getDeclaredMethod` on the **declaring class** can find its metadata.

## 3. Lookup uses exact declared types: no automatic type conversion

Suppose a class has:

```java
void calculate(int value) { }
void calculate(Integer value) { }
void calculate(Number value) { }
void calculate(Object value) { }
```

Parameters `int`, `Integer`, `Number`, and `Object` form four distinct signatures.

| Lookup | Matches corresponding overload? | Reason |
| --- | --- | --- |
| `getDeclaredMethod("calculate", int.class)` | Yes | Declared type `int` |
| `getDeclaredMethod("calculate", Integer.class)` | Yes | Declared type `Integer` |
| `getDeclaredMethod("calculate", Number.class)` | Yes | Declared type `Number` |
| `getDeclaredMethod("calculate", Object.class)` | Yes | Declared type `Object` |
| `getDeclaredMethod("calculate", short.class)` | No | No `short` overload; does not widen to `int` |
| `getDeclaredMethod("calculate", Long.class)` | No | No `Long` overload; does not automatically select `Number` |
| `getDeclaredMethod("calculate", String.class)` | No | No `String` overload; does not automatically select `Object` |

At the **Method lookup step**, Reflection does not apply boxing/unboxing, primitive widening, selecting an assignable superclass/interface, or the Java compiler's overload resolution algorithm. In other words, `int.class != Integer.class`, and `String.class != Object.class`.

At the **step of invoking the found Method** via `Method.invoke`, the argument checking/conversion mechanism differs. For example, a `Method` object representing the `calculate(int)` overload can accept `Integer.valueOf(5)` and unbox it when invoked. However, it **still invokes the `(int)` overload**, without switching to `(Integer)`.

## 4. Complete Java 17+ example: overloads, inheritance, varargs, and generics

Save the entire program as `MethodOverloadLookupDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class MethodOverloadLookupDemo {
    static class Base {
        public String inherited(Number number) {
            return "Base:" + number;
        }
    }

    static class Handler extends Base {
        public String choose(Object value) {
            return "Object";
        }

        public String choose(String value) {
            return "String";
        }

        public String choose(int value) {
            return "int";
        }

        public String choose(Integer value) {
            return "Integer";
        }

        public String combine(String text, int count) {
            return text.repeat(count);
        }

        public String pack(String... values) {
            return "pack:" + Arrays.toString(values);
        }

        public <T extends Number> String accept(T number) {
            return "accept:" + number;
        }

        private String hidden(double value) {
            return "hidden:" + value;
        }
    }

    public static void main(String[] args) throws Exception {
        Handler handler = new Handler();

        Method objectVersion =
                Handler.class.getMethod("choose", Object.class);
        Method stringVersion =
                Handler.class.getMethod("choose", String.class);
        Method intVersion =
                Handler.class.getMethod("choose", int.class);
        Method integerVersion =
                Handler.class.getMethod("choose", Integer.class);

        System.out.println("choose(Object) with String: "
                + objectVersion.invoke(handler, "abc"));
        System.out.println("choose(String): "
                + stringVersion.invoke(handler, "abc"));
        System.out.println("choose(int): "
                + intVersion.invoke(handler, Integer.valueOf(5)));
        System.out.println("choose(Integer): "
                + integerVersion.invoke(handler, Integer.valueOf(5)));

        Method inherited =
                Handler.class.getMethod("inherited", Number.class);
        System.out.println("inherited owner: "
                + inherited.getDeclaringClass().getSimpleName());

        Method combine =
                Handler.class.getMethod("combine", String.class, int.class);
        System.out.println("combine: " + combine.invoke(handler, "Hi", 2));

        try {
            Handler.class.getMethod("combine", int.class, String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Wrong order: NoSuchMethodException");
        }

        try {
            Handler.class.getMethod("choose", StringBuilder.class);
        } catch (NoSuchMethodException e) {
            System.out.println("choose(StringBuilder): NoSuchMethodException");
        }

        try {
            Handler.class.getMethod("choose", short.class);
        } catch (NoSuchMethodException e) {
            System.out.println("choose(short): NoSuchMethodException");
        }

        Method varargs = Handler.class.getMethod("pack", String[].class);
        System.out.println("pack parameter: "
                + varargs.getParameterTypes()[0].getTypeName());
        System.out.println("pack varargs: " + varargs.isVarArgs());
        System.out.println("pack invoke: "
                + varargs.invoke(handler, (Object) new String[] {"a", "b"}));

        Method generic =
                Handler.class.getMethod("accept", Number.class);
        System.out.println("generic erased type: "
                + generic.getParameterTypes()[0].getTypeName());
        System.out.println("generic metadata: "
                + generic.getGenericParameterTypes()[0].getTypeName());

        try {
            Handler.class.getMethod("accept", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("accept(Integer): NoSuchMethodException");
        }

        Method hidden =
                Handler.class.getDeclaredMethod("hidden", double.class);
        System.out.println("hidden private: "
                + Modifier.isPrivate(hidden.getModifiers()));
    }
}
```

Compile/run from the file's directory with JDK 17 or later:

```bash
javac MethodOverloadLookupDemo.java
java MethodOverloadLookupDemo
```

Stdout:

```text
choose(Object) with String: Object
choose(String): String
choose(int): int
choose(Integer): Integer
inherited owner: Base
combine: HiHi
Wrong order: NoSuchMethodException
choose(StringBuilder): NoSuchMethodException
choose(short): NoSuchMethodException
pack parameter: java.lang.String[]
pack varargs: true
pack invoke: pack:[a, b]
generic erased type: java.lang.Number
generic metadata: T
accept(Integer): NoSuchMethodException
hidden private: true
```

Meaning of each part:

1. `getMethod("choose", Object.class)` and `getMethod("choose", String.class)` retrieve **two Method objects for two different overloads**. Passing the same string `"abc"` at `invoke` still produces `Object` and `String` respectively. **There is no re-selection of overloads based on the runtime type of the argument**.
2. `int.class` and `Integer.class` create two independent signatures. `Integer.valueOf(5)` can be unboxed when invoking the `(int)` overload, but does not merge the two signatures during lookup.
3. `getMethod("inherited", Number.class)` finds the public method of `Base`; `getDeclaringClass()` identifies the **declaring** class.
4. Reversing `(String.class, int.class)` to `(int.class, String.class)` causes `NoSuchMethodException` because parameter order is part of the lookup key.
5. `StringBuilder.class` is not automatically converted up to `Object.class`; `short.class` is likewise not automatically converted to `int.class`.
6. Varargs `String...` is stored as a `String[]` array parameter, so look it up with `String[].class`.
7. Generic `<T extends Number>` undergoes **type erasure** to `Number` in the runtime parameter type. `getGenericParameterTypes()` can still provide information on type variable `T`.
8. `getDeclaredMethod` allows finding metadata of `private hidden(double)` directly, which does not mean every caller is automatically allowed to invoke a `private` method.

## 5. Varargs: represented in signature as an array type

The method:

```java
public void log(String... messages) { }
```

in terms of the parameter type list on `Method` is equivalent to declaring `log(String[] messages)`. Both declarations cannot be used as two separate overloads in one class.

```java
// In the context of a class with method public void log(String... messages).
Method logMethod = Example.class.getMethod("log", String[].class);
boolean isVarargs = logMethod.isVarArgs(); // true
```

Do not look it up using `getMethod("log", String.class)` just because the Java call `log("a")` is valid. Likewise, do not look it up using `getMethod("log", String.class, String.class)` just because `log("a", "b")` can be called. At the Reflection lookup step, the parameter count of this varargs method is still **one**.

When using `Method.invoke(Object receiver, Object... args)` in Java, the last parameter is varargs **of the `invoke` API itself**. To pass a `String[]` array as **one argument** of the target method, use:

```java
logMethod.invoke(instance, (Object) new String[] {"a", "b"});
```

The snippet above is illustrative code in a context where `logMethod` and `instance` already exist. Casting `(Object)` prevents Java from spreading the array as the argument list of `Method.invoke`. `Method.invoke` itself does not automatically pack loose strings into an array for a varargs target method.

## 6. Generics: lookup is based on types **after erasure**

Example:

```java
public <T extends Number> void process(T value) { }
```

For Reflection:

```java
// Example within scope of a class having the process method above.
Method method = Example.class.getMethod("process", Number.class);
System.out.println(method.getParameterTypes()[0]); // class java.lang.Number
```

`T` has bound `Number`, so the parameter type after erasure is `Number`. If `T` has no bound, erasure is usually `Object` (with specific rules when there are multiple bounds). Passing `Integer.class` **does not** substitute for `Number.class` to look up that generic method.

Similarly, `List<String>` and `List<Integer>` parameters both have the runtime raw type `java.util.List`. When looking up:

```java
// Example within scope of a class having the method:
// public void consume(java.util.List<String> values) { ... }
Method method = Example.class.getMethod("consume", java.util.List.class);
```

Within the same class, **you cannot overload** based solely on `List<String>` vs. `List<Integer>`, because both declarations clash due to having the same erasure. `getGenericParameterTypes()` and `getTypeParameters()` can help explore generic metadata after finding the `Method`, but the arguments passed to `getMethod` are still `Class<?>...`, not `ParameterizedType`.

## 7. Does return type help select an overload?

No. Two declarations in **the same Java class** like the following are invalid:

```java
// ILLUSTRATION OF NON-COMPILABLE CODE: differing only in return type.
int parse(String source) { return 1; }
long parse(String source) { return 2L; }
```

Each method above shares the same name and the same `(String)` parameter; return type `int` or `long` does not create a valid overload. Therefore, there is no `getMethod(name, returnType, parameterTypes)` API.

This must be distinguished from synthetic methods, bridge methods, and covariant return rules: the compiler/JVM may store multiple methods with the **same name and same parameter types** but **different return types** in bytecode. In that case, `Class.getMethod`/`getDeclaredMethod` applies the API's selection rule (preferring a more specific return type when types are comparable; some cases also depend on API rules), rather than accepting a return type from the caller. If inspecting auto-generated bytecode, you can iterate over `getDeclaredMethods()`, then check `isBridge()`, `isSynthetic()`, `getReturnType()`, and `getDeclaringClass()` to distinguish the `Method` objects.

In normal application programming, identify the **name + parameter type list** first; only inspect the return type and metadata after obtaining the `Method` object.

## 8. Dynamic overload lookup: why can't you just use `arg.getClass()`?

A common mistake:

```java
// Intentionally illustrative code: not a general overload resolver.
Object arg = Integer.valueOf(7);
Method selected = Handler.class.getMethod("choose", arg.getClass());
```

The statement above selects `choose(Integer)` if present. However, if the API needs to call `choose(int)`, `arg.getClass()` returns `Integer.class` and therefore **fails to find the right signature**. When `arg == null`, `arg.getClass()` also causes `NullPointerException`. If the class only has `choose(Number)`, `getMethod("choose", Integer.class)` still fails even though an `Integer` is assignable to a `Number` parameter when invoked.

When you need to invoke a method whose signature is already designed, the right and simplest way is to get the signature information from the **API contract**:

```java
// Short example; Handler and instance appear in the full program above.
Method method = Handler.class.getMethod("choose", int.class);
Object result = method.invoke(instance, Integer.valueOf(7));
```

This snippet is not standalone; `instance` is an already-created `Handler` object and the caller needs to handle checked exceptions. `invoke` runs the `(int)` overload; the `Integer` argument can be unboxed at the invocation step.

If you truly need **overload selection from runtime data with unknown signatures beforehand**, you must define a dedicated strategy: collect candidates by name/parameter count; evaluate assignability, boxing/unboxing, primitive widening, null, varargs, and specificity; and detect ambiguous cases. That is a **separate resolution problem**, not a feature of `getMethod`. Prefer avoiding reimplementing `javac` overload resolution if signatures can be determined upfront from an interface or convention.

## 9. Safe Method query workflow in projects

1. **Determine the name and declared type list** from interfaces, documentation, annotations, schemas, or contracts; do not guess from a set of runtime arguments.
2. **Choose the search scope:** `getMethod` for `public` including inherited; `getDeclaredMethod` for directly declared members, including non-public ones.
3. **Pass each `Class` accurately in order:** primitives use `int.class`, wrappers use `Integer.class`, arrays use `String[].class`, generics use erased types like `List.class`.
4. **Verify received metadata** using `getParameterTypes()`, `getDeclaringClass()`, `getReturnType()`, `isVarArgs()`, `isBridge()` when needed.
5. **Separate the execution phase:** `Method.invoke` also checks receiver/arguments/access rights; checked exceptions or target-cause wrapper exceptions occur at this step.

Example logic to match a signature after listing:

```java
// Illustrative code in a method importing java.lang.reflect.Method and java.util.Arrays.
Class<?>[] expected = {String.class, int.class};
for (Method method : Handler.class.getDeclaredMethods()) {
    if (method.getName().equals("combine")
            && java.util.Arrays.equals(method.getParameterTypes(), expected)) {
        System.out.println(method.getName()); // combine
    }
}
```

Note: `getDeclaredMethods()` **does not guarantee order**, and the array may contain bridge/synthetic methods. Do not pick `methods[0]` assuming the first overload is the one needed.

## 10. Common errors

| Symptom | Main cause | How to fix |
| --- | --- | --- |
| `NoSuchMethodException: choose(java.lang.Integer)` even though `choose(int)` exists | Lookup used wrapper instead of primitive | Use `int.class` |
| `choose(Object)` exists but looking up `choose(StringBuilder)` fails | Lookup requires exact declared type | Use `Object.class` if that is the contract signature |
| `combine(String,int)` exists but cannot be found | `Class` order reversed | Keep exact `String.class, int.class` |
| `log(String...)` exists but looked up with `String.class` | Varargs is declared as `String[]` | Use `String[].class` |
| `accept(T extends Number)` exists but looked up with `Integer.class` | After erasure, `T` is `Number` | Use `Number.class` |
| `getDeclaredMethod` does not see parent's `public` method | Method is not declared directly on subclass | Use `getMethod` or switch to the declaring class |
| `getMethod` does not see `private` method | API only searches `public` | Use `getDeclaredMethod` on the right class, then check access |
| `Method.invoke` fails with `IllegalArgumentException` | Wrong receiver, argument count, or argument type during call | Check `getParameterTypes()` and how varargs are passed |
| `Method.invoke` throws `InvocationTargetException` | Target method itself threw an exception while running | Inspect `getCause()` for the error from the target method |
| Overload result differs from normal Java call | `invoke` uses the already-selected Method, does not re-select by runtime argument | Pick the right signature before invoking |

## 11. Self-check

**Question 1:** A class declares `void send(int count)` and `void send(Integer count)`. Do the two calls `getDeclaredMethod("send", int.class)` and `getDeclaredMethod("send", Integer.class)` return the same overload?

**Answer:** No. These are two `Method` objects for two declarations with different parameter signatures.

**Question 2:** A class has `void send(String[] values)`. Can you look it up using `getMethod("send", String.class, String.class)` to invoke with two strings?

**Answer:** No. The declared parameter type is `String[]`, so `String[].class` must be used. `send(String[])` can correspond to Java `String...` syntax if declared as varargs.

**Question 3:** A class has `void test(Number value)`. Will `getMethod("test", Integer.class)` find it just because `Integer extends Number`?

**Answer:** No. You must pass `Number.class` for an exact lookup.

**Question 4:** Can a `public` method declared in a superclass be found via `Child.class.getMethod(...)`?

**Answer:** Yes, when that method belongs to the public members inherited/searched under `getMethod` rules. `getDeclaredMethod` on the child only sees methods directly declared by the child.

**Takeaway:** When using Reflection to look up overloads, pass the **exact name + exact count, order, and `Class` types of the declared parameters**. Return type is not used to select overloads, Java conversions do not happen during lookup, and `Method.invoke` simply executes the already-selected method.

References: [Java SE 17 `Class.getMethod` / `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Java SE 17 `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [JLS §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).