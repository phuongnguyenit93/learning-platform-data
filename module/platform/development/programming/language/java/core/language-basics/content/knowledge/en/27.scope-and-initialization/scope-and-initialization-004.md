# Parameters or Local Variables Shadowing Fields in Java

> **Java core — language-basics / Scope and Initialization**  
> **Environment:** JDK 17+, single standalone file, no external libraries.  
> **Objective:** Recognize *shadowing* when a parameter/local variable shares a name with a field, use `this.field` or `ClassName.staticField` to select the right target to access, and avoid confusing this with duplicate declaration of two local variables.

## 1. What is *field shadowing*?

A class can declare a field and a method can declare a **parameter or local variable with the same name**. Within the scope of the local variable/parameter, an unqualified name typically resolves to the **closer** declaration, causing the field to be shadowed:

~~~java
public final class Sample {
    private int score = 10;

    public void show() {
        int score = 3; // Local score shadows field score.
        System.out.println(score);      // 3: local.
        System.out.println(this.score); // 10: field.
    }
}
~~~

Both entities still exist separately. Shadowing does not delete the field, does not change the field's type, and does not automatically transfer data between the field and the local variable.

- `score`: simple name, resolved to the local `score` in method `show`.
- `this.score`: explicitly accesses the instance field `score` of **the object invoking** `show`.
- After leaving the local scope, the unshadowed field name can be used in an appropriate instance context.

**Distinction:** A local variable shadowing a **field** is valid; however, declaring a new local with the same name as a local or parameter still in an overlapping scope is normally a **compile error**.

## 2. Parameter matching field name: constructor and setter examples

A very common pattern in Java:

~~~java
public final class Student {
    private String name;
    private int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

In constructor `Student(String name, int age)`:

| Expression | Referenced target |
| --- | --- |
| `name` | Constructor parameter `name` |
| `this.name` | Field `name` belonging to the current object |
| `age` | Parameter `age` |
| `this.age` | Field `age` belonging to the current object |
| `this.age = age` | Assigns the **parameter value** into the **instance field** |

`this` is a reference to the current object inside a constructor and instance method. If you name the parameter differently from the field (`studentName`), you can write `name = studentName;` when no local shadows `name`; however, `this.name = studentName;` is often clearer.

A constructor has no return type, whereas a setter like `setAge` is a method returning `void`. Both can take parameters matching field names.

## 3. Easy-to-miss bug: `value = value` only self-assigns the parameter

~~~java
public final class Counter {
    private int value; // Defaults to 0.

    public void wrongSet(int value) {
        value = value; // Only self-assigns the parameter, DOES NOT modify the field.
    }

    public void correctSet(int value) {
        this.value = value; // Modifies the field.
    }

    public int current() {
        return value; // No local value, so reads the field.
    }
}
~~~

If you create `Counter counter = new Counter();` and call `counter.wrongSet(7)`, `counter.current()` still equals 0. Only after `counter.correctSet(7)` does the result become 7.

**Why doesn't Java report an error?** The statement `value = value` is syntactically valid: both names resolve to the local parameter, so it is a legal assignment that does not have the intended effect. Many IDEs or static analyzers can warn about this kind of self-assignment.

You should not work around this by turning all fields into `static`; use the `this` reference properly or rename the parameter appropriately.

## 4. Local variables can also shadow fields

Shadowing does not occur only in parameter lists:

~~~java
public final class Gauge {
    private int level = 20;

    public void inspect() {
        int level = 5;
        System.out.println("local=" + level);      // local=5
        System.out.println("field=" + this.level); // field=20
        this.level += level;
        System.out.println("updated=" + this.level); // updated=25
    }
}
~~~

Here the local `level` and field `this.level` values are independent. The statement `this.level += level` uses both in a single expression to update the field.

With a local matching a field name placed in an **inner block**, the local name is in effect in the appropriate region:

~~~java
class Example {
    private int total = 100;

    void run() {
        System.out.println(total); // 100.
        {
            int total = 7;
            System.out.println(total);      // 7.
            System.out.println(this.total); // 100.
        }
        System.out.println(total); // 100: the local inside the block is out of scope.
    }
}
~~~

The block's local `total` exists in terms of name scope only from its declaration to the end of the block. **The field remains an object field** and is not deleted when the local enters or leaves scope.

## 5. `static` fields: use the class name to avoid ambiguity

A `static` field belongs to the class, not to an individual instance's state. If a local or parameter shares a name with a static field, use `ClassName.field`:

~~~java
public final class AppSettings {
    private static String mode = "DEFAULT";

    public static void setMode(String mode) {
        AppSettings.mode = mode;
    }

    public static void show(String mode) {
        System.out.println("parameter=" + mode);
        System.out.println("classField=" + AppSettings.mode);
    }
}
~~~

`AppSettings.mode = mode` updates the class field with the parameter value; `mode = mode` only self-assigns the parameter.

In a `static` method **there is no `this`**, so `this.mode` is a compile error. If an instance field is needed from a static method, you must have an appropriate object and access it through that reference (subject to Java access rules).

An instance method can still access a static field, but it is good practice to use the class name so readers know it is shared state. A static field can be modified from other calls; a shadowing local does not create a copy of the static field.

## 6. Distinguishing shadowing from duplicate local names and missing assignment

Three situations that are often confused yet have different compilation outcomes:

| Situation | Outcome |
| --- | --- |
| `private int count;` and a method receiving `int count` | Valid: parameter shadows field; use `this.count` to read/write the field |
| Method receiving `int count` and also declaring `int count` in an inner block | Invalid: the parameter name is still in scope |
| `int count;` in a method body and reading it immediately | Invalid: the local is not yet *definitely assigned* |

An `int` field receives a default value of 0 when the object is created; a local `int` does not automatically receive a default value. Shadowing only changes how **names are resolved**; it does not change the initialization rules of the two variable kinds.

## 7. Design guidelines to reduce confusion

Using parameter names identical to field names (such as `this.name = name`) is idiomatic Java, but you should keep code readable:

- In constructors/setters, consistently use `this.field = field` when names match.
- Use `Type.staticField` to access class state; do not assume `this` exists in static methods.
- Avoid naming locals the same as fields in overly long blocks if it forces readers to constantly distinguish `value` from `this.value`.
- Consider `final` for parameters/locals that do not need reassignment. `final` prevents changing the variable's value per Java rules, but it **does not** resolve shadowing or make a mutable object immutable.
- Use getters or domain-meaningful update methods if modifying a field requires validation, instead of allowing direct modification everywhere.
- When reading errors or investigating bugs, clearly identify whether each name refers to a **local**, **parameter**, **instance field**, or **static field**.

Example of accessing an instance field from static via a passed object:

~~~java
static int readCount(Counter counter) {
    return counter.current();
}
~~~

These choices make code easier to maintain; the `this` keyword itself does not make an assignment business-correct if the condition or passed value is already wrong.

## 8. Standalone Java 17+ program

Create the file **FieldShadowingDemo.java**:

~~~java
public final class FieldShadowingDemo {
    private static String status = "READY";

    private final String name;
    private int count; // Defaults to 0.

    public FieldShadowingDemo(String name) {
        this.name = name;
    }

    private void wrongSet(int count) {
        count = count; // Only self-assigns the parameter.
    }

    private void setCount(int count) {
        this.count = count;
    }

    private void increase(int count) {
        this.count += count;
    }

    private void showLocal() {
        int count = 100;
        System.out.println("localCount=" + count);
        System.out.println("fieldCount=" + this.count);
    }

    private void showName() {
        String name = "Temporary";
        System.out.println("localName=" + name);
        System.out.println("instanceName=" + this.name);
    }

    private void showBlock() {
        String status = "BLOCK";
        System.out.println("blockStatus=" + status);
        System.out.println("classStatus=" + FieldShadowingDemo.status);
    }

    private static String statusPair(String status) {
        return status + "/" + FieldShadowingDemo.status;
    }

    private static void changeStatus(String status) {
        FieldShadowingDemo.status = status;
    }

    private static int readCount(FieldShadowingDemo demo) {
        return demo.count; // Has an object to read the instance field.
    }

    private static int plusOne(int count) {
        return count + 1;
    }

    public static void main(String[] args) {
        FieldShadowingDemo demo = new FieldShadowingDemo("Lan");
        System.out.println("constructorName=" + demo.name);
        System.out.println("defaultCount=" + demo.count);

        demo.wrongSet(8);
        System.out.println("afterWrong=" + demo.count);

        demo.setCount(8);
        System.out.println("afterSetter=" + demo.count);
        demo.showLocal();

        demo.increase(3);
        System.out.println("afterIncrease=" + demo.count);
        demo.showName();

        System.out.println("staticValue=" + FieldShadowingDemo.status);
        System.out.println("statusPair=" + statusPair("LOCAL"));
        changeStatus("ACTIVE");
        System.out.println("newStatus=" + FieldShadowingDemo.status);
        System.out.println("newPair=" + statusPair("PARAM"));

        demo.showBlock();
        System.out.println("afterBlockStatus=" + FieldShadowingDemo.status);
        System.out.println("readInstanceFromStatic=" + readCount(demo));
        System.out.println("methodResult=" + plusOne(4));

        {
            int temporary = 2;
            System.out.println("siblingOne=" + temporary);
        }
        {
            int temporary = 3;
            System.out.println("siblingTwo=" + temporary);
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

**Exact expected stdout:**

~~~text
constructorName=Lan
defaultCount=0
afterWrong=0
afterSetter=8
localCount=100
fieldCount=8
afterIncrease=11
localName=Temporary
instanceName=Lan
staticValue=READY
statusPair=LOCAL/READY
newStatus=ACTIVE
newPair=PARAM/ACTIVE
blockStatus=BLOCK
classStatus=ACTIVE
afterBlockStatus=ACTIVE
readInstanceFromStatic=11
methodResult=5
siblingOne=2
siblingTwo=3
~~~

`afterWrong=0` shows that self-assigning the parameter does not update the field; `afterSetter=8` and `afterIncrease=11` are two proper field updates via `this.count`. `localName`/`instanceName` distinguish local and field, while `statusPair`/`newPair` demonstrate that a parameter matching a static field name can still be distinguished via the class name.

## 9. Checklist and exercises

| Situation | What to do? |
| --- | --- |
| Constructor takes `String name` and class has field `name` | Use `this.name = name;` |
| Setter only writes `value = value;` | Recheck: usually a parameter self-assignment bug |
| Local `count` matches field `count` | Use `count` for local, `this.count` for field |
| Parameter `mode` matches static field `mode` | Use `ClassName.mode` when the field is needed |
| Using `this` in a static method | Invalid; use the class name or an object reference |
| New local matching parameter in an inner block | Duplicate declaration error, not field shadowing |
| Reading an unassigned local | Fails definite assignment even though the name is in scope |
| Two sibling blocks both using name `temp` | Valid when the two scopes do not overlap |

**Exercise 1.** Write a class `Account` with field `balance` and setter `setBalance(int balance)`. Predict the state with `balance = balance;`, then fix it with `this.balance = balance;`.

**Exercise 2.** Create a method with a local matching a field name, printing both `name` and `this.name`. What changes when the local leaves its block?

**Exercise 3.** Declare `static int limit` and method `static void change(int limit)`. Why doesn't `limit = limit;` update the field? Fix it using the class name.

**Exercise 4.** Try declaring local `int count` inside a method that already takes parameter `int count`; explain the compile error, then move that local into a sibling block with non-overlapping scope.

**Exercise 5.** Distinguish an explicitly unassigned field `int value;` from an unassigned local `int value;`. Which variable can be read immediately and why?

### Key Takeaway

**Parameters/local variables can shadow a field with the same name without deleting the field.** In an instance method/constructor, use `this.field` to access the right field; in a static context, use `ClassName.staticField`. Avoid the `value = value` bug, distinguish valid field shadowing from invalid overlapping local-local declarations, and remember that scope does not replace definite assignment checks.
