# 3.8 Handling Varargs and Distinguishing One Array Argument from Multiple Reflective Arguments

When calling a method using Reflection, `Method.invoke` takes **an argument list of the target method**, passed as `Object[]`. If the target method itself takes an array or declares varargs (`String...`, `int...`, `Object...`), you must clearly distinguish between the two array levels. Confusion often causes `IllegalArgumentException: wrong number of arguments` even when the method name and data types appear to be correct.

This is a common bug in plugin loaders, command dispatchers, name-based API callers, testing frameworks, and dynamic object creation mechanisms. The goal of this lesson is to understand how Java packages varargs at the **call site**, how `Method.invoke` and `Constructor.newInstance` accept parameters, how to pass **a single array-typed argument** without accidentally spreading its elements into **multiple reflective arguments**, and how to build a safe adapter when the number of arguments is known at runtime.

## 1. Two Different Varargs Layers

Suppose the target method is declared as:

```java
public static void show(String... items) {
    System.out.println(java.util.Arrays.toString(items));
}
```

This is an illustrative declaration snippet, not a standalone program. At the language level, both of the following direct calls are valid:

```java
show("A", "B");                     // The compiler creates a String[] containing "A", "B".
show(new String[] {"A", "B"});      // Pass the already-created String[] directly.
```

A parameter declared as `String...` is represented as **a single `String[]` parameter** in the method descriptor and in Reflection:

- `getParameterCount()` returns `1`, regardless of the number of elements passed in different calls.
- `getParameterTypes()[0] == String[].class`.
- `isVarArgs() == true` when declared as `String...`; for a method declared with a regular `String[]`, `isVarArgs() == false`.
- To look up the method properly: `SomeClass.class.getMethod("show", String[].class)`. Do not look it up with `getMethod("show", String.class, String.class)`.
- In the class file, the descriptor of `void show(String... items)` is `([Ljava/lang/String;)V`; the same descriptor as `void show(String[] items)`. These two declarations **cannot share the same name to overload within one class** merely by changing `[]` to `...`.

Now consider the **reflection API** signature:

```java
Object Method.invoke(Object receiver, Object... args)
```

`receiver` is the target object receiving the call (use `null` for `static` methods); `args` is **the array containing each actual argument** of the target method. `Method.invoke` itself is also a varargs method, but this level is **different** from the `String...` level in `show`:

```text
Method.invoke(receiver, Object... args)
                        |
                        +-- Object[]: ARGUMENT LIST of the reflective call
                             |
                             +-- args[0] = String[]: ONE array argument of show(...)
```

If Reflection has selected `show(String[])`, the argument list passed down needs **exactly one element**, and that element must be `String[]` (or `null`). `Method.invoke` **does not automatically convert two separate `String`s into one `String[]`** just because `show.isVarArgs()` is `true`.

## 2. One Array or Multiple Arguments: Easily Confused Calls

Given `Method method` pointing to `show(String...)` and `String[] words = {"A", "B"};`. The following table describes **the `args` array that `Method.invoke` actually receives**:

| Call | The `args` list Reflection receives | For `show(String...)` |
| --- | --- | --- |
| `method.invoke(null, (Object) words)` | `Object[]{words}`: **one `String[]`** | Correct, prints `[A, B]` |
| `method.invoke(null, new Object[]{words})` | One element, which is `words` | Correct, prints `[A, B]` |
| `method.invoke(null, (Object[]) words)` | Two elements `"A"`, `"B"` | Wrong argument count: requires one `String[]` |
| `method.invoke(null, words)` | With `words` of type `String[]`, the compiler chooses the call taking `Object[]` | Also passes two elements; may produce a compiler warning |
| `method.invoke(null, "A", "B")` | Two `String` arguments | Wrong argument count, **does not auto-pack** |
| `method.invoke(null)` | Empty argument array (0 elements) | Wrong argument count, not equivalent to `String[0]` |
| `method.invoke(null, (Object) new String[0])` | One empty `String[]` argument | Correct, prints `[]` |
| `method.invoke(null, (Object) null)` | One `null` argument | Correct count; `show` itself decides how to handle `null` |
| `method.invoke(null, (Object[]) null)` | A `null` argument list array, treated as 0 arguments | Wrong argument count |

**Why does casting to `Object` solve this?** `String[]` is a subtype of `Object[]`; if the variable `words` is passed as the second argument to `invoke` as `String[]` or `Object[]`, the compiler can choose the **fixed-arity** invocation, using that array itself as the `args` list. Casting `(Object) words` prevents that interpretation; the compiler must pack `words` as **one element** of a new varargs `Object[]` array.

Alternatively, write the list explicitly as `new Object[]{words}`. Here the **outer** `Object[]` is the argument list, and the **inner** `String[]` is the value of the first argument. Both approaches are correct, but you need to choose based on the program's conditions:

- When you already have **an array you want to pass as one argument**, use `(Object) array` or `new Object[]{array}`.
- When you have **the list of target arguments**, such as `Object[] actualArgs`, use `method.invoke(receiver, actualArgs)`; each element `actualArgs[i]` is matched to each parameter of the target.
- When the target method takes **two separate `String`s**, passing `method.invoke(receiver, "A", "B")` or `method.invoke(receiver, new Object[]{"A", "B"})` is appropriate. An error only occurs if the target signature requires **one `String[]`**.

There is no universal rule like "always cast every array to `Object`": doing so when the target actually needs multiple parameters will cause Reflection to see **one** array argument and report a wrong number of arguments.

## 3. Complete Java 17+ Example: Successful Runs and Controlled Errors

Create the following `VarargsReflectionDemo.java` file. The methods are all `public static` to focus on argument shapes; `null` in the first position of `invoke` represents the receiver of a static method.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;

public class VarargsReflectionDemo {
    public static class Target {
        public static void array(String[] values) {
            System.out.println("array=" + Arrays.toString(values));
        }

        public static void varargs(String... values) {
            System.out.println("varargs=" + Arrays.toString(values));
        }

        public static void pair(String first, String second) {
            System.out.println("pair=" + first + "+" + second);
        }

        public static void numbers(int... values) {
            System.out.println("numbers=" + Arrays.toString(values));
        }

        public static void objects(Object... values) {
            System.out.println("objects=" + Arrays.deepToString(values));
        }

        public static void fails(String... values) {
            throw new IllegalStateException("from target");
        }
    }

    public static class Box {
        private final String[] values;

        public Box(String... values) {
            this.values = values;
        }

        @Override public String toString() {
            return "Box=" + Arrays.toString(values);
        }
    }

    public static void main(String[] args) throws Exception {
        Method array = Target.class.getMethod("array", String[].class);
        Method varargs = Target.class.getMethod("varargs", String[].class);
        Method pair = Target.class.getMethod(
                "pair", String.class, String.class);
        Method numbers = Target.class.getMethod("numbers", int[].class);
        Method objects = Target.class.getMethod("objects", Object[].class);
        String[] words = {"A", "B"};

        System.out.println("array.isVarArgs=" + array.isVarArgs());
        System.out.println("varargs.isVarArgs=" + varargs.isVarArgs());
        System.out.println("varargs.parameters=" + varargs.getParameterCount());
        System.out.println("varargs.parameter0="
                + varargs.getParameterTypes()[0].getTypeName());

        array.invoke(null, (Object) words);         // One String[].
        varargs.invoke(null, (Object) words);       // One String[].
        array.invoke(null, new Object[] {words});   // Also one String[].
        pair.invoke(null, (Object[]) words);        // Two Strings.

        try {
            array.invoke(null, (Object[]) words);
        } catch (IllegalArgumentException e) {
            System.out.println("array expanded="
                    + e.getClass().getSimpleName());
        }
        try {
            varargs.invoke(null, "A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println("varargs expanded="
                    + e.getClass().getSimpleName());
        }

        Object[] mixed = {"A", "B"};
        objects.invoke(null, (Object) mixed);
        try {
            objects.invoke(null, mixed);
        } catch (IllegalArgumentException e) {
            System.out.println("objects expanded="
                    + e.getClass().getSimpleName());
        }

        numbers.invoke(null, new int[] {1, 2});
        varargs.invoke(null, (Object) new String[0]);
        varargs.invoke(null, (Object) null);
        try {
            varargs.invoke(null);
        } catch (IllegalArgumentException e) {
            System.out.println("varargs no args="
                    + e.getClass().getSimpleName());
        }
        try {
            varargs.invoke(null, (Object[]) null);
        } catch (IllegalArgumentException e) {
            System.out.println("varargs null arg list="
                    + e.getClass().getSimpleName());
        }

        Constructor<Box> ctor = Box.class.getConstructor(String[].class);
        System.out.println("constructor.isVarArgs=" + ctor.isVarArgs());
        System.out.println(ctor.newInstance((Object) words));
        try {
            ctor.newInstance("A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println("constructor expanded="
                    + e.getClass().getSimpleName());
        }

        Method fails = Target.class.getMethod("fails", String[].class);
        try {
            fails.invoke(null, (Object) words);
        } catch (InvocationTargetException e) {
            System.out.println("underlying exception="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac --release 17 VarargsReflectionDemo.java
java VarargsReflectionDemo
```

`stdout`:

```text
array.isVarArgs=false
varargs.isVarArgs=true
varargs.parameters=1
varargs.parameter0=java.lang.String[]
array=[A, B]
varargs=[A, B]
array=[A, B]
pair=A+B
array expanded=IllegalArgumentException
varargs expanded=IllegalArgumentException
objects=[A, B]
objects expanded=IllegalArgumentException
numbers=[1, 2]
varargs=[]
varargs=null
varargs no args=IllegalArgumentException
varargs null arg list=IllegalArgumentException
constructor.isVarArgs=true
Box=[A, B]
constructor expanded=IllegalArgumentException
underlying exception=IllegalStateException
```

**Reading the output accurately:**

1. `array` and `varargs` both take one `String[]` at the Reflection level. They differ in the **varargs flag** (`false` vs. `true`), not in the number of parameters.
2. `pair.invoke(null, (Object[]) words)` succeeds because `pair` actually requires **two `String`s**, matching the two elements unpacked from `words`.
3. `array.invoke(null, (Object[]) words)` and `varargs.invoke(null, "A", "B")` fail **before entering the target body** because the Reflection list has two arguments while the target signature has only one.
4. `objects` takes `Object...`: when `mixed` is cast to `Object`, it is preserved as **one `Object[]`**, whereas passing `mixed` bare makes it a two-argument list.
5. `numbers.invoke(null, new int[]{1, 2})` works: `int[]` is an `Object` but **not an `Object[]`**; the compiler packs it into a single argument. With `String[]`, because it **is an `Object[]`**, you need to specify your intent clearly.
6. The `String[0]` array is **one empty array argument**; it is not the same as **an empty Reflection argument list**. `null` also has two levels of meaning depending on the cast.
7. `Constructor.newInstance` encounters the exact same situation. `InvocationTargetException` wraps errors thrown **inside the target method**, not argument-packing errors.

You can further inspect the descriptors of the first two methods with:

```bash
javap -s -p 'VarargsReflectionDemo$Target'
```

Both `array(String[])` and `varargs(String...)` have the descriptor `([Ljava/lang/String;)V`. The `...` syntax is source syntax/a metadata flag, and does not change the array type of the last parameter.

## 4. Tricky Edge Cases: null, Empty Arrays, Object[], Multidimensional Arrays

### 4.1. `null` for the Argument List vs. `null` as an Argument Value

| `Method.invoke` call | Target argument count | Meaning |
| --- | --- | --- |
| `invoke(receiver)` | 0 | No values passed |
| `invoke(receiver, new Object[0])` | 0 | Empty argument list |
| `invoke(receiver, (Object[]) null)` | 0 | Reflection argument list is `null`; valid for a target with no parameters |
| `invoke(receiver, (Object) null)` | 1 | **One** `null` value as the parameter |
| `invoke(receiver, new Object[]{null})` | 1 | **One** `null` element in the list |
| `invoke(receiver, (Object) new String[0])` | 1 | **One** empty `String[]` |

Avoid `invoke(receiver, null)` because the type of `null` does not express clear intent, and the compiler may warn "non-varargs call ... with inexact argument type". Explicitly write `(Object) null` or `(Object[]) null` to select the argument count.

For `show(String... items)`, the two situations are **completely different**:

- Passing `(Object) new String[0]` → the target code receives a zero-length array.
- Passing `(Object) null` → the target code receives **an array variable equal to `null`**; accessing `items.length` will throw `NullPointerException` **inside the target method** and be wrapped by Reflection in `InvocationTargetException`. The `VarargsReflectionDemo` example uses `Arrays.toString` to print null safely.

### 4.2. `Object[]` Is the Most Confusing Type

Suppose the target is `static void consume(Object[] xs)`. Calling `m.invoke(null, new Object[]{"A", "B"})` puts **two** elements `"A"` and `"B"` into the Reflection list; it does not mean passing the entire `Object[]{"A", "B"}` array as **one** argument. The right way:

```java
Object[] data = {"A", "B"};
m.invoke(null, (Object) data);
// Or:
m.invoke(null, new Object[] {data});
```

This is an illustrative snippet with `m` already looked up for `consume(Object[])`. Conversely, if the target really is `static void consumeTwo(Object a, Object b)`, then `m.invoke(null, data)` is the way to pass two arguments.

For a two-dimensional array like `String[][] matrix`, continue using `(Object) matrix` if the target parameter is **one `String[][]`**. A two-dimensional array contains sub-arrays and is still a subtype of `Object[]`, so calling `invoke(receiver, matrix)` bare can be interpreted as **multiple arguments representing the rows of the matrix**.

### 4.3. Primitive Arrays and Element Types

`int[]`, `double[]`, `boolean[]` are not subtypes of `Object[]`. For `void read(int[] nums)`, `m.invoke(receiver, new int[]{1, 2})` normally creates one element in the Reflection list and matches the target. Even so, when writing a framework, create the explicit list `new Object[]{numbers}` for consistency, avoiding reliance on the difference between primitive arrays and reference arrays.

**Do not arbitrarily substitute `Object[]` for `String[]`.** A `String[]` can be assigned to `Object[]`, but an `Object[]` does not automatically convert to `String[]`. If the target parameter is `String[]`, an `Object[]` containing only `String`s is still not a `String[]`. The corresponding error may be `IllegalArgumentException: argument type mismatch` even when the argument count is one.

### 4.4. Reflection Does Not Select Overloads from Passed Values

`Class.getMethod("send", String[].class)` and `Class.getMethod("send", String.class, String.class)` are **two different signature lookups**. Once you have a `Method` object, `invoke` uses the method described by that object; it does not automatically look for another overload to match the argument count.

In addition, `getMethod` and `getDeclaredMethod` themselves have a `Class<?>... parameterTypes` parameter: pass the actual **declared types** (`String[].class` for `String...`), not the types of individual varargs elements as if they were separate method parameters.

## 5. Dynamic Invocation Adapter: Distinguishing EXACT and SPREAD Modes

When writing a framework that receives a list of values at runtime, expose **two separate contracts**:

- **EXACT**: the list already contains each exact argument of the runtime signature. If the last parameter is an array, the last element of the list must be an array of the right type (or `null`).
- **SPREAD**: the caller provides the fixed parameters first, then multiple **element values** for the varargs parameter; the adapter is responsible for packing the tail into an array of the right `componentType` before calling `Method.invoke`.

Do not **guess** the mode based on whether the last element is an array: a single array might be intended by the user to be passed as *one value*, or as a list to be spread; the `null` case is even harder to guess. The mode must be determined by the API contract.

Create a second file `VarargsAdapterDemo.java`:

```java
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.Arrays;

public class VarargsAdapterDemo {
    public static String summarize(String prefix, int... numbers) {
        return prefix + Arrays.toString(numbers);
    }

    static Object invokeExact(Method method, Object receiver, Object[] args)
            throws ReflectiveOperationException {
        return method.invoke(receiver, args);
    }

    static Object invokeSpread(Method method, Object receiver, Object[] supplied)
            throws ReflectiveOperationException {
        if (!method.isVarArgs()) {
            throw new IllegalArgumentException("Target is not varargs");
        }
        Class<?>[] types = method.getParameterTypes();
        int fixed = types.length - 1;
        if (supplied.length < fixed) {
            throw new IllegalArgumentException("Missing fixed arguments");
        }

        Object[] packed = new Object[types.length];
        System.arraycopy(supplied, 0, packed, 0, fixed);
        Class<?> component = types[fixed].getComponentType();
        Object tail = Array.newInstance(component, supplied.length - fixed);
        for (int i = fixed; i < supplied.length; i++) {
            Array.set(tail, i - fixed, supplied[i]);
        }
        packed[fixed] = tail;
        return method.invoke(receiver, packed);
    }

    public static void main(String[] args) throws Exception {
        Method method = VarargsAdapterDemo.class.getMethod(
                "summarize", String.class, int[].class);

        System.out.println(invokeSpread(method, null,
                new Object[] {"n=", 1, 2, 3}));
        System.out.println(invokeSpread(method, null,
                new Object[] {"empty="}));
        System.out.println(invokeExact(method, null,
                new Object[] {"array=", new int[] {5, 8}}));
    }
}
```

```bash
javac --release 17 VarargsAdapterDemo.java
java VarargsAdapterDemo
```

`stdout`:

```text
n=[1, 2, 3]
empty=[]
array=[5, 8]
```

**How the adapter works:**

1. For `summarize(String, int...)`, `getParameterTypes()` returns `[String.class, int[].class]`, so the number of fixed parameters is `1`.
2. In SPREAD, create `Object[2]` for the final argument list. The first element is `prefix`, and the second element is an `int[]` created using `Array.newInstance(int.class, size)`.
3. `Array.set` can unbox `Integer`s and apply valid primitive conversions when placing them into an `int[]` array. An incompatible value causes an error; this is a signal that input handling is needed.
4. When 0 elements are supplied for the varargs part, you must still create `int[0]`. Do not omit the last array parameter.
5. `method.invoke(receiver, packed)` has `packed` of type `Object[]`, so each element of `packed` corresponds to one actual parameter of the target; you do **not** need to cast the entire `packed` to `Object`.

**Limitations of the example:** this is an illustrative adapter for a varargs method that has already been looked up beforehand. It does not select overloads, does not automatically parse strings into numbers, does not handle any custom type-conversion rules, and does not unwrap an already-prepared array in SPREAD mode. Passing `new Object[]{"n=", new int[]{5, 8}}` to SPREAD will try to put an `int[]` into an `int` element slot and fail; choose EXACT for that case. If you want to support null, casting, logging, and overloads in a real framework, design explicit policies at the boundary layer.

## 6. Constructors, Receivers, and Related APIs

### 6.1. `Constructor.newInstance(Object... initargs)`

A constructor also takes an **`Object[]` list**, just like the second parameter of `Method.invoke` but without a receiver. If the constructor is declared as `Box(String... values)`, Reflection sees **one `String[]` parameter**, so:

```java
Constructor<Box> constructor = Box.class.getConstructor(String[].class);
Box a = constructor.newInstance((Object) new String[]{"A", "B"});
Box b = constructor.newInstance(new Object[]{
        new String[]{"A", "B"}
});
```

The snippet above is based on the `Box` class in the `VarargsReflectionDemo.java` example. Both `a` and `b` are valid. `constructor.newInstance("A", "B")` does not automatically combine two strings into a `String[]` and will throw `IllegalArgumentException` due to the wrong number of arguments.

### 6.2. Instance Methods and Static Methods

With `Method.invoke`, **the first parameter is the receiver**, not the first argument of the target method:

```java
Method method = Account.class.getMethod("setTags", String[].class);
Account account = new Account();
method.invoke(account, (Object) new String[]{"vip", "trial"});
```

This is an illustrative snippet, assuming `Account` has a public constructor and an instance method `setTags(String...)`. If the target is `static`, pass `null` as the receiver. If the target is an instance method, pass a valid object of the declaring class or a compatible subtype. A receiver error cannot be solved by changing the cast of the varargs array.

### 6.3. Distinguishing Packing Errors from Errors Inside the Target

| Result / exception | Common source | What to check |
| --- | --- | --- |
| `NoSuchMethodException` on `getMethod` | Wrong name lookup or wrong list of **parameter `Class`es** | For `String...` use `String[].class`; check primitive types, overloads, public/declared scope |
| `IllegalArgumentException: wrong number of arguments` on `invoke` | Number of elements in `Object[] args` differs from the Method's declared parameter count | Print `getParameterCount()`, `args.length`, check if a single array was spread into multiple arguments |
| `IllegalArgumentException: argument type mismatch` | Right count, but type of `args[i]` is incompatible with the parameter type | Compare `getParameterTypes()` with `args[i].getClass()`; note that `String[]` is different from `Object[]` |
| `IllegalAccessException` / `InaccessibleObjectException` | Member access issue or module restriction | Check visibility, module exports/opens; do not arbitrarily disable checks |
| `InvocationTargetException` | Code inside the method/constructor threw an exception | Read `getCause()` for the underlying error; may be an NPE if the target does not accept a null array |
| `NullPointerException` before calling the target body | For example, a null receiver on an instance method, or adapter logic accessing a null list | Determine whether null is in the **receiver**, the **args list**, or the **args[0] value** |

`Method.invoke` can automatically convert some boxed values to primitive parameters via unboxing and valid widening, but it **does not** turn `String` into `String[]`, does not automatically create a varargs array for the target method, and does not perform invalid narrowing.

In a real application, the logger should record the **selected Method**, `isVarArgs()`, `getParameterTypes()`, the number of elements in the argument list, and **the runtime type of each element**; strictly avoid printing sensitive parameter data. For array parameters, logging the type such as `[Ljava.lang.String;` or `[I` often helps spot a shape mismatch faster than just printing `toString()`.

## 7. Decision Workflow When Calling Reflection

1. **Check the target runtime signature.** Use `Method.getParameterCount()` and `getParameterTypes()`; `isVarArgs()` only tells you whether the declaration has `...`. If the method has two parameters, accept two values; if the last parameter is an array, prepare a compatible array.
2. **Distinguish the argument list from an array value.** `Object[]{String[]}` represents one array parameter; `Object[]{"A", "B"}` represents two string parameters.
3. **Decide EXACT or SPREAD at the integration boundary.** EXACT keeps the supplied array as-is; SPREAD gathers the trailing elements into an array of the right type. Do not ambiguously guess from the runtime type.
4. **Handle 0 elements and null intentionally.** A `new String[0]` array, a `null` argument, and an empty argument list have three different meanings.
5. **Call `invoke` with a properly structured `Object[]` list.** For example, `method.invoke(receiver, new Object[]{stringArray})`, or `method.invoke(receiver, preparedArgs)` when `preparedArgs` already contains one element per target parameter.
6. **Classify the error before fixing.** Wrong number/type → fix the argument list; InvocationTargetException → inspect the inner error; NoSuchMethodException → fix the lookup; IllegalAccessException → check access permissions.

### Three Self-Check Exercises

**Exercise A.** The target is `static void task(String[] lines)`. You have `String[] data = {"x", "y"};`. Write the Reflection call that passes the whole array. **Answer:** `method.invoke(null, (Object) data)` or `method.invoke(null, new Object[]{data})`. `method.invoke(null, (Object[]) data)` will become two strings and fail.

**Exercise B.** The target is `static void task(String first, String second)`, with the same `data`. **Answer:** `method.invoke(null, (Object[]) data)` will pass two strings; `method.invoke(null, (Object) data)` would be one array argument that does not match the signature.

**Exercise C.** The target is `static void task(int... ids)`. How do you call it with **0** elements? **Answer:** `method.invoke(null, (Object) new int[0])`. Calling `method.invoke(null)` creates 0 **Reflection arguments**, whereas the target still requires exactly 1 `int[]` parameter.

## Authoritative References

- JDK 17 `Method.invoke` — signature `Object... args`, argument count/type checking rules, and `InvocationTargetException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- JDK 17 `Constructor.newInstance` — initialization arguments and conversion errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- JDK 17 `Executable.isVarArgs`, `getParameterTypes`, and `getParameterCount`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- Oracle Java Tutorial, *Invoking Methods with a Variable Number of Arguments*: https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html
- Oracle Java Tutorial, *IllegalArgumentException from Method.invoke()*: https://docs.oracle.com/javase/tutorial/reflect/member/methodTrouble.html
- Java Language Specification, Java SE 17, `15.12 (*Method Invocation Expressions*) and `8.4.1 (*Formal Parameters*): https://docs.oracle.com/javase/specs/jls/se17/html/

**Takeaway:** `varargs` at the `Method.invoke` call site is the mechanism for packing the **reflective argument list** (`Object[]`). `varargs` on the target method is **one array parameter** at runtime. Using the `(Object) array` cast or the `new Object[]{array}` list passes the array as **one argument**; casting `(Object[]) array` passes the array elements as **multiple arguments**. Choose the right approach based on the target signature.
