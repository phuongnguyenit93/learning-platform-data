# Target Method Varargs Are Represented by a Single Array Parameter

## 1. Key point: `String...` is a `String[]` parameter at runtime

In Java source code, a **varargs** declaration allows the caller to pass a variable number of arguments in the last position:

~~~java
void send(String channel, String... messages) {
    // messages has type String[]
}
~~~

The compiler allows:

~~~java
send("news");
send("news", "A");
send("news", "A", "B");
send("news", new String[]{"A", "B"});
~~~

These are illustrative snippets inside a class having the `send` method, not a standalone program. In calls using a variable number of elements, the compiler **packs the trailing arguments into a `String[]` array** to pass to the target method.

At runtime, the declared signature of `send` has only **two parameters**:

1. `String channel`.
2. `String[] messages`.

Varargs is **syntactic support at the call site in Java code**; it does not mean the target method actually has any number of runtime parameters. The JVM uses an array type at the end of the signature and metadata marking the method as accepting varargs.

**Specifically with Reflection:** `Method.invoke` **does not automatically gather separate arguments into the target method's trailing array**. When invoking via Reflection, you must prepare the final array with the right type and in the right position.

## 2. `getMethod` looks up the array signature, not separate elements

Given a public method:

~~~java
public void send(String channel, String... messages) { }
~~~

Lookup:

~~~java
Method m = Messenger.class.getMethod(
        "send", String.class, String[].class);
~~~

This is an illustrative snippet, requiring class `Messenger`, `import java.lang.reflect.Method`, and checked exception handling.

Do not use:

~~~java
// Wrong: looks for three separate String parameters, which does not exist.
Messenger.class.getMethod(
        "send", String.class, String.class, String.class);
~~~

A method declared as `send(String, String...)` has the exact runtime parameter form `(String, String[])`. Therefore:

| Lookup call | Result |
| --- | --- |
| `getMethod("send", String.class, String[].class)` | Finds the varargs-declared method. |
| `getMethod("send", String.class)` | Does not find this overload if the class only declares `(String, String[])`. |
| `getMethod("send", String.class, String.class)` | Does not match because the second parameter requires `String[]`. |
| `getMethod("send", String.class, String.class, String.class)` | Does not match because the parameter count is wrong. |

`getMethod` requires **exact declared parameter types**; it does not perform overload resolution like the compiler, nor does it automatically expand or pack varargs. Looking up the wrong signature causes `NoSuchMethodException`, never even reaching `invoke`.

### Inspecting metadata with Reflection

~~~java
Method method = Messenger.class.getMethod(
        "send", String.class, String[].class);

System.out.println(method.isVarArgs());           // true
System.out.println(method.getParameterCount());   // 2
System.out.println(method.getParameterTypes()[1].isArray()); // true
System.out.println(method.getParameterTypes()[1].getComponentType()); // class java.lang.String
~~~

`isVarArgs()` indicates whether the method **is declared** to accept a variable number of arguments. `getParameterTypes()` still returns an array of **formal parameter types**, and the last type is `String[].class`.

If a method is declared as `send(String, String[])` (writing the array directly) instead of `send(String, String...)`, the runtime type signature is still `(String, String[])`, but `isVarArgs()` will return `false`. Both forms cannot be declared as two distinct overloads in the same class, because they have the same signature after compilation.

## 3. Two varargs layers that are very easy to confuse

With Reflection, there are **two `...` notations with two different meanings**:

~~~java
// Target method:
void send(String channel, String... messages);

// Reflection API:
Object Method.invoke(Object receiver, Object... args);
~~~

First layer: `messages` is the **second parameter of `send`**, of type `String[]`.  
Second layer: `args` is the **`Object[]` array containing all arguments of the `send` call**, excluding the instance method's receiver.

A correct call has the structure:

~~~text
Method.invoke(
    receiver,                               <-- instance invoking method
    new Object[]{
        "news",                              <-- parameter #1: String
        new String[]{"A", "B"}               <-- parameter #2: String[]
    }
)
~~~

The number of elements in `Object[]` is **2**, not 3. The `String[]` array can contain 0, 1, 2, or many elements, yet it remains **one element** in Reflection's argument array.

Therefore:

~~~java
method.invoke(receiver, "news",
        (Object) new String[]{"A", "B"});

method.invoke(receiver,
        new Object[]{"news", new String[]{"A", "B"}});
~~~

Both forms above call `send` with exactly two parameters. The second form explicitly specifies the entire Reflection argument array. The first form uses `(Object)` to assert that the `String[]` array is **a single argument** of `Method.invoke`, which is especially useful for a target method having only one array parameter.

## 4. Complete runnable Java 17+ program

Create the file **`ReflectVarargsLesson.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectVarargsLesson {
    public static class Messenger {
        public void send(String channel, String... messages) {
            System.out.println(channel + " -> " + Arrays.toString(messages));
        }

        public void only(String... messages) {
            System.out.println("only -> " + Arrays.toString(messages));
        }

        public static void launch(String... args) {
            System.out.println("launch -> " + Arrays.toString(args));
        }
    }

    public static void main(String[] args) throws Exception {
        Messenger receiver = new Messenger();

        // 1. Java compiler automatically packs varargs at direct call sites.
        receiver.send("direct", "A", "B");

        // 2. Reflection sees a signature consisting of String and String[].
        Method method = Messenger.class.getMethod(
                "send", String.class, String[].class);
        System.out.println("isVarArgs=" + method.isVarArgs());
        System.out.println("parameterCount=" + method.getParameterCount());
        System.out.println("second="
                + method.getParameterTypes()[1].getTypeName());
        System.out.println("component="
                + method.getParameterTypes()[1].getComponentType().getTypeName());

        // 3. Two arguments of the target method: String and String[].
        method.invoke(receiver, "reflect",
                (Object) new String[]{"C", "D"});
        method.invoke(receiver,
                new Object[]{"packed", new String[]{"E", "F"}});

        // 4. An empty array differs from a null array.
        method.invoke(receiver, "empty", (Object) new String[0]);
        method.invoke(receiver, "null", (Object) null);

        // 5. Reflection does not automatically pack separate strings into String[].
        try {
            method.invoke(receiver, "wrong", "G", "H");
        } catch (IllegalArgumentException e) {
            System.out.println("expanded: IllegalArgumentException");
        }

        // 6. Target method having only one String[] parameter.
        Method only = Messenger.class.getMethod("only", String[].class);
        only.invoke(receiver, (Object) new String[]{"x", "y"});

        try {
            // Intentionally spread array into 2 args of Method.invoke.
            only.invoke(receiver, (Object[]) new String[]{"x", "y"});
        } catch (IllegalArgumentException e) {
            System.out.println("array spread: IllegalArgumentException");
        }

        // 7. Static method: receiver is null.
        Method launch = Messenger.class.getMethod(
                "launch", String[].class);
        launch.invoke(null, (Object) new String[]{"one", "two"});
    }
}
~~~

Compile and run:

~~~bash
javac ReflectVarargsLesson.java
java ReflectVarargsLesson
~~~

Verified stdout:

~~~text
direct -> [A, B]
isVarArgs=true
parameterCount=2
second=java.lang.String[]
component=java.lang.String
reflect -> [C, D]
packed -> [E, F]
empty -> []
null -> null
expanded: IllegalArgumentException
only -> [x, y]
array spread: IllegalArgumentException
launch -> [one, two]
~~~

### Reading the output properly

- `direct` is a normal Java call: the compiler builds `String[]` automatically.
- `isVarArgs=true` and `parameterCount=2` confirm that varargs is a single array parameter in the runtime signature.
- `reflect` and `packed` produce the same target call even though the two ways of preparing `Object[]` differ.
- `empty` passes a **0-length array**; `null` passes a **null array reference**. The target method receives two different values; here `Arrays.toString(String[])` displays `[]` and `null`.
- `expanded` supplies three `String` arguments to a target call having two formal parameters; `Method.invoke` does not pack `"G", "H"` into an array automatically.
- `array spread` intentionally supplies a `String[]` as the **Reflection API's `Object[]` argument array**, i.e., two separate strings. The result does not match the `only(String[])` method.
- `launch` proves the same rules apply to `static` methods; the receiver passed to `Method.invoke` is `null`.

## 5. `main(String[])` and static varargs methods

The declaration:

~~~java
public static void main(String... args) {
    System.out.println(java.util.Arrays.toString(args));
}
~~~

has a single runtime parameter `String[]`, just like `main(String[])`. To invoke it via Reflection:

~~~java
Method main = App.class.getMethod("main", String[].class);
main.invoke(null, (Object) new String[]{"first", "second"});
~~~

This is an illustrative example in a program having class `App` and handling Reflection exceptions. Because a static method needs no receiver, `invoke` passes `null` as the first argument. `(Object)` keeps **the entire `String[]` as a single argument of the target method**, preventing the strings from being interpreted as multiple elements of `Object... args`.

If you build a plugin runner, CLI launcher, or test runner invoking `main` dynamically, this is the unambiguous way to pass args.

## 6. How to write a utility to invoke varargs methods dynamically

If inputs come from an array of individual values, **build the trailing array yourself according to `componentType`** of the varargs parameter. Not every varargs is `String...`; it can be `int...`, `Number...`, `Object...`, or a multidimensional array.

Suppose you have found the right `Method` with `isVarArgs() == true` and know `fixedCount = method.getParameterCount() - 1`. An argument-preparation algorithm (descriptive level) consists of:

1. Validate that the number of input values is sufficient for the fixed parameters.
2. Keep arguments corresponding to `parameterTypes[0..fixedCount-1]` as-is, checking compatibility.
3. Obtain the trailing array type via `parameterTypes[fixedCount]`, and element type via `getComponentType()`.
4. Use `java.lang.reflect.Array.newInstance(componentType, extraCount)` to create an array of the right type, assigning each remaining value via `Array.set` if conversion is valid.
5. Build `Object[] invocationArgs` with exact length `method.getParameterCount()`, with the last slot holding the newly created array.
6. Call `method.invoke(receiver, invocationArgs)`.

Illustrative example of packing the `String[]` array:

~~~java
String[] trailing = new String[]{"alpha", "beta"};
Object[] invocationArgs = new Object[]{"news", trailing};
method.invoke(receiver, invocationArgs);
~~~

This snippet is in the context of a compatible `method` and `receiver`; `invocationArgs` has two elements. For `int...`, the trailing array must be `int[]`, **not** `Integer[]`. `Array.set` handles appropriate conversions or reports an error when a value is incompatible; the application must validate data before calling.

For libraries accepting dynamic input, you must also specify the case where the trailing array is already provided: choosing to **keep the array as a single argument** or **pack elements into a new array** depends on the API contract. Do not accidentally both keep the array and wrap it again.

## 7. Self-check questions

**Question 1.** How many parameters does `void log(int level, String... parts)` have in `getParameterTypes()`?  
**Two:** `int.class` and `String[].class`.

**Question 2.** Does `logMethod.invoke(receiver, 2, "a", "b")` automatically pack `"a", "b"` into a `String[]`?  
**No.** You must pass `logMethod.invoke(receiver, 2, (Object) new String[]{"a", "b"})` or `new Object[]{2, new String[]{"a","b"}}`.

**Question 3.** Does the method `void print(String[] values)` (without `...`) require one array argument when called via Reflection?  
**Yes.** Reflective invocation inspects the runtime parameter list; the array is still one parameter. `isVarArgs()` only differs in declaration metadata.

**Question 4.** If source code declares `int...`, does `getMethod` pass `int.class`, `Integer[].class`, or `int[].class`?  
**`int[].class`**, because the signature has one primitive array parameter.

**Question 5.** How many arguments does `Method.invoke(receiver, (Object) new String[]{"x", "y"})` pass to the target method?  
**One**, which is the entire `String[]` array.

**Question 6.** A static method declares `String... args`; what should the receiver of `invoke` be?  
**`null`**; the target method's argument is still one `String[]`.

**Takeaway:** there are **two varargs layers**: the compiler packs varargs in normal Java calls; `Method.invoke(Object, Object...)` only packs arguments of **the Reflection API itself**. A target method declaring `T...` still has exactly one `T[]` parameter, and you must pass that array in the right position.

### Official references

- [JDK 17 — `Method.invoke`, `getParameterTypes`, `isVarArgs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Oracle Java Tutorials — Invoking Methods with a Variable Number of Arguments](https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html)
- [Dev.java — Invoking Methods](https://dev.java/learn/api/reflection-method-handles/reflection/methods/)
- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1)
- [Java Language Specification §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2)