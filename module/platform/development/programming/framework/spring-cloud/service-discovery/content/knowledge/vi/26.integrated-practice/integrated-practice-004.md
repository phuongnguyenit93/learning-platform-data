# So sánh tắt ứng dụng êm với buộc dừng tiến trình

Trong microservice, cách một provider dừng hoạt động ảnh hưởng trực tiếp tới service discovery. Khi ứng dụng được tắt êm, nó có cơ hội thông báo ngừng nhận traffic, deregister khỏi registry, hoàn tất request đang xử lý và đóng tài nguyên theo thứ tự. Khi tiến trình bị buộc dừng, shutdown hook có thể không chạy; registry chỉ nhận ra instance biến mất sau một lần health check thất bại, lease hết hạn hoặc session hết hạn.

Hai cách dừng này tạo ra hành vi khác nhau ở provider, Eureka/Consul/ZooKeeper, discovery cache của consumer và request đang bay. Bài thực hành này so sánh hai kịch bản, cấu hình Spring Boot graceful shutdown, kiểm tra luồng kết thúc trong Docker/Kubernetes và đo thời gian instance ngừng được chọn.

## 1. Mục tiêu và bối cảnh thực hành

Giả sử có một hệ thống gồm:

- Eureka Server hoặc Consul làm registry.
- Hai replica của service `inventory-service`.
- Một consumer `order-service` gọi `inventory-service` qua service ID.
- Một endpoint mất khoảng 10 giây để xử lý request nhằm quan sát request đang chạy.

Ta sẽ dừng một replica trong hai cách:

1. **Tắt êm (graceful shutdown):** gửi tín hiệu kết thúc có thể xử lý, để ứng dụng ngừng nhận request mới, rút khỏi discovery và hoàn tất request đang chạy trong giới hạn thời gian.
2. **Buộc dừng (forced termination):** kết thúc tiến trình ngay, không chờ Spring đóng context hoặc hoàn thành request.

Mục tiêu không chỉ là thấy process đã dừng. Cần xác minh:

- Consumer ngừng chọn instance ở thời điểm nào.
- Request đang xử lý có hoàn thành hay bị ngắt.
- Registry xóa hoặc đánh dấu instance như thế nào.
- Replica còn lại có tiếp tục phục vụ được không.
- Instance mới có thể đăng ký lại sau khi khởi động hay không.

## 2. Hai cách dừng khác nhau ở đâu?

| Tiêu chí | Tắt êm | Buộc dừng |
|---|---|---|
| Tín hiệu điển hình | SIGTERM hoặc lệnh stop có timeout | SIGKILL, kill -9 hoặc force kill |
| Shutdown hook của JVM | Có cơ hội chạy | Không chạy |
| Spring ApplicationContext | Có cơ hội đóng theo lifecycle | Không có cơ hội đóng bình thường |
| Request đang xử lý | Có thể được drain trong thời hạn | Có thể bị ngắt ngay |
| Deregistration | Có cơ hội thực hiện qua lifecycle/client | Không thể dựa vào shutdown hook |
| Tài nguyên | Có thể flush, đóng pool và file | OS thu hồi khi process chết; dữ liệu chưa flush có thể mất |
| Registry cleanup | Có thể chủ động; vẫn cần propagation | Thường phụ thuộc lease, health check hoặc session |
| Khả năng dự đoán | Cao hơn nếu timeout được cấu hình đúng | Phụ thuộc thời điểm và cơ chế phát hiện lỗi |

SIGTERM không tự bảo đảm graceful shutdown. Ứng dụng phải xử lý tín hiệu và có quy trình đóng phù hợp; nếu thời gian chờ vượt giới hạn của Docker, Kubernetes hoặc systemd, tiến trình cuối cùng vẫn có thể bị SIGKILL.

Ngược lại, SIGKILL kết thúc process mà không gọi shutdown hook. Không có đoạn code `@PreDestroy`, `DisposableBean.destroy()` hay lifecycle callback nào có thể chạy sau khi tiến trình đã bị SIGKILL.

## 3. Luồng tắt êm của một provider

Một quy trình shutdown có kiểm soát thường gồm các bước:

1. Nhận yêu cầu dừng và chuyển trạng thái readiness sang không nhận traffic mới.
2. Báo cho hệ thống định tuyến và consumer rằng instance sắp rời khỏi service.
3. Deregister khỏi registry hoặc để registry client thực hiện trong lifecycle shutdown.
4. Ngừng nhận request mới ở web server.
5. Chờ request đang xử lý hoàn thành trong giới hạn timeout.
6. Đóng connection pool, scheduler, message listener và các tài nguyên còn lại.
7. Kết thúc JVM.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Spring Boot app
    participant R as Service registry
    participant C as Consumer
    O->>A: SIGTERM / stop request
    A->>A: Readiness = REFUSING_TRAFFIC
    A->>R: Deregister hoặc cập nhật trạng thái
    R-->>C: Registry thay đổi
    C->>R: Refresh / nhận thay đổi
    A->>A: Ngừng nhận request mới
    A->>A: Drain request đang chạy
    A->>A: Đóng bean và tài nguyên
    A-->>O: Process exit
~~~

Thứ tự chi tiết giữa deregistration, readiness và web server shutdown phụ thuộc registry client, web server và phiên bản Spring Boot/Spring Cloud. Điều quan trọng là không đóng listener hoặc connection mà request đang chạy còn cần dùng trước khi drain hoàn tất. Cần kiểm thử lifecycle thực tế của ứng dụng thay vì giả định chỉ bật một property là toàn bộ chuỗi đã đúng.

### Readiness khác liveness

- **Liveness** trả lời process có cần được khởi động lại hay không.
- **Readiness** trả lời instance có nên nhận traffic mới hay không.

Khi shutdown bắt đầu, instance có thể còn sống và xử lý nốt request, nhưng readiness phải chuyển sang không sẵn sàng. Không dùng liveness để biểu diễn trạng thái đang drain; nếu liveness thất bại, Kubernetes có thể restart container trong lúc nó đang shutdown.

## 4. Cấu hình graceful shutdown trong Spring Boot

Với Spring Boot có hỗ trợ graceful shutdown cho embedded web server, có thể cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ý nghĩa:

- `server.shutdown: graceful` yêu cầu embedded web server ngừng nhận kết nối/request mới theo cơ chế graceful của server.
- `spring.lifecycle.timeout-per-shutdown-phase` đặt thời gian tối đa chờ cho mỗi lifecycle phase trong quá trình đóng context.
- Health probes cho phép nền tảng kiểm tra readiness/liveness qua Actuator nếu các endpoint được cấu hình và expose đúng.

Timeout 30 giây chỉ là ví dụ. Chọn theo thời gian xử lý request dài nhất được phép, thời gian drain, tác vụ đóng tài nguyên và grace period của orchestrator. Giá trị quá ngắn có thể làm request bị cắt; giá trị quá dài có thể khiến rollout hoặc scale-down kéo dài.

Các web server và phiên bản Spring Boot có thể có khác biệt về cách xử lý connection đang mở, HTTP/2, streaming response và request async. Kiểm tra tài liệu đúng phiên bản và đo bằng một request thực tế đang chạy.

### Kiểm tra readiness endpoint

Với Actuator probes, endpoint readiness thường có dạng:

~~~text
/actuator/health/readiness
~~~

Trong Kubernetes, cấu hình readiness probe trỏ tới endpoint này. Khi ứng dụng bắt đầu shutdown, Spring Boot có thể chuyển readiness state sang `REFUSING_TRAFFIC` trong lifecycle của nó. Nếu cần chuyển trạng thái sớm hơn để có thời gian propagation tới load balancer/registry, ứng dụng có thể triển khai một bước pre-drain riêng và phát hành trạng thái readiness trước khi đóng context.

Không expose toàn bộ Actuator endpoints ra mạng công cộng. Chỉ mở endpoint cần thiết trong network quản trị và bảo vệ bằng chính sách phù hợp.

## 5. Deregistration khỏi service registry

Dừng web server và deregister là hai việc khác nhau:

- Web server ngừng nhận request trực tiếp.
- Registry ngừng cung cấp instance cho consumer mới.

Với Spring Cloud, registry client thường tham gia lifecycle của application context. Khi context đóng bình thường, implementation có thể deregister hoặc đóng registration/session tương ứng. Hành vi cụ thể phụ thuộc provider và phiên bản.

Nếu ứng dụng tự đăng ký bằng `ServiceRegistry`, cần chủ động gọi thao tác deregister đúng lifecycle. Không gọi deregister thủ công trùng với cơ chế tự động nếu chưa hiểu semantics của provider; thao tác lặp hoặc sai registration có thể gây trạng thái không mong muốn.

### Eureka

Eureka Client thường đăng ký instance, gửi renewal định kỳ và có thể gửi cancellation khi client đóng bình thường. Khi process bị SIGKILL, cancellation không được gửi; server chỉ có thể phát hiện instance không còn renew sau lease expiration và eviction.

Nếu Eureka bật self-preservation, eviction có thể bị hạn chế khi renewal thấp bất thường. Vì vậy, một process bị kill có thể còn trong registry lâu hơn lease dự kiến. Consumer có thể tiếp tục nhận instance stale cho tới khi registry và cache hội tụ.

### Consul

Với Spring Cloud Consul, client có thể deregister service khi ứng dụng đóng theo lifecycle của integration. Nếu agent health check không còn passing, catalog có thể đánh dấu instance critical; chính sách deregister critical service và thời gian giữ lại phụ thuộc cấu hình Consul agent.

Khi process bị kill, Consul agent có thể phát hiện qua health check hoặc TTL check. Đây không phải cùng thời điểm với process exit. Cần kiểm tra cả trạng thái check ở agent và catalog server.

### ZooKeeper

Registration có thể được biểu diễn bằng ephemeral znode gắn với session. Khi client đóng session bình thường, ephemeral node được xóa. Khi process bị kill hoặc mất mạng, node thường chỉ biến mất khi ZooKeeper xác định session đã hết hạn.

Do đó, force kill không làm ephemeral node biến mất ngay lập tức. Thời gian session timeout và khả năng reconnect ảnh hưởng tới thời điểm consumer ngừng nhìn thấy registration.

## 6. Force kill làm lộ ra vấn đề gì?

Khi process bị dừng đột ngột:

- JVM không chạy shutdown hook.
- Spring không gọi các callback đóng context.
- Registry client không có cơ hội gửi deregistration/cancel.
- Request đang xử lý có thể bị reset hoặc mất response.
- Transaction chưa commit hoặc dữ liệu chưa flush có thể ở trạng thái không mong muốn.
- Consumer vẫn có thể chọn instance cũ từ registry/cache.
- Registry chỉ cập nhật sau health check, lease expiration hoặc session expiration.

Một request đã được gửi tới instance trước khi force kill có thể thất bại dù consumer đã có danh sách instance mới. Discovery không thể đưa request đang chạy trở lại một process đã chết. Retry chỉ an toàn khi operation có tính idempotent hoặc có cơ chế chống xử lý trùng.

## 7. Thực hành với Docker

Giả sử container tên `inventory-service` đang chạy và được đăng ký vào Eureka hoặc Consul.

### Tắt êm

~~~bash
docker stop --time 40 inventory-service
~~~

Docker gửi stop signal (thường là SIGTERM, trừ khi image cấu hình `STOPSIGNAL` khác), chờ tối đa 40 giây rồi mới force kill nếu process chưa thoát.

### Buộc dừng

~~~bash
docker kill --signal KILL inventory-service
~~~

Lệnh này gửi SIGKILL ngay. Container không có cơ hội thực hiện graceful shutdown.

### Quan sát

~~~bash
docker inspect inventory-service
docker logs --timestamps inventory-service
~~~

Ghi lại thời điểm stop/kill, log shutdown, exit code và trạng thái container. Sau đó kiểm tra instance trong registry và gọi consumer liên tục để xác định:

- Lúc nào registry xóa hoặc đánh dấu instance.
- Lúc nào consumer ngừng chọn endpoint đó.
- Có request nào bị reset trong quá trình dừng hay không.

Chỉ chạy lệnh trên container của môi trường thực hành. Không dùng tên container chung chung hoặc lệnh stop hàng loạt trong môi trường dùng chung.

### PID 1 và shell wrapper

Nếu container khởi chạy ứng dụng qua shell script, shell phải chuyển tiếp signal tới Java process. Dùng `exec` để Java trở thành process thay thế shell:

~~~dockerfile
ENTRYPOINT ["sh", "-c", "exec java -jar /app/application.jar"]
~~~

Nếu shell giữ vai trò PID 1 và không chuyển tiếp signal, Docker có thể gửi SIGTERM tới shell nhưng JVM không nhận được đúng cách. Khi đó lệnh `docker stop` có thể hết timeout rồi mới SIGKILL, khiến một cấu hình tưởng là graceful thực tế lại thành force stop.

## 8. Thực hành với Kubernetes

Khi Pod bị xóa hoặc thay thế, Kubernetes thực hiện termination theo một chuỗi. Ở mức khái quát:

1. Pod được đánh dấu terminating.
2. EndpointSlice và các thành phần định tuyến cập nhật trạng thái endpoint; propagation có độ trễ.
3. `preStop` hook được chạy nếu có.
4. Kubelet gửi termination signal (thường là SIGTERM) tới container.
5. Ứng dụng có thời gian đóng trong `terminationGracePeriodSeconds`.
6. Khi hết grace period, tiến trình còn sống có thể bị SIGKILL.

Grace period bắt đầu trước khi `preStop` chạy. Thời gian hook sử dụng cũng nằm trong tổng ngân sách termination; không cộng thời gian hook bên ngoài `terminationGracePeriodSeconds`.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory
          image: inventory-service:latest
          ports:
            - name: http
              containerPort: 8080
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Ví dụ dùng 5 giây cho preStop, 30 giây cho Spring lifecycle shutdown và phần còn lại làm margin. Đây chỉ là cách minh họa ngân sách; `sleep` không tự làm readiness fail và không deregister khỏi Eureka/Consul. Trong production, thay bằng một hook hoặc endpoint pre-drain có chủ đích nếu cần thời gian cho routing và registry propagation.

Khi triển khai thực tế:

- Đặt `terminationGracePeriodSeconds` lớn hơn tổng thời gian preStop, drain và shutdown cần thiết, có thêm margin.
- Bảo đảm readiness phản ánh trạng thái sắp dừng.
- Dùng `maxUnavailable` và `maxSurge` phù hợp để rollout không làm mất toàn bộ replica.
- Không để liveness probe restart ứng dụng chỉ vì readiness đang REFUSING_TRAFFIC.
- Kiểm tra EndpointSlice, registry và request path; chúng có thể cập nhật ở thời điểm khác nhau.

### Ngân sách thời gian ví dụ

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Propagation/preStop | 5 giây |
| Drain và Spring lifecycle shutdown | 30 giây |
| Margin | 10 giây |
| Tổng grace period | 45 giây |

Không phải mọi bước chạy tuần tự hoàn toàn. Đo thời gian thực tế để chọn grace period; request streaming hoặc async có thể cần chính sách riêng.

## 9. Tự kiểm soát thứ tự shutdown

Nếu ứng dụng cần chủ động chuyển readiness trước khi Spring bắt đầu đóng web server, có thể phát hành trạng thái `REFUSING_TRAFFIC` từ một bước pre-drain có kiểm soát.

Ví dụ component đơn giản để chuyển trạng thái:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class ReadinessControl {

    private final ConfigurableApplicationContext context;

    public ReadinessControl(ConfigurableApplicationContext context) {
        this.context = context;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
        );
    }
}
~~~

Đây là building block, chưa phải toàn bộ shutdown coordinator. Cần gọi `refuseNewTraffic()` từ cơ chế pre-drain phù hợp với orchestrator hoặc lifecycle của ứng dụng, rồi chờ thời gian propagation trước khi bắt đầu đóng server.

Không gọi `context.close()` ngay bên trong một callback chưa kiểm soát nếu còn request đang chạy. Cũng không tự deregister trước khi readiness/routing có cơ hội cập nhật nếu kiến trúc cần khoảng drain. Thứ tự tối ưu phụ thuộc việc consumer gọi qua Kubernetes Service, Eureka, Consul hay nhiều lớp cùng lúc.

Với đăng ký thủ công, `ServiceRegistry.deregister(registration)` có thể được gọi từ lifecycle component. Tuy nhiên, nếu Eureka/Consul starter đã tự quản lý registration, hãy kiểm tra lifecycle hiện có trước khi thêm deregister thủ công để tránh gọi hai lần hoặc dùng sai registration.

## 10. Bài kiểm tra so sánh hai cách dừng

Chuẩn bị:

- Hai replica `inventory-service`.
- Một consumer gọi liên tục bằng service ID.
- Endpoint test xử lý chậm 10 giây và trả về instance ID.
- Log hoặc metric ghi nhận request bắt đầu/kết thúc.
- Registry dashboard/API để quan sát registration.

Chạy cùng một kịch bản hai lần, chỉ thay cách dừng provider.

### Kịch bản A — graceful shutdown

1. Xác nhận hai instance đều healthy và consumer gọi được cả hai.
2. Gửi một request mất 10 giây tới instance A.
3. Trong lúc request đang chạy, gửi SIGTERM hoặc chạy `docker stop` với timeout đủ dài.
4. Ghi thời điểm readiness chuyển sang refusing traffic.
5. Ghi thời điểm instance bị deregister hoặc không còn được registry trả về.
6. Ghi thời điểm request đang chạy hoàn tất.
7. Xác nhận consumer chỉ chọn instance B cho request mới.

### Kịch bản B — forced termination

1. Khôi phục hai instance và xác nhận baseline.
2. Gửi request mất 10 giây tới instance A.
3. Trong lúc request đang chạy, gửi SIGKILL hoặc force kill container.
4. Ghi request bị reset hoặc timeout ở thời điểm nào.
5. Theo dõi health check, lease hoặc session cho tới khi registry cập nhật.
6. Xác nhận consumer ngừng chọn A và chuyển sang B.
7. Ghi thời gian stale endpoint còn xuất hiện trong registry/cache.

### Bảng ghi kết quả

| Chỉ số | Graceful | Force kill |
|---|---:|---:|
| Thời gian từ tín hiệu dừng đến process exit | Đo thực tế | Đo thực tế |
| Request đang chạy hoàn tất | Có/Không | Có/Không |
| Deregistration chủ động | Có/Không | Không kỳ vọng |
| Thời gian registry bỏ instance | Đo thực tế | Đo thực tế |
| Thời gian consumer ngừng chọn instance | Đo thực tế | Đo thực tế |
| Số request lỗi trong cửa sổ dừng | Đếm | Đếm |
| Instance khỏe bị ảnh hưởng | Đếm | Đếm |

Không điền kết quả giả định vào bảng. Chạy thí nghiệm và lấy timestamp từ log, trace, registry và consumer.

## 11. Cách diễn giải kết quả

Một kết quả graceful tốt thường có:

- Readiness chuyển sang không nhận traffic mới.
- Request mới được chuyển tới replica còn khỏe.
- Request đang chạy hoàn tất trong timeout.
- Registry được deregister hoặc health state được cập nhật nhanh.
- Consumer cache hội tụ và không còn chọn instance đã dừng.

Một kết quả force kill thường có:

- Không có shutdown hook hoặc deregistration chủ động.
- Request đang chạy có thể thất bại.
- Registry vẫn giữ instance cho tới khi health/lease/session phát hiện.
- Consumer có thể gọi endpoint cũ trong stale window.

Nếu graceful shutdown vẫn để consumer gọi instance đã dừng trong thời gian dài, kiểm tra:

1. Readiness có thực sự chuyển sang REFUSING_TRAFFIC không?
2. Registry client có deregister khi context đóng không?
3. Consumer dùng registry hay cache riêng nào?
4. LoadBalancer có cache instance list không?
5. Có proxy hoặc gateway giữ DNS/endpoint cache không?
6. Shutdown timeout có đủ cho drain không?

Nếu force kill không làm request lỗi, có thể request đã được phục vụ bởi replica khác hoặc test không bảo đảm request đang chạy trên instance bị kill. Xác nhận instance ID của request trước khi kết luận.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `docker stop` luôn chờ hết timeout | Java không nhận SIGTERM, shell không chuyển tiếp signal hoặc shutdown bị kẹt | Kiểm tra PID 1, exec, shutdown log và lifecycle phase |
| Pod bị SIGKILL dù đã cấu hình graceful | Grace period ngắn hơn tổng thời gian preStop và drain | Đo từng giai đoạn và tăng ngân sách phù hợp |
| Readiness vẫn UP khi shutdown bắt đầu | Probe không phản ánh trạng thái refusing traffic | Kiểm tra Actuator readiness và pre-drain |
| Registry còn instance sau graceful shutdown | Registry lifecycle không deregister hoặc thao tác bị lỗi | Kiểm tra client shutdown log và REST/catalog state |
| Registry còn instance sau force kill | Lease, health check hoặc session chưa hết | Kiểm tra semantics của registry và timeout |
| Request đang chạy bị mất khi graceful | Web server đóng ngay, timeout quá ngắn hoặc async task chưa hoàn tất | Kiểm tra server shutdown mode, phase timeout và request duration |
| Consumer vẫn chọn instance sau deregister | Fetch interval/cache hoặc propagation delay | Kiểm tra DiscoveryClient và LoadBalancer selection |
| Kubernetes rollout gây downtime | maxUnavailable, readiness hoặc replica count không phù hợp | Kiểm tra Deployment strategy và EndpointSlice |
| Shutdown hook không chạy trong container | PID 1/shell wrapper hoặc force kill | Kiểm tra entrypoint và stop signal |

## 13. Nguyên tắc thiết kế và vận hành

- Dùng graceful shutdown cho rollout, scale-down và dừng có kiểm soát.
- Xem SIGTERM là tín hiệu bắt đầu lifecycle shutdown, không phải bằng chứng ứng dụng đã drain xong.
- Dùng SIGKILL chỉ khi cần force terminate hoặc sau khi grace period hết.
- Chuyển readiness sang refusing traffic trước khi kết thúc nhận request mới.
- Deregister khỏi registry theo lifecycle phù hợp với implementation.
- Chờ request đang chạy trong giới hạn thời gian đã định.
- Đặt Spring shutdown timeout nhỏ hơn grace period của orchestrator và chừa margin.
- Bảo đảm container PID 1 chuyển tiếp signal tới JVM.
- Với Kubernetes, tính cả thời gian preStop trong terminationGracePeriodSeconds.
- Đo stale window ở registry và consumer, không chỉ nhìn trạng thái process.
- Thiết kế retry an toàn với idempotency; discovery không cứu được request đã bị ngắt.
- Kiểm thử cả graceful và force termination trong staging trước khi chọn timeout production.

Tắt ứng dụng êm tạo cơ hội cho provider rút khỏi traffic và hoàn tất công việc đang chạy; buộc dừng kết thúc tiến trình trước khi các bước lifecycle đó diễn ra. Registry và consumer có cơ chế phát hiện riêng nên thời điểm process exit, registration removal và request recovery không trùng nhau. So sánh bằng một thí nghiệm có request đang chạy, ghi timestamp ở provider/registry/consumer và xác minh replica còn lại giúp chọn đúng shutdown timeout cũng như chính sách phục hồi cho hệ thống Spring Cloud Service Discovery.
