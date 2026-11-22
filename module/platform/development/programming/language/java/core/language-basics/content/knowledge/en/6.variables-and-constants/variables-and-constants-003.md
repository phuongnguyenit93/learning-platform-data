# Distinguishing Local Variables, Parameters, and Fields in Java 17+

In Java, three declarations can all use type `int` yet serve very different roles:

- **Local variable:** declared inside the body of a method, constructor, or block; used for temporary calculations within that scope.
- **Parameter:** a variable declared in the parameter list of a method/constructor; receives a value passed by the caller.
- **Field:** a variable declared at class or interface level, outside methods; represents **object** state or **class-level** data if marked `static`.

Understanding where each is declared, its scope, and how it is initialized helps prevent `cannot find symbol`, `variable might not have been initialized`, and mixing up data between objects.

## 1. Quick Identification by Declaration Location

~~~java
public class Example {
    private int balance;             // Instance field.
    private static int accountCount; // Static field.

    public Example(int initial) {    // initial: constructor parameter.
        int checked = initial >= 0 ? initial : 0; // Local variable.
        this.balance = checked;      // Assigns to the object's field.
        accountCount++;
    }

    public int increase(int amount) { // amount: method parameter.
        int next = balance + amount;  // next: local variable.
        balance = next;               // Updates the instance field.
        return balance;
    }
}
~~~

| Criterion | Local variable | Parameter | Instance field | `static` field |
| --- | --- | --- | --- | --- |
| Where is it declared? | Inside a method, constructor, or block | Parameter list | In the class body, without `static` | In the class body, with `static` |
| Who does it belong to? | One execution / appropriate scope | One method/constructor call | Each object has its own copy | Tied to the class in the class-loading context |
| Has automatic default value? | **No** | No; receives value when called | **Yes** | **Yes** |
| Accessible in what scope? | Declaration scope and control-flow rules | Inside the corresponding declaration body | Via an object or `this` | Via class name, e.g., `Example.accountCount` |
| Typically used for | Temporary computation results | Operation input | Per-object state | Object counters, shared configuration |

A parameter in Java is still a **variable**, but it differs from a self-declared local variable in that **its initial value is supplied by the caller**. Saying "parameters are local variables" can be valid under a broad interpretation of usage region, but when classifying by **declaration location**, it is better to separate them.

## 2. Runnable Java Program

Save the UTF-8 file **`VariableKindsDemo.java`**:

~~~java
public class VariableKindsDemo {
    private static int accountCount;  // Static field: initially = 0.

    private final String owner;        // Instance field.
    private int balance;               // Instance field: initially = 0.
    private boolean active;            // Instance field: initially = false.

    public VariableKindsDemo(String owner) {
        this.owner = owner;            // Field = parameter with same name.
        accountCount++;
    }

    public void deposit(int amount) {  // amount: parameter.
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int before = balance;          // Local variable.
        balance += amount;             // Update instance field.
        System.out.println(owner + ": " + before + " -> " + balance);
    }

    public static void main(String[] args) {
        int startingAmount = 50;       // Local variable of main.

        VariableKindsDemo mai = new VariableKindsDemo("Mai");
        VariableKindsDemo an = new VariableKindsDemo("An");

        System.out.println("accounts=" + accountCount);
        System.out.println("mai.initialBalance=" + mai.balance);
        System.out.println("mai.initialActive=" + mai.active);

        mai.deposit(startingAmount);
        an.deposit(20);

        System.out.println("mai.finalBalance=" + mai.balance);
        System.out.println("an.finalBalance=" + an.balance);
        System.out.println(
                "accounts.shared=" + VariableKindsDemo.accountCount);
    }
}
~~~

Open **PowerShell on Windows** or **Bash on Linux** in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 VariableKindsDemo.java
java VariableKindsDemo
~~~

**Expected output:**

~~~text
accounts=2
mai.initialBalance=0
mai.initialActive=false
Mai: 0 -> 50
An: 0 -> 20
mai.finalBalance=50
an.finalBalance=20
accounts.shared=2
~~~

Why?

1. `accountCount` is a **static field**, incremented every time the constructor runs; two objects were created so the result is `2`, whether read via `accountCount` or `VariableKindsDemo.accountCount`.
2. `balance` and `active` are **instance fields** with no explicit initializer: Java sets default values `0` and `false` for each object.
3. `owner` is also an instance field, assigned in the constructor. The `owner` parameter is only used to supply the value for the `this.owner` field.
4. `startingAmount` is a local variable of `main`; `mai.deposit(startingAmount)` passes the value `50` into the `amount` parameter of `deposit`.
5. `before` is a local variable **separate for each call to `deposit`**. Mai's `balance` field changes to `50`, while An's changes to `20`: two objects do not share instance fields.

`main` is a `static` method: there you **cannot access `balance` directly** without going through an object (for example `mai.balance`). Conversely, instance methods like `deposit` can access instance fields via the implicit `this`.


## 3. Initialization by Variable Kind

**Fields** have default values according to their type (`int` is `0`, `boolean` is `false`, references are `null`), though field initializers and constructors can change those values. **Parameters** receive argument values from the call. **Local variables** have no readable default value; they must be definitely assigned before reading.

~~~java
class ExampleState {
    int count; // 0 when a new object is created

    int sum(int input) { // input is a parameter that already received a value from the caller
        int result = count + input; // result is an initialized local
        return result;
    }
}
~~~

An uninitialized `final` instance field must be validly assigned before the constructor completes normally, such as `owner` in the main example. The lesson on default values fully explains array types, `char`, wrappers, and initialization order; the lesson on *definite assignment* analyzes control-flow branches.

## 4. Scope and Shadowing

A local variable or parameter can **shadow** a field with the same name. In the example:

~~~java
private final String owner;

public VariableKindsDemo(String owner) {
    this.owner = owner;
}
~~~

- `owner` on the right is the constructor **parameter**.
- `this.owner` on the left is the current object's **field**.

If you just wrote `owner = owner;`, both sides would refer to the parameter, leaving the field unassigned; for an uninitialized `final` field, the constructor would also violate the mandatory assignment requirement.

**Block scope:** a variable declared inside `{ ... }` cannot be used outside its scope:

~~~java
if (true) {
    int inside = 10;
    System.out.println(inside);
}
// System.out.println(inside); // Error: cannot find symbol inside.
~~~

It is not just indentation: **braces and declaration position** determine the valid scope. Two local variables with the same name in nested scopes also cannot be arbitrarily declared overlapping one another; when unsure, use descriptive names instead of trying to reuse names.

## 5. Parameter Passing in Java Is Pass-by-Value

Java **always passes values** into parameters:

~~~java
static void changeNumber(int value) {
    value = 99; // Only modifies the parameter variable.
}

// In main:
int number = 5;
changeNumber(number);
System.out.println(number); // 5
~~~

For primitive types, the numeric value is copied. For objects, the **reference value** is copied; the method can modify the shared object's state through that reference (if the object allows it), but reassigning the parameter variable does not change the reference in the caller's variable.

Do not turn "parameters are stored on the stack, fields are stored on the heap" into an absolute physical rule: memory optimization is a JVM implementation detail. When learning the language, **semantics, scope, and state sharing** matter more.

## 6. Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `variable might not have been initialized` | Reading a local variable before definite assignment | Assign a value on all necessary branches |
| `cannot find symbol` for a variable | Used out of scope or misspelled name | Check declaration location and `{ }` pairs |
| `non-static variable ... cannot be referenced from a static context` | Reading an instance field directly in `main` | Create/receive an object and access through it |
| Field unchanged after constructor | Parameter shadows field name, wrote `owner = owner` | Write `this.owner = owner` |
| Two objects unexpectedly share a value | Used `static` for data that should belong to each object | Remove `static` for per-object state |
| Field is always `0` or `null` | Forgot to initialize or assigned the wrong field | Check constructors and initializers |
| Reassigning parameter does not change caller | Java passes argument values | Return the result and assign at the caller if needed |

## 7. Self-Check Exercises

1. **Classification:** In `VariableKindsDemo`, which category do `accountCount`, `owner`, `balance`, `startingAmount`, `amount`, and `before` belong to?  
   *Answer:* `accountCount` is a static field; `owner` and `balance` are instance fields; `startingAmount` and `before` are local variables; `amount` is a parameter. There is also the constructor parameter `owner` shadowing the field name.
2. **Prediction:** If `mai.deposit(10)` is called once more, what are `mai.balance` and `an.balance`?  
   *Answer:* `60` and `20`. `accountCount` remains `2` because no new object was created.
3. **Initialization:** Why does `int balance;` at class level read as `0`, while `int local; System.out.println(local);` inside a method does not compile?  
   *Answer:* Fields receive default values; locals must be definitely assigned.
4. **Shadowing:** Explain the difference between `this.owner = owner;` and `owner = owner;` in the constructor.  
   *Answer:* The first assigns the parameter to the field; the second only assigns the parameter to itself.
5. **Pass-by-value:** Why does changing the `value` parameter in `changeNumber` not change the `number` variable at the caller?  
   *Answer:* The parameter holds a copy of the numeric value.

## Checklist

- [ ] Identify **local variables**, **parameters**, **instance fields**, and **static fields** by declaration location.
- [ ] Know that fields have default values whereas local variables do not.
- [ ] Use `this.field` to resolve names shadowed by parameters or local variables.
- [ ] Do not use a local variable outside its block scope.
- [ ] Understand that instance fields belong to each object and static fields are shared at class level.
- [ ] Explain how Java passes values into parameters.
- [ ] Compile and run `VariableKindsDemo.java`, accurately predicting all eight lines of output.

**Takeaway:** Local variables serve a block of computation, parameters carry call data, and fields store object or class state. Ask three questions whenever you see a variable name: **Where is it declared? Who owns that value? And when is it assigned?**
