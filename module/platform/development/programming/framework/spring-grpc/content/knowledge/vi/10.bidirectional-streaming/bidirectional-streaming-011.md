# Kiểm thử chat, command stream và phản hồi liên tục

## 1. Kiểm thử điều gì trong một bidi stream?

Một ứng dụng chat dùng **Spring gRPC** thường có một RPC sống trong suốt phiên: client gửi lệnh tham gia phòng, gửi tin nhắn hoặc rời phòng; server trả xác nhận, chuyển tiếp tin nhắn và chủ động phát heartbeat hoặc thông báo hệ thống. Hai phía gửi độc lập, vì vậy một bài kiểm thử chỉ gửi một request rồi chờ một response sẽ không chứng minh được hành vi song công.

Một bộ kiểm thử hữu ích cần chứng minh ba điều:

1. **Command stream:** client gửi được nhiều command trên cùng RPC; server xử lý và phản hồi đúng command ID.
2. **Chat/event stream:** server có thể phát message do command tạo ra và event chủ động không gắn với command cụ thể.
3. **Phản hồi liên tục:** client tiếp tục nhận heartbeat/event trong khi vẫn gửi command; half-close chiều request không làm response stream dừng sớm.

Bài này tập trung vào cách kiểm thử các hành vi đó bằng gRPC Java và in-process server/channel. Cách làm phù hợp cho service được đăng ký trong Spring: có thể kiểm tra logic RPC trực tiếp bằng service bean, rồi kiểm tra riêng việc Spring tạo và đăng ký bean ở một bài kiểm thử context.

## 2. Hợp đồng nhỏ để kiểm thử

Dùng một contract có command ID để định tuyến phản hồi:

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
  // Rỗng với heartbeat không thuộc command nào.
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

Các assertion sẽ dựa trên contract:

- Mỗi command hợp lệ có `command_id` duy nhất và nhận `CommandAccepted` mang lại đúng ID.
- `SendMessage` tạo thêm một `ChatMessage` mang cùng ID, để client biết message nào là kết quả của command nào.
- `Heartbeat` là event chủ động; `command_id` rỗng và sequence tăng dần.
- Client có thể gọi `onCompleted()` để half-close request stream; server vẫn phát heartbeat cho tới khi hoàn tất response stream.

Không kiểm tra rằng heartbeat luôn xuất hiện trước hay sau một ACK cụ thể. gRPC giữ thứ tự trong từng chiều theo thứ tự gửi, nhưng không quy định lịch xen kẽ giữa các producer độc lập.

## 3. Service mẫu: command response và heartbeat cùng một response stream

Service dưới đây giữ ví dụ nhỏ để tập trung vào kiểm thử. Trong Spring, `@Service` đăng ký implementation; scheduler được inject và dùng chung. Mỗi RPC có state và khóa riêng để command callback và scheduler không ghi đồng thời vào cùng observer.

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
                // Half-close request direction; heartbeat may continue.
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
                        .withDescription("command_id bắt buộc"));
                return;
            }

            switch (command.getActionCase()) {
                case JOIN -> {
                    emit(ChatEvent.newBuilder()
                            .setCommandId(command.getCommandId())
                            .setAccepted(CommandAccepted.newBuilder()
                                    .setDetail("Đã tham gia "
                                            + command.getJoin().getRoomId())
                                    .build())
                            .build());
                }
                case SEND -> {
                    emit(ChatEvent.newBuilder()
                            .setCommandId(command.getCommandId())
                            .setAccepted(CommandAccepted.newBuilder()
                                    .setDetail("Đã nhận tin nhắn").build())
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
                                .setReason("Thiếu action").build())
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

Trong ví dụ, heartbeat dừng sau bốn event. Server chỉ gọi `output.onCompleted()` khi **cả hai điều kiện** đúng: client đã half-close request và bốn heartbeat đã được phát. Nhờ vậy test có thể chứng minh response tiếp tục sau khi client ngừng gửi.

## 4. Vì sao dùng in-process server/channel?

gRPC Java cung cấp `InProcessServerBuilder` và `InProcessChannelBuilder` để chạy client/server trong cùng process, không cần mở TCP port. Đây là cách kiểm thử integration cho contract, callback, half-close và cancellation mà vẫn đi qua gRPC runtime.

Test cần dependency `grpc-inprocess` cùng phiên bản với các thư viện gRPC Java còn lại và JUnit 5. Không hard-code version riêng trong bài; dùng version đã được quản lý bởi dependency management của dự án.

Một fixture JUnit 5:

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

`directExecutor()` giúp fixture nhỏ, dễ quan sát và tránh tạo thêm thread gRPC không cần thiết. Scheduler vẫn chạy riêng để tạo heartbeat bất đồng bộ. Vì vậy service cần đồng bộ state và mọi lần ghi vào response observer theo từng phiên.

Fixture khởi tạo service trực tiếp để tập trung vào hành vi RPC. Nếu cần xác minh Spring component scanning, dependency injection hoặc cấu hình server thực tế, bổ sung một integration test dùng Spring context và inject bean `ChatRoomService`; không cần đưa toàn bộ application context vào mọi test protocol.

## 5. Test: gửi command trong khi đang nhận heartbeat

Test quan trọng nhất phải chứng minh client không đợi server ngừng phản hồi mới gửi command tiếp theo. Test gửi `JOIN`, đợi heartbeat đầu tiên, rồi gửi `SEND` khi response stream vẫn đang hoạt động. Sau đó client half-close và đợi server gửi nốt các heartbeat rồi kết thúc.

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

    // Thu thập response cho tới khi server chủ động gửi heartbeat đầu tiên.
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
    assertTrue(sawHeartbeat, "Server phải push heartbeat khi stream đang mở");

    // Gửi command thứ hai trong khi response direction vẫn đang chạy.
    outgoing.onNext(ChatCommand.newBuilder()
            .setCommandId("message-1")
            .setSend(SendMessage.newBuilder()
                    .setRoomId("engineering")
                    .setText("Xin chào mọi người")
                    .build())
            .build());

    // Half-close request; server vẫn phải gửi các heartbeat còn lại.
    outgoing.onCompleted();
    assertTrue(terminal.await(3, TimeUnit.SECONDS),
            "Server phải kết thúc response sau khi đã gửi đủ heartbeat");
    received.drainTo(events);

    assertNull(failure.get(), "RPC không được kết thúc bằng lỗi");
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
    assertEquals("Xin chào mọi người",
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

Test này xác minh bốn thuộc tính:

- Server gửi heartbeat mà không cần một command tương ứng.
- Client gửi command thứ hai sau khi đã nhận response đầu tiên, chứng minh hai chiều có thể hoạt động cùng lúc.
- Response được liên kết với đúng command bằng `command_id`.
- Half-close request không cắt response; server gửi đủ heartbeat rồi mới hoàn tất RPC.

Test **không** yêu cầu heartbeat phải xen giữa ACK và chat message theo một thứ tự cụ thể. Scheduler và request callback có thể tranh lịch; điều cần xác minh là các message thuộc đúng command, sequence heartbeat liên tục và terminal callback chỉ đến sau những response đã phát.

## 6. Các test bổ sung cho chat và command stream

Một test chính không đủ bao phủ mọi tình huống. Nên chia nhỏ theo hành vi để lỗi dễ định vị:

| Test case | Dữ liệu/điều kiện | Assertion |
| --- | --- | --- |
| Tham gia phòng | `JOIN(room_id)` | Có `ACCEPTED` với đúng `command_id` và room |
| Gửi tin nhắn | `SEND(room_id, text)` | Có ACK và `ChatMessage` mang đúng ID, nội dung |
| Nhiều command liên tiếp | Hai hoặc nhiều command trên cùng observer | Server xử lý đủ; không cần mở RPC mới cho từng command |
| Heartbeat độc lập | Không gửi command mới trong một khoảng thời gian | Vẫn nhận heartbeat theo contract |
| Command lỗi | Thiếu action hoặc room không hợp lệ | Có `REJECTED` đúng ID; stream tiếp tục nếu lỗi chỉ ở command |
| Command ID trùng | Gửi lại ID đang hoạt động | Server áp dụng chính sách duplicate rõ ràng |
| Half-close | Gửi command rồi `outgoing.onCompleted()` | Nhận response còn lại và terminal `onCompleted()` |
| Cancel toàn RPC | Client gọi `ClientCallStreamObserver.cancel()` | Client nhận terminal callback; server dừng heartbeat publisher |
| Deadline | Đặt deadline ngắn hơn thời gian stream | Client nhận status deadline; server cleanup |
| Nhiều client | Hai in-process channel hoặc hai call | State, command ID và heartbeat của các phiên không trộn lẫn |

Với chat thật, bổ sung kiểm thử broadcast: hai client tham gia cùng room, client A gửi message và client B nhận được event. Test phải kiểm tra room isolation: client ở room khác không nhận message. Có thể dùng một event publisher giả hoặc broker test để điều khiển broadcast mà không phụ thuộc hệ thống bên ngoài.

## 7. Đồng bộ test bất đồng bộ mà không tạo flaky test

gRPC async stub gọi callback khi message đến. Test không được giả định `onNext()` đã chạy ngay sau `outgoing.onNext()`. Dùng công cụ đồng bộ phù hợp:

- `BlockingQueue` để nhận event và chờ với timeout.
- `CountDownLatch` để đợi terminal callback.
- `AtomicReference<Throwable>` để lưu lỗi từ callback và kiểm tra sau khi test hoàn tất.
- Scheduler/clock có thể điều khiển nếu cần kiểm tra chính xác thời điểm heartbeat hoặc timeout.

Tránh:

- `Thread.sleep(1000)` rồi giả định đủ message đã đến.
- Assertion về thứ tự xen kẽ giữa command ACK và heartbeat do hai producer khác nhau.
- Chờ vô hạn bằng `take()` hoặc `await()` không timeout; nếu server lỗi, test sẽ treo.
- Chia sẻ queue, latch hoặc state giữa nhiều test mà không reset.

Mọi test cần timeout ở cả bước đợi event và bước đợi terminal. Khi assertion thất bại, đóng channel/server và scheduler trong `@AfterEach` để không giữ thread nền cho test kế tiếp.

## 8. Kiểm thử cancellation và tài nguyên nền

Ngoài luồng thành công, cần chứng minh heartbeat dừng khi client rời phiên. Dùng `ClientResponseObserver` để giữ tham chiếu `ClientCallStreamObserver`:

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
// Sau khi nhận heartbeat đầu tiên:
callRef.get().cancel("Client rời phòng", null);
assertTrue(terminal.await(2, TimeUnit.SECONDS));
```

Ở server, `setOnCancelHandler()` phải hủy scheduled future và đóng subscription theo phiên. Nếu cần chứng minh cleanup triệt để, inject một bộ đếm test-only hoặc publisher giả để xác minh không còn tick sau cancellation; đừng chỉ dựa vào việc client đã nhận `onError`.

## 9. Kiểm tra Spring wiring và môi trường thật

In-process test chứng minh contract và hành vi gRPC của service implementation. Nó không tự chứng minh Spring đã scan đúng package, tạo đúng bean, áp dụng interceptor hay cấu hình TLS. Với các phần đó, thêm một lớp integration test phù hợp:

- Khởi tạo Spring context, inject service bean và xác minh bean được đăng ký.
- Kiểm tra interceptor gắn metadata/tracing theo cấu hình.
- Dùng test certificate hoặc môi trường test phù hợp để kiểm tra TLS/mTLS.
- Dùng channel/network test riêng cho deadline, keepalive, reconnect và hành vi khi transport đứt.

Không cần mở cổng TCP cho mọi test logic. Chỉ dùng network test khi điều cần kiểm tra phụ thuộc vào socket, TLS, HTTP/2 hoặc cấu hình server thực tế.

## 10. Checklist chất lượng cho một chat stream

| Nhóm | Câu hỏi xác minh |
| --- | --- |
| Contract | Mỗi event có loại rõ ràng và command ID khi có liên quan? |
| Song công | Client gửi command mới trong lúc callback response đang nhận event? |
| Continuous response | Server push heartbeat/notice không cần request mới? |
| Correlation | ACK/message trả về đúng command ID? |
| Thứ tự | Sequence trong cùng chiều được giữ; test không áp đặt thứ tự xen kẽ không được đảm bảo? |
| Half-close | Client ngừng gửi nhưng vẫn nhận response tới khi server hoàn tất? |
| Cancellation | Cancel/deadline dừng publisher và giải phóng state? |
| Isolation | Hai phiên chat không chia sẻ nhầm room, ID hoặc event? |
| Reliability | Queue có giới hạn, callback có timeout và terminal event chỉ xảy ra một lần? |

**Tiêu chí hoàn thành:** test chứng minh được command stream nhiều message, chat response có correlation, heartbeat liên tục trong lúc client gửi, half-close đúng vòng đời và cancellation cleanup. Kết quả test không phụ thuộc vào lịch xen kẽ ngẫu nhiên giữa hai hướng.

### Tài liệu tham khảo

- [gRPC Java InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html): dựng server gRPC trong cùng process cho kiểm thử.
- [gRPC Java InProcessChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessChannelBuilder.html): tạo channel in-process.
- [gRPC Java StreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/StreamObserver.html): callback nhận/gửi và terminal event.
- [gRPC Java ClientResponseObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientResponseObserver.html): truy cập call observer trước khi bắt đầu trao đổi.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC service/client và cấu hình trong Spring.
