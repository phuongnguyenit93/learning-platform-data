# One-to-one and one-to-many relationships using reference fields in Java

In object-oriented programs, an object often **knows** or **contains** other objects. For example, a `User` has a `Profile`, a `Department` has many `Employee` objects, and an `Order` contains many `OrderLine` objects. Java represents those associations using **reference fields** or a **collection containing references**.

~~~java
class User {
    Profile profile;                     // One reference.
}

class Department {
    java.util.List<Employee> employees; // One reference to a List containing many references.
}
~~~

These are illustrative declarations, not yet sufficient to create a valid relationship. Java **does not have `one-to-one` or `one-to-many` keywords**; uniqueness, minimum/maximum count, permission to replace links, and bidirectional consistency are **business constraints that code must enforce**.

This lesson belongs to Java Core — **Class & Object / Class Relationships**, using Java 17+. Complete programs include a filename, `javac`/`java` commands, and stdout; standalone code snippets are explicitly marked as illustrative.

## 1. Learning objectives

After this lesson, you need to:

1. Understand reference types, object identity, and reference fields.
2. Distinguish **one-to-one** from **one-to-many** by navigation direction and cardinality.
3. Understand `0..1`, `1`, `0..*`, `1..*` notation and maximum limits.
4. Write unidirectional and bidirectional links using fields, constructors, and methods.
5. Know that a single field **does not automatically guarantee system-wide one-to-one uniqueness**.
6. Use `List`, `Set`, and `Map` appropriately when associating multiple objects.
7. Manage reverse links and transfer objects between two owners.
8. Know why `private final List` is not enough to hide mutable state.
9. Distinguish `==` from `equals/hashCode` in duplicate checking.
10. Recognize association, aggregation, and composition, and avoid confusing them with `extends`.
11. Choose null/`Optional` and constructor validation properly when links are optional or required.
12. Avoid recursion across bidirectional relationships, memory retention, race conditions, and state-dependent tests.
13. Design meaningful APIs, protect relationship constraints, and test failure paths.

## 2. Reference fields and object graphs

An object-type field holds a **reference value** or `null`; it does not contain a complete copy of the target object:

~~~java
class Address {
    String city;
}
class Customer {
    Address address;
}
~~~

If we execute:

~~~java
Address a = new Address();   // Address #1.
Customer c = new Customer(); // Customer #1.
c.address = a;
a.city = "Hue";
~~~

we have:

~~~text
c ----> Customer #1
             |
             | address
             v
          Address #1 <---- a
          city="Hue"
~~~

`c.address` and `a` reference the same Address object. When `a.city` changes, `c.address.city` also observes the same state. The assignment `c.address = a` **does not create a second Address**.

The arrow diagram is only a logical model; the #1 label is not a machine address that Java allows you to manipulate directly.

### A field does not automatically create an object

~~~java
class Customer {
    Address address;
}
~~~

If a constructor/initializer has not assigned it, the reference field `address` defaults to `null`. Reading `customer.address.city` when address is null throws `NullPointerException`. You must use a constructor, factory, or method to assign a valid reference.

## 3. Cardinality must be described on both sides

| UML Notation | Meaning | Example |
| --- | --- | --- |
| `0..1` | May have zero or one | An account may not have a profile picture yet |
| `1` | Exactly one required | An Invoice must have a Customer |
| `0..*` | Zero or more | A Team may not have any Members yet |
| `1..*` | At least one | A finalized Order must have at least one Line |
| `0..5` | From zero to at most five | A group can accept at most 5 members |

A relationship has **two ends**. For example:

~~~text
Department 1 -------- 0..* Employee
Employee   0..1 ----- 1 Department
~~~

Model meaning: a Department can manage many Employees; an Employee may belong to no Department or to one Department. An employee **must not** belong to two departments simultaneously if the contract only allows `0..1`.

### What Java does not enforce automatically

- `Profile profile;` does not guarantee that a Profile is not held by two Users.
- `List<Employee> employees;` does not automatically prevent duplicates.
- `final` does not force a relation to exist or be unique.
- Bidirectional relationships do not synchronize fields automatically.
- Core Java has no “foreign key” that automatically guarantees consistency between objects; databases/ORMs have their own mechanisms.

Write the **invariant** before deciding how to store the reference.

## 4. Unidirectional one-to-one

A **unidirectional** association only allows navigation from A to B:

~~~text
User --------> Profile
~~~

If Profile does not need to know about User, this is a simple design. When Profile is required to exist and must not be replaced after creation, a `private final Profile` with constructor validation is very clear.

Create **`UnidirectionalOneToOneDemo.java`**:

~~~java
import java.util.Objects;

public class UnidirectionalOneToOneDemo {
    record Profile(String name, String language) {
        Profile {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            if (language == null || language.isBlank()) {
                throw new IllegalArgumentException("language required");
            }
        }
    }

    static final class User {
        private final String id;
        private final Profile profile;

        User(String id, Profile profile) {
            this.id = Objects.requireNonNull(id, "id");
            this.profile = Objects.requireNonNull(profile, "profile");
        }

        String description() {
            return id + ": " + profile.name()
                    + " (" + profile.language() + ")";
        }

        Profile profile() {
            return profile;
        }
    }

    public static void main(String[] args) {
        Profile p = new Profile("Mai", "vi");
        User u = new User("U1", p);
        System.out.println(u.description());
        System.out.println("same=" + (u.profile() == p));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnidirectionalOneToOneDemo.java
java UnidirectionalOneToOneDemo
~~~

Stdout:

~~~text
U1: Mai (vi)
same=true
~~~

**Explanation:** `User` holds a reference to the same Profile that the caller created. `Profile` only has String components, so it has immutable state under the usual contract. The `final` field cannot be reassigned in User after the constructor.

**Limitation:** If you create `new User("U2", p)`, Java still accepts it and two Users both point to Profile p. This is **one reference per User**, not yet **strict one-to-one uniqueness on both sides**.

## 5. Optional one-to-one: `0..1`

For an optional link, the field can be null:

~~~java
class Account {
    private Contact contact;

    java.util.Optional<Contact> contact() {
        return java.util.Optional.ofNullable(contact);
    }
}
~~~

This is an illustrative snippet with class `Contact` needing to be defined. `Optional` in the **return type** clearly expresses the possibility of no link; it does not force the caller to guess about null.

Create **`OptionalRelationDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class OptionalRelationDemo {
    record Contact(String phone) {}

    static final class Account {
        private Contact contact;

        void attach(Contact value) {
            contact = Objects.requireNonNull(value);
        }

        void detach() {
            contact = null;
        }

        Optional<Contact> contact() {
            return Optional.ofNullable(contact);
        }
    }

    public static void main(String[] args) {
        Account a = new Account();
        System.out.println("before=" +
                a.contact().map(Contact::phone).orElse("none"));

        a.attach(new Contact("0123"));
        System.out.println("after=" +
                a.contact().map(Contact::phone).orElse("none"));

        a.detach();
        System.out.println("removed=" + a.contact().isEmpty());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OptionalRelationDemo.java
java OptionalRelationDemo
~~~

Stdout:

~~~text
before=none
after=0123
removed=true
~~~

For a **required `1`**, it is better to use a non-null constructor and no detach method if the invariant must always hold. For **`0..1`**, null can be a valid state, but it should have clear semantics and a clear API.

## 6. Bidirectional one-to-one and integrity

If both Person and Passport need to navigate to each other:

~~~text
Person #1 ----passport----> Passport #1
   ^                            |
   |----------holder------------+
~~~

Invariant:

~~~text
person.passport == passport
passport.holder == person
~~~

If you only execute `person.passport = passport`, Java does not automatically assign `passport.holder`. If a second Person links to the same Passport without checking, uniqueness is broken. Therefore, **one operation must manage both sides**.

### Runnable example: object-level exclusivity

Create **`BidirectionalOneToOneDemo.java`**:

~~~java
import java.util.Objects;

public class BidirectionalOneToOneDemo {
    static final class Passport {
        private final String number;
        private Person holder;

        Passport(String number) {
            this.number = Objects.requireNonNull(number);
        }

        void claim(Person person) {
            Objects.requireNonNull(person);
            if (holder != null && holder != person) {
                throw new IllegalStateException("already assigned");
            }
            holder = person;
        }

        String holderName() {
            return holder == null ? "none" : holder.name();
        }

        String number() {
            return number;
        }
    }

    static final class Person {
        private final String name;
        private Passport passport;

        Person(String name) {
            this.name = Objects.requireNonNull(name);
        }

        void attach(Passport target) {
            Objects.requireNonNull(target);
            if (passport != null) {
                throw new IllegalStateException("person already linked");
            }
            target.claim(this);
            passport = target;
        }

        String name() {
            return name;
        }

        String passportNumber() {
            return passport == null ? "none" : passport.number();
        }
    }

    public static void main(String[] args) {
        Person mai = new Person("Mai");
        Person an = new Person("An");
        Passport p = new Passport("P01");

        mai.attach(p);
        System.out.println("Mai=" + mai.passportNumber());
        System.out.println("holder=" + p.holderName());

        try {
            an.attach(p);
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("An=" + an.passportNumber());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BidirectionalOneToOneDemo.java
java BidirectionalOneToOneDemo
~~~

Stdout:

~~~text
Mai=P01
holder=Mai
rejected=already assigned
An=none
~~~

`Passport.claim` checks before updating the reference. If the Passport already has another holder, it throws an exception, so `Person.attach` does not assign the Passport to An. Both directions remain consistent in the demo's sequential scenario.

**Limitations:** The example does not yet support unlink/replacement and is not synchronized across threads. Uniqueness is only enforced through the built API in the current runtime; if using a DB, additional constraints/transactions are required. Nested classes inside the same outer class are easy to present in a single file; access between real-world classes requires properly designed API/helper permissions.

## 7. Should you always create a reverse link?

No. **Unidirectional** is simple, with less state to synchronize. **Bidirectional** allows fast navigation from both sides, but increases coupling:

- Both sides must be updated on attach/detach/replace.
- Cycles can easily occur, causing recursive `toString` or serialization.
- Reference leaks can easily occur if a registry holds objects on both sides.
- One owner must be chosen to be responsible for updating the invariant.

Only use a back-reference when there is a **real use case**: for example, an Employee needs to know its Department, or an entity needs a reverse reference to check a domain rule.

## 8. One-to-many: one field to a collection

Example:

~~~java
class Team {
    private final java.util.List<Member> members =
            new java.util.ArrayList<>();
}
~~~

There are three object levels:

~~~text
Team #1
   |
   | members field
   v
List #1 [0] -------------> Member #1
        [1] -------------> Member #2
        [2] -------------> Member #3
~~~

The `members` field holds a reference to a **List object**. The List stores reference values to **Member objects**. The List does not create Members automatically, and `members.add(existing)` does not clone the existing object.

### Constraints that must be defined

- Can a Team be empty (`0..*` or `1..*`)?
- Is adding the same Member object twice allowed?
- Are two Members with the same name but different IDs valid?
- Is there a maximum limit on member count?
- Is the caller allowed to directly modify the collection?
- Can a Member belong to multiple Teams?

A `List<Member>` does not automatically know the answers to these questions.

## 9. Unidirectional one-to-many: Team → Members

Create **`OneToManyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OneToManyDemo {
    static final class Member {
        private final String name;

        Member(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }
    }

    static final class Team {
        private final List<Member> members = new ArrayList<>();

        void add(Member candidate) {
            Objects.requireNonNull(candidate);
            if (members.contains(candidate)) {
                throw new IllegalArgumentException("duplicate reference");
            }
            members.add(candidate);
        }

        List<Member> snapshot() {
            return List.copyOf(members);
        }

        String names() {
            List<String> result = new ArrayList<>();
            for (Member member : members) {
                result.add(member.name());
            }
            return result.toString();
        }
    }

    public static void main(String[] args) {
        Team team = new Team();
        Member mai = new Member("Mai");
        Member an = new Member("An");

        team.add(mai);
        team.add(an);

        System.out.println("members=" + team.names());
        System.out.println("size=" + team.snapshot().size());

        try {
            team.add(mai);
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OneToManyDemo.java
java OneToManyDemo
~~~

Stdout:

~~~text
members=[Mai, An]
size=2
duplicate=duplicate reference
~~~

In the demo, Member does not override `equals`, so `List.contains` relies on the default equality based on **object identity**. Two different Member instances with the same name can still be added. If “no duplicates” actually means having the same **business ID**, you must check the ID instead of defaulting to reference identity.

`List.copyOf` provides a snapshot whose structure cannot be modified via standard List mutators. With Member containing a private final String in the demo, sharing elements does not pose a significant mutable state risk.

## 10. `List`, `Set`, and `Map`

| Field type | Ordered? | Duplicates? | Use when |
| --- | --- | --- | --- |
| `List<Member>` | Ordered by index | Possible | Need position/order or allow duplicates |
| `Set<Member>` | Depends on implementation | No, per `equals/hashCode` | Need a duplicate-free set |
| `LinkedHashSet<Member>` | Preserves insertion order | No, per equality | Need both no duplicates and insertion order |
| `Map<MemberId, Member>` | By key; ordering depends on implementation | Unique keys | Lookup by stable business ID |
| `Collection<Member>` | General contract | Depends on concrete type | Reduce dependency on implementation |

You should not assume “one-to-many requires ArrayList”. A Department managed by Employee ID can use `Map<String, Employee>`. A Playlist can use List because order matters and songs sometimes repeat.

### Why does `Set` not automatically solve domain uniqueness?

`Set` relies on `equals/hashCode`. If Employee only uses Object's default, two different Employee instances with the same ID can still coexist in the same Set. If Employee uses a mutable field in hashCode and that field changes, `contains/remove` can fail mysteriously. Define business identity clearly.

## 11. Bidirectional one-to-many: Department ↔ Employee

A Department holds many Employee references; each Employee holds at most one Department reference:

~~~text
Department A ----employees----> [Employee Mai, Employee An]
                                      |              |
                                      +--department--+
                                            |
                                            v
                                       Department A
~~~

Desired invariants:

1. If `employee.department == department`, the `department.employees` list contains employee.
2. If the list contains employee, the `employee.department` field points back to department.
3. When moving an employee to another department, remove it from the old list and add it to the new list.
4. When removing, remove on both sides.
5. If duplicates are invalid, do not contain the same employee reference in two slots.

Java does not automatically maintain those invariants. There should be **one coordinating method** for the transfer so callers do not update each side arbitrarily.

## 12. Runnable example: transferring an Employee between two Departments

Create **`BidirectionalOneToManyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BidirectionalOneToManyDemo {
    static final class Employee {
        private final String name;
        private Department department;

        Employee(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        String departmentName() {
            return department == null ? "none" : department.name();
        }
    }

    static final class Department {
        private final String name;
        private final List<Employee> employees = new ArrayList<>();

        Department(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        void add(Employee employee) {
            Objects.requireNonNull(employee);
            if (employee.department == this) {
                return;
            }

            Department previous = employee.department;
            if (previous != null) {
                previous.employees.remove(employee);
            }

            employees.add(employee);
            employee.department = this;
        }

        void remove(Employee employee) {
            Objects.requireNonNull(employee);
            if (employee.department != this) {
                return;
            }
            employees.remove(employee);
            employee.department = null;
        }

        String names() {
            List<String> result = new ArrayList<>();
            for (Employee e : employees) {
                result.add(e.name());
            }
            return result.toString();
        }
    }

    public static void main(String[] args) {
        Department backend = new Department("Backend");
        Department frontend = new Department("Frontend");
        Employee mai = new Employee("Mai");
        Employee an = new Employee("An");

        backend.add(mai);
        frontend.add(an);

        System.out.println("before Backend=" + backend.names());
        System.out.println("before Frontend=" + frontend.names());

        frontend.add(mai);
        System.out.println("after Backend=" + backend.names());
        System.out.println("after Frontend=" + frontend.names());
        System.out.println("Mai=" + mai.departmentName());

        frontend.remove(an);
        System.out.println("An=" + an.departmentName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BidirectionalOneToManyDemo.java
java BidirectionalOneToManyDemo
~~~

Stdout:

~~~text
before Backend=[Mai]
before Frontend=[An]
after Backend=[]
after Frontend=[An, Mai]
Mai=Frontend
An=none
~~~

### Trace after `frontend.add(mai)`

- Initially `mai.department` points to Backend; Backend.employees contains Mai.
- The statement `previous.employees.remove(mai)` removes the reference from the Backend list.
- `frontend.employees.add(mai)` adds the reference to the Frontend list.
- `mai.department = frontend` updates the reverse field.

No new Employee is created during the transfer. The Mai object retains the same identity.

The code intentionally places Employee/Department as **nested classes inside the same outer class**, where Java 17 allows nestmates to access private fields under the current rules. When splitting them into two top-level classes, you must design helper methods, package access, or a relation-management service — you should not make all fields public.

**Limitations:** The demo assumes sequential execution in memory. It does not handle transactions, failures mid-update, multiple threads, or persistence. In practice, you need to check all preconditions **before mutation**, and if multiple steps can fail, ensure proper atomicity/rollback.

## 13. Why not expose two independent setters?

An error-prone API:

~~~java
employee.setDepartment(frontend);
frontend.getEmployees().add(employee);
backend.getEmployees().remove(employee);
~~~

The caller may forget any line, execute them in the wrong order, or hit an exception halfway through. Result: the Employee.department field and the Department lists are **inconsistent**.

Prefer an operation:

~~~java
frontend.add(employee);
~~~

or:

~~~java
employee.transferTo(frontend);
~~~

whose implementation is actually responsible for updating both sides. For a multi-aggregate domain or one with a database, a `transferEmployee` service with transactions and permission checks may be a more appropriate boundary.

“Owner” in a domain API means **the place responsible for the invariant**, not automatically synonymous with the “owning side” in JPA/Hibernate; ORM mapping also has its own rules for storing foreign keys.

## 14. Private fields and snapshots

A field:

~~~java
private final List<Member> members = new ArrayList<>();
~~~

does not prevent mutation of the List, though it keeps the reference from being reassigned. If the API is:

~~~java
List<Member> members() {
    return members;
}
~~~

the caller can call `clear()` or `add(null)` to break Team's validation.

One option:

~~~java
List<Member> membersSnapshot() {
    return List.copyOf(members);
}
~~~

`List.copyOf` returns a List whose structure cannot be modified via List mutators, and it does not reflect subsequent structural changes of the source mutable List. However, it **does not deep-copy Member objects**. If Member is mutable, other aliases can still mutate the Member referenced by the snapshot.

### Runnable example of a shallow snapshot

Create **`ShallowSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    static final class Task {
        private boolean done;

        void complete() {
            done = true;
        }

        boolean done() {
            return done;
        }
    }

    static final class Project {
        private final List<Task> tasks = new ArrayList<>();

        void add(Task task) {
            tasks.add(java.util.Objects.requireNonNull(task));
        }

        List<Task> tasksSnapshot() {
            return List.copyOf(tasks);
        }
    }

    public static void main(String[] args) {
        Project project = new Project();
        Task task = new Task();
        project.add(task);
        List<Task> snapshot = project.tasksSnapshot();

        System.out.println("before=" + snapshot.get(0).done());
        task.complete();
        System.out.println("after=" + snapshot.get(0).done());

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowSnapshotDemo.java
java ShallowSnapshotDemo
~~~

Stdout:

~~~text
before=false
after=true
snapshot cannot be cleared
~~~

**Conclusion:** You may have locked the **relation list structure** against the caller while still sharing mutable **element state**. If the API promises a completely immutable snapshot, you must snapshot the elements or use immutable value objects.

## 15. Object identity and equality

Two common types of comparison:

- `a == b`: whether two references denote the **same object**.
- `a.equals(b)`: whether two objects are **equal in value/business identity** according to the class's contract.

~~~java
record MemberId(String id) {}

MemberId x = new MemberId("M1");
MemberId y = new MemberId("M1");
~~~

In Java 17, `x == y` is false because two separate record instances were created; `x.equals(y)` is true because the components are equivalent.

### Duplicate criteria in relationships

- **Same Java object:** check identity.
- **Same stable ID:** check `id` with equals or a Map key.
- **Same content value:** appropriate for value objects, but not always appropriate for entities.

Do not use a display name as a unique key if the domain allows two people to have the same name.

## 16. One-to-many using a Map with a business ID

Create **`OneToManyByIdDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OneToManyByIdDemo {
    record Member(String id, String name) {
        Member {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
        }
    }

    static final class Team {
        private final Map<String, Member> byId = new LinkedHashMap<>();

        void add(Member member) {
            if (member == null) {
                throw new IllegalArgumentException("member required");
            }
            if (byId.containsKey(member.id())) {
                throw new IllegalArgumentException("duplicate id");
            }
            byId.put(member.id(), member);
        }

        Member find(String id) {
            return byId.get(id);
        }

        List<Member> snapshot() {
            return List.copyOf(byId.values());
        }
    }

    public static void main(String[] args) {
        Team team = new Team();
        team.add(new Member("M1", "Mai"));
        team.add(new Member("M2", "Mai"));

        System.out.println("size=" + team.snapshot().size());
        System.out.println("M2=" + team.find("M2").name());

        try {
            team.add(new Member("M1", "Other"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("size again=" + team.snapshot().size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OneToManyByIdDemo.java
java OneToManyByIdDemo
~~~

Stdout:

~~~text
size=2
M2=Mai
rejected=duplicate id
size again=2
~~~

There are two Members named Mai with different IDs, so both are valid. The repeated M1 is rejected. `LinkedHashMap` preserves insertion order in the demo. `Member` is a record with String components, which helps keep the ID value stable.

**Note on mutable hash keys:** If you use a mutable entity as a `HashMap` key/`HashSet` element and the fields participating in `equals/hashCode` change after insertion, `get/contains/remove` may fail to find the key as expected. Choose an immutable key or a stable ID.

## 17. Association, aggregation, and composition

They may all use reference fields, but differ in **ownership/lifecycle** meaning:

**Association:** A general relationship between objects; the objects can exist independently. For example, a Teacher participates in a Course.

**Aggregation:** A container groups parts that have their own lifecycle. For example, a Department groups Employees; an Employee can switch Departments.

**Composition:** An owner manages parts with lifecycles strongly bound by the domain. For example, an Order has its own OrderLines, which must not be shared as entities between orders.

Java has no dedicated keyword for the JVM to distinguish composition from aggregation automatically. Nor does it automatically “destroy the child” as soon as the owner's reference is dropped. The garbage collector works by reachability, not by UML diamond notation.

### Comparison with inheritance

~~~java
class Car {
    private Engine engine; // HAS-A.
}

class ElectricCar extends Car {
    // IS-A: ElectricCar is a type of Car.
}
~~~

`Car extends Engine` is the wrong model if you only mean a car **has** an engine. A has-a relationship should use a reference field/composition; `extends` represents an is-a relationship and inheritance rules.

## 18. One-to-many composition example: Order → OrderLines

Create **`OrderCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderCompositionDemo {
    record Line(String sku, int quantity, long unitPriceCents) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long subtotal() {
            return Math.multiplyExact(quantity, unitPriceCents);
        }
    }

    static final class Order {
        private final List<Line> lines = new ArrayList<>();

        void addLine(String sku, int quantity, long price) {
            Line line = new Line(sku, quantity, price);
            line.subtotal();
            lines.add(line);
        }

        List<Line> snapshot() {
            return List.copyOf(lines);
        }

        long total() {
            long result = 0;
            for (Line line : lines) {
                result = Math.addExact(result, line.subtotal());
            }
            return result;
        }
    }

    public static void main(String[] args) {
        Order order = new Order();
        order.addLine("P1", 2, 100);
        order.addLine("P2", 1, 50);

        System.out.println("lines=" + order.snapshot().size());
        System.out.println("total=" + order.total());

        try {
            order.snapshot().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot protected");
        }

        System.out.println("total again=" + order.total());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderCompositionDemo.java
java OrderCompositionDemo
~~~

Stdout:

~~~text
lines=2
total=250
snapshot protected
total again=250
~~~

`Order` creates Line values through a domain operation; the caller does not directly modify the List. `Line` is a record containing String/primitive fields; the line objects have immutable state by design in the demo.

**Do not over-infer:** composition does not prevent two Orders from having two Line objects that are **equal in value**. Domain lifecycle ownership and value equality are different concepts.

## 19. Replacing a reference differs from mutating the linked object

Suppose:

~~~java
Profile p = user.profile();
user.changeProfile(new Profile("An"));
~~~

if the API allows it, this is **replacing the reference field**, making User point to a new object. The old Profile may still remain alive through `p` or other references.

Conversely:

~~~java
user.profile().setName("An");
~~~

if Profile is mutable, this is **changing the state of the current Profile object itself**. Aliases to that object can see the new name.

A one-to-one relation can use an **immutable Profile** so each data edit creates a new Profile, or a mutable Profile with its own domain API. You should not refer to both behaviors identically as “changing the Profile” without defining the semantics.

### Does a `final` field guarantee immutability?

`private final Profile profile` only prevents reassigning the reference field in normal Java code. If Profile is mutable, Profile's state can still change. If two Users both hold a mutable Profile, modifying it through one User can affect the other User.

## 20. Relationships and pass-by-value

Java is always **pass-by-value**. For a reference argument, the method receives a **copy of the reference value**.

~~~java
static void replace(Team team) {
    team = new Team();
}
~~~

Reassigning the `team` parameter does not make the caller's Team variable point to the new object. However:

~~~java
static void add(Team team, Member member) {
    team.add(member);
}
~~~

can modify the collection inside the Team object that the caller still references. This is an illustrative snippet, using appropriate types/methods.

The important thing is to distinguish:

- Assigning a reference variable: changes **the arrow from the variable**.
- Assigning a reference field: changes **the arrow from the object field**.
- Adding a List element: mutates **the container object**.
- Modifying an element's field: mutates **the target object that the List is referencing**.

## 21. Null and empty collections

For an optional `0..1` relation, a nullable field can mean “not linked yet”.

For a `0..*` relation, it is usually better to use an **empty List** instead of a null collection field:

~~~java
private final List<Member> members = new ArrayList<>();
~~~

The caller does not have to check both null and empty. If the domain requires `1..*`, the constructor/factory or operation validation must ensure at least one member exists, even after a remove.

### Do not use Optional for every collection

`Optional<List<Member>>` is usually unnecessary if an empty List has a reasonable meaning. Optional is more appropriate for **a relation that may be absent** or a lookup query that may find nothing.

Never treat missing required data as a valid null simply because it is easy to implement: define the invariant first.

## 22. Unlinking does not delete an object immediately

If `department.remove(employee)` is called, the code only removes the reference from the List and may set `employee.department = null`. The Employee object may still be referenced by a local variable, service, registry, or another collection.

If there is no remaining reachable reference path, the GC **may** reclaim the object when appropriate; there is no guarantee of immediate reclamation or an object delete statement in core Java syntax.

This also applies to composition: “child removed from owner” is a domain/persistence policy, not automatically synonymous with the heap object disappearing immediately.

## 23. Bidirectional relationships, cycles, and `toString`

A bidirectional Department/Employee graph can create a cycle:

~~~text
Department ----> Employee
     ^              |
     +--------------+
~~~

Modern GCs can handle unreachable cycles; a cycle by itself **is not enough to prove a memory leak**. However, if `Department.toString()` prints Employees and `Employee.toString()` prints Department, infinite mutual calls can lead to a `StackOverflowError`.

For logging:

- Print the Employee ID or Department name instead of the entire object graph.
- Limit the depth if traversal is needed.
- Use an identity-based visited set if traversing a graph with cycles.
- For JSON serialization, design DTOs or configure reference cycle handling according to the library.

### Runnable program: printing without recursion

Create **`SafeCycleDemo.java`**:

~~~java
public class SafeCycleDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void link(Node node) {
            next = node;
        }

        String describe() {
            return name + " -> " +
                    (next == null ? "none" : next.name);
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.link(b);
        b.link(a);

        System.out.println(a.describe());
        System.out.println(b.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeCycleDemo.java
java SafeCycleDemo
~~~

Stdout:

~~~text
A -> B
B -> A
~~~

The two Nodes reference each other, but `describe()` only reads the name of the next node without calling `next.describe()`, so there is no infinite recursion.

## 24. Static collections and reference lifecycles

A global registry:

~~~java
static final List<Listener> LISTENERS = new ArrayList<>();
~~~

can hold references to objects whose lifecycle should have ended. If a Listener holds User/Service/UI components, the entire graph may remain reachable because of the static List.

For multi-object relationships with lifecycles, you need:

- `unregister/remove`.
- Avoid keeping request/session data in a global static collection.
- Size limits/eviction when needed.
- Have a clear owner and clear cleanup.
- Design tests to use an instance registry instead of global state whenever possible.

**A cycle is not a memory leak by itself**; a reference path still reachable from GC roots is the deciding factor.

## 25. Concurrency: consistent relationships across multiple threads

`ArrayList` is not automatically thread-safe. Code like:

~~~java
if (!members.contains(member)) {
    members.add(member);
}
~~~

is **check-then-act**. Two threads can both observe that the member is absent and both add it, breaking the “no duplicates” invariant.

With a bidirectional relationship, one thread moving an Employee to Department A while another thread moves it to B can create an inconsistent state if not coordinated.

Ways to handle this depending on the system:

- Place a lock/synchronization around **the entire operation of checking and updating the link**, not just a single `add` statement.
- Choose a concurrent collection suited to the specific semantics and atomic operations.
- Use a single-owner thread or actor/message passing when appropriate.
- For persistent data, use transactions, unique constraints/foreign keys, and concurrency control.
- Establish a lock ordering to reduce deadlock risk when updating multiple owners.

A `final` reference does not automatically make a mutable collection thread-safe; `Collections.synchronizedList` also does not automatically guarantee that a multi-step operation involving Employee.department and multiple Lists is atomic.

## 26. Java models and databases/ORMs

When learning core Java, reference fields only describe the **in-memory object graph**. A system with a database adds:

- Primary keys, foreign keys, and unique constraints.
- Transactions when updating relationships.
- Lazy/eager loading and ORM-level object identity maps.
- Cascade operations/orphan removal when the domain requires them.
- Framework-specific “owning side” mapping.

Do not infer that JPA `@OneToMany` is a Java keyword or that a List automatically writes to the database on `add`. The framework applies its own mapping/persistence rules.

A valid bidirectional Java graph **does not prove that the database state is valid**, and conversely a database constraint does not automatically fix out-of-sync field references on the heap if code does not refresh/synchronize them. Both layers must be verified when an ORM is involved.

## 27. Testing bidirectional relationships

For `Department.add(employee)`, do not just assert the list count. Test:

1. Adding a new Employee: Department contains the exact reference; Employee.department points back.
2. Re-adding the same Employee: idempotent policy or clear error thrown.
3. Transferring from A to B: A does not contain Employee; B contains it; Employee.department == B.
4. Removing from B: both directions are cleared.
5. Null input: rejected if invalid.
6. Two Employees with the same name/ID: handled according to the uniqueness contract.
7. If an operation fails, no half-updated state remains.
8. If parallel execution is supported, test invariants under concurrency.

An assertion checking only `employee.departmentName()` is not enough to detect whether the employee still remains in the old Department list.

### Automating tests

In real applications, you can use JUnit to check `assertSame`, `assertTrue`, `assertFalse`, and `assertThrows`. However, the Java 17+ examples in this lesson use `main` and stdout to self-verify without requiring external libraries.

## 28. Common mistakes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| A reference field creates an object automatically | NullPointerException | Initialize explicitly |
| A single reference field guarantees exclusive one-to-one | Multiple owners share the same target | Add constraint/back-reference/owner |
| Two references update automatically | Inverse relation goes out of sync | One operation coordinates both sides |
| `List<Member>` creates Member objects | Empty list | Create/obtain members and then add them |
| A List with 2 entries means 2 distinct objects | Duplicate aliases | Consider object IDs and uniqueness |
| `List.copyOf` deep-copies Member | Mutable Member remains shared | Immutable elements/copy per contract |
| A private final List means the List is immutable | Caller/methods can still mutate the List | Hide mutation paths, return snapshots |
| Every one-to-many must be bidirectional | Unnecessary increase in coupling | Choose direction based on use case |
| Using a mutable business field as a hash key | contains/remove behaves unexpectedly | Stable key |
| Using `extends` to express “has-a” | Wrong subtype semantics | Reference field/composition |
| Dropping a reference deletes the object immediately | Misunderstanding GC | Understand reachability |
| Cycles always leak memory | Misunderstanding GC | Check GC roots |
| Printing the whole graph in toString | Infinite recursion | Print ID/name, track visited |
| Check-then-add on ArrayList is atomic | Race, duplicates | Locks/atomic operations |
| ORM annotations automatically fix the inverse Java field | Inconsistent graph | Manage in-memory association explicitly |
| Not testing remove/move/fail | Invariant only holds on the happy path | Test all transitions |

## 29. Step-by-step relationship design workflow

**Step 1:** List the two object types and navigation use cases.

**Step 2:** Write out the **cardinality from both sides**: `0..1`, `1`, `0..*`, `1..*`, or a limit of N.

**Step 3:** Choose **unidirectional/bidirectional**. If access is only from A to B, do not add unnecessary back-references.

**Step 4:** Choose the representation: a field to an object or a field to a List/Set/Map.

**Step 5:** Define **identity** and the duplicate rule: same instance, stable ID, or value equality.

**Step 6:** Choose the **owner** that performs mutations: constructor/factory, method on A/B, or domain service.

**Step 7:** Protect invariants via non-null validation, private fields, meaningful operations, and snapshots.

**Step 8:** Implement complete attach/detach/replace/move operations, including handling the previous link.

**Step 9:** Specify lifecycle/ownership: can child objects exist independently, are shared aliases allowed, and how is cleanup handled.

**Step 10:** Test failure cases, concurrency, and persistence constraints if the system requires them.

## 30. Exercise 1 — Is a single field enough to guarantee one-to-one?

~~~java
Profile shared = new Profile();
User a = new User();
User b = new User();
a.profile = shared;
b.profile = shared;
~~~

These declarations are an illustrative snippet assuming appropriate public/package fields and constructors.

**Answer:** There are two User objects and **one Profile object**. Both Users reference the same Profile. There is no uniqueness constraint. To ensure a Profile belongs to at most one User, it must be enforced via a relation operation and a back-reference/registry, or a constraint at the persistence layer.

## 31. Exercise 2 — Duplicate reference in a List

~~~java
Member mai = new Member("Mai");
List<Member> members = new ArrayList<>();
members.add(mai);
members.add(mai);
System.out.println(members.size());
System.out.println(members.get(0) == members.get(1));
~~~

**Answer:**

~~~text
2
true
~~~

Both list slots point to the same Member object. If the domain forbids duplicate identity, check before adding or use an appropriate representation.

## 32. Exercise 3 — Transferring ownership

Given the state:

~~~text
A.employees = [Mai, An]
B.employees = [Binh]
Mai.department -> A
An.department -> A
Binh.department -> B
~~~

After `B.add(Mai)` under the contract that each Employee belongs to at most one Department:

~~~text
A.employees = [An]
B.employees = [Binh, Mai]
Mai.department -> B
An.department -> A
Binh.department -> B
~~~

If A still contains Mai, the invariant is broken. Write a test that checks **both collections as well as the back-reference**.

## 33. Exercise 4 — Protecting a private collection

~~~java
class Team {
    private final List<Member> members = new ArrayList<>();
    List<Member> members() {
        return members;
    }
}
~~~

**Question:** Can the caller call `team.members().clear()`? Does that bypass validation?

**Answer:** Yes. The getter returns the raw mutable List. Replace it with a query/snapshot and `addMember`/`removeMember` methods. However, a List snapshot does not automatically deep-copy Member objects if Member is mutable.

## 34. Exercise 5 — Choosing a collection type

Choose a representation for:

- A playlist that needs ordering and allows the same song to appear multiple times.
- A Department accessing Employees by stable ID.
- A duplicate-free set of tags.
- OrderLines with display positions.
- A Customer having at most one loyalty card.

**Suggested answer:** Playlist: List; Department: Map<ID, Employee>; Tags: Set; OrderLines: List; Customer → Card: single reference field. Always add validation to protect cardinality and integrity.

## 35. Exercise 6 — Composition or aggregation?

An Order owns its Line values. A Team contains Employees that can transfer to another Team.

**Answer:** Order–Line fits composition in terms of lifecycle; Team–Employee usually fits association/aggregation. Both use Java references/collections; they differ in the **ownership contract**, not in modifiers or field form.

## 36. Exercise 7 — A cycle is not an automatic GC leak

A Department holds an Employee; the Employee holds the Department.

**Question:** Does the cycle prevent the garbage collector from reclaiming both forever?

**Answer:** No. If there is no reference path from GC roots to the cycle, the objects can be reclaimed. However, a static registry holding a Department/Employee reference can keep them reachable and cause memory retention. You do not need to break every cycle just for the GC to work.

## 37. End-of-lesson checklist

- [ ] I know a reference field stores a reference value or null, and does not create an object automatically.
- [ ] I understand a single field does not automatically create domain-wide uniqueness.
- [ ] I can read relationship multiplicity in both directions.
- [ ] I know to use a non-null constructor for a required relationship.
- [ ] I can use Optional in the API for an optional relationship.
- [ ] I know assigning one field does not automatically update the back-reference.
- [ ] I can design a bidirectional one-to-one relationship with uniqueness checks.
- [ ] I can implement one-to-many using a private List/Set/Map.
- [ ] I can distinguish the collection object from element objects.
- [ ] I know a List can hold two references to the same object.
- [ ] I can distinguish identity, equals, and a stable business ID.
- [ ] I know the risks of Set/Map when hash keys are mutable.
- [ ] I can transfer an Employee between Departments without breaking invariants.
- [ ] I understand why a raw mutable List getter breaks encapsulation.
- [ ] I understand List.copyOf does not deep-copy mutable elements.
- [ ] I can distinguish association, aggregation, composition, and inheritance.
- [ ] I know replacing a reference differs from mutating an object's state.
- [ ] I know dropping a reference does not delete the object immediately.
- [ ] I avoid toString/serialization recursion through cycles.
- [ ] I know a static collection can keep an object graph reachable for a long time.
- [ ] I do not assume ArrayList and check-then-act are automatically thread-safe.
- [ ] I understand in-memory Java relationships differ from DB constraints/transactions.
- [ ] I write tests for attach, detach, transfer, duplicate, and failure paths.
- [ ] I can compile, run, and explain the Java 17+ examples in this lesson myself.

**Conclusion:** A **one-to-one** relationship is fundamentally represented by **one reference field**, and a **one-to-many** relationship by **one reference field to a collection**. However, those structures **only store reference values**. Uniqueness, ownership, minimum/maximum counts, child lifecycle, and bidirectional consistency are **invariants that class and API design must protect**. Choose unidirectional or bidirectional based on the use case, use List/Set/Map according to semantics, keep fields private, provide meaningful operations, and thoroughly test addition, removal, transfer, and failure paths.
