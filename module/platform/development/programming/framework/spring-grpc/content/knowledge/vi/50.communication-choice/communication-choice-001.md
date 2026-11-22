# Chọn gRPC cho RPC nội bộ độ trễ thấp

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện workload phù hợp với giao tiếp RPC nội bộ có yêu cầu độ trễ thấp.
- Giải thích lợi ích và giới hạn của gRPC, HTTP/2 và Protocol Buffers.
- So sánh gRPC với REST/JSON và message broker theo đặc tính giao tiếp.
- Đánh giá tác động của channel reuse, serialization, deadline, streaming và load balancing.
- Xác định điều kiện vận hành cần có trước khi chọn gRPC trong hệ sinh thái Spring.
- Đưa ra quyết định dựa trên latency phân vị, throughput, chi phí tài nguyên và khả năng tương thích.

## 1. Bài toán giao tiếp nội bộ độ trễ thấp

Trong kiến trúc microservices, một request từ người dùng có thể đi qua nhiều service: API gateway gọi hồ sơ, hồ sơ gọi quyền truy cập, đơn hàng gọi tồn kho và thanh toán. Mỗi hop bổ sung thời gian truyền mạng, xử lý, serialization, queueing và chờ dependency. Khi một request có nhiều hop tuần tự, độ trễ của từng RPC cộng dồn vào latency cuối cùng.

**SPRING_GRPC** tập trung phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC. Trong phạm vi này, chọn gRPC phù hợp khi các service nội bộ cần gọi nhau thường xuyên, payload có cấu trúc rõ, cần latency ổn định và cả hai phía có thể dùng generated client/server contract.

gRPC không tự động làm mọi request nhanh hơn. Nó cung cấp một transport và serialization phù hợp cho RPC hiệu quả; kết quả thực tế còn phụ thuộc cách tái sử dụng connection, kích thước message, xử lý server, số hop, network topology, TLS, proxy và mức độ cạnh tranh tài nguyên.

## 2. gRPC cung cấp những gì?

gRPC kết hợp một số thành phần:

- **Protocol Buffers** định nghĩa service, method và message; từ hợp đồng đó sinh mã Java cho client stub và server base class.
- **HTTP/2** vận chuyển RPC qua một kết nối có thể multiplex nhiều stream.
- **Unary RPC** gửi một request và nhận một response, phù hợp cho phần lớn lời gọi service-to-service ngắn.
- **Streaming RPC** cho phép một hoặc hai phía trao đổi nhiều message trên cùng một call.
- **Metadata** mang thông tin ngữ cảnh như authorization, trace ID và correlation ID.
- **Deadline và status code** biểu diễn ngân sách thời gian và kết quả call theo hợp đồng RPC.

Hợp đồng Protobuf giúp client và server chia sẻ kiểu dữ liệu rõ ràng, giảm nhu cầu serialize JSON và parse chuỗi field ở mỗi hop. Code generation cũng phát hiện nhiều lỗi tương thích ở thời điểm build thay vì đợi tới runtime.

## 3. Vì sao gRPC thường phù hợp với RPC nội bộ độ trễ thấp?

### Serialization nhị phân

Protobuf mã hóa message thành wire format nhị phân, thường gọn hơn JSON với cùng dữ liệu có cấu trúc. Message nhỏ hơn có thể giảm byte truyền qua mạng và chi phí parse/serialize. Mức tiết kiệm phụ thuộc schema, loại field, dữ liệu thực tế và cách JSON được nén.

### Multiplexing của HTTP/2

HTTP/2 cho phép nhiều RPC stream cùng hoạt động trên một kết nối TCP. Client không cần mở một kết nối mới cho từng call; channel có thể tái sử dụng transport và tránh lặp chi phí thiết lập connection.

Multiplexing giảm tranh chấp do phải tạo nhiều kết nối, nhưng không loại bỏ mọi hiện tượng head-of-line blocking ở tầng TCP. Mất packet trên một TCP connection vẫn có thể ảnh hưởng các stream cùng connection. Vì vậy, cần đo trên network topology thật.

### Hợp đồng và code generation

Generated stub cung cấp API Java có kiểu dữ liệu, method và request/response được xác định trước. Nó giảm boilerplate, hạn chế sai tên field và tạo cơ sở để kiểm soát tiến hóa API giữa các service.

### Deadline và status có ngữ nghĩa RPC

Client có thể đặt deadline cho call; server nhận biết cancellation/deadline để dừng công việc không còn hữu ích. Status code chuẩn giúp client phân biệt lỗi tạm thời, lỗi xác thực, validation và trạng thái nghiệp vụ.

Những đặc tính này đặc biệt hữu ích khi một request đi qua nhiều service và cần kiểm soát ngân sách latency xuyên suốt.

## 4. So sánh gRPC, REST/JSON và message broker

| Tiêu chí | gRPC | REST/JSON | Message broker |
| --- | --- | --- | --- |
| Mô hình | RPC đồng bộ hoặc streaming | HTTP request/response | Gửi/nhận message bất đồng bộ |
| Contract | Protobuf service/message | OpenAPI/JSON hoặc contract tương đương | Event/message schema |
| Serialization phổ biến | Protobuf nhị phân | JSON văn bản | Tùy broker và serializer |
| Kết nối | HTTP/2, channel có thể reuse | HTTP/1.1 hoặc HTTP/2 tùy stack | Kết nối tới broker |
| Latency | Phù hợp RPC trực tiếp, thường ít byte/parse hơn | Đơn giản và đủ nhanh cho nhiều API | Có thêm broker/queue; không phải lựa chọn mặc định cho request-response tức thời |
| Streaming | Unary, client/server/bidirectional streaming | Có thể dùng SSE/WebSocket hoặc cơ chế khác | Luồng event/consumer |
| Coupling | Client phụ thuộc service contract | Client phụ thuộc HTTP API contract | Producer/consumer tách thời điểm và thường tách vòng đời |
| Trình duyệt | Cần gRPC-Web/proxy hoặc gateway | Hỗ trợ trực tiếp | Thường cần backend hoặc gateway |
| Phù hợp | Service-to-service RPC có schema rõ | API công khai, tích hợp rộng và debug thuận tiện | Event-driven workflow, buffering và xử lý nền |

Không nên chọn gRPC chỉ vì Protobuf nhỏ hơn JSON. Nếu giao tiếp cần durable queue, consumer retry độc lập hoặc tách thời điểm producer/consumer, message broker phù hợp hơn. Nếu client là browser hoặc bên thứ ba cần HTTP dễ tiếp cận, REST có thể giảm chi phí tích hợp.

## 5. Khi nào nên chọn gRPC?

gRPC là ứng viên tốt khi phần lớn điều kiện sau đúng:

- Hai đầu giao tiếp do cùng tổ chức kiểm soát hoặc có quy trình chia sẻ Protobuf contract.
- Workload là RPC trực tiếp giữa service, thường xuyên và có yêu cầu latency/throughput rõ.
- Message có schema ổn định, có thể sinh mã và quản lý version.
- Client/server runtime hỗ trợ HTTP/2 và gRPC phù hợp.
- Cần unary hoặc streaming semantics, deadline, cancellation và status có cấu trúc.
- Có thể vận hành TLS, service discovery, load balancing, observability và debugging cho gRPC.

Ví dụ: OrderService cần kiểm tra tồn kho từ InventoryService trong luồng đặt hàng; ProfileService gọi PermissionService để quyết định quyền truy cập; một gateway nội bộ cần gọi nhiều backend có contract Protobuf.

## 6. Khi nào nên chọn REST hoặc message broker?

REST/JSON thường phù hợp hơn khi API cần được gọi trực tiếp từ browser, tích hợp với nhiều đối tác bên ngoài, cần khả năng khám phá/debug bằng công cụ HTTP phổ biến hoặc schema thay đổi độc lập với client. REST cũng có thể chạy trên HTTP/2; không nên giả định REST luôn dùng HTTP/1.1 hoặc luôn chậm.

Message broker phù hợp khi producer không cần chờ consumer xử lý ngay, cần buffering, fan-out, replay, consumer group hoặc xử lý nền bền vững. RPC đồng bộ gRPC giữ client chờ kết quả và gắn chặt latency của caller với dependency được gọi.

Một hệ thống có thể dùng cả ba: REST ở edge, gRPC giữa các service nội bộ và broker cho event/workflow bất đồng bộ. Chọn theo từng interaction, không cần ép toàn hệ thống dùng một giao thức.

## 7. Định nghĩa contract Protobuf cho RPC nội bộ

Ví dụ InventoryService cung cấp một unary RPC:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.grpc";
option java_multiple_files = true;

message GetAvailabilityRequest {
  string sku = 1;
  int32 requested_quantity = 2;
}

message GetAvailabilityResponse {
  bool available = 1;
  int32 available_quantity = 2;
}

service InventoryService {
  rpc GetAvailability(GetAvailabilityRequest)
      returns (GetAvailabilityResponse);
}
~~~

Package/version trong service name là một phần của RPC path. Khi phát hành contract, không tái sử dụng field number đã xóa và không đổi kiểu field tùy tiện. Thêm field optional theo quy tắc tương thích thường an toàn hơn thay đổi ý nghĩa của field đã tồn tại.

Contract nên mô tả dữ liệu cần thiết cho quyết định nghiệp vụ. Tránh gửi object graph khổng lồ hoặc dữ liệu không được caller sử dụng, vì payload lớn làm tăng serialization, network và memory cost.

## 8. Tái sử dụng ManagedChannel trong client Spring

Một nguyên nhân làm mất lợi ích latency của gRPC là tạo channel mới cho mỗi RPC. Channel quản lý connection, resolver, load balancing và transport; nên được tái sử dụng theo endpoint/target và vòng đời ứng dụng.

Ví dụ client component giữ channel và stub:

~~~java
@Component
final class InventoryGrpcClient implements AutoCloseable {
    private final ManagedChannel channel;
    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    InventoryGrpcClient(InventoryGrpcProperties properties) {
        this.channel = ManagedChannelBuilder
            .forTarget(properties.target())
            .useTransportSecurity()
            .build();

        this.stub = InventoryServiceGrpc.newBlockingStub(channel);
    }

    GetAvailabilityResponse getAvailability(
            String sku, int quantity, Duration timeout) {
        return stub.withDeadlineAfter(
                timeout.toMillis(), TimeUnit.MILLISECONDS)
            .getAvailability(
                GetAvailabilityRequest.newBuilder()
                    .setSku(sku)
                    .setRequestedQuantity(quantity)
                    .build());
    }

    @Override
    public void close() throws InterruptedException {
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Đây là ví dụ minh họa cấu hình TLS; trong dự án, trust material, authority và channel builder phải theo hạ tầng thực tế. Đăng ký channel/client như Spring bean có lifecycle để Spring đóng khi context shutdown. Không tạo channel trong mỗi method rồi bỏ quên transport.

Stub là object nhẹ và có thể tạo biến thể immutable với deadline, interceptor hoặc call option khác. Channel là tài nguyên kết nối cần quản lý.

## 9. Đặt deadline theo ngân sách latency

Nếu caller có ngân sách 200 ms cho một request và dành 80 ms cho các bước khác, RPC tới InventoryService không thể tùy tiện chờ vài giây. Deadline nên được chọn theo latency budget của luồng nghiệp vụ, gồm network, server processing, queueing và thời gian còn lại cho caller.

~~~java
InventoryServiceGrpc.InventoryServiceBlockingStub bounded =
    stub.withDeadlineAfter(80, TimeUnit.MILLISECONDS);

GetAvailabilityResponse response =
    bounded.getAvailability(request);
~~~

Deadline không bảo đảm server dừng ngay lập tức; service cần kiểm tra cancellation và truyền tín hiệu tới công việc nền. Nếu server tiếp tục truy vấn database sau khi caller đã timeout, tài nguyên bị tiêu tốn cho kết quả không còn được dùng.

Không đặt mọi method cùng một deadline mặc định mà không xem xét semantics. Read RPC ngắn, report dài và streaming session có ngân sách khác nhau. Deadline phải đủ chặt để bảo vệ caller nhưng đủ thực tế cho workload.

## 10. Chọn unary hay streaming

Unary thường là lựa chọn đơn giản nhất cho một request ngắn cần một response:

- Dễ retry hơn khi method có semantics an toàn và chưa commit.
- Dễ áp deadline, ghi metric theo RPC và kiểm thử.
- Phù hợp lookup, validation, command/query nhỏ.

Streaming phù hợp khi cần chuyển nhiều message trên cùng call:

- Server-streaming cho event hoặc dữ liệu được phát dần.
- Client-streaming cho upload/chunk hoặc tổng hợp input.
- Bidirectional streaming khi hai phía cần trao đổi liên tục.

Không dùng streaming chỉ để tránh thiết kế pagination hoặc để gom nhiều request không liên quan vào một call. Stream dài hạn cần flow control, cancellation, deadline/lifecycle, giới hạn buffer và chiến lược reconnect/resume.

## 11. Load balancing và service discovery

Một channel có thể đại diện một logical target thay vì một IP cố định. Resolver cung cấp địa chỉ backend; load balancer chọn subchannel cho RPC theo policy. Điều này giúp client kết nối tới nhiều instance và phục hồi khi một backend không khả dụng.

Với gRPC, cần chọn chiến lược cân bằng phù hợp. pick_first thường dùng một backend đang sẵn sàng; round_robin phân phối call qua các backend đã resolve khi resolver và service config hỗ trợ. Tên policy và khả năng phụ thuộc phiên bản/runtime.

Không hard-code một pod IP hoặc port tạm thời trong client production. Dùng DNS, service mesh, resolver hoặc cơ chế discovery được nền tảng hỗ trợ. Kiểm tra HTTP/2 pass-through, idle timeout, connection draining và keepalive trên proxy/load balancer.

## 12. Bảo mật giao tiếp nội bộ

Giao tiếp nội bộ vẫn cần xác thực và bảo vệ dữ liệu. TLS mã hóa transport và xác thực server; mutual TLS có thể xác thực cả client và server bằng certificate. Metadata thường mang bearer token, trace ID hoặc tenant context.

Các nguyên tắc:

- Không gửi credential trên plaintext network không tin cậy.
- Xác minh certificate chain và hostname/authority.
- Chỉ đưa metadata cần thiết vào call; không log token.
- Dùng interceptor hoặc CallCredentials cho authentication phù hợp.
- Kiểm tra authorization ở server; không tin tenant/role chỉ do client tự khai.
- Xoay certificate/credential mà không làm gián đoạn mọi channel cùng lúc.

TLS có chi phí handshake và mã hóa, nhưng channel reuse giảm số lần handshake. Đừng tắt TLS chỉ để cải thiện benchmark; hãy đo với cấu hình bảo mật tương đương production.

## 13. Observability cho RPC nội bộ

Độ trễ thấp cần được đo ở từng hop và toàn request. Tối thiểu nên thu thập:

- RPC count và throughput theo service/method.
- Latency histogram p50, p95, p99; không chỉ trung bình.
- Status code và tỷ lệ lỗi theo method.
- Deadline exceeded, cancellation và retry attempts.
- Kích thước request/response và streaming duration.
- Connection/channel state, backend distribution và queue depth.
- Trace context xuyên qua metadata/interceptor.

Không gắn user ID, request ID hoặc giá trị có cardinality cao làm metric label. Dùng trace/log cho định danh chi tiết và metric label có tập giá trị giới hạn.

Một service có p50 tốt nhưng p99 xấu có thể làm request chain chậm đáng kể. Tail latency thường bị ảnh hưởng bởi GC, lock contention, pool saturation, cold connection, retry storm hoặc một backend chậm.

## 14. Đo hiệu năng trước khi quyết định

So sánh gRPC và REST bằng workload tương đương:

1. Cùng business operation và cùng dữ liệu.
2. Cùng TLS/security assumptions và network path.
3. Cùng concurrency, connection reuse và timeout policy.
4. Warm-up JVM và connection trước khi đo steady state.
5. Đo p50/p95/p99, throughput, CPU, heap/allocations và network bytes.
6. Thử payload nhỏ, trung bình và lớn; cả traffic bình thường lẫn burst.
7. Thử lỗi backend, retry, connection draining và cold start.

Không kết luận chỉ từ microbenchmark serialization. End-to-end latency còn gồm network, queueing, business logic, proxy và dependency. Nếu gRPC giảm byte nhưng service xử lý database chậm, latency tổng có thể gần như không đổi.

## 15. Những chi phí và giới hạn cần tính

gRPC mang theo chi phí vận hành và phát triển:

- Phải quản lý Protobuf schema, generated code và compatibility.
- Cần tooling/debugging hỗ trợ gRPC/HTTP2.
- Browser và một số hệ thống tích hợp cần gRPC-Web, gateway hoặc adapter.
- Proxy/load balancer phải hỗ trợ đúng HTTP/2 mode; cấu hình sai có thể làm stream bị reset hoặc timeout.
- Channel, executor và streaming call cần lifecycle rõ.
- Payload nhị phân khó quan sát trực tiếp hơn JSON; cần tracing/log có chọn lọc.
- Một channel HTTP/2 dùng chung có thể chịu ảnh hưởng khi TCP connection bị mất packet hoặc quá tải.

Những chi phí này hợp lý khi lợi ích về contract, latency, throughput và streaming đáng kể. Nếu hệ thống ít call, payload nhỏ và latency không phải nút thắt, REST có thể đơn giản hơn.

## 16. Ma trận quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
| --- | --- | --- |
| Service-to-service RPC thường xuyên và cần latency/throughput cao? | Có | gRPC là ứng viên mạnh. |
| Hai đầu có thể chia sẻ và version Protobuf contract? | Có | Code generation và typed stub có giá trị. |
| Cần server/client/bidirectional streaming? | Có | gRPC có semantics trực tiếp. |
| Client chủ yếu là browser hoặc đối tác HTTP phổ thông? | Có | REST hoặc gRPC-Web/gateway. |
| Cần durable queue, replay và consumer độc lập? | Có | Message broker phù hợp hơn. |
| Hạ tầng proxy chưa hỗ trợ HTTP/2 end-to-end? | Có | Giải quyết hạ tầng trước hoặc chọn giao thức khác. |
| Chưa có khả năng quan sát, quản lý TLS và deadline? | Có | Bổ sung vận hành trước khi mở rộng gRPC. |

Quyết định cuối cùng nên dựa trên workload và số liệu đo, không chỉ dựa vào danh tiếng “gRPC nhanh”.

## 17. Lỗi thường gặp khi chọn gRPC

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng gRPC luôn nhanh hơn REST | Chọn sai khi bottleneck nằm ở database hoặc business logic | Benchmark end-to-end với workload tương đương. |
| Tạo channel cho từng RPC | Tăng handshake, socket và thread churn | Reuse ManagedChannel theo target/lifecycle. |
| Không đặt deadline | Call treo và chiếm tài nguyên | Chọn deadline theo latency budget. |
| Retry mọi status | Tăng tải và lặp side effect | Chọn retryable status và thiết kế idempotency. |
| Dùng streaming cho mọi method | Tăng độ phức tạp lifecycle/flow control | Ưu tiên unary nếu một request/response đủ dùng. |
| Dùng gRPC trực tiếp cho browser không có adapter | Client không gọi được protocol như mong đợi | Dùng gRPC-Web hoặc gateway/REST edge. |
| Hard-code backend IP | Client không theo kịp scale/restart | Dùng resolver/service discovery. |
| Bỏ TLS để benchmark | Kết quả không đại diện production và giảm bảo mật | Benchmark với TLS tương đương production. |
| Chỉ đo latency trung bình | Bỏ sót tail latency | Đo histogram p50/p95/p99 và error rate. |
| Không quản lý schema compatibility | Deploy lệch phiên bản gây lỗi RPC | Version contract và kiểm tra tương thích. |

## 18. Bài tập thực hành

Đánh giá lựa chọn giao tiếp cho ba luồng:

1. OrderService gọi InventoryService đồng bộ để xác nhận tồn kho.
2. Browser gọi API để xem lịch sử đơn hàng.
3. OrderService phát sự kiện OrderCreated cho nhiều consumer xử lý nền.

Với mỗi luồng:

- Xác định latency requirement, delivery semantics, client type và coupling.
- Chọn gRPC, REST hoặc message broker và giải thích trade-off.
- Với luồng gRPC, định nghĩa Protobuf contract, chọn unary/streaming và deadline.
- Thiết kế channel reuse, TLS, service discovery và status handling.
- Đo p50/p95/p99, throughput, CPU, memory và bytes trên mạng so với phương án thay thế.

**Tiêu chí hoàn thành:** lựa chọn giao thức khớp mô hình tương tác, có lý do định lượng, xác định rõ giới hạn vận hành và không giả định gRPC tự động bảo đảm latency thấp.

## 19. Ghi nhớ

- gRPC phù hợp với RPC nội bộ có contract rõ, tần suất cao, latency/throughput quan trọng và client/server kiểm soát được.
- Protobuf giảm chi phí biểu diễn/parse trong nhiều workload; HTTP/2 multiplex nhiều RPC trên channel.
- Tái sử dụng ManagedChannel, đặt deadline và quản lý cancellation là các yếu tố quan trọng để giữ latency ổn định.
- Unary phù hợp request/response ngắn; streaming dùng khi cần trao đổi nhiều message và phải quản lý flow control/lifecycle.
- REST phù hợp API công khai/browser và tích hợp rộng; broker phù hợp event, buffering và consumer bất đồng bộ.
- TLS, service discovery, proxy HTTP/2 và observability là điều kiện vận hành, không phải phần tùy chọn sau cùng.
- Đo p50/p95/p99, throughput, CPU, memory và network bytes bằng workload tương đương trước khi quyết định.
- gRPC không tự động nhanh hơn nếu bottleneck nằm ở business logic, database, queue hoặc network.

Chọn gRPC cho RPC nội bộ độ trễ thấp khi lợi ích của Protobuf, HTTP/2, typed contract và deadline phù hợp với workload, đồng thời đội ngũ có thể vận hành an toàn và đo được hiệu năng end-to-end.
