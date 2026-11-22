# clone, Serialization, and the Limits of Each Copying Approach

## 1. What Can Differ When You Want "Another Copy"?

A list holds shopping carts. Each cart in turn holds a list of products and shipping details. When creating a copy of the list to try out edits, having a new `List` object is not enough to guarantee that the original carts remain unchanged.

The starting point of this lesson is the **object graph**:

- Each object is a node.
- Reference fields, collection elements, and map keys/values form the links.
- An existing variable only holds a reference to the entry node, often called the root of the graph.
- Two links can point to the same node; a chain of links can also loop back to a previously visited node.

Therefore, "copying" needs a clear scope:

| Level | What is new? | What is still shared? |
|---|---|---|
| Assigning a reference to another variable | Only another variable | The same original object |
| Shallow copy | The outer object or container structure | The objects referenced inside |
| Contract-based deep copy | The nodes specified to be separated in the graph | May still share immutable data, services, or objects designated as shared |
| Converting to another data model | The objects of the target model | Only retains the information defined by the conversion |

**`clone()` does not perform a deep copy by default. Serialization is also not a guarantee of independently cloning every existing state.** Each approach has its own rules and preconditions.

Before choosing, answer three questions: which operations on the copy are allowed to affect the source, which shared links must be preserved in the copy, and which state cannot or should not be carried over?

This lesson focuses on copying collections along with the graphs contained inside them, not on designing a general-purpose persistence protocol. The four complete programs use Java 17 or later and only the standard library. Results are printed using values and reference comparisons, avoiding reliance on object addresses or `HashMap` iteration order.

## 2. Object.clone() and Cloneable: The Basic Mechanism

### 2.1. Cloneable Is a Marker for Object.clone(), Not a General Copying API

`Object` declares the `clone()` method with `protected` access and return type `Object`. `Cloneable` is a marker interface that does not declare a `clone()` method.

This leads to two distinctions:

- A class that implements `Cloneable` without exposing a suitable method still provides no public `clone()` API to external callers.
- A variable of type `Cloneable` cannot rely on that interface alone to call `clone()` as a method defined in an interface contract.

By convention, a class that supports cloning overrides `clone()`, widens its access to `public` when it wants to expose it, and may use the class's specific return type.

If `Object.clone()` is executed on an object that does not implement `Cloneable`, it throws `CloneNotSupportedException`. This is a condition of the `Object.clone()` mechanism; a custom method named `clone` that does not use that mechanism may define a different policy. The [Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html) documentation clearly explains its marker role and the fact that the interface does not declare `clone()`.

### 2.2. Object.clone() Copies Fields Like Assignment

For `Object`'s implementation:

- Primitive values are copied into the corresponding fields.
- Reference field values are also copied, meaning the copy holds references to the same inner objects.
- Referenced objects are not automatically cloned recursively.
- Constructors and field initializers of the class are not run to recreate state as when using `new` normally.
- An instance field marked `transient` is still copied by the `clone` mechanism; `transient` has a different meaning in serialization.

Imagine an object with `int count` and `List<Item> items`. After `super.clone()`, `count` is an independent value on the new object, while `items` on both sides still points to the same list.

To create a deep copy with `clone`, the class must actively replace the references that need to be separated after `super.clone()`, while handling shared relationships and reference cycles according to its policy. [Object.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()) describes this field-by-field copy; it does not perform that recursive step for the class.

### 2.3. A New Object Does Not Imply equals or New Resources

By convention, `clone` typically produces an object with a different reference and the same runtime class as the source. However, do not infer all properties of the result from a single method name. Read the contract of the class itself.

There is also no general requirement that a clone must satisfy `equals` with the source. If a class has not overridden `equals()`, two objects with different references are usually not equal according to `Object.equals()`.

A reference to a database connection, I/O stream, or service does not become an independent resource simply because the object holding it is cloned. Copying external resources requires its own policy.

## 3. Cloning Collections and Arrays: Separating the Container, Sharing Elements

`ArrayList.clone()` creates a new `ArrayList` whose elements are still the old references. `HashMap.clone()` creates a new map without cloning the keys or values. This is a shallow copy at the container level.

The program below uses `Box` objects with a mutable `value` field. `Key` is a record holding only a `String` so that map checks are not complicated by keys changing their hash code.

File **CollectionCloneDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;

public class CollectionCloneDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    record Key(String id) {}

    @SuppressWarnings("unchecked")
    private static ArrayList<Box> cloneList(ArrayList<Box> source) {
        return (ArrayList<Box>) source.clone();
    }

    @SuppressWarnings("unchecked")
    private static HashMap<Key, Box> cloneMap(HashMap<Key, Box> source) {
        return (HashMap<Key, Box>) source.clone();
    }

    public static void main(String[] args) {
        ArrayList<Box> source = new ArrayList<>();
        source.add(new Box(10));
        ArrayList<Box> copy = cloneList(source);
        System.out.println("newList=" + (copy != source));
        System.out.println("sharedElement=" + (copy.get(0) == source.get(0)));

        copy.add(new Box(20));
        System.out.println("listSizes=" + source.size() + "," + copy.size());
        copy.get(0).value = 99;
        System.out.println("originalAfterElementEdit=" + source.get(0).value);
        copy.set(0, new Box(7));
        System.out.println("afterReplace=" +
                source.get(0).value + "," + copy.get(0).value);

        Key key = new Key("K");
        HashMap<Key, Box> map = new HashMap<>();
        map.put(key, new Box(50));
        HashMap<Key, Box> mapCopy = cloneMap(map);
        System.out.println("sharedKey=" +
                (mapCopy.keySet().iterator().next() == key));
        System.out.println("sharedValue=" + (mapCopy.get(key) == map.get(key)));
        mapCopy.get(key).value = 66;
        mapCopy.remove(key);
        System.out.println("mapSizes=" + map.size() + "," + mapCopy.size());
        System.out.println("originalMapValue=" + map.get(key).value);

        int[] numbers = {10, 20};
        int[] numbersCopy = numbers.clone();
        numbersCopy[0] = 90;
        System.out.println("primitiveArray=" + numbers[0] + "," + numbersCopy[0]);

        Box[] objects = {new Box(3)};
        Box[] objectsCopy = objects.clone();
        objectsCopy[0].value = 4;
        System.out.println("objectArrayShared=" + (objects[0] == objectsCopy[0]));
        System.out.println("objectArrayOriginal=" + objects[0].value);

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] matrixCopy = matrix.clone();
        matrixCopy[0][0] = 8;
        System.out.println("newOuterArray=" + (matrix != matrixCopy));
        System.out.println("sharedRow=" + (matrix[0] == matrixCopy[0]));
        System.out.println("matrixOriginal=" + matrix[0][0]);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionCloneDemo.java
java CollectionCloneDemo
```

Exact stdout:

```text
newList=true
sharedElement=true
listSizes=1,2
originalAfterElementEdit=99
afterReplace=99,7
sharedKey=true
sharedValue=true
mapSizes=1,0
originalMapValue=66
primitiveArray=10,90
objectArrayShared=true
objectArrayOriginal=4
newOuterArray=true
sharedRow=true
matrixOriginal=8
```

### 3.1. Adding, Replacing, and Mutating Elements Are Three Different Things

The two lists have separate structures, so `copy.add(...)` increases the size of the copy without adding to the source. However, `copy.get(0)` initially still points to the source's `Box`.

Therefore, `copy.get(0).value = 99` mutates the exact `Box` object held by both lists. Next, `copy.set(0, new Box(7))` only replaces the reference at one position in `copy`; it does not change the reference in `source`. The two sides now hold `99` and `7`.

In the map, `mapCopy.get(key).value = 66` mutates the shared value. `mapCopy.remove(key)` only removes the mapping from the copy. The source's mapping remains intact with the `Box` whose `value` is now `66`.

These results illustrate the exact shallow-copy contract of [ArrayList.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#clone()) and [HashMap.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html#clone()).

### 3.2. Primitive Arrays and Reference Arrays

Arrays support `clone`; the return type of `clone` on a specific array type is that array type itself. There is no need to cast `Object` to `int[]` or `Box[]` when calling it directly as shown in the example.

`int[]` holds `int` values, so `clone` creates a different array and modifying a number in the new array does not modify the old array.

`Box[]` holds references, so the new array still points to the old `Box` instances. `int[][]` is also an array holding references to `int[]` rows. Thus, `clone()` on `int[][]` only separates the outer array; the rows remain shared.

If a matrix genuinely consists of independent rows and you want to separate every row, you can copy each row according to your application's policy. But if multiple positions intentionally point to the same row, cloning each row independently will break that sharing relationship. Even a "two-dimensional array" requires understanding the graph shape.

### 3.3. Do Not Promote a Class's Clone Support into a Collection Guarantee

The `Collection`, `List`, `Set`, and `Map` interfaces do not provide a common public `clone()` method. A variable declared as `List` does not automatically have `clone` just because the runtime object might be an `ArrayList`.

A concrete class supporting `clone` also does not mean every view, wrapper, or factory return value has the same capability. Do not cast an unknown object to `ArrayList` just to use `clone`.

For ordinary structural copying needs, a constructor accepting a collection/map or an explicit copy factory is usually clearer to express. Their contracts must also be read accurately: creating a new container structure does not automatically deep-copy each element.

## 4. Deep Copying Must Preserve Relationships Between Objects

Suppose `root` has two links pointing to `child`, and `child` points back to `root`. There are two simultaneous requirements:

1. The copy must have its own `root` and `child` so they can be modified independently.
2. Both links on the new `root` must still point to the same new `child`; the back-link must point to the new `root`.

If you simply write a recursive function that "creates a `new` object whenever it encounters an object," it can loop infinitely on cycles or create multiple copies of the same node, losing the original relationships.

A mapping table of **source reference → created target reference** solves both problems. Use `IdentityHashMap` to identify the same object by `==`, rather than merging distinct objects just because `equals()` returns `true`.

### 4.1. Program Preserving Duplicate References and Reference Cycles

`Node` below has a public `clone` using `super.clone()` to demonstrate shallow copying. The `deepCopy()` method is a custom copy routine written specifically for the `Node` model; it does not use serialization and does not call `clone` on each node.

File **GraphCopyDemo.java**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class GraphCopyDemo {
    static final class Node implements Cloneable {
        String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        @Override
        public Node clone() {
            try {
                return (Node) super.clone();
            } catch (CloneNotSupportedException impossible) {
                throw new AssertionError(impossible);
            }
        }
    }

    private static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name);
        seen.put(source, target);
        for (Node link : source.links) {
            target.links.add(copy(link, seen));
        }
        return target;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node child = new Node("child");
        root.links.add(child);
        root.links.add(child);
        child.links.add(root);

        Node shallow = root.clone();
        System.out.println("shallowNewRoot=" + (shallow != root));
        System.out.println("shallowSharedList=" + (shallow.links == root.links));
        System.out.println("shallowCycleUsesOriginal=" +
                (shallow.links.get(0).links.get(0) == root));

        Node deep = deepCopy(root);
        Node copiedChild = deep.links.get(0);
        System.out.println("deepNewRoot=" + (deep != root));
        System.out.println("deepNewList=" + (deep.links != root.links));
        System.out.println("deepNewChild=" + (copiedChild != child));
        System.out.println("aliasPreserved=" +
                (deep.links.get(0) == deep.links.get(1)));
        System.out.println("cyclePreserved=" + (copiedChild.links.get(0) == deep));

        copiedChild.name = "child-copy";
        deep.links.add(null);
        System.out.println("names=" + child.name + "," + copiedChild.name);
        System.out.println("linkCounts=" + root.links.size() + "," + deep.links.size());
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
```

Exact stdout:

```text
shallowNewRoot=true
shallowSharedList=true
shallowCycleUsesOriginal=true
deepNewRoot=true
deepNewList=true
deepNewChild=true
aliasPreserved=true
cyclePreserved=true
names=child,child-copy
linkCounts=2,3
```

### 4.2. Registering the New Node Before Following Links

The `copy()` method performs four steps in strict order:

1. Return `null` if the source link is `null`.
2. If the source node is already in the `seen` map, return its corresponding target node.
3. Create the target node and put it into `seen` immediately.
4. Only then copy the source node's links.

The third step must come before recursion. When `child` points back to `root`, the map already knows which object the new `root` is; the method does not create `root` again and does not recurse infinitely.

The two links pointing to `child` also hit the same entry in `seen`, so `aliasPreserved` is `true`. This preserves the aliasing relationship within the new graph, rather than keeping a link back to the mutable object in the source.

[IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html) notes graph transformations and topology-preserving deep copies as a typical use case.

### 4.3. final Does Not Make a List Immutable

`Node.links` is `final`, meaning a different list cannot be assigned to that field after initialization under normal rules. The list's contents can still be added to, removed, or modified.

`super.clone()` copies the reference of this `final` field. `shallow.links` and `root.links` are therefore the same list. If you call `links.clear()` on a shallow clone intending to "clear before re-copying," you will also clear the source's list.

`deepCopy()` uses `new Node(...)`, so the constructor creates a separate list from the start. It does not have to use reflection tricks to reassign a `final` field on a clone.

This is one reason to choose an explicit copy constructor/factory when designing new classes: target object initialization and invariants are directly readable in code.

### 4.4. The Algorithm's Scope Must Be Explicit

`GraphCopyDemo` only knows the `Node` model consisting of a `String` name and `Node` links. It deliberately shares `String` because `String` is immutable. It is not a universal Java object copier, and it does not automatically handle OS resources, arbitrary subclasses, or any new fields added later.

If `Node` gains mutable properties, the designer must decide whether to copy, share, omit, or recompute them. If relationships across multiple roots need to be preserved, a single `seen` map must be shared for the entire group of roots being copied; creating a new map produces a separate copied graph.

For very deep graphs, recursion can overflow the call stack. An algorithm using an explicit queue/stack may be necessary when data scale demands it. Having a "seen map" solves cycles, not unbounded recursion depth.

## 5. Serialization: Encoding the Graph and Reconstructing It

Java Object Serialization uses `ObjectOutputStream` to write state into bytes and `ObjectInputStream` to read it back. When used for copying, the typical workflow is:

1. Write an object root into a byte buffer.
2. Create a new input stream from those bytes.
3. Read the reconstructed root and check the expected type.

This is copying through a **serialized representation contract**, not taking a raw snapshot of JVM memory.

### 5.1. Reference Tracking Within a Single Stream

For ordinary serializable objects, the output stream tracks objects it has already seen and assigns them internal handles. Upon encountering the same object again, it can write a reference to the existing handle instead of writing another independent copy.

When read back, this mechanism preserves multiple links pointing to the same object as well as cycles in ordinary graphs. It does not duplicate a node merely because two paths reach it.

The [Java Object Serialization Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html) specification describes how handles are used to recreate shared references and cycles. Exceptions caused by special types or object replacement mechanisms are examined in the limits section.

### 5.2. Serializable on the Root Object Is Not Enough

`Serializable` is also a marker interface. Under the default mechanism, non-`static` and non-`transient` instance fields of a serializable class participate in the written state. What gets written can be customized via a class's custom serialization hooks.

An `ArrayList` implementing `Serializable` does not make every arbitrary element inside it serializable. When the mechanism reaches an unsupported object that must be written, it can throw `NotSerializableException`. The same applies to keys, values, `Comparator`s, or configurations referenced by the graph.

Even a generic signature like `<T extends Serializable>` only checks the root type through the type system; it does not prove every node actually traversed is valid. You must understand the concrete model and handle runtime errors.

Marking a field `transient` excludes it from the default mechanism, but that is a decision to drop or reconstruct state, not a successful copy of that state.

## 6. Program: Copying a Graph and Observing Altered State

The following example has two `Node`s with a reference cycle and two duplicate links to `child`. It also includes:

- `cache` as a `transient` field with an initializer value.
- `global` as a `static` field.
- `inherited` belonging to `Base`, which does not implement `Serializable`.
- `policy` as an `enum`.
- `token` with `readResolve()` returning a shared object.

The program only reads bytes it just created in memory. The input stream filter restricts the classes and limits needed for this specific example; this is not a utility for accepting arbitrary external bytes.

File **SerializationCopyDemo.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class SerializationCopyDemo {
    static class Base {
        static int constructions;
        int inherited = 7;

        Base() {
            constructions++;
        }
    }

    enum Policy { STANDARD }

    static final class Token implements Serializable {
        private static final long serialVersionUID = 1L;
        static final Token INSTANCE = new Token();

        private Token() {}

        private Object readResolve() {
            return INSTANCE;
        }
    }

    static final class Node extends Base implements Serializable {
        private static final long serialVersionUID = 1L;
        static int constructions;
        static String global = "before";

        String name;
        List<Node> links = new ArrayList<>();
        transient String cache = "warm";
        Policy policy = Policy.STANDARD;
        Token token = Token.INSTANCE;

        Node(String name) {
            constructions++;
            this.name = name;
        }
    }

    private static byte[] serialize(Serializable source) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(source);
        }
        return buffer.toByteArray();
    }

    private static ObjectInputFilter.Status filter(ObjectInputFilter.FilterInfo info) {
        if (info.depth() > 20 || info.references() > 1000 ||
                info.arrayLength() > 1000 || info.streamBytes() > 1_000_000) {
            return ObjectInputFilter.Status.REJECTED;
        }
        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }
        if (type == Node.class || type == Token.class ||
                type == Policy.class || type == Enum.class ||
                type == ArrayList.class || type == Object[].class ||
                type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }
        return ObjectInputFilter.Status.REJECTED;
    }

    private static Node readLocalBytes(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in =
                new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(SerializationCopyDemo::filter);
            return Node.class.cast(in.readObject());
        }
    }

    public static void main(String[] args) throws Exception {
        Node root = new Node("root");
        Node child = new Node("child");
        root.links.add(child);
        root.links.add(child);
        child.links.add(root);
        root.inherited = 99;

        byte[] bytes = serialize(root);
        Base.constructions = 0;
        Node.constructions = 0;
        Node.global = "changed-after-write";
        Node copy = readLocalBytes(bytes);

        System.out.println("newRoot=" + (copy != root));
        System.out.println("newChild=" + (copy.links.get(0) != child));
        System.out.println("aliasPreserved=" +
                (copy.links.get(0) == copy.links.get(1)));
        System.out.println("cyclePreserved=" +
                (copy.links.get(0).links.get(0) == copy));
        System.out.println("cache=" + copy.cache);
        System.out.println("global=" + Node.global);
        System.out.println("inherited=" + copy.inherited);
        System.out.println("baseConstructors=" + Base.constructions);
        System.out.println("nodeConstructors=" + Node.constructions);
        System.out.println("sameEnum=" + (copy.policy == root.policy));
        System.out.println("sameResolvedToken=" + (copy.token == root.token));

        copy.links.get(0).name = "child-copy";
        System.out.println("names=" + child.name + "," + copy.links.get(0).name);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SerializationCopyDemo.java
java SerializationCopyDemo
```

Exact stdout:

```text
newRoot=true
newChild=true
aliasPreserved=true
cyclePreserved=true
cache=null
global=changed-after-write
inherited=7
baseConstructors=2
nodeConstructors=0
sameEnum=true
sameResolvedToken=true
names=child,child-copy
```

### 6.1. Ordinary Nodes Are Separated, Graph Relationships Are Preserved

`copy` is distinct from `root`; `child` inside `copy` is also distinct from the original `child`. Yet the two positions in `copy.links` both point to the same new `child`. The link from the new `child` points back to `copy` itself.

Editing the child's name in the copy does not modify the name in the source. This is the behavior that often leads people to use serialization as a deep-copy mechanism for models that already support it.

However, the program itself shows that you cannot conclude "all state is independent" merely from the fact that `root` and `child` were newly created.

### 6.2. transient and static Do Not Follow the Default Mechanism

`cache` is declared `transient` and has no custom restoration code. The value `"warm"` was initialized when calling the `Node` constructor in the original program, but `Node`'s initialization does not rerun as `new Node(...)` during this read. The deserialized `cache` is `null`.

If `cache` is needed after reading, it must be lazily recomputed or restored using an appropriate mechanism. Do not think of `transient` as "automatically resetting to the field initializer value."

`global` is `static`, belonging to the class in the JVM rather than to each `Node` instance. After changing it to `"changed-after-write"` and reading the bytes, it remains `"changed-after-write"`. The serialized data does not restore `"before"` to this `static` variable.

A memorable contrast: shallow `clone` copies even the values of `transient` instance fields; default serialization omits them. The `transient` keyword is not a universal directive for all copying mechanisms.

### 6.3. Non-Serializable Superclass State Is Reinitialized

`Base` does not implement `Serializable`. The state `inherited = 99` on `root` is not automatically written as part of `Node`'s state. When reconstructing the two `Node`s, `Base`'s no-arg constructor is invoked for each object, resetting `inherited` to `7` and incrementing `Base`'s counter to `2`.

The `Node` constructor does not run, so `Node`'s counter stays `0`. Read both lines together rather than generalizing that "deserialization calls no constructors."

For an ordinary `Serializable` class, the no-arg constructor of its first non-serializable superclass must be accessible under subclassing rules. Without this condition, reconstruction can fail. This contract is described in [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html).

### 6.4. readResolve and Enums Preserve Designated Shared Objects

`Token.readResolve()` returns `Token.INSTANCE`. The deserialized `token` field therefore points back to the existing singleton; `sameResolvedToken` is `true`.

`policy` is an `enum`. Within the same loaded enum type definition, deserializing an enum constant returns the exact corresponding constant, rather than creating an independent enum instance like an ordinary `Node`; `sameEnum` is also `true`.

Sharing immutable enums is usually desirable. However, if a class has a `readResolve()` returning a mutable singleton, the deserialized copy can continue sharing mutable state through that singleton.

Thus, the accurate conclusion is: serialization reconstructs the graph **according to the protocols of the participating classes**, including their replacement and sharing rules. It does not guarantee that "every reachable object has a different reference from the source."

## 7. Constructors, Invariants, and Customization Mechanisms

### 7.1. Do Not Treat Ordinary Constructors as Proof of Data Validation

A class having a constructor that validates values does not automatically mean ordinary `Serializable` deserialization will rerun that constructor. If an invariant must hold after reading, the class's serialization design must include appropriate validation/restoration steps.

A class can define `readObject()` to read state, check conditions, and reject invalid data, for example by throwing `InvalidObjectException`. Some designs use the serialization proxy pattern to reconstruct via a controlled initialization path.

Do not add `readObject` mechanically: read order, partially restored state, superclass relationships, and reference cycles must all be considered. For new application data copying needs, an explicit copy factory/constructor can be simpler than opening another object-construction path via serialization.

### 7.2. writeObject, writeReplace, and readResolve Change Copying Semantics

Classes can write/read custom state via `writeObject()`/`readObject()`, substitute the object being written via `writeReplace()`, or substitute the read result via `readResolve()`.

This means:

- Not every `transient` field is necessarily lost; a class may write or reconstruct related information with custom code.
- Not every non-`transient` field is copied as a direct field-by-field mirror; the serialized representation can be customized.
- Not every deserialized object has reference relationships like a pure duplicate of the source.
- Code from participating classes can execute during writing and reading.

Evaluate the contract of the **entire participating model**, not just whether the root object implements `Serializable`.

The [Object Output Stream](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html) and [Object Input Stream](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html) specifications define these customization points.

### 7.3. Externalizable, enum, and record Have Their Own Rules

`Externalizable` extends `Serializable` but delegates reading/writing to `writeExternal()`/`readExternal()`. During reconstruction, it invokes the `public` no-arg constructor and then calls `readExternal()`. Do not apply the "serializable class constructor does not run" rule of ordinary classes to this case. See [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html).

`record` classes can implement `Serializable`; when read, the record's canonical constructor is used to create the object from its components. Reference cycles passing through record components are also not preserved like cycles of ordinary classes in `GraphCopyDemo` or `SerializationCopyDemo`.

`enum` types have special handling by constant name. Custom serialization methods do not have the same effect as on ordinary classes. Therefore, do not generalize the constructor or cycle results from one example to all Java data types.

The differences for [records and reference cycles](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html#serialization-of-records) are a practical limitation when considering serialization as a general copying tool.

## 8. Program Verifying Failures and Stream Reuse

`SerializationLimitsDemo` addresses four misconceptions:

1. If a collection is serializable, all of its elements can be written.
2. If a `Comparator` works for a tree, it can naturally be written.
3. Writing the same object again always creates a fresh snapshot.
4. A filter that disallows a type can still be bypassed just by casting to the right type afterward.

File **SerializationLimitsDemo.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.NotSerializableException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;

public class SerializationLimitsDemo {
    static final class Box implements Serializable {
        private static final long serialVersionUID = 1L;
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    private static byte[] serialize(Object source) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(source);
        }
        return buffer.toByteArray();
    }

    private static void expectNotSerializable(String label, Object source)
            throws IOException {
        try {
            serialize(source);
            throw new AssertionError(label + ": no exception");
        } catch (NotSerializableException expected) {
            System.out.println(label + "=NotSerializableException");
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        expectNotSerializable("badElement",
                new ArrayList<>(List.of(new Object())));

        Comparator<Integer> order = (a, b) -> Integer.compare(b, a);
        TreeMap<Integer, String> tree = new TreeMap<>(order);
        tree.put(1, "one");
        tree.put(2, "two");
        TreeMap<Integer, String> treeClone =
                (TreeMap<Integer, String>) tree.clone();
        System.out.println("cloneOrder=" + treeClone.navigableKeySet());
        System.out.println("sharedComparator=" +
                (treeClone.comparator() == tree.comparator()));
        expectNotSerializable("badComparator", tree);

        Box original = new Box(10);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            original.value = 20;
            out.writeObject(original);
            out.reset();
            out.writeObject(original);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                    "maxdepth=10;maxrefs=100;maxbytes=100000;" +
                    "SerializationLimitsDemo$Box;!*"));
            Box first = (Box) in.readObject();
            Box second = (Box) in.readObject();
            Box third = (Box) in.readObject();
            System.out.println("sameWithoutReset=" + (first == second));
            System.out.println("valuesWithoutReset=" +
                    first.value + "," + second.value);
            System.out.println("newAfterReset=" + (third != first));
            System.out.println("valueAfterReset=" + third.value);
        }

        byte[] local = serialize(new Box(1));
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(local))) {
            in.setObjectInputFilter(info -> ObjectInputFilter.Status.REJECTED);
            in.readObject();
            throw new AssertionError("filter did not reject");
        } catch (InvalidClassException expected) {
            System.out.println("filter=InvalidClassException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SerializationLimitsDemo.java
java SerializationLimitsDemo
```

Exact stdout:

```text
badElement=NotSerializableException
cloneOrder=[2, 1]
sharedComparator=true
badComparator=NotSerializableException
sameWithoutReset=true
valuesWithoutReset=10,10
newAfterReset=true
valueAfterReset=20
filter=InvalidClassException
```

### 8.1. Valid Container, Invalid Traversed Part

The `ArrayList` in the program contains `new Object()`. `ArrayList` supports `Serializable`, but `Object` does not, so writing the entire graph throws `NotSerializableException`.

The tree's `Comparator` is a lambda assigned only to `Comparator<Integer>`, not to a target type requiring `Serializable`. It works for comparisons and is still shared by `treeClone`, but it cannot be written in this example. Serializing `tree` therefore fails as well.

Switching the lambda to a `Comparator` designed to support `Serializable` can resolve that object's writability error; you must still check any state the `Comparator` holds and its compatibility contract. Do not slap `Serializable` onto types as a way to make arbitrary data copyable.

A cloned tree can keep the old `Comparator` without writing it to bytes. Thus, the success conditions for `clone` and serialization differ. With a mutable `Comparator`, `clone` sharing the `Comparator` is also a link that must be factored into independence assessments.

### 8.2. Output Streams Keep a Table of Seen Objects

The first write records `original` with `value = 10`. After changing `original.value` to `20`, the second write on the same `ObjectOutputStream` may still only write a back-reference to the already-known object.

When read back, `first` and `second` are the same object, both with `value` equal to `10`. The second write did not create a fresh snapshot of `value = 20`.

`out.reset()` clears the stream's tracking state at a valid boundary and causes subsequent writes to treat `original` as an object that needs to be written anew. Thus `third` differs from `first` and has `value = 20`. [ObjectOutputStream.reset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html#reset()) describes this state-resetting effect.

If you want each copy to be an independent graph, the most readable approach is usually to use a fresh pair of streams for each copy rather than inadvertently keeping a long-lived `ObjectOutputStream`. If you need to preserve relationships across multiple roots within the same copy, you must clearly define which write/read pass they belong to.

`writeUnshared()`/`readUnshared()` have their own rules and are not a shortcut for independently cloning all child objects. Do not swap a single call and ignore whole-graph relationships.

### 8.3. Filter Failure Is a Read Failure, Not a Generics Error

The final section produces valid bytes from `Box`, then the filter actively rejects everything. `readObject()` fails with `InvalidClassException`; the fact that the stream contains the expected `Box` type does not bypass the filter.

Only the exception name is printed here deliberately, avoiding reliance on JDK-specific messages or stack traces. In practice, `InvalidClassException` can also stem from class incompatibility; inspect the cause/context to classify it.

Failed writes are discarded along with their buffers and streams. Do not treat data from a failed serialization attempt as a partial copy that can be used normally.

## 9. Safety Limits When Using Serialization for Copying

Serialization can invoke class code during reading. Do not accept an arbitrary byte array from an untrusted source and feed it directly into `ObjectInputStream` merely because the operation is named "copy."

In the examples, bytes are created locally from a known model. Filters are configured before `readObject()` and restrict types and limits per example. Do not turn these demonstration helpers into utilities that accept arbitrary objects or arbitrary bytes.

### 9.1. Filters Need Context

`ObjectInputFilter` can inspect the class being read and metrics such as depth, reference count, array length, and bytes read. An allowlist of classes together with resource limits narrows what data is accepted.

`SerializationCopyDemo`'s filter also allows `Object[]` because the JDK's `ArrayList` deserialization checks the backing element array. Allowing that array does not allow arbitrary element classes; the objects inside still undergo the stream's corresponding checks.

This allowlist is tailored only for the demonstration graph of `Node`, `Token`, the enum, and `ArrayList`. Changing the model or structure implementation may require revisiting the filter; do not widen it to allow the entire standard library just to "make errors go away."

A filter also does not replace business validation, does not guarantee all `String` contents are validated, and checks metrics at filter invocation points rather than turning every operation into a universal absolute quota. When designing a data ingestion boundary, you must also constrain input data, execution permissions, and required invariants.

The [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) and [Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html) documentation detail the mechanism and usage limits. Filtering adds a layer of defense; it does not make deserializing untrusted data a default choice.

### 9.2. Type Checking After readObject Is Not Enough

`Node.class.cast(in.readObject())` confirms the root object after reading is a `Node`. It does not prove every prior step executed safely, nor does it validate the business semantics of child nodes.

A `<T extends Serializable>` signature or a cast is only part of the contract. A copying contract must also specify trusted sources, accepted classes, data limits, invariants, and resource policies.

### 9.3. Bytes Are Not Encrypted Data

Serialization converts state into a byte representation; it does not encrypt it for secrecy. Written fields may contain sensitive information even if the code does not print them.

`transient` excludes a field from the default mechanism, but the same information may exist in another field/object or be written by custom methods. Do not treat `transient` as proof that a byte payload contains no sensitive data.

If only local copying is needed, there is no need to write bytes to a file and read them back; an in-memory buffer already demonstrates the mechanism. Creating a file does not solve copy-depth issues.

## 10. Class Compatibility and serialVersionUID

A serialized payload typically contains class metadata and the state needed for reconstruction. It does not bundle the entire executable code of the program into a standalone runnable unit.

The reader still needs the matching classes and the ability to load them. Missing classes can cause `ClassNotFoundException`. Renaming, changing class structure, or altering the read contract can render old data unusable.

For ordinary `Serializable` classes, `serialVersionUID` participates in compatibility checks. The classes in the examples declare it explicitly:

```java
// Declaration inside a regular Serializable class.
private static final long serialVersionUID = 1L;
```

A UID mismatch between the written representation and the reading class can cause `InvalidClassException`. If not declared explicitly, the UID is computed from class details and can change when the class is edited in ways the author did not intend as a data format change.

However, keeping the same UID **does not automatically make every change compatible**. It does not convert arbitrary field types, restore old logic, or guarantee newly read data satisfies invariants. Compatibility is a design and testing contract, not just a `long` constant.

Enums and records have their own rules, so do not apply all UID conclusions from ordinary classes to them. This lesson does not use native serialization as a long-term interchange format; if the real goal is storage or cross-system communication, design the data format and versioning for that goal.

The [Versioning Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html) describes compatible and incompatible changes. Using serialization strictly for in-process copying can avoid some versioning issues, yet still does not avoid `transient`, custom hooks, overhead, and graph limitations.

## 11. Cost and Resources: "Write Then Read" Is Not a Cheap Assignment

A shallow clone of a collection must allocate a new container structure and copy the necessary references. It does not deep-copy every property of each element.

Manually copying a graph requires creating the designated nodes, traversing links, and potentially maintaining a seen map. `GraphCopyDemo`'s algorithm also requires memory for `IdentityHashMap` and the recursion stack.

Serialization adds constructing the byte representation, storing protocol metadata, tracking references, reading, and reconstructing objects. When using a buffer, the source, intermediate bytes, and new graph can coexist in memory simultaneously; do not assume peak memory is merely the size of the copy.

There is no single timing number that holds for all collections or all graphs. If copying is on a hot path, benchmark with representative data, including size, sharing, depth, and custom methods. Do not take a few-node example and conclude serialization has the same cost as `clone`.

External resources must be evaluated separately:

| State Category | Questions to Answer |
|---|---|
| Connections, sockets, open files | Should the copy open new ones, share in a controlled way, or exclude them? |
| Caches | Should they be copied, dropped and recomputed, or kept as a shared cache? |
| Locks, threads, executors | What does a "copy" mean and who owns the lifecycle? |
| Business entity IDs | Is the copy a snapshot of the same entity or a new entity needing a different ID? |
| Callbacks, listeners, services | Should those links be duplicated or converted to plain data? |
| Comparators or processing strategies | Is sharing safe, and is their state serializable/deserializable? |

Neither `clone()` nor default serialization answers any of the above questions for the designer.

## 12. Choosing a Copying Approach Based on the Required Contract

| Need | Suitable Approach | What Still Needs Checking |
|---|---|---|
| Just another variable name for the same object | Reference assignment | Two places mutating the same object |
| Separate collection structure, elements may be shared | Copy constructor/factory or class-supported `clone` | Elements/keys/values may still be shared |
| Separate mutable data of a model you own | Model-specific copy constructor/factory or copy method | Aliases, cycles, subclasses, new fields |
| Preserve graph topology using existing serialization | Fresh output/input stream pair in a trusted, controlled context | Whole graph, hooks, `transient`, UID, filter, overhead |
| Only need data for display/transfer | Map to a DTO/appropriate data model | Which fields are kept, dropped, or converted |
| Prevent structural edits through returned reference | Unmodifiable wrapper/factory per contract | Whether source remains linked; whether elements are immutable |

Do not force a business class to implement `Serializable` just to avoid writing a few lines of meaningful copy code. If a model already has a controlled `Serializable` protocol and the graph is small, writing/reading can serve a local purpose; accept the limitations noted above.

Conversely, do not write ad-hoc recursion and call it a universal deep copy. A manual function is only valid within the scope of the types and policies it handles.

### 12.1. Copy Constructors and Immutability

A constructor/factory allows explicit decisions: creating a new list, reusing immutable elements, copying mutable values, keeping or assigning IDs, and dropping caches. For classes with `final` fields, purposeful initialization usually expresses the contract more clearly than patching the result of `super.clone()`.

A constructor that accepts a `List` and stores that exact `List` is not yet a structural copy. The name "copy constructor" must be backed by the actual code. If elements are mutable, creating a new `List` only solves the container layer.

### 12.2. JSON or Data Conversion Does Not Automatically Replace Serialization

Writing JSON and reading it back also goes through a data representation. It can be the right choice for a data-transfer model, but it does not automatically preserve runtime types, `Comparator`s, shared references, or cycles the way Java Object Serialization does for ordinary classes.

The ability to preserve such information depends on the specific library and configuration. Do not insert a JSON round-trip and assume you have a correct deep copy for arbitrary graphs.

### 12.3. Unmodifiable Collections Do Not Mean Deep Copies

A collection that forbids structural modification can still hold mutable objects. If an element is shared, mutating its properties still affects every place holding it.

"Cannot be modified through this API," "structure independent from source," and "all internal state independent" are three properties that must be checked separately. Shallow `clone` only satisfies part of them; serialization also only satisfies them according to class protocols, not all three automatically.

## 13. Testing a Copy by Behavior and References

Seeing identical `toString()` output or checking `equals()` is not enough. Two collections can display the same values while still sharing elements; two properly copied objects might also not be `equals` if the class uses identity comparison.

A test suite aligned with the contract typically checks:

1. **Root:** when a new object is required, `copy != source`.
2. **Container structure:** do additions/removals/replacements in `copy` affect the source structure?
3. **Mutable elements:** does mutating a property in `copy` change the source, and is that per policy?
4. **Duplicate links:** do two paths to the same source node still lead to the same target node?
5. **Reference cycles:** does a back-link point to the right target node or mix in a source node?
6. **Dropped/recomputed data:** do caches, `transient` fields, and superclass state have their defined outcomes?
7. **Intentionally shared objects:** do enums, singletons, or services follow policy?
8. **Failures:** do unsupported elements, filter limits, and incompatible data fail clearly?

The programs in this lesson deliberately test both structural changes and property mutations. These are two different kinds of changes, often where a "seemingly independent" copy reveals remaining shared links.

When the source is updated by multiple threads, `clone`, custom algorithms, and serialization do not by default produce an atomic snapshot of the entire graph. Proper ownership, immutability, or synchronization is required during reading. A copy may be independent after creation yet still have captured an inconsistent state if creation lacked coordination.

## 14. Common Pitfalls

| Misconception | Symptom | How to Reason Correctly |
|---|---|---|
| `Cloneable` declares `clone()` | Cannot call via a `Cloneable` variable | Read the public API of the concrete class |
| Any `List` can be cloned | Compile error or invalid cast | Use the interface contract and an appropriate constructor/factory |
| Cloning a list clones each element | Mutating a `Box` in the copy changes the source | Check container and elements separately |
| `final` makes a collection immutable | Contents can still be added/removed | `final` fixes the reference, not the object's contents |
| `transient` makes all copy types skip the field | `clone` still keeps the field's reference | Distinguish `clone` rules from serialization rules |
| Recursive `new` for every link | Loops on cycles or breaks duplicate links | Use an identity-based source→target map and register before recursing |
| `Serializable` on root suffices for the whole graph | `NotSerializableException` when writing | Inspect all actual nodes that need to be serialized |
| Deserialization always runs the class constructor | Validation skipped or cache uninitialized | Understand ordinary classes vs. special types |
| Serialization always separates every object | Singletons or enums remain shared | Check `readResolve` and type-specific protocols |
| Writing the same object again is a fresh snapshot | Reading returns the same object with old state | Understand reference tables and stream lifecycles |
| Keeping the UID makes all versions readable | Read failures or invalid state | Design and test data compatibility |
| Casting after reading is safe enough | Other code may already have run during reading | Control source, classes, filters, and invariants |
| Serialization is secret encryption | Bytes still contain sensitive data | Distinguish byte representation from data security |

## 15. Exercises and Solutions

### Exercise 1 — Two Kinds of Edits on a Cloned List

The original list is an `ArrayList` holding a `Box` with `value = 5`. Clone the list to `c`, call `c.get(0).value = 8`, then `c.set(0, new Box(9))`. What is `value` of the `Box` in the source?

**Solution:** `8`. The first statement mutates the shared `Box`; the second only replaces the reference in `c`. The source does not automatically switch to `Box(9)`.

### Exercise 2 — transient in clone and Serialization

A class supporting `super.clone()` has a `transient List<String> cache` pointing to an `ArrayList`. Without custom handling, compare `cache` in a shallow clone versus `cache` in ordinary deserialization.

**Solution:** A shallow clone keeps the same `cache` reference as the source. Default serialization omits `transient` fields, so `cache` on an ordinary `Serializable` class is not restored from the source after reading; without reconstruction code, it is `null`. A field initializer expression on a serializable class does not automatically run like a `new` constructor during that read.

### Exercise 3 — Matrix with Shared Rows

`int[] row = {1, 2}; int[][] matrix = {row, row};` If you clone the outer array, are the copy's two rows different from the source? If you clone each row separately, is the relationship of both positions sharing one row preserved?

**Solution:** Cloning the outer array keeps the same `row` reference at both positions, which is also the source's `row`. Cloning each row separately separates the data from the source but creates two distinct rows, breaking the sharing relationship between the two positions. To both separate from the source and preserve that relationship, create exactly one new `row` copy and use it for both positions, or use an algorithm with an identity tracking map.

### Exercise 4 — When to Put a Node into the Seen Map?

In `GraphCopyDemo`, can `seen.put(source, target)` be moved after the loop that copies `links`?

**Solution:** That would break cycle handling. When `child` points back to `root` before `root` is registered, the method keeps creating/copying `root` instead of returning the existing target `root`. It must be placed in the map before traversing child links.

### Exercise 5 — equals Cannot Replace Node Identity

Two source nodes have different references but the same name, and `equals()` returns `true`. If you use a `HashMap` based on `equals` to record copies instead of `IdentityHashMap`, what is the risk?

**Solution:** The algorithm may treat two distinct source nodes as one node and merge them into the same target copy. When the goal is to preserve graph topology by identity, those two references must be kept distinct even when their business values are equal.

### Exercise 6 — Serializable Collection with Non-Serializable Element

An `ArrayList<Object>` contains a `new Object()`. The root `ArrayList` implements `Serializable`. Is serialization guaranteed to succeed? What does making a list field `transient` in another class solve?

**Solution:** No; the mechanism can hit the unsupported element and throw `NotSerializableException`. Marking the list field `transient` only omits that write path from the containing class's default state, without copying the list's contents; you must define the desired state after reading. If another reference path still reaches the same unsupported object, the error can still occur.

### Exercise 7 — Writing Twice on the Same Stream

Write a `Box(1)`, change `value` to `2`, then `writeObject` the same `Box` again on the same `ObjectOutputStream` without calling `reset`. Must the two corresponding `readObject` calls return two different `Box` objects with values `1` and `2`?

**Solution:** No. For ordinary objects like this example, the second write uses a back-reference; both reads return the same object and preserve the state written the first time, which is `1`. To write new state, you must design the stream/handle lifecycle appropriately, such as using a fresh stream pair per copy.

### Exercise 8 — Copy Containing a Singleton

A field of a serializable object points to `Config.INSTANCE`. `Config` has `readResolve()` returning `INSTANCE`. After serialization and deserialization, can you assume mutating `Config` in the deserialized copy will not affect the original `Config`?

**Solution:** No. The field can point right back to the shared singleton. If `Config` is mutable, mutating it affects all places holding that same `INSTANCE`. Independence requires changing the model contract, not merely naming the method `deepCopy`.

### Exercise 9 — Superclass Constructor

`Child` implements `Serializable` and extends non-serializable `Parent`. `Parent` has an accessible no-arg constructor that initializes `x = 10`. Before writing, `child.x = 80`. No custom code saves `x`. After reading, what is `x`?

**Solution:** `10` from `Parent`'s initialization, not `80`. The non-serializable superclass state is not automatically written; the appropriate superclass constructor is called during reconstruction. Do not extrapolate this result to `Externalizable` or `record` while ignoring their specific rules.

### Exercise 10 — Choosing a Copy for an Edit Screen

A screen needs to edit a trial list of orders without modifying the original orders. Orders contain a mutable `List<LineItem>` and an immutable `String` code. Is cloning the outer `ArrayList` enough? State the minimum copy contract.

**Solution:** Not enough. You need a separate list structure, separate order objects for the state allowed to be edited, separate `LineItem` lists, and separate mutable `LineItem` objects as required. The `String` code can be shared. If multiple orders intentionally share an inner object, you must decide whether to preserve that sharing in the copy or split it per business rules, and test that behavior. IDs and services must not be copied blindly under the assumption that "deeper is always right."

## 16. Official References

- [Object.clone and the field-by-field copy contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()).
- [Cloneable and marker interface limits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).
- [Serializable and customization methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html).
- [Java Object Serialization Specification — architecture, records, and cycles](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html).
- [ObjectOutputStream — reference handles and reset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html).
- [Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
