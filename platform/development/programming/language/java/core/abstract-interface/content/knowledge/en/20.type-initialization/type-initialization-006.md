# Example of Tracing Initialization Order with Execution Traces

When reading a Java program with inheritance, multiple initializer blocks, and constructors, do not guess the order solely from where `new` is called. Track **class initialization** and **instance initialization** separately, and record each statement with an observable effect, such as `System.out.println`.

This lesson uses a small program with a parent class `Parent` and a child class `Child`. Each initializer block or field initializer prints a trace. Running the program will show why the first object creation includes static traces as well, while the second creation only has instance traces.

## 1. Rules to Use When Tracing

1. **Initialize the parent class before the child class.** Before a class is initialized, its direct superclass must be initialized first.
2. **Static field initializers and static blocks run in textual order within each class.** They run during class initialization, usually triggered by the first active use, such as creating an object with `new` or calling a static method. Class loading does not mean that the initializers have already run.
3. **Static initialization runs once per initialized class in a class loader.** Creating additional objects of the same class does not re-run static blocks or static field initializers.
4. **For each object, the parent class's instance initialization occurs before the child class's instance part.** Within each class, field initializers and instance initializer blocks run in the order they appear in the source code.
5. **The constructor body runs after the initializers of its corresponding class.** The child class constructor calls the parent class constructor before the rest of the child class constructor body runs. If no explicit call is written, Java inserts a `super()` call when valid.

These rules are enough to solve the problem by dividing the traces into two groups: static events that occur when the class is initialized, and instance events that occur each time an object is created.

## 2. Complete Java Program

Save all the code below into the file `InitTraceDemo.java`. The order of the fields and blocks is intentionally arranged so that we can observe textual order.

```java
class Parent {
    static {
        System.out.println("1. Parent: static block");
    }

    private static final String STATIC_VALUE =
            log("2. Parent: static field initializer");

    private final String instanceValue =
            log("5. Parent: instance field initializer");

    {
        System.out.println("6. Parent: instance initializer block");
    }

    Parent() {
        System.out.println("7. Parent: constructor body");
    }

    private static String log(String message) {
        System.out.println(message);
        return message;
    }
}

class Child extends Parent {
    static {
        System.out.println("3. Child: static block");
    }

    private static final String STATIC_VALUE =
            log("4. Child: static field initializer");

    private final String instanceValue =
            log("8. Child: instance field initializer");

    {
        System.out.println("9. Child: instance initializer block");
    }

    Child() {
        System.out.println("10. Child: constructor body");
    }

    private static String log(String message) {
        System.out.println(message);
        return message;
    }
}

public class InitTraceDemo {
    public static void main(String[] args) {
        System.out.println("=== first object ===");
        new Child();

        System.out.println("=== second object ===");
        new Child();
    }
}
```

Compile and run with Java 17 or later:

```text
javac InitTraceDemo.java
java InitTraceDemo
```

## 3. Exact Output

```text
=== first object ===
1. Parent: static block
2. Parent: static field initializer
3. Child: static block
4. Child: static field initializer
5. Parent: instance field initializer
6. Parent: instance initializer block
7. Parent: constructor body
8. Child: instance field initializer
9. Child: instance initializer block
10. Child: constructor body
=== second object ===
5. Parent: instance field initializer
6. Parent: instance initializer block
7. Parent: constructor body
8. Child: instance field initializer
9. Child: instance initializer block
10. Child: constructor body
```

## 4. Reading the Trace Stage by Stage

| Trace | What Just Happened | Reason |
|---|---|---|
| 1 | Static block of `Parent` | The parent class is initialized before the child class. |
| 2 | Static field initializer of `Parent` | It comes after the static block in the source code of `Parent`. |
| 3 | Static block of `Child` | After `Parent` has finished initializing, `Child` then proceeds to initialize. |
| 4 | Static field initializer of `Child` | It comes after the static block in the source code of `Child`. |
| 5–7 | Instance field, instance block, then constructor of `Parent` | The parent class's instance initialization completes before the parent class's constructor. |
| 8–10 | Instance field, instance block, then constructor of `Child` | Only after the parent class constructor completes do the child class's instance initialization and constructor run. |

The numbers in the messages are labels for easy cross-referencing, not sequence numbers automatically generated by the JVM. The traces are printed by statements in the program.

### Why does the second object creation not print lines 1–4?

The static initializers already ran during the first class initialization. The second `new Child()` statement still initializes a new object, so the field initializers and instance initializer blocks of both `Parent` and `Child` continue to run. However, the classes have already been initialized, so the static initializers do not run again.

### Why does the parent class constructor appear before the child class initializers?

The child class constructor must call the parent class constructor. During that process, Java initializes the parent class's instance part and executes the parent class constructor first. When the parent class constructor returns, Java continues with the child class's field initializers and instance initializer blocks, and then runs the child class constructor body.

## 5. Process for Solving Trace Problems Yourself

When encountering a problem that asks you to predict initialization-order output, follow this process:

1. **Pinpoint the class used first.** Determine which action triggers class initialization, such as `new Child()` or calling a static method.
2. **List the classes by inheritance relationship.** Write the parent class first and the child class second.
3. **For each class, scan static members from top to bottom.** Record each static field initializer and static block in the exact order they appear.
4. **Trace a single object.** Start from the parent class's instance initialization; within each class, scan field initializers and instance blocks in textual order, then record the constructor body.
5. **Mark the traces that occur only once.** Static initializers belong to class initialization; instance initializers and constructors belong to each object creation.
6. **Cross-check the output line by line.** Do not reorder lines yourself based on the meaning of variable names or the position of `new`; the order must be derived from Java's rules and the source code.

A scratch table can include three columns: line number, the statement that produces the trace, and the reason it runs at that moment. This approach is especially useful when there are multiple parent classes, multiple initializers, or multiple object creations.

## 6. Common Misconceptions

- **Thinking static initializers run every time an object is created:** wrong; they run when the class is initialized and do not re-run for each instance.
- **Assuming all static members of the child class run before those of the parent class:** wrong; the parent class is initialized before the child class.
- **Grouping field initializers and initializer blocks into two separate groups:** wrong; within the same class, these two kinds are interleaved in the exact declaration order in the source code.
- **Putting the child class constructor before the parent class constructor:** wrong; the parent class constructor call completes before the remaining body of the child class constructor executes.
- **Equating class loading with class initialization:** these are two different steps. When predicting output, you need to determine when class initialization is actually triggered.
- **Forgetting that each `new` creates new instance state:** instance fields are re-initialized for each object, even when static state remains unchanged.
- **Reading the label numbers as if they were automatic output:** the numbers in the example are written inside the message strings. If you change the source code, you must predict based on the actual statements.

## 7. Extending When the Trace Is More Complex

If a constructor uses `this(...)` to call another constructor in the same class, follow the call chain to the constructor that makes the `super(...)` call. The object's instance initialization runs only once in that constructor chain; do not add an extra pass of field initializers for each constructor called via `this(...)`.

If a static initializer calls another method or creates another object, trace the nested call right at that point. Do not move the trace of the nested call to the bottom of the table: it appears immediately when the calling statement is executed. Also note that an error during class initialization can cause the initialization to fail; subsequent uses may receive a class initialization error instead of running the initializers normally again.

To test yourself, change the position of a static block or an instance block, add a `new Child()` line, and predict the output before running it again. If the output differs from your prediction, compare each line against the declaration order and constructor call chain rather than only looking at the final result.
