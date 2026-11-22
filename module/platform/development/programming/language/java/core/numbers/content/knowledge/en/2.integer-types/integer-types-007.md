# Default Values of Fields and Definite Assignment of Local Variables in Java

In Java, **instance fields and `static` fields always have an initial value**, even if the author has not explicitly assigned one. Conversely, **local variables must be definitely assigned before being read** (*definite assignment*). Both rules coexist, yet apply to two different scopes. Understanding them properly helps distinguish compile-time errors from runtime values, especially when working with integer types.

## 1. Distinguishing Fields, Local Variables, Parameters, and Array Elements

| Declaration Location | Example | Has Default Value When Not Explicitly Assigned? | Rule When Reading |
| --- | --- | --- | --- |
| Instance field | `class A { int count; }` | Yes: `0` | Readable after object creation; the value may be changed by initializers/constructors |
| Class (`static`) field | `static long total;` | Yes: `0L` | Readable; shared across the class, not per object |
| Local variable in a method, constructor, or block | `void run() { int n; }` | **No** | The compiler must prove the variable is assigned before every read |
| Method/constructor parameter | `void run(int n)` | Not applicable as a declaration-site default | Value comes from the caller; can be read immediately in the method body |
| Element of a newly created array | `new int[3]` | Yes: each element is `0` | Elements can be read immediately after creating the array |
| Local variable referencing an array | `int[] a;` | **No** | Must assign `a` before use, even though array elements get defaults once an array is created |

A variable is considered *local* solely because it is declared inside a method body, constructor, or block; not because it is of type `int` or declared with `final`. The data type does not determine the assign-before-reading rule: the declaration location is the deciding factor.

## 2. Default Values of All Field Types

When an object is created, its instance fields receive default values before explicit initializers run. When a class is prepared for initialization, its static fields receive default values before static initializers run. Elements of a newly created array are also initialized to defaults.

| Type | Default Value | Notes |
| --- | --- | --- |
| `byte` | `0` | 8-bit signed integer |
| `short` | `0` | 16-bit signed integer |
| `int` | `0` | 32-bit signed integer |
| `long` | `0L` | 64-bit signed integer; writing `0L` makes the `long` type explicit |
| `float` | `0.0f` | 32-bit floating-point number |
| `double` | `0.0d` | 64-bit floating-point number |
| `char` | `'\u0000'` | NUL character (numeric code 0), distinct from `'0'` and space |
| `boolean` | `false` | Not `0` |
| Any reference type, including `String`, `Integer`, objects, arrays | `null` | References no object yet; **not** an empty string or empty array |

The values in the table apply to fields **not yet explicitly initialized**, not a guarantee that the field will keep that value forever. For example, `int quantity = 15;` has an effective value of `15` after field initialization completes.

### Complete Example: Fields, Assigned Local Variable, and Array Elements

Create the file `DefaultValuesDemo.java`:

```java
public class DefaultValuesDemo {
    private static long total;  // static field: 0
    private int count;          // instance field: 0
    private boolean active;     // instance field: false
    private char marker;        // instance field: '\u0000'
    private String label;       // reference field: null

    public static void main(String[] args) {
        DefaultValuesDemo demo = new DefaultValuesDemo();
        int localCount = 7;       // local: assigned before reading
        int[] scores = new int[2]; // array elements automatically receive 0

        System.out.println("total=" + total);
        System.out.println("count=" + demo.count);
        System.out.println("active=" + demo.active);
        System.out.println("markerCode=" + (int) demo.marker);
        System.out.println("label=" + demo.label);
        System.out.println("localCount=" + localCount);
        System.out.println("scores=" + scores[0] + "," + scores[1]);
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac DefaultValuesDemo.java
java DefaultValuesDemo
```

Expected output:

```text
total=0
count=0
active=false
markerCode=0
label=null
localCount=7
scores=0,0
```

The cast `(int) demo.marker` displays the numeric code `0`, because the NUL character is normally invisible if printed directly. String concatenation with a `null` reference produces the text `null`; **calling a method on `null` is different** and can throw `NullPointerException`.

## 3. Local Variables: Declaration Does Not Mean Assigned

Java allows **declaring** a local variable first and **assigning** it later, but does not allow reading it before it is definitely assigned along every path reaching the read.

```java
class InvalidLocal {
    static void show() {
        int value;
        System.out.println(value); // COMPILE ERROR
    }
}
```

This snippet is an **error illustration**, not a program to run. `javac` typically reports `variable value might not have been initialized`. Nothing here prints `0`: the compiler rejects the code before execution.

The right way is to assign before the first read:

```java
class ValidLocal {
    static void show() {
        int value;
        value = 42;
        System.out.println(value);
    }
}
```

`int value = 42;` combines declaration and assignment on one line, though **writing them on the same line is not mandatory**. Reading also happens implicitly inside expressions:

```java
class InvalidIncrement {
    static void show() {
        int count;
        // count++;      // invalid: must read count before incrementing
        // count += 1;    // invalid: also needs to read the old value
        // count = count + 1; // invalid: right-hand side reads count
        count = 0;        // initial assignment, valid
        count++;          // read and increment after assignment, valid
    }
}
```

A local variable `Integer number;` also **does not automatically become `null`**; to allow it to hold `null` initially, you must write `Integer number = null;`. Similarly, `int[] values;` neither creates an array nor initializes that reference variable.

## 4. Definite Assignment Depends on Program Control Flow

The compiler analyzes all control-flow paths that can reach a variable read, rather than just checking whether `=` appears on a preceding line.

### With `if` / `else`: Every Path Reaching the Read Assigns It

File `DefiniteAssignmentDemo.java`:

```java
public class DefiniteAssignmentDemo {
    static int score(boolean passed) {
        int result;
        if (passed) {
            result = 100;
        } else {
            result = 0;
        }
        return result; // both branches have assigned it
    }

    public static void main(String[] args) {
        System.out.println("passed=" + score(true));
        System.out.println("failed=" + score(false));
    }
}
```

```bash
javac DefiniteAssignmentDemo.java
java DefiniteAssignmentDemo
```

```text
passed=100
failed=0
```

If you omit `else`, the variable may remain unassigned when the condition is false:

```java
class MissingBranch {
    static int score(boolean passed) {
        int result;
        if (passed) {
            result = 100;
        }
        return result; // COMPILE ERROR: an unassigned path exists
    }
}
```

You can fix this by giving an initial assignment (`int result = 0;`), assigning in the `else` branch, or returning early in the unassigned branch. You only need to ensure **every path that actually reaches the read** has assigned the variable; not every branch must assign it if that branch exits the method before the read.

### Loops: The Loop Body Might Not Execute

```java
class LoopCase {
    static void show(boolean shouldRun) {
        int last;
        while (shouldRun) {
            last = 10;
            break;
        }
        // System.out.println(last); // invalid: while loop might not execute
    }
}
```

If you need to use `last` after the loop, give it a sensible initial value or restructure the control flow. The programmer “knowing” a condition is usually true does not replace the compiler's *definite assignment* proof.

### Parameters and Local Variables Assigned `null`

```java
class AssignedDoesNotMeanNonNull {
    static void inspect(String text) {
        String local = text; // assigned, even when text is null
        // local.length() will throw NullPointerException if local == null
        System.out.println(local == null ? "missing" : local.length());
    }
}
```

*Definite assignment* checks “has a valid assignment occurred?”, **not** whether a reference is non-`null` or whether a value satisfies business constraints. Those require separate checks, such as `if (local != null)` or `Objects.requireNonNull(...)` when appropriate.

## 5. Fields Have Defaults but Can Be Assigned Later

For an instance field of type `int`:

```java
class Counter {
    int count; // default is 0

    Counter() {
        count = 5; // constructor changes value to 5
    }
}
```

A normal `new Counter()` object will have `count == 5` after the constructor finishes. The default `0` is the initial starting state; initializers and constructors can change it.

At a high level, the relevant order is:

1. Static fields receive defaults, then static initializers / explicit class initializers run in source order when the class is initialized.
2. Each new object receives defaults for its instance fields; field initializers / instance initialization blocks and the constructor body can then assign other values following Java's initialization order.
3. Elements of a newly created array receive defaults according to the element type, and the program can then modify individual elements.

**Note on initializer order:** a method called inside an initializer can observe a field declared later before that field's explicit initializer runs.

File `InitializationOrderDemo.java`:

```java
public class InitializationOrderDemo {
    private int observed = readLater();
    private int later = 5;

    private int readLater() {
        return later;
    }

    public static void main(String[] args) {
        InitializationOrderDemo demo = new InitializationOrderDemo();
        System.out.println("observed=" + demo.observed);
        System.out.println("later=" + demo.later);
    }
}
```

```bash
javac InitializationOrderDemo.java
java InitializationOrderDemo
```

```text
observed=0
later=5
```

At the moment `readLater()` is called, `later` still holds the default `0`; `private int later = 5;` executes afterward. This example does **not** mean every field stays `0` after the constructor finishes.

## 6. The `final` Case: Default Values Do Not Waive the Assignment Requirement

A `final` field assigned at declaration needs no further assignment:

```java
class Config {
    final int retries = 3;
}
```

If a `final` field has no initializer (*blank final field*), the program must ensure it is assigned according to Java's rules: an instance blank final must be assigned exactly once along every constructor initialization path that completes normally; a static blank final must be assigned during class initialization, e.g., via a static initializer. The default `0` cannot be treated as an assignment satisfying this obligation.

File `FinalFieldDemo.java`:

```java
public class FinalFieldDemo {
    private final int id;
    private static final int LIMIT;

    static {
        LIMIT = 10;
    }

    FinalFieldDemo(int id) {
        this.id = id;
    }

    public static void main(String[] args) {
        FinalFieldDemo demo = new FinalFieldDemo(7);
        System.out.println("id=" + demo.id);
        System.out.println("limit=" + LIMIT);
    }
}
```

```bash
javac FinalFieldDemo.java
java FinalFieldDemo
```

```text
id=7
limit=10
```

A `final` local variable can be declared and assigned once later: `final int n; n = 4;` is valid, but a subsequent `n = 5;` is a compile error. Inside an `if`/`else`, each branch can assign to the same `final` variable as long as every execution path to the point of use assigns it at most once (and definitely once before reading). `final` does not mean “automatically has a default”.

## 7. Relationship with `var` and Boxed Numeric Reference Types

Since Java 10, `var` infers the type of **a local variable with an initializer**:

```java
class InferredLocal {
    static void show() {
        var count = 10;              // inferred as int
        var numbers = new int[2];    // inferred as int[]
        System.out.println(count + numbers[0]); // 10
    }
}
```

You cannot write `var count;` (no initializer to infer the type), `var unknown = null;` (cannot infer a type from `null`), or use `var` to declare ordinary fields. This is a specific requirement of `var`, in addition to the definite assignment rule for all local variables.

Distinguish primitive fields from wrapper fields:

```java
class BoxedValues {
    int primitive;        // 0
    Integer boxed;        // null

    int unsafe() {
        return boxed;     // compiles, but unboxing null throws NPE at runtime
    }
}
```

`Integer` is a reference type, so its default is `null`, even though it represents an integer. Do not assume the default of `Integer` is `0`; check for `null` or assign a value before unboxing if needed.

## 8. Common Misconceptions

| Statement | True or False? | Explanation |
| --- | --- | --- |
| “Every `int` variable defaults to `0`.” | False | Only fields/array elements undergo default initialization; unassigned local variables cannot be read |
| “`int x;` in a method followed by `print(x)` prints `0`.” | False | This is a compile error because `x` is not definitely assigned |
| “`static int total;` can be read immediately with value `0`.” | True | Static fields get default initialization; other initializers may change it later |
| “A `String title;` field automatically becomes an empty string.” | False | Its default is `null`, not `""` |
| “`new int[4]` has four elements equal to `0`.” | True | Array elements are initialized to defaults |
| “`int[] numbers;` in a method is an empty array.” | False | It is only a local variable not yet assigned an array reference |
| “Assigned `null` means it failed definite assignment.” | False | `null` is a valid assigned value for a reference type |
| “Using `++` or `+=` is a way to initially assign a local.” | False | These operators must read the old value first, so the local must already be assigned |

### Quick Decision Checklist When Reading Code

1. Identify **where** the variable is declared: field, local, parameter, or array element.
2. If it is a field or newly created array element, look up the type's default value; then check initializers/constructors/assignments that may change it.
3. If it is a local variable, trace every path to its **first read** and verify each path has an assignment.
4. If `final` is present, also check the single-assignment constraint and every required initialization path.
5. If it is a reference type, distinguish **assigned** from **non-`null`**; if it is a wrapper like `Integer`, watch out for unboxing.

The key point to remember is: **default values of fields and array elements are Java's initialization behavior; requiring local variables to be assigned before reading is a compiler check rule**. Therefore, the same declaration `int x;` can allow reading `x` when `x` is a field, yet is not enough to read `x` if `x` is a local variable.
