# Protecting Data When Receiving Parameters or Returning Collections from an API

## 1. Collections Crossing an API Carry Modification Rights

A class holds a list of members and requires the list to always have at least one person. The constructor checks that the input is non-empty and stores the received List. A few lines later, the caller clears the List using the variable they still hold. The list inside the class becomes empty as well, even though no member-removal method of the class was ever called.

The problem lies in shared references. In Java, passing a reference variable into a method creates a copy of the **reference value**, not a copy of the object it points to. Two variables can both lead to the same List. Similarly, returning a reference to an internal List can give the recipient a way to modify the object's state.

In this lesson, an API is the surface of classes and methods that Java components use to work with one another. When a collection crosses that surface, the contract needs to answer:

- Does the method only read the data while running, or keep it for later use?
- Can the recipient modify the collection, or only read it?
- Do changes on one side appear on the other?
- Are the elements inside immutable data, or objects that can still be modified?

**Protecting data** here means maintaining the rules the owner has committed to, while granting the right level of access to the consumer. An unmodifiable collection addresses container modification rights; a copy addresses one level of reference dependency; element objects may require a separate decision.

The lesson starts with a reference-exposure case, builds a safe intake pattern, and then compares three return policies. After that, it handles element objects and nested collections. The goal is to choose the right contract and verify it, rather than adding wrappers everywhere without knowing what is being protected.

Prerequisites are object references, `private final` fields, List/Set/Map operations, and basic exceptions. All programs below are standalone and run on Java 17; save each program under the exact filename listed before the code.

## 2. Three Concepts for Reading Data Boundaries Correctly

### 2.1. Multiple Paths to the Same Object

The situation where multiple references point to the same object is commonly called aliasing. If that object allows modification, one path can modify data that another path is observing.

A parameter variable is local to the method, but the object received is not necessarily private to it. Reassigning the parameter variable does not reassign the caller's variable; calling `clear` on the List object through the parameter variable still affects the shared List.

A `private` field prevents external code from accessing the field directly by name. It does not revoke references to the object that external code already holds. A `final` field prevents reassigning the field reference after initialization under language rules. It does not prohibit mutating methods on the referenced object.

### 2.2. Rules That Always Hold for an Object

A condition such as "the member list is non-empty" is an object invariant: something the class intends to keep true at all valid observation points. If a getter lets the recipient call `clear` on the real List, the recipient can break that condition without going through the class's logic.

Therefore, protecting collections is directly tied to encapsulation. Making a field private only controls the access path by name; designing parameters, return values, and elements is what determines whether unintended state-modification paths remain.

### 2.3. Three Independent Levels

| Level to Consider | Check Question | Example |
| --- | --- | --- |
| Container | Can external code still add/remove/replace elements or internal mappings? | Getter returning the internal ArrayList directly |
| Relationship to source | If the source changes, does the already-received result change with it? | Unmodifiable view vs. snapshot |
| Element state | Can retrieved objects still mutate shared state? | Unmodifiable List containing objects with setters |

A solution may satisfy one level without satisfying another. Stating clearly which levels need protection helps avoid both under-protection and unnecessary copying.

## 3. Experiment: Exposing References on Both Input and Output

This program intentionally keeps a flawed design with respect to the "non-empty" requirement. Save it as `UnsafeReferenceDemo.java` to observe the cause; do not use this Roster class as a design template.

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeReferenceDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> input) {
            if (input.isEmpty()) {
                throw new IllegalArgumentException("At least one member");
            }
            members = input;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An", "Binh"));
        Roster roster = new Roster(input);
        System.out.println("initial=" + roster.members());

        input.clear();
        System.out.println("afterInputClear=" + roster.members());

        roster.members().add("Injected");
        System.out.println("inputAfterGetterAdd=" + input);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnsafeReferenceDemo.java
java UnsafeReferenceDemo
```

Stdout:

```text
initial=[An, Binh]
afterInputClear=[]
inputAfterGetterAdd=[Injected]
```

At construction time, the input is valid and the getter shows two members. After `input.clear()`, the class was never consulted, yet its internal data is now empty. The condition checked in the constructor no longer holds because the class continues to depend on a List that the caller has the right to modify.

Next, `roster.members().add("Injected")` goes in the opposite direction. The getter returns a reference to the same List, so adding through the returned value also appears in the `input` variable. Both directions share the same root cause: failing to establish an ownership boundary.

The `final` keyword in the program was never violated. The `members` field still points to the exact original List; only the contents of the List changed. This is why you must check actual behavior rather than looking at a field declaration and concluding the object is immutable.

Changing only the getter to an unmodifiable wrapper still leaves the `input.clear()` path open. Copying the input into a private ArrayList while continuing to return that ArrayList directly still leaves the getter modification path open. Both boundaries must be addressed.

## 4. Accepting Parameters: Keep the Data You Validated

If a class needs to retain an independent list for long-term use, a clear workflow is:

1. Create private data at the level that needs protection.
2. Validate business rules on the exact data that will be retained.
3. Assign the field only after preparation and validation have succeeded.
4. Expose outputs that do not reopen modification paths outside the contract.

For a List of String names, `List.copyOf(input)` fits the first step because the result does not support container modification and does not track subsequent additions, removals, or element-reference replacements in the input. String is immutable, so sharing the String instances does not open any path to mutate the names.

Validating on the captured copy avoids the pattern of "validating an external object, then storing data that may differ from what was validated." However, capturing does not automatically lock a source that another thread is modifying. The intake contract still needs coordination rules if concurrent modification can occur.

This is a boundary-design principle, not a rule to always copy every parameter. A method that only computes during the call may not need to retain a copy when the contract permits direct reading. An operation designed to modify a List passed in by the caller can also be valid, provided that behavior is documented. Copying is needed when the dependency level and modification rights of the input data do not meet the receiving object's requirements.

Oracle's guidelines clearly distinguish copying mutable data on input and output, and emphasize using the protected copy for validation logic: [Secure Coding Guidelines, Section 6 on Mutability](https://www.oracle.com/java/technologies/javase/seccodeguide.html#6).

## 5. Experiment: Receiving a List of Names and Exposing an Unmodifiable Result

Save as `DefensiveRosterDemo.java`. This class publishes its policy: the list is non-null, contains no nulls, has at least one name, and no name is blank; order and duplicate counts are preserved as provided.

```java
import java.util.ArrayList;
import java.util.List;

public class DefensiveRosterDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> input) {
            List<String> captured = List.copyOf(input);
            if (captured.isEmpty()) {
                throw new IllegalArgumentException("At least one member");
            }
            if (captured.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Blank member");
            }
            members = captured;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An", "Binh"));
        Roster roster = new Roster(input);
        input.clear();
        System.out.println("afterInputClear=" + roster.members());

        try {
            roster.members().clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("getterClear=UnsupportedOperationException");
        }
        System.out.println("afterGetterAttempt=" + roster.members());

        try {
            new Roster(List.of());
        } catch (IllegalArgumentException e) {
            System.out.println("emptyInput=IllegalArgumentException");
        }

        try {
            new Roster(List.of(" "));
        } catch (IllegalArgumentException e) {
            System.out.println("blankInput=IllegalArgumentException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add(null);
        try {
            new Roster(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullMember=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DefensiveRosterDemo.java
java DefensiveRosterDemo
```

Stdout:

```text
afterInputClear=[An, Binh]
getterClear=UnsupportedOperationException
afterGetterAttempt=[An, Binh]
emptyInput=IllegalArgumentException
blankInput=IllegalArgumentException
nullMember=NullPointerException
```

The constructor retains `captured`, not `input`. When the caller clears the source after construction, the member list remains as it was at intake. When the recipient calls `clear` through the getter, the returned object rejects that operation.

Returning the `members` field directly is safe in this design because the field already holds a sealed List and the elements are Strings. There is no need to allocate another ArrayList on every read to protect the same modification boundary. This approach does not rely on the factory method creating a new object in every case; it relies on the contract of the data being returned.

Invalid cases are separated by responsibility:

- Having no members and blank names violate conditions set by the class.
- Null elements violate the contract of the factory method used during intake.
- An empty source List is technically valid input for the factory method, but invalid for this Roster.

Exception types and messages should be consistent with the actual API. For example, do not silently turn an empty list into a default list, do not filter out invalid names, and do not alter names by trimming whitespace. If normalization is needed, it must be specified and published as a separate step in the contract.

Read the capture contract and null rules at [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)). This method has existed since Java 10; the programs in this lesson use JDK 17.

## 6. Returning Collections: Choose One Explainable Contract

When returning a collection, there are at least three useful contracts. Not every contract fits every object.

| Return Contract | Can the recipient modify the container? | If the owner changes the source, what happens to an old result? | Implementation for List of String |
| --- | --- | --- | --- |
| Unmodifiable live view | Not through the view | May see changes from the source | `Collections.unmodifiableList(internal)` |
| Unmodifiable snapshot | No | Does not track container edits to the source after capture | `List.copyOf(internal)` |
| Private modifiable copy | Yes, on the private copy | Does not track container changes in the source | `new ArrayList<>(internal)` |

An unmodifiable view can fit a screen that needs to observe data currently managed by the owner. A snapshot fits a result that must stay stable during a processing pass. A modifiable copy fits when the recipient needs to filter, sort, or append to its own data without updating the owner.

The term "unmodifiable" should make clear that it refers to modification rights through the returned object. It does not by itself promise that every read yields the same data. A view can forbid `add` while still showing new items added by the owner through a valid method.

If the owner needs to enforce business rules when data changes, it should allow changes through meaningful methods such as `addTask`, `removeMember`, or `replacePermissions`. Those methods can check conditions before mutating. Returning an internal List directly and asking callers "not to make invalid edits" gives up the opportunity to enforce those rules in the responsible object itself.

Save as `ReturnPolicyDemo.java`. The program uses String to separate the container modification story from the element state story.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class ReturnPolicyDemo {
    static final class TaskBoard {
        private final List<String> tasks = new ArrayList<>();

        void addTask(String task) {
            Objects.requireNonNull(task, "task");
            if (task.isBlank()) {
                throw new IllegalArgumentException("Blank task");
            }
            tasks.add(task);
        }

        List<String> readView() {
            return Collections.unmodifiableList(tasks);
        }

        List<String> readSnapshot() {
            return List.copyOf(tasks);
        }

        List<String> editableCopy() {
            return new ArrayList<>(tasks);
        }
    }

    public static void main(String[] args) {
        TaskBoard board = new TaskBoard();
        board.addTask("learn");
        List<String> view = board.readView();
        List<String> snapshot = board.readSnapshot();
        List<String> editable = board.editableCopy();

        board.addTask("practice");
        editable.add("local-only");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("editable=" + editable);
        System.out.println("board=" + board.readSnapshot());

        try {
            view.add("blocked");
        } catch (UnsupportedOperationException e) {
            System.out.println("viewAdd=UnsupportedOperationException");
        }

        try {
            snapshot.add("blocked");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshotAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReturnPolicyDemo.java
java ReturnPolicyDemo
```

Stdout:

```text
view=[learn, practice]
snapshot=[learn]
editable=[learn, local-only]
board=[learn, practice]
viewAdd=UnsupportedOperationException
snapshotAdd=UnsupportedOperationException
```

After calling `addTask("practice")`, `view` sees two items because it tracks the internal List. `snapshot` still has one item. `editable` also does not receive the owner's new item, while allowing `local-only` to be added to its private copy.

The `board` line confirms that modifying the private copy does not update the TaskBoard object. The two exception cases confirm that both the view and the snapshot block additions through the returned object, even though their relationship to the source differs.

The names `readView`, `readSnapshot`, and `editableCopy` in the example intentionally express the policy. A real API may choose different naming conventions, but documentation should not force recipients to test mutations or inspect a debugger to learn their rights.

The pass-through reading behavior of the wrapper is described at [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)). The distinction between unmodifiable collections, views, and element data is presented in the [Collection contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 7. Interface Types Decouple Implementations, Not Mutability

Accepting a parameter as `List<String>` instead of requiring `ArrayList<String>` lets an API express the need for a list without tying itself to one implementation. Even so, List still has mutating methods; the type signature does not by itself promise actual mutability or ownership transfer.

Choose the interface according to the data to be represented:

- Need position, order, and duplicate counts: List.
- Need a set of distinct values: Set.
- Need key–value associations: Map.
- Only need to read a group of elements without requiring positions: you can accept Collection or Iterable if it fits the usage.

Do not switch from List to Set just to protect data. Deduplication can lose information, such as how many times a product appeared in the input data. Likewise, do not pick a factory method that does not guarantee order and still promise the order of a specialized source structure.

A wildcard type like `List<? extends Item>` can restrict adding a specific Item at compile time. It is not an unmodifiable List type: operations such as `clear` remain part of the API, and retrieved Items can still have mutating methods. Type bounds and object modification rights are two different concerns.

Returning Iterable instead of List can narrow the method surface that the recipient sees. However, if the underlying object is still the mutable internal collection, changing the declared return type does not create a copy or revoke references. Do not use "the caller cannot see `add` in this signature" as proof of data protection.

For an API that only needs to return a count, a computed value, or a small piece of information, you can return that result directly instead of exposing the entire internal collection. Designing around actual usage often reduces the number of access paths you need to manage.

## 8. Protecting the Outer List Does Not Protect Element Objects

Suppose a report contains line items. The List cannot be modified, but each line is still an object with `setQuantity`. The recipient may not be able to remove a line, yet can still change the quantity on a retrieved line. If that line is also used by another object, the change appears in both places.

There are three options depending on the contract:

1. Use immutable element objects so state can be shared safely.
2. Copy elements into separate objects if the recipient is allowed to modify its own copy.
3. Convert the data into a value representation containing only the information to be exposed.

The third option often fits read-only results. It also avoids exposing mutating methods or unnecessary data from internal business objects.

Save as `ElementBoundaryDemo.java`. `Line` is a mutable object; `LineSnapshot` holds only a String SKU and an int quantity. `ShallowReport` intentionally protects only the outer List; `Report` creates private value objects before sealing the list.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ElementBoundaryDemo {
    static final class Line {
        private final String sku;
        private int quantity;

        Line(String sku, int quantity) {
            this.sku = Objects.requireNonNull(sku, "sku");
            setQuantity(quantity);
        }

        String sku() {
            return sku;
        }

        int quantity() {
            return quantity;
        }

        void setQuantity(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Positive quantity required");
            }
            this.quantity = quantity;
        }
    }

    record LineSnapshot(String sku, int quantity) {
        LineSnapshot {
            Objects.requireNonNull(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Positive quantity required");
            }
        }
    }

    static final class ShallowReport {
        private final List<Line> lines;

        ShallowReport(List<Line> input) {
            lines = List.copyOf(input);
        }

        List<Line> lines() {
            return lines;
        }
    }

    static final class Report {
        private final List<LineSnapshot> lines;

        Report(List<Line> input) {
            List<LineSnapshot> captured = new ArrayList<>();
            for (Line line : input) {
                Objects.requireNonNull(line, "line");
                captured.add(new LineSnapshot(line.sku(), line.quantity()));
            }
            lines = List.copyOf(captured);
        }

        List<LineSnapshot> lines() {
            return lines;
        }
    }

    public static void main(String[] args) {
        Line original = new Line("P1", 2);
        List<Line> input = new ArrayList<>(List.of(original));
        ShallowReport shallow = new ShallowReport(input);
        Report report = new Report(input);

        original.setQuantity(7);
        System.out.println("shallowQuantity=" + shallow.lines().get(0).quantity());
        System.out.println("reportQuantity=" + report.lines().get(0).quantity());

        shallow.lines().get(0).setQuantity(9);
        System.out.println("originalQuantity=" + original.quantity());
        System.out.println("reportAfterEdit=" + report.lines().get(0).quantity());

        input.clear();
        System.out.println("reportSize=" + report.lines().size());
        try {
            report.lines().clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("reportClear=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ElementBoundaryDemo.java
java ElementBoundaryDemo
```

Stdout:

```text
shallowQuantity=7
reportQuantity=2
originalQuantity=9
reportAfterEdit=2
reportSize=1
reportClear=UnsupportedOperationException
```

After updating `original` from quantity 2 to 7, the shallow-copied report reads 7. The report converted to `LineSnapshot` still holds 2. When editing the line retrieved from `shallow.lines()` to 9, the `original` object changes as well. Once again, no outer List modification was performed.

`Report` extracts the needed values and constructs separate `LineSnapshot` objects. Clearing the input List afterward does not remove lines from the report; attempting to clear through the output List is blocked. Both directions are protected at both the container level and the state level the report needs to preserve.

A record in the example is concise syntax for a group of values. Its components are stored in final fields and have accessor methods such as `sku()` and `quantity()`. In this specific case, String is immutable and int is a primitive value, so there are no mutable sub-objects to expose.

Do not generalize that every record is automatically deeply immutable. If a record component is a mutable List, the record still needs to handle input/output List boundaries. A final field does not replace a policy for the referenced object. You can check record field and accessor rules in [JLS 17, Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).

The value-creation approach here fits the `Line` class at hand. It does not automatically copy an arbitrary object graph, preserve all identity relationships between elements, or guarantee atomic reads of multiple fields being mutated by another thread. Those requirements must be designed separately if the model has them.

## 9. Nested Collections Require Checking Every Mutable Layer

A `Map<String, Set<String>>` configuration has at least two collection layers:

- The Map determines which role is associated with which Set.
- The Set determines which permissions belong to that role.

Capturing or wrapping only the outer Map does not prevent adding permissions to a Set that is still shared. Wrapping only the Set while keeping the external Map source does not prevent replacing the Set associated with a role. A two-layer protection goal must handle both paths.

Save as `NestedPolicyDemo.java`. The example's contract is to seal the role table and permission sets at intake time and forbid recipient edits through the output; a role absent from the table returns an empty set. Keys and permissions are Strings, so there is no deeper mutable value-object layer.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class NestedPolicyDemo {
    static final class AccessPolicy {
        private final Map<String, Set<String>> roles;

        AccessPolicy(Map<String, Set<String>> input) {
            Objects.requireNonNull(input, "input");
            Map<String, Set<String>> captured = new HashMap<>();
            input.forEach((role, permissions) -> {
                Objects.requireNonNull(role, "role");
                if (role.isBlank()) {
                    throw new IllegalArgumentException("Blank role");
                }
                Set<String> values = Set.copyOf(permissions);
                if (values.stream().anyMatch(String::isBlank)) {
                    throw new IllegalArgumentException("Blank permission");
                }
                captured.put(role, values);
            });
            roles = Map.copyOf(captured);
        }

        Set<String> permissionsFor(String role) {
            Objects.requireNonNull(role, "role");
            return roles.getOrDefault(role, Set.of());
        }

        Map<String, Set<String>> snapshot() {
            return roles;
        }
    }

    public static void main(String[] args) {
        Set<String> permissions = new HashSet<>(Set.of("read", "write"));
        Map<String, Set<String>> input = new HashMap<>();
        input.put("editor", permissions);
        AccessPolicy policy = new AccessPolicy(input);

        permissions.add("delete");
        input.clear();
        System.out.println("editorForDisplay="
                + new TreeSet<>(policy.permissionsFor("editor")));
        System.out.println("missingEmpty="
                + policy.permissionsFor("missing").isEmpty());

        try {
            policy.permissionsFor("editor").clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("permissionClear=UnsupportedOperationException");
        }

        try {
            policy.snapshot().put("admin", Set.of("all"));
        } catch (UnsupportedOperationException e) {
            System.out.println("mapPut=UnsupportedOperationException");
        }

        System.out.println("editorAfterAttempts="
                + new TreeSet<>(policy.permissionsFor("editor")));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NestedPolicyDemo.java
java NestedPolicyDemo
```

Stdout:

```text
editorForDisplay=[read, write]
missingEmpty=true
permissionClear=UnsupportedOperationException
mapPut=UnsupportedOperationException
editorAfterAttempts=[read, write]
```

In the constructor, each permission Set is captured before being placed into the temporary Map. Once all input has been prepared and validated, the temporary Map is captured into the `roles` field. The field only receives the completed result; a half-populated Map is never exposed.

After creating the policy, the program performs two different kinds of input mutation: adding `delete` to the old Set and clearing the source Map. The result still has the two permissions `read` and `write` for `editor`. Attempts to clear the permission set or add a mapping through the outputs are both blocked.

Printing uses `TreeSet` to get a stable display order, not to implicitly promise that a sealed Set iterates alphabetically. When the result has a real ordering requirement, an ordered contract must be chosen and documented in the design.

The temporary Map and sealed Sets provide sufficient protection for the data shape in the example. If the value type changes to `Set<Permission>` with mutable `Permission` objects, mutability must also be evaluated at that layer. Do not apply a "wrap twice" formula while ignoring the actual element type.

Details of the factory methods used in the example: [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) and [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)). Both reject null per their respective contracts and do not provide deep object copying.

## 10. Document the Contract So Callers Do Not Have to Guess

An API returning `List<T>` still has much to state beyond type `T`. The contract can be presented in Javadoc or method documentation, using verifiable statements.

| Aspect | Question to Answer | Example of Clear Phrasing |
| --- | --- | --- |
| Input retention | Read only during the call, or retained afterward? | The class stores a snapshot of the received names |
| Source mutability | Can the caller still use and modify the source after the call? | Modifying the source container after completion does not change the stored list |
| Result mutability | Does the result allow adding/removing/replacing elements? | The result does not support List modification operations |
| Relation to current state | Do old results reflect later updates from the owner? | The result is a snapshot from the time of retrieval |
| Elements | Shared objects or separate value data? | The result contains LineSnapshot instances independent of input Line objects |
| Invalid data | How are null, empty, or invalid elements handled? | Nulls are rejected; an empty list violates a business precondition |
| Order and duplicates | Are position and occurrence counts preserved? | The List preserves input order and allows duplicate names |
| Concurrent access | Can the caller mutate the source while the method reads? | Concurrent modification must follow the stated coordination mechanism |

For `Roster` in Section 5, a complete description could be: "Accepts a non-null List of names containing no nulls, non-empty, and with no blank names. The class preserves the order and occurrence counts in the List at intake time. Container changes to the input List after the constructor completes do not alter the stored list. The returned read result does not allow List modification."

For `TaskBoard.readView()`, you must add that recipients may see data updated later by `TaskBoard`. If replaced with a promise of a "fixed result," an implementation using a live wrapper would violate the contract even though every `add` call through the view is blocked.

There is no need to publish the implementation class name if that is not a meaningful part of the API. Promising "always returns ArrayList" neither fully describes modification rights nor avoids coupling users to a potentially unnecessary choice. Documenting capabilities, ordering, independence level, and error policy is usually more useful.

Contracts also help evaluate version changes. Changing a getter from a modifiable copy to an unmodifiable result can cause caller code to start throwing exceptions. Changing from a snapshot to a view can cause old results to reflect new state. Do not treat such changes as mere internal optimizations if the documented behavior changes.

## 11. Keep Valid Mutation Paths on the Owner Side

When a class manages changing data, it does not need to make the entire object immutable. It can keep a mutable internal collection, while exposing only operations that satisfy the class's rules.

For example, instead of returning the real List for callers to add members themselves, the class can provide `addMember(name)`. Instead of letting callers remove arbitrarily, the class can check beforehand whether a removal would leave the list empty. Read outputs can then be chosen as a view or a snapshot depending on requirements.

For an operation that takes an entire collection to replace state, prepare the new data in a local variable first. Complete validation and the required protection level before replacing the held state. If invalid data appears at the last item, avoid leaving the object partially updated with earlier items unless the contract allows partial results.

You must also examine exit paths beyond getters:

- Returning `keySet`, `values`, or `entrySet` of an internal Map can expose views backed by the Map.
- Returning part of a List with `subList` can remain linked to the source List.
- Passing a collection or element object to an externally supplied callback also hands over a path to retain references.
- An iterator that supports removal can be a mutation path even when the API does not return a List directly.

The solution depends on each path's contract. If a path should only provide read access, expose a representation protected at the required level. If the recipient is allowed to make changes, route changes through owner-controlled operations or a private copy allowed to be modified.

For example, calling an external handler with an unmodifiable List containing `Line` objects that have setters still lets that handler retain and mutate `Line`. Do not limit your review to the `return` keyword; trace every place where an internal reference is handed to another component.

Do not transfer a mutable collection owned by another party directly into your own field and assume the other side will stop modifying it. If there is an ownership-transfer agreement, it must be explicit and maintainable. In ordinary Java code, reference semantics do not automatically invalidate variables that the transferring side still holds.

## 12. Limits of Copying and Costs to Consider

Copying protects the chosen level of independence; it does not replace all state-management mechanisms.

**On concurrent access:** A mutable source List is not automatically safe to read while another thread writes. The finished copy may no longer track the source, but the process of reading the data must still follow the source's synchronization contract. Do not rely on occasionally seeing or not seeing `ConcurrentModificationException` to conclude that reading is correct. The Collection contract leaves synchronization policy to each implementation.

**On multiple related fields:** Converting a mutable object into value data may read multiple fields at different moments. If fields are required to reflect a single consistent business state, the owner must provide a way to obtain a consistent state or coordinate mutations. An element-copying loop by itself does not establish this guarantee.

**On depth:** One-level copying does not guarantee independence of an entire object graph. For shared relationships, reference cycles, or resources with their own lifecycle, an appropriate policy is needed. Do not recursively "copy everything" without deciding which parts are values, which are resources, and which must preserve identity relationships.

**On cost:** Creating a copy can require traversing data, allocating memory, and holding extra references. If the state is already an appropriate sealed structure, you can return it directly instead of building a copy on every getter call. If the result needs to change over time, consider creating snapshots at meaningful points and reusing them within what the contract allows.

Do not remove a protection step just because allocations show up in a profiler before understanding ownership requirements. Nor should you copy repeatedly across every intermediate layer when layers already share an appropriate immutable value. Optimize based on data-usage paths and measurements, while preserving the behaviors promised by the API.

The examples in this lesson run single-threaded so each mutation path can be observed clearly. They demonstrate data relationships for the stated operations, not a complete synchronization design.

## 13. Verify by Behavior Rather Than Identity

A good test attempts to mutate through every path that the contract says is blocked or isolated. Do not check contents only right after the constructor, because at that moment even a reference-exposing design can produce the expected output.

| Test Path | How to Trigger Mutation | What to Observe per Contract |
| --- | --- | --- |
| Input after intake | Add/remove/replace element references in the source | Private sealed data remains unchanged |
| Unmodifiable result | Call a mutating operation that has an actual effect | Rejected; owner data remains valid |
| Modifiable copy | Modify the returned copy | Changes belong only to the private copy |
| Live view | Update through an owner method | View shows the new data per contract |
| Mutable elements | Call setter through source or result reference | Sharing/isolation level matches documentation |
| Nested collections | Mutate each layer using retained references | Layers promised to be protected remain unchanged |
| Invalid data | Null, empty, or invalid item | Clear error; no half-updated state exposed |

Do not use `result != input` as the sole proof of independence. Two different collection objects can still share mutable elements; two factory-method results also do not necessarily need distinct identities to satisfy the contract.

When testing a List, order and occurrence counts are usually part of the data to compare. For a Set or Map that does not promise ordering, compare elements or mappings; do not assert on printed string order. The `NestedPolicyDemo` experiment intentionally sorts only when printing so stdout stays deterministic.

When testing modification rights, choose an operation that clearly requests a change, such as adding a new element or removing an existing item. Do not infer rules for all collections from no-op calls such as adding an empty collection, because the general contract leaves room for exception differences in those cases.

Finally, check state after a rejected mutation or after invalid input. The important question is not only "was an exception thrown?" but also "does the object still uphold all the rules it committed to?"

## 14. Design Practice and Self-Explanation

### Exercise 1: Notification Recipient List

A class receives a `List<String>` of recipients, retains it for repeated use, and requires it to be non-empty. The caller still wants to use the source List for other work.

State the intake and output policy. After creating the object, clear the source List and try clearing through the getter. Success criteria: the object still holds a valid list; the caller understands that modifying the source does not update the class, and the output has clear modification rights. You can use the intake pattern from `DefensiveRosterDemo` if elements remain String.

### Exercise 2: Report Allowing Private Processing

A method returns results so the recipient can sort and filter them locally, without updating the service's internal data.

Choose a modifiable copy, determine whether elements may be shared, and verify that removing an item from the result does not remove the internal item. If elements have setters and the recipient is also allowed to modify them on its private copy, copying only the container is not enough; you need to decide how to create private element data.

### Exercise 3: Interface for Observing New State

A component wants to observe new items added by the owner without being able to add or remove items itself.

Design an unmodifiable view and documentation that clearly states its relationship to the source. Success criteria: updates made through the owner's methods appear in the view; modifications through the view are blocked; if multiple threads are involved, coordination mechanisms are not overlooked. Do not describe this result as a fixed snapshot.

### Exercise 4: Map Containing Lists of Addresses

The source is `Map<String, List<Address>>`; `Address` is a mutable object. The result must be a report that does not change when the source or an external `Address` changes.

Sketch in words the three layers that need protection: the Map mappings, the Lists, and the `Address` state. Success criteria: propose immutable address data or private value data, seal the corresponding Lists, and then seal the Map. Do not treat a single `Map.copyOf` as sufficient for all three layers.

### Exercise 5: Method That Replaces the Entire Configuration

An object currently holds a valid configuration. A replacement method receives a new collection whose last item violates a rule.

Describe the order of preparation, validation, and update so the old configuration is not partially modified when an error occurs. State where protection of the new data finishes before publication. If the operation has concurrency requirements, separate that consistent-update requirement from merely creating an unmodifiable collection.

### Self-Check Questions

- **Why is `private final` not enough?** `private` controls field access by name, and `final` controls field reassignment; neither prohibits mutating an object that is still referenced elsewhere.
- **Does copying the input and returning an internal `ArrayList` directly solve both directions?** No. Recipients can still mutate state through the output.
- **Does wrapping the input List as unmodifiable and storing the wrapper seal the data?** No. If the underlying source can still be modified, the wrapper can continue to observe changes.
- **When is it appropriate to return the retained collection directly?** When the collection and element-sharing level already satisfy the output contract, such as `Roster` holding a sealed List of Strings.
- **Does changing the return type to `Iterable` automatically create a copy?** No. Declared type and reference relationships are two different things.
- **What matters more than a fixed wrapping or copying formula?** Identifying who is allowed to modify which layer of data, at what time, and then verifying those exact mutation paths.
