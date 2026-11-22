# Creating Objects and Calling Methods with Dot Notation in Java

> **Java core — language-basics / Classes and Objects**  
> **Environment:** JDK 17+, single self-contained Java file.  
> **Goal:** Create objects with `new`, hold references in variables, invoke methods with `object.method(arguments)` syntax, understand return values/`void`, per-object state, aliases, `null`, and differences between instance and `static` methods.

## 1. From Class to Object

A **class** declares state (fields) and behavior (methods). An **object** is an entity created from that class. The expression `new Type(...)` typically allocates an object and calls a matching **constructor** to initialize it:

~~~java
class Lamp {
    private boolean on;

    Lamp(boolean initiallyOn) { // Constructor: same name as class, no return type.
        this.on = initiallyOn;
    }

    void turnOn() {              // Instance method.
        this.on = true;
    }

    boolean isOn() {             // Returns current state.
        return this.on;
    }
}

// Usage from an appropriate method:
// Lamp deskLamp = new Lamp(false);
// deskLamp.turnOn();
// System.out.println(deskLamp.isOn()); // true.
~~~

In `Lamp deskLamp = new Lamp(false);`:

| Part | Meaning |
| --- | --- |
| `Lamp` on the left | Type of the reference variable |
| `deskLamp` | Name of the variable holding a reference to the object |
| `new Lamp(false)` | Creates an object and calls the constructor taking `boolean` |
| `deskLamp.turnOn()` | Calls an instance method via a reference and the dot operator |
| `deskLamp.isOn()` | Calls a method and receives a `boolean` value |

A constructor is **not a `void` method**. A constructor shares the class name and declares no return type; it cannot be called again using `deskLamp.Lamp(...)` syntax.

## 2. The Dot Operator `.` to Call Methods

Common syntax:

~~~java
receiver.methodName(argument1, argument2);
~~~

`receiver` is an expression referencing an object (such as the variable name `deskLamp`). The dot `.` selects an accessible member; parentheses `(...)` and arguments represent a **method call**.

~~~java
String text = " java ";
String clean = text.trim(); // "java"
int size = clean.length();  // 4.
boolean empty = clean.isEmpty(); // false.
~~~

These methods are instance methods of `String`: each call identifies the receiving object via `text` or `clean`. Meanwhile, `text.length` (missing parentheses) is **not a valid call** because `String` provides a `length()` method rather than a public `length` field.

- `object.field`: accesses a **field** if access permissions allow.
- `object.method()`: calls a **zero-parameter method**.
- `object.method(arg)`: calls a method with matching parameters.
- `method()` within the same class can be shorthand in an appropriate context, but writing `object.method()` clearly specifies the **receiving object**.

If a field is `private`, code in an unauthorized class cannot directly read/write `object.field`; use an appropriate public method instead of making fields `public` arbitrarily.

## 3. Methods with Parameters, Return Types, and `void`

~~~java
class Counter {
    private int value;

    Counter(int start) {
        this.value = start;
    }

    void add(int amount) {
        this.value += amount;
    }

    int current() {
        return this.value;
    }
}

// Counter counter = new Counter(2);
// counter.add(3);          // Updates value, returns no value.
// int now = counter.current(); // now == 5.
~~~

When calling `counter.add(3)`, `3` is the **argument**, while `amount` is the **parameter** of the `add` method. `counter.current()` returns an `int` value to assign, print, or use in an expression:

~~~java
// System.out.println("now=" + counter.current());
// int doubleValue = counter.current() * 2;
~~~

`void` means the method **provides no return value**; you cannot write `int x = counter.add(3);`. Conversely, a return type of `int` allows obtaining a value from `current()`.

Inside an instance method body, `this` refers to the **current object** receiving the call. `this.value` clearly refers to the object's field, not a local variable of the same name. Java arguments are passed **by value**, even when the value is a reference to an object.


## 4. Dot Calls Select the Right Receiver

~~~java
Counter first = new Counter(2);
Counter second = new Counter(5);
first.add(3);
second.add(-2);
// first.current() == 5; second.current() == 3.
~~~

The dot in `first.add(3)` selects the object referenced by `first`, while `second.add(-2)` acts on the second object. Both calls invoke the same method but have different **receivers**, so they modify two independent `value` fields.

## 5. How Do Aliases and `null` Affect Calls?

~~~java
Counter alias = first;
alias.add(1);                 // first.current() == 6.
alias = new Counter(1);       // Changes only the alias reference.
Counter missing = null;
// missing.add(1);            // NullPointerException if executed.
~~~

`alias = first` copies the reference value; it does **not** call the constructor. When two names point to the same object, a call through either name reaches the same state; reassigning `alias` does not change `first`'s reference. With `null`, there is no object to serve as receiver for an instance method call, so you must check or ensure the reference is non-null.

To compare whether two references refer to the same object, use `==`; comparing **business contents** of two objects requires an appropriate `equals` contract. The first lesson of the chapter explains object identity and aliasing in greater depth; here, focus on each call's receiver.

## 6. Method Chaining and Temporary Object Expressions

Since `new Counter(...)` is an expression that yields a reference, you can call a method directly on the new object:

~~~java
// new Counter(4).current()  // Returns 4.
~~~

If a method returns the object or a suitable reference, you can use **method chaining**:

~~~java
class Accumulator {
    private int total;

    Accumulator add(int number) {
        total += number;
        return this;
    }

    int value() {
        return total;
    }
}

// int result = new Accumulator().add(2).add(3).value();
// result == 5.
~~~

Evaluated left-to-right along the receiver chain: `new Accumulator()` creates the object, `add(2)` returns `this`, `add(3)` updates the same object, and `value()` returns the result.

If a method returns `void`, you cannot chain by calling another method **on the return value** of the `void` call. Use an object variable name and separate statements for clarity when needed.


## 7. The Dot Operator Also Appears in `static` Calls

~~~java
Counter counter = new Counter(2);
int current = counter.current();       // Instance: has a Counter receiver.
int maximum = Math.max(4, 9);        // Static: Math is a class name.
~~~

Same `.` symbol, yet `counter.current()` invokes behavior on an instance, while `Math.max(...)` invokes a static method through the **class name**, needing no `Math` object. Prefer `Type.staticMethod(...)` to avoid mistaking an object variable for the receiver of a static method; the dedicated `static` lesson analyzes the difference in full.

## 8. Standalone Java 17+ Program

Create file **DotInvocationDemo.java**:

~~~java
public final class DotInvocationDemo {
    private static final class Counter {
        private final String label;
        private int value;

        Counter(String label, int start) {
            this.label = label;
            this.value = start;
        }

        void increment() {
            this.value++;
        }

        void add(int amount) {
            this.value += amount;
        }

        int current() {
            return this.value;
        }

        boolean isPositive() {
            return this.value > 0;
        }

        String summary() {
            return label + ":" + value;
        }

        Counter addAndReturn(int amount) {
            add(amount);
            return this;
        }

        static int recommendedStart() {
            return 1;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter("A", 2);
        Counter second = new Counter("B", 5);
        System.out.println("createdA=" + first.summary());
        System.out.println("createdB=" + second.summary());

        first.increment();
        first.add(3);
        second.add(-2);
        System.out.println("afterCallsA=" + first.summary());
        System.out.println("afterCallsB=" + second.summary());
        System.out.println("returnedValue=" + first.current());
        System.out.println("isPositive=" + first.isPositive());

        Counter alias = first;
        alias.increment();
        System.out.println("aliasSame=" + (alias == first));
        System.out.println("afterAlias=" + first.summary());

        Counter another = new Counter("A", 7);
        System.out.println("sameStateDifferentObject=" + (first == another));
        System.out.println("anotherSummary=" + another.summary());

        System.out.println("afterChain="
                + first.addAndReturn(2).addAndReturn(1).summary());
        System.out.println("temporary="
                + new Counter("T", 4).summary());

        alias = new Counter("X", 1);
        System.out.println("aliasAfterReassign=" + alias.summary());
        System.out.println("firstAfterReassign=" + first.summary());

        System.out.println("staticDefault=" + Counter.recommendedStart());
        System.out.println("mathMax=" + Math.max(4, 9));

        Counter missing = null;
        System.out.println("missingIsNull=" + (missing == null));
        try {
            missing.increment();
        } catch (NullPointerException ex) {
            System.out.println("nullCall=NullPointerException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 DotInvocationDemo.java
java DotInvocationDemo
~~~

**Exact expected stdout:**

~~~text
createdA=A:2
createdB=B:5
afterCallsA=A:6
afterCallsB=B:3
returnedValue=6
isPositive=true
aliasSame=true
afterAlias=A:7
sameStateDifferentObject=false
anotherSummary=A:7
afterChain=A:10
temporary=T:4
aliasAfterReassign=X:1
firstAfterReassign=A:10
staticDefault=1
mathMax=9
missingIsNull=true
nullCall=NullPointerException
~~~

The two objects `first`/`second` have independent state. `aliasSame=true` while `sameStateDifferentObject=false` proves that **an alias is different from a new object with the same state**. `afterChain` illustrates methods returning `this` to enable chaining; `nullCall` only fails when calling an instance method through a `null` reference.

## 9. Common Mistakes and Exercises

| Mistake / Misunderstanding | How to understand or fix |
| --- | --- |
| Writing `Counter c; c.increment();` with an uninitialized local | Create `new Counter(...)` or assign a valid reference before using |
| Writing `Counter c = null; c.increment();` | No object exists yet; can cause `NullPointerException` |
| Calling `c.current` instead of `c.current()` | Methods must include `(...)` even with no arguments |
| Writing `int n = c.increment();` when the method returns `void` | Cannot use a `void` call as a value |
| Thinking `Counter alias = c` creates a new object | Only copies the reference; use `new` when a new object is needed |
| Thinking two objects of the same class always share instance fields | Each object has its own instance field values |
| Thinking the constructor is called via `c.Counter()` | Constructors run on `new Counter(...)`, not as normal methods |
| Treating `Math.max` like an instance method | Call static methods with `Math.max(...)` |
| Accessing a `private` field from another class | Use permitted methods; design getters/setters if needed |

**Exercise 1.** Create a `Rectangle` class with a constructor accepting width and height, and an `area()` method returning the area; call it via `rectangle.area()`.

**Exercise 2.** Create two different `Counter` objects, call `add` with different arguments, and explain why their states do not automatically synchronize.

**Exercise 3.** Create `Counter alias = first` and call `alias.increment()`. Then assign `alias = new Counter(...)` and predict `first.current()`.

**Exercise 4.** Write a method returning `this` to support `counter.addAndReturn(2).addAndReturn(3)`. Try changing the return type to `void` and observe the error when chaining.

**Exercise 5.** Distinguish `object.instanceMethod()` calls from `ClassName.staticMethod()` calls. State why calling an instance method through `null` fails.

### Takeaways

**`new Type(args)` creates an object and calls a constructor; class-typed variables normally hold references to objects.** Use `object.method(args)` to invoke behavior on the **receiving object**, including `(...)` for methods. Two variables can share an object through an alias; two `new` calls create separate objects. `static` belongs to the class and should be called as `Type.method(...)`; a `null` reference cannot receive an instance method call.