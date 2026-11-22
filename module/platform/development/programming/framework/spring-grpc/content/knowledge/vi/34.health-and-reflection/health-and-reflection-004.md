# Thay đổi health khi dependency lỗi

Health của một dịch vụ không chỉ phản ánh tiến trình còn chạy hay không. Nó còn cho biết instance có thể nhận và xử lý loại request mà hệ thống đang định tuyến tới hay không. Với **Spring gRPC**, khi database, service xác thực hoặc một downstream quan trọng gặp sự cố, ứng dụng cần cập nhật trạng thái health để readiness probe, load balancer và gRPC health client đưa ra quyết định đúng.

Không nên đánh dấu toàn bộ tiến trình là unhealthy chỉ vì một request downstream thất bại. Cần xác định dependency nào là bắt buộc, lỗi có đủ bền vững để xem là sự cố hay chỉ là lỗi đơn lẻ, và những RPC nào thực sự bị ảnh hưởng. Health nên thay đổi theo trạng thái đã được đánh giá, có ngưỡng và cơ chế phục hồi để tránh liên tục chuyển UP/DOWN khi dependency chập chờn.

## 1. Phân biệt liveness, readiness và trạng thái của từng RPC service

Ba khái niệm có mục đích khác nhau:

| Loại health | Câu hỏi cần trả lời | Khi dependency lỗi |
| --- | --- | --- |
| **Liveness** | Tiến trình còn sống và có khả năng tiếp tục chạy không? | Thường vẫn healthy; lỗi dependency bên ngoài không phải lý do khởi động lại process |
| **Readiness** | Instance có nên nhận traffic mới không? | Chuyển không ready nếu dependency thiết yếu khiến phần lớn chức năng không thể phục vụ |
| **gRPC service health** | Một service/method group cụ thể có đang phục vụ được không? | Có thể đặt NOT_SERVING cho đúng service bị ảnh hưởng, giữ service khác SERVING |

Ví dụ, ứng dụng có OrderService và CatalogService. Nếu database đơn hàng ngừng hoạt động nhưng catalog vẫn đọc được từ cache, không nhất thiết phải đánh dấu toàn bộ server ngừng phục vụ. Có thể đặt health của OrderService thành NOT_SERVING, trong khi CatalogService vẫn SERVING.

Với Kubernetes, readiness thất bại thường khiến pod bị loại khỏi endpoint nhận traffic; liveness thất bại có thể khiến container bị restart. Không đưa dependency readiness vào liveness một cách máy móc, vì database outage kéo dài có thể tạo vòng lặp restart mà không sửa được database.

## 2. Phân loại dependency theo mức độ ảnh hưởng

Trước khi thay đổi health, hãy phân loại dependency:

- **Critical cho toàn ứng dụng:** nếu lỗi, gần như mọi RPC không thể hoàn thành, ví dụ kho dữ liệu chính khi mọi method đều cần ghi/đọc dữ liệu đó.
- **Critical cho một service hoặc nhóm method:** chỉ một phần API bị ảnh hưởng, ví dụ PaymentService cần payment ledger nhưng ProfileService vẫn hoạt động.
- **Optional hoặc có fallback:** lỗi có thể làm giảm tính năng nhưng ứng dụng vẫn phục vụ được, ví dụ recommendation service khi có thể trả kết quả cơ bản.
- **Dependency có thể phục hồi qua cache/queue:** lỗi tạm thời không nhất thiết làm readiness thất bại nếu hệ thống có khả năng tiếp tục nhận và xử lý request theo hợp đồng.

Health phải phản ánh khả năng phục vụ thực tế. Một dependency optional không nên làm pod bị loại khỏi load balancer nếu các RPC chính vẫn hoạt động. Ngược lại, nếu dependency critical khiến mọi request ghi đều thất bại, giữ readiness UP có thể khiến hệ thống liên tục gửi traffic vào instance không thể xử lý.

## 3. Không đổi health theo một lỗi đơn lẻ

Một lỗi RPC có thể do request không hợp lệ, quyền truy cập, deadline caller quá ngắn hoặc lỗi mạng thoáng qua. Không phải lỗi nào cũng cho thấy dependency đã hỏng.

Ví dụ phân loại:

| Kết quả downstream | Có nên cập nhật dependency health? | Lý do |
| --- | --- | --- |
| UNAVAILABLE lặp lại | Có thể | Có thể cho thấy service hoặc connection không sẵn sàng |
| DEADLINE_EXCEEDED lặp lại với timeout nội bộ hợp lý | Có thể | Có thể phản ánh downstream quá chậm hoặc quá tải |
| RESOURCE_EXHAUSTED | Tùy nguyên nhân | Có thể là throttling/quota hoặc cạn capacity |
| INVALID_ARGUMENT | Không | Lỗi dữ liệu/request của caller |
| PERMISSION_DENIED | Không | Lỗi quyền hoặc policy, không phải availability |
| CANCELLED từ caller | Không | Caller đã hủy; không chứng minh dependency lỗi |
| NOT_FOUND nghiệp vụ | Không | Kết quả hợp lệ theo trạng thái dữ liệu |

Chỉ ghi nhận lỗi có thể quy về dependency. Ví dụ DEADLINE_EXCEEDED từ client không đủ để đánh dấu database lỗi nếu caller đã cấp deadline quá ngắn. Nên phân biệt timeout của call downstream với deadline tổng của request vào service.

## 4. Dùng circuit breaker hoặc bộ theo dõi trạng thái

Một cách phổ biến là dùng circuit breaker hoặc dependency monitor làm nguồn trạng thái. Circuit breaker thường có ba trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: lỗi vượt ngưỡng
    OPEN --> HALF_OPEN: hết thời gian chờ
    HALF_OPEN --> CLOSED: đủ probe thành công
    HALF_OPEN --> OPEN: probe thất bại
~~~

- **CLOSED:** request được phép đi tới dependency; lỗi được thống kê.
- **OPEN:** tạm ngừng gọi dependency hoặc fail fast để tránh tiếp tục gây tải.
- **HALF_OPEN:** cho một số request/probe giới hạn thử khả năng phục hồi.

Ứng dụng có thể ánh xạ trạng thái này sang health. Với dependency critical, OPEN thường làm readiness của service phụ thuộc chuyển OUT_OF_SERVICE hoặc gRPC NOT_SERVING. Chỉ chuyển về SERVING sau khi có bằng chứng phục hồi, chẳng hạn đủ probe thành công trong HALF_OPEN.

Để tránh health flapping, dùng ngưỡng lỗi, cửa sổ thống kê, cooldown và số lần thành công liên tiếp trước khi phục hồi. Không chuyển SERVING chỉ vì một request ngẫu nhiên thành công ngay sau một đợt lỗi.

## 5. Cập nhật Spring Boot Actuator readiness

Spring Boot Actuator cho phép viết HealthIndicator để công bố trạng thái dependency. Indicator nên đọc trạng thái đã được cập nhật bởi circuit breaker hoặc monitor, không thực hiện một network call blocking mới mỗi lần endpoint health được truy vấn.

Ví dụ abstraction trạng thái:

~~~java
public interface DependencyAvailability {
    boolean isCriticalDependencyReady();
    String state();
}
~~~

Health indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersDependency")
public final class OrdersDependencyHealthIndicator
        implements HealthIndicator {

    private final DependencyAvailability availability;

    public OrdersDependencyHealthIndicator(
            DependencyAvailability availability) {
        this.availability = availability;
    }

    @Override
    public Health health() {
        if (!availability.isCriticalDependencyReady()) {
            return Health.outOfService()
                .withDetail("dependency", "orders-database")
                .withDetail("state", availability.state())
                .build();
        }

        return Health.up()
            .withDetail("dependency", "orders-database")
            .withDetail("state", availability.state())
            .build();
    }
}
~~~

DependencyAvailability là abstraction của ứng dụng, được cập nhật từ event của circuit breaker hoặc monitor. Tránh để health() tự gọi database hoặc downstream với timeout dài: health probe có thể bị treo, tạo thêm tải đúng lúc dependency đang quá tải.

Có thể cấu hình health group riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ordersDependency
        liveness:
          include: livenessState
~~~

Tên contributor trong include phải khớp ID health indicator đã đăng ký. Chỉ đưa dependency critical cho khả năng nhận traffic của pod vào readiness group. Dependency optional nên hiển thị detail/metric degraded nhưng không nhất thiết làm readiness thất bại.

## 6. Cập nhật gRPC Health Checking Protocol

gRPC định nghĩa health service chuẩn với hai RPC chính:

- Check: client hỏi trạng thái hiện tại của một service.
- Watch: client đăng ký stream để nhận thay đổi trạng thái khi health thay đổi.

Với gRPC Java, HealthStatusManager trong thư viện grpc-services giúp quản lý trạng thái và cung cấp service implementation. Dự án cần dependency grpc-services cùng phiên bản tương thích với các artifact gRPC Java đang dùng:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager healthStatusManager =
    new HealthStatusManager();

healthStatusManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(orderService)
    .addService(healthStatusManager.getHealthService())
    .build()
    .start();

// Chỉ chuyển sang SERVING sau khi dependency critical đã sẵn sàng.
healthStatusManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.SERVING);
~~~

Ví dụ minh họa server gRPC Java thuần. Khi Spring gRPC starter tự quản lý server, hãy đăng ký healthStatusManager.getHealthService() qua cơ chế service registration hoặc server builder customizer mà starter đang dùng hỗ trợ; không tạo server thứ hai chỉ để thêm health service.

Tên service trong health protocol phải khớp tên service đầy đủ trong gRPC method path, ví dụ acme.orders.v1.OrderService. Chuỗi rỗng "" đại diện trạng thái tổng thể của server. Chỉ đặt trạng thái tổng thể thành NOT_SERVING khi toàn bộ server thực sự không thể nhận traffic; nếu chỉ một service lỗi, cập nhật tên service tương ứng.

## 7. Đẩy trạng thái dependency sang gRPC health service

Khi monitor hoặc circuit breaker phát hiện dependency chuyển trạng thái, publisher cập nhật health manager. Chỉ publish khi trạng thái thay đổi để tránh phát sự kiện lặp:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public final class OrdersGrpcHealthPublisher {

    private static final String SERVICE =
        "acme.orders.v1.OrderService";

    private final HealthStatusManager healthManager;
    private final AtomicReference<ServingStatus> current =
        new AtomicReference<>(ServingStatus.NOT_SERVING);

    public OrdersGrpcHealthPublisher(
            HealthStatusManager healthManager) {
        this.healthManager = healthManager;
        healthManager.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    public void dependencyUnavailable() {
        publish(ServingStatus.NOT_SERVING);
    }

    public void dependencyRecovered() {
        publish(ServingStatus.SERVING);
    }

    private void publish(ServingStatus next) {
        ServingStatus previous = current.getAndSet(next);
        if (previous != next) {
            healthManager.setStatus(SERVICE, next);
        }
    }
}
~~~

Các phương thức dependencyUnavailable() và dependencyRecovered() nên được gọi từ event đã qua ngưỡng của circuit breaker/monitor, không gọi trực tiếp cho mọi exception của từng request. Publisher khởi tạo ở NOT_SERVING; sau khi dependency critical được kiểm tra và application initialization hoàn tất, ứng dụng mới gọi dependencyRecovered() để chuyển sang SERVING.

Khi setStatus thay đổi, client đang dùng Watch có thể nhận trạng thái mới. Điều này giúp load balancer hoặc health-aware client ngừng chọn service không còn phục vụ được và tiếp tục theo dõi khi service hồi phục.

## 8. Dependency lỗi nhưng chỉ một phần API bị ảnh hưởng

Không phải mọi dependency đều dùng chung cho mọi RPC. Có thể duy trì health theo service:

| Dependency lỗi | Service bị ảnh hưởng | Cách công bố |
| --- | --- | --- |
| Orders database | OrderService | OrderService = NOT_SERVING; service khác giữ trạng thái riêng |
| Payment ledger | PaymentService | Chỉ payment service chuyển NOT_SERVING |
| Recommendation service optional | Không làm hỏng chức năng cốt lõi | Giữ SERVING, thêm detail/metric degraded |
| Shared identity provider critical cho mọi RPC | Nhiều service hoặc toàn server | Cập nhật các service phụ thuộc; trạng thái tổng thể chỉ đổi nếu toàn server không thể phục vụ |

Readiness HTTP của pod là một quyết định ở phạm vi instance. Nếu một service không ready nhưng các service khác vẫn hữu ích, cân nhắc dùng service-level gRPC health và routing theo method thay vì loại cả pod khỏi mọi traffic. Khả năng routing theo service phụ thuộc load balancer; nếu hạ tầng chỉ hỗ trợ readiness cấp pod, cần chọn chính sách tổng thể phù hợp với API quan trọng nhất.

## 9. Phục hồi health và tránh flapping

Khi dependency bắt đầu hoạt động lại, đừng chuyển health ngay sau một probe đơn lẻ. Một chu trình phục hồi nên có:

1. Chờ cooldown sau khi circuit mở.
2. Chuyển sang HALF_OPEN và giới hạn số probe.
3. Yêu cầu một số lần probe thành công liên tiếp hoặc tỷ lệ thành công đạt ngưỡng.
4. Kiểm tra dependency đủ khả năng nhận tải thật, không chỉ TCP connect thành công.
5. Chuyển health về SERVING và cho traffic tăng dần nếu hạ tầng hỗ trợ.
6. Nếu lỗi tái diễn, quay lại NOT_SERVING theo ngưỡng đã định.

Health check chủ động cần dùng timeout ngắn, tần suất có giới hạn và executor riêng. Không để hàng nghìn pod đồng loạt probe một database đang phục hồi. Có thể dùng jitter cho lịch probe và giới hạn tổng concurrency.

## 10. Startup và shutdown

Ở startup, server có thể mở socket trước khi mọi dependency sẵn sàng. Nếu health mặc định là SERVING, load balancer có thể gửi traffic quá sớm. Nên khởi tạo trạng thái NOT_SERVING, hoàn tất cấu hình, kết nối hoặc warm-up các dependency critical, rồi mới chuyển sang SERVING.

Ở shutdown:

- Chuyển health service về NOT_SERVING trước khi dừng nhận traffic.
- Cho load balancer thời gian loại instance khỏi pool nếu quy trình deployment yêu cầu.
- Gracefully stop gRPC server và cho call đang chạy hoàn tất trong giới hạn.
- Đóng monitor, scheduler và dependency client theo lifecycle.

Không để health service tiếp tục báo SERVING khi server đang shutdown có chủ đích.

## 11. Kiểm thử thay đổi health khi dependency lỗi

Kiểm thử cần xác minh cả trạng thái và hành vi định tuyến:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Dependency critical hoạt động | Actuator readiness UP, gRPC service SERVING |
| Dependency vượt ngưỡng lỗi | Readiness OUT_OF_SERVICE, service health NOT_SERVING |
| Một dependency của một service lỗi | Service khác vẫn giữ SERVING nếu độc lập |
| Dependency optional lỗi | Health vẫn phù hợp với khả năng phục vụ; detail/metric thể hiện degraded |
| Một request sai input | Không làm dependency health chuyển down |
| Circuit HALF_OPEN có probe thành công | Chưa phục hồi quá sớm; chờ đủ ngưỡng |
| Dependency phục hồi ổn định | Actuator và gRPC health trở lại UP/SERVING |
| Watch client đang kết nối | Nhận được thông báo khi trạng thái thay đổi |
| Application shutdown | Health chuyển NOT_SERVING trước khi server dừng |

Với Spring, kiểm tra endpoint readiness group bằng integration test. Với gRPC, dùng health client gọi Check và mở Watch để xác minh status được cập nhật. Dùng fake dependency hoặc circuit breaker test event để điều khiển lỗi, không cần làm hỏng database thật.

## 12. Quan sát và bảo mật health information

Theo dõi:

- Circuit breaker state và thời điểm chuyển trạng thái.
- Số lần lỗi liên tiếp, tỷ lệ lỗi và số probe phục hồi.
- Readiness status và gRPC SERVING/NOT_SERVING theo service.
- Thời gian từ dependency failure tới khi health được cập nhật.
- Số request bị từ chối hoặc chuyển hướng khi service không ready.
- Thời gian dependency phục hồi và số lần health flapping.

Health endpoint cần cung cấp đủ thông tin cho vận hành nhưng không tiết lộ connection string, hostname nội bộ, token, stack trace hoặc dữ liệu khách hàng. Giới hạn quyền truy cập endpoint chi tiết; với client bên ngoài, chỉ trả trạng thái tối thiểu cần thiết.

## 13. Ghi nhớ và tự kiểm tra

Khi dependency lỗi, cập nhật health dựa trên **mức độ quan trọng, trạng thái lỗi đã qua ngưỡng và phạm vi RPC bị ảnh hưởng**. Dùng Spring Actuator HealthIndicator cho readiness, gRPC HealthStatusManager cho Check/Watch, và circuit breaker hoặc monitor làm nguồn trạng thái. Giữ liveness độc lập với dependency bên ngoài, phục hồi qua HALF_OPEN có kiểm soát và cập nhật NOT_SERVING trước shutdown.

Tự kiểm tra:

1. Vì sao dependency outage thường nên ảnh hưởng readiness thay vì liveness?
2. Khi nào chỉ một gRPC service cần chuyển NOT_SERVING thay vì toàn bộ server?
3. Vì sao không nên gọi dependency blocking trực tiếp mỗi lần Actuator health endpoint được truy vấn?
4. Circuit breaker OPEN và HALF_OPEN được ánh xạ sang health như thế nào?
5. Vì sao cần ngưỡng phục hồi và cooldown để tránh health flapping?
6. Cần kiểm thử gì để chứng minh client Watch nhận được thay đổi trạng thái?

Health động được thiết kế đúng giúp Spring gRPC ngừng nhận traffic ở nơi thực sự không thể phục vụ, giữ các service độc lập tiếp tục hoạt động và tự đưa instance trở lại pool khi dependency phục hồi ổn định.
