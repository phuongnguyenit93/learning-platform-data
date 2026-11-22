# Serialization Filters and Input Data from Other Application Versions

During **Java Advance Compatibility Migration**, an application may receive data produced by an older version, a newer version, or another service. If that data uses **Java native object serialization**, reading back the object is not only a matter of class and **serialVersionUID** compatibility. It is also a security boundary: **ObjectInputStream** can instantiate objects, trigger deserialization logic, and process an entire object graph before the application checks the root object's type.

This lesson belongs to the **Security and Access** chapter, focusing on **serialization filters** in Java, requirements for controlling data from other application versions, and how to upgrade without unintentionally expanding the set of classes permitted to deserialize.

A good filter needs to balance two goals:

1. **Controlled compatibility:** allow precisely the valid data structures of the versions that need to be supported.
2. **Reduced security and denial-of-service risk:** reject disallowed types, excessive depth, abnormal reference counts, oversized arrays, or streams exceeding appropriate limits.

**Scope note:** **ObjectInputFilter** belongs to Java's native serialization mechanism with **ObjectInputStream**. It does not automatically govern JSON via Jackson, XML, Protocol Buffers, Kryo, or other formats. Those formats require their own validation and limit mechanisms.

## 1. Why Is Serialized Data from Another Version a Security Issue?

A serialized Java object can contain type information, fields, and reference relationships across many objects. During deserialization, the runtime and participating classes may execute multiple steps before the **readObject()** call returns a value.

Example exchange flow:

~~~text
Application A / version 1
          |
          | Serialized bytes
          v
Queue / Cache / File / TCP
          |
          v
Application B / version 2
          |
          v
ObjectInputStream
          |
          +--> Resolve class
          +--> Build object graph
          +--> Restore state / run serialization hooks
          |
          v
Object returned to application code
~~~

Even when two applications belong to the same organization, received data can still be untrusted in a security sense:

- A queue or cache may hold old, unverified messages.
- A producer may have been compromised or misconfigured.
- Stored files may have been tampered with.
- Data may arrive from a partner system or an out-of-support version.
- A structurally valid payload may be oversized or contain an abnormal object graph.
- The producer and consumer versions have different dependency graphs.

A producer claiming to run the same Java version does not guarantee the data is safe. Conversely, data from an older version is not automatically dangerous; what matters is **provenance, format, allowed types, and processing limits**.

### 1.1. Two Compatibility Layers to Evaluate Separately

| Aspect | Question | Example |
|---|---|---|
| Serialization compatibility | Can the new consumer read streams from the old producer? | New fields, removed fields, serialVersionUID |
| Security acceptance | Should the consumer accept that object graph? | Class not in allowlist, depth exceeding threshold |

All four combinations can occur:

- Data is readable **and** permitted by policy.
- Data is technically readable but rejected by the filter.
- Data is permitted by policy but cannot be decoded due to differing schema/classes.
- Data is both incompatible and disallowed from processing.

Do not alter the allowlist merely to mask a serialVersionUID error. Nor should you modify **serialVersionUID** merely to bypass a filter rejecting a class.

### 1.2. Input Paths to Survey

In a real Java project, locate every direct or indirect call to **ObjectInputStream**:

- Byte streams over sockets or internal protocols.
- Backup/cache files containing Java serialized objects.
- Queues or messaging adapters using native serialization.
- Distributed caches, sessions, or legacy state storage.
- Batch jobs reading artifacts from a previous version.
- RMI or legacy components using object serialization.
- Frameworks, SDKs, or libraries with internal deserialization.

Not finding **new ObjectInputStream** in application source does not prove there is no deserialization. Frameworks may create streams inside libraries.

## 2. How Java Native Serialization Works Conceptually

Traditional Java serialization uses these main components:

- **Serializable:** marker interface indicating a class participates in standard serialization.
- **ObjectOutputStream:** writes an object graph to a stream.
- **ObjectInputStream:** reconstructs an object graph from a stream.
- **serialVersionUID:** version identifier of the class's serial form.
- Hooks such as **writeObject**, **readObject**, **readResolve**, **writeReplace**, and the **Externalizable** mechanism when supported by the class.
- Class loaders, field descriptors, and object references involved in reconstruction.

Simple example:

~~~java
package com.example.transfer;

import java.io.Serial;
import java.io.Serializable;

public final class TransferEnvelope implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;

    public TransferEnvelope(String requestId, long amount) {
        this.requestId = requestId;
        this.amount = amount;
    }

    public String getRequestId() {
        return requestId;
    }

    public long getAmount() {
        return amount;
    }
}
~~~

Example writing data:

~~~java
import com.example.transfer.TransferEnvelope;
import java.io.ByteArrayOutputStream;
import java.io.ObjectOutputStream;

ByteArrayOutputStream output = new ByteArrayOutputStream();

try (ObjectOutputStream stream = new ObjectOutputStream(output)) {
    stream.writeObject(new TransferEnvelope("REQ-001", 150));
}

byte[] payload = output.toByteArray();
~~~

Reading with **ObjectInputStream** reconstructs the object from information in the stream. However, **do not** read data from untrusted sources with **readObject()** without an appropriate security policy.

### 2.1. Why Is Type Checking After readObject Insufficient?

An unsafe pattern relying solely on a final type check:

~~~java
Object value = input.readObject();

if (!(value instanceof TransferEnvelope)) {
    throw new IllegalArgumentException("Unexpected type");
}
~~~

The problem: the object has already been deserialized **before** the **instanceof** check runs. The runtime may have already:

- Resolved many different classes.
- Instantiated nested objects.
- Processed arrays and reference graphs.
- Executed allowed deserialization hooks of classes.
- Consumed significant CPU or memory.

**ObjectInputFilter** brings class inspection and resource limits into the deserialization process itself, rather than waiting until after object reconstruction completes.

That does not mean a filter blocks every dangerous behavior. Filters must be combined with accepting data only from controlled sources, enforcing size limits at the transport layer, and validating object state after reading.

## 3. ObjectInputFilter and Foundational Mechanisms

**JEP 290 – Filter Incoming Serialization Data** introduced a filtering mechanism for native Java serialization data. **ObjectInputFilter** allows enforcing policy while **ObjectInputStream** is reconstructing an object graph.

Information a filter can observe includes:

- The class currently under consideration.
- Array length if an array is being processed.
- Object graph depth.
- Number of object references processed.
- Number of bytes consumed from the stream.

A filter returns one of three statuses:

| Status | Meaning |
|---|---|
| **ALLOWED** | Condition is permitted by the filter |
| **REJECTED** | Condition is rejected; deserialization must fail |
| **UNDECIDED** | Filter makes no definitive decision |

**UNDECIDED is not equivalent to REJECTED.** If you only use an allow pattern list without a rule rejecting all remaining classes, unmatched classes may still be processed depending on the overall policy. For untrusted input, design **deny by default** for disallowed classes.

### 3.1. Filters Do Not Validate Every Value

A serialization filter does not replace business validation. Specifically:

- A filter does not prove String values are valid.
- A filter does not ensure positive amounts or properly formatted requestIds.
- Cases such as directly encoded Strings may not invoke the class filter in the way an author expects.
- A filter does not verify signatures or producer identity.
- A filter does not confirm the payload is semantically valid after constructing the object.
- A filter does not imply an allowlisted class is always safe.

For example, an object with **requestId = null** and **amount = -100** may have a class entirely within the allowlist, yet must still be rejected by business validation.

## 4. Important Limits: depth, refs, bytes, and array

Filters can enforce thresholds to mitigate abnormal data risks.

| Limit | Meaning | Mitigated Risk |
|---|---|---|
| **maxdepth** | Maximum depth of the object graph | Excessively deep nested graphs |
| **maxrefs** | Maximum number of object references during reading | Too many nodes or references |
| **maxbytes** | Number of bytes from the serialized stream allowed by the filter | Oversized streams |
| **maxarray** | Maximum array length | Abnormal arrays causing memory pressure |

Example policy:

~~~text
maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=4096
~~~

The numbers above are **illustrative values only**, not safe defaults for every system. A valid payload containing deep structures or large item counts could be rejected by those same thresholds.

How to choose thresholds:

1. Measure valid baseline data.
2. Identify the largest sizes/shapes supported by the contract.
3. Account for overhead when producer and consumer are on different versions.
4. Set finite limits with a safety margin.
5. Test right below, at, and above the threshold.
6. Evaluate metrics on real data before rollout.
7. Update alongside controlled schema changes.

**maxbytes does not replace transport-layer limits.** If an application reads an entire multi-GB body into a **byte[]** before creating **ObjectInputStream**, the filter limit applies too late to prevent initial memory allocation. Enforce limits at the gateway, HTTP server, socket framing, file size, or corresponding ingress buffer.

## 5. Configuring Filters with Patterns

Java provides **ObjectInputFilter.Config.createFilter(...)** to build a filter from a pattern string.

Example:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "maxdepth=20;" +
    "maxrefs=1000;" +
    "maxbytes=1048576;" +
    "maxarray=4096;" +
    "com.example.transfer.TransferEnvelope;" +
    "!*"
);
~~~

Meaning:

- The **max...** patterns set resource limits.
- **com.example.transfer.TransferEnvelope** is an allowed class.
- **!* ** in pattern syntax (written without a space as **!***) rejects classes not matching preceding patterns.

The class allowlist pattern must cover the **actual object graph**, not only the root class the application expects to receive.

### 5.1. Pattern Order Matters

Patterns are evaluated in order to reach a decision on a class. For example:

~~~text
com.example.transfer.**;!*
~~~

allows classes in the **com.example.transfer** package and matching subpackages according to pattern rules, then rejects all remaining classes.

Meanwhile:

~~~text
!*;com.example.transfer.**
~~~

places an overly broad rejection rule first, leaving subsequent classes no chance to be allowed.

Therefore, place specifically scoped allow patterns **before** the catch-all rejection rule.

### 5.2. Do Not Open the Entire Ecosystem for a Single Error

An overly broad allowlist such as:

~~~text
java.**;javax.**;com.example.**;!*
~~~

can accept many types outside the data contract. Starting with the **java.** or **com.example.** namespace does not make a class automatically safe.

Start with the truly required DTO/message classes, identify auxiliary types that are deserialized, and open additional ones only with evidence.

### 5.3. Module-Qualified Patterns

Patterns can include a module name to bind classes to a specific module, using syntax like:

~~~text
module.name/package.or.ClassPattern
~~~

This can be useful when module identity is part of the deployment model. However, verify whether the class comes from a named module, automatic module, or unnamed module. Do not guess and copy module names from Maven artifact names.

### 5.4. Filters with Arrays

Filters can receive information about the array class and **arrayLength**. Class pattern rules detail how element types are matched; **maxarray** must still be set to block unreasonable sizes.

A valid stream may use arrays as components of the object graph, even when the root DTO does not declare an array directly because a dependency uses internal collections. Use tests and filter observation to decide which classes truly need to be allowed rather than opening global packages by guesswork.

## 6. Attaching Filters Directly to ObjectInputStream

An example reading a native serialization payload from a buffer **already size-bounded at ingress**:

~~~java
package com.example.transfer;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public final class TransferReader {
    private static final ObjectInputFilter FILTER =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=20;" +
            "maxrefs=1000;" +
            "maxbytes=1048576;" +
            "maxarray=4096;" +
            "com.example.transfer.TransferEnvelope;" +
            "!*"
        );

    public TransferEnvelope read(byte[] payload)
            throws IOException, ClassNotFoundException {

        // External limits must be applied before creating the payload.
        if (payload == null || payload.length > 1_048_576) {
            throw new InvalidObjectException("Invalid payload size");
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(payload))) {

            input.setObjectInputFilter(FILTER);

            Object value = input.readObject();

            if (!(value instanceof TransferEnvelope envelope)) {
                throw new InvalidObjectException("Unexpected root type");
            }

            validate(envelope);
            return envelope;
        }
    }

    private static void validate(TransferEnvelope value)
            throws InvalidObjectException {
        if (value.getRequestId() == null ||
                value.getRequestId().isBlank() ||
                value.getAmount() <= 0) {
            throw new InvalidObjectException("Invalid transfer data");
        }
    }
}
~~~

This example uses Java 17 or later for **instanceof pattern matching**, while demonstrating both ingress limits and stream filtering.

**Points to distinguish:**

1. The filter must be set **before** starting **readObject()**.
2. This policy permits only the **TransferEnvelope** class and special serialization protocol cases; if the object graph needs other classes, evaluate each additional class based on the contract.
3. Root type verification after **readObject()** is still required.
4. **validate(...)** is what checks business data validity.
5. For network payloads, size limits must be enforced when receiving data, **before** allocating large buffers; checking **payload.length** is only an additional defensive layer.
6. Do not include internal class/stack trace details in public errors sent back to an untrusted producer.

### 6.1. Why Not Just Catch Exception?

An anti-pattern to avoid:

~~~java
try {
    return deserialize(payload);
} catch (Exception ignored) {
    return null;
}
~~~

This approach conflates invalid payloads, missing classes, security violations, and programming bugs. It also makes it hard for the consumer to decide whether to retry or move the message to a dead-letter queue.

Classify errors and handle them at the appropriate boundary; do not automatically retry infinitely on a payload consistently rejected by a filter.

### 6.2. readObject Can Return Null or an Unexpected Type

Java serialization can represent null or a different root object than expected. Filters do not replace the **instanceof** check and DTO invariants.

If an API accepts multiple root message types, clearly define the union type or envelope contract instead of casting directly under the assumption every stream holds the same class.

## 7. JVM-Wide Filters and Context-Specific Policies

In addition to per-stream filters, Java supports broader serialization filter configuration.

### 7.1. Process-Wide Filter with jdk.serialFilter

You can configure the **jdk.serialFilter** system property at JVM startup.

Illustrative example:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=4096;com.example.transfer.TransferEnvelope;!*" -jar app.jar
~~~

Quotation marks keep the entire pattern string as a single JVM argument, preventing the shell from interpreting semicolons.

Notes:

- The filter applies JVM-wide and can affect multiple native deserialization paths.
- Overly strict policies can break frameworks or libraries unexpectedly.
- A global filter must not be treated as a replacement for business data validation.
- Test, batch, container, and production environments need separate configuration management.
- How the JVM combines global and per-stream filters depends on the active serialization filter factory.

Do not use a broad process-wide policy just to make every stream reader work. If a system has multiple trust boundaries, policies should differ by use case.

### 7.2. ObjectInputFilter.Config.getSerialFilter

Java can retrieve the configured global filter via **ObjectInputFilter.Config.getSerialFilter()**.

This is useful for diagnostics, but when an application sets a per-stream filter, understand the combination policy. Do not assume that calling **setObjectInputFilter** always accumulates all limits of the prior filter as desired.

### 7.3. JEP 415 – Context-Specific Deserialization Filters

**JEP 415** introduced a context-specific filter factory mechanism (Java 17), allowing filters to be selected or combined when **ObjectInputStream** is created and when a stream filter is set.

A system might have:

~~~text
JVM process
   |
   +--> Endpoint A: message TransferEnvelope
   |        -> Allow transfer DTO + limits A
   |
   +--> Endpoint B: cache session
   |        -> Allow session DTO + limits B
   |
   +--> Batch import job
            -> Allow legacy DTO + limits C
~~~

These input paths have different trust levels and object graphs. Using a single filter could force the team to open it too broadly to cover all input paths.

JEP 415 enables context-aware policies, yet the factory must be properly installed before deserialization occurs. Choosing a filter from an untrusted context declared by the payload itself can inadvertently let input dictate the allowlist.

### 7.4. Framework Integration

Some frameworks create **ObjectInputStream** internally and may offer their own filter configuration. If a library does not allow passing a filter directly:

- Check the official documentation and framework version.
- Determine whether a per-stream policy or filter factory can be configured.
- Investigate whether pre-processing is needed at the application boundary.
- If a JVM-wide filter must be used, measure its blast radius.
- Do not write a wrapper that silently bypasses the framework's policy.

In multi-module applications, designate an owner for the overall filter policy and where it is installed to avoid two libraries configuring incompatible factories.

## 8. serialVersionUID and Class Compatibility Between Two Versions

**serialVersionUID** helps the runtime determine serial-form compatibility between the class present on the consumer and the class descriptor in the serialized stream.

Example:

~~~java
public final class TransferEnvelope implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;
}
~~~

Keeping the same **serialVersionUID** can support some compatible schema changes, yet **does not guarantee** all older streams remain readable.

### 8.1. Adding Fields

Version 1:

~~~java
public final class OrderMessage implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;
}
~~~

Version 2:

~~~java
public final class OrderMessage implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;
    private String region;
}
~~~

With default serialization and other compatibility conditions satisfied, when v2 reads a v1 stream, **region** can receive the default value **null**. Application v2 must handle this cleanly:

~~~java
public String effectiveRegion() {
    return region == null ? "legacy" : region;
}
~~~

Do not assume **region** is always non-null merely because version 2's constructor always assigns it. Default deserialization does not run the Serializable class's constructor the way ordinary object instantiation does.

### 8.2. Removing Fields

A field present in v1 but removed from v2 is normally discarded rather than restored into the v2 object under default serialization. However, removing a field can cause business logic errors if the new class or custom hooks still depend on that information.

With rolling deployments, consider the reverse direction: producer v2 emitting streams for consumer v1. Do not test only v1 → v2 and skip v2 → v1.

### 8.3. Renaming Classes/Packages

Java native serialization's class descriptor is tied to the type name. Renaming a package or class is usually not a schema evolution that can be handled by keeping the same serialVersionUID.

You may need a controlled migration tool to read data with the old class and convert to a new DTO, or design a wire format independent of class names. Avoid arbitrarily overriding **ObjectInputStream.resolveClass** to accept classes from untrusted input; any such mechanism must be rigorously designed and verified.

### 8.4. Changing Field Types

Changing a field's type, inheritance hierarchy, or how custom serialization works can make old streams incompatible. An identical **serialVersionUID** does not eliminate those incompatibilities.

### 8.5. Do Not Edit serialVersionUID Just to "Make It Pass"

If you encounter:

~~~text
java.io.InvalidClassException:
local class incompatible:
stream classdesc serialVersionUID = ...
local class serialVersionUID = ...
~~~

first determine:

- How the old and new classes differ.
- Whether this is a supported serial-form change.
- Whether the stream contains any other types.
- Whether custom **readObject/writeObject** or **Externalizable** is used.
- Whether old data contains information needing migration.
- Whether the filter policy accepts that graph.

Setting the same UID and rerunning may push failure to a later step or silently lose data. It is not a general migration solution.

## 9. Serialization Hooks and Behaviors to Control

Java serialization allows classes to participate in reading/writing in custom ways.

Notable hooks:

- **private writeObject(ObjectOutputStream):** customizes how a Serializable class is written.
- **private readObject(ObjectInputStream):** customizes reading and invariant restoration.
- **readResolve():** can substitute the object returned after reconstruction.
- **writeReplace():** can substitute the object before writing.
- **Externalizable:** the class assumes greater responsibility for format and read/write operations.

Because of these hooks, inspecting field names in source alone is insufficient to understand the wire contract.

### 9.1. Checking Invariants in readObject

Example:

~~~java
package com.example.transfer;

import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;

public final class TransferEnvelope implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;

    public TransferEnvelope(String requestId, long amount) {
        if (requestId == null || requestId.isBlank() || amount <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }
        this.requestId = requestId;
        this.amount = amount;
    }

    public String getRequestId() {
        return requestId;
    }

    public long getAmount() {
        return amount;
    }

    @Serial
    private void readObject(ObjectInputStream input)
            throws IOException, ClassNotFoundException {

        input.defaultReadObject();

        if (requestId == null || requestId.isBlank() || amount <= 0) {
            throw new InvalidObjectException("Invalid transfer");
        }
    }
}
~~~

In this example, the constructor guards normally created objects, while **readObject** re-validates invariants when reconstructing from serialized bytes.

Still, business validation in **readObject** does not replace a filter. The filter must run while the object graph is being built, whereas invariant checks may occur after multiple classes have already been processed.

### 9.2. Do Not Trust Data Just Because the Constructor Validates

A Serializable class is not reconstructed by invoking its own constructor like an ordinary **new** expression. If validation exists only in the constructor, an object read from a stream can violate invariants.

A safer model:

~~~text
Ingress size limit
       |
       v
ObjectInputFilter
       |
       v
Deserialize graph
       |
       v
Class invariant checks / validation
       |
       v
Root type + business contract
       |
       v
Process / Persist
~~~

These steps complement one another. No single step alone is sufficient.

### 9.3. readResolve and the Final Object Type

**readResolve** can substitute the object after deserialization. Therefore, the class appearing in the stream and the final returned object may not be completely identical. This is yet another reason to both filter graph construction and verify the root object after **readObject()**.

## 10. Receiving Data from Another Application Version

Suppose a system upgrades from version A to B, while both versions continue running in parallel:

~~~text
Producer A -----+
                |
                +---- Queue / Cache ----> Consumer B
                |
Producer B -----+                      Consumer A
~~~

Evaluate **both directions**, not only checking whether the new consumer reads old payloads.

### 10.1. Compatibility Matrix

| Producer | Consumer | What to Verify |
|---|---|---|
| A | A | Baseline, current data |
| A | B | New consumer reading data from old producer |
| B | A | Old consumer reading data from new producer |
| B | B | Target behavior |
| A or B | Legacy batch/replay version | Long-lived payloads, batch classes and filters |
| External producer | B | Contract, version, trust boundary |

If B adds a new class to the object graph, consumer A might lack that class on its classpath. If B drops an old class from its allowlist, stream A may be rejected even if class A still exists in the codebase.

### 10.2. Filter and Schema Are Two Independent Checks

Example:

- V1 uses **LegacyTransfer**.
- V2 uses **TransferEnvelope**.
- V2 has a mapping converting LegacyTransfer to TransferEnvelope.

If v2 needs to read v1 streams, v2's filter must permit the classes **necessary** to construct **LegacyTransfer**, after which the application converts to the canonical model.

Do not allow every class in the legacy package just because an old stream contains LegacyTransfer. Explicitly identify the types present in the graph and the expiration window of old data.

### 10.3. Strategy to Support Two Message Types

A migration flow can be organized as:

~~~text
Serialized input
      |
      v
Bounded transport / authentication
      |
      v
ObjectInputFilter matching version and trust source
      |
      v
readObject + root type check
      |
      +--> LegacyTransfer -> convert -> CanonicalTransfer
      |
      +--> TransferEnvelope -> convert -> CanonicalTransfer
      |
      v
Canonical validation
      |
      v
Business logic
~~~

If there are only internal producers, establish a fixed time window for supporting both payload types. Once the old queue is drained and producer A is retired, remove **LegacyTransfer** from the allowlist.

### 10.4. Do Not Let a Version Field Dictate Deserialization Privileges

A payload can claim **version = 2**, yet that is data supplied by the sender itself. If the sender is untrusted, do not rely solely on a version field to select a broader allowlist.

Select policies based on **authenticated context** such as endpoint, producer identity, tenant boundary, topic/queue, and server-configured contract. Version can select a decoder after trust boundaries and format have been constrained, but it is not proof of provenance.

## 11. Configuring Filters for Historical Data

During migration, you may need to maintain multiple policy versions per input stream.

| Data Type | Suggested Policy | Duration |
|---|---|---|
| New messages from producer B | Allow only DTO B, current limits | Long-term |
| Legacy messages from queue A | Allow enumerated DTO A, tight limits | Until old backlog drains |
| Controlled stored snapshots | Dedicated policy matching snapshot schema | Per retention policy |
| External file uploads | Disallow native deserialization if avoidable | Long-term |
| Session cache shared between A and B | Allow only truly required shared classes | During rollout |

### 11.1. Measure Data Before Locking Policy

Do not measure limits from a single sample payload. Collect representative valid examples:

- Small and large messages.
- Object graphs with collections or arrays.
- Payloads from both producers A and B.
- Payloads generated from rare business branches.
- Caches/sessions persisting from the previous release.
- Replayed batch or retry data.
- Payloads with null or absent optional fields.

An allowlist missing a class causes **InvalidClassException** on deserialization; treat that error as a configuration/contract signal, not a reason to allow every class.

### 11.2. Record Allowed Classes with Justification

Example inventory table:

| Class | Producer | Consumer | Reason Allowed | Removal Date |
|---|---|---|---|---|
| com.example.transfer.TransferEnvelope | B | B | Canonical message | Indefinite |
| com.example.legacy.LegacyTransfer | A | B | Drain backlog A | After A retires |
| com.example.transfer.TransferDetail | B | B | Published nested DTO | Per schema |
| Class generated by internal library | A/B | A/B | Only if truly needed by valid graph | Periodic review |

Do not add new classes to the allowlist solely based on a name in an exception unless the class is verified to belong to a valid contract.

## 12. When Serialized Graphs Use Collections and Internal Types

A common migration failure is a filter allowing the root DTO while rejecting dependent classes.

Example DTO containing:

~~~java
private java.util.List<String> tags;
~~~

The stream may record a concrete implementation of **List**, not merely the List interface. How the producer constructs the list affects which concrete class gets serialized.

For example, an **ArrayList** and a collection created from JDK factory methods may not share the same serial form or implementation class. When upgrading the JDK and changing how collections are created, the filter may see different classes than the baseline.

**Controlled handling:**

1. Identify concrete serialized types from stored valid payloads.
2. Record producer version and collection creation code.
3. Prefer a wire DTO with a simple, stable shape.
4. Allow only types actually belonging to the contract.
5. Set graph and size limits.
6. Test both producer A → consumer B and B → A.
7. If multiple collection types must be supported, explicitly document and constrain them rather than opening entire JDK packages.

### 12.1. Do Not Confuse Classpath Dependencies with the Serialized Object Graph

An application has hundreds of dependencies, yet streams contain only specific objects. An allowlist should not mirror the entire classpath.

Conversely, a small DTO may transitively contain objects from another library via an **Object**-typed field or a custom serialization hook. Inventory must be based on the actual wire contract, not only class diagrams.

## 13. Common Errors and How to Classify Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| **InvalidClassException: filter status: REJECTED** | Class or limit rejected by filter | Identify class/metric, compare against policy and payload |
| **InvalidClassException: local class incompatible** | Incompatible serialVersionUID or serial form | Compare v1/v2 classes, fields, and hooks |
| **ClassNotFoundException** | Consumer lacks class referenced by stream | Check classpath and DTO migration plan |
| **StreamCorruptedException** | Data does not conform to object stream format | Check format, framing, corruption |
| **OptionalDataException** | Primitive/object data read out of order in custom serialization | Inspect readObject/writeObject |
| **EOFException** | Stream ended prematurely | Check truncated payload, network framing |
| **InvalidObjectException** | Validation during deserialization rejected object state | Check invariants, source, and schema |
| **ClassCastException** after readObject | Root object does not match type expected by consumer | Verify root type and version mapping |
| OutOfMemoryError or abnormal deserialization time | Graph/size exceeds processing capacity | Ingress limit, maxdepth/maxrefs/maxbytes/maxarray |
| Message A is read but business logic fails | Missing/default field not handled | Version mapping, validation, and invariants |
| Consumer A cannot read payload B | New schema/class not yet supported by A | Dual-write/compat DTO or versioned protocol |

**InvalidClassException** is not caused solely by filters. Read the full message and cause, and compare against the policy or serialVersionUID before fixing.

### 13.1. Is a Filter Error a Security Issue or a Compatibility Issue?

The same **REJECTED** status can mean different things:

- An abnormal payload contains a class outside the contract → the filter worked correctly.
- A valid message from producer A contains an old DTO not yet added to allowlist B → missing migration plan.
- A stream was rejected due to depth, yet it is a contract-valid object graph → thresholds need evaluation.
- An oversized payload or disallowed class was sent to an endpoint → do not widen the policy to "fix" the error.

Do not base decisions solely on a "REJECTED" log; gather context on source, contract, graph, and thresholds.

### 13.2. Error Information Exposed Externally

For untrusted senders, do not return the allowed class list, internal classpath, JDK module details, or full stack traces.

You can distinguish error categories internally while returning a stable public error code, for example:

~~~json
{
  "code": "INVALID_SERIALIZED_PAYLOAD",
  "message": "Unsupported or invalid input",
  "traceId": "request-123"
}
~~~

Technical details are stored in controlled security logs per organizational data policy.

## 14. Testing the Version Matrix and Negative Cases

Do not only test serializing and deserializing once inside the same process of version B. That test cannot detect differences between class versions and historical allowlists.

### 14.1. Generating Golden Payloads from Real Versions

In baseline A, store serialized bytes generated by artifact A itself using representative data. When needed, generate additional payloads with B.

Each fixture should record:

- Producer JDK and application version.
- Artifact checksum.
- Relevant classpath/dependency versions.
- Schema/message type.
- Payload length.
- Source and fixture generation conditions.
- Expected result at the consumer.

Do not regenerate payload A using class B and call it an "old version fixture"; that fails to test A's actual wire form.

### 14.2. Testing the Four Core Combinations

~~~text
               Consumer A       Consumer B
Producer A       A -> A           A -> B
Producer B       B -> A           B -> B
~~~

With rolling upgrades, both **A → B** and **B → A** may require support. If only one direction occurs in practice, explicitly document the dependencies and rollout schedule preventing the reverse direction.

### 14.3. Testing the Class Allowlist

Minimum tests:

1. Valid root DTO → allowed.
2. Valid nested DTO → allowed.
3. A class outside the contract → rejected.
4. A legacy class past end-of-support → rejected after cutoff.
5. Schema-valid array/collection → allowed if part of supported graph.
6. A graph with an unexpected type in an **Object** field → rejected.

**Note:** When testing adversarial inputs, use only safe fixtures created by the QA team in an isolated environment. Never use gadget payloads from untrusted sources to "see if it works" in production.

### 14.4. Testing Resource Limits

| Test | What to Verify |
|---|---|
| maxdepth | Graph exceeding threshold is rejected |
| maxrefs | Graph with too many references is rejected |
| maxarray | Abnormally long array is rejected |
| maxbytes | Stream exceeding limit is rejected |
| Ingress size | Oversized input is blocked before allocating large buffers |
| Truncated stream | Failure is classified without infinite retries |
| Valid maximum | Largest contract-valid payload is still processed |

Do not attempt to build huge object graphs to probe limits inside the same process serving users. Use bounded synthetic data and an appropriate test environment.

### 14.5. Testing Business Invariants

An object with a valid class but invalid fields must still fail.

Examples:

- requestId is null or blank.
- amount is negative or zero.
- Expiration date is earlier than creation date.
- Two fields conflict.
- Enum/value is no longer supported.
- Identifier points to a different tenant.
- Data passed the filter yet violates business rules.

Run these tests at the validator/service layer or in deserialization hooks when appropriate, while verifying no side effects occur before validation fails.

## 15. Rollout Checklist When Upgrading Versions

### 15.1. Before Migration

- [ ] Located native deserialization sites and frameworks indirectly using ObjectInputStream.
- [ ] Locked baseline/target JDK and application versions.
- [ ] Saved golden payloads generated by producer A.
- [ ] Identified trust boundaries and producer identities.
- [ ] Inventoried object graphs/classes required for each message type.
- [ ] Identified risks from Java serialization hooks and dependencies.
- [ ] Selected allowlist policy and resource limits.
- [ ] Configured payload limits at the ingress layer.
- [ ] Identified legacy message types to support during the transition.

### 15.2. During Migration

- [ ] Filter is attached before readObject.
- [ ] Do not allow classes outside the contract just because of a REJECTED error.
- [ ] Tested A → B and B → A if both versions run in parallel.
- [ ] Verified serialVersionUID, field evolution, and custom hooks.
- [ ] Root type and business invariants checked after deserialization.
- [ ] Ran tests for maxdepth/maxrefs/maxarray/maxbytes.
- [ ] Verified global/per-stream/context factory policies do not conflict.
- [ ] Set up metrics and logs for filter rejections while restricting sensitive data.
- [ ] Prepared rollback handling for messages written by the new version.
- [ ] Invalid payload errors do not cause retry loops or stall queues.

### 15.3. After Migration

- [ ] Confirmed producer A is decommissioned per plan.
- [ ] Confirmed legacy backlogs, caches, and sessions are past their support window.
- [ ] Removed unneeded legacy classes from the allowlist.
- [ ] Verified current policy against new fixtures.
- [ ] Recorded decision to keep or purge old stored data.
- [ ] Updated version/protocol documentation and filter owner.
- [ ] Added the next allowlist review to the JDK/dependency upgrade schedule.

### 15.4. Operational Metrics

Monitor:

- Number of filter **REJECTED** responses by endpoint/topic.
- Categorized deserialization error types.
- Observed payload sizes and reference depths within allowed security limits.
- Consumer lag, retry, and dead-letter counts.
- Proportion of legacy payloads still received.
- Number of cases where parsing succeeds yet business validation fails.
- Status of producers A/B during rolling deployment.

Do not write raw serialized bytes or sensitive information to diagnostic logs without appropriate protection policies.

## 16. When Should You Replace Java Native Serialization?

Java native serialization ties data to the Java class model and carries inherent risks when data is untrusted. For network boundaries or long-lived exchange between independent applications/versions, a wire format with an explicit schema is usually easier to govern.

Options to consider:

- **JSON:** easy to inspect with clear field versioning, though requires parser limits and control over polymorphic deserialization.
- **Protocol Buffers:** explicitly defined schema supporting well-defined field evolution rules.
- **Avro:** schema and compatibility mechanisms by design.
- **CBOR or other binary formats:** require defined schemas, limits, and type handling.
- **DTOs with a versioned envelope:** decouple the network contract from internal class names.

**Changing format does not automatically ensure security.** The new parser still needs size limits, depth limits, allowed types, authentication, and business validation. If using Jackson polymorphic typing, control subtypes and configuration rather than opening arbitrary class names.

### 16.1. Format Migration Roadmap

~~~text
Producer A: Java serialized bytes
                 |
                 v
       Legacy reader (strict filter)
                 |
                 v
       Validate + canonical DTO
                 |
                 v
       Encode schema-based format
                 |
                 v
       New consumers B/C
~~~

During the transition period, you can maintain an adapter reading the legacy format in a controlled environment. Once backlogs and retention windows expire, remove the adapter and legacy classes from the runtime path.

### 16.2. Do Not Blindly Convert Format While Reading an Untrusted Stream

An adapter must still deserialize the legacy payload in order to convert it. If that step uses an unfiltered, unbounded ObjectInputStream, converting to JSON afterward does not eliminate the risk at the entry point.

Therefore, prioritize:

1. Ingress data size limits.
2. Filter allowlists and resource limits.
3. Deserialization in an appropriate environment.
4. Root type + business validation.
5. Conversion to the new DTO/schema.
6. Writing out in the new format.

## 17. Security and Compatibility Decision Record Template

To avoid opening allowlists arbitrarily during migration, each policy should have a decision record:

~~~text
Policy ID:
Owner:
Input endpoint / topic / file source:
Trust boundary:
Producer identities:
Producer versions:
Consumer versions:
JDK versions:
Serialized root types:
Permitted nested types:
Filter pattern / filter factory:
maxdepth:
maxrefs:
maxbytes:
maxarray:
Ingress size limit:
Business validation:
Supported serialVersionUID:
Custom serialization hooks:
Old-version fixtures:
Negative fixtures:
Observed filter rejections:
Temporary legacy allowlist:
Legacy removal condition:
Fallback / rollback:
Evidence location:
Approval:
Review date:
~~~

Illustrative example:

~~~text
Policy ID: SER-TRANSFER-02
Input: transfers-queue
Producer: Transfer Service A or B (authenticated internally)
Consumer: Settlement Service B
Root: TransferEnvelope
Temporary legacy type: LegacyTransfer
Allowed until: A stopped, queue drained, retention window elapsed
Filter: narrow allowlist + depth/refs/bytes/array limits
Validation: positive amount, nonblank requestId, tenant authorization
Evidence: golden A->B and B->B tests, filter negative tests
Owner: Integration team
~~~

A policy is considered complete only when there is evidence that valid data is processed, out-of-contract data is blocked, and rollout/rollback paths have safe procedures. Writing a filter string without testing is insufficient.

## 18. Common Mistakes

### 18.1. Checking instanceof Only After readObject

The object graph has already been reconstructed before the check is reached. Attach the filter before reading, and still verify the root type and business invariants afterward.

### 18.2. Making Allowlists Too Broad to Preserve Backward Compatibility

Allowing every class in an internal package or every JDK class because an old payload was rejected increases the attack surface. The solution is to inventory the graph and allow only the classes truly required.

### 18.3. Forgetting the Default Deny Rule

A pattern that allows a few classes while leaving the rest **UNDECIDED** may fail to achieve allowlist enforcement. You need a policy rejecting unpermitted classes and a clear understanding of how filters combine.

### 18.4. Treating serialVersionUID as Equivalent to a Schema Version

A UID does not describe all field, class hierarchy, and custom hook changes. Do not alter a UID to bypass errors without verifying the serial form.

### 18.5. Testing Only A → B and Skipping B → A

Rolling deployments can cause consumer A to receive messages created by producer B. If this direction is unsupported, rollout must prevent that flow through an explicit deployment strategy.

### 18.6. Applying Limits After Reading the Entire Payload

Checking **payload.length** after reading a large body into RAM does not prevent allocation cost. Limits must exist at the ingress layer.

### 18.7. Trusting the Version Field Inside the Payload

A version supplied by the sender is not proof of identity. Select trust policies from authenticated context and server configuration.

### 18.8. Failing to Check Collection Implementation Changes

v1/v2 data may serialize different concrete collection classes. Inspect real object graphs and restrict to required classes; do not open all of **java.util**.

### 18.9. Logging Full Payloads When Filters Reject

Raw serialized bytes may contain sensitive data or be excessively large. Log request/trace IDs, policy IDs, error types, and bounded metrics; store payloads only under secure investigation procedures.

### 18.10. Assuming Switching to JSON Automatically Solves Security

JSON parsers can also face risks when using polymorphic typing, deep nesting, or oversized payloads. They require separate schema validation, type allowlists, and resource limits.

## 19. Official Reference Documentation

When applying to a real system, cross-check APIs and documentation for the target JDK release:

- **JEP 290 – Filter Incoming Serialization Data:** https://openjdk.org/jeps/290
- **JEP 415 – Context-Specific Deserialization Filters:** https://openjdk.org/jeps/415
- **ObjectInputFilter API (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- **ObjectInputStream API (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- **Java Object Serialization Specification:** https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html
- **Serializable API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- **InvalidClassException API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InvalidClassException.html

For frameworks or libraries performing native serialization indirectly, read their version-specific documentation to understand how they install per-stream filters, JVM-wide filters, or filter factories.

---

**Conclusion:** When receiving Java-serialized data from another application version, you cannot rely solely on **serialVersionUID** or **readObject()** returning the expected class. Design trust boundaries, enforce size limits at the ingress layer, apply **ObjectInputFilter** with a class allowlist and resource limits, verify business invariants after reading, and test old and new producer/consumer combinations. A serialization filter is an important layer of defense, not a tool that renders arbitrary serialized objects safe. The long-term roadmap should move toward explicit data contracts with minimal dependence on Java class internals and verified schema evolution.