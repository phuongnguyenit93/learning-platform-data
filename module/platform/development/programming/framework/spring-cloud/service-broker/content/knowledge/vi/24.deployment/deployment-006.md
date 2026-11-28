# Readiness, liveness và khả năng kết nối kho dữ liệu

Một service broker có thể khởi động thành công nhưng chưa sẵn sàng nhận request OSB API. Ví dụ, Spring đã tạo web server nhưng connection pool chưa kết nối được database, migration chưa hoàn tất hoặc worker chưa thể ghi operation vào kho dữ liệu. Nếu platform gửi request provision vào thời điểm này, broker có thể nhận yêu cầu nhưng mất khả năng lưu trạng thái cần thiết để xử lý tiếp.

Khi triển khai **SPRING_CLOUD_SERVICE_BROKER**, cần phân biệt ba trạng thái: ứng dụng đã khởi động, ứng dụng còn sống và ứng dụng có thể nhận traffic. Spring Boot Actuator cung cấp health endpoint và các nhóm probe; Kubernetes sử dụng startup, readiness và liveness probe để quản lý container; Cloud Foundry có cơ chế health check riêng. Broker còn cần đánh giá khả năng kết nối database và các dependency thiết yếu mà không biến sự cố tạm thời của provider thành vòng lặp restart.

Bài học này trình bày ý nghĩa của readiness, liveness và startup; cách thiết kế health check cho database; cách cấu hình Spring Boot Actuator; triển khai Kubernetes probe; lựa chọn health check khi chạy trên Cloud Foundry; quản lý connection pool, graceful shutdown, quan sát và kiểm thử các tình huống lỗi.

## 1. Ba câu hỏi khác nhau về sức khỏe ứng dụng

Health check không nên trả lời một câu hỏi chung chung như "ứng dụng có khỏe không?". Khi triển khai, platform cần biết chính xác nó nên giữ container, gửi traffic hay khởi động lại.

| Trạng thái | Câu hỏi | Ý nghĩa với service broker |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất khởi tạo chưa? | Web server, cấu hình, dependency nội bộ và migration cần thiết đã sẵn sàng |
| Liveness | Process còn hoạt động và có thể tiếp tục chạy không? | JVM không bị deadlock hoặc mắc kẹt không thể phục hồi |
| Readiness | Instance có thể nhận và xử lý request mới an toàn không? | Broker có thể xác thực, đọc/ghi trạng thái, lưu operation và trả response OSB đúng contract |

Ba trạng thái có quan hệ nhưng không thay thế nhau:

- Ứng dụng có thể chưa startup xong nhưng process vẫn sống.
- Ứng dụng có thể live nhưng chưa ready vì database đang mất kết nối.
- Ứng dụng có thể ready trong thời điểm hiện tại nhưng sau đó mất database hoặc queue.
- Process có thể không còn live dù database vẫn hoạt động bình thường.

Với broker, readiness đặc biệt quan trọng vì một request được nhận thường phải được xác thực, kiểm tra service instance, ghi operation hoặc outbox và điều phối tới provider. Nếu broker không thể thực hiện các bước bắt buộc đó, nhận traffic mới có thể tạo ra trạng thái không nhất quán.

## 2. Liveness không phải phép kiểm tra mọi dependency

Liveness trả lời liệu process có thể tiếp tục hoạt động hay cần được khởi động lại. Nó nên kiểm tra những điều mà việc restart process có khả năng khắc phục.

Ví dụ, có thể dùng liveness để phát hiện:

- JVM bị deadlock hoặc application thread không còn phản hồi.
- Vòng lặp xử lý nội bộ khiến ứng dụng không thể phục hồi.
- Một trạng thái runtime nghiêm trọng được ứng dụng chủ động đánh dấu BROKEN.
- Web server hoặc thành phần nền tảng không còn phục vụ được health endpoint.

Không nên đưa database, message broker, cloud provider hoặc secret manager dùng chung vào liveness mặc định. Nếu database bị outage, mọi replica broker có thể cùng trả liveness DOWN. Kubernetes sẽ restart hàng loạt pod, làm tăng tải khởi động, tạo thêm connection storm và không khắc phục được database outage.

Ví dụ:

~~~text
Database ngừng hoạt động
        |
        v
Liveness kiểm tra database và trả DOWN
        |
        v
Platform restart broker pod
        |
        v
Pod mới lại không kết nối được database
        |
        v
Restart lặp lại, làm tăng tải và khó phục hồi
~~~

Nếu ứng dụng thật sự bị kẹt và không thể phục hồi bằng retry hoặc reconnect, liveness có thể được chuyển sang BROKEN. Quyết định này nên dựa trên trạng thái nội bộ của process, không dựa đơn thuần vào một dependency bên ngoài.

## 3. Readiness phản ánh khả năng nhận request OSB API

Readiness trả lời liệu một instance có thể nhận traffic mới và hoàn tất phần việc broker chịu trách nhiệm hay không.

Với service broker, những điều kiện có thể cần cho readiness gồm:

- Spring application context đã khởi tạo.
- Web server đang phục vụ request.
- Database broker có thể thực hiện thao tác cần thiết.
- Schema migration bắt buộc đã hoàn tất.
- Broker có thể ghi operation và outbox nếu request cần xử lý bất đồng bộ.
- Các cấu hình bắt buộc và identity nội bộ đã sẵn sàng.
- Hệ thống chưa bước vào giai đoạn shutdown hoặc từ chối traffic.

Không phải mọi dependency đều phải có mặt trong readiness. Hãy xác định dependency nào cần thiết để nhận và ghi nhận request một cách an toàn.

Ví dụ, nếu broker lưu operation và outbox trong PostgreSQL trước khi trả 202 Accepted, khả năng ghi database là điều kiện readiness quan trọng. Nếu provider cloud tạm thời không phản hồi nhưng broker vẫn có thể lưu operation, trả 202 và để worker retry, provider có thể không cần làm readiness DOWN.

## 4. Phân loại dependency theo vai trò

Một broker thường kết nối nhiều hệ thống. Không nên đưa tất cả chúng vào cùng một health group.

| Dependency | Vai trò | Cách xem xét trong readiness |
|---|---|---|
| Database broker | Lưu instance, binding, operation và outbox | Thường là dependency thiết yếu nếu request path cần đọc/ghi |
| Message broker/queue | Nhận công việc bất đồng bộ | Thiết yếu nếu broker chỉ có thể nhận request khi enqueue được; nếu outbox relay phục hồi được, đánh giá theo thiết kế |
| Secret manager | Đọc provider/binding credentials | Tùy request path; có thể chỉ cần cho một số thao tác |
| Cloud/Kubernetes provider | Tạo và quản lý tài nguyên | Thường xử lý trong worker; outage có thể khiến operation chờ/retry mà broker vẫn ready |
| Identity provider | Xác thực workload hoặc lấy token | Tùy credential cache và khả năng cấp token |
| Metrics/tracing backend | Gửi telemetry | Thường không nên làm readiness DOWN |
| SMTP/notification | Gửi thông báo phụ trợ | Không nên chặn OSB request nếu có thể retry riêng |

Có thể chia dependency thành ba nhóm:

1. **Critical for request acceptance:** thiếu dependency này khiến broker không thể nhận và ghi nhận request đúng contract.
2. **Critical for a specific operation:** chỉ một loại operation cần dependency đó; lỗi nên được biểu diễn trong operation thay vì đánh dấu toàn bộ pod unready nếu thiết kế cho phép.
3. **Best-effort/observability:** lỗi không ngăn broker thực hiện nghiệp vụ cốt lõi.

Quy tắc này giúp tránh tình trạng một provider account lỗi khiến toàn bộ broker bị loại khỏi service endpoints, dù broker vẫn có thể phục vụ catalog, polling operation hoặc các tenant khác.

## 5. Spring Boot Actuator health endpoint

Spring Boot Actuator cung cấp health endpoint để platform hoặc hệ thống monitoring truy vấn trạng thái ứng dụng. Khi thêm dependency Actuator, broker có thể expose health endpoint qua HTTP.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Endpoint tổng quát thường là:

~~~http
GET /actuator/health
~~~

Khi bật health probes, Spring Boot cung cấp các nhóm:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Có thể cấu hình explicit để tránh phụ thuộc vào việc môi trường runtime có được Spring Boot tự nhận diện là Kubernetes hay không. Ví dụ:

~~~yaml
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
      show-details: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Trong ví dụ:

- **livenessState** phản ánh trạng thái liveness của Spring.
- **readinessState** phản ánh trạng thái readiness của Spring.
- **db** là health contributor của database nếu ứng dụng có cấu hình phù hợp, chẳng hạn DataSource và Actuator JDBC.
- **add-additional-paths** yêu cầu Spring Boot tạo đường dẫn probe bổ sung trên main server port, thường là /livez và /readyz.

Tên health contributor phụ thuộc dependency và cấu hình ứng dụng. Nếu dùng R2DBC hoặc custom health indicator, hãy kiểm tra contributor thực tế và khai báo đúng tên trong group.

Cấu hình cần được đối chiếu với phiên bản Spring Boot đang dùng. Một số property hoặc hành vi probe có thể khác giữa các phiên bản.

## 6. Vì sao nên expose probe trên main server port?

Một số ứng dụng cấu hình management server trên port riêng, ví dụ application server ở 8080 và Actuator ở 8081. Nếu Kubernetes chỉ kiểm tra health endpoint ở management port, có thể xảy ra trường hợp management server vẫn trả UP trong khi main web server không thể nhận request OSB.

Khi dùng additional probe paths, health endpoint có thể được phục vụ trên main application port:

~~~text
Main server port 8080
  /v2/catalog
  /v2/service_instances/...
  /livez
  /readyz

Management server port 8081 (nếu cấu hình riêng)
  /actuator/health
  /actuator/info
~~~

Điều này giúp probe kiểm tra cùng network listener mà platform dùng để gửi traffic. Vẫn cần cấu hình firewall và management endpoint exposure phù hợp; không mở toàn bộ Actuator endpoint ra Internet chỉ để Kubernetes đọc health.

Nếu không dùng additional paths, hãy bảo đảm probe trỏ tới đúng port và health endpoint phản ánh cả khả năng phục vụ của main application server.

## 7. Health status và HTTP status code

Actuator health endpoint thường chuyển trạng thái health thành HTTP status:

| Health status | HTTP thường gặp | Ý nghĩa |
|---|---:|---|
| UP | 200 | Thành phần hoạt động |
| DOWN | 503 | Thành phần không đáp ứng |
| OUT_OF_SERVICE | 503 | Thành phần tạm thời không phục vụ |
| UNKNOWN | Thường 200 theo mapping mặc định | Trạng thái chưa xác định, cần cấu hình phù hợp nếu dùng trong probe |

Status mapping có thể được tùy chỉnh. Đối với readiness/liveness, nên bảo đảm mọi trạng thái cần loại instance khỏi traffic đều trả mã HTTP mà platform hiểu là probe failure.

Không dựa vào text trong JSON response nếu platform probe chỉ kiểm tra HTTP status. Ngược lại, khi viết test, hãy xác minh cả status code và health body để phát hiện mapping sai.

Health endpoint không nên trả thông tin chi tiết nhạy cảm cho caller không tin cậy. Có thể đặt show-details thành never hoặc when-authorized và chỉ cho phép network nội bộ truy cập probe.

## 8. Kiểm tra kết nối database đúng cách

Với service broker, database thường giữ trạng thái quan trọng: service instance, binding, provider resource mapping, operation, idempotency key và outbox. Một health check hữu ích cần xác minh khả năng thực hiện một thao tác nhẹ qua đúng connection path của ứng dụng.

Các lựa chọn:

- Mở hoặc lấy một connection từ pool.
- Thực hiện truy vấn nhẹ như SELECT 1.
- Áp dụng timeout ngắn và hữu hạn.
- Kiểm tra lỗi kết nối, authentication, pool exhaustion hoặc timeout.
- Không thực hiện query nặng, scan bảng lớn hoặc ghi dữ liệu nghiệp vụ trong health check.

Nếu chỉ kiểm tra TCP port database đang mở, broker chưa biết rằng credentials hợp lệ, connection pool hoạt động hay truy vấn có thể thực hiện được. Một truy vấn nhẹ qua cùng DataSource/DatabaseClient thường phản ánh tốt hơn khả năng truy cập thực tế.

### JDBC

Với Spring JDBC, Spring Boot Actuator có thể tự cấu hình health indicator cho DataSource khi các dependency phù hợp được thêm vào. Có thể đưa contributor database vào readiness group.

Nếu cần custom check, ví dụ:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class BrokerDatabaseHealthIndicator implements HealthIndicator {

    private final JdbcTemplate jdbcTemplate;

    public BrokerDatabaseHealthIndicator(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Health health() {
        try {
            jdbcTemplate.queryForObject("SELECT 1", Integer.class);
            return Health.up()
                    .withDetail("database", "reachable")
                    .build();
        } catch (DataAccessException exception) {
            return Health.down()
                    .withDetail("database", "unavailable")
                    .build();
        }
    }
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế, nên bắt nhóm exception phù hợp thay vì nuốt mọi lỗi không phân loại; không đưa exception message, SQL, hostname hoặc credentials vào health response công khai. Cần đặt query timeout và bảo đảm health check không bị treo khi pool cạn.

### R2DBC

Với ứng dụng dùng R2DBC, có thể triển khai ReactiveHealthIndicator để truy vấn non-blocking:

~~~java
import java.time.Duration;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class BrokerR2dbcHealthIndicator
        implements ReactiveHealthIndicator {

    private final DatabaseClient databaseClient;

    public BrokerR2dbcHealthIndicator(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Mono<Health> health() {
        return databaseClient.sql("SELECT 1")
                .map((row, metadata) -> row.get(0))
                .first()
                .then(Mono.fromSupplier(() -> Health.up().build()))
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(error ->
                        Mono.just(Health.down().build()));
    }
}
~~~

Ví dụ dùng truy vấn tối giản và timeout hai giây. Kiểu dữ liệu của cột trả về và API mapping cần được đối chiếu với driver R2DBC đang dùng. Nếu database không phản hồi, indicator trả DOWN mà không chờ vô hạn.

Không gọi block() trong reactive health indicator. Không tạo subscription phụ chỉ để chạy truy vấn; hãy trả publisher để Actuator điều phối lifecycle.

## 9. Connection pool cũng là một phần của readiness

Database có thể reachable nhưng broker vẫn không lấy được connection vì pool đã cạn. Nguyên nhân có thể là:

- Connection bị giữ quá lâu.
- Transaction không được đóng.
- Query chậm hoặc lock contention.
- Pool size quá nhỏ so với concurrency.
- Worker tạo quá nhiều operation đồng thời.
- Database giới hạn max connections thấp hơn tổng số connection từ các replica.
- Connection idle bị database hoặc network đóng nhưng pool chưa phát hiện.

Health check lấy một connection từ pool có thể phát hiện pool exhaustion, nhưng cần thận trọng: nếu probe chạy quá thường xuyên, chính probe có thể làm tăng tải khi hệ thống đã quá tải.

Với HikariCP, có thể quan sát active, idle, pending và timeout metric. Không nhất thiết đưa mọi metric vào readiness. Readiness nên dựa vào khả năng thực hiện request cần thiết, còn metric dùng để cảnh báo xu hướng cạn pool.

Ví dụ cấu hình pool:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 2000
      validation-timeout: 1000
      idle-timeout: 600000
~~~

Các giá trị trên chỉ là ví dụ. Cần tính theo số replica, concurrency, transaction duration và giới hạn connection của database. Tổng connection tối đa của toàn bộ broker pods không được vượt quá năng lực database sau khi trừ phần dành cho worker, migration, admin và các ứng dụng khác.

## 10. Không đưa mọi provider vào readiness

Service broker thường điều phối request tới cloud provider hoặc Kubernetes API. Provider có thể bị throttling, timeout hoặc outage trong khi broker vẫn có thể nhận request và lưu operation bền vững.

Ví dụ:

~~~text
Platform gửi provision request
        |
        v
Broker xác thực và lưu instance + operation + outbox
        |
        v
Broker trả 202 Accepted
        |
        v
Worker gọi provider
        |
        +--> Provider UP: tiếp tục provision
        |
        +--> Provider DOWN: retry/reconcile operation
~~~

Trong kiến trúc này, provider outage không nhất thiết làm broker unready. Platform vẫn có thể nhận request và theo dõi operation; worker sẽ xử lý khi provider phục hồi.

Ngược lại, nếu broker không có operation store hoặc queue/outbox và request cần gọi provider đồng bộ ngay, provider có thể là dependency trực tiếp của request path. Hãy quyết định theo kiến trúc thật, không áp dụng một danh sách dependency cố định cho mọi broker.

Không nên gọi mọi provider API từ mỗi readiness probe. Việc đó có thể tạo nhiều request lặp, vượt quota, làm chậm probe và khiến outage ở một account ảnh hưởng tới toàn bộ broker.

## 11. Tách liveness và readiness health groups

Cấu hình điển hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

**Liveness** chỉ chứa trạng thái runtime của ứng dụng. **Readiness** chứa trạng thái readiness cùng database contributor nếu database là dependency thiết yếu cho request acceptance.

Không đưa db vào liveness chỉ để platform restart app khi database lỗi. Không đưa metrics exporter hoặc tracing backend vào readiness nếu broker có thể phục vụ nghiệp vụ khi các hệ thống đó tạm thời gián đoạn.

Nếu broker có nhiều loại endpoint hoặc workload, có thể tạo health group bổ sung, nhưng cần giữ rõ mục đích từng group. Ví dụ health group dành cho worker không nhất thiết là readiness của HTTP API.

## 12. Kubernetes startupProbe, readinessProbe và livenessProbe

Kubernetes cung cấp ba loại probe:

- **startupProbe:** cho phép ứng dụng có thời gian khởi động; khi chưa thành công, liveness và readiness probe chưa được thực hiện.
- **readinessProbe:** khi thất bại, pod bị loại khỏi các endpoint nhận traffic phù hợp của Service.
- **livenessProbe:** khi thất bại đủ số lần theo cấu hình, kubelet có thể restart container.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: service-broker
  template:
    metadata:
      labels:
        app: service-broker
    spec:
      containers:
        - name: broker
          image: example/service-broker:1.0.0
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
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Trong ví dụ, startup probe cho phép khoảng thời gian khởi động dài hơn. Khi startup probe thành công, Kubernetes mới bắt đầu đánh giá readiness và liveness. Các giá trị cần điều chỉnh theo thời gian khởi động thực tế, thời gian probe và SLA.

Nếu dùng path mặc định Actuator thay vì additional path, có thể trỏ tới /actuator/health/liveness và /actuator/health/readiness trên đúng port. Đảm bảo path và port trong manifest khớp với cấu hình ứng dụng.

### Ý nghĩa khi probe thất bại

| Probe | Hành động platform | Dùng khi |
|---|---|---|
| Startup | Tiếp tục chờ trong giới hạn cấu hình; nếu vượt ngưỡng thì restart container | Khởi tạo quá lâu hoặc không thể hoàn tất |
| Readiness | Không gửi traffic mới tới pod chưa sẵn sàng | Database hoặc điều kiện nhận request chưa đáp ứng |
| Liveness | Restart container sau số lần thất bại quy định | Process không còn khả năng tự phục hồi |

Readiness failure không đồng nghĩa pod bị restart. Liveness failure có thể gây restart. Vì vậy, một health check sai có thể biến database outage thành restart storm.

## 13. Spring AvailabilityState trong startup và shutdown

Spring Boot có khái niệm **AvailabilityState** để biểu diễn readiness và liveness trong lifecycle ứng dụng. Có thể dùng event để đánh dấu ứng dụng từ chối traffic khi bắt đầu shutdown hoặc khi một trạng thái nội bộ không thể phục hồi.

Ví dụ chuyển readiness sang trạng thái từ chối traffic:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityManager {

    private final ApplicationContext applicationContext;

    public BrokerAvailabilityManager(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Ví dụ này minh họa API availability. Trong thực tế, không tự chuyển ACCEPTING_TRAFFIC ngay khi constructor chạy. Chỉ đánh dấu ready sau khi các bước startup bắt buộc hoàn tất.

Trong shutdown:

1. Chuyển readiness sang REFUSING_TRAFFIC.
2. Ngừng nhận request mới qua load balancer/platform.
3. Chờ request đang xử lý trong giới hạn termination grace period.
4. Ngừng claim operation mới.
5. Hoàn tất hoặc checkpoint worker đang chạy.
6. Đóng connection pool và resource theo lifecycle.

Nếu ứng dụng dùng async worker, readiness HTTP và worker readiness có thể cần được quản lý riêng. Không đánh dấu toàn bộ pod unready chỉ vì worker tạm dừng nếu HTTP broker vẫn có thể phục vụ catalog và polling; ngược lại, không nhận provision mới nếu không có đường lưu công việc bền vững.

## 14. Health check trên Cloud Foundry

Cloud Foundry hỗ trợ health check cho app instance với các kiểu như process, port hoặc HTTP, tùy phiên bản platform và CLI. HTTP health check yêu cầu app trả response thành công tại endpoint đã cấu hình.

Ví dụ manifest:

~~~yaml
applications:
  - name: service-broker
    memory: 1G
    instances: 2
    health-check-type: http
    health-check-http-endpoint: /actuator/health/liveness
~~~

Nếu chọn HTTP health check để Cloud Foundry quyết định restart app instance, endpoint liveness thường phù hợp hơn vì không phụ thuộc database dùng chung. Readiness có thể được theo dõi riêng hoặc tích hợp với cơ chế routing nếu platform/version hỗ trợ. Cần kiểm tra phiên bản Cloud Foundry và loại health check thực tế; không giả định mọi môi trường có semantics tách biệt giống Kubernetes startup/readiness/liveness.

Nếu HTTP health check failure dẫn tới restart app instance, tránh gắn nó với dependency dùng chung có thể outage dài như database. Khi database tạm thời không khả dụng, broker có thể cần ngừng nhận traffic qua cơ chế routing/maintenance hoặc readiness phù hợp, nhưng restart liên tục không khắc phục được database.

Có thể chọn process hoặc port health check nếu mục tiêu chỉ là xác nhận process/listener còn hoạt động, đồng thời dùng monitoring riêng để quan sát readiness và database. Quyết định cần phù hợp với khả năng của platform và cách broker lưu operation.

## 15. Readiness khi database đang migration

Database migration là một phần quan trọng của startup. Nếu broker khởi động trước khi schema tương thích, request có thể truy cập bảng chưa tồn tại hoặc cột chưa được thêm.

Một trình tự triển khai an toàn:

1. Kiểm tra kết nối database.
2. Chạy migration theo chiến lược đã chọn.
3. Xác minh schema version tương thích với phiên bản broker.
4. Khởi tạo repository, queue/outbox publisher và worker.
5. Chuyển readiness sang ACCEPTING_TRAFFIC.
6. Bắt đầu nhận request OSB API.

Với rolling deployment nhiều replica, không nên để tất cả pod đồng thời chạy migration không được thiết kế cho concurrency. Có thể dùng migration job riêng hoặc cơ chế lock migration của công cụ như Flyway/Liquibase. Schema change nên theo hướng expand-and-contract để phiên bản cũ và mới có thể cùng chạy trong giai đoạn rollout.

Nếu migration thất bại, broker không nên báo ready. Tuy nhiên, process vẫn có thể live để platform tiếp tục theo dõi hoặc thu thập log.

## 16. Connection recovery và database outage

Readiness không thay thế cơ chế reconnect. Broker cần phục hồi khi database tạm thời mất kết nối.

Các tình huống thường gặp:

- Database failover làm connection cũ mất hiệu lực.
- DNS hoặc network route thay đổi.
- TLS certificate được rotate.
- Connection pool giữ connection stale.
- Database từ chối connection do quá tải.
- Password hoặc secret version được rotate.
- Database khởi động lại sau maintenance.

Cần cấu hình pool để phát hiện connection lỗi, giới hạn thời gian chờ lấy connection và tránh giữ connection quá lâu. Khi credential thay đổi, ứng dụng cần có cơ chế refresh pool hoặc restart có kiểm soát tùy driver và secret provider.

Khi database outage:

- Readiness có thể chuyển DOWN nếu broker không thể nhận và ghi nhận request an toàn.
- Liveness vẫn UP nếu process còn hoạt động.
- Worker nên dừng claim công việc mới nếu không thể ghi checkpoint.
- Operation đang chạy cần giữ trạng thái chưa kết luận nếu kết quả provider không rõ.
- Khi database phục hồi, pool cần tái kết nối và readiness trở lại UP.
- Reconciliation kiểm tra operation bị gián đoạn trước khi retry side effect.

## 17. Tránh health check gây tải hoặc che giấu lỗi

Một health check tốt phải nhẹ, có timeout và phản ánh đúng dependency.

Các lỗi thường gặp:

**Query quá nặng.** Dùng query quét bảng operation hoặc đếm toàn bộ binding làm readiness chậm và tăng tải database.

**Không đặt timeout.** Một health request có thể treo lâu, khiến kubelet timeout và restart không cần thiết.

**Chỉ kiểm tra port TCP.** Port mở không chứng minh credentials, connection pool và query hoạt động.

**Dùng chung liveness và readiness.** Database outage có thể gây restart loop.

**Health check luôn trả UP.** Broker có thể nhận traffic khi không ghi được operation hoặc không đọc được trạng thái instance.

**Kiểm tra mọi provider ở mỗi probe.** Tăng request, vượt quota và khiến một provider lỗi ảnh hưởng mọi replica.

**Lộ chi tiết hạ tầng.** Response có thể để lộ database hostname, schema, account hoặc exception message.

**Không kiểm tra trên main server port.** Management port còn sống trong khi main HTTP listener đã lỗi.

**Không test phục hồi.** Health chỉ chuyển DOWN nhưng không trở lại UP sau database recovery do pool hoặc cache trạng thái bị lỗi.

## 18. Observability cho readiness và database

Ngoài probe, cần metric để biết vì sao broker chưa ready và dependency đang suy giảm như thế nào.

Các metric nên quan sát:

| Metric | Ý nghĩa |
|---|---|
| application.ready hoặc trạng thái readiness | Instance có nhận traffic không |
| hikaricp.connections.active | Số connection đang được sử dụng |
| hikaricp.connections.idle | Số connection rảnh |
| hikaricp.connections.pending | Số request đang chờ connection |
| hikaricp.connections.timeout | Số lần lấy connection timeout |
| jdbc.connections.max / active | Mức sử dụng connection nếu metric được export |
| Database query latency | Thời gian query kiểm tra hoặc query nghiệp vụ |
| Health probe duration | Thời gian endpoint health phản hồi |
| broker_operations_queued | Số operation đang chờ |
| Outbox backlog | Số event chưa được publish |
| Provider failure rate | Lỗi provider theo nhóm và account |

Tên metric phụ thuộc phiên bản Micrometer, pool và cấu hình. Hãy kiểm tra metric thực tế được export thay vì giả định mọi metric đều tồn tại.

Tạo alert cho các dấu hiệu có thể hành động:

- Tất cả replica đồng thời unready.
- Readiness DOWN kéo dài.
- Connection pool pending tăng liên tục.
- Connection timeout vượt ngưỡng.
- Database query latency tăng bất thường.
- Outbox backlog hoặc operation queue tăng nhanh.
- Broker ready nhưng worker không thể ghi checkpoint.

Không đưa secret, password, raw SQL parameters hoặc tenant ID có cardinality cao vào metric label.

## 19. Kiểm thử readiness, liveness và database connectivity

Test cần xác minh trạng thái khi startup, khi database lỗi và khi database phục hồi. Không chỉ test endpoint trả 200 lúc mọi dependency đều khỏe.

| ID | Tình huống | Liveness | Readiness | Kết quả mong đợi |
|---|---|---|---|---|
| PROBE-001 | App khởi động bình thường, DB UP | UP | UP sau startup | Pod nhận traffic |
| PROBE-002 | Startup chưa hoàn tất | Chưa dùng để kết luận | OUT_OF_SERVICE/REFUSING | Startup probe tiếp tục chờ |
| PROBE-003 | DB mất kết nối | UP | DOWN nếu DB critical | Pod bị loại khỏi traffic, không restart chỉ vì DB |
| PROBE-004 | DB phục hồi | UP | Trở lại UP | Pod nhận traffic sau khi pool hoạt động |
| PROBE-005 | JVM deadlock hoặc state BROKEN | DOWN | Có thể DOWN | Platform restart theo liveness policy |
| PROBE-006 | Metrics backend lỗi | UP | UP nếu metrics không critical | Broker vẫn nhận request |
| PROBE-007 | Provider API outage, operation queue còn hoạt động | UP | Thường UP | Operation được lưu và worker retry |
| PROBE-008 | Connection pool cạn | UP | DOWN nếu không lấy được connection | Cảnh báo pool saturation |
| PROBE-009 | Migration thất bại | UP nếu process còn chạy | DOWN | Không nhận request |
| PROBE-010 | Graceful shutdown bắt đầu | UP trong thời gian dừng | REFUSING_TRAFFIC | Không nhận request mới |
| PROBE-011 | Main server không phục vụ nhưng management port còn sống | Probe main port thất bại | DOWN | Phát hiện lỗi listener |
| PROBE-012 | Health check timeout | Theo probe policy | Theo probe policy | Không treo vô hạn hoặc tạo tải lớn |

Các kiểm thử nên bao gồm:

- Unit test cho custom HealthIndicator/ReactiveHealthIndicator.
- Integration test với database thật hoặc Testcontainers.
- Test connection pool exhaustion và timeout có kiểm soát.
- Test database restart/failover nếu môi trường hỗ trợ.
- Test HTTP status và JSON của liveness/readiness group.
- Test Kubernetes manifest/probe path trong môi trường test.
- Test shutdown và readiness transition.
- Test rằng health response không chứa thông tin nhạy cảm.

## 20. Ví dụ kiểm thử health endpoint bằng WebTestClient

Có thể dùng WebTestClient để xác minh endpoint health khi ứng dụng đang chạy trong test context.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class BrokerHealthEndpointTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void livenessEndpointIsAvailable() {
        webTestClient.get()
                .uri("/actuator/health/liveness")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void readinessEndpointIsAvailableWhenDatabaseIsReady() {
        webTestClient.get()
                .uri("/actuator/health/readiness")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP");
    }
}
~~~

Test này cần database fixture sẵn sàng. Để kiểm tra DB outage, có thể dùng Testcontainers, đóng network hoặc cấu hình health contributor giả lập; không nên dựa vào database thật của developer để tạo lỗi không ổn định.

Trong test readiness DOWN, xác minh HTTP status là 503 theo mapping và JSON không lộ exception. Trong test liveness, xác minh database outage không làm liveness DOWN nếu policy thiết kế liveness độc lập với DB.

## 21. Checklist triển khai production

Trước khi triển khai broker lên Kubernetes hoặc Cloud Foundry, hãy kiểm tra:

- Đã định nghĩa rõ startup, liveness và readiness.
- Liveness không phụ thuộc database/provider dùng chung.
- Readiness kiểm tra đúng dependency cần thiết để nhận request OSB.
- Database health check dùng query nhẹ và timeout hữu hạn.
- Connection pool có giới hạn phù hợp với tổng số replica.
- Migration hoàn tất trước khi readiness ACCEPTING_TRAFFIC.
- Actuator chỉ expose endpoint cần thiết.
- Health details không tiết lộ hostname, SQL, credential hoặc exception.
- Kubernetes startupProbe, readinessProbe và livenessProbe trỏ đúng path/port.
- Probe kiểm tra main server port khi cần.
- Cloud Foundry health check phù hợp với semantics của platform đang dùng.
- Provider outage được xử lý bằng operation retry nếu broker vẫn có thể lưu công việc.
- Graceful shutdown chuyển readiness sang REFUSING_TRAFFIC.
- Worker ngừng claim operation mới và checkpoint công việc đang chạy.
- Có metric cho pool, DB latency, readiness và outbox backlog.
- Có test cho DB down, recovery, timeout, pool exhaustion và shutdown.

## Kết luận

Readiness, liveness và startup là ba tín hiệu khác nhau phục vụ ba quyết định khác nhau của platform. Với Spring Cloud Service Broker, readiness cần phản ánh khả năng nhận request và ghi nhận operation an toàn, thường bao gồm kết nối database nếu database là dependency thiết yếu. Liveness nên tập trung vào khả năng tự phục hồi của process và không bị kéo xuống chỉ vì một database hoặc provider dùng chung đang outage. Spring Boot Actuator health groups, Kubernetes probes và Cloud Foundry health checks cần được cấu hình theo đúng semantics của môi trường. Khi kết hợp timeout, connection pool hợp lý, migration có kiểm soát, graceful shutdown và kiểm thử phục hồi, broker có thể tránh nhận traffic quá sớm cũng như tránh restart loop trong sự cố dependency.

## Tài liệu tham khảo

- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — cấu hình và expose Actuator endpoint.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) — liveness/readiness health groups và additional paths.
- [Spring Boot Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html) — readiness và liveness state trong application lifecycle.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — hành vi probe và cấu hình container.
- [Cloud Foundry — Health Checks](https://docs.cloudfoundry.org/devguide/deploy-apps/healthchecks.html) — process, port và HTTP health checks.
- [Spring Boot DataSource Health Indicator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — health contributor cho dependency được auto-configure.
- [HikariCP Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby) — connection pool timeout và giới hạn kết nối.
- [Testcontainers for Java](https://java.testcontainers.org/) — kiểm thử tích hợp với database trong container.

