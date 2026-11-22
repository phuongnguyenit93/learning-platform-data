# Keeping Constructors, Setters, and Object Invariants as Design Boundaries When Using Reflection

A `Field` may be writable via Reflection, yet that does not mean the write is **valid by business rules**. For instance, `Registration` requires capacity from 1 to 10, attendees not exceeding capacity, and the list not being mutated externally. Directly assigning `capacity = 0` breaks the invariant even though the JVM accepts the operation.

This article focuses on **state boundaries**: creating via validated constructors/factories, updating via setters or domain methods that maintain invariants, and publishing objects only after validation. For multi-field relationships, two independent setters can expose invalid intermediate state; an atomic operation under the domain contract is usually better. A counterexample uses `Field.setInt` to demonstrate why accessibility does not replace domain contracts.

## 1. Constructors, setters, and invariants have distinct roles

An **invariant** is a condition an object is designed to uphold throughout its observable lifecycle. For example, a `Registration` class has:

- `code` is neither `null` nor blank; the identifier does not change after creation.
- `capacity` lies in the range `1..10`.
- `attendees.size() <= capacity`.
- The attendee list must not be silently mutated by external callers bypassing validation methods.

These rules are enforced at the following boundaries:

| Boundary | Responsibility | Example |
|---|---|---|
| Constructor or static factory | Accept minimum required values, validate before the object can be used | `new Registration("JAVA", 3)` |
| Intentional setter | Verify that a single change is valid against current state | `setCapacity(2)` |
| Business method | Protect multi-field rules and express intent clearly | `register("Lan")`, `reschedule(start,end)` |
| Getter / view | Provide a way to observe state without exposing mutable internals | `List.copyOf(...)`, unmodifiable list |
| Reflection adapter | Look up signatures, convert arguments, **invoke public constructors/methods**, and preserve errors | `Constructor.newInstance(...)`, `Method.invoke(...)` |

A public setter is **not automatically good** just because it has a `set` prefix. A setter allowing arbitrary changes to `id` or individual fields of a cross-field invariant can leave the object in an invalid state at times. Data that should not change should stay `final` or expose only an atomic validated update. In domain models, method meaning usually matters more than JavaBeans naming conventions.

## 2. Three Reflection paths and their consequences

Suppose runtime already has `Class<?>` and configuration data:

~~~text
External input (config / JSON / plugin metadata)
                     |
                     v
       Normalize + structural validation
                     |
          Select domain boundary
           /                  \
          v                    v
 Constructor/factory      Setter/method
          |                    |
          +---------+----------+
                    v
      Object with valid invariants
                    |
                    v
            Further operations
~~~

### Preferred path: invoke an appropriate constructor

~~~java
Constructor<Registration> constructor =
        Registration.class.getConstructor(String.class, int.class);
Registration registration = constructor.newInstance("JAVA", 3);
~~~

This is an **excerpt** from the full program in section 3. `getConstructor(...)` only finds **public constructors** with the exact **parameter type** list. `int.class` differs from `Integer.class` during signature lookup, even though `newInstance(...)` can accept an `Integer` argument that gets unboxed when invoking a constructor taking `int`.

When a constructor throws `IllegalArgumentException` due to invalid data, `Constructor.newInstance` throws `InvocationTargetException` whose `getCause()` is the original exception. Tools must not ignore that rejection and try assigning fields through another route.

### Update path: invoke a public setter or method

~~~java
Method method = Registration.class.getMethod("setCapacity", int.class);
method.invoke(registration, 2);
~~~

`getMethod(...)` finds a public method with the matching name and parameter types. `Method.invoke(...)` runs the **logic inside the setter**: valid range, correlation with other fields, update, and postconditions guaranteed by the class itself. If the setter rejects it, the target error is wrapped in `InvocationTargetException`; unwrapping the cause aids diagnostics and gives no excuse to skip validation.

### Risky path: writing fields directly

~~~java
Field field = Registration.class.getDeclaredField("capacity");
field.setAccessible(true); // Illustrative only in an environment with appropriate permissions
field.setInt(registration, 0);
~~~

**Do not use this as an application data update strategy.** If deep access is allowed, `Field.setInt(...)` writes into the field **without calling `setCapacity`**. The object can hold `capacity = 0` even though the setter forbids it. This is a failure at the **domain contract** level, even when the Reflection operation succeeds technically.

`getDeclaredField` only helps locate a field declared directly on the class, including private fields. It does not mean the system permits reading/writing that field in every Java Platform Module System (JPMS) configuration. `setAccessible(true)` can be denied if a package in another named module is not opened (`opens`). Deep access also does not grant permission to mutate every `final` field; in particular, record fields, static final fields, and final fields of hidden classes have specific restrictions. Do not treat `setAccessible` as a default step in every tool.

## 3. Complete Java 17+ program, including counterexample

Create file **`ConstructionBoundaryDemo.java`** with all the code below. In the program, `Registration` is a `public static final` class nested inside a standalone program; invariants are defined in the constructor, `setCapacity`, and `register`. Near the end, there is **an intentional direct field write test** proving the setter was bypassed; the program then restores valid state through the setter.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class ConstructionBoundaryDemo {
    public static final class Registration {
        private final String code;
        private int capacity;
        private List<String> attendees = List.of();

        public Registration(String code, int capacity) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }
            this.code = code;
            setCapacity(capacity);
        }

        public void setCapacity(int newCapacity) {
            if (newCapacity < 1 || newCapacity > 10) {
                throw new IllegalArgumentException("capacity must be 1..10");
            }
            if (newCapacity < attendees.size()) {
                throw new IllegalArgumentException("capacity below attendees");
            }
            capacity = newCapacity;
        }

        public void register(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            if (attendees.size() == capacity) {
                throw new IllegalStateException("full");
            }
            List<String> next = new ArrayList<>(attendees);
            next.add(name);
            attendees = List.copyOf(next);
        }

        public String getCode() {
            return code;
        }

        public int getCapacity() {
            return capacity;
        }

        public List<String> getAttendees() {
            return attendees;
        }

        public boolean validState() {
            return capacity >= 1 && capacity <= 10
                    && attendees.size() <= capacity;
        }
    }

    @FunctionalInterface
    interface ReflectionAction {
        void run() throws ReflectiveOperationException;
    }

    static void showRejection(String label, ReflectionAction action)
            throws ReflectiveOperationException {
        try {
            action.run();
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(label + " -> " +
                    cause.getClass().getSimpleName() + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Constructor<Registration> constructor =
                Registration.class.getConstructor(String.class, int.class);
        Method register = Registration.class.getMethod("register", String.class);
        Method setCapacity = Registration.class.getMethod("setCapacity", int.class);

        Registration r = constructor.newInstance("JAVA", 3);
        register.invoke(r, "Lan");
        register.invoke(r, "Minh");
        System.out.println("created = " + r.getCode() + ", " + r.getCapacity()
                + ", " + r.getAttendees() + ", valid=" + r.validState());

        showRejection("bad setter", () -> setCapacity.invoke(r, 1));
        showRejection("bad constructor", () -> constructor.newInstance(" ", 3));

        try {
            r.getAttendees().add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("external list mutation -> " +
                    ex.getClass().getSimpleName());
        }

        setCapacity.invoke(r, 2);
        System.out.println("setter success = " + r.getCapacity()
                + ", valid=" + r.validState());

        Field capacityField = Registration.class.getDeclaredField("capacity");
        capacityField.setAccessible(true);  // DEMO ONLY: breaks encapsulation.
        capacityField.setInt(r, 0);          // Deliberately bypasses setter.
        System.out.println("field bypass = " + r.getCapacity()
                + ", valid=" + r.validState());

        setCapacity.invoke(r, 2);
        System.out.println("restored = " + r.validState());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 ConstructionBoundaryDemo.java
java ConstructionBoundaryDemo
~~~

**Verified stdout when running Java 17-compatible in unnamed module:**

~~~text
created = JAVA, 3, [Lan, Minh], valid=true
bad setter -> IllegalArgumentException: capacity below attendees
bad constructor -> IllegalArgumentException: code required
external list mutation -> UnsupportedOperationException
setter success = 2, valid=true
field bypass = 0, valid=false
restored = true
~~~

**Interpretation of each result group:**

1. The constructor checks `code` and calls `setCapacity`. Two `register.invoke(...)` calls add attendees into a new list, updated via `List.copyOf(...)`; initial state is valid.
2. `setCapacity.invoke(r, 1)` executes the setter, but the group already has two attendees so it is rejected. `InvocationTargetException.getCause()` is `IllegalArgumentException("capacity below attendees")`. There is no partial update to `capacity`.
3. `constructor.newInstance(" ", 3)` executes the constructor; the blank code causes the constructor to reject. This is a case of the **target constructor** throwing an exception, whose cause is preserved by the Reflection wrapper.
4. `getAttendees().add("An")` fails because the returned list is unmodifiable. If the getter exposed the internal mutable `ArrayList`, callers would have a way to break the invariant **without Reflection**.
5. `setCapacity.invoke(r, 2)` succeeds because `2` fits two attendees, after which `validState()` remains `true`.
6. The counterexample `Field.setInt(r, 0)` writes directly to `capacity` without invoking setter logic, resulting in `valid=false`. The final snippet restores state via the valid setter.
7. The program runs in an unnamed module. In a named-module application, `setAccessible(true)` may fail; that further underscores that tools should not be designed around always having permission to open private fields.

`showRejection` only catches `InvocationTargetException` for the example. In a real binder, handle `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, `IllegalArgumentException` from mismatched Reflection arguments, and module-system errors separately. Never lump all errors under a single "validation failed" label.

## 4. Design boundaries for Reflection tools

When writing a mapper, small DI container, plugin loader, or configuration ingestion tool, make decisions according to the **initialization/update contract**.

| Need | Preferred approach | Avoid |
|---|---|---|
| Construct an object with required fields | Parameterized constructor, named factory, builder with validating `build()` | Creating an empty object and stuffing private fields |
| Change an independent value | Validated public method, e.g. `setCapacity(...)` | `Field.set(...)` bypassing the setter |
| Change multiple interdependent fields | Atomic update method, constructing a new immutable object | Calling multiple setters exposing invalid intermediate state |
| Populate an immutable value object | Constructor / record canonical constructor | Directly writing `final` fields after construction |
| Populate collections | Convert input data and defensively copy | Retaining caller's mutable `List` reference |
| Schema lacks required method | Report unsupported mapping, or use an adapter defined by class owner | Trying `setAccessible(true)` to "circumvent" the contract |
| Invalid domain value | Return validation error preserving cause and property name | Skipping validation just to force object creation |
| Pure data DTO | May use agreed binder/Bean conventions | Applying the same assumption to every domain entity |

**Metadata is not a strong enough contract.** Knowing a field has type `int` only guarantees Java type rules; it does not say what range the capacity must fall within or how it depends on registered attendees. Even with `@NotNull` or `@Min` annotations, the tool must know explicitly when and how validators run. Reading annotations via Reflection **does not automatically trigger validation**. If a tool decides to use Bean Validation, it must invoke the validator per real architecture and control when the object becomes visible.

A sensible mapping pipeline:

~~~text
Untrusted input
    |
    v
Parse per schema -> convert types -> structural error if invalid
    |
    v
Select constructor/factory per permitted contract
    |
    v
Invoke constructor -> domain validation
    |
    +-- Reject -> return error, preserve cause, do not publish object
    |
    v
Invoke permitted update methods (if any)
    |
    +-- Reject -> discard unpublished object / rollback per architecture
    |
    v
Confirm object is valid, only then publish
~~~

If a tool constructs an object successfully and later setters fail, the tool must ensure **the object has not yet been published or persisted into the system** before completion. No automatic transaction comes merely from using Reflection. For updates on an existing shared object, design an atomic operation or appropriate transaction/domain command; failing partway can leave intermediate state.

## 5. Multi-field invariants: separate setters may be insufficient

Consider a time window:

~~~java
public record TimeWindow(LocalDate start, LocalDate end) {
    public TimeWindow {
        if (start == null || end == null || end.isBefore(start)) {
            throw new IllegalArgumentException("invalid window");
        }
    }
}
~~~

This is an **illustrative code snippet** that must be placed in a valid Java file with `import java.time.LocalDate;` if compiled separately. The record has a canonical constructor verifying `start <= end`. When an update is needed, construct a new record through the valid constructor:

~~~java
TimeWindow next = new TimeWindow(newStart, newEnd);
~~~

If you design a mutable class with independent `setStart` and `setEnd`, call order can temporarily violate `start <= end`. For example, currently day 10 to day 20, wanting to change to day 21 to day 30: calling `setStart(21)` first creates a moment where `start > end`; calling `setEnd(30)` first might work, yet depends on the data. A `reschedule(newStart, newEnd)` method validating the pair of values **before committing both** is far clearer.

Lesson for tools building objects from multiple fields: **"Having setters" does not mean "can be set in arbitrary order".** The tool must know the protocol defined by the class owner. Full-argument constructors, immutable value objects, or builders are usually better suited when invariants span multiple fields.

### Do not inadvertently call overridable methods from constructors

In the demo, `Registration` is `final`, so no subclass overrides `setCapacity`. However, in a **non-`final`** class, calling an overridable setter from a constructor dispatches to the subclass method before the subclass state is fully initialized. This can cause bugs or `this` escape.

A safer general design: the constructor calls a **non-overridable private helper** to validate and then assigns the field; the setter calls that same helper. Illustrative snippet:

~~~java
private static int requireCapacity(int value) {
    if (value < 1 || value > 10) {
        throw new IllegalArgumentException("capacity must be 1..10");
    }
    return value;
}

// Inside constructor or setter:
this.capacity = requireCapacity(value);
~~~

The snippet above does not compile standalone because it assumes a class containing field `capacity` and variable `value`. Do not build a Reflection abstraction forcing every class to have a no-args constructor just to assign fields afterward.

## 6. Setters, fields, accessors, and the Java Platform Module System

Common Reflection APIs:

| API | Search scope | What does it guarantee? |
|---|---|---|
| `type.getConstructor(paramTypes)` | **public** constructor with exact signature | Constructor metadata; calling remains subject to access rules |
| `type.getDeclaredConstructor(paramTypes)` | Constructor declared in type, regardless of modifier | Metadata; may not be invocable if non-public |
| `type.getMethod(name, paramTypes)` | Visible **public** method, including matching inherited | Method metadata; `invoke` can still fail |
| `type.getDeclaredMethod(name, paramTypes)` | Method declared directly in type | Includes non-public; grants no invocation permission |
| `type.getField(name)` | Visible public field | Does not run setter on `Field.set` |
| `type.getDeclaredField(name)` | Directly declared field, including private | Grants no read/write permission or validation |
| `AccessibleObject.trySetAccessible()` | Attempts to open access if runtime permits | Returns `false` when unable to open; does not turn member into domain API |

**JPMS:** `exports` and `opens` are two different concepts. Package `exports` permits using public APIs from another module under corresponding conditions; deep Reflection into non-public members of another module typically requires `opens` to the tool's module. Passing `--add-opens` to the JVM can help a specific integration case, yet it is a deployment/module-policy decision, **not the default fix** when a tool cannot find a setter.

**`final` is not a license to overwrite:** Since Java 17 `Field`, certain kinds of final fields cannot be mutated via Reflection, such as `static final`, final fields in records, and final fields in hidden classes. For other final instance fields, Javadoc warns that mutating them after the object has been published can produce unpredictable results. Tool designs should not rely on mutating final fields to "re-hydrate" domain entities.

**`private` does not automatically make an object immutable:** If a getter returns a mutable `List` held internally by the object, callers can still mutate the data without Reflection. In the demo, `List.copyOf` creates an unmodifiable list to preserve the boundary; when accepting mutable input, proactively create a snapshot instead of retaining the caller's reference.

### Method signatures must match; do not infer from names

Reflection looks up methods by **name and parameter type array**, e.g., `getMethod("setCapacity", int.class)`. `getMethod("setCapacity", Integer.class)` will not automatically match an `int` parameter. Values passed to `Method.invoke` may undergo invocation conversions like unboxing, yet the signature lookup step is separate. With overloads, naively taking the first method starting with `"set..."` can select the wrong contract. A binder should select methods from an explicit schema or fail with a helpful diagnostic.

## 7. Validation and exceptions must not disappear

If a constructor or setter rejects data, the reflective call surfaces an exception at the call site:

~~~java
try {
    method.invoke(target, value);
} catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    throw new IllegalStateException("Could not update property", cause);
}
~~~

This is an **illustrative handling snippet**: variables `method`, `target`, and `value` are assumed present, and `IllegalAccessException` must also be handled. Wrapping in `IllegalStateException(String, Throwable)` preserves the cause, allowing logs and callers to trace the domain error. You may rethrow the original exception type if the API contract allows. Never extract only `cause.getMessage()` and construct a new exception without a cause.

Distinguish:

- **Schema or conversion error:** JSON string `"abc"` fails conversion to `int`, method does not exist, or receiver has wrong type. This is an adapter/binding error; `Method.invoke` may throw `IllegalArgumentException` directly due to bad arguments.
- **Type-valid input violating domain invariant:** `setCapacity(0)` exists, the `int` argument is valid by type, yet the setter throws `IllegalArgumentException("capacity must be 1..10")`; Reflection wraps the target error in `InvocationTargetException`.
- **Missing access rights:** `IllegalAccessException` or `InaccessibleObjectException` relates to accessibility/module boundaries. Do not fix by removing validators.
- **System errors:** `LinkageError`, `ExceptionInInitializerError`, or `Error` must not be treated as validation errors; do not catch `Throwable` and pretend a single property was simply invalid.

If a binder returns a list of errors to the user, record **property name, expected type, allowed values, or safe domain message**, while keeping the cause for internal logs where appropriate. Do not expose stack traces or configuration secrets in external responses.

## 8. Choosing designs by object type

**Pure DTO / JavaBean:** Can fit no-args constructors and setters if the class itself is intentionally a data-transfer container. If validation applies, run an explicit validation step after binding and before publishing/executing.

**Domain entity:** Prefer constructors/factories for required state and domain methods over blanket setters. Entities may be bound by lifecycle, transactions, and aggregate invariants; a generic Reflection binder rarely understands all of them.

**Immutable value object / record:** Constructors/canonical constructors and defensive copies ensure every object is constructed in a valid state. When changes are needed, create a new object; do not "poke" `final` fields. For records with a `List` component, proactively use `List.copyOf` in the constructor if collection mutation must be prevented.

**Third-party class without setters:** Read the library's API to find official constructors/builders/factories or adapters. Never treat missing setters as a defect to work around via deep field access.

**Serialization and ORM:** Some frameworks use specialized instantiation, proxies, bytecode enhancement, or field access per published mappings. These are deliberate trade-offs, **not rules to generalize to every Reflection tool**. If a framework intentionally uses field access, responsibility for upholding invariants at designated validation/lifecycle points must be designed, documented, and tested.

**Plugin loader / configurable service:** Prefer interface/factory contracts or `ServiceLoader` when possible; only instantiate classes from runtime names via Reflection when class sources are controlled and contracts are verified. Calling trusted public constructors avoids creating half-initialized instances.

## 9. Checklist for Reflection tool authors

Before supporting a new kind of object, determine:

1. **What constitutes a valid object?** List invariants of each field and cross-field relationships.
2. **Who owns validation?** Constructor, factory, domain method, external validator, or a clearly defined combination?
3. **At which step may the object be published?** Publish only after all required construction/update and validation steps succeed.
4. **Which APIs does the tool use?** Prefer valid public constructors/methods; never fall back to private field writes when rejected.
5. **Are there mutable aliases?** Check defensive copies for collections, arrays, mutable date/time types, and nested objects if needed.
6. **Are multiple fields interdependent?** Use atomic methods, full-parameter constructors, or builders instead of setters in arbitrary order.
7. **Are JPMS permissions satisfied?** Verify access before invoking, report missing access clearly; do not rely on `setAccessible` by default.
8. **Do exceptions preserve causes?** Separate schema/Reflection errors from domain validation, without swallowing target errors.
9. **Should imposing JavaBeans be avoided?** Domain types do not need to expose setters for every property.
10. **Are invalid states tested?** Verify bad inputs are rejected and published objects never transition into invalid states.

### Practice exercises

1. In the `Registration` example, try `constructor.newInstance("JAVA", 0)`. Distinguish the outer exception from its cause and explain why the constructor calls `setCapacity`.
2. Replace `setCapacity.invoke(r, 1)` with `Field.setInt(r, 1)` in an isolated test. Which invariant is violated and why?
3. Change `getAttendees()` to directly return the internal mutable `ArrayList`. Describe how a caller can break the invariant without using Reflection.
4. Design a `replaceAttendees(List<String>)` command ensuring both the list and capacity remain valid, committing only after checks pass.
5. Given a `start/end` date pair, write a `reschedule(start,end)` method checking both before updating. Explain the weakness of two independent setters.
6. When running in a named module, explain why `getDeclaredField` can succeed yet `trySetAccessible()` returns `false`.
7. For a record containing `List<String>`, write a canonical constructor validating the data and using `List.copyOf`. Try mutating the collection from the caller.

**Key takeaway:** Reflection helps locate and invoke code at runtime; it **does not replace** a class's contract. For objects with invariants, constructors/factories and validated update methods are the primary boundaries. Avoid turning `Field.set` into a shortcut when the model rejects a change, and intentionally design publication timing, atomicity, defensive copies, access policies, and exception diagnostics.

### References

- [Javadoc Java 17 — `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [Javadoc Java 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Javadoc Java 17 — `Field` and final-field write limits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Javadoc Java 17 — `AccessibleObject` and JPMS limits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Javadoc Java 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))