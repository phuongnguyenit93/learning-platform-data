# 6.1 MethodHandle Is a Typed Executable Reference; Distinguishing It from Method

In Java, `java.lang.invoke.MethodHandle` represents **an invocation capability already linked to a specific operation**, with **a full type signature at runtime**. We can hold it in a variable, pass it as a value, invoke it multiple times, pre-bind a receiver object (*receiver*), or create a new handle with a signature adapted to the context. The `java.lang.reflect.Method` object in Reflection also describes a method and can invoke it, but it is a **metadata object about a method declaration**, with a completely different invocation mechanism and type contract.

This lesson focuses on the nature of `MethodHandle`, the direct roles of `MethodType` and `MethodHandles.Lookup`, the `invokeExact`/`invoke` invocation syntax, how it compares with `Method.invoke`, and common pitfalls. All runnable examples use **Java 17+**.

## 1. MethodHandle Points to an Invocable Operation

Let's start with the idea:

~~~java
// Conceptual illustration, not a complete program yet:
MethodHandle handle = /* a valid handle found */;
String result = (String) handle.invokeExact(/* arguments of exact types */);
~~~

`MethodHandle` does not simply store "method name + parameter list"; it is bound to **an executable behavior** that has been identified, such as:

- Calling a `static` method.
- Calling an instance method via virtual dispatch.
- Calling a constructor to create an instance.
- Reading or writing a field.
- Calling another handle with pre-bound, swapped, filtered, or type-converted arguments.

A method handle is usually obtained through `MethodHandles.Lookup`. When the lookup succeeds, the result has a fixed **`MethodType`** describing both the parameter types and the return type. The word "typed" here means **the JVM signature is described and checked at the call site**. It does not mean a Java variable is declared as `MethodHandle<String, Integer>`; `MethodHandle` is not a generic class.

A handle can reference a method declared with generics, but `MethodType` uses **runtime classes after erasure** (`Class<?>`), not storing `List<String>` or `<T>` directly. When full generic metadata of the declaration is needed, `Method` and the `getGeneric...()` APIs serve that purpose.

## 2. Three Components: Lookup → MethodHandle → MethodType

Typical flow:

~~~text
Class + operation name + MethodType
              │
              ▼
       MethodHandles.Lookup
              │ findStatic / findVirtual / findConstructor ...
              ▼
       Linked MethodHandle
              │
              ├── type() → MethodType of the handle
              ├── invokeExact(...) → invoke with an exact matching signature
              ├── invoke(...)      → allows supported type conversions
              └── asType/bindTo/... → create a new adapted handle
~~~

**`MethodHandles.Lookup`** is an object with permission to find and create handles according to an access context. `MethodHandles.lookup()` creates a lookup representing the calling class; access permissions cannot be arbitrarily elevated. `MethodHandles.publicLookup()` is only used for public members accessible in that lookup context. For private members of another class, whether `privateLookupIn` can be used depends on access permissions and module boundaries (especially `opens`/`exports` rules).

**`MethodType`** describes the exact **return type** and **parameter types** of an invocation. For example:

~~~java
MethodType oneString = MethodType.methodType(String.class, String.class);
MethodType addInts   = MethodType.methodType(int.class, int.class, int.class);
MethodType noResult  = MethodType.methodType(void.class, String.class);
~~~

In order, they describe `(String)String`, `(int,int)int`, and `(String)void`. A `MethodType` is only a signature description; **it does not find or invoke a method by itself**. `methodType(...)` accepts `Class<?>` objects; primitive types such as `int.class` and `void.class` are completely valid.

**`MethodHandle`** is the object that holds the operation and the signature. `handle.type()` retrieves the `MethodType` of the handle after lookup or transformation. A handle of type `(String)String` can be invoked via `invokeExact` if the arguments and return type at the call site match this type exactly.

## 3. Lookup Signature Differs from the Instance Handle Signature

Suppose:

~~~java
class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }

    public static String upper(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Finding a static method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType signature = MethodType.methodType(String.class, String.class);

MethodHandle staticHandle =
        lookup.findStatic(Greeter.class, "upper", signature);
// staticHandle.type(): (String)String
~~~

Finding an instance method:

~~~java
MethodHandle virtualHandle =
        lookup.findVirtual(Greeter.class, "greet", signature);
// virtualHandle.type(): (Greeter,String)String
~~~

This is where beginners often get confused:

- When calling `findVirtual(Greeter.class, "greet", signature)`, `signature` contains **the declared parameters of the method**, not yet including `this`. The method `greet(String)` declares one `String` parameter.
- The returned handle requires the **receiver** as the first parameter: `(Greeter,String)String`. Therefore, the call site must pass `Greeter` first, and then `String`.
- For a static method without a receiver, the handle remains `(String)String`.
- `findVirtual` performs **virtual dispatch** according to the runtime type of the receiver, so if a subclass overrides the method, the invocation behavior still follows the appropriate JVM dispatch rules.

This difference also appears in constructors and fields:

| Lookup API | Type used during lookup | `handle.type()` after lookup |
| --- | --- | --- |
| `findStatic(C, "f", methodType(R.class, P.class))` | Notation `(P)R` | `(P)R` |
| `findVirtual(C, "f", methodType(R.class, P.class))` | Notation `(P)R` | `(C,P)R`, with receiver |
| `findConstructor(C, methodType(void.class, P.class))` | Constructor notation `(P)void` | `(P)C`, returns instance |
| `findGetter(C, "field", F.class)` | Field name + field type | `(C)F` |
| `findStaticGetter(C, "field", F.class)` | Static field name + field type | `()F` |

In the table, `C`, `P`, `R`, `F` are notations for **the corresponding classes/types**, not complete Java code to copy. For a constructor, lookup uses `void.class` because a constructor has no return type in its declared signature; the resulting handle, however, returns an instance of `C`.

## 4. invokeExact: Exact Matching of Parameters and Return Type

`invokeExact` is a **signature-polymorphic** method. The parameter types and return type of the call are determined from the call expression itself in bytecode, and must then match `handle.type()` **in full** at runtime.

Suppose a handle has type `(String)String`:

~~~java
String text = (String) handle.invokeExact("Java");
~~~

This is a `(String)String` call site. If changed to:

~~~java
Object value = handle.invokeExact("Java");
~~~

the call site is now `(String)Object` because the expected return type is `Object`. Even though `String` is a subtype of `Object`, **`invokeExact` does not automatically convert the return type**, so it will throw `WrongMethodTypeException` when the actual handle is still `(String)String`.

Important rules:

1. Both **argument types** and **result type** must be exact. Casting at the call site, for example `(String) handle.invokeExact(...)`, is meaningful for determining the call site's return type.
2. For a handle taking `int`, an `Integer` or `long` argument does not automatically substitute for `int` in `invokeExact`.
3. A call can **compile successfully** even if the signature does not match the handle currently held in the variable, because the compiler does not know `handle.type()` through a general `MethodHandle` variable. Mismatches are detected at runtime.
4. `invokeExact` does not use the `Object...` form of `Method.invoke`; the arguments in the call are the actual arguments of the method type, supported by the JVM's signature-polymorphic call site.

If a handle has return type `void`, it must be invoked in a way matching a `void` return signature (a statement without assigning the result). Do not try to force every call into receiving `Object`.

## 5. invoke: Supported Type Conversions

`invoke` is also a signature-polymorphic method, but it **allows adapting** the call site to `handle.type()` through conversions supported by `asType`. For example, from a `(String)String` handle:

~~~java
Object input = "Java";
Object output = handle.invoke(input); // call site: (Object)Object
~~~

At runtime, the adapter converts the input `Object` to `String` via a check/cast and returns `String` as `Object`. If `input` is an `Integer`, a `ClassCastException` may occur. For primitives, the adapter can also perform appropriate boxing/unboxing and widening, but `invoke` **does not arbitrarily convert the string "42" into the number 42**.

You can adapt **explicitly** once via:

~~~java
MethodType generic = MethodType.methodType(Object.class, Object.class);
MethodHandle adapted = handle.asType(generic);
Object result = adapted.invokeExact((Object) "Java");
~~~

`adapted.type()` is `(Object)Object` and `invokeExact` now matches the signature of **the new handle**. `asType` does not replace the logic of the original method: it creates a handle that performs input/output conversions around the original operation; if the types cannot be adapted, creating or invoking the adapter may fail.

**Boundary:** `invoke` is usually suitable when type flexibility is needed, whereas `invokeExact` is clearer when the exact signature is already known and implicit conversions should be avoided. Do not infer that one method is "always faster" merely from their names; performance also depends on the JIT, invocation pattern, and how the application caches handles.

## 6. Complete Example: Finding, Invoking, Binding Receiver, and Comparing with Method

Create file **HandleVsMethodDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Method;
import java.util.Locale;

public class HandleVsMethodDemo {
    static class Greeter {
        private final String prefix;

        Greeter(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + " " + name;
        }

        public static String upper(String text) {
            return text.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString =
                MethodType.methodType(String.class, String.class);

        MethodHandle virtual =
                lookup.findVirtual(Greeter.class, "greet", oneString);

        Greeter greeter = new Greeter("Hello");
        System.out.println("handle params: " +
                virtual.type().parameterCount());
        System.out.println("handle return: " +
                virtual.type().returnType().getSimpleName());

        String exact = (String) virtual.invokeExact(greeter, "Ada");
        System.out.println("exact: " + exact);

        // bindTo binds the receiver, creating a (String)String handle.
        MethodHandle bound = virtual.bindTo(greeter);
        System.out.println("bound params: " +
                bound.type().parameterCount());

        String boundResult = (String) bound.invokeExact("Minh");
        System.out.println("bound: " + boundResult);

        // invoke can convert Object -> String at runtime.
        Object input = "Linh";
        Object flexible = bound.invoke(input);
        System.out.println("invoke: " + flexible);

        MethodHandle adapted = bound.asType(
                MethodType.methodType(Object.class, Object.class));
        Object adaptedResult = adapted.invokeExact((Object) "Nhi");
        System.out.println("asType: " + adaptedResult);

        MethodHandle upper =
                lookup.findStatic(Greeter.class, "upper", oneString);
        String upperResult = (String) upper.invokeExact("java");
        System.out.println("static: " + upperResult);

        try {
            // Return type Object != String: invokeExact does not adapt.
            Object incompatible = bound.invokeExact("Bao");
            System.out.println(incompatible);
        } catch (WrongMethodTypeException expected) {
            System.out.println("invokeExact: WrongMethodTypeException");
        }

        // Reflection Method describes the declaration and returns Object on invoke.
        Method reflected = Greeter.class.getDeclaredMethod(
                "greet", String.class);
        Object reflectedResult = reflected.invoke(greeter, "Mai");
        System.out.println("Method.invoke: " + reflectedResult);

        // Convert Method to MethodHandle (still requires access permissions).
        MethodHandle fromReflection = lookup.unreflect(reflected);
        String converted = (String) fromReflection.invokeExact(
                greeter, "Thu");
        System.out.println("unreflect: " + converted);
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac HandleVsMethodDemo.java
java HandleVsMethodDemo
~~~

Expected stdout:

~~~text
handle params: 2
handle return: String
exact: Hello Ada
bound params: 1
bound: Hello Minh
invoke: Hello Linh
asType: Hello Nhi
static: JAVA
invokeExact: WrongMethodTypeException
Method.invoke: Hello Mai
unreflect: Hello Thu
~~~

**Step-by-step explanation:**

- `findVirtual` receives the method signature `(String)String` but creates a handle with **two parameters**: the receiver `Greeter` and `String`. The return type is `String.class`.
- `invokeExact(greeter, "Ada")` has call site type `(Greeter,String)String`. Casting `(String)` on the result keeps the return type exact.
- `bindTo(greeter)` creates a new handle that holds the receiver, changing the signature to `(String)String`; the original handle is unchanged.
- `bound.invoke(input)` accepts a variable with static type `Object`, converts it to `String` at runtime, and returns the result as `Object`.
- `asType` changes the signature seen from the call site to `(Object)Object`; as a result, `adapted.invokeExact((Object) "Nhi")` is an *exact* call for the adapted handle.
- `findStatic` has no receiver; calling it directly with `"java"` yields `"JAVA"`.
- In the error branch, Java determines the return type to be `Object` because of the receiving variable `Object incompatible`. The handle needs to return `String`, so `invokeExact` throws `WrongMethodTypeException` before executing the target method.
- `Method.invoke` goes through the Reflection API and returns `Object`; `lookup.unreflect(reflected)` creates a handle corresponding to the existing method so that the MethodHandle invocation mechanism can be used.

Remember that **`bindTo` only binds a reference parameter at the first position of the handle**. In cases where you need to bind a parameter at another position or of a primitive type, the corresponding tool is `MethodHandles.insertArguments`. An adapter does not have to modify the original method.

## 7. Where Are Method and MethodHandle Similar, and Where Do They Differ?

`Method` is `java.lang.reflect.Method`. When invoking:

~~~java
Method method = Greeter.class.getDeclaredMethod("greet", String.class);
Object result = method.invoke(greeter, "Lan");
~~~

`Method` has metadata APIs: `getName()`, `getDeclaringClass()`, `getModifiers()`, `getParameterTypes()`, `getGenericParameterTypes()`, `getReturnType()`, `getGenericReturnType()`, `getAnnotations()`... It is suitable when an application needs to **inspect a declaration** or a framework needs to read annotations, generic signatures, and access rules. `Method.invoke` takes a receiver (or `null` for a static method) along with `Object... args`, performs the necessary checks/boxing-unboxing, and returns `Object` (or `null` if the method returns `void`).

`MethodHandle` focuses on **how execution happens**. It has `type()` and a set of combinators/adapters such as `asType`, `bindTo`, `filterArguments`, `filterReturnValue`, `guardWithTest`...; but it does not directly provide the full `getAnnotations()` API or generic declaration metadata like `Method`. A handle can be created by combinators and no longer correspond to **a single declared method**.

| Criterion | `java.lang.reflect.Method` | `java.lang.invoke.MethodHandle` |
| --- | --- | --- |
| Nature | Metadata of a declared method | Reference to an invocable behavior (composable/transformable) |
| Signature in object | Name, declaring class, parameter/return types, modifiers, generic metadata | `MethodType`: runtime return and parameter types |
| Primary invocation | `method.invoke(receiver, Object... args)` | `handle.invokeExact(args...)` or `handle.invoke(args...)` |
| Argument types at call site | Packed in `Object...` | Reflects call-site signature, checked/adapted by JVM |
| Invocation result | `Object` (boxes primitives; `null` for void) | Follows call-site return type; can be primitive or void |
| Instance receiver | Receiver is a separate argument to `Method.invoke` | Receiver is typically the first parameter of an unbound instance handle |
| Exceptions thrown by target method | Wrapped in `InvocationTargetException` | Propagates `Throwable` directly from target |
| Access control | Reflection access checks on invocation and accessibility configuration | Lookup checks permissions when creating handle; can grant invocation capability via created handle |
| Generic/annotation metadata | Has `getGeneric...`, `getAnnotations` APIs | Does not provide full declaration metadata |
| Transforming/chaining calls | No dedicated combinator suite | `bindTo`, `asType`, `filterArguments`, `guardWithTest`... |
| Performance | Depends on implementation, frequency, JIT | Can be optimized very well by JIT when handle is stable; benchmark needed |
| Common scenarios | API discovery, annotations, framework metadata | Dynamic dispatch, adapters, language runtimes, linkage/call sites |

**Not a one-to-one mapping:** `MethodHandle` also represents constructors, field accesses, and many composed processing chains; `Method` is only metadata for a method. If a `Method` object is needed from a handle, `MethodHandles.reflectAs(...)` can support some **direct method handles** when appropriate permissions are present, but it cannot by default turn every composed handle into an equivalent `Method`.

## 8. Different Exceptions: Target Exception vs. Wrapper

A very practical difference is how exceptions from the target method appear:

- `Method.invoke(...)` wraps errors thrown by code inside the target method in `java.lang.reflect.InvocationTargetException`. To find the root cause, use `getCause()` or `getTargetException()`.
- `MethodHandle.invokeExact(...)` and `invoke(...)` let the target's exception **pass directly** to the caller, without wrapping it in `InvocationTargetException` solely because of the invocation mechanism.
- Errors **before calling the target** can be `WrongMethodTypeException` (signature mismatch / cannot be adapted) or `ClassCastException` when an adapter needs to cast an incompatible value.
- `Lookup.findVirtual/findStatic` can throw `NoSuchMethodException` or `IllegalAccessException` when the name/signature does not exist or permissions are lacking; this differs from target exceptions at execution time.

Second standalone example, file **HandleExceptionDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class HandleExceptionDemo {
    public static class Calculator {
        public int base = 10;

        public Calculator() {
        }

        public int divide(int numerator, int denominator) {
            return numerator / denominator;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle constructor = lookup.findConstructor(
                Calculator.class, MethodType.methodType(void.class));
        Calculator calculator = (Calculator) constructor.invokeExact();

        MethodHandle getter =
                lookup.findGetter(Calculator.class, "base", int.class);
        int base = (int) getter.invokeExact(calculator);
        System.out.println("getter: " + base);

        MethodHandle divide = lookup.findVirtual(
                Calculator.class,
                "divide",
                MethodType.methodType(int.class, int.class, int.class));

        try {
            int ignored = (int) divide.invokeExact(calculator, 8, 0);
            System.out.println(ignored);
        } catch (ArithmeticException ex) {
            System.out.println("handle: ArithmeticException");
        }

        Method method = Calculator.class.getMethod(
                "divide", int.class, int.class);

        try {
            method.invoke(calculator, 8, 0);
        } catch (InvocationTargetException ex) {
            System.out.println("method wrapper: " +
                    ex.getClass().getSimpleName());
            System.out.println("target: " +
                    ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac HandleExceptionDemo.java
java HandleExceptionDemo
~~~

Expected stdout:

~~~text
getter: 10
handle: ArithmeticException
method wrapper: InvocationTargetException
target: ArithmeticException
~~~

Here `findConstructor` takes a constructor signature with no parameters and **return type `void.class` during lookup**, but the resulting handle has type `()Calculator`. `findGetter` creates a handle of type `(Calculator)int`. `findVirtual` on the `divide(int,int)` method creates a `(Calculator,int,int)int` handle. When the denominator is 0, integer division throws `ArithmeticException`: the handle call receives this exception directly; `Method.invoke` wraps the original exception in `InvocationTargetException`.

Both programs use `main(String[] args) throws Throwable` because the invocation methods on `MethodHandle` have a `throws Throwable` contract, which is broader than `throws Exception`. When building real applications, handle the necessary exception types according to context, rather than catching `Throwable` and ignoring all JVM errors.

## 9. How Lookup Grants Access and Why It Differs from setAccessible

`MethodHandles.Lookup` represents **the caller's access context**. Commands such as `findStatic`, `findVirtual`, `findConstructor`, and `findGetter` perform the lookup and check the corresponding permissions. If the member does not exist with that exact name/signature, `NoSuchMethodException` may occur; if permissions are insufficient or it is inaccessible due to modules, `IllegalAccessException` may occur.

Do not confuse `lookup()` with JVM-wide privileges: a regular class's lookup does not automatically have permission to call private members of any arbitrary class. `privateLookupIn(Target.class, lookup)` allows requesting a lookup with private access to the target class **when the context and modules permit**; it does not break module boundaries arbitrarily. `publicLookup()` is useful when only working with accessible public APIs.

With Reflection, `Method#setAccessible(true)` or `trySetAccessible()` can adjust access checks within valid bounds, while still remaining subject to the rules of the Java Platform Module System. `Lookup` controls the **handle creation** process; once created successfully, the handle can be passed around as an already-linked invocation capability, and the recipient can invoke it without repeating the entire lookup operation. Therefore, **do not distribute handles that already hold sensitive permissions to untrusted code**.

If converting from `Method` to `MethodHandle` using `lookup.unreflect(method)`, access permissions still matter; merely having a `Method` object does not automatically grant permission to create a handle to every private method.

## 10. handle.type(), Generics, and Casting: Three Conceptual Layers to Keep Separate

**Layer 1 — Java signature in source:** `String greet(String who)` is a declaration. If there is `<T> T transform(T input)`, this is a generic method; the type variable `T` is meaningful to the compiler and metadata.

**Layer 2 — JVM `MethodType`:** After erasure, `<T> T transform(T input)` (unbounded) has an execution type close to `(Object)Object`. `MethodType` holds `Class<?>`/primitive return and parameter types; it does not keep `T` in `MethodHandle.type()`. With `T extends Number`, the erasure of `T` is typically `Number`, so the corresponding JVM type is based on `Number`.

**Layer 3 — Call-site signature:** `invokeExact` interprets the argument and result types of the current call expression. It must match **the handle type**, not relying on `Method`'s own generic type inference. `invoke` can adapt according to `asType` rules; the adapter is not a full generic inference mechanism.

For example, `Method` can report `List<String>` in `getGenericReturnType()`, whereas a handle invoking that method can only record the return type as `List.class` or an equivalent runtime type according to the erased signature. Do not use `handle.type().toString()` to infer erased generic arguments.

## 11. Storing Handles, Binding Receivers, and Sharing Adapters Properly

`MethodHandle` is an object that can be stored in a field and reused many times. A handle's `type()` signature is stable; transformations such as `asType` or `bindTo` **return a new handle**, without modifying the signature of the original handle.

Example operations on an instance handle `(Greeter,String)String`:

~~~java
// Assume virtual and greeter have already been created as in the program above.
MethodHandle bound = virtual.bindTo(greeter);
// bound.type(): (String)String

MethodHandle generic = bound.asType(
        MethodType.methodType(Object.class, Object.class));
// generic.type(): (Object)Object
~~~

**A pre-bound receiver** does not mean an immutable object: if `greeter` has mutable state, subsequent calls will still see its current state. "An immutable handle" only refers to the handle's operation/signature binding, not a guarantee that the result is always the same.

For an application that repeatedly performs a dynamic invocation, it is usually sensible to **cache the appropriate handle** rather than looking it up with `Lookup` on every pass. Even so, do not automatically assume `MethodHandle` is always faster than Reflection: performance characteristics can vary with call-site stability, adapter types, usage of `invokeWithArguments`, JIT warmup, and JVM version. Benchmark the actual business flow when optimizing.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `WrongMethodTypeException` when calling `invokeExact` | Parameter types **or result type** at the call site do not match `type()` | Check the entire `handle.type()`, cast the return type explicitly, or use `invoke`/`asType` if adaptation is desired |
| `ClassCastException` when using `invoke` | Adapter must cast a value from `Object` to the target reference type, but the value is incompatible | Validate the actual input before invoking |
| `NoSuchMethodException` on `findVirtual` | Wrong name, parameters, or return type in `MethodType` | Match the declared signature after erasure exactly |
| `IllegalAccessException` from `Lookup` | Lookup lacks permission for the member or module boundary | Choose the right caller/module lookup, expose the API, or design appropriate access permissions |
| Calling an instance handle with missing arguments | Forgot the receiver at the first position | Check `handle.type().parameterCount()`; pass the receiver or use `bindTo` |
| Constructor handle uses `methodType(C.class,...)` for lookup | Constructor lookup requires `void.class` | Use `methodType(void.class, ...)` in `findConstructor` |
| Method throws an error without `InvocationTargetException` | MethodHandle forwards the original exception | Catch the exception type actually thrown by the target |
| `Method.invoke` produces `InvocationTargetException` | Reflection wraps the target's exception | Use `getCause()` or `getTargetException()` |
| Simply casting Reflection's `Object` to a primitive | `Method.invoke` boxes primitive results | Cast/unbox the appropriate wrapper or invoke a handle with a primitive return type |
| `handle.type()` has no generic arguments | `MethodType` uses runtime classes/primitives after erasure | Read generic metadata from `Method`/`Type` if needed |
| Unexpected benchmark results | JIT not warmed up, handle changing frequently, redundant adapters | Benchmark realistically, cache stable handles, measure lookup cost as well |

### When to Use Which API?

- Use `Method` when the focus is **inspecting declarations**, listing methods, reading annotations/generic signatures, finding names/modifiers, or traditional Reflection applications.
- Use `MethodHandle` when the focus is **dynamic invocation with a clearly described type signature**, wanting to retain/configure invocation capabilities, using receiver binding, adapters/combinators, and potentially optimizing frequent call paths.
- You can **combine** them: find `Method` to read metadata, then use `Lookup.unreflect(method)` to convert to a handle when access permissions allow.
- Use normal direct invocation syntax when types and call flows are already fixed in source code, as there is no need to add a dynamic invocation mechanism.

## 13. Self-Check Questions

1. **What is the core difference in meaning between a Handle and a Method?**  
   `Method` describes a declared method; `MethodHandle` is the capability to **execute** an operation with a `MethodType`, possibly through adapters/combinators.

2. **Why does `lookup.findVirtual(Greeter.class, "greet", methodType(String.class, String.class))` have `parameterCount() == 2`?**  
   The method declares one `String`, while an unbound instance handle needs the `Greeter` receiver added at the beginning.

3. **Given a `(String)String` handle, is calling `Object v = handle.invokeExact("x")` valid at runtime?**  
   No. The call-site return type is `Object`, which does not match `String`; `WrongMethodTypeException` will be thrown.

4. **When does `invoke` work while `invokeExact` fails?**  
   When the call site differs from the handle type but can be converted according to `asType`, such as `(Object)Object` to a `(String)String` handle with an actual argument of `String`.

5. **Does `bindTo` mutate the old handle?**  
   No. It returns a new handle with the first reference parameter bound; the old handle and old type remain intact.

6. **How do `Method.invoke` and `MethodHandle.invokeExact` handle target errors?**  
   Reflection wraps target errors in `InvocationTargetException`; a handle propagates the target exception directly.

7. **Can `MethodHandle.type()` be used to read `List<String>` in detail?**  
   No. `MethodType` describes JVM types after erasure and does not retain that generic signature; Reflection's `Method.getGenericReturnType()` is needed when appropriate.

8. **Can `MethodHandles.publicLookup()` access a private method?**  
   No. Lookup permissions depend on the caller and access/module rules; a private lookup must satisfy access requirements.

9. **Is using MethodHandle guaranteed to be faster than Method.invoke?**  
   There is no universal guarantee. You must consider the call site, adapters, caching level, JIT, and measure in context.

## 14. Key Takeaways

- `MethodHandle` represents **an executable operation** with a `MethodType` signature, rather than merely a method metadata object.
- `MethodHandles.Lookup` selects and checks permissions when creating handles; `findVirtual` creates a handle with **receiver** as the first parameter, whereas `findStatic` does not.
- `invokeExact` requires **exact matching of both parameters and result** with `handle.type()`. `invoke` supports certain adaptations via `asType`.
- `bindTo`/`asType` return new handles; they do not modify the old handle.
- `Method.invoke` takes `Object...` and wraps exceptions thrown by the target; `MethodHandle` uses a typed call site and propagates target exceptions directly.
- `Method` has annotation/generic declaration metadata; `MethodHandle` serves dynamic invocation, described using runtime classes/primitives after erasure.
- Do not assume performance, access permissions, or type conversions are identical: check `type()`, choose the right lookup, and test in the target environment.

Understanding this distinction helps read `java.lang.invoke` APIs accurately, avoid runtime signature mismatches, and know when to use Reflection metadata versus a linked invocation capability.