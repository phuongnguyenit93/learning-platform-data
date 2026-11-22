# Reference Variables and the Objects They Reference — Java 17+

In Java, when declaring `Box item = new Box(10);`, we need to distinguish the **reference variable `item`** from the **`Box` object created by `new`**.

- A **reference variable** has a declared type (for example, `Box`) and can hold a reference value to a compatible object or `null`. This variable can be reassigned unless constrained by `final`.
- An **object** carries its own state and behavior according to its class. Two variables can reference **the same object**; in that case, an operation that modifies the object's state through one variable can be observed through the other.
- **Reference assignment does not clone the object.** In `Box other = item;`, the reference value is copied, rather than creating another `Box`.
- `null` means **not referencing any object**, not a special object with fields or methods.

This is the **semantics** of Java, without needing to assume memory addresses, stack/heap placement, or how the JVM optimizes objects.

## 1. Four Operations That Look Similar but Differ in Nature

~~~java
Box first = new Box("Main", 10); // Creates an object; first references it.
Box alias = first;        // Copies the reference, does NOT create a new Box.
Box another = new Box("Other", 10); // Creates another Box, even with the same values.
alias = null;             // Only changes the alias variable.
~~~


| Operation | Does the variable change? | Does the object change? |
| --- | --- | --- |
| `Box first = new Box("Main", 10);` | `first` receives the reference | A new object is created |
| `Box alias = first;` | `alias` receives a copy of the reference | Does not create or modify an object |
| `alias.points = 20;` | The reference in `alias` does not change | The shared object is modified if the field allows it |
| `alias = new Box("Fresh", 5);` | `alias` points to a different object | The old object is not replaced by the new object |
| `alias = null;` | `alias` no longer points to an object | The old object itself is not immediately deleted |
| `Box independent = new Box("Independent", 20);` | `independent` holds its own reference | A new object is created, even with matching data |

The snippets in this section use the same constructor `Box(String label, int points)` and field `points` as the program in section 2; these example snippets only need to be placed in an appropriate scope after the `Box` class definition to be tried out.

Visualize it:

~~~text
first ───┐
         ├──────> Box(points=10)
alias ───┘

another ────────> Box(points=10)   // Different object

alias = null;
first ──────────> Box(points=10)
alias ──────────> null
~~~

The diagram only describes **reference relationships**, not RAM addresses or physical memory management mechanisms.

## 2. Standalone Runnable Java 17+ Example

Save a UTF-8 file named **`ReferenceObjectDemo.java`**:

~~~java
public class ReferenceObjectDemo {
    static class Box {
        final String label;
        int points;

        Box(String label, int points) {
            this.label = label;
            this.points = points;
        }
    }

    static void increase(Box parameter) {
        parameter.points += 5; // Modifies the object currently being referenced.
    }

    static void replace(Box parameter) {
        parameter = new Box("Replacement", 99);
        System.out.println("insideReplace=" + parameter.points);
    }

    public static void main(String[] args) {
        Box first = new Box("Main", 10);
        Box alias = first;
        Box separate = new Box("Main", 10);

        System.out.println("aliasSameObject=" + (first == alias));
        System.out.println("separateSameObject=" + (first == separate));

        alias.points = 20;
        System.out.println("firstAfterAlias=" + first.points);
        System.out.println("separatePoints=" + separate.points);

        increase(first);
        System.out.println("afterIncrease=" + first.points);

        replace(first);
        System.out.println("afterReplace=" + first.points);

        alias = null;
        System.out.println("aliasIsNull=" + (alias == null));
        System.out.println("firstStillWorks=" + first.points);

        Box old = first;
        first = new Box("Fresh", 7);
        System.out.println("newObject=" + first.points);
        System.out.println("oldObject=" + old.points);

        final Box fixedReference = old;
        fixedReference.points = 30;
        System.out.println("finalReferencePoints=" + old.points);

        Box absent = null;
        System.out.println("absentIsNull=" + (absent == null));
        try {
            System.out.println(absent.points);
        } catch (NullPointerException ex) {
            System.out.println("dereference=NullPointerException");
        }

        Box[] slots = new Box[2];
        System.out.println("defaultArrayElementNull=" + (slots[0] == null));
        slots[0] = old;
        System.out.println("arraySharesObject=" + (slots[0] == old));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file, using JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ReferenceObjectDemo.java
java ReferenceObjectDemo
~~~

**Expected output of the program** (excluding the version lines printed by `java -version` and `javac -version`):

~~~text
aliasSameObject=true
separateSameObject=false
firstAfterAlias=20
separatePoints=10
afterIncrease=25
insideReplace=99
afterReplace=25
aliasIsNull=true
firstStillWorks=25
newObject=7
oldObject=25
finalReferencePoints=30
absentIsNull=true
dereference=NullPointerException
defaultArrayElementNull=true
arraySharesObject=true
~~~

### Analyzing the Output

1. `alias = first` makes both variables point to the same object, so `first == alias` is `true`. `separate` is created with another `new` call; having the same data does not make it the same object.
2. `alias.points = 20` makes `first.points` become 20. It is not that "the `first` variable had its reference modified"; **the state of the shared object** changed.
3. The `increase` method receives a copy of the reference. It still accesses the same object and increments `points` to 25.
4. `replace` only reassigns the **local parameter** to a new `Box`. The caller's `first` variable still points to the object with `points = 25`.
5. Assigning `alias = null` does not make the object disappear because `first` still holds a reference. When assigning `first = new Box("Fresh", 7)`, `old` continues to hold a reference to the old object.
6. `final Box fixedReference = old` prevents reassigning the `fixedReference` variable; it does **not** freeze `points` inside the object. Modifying the field through `fixedReference` changes `old.points` to 30.
7. `absent.points` throws `NullPointerException` because `absent` is `null`. A `Box[]` array is also an object; each reference element is initially `null`. Assigning `slots[0] = old` creates another alias.

## 3. Java Always Passes Parameters **by Value**

For reference-type parameters, Java **copies the reference value** into the parameter variable. Therefore, we need to separate two things:

~~~java
static void mutate(Box b) {
    b.points = 42; // Modifies the state of the shared object.
}

static void reassign(Box b) {
    b = new Box("Other", 42); // Only reassigns the parameter b.
}
~~~

- Calling `mutate(first)` can cause `first.points` to change, because the caller and the parameter both lead to the same object.
- Calling `reassign(first)` does **not** make the `first` variable point to a new object.
- If you want the caller to use a replacement object, the method can **return the new reference**, and then the caller writes `first = createReplacement(...);`.

Do not call this mechanism "Java passes references by reference": **Java does not allow a method to reassign the caller's reference variable by reassigning a parameter**.


## 4. Identifying the Same Object

Two calls to `new Box("A", 10)` create two objects that may have the same data, but `x == y` will be `false` if `x` and `y` point to those two objects. Conversely, `Box z = x;` makes `x == z` evaluate to `true` because only the reference is copied. `==` does not automatically compare fields; for `String`, use `equals` when you want to compare contents. Custom types only compare values with `equals` when an appropriate contract is defined.


## 5. The `null` Value and Unassigned Variables

`Box absent = null;` is a variable that already has a value but does not point to any object yet; `absent.points` will throw `NullPointerException`. By contrast, a local variable that is only declared as `Box pending;` has not undergone *definite assignment*, so it cannot be read. Reference-type fields and array elements have a default value of `null`.

`alias = null` only changes the value of one variable, without destroying the object held by other aliases; the exact timing of garbage collector reclamation is not guaranteed. Closing resources such as files or sockets via `close()`/`try-with-resources` is a separate responsibility.

## 6. Common Misconceptions

| Statement | True/False | Explanation |
| --- | --- | --- |
| "`Box b = a;` creates a new Box." | **False** | Only copies the reference value |
| "Two variables point to the same object; modifying a field through one is seen through the other." | **True** for mutable fields | Both access the same state |
| "Assigning `b = null` deletes the object immediately." | **False** | Only changes the reference; other aliases may remain |
| "`new Box(1)` and `new Box(1)` are the same object." | **False** | Two separate object creations |
| "Reassigning a `Box` parameter changes the caller's variable." | **False** | The parameter is a copy of the reference value |
| "`final Box b` makes all fields immutable." | **False** | `final` constrains reassigning the variable, not the object's state |
| "`null` is an empty object." | **False** | No object is referenced |
| "A `Box[]` array comes pre-filled with individually constructed `Box` instances." | **False** | Reference-type elements are initially `null` |

## 7. Self-Check Exercises

**Exercise 1.** Predict the following output:

~~~java
Box a = new Box("One", 1);
Box b = a;
b.points = 4;
System.out.println(a.points);
~~~

*Answer:* `4`. Both variables reference the same object.

**Exercise 2.** If you continue by writing `b = new Box("Two", 9);`, what does `a.points` become?

*Answer:* Still `4`. Only `b` points to the new object.

**Exercise 3.** Given `Box x = null;`, is checking `x == null` valid? What about `x.points`?

*Answer:* The comparison is valid and returns `true`. Accessing the field throws `NullPointerException`.

**Exercise 4.** Why does a method taking `Box parameter` and writing `parameter = new Box("New", 3);` not modify the reference in the caller's variable?

*Answer:* Java passes a **copy of the reference value** into the parameter; the assignment only updates the local parameter.

**Exercise 5.** Does `final Box b = new Box("Fixed", 5);` allow `b.points = 6;`? Does it allow `b = new Box("Other", 6);`?

*Answer:* It allows modifying `points`; it does not allow reassigning the `final` variable.

## Checklist

- [ ] Distinguish a **reference variable** from the **created object**.
- [ ] Understand that assignment between reference variables **copies the reference value**.
- [ ] Distinguish modifying an object's field from reassigning a variable to point to another object.
- [ ] Know that `==` compares object identity, not content by default.
- [ ] Know that Java passes all parameters by value, including reference parameters.
- [ ] Understand `null`, dereferencing `null`, and conditions for memory reclamation.
- [ ] Avoid misunderstanding `final` as making an object immutable.

**Remember:** A reference variable is **a place that holds a logical link to an object**, while an object is **the entity that holds state**. Copying the link does not copy the entity; modifying the entity does not automatically change the variable; changing the variable does not automatically modify or delete the entity.
