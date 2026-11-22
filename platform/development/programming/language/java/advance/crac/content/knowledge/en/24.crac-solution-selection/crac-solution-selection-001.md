# CRaC and Java Serialization: Differences in What Is Saved

Both CRaC and Java serialization can help a Java program continue using previously saved state, but they save different things and serve two different goals. Java serialization writes a selected object graph into a byte stream. CRaC coordinates with the JVM and a checkpoint engine to capture the state of the entire process at a point in time, then restores the process to continue execution.

Therefore, when using Java serialization, the developer decides which root object is written and which fields belong to the object graph. When using CRaC, the persistence boundary is the running process/JVM: the heap, thread state, and various runtime states supported by the checkpoint engine are saved together. The application must still prepare external resources such as connection pools, sockets, consumers, tokens, and leases so they remain valid after restore.

This difference determines how to choose a solution:

- If the goal is to store a set of business objects or exchange data between components, serialization may be appropriate.
- If the goal is to reduce startup time by resuming an application that is already initialized, warmed up, and has frameworks loaded, CRaC is more suitable.
- If data needs to be stored long-term, stable across multiple application versions or multiple languages, consider a schema-based data format such as JSON, Avro, or Protocol Buffers rather than treating Java serialization as the default durable storage format.

## 1. Two State-Saving Mechanisms at Two Different Boundaries

### 1.1. Java Serialization Saves a Selected Object Graph

Java serialization writes an object graph starting from one or more root objects into an ObjectOutputStream. The stream contains class metadata, serialized fields, and reference relationships needed to reconstruct the graph.

Example:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(order);
}
~~~

In this example, order is the root object. Serialization follows references from order to objects that can be serialized according to Java serialization rules. It does not automatically write the entire heap, every Spring bean, every thread, or every static variable in the application.

Normally, a class needs to implement java.io.Serializable to participate in the default mechanism. Non-static and non-transient instance fields are considered for writing to the stream. If the graph contains a non-serializable object, the operation may throw NotSerializableException, unless the class handles that field via custom serialization hooks or excludes it from the state to be saved.

### 1.2. CRaC Saves Process/JVM State

CRaC (Coordinated Restore at Checkpoint) enables checkpointing a running Java process and then restoring the process from the created image. The scope of the checkpoint is coordinated by the JVM, the CRaC runtime, and the specific engine. With a CRIU-based engine, process and operating system state are dumped/restored according to kernel and CRIU capabilities; other engines have their own implementations.

A checkpoint image typically retains a lot of state that Java serialization does not handle:

- Objects in the JVM heap, without requiring each business class to implement Serializable.
- Execution state of threads and stacks at the checkpoint point, within the scope supported by the engine.
- Loaded classes and internal JVM state.
- Portions of runtime/native state and process state that the engine can capture.
- File descriptors, memory mappings, and OS resources according to the engine's checkpoint capabilities.

This is not a guarantee that every socket, file, native thread, or external connection will continue working after restore. The application needs to register resources or use framework/library integrations to close, refresh, and recreate resources that cannot safely remain open.

### 1.3. Visualizing the Persistence Boundary

~~~mermaid
flowchart TD
    subgraph SER[Java serialization]
        A[Root object] --> B[Object graph via references]
        B --> C[Serializable fields and custom hooks]
        C --> D[Byte stream]
        D --> E[ObjectInputStream]
        E --> F[Reconstructed object graph]
    end
    subgraph CRAC[CRaC checkpoint/restore]
        G[Running JVM application] --> H[Resource beforeCheckpoint]
        H --> I[Checkpoint engine captures process/JVM state]
        I --> J[Checkpoint image]
        J --> K[Restore process/JVM]
        K --> L[Resource afterRestore]
        L --> M[Application resumes execution]
    end
~~~

Serialization produces a data representation of a selected object graph. CRaC creates an image of the process's execution state. The two outputs are not interchangeable.

## 2. Direct Comparison

| Aspect | Java serialization | CRaC |
|---|---|---|
| Unit saved | Object graph starting from a root object | Process/JVM state at checkpoint |
| Scope | Objects and fields handled by serialization | Heap, thread/process/runtime state supported by the engine |
| Data selection | Developer calls writeObject() with a root object | Choose checkpoint timing and prepare Resources |
| Class requirements | Usually requires Serializable or Externalizable | Does not require heap classes to implement Serializable |
| Static variables | Not part of default object serialization state | Part of class/JVM state in the image if retained by the runtime |
| Transient fields | Ignored under default mechanism | Still reside in the heap snapshot like other fields |
| Threads and stacks | Does not serialize thread execution state | Can be checkpointed/restored depending on the engine |
| Sockets and connections | Cannot be serialized as live connections | May be partially handled by the engine, but usually require callbacks to close/recreate connections |
| Resumption point | Deserialization constructs a new object graph; application decides how to resume work | Process continues from the checkpointed state |
| Portability | Stream can be moved across Java environments with compatible classes/schema | Image usually depends on JDK build, engine, OS, kernel, CPU, and runtime |
| Versioning | Depends on serialVersionUID, class evolution, and custom hooks | Depends on engine/runtime checkpoint image compatibility |
| Common goal | Persist/exchange an object graph | Reduce startup by restoring an initialized application |
| External resource management | Application must manually manage non-serializable handles | Application coordinates via CRaC Resource or integrations |
| Security | Deserializing untrusted data risks gadget/deserialization attacks | Checkpoint image can contain secrets and sensitive execution state |

## 3. Which Objects Does Java Serialization Save?

### 3.1. Starting from the Root Object

Serialization does not scan the entire heap automatically. It starts from the object passed to writeObject() and traverses reference fields participating in serialization.

Example:

~~~java
import java.io.Serializable;
import java.util.List;

public final class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final CustomerSnapshot customer;
    private final List<OrderLineSnapshot> lines;

    public OrderSnapshot(
            String orderId,
            CustomerSnapshot customer,
            List<OrderLineSnapshot> lines) {
        this.orderId = orderId;
        this.customer = customer;
        this.lines = List.copyOf(lines);
    }
}
~~~

When writing OrderSnapshot, serialization continues processing customer, elements in lines, and subsequent referenced objects if they are serializable. If a required object in the graph does not support serialization and is not handled customly, writing will fail.

Therefore, the saved scope depends on the object graph structure and each class's serialization contract. Changing a reference field can enlarge the graph and cause serialization to fail if the new object is incompatible.

### 3.2. Shared References and Circular References

Java serialization has a handle mechanism to preserve reference relationships within the same stream. If two fields point to the same object, upon deserialization they can continue pointing to the same instance in the new graph. Circular references are also supported.

Example:

~~~java
public final class SharedCustomerReference implements Serializable {
    private static final long serialVersionUID = 1L;

    private final CustomerSnapshot billingCustomer;
    private final CustomerSnapshot shippingCustomer;

    public SharedCustomerReference(CustomerSnapshot customer) {
        this.billingCustomer = customer;
        this.shippingCustomer = customer;
    }
}
~~~

CustomerSnapshot also implements Serializable. Both fields of SharedCustomerReference hold a reference to this same object:

~~~java
CustomerSnapshot customer = new CustomerSnapshot("C-100");
SharedCustomerReference snapshot =
        new SharedCustomerReference(customer);

try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(snapshot);
}
~~~

In the example, SharedCustomerReference has two reference fields pointing to customer and the classes in the graph implement Serializable. When reading the snapshot via ObjectInputStream, both fields can continue pointing to the same instance in the new graph. Serialization's handle table preserves shared references and supports circular references within the same stream.

This is a property of the object graph within a single stream; it does not mean serialization preserves object identity between the old process and the new process.

### 3.3. Rules for static and transient

Static state belongs to the class, not to individual object instances. Default Java serialization does not write static fields as part of an object's state.

Transient fields are skipped during default serialization. After deserialization, transient fields receive default values (null, 0, false) or are re-initialized via custom readObject()/application initialization logic.

Example:

~~~java
import java.io.Serializable;

public final class UserSessionSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String userId;
    private transient String accessToken;
    private static long activeSessionCount;

    public UserSessionSnapshot(String userId, String accessToken) {
        this.userId = userId;
        this.accessToken = accessToken;
    }
}
~~~

When serializing this object by default:

- userId is written.
- accessToken is skipped because it is transient.
- activeSessionCount is not written as an object field.

After deserialization, the application must re-issue the token or recreate transient state per policy. Do not serialize credentials simply because the field exists in the object.

With CRaC, transient does not exclude a field from the checkpoint. If the object is in the heap at checkpoint time, the transient field's value remains part of the heap state captured by the runtime mechanism. To discard or replace a value before/after restore, handle it explicitly via callbacks/resources or bootstrap logic.

### 3.4. Custom Serialization Hooks

Java serialization allows customizing how objects are written/read through methods such as:

- private void writeObject(ObjectOutputStream out)
- private void readObject(ObjectInputStream in)
- private Object writeReplace()
- private Object readResolve()
- Externalizable.writeExternal() and readExternal()

Example:

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class UserSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String userId;
    private transient String accessToken;

    private void writeObject(ObjectOutputStream out) throws IOException {
        out.defaultWriteObject();
        // Write only additional data allowed under the serialization contract.
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();
        // Restore transient state according to security policy.
        accessToken = null;
    }
}
~~~

These hooks only affect Java serialization. They are not invoked merely because a CRaC checkpoint or restore occurs. CRaC does not serialize individual objects using ObjectOutputStream; it checkpoints the process state.

### 3.5. Classes Not Implementing Serializable

If an object not implementing Serializable appears in the default graph, serialization normally throws NotSerializableException. A class can handle that field by:

- Marking the field as transient.
- Writing an alternative representation in writeObject().
- Using writeReplace() to substitute the object with a serializable proxy.
- Implementing Externalizable if full control over the representation is desired.

For a serializable subclass with a non-serializable superclass, the no-argument constructor of the non-serializable superclass is invoked during deserialization to initialize the superclass portion. Classes in complex systems therefore need a clear serialization contract.

CRaC imposes no such requirement on business classes. An object in the heap does not need to implement Serializable to be included in a checkpoint. However, native resources held by an object may not recover simply because the wrapper object remains in the heap.

## 4. What Does CRaC Save Beyond the Object Graph?

### 4.1. Heap and Object State

The heap is the region holding live JVM objects. At checkpoint, existing object state is saved with the process according to engine capabilities. Static fields, transient fields, objects not implementing Serializable, and framework objects can all reside in the heap snapshot.

For example, a Spring Boot application may already have:

- Created the ApplicationContext and singleton beans.
- Bound configuration into beans.
- Loaded schemas, parsers, and metadata.
- Warmed up caches.
- Loaded classes and optimized several code paths.

If the checkpoint is created after these steps, the created state can be preserved in the image. After restore, the application continues from the saved runtime state rather than deserializing each bean individually.

### 4.2. Threads and Execution State

Java serialization does not save thread stacks or a thread's execution position. An object having a field referencing a Thread does not turn the thread into a resumable part of the object graph.

CRaC checkpoints the running process, so thread state and execution state are part of the checkpoint/restore problem. Specific capabilities depend on the JVM, engine, and operating system. Before checkpoint, the application must coordinate so threads are not stuck in an unrecoverable I/O operation or critical section.

For workers, executors, and schedulers, determine:

- Which threads can resume after restore.
- Which threads must be stopped and recreated.
- How in-flight tasks are completed, canceled, or retried.
- Whether shut-down executors are replaced with new instances.
- That two workers do not process the same job after multiple replicas are restored.

Do not treat a thread's presence in the image as proof that the dependency or work the thread was waiting on is still valid.

### 4.3. Class Metadata and JVM State

Java serialization saves class descriptors and object data required to construct the graph. It does not save a JVM with loaded classes, JIT code cache, or full runtime state.

A CRaC checkpoint can retain JVM state such as loaded classes and runtime components supported by the engine. This helps avoid part of the startup, class loading, and warm-up overhead. However, retention depth and compatibility conditions depend on the engine/JDK; do not assume a checkpoint image can be moved arbitrarily between JDK builds.

### 4.4. Native Memory and Operating System Resources

A Java application can hold off-heap state:

- Direct ByteBuffers.
- JNI/native library allocations.
- File descriptors and memory mappings.
- Sockets and connection pools.
- Native threads and event loops.
- GPUs, devices, or specialized OS resources.

Serialization only writes the object graph according to contract. It does not preserve these native resources verbatim.

The CRaC engine can checkpoint portions of process/native state and file descriptors, but resources depending on external peers such as database connections, broker sessions, or TLS sessions typically need to be closed and recreated. The continued existence of a wrapper object does not guarantee the underlying native handle is still usable.

## 5. CRaC Resource Callbacks and Serialization Hooks Are Not the Same

This is an important distinction when integrating external resources.

### 5.1. CRaC Resource

An application can implement org.crac.Resource to prepare before checkpoint and recover after restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseClientResource implements Resource {
    private final DatabaseClientFactory factory;
    private DatabaseClient client;

    public DatabaseClientResource(DatabaseClientFactory factory)
            throws Exception {
        this.factory = factory;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.stopAcceptingWork();
            client.drain();
            client.close();
            client = null;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = factory.create();
        client.verifyConnection();
    }
}
~~~

DatabaseClient and DatabaseClientFactory are illustrative application-defined types. In practice, use the official lifecycle API of the pool or driver. The example illustrates the idea: close the resource before checkpoint, then recreate and verify it after restore.

### 5.2. Serialization Hooks

writeObject() or readObject() is invoked while writing/reading an object stream. It does not run automatically when the JVM checkpoints. If serialization is used to save a client configuration, readObject() can recreate some transient fields, but that is object graph deserialization logic.

### 5.3. Comparison Table

| Mechanism | When invoked | Purpose | Scope |
|---|---|---|---|
| writeObject() | When ObjectOutputStream serializes an object | Customize data written to the stream | A class/object graph |
| readObject() | When ObjectInputStream deserializes an object | Reconstruct object state | A class/object graph |
| writeReplace() | During serialization | Replace an object with a proxy/other representation | An object |
| readResolve() | After deserializing an object | Replace the newly read object with another instance | An object |
| beforeCheckpoint() | Before CRaC checkpoint | Quiesce, flush, close, or prepare resources | Resource/process |
| afterRestore() | After CRaC restore | Reconnect, refresh, and verify resources | Resource/process |

Do not use serialization hooks to replace CRaC callbacks. Nor should CRaC callbacks be used as a mechanism for writing business objects to files.

## 6. Example: Same State, Two Ways to Save It

Suppose an application has a ReportModel object containing computed data for rendering a report.

### 6.1. Saving the Object Graph with Serialization

~~~java
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

public final class ReportModel implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String reportId;
    private final List<ReportLine> lines;
    private final BigDecimal total;

    public ReportModel(
            String reportId,
            List<ReportLine> lines,
            BigDecimal total) {
        this.reportId = reportId;
        this.lines = List.copyOf(lines);
        this.total = total;
    }
}
~~~

Writing and reading:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(snapshotPath))) {
    out.writeObject(reportModel);
}

ReportModel restored;
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(snapshotPath))) {
    restored = (ReportModel) in.readObject();
}
~~~

The result is a new object graph constructed from the stream. The application must decide when to read the file, check data version, handle errors, and pass the object into a service.

### 6.2. Saving Application State with CRaC

With CRaC, the application initializes the model and related beans in the heap, then creates a checkpoint. Upon restore, the process resumes from the checkpointed state:

~~~java
ReportModel reportModel = reportService.prepareReport();
// Initialize caches, parsers, and required components.
// Reach the checkpoint requested by the runtime/operator.
// After restore, the application continues using the restored heap state.
~~~

The code above only illustrates where the state resides. The application must use the CRaC runtime/engine, trigger checkpointing via the environment's mechanism, and register resources for external dependencies. No ObjectOutputStream is called to save reportModel.

### 6.3. When Is Each Approach Appropriate?

If you only need to save ReportModel to reload later or send to another process, serialization (or a schema-based data format) is the more appropriate boundary.

If the goal is fast startup of an entire service with loaded frameworks, configuration, caches, and metadata, CRaC can preserve process state more appropriately. Using serialization to write a single report model does not replace restoring the JVM, threads, bean graph, and runtime state.

## 7. Lifecycle Differences After Recovery

### 7.1. Deserialization Constructs New Objects

ObjectInputStream.readObject() constructs an object graph in the current process. It does not return the program to the exact instruction executing when the stream was written. Constructors and the serialization protocol apply per Java rules; deserialized objects have new identities compared to objects in the prior process, even though the graph can preserve shared references within the stream.

The application needs to:

- Validate data after deserialization.
- Verify versions and invariants.
- Re-initialize transient state.
- Wire objects into services or repositories.
- Handle side effects if loading objects triggers additional actions.

### 7.2. CRaC Restore Continues the Process

CRaC restore recovers the process from the checkpoint image. The application continues from the saved runtime state. There is no generic step that automatically invokes constructors for every bean or re-deserializes individual objects.

Resource callbacks and framework integrations handle what needs to be prepared again. After restore, the application must still verify:

- Database and broker connections.
- Tokens, certificates, and secrets.
- Leases and leader ownership.
- DNS, endpoints, and current environment metadata.
- Replica identity if the same image is used across multiple instances.
- Cache freshness and scheduler deadlines.

### 7.3. Portability

Java serialization produces a byte stream that can be written to a file or transmitted over a network. However, the stream still depends on available classes, serialVersionUID, schema, and how classes handle class evolution. Java serialization is not a language-neutral format.

A CRaC checkpoint image is typically bound to a specific JDK build, engine, kernel, OS, CPU architecture, container runtime, and environment state. Do not assume an image can be copied from an arbitrary node to another or restored with a different JDK version without compatibility verification.

## 8. Versioning and Data Compatibility

### 8.1. serialVersionUID

A Serializable class can declare serialVersionUID to control compatibility between the class used when writing and the class used when reading:

~~~java
private static final long serialVersionUID = 1L;
~~~

If not declared, Java can compute a default value based on class structure. Modifying the class can change this value and cause InvalidClassException during deserialization.

Declaring the same serialVersionUID does not automatically guarantee all changes are safe. Adding/removing fields, changing data types, changing invariants, or modifying custom serialization logic must still be tested.

### 8.2. Class Evolution

With serialization, policies are needed for:

- Do new fields have default values or require migration?
- Are removed fields still tolerated when reading old streams?
- Have data types changed?
- Does readObject() need to convert old data?
- Do serialization proxies preserve compatibility?
- Can streams from multiple application versions be read?

For data that needs long-term storage, explicit schema versions and migrations are usually easier to manage than relying entirely on Java object serialization.

### 8.3. Checkpoint Image Evolution

Because a CRaC image stores runtime state, upgrading the JDK, GC, native libraries, agents, frameworks, or container base image can render old images incompatible. Recreate the checkpoint image through a verified pipeline when upgrading the runtime.

Do not use serialVersionUID to solve checkpoint image compatibility. The two mechanisms have completely different versioning contracts.

## 9. Security

### 9.1. Risks of Java Deserialization

Do not deserialize Java object streams from untrusted sources. An object graph can trigger behavior during deserialization via gadget chains or custom serialization hooks of classes present on the classpath.

If Java serialization must be used:

- Read streams only from trusted and authenticated sources.
- Apply ObjectInputFilter to restrict allowed classes, graph depth, reference count, array size, and byte count.
- Do not allow arbitrary classes just because they implement Serializable.
- Validate data after deserialization.
- Prefer schema-based formats and safe parsers for externally exchanged data.

Example illustrating an allowlist-based filter:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "com.example.snapshot.*;java.base/*;!*");

try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(snapshotPath))) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

The filter must be tuned to the actual graph. The example above illustrates filter pattern syntax; it should not be copied verbatim without checking valid classes and resource limits.

### 9.2. Protecting CRaC Checkpoint Images

A checkpoint image may contain all or a large portion of a process's memory state, including:

- Passwords, access tokens, and refresh tokens.
- Private keys, certificate material, and session secrets.
- User data or request payloads.
- Connection details and internal configuration.
- Transaction state or business caches.

Therefore:

- Only create and restore images from trusted pipelines/sources.
- Restrict read, write, and download permissions on checkpoint images.
- Encrypt at rest and in transit as required by the platform.
- Manage retention and delete images per policy.
- Do not push images to public registries.
- Do not log sensitive contents from the heap or resource callbacks.
- Refresh credentials after restore when they could expire or be rotated.

Both serialization streams and CRaC images must be protected, but their data surfaces differ. A stream may contain only a single object graph; a checkpoint image may contain a much broader state of the application.

## 10. Performance and Cost

### 10.1. Java Serialization

Cost depends on object graph size, object count, reference count, custom hooks, I/O, and object allocation during deserialization. The advantage is being able to save only the required data. If the graph is small and well-structured, writing/reading a few objects can be simpler than checkpointing an entire process.

The drawback is that the application must select the exact graph, handle class compatibility, restore transient state, and re-integrate objects into the application lifecycle.

### 10.2. CRaC

Checkpoint/restore cost depends on memory size, thread count, mapping count, resource count, checkpoint engine, and OS environment. A large image can consume storage space, copy time, and restore time.

The advantage is preserving initialized state at the process level, which can significantly reduce repetitive startup work. The drawback is that the image depends on the runtime/environment and external resources still require handling.

### 10.3. Do Not Compare the Two Mechanisms Solely by File Write Time

A fair measurement needs to account for the full workload:

| Metric | Serialization | CRaC |
|---|---|---|
| Snapshot creation time | Write object graph to stream | Create checkpoint process image |
| Size | Size of serialized object graph | Size of checkpoint image |
| Recovery time | Deserialize and integrate objects into app | Restore process/JVM and recover resources |
| Additional work | Reinitialize transient state, validate graph | Reconnect, refresh credentials, readiness |
| Restored scope | Selected object graph | Process state per engine |

If the goal is startup time, measure CRaC's restore-to-ready and first-request latency. If the goal is loading a dataset, measure deserialization, validation, and graph integration time. Do not compare the time to write a small object against the time to create a full JVM image to conclude which mechanism is faster overall.

## 11. Choosing a Solution Based on the Problem

### 11.1. Choose Java Serialization When

- You need to save a specific object graph.
- Classes have a clear serialization contract.
- Data needs to be written/read as a stream.
- There is no need to restore threads, the JVM, or an executing process.
- The application can re-initialize resources and runtime state itself.
- The stream source is trusted and has appropriate versioning/filtering policies.

Java serialization is typically suited for internal data within a controlled boundary. For long-term storage or cross-language communication, consider JSON, Avro, Protobuf, or another schema-based format.

### 11.2. Choose CRaC When

- You need to reduce startup time for an initialized Java application.
- Major overhead lies in framework startup, class loading, warm-up, or loading data into the heap.
- You want to resume the runtime state of the entire process.
- The JDK/engine and deployment environment support checkpoint/restore.
- External resources can be prepared and recovered using CRaC Resources or integrations.
- Processes exist to protect, build, distribute, and test checkpoint images.

### 11.3. Use Both Together When

Both mechanisms can coexist in an application because they address two different boundaries:

- Serialization persists a subset of durable business data or exchanges data across systems.
- CRaC preserves initialized process state to reduce startup.

For example, an application can read a data snapshot from a schema-based format, populate an in-heap cache, and then create a CRaC checkpoint to clone the warmed-up environment. After restore, the application still needs to verify cache freshness and connections. You do not need to serialize the entire bean graph just to create a checkpoint.

## 12. Common Misconceptions

| Misconception | Reality |
|---|---|
| CRaC is Java serialization at the JVM level | CRaC checkpoints the process/JVM using a runtime engine; it does not write individual objects via ObjectOutputStream |
| Every object must implement Serializable to be saved by CRaC | CRaC does not require a per-class serialization contract |
| Java serialization saves the entire heap | It saves the object graph starting from a chosen root object and elements per serialization rules |
| Transient fields are absent from CRaC images | transient only affects default Java serialization; values remain in the heap checkpoint if still in memory |
| Static variables are written to the serialization stream | Static belongs to class state and is not written like default instance fields |
| Deserialization resumes running threads | Deserialization builds an object graph; it does not restore thread execution position |
| CRaC guarantees all sockets and database connections remain functional | External resources usually need to be closed, refreshed, or recreated |
| readObject is called after CRaC restore | Serialization hooks do not automatically run during the CRaC lifecycle |
| serialVersionUID determines checkpoint compatibility | It belongs only to Java serialization; checkpoint images depend on JDK/engine/OS/runtime |
| Checkpoint images can move freely between machines | Portability depends on engine and compatible environments |
| A serialization stream is always safe if classes implement Serializable | Deserializing untrusted data can lead to gadget/deserialization attacks |
| Checkpoint images contain only non-sensitive data | Heap/process state can contain credentials and user data |

## 13. Quick Decision Table

| Question | If yes | Appropriate direction |
|---|---|---|
| Only need to save an object or a small graph? | Yes | Serialization or schema-based data format |
| Need to preserve the state of many initialized beans/frameworks? | Yes | CRaC |
| Need to resume threads and process from the checkpoint? | Yes | CRaC |
| Need to exchange data with non-Java systems? | Yes | JSON/Avro/Protobuf are usually better suited than Java serialization |
| Need an application snapshot to reduce startup? | Yes | CRaC |
| Need to store data long-term across versions? | Yes | Format with clear schema and migration |
| Need to keep database connections alive across downtime? | Yes | Do not rely on serialization; with CRaC, design a Resource to reconnect |
| Need precise control over which fields are saved? | Yes | Serialization or schema-based data format |
| Need to restore full process/JVM state? | Yes | CRaC |

## 14. Design Workflow When Choosing Java Serialization

1. Select the root object and define the graph to save.
2. Evaluate all reference fields and classes in the graph.
3. Declare serialVersionUID and class evolution policies.
4. Mark state that should not be written as transient.
5. Write custom serialization hooks when alternative representations are needed.
6. Define how transient state is recreated after deserialization.
7. Add ObjectInputFilter and read streams only from trusted sources.
8. Test streams from older versions and class changes.
9. Verify invariants after the object graph is reconstructed.
10. Measure write/read time, stream size, and integration overhead.

## 15. Design Workflow When Choosing CRaC

1. Verify the JDK/runtime and checkpoint engine support CRaC.
2. Choose the checkpoint timing after reusable initialization steps complete.
3. Inventory all off-heap resources: sockets, pools, consumers, schedulers, files, native handles.
4. Register org.crac.Resource or use appropriate framework integrations.
5. Stop accepting new work, drain tasks, and close resources before checkpoint.
6. Create the checkpoint image and record runtime/image metadata.
7. Restore in a compatible environment.
8. Recreate connections, credentials, identities, and leases after restore.
9. Verify dependencies and readiness before receiving traffic.
10. Test restoring multiple times and across multiple replicas if the image is used for scale-out.
11. Protect the checkpoint image as data containing sensitive memory state.
12. Measure restore-to-ready, first-request latency, p50/p95/p99, and throughput.

## 16. Key Principles to Remember

- Java serialization saves a selected object graph; CRaC saves process/JVM state according to the checkpoint engine's capabilities.
- Serialization starts from a root object and follows references; it does not automatically write the entire heap.
- Serializable, transient, serialVersionUID, and serialization hooks belong to Java serialization.
- CRaC does not require classes to implement Serializable; transient and static fields remain JVM/heap state within the checkpoint scope.
- Serialization does not save thread execution state; CRaC can restore thread/process state depending on the engine.
- Do not assume CRaC preserves all sockets, database connections, or native resources; Resource callbacks and integrations are required.
- writeObject()/readObject() do not replace beforeCheckpoint()/afterRestore().
- Java serialization constructs a new object graph; CRaC resumes the process from the checkpointed state.
- Serialization streams depend on class compatibility; checkpoint images depend on the JDK, engine, and runtime environment.
- Do not deserialize untrusted data; use filters and schema-based formats when appropriate.
- Protect checkpoint images because heap/process state may contain secrets and user data.
- Choose based on the boundary to preserve: data/object graphs versus the entire initialized process.

Java serialization and CRaC are not two versions of the same technique. Serialization saves a selected subset of data following an object graph and class serialization contracts. CRaC saves the execution state of a Java process so it can resume after restore, while requiring the application to coordinate with external resources. Once the scope of state to preserve, compatibility, and resource lifecycles are clearly defined, choosing the right mechanism becomes simpler and less risky.
