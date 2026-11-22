# Deadline qua proxy và load balancer

Trong hệ thống Spring gRPC, RPC có thể đi qua gateway, reverse proxy, service mesh hoặc load balancer trước khi tới server. Mỗi tầng có thể có timeout riêng. Nếu proxy đặt lại thời gian chờ mới thay vì giữ ngân sách còn lại của caller, tổng thời gian xử lý có thể vượt deadline ban đầu. Nếu proxy dùng timeout quá ngắn hoặc không hiểu streaming, nó có thể ngắt một RPC hợp lệ.

**Deadline end-to-end** là giới hạn thời gian mà caller cấp cho toàn bộ RPC. Proxy và load balancer cần giữ giới hạn này xuyên suốt các hop, áp dụng timeout nội bộ phù hợp và truyền cancellation về upstream khi lời gọi kết thúc. Trong gRPC, deadline được biểu diễn trên wire bằng header giao thức **grpc-timeout**; proxy L7 hiểu gRPC cần bảo toàn hoặc cập nhật thời lượng còn lại đúng cách.

## 1. RPC đi qua proxy và load balancer như thế nào?

Một request có thể đi theo tuyến:

~~~mermaid
flowchart LR
    C["gRPC client"] --> P["Gateway / L7 proxy"]
    P --> L["Load balancer"]
    L --> S["Spring gRPC server"]
    S --> D["Database / downstream"]
~~~

Client có thể cấp 1.200 ms cho toàn bộ RPC. Thời gian chờ ở gateway, cân bằng tải, network, hàng đợi và xử lý server đều tiêu thụ ngân sách đó. Khi request tới Spring gRPC server, server phải nhận được **thời gian còn lại**, không phải một deadline mới đầy đủ 1.200 ms.

Ví dụ minh họa:

| Chặng | Thời gian đã dùng | Ngân sách còn lại xấp xỉ |
| --- | ---: | ---: |
| Client bắt đầu | 0 ms | 1.200 ms |
| Gateway nhận và định tuyến | 100 ms | 1.100 ms |
| Load balancer chọn upstream, truyền request | 50 ms | 1.050 ms |
| Spring gRPC xử lý và gọi downstream | 700 ms | 350 ms |
| Trả response qua các hop | 150 ms | 200 ms dự phòng |

Các con số chỉ minh họa. Điều quan trọng là **mọi tầng cùng dùng một ngân sách tổng**, và mỗi tầng chỉ tiêu thụ phần thời gian được cấp.

## 2. Proxy L4 và proxy L7 ảnh hưởng deadline khác nhau

### L4: TCP passthrough

Load balancer L4 thường chuyển tiếp kết nối TCP mà không phân tích HTTP/2 hoặc gRPC metadata. Nếu nó hoạt động như passthrough, header grpc-timeout đi trong luồng HTTP/2 end-to-end tới gRPC server. L4 vẫn có thể áp dụng TCP connection timeout, idle connection timeout hoặc giới hạn kết nối riêng.

Timeout của kết nối TCP không thay thế deadline của từng RPC. Một kết nối HTTP/2 có thể mang nhiều RPC đồng thời; đóng connection có thể ảnh hưởng tất cả stream đang chạy trên connection đó.

### L7: gRPC-aware proxy

Proxy L7 kết thúc HTTP/2 phía client và tạo upstream request mới tới server. Nó có thể đọc route, method, metadata và áp dụng timeout/retry policy. Khi làm vậy, proxy cần:

- Bảo toàn deadline caller hoặc chuyển nó thành timeout upstream tương đương.
- Tính **thời gian còn lại** khi request đi qua proxy.
- Không ghi đè deadline ngắn hơn mà caller đã đặt.
- Giữ status gRPC và trailers phù hợp khi trả kết quả.
- Truyền cancellation/reset tới upstream khi downstream client hủy hoặc deadline hết.

Không phải proxy nào cũng xử lý gRPC giống nhau. Với proxy chỉ hiểu HTTP chung, cần xác minh cách nó xử lý header grpc-timeout, HTTP/2 stream và gRPC trailers. Không giả định rằng một HTTP route timeout tự động tương đương deadline gRPC end-to-end.

## 3. grpc-timeout là header giao thức, không phải metadata tùy chỉnh

Khi client gRPC đặt deadline, gRPC transport mã hóa thời lượng còn lại vào header **grpc-timeout**. Giá trị này có thể dùng đơn vị thời gian khác nhau theo quy tắc giao thức; ứng dụng không nên tự parse hoặc copy chuỗi header này trong code nghiệp vụ.

~~~java
GetOrderResponse response = orderStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

Nếu proxy L7 kết thúc kết nối HTTP/2 và tạo request upstream mới, proxy cần chuyển tiếp hoặc tính lại timeout theo ngân sách còn lại. Không nên gửi lại nguyên giá trị ban đầu sau khi đã tiêu tốn thời gian ở gateway. Nếu caller còn 800 ms khi tới proxy, upstream không thể được cấp lại 1.200 ms.

Metadata như authorization, tenant ID, request ID và trace context là các thông tin riêng. Interceptor có thể quản lý chúng, nhưng không dùng custom metadata để thay thế deadline gRPC.

## 4. Phân biệt các timeout trên proxy và load balancer

Một proxy thường có nhiều timeout khác nhau. Tên gọi cụ thể phụ thuộc sản phẩm, nhưng ý nghĩa thường gồm:

| Timeout | Phạm vi | Vai trò |
| --- | --- | --- |
| **Connect timeout** | Thiết lập kết nối upstream | Giới hạn thời gian mở kết nối tới backend |
| **Route/request timeout** | Một request hoặc logical upstream operation | Giới hạn tổng thời gian proxy chờ kết quả |
| **Per-try timeout** | Một lần thử upstream | Giới hạn thời gian của từng attempt khi proxy retry |
| **Stream idle timeout** | Một HTTP/2/gRPC stream | Đóng stream không có hoạt động trong thời gian quy định |
| **Maximum stream duration** | Tổng tuổi thọ stream | Giới hạn phiên streaming dài hạn |
| **TCP idle timeout** | Kết nối transport | Thu hồi connection không hoạt động |

Các timeout này không thể thay thế lẫn nhau. Ví dụ, connect timeout 200 ms chỉ giới hạn mở kết nối; nó không giới hạn thời gian server xử lý RPC. Stream idle timeout 60 giây cũng không có nghĩa một RPC unary được phép chạy 60 giây.

Tên và cách tính route timeout/per-try timeout khác nhau giữa Envoy, ingress controller, service mesh và cloud load balancer. Cần đọc đúng tài liệu của sản phẩm và kiểm tra bằng integration test; không sao chép một cấu hình timeout giữa các proxy khác nhau mà không xác minh ngữ nghĩa.

## 5. Phân bổ ngân sách giữa caller, proxy và backend

Một chính sách thực tế có thể bắt đầu bằng:

| Tầng | Giới hạn ví dụ | Mục đích |
| --- | ---: | --- |
| Client logical RPC | 1.200 ms | Ngân sách end-to-end của caller |
| Gateway route | tối đa 1.100 ms | Chừa thời gian cho client nhận response |
| Upstream per try | tối đa 400 ms | Giới hạn mỗi attempt backend |
| Spring gRPC method | theo deadline còn lại, tối đa 350 ms cho bước nghiệp vụ chính | Không vượt ngân sách upstream |
| Database query | tối đa 250 ms | Ngăn query giữ connection lâu |

Đây chỉ là ví dụ phân bổ, không phải cấu hình chuẩn. Các giới hạn phải được chọn theo latency p95/p99, SLA, thời gian queue và chi phí xử lý ở từng tầng.

Nguyên tắc:

1. Timeout route của proxy không nên vượt ngân sách caller còn lại.
2. Per-try timeout phải nhỏ hơn hoặc bằng route timeout và deadline còn lại.
3. Backend/downstream timeout phải nằm trong ngân sách mà proxy và caller còn cấp.
4. Dành phần dự phòng cho serialize, network response và xử lý ở caller.
5. Khi không còn đủ thời gian cho một attempt hợp lý, không bắt đầu attempt mới.

Không đặt timeout của mọi tầng bằng cùng một con số. Nếu mỗi tầng cấp lại đầy đủ 1.200 ms, tổng thời gian thực tế có thể dài hơn nhiều so với SLA.

## 6. Retry ở client và proxy có thể nhân số attempt

gRPC client có thể retry theo service config; proxy L7 cũng có thể retry upstream. Nếu cả hai cùng retry, số request tới backend có thể tăng theo tích số attempt của từng tầng.

Ví dụ client tối đa 3 attempts và proxy tối đa 2 attempts cho mỗi request nhận được có thể tạo tới 6 upstream attempts trong trường hợp xấu. Khi nhiều client cùng gặp lỗi, retry amplification có thể làm backend quá tải hơn.

Nên:

- Chọn một tầng chịu trách nhiệm retry chính cho từng loại lỗi.
- Giới hạn tổng attempts và thời gian retry trong deadline logical RPC.
- Dùng exponential backoff và jitter.
- Chỉ retry status thực sự có thể phục hồi.
- Tránh retry command có side effect nếu chưa có idempotency.
- Theo dõi số logical RPC so với số upstream attempts.

DEADLINE_EXCEEDED không chứng minh backend chưa thực hiện thao tác. Proxy có thể timeout khi backend đã commit nhưng response chưa quay về. Với command như tạo đơn hoặc thanh toán, dùng idempotency key ổn định xuyên suốt client, proxy và backend; không tạo key mới cho mỗi attempt.

## 7. Cancellation phải đi ngược từ proxy về backend

Khi client hủy RPC hoặc deadline hết, proxy L7 cần kết thúc downstream stream và yêu cầu hủy upstream call. Ở Spring gRPC server, gRPC Java thường thể hiện việc này qua context cancellation:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    stopProducer();
    releaseTemporaryResources();
}, cleanupExecutor);
~~~

Tên future, producer và hàm cleanup là thành phần giả định của ứng dụng. Server cần truyền context/cancellation tới các lời gọi downstream và kết nối tín hiệu với database, HTTP client hoặc tác vụ nền có thể hủy.

Cancellation không tự rollback transaction đã commit. Nếu backend hoàn tất side effect trước khi proxy hủy call, client có thể nhận timeout dù thao tác đã xảy ra. Idempotency và operation status vẫn cần thiết.

Proxy cũng có thể có hành vi khác nhau khi client disconnect: một số cấu hình hủy upstream ngay, số khác có thể để request tiếp tục theo policy. Cần kiểm tra và cấu hình rõ hành vi này, nhất là với RPC tốn tài nguyên.

## 8. Streaming cần timeout riêng

Với server streaming hoặc bidirectional streaming, proxy có thể áp route timeout ngắn vốn phù hợp với unary. Điều đó khiến stream hợp lệ bị ngắt giữa chừng. Ngược lại, bỏ tất cả timeout có thể giữ connection, subscription và buffer vô hạn.

Phân biệt:

- **RPC deadline:** tổng thời gian sống của một RPC.
- **Stream idle timeout:** khoảng thời gian stream không có hoạt động theo định nghĩa của proxy.
- **Maximum stream duration:** tuổi thọ tối đa của một stream.
- **HTTP/2 keepalive:** kiểm tra tính sống của transport connection.

Một subscription dài hạn có thể dùng session lifetime hữu hạn, idle timeout, heartbeat có giới hạn, cursor/sequence và reconnect. Nếu proxy cho phép ngoại lệ route timeout cho stream, cần bù bằng giới hạn stream đồng thời, backpressure, cancellation cleanup và thời gian sống phiên rõ ràng.

Đừng xem heartbeat là bằng chứng nghiệp vụ đang tiến triển. Heartbeat có thể giữ stream hoạt động ở tầng transport nhưng không thay thế giới hạn phiên hoặc deadline của thao tác.

## 9. TLS termination và gRPC metadata

Proxy có thể kết thúc TLS ở biên rồi tạo kết nối TLS/mTLS mới tới backend. Việc kết thúc TLS không tự loại bỏ deadline: proxy L7 vẫn có thể đọc grpc-timeout trong HTTP/2 headers và chuyển ngân sách phù hợp tới upstream.

Khi triển khai, xác minh:

- Downstream và upstream đều dùng HTTP/2 phù hợp với gRPC.
- Proxy giữ nguyên gRPC method path, metadata cần thiết và trailers.
- Header grpc-timeout được bảo toàn hoặc chuyển đổi đúng ngữ nghĩa.
- TLS/mTLS được cấu hình riêng cho từng chặng theo trust boundary.
- Không ghi log credential hoặc metadata nhạy cảm khi debug timeout.

Với L4 passthrough, proxy không giải mã TLS và thường không thể áp policy theo từng gRPC method. Nó chỉ có thể quản lý connection-level timeout/health và chuyển tiếp byte stream.

## 10. Kiểm thử deadline qua proxy và load balancer

Kiểm thử trực tiếp client-server chưa đủ để xác minh hành vi khi có proxy. Cần dựng topology gần production và kiểm tra:

1. Client đặt deadline ngắn; proxy chuyển đúng ngân sách còn lại tới backend.
2. Proxy route timeout ngắn hơn client deadline; client nhận status phù hợp và không chờ quá SLA.
3. Backend xử lý lâu; proxy timeout và cancellation có truyền tới server không.
4. Client chủ động cancel; proxy có hủy upstream call và server có dừng tác vụ không.
5. Proxy retry và client retry cùng bật; đo số upstream attempts thực tế.
6. Streaming vượt route timeout unary; xác minh policy stream riêng, idle timeout và reconnect.
7. TLS termination vẫn giữ method path, gRPC status, trailers và timeout semantics.

Dùng backend giả lập có độ trễ điều khiển được, ghi timestamp ở client/proxy/server và trace ID xuyên suốt. Kiểm tra cả status cuối lẫn số lần backend thực thi; một test chỉ xác nhận client nhận DEADLINE_EXCEEDED chưa chứng minh backend đã dừng.

## 11. Quan sát deadline theo từng hop

Theo dõi theo trace ID, full method name và upstream cluster:

- Deadline/thời gian còn lại khi request vào và rời proxy.
- Route timeout, per-try timeout và số attempts của proxy.
- Latency và gRPC status tại client, proxy và backend.
- Thời gian queue, connect, xử lý server và downstream.
- Số upstream call còn chạy sau client cancellation.
- Stream duration, idle close, reconnect và buffer/backpressure.
- Tỷ lệ retry amplification và idempotency hit.

Nếu client timeout nhưng backend vẫn chạy, điều tra cancellation propagation. Nếu proxy timeout trước client, kiểm tra route timeout và phần dự phòng. Nếu backend nhận request với ngân sách rất thấp, độ trễ có thể nằm ở gateway, load balancer hoặc queue trước đó.

Không chỉ tăng timeout khi thấy nhiều lỗi. Trước hết xác định hop tiêu thụ ngân sách, rồi điều chỉnh timeout, capacity hoặc retry policy ở đúng tầng.

## 12. Ghi nhớ và tự kiểm tra

**Deadline qua proxy và load balancer phải giữ nguyên ngân sách end-to-end của caller.** L4 passthrough thường chuyển tiếp HTTP/2 stream; L7 gRPC-aware proxy phải bảo toàn hoặc tính lại grpc-timeout, áp route/per-try timeout không vượt ngân sách còn lại và truyền cancellation về backend. Retry ở client và proxy cần phối hợp để tránh khuếch đại tải; streaming cần policy riêng về idle và session lifetime.

Tự kiểm tra:

1. Proxy L4 khác proxy L7 ở khả năng hiểu grpc-timeout như thế nào?
2. Vì sao proxy không được cấp lại toàn bộ timeout ban đầu khi tạo upstream request?
3. Route timeout và per-try timeout khác nhau ở điểm nào?
4. Vì sao bật retry đồng thời ở client và proxy có thể làm backend nhận nhiều attempts hơn dự kiến?
5. Khi proxy hủy upstream call, Spring gRPC server cần làm gì để dừng công việc và bảo vệ side effect?

Quản lý deadline xuyên proxy và load balancer giúp Spring gRPC giữ đúng giới hạn thời gian caller yêu cầu, giảm request bị treo và duy trì hành vi nhất quán khi định tuyến, retry hoặc streaming qua nhiều tầng hạ tầng.
