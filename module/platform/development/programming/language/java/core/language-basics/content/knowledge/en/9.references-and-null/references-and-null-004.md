# Reference Assignment Makes Multiple Variables Share One Object in Java

> **Java core — language-basics / References and null**  
> **Requirements:** JDK 17+; standard library only, single standalone Java file.  
> **Goal:** Understand that assignment between reference-type variables **copies the reference value**, not the object; distinguish **mutating object state** from **reassigning a variable**, and know how to limit side effects caused by multiple variables pointing to one object.

## 1. A Reference Variable Does Not Contain a Copy of the Object

Example:

~~~java
class Box {
    int value;
    Box(int value) {
        this.value = value;
    }
}

Box first = new Box(10);
Box second = first;
~~~

The line `new Box(10)` creates a `Box` object. The variable `first` holds a reference to that object. The line `second = first` **copies the reference value** into `second` — it does not call `new` and **does not create a copy**.

After the assignment, both names point to **one object**:

~~~mermaid
flowchart LR
    A["first"] --> O["Box object: value = 10"]
    B["second"] --> O
~~~

How to picture it: `first` and `second` are **two separate variables**, but right now the value of both variables is a reference to **the same object**. The variables do not point to each other.

| Operation | Is a new object created? | What happens |
| --- | --- | --- |
| `Box first = new Box(10);` | Yes | Creates a Box and stores the reference in first |
| `Box second = first;` | No | Both variables point to the same Box |
| `second.value = 20;` | No | Mutates the shared Box; reading `first.value` also yields 20 |
| `second = new Box(30);` | Yes | second switches to a new Box; first still points to the old Box |
| `second = null;` | No | Only second points to no object; first does not change |

**Core point:** `second = first` is not a *deep copy*, *shallow object copy*, or full data duplication. It is **reference assignment**.


## 2. Tracking an Alias When State Changes

If `Box b = a;` then `b.value = 20;`, both variables still reference the same object and `a.value` becomes `20`. If you continue with `b = new Box(30);`, only `b` switches to the new object, and `a.value` remains `20`. These two situations differ because the first operation modifies the **shared object**, while the second operation modifies the **reference value stored in the variable**. In the full example below, track the alias branches of the original object rather than looking only at variable names.

## 3. Runnable Java 17+ Example

Create the file **`ReferenceAliasDemo.java`**:

~~~java
public final class ReferenceAliasDemo {
    private static final class Box {
        private int score;

        Box(int score) {
            this.score = score;
        }

        void add(int amount) {
            score += amount;
        }

        int getScore() {
            return score;
        }
    }

    private static void addPoints(Box box) {
        box.add(5); // Modifies the very object that the caller holds.
    }

    private static void rebind(Box box) {
        box = new Box(999); // Only changes the local parameter variable.
        System.out.println("insideRebind=" + box.getScore());
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;

        System.out.println("sameReference=" + (first == alias));

        alias.add(10);
        System.out.println("viaFirst=" + first.getScore());

        addPoints(first);
        System.out.println("viaAlias=" + alias.getScore());

        rebind(alias);
        System.out.println("afterCall=" + alias.getScore());

        alias = new Box(30);
        System.out.println("sharedAfterRebind=" + (first == alias));
        System.out.println("firstScore=" + first.getScore());
        System.out.println("aliasScore=" + alias.getScore());

        Box third = first;
        third = null;
        System.out.println("thirdNull=" + (third == null));
        System.out.println("firstStill=" + first.getScore());

        int[] left = {1, 2};
        int[] right = left;
        right[0] = 9;
        System.out.println("arrayFirst=" + left[0]);

        String textA = "Hi";
        String textB = textA;
        textB = textB.concat("!");
        System.out.println("textA=" + textA);
        System.out.println("textB=" + textB);

        Box independent = new Box(first.getScore());
        independent.add(100);
        System.out.println("separateCopy=" + independent.getScore());
        System.out.println("originalStill=" + first.getScore());
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ReferenceAliasDemo.java
java ReferenceAliasDemo
~~~

**Expected output (exact):**

~~~text
sameReference=true
viaFirst=20
viaAlias=25
insideRebind=999
afterCall=25
sharedAfterRebind=false
firstScore=25
aliasScore=30
thirdNull=true
firstStill=25
arrayFirst=9
textA=Hi
textB=Hi!
separateCopy=125
originalStill=25
~~~

**Explanation of key milestones:**

1. `alias = first` makes `first == alias` evaluate to `true`.
2. Calling `alias.add(10)` increments the shared object from 10 to 20; reading through `first` sees 20. `addPoints(first)` increments it further to 25; reading through `alias` still sees 25.
3. Inside `rebind`, the parameter `box` is assigned to a new Box (999). When the method returns, the caller's `alias` still points to the Box with score 25.
4. `alias = new Box(30)` makes `first` and `alias` point to **two different Boxes**, with scores 25 and 30 respectively.
5. Assigning `third = null` only changes the variable `third`, without deleting the Box held by `first`.
6. Arrays are objects too: `right = left` makes both variables share the array; modifying `right[0]` turns `left[0]` into 9.
7. `String` is immutable: `concat` produces the result string `"Hi!"`, while `textA` remains `"Hi"`.
8. `new Box(first.getScore())` creates a separate Box with initial value 25; incrementing the separate instance to 125 does not change `first`'s Box.


## 4. Aliases Passed Through Parameters

Java passes **by value**: a method receives a copy of the reference. Therefore, `box.add(5)` can modify the object that the caller also holds, whereas `box = new Box(100)` only reassigns the method's parameter. This is also why `rebind(alias)` in the program only prints `insideRebind=999` while the caller's `alias` still has score `25`.


## 5. Aliasing Does Not Mean All Data Is Mutable

Arrays are also mutable objects: after `int[] b = a; b[0] = 9;`, reading `a[0]` yields `9`. By contrast, `String` is immutable; `String b = a; b = b.concat("!");` only changes `b`'s reference to the result, without modifying the string that `a` holds. Assigning `b = null` only drops the alias in `b`, and a `final` variable only forbids reassigning itself; neither rule makes the original object vanish or become immutable.

## 6. When Do You Need to Copy an Object?

Sharing a reference is useful when multiple places **intentionally share the same state**. However, if one place needs to make modifications without affecting others, you must create an **independent object**.

~~~java
Box original = new Box(10);
Box shared = original;                  // Same object.
Box independent = new Box(original.getScore()); // New object.
~~~

`independent.add(5)` does not modify `original` in the Box example that only has a primitive `score` field. However, for an object containing references to nested mutable objects, copying only the fields is a **shallow copy** and may still share child objects. When complete independence is required, consider a **deep copy** suited to the data model.

For primitive arrays, `int[] copy = originalArray.clone();` creates a new array with independent values. For arrays of references, `clone()` creates a **new array**, but the reference elements may still point to **the same child objects**. Do not apply "clone = deep copy" to every type.

## 7. Common Mistakes and Self-Check Questions

| Misconception | Correction |
| --- | --- |
| "`b = a` will copy the whole object." | False: it only copies the **reference value**, without creating a new object |
| "Modifying `b.score` does not affect `a` because they are two variables." | If `a == b`, it modifies the same object, so `a` sees the change |
| "`b = new Box(...)` makes `a` switch objects too." | False: only variable `b` is reassigned |
| "Assigning `b = null` deletes the shared object." | False: other aliases may still reference that object |
| "Java is pass-by-reference, so changing a parameter in a method changes the caller's variable." | False: Java is pass-by-value, copying the reference value |
| "Arrays assigned with `=` automatically copy their elements." | False: both variables reference the old array |
| "`String.concat` modifies the shared String's contents." | False: String is immutable; the concat result does not modify the original object |

**Exercise 1:** Given `Box x = new Box(2); Box y = x;`. Predict the result if you call `y.add(3)` and then read `x.getScore()`. Is `x == y` true or false?

**Exercise 2:** After Exercise 1, execute `y = new Box(10);`. What are `x.getScore()` and `y.getScore()` equal to, and how many Box objects have been created?

**Exercise 3:** Given `int[] a = {1, 2}; int[] b = a;`, change `b[1]` to 99 and print `a[1]`. Then try `b = a.clone(); b[1] = 5;`: does `a[1]` change further?

**Exercise 4:** Write a method that takes a `Box` and tries two operations: `box.add(1)`, `box = new Box(0)`. Explain why only one operation is observed by the caller on the original Box.

**Exercise 5:** Given `String a = "Hi"; String b = a; b = b + "!";`. Predict `a` and `b`, distinguishing **reference assignment** from **String immutability**.

### Remember

**Assigning `b = a` with reference types creates another alias to the same object, without copying the object.** Every alias can observe changes to **mutable object state**. Conversely, **reassigning a variable** (to another object or `null`) only changes that variable. Java passes references **by value** as well, and when independent data is needed you must **create an appropriate copy**, not merely assign to a new variable name.
