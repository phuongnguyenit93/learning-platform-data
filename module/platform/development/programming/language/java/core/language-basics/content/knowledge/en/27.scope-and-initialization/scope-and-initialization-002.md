# Variable Lifetime Differs from Name Scope in Java

## 1. Two distinct concepts

When discussing Java variables, we must distinguish **scope** (*the region where a name can be used*) from **lifetime** (*how long an entity exists at runtime*).

- **Name scope (scope)** is the portion of source code text where the compiler allows using an **identifier** to refer to a declaration. This is primarily a static rule checked at compile time.
- **Variable lifetime** relates to when an execution creates and stops using that variable instance. It depends on the kind of variable: local variable/parameter, instance field, or `static` field.
- **Object lifetime** is a separate matter. An object created with `new` can still be referenced after the initial local variable goes out of scope. The JVM manages object eligibility for collection via *reachability* (whether it is still reachable from reference roots); there is no guarantee of immediate collection when a statement block ends.

**Important rule:** Going out of a variable's name scope **does not mean** the object it pointed to has been destroyed; and remaining within syntactic scope **does not mean** the object's state must persist until the end of the scope in a fixed memory layout.

Example snippet placed inside a method:

```java
{
    int count = 5;
    System.out.println(count); // Allowed: count is in scope
}
// System.out.println(count); // COMPILE ERROR: name count is not visible
```

Outside the `{}` block, the name `count` is no longer in scope; the compiler rejects using that name. There is no need to observe how the JVM allocates or frees memory to conclude that error.

## 2. Variable kinds and the meaning of scope/lifetime

| Variable kind | Where declared and name scope | Lifetime of the variable entity |
| --- | --- | --- |
| **Local variable (local)** | Inside a statement block, method body, loop, or corresponding block per language rules | Tied to the execution of the code segment and its corresponding execution scopes; each method invocation has its own local variables |
| **Method/constructor parameter** | Inside the body of the declared method/constructor, with corresponding scope rules | Separate parameter variable for each invocation |
| **Instance field** (non-`static`) | Member of the class, accessed via `this`/object reference per access rules | Part of each object's state; exists from when the object is created until the object no longer exists |
| **`static` field** | Member of the class, accessed per member and access rules | One copy per class definition in a runtime class loader; tied to the loaded/initialized class lifecycle, not to individual instances |

This table describes the programming-language model; it does **not** assert that every local variable must physically reside on the stack or that every object must reside in a specific memory region. The JVM/JIT may optimize layout and storage while preserving Java semantics.

**Example distinguishing instance from `static`:**

```java
class Counter {
    static int totalCreated;
    int value;

    Counter(int value) {
        this.value = value;
        totalCreated++;
    }
}
```

Two `Counter` objects have two independent `value` fields, whereas `Counter.totalCreated` is shared within the same runtime class. The scope of the name `value` in the class and the lifetime of the `value` state in each object are two different issues.

### When a method runs multiple times

```java
static int square(int n) {
    int result = n * n;
    return result;
}
```

Each call to `square` creates a separate execution context for parameter `n` and local variable `result`. Nested/recursive calls do not share a single local variable, even though in source code they share the name `result`. After `return`, the caller receives the **return value**, rather than continuing to access the variable `result` by name.

## 3. Variable name scope in blocks and loops

The basic rule is that a local name can be referenced from its declaration to the end of the appropriate block; a variable declared in a `for` initializer has scope only within the `for` statement:

~~~java
for (int i = 0; i < 2; i++) {
    int square = i * i;
    System.out.println(square); // 0, then 1
}
// i and square are no longer in scope here.
~~~

This is a **source code** rule; it does not indicate GC timing or how the JVM physically lays out variables. In the loop, `i` persists across index updates, while the initializer expression for `square` is executed anew each time the loop body is entered. Another method call creates a different local context, even if they share the same name in source.

Two sibling blocks can use the same local name because their scopes do not overlap; a nested block cannot redeclare a local/parameter name already in scope from an enclosing block. To understand exact duplicate-declaration errors, see the lesson on *duplicate local variable names*. Here we focus on a different question: **when the name can no longer be referenced, do the reference value and the object continue to exist?**

## 4. Reference variable leaves scope, but the object still exists

Consider a method that creates an array and returns it:

```java
static int[] createValues() {
    int[] numbers = {3, 6, 9};
    return numbers;
}

int[] received = createValues();
System.out.println(received[1]); // 6
```

At the end of `createValues()`, the local name `numbers` can no longer be used at the call site; the method execution also ends. **However, the `int[]` array object can still be accessed via the `received` variable**, because the method returned the reference value pointing to that same array.

Similarly, an object can continue to exist when a reference to it is stored in a field, another array element, or a live data structure. The lifetime of an **object** is not bound by the scope of **an initial local variable**.

Conversely, while a reference variable is still in scope, you should not infer that the old object is still needed after a reassignment:

```java
StringBuilder builder = new StringBuilder("old");
builder = new StringBuilder("new");
```

The variable `builder` is still usable, but it no longer points to the `StringBuilder("old")` object. If no other live references point to the old object, that object **may become eligible for garbage collection**. When the JVM actually collects it is unspecified, and `System.gc()` should not be used to infer a precise lifetime.

## 5. Lambdas and capturing local values (*capture*)

A lambda can use a local variable from an enclosing scope when that variable is `final` or **effectively final** (assigned at most once and never reassigned). This does not turn Java into a pass-by-reference language: the lambda holds the value needed to execute the behavior later.

```java
static Runnable makePrinter() {
    String message = "Xin chao";
    return () -> System.out.println(message);
}

Runnable printer = makePrinter();
printer.run(); // Xin chao
```

The statement `printer.run()` still executes **after** `makePrinter()` has returned and the name `message` no longer exists in the earlier execution context. The lambda retains the data needed to use `message`; for a reference value, the referenced object can still exist.

You cannot reassign a local variable that has been captured by a lambda:

```java
int count = 2;
Runnable show = () -> System.out.println(count);
// count++; // COMPILE ERROR: count is no longer effectively final
```

If a local variable references a **mutable object**, a lambda can still modify that object's state, provided the captured local variable itself is not reassigned:

```java
int[] counter = {0};
Runnable increase = () -> counter[0]++;
increase.run();
// counter[0] == 1
```

The scope of the name `counter`, the lambda holding the reference value, and the lifetime of the array are **three separate factors**. You should not use a single-element array just to "work around" the effectively final constraint in program design; choose a clearly meaningful state structure when truly needed.

## 6. Standalone Java 17+ program

Create the file **`ScopeLifetimeDemo.java`**:

```java
import java.util.Arrays;

public class ScopeLifetimeDemo {
    private static int created;
    private int value;

    public ScopeLifetimeDemo(int value) {
        this.value = value;
        created++;
    }

    static int calculate(int input) {
        int result;
        {
            int temp = input * 2;
            result = temp + 1;
            System.out.println("Khoi mot: " + temp);
        }
        {
            int temp = input + 10; // Name temp is reused
            System.out.println("Khoi hai: " + temp);
        }
        return result;
    }

    static int[] makeArray() {
        int[] localArray = {3, 6, 9};
        return localArray; // Reference escapes the method
    }

    static Runnable makePrinter() {
        String message = "Hello";
        return () -> System.out.println("Lambda: " + message);
    }

    public static void main(String[] args) {
        int outer = 5;
        {
            int inside = outer * 2;
            System.out.println("Trong khoi: " + inside);
        }
        System.out.println("Ngoai khoi: " + outer);

        int answer = calculate(4);
        System.out.println("Ket qua: " + answer);

        ScopeLifetimeDemo object = new ScopeLifetimeDemo(12);
        System.out.println("Instance field: " + object.value);
        System.out.println("Static field: " + ScopeLifetimeDemo.created);

        int[] returned = makeArray();
        System.out.println("Mang sau return: " + Arrays.toString(returned));

        Runnable action = makePrinter();
        action.run();

        for (int i = 0; i < 2; i++) {
            System.out.println("Lap: " + i);
        }
    }
}
```

In the directory containing the file, using JDK 17 or later on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 ScopeLifetimeDemo.java
java ScopeLifetimeDemo
```

**Exact** stdout output (successful compilation prints no lines):

```text
Trong khoi: 10
Ngoai khoi: 5
Khoi mot: 8
Khoi hai: 14
Ket qua: 9
Instance field: 12
Static field: 1
Mang sau return: [3, 6, 9]
Lambda: Hello
Lap: 0
Lap: 1
```

Output explanation:

1. `inside` can only be referenced by name inside the block, while `outer` remains usable after that block.
2. The two `temp` variables in the two sibling blocks are valid despite having the same name. `result` is declared outside both blocks, so it can receive the value inside a block and then be returned.
3. `object.value` is an instance field of the `ScopeLifetimeDemo` object, whereas `created` is a `static` field of the class.
4. The array created in `makeArray()` is still usable after the method finishes because the reference value is returned.
5. The lambda returned from `makePrinter()` still prints `Hello`; this **does not mean** the local `message` is still accessible by name from `main`.
6. The `for` counter variable `i` can be used inside the loop, but cannot be referenced by name outside the loop.

## 7. Field lifetimes and practical notes

### Instance fields

When creating an object, instance state is initialized according to Java rules. Each object has its own instance fields; fields are kept as part of the object's state while the object exists. A method can finish while the object continues to be accessed via another object's field, a returned variable, or another reference.

### `static` fields

A `static` field belongs to the class at runtime, not to individual objects. Initialization of `static` fields happens according to the class initialization mechanism; method calls or creating additional instances do not create a new static copy per instance. Do not oversimplify this as "static fields live until the computer shuts down": class and class loader lifetimes can end when runtime conditions allow.

### GC and `null`

- `reference = null` only **changes the value of a reference variable**; it does not directly delete the object.
- The object may still be referenced from elsewhere; even when it is no longer reachable, the exact time GC collects it is indeterminate.
- A local variable going out of scope is not a **destructor** and does not force the JVM to invoke cleanup.
- For resources such as files, sockets, and database connections, you must actively close them properly; prefer `try-with-resources` for `AutoCloseable` objects rather than waiting for GC.

## 8. Common misconceptions to avoid

| Statement | Assessment | Why? |
| --- | --- | --- |
| "Not being able to reference a variable name after `}` means the object it held has been destroyed." | False | Name scope and object reachability are independent. |
| "Local variables in a method are shared across invocations." | False | Each execution has its own local variables and parameters, even in recursion. |
| "A returned array is lost because the original local variable ends." | False | The returned reference value keeps the array accessible. |
| "`static` creates one copy of a value per object." | False | A `static` field is tied to the class at runtime. |
| "Calling `System.gc()` guarantees immediate collection of an object." | False | There is no guarantee of immediate collection. |
| "A lambda can retain a local value to run after the enclosing method finishes." | True | Capture rules for final/effectively final variables allow this behavior. |

**Key Takeaway:** *Scope answers "where in code can this variable name be written?"; lifetime answers "until when does a variable/object entity exist at runtime?"*. To understand Java accurately, keep distinguishing **the variable holding a reference value** from **the object that value points to**.
