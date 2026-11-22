# Test retryable và non-retryable status

Retry giúp client gRPC phục hồi sau lỗi tạm thời, nhưng retry mọi lỗi đều có thể làm tăng tải, kéo dài thời gian chờ và lặp lại side effect. Một status chỉ được retry khi policy cho phép, call vẫn còn khả năng retry và deadline tổng còn đủ ngân sách. Vì vậy, cần kiểm thử cả status có thể retry lẫn status phải kết thúc ngay, đồng thời xác minh số attempt thực tế và kết quả cuối mà caller nhận.

**Test retryable và non-retryable status** là kiểm thử hành vi retry của gRPC client theo status code, retry policy và trạng thái commitment của RPC. Bài thuộc chương **Error testing** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là cấu hình retryableStatusCodes, phân biệt attempt status với final status, kiểm thử maxAttempts, backoff, deadline và bảo đảm operation có thể chịu được request lặp.

## 1. Retryable status không có nghĩa mọi call đều được thử lại

gRPC retry dựa trên service config của client. Một method có thể khai báo:

- maxAttempts: tổng số lần thử tối đa, bao gồm attempt đầu tiên.
- initialBackoff: thời gian chờ trước retry đầu tiên.
- maxBackoff: giới hạn backoff.
- backoffMultiplier: hệ số tăng backoff.
- retryableStatusCodes: allowlist status code cho phép thử lại.

Client chỉ retry theo policy khi attempt kết thúc bằng status nằm trong allowlist và RPC chưa bị commit. Deadline tổng, retry throttling, server pushback, retry buffer và trạng thái call đều có thể ngăn một retry tiếp theo.

Ví dụ: policy cho phép UNAVAILABLE với maxAttempts=3. Nếu attempt đầu trả UNAVAILABLE, client có thể tạo attempt thứ hai. Nếu attempt thứ hai thành công, caller chỉ nhận final status OK; lỗi UNAVAILABLE trung gian không phải final status của logical call.

Một status nằm trong retryableStatusCodes là điều kiện cần, không phải bảo đảm retry chắc chắn xảy ra.

## 2. Phân biệt logical call, attempt và final status

Ba đơn vị cần tách rõ khi viết test:

| Đơn vị | Ý nghĩa | Nơi quan sát |
| --- | --- | --- |
| Logical call | Một lần ứng dụng gọi method gRPC. | Client stub/call boundary. |
| Attempt | Một lần thử gửi RPC tới transport/server. | Retry instrumentation hoặc số lần server handler được gọi. |
| Final status | Kết quả cuối cùng mà ứng dụng client nhận. | Client terminal callback hoặc exception từ blocking stub. |

Ví dụ một logical call:

1. Attempt 1 tới server và kết thúc UNAVAILABLE.
2. Client chờ backoff.
3. Attempt 2 tới server và trả response thành công.
4. Client nhận final status OK.

Kết quả mong đợi là một logical call, hai server-observed attempts và một final status OK. Không cộng hai attempts thành hai lần gọi ở tầng ứng dụng.

Server invocation counter chỉ đếm các attempt đã tới service handler. Nó không đếm các lỗi kết nối xảy ra trước khi request tới server. Để quan sát toàn bộ attempt của client, cần instrumentation ở retry layer hoặc telemetry hỗ trợ attempt-level metrics.

## 3. Chọn status theo semantics của lỗi

Status code phải mô tả đúng nguyên nhân, sau đó retry policy mới quyết định có thử lại hay không:

| Status | Cách xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| UNAVAILABLE | Thường có thể retry với backoff. | Service/transport có thể tạm thời không khả dụng. |
| RESOURCE_EXHAUSTED | Chỉ retry khi server biểu thị tình trạng có thể phục hồi và client có backoff/pushback phù hợp. | Retry tức thời có thể làm quá tải nặng hơn. |
| DEADLINE_EXCEEDED | Chỉ retry khi policy và deadline tổng còn ngân sách; thường call đã gần hoặc hết hạn. | Retry không thể tạo thêm thời gian ngoài deadline tổng. |
| ABORTED | Thường cần retry ở tầng transaction/workflow cao hơn. | Có thể phải đọc lại state hoặc thực hiện lại cả transaction. |
| FAILED_PRECONDITION | Không retry cho tới khi điều kiện hệ thống thay đổi. | Gửi lại cùng request không sửa được precondition. |
| INVALID_ARGUMENT | Không retry. | Request sai dữ liệu hoặc vi phạm contract. |
| UNAUTHENTICATED / PERMISSION_DENIED | Không retry tự động bằng cùng credential/quyền. | Cần xác thực hoặc cấp quyền đúng. |
| NOT_FOUND | Thường không retry nếu đối tượng thực sự không tồn tại. | Lặp lại cùng truy vấn không làm tài nguyên xuất hiện. |

Đây là hướng dẫn thiết kế thường gặp, không phải bảng phân loại bắt buộc của gRPC. Service config mới là nơi khai báo status nào được retry. Không thêm hàng loạt status vào allowlist chỉ để tăng tỷ lệ thành công.

## 4. Cấu hình retry policy cho unary method

Ví dụ cấu hình chỉ retry UNAVAILABLE cho inventory.Inventory/GetStock:

~~~java
import java.util.List;
import java.util.Map;

Map<String, ?> retryPolicy = Map.of(
        "maxAttempts", 3.0,
        "initialBackoff", "0.05s",
        "maxBackoff", "0.2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE")
);

Map<String, ?> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.Inventory",
                "method", "GetStock")),
        "retryPolicy", retryPolicy
);

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(methodConfig)
);
~~~

maxAttempts=3 nghĩa là tối đa ba lần thử: attempt ban đầu và tối đa hai retries. Giá trị trong service config là JSON-compatible; ví dụ dùng 3.0 cho số attempts và chuỗi duration theo định dạng gRPC service config.

retryableStatusCodes là allowlist. Trong ví dụ, INVALID_ARGUMENT không được retry dù server trả status đó nhiều lần. Policy nên được giới hạn theo service/method cần retry, không bật retry rộng cho mọi RPC nếu semantics của chúng khác nhau.

## 5. Tạo test server có hành vi xác định

Để kiểm thử retry policy, dùng một service test có thể trả status theo số lần được gọi. Ví dụ attempt đầu trả UNAVAILABLE, attempt sau thành công:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.atomic.AtomicInteger;

final class RetryTestInventoryService
        extends InventoryGrpc.InventoryImplBase {

    final AtomicInteger receivedAttempts = new AtomicInteger();

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {

        int attempt = receivedAttempts.incrementAndGet();
        if (attempt == 1) {
            responseObserver.onError(
                    Status.UNAVAILABLE
                            .withDescription("temporary test failure")
                            .asRuntimeException());
            return;
        }

        responseObserver.onNext(StockReply.newBuilder()
                .setAvailableUnits(7)
                .build());
        responseObserver.onCompleted();
    }
}
~~~

Counter nằm trong service instance nên phản ánh số lần request thực sự tới handler. Trong test thật, dùng generated class, method và field tương ứng với Protobuf contract của dự án.

Để kiểm tra non-retryable status, tạo một fixture khác luôn trả INVALID_ARGUMENT và tăng cùng loại counter. Không dùng một service fixture đã có state từ test trước; mỗi test cần state độc lập để số attempt không phụ thuộc thứ tự chạy.

## 6. Dùng transport loopback để kiểm thử retry

Retry behavior cần được kiểm thử qua một client channel có service config và một server transport thực. Ví dụ dưới đây dùng Netty loopback:

~~~java
Server server = NettyServerBuilder.forPort(0)
        .addService(retryTestService)
        .build()
        .start();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("127.0.0.1", server.getPort())
        .usePlaintext()
        .enableRetry()
        .defaultServiceConfig(serviceConfig)
        .build();

try {
    InventoryBlockingStub stub =
            InventoryGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(3, TimeUnit.SECONDS);

    StockReply reply = stub.getStock(request);

    assertEquals(7, reply.getAvailableUnits());
    assertEquals(2, retryTestService.receivedAttempts.get());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
    server.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Đây là skeleton test; các biến retryTestService, serviceConfig và request được tạo từ fixture ở trên. Dùng port 0 để hệ điều hành cấp port trống. Channel phải được tạo sau khi server đã start và đóng trong teardown để không rò thread/socket giữa các test.

Netty loopback giúp kiểm tra retry qua transport thực tế hơn in-process transport. Hành vi cụ thể còn phụ thuộc phiên bản grpc-java, resolver và cấu hình retry; cần dùng đúng version của ứng dụng và xác minh retry được bật, service config được áp dụng cho đúng full service/method name.

## 7. Test retryable status: attempt đầu lỗi, attempt sau thành công

Với policy chỉ retry UNAVAILABLE, test thành công cần xác minh cả response và attempt count:

~~~java
@Test
void retriesUnavailableAndReturnsOk() {
    // Arrange: server trả UNAVAILABLE lần đầu, OK ở lần thứ hai.
    RetryTestInventoryService service =
            new RetryTestInventoryService();
    RunningGrpcFixture fixture =
            RunningGrpcFixture.start(service, retryServiceConfig());

    try {
        InventoryBlockingStub stub =
                fixture.stub().withDeadlineAfter(3, TimeUnit.SECONDS);

        // Act
        StockReply reply = stub.getStock(validRequest());

        // Assert
        assertEquals(7, reply.getAvailableUnits());
        assertEquals(2, service.receivedAttempts.get());
    } finally {
        fixture.close();
    }
}
~~~

RunningGrpcFixture là helper test của ứng dụng, chịu trách nhiệm start Netty server/channel và đóng chúng. Test không chỉ assert response thành công; nếu chỉ kiểm tra response, test có thể pass ngay cả khi retry policy không được áp dụng và fixture vô tình trả OK ở attempt đầu.

Không assert backoff chính xác tới millisecond. Scheduler, CI load và runtime có thể làm thời điểm retry dao động. Hãy assert số attempt, final status và deadline tổng; nếu cần xác minh backoff, đo khoảng thời gian với tolerance rộng hoặc quan sát retry instrumentation.

## 8. Test non-retryable status: kết thúc sau một attempt

Với cùng retry policy nhưng service trả INVALID_ARGUMENT, client phải kết thúc logical call mà không tạo policy retry:

~~~java
@Test
void doesNotRetryInvalidArgument() {
    AtomicInteger receivedAttempts = new AtomicInteger();
    InventoryGrpc.InventoryImplBase service =
            new InventoryGrpc.InventoryImplBase() {
                @Override
                public void getStock(
                        StockRequest request,
                        StreamObserver<StockReply> responseObserver) {
                    receivedAttempts.incrementAndGet();
                    responseObserver.onError(
                            Status.INVALID_ARGUMENT
                                    .withDescription("invalid test input")
                                    .asRuntimeException());
                }
            };

    RunningGrpcFixture fixture =
            RunningGrpcFixture.start(service, retryServiceConfig());
    try {
        InventoryBlockingStub stub =
                fixture.stub().withDeadlineAfter(3, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getStock(invalidRequest()));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        assertEquals(1, receivedAttempts.get());
    } finally {
        fixture.close();
    }
}
~~~

Test này chứng minh INVALID_ARGUMENT không nằm trong retryableStatusCodes. Nó cũng xác minh final status mà caller nhận đúng là INVALID_ARGUMENT, không bị biến thành UNAVAILABLE hoặc một lỗi chung khác.

## 9. Test status retryable nhưng policy không cho phép

Status và policy phải được kiểm tra riêng. Nếu server trả UNAVAILABLE nhưng method không có retry policy, client không thực hiện policy retry. Có thể viết test với channel không gắn retry service config và server fixture trả UNAVAILABLE sau khi handler đã nhận request:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stubWithoutRetryPolicy.getStock(validRequest()));

assertEquals(
        Status.Code.UNAVAILABLE,
        error.getStatus().getCode());
assertEquals(1, service.receivedAttempts.get());
~~~

Khi kiểm thử trường hợp không có policy, phải bảo đảm request đã tới service handler và handler chủ động trả UNAVAILABLE. gRPC có thể thực hiện transparent retry giới hạn trong một số tình huống transport biết request chưa được server xử lý; điều đó khác với retry theo service policy. Counter ở handler giúp xác minh trường hợp test đang kiểm tra.

## 10. Retry exhaustion và final status

Nếu mọi attempt đều trả status retryable, client thử tới maxAttempts hoặc dừng sớm khi deadline/commitment/throttling không cho phép:

~~~text
Logical call (maxAttempts = 3)
  attempt 1 -> UNAVAILABLE
  backoff
  attempt 2 -> UNAVAILABLE
  backoff
  attempt 3 -> UNAVAILABLE
  final status -> UNAVAILABLE
~~~

Test cần xác minh:

- Server handler được gọi ba lần trong trường hợp mọi attempt đều tới server.
- Client nhận final status UNAVAILABLE.
- Không có attempt thứ tư.
- Tổng thời gian không vượt deadline test.

Nếu một attempt không tới server do lỗi kết nối, server counter có thể nhỏ hơn số client attempts. Trong trường hợp đó, dùng retry instrumentation phía client để xác minh attempt count thay vì suy ra mọi attempt từ server counter.

## 11. Deadline có thể kết thúc retry trước maxAttempts

Deadline áp dụng cho toàn logical call, bao gồm các attempt và khoảng backoff:

~~~text
Deadline tổng: 300 ms

Attempt 1:  UNAVAILABLE
Backoff:    chờ
Attempt 2:  đang thực hiện
Deadline:   hết
Final:      DEADLINE_EXCEEDED
~~~

Khi deadline hết, client không được kéo dài ngân sách bằng cách cấp timeout mới cho mỗi attempt. Test deadline nên dùng một handler chậm hoặc backoff đủ lớn để deadline tổng hết trước lần retry tiếp theo; xác minh final status và số attempt thực tế, không phụ thuộc một timing chính xác tuyệt đối.

DEADLINE_EXCEEDED cũng có thể được khai báo retryable trong policy, nhưng nếu deadline của logical call đã hết thì không còn thời gian cho attempt tiếp theo. Không dùng retry để che một deadline budget quá nhỏ hoặc dependency liên tục chậm.

## 12. Commitment có thể ngăn retry

Một attempt chỉ có thể được retry khi gRPC còn khả năng phát lại call. Khi call đã committed, retry policy không tiếp tục tạo attempt mới. Các trường hợp quan trọng gồm:

- Client đã nhận response headers từ server.
- Request message vượt giới hạn retry buffer khiến call được commit.
- Streaming call đã trao đổi dữ liệu theo cách không thể phát lại an toàn.

Do đó, test retry nên bắt đầu bằng unary method đơn giản, chưa gửi response headers trước lỗi. Nếu muốn kiểm tra commitment, tạo một test riêng có server gửi response headers rồi mới kết thúc attempt bằng status; xác minh client không retry attempt đã commit theo semantics của runtime/version đang dùng.

Không nhầm status nằm trong allowlist với call chắc chắn retry. Status retryable nhưng call committed vẫn có thể kết thúc ngay.

## 13. Idempotency và side effect khi retry

Retry có thể làm cùng logical operation tới server nhiều lần. Một tình huống phổ biến:

1. Server nhận request và ghi dữ liệu thành công.
2. Response bị mất hoặc connection đứt trước khi client nhận kết quả.
3. Client thấy lỗi retryable và gửi lại request.
4. Server nhận cùng thao tác lần thứ hai.

Nếu method thực hiện side effect, retry có thể tạo đơn hàng trùng, trừ tiền hai lần hoặc phát event trùng. Với RPC ghi, cần thiết kế idempotency:

- Client gửi idempotency key ổn định cho logical operation.
- Server lưu kết quả theo key trong transaction phù hợp.
- Request lặp với cùng key trả lại kết quả đã lưu thay vì thực hiện side effect lần nữa.
- Key có phạm vi, TTL và quyền truy cập rõ ràng.
- Test mô phỏng response bị mất sau khi side effect đã commit.

Không tạo idempotency key mới ở mỗi attempt. Request ID dùng để liên kết log cũng không tự động là idempotency key; hai trường có lifecycle và semantics khác nhau.

## 14. Retry và streaming RPC

Không áp dụng kết quả test unary cho mọi streaming method. Với client-streaming hoặc bidirectional streaming, request có thể đã gửi nhiều message; server có thể đã xử lý một phần trước khi lỗi. Với server-streaming, client có thể đã nhận response message trước khi stream kết thúc.

Sau khi call đã committed, gRPC không thể mặc định phát lại toàn bộ stream. Nếu ứng dụng cần phục hồi, hãy thiết kế resume protocol bằng cursor/sequence number, acknowledgement và idempotent processing. Mở một RPC mới từ vị trí đã xác nhận là application-level resume, khác với automatic retry của gRPC.

Test streaming cần kiểm tra duplicate, mất message, reconnect và resume cursor riêng. Không khẳng định rằng retry policy unary chứng minh streaming retry an toàn.

## 15. Observability khi test retry

Để biết test thực sự làm gì, ghi nhận riêng:

| Tín hiệu | Mục đích |
| --- | --- |
| Logical calls started/completed | Một lần ứng dụng gọi method và final status. |
| Server handler invocation count | Số attempt thực sự tới handler test. |
| Client attempt count | Số lần client retry layer bắt đầu attempt, nếu instrumentation hỗ trợ. |
| Attempt status | Status từng attempt. |
| Final status | Status duy nhất caller nhận. |
| Logical call duration | Tổng thời gian gồm backoff và mọi attempt. |

ClientInterceptor ở ranh giới ứng dụng thường quan sát final onClose; nó không nhất thiết thấy từng retry attempt bên trong channel. Không tăng attempt counter ở mỗi onClose của interceptor thông thường. Dùng OpenTelemetry/gRPC instrumentation hoặc telemetry có attempt-level semantics nếu cần số liệu client attempts.

Trong test, server invocation counter là bằng chứng hữu ích cho số attempt đã đến server. Kết hợp với final status và response để tránh test chỉ kiểm tra một phía.

## 16. Các tình huống kiểm thử cần có

| Trường hợp | Policy/server fixture | Kết quả mong đợi |
| --- | --- | --- |
| Retryable rồi thành công | UNAVAILABLE, sau đó OK; policy cho phép retry. | Nhiều attempts; final status OK. |
| Non-retryable | INVALID_ARGUMENT; policy chỉ cho UNAVAILABLE. | Một attempt; final status INVALID_ARGUMENT. |
| Retryable nhưng không có policy | Server handler trả UNAVAILABLE; channel không có retry policy. | Không có policy retry; final status UNAVAILABLE. |
| Retry exhaustion | Mọi attempt trả UNAVAILABLE; maxAttempts=3. | Tối đa ba attempts; final status lỗi. |
| Deadline trong backoff | Attempt lỗi, backoff dài hơn ngân sách còn lại. | Final status DEADLINE_EXCEEDED; không retry sau deadline. |
| Commitment | Server gửi response headers trước lỗi retryable. | Không giả định attempt đã commit được retry. |
| Side effect và response mất | Server commit rồi transport lỗi. | Idempotency ngăn side effect trùng. |
| Caller cancellation | Client hủy logical call trong backoff. | Không tiếp tục tạo attempt mới. |
| Status không phù hợp | Server dùng INVALID_ARGUMENT cho lỗi tạm thời. | Test phát hiện contract/status mapping sai. |

Mỗi test nên có fixture riêng, deadline hữu hạn, cleanup channel/server và assertion về cả attempt count lẫn final status. Không dùng Thread.sleep() để đoán retry đã xảy ra; dùng counter, latch hoặc test observer có timeout.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| UNAVAILABLE không được retry | Method không có policy hoặc status không nằm trong allowlist. | Kiểm tra service config và full method name. |
| INVALID_ARGUMENT bị retry | Đưa status lỗi dữ liệu vào retryableStatusCodes. | Chỉ retry lỗi tạm thời theo semantics. |
| Test chỉ assert response OK | Không chứng minh có retry thực sự. | Assert server invocation/attempt count. |
| Assert attempt count lớn hơn maxAttempts | Hiểu maxAttempts là số retries ngoài attempt đầu. | Nhớ maxAttempts bao gồm attempt đầu tiên. |
| Server counter thấp hơn client attempt count | Một số attempt thất bại trước khi tới handler. | Dùng client attempt instrumentation và đặt tên metric đúng. |
| Retry không xảy ra dù status được allowlist | Call đã committed, deadline hết hoặc throttling/pushback. | Kiểm tra response headers, buffer, deadline và retry telemetry. |
| Side effect bị lặp | Operation không idempotent. | Idempotency key và deduplication phía server. |
| Test lúc pass lúc fail | Phụ thuộc sleep/timing hoặc dùng chung fixture state. | Dùng latch, deadline hợp lý và fixture độc lập. |

## 18. Bài tập thực hành

1. Cấu hình policy chỉ retry UNAVAILABLE cho một unary read method.
2. Viết test service trả UNAVAILABLE lần đầu rồi OK; xác minh một logical call tạo hai server-observed attempts.
3. Viết test trả INVALID_ARGUMENT; xác minh chỉ một attempt và final status giữ nguyên.
4. Viết test UNAVAILABLE khi channel không có retry policy; phân biệt policy retry với transparent retry.
5. Kiểm thử retry exhaustion với maxAttempts=3.
6. Kiểm thử deadline hết trong backoff và caller cancellation.
7. Thiết kế test commitment và idempotency cho một RPC ghi.
8. Tạo dashboard/test report phân biệt logical call, attempt status, final status và logical call duration.

Sau bài này, bạn cần biết cách chứng minh một status có được retry theo policy hay không, phân biệt lỗi trung gian với final status, và kiểm tra các điều kiện có thể ngăn retry như commitment hoặc deadline. Kết hợp attempt count, final status và idempotency test giúp dịch vụ Spring gRPC phục hồi lỗi tạm thời mà không tạo retry storm hoặc lặp side effect.
