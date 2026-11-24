# Thêm Actuator, Micrometer và phụ thuộc cần cho từng thí nghiệm

Khi triển khai Spring Cloud CircuitBreaker, ứng dụng cần thư viện hiện thực để bảo vệ lời gọi đến dịch vụ phụ thuộc. Để quan sát cơ chế bảo vệ, cần thêm Spring Boot Actuator và tích hợp metrics của Resilience4j với Micrometer. Nếu muốn Prometheus thu thập số liệu, ứng dụng còn cần registry tương ứng. Mỗi thí nghiệm có thể cần thêm phụ thuộc riêng, chẳng hạn starter reactive hoặc thư viện kiểm thử luồng `Mono` và `Flux`.

Bài này chuẩn bị các phụ thuộc và cấu hình nền cho module **SPRING_CLOUD_CIRCUIT_BREAKER**. Mục tiêu là giúp ứng dụng chạy được thí nghiệm circuit breaker đồng bộ hoặc reactive, kiểm tra trạng thái qua Actuator và xuất metrics để quan sát hiệu quả bảo vệ dịch vụ.

## 1. Vai trò của từng thành phần

| Thành phần | Vai trò trong thí nghiệm |
|---|---|
| Spring Cloud CircuitBreaker | Cung cấp API thống nhất để bọc lời gọi đến dịch vụ phụ thuộc. |
| Resilience4j | Thực hiện circuit breaker và các cơ chế như Retry, Bulkhead, TimeLimiter, RateLimiter. |
| Spring Boot Actuator | Cung cấp các endpoint quản lý như `/actuator/health`, `/actuator/metrics` và endpoint Prometheus khi có registry phù hợp. |
| Micrometer | Cung cấp API metrics để ứng dụng và thư viện ghi nhận số liệu theo cách độc lập với hệ thống thu thập. |
| Micrometer Prometheus Registry | Chuyển metrics Micrometer thành định dạng Prometheus có thể scrape. |
| Spring WebFlux và Reactor | Cung cấp mô hình reactive để thực hành lời gọi bất đồng bộ bằng `Mono` hoặc `Flux`. |

Actuator và Micrometer có vai trò khác nhau. Actuator công bố các endpoint quản trị; Micrometer thu thập và chuẩn hóa số liệu. Chỉ thêm Actuator không đồng nghĩa mọi metrics riêng của Resilience4j đã được đăng ký. Cần có tích hợp Resilience4j-Micrometer tương thích với phiên bản thư viện đang dùng.

## 2. Quản lý phiên bản trước khi thêm dependency

Spring Boot, Spring Cloud và Resilience4j có quan hệ phiên bản. Trước khi thêm thư viện, hãy xác định phiên bản Spring Boot của dự án và dùng Spring Cloud BOM tương thích để quản lý các starter Spring Cloud. Không tùy tiện trộn các release train Spring Cloud hoặc ghi đè phiên bản transitive của Resilience4j bằng một phiên bản khác.

Với Maven, dự án thường đã khai báo Spring Boot parent hoặc Spring Boot dependency management và Spring Cloud BOM trong `dependencyManagement`. Ví dụ khai báo BOM Spring Cloud có dạng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Giá trị `spring-cloud.version` phải là release train tương thích với Spring Boot đang sử dụng. Nếu dự án đã có BOM, hãy giữ một nguồn quản lý phiên bản nhất quán thay vì khai báo BOM trùng lặp. Khi cần thêm module Resilience4j trực tiếp, hãy dùng BOM hoặc cơ chế quản lý phiên bản mà dự án đã chọn để các module Resilience4j cùng phiên bản.

## 3. Dependency nền cho circuit breaker và quan sát

Với ứng dụng Spring MVC hoặc lời gọi imperative, các dependency Maven cơ bản có thể gồm:

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
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Ý nghĩa của các dependency:

- `spring-cloud-starter-circuitbreaker-resilience4j` cung cấp tích hợp Spring Cloud CircuitBreaker với Resilience4j cho lời gọi imperative.
- `spring-boot-starter-actuator` bật các thành phần quản trị và tích hợp metrics của Spring Boot.
- `resilience4j-micrometer` cung cấp bộ chuyển đổi metrics của Resilience4j sang Micrometer. Kiểm tra dependency tree để biết starter hoặc cấu hình hiện tại đã cung cấp module này hay chưa; tránh khai báo trùng hoặc ép phiên bản không tương thích.
- `micrometer-registry-prometheus` cung cấp registry để xuất số liệu ở định dạng Prometheus. Đây là dependency phục vụ kịch bản Prometheus; nếu dùng backend khác, chọn registry tương ứng hoặc không cần registry Prometheus.

Nếu chỉ cần kiểm tra health và metrics qua Actuator mà chưa xuất số liệu cho Prometheus, có thể chưa thêm `micrometer-registry-prometheus`. Nếu ứng dụng không sử dụng Resilience4j metrics binder tự động từ cấu hình hiện tại, hãy thêm `resilience4j-micrometer` theo hướng dẫn của phiên bản Resilience4j đang dùng.

## 4. Bổ sung dependency theo từng thí nghiệm

Không phải ứng dụng nào cũng cần tất cả các starter. Chọn dependency theo mô hình gọi và nội dung thực hành:

| Thí nghiệm | Dependency hoặc thành phần cần thêm | Ghi chú |
|---|---|---|
| Circuit breaker imperative | `spring-cloud-starter-circuitbreaker-resilience4j` | Dùng với lời gọi đồng bộ, ví dụ client trả về đối tượng kết quả trực tiếp. |
| Circuit breaker reactive | `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | Dùng khi lời gọi trả về `Mono` hoặc `Flux`; cần có WebFlux/Reactor trong ứng dụng. |
| Health và metrics | `spring-boot-starter-actuator`, `resilience4j-micrometer` | Actuator công bố endpoint, binder ghi metrics Resilience4j vào Micrometer. |
| Scrape bằng Prometheus | `micrometer-registry-prometheus` | Chỉ thêm khi muốn xuất metrics theo định dạng Prometheus. |
| Kiểm thử ứng dụng | `spring-boot-starter-test` với scope `test` | Cung cấp nền tảng kiểm thử Spring Boot, JUnit và Mockito theo cấu hình dự án. |
| Kiểm thử reactive | `reactor-test` với scope `test` | Hỗ trợ kiểm tra publisher bằng `StepVerifier`. |
| Thử lỗi dịch vụ phụ thuộc | Mock client, WireMock hoặc MockWebServer | Chọn công cụ phù hợp để mô phỏng timeout, lỗi HTTP và phục hồi. |

Nếu dùng reactive, dependency Spring Cloud tương ứng là:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

Không thay starter imperative bằng reactive chỉ vì ứng dụng có dùng `CompletableFuture`. Reactive starter dành cho luồng Reactor; lựa chọn phụ thuộc vào kiểu dữ liệu và mô hình thực thi của client. Nếu cùng một ứng dụng có cả hai loại lời gọi, hãy xác nhận các starter tương thích trong dependency tree và chỉ cấu hình những phần thực sự sử dụng.

Với các thí nghiệm Retry, Bulkhead, TimeLimiter hoặc RateLimiter, Spring Cloud CircuitBreaker và Resilience4j có thể cung cấp một phần tích hợp qua starter. Nếu bài thực hành gọi trực tiếp API của Resilience4j, có thể cần module tương ứng như `resilience4j-retry`, `resilience4j-bulkhead`, `resilience4j-timelimiter` hoặc `resilience4j-ratelimiter`. Hãy kiểm tra module đã có theo dependency tree trước khi thêm thủ công. Các module cùng họ phải dùng phiên bản đồng bộ.

## 5. Cấu hình Actuator và Micrometer

Sau khi thêm dependency, cấu hình những endpoint cần dùng trong `application.yml`:

```yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  metrics:
    tags:
      application: ${spring.application.name}

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
```

Trong cấu hình trên:

- `health` cung cấp thông tin sức khỏe ứng dụng và các health indicator đã đăng ký.
- `metrics` cho phép tra cứu các meter qua Actuator.
- `prometheus` công bố endpoint Prometheus khi registry tương ứng có mặt.
- `application` là tag chung giúp phân biệt số liệu của các ứng dụng khi cùng đẩy về một backend.
- `registerHealthIndicator: true` đăng ký health indicator cho circuit breaker `inventory` nếu tích hợp phiên bản đang dùng hỗ trợ cấu hình này.

Chỉ expose các endpoint cần thiết. Trong môi trường dùng Spring Security, hãy cấu hình quyền truy cập cho endpoint quản trị theo chính sách của ứng dụng; không để endpoint chứa thông tin vận hành nhạy cảm có thể truy cập công khai. `show-details: when-authorized` giới hạn việc hiển thị chi tiết health theo cơ chế xác thực và phân quyền đã cấu hình.

Health indicator của circuit breaker phản ánh trạng thái phụ thuộc thông qua mạch. Mạch `OPEN` có thể khiến health của thành phần phụ thuộc báo không khỏe dù tiến trình ứng dụng vẫn chạy bình thường. Khi triển khai readiness và liveness probe, hãy quyết định rõ trạng thái circuit breaker có nên ảnh hưởng đến khả năng nhận traffic hay không. Không nên để lỗi của một dịch vụ phụ thuộc khiến liveness probe khởi động lại liên tục một ứng dụng vẫn có thể phục vụ các chức năng khác.

## 6. Kiểm tra endpoint sau khi khởi động

Sau khi chạy ứng dụng với profile cấu hình phù hợp, có thể kiểm tra các endpoint đã expose. Ví dụ khi Actuator dùng cổng và context path mặc định:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
```

Kết quả mong đợi:

- `/actuator/health` trả trạng thái sức khỏe tổng hợp. Nếu đã bật health indicator của Resilience4j, kiểm tra phần chi tiết tương ứng khi tài khoản được phép xem.
- `/actuator/metrics` liệt kê các meter đã đăng ký. Có thể truy vấn một meter cụ thể bằng tên được trả về trong danh sách.
- `/actuator/prometheus` trả dữ liệu dạng text để Prometheus scrape, nếu đã thêm Prometheus registry và expose endpoint.

Tên meter và tag cụ thể phụ thuộc phiên bản Resilience4j, Micrometer và cấu hình binder. Các nhóm số liệu thường cần quan sát gồm số lời gọi thành công, thất bại, bị từ chối khi mạch mở, tỷ lệ lỗi, tỷ lệ lời gọi chậm và trạng thái circuit breaker. Không giả định một meter tồn tại chỉ vì endpoint Actuator trả HTTP 200; hãy kiểm tra danh sách meter và xác nhận số liệu thay đổi khi thực hiện lời gọi thử nghiệm.

Nếu `/actuator/metrics` hoạt động nhưng không có metrics circuit breaker, kiểm tra module `resilience4j-micrometer`, cấu hình tự động tạo binder, tên instance và việc lời gọi thực sự đi qua circuit breaker. Nếu `/actuator/prometheus` trả 404, kiểm tra Prometheus registry và cấu hình exposure. Nếu endpoint bị từ chối, kiểm tra security rules, cổng quản trị và context path.

## 7. Chuẩn bị thí nghiệm circuit breaker và fallback

Thí nghiệm cơ bản cần một client gọi đến dịch vụ phụ thuộc và một circuit breaker có định danh. Có thể dùng client giả trong unit test hoặc một dịch vụ mô phỏng để chủ động tạo phản hồi thành công, lỗi và độ trễ.

Ví dụ khai báo một service imperative:

```java
@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Stock findStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.findStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
```

Trong thí nghiệm, thay đổi hành vi của `InventoryClient` theo các tình huống:

1. Trả kết quả thành công để quan sát số lời gọi thành công và trạng thái `CLOSED`.
2. Ném lỗi hoặc trả lỗi kết nối đủ số lần để vượt ngưỡng, sau đó xác nhận mạch chuyển sang `OPEN` và lời gọi tiếp theo được từ chối sớm.
3. Cho lời gọi chính thất bại để xác nhận fallback trả trạng thái dự phòng có ý nghĩa nghiệp vụ.
4. Khôi phục client sau thời gian chờ để quan sát các lời gọi thăm dò ở `HALF_OPEN`.

Đối chiếu từng tình huống với `/actuator/health`, `/actuator/metrics` hoặc dữ liệu Prometheus. Metrics cần thay đổi theo lời gọi thực tế; fallback được gọi không có nghĩa lời gọi đến dịch vụ phụ thuộc đã thành công.

## 8. Chuẩn bị thí nghiệm reactive

Nếu ứng dụng dùng WebFlux, client nên trả về `Mono` hoặc `Flux` và service sử dụng `ReactiveCircuitBreakerFactory`. Thêm `reactor-test` ở scope `test` để kiểm tra publisher mà không cần gọi `block()`.

Ví dụ kiểm thử với `StepVerifier`:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveInventoryServiceTest {
    @Test
    void returnsFallbackWhenDependencyFails() {
        Mono<Stock> result = Mono.just(Stock.unavailable("SKU-1"));

        StepVerifier.create(result)
            .expectNextMatches(stock -> !stock.isAvailable())
            .verifyComplete();
    }
}
```

Đoạn kiểm thử trên minh họa cách xác nhận một publisher phát ra kết quả dự phòng; trong bài thực hành hoàn chỉnh, hãy thay `Mono` tạo trực tiếp bằng lời gọi service đã được bọc circuit breaker và mock client để điều khiển lỗi. Dùng `StepVerifier` để kiểm tra giá trị, lỗi và tín hiệu hoàn tất theo đúng ngữ nghĩa reactive. Không chặn event loop bằng `block()` trong mã reactive của ứng dụng.

## 9. Kiểm tra dependency và xử lý lỗi cấu hình

Khi dependency đã được thêm, có thể dùng Maven để xem module thực tế mà dự án nhận được:

```bash
mvn dependency:tree
```

Tìm các nhóm `spring-cloud-starter-circuitbreaker`, `resilience4j`, `spring-boot-starter-actuator`, `micrometer-core` và registry đã chọn. Nếu cùng một module xuất hiện với nhiều phiên bản, xem lại BOM và các dependency ghi đè. Không thêm thủ công một phiên bản mới chỉ để khắc phục lỗi runtime khi chưa xác định nguyên nhân xung đột.

Một số tình huống thường gặp:

| Hiện tượng | Điểm cần kiểm tra |
|---|---|
| Không inject được `CircuitBreakerFactory` | Starter Resilience4j đã có trong runtime classpath chưa; dependency và phiên bản Spring Cloud có tương thích không? |
| Không inject được `ReactiveCircuitBreakerFactory` | Đã thêm reactive starter và các dependency Reactor cần thiết chưa? |
| Health không hiển thị circuit breaker | Instance đã bật `registerHealthIndicator` chưa; phiên bản provider có health indicator tương ứng không? |
| Metrics circuit breaker không xuất hiện | Có `resilience4j-micrometer` và binder tương thích không; lời gọi có đi qua circuit breaker không? |
| Endpoint Prometheus không tồn tại | Đã thêm `micrometer-registry-prometheus` và expose `prometheus` chưa? |
| Ứng dụng không truy cập được endpoint | Kiểm tra security, cổng quản trị, base path và danh sách endpoint được expose. |

## 10. Checklist trước khi bắt đầu thực hành

- [ ] Spring Boot và Spring Cloud dùng phiên bản tương thích, được quản lý nhất quán bằng BOM.
- [ ] Ứng dụng có starter Resilience4j phù hợp với kiểu gọi imperative hoặc reactive.
- [ ] Actuator đã được thêm và chỉ expose các endpoint cần thiết.
- [ ] Resilience4j-Micrometer được tích hợp để ghi metrics circuit breaker.
- [ ] Prometheus registry được thêm nếu thí nghiệm cần Prometheus scrape.
- [ ] Cấu hình instance circuit breaker có tên khớp với định danh trong mã.
- [ ] Có client hoặc dịch vụ mô phỏng để tạo thành công, lỗi, timeout và phục hồi.
- [ ] Với reactive, có `reactor-test` và kiểm thử publisher bằng `StepVerifier`.
- [ ] Đã xác nhận endpoint và metrics thay đổi sau khi chạy một lời gọi thực tế.

Khi hoàn tất các bước chuẩn bị này, môi trường đã có nền tảng để thực hành trạng thái circuit breaker, fallback, timeout, bulkhead và quan sát hiệu quả bảo vệ. Hãy thêm dependency theo từng thí nghiệm, giữ phiên bản đồng bộ và kiểm tra số liệu bằng các endpoint đã cấu hình trước khi đưa cơ chế bảo vệ vào dịch vụ thật.
