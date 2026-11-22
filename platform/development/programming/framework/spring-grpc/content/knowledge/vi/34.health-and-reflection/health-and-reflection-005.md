# Health check qua load balancer

Health check giúp load balancer chọn những instance có thể phục vụ RPC tại thời điểm hiện tại. Với **Spring gRPC**, server cần công bố trạng thái health theo giao thức gRPC chuẩn; client-side load balancer, proxy hoặc hạ tầng điều phối phải được cấu hình để đọc trạng thái đó và ngừng gửi request tới backend không còn phục vụ được.

Một cổng TCP mở không có nghĩa service đã sẵn sàng. Process có thể đang chạy nhưng database chưa kết nối, service đang khởi động, hoặc một nhóm RPC đã bị vô hiệu hóa do dependency lỗi. Vì vậy cần phân biệt TCP probe, gRPC Health Checking Protocol và readiness probe của nền tảng triển khai.

## 1. Ba loại health check thường gặp

| Cơ chế | Điều được kiểm tra | Giới hạn |
| --- | --- | --- |
| TCP connect probe | Có thể mở kết nối tới port hay không | Không xác minh HTTP/2, gRPC service hoặc dependency |
| gRPC Health Check | Trạng thái SERVING/NOT_SERVING của một service | Cần server triển khai health protocol và LB hỗ trợ gRPC health |
| Platform readiness probe | Instance có nên nhận traffic mới hay không | Thường là quyết định ở cấp pod/instance, có thể không phân biệt từng gRPC service |

TCP probe hữu ích để phát hiện process không lắng nghe port, nhưng có thể đánh dấu một server là healthy ngay cả khi service chưa sẵn sàng. Ngược lại, một server có nhiều service độc lập có thể chỉ cần loại một service khỏi pool; gRPC health cho phép công bố trạng thái theo tên service.

Liveness trả lời process có cần được restart hay không. Readiness trả lời instance có nên nhận traffic hay không. Load balancer health check thường phục vụ mục đích readiness; không dùng lỗi dependency bên ngoài làm liveness thất bại nếu restart process không thể khôi phục dependency.

## 2. Giao thức gRPC Health Checking

gRPC định nghĩa service chuẩn có tên đầy đủ là grpc.health.v1.Health, với hai RPC:

- **Check**: client gửi tên service và nhận trạng thái hiện tại.
- **Watch**: client mở server-streaming RPC để nhận trạng thái ban đầu và các thay đổi tiếp theo.

Các trạng thái phục vụ chính:

| Trạng thái | Ý nghĩa với load balancer |
| --- | --- |
| SERVING | Backend có thể nhận RPC cho service được hỏi |
| NOT_SERVING | Backend không nên nhận RPC mới cho service đó |
| UNKNOWN | Chưa xác định được khả năng phục vụ |

Client-side gRPC load balancer thường dùng Watch để theo dõi từng backend lâu dài. Khi một backend chuyển NOT_SERVING, LB có thể ngừng chọn backend đó cho service tương ứng. Khi trạng thái trở lại SERVING, backend có thể được đưa lại vào pool theo chính sách của LB.

Tên service phải khớp chính xác tên đầy đủ trong Protobuf service, ví dụ acme.orders.v1.OrderService. Chuỗi rỗng đại diện health tổng thể của server. Nếu chỉ OrderService bị ảnh hưởng, hãy cập nhật trạng thái service đó thay vì đánh dấu mọi service NOT_SERVING.

## 3. Đăng ký HealthStatusManager trên Spring gRPC server

gRPC Java cung cấp HealthStatusManager trong artifact grpc-services. Nó triển khai health service chuẩn và quản lý trạng thái cho từng service:

~~~java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

HealthStatusManager healthManager = new HealthStatusManager();
String orderServiceName = "acme.orders.v1.OrderService";

healthManager.setStatus(
    orderServiceName,
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(orderService)
    .addService(healthManager.getHealthService())
    .build()
    .start();

// Sau khi dependency critical và application initialization sẵn sàng:
healthManager.setStatus(
    orderServiceName,
    ServingStatus.SERVING);
~~~

Ví dụ minh họa gRPC Java server. Trong ứng dụng Spring, quản lý HealthStatusManager thành bean và đăng ký health service qua cơ chế service registration hoặc ServerBuilder customizer của starter đang dùng. Không tạo server thứ hai nếu starter đã sở hữu server lifecycle.

Khởi tạo ở NOT_SERVING giúp tránh cửa sổ server đã mở port nhưng dependency critical chưa sẵn sàng. Chỉ chuyển SERVING sau khi startup hoàn tất. Nếu có nhiều service, đặt trạng thái riêng cho từng service và cập nhật trạng thái tổng thể chỉ khi toàn bộ server thực sự không thể nhận traffic.

## 4. Client-side load balancing với healthCheckConfig

Trong client-side load balancing, ứng dụng gRPC kết nối tới resolver trả về danh sách backend. Load balancing policy chọn subchannel để gửi RPC. Có thể cấu hình service config với healthCheckConfig để client thực hiện health checking trên các backend:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "acme.orders.v1.OrderService"
  },
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

healthCheckConfig chỉ rõ service name mà client cần theo dõi qua gRPC Health Watch. Khi backend báo NOT_SERVING, client-side LB có thể loại subchannel đó khỏi tập endpoint đủ điều kiện cho RPC tương ứng. round_robin là ví dụ policy phân phối request giữa các backend đủ điều kiện.

Service config phải được cung cấp cho channel qua name resolver hoặc cấu hình mặc định mà gRPC Java hỗ trợ. Ví dụ cấu hình channel trực tiếp:

~~~java
Map<String, ?> serviceConfig = Map.of(
    "healthCheckConfig",
    Map.of("serviceName", "acme.orders.v1.OrderService"),
    "loadBalancingConfig",
    List.of(Map.of("round_robin", Map.of())));

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.internal:9090")
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

Đây là ví dụ cho gRPC Java client có resolver và LB policy tương ứng. Cần xác minh policy được hỗ trợ trong phiên bản runtime và cấu hình resolver thực tế. Nếu resolver trả service config riêng, cần thống nhất nguồn cấu hình; không giả định defaultServiceConfig luôn ghi đè service config từ resolver.

Health checking phải được hỗ trợ bởi load balancing policy/client runtime. Chỉ khai báo service name trong file YAML của Spring không tự làm mọi channel hoặc mọi proxy thực hiện health check.

## 5. Proxy và load balancer phía hạ tầng

Không phải mọi load balancer đều dùng cùng cơ chế:

- **TCP/L4 load balancer** thường chỉ kiểm tra kết nối port hoặc health probe ở tầng transport. Nó không tự hiểu trạng thái từng gRPC service.
- **gRPC-aware L7 proxy/service mesh** có thể gọi gRPC Health Check hoặc Watch để quyết định backend nào đủ điều kiện.
- **Kubernetes readiness** quyết định pod có nằm trong EndpointSlice/Service endpoint hay không; probe có thể dùng HTTP, TCP hoặc gRPC tùy cấu hình và phiên bản.
- **Client-side gRPC LB** dùng resolver và policy trong client process để theo dõi từng backend, thường qua Health Watch khi service config bật health checking.

Với proxy L7, cấu hình active health check cần chỉ rõ protocol gRPC và đúng service name. Nếu proxy chỉ dùng HTTP path hoặc TCP connect, nó có thể kiểm tra được process nhưng không kiểm tra được trạng thái gRPC service. Hãy kiểm tra tài liệu sản phẩm về hỗ trợ HTTP/2, gRPC Check/Watch, TLS và cách diễn giải status.

Một deployment có thể có nhiều tầng health check: Kubernetes readiness loại pod khỏi Service endpoint; Envoy kiểm tra endpoint trong cluster; client-side LB tiếp tục theo dõi backend. Các tầng phải dùng cùng tiêu chí readiness hoặc có lý do rõ ràng khi khác nhau, nếu không backend có thể bị tầng này coi là healthy nhưng tầng khác loại bỏ.

## 6. Health theo service và routing

Giả sử server cung cấp OrderService và CatalogService. Database đơn hàng có thể lỗi trong khi catalog vẫn phục vụ từ cache:

~~~java
healthManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

healthManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);
~~~

Client cấu hình health check cho OrderService sẽ không chọn backend đang NOT_SERVING cho service đó. Một client khác theo dõi CatalogService vẫn có thể dùng cùng backend. Cách này chỉ có hiệu lực nếu LB hỗ trợ health theo service và routing phù hợp; một HTTP load balancer chỉ có readiness cấp pod có thể loại cả pod.

Nếu dependency dùng chung ảnh hưởng mọi RPC, cập nhật trạng thái service liên quan hoặc trạng thái tổng thể theo chính sách. Không báo SERVING cho một service mà request của nó chắc chắn thất bại chỉ để giữ số backend trong pool.

## 7. Trạng thái khi startup, dependency lỗi và shutdown

Một vòng đời health hợp lý:

1. **Starting**: khởi tạo health manager với NOT_SERVING.
2. **Dependency validation**: kiểm tra database, credential provider và dependency critical với timeout ngắn.
3. **Ready**: chuyển service liên quan sang SERVING.
4. **Degraded**: khi circuit breaker/monitor xác nhận dependency không sẵn sàng qua ngưỡng, chuyển service bị ảnh hưởng sang NOT_SERVING.
5. **Recovery**: chỉ chuyển lại SERVING sau probe thành công ổn định hoặc circuit breaker đóng.
6. **Draining**: trước graceful shutdown, chuyển NOT_SERVING để LB ngừng chọn backend mới; sau đó chờ request đang chạy hoàn tất trong grace period.

Không cập nhật health theo một exception đơn lẻ. Phân biệt lỗi caller như INVALID_ARGUMENT/CANCELLED với lỗi availability của dependency như UNAVAILABLE lặp lại. Dùng cooldown, cửa sổ thống kê và probe giới hạn để tránh health flapping.

Khi chuyển NOT_SERVING, các client Watch cần thời gian nhận update và LB cần thời gian áp dụng. Vì vậy, graceful shutdown vẫn cần grace period; không đóng socket ngay lập tức sau khi đổi trạng thái.

## 8. Timeout, bảo mật và tải của health check

Health check cũng là traffic và có thể gây tải nếu tần suất quá cao. Nên:

- Dùng Watch cho client-side LB khi được hỗ trợ, thay vì liên tục polling Check từ mọi client.
- Nếu dùng active Check, đặt interval, timeout và ngưỡng failure hợp lý.
- Không để health handler thực hiện truy vấn blocking dài cho mỗi lần kiểm tra.
- Dùng trạng thái đã được monitor/circuit breaker cập nhật, hoặc probe nhẹ có giới hạn.
- Bảo vệ health endpoint theo trust boundary; không để endpoint chi tiết tiết lộ topology hoặc thông tin nhạy cảm.
- Nếu gRPC server dùng TLS/mTLS, cấu hình probe/client tương thích với certificate, hostname và credential.

Health check không thay thế deadline của RPC nghiệp vụ. Một endpoint báo SERVING chỉ cho biết service được xem là có thể nhận request; từng RPC vẫn cần deadline, retry và xử lý lỗi riêng.

## 9. Kiểm thử load balancer loại backend lỗi

Kiểm thử cần có ít nhất hai backend để xác minh LB thực sự fail over:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Cả hai backend SERVING | Request được phân phối theo policy |
| Backend A chuyển NOT_SERVING | Client/proxy ngừng gửi RPC mới tới A sau khi nhận health update |
| Backend B vẫn SERVING | Request tiếp tục thành công qua B |
| A phục hồi SERVING | A được đưa lại vào pool theo policy |
| Service A lỗi nhưng service B còn tốt | Health theo service không loại nhầm service độc lập |
| Backend không triển khai Health Watch | LB xử lý theo policy cấu hình, không giả định backend healthy |
| Health endpoint timeout hoặc TLS lỗi | Backend bị xem là unhealthy theo failure threshold |
| Graceful shutdown | Backend được drain trước khi server đóng kết nối |

Dùng gRPC health client gọi Check và Watch để xác minh server status. Sau đó chạy integration test qua đúng resolver, LB policy hoặc proxy như production; test gọi trực tiếp một server không chứng minh được hành vi phân phối traffic.

## 10. Quan sát hoạt động của health-aware load balancing

Theo dõi theo service name và backend identity:

- Số backend SERVING, NOT_SERVING và UNKNOWN.
- Thời gian từ lúc server đổi status tới lúc LB loại hoặc thêm backend.
- Health Watch disconnect/reconnect và Check failure.
- Số RPC được gửi tới từng backend và tỷ lệ lỗi sau failover.
- Thời gian backend ở trạng thái draining.
- Số lần health flapping và nguyên nhân chuyển trạng thái.
- Probe latency, timeout và tải do health check tạo ra.

Khi request vẫn đi tới backend NOT_SERVING, kiểm tra service name có khớp không, LB có hỗ trợ gRPC health không, service config có được áp dụng không và health update đã tới subchannel chưa. Nếu tất cả backend bị loại, kiểm tra readiness threshold và khả năng phục hồi; tránh để LB tiếp tục retry dồn dập vào endpoint không phục vụ được.

## 11. Ghi nhớ và tự kiểm tra

**Health check qua load balancer** cần một health signal mà LB hiểu và một chính sách routing dùng signal đó. TCP probe chỉ kiểm tra port; gRPC Health Check/Watch công bố trạng thái theo service; readiness của nền tảng thường quyết định ở cấp instance. Đăng ký HealthStatusManager, khởi tạo NOT_SERVING, chuyển SERVING khi sẵn sàng, và drain bằng NOT_SERVING trước shutdown. Bật healthCheckConfig ở client-side LB hoặc cấu hình probe gRPC-aware ở proxy/hạ tầng.

Tự kiểm tra:

1. Vì sao TCP connect thành công không chứng minh gRPC service đã sẵn sàng?
2. Check và Watch khác nhau như thế nào?
3. healthCheckConfig.serviceName cần khớp với giá trị nào trong Protobuf?
4. Vì sao một backend có thể SERVING cho CatalogService nhưng NOT_SERVING cho OrderService?
5. Client-side LB, L7 proxy và Kubernetes readiness khác nhau ở phạm vi health ra sao?
6. Vì sao cần grace period sau khi chuyển backend sang NOT_SERVING?

Health-aware load balancing giúp Spring gRPC tránh gửi request mới tới backend không thể phục vụ, chuyển tải sang instance khỏe và đưa backend trở lại pool sau khi dependency phục hồi có kiểm soát.
