# gRPC Health Checking Protocol

**Chương:** Health and reflection  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và server/client cho unary hoặc streaming RPC. Bài này tập trung vào chuẩn gRPC Health Checking Protocol để load balancer, client và nền tảng triển khai biết một service đang sẵn sàng nhận request hay không.

## 1. Health Checking Protocol giải quyết vấn đề gì?

Một tiến trình có thể đã mở cổng và chấp nhận kết nối nhưng service chưa sẵn sàng xử lý nghiệp vụ. Ví dụ:

- Ứng dụng vẫn đang khởi tạo connection pool hoặc tải cấu hình.
- Migration hoặc bước warm-up bắt buộc chưa hoàn tất.
- Một dependency thiết yếu đang mất kết nối.
- Service đang shutdown và cần ngừng nhận request mới.

Kiểm tra TCP port chỉ xác nhận có tiến trình nhận kết nối. Nó không xác nhận gRPC service đã sẵn sàng. Health Checking Protocol cung cấp một service gRPC chuẩn để caller hỏi trạng thái theo tên service và nhận các cập nhật trạng thái qua streaming.

Health protocol giúp các thành phần bên ngoài quyết định có gửi traffic tới instance hay không. Nó không thay thế kiểm thử nghiệp vụ, authorization hoặc giám sát chi tiết dependency.

## 2. Hai RPC chuẩn: Check và Watch

Health service được định nghĩa trong package `grpc.health.v1`. Hợp đồng chuẩn có hai RPC:

```proto
service Health {
  rpc Check(HealthCheckRequest) returns (HealthCheckResponse);
  rpc Watch(HealthCheckRequest)
      returns (stream HealthCheckResponse);
}

message HealthCheckRequest {
  string service = 1;
}

message HealthCheckResponse {
  enum ServingStatus {
    UNKNOWN = 0;
    SERVING = 1;
    NOT_SERVING = 2;
    SERVICE_UNKNOWN = 3;
  }
  ServingStatus status = 1;
}
```

Ý nghĩa:

- **Check** là unary RPC: client gửi tên service và nhận trạng thái hiện tại một lần.
- **Watch** là server-streaming RPC: client gửi tên service, server gửi trạng thái ban đầu rồi gửi các thay đổi tiếp theo khi trạng thái thay đổi.

Ví dụ tên service:

```text
orders.v1.OrderService
```

Tên này là package protobuf cộng với tên service. Chuỗi rỗng `""` đại diện trạng thái tổng thể của server, không phải tên một service cụ thể.

### Ý nghĩa của ServingStatus

| Trạng thái | Ý nghĩa | Hành vi thường dùng |
| --- | --- | --- |
| `UNKNOWN` | Chưa xác định trạng thái | Trạng thái chưa được đánh giá hoặc khởi tạo |
| `SERVING` | Service sẵn sàng phục vụ | Có thể nhận request |
| `NOT_SERVING` | Service hiện không sẵn sàng | Ngừng route traffic mới tới service |
| `SERVICE_UNKNOWN` | Server không biết service được yêu cầu trong Watch | Client cần xử lý service name sai hoặc chưa được đăng ký |

Với RPC `Check`, service name không được nhận diện thường dẫn đến status gRPC `NOT_FOUND`. Với `Watch`, server có thể gửi `SERVICE_UNKNOWN` để biểu thị tên service chưa biết; stream vẫn có thể tiếp tục để gửi trạng thái khi service được đăng ký sau đó.

Không nhầm enum `NOT_SERVING` với gRPC status code `NOT_FOUND`: một cái là trạng thái health trong response, cái còn lại là kết quả lỗi của RPC.

## 3. Check và Watch được dùng khi nào?

**Check** phù hợp với probe định kỳ hoặc công cụ chỉ cần biết trạng thái tại thời điểm gọi. Mỗi lần gọi tạo một RPC riêng; tần suất quá cao có thể tạo tải không cần thiết.

**Watch** phù hợp với client-side health checking. Client mở một stream và theo dõi trạng thái liên tục. Khi nhận `SERVING`, client có thể đưa backend vào trạng thái đủ điều kiện nhận request; khi nhận `NOT_SERVING`, client ngừng gửi request mới tới backend đó.

Watch giúp tránh polling liên tục, nhưng client cần xử lý reconnect, stream error và trạng thái ban đầu. Nếu stream bị ngắt, client không nên mặc định backend vẫn healthy mãi; hành vi khi mất health stream phụ thuộc chính sách health checker và load balancer.

## 4. Cài đặt health service trong gRPC Java

gRPC Java cung cấp `HealthStatusManager` trong artifact `grpc-services`. Lớp này triển khai service health chuẩn và cung cấp API cập nhật trạng thái:

```java
import io.grpc.BindableService;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

public final class GrpcHealth {

    public static final String ORDER_SERVICE =
            "orders.v1.OrderService";

    private final HealthStatusManager manager =
            new HealthStatusManager();

    public GrpcHealth() {
        manager.setStatus("", ServingStatus.NOT_SERVING);
        manager.setStatus(
                ORDER_SERVICE,
                ServingStatus.NOT_SERVING);
    }

    public BindableService healthService() {
        return manager.getHealthService();
    }

    public void markReady() {
        manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        manager.setStatus("", ServingStatus.SERVING);
    }

    public void markUnavailable() {
        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
        manager.setStatus("", ServingStatus.NOT_SERVING);
    }

    public void stopServing() {
        manager.enterTerminalState();
    }
}
```

Ví dụ khởi tạo cả trạng thái service cụ thể và trạng thái tổng thể là `NOT_SERVING`, rồi chỉ chuyển sang `SERVING` khi ứng dụng đã sẵn sàng. `HealthStatusManager` cung cấp `BindableService` để đăng ký vào gRPC server.

Dependency cần dùng là `io.grpc:grpc-services`; nên quản lý version cùng BOM/version gRPC Java của ứng dụng để tránh lệch phiên bản giữa generated health classes và runtime.

Trong Spring, đăng ký manager như một singleton bean để service registration và lifecycle component cùng cập nhật một nguồn trạng thái:

```java
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    public HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }
}
```

### Đăng ký health service vào server

Với gRPC Java server builder trực tiếp:

```java
HealthStatusManager healthStatusManager =
        new HealthStatusManager();

NettyServerBuilder.forPort(port)
        .addService(orderGrpcService)
        .addService(healthStatusManager.getHealthService())
        .build()
        .start();
```

Trong Spring gRPC, server thường do starter và auto-configuration quản lý. Hãy đăng ký `healthStatusManager.getHealthService()` qua cơ chế server service registration/customizer mà starter của dự án hỗ trợ. Không khởi tạo thêm một server độc lập chỉ để bật health service, vì probe sẽ có thể kiểm tra nhầm cổng hoặc nhầm lifecycle.

Nếu starter có sẵn tích hợp health service, dùng đúng extension point của starter và chỉ tạo một nguồn trạng thái duy nhất. Tránh đăng ký hai implementation cùng service name.

## 5. Quản lý trạng thái theo vòng đời Spring

Health state phải phản ánh khả năng phục vụ thật của ứng dụng, không chỉ trạng thái JVM. Một cách tổ chức là tạo Spring bean quản lý `HealthStatusManager`, sau đó cập nhật nó theo các mốc lifecycle:

```java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class GrpcReadinessLifecycle {

    private static final String ORDER_SERVICE =
            "orders.v1.OrderService";

    private final HealthStatusManager health;

    public GrpcReadinessLifecycle(HealthStatusManager health) {
        this.health = health;
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        // Chỉ gọi khi các điều kiện readiness bắt buộc đã hoàn tất.
        health.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    @EventListener(ContextClosedEvent.class)
    public void applicationStopping() {
        health.enterTerminalState();
    }
}
```

Đây là ví dụ lifecycle tối giản. Trong ứng dụng thực, `ApplicationReadyEvent` chỉ là mốc tham khảo; nếu dependency thiết yếu được kiểm tra bất đồng bộ hoặc có bước warm-up riêng, hãy chờ readiness gate của ứng dụng trước khi gọi `markReady`. Khi shutdown, phải đánh dấu `NOT_SERVING` trước khi server ngừng nhận health RPC và trước giai đoạn drain traffic. Thứ tự lifecycle cụ thể cần phù hợp với cách starter đóng server.

Không để trạng thái mặc định là `SERVING` ngay khi object được tạo. Nếu ứng dụng chưa kết nối database hoặc chưa nạp cấu hình bắt buộc, probe có thể route traffic quá sớm.

## 6. Health status theo service và toàn server

Một server có thể cung cấp nhiều gRPC service. Health status nên được quản lý theo tên service đầy đủ:

```java
health.setStatus(
        "orders.v1.OrderService",
        ServingStatus.SERVING);

health.setStatus(
        "inventory.v1.InventoryService",
        ServingStatus.NOT_SERVING);
```

Client theo dõi `orders.v1.OrderService` có thể tiếp tục route traffic tới service đó, trong khi `inventory.v1.InventoryService` không nhận traffic mới. Trạng thái chuỗi rỗng `""` là trạng thái tổng thể; ứng dụng cần định nghĩa quy tắc tổng hợp rõ ràng.

Ví dụ nếu cả Order và Inventory đều bắt buộc cho mọi request, tổng thể chỉ `SERVING` khi cả hai sẵn sàng. Nếu chúng độc lập, một service hỏng không nhất thiết phải làm service còn lại ngừng phục vụ. Không cập nhật status tổng thể theo cảm tính; hãy xác định quan hệ phụ thuộc và cách load balancer/probe sử dụng tên service.

Khi một dependency thay đổi trạng thái, cập nhật service bị ảnh hưởng:

```java
public void onInventoryDependencyUnavailable() {
    health.setStatus(
            "orders.v1.OrderService",
            ServingStatus.NOT_SERVING);
}

public void onInventoryDependencyRecovered() {
    health.setStatus(
            "orders.v1.OrderService",
            ServingStatus.SERVING);
}
```

Chỉ đánh dấu service `NOT_SERVING` nếu dependency đó thực sự bắt buộc để xử lý request. Nếu service có fallback hợp lệ hoặc chỉ một tính năng phụ bị ảnh hưởng, có thể giữ service serving và báo tình trạng chi tiết qua metrics/monitoring riêng.

## 7. Client-side health checking

Một số gRPC client/load balancer hỗ trợ health checking tự động bằng `Watch`. Service config có thể chỉ định tên service cần kiểm tra:

```json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrderService"
  }
}
```

Khi tính năng được bật và client implementation hỗ trợ, client mở health Watch stream. Backend chỉ được xem là đủ điều kiện nhận request sau khi health status báo `SERVING`. Nếu status chuyển sang `NOT_SERVING`, client ngừng route request mới tới backend đó theo chính sách load balancer.

Không phải mọi gRPC client, ngôn ngữ hoặc load balancer đều bật client-side health checking mặc định. Cần xác minh hỗ trợ của runtime, service config có được áp dụng hay không và health service có được expose trên cùng endpoint mà client kiểm tra hay không.

Với client tự viết, có thể dùng `HealthGrpc.HealthStub` gọi `watch()` và duy trì state theo stream. Client cần xử lý reconnect/backoff, cancellation khi channel đóng và không route traffic khi chưa nhận được trạng thái serving đáng tin cậy.

## 8. Kết hợp với readiness và liveness probe

Health Checking Protocol là giao thức báo trạng thái phục vụ của gRPC service. Nó thường được dùng để triển khai readiness probe, nhưng không đồng nghĩa với mọi loại health probe:

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| Liveness | Tiến trình có còn hoạt động theo tiêu chí nền tảng không? | Nền tảng có thể restart container/process |
| Readiness | Instance có thể nhận request mới không? | Nền tảng/load balancer ngừng route traffic |
| Startup | Ứng dụng đã hoàn thành giai đoạn khởi động chưa? | Nền tảng trì hoãn liveness/readiness theo cấu hình |
| gRPC Health Check | Service name được hỏi có đang `SERVING` không? | Client/probe quyết định route hoặc đánh dấu unhealthy |

Không đánh dấu liveness thất bại chỉ vì database tạm thời mất kết nối. Nếu readiness chuyển `NOT_SERVING`, instance có thể được rút khỏi traffic để tránh lỗi dây chuyền; restart liên tục không nhất thiết sửa được dependency outage.

Một số nền tảng có probe gRPC native gọi unary `Check`; một số hệ thống khác dùng HTTP health endpoint hoặc client-side `Watch`. Cần cấu hình đúng service name và port. Không giả định nền tảng đang dùng hỗ trợ mọi dạng probe.

## 9. Shutdown và graceful draining

Khi ứng dụng shutdown:

1. Chuyển service health sang `NOT_SERVING` hoặc gọi `enterTerminalState()`.
2. Cho load balancer/client-side health checker thời gian nhận trạng thái mới.
3. Ngừng nhận request mới theo cơ chế graceful shutdown của server.
4. Chờ các RPC đang chạy hoàn tất trong giới hạn thời gian.
5. Đóng channel, executor và dependency.

Nếu đóng server trước khi cập nhật health state, probe có thể chỉ thấy kết nối bị reset thay vì trạng thái `NOT_SERVING` có chủ đích. Nếu đánh dấu `NOT_SERVING` quá muộn, load balancer vẫn có thể gửi request trong lúc dependency đã dừng.

Health Watch stream cũng phải được kết thúc đúng theo lifecycle server. Không để một background health publisher tiếp tục cập nhật state sau khi Spring context đã đóng.

## 10. Bảo mật và giới hạn thông tin health

Health endpoint thường được probe nội bộ gọi, nhưng vẫn là một RPC endpoint có thể bị truy cập nếu mở ra mạng rộng. Nên:

- Giới hạn network access hoặc áp dụng authentication/authorization phù hợp với nền tảng probe.
- Chỉ công bố service name và trạng thái phục vụ cần thiết.
- Không đưa hostname, connection string, token, SQL hoặc exception message vào health response.
- Không dùng health response thay cho diagnostic API hoặc metrics.
- Đảm bảo health service không bị chặn bởi cùng một dependency đang gặp sự cố; nếu probe phải truy vấn database mỗi lần, chính probe có thể timeout khi database quá tải.

Health status nên được cập nhật từ readiness state/health evaluator có kiểm soát. Tránh thực hiện một loạt dependency checks đồng bộ trong từng lần `Check`; điều đó có thể khuếch đại sự cố khi probe được gọi thường xuyên.

## 11. Kiểm thử Health Checking Protocol

Nên kiểm thử cả trạng thái hiện tại và stream cập nhật:

| Ca | Kỳ vọng |
| --- | --- |
| Service khởi động nhưng chưa ready | `Check` trả `NOT_SERVING` |
| Service đã ready | `Check` trả `SERVING` |
| Tên service không tồn tại qua Check | RPC trả `NOT_FOUND` |
| Tên service chưa biết qua Watch | Stream báo `SERVICE_UNKNOWN` theo protocol |
| Status đổi từ serving sang not serving | Watch client nhận update mới |
| Một service ngừng phục vụ, service khác vẫn hoạt động | Status từng service phản ánh đúng độc lập |
| Shutdown bắt đầu | Status chuyển sang not serving trước khi server drain |
| Client hủy Watch | Server giải phóng stream/call state |

Ví dụ test Check qua in-process server:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcHealthCheckTest {

    @Test
    void reportsServiceStatus() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        HealthStatusManager manager = new HealthStatusManager();
        manager.setStatus(
                "orders.v1.OrderService",
                ServingStatus.SERVING);

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(manager.getHealthService())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            var response = HealthGrpc.newBlockingStub(channel)
                    .check(HealthCheckRequest.newBuilder()
                            .setService("orders.v1.OrderService")
                            .build());

            assertEquals(ServingStatus.SERVING, response.getStatus());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

Test này xác nhận service health được đăng ký và client gọi được generated health stub qua gRPC channel. Nên bổ sung test cho `NOT_SERVING`, unknown service và Watch stream. Với Watch, dùng latch/future có timeout để chờ các status update; không dùng `Thread.sleep()` làm cơ chế đồng bộ.

## 12. Tự luyện tập

1. Vì sao TCP port mở chưa chứng minh gRPC service sẵn sàng?
2. Phân biệt `Check` unary với `Watch` server-streaming; khi nào client-side health checking cần Watch?
3. Một server có hai service độc lập, một service mất dependency. Hãy xác định status của từng service và status tổng thể.
4. Vì sao không nên thực hiện database query đồng bộ trong mỗi lần health Check?
5. Thiết kế trình tự cập nhật `NOT_SERVING` và graceful shutdown để load balancer ngừng gửi request trước khi server đóng.

**Ghi nhớ:** gRPC Health Checking Protocol chuẩn cung cấp `Check` để hỏi trạng thái một lần và `Watch` để theo dõi thay đổi. Dùng tên service protobuf đầy đủ, quản lý `SERVING`/`NOT_SERVING` theo readiness thực tế, đăng ký health service vào đúng Spring gRPC server và cập nhật trạng thái trước khi shutdown. Health response phải nhanh, an toàn và không tiết lộ chi tiết nội bộ.
