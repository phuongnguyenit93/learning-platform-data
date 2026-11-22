# NotSerializableException, InvalidClassException, and StreamCorruptedException in Java Serialization

## 1. Lesson Goal and Context

When using Java Object Serialization, the three exceptions `NotSerializableException`, `InvalidClassException`, and `StreamCorruptedException` often appear around `ObjectOutputStream.writeObject(...)` / `ObjectInputStream.readObject(...)` operations, yet they report **three distinct kinds of problems**:

- **`NotSerializableException`:** cannot write an object in the object graph because its class does not support Java Serialization.
- **`InvalidClassException`:** the class descriptor in the stream and the loaded local class are incompatible for restoring the object (typically a `serialVersionUID` mismatch).
- **`StreamCorruptedException`:** the input data does not conform to the Java Object Serialization format or contains invalid control/format codes.

This lesson focuses on standard Java Serialization in `java.io` on **Java 17+**: causes, when they occur, how to reproduce them, how to read error messages, fixes, and prevention. These are *checked* exceptions under `IOException`; do not treat them as a single error merely because they share `IOException`.

## 2. Underlying Mechanism to Understand

`ObjectOutputStream` writes Java objects as an **object stream**, including class identification data, version information, and object state data. `ObjectInputStream` interprets that stream and reconstructs objects based on classes present in the reading JVM.

This process has its own requirements:

1. **Serializability of the entire graph:** a class to be serialized normally implements the marker interface `java.io.Serializable`. When writing an object, Java also traverses non-`static`, non-`transient` reference fields it must persist. If it encounters an object whose class is not serializable, the operation fails even though the root class implements `Serializable`.
2. **Class compatibility on read:** the saved class descriptor is compared against the local class. `serialVersionUID` (of type `long`) is the standard version check key, though matching UIDs alone does not automatically guarantee every structural change is compatible.
3. **Valid stream format:** `ObjectInputStream` expects data produced by the object stream mechanism. For example, a stream normally begins with header bytes `AC ED 00 05`; feeding a text file, JSON, or random bytes into `ObjectInputStream` does not turn them into Java objects.
4. **Resource lifecycle:** the stream must be closed or finished writing before reading from the produced bytes/file. `try-with-resources` ensures the stream is closed on success or failure.

`Serializable` is unrelated to `java.beans`, JSON serialization, or simply having getters/setters on a class. It is a binary protocol specific to Java Object Serialization.

## 3. Quick Comparison Table

| Exception | Usually occurs during | Core meaning | First place to inspect |
| --- | --- | --- | --- |
| `NotSerializableException` | `ObjectOutputStream.writeObject`; also possible in custom serialization | An object to be written is not serializable | Class name in `getMessage()`; reference path to the offending field |
| `InvalidClassException` | `ObjectInputStream.readObject` or class verification during serialization | Class definition/descriptor is incompatible or invalid | Class name, `serialVersionUID` on both sides, class change history |
| `StreamCorruptedException` | Constructing `ObjectInputStream` (bad header) or during `readObject` | Bytes violate object stream format rules | Byte source, header, concatenation/mixing/appending of streams |

**Note:** the occurrence locations in the table are common cases, not an exhaustive list of every internal code path. When diagnosing, prioritize exception type, message, stack trace, and the active I/O operation.

## 4. `NotSerializableException` — An Object Is Not Eligible to Be Written

### 4.1. Causes and Offending Objects

Java throws `java.io.NotSerializableException` if an object must be written while its class does not validly implement `Serializable` or `Externalizable`. Common causes:

- The root class does not implement `Serializable`.
- The root class implements `Serializable`, but a field holds a non-serializable object such as `Thread`, a DB connection, a stream, a socket, or a plain `Object`.
- A serializable collection such as `ArrayList` contains a non-serializable element; you must check the **actual runtime elements**, not just the collection's declared type.
- Custom `writeObject` / `writeExternal` explicitly writes a non-serializable object.

`static` fields are not part of the object state written by default serialization. `transient` fields are skipped by the default mechanism, though if a custom `writeObject` manually calls `writeObject` on that field, the error can still occur.

### 4.2. Reproducible Example on Java 17+

Create `NotSerializableDemo.java`:

~~~java
import java.io.*;

public class NotSerializableDemo {
    static final class Job implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String code;
        private final Object runtimeState = new Object();

        Job(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws IOException {
        try (var bytes = new ByteArrayOutputStream();
             var out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Job("J-01"));
        } catch (NotSerializableException e) {
            System.out.println("NotSerializableException: " + e.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac NotSerializableDemo.java
java NotSerializableDemo
~~~

Output:

~~~text
NotSerializableException: java.lang.Object
~~~

`Job` implements `Serializable`, yet the `runtimeState` field holds a `java.lang.Object`, which does not implement that interface. The class name in the message is the **class of the offending object**, not necessarily the class passed directly to `writeObject`. `code` is a `String`, so it causes no error.

### 4.3. Fix According to Data Semantics

If `runtimeState` is a cache or runtime-only resource, mark it `transient` and recreate it when needed. If that data *must survive restoration*, do not simply mark it `transient` to silence the error: convert it to persistable state, or design a dedicated DTO holding only the data to save.

Standalone example file `TransientDemo.java`:

~~~java
import java.io.*;

public class TransientDemo {
    static final class Job implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String code;
        private transient Object runtimeState = new Object();

        Job(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Job("J-01"));
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Job restored = (Job) in.readObject();
            System.out.println(restored.code);
            System.out.println(restored.runtimeState == null);
        }
    }
}
~~~

~~~bash
javac TransientDemo.java
java TransientDemo
~~~

~~~text
J-01
true
~~~

A `transient` field receives its default value (`null` for reference types) when the serializable object is restored by the default mechanism; the initializer `= new Object()` on the serializable class itself **does not re-run** during that process. To rebuild caches after reading, add an appropriate custom `readObject` or lazy initialization in an accessor. Simply adding `implements Serializable` to every offending class is unsafe as well: many runtime resources make no sense to save to disk.

## 5. `InvalidClassException` — Class in Stream and Current Class Are Incompatible

### 5.1. Role of `serialVersionUID`

`java.io.InvalidClassException` commonly occurs when an application writes an object with one version of a class and later reads it with another version whose `serialVersionUID` does not match. When a class implements `Serializable`, declare a fixed, intentional UID:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

`@Serial` is an annotation introduced in Java 14 that helps the compiler verify serialization declarations/extension points; it does not make a class serializable on its own. If UID is omitted, the JVM computes a default value from class characteristics; many source edits can alter the auto-computed UID and cause unpredictable failures. A fixed UID lets you manage compatibility deliberately, but **it is not a schema migration mechanism**.

Other causes can be classes violating serialization rules, such as lacking an accessible no-argument constructor on the first non-serializable superclass, or incompatible structural changes in the class. Do not claim every `InvalidClassException` is caused by UID.

### 5.2. Reproducing the Error with Two Versions of the Same Class

This example requires **two separate compilations** because two `SavedItem.java` files share the same class name with different UIDs. Create the structure:

~~~text
demo/
  v1/SavedItem.java
  v1/WriteItem.java
  v2/SavedItem.java
  v2/ReadItem.java
~~~

Contents of `v1/SavedItem.java`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public class SavedItem implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String name;

    public SavedItem(String name) {
        this.name = name;
    }
}
~~~

Contents of `v1/WriteItem.java`:

~~~java
import java.io.*;

public class WriteItem {
    public static void main(String[] args) throws Exception {
        try (var out = new ObjectOutputStream(
                new FileOutputStream("saved-item.ser"))) {
            out.writeObject(new SavedItem("J-01"));
        }
        System.out.println("Wrote v1");
    }
}
~~~

Contents of `v2/SavedItem.java` (same class name, UID changed to 2):

~~~java
import java.io.Serial;
import java.io.Serializable;

public class SavedItem implements Serializable {
    @Serial
    private static final long serialVersionUID = 2L;

    private final String name;

    public SavedItem(String name) {
        this.name = name;
    }
}
~~~

Contents of `v2/ReadItem.java`:

~~~java
import java.io.*;

public class ReadItem {
    public static void main(String[] args) throws Exception {
        try (var in = new ObjectInputStream(
                new FileInputStream("saved-item.ser"))) {
            in.readObject();
            System.out.println("Read OK");
        } catch (InvalidClassException e) {
            System.out.println("InvalidClassException");
        }
    }
}
~~~

From the `demo` directory containing `v1` and `v2`, run in sequence:

~~~bash
javac -d v1 v1/SavedItem.java v1/WriteItem.java
java -cp v1 WriteItem
javac -d v2 v2/SavedItem.java v2/ReadItem.java
java -cp v2 ReadItem
~~~

Output:

~~~text
Wrote v1
InvalidClassException
~~~

Version v1 wrote a `SavedItem` descriptor with UID `1L`. Version v2 loads a class of the same name with UID `2L`, so `readObject` cannot restore the object. Printing `e.getMessage()` typically shows the class name and both `serialVersionUID` values; do not depend on exact message wording across JDK releases.

### 5.3. Handling Class Evolution Properly

1. Identify **which application version wrote** the data and **which version is reading** it; record the full stack trace and message.
2. Inspect `serialVersionUID`, class name/package, field changes, and class hierarchy. The tool `serialver -classpath ... TenClass` can look up the UID of a compiled class, though comparing against the UID in deployed data/versions is essential.
3. For compatible changes (e.g., adding a normal field), preserve the UID intentionally after verifying the data contract; new fields usually receive default values when reading old data.
4. For incompatible changes or semantic shifts, build a **migration pipeline**—reading with the old version and exporting to the new format—or maintain a reader for legacy data. Do not arbitrarily reset v2's UID back to 1 just to silence the exception.
5. If data must be retained long-term or exchanged across systems, consider an explicit-schema/versioned format with clear migrations instead of Java binary serialization.

Matching UIDs **do not** guarantee data is valid for business logic. For example, repurposing a property name to a different meaning can yield default values or wrong data without throwing an error. Conversely, not every field change is incompatible; specific serialization compatibility rules govern it.

## 6. `StreamCorruptedException` — Byte Stream Is Malformed

### 6.1. Common Causes

`java.io.StreamCorruptedException` signals that the object stream contains invalid control/format information. Typical scenarios:

- Creating `ObjectInputStream` over UTF-8 text, JSON, CSV, images, or `DataOutputStream` output instead of a stream written by `ObjectOutputStream`.
- Missing or misreading leading stream bytes; passing data starting at an incorrect offset.
- Mixing `ObjectOutputStream` writes with manual raw byte writes in the **same protocol** when the reader does not know how to separate them.
- Appending multiple writes using **new `ObjectOutputStream` instances** into the same file; each new object stream constructor writes another header, causing a continuous `ObjectInputStream` to hit a mid-stream header as an invalid data code.
- Data modified or corrupted in its format structure.

There is no rule that "corrupted files always throw `StreamCorruptedException`": an empty or truncated file can throw `EOFException`; malformed or cut-off streams at other positions can produce other exceptions.

### 6.2. Bad Header Example with Deterministic Output

Create `StreamCorruptedDemo.java`:

~~~java
import java.io.*;

public class StreamCorruptedDemo {
    public static void main(String[] args) throws Exception {
        byte[] notAnObjectStream = {0x00, 0x01, 0x02, 0x03};

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(notAnObjectStream))) {
            in.readObject();
        } catch (StreamCorruptedException e) {
            System.out.println("StreamCorruptedException");
        }
    }
}
~~~

~~~bash
javac StreamCorruptedDemo.java
java StreamCorruptedDemo
~~~

~~~text
StreamCorruptedException
~~~

The error is thrown **right inside the `ObjectInputStream` constructor** when reading the header, before `readObject()` is even reached. Printing the message in this case typically shows `invalid stream header: 00010203`; the hex code helps identify the actual data type.

### 6.3. Writing and Reading Matching Stream Pairs

A minimal serialization pair, `RoundTripDemo.java`:

~~~java
import java.io.*;

public class RoundTripDemo {
    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject("hello");
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            String value = (String) in.readObject();
            System.out.println(value);
        }
    }
}
~~~

~~~bash
javac RoundTripDemo.java
java RoundTripDemo
~~~

~~~text
hello
~~~

Writer and reader must agree on object order, message boundaries, and how streams are opened/closed. To write multiple objects to one file, use **one `ObjectOutputStream` for the entire write session** and one corresponding `ObjectInputStream` for the read session, with well-defined record counts/boundaries. `flush()` pushes buffered data to the underlying layer; it does not fix format errors or writing multiple headers.

If a protocol prepends a length, version, or custom metadata bytes, parse/read that prefix first before constructing `ObjectInputStream` on the **exact object stream payload slice**; you cannot use `readObject()` to read arbitrary raw bytes.

## 7. Situations Easily Confused with These Three Exceptions

| Symptom | What it might be | How to verify |
| --- | --- | --- |
| `writeObject(list)` reports `NotSerializableException: com.example.X` | An element or child field of type `X` is not serializable | Trace the object graph from the list down to elements and fields |
| `readObject()` reports `InvalidClassException` after an upgrade | Class changed UID or made an incompatible change | Compare writer/reader class versions and UIDs; test reading with the old version |
| `new ObjectInputStream(...)` reports `StreamCorruptedException` | Bad header or reading wrong format/offset | Inspect the source, first 4 bytes, and file-writing code |
| `readObject()` reports `EOFException` | End of stream reached, missing data, or more reads than writes | Count records, check file size and read loop |
| `readObject()` reports `ClassNotFoundException` | Written class is missing from reader's classpath/class loader | Check class/package names, JARs, and deployment environment |
| `readObject()` reports `OptionalDataException` | Reader expects an object where primitive data sits in the protocol | Compare order of `writeObject`, `writeInt`, and corresponding read calls |
| `readObject()` reports `WriteAbortedException` | Writer aborted writing an object after an error and recorded it in the stream | Inspect `getCause()` and writer-side error logs |

`ClassNotFoundException` is not one of the three main types and belongs to a different exception branch than `IOException`. `IOException`/`EOFException` carry distinct meanings; do not wrap every read failure into `StreamCorruptedException` in a catch block.

## 8. Step-by-Step Diagnosis and Troubleshooting Procedure

1. **Identify the failing operation.** Writing (`writeObject`), creating the reader (`new ObjectInputStream`), or reading (`readObject`)? Capture the full stack trace and message, including the root `cause` if present.
2. **For `NotSerializableException`:** extract the offending class name from the message and locate the field/collection holding an instance of that class. Separate data to persist from runtime resources. Convert to a serializable DTO, restructure, or mark `transient` with an appropriate rebuild plan.
3. **For `InvalidClassException`:** identify the class from the stream, the currently loaded class, and both UIDs. Check schema compatibility, non-serializable superclass constructors, and class changes. Perform migration when needed.
4. **For `StreamCorruptedException`:** verify the source bytes were genuinely produced by `ObjectOutputStream`, without mixed text/JSON/metadata or appended duplicate headers. Read/write at the exact expected position and protocol.
5. **Test on minimal reproducible data.** Write a write → read test on the **same version** to verify basic code, then use the failing data/version to separate protocol errors from compatibility errors.
6. **Fix the root cause and add regression tests.** Save stream fixtures from an older version if backward reading is promised; test object graphs with collections, nulls, transients, truncated data, and invalid streams.

In real applications, catch exceptions at the I/O boundary to log sufficient context and return meaningful errors. Never swallow exceptions and treat a failed restoration as valid data; likewise, do not delete a serialized file on the first read failure before determining the cause and retention policy.

## 9. Preventing Errors by Design

- **Keep persisted data minimal:** separate exchange/storage models from entities holding sockets, executors, threads, connections, loggers, or caches; being serializable does not mean suitable for long-term storage.
- **Manage versions:** declare `serialVersionUID` deliberately for serializable classes, test reading old data on new releases, and design migrations for incompatible changes.
- **Standardize the protocol:** clearly define write/read sessions, data order, message framing, and buffer/file handling. Do not use a serialization stream as a catch-all container for arbitrary data.
- **Observability:** log class name, application version, I/O location, filename/message name, and cause. For sensitive data, never dump whole objects or streams into logs.
- **Security:** Java deserialization of untrusted data is dangerous due to behavior triggered during object graph reconstruction. Avoid `ObjectInputStream` on untrusted input; when required, consider JEP 290 `ObjectInputFilter` along with limits on classes, depth, reference counts, and size. Filters **do not replace** source trust controls and safe protocol design.

## 10. Self-Check

**Question 1.** Class `Order` implements `Serializable` and holds `List<PaymentConnector>`. `ArrayList` is serializable, while `PaymentConnector` does not implement `Serializable`. What happens when writing a list containing an element of that type?

**Answer:** It will likely throw `NotSerializableException` when Java reaches the `PaymentConnector` element. You must fix the object graph being written, not just the declared type of the list field.

**Question 2.** A class adds an `int retries` field and keeps the same UID. Will old data definitely cause `InvalidClassException`?

**Answer:** No. Adding an ordinary field is normally a compatible change; when reading old data, the new field typically receives default value `0`. You must still test business logic and related compatibility rules.

**Question 3.** Reading a JSON file through `ObjectInputStream` throws a header error. Can you fix it by making the JSON class implement `Serializable`?

**Answer:** No. JSON bytes are not a Java Object Serialization stream. Use a JSON parser for JSON, or switch the writer to `ObjectOutputStream` and align the format on both sides.

**Question 4.** Why does a file containing only half its data not necessarily throw `StreamCorruptedException`?

**Answer:** If the reader needs more bytes and hits the end of the file, `EOFException` can be the direct signal. The exact exception depends on where data is missing and the decoding stage.

## 11. Takeaways

- `NotSerializableException` → **object graph issue on write**: inspect the actual runtime class and fields/elements being serialized.
- `InvalidClassException` → **class compatibility/definition issue**: inspect UID, class version, and data evolution history.
- `StreamCorruptedException` → **object stream structure issue**: inspect byte source, header, offset, and writer/reader coordination.

Catching the right exception type narrows down the failure quickly, yet the true fix must rest on what data needs saving, compatibility contracts, and the designed stream format.