# Recovery sau restart

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt graceful shutdown, process crash và restart của gRPC server.
- Giải thích ManagedChannel reconnect tới endpoint sau khi server khởi động lại.
- Nhận diện vì sao RPC đang chạy có thể thất bại dù server mới đã sẵn sàng.
- Chọn retry, wait-for-ready và deadline phù hợp cho RPC mới.
- Bảo vệ operation có side effect bằng idempotency key.
- Khôi phục streaming session bằng sequence/cursor ở tầng ứng dụng.
- Tổ chức readiness, service discovery và integration test cho kịch bản restart.

## 1. Restart là một tình huống lỗi cần thiết kế trước

gRPC server có thể restart do deploy phiên bản mới, scale/recreate container, process crash, máy chủ reboot hoặc thao tác vận hành. Trong khoảng thời gian server dừng, client có thể không thiết lập được transport mới; các RPC đang chạy có thể bị ngắt và RPC mới có thể phải chờ hoặc thất bại.

Với **SPRING_GRPC**, độ tin cậy không chỉ là server khởi động lại thành công. Client cần biết khi nào có thể gọi lại, operation trước đã hoàn tất hay chưa, stream cần resume từ đâu và service chỉ được đánh dấu sẵn sàng khi dependency cần thiết đã hoạt động.

Recovery sau restart gồm nhiều lớp:

- Transport reconnect để tạo lại kết nối tới endpoint.
- RPC retry hoặc wait-for-ready để xử lý call phù hợp.
- Idempotency để tránh lặp side effect khi kết quả lần gọi trước không rõ.
- Persistence và checkpoint để khôi phục trạng thái nghiệp vụ.
- Readiness/service discovery để điều phối traffic tới instance sẵn sàng.

Không một cơ chế đơn lẻ nào bảo đảm toàn bộ các lớp này.

## 2. Graceful shutdown và process crash

Hai kiểu dừng server có hành vi khác nhau:

| Tình huống | Hành vi | Ảnh hưởng tới client |
| --- | --- | --- |
| Graceful shutdown | Server ngừng nhận call mới và cho call đang chạy cơ hội hoàn tất trong thời gian drain | Call đang chạy có thể hoàn tất; call mới cần được chuyển sang instance khác hoặc chờ. |
| Shutdown cưỡng bức | Server yêu cầu hủy call đang hoạt động và dừng transport | Call đang chạy có thể nhận lỗi hoặc cancellation. |
| Process crash / node mất | Server không thể thực hiện lifecycle shutdown | Transport bị đứt; client phát hiện lỗi và thử kết nối lại. |
| Restart cùng endpoint | Process mới bind lại cùng địa chỉ/port | Channel có thể reconnect và gửi các RPC mới. |
| Restart với endpoint mới | Địa chỉ instance thay đổi | Resolver/load balancer phải cập nhật endpoint; channel cần nhìn thấy địa chỉ mới. |

Graceful shutdown giúp giảm số RPC bị ngắt, nhưng không bảo đảm mọi call đều hoàn tất. Call có thể vượt drain timeout hoặc bị gián đoạn do dependency lỗi. Process crash không có cơ hội chạy cleanup; dữ liệu cần khôi phục phải được lưu bền vững trước đó.

## 3. ManagedChannel reconnect sau khi server trở lại

ManagedChannel đại diện cho một logical target và quản lý transport, resolver, load balancing cùng backoff. Khi kết nối bị mất, channel có thể chuyển qua các trạng thái như IDLE, TRANSIENT_FAILURE, CONNECTING rồi READY khi kết nối được thiết lập lại.

Nếu server mới lắng nghe trên cùng target, client thường có thể tiếp tục dùng channel cũ. Không cần tạo một channel mới cho từng lần server restart. Reconnect chỉ khôi phục khả năng thiết lập transport; nó không tự phục hồi business operation đã bị ngắt.

Một channel không tự biết endpoint mới nếu client trỏ trực tiếp tới một IP/port đã thay đổi. Trong môi trường container/orchestrator, dùng DNS/service discovery hoặc resolver ổn định để channel nhận được danh sách endpoint mới.

## 4. Channel reconnect không đồng nghĩa RPC được replay

Đây là khác biệt quan trọng nhất khi thiết kế recovery:

- **Reconnect** thiết lập lại transport cho các RPC mới.
- **Retry** thực hiện lại một RPC đủ điều kiện sau một lỗi.
- **Wait-for-ready** cho phép một RPC mới chờ channel trở lại trạng thái có thể gửi, thay vì fail ngay khi channel tạm thời không khả dụng.
- **Resume** khôi phục một stream hoặc workflow từ checkpoint do ứng dụng định nghĩa.

Một RPC đang chạy khi server crash có thể thất bại dù channel reconnect thành công vài giây sau. gRPC không thể biết server đã thực hiện side effect hay chưa nếu response chưa tới client.

Vì vậy, không được suy luận “client nhận UNAVAILABLE nên server chưa làm gì”. Server có thể đã ghi database thành công trước khi kết nối bị ngắt. Với operation có side effect, cần idempotency key hoặc API truy vấn trạng thái operation.

## 5. Connectivity state và readiness

gRPC Java cung cấp connectivity state để quan sát channel:

- IDLE: channel chưa cần tạo transport hoặc đang ở trạng thái nhàn rỗi.
- CONNECTING: đang thiết lập kết nối.
- READY: có transport sẵn sàng nhận RPC.
- TRANSIENT_FAILURE: kết nối tạm thời thất bại và runtime sẽ thử lại theo backoff.
- SHUTDOWN: channel đã đóng và không thể dùng cho call mới.

Có thể quan sát state khi chẩn đoán:

~~~java
ConnectivityState state = channel.getState(true);
log.info("gRPC channel state: {}", state);
~~~

Tham số true yêu cầu channel bắt đầu kết nối nếu đang IDLE. Trong ứng dụng thật, tránh vòng lặp polling liên tục. Có thể dùng notifyWhenStateChanged để nhận tín hiệu state thay đổi, nhưng READY chỉ mô tả transport; nó không chứng minh mọi dependency nghiệp vụ đã sẵn sàng.

Nếu hệ thống bật gRPC Health Checking Protocol, client/load balancer có thể kiểm tra trạng thái service riêng. Health service cần báo SERVING khi service thực sự nhận traffic được và NOT_SERVING trong lúc khởi động, drain hoặc dependency bắt buộc chưa sẵn sàng.

## 6. Wait-for-ready cho RPC mới

Khi server tạm thời không khả dụng, một RPC mới có thể fail ngay với lỗi transport. withWaitForReady() cho phép call chờ channel có thể gửi request:

~~~java
InventoryServiceGrpc.InventoryServiceBlockingStub recoveryStub =
    InventoryServiceGrpc.newBlockingStub(channel)
        .withWaitForReady()
        .withDeadlineAfter(4, TimeUnit.SECONDS);

GetAvailabilityResponse response =
    recoveryStub.getAvailability(request);
~~~

Wait-for-ready không tạo thêm thời gian vô hạn. Deadline vẫn giới hạn toàn bộ thời gian chờ và xử lý. Nếu server không trở lại trước deadline, call thất bại.

Chỉ dùng wait-for-ready khi việc chờ có ý nghĩa nghiệp vụ. Nếu một request đã quá hạn khi server phục hồi, xử lý nó có thể gây tải dồn hoặc thực hiện một hành động không còn cần thiết. Với request tương tác người dùng, deadline có thể ngắn; với công việc nền, có thể dùng queue bền vững thay vì giữ RPC chờ.

## 7. Retry sau restart

Retry phù hợp khi lỗi có khả năng tạm thời và operation an toàn khi thực hiện lại. gRPC Java có transparent retry trong một số tình huống runtime biết request chưa tới application; configured retry có thể được khai báo trong service config cho method cụ thể.

Retry policy thường xác định:

- maxAttempts: tổng số lần thực hiện tối đa, bao gồm attempt đầu.
- initialBackoff và maxBackoff: khoảng chờ ban đầu và giới hạn.
- backoffMultiplier: hệ số tăng backoff.
- retryableStatusCodes: status được phép thử lại.

Ví dụ minh họa service config cho method đọc tồn kho:

~~~java
Map<String, Object> retryPolicy = Map.of(
    "maxAttempts", 3.0,
    "initialBackoff", "0.1s",
    "maxBackoff", "1s",
    "backoffMultiplier", 2.0,
    "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
    "name", List.of(Map.of(
        "service", "acme.inventory.v1.InventoryService",
        "method", "GetAvailability")),
    "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig = Map.of(
    "methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress(host, port)
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

Tên service/method phải khớp RPC path trong Protobuf. Cấu hình thực tế cần tương thích phiên bản gRPC Java và resolver đang dùng. Không bật retry rộng cho mọi method nếu chưa phân tích side effect và tải khi server phục hồi.

### Khi nào runtime còn có thể retry?

gRPC chỉ retry một call khi runtime còn đủ điều kiện phát lại call history. Khi client nhận response headers, call được xem là committed và runtime không tự retry call đó nữa. Call cũng có thể không còn retry được nếu retry buffer không đủ giữ dữ liệu cần thiết.

Vì vậy, server có thể đã bắt đầu hoặc thậm chí hoàn tất side effect trong khi client chưa nhận response. Retry policy không phải cam kết exactly-once. Với command ghi dữ liệu, idempotency key vẫn cần thiết ngay cả khi retry chỉ được cấu hình cho UNAVAILABLE.

## 8. Chọn status có thể retry

UNAVAILABLE thường phù hợp với lỗi tạm thời như server đang restart hoặc transport không khả dụng. Tuy nhiên, status này không chứng minh operation chưa được thực hiện.

Các status khác cần được cân nhắc theo semantics:

| Status | Hướng xử lý thường gặp |
| --- | --- |
| UNAVAILABLE | Có thể retry có giới hạn nếu operation an toàn. |
| RESOURCE_EXHAUSTED | Chỉ retry khi có chính sách phục hồi/quota rõ; retry ngay có thể làm quá tải nặng hơn. |
| DEADLINE_EXCEEDED | Thận trọng vì deadline đã hết và operation trước có thể đã hoàn tất. |
| ABORTED | Có thể cần chạy lại transaction ở tầng ứng dụng. |
| INVALID_ARGUMENT | Không retry cùng request sai. |
| UNAUTHENTICATED / PERMISSION_DENIED | Sửa credential/quyền trước khi gọi lại. |
| FAILED_PRECONDITION | Thay đổi điều kiện nghiệp vụ rồi mới thử lại. |

Retry cần backoff và jitter để nhiều client không cùng reconnect/retry tại một thời điểm tạo thành retry storm. Tổng thời gian retry vẫn phải nằm trong deadline hoặc business deadline đã xác định.

## 9. Idempotency bảo vệ side effect

Giả sử client gọi CreateOrder. Server ghi order thành công, sau đó process crash trước khi response tới client. Client nhận UNAVAILABLE và không biết order đã được tạo hay chưa. Nếu gửi lại request mà server không nhận diện lần lặp, có thể tạo hai order.

Thiết kế idempotency:

1. Client tạo một idempotency key cho operation logic.
2. Mọi attempt retry của operation đó dùng cùng key.
3. Server lưu key cùng kết quả hoặc trạng thái xử lý trong storage bền vững.
4. Khi nhận key đã xử lý, server trả kết quả đã lưu thay vì lặp side effect.
5. Việc lưu key và thay đổi nghiệp vụ cần cùng transaction hoặc có cơ chế khôi phục nhất quán.

~~~proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
~~~

Không tạo key mới cho mỗi attempt. Key mới biến retry thành operation mới và không còn bảo vệ duplicate.

## 10. Server cần readiness trước khi nhận traffic

Process vừa mở port chưa chắc đã xử lý được RPC. Server có thể còn đang kết nối database, tải cache, đăng ký service hoặc khôi phục state.

Một quy trình khởi động an toàn:

1. Khởi tạo Spring ApplicationContext và các dependency.
2. Khởi động gRPC listener.
3. Kiểm tra dependency bắt buộc và trạng thái application.
4. Đăng ký/đánh dấu service là SERVING khi có thể nhận traffic.
5. Cho resolver/load balancer đưa instance vào pool.

Nếu dùng health checking, cập nhật health status theo lifecycle. Không đánh dấu SERVING chỉ vì socket đã bind. Khi restart, client có thể reconnect rất sớm; readiness ngăn request tới instance chưa sẵn sàng.

## 11. Graceful shutdown khi deploy

Trước khi dừng server:

- Đánh dấu instance NOT_SERVING hoặc loại khỏi service discovery.
- Ngừng nhận RPC mới và bắt đầu drain.
- Cho RPC đang chạy thời gian hoàn tất trong giới hạn cấu hình.
- Hủy các stream dài hạn hoặc thông báo client reconnect theo contract.
- Đóng dependency/executor theo thứ tự lifecycle.

Trong Spring, server do starter quản lý nên được dừng theo lifecycle của starter/application context. Không tự shutdown server dùng chung từ một request handler hoặc test method.

Graceful shutdown chỉ giảm gián đoạn; client vẫn cần xử lý lỗi transport vì process có thể crash hoặc vượt thời gian drain. Deadline của RPC nên ngắn hơn hoặc tương thích với thời gian drain để call không giữ tài nguyên vô hạn.

## 12. Service discovery và endpoint sau restart

Nếu server restart trên cùng địa chỉ/port, channel đang trỏ tới endpoint đó có thể reconnect sau khi listener mới sẵn sàng.

Trong môi trường nhiều instance:

- Dùng DNS, service mesh hoặc resolver thay vì lưu pod IP cố định trong client.
- Resolver cần cập nhật danh sách endpoint khi instance cũ bị loại và instance mới xuất hiện.
- Load balancer chỉ chọn backend cho RPC mới; stream đang mở thường vẫn gắn với backend cũ.
- Khi instance bị drain, client cần reconnect và mở RPC mới.
- Kiểm tra timeout/connection draining của proxy và load balancer để tránh cắt stream ngoài dự kiến.

Không nhầm reconnect tới cùng endpoint với discovery endpoint mới. Nếu channel dùng forAddress tới IP cũ, server restart ở IP khác không làm channel tự biết địa chỉ mới.

## 13. Khôi phục server-streaming và bidirectional stream

Một stream đang mở không tự di chuyển sang server mới. Khi server restart, client cần nhận terminal error/cancellation, sau đó mở RPC mới.

Để không mất dữ liệu:

1. Mỗi message có sequence hoặc event ID ổn định.
2. Client lưu cursor cuối cùng đã xử lý thành công.
3. Khi reconnect, client gửi cursor để server tiếp tục từ vị trí tương ứng.
4. Server đọc lại event từ nguồn có retention rồi chuyển sang live feed.
5. Client deduplicate nếu message cuối được gửi lại.
6. Nếu cursor hết hạn, server yêu cầu snapshot/resync.

Nếu source chỉ giữ dữ liệu trong memory của process, restart sẽ làm mất state đó. Cần lưu event/checkpoint ở database hoặc event log khi yêu cầu recovery bao gồm dữ liệu phát sinh trong thời gian server offline.

Với bidirectional stream, client cũng phải khôi phục trạng thái của chiều gửi: sequence cuối đã được server xác nhận, message chưa xác nhận và idempotency key cho từng operation.

## 14. Trạng thái phiên không nên chỉ nằm trong memory

Một server process có thể giữ subscription, session map hoặc workflow state trong memory. Khi process restart, các cấu trúc đó mất đi.

Hãy phân loại state:

- Ephemeral state: cache có thể tái tạo, connection và observer; có thể mất khi restart.
- Durable business state: order, payment, workflow progress; phải lưu trong storage bền vững.
- Recoverable stream state: cursor, sequence, checkpoint; cần lưu nếu client phải resume.
- Derived state: cache/index có thể rebuild từ database hoặc event log.

Không cố serialize toàn bộ Netty channel hoặc StreamObserver để khôi phục sau restart. Khôi phục logical operation/session từ dữ liệu bền vững, rồi tạo RPC/transport mới.

## 15. Kiểm thử restart bằng cùng endpoint

Một integration test có thể khởi động server trên port động, giữ channel, dừng server rồi bind server mới trên chính port đó:

~~~java
Server first = NettyServerBuilder.forPort(0)
    .addService(service)
    .build()
    .start();

int port = first.getPort();
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("127.0.0.1", port)
    .usePlaintext()
    .build();

InventoryServiceGrpc.InventoryServiceBlockingStub stub =
    InventoryServiceGrpc.newBlockingStub(channel)
        .withWaitForReady()
        .withDeadlineAfter(5, TimeUnit.SECONDS);

first.shutdown();
if (!first.awaitTermination(5, TimeUnit.SECONDS)) {
    first.shutdownNow();
    throw new IllegalStateException("First server did not stop");
}

Server second = NettyServerBuilder.forPort(port)
    .addService(service)
    .build()
    .start();

GetAvailabilityResponse response = stub.getAvailability(request);
~~~

Đây là skeleton cho test fixture tự sở hữu server. Test thực tế cần try/finally để đóng channel và server thứ hai, đồng thời xử lý trường hợp bind lại port thất bại. Giữ cùng channel để xác minh reconnect; nếu tạo channel mới sau restart, test chỉ chứng minh server mới nhận call chứ chưa chứng minh channel cũ phục hồi.

Port được chọn ban đầu bằng forPort(0) nên không hard-code cổng chung cho suite. Khi restart, fixture cố ý bind lại port thực tế để giữ nguyên endpoint của client.

## 16. Kiểm thử RPC đang chạy khi restart

Tạo một handler test có thể chặn ở latch:

1. Client bắt đầu RPC và server báo handler đã vào.
2. Test dừng server khi handler chưa hoàn tất.
3. Client quan sát terminal status/error của call đang chạy.
4. Test restart server trên cùng endpoint.
5. Client dùng channel cũ gọi một RPC mới và xác nhận thành công.
6. Nếu operation trước có side effect, truy vấn trạng thái bằng idempotency key để xác định đã commit hay chưa.

Không assert rằng mọi transport/version luôn trả cùng một status cho call đang chạy. Tùy thời điểm server stop, client có thể thấy UNAVAILABLE, CANCELLED hoặc lỗi deadline/transport khác. Assert hành vi hợp đồng và việc call kết thúc, sau đó xác minh recovery của call mới.

## 17. Các kịch bản recovery cần có

Một bộ integration test nên bao gồm:

1. Server graceful restart: call mới thành công sau khi server mới ready.
2. Server abrupt stop: channel nhận biết lỗi transport và reconnect sau restart.
3. In-flight unary RPC bị ngắt: client không giả định operation chưa commit.
4. Retryable UNAVAILABLE: retry có giới hạn và deadline.
5. Non-retryable status: client không lặp request vô ích.
6. Wait-for-ready: call mới chờ server trở lại hoặc deadline hết.
7. Endpoint thay đổi: resolver/service discovery cung cấp địa chỉ mới.
8. Server-streaming restart: client reconnect bằng cursor và phát hiện gap/duplicate.
9. Readiness: instance chỉ nhận traffic sau khi dependency cần thiết sẵn sàng.
10. Idempotency: retry cùng key không tạo side effect trùng.

Test nên dùng latch và timeout thay vì Thread.sleep(). Ghi nhận server lifecycle, channel state, invocation count và cursor để chẩn đoán.

## 18. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ channel reconnect sẽ replay RPC đang chạy | Operation bị mất hoặc client hiểu sai kết quả | Phân biệt reconnect và retry. |
| Retry mọi UNAVAILABLE mà không idempotency | Duplicate side effect | Dùng idempotency key và trạng thái operation. |
| Tạo channel mới cho mỗi lần retry | Connection churn và khó quan sát recovery | Reuse ManagedChannel theo target. |
| Không đặt deadline | Call chờ vô hạn khi server không trở lại | Deadline hữu hạn theo latency budget. |
| Bật wait-for-ready cho mọi RPC | Request cũ có thể dồn lại sau restart | Chỉ bật khi chờ còn ý nghĩa và có deadline. |
| Đánh dấu readiness ngay khi bind port | Traffic đến trước khi dependency sẵn sàng | Health/readiness theo trạng thái ứng dụng. |
| Giữ session/sequence chỉ trong memory | Restart làm mất khả năng resume | Lưu durable checkpoint/event khi cần. |
| Coi stream tự resume sau restart | Mất message trong khoảng gián đoạn | Cursor, replay và deduplication ở tầng ứng dụng. |
| Dùng IP instance cố định | Không theo kịp endpoint mới | DNS/resolver/service discovery. |
| Chỉ test call mới sau restart | Bỏ sót hành vi in-flight RPC | Test riêng call đang chạy và call mới. |

## 19. Bài tập thực hành

Thiết kế recovery cho InventoryService trong Spring gRPC:

1. Tạo server fixture có thể start/stop trên port động.
2. Tạo một ManagedChannel và giữ nó xuyên suốt lần restart.
3. Xác nhận unary RPC hoạt động trước khi dừng server.
4. Dừng server, khởi động lại trên cùng endpoint và xác nhận RPC mới qua channel cũ thành công.
5. Tạo một RPC đang chạy lúc server dừng và kiểm tra terminal status.
6. Thêm retry policy chỉ cho method đọc an toàn, với max attempts/backoff/deadline.
7. Thêm idempotency key cho command tạo order hoặc reservation.
8. Nếu có server-streaming, bổ sung sequence/cursor và kiểm thử resume sau restart.
9. Chỉ đánh dấu service SERVING sau khi dependency và recovery state sẵn sàng.
10. Kiểm tra graceful shutdown, cleanup channel/server và service discovery.

**Tiêu chí hoàn thành:** channel có thể reconnect, RPC mới thành công sau restart, call đang chạy được xử lý theo semantics rõ, retry không tạo side effect trùng và stream có cách resume được kiểm chứng.

## 20. Ghi nhớ

- Restart có thể graceful, cưỡng bức hoặc do process crash; mức độ gián đoạn khác nhau.
- ManagedChannel có thể reconnect tới cùng target nhưng không tự khôi phục mọi RPC đang chạy.
- Retry, wait-for-ready và reconnect là ba cơ chế khác nhau; streaming resume cần logic ứng dụng.
- Deadline giới hạn tổng thời gian chờ và retry; backoff giúp tránh retry storm.
- UNAVAILABLE có thể retry nếu operation an toàn, nhưng không chứng minh server chưa thực hiện side effect.
- Idempotency key bảo vệ command khi client không biết attempt trước đã commit hay chưa.
- Readiness phải phản ánh khả năng xử lý thật, không chỉ việc port đã bind.
- Service discovery cần cập nhật endpoint khi instance thay đổi.
- Stream dài hạn cần cursor, sequence, replay và deduplication nếu yêu cầu không mất dữ liệu.
- Durable business state phải nằm ngoài memory của process để sống qua restart.
- Kiểm thử riêng graceful/abrupt restart, in-flight RPC, call mới, readiness và resume.

Recovery sau restart đáng tin cậy khi transport reconnect, application xử lý lại call an toàn, dữ liệu nghiệp vụ được lưu bền vững và client có thể tiếp tục workflow từ checkpoint thay vì giả định process mới giữ nguyên trạng thái cũ.
