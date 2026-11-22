# The Role of Constructors in Creating Valid State in Java

**A constructor** is the mechanism that enables a Java object to have its initial state established when it is created. A good constructor does not merely assign parameters to fields, but also **validates input conditions, builds consistent relationships between fields, and ensures the necessary *invariants*** before the object is provided to calling code.

For example, an account is valid only if its ID is non-empty and its initial balance is non-negative. A time period is valid only if the start time is not after the end time. The constructor is the right place to eliminate invalid state **right at the point of object creation**, rather than letting subsequent methods repeatedly guess whether fields have been sufficiently set.

This lesson applies to **Java 17+**, focusing on the role of constructors in class design, the initialization lifecycle, protecting invariants, validation, `final`, defensive copying, constructor chaining, and pitfalls that expose an incompletely initialized object.

## 1. What Is a Constructor and What Does “Valid State” Mean?

Consider a simple class:

~~~java
class Student {
    private final String studentId;
    private final int age;

    Student(String studentId, int age) {
        this.studentId = studentId;
        this.age = age;
    }
}
~~~

This is a **declaration snippet**, with no `main` method to run standalone. `Student(...)` is the constructor: its name matches the class name and it **has no return type declaration**, not even `void`.

When you write:

~~~java
Student student = new Student("SV-01", 20);
~~~

Java creates a `Student` object, executes the corresponding initialization process, and assigns **a reference to the object** to the `student` variable. A constructor **is not** a method that returns an object with a `return student` statement; rather, the `new Student(...)` expression itself evaluates to a reference to the created object.

However, the first constructor above **does not truly protect state**: it accepts `studentId == null`, an ID consisting only of whitespace, and a negative age. The object is still created using `new`, but it may be invalid according to business rules.

A **class invariant** is a condition that must be true at the points when the object is considered to be in a usable state according to its contract. For example:

- `studentId != null` and `!studentId.isBlank()`.
- `age >= 0` and `age <= 150` if this is the age range specified by the application.
- `start <= end` if the object represents a time period.
- `balance >= 0` if the account model does not allow a negative balance.
- The list of registered items does not contain `null` and cannot be silently modified by the caller through a shared reference.

**The constructor is responsible for establishing the initial invariant**; subsequent state-changing commands/methods remain responsible for **maintaining** that invariant. Nothing in Java automatically makes a business condition hold true: validation code must be written.

## 2. Initialization Phases: Do Not Confuse Default Values with Valid State

For a normal object created with `new`, instance fields begin with **type-based default values** before the relevant field initializers, instance initializers, and constructor body execute in the order specified by Java.

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` of the appropriate type |
| `float`, `double` | `0.0` of the appropriate type |
| `char` | `'\u0000'`, UTF-16 code unit U+0000 |
| `boolean` | `false` |
| Reference types, e.g., `String`, arrays, classes | `null` |

For example:

~~~java
class UserProfile {
    private String username; // defaults to null
    private int age;         // defaults to 0
}
~~~

When calling `new UserProfile()`, if the class declares no constructor, Java provides a no-argument **default constructor** in accordance with the language rules. However, an object having the field `username == null` can make it **invalid to use**.

Default values **do not equate to valid business values**:

- `0` may be an appropriate starting point for a counter.
- `0` may be an invalid quantity for an order requiring `quantity > 0`.
- `null` may be valid for an “optional profile picture” field.
- `null` may be an error for a required customer ID.

### 2.1. Declaring a Constructor Stops Automatic Generation of the Default No-Arg Constructor

~~~java
class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }
}
~~~

Because `Ticket` already declares a constructor taking a `String`, the compiler **does not** automatically generate a `Ticket()` constructor. The statement `new Ticket()` causes a compilation error unless a corresponding no-argument constructor is declared.

If you want to provide a valid default way of creating an instance, you must define it:

~~~java
class Ticket {
    private final String code;

    Ticket() {
        this("UNASSIGNED");
    }

    Ticket(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Mã vé không hợp lệ");
        }
        this.code = code;
    }
}
~~~

The two constructors are **overloads** with different parameter lists; the no-argument constructor delegates to the constructor taking a `String` using `this("UNASSIGNED")`.

**You should not add an empty `Ticket()` constructor just for “convenience”** if there is no default state that satisfies the invariant. A class representing an entity that requires a real `id` should not fabricate a fake id, unless that is an explicit business requirement.

## 3. Validating Inputs at Initialization

**Having the right data type does not mean having a valid value.** A `String` can be `null` or blank; a `long` can be negative; two individual `LocalDate` values may each be valid yet form an inverted time range. Validity conditions must be determined from the *contract of the class*, not based on whether `javac` accepts the parameter types.

Example of an account class with an ID, an owner, and an opening balance:

~~~java
import java.util.Objects;

class Account {
    private final String id;
    private final String owner;
    private long balance;

    Account(String id, String owner, long openingBalance) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(owner, "owner");
        if (id.isBlank() || owner.isBlank()) {
            throw new IllegalArgumentException("blank account info");
        }
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.id = id;
        this.owner = owner;
        this.balance = openingBalance;
    }
}
~~~

This is a **class declaration** without `main`. The checks happen before assigning state; every constructor call that **completes normally** creates an Account with a non-blank ID/owner and a non-negative balance.

### Checking Relationships Between Parameters

~~~java
import java.time.LocalDate;
import java.util.Objects;

class BookingPeriod {
    private final LocalDate start;
    private final LocalDate end;

    BookingPeriod(LocalDate start, LocalDate end) {
        this.start = Objects.requireNonNull(start, "start");
        this.end = Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end before start");
        }
    }
}
~~~

`LocalDate` is immutable. The condition `end >= start` is an **invariant of the time period**, not of either individual `LocalDate`. A constructor that fails this condition will throw rather than returning a valid instance to the caller; the assignments performed before the throw in this example do not result in exposing a successful instance to the outside.

**Learning scope:** in this lesson, validation illustrates the *role of protecting invariants*. More detailed decisions such as exception types, normalization, defensive copying, rolling back side effects, and caller error handling belong to the separate lesson **“Input Validation and Error Handling in Constructors”**. Just remember: **identify the invariant → validate the data appropriately → complete valid initialization or report a clear error**.

## 4. Setting All Required Fields, Preferring `final` Where Appropriate

An object is easier to understand and maintain if properties that **do not change after creation** are declared `final`:

~~~java
class Course {
    private final String courseCode;
    private final int credits;

    Course(String courseCode, int credits) {
        if (courseCode == null || courseCode.isBlank()) {
            throw new IllegalArgumentException("Mã học phần không hợp lệ");
        }
        if (credits < 1 || credits > 10) {
            throw new IllegalArgumentException("Số tín chỉ ngoài phạm vi");
        }

        this.courseCode = courseCode;
        this.credits = credits;
    }
}
~~~

`final` on a field:

- Requires assignment **exactly once** according to the definite assignment rules if it is a *blank final field*.
- Prevents methods from reassigning that field after object creation.
- Helps express the intent that “this instance's course code and credits are fixed”.

`final` **does not automatically validate values**. `final String code = null;` can still compile; the invariant “code is non-null” must be enforced separately.

For a reference field, `final` also **does not make the referenced object immutable**. `final List<String> names` cannot be reassigned to another list, but the list itself can be modified if it is a mutable list and some code holds a reference to it.

### 4.1. A Blank Final Field Must Be Assigned on Normally Completing Constructor Paths

~~~java
class Range {
    private final int min;
    private final int max;

    Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min lớn hơn max");
        }
        this.min = min;
        this.max = max;
    }
}
~~~

A constructor that throws an exception before assignment **does not complete normally**, so no successfully initialized `Range` object exists with an unassigned final field. If the constructor completes, both required fields already have values.

An `if` branch that assigns only `min` and lets the constructor complete without assigning `max` will cause a definite assignment error if `max` is a blank final field. Compiler errors help catch some initialization paths with missing data, but **cannot replace business checks** such as `min <= max`.

## 5. Avoid Partial Updates Before Validation Completes

When a constructor creates multiple components, validation and computations that can fail should be performed **before publishing the object**. For an ordinary class, if the constructor throws an exception, the `new` expression does not return a completed reference to the caller; however, updating external objects or exposing `this` can still have consequences.

Example of a design with dangerous side effects:

~~~java
import java.util.List;

class BadRegistration {
    BadRegistration(List<String> externalLog, String username) {
        externalLog.add("starting"); // Already modified the caller's state
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username không hợp lệ");
        }
    }
}
~~~

This is an illustrative snippet. If `username` is invalid, the constructor throws an exception, yet `externalLog` has already been modified. **You cannot conclude that “when a constructor fails, all side effects automatically roll back”**.

A more predictable design:

~~~java
import java.util.List;

class Registration {
    private final String username;

    Registration(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username không hợp lệ");
        }
        this.username = username;
    }
}
~~~

If you genuinely must call an external resource or persist data at creation time, design transactions, cleanup, rollback, and ownership responsibilities separately. A constructor does not automatically create a database transaction or automatically undo I/O operations.

### 5.1. Precompute New Values That Could Overflow

~~~java
class AmountSummary {
    private final long total;

    AmountSummary(long subtotal, long tax) {
        if (subtotal < 0 || tax < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }
        long checkedTotal = Math.addExact(subtotal, tax);
        this.total = checkedTotal;
    }
}
~~~

`Math.addExact` throws `ArithmeticException` if `long` overflows. By performing the calculation before assigning the `total` field, the constructor completes successfully only when the sum is representable in a `long`. This is an essential example showing **valid state is not merely each individual argument being valid**.

## 6. Defensive Copy: Preventing the Caller from Modifying Data After the Constructor Finishes

A common mistake is when a constructor validates mutable input yet still keeps the **original reference** owned by the caller. After the object is created, the caller modifies the input data and breaks the invariant.

**Unsafe example:**

~~~java
import java.util.List;

class UnsafeEnrollment {
    private final List<String> courseCodes;

    UnsafeEnrollment(List<String> codes) {
        if (codes == null || codes.isEmpty()) {
            throw new IllegalArgumentException("Phải chọn ít nhất một môn");
        }
        this.courseCodes = codes; // Retains the mutable list held by the caller
    }
}
~~~

The caller can write:

~~~java
List<String> chosen = new java.util.ArrayList<>();
chosen.add("JAVA");
UnsafeEnrollment enrollment = new UnsafeEnrollment(chosen);
chosen.clear(); // the internal object may lose the validated data
~~~

This is a fragment inside a method and does not run standalone. `final` only prevents reassigning the `courseCodes` field; **it does not prevent `chosen.clear()` from modifying the shared list object**.

### 6.1. Taking an Immutable Snapshot When the Data Is a Collection of Immutable Elements

~~~java
import java.util.List;

class Enrollment {
    private final List<String> courseCodes;

    Enrollment(List<String> codes) {
        if (codes == null || codes.isEmpty()) {
            throw new IllegalArgumentException("Phải chọn ít nhất một môn");
        }

        List<String> snapshot = List.copyOf(codes);

        for (String code : snapshot) {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Mã môn không hợp lệ");
            }
        }

        this.courseCodes = snapshot;
    }

    List<String> getCourseCodes() {
        return courseCodes;
    }
}
~~~

`List.copyOf` (Java 10+) creates a list that **cannot be modified through list-mutating methods**, does not allow `null` elements, and protects against subsequent structural changes on a mutable source such as `ArrayList`. Here the elements are immutable `String` values, so returning that list through a getter does not allow the caller to modify element contents.

Notes:

- `List.copyOf(codes)` throws `NullPointerException` if `codes` contains a null element. If the contract wants to turn that case into an `IllegalArgumentException` with a custom message, check beforehand or catch/handle it intentionally.
- `List.copyOf` is a **shallow copy with respect to elements**: for `List<MutableItem>`, the copy still contains references to the `MutableItem` objects. If the elements are mutable, each element must be copied/frozen as required.
- You should not access the same mutable `codes` multiple times to both validate and copy if another thread could modify it concurrently. In a concurrent environment, there must be a contract that the caller does not modify the list during construction, or an appropriate synchronization/consistent-snapshot mechanism.
- Do not use `Collections.unmodifiableList(codes)` and assume it is a snapshot. It is only a **view that disallows modification through the view**; changes in the `codes` source may still be observed.

### 6.2. For Arrays, Clone the Input Data When Independent Ownership Is Needed

~~~java
class ExamResult {
    private final int[] marks;

    ExamResult(int[] marks) {
        if (marks == null || marks.length == 0) {
            throw new IllegalArgumentException("Thiếu điểm");
        }

        int[] copy = marks.clone();
        for (int mark : copy) {
            if (mark < 0 || mark > 100) {
                throw new IllegalArgumentException("Điểm ngoài [0,100]");
            }
        }
        this.marks = copy;
    }

    int[] getMarks() {
        return marks.clone();
    }
}
~~~

This is a declaration snippet. Each `int` element is a primitive, so the array's `clone()` creates an independent copy of the mark values. Copying on **input** protects against modifying the source after the constructor; copying on **output** protects against the caller modifying the internal array via the getter. If the array contains mutable objects, `clone()` only copies element references, and deep copying still needs to be considered.

## 7. Complete Example: A Constructor Creating an Always-Valid Object

The following program combines **validation**, **`final` fields**, **defensive copying**, and **constructor overloading/chaining**, and proves that mutating the source data after creation **does not break the object's state**.

Save as **`ValidConstructionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidConstructionDemo {
    static final class Enrollment {
        private final String studentId;
        private final List<String> courseCodes;
        private final int maximumCourses;

        Enrollment(String studentId, List<String> courseCodes) {
            this(studentId, courseCodes, 4);
        }

        Enrollment(String studentId,
                   List<String> courseCodes,
                   int maximumCourses) {
            if (studentId == null || studentId.isBlank()) {
                throw new IllegalArgumentException("Mã sinh viên không hợp lệ");
            }
            if (maximumCourses < 1) {
                throw new IllegalArgumentException("Giới hạn phải dương");
            }
            if (courseCodes == null) {
                throw new IllegalArgumentException("Danh sách môn bị null");
            }

            List<String> copy = List.copyOf(courseCodes);

            if (copy.isEmpty() || copy.size() > maximumCourses) {
                throw new IllegalArgumentException(
                        "Số môn không hợp lệ");
            }
            for (String code : copy) {
                if (code.isBlank()) {
                    throw new IllegalArgumentException(
                            "Mã môn không hợp lệ");
                }
            }
            if (copy.stream().distinct().count() != copy.size()) {
                throw new IllegalArgumentException(
                        "Trùng mã môn");
            }

            this.studentId = studentId;
            this.courseCodes = copy;
            this.maximumCourses = maximumCourses;
        }

        String studentId() {
            return studentId;
        }

        List<String> courseCodes() {
            return courseCodes;
        }

        int capacityLeft() {
            return maximumCourses - courseCodes.size();
        }
    }

    public static void main(String[] args) {
        List<String> chosen = new ArrayList<>(
                List.of("JAVA", "SQL"));

        Enrollment registration = new Enrollment("SV-17", chosen);

        chosen.clear();
        chosen.add("PYTHON");

        System.out.println("Student = " + registration.studentId());
        System.out.println("Courses = " + registration.courseCodes());
        System.out.println("Capacity left = " + registration.capacityLeft());

        try {
            new Enrollment("SV-18", List.of("JAVA", "JAVA"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            registration.courseCodes().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot edit courses");
        }

        System.out.println("Still valid = "
                + registration.courseCodes());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ValidConstructionDemo.java
java ValidConstructionDemo
~~~

**Exact stdout:**

~~~text
Student = SV-17
Courses = [JAVA, SQL]
Capacity left = 2
Rejected = Trùng mã môn
Cannot edit courses
Still valid = [JAVA, SQL]
~~~

Explanation:

1. The two-parameter constructor calls `this(studentId, courseCodes, 4)`, which helps **centralize all validation in one primary constructor**. The default limit is 4 courses.
2. The primary constructor checks id, capacity, and `courseCodes`; creates `List.copyOf`; checks the count, blank course codes, and duplicate codes before assigning the three `final` fields.
3. After creating `registration`, the caller calls `chosen.clear()` and adds `"PYTHON"` to the initial list. Because the constructor kept a snapshot, `registration.courseCodes()` is still `[JAVA, SQL]`.
4. `capacityLeft()` returns `4 - 2 = 2`.
5. Creating `Enrollment("SV-18", List.of("JAVA", "JAVA"))` violates the “no duplicate course codes” invariant, so the constructor throws `IllegalArgumentException` with the message `"Trùng mã môn"`; no completed instance is returned to the caller.
6. Calling `clear()` on the returned list fails with `UnsupportedOperationException` because the internally held list is unmodifiable; the object still keeps valid state.

**Limitation of this illustration:** this is an example for a collection of immutable `String` elements. For a collection of mutable `Course` objects, `List.copyOf` alone is not enough to prevent modifying individual element objects. If invariants involve the contents of child objects, deep immutability modeling or appropriate ownership control is needed.

## 8. Constructor Chaining: Do Not Repeat Validation Across Multiple Creation Paths

A class can have multiple constructors (constructor overloading), each providing a way to initialize. To avoid creation paths that lead to inconsistent state, you should **delegate to a central constructor**:

~~~java
class Coordinate {
    private final int x;
    private final int y;

    Coordinate() {
        this(0, 0);
    }

    Coordinate(int position) {
        this(position, position);
    }

    Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

This is a class declaration snippet. The first two constructors call the two-parameter constructor using `this(...)`, so the state-setup logic is not duplicated in three places.

### 8.1. Rules for `this(...)` and `super(...)` in Java 17

- `this(...)` calls **another constructor in the same class**.
- `super(...)` calls **a constructor of the superclass**.
- In Java 17, an explicit `this(...)` or `super(...)` constructor call must be **at the start of the constructor body**, and a constructor cannot use both explicit calls as two consecutive steps.
- If there is no matching explicit call, the constructor has an implicit `super()` call according to Java's rules. If the superclass has no accessible no-argument constructor, the subclass must specify a callable superclass constructor.
- A `this(...)` call chain must not form a recursive constructor cycle.

The goal of constructor chaining is to unify valid initialization paths, **not merely to reduce lines of code**. A convenience constructor should not bypass the mandatory checks performed by the primary constructor.

### 8.2. Superclass Constructors Also Participate in Creating Valid State

~~~java
class Document {
    private final String id;

    Document(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        this.id = id;
    }
}

class Invoice extends Document {
    private final long amount;

    Invoice(String id, long amount) {
        super(id);
        if (amount < 0) {
            throw new IllegalArgumentException("amount âm");
        }
        this.amount = amount;
    }
}
~~~

This is a declaration snippet; there is no `main`. The `Invoice` constructor calls `super(id)` so that the superclass establishes the invariant of `Document` before establishing the additional invariant of `Invoice`. If the superclass rejects `id`, the subclass constructor does not complete.

In OOP practice, calling a method that can be overridden inside a superclass constructor is **dangerous**: dynamic dispatch can run the subclass's implementation while the subclass's fields are still at their default values. To keep state consistent, you should avoid calling overridable instance methods from constructors, especially if the implementation needs uninitialized fields.

## 9. Differences Among Field Initializers, Instance Initializers, and the Constructor Body

Java supports several places to put initialization logic:

~~~java
class Settings {
    private int retries = 3;

    {
        retries += 1;
    }

    Settings(int retries) {
        if (retries < 0) {
            throw new IllegalArgumentException("retries âm");
        }
        this.retries = retries;
    }
}
~~~

In this class:

1. The instance field has the default value `0` when the object's memory is initialized.
2. The field initializer sets `retries = 3` when it is this class's turn to initialize.
3. The instance initializer block executes in its corresponding textual order, increasing `retries` to `4`.
4. The constructor body continues and assigns `this.retries` from the validated parameter.

If `new Settings(7)` is called, the final value of `retries` is 7. **You should not scatter initialization logic across many places if doing so makes invariants harder to reason about**. A central constructor is usually easier to read, unless an initializer helps declare a very clear shared default.

### 9.1. Constructors Do Not Automatically Re-Execute When Fields Change

After an object is created, calling a setter or command does not rerun the constructor. Therefore, an invariant established by the constructor must be **continuously maintained** through state-modifying methods:

~~~java
class ProductStock {
    private int quantity;

    ProductStock(int quantity) {
        requireNonNegative(quantity);
        this.quantity = quantity;
    }

    void replenish(int added) {
        if (added <= 0) {
            throw new IllegalArgumentException("added phải dương");
        }
        quantity = Math.addExact(quantity, added);
    }

    int quantity() {
        return quantity;
    }

    private static void requireNonNegative(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
    }
}
~~~

This is a declaration snippet. If a setter `setQuantity(-99)` without validation is allowed, the object can still enter an invalid state after the constructor succeeds. **An invariant is a lifecycle-wide contract**, not just a check at the moment of `new`.

## 10. Do Not Let `this` Escape While the Constructor Has Not Yet Finished

A subtle risk is **this escape**: the constructor publishes a reference to the object being created to other code before completing initialization. Outside code can then observe fields that have not yet been set.

Example of a design to avoid:

~~~java
import java.util.List;

class EventListener {
    private final String label;

    EventListener(List<EventListener> registry) {
        registry.add(this);  // Exposes reference too early
        this.label = "ready";
    }
}
~~~

Here `registry` is a collection owned by the caller. The constructor puts `this` into the list **before assigning `label`**, enabling a callback, an observer, or another thread to see an instance currently under construction. If the constructor fails afterward, the registry may also retain a reference to an incomplete object.

A safer design is to construct the object completely first and register it afterward:

~~~java
import java.util.List;

class EventListener {
    private final String label;

    EventListener(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label không hợp lệ");
        }
        this.label = label;
    }

    static EventListener createAndRegister(
            String label, List<EventListener> registry) {
        EventListener ready = new EventListener(label);
        registry.add(ready);
        return ready;
    }
}
~~~

This is a declaration snippet. The factory creates an object whose constructor has already finished before adding it to the registry. You also need to control the condition `registry != null` and the thread safety of the registry according to the actual contract. If registration is a multi-step transaction, you still must define a rollback strategy when the registry throws an exception.

Other forms of *this escape* to guard against:

- Passing `this` to an external API that might store the reference or invoke a callback immediately.
- Registering a listener in a constructor when the listener may be triggered before initialization finishes.
- Creating/starting a thread in a constructor and letting the task use `this`.
- Calling an overridable method from a constructor; the subclass implementation may observe uninitialized subclass fields.

**Just because a field has `final` does not mean every way of publishing the object is safe**. The special guarantees for final fields in the Java Memory Model depend on the object being properly constructed, including not letting a reference to the object escape while it is under construction. If a mutable object is shared across threads, proper safe publication and synchronization mechanisms are still needed.

## 11. Inheritance and Initialization Order: Avoid Relying on Subclasses Too Early

Consider the following illustrative snippet:

~~~java
class Parent {
    Parent() {
        describe();
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String value = "ready";

    @Override
    void describe() {
        System.out.println(value);
    }
}
~~~

If a program creates `new Child()`, `Parent`'s constructor can call the `Child.describe()` implementation due to dynamic dispatch. At that point, however, `Child`'s field initializer `value = "ready"` **has not run yet**, so `value` is still at its default `null`. This is not a safe way for a superclass to validate subclass state.

What you should do:

- Have the superclass constructor set up and check only **the part of state owned by the superclass**.
- Avoid calling overridable methods inside constructors; prefer private, static, or final methods when you need a helper that does not depend on subclasses.
- Have the subclass invoke a valid `super(...)`, and then set up and check its own state.
- If an operation requires a fully constructed object, perform it after the constructor finishes in a factory or an initialization method with a clear contract.

An invariant shared between a superclass and a subclass may require a safer API design rather than trying to call an overridden method to “validate once for all”.

## 12. Records and Compact Constructors in Java 17

A **record** is an appropriate choice for declaring a value-carrying data type with clearly defined components. Records do not make validation appear automatically, but they allow a **compact constructor** for concise invariant checking:

~~~java
import java.util.Objects;

record DateRange(String start, String end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (start.compareTo(end) > 0) {
            throw new IllegalArgumentException("start sau end");
        }
    }
}
~~~

This is a record declaration snippet, with no `main`. Comparing ISO date strings will be accurate in order only when the data has the corresponding standard format, whereas real applications should use `LocalDate` instead of free-form date strings.

A more idiomatic example:

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end trước start");
        }
    }
}
~~~

With a compact constructor, Java performs the assignment of record components to their corresponding fields **after the compact constructor body** according to the language rules. Therefore, inside this block, validate/adjust parameters if genuinely necessary; do not attempt to assign the component fields directly as in a normal constructor.

A record provides final component fields and accessors, but **does not guarantee deep immutability** for mutable reference components. For example, a record containing a `List<String>` should still use `List.copyOf` if a snapshot is needed and list modification must be disallowed.

## 13. Constructor Failure: Is Any Object Left Usable?

Suppose:

~~~java
class PositiveQuantity {
    private final int quantity;

    PositiveQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        this.quantity = quantity;
    }
}
~~~

When the caller executes `new PositiveQuantity(-1)`, the exception causes the object creation expression to fail; the caller **does not receive a normal return reference** from that `new` expression.

However, distinguish the effects:

- **No successful initialization result**: true for a `new` call that throws an exception.
- **No side effects have occurred**: not guaranteed. The constructor may still have written logs, modified an external collection, opened a resource, called a service, or exposed `this` before throwing.
- **Fields assigned before throwing are rolled back**: Java does not apply automatic transactions to fields or external resources.
- **The garbage collector automatically handles all non-memory resources**: incorrect; resources such as file handles, sockets, and transactions require proper cleanup, typically via `try`/`finally` or `try-with-resources` at the point of ownership.

### 13.1. Consider a Static Factory If Creation Requires Multiple Steps

Constructors suit synchronous, straightforward logic: validating inputs and assigning state. If construction requires I/O, database lookups, opening resources, complex configuration, or performing rollbackable actions, a **static factory** or an object-creation service is often easier to organize:

~~~java
class ApiClient {
    private final String endpoint;

    private ApiClient(String endpoint) {
        this.endpoint = endpoint;
    }

    static ApiClient fromEndpoint(String endpoint) {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("endpoint không hợp lệ");
        }
        return new ApiClient(endpoint);
    }
}
~~~

This is an illustrative declaration snippet; here the static factory only validates and calls the private constructor, with no I/O yet. It allows naming the creation path (`fromEndpoint`), coordinating validation, or choosing an implementation when needed. **A factory does not replace invariants**: the constructor/factory must still guarantee that every published object is valid.

Consider designing the class so that callers do not have a public `new` path bypassing validation if the class genuinely needs a centralized creation process.

## 14. Constructors and Controlling Object Instantiation

A constructor's access level defines where it is permitted to be called:

| Declaration | Typical meaning |
| --- | --- |
| `public ClassName(...)` | Can be created from anywhere the class/constructor is accessible |
| `protected ClassName(...)` | Intended for inheritance models and access under protected rules |
| `ClassName(...)` without modifier | Callable only within package-private scope |
| `private ClassName(...)` | Controls creation within valid class/nested contexts; often paired with a static factory |

A class can have a `private` constructor and `public static` factories to ensure that callers always go through a controlled validation process. Conversely, exposing all constructor overloads publicly while each overload validates differently can easily create **multiple paths to inconsistent state**.

There is no return type in a constructor. For example:

~~~java
class Device {
    Device() { }       // constructor

    void Device(int n) { } // this is a method named Device, NOT a constructor
}
~~~

This is a syntactically valid class declaration, but the method `void Device(int n)` is usually a design mistake written accidentally by learners. A true constructor requires **the class name** and **no return type**; distinguishing these is important when debugging fields that are “not initialized as expected”.

## 15. When Constructors Are Not the Only Path to Creating or Restoring Objects

A class can be created or restored through mechanisms other than ordinary `new` calls. For example, Java Object Serialization has its own rules: when deserializing an ordinary `Serializable` class, the constructors and instance initializers **of that Serializable class itself** do not execute as they would when instantiated with `new`; instead, the no-argument constructor of the nearest non-Serializable superclass is executed according to the serialization rules.

Therefore, if a class has important invariants and participates in serialization, you must design ways to protect those invariants during restoration:

- Validate the restored data in appropriate logic (for example, `readObject`) or use the serialization proxy pattern when suitable.
- Do not assume that constructors always run for every deserialized object.
- Consider the security risks of native Java deserialization from untrusted sources; do not indiscriminately use `ObjectInputStream` on arbitrary byte streams.
- Persistence/ORM frameworks, reflection, or other object-mapping mechanisms may have their own object-creation rules that require following the framework's contract. Do not expose a public constructor that creates invalid state for all callers just to satisfy a framework if a safer configuration option exists.

This is a **limitation of invariants that rely solely on constructors**. In ordinary Java code created with `new`, constructor validation is the first line of defense; with custom restoration/mapping mechanisms, additional entry paths must also be protected.

## 16. Constructors, Immutability, and Thread Safety

A class whose fields are all `private final`, that uses immutable types, and that defensively handles mutable inputs can significantly reduce the number of states to track:

~~~java
import java.util.List;

class CoursePlan {
    private final String name;
    private final List<String> codes;

    CoursePlan(String name, List<String> codes) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name trống");
        }
        this.codes = List.copyOf(codes);
        if (this.codes.isEmpty()) {
            throw new IllegalArgumentException("codes rỗng");
        }
        this.name = name;
    }

    String name() {
        return name;
    }

    List<String> codes() {
        return codes;
    }
}
~~~

This is an illustrative snippet. With String/list-of-String, once the constructor succeeds, the object has no state-mutating methods and does not expose its mutable collection. Such a design is very favorable for data sharing.

However:

- **`final` does not by itself guarantee concurrent safety for a mutable object it points to.**
- If the constructor exposes `this` too early, the guarantees of final fields and safe initialization can be broken.
- If an object has mutable fields or involves data that changes across threads, appropriate synchronization/safe publication mechanisms are needed.
- If an object is constructed from input that is concurrently modified by another thread without a synchronization contract, the constructor does not automatically guarantee an atomic snapshot.

**Establishing valid initial state** and **maintaining correctness when used by multiple threads** are two related yet non-identical responsibilities.

## 17. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to address |
| --- | --- | --- |
| Constructor only assigns fields without validating | Object ends up with `null`, negative numbers, or conflicting field relationships | Define invariants and check them before assigning |
| Giving every class a no-argument constructor even when no valid default exists | Callers create objects not ready for use | Allow only creation paths that produce valid state |
| Assuming a field with a default value is valid | `int = 0` or reference = `null` may violate business rules | Distinguish Java defaults from data domain constraints |
| Using `final` instead of validation | A final field can still receive a meaningless value | Both validate and assign `final` |
| Retaining a reference to mutable input | Caller modifies input after the constructor, breaking invariants | Defensive copy or transfer ownership under a clear contract |
| Returning the object's mutable array/list directly | Caller mutates internal state outside commands | Have getters return an appropriate snapshot/read-only data |
| Shallow-copying and assuming element objects are immutable | Mutable elements remain shared | Consider deep copying or immutable value objects |
| Two constructor overloads having different validation rules | One creation path is valid while another lets bad data through | Use `this(...)` targeting a central constructor |
| Calling an overridable method from a constructor | Subclass method may see uninitialized fields | Avoid virtual dispatch inside constructors |
| Registering `this` into a listener/registry before completion | Incomplete object is observed by other code | Register after construction, typically via a factory |
| Constructor throws an error after modifying external resources | Side effects remain even though `new` failed | Validate first, with explicit cleanup/transaction handling |
| Constructor overload with too many parameters of the same type | Callers easily swap argument positions | Use value objects, named builders/factories, and validation |
| Public setter breaks invariants after construction | Object is initially valid but becomes invalid later | Commands must maintain invariants |
| Relying on constructors to protect deserialization as well | Some restoration mechanisms do not run constructors like `new` | Also protect data restoration/mapping paths |

### 17.1. An Easy-to-Make Mistake: Validating and Still Retaining the Original List

~~~java
class UnsafeSet {
    private final java.util.List<String> names;

    UnsafeSet(java.util.List<String> names) {
        if (names == null || names.isEmpty()) {
            throw new IllegalArgumentException();
        }
        this.names = names; // the "non-empty" invariant is not protected long-term
    }
}
~~~

This is an illustrative snippet. Even though the constructor validated the input, the caller later calls `names.clear()`, causing the internal field to point to an empty list. **Validation truly retains its effect only when ownership and mutability are designed alongside it**.

## 18. Self-Check Exercises

**Question 1.** Why does `new Student(null, -5)` compile even though it is invalid according to business rules?

**Answer:** The compiler only checks that the arguments have compatible types (null is a reference value and `-5` is an `int`). Rules such as “student ID is non-null” or “age is non-negative” are invariants that the constructor must check at runtime.

**Question 2.** Is `private final List<String> items` enough to guarantee that the caller cannot delete elements?

**Answer:** No. `final` prevents reassigning the reference field, but does not prevent modifying a mutable list. You can take a snapshot with `List.copyOf` if the contract does not allow the caller to modify the list, while also ensuring the elements are valid.

**Question 3.** A class declares `Order(String id)` without declaring `Order()`. Will `new Order()` automatically use a default constructor?

**Answer:** No. Once a class has declared at least one constructor, the compiler does not automatically add a default no-arg constructor. If you want one, it must be declared explicitly.

**Question 4.** A constructor throws `IllegalArgumentException` after adding `this` to a global list. Is it certain that the list will not contain that object?

**Answer:** No. An exception does not automatically roll back side effects; this is an error that leaks an incomplete object (*this escape*). Avoid registering the object before the constructor finishes.

**Question 5.** Why is `this(...)` often useful when a class has multiple constructor overloads?

**Answer:** It centralizes validation and state-setup logic into one central initialization path, reducing the chance that an overload misses an invariant.

**Question 6.** A superclass constructor calls an overridable method. A subclass overrides that method and reads a subclass field. What is the risk?

**Answer:** Dynamic dispatch may call the subclass method **before the subclass's field initializers/constructor body run**, so the method sees default values such as `null` or `0`. You should avoid calling overridable methods in constructors.

**Question 7.** If a constructor finishes, is the object automatically thread-safe?

**Answer:** No. A constructor sets up initial state; correctness when shared by multiple threads depends on mutability, safe publication, synchronization, and the subsequent access protocol.

**Question 8.** Does `record Range(int min, int max)` automatically reject `min > max`?

**Answer:** No. A record automatically generates members according to Java's rules, but business invariants must be checked by a compact constructor or another valid constructor.

**Question 9.** Does `List.copyOf(list)` always create a deep copy of all element objects?

**Answer:** No. It protects the list structure through an unmodifiable result, but mutable element objects can still be shared. Separate handling is needed if invariants depend on element state.

**Question 10.** An instance field `int quantity` defaults to 0. Does that mean `quantity = 0` is always valid?

**Answer:** No. If business rules require an order to contain at least one unit, the constructor must reject 0 or provide a default initialization that satisfies that condition.

## 19. Checklist for Designing Constructors That Create Valid State

When writing a new constructor, check in order:

1. **Define invariants:** what properties must the object always have after successful creation?
2. **Validate each parameter:** null, blank, value range, format, length, and other conditions.
3. **Validate parameter relationships:** `start <= end`, non-overflowing sum, element count within limits, no duplicates as required.
4. **Decide `final` fields:** which values should not be reassigned after initialization?
5. **Evaluate mutable inputs:** keep a reference, shallow copy, deep copy, or transfer ownership with a clear contract?
6. **Set only validated state:** prefer computing/snapshotting before assigning or producing irreversible side effects.
7. **Unify constructor overloads:** use `this(...)` and `super(...)` according to the rules; avoid paths that bypass validation.
8. **Do not publish `this` too early:** prevent callbacks, registries, or threads from using an incomplete instance.
9. **Ensure exception behavior:** a failed constructor does not leave behind forgotten resources or external effects.
10. **Protect the entire lifecycle:** every subsequent state-changing method must maintain invariants, not only the constructor.
11. **Consider other restoration paths:** serialization, ORM, or framework mapping if the application uses them.
12. **Write tests:** valid constructor calls produce usable objects; invalid inputs are rejected; modifying mutable sources after creation does not break invariants.

**Conclusion:** a good constructor is **the gatekeeper of a class's state**. It does not merely “fill data into fields”, but clarifies right at object creation: *which inputs are accepted, which field relationships must hold, which data is independently owned, and from what point the object can be safely published*. When constructor validation is combined with encapsulation and invariant-maintaining commands, the class becomes easy to use correctly and difficult to fall into an invalid state.
