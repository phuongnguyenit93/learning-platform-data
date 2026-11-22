# Analyzing a Failed Two-Reference Swap Example in Java

## Learning Objectives

After this lesson, you can:

- Explain why a `swap(a, b)` method that receives two objects as arguments **cannot swap the caller's two reference variables** by reassigning the two parameters.
- Trace the reference values step by step before the call, during the call, and after the method returns.
- Distinguish **reference variables** from **objects**, **reassigning a reference** from **modifying object state**, and **pass-by-value** from true pass-by-reference.
- Recognize why parameter names matching caller variable names, generic methods, `Object` and `String` types, `final`, or the `static` keyword do not change Java's pass-by-value rule.
- Explain why two variables referencing the same object, array elements, fields of a holder object, and local variables behave differently when you want to “swap” them.
- Perform an actual swap by **modifying the storage location of the references** such as array/`List` elements, **modifying a holder's fields**, or **returning a pair of results and having the caller explicitly reassign them**.
- Compile Java 17+ examples yourself, predict stdout, and identify common misconceptions.

## 1. Problem Statement: Assuming `swap` Will Swap Two Variables

Suppose you have two objects:

~~~java
Box first = new Box("A");
Box second = new Box("B");
~~~

You want, after calling a method:

~~~java
swap(first, second);
~~~

for the variable `first` to reference Box B and the variable `second` to reference Box A. A beginner might easily write:

~~~java
static void swap(Box a, Box b) {
    Box temp = a;
    a = b;
    b = temp;
}
~~~

This code is an **illustrative method declaration** that needs to be placed in a class with the `Box` type. The swap logic *seems* correct because at the end of the method: parameter `a` holds the value that was in `b`, and parameter `b` holds the value that was in `a`.

However, when the call finishes:

- `first` still references **Box A**.
- `second` still references **Box B**.
- The two parameters `a` and `b` have been reassigned **inside the call**, not the caller's two variables.

This is a classic example for learning the semantics that **Java only passes parameters by value** (*pass-by-value*).

### 1.1. What Is Being Swapped?

In the snippet above, there are **at least four reference variables**:

| Variable | Where Does It Belong? | Role |
| --- | --- | --- |
| `first` | Caller scope | Holds a reference to Box A |
| `second` | Caller scope | Holds a reference to Box B |
| `a` | Parameter of the `swap` method | Initially receives a copy of `first`'s reference |
| `b` | Parameter of the `swap` method | Initially receives a copy of `second`'s reference |
| `temp` | Local variable in `swap` | Holds an intermediate reference copy |

The line `Box temp = a;` does **not** copy the contents of Box A: it copies the **reference value** that `a` holds. The line `a = b;` only assigns to **parameter variable `a`**; the line `b = temp;` only assigns to **parameter variable `b`**.

Multiple variables can hold the same reference, but **they do not become the same variable**.

## 2. Core Rule: Reference Values Are Also Passed by Value

In Java:

- For arguments of primitive types `int`, `double`, `boolean`..., the caller passes the **primitive value**.
- For arguments of reference types such as `Box`, `StringBuilder`, arrays, `List`..., the caller passes the **reference value to the object**.
- In both cases, **the callee's parameter variable is initialized from the argument value**. There is no language mechanism for a method to directly receive a “reference to the caller's local variable slot” in pass-by-reference style.

Example:

~~~java
static void changeNumber(int number) {
    number = 999;
}

static void changeReference(Box box) {
    box = new Box("new");
}
~~~

Both declarations are illustrative inside a class that has `Box`. The first method reassigns a primitive parameter; the second method reassigns a reference parameter. **Neither itself reassigns the variable the caller used to pass the argument**.

In the call `swap(first, second)`, Java does not give the method access to the caller's two local variables named `first` and `second`. It only gives the method two parameter variables `a`, `b` holding **the copied reference values**.

### 2.1. “Pass object by reference” Is Misleading Phrasing

Some people describe Java as “passing objects by reference”, meaning that the object is **not deep-copied** when passed into a method. If interpreted loosely, this statement can cause misunderstanding.

A more accurate phrasing:

> Java is **pass-by-value**. When an argument has a reference type, **the copied value is the object reference**. The callee can use this reference to access the same object, but cannot reassign the caller's reference variable by reassigning the parameter.

Consequences:

- **Modifying the object:** can be observed by the caller when both sides point to a mutable object.
- **Reassigning the parameter:** only changes the callee's local parameter reference, not the reference variable on the caller side.

## 3. Standalone Runnable Example: Swap Fails Even Though Swapped Inside

Save as **`FailedReferenceSwapDemo.java`**:

~~~java
public class FailedReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static void swap(Box a, Box b) {
        System.out.println("inside before=" + a.id + "," + b.id);
        Box temp = a;
        a = b;
        b = temp;
        System.out.println("inside after=" + a.id + "," + b.id);
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = new Box("B");

        Box originalFirst = first;
        Box originalSecond = second;

        System.out.println("outside before=" + first.id + "," + second.id);
        swap(first, second);
        System.out.println("outside after=" + first.id + "," + second.id);
        System.out.println("same first=" + (first == originalFirst));
        System.out.println("same second=" + (second == originalSecond));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac FailedReferenceSwapDemo.java
java FailedReferenceSwapDemo
~~~

**Exact stdout:**

~~~text
outside before=A,B
inside before=A,B
inside after=B,A
outside after=A,B
same first=true
same second=true
~~~

**Output explanation:**

1. Before the call, `first` points to Box A and `second` points to Box B.
2. `swap(first, second)` **copies the two reference values** into parameters `a` and `b`.
3. At the start of the method, `a.id` is A and `b.id` is B.
4. The three assignments `temp = a; a = b; b = temp;` actually swap the **two parameter variables** inside the method. Therefore, the `inside after` line prints B,A.
5. When the method returns, no assignments were performed on **variables `first`, `second` in `main`**. Therefore, `outside after` is still A,B.
6. The comparisons `first == originalFirst` and `second == originalSecond` are both `true`: the caller's two variables still point to the exact original objects.

**Notably:** the two objects Box A and Box B **do not swap positions in memory**, nor are they copied. Only the local reference variables inside `swap` change places.

## 4. Drawing Reference States Before, During, and After the Call

### 4.1. Before `swap(first, second)`

~~~text
CALLER
first  -----------------> Box A { id = "A" }
second -----------------> Box B { id = "B" }
~~~

### 4.2. Immediately Upon Entering `swap`

The callee is initialized with two independent parameters:

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ a
second ---------> Box B <------ b
~~~

The arrows from `first` and `a` both point to **Box A**. That does not mean `first` and `a` are the same variable.

### 4.3. After `temp = a;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ a, temp
second ---------> Box B <------ b
~~~

The new `temp` variable stores the Box A reference. No Box C is created.

### 4.4. After `a = b;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ temp
second ---------> Box B <------ a, b
~~~

Only variable `a` points to Box B. Variable `first` still points to Box A.

### 4.5. After `b = temp;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ b, temp
second ---------> Box B <------ a
~~~

Parameters `a` and `b` have swapped the objects they reference; whereas `first` and `second` **are unchanged**.

### 4.6. After `swap` Returns

~~~text
CALLER
first  -----------------> Box A { id = "A" }
second -----------------> Box B { id = "B" }
~~~

The local variables `a`, `b`, `temp` of the call can no longer be used from the caller. There is no “write back changed parameters” operation into the caller's argument variables.

Note that the diagram only depicts reference relationships. Java does not guarantee that a reference must be a specific machine address, or that objects must be stored at the positions shown in the diagram.

## 5. Why Do `swap(Object a, Object b)` and Generic `swap(T a, T b)` Also Fail?

Changing the **declared parameter type** does not change the passing mechanism:

~~~java
static void swapObjects(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}

static <T> void swapGeneric(T a, T b) {
    T temp = a;
    a = b;
    b = temp;
}
~~~

These are valid method declarations in an appropriate class. Calling:

~~~java
swapObjects(first, second);
swapGeneric(first, second);
~~~

still only reassigns the **two parameter references** inside the callee.

The generic type parameter `T` allows reusing the method with multiple object types and adds static type checking. It does **not** turn parameter `T a` into a reference to **the caller's variable**. Similarly, using `Object` as the parameter type does not grant permission to modify the caller's variable.

### 5.1. Why Does Renaming Parameters Also Have No Effect?

~~~java
static void swap(Box first, Box second) {
    Box temp = first;
    first = second;
    second = temp;
}
~~~

Even when the callee's parameters have the same names as the local variables in the caller, they are still **two variable declarations belonging to different scopes**. Identical spelling does not create an implicit binding.

### 5.2. `final` and Parameter Swapping

If you write:

~~~java
static void swap(final Box a, final Box b) {
    // a = b; // Invalid because a is a final parameter
}
~~~

the compiler **prevents parameter reassignment**, so even swapping the two local parameter variables like in the initial incorrect example cannot be written that way.

Not using `final` does not mean the caller's variables can be modified. Whether parameters can be reassigned or not, they still receive references **by value**.

## 6. Modifying Object State Can Succeed, but It Is Not Swapping References

This is the most important point after understanding the failed example. If a method **calls a mutating method** or **writes to an object's field**, the caller can observe the change because the parameter and the caller reference the same object.

Save **`MutationNotReferenceSwapDemo.java`**:

~~~java
public class MutationNotReferenceSwapDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void modifyThenSwapLocals(Box a, Box b) {
        a.value += 10;
        b.value += 20;

        Box temp = a;
        a = b;
        b = temp;

        a.value += 1;
        System.out.println("inside values=" + a.value + "," + b.value);
    }

    public static void main(String[] args) {
        Box first = new Box(1);
        Box second = new Box(2);

        Box firstBefore = first;
        Box secondBefore = second;

        modifyThenSwapLocals(first, second);

        System.out.println("outside values=" + first.value + "," + second.value);
        System.out.println("references unchanged=" +
                (first == firstBefore && second == secondBefore));
    }
}
~~~

Commands:

~~~bash
javac MutationNotReferenceSwapDemo.java
java MutationNotReferenceSwapDemo
~~~

Output:

~~~text
inside values=23,11
outside values=11,23
references unchanged=true
~~~

**Trace:**

- Initially, Box A.value = 1, Box B.value = 2.
- `a.value += 10` modifies Box A to 11.
- `b.value += 20` modifies Box B to 22.
- The three local swap assignments make `a` point to Box B and `b` point to Box A.
- `a.value += 1` now modifies Box B to 23.
- The callee prints `inside values=23,11`.
- The caller still has `first` → Box A (11), `second` → Box B (23). None of the caller's variables were swapped.
- `references unchanged=true` confirms that the caller's reference variables remain unchanged.

**Note the distinction:** The line `outside values=11,23` looks as though the two **numbers** “have swapped”, but in reality the method **modified the field values** without changing the positions of the caller's two references at all. This is why you should check both **object identity** and **object state** when analyzing.

### 6.1. Swapping Object Contents Differs from Swapping References

You can write a method that swaps field values:

~~~java
static void swapValues(Box a, Box b) {
    int temp = a.value;
    a.value = b.value;
    b.value = temp;
}
~~~

This is illustrative code with `Box.value` as a mutable `int` field. After `swapValues(first, second)`, **the values inside Box A and Box B** have swapped, while variable `first` still points to Box A and `second` still points to Box B.

If Box contains multiple fields, swapping one field does not mean “swapping the entire object”; attempting to swap every field can violate invariants, other aliasing, or constraints such as `final`. If the goal is to swap **reference variables**, a different solution is needed.

## 7. Why Can't Two Local Reference Variables Be Swapped via Ordinary Parameters?

In Java, when a method is called with two expressions such as:

~~~java
swap(first, second);
~~~

the callee only receives **two reference values**. It is not given a primitive “address of variable `first`” or a reference-to-variable that allows the statement `a = ...` to modify the caller's variable.

This remains true when:

- The two caller variables are instance fields and are passed as `swap(this.left, this.right)`.
- The two arguments are array elements, for example `swap(items[0], items[1])`.
- The method has parameter type `Object` or generic `<T>`.
- The method returns `void` or has another return type, yet the caller **does not reassign them itself**.
- The method is declared as a `static` or instance method.
- The arguments are mutable or immutable objects, or `null` (if the signature allows it).

**However:** a method **can modify fields or array elements on its own** if given a mutable object/array container. That is a different style of API: instead of receiving **the values at two locations**, the method receives **the storage locations of the values** via a mutable container.

Example:

~~~java
swap(items[0], items[1]); // Does not swap items[0] and items[1]
swapAt(items, 0, 1);      // Can swap the two elements in the items array
~~~

The two calls above have different meanings. The first call passes **the values of the two elements**; the second call passes **a reference to the array itself** and **two indices**, allowing the method to update those elements.

## 8. Correct Approach 1: Swapping Two Elements in an Array

Save **`ArrayReferenceSwapDemo.java`**:

~~~java
public class ArrayReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static <T> void ineffectiveSwap(T first, T second) {
        T temporary = first;
        first = second;
        second = temporary;
    }

    static <T> void swapAt(T[] items, int left, int right) {
        T temporary = items[left];
        items[left] = items[right];
        items[right] = temporary;
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");
        Box[] items = {a, b};

        ineffectiveSwap(items[0], items[1]);
        System.out.println("after ineffective=" + items[0].id + "," + items[1].id);

        swapAt(items, 0, 1);
        System.out.println("after swapAt=" + items[0].id + "," + items[1].id);

        System.out.println("items[0] is b=" + (items[0] == b));
        System.out.println("items[1] is a=" + (items[1] == a));
        System.out.println("caller a=" + a.id + ", caller b=" + b.id);
    }
}
~~~

Compile/run:

~~~bash
javac ArrayReferenceSwapDemo.java
java ArrayReferenceSwapDemo
~~~

Output:

~~~text
after ineffective=A,B
after swapAt=B,A
items[0] is b=true
items[1] is a=true
caller a=A, caller b=B
~~~

**Explanation:**

- `ineffectiveSwap(items[0], items[1])` reads the **two reference values** from the array and passes copies into the method. The reassignments to `first` and `second` only change the parameters; the `items` array does not change.
- `swapAt(items, 0, 1)` receives a **copy of the reference to the `items` array** along with two primitive indices.
- Although parameter `items` is also passed by value, it points to **the same array object** as the caller.
- The statements `items[left] = items[right]` and `items[right] = temporary` directly **modify the elements of the array object**. Therefore, the two array slots swap references.
- The two local variables `a` and `b` in `main` **still** point to the original Boxes. Swapping within the **array** does not automatically swap those two local variables.

### 8.1. Arrays Are Mutable Containers, but Indices Must Be Checked

`swapAt(items, i, j)` is only valid if `items` is not `null` and both indices are within the range `0 .. items.length-1`. Otherwise, Java can throw `NullPointerException` or `ArrayIndexOutOfBoundsException`.

If `i == j`, the three-step swap above reassigns the same element with its own value, so the order does not change. For a general-purpose API, you can check beforehand if clear error messages or performance are needed.

### 8.2. Are Generic Arrays `T[]` Always Safe?

Java allows declaring the method `static <T> void swapAt(T[] array, int i, int j)` as shown above. For elements taken from **the array itself**, they have a compatible type to be assigned back into that array. However, array covariance and runtime store checks are broader topics: do not infer from the fact that the generic method compiles that assigning any arbitrary object into an array is valid at runtime.

The main takeaway of the example does not depend on generics: modifying **array elements** mutates the container; modifying **local parameters** does not mutate caller variables.

## 9. Correct Approach 2: Using `List` and `Collections.swap`

For a mutable `List`, Java provides `java.util.Collections.swap(list, i, j)` to swap the elements at two positions.

Save **`ListReferenceSwapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");

        List<Box> boxes = new ArrayList<>(List.of(a, b));
        System.out.println("before=" + boxes.get(0).id + "," + boxes.get(1).id);

        Collections.swap(boxes, 0, 1);
        System.out.println("after=" + boxes.get(0).id + "," + boxes.get(1).id);

        System.out.println("box a still A=" + a.id);
        System.out.println("box b still B=" + b.id);
        System.out.println("positions swapped=" +
                (boxes.get(0) == b && boxes.get(1) == a));
    }
}
~~~

Run:

~~~bash
javac ListReferenceSwapDemo.java
java ListReferenceSwapDemo
~~~

Output:

~~~text
before=A,B
after=B,A
box a still A=A
box b still B=B
positions swapped=true
~~~

`Collections.swap` modifies **the slots in the `ArrayList`** and does not require swapping the two local variables `a` and `b`. If the list does not support `set` at those positions, the swap can throw `UnsupportedOperationException`. `List.of(a,b)` cannot be modified; therefore, the example wraps it in `new ArrayList<>(...)` to obtain a mutable list.

**API design:** if you are managing a list of objects, operate directly on the data structure containing them. There is no need to simulate pass-by-reference for local variables.

## 10. Correct Approach 3: Using Holder Objects to Swap Reference Fields

If the business logic requires swapping two **storage slots** inside objects, you can create a holder type with a mutable field. The method receives references to the holder objects and **modifies the field** inside them.

Save **`HolderReferenceSwapDemo.java`**:

~~~java
public class HolderReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static final class Holder<T> {
        T value;

        Holder(T value) {
            this.value = value;
        }
    }

    static <T> void swapValues(Holder<T> left, Holder<T> right) {
        T temporary = left.value;
        left.value = right.value;
        right.value = temporary;
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");

        Holder<Box> first = new Holder<>(a);
        Holder<Box> second = new Holder<>(b);

        swapValues(first, second);

        System.out.println("first holder=" + first.value.id);
        System.out.println("second holder=" + second.value.id);
        System.out.println("holders unchanged=" +
                (first != second));
        System.out.println("first points to b=" + (first.value == b));
    }
}
~~~

Compile/run:

~~~bash
javac HolderReferenceSwapDemo.java
java HolderReferenceSwapDemo
~~~

Output:

~~~text
first holder=B
second holder=A
holders unchanged=true
first points to b=true
~~~

Here:

- `first` and `second` are two different **holder objects**.
- Parameters `left` and `right` receive **copies of the references** to the two holder objects.
- `left.value = right.value` and `right.value = temporary` modify **the `value` fields** of the holders that the caller still references.
- The caller variables `first`, `second` do not change their holder object; however, **the reference field content** of each holder has changed.

This is an **intentional mutating API**, not pass-by-reference of the `first` or `second` variables. If the holders/fields are shared across threads, swapping multiple fields is not automatically atomic; proper synchronization is required if multithreaded invariants are desired.

### 10.1. Should `AtomicReference` Be Used Instead of a Holder?

`AtomicReference<T>` is a reference holder type with primitive operations that have useful synchronization semantics. However, the two statements `left.set(right.get())` and `right.set(temp)` **do not form an atomic two-slot swap as a single unit**. They can be observed by another thread in an intermediate state without a coordinated synchronization mechanism.

Do not use `AtomicReference` merely hoping Java turns into pass-by-reference. It addresses specific concurrency/reference-update needs and **does not change the parameter-passing mechanism** of the language.

## 11. Correct Approach 4: Returning a Value Pair and Having the Caller Assign Them

To actually swap two **local variables** in the caller, the straightforward approach is for the method to return the new values and for **the caller to perform the assignments**.

In Java 17, a `record` can express a result pair more clearly than an `Object[]` array lacking specific element names/types.

Save **`SwapResultDemo.java`**:

~~~java
public class SwapResultDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    record Pair<T>(T first, T second) { }

    static <T> Pair<T> swapped(T left, T right) {
        return new Pair<>(right, left);
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = new Box("B");

        System.out.println("before=" + first.id + "," + second.id);

        Pair<Box> result = swapped(first, second);
        System.out.println("before assigning=" + first.id + "," + second.id);

        first = result.first();
        second = result.second();

        System.out.println("after assigning=" + first.id + "," + second.id);
    }
}
~~~

Commands:

~~~bash
javac SwapResultDemo.java
java SwapResultDemo
~~~

Output:

~~~text
before=A,B
before assigning=A,B
after assigning=B,A
~~~

**Why does this approach work?**

- The `swapped` method does **not** change the two local variables `first`, `second`; it only creates and returns a `Pair<Box>` value containing the two references in reversed order.
- After the method returns, the caller's variables still hold A/B (the `before assigning` line).
- It is the two assignments `first = result.first(); second = result.second();` in `main` that change the reference values stored in the caller's local variables.
- Because `Pair<Box>` holds both output values simultaneously, sequential assignment does not lose the old value; if you merely wrote `first = second; second = first;`, both would end up pointing to B.

### 11.1. What If the Caller Variables Are `final`?

With:

~~~java
final Box first = new Box("A");
final Box second = new Box("B");
~~~

you **cannot** reassign `first = ...` or `second = ...` after they are initialized. That is the policy of `final`, not a limitation of the factory/record.

If the code needs to keep immutable references, you can create **a new pair**:

~~~java
Pair<Box> original = new Pair<>(first, second);
Pair<Box> reversed = swapped(original.first(), original.second());
~~~

This is an illustrative snippet with appropriately declared `Box` and `Pair` types. There is no need to modify the `first`, `second` variables: the caller chooses to use `reversed` as the new logical result.

## 12. Distinguishing Common “Swap” Goals

The phrase “swapping two objects” can be interpreted in multiple ways. Before choosing code, ask **what exactly needs to change**.

| Goal | Approach | Does the Original Local Reference Variable Change? | Does Object Data Change? |
| --- | --- | --- | --- |
| Swap two parameter references of the callee | `swap(Box a, Box b)` using three assignments | **No** | No, if only assigning variables |
| Swap **field values** of two mutable Boxes | Write `a.value` and `b.value` | No | **Yes** |
| Swap two **array elements** | `swapAt(Box[] array,i,j)` | Array variable does not change | **Array entries change**; Box data does not need to change |
| Swap two **List elements** | `Collections.swap(list,i,j)` | List variable does not change | **List entries change** |
| Swap fields inside two holders | `swapValues(Holder<T>,Holder<T>)` | Holder variables do not change | **Holder fields change** |
| Swap two caller **local variables** | Return pair, caller reassigns | **Yes**, assigned by caller | Objects do not need to be modified |
| Create a reversed view without modifying original data | Return a new pair/list in reversed order | No | Does not modify original data |

**Do not call every result that looks like B,A a “successful reference swap”.** Distinguish where the modified references are stored: **parameter variables**, **caller variables**, **array elements**, **list elements**, **object fields**.

## 13. When Both Variables Reference the Same Object

Suppose:

~~~java
Box first = new Box("A");
Box second = first;
swap(first, second);
~~~

The caller's two variables are already **aliases** of the same Box A from the start. Swapping two identical reference values (even if the caller does it itself) has no observable effect on identity: both still point to Box A.

This easily makes tests misleading if you only test two identical aliases; a `swap` method with faulty logic can look as if “no change is the right behavior”. To verify reference swapping, use **two different objects**, and compare identity after the operation.

### 13.1. When a Parameter Has the Value `null`

Example:

~~~java
Box first = new Box("A");
Box second = null;
swap(first, second);
~~~

If `swap` only reassigns parameters and **does not access a field or call an instance method** on `null`, the call still compiles and can execute normally. However, upon returning:

- `first` still holds the reference to Box A.
- `second` is still `null`.

Do not think “`null` is assigned to parameter a” means the caller's `first` also becomes `null`. Every assignment inside applies only to local parameters.

If using the array/holder approach, you must follow the contract: an element can be `null`, and swapping those references can still be meaningful as long as the code does not dereference null.

## 14. Reassigning Reference Variables and Modifying `StringBuilder` Contents

`StringBuilder` is a mutable object, clearly showing the difference between **reassigning a reference** and **modifying an object**.

Save **`StringBuilderReferenceDemo.java`**:

~~~java
public class StringBuilderReferenceDemo {
    static void swapLocals(StringBuilder a, StringBuilder b) {
        StringBuilder temp = a;
        a = b;
        b = temp;
        a.append("!");
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");

        swapLocals(first, second);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
~~~

Run:

~~~bash
javac StringBuilderReferenceDemo.java
java StringBuilderReferenceDemo
~~~

Output:

~~~text
first=A
second=B!
~~~

Inside the method:

1. `a` initially points to StringBuilder A, `b` points to StringBuilder B.
2. After the three local assignments, `a` points to StringBuilder B, `b` points to StringBuilder A.
3. `a.append("!")` **modifies object B** to B!.
4. The caller still points to A via `first` and B via `second`, so it prints A and B!.

This example shows both that **swapping local references does not affect caller variables** and that a method receiving a copy of a reference can still **mutate the object**.

## 15. Why Does `String` Often Confuse Learners?

`String` is a reference type, yet **immutable**. Consider:

~~~java
static void swapStrings(String a, String b) {
    String temp = a;
    a = b;
    b = temp;
}
~~~

If the caller has `String first = "A", second = "B";` and then calls `swapStrings(first, second)`, the caller's two variables still hold `"A"` and `"B"`.

Just as with `Box`, the three assignments only swap the **local parameters**. It is not because String is immutable that the swap fails; **every reference type** follows this pass-by-value rule.

The difference is that String **does not have ordinary mutating methods** like `append` to modify the contents of a String object. For example:

~~~java
static void addSuffix(String text) {
    text = text + "!";
}
~~~

does not modify the caller's string variable; the concatenation creates a new string value and reassigns parameter `text`.

Because string literals can be interned, using `==` between literals to infer that two variables share the same object can be misleading. When analyzing a swap problem, you should use two independent objects with clear identity and check reference equality intentionally.

## 16. Passing a Reference to a Method Does Not Create a Copy of the Object

Another misconception is: “Because Java is pass-by-value, every time a `Box` is passed into a method, a new Box is created.” That is **incorrect**.

~~~java
Box first = new Box("A");
use(first);
~~~

With a method `use(Box p)`, Java **copies the reference value** into `p`. There is no step that automatically calls a copy constructor or deep clones `Box`. Therefore, `p == first` can be `true` as soon as the method begins.

Separate the two actions:

- **Copying the reference value**: the callee and caller both have a reference to the original object.
- **Copying the object**: creating a new object and intentionally copying its contents; requires a dedicated constructor/copy API.

The essence of the `swap` failure lies in **reassigning parameter variables**, not in whether objects are copied or not.

## 17. Can an Array Be Used to Swap the Local Variables Themselves?

Not directly. Consider:

~~~java
Box first = new Box("A");
Box second = new Box("B");
Box[] holder = {first, second};
swapAt(holder, 0, 1);
~~~

Afterward:

- `holder[0]` points to B, `holder[1]` points to A.
- However, **the local variable `first` still points to A, and `second` still points to B**.

The array is **a new reference storage location**, separate from the local variables. If the local variables are to change as well, the caller must write:

~~~java
first = holder[0];
second = holder[1];
~~~

This is similar to returning a pair: **the caller** is responsible for reassigning the two local variables.

Using an array or holder is only beneficial when **the data storage location in the container** is what the API actually owns/needs to change. Do not construct an extra mutable holder just as a “workaround” instead of two simple assignments in the caller.

## 18. Argument Evaluation Order: The Caller Can Be Modified Before swap Is Called

A subtle scenario: argument expressions can have **side effects** before the method starts.

Illustrative example:

~~~java
static void swap(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}

// In the caller:
Object first = new Object();
Object second = new Object();
swap(first = second, second);
~~~

After the call, the caller's `first` variable has indeed changed its reference to point to the same object as `second`. However, **the cause is that the argument expression `first = second` reassigned the caller variable before entering the method**, not the three assignments in the body of `swap`.

The left-to-right argument evaluation rule ensures the expression `first = second` runs before evaluating the second argument `second`. That is why you **cannot** rely on “the caller's value changed after the call” as proof that the method uses pass-by-reference; you must check **which operation actually assigns the caller variable**.

In application code, avoid placing assignments that mutate the same data inside a hard-to-read argument list. Splitting them into statements with clear names and intent is easier to control.

## 19. Swapping References in Fields: When Can It Be Done?

Suppose an object manages two fields `left` and `right`:

~~~java
class PairBox {
    Box left;
    Box right;

    void swapFields() {
        Box temp = left;
        left = right;
        right = temp;
    }
}
~~~

This snippet is an illustrative class that requires declaring `Box`. `swapFields()` **directly modifies two fields belonging to the same `PairBox` object**, rather than modifying two copied parameter variables. Therefore, a caller referencing that `PairBox` will observe the swapped fields.

If fields are declared `final` after initialization, Java does not allow ordinary methods to reassign them. When an immutable model is needed, create a new `PairBox`/record with the reversed order and return it instead of mutating fields.

If the object containing the two fields can be read/written concurrently by multiple threads, swapping two fields with three assignments is **not atomic** by default. Synchronization or an immutable data design is needed if intermediate states must not be exposed.

## 20. Common Mistakes and How to Fix Them

| Misconception | What Is True |
| --- | --- |
| “`swap(a,b)` is like C++ pass-by-reference, so it can swap the caller's two variables.” | Java is pass-by-value. There are no reference-to-variable parameters like in the corresponding C++ example. |
| “Because Box is an object, a method receiving Box can modify the caller's reference variable itself.” | It can modify **the object's state** through the reference, but cannot reassign the caller's variable through the parameter. |
| “If B,A is printed inside the method, it must also be B,A outside.” | B,A can simply be the values of the **two local parameters** after assignment. |
| “`Box temp=a` creates a new Box.” | It only copies the reference; it does not call `new`. |
| “Changing parameter variable names to match caller variable names will modify the caller.” | Two scopes have separate variable declarations, regardless of whether their names match. |
| “A `static` method cannot swap, while an instance method can.” | Both receive arguments by value; `static` is not the reason. |
| “Generic `<T>` enables pass-by-reference.” | No. Generics only govern types/type checking and do not change parameter-passing semantics. |
| “`Object` differs from `Box` in how references are passed.” | Both copy reference values; they differ in static type and available methods. |
| “Assigning `a = b` in the callee changes a field of Box a.” | No, it only changes the value of reference variable `a`. |
| “If you mutate and then swap locals, all results will be lost.” | Mutations to the objects that already happened can be seen by the caller; only rebinding the local parameter does not affect caller variables. |
| “`swapAt(items,0,1)` swaps the two original local variables.” | It swaps **array entries** and does not automatically swap the local variables originally used to populate the array. |
| “`Collections.swap` creates new Boxes.” | It swaps the positions of list elements; it does not require recreating Box objects. |
| “Swapping two holder fields means Java has pass-by-reference.” | No; the method modifies **object fields** via copied references. |
| “Returning a swapped Pair automatically modifies caller variables.” | Caller variables only change when **explicitly reassigned** from the resulting Pair. |
| “`final Box a` makes the Box object immutable.” | `final` restricts reassigning the reference variable/field; the state of Box can still be mutable. |
| “`null` cannot appear in a reference-swapping method.” | Null can be passed for reference parameters; an error only occurs if null is dereferenced or another condition is violated. |
| “Having two variables point to the same object and swapping proves correctness.” | When two references are identical, swapping does not change identity; you need to test with two independent objects. |
| “For a thread-safe swap, you only need an AtomicReference for each field.” | Two operations on two separate AtomicReferences do not by default form an atomic transaction. |

## 21. Debugging Checklist for Reference-Swap Examples

When encountering a Java snippet that appears to swap object references, proceed step by step:

1. **Identify where the references to be swapped are stored**: local variables, array elements, list positions, instance fields, or holder fields?
2. **Count the distinct objects**: how many `new` calls, factory reuses, or aliases are there? Be careful if two variables point to the same object from the beginning.
3. **Distinguish caller variables from callee parameters**: draw two separate rows for them.
4. **Trace parameter binding right at the call**: `a` receives a *copy* of argument 1's reference; `b` receives a *copy* of argument 2's reference.
5. **Check where each assignment targets**: `a = b` changes the parameter; `a.field = x` changes the object; `array[0] = b` changes the array entry.
6. **If the method body does not write back into the caller's container/field and does not return a value assigned by the caller**, the caller's local reference variables do not change on their own.
7. **Check both identity `==` and field contents**: sometimes object data is modified, making the program's output look like a successful swap.
8. **If the solution uses a returned pair**, the caller must assign the results back to the desired storage locations.
9. **If the solution uses a mutable container**, ensure mutability permission, index bounds, null contracts, and thread safety when needed.
10. **If the code has side effects in argument expressions**, consider evaluation order so you do not mistake pre-call changes for effects of the method.

## 22. Self-Check Exercises

**Question 1.** Two variables `Box a`, `Box b` point to two objects A/B. Method `swap(Box x,Box y)` assigns `Box t=x; x=y; y=t;`. After calling `swap(a,b)`, what do a/b point to?  
**Answer:** a still points to A, b still points to B. Only parameters x/y of the method were swapped.

**Question 2.** Why doesn't `x=y` in `swap` reassign `a` in the caller?  
**Answer:** x is a **different parameter variable** that received a copy of the argument's reference; Java does not allow x to be an alias of variable a's storage location.

**Question 3.** If `swap(a,b)` is called when a and b both already point to Box A, what happens in the caller?  
**Answer:** Both still point to A. Even a correct swap does not make two identical references look different; this test is insufficient to prove the implementation.

**Question 4.** Can generic `static <T> void swap(T a,T b)` modify caller variables?  
**Answer:** No. Generics do not change pass-by-value.

**Question 5.** Does `Box[] arr={a,b}; swap(arr[0],arr[1]);` with a method that only swaps local parameters change the array?  
**Answer:** No. It only receives copies of the two element references.

**Question 6.** Does `swapAt(arr,0,1)` with a body writing to `arr[0]` and `arr[1]` change the array?  
**Answer:** Yes. The method receives a reference to the same array object, then modifies **array elements**.

**Question 7.** After `swapAt(arr,0,1)`, do the two local variables a and b (used to create the array) also swap automatically?  
**Answer:** No. To swap the two local variables, the caller must reassign them from the array or from another result.

**Question 8.** Given two independent `Holder<Box>` instances, does a method reassigning `left.value` and `right.value` change the contents of the caller's holder objects?  
**Answer:** Yes, if the fields are mutable and the references are valid. However, the caller variables pointing to the holders are still not reassigned.

**Question 9.** If a swap method returns a `Pair<Box>` containing (B,A), do the caller's a/b variables change automatically?  
**Answer:** No. The caller must perform the assignments `a=result.first(); b=result.second();`.

**Question 10.** `swap` first mutates `a.value`, `b.value` and then rebinds parameters. Does the caller see the mutation?  
**Answer:** Potentially yes, because the parameters initially pointed to the same objects as the caller. Rebinding the parameters afterward does not undo mutations that already occurred.

**Question 11.** Does `String a="A", b="B"; swap(a,b);` change the string variables in the caller?  
**Answer:** No. String is still a reference type passed by value. String's immutability is not the primary reason the swap fails.

**Question 12.** Why might a test that only prints `a.value` and `b.value` be insufficient to verify swapping references?  
**Answer:** The method might have swapped **field contents** instead of references; you need to check object identities `==` or retained original references.

**Question 13.** A method `void swapFields()` takes no parameters, yet swaps `this.left` and `this.right`. Why can the caller observe the swap?  
**Answer:** The method body directly **writes to the object's fields**; the pass-by-value rule for arguments does not prohibit a method from modifying shared mutable state.

**Question 14.** A method uses two `AtomicReference` instances and calls `get/set` to swap fields. Does that guarantee an atomic two-slot swap under multithreading?  
**Answer:** Not yet. Individual atomic operations do not by default make **the entire sequence of two writes** an atomic transaction; coordinated synchronization is needed if that is a requirement.

**Question 15.** If the call is `swap(first=second,second)`, and after the call first changes its reference, does that prove `swap` modified the caller's variable?  
**Answer:** No. It was the **assignment expression first=second in the argument** that changed the caller variable *before* the method began.

## References

- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference values and object identity.
- Java Language Specification, [`4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): variables and kinds of variables.
- Java Language Specification, [`8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): formal parameters and their declarations.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): evaluating arguments before invoking a method.
- Java Platform API, [`Collections.swap(List,int,int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#swap(java.util.List,int,int)): swapping elements in a list.

## Key Takeaways

`swap(a,b)` with body `T t=a; a=b; b=t;` **cannot swap the caller's two reference variables**, because Java passes **reference values** into **independent parameter variables**. After the method finishes, the caller's two variables still hold their original reference values. Code inside the method can swap **parameters** and print the result B,A, but that is not proof that the caller was modified.

To actually swap, operate on the right **reference storage location**: swap two **array/list entries**, swap two **fields of holder objects**, or **return a new Pair and let the caller reassign it**. Do not confuse **reassignment of a reference variable** with **mutation of an object**, and do not treat “the parameter is an object” as an exception to pass-by-value. Distinguishing the three layers — **variable**, **reference value**, **object** — is the key to reading Java swap examples accurately.
