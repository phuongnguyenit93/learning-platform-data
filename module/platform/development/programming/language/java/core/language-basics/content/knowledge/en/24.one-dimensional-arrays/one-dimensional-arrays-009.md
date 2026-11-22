# Assigning Arrays Copies Only the Reference — Java 17+

## 1. Nature of array assignment

Arrays in Java are **objects**. An array-typed variable such as `int[]` holds a **reference value** pointing to that object. Assigning from one array variable to another **copies the reference value**, without creating a new array or copying individual elements.

~~~java
int[] a = {10, 20, 30};
int[] b = a;             // Both reference the same array.
b[0] = 99;               // Modifies the element in the shared array.
System.out.println(a[0]);
~~~

**Exact stdout:**

~~~text
99
~~~

Model:

~~~text
Variable a ───┐
              ▼
          int[] {99, 20, 30}
              ▲
Variable b ───┘
~~~

`a` and `b` are **two different variables**, yet at that point in time they point to **the same array object**. The common term for this is an **alias** (two references to the same object).

**Rule:** `b = a;` is not equivalent to `b = a.clone();` or `b = Arrays.copyOf(a, a.length);`.

## 2. Distinguishing element modification from reference reassignment

~~~java
int[] a = {1, 2};
int[] b = a;

b[0] = 7;            // Modifies the object that both a and b point to.
System.out.println(java.util.Arrays.toString(a));

b = new int[]{8, 9}; // Changes only the reference held in variable b.
System.out.println(java.util.Arrays.toString(a));
System.out.println(java.util.Arrays.toString(b));
~~~

**Exact stdout:**

~~~text
[7, 2]
[7, 2]
[8, 9]
~~~

Two kinds of operations:

| Operation | Affects |
|---|---|
| `b = a;` | The reference in **variable b**; creates no array |
| `b[0] = 7;` | The **element** in the array that b currently points to |
| `b = new int[]{8, 9};` | Switches **variable b** to a new array object |
| `a[0]` after b switches to another array | Still reads the old array that a points to |

Reassigning `b` does not "drag along" `a`, even if `a == b` was true beforehand. **Do not confuse changing an object's contents with changing a reference variable.**

## 3. `==` checks whether two variables reference the same array object

~~~java
int[] first = {1, 2};
int[] alias = first;
int[] other = new int[]{1, 2};

System.out.println(first == alias);
System.out.println(first == other);
System.out.println(java.util.Arrays.equals(first, other));
~~~

**Exact stdout:**

~~~text
true
false
true
~~~

- For two array references, `==` checks whether they point to **the same object**.
- Two distinct array objects can still hold **equal** elements.
- `Arrays.equals(int[], int[])` compares the contents element by element of two one-dimensional `int[]` arrays.

| To check | Use |
|---|---|
| Do two variables point to the same array? | `a == b` |
| Do two `int[]` arrays have the same sequence of values? | `Arrays.equals(a, b)` |
| To print the elements of an `int[]` array | `Arrays.toString(a)` |

`a.equals(b)` on normal Java arrays **does not automatically compare element by element** like `Arrays.equals`. Do not use `==` to conclude that two arrays have equal contents.

## 4. Why passing an array into a method can also change data

Java **passes arguments by value** (*pass-by-value*). When an argument is an array reference variable, **the value being copied is the reference itself**.

~~~java
static void changeElement(int[] values) {
    values[0] = 50;
}

static void rebindParameter(int[] values) {
    values = new int[]{7, 8}; // Reassigns only the local parameter variable.
    values[0] = 70;
}
~~~

~~~java
int[] original = {1, 2, 3};
changeElement(original);
System.out.println(java.util.Arrays.toString(original));

rebindParameter(original);
System.out.println(java.util.Arrays.toString(original));
~~~

**Exact stdout:**

~~~text
[50, 2, 3]
[50, 2, 3]
~~~

In `changeElement`, the parameter `values` is a **copy of the reference** that still points to **the same array** as `original`; modifying `values[0]` changes the caller's data. In `rebindParameter`, assigning `values = new int[]{...}` only changes **the parameter for that call**; the variable `original` in the caller still points to the old array.

This is **not pass-by-reference** in the sense that a method could reassign the caller's reference variable. If the caller needs to use a new array, the method can **return the new array**, and the caller assigns it explicitly: `original = createNewArray(original);`.

## 5. Copying contents to avoid sharing an `int[]` array

Common approaches:

~~~java
import java.util.Arrays;

int[] original = {1, 2, 3};
int[] clone = original.clone();
int[] copy = Arrays.copyOf(original, original.length);

System.out.println(original == clone);
System.out.println(Arrays.equals(original, clone));
~~~

**Exact stdout:**

~~~text
false
true
~~~

`clone()` on `int[]` creates **a new array of the same type, same length, and same element values**. `Arrays.copyOf(original, original.length)` also creates a new array. After having a copy:

~~~java
clone[0] = 99;
System.out.println(Arrays.toString(original));
System.out.println(Arrays.toString(clone));
~~~

**Exact stdout:**

~~~text
[1, 2, 3]
[99, 2, 3]
~~~

Because the two `int[]` arrays are now independent, modifying primitive values in the copy does not affect the original.

| Technique | Creates a new destination array? | Destination length |
|---|---|---|
| `int[] b = a;` | **No** | No new array |
| `int[] b = a.clone();` | **Yes** | Equal to `a.length` |
| `int[] b = Arrays.copyOf(a, a.length);` | **Yes** | Equal to `a.length` |
| `int[] b = Arrays.copyOf(a, 5);` | **Yes** | Equal to `5` |
| `System.arraycopy(a, 0, b, 0, n)` | **Does not create b automatically** | `b` must already be allocated with enough space |

With `Arrays.copyOf(a, 5)`, if the original array has length 3, the two added slots of `int[]` have default value `0`. If the new length is smaller, trailing elements beyond the new length are not copied.

**Caution:** `clone()` or `copyOf` is still a **shallow copy** when the array elements are references to mutable objects. This distinction is illustrated right below.

## 6. Object arrays: copying the array does not copy the element objects

~~~java
StringBuilder[] first = {
    new StringBuilder("A"),
    new StringBuilder("B")
};
StringBuilder[] second = first.clone(); // Different outer array, shared item references.

second[0].append("!");
System.out.println(first[0]);

second[1] = new StringBuilder("C");
System.out.println(first[1]);
System.out.println(second[1]);
~~~

**Exact stdout:**

~~~text
A!
B
C
~~~

`second[0].append("!")` mutates **the `StringBuilder` object referenced by both arrays**, so `first[0]` also displays `A!`. By contrast, `second[1] = new StringBuilder("C")` only replaces the **element reference** at slot 1 of `second`; `first[1]` still points to `"B"`.

Therefore, distinguish two levels:

1. **The array**: `first` and `second` are two distinct array objects after `clone()`.
2. **Element objects**: corresponding elements can still be references to the same mutable object.

To isolate mutable contents as well, you must create **copies of each element object**, according to that type's contract. With `String` (immutable), sharing references typically causes no content-mutation issues. With `StringBuilder`, mutating contents affects every reference to that object.

## 7. Assigning `null` or returning a new array

~~~java
int[] a = {3, 4};
int[] b = a;
b = null;

System.out.println(b == null);
System.out.println(java.util.Arrays.toString(a));
~~~

**Exact stdout:**

~~~text
true
[3, 4]
~~~

Assigning `b = null` only stops **variable b** from pointing to the array; `a` still holds that array. Accessing `b.length` or `b[0]` afterward throws `NullPointerException`.

A method can return a **new** reference so the caller can intentionally update its variable:

~~~java
static int[] appendZero(int[] source) {
    return java.util.Arrays.copyOf(source, source.length + 1);
}
~~~

~~~java
int[] a = {3, 4};
int[] longer = appendZero(a);
System.out.println(java.util.Arrays.toString(a));
System.out.println(java.util.Arrays.toString(longer));
~~~

**Exact stdout:**

~~~text
[3, 4]
[3, 4, 0]
~~~

Arrays have a fixed length. `appendZero` does not "extend" the old object; it **allocates another array**. If the caller wants variable `a` to use the longer array, it must write `a = appendZero(a);`.

## 8. Complete Java 17+ program

Save to the exact file **`ArrayReferenceAssignmentDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayReferenceAssignmentDemo {
    private ArrayReferenceAssignmentDemo() {}

    static void mutateElement(int[] values) {
        values[0] = 99;
    }

    static void rebindParameter(int[] values) {
        values = new int[]{7, 8};
        values[0] = 70;
    }

    public static void main(String[] args) {
        int[] original = {10, 20, 30};
        int[] alias = original;

        System.out.println("original start=" + Arrays.toString(original));
        System.out.println("alias same array=" + (original == alias));

        alias[1] = 77;
        System.out.println("original after alias write=" + Arrays.toString(original));

        mutateElement(alias);
        System.out.println("original after mutate=" + Arrays.toString(original));

        rebindParameter(alias);
        System.out.println("original after reassign parameter="
                + Arrays.toString(original));

        int[] copy = original.clone();
        System.out.println("clone same array=" + (original == copy));
        System.out.println("clone contents equal=" + Arrays.equals(original, copy));
        copy[0] = 1;
        System.out.println("original after clone write=" + Arrays.toString(original));
        System.out.println("clone=" + Arrays.toString(copy));

        int[] extended = Arrays.copyOf(original, 5);
        System.out.println("extended=" + Arrays.toString(extended));
        System.out.println("original length=" + original.length);

        int[] destination = new int[3];
        System.arraycopy(original, 0, destination, 0, original.length);
        destination[2] = -5;
        System.out.println("arraycopy dest=" + Arrays.toString(destination));
        System.out.println("original after arraycopy dest write="
                + Arrays.toString(original));

        alias = new int[]{4, 5};
        System.out.println("alias after rebinding=" + Arrays.toString(alias));
        System.out.println("original after rebinding=" + Arrays.toString(original));
        System.out.println("same after rebinding=" + (original == alias));

        int[] missing = original;
        missing = null;
        System.out.println("null reference=" + (missing == null));
        System.out.println("original survives null=" + Arrays.toString(original));

        StringBuilder[] objects = {
            new StringBuilder("A"), new StringBuilder("B")
        };
        StringBuilder[] shallow = objects.clone();
        System.out.println("object array shared item=" + (objects[0] == shallow[0]));
        shallow[0].append("!");
        System.out.println("object after item edit=" + objects[0]);
        shallow[1] = new StringBuilder("C");
        System.out.println("object original second=" + objects[1]);
        System.out.println("object new second=" + shallow[1]);
        System.out.println("object shared array=" + (objects == shallow));
    }
}
~~~

Requires **JDK 17 or later**; uses no libraries outside the JDK or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayReferenceAssignmentDemo.java
java -cp . ArrayReferenceAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayReferenceAssignmentDemo.java
java -cp . ArrayReferenceAssignmentDemo
~~~

### Exact expected stdout

~~~text
original start=[10, 20, 30]
alias same array=true
original after alias write=[10, 77, 30]
original after mutate=[99, 77, 30]
original after reassign parameter=[99, 77, 30]
clone same array=false
clone contents equal=true
original after clone write=[99, 77, 30]
clone=[1, 77, 30]
extended=[99, 77, 30, 0, 0]
original length=3
arraycopy dest=[99, 77, -5]
original after arraycopy dest write=[99, 77, 30]
alias after rebinding=[4, 5]
original after rebinding=[99, 77, 30]
same after rebinding=false
null reference=true
original survives null=[99, 77, 30]
object array shared item=true
object after item edit=A!
object original second=B
object new second=C
object shared array=false
~~~

Step-by-step analysis: `alias` initially shares the same reference as `original`, so writing through `alias` and through the `mutateElement` parameter changes the original array. Reassigning the `values` parameter inside `rebindParameter` does not make the caller point to a new array. `clone()` and `copyOf` create independent `int[]` arrays. `System.arraycopy` copies elements into an already allocated destination array. In the `StringBuilder[]` part, `clone` only separates **the arrays**, without creating copies of the mutable element objects.

## 9. Common mistakes

| Mistake | Consequence / misconception | Correct approach |
|---|---|---|
| `int[] b = a;` copies data | Both variables still point to the same object | Use `a.clone()` or `Arrays.copyOf` |
| `b[0] = 5` affects only b | When aliased, a also sees the change | Distinguish reference variables from the array |
| `b = new int[2]` makes a change too | Only b points to the new object | Assigning one variable does not modify another variable |
| `a == b` checks equal elements | It compares identity | Use `Arrays.equals` for `int[]` contents |
| `values = new int[]{...}` inside a method reassigns the caller's array | The parameter is a copy of the reference | Return the new array and have the caller assign it |
| `clone()` on `StringBuilder[]` clones each StringBuilder | Element objects can still be shared | Copy each object individually when needed |
| `System.arraycopy` automatically creates the destination array | Destination must already exist with enough capacity | Allocate destination beforehand |
| `b = null` also makes a null | Only b is reassigned | `a` can still point to the old array |

## 10. Exercises and answers

**A — Predict the value:**

~~~java
int[] a = {2, 4};
int[] b = a;
b[1] = 9;
System.out.println(a[1]);
~~~

**Answer:** `9`, because both variables point to the same array.

**B — Reassigning a variable:**

~~~java
int[] a = {2, 4};
int[] b = a;
b = new int[]{7};
System.out.println(a.length + "," + b.length);
~~~

**Answer:** `2,1`. Switching `b` to a new array does not change `a`.

**C — Comparing references and contents:**

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(a == b);
System.out.println(Arrays.equals(a, b));
~~~

**Answer:**

~~~text
false
true
~~~

**D — Method receiving an array:**

~~~java
static void edit(int[] a) {
    a[0] = 5;
    a = new int[]{8};
}
~~~

After `int[] x = {1}; edit(x);`, the value of `x[0]` is **5**. Assigning `a = new int[]{8}` does not change the caller's `x` reference variable.

**E — When cloning an object array:** `StringBuilder[] copy = original.clone();` makes `copy == original` **false**, yet `copy[0] == original[0]` can be **true**. To change `StringBuilder` state independently, you must copy that object itself.

## 11. Checklist and conclusion

- [ ] Understand that a variable of type `T[]` holds a reference to an array object.
- [ ] Know that assigning `b = a` only copies the reference, without copying elements.
- [ ] Distinguish modifying `b[i]` from reassigning `b`.
- [ ] Use `==` to check for the same object, and `Arrays.equals` to check `int[]` contents.
- [ ] Understand that Java passes array references **by value** on method calls.
- [ ] Use `clone()`/`Arrays.copyOf` to create a new independent primitive array.
- [ ] Know that `System.arraycopy` copies into an already created destination array.
- [ ] Recognize shallow copying when an array contains mutable objects.
- [ ] Do not confuse `null` on one variable with the state of another variable.
- [ ] Run `ArrayReferenceAssignmentDemo.java` with Java 17+ and verify exact stdout.

**Conclusion:** For one-dimensional arrays in Java, `b = a` only **copies the reference**; both variable names point to the same array object until one variable is reassigned. Modifying elements through an alias changes the shared data. To get an independent `int[]` array, you must **create a copy of the array object**; if elements are mutable objects, you may also need to copy the element objects themselves.