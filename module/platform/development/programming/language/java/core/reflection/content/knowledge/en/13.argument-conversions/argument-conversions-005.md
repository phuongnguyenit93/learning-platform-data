# Argument Count and IllegalArgumentException When Calling Java Reflection

When invoking a method or constructor via Reflection, the number and types of arguments must match **the exact selected signature**. In normal Java source code, the compiler can resolve overloads, pack varargs, and check multiple conversions. With `java.lang.reflect.Method.invoke(...)` and `Constructor.newInstance(...)`, however, you have already selected a specific executable before passing data. Reflection does not re-search overloads, does not automatically parse Strings into numbers, does not drop extra arguments, and does not supply missing arguments.

This lesson focuses on how to check **argument count**, causes of `IllegalArgumentException`, conversion rules for each formal parameter, and how to distinguish Reflection errors from errors thrown by the target method body.

## 1. The method lookup step differs from the invoke step

Example target method:

```java
class Calculator {
    public long add(int left, long right) {
        return left + right;
    }
}
```

Lookup step:

```java
java.lang.reflect.Method method =
        Calculator.class.getMethod("add", int.class, long.class);
```

Execution step:

```java
Calculator calculator = new Calculator();
Object value = method.invoke(calculator, 2, 5L); // Long(7)
```

The snippets above are illustrative code put together; `NoSuchMethodException`, `IllegalAccessException`, and `InvocationTargetException` must be handled at the calling method. The two formal parameter types are `int` and `long`, so the method takes **exactly two arguments** after the receiver. `Method.invoke` has the signature:

```java
Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
```

Where:

- `obj` is the **receiver** for an instance method; it **does not count toward** the method's formal parameter count. For a static method, `null` may be passed as the receiver.
- `args` is an array of actual arguments; each element corresponds to a formal parameter in order. The return type is `Object`; primitive values are boxed, and a `void` method yields `null`.
- `Method.getParameterCount()` returns the number of formal parameters, while `Method.getParameterTypes()` returns their types in order. For `add(int,long)`, these two values are `2` and the array `[int.class,long.class]` respectively.

If the signature is not found during `getMethod(...)`, the exception is `NoSuchMethodException`. Once the method is found, passing invalid arguments to `invoke(...)` typically raises `IllegalArgumentException`. The two errors belong to two different steps.

## 2. Wrong count: missing one, one extra, or confusing the receiver

For `add(int,long)`:

| Call | Result | Reason |
| --- | --- | --- |
| `method.invoke(calculator, 2, 5L)` | Valid, returns `Long(7)` | Two slots with matching types |
| `method.invoke(calculator, 2)` | `IllegalArgumentException` | Missing one slot |
| `method.invoke(calculator, 2, 5L, 8L)` | `IllegalArgumentException` | One extra slot |
| `method.invoke(new Object(), 2, 5L)` | `IllegalArgumentException` | Receiver incompatible with declaring class |
| `method.invoke(null, 2, 5L)` | `NullPointerException` | Null receiver for an instance method |
| `method.invoke(calculator, 2, "5")` | `IllegalArgumentException` | String is not automatically parsed into `long` |

All calls above are illustrative code assuming `method` and `calculator` are already declared. **Receiver count + argument count is not the formal parameter count**: `getParameterCount()` of `add` is still 2, even though `Method.invoke` shows an additional receiver in the first position.

A target method with no parameters requires `method.invoke(receiver)` or providing an empty actual args array. Meanwhile, `method.invoke(receiver, (Object) null)` **passes one slot containing null**, not zero slots.

## 3. Runnable Java 17+ example with exact output

Save the entire program below as `ReflectionArgumentDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionArgumentDemo {
    public static class Calculator {
        public long add(int left, long right) {
            return left + right;
        }

        public String join(String prefix, String... items) {
            return prefix + ":" + String.join(",", items);
        }

        public int fail(int value) {
            throw new IllegalArgumentException("business rule");
        }
    }

    private static void attempt(
            String label, Method method, Object receiver, Object... args) {
        try {
            Object result = method.invoke(receiver, args);
            System.out.println(label + " -> " + result);
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> IllegalArgumentException");
        } catch (IllegalAccessException ex) {
            System.out.println(label + " -> IllegalAccessException");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> target "
                    + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Calculator calculator = new Calculator();

        Method add = Calculator.class.getMethod(
                "add", int.class, long.class);

        System.out.println("parameter count: " + add.getParameterCount());
        attempt("correct", add, calculator, 2, 5L);
        attempt("missing", add, calculator, 2);
        attempt("extra", add, calculator, 2, 5L, 8L);
        attempt("string", add, calculator, 2, "5");
        attempt("null primitive", add, calculator, null, 5L);
        attempt("narrowing", add, calculator, 2L, 5L);
        attempt("widening", add, calculator, (byte) 2, 5);
        attempt("wrong receiver", add, new Object(), 2, 5L);

        Method join = Calculator.class.getMethod(
                "join", String.class, String[].class);
        System.out.println("join varargs: " + join.isVarArgs());
        attempt("packed", join, calculator, "tag",
                (Object) new String[] {"A", "B"});
        attempt("spread", join, calculator, "tag", "A", "B");

        Method fail = Calculator.class.getMethod("fail", int.class);
        attempt("target throws", fail, calculator, 4);
    }
}
```

Run:

```bash
javac ReflectionArgumentDemo.java
java ReflectionArgumentDemo
```

Stdout:

```text
parameter count: 2
correct -> 7
missing -> IllegalArgumentException
extra -> IllegalArgumentException
string -> IllegalArgumentException
null primitive -> IllegalArgumentException
narrowing -> IllegalArgumentException
widening -> 7
wrong receiver -> IllegalArgumentException
join varargs: true
packed -> tag:A,B
spread -> IllegalArgumentException
target throws -> target IllegalArgumentException
```

Result explanation:

1. `correct`: Integer unboxes to int, Long unboxes to long; the method returns primitive long and Reflection boxes the result into `Long`.
2. `missing`, `extra`: wrong number of formal parameters, so Reflection does not invoke the method.
3. `string`: Reflection does not run `Long.parseLong("5")`.
4. `null primitive`: cannot unbox null to primitive int.
5. `narrowing`: passing `Long` into an `int` slot requires unsupported narrowing.
6. `widening`: Byte unboxes then widens to int; Integer unboxes then widens to long; returns 7.
7. `wrong receiver`: `new Object()` is not an instance of `Calculator`.
8. `packed`: the last slot contains a `String[]` matching the formal parameter type of the varargs method.
9. `spread`: supplies three slots for a method that actually has two formal parameters; Reflection does not pack them automatically.
10. `target throws`: the `fail` method body **was invoked** and threw `IllegalArgumentException` itself, which `Method.invoke` wrapped in `InvocationTargetException`. Hence the helper prints the `target` prefix to distinguish it.

## 4. Constructor.newInstance has similar rules

For a constructor selected via `Class.getConstructor(...)` or `getDeclaredConstructor(...)`, calling `Constructor.newInstance(Object... initargs)` requires the exact count and types matching the constructor's formal parameters.

Illustrative example:

```java
public static class Ticket {
    private final int number;

    public Ticket(int number) {
        this.number = number;
    }

    @Override
    public String toString() {
        return "Ticket(" + number + ")";
    }
}
```

This static nested class must be placed inside an outer class when compiling. Calling:

```java
java.lang.reflect.Constructor<Ticket> ctor =
        Ticket.class.getConstructor(int.class);

Ticket ticket = ctor.newInstance(7);
System.out.println(ticket); // Ticket(7)
```

`ctor.newInstance()` is missing an argument; `ctor.newInstance("7")` has the wrong type; `ctor.newInstance(7L)` requires narrowing long to int. All of those cases result in `IllegalArgumentException` directly from Reflection.

If code inside the constructor **itself throws an exception**, `Constructor.newInstance` wraps the original exception in `InvocationTargetException`. If the class is abstract, instantiating via a constructor can cause `InstantiationException`; if access to the constructor is not permitted, `IllegalAccessException` can occur.

A notable case is **non-static inner classes**: a constructor may require a hidden parameter representing the enclosing instance. Therefore, general-purpose tools should not count parameters merely by eyeballing source code; use `Constructor.getParameterCount()` and `getParameterTypes()` on the actual executable.

## 5. Distinguishing exceptions during discovery, preparation, and invocation

| Exception | Typical source | How to handle |
| --- | --- | --- |
| `NoSuchMethodException` | Lookup by name/signature failed before invoke | Check method name, `Class<?>`, visibility, and formal parameter types |
| Direct `IllegalArgumentException` | Wrong slot count, type, unboxing/widening, or wrong receiver kind | Compare actual args with executable metadata |
| `NullPointerException` | Null receiver for instance method or another bug in caller code | Check receiver; do not confuse with errors from method body |
| `IllegalAccessException` | Member lacks valid access permission | Check accessibility and JPMS |
| `InaccessibleObjectException` | Attempted to enable deep reflection via `setAccessible(true)` but module is not open | Use public API or declare valid `opens` for owned code |
| `InvocationTargetException` | Method/constructor **executed** and threw an exception | Inspect `getCause()` |
| `ExceptionInInitializerError` | Class initialization failed during invocation | Check static initializer and cause |
| `ClassCastException` | Caller code cast the returned `Object` to the wrong type | Check return type and cast |

Emphasizing a critical distinction:

```java
// Passing invalid parameter: Reflection directly throws IllegalArgumentException.
method.invoke(receiver, "not-an-int");

// Valid parameter but target method code itself throws IllegalArgumentException:
// Method.invoke will throw InvocationTargetException containing that cause.
```

This is illustrative code, assuming `method` requires one int parameter. If you only catch `IllegalArgumentException` directly from `invoke`, you do not automatically catch an `IllegalArgumentException` thrown by the target method. To record business errors, catch `InvocationTargetException` and inspect `getCause()`.

With `Method.invoke`, basic handling code:

```java
try {
    Object result = method.invoke(receiver, actualArgs);
} catch (IllegalArgumentException ex) {
    // Error in receiver or actual arguments list.
} catch (IllegalAccessException ex) {
    // Reflection access permission error.
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable targetFailure = ex.getCause();
    // Error occurred inside the invoked method.
}
```

This is an illustrative snippet, depending on `method`, `receiver`, and `actualArgs` supplied by the application. Production code should preserve stack trace/cause rather than merely printing the exception name.

## 6. Pre-checking before invoke without recklessly replicating the compiler

Arity can be checked early:

```java
int formalCount = method.getParameterCount();
Class<?>[] formalTypes = method.getParameterTypes();
boolean varargs = method.isVarArgs();

Object[] actualArgs = {2, 5L};
if (actualArgs.length != formalCount) {
    throw new IllegalArgumentException(
            "Expected " + formalCount + " args, got " + actualArgs.length);
}
```

This is an illustrative snippet using method `add`. In practice, you must handle `actualArgs` possibly being null, check each position, and verify receiver compatibility. When the formal type is a reference, you can evaluate `expectedType.isInstance(value)`; when the formal type is a primitive, `Class.isInstance(wrapper)` does not substitute for unboxing/widening rules, so a mapping is needed if validating proactively.

Pre-checking is important but does not completely replace `invoke`: a receiver can be null, access can be denied, or the target method can throw an exception. An adapter receiving data from CLI/HTTP/JSON should parse and validate on its own first, then **select an explicit overload** matching the desired signature.

When crafting error messages for users, include the specific method name, expected/actual counts, parameter position, and expected type. Do not rely on the exact `IllegalArgumentException.getMessage()` of the JDK, as messages may differ across runtime versions.

## 7. Self-check questions

Suppose `Method m` represents `Calculator.add(int,long)` from section 3:

- `m.invoke(c, 1, 2L)`: **valid**, result `Long(3)`.
- `m.invoke(c, 1)`: **IllegalArgumentException**, because one argument is missing.
- `m.invoke(c, 1, 2L, 3L)`: **IllegalArgumentException**, because there is one extra argument.
- `m.invoke(c, 1, "2")`: **IllegalArgumentException**, because String is not automatically parsed to long.
- `m.invoke(c, (byte)1, 2)`: **valid** due to primitive widening.
- `m.invoke(c, 1L, 2L)`: **IllegalArgumentException**, because the first formal parameter requires int and long does not automatically narrow.
- `m.invoke(null, 1, 2L)`: **NullPointerException**, because the method is non-static and the receiver is null.
- `Calculator.fail(4)` throws `IllegalArgumentException` itself: Reflection wraps it in **InvocationTargetException**.
- How many formal parameters does `Calculator.join(String,String...)` require? **Two**: String and String[].
- To pass an array to a varargs target method via Reflection, what is the clear way? **`(Object) new String[] {"A","B"}`** in the final array slot.

**Takeaway:** identify the exact executable, count **formal parameters** accurately, verify the **receiver**, check compatibility of each argument, and pack varargs arrays yourself. When errors occur, distinguish a direct `IllegalArgumentException` where Reflection detects invalid arguments from an `InvocationTargetException` wrapping a failure from the target method/constructor.

### Official references

- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [JLS 17 — Method Invocation Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3)