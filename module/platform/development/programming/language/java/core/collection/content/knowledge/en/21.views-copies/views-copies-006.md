# Shallow Copy, Deep Copy, and Shared Element Objects

## 1. At Which Layer Is Independence Needed?

A program receives a `List` and creates another `List` to modify. It may want to avoid modifying the input list, yet still accidentally change the state of an element that both lists point to.

To understand the result, you need to look at data in layers: the reference variable, the collection object, then the element objects and the data nested inside them.

Three different actions:

| Action | New collection? | Are elements cloned? |
|---|---|---|
| Assigning `alias = source` | No | No; both variables point to the same collection |
| `new ArrayList<>(source)` | Has its own container structure | No; element references are copied |
| Creating a new collection and copying objects according to a chosen policy | Yes | Objects within the copy scope are recreated |

Shallow copy creates a new layer of objects while keeping the internal references according to the operation's policy. Deep copy recreates the mutable objects within the scope that needs independence.

There is no single right depth for every problem. Sometimes you only need to modify the containing list without modifying elements; sometimes you need an independently editable data copy; sometimes you must copy an entire graph that has multiple reference paths and cycles.

The complete programs in this article use Java 17 or later. The small data classes intentionally allow direct mutation so that each reference relationship can be clearly observed.

### 1.1. A Diagram for Reading Changes

After `new ArrayList<>(source)`, you can picture it as:

```text
source ──→ First List  ──┬──→ Person A
                         └──→ Person B

copy   ──→ Second List ──┬──→ Person A
                         └──→ Person B
```

The two `List` instances are different, but both arrows at the first position lead to the same `Person A`. Adding a slot to the second `List` does not automatically add it to the first `List`; modifying `Person A`'s name is seen by everything pointing to `Person A`.

After an appropriate deep copy, the `Person` objects whose state needs to be independent are also recreated. Immutable values such as `String` can continue to be shared without creating a path to mutate state through them.

## 2. References, Identity, and Kinds of Changes

### 2.1. Assigning a Reference Does Not Recreate the Object

A reference-type variable holds a reference value to an object or `null`. Assigning that value to another variable does not automatically run a constructor to clone the object.

Therefore, `alias = source` creates another path to the same collection. This is not yet a shallow copy of the collection; a new collection does not even exist.

The fundamentals of references and objects are described in [JLS 17, Section 4.3.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1).

### 2.2. `==` and `equals` Answer Two Different Questions

For object references, `==` checks whether they are the same object. `equals` checks equality according to that type's contract.

Two different `List` instances can be `equals` because they contain equal elements in order. Two different element objects can also be `equals` if the class defines equality by data.

Therefore, `equals` on the result does not prove deep or shallow copying. You need to inspect references at the right data layer and test the mutations that the copy is required to isolate.

Do not use `hashCode` or the default `toString` string as definitive proof of identity. The examples use `==`/`!=` comparisons for that.

### 2.3. Replacing a Reference Differs from Mutating the Referenced Object

With a shallow copy `List<Person>`:

- `copy.set(i, new Person(...))` replaces the reference in a slot of `copy`.
- `copy.add(...)` adds a slot in `copy`.
- `copy.get(i).name = ...` mutates the `Person` object retrieved from that slot.

The first two actions change the target collection. The third action can mutate the very `Person` shared by the source.

This distinction explains why "I only changed data in the copy" sometimes still changes the source data: you must identify which object layer is being modified.

### 2.4. `final` Does Not Make Everything Behind It Immutable

A `final` reference cannot be reassigned after initialization under language rules. It does not by itself prevent mutating the `List` contents or the state of the elements behind it.

Similarly, a `List` that disallows `add`/`remove`/`set` does not prove that the elements inside have no mutator methods or mutable fields. Collection mutability and element immutability are two separate conditions.

## 3. Program 1: New Collection, Elements Still Shared

Save to `ShallowCollectionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCollectionDemo {
    static final class Person {
        String name;

        Person(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Person> source = new ArrayList<>(
                List.of(new Person("Ada"), new Person("Bob")));
        List<Person> alias = source;
        List<Person> copy = new ArrayList<>(source);
        System.out.println("aliasSameList=" + (alias == source));
        System.out.println("copySameList=" + (copy == source));
        System.out.println("sameFirstElement=" + (copy.get(0) == source.get(0)));
        copy.get(0).name = "Ada2";
        System.out.println("sourceAfterElementEdit=" + source);
        copy.set(1, new Person("Cid"));
        System.out.println("sourceAfterCopySet=" + source);
        System.out.println("copyAfterSet=" + copy);
        copy.add(new Person("Dan"));
        System.out.println("sourceSize=" + source.size());
        System.out.println("copySize=" + copy.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ShallowCollectionDemo.java
java ShallowCollectionDemo
```

Stdout:

```text
aliasSameList=true
copySameList=false
sameFirstElement=true
sourceAfterElementEdit=[Ada2, Bob]
sourceAfterCopySet=[Ada2, Bob]
copyAfterSet=[Ada2, Cid]
sourceSize=2
copySize=3
```

### 3.1. Three Comparisons Clarify Three Layers of Relationships

`aliasSameList` is `true`: `alias` and `source` point to the same `List`. `copySameList` is `false`: the `ArrayList` constructor creates a different container structure.

`sameFirstElement` is `true`: the first element in both `List`s is still the same `Person`. There is no per-`Person` copying inside `new ArrayList<>(source)`.

### 3.2. Mutating a `Person` Differs from Replacing a `List` Slot

Changing the name through `copy.get(0)` makes `source` print `Ada2, Bob` because the first `Person` is shared.

`copy.set(1, new Person("Cid"))` only replaces the second slot of `copy`. `source` still has `Bob`, while `copy` has `Cid`. Adding `Dan` makes `copySize` become `3`, while `sourceSize` remains `2`.

From those results, we can say the copy is independent in container structure, but not yet independent in the state of every element.

The constructor accepting a `Collection` and the element-holding behavior of `ArrayList` are described in [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 4. Unmodifiable Views and Unmodifiable Copies

### 4.1. Two Ways to Block Modification Have Different Relationships to the Source

`Collections.unmodifiableList(source)` is a view that blocks modification through the wrapper. When `source` changes through another reference, reading the view still reads the source data.

`List.copyOf(source)` returns a `List` that does not allow adding, removing, or replacing elements. Subsequent changes to the source collection are not reflected as a live view on this result. However, the element objects themselves may still be shared.

Do not call both cases "immutable deep copies." They address collection mutability under two different contracts.

### 4.2. Program 2: Cannot `add`, Yet Can Still Mutate `Task`

Save to `UnmodifiableElementDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class UnmodifiableElementDemo {
    static final class Task {
        String title;

        Task(String title) {
            this.title = title;
        }
    }

    public static void main(String[] args) {
        Task task = new Task("draft");
        List<Task> source = new ArrayList<>(List.of(task));
        List<Task> view = Collections.unmodifiableList(source);
        List<Task> snapshot = List.copyOf(source);
        source.add(new Task("extra"));
        System.out.println("sourceSize=" + source.size());
        System.out.println("viewSize=" + view.size());
        System.out.println("snapshotSize=" + snapshot.size());
        snapshot.get(0).title = "done";
        System.out.println("sourceTitle=" + source.get(0).title);
        System.out.println("viewTitle=" + view.get(0).title);
        System.out.println("sameTask=" + (snapshot.get(0) == source.get(0)));
        try {
            snapshot.add(new Task("blocked"));
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotAdd=UnsupportedOperationException");
        }

        List<String> names = new ArrayList<>(List.of("A", "B"));
        List<String> savedNames = List.copyOf(names);
        names.set(0, "A2");
        System.out.println("savedNames=" + savedNames);
        System.out.println("currentNames=" + names);
        try {
            List.copyOf(Arrays.asList("A", null));
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullCopyOf=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableElementDemo.java
java UnmodifiableElementDemo
```

Stdout:

```text
sourceSize=2
viewSize=2
snapshotSize=1
sourceTitle=done
viewTitle=done
sameTask=true
snapshotAdd=UnsupportedOperationException
savedNames=[A, B]
currentNames=[A2, B]
nullCopyOf=NullPointerException
```

### 4.3. Source Structure and Snapshot Differ

After `source.add(extra)`, both `source` and `view` have size `2`; `snapshot` still has size `1`.

`snapshot.add` is rejected. But `snapshot.get(0).title = "done"` does not call a structural mutation method on the `List`: it mutates the returned `Task`. `source` and `view` both read title `done`, and `sameTask` is `true`.

Having no exception here is expected: a `List`'s prohibition on `add`/`remove`/`set` is not an automatic protection layer for each object returned by `get`.

### 4.4. Immutable Elements Can Be Shared Safely

`savedNames` keeps `A, B` when `names` replaces its first slot with `A2`. `String` is immutable; `names.set` does not mutate the `String` object `"A"`, it replaces the reference inside `names`.

In a model that only needs an unmodifiable `List` and immutable `String` elements, there is no need to create a new `String` just to guarantee nobody mutates the old `String`'s contents.

`List.copyOf` does not allow `null` elements, so the test with `null` throws `NullPointerException`. In addition, the API may reuse an already-unmodifiable `List`; do not rely on `==` to promise that every `copyOf` call always produces a brand-new `List` instance.

References: [List.copyOf — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Collections.unmodifiableList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).


## 5. Deep Copy Requires Knowing the Structure and Data Scope

### 5.1. Creating a New Element Object May Still Not Be Enough

Suppose `Task` has a `title` of type `String` and `tags` of type `List<String>`. Creating another `Task` and assigning `tags = other.tags` still makes both `Task` instances share the `tags` list.

You can draw the layers like this:

```text
Original Task ──→ tags List ──→ Strings
New Task      ──→ tags List ──→ Strings
                  ↑ same List if only the tags field is assigned
```

If you want the two `Task` instances to edit their `tags` lists independently, you must create a new `tags` `List`. Because the elements in `tags` are immutable `String`s, you can continue sharing the `String`s under this example's policy.

If you change it to `List<MutableTag>`, creating a separate `List` still does not isolate `MutableTag`. The copy scope must be evaluated further according to the actual data types.

### 5.2. A Copy Constructor Is Only as Deep as Its Implementation

Java does not automatically require a constructor accepting an object of the same type to be a deep copy. The name "copy constructor" is an API design convention; the constructor body decides which references continue to be shared.

A method named `copy`, `duplicate`, or `clone` also needs a clear contract: which layers are copied, which elements are kept, whether `null` is allowed, and whether the result is mutable.

In the next example, the constructor taking a `Task` intentionally shallow-copies the fields. `independentCopy` creates a separate `tags` `List` to satisfy this small model's independence requirement. Both paths are placed side by side for observation, not as a recommendation for a business API to have ambiguous copy behavior.

## 6. Program 3: New `Task`, Yet the Inner List Can Still Be Shared

Save to `NestedObjectCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedObjectCopyDemo {
    static final class Task {
        String title;
        List<String> tags;

        Task(String title, List<String> tags) {
            this.title = title;
            this.tags = tags;
        }

        Task(Task other) {
            this.title = other.title;
            this.tags = other.tags;
        }

        static Task independentCopy(Task source) {
            return new Task(source.title, new ArrayList<>(source.tags));
        }
    }

    public static void main(String[] args) {
        Task original = new Task("report", new ArrayList<>(List.of("urgent")));
        Task fieldCopy = new Task(original);
        Task independent = Task.independentCopy(original);
        System.out.println("differentTask=" + (fieldCopy != original));
        System.out.println("fieldCopySharesTags=" + (fieldCopy.tags == original.tags));
        System.out.println("independentSharesTags="
                + (independent.tags == original.tags));
        fieldCopy.tags.add("shared");
        System.out.println("originalTagsAfterFieldCopyEdit=" + original.tags);
        System.out.println("independentTagsBeforeEdit=" + independent.tags);
        independent.tags.add("local");
        independent.title = "copy-report";
        System.out.println("originalTagsAfterIndependentEdit=" + original.tags);
        System.out.println("independentTags=" + independent.tags);
        System.out.println("originalTitle=" + original.title);
        System.out.println("independentTitle=" + independent.title);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NestedObjectCopyDemo.java
java NestedObjectCopyDemo
```

Stdout:

```text
differentTask=true
fieldCopySharesTags=true
independentSharesTags=false
originalTagsAfterFieldCopyEdit=[urgent, shared]
independentTagsBeforeEdit=[urgent]
originalTagsAfterIndependentEdit=[urgent, shared]
independentTags=[urgent, local]
originalTitle=report
independentTitle=copy-report
```

### 6.1. `Task` Identity and `tags` Identity Are Checked Separately

`differentTask` is `true`, so `fieldCopy` and `original` are two different `Task` objects. Yet `fieldCopySharesTags` is also `true`: the two `tags` fields point to the same `List`.

`independentSharesTags` is `false` because `independentCopy` creates a different `ArrayList` for `tags`.

Checking only that the new `Task` differs from the old `Task` is not enough. You must inspect down to the state layer that the independence requirement actually needs to protect.

### 6.2. Modifying `tags` Through `fieldCopy` Changes the Source

`fieldCopy.tags.add("shared")` mutates the shared `tags` `List`. `originalTagsAfterFieldCopyEdit` is `urgent, shared`.

`independent` was created before that operation, so `independentTagsBeforeEdit` only has `urgent`. After `independent.tags.add("local")`, the independent copy's tags are `urgent, local`; `original` remains `urgent, shared`.

### 6.3. Sharing a `String` Does Not Mean Sharing the Field Variable

`title` is assigned the same `String` reference when creating the copy. However, `independent.title = "copy-report"` only changes `independent`'s `title` field; it does not reassign `original`'s field. `originalTitle` remains `report`.

The `String`'s contents are not mutated by that assignment. This is a case where immutable objects can be shared while two data copies remain independent for the allowed mutations of the model.

`independentCopy` assumes `source` and `source.tags` are non-null. If a business API needs to accept `null` or other element types, that policy must be added explicitly.

## 7. When Data Is a Graph Rather Than a Simple Tree

### 7.1. One Object Can Be Referenced Multiple Times

A `List` can contain the same object at two positions. Two different elements can also point to the same `Address`, sublist, or shared node.

If every encounter with a reference creates an independent new copy, sharing relationships in the result will be broken. For example, two people originally referencing one address might become two separate `Address` objects after copying, changing the model's meaning.

That is not always forbidden in every domain, but it must be a deliberate policy. When the requirement is to preserve the reference shape of the graph, one source object must correspond to one target object within the same copy pass.

### 7.2. Graphs Can Have Cycles

`root` can point to `child`, while `child` points back to `root`. A recursive algorithm that merely "creates a new node and copies all children" without remembering already-seen objects will keep looping.

You need a map from source objects to already-created target objects:

1. If the source is `null`, handle it according to the `null` policy.
2. If the source is already in the map, reuse the target copy.
3. If not yet present, create the target object and record it in the map immediately.
4. Only then copy the child reference paths.

Recording before the recursive step is what allows a cyclic reference to find the target object currently under construction.

### 7.3. The Memo Table Must Distinguish Identity from `equals`

Two different nodes can be `equals` because they have the same data. When copying to preserve reference structure, you must not merge two distinct source objects into one target node just because they are `equals`.

`IdentityHashMap` compares keys by reference identity rather than `equals`. It fits the memo table in this example. That is a specialized purpose, not a reason to replace every business `HashMap` with `IdentityHashMap`.

Reference: [IdentityHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

### 7.4. Policy of the Graph Example

The next model copies `Node` objects and new `links` `List`s, preserving edge order, duplicate edges, and cycles in the resulting graph. `String name` is shared due to immutability.

The `Node` class defines a simple `equals` based on `name` to intentionally create two nodes that are equal in data yet distinct in identity. The copy map must still keep them separate. This is a model illustrating the difference between `equals` and identity, not a general rule for choosing business identifiers for every `Node`.

## 8. Program 4: Preserving Shared Parts and Cycles in a New Graph

Save to `GraphCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphCopyDemo {
    static final class Node {
        String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node
                    && Objects.equals(name, ((Node) other).name);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(name);
        }
    }

    static Node copy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }
        Node result = new Node(source.name);
        seen.put(source, result);
        for (Node link : source.links) {
            result.links.add(copy(link, seen));
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node shared = new Node("leaf");
        Node equalButDistinct = new Node("leaf");
        root.links.add(shared);
        root.links.add(shared);
        root.links.add(equalButDistinct);
        shared.links.add(root);

        Node copied = copy(root);
        System.out.println("sourceLeavesEqual=" + shared.equals(equalButDistinct));
        System.out.println("newRoot=" + (copied != root));
        System.out.println("newLeaf=" + (copied.links.get(0) != shared));
        System.out.println("sharedLinkPreserved="
                + (copied.links.get(0) == copied.links.get(1)));
        System.out.println("distinctEqualNodesPreserved="
                + (copied.links.get(0) != copied.links.get(2)));
        System.out.println("cyclePreserved="
                + (copied.links.get(0).links.get(0) == copied));
        copied.links.get(0).name = "copy-leaf";
        System.out.println("originalLeafName=" + shared.name);
        System.out.println("copiedLeafName=" + copied.links.get(0).name);
        System.out.println("copiedOtherLeafName=" + copied.links.get(2).name);
        System.out.println("nullCopy=" + copy(null));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
```

Stdout:

```text
sourceLeavesEqual=true
newRoot=true
newLeaf=true
sharedLinkPreserved=true
distinctEqualNodesPreserved=true
cyclePreserved=true
originalLeafName=leaf
copiedLeafName=copy-leaf
copiedOtherLeafName=leaf
nullCopy=null
```

### 8.1. Three Edges, Yet Only Two Distinct Source Leaf Nodes

`root.links` contains `shared` twice and then `equalButDistinct`. Both leaf nodes have the same `name`, so `sourceLeavesEqual` is `true`, yet they are two distinct objects.

`shared` also points back to `root`. We do not print the whole graph with a recursive `toString`; the example checks the required relationships using `==`/`!=` to avoid depending on cycle-formatting logic.

### 8.2. New Target Nodes, Shared Parts Preserved in the Target Graph

`newRoot` and `newLeaf` are both `true`. The target graph does not reuse those mutable `Node` objects from the source.

`sharedLinkPreserved` is `true`: the first two edges in the copy still lead to the same target `Node`. `distinctEqualNodesPreserved` is also `true`: the third edge leads to a different target `Node`, even though the two source nodes are `equals`.

If you used a memo table that merges by `equals`, the two leaf nodes would risk being wrongly merged. `IdentityHashMap` enforces the policy of one source identity corresponding to one target identity.

### 8.3. Cycles Are Preserved Without Pointing Back to the Source

`cyclePreserved` is `true` because the target leaf node points back to `copied`, not to the source `root`. Calling `seen.put` before traversing `links` enables the algorithm to achieve this.

After renaming the first target leaf node to `copy-leaf`, `originalLeafName` remains `leaf`. The third target leaf node also remains `leaf`, proving that the two separate target nodes were not merged by name.

`nullCopy` is `null` per the policy of the `copy` method in the example.

### 8.4. Scope of the Algorithm Is Not Arbitrary `Object`s

The algorithm specifically knows `Node`'s `name` and `links` fields. If `Node` gains another mutable payload, that payload must be brought into the copy policy; the current code does not automatically discover and copy every new field.

Each call to `copy(root)` creates a new memo table. If you copy multiple roots and need to preserve sharing relationships across those roots, you must design a shared copy context for the whole pass rather than creating a separate table per root by default.

Recursion with a memo table handles cycles, yet a very deep chain of nodes can still exceed the call stack capacity. When the data requires it, you can design a traversal using an explicit worklist; that is an implementation decision specific to the model.


## 9. `clone` Does Not Automatically Mean Deep Copy

### 9.1. `Object.clone` Copies Fields by Their Held Values

`Object.clone` copies fields as if by assignment. Primitive fields have their primitive values copied; reference fields have their reference values copied. The objects that reference fields point to are not automatically cloned along with them.

Therefore, `super.clone` is usually only a shallow-copy step. If a class needs those mutable fields to be independent, the implementation must still handle them according to the chosen contract.

`Cloneable` is a marker interface related to permission to use the `Object.clone` mechanism. It does not declare a `clone` method and does not automatically generate a `public` deep-copy method for the class.

References: [Object.clone — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [Cloneable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).

### 9.2. Arrays Also Have Multiple Reference Layers

Cloning an `int[]` creates a new array holding numeric values, so changing a slot in the target array does not change the source slot.

Cloning a `StringBuilder[]` creates a new outer array, yet the `StringBuilder` elements can still be the same objects. Calling `append` on an element through the target array still mutates the object used by the source.

Even an `int[][]` is an array containing references to inner `int[]` arrays. Cloning the outer array does not automatically recreate each inner array. You must examine each layer, rather than seeing `int` and concluding there are no internal references.

### 9.3. `ArrayList.clone` Also Does Not Clone Elements

`ArrayList` documents `clone` as a shallow copy: a new `List` does not mean every element inside is new. When writing readable code against the `List` interface, the constructor accepting a `Collection` usually expresses copying the container structure clearly without guessing about `clone`.

What matters is still the contract, not merely choosing between the `new` keyword and a method named `clone`. A custom constructor can also reassign old references; a custom copy method can also create multiple layers of new objects.

The specific contract of `ArrayList.clone` is stated in [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 10. Program 5: `clone` on Fields and Arrays

Save to `CloneFieldsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CloneFieldsDemo {
    static final class Box implements Cloneable {
        int quantity;
        List<String> tags;

        Box(int quantity, List<String> tags) {
            this.quantity = quantity;
            this.tags = tags;
        }

        @Override
        public Box clone() {
            try {
                return (Box) super.clone();
            } catch (CloneNotSupportedException impossible) {
                throw new AssertionError(impossible);
            }
        }

        Box independentCopy() {
            return new Box(quantity, new ArrayList<>(tags));
        }
    }

    public static void main(String[] args) {
        Box original = new Box(3, new ArrayList<>(List.of("base")));
        Box shallow = original.clone();
        Box independent = original.independentCopy();
        System.out.println("newBox=" + (shallow != original));
        System.out.println("cloneSharesTags=" + (shallow.tags == original.tags));
        shallow.quantity = 7;
        shallow.tags.add("via-clone");
        System.out.println("originalQuantity=" + original.quantity);
        System.out.println("cloneQuantity=" + shallow.quantity);
        System.out.println("originalTags=" + original.tags);
        System.out.println("independentTagsBeforeEdit=" + independent.tags);
        independent.tags.add("local");
        System.out.println("originalTagsAfterIndependentEdit=" + original.tags);

        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;
        System.out.println("originalNumbers=" + Arrays.toString(numbers));
        StringBuilder[] builders = {new StringBuilder("x")};
        StringBuilder[] builderCopy = builders.clone();
        builderCopy[0].append("!");
        System.out.println("sharedArrayElement=" + builders[0]);
        int[][] grid = {{1, 2}};
        int[][] gridCopy = grid.clone();
        gridCopy[0][0] = 9;
        System.out.println("sharedInnerArray=" + grid[0][0]);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CloneFieldsDemo.java
java CloneFieldsDemo
```

Stdout:

```text
newBox=true
cloneSharesTags=true
originalQuantity=3
cloneQuantity=7
originalTags=[base, via-clone]
independentTagsBeforeEdit=[base]
originalTagsAfterIndependentEdit=[base, via-clone]
originalNumbers=[1, 2]
sharedArrayElement=x!
sharedInnerArray=9
```

### 10.1. New `Box`, Yet `tags` Is Still Shared

`Box` implements `clone` by calling `super.clone`. `newBox` is `true`, yet `cloneSharesTags` is also `true`.

`shallow.quantity = 7` changes the `int` field of the target `Box`; `originalQuantity` remains `3`. `shallow.tags.add("via-clone")`, however, mutates the shared `tags` `List`, so `originalTags` becomes `base, via-clone`.

`independentCopy` created a separate `Box` and `ArrayList` for `tags` before this change. `independentTagsBeforeEdit` only has `base`. Adding `local` to that copy does not add it to `original.tags`.

In this model, `tags` holds immutable `String`s, so creating a separate `List` is enough for the scope of independence demonstrated. If `tags` held mutable objects, you would need to examine those elements further.

### 10.2. `CloneNotSupportedException` Must Not Be Used to Mask Other Errors

`Box` already `implements Cloneable`, so the example treats a refusal from `super.clone` as an abnormal failure and turns it into `AssertionError`. Do not use this `catch` as a way to handle general business data errors.

The class itself declares `public clone` and returns `Box`. Merely writing `implements Cloneable` without designing a suitable calling API does not solve all copying concerns on its own.

### 10.3. Three Array Results Reflect Three Kinds of Container Layers

`numberCopy[0]` is changed to `9`, while `originalNumbers` remains `[1, 2]`.

`builderCopy[0]` still points to the same first `StringBuilder`, so `sharedArrayElement` is `x!` after `append`.

`gridCopy[0]` is still the same inner `int[]` array as `grid[0]`, so changing a cell in the inner array makes `sharedInnerArray` become `9`. If you want all rows of a matrix to be independent, you must recreate the row arrays according to an appropriate policy; cloning the outer layer is not enough.

## 11. Designing a Verifiable Copy Contract

### 11.1. Choose the Scope of Independence Before Writing Code

A copy API should be able to answer:

- Is the outer object created anew?
- Do nested collections get their own containers?
- Which mutable element objects must be recreated?
- Which immutable objects continue to be shared?
- Must sharing relationships and cycles in the source be preserved in the target graph?
- How are `null` sources, `null` elements, and `null` fields handled?
- Does the result allow modifying the collection and its elements?

Do not call a result a deep copy just because there are many `new` expressions. Evaluate it against the state paths that can be mutated within the business scope.

### 11.2. Defensive Copying at Data Ownership Boundaries

If a class does not want callers to mutate internal data through an input `List`, it can store an appropriate copy upon receiving the data. If it does not want callers to mutate data through a getter, the returned result also needs a suitable policy.

Copying only the `List` layer protects container membership against external `add`/`remove`/`set`. If mutable elements are still shared, callers can still mutate them. To isolate that state as well, you must copy the elements, switch to an immutable value model, or explicitly document the sharing relationship.

An unmodifiable `List` containing immutable elements usually allows safe data sharing under the model's allowed operations. There is no need to recreate every object just to increase the number of copied layers.

### 11.3. `List`, `Set`, and `Map` Have Additional Container Contracts

When changing container structures during copying, preserve the properties callers rely on:

| Data type | What to decide beyond creating a new object |
|---|---|
| `List` | Order, duplicate elements, `null`, mutability |
| `List` of `List` | Whether a new outer `List` is enough, or inner `List`s also need to be new |
| Reference array | Whether each element object is copied |
| `Set` | Equality relation, uniqueness, order if any |
| `Map` | Which keys and values are mutable, order, `Comparator` if any |
| Object graph | Shared edges, cycles, objects outside the copy scope |

For example, deep-copying only a `Map`'s values while still sharing mutable keys may fail data-isolation requirements. If you create a new `TreeMap` and drop its `Comparator` policy, the result may change ordering or key-acceptance rules.

Do not mutate attributes used in `equals`/`hashCode` of an object while it is still serving as a key in a hash map or an element in a hash set and expect the container to reorganize itself. Copy policy does not replace the contracts for using those collections.

### 11.4. There Is No Simple `deepCopy(Object)` That Knows Every Meaning

An object may hold an open file, connection, thread, cache, or shared service. "Clone everything" does not tell you whether external resources should be shared, reopened, or excluded from the copy.

For domain data with known types, a copy constructor/factory or a converter with a specific contract usually makes the scope easier to read and verify. If you choose a mechanism based on serialization, JSON, or a library, you must still read that mechanism's contract and verify types, reference relationships, cycles, and which parts of the data are preserved.

Do not treat a single successful conversion as default proof that every property of the graph was copied properly.

### 11.5. Copying Does Not Automatically Create an Atomic Snapshot Under Concurrency

In the examples, the source is not modified elsewhere during copying. That condition keeps the result deterministic and easy to verify.

A loop recreating elements from a mutating source does not automatically observe the entire state at a single point in time. You need an appropriate source access contract or separate coordination if the domain requires a consistent snapshot.

Similarly, a completed copy does not automatically become thread-safe if multiple places later mutate it concurrently. Copy depth and access coordination are two distinct decisions.

## 12. Cost and How to Verify Independence

### 12.1. Cost Depends on How Many Objects Must Be Recreated

Shallow-copying a `List` of `n` elements collects `n` references into a new container structure. The work also depends on how the source supports traversal, but it does not automatically include the cost of copying every element's entire state.

For the `Node` graph in the example and a memo table with expected constant-time lookup, copying visits the nodes and edges to be processed, corresponding to expected `O(V + E)` work. It also needs memory for the memo table and the target graph; recursion also uses call stack space proportional to traversal depth.

If an element holds large data, the cost of recreating that element must be accounted for separately. Do not choose deep copying out of habit when the requirement is only to replace the outer `List` structure.

### 12.2. Test Along Every Mutation Path

A good test does not only use `equals` between source and target. Check:

1. The identity of the outer object and the elements required to be distinct.
2. The identity of immutable parts allowed to be shared, if meaningful.
3. Whether `add`/`remove`/`set` on the target collection affects the source.
4. Whether mutating target element state affects the source.
5. Where nested `List`s or objects are still shared.
6. Whether shared edges and cycles are preserved according to policy.
7. Whether two equal source objects with distinct identities are mistakenly merged.
8. Whether `null` and empty collections are handled according to contract.

Test the reverse direction too—mutating the source and reading the target—if bidirectional independence is required. A matching result right after copying is not enough to prove that subsequent mutations are properly isolated.

## 13. Common Pitfalls

| Conclusion or approach | Why it is wrong | How to verify or adjust |
|---|---|---|
| `alias = source` copies the `List` | Only adds another reference to the same `List` | Check `alias == source` |
| `new ArrayList<>(source)` recreates every element | It copies the container structure and references | Check element identity and test mutating state |
| If outer objects differ, all data differs | Nested fields may still share the same references | Check each mutable layer that needs independence |
| `List.copyOf` makes elements immutable | Only blocks `List` mutation and ignores later source structure changes | Check mutability of each element |
| An `unmodifiable` wrapper is a data copy | The wrapper still backs onto the source | Distinguish views from copy results |
| `final List` means the `List` contents cannot change | `final` blocks reference reassignment, not object mutation | Design mutability permissions and immutability separately |
| `equals` between source and target proves deep copy | `equals` checks type equality, not all reference sharing | Use `==`/`!=` at the relevant layers and test mutations |
| `clone` is always a deep copy | `Object.clone` copies fields by their held values | Read the class contract, handle mutable fields when needed |
| Cloning a 2D array makes every row new | The outer array holds references to inner arrays | Check identity of the row arrays |
| Recursive copying without memoizing nodes | Can loop on cycles or break sharing relationships | Use a memo context per graph policy |
| Using `equals` to merge nodes in an identity-preserving copy | Two distinct sources that are `equals` can be merged | Memoize by identity when that is required |
| Creating a new inner `List` while forgetting mutable elements inside | Only adds one layer of independence | Define copy boundaries by data type |
| `List.copyOf` with `null` elements | The API rejects `null` | Choose a `null` policy and suitable construction method |
| Once copied, it is concurrency-safe | The copy can still be mutated concurrently by multiple callers | Design access coordination separately |

## 14. Self-Check and Practice

### 14.1. Questions and Answers

1. **Why does adding an element to a shallow copy not change the source's size, yet changing an element's name can change the source?** The new `List` structure is independent, while the element objects can still be shared.
2. **Is `copy.set` replacing a new `Person` the same as `copy.get(i).name = ...`?** No. `set` replaces the reference in the target `List`; mutating `name` affects the referenced `Person`.
3. **Does a `Task(Task other)` constructor deep-copy by default?** No. The constructor body determines how each field is copied.
4. **Do we need to clone a new `String` to prevent someone from mutating the `String`'s contents?** No. `String` is immutable; it can be shared according to the model's requirements.
5. **Why can a `Task` inside `List.copyOf` still be seen changing?** The target collection disallows structural modification, yet it can still hold the same mutable `Task` reference.
6. **Must a deep copy break all sharing within the copy?** No. If the requirement is to preserve the graph, edges leading to the same source node must lead to the same target node, while mutable target nodes are separated from the source.
7. **Why must a node be recorded in the map before copying its children?** So that a returning reference path can find the target object being constructed, avoiding infinite recursion.
8. **Why does `IdentityHashMap` fit the memo table in the example?** It distinguishes object identity and does not merge two sources merely because of `equals`.
9. **Does `Object.clone` automatically clone all reference fields?** No. Field contents are copied as in assignment.
10. **Can an `int[][]` clone still share inner arrays?** Yes. The new outer array still holds the old row array references.
11. **Does an unmodifiable `List` containing immutable elements always need to deep-copy every element?** You do not need to recreate immutable parts just to prevent state mutation through them; you must still consider other contract requirements.
12. **Is deep copy enough to get a consistent snapshot of a source being modified by another thread?** No. You also need a contract or mechanism coordinating how the source is read.

### 14.2. Exercise: Three Data Layers

Create a `List<List<StringBuilder>>` with two rows. Write three ways to produce a result: only assigning the reference, creating a new outer `List`, and creating both new row `List`s and new `StringBuilder`s.

For each approach, test three operations: adding a row to the result; adding a `StringBuilder` to a row; appending to a `StringBuilder`. Predict which operations still affect the source.

The third approach should clearly express the policy if the same `StringBuilder` appears multiple times: should it keep a single corresponding target copy or deliberately split into independent copies?

### 14.3. Exercise: Verifying an `Order` Copy Contract

Design an `Order` with a `String` `id` and a mutable `List<Line>`, where each `Line` has a quantity and a description. Write the copy contract clearly before implementing.

If the requirement is to edit quantities in the copy without affecting the source, you need a new `List` and new `Line`s. If the description is a `String`, the `String` can be shared. If a `Line` in turn references another mutable object, decide whether it falls within the scope requiring independence.

Test replacing the `List`, replacing a `Line`, and mutating a field inside a `Line` as separate actions.

### 14.4. Exercise: Two Equal Nodes and a Cycle

Based on `GraphCopyDemo`, create two identity-distinct `Node`s with the same `name` and have both link to a shared `Node`. Add a link back to the root.

Verify that the result has two separate nodes for the two separate sources, one shared target node for the shared source, and a cycle in the result pointing back to the target node. Then mutate one target `Node` and prove the source is unchanged.

Do not use `equals` as the sole check; identity relationships are precisely what must be verified.

## 15. References and Verification Scope

- [JLS 17, Objects and Reference Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1): fundamentals of references and objects; the same chapter describes `final` variables.
- [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): constructor accepting a `Collection` and shallow `clone` that does not copy elements.
- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `copyOf`, result mutability, mutable elements, and `null` conditions.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `unmodifiableList` wrapper.
- [Object — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): field-copying mechanism of `clone`.
- [Cloneable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface that does not itself provide a `public clone` method.
- [IdentityHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): identity comparison and its use in object graph transformations.

The five complete programs were compiled with `javac --release 17 -encoding UTF-8` and run on Corretto JDK 17.0.15, producing the exact recorded stdout. Identity results are printed using `==`/`!=`; the graph example directly tests shared edges and cycles. The custom copy methods in this article apply only to the declared models and are not presented as a general-purpose copier for arbitrary `Object`s.
