# Reference Assignment Does Not Create a New Object in Java

## 1. The Nature of Reference Assignment

In Java, a variable of a reference type (for example `Person`, `String`, an array, or `List`) holds a **reference value pointing to an object**, or the value `null`. With the assignment `b = a`, Java copies the **reference value** of `a` into the variable `b`. The assignment itself does not create an additional object and does not copy the object's fields.

~~~java
Box first = new Box("A"); // new Box(...) creates the object.
Box alias = first;        // Copies the reference, does not create a second Box.
~~~

Afterward, `first` and `alias` are **two separate variables referencing the same Box**:

~~~text
first ──┐
        ├──► Box { value = "A" }
alias ──┘
~~~

Declaring a reference variable is not equivalent to creating an object of the referenced class. In `Box first = new Box("A")`, the **`new` expression** brings the object into existence, while the assignment merely places the reference into `first`. The statement “assignment does not create a new object” refers to the reference-copying operation; it does not deny that the **right-hand expression** may itself create an object.

## 2. Complete Example: Aliasing, Mutating State, and Reassignment

Create the file `ReferenceAssignmentDemo.java`:

~~~java
public class ReferenceAssignmentDemo {
    static final class Box {
        String value;

        Box(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box alias = first;

        System.out.println("same after assignment: " + (first == alias));

        alias.value = "B";
        System.out.println("first.value: " + first.value);

        alias = new Box("C");
        System.out.println("same after rebinding: " + (first == alias));
        System.out.println("first.value: " + first.value);
        System.out.println("alias.value: " + alias.value);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 ReferenceAssignmentDemo.java
java ReferenceAssignmentDemo
~~~

Stdout:

~~~text
same after assignment: true
first.value: B
same after rebinding: false
first.value: B
alias.value: C
~~~

Read step by step:

1. `new Box("A")` creates a Box object, and `first` receives a reference to that object.
2. `Box alias = first` copies the reference into `alias`, so `first == alias` is `true`.
3. `alias.value = "B"` **modifies the state of the shared object**. Through `first.value`, we also see `"B"`.
4. `alias = new Box("C")` creates a second Box and assigns the reference of the new Box to **only the variable** `alias`.
5. `first` still points to the Box with `value = "B"`; `alias` points to the Box with `value = "C"`. The two variables no longer share the same reference, so `==` returns `false`.

You must distinguish two operations:

- **Modifying the object:** `alias.value = "B"` affects the object that the aliases point to.
- **Reassigning the variable:** `alias = other`, `alias = null`, or `alias = new Box(...)` changes the reference value inside `alias` alone. This statement does not itself modify the old object and does not change the value of `first`.

## 3. Difference from Primitive Assignment

For primitive types, the copied value is a direct number, character, or boolean value:

~~~java
int a = 10;
int b = a;
b = 20;
System.out.println(a); // 10
System.out.println(b); // 20
~~~

For reference types, assignment still copies a **value**, but that value points to an object. Reference variables are independent when **reassigned**, even though they can **share an object**. Therefore, you should not call `Box b = a` “copying a Box”.

## 4. Object Identity: == Differs from equals

`==` on two compatible references checks whether they have the same reference value: the same object, or both `null`. `equals(Object)` is a method for a class to define the meaning of “equal” by convention; many classes, such as `String`, override this method to compare content. If a class does not override it, it inherits identity-comparison behavior from `Object`.

~~~java
String x = new String("java");
String y = new String("java");
System.out.println(x == y);      // false
System.out.println(x.equals(y)); // true
~~~

The two `new String("java")` expressions create two different String objects, yet the content of both strings is equal. Only use `new String(...)` here to demonstrate identity; for ordinary strings, use literals such as `"java"`.

Do not rely on `System.identityHashCode(obj)` to prove identity: the identity hash code is not guaranteed to be unique for every object. To tell whether two references point to **the exact same object**, use `==`.

## 5. Passing Objects to Methods: Java Still Passes by Value

Java always **passes parameters by value**. When the argument is a reference variable, the method parameter receives a **copy of the reference value**. Because of this, a method can modify a shared object, but reassigning the parameter cannot cause the caller's variable to change its reference on its own.

Create the file `ParameterPassingDemo.java`:

~~~java
public class ParameterPassingDemo {
    static class Box {
        String value;

        Box(String value) {
            this.value = value;
        }
    }

    static void reassign(Box parameter) {
        parameter = new Box("new");
    }

    static void mutate(Box parameter) {
        parameter.value = "changed";
    }

    public static void main(String[] args) {
        Box original = new Box("initial");

        reassign(original);
        System.out.println("after reassign: " + original.value);

        mutate(original);
        System.out.println("after mutate: " + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterPassingDemo.java
java ParameterPassingDemo
~~~

Stdout:

~~~text
after reassign: initial
after mutate: changed
~~~

In `reassign`, the local variable `parameter` receives a reference to a new object, but `original` on the caller side is not reassigned. In `mutate`, the parameter and `original` both reference the original Box, so the change to `value` is observed outside. If you want the caller to switch to another object, **return the reference** and assign it explicitly on the caller side, such as `original = createBox();`.

## 6. final, null, and Object Reachability

### A final Variable Does Not Mean an Immutable Object

~~~java
final Box selected = new Box("A");
selected.value = "B";      // Allowed if the object has mutable fields.
// selected = new Box("C"); // Does not compile if // is removed: selected is final.
~~~

`final` forbids reassigning the **variable**; it does not make the object immutable. An immutable object is the result of class design, for example exposing only operations that do not mutate state.

### null Does Not Create or Destroy an Object

~~~java
Box first = new Box("A");
Box alias = first;
first = null;
// alias still references Box("A").
~~~

`Box b = null` does not create any Box. `first = null` only changes the reference in `first`; the old Box can still be accessed through `alias`. When an object is no longer reachable through appropriate strong reference paths, it may become eligible to be reclaimed by the garbage collector; Java does not guarantee immediate reclamation at the moment a variable is assigned.

Attempting to access a field or call an instance method through a `null` reference causes `NullPointerException`. Comparing `b == null` or assigning `b = null` by itself remains valid.

## 7. Arrays, Collections, and True Copying

Arrays are also objects, so array assignment creates an alias:

~~~java
int[] numbers = {1, 2};
int[] same = numbers;
same[0] = 99;
System.out.println(numbers[0]);      // 99
System.out.println(numbers == same); // true
~~~

The same holds for collections: `List<String> b = a;` does not create a new list; `a` and `b` point to the same List, so adding/removing elements through one variable is observed by the other.

If you want to create an **independent container object**, you must explicitly request creation or copying:

~~~java
int[] copy = numbers.clone();
System.out.println(numbers == copy); // false
~~~

An array's `clone()` creates a new array. For an **array containing references**, this is a **shallow copy**: the new array still holds references to the old element objects. Similarly, `new ArrayList<>(oldList)` creates a new List, but its reference-type elements are not automatically deep-copied. If every custom element needs to be independent, you must build a rule to copy each element (a copy constructor or an appropriate copy-creating method).

### The String Case

~~~java
String first = "Java";
String alias = first;
alias = alias + " 17";
System.out.println(first); // Java
~~~

The two variables initially reference the same String. However, `String` is **immutable**: concatenation constructs a new string value and assigns the result to `alias`, without modifying the string that `first` references. Therefore, you cannot use the string example to conclude that mutable objects also do not share state changes.

## 8. Common Misconceptions

| Misconception | What Actually Happens |
| --- | --- |
| `Box b = a` creates a copy of Box. | False. `b` and `a` reference the same Box. |
| `b.field = x` is the same as `b = other`. | The first modifies the object; the second reassigns the variable `b`. |
| Java passes references “by reference”, so a method can reassign the caller's variable. | False. The parameter receives a copy of the reference value. |
| Two objects with the same data have `==` equal to `true`. | False. `==` compares identity; `equals` can compare content if the class defines it. |
| A `final` variable makes the object immutable. | False for mutable objects. |
| Assigning `null` or reassigning to a new object immediately deletes the old object. | False. Reachability and GC timing are separate matters. |
| Copying a List/array deep-copies every element. | False for standard shallow copies. |

## 9. Technique for Predicting Results When Reading Code

Draw each **object** as a box and each **reference variable** as an arrow. When encountering `new` (or an operation that actually creates an object), add the corresponding box. When encountering `b = a`, simply update `b`'s arrow to match `a`. When encountering `b.field = value`, update the field inside the box that `b` currently points to. When encountering `b = null`, erase `b`'s arrow alone. When encountering `b = new Box(...)`, draw a new box and point only `b`'s arrow to it.

This method cleanly separates **object identity**, **shared state**, and **each variable's reference value**. It is sufficient to reason about aliasing without needing to know actual memory addresses or how the JVM lays out objects.