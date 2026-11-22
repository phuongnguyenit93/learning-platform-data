# Kiểm thử streaming end to end

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Thiết kế integration test chạy qua gRPC server, HTTP/2 transport và generated client stub.
- Kiểm thử server-streaming, client-streaming và bidirectional streaming.
- Đồng bộ test thread với callback bất đồng bộ mà không phụ thuộc vào Thread.sleep.
- Xác minh thứ tự message, terminal event, status lỗi và cancellation.
- Đặt deadline, giới hạn thời gian chờ và dọn channel/stream đúng vòng đời.
- Phân biệt kiểm thử end to end qua TCP với test service trực tiếp hoặc in-process transport.

## 1. End to end có nghĩa là kiểm tra đường đi thật của RPC

Một test gọi trực tiếp method Java của service chỉ kiểm tra business method. Nó không xác nhận Protobuf serialization, generated stub, HTTP/2 transport, server dispatch, metadata, status mapping hay cách client nhận callback.

Kiểm thử streaming end to end cần một client gRPC thật kết nối tới server đang chạy. Request và response phải đi qua generated code và transport. Trong **SPRING_GRPC**, server thường dùng service bean và dependency do Spring quản lý; test nên khởi động đúng application context và gọi endpoint gRPC đã bind.

Một bài test tốt xác minh cả nội dung message và vòng đời stream: message nào được gửi, thứ tự nhận, khi nào stream hoàn tất, lỗi được biểu diễn bằng status nào và tài nguyên được giải phóng ra sao.

## 2. Ba kiểu streaming cần kiểm thử

Protobuf định nghĩa ba kiểu RPC streaming:

| Kiểu | Request | Response | Ví dụ sử dụng |
| --- | --- | --- | --- |
| Server-streaming | Một message | Nhiều message | Theo dõi giá, sự kiện hoặc tiến độ. |
| Client-streaming | Nhiều message | Một message cuối | Upload chunks, tổng hợp số liệu. |
| Bidirectional streaming | Nhiều message | Nhiều message | Chat, đồng bộ hai chiều, điều khiển thiết bị. |

Mỗi kiểu có lifecycle khác nhau. Server-streaming kết thúc khi server gọi onCompleted/onError. Client-streaming thường kết thúc chiều request khi client gọi onCompleted; server sau đó gửi response cuối. Bidirectional streaming có hai chiều độc lập: client có thể tiếp tục gửi trong khi đang nhận response.

## 3. Hợp đồng Protobuf cho bài kiểm thử

Ví dụ một service có đủ ba kiểu streaming:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.example.inventory.grpc";
option java_multiple_files = true;

message WatchRequest {
  string sku = 1;
}

message StockUpdate {
  string sku = 1;
  int64 available = 2;
  int64 sequence = 3;
}

message StockChunk {
  string upload_id = 1;
  int64 quantity = 2;
}

message UploadSummary {
  string upload_id = 1;
  int64 chunk_count = 2;
  int64 total_quantity = 3;
}

message ClientMessage {
  int64 sequence = 1;
  string text = 2;
}

message ServerMessage {
  int64 sequence = 1;
  string text = 2;
}

service InventoryStream {
  rpc WatchStock(WatchRequest) returns (stream StockUpdate);
  rpc UploadStock(stream StockChunk) returns (UploadSummary);
  rpc Exchange(stream ClientMessage) returns (stream ServerMessage);
}
~~~

Generated code cung cấp async stub và server base class cho từng method. Test dùng đúng generated type từ hợp đồng của dự án; không tự tạo request/response giả để thay cho serialization thật.

## 4. Khởi động server bằng Spring test context

Integration test nên dùng service implementation được Spring inject và server lifecycle do starter hoặc test fixture quản lý. Nếu starter tự khởi động gRPC server, lấy port thực tế từ test support của starter. Nếu test tự sở hữu server, đăng ký service bean vào một server fixture có lifecycle gắn với context.

Điều kiện quan trọng:

- Server đã bind thành công trước khi test tạo channel.
- Test lấy đúng gRPC port, không nhầm với port web của Spring Boot.
- Dùng port động để test song song không xung đột.
- Chỉ có một chủ sở hữu server lifecycle trong mỗi context.
- Nếu mục tiêu là kiểm tra transport, dùng TCP channel thật; in-process test không thay thế được kiểm tra HTTP/2 socket.

Các bài trước đã trình bày chi tiết khởi động server và lấy port động. Ở đây, test tập trung vào stream sau khi endpoint đã sẵn sàng.

## 5. Tạo channel và async stub

Streaming API thường dùng async stub. Tạo channel sau khi Spring context đã refresh:

~~~java
@SpringBootTest
class InventoryStreamingIntegrationTest {
    @Autowired
    GrpcTestEndpoint grpcEndpoint;

    private ManagedChannel channel;
    private InventoryStreamGrpc.InventoryStreamStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcEndpoint.port())
            .usePlaintext()
            .build();

        stub = InventoryStreamGrpc.newStub(channel)
            .withDeadlineAfter(5, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

GrpcTestEndpoint là abstraction test-only cung cấp port của server do Spring/starter quản lý. Thay nó bằng accessor thực tế trong dự án. usePlaintext chỉ dành cho test loopback không bật TLS; nếu production dùng TLS, cần một bộ test kết nối bằng trust certificate.

Đặt deadline ở stub hoặc từng call để RPC không treo vô hạn. Timeout chờ callback của test nên dài hơn deadline RPC một khoảng nhỏ để test có thể nhận và assert lỗi cuối.

## 6. Đồng bộ callback với test thread

Async stub trả kết quả qua StreamObserver. Test method và callback thường chạy trên các thread khác nhau, vì vậy không thể gọi RPC rồi assert ngay lập tức.

Một pattern hữu ích:

- Dùng CountDownLatch để báo terminal event.
- Dùng CopyOnWriteArrayList hoặc collection có đồng bộ để lưu message.
- Dùng AtomicReference để giữ lỗi callback.
- Chỉ assert trên test thread sau khi latch hoàn tất.
- Đặt timeout hữu hạn cho await.

Không dùng Thread.sleep để đoán khi nào message tới. Sleep làm test phụ thuộc tốc độ máy và dễ flaky trên CI. Không để assertion failure trong callback mà không chuyển lỗi về test thread; exception trên callback thread có thể không làm test method thất bại như mong đợi.

## 7. Kiểm thử server-streaming

Server-streaming trả về nhiều response cho một request. Ví dụ client theo dõi tồn kho của một SKU:

~~~java
@Test
void receivesAllStockUpdatesInOrder() throws Exception {
    List<StockUpdate> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    stub.watchStock(
        WatchRequest.newBuilder().setSku("SKU-42").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(StockUpdate update) {
                received.add(update);
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

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, received.size());
    assertEquals(
        List.of(1L, 2L, 3L),
        received.stream().map(StockUpdate::getSequence).toList());
}
~~~

Test xác nhận số lượng và sequence của message, không chỉ xác nhận có ít nhất một response. Nếu hợp đồng không bảo đảm thứ tự, hãy assert theo correlation ID hoặc tập kết quả thay vì ép thứ tự không có trong contract.

Server phải gọi đúng một terminal event. Nếu server stream vô hạn, test cần chủ động cancel sau khi nhận đủ điều kiện; không chờ onCompleted vì nó có thể không bao giờ xảy ra.

## 8. Kiểm thử client-streaming

Client-streaming gửi nhiều request message rồi nhận một response cuối. Method trên async stub trả về request observer; test gọi onNext nhiều lần và gọi onCompleted để kết thúc chiều gửi:

~~~java
@Test
void uploadsChunksAndReceivesOneSummary() throws Exception {
    AtomicReference<UploadSummary> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    StreamObserver<StockChunk> request = stub.uploadStock(
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary summary) {
                result.set(summary);
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

    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(2).build());
    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(5).build());
    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(3).build());
    request.onCompleted();

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertNotNull(result.get());
    assertEquals(3, result.get().getChunkCount());
    assertEquals(10, result.get().getTotalQuantity());
}
~~~

onCompleted trên request observer báo rằng client đã gửi xong input; nó không có nghĩa response cuối đã tới. Test chỉ hoàn tất khi response observer nhận terminal event. Không gọi request.onCompleted trước khi gửi xong toàn bộ chunks.

Nếu client gặp lỗi khi gửi, dùng request.onError để kết thúc chiều request với lỗi. Không tiếp tục gọi onNext sau terminal event.

## 9. Kiểm thử bidirectional streaming

Với bidirectional streaming, client và server có thể gửi message độc lập theo hai chiều. Client nhận request observer ngay khi mở stream và cung cấp response observer để nhận message:

~~~java
@Test
void exchangesMessagesInBothDirections() throws Exception {
    List<ServerMessage> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    StreamObserver<ClientMessage> request = stub.exchange(
        new StreamObserver<>() {
            @Override
            public void onNext(ServerMessage message) {
                received.add(message);
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

    request.onNext(ClientMessage.newBuilder()
        .setSequence(1).setText("first").build());
    request.onNext(ClientMessage.newBuilder()
        .setSequence(2).setText("second").build());
    request.onCompleted();

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(List.of(1L, 2L),
        received.stream().map(ServerMessage::getSequence).toList());
}
~~~

Ví dụ gửi xong request trước khi assert response để giữ test đơn giản. Một test tương tác hai chiều thực sự có thể gửi message tiếp theo sau khi nhận response hoặc phối hợp hai chiều bằng latch/queue. Không giả định server phải trả response ngay cho từng request trừ khi đó là contract của method.

## 10. Kiểm tra lỗi và status ở giữa stream

Streaming call có thể kết thúc bằng status lỗi sau khi đã gửi một số message. Test cần kiểm tra cả message đã nhận trước lỗi và status cuối:

~~~java
@Test
void preservesMessagesBeforeTerminalError() throws Exception {
    List<StockUpdate> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch terminal = new CountDownLatch(1);

    stub.watchStock(
        WatchRequest.newBuilder().setSku("MISSING").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(StockUpdate update) {
                received.add(update);
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

    assertTrue(terminal.await(6, TimeUnit.SECONDS));
    assertNotNull(failure.get());
    assertEquals(
        Status.Code.NOT_FOUND,
        Status.fromThrowable(failure.get()).getCode());
}
~~~

Trong thực tế, status có thể đến từ validation trước message đầu tiên hoặc sau một phần stream. Test cần phản ánh contract thực tế. Không assert message description quá chi tiết nếu nội dung đó không phải API contract; status code thường ổn định hơn.

## 11. Cancellation và client ngừng nhận stream

Với server stream dài hạn, client có thể cancel khi không còn cần dữ liệu. Dùng ClientResponseObserver để lấy ClientCallStreamObserver trong beforeStart:

~~~java
AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
    new AtomicReference<>();
CountDownLatch firstUpdate = new CountDownLatch(1);

stub.watchStock(
    WatchRequest.newBuilder().setSku("SKU-42").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchRequest> requestStream) {
            callRef.set(requestStream);
        }

        @Override
        public void onNext(StockUpdate update) {
            firstUpdate.countDown();
        }

        @Override
        public void onError(Throwable error) {}

        @Override
        public void onCompleted() {}
    });

assertTrue(firstUpdate.await(3, TimeUnit.SECONDS));
callRef.get().cancel("test no longer needs updates", null);
~~~

Test đầy đủ nên xác nhận server nhận cancellation và dừng producer/subscription liên quan. Cancellation không đồng nghĩa server luôn có thể dừng ngay lập tức; service phải truyền tín hiệu tới công việc nền và giải phóng buffer. Không assert một status duy nhất cho phía client nếu transport/cancellation race có thể làm status quan sát khác nhau; xác minh hành vi cleanup và không có message tiếp tục sau khi cancellation được xử lý.

## 12. Kiểm thử deadline và stream bị treo

Một stream có thể không phát message hoặc không kết thúc. Đặt deadline cho call:

~~~java
InventoryStreamGrpc.InventoryStreamStub boundedStub =
    stub.withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

Trong test, dùng timeout riêng cho latch. Khi deadline hết, client nhận lỗi terminal, thường là DEADLINE_EXCEEDED nếu deadline phía client là nguyên nhân. Server cần quan sát cancellation/deadline và dừng công việc.

Không đặt timeout của latch ngắn hơn deadline một cách tùy tiện, vì test có thể fail trước khi gRPC trả status cuối. Một khoảng đệm nhỏ giúp thu thập lỗi thực tế.

## 13. Kiểm tra backpressure và giới hạn message

Một end-to-end test cơ bản thường gửi ít message. Để kiểm tra tải stream, hãy xác minh ứng dụng không tích lũy queue vô hạn khi producer nhanh hơn consumer.

Các điểm nên kiểm tra:

- Manual inbound flow control chỉ request thêm message khi có capacity.
- Outbound writer tôn trọng isReady và dừng gửi khi transport chưa sẵn sàng.
- Queue ứng dụng có giới hạn theo số message và/hoặc tổng byte.
- Khi vượt giới hạn, server có chính sách reject/status rõ ràng.
- Cancellation giải phóng queue và buffer đang giữ.

Đừng biến một test E2E nhỏ thành benchmark. Dùng test riêng có tải kiểm soát để đo throughput, memory và latency; integration test ở đây xác nhận semantics và lifecycle.

## 14. Test TCP thật và in-process

| Cách test | Điều xác minh | Giới hạn |
| --- | --- | --- |
| Gọi trực tiếp service method | Logic Java trong handler | Không kiểm tra generated stub, serialization hoặc transport. |
| In-process gRPC | Stub, dispatch, callback và một phần interceptor | Không kiểm tra TCP socket, HTTP/2 network path hoặc TLS handshake. |
| TCP gRPC qua port động | Server startup, Protobuf serialization, HTTP/2, callback và status | Cần quản lý port, channel và lifecycle. |
| TCP gRPC qua TLS | Các phần trên cùng certificate/trust/hostname handshake | Cần certificate test và cấu hình client trust. |

Để gọi là end to end cho transport, ưu tiên TCP test qua server đang chạy. In-process test hữu ích cho suite nhanh nhưng không thay thế nhóm test TCP/TLS.

## 15. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Assert ngay sau khi gọi async stub | Callback chưa chạy, test đọc collection rỗng | Đợi terminal event bằng latch có timeout. |
| Dùng Thread.sleep để chờ message | Test flaky trên CI | Dùng latch, queue hoặc condition. |
| Chỉ assert số message | Bỏ sót sai thứ tự hoặc sai nội dung | Assert sequence, correlation ID và payload. |
| Nhầm request onCompleted với response hoàn tất | Test kết thúc quá sớm | Đợi response observer terminal event. |
| Không lưu lỗi callback | Test có thể bỏ sót lỗi bất đồng bộ | Lưu Throwable và assert trên test thread. |
| Gửi onNext sau onCompleted | Vi phạm stream lifecycle | Tuân thủ một terminal event cho mỗi chiều. |
| Không cancel stream vô hạn | Rò call, thread và buffer | Cancel sau điều kiện test và xác minh cleanup. |
| Không đặt deadline | Suite có thể treo | Deadline cho RPC và timeout cho test wait. |
| Chỉ test in-process | Bỏ sót lỗi transport | Bổ sung TCP end-to-end test. |

## 16. Ma trận kiểm thử streaming end to end

Một bộ test cơ bản nên có:

1. Server-streaming: nhận đủ message, đúng payload và sequence, sau đó onCompleted.
2. Client-streaming: gửi nhiều chunks, kết thúc request và nhận đúng summary.
3. Bidirectional streaming: gửi/nhận nhiều message và xác minh thứ tự theo contract.
4. Error: stream kết thúc bằng status đúng, kể cả khi đã có message trước đó.
5. Cancellation: client hủy stream và server dừng công việc nền.
6. Deadline: stream không hoàn tất bị kết thúc trong thời hạn.
7. Flow control: queue có giới hạn và producer không vượt capacity.
8. Lifecycle: channel đóng sau test, server đóng khi Spring context kết thúc.

Mỗi test nên có deadline, timeout chờ, assertion về payload/status và cleanup. Test không được phụ thuộc thứ tự chạy với test method khác hoặc state còn sót trong singleton service.

## 17. Bài tập thực hành

Triển khai integration test cho service InventoryStream:

1. Khởi động Spring test context với server đăng ký InventoryStream service.
2. Tạo ManagedChannel qua port động và generated async stub.
3. Kiểm thử WatchStock nhận ba update đúng sequence rồi hoàn tất.
4. Kiểm thử UploadStock nhận ba chunks và trả summary chính xác.
5. Kiểm thử Exchange gửi hai message và nhận response tương ứng.
6. Thêm trường hợp server trả NOT_FOUND hoặc lỗi validation giữa stream.
7. Cancel một WatchStock dài hạn và xác nhận worker/subscription được dọn.
8. Kiểm tra deadline cho stream không hoàn tất.
9. Đóng channel và xác nhận server tuân theo Spring lifecycle.

**Tiêu chí hoàn thành:** cả ba kiểu streaming đi qua generated stub và TCP transport, message/status đúng contract, callback được đồng bộ có timeout và không rò stream hoặc tài nguyên sau test.

## 18. Ghi nhớ

- End-to-end test phải gọi qua generated stub và server đang chạy; gọi trực tiếp method chỉ là unit test.
- Server-streaming, client-streaming và bidirectional streaming có lifecycle khác nhau.
- Đợi callback bằng latch/queue có timeout; không dùng Thread.sleep để đồng bộ.
- Lưu lỗi callback và assert trên test thread.
- Kiểm tra payload, sequence, số lượng message và terminal status.
- Request onCompleted chỉ kết thúc chiều gửi; phải đợi response observer hoàn tất.
- Cancellation và deadline phải được truyền tới worker để cleanup.
- Dùng TCP test để xác minh HTTP/2 transport; in-process không chứng minh TCP/TLS.
- Quản lý channel theo test và server theo Spring context lifecycle.

Kiểm thử streaming end to end xác nhận toàn bộ đường đi của message qua Spring gRPC, từ generated client tới server handler và callback response, đồng thời kiểm tra status, thứ tự, cancellation và vòng đời tài nguyên.
