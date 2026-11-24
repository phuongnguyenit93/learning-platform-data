# Phân biệt starter Spring Cloud với starter Resilience4j trực tiếp

Trong Spring Cloud Circuit Breaker, Resilience4j là một bộ máy thực thi Circuit Breaker; Spring Cloud cung cấp thêm một lớp API thống nhất để ứng dụng gọi bộ ngắt. Starter Spring Cloud CircuitBreaker và starter Spring Boot của Resilience4j đều có thể đưa Resilience4j vào ứng dụng, nhưng chúng cung cấp cách tích hợp và API khác nhau.

Phân biệt hai lựa chọn này ngay từ bước chuẩn bị môi trường giúp tránh khai báo dependency không cần thiết, dùng nhầm API hoặc vô tình bọc một lời gọi bằng nhiều Circuit Breaker. Mục tiêu của cả hai là bảo vệ dịch vụ phụ thuộc chậm hoặc không khả dụng, hạn chế lỗi dây chuyền và cho phép ứng dụng trả fallback có kiểm soát.

## 1. Hai starter giải quyết hai nhu cầu tích hợp khác nhau

**Spring Cloud CircuitBreaker với Resilience4j** đặt một lớp trừu tượng giữa mã ứng dụng và thư viện Circuit Breaker. Ứng dụng tạo bộ ngắt thông qua `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`. Starter tự cấu hình implementation Resilience4j và cung cấp các factory tương ứng. Cách này hữu ích khi ứng dụng muốn dùng API của Spring Cloud và giữ mức phụ thuộc vào implementation thấp hơn.

**Resilience4j Spring Boot starter trực tiếp** tích hợp Resilience4j vào Spring Boot. Starter cung cấp cấu hình tự động, registry và các annotation như `@CircuitBreaker`, `@Retry`, `@RateLimiter` và `@Bulkhead` thông qua Spring AOP. Ứng dụng gọi annotation hoặc API của Resilience4j trực tiếp, phù hợp khi muốn dùng các khả năng riêng của thư viện mà không cần lớp trừu tượng Spring Cloud.

| Tiêu chí | Spring Cloud CircuitBreaker + Resilience4j | Resilience4j Spring Boot trực tiếp |
| --- | --- | --- |
| API chính | `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` | `@CircuitBreaker`, `CircuitBreakerRegistry`, API Resilience4j |
| Cách bảo vệ lời gọi | Bao lời gọi bằng factory và callback fallback | Đánh dấu phương thức bằng annotation hoặc gọi registry/API trực tiếp |
| Phạm vi tích hợp | Lớp trừu tượng Spring Cloud với implementation được chọn | Tích hợp trực tiếp thư viện Resilience4j vào Spring Boot |
| Reactive | Dùng starter Reactor và `ReactiveCircuitBreakerFactory` | Thêm `resilience4j-reactor` để hỗ trợ Reactor `Mono`/`Flux` |
| Cấu hình | Dùng thuộc tính Resilience4j và có thể tùy biến factory bằng `Customizer` | Dùng thuộc tính Resilience4j và các customizer/registry của thư viện |

Không có lựa chọn nào tự động tốt hơn trong mọi dự án. Hãy chọn theo API mà mã ứng dụng cần sử dụng và kiến trúc Spring đang có.

## 2. Khai báo dependency cho Spring Cloud CircuitBreaker

Với ứng dụng Spring MVC hoặc lời gọi đồng bộ, dùng starter không reactive:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

Với ứng dụng WebFlux dùng Reactor, thay bằng starter reactive:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

Trong cả hai trường hợp, quản lý phiên bản Spring Cloud bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. Ví dụ cấu trúc Gradle Groovy:

```groovy
ext {
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
```

Thay placeholder bằng release train tương thích được công bố trong ma trận hỗ trợ Spring Cloud và Spring Boot của dự án. Không tự chọn phiên bản starter riêng lẻ hoặc trộn các release train khác nhau.

### API factory của Spring Cloud

Ví dụ bảo vệ lời gọi lấy tồn kho bằng `CircuitBreakerFactory`: 

```java
@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
```

`create("inventory")` lấy bộ ngắt có ID `inventory`. Hàm thứ nhất thực hiện lời gọi tới dịch vụ phụ thuộc; hàm thứ hai xử lý lỗi để tạo kết quả dự phòng. Khi bộ ngắt `OPEN`, lời gọi được từ chối nhanh và fallback có thể trả trạng thái tồn kho chưa xác định. Khi `HALF_OPEN`, chỉ các lời gọi thăm dò được cấp quyền mới đi tới dịch vụ.

Với Reactor, dùng `ReactiveCircuitBreakerFactory` để bọc `Mono` hoặc `Flux`. Chọn đúng starter reactive khi ứng dụng cần API này; không suy ra rằng chỉ vì ứng dụng có WebFlux thì mọi lời gọi đều tự động được bảo vệ.

## 3. Khai báo dependency cho Resilience4j trực tiếp

Với Spring Boot 3, starter trực tiếp là `io.github.resilience4j:resilience4j-spring-boot3`. Tài liệu Resilience4j yêu cầu Actuator và Spring AOP có mặt trong runtime:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Quản lý phiên bản các module Resilience4j bằng Resilience4j BOM để những module cùng họ dùng phiên bản tương thích:

```groovy
dependencyManagement {
    imports {
        mavenBom "io.github.resilience4j:resilience4j-bom:${resilience4jVersion}"
    }
}
```

Chọn starter phù hợp với major version Spring Boot đang dùng. Với Spring Boot 2, tài liệu Resilience4j sử dụng module `resilience4j-spring-boot2`; với Spring Boot 3, dùng `resilience4j-spring-boot3`. Không thay tên module theo suy đoán nếu dự án đang dùng một dòng phiên bản khác.

Nếu ứng dụng dùng WebFlux và cần bảo vệ `Mono`/`Flux` qua tích hợp Reactor của Resilience4j, thêm module:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-reactor'
}
```

### API annotation của Resilience4j

Starter trực tiếp cho phép đặt annotation lên phương thức Spring-managed:

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    Stock inventoryFallback(String sku, Throwable cause) {
        return Stock.unavailable(sku);
    }
}
```

`fallbackMethod` phải có các tham số của phương thức gốc và thêm tham số ngoại lệ ở cuối; kiểu trả về cần phù hợp với phương thức được bảo vệ. Annotation được áp dụng qua Spring AOP, vì vậy phương thức cần được gọi qua proxy Spring. Lời gọi nội bộ kiểu `this.getStock(...)` trong cùng bean không đi qua proxy AOP theo cách thông thường và có thể bỏ qua aspect.

Nếu muốn điều khiển bằng API thay vì annotation, có thể lấy instance từ `CircuitBreakerRegistry` rồi gọi `executeSupplier`, `executeCallable` hoặc API tương ứng. Đây là API của Resilience4j, không phải `CircuitBreakerFactory` của Spring Cloud.

## 4. Cấu hình thuộc tính Circuit Breaker

Cả hai cách tích hợp đều có thể sử dụng cấu hình instance của Resilience4j trong `application.yml`. Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

ID `inventory` phải trùng với tên instance được tham chiếu trong mã. Trong cấu hình này, bộ ngắt ghi nhận tối đa 20 kết quả theo cửa sổ đếm, chỉ đánh giá tỷ lệ lỗi sau ít nhất 10 lời gọi và mở mạch khi tỷ lệ lỗi đạt ngưỡng 50%. Sau ít nhất 15 giây ở `OPEN`, tối đa ba lời gọi được phép thăm dò trong `HALF_OPEN`.

Với Spring Cloud CircuitBreaker, có thể tạo cấu hình mặc định hoặc cấu hình theo ID bằng `Customizer<Resilience4JCircuitBreakerFactory>`; với reactive dùng `Customizer<ReactiveResilience4JCircuitBreakerFactory>`. Cấu hình properties của Spring Cloud CircuitBreaker có độ ưu tiên cao hơn cấu hình Java `Customizer`. Vì vậy, nếu giá trị đang chạy khác với giá trị trong bean tùy biến, hãy kiểm tra cấu hình properties theo ID và nhóm.

Với Resilience4j trực tiếp, các thuộc tính được binding vào cấu hình Spring Boot của Resilience4j. Có thể dùng các customizer chuyên biệt như `CircuitBreakerConfigCustomizer` để tùy chỉnh instance khi cần. Tránh khai báo nhiều nguồn cấu hình cho cùng một thuộc tính nếu nhóm phát triển không có quy ước rõ ràng về thứ tự ưu tiên.

## 5. Chọn starter theo kiểu ứng dụng

**Chọn Spring Cloud CircuitBreaker** khi ứng dụng đã dùng Spring Cloud, muốn gọi Circuit Breaker qua factory, muốn giữ API ở lớp trừu tượng Spring Cloud hoặc cần khả năng thay implementation theo lựa chọn được hỗ trợ trong release train.

**Chọn Resilience4j Spring Boot trực tiếp** khi ứng dụng muốn dùng annotation `@CircuitBreaker`, registry hoặc các API chuyên biệt của Resilience4j; khi không cần lớp factory trừu tượng của Spring Cloud; hoặc khi muốn cấu hình các module Resilience4j trực tiếp.

**Với ứng dụng reactive**, quyết định theo API mong muốn: Spring Cloud dùng starter `reactor-resilience4j` và `ReactiveCircuitBreakerFactory`; Resilience4j trực tiếp cần module `resilience4j-reactor` để tích hợp Reactor. Kiểm tra cả kiểu trả về của phương thức và cách fallback được viết để tránh chuyển đổi `Mono`/`Flux` sang kiểu đồng bộ ngoài ý muốn.

Không nên bọc cùng một lời gọi bằng một Circuit Breaker Spring Cloud và một Circuit Breaker Resilience4j annotation nếu không có thiết kế rõ ràng. Hai lớp bảo vệ có thể có sliding window, ngưỡng lỗi và trạng thái độc lập, làm số lần gọi bị chặn hoặc fallback khó giải thích. Nếu dự án có lý do dùng cả hai API ở các khu vực khác nhau, quy định rõ mỗi lời gọi do lớp nào sở hữu.

## 6. Actuator, health và metrics

Actuator cung cấp health endpoint và điểm tích hợp cho quan sát ứng dụng. Để xuất metrics Resilience4j qua Micrometer, thêm `spring-boot-starter-actuator` và `resilience4j-micrometer` theo hướng dẫn của phiên bản đang dùng. Với cấu hình `registerHealthIndicator: true`, có thể đưa trạng thái Circuit Breaker vào health information nếu health endpoint được cấu hình phù hợp.

Ví dụ phần dependency metrics:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.github.resilience4j:resilience4j-micrometer'
}
```

Theo dõi ít nhất số lần chuyển `CLOSED`/`OPEN`/`HALF_OPEN`, số lời gọi thành công và thất bại, số lời gọi bị từ chối, số lần fallback và độ trễ của dịch vụ phụ thuộc. Chỉ thấy endpoint health hoạt động chưa đủ để kết luận Circuit Breaker đang bảo vệ đúng; hãy kiểm tra metrics và hành vi lời gọi thực tế.

Không mở các endpoint Actuator chi tiết ra mạng công cộng nếu chưa có cơ chế xác thực và phân quyền phù hợp. Chỉ expose những endpoint cần thiết cho môi trường triển khai.

## 7. Kiểm tra cấu hình sau khi thêm starter

Thực hiện kiểm tra trên một môi trường phát triển hoặc test với dịch vụ phụ thuộc giả lập:

1. Kiểm tra dependency tree để xác nhận chỉ có các starter và phiên bản tương thích với Spring Boot/Spring Cloud đã chọn. Với Spring Cloud, xác nhận BOM quản lý đúng release train; với Resilience4j trực tiếp, xác nhận các module cùng dùng BOM phù hợp.
2. Khởi động ứng dụng và xác nhận Spring tạo được bean factory tương ứng hoặc các bean/registry Resilience4j cần thiết. Nếu dùng annotation, kiểm tra Spring AOP có mặt và phương thức được gọi qua proxy.
3. Cấu hình một instance có ID `inventory`, tạo lỗi có kiểm soát ở dịch vụ giả lập và gửi đủ lời gọi để vượt ngưỡng. Xác nhận mạch chuyển `CLOSED` sang `OPEN`.
4. Gửi lời gọi khi mạch `OPEN`; xác nhận dịch vụ phụ thuộc không nhận thêm request và fallback trả kết quả đúng định dạng.
5. Sau thời gian chờ, gửi các lời gọi thăm dò; xác nhận kết quả phục hồi đưa mạch về `CLOSED`, còn lỗi tiếp tục làm mạch quay lại `OPEN`.
6. Kiểm tra health và metrics nếu đã cấu hình Actuator/Micrometer; xác nhận ID hiển thị đúng với instance trong cấu hình.

## 8. Lỗi cấu hình thường gặp

- Dùng nhầm starter không reactive trong khi mã cần `ReactiveCircuitBreakerFactory`, hoặc thiếu `resilience4j-reactor` khi tích hợp Reactor trực tiếp.
- Trộn Spring Cloud release train với phiên bản Spring Boot không tương thích, hoặc tự pin phiên bản starter khiến dependency tree lệch nhau.
- Khai báo `@CircuitBreaker` nhưng thiếu `spring-boot-starter-aop`, hoặc gọi phương thức qua self-invocation khiến Spring AOP không áp dụng aspect.
- ID trong mã khác ID trong `resilience4j.circuitbreaker.instances`, dẫn đến cấu hình mong muốn không được áp dụng cho instance đang chạy.
- Có nhiều tầng Circuit Breaker bọc cùng một lời gọi khiến trạng thái, fallback và metrics khó theo dõi.
- Cho rằng fallback đã chạy nghĩa là dịch vụ phụ thuộc phục hồi. Fallback chỉ xử lý kết quả của lời gọi được bảo vệ; cần quan sát riêng trạng thái và kết quả lời gọi tới dịch vụ.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker – Spring Cloud Commons](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): API trừu tượng, `CircuitBreakerFactory` và các khái niệm tích hợp.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html): starter reactive/non-reactive, factory, cấu hình properties, customizer và metrics.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): dependency trực tiếp, Actuator, AOP, Reactor và annotation.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): trạng thái, sliding window, ngưỡng lỗi và cấu hình máy trạng thái.
