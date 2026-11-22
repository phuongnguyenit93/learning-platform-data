# Captured variables and the effectively final rule

In Java, lambda expressions and local classes or anonymous classes can use variables declared in an outer scope. When such a lambda or class references an outer local variable or parameter, that variable is called a **captured variable**. A captured local variable must be declared with `final` or be **effectively final**.

This rule commonly appears when writing callbacks, processing collections with Streams, creating tasks to run later, or defining a class inside a method.

## 1. What does effectively final mean?

A variable is effectively final when it is not declared with the `final` keyword, yet still satisfies the assignment rules of a final variable: after the variable is initialized or first assigned along the control flow, the program does not reassign a value to it. Assignments such as `=`, `+=`, `-=` and increment/decrement operations such as `++`, `--` can all make a variable no longer effectively final.

~~~java
int limit = 10;                 // effectively final
Runnable task = () -> System.out.println(limit);
task.run();
~~~

This code is valid because `limit` is not reassigned after initialization. Adding `final` is not required; the compiler determines that it is effectively final from how the variable is used.

~~~java
final int limit = 10;           // explicitly final
Runnable task = () -> System.out.println(limit);
task.run();
~~~

The code above is also valid. `final` clearly expresses intent and prevents reassignment right at the point of declaration.

A variable without an initial value at its declaration can still be effectively final if it is assigned exactly once on every branch that can reach the point of use:

~~~java
String mode;
if (args.length > 0) {
    mode = "provided";
} else {
    mode = "default";
}

Runnable task = () -> System.out.println(mode);
task.run();
~~~

In each branch, `mode` is assigned only once and already has a value before the lambda uses it. If there is a branch that leaves the variable uninitialized or a subsequent reassignment, the code will no longer satisfy the condition.

## 2. Which variables are subject to this rule?

The rule applies when a lambda, local class, or anonymous class captures a local variable or parameter from an outer scope. Common cases include:

- A local variable declared in a method.
- A method or constructor parameter.
- A parameter of an outer lambda when a nested inner lambda uses it.
- A variable declared in a method and then used in a local class or anonymous class.

Example with a method parameter:

~~~java
static Runnable createPrinter(String message) {
    return () -> System.out.println(message);
}
~~~

`message` is a parameter of `createPrinter`. Because the method does not reassign this parameter, the lambda can capture it. The lambda can be run after `createPrinter` returns; therefore, the local variable does not need to continue existing as an active local variable of the method.

Instance and static fields are not subject to this effectively final requirement. A lambda can read or update a field according to normal access rules. However, the ability to update a field does not automatically guarantee thread safety; if multiple threads access it concurrently, appropriate synchronization design is still required.

## 3. Complete runnable Java example

Save the following code as `EffectivelyFinalDemo.java`. The example shows a lambda capturing an integer variable, an anonymous class capturing a string, and a lambda still being able to mutate the state of the object referenced by an effectively final variable.

~~~java
import java.util.function.IntUnaryOperator;

public class EffectivelyFinalDemo {
    public static void main(String[] args) {
        int multiplier = 3;
        IntUnaryOperator timesMultiplier = value -> value * multiplier;
        System.out.println(timesMultiplier.applyAsInt(4));

        String prefix = "ID-";
        Runnable printId = new Runnable() {
            @Override
            public void run() {
                System.out.println(prefix + 7);
            }
        };
        printId.run();

        int[] counter = {0};
        Runnable increment = () -> counter[0]++;
        increment.run();
        increment.run();
        System.out.println(counter[0]);
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac EffectivelyFinalDemo.java
java EffectivelyFinalDemo
~~~

Exact stdout output:

~~~text
12
ID-7
2
~~~

`multiplier` and `prefix` are captured without being reassigned. The variable `counter` is also effectively final: the reference variable still points to the same array. The statement `counter[0]++` modifies an element of the array and does not reassign the `counter` variable. Therefore, the example is valid and prints `2`.

## 4. Reassigning a variable causes a compile error

Once a local variable is captured by a lambda or nested class, that variable cannot be reassigned, even if the assignment appears after the lambda declaration line:

~~~java
int attempts = 1;
Runnable task = () -> System.out.println(attempts);
attempts = 2; // Compile error: attempts is not effectively final
~~~

The error does not depend on whether the lambda has run yet. The compiler examines all uses of the variable. Compound assignments such as `attempts += 1` and increments such as `attempts++` also violate the rule. How to fix it depends on the intended meaning:

- If the value must remain fixed, remove the reassignment or declare the variable as `final`.
- If each task needs its own value, create a new, effectively final variable for that task.
- If mutable state is needed, consider a stateful object or an appropriate field; synchronization must still be handled if multiple threads are involved.

## 5. Loops and variables captured by lambdas

The counter variable of a classic `for` loop is usually incremented in the loop's update clause, so it is not effectively final:

~~~java
for (int i = 0; i < 3; i++) {
    Runnable task = () -> System.out.println(i); // Compile error
}
~~~

`i++` modifies the variable `i` itself on each iteration. If each lambda needs to use the value of a specific iteration, copy that value into a new variable inside the loop body:

~~~java
for (int i = 0; i < 3; i++) {
    int current = i;
    Runnable task = () -> System.out.println(current);
    task.run();
}
~~~

Output:

~~~text
0
1
2
~~~

Each time the loop body executes, a new `current` variable is initialized. That variable is not reassigned after initialization, so the lambda can capture it. If you move the declaration of `current` outside the loop and reassign it on each iteration, the effectively final issue will reappear.

## 6. Capturing a reference does not mean freezing the object

Effectively final is about **a variable not being reassigned**, not about the object that the variable references being immutable.

~~~java
var names = new java.util.ArrayList<String>();
Runnable task = () -> names.add("Ada");
task.run();
System.out.println(names);
~~~

Output:

~~~text
[Ada]
~~~

`names` still points to the same list, so the reference variable is effectively final. The contents of the list can change through `add`. Similarly, `final List<String> names` prevents assigning a different list to `names`, but does not by itself prevent adding or removing elements.

Three things should be distinguished:

- **Reassigning the variable:** `names = anotherList` changes the reference and violates the effectively final rule if `names` is being captured.
- **Mutating the object:** `names.add("Ada")` keeps the same reference and is allowed.
- **Ensuring thread safety:** effectively final does not make a mutable object thread-safe. Sharing an object across multiple threads still requires considering synchronization, thread-safe data structures, or data ownership.

For primitive types, a lambda receives the value of the variable. For reference variables, the captured value is the reference to the object; the lambda does not receive a deep copy of the entire object.

## 7. Lambdas, local classes, and anonymous classes

The same principle applies when a local class or an anonymous class uses an outer local variable.

~~~java
int base = 10;

class Adder {
    int add(int value) {
        return base + value;
    }
}

Adder adder = new Adder();
System.out.println(adder.add(5));
~~~

`base` must be final or effectively final because the local class `Adder` uses a variable declared in the outer method. The anonymous class in the complete example also captures `prefix` under that same rule.

There is a notable difference regarding `this`: inside a lambda, `this` still refers to the object enclosing the lambda; inside an anonymous class, `this` refers to the anonymous class instance itself. This difference can affect how members are accessed, but it does not change the effectively final rule for captured local variables.

## 8. Common errors and how to handle them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| “must be final or effectively final” error | A local variable is reassigned or incremented/decremented after initialization | Remove the reassignment or use a new variable for each task |
| Reassigned after the lambda line even though the lambda has not run yet | The compiler checks the assignment rules without waiting until runtime | Keep the variable effectively final throughout its entire scope |
| Declared `final`, yet the list can still be modified | `final` locks reassigning the reference, not the state of the object | Use an immutable data type if true immutability is needed |
| The lambda can modify a field, but cannot modify a local variable | Fields and local variables are governed by different rules | Choose where to store state intentionally and handle synchronization when needed |
| Copied the variable, yet still getting an error | The copied variable is also reassigned later, or the copy is declared outside the loop and updated repeatedly | Initialize a separate variable within each task's scope and do not reassign it |

## 9. Checklist when reading or writing code

1. Identify which variables are declared outside the lambda or local/anonymous class but used inside it.
2. Check all paths in the code: is the variable initialized before use, and is it reassigned, incremented, or decremented?
3. If a separate value needs to be kept for each loop iteration, create a new local variable inside the loop body.
4. If only the state of the referenced object is mutated, confirm whether that is intentional and whether it is safe in the execution context.
5. Distinguish the compile-time effectively final rule from immutability and thread safety; these are three different properties.

The effectively final rule helps Java clearly determine which local values can be used by lambdas and local/anonymous classes, even when that action executes after the original method has finished.
