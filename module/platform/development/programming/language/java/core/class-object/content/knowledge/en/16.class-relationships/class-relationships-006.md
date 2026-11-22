# Bidirectional Relationships and Preserving Consistency Between Classes in Java

In object-oriented programming, a **bidirectional association** allows navigating from object A to object B, as well as tracing back from B to A. For example, an `Employee` knows the department it belongs to, while a `Department` knows the employees in that department. Both sides must describe **the same relationship**.

The danger is that Java does not automatically synchronize two references or collections. If `employee.department` points to department X, yet `X.employees` does not contain that employee, the objects are in an inconsistent state. Similarly, if an employee is moved from X to Y without being removed from X's list, one person can appear in two departments even though the model allows belonging to at most one department.

This lesson belongs to **Java core - class-object**, under the **Class Relationships** group. The goal is to design *relationship invariants*, control adding, removing, and transferring links, avoid one-sided updates, handle exceptions, prevent duplicates and mutable aliases, distinguish one-to-one, one-to-many, and many-to-many relationships, and recognize when concurrency control or a database transaction is needed. Complete programs use **Java 17+**.

## 1. Unidirectional and Bidirectional Associations

Unidirectional:

~~~java
class Department {
    private final String name = "Engineering";
}

class Employee {
    private Department department;
}
~~~

These are two illustrative classes without `main`. When holding an Employee object, authorized code can follow `department`. Conversely, a Department has no field providing direct access to the list of Employees. To find who belongs to that department, one can query a repository or an externally managed collection.

Bidirectional:

~~~java
class Department {
    private final java.util.List<Employee> employees =
            new java.util.ArrayList<>();
}

class Employee {
    private Department department;
}
~~~

Now there are two directions, yet **the two fields do not automatically stay consistent with each other**. A collection and a reference are storing duplicate link information. If two independent update sites exist, they can easily drift out of sync.

A bidirectional relationship should only be chosen when reverse lookup provides real value. If the reverse direction can be queried easily and is rarely used, a unidirectional model can be less risky.

## 2. Do Not Confuse Bidirectional with Aggregation/Composition

These are different dimensions of classification:

| Concept | Meaning | Example |
| --- | --- | --- |
| Association | Objects are related | Employee and department |
| Unidirectional/bidirectional | Can be navigated in one or both directions | Employee → Department or both |
| Multiplicity | How many partners each end has | One department has many people; each person has at most one department |
| Aggregation | Loose whole–part relationship according to the domain model | A team consists of independent members |
| Composition | Strong ownership/part lifecycle bound to the whole | Order owns OrderLine |
| Ownership of update | Which part of the code executes link changes | Department.addMember is the entry point |

**A bidirectional relationship is not automatically composition.** A friendship link can be bidirectional, yet neither owns the other's lifecycle. An Order can own OrderLine, yet the API may only need the direction from Order to its lines.

In Java Core, these relationships are usually represented using reference fields, `List`, `Set`, `Map`, and methods. The responsibility for maintaining invariants belongs to the code, not a special keyword.

## 3. Writing Invariants in a Checkable Form

Business assumption: one `Member` belongs to **0 or 1** `Team`; one `Team` has **0 or many** `Member`s; each member appears only once within the same team.

~~~text
Member.team == T
    <=> Team T contains Member exactly once.

Member.team == null
    => no Team within the managed scope holds Member.

Member has only one team at a time.
If moved from A to B:
    A no longer has Member;
    B has Member exactly once;
    Member.team == B.
~~~

The `<=>` symbol in the diagram means both directions are equivalent regarding the existence of the relationship. You must not only check `member.team != null`, but also verify that the Team on the reverse side actually stores the member.

If the business rules do not allow a member without a team, you must use multiplicity **1 ↔ 0..***, and the `leave()` method must not expose the `team=null` state as a valid final state. Domain policy decides whether `null` is allowed or not.

## 4. Three Core Operations of a Bidirectional Relationship

| Operation | Required Changes |
| --- | --- |
| Add | Attach the reference from A to B and add A to B's collection |
| Remove | Clear the reference on A and remove A from B's collection |
| Move A from B1 to B2 | Remove from B1, add to B2, update A's reference |
| Re-add the same link | Do not create duplicate elements |
| Remove again or request removal from the wrong B | Do not accidentally remove a different link |
| Validation failure | Keep the old state according to the contract |

A dangerous call if the setter only modifies one field:

~~~java
employee.setDepartment(newDepartment);
~~~

This is **an illustrative call of an unprotected API**, not a standalone program. `oldDepartment.employees` and `newDepartment.employees` may still remain unchanged.

A more sensible behavioral API is `employee.transferTo(newDepartment)` or `newDepartment.addEmployee(employee)`. Inside that method, the code performs all necessary updates.

## 5. Choosing a Single Source to Execute Changes

There should be **one central algorithm** for changing links. If both ends expose convenient public methods, the other end **delegates** to that algorithm; do not duplicate two implementations.

For example, `Member.moveTo(next)` can call `next.add(this)`. `Team.add(member)` is where the old team and new team are checked and both ends are updated. When leaving a team, `Member.moveTo(null)` delegates to `oldTeam.remove(this)`.

The algorithm does not have to live inside Team: a `MembershipService` or `Employee.transferTo` can also be the owner. What matters is avoiding an API that forces the caller to remember three independent operations in the exact order.

**Correct design:** the caller expresses *intent*. **Error-prone design:** the caller must know every internal collection/reference.

## 6. Complete Program: One Team and Many Members

Create the file **`BidirectionalTeamDemo.java`**. The two member types `Team` and `Member` live in the same enclosing class; Java allows code in nested classes to access each other's appropriate `private` members within the same nest.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BidirectionalTeamDemo {
    private static final class Team {
        private final String name;
        private final List<Member> members = new ArrayList<>();

        Team(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("team name rỗng");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        List<String> memberNames() {
            return members.stream()
                    .map(Member::name)
                    .toList();
        }

        boolean add(Member member) {
            Objects.requireNonNull(member, "member");

            if (member.team == this) {
                return false;
            }
            if (members.contains(member)) {
                throw new IllegalStateException("đích đã chứa member");
            }

            Team old = member.team;
            if (old != null && !old.members.contains(member)) {
                throw new IllegalStateException("nguồn thiếu member");
            }

            // The step that may require allocation at the destination happens first.
            members.add(member);

            if (old != null) {
                old.members.remove(member);
            }
            member.team = this;
            return true;
        }

        boolean remove(Member member) {
            Objects.requireNonNull(member, "member");

            if (member.team != this) {
                return false;
            }
            if (!members.remove(member)) {
                throw new IllegalStateException("team thiếu member");
            }
            member.team = null;
            return true;
        }
    }

    private static final class Member {
        private final String name;
        private Team team;

        Member(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("member name rỗng");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        String teamName() {
            return team == null ? "-" : team.name();
        }

        boolean moveTo(Team next) {
            if (next == null) {
                return team != null && team.remove(this);
            }
            return next.add(this);
        }
    }

    public static void main(String[] args) {
        Team red = new Team("Đỏ");
        Team blue = new Team("Xanh");
        Member an = new Member("An");
        Member binh = new Member("Bình");

        red.add(an);
        red.add(binh);
        System.out.println("red=" + red.memberNames());
        System.out.println("blue=" + blue.memberNames());

        System.out.println("repeat=" + red.add(an));
        System.out.println("An team=" + an.teamName());

        an.moveTo(blue);
        System.out.println("after red=" + red.memberNames());
        System.out.println("after blue=" + blue.memberNames());
        System.out.println("after An=" + an.teamName());

        System.out.println("wrong remove=" + red.remove(an));
        an.moveTo(null);
        System.out.println("empty blue=" + blue.memberNames());
        System.out.println("unassigned=" + an.teamName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BidirectionalTeamDemo.java
java BidirectionalTeamDemo
~~~

**Stdout:**

~~~text
red=[An, Bình]
blue=[]
repeat=false
An team=Đỏ
after red=[Bình]
after blue=[An]
after An=Xanh
wrong remove=false
empty blue=[]
unassigned=-
~~~

### Why Does This Example Keep Both Ends Consistent?

- `Team.members` and `Member.team` are private, with no arbitrary direct setters.
- `red.add(an)` adds to the list and changes `an.team` in the same code path.
- Calling `red.add(an)` a second time returns `false`, avoiding duplicates.
- `an.moveTo(blue)` delegates to `blue.add(an)`: it validates the source, adds to the destination, removes from the source, and sets the new reference.
- `red.remove(an)` when An already belongs to Blue returns `false`, without removing the current relationship.
- `an.moveTo(null)` removes specifically from Blue and returns An to an unassigned state.

**Limitations:** this example is intentionally **single-threaded**, with no callbacks/database. The individual steps are not atomic across threads. `ArrayList.add` can fail due to resource constraints; adding to the destination before removing from the source reduces one scenario of losing the relationship, but **does not guarantee rollback against all critical errors**.

## 7. An Invariant Needs Both Forward and Reverse Directions

Some code only checks one end:

~~~text
assert member.team == team
~~~

This is not enough. If `team`'s collection does not contain `member`, the system is still wrong. A complete check for a 0..1 ↔ 0..* relationship needs to verify:

- If `member.team == team`, the team's collection must contain the member.
- If the collection contains the member, the `member.team` field must point to that same team.
- Each member object appears exactly once in one team according to the model.
- A member belonging to team A is no longer in any other team B within the managed relationship scope.

When writing tests for a move operation, you must check **the old team, the new team, and the moved object**. Checking only the `member.teamName()` line after the call cannot detect "leftover entries in the old list".

## 8. Why Not Return the Internal Collection Directly?

If you design it as:

~~~java
List<Member> getMembers() {
    return members;
}
~~~

and a caller executes:

~~~java
team.getMembers().clear();
~~~

then the caller clears all memberships in Team without updating `member.team` on each Member. This is **an illustrative snippet showing a path that breaks the invariant**, not a complete program.

Options:

- **Snapshot:** `List.copyOf(members)` when elements are non-null; the caller cannot add/remove through the snapshot list.
- **Read-only view:** `Collections.unmodifiableList(members)`; prevents modification through the view, yet reflects changes to the original list.
- **Projection:** return only the readable information needed, such as a list of names or IDs.
- **Queries:** `containsMember`, `memberCount`, `findMember` if exposing the entire list is unnecessary.

`List.copyOf` creates a shallow copy: the Member objects inside are **not deep-copied**. If Member has a setter that violates the invariant, the caller can still mutate that object. Therefore, you must protect the elements as well, not just the collection container.

In `BidirectionalTeamDemo`, `memberNames()` returns a `List<String>` from `Stream.toList()`; the result does not support modification through the list API and does not allow the caller to manipulate membership directly.

## 9. Using `List` or `Set` to Prevent Duplicates?

| Collection | Advantages | Points to Note |
| --- | --- | --- |
| `ArrayList<Member>` | Preserves insertion order, easy to demo | Must check for duplicates manually |
| `LinkedHashSet<Member>` | No duplicates by equality and preserves order | `equals/hashCode` must be stable |
| `HashSet<Member>` | Convenient membership lookup | Iteration order is not fixed |
| `Map<MemberId,Member>` | Ensures each ID appears only once | Requires defining a unique/stable ID |
| `List<Enrollment>` | Suitable when a link is an object with attributes | Needs a way to find duplicates by key pair |

`Member` in the complete program is `final` and does not override `equals`: `ArrayList.contains` relies on object identity. **Two different employee objects with the same name** are still two distinct entities. A real system should use an employee ID or an identity with a clear contract, rather than using a display name as the unique key.

Do not use mutable fields to compute `hashCode` for an object that is an element in a `HashSet`: changing the field can prevent the set from finding the element in its old bucket.

## 10. Validation, Idempotence, and Policy When Inconsistency Is Detected

If the same relationship is added again, the method can return `false` without creating a duplicate link. If the caller removes from the wrong side, it should return `false` or a meaningful result, **without severing a link that currently exists elsewhere**.

When a mismatch between the field and the collection is detected, do not silently guess which side is right and patch half of it. The example above chooses `IllegalStateException` to report an invalid internal state.

A contract can specify:

~~~text
add(already exists consistently) -> no change
remove(does not exist) -> no change
move(A -> B) -> all sides reflect B
invalid input -> report error before changing
inconsistent internal state -> fail fast for investigation
~~~

Systems that need self-healing data can create **a dedicated reconciliation process**. However, reconciliation should not be silently mixed into every setter, because that can mask the root cause of errors or lose valid links.

## 11. Operation Ordering During Moves and Preserving State on Error

Consider moving a Member from Team A to Team B. If B is already full and the code removes the Member from A before checking capacity, then when validation fails, the Member has already lost its old link.

A better sequence:

1. Validate parameters and rules allowing the move.
2. Check B's conditions, such as capacity and active status.
3. Verify that the Member is actually present in A if the field says A.
4. Compute the data needed for the update; perform operations that may throw exceptions first.
5. Update the related structures inside a controlled entry point.
6. Verify that the new state satisfies the invariant; publish the successful result.

Updating two collections and a field is still not an **atomic transaction** across threads when using only ordinary methods. If there are callbacks or external code has permission to modify collections during the move, the risk is even greater.

**Do not treat exceptions as automatic rollback.** Java will not automatically undo `old.members.remove(member)` just because a subsequent `new.members.add(member)` step throws an error.

## 12. Bidirectional One-to-One Relationship: Maintaining Symmetry

Bidirectional one-to-one requires:

~~~text
A.partner == B <=> B.partner == A

Each A has at most one partner.
Depending on business rules, null may represent being unpaired.
~~~

If A↔B and C↔D and you call A to pair with C, the consistent result must be **A↔C**, with B no longer having a partner and D also no longer having a partner. Merely assigning `A.partner=C` and `C.partner=A` will leave two stale old references behind.

Create the file **`SymmetricPartnerDemo.java`**:

~~~java
public class SymmetricPartnerDemo {
    private static final class Partner {
        private final String name;
        private Partner peer;

        Partner(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name rỗng");
            }
            this.name = name;
        }

        String peerName() {
            return peer == null ? "-" : peer.name;
        }

        void unpair() {
            if (peer == null) {
                return;
            }
            Partner old = peer;
            if (old.peer != this) {
                throw new IllegalStateException("quan hệ bị lệch");
            }
            peer = null;
            old.peer = null;
        }

        void pairWith(Partner other) {
            if (other == null) {
                throw new IllegalArgumentException("other null");
            }
            if (other == this) {
                throw new IllegalArgumentException("không tự ghép");
            }
            if (peer == other) {
                if (other.peer != this) {
                    throw new IllegalStateException("quan hệ bị lệch");
                }
                return;
            }

            if (peer != null && peer.peer != this) {
                throw new IllegalStateException("nguồn bị lệch");
            }
            if (other.peer != null && other.peer.peer != other) {
                throw new IllegalStateException("đích bị lệch");
            }

            unpair();
            other.unpair();
            peer = other;
            other.peer = this;
        }
    }

    public static void main(String[] args) {
        Partner an = new Partner("An");
        Partner binh = new Partner("Bình");
        Partner chi = new Partner("Chi");
        Partner dung = new Partner("Dũng");

        an.pairWith(binh);
        chi.pairWith(dung);
        System.out.println("first=" + an.peerName()
                + "/" + binh.peerName());
        System.out.println("second=" + chi.peerName()
                + "/" + dung.peerName());

        an.pairWith(chi);
        System.out.println("An=" + an.peerName());
        System.out.println("Chi=" + chi.peerName());
        System.out.println("Bình=" + binh.peerName());
        System.out.println("Dũng=" + dung.peerName());

        chi.unpair();
        System.out.println("after unpair="
                + an.peerName() + "/" + chi.peerName());

        try {
            an.pairWith(an);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SymmetricPartnerDemo.java
java SymmetricPartnerDemo
~~~

**Stdout:**

~~~text
first=Bình/An
second=Dũng/Chi
An=Chi
Chi=An
Bình=-
Dũng=-
after unpair=-/-
reject=không tự ghép
~~~

### Analysis

`an.pairWith(chi)` checks both existing links first, unpairs A↔B, unpairs C↔D, and then assigns A↔C. There are no callbacks or external mutations during this process. Calling `chi.unpair()` next clears **both references**.

The example **forbids self-pairing** `A↔A` because of the illustrative model's rules, not because Java forbids an object from pointing to `this`. In domains where self-references are valid, the invariants and handling must be defined separately.

For a mandatory 1↔1 relationship, the `peer=null` state may be disallowed; in that case, the same `unpair()` API cannot be exposed as a valid public operation.

## 13. Many-to-Many Relationships and Association Objects

With `Student` and `Course`, one student takes many courses, and one course has many students. A direct bidirectional design might consist of:

~~~text
Student.courses = Set<Course>
Course.students = Set<Student>
~~~

However, every enrollment or drop must add/remove in **both sets**, avoiding duplicates and keeping both sides consistent.

If the relationship carries attributes such as score, enrollment date, or status, an `Enrollment` class representing **the link itself** is usually more natural. A score of 9 belongs to **An–Java**, not An's general score across all courses or Java's score for all students.

There are two ways to organize this:

- Keep two collections and a helper that updates both.
- Keep an **Enrollment registry as the source of truth**, then build both query directions on top of the registry, avoiding storing two copies of membership.

The second approach may need additional indexes for efficient lookup on large datasets; however, those indexes must also be updated according to the same rules.

## 14. Complete Program: Many-to-Many Using a Single Registry

Create the file **`EnrollmentRegistryDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class EnrollmentRegistryDemo {
    private static final class Student {
        private final String name;

        Student(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("student name rỗng");
            }
            this.name = name;
        }
    }

    private static final class Course {
        private final String code;

        Course(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("course code rỗng");
            }
            this.code = code;
        }
    }

    private static final class Enrollment {
        private final Student student;
        private final Course course;
        private int score;

        Enrollment(Student student, Course course) {
            this.student = student;
            this.course = course;
        }

        int score() {
            return score;
        }

        void setScore(int next) {
            if (next < 0 || next > 10) {
                throw new IllegalArgumentException("score ngoài 0..10");
            }
            score = next;
        }
    }

    private record Key(Student student, Course course) {
    }

    private final Map<Key, Enrollment> entries =
            new LinkedHashMap<>();

    Enrollment enroll(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        Key key = new Key(student, course);
        return entries.computeIfAbsent(
                key, k -> new Enrollment(student, course));
    }

    boolean drop(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        return entries.remove(new Key(student, course)) != null;
    }

    Optional<Enrollment> find(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        return Optional.ofNullable(
                entries.get(new Key(student, course)));
    }

    List<String> coursesOf(Student student) {
        Objects.requireNonNull(student, "student");
        return entries.values().stream()
                .filter(e -> e.student == student)
                .map(e -> e.course.code)
                .toList();
    }

    List<String> studentsOf(Course course) {
        Objects.requireNonNull(course, "course");
        return entries.values().stream()
                .filter(e -> e.course == course)
                .map(e -> e.student.name)
                .toList();
    }

    public static void main(String[] args) {
        EnrollmentRegistryDemo registry =
                new EnrollmentRegistryDemo();
        Student an = new Student("An");
        Student binh = new Student("Bình");
        Course java = new Course("Java");
        Course sql = new Course("SQL");

        registry.enroll(an, java).setScore(9);
        registry.enroll(an, sql).setScore(8);
        registry.enroll(binh, java).setScore(7);
        registry.enroll(an, java);

        System.out.println("An=" + registry.coursesOf(an));
        System.out.println("Java=" + registry.studentsOf(java));
        System.out.println("score="
                + registry.find(an, java).orElseThrow().score());

        System.out.println("drop=" + registry.drop(an, java));
        System.out.println("An after=" + registry.coursesOf(an));
        System.out.println("Java after=" + registry.studentsOf(java));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnrollmentRegistryDemo.java
java EnrollmentRegistryDemo
~~~

**Stdout:**

~~~text
An=[Java, SQL]
Java=[An, Bình]
score=9
drop=true
An after=[SQL]
Java after=[Bình]
~~~

### One Source of Truth for Both Query Directions

- `Key(Student,Course)` identifies the pair; `computeIfAbsent` does not create a second Enrollment for an existing key pair.
- Re-enrolling `an,java` keeps the existing Enrollment object, including the score of 9.
- `coursesOf(an)` and `studentsOf(java)` both **read entries**; there are no two independent membership collections that must be synchronized.
- `drop` removes a pair. Afterward, **both views** no longer contain that pair.
- `LinkedHashMap` preserves the existing insertion order, keeping stdout in a stable order.

In the example, `Student` and `Course` do not override `equals/hashCode`; the `Key` record uses the equality of its components, so here each Student/Course object is distinguished by reference identity. For a real application that needs to manage multiple objects representing the same entity, you should use **stable studentId/courseId** or another appropriate identity contract.

## 15. Identity Issues and `equals/hashCode`

Two `Employee` objects with the same name `"An"` are not necessarily the same person. Two Java objects representing the same database row are also not necessarily **the same `==` reference**. Therefore, you must decide clearly what constitutes a duplicate link:

- Use **object identity** when all objects are managed centrally within the same aggregate and reference identity is the business identity in that scope.
- Use an **immutable ID** when the entity has a persistent identifier.
- Be careful with **equality based on mutable fields** for objects placed in a `HashSet` or used as `HashMap` keys.

An error-prone illustrative example:

~~~java
@Override
public int hashCode() {
    return mutableName.hashCode();
}
~~~

This is **an illustrative method snippet** in a hypothetical class with a `mutableName` field, not a standalone program. If `mutableName` changes after the object is inserted into a HashSet, the hash code can change and the set may fail to find/remove the object as expected.

For bidirectional relationships, that bug can cause `oldTeam.members.remove(member)` to fail and leave behind a stale reference. Do not include every relationship field in `equals/hashCode` just because a tool can auto-generate the code.

## 16. Avoiding Cycles in `toString` and Serialization

Bidirectional relationships create reference cycles:

~~~text
Employee -> Department -> List<Employee> -> Employee -> ...
~~~

If `Employee.toString()` prints `department.toString()`, while `Department.toString()` prints all `employees` using `toString()`, the two methods can recurse infinitely until throwing `StackOverflowError`.

Similarly, a serializer that does not know how to handle cycles can fail with an error or produce duplicated data. Strategies:

- Print the **ID/short name** of the other end instead of the entire object graph.
- Use a dedicated DTO for data output to clearly define traversal direction and depth.
- Use ID references, annotations, or cycle-handling configuration when supported by the serialization library.
- Do not automatically include every association in `equals/hashCode`.

**A reference cycle does not mean a memory leak.** The Java GC can reclaim a group of mutually referencing objects if they are no longer reachable from GC roots. Leaks are usually related to objects still held by a root, static collection, listener, or cache—not merely because A points to B and B points to A.

## 17. Removing a Link Differs from Deleting an Object

For example: when deleting a Team, you can choose to move all Members to another Team, unassign them to the `null` state, or reject deleting a Team that still has members.

With `Order`–`OrderLine` under composition, lifecycle policy may require an order line to belong to a single Order and be deleted along with the Order. However, **that is a specific business rule**, not something Java infers from Order containing `List<OrderLine>`.

Before writing `remove`, ask:

1. Is the relationship mandatory or nullable?
2. Does removing the link also delete the entity?
3. Are permission/status checks needed before removal?
4. If child objects exist, should they be detached, moved, or cascaded?
5. What state must the remaining ends reflect upon success?
6. If multiple objects are involved, how are removal order and mid-operation errors handled?

You should not expose `getChildren().clear()` as a general removal API if each child still holds a back-reference.

## 18. Concurrency: One Method Does Not Mean Atomic

Suppose a Member moves from A to B. The three operations:

~~~text
B adds Member
A removes Member
Member.team = B
~~~

are still separate steps. Another thread may observe the Member in both lists or see an un-updated reference. If two threads simultaneously move the same Member to different Teams, the result can race and break the invariant.

Approaches when concurrency is truly needed:

- A **shared aggregate/service lock** protecting the entire read–check–write operation.
- If locking multiple Teams, follow a consistent lock ordering to avoid deadlocks.
- Represent membership as an immutable snapshot and publish a new reference using a thread-safe mechanism.
- Move consistency involving persistent data into database transactions and constraints.

Merely adding `synchronized` to `Team.add` is not enough if `Team.remove` or another API modifies the same state under a different lock. The runnable examples in this lesson are **sequential models** and do not claim to be thread-safe.

## 19. ORM/JPA and the Owning Side Concept

With a database, a bidirectional relationship has two layers of consistency:

- **Object graph in Java:** references and collections on both sides must align.
- **Persistence state:** foreign keys/join tables must be written/committed within a transaction.

Some ORM/JPA mappings have an **owning side** and an **inverse side**. If the foreign key is actually managed from `Employee.department`, calling only `Department.employees.add(employee)` may **not be enough** to update the foreign key as intended, depending on the mapping and provider.

Domain helpers should synchronize **both sides of the object graph** according to the model's rules, while also ensuring the side ORM uses for persistence writes is set properly. Database transactions/foreign keys do not automatically fix Java object references that have gone out of sync in memory.

**Do not confuse ORM's owning side with composition/lifecycle ownership.** They are different concepts: one is a data mapping policy, while the other is a domain design decision.

## 20. Testing Relationships with a Test Matrix

| Case | Initial State | Action | Result to Verify |
| --- | --- | --- | --- |
| T1 | Member does not belong to a team | `A.add(m)` | A contains m and m.team=A |
| T2 | m belongs to A | `A.add(m)` | No duplicate |
| T3 | m belongs to A | `B.add(m)` | Removed from A, present in B, m.team=B |
| T4 | m belongs to B | `A.remove(m)` | B is unaffected |
| T5 | m belongs to B | `B.remove(m)` | Removed from B, m.team=null |
| T6 | m already left | Leave again | No change if contract is idempotent |
| T7 | Target team is full | Attempt move | Must keep old team |
| T8 | Caller receives list | Try removing element | Does not directly modify membership |
| T9 | A↔B and C↔D | A pairs with C | Both B and D are unpaired |
| T10 | Student already enrolled in Course | Re-enroll | Does not add duplicate Enrollment |
| T11 | Enrolled Student–Course | Drop | Both query directions lose the pair |
| T12 | Null/invalid argument | Call API | Rejected before updating |

You should check **both forward and reverse directions** of each state. If Team A no longer contains m, yet `m.team` still points to A, it fails the check. If returning a read-only `List` still allows element objects to be mutated to break the association, protection is also incomplete.

### A Plain JDK Test Snippet

Assume the test has access to observe a read-only API for member/team:

~~~java
if (member.team() != expectedTeam) {
    throw new AssertionError("member trỏ sai team");
}
if (!expectedTeam.members().contains(member)) {
    throw new AssertionError("team thiếu member");
}
~~~

This is **an illustrative snippet using a hypothetical API**, not a standalone file: `team()` and `members()` must be defined if reused. If writing tests with JUnit, you can use `assertSame`, `assertTrue`, and `assertEquals`, though that requires the JUnit dependency.

What matters is not the test framework, but **checking all invariants after every operation**, including after failures.

## 21. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only modifying `employee.department` | Old/new departments are not updated | One API updating both sides |
| Only adding to `department.employees` | Employee does not know its department | Synchronize the back-reference |
| Forgetting to remove from the old department | One Member in two departments | Transfer link with validation |
| Removing from the wrong department and clearing member's field | Breaks the valid relationship with another department | Check ownership before removing |
| Caller directly calls `clear()` on the collection | Removes from only one side | Do not return internal mutable collections |
| Repeatedly adding creates duplicates in a List | Wrong iteration, counts, and removals | Prevent duplicates via checks/Set/ID |
| Removing from source before validating destination | Failure loses the old link | Validate before modifying |
| Two update methods in two classes without delegation | Logic diverges over time | Single central algorithm |
| `equals/hashCode` depending on mutable fields | HashSet/HashMap fails to find the element | Stable ID or identity |
| `toString` printing full back-and-forth relationships | Infinite recursion | Print IDs, DTOs, limit traversal |
| Conflating link removal with entity deletion | Deletes data against business rules | Separate lifecycle rules |
| Treating a multi-assignment method as atomic | Threads observe inconsistent state | Synchronization/transactions |
| ORM updating one side and assuming synchronization | Object graph or FK may be wrong | Bidirectional helper, explicit mapping |
| Not testing moves, repeated removals, and errors | Bugs surface late | Test both before/after states |

## 22. Practice Exercises

**Exercise 1.** If `e.department=D`, what relationship must D's collection have with e? If e belongs to no department, what must the other collections look like?

**Exercise 2.** Why is calling `e.setDepartment(B)` alone insufficient when e is currently in A? State three changes.

**Exercise 3.** E belongs to B, but `remove(E)` is called on A. May `E.department=null` be set?

**Exercise 4.** Calling `add(E)` a second time on a Team that already contains E. What should the API avoid?

**Exercise 5.** If using `HashSet<Employee>`, why can changing a field involved in hash calculation while the object is inside the Set cause `remove` to fail?

**Exercise 6.** `Department.getEmployees()` returns the internal `ArrayList`. Which operations can a caller use to break the relationship? Propose safe methods.

**Exercise 7.** Two pairs A↔B and C↔D change into A↔C. Whom must B and D point to?

**Exercise 8.** If the relationship requires a Member to belong to **exactly one Team**, is a `leave()` method that sets null appropriate?

**Exercise 9.** Enrollment stores `score`. Why not place a single score on `Student` or `Course`?

**Exercise 10.** What limitation does a registry keyed by `Key(Student,Course)` using object identity have when the same student is loaded as two separate Java objects?

**Exercise 11.** When Team B is already full, why should you not remove Member from A before checking B?

**Exercise 12.** Does having `synchronized` on each individual `Team.add` guarantee that a move operation across A, B, and Member is atomic?

**Exercise 13.** ORM/JPA has an owning side. Why might modifying the inverse collection not be enough to persist the foreign key?

**Exercise 14.** If `toString` on both sides prints the entire opposite object, what error can occur?

### Reference Answers

1. D contains e exactly once and e points to D; if e.department=null, no department within the managed scope still holds e.
2. Remove e from A, add e to B, and update `e.department=B`.
3. No. A does not own the current link and must not break B's relationship.
4. Avoid creating duplicates; it can return false or leave state unchanged.
5. The Set's hash bucket was chosen from the initial hash; changing the hash value makes lookup/removal unreliable.
6. `clear`, `remove`, and `add` can modify one side; return a snapshot/read-only view/projection and provide a behavioral API.
7. B.peer=null, D.peer=null, A.peer=C, C.peer=A.
8. No, if the null state is forbidden; a direct transfer or another business operation is needed.
9. The score belongs to a **Student–Course pair**; Enrollment is the natural place to hold relationship data.
10. Two different instances can produce two different Keys even though they represent the same entity; use a stable ID/appropriate identity strategy.
11. B may reject it, and Member would lose its old relationship; validate the destination before making changes.
12. Not necessarily. You must protect the **entire** sequence across the objects and avoid lock orderings that cause deadlocks.
13. Because ORM relies on the mapping/owning side when determining persistence changes; you must synchronize the object graph and map it properly.
14. `StackOverflowError` due to non-terminating mutual recursion.

## 23. Bidirectional Relationship API Design Checklist

- Is it truly necessary to store **both sides**, or is one side/a registry enough?
- Is the multiplicity `0..1`, `1`, `0..*`, or `1..*`?
- Is leaving the team allowed? Are there transfer rules?
- Who owns the add/remove/move algorithm?
- Do public methods delegate to **a single source of execution**?
- Are duplicates checked and wrong-side removals prevented?
- Are all preconditions validated before mutating state?
- On failure, is the original state preserved according to the contract?
- Is a mutable list/set exposed through a getter?
- Do `equals/hashCode` depend on mutable fields?
- Does `toString` or serialization enter a cycle?
- Are link removal and object deletion mixed together?
- If multithreaded, what mechanism protects the entire invariant?
- If using an ORM, are the object graph and persistence mapping synchronized?
- Do tests verify **both sides** of add, remove, move, and error cases?

## 24. References

- [Java SE 17 — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): list operations, `List.copyOf`, `equals`.
- [Java SE 17 — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): uniqueness by `equals/hashCode`.
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): registry mapping keys to Enrollment.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull`.
- [Java SE 17 — Object.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): comparison and hashing rules.
- [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): returns a list that does not support modification.
- [Java Language Specification 17, §8](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): declarations of classes, fields, methods, and nested classes.
- [Java Language Specification 17, §17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): thread/lock issues and visibility of mutable state.

**Conclusion:** Bidirectional relationships allow convenient navigation, yet require **an invariant describing both directions**. Do not let callers modify individual references/collections piecemeal; use a behavioral API to **add, remove, or transfer links** in sync, handle duplicates and failures explicitly, protect mutable collections, and test both sides. For many-to-many relationships or relationships with their own attributes, using an association object/registry as the **single source of truth** often reduces duplicated state. When moving from a sequential model to multithreading or a database, properly scoped synchronization/transactions are required—you cannot rely solely on `private` or a multi-line method.
