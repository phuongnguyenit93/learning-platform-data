# Health-aware load balancing

## 1. Chỉ chọn backend thực sự sẵn sàng phục vụ

Trong **SPRING_GRPC**, một service gRPC có thể chạy trên nhiều instance và client dùng `ManagedChannel`, name resolver cùng load balancing policy để chọn backend cho mỗi RPC mới. Tuy nhiên, một địa chỉ có thể kết nối được chưa chắc ứng dụng phía sau đang khỏe. **Health-aware load balancing** bổ sung tín hiệu sức khỏe ứng dụng vào quyết định chọn backend, để client tránh gửi RPC mới đến instance không thể phục vụ.

Ví dụ service `orders` có ba instance:

~~~text
Resolver trả về:
  A: 10.60.0.11:9090
  B: 10.60.0.12:9090
  C: 10.60.0.13:9090

Trạng thái transport:
  A: READY
  B: READY
  C: READY

Trạng thái ứng dụng:
  A: SERVING
  B: NOT_SERVING (database chưa sẵn sàng)
  C: SERVING

Health-aware picker:
  Chọn A hoặc C cho RPC mới
  Không chọn B cho đến khi B trở lại SERVING
~~~

Nếu chỉ dựa vào trạng thái kết nối, cả A, B và C đều có thể được xem là sẵn sàng nhận RPC. Health-aware load balancing giúp phân biệt **kết nối được** với **phục vụ được**.

## 2. Connectivity READY không phải application health

gRPC channel theo dõi trạng thái kết nối của subchannel, chẳng hạn `IDLE`, `CONNECTING`, `READY` và `TRANSIENT_FAILURE`. Trạng thái `READY` cho biết transport đã thiết lập kết nối để gửi RPC; nó không chứng minh database, message broker hoặc dependency nghiệp vụ của backend đang hoạt động bình thường.

Một instance có thể:

- Mở TCP port và hoàn tất TLS handshake.
- Nhận HTTP/2 connection.
- Trả lời một RPC health hoặc business bằng lỗi vì dependency bắt buộc đang hỏng.

Do đó cần tách các tín hiệu:

| Tín hiệu | Trả lời câu hỏi | Nơi thường được dùng |
|---|---|---|
| Connectivity state | Có thể gửi RPC qua kết nối này không? | gRPC channel/subchannel |
| Liveness | Tiến trình còn sống hay cần khởi động lại? | Container orchestrator |
| Readiness | Instance có nên nhận traffic mới không? | Kubernetes/service discovery |
| gRPC application health | Service cụ thể có đang phục vụ được không? | gRPC health checking |
| Outlier/ejection signal | Backend có hành vi lỗi bất thường so với nhóm không? | Service mesh/control plane |

Liveness và readiness cũng không đồng nghĩa. Một ứng dụng có thể còn sống nhưng chưa sẵn sàng vì đang khởi tạo schema hoặc tải dữ liệu. Nếu liveness probe coi mọi lỗi dependency là lỗi tiến trình, orchestrator có thể restart liên tục trong khi chỉ cần chờ dependency phục hồi.

## 3. gRPC Health Checking Protocol

gRPC định nghĩa service chuẩn `grpc.health.v1.Health` trong package `grpc.health.v1`. Service cung cấp hai RPC chính:

- `Check`: hỏi trạng thái sức khỏe hiện tại của một service.
- `Watch`: đăng ký nhận thay đổi trạng thái theo thời gian.

Health response dùng các trạng thái như:

| Trạng thái | Ý nghĩa |
|---|---|
| `SERVING` | Service hiện có thể phục vụ |
| `NOT_SERVING` | Service hiện không nên nhận RPC mới |
| `SERVICE_UNKNOWN` | Health service không có thông tin cho service được hỏi |
| `UNKNOWN` | Trạng thái chưa xác định theo hợp đồng health |

Client-side health checking thường dùng `Watch` để theo dõi trạng thái backend, thay vì gửi một `Check` mới cho mỗi business RPC. Khi trạng thái service không còn `SERVING`, health-aware load balancer có thể ngừng chọn backend đó cho RPC mới. Hành vi cụ thể phụ thuộc gRPC runtime, load balancing policy và service config có hỗ trợ health checking.

Tên service cần được thống nhất. Với service được khai báo:

~~~proto
package orders.v1;

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}
~~~

Tên đầy đủ dùng trong health check là `orders.v1.OrdersService`, không phải tên Java class hay tên bean Spring.

## 4. Expose health service trong gRPC Java

gRPC Java cung cấp `HealthStatusManager` trong artifact `grpc-services`. Server đăng ký health service cùng business service và cập nhật trạng thái theo lifecycle:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

public final class OrdersGrpcServer {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health =
            new HealthStatusManager();

    private Server server;

    public void start(OrdersServiceImpl ordersService)
            throws java.io.IOException {
        server = NettyServerBuilder.forPort(9090)
                .addService(ordersService)
                .addService(health.getHealthService())
                .build()
                .start();

        // Chỉ chuyển sang SERVING sau khi dependency bắt buộc
        // và phần khởi tạo nghiệp vụ đã sẵn sàng.
        health.setStatus(SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }
}
~~~

Đoạn code minh họa server dùng Netty shaded transport; dự án phải có dependency `grpc-services` và các artifact gRPC cùng phiên bản. Trong Spring, có thể quản lý `HealthStatusManager` như bean và đăng ký `getHealthService()` qua cơ chế đăng ký service của starter đang dùng.

`setStatus(SERVICE, ...)` cập nhật health theo service cụ thể. Trường tên service rỗng thường được dùng cho trạng thái tổng thể của server. Nếu server cung cấp nhiều gRPC service, không nên đặt tất cả cùng `SERVING` chỉ vì tiến trình còn sống: mỗi service có thể phụ thuộc vào các thành phần khác nhau.

Không đánh dấu `SERVING` ngay khi socket mở. Hãy đợi các dependency thật sự cần cho request, migration/schema, consumer hoặc cache bắt buộc hoàn tất khởi tạo.

## 5. Cấu hình client health checking

gRPC service config có thể kết hợp load balancing policy với `healthCheckConfig`. Ví dụ:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ],
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrdersService"
  }
}
~~~

Ý nghĩa:

- `round_robin` phân phối RPC mới qua các subchannel đủ điều kiện.
- `healthCheckConfig.serviceName` chỉ định service mà client cần theo dõi qua gRPC health checking.
- Backend chỉ nên được xem là healthy cho service đó khi health signal thỏa điều kiện của client-side health checking, thường là trạng thái `SERVING`.

Service config có thể được resolver cung cấp hoặc đặt làm cấu hình mặc định của channel nếu runtime hỗ trợ. Ví dụ cấu hình mặc định trong gRPC Java:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

java.util.Map<String, Object> serviceConfig = java.util.Map.of(
        "loadBalancingConfig", java.util.List.of(
                java.util.Map.of("round_robin", java.util.Map.of())),
        "healthCheckConfig",
                java.util.Map.of("serviceName", "orders.v1.OrdersService")
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultServiceConfig(serviceConfig)
        .useTransportSecurity()
        .build();
~~~

Đây là cách biểu diễn cấu hình ở tầng gRPC Java; khả năng health checking và policy được dùng phải được xác nhận theo phiên bản gRPC Java, provider và resolver thực tế. Không phải mọi starter hoặc custom load balancer đều bật client-side health checking giống nhau. Nếu runtime không hỗ trợ, cần dùng health-aware discovery/control plane để loại endpoint không khỏe khỏi danh sách hoặc một policy có tích hợp health signal.

Đừng nhầm cấu hình client-side health checking với việc chỉ đăng ký health service ở server. Server phải expose và cập nhật trạng thái; client phải được cấu hình để theo dõi và dùng trạng thái đó trong quá trình chọn backend.

## 6. Định nghĩa health theo khả năng phục vụ nghiệp vụ

Health check có ích khi trạng thái phản ánh đúng khả năng xử lý request. Nếu `GetOrder` bắt buộc truy cập database chính, backend không nên báo `SERVING` khi database đó mất kết nối kéo dài. Nhưng nếu một dependency tùy chọn chỉ phục vụ tính năng phụ, đánh dấu toàn bộ service `NOT_SERVING` có thể loại bỏ một backend vẫn xử lý được phần lớn RPC.

Vì vậy:

1. Xác định dependency nào bắt buộc đối với từng gRPC service.
2. Định nghĩa điều kiện chuyển `SERVING`/`NOT_SERVING`.
3. Phân biệt lỗi ngắn có thể tự phục hồi với lỗi kéo dài.
4. Cập nhật health từ tín hiệu đã có (connection state, circuit breaker, dependency monitor) thay vì chạy truy vấn nặng cho mỗi lần health check.
5. Nếu các method có yêu cầu khác nhau, cân nhắc health theo service hoặc nhóm service phù hợp; một status tổng thể duy nhất có thể quá thô.

Health status là tín hiệu coarse-grained, không phải thay thế mọi kiểm tra nghiệp vụ. Một backend có thể `SERVING` nhưng một request cụ thể vẫn trả `NOT_FOUND` hoặc `FAILED_PRECONDITION` hợp lệ.

## 7. Khi không còn backend healthy

Health-aware load balancing có thể loại backend `NOT_SERVING` khỏi lựa chọn RPC mới. Nếu mọi backend đều unhealthy hoặc health state chưa được xác nhận, client không có nơi an toàn để gửi RPC.

Hành vi quan sát được phụ thuộc policy và cấu hình:

- RPC có thể thất bại với status như `UNAVAILABLE`.
- RPC có `withWaitForReady()` có thể chờ backend trở lại healthy trong thời gian deadline còn hiệu lực.
- Khi một backend chuyển lại `SERVING`, health watcher có thể cập nhật trạng thái và backend đủ điều kiện được đưa trở lại picker.

Ví dụ:

~~~java
GetOrderReply reply = stub
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` không làm backend khỏe lên và không chờ vô hạn. Deadline vẫn là giới hạn cuối cùng. Với thao tác không còn ý nghĩa sau một khoảng chờ, nên để RPC thất bại sớm thay vì xếp hàng quá lâu.

Không nên tự động retry liên tục mọi status khi không có backend healthy. Phân loại status, dùng backoff/jitter khi phù hợp và giới hạn tổng thời gian retry để tránh tạo thêm tải lên một cụm đang phục hồi.

## 8. Health thay đổi không di chuyển RPC đang chạy

Health-aware load balancing tác động chủ yếu đến **RPC mới**. Khi một backend đổi từ `SERVING` sang `NOT_SERVING`, các lời gọi mới có thể được chuyển sang backend khác sau khi trạng thái health được cập nhật. RPC đã bắt đầu thường vẫn gắn với backend ban đầu.

~~~text
Trước khi drain:
  RPC #1 -> A (đang chạy)
  RPC #2 -> A
  RPC #3 -> B

A chuyển NOT_SERVING:
  RPC mới -> B hoặc C
  RPC #1 vẫn đang chạy trên A

A graceful shutdown:
  chờ RPC #1 hoàn tất trong grace period
  sau đó đóng server
~~~

Đối với server streaming dài, drain có thể kéo dài hơn thời gian dừng instance cho phép. Cần định nghĩa cách kết thúc stream, gửi status phù hợp và để client reconnect/resume bằng cursor nếu dữ liệu phải liên tục. Health status không tự phát lại response hoặc chuyển phần còn lại của stream sang instance khác.

## 9. Graceful shutdown: báo NOT_SERVING trước khi dừng

Khi deploy hoặc shutdown có chủ đích, thứ tự thao tác giúp giảm RPC mới đi vào instance sắp dừng:

1. Đặt health của service thành `NOT_SERVING`.
2. Chờ health signal lan đến client/load balancer hoặc service discovery trong khoảng thời gian có giới hạn.
3. Ngừng nhận công việc mới ở tầng ứng dụng nếu có cơ chế admission/drain.
4. Gọi graceful server shutdown để RPC đang chạy có thời gian hoàn tất.
5. Hết grace period thì hủy các RPC còn lại và đóng dependency.

Ví dụ:

~~~java
public void stop() throws InterruptedException {
    health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    health.setStatus("", ServingStatus.NOT_SERVING);

    if (server != null) {
        server.shutdown();
        if (!server.awaitTermination(20, java.util.concurrent.TimeUnit.SECONDS)) {
            server.shutdownNow();
        }
    }
}
~~~

Đây là ví dụ lifecycle đơn giản. Trong Spring, đặt logic tương ứng trong lifecycle hook phù hợp và bảo đảm thời gian chờ không vượt quá termination grace period của nền tảng. Nếu health checker hoặc resolver có độ trễ cập nhật, chỉ đổi status rồi dừng ngay có thể chưa đủ thời gian để client ngừng chọn instance.

## 10. Tránh health flapping và health check gây quá tải

Nếu health đổi liên tục giữa `SERVING` và `NOT_SERVING`, backend có thể liên tục bị đưa vào/loại khỏi picker. Điều này gây phân phối tải dao động và có thể tạo đợt reconnect lớn.

Một số biện pháp:

- Dùng ngưỡng lỗi liên tiếp hoặc khoảng thời gian ổn định trước khi chuyển trạng thái.
- Dùng hysteresis: ngưỡng đưa backend ra khỏi phục vụ có thể khác ngưỡng đưa trở lại.
- Không thực hiện truy vấn database nặng mỗi khi client gọi `Check` hoặc mở `Watch`.
- Cập nhật health từ monitor định kỳ hoặc sự kiện dependency, với timeout và cache trạng thái ngắn.
- Giới hạn số health watcher và bảo đảm `Watch` được phục vụ hiệu quả.
- Chỉ đánh dấu `SERVING` sau khi dependency đã phục hồi ổn định.

Health endpoint nên trả thông tin tối thiểu cần cho quyết định phục vụ. Không đưa hostname nội bộ, thông tin xác thực, stack trace hoặc chi tiết dependency nhạy cảm vào health response công khai.

## 11. Phân biệt gRPC health, Kubernetes readiness và outlier detection

Các lớp này bổ sung cho nhau:

| Cơ chế | Ai quan sát | Tác động |
|---|---|---|
| gRPC health `Watch` | gRPC client có hỗ trợ client-side health checking | Có thể loại backend khỏi lựa chọn RPC mới trên channel |
| Kubernetes readiness probe | Kubelet/control plane | Pod không được đưa vào endpoint traffic của Service khi không ready |
| Liveness probe | Kubelet | Có thể restart container nếu tiến trình không còn sống |
| Outlier detection | Service mesh/proxy/control plane | Tạm ejection backend có tỷ lệ lỗi/latency bất thường |

Có thể dùng nhiều cơ chế đồng thời, nhưng phải tránh mâu thuẫn. Ví dụ readiness của Kubernetes báo healthy trong khi gRPC health báo `NOT_SERVING`; client trực tiếp có thể vẫn nhìn thấy pod nhưng health checker sẽ loại nó. Ngược lại, nếu Kubernetes đã gỡ endpoint, client không còn phân giải thấy pod dù health status bên trong vẫn `SERVING`.

Outlier detection cũng khác health check chủ động. Nó có thể loại một backend vì thống kê lỗi của traffic thực tế, kể cả khi backend vẫn trả health `SERVING`. Health check trả lời trạng thái được service công bố; outlier detection suy ra hành vi bất thường qua quan sát traffic.

## 12. Kiểm thử health-aware load balancing

Để xác minh hành vi, cần nhiều backend có thể nhận diện riêng và có thể điều khiển health status:

| Tình huống | Kết quả cần xác minh |
|---|---|
| A, B đều `SERVING` | RPC mới có thể được phân phối qua cả hai theo policy |
| B chuyển `NOT_SERVING` | RPC mới không được chọn B sau khi health update được áp dụng |
| B trở lại `SERVING` | B có thể được đưa lại vào picker |
| Health service không biết tên service | Client xử lý trạng thái unknown theo cấu hình, không mặc định coi là healthy |
| Không backend nào `SERVING` | RPC lỗi hoặc chờ theo `waitForReady` và deadline |
| Business port `READY` nhưng database bắt buộc hỏng | Health phản ánh `NOT_SERVING` theo quy tắc nghiệp vụ |
| Shutdown có chủ đích | `NOT_SERVING` được công bố trước graceful shutdown |
| Stream đang chạy khi backend drain | RPC hiện tại có kết cục xác định; client resume nếu cần |
| Health watcher bị ngắt | Client/runtime phục hồi theo hành vi hỗ trợ; không coi im lặng là bằng chứng backend khỏe |
| Nhiều client mở health watch | Server không bị health checking tạo tải quá mức |

Integration test nên xác minh service config thực sự được áp dụng và client runtime có hỗ trợ health checking. Một unit test chỉ gọi `HealthStatusManager.setStatus` chưa chứng minh picker đã loại backend. Cần test qua channel với nhiều instance và quan sát backend nhận RPC.

## 13. Metrics và chẩn đoán

Theo dõi cả health signal và lựa chọn thực tế:

- Số backend `SERVING`/`NOT_SERVING` theo service.
- Thời điểm và nguyên nhân chuyển health status.
- Số subchannel `READY` và số backend đủ điều kiện theo health.
- Số RPC được chọn theo instance.
- Tỷ lệ `UNAVAILABLE`, `DEADLINE_EXCEEDED` và lỗi health watch.
- Thời gian từ lúc backend chuyển `NOT_SERVING` đến khi ngừng nhận RPC mới.
- Thời gian drain và số RPC còn mở khi shutdown.
- Số lần backend flapping hoặc bị outlier ejection.

Nếu backend `NOT_SERVING` vẫn nhận RPC mới, kiểm tra client có bật health checking không, service name có khớp đầy đủ không, health service có được đăng ký không, service config có tới channel không và load balancing provider có hỗ trợ tính năng đó không.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi subchannel `READY` là service healthy | RPC đến backend có dependency hỏng | Dùng health signal ở tầng ứng dụng |
| Chỉ expose health service nhưng client không theo dõi | Health status không ảnh hưởng picker | Cấu hình client-side health checking hoặc discovery tương ứng |
| Health config dùng sai service name | Client theo dõi nhầm service hoặc không nhận trạng thái mong đợi | Dùng tên đầy đủ `package.Service` |
| Đánh dấu `SERVING` ngay khi port mở | Backend nhận traffic trước khi dependency sẵn sàng | Chuyển `SERVING` sau initialization |
| Đánh dấu mọi service `NOT_SERVING` khi một dependency tùy chọn lỗi | Loại backend quá mức | Định nghĩa health theo dependency bắt buộc của từng service |
| Health check truy vấn database nặng liên tục | Health checking tự tạo tải lên dependency đang yếu | Cập nhật status từ monitor có timeout/cache |
| Dừng server ngay sau khi đặt `NOT_SERVING` | Client chưa kịp nhận health update; RPC đang chạy bị cắt | Chờ propagation và graceful drain |
| Nghĩ health change chuyển stream đang chạy | RPC hiện tại vẫn gắn với backend cũ | Reconnect/resume bằng cursor ở tầng ứng dụng |

**Ghi nhớ:** Health-aware load balancing kết hợp danh sách endpoint, trạng thái kết nối và sức khỏe service để chọn backend cho RPC mới. gRPC Health Checking Protocol cung cấp `Check`/`Watch`; server phải công bố trạng thái có ý nghĩa và client/runtime phải thực sự dùng health signal trong picker. `READY` chỉ phản ánh transport, còn `SERVING` phản ánh khả năng phục vụ theo hợp đồng ứng dụng. Khi drain, báo `NOT_SERVING` trước, chờ propagation và graceful shutdown; RPC/stream đang chạy cần retry hoặc resume riêng nếu bị gián đoạn.
