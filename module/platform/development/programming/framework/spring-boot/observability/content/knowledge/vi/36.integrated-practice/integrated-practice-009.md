# Thiết lập health và readiness

Một dịch vụ Spring Boot có thể khởi động thành công nhưng chưa chắc đã sẵn sàng nhận request. Ứng dụng có thể đang nạp cache, khởi tạo kết nối, chạy migration hoặc chờ một thành phần bắt buộc. Ngược lại, một ứng dụng đã nhận request vẫn có thể gặp lỗi nội bộ và cần được khởi động lại. Nếu chỉ kiểm tra process còn sống hay không, nền tảng triển khai sẽ khó phân biệt hai tình huống này.

Spring Boot Actuator cung cấp health endpoint và các trạng thái availability để mô tả tình trạng ứng dụng. Khi chạy trên Kubernetes, liveness probe cho biết container có cần được khởi động lại hay không; readiness probe cho biết Pod có nên nhận traffic hay không; startup probe dành thời gian cho ứng dụng khởi động chậm. Thiết lập đúng ba loại kiểm tra này giúp điều phối traffic và phục hồi sự cố mà không tạo ra vòng lặp restart ngoài ý muốn.

Bài thực hành này xây dựng cấu hình health và readiness cho một dịch vụ Spring Boot có HTTP API, database và một dependency bên ngoài. Bạn sẽ bật health probes, tạo health group, cấu hình Kubernetes probes, kiểm thử trạng thái và liên kết kết quả với metrics, logs cùng distributed tracing.

## 1. Phân biệt liveness, readiness và startup

Ba loại probe trả lời ba câu hỏi khác nhau:

| Probe | Câu hỏi | Khi thất bại, Kubernetes làm gì? | Ví dụ |
|---|---|---|---|
| Liveness | Ứng dụng còn hoạt động và có thể tiếp tục tiến triển không? | Khởi động lại container sau khi đạt ngưỡng thất bại | Deadlock, event loop hoặc worker chính không còn tiến triển |
| Readiness | Pod đã sẵn sàng nhận request chưa? | Đánh dấu Pod không sẵn sàng và ngừng gửi traffic dịch vụ đến Pod đó | Đang warm up cache hoặc dependency bắt buộc chưa khả dụng |
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động ban đầu chưa? | Chưa chạy liveness/readiness cho đến khi startup probe thành công; thất bại quá ngưỡng sẽ khởi động lại container | Ứng dụng cần thời gian nạp dữ liệu hoặc khởi tạo lâu |

Liveness không nên phụ thuộc vào database, message broker hay dịch vụ bên ngoài. Nếu database gặp sự cố, tất cả Pod có thể cùng fail liveness và bị restart. Việc restart hàng loạt không sửa được database mà còn làm tăng tải khi các ứng dụng khởi động lại, tạo thành một vòng lặp phục hồi tệ hơn.

Readiness có thể xét dependency nếu dịch vụ thực sự không thể phục vụ request khi dependency đó ngừng hoạt động. Tuy nhiên, hãy cân nhắc chế độ degraded mode, cache hoặc khả năng retry trước khi đưa dependency vào readiness. Một hệ thống có thể vẫn phục vụ phần lớn request khi một tích hợp phụ trợ bị lỗi; trong trường hợp đó, đánh dấu toàn bộ Pod unready có thể làm giảm năng lực phục vụ không cần thiết.

Startup probe hữu ích khi thời gian khởi động có thể dài hoặc biến động. Nó giúp đặt ngưỡng khởi động riêng mà không phải nới liveness probe cho toàn bộ vòng đời container. Sau khi startup probe thành công, liveness và readiness mới bắt đầu kiểm tra theo cấu hình của chúng.

## 2. Bật health probes trong Spring Boot

Giả sử ứng dụng đã có Spring Boot Actuator và chạy HTTP trên cổng `8080`. Nếu dùng Maven, dependency thường có dạng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Trong `application.yaml`, bật probes và expose health endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: when-authorized
```

Khi `management.endpoint.health.probes.enabled` được bật, Spring Boot cung cấp hai health group dành cho liveness và readiness. Các endpoint group có thể được truy cập qua:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Với `management.endpoint.health.probes.add-additional-paths=true`, Spring Boot còn tạo hai đường dẫn ngắn trên cổng HTTP chính:

```text
GET /livez
GET /readyz
```

Các đường dẫn ngắn này rất hữu ích khi Kubernetes kiểm tra ứng dụng qua cổng phục vụ request. Nếu cấu hình management server chạy trên cổng riêng, hãy đặc biệt chú ý kiểm tra readiness và liveness trên cổng ứng dụng chính. Một management server vẫn phản hồi không chứng minh HTTP server phục vụ người dùng còn hoạt động.

`show-details: when-authorized` giới hạn thông tin chi tiết health cho người đã được cấp quyền. Probe của Kubernetes chỉ cần mã HTTP và trạng thái, không cần nhận thông tin kết nối database, tên host nội bộ hoặc thông tin nhạy cảm khác.

## 3. Xác định nội dung health group

Spring Boot cung cấp các availability state contributor:

- `livenessState` phản ánh trạng thái liveness của ứng dụng.
- `readinessState` phản ánh ứng dụng đang chấp nhận hay từ chối traffic.

Mặc định, liveness group được xây dựng quanh `livenessState`, readiness group quanh `readinessState`. Có thể khai báo tường minh và thêm health indicator cần thiết vào readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Trong ví dụ này, `db` là health indicator do Spring Boot auto-configuration tạo ra khi ứng dụng có cấu hình datasource và dependency tương ứng. Readiness chỉ chuyển sang trạng thái không sẵn sàng khi availability state từ chối traffic hoặc database health contributor báo lỗi.

Hãy chỉ thêm `db` nếu API thực sự không thể phục vụ request khi database không khả dụng. Nếu một số endpoint vẫn phục vụ được bằng cache hoặc dữ liệu cục bộ, cân nhắc thiết kế readiness theo khả năng phục vụ thực tế. Tránh đưa mọi dependency vào readiness theo thói quen. Mỗi lần probe có thể gọi health contributor; kiểm tra dependency phải nhanh, có timeout và không tạo tải lớn.

Không đưa `db`, broker hoặc remote API vào liveness group. Liveness nên phản ánh khả năng tiến triển của chính tiến trình ứng dụng. Khi dependency ngoài bị lỗi, ứng dụng cần có cơ hội tiếp tục chạy, ghi nhận tình trạng và phục hồi kết nối.

## 4. Viết custom HealthIndicator cho dependency quan trọng

Nếu cần kiểm tra một dependency không có health contributor mặc định, có thể triển khai `HealthIndicator`. Ví dụ dưới đây minh họa một dịch vụ inventory bên ngoài:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventory")
class InventoryHealthIndicator implements HealthIndicator {

    private final InventoryClient client;

    InventoryHealthIndicator(InventoryClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            // Client phải cấu hình connect/read timeout ngắn và có giới hạn.
            client.checkConnection();
            return Health.up().withDetail("dependency", "inventory").build();
        } catch (Exception ex) {
            // Không đưa token, URL nội bộ hoặc thông tin nhạy cảm vào detail.
            return Health.down().withDetail("dependency", "inventory").build();
        }
    }
}
```

`InventoryClient` là thành phần của ứng dụng, cần được thay bằng client thực tế. Phương thức kiểm tra phải có timeout rõ ràng; không để một health request chờ vô hạn khi dịch vụ bên ngoài không phản hồi. Nếu API có thể phục vụ request khi inventory tạm thời gián đoạn, đừng đưa `inventory` vào readiness.

Nếu inventory là dependency bắt buộc, thêm contributor vào readiness group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
```

ID contributor được đặt theo tên bean `inventory`. Có thể kiểm tra riêng contributor bằng `/actuator/health/inventory` nếu health endpoint và contributor được expose theo cấu hình phù hợp. Đối với production, chỉ cho phép người có quyền xem chi tiết health; probe của nền tảng nên gọi endpoint readiness tổng hợp.

Một health indicator nên kiểm tra khả năng phục vụ ở mức tối thiểu. Không chạy truy vấn nặng, quét toàn bộ dữ liệu, gọi nhiều API tuần tự hoặc thực hiện thao tác ghi trong mỗi lần probe. Nếu cần kiểm tra sâu, hãy cung cấp một diagnostic endpoint có quyền truy cập riêng và chạy theo lịch hoặc khi điều tra sự cố.

## 5. Cấu hình Kubernetes probes

Khi dùng các đường dẫn `/livez` và `/readyz` trên cổng ứng dụng, một phần cấu hình Deployment có thể như sau:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: observability-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: observability-demo
  template:
    metadata:
      labels:
        app: observability-demo
    spec:
      containers:
        - name: app
          image: example/observability-demo:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

Các giá trị thời gian trên chỉ là điểm bắt đầu để minh họa. Với cấu hình startup probe này, Kubernetes cho ứng dụng tối đa khoảng 300 giây kiểm tra startup trước khi coi container thất bại, tùy cách tính chu kỳ và timeout. Khi startup thành công, liveness và readiness mới được thực hiện. Hãy chọn ngưỡng theo thời gian khởi động thực tế và độ trễ của môi trường.

Readiness được kiểm tra thường xuyên hơn trong ví dụ vì mục tiêu của nó là điều phối traffic khi trạng thái phục vụ thay đổi. Liveness có thể có chu kỳ dài hơn để tránh restart do một lỗi thoáng qua. `failureThreshold` kết hợp với `periodSeconds` quyết định thời gian gần đúng trước khi Kubernetes hành động; `timeoutSeconds` giới hạn thời gian chờ cho mỗi lần kiểm tra.

Khi readiness thất bại, Pod vẫn chạy nhưng được đánh dấu không sẵn sàng và bị loại khỏi endpoint của Service cho đến khi probe thành công trở lại. Khi liveness thất bại đủ ngưỡng, kubelet khởi động lại container. Startup probe giúp ứng dụng có thời gian khởi tạo trước khi hai probe còn lại bắt đầu.

Nếu không dùng `add-additional-paths`, có thể cấu hình probe gọi `/actuator/health/liveness` và `/actuator/health/readiness`. Đảm bảo `management.server.port`, `management.server.base-path`, context path và port name trong Deployment khớp với endpoint thực tế.

## 6. Phối hợp readiness với graceful shutdown

Trong lúc triển khai phiên bản mới hoặc scale down, ứng dụng cần ngừng nhận request mới và hoàn tất request đang xử lý. Spring Boot hỗ trợ graceful shutdown cho web server:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Khi shutdown bắt đầu, Spring Boot chuyển readiness sang trạng thái từ chối traffic để nền tảng có thể ngừng định tuyến request mới đến instance. Web server sau đó chờ các request đang xử lý hoàn tất trong khoảng timeout được cấu hình. Hãy đồng bộ khoảng thời gian này với `terminationGracePeriodSeconds` của Pod và thời gian drain ở ingress/load balancer.

Nếu ứng dụng thực hiện warm-up bất đồng bộ sau khi Spring context đã sẵn sàng, trạng thái readiness mặc định có thể chuyển sang accepting traffic trước khi warm-up hoàn tất. Khi đó, có thể chủ động điều khiển `ReadinessState`:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
class StartupReadiness {

    private final ConfigurableApplicationContext context;

    StartupReadiness(ConfigurableApplicationContext context) {
        this.context = context;
    }

    void beginWarmup() {
        AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
    }

    void finishWarmup() {
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Gọi `beginWarmup()` trước khi chạy công việc warm-up và chỉ gọi `finishWarmup()` sau khi các điều kiện phục vụ đã sẵn sàng. Trong ứng dụng thực tế, hãy gắn hai lời gọi này với lifecycle hoặc workflow khởi tạo rõ ràng; tránh đặt readiness ở trạng thái refusing mà không có đường phục hồi.

Readiness state cũng hữu ích khi cần đưa một instance vào chế độ bảo trì. Hãy chuyển sang `REFUSING_TRAFFIC`, chờ traffic được drain, thực hiện thao tác bảo trì rồi chuyển lại `ACCEPTING_TRAFFIC` khi instance có thể phục vụ. Không sử dụng liveness để điều khiển bảo trì vì điều đó có thể gây restart không cần thiết.

## 7. Bảo vệ health endpoint

Probe của kubelet cần truy cập endpoint, nhưng các endpoint chẩn đoán chi tiết không nên công khai tùy tiện. Khi ứng dụng dùng Spring Security, hãy cho phép truy cập đúng các đường dẫn probe trong security chain hiện có, ví dụ `/livez` và `/readyz`, đồng thời giữ các endpoint Actuator khác theo chính sách xác thực. Nếu dùng đường dẫn `/actuator/health/...`, hãy cho phép đúng nhóm endpoint mà kubelet cần.

Một số nguyên tắc:

- Chỉ expose `health` và các endpoint quản trị thực sự cần thiết.
- Không expose `env`, `configprops`, `heapdump` hoặc toàn bộ endpoint Actuator ra mạng công cộng.
- Dùng `show-details: when-authorized` hoặc `never` ở production.
- Không đưa connection string, credential, token, tên host nhạy cảm hay exception message có dữ liệu người dùng vào health details.
- Giới hạn network access đến management endpoint bằng network policy, firewall hoặc mạng quản trị.
- Đảm bảo probe có thể truy cập endpoint sau khi bật Spring Security; nếu không, Kubernetes có thể nhận 401/403 và đánh dấu Pod thất bại.

Nếu management endpoint chạy trên cổng riêng, hãy đánh giá cổng đó có được kubelet truy cập hay không và probe có kiểm tra đúng web server chính không. Cấu hình additional paths trên cổng ứng dụng thường giúp tránh tình huống management server vẫn khỏe trong khi server phục vụ request đã lỗi.

## 8. Kiểm tra thủ công và kiểm thử tự động

Khởi động ứng dụng với Actuator và gọi các endpoint:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

Khi ứng dụng bình thường, endpoint trả về trạng thái `UP` và HTTP 200. Khi readiness chuyển sang `REFUSING_TRAFFIC`, readiness endpoint trả về trạng thái không sẵn sàng; các trạng thái `DOWN` hoặc `OUT_OF_SERVICE` mặc định được ánh xạ thành HTTP 503. Liveness vẫn nên tiếp tục trả về `UP` nếu tiến trình còn có thể tiến triển và dependency bên ngoài chỉ đang gặp sự cố.

Có thể kiểm thử trạng thái readiness trong test hoặc một workflow bảo trì bằng cách phát availability event:

```java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC
);
```

Sau khi trạng thái chuyển, gọi `/readyz` để xác minh HTTP status và nội dung phản hồi. Phát event `ReadinessState.ACCEPTING_TRAFFIC` để đưa ứng dụng trở lại trạng thái nhận traffic. Đừng dùng thao tác này để mô phỏng liveness failure trong môi trường đang phục vụ người dùng.

Một integration test có thể kiểm tra các endpoint trên cổng ngẫu nhiên:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.probes.add-additional-paths=true"
    }
)
class HealthProbeTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void livenessEndpointIsAvailable() {
        ResponseEntity<String> response = http.getForEntity("/livez", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void readinessEndpointIsAvailable() {
        ResponseEntity<String> response = http.getForEntity("/readyz", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }
}
```

Đây là ví dụ kiểm thử trạng thái bình thường; test project cần có các import, static assertion và test dependency phù hợp. Nên bổ sung test cho custom health indicator khi dependency phản hồi thành công, timeout và lỗi kết nối. Nếu readiness group có database, dùng database test hoặc Testcontainers để kiểm thử cả trạng thái dependency. Tránh để test tích hợp gửi health check đến hệ thống production.

## 9. Kết nối health với metrics, logs và traces

Health endpoint cho biết trạng thái tại thời điểm kiểm tra. Các tín hiệu observability giúp hiểu trạng thái đó thay đổi như thế nào và nguyên nhân nằm ở đâu.

**Metrics.** Theo dõi tỷ lệ probe thất bại, số lần restart, số Pod không sẵn sàng, thời gian startup và thời gian drain. Các số liệu Kubernetes thường đến từ kubelet, kube-state-metrics hoặc nền tảng container. Phía ứng dụng có thể theo dõi latency của request và các meter liên quan đến dependency. Khi tính SLI cho traffic người dùng, cân nhắc tách request probe khỏi request nghiệp vụ để các lần kiểm tra định kỳ không làm sai request rate hoặc latency của người dùng.

**Logs.** Khi readiness chuyển trạng thái, log nên ghi nguyên nhân ở mức có thể hành động: dependency nào không sẵn sàng, timeout bao lâu, trạng thái nào được công bố và instance nào bị ảnh hưởng. Không ghi lặp stack trace ở mức ERROR cho mỗi lần kubelet probe nếu lỗi đã được ghi nhận ở nơi khác. Tránh log secret hoặc chi tiết health nhạy cảm.

**Traces.** Nếu probe được instrument như HTTP request thông thường, chúng có thể xuất hiện trong `http.server.requests` và tracing backend. Có thể lọc hoặc nhận diện route `/livez`, `/readyz` khi xây dashboard và chính sách lấy mẫu. Không nên tạo span con hoặc gọi thêm dịch vụ từ health indicator chỉ để tạo trace; việc kiểm tra phải nhẹ và có giới hạn.

Khi điều tra một Pod liên tục mất readiness, hãy đối chiếu thời điểm probe thất bại với deploy, log ứng dụng, connection pool, latency database, lỗi DNS/network và trace của request nghiệp vụ. Nếu liveness vẫn tốt nhưng readiness thất bại, tiến trình có thể vẫn chạy nhưng chưa thể phục vụ; nếu cả liveness lẫn readiness thất bại, cần xác định lỗi nằm ở tiến trình, web server hay cấu hình probe.

## 10. Tình huống thực hành: database mất kết nối

Giả sử dịch vụ Spring Boot có ba replica. Database tạm thời không truy cập được trong hai phút. Bạn đã cấu hình:

- Liveness chỉ bao gồm `livenessState`.
- Readiness gồm `readinessState,db`.
- Kubernetes liveness gọi `/livez`, readiness gọi `/readyz`.

Khi database mất kết nối, health contributor `db` báo `DOWN`. Readiness group chuyển sang trạng thái không sẵn sàng, Kubernetes ngừng gửi traffic mới đến các Pod bị ảnh hưởng. Liveness vẫn `UP`, nên kubelet không restart toàn bộ container chỉ vì database tạm thời gián đoạn.

Khi database phục hồi và health contributor trả về `UP`, readiness group có thể trở lại `UP`; Kubernetes đưa Pod trở lại endpoint của Service. Trong thời gian đó, nhóm vận hành kiểm tra log kết nối, pool exhaustion, database latency và cảnh báo từ metrics backend.

Nếu ứng dụng có cache và vẫn phục vụ được một phần request khi database mất kết nối, cấu hình readiness có thể không nên bao gồm `db`. Thay vào đó, readiness phản ánh khả năng phục vụ thực tế, còn health detail và metrics vẫn giúp quan sát database đang lỗi. Quyết định này cần dựa trên hợp đồng API và hành vi degraded mode đã được thiết kế, không chỉ dựa trên việc có datasource trong ứng dụng.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Kubernetes báo probe 404 | Chưa bật probes, chưa bật additional paths hoặc sai context path | Kiểm tra cấu hình Actuator và gọi endpoint từ trong Pod |
| Probe nhận 401/403 | Spring Security chặn kubelet | Cho phép đúng đường dẫn probe trong security chain và giới hạn network access |
| Management health UP nhưng ứng dụng không nhận request | Management server chạy cổng riêng và probe không kiểm tra cổng ứng dụng | Dùng additional paths trên main port hoặc probe trực tiếp cổng ứng dụng |
| Tất cả Pod restart khi database lỗi | Database được đưa vào liveness group | Chỉ dùng liveness state của ứng dụng; chuyển dependency check sang readiness nếu phù hợp |
| Pod luôn unready dù API vẫn phục vụ được | Readiness bao gồm dependency tùy chọn hoặc indicator quá nhạy | Điều chỉnh readiness theo khả năng phục vụ thực tế và kiểm tra timeout |
| Pod unready quá sớm khi khởi động | Thiếu startup probe hoặc readiness phụ thuộc warm-up chưa hoàn tất | Thêm startup probe và điều khiển readiness trong giai đoạn warm-up |
| Probe timeout làm tăng tải | Health indicator gọi API chậm hoặc thực hiện truy vấn nặng | Đặt timeout ngắn, giảm công việc trong indicator và tránh gọi nhiều dependency tuần tự |
| Rollout làm mất request đang xử lý | Shutdown không graceful hoặc thời gian drain quá ngắn | Bật graceful shutdown và đồng bộ termination grace period với timeout xử lý |
| Dashboard request rate tăng do probe | Probe được tính như HTTP request bình thường | Nhận diện route probe và loại khỏi SLI nghiệp vụ khi phù hợp |

## 12. Checklist triển khai

- Đã thêm Spring Boot Actuator và expose health endpoint cần thiết.
- Đã bật `management.endpoint.health.probes.enabled`.
- Đã cấu hình `/livez` và `/readyz` trên cổng ứng dụng nếu nền tảng cần kiểm tra main port.
- Liveness chỉ phản ánh sức khỏe tiến trình, không phụ thuộc dịch vụ bên ngoài.
- Readiness phản ánh khả năng phục vụ request và chỉ gồm dependency thực sự bắt buộc.
- Custom health indicator có timeout, xử lý lỗi và không trả thông tin nhạy cảm.
- Startup probe phù hợp với thời gian khởi động thực tế.
- Security cho phép kubelet gọi đúng probe endpoint nhưng vẫn bảo vệ Actuator chi tiết.
- Graceful shutdown và thời gian drain được đồng bộ với Kubernetes.
- Metrics, logs và traces có thể phân biệt probe với request nghiệp vụ.
- Đã kiểm thử trạng thái UP, DOWN, readiness refusal, startup chậm và dependency timeout.

Khi liveness, readiness và startup được cấu hình theo đúng vai trò, nền tảng có thể restart tiến trình bị lỗi, ngừng gửi traffic đến instance chưa sẵn sàng và dành đủ thời gian cho ứng dụng khởi động. Kết hợp health endpoint với metrics, logs và traces giúp đội vận hành thấy được cả trạng thái hiện tại lẫn nguyên nhân của thay đổi đó.
