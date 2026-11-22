# Simulating Exceptions in beforeCheckpoint() and afterRestore()

CRaC (Coordinated Restore at Checkpoint) invokes Resource callbacks so that the application can prepare resources before creating a checkpoint image and recover them after the process is restored. The two callbacks sit at two different boundaries:

- beforeCheckpoint() runs before the runtime creates a checkpoint. The application typically drains work, synchronizes data, and closes sockets, file handles, or connection pools.
- afterRestore() runs in the restored process. The application typically recreates connections, verifies dependencies, and restarts workers.

Callbacks can fail due to I/O errors, timeouts, expired credentials, unavailable dependencies, missing permissions, or programming bugs. If only the happy path is tested, the application can fall into a half-ready state without being detected.

The testing approach is to intentionally inject faults at identified points, verify resource state after the failure, and then test the corresponding recovery path. A failure in beforeCheckpoint() causes checkpoint preparation to fail; a failure in afterRestore() means the restored process cannot yet be considered ready. Both branches need to be tested separately.

## 1. Goals of Fault Injection

Fault injection is a technique of intentionally introducing a controlled error at a point in the execution flow.

In CRaC testing, it is possible to simulate:

- Resource cannot flush or close a file.
- Database pool cannot drain active connections.
- HTTP client cannot close a socket.
- Secret provider cannot issue a new token.
- DNS or remote service is not yet available.
- File or mount does not exist after restore.
- Resource is partially initialized and then throws an exception.
- Validation step fails after the connection has opened.
- One Resource succeeds, but the next Resource fails.

A useful test needs to verify:

1. The error is propagated to the right calling layer.
2. The application does not continue in a half-ready state.
3. Modified resources are identified accurately.
4. Resources can be recovered or marked as unrecoverable.
5. Requests, workers, and schedulers do not run when dependencies are not ready.
6. Logs preserve the cause and exception chain without leaking secrets.
7. The next checkpoint attempt is not affected by leftover state.

## 2. Identifying Failure Points in Each Callback

Before writing tests, break the callback down into small steps and identify side effect boundaries.

A beforeCheckpoint() that manages a pool might consist of:

~~~text
Stop accepting new requests
        |
        v
Wait for in-flight requests and transactions
        |
        v
Flush necessary data
        |
        v
Close connection pool
        |
        v
Mark resource as closed
~~~

Faults can be injected when stopping new requests, while waiting for transactions, after flushing, or after the pool has closed.

An afterRestore() might consist of:

~~~text
Read current configuration and credentials
        |
        v
Create new connection pool
        |
        v
Verify database
        |
        v
Start worker
        |
        v
Open request gate
~~~

Faults can be injected before opening the pool, right after opening the pool, when validation fails, or before opening the request gate.

Distinguishing failures before and after side effects is very important:

| Failure location | Possible remaining state |
|---|---|
| Before drain | Resource may still operate normally |
| After drain | Request gate is closed, workers may have stopped |
| After closing resource | Original process needs to reopen it if the checkpoint is aborted |
| While creating resource | Partially created sockets or threads may remain |
| After creating resource | Handle exists but has not been verified |
| Before opening gate | Dependency may be ready, but the application is not yet accepting traffic |

CRaC does not automatically roll back side effects that the application performed before a callback threw an exception. If three resources have closed and then the fourth resource fails, the application needs to know the state of all three resources and how to recover them.

## 3. Creating a Deterministic, One-Shot FaultInjector

Test conditions should not be scattered throughout production code, nor should random errors be used. Create a small abstraction to inject faults at the exact points.

~~~java
public enum FaultPoint {
    BEFORE_CHECKPOINT_AFTER_DRAIN,
    BEFORE_CHECKPOINT_AFTER_CLOSE,
    AFTER_RESTORE_BEFORE_OPEN,
    AFTER_RESTORE_AFTER_OPEN,
    AFTER_RESTORE_BEFORE_READY
}
~~~

A simple implementation using AtomicReference:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class FaultInjector {
    private final AtomicReference<FaultPoint> armed =
        new AtomicReference<>();

    public void arm(FaultPoint point) {
        armed.set(point);
    }

    public void hit(FaultPoint point) throws InjectedFailure {
        if (armed.compareAndSet(point, null)) {
            throw new InjectedFailure(
                "Injected failure at " + point
            );
        }
    }
}
~~~

A dedicated exception helps tests distinguish simulated errors from real errors:

~~~java
public final class InjectedFailure extends Exception {
    public InjectedFailure(String message) {
        super(message);
    }
}
~~~

Each test triggers only one FaultPoint. The fault is consumed once so that recovery does not accidentally rethrow the same error. Production can use a no-op implementation.

Do not enable fault injection via a public endpoint. If controlled by configuration, allow it only in a test profile and verify that the profile cannot be deployed to production.

## 4. Simulating Failures in beforeCheckpoint()

Example Resource managing a handle and a request gate. The interfaces are application abstractions:

~~~java
public interface RequestGate {
    void stopAndDrain() throws Exception;
    void resume();
    void keepClosed();
}

public interface ManagedHandle {
    void validate() throws Exception;
    void close() throws Exception;
}

public interface HandleFactory {
    ManagedHandle open() throws Exception;
}
~~~

Illustrative Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TestableFileResource implements Resource {
    enum State {
        READY, PREPARING, CLOSED, RESTORING, FAILED
    }

    private final RequestGate gate;
    private final HandleFactory factory;
    private final FaultInjector faults;

    private ManagedHandle handle;
    private volatile State state = State.READY;

    public TestableFileResource(
            RequestGate gate,
            HandleFactory factory,
            FaultInjector faults) throws Exception {
        this.gate = gate;
        this.factory = factory;
        this.faults = faults;
        this.handle = factory.open();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        prepareForCheckpoint();
    }

    synchronized void prepareForCheckpoint() throws Exception {
        state = State.PREPARING;
        gate.stopAndDrain();

        faults.hit(FaultPoint.BEFORE_CHECKPOINT_AFTER_DRAIN);

        if (handle != null) {
            handle.close();
            handle = null;
        }

        state = State.CLOSED;
        faults.hit(FaultPoint.BEFORE_CHECKPOINT_AFTER_CLOSE);
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        restoreResources();
    }

    synchronized void restoreResources() throws Exception {
        state = State.RESTORING;
        ManagedHandle opened = null;

        try {
            faults.hit(FaultPoint.AFTER_RESTORE_BEFORE_OPEN);

            opened = factory.open();
            faults.hit(FaultPoint.AFTER_RESTORE_AFTER_OPEN);

            opened.validate();
            faults.hit(FaultPoint.AFTER_RESTORE_BEFORE_READY);

            handle = opened;
            opened = null;
            state = State.READY;
            gate.resume();

        } catch (Exception failure) {
            state = State.FAILED;
            gate.keepClosed();

            if (opened != null) {
                try {
                    opened.close();
                } catch (Exception closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
            }

            throw failure;
        }
    }

    synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (handle == null) {
            handle = factory.open();
        }

        handle.validate();
        state = State.READY;
        gate.resume();
    }

    State state() {
        return state;
    }
}
~~~

This is an illustrative skeleton. A real implementation needs to handle cleanup if factory.open() partially creates a resource and then throws an exception, and needs to determine whether close() is safe when called multiple times.

If the failure occurs at BEFORE_CHECKPOINT_AFTER_DRAIN, the handle is still open, but the request gate is closed. If the failure occurs at BEFORE_CHECKPOINT_AFTER_CLOSE, the handle is closed, and the original process needs to recreate the handle if the checkpoint is aborted. Both scenarios require separate tests.

## 5. Verifying an Aborted Checkpoint After a beforeCheckpoint() Failure

When beforeCheckpoint() throws an exception, checkpoint preparation fails. If the application proactively calls Core.checkpointRestore(), the CRaC API reports the checkpoint error via CheckpointException.

The recovery branch needs to return the original process to a runnable state:

~~~java
try {
    Core.checkpointRestore();

    // When restore succeeds, afterRestore() has already run.
    application.markRestoredAndReady();

} catch (CheckpointException checkpointFailure) {
    try {
        fileResource.recoverAfterAbortedCheckpoint();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        application.markNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    application.markNotReady();
    throw restoreFailure;
}
~~~

The example assumes fileResource is the resource whose state was closed or modified. A real application may need to recover multiple resources and open the request gate only after all have recovered successfully.

Do not assume afterRestore() runs as a rollback callback when a checkpoint is aborted. afterRestore() serves the process that is actually restored.

### If Checkpoint Is Requested via jcmd

~~~bash
jcmd <pid> JDK.checkpoint
~~~

When the command is sent from an external terminal, the API calling thread inside the application does not have a try/catch block wrapping that call. You cannot rely on catching CheckpointException in the coordinator to automatically recover the original process.

If immediate rollback inside the application is a mandatory requirement, coordinate checkpoints via the in-application API or provide an independent recovery mechanism. With jcmd, test command output, runtime logs, and process state using an external harness.

## 6. Simulating Failures in afterRestore()

afterRestore() runs in the restored process. Some resources may have been reopened, while other dependencies are still not ready.

Failure points have different meanings:

- AFTER_RESTORE_BEFORE_OPEN: new handle has not been created yet.
- AFTER_RESTORE_AFTER_OPEN: handle exists but has not been verified.
- AFTER_RESTORE_BEFORE_READY: handle is verified, but the application is not yet allowed to accept work.

If the callback throws an exception, do not open the request gate or mark the application ready. Keep the FAILED/RESTORING state and propagate the exception outward according to the API contract.

### Cleanup on Partial Restore Failure

The restoreResources() method in the previous section's example keeps the new handle in a local variable until validation completes. If fault injection or validation throws an exception, it closes the new handle, keeps the gate closed, and attaches any cleanup error to the original exception using addSuppressed(). As a result, the handle field does not point to a partially created new resource.

The gate must be kept closed throughout the restore bootstrap process. Do not swallow exceptions and return normally if a dependency cannot operate yet.

## 7. Distinguishing CheckpointException and RestoreException

When calling the CRaC coordination API directly, distinguish between the two branches:

| Exception | Timing | What to verify |
|---|---|---|
| CheckpointException | Checkpoint process did not complete | Recover the original process after a preparation failure |
| RestoreException | Restore process encountered an error | The restored instance does not open traffic when a callback fails |

Tests for beforeCheckpoint() must verify the checkpoint failure branch. Tests for afterRestore() must verify the restore failure branch. Do not merge both into a single generic catch Exception, as it obscures the error type and the recovery path that needs to run.

The exception chain and diagnostic details may depend on the JDK/CRaC version and how the checkpoint was triggered. In integration tests, record causes and suppressed exceptions rather than relying on a fixed message text.

## 8. Unit Tests for Each Failure Point

Unit tests invoke callback logic directly without creating a checkpoint image. Processing logic can be extracted into package-private methods such as prepareForCheckpoint() and restoreResources() for testing.

JUnit 5 example testing a failure after the handle closes:

~~~java
@Test
void checkpointFailureAfterCloseCanBeRecovered() throws Exception {
    FaultInjector faults = new FaultInjector();
    FakeGate gate = new FakeGate();
    FakeHandleFactory factory = new FakeHandleFactory();

    TestableFileResource resource =
        new TestableFileResource(gate, factory, faults);

    faults.arm(FaultPoint.BEFORE_CHECKPOINT_AFTER_CLOSE);

    assertThrows(
        InjectedFailure.class,
        resource::prepareForCheckpoint
    );

    assertEquals(
        TestableFileResource.State.CLOSED,
        resource.state()
    );
    assertTrue(gate.isClosed());
    assertEquals(1, factory.openCount());
    assertEquals(1, factory.closeCount());

    resource.recoverAfterAbortedCheckpoint();

    assertEquals(
        TestableFileResource.State.READY,
        resource.state()
    );
    assertFalse(gate.isClosed());
    assertEquals(2, factory.openCount());
}
~~~

Example testing a failure after opening a new handle but before readiness is enabled:

~~~java
@Test
void restoreFailureAfterOpenKeepsApplicationClosed() throws Exception {
    FaultInjector faults = new FaultInjector();
    FakeGate gate = new FakeGate();
    FakeHandleFactory factory = new FakeHandleFactory();

    TestableFileResource resource =
        new TestableFileResource(gate, factory, faults);

    resource.prepareForCheckpoint();
    faults.arm(FaultPoint.AFTER_RESTORE_AFTER_OPEN);

    assertThrows(
        InjectedFailure.class,
        resource::restoreResources
    );

    assertTrue(gate.isClosed());
    assertEquals(
        TestableFileResource.State.FAILED,
        resource.state()
    );
    assertEquals(2, factory.closeCount());
}
~~~

The second example assumes restoreResources() performs partial handle cleanup like the sample in the previous section. The test needs to verify that the newly opened handle was closed when the failure occurred.

Important assertions:

- The right exception type is thrown.
- State matches the failure point.
- Request gate remains closed if restore has not completed.
- Handle is opened and closed the exact expected number of times.
- Workers or schedulers do not run unexpectedly.
- Cleanup failure is attached to the original exception via addSuppressed().
- Successful recovery transitions the resource back to READY.
- Failed recovery keeps the resource in FAILED and the gate closed.

Do not check only assertThrows. The state after the exception is the important part.

## 9. Fault Injection Matrix

| Callback | Failure point | Expected outcome to verify |
|---|---|---|
| beforeCheckpoint | Before drain | Resource is not closed |
| beforeCheckpoint | After drain | Gate is recovered if checkpoint is aborted |
| beforeCheckpoint | After closing handle | Handle is reopened in the original process |
| beforeCheckpoint | When closing the second resource | Previously closed resource is recovered |
| afterRestore | Before opening handle | Gate is closed, application is not ready |
| afterRestore | After opening handle | Partial handle is cleaned up |
| afterRestore | Validation fails | Workers and listeners have not started |
| afterRestore | Before opening gate | Traffic remains blocked |
| recovery | Reopening resource fails | Recovery error is preserved, instance is not ready |
| cleanup | Closing partial resource fails | Cleanup error is suppressed and recorded |

With multiple Resources, add a test where one Resource prepares successfully but the next Resource fails. Verify that every resource whose state changed can be recovered or placed into a safe state.

## 10. Testing Multiple Resources and Dependencies

Applications typically have listeners, workers, JDBC pools, HTTP clients, and file channels:

~~~text
Request Listener
       |
       v
Background Worker
       |
       +------> JDBC Pool
       |
       +------> HTTP Client
       |
       +------> File Channel
~~~

Before checkpoint, listeners and workers need to stop before the dependencies they use. After restore, dependencies must be reopened before workers and listeners run.

Do not rely implicitly on Resource registration order if correctness depends on ordering. Use a coordinator with an explicit sequence or a supported CRaC integration.

Tests can record an event log:

~~~java
List<String> events = new CopyOnWriteArrayList<>();

events.add("gate.stop");
events.add("worker.stop");
events.add("jdbc.close");
events.add("http.close");
~~~

After the callback or coordinator runs, compare the event log against the order required by the design. When a callback fails, verify that rollback steps are invoked in accordance with dependencies.

## 11. Integration Tests with Real Checkpoints

Unit tests that only invoke callback methods directly do not test the entire runtime. Integration tests running in a separate JVM with a CRaC JDK and a real checkpoint/restore environment are needed.

A harness can:

1. Launch the test application in a separate process.
2. Register the test Resource.
3. Write state and callback milestones to a result file.
4. Enable a specific FaultPoint.
5. Call Core.checkpointRestore() or trigger via runtime tooling.
6. Collect exit code, stdout/stderr, and process status.
7. Inspect which callbacks ran, what exceptions occurred, and what state the resource is in.

Do not run checkpoint integration tests in the same JVM as the regular test suite. Restore can alter execution threads and process state in ways incompatible with the test runner.

### Testing via Core.checkpointRestore()

~~~java
try {
    Core.checkpointRestore();
    writeMarker("RESTORE_RETURNED");
} catch (CheckpointException failure) {
    writeMarker("CHECKPOINT_FAILED");
    recoverOriginalProcess();
} catch (RestoreException failure) {
    writeMarker("RESTORE_FAILED");
    keepApplicationNotReady();
}
~~~

Markers should be written to a durable result file or an independent test channel. Do not rely solely on log buffers in the heap, because buffers may not be flushed when the process encounters an error.

### Testing with jcmd

~~~bash
jcmd <pid> JDK.checkpoint
~~~

An external harness monitors the command result, runtime logs, and process. Because the command is executed outside the JVM, the application has no catch block in an API calling thread to handle that command's exception itself.

In test reports, clearly state whether Core.checkpointRestore() or jcmd is being used. The two trigger methods have different observation and recovery paths.

## 12. Simulating External Dependency Failures

Some failures should be produced using test doubles or test services to verify actual library behavior:

- Database refuses connections.
- HTTP endpoint returns an error or times out.
- DNS fails to resolve.
- Secret manager returns an authentication error.
- File path does not exist or is read-only.
- Mount volume is not ready.
- TLS certificate is invalid.
- Native client fails to initialize.

For network errors, use a controllable mock server or test service. For file errors, use a dedicated test directory with intentionally configured permissions. Do not modify permissions or delete data on a production filesystem to induce failures.

Tests need to verify timeouts, bounded retries, backoff, and readiness behavior. Do not allow callbacks to retry indefinitely, as it can hang restore or prolong startup time.

## 13. Inspecting Exception Chains and Logs

Logs should retain:

- Resource and callback names.
- Operation being executed.
- FaultPoint or state before failure.
- Exception type and cause.
- Execution duration.
- Cleanup result.
- Non-sensitive instance ID or checkpoint generation.

Structured log example:

~~~text
event=crac_callback_failure
resource=fileResource
callback=beforeCheckpoint
operation=close_handle
state=CLOSED
exception=IOException
checkpointGeneration=test-42
~~~

Do not log tokens, passwords, private keys, request bodies, or sensitive file contents. If an exception message contains credentials or connection strings, redact them before logging.

If cleanup fails while handling the primary error, use addSuppressed() to preserve both errors:

~~~java
try {
    handle.close();
} catch (Exception closeFailure) {
    originalFailure.addSuppressed(closeFailure);
}

throw originalFailure;
~~~

The original error indicates where the callback failed; the suppressed exception indicates that cleanup also encountered an issue.

## 14. Keeping Fault Injection Out of Production

Fault injection needs a clear scope:

- Provide the FaultInjector implementation only in test sources or a test profile.
- Production uses a no-op implementation by default.
- Do not expose a public endpoint to trigger faults.
- If enabled via configuration, allow it only in an isolated test environment.
- Log whenever fault injection is triggered.
- Set timeouts for integration tests.
- Clean up processes, checkpoint images, temporary files, and test volumes after tests.
- Do not use production secrets or production checkpoint images as fixtures.

An interface can be used:

~~~java
public interface Faults {
    void hit(FaultPoint point) throws Exception;
}

public final class NoOpFaults implements Faults {
    @Override
    public void hit(FaultPoint point) {
        // Do not trigger failure in production.
    }
}
~~~

Tests replace NoOpFaults with FaultInjector. Separating the interface keeps production code free from dependencies on fault-control environment variables or endpoints.

## 15. Common Mistakes in Test Suites

**Checking only the exception:** the test passes, but the file channel remains closed or workers keep running. Check state, open/close counts, and readiness.

**Using random errors:** tests become hard to reproduce. Use a specific, one-shot FaultPoint.

**Using the same process for multiple restores:** restore can alter execution threads. Use a separate JVM for each integration scenario.

**Relying on unguaranteed callback order:** if ordering is required, coordinate in a coordinator or supported integration.

**Infinite retries in afterRestore():** an unavailable dependency can prevent the callback from finishing. Use timeouts and bounded backoff.

**Swallowing exceptions:** the runtime may continue while resources are not yet safe. Only catch to perform cleanup or add context, then propagate the error outward if the callback cannot complete.

## 16. Recommended Testing Workflow

### Preparation

1. Create a Resource with observable state.
2. Extract resource open/close operations from callbacks for unit testing.
3. Add FaultPoints at critical side effect boundaries.
4. Create a fake gate, fake handle factory, and event recorder.
5. Prepare a separate JVM and directory for integration tests.

### Testing beforeCheckpoint()

1. Trigger a fault before drain.
2. Trigger a fault after drain.
3. Trigger a fault after closing the handle.
4. Trigger a fault when closing the second resource in a group.
5. Verify that the checkpoint is reported as failed.
6. With Core.checkpointRestore(), run recovery in the original process.
7. Verify that the resource is reopened and readiness is enabled only after recovery succeeds.

### Testing afterRestore()

1. Create a checkpoint successfully in the test environment.
2. Restore with a fault before opening the resource.
3. Restore with a fault after partially opening the resource.
4. Restore with a fault during validation.
5. Restore with a fault right before opening the request gate.
6. Verify that the exception is reported through the correct failure path.
7. Verify that the request gate is closed and workers do not run when restore has not completed.

### Testing Recovery and Repeatability

1. Make recovery succeed after a checkpoint failure.
2. Make recovery fail and verify that the application remains not-ready.
3. Run checkpoint again after successful recovery.
4. Run multiple iterations to detect leaked handles or non-idempotent callbacks.
5. Inspect logs, metrics, and artifact cleanup.

## 17. Principles to Remember

- beforeCheckpoint() and afterRestore() are two failure points with different consequences.
- Fault injection should be deterministic with FaultPoint, single-use (one-shot), and reproducible.
- Test failures both before and after side effects.
- CRaC does not automatically roll back resources that the application closed or modified before a callback failed.
- A beforeCheckpoint() failure causes checkpoint preparation to fail; the original process needs to recover modified resources.
- An afterRestore() failure must keep the application in a not-ready state.
- afterRestore() is not a rollback callback when a checkpoint is aborted.
- Distinguish CheckpointException and RestoreException when coordinating with Core.checkpointRestore().
- For external jcmd, test through a harness; the application thread does not catch that command's exception.
- Unit tests verify callback logic; integration tests in a separate JVM verify the real runtime.
- Verify state, side effects, readiness, cleanup, and exception chains, not just assertThrows.
- Do not swallow exceptions if resources cannot yet be returned to a safe state.
- Do not enable fault injection in production or use production data to test failures.
- Set timeouts and retry limits so callbacks do not hang indefinitely.

Intentional exception simulation helps test states that normal execution paths do not expose: a partially closed resource, a partially created new client, or a dependency not yet ready after restore. When each failure point has an expected state, a clear rollback path, and integration tests running on the real runtime, the application can fail in a controlled manner instead of continuing to accept work in an inconsistent state.
