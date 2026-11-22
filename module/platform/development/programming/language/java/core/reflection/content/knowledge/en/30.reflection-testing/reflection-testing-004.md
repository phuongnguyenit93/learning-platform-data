# Testing `invoke` with `null`, `varargs`, Arrays, and Wrong Types

## 1. Goal

**Method.invoke(Object obj, Object... args)** is the Core Reflection API for calling a method at runtime. When testing Reflection tools, the four most common bug categories are passing **null** ambiguously, mishandling **varargs** and **arrays**, supplying incompatible **argument types/counts**, and confusing exceptions thrown by Reflection with exceptions thrown by the target method.

Learners must distinguish two layers of varargs:

- Java source layer: when calling **Method.invoke**, the compiler decides how arguments are packed into this API's own **Object... args** parameter.
- Target method layer: Reflection receives an argument list; the target method must receive the exact count and types matching its runtime signature. Reflection does not automatically bundle loose strings into a `String[]` for a target method declared with `String...`.

This lesson practices on JDK 17+, without needing Spring, JUnit, or external libraries. The sample program's output is verified against the Java runtime.

## 2. `Method.invoke` Rules

| Component | Rule | Typical error |
| --- | --- | --- |
| Receiver for instance method | Object must be non-null and compatible with the declaring class | `NullPointerException` if null; `IllegalArgumentException` if wrong type |
| Receiver for static method | Can pass null; receiver object is unused | No instance creation required |
| Argument list | Exact element count matching `method.getParameterCount()` | `IllegalArgumentException` when too many/too few |
| Reference parameter type | Argument compatible with declared type; null may be valid | `IllegalArgumentException` if not assignable |
| Primitive parameter | Unboxing and widening valid; rejects null or narrowing | `IllegalArgumentException` |
| Varargs method | One final formal parameter of array type | Reflection does not auto-pack loose arguments |
| Return value | Primitives are boxed; `void` returns null from `invoke` | Do not treat `void` as returning another object |
| Method body throws `Throwable` | Reflection wraps `Throwable` thrown by target method | `InvocationTargetException` with `getCause()` |
| Access permission | Access checks still apply | `IllegalAccessException` |

**Looking up a method and invoking a method are two separate steps.** For example, a method declared as **triple(int)** is found using **getMethod("triple", int.class)**; using **Integer.class** throws **NoSuchMethodException** at the lookup step. However, once you have the `Method` object for `triple(int)`, passing a matching wrapper **Integer** can be unboxed to invoke the target method.

## 3. `null`: Receiver, Single `null` Argument, `null` Arguments Array

Consider **String accept(String value)** and a valid **target** object.

| Call | Target method's argument count | Result |
| --- | --- | --- |
| **accept.invoke(target, (Object) null)** | 1 argument with value null | Valid for String |
| **accept.invoke(target, new Object[]{null})** | 1 argument with value null | Valid for String |
| **accept.invoke(target, (Object[]) null)** | 0 arguments | `IllegalArgumentException` due to missing argument |
| **accept.invoke(target)** | 0 arguments | `IllegalArgumentException` |
| **accept.invoke(null, "hi")** | Null receiver, not null argument | `NullPointerException` |
| **accept.invoke("wrong receiver", "hi")** | Receiver is not Target | `IllegalArgumentException` |
| **ping.invoke(null)** with static `ping()` | Zero arguments, static | Succeeds |

**(Object) null** is treated by the compiler as **one element** in `Method.invoke`'s `Object[]` varargs list. **(Object[]) null** is the **entire** argument-list array being null and is interpreted as zero arguments. Writing **invoke(target, null)** without a cast can trigger a compiler warning or make readers uncertain which form you intended. In libraries, use **new Object[]{null}** when you want a single null argument.

For a zero-parameter method, both **invoke(target)** and **invoke(target, (Object[]) null)** represent a zero-argument call. For an **int** parameter, even **(Object) null** is invalid because `int` is primitive.

## 4. Target Method Varargs vs. `Method.invoke` Varargs

A method declared as:

~~~java
public String join(String... parts) {
    return parts == null
            ? "array=<null>"
            : String.join("|", parts);
}
~~~

has the runtime signature **join(String[])**, meaning only **one formal parameter**. The `Method` object is looked up as follows:

~~~java
Method join = Target.class.getMethod("join", String[].class);
~~~

These are illustrative snippets; the full `Target` class is in section 7.

| Call | Interpretation | Result |
| --- | --- | --- |
| **join.invoke(target, "A", "B")** | Two loose Strings; method needs one `String[]` | `IllegalArgumentException` |
| **join.invoke(target, (Object) new String[]{"A", "B"})** | One `String[]` argument | Strings A and B joined by `\|` |
| **join.invoke(target, new Object[]{new String[]{"A", "B"}})** | Outer `Object[]` has one `String[]` element | Succeeds |
| **join.invoke(target, (Object[]) new String[]{"A", "B"})** | `String[]` used as `Object[]` holding two arguments | `IllegalArgumentException` |
| **join.invoke(target, (Object) new String[0])** | One argument that is an empty array | Empty string |
| **join.invoke(target, (Object) null)** | One `String[]` argument with value null | Returns `array=<null>` |
| **join.invoke(target, (Object) new int[]{1, 2})** | An `int[]` incompatible with `String[]` | `IllegalArgumentException` |

**Array covariance trap:** `String[]` is a subtype of `Object[]`. Writing **join.invoke(target, new String[]{"A","B"})** directly can cause the compiler to use that `String[]` itself as `invoke`'s **Object[]** varargs list—i.e., two arguments; the compiler usually emits an ambiguous call warning. When you want to pass **one array as one argument**, write **(Object) new String[]{...}** or **new Object[]{new String[]{...}}**.

Do not equate calling **target.join("A","B")** with **join.invoke(target, "A","B")**. In the first case, the Java compiler packs the varargs for the target method; in the second case, Reflection sees two arguments and does not automatically group them into a `String[]`.

## 5. Testing Primitives and Wrong-Type Arguments

For **int triple(int n)**:

- **Integer.valueOf(4)** is unboxed to `int`, returning `12`.
- **Short.valueOf((short) 4)** is unboxed to `short` and widened to `int`, returning `12`.
- **Long.valueOf(4)** cannot be narrowed from `long` to `int`, resulting in **IllegalArgumentException**.
- **"4"** is a `String` and is not auto-parsed to `int`, resulting in **IllegalArgumentException**.
- **(Object) null** cannot supply a primitive `int` value, resulting in **IllegalArgumentException**.
- Too many or too few arguments also result in **IllegalArgumentException**.

Reflection does not replace converters in the HTTP/JSON/configuration layer. If you want to accept the string `"4"`, parse and validate explicitly before passing a matching `Integer`/`int`; do not expect `Method.invoke` to convert arbitrary inputs into the target parameter type.

## 6. Two Error Layers: Argument Checking vs. Target Code

**Error before the method body runs:**

~~~java
triple.invoke(target, "4");
~~~

Reflection rejects a `String` for an `int` parameter and throws **IllegalArgumentException directly**. The target method body has not executed.

**Error after the method body runs:**

~~~java
public String fail() {
    throw new IllegalStateException("boom");
}
~~~

When calling **fail.invoke(target)**, Reflection wraps the exception from the target code in **InvocationTargetException**. Use **getCause()** to inspect **IllegalStateException("boom")**.

Even when the target method itself throws **IllegalArgumentException**, the outer exception at the Reflection caller is still **InvocationTargetException**, with cause `IllegalArgumentException`. Hence unit tests must check **both the outer type and the cause**, not just the final exception name.

Additionally, **IllegalAccessException** can come from access checks, **ExceptionInInitializerError** can come from failed static class initialization, and **NoClassDefFoundError** can result from a class that previously failed initialization or a missing dependency. They are not the same as argument-packing errors.

## 7. Complete Java 17+ Example: 18 Test Cases

Save the code below as **InvokeEdgeDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Locale;

public class InvokeEdgeDemo {
    public static class Target {
        public String accept(String s) {
            return s == null ? "<null>" : s.toUpperCase(Locale.ROOT);
        }

        public int triple(int n) {
            return n * 3;
        }

        public String join(String... parts) {
            return parts == null
                    ? "array=<null>"
                    : String.join("|", parts);
        }

        public static String ping() {
            return "pong";
        }

        public String fail() {
            throw new IllegalStateException("boom");
        }
    }

    @FunctionalInterface
    interface Action {
        Object run() throws Throwable;
    }

    static void check(String label, Action action) {
        try {
            System.out.println(label + " -> " + action.run());
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println(label + " -> InvocationTargetException("
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage() + ")");
        } catch (Throwable e) {
            System.out.println(label + " -> "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Target target = new Target();

        Method accept = Target.class.getMethod(
                "accept", String.class);
        Method triple = Target.class.getMethod(
                "triple", int.class);
        Method join = Target.class.getMethod(
                "join", String[].class);
        Method ping = Target.class.getMethod("ping");
        Method fail = Target.class.getMethod("fail");

        check("null value",
                () -> accept.invoke(target, (Object) null));
        check("null args array",
                () -> accept.invoke(target, (Object[]) null));
        check("null receiver",
                () -> accept.invoke(null, "hi"));

        check("static receiver null",
                () -> ping.invoke(null));
        check("static receiver supplied",
                () -> ping.invoke(target));

        check("null for int",
                () -> triple.invoke(target, (Object) null));
        check("short to int",
                () -> triple.invoke(target, Short.valueOf((short) 4)));
        check("wrong type",
                () -> triple.invoke(target, "4"));
        check("wrong count",
                () -> accept.invoke(target));
        check("wrong receiver",
                () -> accept.invoke("not-target", "hi"));

        check("join expanded",
                () -> join.invoke(target, "A", "B"));
        check("join String[] spread",
                () -> join.invoke(
                        target, (Object[]) new String[]{"A", "B"}));
        check("join packed",
                () -> join.invoke(
                        target, (Object) new String[]{"A", "B"}));
        check("join Object[] args",
                () -> join.invoke(target,
                        new Object[]{new String[]{"A", "B"}}));
        check("join wrong array type",
                () -> join.invoke(
                        target, (Object) new int[]{1, 2}));
        check("join null array argument",
                () -> join.invoke(target, (Object) null));
        check("join empty array",
                () -> join.invoke(target, (Object) new String[0]));

        check("target exception",
                () -> fail.invoke(target));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 InvokeEdgeDemo.java
java InvokeEdgeDemo
~~~

Stdout output:

~~~text
null value -> <null>
null args array -> IllegalArgumentException
null receiver -> NullPointerException
static receiver null -> pong
static receiver supplied -> pong
null for int -> IllegalArgumentException
short to int -> 12
wrong type -> IllegalArgumentException
wrong count -> IllegalArgumentException
wrong receiver -> IllegalArgumentException
join expanded -> IllegalArgumentException
join String[] spread -> IllegalArgumentException
join packed -> A|B
join Object[] args -> A|B
join wrong array type -> IllegalArgumentException
join null array argument -> array=<null>
join empty array -> 
target exception -> InvocationTargetException(IllegalStateException:boom)
~~~

**Output explanation:**
1. **null value** passes a single null for `String`, and the method runs normally; **null args array** passes an empty list, causing an argument count mismatch; **null receiver** lacks a valid instance.
2. Method **ping** is static, so a null receiver or a provided receiver makes no difference to the result.
3. **triple(int)** only accepts compatible arguments; `Short` is widened, while `String` and `null` are not.
4. **join(String...)** actually takes one `String[]`, so two loose strings fail; both packing styles **(Object) String[]** and **new Object[]{String[]}** succeed.
5. **join empty array ->** has nothing after the arrow because `String.join` on an empty array returns an empty string.
6. **target exception** shows the method body ran and threw `IllegalStateException`, wrapped by Reflection in `InvocationTargetException`.

The example was executed with the JDK and verified across all 18 cases. The program uses only features available since before Java 17.

### The Two-Level Array Problem

The two calls below have different meanings:

~~~java
join.invoke(target, (Object[]) new String[]{"A", "B"});
join.invoke(target, (Object) new String[]{"A", "B"});
~~~

The first call supplies **two** Reflection arguments; the second call supplies **one** `String[]` argument. The cast here expresses intent, not merely silencing a compiler warning.

## 8. Write Assertions Instead of Only Printing Results

A practice program that prints output helps you learn the mechanism, but regression tests should verify exact results or exceptions. You can use JUnit 5 if the project already has the dependency, or write a plain Java helper:

~~~java
@FunctionalInterface
interface ThrowingAction {
    void run() throws Throwable;
}

static <T extends Throwable> T expectThrows(
        Class<T> expected, ThrowingAction action) {
    try {
        action.run();
    } catch (Throwable actual) {
        if (expected.isInstance(actual)) {
            return expected.cast(actual);
        }
        throw new AssertionError(
                "Expected " + expected.getName()
                + ", actual " + actual.getClass().getName(), actual);
    }
    throw new AssertionError(
            "Expected exception " + expected.getName());
}
~~~

This is an **illustrative snippet to place inside a test class**, not a standalone program. Example checking both error layers:

~~~java
IllegalArgumentException inputError = expectThrows(
        IllegalArgumentException.class,
        () -> triple.invoke(target, "4"));

InvocationTargetException executionError = expectThrows(
        InvocationTargetException.class,
        () -> fail.invoke(target));

if (!(executionError.getCause() instanceof IllegalStateException)) {
    throw new AssertionError("Unexpected cause");
}
~~~

**Better than catching a generic exception and letting the test PASS:** you must assert that the exception belongs to the right layer, preserves its cause, and for succeeding cases verify the return value rather than merely checking "no crash."

| Phase | Key verification |
| --- | --- |
| Arrange | Look up the exact `Method` by name and parameter `Class[]`; create receiver |
| Act | Prepare the exact `Object[]` containing the argument list |
| Assert | Return value, direct exception, or `InvocationTargetException.getCause()` |
| Isolation | Separate tests do not share arbitrary state |
| Portability | Do not couple tests to JDK messages/stack traces that may change |

If a method has side effects, check state before and after the call. When running in a module environment, distinguish access permission errors from argument errors.

## 9. Minimum Test Matrix for a Reflection Invoker

| Scenario | Input | Expectation |
| --- | --- | --- |
| Single null for String | `(Object) null` | Valid if body handles it |
| No arguments | `(Object[]) null` for a method needing one parameter | `IllegalArgumentException` |
| Null instance receiver | null receiver | `NullPointerException` |
| Null static receiver | null receiver for static method | Valid |
| Primitive null | `int` receives null | `IllegalArgumentException` |
| Primitive widening | `int` receives `Short` | Valid |
| Primitive narrowing | `int` receives `Long` | `IllegalArgumentException` |
| Wrong type | `int` receives `String` | `IllegalArgumentException` |
| Wrong count | `String` receives two/zero arguments | `IllegalArgumentException` |
| Wrong receiver | instance method invoked on object of another type | `IllegalArgumentException` |
| Loose varargs | `String[]` receives two Strings | `IllegalArgumentException` |
| Packed varargs | `String[]` receives exactly one `String[]` | Valid |
| Wrong array | `String[]` receives `int[]` | `IllegalArgumentException` |
| Empty array | `String[]` receives `String[0]` as one Object | Valid |
| Null array | `String[]` receives one null | Body receives null |
| Method body error | target throws `IllegalStateException` | `InvocationTargetException` containing cause |
| Void-returning method | no return value | `invoke` returns null |
| Wrong signature lookup | looking up `int` method with `Integer.class` | `NoSuchMethodException` before invoke |

Do not call **getMethod** with an uncertain signature and then try calling it with a bunch of random types. Identify the exact overload needed first, then verify argument types and counts.

## 10. Exercises

1. **Primitive varargs:** add **sum(int... values)**. Compare **(Object) new int[]{1,2}** against passing two loose `Integer` values to `invoke`.
2. **Two-dimensional array:** add **rows(String[][] data)**; test passing **(Object) new String[][]{...}** versus accidentally treating the 2D array as an `Object[]` argument list.
3. **Overload:** add **handle(String)** and **handle(Integer)**, confirming `getMethod` requires the exact `Class` type. Reflection does not dynamically select a different overload during `invoke`.
4. **Cause:** make the method body throw **IllegalArgumentException("from target")**. Compare the `InvocationTargetException` wrapper against an `IllegalArgumentException` caused by invalid input.
5. **Void return:** add a `void` method that updates state, then verify the value from `invoke` is `null` and the side effect is correct.
6. **Empty/null array:** distinguish **new String[0]** and **(Object) null** for formal `String[]`; explain why the target may react differently.
7. **Test helper:** write a helper that prepares `Object[]` from user data according to `Method`'s `Class[]`, checking primitive nulls, counts, and array types before calling Reflection.

## 11. Self-Check Questions

**Question 1.** Why does **(Object) null** differ from **(Object[]) null**?  
**Answer:** One is a single null argument; the other is a null argument array, treated as zero arguments.

**Question 2.** How many parameters does method **join(String...)** have at runtime?  
**Answer:** One parameter of type `String[]`.

**Question 3.** Why is **join.invoke(target, "A","B")** wrong?  
**Answer:** Reflection sees two arguments while the target method expects one `String[]`.

**Question 4.** Does a method taking `int` accept `Short`?  
**Answer:** Yes, via unboxing and primitive widening to `int`.

**Question 5.** Does a method taking `int` accept `null`?  
**Answer:** No, `IllegalArgumentException`.

**Question 6.** If the target throws `IllegalStateException`, what does the `Method.invoke` caller catch?  
**Answer:** `InvocationTargetException`, with cause `IllegalStateException`.

**Question 7.** Is a null receiver valid for an instance method?  
**Answer:** No; it usually throws `NullPointerException`. For a static method, a null receiver is valid.

**Completion criteria:** accurately predict all example stdout lines, explain the two varargs layers, distinguish null receiver/argument, and write tests asserting the right exception/cause.

## 12. Official References

- [Javadoc Java SE 21 — Method.invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Javadoc Java SE 21 — InvocationTargetException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java Language Specification §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12)
- [Javadoc Java SE 21 — Executable.isVarArgs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html#isVarArgs())

**Final principle:** prepare the exact **`Object[]` argument list**, even when **an element in that list is itself an array**.