# Instance Fields and Per-Instance Data in Java

A class can create multiple objects, and each object holds **its own state**. In Java, the component that directly stores that state is the **instance field** (also called a non-`static` field). Understanding this helps answer questions such as: why modifying student A's score does not change student B's score, why two variables can still observe the same change, and what happens if a field holds a reference to a shared object.

## 1. What Is an Instance Field?

A **field** is a variable declared in the class body, outside any constructor, method, or block. An **instance field** is a field **not declared `static`**. Each object created from the class has a portion of state corresponding to the instance fields declared or inherited according to the Java language rules.

Example of a partial class (not yet a standalone runnable program):

~~~java
class ScoreCard {
    String playerName; // instance field
    int score;         // instance field
}
~~~

Each `new ScoreCard()` creates a new object with **its own field values**. One object can have `score = 10`, while another object has `score = 0`.

This does not mean the JVM necessarily arranges fields in a specific memory layout that a program can access directly. Java specifies **the state semantics of each object**; storage details are implemented by the JVM.

### Three Concepts to Distinguish

| Concept | Example | What Is Created or Stored |
| --- | --- | --- |
| Class | `class ScoreCard { ... }` | Type definition, its fields, and valid behaviors |
| Object | `new ScoreCard()` | An instance with its own state |
| Reference variable | `ScoreCard a` | A variable that can point to an object or hold `null` |

The statement `ScoreCard a;` inside a method **does not create an object yet**. Only the statement `a = new ScoreCard();` creates an instance and assigns its reference to the variable `a`. The value stored in variable `a` is distinct from the field values located inside the object it refers to.

## 2. One Class, Multiple Independent Copies of State

Create the file **`InstanceFieldDemo.java`** and use Java 17 or later:

~~~java
class ScoreCard {
    private final String playerName;
    private int score;

    ScoreCard(String playerName) {
        if (playerName == null || playerName.isBlank()) {
            throw new IllegalArgumentException("Tên người chơi không hợp lệ");
        }
        this.playerName = playerName;
        this.score = 0;
    }

    void earn(int points) {
        if (points <= 0) {
            throw new IllegalArgumentException("Điểm cộng phải dương");
        }
        score = Math.addExact(score, points);
    }

    int score() {
        return score;
    }

    String display() {
        return playerName + ": " + score;
    }
}

public class InstanceFieldDemo {
    public static void main(String[] args) {
        ScoreCard an = new ScoreCard("An");
        ScoreCard binh = new ScoreCard("Binh");

        an.earn(10);
        binh.earn(5);
        an.earn(3);

        System.out.println(an.display());
        System.out.println(binh.display());

        ScoreCard aliasOfAn = an;
        aliasOfAn.earn(2);
        System.out.println(an.display());

        ScoreCard anotherAn = new ScoreCard("An");
        System.out.println(anotherAn.display());
        System.out.println(an == aliasOfAn);
        System.out.println(an == anotherAn);
    }
}
~~~

From the directory containing the file, run:

~~~bash
javac -encoding UTF-8 InstanceFieldDemo.java
java InstanceFieldDemo
~~~

Stdout output:

~~~text
An: 13
Binh: 5
An: 15
An: 0
true
false
~~~

The program has a single `ScoreCard` class definition, yet **three objects** are created via three `new ScoreCard(...)` calls: `an`, `binh`, and `anotherAn` point to three different instances.

- `an.earn(10)` and then `an.earn(3)` change the score of An's object from 0 to 13; Binh's score remains 5.
- `aliasOfAn = an` only **copies the reference** to An's object. There is no `new` call, so no fourth object is created.
- `aliasOfAn.earn(2)` affects the very same object that `an` also refers to; therefore, `an.display()` prints `An: 15`.
- `anotherAn = new ScoreCard("An")` creates a **new object**. Having the same player name does not cause the two objects to share the `score` field; `anotherAn`'s score is still 0.
- `an == aliasOfAn` is `true`, because both references point to the same object. `an == anotherAn` is `false`, because they are two different objects.

### State Diagram After the Operations

~~~text
ScoreCard class definition
  - playerName: String
  - score: int
  - earn(...), display(), score()
             |
             | creates multiple instances
             v

variable an -----------------+----> Object #1: ScoreCard
variable aliasOfAn ----------+      playerName = "An"
                                    score      = 15

variable binh --------------------> Object #2: ScoreCard
                                    playerName = "Binh"
                                    score      = 5

variable anotherAn ---------------> Object #3: ScoreCard
                                    playerName = "An"
                                    score      = 0
~~~

**Core takeaway from the example:** independence depends on **the number of objects actually created**, not on the number of reference variables or whether the objects have identical initial data.

## 3. `this` Selects the Field of the Current Object

In the constructor:

~~~java
this.playerName = playerName;
this.score = 0;
~~~

`this` is a reference to the current object being initialized or executing an instance method. In the first statement, `this.playerName` is the object's field; `playerName` on the right is the constructor **parameter**.

When calling:

~~~java
an.earn(10);
binh.earn(5);
~~~

Java executes the `earn` method with different **receiver objects**. Inside `earn`, the name `score` is resolved as the field of `this` in that context, equivalent to writing `this.score`.

It is not that each object has an independent copy of the machine code/method body of `earn` in the language semantics. **The behavior declaration in the class is reused; the instance state that the behavior operates on belongs separately to the receiver object.**

### Name Collisions Between Field, Parameter, and Local Variable

Consider the illustrative snippet:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void setValue(int value) {
        this.value = value;
    }

    int value() {
        return this.value;
    }
}
~~~

This is a **standalone class definition without `main`**. In the constructor and `setValue`, the parameter `value` **shadows** the instance field of the same name. Writing `this.value` explicitly indicates the object's field, while `value` without `this` refers to the parameter. If you write `value = value;`, both sides are the parameter and **do not update the field**.

When there is no closer variable with the same name, as in `ScoreCard.earn`, you can write `score` as shorthand instead of `this.score`. The `this` keyword **cannot be used in a `static` context**.

## 4. Each Object Instantiation Creates a Separate Copy of State

With `new ScoreCard("An")` in the main example, the instance fields are set to default values **for that specific instance** before field initializers and the constructor complete. `int score` starts at `0`, while a reference field such as `String playerName` defaults to `null` before the constructor assigns the required name. If you subsequently create `new ScoreCard("Binh")`, the later object does not reuse the `score` or `playerName` of the previous object.

The general order to remember is: **default values → appropriate superclass initialization → instance field/initializer blocks in source order within the class → constructor body of the class**; `this(...)` chaining has its own rules and does not re-run the same class's initializers merely because one constructor delegates to another. This is a conceptual order, not a claim about physical heap layout.

A `final` field such as `private final String playerName;` still **belongs separately to each object**. It must be assigned according to definite-assignment rules during valid construction, typically via a constructor, and then cannot be reassigned; `final` does not make the entire object immutable. The focus here is that **two instantiations produce two separate states**, rather than repeating tests of every default value or analyzing local-variable definite-assignment branches.

## 5. Instance Fields Differ from Static Fields

**Instance field:** each object holds its own state.  
**Static field:** a member belonging to the class, shared by instances of the same class within the same class-loading context.

Illustrative snippet:

~~~java
class VisitCounter {
    static int totalVisits; // belongs to the class
    int myVisits;           // separate for each object

    void visit() {
        myVisits++;
        totalVisits++;
    }
}
~~~

If there are two instances `first` and `second`, calling `first.visit()` twice and `second.visit()` once in a sequential flow yields:

| Field Read | Value |
| --- | ---: |
| `first.myVisits` | 2 |
| `second.myVisits` | 1 |
| `VisitCounter.totalVisits` | 3 |

The `VisitCounter` example is only an **illustrative class definition**, without `main`. The variable `myVisits` must be an instance field because each object needs its own visit count; the variable `totalVisits` is intentionally designed to keep a shared count at the class level.

**Dangerous mistake:** if you accidentally add `static` to a field that needs to be separate for each object, such as `static int score`, every `ScoreCard` will share a single score field instead of having its own score.

On the other hand, using `static` does not make the `++` operation safe when multiple threads update it. Both instance field and static field accesses must consider concurrency issues if the same state is shared across multiple threads.

## 6. “Each Field Is Separate” Does Not Mean All Referenced Data Is Independent

For a primitive type such as `int`, the field stores the **value** directly. For a reference type such as `StringBuilder`, the field stores a **reference** to another object. Two owner objects can have **two separate reference fields**, yet the values of those two fields can both point to **a single shared object**.

Create the file **`ReferenceFieldDemo.java`**:

~~~java
import java.util.Objects;

class Notebook {
    private StringBuilder content;

    Notebook(StringBuilder content) {
        this.content = Objects.requireNonNull(content);
    }

    void append(String text) {
        content.append(text);
    }

    void replaceBuffer(StringBuilder replacement) {
        content = Objects.requireNonNull(replacement);
    }

    String text() {
        return content.toString();
    }
}

public class ReferenceFieldDemo {
    public static void main(String[] args) {
        StringBuilder shared = new StringBuilder("A");
        Notebook first = new Notebook(shared);
        Notebook second = new Notebook(shared);

        first.append("B");
        System.out.println(first.text());
        System.out.println(second.text());

        second.replaceBuffer(new StringBuilder("C"));
        System.out.println(first.text());
        System.out.println(second.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceFieldDemo.java
java ReferenceFieldDemo
~~~

Stdout:

~~~text
AB
AB
AB
C
~~~

What happened?

1. `new Notebook(shared)` is called twice, so there are two `Notebook` objects, each owning a separate `content` field.
2. **Initially**, these two fields hold the same reference value pointing to the `StringBuilder` object created on the `shared` line.
3. `first.append("B")` mutates the shared `StringBuilder`; consequently, `second.text()` also returns `AB`.
4. `second.replaceBuffer(new StringBuilder("C"))` only reassigns **the content field of object second**. The `content` field of `first` still points to the old builder and returns `AB`; object `second` returns `C`.

Diagram before the `replaceBuffer` step:

~~~text
first  ---> Notebook #1 ---> content ----+
                                         |
                                         +--> StringBuilder "AB"
                                         |
second ---> Notebook #2 ---> content ----+
~~~

Diagram after the `replaceBuffer` step:

~~~text
first  ---> Notebook #1 ---> content ----> StringBuilder "AB"

second ---> Notebook #2 ---> content ----> StringBuilder "C"
~~~

This explains a practical issue: if a constructor accepts a `List`, `Map`, array, or a mutable object and then **stores the reference directly** in a field, the caller and other instances may still hold references to that data. If the design requires **independent ownership**, you should consider making an appropriate copy or using an immutable type; a shallow copy can still share child objects.

For example, `String` is a reference type, yet **immutable** according to its API, so sharing the same `String` does not create a situation of in-place content modification like `StringBuilder`. You should not conclude that “every reference-type field is dangerous”; instead, examine **mutability and how references are shared**.

## 7. Reading, Writing Fields, and the Principle of Encapsulation

If the fields of `ScoreCard` were `public`, external code could execute `an.score = -999;` and break the non-negative score requirement. The design in the main example uses:

~~~java
private int score;

void earn(int points) {
    if (points <= 0) {
        throw new IllegalArgumentException("Điểm cộng phải dương");
    }
    score = Math.addExact(score, points);
}

int score() {
    return score;
}
~~~

*These lines are excerpted from inside the `ScoreCard` class, not a standalone compilable file.*

- `private` restricts direct access to the `score` field to the scope of the declaring class.
- `earn` is a controlled entry point for modifying state; invalid input is rejected **before** assignment.
- `Math.addExact` prevents silent integer overflow; if addition overflows, the assignment is not performed.
- `score()` provides the current observable value without exposing a field that can be arbitrarily modified.

**A getter is not mandatory for every field.** Only provide read or update methods when they genuinely serve the behavior needed by users of the class. In object-oriented design, domain-meaningful behavior is often clearer than letting code anywhere directly edit individual fields.

`private` is not a security boundary for a production-deployed service; it is a language-level access mechanism to support correctness control and encapsulation.

## 8. References, Assignment, and Method Parameters

The independence of instance fields is often misunderstood when using assignment.

| Statement | Creates a new object? | Consequence |
| --- | --- | --- |
| `ScoreCard a = new ScoreCard("An");` | Yes | `a` points to a new object |
| `ScoreCard b = a;` | No | `a` and `b` both point to that object |
| `ScoreCard c = new ScoreCard("An");` | Yes | `c` points to a different object, even though the initial data is the same |
| `b = c;` | No | Variable `b` changes its reference; the old object is not modified merely by the assignment |
| `a = null;` | No | Variable `a` stops referencing the object; the object may still be held by another variable |

In Java, **all arguments are passed by value**. For a reference variable, the value passed is **a copy of the reference**. Therefore, a method receiving a reference can modify the instance fields of the shared object if it has access, but reassigning the parameter itself does not change the caller's variable.

Short example (placed inside a class where `ScoreCard` already exists; **non-standalone** illustrative snippet):

~~~java
static void award(ScoreCard card) {
    card.earn(1);                 // modifies the state of the referenced object
    card = new ScoreCard("Khac"); // only changes the local parameter variable
}
~~~

When `award(an)` completes, the object that `an` points to receives 1 point; `an` does not automatically switch to the object named `"Khac"`.

Do not infer from two **different reference variables** that two **objects** are also different. And do not infer from two **different objects** that they cannot share **child objects** through a reference-type field.

## 9. Field Lifetime and Limitations of the Examples

An instance field exists as part of the **object's** state. The scope of a variable holding a reference and the duration for which the object remains reachable are two different matters:

- A local variable `ScoreCard card` going out of scope does not mean the object is immediately deleted. The object may still be referenced from another variable, a field of another object, or elsewhere.
- An object that is no longer reachable can become eligible for reclamation by the garbage collector. There is **no guarantee** it will be reclaimed immediately after a `null` assignment.
- For an object with a reference field holding `null`, that field still **exists**; it simply does not point to any object yet.
- The same class definition can be used to create zero, one, or many objects; only objects that are actually created have concrete instance field values.

### A Note on Multithreading

The examples above execute sequentially. “Per-object separate fields” **does not mean** always safe in a multithreaded program. If two threads both hold a reference to **one** `ScoreCard`, they can simultaneously read/write **one** `score` field. The update `score = Math.addExact(score, points)` is not an atomic operation across the entire read–compute–write sequence. For concurrency, you must design appropriate synchronization, atomic mechanisms, or state ownership.

Conversely, when each thread owns its own separate object and does not share references to other mutable state, the independence of instance fields helps prevent interference between them.

## 10. Pitfalls and How to Recognize Them

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| “There are two variables, so there must be two instances” | `ScoreCard b = a;` does not call `new` | Two variables can reference the same object |
| “Two objects have the same name, so they share score” | A domain name and object identity are two different things | Each instance has its own `score` field |
| “Making score `static` still keeps scores separate” | A static field is shared at the class level | Use an instance field for separate data |
| “A `final` field makes the object immutable” | Other fields or referenced objects can still change | `final` only restricts reassigning the field itself |
| “Separate reference fields guarantee separate contents” | Two fields can both point to a mutable object | Consider aliasing, copying, and immutability |
| “Both fields and local variables default to 0” | A local variable must be definitely assigned before being read | Default-value rules apply to fields and array elements |
| “When variable `a` goes out of scope, the object disappears immediately” | The object may still have other reference paths | The GC decides when to reclaim unreachable objects |
| “Instance fields are automatically safe when used by multiple threads” | Multiple threads can hold references to the same object | Synchronization is needed when concurrently modifying shared mutable state |

When observing a bug where data “changes on its own” between two places in a program, check: are two variables pointing to the same object? Is the field declared `static` or as an instance field? If the field is a reference, are two objects holding the same child object?

## 11. Self-Check Exercises

**Exercise 1 — Separating state.** Given:

~~~java
ScoreCard a = new ScoreCard("A");
ScoreCard b = new ScoreCard("B");
a.earn(4);
b.earn(2);
~~~

What are `a.score()` and `b.score()`? Why does modifying A not change B?

**Exercise 2 — Copying a reference.** After Exercise 1, write:

~~~java
ScoreCard c = a;
c.earn(1);
~~~

What are `a.score()` and `c.score()`? How many `ScoreCard` objects have been created?

**Exercise 3 — Creating a new object with the same data.** Write `ScoreCard d = new ScoreCard("A");`. Is `d`'s score equal to `a`'s score? Is `a == d` `true` or `false`?

**Exercise 4 — References in fields.** Two `Notebook` objects are created with the same `StringBuilder`. If one notebook `append`s data, can the other notebook read the new part? If the second notebook is assigned a new `StringBuilder` via `replaceBuffer`, what remains shared?

**Exercise 5 — Field design.** In a `ShoppingBasket` class, should `itemCount` be declared as an instance field or `static` if each basket needs its own item count? When does a class-level variable make sense?

**Reference answers:**

1. `a.score() == 4`, `b.score() == 2`; two different instances have two separate `score` fields.
2. Both are 5; `c` only aliases `a`, and the total number of instances remains 2.
3. `d.score() == 0` and `a == d` is `false`: the third `new` call creates a new object.
4. Initially yes, because both point to the mutable builder; after replacing the reference in the second notebook, the two fields point to two different builders.
5. Use an instance field for each basket's `itemCount`; only use static when intentionally storing state belonging to the class, shared across baskets.

The point to remember is that **each object owns its instance field values, but references to objects can be shared**. To know where a change has an effect, identify the object receiving the operation and trace the references inside the fields.
