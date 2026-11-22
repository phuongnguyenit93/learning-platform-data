# Health status của service

## 1. Health status cho biết service có thể nhận RPC hay không

Trong **SPRING_GRPC**, một service được định nghĩa bằng Protocol Buffers, sinh mã Java và được đăng ký vào gRPC server do ứng dụng Spring quản lý. Khi service chạy trong môi trường nhiều instance, client, load balancer hoặc nền tảng triển khai cần biết instance nào thực sự có thể phục vụ request.

**Health status** là tín hiệu ở tầng ứng dụng cho biết một service cụ thể đang sẵn sàng phục vụ hay không. Nó giúp phân biệt:

- Tiến trình còn chạy.
- TCP/HTTP/2 connection đã thiết lập.
- Service nghiệp vụ đã khởi tạo xong và có thể xử lý RPC.

Ba điều này không đồng nghĩa. Một gRPC server có thể nhận kết nối và subchannel ở trạng thái `READY`, nhưng `OrdersService` vẫn chưa thể xử lý request vì database bắt buộc chưa kết nối hoặc quá trình khởi tạo chưa hoàn tất.

## 2. gRPC Health Checking Protocol

gRPC định nghĩa health service chuẩn `grpc.health.v1.Health` với hai RPC:

- `Check`: truy vấn trạng thái hiện tại của một service.
- `Watch`: đăng ký nhận trạng thái ban đầu và các thay đổi trạng thái tiếp theo.

Request mang tên service cần kiểm tra. Tên này thường là tên đầy đủ trong protobuf, gồm package và service, ví dụ `orders.v1.OrdersService`; không phải tên Java class hay Spring bean.

Health response dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `UNKNOWN` | Chưa xác định trạng thái |
| `SERVING` | Service có thể phục vụ |
| `NOT_SERVING` | Service hiện không nên nhận RPC mới |
| `SERVICE_UNKNOWN` | Health service không biết service được yêu cầu; trạng thái này được dùng trong luồng `Watch` |

`Check` phù hợp với probe hỏi trạng thái tại một thời điểm. `Watch` phù hợp với client muốn theo dõi thay đổi liên tục mà không phải polling liên tục. Nếu tên service không được đăng ký, `Check` có thể trả status `NOT_FOUND`; `Watch` có thể phát `SERVICE_UNKNOWN` và tiếp tục theo dõi để nhận cập nhật nếu service xuất hiện.

## 3. Trạng thái được quản lý theo tên service

Một gRPC server có thể cung cấp nhiều service. Health status nên phản ánh riêng khả năng phục vụ của từng service:

~~~text
gRPC server
  ├── orders.v1.OrdersService        SERVING
  ├── inventory.v1.InventoryService  NOT_SERVING
  └── payments.v1.PaymentsService    SERVING
~~~

Như vậy, lỗi dependency chỉ ảnh hưởng `InventoryService` không nhất thiết khiến `OrdersService` và `PaymentsService` cùng bị đánh dấu `NOT_SERVING`.

Health protocol cũng cho phép dùng tên service rỗng (`""`) để biểu diễn trạng thái tổng thể của server. Trạng thái tổng thể hữu ích cho probe ở cấp server, nhưng không thay thế trạng thái theo từng service khi chúng có dependency và khả năng phục vụ khác nhau.

Không dùng tên Java package thay cho protobuf service name. Nếu protobuf khai báo:

~~~proto
package orders.v1;

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}
~~~

thì health key là `orders.v1.OrdersService`.

## 4. Expose health service bằng gRPC Java

Artifact `grpc-services` cung cấp `HealthStatusManager`, một implementation quản lý trạng thái và cung cấp health service để đăng ký vào server:

~~~java
import io.grpc.Server;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;

public final class OrdersGrpcServer {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health =
            new HealthStatusManager();

    private Server server;

    public void start(OrdersServiceImpl ordersService)
            throws java.io.IOException {
        // Server chưa sẵn sàng cho đến khi dependency được kiểm tra.
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);

        server = NettyServerBuilder.forPort(9090)
                .addService(ordersService)
                .addService(health.getHealthService())
                .build()
                .start();
    }

    public void markReady() {
        health.setStatus(SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    public void markNotReady() {
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
        health.setStatus("", ServingStatus.NOT_SERVING);
    }
}
~~~

`HealthStatusManager` cần được dùng chung giữa nơi cập nhật trạng thái và health service đã đăng ký. Nếu tạo hai manager khác nhau, service có thể tiếp tục trả trạng thái cũ dù component readiness đã cập nhật manager còn lại.

Đoạn code dùng Netty shaded transport và minh họa cách đăng ký trực tiếp trong gRPC Java. Dự án cần dependency `grpc-services` tương thích với các artifact gRPC còn lại.

## 5. Quản lý health status theo lifecycle Spring

Trong ứng dụng Spring, quản lý một `HealthStatusManager` như bean và inject cùng instance đó vào component theo dõi lifecycle:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }
}
~~~

Component lifecycle có thể đặt trạng thái ban đầu, chuyển sang `SERVING` sau khi ứng dụng sẵn sàng và chuyển lại `NOT_SERVING` khi shutdown:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersHealthLifecycle {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health;

    public OrdersHealthLifecycle(HealthStatusManager health) {
        this.health = health;
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        // Chỉ dùng ApplicationReadyEvent khi các dependency
        // bắt buộc đã được kiểm tra và server đã đăng ký health service.
        health.setStatus(SERVICE, ServingStatus.SERVING);
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosing() {
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }
}
~~~

Health service phải được đăng ký vào gRPC server thông qua cơ chế service registration của Spring gRPC starter đang dùng. Với starter quản lý server tự động, hãy đưa `health.getHealthService()` vào danh sách service mà server publish; không tự tạo một server Netty thứ hai chỉ để expose health.

`ApplicationReadyEvent` là một mốc lifecycle tiện dụng, nhưng không tự chứng minh mọi dependency nghiệp vụ đã khỏe. Nếu service có bước readiness riêng, hãy gọi `markReady` sau khi bước đó thành công và cập nhật lại status khi dependency bắt buộc mất khả năng phục vụ.

## 6. Health status phải phản ánh khả năng phục vụ nghiệp vụ

Một service chỉ nên báo `SERVING` khi có thể xử lý các RPC mà nó cam kết. Hãy xác định dependency nào thực sự bắt buộc:

| Dependency | Ví dụ quyết định |
|---|---|
| Database chính mà mọi RPC cần | Không kết nối được có thể chuyển service sang `NOT_SERVING` |
| Message broker chỉ dùng cho một RPC cụ thể | Có thể chỉ ảnh hưởng service/nhóm RPC phụ thuộc broker |
| Cache có thể fallback sang database | Không nhất thiết làm service ngừng phục vụ |
| Dịch vụ phân tích không thiết yếu | Lỗi có thể chỉ làm mất tính năng phụ |

Đừng đánh dấu toàn bộ server `NOT_SERVING` chỉ vì một dependency tùy chọn gặp sự cố. Ngược lại, đừng giữ `SERVING` khi dependency bắt buộc đã mất và request chắc chắn không thể hoàn tất.

Health check không nên thực hiện truy vấn nặng đến mọi dependency mỗi lần có `Check`. Nên cập nhật trạng thái từ readiness coordinator hoặc dependency monitor có timeout, cache kết quả ngắn và giới hạn tần suất. `Watch` nên nhận thay đổi từ trạng thái đã được quản lý thay vì kích hoạt một loạt kiểm tra mới cho mỗi watcher.

## 7. Phân biệt health, readiness và liveness

Ba tín hiệu thường được dùng cùng nhau nhưng phục vụ mục đích khác nhau:

| Tín hiệu | Câu hỏi | Hành động thường gặp |
|---|---|---|
| Liveness | Tiến trình có còn hoạt động hay bị kẹt đến mức cần restart? | Nền tảng khởi động lại container/process |
| Readiness | Instance có nên nhận traffic mới không? | Loại instance khỏi endpoint/traffic pool |
| gRPC health status | Service gRPC cụ thể có đang phục vụ được không? | Probe, client health checking hoặc load balancer loại service khỏi lựa chọn |

Một ứng dụng có thể còn sống (`liveness` tốt) nhưng chưa sẵn sàng (`readiness` kém) vì đang warm up. Nếu liveness phụ thuộc trực tiếp vào database, database chập chờn có thể làm container restart liên tục dù tiến trình vẫn khỏe.

Với Kubernetes, gRPC probe có thể kiểm tra health service trên port được chỉ định:

~~~yaml
readinessProbe:
  grpc:
    port: 9090
    service: orders.v1.OrdersService
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Probe này chỉ có ý nghĩa khi health service đã được đăng ký và trạng thái được cập nhật đúng. Nên dùng readiness để ngừng đưa traffic mới đến service không sẵn sàng. Liveness cần phản ánh tình trạng tiến trình; không cấu hình để một dependency tùy chọn lỗi gây restart loop.

## 8. Client-side health checking và load balancing

Một gRPC client có thể dùng health checking để theo dõi backend qua RPC `Watch`. Service config có thể chỉ định tên service cần kiểm tra:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrdersService"
  }
}
~~~

Khi runtime và load balancing policy hỗ trợ client-side health checking, subchannel chỉ được xem là đủ điều kiện nhận RPC mới khi health signal thỏa điều kiện, thường là `SERVING`. Khi service chuyển `NOT_SERVING`, picker có thể ngừng chọn backend đó cho RPC mới; khi trở lại `SERVING`, backend có thể được đưa vào lựa chọn.

Việc expose health service ở server chưa tự bật client-side health checking. Client cần nhận service config và runtime/provider phải hỗ trợ tính năng này. Nếu hệ thống dùng proxy hoặc service mesh, health policy có thể do proxy thực hiện thay vì gRPC client.

Health status thay đổi không tự di chuyển RPC đang chạy sang instance khác. Unary RPC đang xử lý vẫn có thể hoàn tất hoặc thất bại ở backend cũ; server stream đang mở không tự chuyển phần còn lại sang backend mới. Client cần retry khi RPC còn đủ điều kiện hoặc reconnect/resume bằng cursor nếu stream cần tiếp tục.

## 9. Graceful shutdown: chuyển NOT_SERVING trước

Khi triển khai phiên bản mới hoặc dừng instance, thứ tự cập nhật health giúp giảm RPC mới đi vào server sắp dừng:

1. Đặt health status của service thành `NOT_SERVING`.
2. Đánh dấu readiness false hoặc deregister instance khỏi discovery.
3. Chờ health update và endpoint change lan đến client/load balancer trong khoảng thời gian có giới hạn.
4. Drain RPC đang chạy trong grace period.
5. Đóng server và các dependency còn lại.

Ví dụ phần cập nhật status:

~~~java
health.setStatus(
        "orders.v1.OrdersService",
        ServingStatus.NOT_SERVING);
~~~

Không dừng server ngay sau khi cập nhật status nếu client cần thời gian nhận `Watch` update hoặc resolver cần thời gian refresh. Với server stream dài, xác định chính sách kết thúc stream và cơ chế reconnect/resume ở client. `NOT_SERVING` chỉ ngăn lựa chọn RPC mới ở các thành phần có theo dõi health; nó không tự hủy hoặc chuyển RPC đã bắt đầu.

## 10. Health status không phải cơ chế authorization

Health endpoint thường được gọi bởi probe, load balancer hoặc hệ thống giám sát. Nó nên trả tín hiệu tối thiểu cần thiết, không tiết lộ:

- Connection string hoặc thông tin xác thực.
- Hostname nội bộ và cấu trúc mạng nhạy cảm.
- Stack trace hoặc exception chi tiết.
- Dữ liệu khách hàng hoặc payload nghiệp vụ.

Giới hạn nơi có thể truy cập health service bằng network policy, listener nội bộ hoặc cơ chế xác thực phù hợp với hạ tầng. Nếu probe của nền tảng không gửi được credential, thiết kế endpoint/probe riêng trong vùng mạng được kiểm soát; không vì tiện lợi mà bỏ xác thực cho toàn bộ API nghiệp vụ.

Health status cũng không chứng minh caller có quyền gọi `GetOrder` hoặc `CreateOrder`. Authentication và authorization vẫn phải được thực hiện trên RPC nghiệp vụ.

## 11. Kiểm thử health status

Kiểm thử cần xác minh cả trạng thái được công bố lẫn tác động của nó:

| Tình huống | Điều cần xác minh |
|---|---|
| Server vừa khởi động | Service ở `NOT_SERVING` hoặc trạng thái chưa xác định cho đến khi readiness hoàn tất |
| Dependency bắt buộc sẵn sàng | Status chuyển sang `SERVING` |
| Dependency bắt buộc mất kết nối | Status chuyển `NOT_SERVING` theo chính sách |
| Dependency tùy chọn lỗi | Service vẫn `SERVING` nếu vẫn đáp ứng hợp đồng |
| `Check` đúng service name | Trả trạng thái hiện tại |
| `Watch` đúng service name | Nhận trạng thái ban đầu và các thay đổi tiếp theo |
| Service name không tồn tại | Xử lý `NOT_FOUND`/`SERVICE_UNKNOWN` đúng theo RPC và implementation |
| Server cung cấp nhiều service | Status từng service độc lập; status `""` theo chính sách tổng thể |
| Shutdown | Status thành `NOT_SERVING` trước khi server drain |
| Client health checking | Backend `NOT_SERVING` không nhận RPC mới sau khi update được áp dụng |
| Watch bị ngắt | Client/runtime phục hồi theo chính sách, không coi im lặng là bằng chứng healthy |

Unit test cho `HealthStatusManager` xác minh việc cập nhật trạng thái. Integration test qua channel hoặc probe thực tế mới chứng minh health service được đăng ký, tên service đúng và client/load balancer thực sự dùng status.

## 12. Quan sát và chẩn đoán

Theo dõi:

- Số service `SERVING` và `NOT_SERVING` theo instance.
- Thời điểm và nguyên nhân chuyển trạng thái.
- Thời gian từ khi readiness thay đổi đến khi probe/client nhận được cập nhật.
- Số health `Check` và `Watch`, lỗi watcher và số watcher đang mở.
- Số subchannel `READY` so với số backend `SERVING`.
- RPC mới đến backend sau thời điểm backend chuyển `NOT_SERVING`.
- Thời gian drain và số RPC/stream còn mở khi shutdown.

Nếu probe báo healthy nhưng RPC nghiệp vụ thất bại, kiểm tra health policy có phản ánh đúng dependency bắt buộc không. Nếu server đã `NOT_SERVING` nhưng vẫn nhận RPC mới, kiểm tra probe đang gọi đúng service name chưa, client/proxy có bật health checking không và endpoint discovery đã cập nhật chưa.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra TCP port | Server nhận kết nối nhưng service chưa sẵn sàng | Expose gRPC health service |
| Dùng sai tên service | Probe/client không tìm thấy status cần kiểm tra | Dùng tên đầy đủ `package.Service` |
| Chỉ đăng ký health service nhưng không cập nhật status | Health response không phản ánh lifecycle thật | Quản lý `HealthStatusManager` theo readiness |
| Tạo nhiều `HealthStatusManager` độc lập | Health service trả trạng thái khác với component cập nhật | Dùng một manager được chia sẻ |
| Đánh dấu `SERVING` ngay khi server bind port | Traffic đến trước khi dependency sẵn sàng | Chỉ chuyển `SERVING` sau readiness |
| Gắn liveness với dependency tùy chọn | Container restart liên tục khi dependency chập chờn | Tách liveness khỏi readiness/health nghiệp vụ |
| Dừng server ngay sau `NOT_SERVING` | Client chưa nhận update; RPC đang chạy bị cắt | Chờ propagation và graceful drain |
| Nghĩ health change tự chuyển stream | Stream hiện tại vẫn gắn với backend ban đầu | Reconnect/resume bằng cursor |
| Trả chi tiết dependency trong health response | Rò rỉ thông tin nội bộ | Chỉ trả status tối thiểu |

**Ghi nhớ:** Health status của service là tín hiệu ứng dụng theo tên gRPC service, được công bố qua `grpc.health.v1.Health` bằng `Check` và `Watch`. Dùng `HealthStatusManager` để quản lý trạng thái, chia sẻ cùng instance giữa health service và lifecycle component, chỉ báo `SERVING` sau readiness và chuyển `NOT_SERVING` trước khi drain. Phân biệt liveness, readiness và connectivity; health status giúp điều phối RPC mới nhưng không tự phục hồi RPC hoặc stream đang chạy.
