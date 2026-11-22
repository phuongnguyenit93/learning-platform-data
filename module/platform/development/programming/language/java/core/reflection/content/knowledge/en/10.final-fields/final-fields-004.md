# Final Fields in Records and Hidden Classes: Reflection Limits in Java 17+

## 1. The Problem to Understand

A common mistake when learning Java Reflection is assuming that: **if `Field.setAccessible(true)` succeeds, any `final` field can be modified**. This is **false**.

Since Java 17 (and in corresponding APIs already present in earlier versions), Java distinguishes a group of **non-modifiable final fields**. The three key groups according to the `java.lang.reflect.Field` and `AccessibleObject` documentation are:

1. All `static final` fields declared in any class/interface.
2. All `final` fields declared in a **record class**.
3. All `final` fields declared in a **hidden class**.

For this group, even if the calling code has successfully enabled deep access with `setAccessible(true)` or `trySetAccessible()`, Reflection can only **bypass access-control checks in order to read**; it **does not grant write permission** on those fields.

Conceptual example:

```java
Field field = SomeRecord.class.getDeclaredField("name");
field.setAccessible(true);      // May succeed if the module allows it.
Object value = field.get(obj);  // Can be read.
field.set(obj, "changed");      // IllegalAccessException: final field cannot be modified.
```

These illustrative lines require a corresponding `SomeRecord` definition and `obj` instance, and do not form a standalone Java program. The complete compilable/runnable program in section 7 will demonstrate the rule using both a record and a hidden class.

This lesson focuses on **write permissions of `Field` when the declaring class is a record or a hidden class**. This must be distinguished from two other concepts: Java access levels (`private`/`public`) and field hiding (a subclass declaring a field with the same name as a superclass). A **hidden class** is a kind of class defined by the runtime via a specialized mechanism; it does not mean "a field hidden by another class".

## 2. Why `final` Matters, and Why Reflection Has Exceptions

### 2.1. `final` in ordinary Java programming

An instance `final` field is normally assigned when the object is initialized and cannot be reassigned with ordinary Java syntax after valid initialization. Example:

```java
final class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

`Ticket.code` is a `private final` field: external code cannot assign `ticket.code = "x"`. That does not necessarily mean **every** reflective operation on every ordinary instance final field is forbidden at the API level.

On Java 17, the `Field.set` documentation still notes a very narrow case where Reflection can write an **instance final field in an ordinary class** when `setAccessible(true)` has succeeded. That is primarily meaningful during object restoration/deserialization workflows involving blank final fields **before** the object is published to other parts of the program. If a final field is modified afterward, observed results can become unpredictable due to optimizations and the special guarantees of the Java memory model.

**Do not use this historical capability as a basis for designing APIs that mutate immutable objects.** The rules for records and hidden classes are even stricter: `final` fields declared by these classes are **non-modifiable**, even when access checks have been bypassed successfully.

### 2.2. Same `final` keyword, different write conditions

| Declaring class / field type | Can access checks be bypassed to read? | Can `Field.set(...)` write the `final` field? |
|---|---|---|
| `static final` field in any class/interface | Yes, if allowed by the runtime | **No** |
| `final` instance field declared in a `record` | Yes, if allowed by the runtime | **No** |
| `final` field declared in a `hidden class` | Yes, if allowed by the runtime | **No** |
| `final` instance field of an ordinary class, not record/hidden | Yes, depending on permissions/modules | On Java 17, supported under very narrow conditions when suppressing access checks; should not be used to update live objects |
| **Non-`final`** instance field | Yes, depending on permissions/modules | Writable if other conditions (receiver, data type, permissions, etc.) are valid |

This table describes the behavior of the **Java 17 Reflection API**; it does not guarantee successful access across named modules or write capability for non-final field kinds. For instance fields, the receiver must be a compatible object; for static fields, `Field.set` ignores the receiver and `null` may be passed.

Scope note for the rule: in a **hidden class**, only **fields with the `final` modifier** belong to the non-writable group; non-final fields in a hidden class do not automatically become immutable just because the class is hidden.

## 3. Record: Components Produce `private final` Fields

### 3.1. What is a Record within the scope of this lesson?

A record is a class declaration form for structured data; **record components** appear in its header. Example:

```java
record UserId(long value, String source) {
}
```

For `UserId`, the compiler generates members corresponding to the record components, including:

- Two **private final instance fields** corresponding to `value` and `source`.
- Two accessor methods `value()` and `source()`.
- A canonical constructor accepting parameters matching the record header (unless another valid form is explicitly declared).
- Implementations of `equals`, `hashCode`, and `toString` per the record contract.

A record is a `final` class, cannot serve as a superclass for inheritance in the usual way, and cannot arbitrarily declare additional instance fields beyond those corresponding to its components under the language rules. A record may have its own static fields and methods. Component fields are `private final` even though the header syntax simply writes `record UserId(long value, ...)`.

Records provide **shallow immutability** at the component-reference level: a component field cannot be reassigned after initialization, but if a component holds a reference to a mutable object such as a `List`, the internal state of the referenced object can still change unless copied/protected. Field immutability and deep immutability of the entire object graph are two different things.

### 3.2. How does Reflection view record fields?

`Class.isRecord()` returns `true` for a record class. The `Class` object also provides `getRecordComponents()` to list components at the record's semantic level.

```java
record UserId(long value, String source) {}

Class<?> type = UserId.class;
System.out.println(type.isRecord());        // true

Field field = type.getDeclaredField("source");
System.out.println(field.getName());        // source
System.out.println(Modifier.isFinal(field.getModifiers())); // true
```

This example snippet assumes imports of `java.lang.reflect.Field` and `java.lang.reflect.Modifier`, and handling of `NoSuchFieldException`. It illustrates looking up metadata without yet reading or writing values.

There are two ways to read the information:

- **Via the record API:** `userId.source()` or the accessor method returns the value; this is the convenient approach in application code.
- **Via Reflection:** `getDeclaredField("source")` followed by `Field.get(userId)` if access permissions allow.

Use `getRecordComponents()` when you want **record components in exact declaration order**, along with their types, accessors, and associated annotations. Use `getDeclaredFields()` when you genuinely need field metadata: a record can also contain static fields that are not components. Do not assume `getDeclaredFields()` matches `getRecordComponents()` in either contents or order.

### 3.3. Why doesn't `setAccessible(true)` modify a record component?

Suppose we have a record:

```java
record Person(String name, int age) {}
```

`name` and `age` are final fields declared by the record class. Even with metadata and appropriate access permissions:

```java
Person p = new Person("An", 25);
Field nameField = Person.class.getDeclaredField("name");

if (nameField.trySetAccessible()) {
    System.out.println(nameField.get(p)); // An
    nameField.set(p, "Binh");             // IllegalAccessException
}
```

This is an illustrative snippet in a context where `Field` is imported and checked exceptions are handled. `trySetAccessible() == true` only indicates that the runtime permits **bypassing access-level checks**. It does not make a final field in a record writable.

**The right way when a new value is needed** is to create a new record instance through a valid constructor/factory:

```java
Person updated = new Person("Binh", p.age());
```

A record is a way of passing data by component values, not a mechanism for updating individual fields after initialization. If a record is stored in a collection/map, replace the reference to the record with a new instance according to your application's design.

## 4. Hidden Class: Runtime-Defined Class That Still Disallows Writing Final Fields

### 4.1. A Hidden Class is not a `private` class

A **hidden class** is introduced through Java runtime / Method Handles mechanisms, supporting dynamic implementations (such as internal classes generated by frameworks or the runtime), where the class does not need to be discoverable by binary name through ordinary mechanisms.

Differences from ordinarily declared and loaded classes:

- Can be defined from class-file bytes via `MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)`.
- `Class.isHidden()` returns `true` for a hidden class.
- A hidden class **is not discoverable via ordinary binary-name lookup mechanisms**; for example, you cannot rely on `Class.forName(className)` to find a hidden class the way ordinary classes are found.
- It still has a `Class<?>` object, constructors, methods, and fields that code holding a reference to the class can inspect using Reflection/Method Handles.
- A hidden class is defined within an appropriate package/module/lookup context and has its own rules for discoverability, linkage, and lifecycle; it is not automatically synonymous with `private` or with external code being unable to hold its `Class<?>`.

A hidden class is completely different from:

- **Nested class**: a class declared inside another class.
- **Anonymous class**: a class without a simple name in source code.
- **Field hiding**: a subclass defining a field with the same name as its superclass.
- **`private` member/class**: language-level access control.

An ordinary nested class **is not automatically a hidden class**; for example, `Outer.Inner.class.isHidden()` normally returns `false`. To obtain an actual hidden class, an appropriate definition mechanism must be used, or the class must be created by the runtime/framework.

### 4.2. Why can't a hidden class's final field be modified?

Java Reflection treats every `final field` **declared in a hidden class** as non-modifiable. The "hidden" condition applies to the **declaring class of the field**: check `field.getDeclaringClass().isHidden()` rather than only inspecting the class of the object passed as the receiver.

```java
Field f = hiddenClass.getDeclaredField("token");

System.out.println(f.getDeclaringClass().isHidden()); // true
System.out.println(Modifier.isFinal(f.getModifiers())); // true
```

If `token` is final, even if `f.setAccessible(true)` succeeds under access conditions, `f.set(hiddenObject, "new")` will throw `IllegalAccessException`. These lines illustrate metadata; the full way to create a hidden class and `hiddenObject` appears in section 7.

This constraint lets the runtime rely on the stable semantics of final fields in dynamically generated classes. Dynamic classes frequently participate in execution optimizations or specialized linkage, so allowing Reflection to arbitrarily reassign initialized final values would break implementation assumptions.

For a **non-final field** declared in a hidden class, whether `Field.set` succeeds still depends on access permissions, receiver, and data type. Do not treat `isHidden()` as a blanket ban on all field operations.

### 4.3. Creating a hidden class and using class-file bytes

`Lookup.defineHiddenClass` requires:

- Valid class-file bytes matching the package of the lookup class and the API's constraints.
- A `MethodHandles.Lookup` with sufficient privileges (full privilege access).
- Initialization choice and `ClassOption` values if needed. `NESTMATE` allows defining the hidden class as a nestmate of the lookup class per the API.

The API returns a `Lookup` corresponding to the defined hidden class; `lookupClass()` retrieves the `Class<?>` object of that hidden class. Only calling `Class.isHidden()` on **the class actually returned by `defineHiddenClass`** properly verifies this case. Do not conflate the template class used to obtain the bytes with the newly VM-defined hidden class.

## 5. Access Permission and Write Permission Are Two Independent Conditions

### 5.1. What does `trySetAccessible` mean?

`Field` extends `AccessibleObject`. Some common APIs:

| API | Role |
|---|---|
| `field.canAccess(receiver)` | Checks whether the field can currently be accessed with an appropriate receiver; does not change state |
| `field.trySetAccessible()` | Attempts to enable access-check suppression; returns a boolean indicating success/failure |
| `field.setAccessible(true)` | Requests enabling access-check suppression; may throw `InaccessibleObjectException` if not opened |
| `field.get(receiver)` | Reads the value when permitted |
| `field.set(receiver, value)` | Requests writing the value, also subject to specific restrictions for final fields |

For a non-modifiable final field, `setAccessible(true)` **does not enable write capability**. This is not a contradiction: **bypassing Java access-permission checks** and **being allowed to modify a final field** are two different conditions.

A typical flow:

```text
getDeclaredField(...)                    -> Field metadata
   |
   +-- trySetAccessible() == false       -> cannot enable access-check suppression
   |
   +-- trySetAccessible() == true        -> can bypass Java access checks
           |
           +-- get(receiver)             -> can read
           |
           +-- set(receiver, newValue)
                  |
                  +-- final field in record/hidden?
                         |
                         +-- Yes         -> IllegalAccessException
                         +-- No          -> check static final, field kind,
                                          receiver, data type, other conditions
```

The diagram only illustrates the write-permission branch relevant to this lesson, and does not list every Reflection exception/validation. A `get` call can still fail if the receiver is wrong or the calling program lacks permission; a `set` call on a non-final field also requires type and receiver checks.

### 5.2. Module boundaries remain in effect

The Java Platform Module System (JPMS) enforces strong encapsulation. For a class in another named module, `trySetAccessible()` may return `false` if the package is not appropriately opened via `opens` to the caller's module. When `setAccessible(true)` cannot enable suppression, it may throw `InaccessibleObjectException`.

For example code running on the classpath in the **unnamed module**, calling `trySetAccessible()` on a private field in the same module may succeed. However, do not generalize that every framework accessing private fields across any module will succeed.

Crucially: **even when a package is fully `opens`**, a `final` field declared by a record or hidden class still does not become writable via `Field.set`.

## 6. Exact Rules of `Field.set` on Java 17

According to the contract of `Field.set(Object, Object)`, a final field can only be granted write permission via this Reflection path if all of the following conditions hold simultaneously:

1. `setAccessible(true)` (or `trySetAccessible` succeeding with equivalent effect) has enabled suppression on **that exact `Field` object**.
2. The field is **not `static`**.
3. The declaring class of the field is **not a hidden class**.
4. The declaring class of the field is **not a record class**.

If any of the conditions above is not satisfied, `Field.set` throws `IllegalAccessException` for a final field. These conditions are separate from checking the receiver object and whether the input value can be converted.

| Check | Example | Conclusion |
|---|---|---|
| `Modifier.isFinal(f.getModifiers())` | `true` | The field has the final modifier |
| `Modifier.isStatic(f.getModifiers())` | `true` | Final + static is non-modifiable |
| `f.getDeclaringClass().isRecord()` | `true` | A final field in a record is non-modifiable |
| `f.getDeclaringClass().isHidden()` | `true` | A final field in a hidden class is non-modifiable |
| `f.trySetAccessible()` | `true` | Access checks can be suppressed; **does not** imply write permission |

You can use these checks to determine beforehand that your code **should not call `set`**. Nevertheless, application code should still handle exceptions when performing real Reflection operations, because metadata, module permissions, receiver types, and runtime environments can produce additional errors.

## 7. Complete Java 17+ Program: Readable but Not Modifiable

This example **actually creates a hidden class**, rather than merely naming an ordinary class "Hidden". It contains:

- `Order` as a record with component `label`, from which the compiler generates a final field.
- `HiddenTemplate` as an ordinary static nested class, whose **class-file bytes** are used to define a **new hidden class** via `Lookup.defineHiddenClass`.
- `Ordinary` for metadata comparison: an ordinary class with a private final field that is neither a record nor a hidden class.

### 7.1. Source code

Save as **`RecordHiddenFinalDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class RecordHiddenFinalDemo {
    record Order(int id, String label) {}

    public static class HiddenTemplate {
        private final String code;

        public HiddenTemplate(String code) {
            this.code = code;
        }
    }

    static class Ordinary {
        private final String code;

        Ordinary(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws Exception {
        Order order = new Order(7, "ready");
        Field recordField = Order.class.getDeclaredField("label");

        System.out.println("record class: " + Order.class.isRecord());
        System.out.println("record field final: "
                + Modifier.isFinal(recordField.getModifiers()));
        System.out.println("record open: " + recordField.trySetAccessible());
        System.out.println("record read: " + recordField.get(order));

        try {
            recordField.set(order, "updated");
            System.out.println("record write: success");
        } catch (IllegalAccessException ex) {
            System.out.println("record write: "
                    + ex.getClass().getSimpleName());
        }

        String resource = "RecordHiddenFinalDemo$HiddenTemplate.class";
        byte[] bytes;
        try (InputStream in =
                RecordHiddenFinalDemo.class.getResourceAsStream(resource)) {
            if (in == null) {
                throw new IllegalStateException("Missing " + resource);
            }
            bytes = in.readAllBytes();
        }

        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(bytes, true,
                        MethodHandles.Lookup.ClassOption.NESTMATE)
                .lookupClass();

        Object hiddenObject =
                hidden.getDeclaredConstructor(String.class)
                        .newInstance("sealed");
        Field hiddenField = hidden.getDeclaredField("code");

        System.out.println("hidden class: " + hidden.isHidden());
        System.out.println("hidden field final: "
                + Modifier.isFinal(hiddenField.getModifiers()));
        System.out.println("hidden open: " + hiddenField.trySetAccessible());
        System.out.println("hidden read: " + hiddenField.get(hiddenObject));

        try {
            hiddenField.set(hiddenObject, "updated");
            System.out.println("hidden write: success");
        } catch (IllegalAccessException ex) {
            System.out.println("hidden write: "
                    + ex.getClass().getSimpleName());
        }

        Field ordinary = Ordinary.class.getDeclaredField("code");
        System.out.println("ordinary record: "
                + ordinary.getDeclaringClass().isRecord());
        System.out.println("ordinary hidden: "
                + ordinary.getDeclaringClass().isHidden());
        System.out.println("ordinary final: "
                + Modifier.isFinal(ordinary.getModifiers()));
    }
}
```

Run in the directory containing the file using JDK 17+:

```bash
javac --release 17 RecordHiddenFinalDemo.java
java RecordHiddenFinalDemo
```

The `javac` command creates the necessary class files in the same directory. When run directly with the current classpath, the resource `RecordHiddenFinalDemo$HiddenTemplate.class` will exist for `getResourceAsStream` to read its bytes. If packaging the application in a special way, you must ensure that class-file resource is distributed and readable.

### 7.2. Expected output

```text
record class: true
record field final: true
record open: true
record read: ready
record write: IllegalAccessException
hidden class: true
hidden field final: true
hidden open: true
hidden read: sealed
hidden write: IllegalAccessException
ordinary record: false
ordinary hidden: false
ordinary final: true
```

The output above was verified by compiling the source code with `--release 17` and running on a compatible JDK. It assumes a normal classpath/unnamed module environment, without adding a SecurityManager or special mechanism blocking Reflection permissions.

### 7.3. Detailed explanation of the record flow

- `Order.class.isRecord()` returns `true` because `Order` is a record.
- `getDeclaredField("label")` locates the field declared by the record, which has the `final` modifier.
- `trySetAccessible()` returns `true` in this example because the caller meets the access conditions (same unnamed module).
- `get(order)` successfully reads `"ready"`.
- `set(order, "updated")` still throws `IllegalAccessException` due to the **non-modifiable final field rule for records**. The error is **not** because the field could not be found, not because of a wrong `String` type, and not because `trySetAccessible()` returned `false`.

### 7.4. Detailed explanation of the hidden class flow

- `HiddenTemplate` when declared in source code is just an ordinary nested class; it is **not** a hidden class.
- `getResourceAsStream` retrieves the compiled bytecode of the template itself. `defineHiddenClass` uses those bytes to create a new class and returns a `Lookup`; `lookupClass()` is the **actual hidden class**.
- `hidden.isHidden()` returns `true`. This distinction proves the example operates on a hidden class, not merely a class whose name contains the word "Hidden".
- The constructor is invoked via Reflection to create `hiddenObject`. The field `code` is declared as `private final` in that class.
- `hiddenField.trySetAccessible()` succeeds, and `get(hiddenObject)` reads `"sealed"`.
- `set(hiddenObject, "updated")` throws `IllegalAccessException` because the declaring class of the final field is a **hidden class**.

### 7.5. Comparison with an ordinary class

`Ordinary` has `private final String code`, but both `isRecord()` and `isHidden()` return `false`. The program **does not attempt to modify the field** of `Ordinary` because reflectively mutating a final field of an ordinary class after initialization is not a technique to use in business code. Its purpose is to make clear: **`final` alone does not fully describe the special restrictions in records/hidden classes**.

## 8. Edge Cases and Exceptions to Distinguish

### 8.1. Lookup errors vs. write errors

| Situation | Typical result |
|---|---|
| Field name does not exist in the requested type | `NoSuchFieldException` on `getDeclaredField` |
| Field found, but lacks normal access permission | `IllegalAccessException` on `Field.get/set` |
| Another module's package does not allow deep reflection | `trySetAccessible()` may return `false`; `setAccessible(true)` may throw `InaccessibleObjectException` |
| Final field in a record/hidden class, access suppression enabled | `Field.set(...)` still throws `IllegalAccessException` |
| Instance field but receiver is `null` | `NullPointerException` |
| Receiver is not a compatible instance of the declaring class | `IllegalArgumentException` |
| Value has wrong type or cannot be converted per `Field.set` rules | `IllegalArgumentException` |

The fact that `Field.set` fails for a record final field **does not mean** the record class cannot be found via Reflection. Likewise, a hidden class can still be inspected via its `Class<?>` even though binary-name lookup mechanisms do not apply.

### 8.2. Final fields and static fields

A record can validly declare static fields. If a field is `static final`, it is also forbidden from being modified via `Field.set` under the general rule applying to all classes. For non-final static fields, Reflection can write under permitted conditions, but that is **not directly related** to writing record component fields.

### 8.3. Does reading imply being able to mutate an immutable structure?

No. `Field.get` returns the field's value. For reference-type fields, that value may be a reference to a mutable object. Example:

```java
record Team(java.util.List<String> members) {}

var names = new java.util.ArrayList<String>();
names.add("An");
Team team = new Team(names);
names.add("Binh");
System.out.println(team.members().size()); // 2
```

The record component `members` is final and cannot be reassigned via Reflection, but the `ArrayList` it points to remains mutable. If you want the record to have deeper immutability semantics, use a defensive copy, for instance in a compact canonical constructor:

```java
record SafeTeam(java.util.List<String> members) {
    SafeTeam {
        members = java.util.List.copyOf(members);
    }
}
```

These are standalone illustrative snippets about **shallow immutability**, not Field write operations. `List.copyOf` creates a list that does not support modification via mutator APIs and rejects `null` elements; if the elements themselves are mutable objects, additional mechanisms are still needed to ensure deep immutability.

## 9. Can `VarHandle` or Method Handles Modify These Final Fields?

Do not assume that another reflection API will automatically grant write permission where `Field.set` has forbidden it.

- `VarHandle` accesses variables according to supported access modes. A VarHandle for a final field typically supports only read modes; `set` and write modes are unsupported. You can check beforehand with `isAccessModeSupported(...)`.
- `MethodHandles.Lookup` enables accessing methods/fields according to lookup permissions, but you should not rely on creating a setter for a final field of a record/hidden class. A lookup reference is not a license to mutate any final field.
- Bypassing Java access checks (`setAccessible`) is different from bypassing a field's **non-modifiable** property.
- Internal/unsupported APIs or mutating memory outside standard mechanisms can break runtime assumptions, corrupt data, and do not form a stable contract for applications.

If you need to "update a record", **create a new record** from the old data and the data to change:

```java
record Position(int x, int y) {}

Position p1 = new Position(2, 3);
Position p2 = new Position(8, p1.y());
// p1 is still Position(2, 3); p2 is Position(8, 3).
```

For hidden classes, design explicit factories/constructors and clearly declared mutable state from the beginning if post-creation changes are needed; do not turn final fields into hidden mutation targets.

## 10. When Does This Limit Affect Frameworks?

### 10.1. Serialization and deserialization

Many traditional libraries create an empty instance and then assign fields via `Field.set`. That strategy cannot be applied unchanged to **final record components**.

For records, modern serializers/deserializers typically need to:

1. Read the list of `RecordComponent`, their names, and their types.
2. Collect constructor argument values from the input data.
3. Invoke the record's **canonical constructor** in the right component order/types.
4. Use accessors or read-only Reflection when exporting data.

Exact mechanisms depend on the library; check the documentation for the version in use. Do not manually modify `private final` record fields after the constructor has run.

### 10.2. Dependency injection, ORM, bytecode tooling

Tools that inject dependencies by directly assigning fields need to recognize final fields. If a field belongs to a record or hidden class, `Field.set` cannot be expected to work merely because access suppression has been enabled.

For records, prefer **constructor injection** or transforming the model into a new object under an immutability contract. For hidden classes, bytecode-generating frameworks should clearly decide during definition which data is final, which constructor/factory initializes it, and which data is genuinely mutable.

### 10.3. Inspection and debugging tools

If a tool only needs to **display metadata** such as name, modifiers, type, or declaring class, use `getDeclaredFields()` and metadata methods. Do not call `setAccessible` just to retrieve field names.

If reading a private final field is needed, check access permissions and module scope. If disallowed, report **access blocked** clearly. If modifying a final field of a record/hidden class is requested, report **non-modifiable by Reflection** rather than continuing to try different `Field.set` variants.

## 11. Common Misconceptions

**Misconception 1: "Having a `Field` means it can be modified."** False. Having metadata only proves the member exists. Read/write capability also depends on permissions, receiver, type, and final-field rules.

**Misconception 2: "`setAccessible(true)` succeeding means it can be written."** False. It only suppresses Java-language access checks within runtime limits; the group of non-modifiable final fields can still only be read.

**Misconception 3: "A record is a final class, so only the class is final."** False. Record components also correspond to private final instance fields; those fields are the focus of the Reflection restriction.

**Misconception 4: "A hidden class is a class with a secret/private name."** False. A hidden class is a runtime-defined type created through a specialized mechanism, with `isHidden() == true` and distinct lookup characteristics.

**Misconception 5: "Only `static final` is forbidden from being modified."** False. On Java 17, final fields declared by records and hidden classes are also forbidden from being written via `Field.set`, including instance fields.

**Misconception 6: "All fields of a hidden class cannot be modified."** False. The special restriction refers to **final fields**; non-final fields are still governed by normal access and assignment rules.

**Misconception 7: "Records guarantee everything inside is completely immutable."** False. A final component reference does not automatically freeze a mutable object it points to; defensive copying may be needed.

**Misconception 8: "`getDeclaringClass()` returning the receiver's class is enough."** False. A field can be found through a subtype while declared in a supertype. The record/hidden-class rule is based on the **declaring class of the field**.

**Misconception 9: "It can be fixed with `--add-opens`."** False with respect to the non-modifiable property. Opening a package can resolve deep reflection access across module boundaries, but it does not allow `Field.set` to write final fields of records/hidden classes.

**Misconception 10: "`IllegalAccessException` when writing final means the program lacked read permission."** Not necessarily. The runnable example above read successfully first and only then was denied the write.

## 12. Practical Checklist and Self-Check Questions

When writing tools that process Reflection fields, you can follow this sequence:

1. Find the `Field` by appropriate class and name, e.g., `getDeclaredField(name)`.
2. Read `f.getDeclaringClass()` to identify **the class that actually declares** the field.
3. Use `Modifier.isFinal(f.getModifiers())` and `Modifier.isStatic(...)` to determine modifiers.
4. If `final` and (static or `getDeclaringClass().isRecord()` or `getDeclaringClass().isHidden()`), treat the field as **non-modifiable via `Field.set`**.
5. If you only need to read the value, check `canAccess(receiver)` and use `trySetAccessible()` when genuinely needed, while respecting module boundaries.
6. Prefer record accessors/constructors/factories and the object's official API; do not default to reading/writing private fields.
7. If a framework needs updates, redesign object instantiation; do not rely on post-initialization mutation of final fields.
8. Classify exceptions accurately: field not found, access not opened, wrong receiver, or fixed field cannot be written.

**Self-check questions:**

- Does a successful `Field.setAccessible(true)` guarantee `Field.set` will succeed on `record Point(int x)`? Why?
- What is the difference between `Class.isRecord()` and `Class.isHidden()`?
- Is a `private int counter` field in a hidden class (not `final`) forbidden from modification merely because the class is hidden?
- Why does the `HiddenTemplate` class declared in source code not automatically become a hidden class? Which line creates the real hidden class?
- If `getDeclaredField` succeeds but `set` throws `IllegalAccessException`, what might the causes be?
- Can `opens package` remove the prohibition on writing a record's final component?
- How do you change `Person("An", 25)` into a new record with name `"Binh"` without modifying the old field?
- Why can a record with a `List<String>` component still exhibit changes inside that list?

**Learning conclusion:** Records and hidden classes protect the meaning of **final fields** with a dedicated Reflection restriction. You can see them, enable access to read them, and read the field, yet **`Field.set` still cannot write to them**. Identify the declaring class, modifiers, and operation intent before choosing a Reflection method.

Standard references for verification: [Java SE 17 — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html), [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), and [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html).