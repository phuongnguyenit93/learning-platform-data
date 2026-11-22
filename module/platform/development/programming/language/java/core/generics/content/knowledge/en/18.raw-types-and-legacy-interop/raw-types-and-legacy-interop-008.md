# Migrating Legacy APIs to Generics Boundary by Boundary

## Objectives and Context

A long-lived Java system may contain APIs written before generics appeared in Java 5: methods returning `List` without type arguments, accepting raw `Collection`, or taking and returning `Object`. Those APIs still run, yet the compiler cannot guarantee that elements are used with the right data types. The goal during migration is to **place type information and data validation right at the handoff point between legacy and new code**, then expand the type-safe region step by step.

After this lesson, you can:

- Identify **boundaries** between legacy libraries/modules and application code using generics.
- Choose whether to replace `List` with `List<?>`, `List<T>`, `List<User>`, or a purposeful wrapper/adapter.
- Build a **typed adapter** that takes raw data, validates each element, and returns a `List<User>` that does not share mutable state with the legacy dataset.
- Wrap `Object`-based APIs with `Class<T>` when runtime type checks are needed.
- Know where `rawtypes` and `unchecked` warnings should be isolated and when a cast is insufficient to guarantee safety.
- Plan a scoped migration sequence together with checks for source, binary, and behavioral compatibility.

The lesson focuses on a **boundary-by-boundary migration strategy**, without requiring a simultaneous rewrite of the entire system. Examples use Java 17 or later and are compiled and run to verify outputs.

## 1. Why Shouldn't You Replace All Raw Types with Find-and-Replace?

Consider a legacy API:

```java
interface LegacyRepository {
    java.util.List findAll();
    void save(Object value);
}
```

New code wants to work with `User` instead of arbitrary `Object`. It can be tempting to edit it directly into:

```java
interface UserRepository {
    java.util.List<User> findAll();
    void save(User user);
}
```

Both declarations are **contract illustrations** and require a `User` class to compile standalone. These are two different APIs in terms of data commitments and `save`'s parameter type; you cannot assume changing the signature is safe for all callers.

Risks before replacing:

- Actual data returned by `LegacyRepository.findAll()` may include `User`, other legacy types, or even `null`.
- Legacy code may call `save(Object)` with object types other than `User`; changing to `save(User)` impacts source compatibility.
- Already-compiled implementations and modules may rely on the old descriptor; changing `save(Object)` to `save(User)` **changes the descriptor**, requiring binary compatibility checks.
- Simply performing `(List<User>) legacy.findAll()` does not check each element in the list because of **type erasure**.
- A collection to which legacy code still holds write access can be mutated after the cast, breaking assumptions in new code.

A better starting point is identifying: **which inputs are untrusted regarding type, who can mutate the data, and what the new contract must guarantee**.

## 2. What Is a Boundary? Looking at Data Flow Direction

A boundary appears where a value moves from a region lacking type control into a region with an explicit generic contract.

```text
        Legacy code / library
        (raw List, Object, mixed data)
                 |
                 v
       Conversion boundary
       - validate elements
       - convert representation if needed
       - copy / isolate mutation rights
       - report errors with context
                 |
                 v
         API with generics
      (List<User>, UserRepository)
                 |
                 v
           Business logic
       (needs only User)
```

A program can have many boundaries: third-party libraries, old drivers, data import APIs, callbacks, queues, or APIs returning `Object`. **Migrating boundary by boundary** means completing validation and contracts for one data path first, so downstream consumer layers stop guessing or scattering casts.

When identifying a boundary, note:

| Question | What you need to know |
| --- | --- |
| Who owns the legacy API? | Can source be edited, or can you only write an adapter? |
| What types are in the actual data? | A single type, multiple types, or an unknown schema? |
| Is `null` allowed? | Must `null` be preserved, filtered out, or explicitly rejected? |
| Can the collection be modified after return? | If yes, consider a copy/snapshot |
| Do callers need to read or write? | Reading can use wildcards; writing needs a concrete contract |
| How should invalid data be handled? | Fail-fast, report errors with index, or collect errors |
| Are there legacy callers/binaries? | May need parallel adapters, a migration plan, or compatibility checks |

Starting from **data and contracts** before editing syntax prevents situations where warnings disappear while runtime risks remain.

## 3. Raw Types, Wildcard Types, and Typed Types on Both Sides of a Boundary

The following three declarations are not equivalent:

```java
java.util.List raw = obtainLegacyList();
java.util.List<?> unknown = raw;
java.util.List<User> users = convertAndCheck(unknown);
```

This code **illustrates the conversion flow**: `obtainLegacyList()` and `convertAndCheck(...)` stand for application-provided methods, while `User` is the domain type.

- **`List`**: raw type, omitting generic arguments. `add(...)` can be called via a raw reference with an unchecked warning.
- **`List<?>`**: list with an unknown element type; safe to iterate as `Object` and restricts inserting non-`null` values.
- **`List<User>`**: a promise understood by the compiler that each element is returned as `User`. To build this promise from a raw source, you need real validation backing it.

If the task is merely displaying elements, `List<?>` can be the final target of improving the API:

```java
static void printAnything(java.util.List<?> input) {
    for (Object value : input) {
        System.out.println(value);
    }
}
```

The snippet above is a method placed inside a Java class. It is not `List<Object>`: Java generics are invariant, so `List<String>` does **not** automatically convert to `List<Object>`. Use `List<Object>` when an API needs a list whose contract intentionally allows holding heterogeneous `Object` values; use `List<?>` when element types are unknown and you primarily need to **read**.

## 4. Complete Example: An Adapter Validating Each Element Before Exposing a Typed API

Suppose you have `LegacyDirectory` taking `Object` and returning raw `List`; that library cannot be changed in the initial phase. New code wants to work with `UserDirectory.users(): List<User>`. We build an **adapter** in between.

Create file **`MigrationBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class MigrationBoundaryDemo {
    // Simulates a legacy library: cannot be edited or API cannot change yet.
    static final class LegacyDirectory {
        private final List entries = new ArrayList();

        void add(Object entry) {
            entries.add(entry);
        }

        List findAll() {
            return entries;
        }
    }

    record User(String id, String name) {
        User {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
        }
    }

    interface UserDirectory {
        List<User> users();
    }

    static List<User> checkedUsers(List<?> source) {
        Objects.requireNonNull(source);
        List<User> result = new ArrayList<>();

        for (int index = 0; index < source.size(); index++) {
            Object item = source.get(index);
            if (!(item instanceof User user)) {
                String type = item == null
                        ? "null"
                        : item.getClass().getName();
                throw new IllegalArgumentException(
                        "Unexpected entry at index " + index + ": " + type);
            }
            result.add(user);
        }
        return List.copyOf(result);
    }

    static final class LegacyDirectoryAdapter implements UserDirectory {
        private final LegacyDirectory legacy;

        LegacyDirectoryAdapter(LegacyDirectory legacy) {
            this.legacy = Objects.requireNonNull(legacy);
        }

        @Override
        public List<User> users() {
            return checkedUsers(legacy.findAll());
        }
    }

    public static void main(String[] args) {
        LegacyDirectory old = new LegacyDirectory();
        old.add(new User("u1", "Lan"));
        old.add(new User("u2", "Minh"));

        UserDirectory directory = new LegacyDirectoryAdapter(old);
        List<User> snapshot = directory.users();
        System.out.println("users: " + snapshot);

        old.add("wrong format");
        try {
            directory.users();
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("previous snapshot size: " + snapshot.size());
    }
}
```

From the directory containing the file:

```bash
javac -Xlint:rawtypes -Xlint:unchecked MigrationBoundaryDemo.java
java MigrationBoundaryDemo
```

**Verified stdout on Java:**

```text
users: [User[id=u1, name=Lan], User[id=u2, name=Minh]]
rejected: Unexpected entry at index 2: java.lang.String
previous snapshot size: 2
```

Compiler warnings are expected in the `LegacyDirectory` region due to raw `List`, raw `ArrayList`, and `entries.add(entry)`. They appear in `javac`'s output, not the stdout of the `java` command.

### Layer-by-layer explanation

**`LegacyDirectory`:** keeps the legacy API, allowing any `Object` to be stored. In real applications, this could be a class in an external JAR or source deployed across multiple systems. `@SuppressWarnings` is omitted from the sample so learners can see the warnings clearly.

**`User`:** uses a Java 17 `record` and rejects `null` fields. This gives `List<User>` on the modern side a clear domain type.

**`checkedUsers(List<?>)`:** takes a list of unknown element type. Each object is checked with `instanceof User`. Wrong values are rejected with an error showing **index** and **actual type**; `null` is also rejected. Because every element passed validation, the method can place those `User` instances into an `ArrayList<User>` without needing an unchecked cast.

**`List.copyOf(result)`:** creates a list unmodifiable via standard APIs and detached from the input list. Because `User` is a record holding only immutable `String` fields, the example produces a suitable snapshot; for domain elements with mutable state, copying the list does not automatically make every element immutable.

**`LegacyDirectoryAdapter`:** is the sole point where new code needs to know about `LegacyDirectory`. Callers use `UserDirectory` and never see raw `List`.

**Second call:** after the legacy library adds a contract-breaking `String`, the next adapter call detects it immediately at index 2. The previously returned `snapshot` list does not gain that element because data was isolated.

The example intentionally puts the legacy API and adapter in the same file for easy running; in real systems, the legacy library and adapter typically live in separate packages/modules.

## 5. Why Not Cast `List` Directly to `List<User>`?

A dangerous "quick fix":

```java
// Example requires a context with legacyDirectory and class User.
// @SuppressWarnings("unchecked")
// List<User> users = (List<User>) legacyDirectory.findAll();
```

Without suppression, the compiler reports an **unchecked cast**. Reason: due to erasure, the JVM knows the object is a `List`, yet cannot verify **every element** is a `User`. The cast can succeed without detecting a `String` sitting inside the list.

Failure typically arrives later:

```java
// for (User user : users) {
//     System.out.println(user.name()); // Possible ClassCastException.
// }
```

In the loop above, the compiler may emit a cast when reading each element assuming `User`. This is a form of **heap pollution**: actual data inside the collection object no longer matches the generic type promised by the variable.

**Checking each element and creating a new list** fits well when the dataset is small and clear contracts plus type safety are needed. If data is very large or streaming, you can design a validator processing records one by one, collecting errors / routing to an error pipeline, or providing a typed view that checks on read; the choice must clarify error detection timing and data mutability.

You also cannot assume:

```java
if (candidate instanceof List<?>) {
    // candidate is a List; no proof yet that all elements are User.
}
```

is enough to return `List<User>`. `instanceof List<?>` checks only **the runtime collection type**; `User` as a type argument does not exist as a specialized `List<User>` runtime class.

## 6. Boundaries for APIs Returning `Object`: Using Type Tokens When Appropriate

Not every legacy API returns a collection. A configuration system might use `Object read(String key)` and `void write(String key, Object value)`. New code wants to read a concrete value and detect type mismatches right at the gateway.

Create file **`TypedGatewayDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class TypedGatewayDemo {
    static final class LegacySettings {
        private final Map<String, Object> values = new HashMap<>();

        Object read(String key) {
            return values.get(key);
        }

        void write(String key, Object value) {
            values.put(key, value);
        }
    }

    static final class SettingsGateway {
        private final LegacySettings legacy;

        SettingsGateway(LegacySettings legacy) {
            this.legacy = Objects.requireNonNull(legacy);
        }

        <T> T read(String key, Class<T> type) {
            Objects.requireNonNull(type);
            return type.cast(legacy.read(key));
        }

        <T> void write(String key, Class<T> type, T value) {
            Objects.requireNonNull(type);
            legacy.write(key, type.cast(value));
        }
    }

    public static void main(String[] args) {
        LegacySettings old = new LegacySettings();
        SettingsGateway gateway = new SettingsGateway(old);

        gateway.write("retries", Integer.class, 3);
        Integer retries = gateway.read("retries", Integer.class);
        System.out.println("retries: " + retries);

        old.write("retries", "three");
        try {
            gateway.read("retries", Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("rejected: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac TypedGatewayDemo.java
java TypedGatewayDemo
```

**Verified stdout:**

```text
retries: 3
rejected: ClassCastException
```

Analysis:

- The adapter accepts an explicit `Class<T>`, such as `Integer.class`.
- `Class.cast(Object)` performs **a runtime type check**. When the actual value is `String` while the caller asks for `Integer`, the failure happens at the adapter boundary.
- Generic `<T> T read(...)` lets callers receive a typed result, while the token drives the runtime check.
- `Class.cast(null)` returns `null`, so in a real API you should clearly define rules for missing keys vs. `null` values (e.g., returning `Optional<T>` or throwing an exception).
- `Class<T>` can describe runtime types like `Integer`, yet **cannot fully validate nested types** like `List<String>` using `List.class` alone. If an API returns an arbitrary `List`, you still need element-by-element validation or a richer type metadata representation.

This pattern illustrates using a generic method at **a boundary** without forcing edits to `LegacySettings`'s signatures or data.

## 7. Incrementally Migrating an API: Before, During, and After

Picture three coexisting phases instead of one global rewrite.

| Phase | Legacy side | Boundary | Modern consumer side |
| --- | --- | --- | --- |
| Before migration | `List findAll()` | None yet | Scattered casts, risk of late failures |
| Intermediate step | Keep legacy API | `checkedUsers(List<?>)` + `UserDirectory` | Uses only `List<User>` |
| Once source API is owned | Can move generics into internal class per real contract | Adapter still serves legacy callers or is retired | Typed data end to end |

**Step 1 — Map callers and callees.** Identify old methods, where data is created, and where collections are received and mutated. Specifically distinguish collection **ownership**: a method returning a raw `List` backed by mutable state differs from one returning a snapshot.

**Step 2 — Write the target type contract.** Choose `User`, `List<User>`, or `List<?>` matching the actual data. Decide on `null`, wrong-typed elements, and error-reporting behavior. Do not assume every legacy record has the same type.

**Step 3 — Build a small validation point.** Write an adapter accepting the raw API that exposes the typed API only after data is verified. You can fail with a contextual exception or return validation error lists; choose based on business needs.

**Step 4 — Move one group of callers to the typed interface.** Replace scattered calls and casts with a dependency on `UserDirectory`. Keep legacy API access centralized inside the adapter.

**Step 5 — Test with both valid and invalid data.** Mixed-type data, `null`, empty lists, mutations after return, and potential concurrent mutation are crucial test conditions.

**Step 6 — Migrate the source once you own it.** After verifying all write and read sites, replace raw declarations with concrete generics in the data-owning class; evaluate impact on legacy callers, subclasses/interfaces, and class files.

**Step 7 — Shrink the legacy zone.** Remove unneeded adapters once all callers have migrated; keep an adapter as a compatibility layer if external systems still depend on the old API.

Each phase must have clear checkpoints and scope; replacing hundreds of `List` declarations with `List<User>` via search-and-replace makes it hard to tell real improvements apart from unchecked casts hiding bugs.

## 8. Compatibility of Generic Signatures Is Not Just Syntax

Java generics use **type erasure**, so parameterizing certain signatures can keep the same JVM descriptor. For example:

```java
// Old form:
java.util.List findAll();

// Generic declaration form:
java.util.List<User> findAll();
```

Both declarations above share **the same return descriptor** `()Ljava/util/List;` after erasure. Yet you must not conclude from this that every raw-to-generic change is completely compatible in every dimension:

- **Binary compatibility:** check each method's descriptor, name, visibility, inheritance/bridge relationships, and pre-compiled classes. For example, changing `save(Object)` to `save(User)` alters the descriptor from `(Ljava/lang/Object;)V` to `(L.../User;)V` and can prevent pre-compiled legacy callers from linking properly.
- **Source compatibility:** legacy code may compile with warnings when passing raw types to typed APIs, yet some changes cause compile errors due to generic rules, wildcards, overloads, or name clashes.
- **Behavioral compatibility:** changing a declared type does not automatically filter or convert stored data. An adapter may actively throw on invalid data; this change must be agreed upon in the contract.
- **Reflection compatibility:** frameworks inspecting generic `Signature` attributes, method names, or annotations can observe metadata differences even when erased descriptors match.
- **Subclass/interface compatibility:** generic methods can cause the compiler to generate **bridge methods** when overridden; compile and verify against actual inheritance hierarchies.

You can observe part of this directly from the compiled `MigrationBoundaryDemo.java` file:

```bash
javap -s -p 'MigrationBoundaryDemo$LegacyDirectory'
javap -s -p 'MigrationBoundaryDemo$LegacyDirectoryAdapter'
```

Representative snippet from verified output:

```text
java.util.List findAll();
  descriptor: ()Ljava/util/List;

public java.util.List<MigrationBoundaryDemo$User> users();
  descriptor: ()Ljava/util/List;
```

The two methods have **different names**, so they cannot be treated as two binary versions of the same method; the excerpt only demonstrates that **raw `List` and `List<User>` share the return descriptor `Ljava/util/List;`**. For a real system, verifying binary compatibility requires comparing the entire current API against the proposed API, including method names, parameters, and hierarchy.

Similarly, running:

```bash
javap -s -p 'TypedGatewayDemo$SettingsGateway'
```

shows that the generic method `<T> T read(String, Class<T>)` has erased form `(String, Class)Object`. That is why the compiler must still rely on source-level generic checking together with the runtime `Class<T>` token.

## 9. Choosing Signatures According to Data Flow Direction

When updating public APIs, decide whether a parameter is a **source to read from** or a **target to write into**. Wildcards are not decoration; they express type constraints.

**Reading elements as a supertype** (*producer*):

```java
static double sumNumbers(java.util.List<? extends Number> source) {
    double sum = 0;
    for (Number number : source) {
        sum += number.doubleValue();
    }
    return sum;
}
```

Can accept `List<Integer>`, `List<Double>`, or `List<Number>`; the compiler forbids arbitrarily adding a `Number` to a source that might be a `List<Integer>`. The method is behaviorally complete and needs to be placed inside a class to run.

**Writing a type into a target accepting a supertype** (*consumer*):

```java
static void addLabels(java.util.List<? super String> target) {
    target.add("migrated");
    target.add("validated");
}
```

Can accept `List<String>` or `List<Object>`, since both can receive a `String`. When reading from `List<? super String>`, results can only be guaranteed as `Object`.

The **PECS** rule (Producer Extends, Consumer Super) helps when cleaning up legacy APIs with many callers. You do not need to change every parameter to `List<T>`: if a method only reads, `List<?>` or `List<? extends T>` usually expresses intent more clearly; if it writes, specify the allowed write type and consider `? super T`.

For mixed collections from legacy sources, a typed API like `List<User>` is valid only after having proof of the elements. PECS expresses data-flow direction; **it does not automatically validate data inside a raw collection**.

## 10. Compiler Warnings: Tracking Intentionally During Migration

While running:

```bash
javac -Xlint:rawtypes -Xlint:unchecked MigrationBoundaryDemo.java
```

the compiler warned about raw `List`, raw `ArrayList`, and unchecked `entries.add(entry)` in the simulated legacy part. Read the two groups separately:

| Warning group | Meaning | Preferred action |
| --- | --- | --- |
| `rawtypes` | A generic declaration/name is used without type arguments | Replace with a parameterized type or wildcard once the contract is known |
| `unchecked` | A call/conversion is not fully type-checked | Identify data source, add a validation step, or scope a proven cast |

In the `checkedUsers` adapter example, accepting `List<?>` and iterating `Object` introduces no unchecked casts of its own. Warnings stay confined to the legacy class to **pinpoint exact type debt** rather than spreading it into `UserDirectory`.

If you own the legacy source, you can eliminate warnings spot by spot by replacing raw fields, constructors, and methods with true generics. If the legacy code belongs to an external library, you do not need to force immediate external changes: prioritize a validated typed boundary.

Use `@SuppressWarnings("unchecked")` only after having a reliable argument proving type correctness; place it at the smallest possible scope, accompanied by rationale and matching tests. **Never use suppression as a migration step in place of data validation.**

## 11. Policies for `null`, Copying, and Data Mutability

You cannot treat "returns `List<User>`" as a complete contract without agreeing on the following properties.

### `null`

In `MigrationBoundaryDemo`, `checkedUsers` rejects `null` because pattern `instanceof User` evaluates to `false`. If business logic allows missing elements, pick an explicit model: default values, filtered removal with reporting, or `Optional` in another layer. `List.copyOf` also rejects `null` elements.

With `SettingsGateway.read`, if a key does not exist then `LegacySettings.read` returns `null`; `Class.cast(null)` returns `null`. A production API may need to distinguish **missing key** from **present key with null value**.

### Aliases and mutation rights

Returning a raw list directly from legacy code means typed code may be holding an **alias** to a mutable collection. Another legacy caller modifying the list can invalidate the new data's type after your check time.

Creating a new snapshot after validation eliminates sharing **list structure** in the sequential case of the example. However, if `User` elements have mutable fields or the source is modified concurrently during iteration, you need proper ownership management, locking/snapshotting, or deeply immutable data. `List.copyOf` is not a substitute for synchronization.

### Error detection timing

An adapter can choose:

- **Fail-fast**: throw an exception on the first invalid element, as in the example.
- **Collect-errors**: gather validation errors with indices and return a report for correction.
- **Intentional skip**: drop invalid elements if the business contract allows it and emit transparent metrics.

Never silently drop wrong-typed elements if consumers assume all data was processed completely.

## 12. Designing Tests for Each Boundary

A meaningful test suite for a migration boundary should be based on **the actual contract**, not just the updated signature. For `checkedUsers` in the example, test cases to consider:

| Test case | Input | Expectation |
| --- | --- | --- |
| Valid list | Two `User` instances | Two elements in order |
| Empty list | `List.of()` | Empty list |
| Wrong type | `User`, then `String` | Error clearly identifying index 1 |
| `null` value | One `null` element | Rejected per policy |
| Mutating source after conversion | Add element to raw list | Previous snapshot gains no element |
| Caller attempts to write to result | Call `add` on returned list | Rejected if using `List.copyOf` |
| Concurrent source modification | Modified while iterating | Requires contract-defined sync/checks |
| Mutable inner object values | Mutate element field | Decide whether deep copy is needed |

For `SettingsGateway`, test reading with the right token, wrong token, missing key, and `null` value. For existing public APIs, add build/caller compatibility tests to verify source and binary compatibility when required.

An especially valuable test: **put wrong-typed data into the raw source first**, then prove the typed side does not accept that data per the contract. Testing only the happy path can miss bugs tied to the very goal of migration.

## 13. Common Migration Mistakes

**1. Replacing `List` with `List<Object>` for every case.**

This throws away the chance to express domain types and can prevent passing `List<String>` to the API due to invariance. Choose by intent: `List<?>` for reading unknown types, `List<User>` after validation, or `List<Object>` when truly heterogeneous types are desired.

**2. Casting `(List<User>) raw` directly at every caller.**

Each cast widens the trusted region, checks no elements, and causes failures far from the source. Centralize conversion inside one verified adapter.

**3. Changing a generic return type and assuming data is already clean.**

A compile-time signature does not turn strings into users, does not reject bad elements at runtime, and does not isolate mutable lists. You need schema checks and a data ownership policy.

**4. Replacing an `Object` parameter with `User` on a public API while ignoring pre-compiled callers.**

The descriptor can change, causing `NoSuchMethodError` or other linkage errors when running un-updated binaries. Consider parallel adapters/methods and verify compatibility using builds, `javap`, or API checks.

**5. Silencing all `unchecked` warnings in new code.**

Warnings signal unproven type safety. Isolate them where legacy code meets new code, document specific reasons, and remove them gradually once sources become typed.

**6. Checking `instanceof List<?>` and thinking `List<User>` is validated.**

That check verifies only the container type; to validate elements, iterate and check each value, or rely on substantiated metadata/contracts.

**7. Mixing generics migration with silent API semantic changes.**

If the old API returned a live collection view while the new API returns an immutable snapshot, that is a behavioral change that must be communicated clearly. Sometimes an intentional change is necessary, yet callers and tests must be updated for the new contract.

**8. Trying to generify heterogeneous domains.**

If a `List` holds several distinct business record kinds, you may need an explicit common supertype (e.g., a sealed hierarchy), conversion into separate domain forms, or `List<?>` where information is insufficient. Forcing everything into `List<User>` does not solve data heterogeneity.

## 14. Practice Exercises: Applying Boundary-by-Boundary Migration

### Exercise 1 — Finding the danger point

Given a legacy API:

```java
static java.util.List load() {
    java.util.List data = new java.util.ArrayList();
    data.add("A");
    data.add(7);
    return data;
}
```

What is the risk if a new caller writes `List<String> x = (List<String>) load();`?

**Answer hint:** the unchecked cast does not check each element; the `Integer` will cause a failure when read expecting `String`. Migrate using an adapter that checks every element; fail-fast or return errors to the caller.

### Exercise 2 — Choosing the target signature

An API only iterates over elements of a `List` of unknown type; should it change to `List<Object>`?

**Answer:** usually `List<?>` is better. It accepts `List<String>`, `List<Integer>`, and many other forms without allowing arbitrary writes.

### Exercise 3 — Limits of `Class<T>`

An adapter taking `Class<T>` can check `String.class`. Can it verify an entire `List<String>` using only `List.class`?

**Answer:** no; `List.class` checks only the container class. The `String` type argument is erased in runtime descriptors; you must check elements or retain reliable metadata/contracts.

### Exercise 4 — Source, binary, and data

Is replacing `List findAll()` with `List<User> findAll()` always safe?

**Answer:** there is no blanket guarantee. Both return types use the same JVM `List` descriptor in this example, yet source callers, generic signature metadata, element contracts, collection mutability rights, and error handling can differ. Inspect the specific API, behavior, and consumers.

### Exercise 5 — Benefits of a snapshot

Why does the `checkedUsers` example create an `ArrayList<User>` and use `List.copyOf` instead of returning the raw list under a cast?

**Answer:** it both validates every element and creates a new list, preventing typed callers from sharing mutable structure with the legacy list; the result is also unmodifiable via standard list APIs.

### Exercise 6 — Prioritization order in a large system

A project has 20 callers using `Object` from a legacy library; only 3 callers need `User`. Should you immediately rewrite the library and all 20 callers?

**Answer hint:** define the contract for those 3 callers, build an adapter serving only `User`, test wrong-typed data, and migrate those 3 callers first. After observing the remaining paths, decide how to update the source and retire the legacy layer appropriately.

## Checklist for Applying to a Boundary

Before marking a migration path complete, answer:

1. Have **data sources, ownership, mutation sites**, and actual data types been identified?
2. Was the right new API signature chosen, avoiding raw types in consumer layers?
3. Is legacy data **validated before attaching a typed generic commitment**?
4. Is there an explicit policy for `null`, invalid elements, and error reporting?
5. Should the returned collection be an immutable snapshot or is a live view permitted?
6. Where do `rawtypes`/`unchecked` warnings remain, and are they understood and bounded?
7. Have public signature changes been evaluated for source, binary, and behavioral compatibility?
8. Have tests been run for valid/invalid types, empty data, post-return mutations, and legacy callers?

## Conclusion

**Migrating legacy APIs to generics boundary by boundary** turns type uncertainty into an explicit contract right where data enters modern code. Raw `List` or `Object` can remain temporarily on the legacy side; the adapter handles validation, conversion, error reporting, and data ownership protection; new consumers use `List<User>` or generic methods with `Class<T>` without arbitrary casts. Once data and callers in one region are verified, you can move to the next region while checking API compatibility across compiler, runtime, and bytecode.