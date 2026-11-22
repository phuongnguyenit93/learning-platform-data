# Tracing References Across Multiple Calls and Multiple Objects in Java

A Java code snippet with multiple nested method calls often causes confusion not because the syntax is difficult, but because **the same object can be referenced by multiple variables across multiple calls**, while each reference variable can be reassigned to a different object.

Let's start with an absolutely critical rule:

> **Java always passes arguments by value (pass-by-value).** For reference-type arguments, the value copied to the parameter is the *reference value* itself. Two variables can reference the same object; modifying the object can be observed through both, but reassigning the parameter does not cause the caller's variable to change its reference on its own.

Example:

~~~java
Box a = new Box(1);
Box b = a;
change(b);
~~~

To predict what the variable `a` will observe after `change`, we cannot just look at variable names. We need to know whether inside `change` it **modifies the existing Box's state** or **assigns a different reference to the parameter**. If there are calls `main → first → second → third`, at each level a **separate parameter variable** appears, which may hold copies of the reference to the same object.

This article guides you through a method for accurately tracing references across **call chains, multiple objects, aliases, arrays, object graphs, return values, loops/recursion, polymorphism, and exception handling**. The complete examples run on **Java 17+**.

## 1. Four Things That Must Always Be Kept Separate

| Concept | Example | What Does It Mean? |
| --- | --- | --- |
| **Object** | Instance `new Account(10)` | An entity with identity and state, such as the `balance` field |
| **Reference variable** | `Account account` | A variable declared with type `Account`, holding a reference value or `null` |
| **Reference value** | The value currently stored in `account` | Allows accessing an object; can be copied into another variable |
| **Object state** | `account.balance = 20` | Data belonging to the object, not separate data per alias |

Compare the two statements:

~~~java
account = new Account(20);
account.balance = 20;
~~~

Assume `Account` has an accessible constructor and field. **The first line** creates a new Account and reassigns **the variable `account`**. **The second line** modifies a field of **the object currently referenced by `account`**. These are two different behaviors even though both contain an `=` assignment.

### Reference Diagrams Are Logical Diagrams

~~~text
main.account --------+
                     |
first.parameter -----+----> Account #1 { balance = 10 }
                     |
second.target -------+
~~~

The arrows above depict **reference relationships**, not actual RAM addresses. Java does not require the representation of a reference inside the JVM to be a physical address pointer that a programmer can read or perform arithmetic on. Using numbers `#1`, `#2` is simply a way of **labeling objects by creation order in exercises**.

## 2. Start Tracing from Object Creations

Count and label each object created when `new` completes normally:

~~~java
Box first = new Box(10);   // Box #1
Box second = new Box(20);  // Box #2
Box alias = first;         // No Box #3
~~~

State:

~~~text
Variable first  -> Box #1 { value = 10 }
Variable second -> Box #2 { value = 20 }
Variable alias  -> Box #1 { value = 10 }
~~~

An assignment `alias = first` **does not clone** Box #1. These are **two variables pointing to one object**. Conversely, two separate `new Box(10)` instantiations create **two different objects**, even if their corresponding fields have equal values.

To predict the result of the program, use two separate tables:

**Reference table**

| Variable | Referenced object |
| --- | --- |
| `first` | #1 |
| `second` | #2 |
| `alias` | #1 |

**Object table**

| Object | State |
| --- | --- |
| #1 | `value = 10` |
| #2 | `value = 20` |

When encountering a **reference variable assignment**, update the reference table. When encountering a **field/element modification through a reference**, update the object state table. Do not automatically update both tables at the same time if the statement does not require it.

## 3. A Basic Program: Aliases and Variable Reassignment

Create the file **`AliasTraceDemo.java`**:

~~~java
public class AliasTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box left = new Box(1);
        Box right = left;

        right.value = 5;
        right = new Box(9);

        System.out.println("left=" + left.value);
        System.out.println("right=" + right.value);
        System.out.println("same=" + (left == right));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AliasTraceDemo.java
java AliasTraceDemo
~~~

Stdout:

~~~text
left=5
right=9
same=false
~~~

Tracing statement by statement:

| Step | `left` points to | `right` points to | Box #1 | Box #2 |
| --- | --- | --- | --- | --- |
| `left = new Box(1)` | #1 | Not yet | `value=1` | Not yet created |
| `right = left` | #1 | #1 | `value=1` | Not yet created |
| `right.value = 5` | #1 | #1 | `value=5` | Not yet created |
| `right = new Box(9)` | #1 | #2 | `value=5` | `value=9` |

At step three, `right.value = 5` modifies Box #1, so reading through `left` also sees 5. At step four, `right` is **reassigned** to Box #2; `left` still points to Box #1.

**Rule of thumb:** Before answering "which variable changed?", ask **did a reference variable switch its arrow, or did the object state change a field?**

## 4. Each Method Call Has Its Own Parameters

Suppose:

~~~java
static void change(Box parameter) {
    parameter.value = 7;
    parameter = new Box(99);
}

// In main:
Box original = new Box(1);
change(original);
~~~

When calling `change(original)`, Java:

1. Evaluates the argument `original`, obtaining the reference value to Box #1.
2. Copies that reference value into **the parameter `parameter` belonging to the `change` call**.
3. Executes the statements inside `change`.
4. Returns to the caller when the call completes normally or transfers control according to the exception mechanism.

Diagram immediately upon entering the method:

~~~text
main.original ---------+
                       +----> Box #1 { value = 1 }
change.parameter ------+
~~~

After `parameter.value = 7`:

~~~text
main.original ---------+
                       +----> Box #1 { value = 7 }
change.parameter ------+
~~~

After `parameter = new Box(99)`:

~~~text
main.original --------------> Box #1 { value = 7 }
change.parameter -----------> Box #2 { value = 99 }
~~~

This is why Java **has no mechanism for "reassigning a parameter to modify the caller's variable"**. A parameter in the callee is a separate variable, regardless of whether its name is the same as or different from the name in the caller.

### Complete Runnable Program

Save **`ParameterRebindingDemo.java`**:

~~~java
public class ParameterRebindingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box parameter) {
        parameter.value = 7;
        parameter = new Box(99);
        System.out.println("inside=" + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(1);
        change(original);
        System.out.println("outside=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterRebindingDemo.java
java ParameterRebindingDemo
~~~

Stdout:

~~~text
inside=99
outside=7
~~~

There is no mechanism to undo `parameter.value = 7` when the callee finishes: the change was already written to the object that the caller still references.

## 5. Tracing a Three-Call Chain: `main → levelOne → levelTwo`

This is the central scenario of the article: **each level has a parameter variable**, yet the levels can still all point to the same object.

Create **`ThreeLevelTraceDemo.java`**:

~~~java
public class ThreeLevelTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void levelTwo(Box item) {
        item.value += 10;
        item = new Box(100);
        item.value += 1;
        System.out.println("levelTwo=" + item.value);
    }

    static void levelOne(Box item) {
        item.value += 2;
        levelTwo(item);
        System.out.println("levelOne=" + item.value);
    }

    public static void main(String[] args) {
        Box root = new Box(1);
        levelOne(root);
        System.out.println("main=" + root.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeLevelTraceDemo.java
java ThreeLevelTraceDemo
~~~

Stdout:

~~~text
levelTwo=101
levelOne=13
main=13
~~~

### Timeline of Execution

1. `main` creates Box #1 with `value = 1`; `root → #1`.
2. `levelOne(root)` creates a **separate parameter variable** `item` in levelOne, holding the reference value to #1.
3. `levelOne` executes `item.value += 2`, so **Box #1 changes from 1 to 3**.
4. `levelTwo(item)` creates **another parameter**, also named `item` but belonging to levelTwo, initially referencing #1.
5. `levelTwo` executes `item.value += 10` → **Box #1 becomes 13**.
6. `levelTwo` executes `item = new Box(100)` → creates **Box #2** and reassigns only the parameter of levelTwo.
7. `item.value += 1` in levelTwo modifies **Box #2** to 101, then prints `levelTwo=101`.
8. When levelTwo finishes, the code in levelOne continues with **the levelOne parameter still pointing to #1**. Prints `levelOne=13`.
9. `main` continues; `root` still points to #1, so it prints `main=13`.

Diagram at the moment right before levelTwo prints:

~~~text
main.root -----------------+
                           |
levelOne.item -------------+----> Box #1 { value = 13 }

levelTwo.item -------------------> Box #2 { value = 101 }
~~~

**Do not be fooled by the duplicate name `item`:** two parameters with the same name in two calls are not the same variable. Scope and the call determine which variable is being reassigned.

### Detailed State Table

| Checkpoint | `main.root` | `levelOne.item` | `levelTwo.item` | #1 value | #2 value |
| --- | --- | --- | --- | --- | --- |
| After `new Box(1)` | #1 | — | — | 1 | — |
| Entering levelOne | #1 | #1 | — | 1 | — |
| After `+= 2` | #1 | #1 | — | 3 | — |
| Entering levelTwo | #1 | #1 | #1 | 3 | — |
| After `+= 10` | #1 | #1 | #1 | 13 | — |
| After `new Box(100)` | #1 | #1 | #2 | 13 | 100 |
| After `+= 1` | #1 | #1 | #2 | 13 | 101 |
| Returning to levelOne | #1 | #1 | Call scope ended | 13 | 101 |
| Returning to main | #1 | Call scope ended | — | 13 | 101 |

A dash "—" in the table means the variable of that call **does not exist yet or is no longer active in the described execution path**. It does not imply that Box #2 must be collected immediately by the garbage collector.

## 6. The Stack Frame Model: Useful, but Not an Absolute RAM Diagram

To solve exercises, we can represent active methods as **logical call frames**:

~~~text
                 LEVEL TWO running
+---------------------------------------------+
| levelTwo frame: item -> Box #2              |
+---------------------------------------------+
| levelOne frame: item -> Box #1              |
+---------------------------------------------+
| main frame: root -> Box #1                  |
+---------------------------------------------+

Box #1 { value=13 }       Box #2 { value=101 }
~~~

Each call has the parameter/local variables of **that call**. When the callee finishes, the caller continues with its own variables. But do not infer that:

- Every reference is guaranteed to have a stack RAM slot at a fixed location.
- An object must reside at an unchanging heap address.
- The JVM cannot inline a method or optimize an object.

The JIT, garbage collector, and JVM implementation may use different optimizations. The frame and object tables are a **semantic model** for predicting program behavior; the observable results still follow Java's rules.

## 7. Multiple Objects Passing Through a Call Chain

When a method receives two parameters of the same type, do not assume they always point to two different objects.

~~~java
static void transfer(Box source, Box destination) {
    source.value -= 3;
    destination.value += 3;
}
~~~

There are two cases:

**Case A: two different objects**

~~~java
Box a = new Box(10);
Box b = new Box(5);
transfer(a, b);
~~~

Result: `a`'s object has 7, `b`'s object has 8.

**Case B: the same object**

~~~java
Box a = new Box(10);
transfer(a, a);
~~~

`source` and `destination` are **two different parameters**, yet both point to `a`'s object. The method subtracts 3 and then adds 3 on **that same object**, so the final value is still 10.

This is an **illustrative code snippet** using a `Box` type with an accessible field; it is not yet a standalone runnable file. In some business APIs, having two parameters alias each other must be **prevented with validation**; in other APIs it may be allowed. Check with `source == destination` when you need to compare identity.

### Why Is Tracing "by Variable Name" Not Enough?

In the call `transfer(a, a)`, the two parameters have two different names, yet their reference values are equal by identity. If you only build a table saying "source decreases by 3; destination increases by 3" while forgetting the shared object, you will arrive at the wrong result. **You must trace object IDs**, not just parameter names.

## 8. Runnable Example: Two Parameters That Can Alias

Create **`TwoParametersAliasDemo.java`**:

~~~java
public class TwoParametersAliasDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void move(Box from, Box to, int amount) {
        from.value -= amount;
        to.value += amount;
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box second = new Box(5);

        move(first, second, 3);
        System.out.println("distinct=" + first.value + "," + second.value);

        move(first, first, 2);
        System.out.println("same=" + first.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 TwoParametersAliasDemo.java
java TwoParametersAliasDemo
~~~

Stdout:

~~~text
distinct=7,8
same=7
~~~

With the first call, the fields of two independent objects change. The second call uses **two copies of the reference to the same Box #1**, so it subtracts 2 and then adds 2, resulting in a net change of 0. `move` does not need to know the caller's variable names; it works with the **objects that the parameters actually reference**.

In production, a money/quantity transfer operation needs to check for negative numbers, overflow, and the policy for transferring to the same account. This example is only meant to demonstrate aliasing.

## 9. Tracing Return Values Across Multiple Levels

`return` can pass **a reference value** back to the caller. If a method returns a parameter or a field, it **does not automatically clone the object**.

~~~java
static Box identity(Box value) {
    return value;
}
~~~

If `Box result = identity(original);`, both variables reference the original object. However, a method can also return a new object:

~~~java
static Box copyValue(Box value) {
    return new Box(value.value);
}
~~~

That is an **illustrative code snippet**. When `new Box(...)` succeeds, the method returns a reference **to a new object**; the two objects may have equal field values but different identities.

### Returning and Reassigning at the Caller

With:

~~~java
Box current = new Box(1);
current = replace(current);
~~~

if `replace` returns a different reference, **the assignment in the caller** makes `current` change its arrow. A method cannot reassign the caller's `current` variable on its own merely by modifying its internal parameter.

**Comparison table:**

| Behavior inside the method | What does the caller observe? |
| --- | --- |
| Modify a shared object's field | Can see the changed field |
| Reassign the parameter | Caller's variable does not automatically change |
| Return the old parameter | Caller can receive the same reference |
| Return a new object | Caller can receive a new reference |
| Caller ignores the return value | Caller's variable is not automatically reassigned |
| Caller executes `current = method(current)` | Caller explicitly updates the reference from the method result |

## 10. Runnable Example: Replacing an Object at a Middle Level via `return`

Create the file **`ReturnReferenceChainDemo.java`**:

~~~java
public class ReturnReferenceChainDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static Box deep(Box parameter) {
        parameter.value += 2;
        return new Box(parameter.value * 10);
    }

    static Box middle(Box parameter) {
        Box result = deep(parameter);
        parameter = result;
        parameter.value += 1;
        return parameter;
    }

    public static void main(String[] args) {
        Box original = new Box(1);
        Box result = middle(original);

        System.out.println("original=" + original.value);
        System.out.println("result=" + result.value);
        System.out.println("same=" + (original == result));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReturnReferenceChainDemo.java
java ReturnReferenceChainDemo
~~~

Stdout:

~~~text
original=3
result=31
same=false
~~~

Trace:

1. `main.original` → Box #1 (1).
2. `middle.parameter` receives reference #1.
3. `deep.parameter` also receives #1 and executes `+= 2`: Box #1 becomes 3.
4. `deep` creates Box #2 with `value = 3 * 10 = 30`; returns reference #2.
5. `middle.result` → #2, then `middle.parameter = result` changes only **middle's parameter** to #2.
6. `parameter.value += 1` in middle modifies Box #2 to 31.
7. Middle returns #2; `main.result` receives reference #2.
8. `main.original` still points to #1 and observes 3.

Diagram at print time:

~~~text
main.original ----------> Box #1 { value=3 }
main.result ------------> Box #2 { value=31 }
~~~

The easiest mistake to make is predicting `original=31` by thinking `parameter = result` also changes the variable in the caller. **There is no such assignment in main.**

## 11. Holding Multiple References in Fields: Object Graphs

Not all references are in local variables. An object can have a **reference-type field** referencing another object.

~~~java
class Node {
    String label;
    Node next;
}
~~~

Each Node instance has a `next` field, which can hold a reference to another Node or null. When a method modifies `node.next`, it is **modifying a field of the Node object** that `node` references. This is not reassigning the parameter variable `node`.

Example:

~~~java
Node first = new Node();
Node second = new Node();
first.next = second;
~~~

Model:

~~~text
first -> Node #1 { next ----------> Node #2 }
second ---------------------------> Node #2
~~~

`first.next` and `second` are **two reference storage locations that can point to the same Node #2**. If a method executes `first.next.label = "updated"`, it modifies the label of Node #2, so reading `second.label` also sees the new value.

### What Is the Impact of a Reassigned Field Link?

~~~java
Node third = new Node();
first.next = third;
~~~

Afterward, `first.next` points to Node #3, while the variable `second` still points to Node #2. This line **does not delete or modify Node #2**; it replaces a reference field inside Node #1.

To solve multi-object problems correctly, draw both **arrows from variables to objects** and **arrows from an object's fields to other objects**.

## 12. Object Graph Program: Changing Links, Not Old Objects

Create the file **`ObjectGraphTraceDemo.java`**:

~~~java
public class ObjectGraphTraceDemo {
    static final class Node {
        String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static void relink(Node current, Node target) {
        current.next = target;
        target.label = target.label + "!";
        current = target;
        current.next = null;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.next = b;
        b.next = c;

        relink(a, c);

        System.out.println("a.next=" + a.next.label);
        System.out.println("b.next=" + b.next.label);
        System.out.println("c.label=" + c.label);
        System.out.println("c.next=null: " + (c.next == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ObjectGraphTraceDemo.java
java ObjectGraphTraceDemo
~~~

Stdout:

~~~text
a.next=C!
b.next=C!
c.label=C!
c.next=null: true
~~~

Trace before the call:

~~~text
a -> Node #1 { label="A", next -> #2 }
b -> Node #2 { label="B", next -> #3 }
c -> Node #3 { label="C", next -> null }
~~~

Inside `relink(a, c)`:

1. `current` initially → #1; `target` → #3.
2. `current.next = target` modifies **Node #1's field**: `#1.next` from #2 to #3.
3. `target.label = target.label + "!"` modifies **Node #3's field**: label becomes `C!`. This assigns a new String reference to the field; the old String is not modified.
4. `current = target` reassigns only **the parameter current** to #3; variable `a` in main still → #1.
5. `current.next = null` modifies the `next` field of **Node #3**, not #1.

After the call:

~~~text
a -> Node #1 { label="A", next -> #3 }
b -> Node #2 { label="B", next -> #3 }
c -> Node #3 { label="C!", next -> null }
~~~

Both `a.next` and `b.next` now point to #3. `b` was not reassigned, yet `b.next.label` changed because **Node #3 is shared**. This is an important pattern in object graphs.

## 13. When There Are Two Paths to the Same Object: Nested Aliasing

Example:

~~~java
class Person {
    Address address;
}
class Address {
    String city;
}
~~~

If two Person objects have their `address` field pointing to **one Address instance**, changing `personA.address.city` can cause `personB.address.city` to change. The two Person objects remain **two separate objects**, yet both reference one child object.

There are two levels of aliasing:

- **Direct aliasing:** `a == b` when two variables reference the same object.
- **Indirect aliasing through a field:** `a != b` yet `a.address == b.address`.

### What to Check

A method `updateCity(Person person, String city)` may do:

~~~java
person.address.city = city;
~~~

or:

~~~java
person.address = new Address(city);
~~~

The first line modifies **the shared Address object**. The second line modifies **the address reference field of the Person object**, switching that Person to a new Address; another Person may still use the old Address.

For multi-object exercises, **drawing only the arrows from variables is not enough**. You must draw links through fields and array elements.

## 14. Runnable Example: Two Persons Sharing an Address

Create the file **`SharedNestedObjectDemo.java`**:

~~~java
public class SharedNestedObjectDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    static void updateSharedAddress(Person person) {
        person.address.city = "Da Nang";
    }

    static void replaceOnlyOneAddress(Person person) {
        person.address = new Address("Hue");
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Person mai = new Person("Mai", shared);
        Person an = new Person("An", shared);

        updateSharedAddress(mai);

        System.out.println("after update Mai=" + mai.address.city);
        System.out.println("after update An=" + an.address.city);
        System.out.println("same address=" + (mai.address == an.address));

        replaceOnlyOneAddress(mai);

        System.out.println("after replace Mai=" + mai.address.city);
        System.out.println("after replace An=" + an.address.city);
        System.out.println("same address=" + (mai.address == an.address));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedNestedObjectDemo.java
java SharedNestedObjectDemo
~~~

Stdout:

~~~text
after update Mai=Da Nang
after update An=Da Nang
same address=true
after replace Mai=Hue
after replace An=Da Nang
same address=false
~~~

Analysis:

- Initially, `shared`, `mai.address`, and `an.address` all point to Address #1.
- `updateSharedAddress(mai)` modifies `Address #1.city`. Both Persons observe `Da Nang`.
- `replaceOnlyOneAddress(mai)` creates Address #2 and assigns `mai.address` to #2.
- `an.address` still points to #1 and keeps the city `Da Nang`.
- No assignment makes the variable `mai` switch to a different Person; **only a field of Person Mai is reassigned**.

**Lesson:** "Cannot reassign the caller's variable from a parameter" does not mean "the callee cannot change a reference stored inside the caller's object." A method can modify `person.address` if the object is mutable and access permissions allow it.

## 15. Arrays Also Create Reference Paths to Multiple Objects

A `Node[]` variable holds **a reference to an array object**, while each element of the array holds **a reference to a Node object or null**.

~~~java
Node first = new Node("A");
Node second = new Node("B");
Node[] nodes = {first, second, first};
~~~

There are three element slots, yet only **two Node objects** are created. `nodes[0]` and `nodes[2]` both point to Node A; `nodes[1]` points to Node B.

Diagram:

~~~text
nodes -> Array #1
           [0] ----+
           [1] ----|------> Node #2 { label="B" }
           [2] ----+
                    \-----> Node #1 { label="A" }
first ---------------------> Node #1
second --------------------> Node #2
~~~

If a method executes `nodes[0].label = "X"`, both `nodes[2].label` and `first.label` also yield `X`. If it executes `nodes[0] = new Node("Y")`, **only slot [0]** switches to the new Node; slot [2] and `first` still point to Node A.

## 16. Runnable Example: Assigning Array Elements and Reassigning an Array Parameter

Create the file **`ArrayReferenceChainDemo.java`**:

~~~java
public class ArrayReferenceChainDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void edit(Box[] items) {
        items[0].value += 5;
        items[1] = new Box(50);

        items = new Box[] {new Box(100)};
        items[0].value++;
    }

    public static void main(String[] args) {
        Box common = new Box(1);
        Box[] array = {common, common};

        edit(array);

        System.out.println("common=" + common.value);
        System.out.println("slot0=" + array[0].value);
        System.out.println("slot1=" + array[1].value);
        System.out.println("slots same=" + (array[0] == array[1]));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayReferenceChainDemo.java
java ArrayReferenceChainDemo
~~~

Stdout:

~~~text
common=6
slot0=6
slot1=50
slots same=false
~~~

At the start of `edit`:

~~~text
main.array ---> Array #1 [0] --> Box #1 { value=1 }
                         [1] --> Box #1 { value=1 }
main.common ------------------> Box #1
edit.items  ---> Array #1
~~~

Inside the method:

1. `items[0].value += 5` modifies Box #1 to 6. Because the two elements alias each other at this moment, slot 1 also *reads* 6 before being replaced.
2. `items[1] = new Box(50)` creates Box #2 and assigns **element [1] of Array #1** to Box #2.
3. `items = new Box[] {new Box(100)}` creates Array #2 and Box #3, then **reassigns parameter items** to Array #2. `main.array` still points to Array #1.
4. `items[0].value++` modifies Box #3 to 101, without affecting Array #1 or Box #1.
5. Returning to `main`: `common` and `array[0]` both point to Box #1 (6); `array[1]` points to Box #2 (50).

**Three layers must be traced separately:** the parameter `items`, the array object, and the objects stored in the array elements. Confusing any one of the three can lead to a wrong stdout prediction.

## 17. Primitives Inside Objects Do Not Change Pass-by-Value

Example:

~~~java
static void increase(int number) {
    number++;
}

static void increaseBox(Box box) {
    box.value++;
}
~~~

The first method receives **a copy of the `int`**. The second method receives **a copy of the reference to Box**, yet `box.value++` modifies **the primitive field inside the shared Box object**.

Therefore:

~~~java
int number = 5;
increase(number);
// number is still 5.

Box box = new Box(5);
increaseBox(box);
// box.value becomes 6.
~~~

These snippets are illustrative code and require an appropriate `Box` class. It is not "primitives are pass-by-value, objects are pass-by-reference." **Both are pass-by-value**. The difference is **whether the copied value is a direct number or a reference to a stateful object**.

### A `final` Field Can Still Reference a Mutable Object

~~~java
final Box box = new Box(5);
box.value = 9;  // Valid if the field is accessible and mutable.
// box = new Box(1); // Invalid because variable box is final.
~~~

`final` on a reference variable prevents **reassigning the variable**, and does not automatically prevent **modifying the Box object**.

## 18. `final` Parameters in a Call Chain

If a method is defined as:

~~~java
static void work(final Box box) {
    box.value += 1;
    // box = new Box(99); // Compilation error.
}
~~~

`final` on a parameter prevents the `box` variable from being reassigned, yet **still allows** `box.value += 1` if the object is mutable. This can reduce errors of accidentally changing a reference inside a method, though it does not make the method "read-only" for the object.

If you want an API to truly not modify the input, a design contract is needed:

- Do not call mutators on the passed-in object.
- Do not expose mutable aliases, or perform a defensive copy when appropriate.
- Use immutable/value objects when state should not change.
- Test for observable side effects, especially when the input is shared across multiple levels.

## 19. Comparing Identity and Equality While Tracing

For object references, `a == b` returns true if they denote the same object (or both are null), within a valid type comparison. `equals` can represent **value equality**, depending on the class.

A Java 17 record:

~~~java
record Point(int x, int y) {}
~~~

If:

~~~java
Point first = new Point(1, 2);
Point second = new Point(1, 2);
Point alias = first;
~~~

then:

| Expression | Result | Explanation |
| --- | --- | --- |
| `first == second` | false | Two separately created objects |
| `first.equals(second)` | true | Record equality by component values |
| `first == alias` | true | `alias` holds the same reference |
| `first.equals(alias)` | true | Same object and component values |

When drawing a **reference diagram**, use **identity** (labels #1, #2 or `==`), and do not merge two objects just because `equals` is true.

**Avoid using `System.identityHashCode` to infer an address or guarantee a unique object ID**: identity hash values can collide between different objects and are not memory addresses.

## 20. Static Variables Can Add Another Reference Path

A reference does not reside only in locals/parameters; it can also be held by a **static field**. A method can change a static field, producing an observable effect outside its parameters.

Example:

~~~java
class Registry {
    static Box latest;
}

static void register(Box box) {
    Registry.latest = box;
}
~~~

If `register(original)` is called, `Registry.latest` and the variable `original` both point to the object. If afterward `original = new Box(2)` runs in the caller, the static field **still points to the old object**.

These snippets are illustrative code. When solving a trace, add a row to the reference table for **`Registry.latest`**. A static field can keep an object reachable longer than local variables; a frame finishing does not automatically clear the reference in a static field.

For long-running applications, unbounded static caches/registries can cause **memory retention**. Do not assume that merely letting a method return means every object created inside it will be collected immediately.

## 21. Calling an Instance Method and `this`: Another Path to the Object

Inside an instance method, `this` is a reference to the **receiver object** of the corresponding call.

~~~java
class Counter {
    int value;

    void increase() {
        this.value++;
    }
}
~~~

If:

~~~java
Counter a = new Counter();
Counter b = a;
b.increase();
~~~

then during the `increase` call, `this` points to **the same Counter object** as `a` and `b`. The change to `this.value` can be observed through both variables.

### `this` Does Not Create Another Object

The line `this.value++` has no `new` and is not a constructor call. `this(...)` is a separate syntax for calling another constructor of the same class **inside a constructor**, and must not be confused with `this.field` or `this.method()`.

If the method call starts from a field:

~~~java
container.item.increase();
~~~

then the `this` receiver of `increase` is **the Counter object that `container.item` currently references**, not the `container` object.

## 22. Polymorphism: A Variable's Type Can Differ from the Object's Runtime Type

When tracing references, do not equate the **declared type** with the **runtime class**.

~~~java
Animal pet = new Dog();
~~~

If `Dog extends Animal`, the variable `pet` has **declared type Animal** but points to a **Dog instance**. The assignment:

~~~java
Animal samePet = pet;
~~~

only copies the reference; it does not create another Animal object.

**Overriding:** An overridden instance method can dispatch based on the runtime class Dog. **Overloading:** The compiler chooses the overload signature based on the expression types at compile time. The two mechanisms are not the same and can appear at the same time.

### Standalone Runnable Example

Create **`PolymorphicTraceDemo.java`**:

~~~java
public class PolymorphicTraceDemo {
    static class Animal {
        String sound() {
            return "?";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }
    }

    static void inspect(Animal parameter) {
        System.out.println("sound=" + parameter.sound());
        parameter = new Dog();
        System.out.println("new sound=" + parameter.sound());
    }

    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        inspect(animal);

        System.out.println("same=" + (animal == dog));
        System.out.println("sound after=" + animal.sound());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PolymorphicTraceDemo.java
java PolymorphicTraceDemo
~~~

Stdout:

~~~text
sound=woof
new sound=woof
same=true
sound after=woof
~~~

`inspect(parameter)` initially holds a reference to Dog #1; the call `parameter.sound()` uses the Dog implementation. After `parameter = new Dog()`, parameter points to Dog #2, while `animal` and `dog` in the caller still point to Dog #1. Since both objects are Dogs, the output `woof` is not enough to distinguish identity; the line `same=true` confirms that the two variables **in the caller** still point to the same object.

**Technique when two objects print identical data:** Add an `==` comparison or assign each object a logical ID to avoid inferring that identical outputs mean the same object.

## 23. Recursion: Same Parameter Name, Many Different Calls

In recursion, a method can call itself, yet **each call has its own set of parameters/locals**.

~~~java
static void walk(Node current, int depth) {
    if (current == null) {
        return;
    }
    System.out.println(depth + ":" + current.label);
    walk(current.next, depth + 1);
}
~~~

If there is a chain Node #1 → #2 → #3 → null, then:

~~~text
walk(#1,0) frame 1: current -> #1
  walk(#2,1) frame 2: current -> #2
    walk(#3,2) frame 3: current -> #3
      walk(null,3) frame 4: current -> null, return
    return frame 3
  return frame 2
return frame 1
~~~

Reassigning `current` in a call at depth 2 does not automatically change `current` at depth 1. The parameters have the same name but belong to different **calls**, just like in a multi-level method chain.

### Watch Out for Cycles

If `last.next = first` creates a cycle in linked nodes, the `walk` method above can recurse infinitely until a `StackOverflowError` occurs. Java reference graphs allow cycles; do not assume a structure is always a null-terminated chain.

## 24. Runnable Example: Tracing Recursion and Reassigning a Parameter at Each Level

Create the file **`RecursiveReferenceTraceDemo.java`**:

~~~java
public class RecursiveReferenceTraceDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static void walk(Node current, int depth) {
        if (current == null) {
            System.out.println("end depth=" + depth);
            return;
        }

        System.out.println(depth + ":" + current.label);
        Node next = current.next;
        current = null;
        walk(next, depth + 1);
    }

    public static void main(String[] args) {
        Node first = new Node("A");
        Node second = new Node("B");
        first.next = second;

        walk(first, 0);

        System.out.println("first.next=" + first.next.label);
        System.out.println("second=" + second.label);
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecursiveReferenceTraceDemo.java
java RecursiveReferenceTraceDemo
~~~

Stdout:

~~~text
0:A
1:B
end depth=2
first.next=B
second=B
~~~

Inside each frame:

1. It saves `current.next` into local `next`, so it still holds a reference to the next node.
2. `current = null` only reassigns the parameter of **the current frame**, without deleting the node and without setting `first = null` or `first.next = null`.
3. `walk(next, depth + 1)` passes a **copy of the reference** to the next node into the new frame.
4. After all calls return, `first.next` still points to Node B; `second` still points to Node B.

The line `current = null` **does not free the object immediately**; other aliases and the `first.next` field still keep the object reachable. The purpose of this line is only to illustrate reassigning a parameter.

## 25. Object Graphs with Cycles and Visited Checks

A structure can involve sharing or cycles:

~~~text
Node A.next -> Node B
Node B.next -> Node C
Node C.next -> Node A
~~~

You cannot traverse with a "keep moving forward until `null`" algorithm if all edges form a cycle. You need to record the **visited object identities**. With some APIs, `HashSet<Node>` relies on `equals/hashCode`; if Node overrides equality by value, two different objects may be treated as one. When the goal is to trace **identity**, you can use a set backed by `IdentityHashMap`.

Illustrative example:

~~~java
java.util.Set<Node> visited =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<>());

Node current = first;
while (current != null && visited.add(current)) {
    System.out.println(current.label);
    current = current.next;
}
~~~

This is an **illustrative code snippet** that requires an appropriate `Node` and `first`. `visited.add(current)` returns true only when the reference points to a Node object not yet recorded by **identity**, so the loop stops when it encounters the same object again.

Use identity tracking when the problem is a **reference graph**; do not automatically replace business equality with identity in every collection. If the goal is to compare two products with the same ID, domain-based `equals` may be more appropriate.

## 26. Exceptions Thrown at a Deep Level Do Not Automatically Undo Object Modifications at Upper Levels

A call can modify a shared object and then throw an exception. If the caller catches the exception, the object may **still carry the modified state**.

Create the file **`ExceptionReferenceTraceDemo.java`**:

~~~java
public class ExceptionReferenceTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void deepest(Box item) {
        item.value += 10;
        throw new IllegalStateException("stop");
    }

    static void middle(Box item) {
        item.value += 2;
        deepest(item);
        item.value += 100; // Not executed.
    }

    public static void main(String[] args) {
        Box original = new Box(1);

        try {
            middle(original);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("after=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExceptionReferenceTraceDemo.java
java ExceptionReferenceTraceDemo
~~~

Stdout:

~~~text
caught=stop
after=13
~~~

Trace:

- `main.original`, `middle.item`, and `deepest.item` all initially point to Box #1.
- `middle` adds 2; Box #1 changes from 1 to 3.
- `deepest` adds 10; Box #1 changes from 3 to 13.
- `deepest` throws `IllegalStateException`. The statement `item.value += 100` after the `deepest` call in middle **does not run**.
- The `catch` block in main handles the exception, yet **does not roll back** the two object modifications already performed, so `after=13`.

If business rules require **atomic** changes, you must design an appropriate transaction, state copy, or recovery mechanism; throwing an exception cannot be treated as an automatic object rollback.

## 27. Argument Evaluation Order Affects Tracing

Java evaluates argument expressions **from left to right**. If they have side effects on the same object, the values passed into the method afterward may differ from expectations.

Create **`ArgumentTraceDemo.java`**:

~~~java
public class ArgumentTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static int bump(Box box) {
        box.value++;
        System.out.println("bump=" + box.value);
        return box.value;
    }

    static void receive(Box box, int before, int after) {
        System.out.println("receive=" + box.value + "," + before + "," + after);
    }

    public static void main(String[] args) {
        Box box = new Box(1);

        receive(box, bump(box), bump(box));

        System.out.println("main=" + box.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentTraceDemo.java
java ArgumentTraceDemo
~~~

Stdout:

~~~text
bump=2
bump=3
receive=3,2,3
main=3
~~~

Explanation:

1. The first argument `box` is evaluated: the reference to Box #1.
2. The second argument `bump(box)` is called, modifying Box #1 to 2 and returning `int 2`.
3. The third argument `bump(box)` runs, modifying the same Box #1 to 3 and returning `int 3`.
4. The `receive` method begins; the Box parameter points to the same Box #1 whose state is **currently 3**, while `before` and `after` hold **the already computed primitive values 2 and 3**.
5. `main` continues and sees `box.value = 3`.

There are not three Box instances. This is just **one object** read/modified across multiple calls. In real-world code, avoid complex side effects directly inside an argument list if they make the order hard to understand.

## 28. Distinguishing Creating a New Object in the Callee vs. Before the Call

Two calls look similar:

~~~java
replace(new Box(5));
~~~

and:

~~~java
Box original = new Box(5);
replace(original);
~~~

In both cases, the callee receives a copy of the reference to a Box object. The difference is that the second caller **separately stores the reference** `original` so it can still use it after the call; the first caller does not directly store the result of `new` into a variable from that statement itself.

However, do not conclude that the object from the first call is always collected as soon as the method returns. The callee may return the reference, assign it to a field, or place the object into another collection, keeping the object reachable. How many aliases exist and where they reside are what determine the access paths to the object, not merely whether the code has a local variable named `original`.

## 29. Common Mistakes When Tracing Across Multiple Methods

| Incorrect Reasoning | Why Is It Wrong? | How to Fix It |
| --- | --- | --- |
| "An object parameter is the caller's variable." | A parameter is a separate variable for that call, receiving only a copy of the reference. | Draw separate frames for caller/callee. |
| "Setting `parameter = new X()` makes the caller point to the new object." | It only assigns the parameter. | Record the arrow of the exact variable being assigned. |
| "If a field is modified in the callee, the caller won't know." | Two references can point to the same mutable object. | Update the state table of the shared object. |
| "Two differently named parameters are always two objects." | The caller can pass the same reference to both. | Check the identity of each parameter. |
| "The same parameter name in two methods is one variable." | Two calls have separate scopes/frames. | Label them `middle.item` and `deep.item`. |
| "Two objects with the same data are one object." | Identity differs from value equality. | Count creations and assign object ID labels. |
| "Assigning `node.next = x` changes `node`'s reference." | This assigns a **field reference**, not the `node` variable. | Trace arrows coming from fields. |
| "An array is just a list of values, not an object." | An array has identity and reference elements. | Draw the array object and each slot. |
| "`final` makes an object unmodifiable." | It prevents reassigning the variable/field, and does not automatically make the object immutable. | Separate reference immutability from object mutability. |
| "A method returning a reference clones the object." | `return parameter;` can return the same object. | Find where a new object is actually created. |
| "Casting or upcasting creates a new object." | Valid reference type conversion does not clone the instance. | Keep the same object ID after the cast. |
| "Changing a parameter at a deep recursion level changes upper levels too." | Each recursive call has its own parameter. | Build a table by depth/frame. |
| "Throwing an exception restores all old fields." | Side effects are not automatically rolled back. | Track all modifications made before the exception. |
| "Arguments are evaluated simultaneously." | Java evaluates them in left-to-right order. | Trace side effects during evaluation. |
| "An object leaving local scope is GC'd immediately." | Aliases, fields, returns, or static references may still exist. | Trace reachability instead of guessing GC timing. |

## 30. A Six-Step Method for Solving Trace Exercises

For an exercise with multiple methods/classes and tangled assignments, proceed **sequentially**:

**Step 1 — List the objects and label them.** Each successfully executed instance/array creation expression receives an ID `#1`, `#2`, ...; do not count a reference assignment as creating a new object.

**Step 2 — Build an object state table.** Record primitive fields, reference fields, and array elements. For reference fields, record the target object ID instead of merely writing `"has object"`.

**Step 3 — Build a variable table per frame.** Do not merge the `item` variable of method A with `item` of method B. Write `main.item`, `A.item`, `B.item`, or label by call count if recursive.

**Step 4 — Follow execution order.** Evaluate arguments, call the method, execute the statements in exact order, and then return to the caller. For exceptions, follow the unwind path rather than continuing to run lines after the throw statement.

**Step 5 — Classify each assignment.** If the left-hand side is a **reference variable/parameter**, change only that variable's target. If it is a **field or array slot**, modify the link/state inside the currently referenced object. If it is a **primitive field**, modify the value inside the object; if it is a primitive parameter, modify only the parameter.

**Step 6 — Compute output from the state at the exact moment.** `println` reads the field **when it runs**, not when the reference was assigned. For `==`, ask whether it is the same object identity; for `equals`, check the specific contract of the class.

### A Table Template You Can Copy Onto Paper

| Statement / checkpoint | Frame | Variable changing reference | Object / field changed | Output |
| --- | --- | --- | --- | --- |
| `new Box(1)` | main | `main.a → #1` | Create #1, `value=1` | — |
| `call(a)` | callee | `callee.p → #1` | Does not automatically modify fields | — |
| `p.value++` | callee | None | `#1.value: 1 → 2` | — |
| `p = new Box(9)` | callee | `callee.p → #2` | Create #2, `value=9` | — |
| `return` | callee → main | Callee variables become inactive | #1 still has `value=2` | — |
| `println(a.value)` | main | None | None | `2` |

This template works well for **a normal call chain**, **recursive calls**, and **object graphs** if you add a column for links between fields.

## 31. Practice Exercise 1 — Two Paths Through the Same Object

Given two classes:

~~~java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

static void apply(Box first, Box second) {
    first.value += 4;
    second = new Box(50);
    second.value += 2;
}
~~~

Assume the `apply` method resides in an appropriate class. Caller:

~~~java
Box a = new Box(1);
Box b = a;
apply(a, b);
System.out.println(a.value);
System.out.println(b.value);
System.out.println(a == b);
~~~

**Predict it yourself, then check:** stdout is

~~~text
5
5
true
~~~

Explanation: both caller variables point to Box #1. `first.value += 4` modifies #1 to 5. `second = new Box(50)` creates Box #2 and changes **only the parameter second**; it does not reassign the caller's `b`. After the method finishes, `a` and `b` still point to the same #1.

## 32. Practice Exercise 2 — Changing a Reference Field in a Shared Object

Suppose:

~~~java
class Holder {
    Box value;
}

static void attach(Holder holder, Box box) {
    holder.value = box;
    box = new Box(99);
}
~~~

Caller:

~~~java
Holder h = new Holder();
Box a = new Box(7);
attach(h, a);
System.out.println(h.value == a);
System.out.println(h.value.value);
~~~

Stdout:

~~~text
true
7
~~~

`holder.value = box` modifies **a field of the Holder object**; it is allowed to make `h.value` in the caller point to Box #1. However, `box = new Box(99)` only reassigns the parameter `box`. No statement sets `h.value` to Box #2.

The snippets in these two exercises are **code fragments to be placed into a valid Java file**, not standalone programs. You need to place the static methods inside a class and use the corresponding Box/Holder classes.

## 33. Practice Exercise 3 — Two Objects Linked Through a Field

~~~java
class Node {
    Node next;
    int value;

    Node(int value) {
        this.value = value;
    }
}

static void modify(Node n) {
    Node oldNext = n.next;
    n.next = new Node(30);
    oldNext.value += 5;
}
~~~

Caller:

~~~java
Node a = new Node(1);
Node b = new Node(2);
a.next = b;
modify(a);
System.out.println(a.next.value);
System.out.println(b.value);
System.out.println(a.next == b);
~~~

Stdout:

~~~text
30
7
false
~~~

Inside `modify`, `oldNext` holds the reference to Node `b` **before** `n.next` is assigned to a new Node. Reassigning the field `n.next` does not cause `oldNext` to lose the old object. `oldNext.value += 5` therefore increments Node B from 2 to 7. The graph after the call has `a.next → new Node (30)` and `b → old Node (7)`.

## 34. Practice Exercise 4 — Returning a Reference Across Two Levels

~~~java
static Box inner(Box input) {
    input.value++;
    return input;
}

static Box outer(Box input) {
    Box returned = inner(input);
    returned = new Box(returned.value + 5);
    return returned;
}
~~~

Caller:

~~~java
Box a = new Box(1);
Box b = outer(a);
System.out.println(a.value);
System.out.println(b.value);
System.out.println(a == b);
~~~

Stdout:

~~~text
2
7
false
~~~

`inner` modifies Box #1 to 2 and returns that same reference #1. `outer` creates Box #2 with value 7 and returns #2. The caller's `a` continues pointing to #1 (2), and `b` points to #2 (7). Assigning the variable `returned` in outer does not automatically assign `a` in main.

## 35. Practice Exercise 5 — Recursive Parameters Are Not One Single Variable

~~~java
static void visit(Box box, int depth) {
    if (depth == 0) {
        return;
    }

    box.value++;
    Box next = new Box(box.value);
    visit(next, depth - 1);
}
~~~

Caller:

~~~java
Box first = new Box(1);
visit(first, 3);
System.out.println(first.value);
~~~

The output is `2`. At depth 3, the method modifies Box #1 from 1 to 2, creates Box #2 with 2, and calls depth 2 on Box #2. At depth 2, the method modifies Box #2 from 2 to 3 and creates Box #3; at depth 1, it modifies Box #3 from 3 to 4. Those new objects do not automatically become the variable `first`; therefore `first.value` remains 2.

This is an illustrative code snippet, not a standalone runnable program. The lesson is to **trace each frame and each `new` instantiation** instead of applying all increments to a single object.

## 36. Situations to Watch Out for in Real-World Practice

### Null Reference

If a parameter receives null, `parameter = new Box(...)` is a valid reassignment for the parameter variable, but it does not update the caller. If earlier code accesses `parameter.value` while parameter is null, an NPE will occur. When tracing, explicitly write a "null" arrow instead of drawing a dummy object.

### Immutable Objects

`String` is a reference type, yet it is immutable. `text = text + "!"` usually causes the variable `text` to reference a new resulting string; it does not modify the old string held by other aliases. Therefore, sharing a reference does not always create the ability to mutate state: **whether an object is mutable or immutable** determines this.

### Constructor/Factory

If a constructor/factory creates two objects and links them via fields, you must draw each object and field link. A constructor that throws an exception does not successfully return a reference to the caller from the `new` expression, yet side effects already executed before the exception are not automatically rolled back.

### Collection Copy

`new ArrayList<>(existing)` creates a new collection object, yet **copies the element references**. The two collections may not alias each other at the container level while still sharing mutable element objects. This is a shallow copy; if deep independence is desired, you need a deep copy strategy tailored to the data model.

### Multiple Threads

If two threads concurrently modify a mutable object through aliased references, you need synchronization/atomicity/visibility rules from the Java Memory Model. The **sequential** trace table in this article does not by itself prove that a multithreaded program is thread-safe. In particular, `value++` is not an atomic increment across multiple threads.

### Garbage Collection

When a parameter or local ceases to be active, the object is not necessarily collected immediately: a field, static, array, return value, or another alias may still keep the object reachable. Do not use `System.gc()` or `identityHashCode` to "prove" which object just disappeared.

## 37. Self-Assessment Checklist

- [ ] I can distinguish between a reference variable, a reference value, object identity, and field state.
- [ ] I know that each method call has its own parameters/locals belonging to **that call**.
- [ ] I know that Java passes **a copy of the reference value**, not the caller's variable by reference.
- [ ] I can draw a two-column table: **variable → object ID**, **object ID → state**.
- [ ] I can correctly identify when `p = new X()` only reassigns the parameter.
- [ ] I can correctly identify when `p.field = ...` modifies an object that the caller may still reference.
- [ ] I can predict the result when the same object is passed through **two parameters**.
- [ ] I can trace references through a chain `main → A → B → C` and on the return path.
- [ ] I know that `return parameter;` does not automatically clone the object, and the caller must explicitly assign the result if it wants to change its reference.
- [ ] I know that an object can contain a **reference field** to another object and form a multi-level alias graph.
- [ ] I can distinguish modifying a field link from reassigning the variable holding the object.
- [ ] I know that an array is an object; array slots can hold references to the same element object.
- [ ] I can distinguish a changing primitive field from a changing primitive parameter.
- [ ] I can distinguish a `final` reference from an immutable object.
- [ ] I can distinguish identity via `==` from equality via `equals`.
- [ ] I understand that upcasting does not create a new object and overriding dispatches based on the runtime object.
- [ ] I know that each recursive call has its own frame/parameter; modifying a reference at a deep level does not modify variables at upper levels.
- [ ] I can trace side effects on an object made before an exception is thrown.
- [ ] I can evaluate argument evaluation order correctly from left to right.
- [ ] I do not predict GC or RAM addresses from the arrow diagram model.
- [ ] I can compile, run, and explain each stdout of the Java 17+ programs in this article on my own.

**Conclusion:** To trace references across multiple calls and multiple objects, do not ask "is this object variable passed by reference or by value?". Java already has the answer: **always pass-by-value**. Ask more specific questions: **which reference copy does each parameter currently hold; which objects are created; which fields/array slots are modified; which variables are reassigned; and which references are returned?** Breaking those questions into tables per call and per object is a reliable method for accurately predicting every change in Java trace exercises.
