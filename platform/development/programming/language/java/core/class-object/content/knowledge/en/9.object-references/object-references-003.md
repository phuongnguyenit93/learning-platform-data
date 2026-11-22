# Multiple Variables Referencing the Same Object in Java

## Learning Objectives

After this lesson, you can:

- Accurately explain **reference variables**, **objects**, and **shared references/aliasing** in Java.
- Distinguish between multiple variables holding **the same reference value** and multiple independent objects having **the same content**.
- Predict the effects of **modifying object state** through a variable, **reassigning a reference variable**, setting a variable to `null`, or passing a reference into a method.
- Use the `==` operator and `equals()` for their intended purposes: comparing **identity** or **logical value**.
- Understand `final`, immutable `String`, arrays, collections, shallow copy, and deep copy in the context of aliasing.
- Avoid leaking mutable state through constructors, getters, collections, or shared references.
- Recognize the connection to garbage collection, *reachability*, and thread safety.
- Compile/run Java 17+ programs and explain stdout without relying on false assumptions about “passing objects by reference”.

## 1. Aliasing Is an Issue of Observable Shared State

**Aliasing** occurs when two or more reference paths lead to **the same mutable object**. This lesson focuses on the consequence: one place can change state that other places also see, even when references reside in fields, arrays, or collections.

~~~java
Box a = new Box(10);
Box b = a;
Box independent = new Box(10);
b.value = 20;
~~~

This is a snippet requiring Box with a constructor taking an int and an accessible field value. After the mutation, `a.value` is 20, and `independent.value` is 10. `a == b` is true, while `a == independent` is false. Reference assignment **does not** automatically copy an object.

When you notice “modify in one place, another place changes too”, follow this order:

1. List all reference paths to the shared mutable object.
2. Distinguish object mutation from variable reassignment.
3. Check nested references: two outer objects may be separate yet share a List or a child object.
4. If isolation is needed, consider a defensive copy, immutable elements, a read-only API, or an ownership policy.
5. If there are multiple threads, synchronization/transactions matching the requirements are needed; aliasing does not make code concurrently safe on its own.

The following examples practice each case in depth; this is not just an exercise in counting `new` calls.

## 2. Standalone Example: Creating an Alias, Modifying an Object, and Reassigning a Variable

Save the file **`ReferenceAliasingDemo.java`**:

~~~java
public class ReferenceAliasingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box separate = new Box(10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == separate: " + (first == separate));

        alias.value = 25;
        System.out.println("after mutation: first=" + first.value
                + ", alias=" + alias.value
                + ", separate=" + separate.value);

        alias = new Box(99);
        System.out.println("after reassignment: first=" + first.value
                + ", alias=" + alias.value);

        alias = null;
        System.out.println("alias is null: " + (alias == null));
        System.out.println("first still=" + first.value);
    }
}
~~~

Compile and run with JDK 17 or later in the directory containing the file:

~~~bash
javac ReferenceAliasingDemo.java
java ReferenceAliasingDemo
~~~

**Exact stdout:**

~~~text
first == alias: true
first == separate: false
after mutation: first=25, alias=25, separate=10
after reassignment: first=25, alias=99
alias is null: true
first still=25
~~~

Explanation of each stage:

1. `first` and `alias` both reference Box A, so `first == alias` is `true`.
2. `separate` points to the newly created Box B, so `first == separate` is `false` even though the two Boxes initially have the same field value.
3. `alias.value = 25` performs **a field assignment on Box A**. Reading either `first.value` or `alias.value` sees `25`.
4. `alias = new Box(99)` **reassigns the variable alias itself** to Box C. It **does not** change Box A and does not automatically change the variable `first`; `first.value` is still `25`.
5. `alias = null` only changes the value of the variable `alias`; it does not delete Box A, does not change `first`, and does not immediately destroy Box C. Box A is still referenced by `first`.

**Conclusion:** You must distinguish between two kinds of operations:

| Operation | What changes | Does another alias see the change? |
| --- | --- | --- |
| `alias.value = 25` | State of the object that `alias` is referencing | **Yes**, if the other alias references the same object |
| `alias = new Box(99)` | Reference value stored in **the variable `alias`** | **No**, other alias variables do not automatically switch with it |
| `alias = first` | Variable `alias` points to the object of `first` | The two variables reference the same object again, but no new object is created |
| `alias = null` | Variable `alias` references no object | Does not affect other variables holding a reference |
| `first.value` | Reading a field through a reference | Does not change state |

## 3. `==` Compares Identity, `equals()` Compares According to the Class Contract

### 3.1. `==` Between Two References

For two variables of compatible reference types, `a == b` checks whether they have the same **reference value**: the same object, or both are `null`.

~~~java
Object a = new Object();
Object alias = a;
Object other = new Object();

System.out.println(a == alias); // true
System.out.println(a == other); // false
~~~

This is a snippet placed inside a method. Two `new Object()` calls create two separate objects; being of the same class does not mean having the same identity.

`==` **does not** automatically compare all fields, strings, or collection elements. If you need to compare logical state, check `equals()` according to the type's contract.

### 3.2. `equals()` Does Not Mean “All Fields Are Identical” by Default

The `Object` class declares `equals()` with default behavior based on identity. If a class **does not override `equals()`**, two different instances typically compare as `false` with `equals` even when their fields contain identical content.

Classes such as `String`, numeric wrappers, and appropriate value objects typically **override** `equals` to compare by value or their respective contract.

Standalone example **`IdentityVsEqualityDemo.java`**:

~~~java
import java.util.Objects;

public class IdentityVsEqualityDemo {
    static final class Person {
        private final String id;

        Person(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Person person)) {
                return false;
            }
            return id.equals(person.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Person first = new Person("P01");
        Person alias = first;
        Person other = new Person("P01");

        System.out.println("alias identity=" + (first == alias));
        System.out.println("other identity=" + (first == other));
        System.out.println("other equality=" + first.equals(other));

        String x = new String("java");
        String y = new String("java");
        System.out.println("string identity=" + (x == y));
        System.out.println("string equality=" + x.equals(y));
    }
}
~~~

Compile/run:

~~~bash
javac IdentityVsEqualityDemo.java
java IdentityVsEqualityDemo
~~~

Output:

~~~text
alias identity=true
other identity=false
other equality=true
string identity=false
string equality=true
~~~

In `Person`, `equals` is overridden based on the `id` field, so two Person objects with **different identities** still have **equal logical values**. Because `equals` is overridden, the example also overrides `hashCode` consistently, which is necessary when used with `HashSet` and `HashMap`.

`new String("java")` creates a new `String` object in each expression, so the two separate objects have `== false`, whereas `String.equals` checks the character contents so it is `true`.

**Do not use an example with two identical string literals to prove that all Strings with the same content share the same identity.** Literals can be interned; interning does not make `==` a general content comparison operator.

### 3.3. When to Use `Objects.equals(a, b)`?

`java.util.Objects.equals(a,b)` helps compare equality according to the `equals` contract in a **`null`-safe** manner:

~~~java
String a = null;
String b = null;
System.out.println(java.util.Objects.equals(a, b)); // true
~~~

If you call `a.equals(b)` when `a == null`, the program throws a `NullPointerException`. However, `Objects.equals` does not change the definition of identity; it simply implements a null-handling equality check.

## 4. Reassigning a Variable Does Not Make Another Alias Change Its Reference

Consider:

~~~java
Box left = new Box(1);
Box right = left;
right = new Box(2);
~~~

On line 2, `left` and `right` both reference Box A. Line 3 creates a new Box B and then **reassigns the variable `right`**; afterward:

~~~text
left  -----> Box A { value = 1 }
right -----> Box B { value = 2 }
~~~

This principle holds for local variables, instance fields, static fields, and parameter variables (if reassignment is permitted). Pointing one variable to a new object **does not propagate** to other variables that previously held the same reference value.

A misconception is writing:

~~~java
User old = currentUser;
currentUser = new User("Other");
~~~

and assuming `old` also points to the new user. With complete code and a suitable `User`, `old` still retains the old reference. Conversely, if **a field of the old object is modified** before or after that through another reference, `old` can still observe the modification.

### 4.1. `null` Does Not Delete an Object Referenced by Another Variable

~~~java
Box first = new Box(5);
Box second = first;
first = null;
System.out.println(second.value); // 5
~~~

Inside a method with a suitable `Box` class, `second` still references the object. `null` is a **special reference value** indicating no object; it is not a command to free an object.

If you read `first.value` after `first = null`, Java throws a `NullPointerException`; however, `second.value` is still usable.

## 5. `final` Fixes the Reference Variable, Does Not Make the Object Immutable

A reference-type field/local/parameter can be declared `final`:

~~~java
final StringBuilder buffer = new StringBuilder("A");
buffer.append("B"); // Valid
// buffer = new StringBuilder("C"); // Invalid
~~~

`final` prevents **reassigning the variable `buffer`** after it has been assigned a valid value, but it does not prevent modifying the `StringBuilder` object through `append`.

Standalone example **`FinalReferenceDemo.java`**:

~~~java
public class FinalReferenceDemo {
    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        final Counter a = new Counter(3);
        Counter b = a;

        b.value = 8;
        System.out.println("a.value=" + a.value);
        System.out.println("same object=" + (a == b));

        b = new Counter(100);
        System.out.println("a after b reassigned=" + a.value);
        System.out.println("b.value=" + b.value);
    }
}
~~~

Compile/run:

~~~bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Output:

~~~text
a.value=8
same object=true
a after b reassigned=8
b.value=100
~~~

Here, `a` is final so it cannot be reassigned; `b` is not final and can switch to a new Counter. `a` being final **does not** protect `a.value` from changes via the alias `b`.

**Distinguish three levels:**

1. **Non-reassignable reference variable**: `final Box b`.
2. **Object providing a non-mutating API**: for example, a properly designed immutable type.
3. **Entirely unmodifiable object graph**: a stronger requirement; every nested mutable object must also be protected or copied according to the contract.

An object containing `final List<String> items` **is not necessarily immutable**, because the list that `items` points to may still be mutable.

## 6. String: Aliasing Still Exists, but Strings Are Immutable

`String` is a reference type. Two `String` variables can reference **the same object**, but the content of a String object **cannot be modified in place** through the normal API.

Save **`ImmutableStringDemo.java`**:

~~~java
public class ImmutableStringDemo {
    public static void main(String[] args) {
        String first = "Hi";
        String alias = first;

        System.out.println("initial identity=" + (first == alias));

        alias = alias + "!";
        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("identity after concat=" + (first == alias));
    }
}
~~~

Run:

~~~bash
javac ImmutableStringDemo.java
java ImmutableStringDemo
~~~

Output:

~~~text
initial identity=true
first=Hi
alias=Hi!
identity after concat=false
~~~

`alias = alias + "!"` creates **a new string value** and reassigns the variable `alias`. It does not change the contents of the String `"Hi"` that `first` still references.

This does not mean aliasing “does not happen with immutable objects”. Aliases can still share a reference; it is just that **no change to the object's content can be observed through another variable** because the object is immutable. Immutability makes sharing references safer.

**Be careful with concluding `String a == b`**: String literals may share the same object due to interning, but Strings from different sources may still not share the same identity. To compare content, use `equals`, not `==`.

## 7. Parameter Passing: Java Passes by Value, Including Reference Values

When a caller passes an object reference to a method, Java **copies the reference value** into the parameter variable. Therefore:

- The parameter initially references the same object as the caller's variable.
- The method can modify the **object** through the parameter if the object permits it and access rights allow.
- Reassigning the **parameter** to another object **does not reassign the caller's variable**.
- For primitive arguments, the parameter receives a copy of the primitive value; reassigning it also does not modify the caller's variable.

Save the file **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutateThenReassign(Box parameter) {
        parameter.value += 5;
        parameter = new Box(999);
        System.out.println("inside object=" + parameter.value);
    }

    static void changePrimitive(int number) {
        number += 100;
        System.out.println("inside primitive=" + number);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        mutateThenReassign(original);
        System.out.println("outside original=" + original.value);
        System.out.println("outside alias=" + alias.value);
        System.out.println("same object=" + (original == alias));

        int number = 7;
        changePrimitive(number);
        System.out.println("outside primitive=" + number);
    }
}
~~~

Compile/run:

~~~bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Output:

~~~text
inside object=999
outside original=15
outside alias=15
same object=true
inside primitive=107
outside primitive=7
~~~

Detailed analysis:

1. `original` and `alias` hold the same reference to Box A (initially `value = 10`).
2. Calling `mutateThenReassign(original)`: Java **copies the reference value A** into the parameter `parameter`. No new Box is created during the parameter-passing step.
3. `parameter.value += 5` modifies Box A to `15`; both the caller and the alias can observe this.
4. `parameter = new Box(999)` only makes the call's parameter point to Box B; `original` and `alias` in the caller **do not** change their references.
5. `changePrimitive(number)` receives a copy of `7` and prints `107` inside the method, while the variable `number` in `main` remains `7`.

**The accurate way to state it:** Java is **pass-by-value**. For objects, the value copied is the **reference**, so multiple variables can point to the same object. It is **not** pass-by-reference of a *variable* in the sense that the callee can directly reassign the caller's variable.

### 7.1. How to Change the Caller's Reference?

Instead of expecting reassigning the parameter to affect the caller, **return the new reference** and let the caller assign it:

~~~java
static Box replace(Box oldValue) {
    return new Box(oldValue.value + 1);
}

// Inside a method:
Box box = new Box(5);
box = replace(box);
~~~

This is an illustrative snippet requiring a suitable `Box` class. After the assignment statement, the caller explicitly switches `box` to the new object. This approach usually makes data flow clearer than a method secretly mutating object state unnecessarily.

## 8. Aliasing Through Instance Fields and the Object Graph

Multiple variables referencing the same object do not happen only because of `Box b = a`. Aliasing also occurs when **two fields on different objects hold the same reference**.

Example:

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Person {
    String name;
    Address address;

    Person(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
~~~

These are illustrative class declarations, without `main`.

If the caller writes:

~~~java
Address common = new Address("Ha Noi");
Person a = new Person("An", common);
Person b = new Person("Binh", common);
~~~

then `a` and `b` are **two different Person objects**, but:

~~~text
Person A ---- address ----+
                          |
                          +----> Address { city = "Ha Noi" }
                          |
Person B ---- address ----+
~~~

`a.address == b.address` is `true`. When `a.address.city = "Hue";`, reading `b.address.city` will see `"Hue"` because both reference the same `Address`.

This explains why “creating a new object” **does not guarantee that all internal data is independent**. The new object may receive references to existing components and share them.

### 8.1. Short Program Confirming Field Sharing

Save **`SharedFieldDemo.java`**:

~~~java
public class SharedFieldDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Person a = new Person("An", shared);
        Person b = new Person("Binh", shared);

        System.out.println("same address=" + (a.address == b.address));
        a.address.city = "Hue";
        System.out.println(a.name + "=" + a.address.city);
        System.out.println(b.name + "=" + b.address.city);
    }
}
~~~

Compile/run:

~~~bash
javac SharedFieldDemo.java
java SharedFieldDemo
~~~

Output:

~~~text
same address=true
An=Hue
Binh=Hue
~~~

Both `Person.address` fields are declared `final`, yet only **the reference value in the field cannot be reassigned**; the `Address` object remains mutable and remains shared. This is why ownership design or defensive copying is needed when you do not want data to be shared.

## 9. Aliasing with Arrays: `int[] b = a` Does Not Copy Elements

An array is an **object** in Java. A variable of type `int[]` stores a reference to an array, not a copy of its elements.

~~~java
int[] first = {1, 2, 3};
int[] alias = first;

alias[0] = 99;
System.out.println(first[0]); // 99
~~~

`alias[0]` and `first[0]` access **element 0 of the same array object**. The operation `alias = new int[]{7,8};` will only reassign the variable `alias`, without changing `first`.

### 9.1. Copying a One-Dimensional Array

To get another `int[]` array:

~~~java
int[] source = {1, 2, 3};
int[] copy = source.clone();
copy[0] = 100;

System.out.println(source[0]); // 1
System.out.println(copy[0]);   // 100
~~~

For a **one-dimensional primitive array**, `clone()` creates a new array and copies **the value of each element**. `Arrays.copyOf(source, source.length)` and `System.arraycopy` can also be used when appropriate.

For an **array containing references**, `clone()` only copies **the reference elements**: the objects they point to can still be shared.

### 9.2. Two-Dimensional Arrays: `clone()` Usually Only Copies the Outer Layer

Save the file **`ArrayAliasingDemo.java`**:

~~~java
public class ArrayAliasingDemo {
    public static void main(String[] args) {
        int[][] source = {
                {1, 2},
                {3, 4}
        };

        int[][] alias = source;
        int[][] shallow = source.clone();

        int[][] deep = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            deep[i] = source[i].clone();
        }

        source[0][0] = 99;

        System.out.println("source == alias=" + (source == alias));
        System.out.println("source == shallow=" + (source == shallow));
        System.out.println("row shared=" + (source[0] == shallow[0]));
        System.out.println("shallow[0][0]=" + shallow[0][0]);
        System.out.println("deep[0][0]=" + deep[0][0]);
    }
}
~~~

Compile/run:

~~~bash
javac ArrayAliasingDemo.java
java ArrayAliasingDemo
~~~

Output:

~~~text
source == alias=true
source == shallow=false
row shared=true
shallow[0][0]=99
deep[0][0]=1
~~~

Explanation:

- `alias` is **the same outer array** as `source`.
- `shallow = source.clone()` creates **a different outer array**, but each element still points to the **old subarrays**.
- Therefore `source[0] == shallow[0]` is `true`, and modifying `source[0][0]` shows up in `shallow[0][0]`.
- `deep` creates a new outer array **and copies each `int[]` subarray**. For the example structure having only `int[]` rows, this is an independent copy of the primitive elements; `deep[0][0]` remains `1`.

The term “deep copy” must always be understood **according to the structural depth that needs to be copied**. For an array containing objects with complex nested references, calling `clone()` on just one sub-level is not necessarily enough to create an independent copy of the entire object graph.

## 10. Collections: Aliases, Copies, and Read-Only Views

`List`, `Set`, and `Map` are all worked with through references. When you write:

~~~java
java.util.List<String> source = new java.util.ArrayList<>();
java.util.List<String> alias = source;
~~~

`source` and `alias` point to **the same ArrayList**. `alias.add("Java")` increases `source.size()` because it is the same object. However, `alias = new ArrayList<>()` only switches the variable `alias` to another list.

There are several approaches that **are not direct aliases**, and they must be distinguished:

| Creation approach | Creates a new container? | Shares component state? | When source adds/removes elements |
| --- | --- | --- | --- |
| `alias = source` | No | The exact same collection object | The alias sees the change |
| `new ArrayList<>(source)` | Yes | **Shallow** copy: copies element references | The new container does not automatically change size |
| `List.copyOf(source)` | Returns an unmodifiable list; may reuse in some cases per the API | Mutable element objects can still be shared | Does not reflect subsequent structural changes to source |
| `Collections.unmodifiableList(source)` | View that disallows mutating operations through the view | Same **backing list** for observation | The view can reflect changes in source |
| `List.of("A","B")` | Provides an unmodifiable list | Immutable String elements | No corresponding mutable source |

**“Unmodifiable through the list API” differs from “the list and all its elements are completely immutable”.** For example, `List.copyOf` creates/provides an unmodifiable list, yet if the elements are `StringBuilder` instances, modifying an element through another reference can still be observed.

### 10.1. Standalone Example: Snapshot and View

Save **`CollectionAliasingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionAliasingDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> alias = source;
        List<String> copy = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);

        alias.add("B");

        System.out.println("source=" + source);
        System.out.println("alias=" + alias);
        System.out.println("copy=" + copy);
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        source.set(0, "X");
        System.out.println("snapshot later=" + snapshot);
        System.out.println("view later=" + view);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Compile/run:

~~~bash
javac CollectionAliasingDemo.java
java CollectionAliasingDemo
~~~

Output:

~~~text
source=[A, B]
alias=[A, B]
copy=[A]
snapshot=[A]
view=[A, B]
snapshot later=[A]
view later=[X, B]
snapshot cannot add
~~~

**Points to remember:**

- `alias.add("B")` modifies the same list that `source` points to.
- `copy` and `snapshot` capture the element structure at creation time; they do not automatically receive the `"B"` element added later.
- `view` is an **unmodifiable view** of `source`; it prevents calling `add` through the view while still reflecting changes to the backing list.
- `snapshot.add("C")` throws `UnsupportedOperationException` because `List.copyOf` returns an unmodifiable list.
- Do not rely on `snapshot != source` as an **identity guarantee** for all inputs: the API may reuse the object if the input is already a suitable unmodifiable list.

## 11. Shallow Copy Differs from Deep Copy of an Object Graph

Suppose a `Person` holds a reference to an `Address`. Creating a new Person by passing **the same `Address`** is a **shallow copy** of the structure in the example:

~~~java
Person clone = new Person(original.name, original.address);
~~~

`clone` is a new Person object, yet `clone.address == original.address` is still `true`. Modifying the address on the original also affects the shallow copy.

To isolate the `Address` state, you need to create a new Address and copy its meaningful contents, for example `new Address(original.address.city)`. This is a deep copy step for the **specific two-level** object graph under consideration.

### 11.1. Standalone Runnable Java Example on Shallow/Deep Copy

Save **`CopyDepthDemo.java`**:

~~~java
public class CopyDepthDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person copyShallow() {
            return new Person(name, address);
        }

        Person copyDeepForThisModel() {
            return new Person(name, new Address(address.city));
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Lan", new Address("Ha Noi"));
        Person shallow = original.copyShallow();
        Person deep = original.copyDeepForThisModel();

        System.out.println("same Person=" + (original == shallow));
        System.out.println("shallow shares Address=" +
                (original.address == shallow.address));
        System.out.println("deep shares Address=" +
                (original.address == deep.address));

        original.address.city = "Hue";
        System.out.println("original=" + original.address.city);
        System.out.println("shallow=" + shallow.address.city);
        System.out.println("deep=" + deep.address.city);
    }
}
~~~

Run:

~~~bash
javac CopyDepthDemo.java
java CopyDepthDemo
~~~

Output:

~~~text
same Person=false
shallow shares Address=true
deep shares Address=false
original=Hue
shallow=Hue
deep=Ha Noi
~~~

Analysis:

1. Both copy methods create a new `Person`: `original == shallow` is `false`.
2. `copyShallow` passes the old `address`, so `original.address == shallow.address` is `true`.
3. `copyDeepForThisModel` creates a new Address, so the reference to Address is no longer shared.
4. `original.address.city = "Hue"` modifies the old Address; `shallow` observes `Hue`, while `deep` keeps `Ha Noi`.

**Limitation:** This is a deep copy for a simple model that has only one mutable reference field `Address`. In an object graph with cycles, identities that need to be preserved, nested collections, or external resources, true deep copying can be complex and must be defined by contract. You should not call a default `clone()` method a “deep clone” without proving that it copies every required component.

### 11.2. When Is a Shallow Copy Sufficient?

A shallow copy is usually sufficient when:

- The shared elements are **immutable**, such as `String` and certain properly designed value objects.
- The API **intentionally shares** component objects, such as shared services or caches.
- The data is not modified within the relevant lifecycle.
- Ownership and update rules are clearly defined.

Conversely, if the internal data is mutable and each copy must be completely independent, you must inspect every nested reference before choosing deep copy, an immutable model, or copy-on-write.

## 12. Designing Constructors/Getters to Avoid Unintended Aliasing

A common way mutable state leaks is when a constructor **directly retains an external reference** or a getter **returns a reference to an internal mutable collection**.

### 12.1. Design Vulnerable to External Modification

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

This is a compilable illustrative class. `members` is declared `final`, yet:

- The caller can still keep the `source` variable and call `source.add("X")`; `Team.members` observes the change because it is the same list.
- A caller obtaining `team.members()` and calling `add` on the returned list also directly modifies Team's state.

If Team wants to control the member list, this is **exposure of mutable representation**.

### 12.2. Using Defensive Copying for a String Collection

Save **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    static final class Team {
        private final List<String> members;

        Team(List<String> input) {
            this.members = List.copyOf(input);
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> external = new ArrayList<>(List.of("Lan"));
        Team team = new Team(external);

        external.add("Minh");

        System.out.println("external=" + external);
        System.out.println("team=" + team.members());

        try {
            team.members().add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("team list cannot add");
        }
    }
}
~~~

Compile/run:

~~~bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Output:

~~~text
external=[Lan, Minh]
team=[Lan]
team list cannot add
~~~

`List.copyOf(input)` creates/provides an unmodifiable list with **the element contents at the time of the call**. Because the elements are immutable `String` objects, Team does not have to worry about users changing the contents of each `String`. The getter returns that unmodifiable list itself, so callers cannot `add` to Team's list.

**If the list contains mutable objects**, `List.copyOf` still keeps references to those elements. When deep immutability is needed, you must copy the elements or use appropriate immutable value objects. In addition, `List.copyOf` does not accept null elements; therefore, that also becomes part of the constructor contract that needs to be documented.

### 12.3. For Arrays, Copy When Receiving and Returning

~~~java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        this.values = values.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

This is a valid illustrative class. `clone()` on `int[]` creates a copy of the primitive values; the caller cannot modify the internal array simply by keeping the original array or mutating the array returned by the getter.

If `values` is `Person[]`, clone only copies the **element references**, without automatically copying each Person. In that case, the necessary level of protection depends on whether Person is mutable and the data ownership rules.

## 13. Static Fields Can Be a Source of Object Sharing

Two instance fields belonging to two different objects generally store reference values **independently in terms of field storage location**, yet they **can point to the same object** if assigned that way. Meanwhile, a **static field** itself is associated with the class, holding a single shared value within the scope of that class.

Example:

~~~java
class Repository {
    static final java.util.List<String> SHARED =
            new java.util.ArrayList<>();

    private final java.util.List<String> local =
            new java.util.ArrayList<>();
}
~~~

This is an illustrative class:

- `Repository.SHARED` is a static field holding a shared list reference; code accessing it sees the same list.
- On each `new Repository()`, the `new ArrayList<>()` initializer allocates a separate list for the `local` field of the new object.
- However, `final` on both fields only prevents **reassigning the field reference**, without making the list itself immutable.

Do not use `static` merely for “convenience in accessing data” if the data actually belongs individually to each object. Also, do not assume every instance field automatically creates a new list: if the initializer is `local = Repository.SHARED`, separate instance fields can still hold **the same reference**.

## 14. Aliasing and Garbage Collection

Java automatically manages memory through the runtime's garbage collection (GC) mechanism. Multiple variables holding references to an object can keep the object **reachable**, depending on variable scope and reference relationships.

Example:

~~~java
Object first = new Object();
Object second = first;
first = null;
~~~

At a point where the code can still use `second`, the object remains reachable through `second`. Assigning `first = null` **does not directly invoke a destructor**, does not force GC to run immediately, and does not erase data to invalidate `second`.

If later **there are no remaining reachable reference paths** to the object from GC roots, the object may become eligible for reclamation. **The timing of GC is not guaranteed by Java to be immediate**. `System.gc()` is also not a command guaranteed to free the exact object at the exact moment.

An object can remain reachable through fields, static caches, collections, closures/inner classes, threads, or other references rather than just the local variable you are currently looking at.

### 14.1. Reference Cycles Do Not Automatically Mean Leaks

Two objects A and B whose fields point to each other can form a cycle A → B → A. If **there is no longer a reachable path from GC roots**, that cycle can still be handled by GC; Java does not require “manual reference counting” and does not keep every cycle alive forever by default.

Conversely, a static collection accidentally retaining an object long-term can prevent data from being reclaimed even though the caller thinks all local variables were dropped. The issue is **reachability and lifecycle**, not merely the number of arrows in a diagram.

## 15. Aliasing in Multithreaded Programs

If multiple variables across different threads point to **the same mutable object**, they can access and modify **shared state**. Aliasing by itself does not equate to a data race, but it creates the conditions for sharing data.

Illustrative example:

~~~java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

If the same `Counter` is shared across multiple threads and threads concurrently call `increment()` without synchronization, the `value++` operation is **non-atomic** and can lose increments. Simply having two variables referencing the same Counter **does not** provide synchronization.

Options depending on the problem:

- Avoid sharing mutable objects; use immutable values or copy according to ownership.
- Use synchronization/locks if multiple operations must preserve an invariant together.
- Use `AtomicInteger` or an appropriate atomic type for simple numeric operations.
- Define thread-confinement or message-passing rules when appropriate.

Note that `final Counter c` does not make `c.value++` atomic. `final` prevents changing the reference variable; it is not a multithreading lock.

## 16. Misconceptions and Fixes

| Misconception | Correct explanation / fix |
| --- | --- |
| “`Box b = a` creates a copy of Box.” | It only copies **the reference value**; to create a new Box, use an appropriate constructor/copy/factory. |
| “Two variables must mean two objects.” | There can be multiple aliases for one object, or one variable pointing to multiple objects sequentially. |
| “If two objects have identical fields, `a == b` is true.” | `==` on references compares **identity**, not fields. |
| “`equals()` compares all fields by default.” | `Object.equals` defaults to identity; a class must override it when value equality is desired. |
| “Assigning `b = new Box(...)` makes `a` change too.” | Only `b` changes its reference value; `a` still retains the old reference. |
| “`b.field = 10` only changes information private to variable b.” | The field belongs to the **object**, so every alias to the same object observes the new state. |
| “`a = null` deletes the object even though `b` still references it.” | `a` simply stops pointing to the object; `b` can still use the object. |
| “Java passes objects by reference to the caller's variable.” | Java passes **a copy of the reference value**; reassigning the parameter does not reassign the caller's variable. |
| “`final List` is an immutable list.” | `final` only prevents reassigning the reference variable/field; the list itself can be mutable. |
| “`String b = a`, and then concatenating characters to b modifies a.” | String is immutable; concatenation creates a new string value and reassigns b. |
| “`int[][] copy = original.clone()` copies every element in every row.” | It only copies the outer array; the `int[]` rows can still be shared. |
| “`new ArrayList<>(source)` also copies all element objects.” | It is only a shallow copy of the container; element references are still shared. |
| “`Collections.unmodifiableList(source)` is a snapshot.” | It is typically a read-only **view** tied to the backing list; when source changes, the view can reflect it. |
| “`List.copyOf(source)` turns each mutable element into an immutable one.” | Only the list structure cannot be modified; the contents of element objects can still change. |
| “A getter returns the internal list, yet `private final` is enough protection.” | The caller can modify the list if it is mutable; use a defensive copy or an unmodifiable API as appropriate. |
| “Sharing the same object across threads is automatically safe.” | There is no thread-safety guarantee; proper synchronization or immutability is required. |
| “Once no local variable remains, the object is guaranteed to be deleted immediately.” | GC depends on reachability and runtime decisions; the object may still be retained via a field/cache. |

## 17. Reasoning Process When Seeing Multiple Reference Variables

When reading code with multiple reference variables, you can follow these steps:

1. **Mark every place an object is created**: `new`, factories, clone/copy, objects returned from methods. Do not assume a factory always calls `new`.
2. **Draw variables/fields as arrows** to objects; at the beginning, note clearly which arrows point to the same object.
3. **When encountering `b = a`**, have `b` point to the same object as `a` at **the time of assignment**; do not create a new object.
4. **When encountering `b.field = ...` or `b.methodMutating()`**, change the state of **the object that b is pointing to**, not “state stored inside the name b”.
5. **When encountering `b = new ...` or `b = null`**, redirect **arrow b**; other arrows do not automatically move with it.
6. **If a method receives a reference**, add a parameter variable initially pointing to the same object; track mutation and rebinding separately.
7. **If there is a copy**, ask explicitly: copy the container? copy the elements? copy nested objects? Are there immutable values or intentional shared dependencies?
8. **If comparing**, separate `==` (identity) from `equals` (logical contract). For nullable references, consider `Objects.equals`.
9. **If there is multithreading or long-lived data**, check which aliases still keep the object reachable and whether all shared mutations are synchronized.

This is a more effective process than guessing which `new` was “called most recently” or assuming each variable name corresponds to a separate object.

## 18. Self-Check with Answers

### Question 1. One Object or Two?

~~~java
Box x = new Box(2);
Box y = x;
~~~

**Question:** How many `Box` objects are created by these two lines?  
**Answer:** One. `y` receives the same reference as `x`, without calling `new`.

### Question 2. Reading Through an Alias After Mutation

~~~java
Box x = new Box(2);
Box y = x;
y.value = 8;
~~~

**Question:** What is `x.value`?  
**Answer:** `8`, because x and y share the same Box.

### Question 3. Reading After Reassignment

~~~java
Box x = new Box(2);
Box y = x;
y = new Box(8);
~~~

**Question:** What is `x.value` and what is `x == y`?  
**Answer:** `x.value == 2`, `x == y` is `false`. Reassigning y does not modify x.

### Question 4. Objects with Identical Fields but Different Identities

~~~java
Box a = new Box(10);
Box b = new Box(10);
~~~

**Question:** What is `a == b`?  
**Answer:** `false`, because there are two separate objects even though their fields are equal.

### Question 5. Passing a Parameter

~~~java
static void reset(Box p) {
    p = new Box(0);
}
~~~

**Question:** Does `reset(myBox)` make `myBox` point to a new object?  
**Answer:** No. Java copies the reference into p; only p is reassigned. To change the caller's variable, return the new reference and let the caller assign it.

### Question 6. Mutation Inside a Method

~~~java
static void reset(Box p) {
    p.value = 0;
}
~~~

**Question:** After `reset(myBox)`, can `myBox.value` become `0`?  
**Answer:** Yes. p and myBox refer to the same object at call time; the method modifies that object.

### Question 7. Final Reference

**Question:** Does `final Box box = new Box(1);` prevent `box.value = 2;`?  
**Answer:** No. The `value` field remains mutable if there are no other constraints; `final` only prevents reassigning the variable box.

### Question 8. String

**Question:** Given `String a = "A"; String b = a; b += "B";`, what is a?  
**Answer:** `"A"`. String is immutable; b is reassigned to the new `"AB"` string.

### Question 9. Array Clone

**Question:** With `int[][] original`, does copying via `original.clone()` guarantee independent subarrays?  
**Answer:** Not yet. Clone copies the outer array, and each outer array element is still a reference to the old `int[]` subarrays.

### Question 10. Collection Copy

**Question:** Why can `new ArrayList<>(listOfPersons)` still share state with the old list?  
**Answer:** It copies the **references to each Person**, not the Person objects; if the Persons are mutable, both lists can still observe changes to the shared Person.

### Question 11. Snapshot and View

**Question:** What is the difference between `List.copyOf(source)` and `Collections.unmodifiableList(source)` when source undergoes structural changes later?  
**Answer:** `List.copyOf` provides an unmodifiable list with the elements at creation time; `Collections.unmodifiableList(source)` is an unmodifiable **view** over source and therefore can reflect changes to source.

### Question 12. Null

**Question:** After `Box a = new Box(1); Box b = a; a = null;`, can `b.value` be accessed?  
**Answer:** Yes, it still reads `1`, because b still references the object.

### Question 13. Equality

**Question:** For two Persons that are different objects with the same `id`, is `a.equals(b)` necessarily true?  
**Answer:** Not necessarily. It depends on whether Person overrides `equals` based on `id`. `a == b` is still false if they are two different objects.

### Question 14. Thread Safety

**Question:** Two threads both point to Counter and call `counter.value++`; is merely making the reference variable `final` enough to avoid a race?  
**Answer:** No. `final` does not make the field update atomic or synchronized.

## References

- Java Language Specification, [§4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): references and objects.
- Java Language Specification, [§4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): variables, variable types, and values.
- Java Language Specification, [§15.21.3 — Reference Equality Operators == and !=](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.3): equality testing between references.
- Java Language Specification, [§15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): argument evaluation and method invocation.

## Key Takeaways

**Multiple variables can hold the same reference value pointing to an object**. Writing `b = a` does not create a new object: it creates an **alias**. Modifying **object state** through one alias allows other aliases to the same object to observe the change; conversely, **reassigning a reference variable** to another object or `null` does not automatically reassign the remaining variables.

`==` between references checks for **the same object**; `equals` checks for **equality according to the type's contract**. Java **passes parameters by value**, even when the value copied is a reference. For arrays/collections/nested objects, copying a container is usually only a **shallow copy**; if independent state is required, you must decide on the level of defensive/deep copying or use immutable values. Clearly understanding these relationships is the foundation for avoiding bugs involving shared mutable state, identity, ownership, and concurrency.
