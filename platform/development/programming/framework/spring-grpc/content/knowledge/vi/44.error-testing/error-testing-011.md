# Test lỗi sau một phần streaming

Trong streaming RPC, server hoặc client có thể đã gửi và nhận một số message trước khi call kết thúc bằng lỗi. Khi đó, test không chỉ kiểm tra status cuối mà còn phải xác minh những message nào đã được quan sát, thứ tự của chúng, callback terminal nào được gọi và tài nguyên có được giải phóng hay không. Một lỗi đến sau message thứ hai có semantics khác với lỗi xảy ra trước message đầu tiên.

**Test lỗi sau một phần streaming** là kiểm thử hành vi của gRPC khi một stream đã trao đổi một phần dữ liệu rồi kết thúc bằng status lỗi, cancellation hoặc deadline. Bài thuộc chương **Error testing** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là kiểm tra partial messages và terminal status theo từng kiểu RPC, kiểm soát callback bất đồng bộ, phân biệt application error với transport failure, và thiết kế cursor/idempotency khi cần phục hồi phần dữ liệu chưa xử lý.

## 1. Một stream có thể kết thúc sau khi đã giao dữ liệu

Một gRPC streaming call có hai phần cần quan sát:

1. Các message được trao đổi trong quá trình stream.
2. Kết quả terminal: hoàn tất bình thường, lỗi hoặc cancellation.

Ví dụ server-streaming:

~~~text
Client                         Server
  |                               |
  |---- Watch(request) ---------->|
  |<--- Event(sequence=1) ---------|
  |<--- Event(sequence=2) ---------|
  |<--- DATA_LOSS ----------------|
  |                               |
~~~

Client đã nhận hai event trước khi nhận lỗi DATA_LOSS. Hai event đó đã được giao tới callback onNext; status cuối không xóa những gì client đã quan sát. Ứng dụng phải quyết định có giữ lại partial result, đánh dấu operation không hoàn chỉnh hay phục hồi từ cursor.

Một RPC có đúng một terminal outcome. Với StreamObserver, terminal callback là onError hoặc onCompleted; sau một trong hai callback, không được có thêm onNext hoặc terminal callback thứ hai. Test cần phát hiện vi phạm lifecycle này.

## 2. Phân biệt bốn kiểu RPC

| Kiểu RPC | Luồng message | Lỗi sau một phần dữ liệu được quan sát ở đâu? |
| --- | --- | --- |
| Unary | Một request, một response | Thông thường không có response message một phần; client nhận một status/error. |
| Server-streaming | Một request, nhiều response | Client có thể đã nhận một số response qua onNext trước onError. |
| Client-streaming | Nhiều request, một response | Server có thể đã xử lý một số request; client nhận lỗi thay vì response cuối. |
| Bidirectional streaming | Nhiều request, nhiều response | Cả hai phía có thể đã trao đổi một phần message trước terminal error. |

Test phải khớp với semantics của method. Không dùng một test server-streaming để kết luận client-streaming hoặc bidirectional có cùng hành vi. Với client-streaming, request message đã gửi không đồng nghĩa server đã xử lý hoặc commit chúng. Với bidirectional, hai hướng có tiến độ riêng và có thể quan sát số message khác nhau tại thời điểm lỗi.

## 3. Những điều cần assert sau partial failure

Một test tốt thường xác minh:

- Số message client đã nhận hoặc server đã xử lý trước lỗi.
- Thứ tự message và sequence/cursor nếu protocol có định nghĩa.
- Status code và error details/trailers cần thiết.
- onError được gọi đúng một lần; onCompleted không được gọi sau lỗi.
- Không có onNext sau terminal callback.
- Cancellation được truyền tới handler và công việc nền được dừng.
- Queue, timer, listener và resource gắn với stream được giải phóng.
- Không có retry/replay làm lặp message hoặc side effect ngoài contract.

Đừng chỉ assert rằng client nhận StatusRuntimeException. Nếu server đã gửi hai response trước lỗi, bỏ qua assertion về hai response đó sẽ không kiểm tra được phần quan trọng nhất của tình huống.

## 4. Tạo server-streaming service lỗi sau hai message

Ví dụ service gửi hai event rồi kết thúc bằng DATA_LOSS:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class PartialWatchService
        extends EventServiceGrpc.EventServiceImplBase {

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<Event> responseObserver) {

        responseObserver.onNext(Event.newBuilder()
                .setSequence(1)
                .setPayload("first")
                .build());

        responseObserver.onNext(Event.newBuilder()
                .setSequence(2)
                .setPayload("second")
                .build());

        responseObserver.onError(
                Status.DATA_LOSS
                        .withDescription("event log is inconsistent")
                        .asRuntimeException());
    }
}
~~~

Đây là fixture test có hành vi xác định. Service production có thể phát hiện lỗi khi đọc broker, giải mã event hoặc xác minh checksum; khi đó nó phải chọn status phù hợp và kết thúc stream đúng một lần.

Không gọi onCompleted() sau onError(). Cũng không bắt exception rồi tiếp tục gửi message như thể stream vẫn hoạt động. Sau terminal signal, listener/observer đã kết thúc.

## 5. Test server-streaming: giữ partial messages và kiểm tra terminal status

Client bất đồng bộ nhận từng message qua onNext, sau đó nhận terminal callback. Dùng CountDownLatch thay vì Thread.sleep() để đồng bộ test:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class PartialServerStreamTest {

    @Test
    void receivesMessagesBeforeTerminalError() throws Exception {
        List<Long> sequences = new CopyOnWriteArrayList<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicInteger terminalCallbacks = new AtomicInteger();
        AtomicInteger completedCallbacks = new AtomicInteger();
        CountDownLatch terminal = new CountDownLatch(1);

        EventServiceGrpc.EventServiceStub stub = testStub();
        stub.watch(WatchRequest.getDefaultInstance(),
                new StreamObserver<>() {
                    @Override
                    public void onNext(Event event) {
                        sequences.add(event.getSequence());
                    }

                    @Override
                    public void onError(Throwable error) {
                        terminalCallbacks.incrementAndGet();
                        failure.set(error);
                        terminal.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        terminalCallbacks.incrementAndGet();
                        completedCallbacks.incrementAndGet();
                        terminal.countDown();
                    }
                });

        assertTrue(terminal.await(2, TimeUnit.SECONDS));
        assertEquals(List.of(1L, 2L), sequences);
        assertEquals(1, terminalCallbacks.get());
        assertEquals(0, completedCallbacks.get());
        assertNotNull(failure.get());
        assertEquals(
                Status.Code.DATA_LOSS,
                Status.fromThrowable(failure.get()).getCode());
    }
}
~~~

testStub() là helper tạo channel kết nối tới fixture server. CopyOnWriteArrayList giúp test an toàn khi callback chạy trên transport thread khác. Với throughput test lớn, có thể dùng queue concurrent phù hợp hơn; ở đây mục tiêu là làm rõ assertion.

Test chứng minh hai response đã được quan sát trước terminal DATA_LOSS, chỉ có một terminal callback và không có onCompleted. Deadline chờ latch là hàng rào để test không treo vô hạn nếu server không gửi terminal event.

## 6. Thứ tự message và terminal error

gRPC bảo toàn thứ tự message trong một stream. Khi server gọi onNext lần lượt rồi onError, client sẽ quan sát các message đã được gửi trước terminal status theo thứ tự stream. Tuy nhiên, không nên dựa vào thứ tự log giữa nhiều thread hoặc giữa các RPC khác nhau.

Nếu message có sequence number, test nên assert cả nội dung và thứ tự:

~~~java
assertEquals(List.of(10L, 11L, 12L), receivedSequences);
assertEquals(Status.Code.DATA_LOSS, terminalStatus);
~~~

Nếu test chỉ kiểm tra receivedSequences.size() == 3, nó có thể bỏ sót message trùng hoặc sai thứ tự. Với event stream, sequence/cursor là một phần contract giúp client phát hiện gap và duplicate.

Không giả định mọi message mà server đã gọi onNext đều đã được application client xử lý trước khi network bị reset. Với application status kết thúc bình thường qua gRPC transport, thứ tự message và terminal trailers được duy trì; với lỗi transport đột ngột, một message đang in-flight có thể chưa tới callback client. Test transport failure phải cho phép phân biệt message đã quan sát với message server mới chỉ gửi.

## 7. Test client-streaming: server lỗi sau khi nhận một phần request

Trong client-streaming, client gửi nhiều request message qua một StreamObserver. Server có thể xử lý một số message rồi phát lỗi thay vì trả response tổng kết:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class PartialUploadService
        extends UploadServiceGrpc.UploadServiceImplBase {

    final AtomicInteger received = new AtomicInteger();
    final AtomicBoolean terminal = new AtomicBoolean();

    @Override
    public StreamObserver<UploadChunk> upload(
            StreamObserver<UploadReply> responseObserver) {

        return new StreamObserver<>() {
            @Override
            public void onNext(UploadChunk chunk) {
                int count = received.incrementAndGet();
                if (count == 2 && terminal.compareAndSet(false, true)) {
                    responseObserver.onError(
                            Status.RESOURCE_EXHAUSTED
                                    .withDescription("upload quota reached")
                                    .asRuntimeException());
                }
            }

            @Override
            public void onError(Throwable error) {
                // Dừng xử lý và giải phóng state của upload.
                terminal.set(true);
            }

            @Override
            public void onCompleted() {
                if (terminal.compareAndSet(false, true)) {
                    responseObserver.onNext(
                            UploadReply.newBuilder()
                                    .setAcceptedChunks(received.get())
                                    .build());
                    responseObserver.onCompleted();
                }
            }
        };
    }
}
~~~

Khi server phát lỗi, client nhận terminal onError ở response observer; nó không nhận UploadReply tổng kết. Server counter cho biết handler đã nhận hai chunk. Không khẳng định chunk thứ ba chắc chắn đã tới server chỉ vì client đã gọi requestObserver.onNext(chunk3) trước khi quan sát lỗi; send call là thao tác đưa message vào client call, không phải application acknowledgement từ server.

Trong fixture thật, cần có guard để server không gửi onCompleted sau onError; ví dụ trên minh họa nhánh lỗi sau chunk thứ hai và nhánh hoàn tất nếu stream kết thúc sớm.

## 8. Test client-streaming ở phía caller

Client test cần đợi terminal response và kiểm tra status:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

AtomicReference<Throwable> failure = new AtomicReference<>();
AtomicInteger responseCount = new AtomicInteger();
CountDownLatch terminal = new CountDownLatch(1);

StreamObserver<UploadReply> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadReply reply) {
                responseCount.incrementAndGet();
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

StreamObserver<UploadChunk> requestObserver =
        asyncStub.upload(responseObserver);

requestObserver.onNext(chunk(1));
requestObserver.onNext(chunk(2));

assertTrue(terminal.await(2, TimeUnit.SECONDS));
assertNotNull(failure.get());
assertEquals(0, responseCount.get());
assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        Status.fromThrowable(failure.get()).getCode());
assertEquals(2, service.received.get());
~~~

Ví dụ bỏ qua việc gửi chunk tiếp theo sau khi server đã báo lỗi. Trong test race condition, client có thể đã enqueue thêm request message trước khi nhận terminal callback; khi đó hãy assert những gì server thực sự nhận và không coi số lần gọi onNext ở client là số message đã commit ở server.

## 9. Test bidirectional streaming: hai hướng có tiến độ riêng

Bidirectional stream cho phép client và server gửi message độc lập. Một phía có thể đã nhận response trong khi phía kia đang gửi request tiếp theo. Khi lỗi xảy ra, test cần ghi nhận:

- Số request message server đã xử lý.
- Số response message client đã nhận.
- Sequence/correlation giữa request và response.
- Status cuối và terminal callback.
- Cancellation/cleanup ở cả hai phía.

Ví dụ server trả lời hai request đầu rồi lỗi:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class PartialChatService
        extends ChatGrpc.ChatImplBase {

    @Override
    public StreamObserver<ChatRequest> chat(
            StreamObserver<ChatReply> responseObserver) {

        AtomicInteger received = new AtomicInteger();
        AtomicBoolean terminal = new AtomicBoolean();
        return new StreamObserver<>() {
            @Override
            public void onNext(ChatRequest request) {
                int index = received.incrementAndGet();
                if (index <= 2 && !terminal.get()) {
                    responseObserver.onNext(
                            ChatReply.newBuilder()
                                    .setSequence(index)
                                    .setText("ack-" + index)
                                    .build());
                }
                if (index == 2 && terminal.compareAndSet(false, true)) {
                    responseObserver.onError(
                            Status.INTERNAL
                                    .withDescription("chat stream failed")
                                    .asRuntimeException());
                }
            }

            @Override
            public void onError(Throwable error) {
                // Cleanup session state.
                terminal.set(true);
            }

            @Override
            public void onCompleted() {
                if (terminal.compareAndSet(false, true)) {
                    responseObserver.onCompleted();
                }
            }
        };
    }
}
~~~

Test client ghi lại response sequence và terminal status. Không assert server đã nhận mọi request mà client đã gửi; sau khi server kết thúc stream, các message đang chờ có thể không được xử lý. Nếu protocol yêu cầu xác nhận từng request, server cần gửi application acknowledgement chứa sequence/event ID.

## 10. In-process test và transport-level test

In-process transport thích hợp để kiểm thử logic service và thứ tự callback ở mức gRPC API. Nó nhanh, deterministic và không cần mở TCP socket. Tuy nhiên, nó không kiểm tra đầy đủ HTTP/2 framing, TLS, proxy timeout, TCP reset hoặc lỗi mạng thực tế.

| Mục tiêu | Kiểu test nên dùng |
| --- | --- |
| Server gọi onNext rồi onError | In-process gRPC test. |
| Status code/trailers từ service | In-process test; thêm Netty loopback nếu cần xác minh transport. |
| Client cancel sau khi nhận một phần response | In-process test cho logic; Netty loopback cho transport behavior. |
| TCP reset giữa các message | Netty loopback hoặc test proxy/network fault. |
| TLS handshake lỗi khi stream đang hoạt động | Netty TLS test hoặc môi trường integration tương đương. |
| Proxy idle timeout/maximum stream duration | Test qua đúng proxy/gateway cấu hình production. |

Không dùng in-process test để kết luận hành vi khi TCP connection bị reset. Cũng không cần dùng network fault injection cho mọi status mapping test; chọn tầng test theo điều đang muốn chứng minh.

## 11. Dùng in-process fixture cho status sau partial messages

Một fixture tối giản có thể tạo server/channel trong cùng process:

~~~java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(new PartialWatchService())
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    EventServiceGrpc.EventServiceStub stub =
            EventServiceGrpc.newStub(channel);
    // Gọi method và đợi terminal callback bằng CountDownLatch.
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
~~~

directExecutor() làm callback có thể chạy ngay trên thread gọi; không được giả định callback luôn chạy trên thread riêng. Vẫn nên dùng collection thread-safe nếu test có thể chuyển sang Netty hoặc executor khác. Fixture phải đóng channel và server trong finally để không rò tài nguyên.

## 12. Cancellation sau khi client đã nhận một phần dữ liệu

Client có thể quyết định dừng stream sau một số message, ví dụ người dùng hủy download hoặc UI không còn cần event. Với async stub, dùng ClientResponseObserver để lấy ClientCallStreamObserver trong beforeStart và gọi cancel:

~~~java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
        new AtomicReference<>();
CountDownLatch twoMessages = new CountDownLatch(2);

ClientResponseObserver<WatchRequest, Event> observer =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<WatchRequest> requestStream) {
                callRef.set(requestStream);
            }

            @Override
            public void onNext(Event event) {
                twoMessages.countDown();
            }

            @Override
            public void onError(Throwable error) {
                // Cancellation thường kết thúc phía client bằng CANCELLED.
            }

            @Override
            public void onCompleted() {
                // Server có thể hoàn tất trước khi client cancel.
            }
        };

asyncStub.watch(watchRequest, observer);
assertTrue(twoMessages.await(2, TimeUnit.SECONDS));
callRef.get().cancel("client no longer needs events", null);
~~~

Test server cần quan sát cancellation bằng ServerCallStreamObserver.setOnCancelHandler() hoặc gRPC Context.CancellationListener, sau đó xác minh queue/subscription/timer đã được cleanup. Vì race giữa message thứ hai và terminal callback là có thể xảy ra, test nên dùng fixture giữ stream mở sau hai message hoặc đồng bộ bằng latch để bảo đảm client cancel trước khi server tự kết thúc.

Không coi client cancel là một lỗi nghiệp vụ của server. Client có thể đã nhận đủ dữ liệu cần thiết cho use case của nó và chủ động đóng stream.

## 13. Deadline hết sau partial messages

Deadline áp dụng cho toàn RPC. Server-streaming có thể gửi một số response rồi call kết thúc vì deadline:

~~~text
Client deadline: 500 ms

0 ms     request accepted
120 ms   response sequence=1
240 ms   response sequence=2
500 ms   deadline expires
         client terminal status: DEADLINE_EXCEEDED
~~~

Test nên cấu hình server phát message theo lịch có kiểm soát hoặc dùng fake dependency có latch. Không dùng Thread.sleep() dài để đoán message nào đến trước deadline. Dùng deadline đủ rộng cho CI, đồng bộ message bằng latch và xác minh terminal status.

Status quan sát có thể khác theo phía: client thường nhận DEADLINE_EXCEEDED, còn server quan sát cancellation khi deadline hết. Server không nên tiếp tục đọc broker hoặc thực hiện công việc nền sau khi call đã bị hủy nếu công việc đó chỉ phục vụ stream.

## 14. Partial result không tự động được rollback

Khi server đã gửi một response message và client đã nhận, gRPC không thể thu hồi message đó chỉ vì stream kết thúc bằng lỗi. Với client-streaming, server có thể đã xử lý một phần request trước khi lỗi. Với bidirectional, cả hai phía có thể đã tạo side effect.

Ứng dụng phải xác định semantics:

- **Partial result hợp lệ:** client giữ phần dữ liệu đã nhận và đánh dấu operation chưa hoàn tất.
- **All-or-nothing:** server staging dữ liệu và chỉ commit khi stream kết thúc thành công; client không coi message trung gian là commit cuối.
- **Resumable stream:** message có sequence/cursor và client tiếp tục từ checkpoint đã xác nhận.
- **At-least-once:** reconnect có thể gửi lại event; client deduplicate bằng event ID hoặc sequence.

Nếu cần all-or-nothing cho upload, không commit side effect nghiệp vụ ở từng onNext trừ khi có transaction/staging và cleanup rõ. Nếu cần partial progress, response nên thể hiện sequence/progress và terminal failure để client không nhầm dữ liệu tạm thời với kết quả hoàn tất.

## 15. Retry sau partial streaming

Không giả định gRPC tự phát lại một stream sau khi đã có dữ liệu được chuyển tới ứng dụng. Retry commitment phụ thuộc trạng thái call, response headers, retry buffer và semantics của RPC. Khi response headers đã tới client, call đã committed và retry policy không tiếp tục replay attempt đó.

Với streaming workflow, thiết kế phục hồi ở tầng ứng dụng:

1. Mỗi event có event ID và sequence/cursor ổn định.
2. Client lưu checkpoint sau khi xử lý dữ liệu theo durability requirement.
3. Khi stream lỗi, client mở RPC mới từ cursor đã xác nhận.
4. Server có thể gửi lại event chưa được xác nhận.
5. Client deduplicate và chỉ commit business effect một lần.

Test cần chứng minh reconnect không bỏ sót event và không tạo side effect trùng. Đây là resume protocol, không phải automatic retry của gRPC.

## 16. Kiểm tra trailers và error details

Status cuối có thể đi kèm trailers chứa metadata hoặc rich error details. Nếu contract yêu cầu client phân biệt lỗi tạm thời, quota hoặc cursor hết hạn, hãy kiểm tra cả status code và error detail đã chuẩn hóa.

Không đưa payload nhạy cảm vào status description. Error detail nên chứa mã lỗi, retry hint hoặc checkpoint đã được phép, không chứa request/response message thô. Test cần xác minh:

- Status code đúng.
- Description không làm lộ dữ liệu.
- Trailer keys nằm trong allowlist.
- Client parse được error detail đã định nghĩa.
- Không có onCompleted sau onError.

## 17. Ma trận kiểm thử partial streaming failure

| Trường hợp | Setup | Assertion chính |
| --- | --- | --- |
| Server-streaming: lỗi sau hai event | Server onNext hai lần rồi onError(DATA_LOSS). | Client nhận sequence 1, 2 theo thứ tự; final status DATA_LOSS. |
| Server-streaming: lỗi trước event đầu | Server onError ngay. | Không có onNext; terminal error đúng một lần. |
| Client-streaming: server lỗi sau hai chunk | Server đếm hai request rồi trả RESOURCE_EXHAUSTED. | Client không nhận response tổng kết; server đã xử lý hai chunk. |
| Bidirectional: lỗi sau hai ack | Server trả hai response rồi kết thúc INTERNAL. | Client nhận hai ack đúng thứ tự và terminal error. |
| Client cancel sau hai event | Client cancel khi đã nhận hai message. | Server nhận cancellation và cleanup session. |
| Deadline sau partial result | Deadline hết khi stream đang chạy. | Client nhận DEADLINE_EXCEEDED; server dừng công việc. |
| Transport reset | Proxy/socket đóng sau một phần message. | Chỉ assert message thực sự quan sát được; phân biệt transport failure. |
| Reconnect/resume | Stream lỗi sau cursor N. | Client tiếp tục từ checkpoint, xử lý duplicate idempotently. |
| Terminal callback lifecycle | Server lỗi hoặc hoàn tất. | Chỉ một terminal callback; không có message sau terminal. |

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test chỉ kiểm tra status | Bỏ qua message đã nhận trước lỗi. | Assert partial payload, sequence và terminal status. |
| Gọi onCompleted sau onError | Không quản lý terminal lifecycle. | Dùng terminal guard và một nhánh kết thúc duy nhất. |
| Cho rằng client đã gửi là server đã nhận | Nhầm onNext phía client với application acknowledgement. | Đếm message ở server hoặc dùng ack protocol. |
| Test transport reset bằng in-process transport | In-process không mô phỏng TCP/HTTP2 failure. | Dùng Netty loopback hoặc proxy fault injection. |
| Test phụ thuộc sleep | Race giữa callback và assertion. | Dùng latch, queue và deadline hữu hạn. |
| Client cancel nhưng server vẫn xử lý | Không propagate cancellation tới broker/task. | Đăng ký cancel handler và cleanup idempotent. |
| Retry làm lặp event/side effect | Không có cursor hoặc idempotency. | Resume protocol, event ID và deduplication. |
| Partial response bị coi là hoàn tất | Không có terminal state/progress contract. | Phân biệt partial result với committed result. |

## 19. Bài tập thực hành

1. Viết server-streaming fixture gửi hai event rồi kết thúc bằng DATA_LOSS; assert cả sequence và terminal status.
2. Viết client-streaming fixture nhận hai chunk rồi trả RESOURCE_EXHAUSTED; xác minh không có response tổng kết.
3. Viết bidirectional fixture trả hai acknowledgement rồi kết thúc INTERNAL.
4. Dùng in-process server/channel kiểm thử application status và dùng Netty loopback kiểm thử transport reset.
5. Hủy stream sau một phần response; xác minh server nhận cancellation và giải phóng subscription/queue.
6. Đặt deadline ngắn hơn thời gian stream dự kiến; xác minh partial messages và final DEADLINE_EXCEEDED.
7. Thiết kế cursor/resume và test duplicate delivery sau reconnect.
8. Kiểm tra một terminal callback duy nhất, không có onNext sau terminal và không có side effect ngoài contract.

Sau bài này, bạn cần biết cách kiểm thử message đã được trao đổi trước lỗi cho từng kiểu streaming RPC, xác minh terminal status/callback và cleanup, cũng như phân biệt application status với transport failure. Khi partial progress có sequence, cursor và acknowledgement rõ ràng, hệ thống Spring gRPC có thể phục hồi stream mà không âm thầm mất dữ liệu hoặc lặp side effect.
