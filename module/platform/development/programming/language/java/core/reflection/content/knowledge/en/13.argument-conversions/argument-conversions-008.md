# The Reflection API's Object... Varargs and How to Pass an Array as One Argument

## 1. The problem: passing String[] to Method.invoke yet Java interprets it as multiple arguments

Java Reflection provides `java.lang.reflect.Method.invoke` to call a method resolved at runtime:

~~~java
Object invoke(Object receiver, Object... args)
        throws IllegalAccessException, IllegalArgumentException,
               java.lang.reflect.InvocationTargetException;
~~~

The `receiver` parameter is the object receiving the call (or `null` for a static method). The `Object... args` part is **the list of arguments that the target method receives**, not a single argument named `args`. In bytecode, the second parameter of `invoke` is actually `Object[]`. The ellipsis `...` enables **the compiler at the call site** to automatically create an `Object[]` array containing each argument.

This easily creates a trap when the target method itself requires an argument that is **an array**:

~~~java
public void printAll(String[] items) { /* ... */ }
~~~

If called as:

~~~java
String[] items = {"red", "blue"};
Method method = Printer.class.getMethod("printAll", String[].class);
method.invoke(printer, items); // ERROR-PRONE: items can be used as the Object[] arguments array
~~~

Because `String[]` is a subtype of `Object[]`, the compiler can use **`items` itself as the array holding `invoke`'s arguments**. Reflection then sees two arguments `"red"` and `"blue"`, whereas `printAll` declares only **one parameter of type `String[]`**. The result is `IllegalArgumentException` due to an argument count mismatch.

**The guaranteed way to pass an array as a single argument:**

~~~java
method.invoke(printer, (Object) items);
method.invoke(printer, new Object[] { items });
~~~

In the case above, both forms make `Method.invoke`'s `args` have **one element**, and that element is the `String[]` array object to pass to `printAll`.

This lesson distinguishes the two varargs layers, explains the `String[]` and `int[]` cases, handles `null`, shows the difference between a target method taking a regular array vs. declaring `String...`, and practices the errors reported by Reflection.

## 2. Two argument layers: outer Object[] and inner data array

Consider the API:

~~~java
Method method = Printer.class.getMethod("printAll", String[].class);
String[] items = {"red", "blue"};
Object result = method.invoke(printer, new Object[] { items });
~~~

We have **two arrays at two levels**:

~~~text
Method.invoke(printer, new Object[] { items })
                      |
                      +-- Object[] args of Method.invoke itself
                          length = 1
                          args[0] --------------+
                                                 |
                                                 v
                                 String[] items = ["red", "blue"]
                                 (one argument of printAll)
~~~

- **The outer array** has type `Object[]`, representing *the number and order of parameters* to pass to the target method.
- **The inner array** has type `String[]`, representing *the value of the single parameter* that `printAll(String[])` expects.
- `args.length == 1` does not mean `items.length == 1`. `items` still contains two strings, or could contain thousands of elements.
- The target method receives exactly one `String[]` parameter. Reflection does not iterate `items` and treat each element as a parameter of `printAll` once it is wrapped properly.

Contrast the two expressions:

~~~java
method.invoke(printer, items);
method.invoke(printer, new Object[] { items });
~~~

They are **not equivalent** if `items` has type `String[]` or another reference array type convertible to `Object[]`. The first expression may send `items` directly as the `args` array of the `invoke` API; the second expression creates an `Object[]` containing a single element, `items`.

A quick self-check before running: if the target method declares `printAll(String[])`, the question to ask is **how many elements will `Method.invoke` see in `Object[] args`?** The answer must be one, and that element must be compatible with `String[]`.

## 3. How does varargs in Java work at the call site?

The `Object... args` notation is syntax for a variable-arity parameter. From the JVM signature perspective, it is an `Object[]` array parameter. Java allows two common ways of calling it:

~~~java
method.invoke(receiver, value1, value2); // variable arity form
method.invoke(receiver, new Object[] { value1, value2 }); // explicit args array
~~~

In the first form, the compiler typically generates `new Object[] { value1, value2 }` to pass to the `invoke` method. The second form supplies the `Object[]` array directly, so the compiler does not need to create another array.

### Why does String[] cause a trap?

~~~java
String[] words = {"a", "b"};
method.invoke(receiver, words);
~~~

`String[]` is a **reference array** and has a subtype relationship with `Object[]`. Thus, at the last argument position of `invoke(Object, Object...)`, the compiler can choose the fixed-arity call with an already-existing `Object[]` array parameter. It does not necessarily wrap `words` inside a new `Object[]`.

Read in terms of the equivalent at the Reflection argument layer:

~~~text
method.invoke(receiver, words)
    -> args of Method.invoke is words
    -> args.length = words.length
    -> each String element is treated as an argument of the target method
~~~

When compiling with `javac`, this style of call often emits the warning *non-varargs call for last parameter; cast to Object for a varargs call or to Object[] for a non-varargs call*. This warning refers to **how the `Method.invoke` call is compiled**, not a claim about whether the target method has varargs or not.

### Why does casting to (Object) fix it?

~~~java
method.invoke(receiver, (Object) words);
~~~

The cast makes the **static type** of the last argument expression become `Object`, no longer `Object[]`. The compiler must use the variable-arity form and wrap this value into an `Object[]` containing **one element**.

Notably, the cast `(Object) words` **does not change the runtime nature of the `words` array**. The element inside is still `String[]` and can still be passed to `String[]` at the target method. The cast only affects how the compiler packs parameters for the `invoke` call.

### Why does casting to (Object[]) NOT fix it?

~~~java
method.invoke(receiver, (Object[]) words);
~~~

For `String[]`, this cast is valid, yet it still causes the call to take **an `Object[]` as the container of the argument list**, so it spreads the strings into multiple parameters of the target method. It chooses *the outer array type*, the opposite of the goal of passing the data array itself as one argument.

Therefore, when you want to pass **one data array** to the target method, prefer `(Object) array` or `new Object[]{array}`. Do not casually switch to `(Object[]) array`.

## 4. Table of scenarios to distinguish

Suppose the target method is `void accept(String[] values)`, variable `String[] values = {"red", "blue"};`, and `m` is the `Method` describing that method:

| Call | Arguments the target method receives | Result |
| --- | --- | --- |
| `m.invoke(target, (Object) values)` | 1: the `String[]` array itself | ✅ Correct |
| `m.invoke(target, new Object[] { values })` | 1: the `String[]` array itself | ✅ Correct |
| `Object[] args = { values }; m.invoke(target, args)` | 1: the `String[]` array itself | ✅ Correct |
| `m.invoke(target, values)` | 2: `"red"` and `"blue"` | ❌ Wrong parameter count |
| `m.invoke(target, (Object[]) values)` | 2: `"red"` and `"blue"` | ❌ Wrong parameter count |
| `m.invoke(target, "red", "blue")` | 2 String arguments | ❌ Wrong parameter count |
| `m.invoke(target, (Object) null)` | 1 `null` argument | ✅ Correct if the target method allows a `null` array |
| `m.invoke(target, new Object[] { null })` | 1 `null` argument | ✅ Correct |
| `m.invoke(target, (Object[]) null)` | Argument list in `invoke` API is `null`, usable for a method with **no** parameters | ❌ Incompatible with a method requiring one parameter |

To call a method taking **two individual `String`s**, for example `void pair(String left, String right)`, `m.invoke(target, new Object[]{"red", "blue"})` is actually **correct** because two elements are two parameters. How many elements the outer `Object[]` array contains must match **the actual parameter count of the target method**, rather than the element count of an inner data array.

Note on `null`: `(Object) null` guarantees **one argument with value null**; `(Object[]) null` is **a null argument-array variable** passed to `Method.invoke`, not a null element. If the target has no parameters, Java allows `args` to be `null` or a 0-length array; if the target requires one parameter, use the form containing one element.

## 5. Complete Java 17+ example: String[], primitive int[], varargs, and null

Create the file **`ReflectionVarargsDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectionVarargsDemo {
    public static class Receiver {
        public String accept(String[] values) {
            return values == null
                    ? "array=null"
                    : "array=" + Arrays.toString(values);
        }

        public String collect(String... values) {
            return "varargs=" + Arrays.toString(values);
        }

        public String pair(String first, String second) {
            return "pair=" + first + "+" + second;
        }

        public String numbers(int[] values) {
            return "numbers=" + Arrays.toString(values);
        }

        public String noArguments() {
            return "no-arguments";
        }
    }

    @FunctionalInterface
    interface ReflectCall {
        Object execute() throws Exception;
    }

    private static void attempt(String label, ReflectCall call) {
        try {
            System.out.println(label + ": " + call.execute());
        } catch (Exception error) {
            System.out.println(label + ": "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Receiver receiver = new Receiver();
        String[] words = {"red", "blue"};

        Method accept = Receiver.class.getMethod(
                "accept", String[].class);
        Method collect = Receiver.class.getMethod(
                "collect", String[].class);
        Method pair = Receiver.class.getMethod(
                "pair", String.class, String.class);
        Method numbers = Receiver.class.getMethod(
                "numbers", int[].class);
        Method none = Receiver.class.getMethod("noArguments");

        System.out.println("accept parameters="
                + accept.getParameterCount());
        System.out.println("collect isVarArgs="
                + collect.isVarArgs());

        attempt("(Object) String[]",
                () -> accept.invoke(receiver, (Object) words));
        attempt("Object[]{String[]}",
                () -> accept.invoke(receiver, new Object[] { words }));
        attempt("(Object[]) String[]",
                () -> accept.invoke(receiver, (Object[]) words));

        attempt("target String...",
                () -> collect.invoke(receiver, (Object) words));
        attempt("target String... separately",
                () -> collect.invoke(receiver, "red", "blue"));

        attempt("two String parameters",
                () -> pair.invoke(receiver, (Object[]) words));

        attempt("primitive int[]",
                () -> numbers.invoke(receiver, (Object) new int[] {1, 2}));

        attempt("(Object) null",
                () -> accept.invoke(receiver, (Object) null));
        attempt("(Object[]) null for one parameter",
                () -> accept.invoke(receiver, (Object[]) null));
        attempt("no-arg method",
                () -> none.invoke(receiver));
    }
}
~~~

Compile and run from the directory containing the file, with JDK 17 or later:

~~~bash
javac --release 17 ReflectionVarargsDemo.java
java ReflectionVarargsDemo
~~~

**Stdout derived per the Java SE 17 contract, reproducible with the code above:**

~~~text
accept parameters=1
collect isVarArgs=true
(Object) String[]: array=[red, blue]
Object[]{String[]}: array=[red, blue]
(Object[]) String[]: IllegalArgumentException
target String...: varargs=[red, blue]
target String... separately: IllegalArgumentException
two String parameters: pair=red+blue
primitive int[]: numbers=[1, 2]
(Object) null: array=null
(Object[]) null for one parameter: IllegalArgumentException
no-arg method: no-arguments
~~~

### Explaining the code and output

- `accept.getParameterCount()` is `1` because the method declares exactly one `String[]` parameter. Elements inside the data array do not increase the method's parameter count.
- `collect.isVarArgs()` is `true` because the source declaration is `String... values`. In bytecode, the final parameter is `String[]`; the varargs flag is recorded in metadata.
- `accept.invoke(receiver, (Object) words)` and `accept.invoke(receiver, new Object[]{words})` both pass a single `String[]` array.
- `(Object[]) words` makes `words` become Reflection's `args` container, resulting in two separate strings; whereas `accept(String[])` requires only one parameter.
- `collect(String... values)` is **the target method's varargs**. However, `Method.invoke` **does not automatically gather `"red", "blue"` into a `String[]` merely because `collect.isVarArgs()` returns `true`**. Thus passing two separate strings still reports a parameter count error; a single `String[]` must be passed.
- `pair(String,String)` has two separate parameters, so spreading `words` (via `(Object[])`) fits right in.
- `int[]` is an object, but **not** `Object[]`. `(Object) new int[]{1,2}` passes the primitive array itself as a single argument; there is no auto-boxing of each `int` element into `Integer`.
- `accept.invoke(receiver, (Object) null)` has **one null argument** compatible with `String[]`, whereas `accept.invoke(receiver, (Object[]) null)` passes a **null argument-list array**, failing to supply the single parameter the target method requires.
- The zero-parameter method `noArguments()` is invoked with `none.invoke(receiver)`; it does not need an `args` array in source code.

The `attempt` helper intentionally prints **the exception class name**, avoiding dependence on error messages that vary across JDK versions. When Reflection successfully invokes a method but the target method itself throws an exception, `Method.invoke` wraps the original error in `InvocationTargetException`; this example does not cause target methods to throw exceptions.

## 6. Array covariance, primitive arrays, and Object[]

### 7.1. Reference arrays are covariant

In Java, `String[]` is a subtype of `Object[]`. This explains why:

~~~java
String[] words = {"a", "b"};
Object[] asObjects = words;
~~~

is valid, and why `method.invoke(receiver, words)` can be interpreted as passing the entire `Object[]` argument array. When intending to pass **an array as data**, use `(Object) words` or create a wrapper `new Object[]{words}`.

Do not try to "solve" this by pouring `String[]` into an `Object[]` without a wrapping layer. For example:

~~~java
Object[] args = words; // args array has 2 elements, not 1
method.invoke(receiver, args); // still two arguments "a", "b"
~~~

To make the args array have one element:

~~~java
Object[] args = { words }; // length == 1; args[0] is String[]
method.invoke(receiver, args);
~~~

### 7.2. Primitive arrays are not Object[]

`int[]`, `long[]`, and `char[]` are all objects and assignable to `Object`, yet **not** subtypes of `Object[]`:

~~~java
int[] nums = {1, 2, 3};
Object asOneObject = nums; // valid
// Object[] notAllowed = nums; // compile error
~~~

Therefore, calling `method.invoke(receiver, nums)` is normally packed by the compiler as a single `Object` argument since `int[]` cannot become `Object[]` directly. Nevertheless, use `(Object) nums` or `new Object[]{nums}` for clear intent and consistency with code handling multiple array kinds.

A primitive integer array does **not** automatically become `Integer[]`, and `Method.invoke` does not automatically box elements inside an array. If the target method takes `Integer[]`, passing `int[]` is still a type mismatch; an appropriate array must be created/converted proactively beforehand.

### 7.3. Multidimensional arrays are also one argument value

For example, target method `void process(String[][] matrix)`:

~~~java
String[][] matrix = { {"a", "b"}, {"c"} };
Method m = Handler.class.getMethod("process", String[][].class);
m.invoke(handler, (Object) matrix);
~~~

`String[][]` is also a subtype of `Object[]` (because each element is a `String[]`), so without casting to `(Object)`, it can be used as Reflection's argument container. When passing **the entire matrix as one argument**, the rule remains the same as for `String[]`.

This example requires a `Handler` class containing `process(String[][])`; it illustrates how to pass it, not a standalone program.

## 7. Passing null and empty arrays accurately

The following three concepts are distinct:

1. **No arguments for the target method**: `m.invoke(receiver)` or `m.invoke(receiver, new Object[0])`.
2. **Exactly one argument with value null**: `m.invoke(receiver, (Object) null)` or `m.invoke(receiver, new Object[]{null})`.
3. **Exactly one argument that is an empty array**: `m.invoke(receiver, (Object) new String[0])` when the target method accepts `String[]`.

These values are not interchangeable:

| Target method | Reflection call | Meaning |
| --- | --- | --- |
| `void noArgs()` | `invoke(receiver)` | No arguments, valid |
| `void noArgs()` | `invoke(receiver, (Object[]) null)` | Null `args` is accepted for a zero-parameter method |
| `void accept(String[] values)` | `invoke(receiver, (Object) null)` | One reference-type parameter, null value |
| `void accept(String[] values)` | `invoke(receiver, (Object) new String[0])` | One valid String[] parameter, length 0 |
| `void accept(String[] values)` | `invoke(receiver, new Object[]{null})` | One valid null parameter |
| `void accept(String[] values)` | `invoke(receiver)` | Missing one argument; parameter count error |
| `void accept(String[] values)` | `invoke(receiver, (Object[]) null)` | Required argument element not provided; parameter count error |

Writing `m.invoke(receiver, null)` without a cast easily causes confusion at **compile time**: the `null` literal may be treated as the `Object[]` array of the varargs call. To pass **one null to the target method**, always use `(Object) null` or `new Object[]{null}`. To pass **an empty array**, create an array of **the target parameter's exact type**; an outer `new Object[0]` means zero arguments, unlike `new Object[]{new String[0]}`.

## 8. Self-check exercises with answers

**Exercise 1.** Given `void process(String[] names)`, `String[] names = {"An", "Binh"};`, and the corresponding `Method m`. How many arguments does `m.invoke(receiver, names)` receive at the Reflection level?

**Answer:** The two elements of `names` can become two arguments to `Method.invoke` because `String[]` is compatible with `Object[]`. The target method requires exactly one `String[]`, so the call is incorrect. Use `m.invoke(receiver, (Object) names)`.

**Exercise 2.** With the same target method, how many parameters does `m.invoke(receiver, new Object[]{names})` pass?

**Answer:** One parameter, which is the `String[]` array, matching the signature.

**Exercise 3.** `void aggregate(String... names)` is retrieved via `getMethod("aggregate", String[].class)`. `method.isVarArgs()` returns `true`. Can you call `method.invoke(receiver, "An", "Binh")` for Reflection to automatically pack the two strings?

**Answer:** No. Varargs metadata does not make `Method.invoke` automatically pack `String[]` for the target method. Use `method.invoke(receiver, (Object) new String[]{"An","Binh"})` or the container `new Object[]{new String[]{"An","Binh"}}`.

**Exercise 4.** A target method accepts two arguments `String left, String right`. You have a variable `String[] names` containing two strings. Write two valid ways to call it.

**Answer:** `m.invoke(receiver, names[0], names[1])` or `m.invoke(receiver, (Object[]) names)`; in this case, spreading the two elements into two arguments is actually what is needed.

**Exercise 5.** For target method `void accept(int[] values)`, why doesn't `int[]` have the same covariance trap as `String[]`?

**Answer:** `int[]` is not `Object[]`. It is a single `Object`; with `Method.invoke`, it can be wrapped as one element. You should still use `(Object) values` for clarity and to avoid surprises when changing array types.

**Exercise 6.** Distinguish `m.invoke(receiver, (Object) null)` from `m.invoke(receiver, (Object[]) null)` if the target method accepts one `String[]`.

**Answer:** The first passes one null argument, valid for a reference type; the second passes a null argument-list array, failing to satisfy the required single parameter, resulting in an argument count error.

**Exercise 7.** Given `void consume(Object[] values)`, you have `Object[] values = { "a", "b" };`. Is `consumeMethod.invoke(receiver, values)` right?

**Answer:** No. To pass all of `values` as a single parameter of type `Object[]`, use `consumeMethod.invoke(receiver, (Object) values)` or `new Object[]{values}`. Without the cast, `Object[] values` is used directly as the two-argument container.

**Exercise 8.** When `Method.invoke` throws `InvocationTargetException`, can you conclude it was because the varargs array was spread?

**Answer:** No. `InvocationTargetException` means the target method already executed and threw an exception. Argument count/type errors in the Reflection invocation mechanism usually cause `IllegalArgumentException` before the method is called.

## 9. Takeaway

**For `Method.invoke(receiver, Object... args)`, the outermost `Object[]` array is always the target method's parameter list.** If the target requires **one parameter that is an array**, place the data array into **one element** of that list:

~~~java
method.invoke(receiver, (Object) array);
method.invoke(receiver, new Object[] { array });
~~~

Do not confuse `String...` of the target method with `Object...` of the Reflection API; each packing mechanism happens in **a different call**. Do not confuse `(Object) array` (one argument) with `(Object[]) array` (the entire argument array). When unsure, check `getParameterTypes()` and construct the outer `Object[]` explicitly.

**Official references:**

- [Java SE 17: `Method.invoke` and `Method.isVarArgs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html).
- [Dev.java: Invoking Methods with Reflection](https://dev.java/learn/reflection/methods/).
- [JLS §15.12.2.4 and §15.12.4.2 — Variable Arity Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).