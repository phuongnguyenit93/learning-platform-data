# Restarting after a process is killed

In Spring Batch, restarting lets you resume a JobInstance that was started but not finished after the previous execution failed or stopped. When a JVM, container, or server is killed abruptly, Spring Batch usually does not get a chance to run Step/Job completion callbacks or update the final status in JobRepository. Consequently, business data and metadata may reflect different points in time: some chunks committed, the in-flight chunk may have rolled back, while the JobExecution or StepExecution may still show status `STARTED`.

Restarting after a process is killed requires addressing both issues: determining what work has committed and transitioning the old execution's metadata into a restartable state. Simply relaunching with the same JobParameters may not suffice because JobRepository may still consider the JobInstance running. Before restarting, you must verify the old process has truly stopped, inspect checkpoints and side effects, and use an appropriate administrative mechanism to resolve the orphaned execution.

## 1. A killed process differs from a controlled Job stop

Spring Batch supports requesting a running Job to stop via `JobOperator.stop(jobExecutionId)`. This is a controlled stop request. The framework gets a chance to observe the request and stop at a safe processing boundary, such as after the current chunk finishes its transaction.

A killed process is a different scenario:

- The JVM may be terminated by `kill -9`, `SIGKILL`, or the OS.
- A container may be terminated by the runtime after graceful shutdown times out.
- A VM or server may lose power or crash.
- The process may be terminated by the OOM killer.
- The application may be terminated before Spring Batch updates final metadata.

In these cases, `afterStep`, `afterJob`, `ItemStream.close()`, or application cleanup logic may not execute. Do not rely on shutdown hooks to guarantee that JobRepository is always updated to `FAILED` or `STOPPED`.

| Scenario | How it ends | Typical metadata |
|---|---|---|
| Job completes normally | Framework finishes Steps and Job | `COMPLETED` |
| Job receives stop request and handles it | Framework stops via controlled mechanism | `STOPPED` after stopping finishes |
| Exception handled and Step fails | Framework records error | Usually `FAILED` |
| JVM/process killed abruptly | No normal termination path | May remain `STARTED` or lack final status update |

An execution still showing `STARTED` after the process died is often called a stale or orphaned execution. Spring Batch cannot automatically conclude the process is dead from that metadata alone; an operational recovery step is required.

## 2. Why might JobExecution still be in STARTED status?

JobRepository stores JobExecution and StepExecution statuses in the metadata database. When a Job starts, the status is updated to `STARTED`. While running, the framework continues updating counters, ExecutionContext, and Step statuses.

If the process is killed before the framework writes the final status, metadata may still show:

```text
BATCH_JOB_EXECUTION.STATUS = STARTED
BATCH_STEP_EXECUTION.STATUS = STARTED
```

This does not prove the Job is still running. It only indicates metadata has not recorded the end of the execution. Conversely, do not assume an execution is stale solely because logs have been quiet for a while: a Step might be running a long query, waiting on an external service, or processing an expensive item.

Before changing status, verify the corresponding process/container/host has stopped and no old worker is still producing side effects. Marking it `FAILED` while the old process is still alive can cause a restart to run concurrently with the old execution and produce duplicate writes or data contention.

## 3. What happens to transactions when a process dies?

Chunk Steps typically process each chunk in a transaction. When a process dies, the outcome depends on timing and the transaction manager:

- Committed chunks: changes from committed transactions are preserved.
- In-flight uncommitted chunk: the database typically rolls back the transaction once it detects the closed connection/session.
- Process dies during commit: the client may not know for sure whether the commit succeeded; data and metadata must be checked.
- Non-transactional side effects: HTTP requests, emails, messages, or files may already have completed even if the database transaction rolled back.

```text
Chunk 1                 Chunk 2 running            Chunk 3
BEGIN                   BEGIN                      Not started yet
Read/Process/Write      Read/Process/Write
COMMIT                  Process killed
                        DB detects lost session
                        ROLLBACK (if uncommitted)

Chunk 1 preserved       Chunk 2 needs recovery     Chunk 3 not run yet
```

If the database committed chunk 2 but the process died before receiving the commit response or updating related metadata, the outcome can be ambiguous. Do not rely solely on the application's last log lines to decide whether a chunk committed.

How quickly the database detects a lost connection also depends on the database, driver, network, and timeout settings. During a host crash or network partition, rollback might not happen immediately. Verify old transactions/sessions have been released by the database before relaunching the same job.

## 4. Checkpoints determine where the Step resumes

For readers supporting `ItemStream`, Spring Batch uses `ExecutionContext` to save state such as read position, line count, or last key. Key callbacks:

- `open(ExecutionContext)`: restores saved state when the Step starts or restarts.
- `update(ExecutionContext)`: copies current state into context at chunk update points.
- `close()`: releases resources when the stream lifecycle ends normally.

In a chunk Step, streams update the context before the chunk transaction commits. When metadata and business data participate in the same appropriate transaction, the new checkpoint is confirmed together with the committed chunk. If the chunk rolls back, that chunk's checkpoint does not become a committed restart boundary.

For example, a file reader processed up to line 10,000 and that checkpoint committed. The process died while handling lines 10,001–10,200. On restart, the reader can restore from the last checkpoint and reprocess the uncommitted portion.

```text
Committed checkpoint: line 10,000
       |
       v
Read lines 10,001-10,200
       |
       v
Writer processes chunk
       |
       X Process killed before commit
       |
       v
Restart from committed checkpoint: 10,000
```

Readers must have stable state and support restarting. If a custom reader does not implement `ItemStream`, does not save state, or cannot restore source position, the Step may re-read from the beginning or fail to resume at the intended position.

## 5. Restarting preserves the JobInstance

Spring Batch distinguishes `JobInstance` from `JobExecution`:

- `JobInstance` represents a logical business run, identified by Job name and identifying JobParameters.
- `JobExecution` represents a specific execution attempt of a JobInstance.
- A JobInstance can have multiple JobExecutions when a previous run failed/stopped and was restarted.

For example, Job `dailyOrderImport` runs with identifying parameter `businessDate=2026-11-15`. If the execution is killed and then recovered, the restart must resume the same JobInstance with the same business identity.

Do not add a new timestamp or UUID to identifying parameters just to run again. That typically creates a new JobInstance, causing Spring Batch to treat it as a separate business run and potentially reprocess all data.

| Action | Result |
|---|---|
| Restart old execution with original JobInstance/identifying parameters | Resumes the old business run using saved metadata and checkpoints. |
| Launch same Job with same identifying parameters after old execution becomes eligible for restart | Creates a new JobExecution for the same JobInstance. |
| Add a new identifying parameter | Creates a new JobInstance. |
| Change a non-identifying parameter | Does not create a new JobInstance solely due to changing that parameter. |
| Launch a `COMPLETED` JobInstance | Typically rejected because the instance is already complete. |

If business rules genuinely call for creating a new import batch, use an identifying parameter reflecting the new batch identity, such as a new batch ID or business date. Do not use that approach to simulate a restart.

## 6. Why can't you immediately restart an execution still in STARTED?

When JobRepository still records a JobExecution as `STARTED`, Spring Batch may view the JobInstance as actively executing. Another launch with the same identifying parameters can be rejected with an error like `JobExecutionAlreadyRunningException`.

This is an essential safeguard preventing two processes from running the same JobInstance simultaneously. If the old process truly died without updating metadata, you must recover the stale execution's status before restarting.

`JobOperator.restart(executionId)` restarts an execution that ended in a restartable status, such as `FAILED` or `STOPPED`. It is not a kill-process command and should not be called to force-rerun a JobExecution that metadata still considers running.

The recovery procedure should:

1. Identify the exact stale JobExecution ID.
2. Verify the old process and all its workers have actually stopped.
3. Inspect JobExecution/StepExecution statuses and the last committed checkpoint.
4. Use the application-supported admin/recovery mechanism to terminate the stale execution in an appropriate status, typically `FAILED` when restarting is needed.
5. Once metadata is valid, restart the same JobInstance using the appropriate operational API.

Transitioning a stale execution's status is a sensitive administrative action. Do not automatically mark every execution `STARTED` longer than a threshold as `FAILED` without checking heartbeats, hosts, and workers. Avoid two processes owning the same execution.

## 7. Verify the old process is dead before recovering

Before altering metadata or restarting, verify the actual process state:

- On VMs or servers, confirm the PID/process no longer exists.
- In Kubernetes, confirm the old Pod is terminated and no old container/worker is still processing data.
- On other container platforms, confirm the task/container has completely stopped.
- If the Job uses remote partitioning, confirm worker processes and in-flight messages have been handled per recovery procedures.
- Check that old database sessions/transactions have been released or timed out.
- Ensure schedulers or orchestrators are not launching another execution with the same identity.

A newly created Pod does not automatically prove the old Pod stopped completely. During rolling restarts or node partitions, two processes might both believe they own a batch. Appropriate locking/leasing or fencing mechanisms are needed when running multiple instances.

## 8. JobOperator.stop does not replace recovery after a kill

`JobOperator.stop(jobExecutionId)` sends a stop request to a running Job. The framework can observe this request and stop at a safe point. When the process has already been killed, no worker remains to receive the request and update final metadata.

Calling `stop` on a stale `STARTED` execution may transition its status to `STOPPING`, yet no old process exists to complete the stop. Therefore, do not use `stop` as a metadata cleanup command for dead processes.

Distinguish the administrative operations:

| API/concept | Purpose | When to use |
|---|---|---|
| `JobOperator.stop(executionId)` | Request a running process to stop gracefully | When the execution is still active and able to receive requests. |
| `JobOperator.restart(executionId)` | Restart an ended execution eligible for restart | After the old execution is in a restartable status. |
| `JobOperator.abandon(executionId)` | Mark an ended execution as not to be restarted | When deciding to permanently abandon the old execution per policy. |
| Stale execution recovery | Fix status of an orphaned execution after process death | After verifying no old process remains and using a safe admin procedure. |

`ABANDONED` means the execution is discarded, not an intermediate status for restarting. If the goal is to resume work, do not mark the execution `ABANDONED`.

## 9. Controlled recovery of stale metadata

Spring Batch cannot determine for certain that a process died solely from a `STARTED` record. Depending on the version, infrastructure, and operations, the application needs an admin tool or recovery procedure to update the statuses of orphaned JobExecutions and StepExecutions.

That procedure should follow these principles:

- Only process executions verified to have no active processes/workers.
- Load the exact JobExecution and StepExecutions from JobRepository/JobExplorer.
- Inspect statuses, versions, last-updated timestamps, and related executions.
- Transition the stale execution to an appropriate terminal status using the repository/admin API supported by the version in use.
- Consistently update both related StepExecution statuses and the JobExecution; do not leave parent/child metadata inconsistent.
- Audit the operator, timestamp, reason, and execution ID.
- Only then call restart on the same JobInstance.

Do not provide a generic SQL statement to change `STATUS='STARTED'` to `FAILED` across tables. Metadata has relationships across JobInstance, JobExecution, StepExecution, ExecutionContext, versions, and update timestamps. Manually editing a few columns can leave invalid state or break restartability.

If the application needs automated recovery, build an admin operation with locking/leasing, process-owner verification, timeout/heartbeat checks, and the corresponding JobRepository API. Test this procedure on the exact Spring Batch version and metadata database before deploying to production.

## 10. Restarting with JobOperator

Once the old execution is in a restartable status, you can use `JobOperator.restart` with the old execution ID:

```java
@Service
public class BatchRestartService {

    private final JobOperator jobOperator;

    public BatchRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long restart(long previousExecutionId) throws Exception {
        return jobOperator.restart(previousExecutionId);
    }
}
```

`restart` takes the previous JobExecution ID, not the JobInstance ID or StepExecution ID. JobOperator uses metadata to identify the Job, JobParameters, and state to resume.

Before calling this method, the application must ensure the previous execution has been validly terminated and no old process remains. If the execution is still `STARTED`, already `COMPLETED`, or `ABANDONED`, the restart operation may be rejected according to Spring Batch state rules.

You can use `JobExplorer` to query execution details for administrative dashboards:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    throw new IllegalArgumentException("JobExecution not found");
}

BatchStatus status = execution.getStatus();
JobParameters parameters = execution.getJobParameters();
```

The snippet illustrates reading metadata. Do not transition statuses based solely on the read object; recovery must verify process ownership and update via an appropriate administrative mechanism.

## 11. Reader checkpoints and saveState

To restart from the right position, readers need to save state. Many standard Spring Batch readers implement `ItemStream` and support `saveState`.

File reader example:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

`saveState(true)` lets the reader store its read position in ExecutionContext. Keep the reader name stable because the name typically participates in checkpoint key generation. `@StepScope` allows the reader to receive the current execution's JobParameters.

For custom readers, implement `ItemStreamReader` and manage `open`, `update`, and `close`. Do not store checkpoint state of an execution in mutable fields of a singleton shared across multiple Jobs.

### Data sources must remain stable

Line or offset checkpoints only make sense if the data source maintains a stable order. If the file is replaced or database rows are inserted/deleted between the run and the restart, the reader may miss or double-read records.

Ways to mitigate risk:

- Use immutable input files and checksums/manifests to verify the exact file on restart.
- Use ascending keys or stable cursors instead of offsets on mutable datasets.
- Store a high-watermark or snapshot ID for the run.
- Do not reuse the same JobInstance with an input file containing different content.

## 12. Committed chunks vs. uncommitted chunks

Suppose a Step imports 1,000 items with a chunk size of 100. The process is killed while processing the sixth chunk.

| Chunk | State before kill | Behavior on restart |
|---|---|---|
| 1–5 | Committed | Committed data is preserved; generally not reprocessed within the same Step restart. |
| 6 | Uncommitted | Transaction typically rolls back; reprocessed from the most recently committed checkpoint. |
| 7–10 | Not started | Processed after preceding chunks complete. |

This is the expected model when reader checkpoints, JobRepository, and writers adhere to the transaction/restart contract. If business data and metadata use two independent transaction managers, there is no automatic atomic guarantee across both databases; data reconciliation may be required before restarting.

If chunk six actually committed before the process died without receiving the ACK, inspect target data and checkpoints. Writers should be idempotent or use unique business keys so reprocessing does not create duplicate records.

## 13. Tasklets and restarting after a process kill

Tasklets normally perform one action inside a TaskletStep transaction. If the process dies mid-operation, the outcome depends on the resource:

- Database changes inside an uncommitted transaction may roll back.
- Already-committed database changes remain.
- Moved files or sent HTTP requests do not roll back automatically.
- Step metadata may remain `STARTED` if the process died before updating final status.

Tasklets run again from the beginning on restart per policy. Therefore, a Tasklet must be idempotent or check whether the operation already completed.

For example, a Tasklet archiving a file should check both source and target files:

```java
if (Files.exists(targetPath)) {
    verifyArchivedFile(targetPath, expectedChecksum);
} else if (Files.exists(sourcePath)) {
    Files.move(sourcePath, targetPath, StandardCopyOption.ATOMIC_MOVE);
} else {
    throw new FileNotFoundException("Source and target are missing");
}
```

This is an illustrative example; filesystems without atomic move support, checksum mismatches on target files, and errors between operations must be handled explicitly. Do not assume a database transaction can restore a filesystem operation.

## 14. Non-transactional side effects and idempotency

A process kill can occur right after an external system has processed a request but before JobRepository records chunk/Step completion. On restart, the same request may be sent again.

Before restarting, determine:

- Do writers/processors make HTTP calls, send emails, or publish messages?
- Could the external system have processed the request before the response was lost?
- Is there a stable idempotency key across retries and restarts?
- Can the operation status be queried by business key?
- Is there an outbox/inbox or deduplication mechanism?

For side effects emitted after primary data commits, a transactional outbox is a common choice: write business data and an outbox record in the same transaction, then have a relay publish the event. The relay still needs idempotency because it can send successfully and crash before marking the event as sent.

Do not blindly retry a payment, reservation, or resource-creation operation without knowing whether the prior attempt succeeded. Query status, reuse the same idempotency key, or route the operation to a reconciliation process.

## 15. JobRepository must be durable

Restartability relies on metadata persisted in JobRepository. If JobRepository is in-memory-only or metadata is lost, Spring Batch lacks durable information to restore JobInstances, JobExecutions, and checkpoints.

In production:

- Use a JobRepository stored in a durable database.
- Back up metadata according to operational policies.
- Do not delete `BATCH_*` tables while Jobs may still need restarting or auditing.
- Ensure the metadata schema matches the Spring Batch version.
- Monitor repository size, indexes, and query latency.
- Keep JobParameters/ExecutionContext serializable and compatible across upgrades.

If the metadata repository is restored from an older backup than the business database, checkpoints may lag behind target data. A restart could then replay side effects; reconciliation or restoring both resources to a consistent state is required.

## 16. Process kills in container/Kubernetes environments

In container environments, the orchestrator may send a termination signal before removing a container. Applications should have a graceful shutdown period long enough to stop accepting new Jobs and allow running Jobs to finish the current chunk or stop cleanly.

Operational considerations:

- Configure `terminationGracePeriodSeconds` to accommodate maximum chunk duration and cleanup.
- Ensure the application receives SIGTERM and shuts down the Spring context cleanly.
- Pause schedulers/triggers before terminating to avoid launching additional Jobs.
- If a specific Job must stop, invoke `JobOperator.stop(executionId)` while the process is still alive.
- If the grace period expires and the container receives SIGKILL, treat it as a process crash; check for stale metadata before restarting.
- Tune readiness/liveness probes carefully; repeated liveness restarts can kill running Jobs.
- With multiple replicas, use locks or coordination mechanisms to prevent two instances from owning the same business operation.

Graceful shutdown reduces the likelihood of stale metadata, but does not replace checkpoints, idempotency, and recovery procedures. Shutdown hooks are never guaranteed to run when a node or kernel crashes.

## 17. Schedulers and preventing duplicate launches after a process kill

After an instance dies, a scheduler or another instance may attempt to relaunch the Job. If metadata is still `STARTED`, JobRepository usually blocks a new execution for the same JobInstance. However, orchestrators must avoid creating a new JobInstance via different identifying parameters just to bypass this error.

Best practices:

- Use stable business keys for identifying parameters.
- Inspect current executions before launching.
- Automatically recover only after verifying the old owner died.
- Use distributed locks/leases with fencing tokens when multiple schedulers/replicas operate.
- Store correlation IDs linking scheduler runs, JobInstances, and JobExecutions.
- Separate workflows for creating new JobInstances from workflows for restarting old JobInstances.

If a scheduler uses a timestamp as an identifying parameter every minute, a single process kill can spawn multiple distinct JobInstances processing the same dataset. Design identifying parameters around business identity rather than scheduler trigger time.

## 18. Common pitfalls

### Relaunching immediately with the same JobParameters

If the old JobExecution is still `STARTED`, JobRepository may consider the JobInstance running and reject the launch. Verify the old process, recover stale metadata, and then restart.

### Adding a timestamp to create a new JobInstance

This bypasses the old execution status but can reprocess all data and create duplicate side effects. Restarts must preserve the original business run's identifying parameters.

### Calling JobOperator.stop after the process already died

No process remains to receive the request and complete stopping. Recover stale metadata through an administrative procedure instead.

### Marking an execution ABANDONED and expecting to restart it

`ABANDONED` indicates the execution will not be resumed. If resuming is required, use an appropriate restartable terminal status, typically `FAILED`, per recovery procedures.

### Directly updating a STATUS column in BATCH_* tables

Metadata involves multiple relationships and version columns. Manually editing a single column can make JobExecution/StepExecution inconsistent. Use supported repository/admin APIs and audit the operation.

### Assuming an uncommitted chunk definitely caused no side effects

HTTP calls, emails, messages, and files may have been processed outside the transaction. Check target systems or use idempotency/outboxes before re-running.

### Reader does not save checkpoints

The reader may start from the beginning or fail to restore the right position. Use an `ItemStream`-capable reader, enable `saveState`, and keep input stable.

### Restarting while the old process is still running

Two executions may concurrently process the same business keys. Verify PIDs/containers/workers and database sessions before recovering.

### Using an in-memory JobRepository in production

Process death loses metadata; reliable restarts become impossible. Use a durable repository.

## 19. Operational runbook after a process kill

A recovery runbook can follow this sequence:

1. **Prevent new launches:** pause schedulers or triggers creating the same business operation.
2. **Identify the execution:** look up Job name, JobInstance, JobExecution ID, StepExecutions, and identifying parameters.
3. **Verify process state:** check PID, container, Pod, host, and remote workers; confirm no old process remains active.
4. **Check transactions:** confirm old database sessions closed and uncommitted transactions rolled back or recovered.
5. **Read metadata:** inspect BatchStatus, ExitStatus, update timestamps, failure exceptions, commit/rollback counts, and ExecutionContext.
6. **Reconcile data:** identify the last committed chunk, check target data for duplicates, and verify whether non-transactional side effects occurred.
7. **Recover stale execution:** use a supported admin/recovery API to terminate the orphaned `STARTED` state after confirming old process death; update related executions consistently.
8. **Preserve identity:** do not add new identifying parameters if the goal is restarting the old JobInstance.
9. **Restart:** invoke `JobOperator.restart(previousExecutionId)` or the corresponding launch mechanism once the execution is restart-eligible.
10. **Monitor:** watch the new JobExecution, StepExecutions, checkpoints, retry/skip counts, and target data.
11. **Reconcile outcomes:** confirm no side effects were lost or duplicated; resolve operations with indeterminate status.
12. **Re-enable scheduler:** resume automated schedules only once the JobInstance and business data are in a safe state.

| Check | Evidence needed before restarting |
|---|---|
| Old process | PID/container/Pod terminated, no remaining worker owns the execution. |
| Transactions | Old sessions released; commit/rollback status determined or reconciled. |
| Metadata | Stale Job/Step executions identified and recovered per procedure. |
| Checkpoints | ExecutionContext reflects the last committed chunk. |
| Input | File/snapshot/cursor matches the original JobInstance. |
| Side effects | Idempotency, status lookup, or reconciliation in place for unknown operations. |
| JobParameters | Identifying parameters preserved for the restart. |

## 20. Testing restarts after process kills

Do not test only Job failures caused by exceptions. Simulate abrupt process termination at different points:

- Before a chunk starts.
- After the reader reads items but before the writer.
- While the writer is writing but before commit.
- While commit is in progress.
- After commit but before the application logs or receives the response.
- After non-transactional side effects succeed but before metadata updates.
- While a partition worker is running.
- Inside a Tasklet moving files or calling APIs.

After each scenario, verify:

- JobRepository has accurate or recoverable execution status.
- Committed chunks remain intact.
- Uncommitted chunks are reprocessed from checkpoints.
- Readers restore the exact position without missing data.
- Writers do not create duplicate records or side effects.
- JobInstance preserves its identity.
- The recovery procedure prevents two processes from running the same operation.

Run tests against a real database and transaction manager or a production-equivalent environment. Mocks cannot prove rollback behavior on dropped sockets, lost commit ACKs, or separate metadata and business datasources.

## 21. Deciding between restart, reprocess, and a new Job

Not every process kill should restart the same JobInstance. Distinguish three intents:

| Intent | Approach |
|---|---|
| Resume the remainder of the same business run | Recover the stale execution and restart the same JobInstance. |
| Re-run specific failed or rejected items | Create a dedicated reprocess workflow with business keys and corrected inputs. |
| Process a new business batch | Create a new JobInstance using new identifying parameters reflecting the new batch/business run. |

Restarting does not automatically revert target data to its pre-Job state. If re-running completely from scratch is needed, an explicit delete/overwrite/idempotency strategy and understanding of prior side effects are required.

## Conclusion

When a process is killed, Spring Batch may not have time to transition JobExecution/StepExecution out of `STARTED`. Committed chunks persist; uncommitted transactions usually roll back when the database session closes, while commits at the moment of disconnection may need reconciliation. Reader checkpoints in `ExecutionContext` determine where the Step resumes, but the JobInstance can only restart once the old execution is in an eligible status. Verify old processes/workers are dead, recover stale metadata via a supported administrative mechanism, preserve identifying JobParameters, and trigger restart using the old execution ID. Because rollbacks do not undo non-transactional side effects, writers and Tasklets need idempotency, outboxes, or reconciliation so restarting neither drops nor duplicates business actions.
