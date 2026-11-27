# Testing Chat, Command Streams, and Continuous Responses

## 1. What to Test in a Bidi Stream

A chat application using **Spring gRPC** typically maintains a long-lived RPC for the entire session: the client sends commands to join a room, send messages, or leave a room; the server returns acknowledgments, forwards messages, and proactively emits heartbeats or system notifications. Both sides send independently, so a test that merely sends one request and waits for one response will not prove full-duplex behavior.

A useful test suite should prove three things:

1. **Command stream:** the client can send multiple commands on the same RPC; the server processes and responds with the right command ID.
2. **Chat/event stream:** the server can emit command-triggered messages as well as proactive events not bound to any specific command.
3. **Continuous responses:** the client continues receiving heartbeats/events while still sending commands; half-closing the request direction does not prematurely end the response stream.

This lesson focuses on testing those behaviors using gRPC Java and an in-process server/channel. The approach fits services registered in Spring: you can test RPC logic directly via the service bean, and separately test Spring bean creation and registration in a context test.

## 2. Small Contract for Testing

Use a contract with command IDs to route responses:

```proto
syntax = "proto3";

package chat.v1;

option java_multiple_files = true;
option java_package = "com.example.chat.v1";

service ChatRoom {
  rpc Converse(stream ChatCommand) returns (stream ChatEvent);
}

message ChatCommand {
  string command_id = 1;
  oneof action {
    JoinRoom join = 2;
    SendMessage send = 3;
  }
}

message JoinRoom {
  string room_id = 1;
  string nickname = 2;
}

message SendMessage {
  string room_id = 1;
  string text = 2;
}

message ChatEvent {
  // Empty for heartbeats not belonging to any command.
  string command_id = 1;
  oneof event {
    CommandAccepted accepted = 2;
    ChatMessage message = 3;
    Heartbeat heartbeat = 4;
    CommandRejected rejected = 5;
  }
}

message CommandAccepted { string detail = 1; }
message ChatMessage {
  string room_id = 1;
  string sender = 2;
  string text = 3;
}
message Heartbeat { int64 sequence = 1; }
message CommandRejected { string reason = 1; }
```

Assertions will rely on the contract:

- Each valid command has a unique `command_id` and receives a `CommandAccepted` carrying that same ID.
- `SendMessage` also produces a `ChatMessage` carrying the same ID so the client knows which command produced which message.
- `Heartbeat` is a proactive event; `command_id` is empty and sequence increases monotonically.
- The client can call `onCompleted()` to half-close the request stream; the server keeps emitting heartbeats until completing the response stream.

Do not assert that a heartbeat always appears before or after a specific ACK. gRPC preserves per-direction send order, but does not dictate interleaving between independent producers.

## 3. Sample Service: Command Responses and Heartbeats on One Response Stream

The service below stays small to keep the focus on testing. In Spring, `@Service` registers the implementation; the scheduler is injected and shared. Each RPC has its own state and lock so the command callback and scheduler do not write concurrently to the same observer.

```java
package com.example.chat;

import com.example.chat.v1.ChatCommand;
import com.example.chat.v1.ChatEvent;
import com.example.chat.v1.ChatMessage;
import com.example.chat.v1.ChatRoomGrpc;
import com.example.chat.v1.CommandAccepted;
import com.example.chat.v1.CommandRejected;
import com.example.chat.v1.Heartbeat;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class ChatRoomService extends ChatRoomGrpc.ChatRoomImplBase {
    private final ScheduledExecutorService scheduler;

    public ChatRoomService(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    @Override
    public StreamObserver<ChatCommand> converse(
            StreamObserver<ChatEvent> responseObserver) {
        ServerCallStreamObserver<ChatEvent> output =
                (ServerCallStreamObserver<ChatEvent>) responseObserver;
        Session session = new Session(output);
        output.setOnCancelHandler(session::cancel);
        session.start();

        return new StreamObserver<>() {
            @Override
            public void onNext(ChatCommand command) {
                session.handle(command);
            }

            @Override
            public void onError(Throwable error) {
                session.cancel();
            }

            @Override
            public void onCompleted() {
                // Half-close request direction; heartbeats may continue.
                session.inputCompleted();
            }
        };
    }

    private final class Session {
        private final ServerCallStreamObserver<ChatEvent> output;
        private ScheduledFuture<?> heartbeatJob;
        private long heartbeatSequence;
        private boolean inputDone;
        private boolean terminated;

        Session(ServerCallStreamObserver<ChatEvent> output) {
            this.output = output;
        }

        synchronized void start() {
            heartbeatJob = scheduler.scheduleAtFixedRate(
                    this::heartbeat, 40, 80, TimeUnit.MILLISECONDS);
        }

        synchronized void handle(ChatCommand command) {
            if (terminated || output.isCancelled()) {
                cancel();
                return;
            }
            if (command.getCommandId().isBlank()) {
                fail(Status.INVALID_ARGUMENT
                        .withDescription("command_id is required"));
                return;
            }

            switch (command.getActionCase()) {
                case JOIN -> {
                    emit(ChatEvent.newBuilder()
                            .setCommandId(command.getCommandId())
                            .setAccepted(CommandAccepted.newBuilder()
                                    .setDetail("Joined "
                                            + command.getJoin().getRoomId())
                                    .build())
                            .build());
                }
                case SEND -> {
                    emit(ChatEvent.newBuilder()
                            .setCommandId(command.getCommandId())
                            .setAccepted(CommandAccepted.newBuilder()
                                    .setDetail("Message received").build())
                            .build());
                    emit(ChatEvent.newBuilder()
                            .setCommandId(command.getCommandId())
                            .setMessage(ChatMessage.newBuilder()
                                    .setRoomId(command.getSend().getRoomId())
                                    .setSender("server")
                                    .setText(command.getSend().getText())
                                    .build())
                            .build());
                }
                case ACTION_NOT_SET -> emit(ChatEvent.newBuilder()
                        .setCommandId(command.getCommandId())
                        .setRejected(CommandRejected.newBuilder()
                                .setReason("Missing action").build())
                        .build());
            }
        }

        private synchronized void heartbeat() {
            if (terminated || output.isCancelled()) {
                cancel();
                return;
            }
            heartbeatSequence++;
            emit(ChatEvent.newBuilder()
                    .setHeartbeat(Heartbeat.newBuilder()
                            .setSequence(heartbeatSequence).build())
                    .build());
            if (heartbeatSequence == 4) {
                stopHeartbeat();
                finishIfReady();
            }
        }

        synchronized void inputCompleted() {
            inputDone = true;
            finishIfReady();
        }

        synchronized void cancel() {
            terminated = true;
            stopHeartbeat();
        }

        private void emit(ChatEvent event) {
            if (terminated || output.isCancelled()) {
                cancel();
                return;
            }
            try {
                output.onNext(event);
            } catch (RuntimeException error) {
                cancel();
            }
        }

        private void finishIfReady() {
            if (!terminated && inputDone && heartbeatSequence == 4) {
                terminated = true;
                stopHeartbeat();
                output.onCompleted();
            }
        }

        private void fail(Status status) {
            if (!terminated) {
                terminated = true;
                stopHeartbeat();
                output.onError(status.asRuntimeException());
            }
        }

        private void stopHeartbeat() {
            if (heartbeatJob != null) {
                heartbeatJob.cancel(false);
                heartbeatJob = null;
            }
        }
    }
}
```

In the example, heartbeats stop after four events. The server calls `output.onCompleted()` only when **both conditions** hold: the client has half-closed requests and four heartbeats have been emitted. Thus tests can prove that responses continue after the client stops sending.

## 4. Why Use an In-Process Server/Channel?

gRPC Java provides `InProcessServerBuilder` and `InProcessChannelBuilder` to run client and server in the same process without opening a TCP port. This lets you run integration tests for contracts, callbacks, half-close, and cancellation while still exercising the gRPC runtime.

Tests need the `grpc-inprocess` dependency at the same version as the rest of the gRPC Java libraries, along with JUnit 5. Do not hardcode separate versions in the lesson; use the version managed by your project's dependency management.

A JUnit 5 fixture:

```java
package com.example.chat;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class ChatRoomServiceTest {
    private Server server;
    private ManagedChannel channel;
    private ScheduledExecutorService scheduler;

    @BeforeEach
    void setUp() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        scheduler = Executors.newSingleThreadScheduledExecutor();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new ChatRoomService(scheduler))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void tearDown() throws Exception {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(2, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(2, TimeUnit.SECONDS);
        }
        if (scheduler != null) {
            scheduler.shutdownNow();
            scheduler.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
```

`directExecutor()` keeps the fixture small, easy to observe, and avoids spawning unnecessary gRPC threads. The scheduler still runs separately to generate heartbeats asynchronously. Hence the service must synchronize session state and all writes to the response observer.

The fixture instantiates the service directly to focus on RPC behavior. If you need to verify Spring component scanning, dependency injection, or real server configuration, add a separate integration test using a Spring context and inject the `ChatRoomService` bean; there is no need to boot the full application context in every protocol test.

## 5. Test: Sending Commands While Receiving Heartbeats

The most important test must prove the client does not wait for the server to stop responding before sending the next command. The test sends `JOIN`, waits for the first heartbeat, and then sends `SEND` while the response stream is still active. Afterward, the client half-closes and waits for the server to emit the remaining heartbeats and finish.

```java
import static org.junit.jupiter.api.Assertions.*;

import com.example.chat.v1.ChatCommand;
import com.example.chat.v1.ChatEvent;
import com.example.chat.v1.ChatRoomGrpc;
import com.example.chat.v1.JoinRoom;
import com.example.chat.v1.SendMessage;
import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void sendsCommandsWhileContinuousResponsesAreArriving() throws Exception {
    BlockingQueue<ChatEvent> received = new LinkedBlockingQueue<>();
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<ChatEvent> incoming = new StreamObserver<>() {
        @Override
        public void onNext(ChatEvent event) {
            received.add(event);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    };

    ChatRoomGrpc.ChatRoomStub stub = ChatRoomGrpc.newStub(channel);
    StreamObserver<ChatCommand> outgoing = stub.converse(incoming);

    outgoing.onNext(ChatCommand.newBuilder()
            .setCommandId("join-1")
            .setJoin(JoinRoom.newBuilder()
                    .setRoomId("engineering")
                    .setNickname("An")
                    .build())
            .build());

    // Collect responses until the server proactively emits the first heartbeat.
    List<ChatEvent> events = new ArrayList<>();
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
    boolean sawHeartbeat = false;
    while (!sawHeartbeat && System.nanoTime() < deadline) {
        ChatEvent event = received.poll(100, TimeUnit.MILLISECONDS);
        if (event != null) {
            events.add(event);
            sawHeartbeat = event.hasHeartbeat();
        }
    }
    assertTrue(sawHeartbeat, "Server must push heartbeat while stream is open");

    // Send a second command while the response direction is still running.
    outgoing.onNext(ChatCommand.newBuilder()
            .setCommandId("message-1")
            .setSend(SendMessage.newBuilder()
                    .setRoomId("engineering")
                    .setText("Hello everyone")
                    .build())
            .build());

    // Half-close requests; server must still emit the remaining heartbeats.
    outgoing.onCompleted();
    assertTrue(terminal.await(3, TimeUnit.SECONDS),
            "Server must end response after sending all heartbeats");
    received.drainTo(events);

    assertNull(failure.get(), "RPC must not end with an error");
    assertTrue(events.stream().anyMatch(event ->
            event.getEventCase() == ChatEvent.EventCase.ACCEPTED
                    && event.getCommandId().equals("join-1")));
    assertTrue(events.stream().anyMatch(event ->
            event.getEventCase() == ChatEvent.EventCase.ACCEPTED
                    && event.getCommandId().equals("message-1")));

    ChatEvent chatMessage = events.stream()
            .filter(event -> event.hasMessage()
                    && event.getCommandId().equals("message-1"))
            .findFirst()
            .orElseThrow();
    assertEquals("Hello everyone",
            chatMessage.getMessage().getText());

    List<Long> heartbeatSequences = new ArrayList<>();
    for (ChatEvent event : events) {
        if (event.hasHeartbeat()) {
            heartbeatSequences.add(event.getHeartbeat().getSequence());
        }
    }
    assertEquals(List.of(1L, 2L, 3L, 4L), heartbeatSequences);
}
```

This test verifies four properties:

- The server sends heartbeats without needing a corresponding command.
- The client sends a second command after receiving an initial response, proving both directions can operate simultaneously.
- Responses correlate back to the right command via `command_id`.
- Half-closing requests does not cut off responses; the server sends all heartbeats before completing the RPC.

The test does **not** require heartbeats to interleave before or after ACKs and chat messages in a specific order. The scheduler and request callbacks can race; what must be verified is that messages match their commands, heartbeat sequences are contiguous, and the terminal callback arrives only after emitted responses.

## 6. Additional Tests for Chat and Command Streams

A single main test cannot cover every scenario. Split tests by behavior so failures are easy to localize:

| Test case | Input/condition | Assertion |
| --- | --- | --- |
| Join room | `JOIN(room_id)` | `ACCEPTED` present with matching `command_id` and room |
| Send message | `SEND(room_id, text)` | ACK and `ChatMessage` carry matching ID and text |
| Multiple consecutive commands | Two or more commands on the same observer | Server processes all; no need to open a new RPC per command |
| Independent heartbeat | No new commands sent for a period | Heartbeats still arrive per contract |
| Invalid command | Missing action or invalid room | `REJECTED` with matching ID; stream continues if error is per-command |
| Duplicate command ID | Resend an active ID | Server enforces explicit duplicate policy |
| Half-close | Send commands then `outgoing.onCompleted()` | Remaining responses arrive followed by terminal `onCompleted()` |
| Cancel entire RPC | Client calls `ClientCallStreamObserver.cancel()` | Client receives terminal callback; server stops heartbeat publisher |
| Deadline | Set deadline shorter than stream duration | Client receives deadline status; server cleans up |
| Multiple clients | Two in-process channels or two calls | Session states, command IDs, and heartbeats do not mix |

For real chat, add broadcast tests: two clients join the same room, client A sends a message, and client B receives the event. Tests must verify room isolation: clients in other rooms must not receive the message. You can use a mock event publisher or test broker to drive broadcasts without depending on external systems.

## 7. Synchronizing Asynchronous Tests Without Flakiness

The gRPC async stub invokes callbacks when messages arrive. Tests must not assume `onNext()` has already run immediately after `outgoing.onNext()`. Use proper synchronization primitives:

- `BlockingQueue` to collect events and wait with a timeout.
- `CountDownLatch` to wait for terminal callbacks.
- `AtomicReference<Throwable>` to capture callback errors and assert after the test finishes.
- Controllable scheduler/clock when testing exact heartbeat timing or timeouts.

Avoid:

- `Thread.sleep(1000)` and assuming enough messages arrived.
- Asserting interleaving order between command ACKs and heartbeats from two different producers.
- Unbounded waits via `take()` or `await()` without timeouts; if the server fails, the test hangs.
- Sharing queues, latches, or state across tests without resetting.

Every test needs timeouts on both event waits and terminal waits. Even when an assertion fails, close the channel/server and scheduler in `@AfterEach` so background threads do not leak into subsequent tests.

## 8. Testing Cancellation and Background Resources

Beyond the happy path, prove that heartbeats stop when the client leaves the session. Use `ClientResponseObserver` to retain a reference to `ClientCallStreamObserver`:

```java
import io.grpc.stub.ClientCallStreamObserver;

AtomicReference<ClientCallStreamObserver<ChatCommand>> callRef =
        new AtomicReference<>();

ClientResponseObserver<ChatCommand, ChatEvent> observer =
        new ClientResponseObserver<>() {
    @Override
    public void beforeStart(
            ClientCallStreamObserver<ChatCommand> requestStream) {
        callRef.set(requestStream);
    }

    @Override public void onNext(ChatEvent event) { received.add(event); }
    @Override public void onError(Throwable error) { terminal.countDown(); }
    @Override public void onCompleted() { terminal.countDown(); }
};

StreamObserver<ChatCommand> outgoing = stub.converse(observer);
outgoing.onNext(joinCommand);
// After receiving the first heartbeat:
callRef.get().cancel("Client left room", null);
assertTrue(terminal.await(2, TimeUnit.SECONDS));
```

On the server, `setOnCancelHandler()` must cancel the scheduled future and close per-session subscriptions. To prove thorough cleanup, inject a test-only counter or mock publisher to verify zero ticks occur after cancellation; do not rely solely on the client receiving `onError`.

## 9. Verifying Spring Wiring and Real Environments

In-process tests prove the contract and gRPC behavior of the service implementation. They do not automatically prove that Spring scanned the right packages, created the right beans, applied interceptors, or configured TLS. For those parts, add an appropriate integration test layer:

- Boot the Spring context, inject the service bean, and verify the bean is registered.
- Test that interceptors attach metadata/tracing as configured.
- Use test certificates or an appropriate test environment to verify TLS/mTLS.
- Use dedicated channel/network tests for deadlines, keepalive, reconnects, and transport drop behavior.

You do not need to open TCP ports for every logic test. Use network tests only when the behavior under test depends on sockets, TLS, HTTP/2, or real server configuration.

## 10. Quality Checklist for a Chat Stream

| Group | Verification question |
| --- | --- |
| Contract | Does every event have a clear type and a command ID when relevant? |
| Full-duplex | Can the client send new commands while the response callback is receiving events? |
| Continuous response | Does the server push heartbeats/notices without requiring new requests? |
| Correlation | Do ACKs/messages return the matching command ID? |
| Ordering | Are sequences preserved within the same direction, without tests asserting unguaranteed interleaving? |
| Half-close | Can the client stop sending while continuing to receive responses until the server finishes? |
| Cancellation | Do cancel/deadline stop publishers and free state? |
| Isolation | Are two chat sessions prevented from sharing rooms, IDs, or events by mistake? |
| Reliability | Are queues bounded, callbacks timed, and terminal events fired only once? |

**Completion criteria:** tests prove multi-message command streams, correlated chat responses, continuous heartbeats while the client sends, proper half-close lifecycle, and cancellation cleanup. Test outcomes do not depend on arbitrary interleaving between the two directions.

### References

- [gRPC Java InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html): running a gRPC server in the same process for testing.
- [gRPC Java InProcessChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessChannelBuilder.html): creating an in-process channel.
- [gRPC Java StreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/StreamObserver.html): receive/send callbacks and terminal events.
- [gRPC Java ClientResponseObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientResponseObserver.html): accessing the call observer before starting exchange.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): integrating gRPC services/clients and configuration in Spring.
