# @CircuitBreaker của Resilience4j khác API Spring Cloud CircuitBreaker

## Hai cách tích hợp có mục tiêu khác nhau

Trong hệ thống Spring Cloud, tên “Circuit Breaker” có thể chỉ hai API thường được dùng cùng Resilience4j nhưng có cách tích hợp khác nhau:

- `@CircuitBreaker` là annotation của Resilience4j. Spring AOP dùng aspect để chặn lời gọi phương thức, áp dụng Circuit Breaker rồi trả kết quả hoặc gọi fallback.
- `CircuitBreakerFactory` là abstraction lập trình của Spring Cloud Circuit Breaker. Ứng dụng chủ động tạo breaker theo tên và bọc lời gọi bằng `run(...)`.

Cả hai có thể dựa trên Resilience4j để thực thi chính sách bảo vệ, nhưng chúng không phải cùng một API và không tự động thay thế cho nhau. Annotation thuộc tích hợp AOP của Resilience4j; `CircuitBreakerFactory` thuộc abstraction của Spring Cloud. Việc chọn cách nào ảnh hưởng đến dependency, cách cấu hình, vị trí đặt logic và cách kiểm soát luồng gọi.

| Tiêu chí | Resilience4j `@CircuitBreaker` | Spring Cloud `CircuitBreakerFactory` |
| --- | --- | --- |
| Cách sử dụng | Đánh dấu phương thức bằng annotation. | Tạo breaker và gọi `run` trong mã ứng dụng. |
| Cơ chế áp dụng | Spring AOP proxy và aspect của Resilience4j. | Gọi trực tiếp abstraction trong code. |
| Fallback | Phương thức fallback có chữ ký tương thích với phương thức gốc. | Truyền `Function<Throwable, T>` trực tiếp vào `run`. |
| Cấu hình | Instance Resilience4j, thường theo `resilience4j.circuitbreaker.instances`. | Factory và provider của Spring Cloud; với Resilience4j thường tùy chỉnh bằng `Customizer<Resilience4JCircuitBreakerFactory>`. |
| Phụ thuộc provider | Gắn trực tiếp với Resilience4j. | Có thể thay implementation provider mà ít ảnh hưởng mã gọi hơn. |
| Kiểm soát phạm vi | Theo phương thức được aspect chặn. | Theo chính xác đoạn supplier được đưa vào `run`. |

## Resilience4j @CircuitBreaker hoạt động qua Spring AOP

Annotation thường dùng là `io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker`. Khi Spring tạo bean, aspect của Resilience4j áp dụng interceptor cho phương thức được đánh dấu. Lời gọi đi qua proxy sẽ được bao quanh bởi Circuit Breaker có tên trong thuộc tính `name`.

Ví dụ:

```java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public Inventory find(String sku) {
        return inventoryClient.fetch(sku);
    }

    private Inventory inventoryFallback(String sku, Throwable cause) {
        return Inventory.unknown(sku);
    }
}
```

`name = "inventory"` là tên instance Circuit Breaker. Khi lời gọi phương thức đi qua proxy, aspect áp dụng breaker tương ứng. Nếu supplier thất bại hoặc breaker từ chối lời gọi, fallback phù hợp có thể được gọi. `Inventory` và `InventoryClient` là các kiểu do ứng dụng định nghĩa; `Inventory.unknown` cần thể hiện trạng thái chưa xác định, không được giả làm kết quả tồn kho bằng 0 hoặc khẳng định hết hàng.

### Chữ ký fallback

Phương thức fallback cần có kiểu trả về tương thích với phương thức gốc, nhận các tham số nghiệp vụ theo cùng thứ tự, sau đó có thể nhận thêm tham số ngoại lệ ở cuối. Ví dụ trên dùng `Throwable` để minh họa. Có thể khai báo kiểu ngoại lệ cụ thể nếu muốn xử lý riêng một nhóm lỗi.

```java
@CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
public Inventory find(String sku) {
    return inventoryClient.fetch(sku);
}

private Inventory inventoryFallback(String sku, CallNotPermittedException cause) {
    return Inventory.temporarilyUnavailable(sku);
}

private Inventory inventoryFallback(String sku, Throwable cause) {
    return Inventory.unknown(sku);
}
```

Khi có nhiều overload fallback, Resilience4j tìm phương thức phù hợp với loại exception và các tham số của phương thức gốc. Cần tránh các overload mơ hồ và xác nhận chữ ký với phiên bản thư viện đang dùng. Nếu không tìm thấy fallback tương thích, lời gọi có thể kết thúc bằng lỗi cấu hình fallback thay vì kết quả dự phòng mong muốn.

Fallback là xử lý lỗi cho caller, còn quy tắc `recordException` và `ignoreException` quyết định lỗi có được tính vào thống kê Circuit Breaker hay không. Một exception bị bỏ qua trong thống kê vẫn có thể được truyền đến fallback hoặc caller; việc bỏ qua không đồng nghĩa nuốt exception.

## Điều kiện để annotation được áp dụng

Vì annotation sử dụng Spring AOP, cần bảo đảm tích hợp AOP được đưa vào ứng dụng. Thông thường, ứng dụng dùng module Spring Boot của Resilience4j tương thích với phiên bản Spring Boot và có Spring AOP trên classpath. Ví dụ tên artifact thường gặp là `resilience4j-spring-boot3` cho Spring Boot 3; ứng dụng Spring Boot 2 dùng dòng artifact tương ứng của phiên bản Resilience4j hỗ trợ Boot 2. Kiểm tra tài liệu và dependency management của đúng phiên bản thay vì trộn các dòng không tương thích.

Các điều kiện thực tế cần kiểm tra:

- Có Resilience4j Spring Boot integration và aspect tương ứng trên runtime classpath.
- Spring AOP được cấu hình đúng; nếu starter không kéo theo AOP cần thiết, bổ sung dependency AOP tương thích.
- Bean được Spring quản lý, và lời gọi đến phương thức được thực hiện qua proxy.
- Tên trong `@CircuitBreaker(name = "inventory")` khớp instance cấu hình.
- Không có cấu hình loại trừ hoặc tự tạo bean khiến aspect không được kích hoạt.

Spring AOP mặc định dựa trên proxy. Lời gọi nội bộ trong cùng object như `this.find(sku)` không đi qua proxy nên có thể bỏ qua aspect. Ví dụ:

```java
public Inventory load(String sku) {
    // Lời gọi nội bộ này có thể không đi qua Spring proxy.
    return this.find(sku);
}
```

Nếu cần áp dụng interceptor, hãy gọi phương thức được bảo vệ qua một bean Spring khác hoặc thiết kế lại ranh giới service để lời gọi đi qua proxy. Tránh tự lấy proxy hoặc dùng cơ chế vòng vo khi chỉ cần tách trách nhiệm giữa hai bean.

## Cấu hình instance cho annotation Resilience4j

Có thể cấu hình instance theo tên trong `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
```

Trong ví dụ, Circuit Breaker giữ tối đa 20 kết quả gần nhất và bắt đầu đánh giá khi có ít nhất 10 lời gọi được ghi nhận. Khi failure rate đạt hoặc vượt 50%, breaker có thể chuyển sang `OPEN`. Sau khoảng chờ cấu hình, nó có thể chuyển sang `HALF_OPEN` để thử một số lời gọi theo chính sách.

Tên `inventory` trong YAML phải khớp với `name` của annotation. Các thuộc tính này là cấu hình của Resilience4j; cần bảo đảm Spring Boot integration đang nạp đúng file cấu hình và phiên bản hỗ trợ các property đã chọn.

## Spring Cloud CircuitBreaker dùng factory theo cách lập trình

Spring Cloud Circuit Breaker cung cấp abstraction `CircuitBreakerFactory`. Ứng dụng inject factory và bọc đúng lời gọi cần bảo vệ:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogClient catalogClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogService(
            CatalogClient catalogClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogClient = catalogClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public CatalogItem find(String productId) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(productId),
            error -> CatalogItem.unavailable(productId)
        );
    }
}
```

Ở đây, `create("catalog")` tạo breaker có định danh `catalog`. Supplier chỉ chứa lời gọi đến dependency; fallback được truyền ngay tại chỗ dưới dạng hàm nhận `Throwable`. Cách này không cần đánh dấu phương thức bằng annotation và không phụ thuộc vào việc lời gọi nội bộ có đi qua AOP proxy hay không.

Vì fallback nằm cạnh supplier, người đọc dễ thấy đoạn mã nào được bảo vệ và kết quả thay thế là gì. Đổi lại, nếu có nhiều lời gọi cần chính sách tương tự, ứng dụng có thể lặp lại đoạn `run` hoặc cần một helper để tránh trùng lặp. Hãy giữ phạm vi supplier chính xác: validation, xử lý dữ liệu cục bộ hoặc các bước không thuộc dependency không nhất thiết phải nằm bên trong Circuit Breaker.

## Tùy chỉnh factory khi dùng Resilience4j provider

Nếu ứng dụng dùng starter Resilience4j cho Spring Cloud Circuit Breaker, có thể tùy chỉnh factory do starter tạo bằng `Customizer`:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(
                    CircuitBreakerConfig.custom()
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .build()
                )
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .build()
                )
                .build()
        );
    }
}
```

Customizer này áp dụng cấu hình mặc định cho các ID mà factory tạo. `CircuitBreakerConfig` điều khiển sliding window và failure rate; `TimeLimiterConfig` điều khiển giới hạn thời gian chờ trong tích hợp tương ứng. Hai cơ chế có vai trò riêng. Tên lớp builder và package cần khớp với phiên bản Spring Cloud Circuit Breaker Resilience4j đang dùng.

Factory cũng có API cấu hình riêng theo ID trong các phiên bản hỗ trợ. Khi một dependency cần chính sách riêng, hãy cấu hình theo tên thay vì vô tình thay đổi mọi breaker bằng một default chung. Đừng giả định cấu hình YAML dành cho Resilience4j annotation và cấu hình Customizer của factory luôn được áp dụng giống nhau; xác nhận hành vi của provider trong phiên bản dự án.

## Reactive: factory và annotation cần đúng loại API

Với WebFlux và Reactor, Spring Cloud Circuit Breaker có `ReactiveCircuitBreakerFactory`. Ví dụ:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<CatalogItem> findReactive(String productId) {
    Mono<CatalogItem> primary = webClient.get()
        .uri("/catalog/{id}", productId)
        .retrieve()
        .bodyToMono(CatalogItem.class);

    return reactiveCircuitBreakerFactory.create("catalog").run(
        primary,
        error -> Mono.just(CatalogItem.unavailable(productId))
    );
}
```

Reactive factory nhận publisher và fallback publisher. Pipeline được subscribe mới thực thi lời gọi; không dùng `block()` để lấy kết quả trong event-loop. Với annotation Resilience4j, hỗ trợ reactive phụ thuộc vào module Reactor và cách aspect của phiên bản đang dùng tích hợp với publisher. Không suy ra rằng annotation đồng bộ và reactive factory là một API. Khi chọn annotation cho `Mono` hoặc `Flux`, hãy xác nhận tài liệu đúng phiên bản và kiểm thử subscription, cancellation, fallback cùng metrics.

## Có nên đặt cả annotation và factory trên cùng lời gọi?

Thông thường, không nên bọc cùng một lời gọi bằng cả `@CircuitBreaker` và `CircuitBreakerFactory` nếu không có mục đích rõ ràng. Nếu một phương thức được aspect bảo vệ rồi bên trong lại gọi factory cho cùng dependency, request có thể đi qua hai Circuit Breaker độc lập hoặc lồng nhau. Điều này làm số liệu, ngưỡng mở mạch và fallback khó giải thích.

Ví dụ cần tránh:

```java
@CircuitBreaker(name = "inventory")
public Inventory find(String sku) {
    return circuitBreakerFactory.create("inventory").run(
        () -> inventoryClient.fetch(sku),
        error -> Inventory.unknown(sku)
    );
}
```

Trong đoạn mã này, cả aspect bên ngoài và factory bên trong có thể cùng quản lý một dependency. Chọn một điểm áp dụng chính sách cho mỗi lời gọi. Nếu cần nhiều decorator như Retry, RateLimiter, Bulkhead và Circuit Breaker, hãy xác định thứ tự và trách nhiệm từng lớp, đồng thời theo dõi riêng số lần retry và số lần gọi thực tế đến dependency.

## Chọn cách nào cho ứng dụng?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Muốn bảo vệ nhanh một phương thức service và chấp nhận cơ chế AOP | Resilience4j `@CircuitBreaker`. |
| Muốn thấy rõ supplier và fallback ngay tại đoạn gọi | Spring Cloud `CircuitBreakerFactory.run`. |
| Muốn giữ mã nghiệp vụ ít phụ thuộc trực tiếp Resilience4j và dùng abstraction Spring Cloud | `CircuitBreakerFactory` với provider được cấu hình. |
| Muốn dùng một API tạo breaker cho publisher Reactor | `ReactiveCircuitBreakerFactory`. |
| Cần thay provider hoặc thống nhất cách gọi giữa nhiều implementation | Spring Cloud Circuit Breaker abstraction. |
| Cần dùng trực tiếp registry, aspect và tính năng riêng của Resilience4j | Resilience4j Spring Boot integration và annotation. |

Lựa chọn nên nhất quán trong từng ranh giới service. Annotation có thể gọn khi chính sách gắn tự nhiên với phương thức; factory phù hợp khi muốn quyết định rõ đoạn supplier, fallback hoặc provider trong code. Cả hai vẫn cần timeout, phân loại exception, fallback đúng ngữ nghĩa và metrics phù hợp.

## Kiểm tra tích hợp và các lỗi thường gặp

Khi annotation không hoạt động, kiểm tra dependency AOP, bean proxy, lời gọi nội bộ, tên instance và fallback signature. Khi factory không được inject, kiểm tra starter Spring Cloud Circuit Breaker, provider được chọn và auto-configuration. Khi reactive fallback không chạy, kiểm tra publisher có được subscribe và đúng kiểu factory reactive có được dùng.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `@CircuitBreaker` không mở mạch | Aspect không được nạp hoặc lời gọi bỏ qua proxy. | Kiểm tra AOP dependency, bean Spring và self-invocation. |
| Không tìm thấy fallback | Sai tên, sai tham số, kiểu trả về hoặc exception overload. | Đối chiếu chữ ký fallback với phương thức gốc. |
| Không inject được `CircuitBreakerFactory` | Thiếu starter/provider hoặc auto-configuration không khớp. | Kiểm tra runtime dependency và condition report. |
| Factory dùng ngưỡng khác mong đợi | Customizer hoặc cấu hình theo ID không áp dụng như dự kiến. | Xác nhận ID, thứ tự customizer và cấu hình của phiên bản. |
| Hai lần fallback hoặc metrics khó hiểu | Cùng lời gọi bị bọc nhiều lần. | Xác định một nơi sở hữu Circuit Breaker cho lời gọi đó. |
| Reactive request không chạy | Publisher chưa được subscribe hoặc pipeline bị block sai chỗ. | Kiểm tra subscription và không gọi `block()` trên event-loop. |

Khi kiểm thử, tạo các trường hợp thành công, timeout, lỗi server và Circuit Breaker đang `OPEN`. Quan sát cả response cuối cùng, fallback invocation, trạng thái breaker và metrics của dependency. Một fallback trả response hợp lệ không có nghĩa lời gọi chính thành công.

## Ghi nhớ

`@CircuitBreaker` của Resilience4j là cách khai báo chính sách bằng annotation và Spring AOP. `CircuitBreakerFactory` của Spring Cloud là cách lập trình, tạo breaker và bọc supplier bằng `run`. Chúng có thể dùng cùng provider Resilience4j nhưng thuộc hai lớp tích hợp khác nhau. Hiểu rõ ranh giới này giúp chọn đúng dependency, cấu hình đúng instance, tránh bọc trùng và giữ fallback cùng số liệu vận hành dễ giải thích.
