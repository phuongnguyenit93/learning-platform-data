# Terminating Streams According to Their Lifecycle

## Learning Objectives

After this lesson, you will be able to:

- Describe the lifecycles of unary, server-streaming, client-streaming, and bidirectional streaming RPCs.
- Distinguish closing the request-sending direction from terminating the entire RPC.
- Use **onCompleted()**, **onError()**, and cancellation properly according to each observer's role.
- Determine when the server is permitted to finish the response stream.
- Handle deadlines, asynchronous errors, and client disconnects without leaking resources.
- Test lifecycles to guarantee each stream direction has strictly one terminal event.

## 1. Lifecycle of a Streaming RPC

A gRPC call has a start time, a message-exchange phase, and a final outcome. With streaming RPCs, each transmission direction can finish at a different time. Therefore, distinguish **closing a message-sending direction** from **ending the RPC**.

In gRPC Java, **StreamObserver<T>** uses three callbacks:

- **onNext(value)**: sends or receives a message while that stream direction is still active.
- **onCompleted()**: finishes the stream direction represented by that observer successfully.
- **onError(error)**: terminates the stream direction with an error.

For an observer the application uses to send messages, after **onCompleted()** or **onError()**, no further **onNext()** or other terminal callback may be called. For an observer the application provides to receive responses, gRPC invokes the receiving callbacks; the application must handle them in the same lifecycle order and never treat them as data-sending APIs.

## 2. An RPC Can Have Two Independent Directional Lifecycles

In client-streaming and bidirectional streaming, the client can finish sending requests while still waiting for responses from the server. This is a **half-close**: the client declares it will send no more request messages, yet the RPC may still be active.

For example:

~~~text
Client request direction:
onNext(chunk 1) -> onNext(chunk 2) -> onCompleted()

Server response direction:
onNext(progress) -> onNext(progress) -> onCompleted()
~~~

Calling **onCompleted()** on the client's request observer only closes the client → server direction. It does not mean the server has finished its work or that the client has received the final response.

Similarly, when the server receives **onCompleted()** on the request observer, it means the client has finished sending the request stream. The server can continue processing the received data, send one or more responses, and only then complete the response observer.

## 3. Lifecycles of the Four RPC Types

| RPC Type | Request | Response | Termination meaning |
| --- | --- | --- | --- |
| **Unary** | One message | One message | Server sends response then completes successfully; or call ends with an error. |
| **Server-streaming** | One message | Many messages | Server finishes sending all responses then completes the response direction. |
| **Client-streaming** | Many messages | One message | Client half-closes requests; server finishes processing then returns one final response. |
| **Bidirectional** | Many messages | Many messages | Both sides send independently; each direction can end at a different time. |

The biggest distinction lies in client-streaming and bidirectional: the client calling **requestObserver.onCompleted()** signals the end of requests, not the end of the response stream.

## 4. Unary and Server-Streaming: Server Completes Responses

With a unary RPC, the server typically sends strictly one response and then calls **onCompleted()**:

~~~java
@Override
public void getProfile(
        GetProfileRequest request,
        StreamObserver<Profile> responseObserver) {
    try {
        Profile profile = profileService.find(request.getUserId());
        responseObserver.onNext(profile);
        responseObserver.onCompleted();
    } catch (ProfileNotFoundException ex) {
        responseObserver.onError(
            Status.NOT_FOUND
                .withDescription("Profile not found")
                .asRuntimeException());
    }
}
~~~

Never call **onCompleted()** inside **finally**, because the `catch` branch may have already called **onError()**. There must be strictly one termination path: success or failure.

With server-streaming, the server calls **onNext()** for each response. Call **onCompleted()** only when the data source has finished and no responses remain waiting to be sent. If the producer runs asynchronously, completion state must be synchronized with the queue and writer.

## 5. Client-Streaming: Request Half-Closes Before Response

The async stub returns a **StreamObserver<Request>** for the client to send multiple requests. The client calls **onCompleted()** when finished sending:

~~~java
StreamObserver<UploadChunk> requestObserver =
    asyncStub.upload(new StreamObserver<UploadResult>() {
        @Override
        public void onNext(UploadResult result) {
            showUploadResult(result);
        }

        @Override
        public void onError(Throwable error) {
            showUploadFailure(error);
        }

        @Override
        public void onCompleted() {
            showUploadFinished();
        }
    });

requestObserver.onNext(firstChunk);
requestObserver.onNext(secondChunk);
requestObserver.onCompleted(); // Half-close request direction.
~~~

Only after the client half-closes does the server know no more chunks are coming. The server can verify integrity, flush data, write final metadata, and build **UploadResult**. The client's response observer will receive **onNext(result)** followed by **onCompleted()** if successful.

Do not wait for the final response before half-closing if the server only returns a result after receiving all input; otherwise, both sides wait on each other indefinitely until the deadline expires.

## 6. Bidirectional Streaming: Two Directions Terminate Independently

With bidi streaming, the client can keep receiving responses after calling **onCompleted()** on the request observer. For instance, the client sends a subscribe command, receives updates, and then half-closes when no new commands are needed:

~~~text
Client -> Server: subscribe
Server -> Client: update 1
Client -> Server: filter change
Server -> Client: update 2
Client -> Server: onCompleted()  (no more new requests)
Server -> Client: update 3
Server -> Client: onCompleted()  (response stream ends)
~~~

The server should not end the response stream just because the request stream has half-closed, unless the business contract explicitly specifies that. There may still be data being processed or responses already scheduled.

Conversely, the server can end responses before the client closes the request stream if the RPC is complete or the server decides to stop the call. The client must stop sending upon receiving a terminal result or cancellation; never keep emitting requests on an already-terminated call.

## 7. onCompleted and onError Are Terminal Events

Each stream direction has only one terminal outcome:

| Outcome | Callback | Meaning |
| --- | --- | --- |
| Success | **onCompleted()** | No further messages in that stream direction. |
| Failure | **onError(Throwable)** | Stream direction ends with an error; gRPC status indicates the cause to the receiver. |

Never call both to "ensure" completion. Never call **onNext()** after a terminal event. On the server response observer, **onError()** usually carries a **StatusRuntimeException** or an error mapped to an appropriate status.

An error occurring after **onCompleted()** has already been sent cannot flip the RPC outcome to failure. Record late errors via logs/metrics or handle them in a separate workflow; never emit a second terminal callback.

## 8. Client Cancel and Deadlines Are Not onCompleted

**Cancellation** occurs when the client actively cancels the call, the channel closes, or the call is cancelled by runtime mechanisms. **Deadline exceeded** occurs when the RPC timeout expires before completion. These are not successful completions.

On the server, you can detect call cancellation using **ServerCallStreamObserver.setOnCancelHandler(...)**:

~~~java
ServerCallStreamObserver<Update> call =
    (ServerCallStreamObserver<Update>) responseObserver;

call.setOnCancelHandler(() -> {
    stopUpstreamSubscription();
    cancelPendingWork();
    releaseResources();
});
~~~

The cancellation handler should signal shutdown and return quickly. Do not block this callback with long I/O operations. Cleanup must be safe when multiple termination causes occur close together, such as client cancellation occurring concurrently with a worker error.

Do not attempt to send an extra **onCompleted()** or **onError()** in response to an already-cancelled call. The transport already manages the cancellation outcome; the application must stop the producer and release resources.

## 9. Managing Resources Along the Lifecycle

A long-lived streaming RPC may hold database cursors, subscriptions, file handles, queues, executor tasks, or semaphore permits. Every resource must be tied to the call lifecycle:

1. **On start**: allocate resources and register the cancellation handler.
2. **While running**: verify the call is still active before continuing expensive work.
3. **On request half-close**: stop expecting new input, while finishing processing of already-received data.
4. **On successful or error completion**: stop the producer and release resources.
5. **On cancel/deadline**: cancel upstream, stop workers, and clear pending queues per policy.

Group cleanup into an idempotent function that can be called multiple times while releasing each resource only once. This prevents leaks when cancellation and terminal callbacks arrive nearly simultaneously.

## 10. Serializing Termination with Multiple Workers

An asynchronous producer may generate responses from multiple threads. If worker A calls **onCompleted()** while worker B is still preparing **onNext()**, a message may be sent after the terminal event.

Do not merely check a standalone boolean:

~~~java
if (!terminated.get()) {
    responseObserver.onNext(update);
}
~~~

Another worker can set **terminated = true** and call **onCompleted()** after the check finishes but before **onNext()** executes. Both the state check and callback invocation must be serialized:

- Use a serial executor as the sole place calling the observer.
- Or use an emitter whose lock wraps both the check and callback emission.
- All producers only enqueue messages or request terminal events; they never call the observer directly.
- Only the writer owns the right to emit **onNext**, **onError**, and **onCompleted**.

With server-streaming using readiness, the writer must also check **isReady()** and pause draining when not ready. When the producer finishes, emit **onCompleted()** only after the queue is empty and no message is still in flight.

## 11. Client-Streaming Server Pattern Terminating at the Right Time

The server receives multiple chunks and returns a result only after the client half-closes:

~~~java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    UploadSession session = uploadService.openSession();

    return new StreamObserver<>() {
        private boolean finished;

        @Override
        public void onNext(UploadChunk chunk) {
            if (finished) {
                return;
            }
            session.accept(chunk);
        }

        @Override
        public void onError(Throwable error) {
            if (finished) {
                return;
            }
            finished = true;
            session.abort();
        }

        @Override
        public void onCompleted() {
            if (finished) {
                return;
            }
            finished = true;
            try {
                UploadResult result = session.finish();
                responseObserver.onNext(result);
                responseObserver.onCompleted();
            } catch (RuntimeException ex) {
                responseObserver.onError(
                    Status.INTERNAL
                        .withDescription("Upload finalization failed")
                        .withCause(ex)
                        .asRuntimeException());
            } finally {
                session.close();
            }
        }
    };
}
~~~

This is a skeleton for a sequential handler. If callbacks can be invoked from multiple threads or **session.finish()** runs asynchronously, the **finished** state and response emission must be protected by an appropriate serial executor/synchronization. In a real system, cancellation must also be wired to **session.abort()** and **session.close()**.

Key point: **onCompleted()** on the request observer is when the server knows input has ended. It is not a terminal event for the response observer; the server still needs to send the final response and complete the response direction separately.

## 12. Testing Streaming RPC Lifecycles

Key test cases:

1. Unary success: one response followed by terminal success.
2. Unary failure: no response after terminal error.
3. Server-streaming: receive all messages in order then **onCompleted()**.
4. Client-streaming: client half-closes, server finishes processing all input then returns the final response.
5. Bidirectional: client half-closes yet still receives responses for already-sent data.
6. Client cancels mid-stream: server stops producer and releases subscriptions/queues.
7. Deadline expires: workers stop and emit no further messages.
8. Worker errors concurrently with cancellation: only one cleanup path takes effect and no duplicate terminal callbacks occur.
9. Asynchronous producer finishes while the queue still holds messages: server drains everything before completing.

When testing, do not merely verify the client receives the right data. Also verify that upstream subscriptions are cancelled, queues are freed, executor tasks stop, and observers receive no callbacks after a terminal event.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Treating request **onCompleted()** as ending the whole RPC | Server/client stops too early, losing final responses | Treat it as a half-close of the request direction. |
| Server completing response immediately upon receiving all requests | Drops pending asynchronous work | Wait for processing to finish and drain the response queue. |
| Calling **onCompleted()** in **finally** | May be called after **onError()** | Choose a single terminal path. |
| Sending **onNext()** after a terminal event | Violates observer lifecycle | Serialize state and callbacks. |
| Treating cancellation as successful completion | Reports wrong outcome and keeps processing | Stop producer, clean up, and emit no redundant terminal event. |
| Ignoring deadlines | RPC holds resources for too long | Propagate deadlines/cancellation to upstream work. |
| Cleaning up only on the success branch | Resource leaks on error or cancel | Use idempotent cleanup on all termination paths. |
| Multiple workers emitting responses concurrently | Races, wrong ordering, or duplicate terminal events | Use one serial writer per observer. |

## 14. Practice Exercises

Design a client-streaming RPC that receives records and returns the total count of valid records:

1. Client sends multiple records via the request observer.
2. Client calls **onCompleted()** when no records remain; explain why this is only a half-close.
3. Server continues validating and saving already-received records.
4. After processing finishes, server sends one **UploadSummary** then calls response **onCompleted()**.
5. If validation fails fatally, server terminates the response with **onError()** and does not call **onCompleted()**.
6. Add a cancellation handler to stop writing data and close the session.
7. Write tests for client half-close, final server response, mid-stream error, and cancellation.

**Completion criteria:** distinguish the two directional lifecycles, terminate strictly once, lose no final responses, and release resources across all termination paths.

## 15. Key Takeaways

- A streaming RPC can have two send/receive directions with different completion times.
- **onCompleted()** on the client's request observer half-closes the request direction; the server can still send responses.
- **onCompleted()** on the response observer ends responses successfully; **onError()** ends with an error.
- Never call **onNext()** or another terminal callback after a terminal event.
- Cancellation and deadlines are not successes; they must stop producers and trigger cleanup.
- With asynchronous processing, use a single sequential emitter gate and idempotent cleanup.
- Test half-close, terminal outcomes, cancellation, deadlines, and background resources.

Managing lifecycles properly helps Spring gRPC services finish each streaming direction at the right time, preserve final responses, avoid callbacks after terminal events, and release resources whether an RPC succeeds, fails, or is cancelled.
