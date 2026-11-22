# 7.7 Binding a receiver or reference argument with bindTo

`MethodHandle.bindTo(Object x)` creates a **new method handle** by pre-binding a reference value `x` to the **first parameter** of the current method handle. From the next call onward, the caller no longer has to pass that parameter. This is a technique commonly used to pre-bind a *receiver* for an instance method; it can also be used to bind the first reference argument of a static method or of an already-transformed handle.

What to remember right away: **`bindTo` binds the first parameter that has a reference type**, not a mechanism exclusively for receivers. If the first parameter has a primitive type such as `int`, `bindTo` does not apply directly. If you need to bind an argument at an arbitrary position or bind a primitive, use `MethodHandles.insertArguments`.

This lesson uses Java 17+ and places `bindTo` in the context of `MethodHandle`, `MethodType`, `MethodHandles.Lookup`, `invokeExact`, and handle transformations.

## 1. Visualizing parameter binding

Suppose there is an instance method:

~~~java
class Greeter {
    String greet(String name) {
        return "Hello " + name;
    }
}
~~~

A handle created with `findVirtual` to call `Greeter.greet(String)` will have an equivalent type:

~~~text
Before binding:
  MethodHandle: (Greeter, String) -> String
                 receiver  name

Bind receiver with bindTo(greeter):
  MethodHandle: (String) -> String
                 name

When calling the new handle, the receiver is already held inside the handle.
~~~

The source method only declares one parameter `name`. However, an **unbound handle** for a virtual call requires the receiver as the first parameter; `bindTo(greeter)` removes the receiver parameter from the **invocation signature of the new handle**. This can be viewed as a form of *partial application*: fixing one input, obtaining a remaining function with one fewer argument.

For a static method:

~~~java
static String surround(String prefix, String content) {
    return prefix + content;
}
~~~

The initial handle has type `(String, String)String` and **has no receiver**. `bindTo("prefix: ")` is still valid because the first parameter `prefix` is a `String` reference; the new handle has type `(String)String`. Therefore, the meaning of the bound parameter depends on the **handle signature**, not on the method name.

## 2. Exact contract of MethodHandle.bindTo

Syntax:

~~~java
MethodHandle bound = original.bindTo(value);
~~~

Result and conditions:

1. `original.type()` must have **at least one parameter**. The parameter at position `0` must be a **reference type** such as `String.class`, `Object.class`, or another class/interface, and must not be a primitive.
2. `value` must be convertible to the first parameter's class via a reference type check. If incompatible, `ClassCastException` may be thrown **immediately upon binding**.
3. The returned handle drops **exactly the first parameter** from the parameter list; the return type and the order of the remaining parameters are preserved. For example, from `(Greeter,String,int)String` to `(String,int)String` after binding a `Greeter`.
4. **The original handle is not modified.** `bindTo` returns a different handle. Calls to `original` still must provide all parameters as before.
5. The bound value is stored as a **reference to the object**, which does not mean creating a copy of the object. If the receiver changes state, subsequent calls of the bound handle can see that change.
6. `bindTo` does not invoke the target method immediately. Method execution and exceptions from the method body occur when `invokeExact`, `invoke`, or another handle invocation path is executed.

If a handle has no parameters or its first parameter is a primitive, calling `bindTo` causes `IllegalArgumentException`. An incompatible reference type causes `ClassCastException` when binding. Do not confuse these two error groups with `WrongMethodTypeException`, which appears at **invocation** time when calling a handle with an incorrect call site signature.

For `null`: because `bindTo` works with references, the value `null` can be bound when the first parameter is a reference type. However, if it is the receiver of an instance method that needs to access the object, the actual call typically leads to `NullPointerException`. Nor should `bindTo(null)` be used to represent a valid receiver.

## 3. Obtaining the right MethodHandle with Lookup before binding

`bindTo` is a method of `MethodHandle`, so a valid handle is needed first. For an instance method:

~~~java
class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }
}

// Illustration; place in a method that handles ReflectiveOperationException:
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType declaredType =
        MethodType.methodType(String.class, String.class);
MethodHandle handle =
        lookup.findVirtual(Greeter.class, "greet", declaredType);
~~~

When **finding the method** with `findVirtual`, `declaredType` describes the type of the declared method: `(String)String`. When **receiving the handle**, `handle.type()` is `(Greeter,String)String` because the handle needs the `Greeter` receiver added at the beginning.

Next:

~~~java
Greeter greeter = new Greeter();
MethodHandle bound = handle.bindTo(greeter);

// Before: handle.type() has 2 parameters, consisting of Greeter and String.
// After:  bound.type() has 1 parameter, String.
String result = (String) bound.invokeExact("Ada");
~~~

The line `(String) bound.invokeExact("Ada")` is significant regarding types: `invokeExact` is a *signature-polymorphic* call, so **both the argument types and the result type inferred by the compiler at the call site** must match `bound.type()` exactly. Assigning to an `Object` variable instead of casting `(String)` will request a return type of `Object`; with a handle that actually returns `String`, `invokeExact` will throw `WrongMethodTypeException`.

If type conversions supported by `asType` are acceptable, `invoke` is more flexible than `invokeExact`. But both invoke the handle **after the receiver has been bound**, without needing to pass the receiver again.

### Reading MethodType to self-check

Do not just guess the handle type from the source signature. Check it:

~~~java
System.out.println(handle.type().parameterCount());  // 2
System.out.println(bound.type().parameterCount());   // 1
System.out.println(bound.type().parameterType(0));   // class java.lang.String
System.out.println(bound.type().returnType());       // class java.lang.String
~~~

The four lines above are an **illustrative snippet** requiring the appropriate `handle` and `bound` variables. `parameterCount()`, `parameterType(i)`, and `returnType()` return information from the `MethodType` of the **current handle**. This is a more effective debugging approach than inferring from the original method name when the handle has gone through multiple adapters.

## 4. Full example 1: binding a receiver and a static reference argument

Create file **BindToDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class BindToDemo {
    static class Greeter {
        private final String prefix;

        Greeter(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + " " + name;
        }
    }

    static class LoudGreeter extends Greeter {
        LoudGreeter(String prefix) {
            super(prefix);
        }

        @Override
        public String greet(String name) {
            return super.greet(name).toUpperCase(Locale.ROOT);
        }
    }

    public static String decorate(String prefix, String value) {
        return prefix + "[" + value + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString =
                MethodType.methodType(String.class, String.class);

        MethodHandle unbound = lookup.findVirtual(
                Greeter.class, "greet", oneString);
        Greeter hello = new Greeter("Hello");

        System.out.println("unbound parameters: " +
                unbound.type().parameterCount());
        System.out.println("first parameter: " +
                unbound.type().parameterType(0).getSimpleName());

        String direct = (String) unbound.invokeExact(hello, "An");
        System.out.println("unbound call: " + direct);

        MethodHandle bound = unbound.bindTo(hello);
        System.out.println("bound parameters: " +
                bound.type().parameterCount());

        String greeting = (String) bound.invokeExact("Binh");
        System.out.println("bound call: " + greeting);

        // unbound still has the original type, requiring the receiver to be passed.
        Greeter welcome = new Greeter("Welcome");
        String unchanged =
                (String) unbound.invokeExact(welcome, "Minh");
        System.out.println("original unchanged: " + unchanged);

        // bindTo holds the exact receiver instance, virtual dispatch still works.
        Greeter loud = new LoudGreeter("Hello");
        MethodHandle loudBound = unbound.bindTo(loud);
        String shouted = (String) loudBound.invokeExact("Mai");
        System.out.println("virtual dispatch: " + shouted);

        // static method has no receiver; bindTo binds the first argument.
        MethodHandle decorate = lookup.findStatic(
                BindToDemo.class, "decorate",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodHandle withPrefix = decorate.bindTo("tag");

        System.out.println("static parameters after bind: " +
                withPrefix.type().parameterCount());
        String tagged = (String) withPrefix.invokeExact("OK");
        System.out.println("static bound: " + tagged);
    }
}
~~~

Compile and run:

~~~bash
javac BindToDemo.java
java BindToDemo
~~~

Stdout:

~~~text
unbound parameters: 2
first parameter: Greeter
unbound call: Hello An
bound parameters: 1
bound call: Hello Binh
original unchanged: Welcome Minh
virtual dispatch: HELLO MAI
static parameters after bind: 1
static bound: tag[OK]
~~~

**Why is each result right?**

- `unbound.type()` has two parameters: receiver `Greeter` and name `String`. `getSimpleName()` of the first parameter type is `Greeter`.
- `unbound.invokeExact(hello, "An")` takes the receiver explicitly; `bound.invokeExact("Binh")` only takes the name because `hello` has already been bound.
- `unbound` can still be called with `welcome` after `bound` has been created: `bindTo` does not modify the original handle.
- `LoudGreeter` overrides `greet`. The `findVirtual` handle still invokes according to the virtual dispatch of the actual receiver, even when the receiver has been bound into the handle. Therefore, the result is uppercased.
- `decorate` is a static method with signature `(String,String)String`. `bindTo("tag")` binds the `prefix` parameter, even though this method **has no `this`**; the new handle has exactly one parameter `value`.

This example also clearly distinguishes two things: **binding a receiver** is a very common case, while **binding a leading reference argument** is the general contract of `bindTo`.

## 5. How does bindTo differ from insertArguments?

`MethodHandles.insertArguments(target, pos, values...)` also creates a new handle with pre-bound values, but is more general:

| Criterion | `handle.bindTo(value)` | `MethodHandles.insertArguments(target, pos, values...)` |
| --- | --- | --- |
| Bindable position | Only the first parameter (index 0) | Specified position `pos` |
| Number of values in one call | One value | Can bind multiple consecutive values |
| Bindable value types | Only when the first parameter is a reference type | Can be reference or primitive (via boxing of the varargs API) |
| Result object | New handle | New handle |
| Original handle | Unchanged | Unchanged |
| Typical scenario | Binding a receiver or leading reference argument | Binding middle, trailing, multiple arguments, or primitives |

With a static method:

~~~java
static String surround(String left, String content, String right) {
    return left + content + right;
}
~~~

Its handle has type `(String,String,String)String`. We can fix the right side and then fix the left side:

~~~java
// Assume "surround" is the MethodHandle found by the corresponding findStatic:
MethodHandle withClose =
        MethodHandles.insertArguments(surround, 2, "]");
MethodHandle withBrackets = withClose.bindTo("[");
String result = (String) withBrackets.invokeExact("text"); // [text]
~~~

**How to read positions:** `insertArguments(surround, 2, "]")` binds the **third parameter** of the original handle (index 2), creating a `(String,String)String` handle. Then `bindTo("[")` binds the first parameter `left` of the new handle, creating `(String)String`. Here there is no receiver; the two bound values are used to create a function that only takes the content part.

### Primitives: why is bindTo not enough?

An `(int,int)int` handle cannot call `bindTo(7)` even though Java automatically autoboxes `7` to `Integer` when calling `bindTo(Object)`: **the first parameter of the handle is still primitive `int`**, so `bindTo` throws `IllegalArgumentException`.

Instead:

~~~java
// add has MethodType (int,int)int:
MethodHandle addSeven =
        MethodHandles.insertArguments(add, 0, 7);
int answer = (int) addSeven.invokeExact(5); // 12
~~~

`insertArguments` handles extracting the primitive value from the argument list and checking the type compatibility of each slot. `addSeven.type()` becomes `(int)int`.

To bind multiple arguments, for example `(String,int,String)String`, you can provide multiple consecutive values after `pos`, but remember that subsequent parameters will **change positions** in the transformed handle. When an adapter chain is long, it is usually best to use distinct variable names for each step and check `type()`.

## 6. Full example 2: receiver state, binding position, and primitive errors

Create file **BindingDetailsDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BindingDetailsDemo {
    static class Counter {
        private int calls;

        public String next(String label) {
            calls++;
            return label + ":" + calls;
        }
    }

    public static String surround(
            String left, String content, String right) {
        return left + content + right;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle unboundCounter = lookup.findVirtual(
                Counter.class,
                "next",
                MethodType.methodType(String.class, String.class));

        Counter counter = new Counter();
        MethodHandle count = unboundCounter.bindTo(counter);
        String first = (String) count.invokeExact("run");
        String second = (String) count.invokeExact("run");
        System.out.println("counter first: " + first);
        System.out.println("counter second: " + second);

        MethodHandle surroundHandle = lookup.findStatic(
                BindingDetailsDemo.class, "surround",
                MethodType.methodType(
                        String.class,
                        String.class, String.class, String.class));

        MethodHandle closeFixed =
                MethodHandles.insertArguments(surroundHandle, 2, "]");
        MethodHandle brackets = closeFixed.bindTo("[");
        String wrapped = (String) brackets.invokeExact("value");
        System.out.println("brackets: " + wrapped);

        MethodHandle addHandle = lookup.findStatic(
                BindingDetailsDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));

        try {
            addHandle.bindTo(7);
            System.out.println("unreachable");
        } catch (IllegalArgumentException expected) {
            System.out.println("primitive bindTo: IllegalArgumentException");
        }

        MethodHandle addSeven =
                MethodHandles.insertArguments(addHandle, 0, 7);
        int sum = (int) addSeven.invokeExact(5);
        System.out.println("insertArguments: " + sum);

        try {
            unboundCounter.bindTo("not a Counter");
            System.out.println("unreachable");
        } catch (ClassCastException expected) {
            System.out.println("wrong receiver: ClassCastException");
        }

        System.out.println("original params: " +
                unboundCounter.type().parameterCount());
        System.out.println("bound params: " +
                count.type().parameterCount());
    }
}
~~~

Compile and run:

~~~bash
javac BindingDetailsDemo.java
java BindingDetailsDemo
~~~

Stdout:

~~~text
counter first: run:1
counter second: run:2
brackets: [value]
primitive bindTo: IllegalArgumentException
insertArguments: 12
wrong receiver: ClassCastException
original params: 2
bound params: 1
~~~

Analysis:

1. `count` holds **a reference to the exact `counter` object**. Both calls increment the same `calls` field; `bindTo` does not copy the object and does not turn a stateful method into a pure function.
2. For `surround`, binding `right` with `insertArguments` and then binding `left` with `bindTo` creates a function with one remaining argument `content`.
3. `addHandle` has first parameter `int`. Calling `bindTo(7)` fails right at the handle creation step because `int` is not a reference type; this is `IllegalArgumentException`, not `WrongMethodTypeException`.
4. `insertArguments(addHandle, 0, 7)` can bind a primitive; the new handle takes one `int` and returns `int`.
5. `unboundCounter` requires a receiver of type `Counter`, so attempting to bind a `String` causes `ClassCastException` immediately upon binding.
6. `unboundCounter` still has two parameters after all transformations; `count` only has one parameter left.

If you do not need to deal with stateful objects, you can also bind an immutable reference like `String`. The core point remains that **the first reference value is bound**, not a precomputed call result.

## 7. Relationship between bindTo, invokeExact, invoke, asType, and method references

### bindTo changes the handle type; it does not pre-call the method

Suppose `MethodHandle mh` has type `(Greeter,String)String`, and `Greeter greeter` is a valid receiver:

~~~java
MethodHandle bound = mh.bindTo(greeter);
// bound.type() == (String)String (signature meaning)
String value = (String) bound.invokeExact("Ada");
~~~

`bindTo` **does not precompute** `greet("Ada")`, because at bind time the name `"Ada"` is not yet known. It only fixes the receiver. When calling the new handle, the method body is still executed according to the current state.

### asType adapts the signature, bindTo fixes a value

`bound.asType(MethodType.methodType(Object.class, Object.class))` creates an adapter of type `(Object)Object` so the caller can invoke `invokeExact((Object) "Ada")` and receive `Object`. It does not bind a receiver or argument. Conversely, `bindTo` removes a parameter by embedding a **concrete value** into the handle.

If a first parameter is originally a primitive, an adapter accepting `Integer`/`Object` can be created to serve certain API needs, but that may add boxing/unboxing and runtime checks. When the goal is simply to fix a primitive, `insertArguments` is usually more readable.

### invoke and invokeExact both use the handle type after binding

A common mistaken call is continuing to pass the already-bound receiver:

~~~java
// Error illustration only; bound has type (String)String.
// String wrong = (String) bound.invokeExact(greeter, "Ada");
~~~

This call is incorrect because the handle only has one parameter left. You must call `bound.invokeExact("Ada")` with the appropriate return type. If using `invoke`, the JVM may try to adapt the **types** of the remaining parameters, but **does not automatically restore** the removed receiver parameter.

### Close to method references, but not identical

Conceptually, `greeter::greet` is a receiver-bound method reference to be converted into a compatible functional interface, whereas unbound `Greeter::greet` may need the receiver as the first parameter of the functional interface. `bindTo` expresses a similar "bind receiver" idea but operates at the `java.lang.invoke` layer, where signatures are described by `MethodType` and calls use `MethodHandle`. Do not substitute these APIs indiscriminately: lambda/method reference syntax gives the compiler direct functional type checking; handles are appropriate when the call target is chosen or transformed at runtime.

## 8. Does bindTo affect access permissions and virtual dispatch?

**Lookup and access permissions:** `MethodHandles.Lookup` verifies permissions when creating the initial handle. `bindTo` does not grant additional access to private methods or encapsulated module classes. It only binds a parameter of an existing handle. If you need to look up a valid private method, resolve the lookup context and Java module system rules before binding.

**Virtual dispatch:** `findVirtual` creates a handle for the instance method dispatch mechanism. When `bindTo` holds a receiver whose runtime class is a subclass, the overriding method can still be selected according to the runtime receiver's dispatch. The `LoudGreeter` example in the program above demonstrates this. Binding does not force the method to become a fixed copy of the `Greeter.greet` body.

**Does not change receiver identity:** `bound` holds the same receiver object (which may be passed to multiple places), so modifying the object's state elsewhere still affects calls through the handle. `bindTo` does not guarantee thread safety, does not prevent concurrent modification, and does not automatically synchronize. If the receiver is a mutable object accessed by multiple threads, you must protect its state according to the object's contract and cannot rely on binding.

**Lifecycle:** The handle holds a reference to the bound object as long as the handle and structures holding it remain alive. Caching a receiver-bound handle in a long-lived scope can accidentally keep the receiver and objects referenced by the receiver alive. For short-lived objects, consider caching the **unbound handle** and passing the receiver at call time instead of keeping each receiver in a global cache.

## 9. Using bindTo in a real processing flow

For example, an application has multiple `Formatter`s. When initializing the processing pipeline, the application selects a receiver based on configuration and then calls it repeatedly:

~~~java
interface Formatter {
    String format(String input);
}

class UpperFormatter implements Formatter {
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

You can look up the `Formatter.format(String)` handle once, then `bindTo(selectedFormatter)` to create a callback of type `(String)String`. Selecting the object only happens when configuration changes; the processing loop only passes the data string. However, when configuration needs to re-select the receiver, you must create a **new handle** or keep the unbound handle to switch receivers, because the bound handle continues to call the old receiver.

Design assessment:

- **When appropriate:** the caller already has a fixed receiver and repeatedly invokes the same operation, builds dynamic pipelines, or combines handles with `filterArguments`, `filterReturnValue`, and other adapters.
- **When unnecessary:** application code knows the exact type and method at compile time; calling `formatter.format(text)` or `formatter::format` is usually simpler.
- **When the receiver changes per request:** keep the unbound handle or create an appropriate handle for each receiver with a clear lifecycle; avoid binding and placing into a singleton cache without lifecycle management.
- **When optimization is needed:** measure with JIT warmup and actual call flows. One cannot conclude that `bindTo` is always faster than normal calls or `Method.invoke` for every JVM and case.

## 10. Common errors and how to fix them

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `IllegalArgumentException` right at `bindTo` | Handle has no parameters or first parameter is primitive | Check `type().parameterCount()` and `parameterType(0)`; use `insertArguments` for primitives |
| `ClassCastException` at bind time | Bound value does not match reference type at index 0 | Check the object's class against the handle's first parameter |
| `WrongMethodTypeException` at `invokeExact` | Still passing receiver after bind, wrong argument type, or **wrong return type** | Print `bound.type()`; provide exact remaining parameters and appropriate cast/assignment for return type |
| `NullPointerException` when calling receiver-bound handle | Receiver is `null` or logic inside method dereferences a null value | Check receiver before binding and null contract of the method |
| No result seen when binding | `bindTo` only creates a new handle; method not yet called | Call `invokeExact`/`invoke` on the new handle |
| After binding, cannot call old handle like new handle | `bindTo` does not modify the original handle | Use a separate `bound` variable and provide the right signature for each handle |
| Bound wrong argument of static method | `bindTo` always fixes argument index 0 | Check parameter order; use `insertArguments` with the required `pos` |
| Want to bind second parameter or `int` | `bindTo` does not support arbitrary positions/primitives | Use `MethodHandles.insertArguments` |
| Changed receiver but handle still calls old object | Bound handle already holds the receiver at creation time | Create a new bound handle or use the unbound handle |
| Data appears "frozen" | Misunderstanding binding as precomputing the result | Remember that binding holds a **reference**, method runs on each invocation |
| Mutable receiver has race across multiple threads | `bindTo` does not provide synchronization | Design thread safety protection for the receiver |
| Cache causes objects to be held long-term | Bound handle holds a reference to the receiver | Manage cache/lifetime, use unbound handle when appropriate |

**Note on target exceptions:** If the method called through the handle throws `IOException`, `IllegalStateException`, or another exception, that exception is forwarded directly according to the `MethodHandle.invokeExact`/`invoke` contract. `bindTo` does not wrap this mechanism in `InvocationTargetException` like `java.lang.reflect.Method.invoke`. Because `invokeExact` and `invoke` declare `throws Throwable`, standalone examples use `main(...) throws Throwable` to express the full contract; real-world applications should handle exceptions according to context.

## 11. Self-check with answers

**Question 1.** An unbound handle has `type() == (Greeter,String)String`. After `bindTo(greeter)`, what is the remaining signature?  
**Answer:** `(String)String`. The receiver has been fixed, so it no longer appears in the call parameters.

**Question 2.** Can `bindTo` be used with a static method handle?  
**Answer:** Yes, if the handle's first parameter has a reference type. In that case it binds the first argument of the static method; static methods have no receiver.

**Question 3.** For handle `(int,int)int`, is `bindTo(5)` valid?  
**Answer:** No. The first parameter is primitive `int`, so `bindTo` causes `IllegalArgumentException`. Use `MethodHandles.insertArguments(handle, 0, 5)`.

**Question 4.** After creating `bound = unbound.bindTo(greeter)`, can `unbound.invokeExact(greeter, "A")` still be called?  
**Answer:** Yes. `unbound` retains its original signature and behavior.

**Question 5.** Does `bindTo(greeter)` cause `greeter.greet(...)` to run ahead of time?  
**Answer:** No. The body executes when the new handle is invoked, so the result still depends on unbound parameters and the receiver's state at call time.

**Question 6.** A handle has `type() == (String)String`. Why can `Object out = bound.invokeExact("x")` cause an error?  
**Answer:** The call site return type is `Object`, which does not match the handle's `String`; `invokeExact` requires an exact match for the return type as well.

**Question 7.** If you want to bind the third argument of `(String,int,String)String`, what do you use?  
**Answer:** `MethodHandles.insertArguments(handle, 2, "suffix")` because `bindTo` only binds the first parameter.

**Question 8.** Does a bound handle with `LoudGreeter` attached, but looked up via `findVirtual(Greeter.class, ...)`, invoke the override?  
**Answer:** Yes, when the method is virtual and the actual receiver has a matching override; `bindTo` does not disable the virtual dispatch mechanism.

**Question 9.** What consequence can long-term caching of a `bound` handle have?  
**Answer:** The receiver is kept referenced for the lifetime of the handle/cache. You need to manage the lifetime or cache the unbound handle if the receiver changes continuously.

## 12. Key takeaways

- `bindTo(Object)` **fixes the first reference-typed parameter** of a `MethodHandle` and returns a **new handle** with one fewer parameter.
- For an unbound `findVirtual` instance handle, the first parameter is usually the **receiver**; after binding, the call only needs the remaining arguments.
- For a static handle, the first parameter is a business argument, which can still be bound as normal.
- `bindTo` does not support handles starting with a primitive and cannot choose an arbitrary position; use `MethodHandles.insertArguments` for those situations.
- `bindTo` holds a reference, **does not create a copy of the receiver**, does not pre-run the method, does not modify the original handle, and does not automatically provide thread safety.
- `invokeExact` must match the **new** `MethodType` of the bound handle, including the return type; `invoke` allows some type conversions but does not automatically restore the bound parameter.
- You should inspect `handle.type()` before and after transformation; this is the most important tool for understanding signature mismatches when combining handles.

With `bindTo`, we transition from an invocation capability "needing a receiver or input reference value" to an invocation capability already configured with that value. When used properly, this approach helps clearly express dynamic calls with a fixed context while retaining control over types, execution timing, and receiver lifecycle.
