# Không có metrics hay health indicator do thiếu phụ thuộc hoặc exposure

Khi triển khai Spring Cloud CircuitBreaker với Resilience4j, ứng dụng có thể gọi dependency và chuyển trạng thái breaker bình thường nhưng không thấy metrics hoặc health indicator trong Spring Boot Actuator. Hai nhóm chức năng này cần các thành phần tích hợp riêng: Actuator cung cấp endpoint, Micrometer nhận và xuất metrics, còn Resilience4j cần binder hoặc Spring Boot integration phù hợp để đăng ký số liệu và health contributor.

Một endpoint không xuất hiện chưa đủ để kết luận circuit breaker không hoạt động. Có thể thiếu dependency, sai phiên bản, thiếu registry, chưa bật health indicator cho instance, hoặc endpoint đã tồn tại nhưng chưa được expose qua HTTP. Cần kiểm tra từng lớp theo thứ tự để tìm đúng nguyên nhân.

## 1. Phân biệt metrics, health indicator và trạng thái circuit breaker

Ba khái niệm liên quan nhưng trả lời các câu hỏi khác nhau:

| Thành phần | Mục đích | Nơi thường quan sát |
| --- | --- | --- |
| Circuit breaker runtime | Cho phép hoặc từ chối lời gọi theo trạng thái và sliding window | `CircuitBreakerRegistry`, log và event |
| Micrometer metrics | Đếm kết quả, đo thời gian, tỷ lệ lỗi/chậm và trạng thái | Actuator `/metrics`, Prometheus hoặc backend metrics |
| Health indicator | Tổng hợp tình trạng breaker thành một health contributor | Actuator `/health` và health group |

Breaker có thể hoạt động dù metrics binder chưa được thêm. Metrics có thể tồn tại trong `MeterRegistry` dù endpoint `/actuator/metrics` chưa được expose. Health endpoint có thể trả `UP` mà không có chi tiết breaker nếu integration hoặc cấu hình đăng ký health indicator chưa được bật.

Do đó, hãy xác định rõ triệu chứng:

- Không có endpoint `/actuator/metrics` hoặc `/actuator/prometheus`.
- Endpoint có nhưng không liệt kê meter của Resilience4j.
- Meter có nhưng không có dữ liệu hoặc không có tag theo breaker ID.
- `/actuator/health` hoạt động nhưng không hiển thị component circuit breaker.
- Health component có nhưng không phản ánh state hoặc trạng thái tổng thể khác mong đợi.

Mỗi trường hợp có nguyên nhân và cách kiểm tra khác nhau.

## 2. Kiểm tra dependency trước tiên

Với Maven, ứng dụng dùng Spring Cloud CircuitBreaker Resilience4j backend thường cần starter tương ứng, Actuator và Micrometer binder. Nếu muốn scrape bằng Prometheus, thêm Prometheus registry:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Vai trò của từng dependency:

- `spring-cloud-starter-circuitbreaker-resilience4j` cung cấp Spring Cloud CircuitBreaker factory với Resilience4j backend.
- `spring-boot-starter-actuator` cung cấp các endpoint vận hành như health và metrics.
- `resilience4j-micrometer` cung cấp tích hợp meter cho các thành phần Resilience4j.
- `micrometer-registry-prometheus` cung cấp registry và định dạng scrape Prometheus.

Nếu ứng dụng cần health indicator tự động của Resilience4j Spring Boot integration, kiểm tra dự án đã dùng đúng integration tương thích với phiên bản Spring Boot hay chưa. Với Spring Boot 3, artifact thường dùng là `resilience4j-spring-boot3`; dự án Spring Boot 2 cần artifact tương ứng cho Boot 2. Tích hợp Spring Cloud factory và tích hợp Spring Boot native có mục đích khác nhau; không thêm nhiều starter một cách máy móc nếu chúng tạo cấu hình hoặc registry trùng lặp. Hãy xác minh bean và registry mà ứng dụng thực sự sử dụng.

Quản lý phiên bản Spring Boot, Spring Cloud, Resilience4j và Micrometer bằng BOM/dependency management tương thích. Tránh tự ghép các phiên bản khác release train vì auto-configuration hoặc meter binder có thể không tương thích.

### Kiểm tra dependency tree

Với Maven Wrapper, xem dependency tree để xác nhận artifact đã có trong runtime classpath:

```bash
./mvnw dependency:tree
```

Có thể lọc theo nhóm liên quan:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud,io.github.resilience4j,io.micrometer
```

Kiểm tra cả scope của dependency. Một thư viện chỉ nằm trong `test` scope sẽ không được nạp khi ứng dụng chạy production. Nếu dùng Gradle, xem `runtimeClasspath` thay vì chỉ kiểm tra compile/test configuration.

## 3. Bật đúng Actuator endpoint exposure

Có dependency Actuator không có nghĩa mọi endpoint đều được mở qua HTTP. Spring Boot tách việc endpoint được enable khỏi việc endpoint được expose qua web hoặc JMX. Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

`health` thường được expose mặc định trong cấu hình tiêu chuẩn, nhưng `metrics` và `prometheus` cần được đưa vào danh sách exposure nếu muốn truy cập qua HTTP. `prometheus` chỉ có thể hoạt động khi registry Prometheus tương ứng đã có trên classpath và được auto-configure.

Nếu ứng dụng có cấu hình `management.endpoints.web.exposure.include` ở nhiều file profile, hãy kiểm tra giá trị cuối cùng sau khi merge. Một file profile có thể ghi đè danh sách exposure và vô tình loại bỏ `metrics` hoặc `prometheus`.

Exposure không thay thế bảo mật. Chỉ expose endpoint cần thiết, giới hạn truy cập qua mạng quản trị/monitoring và áp dụng authentication/authorization thích hợp. Không mở `env`, `configprops` hoặc health details nhạy cảm công khai chỉ để chẩn đoán.

## 4. Xác minh endpoint có thực sự được expose

Sau khi ứng dụng khởi động, kiểm tra từ đúng host, port và management base path:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
```

Nếu dùng management port riêng, context path khác hoặc reverse proxy, URL sẽ thay đổi. Ví dụ:

```yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      base-path: /manage
```

Khi đó endpoint có thể là `http://localhost:9091/manage/health`, không phải `/actuator/health` trên cổng ứng dụng. Kiểm tra cấu hình thực tế thay vì đoán URL.

Đọc HTTP status và response:

| Kết quả | Hướng kiểm tra |
| --- | --- |
| `404 Not Found` | Endpoint chưa được expose, sai base path/port hoặc endpoint không được auto-configure |
| `401 Unauthorized` / `403 Forbidden` | Endpoint có thể tồn tại nhưng bị Spring Security hoặc proxy chặn |
| `503 Service Unavailable` ở health | Health contributor báo `DOWN` hoặc trạng thái tổng thể không đạt; đọc chi tiết nếu được phép |
| `200 OK` nhưng không có breaker detail | Health endpoint hoạt động, nhưng health contributor của Resilience4j có thể chưa được đăng ký hoặc chưa được bật |
| `/metrics` có nhưng không có meter Resilience4j | Kiểm tra Micrometer binder, registry và việc breaker được tạo/đăng ký |
| `/prometheus` trả `404` | Kiểm tra Prometheus registry dependency và exposure |

Nếu endpoint bị chặn bởi security, không tắt toàn bộ bảo mật để thử. Dùng tài khoản/role quản trị được cấp hoặc kiểm tra từ mạng monitoring theo chính sách của ứng dụng.

## 5. Bật health indicator của Resilience4j

Với Spring Boot integration của Resilience4j, cần bật health indicator toàn cục và đăng ký indicator cho instance cần theo dõi. Ví dụ:

```yaml
management:
  health:
    circuitbreakers:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
```

Hai cấu hình có ý nghĩa riêng:

- `management.health.circuitbreakers.enabled` bật health contributor circuit breaker trong Actuator integration tương ứng.
- `resilience4j.circuitbreaker.instances.inventory.registerHealthIndicator` yêu cầu đăng ký health indicator cho instance `inventory`.

Tên và khả năng của health contributor phụ thuộc phiên bản Resilience4j Spring Boot integration. Sau khi bật, gọi `/actuator/health` để xem danh sách component thực tế; nếu component được expose riêng, dùng đúng ID mà response trả về. Không mặc định mọi phiên bản đều dùng cùng cách viết path con.

Nếu ứng dụng chỉ dùng Spring Cloud CircuitBreaker factory mà không có Spring Boot health integration, factory có thể vẫn hoạt động nhưng health contributor native của Resilience4j không tự xuất hiện. Khi cần health indicator, thêm integration tương thích hoặc tự triển khai `HealthIndicator` dựa trên đúng breaker instance mà ứng dụng đang sử dụng.

## 6. Health indicator không phải readiness và liveness giống nhau

Health indicator của circuit breaker có thể báo `DOWN` khi breaker `OPEN`, tùy mapping của integration và phiên bản. Điều đó phản ánh dependency đang không khỏe theo góc nhìn của caller; nó không nhất thiết có nghĩa tiến trình Spring Boot đã chết hoặc không thể phục vụ bất kỳ request nào.

Trong Kubernetes, cần phân biệt:

- **Liveness:** tiến trình còn sống và có thể tiếp tục chạy hay không.
- **Readiness:** instance có nên nhận traffic mới hay không.
- **Dependency health:** một dịch vụ phụ thuộc cụ thể đang có thể phục vụ lời gọi hay không.

Không đưa health indicator dependency vào liveness probe một cách tùy tiện. Nếu Inventory Service gặp outage, breaker chuyển `OPEN`, health tổng thể thành `DOWN` và liveness probe làm Kubernetes restart toàn bộ pod Order Service, hệ thống có thể tạo thêm vòng lặp restart trong khi ứng dụng vẫn có thể phục vụ các chức năng khác hoặc trả fallback.

Hãy thiết kế health group rõ ràng. Liveness nên phản ánh tình trạng tiến trình; readiness có thể phản ánh khả năng phục vụ theo chính sách của service; dependency health nên được theo dõi riêng hoặc chỉ tham gia readiness khi nghiệp vụ thực sự yêu cầu. Cẩn trọng khi tất cả replica cùng bị đánh dấu not-ready vì một dependency dùng chung đang lỗi.

## 7. Kiểm tra Micrometer binder và meter registry

Sau khi có Actuator `/metrics`, kiểm tra danh sách meter:

```bash
curl http://localhost:8080/actuator/metrics
```

Tìm meter liên quan đến Resilience4j, thường có các tên dạng:

- `resilience4j.circuitbreaker.calls`
- `resilience4j.circuitbreaker.state`
- `resilience4j.circuitbreaker.failure.rate`
- `resilience4j.circuitbreaker.slow.call.rate`
- `resilience4j.circuitbreaker.buffered.calls`

Tên và tag chính xác có thể thay đổi theo phiên bản và registry. Hãy dùng danh sách meter do ứng dụng trả về làm nguồn xác minh. Nếu meter xuất hiện, truy vấn một meter cụ thể:

```bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory"
```

Nếu response báo meter không tồn tại:

1. Xác nhận `resilience4j-micrometer` có trong runtime classpath.
2. Xác nhận `MeterRegistry` được Spring Boot tạo và không bị thay thế bởi registry độc lập.
3. Xác nhận breaker instance `inventory` thực sự được tạo và sử dụng.
4. Kiểm tra integration có tự bind metrics hay cần bind registry theo cách của phiên bản đó.
5. Kiểm tra tên meter và tag thực tế từ `/actuator/metrics`.

Trong ứng dụng dùng Resilience4j native registry, có thể bind metric thủ công nếu integration chưa tự thực hiện:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerMetricsConfiguration {

    public CircuitBreakerMetricsConfiguration(
            CircuitBreakerRegistry circuitBreakerRegistry,
            MeterRegistry meterRegistry) {
        TaggedCircuitBreakerMetrics
            .ofCircuitBreakerRegistry(circuitBreakerRegistry)
            .bindTo(meterRegistry);
    }
}
```

Đoạn mã này dành cho trường hợp ứng dụng quản lý `CircuitBreakerRegistry` native và chưa có binder tự động. Nếu Resilience4j Spring Boot integration hoặc customizer đã bind meter, không bind lần thứ hai vì có thể tạo đăng ký trùng hoặc hành vi khó hiểu. Quan trọng nhất là binder và mã nghiệp vụ phải dùng cùng registry/instance.

## 8. Phân biệt thiếu meter với chưa có dữ liệu

Một meter có thể đã được đăng ký nhưng chưa có giá trị đáng kể vì chưa có lời gọi. Ví dụ timer `resilience4j.circuitbreaker.calls` chỉ có dữ liệu sau khi supplier được thực thi và kết quả được ghi nhận. Gauge state có thể tồn tại ngay sau khi breaker được tạo, trong khi timer count vẫn bằng 0.

Để kiểm tra, tạo một lời gọi thành công có kiểm soát trong môi trường dev/test rồi truy vấn lại meter. Sau đó mô phỏng một lỗi được cấu hình ghi nhận và một lời gọi bị từ chối khi breaker `OPEN`. Xác minh các loại kết quả xuất hiện với tag phù hợp.

Không dùng request thật tới hệ thống thanh toán hoặc dependency production chỉ để tạo metric thử. Dùng mock, stub hoặc môi trường test có dữ liệu và endpoint kiểm soát được.

Nếu `/actuator/metrics` liệt kê meter nhưng Prometheus không có series, kiểm tra thêm:

- Prometheus registry có được thêm và auto-configure không?
- `/actuator/prometheus` có trả output và có chứa tên metric đã chuyển đổi không?
- Prometheus scrape đúng scheme, host, port, path và authentication không?
- Target có ở trạng thái `UP` trong Prometheus không?
- Relabeling hoặc metric filtering có loại bỏ series không?

Micrometer meter name có thể được chuyển đổi khi xuất Prometheus, ví dụ dấu chấm thành dấu gạch dưới. Tìm theo tên đã xuất ở endpoint Prometheus, không chỉ theo tên Micrometer.

## 9. Kiểm tra auto-configuration và registry đang được dùng

Nếu dependency và exposure đã đúng nhưng indicator hoặc meter vẫn thiếu, kiểm tra auto-configuration:

1. Đảm bảo dependency nằm trong runtime classpath và đúng phiên bản Spring Boot.
2. Kiểm tra log khởi động để tìm lỗi tạo bean hoặc điều kiện auto-configuration không thỏa mãn.
3. Trong môi trường phát triển, có thể bật report điều kiện auto-configuration bằng `--debug` khi khởi động để xem cấu hình nào được áp dụng hoặc bị bỏ qua.
4. Xác minh `CircuitBreakerRegistry` và `MeterRegistry` là bean do integration dự kiến quản lý.
5. Xác minh breaker ID được tạo qua cùng factory/registry mà health indicator và metrics binder đang quan sát.

Ví dụ một lỗi thường gặp là service gọi `CircuitBreakerFactory.create("inventory")` nhưng custom metrics code lại tạo `CircuitBreakerRegistry.ofDefaults()` riêng. Hai nơi có thể chứa hai breaker khác nhau cùng tên; metric của registry phụ không phản ánh lời gọi thật. Tương tự, health indicator lấy registry khác có thể luôn báo state `CLOSED` dù breaker factory đang `OPEN`.

Không tạo registry mới trong mỗi request hoặc trong mỗi cấu hình listener. Dùng một registry được quản lý trong application context và thống nhất cách tạo instance giữa mã gọi, metrics và health.

## 10. Ví dụ cấu hình hoàn chỉnh

Một cấu hình cơ bản cho service Spring Boot có Resilience4j, Actuator và Prometheus có thể như sau:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  health:
    circuitbreakers:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: ${spring.application.name}
```

Đảm bảo classpath có các dependency cần thiết cho backend, Actuator, Micrometer binder và registry xuất dữ liệu. Health indicator cần Spring Boot integration tương thích hoặc một implementation riêng. Sau khi chạy, xác minh lần lượt `/actuator/health`, `/actuator/metrics` và `/actuator/prometheus`.

## 11. Checklist chẩn đoán nhanh

| Triệu chứng | Kiểm tra trước | Hành động |
| --- | --- | --- |
| `/actuator/metrics` trả 404 | Actuator dependency, endpoint enabled và web exposure | Thêm Actuator và expose `metrics`; kiểm tra port/base path |
| `/actuator/prometheus` trả 404 | Prometheus registry và exposure | Thêm `micrometer-registry-prometheus`, expose `prometheus` |
| Metrics endpoint có nhưng thiếu meter Resilience4j | `resilience4j-micrometer`, registry và breaker instance | Thêm binder phù hợp; xác minh cùng registry và tạo lời gọi test |
| Health endpoint không có component circuit breaker | Resilience4j Spring Boot integration, global enable và per-instance registration | Bật health indicator và kiểm tra đúng integration/phiên bản |
| Health component luôn `UP` dù breaker `OPEN` | Registry/instance được health indicator quan sát và state mapping của phiên bản | Xác minh cùng instance; kiểm tra mapping và cấu hình health |
| Prometheus không có series dù Actuator metrics có | Registry Prometheus, scrape target/path, filtering | Kiểm tra `/actuator/prometheus` và trạng thái target |
| Endpoint trả 401/403 | Spring Security hoặc reverse proxy | Cấp quyền cho monitoring principal, không tắt bảo mật toàn cục |
| Health `DOWN` làm pod restart | Liveness/readiness group | Không đưa dependency health vào liveness một cách tùy tiện |

## 12. Quy tắc triển khai

- Dùng đúng Spring Cloud Resilience4j backend và phiên bản tương thích với Spring Boot.
- Thêm Actuator để có endpoint vận hành; thêm `resilience4j-micrometer` để bind metrics.
- Thêm Prometheus registry nếu cần scrape định dạng Prometheus.
- Dùng Spring Boot Resilience4j integration tương thích hoặc HealthIndicator riêng nếu cần health contributor native.
- Bật `registerHealthIndicator` cho instance và global health integration theo phiên bản đang dùng.
- Phân biệt endpoint được enable với endpoint được expose qua HTTP.
- Kiểm tra port, base path, security và profile đang hoạt động.
- Đảm bảo health indicator, metrics binder và mã gọi quan sát cùng breaker registry/instance.
- Không dùng dependency health làm liveness probe nếu điều đó có thể gây restart dây chuyền.
- Kiểm tra meter thực tế bằng Actuator trước khi viết Prometheus query hoặc dashboard.

Khi metrics hoặc health indicator không xuất hiện, hãy lần lượt xác minh dependency, auto-configuration, registry, instance ID và endpoint exposure. Cách kiểm tra theo từng lớp giúp phân biệt lỗi tích hợp Resilience4j với lỗi cấu hình Actuator hoặc bảo mật, đồng thời tránh thay đổi circuit breaker runtime khi vấn đề thực sự chỉ nằm ở đường quan sát.
