# Forward Reference Restrictions in Java Initializer Expressions and Blocks

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between a field's **name scope** and **when the field receives its initialized value**; understand why a field declared below can be in scope yet still trigger `illegal forward reference`.
- Correctly apply **JLS §8.3.3 — Restrictions on Field References in Initializers** to static field initializers, `static { ... }`, instance field initializers, and instance initializer blocks `{ ... }`.
- Recognize the combined conditions that make a **simple-name read** before a field's declaration or within that field's own initializer a compile-time error.
- Distinguish **reading a value** from **assigning to the left-hand side** of an assignment, as well as `x = 2` from `x += 2` and `x++`.
- Explain why `ClassName.field` or `this.field` can pass the *simple-name forward reference* check, yet still observe the **default value** if the target initializer has not run yet.
- Understand why **calling a method** to read a field declared later is not automatically checked in the same way, yet can lead to incomplete data.
- Predict the order of static and instance initializers, their relationship with constructors, compile-time constant variables, inherited fields, and dependency cycles.
- Rewrite hazardous cases using **ordering dependencies first**, **candidate values**, and clear **factory/constructor** approaches instead of trying to “work around” the compiler.
- Run standalone Java 17+ examples, determine their output, and identify the cause of initialization errors.

## 1. What is a “Forward Reference”?

Consider the following declaration:

~~~java
class Sample {
    int first = later;
    int later = 10;
}
~~~

This is an **intentionally invalid example**, not a runnable program. In `first = later`, the name `later` appears inside an **instance field initializer** to the left of the declaration of field `later`. The Java compiler reports an error like `illegal forward reference`.

Many people think: “Class Sample already has field later, why can't it be used?” You need to distinguish:

1. **Scope:** the name of a member declared in a class has scope across the class body. Simply put, the compiler knows the class has field `later`.
2. **Restrictions on forward references:** Java **prohibits certain forms of premature field reads** directly inside field initializers or initializer blocks belonging to the class itself.
3. **Initialization order:** at runtime, fields hold **default values** before their respective initializers assign the final value; declaration order affects the observed value.

Therefore, “the compiler recognizes that the field exists” **does not mean** “every expression using that field is valid”, and even less does it mean “the field already holds the intended value”.

### 1.1. Two Things to Distinguish

| Scenario | Conclusion |
| --- | --- |
| `int a = b; int b = 10;` in the same class | **Error**: premature read of instance field `b` by simple name |
| `static int a = b; static int b = 10;` in the same class | **Error**: premature read of static field `b` by simple name |
| `int a = this.b; int b = 10;` | May **compile**, but `a` may receive `0` |
| `static int a = Sample.b; static int b = 10;` | May **compile**, but `a` may receive `0` |
| `int a = readB(); int b = 10;`, where method `readB()` returns `b` | May compile; calling it early may return `0` |
| `static { b = 4; } static int b = 10;` | Assigning to `b` is valid, but the subsequent initializer overwrites it with `10` |
| `int a = 10; int b = a;` | Valid: reads a field that appeared earlier |
| Constructor reads a field declared below | Does not fall under the exact `8.3.3` check for field/instance initializers; runtime order still matters |

The table presents **specific usage forms and contexts**. Illustrative snippets marked as errors may not compile; valid cases must still satisfy typing, access, definite assignment, and other Java rules.

## 2. How Does Java Execute Field Initializers and Initializer Blocks?

A class can declare:

- **Static field initializer**: `static int x = expression;`.
- **Static initializer block**: `static { statements; }`.
- **Instance field initializer**: `int y = expression;`.
- **Instance initializer block**: `{ statements; }`.
- **Constructor**: `Sample() { statements; }`.

**Static initializers** are executed at runtime when the class is initialized, in the **order in which they appear in the class body** of that class.

**Instance initializers** are executed when creating an instance, in the **order in which they appear in the class body** of that class, after the constructor invocation to the superclass/target constructor according to Java 17 rules, and before the constructor body of the corresponding class level.

Java does not automatically group all field initializers to run before all initializer blocks: they are **interleaved in textual order** within each static or instance group.

### 2.1. Default Values Before Initializers

An `int` field has a default of `0`, a `boolean` has a default of `false`, and a reference field has a default of `null`. Assignments such as `= 10`, `= true`, and `= new Object()` belong to the corresponding initializer phase.

This is a very important difference compared to local variables. Java does not allow you to read a **local variable that is not definitely assigned**, whereas a field can be read in valid contexts even when its initializer expression has not yet run and currently holds its default value.

### 2.2. First Example: Normal Execution Order

Save **`OrderedInitializersDemo.java`**:

~~~java
public class OrderedInitializersDemo {
    static class Example {
        static int base = trace("static base", 4);

        static {
            System.out.println("static block sees base=" + base);
        }

        static int total = trace("static total", base + 2);

        int id = trace("instance id", 7);

        {
            System.out.println("instance block sees id=" + id);
        }

        int doubled = trace("instance doubled", id * 2);

        Example() {
            System.out.println("constructor doubled=" + doubled);
        }

        static int trace(String label, int value) {
            System.out.println(label + "=" + value);
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        new Example();
        System.out.println("again");
        new Example();
    }
}
~~~

Compile/run using JDK 17 or later:

~~~bash
javac OrderedInitializersDemo.java
java OrderedInitializersDemo
~~~

**Exact stdout:**

~~~text
start
static base=4
static block sees base=4
static total=6
instance id=7
instance block sees id=7
instance doubled=14
constructor doubled=14
again
instance id=7
instance block sees id=7
instance doubled=14
constructor doubled=14
~~~

On the first instance creation, `Example` requires class initialization, so the static group runs first. Each object creation then runs the instance group, followed by the constructor. Each field initializer references fields that have already been initialized **in a clear order**.

**Best practice:** declare fields used as dependencies **before** the fields that consume them, avoiding turning initialization into a hard-to-follow web of relationships.

## 3. JLS §8.3.3 Rules for Static Fields

For a static field `f` declared in class/interface `C`, Java reports a compile-time error for a **reference by simple name** to `f` when **simultaneously**:

1. The reference occurs in a **static field initializer** or **static initializer block** of `C`.
2. The reference is located in **`f`'s own initializer**, or at a source position **before `f`'s declarator**.
3. The reference is **not** on the left-hand side of an assignment expression.
4. The **innermost enclosing class/interface** of the reference is still `C`.

Emphasis on the word **simultaneously**. This is not a rule saying “you may never refer to a field declared later”, but rather a combination of conditions on **field kind**, **location**, **reference form**, and **innermost enclosing class**.

### 3.1. Two Common Error Forms

~~~java
class BadStatic {
    static int first = later + 1; // ERROR: reads later by simple name.
    static int later = 10;
}
~~~

~~~java
class BadStaticBlock {
    static {
        // System.out.println(later); // ERROR if uncommented.
    }

    static int later = 10;
}
~~~

The first snippet intentionally **does not compile**. The second snippet comments out the invalid line to highlight the error point. Do not combine these snippets into the same source file intended to run as a complete demo.

### 3.2. Reading After the Declarator Is Generally Valid

~~~java
class GoodStatic {
    static int later = 10;
    static int first = later + 1;

    static {
        System.out.println(first);
    }
}
~~~

The declarations compile validly. During class initialization, `later` is assigned 10 before `first` reads it, so `first` receives 11.

### 3.3. Self-Reference Is Also Restricted

~~~java
class BadSelfReference {
    static int x = x + 1; // ERROR: simple-name read inside x's initializer.
}
~~~

The issue is not limited to “a field declared later”. `x` is right inside **`x`'s own** initializer, and the simple-name read of `x` satisfies the prohibited conditions.

However, Java does not necessarily block every form of indirect/self-reference; qualified access or a method call can allow the program to compile and then read the default value. Therefore, the compiler check is **a guardrail**, not a prover that every dependency is acyclic.

## 4. Corresponding Rules for Instance Fields

For an **instance field `f`** declared in class `C`, a simple-name read causes an error when **simultaneously**:

1. The reference occurs in an **instance field initializer** or **instance initializer block** of `C`.
2. The reference appears within `f`'s own initializer or before `f`'s declarator.
3. It is **not** the left-hand side of an assignment expression.
4. The innermost enclosing class containing the reference is `C`.

The instance rule mirrors the static rule, but **its context is different**. Instance initializers are executed for each object, whereas static initializers are executed when the class is initialized.

### 4.1. Error Example in an Instance Field Initializer

~~~java
class BadInstance {
    int copied = later; // ERROR: illegal forward reference.
    int later = 11;
}
~~~

### 4.2. Error Example in an Instance Initializer Block

~~~java
class BadInstanceBlock {
    {
        // System.out.println(later); // ERROR if uncommented.
    }

    int later = 11;
}
~~~

### 4.3. Valid Example When Moving Dependencies Earlier

~~~java
class GoodInstance {
    int later = 11;
    int copied = later;

    {
        System.out.println("copied=" + copied);
    }
}
~~~

Here `copied` receives 11 upon instance creation, and then the block prints 11. That is the clearest way to handle it if the logic requires copied to depend on later.

## 5. Qualified Names May Be Valid but Unsafe Regarding Values

JLS §8.3.3 checks a **simple-name reference** like `later`. A **qualified** expression such as `State.later` (static) or `this.later` (instance) does not match the same reference form blocked by that condition.

**This does not mean the field is initialized earlier.** It only means the source can compile, while the runtime order does not change.

### 5.1. Complete Example: Static Qualified Forward Reference

Save **`QualifiedStaticForwardDemo.java`**:

~~~java
public class QualifiedStaticForwardDemo {
    static class State {
        static int copied = State.later;
        static int later = 25;

        static {
            System.out.println("block later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("copied=" + State.copied);
        System.out.println("later=" + State.later);
    }
}
~~~

Run:

~~~bash
javac QualifiedStaticForwardDemo.java
java QualifiedStaticForwardDemo
~~~

Output:

~~~text
block later=25
copied=0
later=25
~~~

**Trace:**

1. When `State` is initialized, ordinary static fields are prepared with default `0` before initializer expressions run.
2. `copied = State.later` is evaluated before `later = 25`.
3. The qualified access `State.later` **compiles**, yet reads the default `0`.
4. `later = 25` then runs, after which the static block prints `block later=25`.
5. `copied` **does not automatically update** when `later` receives 25.

This is not merely a syntactic difference: the program can contain a **hard-to-detect logic bug** even though the compiler accepts it.

### 5.2. Complete Example: Instance Qualified Forward Reference

Save **`QualifiedInstanceForwardDemo.java`**:

~~~java
public class QualifiedInstanceForwardDemo {
    static final class Pair {
        int copied = this.later;
        int later = 11;

        Pair() {
            System.out.println("constructor copied=" + copied);
            System.out.println("constructor later=" + later);
        }
    }

    public static void main(String[] args) {
        new Pair();
    }
}
~~~

Run:

~~~bash
javac QualifiedInstanceForwardDemo.java
java QualifiedInstanceForwardDemo
~~~

Output:

~~~text
constructor copied=0
constructor later=11
~~~

Instance field `copied` is initialized before `later`. `this.later` reads the default value 0 of the **same object**; then `later = 11` runs. The constructor body runs only after the instance field initializers belonging to Pair, so it prints 0 and 11 respectively.

### 5.3. When Should Qualified Forward References Be Avoided?

If `copied` is expected to be a copy of the **final value** of `later`, then writing `this.later` to “bypass the compiler” **does not solve the requirement**.

The real fix:

~~~java
class CorrectPair {
    int later = 11;
    int copied = later;
}
~~~

Or compute both fields in the constructor from a validated candidate value. Use a qualified forward read only when you **truly want** to depend on the current incomplete state — a rare and misleading case.

## 6. Left-Hand Side of Assignment: Assigning Before the Declarator Appears

A key JLS condition is that **a reference on the left-hand side of an assignment is not prohibited**.

Example:

~~~java
class EarlyWrite {
    static {
        number = 5; // Valid: number is on the LHS of the assignment.
    }

    static int number = 20;
}
~~~

The `static` block assigns `number = 5` first; afterward, the field initializer `number = 20` still runs and **overwrites** it. This is a syntactically valid assignment, yet it may be pointless or confusing.

### 6.1. Program Observing Early Assignment Followed by Overwrite

Save **`WriteBeforeDeclarationDemo.java`**:

~~~java
public class WriteBeforeDeclarationDemo {
    static class StaticHolder {
        static {
            number = 5;
            System.out.println("static early=" + StaticHolder.number);
        }

        static int number = 20;
    }

    static class InstanceHolder {
        {
            later = 7;
            System.out.println("instance early=" + this.later);
        }

        int later = 30;
    }

    public static void main(String[] args) {
        System.out.println("static final=" + StaticHolder.number);

        InstanceHolder holder = new InstanceHolder();
        System.out.println("instance final=" + holder.later);
    }
}
~~~

Commands:

~~~bash
javac WriteBeforeDeclarationDemo.java
java WriteBeforeDeclarationDemo
~~~

Output:

~~~text
static early=5
static final=20
instance early=7
instance final=30
~~~

**Step by step:**

- `number = 5` in the static block is an assignment LHS, so it is permitted before `number` is declared.
- `StaticHolder.number` in the print statement is qualified, so it can read 5 at that point.
- `static int number = 20` runs next and overwrites it.
- The instance block can assign `later = 7` before the declarator.
- `this.later` in the block reads 7, but the field initializer `later = 30` runs after the block and overwrites it with 30.

**Do not infer that because “assigning earlier” is accepted by the compiler, it is always a sound design.** Avoid relying on initialization order to overwrite states in ways that are hard to follow.

### 6.2. Simple Assignment Left-Hand Side Differs from Reads

~~~java
class Examples {
    static {
        next = 3;        // Valid: assignment LHS.
        // next += 2;     // ERROR: compound assignment also reads the value of next.
        // next++;        // ERROR: ++ reads the current value of next.
        // next = next+1; // ERROR: RHS reads next by simple name.
    }

    static int next = 10;
}
~~~

`next += 2` does not only write; semantically it also needs to read the current value of the field. `next++` also reads (and writes), so it does not fall under the exempted case of “only assigning on the left-hand side of an assignment”.

### 6.3. Nested Assignment Expressions

~~~java
class NestedAssign {
    static int first = (later = 2);
    static int later = 9;
}
~~~

In `first`'s initializer, `later` is on the left-hand side of `later = 2`, not a read. The code can compile, and if initialized, `first` receives 2, while `later` is ultimately assigned 9 by the subsequent initializer.

When you need to create valid dependencies, it is better to write explicit assignments inside a constructor or method rather than chaining multiple assignments in field initializers.

## 7. Calling a Method to Read a Field Declared Later

The `8.3.3` check applies only within the stated **initializer contexts**. When a method body reads a field declared later, it is not automatically prohibited by that exact set of conditions, even if the method is called very early from a field initializer.

However, **when** the method is called still determines its return value.

### 7.1. Complete Program: Static Method Reading Default

Save **`IndirectStaticReadDemo.java`**:

~~~java
public class IndirectStaticReadDemo {
    static class Data {
        static int copied = readLater();

        static int readLater() {
            return later;
        }

        static int later = 9;
    }

    public static void main(String[] args) {
        System.out.println("copied=" + Data.copied);
        System.out.println("later=" + Data.later);
    }
}
~~~

Run:

~~~bash
javac IndirectStaticReadDemo.java
java IndirectStaticReadDemo
~~~

Output:

~~~text
copied=0
later=9
~~~

`copied = readLater()` calls the method while `Data` is being initialized. Method `readLater()` returns `later`, but the initializer `later = 9` has not run yet. The compiler does not report `illegal forward reference` for the read inside the method, and the returned value is the default 0.

### 7.2. Complete Program: Instance Method Reading Default

Save **`IndirectInstanceReadDemo.java`**:

~~~java
public class IndirectInstanceReadDemo {
    static class Data {
        int copied = readLater();

        int readLater() {
            return later;
        }

        int later = 9;
    }

    public static void main(String[] args) {
        Data data = new Data();
        System.out.println("copied=" + data.copied);
        System.out.println("later=" + data.later);
    }
}
~~~

Commands:

~~~bash
javac IndirectInstanceReadDemo.java
java IndirectInstanceReadDemo
~~~

Output:

~~~text
copied=0
later=9
~~~

For instance fields, the mechanism is similar: `copied`'s initializer calls `readLater()` while the object is being initialized. The method reads instance field `later`, which is still at its default 0; afterward, the initializer `later = 9` completes.

**Takeaway:** changing from `copied = later` to `copied = readLater()` to avoid a compiler error **does not guarantee** that `copied` is correct according to business logic. You must adjust the ordering/design, not just the form of access.

## 8. Self-Reference via Qualification: Valid but Potentially Harmful

A self-reference is the case where a field references itself inside its own initializer.

### 8.1. Simple Reads Are Prohibited

~~~java
class BadSelf {
    static int count = count + 1; // ERROR.
}
~~~

~~~java
class BadSelfInstance {
    int count = count + 1; // ERROR.
}
~~~

### 8.2. Qualified References Can Compile

Save **`QualifiedSelfReferenceDemo.java`**:

~~~java
public class QualifiedSelfReferenceDemo {
    static class StaticNode {
        static int value = StaticNode.value + 1;
    }

    static class InstanceNode {
        int value = this.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("static=" + StaticNode.value);
        System.out.println("instance=" + new InstanceNode().value);
    }
}
~~~

Run:

~~~bash
javac QualifiedSelfReferenceDemo.java
java QualifiedSelfReferenceDemo
~~~

Output:

~~~text
static=1
instance=1
~~~

- StaticNode.value starts with default 0. The initializer reads `StaticNode.value` (qualified), adds 1, and assigns 1.
- InstanceNode.value also starts at 0 for each object. The initializer reads `this.value`, adds 1, and assigns 1.
- The result 1 does **not** mean Java runs the initializer twice. It is a single calculation based on the default value.

In most business code, self-referential expressions like the above should not be used as a counting mechanism. If you need a counter, define the increment in a method/constructor with explicit state.

## 9. Distinguishing a Field Declared Later from a Field in Another Class or Superclass

The rule is not “every field on a later line is forbidden”. It considers **which field is declared in class `C`**, which context is reading it, and which class encloses the reference.

### 9.1. An Instance Initializer Can Reference a Static Field Declared Later

JLS `8.3.2 allows an **instance field initializer** to reference suitable class variables by simple name, including a static field declared later in the same class. During normal instance creation, the class has already initialized its static part.

Save **`CrossKindForwardDemo.java`**:

~~~java
public class CrossKindForwardDemo {
    static class Data {
        int snapshot = SHARED;

        static int SHARED = 12;

        Data() {
            System.out.println("snapshot=" + snapshot);
        }
    }

    public static void main(String[] args) {
        Data data = new Data();
        System.out.println("shared=" + Data.SHARED);
    }
}
~~~

Run:

~~~bash
javac CrossKindForwardDemo.java
java CrossKindForwardDemo
~~~

Output:

~~~text
snapshot=12
shared=12
~~~

`snapshot` is an instance field, and `SHARED` is a static field. When the constructor creates an instance, static initialization of Data has already completed in the example. The rule prohibiting **premature instance-field simple-name reads in an instance initializer** does not apply to this read of static `SHARED`.

**Do not overgeneralize:** if a static initializer attempts to read an instance field by simple name, that is a **static context** error (no current instance), not the same kind of forward reference error.

### 9.2. Inherited Fields Declared in a Superclass

Example:

~~~java
class Parent {
    protected int inherited = 17;
}

class Child extends Parent {
    int copied = inherited;
    int local = 25;
}
~~~

These are illustrative classes that compile within the same package. `inherited` is **declared in Parent**, not an instance field of Child located after the declaration of `copied`. In the Child creation process, Parent's instance initialization runs before Child initializes `copied`.

Be careful in cases where a subclass is **hiding** a field with the same name: name resolution may select a different declaration, causing the read to change meaning or become a forward reference. Use clear names instead of relying on complex shadowing/hiding.

### 9.3. Difference Between Field References and Local Variables

~~~java
static void example() {
    // System.out.println(local); // local is not declared yet.
    int local = 3;
    System.out.println(local);
}
~~~

Local variables have their own scope/definite-assignment rules. Do not apply a field's “qualified name bypasses forward reference” to a local variable; there is no `this.local` to access an out-of-scope local.

## 10. Constant Variables and Exceptions Regarding Initialization Timing

With:

~~~java
static final int PORT = 8080;
static final String APP = "Demo";
~~~

if the two fields satisfy the definition of a **constant variable** (final, primitive/String, constant-expression initializer), the JVM has a mechanism to process constant values early according to class initialization rules, and the compiler can use the constant value directly in clients.

This must be **separated** from the `8.3.3` check:

- **Forward-reference check** examines location, name form, and context.
- **Constant-variable semantics** examines modifiers/type/initializer and when the constant value is provided.
- **Runtime static field initialization** examines the evaluation order of the remaining static field initializers and blocks.

Do not conclude that every read of a `static final` field is safe: if the initializer is `calculate()` or the field has type `List`, it is not a constant variable as defined by the JLS.

### 10.1. Example Avoiding Ambiguity with Qualification

Save **`ConstantAndRuntimeForwardDemo.java`**:

~~~java
public class ConstantAndRuntimeForwardDemo {
    static class Values {
        static int constantCopy = Values.CONSTANT;
        static int runtimeCopy = Values.RUNTIME;

        static final int CONSTANT = 40;
        static final int RUNTIME = calculate();

        private static int calculate() {
            System.out.println("calculate runtime");
            return 9;
        }
    }

    public static void main(String[] args) {
        System.out.println("constantCopy=" + Values.constantCopy);
        System.out.println("runtimeCopy=" + Values.runtimeCopy);
        System.out.println("constant=" + Values.CONSTANT);
        System.out.println("runtime=" + Values.RUNTIME);
    }
}
~~~

Run:

~~~bash
javac ConstantAndRuntimeForwardDemo.java
java ConstantAndRuntimeForwardDemo
~~~

Output:

~~~text
calculate runtime
constantCopy=40
runtimeCopy=0
constant=40
runtime=9
~~~

**Explanation:**

- `Values.CONSTANT` is a compile-time constant variable, holding the value 40 when referenced from `constantCopy`'s initializer.
- `Values.RUNTIME` is static final but calls method `calculate()`, so it is **not** a constant variable.
- At the moment `runtimeCopy = Values.RUNTIME` runs, `calculate()` has not run yet, so `runtimeCopy` receives the default 0.
- Afterward, the field initializer `RUNTIME = calculate()` runs and prints `calculate runtime`.
- When `main` prints the results, field `RUNTIME` is 9, while `runtimeCopy` still holds 0.

All forward reads here use **qualified names**, avoiding the simple-name forward reference error. The difference comes from **constant-expression semantics**, not a field being arbitrarily “prioritized by the JVM”.

### 10.2. Avoid Referencing Constants That Do Not Meet the Conditions

If you have:

~~~java
static final int LATER = Integer.parseInt("40");
~~~

`LATER` is not a compile-time constant. Even though the numeric result is 40, an early access via qualification can still see default 0 before the initializer runs.

Therefore, check the **initializer kind**, not just `static final` or a predictable value.

## 11. Circular Dependencies Between Static Fields or Classes

An easy way to create unpredictable bugs is to make initializers depend on each other. The compiler can block a direct simple-name forward read, but **indirectly through methods** or **through other classes** can bypass part of the check.

### 11.1. Two Classes Referencing Each Other

Save **`CircularStaticDependencyDemo.java`**:

~~~java
public class CircularStaticDependencyDemo {
    static class A {
        static int value = B.value + 1;
    }

    static class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
~~~

Run:

~~~bash
javac CircularStaticDependencyDemo.java
java CircularStaticDependencyDemo
~~~

Output:

~~~text
A=2
B=1
~~~

Trace:

1. `A.value` is accessed first, starting the initialization of A.
2. A needs `B.value`, which triggers the initialization of B.
3. B reads `A.value` while A is **being initialized by the same thread**, so it observes the default 0 according to the recursive initialization mechanism.
4. B computes 0 + 1 = 1 and completes.
5. A computes 1 + 1 = 2 and completes.

If the activation order of A/B were reversed, the result could be different. This is why you should **not use circular static initializers** as a mechanism for establishing application state.

### 11.2. Do Not Assume Every Cycle Is Detected by the Compiler

`8.3.3` is a **local** set of constraints concerning how fields are read inside initializers. It is not an algorithm for detecting all dependency cycles across methods, classes, nested objects, services, or modules.

You should apply an acyclic design and proactively inspect the dependency graph, rather than relying on Java to reject every cycle at compile time.

## 12. Static Initializers and Instance Initializers Differ in Context

| Context | Has `this`? | Read static field by simple name? | Read instance field by simple name? |
| --- | --- | --- | --- |
| `static int x = ...` | No | Yes, subject to forward-reference restrictions | No current instance |
| `static { ... }` | No | Yes, subject to forward-reference restrictions | No current instance |
| `int x = ...` | Yes, in a valid instance context | Yes, including some static fields declared later | Yes, subject to instance forward-reference restrictions |
| `{ ... }` instance block | Yes | Yes, subject to the corresponding rules | Yes, subject to instance forward-reference restrictions |
| Constructor body | Yes, after an appropriate explicit constructor invocation | Yes, subject to scope/access/static rules | Yes; not subject to the exact `8.3.3` check for field/block initializers |
| Static method body | No | Yes, subject to scope/access | No current instance without specifying a receiver |
| Instance method body | Yes | Yes | Yes, subject to scope/access |

Attempting to use `this.later` in a static block is **syntactically/contextually invalid** even when trying to avoid a simple-name error. `this` only makes sense when a suitable instance context exists.

### 12.1. Constructors Can Reference Fields Declared Below

~~~java
class ConstructorRead {
    ConstructorRead() {
        System.out.println(later);
    }

    int later = 5;
}
~~~

This is a valid **illustrative class**: during `new ConstructorRead()`, the class's instance field initializer `later = 5` runs before the constructor body, so the constructor prints 5. Even though the field is declared textually after the constructor, that does not constitute an illegal forward reference under `8.3.3`.

**However**, calling an overridable instance method of a subclass from a superclass constructor can cause that method to see subclass fields still at default 0/null. This is a different initialization-order hazard, not a simple-name forward reference in a field initializer.

## 13. Innermost Enclosing Class: Exceptions with Nested/Anonymous Classes

JLS §8.3.3 includes the condition that **the innermost class/interface containing the reference must be C itself**. If a field is read from inside another **nested/anonymous class**, that condition may not hold; the reference is not blocked by this exact rule.

### 13.1. Illustration via an Anonymous Class

Save **`NestedReferenceDemo.java`**:

~~~java
public class NestedReferenceDemo {
    static class Owner {
        static int result = new Object() {
            int read() {
                return later;
            }
        }.read();

        static int later = 8;
    }

    public static void main(String[] args) {
        System.out.println("result=" + Owner.result);
        System.out.println("later=" + Owner.later);
    }
}
~~~

Run:

~~~bash
javac NestedReferenceDemo.java
java NestedReferenceDemo
~~~

Output:

~~~text
result=0
later=8
~~~

Inside the anonymous class's `read()` method, the compiler does not apply the exact check for a simple-name field read in `Owner`'s static initializer as a direct read within the same innermost class. The method runs before `Owner.later = 8`, so the result is still the default 0.

**Do not use an anonymous class structure just to avoid a forward-reference error.** It makes the code longer without making the state any more accurate. The example is provided to understand the exact JLS condition and the relationship between lexical nesting and runtime order.

### 13.2. A Lambda Is Not a Design Fix

Although a lambda expression can defer body execution until it is invoked, it does **not** turn an invalid or circular dependency into a reliably correct model. When reading code with a lambda in an initializer, you must check **when the functional method executes**, where names are resolved, and which fields are already ready. Separating construction from runtime usage remains easier to understand.

## 14. Why Can Reading Default Values Cause Business Logic Bugs?

A field initialized prematurely from another field can silently hold wrong data:

~~~java
class Limits {
    static int DEFAULT = Limits.MAX;
    static int MAX = 100;
}
~~~

This illustrative code compiles with qualified `Limits.MAX`, but `DEFAULT` receives 0. Then `MAX` receives 100; there is no mechanism to “automatically recompute” `DEFAULT`.

The dangerous part is that the program **does not necessarily throw an exception**, and 0 may look like a normal value. For data validation, 0 can produce completely different logic: an invalid limit, an immediate timeout, a memory size of 0, etc.

### 14.1. When Reading a Reference Field Too Early

~~~java
class Endpoints {
    static String first = Endpoints.second;
    static String second = "service";
}
~~~

`first` can receive `null`, while `second` later becomes `"service"`. If code in `first`'s initializer calls a method on a `null` reference, class initialization can fail because a `NullPointerException` is thrown.

### 14.2. Class Initialization Failure Differs from Default Values

If an exception is thrown in a static field initializer/static block, class initialization can fail; the first time typically produces `ExceptionInInitializerError` if the throwable is a non-`Error`, and a subsequent active use of the erroneous runtime class can encounter `NoClassDefFoundError`.

Therefore, there are two distinct kinds of errors:

- **Silent wrong value:** class initialization succeeds, but a field copies an unintended 0/null value.
- **Initialization failure:** a static initializer throws an exception and the runtime class becomes unusable under the initialization failure mechanism.

A forward-reference restriction does not guarantee full protection against both.

## 15. Runtime Failure Example from Reading a Reference Early

Save **`EarlyNullInitializationDemo.java`**:

~~~java
public class EarlyNullInitializationDemo {
    static class Bad {
        static int length = Bad.text.length();

        static String text = "READY";
    }

    public static void main(String[] args) {
        try {
            System.out.println(Bad.length);
        } catch (ExceptionInInitializerError error) {
            System.out.println("initialization failed");
            System.out.println("cause=" +
                    error.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac EarlyNullInitializationDemo.java
java EarlyNullInitializationDemo
~~~

Output:

~~~text
initialization failed
cause=NullPointerException
~~~

Explanation:

1. When initialization of `Bad` begins, `Bad.text` has the default value `null`.
2. `Bad.length`'s initializer reads `Bad.text` via qualified access and then calls `length()`.
3. Because the receiver is `null`, a `NullPointerException` occurs before reaching the initializer `text = "READY"`.
4. The JVM reports a class initialization error via the `ExceptionInInitializerError` mechanism, and `main` catches this error to print the cause.

**Warning:** this example illustrates the mechanism; production code should generally not catch `Error` and ignore it as a startup strategy. Fix the declaration order or use a clear factory to initialize data.

## 16. Avoiding Dependence on Default Values with Clear Ordering and Methods

When one field needs another field:

### 16.1. Place Dependencies First

~~~java
class Limits {
    static int max = 100;
    static int defaultLimit = max;
}
~~~

This is usually the simplest approach when the values belong to the same class, have no cycles, and do not require dynamic configuration.

### 16.2. Place Complex Logic in a Static Factory Method

~~~java
class Limits {
    private static final Settings SETTINGS = createSettings();

    private static Settings createSettings() {
        int max = 100;
        int defaultLimit = max / 2;
        return new Settings(max, defaultLimit);
    }

    record Settings(int max, int defaultLimit) {
        Settings {
            if (max <= 0 || defaultLimit < 0 ||
                    defaultLimit > max) {
                throw new IllegalArgumentException("invalid limits");
            }
        }
    }
}
~~~

This snippet is a **valid class** in an appropriate Java file. Instead of using multiple mutually dependent and textually distant static fields, the factory produces a configuration value with a clear invariant. `Settings` is an immutable record containing only primitive ints; other callers cannot mutate its contents through setters.

**Note:** a factory called from a field initializer still runs when the class is initialized; it **does not automatically become lazy initialization**. The benefit here is that dependencies/validation are easy to verify and no forward read is needed.

### 16.3. Initialize the Whole Group in a Static Block

~~~java
class GoodConfig {
    static final int MAX;
    static final int DEFAULT;

    static {
        int candidateMax = 100;
        int candidateDefault = candidateMax / 2;

        if (candidateDefault < 0 ||
                candidateDefault > candidateMax) {
            throw new IllegalStateException("invalid values");
        }

        MAX = candidateMax;
        DEFAULT = candidateDefault;
    }
}
~~~

This is a compilable example (blank static final fields are validly assigned). Values are computed in **local variables** declared and assigned in a clear sequence; only after validation are they assigned to the fields.

In this example, `MAX` and `DEFAULT` are static final fields, yet they are **not compile-time constant variables**, because they are assigned inside a block rather than initialized with a constant-expression initializer directly at the declarator.

### 16.4. Constructors for Per-Object State

~~~java
class Range {
    private final int maximum;
    private final int preferred;

    Range(int maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException("maximum must be positive");
        }
        this.maximum = maximum;
        this.preferred = maximum / 2;
    }

    int preferred() {
        return preferred;
    }
}
~~~

If the state depends on each instance, a constructor like the above is more appropriate than using static fields. There is no need for `this.preferred` to read before `maximum` is initialized through a field initializer; every dependency is visible inside the constructor.

## 17. Debugging an `illegal forward reference` Error

When the compiler reports `illegal forward reference`, ask yourself:

1. **Which field is being read?** Does the simple name resolve to a static field or an instance field?
2. **In which class is that field declared?** The class containing the initializer itself, or a superclass/outer class?
3. **Where does the read occur?** A static field initializer, static block, instance field initializer, instance block, or method/constructor?
4. **Is it reading the field itself or a field declared further down?**
5. **Does the expression use a simple name or a qualified name?**
6. **Is the name on the right-hand side or left-hand side of an assignment?** For compound assignment or ++/--, a read is also involved.
7. **Is the innermost enclosing class/interface the exact class declaring the field?**
8. **If changed to a qualified/method call, what value will be observed at runtime?** Will it be default 0/null?
9. **Is there any constant variable involved, and what does that mean for its initialization timing?**
10. **Can the dependency be placed first or computed together in a factory/constructor?**

Although there are many conditions, the fix is usually very simple: **do not read a field before its required value has been initialized**.

### 17.1. Why Shouldn't You Just Add `this.` or the Class Name?

Changing:

~~~java
int copied = later;
~~~

to:

~~~java
int copied = this.later;
~~~

can turn a compile-time error into a valid program, but **does not guarantee `copied` is correct**. If `later` is assigned 11 on a later line, `copied` will very likely receive 0 as in the demo.

To fix the **semantics**, move `later`'s initializer earlier or remove the redundant field copy so a single source of truth is read when needed.

### 17.2. Why Shouldn't You Just Switch to a Getter?

~~~java
int copied = getLater();

int getLater() {
    return later;
}

int later = 11;
~~~

A method call is not subject to the same forward-read check by itself, yet the getter is called **when later does not yet hold 11**. The result may still be 0. Methods should only be used when the order/input values are already under control.

## 18. Distinguishing Issues Commonly Grouped as “Forward Reference”

| Scenario | Rule Group |
| --- | --- |
| `int a = b; int b = 1;` in the same class | JLS `8.3.3` instance forward read |
| `static int a = b; static int b = 1;` | JLS `8.3.3` static forward read |
| `int a = this.b; int b = 1;` | Compilation may be valid, but runtime initialization order |
| `static int a = C.b; static int b = 1;` | Qualified access; runtime default values |
| `{ b = 1; } int b = 5;` | Assignment LHS exception, later initializer overwrites |
| `{ b++; } int b;` | Read-before-declaration restriction |
| `int a = readB(); int b = 5;` | Indirect read and initialization order |
| `int a = STATIC_B; static int STATIC_B = 5;` | Instance initializer reading a static field, different scope/rules |
| Local variable used before declaration | Local scope, not `8.3.3` field check |
| Local declared but not yet assigned | Definite assignment |
| Constructor calls overridden method in subclass too early | Object initialization + dynamic dispatch |
| Static initializer uses `this.b` | Static context has no `this` |
| Two static classes read each other | Class initialization dependency/cycle |
| `final` field not assigned along a valid path | Definite assignment and final field rules |

**Accurate classification** is very important. Name-in-scope errors, definite assignment errors, static context errors, and out-of-order initialization errors have different solutions.

## 19. Common Misconceptions and Pitfalls

| Misconception | Reality |
| --- | --- |
| “If a field is declared later, the compiler doesn't know its name.” | Members have scope across the class body; the restriction is an additional check. |
| “Any forward reference is prohibited.” | The JLS restricts cases of reading via simple name in specific contexts. |
| “Only static fields have forward-reference restrictions.” | Instance field initializers and instance initializer blocks have them too. |
| “Every use of a field name declared later is illegal.” | Constructor/method bodies and qualified references have different semantics. |
| “`this.later` won't compile because the field is declared below.” | It can compile; the risk is reading the default value. |
| “`ClassName.later` runs later's initializer first.” | Qualification does not change textual execution order. |
| “Using a getter will automatically wait for the field to finish.” | A method called early still sees the uninitialized field. |
| “`x = 3` and `x += 3` behave the same when the field is declared later.” | Compound assignment reads the old value, so they differ. |
| “Assigning before the field and then having a field initializer keeps the assigned value.” | The subsequent initializer can overwrite it. |
| “If it compiles, the initialization order is correct.” | You can still observe 0/null or dependency cycles. |
| “`final` gives every field its final value from the very beginning.” | Blank final/runtime final and constant variables have different semantics. |
| “`static final` is always a constant variable.” | It requires primitive/String and a constant-expression initializer. |
| “Forward-reference errors for locals are the same as for fields.” | Local scope/definite-assignment rules are different. |
| “All static blocks run before static fields.” | Field initializers and blocks run in textual order. |
| “Instance field initializers run after the constructor body.” | Normally they run before the constructor body of that class level. |
| “Reading a superclass instance field declared later is like reading a Child field declared later.” | The declaring class and constructor order differ. |
| “The compiler will detect every dependency cycle.” | No; indirect and cross-class cycles can slip through. |
| “No compiler error means static dependencies are thread-safe.” | Class initialization coordination does not replace synchronization for mutable state. |
| “Turning an error into null is an improvement.” | Turning a compile-time error into a runtime error usually makes debugging harder. |

## 20. Self-Check Questions with Answers

**Question 1.** Why does `int a = b; int b = 5;` in the same class report an error?  
**Answer:** `a`'s initializer reads instance field `b` by simple name before `b`'s declaration; this falls under JLS `8.3.3`.

**Question 2.** How does `static int a = b; static int b = 5;` differ from the case above?  
**Answer:** This is the **static** version; the read occurs in a static field initializer and satisfies the corresponding prohibition conditions.

**Question 3.** Why can `int a = this.b; int b = 5;` compile yet leave a equal to 0?  
**Answer:** A qualified reference is not covered by the simple-name read prohibition, but `b` is still at default 0 when `a`'s initializer runs.

**Question 4.** If you write `static int a = Sample.b; static int b = 5;`, does a automatically become 5 after b is assigned?  
**Answer:** No. It can receive default 0 and keep 0; there is no reactive recomputation.

**Question 5.** Can a static block before field `x` write `x = 10`?  
**Answer:** Yes, if other rules are satisfied; this is an assignment LHS exempted from the forward-read check.

**Question 6.** After `static { x = 10; } static int x = 20;`, what is the final value of x?  
**Answer:** 20, because the subsequent field initializer overwrites the assignment in the earlier block.

**Question 7.** Is `x += 1` before x's declaration the same as `x = 1`?  
**Answer:** No; `x += 1` must read the old value of x, so it does not benefit from the left-hand-side assignment-only exception.

**Question 8.** Is `x++` before x's declaration valid under the assignment LHS exception?  
**Answer:** No. ++ reads the current value; it is prohibited in a context satisfying the rule.

**Question 9.** Why can a method `readX()` returning x declared later still compile?  
**Answer:** The read is inside a method body, not directly in an initializer context satisfying all `8.3.3` conditions.

**Question 10.** Does calling method `readX()` from a field initializer guarantee getting the final initialized value of x?  
**Answer:** No. A method run early still reads default 0/null.

**Question 11.** Is `static int x = x + 1;` valid?  
**Answer:** No, a simple-name self-reference read in x's own initializer is prohibited.

**Question 12.** What can `static int x = Owner.x + 1;` yield for x when the class is initialized for the first time?  
**Answer:** It can be 1 because the qualified read sees default 0 and then adds 1.

**Question 13.** What result can `int x = this.x + 1;` produce when creating an object for the first time?  
**Answer:** 1, also based on the int default 0. It should not be used as a design pattern.

**Question 14.** Why can an instance field initializer use a static field declared further down?  
**Answer:** `8.3.3` distinguishes instance-field reads from class-variable reads; static class initialization normally happens before instance creation.

**Question 15.** Is a subclass reading a superclass instance field always considered a forward reference in the subclass?  
**Answer:** No. The field is declared in the superclass and has its own initialization order; one must consider the declaring class, accessibility, and name resolution.

**Question 16.** If class A's static initializer reads a field of B, and B reads a field of A, will the compiler always report an error?  
**Answer:** No. Cycles across multiple classes can compile yet read default values at runtime.

**Question 17.** Why are two `static final` fields not necessarily treated identically as compile-time constants?  
**Answer:** Only final primitive/String fields with a constant-expression initializer are constant variables; an initializer from a method call does not qualify.

**Question 18.** Does a constructor reading a field declared below necessarily cause `illegal forward reference`?  
**Answer:** No. `8.3.3` does not check the constructor body under the exact conditions for field/initializer blocks; the runtime value still depends on initialization order.

**Question 19.** If a static qualified forward read accesses an uninitialized `String` field, what default value is typically observed?  
**Answer:** `null`, except in the case of a compile-time constant variable or other special initialization semantics.

**Question 20.** Why is using `this.x` inside `static { ... }` invalid?  
**Answer:** A static context has no current instance; this is a static-context rule violation, not merely a forward reference.

**Question 21.** To fix `int a = b; int b = compute();`, what is the best approach when a needs the initialized value of b?  
**Answer:** Place `b`'s initializer before `a` or compute both in a constructor/factory with explicit dependencies; do not just replace `b` with `this.b`.

**Question 22.** Why is `int a = this.b; int b = 5;` a code smell even though the compiler accepts it?  
**Answer:** It relies on a default value with no business meaning and easily creates silent wrong state during refactoring.

**Question 23.** Does a `final int b` assigned in a constructor become a compile-time constant variable if the constructor always assigns 5?  
**Answer:** No. It does not have a constant-expression initializer at its declaration.

**Question 24.** If the compiler reports an error in an initializer block, what should the first analysis step be?  
**Answer:** Identify the field being read, its static/instance kind, whether it appears before the declarator or is a self-reference, whether it is simple/qualified, and whether it is on the LHS/RHS.

## 21. References

- Java Language Specification (Java SE 17), [`8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): core rules for **forward references and self-references** in field/static/instance initializers.
- Java Language Specification, [`8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initializer semantics; notes on static constants and instance initializers.
- Java Language Specification, [`8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance initializer blocks.
- Java Language Specification, [`8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static initializer blocks.
- Java Language Specification, [`12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): when static fields receive values and the initialization steps.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance field initialization and constructor order.
- Java Language Specification, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): constant variable.
- Java Language Specification, [`16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): rules for assigning before reading, especially for local and blank final variables.

## Key Takeaways

**Forward reference restrictions** in Java do not mean a field’s name “is not yet known” if placed later. According to JLS §8.3.3, Java prevents **simple-name reads** of static/instance fields in an **initializer of the same kind** when the field is declared later or references itself, while also considering assignment LHS and innermost enclosing class conditions.

Switching to `ClassName.field`, `this.field`, or calling a method may make the code **compile**, but does not change the runtime order and can cause the read value to be `0`, `false`, or `null`. Therefore, do not fix the error with syntax alone: **initialize dependencies first**, verify candidate state, and avoid circular dependencies. Distinguishing the three questions **“is the field in scope?” → “is this reference form valid?” → “has it received the required value yet?”** is the key to reading and designing field initializers in Java.
