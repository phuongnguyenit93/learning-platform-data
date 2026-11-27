# Type Casting, Disjoint Types, and Compiler Checks in Java 17

**Topic:** Java 17  
**Chapter:** Designing with `sealed`  
**Lesson:** Type casting, disjoint types, and compiler checks

When using inheritance or interfaces, developers often cast a reference from a general type to a more specific type. Java checks casts before the program runs. However, with open hierarchies, the compiler sometimes cannot know all subclasses that might appear in the future.

Since Java 17, `sealed` classes/interfaces are a **stable** language feature. By declaring the exact permitted direct subtypes, `sealed` enables the compiler to recognize many cases where **two types cannot share any runtime object** (*disjoint types*). As a result, certain meaningless casts are rejected at compile time rather than failing only at runtime.

This lesson focuses on three questions:

1. When is a reference type cast accepted at compile time?
2. How does Java 17 determine that two types are **disjoint**, especially with `sealed`, `final`, and `non-sealed`?
3. What is the difference between a **compile-time error**, a **runtime `ClassCastException`**, and **`instanceof` returning `false`**?

> **Java 17 scope:** `sealed` was standardized in Java 17; pattern matching for `instanceof` has been stable since Java 16. Pattern matching for `switch` is still in **preview** in Java 17, so the examples below use stable Java 17 syntax and do not require `--enable-preview`.

## 1. What Is Reference Type Casting?

In Java, a reference variable has a **static type** known at compile time. The object that the variable points to has an **actual runtime type**.

```java
interface Animal {}

final class Dog implements Animal {}

Animal animal = new Dog();   // Static type: Animal; actual object: Dog
Dog dog = (Dog) animal;      // Cast from Animal to Dog
```

On the cast line:

- **Source type (`S`):** `Animal` — the static type of the expression `animal`.
- **Target type (`T`):** `Dog` — the type requested by the cast.
- **Actual runtime type:** `Dog`, so the cast succeeds.

Cast syntax does not create a new object and does not turn an object into another class. It asks the type system to view the reference as the target type, performing a runtime check when necessary.

### 1.1. Three Categories of Situations

**Upcast (widening reference conversion):**

```java
Dog dog = new Dog();
Animal animal = dog;          // No cast needed
Object value = (Object) dog;  // Explicit cast, though unnecessary
```

Because every `Dog` is an `Animal`, the conversion is always valid for non-`null` references. The compiler knows this relationship.

**Downcast:**

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;      // Compiles, succeeds at runtime
```

An `Animal` variable *might* point to a `Dog`, though not necessarily. The cast is accepted at compile time; the runtime must verify the actual object.

**Casting between two interfaces or from a class to another interface:**

```java
interface Auditable {}
interface Exportable {}

final class Report implements Auditable, Exportable {}

Auditable a = new Report();
Exportable e = (Exportable) a;  // Valid; actual object supports both
```

Two interfaces can be implemented together by a single class. Not sharing a direct `extends` relationship does not mean they are always disjoint.

### 1.2. A Cast Can Compile Yet Fail at Runtime

```java
interface Animal {}

final class Dog implements Animal {}
final class Cat implements Animal {}

Animal animal = new Cat();

Dog dog = (Dog) animal;  // Compiles; throws ClassCastException at runtime
```

At compile time, the static type is `Animal`, so the reference **could potentially** hold a `Dog`. The compiler does not conclude from the static type alone that the cast is definitely wrong. At runtime, the actual object is `Cat`, not `Dog`, so `ClassCastException` is thrown.

This is the fundamental boundary: **"a cast might succeed" is different from "a cast is guaranteed to succeed."**

## 2. What Does "Disjoint Types" Mean?

In the context of the Java Language Specification (JLS), two class/interface types are **disjoint** when the compiler can prove that **no non-`null` object** can simultaneously be an instance of both types. When two types are disjoint, many casts between them are rejected at compile time.

You can think of them as sets:

```text
S: set of objects that can be instances of S
T: set of objects that can be instances of T

Possibly intersecting: S ∩ T may contain objects
Disjoint:              S ∩ T = ∅ (excluding null)
```

A classic example:

```java
final class Invoice {}
interface Printable {}

// INVALID:
static Printable convert(Invoice invoice) {
    return (Printable) invoice;
}
```

`Invoice` is declared `final` and does not implement `Printable`. No class can both descend from `Invoice` and implement `Printable`, because `Invoice` cannot have subclasses. Thus, the two types are disjoint. The compiler rejects the cast.

By contrast:

```java
class DraftInvoice {}              // Not final
interface Printable {}

class PrintableDraft extends DraftInvoice implements Printable {}

static Printable convert(DraftInvoice invoice) {
    return (Printable) invoice;   // Compiles
}
```

`DraftInvoice` does not currently implement `Printable` directly, yet a subclass like `PrintableDraft` **can** do both. Therefore, the cast has a chance of succeeding and must be checked against the actual object.

**Disjointness is a conclusion about type structure, not a guess about specific data in one run.**

## 3. Baseline Rules Before Considering `sealed`

Java already checked many impossible casts prior to Java 17. `sealed` extends that reasoning by supplying additional information about permitted branches.

| Type pair | Can they intersect? | Reason |
|---|---|---|
| Class `Dog` and interface `Animal` where `Dog implements Animal` | Yes | Every `Dog` is an `Animal` |
| Two regular classes with no inheritance relationship | No | An object cannot simultaneously extend two independent class branches |
| `final class Invoice` and interface `Printable` not implemented by `Invoice` | No | `Invoice` cannot have subclasses to add the interface |
| Non-`final` class and an interface not yet implemented by it | Possibly | A subclass can implement the interface |
| Two open interfaces with no `extends` relationship | Possibly | A single class can implement both |
| A `sealed` interface and another interface | Depends on permitted branches | If every branch is disjoint from the target, the compiler can reject the cast |

### 3.1. Two Unrelated Classes: Being "Open" Does Not Mean They Can Intersect

```java
class Car {}
class House {}

static House asHouse(Car car) {
    return (House) car;  // COMPILE ERROR
}
```

Both `Car` and `House` are non-`final`, yet Java allows a class to directly inherit from only one superclass. No subclass can simultaneously `extends Car` and `extends House`. These two independent classes are disjoint.

### 3.2. Two Open Interfaces: A Shared Implementation Can Exist

```java
interface Searchable {}
interface Cacheable {}

final class SearchCache implements Searchable, Cacheable {}

static Cacheable asCacheable(Searchable value) {
    return (Cacheable) value;   // Compiles
}
```

Because a class such as `SearchCache` can exist, the compiler does not reject the cast. If `value` actually references a type implementing only `Searchable`, the runtime throws `ClassCastException`.

### 3.3. A `final` Class and an Unimplemented Interface

```java
interface Trackable {}

final class ImmutablePoint {}

// INVALID:
static Trackable asTrackable(ImmutablePoint point) {
    return (Trackable) point;
}
```

Here, `final` eliminates the possibility of adding the interface through a subclass. That is why `final` carries significant weight when the compiler evaluates disjoint types.

## 4. How `sealed` Changes Compiler Reasoning

A `sealed` interface permits only the direct subtypes listed in `permits`. Each direct subtype must itself be declared `final`, `sealed`, or `non-sealed`; records are implicitly `final`.

```java
sealed interface OperationResult permits Success, Failure {}

record Success(String message) implements OperationResult {}

record Failure(String reason) implements OperationResult {}
```

With this model, the compiler knows an `OperationResult` object must belong to a permitted branch. Since both records are `final`, no other subclass of those records can appear to "sneak in" an extra interface outside the model.

### 4.1. Another Interface Intersects None of the Branches

```java
interface JsonWritable {}

sealed interface OperationResult permits Success, Failure {}

record Success(String message) implements OperationResult {}

record Failure(String reason) implements OperationResult {}

static JsonWritable asJson(OperationResult result) {
    return (JsonWritable) result;   // COMPILE ERROR on Java 17
}
```

Reasoning:

1. `OperationResult` permits only `Success` and `Failure`.
2. Both `Success` and `Failure` are records, implicitly `final`.
3. Neither record implements `JsonWritable`.
4. Neither can have subtypes that add `JsonWritable`.
5. Therefore, no non-`null` object can be both an `OperationResult` and a `JsonWritable`.

Even though `JsonWritable` is an open interface, **the `OperationResult` side has closed all relevant branches**, leaving no possibility for the cast to succeed.

### 4.2. When One Branch Can Intersect, the Cast Is Allowed

Modify one branch so that the subtype itself implements `JsonWritable`:

```java
interface JsonWritable {
    String toJson();
}

sealed interface OperationResult permits Success, Failure {}

record Success(String message)
        implements OperationResult, JsonWritable {

    @Override
    public String toJson() {
        return "{\"message\":\"" + message() + "\"}";
    }
}

record Failure(String reason) implements OperationResult {}

static JsonWritable asJson(OperationResult result) {
    return (JsonWritable) result; // Compiles
}
```

The cast **can** succeed if `result` holds a `Success`, yet will fail at runtime if it holds a `Failure`.

`toJson()` merely illustrates the interface contract; in real applications, use a proper JSON library to escape data correctly.

### 4.3. Not Every Pair of Distinct Interfaces Is Disjoint

Two `sealed` interfaces can both permit a common implementing class:

```java
sealed interface Readable permits FileEntry {}

sealed interface Storable permits FileEntry {}

final class FileEntry implements Readable, Storable {}

static Storable asStorable(Readable readable) {
    return (Storable) readable;  // Valid
}
```

Even though `Readable` and `Storable` do not `extends` each other, they share **`FileEntry`**. Therefore, they are not disjoint.

## 5. `non-sealed` Reopens the Possibility of Common Objects

The `permits` restriction applies only to **direct subtypes**. When a branch is declared `non-sealed`, that branch reopens under standard inheritance rules. The compiler must account for subclasses that may appear in the future.

```java
sealed interface JobResult permits Done, ExtensionResult {}

record Done(String value) implements JobResult {}

non-sealed interface ExtensionResult extends JobResult {}

class FrameworkEvent {}

final class CustomResult extends FrameworkEvent
        implements ExtensionResult {}
```

Because `CustomResult` is both a `FrameworkEvent` and a `JobResult`, those two types **can intersect**. Consider the cast:

```java
static FrameworkEvent convert(JobResult result) {
    return (FrameworkEvent) result;   // Compiles
}
```

If `result` is a `CustomResult`, the cast succeeds. If `result` is `Done`, the cast fails at runtime. The fact that `JobResult` is `sealed` does not automatically block the cast, because a `non-sealed` branch allows intersecting with `FrameworkEvent`.

### 5.1. Casting to an Unrelated `final` Class Is Still Rejected

Add the class:

```java
final class UnrelatedRecord {}
```

Now:

```java
static UnrelatedRecord convert(JobResult result) {
    return (UnrelatedRecord) result;  // COMPILE ERROR
}
```

`UnrelatedRecord` implements neither `JobResult` nor `ExtensionResult`, and as a `final` class it cannot have subclasses adding those interfaces. A `non-sealed` branch allowing some types to intersect **does not mean every target type can intersect**.

### 5.2. Comparing Two Cases in the Same Tree

```text
JobResult (sealed)
├── Done (record, final)
└── ExtensionResult (non-sealed interface)
    └── CustomResult (extends FrameworkEvent)

FrameworkEvent (open class)
└── CustomResult (implements ExtensionResult)

UnrelatedRecord (final class, does not implement JobResult)
```

| Source | Target | Compile result | Why |
|---|---|---|---|
| `JobResult` | `Done` | Allowed | `Done` is a permitted branch |
| `JobResult` | `FrameworkEvent` | Allowed | A class can both extend `FrameworkEvent` and implement `ExtensionResult` |
| `JobResult` | `UnrelatedRecord` | Rejected | Target class is `final` and participates in no branch |
| `FrameworkEvent` | `JobResult` | Allowed in this model | `CustomResult` is a common descendant |
| `Done` | `UnrelatedRecord` | Rejected | Two unrelated classes; cannot share an instance |

## 6. The Compiler Reasons About "Possibility," Not Runtime Values

A helpful rule of thumb: **cast rules look at the expression's static type and the declared hierarchy**, not just the concrete object a developer knows was instantiated on a particular line.

Suppose:

```java
JobResult result = new Done("OK");
FrameworkEvent event = (FrameworkEvent) result;
```

This cast still **passes compile-time type checking** because the `JobResult` tree has the `ExtensionResult` branch, and a type like `CustomResult` can belong to both sets. Yet at runtime, the object is `Done`, so Java throws `ClassCastException`.

If you change the static type to `Done`:

```java
Done result = new Done("OK");
FrameworkEvent event = (FrameworkEvent) result; // COMPILE ERROR
```

`Done` is a record, hence a `final` class, and does not extend `FrameworkEvent`. The compiler has enough information to reject the cast.

This creates an important distinction:

| Expression's static type | Runtime object | What can Java conclude? |
|---|---|---|
| `JobResult` | `Done` | Only knows `JobResult` has another branch that can intersect `FrameworkEvent`; cast is allowed, runtime fails |
| `JobResult` | `CustomResult` | Cast is allowed; runtime succeeds |
| `Done` | `Done` | `Done` and `FrameworkEvent` are disjoint classes; blocked at compile time |

Never conclude a cast is "safe" just because `javac` accepts it.

## 7. `instanceof` Undergoes Similar Type-Compatibility Checks

With `instanceof`, Java checks the type condition at runtime and returns `true` or `false`. However, **the `instanceof` expression itself must be valid at compile time**.

### 7.1. Distinguishing Casting from Type Testing

```java
static String describe(JobResult result) {
    if (result instanceof Done done) {
        return "Completed: " + done.value();
    }
    if (result instanceof FrameworkEvent) {
        return "Extension branch";
    }
    return "Other result";
}
```

Here:

- `result instanceof Done done` tests the object and, if matched, binds the pattern variable `done` of type `Done`. Pattern matching for `instanceof` has been stable since Java 16.
- `result instanceof FrameworkEvent` compiles because `JobResult` has a `non-sealed` branch; the expression evaluates to `true` or `false` depending on the actual object.
- No cast in this example throws `ClassCastException`; when a test fails, `instanceof` returns `false`.

### 7.2. If Two Types Are Disjoint, `instanceof` Is Rejected Too

```java
static boolean wrong(JobResult result) {
    return result instanceof UnrelatedRecord;  // COMPILE ERROR
}
```

The compiler does not wait for runtime to return `false`, because the type rules already prove there can be no shared object. This is a validity check on the **expression**, not dead-code elimination of an always-false `if` branch.

### 7.3. Pattern Matching for `instanceof` Has Additional Rules

Java 17 has two common forms:

```java
if (result instanceof Done) {
    // Traditional type test.
}

if (result instanceof Done done) {
    // Type test plus pattern variable binding done.
}
```

In Java 17, the **type pattern** form is also rejected if the static type on the left is **already a subtype** of the pattern type. For example:

```java
Done done = new Done("OK");

// INVALID: Done is already a subtype of JobResult.
if (done instanceof JobResult another) {
    System.out.println(another);
}
```

The traditional form `done instanceof JobResult` can compile, though it is typically redundant since a non-`null` `Done` is always a `JobResult`. The rule rejecting a pattern that "obviously always matches the expression type" is a **specific rule of pattern matching**; it does not mean `Done` and `JobResult` are disjoint.

### 7.4. Scope of Pattern Variables

The variable `done` can only be used in places where Java proves the pattern expression matched:

```java
static String label(JobResult result) {
    if (result instanceof Done done) {
        return done.value();    // Valid inside the true branch
    }
    return "Not Done";
}
```

You cannot assume `done` exists outside the scope where the condition is confirmed. This scoping rule prevents accessing an unestablished value.

## 8. Compile-Time Checks vs. Runtime Errors

| Case | At compile time | At runtime |
|---|---|---|
| Cast from subtype to supertype | Accepted | Succeeds; typically needs no extra check |
| Cast between two potentially intersecting types | Accepted | May succeed or throw `ClassCastException` |
| Cast between two types proven disjoint | **Compile error** | Code cannot run as written |
| `instanceof` between two potentially intersecting types | Accepted | Returns `true` or `false` |
| `instanceof` between two types proven disjoint | **Compile error** | Code cannot run |
| `instanceof` with `null` in a valid expression | Accepted | Returns `false` |
| Casting a `null` reference via a valid conversion | Accepted | Result remains `null` |

### 8.1. Why Does `null` Not Invalidate Disjointness Rules?

The exact definition of disjoint types excludes `null` because `null` is not an instance of any class or interface. However, cast checking relies on **static types**, so a forbidden cast does not become valid simply because a variable currently holds `null`.

Example:

```java
final class Alpha {}
final class Beta {}

Alpha alpha = null;

// COMPILE ERROR because Alpha and Beta are two unrelated classes:
Beta beta = (Beta) alpha;
```

Conversely, casting from an expression of type `Object` to `Beta` is a potentially valid conversion:

```java
Object value = null;
Beta beta = (Beta) value;      // Valid; beta == null
boolean test = value instanceof Beta;  // Valid; evaluates to false
```

Do not use `null` to infer that the compiler will permit arbitrary casts between unrelated types.

### 8.2. Casting Through `Object` Can Hide Static Type Information

```java
JobResult result = new Done("OK");

Object broad = result;  // Widens static type to Object

try {
    UnrelatedRecord record = (UnrelatedRecord) broad;
    System.out.println(record);
} catch (ClassCastException exception) {
    System.out.println("Object is not an UnrelatedRecord");
}
```

The cast from `Object` to `UnrelatedRecord` compiles because an `Object` variable could refer to an `UnrelatedRecord` instance. Yet the actual object is still `Done`, so runtime throws `ClassCastException`.

Routing through `Object`, raw types, or reflection **does not change the actual type of the object**. It merely strips static type information from the compiler at a check site; it is not a proper fix when two types are fundamentally incompatible.

## 9. The Compiler Reasons Across Multiple `sealed` Levels

The compiler does not inspect only the root's `permits`: it can trace further down nested `sealed` branches.

```java
interface Auditable {}

sealed interface Message permits UserMessage, SystemMessage {}

sealed interface UserMessage extends Message
        permits TextMessage, ImageMessage {}

record TextMessage(String text) implements UserMessage {}

record ImageMessage(byte[] bytes) implements UserMessage {}

record SystemMessage(String code) implements Message {}
```

In this model:

```text
Message (sealed)
├── UserMessage (sealed)
│   ├── TextMessage (record/final)
│   └── ImageMessage (record/final)
└── SystemMessage (record/final)

Auditable (open interface, implemented by none of the types above)
```

The following cast is rejected:

```java
static Auditable asAuditable(Message message) {
    return (Auditable) message;  // COMPILE ERROR
}
```

Although `UserMessage` is an interface, it is also `sealed`, and its branches `TextMessage` and `ImageMessage` are closed. No branch can produce an object that is both a `Message` and an `Auditable`.

If `UserMessage` were changed to a `non-sealed interface`, a new class could implement both `UserMessage` and `Auditable`. In that case, disjointness would no longer hold, and the compiler could accept the cast.

**Mental model to keep:** For multi-level `sealed` hierarchies, trace down the branches until you hit a `final` type, a `non-sealed` branch, or a type capable of intersecting the target cast type.

## 10. Complete Runnable Java 17 Example

This example simultaneously demonstrates:

- Type checking with `instanceof` and pattern matching.
- A cast that **can succeed** thanks to a `non-sealed` branch.
- A cast that **still compiles** yet fails at runtime with `ClassCastException`.

Save the code to **`SealedCastDemo.java`**:

```java
public class SealedCastDemo {

    sealed interface Response
            permits Accepted, Rejected, Extension {}

    record Accepted(String id) implements Response {}

    record Rejected(String reason) implements Response {}

    non-sealed interface Extension extends Response {}

    static class ExternalBase {
        String source() {
            return "external";
        }
    }

    static final class PartnerResponse extends ExternalBase
            implements Extension {}

    static final class Unrelated {}

    static String describe(Response response) {
        if (response instanceof Accepted accepted) {
            return "Accepted: " + accepted.id();
        }
        if (response instanceof Rejected rejected) {
            return "Rejected: " + rejected.reason();
        }
        if (response instanceof ExternalBase base) {
            return "Extension: " + base.source();
        }
        return "Other extension";
    }

    static ExternalBase asExternalBase(Response response) {
        // Valid because a Response that is also an ExternalBase can exist.
        return (ExternalBase) response;
    }

    public static void main(String[] args) {
        Response fromPartner = new PartnerResponse();
        Response fromCore = new Accepted("R-17");

        System.out.println(describe(fromPartner));
        System.out.println(describe(fromCore));

        ExternalBase converted = asExternalBase(fromPartner);
        System.out.println(converted.source());

        try {
            // Statically allowed; fails on an Accepted instance.
            asExternalBase(fromCore);
        } catch (ClassCastException exception) {
            System.out.println("Cast failed at runtime");
        }

        // If uncommented, the cast below fails right at compile time:
        // Unrelated value = (Unrelated) fromCore;
    }
}
```

Using JDK 17:

```bash
javac --release 17 SealedCastDemo.java
java SealedCastDemo
```

Expected output:

```text
Extension: external
Accepted: R-17
external
Cast failed at runtime
```

Notable point: `asExternalBase` accepts static type `Response`, while `Response` has an open `Extension` branch. Therefore, the compiler **cannot** rule out receiving a `PartnerResponse`. Static type validity cannot predict that the actual object is `Accepted` on a specific call.

## 11. Compiler Checks Related to `permits` and Hierarchy Validity

Beyond cast checking, `javac` also validates the **structure of `sealed` hierarchies**:

### 11.1. Direct Subtypes Must Be Permitted

```java
sealed interface AccessResult permits Allow {}

final class Allow implements AccessResult {}

// INVALID: Deny is not in permits.
final class Deny implements AccessResult {}
```

The compiler blocks direct implementations outside the declared list. That is the basis on which it trusts the hierarchy is controlled.

### 11.2. Subtypes Must Declare How the Hierarchy Continues

```java
sealed class BaseResult permits ChildResult {}

// INVALID: ChildResult requires final, sealed, or non-sealed.
class ChildResult extends BaseResult {}
```

Fix it with one of the valid options:

```java
sealed class BaseResult permits ChildResult {}

final class ChildResult extends BaseResult {}
```

You can use `sealed` for multi-level branches, or `non-sealed` when intentionally allowing extension. Decisions at each level directly affect "can intersect" conclusions during casts.

### 11.3. Subtypes Must Directly Extend or Implement the Exact Parent

```java
sealed interface Task permits Parent, Grandchild {}

non-sealed interface Parent extends Task {}

// INVALID when listing Grandchild in Task's permits:
// Grandchild only extends Parent, not directly Task.
interface Grandchild extends Parent {}
```

The `permits` list is not a list of all descendants. Only **direct** subtypes are listed. Once below a `non-sealed` branch, deeper descendants must not be placed in the root's `permits`.

### 11.4. Subtypes Must Belong to the Proper Module/Package

In a **named module**, permitted direct subtypes must be in the same module as the `sealed` type. In an **unnamed module**, they must be in the same package.

Because of these constraints, direct branches cannot be added arbitrarily from an outside module. For plugin extension points outside a module, consider designing an appropriate `non-sealed` branch or keeping the interface open.

## 12. Common Points of Confusion

### 12.1. "Two unrelated interfaces always fail to cast"

**False.** Two open interfaces can both be implemented by one class. Even two `sealed` interfaces can share a common subtype if their `permits` structures allow it.

### 12.2. "If `instanceof` always returns `false`, Java accepts and optimizes it away"

**Not necessarily.** When two types are proven disjoint, `instanceof` is an invalidly typed expression and can be rejected at compile time.

### 12.3. "Having `sealed` means the compiler knows every object type in the hierarchy"

**Inaccurate.** It knows the permitted direct branches. If a `non-sealed` branch appears, new subtypes can still be added beneath it.

### 12.4. "If a cast compiles, it is safe"

**False.** It only means the conversion is not proven impossible under static rules. Runtime can still throw `ClassCastException`.

### 12.5. "`final` and `sealed` enforce security access control"

**False.** They govern inheritance/implementation at the language level and support type checking; they do not replace authentication, authorization, or validation.

### 12.6. "Pattern matching for `instanceof` and pattern matching for `switch` are both standard in Java 17"

**False.** Pattern matching for `instanceof` is standard since Java 16, while pattern matching for `switch` is only in *preview* in Java 17. For examples running by default on Java 17, prefer `instanceof` and stabilized constructs.

### 12.7. "Every rejected cast is caused by `sealed`"

**False.** Rules such as two independent classes sharing no common object or a `final class` not implementing an interface existed beforehand. `sealed` extends disjointness proofs when permitted branches are known.

## 13. Reasoning Workflow When Reading a Cast

When encountering `(Target) source` or `source instanceof Target`, you can analyze in order:

1. **Identify the static type of `source`**, without conflating it with the object instantiated on a specific line.
2. **Identify `Target`** and direct or indirect parent–child relationships.
3. For two independent classes, check intersection possibility through the class hierarchy (Java has single class inheritance).
4. If a `final` class is involved, check whether it directly or indirectly implements the target interface.
5. If a `sealed` class/interface is involved, follow the types in `permits` down the sub-branches.
6. When encountering `non-sealed` or an extensible class, consider whether a future subclass could satisfy both types simultaneously.
7. If **proven there is no common object type**, the cast or `instanceof` check is rejected at compile time.
8. If **intersection is possible**, the cast can compile, yet runtime behavior must be considered; use `instanceof` to check when needed and avoid blind casts.

**Note:** This reasoning workflow covers common class/interface examples. The Java Language Specification also has specific rules for generics, arrays, intersection types, and type variables. When encountering complex types, apply the formal rules in JLS `5.1.6` and `5.5` instead of simplifying from a tree diagram alone.

### Quick Decision Table

| Observation | Practical conclusion |
|---|---|
| `S` is a subtype of `T` | Valid upcast, usually needs no cast |
| `T` is a subtype of `S` | Possible downcast, requires runtime check |
| Two classes not in the same inheritance chain | Cannot cast directly between them |
| `final` class not implementing the target interface | Cannot cast directly between those two types |
| `sealed` with all branches closed and none intersecting the target | Compiler can prove disjointness and reject |
| `sealed` with a `non-sealed` branch that can intersect the target | Cast may be permitted; outcome depends on the runtime object |
| Casting from `Object` to a specific type | Compiles; no guarantee the actual object has that type |

## 14. Reasoning Practice

**Exercise 1.** Read the declarations:

```java
sealed interface A permits A1, A2 {}

record A1() implements A {}
record A2() implements A {}

interface B {}
```

Can the cast `(B) someA`, where `someA` has static type `A`, compile on Java 17?

**Answer:** No. `A` has only two terminal branches `A1` and `A2`; neither implements `B`. The two interfaces `A` and `B` have no common instances, so they are disjoint.

**Exercise 2.** Keep `A` but change one branch:

```java
sealed interface A permits A1, APlugin {}

record A1() implements A {}

non-sealed interface APlugin extends A {}

interface B {}
```

Is `(B) someA` still guaranteed to be rejected?

**Answer:** No. A class can exist that implements both `APlugin` and `B`. Therefore, with static type `A`, casting to `B` can compile, though it may fail at runtime.

**Exercise 3.** Two interfaces `Left` and `Right` are both `sealed`, yet both permit `Both`, and `Both` is a `final` class implementing both. Are they disjoint?

**Answer:** No. `Both` is a valid shared object type.

**Exercise 4.** A variable of static type `A` points to an `A1`. In the model of Exercise 2, why does `(B) someA` pass compile-time checking yet still throw `ClassCastException`?

**Answer:** Static type `A` has the open `APlugin` branch, so an intersection with `B` is possible. However, the current runtime object is `A1` and does not implement `B`, so the cast fails at runtime.

**Exercise 5.** Why can replacing `someA` with a variable of static type `A1` change the cast check outcome?

**Answer:** `A1` is a record, implicitly `final`. There can be no subclasses of `A1` to add `B`. Therefore, if `A1` itself does not implement `B`, the pair is disjoint right at static checking.

**Exercise 6.** Does `JobResult value = null;` allow casting to `UnrelatedRecord`, given both types are disjoint?

**Answer:** No. Cast validity is determined from the static types `JobResult` and `UnrelatedRecord`. If `Object value = null;` is used instead, casting to `UnrelatedRecord` can be valid and evaluates to `null`.

## 15. Official References

- [Oracle Java SE 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): the **Narrowing Reference Conversion and Disjoint Types** section explains impossible casts and `sealed`/`non-sealed` examples.
- [Java Language Specification 17 — `5.1.6 Narrowing Reference Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): definition of narrowing reference conversion, disjoint types rules, and runtime checks.
- [Java Language Specification 17 — `5.5 Casting Contexts`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): casting contexts and validity conditions.
- [Java Language Specification 17 — `15.16 Cast Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.16): cast expression rules.
- [Java Language Specification 17 — `15.20.2 The instanceof Operator`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): regular `instanceof` and pattern matching.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): motivation and official design of `sealed` in Java 17.

**Core takeaway:** `sealed` does not eliminate runtime type checking in Java. It makes **static checking more accurate**, allowing `javac` to reject casts that can never share an object. When a hierarchy retains an open branch or has a shared implementing type, casts can still be accepted and the program must handle cases where the runtime object is not of the expected type.
