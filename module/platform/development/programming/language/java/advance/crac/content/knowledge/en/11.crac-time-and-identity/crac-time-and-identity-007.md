# UUIDs and counters generated before checkpoint when spawning multiple replicas

CRaC (Coordinated Restore at Checkpoint) makes it possible to create a state image of a Java process and then launch multiple processes from that same image. When multiple replicas are restored from a single checkpoint image, each replica starts with the identical heap state at the time of checkpoint.

This directly affects UUIDs, counters, and identifier generators. A UUID already generated before checkpoint will have the same value in every replica. An AtomicLong or in-memory counter also starts from the same value across all replicas. If each replica continues incrementing the counter or generating IDs from the same internal state, they can produce duplicate identifiers.

To generate unique IDs after cloning, the application must distinguish shared state inherited from the image from per-instance identity. Identifiers that need to distinguish replicas must be allocated or reinitialized after restore using a source that is unique across instances.

## 1. Why does cloning a checkpoint duplicate identifier state?

Suppose the application creates a checkpoint with the state:

~~~text
instanceId = 7f...
requestId  = a2...
counter    = 5000
workerId   = 12
randomState = S
~~~

From the same image, the system restores three processes:

~~~text
                 Checkpoint image
                counter = 5000
                workerId = 12
                randomState = S
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Copy A        Copy B        Copy C
       count=5000    count=5000    count=5000
       worker=12     worker=12     worker=12
       state=S       state=S       state=S
~~~

Each process has its own memory space after restore, but the initial values are copied from the same image. AtomicLong guarantees atomic updates across threads within one process; it does not coordinate with AtomicLong in other processes.

If all three replicas call incrementAndGet(), each replica can receive the same value 5001. If that value is used as a global key, the three replicas can overwrite or collide on data.

It is necessary to distinguish:

- **Logical application ID:** identifies the same application or the same service; can be identical across replicas.
- **Instance ID:** unique identifier for each restored process; must differ across replicas.
- **Request/job/event ID:** identifies a specific operation; needs to be unique within the scope required by the system.
- **Counter/sequence:** monotonically increasing sequence number; the scope of uniqueness can be one instance, one worker, one database, or the entire system.

Not every identical value across replicas is a bug. A bug occurs when a value is used with the expectation of uniqueness in a broader scope than the scope it actually guarantees.

## 2. UUIDs generated before checkpoint remain identical

A UUID is a 128-bit value. Java represents it with java.util.UUID.

~~~java
UUID id = UUID.randomUUID();
~~~

UUID.randomUUID() creates a version 4 UUID, using a random number source to generate the UUID's bits. With a proper random source, the probability of collision between newly generated UUIDs is very small.

However, a UUID is a data value. If the application generates a UUID before checkpoint and keeps it in a field, every replica restored from the image will receive that same value:

~~~java
public final class ApplicationState {
    // This value is generated once before checkpoint.
    private final UUID instanceId = UUID.randomUUID();
}
~~~

If three processes restore an image containing instanceId, all three see the exact same UUID. No random algorithm runs again just because the object was restored; the field holds an already finalized UUID value.

If the UUID represents a logical application ID, keeping it may be correct. If it is used as an instance ID, a new UUID must be assigned for each replica after restore.

### Generating an instance ID after restore

A Resource can be registered to update the instance-specific identifier after the process is restored:

~~~java
import java.util.UUID;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class InstanceIdentity implements Resource {
    private volatile UUID instanceId;

    public InstanceIdentity() {
        this.instanceId = UUID.randomUUID();
        Core.getGlobalContext().register(this);
    }

    public UUID instanceId() {
        return instanceId;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // No need to change the logical application ID here.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        instanceId = UUID.randomUUID();
    }
}
~~~

The example illustrates where to update the ID. In actual deployment, confirm that the SecureRandom source used by the runtime and provider has independent state after restore. If the runtime has a CRaC reseed mechanism for SecureRandom, use the proper supported configuration and version. If there is no such guarantee, use a generator reseeded from independent entropy or allocate IDs from an external service.

Assigning the new UUID in afterRestore() also needs to occur before request listeners, workers, or schedulers start generating IDs. If other components use instanceId in their restore callbacks, coordinate the initialization order so that the new ID is ready beforehand.

## 3. Random number generator state can be copied

It is not only pre-stored UUIDs that risk duplication. Random number generators also have internal state.

A PRNG (Pseudo-Random Number Generator) typically produces the next sequence of values from its current state. If that state is copied verbatim to multiple processes, the processes can produce the exact same sequence of values:

~~~text
Generator A: state S -> x1 -> x2 -> x3 -> x4
Generator B: state S -> x1 -> x2 -> x3 -> x4
Generator C: state S -> x1 -> x2 -> x3 -> x4
~~~

This does not mean every SecureRandom implementation is guaranteed to repeat sequences after CRaC. Behavior depends on the provider, entropy source, JDK version, and checkpoint/restore integration mechanism. Some runtimes or providers may handle reseeding on restore. Check the documentation of the running JDK and provider.

The important point is not to deduce that simply creating a new SecureRandom object after restore guarantees independent state. If the provider initializes from copied state or a copied entropy source, creating a new object is not enough.

### UUID.randomUUID() and SecureRandom

UUID.randomUUID() is a convenient API, but the application does not pass a custom SecureRandom into this method. Therefore, the application does not directly control when the internal generator used by UUID is reseeded.

If explicit control over UUID generation after restore is required, manage a dedicated SecureRandom, use a provider supporting reseed, and check for errors if fresh entropy cannot be obtained.

Example of generating a v4 UUID from a managed generator:

~~~java
import java.nio.ByteBuffer;
import java.util.UUID;
import java.security.SecureRandom;

public final class UuidGenerator {
    private final SecureRandom random;

    public UuidGenerator(SecureRandom random) {
        this.random = random;
    }

    public synchronized UUID nextUuid() {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);

        // Set version 4.
        bytes[6] = (byte) ((bytes[6] & 0x0f) | 0x40);

        // Set RFC 4122 variant.
        bytes[8] = (byte) ((bytes[8] & 0x3f) | 0x80);

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
~~~

The code snippet generates a v4 UUID from 122 random bits. It does not by itself solve the post-restore entropy issue; it is the responsibility of SecureRandom management to provide a generator with independent state across replicas.

### Reseeding after restore

With JDKs supporting SecureRandom.reseed() and providers capable of reseeding, the provider can be requested to obtain fresh entropy:

~~~java
SecureRandom random = SecureRandom.getInstanceStrong();
random.reseed();
~~~

Points to note:

- getInstanceStrong() selects an algorithm/provider according to the JDK's security configuration; it can be slow or block waiting for entropy depending on the environment.
- reseed() requires provider support. If the provider does not support it, the application must handle UnsupportedOperationException or the corresponding error.
- setSeed(System.currentTimeMillis()) is not a safe way to reseed. The time can be identical across replicas and does not provide sufficiently strong cryptographic entropy.
- setSeed() supplements seed data per the SecureRandom contract; a predictable seed should not be considered a way to guarantee independence between processes.
- Reseeding must complete before the generator is used to issue IDs.

If independent entropy cannot be confirmed, do not issue IDs based on that generator. Keep the application in an unready state or use an external ID-allocation service.

## 4. AtomicLong and in-memory counters are also cloned

Example:

~~~java
public final class LocalSequence {
    private final AtomicLong counter = new AtomicLong(0);

    public long next() {
        return counter.incrementAndGet();
    }
}
~~~

If the checkpoint is created when counter is 100, every restored replica starts from 100. The replicas can simultaneously issue:

| Instance | Counter value after restore | Next ID |
|---|---:|---:|
| A | 100 | 101 |
| B | 100 | 101 |
| C | 100 | 101 |

AtomicLong only resolves contention between threads within the same process. It does not provide a distributed lock, does not communicate with other replicas, and does not know how many times an image has been restored.

Similarly, the following mechanisms are all only process-scoped without external coordination:

- synchronized.
- ReentrantLock.
- AtomicInteger and AtomicLong.
- LongAdder.
- Static variables.
- Counters in a singleton or bean.
- Per-thread or ThreadLocal counters.

These values can be copied along with the checkpoint image. Do not use them alone as a global sequence when one image can spawn multiple instances.

## 5. Strategies for generating unique IDs after restore

There is no single ID allocation method suitable for every system. Choose based on uniqueness scope, ordering requirements, and availability of external services.

| Strategy | How it works | Suitable for |
|---|---|---|
| UUID v4 with independent entropy | Generate new UUIDs after restore using a random source that has been reseeded/guaranteed independent | Distributed IDs, ordering not required |
| Database sequence | Database issues unique monotonically increasing numbers | System-wide numeric IDs |
| Block/range allocation | Coordinator allocates non-overlapping number ranges for each instance | High-volume IDs, reducing service calls |
| Instance ID + local counter | Allocate a distinct instance ID after restore and combine with a local counter | Per-instance unique IDs |
| Worker ID + timestamp + sequence | Snowflake-style generator with uniquely allocated worker ID | Time-ordered numeric IDs |
| Centralized ID service | Each request or batch obtains IDs from an allocation service | Systems needing centralized policy |

### New UUID after restore

Use UUID v4 when IDs with extremely low collision probability are needed and time-based ordering is not required. Ensure the generator uses independent entropy after restore.

### Database sequence

A database sequence can issue unique numbers for multiple instances sharing one database:

~~~sql
CREATE SEQUENCE event_id_seq START WITH 1 INCREMENT BY 1;
~~~

Each instance obtains an ID with:

~~~sql
SELECT nextval('event_id_seq');
~~~

Function names and syntax depend on the database; the example above uses PostgreSQL. Sequences typically do not roll back with transactions, so gaps may appear when a transaction fails. Gaps do not affect uniqueness.

The advantage is that multiple replicas share a single allocation source. The disadvantage is that the database must be available when issuing IDs and load can increase if every ID must query the database.

### Allocating ranges from a coordinator

To reduce the number of database calls, each instance can request a block of numbers:

~~~text
Copy A requests range:  100000 - 100999
Copy B requests range:  101000 - 101999
Copy C requests range:  102000 - 102999
~~~

Each replica increments a local counter within its range. The coordinator must allocate ranges via an atomic operation so that no two instances receive the same range.

Do not allocate a range before checkpoint and reuse it after restore. If the range is stored in the heap, every replica inherits the same range. Each replica must request a new range after restore or request a new lease/namespace.

### Instance ID combined with local counter

A simple approach is to allocate a unique instance ID after restore, then combine it with a local sequence:

~~~text
instanceId = 6f2b...
localCounter = 1, 2, 3, 4, ...

Generated ID:
6f2b...-1
6f2b...-2
6f2b...-3
~~~

Replicas have different instance IDs so they can use the same localCounter values without producing the same ID.

The condition is that the instance ID must truly be new and unique across replicas. If the instance ID was generated before checkpoint, this solution loses its effect.

## 6. Allocating a new instance identity from a coordinator

For systems requiring strong uniqueness, identity can be allocated from a database or coordination service after restore.

A simple abstraction:

~~~java
import java.util.UUID;

public interface InstanceIdentityAllocator {
    InstanceIdentity acquireNewIdentity() throws Exception;
}

public record InstanceIdentity(
    UUID instanceId,
    long fencingToken
) {}
~~~

On each allocation, the coordinator returns a new instance ID and a monotonically increasing fencing token. The fencing token helps external systems identify which instance holds the latest write authority.

A Resource can request a new identity in afterRestore():

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CloneAwareIdentity implements Resource {
    private final InstanceIdentityAllocator allocator;

    private volatile InstanceIdentity identity;
    private final AtomicLong localCounter = new AtomicLong();

    public CloneAwareIdentity(
            InstanceIdentityAllocator allocator) throws Exception {
        this.allocator = allocator;
        this.identity = allocator.acquireNewIdentity();
        Core.getGlobalContext().register(this);
    }

    public String nextId() {
        InstanceIdentity current = identity;

        if (current == null) {
            throw new IllegalStateException(
                "Instance identity is not ready"
            );
        }

        long sequence = localCounter.getAndIncrement();

        return current.instanceId() + "-" + sequence;
    }

    public long fencingToken() {
        InstanceIdentity current = identity;
        if (current == null) {
            throw new IllegalStateException("Identity is not ready");
        }

        return current.fencingToken();
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Do not clear identity here.
        // If the checkpoint is aborted, the original instance still needs the current identity.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        InstanceIdentity fresh = allocator.acquireNewIdentity();

        // Reset the sequence before publishing the new identity.
        localCounter.set(0);
        identity = fresh;
    }
}
~~~

The example assumes the allocator can issue a new identity that does not collide with any active replica. In practice, the allocator needs atomic operations at the database or coordinator and a policy for handling when that service is unavailable.

Acquiring a new identity in the constructor serves a normally launched instance. In afterRestore(), each replica receives its own identity. localCounter can restart from 0 because the instanceId namespace has changed.

### Why have a fencing token?

A lease can expire or an old instance can still be running due to a network partition. If the old instance continues writing after the new instance receives the lease, relying solely on the instance ID is not enough.

A fencing token is an incrementing generation number issued by the coordinator. The write-receiving system checks the token; older tokens are rejected. As a result, an instance with an old lease cannot overwrite data managed by an instance with a newer token.

Example:

~~~text
Checkpoint contains fencing token = 40

After restore:
Copy A receives token = 41
Copy B receives token = 42
Copy C receives token = 43

The storage only accepts the latest token according to lease/ownership.
~~~

Token enforcement needs to be supported by the write-receiving system. Simply incrementing a variable in the heap does not create fencing between processes.

## 7. Per-instance counters and range allocation

If each replica generates many IDs, calling the coordinator for every ID can be expensive. A new range can be requested after restore and then a local counter incremented within that range.

Example abstraction:

~~~java
public record IdRange(long firstInclusive, long lastInclusive) {}

public interface IdRangeAllocator {
    IdRange allocateRange(int size) throws Exception;
}
~~~

Resource holding the range:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RangeSequence implements Resource {
    private final IdRangeAllocator allocator;
    private final int blockSize;

    private long nextValue;
    private long rangeEndExclusive;

    public RangeSequence(
            IdRangeAllocator allocator,
            int blockSize) throws Exception {
        this.allocator = allocator;
        this.blockSize = blockSize;
        allocateNewRange();
        Core.getGlobalContext().register(this);
    }

    public synchronized long nextId() throws Exception {
        if (nextValue >= rangeEndExclusive) {
            allocateNewRange();
        }

        return nextValue++;
    }

    private synchronized void allocateNewRange() throws Exception {
        IdRange range = allocator.allocateRange(blockSize);
        nextValue = range.firstInclusive();
        rangeEndExclusive = Math.addExact(range.lastInclusive(), 1);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Do not rely on the currently held range to share across replicas.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Each replica requests a new range, instead of using the range in the image.
        allocateNewRange();
    }
}
~~~

This is a conceptual example; an actual implementation must handle numeric overflow, errors during range allocation, and publishing the new range. The nextId() method is synchronized to illustrate correctness; if high throughput is needed, it can be optimized with atomic reservation while still ensuring no two threads receive the same value and an exhausted range is not used.

Important rule: a range stored in the image is a cloned range. Do not reuse that range after restore. Request a new range from the shared allocation source.

## 8. Snowflake-style ID generators

Some systems use a structured 64-bit numeric ID consisting of:

- Timestamp relative to a custom epoch.
- Worker ID or node ID.
- Sequence incrementing within the same time interval.

An illustrative layout:

~~~text
| timestamp | workerId | sequence |
| 41 bits   | 10 bits  | 12 bits  |
~~~

Worker ID distinguishes nodes; sequence distinguishes IDs generated by the same node within the same time unit.

This approach can generate roughly time-ordered IDs without accessing the database for every ID. However, when restoring multiple replicas from the same checkpoint, both worker ID and sequence in the heap can be identical.

To use safely:

1. Each instance requests its own worker ID or lease after restore.
2. The coordinator ensures two active instances do not use the same worker ID within the same scope.
3. Sequence is reset according to generator rules after the new worker ID is allocated.
4. If the clock moves backward, the generator must wait, report an error, or use a fencing mechanism; do not continue generating potentially duplicate IDs.
5. If the sequence within the same millisecond overflows, the generator must wait until the next tick or report overload.
6. The worker ID lease must have a TTL, renewal, and fencing to handle old instances that have not stopped.

Do not use hostname or PID as a unique worker ID without an allocation rule. Hostnames can collide in containers, PIDs can be reused, and one checkpoint image can be restored multiple times on the same host.

## 9. Distinguishing retained identifiers from identifiers that must be regenerated

When designing checkpointed objects, classify each field:

| Data | Keep across restore? | Reason |
|---|---|---|
| Logical application ID | Usually yes | Replicas still belong to the same application |
| Tenant ID | Yes, if same tenant | Business data scope has not changed |
| ID of an existing record | Yes | Record identifier must not change |
| Instance ID | No, if replicas need to be distinguished | Each restored process is a separate instance |
| Worker ID/lease | Must be reallocated | Avoid two replicas sharing the same namespace |
| Global AtomicLong in heap | Cannot be used as a global sequence | Value is copied |
| Local counter attached to a new instance ID | Can be reset | The namespace has been renewed |
| UUID for an in-flight request | Depends on business logic | Need to avoid resending the same request as a new operation |
| PRNG state used to generate IDs | Must ensure independence | Avoid repeating sequences after cloning |

A final field does not automatically become unique. final only prevents reassigning the reference after initialization; it does not prevent the checkpoint image from copying the same value to multiple processes.

## 10. When to reallocate identity

The appropriate time is usually afterRestore(), after the necessary dependencies are ready and before the application opens traffic.

A possible sequence is:

~~~text
Restore process
       |
       v
Initialize configuration and dependencies
       |
       v
Connect coordinator / ID allocator
       |
       v
Allocate new instance ID, worker ID, or range
       |
       v
Initialize local counter
       |
       v
Start workers and schedulers
       |
       v
Open request listener
~~~

If the identity-allocating resource runs after a worker-starting resource, the worker can issue IDs from the old namespace. Coordinate callback ordering or use a startup gate so that workers do not run before the new identity is allocated.

### If the coordinator is unavailable

If identity must be unique system-wide and the coordinator cannot allocate identity, do not generate a worker ID from a timestamp or PID and assume it will not collide.

Options:

- Keep the instance in a not-ready state and retry with backoff.
- Use a UUID from independent entropy if system policy allows.
- Do not accept ID-generation work until the allocator is operational.
- Report errors clearly so the orchestration system can retry or transition the instance to an error state.

Uniqueness is a correctness condition. Continuing to run with an unknown namespace can cause data conflicts harder to repair than being temporarily unready.

## 11. Case where checkpoint is aborted

It is necessary to distinguish an aborted checkpoint from a successful restore.

- When checkpoint succeeds and the process is restored, afterRestore() runs on the new process. Each replica needs a separate identity allocated.
- When checkpoint is aborted, the original Java process continues. afterRestore() is not a rollback callback for this case.

If the application calls Core.checkpointRestore(), it can catch CheckpointException. However, not every identity needs to be replaced when checkpoint is aborted. If the original process is still the same instance and the old lease is still valid, it can continue using the current identity.

~~~java
try {
    Core.checkpointRestore();
    // Continue in the restored process.
} catch (CheckpointException checkpointFailure) {
    // The original process continues.
    // Keep the current identity/lease if still valid.
    recoverOriginalInstance(checkpointFailure);
    throw checkpointFailure;
} catch (RestoreException restoreFailure) {
    // Process restored, but restore notification failed.
    // Keep the instance in the not-ready state.
    markNotReady(restoreFailure);
    throw restoreFailure;
}
~~~

If beforeCheckpoint() already released the lease before checkpoint completed, when checkpoint is aborted the original process may lose ownership. In that case, the coordinator must reallocate a lease for the original instance in the CheckpointException branch. Another design is not to release the lease in beforeCheckpoint(), and instead only issue a new-generation lease in afterRestore(); the choice needs to match the lease and fencing policy of the system.

With an external jcmd command, application code does not have a try/catch block wrapping that call. Management procedures and resource lifecycles suitable for how checkpoint requests are operated are needed.

## 12. Testing when spawning multiple replicas

Do not test only a single restore. Create multiple processes from the same checkpoint image and verify that they do not generate duplicate IDs.

A test can perform:

1. Start the application with counters and UUID state initialized.
2. Create a checkpoint image.
3. Restore the image into multiple independent processes.
4. Each process allocates a new instance ID.
5. Each process generates a large number of IDs.
6. Write the IDs to a shared data store or test set.
7. Detect duplicates and confirm worker ID/lease is not shared.
8. Start additional instances after a lease expires or an old instance is stopped.
9. Check that the fencing token prevents an old instance from writing after losing ownership.

### Scenarios to test

| Scenario | What to confirm |
|---|---|
| One image restored twice | Two different instance IDs |
| Multiple cloned images started concurrently | Allocator issues non-overlapping identities/ranges |
| SecureRandom state checkpointed | Post-restore generator has independent entropy per runtime/provider |
| Counter checkpointed at value N | Replicas do not use N+1 as a shared global ID |
| Coordinator temporarily unavailable | Instance is not ready, does not issue IDs from the wrong namespace |
| Old instance lost lease but still running | Old fencing token is rejected |
| Range nearly exhausted | New block allocated atomically, no range used concurrently |
| Clock moves backward with Snowflake | Generator does not produce potentially duplicate IDs |

### Recording evidence

Logs or metrics should include:

- checkpoint generation or image ID.
- new instance ID after restore.
- worker ID and fencing token.
- timestamp of identity allocation.
- start/end range if using block allocation.
- count of failed ID allocations.
- count of detected conflicts.
- readiness status of the ID generator.

Do not log secrets, seeds, or internal state of SecureRandom. Only log metadata necessary for diagnostics.

## 13. Common design mistakes

**Using a UUID generated before checkpoint as the instance ID:** every replica holds the same UUID because it is a value already stored in the heap.

**Believing AtomicLong is globally unique:** AtomicLong is only atomic within a single process; replicas start from the same value.

**Creating a new SecureRandom and assuming it is definitely independent:** behavior depends on the provider and entropy source. Must verify the reseed mechanism after restore.

**Calling setSeed() with the current time:** time can be identical across replicas and does not replace cryptographic entropy.

**Allocating worker ID or range before checkpoint:** that value is copied along with the image. Each replica needs a namespace reallocated after restore.

**Using PID or hostname as worker ID:** they do not guarantee uniqueness when running multiple containers or restoring on the same machine.

**Starting workers before allocating a new identity:** workers can issue IDs from the old namespace before afterRestore() completes.

**Ignoring the fencing token:** an old instance can continue writing after the lease has been granted to a new instance.

**Not testing multiple replicas:** a single running process cannot expose collisions caused by the same image.

## 14. Recommended implementation workflow

### Before checkpoint

1. Classify which IDs are logical IDs and which IDs must be unique per instance.
2. Determine which counters are used only locally and which counters need system-wide uniqueness.
3. Ensure UUIDs/worker IDs/ranges created before checkpoint are not used as a per-replica namespace for all replicas.
4. Save business state that needs to be preserved, such as record IDs and last processed sequence.
5. Register the Resource responsible for reinitializing identity after restore.

### After restore

1. Initialize dependencies needed for the ID allocator.
2. Obtain fresh entropy or confirm the runtime/provider has reseeded the generator via a supported mechanism.
3. Allocate a new instance ID, worker ID, lease, or range from a shared source.
4. Reset local counters within the new namespace.
5. Publish the new identity before starting workers and schedulers.
6. Check the fencing token or ownership if the system uses leases.
7. Only open traffic when the ID generator is ready.

### When checkpoint is aborted

1. The original process continues with the current identity if the lease is still valid.
2. If the lease was released during the preparation phase, reallocate the lease to the original instance.
3. Do not call afterRestore() to handle rollback.
4. Keep the application not-ready if it cannot be confirmed that the current namespace is still valid.

## 15. Principles to remember

- A checkpoint image can be restored into multiple processes with the same initial heap state.
- UUIDs generated before checkpoint will have the same value in every replica.
- AtomicLong, synchronized, and in-memory counters only guarantee process scope.
- PRNG state can be copied; check the reseed behavior of the JDK, runtime, and provider.
- Do not treat new SecureRandom() or setSeed(currentTimeMillis) as a guarantee of independence across replicas.
- Allocate a new instance ID, worker ID, lease, or range after restore.
- Combine instance ID with a local counter to generate instance-specific IDs.
- Use a database sequence or coordinator when system-wide uniqueness is required.
- Do not reuse a range already present in the checkpoint image.
- Use a fencing token to prevent an old instance from writing after losing ownership.
- Allocate identity before opening workers, schedulers, and request listeners.
- Test restoring multiple replicas concurrently from the same image.

When spawning multiple replicas from one checkpoint image, every value in the heap needs to be reviewed according to the uniqueness scope required by the application. Keeping logical IDs and business data is reasonable; instance identity, worker namespaces, and counters used to issue global IDs need to be reallocated or partitioned after restore.