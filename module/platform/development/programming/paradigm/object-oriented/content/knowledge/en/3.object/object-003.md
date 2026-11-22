# Multiple References to the Same Object in Java

In object-oriented programming (OOP), **one object** can be accessed through **multiple reference variables**. This commonly occurs when assigning one object variable to another, passing an object to a method, retrieving one from a collection, or returning one through a getter.

The key point: **copying a reference does not create a new object**. When two variables refer to the same mutable object, a state change through either reference is visible through the other.

## 1. How Does a Reference Differ from an Object?

Consider this declaration:

~~~java
Student student = new Student("An");
~~~

- `new Student("An")` creates a new `Student` object.
- `student` is a reference variable used to access that object.
- The reference variable does not contain a complete copy of the `Student`; it holds a reference value to the object.
- Adding `Student another = student;` copies **the reference value** rather than creating a second `Student`.

For example:

~~~java
Student a = new Student("An");
Student b = a;
~~~

~~~mermaid
flowchart LR
    A["Tham chiếu a"] --> O["Một đối tượng Student\nname = An"]
    B["Tham chiếu b"] --> O
~~~

The diagram is **a conceptual model** of reference relationships, not a depiction of physical memory locations or actual addresses. Both `a` and `b` access **the same instance**.

Compare this with a primitive type:

~~~java
int x = 10;
int y = x; // Sao chép giá trị số nguyên
y = 20;

System.out.println(x); // 10
System.out.println(y); // 20
~~~

In the `int` example, changing `y` does not affect `x` because each variable holds its own value. Reference variables, however, can point to the same object, so the outcome depends on whether you **mutate the object** or **reassign a reference variable**.

## 2. Runnable Example: Two References Observe the Same Change

`Main.java`:

~~~java
import java.util.Objects;

public class Main {
    static class Student {
        private String name;

        Student(String name) {
            setName(name);
        }

        String getName() {
            return name;
        }

        void setName(String name) {
            String checked = Objects.requireNonNull(name, "name").trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException("Tên không được rỗng");
            }
            this.name = checked;
        }
    }

    public static void main(String[] args) {
        Student first = new Student("An");
        Student second = first; // Không gọi new

        System.out.println(first == second);  // true
        System.out.println(first.getName());   // An

        second.setName("Bình"); // Thay đổi đối tượng dùng chung

        System.out.println(first.getName());   // Bình
        System.out.println(second.getName());  // Bình
    }
}
~~~

Step-by-step explanation:

1. `new Student("An")` creates **one** object, referenced by `first`.
2. `second = first` copies its reference value; there is still only **one** object.
3. `second.setName("Bình")` modifies the `name` property of that object.
4. Because `first` refers to the same object, `first.getName()` also returns `Bình`.

This is **aliasing**: several references act as different “names” for accessing the same object.

## 3. Distinguishing State Changes from Reference Reassignment

The following operations produce very different results.

### Case A: Modifying the Object Itself

~~~java
Student a = new Student("An");
Student b = a;

b.setName("Chi");

System.out.println(a.getName()); // Chi
System.out.println(a == b);      // true
~~~

`b.setName(...)` acts on **the referenced object**. Both `a` and `b` continue to refer to the original object.

### Case B: Reassigning a Reference Variable

~~~java
Student a = new Student("An");
Student b = a;

b = new Student("Dung"); // Tạo đối tượng mới, thay tham chiếu ở b

System.out.println(a.getName()); // An
System.out.println(b.getName()); // Dung
System.out.println(a == b);      // false
~~~

~~~mermaid
flowchart LR
    A["a"] --> O1["Student #1\nname = An"]
    B["b"] --> O2["Student #2\nname = Dung"]
~~~

Assigning `b = new Student(...)` changes only **variable b's value**. It neither changes `a` nor deletes or automatically replaces the object referenced by `a`.

Another assignment can make the variables share a reference again:

~~~java
b = a;
System.out.println(a == b); // true
~~~

Comparison:

| Statement | Creates a new object? | Reassigns `a`? | Can a change be observed through `a`? |
| --- | --- | --- | --- |
| `Student b = a;` | No | No | Both variables share the same instance |
| `b.setName("Chi");` | No | No | Yes, `a.getName()` also sees “Chi” |
| `b = new Student("Dung");` | Yes | No | No; `a` still points to the old instance |
| `b = null;` | No | No | No; only `b` stops referencing the instance |
| `a = b;` | No | Yes | `a` points to the instance currently referenced by `b` |

**Rule to remember:** invoking a state-changing method through a reference affects the shared object; reassigning a reference variable affects only that variable.

## 4. How Can You Verify That References Point to the Same Instance?

In Java, `a == b` compares references to confirm whether they point to **the same object** (or are both `null`). Two instances with identical data can still have different identities:

~~~java
record Point(int x, int y) {}
Point a = new Point(3, 5);
Point b = new Point(3, 5);
Point alias = a;

System.out.println(a == alias); // true
System.out.println(a == b);     // false
System.out.println(a.equals(b)); // true: Point so sánh giá trị
~~~

`equals()` answers a **different** question: does the class consider these values equivalent? It is not an alias test. The next lesson explores the `equals/hashCode` contract, `String`, and collections.

## 5. Aliasing Can Occur Within a Single Method Call

Java passes arguments **by value**. When arguments reference objects, parameters receive copies of reference values, so two parameters can even point to **the same object**:

~~~java
static void incrementBoth(Box x, Box y) {
    x.value++;
    y.value++;
}

Box box = new Box(0);
incrementBoth(box, box);
System.out.println(box.value); // 2
~~~

This snippet assumes `Box` has an `int value` field and a constructor accepting an initial value. Although the method declares **two parameter variables**, the caller passes the same object twice. When the method modifies both `x.value` and `y.value`, both statements act on `box`. This matters when designing APIs accepting several objects and incorrectly assuming those objects are independent.

Assigning `x = new Box(...)` inside the method only changes the `x` parameter, not the caller's reference variable. *References, Values, and Passing Objects* provides complete pass-by-value and parameter-swapping examples.

## 6. Multiple References Arise Naturally in Programs

### Through a Collection

~~~java
import java.util.ArrayList;
import java.util.List;

Student student = new Student("An");
List<Student> students = new ArrayList<>();

students.add(student);          // List lưu tham chiếu đến student
Student fromList = students.get(0);

System.out.println(student == fromList); // true

fromList.setName("Hoa");
System.out.println(student.getName());   // Hoa
~~~

`List<Student>` stores elements as references to `Student` objects; it does not automatically deep-copy each object when `add` or `get` is called.

### Through Relationships Between Objects

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Employee {
    Address address;

    Employee(Address address) {
        this.address = address;
    }
}

Address shared = new Address("Hà Nội");

Employee e1 = new Employee(shared);
Employee e2 = new Employee(shared);

e1.address.city = "Đà Nẵng";
System.out.println(e2.address.city); // Đà Nẵng
~~~

In this example, the two `Employee` instances are **different objects**, but their `address` fields reference **the same Address object**. This is reference sharing through an object relationship; it does not mean every attribute of `e1` and `e2` is shared.

Diagram:

~~~mermaid
flowchart LR
    E1["Employee e1"] --> A["Address\ncity = Đà Nẵng"]
    E2["Employee e2"] --> A
~~~

In a real system, sharing `Address` may be appropriate if both employees refer to a shared address record, but it can be **a bug** if each employee needs an independent address.

## 7. Distinguishing Aliases from Copies That Contain Shared References

~~~java
List<Student> original = new ArrayList<>();
original.add(new Student("An"));

List<Student> copied = new ArrayList<>(original);
System.out.println(original == copied);             // false
System.out.println(original.get(0) == copied.get(0)); // true
~~~

`copied` is **a separate List object**, but the `Student` element is still shared; calling `copied.get(0).setName("Lan")` can make `original.get(0).getName()` return `"Lan"`. Conversely, adding elements to `copied` does not automatically change the structure of `original`.

This is why **“two different containers” does not guarantee “all contained objects are different.”** The lesson *Shallow and Deep Copies* covers shallow and deep copying, preserving shared references, and handling cyclic object graphs.

## 8. What About Sharing Immutable Objects?

An immutable object such as `String` or `LocalDate` can still have multiple aliases. The difference is that the instance's contents cannot be changed through an alias. For example, `String b = a; b = b.toUpperCase();` assigns the resulting string to `b` without modifying the string referenced by `a`.

`final Student owner = new Student("An");` also does not prevent `Student alias = owner; alias.setName("Bình");`: `final` only prevents **reassigning the `owner` variable**. To avoid side effects from multiple aliases, consider mutability and reference exposure, as discussed in *Mutable/Immutable Objects*.

## 9. When an Alias Stops Referencing an Object

~~~java
Student first = new Student("An");
Student second = first;
first = null;

System.out.println(second.getName()); // An
~~~

Assigning `first = null` removes only **one reference path**. The object remains accessible through `second`. Once no strong reference path from GC roots can reach the object, it *may* become eligible for garbage collection, but immediate collection is not guaranteed. *Null Values and Objects That Do Not Exist* distinguishes `null`, uninitialized variables, and object existence in more detail.

## 10. Practical Mistakes and How to Prevent Them

**Mistake 1 — Accidentally Changing Original Data While Experimenting:**

~~~java
Student draft = originalStudent;
draft.setName("Tên thử"); // originalStudent cũng bị thay đổi
~~~

If you need an independent object, create an appropriate copy (using a copy constructor, factory, or deliberate mapping) rather than merely assigning another reference variable.

**Mistake 2 — Exposing a Mutable Field Through a Getter:**

~~~java
class Team {
    private final List<Student> members = new ArrayList<>();

    List<Student> getMembers() {
        return members; // Caller có thể clear(), add(), remove() tự do
    }
}
~~~

Return `List.copyOf(members)` to protect the list structure from external modification. However, because `Student` elements remain mutable, callers **can still** modify each `Student`'s name through returned references. For fully read-only data, return immutable DTOs/value objects or protective copies of all necessary state.

**Mistake 3 — Confusing Reference Sharing with Concurrency Bugs:**

When several **threads** hold references to a mutable object, data races, lost updates, or inconsistent state may occur. Merely having multiple aliases **does not automatically create a race condition**; the problem arises when concurrent operations are not coordinated.

~~~java
class Counter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int getValue() {
        return value;
    }
}
~~~

Here, `synchronized` protects access to `Counter` state when threads use the same instance and all access paths obey the same synchronization mechanism. Systems spanning multiple processes or services need appropriate coordination at the data/distributed layer.

**Mistake 4 — Reassigning a Reference and Assuming a Collection Changed:**

~~~java
Student s = new Student("An");
List<Student> group = new ArrayList<>();
group.add(s);

s = new Student("Bình");

System.out.println(group.get(0).getName()); // An
System.out.println(group.get(0) == s);      // false
~~~

`group` still contains a reference to the original `Student("An")`. To replace a list element, modify the list itself, for example with `group.set(0, s)`.

## 11. Self-Assessment Questions

**Question 1:** Given `Student b = a;`, how many new `Student` objects does that statement itself create in memory?

**Answer:** None. It copies a reference value and contains no `new` expression.

**Question 2:** `a == b` is `true`. If `b.setName("Minh")` is called, does the result of `a.getName()` change?

**Answer:** Yes, provided the setter successfully changes the shared object's `name` property. Both variables reference the same instance.

**Question 3:** After `b = new Student("Khác")`, does `a` automatically refer to the new object?

**Answer:** No. Only `b` is reassigned; `a` retains its previous reference.

**Question 4:** Does `new ArrayList<>(oldList)` completely separate all the contained `Student` objects?

**Answer:** No. It creates another list but retains the same element references. Copy each mutable object if independent state is required.

**Question 5:** Does Java pass objects by reference?

**Answer:** No. Java passes **a copy of the reference value** using pass-by-value. A method can modify a shared object but cannot reassign the caller's reference variable merely by assigning to a parameter.

**Question 6:** Can two distinct instances with identical data satisfy `== true`?

**Answer:** No, if they truly are different instances. `equals()` may evaluate to `true` if the type defines content-based equality.

When reading or writing Java code, ask: **“How many objects exist? Which variables reference which objects? Is the next statement changing object state or only reassigning a reference?”** These questions explain most aliasing behavior and help prevent unintended data changes.
