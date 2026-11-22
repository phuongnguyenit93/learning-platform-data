# Test async stub

Async stub là client API được sinh từ Protobuf service để gọi gRPC mà không chặn thread chờ response. Kết quả được chuyển qua `StreamObserver`: client nhận message bằng `onNext`, kết thúc thành công bằng `onCompleted`, hoặc nhận lỗi bằng `onError`. Đây là API cần dùng khi kiểm thử client-streaming và bidirectional-streaming; nó cũng phù hợp để kiểm thử unary và server-streaming theo mô hình callback.

Trong Spring gRPC, test async stub cần xác minh cả kết quả RPC lẫn vòng đời callback: callback nào được gọi, số message và thứ tự message, status lỗi, deadline, cancellation và việc giải phóng tài nguyên. Vì callback có thể chạy trên thread khác thread test, assertion cần được đồng bộ hóa bằng latch, future hoặc queue; không đọc collection đang được callback cập nhật mà thiếu synchronization.

## 1. Async stub và vòng đời callback

Generated async stub trả kết quả qua callback thay vì trả response trực tiếp:

```text
Client calls asyncStub.method(request, responseObserver)
                   |
                   v
              gRPC call
                   |
          +--------+--------+
          |                 |
       success             error
          |                 |
       onNext(...)        onError(...)
          |                 |
       onCompleted       terminal
          |
       terminal
```

Với unary RPC, thành công thường có đúng một `onNext(response)` rồi `onCompleted()`. Với server-streaming, có thể có nhiều `onNext` trước `onCompleted`. Nếu RPC lỗi, `onError` là callback kết thúc; client không được chờ `onCompleted` sau đó.

Với client-streaming và bidirectional-streaming, method của async stub trả về `StreamObserver<Request>` để client gửi request. Response vẫn được nhận qua `StreamObserver<Response>` mà client truyền vào lúc bắt đầu call. Client kết thúc luồng request bằng `onCompleted()`; server có thể trả response cuối cùng sau khi nhận hết request.

Không giả định callback luôn chạy trên thread đã gọi stub. Executor, transport và cấu hình server quyết định cách callback được lập lịch. Thiết kế test phải an toàn với callback bất đồng bộ ngay cả khi in-process test đôi lúc thực thi callback trực tiếp.

## 2. Những kiểu RPC async stub hỗ trợ

| Kiểu RPC | Cách gọi generated async stub | Kết quả phía client |
| --- | --- | --- |
| Unary | `stub.getOrder(request, responseObserver)` | Một response hoặc một lỗi |
| Server-streaming | `stub.watchOrders(request, responseObserver)` | Nhiều response trong một stream |
| Client-streaming | `StreamObserver<Request> requests = stub.upload(responseObserver)` | Gửi nhiều request, nhận một response cuối |
| Bidirectional-streaming | `StreamObserver<Request> requests = stub.chat(responseObserver)` | Gửi và nhận nhiều message độc lập theo stream |

Async stub hỗ trợ cả bốn kiểu RPC. Đây là khác biệt quan trọng so với blocking stub, vốn chỉ cung cấp API đồng bộ cho unary và server-streaming.

## 3. Dựng in-process server và channel

In-process transport giúp test service và generated async stub trong cùng JVM mà không mở TCP port:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterAsyncStubTest {
    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .addService(new GreeterService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .build();

        stub = GreeterGrpc.newStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

`GreeterGrpc.GreeterStub` là generated async stub; `newStub(channel)` tạo stub dùng channel test. Tên server phải mới cho mỗi fixture để test không kết nối nhầm server khác. Đóng channel trước server và dùng timeout hữu hạn để teardown không treo vô hạn.

Ví dụ giả định test dependencies có `grpc-inprocess`, generated Protobuf classes, grpc-stub và JUnit 5, với phiên bản grpc-java được quản lý đồng bộ bằng BOM/version catalog. Test này kiểm tra gRPC call pipeline trong JVM; nó không kiểm tra TLS, HTTP/2 qua socket hay ingress.

## 4. Kiểm thử unary callback

Với unary RPC, dùng `CountDownLatch` để chờ callback kết thúc trong thời gian hữu hạn. Lưu response và lỗi vào `AtomicReference` để thread test đọc an toàn:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void receivesUnaryResponse() throws InterruptedException {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("An")
        .build();

    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<HelloReply> response = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    AtomicInteger responseCount = new AtomicInteger();

    stub.sayHello(request, new StreamObserver<>() {
        @Override
        public void onNext(HelloReply value) {
            response.set(value);
            responseCount.incrementAndGet();
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    });

    assertTrue(completed.await(2, TimeUnit.SECONDS),
        "RPC did not complete before test timeout");
    assertNull(failure.get());
    assertEquals(1, responseCount.get());
    assertEquals("Hello, An", response.get().getMessage());
}
```

Timeout hai giây ở `await` là giới hạn của test để tránh suite bị treo; nó không thay thế RPC deadline. Trong test production-like, đặt deadline riêng trên stub để kiểm tra chính sách timeout của client.

Không viết assertion JUnit trực tiếp trong `onNext` rồi kỳ vọng lỗi assertion tự truyền về thread test. Callback có thể chạy ở thread khác và lỗi có thể không làm test fail theo cách mong muốn. Hãy capture kết quả, đợi terminal callback, rồi assertion trên thread test.

## 5. Kiểm thử status lỗi qua onError

Khi server kết thúc RPC bằng status lỗi, async stub gọi `onError`. Dùng `Status.fromThrowable` để đọc status code:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Test
void receivesInvalidArgument() throws InterruptedException {
    HelloRequest request = HelloRequest.newBuilder()
        .setName(" ")
        .build();

    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();
    AtomicInteger unexpectedResponses = new AtomicInteger();

    stub.sayHello(request, new StreamObserver<>() {
        @Override
        public void onNext(HelloReply value) {
            unexpectedResponses.incrementAndGet();
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
    });

    assertTrue(terminal.await(2, TimeUnit.SECONDS));
    assertNotNull(failure.get());
    assertEquals(0, unexpectedResponses.get());
    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        Status.fromThrowable(failure.get()).getCode());
}
```

Trong test thực tế, thay `fail` trong callback bằng một cờ hoặc bộ đếm để tránh assertion chạy trên callback thread. Có thể dùng `AtomicInteger unexpectedResponses` rồi kiểm tra sau khi latch hoàn tất. Status cần được xác minh theo contract: `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `UNAVAILABLE` hoặc status phù hợp khác.

## 6. Kiểm thử server-streaming và thứ tự message

Với server-streaming, callback `onNext` có thể được gọi nhiều lần. Thu thập message vào collection thread-safe, sau đó đợi `onCompleted`:

```java
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

@Test
void receivesServerStreamInOrder() throws InterruptedException {
    ConcurrentLinkedQueue<String> messages =
        new ConcurrentLinkedQueue<>();
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    stub.sayHelloMany(
        HelloRequest.newBuilder().setName("An").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(HelloReply value) {
                messages.add(value.getMessage());
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                completed.countDown();
            }

            @Override
            public void onCompleted() {
                completed.countDown();
            }
        });

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(
        List.of("Hello, An", "Welcome, An", "Goodbye, An"),
        List.copyOf(messages));
}
```

Kiểm tra cả số lượng và thứ tự response. Nếu stream có thể phát rất nhiều message, tránh giữ toàn bộ payload trong memory chỉ để test; dùng queue giới hạn, counter, checksum hoặc assertion theo từng message. Luôn có deadline hoặc timeout test để trường hợp server quên `onCompleted` không làm suite chờ vô hạn.

## 7. Kiểm thử client-streaming

Với client-streaming RPC, gọi method trên async stub để lấy `StreamObserver<Request>`. Client gửi nhiều message bằng `onNext`, rồi gọi `onCompleted` để báo đã gửi xong. Server trả một response cuối qua response observer.

Ví dụ contract:

```proto
service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadSummary);
}
```

Test gửi các chunk và đợi summary:

```java
@Test
void uploadsMultipleChunks() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<UploadSummary> summary = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadSummary> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary value) {
                summary.set(value);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                completed.countDown();
            }

            @Override
            public void onCompleted() {
                completed.countDown();
            }
        };

    StreamObserver<UploadChunk> requests = stub.upload(responseObserver);
    requests.onNext(chunk(1, "part-a"));
    requests.onNext(chunk(2, "part-b"));
    requests.onNext(chunk(3, "part-c"));
    requests.onCompleted();

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, summary.get().getChunkCount());
}
```

Hàm `chunk(...)` là factory test tạo UploadChunk theo schema của ứng dụng. Không gọi `requests.onCompleted()` trước khi gửi hết message. Nếu client kết thúc request stream bằng `onError`, server phải nhận call kết thúc bất thường và không được giả định sẽ trả summary thành công.

## 8. Kiểm thử bidirectional-streaming

Với bidi-streaming, client và server có thể gửi message độc lập trên cùng call. Client nhận response observer khi mở stream và dùng request observer để gửi:

```proto
service ChatService {
  rpc Chat(stream ChatMessage) returns (stream ChatMessage);
}
```

Test nên xác minh:

- Mỗi request hợp lệ tạo response theo contract.
- Thứ tự response được giữ nếu contract yêu cầu.
- Client có thể gửi request tiếp theo khi response trước chưa hoàn tất.
- Server có thể kết thúc bằng `onCompleted` hoặc status lỗi.
- Client có thể cancel stream và server dừng công việc liên quan.

Đừng giả định một `onNext` từ client đồng nghĩa server đã xử lý request và response đã tới. Nếu cần xác minh round-trip từng message, dùng correlation ID trong message và chờ response tương ứng thay vì chỉ đếm số request đã gửi.

Ví dụ rút gọn cho một service echo theo correlation ID:

```java
BlockingQueue<String> receivedIds = new LinkedBlockingQueue<>();
CountDownLatch terminal = new CountDownLatch(1);
AtomicReference<Throwable> failure = new AtomicReference<>();

StreamObserver<ChatMessage> responses = new StreamObserver<>() {
    @Override
    public void onNext(ChatMessage value) {
        receivedIds.add(value.getCorrelationId());
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

StreamObserver<ChatMessage> requests = stub.chat(responses);
requests.onNext(chatMessage("c-1", "first"));
requests.onNext(chatMessage("c-2", "second"));
requests.onCompleted();

assertTrue(terminal.await(2, TimeUnit.SECONDS));
assertNull(failure.get());
assertEquals(List.of("c-1", "c-2"), List.of(
    receivedIds.poll(), receivedIds.poll()));
```

Ví dụ giả định server echo mỗi correlation ID đúng một lần; `chatMessage` là factory tạo message theo schema ứng dụng. Với protocol không bảo đảm response order, đối chiếu theo map correlation ID thay vì so sánh thứ tự list.

## 9. Deadline, cancellation và flow control

Async không có nghĩa là call tự kết thúc. Đặt deadline hữu hạn:

```java
GreeterGrpc.GreeterStub boundedStub =
    stub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);

boundedStub.sayHello(request, responseObserver);
```

Khi deadline hết hạn, client observer nhận `onError` với status thường là `DEADLINE_EXCEEDED`. Cancellation chủ động có thể thực hiện qua `ClientResponseObserver` và `ClientCallStreamObserver`:

```java
AtomicReference<ClientCallStreamObserver<HelloRequest>> callControl =
    new AtomicReference<>();
CountDownLatch callStarted = new CountDownLatch(1);

ClientResponseObserver<HelloRequest, HelloReply> observer =
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<HelloRequest> requestStream) {
            callControl.set(requestStream);
            callStarted.countDown();
        }

        @Override
        public void onNext(HelloReply value) {
            // Capture response for assertions.
        }

        @Override
        public void onError(Throwable error) {
            // Capture terminal status.
        }

        @Override
        public void onCompleted() {
            // Record successful completion.
        }
    };

stub.sayHello(request, observer);
assertTrue(callStarted.await(1, TimeUnit.SECONDS));
callControl.get().cancel("test cancellation", null);
```

Trong test hoàn chỉnh, chờ `beforeStart` được gọi trước khi lấy control handle và xác minh terminal status sau cancellation. Server handler nên quan sát cancellation qua gRPC Context hoặc cancellation callback để dừng tác vụ dài; chỉ hủy phía client mà server vẫn tiếp tục xử lý vô hạn là một lỗi tài nguyên.

Với streaming response, `ClientResponseObserver.beforeStart` còn cho phép điều khiển inbound flow:

```java
@Override
public void beforeStart(
        ClientCallStreamObserver<WatchRequest> requestStream) {
    requestStream.disableAutoInboundFlowControl();
    requestStream.request(1);
}

@Override
public void onNext(WatchReply value) {
    process(value);
    callControl.get().request(1);
}
```

Ví dụ trên minh họa demand từng message. Test flow control cần xác minh client chỉ nhận số message đã yêu cầu và tiếp tục request sau khi xử lý; không gọi `request` đồng thời tùy tiện từ nhiều thread nếu chưa thiết kế synchronization.

## 10. Thread safety và tránh test bị treo

Callback có thể chạy đồng thời với thread test. Chọn cấu trúc đồng bộ theo loại dữ liệu:

| Nhu cầu | Cách lưu phù hợp |
| --- | --- |
| Một response | `AtomicReference<T>` |
| Một lỗi terminal | `AtomicReference<Throwable>` |
| Đếm callback | `AtomicInteger` hoặc `LongAdder` |
| Nhiều message | `ConcurrentLinkedQueue<T>` hoặc synchronized collection |
| Chờ terminal callback | `CountDownLatch` |
| Kết quả bất đồng bộ có timeout | `CompletableFuture<T>` với `get(timeout, unit)` |

Các nguyên tắc:

- Không dùng `Thread.sleep()` để đoán callback đã chạy.
- Luôn chờ với timeout hữu hạn và báo lỗi rõ khi hết thời gian.
- Không gọi `onNext` sau `onCompleted` hoặc `onError`.
- Mỗi observer chỉ có một terminal event.
- Không block bên trong callback chờ một callback khác cần cùng executor.
- Dọn stream, channel, server và executor khi test kết thúc.

Nếu dùng `directExecutor()` cho in-process server, callback có thể chạy ngay trong thread gọi. Điều đó hữu ích cho test logic đơn giản nhưng không kiểm tra được mọi race condition. Bổ sung test với executor bất đồng bộ có giới hạn để xác minh thread safety và scheduling.

## 11. Spring gRPC integration và ranh giới transport

In-process test xác minh generated stub gọi đúng service implementation và callback nhận đúng kết quả. Để xác minh Spring wiring, dùng test context với đúng starter và cấu hình production:

1. Đăng ký service implementation, interceptor và dependency qua Spring bean.
2. Khởi động server do starter quản lý trên port test hoặc port động.
3. Lấy channel/stub từ client configuration thực tế.
4. Gọi unary/streaming RPC và xác minh callback/status.
5. Đóng Spring context, channel và server; xác minh không còn executor/stream sống.

In-process transport không xác minh TCP, TLS/mTLS, HTTP/2 negotiation, DNS, proxy, ingress hoặc service mesh. Những phần đó cần TCP/TLS integration test. Không kết luận Spring starter đã expose đúng port chỉ từ một fixture tự tạo bằng `InProcessServerBuilder`.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Unary success | Request hợp lệ | Một `onNext`, rồi `onCompleted` |
| Unary error | Request không hợp lệ | `onError` mang status đúng |
| Server streaming | Nhiều response | Đúng số lượng và thứ tự |
| Client streaming | Nhiều request rồi complete | Nhận một summary chính xác |
| Bidirectional | Request/response xen kẽ | Correlation và ordering đúng contract |
| Deadline | Call vượt hạn | `onError` với `DEADLINE_EXCEEDED` |
| Cancellation | Client hủy stream | Terminal status và server cleanup đúng |
| Flow control | Request từng message | Không nhận vượt demand |
| Metadata | Request ID/credential | Server đọc đúng metadata đã xác minh |
| Concurrency | Nhiều call đồng thời | Không rò state giữa observer |
| Cleanup | Test kết thúc | Không còn stream/channel/server/executor |
| Spring wiring | Server do starter quản lý | Bean, interceptor và lifecycle đúng |
| Transport | TCP/TLS | HTTP/2, certificate và network hoạt động |

**Bài tập:** `OrderService` có unary `GetOrder`, server-streaming `WatchOrderEvents`, client-streaming `UploadOrderLines` và bidi-streaming `ExchangeUpdates`. Client dùng async stub; mọi call phải có deadline và request ID.

1. Dựng in-process server/channel và tạo generated async stub.
2. Viết unary test dùng latch, kiểm tra một response và terminal callback.
3. Viết status test xác minh `NOT_FOUND` và `INVALID_ARGUMENT` qua `onError`.
4. Kiểm tra `WatchOrderEvents` trả đúng thứ tự event.
5. Gửi nhiều line qua `UploadOrderLines`, gọi `onCompleted` và xác minh summary.
6. Kiểm tra bidi stream bằng correlation ID để xác minh từng round-trip.
7. Kiểm tra deadline, cancellation và server cleanup.
8. Kiểm thử flow control bằng `request(1)` và xử lý từng response.
9. Xác minh request ID qua interceptor, không dùng mutable field chia sẻ giữa call.
10. Bổ sung Spring context và TCP/TLS integration tests cho các ranh giới tương ứng.

**Câu hỏi tự kiểm tra:**

- Vì sao async stub trả kết quả qua `StreamObserver`?
- Unary thành công có thứ tự callback nào?
- Khi nào `onError` là terminal event?
- Client-streaming lấy request observer từ đâu?
- Vì sao `onNext` phía client chưa chứng minh server đã xử lý message?
- Dùng latch và atomic reference để đồng bộ assertion ra sao?
- Deadline và cancellation khác nhau thế nào?
- `disableAutoInboundFlowControl` và `request(n)` kiểm soát điều gì?
- Vì sao không block bên trong callback?
- In-process test không xác minh được các thuộc tính transport nào?

**Ghi nhớ:** Test async stub phải xác minh callback lifecycle, response/status, thứ tự message, deadline và cancellation. Dùng latch/future có timeout, atomic reference và collection thread-safe để đồng bộ kết quả; kiểm tra riêng unary, server-streaming, client-streaming và bidi-streaming. In-process test xác minh call behavior, Spring context test xác minh wiring, còn TCP/TLS test xác minh transport production.
