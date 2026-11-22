# Recursive Initialization, Circular Dependencies, and Incomplete Values in Java

## 1. The Problem: A Class Is Used While It Is Still Initializing

A Java class may access itself — directly or through another class — while executing `static` field assignment expressions or a `static { ... }` block. Java allows this situation in many cases, but the result is not always intuitive: **a `static` field may be read when it only holds its default value, before its initializer finishes running**.

Two phenomena need to be distinguished right away:

1. **Initialization recursion on the same thread:** while class A is being initialized, code accesses A again (possibly in a cycle A → B → A). The JVM recognizes that the same thread already has A's initialization in progress and **does not re-run** A's initializer; the recursive request is considered complete for that thread. Code may read fields of A that have not yet been assigned their final values.
2. **Circular initialization dependency across multiple threads:** thread T1 is initializing A and then needs B, while T2 is initializing B and then needs A. Each thread may have to wait for the other thread to finish, forming a **deadlock**.

Both cases originate from a circular dependency, but their mechanisms and symptoms differ. **An A → B → A cycle on the same thread does not automatically cause a StackOverflowError or a deadlock.** It typically produces “strange” results due to observing an incomplete state. A cross-thread cycle can block indefinitely without throwing an exception.

## 2. Phases Related to `static` Field Values

Before analyzing circular dependencies, we need to identify when the JVM creates values:

```text
Loading
   ↓
Linking
   ├── Verification
   ├── Preparation: allocate/set default values for static fields
   └── Resolution: may be performed early or deferred
   ↓
Initialization
   ├── ensure required superclasses have been initialized
   ├── run static field initializers in declaration order
   └── run static blocks in corresponding order
   ↓
Initialized successfully
```

**Preparation** prepares `static` fields with default values: integer `0`, `boolean=false`, reference `null`, etc. **Initialization** executes the assignment statements/expressions in the source code, in the textual order of the fields and static blocks. Therefore, given:

```java
static int count = calculate();
static String label = "ready";
```

while `calculate()` has not yet returned, `count` and `label` may still be `0` and `null` to code performing recursive initialization on the **same thread**.

There is an exception for **constant variables** represented by the `ConstantValue` attribute: the JLS specifies that they are assigned during the initialization procedure before running regular initializers, and use sites may already have inlined the constant at compile time. Therefore, do not infer that every `static final` field can be observed with a default value; only `static` fields that are **not compile-time constants** are the case requiring special attention in this article.

Do not equate *loaded* or *linked* with *initialized*. Reads of `Class<?>` or `T.class` do not by themselves trigger running T's initializer; whereas reading a non-compile-time-constant static field generally requires initializing the class that **declares** that field.

## 3. How Does the JVM Handle Recursive Initialization Requests?

According to the procedure in **JLS `12.4.2**, each runtime class or interface has an initialization state, which can be summarized as:

| State | Meaning when a thread requests initialization |
|---|---|
| Uninitialized | The thread starts the initialization procedure if selected to do so |
| Currently being initialized by **another** thread | The requesting thread must wait and recheck after the state changes |
| Currently being initialized by the **current thread itself** | The recursive request completes normally; `<clinit>` is not re-run |
| Successfully initialized | Use immediately, without re-running `<clinit>` |
| In an erroneous state | Further use along an initialization-triggering path will fail, typically with `NoClassDefFoundError` |

The JVM has its own initialization synchronization mechanism for each **runtime class/interface**. You do not need to, and should not try to, manually manage an “init lock” via `synchronized (SomeClass.class)` to control the initialization lifecycle. How the JVM implements the initialization lock is not necessarily equivalent to the Java monitor used by application code.

For the **same-thread** recursion case, the sequence can be visualized as follows:

```text
Thread T:
  initialize A
      A.<clinit> begins
          read B.value
              initialize B
                  B.<clinit> begins
                      read A.value
                          A is being initialized by T
                          → recursive request is considered handled
                          → returns the current value of A.value
                  B.<clinit> completes
          A.<clinit> completes
  A is successfully initialized
```

The key point: **“the recursive initialization request completes” does not mean `A.<clinit>` has finished running**. It only allows the same thread to proceed without initializing A infinitely. The state of A's fields still reflects what has been assigned **up to the time of access**.

## 4. Complete Example: An A → B → A Cycle and Values Still at Default

Create the file `CircularInitDemo.java`:

```java
public class CircularInitDemo {
    static class A {
        static int value = compute();

        static int compute() {
            System.out.println("A computes using B");
            return B.value + 1;
        }

        static {
            System.out.println("A finalized value=" + value);
        }
    }

    static class B {
        static int value = compute();

        static int compute() {
            System.out.println("B computes using A");
            return A.value + 10;
        }

        static {
            System.out.println("B finalized value=" + value);
        }
    }

    public static void main(String[] args) {
        boolean bFirst = args.length > 0 && args[0].equals("B");
        System.out.println("Start: " + (bFirst ? "B" : "A"));

        if (bFirst) {
            System.out.println("B.value=" + B.value);
            System.out.println("A.value=" + A.value);
        } else {
            System.out.println("A.value=" + A.value);
            System.out.println("B.value=" + B.value);
        }
    }
}
```

Compile once with Java 17+:

```bash
javac CircularInitDemo.java
```

### 4.1. Accessing A First

```bash
java CircularInitDemo
```

Exact stdout:

```text
Start: A
A computes using B
B computes using A
B finalized value=10
A finalized value=11
A.value=11
B.value=10
```

Step-by-step analysis:

1. Reading `A.value` in `main` forces the JVM to initialize A. Before the assignments run, both `A.value` and `B.value` have the default value `0` once their respective classes have been prepared.
2. `A.compute()` prints the first line, then requests `B.value`; because B is not yet initialized, the same thread begins initializing B.
3. `B.compute()` prints the second line, then requests `A.value`. A **is currently being** initialized by that very thread, so the JVM lets the recursive request complete without re-running A's initializer. **The assignment to `A.value` has still not finished**, so B reads `0`.
4. B computes `0 + 10 = 10`, assigns it to `B.value`, and then runs the static block printing `B finalized value=10`.
5. Back in A: `B.value` is now `10`; A computes `10 + 1 = 11`, assigns it to `A.value`, and then prints `A finalized value=11`.
6. `main` receives `A.value=11`, then reads `B.value=10`; the classes are already initialized, so their initializers do not run again.

**Conclusion from the example:** The JVM does not “wait for complete data” when the very thread running an initializer reads an unassigned field. It returns the current value, which here is `0`.

### 4.2. Accessing B First

Run the program in **a new JVM** with the argument `B`:

```bash
java CircularInitDemo B
```

Exact stdout:

```text
Start: B
B computes using A
A computes using B
A finalized value=1
B finalized value=11
B.value=11
A.value=1
```

This time B initializes first and is read back before being assigned, so `B.value=0` while computing A. Afterward, `A.value=1` and `B.value=11`. **The same source code, but a different first access point leads to a different final state.**

The two runs must be in **two separate JVM processes**, because within the same JVM where A/B have already initialized successfully, changing the read order afterward **does not re-initialize** the classes. This is a common mistake when writing experimental tests for class initialization.

## 5. Recursion Within a Single Class: Two Classes Are Not Required

A circular dependency also appears when a class's static initializer calls a static method of that same class, and the method reads a field that has not yet been assigned.

Create `SelfInitDemo.java`:

```java
public class SelfInitDemo {
    static class Settings {
        static int first = computeFirst();
        static int second = 8;

        static int computeFirst() {
            System.out.println("computeFirst sees second=" + second);
            return second + 1;
        }

        static {
            System.out.println(
                    "static block sees first=" + first
                    + ", second=" + second
            );
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + Settings.first);
        System.out.println("second=" + Settings.second);
    }
}
```

Run commands:

```bash
javac SelfInitDemo.java
java SelfInitDemo
```

Stdout:

```text
computeFirst sees second=0
static block sees first=1, second=8
first=1
second=8
```

`Settings.second` has not yet been assigned `8` when `computeFirst()` runs, so at that point it is still `0`. Java has a rule restricting certain direct references to static fields declared later in an initializer (**illegal forward reference**), but reading through a method as in the example still compiles validly. This compiler rule does not guarantee that every observation of a static field is already complete.

Avoid using the result from a field declared later as a validity condition directly in a preceding field initializer if the logic depends on the post-initialization value.

## 6. Circular Dependencies Can Leave `null` or Objects Not Yet Ready

For reference-type fields, the default value is **`null`**. This is more dangerous than adding `0`: code may throw a `NullPointerException`, store `null` in a cache, or pass an invalid reference out.

### 6.1. Example Showing `static final` Does Not Protect Against Initialization Cycles

Create `CircularReferenceDemo.java`:

```java
public class CircularReferenceDemo {
    static final class Holder {
        final String name;

        Holder(String name) {
            this.name = name;
        }
    }

    static final class Left {
        static final Holder HOLDER = Right.HOLDER;

        static {
            System.out.println("Left.HOLDER=" + Left.HOLDER);
        }
    }

    static final class Right {
        static final Holder HOLDER = Left.HOLDER;

        static {
            System.out.println("Right.HOLDER=" + Right.HOLDER);
        }
    }

    public static void main(String[] args) {
        System.out.println("read Left");
        System.out.println("result Left=" + Left.HOLDER);
        System.out.println("result Right=" + Right.HOLDER);
    }
}
```

Run:

```bash
javac CircularReferenceDemo.java
java CircularReferenceDemo
```

Stdout:

```text
read Left
Right.HOLDER=null
Left.HOLDER=null
result Left=null
result Right=null
```

Reading `Left.HOLDER` causes the JVM to initialize Left, which begins evaluating `Right.HOLDER`. Inside Right's initialization, reading `Left.HOLDER` happens on the **same thread that is currently initializing Left**, and Left's assignment has not yet finished, so its value is `null`. Right stores `null`, and afterward Left also stores `null`.

Both fields are declared `static final`, but `Holder` is a reference type rather than a `String` compile-time constant; `final` only constrains field assignment, and **does not guarantee that a circularly dependent initialization graph will automatically produce valid values**. In the example, `Holder`'s constructor has not even been called once. Nor does `final` turn a `null` reference into a valid object.

### 6.2. Distinguishing “Incomplete Values” from “Incompletely Constructed Objects”

There are at least three kinds of issues:

- **Static field still at its default:** not yet assigned; the recursive thread sees `0`/`false`/`null`.
- **Static field temporarily assigned but will still change:** logic between static blocks may read an intermediate value.
- **Object published prematurely:** a static initializer/constructor places `this` or an object under construction into a registry/callback; other code may use the object before its invariants are established. This also relates to safe publication, especially across multiple threads, and cannot be explained solely by default values of static fields.

Do not conclude that every field will always hold its default value in a circular dependency: **the order of assignments already executed** determines the observed value. A field that has already been assigned beforehand can be completely valid; a field not yet assigned may not be valid yet.
