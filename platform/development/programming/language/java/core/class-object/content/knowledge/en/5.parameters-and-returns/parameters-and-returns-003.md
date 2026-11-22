# Primitive Parameters and Reference Parameters in Java

When calling a method, Java passes the **value of the argument** to the **parameter**. The most important thing to remember is: **Java always passes arguments by value (pass-by-value)**, for both primitive types and reference types.

The difference lies in **which value is copied**:

- For primitive parameters such as `int`, `double`, `boolean`, Java copies the **primitive value**. Reassigning the parameter does not change the caller's primitive variable.
- For reference parameters such as `Student`, `StringBuilder`, `int[]`, Java copies the **reference value** to the object. Two variables can point to the same object. The method can modify the state of that object if the object allows it, but **reassigning the parameter** does not reassign the caller's variable.

The phrase "passing an object by reference" often leads beginners to misunderstand that the method receives permission to reassign a variable in the caller. In Java, **there is no pass-by-reference mechanism for the caller's variables**. To understand this accurately, we need to separate four things: **variables**, **variable values**, **objects**, and **assignment/state mutation**.

## 1. Review: Arguments, Parameters, and Data Types

An **argument** is an expression written at the call site; a **parameter** is a variable declared in the method signature.

~~~java
static int increase(int number) {
    return number + 1;
}

// In another method:
int score = 10;
int result = increase(score);
~~~

These are **illustrative code snippets**, which must be placed inside an appropriate class/method. `score` is a variable in the caller; the expression `score` in `increase(score)` is the argument. `number` is the parameter of `increase`. `increase` returns `11`, while `score` remains `10`.

### Two Related Type Categories

| Category | Example types | Value passed when calling a method |
| --- | --- | --- |
| Primitive | `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean` | Numeric, character, or boolean value, after conversions allowed by Java |
| Reference | User-defined classes such as `Account`, `String`, `Integer`, interface types, arrays such as `int[]` | Reference value to an object, or `null` |

`String` is a class; `Integer` is a wrapper class; **arrays are also objects**. Therefore, they all belong to the reference type category. An object can contain multiple primitive fields, but a variable of a class type does not "contain the entire object" in the sense of copying all fields when passing parameters.

Each parameter receives the value of the argument according to the conversion rules on method invocation. For example, an `int` can be widened to `long` when a method requires `long`. That is still **pass-by-value**.

## 2. Primitive Parameters: Modifying the Parameter Does Not Modify the Caller's Variable

Save the following program as **`PrimitiveParameterDemo.java`**:

~~~java
public class PrimitiveParameterDemo {
    static void change(int number, boolean enabled) {
        System.out.println("inside before: " + number + ", " + enabled);

        number = 99;
        enabled = false;

        System.out.println("inside after: " + number + ", " + enabled);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean active = true;

        change(score, active);

        System.out.println("outside: " + score + ", " + active);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 PrimitiveParameterDemo.java
java PrimitiveParameterDemo
~~~

Stdout:

~~~text
inside before: 10, true
inside after: 99, false
outside: 10, true
~~~

When calling `change(score, active)`:

1. Java reads the value of `score` as `10` and `active` as `true`.
2. These values are put into new parameters named `number` and `enabled` for the **call to `change`**.
3. Assigning `number = 99` and `enabled = false` only changes those two parameters.
4. The method finishes; the caller continues with `score = 10` and `active = true`.

Conceptual diagram:

~~~text
main()                          change(...)
  score  = 10    --copy 10-->    number  = 10 -> 99
  active = true  --copy ---->    enabled = true -> false

After change(): score = 10, active = true
~~~

There is no linking arrow that makes a primitive variable in the caller update automatically along with the parameter. **The variable names on both sides do not have to be the same**; independence comes from the pass-by-value mechanism, not from naming.

### Do Not Confuse This with Assignment in the Caller

~~~java
int score = 10;
score = increase(score);
~~~

Here `score` **changes** if `increase` returns a different value, but the reason is that the caller performs the assignment `score = ...`. The method does not rewrite the `score` variable in the caller itself.

With the method `static int increase(int number) { return number + 1; }`, the statement above makes `score` become `11`. This is the design you should generally use if you want to compute a **new primitive value** and let the caller decide whether to update the variable.

## 3. Reference Parameters: Copying the Reference, Not the Object

Consider the class:

~~~java
class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}
~~~

A variable `Counter counter` holds a **reference value** to a Counter instance. When passing this variable to the method `update(Counter parameter)`, Java copies that reference into the parameter variable `parameter`.

~~~text
Before the call:
caller.counter -------> Counter #1 { value = 5 }

During the call:
caller.counter ---+
                  +----> Counter #1 { value = 5 }
callee.parameter -+
~~~

Two different variables hold reference values leading to **the same object**. The operation `parameter.value = 20` changes the field of object #1, so reading via `caller.counter.value` also sees `20`. Conversely, `parameter = new Counter(100)` only makes **the parameter** point to a new instance; the caller's variable still points to object #1.

### Standalone Example: Modifying an Object and Reassigning a Parameter

Create the file **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        int getValue() {
            return value;
        }

        void setValue(int nextValue) {
            value = nextValue;
        }
    }

    static void change(Counter parameter) {
        parameter.setValue(20);
        System.out.println("after mutation: " + parameter.getValue());

        parameter = new Counter(100);
        System.out.println("after reassignment: " + parameter.getValue());
    }

    public static void main(String[] args) {
        Counter counter = new Counter(5);

        change(counter);

        System.out.println("caller: " + counter.getValue());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Stdout:

~~~text
after mutation: 20
after reassignment: 100
caller: 20
~~~

Precise analysis:

- After `parameter.setValue(20)`, **the shared object** has `value = 20`.
- After `parameter = new Counter(100)`, **the parameter** is assigned a reference to another object. The new object has `value = 100`.
- The caller's `counter` variable has never been assigned a new reference. It still references the first object with `value = 20`.
- The method ending does not automatically undo the state mutation performed on the first object.

Diagram after the reassignment statement **inside `change`**:

~~~text
caller.counter ----------> Counter #1 { value = 20 }

callee.parameter --------> Counter #2 { value = 100 }
~~~

This diagram illustrates **object identity and reference relationships**, not actual addresses allocated by the JVM. There is no need to observe memory addresses to explain the program output.

## 4. Distinguishing "Modifying an Object" and "Changing a Reference"

There are three operations that are written quite similarly but have different effects:

| Statement in method | Effect | Does the caller see the change? |
| --- | --- | --- |
| `value = 7;` with `value` as an `int` parameter | Reassigns the primitive parameter | No, unless the caller itself uses the returned value |
| `item.setCount(7);` or `item.count = 7;` if access is valid | Modifies the **object state** that the parameter points to | Yes, if the caller still observes the same object |
| `item = new Item();` | Assigns a new reference to the **parameter variable** | Does not make the reference variable in the caller point to the new Item |

An object may be immutable or disallow modifying fields from a method; in that case, having a reference does not automatically grant permission to modify it. Modifiability depends on the API, access modifiers, and object design, not on the parameter-passing mechanism.

### Passing a Reference Value Across Multiple Methods

If `main` calls `service.process(account)` and `process` in turn calls `validate(account)`, each call has **its own parameter containing a copy of the reference value**. The parameters can all point to the same object. That is why a state change across multiple method levels can be observed in the first caller.

However, at any level, the assignment `account = anotherAccount` only changes the **variable at that level**. It does not go back up and reassign every variable with the same name in the callers.

## 5. Arrays Are Also Passed by Reference Value

An array such as `int[]` is a **reference type**. A method can modify elements in the shared array, but cannot reassign the caller's array variable by assigning the parameter.

Create the file **`ArrayParameterDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void edit(int[] values) {
        values[0] = 99;
        values = new int[] {7, 8, 9};
        values[1] = 42;
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        edit(numbers);

        System.out.println("caller: " + Arrays.toString(numbers));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayParameterDemo.java
java ArrayParameterDemo
~~~

Stdout:

~~~text
caller: [99, 2, 3]
~~~

Explanation:

1. Initially, the parameter `values` and the variable `numbers` both point to the array `[1, 2, 3]`.
2. `values[0] = 99` writes to the first element of the **shared array**, so the caller sees `[99, 2, 3]`.
3. `values = new int[] {7, 8, 9}` changes the reference of the **parameter** to a new array.
4. `values[1] = 42` modifies the new array to `[7, 42, 9]`, without touching the original `numbers` array.

### `int[]` Is a Reference Type Even Though Elements Are Primitives

An `int[]` array contains primitive `int` elements, but the **array variable** is still a reference to an array object. Therefore:

- `numbers[0]` is an `int` value;
- `numbers` is a reference value;
- `edit(numbers)` copies the reference;
- `edit(numbers[0])`, if the method has a corresponding `int` parameter, will copy the primitive value of one element.

This is the distinction between the **type of the element** and the **type of the argument passed to the method**.

### To Replace the Caller's Array, Return a New Array

An API can return a new array:

~~~java
static int[] replaceWithNewArray(int[] oldValues) {
    return new int[] {7, 8, 9};
}

// In the caller:
numbers = replaceWithNewArray(numbers);
~~~

This is an **illustrative snippet**, which must be placed inside the corresponding class and method. Only the assignment `numbers = ...` **in the caller** causes the `numbers` variable to hold a reference to the returned array. Returning a reference from a method does not automatically change the caller's variable if the caller ignores the result.

## 6. Two Reference Variables of the Caller Cannot Be Swapped Using Only Two Parameters

A common mistake is writing `swap(a, b)` and expecting the two variables in the caller to exchange objects.

Create the file **`SwapParameterDemo.java`**:

~~~java
public class SwapParameterDemo {
    static final class Box {
        final String label;

        Box(String label) {
            this.label = label;
        }
    }

    static void swap(Box first, Box second) {
        Box temporary = first;
        first = second;
        second = temporary;

        System.out.println("inside: " + first.label + ", " + second.label);
    }

    public static void main(String[] args) {
        Box left = new Box("LEFT");
        Box right = new Box("RIGHT");

        swap(left, right);

        System.out.println("outside: " + left.label + ", " + right.label);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SwapParameterDemo.java
java SwapParameterDemo
~~~

Stdout:

~~~text
inside: RIGHT, LEFT
outside: LEFT, RIGHT
~~~

The method swapped **its own two parameter variables**, so the print statement inside the method outputs `RIGHT, LEFT`. The variables `left` and `right` in `main` are not reassigned; the print statement outside still outputs `LEFT, RIGHT`.

If the goal is to change the order of **two elements of an array**, the method can modify the contents of the shared array:

~~~java
static void swapElements(Box[] boxes) {
    Box temporary = boxes[0];
    boxes[0] = boxes[1];
    boxes[1] = temporary;
}
~~~

This is an **illustrative method snippet**; it is only valid when `Box[]` has at least two elements and the array is not `null`. This method can change **the elements of the array object** passed in by the caller, rather than swapping two independent reference variables of the caller.

In practice, a method that accepts a mutable container or returns a new result usually has clearer semantics than an API expected to directly modify the caller's variables.

## 7. `String`, Wrappers, and Immutable Objects: A Reference Does Not Mean It Can Be Modified

Some classes such as `String` and the wrapper classes `Integer`, `Long`, and `Boolean` are designed to be immutable. A method can compute a new string or wrapper value and then **reassign the parameter**, but it cannot modify the internal state of the old object as it can with a mutable `StringBuilder`.

Create the file **`ImmutableAndMutableDemo.java`**:

~~~java
public class ImmutableAndMutableDemo {
    static void update(String text, Integer number, StringBuilder builder) {
        text = text + "!";
        number = number + 1;
        builder.append("!");

        System.out.println("inside text: " + text);
        System.out.println("inside number: " + number);
        System.out.println("inside builder: " + builder);
    }

    public static void main(String[] args) {
        String text = "Java";
        Integer number = 10;
        StringBuilder builder = new StringBuilder("Java");

        update(text, number, builder);

        System.out.println("outside text: " + text);
        System.out.println("outside number: " + number);
        System.out.println("outside builder: " + builder);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableAndMutableDemo.java
java ImmutableAndMutableDemo
~~~

Stdout:

~~~text
inside text: Java!
inside number: 11
inside builder: Java!
outside text: Java
outside number: 10
outside builder: Java!
~~~

Reasons:

- `String` is immutable. The expression `text + "!"` creates new string content; `text = ...` assigns a new reference **only to the parameter `text`**.
- `Integer` is immutable. The expression `number + 1` involves unboxing, numeric calculation, and then boxing (the details may be optimized); `number = ...` changes the parameter's reference and does not make the `number` variable in the caller receive a new value.
- `StringBuilder` is mutable. `builder.append("!")` modifies the state of the object that both the parameter and the caller point to, so the caller sees `Java!`.

**Avoid inferring that "a reference type will always change when passed into a method".** The passing mechanism is the same for every reference type; what differs is whether the method performs **parameter reassignment** or **invokes behavior that modifies the object's state**.

### Primitive Types Differ from Wrapper Types

`int` and `Integer` are not the same type:

- `int` always holds an integer value within the `int` type range and does not hold `null`.
- `Integer` is a reference type and can be `null`; auto-unboxing a null `Integer` value causes a `NullPointerException`.
- A call can perform boxing/unboxing according to Java's overload and conversion rules, but that **does not turn Java into pass-by-reference**.
- You should not use `==` to compare the contents of two wrapper objects if the goal is value equality: compare appropriately for the type, such as `Integer.equals` with proper null handling, or controlled unboxing.

## 8. `null` Is Also a Reference Value Passed by Value

If the argument is `null` or a reference variable currently holding `null`, the parameter receives the corresponding null value. There is no object behind null for the method to modify.

~~~java
static void requireName(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }
    System.out.println(name.length());
}
~~~

This is an **illustrative method snippet**, not a standalone program. If `requireName(null)` is called, the method throws the `IllegalArgumentException` declared in its body. If the check statement is omitted and `name.length()` is called, a `NullPointerException` will occur because the receiver is null.

A method can assign a null parameter to a new object:

~~~java
static void createIfMissing(StringBuilder value) {
    if (value == null) {
        value = new StringBuilder("created");
    }
}
~~~

However, calling `createIfMissing(null)` **does not create an object and automatically put it into the caller's reference variable**. The new object is only assigned to the parameter `value`. To receive the new object, the caller needs the method to **return the reference**, for example:

~~~java
static StringBuilder ensureValue(StringBuilder value) {
    return value == null ? new StringBuilder("created") : value;
}

// In the caller:
StringBuilder result = ensureValue(null);
~~~

The snippets above are examples of how to handle references and must be placed inside an appropriate class/method.

## 9. `final` Parameters: Cannot Reassign the Parameter, but Can Still Modify the Object

Java allows declaring a parameter as `final`:

~~~java
static void rename(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder("other"); // Compilation error.
}
~~~

In this illustrative method, `final` prevents assigning a new reference to the parameter variable `builder`. It does **not** prevent `builder.append("!")` from modifying the StringBuilder. Similarly, `final int number` disallows reassigning `number`.

Therefore:

- `final` on a **variable** governs whether the variable can be reassigned.
- Immutability of an **object** is a design property of the class and all of its observable data.
- `final` does not change the pass-by-value rule.

Declaring `final` helps avoid accidentally reassigning parameter names in complex methods, but it is not required for a method to use the parameter-passing mechanism properly.

## 10. Reference to an Object Containing Primitive Fields: Distinguishing Two Data Levels

Suppose we have:

~~~java
class Player {
    private int score;

    Player(int score) {
        this.score = score;
    }

    void addPoints(int points) {
        score += points;
    }
}
~~~

The field `score` and the parameter `points` are both primitive `int`, but the call `player.addPoints(5)` is an **instance method on the object `player`**. Inside the method, the operation `score += points` updates a **primitive field within the object's state**, so when the caller reads through the object afterward, it sees that score has changed.

This does not prove that the method receives primitives by reference; in reality:

- `points` receives a copy of the value `5`.
- `this` in `addPoints` represents the current Player.
- The method updates the `this.score` field of that object.
- Modifying a field is different from reassigning the caller's `points` variable.

You should always answer the question: **Is the assignment writing to a parameter, a local variable, an object field, an array element, or a variable of the caller itself?** The syntax `=` looks the same, but the targets are different storage locations.

## 11. Passing References and Issues of Aliasing and Encapsulation

Because multiple variables can reference the same mutable object, external code can modify shared data in unintended ways if an API directly exposes internal references.

Example of a class that is not safe regarding encapsulation:

~~~java
class ScoreBook {
    private final int[] scores;

    ScoreBook(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }
}
~~~

This is an **illustrative class**. The constructor stores the exact `scores` reference from the caller; the `scores()` method returns a reference to the internal array. The caller can modify `scores[0]` after passing it in, or modify elements of the returned array. No array-copying step happens automatically when crossing a method boundary.

One approach using defensive copies:

~~~java
class ScoreBook {
    private final int[] scores;

    ScoreBook(int[] scores) {
        if (scores == null) {
            throw new IllegalArgumentException("scores is required");
        }
        this.scores = scores.clone();
    }

    int[] scores() {
        return scores.clone();
    }
}
~~~

This is an **alternative version** of the `ScoreBook` class above, not an additional class declared with the same name in the same package. Because the array contains primitive `int` elements, `clone()` creates a new array with each element's value copied. If the caller modifies the old array or the returned array, it will not change the array inside `ScoreBook`.

For an array of mutable objects, `clone()` only copies **the array structure and the element references**, without automatically deep-copying each object inside. To achieve deep immutability, you need to design element copying or use appropriate immutable types.

### Defining Clear Method Contracts

An API should clearly state whether a method is allowed to modify the caller's object:

- `sortInPlace(int[] values)` can be designed to modify the elements of the passed-in array.
- `sortedCopy(int[] values)` can return a new array, leaving the caller's array unchanged.
- `addPoints(Player player, int points)` can modify the Player state.
- `calculateScore(Player player)` can be read-only, without modifying state.
- `withName(String newName)` on a value object can return a new object instead of modifying the current object.

The names above are **API design suggestions**, not built-in standard Java methods. Regardless of which policy each method chooses, argument passing still follows pass-by-value.

## 12. Return Values Are the Usual Way to Communicate a New Value

To update a primitive variable in the caller, a method can return the new value:

~~~java
static int addBonus(int oldScore, int bonus) {
    return Math.addExact(oldScore, bonus);
}

// In the caller:
int score = 10;
score = addBonus(score, 5);
~~~

`score` becomes `15` because the caller explicitly assigns the `return` value. If the assignment is omitted and only `addBonus(score, 5);` is called, the variable `score` remains `10`.

To replace the caller's reference, a method can also return an object:

~~~java
static StringBuilder replace(StringBuilder original) {
    return new StringBuilder("new");
}

// In the caller:
StringBuilder builder = new StringBuilder("old");
builder = replace(builder);
~~~

The assignment in the caller makes `builder` point to the new StringBuilder. The old object is not necessarily garbage-collected immediately, because that depends on any remaining reference paths and the GC mechanism.

**Do not use a parameter as an "output parameter" by reassigning it and expecting the caller to see the new reference.** Java does not provide `ref`/`out` parameter syntax as some other languages do.

## 13. Varargs Are Effectively Still Array Parameters

Declaring `int... values` allows passing a variable number of `int` arguments. Inside the method body, `values` has the type `int[]`.

Create the file **`VarargsParameterDemo.java`**:

~~~java
import java.util.Arrays;

public class VarargsParameterDemo {
    static void change(int... values) {
        if (values.length > 0) {
            values[0] = 77;
        }
        System.out.println("inside: " + Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] existing = {1, 2};

        change(existing);
        System.out.println("existing: " + Arrays.toString(existing));

        change(3, 4);
    }
}
~~~

~~~bash
javac -encoding UTF-8 VarargsParameterDemo.java
java VarargsParameterDemo
~~~

Stdout:

~~~text
inside: [77, 2]
existing: [77, 2]
inside: [77, 4]
~~~

When calling `change(existing)`, the method receives a reference to the `existing` array itself; modifying `values[0]` causes the caller to see the element change. When calling `change(3, 4)`, the varargs mechanism creates a corresponding argument array for the call, and the method modifies that array. There is no array variable named `existing` in the caller of the second call that gets updated.

This is why varargs should be understood through the parameter's **actual array type**. In the example, modifying an element is intentional so we can observe aliasing; many varargs APIs should only read the input data to avoid unexpected side effects.

## 14. Argument Evaluation Order: Each Expression Runs Before the Method Body

A call `combine(first(), second())` must evaluate the arguments before the target method begins. Java specifies that argument expressions are evaluated **from left to right**. Side effects while evaluating arguments can change the values passed into the method.

Create the file **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int trace(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    static void receive(int first, int second) {
        System.out.println("received=" + first + "," + second);
    }

    public static void main(String[] args) {
        int number = 3;

        receive(
                trace("left", number++),
                trace("right", number)
        );

        System.out.println("number=" + number);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Stdout:

~~~text
left=3
right=4
received=3,4
number=4
~~~

The first argument `number++` evaluates to `3`, while also updating **the variable in the caller** to `4` before the second argument is evaluated. Therefore, `trace("right", number)` receives `4`.

This example highlights two independent mechanisms:

1. Java evaluates arguments from left to right and can perform side effects **directly in the caller**.
2. Afterward, the target method receives the computed values into its separate parameters.

If the `receive` method contains the statement `first = 100;`, that assignment still does not cause `number` in `main` to change further. In real code, modifying a variable directly inside an argument list often harms readability; consider splitting it into clear statements.

## 15. When an Exception Occurs: Parameters May Not All Be Passed

An argument expression can throw an exception. If an argument has not finished evaluating, the target method call may never begin.

~~~java
static int fail() {
    throw new IllegalStateException("argument failed");
}

static void show(int a, int b) {
    System.out.println("show called");
}

// In the caller:
show(1, fail());
~~~

These are **illustrative snippets**, not a standalone program. With the call `show(1, fail())`, the expression `fail()` throws an exception while preparing the second argument; the body of `show` **does not run** and the line `show called` is not printed. If the caller has an appropriate `catch`, it can handle the exception.

In another case, if a parameter is `null` and the method accesses `parameter.field`, the exception can occur **inside the method body**. The two cases have different stack traces, so you should check where the exception actually originated.

## 16. Boxing, Overloading, and the Selected Parameter Type

The parameter types in a method signature determine which conversions are allowed at the call site. For example:

~~~java
static void print(long number) {
    System.out.println("long=" + number);
}

static void print(Integer number) {
    System.out.println("Integer=" + number);
}
~~~

This is an **illustrative pair of methods**, which must be placed in a class and called from an appropriate method. When calling `print(5)` with an `int` literal, Java prefers primitive widening to `long` over boxing to `Integer` under the corresponding overload resolution rules, so it selects `print(long)`.

Do not infer that "because `Integer` is an object, Java passed by reference". Overload resolution decides **which method is called**; pass-by-value decides **what value the parameter of the selected method receives**. The two mechanisms belong to different stages/aspects.

Some things to remember about wrappers:

- `Integer a = 5;` can use autoboxing to create/obtain a wrapper value.
- `int b = a;` uses unboxing, and if `a == null`, it can throw a `NullPointerException`.
- `Integer` has no setter to change the integer value of an instance. Assigning `a = a + 1` creates/obtains another wrapper value for the variable `a` to reference, without modifying the old wrapper.
- `==` between two wrapper references checks for the same instance, not necessarily the same value. For logical comparison, use `equals` according to its contract and handle null.

## 17. "Passing the Same Object" Does Not Mean "Safely Modifying the Object from Multiple Threads"

A mutable object can be shared by multiple references within a single thread or across threads. The ability to point to the same object explains why a method can change state, but it **does not automatically create a synchronization mechanism**.

~~~java
class UnsafeCounter {
    int value;

    void increment() {
        value++;
    }
}
~~~

This is an illustrative class. If multiple threads concurrently call `increment()` on **the same instance**, the operation `value++` does not guarantee an atomic update; updates can be lost or visibility issues can occur under the Java Memory Model. A parameter holding a reference to Counter does not make the behavior suddenly thread-safe. When studying concurrency, you need to choose appropriate synchronization, atomic types, or immutable models.

In this lesson, the programs run sequentially to focus on the primitive/reference mechanism. Do not confuse the concept of pass-by-value with concurrency issues.

## 18. Common Misconceptions

| Misleading statement | Correct understanding |
| --- | --- |
| "Primitives are pass-by-value, objects are pass-by-reference." | Both are pass-by-value; for an object, the copied value is the **reference**. |
| "Calling a method with an object creates a copy of the object." | Only the reference is copied; fields are not cloned automatically. |
| "Reassigning a parameter reassigns the caller's variable." | A parameter is a separate variable for that call; the caller's variable cannot be reassigned through that assignment. |
| "Modifying a field via a parameter does not affect the caller." | If the caller and the parameter point to the same mutable object, the caller can observe the changed field. |
| "An array holds ints, so it is passed like an int." | `int[]` is a reference type; the `int` elements are primitives. |
| "`String` is a reference type, so string concatenation changes the original string." | `String` is immutable; concatenation produces a new string value. |
| "`Integer` is a primitive like `int`." | `Integer` is a wrapper object, can be null, and is immutable. |
| "A `final` parameter prevents modifying any object." | It prevents reassigning the parameter variable, and does not itself prevent calling mutating methods on the object. |
| "A method can swap two object variables of the caller by swapping parameters." | It only swaps the two parameters; the caller must assign the result or intentionally modify container contents. |
| "When a reference variable goes out of scope, the object definitely disappears." | The object may have other aliases; GC timing is not guaranteed. |
| "A method that receives an object can naturally modify private fields." | The method must have access permission or be provided an appropriate API. |
| "An object's return value is a deep-copied object." | Returning a reference normally only returns the reference value, not a deep copy. |

## 19. Self-Check Exercises: Read the Code Before Looking at the Result

### Exercise 1 — Independent Primitives

~~~java
static void increase(int n) {
    n++;
}

// In the caller:
int x = 2;
increase(x);
System.out.println(x);
~~~

The result is **`2`**. The statement `n++` changes the parameter `n`. If you change the method to `static int increase(int n) { return n + 1; }` and write `x = increase(x);`, the result is **`3`** because the caller assigns the returned value.

### Exercise 2 — References to the Same Object

~~~java
class Item {
    int count;
}

static void fill(Item p) {
    p.count = 7;
}

// In the caller:
Item a = new Item();
fill(a);
System.out.println(a.count);
~~~

The result is **`7`**. The parameter `p` and the variable `a` both reference the same Item. Different variable names do not create different objects.

### Exercise 3 — Reassigning the Parameter Does Not Change the Caller

~~~java
static void reset(Item p) {
    p = new Item();
    p.count = 50;
}

// In the caller, after a.count = 7 has already been set:
reset(a);
System.out.println(a.count);
~~~

The result is still **`7`**, because `reset` only assigns a new reference to the parameter `p` and then modifies the new Item. The Item that `a` points to is not modified.

### Exercise 4 — Array Alias

~~~java
static void replaceFirst(int[] array) {
    array[0] = -1;
    array = new int[] {100, 200};
}

// In the caller:
int[] data = {5, 6};
replaceFirst(data);
System.out.println(data[0]);
~~~

The result is **`-1`**. The first line modifies the caller's array; the following line only assigns the parameter variable to a new array.

### Exercise 5 — Distinguishing String and StringBuilder

~~~java
static void modify(String text, StringBuilder builder) {
    text += "!";
    builder.append("!");
}

// In the caller:
String a = "Go";
StringBuilder b = new StringBuilder("Go");
modify(a, b);
System.out.println(a + " / " + b);
~~~

Result:

~~~text
Go / Go!
~~~

The expression `text += "!"` inside the method reassigns the String parameter; `builder.append("!")` modifies the shared StringBuilder.

The snippets in Exercises 1–5 are **code fragments meant to be placed into test classes/methods**, not standalone programs. You can use the complete runnable files from the earlier sections as a basis to try them yourself.

## 20. Method Design Checklist

Before writing or calling a method, ask:

1. **Is the parameter a primitive or a reference type?** Arrays and wrappers are reference types, even if their elements/contents relate to integers.
2. **Does the method reassign the parameter or modify the object?** `parameter = ...` is different from `parameter.field = ...` or `parameter.mutate()`.
3. **Does the caller need a new value or a side effect?** If a separate variable of the caller needs to be updated, usually use `return` and assign the result at the caller.
4. **Are there other aliases?** Other components that also hold references to the mutable object can observe the change.
5. **Is the object immutable?** `String` and `Integer` do not have internal state that is modified through operations like in the mutable examples.
6. **Can `null` occur?** Check at the input boundary if null is invalid.
7. **Is a defensive copy needed?** Especially when accepting/returning arrays or mutable collections.
8. **Does the method have a clear contract regarding state mutation?** The method name, documentation, and tests should show when the input is modified.
9. **Are there any edge cases or exceptions before the call completes?** Arguments are also Java expressions that are evaluated and can have side effects.
10. **Are multiple threads modifying the object simultaneously?** Synchronization must be designed independently of the parameter-passing mechanism.

**Learning takeaway:** Whenever you encounter a Java method, picture that **each parameter is a separate variable populated with a copy of the argument's value**. For primitives, the copy is the primitive value. For references, the copy is a reference that can lead to the same object. From this model, you will accurately explain the behavior of parameter assignment, field modification, changing array elements, string concatenation, returning new objects, and aliasing cases in real-world Java code.
