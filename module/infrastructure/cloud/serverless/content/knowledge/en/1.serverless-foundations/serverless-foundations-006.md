# Execution Time, Memory, Payload, and Ephemeral Resource Limits

Serverless applications are typically deployed as one or more functions that run when an HTTP request, a queue message, or an event from another service arrives. Each execution is granted a finite resource budget. A function can run fine on a developer machine yet fail in the cloud if it processes too long, consumes too much memory, receives an oversized payload, or fills ephemeral storage.

Understanding these limits helps Java developers choose how to split work, set timeouts, stream data, and decide when FaaS is appropriate. Exact numbers depend on the provider, trigger service, deployment region, configuration, and time. Therefore, look up current quotas for each service before designing; there is no single universal limit across all serverless platforms.

## 1. Four Limit Categories to Distinguish

| Category | What does the limit control? | What can happen when exceeded? |
|---|---|---|
| Execution timeout | Maximum duration for a single execution | The platform terminates the function; the request may time out; messages or events may be retried depending on the trigger |
| Memory | RAM that the runtime and application code are permitted to use | The function may be terminated, flagged as errored by the runtime, or throw an OutOfMemoryError |
| Payload | Size of request, event, message, batch, or response passed through each service | A service may reject the request, fail to enqueue the message, fail to invoke the function, or fail to return the response |
| Ephemeral resources | Ephemeral disk space, file descriptors, threads, sockets, and short-lived OS resources | File writes fail, OS resources are exhausted, connections run out, or the function slows down and fails |

These limits are related but not interchangeable. Increasing memory does not automatically increase payload size. Increasing timeout does not allow a request to bypass an API gateway limit. Adding ephemeral disk space does not make data on that disk durable.

An HTTP request can pass through multiple layers: client, load balancer or API gateway, function, and downstream services. Each layer has its own timeouts and size limits. For messages or events, limits may reside at the producer, queue, event bus, batch size, and function. When analyzing errors, identify the exact layer that rejected or terminated processing.

## 2. Execution Time Limits

### 2.1. Function Timeout and Caller Service Timeout

The execution timeout is the maximum time the platform allows a single invocation to run. This duration can include runtime initialization, library loading, input processing, external service calls, and result generation; exact accounting depends on the platform.

With synchronous HTTP, the client or API gateway may time out before the function reaches its execution timeout. For example, if a function is configured to run longer than the gateway allows, once the gateway closes the connection the caller still receives no result. The function may even continue running for a while if the platform allows it. Therefore, check both the function timeout and the timeout of every component along the path.

With asynchronous processing, the sender typically receives an acknowledgment that the event was accepted before the function completes. If an invocation times out or fails, the platform may retry, move the event to a dead-letter queue, or send it to an error destination. Retry policies, event retention periods, and attempt counts vary by service. Do not infer that a timeout means an event was definitely lost or will definitely be rerun.

### 2.2. Budgeting Execution Time

Do not spend the entire timeout on core business processing. An invocation also needs time to read and decode input, call external services, write results, close resources, and finish the response. Budget time across each stage:

~~~text
Invocation budget
  = initialization and input reading
  + business processing
  + external service calls
  + writing results and building response
  + safety margin
~~~

The safety margin allows the application to finish critical operations and return a controlled error before the platform terminates the function. The margin value should be determined by measuring representative workloads rather than picking a fixed percentage for every application.

When calling HTTP endpoints, databases, or other services, set connect timeouts and read/request timeouts smaller than the remaining invocation time. If a call could take longer than the remaining budget, fail early or offload the work to a queue. Retries must be bounded, with backoff and jitter; do not loop indefinitely inside a short invocation.

For Java, use a monotonic clock such as System.nanoTime() to measure elapsed time. Wall clocks such as System.currentTimeMillis() can jump when the system synchronizes time. If the platform provides an API reporting remaining invocation time, use that API as the primary source because it reflects the runtime's actual deadline.

### 2.3. Handling Long-Running Work

If a task might exceed the timeout, split it into resumable steps:

- Partition data into small chunks and process each chunk.
- Persist checkpoints or progress state in a database or object storage.
- Push subsequent work into a queue or workflow orchestration.
- Design each step to be safely re-executable using an idempotency key.
- Cap retry counts and route persistently failing tasks to a dead-letter queue for investigation.

Do not assume an invocation will complete strictly once. A timeout can occur after a downstream service accepted a command but before the function received the response. Upon retry, the command may be sent again. For creating orders, charging payments, or sending notifications, use idempotency keys, unique constraints, or state-recording mechanisms to prevent duplicate side effects.

## 3. Memory Limits

### 3.1. Function Memory Is More Than Java Heap

The RAM limit configured for a function must hold the entire process, not only Java objects. Memory consumers can include:

- Java heap: objects, collections, strings, and decoded data.
- Metaspace and class data: class metadata, proxies, and loaded libraries.
- Thread stacks: each thread has its own stack region.
- Native memory and direct buffers: TLS, NIO, compression, JNI libraries, and JVM internals.
- Platform runtime, JIT compiler, agents, and platform libraries.

Accordingly, setting Xmx equal to the entire RAM limit is risky. When the heap consumes nearly the whole budget, the JVM still needs off-heap memory to operate. Leave headroom based on measurements from the target deployment environment.

In Java, Runtime.getRuntime().maxMemory() reports the maximum heap limit seen by the JVM; it is not the total RAM the function is consuming. Runtime.getRuntime().freeMemory() does not tell you how much container RAM remains either. Combine JVM metrics with platform memory metrics.

### 3.2. Common Causes of Memory Spikes

Certain code patterns can drive memory usage up rapidly:

- Reading an entire file or request into a byte[] and then creating additional Strings and object trees.
- Parsing large JSON into deeply nested objects when only a few fields are needed.
- Accumulating results for all records in a List before writing to the destination.
- Making multiple copies of data during encoding conversions, serialization, or compression.
- Loading large libraries or instantiating multiple clients per invocation.
- Creating unbounded threads, futures, or tasks.
- Holding invocation data in static variables longer than needed.

For instance, reading a payload of size P into a byte[], converting it to a String, and parsing it into objects can consume several times P in RAM. The amplification factor depends on encoding, JSON structure, and how the library represents objects. Thus, request size cannot be used directly as a RAM predictor.

### 3.3. Controlling Memory in Java

Prefer streaming processing when data is large. Read in fixed-size buffers, process each chunk, and release references. For large JSON, use a streaming parser instead of always parsing everything into an object tree. When writing output, consider writing in small batches.

Bound collection sizes and concurrent tasks. Use thread pools with bounded thread counts and bounded queues. If the queue is full, reject or apply backpressure instead of silently accumulating work in the heap. Reuse thread-safe clients at the execution environment scope if the library allows, but never retain one user's data in static variables.

Increasing memory allocation may cause some platforms to allocate additional CPU or speed up processing, though this depends on the provider. Benchmark multiple configurations on the same workload and compare duration, peak memory, throttling counts, and cost. Choose configurations based on latency and cost targets rather than simply picking the highest RAM tier.

## 4. Payload Limits and Transferring Large Data

### 4.1. Size Is Constrained at Multiple Points

A payload is data crossing boundaries between services: HTTP bodies, messages, events, individual batch records, or responses. Constraint points can include:

- Clients, proxies, load balancers, and API gateways.
- Services receiving requests or integrating with the function.
- Queues, topics, or event buses.
- Single message size, total batch size, and record count per batch.
- Event size limit passed by the platform into the function.
- Synchronous response size or data returned by the function.

Request and response limits can differ. Function limits can also differ from gateway or queue limits. A request might be accepted by the gateway yet fail to forward to the function. Verify limits across the entire path and check payload sizes after serialization.

When encoding binary data as Base64, size typically grows by roughly one third, before counting JSON wrappers and metadata. Compression can shrink transfer size but requires CPU and RAM to compress/decompress; do not treat compression as a guaranteed way to bypass quotas.

### 4.2. When Payloads Are Small

For small, well-bounded requests, a function can validate, decode, and process directly. Even so, you should:

- Check size before deep parsing.
- Validate data types, field counts, string lengths, and nesting depth.
- Return clear errors for oversized inputs.
- Avoid logging entire payloads.
- Never trust that clients always send accurate Content-Length or size metadata.

If the platform has already loaded the entire event into memory before calling the handler, checking inside the handler only prevents the application from allocating even more RAM; it cannot undo the ingestion cost that already occurred in the runtime layer.

### 4.3. When Payloads Are Large

Do not stuff large file contents into HTTP bodies or messages when services have lower limits. A common pattern is storing the content in object storage and passing a reference:

1. The client uploads the file directly to object storage using an authorized, time-limited URL.
2. Once upload finishes, the client sends a small event containing the object key, bucket/container, business ID, and required metadata.
3. The function reads the file via streaming or in chunks.
4. The function writes results to object storage or a database.
5. The system persists processing state and emits a completion event if needed.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Object Storage
    participant Q as Queue or Event Bus
    participant F as Java Function
    C->>S: Upload file directly
    S-->>C: Return object key
    C->>Q: Send small event with object key
    Q->>F: Trigger function
    F->>S: Stream file
    F->>S: Write result or checkpoint
    F-->>Q: Complete or report error
~~~

This approach shrinks payloads flowing through queues and functions while allowing retries using the reference to the same object. Check access permissions, URL expiration, object lifecycle, file size, checksums, and whether the object could be modified during processing.

For queues, consider splitting large messages into smaller chunks with sequence numbers and a shared correlation identifier. Consumers must detect missing chunks, duplicates, and out-of-order delivery. If business logic requires treating the whole file as one unit, store a manifest to track part states.

## 5. Ephemeral Resources in Serverless Environments

### 5.1. Ephemeral Disk and the /tmp Directory

Many platforms provide a local ephemeral storage area for each execution environment, commonly mounted at a directory such as /tmp. Applications can use this area to download files, extract archives, generate reports, or exchange data with libraries that only accept file paths.

Ephemeral disk has its own quota. Free space can shrink across multiple invocations if files are not cleaned up. Some platforms keep execution environments alive across invocations, so leftover files can appear on subsequent runs. However, environments can be replaced at any time; ephemeral files are not durable storage and must never serve as the source of truth.

When using temporary files:

- Generate unique filenames to avoid overwrites across invocations.
- Close streams inside try-with-resources.
- Delete files in a finally block, even when errors occur.
- Check available space before downloading or extracting.
- Limit the number and size of files processed concurrently.
- Do not rely on a file still existing on the next invocation.
- Do not write sensitive data without appropriate protections.

Java example:

~~~java
Path tempFile = Files.createTempFile("serverless-", ".bin");

try {
    try (InputStream input = source;
         OutputStream output = Files.newOutputStream(tempFile)) {
        input.transferTo(output);
    }

    processFile(tempFile);
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

This snippet assumes the function owns the InputStream and is responsible for closing it. If the stream is managed by a framework, follow the framework's contract instead of closing resources the application does not own.

When processing compressed archives, limit both the compressed file size and the total uncompressed size, entry count, and directory depth. A small archive can expand into huge data, exhausting disk or memory.

### 5.2. File Descriptors, Threads, and Connections

Beyond disk, functions also consume operating system resources:

- File descriptors for files, sockets, and pipes.
- Threads and thread stacks.
- HTTP, database, and message broker connections.
- Direct buffers and native resources.

If each invocation creates a new HTTP client or connection pool without closing it, open sockets can accumulate across runs. If new threads are spawned per record, the function can exhaust threads or stack memory. Reuse appropriate clients, close resources properly, set pool limits, and use connection timeouts.

Concurrency within a single execution environment depends on the runtime and platform. Never assume every function has only one active invocation at a time or that every static variable is safe. If an application can process concurrently within the same process, shared state must be thread-safe and invocation data must be isolated.

## 6. Designing by Trigger Type

| Trigger | Key risks | Appropriate design |
|---|---|---|
| Synchronous HTTP | Gateway or client times out before function; response exceeds limits | Fast validation, body limits, end-to-end timeout budgeting; for long tasks return an acceptance code and process asynchronously |
| Queue/message | Message or batch exceeds quota; retries cause duplicate processing; one failing record affects the batch | Cap sizes and batches; idempotent handling; use partial batch responses if supported; configure retries and DLQ |
| Asynchronous event | Events may arrive late, duplicated, or out of order; function timeouts | Process events independently, persist state, deduplicate, define retry policies and error destinations |
| Object storage event | Large files or objects modified/deleted before processing | Pass object key and version/checksum; stream reads; manage permissions and object lifecycle |

HTTP fits when callers need fast results and work is clearly bounded. If processing time is unpredictable, return an acceptance status with a job ID, then process via a queue or workflow. Callers query status through a separate endpoint.

For queues, batch size affects both duration and memory. Larger batches reduce function invocation overhead but raise peak memory and the risk that one bad record forces many records to reprocess. Choose batch size based on per-record processing time, data size, and the service's retry mechanism. When the platform supports per-record failure reporting, use it to avoid unnecessarily replaying the entire batch.

## 7. Java Example: Bounded Data Reading

The following snippet reads an InputStream using a fixed buffer and rejects data exceeding an application-defined threshold. This is an application-layer limit; it does not replace gateway, queue, or platform quotas.

~~~java
static void copyWithLimit(
        InputStream input,
        OutputStream output,
        long maxBytes) throws IOException {

    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be non-negative");
    }

    byte[] buffer = new byte[64 * 1024];
    long total = 0;
    int count;

    while ((count = input.read(buffer)) != -1) {
        total += count;

        if (total > maxBytes) {
            throw new IOException("Payload exceeds the application limit");
        }

        output.write(buffer, 0, count);
    }
}
~~~

In this example, buffer memory does not grow with file size. Data is written to the destination after each read. If the destination is a temporary file, close streams and delete the file on failure. If the destination is object storage or a network service, set timeouts and handle mid-stream write failures.

## 8. Measuring and Testing Limits

You cannot choose reliable configurations based solely on average request size. Test with representative data and worst-case scenarios:

1. Measure cold start and warm invocation durations separately if the platform provides metrics.
2. Test small payloads, payloads near application limits, and payloads exceeding limits.
3. Test files with many records, unusually large records, and compressed archives with high expansion ratios.
4. Test slow downstream responses, dropped connections, and transient errors.
5. Test high concurrent invocations to uncover connection, thread, or memory exhaustion.
6. Test function timeouts at different points to verify retries and idempotency.
7. Monitor ephemeral disk space across multiple invocations in the same execution environment if the platform keeps environments alive.

Useful metrics include duration, timeout count, error count, throttling, memory used/peak, payload size, records per batch, retry count, message age, open connection count, and ephemeral disk usage. Attach request IDs, correlation IDs, or job IDs to logs to connect processing steps. Log sizes and necessary metadata; avoid logging full request contents or sensitive data.

Watch percentiles such as p95 and p99, not just averages. A function with a low average duration can still time out frequently when encountering large files or slow downstream services. Set alerts before hitting quotas so there is time to adjust batch sizes, memory, timeouts, or task splitting.

## 9. Configuration Selection Workflow

You can apply the following workflow to each function:

1. **Map the data path.** List the client, gateway, trigger, function, and downstream services; record timeouts and quotas for each layer.
2. **Set business limits.** Define maximum sizes, record counts, target processing times, and expected concurrency.
3. **Choose how data is transferred.** Small data can travel in requests or events; large data should be stored in object storage and passed by reference.
4. **Measure resource usage.** Measure time, heap, native memory, ephemeral disk, threads, and connections with representative data.
5. **Set budgets and margins.** Downstream call timeouts must fit inside the remaining deadline; heap must leave headroom for native and runtime memory.
6. **Verify retries and idempotency.** Simulate a timeout after an external operation succeeds but before the function receives the response.
7. **Monitor after deployment.** Use metrics and logs to detect workload shifts, then tune configurations or split tasks.

When a function frequently requires very long durations, large amounts of RAM, continuous data processing, or durable local state, evaluate workers/containers or dedicated processing services. FaaS fits best when work can be divided into bounded invocations, scales with events, and does not depend on durable local state.

## 10. Self-Check Questions

- How do a function's timeout and a gateway's timeout relate to each other?
- Why is the heap limit not equal to the function's RAM limit?
- Why can reading an entire payload into a byte[] consume more RAM than the payload size?
- When should you pass an object key instead of putting a file into a message?
- Why must files in /tmp not be used as durable state?
- What problem can occur on retry if an invocation times out after writing data to another system?
- Which metrics help detect a function approaching memory or execution time limits?

Being able to answer these questions helps developers evaluate a function across its entire data lifecycle: where data enters, how many resources it consumes, where it is stored, and what happens when an invocation ends or is retried.
