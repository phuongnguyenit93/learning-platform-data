# Data Compatibility: Files, Serialized Objects, and Messages

In a Java project, application version upgrades often roll out in multiple phases. A new server may have to read data written by an old version; an old process may still be handling messages sent by a new process; or a file created years ago may still need to open after the program's structure has changed. All of these situations fall under **data compatibility**.

Data compatibility is the ability of different versions of a program to continue exchanging, storing, and interpreting data according to the same contract. That contract does not consist merely of field names and data types. It also encompasses field meanings, encoding, rules for handling missing values, units of measurement, date/time formats, and rules for handling parts of data that a version does not recognize yet.

This lesson focuses on three data forms commonly encountered when migrating Java applications: **files**, **serialized Java objects**, and **messages between components**. Each form has its own compatibility mechanisms, yet all require a clear version-management process.

## 1. Foundational concepts

Suppose version `v1` of an application writes data, and later version `v2` reads that data. We must distinguish the direction of compatibility:

| Concept | Meaning | Example |
|---|---|---|
| Backward compatibility | A new reader understands data created by an old writer. | `v2` can read files or messages from `v1`. |
| Forward compatibility | An old reader can still process data created by a new writer. | `v1` ignores a new field added by `v2`. |
| Bidirectional compatibility (full compatibility) | Both new and old readers can process each other's data within the committed scope. | Versions can be deployed side by side during an upgrade phase. |

Terminology can be used differently across teams or tools. Therefore, when designing a format, state the exact matrix explicitly: which writer versions are supported by which reader versions. Do not merely state vaguely that a format "is compatible".

Beyond structure, consider **semantic compatibility**. For example, the `amount` field remains a decimal number in both versions, yet `v1` interprets it as Vietnamese dong while `v2` interprets it as US dollars. The data type did not change, yet the meaning changed; this is still a contract-breaking change.

A change is generally safer when it has all of the following characteristics:

- New fields can be absent in old data and have reasonable default values.
- Old readers can ignore new fields without corrupting business outcomes.
- Existing fields keep their exact names, types, units, and meanings.
- The format has a way to identify its version and rules for handling unsupported versions.

## 2. File compatibility

### 2.1. A file is also a data contract

A file produced by an application is not just a bag of bytes. It has structure that the reading program must understand. For text files, structure can include column headers, delimiters, field order, encoding, and null-value rules. For binary files, structure can include signatures, version numbers, section lengths, byte order, and checksums.

Before changing a file format, settle the following questions:

1. Is the file encoded in UTF-8, UTF-16, or another encoding?
2. Do date/time values carry timezones or only local time?
3. Do decimal numbers use a dot or a comma? Is precision specified?
4. Do missing values, `null`, empty strings, and `0` have distinct meanings?
5. Is the reader permitted to ignore unknown columns or fields?
6. If a mandatory field is missing, will the program reject the file or apply a default?
7. Is it still necessary to read files created by versions that have reached end-of-support?

These seemingly minor details are often what cause an upgrade to break historical data.

### 2.2. Text files and structured formats

CSV, JSON, XML, and other text formats are convenient to inspect visually, yet still need versioning rules. For instance, a CSV file initially has columns `id,name`; a new version adds `email`. A new reader can read old files if it tolerates a missing `email` column. Conversely, an old reader may fail on new files if it assumes every file always has exactly two columns or relies on positional column indexing.

For CSV, you should:

- Put column names in the header row and map by name rather than relying strictly on position.
- Specify delimiters, quote-escaping rules, and how newlines inside cells are represented.
- Use UTF-8 and document the encoding in the format specification.
- Define how unknown columns, missing columns, and empty values are handled.
- Avoid changing the units or meanings of existing columns.

For JSON, a version field can be added to the document:

```json
{
  "formatVersion": 2,
  "customerId": "C-1042",
  "displayName": "Nguyen An",
  "email": "an@example.test"
}
```

When reading, the program inspects `formatVersion` and converts the data into the current internal model. If the version field is absent, the application may treat it as version `1` **only when the old contract explicitly specified this**. Do not guess the version merely from which fields happen to appear in the file.

JSON allows expressing new fields without breaking document syntax, yet that does not automatically guarantee compatibility. A parsing library may reject unknown properties; a new field may be treated as required; or two versions may interpret `null` differently. Configure and test the reader according to the exact application policy.

### 2.3. Binary files need identifiers and version numbers

For an application-defined binary format, do not simply write fields sequentially and expect every reader to always know how to decode them. A simple layout can begin with:

| Component | Purpose |
|---|---|
| Magic number / signature | Identify the exact file type. |
| Format version | Select the corresponding decoder. |
| Payload length | Validate data length and prevent out-of-bounds reads. |
| Payload | Actual contents. |
| Checksum (if needed) | Detect accidental data corruption. |

The following example illustrates checking a file header with `DataInputStream`. This shows only the header; payload decoding must be defined per version.

```java
import java.io.DataInputStream;
import java.io.IOException;

public final class FileHeaderReader {
    private static final int MAGIC = 0x43555354; // ASCII: CUST
    private static final int MAX_PAYLOAD_LENGTH = 20 * 1024 * 1024;

    public static int readVersion(DataInputStream input) throws IOException {
        int magic = input.readInt();
        if (magic != MAGIC) {
            throw new IOException("Not a supported customer file");
        }

        int version = input.readUnsignedShort();
        int payloadLength = input.readInt();

        if (payloadLength < 0 || payloadLength > MAX_PAYLOAD_LENGTH) {
            throw new IOException("Invalid payload length: " + payloadLength);
        }

        if (version != 1 && version != 2) {
            throw new IOException("Unsupported file version: " + version);
        }

        return version;
    }
}
```

`DataInputStream.readInt()` reads four bytes in big-endian order. If the format is shared across multiple languages or platforms, byte order and field sizes must be part of the specification rather than relying on implicit Java program defaults.

Once the version is identified, decoders can be separated:

```java
switch (version) {
    case 1:
        return readVersion1(input);
    case 2:
        return readVersion2(input);
    default:
        throw new IOException("Unsupported version: " + version);
}
```

Both decoders can produce the same current internal model. This keeps business logic insulated from the details of every historical format.

### 2.4. Strategy for migrating old files

When upgrading files in bulk, separate two steps: **reading the old format** and **writing the new format**. A typical workflow is:

1. Read the file and identify its version.
2. Decode it into an intermediate model or the current business model.
3. Validate required fields and convert units, date/time values, or defaults according to published rules.
4. Write to a temporary file in the new format.
5. Re-read or verify the temporary file, and only then replace the target file.
6. Keep backups or audit logs sufficient for traceability and recovery when needed.

Writing via a temporary file avoids leaving a partially written target file if the process stops mid-way. `Files.move` with `StandardCopyOption.ATOMIC_MOVE` can be used when the filesystem supports it; handle the case where atomic moves are unsupported. Never delete the original before the new copy is verified.

A migration job should be **idempotent**: running it again must not transform the data a second time. You can achieve this by writing the new version to the header, checking the version before converting, and recording status per file. For large file sets, report counts of succeeded, failed, and skipped files.

If old files can still be produced during the upgrade window, define when writers stop emitting the old format. Otherwise, a migration pass can finish while new data keeps arriving in the old format.

## 3. Compatibility of serialized Java objects

### 3.1. What does Java Serialization store?

Java Serialization writes an object graph to a byte stream and reconstructs that graph using `ObjectOutputStream` and `ObjectInputStream`. A class typically participates by implementing `Serializable`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private String name;
    private String email;
}
```

The serialized stream contains metadata needed to identify the class and restore object state. When reading, Java must locate the corresponding class and check compatibility between the class descriptor in the stream and the class present in the running program.

This is a key distinction between Java Serialization and an independent exchange format such as JSON or Protocol Buffers: Java serialized data is tightly coupled to class names, class structure, and Java's serialization rules. Thus, while suitable for some controlled internal state persistence cases, it is usually a poor choice for long-term data contracts across multiple systems or languages.

### 3.2. Role of `serialVersionUID`

`serialVersionUID` is the version identifier of a serializable class. When reading an object, Java compares the UID in the stream against the current class's UID. If the two values do not match, reading typically fails with `InvalidClassException`.

Declare the UID explicitly:

```java
private static final long serialVersionUID = 1L;
```

If omitted, Java computes a default UID from several class characteristics. Seemingly minor structural changes can alter the computed UID, making old data unreadable after recompilation.

Keeping the UID unchanged does not mean every edit is safe. The UID only participates in class version checking; it does not convert data automatically, does not guarantee field meanings stayed unchanged, and does not replace compatibility testing. If a change is genuinely incompatible, changing the UID can fail fast, yet the application still needs a dedicated data migration path.

### 3.3. Class changes and their impact on old data

For ordinary `Serializable` classes, some changes can be handled by Java's default rules:

| Change | Typical behavior reading old streams | What to watch out for |
|---|---|---|
| Add instance field | The new field receives the type's default value if absent in old streams. | `null`, `0`, or `false` may not be valid business defaults. |
| Remove instance field | Field values present in the stream yet missing from the class are ignored. | That data is no longer retained in the restored object. |
| Rename field | Treated as removing the old field and adding a new field. | Old values do not transfer automatically to the new name. |
| Change field type | Usually incompatible and can cause read failures. | Requires explicit conversion logic or an intermediate format. |
| Change `serialVersionUID` | UID mismatch causes Java to reject reading the class. | Implement a migration strategy rather than merely changing the UID. |

For example, the first version has:

```java
public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
}
```

The later version adds `email`:

```java
public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
    private String email;
}
```

When reading a stream produced by the old class, `email` receives `null` since the stream lacks that field. If business logic requires a default such as `"unknown"`, the program must assign that value during deserialization or immediately afterward. Never assume Java's field default is always a valid business value.

Changes involving superclasses, subclasses, `enum` types, `static` fields, `transient` fields, or custom serialization mechanisms follow specific rules. When inheritance hierarchies change, check the serialization specification for that exact case and test against real streams written by prior versions.

### 3.4. Using `readObject` to convert legacy state

A class can define a private `readObject` method to control how state is restored. `ObjectInputStream.GetField` lets you check whether a field exists in the stream and supply defaults when it does not.

```java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    private String name;
    private String email;
    private String status;

    private void readObject(ObjectInputStream input)
            throws IOException, ClassNotFoundException {
        ObjectInputStream.GetField fields = input.readFields();

        name = (String) fields.get("name", null);
        email = (String) fields.get("email", null);

        if (fields.defaulted("status")) {
            status = "ACTIVE";
        } else {
            status = (String) fields.get("status", "ACTIVE");
        }
    }
}
```

In this example, old streams lack `status`, so restored objects receive `ACTIVE`. This is the example's business decision; real systems must pick defaults based on actual data and historical rules. If no safe value can be inferred, flag the record for handling or reject it rather than silently assigning an inaccurate state.

Related mechanisms:

- `writeObject` customizes how state is written.
- `serialPersistentFields` declares a stable set of serializable fields, partially decoupling stored field names from internal class fields.
- `writeReplace` and `readResolve` substitute objects during writing or reading, useful in patterns such as singletons or proxies.

These mechanisms make serialization more flexible yet add complexity. Keep test fixtures created by prior versions to prove old data still restores accurately.

### 3.5. Limits and safety of Java Serialization

Never treat a Java Serialization stream as harmless data. Deserialization can instantiate many objects and trigger logic across involved classes. Never read arbitrary serialized data from untrusted sources. If this mechanism must be retained, constrain allowed deserializable types with `ObjectInputFilter`, and limit object graph depth, reference counts, and array sizes appropriately for the application.

For long-lived data, network-exchanged data, or cross-language data, consider a format with schemas and explicit evolution rules. Java Serialization can be retained for short-lived internal data only when you know exactly where it is stored, which versions wrote it, and its support lifecycle.

## 4. Message compatibility

### 4.1. Messages are contracts between independent components

Messages appear in REST APIs, queues, publish/subscribe systems, Kafka, background jobs, and inter-service integrations. Producers and consumers can be deployed at different times. During a rolling deployment, two versions can coexist.

Therefore, verify at least four cases:

| Producer | Consumer | Question to answer |
|---|---|---|
| Old | Old | Does the current system keep working? |
| Old | New | Can the new consumer read messages already sitting in the queue? |
| New | Old | Can the old consumer handle new messages during a mixed deployment phase? |
| New | New | Do new components share the same interpretation of schema and data semantics? |

Old-producer to new-consumer is usually essential for draining backlog messages. New-producer to old-consumer usually determines whether producers can roll out first.

### 4.2. Designing evolvable payloads

A message should have clear structure and keep field meanings stable. Example:

```json
{
  "eventType": "CustomerAddressChanged",
  "schemaVersion": 2,
  "eventId": "evt-8f31",
  "occurredAt": "2026-11-12T08:30:00Z",
  "payload": {
    "customerId": "C-1042",
    "address": {
      "city": "Ho Chi Minh City",
      "countryCode": "VN"
    }
  }
}
```

The outer envelope carries event type, schema version, identifier, and occurrence timestamp. The payload holds business data. Consumers can route by `eventType` and pick a decoder by `schemaVersion`.

Useful design rules:

- Adding optional fields is usually more compatible than deleting or changing the type of existing fields.
- Define default values when new fields are absent.
- Preserve existing field meanings. If meaning changes, add a new field or a new event type.
- For enums, consumers should define a strategy for unknown values, such as storing raw values, controlled skipping, or routing to an `UNKNOWN` branch.
- Use timezone-aware timestamps, typically ISO-8601 in UTC, rather than ambiguous local timestamp strings.
- Specify units for money, distance, weight, and other quantities. Never change units on the same field without changing the contract.
- For monetary amounts or precision decimals, specify representation and precision explicitly rather than relying on platform implicit rounding.
- Never use Java class names as public message contracts. Class names change during refactoring and should not force every producer and consumer to change alongside.

For JSON, consumers can be configured to ignore unknown properties. Still, test this policy in the exact library used. Ignoring new fields is safe only when the new field is not required for correct business behavior in older consumers.

### 4.3. Schemas and evolution rules

As producers and consumers grow, relying solely on JSON documentation can become insufficient. Schemas describe data types, required fields, default values, and compatibility rules.

**Protocol Buffers (Protobuf)** uses field numbers in the wire format. Once a schema is published, never arbitrarily change an active field's number or reuse the number of a deleted field. Mark retired field numbers and names as `reserved`. Adding new fields with new numbers is usually compatible as long as existing semantics and wire-type rules hold. Never switch types just because two types look similar in Java code.

**Avro** supports schema evolution by matching the writer schema against the reader schema. A reader can decode data written with an older schema when resolution rules allow it. Default values for new fields in the reader schema play a key role when the writer schema lacks those fields.

**JSON Schema** and JSON schema tools validate payload structure, though compatibility depends on schema definitions and consumer configuration. For instance, adding an optional property is usually far lower risk than adding a required property absent from historical data.

When using a schema registry, define verification policies on schema registration: backward, forward, full, or a platform variant. The policy must match real deployment order and message retention windows. Messages can stay in queues or logs longer than the rollout window of a single application release.

### 4.4. Rolling out message changes step by step

Suppose you need to add `preferredLanguage` to a customer event. A safe rollout order typically follows:

1. **Upgrade consumers first.** New consumers handle old messages missing `preferredLanguage` while also understanding the field when present.
2. **Deploy new consumers.** Meanwhile, producers still emit the old format, so new consumers must process it normally.
3. **Upgrade producers.** Producers start sending `preferredLanguage`; if old consumers must stay compatible, they must safely ignore the new field.
4. **Monitor and wait out the transition window.** Watch deserialization errors, dead-letter queues, and lagging consumers.
5. **Retire old fields only after confirming no readers need them.** When removing fields, perform removal in a separate rollout respecting retention and replay windows.

For breaking changes such as altering core structure or meaning, consider creating a new event type or versioned channel such as `CustomerAddressChangedV2`. Consumers can support both during transition. Never silently emit a new structure under an old event name hoping every consumer understands it.

In systems supporting event replay, test historical data too. New consumers may have to read messages stored months earlier, not only recent payloads. If old schemas are discontinued, include a historical conversion step or retain matching decoders.

## 5. Comparing the three data forms

| Criterion | Files | Java Serialization | Messages |
|---|---|---|---|
| Common scope | Storage, batch exchange, import/export | Internal object state persistence | Cross-service or cross-process communication |
| Version identification | Header, metadata, schema name, or version field | `serialVersionUID` and class descriptors in stream | Schema version, event type, schema registry |
| Primary risks | Encoding, column order, binary layout, stale data | Coupling to Java classes and class-layout changes | Version skew between producer/consumer, queued backlog |
| Common mitigation | Versioned readers and file conversion | Controlled `readObject` or migrating to DTOs/other formats | Schema evolution and ordered consumer/producer rollouts |
| Essential testing | File fixtures from previous releases | Historical serialized streams saved as fixtures | Contract tests and historical message replay |

No single strategy fits all three. Files often need migration and archival workflows; Java Serialization demands tight class-version governance; messages require coordinating rollout order across components.

## 6. Execution workflow when upgrading data in Java applications

A practical workflow splits into these steps:

### Step 1: Inventory data sources

List files, file-backed tables, persistent caches, object streams, queues, topics, and API payloads that can survive across deployments. Record which version produced the data, where it lives, retention duration, and which components read it.

### Step 2: Gather real sample data

Collect representative samples from versions still requiring support. Redact sensitive information before committing fixtures into source control. Fixtures should include missing fields, null/empty values, boundary values, and historical cases that previously caused bugs.

### Step 3: Document contracts and compatibility matrices

For each format, record field names, types, meanings, units, defaults, missing-field rules, and supported versions. State explicitly which readers must decode which writers. Do not infer the contract merely from current Java class definitions.

### Step 4: Build centralized converters

Keep legacy-format parsing and conversion inside a dedicated class or module. Convert historical data into a stable internal model and keep business logic operating on that model. Avoid scattering `if (version == 1)` branches across the application.

### Step 5: Deploy in the proper order

For messages, usually upgrade consumers before producers start emitting new payloads. For files, establish when writers stop creating old formats and when existing files convert. For Java Serialization, confirm new classes read old streams or build standalone conversion utilities.

### Step 6: Monitor after migration

Track converted record/file counts, failure counts, source versions, and error causes. Keep recovery options ready when new data is invalid. For messages, monitor deserialization error rates, retries, and dead-letter queues.

## 7. Compatibility testing

Testing solely with data generated by the newest version misses most migration defects. Test across a version matrix and preserve sample fixtures long term.

### 7.1. Golden fixtures

Golden fixtures are sample files or messages generated by previous releases and preserved as fixed test inputs. Whenever classes or schemas change, test the current reader against all fixtures within the supported window.

For example, a test can confirm version 1 JSON data converts into the current model with proper defaults:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class CustomerFileMigrationTest {
    @Test
    void readsVersion1FileWithDefaultEmail() throws Exception {
        Customer customer = CustomerFileReader.read(
                getClass().getResourceAsStream("/fixtures/customer-v1.json"));

        assertEquals("C-1042", customer.getId());
        assertEquals("Nguyen An", customer.getName());
        assertNull(customer.getEmail());
    }
}
```

`CustomerFileReader` and `Customer` are illustrative names; in real projects, fixtures must come from real format outputs and assertions must reflect agreed data policy. If `null` is invalid, the test should verify a default value or explicit validation failure.

### 7.2. Producer/consumer matrix testing

For messages, test supported version pairs: old producer with new consumer, new producer with old consumer, and both new. Include valid messages, missing fields, unknown fields, and new enum values.

Contract tests verify that producers emit published schemas and consumers continue accepting payloads within the committed range. If using a schema registry, verify compatibility policies right inside the build or release pipeline.

### 7.3. Conversion and recovery testing

Beyond verifying reads succeed, check:

- Converted values preserve business meaning.
- Units, timezones, and numeric precision do not shift unexpectedly.
- Invalid data triggers clear errors without destroying original records.
- Re-running migration does not modify already migrated data.
- Newly written files can be re-read by new readers.
- Where forward compatibility is required, old readers handle new data per published policy.

For Java Serialization, archive at least one stream generated by every supported class version. Never regenerate old fixtures using new code, since regenerated fixtures no longer represent historical layouts.

## 8. Common design mistakes

**Renaming a field and assuming old data moves over automatically.** In Java Serialization, old and new field names do not map to each other automatically. In JSON or CSV, consumers also need explicit aliases or conversion rules.

**Adding a field and assuming it is always present.** Old data lacks the new field. Consumers must define defaults or handle missing cases.

**Keeping the type unchanged while changing the meaning.** Changing currency units, timezones, or rounding rules still breaks the contract. Introduce a new field or new version if old semantics cannot be preserved.

**Using `serialVersionUID` as a quick-fix switch.** Keeping UIDs equal may get past an initial check, yet it never turns two incompatible structures into compatible ones. Understand serialization rules and test with old serialized streams.

**Testing only freshly generated data.** That does not prove the application can read data already sitting in production. Preserve historical fixtures and test across the version matrix.

**Removing legacy fields or schemas too early.** Queues, event logs, backups, and exported files can outlive deployment windows. End support only after accounting for the entire lifecycle of historical data.

**Ignoring unknown fields unconditionally.** This can keep old consumers from crashing on new fields, yet it can also silently drop critical information. Ignore policies must align with business requirements and include error visibility.

## 9. Checklist before releasing a data change

- [ ] Identified every place where data is created, stored, and read.
- [ ] Documented format versions and the required compatibility matrix.
- [ ] Defined how new fields are handled when absent in old data.
- [ ] Preserved types, units, and meanings of existing fields without silent changes.
- [ ] Collected fixtures generated by prior releases still requiring support.
- [ ] Tested producer/consumer or writer/reader pairs in the planned rollout order.
- [ ] Verified migration jobs are idempotent and have data recovery procedures.
- [ ] Added logging or metrics to detect decoding errors and invalid data.
- [ ] Established when support for legacy formats or schemas ends.
- [ ] If using Java Serialization, evaluated deserialization risks and restricted allowed types.

## Conclusion

Data compatibility must be designed as part of the contract across application versions. For files, govern encoding, layout, and format versioning; for Java Serialization, understand `serialVersionUID`, class-change rules, and state recovery hooks; for messages, coordinate schemas and producer/consumer rollout order. With historical sample fixtures, centralized converters, and matrix-based compatibility tests, Java upgrades no longer rely on assuming every piece of data in the system was produced by the latest code.
