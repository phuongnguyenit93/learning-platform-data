# Do not confuse a `Method` object with a method invocation result in Java Reflection

## 1. Two different objects, two different roles

In Java Reflection, `java.lang.reflect.Method` is **an object describing a method**: its name, declared return type, parameter type list, modifiers, annotations, declaring class, and related attributes. You can obtain a `Method` from `Class.getMethod(...)` or `Class.getDeclaredMethod(...)` without **ever executing the method body**.

When you want to actually execute the method that `Method` describes, call:

~~~java
Object result = method.invoke(receiver, arguments);
~~~

`Method.invoke(...)` uses the `Method` object to perform the call, and then returns **the value returned by the target method** as an `Object`. If the target method returns `void`, the value returned by `invoke` is `null`. If the target method returns a primitive such as `int`, Reflection boxes the value into a wrapper such as `Integer`. If the target method itself returns `null`, `invoke` also returns `null`.

Distinguish:

| Expression / variable | What does it represent? | Has the target method executed yet? |
| --- | --- | --- |
| `Method method = type.getMethod("run");` | Metadata for method `run()` | No. |
| `method.getName()` | Method name as a `String` | No. |
| `method.getReturnType()` | `Class<?>` object for the declared return type | No. |
| `Object value = method.invoke(target);` | Return value from one run of `run()` | Yes. |
| `Method another = method;` | Reference to the same method-describing object | Not run any additional time. |

**Key point:** `method` is **the tool object used to invoke**; `value` is **the result of one invocation**. The two values can only share the `Method` type in the special case where **the target method itself has return type `Method`**. There is no general rule that `invoke()` returns another `Method`.

## 2. Standalone runnable Java 17+ example

Create the file `MethodObjectDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class MethodObjectDemo {
    public static class Counter {
        private int value;

        public Counter(int initial) {
            this.value = initial;
        }

        public int add(int delta) {
            value += delta;
            return value;
        }

        public int current() {
            return value;
        }

        public void reset() {
            value = 0;
        }

        public static String label() {
            return "counter";
        }

        public int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter(10);
        Method add = Counter.class.getMethod("add", int.class);

        System.out.println("method name: " + add.getName());
        System.out.println("return type: " + add.getReturnType().getSimpleName());
        System.out.println("after lookup: " + counter.current());

        Object firstResult = add.invoke(counter, 5);
        System.out.println("result: " + firstResult);
        System.out.println("result type: " + firstResult.getClass().getSimpleName());
        System.out.println("counter value: " + counter.current());

        Method reset = Counter.class.getMethod("reset");
        Object voidResult = reset.invoke(counter);
        System.out.println("void result is null: " + (voidResult == null));
        System.out.println("after reset: " + counter.current());

        Method label = Counter.class.getMethod("label");
        System.out.println("static result: " + label.invoke(null));

        Method fail = Counter.class.getMethod("fail");
        try {
            fail.invoke(counter);
        } catch (InvocationTargetException ex) {
            System.out.println("cause: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 MethodObjectDemo.java
java MethodObjectDemo
~~~

Stdout verified when compiled targeting Java 17 and run on JDK 24:

~~~text
method name: add
return type: int
after lookup: 10
result: 15
result type: Integer
counter value: 15
void result is null: true
after reset: 0
static result: counter
cause: IllegalStateException
~~~

Explanation of milestones:

1. `Counter.class.getMethod("add", int.class)` **only looks up the Method** for name `add` and a single primitive `int` parameter. It does not add any number; `counter.current()` remains `10`. `int.class` in the query is the parameter type, not input data.
2. `add.getName()` and `add.getReturnType()` read **metadata**. Since the source method declares `int add(int)`, `getReturnType()` is `int.class`. They do not execute `add`.
3. `add.invoke(counter, 5)` **executes** `counter.add(5)`. Variable `firstResult` receives value `15` boxed as `Integer`, though the compile-time type of the variable remains `Object`. At the same time, state `counter.value` changes from `10` to `15`.
4. `reset.invoke(counter)` invokes `void reset()`. State is reset to `0`, while `voidResult` receives `null`. No "void object" is returned.
5. `label.invoke(null)` uses `null` as receiver because `label()` is `static`. The result of the call is `String "counter"`.
6. Method `fail()` throws `IllegalStateException`; `Method.invoke()` wraps exceptions arising from **the target method body** in `InvocationTargetException`. Call `getCause()` to retrieve the actual exception.

## 3. Three moments to identify during Reflection

You can visualize the flow:

~~~text
Class<?> type = Counter.class
          |
          | getMethod("add", int.class)  [metadata lookup]
          v
Method add                        [add() not called yet]
          |
          | getName()/getReturnType()  [read metadata]
          |
          | invoke(counter, 5)       [execute add(5)]
          v
Object firstResult                 [Integer(15), invocation result]
          |
          | cast/convert per contract
          v
int value = (Integer) firstResult  [int value 15]
~~~

This flow does not turn `Method` into `Integer`: variable `add` still represents **the same method metadata** before and after `invoke()`; it merely produces the value object `firstResult` and any side effects from the source method.

One `Method` can be used to invoke **multiple times**, on **multiple compatible instances**:

~~~java
Method method = Counter.class.getMethod("add", int.class);

Counter a = new Counter(1);
Counter b = new Counter(100);

Object resultA = method.invoke(a, 2); // Integer(3)
Object resultB = method.invoke(b, 2); // Integer(102)
~~~

This is an additional snippet using the `Counter` class defined in section 2, **not a standalone Java file**. The two results differ because the receivers differ; `method` itself holds no `value` state of `a` or `b`.

## 4. Why does `invoke()` return `Object` and how to use the right type?

General signature:

~~~java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

- `obj` is the **receiver** of an instance method; it must be an object compatible with the class declaring the method. For `static` methods, the receiver is ignored, and `null` is typically passed.
- `args` are the **argument values when calling**, in the required order and count. Do not confuse `int.class` (lookup metadata) with `5` (execution argument).
- The declared type of `Method.invoke()` is `Object` because it can invoke methods with vastly different return types. The actual return value is boxed if primitive; for `void`, it is `null`.
- Casting must match the **runtime value and the target method's contract**. A method returning `String` needs casting to `String` to use `String` APIs; a method returning `int` is normally received via `Integer` on `invoke`.

The following additional example uses `Counter` and `add` from section 2:

~~~java
Object raw = add.invoke(counter, 7);
int number = (Integer) raw;
System.out.println(number);
~~~

Note that the final result depends on the current value of `counter` when this snippet runs. This is an illustrative snippet **with no fixed stdout** unless prior state is known; it is not a standalone file. Casting `(Integer)` is appropriate because `add` returns primitive `int`.

**Distinguishing declared type and result type:**

~~~java
Class<?> declaredReturnType = add.getReturnType(); // int.class
Object actualReturnValue = add.invoke(counter, 1); // boxed Integer, e.g. 1 invocation
Class<?> actualValueType = actualReturnValue.getClass(); // Integer.class
~~~

`declaredReturnType` has type `Class<?>` and describes the signature; `actualReturnValue` holds data from **one execution**. If a method declares returning `Number` yet at runtime returns `Integer`, `getReturnType()` remains `Number.class`. If the method returns `null`, you cannot call `getClass()` directly on the result.

## 5. From metadata to result: choosing the right operation

| Question | API / value to use |
| --- | --- |
| Which methods exist? | `Class.getMethod(name, parameterTypes...)` for public, including inherited; `getDeclaredMethod(...)` for direct declarations |
| What type does the method return per signature? | `method.getReturnType()` returns `Class<?>`; does not run the method body |
| Want to execute and get the result? | `Object result = method.invoke(receiver, args...)` |
| Why is `result == null`? | Check `getReturnType() == void.class` or whether a reference method actually returned `null` |

**Lookup vs. execution:** when looking up overloads, use exact formal parameter types such as `int.class`, `String[].class`; when calling, pass **values** such as `5`, `new String[]{...}`. `invoke` does not re-select overloads. Instance methods require a compatible receiver; static methods can use `null`. If the target accepts an array, pass it as **one** argument, e.g., `method.invoke(receiver, (Object) names)`.

**Result vs. metadata:** for `int add(int)`, `getReturnType()` remains `int.class` while `invoke` returns `Integer`. For `void reset()`, `invoke` returns `null` even though reset mutated state; reference-returning methods can also return `null`.

**Errors vs. results:** signature not found → `NoSuchMethodException`; not permitted to invoke → `IllegalAccessException`; invalid receiver/args → `IllegalArgumentException` or `NullPointerException`; method body throws error → `InvocationTargetException`, read `getCause()`. Do not use `result == null` to infer that the call failed.

## 6. Usage scenarios and common mistakes

**Scenario 1 — Inspecting metadata before invoking.** A framework uses `getDeclaredMethods()` and `getAnnotation(...)` to find handlers meeting criteria. The obtained `Method` objects are only descriptors. Handlers only run at the moment the framework calls `invoke(...)` (or an equivalent invocation mechanism).

**Scenario 2 — Obtaining data returned by a handler.** A method like `String buildName()` yields a `String` result from `invoke()`. The variable holding `Method` is not the generated name string. To process it as a string, capture the invocation result, check its type, or cast appropriately.

**Scenario 3 — Methods that mutate state or perform I/O.** You cannot decide a method has done its job merely by obtaining its `Method`. You must execute it, handle exceptions, and understand side effects. With `void`, Reflection returns `null`, yet side effects can still occur.

Mistakes to avoid:

1. **"`getMethod()` immediately calls the method."** False: that is only a metadata lookup.
2. **"The `Method` variable is the value the method returned."** False: only `invoke()` runs the method, and the return value must be stored separately if needed.
3. **"The result always has type `Method`."** False: the result depends on the target method's signature; the `invoke` API declares returning `Object`.
4. **"When a method returns a primitive, `result.getClass()` is `int.class`."** False: if the value is non-null, Reflection boxes `int` to `Integer`.
5. **"`result == null` means the call did not run."** False: both `void` methods and reference-returning methods returning `null` produce `null`.
6. **"`getReturnType()` alone tells you the actual return value."** False: that is the **declared type**. The method has not run and there is no result yet.
7. **"Exceptions from the target method are always thrown straight out of `invoke()`."** False: they are usually wrapped in `InvocationTargetException`; inspect `getCause()`.
8. **"Once you have a `Method`, you can definitely call it."** False: callers must still satisfy visibility, JPMS, receiver, and argument rules.
9. **"Calling the same `Method` always yields the same result."** False: results depend on receiver, inputs, state, and side effects at invocation time.

## 7. Self-check for comprehension

1. Does `Method m = Counter.class.getMethod("add", int.class);` change `Counter`'s state? Why or why not?
2. Given `Counter c = new Counter(7);`, what runtime type and value does `m.invoke(c, 3)` return? If you call `m.invoke(c, 3)` again, is the result still the same as the first time?
3. Why does `reset.invoke(c) == null` not prove `reset()` failed?
4. Why is `m.getReturnType() == int.class` while `m.invoke(c, 1).getClass() == Integer.class`?
5. If the target method throws `IllegalStateException`, where on `InvocationTargetException` should you look to get the original exception?
6. When Reflection invokes a no-argument `static` method, what value can be passed as the receiver?

**Takeaway:** `Method` is **an object representing a method**; `Method.invoke(...)` is **the action of calling that method**; the result of `invoke(...)` is **the return value of the call**, not the `Method` itself.

## Standard documentation

- [Java SE 17 — `java.lang.reflect.Method`, especially `invoke(...)`, `getReturnType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `java.lang.Class`, `getMethod(...)` and `getDeclaredMethod(...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)