# Passing a Copy of a Reference into a Method in Java

In Java, **every argument is passed by value (*pass-by-value*)**, including arguments of reference types such as `String`, `Customer`, `int[]`, `List<String>`, or an interface. When calling a method with a reference variable, Java **copies the reference value** into the method's **formal parameter variable (*formal parameter*)**. **It does not copy the entire object**, nor does it **pass the caller's variable itself for the method to reassign it**.

This is a very important rule that is easy to misunderstand because Java allows a method to **modify the state of the object** referenced by both the caller and the callee. An operation such as `parameter.name = "Mai"` can be observed by the caller; however, `parameter = new Customer("Mai")` does **not** change the variable that the caller passed in. Both are completely consistent with the **pass-by-value** mechanism.

This lesson uses Java 17+, presenting everything from reference diagrams to runnable code, along with cases for immutable String, arrays/collections, `null`, `final`, generics, varargs, methods returning a reference, and API design to avoid unintended side effects.

## 1. Distinguishing Reference Variables, Reference Values, and Objects

Consider the declaration:

~~~java
class Customer {
    String name;

    Customer(String name) {
        this.name = name;
    }
}
~~~

This is a **class declaration snippet**, without a standalone runnable `main`.

In another method:

~~~java
Customer first = new Customer("Lan");
Customer alias = first;
~~~

There are three concepts to keep separate:

1. `first` is a **variable** with declared type `Customer`.
2. **The value of `first`** is a **reference** to a `Customer` instance.
3. The instance created by `new Customer("Lan")` is the **object**, holding the field `name` with the value `"Lan"`.

`alias = first` copies the **reference value** into the variable `alias`, so the two variables point to the same object. No second object is created by that assignment.

~~~text
Variable first  -----+
                     +------> Customer object { name = "Lan" }
Variable alias  -----+
~~~

The connecting lines only represent reference relationships, not physical RAM addresses. The Java specification does not require source code to be able to access raw object addresses.

**Rule to remember before learning parameter passing:** a reference variable is not an object; it **holds a reference value to an object or `null`**. When assigning one reference variable to another, Java copies the reference value, rather than automatically cloning the object.

## 2. What Happens at a Method Call?

Consider the method:

~~~java
static void inspect(Customer person) {
    System.out.println(person.name);
}
~~~

And the call:

~~~java
Customer customer = new Customer("Lan");
inspect(customer);
~~~

When the call is executed:

1. Java evaluates the argument expression `customer`, obtaining the **reference value** to the `Customer` object.
2. The method's parameter `person` receives **a copy of that reference value**.
3. Throughout the call, `customer` and `person` are **two separate variables**, yet both point to **one object**.
4. When the method finishes, the parameter variable `person` is no longer in scope for that call; the caller's variable `customer` still exists and still holds its original reference value, unless the caller itself or another mechanism has changed it.

~~~text
CALLER                                      CALLEE

customer -------+                          person ------+
                |                                        |
                +------------------+---------------------+
                                   |
                                   v
                       Customer { name = "Lan" }
~~~

**There is no “passing an object by value” here:** the object is not deep-copied during the call. **Nor is there “passing the customer variable by reference”:** the method does not have permission to change the value of the `customer` variable just by reassigning `person`.

Java uses the pass-by-value mechanism for **every parameter**. The difference between primitives and references is **the kind of value being copied**, not that Java switches from pass-by-value to pass-by-reference.

## 3. Two Behaviors That Must Be Distinguished: Modifying the Object and Reassigning the Parameter

### 3.1. Modifying the State of the Shared Object

~~~java
static void rename(Customer person) {
    person.name = "Mai";
}
~~~

Suppose the caller has:

~~~java
Customer customer = new Customer("Lan");
rename(customer);
System.out.println(customer.name); // Mai
~~~

The `rename` method receives a copy of the reference in `person`. Then `person.name = "Mai"` **accesses and modifies the field of the object** to which both `person` and `customer` point. The caller sees `"Mai"` because **the object changed**, not because the `customer` variable was passed by reference.

### 3.2. Reassigning the Parameter to Another Object

~~~java
static void replace(Customer person) {
    person = new Customer("Hà");
}
~~~

Caller:

~~~java
Customer customer = new Customer("Lan");
replace(customer);
System.out.println(customer.name); // Lan
~~~

This time the method executes `person = new Customer("Hà")`. It creates a new `Customer` and then **reassigns the local parameter variable `person`**. The `customer` variable at the caller is not reassigned; it still points to the original `"Lan"` object.

~~~text
BEFORE replace reassigns:

customer ------+
               +----> Customer A { name = "Lan" }
person --------+

AFTER replace reassigns:

customer ------------> Customer A { name = "Lan" }
person --------------> Customer B { name = "Hà" }
~~~

The two variables only share the object until `person` receives a different reference value. **There is no pointer to the “customer variable slot” for an assignment inside the method to modify the caller's variable**.

### 3.3. Assigning `null` to the Parameter Does Not Clear the Caller's Variable Either

~~~java
static void clearParameter(Customer person) {
    person = null;
}
~~~

After `clearParameter(customer)`, the caller still keeps `customer` pointing to the old object. Assigning `person = null` only changes the value of the parameter inside the method.

If the caller wants the `customer` variable to become null, **the caller must assign** `customer = null` itself or explicitly use a value returned from the method according to its contract.

## 4. Complete Java 17+ Example: Modifying an Object, Replacing a Parameter, Passing an Alias

Save the file **`ReferencePassingDemo.java`**:

~~~java
public class ReferencePassingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box item) {
        item.value = 20;
    }

    static void reassign(Box item) {
        item = new Box(90);
        item.value = 91;
    }

    static void mutateThenReassign(Box item) {
        item.value = 30;
        item = new Box(70);
        item.value = 80;
    }

    static void clearParameter(Box item) {
        item = null;
    }

    static Box createReplacement(Box old) {
        return new Box(old.value + 100);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        mutate(original);
        System.out.println("After mutate = " + original.value);

        reassign(original);
        System.out.println("After reassign = " + original.value);

        mutateThenReassign(original);
        System.out.println("After both = " + original.value);

        clearParameter(original);
        System.out.println("Still non-null = " + (original != null));
        System.out.println("Alias same = " + (alias == original));

        Box replacement = createReplacement(original);
        System.out.println("New value = " + replacement.value);
        System.out.println("Old value = " + original.value);
        System.out.println("Same object = " + (replacement == original));

        original = replacement;
        System.out.println("Caller reassigned = " + original.value);
        System.out.println("Alias still old = " + alias.value);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ReferencePassingDemo.java
java ReferencePassingDemo
~~~

**Exact stdout:**

~~~text
After mutate = 20
After reassign = 20
After both = 30
Still non-null = true
Alias same = true
New value = 130
Old value = 30
Same object = false
Caller reassigned = 130
Alias still old = 30
~~~

Explanation in order:

1. `original` points to `Box(10)`; `alias = original` creates **an alias to the same object**, without cloning.
2. `mutate(original)` copies the reference value to `item`. `item.value = 20` modifies the shared object, so the caller sees 20.
3. `reassign(original)` creates `Box(90)` and assigns it to the **parameter** `item`. It goes on to modify the new object to 91, but `original` still points to the old Box holding the value 20.
4. `mutateThenReassign(original)` modifies the old object to 30 **before** assigning `item` to a new Box. The caller sees 30, not 80; this demonstrates that the two operations have different effects.
5. `clearParameter(original)` only assigns `item = null`; `original != null` remains true.
6. `alias == original` remains true because both still point to the same old Box.
7. `createReplacement(original)` **returns a reference** to a new object with the value `30 + 100 = 130`. `replacement == original` is false.
8. The caller itself executes `original = replacement`, so from that point on `original` points to the new Box. `alias` still points to the old Box with the value 30.

A way to remember this: **modifying the object through the parameter can be observed from the caller; reassigning the parameter itself does not change the reference variable on the caller side**.

## 5. Comparison with Passing Primitive Parameters

Both primitives and references are pass-by-value, but the values copied are different.

~~~java
static void updateNumber(int value) {
    value = 99;
}

static void updateBox(Box box) {
    box.value = 99;
}
~~~

With a primitive:

~~~java
int number = 10;
updateNumber(number);
// number still equals 10
~~~

The method receives **a copy of the number 10** in the parameter `value`. Changing `value` does not affect the caller's variable `number`.

With a reference:

~~~java
Box box = new Box(10);
updateBox(box);
// box.value is 99
~~~

The method receives **a copy of the reference**, pointing to the same Box. It does not reassign the `box` variable, but modifies the `Box` object through the reference.

| Situation | What is copied on call | What does the caller see? |
| --- | --- | --- |
| `change(int n)` then `n = 99` | `int` value | The caller's `int` variable is unchanged |
| `change(Box b)` then `b = new Box(...)` | Reference value | The caller's `Box` variable is unchanged |
| `change(Box b)` then `b.value = 99` | Reference value | The shared object has the new field value 99 |
| `change(Box b)` then `b = null` | Reference value | The caller's variable still holds the old reference |
| `change(Box b)` then `b.update()` | Reference value | Depending on `update()`, the object may be modified |

**Note:** you should not say “Java uses pass-by-value only for primitives, and pass-by-reference for objects”. The accurate statement is that **Java passes by value**, and a **value can be a reference**.

## 6. Why Does Calling a Method on an Object Affect the Caller?

A method such as:

~~~java
static void addItem(java.util.List<String> items) {
    items.add("Java");
}
~~~

receives a **reference to a List object**. Because `add` is an operation on the object itself, a caller holding a reference to the same List will see the new element, provided the collection is mutable and the operation succeeds.

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
addItem(list);
System.out.println(list); // [Java]
~~~

This is a fragment inside a method. Sharing an object is a normal mechanism of Java OOP, not evidence of “pass-by-reference” in the sense of passing the caller's variable.

Compare the following way of writing it:

~~~java
static void replaceList(java.util.List<String> items) {
    items = new java.util.ArrayList<>();
    items.add("Khác");
}
~~~

Calling `replaceList(list)` does not make `list` on the caller side point to the new ArrayList. The new object is only assigned to the parameter `items`; the caller still keeps the old list.

### 6.1. A Reference Parameter Is a New Variable

Intuitively, the call:

~~~java
updateBox(box);
~~~

can be pictured as the method receiving a **separate variable** initialized with the argument's reference value:

~~~text
At caller:     box  -> Box object
On call:       param = copy of the value in box
In method:     param -> same Box object (until param is reassigned)
~~~

However, this is a conceptual diagram rather than Java programmers actually declaring parameters via assignment as in code. Java defines the details of argument evaluation, parameter binding, and method invocation according to the language specification; the compiler/JIT may optimize the implementation while preserving the observable semantics.

## 7. Arrays: Changing an Element Differs from Reassigning the Array Parameter

Arrays in Java are objects. An `int[] values` parameter is a **reference-type** parameter, not a primitive parameter simply because its elements are `int`.

~~~java
static void changeElement(int[] values) {
    values[0] = 99;
}

static void replaceArray(int[] values) {
    values = new int[]{7, 8, 9};
}
~~~

With the caller:

~~~java
int[] numbers = {1, 2, 3};

changeElement(numbers);  // numbers[0] becomes 99
replaceArray(numbers);   // numbers still points to the old array
~~~

Afterward, `numbers` still references the array containing `[99, 2, 3]`.

**Distinguish clearly:**

- `values[0] = 99` modifies an **element of the shared array object**.
- `values = new int[]{...}` reassigns **the parameter variable `values`**, without changing the `numbers` variable at the caller.
- `values = null` also only reassigns the parameter; the caller's array does not disappear because of that.
- If both the caller and the callee hold references to an **array of mutable objects**, the element objects can also be shared separately.

### 7.1. Complete Java Example for Arrays and StringBuilder

Save as **`ArrayAndBuilderDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayAndBuilderDemo {
    static void changeElements(int[] data) {
        data[0] = 9;
        data[1] = 8;
    }

    static void replaceArray(int[] data) {
        data = new int[]{100, 200};
    }

    static void changeBuilder(StringBuilder builder) {
        builder.append("!");
        builder = new StringBuilder("Other");
        builder.append("?");
    }

    static void replaceString(String text) {
        text = text.toUpperCase();
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2};

        changeElements(numbers);
        replaceArray(numbers);

        System.out.println("Numbers = " + Arrays.toString(numbers));

        StringBuilder text = new StringBuilder("Hi");
        changeBuilder(text);
        System.out.println("Builder = " + text);

        String label = "java";
        replaceString(label);
        System.out.println("String = " + label);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ArrayAndBuilderDemo.java
java ArrayAndBuilderDemo
~~~

**Exact stdout:**

~~~text
Numbers = [9, 8]
Builder = Hi!
String = java
~~~

Explanation:

1. `changeElements(numbers)` modifies the shared array elements; the caller's array changes to `[9, 8]`.
2. `replaceArray(numbers)` creates a new array in the callee but only reassigns the parameter. The caller's `numbers` is still the `[9, 8]` array.
3. `changeBuilder(text)` calls `append("!")` on the same StringBuilder object, so the caller sees `Hi!`. Afterward, it assigns the parameter `builder` to a new StringBuilder and modifies the new object, without turning the caller's object into `Other?`.
4. `replaceString(label)` assigns the parameter `text` to another String with the content `JAVA`; the caller's `label` variable remains the `"java"` reference.

The example emphasizes **three different factors**: object type, ability to change (*mutability*), and reassigning the parameter variable.

## 8. String: The Reference Is Copied, but the Object Content Is Immutable

`String` is a **reference type**, not a primitive. A `String` object is **immutable**: there is no normal way to change the content of the String instance itself after creation.

~~~java
static void changeName(String name) {
    name = name.toUpperCase();
}
~~~

If the caller:

~~~java
String name = "Lan";
changeName(name);
System.out.println(name); // Lan
~~~

then the caller's `name` is still `"Lan"`. The `toUpperCase()` method returns a String result; the assignment in the callee only changes **the parameter `name`**.

This often causes confusion: “Why does passing a String look just like a primitive?”. The reason is **not** that Java uses a different passing mechanism for String. Java still **copies the reference value** just as with any object; it is simply that **String does not allow modifying the content of the shared object**.

Compared to mutable `StringBuilder`:

~~~java
static void appendSuffix(StringBuilder builder) {
    builder.append("!");
}
~~~

When the caller has `new StringBuilder("Lan")` and passes it into `appendSuffix`, the caller sees `Lan!` because the method modifies the object.

| Parameter type | Can the object be modified through the parameter? | Does reassigning the parameter change the caller's variable? |
| --- | --- | --- |
| `String` | Cannot modify the String object's content through normal APIs | No |
| `StringBuilder` | Yes, for example `append` | No |
| `int[]` | Yes, for example modifying elements | No |
| Mutable `List<String>` | Yes, for example `add` | No |
| Immutable record with immutable components | Cannot modify state through normal accessors | No |

**Do not use `==` to compare String content** just because two variables may reference the same String literal. `==` on references compares identity; to compare content, use `equals` with appropriate null handling.

## 9. Passing `null` Is Also Just Copying a Reference Value

`null` is a valid value for reference-type parameters according to the language rules:

~~~java
static void inspect(String text) {
    if (text == null) {
        System.out.println("Missing");
        return;
    }
    System.out.println(text.length());
}
~~~

The call `inspect(null)` passes the null value into the parameter `text`. **No object is created or copied**.

If the code attempts to dereference null:

~~~java
static void wrong(StringBuilder builder) {
    builder.append("!"); // NPE if builder == null
}
~~~

then the method throws `NullPointerException`. This is a **null receiver** issue when calling an instance method, not a difference in Java pass-by-value.

### 9.1. A Method Cannot “Make It Non-Null” for the Caller by Assigning the Parameter

~~~java
static void initialize(StringBuilder buffer) {
    if (buffer == null) {
        buffer = new StringBuilder("ready");
    }
}
~~~

Caller:

~~~java
StringBuilder result = null;
initialize(result);
System.out.println(result == null); // true
~~~

Because `buffer` is a separate parameter, assigning a new object only gives the callee a new reference. The caller still has `result == null`.

**The right way when you want the caller to have a new object:** return the reference and let the caller assign it:

~~~java
static StringBuilder ensureBuffer(StringBuilder buffer) {
    return buffer == null
            ? new StringBuilder("ready")
            : buffer;
}

// In the caller:
StringBuilder result = null;
result = ensureBuffer(result);
~~~

Afterward, `result` can point to a non-null StringBuilder; **it is the assignment statement in the caller** that changed the value of the caller's variable.

## 10. What Are the Ways to Replace the Caller's Reference?

Because the parameter is not an alias of the **variable** on the caller side, a method cannot simply execute `parameter = new Object()` and cause the variable passed from the caller to change along with it. Use an explicit contract.

### 10.1. Returning a New Object and Assigning It at the Caller

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class AddressOps {
    static Address movedTo(Address old, String city) {
        return new Address(city);
    }
}
~~~

Caller:

~~~java
Address address = new Address("Huế");
address = AddressOps.movedTo(address, "Hà Nội");
~~~

`movedTo` receives a copy of the `old` reference; the result is a reference to **another Address**. The `address` variable is reassigned at the **caller**.

In a real API, the `old` parameter in the example is unused, so it can be omitted or the method can be designed to copy the remaining data from the old address to avoid a redundant parameter. This is a minimal example to emphasize how a reference is returned and received.

### 10.2. Modifying a Reference Field Inside a Holder Object

~~~java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}

class HolderOps {
    static void replace(Holder<StringBuilder> holder) {
        holder.value = new StringBuilder("new");
    }
}
~~~

If the caller has `Holder<StringBuilder> holder`, after `HolderOps.replace(holder)`, the `holder.value` field can change. Because both the caller and the callee reference the same **Holder object**, the method modifies **the Holder's state**, without reassigning the caller's `holder` variable.

This mechanism is useful in some APIs that use an output holder, but it can complicate the design, create shared mutable state, and require concurrency control. If only a new result is needed, **a return value is usually clearer**.

### 10.3. Replacing an Element of an Array or Collection Held by the Caller

~~~java
static void replaceFirst(StringBuilder[] slots) {
    slots[0] = new StringBuilder("new");
}
~~~

This method replaces **an element of the shared array object**. When the caller reads `slots[0]`, it sees the new object, yet the caller's `slots` variable still holds the reference value to the same array. This is also **not** pass-by-reference of the caller's variable.

## 11. `final` on a Parameter Does Not Change the Passing Mechanism

You can declare a parameter as `final`:

~~~java
static void update(final Customer person) {
    person.name = "Mai"; // Can be valid: modifying a mutable object
    // person = new Customer("An"); // Compile error: reassigning a final parameter
}
~~~

The `final` modifier here **does not make the object immutable**. It only **prevents the parameter variable `person` from being reassigned** inside the method. The method still receives a copy of the reference value as usual.

Some cases:

- `final int n`: cannot reassign the numeric parameter `n`.
- `final String text`: cannot reassign the reference parameter `text`.
- `final List<String> values`: cannot reassign `values`, though `values.add(...)` can still be called if the list is mutable and the contract allows it.
- `final Customer customer`: cannot change the reference in the parameter, though mutable fields on the object can be modified.

**Important distinction:** `final` restricts reassigning **the variable**; it does not change Java pass-by-value, does not clone the object, and is not a concurrency/thread-safety mechanism.

### 11.1. Do Not Confuse with a `final` Field

~~~java
class Registry {
    private final java.util.List<String> values;

    Registry(java.util.List<String> values) {
        this.values = values;
    }
}
~~~

The `values` field is final, but because the constructor **keeps the reference to the List object** provided by the caller, the caller can continue modifying that very list if it is mutable. To prevent aliasing, a snapshot/defensive copy is needed when the contract requires it.

## 12. Avoiding Exposing Mutable State: Defensive Copying

Knowing that Java passes a copy of the reference helps explain why a constructor like the following can be dangerous:

~~~java
import java.util.List;

class UnsafeTeam {
    private final List<String> members;

    UnsafeTeam(List<String> members) {
        this.members = members;
    }

    List<String> members() {
        return members;
    }
}
~~~

The caller and the `UnsafeTeam` object both hold references to **the same mutable List**. Calling `externalList.clear()` can remove team members after the constructor finishes; calling `team.members().add(...)` also modifies internal state without going through a controlled method.

### 12.1. Protecting with an Appropriate Snapshot

~~~java
import java.util.List;

class Team {
    private final List<String> members;

    Team(List<String> source) {
        if (source == null || source.isEmpty()) {
            throw new IllegalArgumentException("Danh sách trống");
        }

        List<String> snapshot = List.copyOf(source);
        for (String member : snapshot) {
            if (member.isBlank()) {
                throw new IllegalArgumentException("Tên thành viên trống");
            }
        }

        this.members = snapshot;
    }

    List<String> members() {
        return members;
    }
}
~~~

`List.copyOf` creates a list that cannot be modified via its API and does not accept null elements. With immutable `String` members, a structural snapshot is sufficient to prevent the caller from altering the team's contents through its own List.

**Do not confuse shallow copy with deep copy.** If the list contains `MutableMember`, `List.copyOf` still keeps references to the same MutableMember elements; the caller can modify an element if it holds a reference. Depending on the invariant, you need to copy/freeze each child object or design explicit ownership.

### 12.2. With Primitive Arrays

~~~java
class Scores {
    private final int[] values;

    Scores(int[] source) {
        this.values = source.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

This constructor needs additional `source != null` validation in a real API (if source is null, `clone()` throws an NPE). For an `int[]` array, `clone()` creates a separate array and copies each element's primitive value; therefore, the caller modifying the original array does not modify the internal array, and modifying the getter's result does not affect the internal array either.

**There is no automatic cloning at method boundaries:** it is the `source.clone()` code itself that creates the copy. Simply passing `source` to the constructor does not clone the array at all.

## 13. Generic Methods Are Still Pass-by-Value

A generic method using a reference type parameter:

~~~java
class GenericOps {
    static <T> T identity(T item) {
        return item;
    }
}
~~~

For example, `Customer returned = GenericOps.identity(customer)`: the parameter `item` receives a copy of the reference, and then the method **returns the same reference value**. No new `Customer` object is created.

If `item == null`, the method can also return null according to the declaration of `T` in the corresponding context. A generic method does not create a different parameter-passing mechanism, nor does it automatically guarantee non-null.

### 13.1. Java Does Not Support Pass-by-Reference Parameters Like C++ `T&`

Some languages allow a function to receive **an alias to the caller's variable itself** and reassign that variable. Java has no equivalent parameter syntax that allows a method to directly reassign the caller's local variable through a call.

When you see `Customer parameter` in a Java method, understand it as a **separate parameter variable** carrying a copied reference, not a “reference to the caller's Customer variable slot”.

## 14. Varargs Still Receive an Array Reference Value

A method:

~~~java
static int count(String... names) {
    return names.length;
}
~~~

uses a varargs parameter. In the body, `names` has the array type `String[]`, meaning it is a **reference parameter** according to Java's rules.

When the caller invokes `count("Lan", "Mai")`, the compiler/runtime processes the argument list according to the appropriate invocation and varargs array mechanism. If the caller passes a `String[]` array directly in a call of appropriate arity, the method can receive a reference to that array. In either case, **the parameter variable `names` is still a separate variable**, assigned a reference value via pass-by-value.

Example modifying an element:

~~~java
static void changeFirst(String... names) {
    names[0] = "New";
}
~~~

If the caller does:

~~~java
String[] a = {"Old"};
changeFirst(a);
System.out.println(a[0]); // New
~~~

then `changeFirst` modifies **an element in the same array** `a`. If the caller calls `changeFirst("Old")`, the array created by the varargs call is not held by the caller via a corresponding array variable; a side effect on that temporary array does not mean the caller has a String variable reassigned.

**Note:** `changeFirst` assumes the array is non-null and has at least one element. In real code, preconditions must be checked if callers are allowed to pass an empty or null array.

## 15. Shared References and Aliasing

If the caller has multiple variables referencing the same object:

~~~java
Box first = new Box(5);
Box second = first;
~~~

then after `mutate(first)`, the caller can observe the change through `second.value` because **both variables point to the same object**. This has nothing to do with whether the variable names are the same as or different from the parameter name.

Model:

~~~text
first  -------+
              +--------> Box { value = 20 }
second -------+
param  -------+  (while mutate is running)
~~~

Note the distinction between **shared references** and **mutable objects**:

- If both reference an immutable `String`, the caller and the callee cannot modify the String's content.
- If both reference a mutable `StringBuilder`, modifications through one side can be seen by the other.
- If both reference an `int[]` array, changing elements can be seen by the other.
- If both reference an immutable record containing only immutable components, code typically only observes state without modifying the object.
- If a record has a component that is a mutable reference, the final record does not automatically make the child object immutable.

**A copy of a reference is not a copy of the object's state.** If you need the callee's changes not to affect the caller, you must rely on immutable data, appropriate copying, or an ownership contract.

## 16. A Method Can Modify an Object and Return That Same Object

~~~java
class Counter {
    private int value;

    Counter add(int n) {
        this.value += n;
        return this;
    }

    int value() {
        return value;
    }
}
~~~

If the caller executes:

~~~java
Counter counter = new Counter();
Counter returned = counter.add(3);
System.out.println(returned == counter); // true
~~~

`return this` returns **the reference value to the current object**. `returned == counter` is true because they both point to the same instance.

In this example, there are two noteworthy copies of reference values:

1. At the call `counter.add(3)`, the receiver is the current object; `3` is copied into the primitive parameter `n`.
2. At the `return this` statement, the result is the reference value transferred to the caller and assigned to the variable `returned`.

Method chaining such as `counter.add(1).add(2)` relies on `return this` to continue calling on the same object. It does not prove that Java has pass-by-reference for the caller's variable.

## 17. Do Not Confuse a Copied Reference with an Object Copy

There are several different levels of “copy”:

| Operation | What is copied |
| --- | --- |
| `Customer b = a;` | Reference value |
| Passing `a` into `modify(Customer c)` | Reference value into parameter `c` |
| `return a;` | Returned reference value |
| `new Customer(a.name)` | Creates a new Customer object, copying/transferring the data handled by the constructor |
| `int[] b = a.clone();` | New array; the `int` elements are copied |
| `Address[] b = a.clone();` | New array; the elements are shallowly copied references |
| `List.copyOf(mutableList)` | Unmodifiable List containing element references, without deep-copying child objects |
| Structural deep copy | Each mutable object must be copied according to the design contract |

When someone says “Java copies the object when passing a parameter”, ask **which object is created? Where is the `new`, `clone`, or factory copy?** If a method merely takes `Customer c` and the caller merely passes `customer`, no object-copying step takes place from the parameter-passing syntax.

### 17.1. The Parameter-Passing Mechanism Does Not Dictate Memory Layout

Some resources use the phrase “Java passes a memory address” as an analogy, but the more accurate explanation is **copying a reference value**. Java does not allow ordinary code to read/assign a raw memory address, and the JVM may implement/optimize references in many ways as long as it preserves the semantics of the Java Language Specification.

Also, do not infer from parameter-passing syntax that every primitive must live on the stack and every reference must live on the heap. How the JVM/JIT lays out or eliminates allocations is an implementation detail and does not change the logical results of the examples.

## 18. Impact When Multiple Threads Are Involved

Pass-by-value is **not** synonymous with thread-safe. Two threads can receive **two copies of the reference value pointing to the same mutable object**. If they modify the object concurrently, a data race can occur.

~~~java
class UnsafeCounter {
    private int value;

    void increment() {
        value++;
    }
}
~~~

If two threads receive the same `UnsafeCounter` object and call `increment()`, both `value++` operations can race, causing a lost update. Even though each thread has its own parameter variable, **the shared object** still needs a synchronization strategy.

Example protected by a monitor:

~~~java
class SynchronizedCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int current() {
        return value;
    }
}
~~~

Operations on the same `SynchronizedCounter` object are synchronized through the instance's monitor, provided all relevant accesses follow that rule. **Simply declaring `final Box parameter` or copying a reference does not create synchronization.**

For a method that transfers a new object to the caller by returning a result, if the caller/program uses that object on another thread, **safe publication** and the mutability of the returned object must also be considered; the argument-passing mechanism does not automatically solve the entire Java Memory Model.

## 19. API Design: Should a Method Modify a Passed-In Object?

Some APIs **intentionally modify mutable input**:

~~~java
static void sortValues(int[] values) {
    java.util.Arrays.sort(values);
}
~~~

Callers want their array sorted in place, and that effect should be clearly documented.

Other APIs aim **not to modify the caller's data**:

~~~java
static int[] sortedCopy(int[] values) {
    int[] copy = values.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
~~~

The second approach creates a new array, sorts on the copy, and then returns a reference to the copy. The caller can choose to assign the result to a new variable or an existing variable.

Example:

~~~java
int[] numbers = {3, 1, 2};
int[] sorted = sortedCopy(numbers);
// numbers is still [3, 1, 2], sorted is [1, 2, 3]
~~~

This part is a method fragment; `values == null` will cause `clone()` to fail with an NPE. A real API should decide whether to reject null or use a default, and document it.

**Things to state clearly in the contract of a method that accepts references:**

- Does the parameter allow `null`?
- Is the method allowed to modify the state of the passed-in object?
- If a new object is created, does the method return a new reference or update a field in a holder?
- Is the caller or the callee responsible for closing resources/lifecycle?
- Is the reference retained for use after the method finishes?
- Is the data structure shallow-copied, deep-copied, or used as a read-only view?
- Is the method safe for concurrent callers using the same object?

You should not “modify an object without the caller knowing” inside a method named `get...` or `calculate...` when the caller has reason to expect a non-mutating query. Choose names like `sortInPlace`, `updateCustomer`, or `appendTo` when a side effect is the primary contract.

## 20. Common Misconceptions

1. **“Java passes objects by reference like a C++ reference parameter.”** Inaccurate. Java passes **the reference value by value**; the method has its own parameter variable and cannot reassign the caller's variable.
2. **“A method can modify an object's field, so it must be pass-by-reference.”** No. The caller and the callee point to the same object; the method modifies the shared object.
3. **“`param = new Box(...)` will change the object the caller points to.”** Wrong. It only changes the `param` variable in the callee.
4. **“`param = null` makes the caller lose the object.”** Wrong. The caller's variable does not change and other aliases still hold the object.
5. **“`String` is passed by a separate mechanism.”** Wrong. String is a reference; its observable behavior differs because it is **immutable**.
6. **“`int[]` is a primitive parameter because its elements are int.”** Wrong. An array is an object; an array parameter is a reference type.
7. **“Calling `items.add(x)` is the same as assigning `items = new List(...)`.”** Wrong. One modifies the List object; the other changes the value of the parameter variable.
8. **“`final Customer c` makes Customer unchangeable.”** Wrong. Final restricts reassigning **c**; it does not make the object immutable.
9. **“Returning a new object from a method automatically updates the caller's variable.”** No. The caller needs to receive and assign the return value if it wants to change its own variable.
10. **“Passing an object into a method automatically clones the object.”** Wrong. If a copy is needed, there must be explicit copying logic.
11. **“Copying a List with `List.copyOf` is a deep copy.”** Wrong if elements are mutable; element references can still be shared.
12. **“A null reference variable passed into a method will automatically create an object when needed.”** Wrong. Null is also copied; the callee must handle or reject it.
13. **“Simply copying the reference value avoids races between threads.”** Wrong. Two references can still point to the same mutable object.
14. **“The caller's variable and the parameter having the same name means they are a single variable.”** Wrong. Having the same name in different scopes does not mean being the same variable.
15. **“`return this` proves the caller passed by reference.”** Wrong. It is the operation of returning a reference value from a method.
16. **“Every change inside the callee is visible to the caller.”** Wrong. Only changes to shared state can be observed; local/parameter assignments do not automatically appear in the caller.

## 21. Self-Check Exercises with Answers

**Question 1.** If `Box b = new Box(10);` and `void f(Box x) { x.value = 20; }`, what is `b.value` after `f(b)`?

**Answer:** `20`. Both `b` and `x` point to the same Box object; the callee modifies the field on the shared object.

**Question 2.** If `void f(Box x) { x = new Box(20); }`, does variable `b` point to the new object after `f(b)`?

**Answer:** No. The callee only reassigns the parameter `x`; variable `b` still points to the old Box.

**Question 3.** A method takes `String s` and assigns `s = s.toUpperCase()`. Does the caller see its String variable change?

**Answer:** No. The parameter receives a copy of the reference; String is immutable; reassigning `s` only modifies the callee's variable.

**Question 4.** A `StringBuilder builder` is passed into a method that calls `builder.append("!")`. Can the caller see the `!` character?

**Answer:** Yes, if builder is non-null and the same object is shared. `append` modifies the StringBuilder's state.

**Question 5.** Is `int[] values` a primitive parameter or a reference parameter?

**Answer:** A reference parameter, because arrays are objects in Java. It is the elements of the array that have the primitive type `int`.

**Question 6.** Does calling `void reset(StringBuilder b) { b = null; }` make the caller's variable null?

**Answer:** No. `b` is a separate parameter and only it is assigned null.

**Question 7.** When the caller needs to receive a new object, which way is simpler: assigning the parameter inside the method or returning the object and assigning it at the caller?

**Answer:** Returning the new object with `return` and letting the caller write `variable = method(variable);` is usually clearer.

**Question 8.** If a parameter is declared `final List<String> list`, can the callee call `list.add("A")`?

**Answer:** It can, if the List object is mutable and other conditions allow it. `final` only prevents reassigning the parameter variable `list`.

**Question 9.** A constructor keeps `this.values = externalList`; can the caller modifying externalList afterward cause the state inside the object to change?

**Answer:** Yes, because the constructor only holds a copy of the reference to the same List object. You can perform a defensive copy if an independent snapshot is needed.

**Question 10.** Are two threads receiving two reference parameters pointing to the same `Counter` object automatically state-isolated?

**Answer:** No. The parameter variables are separate, but **the referent object** is still shared; appropriate synchronization is needed when concurrently modifying mutable state.

**Question 11.** Does passing `null` to a method that takes `Customer` cause any Customer object to be copied?

**Answer:** No. The null value is transferred into the parameter; there is no target object to copy or operate on.

**Question 12.** `int[] a = {1}; mutate(a);`, inside `mutate` the method assigns `a[0] = 5` and then `a = new int[]{9}`. What value does the caller see for `a[0]`?

**Answer:** `5`. The first element assignment modifies the shared array; assigning `a` to a new array only modifies the callee's parameter variable.

**Question 13.** `Holder<Customer> h` is passed into a method, and the method assigns `h.value = new Customer("A")`. Does the caller's variable `h` change its reference?

**Answer:** No; `h` still points to the same Holder. However, **the `value` field of the Holder object** has changed, so the caller observes the new Customer through `h.value`.

**Question 14.** Why does `return item;` in the generic method `<T> T identity(T item)` not create an object copy?

**Answer:** The method returns **the reference value** currently held in the parameter; there is no `new` or object-copying operation in the method.

## 22. Checklist When Reading or Designing a Method Call

1. **Classify the argument:** primitive or reference? For a reference, the copied value is the reference.
2. **Identify the actual object:** which variable is pointing to which object? Are there multiple aliases?
3. **Read the operation inside the method accurately:** `param = ...` reassigns the parameter; `param.field = ...` modifies the object.
4. **If passing an array/collection:** does the method modify elements/structure or assign the parameter to a new object?
5. **If the parameter is a String/immutable type:** can the object change, or does the method only create a new result?
6. **If the parameter has `final`:** remember that it prevents reassigning the variable, and does not make the object immutable.
7. **If you want to change the caller's variable:** use return + caller assignment, or explicitly use a holder with a clear contract.
8. **If you want to protect mutable input:** copy appropriately right at the boundary and consider child objects as well.
9. **If `null` is present:** does the method handle, validate, or dereference null according to the contract?
10. **If multiple threads are involved:** multiple copies of a reference can still point to the same mutable object; check synchronization.
11. **If the API has side effects:** name and clearly document the potential to modify parameter objects.
12. **When reading the result:** always compare the state of the caller's variable against the state of the referenced object, because those are two different things.

**Conclusion:** In Java, a method call **copies the reference value into a new parameter**, without copying the object and without passing the caller's “variable slot”. Because both references can point to **the same object**, the method is allowed to modify the object's state according to its API, yet **cannot reassign the caller's variable by assigning the parameter**. Clearly distinguishing **the variable**, **the reference value**, and **the referenced object** is the key to accurately understanding Java pass-by-value, aliasing, mutable state, and how to design safe methods.
