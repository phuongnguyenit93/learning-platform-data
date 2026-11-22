# Readiness khác với liveness

## 1. Hai tín hiệu trả lời hai câu hỏi khác nhau

Trong **SPRING_GRPC**, một ứng dụng Spring có thể mở gRPC server và phục vụ nhiều RPC được định nghĩa bằng Protocol Buffers. Khi triển khai nhiều instance, nền tảng cần quyết định khi nào gửi traffic đến instance và khi nào phải khởi động lại tiến trình. Hai quyết định đó cần hai tín hiệu riêng:

- **Readiness** trả lời: instance có nên nhận request mới vào lúc này không?
- **Liveness** trả lời: tiến trình còn hoạt động đúng mức để tiếp tục chạy, hay cần được khởi động lại?

Readiness thường thay đổi trong suốt vòng đời ứng dụng: đang khởi tạo, đã sẵn sàng, tạm ngừng nhận traffic, rồi sẵn sàng trở lại. Liveness phản ánh tình trạng tiến trình; một dependency bên ngoài chập chờn thường không phải lý do để restart ứng dụng.

~~~text
Ứng dụng đang khởi động
  liveness:   CORRECT (tiến trình hoạt động)
  readiness:  REFUSING_TRAFFIC (chưa nhận request)

Ứng dụng đã sẵn sàng
  liveness:   CORRECT
  readiness:  ACCEPTING_TRAFFIC

Database bắt buộc tạm thời mất kết nối
  liveness:   CORRECT
  readiness:  REFUSING_TRAFFIC

Tiến trình bị deadlock hoặc không thể tiến triển
  liveness:   BROKEN
  readiness:  REFUSING_TRAFFIC
~~~

Nếu dùng cùng một health check cho cả hai quyết định, một lỗi dependency có thể khiến Kubernetes restart container liên tục. Trong khi đó, điều cần làm chỉ là tạm ngừng gửi traffic và chờ dependency phục hồi.

## 2. Readiness điều khiển traffic admission

Khi readiness là `ACCEPTING_TRAFFIC`, instance được xem là đủ điều kiện nhận request mới. Khi readiness chuyển `REFUSING_TRAFFIC`, hệ thống điều phối nên ngừng đưa request mới đến instance đó.

Readiness có thể chuyển sang false trong các tình huống:

- Ứng dụng chưa hoàn tất khởi tạo cấu hình, cache hoặc dữ liệu cần thiết.
- Dependency bắt buộc đối với service đang không thể sử dụng.
- Instance đang drain để triển khai phiên bản mới hoặc shutdown.
- Service chủ động từ chối traffic vì đang quá tải theo chính sách admission control.

Readiness không có nghĩa mọi request đều chắc chắn thành công. Một instance `READY` vẫn có thể trả `NOT_FOUND`, `INVALID_ARGUMENT`, `PERMISSION_DENIED` hoặc gặp lỗi riêng của một request. Readiness chỉ là tín hiệu tổng quát về khả năng nhận công việc mới.

Trong gRPC, readiness có thể được công bố qua `grpc.health.v1.Health` để probe, client health checking hoặc proxy sử dụng. Với service cụ thể, status thường dùng tên đầy đủ như `orders.v1.OrdersService`.

## 3. Liveness quyết định có nên restart tiến trình

Liveness là tín hiệu cho biết tiến trình còn hoạt động và có thể tiếp tục vận hành. Nếu liveness thất bại liên tiếp theo ngưỡng cấu hình, Kubernetes có thể restart container.

Liveness nên phát hiện tình trạng nội bộ nghiêm trọng, ví dụ:

- Process bị deadlock và không thể xử lý công việc.
- Một thành phần thiết yếu bên trong tiến trình bị kẹt không thể phục hồi.
- Event loop hoặc worker quan trọng không còn tiến triển.
- Ứng dụng rơi vào trạng thái lỗi không thể tự khôi phục.

Không nên đưa mọi dependency bên ngoài vào liveness. Nếu database tạm mất kết nối, restart tất cả replica cùng lúc có thể làm tăng tải kết nối khi database vừa phục hồi. Nếu DNS hoặc message broker chập chờn, restart hàng loạt có thể biến sự cố ngắn thành outage rộng hơn.

Liveness cũng không nên là một bài kiểm tra sâu, chậm và phụ thuộc nhiều hệ thống. Probe cần phản hồi nhanh, ổn định và phản ánh tình trạng của chính tiến trình.

## 4. Phân biệt thêm startup probe và connectivity

Ngoài readiness và liveness, cần hiểu hai khái niệm liên quan:

| Tín hiệu | Ý nghĩa | Tác động |
|---|---|---|
| Startup probe | Ứng dụng đã hoàn tất giai đoạn khởi động hay chưa? | Tạm hoãn liveness/readiness probe cho đến khi startup thành công |
| Readiness | Instance có nhận traffic mới không? | Thêm hoặc loại instance khỏi traffic pool |
| Liveness | Tiến trình có cần restart không? | Có thể restart container |
| gRPC connectivity `READY` | Channel/subchannel đã thiết lập transport để gửi RPC | Chỉ phản ánh kết nối, không chứng minh nghiệp vụ sẵn sàng |

Một gRPC subchannel ở trạng thái `READY` chỉ cho biết kết nối transport đã sẵn sàng. Server có thể đang chạy nhưng `OrdersService` chưa sẵn sàng vì database hoặc dữ liệu khởi tạo chưa hoàn tất.

Startup probe hữu ích khi ứng dụng có thời gian khởi động dài. Nếu chỉ dùng liveness với ngưỡng quá ngắn, Kubernetes có thể restart container trước khi ứng dụng hoàn tất startup.

## 5. Vòng đời readiness và liveness

Một vòng đời điển hình:

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Khởi tạo xong
    Ready --> NotReady: Dependency bắt buộc lỗi / drain
    NotReady --> Ready: Dependency phục hồi / kết thúc drain
    Ready --> Restarting: Liveness thất bại
    NotReady --> Restarting: Liveness thất bại
    Restarting --> Starting
~~~

Liveness và readiness có thể cùng thay đổi, nhưng không nên gắn cứng với nhau. Ví dụ database lỗi có thể làm readiness false trong khi liveness vẫn đúng. Nếu tiến trình bị deadlock, liveness false; readiness cũng nên ngừng nhận traffic vì instance không còn phục vụ được.

## 6. Kubernetes sử dụng hai probe theo hai cách khác nhau

Kubernetes xử lý kết quả probe khác nhau:

- Readiness probe thất bại: Pod được đánh dấu không ready và thường bị loại khỏi endpoint traffic của Service. Container vẫn chạy.
- Liveness probe thất bại liên tiếp vượt ngưỡng: kubelet restart container theo restart policy.
- Startup probe chưa thành công: liveness và readiness probe chưa được thực hiện; điều này cho ứng dụng thời gian khởi động.

Ví dụ dùng Spring Boot Actuator cho readiness/liveness qua HTTP:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health

---
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8081
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8081
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Đây là hai phần cấu hình minh họa cho Spring Boot và Kubernetes; trong manifest thật, `readinessProbe` và `livenessProbe` nằm dưới `spec.containers[].`. Cần bảo đảm management port và endpoint được expose trong mạng probe có thể truy cập.

Nếu dùng native gRPC probe, có thể kiểm tra health service trên cổng gRPC:

~~~yaml
readinessProbe:
  grpc:
    port: 9090
    service: orders.v1.OrdersService
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
~~~

Native gRPC probe cần health service được đăng ký và trả trạng thái theo đúng service name. Probe gRPC tích hợp của Kubernetes không cung cấp đầy đủ tùy chọn TLS/authentication như một gRPC client ứng dụng. Nếu endpoint chỉ chấp nhận mTLS hoặc yêu cầu credential riêng, hãy dùng một probe endpoint được kiểm soát hoặc cơ chế probe phù hợp thay vì mở rộng quyền truy cập API nghiệp vụ.

## 7. Spring Boot biểu diễn hai trạng thái này

Spring Boot cung cấp hai nhóm trạng thái availability:

- `LivenessState.CORRECT` và `LivenessState.BROKEN`.
- `ReadinessState.ACCEPTING_TRAFFIC` và `ReadinessState.REFUSING_TRAFFIC`.

Khi Actuator health probes được bật, các endpoint `/actuator/health/liveness` và `/actuator/health/readiness` phản ánh hai nhóm tương ứng. Spring Boot cũng phát các availability event để ứng dụng chủ động thay đổi trạng thái:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public final class TrafficAdmission {
    private final ApplicationContext context;

    public TrafficAdmission(ApplicationContext context) {
        this.context = context;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Đối với liveness, ứng dụng có thể công bố `LivenessState.BROKEN` khi phát hiện tình trạng nội bộ không thể phục hồi:

~~~java
AvailabilityChangeEvent.publish(
        context,
        LivenessState.BROKEN);
~~~

Chỉ công bố `BROKEN` khi restart thực sự là hành động phù hợp. Một lỗi database hoặc API downstream thông thường nên được xử lý qua readiness/dependency policy, không tự động biến thành liveness failure.

## 8. Không đưa dependency ngoài vào liveness một cách máy móc

Spring Boot health indicator có thể kiểm tra database, disk, broker hoặc hệ thống bên ngoài. Việc thêm indicator vào readiness có thể hữu ích nếu dependency đó bắt buộc để phục vụ traffic. Thêm cùng indicator vào liveness thường tạo rủi ro restart loop.

Ví dụ quyết định:

| Sự cố | Readiness | Liveness | Lý do |
|---|---|---|---|
| Database chính ngừng hoạt động và mọi RPC cần database | Có thể `REFUSING_TRAFFIC` | Vẫn `CORRECT` | Chờ database phục hồi, không restart hàng loạt |
| Cache tùy chọn lỗi nhưng có fallback | Có thể vẫn accepting | `CORRECT` | Service vẫn có thể phục vụ |
| Ứng dụng đang warm up | `REFUSING_TRAFFIC` | `CORRECT` | Tiến trình đang khởi tạo bình thường |
| Deadlock trong thành phần thiết yếu | `REFUSING_TRAFFIC` | `BROKEN` | Tiến trình không còn tiến triển |
| Đang graceful shutdown | `REFUSING_TRAFFIC` | Vẫn `CORRECT` trong thời gian drain | Ngừng nhận việc mới, hoàn tất việc đang chạy |

Spring Boot mặc định tách health group liveness và readiness. Nếu thêm custom indicator, hãy chỉ đưa vào group mà nó thực sự phục vụ. Không giả định mọi health indicator đều tự động được dùng cho cả hai endpoint.

## 9. Ánh xạ readiness Spring sang gRPC HealthStatusManager

Một ứng dụng có thể cần cả Actuator probe và gRPC health service. Khi đó, có thể dùng cùng nguồn readiness để cập nhật gRPC health status. Ví dụ:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class GrpcReadinessBridge {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health;

    public GrpcReadinessBridge(HealthStatusManager health) {
        this.health = health;
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        ServingStatus status =
                event.getState() == ReadinessState.ACCEPTING_TRAFFIC
                        ? ServingStatus.SERVING
                        : ServingStatus.NOT_SERVING;
        health.setStatus(SERVICE, status);
    }
}
~~~

`HealthStatusManager` phải là cùng instance được đăng ký vào gRPC server. Component bridge chỉ đồng bộ readiness của service; nó không biến mọi liveness event thành readiness event. Khi liveness chuyển `BROKEN`, ứng dụng cũng cần ngừng nhận traffic trước khi tiến trình bị restart, nhưng hai trạng thái vẫn có ý nghĩa riêng.

Nếu server cung cấp nhiều service, có thể ánh xạ readiness theo từng service thay vì đặt tất cả status giống nhau. Ví dụ `InventoryService` phụ thuộc broker trong khi `OrdersService` vẫn phục vụ được bằng database.

## 10. Graceful shutdown bắt đầu bằng readiness false

Khi deploy hoặc shutdown có chủ đích, mục tiêu đầu tiên là ngừng gửi request mới đến instance:

1. Chuyển readiness sang `REFUSING_TRAFFIC`.
2. Cập nhật gRPC health thành `NOT_SERVING` và/hoặc deregister khỏi service discovery.
3. Chờ endpoint update lan đến load balancer/client trong khoảng thời gian có giới hạn.
4. Drain RPC đang chạy trong grace period.
5. Đóng gRPC server, executor và dependency.

Trong thời gian drain, liveness vẫn có thể là `CORRECT`: tiến trình đang hoạt động bình thường để hoàn tất RPC hiện tại. Không chuyển liveness thành `BROKEN` chỉ để ép Kubernetes loại Pod khỏi traffic; đó là nhiệm vụ của readiness.

Với server streaming dài, cần quy định stream kết thúc khi shutdown và cách client reconnect/resume bằng cursor hoặc sequence. Readiness false không tự chuyển stream đang chạy sang backend khác.

## 11. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng cùng một check phụ thuộc database cho readiness và liveness | Database lỗi làm container restart liên tục | Để readiness phản ánh khả năng phục vụ; liveness chỉ phản ánh tiến trình |
| Liveness probe quá nhạy | Restart trong lúc ứng dụng warm up hoặc GC pause ngắn | Dùng startup probe, timeout và failure threshold phù hợp |
| Readiness luôn trả healthy ngay khi port mở | Traffic đến trước khi service khởi tạo xong | Chuyển accepting traffic sau readiness thực tế |
| Readiness thất bại nhưng restart container | Tạo churn dù tiến trình vẫn khỏe | Chỉ liveness failure mới kích hoạt restart |
| Gộp mọi dependency vào readiness | Một dependency tùy chọn loại toàn bộ replica | Xác định dependency bắt buộc theo service |
| Dùng gRPC connectivity `READY` làm readiness | Transport tốt nhưng nghiệp vụ chưa sẵn sàng | Kiểm tra health status ở tầng service |
| Dừng server trước khi readiness update lan truyền | Request mới có thể bị reset | Chuyển readiness false, chờ propagation rồi drain |
| Không phục hồi readiness sau khi dependency khỏe lại | Instance bị loại khỏi traffic pool lâu dài | Theo dõi dependency và công bố lại `ACCEPTING_TRAFFIC` |

## 12. Kiểm thử readiness và liveness

Kiểm thử nên xác minh hai quyết định độc lập:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Ứng dụng đang khởi động | Readiness từ chối traffic; startup probe cho đủ thời gian |
| Khởi tạo hoàn tất | Readiness chuyển accepting traffic |
| Database bắt buộc tạm lỗi | Readiness từ chối traffic; liveness vẫn correct |
| Database phục hồi | Readiness trở lại accepting traffic |
| Dependency tùy chọn lỗi | Readiness vẫn accepting nếu service còn đáp ứng hợp đồng |
| Thành phần nội bộ deadlock | Liveness chuyển broken; nền tảng restart theo ngưỡng |
| Graceful shutdown | Readiness false trước; liveness vẫn correct trong drain |
| gRPC health service | Service key phản ánh readiness, không chỉ transport `READY` |
| Nhiều gRPC service | Một service không khỏe không làm service độc lập bị loại nếu policy cho phép |
| Probe timeout hoặc endpoint lỗi | Hành vi failure threshold và recovery đúng cấu hình |

Test đơn vị có thể kiểm tra event và mapping trạng thái. Integration test trong Kubernetes hoặc môi trường tương đương mới chứng minh readiness thật sự loại Pod khỏi traffic và liveness thật sự kích hoạt restart.

## 13. Quan sát và chẩn đoán

Theo dõi riêng:

- Trạng thái readiness và liveness theo Pod/instance.
- Số lần chuyển `ACCEPTING_TRAFFIC` ↔ `REFUSING_TRAFFIC`.
- Số lần liveness probe thất bại và container restart.
- Thời gian startup, thời gian từ readiness false đến khi endpoint bị loại.
- Thời gian drain và số RPC/stream còn mở.
- Dependency gây readiness false và thời gian phục hồi.
- Chênh lệch giữa gRPC health, Actuator health và Kubernetes Pod condition.

Nếu Pod liên tục restart khi database chập chờn, kiểm tra database indicator có bị đưa vào liveness hay không. Nếu Pod không restart dù ứng dụng bị deadlock, kiểm tra liveness probe có thực sự phát hiện tình trạng nội bộ đó và có bị cấu hình quá dễ thành công không.

**Ghi nhớ:** Readiness điều khiển việc instance có nhận traffic mới hay không; liveness quyết định tiến trình có cần restart hay không. Dependency ngoài thường tác động đến readiness, còn liveness nên phản ánh khả năng tiến triển của chính tiến trình. Trong Spring Boot dùng `ReadinessState` và `LivenessState`; trong Kubernetes dùng readiness/liveness probe riêng, thêm startup probe khi cần. Với gRPC, ánh xạ readiness sang `HealthStatusManager` để client/proxy loại service khỏi lựa chọn mới, rồi drain RPC hiện tại trước khi shutdown.
