# Serialization and `serialVersionUID` When Custom Exception Contracts Require It

**Custom exceptions in Java are serializable** because `java.lang.Throwable` already implements `java.io.Serializable`. However, the fact that an exception *can* go through the Java Object Serialization mechanism does not mean every application *should* write that exception to bytes, persist it long-term, or send it over the network. If there is genuinely a **contract** to store or transmit exception objects using Java serialization, you must carefully design **`serialVersionUID`, field structure, cause, suppressed exceptions, version compatibility, and deserialization safety**.

This lesson focuses on the question: **When is serialization part of a custom exception's contract, and how should `serialVersionUID` be handled?** The standalone examples use Java 17 or later.

Summary first:

- Extending either `Exception` or `RuntimeException` results in a subclass of `Throwable`, so **both belong to the `Serializable`-supporting hierarchy**.
- `serialVersionUID` is the **version identifier of a serializable class** used for data compatibility checks during deserialization; it is **not** an object ID or a business error code.
- **Not every custom exception needs to publish a serialization contract.** Just because an IDE suggests “add `serialVersionUID`” does not mean the program must persist or send exceptions across processes.
- When compatibility across versions of the **same class** is genuinely needed, explicitly declaring `private static final long serialVersionUID` and maintaining the serialized form can be valuable.
- **Keeping the same `serialVersionUID` does not guarantee that every change is compatible.** Class structure, field types, hierarchy, custom serialization logic, and classes in the object graph still matter.
- **Do not deserialize untrusted bytes with `ObjectInputStream` indiscriminately**; native Java serialization carries significant security risks and version coupling. For public APIs, it is usually better to convert error information into an explicit DTO/schema.

## 1. Starting from the Hierarchy: Custom Exceptions Are Already `Serializable`

The relevant hierarchy:

```text
java.lang.Object
    └── java.lang.Throwable implements java.io.Serializable
          ├── java.lang.Error
          └── java.lang.Exception
                ├── CustomCheckedException
                └── java.lang.RuntimeException
                      └── CustomUncheckedException
```

If you declare:

```java
class ImportFailedException extends Exception {
    ImportFailedException(String message) {
        super(message);
    }
}

class WorkflowFailureException extends RuntimeException {
    WorkflowFailureException(String message) {
        super(message);
    }
}
```

these are **two illustrative classes** without `main`. Both inherit Java serialization capability from `Throwable`; there is no need to write `implements Serializable` just to enable it.

This does **not** change checked/unchecked rules:

- `ImportFailedException` is a **checked exception**; callers must catch or declare it when it can be thrown.
- `WorkflowFailureException` is an **unchecked exception**; callers are not forced by the compiler.
- **Both** can be passed to `ObjectOutputStream.writeObject` in terms of type, though writing can fail if the object graph contains a non-serializable field or hits another condition.

**Checked/unchecked classification and serialization capability are two orthogonal axes.** Do not choose `extends RuntimeException` to make serialization “easier,” and do not choose `extends Exception` just because you want to persist the exception.

## 2. What Does Serialization Mean in This Lesson?

**Java Object Serialization** is the mechanism for writing the state of a supported object graph into a byte format that can be read back by `ObjectInputStream` in a compatible Java environment.

Two representative APIs:

- `ObjectOutputStream.writeObject(object)`: writes an object/object graph.
- `ObjectInputStream.readObject()`: reads an object back from the stream and can instantiate the corresponding Java objects.

Skeleton example:

```java
try (ObjectOutputStream out =
             new ObjectOutputStream(outputStream)) {
    out.writeObject(exception);
}
```

This is **illustrative code**; it requires `outputStream`, `exception`, and the corresponding imports to be declared, as well as handling or declaring the checked `IOException`. Writing an object does **not** mean an exception is being `throw`n. Writing an exception object is a data operation; Java does not throw that exception simply because it is serialized.

Distinguish between:

| Operation | Purpose | Directly related to `serialVersionUID`? |
| --- | --- | --- |
| `throw new MyException(...)` | Signal an error on the current call stack | Not a serialized-form read/write operation |
| `catch (MyException e)` | Catch a propagating exception | No |
| `e.getMessage()` | Read the message | No |
| `e.printStackTrace()` | Print diagnostic information | No |
| `writeObject(e)` | Serialize the object graph | Yes, when writing the serializable class descriptor |
| `readObject()` | Deserialize the object graph | Yes, when checking class compatibility against the written data |

Do not conflate “logging an exception,” “sending a message to the user,” and “Java-serializing a `Throwable` object” into a single concept. Most logging operations and API responses **do not need** native Java serialization.

## 3. What Is `serialVersionUID`?

In Java serialization, a serializable class has a `long` **serial version UID**. During deserialization, Java uses the class metadata in the stream and the class descriptor on the reading side to check compatibility, including comparing `serialVersionUID` for classes that follow the standard versioning mechanism.

Standard declaration:

```java
private static final long serialVersionUID = 1L;
```

You should write this field **inside the custom exception class itself** if you decide to actively manage the serialized form version.

Explanation of each modifier and part:

- `private`: this is an implementation detail of the class, not API data for callers to access.
- `static`: belongs to the class, not to individual exception instances.
- `final`: a constant; does not change per object.
- `long`: the required type for the serial version UID value.
- `1L`: an illustrative value; **it does not have to be a random number or globally unique across the application**.

Several things **`serialVersionUID` is not**:

- Not an “error code” to display to users.
- Not a library version under Semantic Versioning.
- Not a unique identifier for each `Throwable` instance.
- Not automatically incremented when building a new software version.
- Not encryption or data protection.
- Not a guarantee that the class remains compatible when the schema changes.
- Not required to share the same value across all classes in the same exception branch.

Each serializable class in a hierarchy can have **its own UID**. A UID declared on a parent class does not replace managing the serialized form of a subclass when the subclass has its own contract.

## 4. When Do You Actually Need to Care About the UID?

You should examine it carefully when **the contract specifies** that exception objects must be Java-serialized and **read back later**, especially across different program versions. For example:

1. An internal component persists `Throwable` objects with `ObjectOutputStream` and needs to restore them with `ObjectInputStream`.
2. A legacy Java-to-Java system has an existing protocol based on Java serialization where exceptions are transmitted as serializable objects.
3. A state-persistence feature or compatibility test mechanism is explicitly designed to use serialized exception objects.
4. A library commits that the **serialized form of its custom exceptions** remains stable across specific releases.

In those situations, you must define **which versions must remain compatible, how long data is retained, the upgrade policy, and which fields must remain stable**.

Conversely, if an exception is only:

- `throw`n/`catch`ed within the same program,
- written to logs,
- mapped to an HTTP status and error response,
- presented in a CLI,
- or used in ordinary unit tests,

then **there is not necessarily a runtime requirement for Java serialization**. Explicitly declaring a UID can still be reasonable to follow a code convention or silence tool warnings, but you should not claim “long-term compatible exception persistence/transmission supported” just by adding one UID line.

## 5. Does the Compiler Generate a UID Automatically If Undeclared?

There is a mechanism that computes a **default UID** for a serializable class when the class does not declare a valid `serialVersionUID`. The default value is calculated from structural class information according to Java's serialization algorithm.

However, the automatically computed value can **change when source code or class signatures change**, including changes that do not look like “data changes” to the author. That can make data serialized by an older version unreadable by a newer version.

Therefore, for classes that genuinely commit to serialized-form compatibility, **declaring an explicit UID** makes version management intentional:

```java
public class JobFailureException extends Exception {
    private static final long serialVersionUID = 1L;

    public JobFailureException(String message) {
        super(message);
    }
}
```

This is a **complete class without `main`**, meant to be saved as `JobFailureException.java`. Keep the distinction clear:

- A **stable** UID only helps pass one of the compatibility checks.
- To remain compatible, changes to the serialized form must also obey Java serialization rules.
- Forcing the same UID across an **incompatible** change does not make objects automatically compatible.

If there is no real persistence/compatibility requirement, there is no need to design a migration mechanism just because the IDE emitted a `serial` warning.

## 6. How Should a Custom Exception with a UID Be Declared?

Example of a checked exception carrying a message, cause, and simple error code:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public DataLoadException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public DataLoadException(
            String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
```

This is a **standalone Java class** to place in `DataLoadException.java`. `Throwable` already supports `Serializable`, so the class does not need to write `implements Serializable` again.

Design decisions:

- `errorCode` is a `String` and is serializable.
- `message` and `cause` are passed to the superclass.
- `serialVersionUID = 1L` explicitly marks the serialized-form version of the current class.
- `getErrorCode()` is an application contract, **not** a Java serialization versioning mechanism.
- Fields added later must be evaluated for compatibility rather than changing the UID by default on every commit.

If the class uses an `enum` as an error code, enums have their own special serialization behavior; enum constant names and enum evolution policies must still be considered. Error codes on public APIs also need stability under the business contract, independent of the UID.

## 7. Runnable Java 17 Example: Round-Tripping a Custom Exception

This example demonstrates that a message, error code, cause, and suppressed exception can be written and read back when the entire object graph conforms to Java serialization.

Save as **`CustomExceptionRoundTripDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

class ImportException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String code;

    ImportException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    String getCode() {
        return code;
    }
}

public class CustomExceptionRoundTripDemo {
    static byte[] encode(ImportException error) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeObject(error);
        }
        return bytes.toByteArray();
    }

    static ImportException decode(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return (ImportException) in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        IOException source = new IOException("Tệp không đọc được");
        ImportException original = new ImportException(
                "IMPORT_IO", "Nhập dữ liệu thất bại", source);
        original.addSuppressed(
                new IllegalStateException("Cleanup thất bại"));

        byte[] data = encode(original);
        ImportException restored = decode(data);

        System.out.println("Cùng instance: " + (original == restored));
        System.out.println("Mã lỗi: " + restored.getCode());
        System.out.println("Message: " + restored.getMessage());
        System.out.println("Cause type: "
                + restored.getCause().getClass().getSimpleName());
        System.out.println("Cause message: "
                + restored.getCause().getMessage());
        System.out.println("Suppressed: "
                + restored.getSuppressed().length);
        System.out.println("Lỗi phụ: "
                + restored.getSuppressed()[0].getMessage());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 CustomExceptionRoundTripDemo.java
java CustomExceptionRoundTripDemo
```

**Exact stdout** with the classes from the example and a stream containing only data produced by the program itself:

```text
Cùng instance: false
Mã lỗi: IMPORT_IO
Message: Nhập dữ liệu thất bại
Cause type: IOException
Cause message: Tệp không đọc được
Suppressed: 1
Lỗi phụ: Cleanup thất bại
```

Explanation:

1. `original` is an `ImportException` instance with a `code` field, message, and cause.
2. `addSuppressed` attaches an additional suppressed `Throwable`.
3. `ObjectOutputStream` writes the object graph into a byte array.
4. `ObjectInputStream` reads a **new instance** corresponding to the serialized data.
5. `original == restored` is `false`, because the two instances do not share identity.
6. The message, `code` field, cause, and suppressed exception are restored by the default mechanism in this scenario.
7. **There is no `throw restored` statement** in the program. Deserialization does not mean throwing the restored error.

The `main throws Exception` signature here is only to keep the focus on serialization mechanics; in a real application, boundaries will need policies for catching and handling I/O errors, malformed data, missing classes, or untrusted data.

## 8. Deserializing Does Not “Re-Run” the Original Failure

A deserialized exception object is **restored data**, not an error event happening again on its own.

Specifically:

- `getMessage()` on the restored object reads the serialized message.
- `getCause()` may reference the restored cause object.
- `getSuppressed()` may contain the restored suppressed objects.
- `getStackTrace()` may provide the trace data recorded during the previous failure, depending on the serialized form and `Throwable` mechanics.
- `readObject()` **does not automatically execute `throw restored`**.
- If code later explicitly executes `throw restored`, it throws that object; normally the `throw` statement does not refresh the object's stack trace.

The read-back stack trace usually does **not** point to the time of decoding. It is data from the failure that was previously recorded and serialized, unless code or the JVM performs special actions such as `fillInStackTrace()` or `setStackTrace()`.

Therefore, do not use a deserialized stack trace to infer that the program at the current moment just executed those old frames.

## 9. When Does `InvalidClassException` Occur?

`java.io.InvalidClassException` is a kind of `ObjectStreamException` and can occur when Java detects that **the class on the reading side is incompatible with the class described in the stream**.

Common scenario:

1. Version V1 of `com.example.DataLoadException` is serialized with UID = `1L`.
2. Version V2 on the reading side has the same class name but UID = `2L`.
3. When `ObjectInputStream` attempts to restore the object, the version check can result in **`InvalidClassException`** due to the UID mismatch.

This is a **scenario across two versions**, not a single source program running two identically named definitions simultaneously. Within the same class loader, you cannot arbitrarily define two versions with the same binary name by placing two classes of the same name in one file.

Illustrative V1 and V2 declarations to understand the issue:

**V1** – `DataLoadException.java` built/distributed in the initial release:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 1L;

    public DataLoadException(String message) {
        super(message);
    }
}
```

**V2** – a class with the **same binary name** in the new release:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 2L;

    public DataLoadException(String message) {
        super(message);
    }
}
```

These are **two alternative versions**, not placed together on the same classpath. Data written by V1 and then read by V2 can fail the UID check because the stream and local versions differ.

An actual error message typically mentions `stream classdesc serialVersionUID` and `local class serialVersionUID`. Class names, paths, and UID numbers vary by situation; do not rely on the exact exception message text for business decisions.

**Do not increment the UID just because the release version increases.** When you want to maintain serialized-form compatibility, keep or change the UID based on the compatibility contract, not mechanically following a release schedule.

## 10. Matching UIDs Still Might Not Read Old Data

Suppose you keep `serialVersionUID = 1L` across multiple versions. That **does not guarantee** every class change is compatible with old object streams.

Changes that require special caution:

- **Changing the type of a field** already written in the serialized form can cause incompatibility.
- **Renaming the class or changing its package** changes the binary name that must be resolved on read.
- **Changing serializable/non-serializable inheritance relationships** or switching between `Serializable` and `Externalizable` has specific rules.
- **Adding custom `writeObject`/`readObject` logic** that is inconsistent between versions can misread data even if the UID is preserved.
- **Changing class invariants** can render previously restored state invalid.
- **Changing a field to a non-serializable type** can cause object writing to fail with `NotSerializableException`.
- **Nested cause/field classes** that no longer exist or changed incompatibly can prevent the entire graph from being restored.

Changing the UID also **does not automatically migrate data** to a new schema. Versioning and migration remain the responsibility of the storage protocol designer.

If the serialized form is genuinely part of the contract, specify **which fields may change**, which older versions can be read, and whether tests use real data from older releases.

## 11. Does Adding a Field Always Break Compatibility?

In many **default Java serialization** cases, adding a new serializable field to a class with the same UID is a **potentially compatible change when reading old data with the new version**. The new field does not exist in the old stream and can receive its **default value** upon deserialization.

Thought experiment:

**V1:**

```java
class ImportFailure extends Exception {
    private static final long serialVersionUID = 1L;
    String code;
}
```

**V2:**

```java
class ImportFailure extends Exception {
    private static final long serialVersionUID = 1L;
    String code;
    String category;
}
```

These are **two alternative versions**, not two classes compiled with the same name in one source set. If V2 reads V1 data under default rules with no other incompatible changes, the `category` field can receive **`null`**, because the V1 stream has no data for it.

Similarly:

- A new `int` field can receive `0` when absent from the stream.
- A new `boolean` field can receive `false`.
- A new reference field can receive `null`.

**Common pitfall:** do not assume field initializers in V2 source code run automatically and replace those defaults during default deserialization. For restored serializable classes, constructors and field initializers of the serializable class itself **are not executed like a normal `new`**. Constructors of the first non-serializable superclass follow separate rules.

If the new `category` is required, you must design restoration/validation logic for old versions or maintain a specific schema. **Simply keeping the old UID does not materialize data that was never written.**

## 12. Does Removing a Field Always Break Compatibility?

With default Java serialization, **removing a field** sometimes still allows old data to be read by the new class: field data no longer present in the reading class can be ignored by field mapping.

However, do not conclude that every case is safe:

- Information needed for restoration or diagnostic logic may be lost.
- Custom `readObject` code may depend on the old field.
- Nested classes or other type changes can still cause incompatibility.
- The getter API contract may have changed even if the data can be read.

For example, removing a `requestId` field to avoid persisting sensitive data is a security and schema decision, not merely a compiler change. You must evaluate every place that reads old objects and uses that field.

For long-lived data, **the set of compatible changes must be verified with cross-version tests**, rather than relying solely on the assumption that Java will ignore extra fields.

## 13. Not Every Field in a Custom Exception Is Serializable

Extending `Throwable` means the class can participate in Java serialization; **it does not mean every instance field you add is automatically serializable**.

Example of an exception holding a reference to a `Thread`:

```java
class WorkerFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final Thread workerThread;

    WorkerFailure(String message, Thread workerThread) {
        super(message);
        this.workerThread = workerThread;
    }
}
```

This is an **illustrative class**. `Thread` does not implement `Serializable`, so if default serialization attempts to write a non-`null` `workerThread` field, it can throw `NotSerializableException`.

Key consequences:

- **Having a UID does not fix a non-serializable field error.**
- Do not put objects like threads, sockets, services/clients, locks, callbacks, or live infrastructure objects into an exception's serialized form just for debugging.
- If you need identifying information, use structured data such as `String workerName`, `String operationId`, or an error code instead of a live object.
- If a field is only used at runtime, consider `transient`; however, you must accept that its data **will not be restored**.

New fields on a custom exception must be reviewed like a **data model** if the class participates in serialization—not simply adding whatever happens to be convenient.

## 14. Runnable Example: `NotSerializableException` from a Field

Save **`NonSerializableFieldDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectOutputStream;
import java.io.IOException;

class TaskFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final Thread thread;

    TaskFailure(String message, Thread thread) {
        super(message);
        this.thread = thread;
    }
}

public class NonSerializableFieldDemo {
    public static void main(String[] args) throws IOException {
        TaskFailure error =
                new TaskFailure("Task thất bại", Thread.currentThread());

        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(error);
            System.out.println("Không tới dòng này");
        } catch (NotSerializableException e) {
            System.out.println("Không thể serialize: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NonSerializableFieldDemo.java
java NonSerializableFieldDemo
```

**Exact stdout** on standard Java 17:

```text
Không thể serialize: java.lang.Thread
```

Even though `TaskFailure extends RuntimeException` and explicitly declares a UID, `Thread` cannot be written by default serialization. `NotSerializableException` describes the non-serializable class encountered in the object graph.

This is a **failure in the serialize operation**, not `TaskFailure` throwing itself. The program catches the `NotSerializableException` raised by `ObjectOutputStream`.

If you later remove the `thread` field or replace it with `String threadName`, consider the new serialized form and the ability to read old data if a contract has been published.

## 15. `transient` Fields: Keeping Runtime-Only Data Out of the Stream

The `transient` keyword marks an instance field as **excluded from the class's default serialization**. This is useful when a field holds temporary, sensitive, or non-serializable data.

Example:

```java
class JobFailure extends Exception {
    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private transient String debugNote;

    JobFailure(String errorCode, String debugNote) {
        super("Job thất bại");
        this.errorCode = errorCode;
        this.debugNote = debugNote;
    }
}
```

This is an **illustrative class** without `main`. After default deserialization:

- `errorCode` can be restored.
- `debugNote` is **not saved**, so a reference field typically receives `null`.
- `serialVersionUID` is not an instance field of the object and is not stored like ordinary instance state.

Do not use `transient` to mask the lack of schema design: if a field is genuinely a required invariant for post-restoration processing, omitting it from the serialized form can produce an object in an incomplete state.

Security is also more than marking fields `transient`: the detail message, cause, suppressed exceptions, or other fields may still contain sensitive information.

## 16. Runnable Example: `transient` Data Disappears After Deserialization

Save **`TransientExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

class RemoteTaskException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String code;
    private transient String localDebug;

    RemoteTaskException(String code, String localDebug) {
        super("Remote task failed");
        this.code = code;
        this.localDebug = localDebug;
    }

    String getCode() {
        return code;
    }

    String getLocalDebug() {
        return localDebug;
    }
}

public class TransientExceptionDemo {
    public static void main(String[] args) throws Exception {
        RemoteTaskException original =
                new RemoteTaskException("TASK_01", "trace chỉ ở máy này");

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
        }

        RemoteTaskException copy;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            copy = (RemoteTaskException) in.readObject();
        }

        System.out.println("Code: " + copy.getCode());
        System.out.println("Message: " + copy.getMessage());
        System.out.println("Debug null: " + (copy.getLocalDebug() == null));
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 TransientExceptionDemo.java
java TransientExceptionDemo
```

**Exact stdout:**

```text
Code: TASK_01
Message: Remote task failed
Debug null: true
```

The reason `debugNote`/`localDebug` is absent after restoration is the **`transient` policy**, not a `serialVersionUID` error. Application code using the restored object must expect and handle that state.

## 17. Cause, Suppressed Exceptions, and Stack Trace Also Affect the Contract

`Throwable` stores more than a message. A custom exception can carry:

- **Detail message**: via `getMessage()`.
- **Cause**: reference to the underlying cause exception, accessed via `getCause()`.
- **Suppressed exceptions**: array of secondary errors, accessed via `getSuppressed()`.
- **Stack trace**: stack frame data when the object was created/populated or modified via API.
- **Custom fields**: error code, task type, parameters, diagnostic context.

When using default Java serialization in a supported scenario, related objects such as cause and suppressed exceptions become part of the **object graph to be written and read**.

Keep in mind:

1. A cause is also a `Throwable` and may be a custom subclass with non-serializable fields.
2. A suppressed exception may also contain custom fields and further cause/suppressed relationships.
3. The stack trace may contain environment details and source locations from where the error was created, **not** the current stack at decode time.
4. The read-back object does not undergo a new failure on its own.
5. Special exception states (disabled suppression, disabled writable stack trace) can affect the observed data.
6. Successful serialization is not proof that the data is safe to display to end users.

Do not test only the message if the contract promises an error code, cause, or suppressed exceptions; test all committed data parts.

## 18. A Custom Subclass's `serialVersionUID` Differs from `Throwable`'s `serialVersionUID`

`Throwable` is a serializable class with its own serialized form. The exception class you create **also has its own class descriptor and UID** under Java serialization.

Example:

```java
class BaseImportException extends Exception {
    private static final long serialVersionUID = 1L;
}

class CsvImportException extends BaseImportException {
    private static final long serialVersionUID = 2L;
}
```

These are **two illustrative classes** without `main`. There is no rule requiring the two UIDs to match or forcing them to differ. Each UID pertains to the **serialized form of its own class**, not a global numbering system.

If `CsvImportException` has its own fields, its serialized form must be managed appropriately. Changing the serialized form of the parent class can also affect the ability to restore a subclass object.

**Do not infer that because the superclass already has a UID, the subclass does not need to consider its own contract.** At the same time, there is no need to invent a “tree-wide UID scheme” if there is no requirement to read objects across versions.

## 19. The `serialver` Command for Inspecting a UID

The JDK provides the **`serialver`** tool to look up the `serialVersionUID` of a serializable class that the JDK can load.

Example with a compiled class:

```bash
javac --release 17 JobFailureException.java
serialver JobFailureException
```

This is an **illustrative command**, assuming `JobFailureException.java` contains the class shown earlier and the JDK provides `serialver` on `PATH`.

If the class is in a package, pass the **fully qualified name** and set the appropriate classpath:

```bash
serialver -classpath build/classes com.example.JobFailureException
```

This is a CLI syntax example; it does not assume `build/classes` exists in every project.

The tool can help verify the recognized UID, but **it cannot replace serialization/deserialization testing between two versions**. Two classes with identical UIDs can still differ in schema or post-restoration behavior.

Do not use `serialver` output as a business error code, and do not copy a random UID from another class just to “keep them in sync.”

## 20. Should You Increment the UID Every Time the Class Changes?

**Not always.** That is a major misconception.

A practical policy:

- If the class does not publish a durable serialization contract: you can use a fixed UID by convention, or avoid cross-version data compatibility management.
- If the class commits to **backward compatibility**, keep the appropriate UID within the allowed serialized-form changes, and test against data from previous versions.
- If a change genuinely **breaks restoration** and the policy is to reject old streams, changing the UID can explicitly surface the incompatibility; you still need to consider migration and upgrade procedures.
- If data must be preserved despite deep class changes, do not rely on the UID alone: design an external schema/versioning scheme or explicit data-conversion reading logic.

The number `1L` does not mean “application version 1.0.” There is no Java rule requiring every UID to become `2L` when the application reaches version 2.0.

## 21. Serialization Compatibility Differs from API Compatibility

A class can:

- **Compile with old caller code** yet fail to read old object bytes.
- **Read old object bytes** yet have public API behavior changes that break callers.
- Have a matching `serialVersionUID` yet miss required fields after deserialization.
- Restore the message/cause yet lose a `transient` field that business logic depends on.

For example, an update renaming a getter `getCode()` to `code()` can break Java callers even though the serialized form is unchanged. Conversely, changing a private field's type can affect serialization even while the public signature stays nearly identical.

Therefore, different kinds of testing are needed:

| Test Type | Question |
| --- | --- |
| API/source compatibility | Can old callers still compile and use it? |
| Serialization compatibility | Can bytes written by the old version be read by the new version? |
| Behavioral compatibility | Does the restored object still satisfy its semantics and contract invariants? |
| Security compatibility | Is the data content still safe and permitted to restore in the new context? |

**The UID only serves part of the second row.**

## 22. Why Not Use Java Serialization as a Public API Format for Exceptions?

In modern systems, many applications need to send error information over HTTP, message queues, or long-term logs. The goal is usually to **send a structured description of the error**, not to transmit an entire Java `Throwable` object.

With native Java serialization, receivers can become coupled to:

- The sender's binary name/package and Java classpath.
- `serialVersionUID` and serialized forms of multiple classes.
- Object graphs containing cause/suppressed/custom fields.
- Java serialization compatibility rules and library versions.
- Security risks when deserializing untrusted data.
- Internal or sensitive information accidentally present in messages/stack traces.

For public APIs, it is usually better to **convert exceptions into a DTO/error envelope** with explicitly designed fields, for example:

```json
{
  "code": "IMPORT_FAILED",
  "message": "Không thể nhập dữ liệu",
  "requestId": "req-123"
}
```

This is a **JSON example**, not a format produced by `ObjectOutputStream`. The receiver understands the schema without loading the server's Java classes. Technical details like stack traces, causes, and suppressed exceptions usually belong in properly protected logging/tracing systems, not returned directly to end users.

Java serialization is not “banned” in all applications; it simply requires a **trusted context, a clear contract, and a practical reason**.

## 23. Alternative Pattern: Error DTO Instead of Serializing `Throwable`

When the goal is simply to **transmit failure state**, creating an independent error data type can be simpler. Java 17 has `record`:

```java
record ErrorInfo(String code, String message) {
}

class ImportFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final String code;

    ImportFailure(String code, String message) {
        super(message);
        this.code = code;
    }

    ErrorInfo toErrorInfo() {
        return new ErrorInfo(code, "Không thể nhập dữ liệu");
    }
}
```

These are **two illustrative types** without `main`. `ErrorInfo` expresses the permitted communication data, while `ImportFailure` retains the exception and internal diagnostics.

A Java `record` has its own special serialization handling when implementing `Serializable`; here, the example **only models a DTO** and does not put the record into a native Java object stream. If you choose JSON or another protocol, use an appropriate encoder/decoder.

A stable error message schema might include: `code`, a reviewed message, request ID, and response type. **Do not include stack traces in a public DTO** just because the exception object has them.

## 24. Security Risks When Deserializing Untrusted Objects

`ObjectInputStream.readObject()` does not merely read harmless strings; it can trigger instantiation/restoration of Java objects and execute restoration logic on the classes involved. Complex object graphs or classes with dangerous deserialization behavior can create security risks.

Principles:

1. **Do not deserialize data from strangers or untrusted networks** using native Java serialization unless there is a serious security design in place.
2. Prefer **data protocols with explicit schemas** when the goal is error exchange.
3. If Java serialization must be used in a controlled environment, restrict **which classes may be deserialized**, as well as size, depth, and reference counts through appropriate mechanisms such as `ObjectInputFilter`.
4. Control the classpath, dependencies, and permitted versions.
5. After deserialization, **validate data and invariants** before using it in business logic.
6. Do not treat `serialVersionUID` as sender authentication or tamper protection.
7. Do not store or display raw messages, stack traces, causes, and suppressed exceptions where appropriate access control is lacking.
8. If streams are stored long-term, establish retention policies, encryption where appropriate, version rotation, and data deletion.

**Deserialization filters are a mitigation, not a reason to arbitrarily expose an endpoint accepting `ObjectInputStream` from the Internet.** The round-trip example in this lesson only processes bytes created in the same program to illustrate Java behavior.

## 25. Testing Cross-Version Compatibility Properly

A round-trip test **within the same build** confirms that an object can be serialized and deserialized at that moment, but it is **not enough** to prove that data from an old version can be read by a new version.

A meaningful testing process:

1. **Define the contract:** which version must read streams from which version? Is backward reading required, or only reading old data with the new version?
2. **Generate byte fixtures from real releases**, using the JDK and classes of the published version. Store test fixtures in a controlled location.
3. **Read fixtures with the new version**, using the exact classpath, policy, and filters the application is expected to use.
4. Verify **message, error code, cause, suppressed**, and all fields actually covered by the contract.
5. Verify that the restored object **satisfies invariants**—not merely that it avoids throwing `InvalidClassException`.
6. Test failure paths: mismatched UID, missing class, non-serializable field, corrupted stream, and data exceeding limits.
7. Test creating an object in the **new version** and reading it in the **old version** only if the contract requires that direction.
8. Record the decision: keep the UID, change the UID, perform migration, or drop support for overly old data.

If you do not store fixtures and only run `serialize -> deserialize` with the same current class, an incompatible change across releases can go undetected.

## 26. When Should You Write Custom `readObject` / `writeObject`?

Java allows classes to implement custom serialization logic, such as:

```java
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

This is an **illustrative method pair** that only makes sense when declared inside a suitable serializable class with `java.io` types imported. They are unnecessary if you only want default round-tripping.

When the serialized-form contract is genuinely complex, these hooks can be used to control data or validate invariants. However:

- Custom `readObject`/`writeObject` code makes the **binary contract harder to evolve** without documentation and fixture tests.
- Do not forget to call `defaultReadObject`/`defaultWriteObject` when the schema expects the default mechanism.
- Hooks must account for invalid data, missing fields, version changes, and deserialization safety.
- Custom code can throw `IOException` or `ClassNotFoundException` as part of the contract.
- A `Throwable` also has superclass state such as cause and stack trace; custom field design must not assume it controls the entire superclass serialized form.

For most application custom exceptions, **avoid adding custom serialization logic just to clear IDE warnings**. If you do not need to persist or transmit the object, keeping the exception design simple is safer and easier to maintain.

## 27. Serializing an Exception Is Not a Completely Reliable History Mechanism

An exception is **diagnostic data**; many of its components are tied to the time and runtime environment: technical message, class name, stack trace, cause, and suppressed exceptions. When saved as object bytes, those details can become:

- Stale and no longer reflective of current code.
- Hard to read if classes have changed or been deleted.
- Sensitive because they contain file names, package names, system information, or user data.
- Harder to filter or search than a log or event with an explicit schema.
- Incomplete if `transient` fields were omitted or suppression/stack traces were disabled.

If the business requirement is an **audit trail**, it is usually better to store structured events: timestamp, stable error code, task ID, originating system, and permitted metadata. `Throwable` bytes can serve as secondary data for internal diagnostics if authorized and governed by a clear retention policy.

Do not use `serialVersionUID` as a substitute for a semantic **schema version** in audit documentation or communication APIs.

## 28. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| “Only exceptions that `implements Serializable` can be written with `ObjectOutputStream`.” | `Throwable` already implements `Serializable`, so custom subclasses are part of that hierarchy. |
| “Only `extends Exception` is Serializable; `extends RuntimeException` is not.” | Both inherit from `Throwable`. |
| “Every custom exception must declare a UID to run.” | `throw`/`catch` does not need a UID; Java also has a default UID mechanism for serialization. |
| “Adding `serialVersionUID` makes every field serializable.” | No. A field holding a non-serializable object can still cause `NotSerializableException`. |
| “`serialVersionUID` is the ID of each exception instance.” | No. It relates to the class version during serialization. |
| “Every application version bump must increment the UID.” | No; base the decision on the serialized-form compatibility contract. |
| “Keeping the same UID always reads all old streams.” | No. Schema, hierarchy, and custom logic changes can still be incompatible. |
| “Changing the UID does not affect persisted data.” | It can cause `InvalidClassException` when reading data from a previous UID. |
| “A newly added field always gets its initializer value when deserializing old data.” | No. A field missing from the stream typically receives its default value under serialization rules. |
| “A `transient` field is saved automatically if assigned in the constructor.” | Not in default serialization; a serializable class's constructor also does not run like a normal `new` upon restoration. |
| “An exception's cause/suppressed are always copied into a DTO/API response.” | No. Those are two separate designs; you must explicitly select the data. |
| “Deserializing an exception means that exception is thrown.” | No. `readObject` returns an object; throwing is a separate operation. |
| “A UID is a security mechanism.” | No. It neither authenticates nor protects the stream from malicious data. |
| “A same-build round-trip guarantees compatibility with old versions.” | No. You must test cross-version using old data fixtures. |
| “Since it's a `Throwable`, just serialize it to send over HTTP.” | No. A structured DTO/schema is usually more appropriate for public communication. |
| “`getStackTrace()` after decoding points to the decode line.” | Normally it reflects the trace stored in the object; decoding does not refresh the trace. |

## 29. Self-Check Questions

**1. Is `class MyException extends Exception` already Serializable?**  
Yes, it can participate in Java serialization because it inherits from `Throwable`, without needing to repeat `implements Serializable`.

**2. Does `class MyException extends RuntimeException` differ in that respect?**  
No. The checked/unchecked distinction relates to catching/declaring, not whether it is `Serializable`.

**3. Which exception instance does `serialVersionUID = 1L` identify?**  
It does not identify an instance. It is the class version in the serialized-form verification mechanism.

**4. Why declare an explicit UID when there is a long-term compatibility contract?**  
To intentionally manage the class's UID rather than depending on a default computation that can change with structural class details.

**5. Are two versions with the same UID always compatible?**  
No. You must consider schema, field types, class hierarchy, classes in the graph, and read/write logic.

**6. Is incrementing the UID for every release always right?**  
No. Doing so can break the ability to read old data with no benefit.

**7. If a custom field holds a non-`null` `Thread`, what error can default serialization raise?**  
`NotSerializableException`, because `Thread` is not serializable.

**8. What happens to a `transient` field when read back by default serialization?**  
It is not saved; for a reference field, it typically receives `null` unless custom restoration logic is provided.

**9. Does reading back a serialized exception throw it onto the call stack?**  
No. You must explicitly `throw` the object if you want to throw it.

**10. Are cause and suppressed exceptions serialized in the given round-trip example?**  
Yes, because the graph is constructed with appropriate serializable `Throwable`s; the result is verified with `getCause()` and `getSuppressed()`.

**11. If an object created in an old version is deserialized, is the stack trace a snapshot of the new call stack?**  
Normally no. It is the stored trace data; decoding does not recapture it.

**12. For an HTTP API, is it mandatory to send `Throwable` via Java serialization to transmit errors?**  
No. Usually an error DTO and a protocol with an explicit schema should be used.

**13. What can `InvalidClassException` indicate?**  
A class on the reading side is incompatible with the class described in the stream, commonly seen when UIDs mismatch.

**14. Can a UID be used to authenticate data arriving from a trusted server?**  
No. A UID is not a digital signature or an authentication mechanism.

**15. Why are fixtures from old versions needed?**  
Because a round-trip using only the same build cannot test data compatibility across versions.

**16. If a new field is added after an old version has written a stream, what will the new field's value be?**  
Under default serialization in a compatible case, a field absent from the stream can receive its default value, such as `null` for a reference.

**17. What if an exception object has a custom cause that is not completely serializable?**  
Serialization of the entire graph can fail due to the non-serializable field in the cause class, even if the outer exception has a UID.

**18. When should you think about `ObjectInputFilter`?**  
When the application genuinely uses Java deserialization and needs to restrict/filter which classes can be restored in a security-reviewed context.

## 30. Checklist Before Committing to a Custom Exception's Serialized Form

1. **Is native Java serialization genuinely required?** If you only log or return API responses, do not create an unnecessary contract.
2. **What is the trust boundary?** Does the stream come from the program itself, a controlled internal system, or an external source?
3. **Does the class declare an explicit UID?** If committing to compatibility, manage the UID intentionally.
4. **Is the UID kept distinct from the application's schema/error codes?**
5. **Is every instance field serializable?** Are any live objects (threads, sockets, services) being held inside the exception?
6. **Should any fields be marked `transient`?** Are post-restoration consequences handled?
7. **Is there sensitive data in the message, cause, suppressed exceptions, or stack trace?**
8. **Must data from previous versions remain readable?** Keep fixtures and cross-version tests.
9. **Are field additions, removals, or type changes compatible under the contract?**
10. **Do changes to class name, package, or hierarchy affect the serialized form?**
11. **Is there custom `readObject`/`writeObject`?** Are data/invariants validated and compatibility checked?
12. **Are there tests for `InvalidClassException`, `ClassNotFoundException`, `NotSerializableException`, and corrupted streams?**
13. **Is `ObjectInputStream` protected from untrusted data?** Evaluate the need for filters and depth/size limits.
14. **Can an explicit DTO/schema be used instead of serializing the entire `Throwable`?**
15. **Does the restored object retain valid business meaning without triggering dangerous actions?**
16. **Is there a deprecation/migration policy for old serialized data?**
17. **Are changes to cause/suppressed classes and related dependencies tracked?**
18. **Are API/source compatibility contracts distinguished from serialization compatibility?**
19. **Have you verified that serialization is not being misused as the default logging/audit mechanism?**
20. **If there is no serialization contract, have you avoided creating unnecessary long-term compatibility commitments?**

## 31. Conclusion

**Java custom exceptions are already `Serializable` via `Throwable`**, whether checked or unchecked. However, separate that technical capability from **contract requirements**: most errors only need to be thrown, caught, logged, or converted into structured messages; there is no inherent need to store or send `Throwable`s using Java Object Serialization.

When a contract **genuinely requires** serializing and deserializing custom exceptions across versions, **declare and manage `serialVersionUID` explicitly**, understand the serialized form of each class and field, keep messages/causes/suppressed exceptions limited to permitted data, test with byte fixtures from old releases, and put deserialization safety first.

**A matching UID is only one condition for compatibility, not a complete guarantee; nor is a UID an error code or a security mechanism.** When durable API communication is needed, an explicit error DTO/schema usually imposes fewer constraints, is easier to manage for compatibility, and is safer than transmitting the entire `Throwable` graph.
