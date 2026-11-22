# Kiểm thử retry và server restart

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt retry một RPC với việc ManagedChannel tự kết nối lại server.
- Cấu hình retry policy theo service/method và chọn status code có thể retry.
- Hiểu thời điểm một RPC được commit và vì sao không phải lỗi nào cũng có thể retry an toàn.
- Thiết kế operation idempotent để tránh side effect trùng khi response bị mất.
- Kiểm thử retry có kiểm soát bằng server trả UNAVAILABLE ở một số lần gọi đầu.
- Kiểm thử server restart, channel reconnect và giới hạn của các RPC đang chạy.
- Quản lý deadline, wait-for-ready, health state và lifecycle server trong Spring integration test.

## 1. Retry và server restart là hai vấn đề khác nhau

Khi gRPC server tạm thời không khả dụng, client có thể gặp lỗi ở hai lớp:

- **RPC retry**: client thực hiện lại một call đủ điều kiện theo retry policy. Mỗi attempt có thể tạo một lần thực thi mới ở server.
- **Channel reconnect**: ManagedChannel phát hiện kết nối bị lỗi và thử kết nối lại endpoint theo resolver/load-balancer và backoff. Việc kết nối lại không tự động phát lại mọi RPC đang chạy.

Phân biệt hai hành vi này rất quan trọng khi kiểm thử **SPRING_GRPC**. Channel có thể trở lại READY sau khi server khởi động lại, nhưng call đang chạy lúc server dừng có thể đã thất bại. Ngược lại, retry policy có thể gọi lại một unary RPC trên cùng channel nếu call chưa commit và status thuộc nhóm được phép retry.

Một test chỉ xác nhận channel kết nối lại không chứng minh retry policy hoạt động. Một test chỉ xác nhận RPC được gọi nhiều lần cũng không chứng minh channel phục hồi sau khi server restart.

## 2. Các loại retry trong gRPC

gRPC có thể thực hiện retry trong một số trường hợp:

1. **Transparent retry**: runtime có thể retry khi biết request chưa được server application xử lý, ví dụ call chưa được chuyển tới server listener.
2. **Configured retry**: service config định nghĩa retry policy cho method, gồm số attempt tối đa, backoff và status code có thể retry.
3. **Application retry**: ứng dụng tự gọi lại operation sau khi nhận lỗi. Cách này cần tự quản lý deadline, idempotency và số lần thử.

Configured retry không có nghĩa mọi lỗi đều được thử lại. Chỉ status nằm trong retryableStatusCodes mới được retry theo policy. Ví dụ UNAVAILABLE thường phù hợp với lỗi tạm thời; INVALID_ARGUMENT, UNAUTHENTICATED hoặc PERMISSION_DENIED thường không thể khắc phục bằng cách gửi lại cùng request.

Không nhầm retry policy với reconnect. Reconnect phục hồi transport; retry policy quyết định một call có được gửi lại hay không.

## 3. Khi nào một RPC được commit?

gRPC retry runtime lưu lại call history trong giới hạn retry buffer. Một call có thể được retry khi runtime còn có thể phát lại request một cách hợp lệ. Khi call đã commit, runtime không tự retry call đó nữa.

Các tình huống có thể làm call commit gồm:

- Client nhận response headers từ server.
- Retry buffer không còn đủ khả năng lưu request history.
- Call vượt qua một điểm mà runtime không thể đảm bảo việc phát lại an toàn theo retry contract.

Với unary RPC, server thường gửi response headers cùng hoặc trước response cuối; do đó retry thường chỉ khả thi trước khi call commit. Đối với streaming RPC, request/response có thể đã trao đổi nhiều message và việc phát lại toàn bộ stream phức tạp hơn. Không thiết kế upload hoặc bidirectional stream dựa trên giả định rằng gRPC sẽ replay toàn bộ stream sau mọi lỗi.

Một RPC đã commit có thể vẫn trả lỗi cho client nếu server hoặc kết nối hỏng trước khi client nhận được response cuối. Client không thể kết luận operation chưa xảy ra chỉ từ lỗi transport.

## 4. Chọn status code có thể retry

Retry policy phải phản ánh ngữ nghĩa operation và nguyên nhân lỗi:

| Status | Cân nhắc retry? | Lý do |
| --- | --- | --- |
| UNAVAILABLE | Thường có | Server hoặc dependency tạm thời không khả dụng; cần giới hạn attempts và backoff. |
| RESOURCE_EXHAUSTED | Chỉ khi có chính sách phục hồi rõ | Có thể là quá tải hoặc quota; retry ngay có thể làm tải nặng hơn. |
| ABORTED | Tùy transaction semantics | Có thể cần chạy lại toàn bộ transaction ở tầng ứng dụng. |
| DEADLINE_EXCEEDED | Thận trọng | Retry tiếp có thể không còn đủ deadline và operation trước có thể đã hoàn tất. |
| INVALID_ARGUMENT | Thường không | Request sai sẽ tiếp tục sai nếu gửi lại. |
| UNAUTHENTICATED / PERMISSION_DENIED | Không | Cần credential hoặc quyền phù hợp, không phải retry cùng request. |
| FAILED_PRECONDITION | Thường không | Điều kiện nghiệp vụ cần thay đổi trước khi thử lại. |

Status code là một phần hợp đồng giữa client và server. Không trả UNAVAILABLE cho lỗi validation hoặc lỗi nghiệp vụ chỉ để kích hoạt retry. Làm vậy có thể khiến client tạo tải lặp và che giấu lỗi thực.

## 5. Cấu hình retry policy bằng service config

gRPC Java hỗ trợ service config để gắn policy với service hoặc method. Ví dụ dưới đây giới hạn retry cho method unary GetStock:

~~~java
Map<String, Object> retryPolicy = Map.of(
    "maxAttempts", 4.0,
    "initialBackoff", "0.1s",
    "maxBackoff", "1s",
    "backoffMultiplier", 2.0,
    "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
    "name", List.of(Map.of(
        "service", "acme.catalog.v1.CatalogService",
        "method", "GetStock")),
    "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig = Map.of(
    "methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("127.0.0.1", server.port())
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

Trong ví dụ, maxAttempts bao gồm attempt đầu tiên; giá trị 4 có nghĩa tối đa bốn lần thực hiện, không phải bốn lần retry cộng thêm lần đầu. Backoff tăng theo multiplier cho tới maxBackoff. Runtime còn có thể áp dụng jitter để tránh nhiều client retry đồng loạt.

Tên service/method phải khớp full service name và method name trong Protobuf. Service config sai cấu trúc hoặc sai kiểu có thể bị từ chối khi tạo channel. Hãy dùng cấu hình được quản lý bởi resolver hoặc defaultServiceConfig phù hợp với phiên bản gRPC Java trong dự án. Bảo đảm retry không bị disable ở channel.

Không áp dụng retry policy rộng cho mọi method nếu có method tạo side effect. Ưu tiên khai báo policy ở method có hợp đồng retry rõ ràng.

## 6. Deadline bao trùm toàn bộ attempts

Deadline là ngân sách thời gian cho toàn RPC, không phải ngân sách riêng cho mỗi attempt. Thời gian chờ backoff cũng tiêu thụ ngân sách đó.

~~~java
CatalogServiceGrpc.CatalogServiceBlockingStub stub =
    CatalogServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

StockReply reply = stub.getStock(
    StockRequest.newBuilder()
        .setSku("SKU-42")
        .build());
~~~

Nếu deadline còn rất ít sau attempt đầu, runtime có thể không còn thời gian để thực hiện attempt tiếp theo. Không đặt deadline quá ngắn rồi kết luận retry không hoạt động. Ngược lại, deadline quá dài có thể giữ tài nguyên lâu trong khi server đang lỗi.

Trong integration test, deadline RPC và timeout của test framework phải hữu hạn. Timeout của latch/future nên dài hơn deadline RPC một khoảng nhỏ để test có thể thu thập kết quả cuối.

## 7. Idempotency bảo vệ side effect khi retry

Retry có thể tạo duplicate execution. Ví dụ client gửi yêu cầu tạo đơn hàng, server ghi đơn thành công nhưng response bị mất do server restart. Client thấy UNAVAILABLE rồi gửi lại. Nếu server không nhận diện request trùng, hệ thống có thể tạo hai đơn.

Một operation idempotent cho cùng một idempotency key sẽ tạo cùng kết quả logic khi được thực hiện nhiều lần. Thiết kế thường gồm:

- Client tạo request ID/idempotency key duy nhất cho một operation logic.
- Server lưu key cùng kết quả hoặc trạng thái xử lý trong storage bền vững.
- Khi nhận lại key đã xử lý, server trả kết quả đã lưu thay vì lặp side effect.
- Việc ghi key và side effect phải có tính nguyên tử hoặc có cơ chế khôi phục nhất quán.

~~~proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
~~~

Không tạo idempotency key mới mỗi lần retry. Các attempt của cùng một operation phải dùng cùng key. Với operation đọc dữ liệu, retry thường dễ an toàn hơn; với operation ghi, cần hợp đồng idempotency rõ ràng.

## 8. Kiểm thử retry có kiểm soát

Một test ổn định có thể tạo service giả lập trả UNAVAILABLE ở hai lần đầu rồi thành công ở lần thứ ba. Bộ đếm invocation chứng minh số attempt thực tế:

~~~java
final class RetryCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    final AtomicInteger attempts = new AtomicInteger();

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        int attempt = attempts.incrementAndGet();
        if (attempt < 3) {
            responseObserver.onError(
                Status.UNAVAILABLE
                    .withDescription("Temporary test failure")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(
            StockReply.newBuilder().setAvailable(7).build());
        responseObserver.onCompleted();
    }
}
~~~

Khởi động server với service test này, tạo channel có retry policy cho đúng method, gọi stub và assert:

~~~java
StockReply reply = stub.getStock(
    StockRequest.newBuilder().setSku("SKU-42").build());

assertEquals(7, reply.getAvailable());
assertEquals(3, retryService.attempts.get());
~~~

Test cần dùng deadline đủ cho backoff và không có response headers được gửi trước các lỗi thử lại. Server implementation ở ví dụ chỉ gọi onError; nếu thêm metadata/headers trước lỗi, call có thể bị commit và retry sẽ không diễn ra như mong đợi.

Không dùng Thread.sleep để đoán số attempt. Có thể dùng latch trong service test để điều khiển từng lần xử lý và quan sát invocation count. Giữ backoff nhỏ nhưng hữu hạn để suite không chậm.

## 9. Retry không thay thế application-level resume cho streaming

Đối với client-streaming hoặc bidirectional streaming, lỗi có thể xảy ra sau khi server đã nhận và xử lý một phần message. Việc mở một stream mới không tự khôi phục vị trí xử lý.

Thiết kế resume ở tầng ứng dụng:

- Gắn sequence number hoặc offset vào mỗi message.
- Server xác nhận checkpoint đã ghi bền vững.
- Client lưu checkpoint cuối đã được xác nhận.
- Khi reconnect, client mở stream mới và tiếp tục từ sequence tiếp theo.
- Dùng idempotency key để xử lý an toàn message có thể được gửi lại.

Với stream dài hạn, retry policy của gRPC không phải cơ chế phục hồi toàn bộ phiên. Hãy kiểm thử reconnect/resume bằng cách dừng server sau một số message, khởi động lại rồi xác minh không mất hoặc nhân đôi dữ liệu đã xác nhận.

## 10. ManagedChannel làm gì khi server restart?

ManagedChannel quản lý kết nối và có thể chuyển qua các trạng thái như IDLE, CONNECTING, READY, TRANSIENT_FAILURE và SHUTDOWN. Khi kết nối bị mất, channel có thể thử kết nối lại theo backoff. Khi server trở lại cùng địa chỉ và port, channel có thể thiết lập transport mới mà client không cần tạo channel mới.

Tuy nhiên:

- Channel reconnect không bảo đảm RPC đang chạy được tiếp tục.
- Call đã thất bại không tự sống lại chỉ vì server đã READY.
- RPC mới có thể thành công sau khi channel kết nối lại.
- Nếu server chuyển sang port mới, channel đang trỏ tới địa chỉ cũ không tự biết port mới trừ khi resolver/service discovery cập nhật endpoint.

Giữ channel dùng lâu dài theo vòng đời client. Không tạo channel mới cho từng retry; điều đó bỏ qua connection pooling, resolver và backoff mà ManagedChannel đã cung cấp.

## 11. wait-for-ready khác retry

Phương thức withWaitForReady yêu cầu client chờ channel trở lại trạng thái có thể gửi call thay vì fail ngay khi channel đang ở trạng thái tạm thời không khả dụng. Call vẫn chịu deadline; nếu server không phục hồi trước deadline, call thất bại.

wait-for-ready không phát lại một call đã commit và cũng không bảo đảm server sẽ xử lý thành công. Nó điều khiển thời điểm call được gửi qua channel. Retry policy điều khiển việc thực hiện lại một call đủ điều kiện sau status có thể retry.

Không dùng wait-for-ready cho mọi call nếu việc xếp hàng request trong thời gian server lỗi có thể làm tăng tải đột ngột sau khi server phục hồi. Đặt deadline, giới hạn concurrency và chỉ bật cho method phù hợp.

## 12. Kiểm thử server restart trên cùng endpoint

Để kiểm tra channel reconnect, client phải tiếp tục trỏ tới cùng địa chỉ sau khi server được khởi động lại. Một fixture test có thể:

1. Khởi động server trên port động và ghi lại port đã cấp.
2. Tạo channel trỏ tới port đó và xác nhận RPC thành công.
3. Dừng server graceful và đợi server terminated.
4. Khởi động server mới trên chính port đã ghi.
5. Dùng channel cũ gọi một RPC mới với deadline và wait-for-ready nếu kịch bản cần chờ reconnect.
6. Xác nhận RPC mới thành công sau khi transport được thiết lập lại.

Server restart fixture phải đợi server cũ giải phóng port trước khi bind lại. Nếu bind cùng port thất bại, test cần báo lỗi rõ ràng thay vì âm thầm chọn port khác, vì đổi port sẽ không còn kiểm tra channel reconnect tới endpoint cũ.

Nếu test khởi động server mới trên port khác, hãy tạo channel mới hoặc cập nhật resolver. Đó là test endpoint discovery/update, không phải test reconnect tới cùng endpoint.

Ví dụ helper tối giản cho fixture sở hữu server:

~~~java
synchronized void restartOnSamePort() throws InterruptedException {
    Server old = server;
    int oldPort = old.getPort();

    old.shutdown();
    if (!old.awaitTermination(5, TimeUnit.SECONDS)) {
        old.shutdownNow();
        throw new IllegalStateException("Old server did not terminate");
    }

    try {
        server = NettyServerBuilder.forPort(oldPort)
            .addService(service)
            .build()
            .start();
    } catch (IOException ex) {
        throw new IllegalStateException(
            "Cannot restart gRPC server on the same port", ex);
    }
}
~~~

Test có thể giữ channel cũ và gọi lại sau restart:

~~~java
grpcServer.restartOnSamePort();

StockReply reply = stub.withWaitForReady()
    .withDeadlineAfter(5, TimeUnit.SECONDS)
    .getStock(StockRequest.newBuilder().setSku("SKU-42").build());

assertEquals(7, reply.getAvailable());
~~~

Đây là minh họa cho server fixture đơn service; fixture thực tế cần đồng bộ truy cập server field và giữ cùng danh sách service/interceptor khi tạo server mới. Test nên xác nhận RPC thành công sau khi channel reconnect, không chỉ xác nhận restart helper trả về.

## 13. RPC đang chạy khi server dừng

Một call đang chạy có thể nhận UNAVAILABLE, CANCELLED hoặc status transport khác khi server dừng; status quan sát được phụ thuộc thời điểm và transport. Nếu server đã thực hiện side effect nhưng response chưa tới client, kết quả nghiệp vụ có thể không xác định từ phía client.

Test restart nên phân biệt:

- **Call trước khi dừng**: đang xử lý và bị gián đoạn.
- **Call trong thời gian server dừng**: fail ngay hoặc chờ nếu dùng wait-for-ready.
- **Call sau khi server phục hồi**: thành công qua channel đã reconnect.

Không khẳng định call đang chạy sẽ được tiếp tục từ đúng instruction hoặc message cuối. Với operation có side effect, dùng idempotency key và truy vấn trạng thái operation để client xác định kết quả.

## 14. Điều phối restart trong Spring test context

Nếu server do Spring gRPC starter quản lý, restart cần đi qua lifecycle API được starter hỗ trợ. Nếu test tự quản lý server, fixture có thể đóng và tạo lại io.grpc.Server trong cùng test.

Khi shutdown bắt đầu, readiness nên chuyển sang NOT_SERVING để load balancer/client health checking ngừng gửi call mới. Sau đó server dừng graceful trong thời hạn; nếu không kết thúc mới dùng shutdownNow. Khi server mới sẵn sàng, cập nhật health state về SERVING.

Không gọi shutdown server do Spring context sở hữu từ từng @AfterEach nếu context được cache và chia sẻ giữa test. Test restart có thể cần một context riêng hoặc fixture có quyền điều khiển lifecycle rõ ràng. Client channel phải được đóng trong teardown cuối cùng.

## 15. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi channel reconnect là RPC retry | Call đang chạy vẫn thất bại | Kiểm thử riêng reconnect và retry policy. |
| Retry mọi status | Lặp request sai hoặc tăng tải khi quá tải | Chỉ chọn status tạm thời phù hợp. |
| Retry operation ghi không idempotent | Tạo duplicate side effect | Dùng idempotency key và lưu kết quả. |
| Đặt deadline quá ngắn | Backoff tiêu hết ngân sách trước attempt tiếp theo | Chọn deadline đủ cho tổng attempts/backoff. |
| Server gửi response headers trước lỗi | Call đã commit, retry không còn xảy ra | Hiểu commitment point và thiết kế test đúng. |
| Kết luận retry không hoạt động từ streaming test | Streaming có semantics retry khác unary | Dùng unary để test policy; resume stream ở tầng ứng dụng. |
| Restart server trên port mới nhưng giữ channel cũ | Channel tiếp tục gọi endpoint cũ | Giữ cùng port hoặc cập nhật resolver/recreate channel. |
| Dùng Thread.sleep để đợi reconnect | Test flaky theo tốc độ máy | Dùng latch, wait-for-ready và deadline. |
| Không kiểm tra server invocation count | Không biết call có được thực thi nhiều lần | Dùng counter hoặc idempotency store trong test. |

## 16. Ma trận kiểm thử retry và restart

Một bộ integration test nên có các trường hợp:

1. Unary method trả UNAVAILABLE hai lần rồi thành công: client nhận response và server ghi nhận ba attempts.
2. Status không retryable như INVALID_ARGUMENT: chỉ có một lần thực thi.
3. Deadline hết trước khi backoff hoàn tất: client nhận DEADLINE_EXCEEDED.
4. Server dừng khi RPC đang chạy: client quan sát lỗi và operation được kiểm tra bằng idempotency key.
5. Server restart trên cùng port: channel cũ kết nối lại và RPC mới thành công.
6. Server restart trên port mới: resolver được cập nhật hoặc client tạo channel mới.
7. Client dùng wait-for-ready trong thời gian server tạm dừng: call chờ tới khi server phục hồi hoặc deadline hết.
8. Streaming bị gián đoạn sau checkpoint: client resume từ checkpoint mà không mất/nhân đôi message đã xác nhận.

Test cần đặt deadline, timeout chờ và số attempt hữu hạn. Ghi nhận status, invocation count, endpoint/port và thời điểm server lifecycle để chẩn đoán lỗi.

## 17. Bài tập thực hành

Xây dựng integration test cho CatalogService:

1. Cấu hình retry policy cho unary GetStock, chỉ retry UNAVAILABLE, tối đa bốn attempts.
2. Tạo test service trả UNAVAILABLE ở hai lần đầu rồi thành công.
3. Assert response cuối và invocation count.
4. Tạo case INVALID_ARGUMENT và xác nhận không retry.
5. Dừng server sau khi channel đã kết nối, sau đó restart server trên cùng port.
6. Dùng channel cũ gọi RPC mới và xác nhận channel reconnect.
7. Tạo một RPC đang chạy khi server dừng; xác minh lỗi và kiểm tra trạng thái operation bằng idempotency key.
8. Nếu có streaming upload, bổ sung sequence/checkpoint và test resume riêng.

**Tiêu chí hoàn thành:** phân biệt được retry với reconnect, cấu hình policy đúng method/status, kiểm soát deadline, chứng minh channel phục hồi sau restart và không tạo duplicate side effect.

## 18. Ghi nhớ

- Retry thực hiện lại một RPC đủ điều kiện; reconnect chỉ khôi phục transport của ManagedChannel.
- Configured retry dựa trên service config, retryable status codes, max attempts và backoff.
- Một call đã commit không được gRPC retry tự động; response headers là một điểm commit quan trọng.
- Deadline bao trùm mọi attempts và thời gian backoff.
- Operation có side effect cần idempotency key để tránh thực thi trùng.
- Streaming RPC cần checkpoint/resume ở tầng ứng dụng khi lỗi sau khi đã trao đổi message.
- Channel có thể reconnect tới cùng endpoint sau server restart, nhưng call đang chạy không tự tiếp tục.
- wait-for-ready trì hoãn gửi call khi channel tạm thời không khả dụng; nó không thay retry policy.
- Test restart cùng endpoint phải bind lại đúng port; port mới cần resolver update hoặc channel mới.
- Kiểm thử riêng retry, reconnect, in-flight failure và resume để kết luận đúng về độ tin cậy.

Kiểm thử retry và server restart giúp xác nhận dịch vụ Spring gRPC phục hồi đúng trước lỗi tạm thời, giới hạn việc thực thi lặp và giữ kết quả nghiệp vụ nhất quán khi transport bị gián đoạn.
