# Java Is Always Pass-by-Value: The Argument Value Copy Model

In Java, **every method and constructor call passes arguments by value**. That holds true for `int`, `double`, and `boolean` as well as objects such as `Student`, `List`, and arrays. The difference lies in **which value is copied**: for primitive types, it is the numeric/logical value itself; for reference types, it is the **reference value pointing to the object**, not a copy of the entire object.

This rule explains three seemingly contradictory phenomena:

- Modifying an `int` parameter **does not** change the caller's `int` variable.
- Reassigning a `Student` parameter so that it points to a new object **does not** change the caller's `Student` variable.
- Calling `student.setName(...)` through the parameter can **modify the object** that the caller is still referencing.

This article presents the argument value copy mechanism, runnable Java 17+ examples, the effects of aliases, arrays, `String`, wrappers, `final`, varargs, ways of returning results, and common mistakes.

## 1. Separating Four Concepts: Variable, Value, Reference, Object

First, distinguish:

| Concept | Example | Meaning |
| --- | --- | --- |
| Variable | `int n`, `Box box` | A typed location used to hold a value |
| Primitive value | `7`, `true` | A value of a primitive type |
| Reference value | The value currently held in `Box box` | A reference to an object, or `null` |
| Object | The result of `new Box(10)` | An entity with its own instance state |

Example:

~~~java
int n = 7;
Box first = new Box(10);
Box alias = first;
~~~

This is an illustrative snippet assuming a `Box` class exists. The variable `n` holds the integer value `7`. The variable `first` holds **a reference value** pointing to the created object. The assignment `alias = first` copies the reference; it **does not create a new Box**.

When calling `f(n)` or `g(first)`, Java evaluates the argument expression and passes **the resulting value** into a new parameter variable in the call. **There is no rule for directly passing "the caller's variable" so that the callee can reassign it.**

An accurate way to state it: *Java is pass-by-value, including reference values*. It is not "primitives are pass-by-value while objects are pass-by-reference" in the sense of passing the caller's variable by reference.

## 2. The Value Copy Model When Calling a Method

Consider a method:

~~~java
static void examine(int number, Box item) {
    // number and item are the parameter variables of the current call.
}
~~~

And the call:

~~~java
int score = 7;
Box current = new Box(10);
examine(score, current);
~~~

These are illustrative snippets, not standalone programs yet. Conceptual model:

~~~text
CALLER                        CALLEE
-----------------------       -------------------------
score  [int value: 7] ------> number  [int copy: 7]

current [reference R] ------> item    [copy of reference R]
                  |                             |
                  +------------+----------------+
                               |
                               v
                         A Box object
                         [value = 10]
~~~

**What is copied** is the value currently stored in the variable or the result of the expression. The two reference variables `current` and `item` are **two different variables**, yet they can hold **the same reference value R**, meaning they both point to **one object**.

Therefore, we must separate two operations:

1. **Reassigning the parameter variable:** `item = new Box(20)` only changes the reference value stored in the callee's **`item` variable**.
2. **Modifying the object through the reference:** `item.add(5)` accesses the object that `item` points to and modifies the field inside that object; the caller can see the change while still holding a reference to the same object.

This model is **Java semantics**; it makes no claim about how a specific JVM lays out variables/references in registers or physical memory.

## 3. For Primitive Types: The Parameter Is a Separate Variable

Create the complete file **`PrimitiveValueDemo.java`**:

~~~java
public class PrimitiveValueDemo {
    static void change(int number) {
        System.out.println("inside before=" + number);
        number = 99;
        System.out.println("inside after=" + number);
    }

    static void flip(boolean enabled) {
        enabled = !enabled;
        System.out.println("inside flag=" + enabled);
    }

    public static void main(String[] args) {
        int score = 7;
        boolean active = true;

        change(score);
        System.out.println("outside number=" + score);

        flip(active);
        System.out.println("outside flag=" + active);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PrimitiveValueDemo.java
java PrimitiveValueDemo
~~~

**Exact stdout:**

~~~text
inside before=7
inside after=99
outside number=7
inside flag=false
outside flag=true
~~~

`change(score)` passes the value `7` to the parameter variable `number`. Inside the method, `number = 99` only modifies the **parameter**; it does not modify `score`.

Similarly, `flip(active)` receives a copy of `true`, changes the parameter to `false`, and prints the new value. The caller's `active` variable remains `true`.

This does not mean "Java prevents every method from modifying external data": a method can still update fields of a passed-in object, `static` fields, files, or a database. The example only proves that **reassigning a primitive parameter does not change the caller's argument variable**.

## 4. For Reference Types: Copying the Reference, Not the Object

Create the standalone file **`ReferenceValueDemo.java`**:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        value = Math.addExact(value, amount);
    }

    int value() {
        return value;
    }
}

public class ReferenceValueDemo {
    static void mutate(Counter counter) {
        counter.add(5);
        System.out.println("inside mutate=" + counter.value());
    }

    static void replace(Counter counter) {
        counter = new Counter(100);
        counter.add(1);
        System.out.println("inside replace=" + counter.value());
    }

    static void clear(Counter counter) {
        counter = null;
        System.out.println("inside clear=" + counter);
    }

    public static void main(String[] args) {
        Counter original = new Counter(10);
        Counter alias = original;

        System.out.println("before=" + original.value());

        mutate(original);
        System.out.println("after mutate=" + original.value());

        replace(original);
        System.out.println("after replace=" + original.value());

        clear(original);
        System.out.println("caller nonnull=" + (original != null));
        System.out.println("same instance=" + (original == alias));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReferenceValueDemo.java
java ReferenceValueDemo
~~~

**Stdout:**

~~~text
before=10
inside mutate=15
after mutate=15
inside replace=101
after replace=15
inside clear=null
caller nonnull=true
same instance=true
~~~

The three methods do very different things:

### `mutate(original)`: Modifying the Shared Object

When `mutate` starts, the parameter `counter` is a new variable, yet it holds **a reference to the same Counter** that `original` points to. `counter.add(5)` modifies that object's `value` field from 10 to 15. Therefore, after returning to `main`, `original.value()` is 15.

This is a **side effect on the referenced object**, not passing the `original` variable by reference.

### `replace(original)`: Changing Only the Parameter's Reference

In `replace`:

~~~java
counter = new Counter(100);
counter.add(1);
~~~

This is an excerpt from the method above. The first line creates a new object and assigns **the parameter variable `counter`** to it. The new object increases to 101, while `main`'s `original` variable still points to **the old object** with value 15. Thus, the two output lines are `inside replace=101` and `after replace=15`, respectively.

### `clear(original)`: Assigning null to the Parameter; the Caller Still Keeps the Object

`counter = null;` only changes the call's local parameter; `original` is not automatically set to null. `original == alias` remains `true` because the two variables in `main` still hold the original reference.

**Conclusion:** A callee can **change the state of a shared object**, but it cannot **reassign the caller's reference variable itself** through ordinary parameter reassignment.

## 5. Before–After Diagram: Mutate vs. Reassign

Before the call:

~~~text
main()
  original ------+
                 +----> Counter #1, value = 10
  alias ---------+

mutate(counter)
  counter ------------> Counter #1, value = 10
                           |
                           +-- add(5) --> value = 15
~~~

After `mutate`, both `original` and `alias` see `Counter #1` with `value = 15`.

In `replace(counter)`:

~~~text
main()                              replace()
  original -----+                   counter -----+
                |                                 |
  alias --------+----> Counter #1, value = 15      |
                                                   |
                             counter = new Counter(100)
                                                   |
                                  counter --------+----> Counter #2
                                                         value = 100
                                  counter.add(1)        value = 101
~~~

When `replace` finishes, the parameter variable is no longer used in the caller; `original` and `alias` still point to `Counter #1`. Object #2 in the example can become a candidate for garbage collection if no other live references hold it; **there is no guarantee that the JVM will reclaim it immediately**.

Remember the rules:

- **Copying a reference** does not create a copy of the object.
- **Reassigning a reference variable** does not by itself change other variables.
- **Modifying a field through one reference** can be seen through aliases pointing to that same object.

## 6. Why Is "Objects Are Passed by Reference" a Misleading Phrasing?

Learners sometimes say "Java passes objects by reference" because they observe that the caller sees changes from `counter.add(5)`. This phrasing easily leads to the false conclusion that `counter = new Counter(...)` inside the callee also changes the caller's `original` variable.

In parameter-passing terminology:

- **Pass by value**: the callee receives a **value** in its parameter variable.
- **Pass by reference** in the sense that the caller's variable is passed as an assignable alias: the callee can change **the caller's variable itself** by assigning through the parameter.
- **Java uses pass by value**. For objects, the value passed is a **reference value**, not a copied object.

A simple counterexample:

~~~java
static void reset(Counter c) {
    c = null;
}
~~~

If this were passing the caller's variable by reference, assigning `c = null` would turn the caller's variable into `null`; however, Java **does not** behave that way. Therefore, saying **"a copy of the reference value"** is more accurate.

Some languages use the term "call by sharing" to describe the effect of both sides sharing an object. That term may help intuition, but it **does not change Java's pass-by-value argument-passing mechanism**.

## 7. Arrays Are Objects Too: Elements Can Be Modified, Caller Variables Cannot Be Reassigned

Arrays in Java are **objects**. When passing an `int[]`, the parameter receives a copy of **the reference to the array** rather than copying every element.

Create the file **`ArrayValueDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayValueDemo {
    static void editFirst(int[] items) {
        items[0] = 42;
    }

    static void replaceArray(int[] items) {
        items = new int[] {9, 9, 9};
        System.out.println("inside replacement=" + Arrays.toString(items));
    }

    static void appendText(String text) {
        text = text + "!";
        System.out.println("inside text=" + text);
    }

    static void appendBuilder(StringBuilder builder) {
        builder.append("!");
    }

    public static void main(String[] args) {
        int[] values = {1, 2};
        editFirst(values);
        System.out.println("after edit=" + Arrays.toString(values));

        replaceArray(values);
        System.out.println("after replacement=" + Arrays.toString(values));

        String message = "Java";
        appendText(message);
        System.out.println("outside text=" + message);

        StringBuilder builder = new StringBuilder("Java");
        appendBuilder(builder);
        System.out.println("outside builder=" + builder);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ArrayValueDemo.java
java ArrayValueDemo
~~~

**Stdout:**

~~~text
after edit=[42, 2]
inside replacement=[9, 9, 9]
after replacement=[42, 2]
inside text=Java!
outside text=Java
outside builder=Java!
~~~

Explanation:

1. `editFirst(values)` receives a copy of the reference to **the same array** and assigns `items[0] = 42`. The caller sees `[42, 2]`.
2. `replaceArray(values)` creates a new array and assigns it to **the `items` variable inside**. The caller's `values` array is not replaced.
3. `String` is **immutable**. `text = text + "!"` creates/obtains a new string value to reassign to the parameter variable; it does not modify the content of the `String` object that `message` points to.
4. `StringBuilder` is **mutable**. `builder.append("!")` modifies the very object that both caller and callee are referencing; the caller reads `Java!`.

**Do not say that Java "copies the entire array when passing parameters."** Copying an array must be a separate operation, such as `Arrays.copyOf`, `clone()` on the array, or an appropriate copying strategy.

## 8. The `String` Case: Pass-by-Value Without Exception

`String` often causes confusion because it is a reference type yet behaves like a "value" when concatenating strings:

~~~java
static void makeLoud(String message) {
    message = message.toUpperCase();
}
~~~

This is an illustrative method snippet. If the caller writes:

~~~java
String title = "java";
makeLoud(title);
System.out.println(title); // java
~~~

then `title` remains `"java"`. The `toUpperCase()` method returns an appropriate `String`, while reassigning `message` only changes **the parameter**. It is impossible to modify the contents of an existing `String` by changing its character fields through the standard API, because `String` is immutable.

If you want the caller to receive the result, **return the value**:

~~~java
static String makeLoud(String message) {
    return message.toUpperCase();
}

// In the caller:
String title = "java";
title = makeLoud(title);
System.out.println(title); // JAVA
~~~

The two `makeLoud` declaration examples above are **two alternative versions for comparison** and must not be placed in the same class at the same time, because changing only the return type does not create a valid overload. The second snippet demonstrates the rule: **the caller explicitly reassigns its own variable with the returned result**.

This is not a "workaround" for pass-by-value; it is explicit communication between the method and the call site via `return`.

## 9. Wrappers and Autoboxing: Reassignment Still Happens Only in the Callee

Wrappers such as `Integer`, `Long`, and `Boolean` are **reference types**, and the instances representing their values are **immutable** through the API. Consider:

~~~java
static void increase(Integer value) {
    value++;
}
~~~

This is an illustrative snippet. If we have:

~~~java
Integer count = Integer.valueOf(10);
increase(count);
System.out.println(count); // 10
~~~

`value++` involves **unboxing**, incrementing the value, and **boxing** the result, then reassigning the parameter variable `value`; it does not modify the original wrapper object and does not reassign the caller's `count` variable.

In practice, avoid using a wrapper simply expecting it to act as an "output parameter." An `Integer` wrapper can also be `null`, and unboxing a null value causes a `NullPointerException`.

Note that `Integer x = 5;`, when passed to an `int` parameter, can be unboxed during argument compatibility; the parameter receives **the primitive value** after conversion. Boxing/unboxing conversions do not turn the caller's variable into a reassignable alias.

## 10. Why Doesn't Writing `swap(a,b)` Swap Two Reference Variables in the Caller?

A short test of the pass-by-value rule:

~~~java
static void swap(Object left, Object right) {
    Object temporary = left;
    left = right;
    right = temporary;
}
~~~

If the caller has two variables `a` and `b` pointing to two different objects, calling `swap(a, b)` **does not swap the two caller variables**. The two parameters `left` and `right` are **copies of the two reference values**; the three assignments only swap the two local variables inside the callee.

Draw two columns: caller variables (`a`, `b`) and callee variables (`left`, `right`). After each assignment, the caller column stays unchanged. To modify two slots of a shared array/list, you can change **the container's elements**; to swap two local variables, the caller itself must reassign them from the result.

The dedicated article on swapping references in this chapter will trace line by line and compare array, list, holder, and result-record solutions. In this overview article, you only need to grasp the rule: **reassigning a parameter does not reassign the caller's variable**.

## 11. If You Want the Result to Change the Caller's Variable, What Should You Do?

When an API wants to send back a new value, it should usually **return** the result and let the call site decide the assignment:

~~~java
static int doubled(int value) {
    return Math.multiplyExact(value, 2);
}

// Caller:
int score = 7;
score = doubled(score); // score becomes 14
~~~

This is an illustrative snippet inside a class; `Math.multiplyExact` throws an `ArithmeticException` if the integer multiplication overflows.

For reference types:

~~~java
static String addSuffix(String source) {
    return source + "!";
}

// Caller:
String name = "An";
name = addSuffix(name); // the caller reassigns its own variable
~~~

If a method needs to return **multiple results**, consider creating an explicit result type such as a `record`:

~~~java
record DivisionResult(int quotient, int remainder) {
}

static DivisionResult divide(int a, int b) {
    return new DivisionResult(a / b, a % b);
}
~~~

Both declarations belong in an appropriate class context; `divide` assumes `b != 0`, and if it is 0, it will throw an `ArithmeticException`. Java 17 supports `record` as a concise way to represent multiple result values.

APIs may intentionally **modify a passed-in mutable object**, such as `List.add`, `Collections.sort`, or a `StringBuilder`. Document the side effect clearly in the contract, and do not use a mutable holder just to simulate pass-by-reference when a return value would be simpler.

## 12. Using an Object to Hold Results: Contents Can Be Modified, Caller Variable Cannot

If it is truly necessary for the callee to update a data-holding object, the caller can create a container:

~~~java
class IntHolder {
    int value;

    IntHolder(int value) {
        this.value = value;
    }
}

static void increment(IntHolder holder) {
    holder.value++;
}
~~~

These are illustrative declarations placed inside a valid Java structure. On the caller side:

~~~java
IntHolder holder = new IntHolder(10);
increment(holder);
System.out.println(holder.value); // 11
~~~

This works because the method modifies **the `value` field of the same object**. It **does not prove that Java has switched to pass-by-reference**: the `holder` parameter variable is still a reference copy, and if the callee assigns `holder = new IntHolder(0)`, the caller does not automatically point to the new object.

A specialized wrapper like `AtomicInteger` has its own value-update API and concurrency rules, yet it is not a Java "integer parameter passed by reference." Choose a container only when the API design genuinely needs its identity, shared state, or update mechanism.

## 13. Constructors Also Receive Copies of Argument Values

The pass-by-value rule applies when calling a **constructor**, not just a method:

~~~java
class Student {
    private final String name;
    private final int grade;

    Student(String name, int grade) {
        this.name = name;
        this.grade = grade;
    }
}
~~~

This is an illustrative class. With `new Student(title, level)`, the constructor parameters `name` and `grade` receive argument values via the same mechanism as methods. `this.name = name` and `this.grade = grade` are assignments **to the fields of the object being initialized**, not reassignments of the caller's `title` or `level` variables.

If a constructor stores a mutable reference directly:

~~~java
class Scores {
    private final int[] points;

    Scores(int[] points) {
        this.points = points;
    }
}
~~~

then the `this.points` field receives **a copy of the reference value** pointing to **the same array** that the caller passed in. The caller still holds the array and can modify its elements. `final` on the field only prevents **reassigning the field reference**; it does not create a copy of the array's contents.

If the class needs independent ownership of the data, consider defensive copying:

~~~java
Scores(int[] points) {
    this.points = java.util.Arrays.copyOf(points, points.length);
}
~~~

This is an **alternative constructor version** and cannot coexist with the `Scores(int[])` constructor above in the same class. It copies the `int` elements into a new array; for an array containing mutable objects, copying the elements is only a **shallow copy** unless each child object is also copied.

## 14. `final` on Parameters Does Not Change the Passing Mechanism

You can declare:

~~~java
static void show(final Counter counter) {
    System.out.println(counter.value());
    // counter = new Counter(10); // Compile error: cannot reassign a final parameter.
}
~~~

`final` **prevents reassigning the parameter variable itself**, yet you can still call `counter.add(1)` if the reference is non-null and the API allows it. It does not make the object immutable, nor does it switch parameter passing to pass-by-reference.

Example:

~~~java
static void increment(final Counter counter) {
    counter.add(1); // Valid: does not reassign the counter variable.
}
~~~

A `final` field, a `final` local variable, and a `final` parameter each have their corresponding no-reassignment rule; they do not automatically copy the referenced object.

**Design note:** Sometimes marking a parameter `final` helps catch accidental reassignment inside the method body. However, whether or not to use `final` is usually a coding convention, not a difference in parameter-passing semantics.

## 15. `null` Is Also a Reference Value Passed by Value

When you write:

~~~java
static void set(Counter counter) {
    counter = new Counter(5);
}

Counter ref = null;
set(ref);
System.out.println(ref == null); // true
~~~

This is an illustrative snippet in a context with a `Counter` class. The value of `ref` at the time of the call is `null`; the parameter `counter` receives **a copy of null**. The method creates an object and assigns it to the parameter variable; it does not reassign the caller's `ref`.

Conversely:

~~~java
static void use(Counter counter) {
    counter.add(1);
}
~~~

If the caller passes `null`, `counter.add(1)` throws a `NullPointerException` when attempting to call an instance method through a null reference. This is a matter of **preconditions and null handling**, not evidence of a different argument-passing mechanism.

To keep the API clear, you can use `Objects.requireNonNull(counter)` or another validation rule before accessing the object; it should be clearly established whether null is an invalid input or a valid state.

## 16. Varargs Also Work by Value: The Parameter Is an Array

Declaration:

~~~java
static int sum(int... numbers) {
    int result = 0;
    for (int number : numbers) {
        result = Math.addExact(result, number);
    }
    return result;
}
~~~

Inside, `numbers` is a parameter variable of type **`int[]`**, and its value is **a reference to the array**.

The caller can:

~~~java
sum();                 // No elements: 0.
sum(2, 3);             // Two elements: 5.
sum(new int[] {2, 3}); // Passing an existing array: 5.
~~~

When called with separate arguments `sum(2,3)`, Java handles the variable-arity call using an appropriate parameter array. When passing an existing array of a matching type `sum(array)`, the call can pass **the caller's array reference** directly into the parameter. In both cases, **the value passed to the parameter is a reference value** according to Java's rules.

A point to watch if the method modifies `numbers[0]`: with a caller-supplied array, the caller can observe the change; with separate arguments, the caller has no original array variable through which to observe it. However, assigning `numbers = new int[]{...}` inside the callee still **does not** change the caller's array variable.

Calling `sum()` creates an empty array parameter according to normal varargs semantics, **not** passing `null` by default. The caller can still intentionally pass `sum((int[]) null)`; if the method body iterates over `numbers` immediately, it will encounter a `NullPointerException`.

## 17. How Arguments Are Evaluated Before Passing Their Values

When calling a method, Java needs to **evaluate the argument expressions** to obtain their actual values. According to the language rules, argument expressions are evaluated **from left to right** in normal calls. If an argument expression produces a side effect, that side effect occurs **on the caller side during evaluation**, not because the callee was handed the caller's variable by reference.

Example standalone file **`ArgumentEvaluationDemo.java`**:

~~~java
public class ArgumentEvaluationDemo {
    static int next(int[] counter) {
        counter[0]++;
        System.out.println("evaluated=" + counter[0]);
        return counter[0];
    }

    static void receive(int first, int second) {
        first = 100;
        System.out.println("received=" + first + "," + second);
    }

    public static void main(String[] args) {
        int[] state = {0};
        receive(next(state), next(state));
        System.out.println("caller state=" + state[0]);
    }
}
~~~

Run:

~~~bash
javac ArgumentEvaluationDemo.java
java ArgumentEvaluationDemo
~~~

**Stdout:**

~~~text
evaluated=1
evaluated=2
received=100,2
caller state=2
~~~

Step by step:

1. Java evaluates the first `next(state)`, increments element `state[0]` to 1, prints `evaluated=1`, and yields the argument value `1`.
2. Next, it evaluates the second `next(state)`, increments `state[0]` to 2, prints `evaluated=2`, and yields `2`.
3. `receive` receives **two already-evaluated integer values**, `first=1` and `second=2`. Assigning `first=100` only changes the parameter.
4. On the caller side, `state[0]` is 2 because **the two calls to `next` modified the array** during argument evaluation.

This is an important detail: **"pass by value" does not mean argument evaluation cannot cause side effects**. It only describes how the evaluated value is transferred into the parameter.

Valid argument conversions such as primitive widening, boxing/unboxing, or varargs handling can occur according to call rules; they do not turn the call into passing the caller's variable by reference.

## 18. Generic Methods Do Not Change This Rule

Example:

~~~java
static <T> void reassign(T element, T replacement) {
    element = replacement;
}
~~~

This is an illustrative generic method. If `T` is `String`, `Student`, or `List<String>`, the assignment `element = replacement` only reassigns **the `element` parameter variable** within the call; it does not change the caller's variable.

If `T` represents a mutable object and the method calls a behavior that modifies that object (via an appropriate API), side effects can appear. Generics only generalize how **data types** are expressed; they do not introduce a pass-by-reference mechanism.

A lambda or method reference accepting parameters does not change the rule either: argument values are still passed to formal parameters according to Java semantics. If a lambda holds a reference to an external object, it can share that object; this is a matter of **aliasing and capture**, not passing variables through reassignable references.

## 19. Using Shared Objects Does Not Mean Thread-Safe

When both callee and caller hold references to a mutable object, both can operate on the object's state. In a multithreaded environment, **holding the same reference does not guarantee safe reads and writes**.

Example:

~~~java
class SharedCount {
    int value;

    void increment() {
        value++;
    }
}
~~~

This is an illustrative class snippet. If two threads both hold references to **a single `SharedCount`**, both can update the `value` field inside the same object. The `value++` operation is not an atomic read–modify–write sequence; increments can be lost or visibility issues can occur without synchronization.

Avoid confusing:

- **Copying a reference value:** two parameters/variables can point to the same object.
- **Sharing a mutable object:** changes can be observed by multiple reference holders.
- **Memory visibility/thread safety:** to guarantee observation/manipulation across threads, appropriate synchronization, atomics, or ownership is required.

**Do not infer from "Java is pass-by-value" that objects are copied for each thread**. Java does not do that in normal method calls.

## 20. When Should You Return a Result, and When Should You Modify an Object?

Both API styles are valid, but they serve different purposes:

| Goal | Generally Appropriate Design | Example |
| --- | --- | --- |
| Compute a new value from input data | Return the result without modifying the input | `int next = doubled(current)` |
| Create a new string | Return `String` | `name = normalize(name)` |
| Update a domain object's state | Instance method with clear preconditions | `account.deposit(amount)` |
| Modify elements of a passed-in array/list | State the side effect clearly in the name/Javadoc | `sortInPlace(items)` |
| Need multiple results | `record`/result object | `DivisionResult` |
| Need shared state with a clear lifecycle | Appropriate holder/domain object | `Counter` |
| Need independence from mutable input data | Copy appropriately before storing/using | `Arrays.copyOf`, copy constructor |

For an API that accepts a mutable object, clearly document whether the method is **read-only**, **may mutate it**, **retains the reference**, or **copies its contents**. The pass-by-value rule does not decide these choices on its own.

**Contract example:** `void sortInPlace(List<String> items)` makes clear that the method modifies the passed-in list; `List<String> sortedCopy(List<String> items)` suggests returning a new result without changing the order of the input list. You must test and document the behavior, rather than relying solely on the name.

## 21. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| "Primitives are pass-by-value, objects are pass-by-reference" | Easily implies the callee can reassign the caller's variable | **All arguments are passed by value**; for objects, it is the reference value |
| "Passing an object copies the whole object" | Only the reference is copied | Both sides can see the same object |
| "Assigning `param = new Object()` changes the caller's variable" | It only reassigns the parameter variable | The caller needs to receive and assign the returned result |
| "Calling `param.setX(...)` is pass-by-reference" | It is modifying a shared object | It is not reassigning the caller's variable |
| "Arrays copy themselves automatically when passed" | Arrays are objects, so a reference value is passed | Use `Arrays.copyOf` when you want a separate array |
| "String is an exception and is truly passed by reference" | String is immutable; the parameter variable is still independent | Return a new String if you need to change the caller's value |
| "`Integer++` changes the caller's Integer" | It unboxes/increments/boxes and reassigns the parameter | Wrappers are immutable; use return |
| "`final` means pass-by-reference" | It only prevents reassigning the parameter variable | It does not change how arguments are passed |
| "Swapping two object parameters swaps the two caller variables" | It only swaps two local callee variables | Return a result or modify a shared container |
| "There are no side effects with pass-by-value" | Shared objects/arrays can still be modified | Distinguish the parameter from the referenced object |
| "`null` is an object that gets copied" | `null` is a special reference value | A copy of null is passed; no object is created |
| "Pass-by-value guarantees thread safety" | The same mutable object can be shared | Separate concurrency design is required |

When a change does not show up on the caller side, ask: **Did the method reassign the parameter variable, or did it modify the state of the object that both point to?** When a change **does** appear, trace the aliases and check which parties hold references to the modified object.

## 22. Knowledge Self-Check

**Question 1 — Primitives.** Given `int x=3;`, calling `f(x)` where `f(int x)` assigns `x=100`, what is the value of `x` in the caller after the call?

**Question 2 — References.** `Box a=new Box(10);` is passed into `void update(Box p) { p.add(5); }`. After the call, does `a` still point to the same object? Does the object's value change?

**Question 3 — Reassignment.** With `void reset(Box p) { p=new Box(0); }`, what happens to the caller's variable `a`?

**Question 4 — Null.** If the caller has `Box a=null;` and `void init(Box x){x=new Box(1);}`, after `init(a)`, is `a` still null?

**Question 5 — Arrays.** Given `int[] nums={1,2};`, calling `change(nums)` where `change(int[] a)` executes `a[0]=9`, what is `nums[0]`? What if the body is replaced with `a=new int[]{9,9}`?

**Question 6 — String.** Given `String s="A";` and `void edit(String t){t+="B";}`, after `edit(s)`, what is `s`? How do you obtain `"AB"`?

**Question 7 — Swap.** Why does a method `swap(Object x,Object y)` that only assigns `x=y`, `y=temp` fail to swap variables in the caller? Is passing `Object[]` to a method that swaps two elements any different?

**Question 8 — Wrappers.** `Integer count=10;` calls `increase(count)` whose body is `value++`. Why is `count` still 10?

**Question 9 — final.** Can you call `counter.add(1)` through a `final Counter counter` parameter? Can you reassign `counter = new Counter(0)`?

**Question 10 — Argument Evaluation.** With `receive(next(state),next(state))` in the program above, why does `state[0]` in the caller increase by 2 even though both parameters of `receive` are primitives?

**Question 11 — Copying.** A constructor receives `List<String>` and stores `this.items = items`. Does it create a copy of the list? What should you do if you want to decouple the internal list from the caller?

**Question 12 — Concurrency.** Two threads hold two separate reference variables that point to the same `Counter`. Are there two copies of the object? Can they safely increment the field concurrently without synchronization?

### Answers and Explanations

1. Still 3: `f` only receives a copy of the primitive value.
2. `a` still points to the same object; `add(5)` modifies that object, so its value changes from 10 to 15.
3. `a` does not change its reference; only the parameter `p` points to the new object.
4. Still null; `init` cannot reassign the variable `a`.
5. With element assignment, `nums[0]=9`; with reassigning `a`, `nums[0]` remains 1.
6. Still `"A"`; the method needs to return a new String and the caller assigns `s=edit(s)`.
7. `x` and `y` are two separate parameter variables. Modifying elements of the same array object lets the caller see the changed array contents, whereas other reference variables in the caller do not change on their own.
8. `value++` produces a new value and assigns it to the parameter; the `Integer` wrapper is not modified in place.
9. Calling `add(1)` is allowed if non-null and permitted by the API; reassigning `counter` is rejected by the compiler because of `final`.
10. The two `next(state)` expressions modify the array object during **argument evaluation**; `receive` only receives the primitive values 1 and 2.
11. No. The field only receives a copy of the reference to the same list; you need an appropriate list copy, such as `new ArrayList<>(items)` or `List.copyOf(items)` depending on the contract, while also considering mutable elements.
12. There is only **one shared object**; concurrent updates require appropriate synchronization/atomic design.

## 23. Reference Documentation

- [Java Language Specification 17, §15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): argument evaluation and how values are passed into a call.
- [Java Language Specification 17, §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): left-to-right evaluation of argument expressions.
- [Java Language Specification 17, §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): formal parameters, varargs, and modifiers.
- [Java Language Specification 17, §4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): variables, values, and variable types.
- [Java Language Specification 17, §10 — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): arrays as objects and working with arrays.

**Remember:** Java **always uses pass-by-value**. For primitives, the callee receives a **numeric/logical copy**. For objects and arrays, the callee receives a **copy of the reference value**, so both sides can see and modify **a single object** yet **cannot reassign each other's variables** solely through parameter assignment. To change the caller's variable value, return the result for the caller to assign; to modify the state of a shared object, design and document the side effect intentionally.
