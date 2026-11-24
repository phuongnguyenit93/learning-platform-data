# Phân biệt lớp bao Spring Cloud với CircuitBreaker gốc của Resilience4j

Trong ứng dụng Spring Cloud, có hai cách phổ biến để gọi circuit breaker do Resilience4j cung cấp. Cách thứ nhất dùng **Spring Cloud CircuitBreaker** làm lớp API thống nhất, sau đó chọn Resilience4j làm implementation. Cách thứ hai gọi trực tiếp API của **Resilience4j**, thông qua `CircuitBreaker`, `CircuitBreakerRegistry`, decorator hoặc annotation của thư viện.

Cả hai cách đều có thể bảo vệ lời gọi đến cùng một dịch vụ và sử dụng các khái niệm như `CLOSED`, `OPEN`, `HALF_OPEN`, failure rate, slow-call rate và sliding window. Điểm khác nhau nằm ở lớp API mà mã ứng dụng phụ thuộc, cách tạo và quản lý instance, cách gắn fallback, cũng như mức độ kiểm soát chi tiết mà ứng dụng cần. Chọn một cách rõ ràng cho từng ranh giới lời gọi giúp tránh vô tình tạo hai circuit breaker độc lập hoặc bọc cùng một lời gọi nhiều lần.

## 1. Hai lớp nằm ở đâu trong kiến trúc?

Spring Cloud CircuitBreaker cung cấp abstraction để ứng dụng gọi circuit breaker mà ít phụ thuộc vào thư viện cụ thể. Ứng dụng làm việc với các API như `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`. Spring Cloud chọn backend tương ứng, ví dụ Resilience4j, để thực thi cơ chế bảo vệ.

Resilience4j là thư viện cung cấp trực tiếp các thành phần bảo vệ. API gốc của circuit breaker nằm trong package `io.github.resilience4j.circuitbreaker`, gồm `CircuitBreaker`, `CircuitBreakerConfig` và `CircuitBreakerRegistry`. Thư viện còn có tích hợp Spring Boot, annotation, Reactor và các module như Retry, RateLimiter, Bulkhead, TimeLimiter.

```text
Mã nghiệp vụ
    |
    +-- Spring Cloud CircuitBreaker API
    |       CircuitBreakerFactory / ReactiveCircuitBreakerFactory
    |                    |
    |                    v
    |          Resilience4j implementation
    |                    |
    +-- Resilience4j native API
            CircuitBreaker / Registry / Decorators
                         |
                         v
                Dịch vụ phụ thuộc
```

Sơ đồ cho thấy hai đường truy cập khác nhau tới cơ chế Resilience4j. Khi dùng Spring Cloud abstraction, mã nghiệp vụ gọi qua lớp Spring Cloud. Khi dùng API gốc, mã nghiệp vụ thao tác trực tiếp với đối tượng Resilience4j. Không cần tạo thêm một circuit breaker native bên ngoài chỉ để dùng được Resilience4j nếu Spring Cloud đã cấu hình backend này cho lời gọi.

## 2. So sánh API và trách nhiệm

| Tiêu chí | Spring Cloud CircuitBreaker | Resilience4j gốc |
| --- | --- | --- |
| API chính | `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` | `CircuitBreaker`, `CircuitBreakerRegistry`, `CircuitBreakerConfig` |
| Mức phụ thuộc | Phụ thuộc abstraction của Spring Cloud; có thể thay backend với thay đổi mã ứng dụng ít hơn | Phụ thuộc trực tiếp API và kiểu dữ liệu của Resilience4j |
| Tạo instance | Gọi `factory.create("inventory")` | Lấy instance từ `CircuitBreakerRegistry` hoặc tạo theo cấu hình |
| Fallback | Thường truyền hàm fallback trực tiếp vào `run(...)` | Tự xử lý bằng `try/catch`, decorator, annotation fallback hoặc cơ chế ứng dụng |
| Tùy chỉnh sâu | Dùng cấu hình Spring Cloud và customizer của backend | Có thể cấu hình trực tiếp, lắng nghe event, dùng decorator và truy cập registry |
| Reactive | Dùng `ReactiveCircuitBreakerFactory` | Dùng module Reactor và `CircuitBreakerOperator`, hoặc tích hợp native tương ứng |
| Phù hợp khi | Muốn API thống nhất trong hệ sinh thái Spring Cloud | Cần kiểm soát trực tiếp Resilience4j hoặc dùng thư viện ngoài Spring Cloud |

Spring Cloud CircuitBreaker không thay thế engine Resilience4j trong cấu hình này; nó cung cấp lớp gọi và tích hợp backend. Resilience4j gốc cũng không tự động trở thành Spring Cloud abstraction chỉ vì ứng dụng có dependency Resilience4j. Hai API có kiểu đối tượng khác nhau, dù backend có thể là cùng một thư viện.

## 3. Dùng Spring Cloud CircuitBreaker với backend Resilience4j

Với ứng dụng Spring Cloud, thêm starter Resilience4j tương ứng và quản lý phiên bản Spring Cloud bằng BOM tương thích với phiên bản Spring Boot của dự án:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

Nếu ứng dụng dùng API reactive, sử dụng starter reactive Resilience4j tương ứng:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

Không tự chọn một phiên bản starter tùy ý; hãy dùng Spring Cloud release train tương thích với Spring Boot và để dependency management quản lý các phiên bản liên quan.

### Tạo và gọi circuit breaker qua factory

Spring Cloud cung cấp `CircuitBreakerFactory`. Tên instance truyền vào `create(...)` phải khớp với tên trong cấu hình Resilience4j:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

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

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

`create("inventory")` yêu cầu factory cung cấp circuit breaker có ID `inventory`. Hàm thứ nhất thực hiện lời gọi đến dịch vụ kho hàng. Hàm thứ hai là fallback, được gọi khi tác vụ lỗi hoặc circuit breaker không cho phép lời gọi đi tiếp do đang `OPEN`. Ví dụ dùng kết quả dự phòng để biểu diễn trạng thái chưa lấy được dữ liệu; ứng dụng thực tế cần định nghĩa rõ dữ liệu đó có được phép dùng cho nghiệp vụ hay không.

### Cấu hình instance cho backend

Backend Resilience4j đọc cấu hình theo ID instance. Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

`minimumNumberOfCalls` đặt số mẫu tối thiểu trước khi đánh giá. `failureRateThreshold` và `slowCallRateThreshold` là hai ngưỡng có thể làm circuit breaker chuyển từ `CLOSED` sang `OPEN`. `waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState` điều khiển giai đoạn thử phục hồi. Các thuộc tính này thuộc cấu hình của backend Resilience4j; Spring Cloud abstraction không làm thay đổi ý nghĩa của chúng.

### Tùy chỉnh backend

Khi cần áp dụng cấu hình mặc định hoặc tùy chỉnh theo ID, Spring Cloud CircuitBreaker cho phép cấu hình factory bằng customizer. Ví dụ sau minh họa cách đặt cấu hình mặc định cho các ID chưa có cấu hình riêng:

```java
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(
                    io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
                        .custom()
                        .failureRateThreshold(50)
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .build()
                )
                .build()
        );
    }
}
```

Đây là cách tùy chỉnh ở lớp Spring Cloud factory. Trong dự án thực tế, nên chọn một nguồn cấu hình có chủ đích, chẳng hạn YAML theo môi trường hoặc customizer theo ID, và tránh để nhiều nguồn cùng ghi đè một thuộc tính mà không có quy ước rõ ràng. Nếu cần cấu hình riêng cho một instance, dùng cấu hình theo ID hoặc `configure(...)` phù hợp thay vì thay đổi mặc định cho tất cả instance.

## 4. Dùng trực tiếp CircuitBreaker và Registry của Resilience4j

Khi cần thao tác với API gốc, ứng dụng lấy circuit breaker từ `CircuitBreakerRegistry`. Registry quản lý các instance theo tên và cho phép dùng lại chúng trong các thành phần cần cùng một trạng thái bảo vệ.

Ví dụ tạo registry với cấu hình lập trình trong ứng dụng Java thuần:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;

import java.time.Duration;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .slowCallDurationThreshold(Duration.ofSeconds(2))
    .slowCallRateThreshold(60)
    .waitDurationInOpenState(Duration.ofSeconds(15))
    .build();

CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(config);
CircuitBreaker inventoryBreaker = registry.circuitBreaker("inventory");
```

Registry và breaker nên được tạo một lần ở phạm vi ứng dụng rồi tiêm vào các service cần dùng. Không tạo registry mới cho từng request hoặc từng lần gọi phương thức; mỗi registry có thể quản lý một nhóm instance riêng, khiến trạng thái và số liệu bị phân tán.

Trong ứng dụng Java thuần, module cốt lõi cần dùng là `io.github.resilience4j:resilience4j-circuitbreaker`. Nếu dùng Spring Boot để bind cấu hình YAML và dùng annotation, hãy chọn starter `resilience4j-spring-boot3` hoặc starter tương ứng với phiên bản Spring Boot của dự án.

### Bọc lời gọi bằng API gốc

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

public InventoryResult getInventory(
        String sku,
        CircuitBreaker inventoryBreaker,
        InventoryClient inventoryClient) {
    try {
        return inventoryBreaker.executeSupplier(
            () -> inventoryClient.fetch(sku)
        );
    } catch (CallNotPermittedException ex) {
        // Circuit breaker đang OPEN và từ chối lời gọi mới.
        return InventoryResult.unavailable(sku);
    }
}
```

`executeSupplier(...)` thực thi tác vụ trong phạm vi circuit breaker và ghi nhận kết quả theo cấu hình. `CallNotPermittedException` cho biết breaker từ chối lời gọi vì đang ở trạng thái không cho phép. Ví dụ chỉ fallback cho trường hợp bị từ chối; exception từ dịch vụ phụ thuộc vẫn được truyền ra ngoài. Nếu muốn fallback cho cả lỗi từ dịch vụ, hãy xử lý nhóm exception đó theo chính sách nghiệp vụ riêng, tránh vô tình che giấu lỗi lập trình hoặc lỗi dữ liệu.

Có thể dùng decorator thay cho `executeSupplier(...)` khi cần kết hợp nhiều cơ chế:

```java
import java.util.function.Supplier;

Supplier<InventoryResult> inventoryCall =
    CircuitBreaker.decorateSupplier(
        inventoryBreaker,
        () -> inventoryClient.fetch(sku)
    );

InventoryResult result = inventoryCall.get();
```

Decorator trả về một `Supplier` đã được bọc bởi circuit breaker. Có thể kết hợp decorator của Retry, Bulkhead hoặc RateLimiter theo thứ tự phù hợp. Thứ tự bọc ảnh hưởng đến việc cơ chế nào quan sát kết quả và thời gian của cơ chế nào; hãy xác định rõ mục tiêu trước khi ghép nhiều decorator.

## 5. Annotation gốc của Resilience4j trong Spring Boot

Resilience4j cung cấp annotation `@CircuitBreaker` thông qua tích hợp Spring Boot. Đây là annotation của Resilience4j, không phải API factory của Spring Cloud CircuitBreaker. Nó thường được triển khai bằng Spring AOP, vì vậy phương thức được gọi qua Spring proxy mới được áp dụng advice; lời gọi nội bộ bằng `this.someMethod()` có thể bỏ qua proxy.

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
    public InventoryResult getInventory(String sku) {
        return inventoryClient.fetch(sku);
    }

    private InventoryResult inventoryFallback(String sku, Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
```

Fallback của annotation cần có các tham số nghiệp vụ tương ứng với phương thức gốc và thêm một tham số exception ở cuối. Resilience4j tìm phương thức fallback tương thích với chữ ký và kiểu exception. Trong ví dụ, `Throwable` là kiểu tổng quát; có thể dùng kiểu exception cụ thể để áp dụng chính sách khác nhau cho lỗi bị từ chối, timeout hoặc lỗi dịch vụ.

Để dùng annotation, ứng dụng cần starter Spring Boot Resilience4j phù hợp với phiên bản Spring Boot và AOP được cấu hình theo hướng dẫn của phiên bản đó. Chẳng hạn, Spring Boot 3 dùng starter `resilience4j-spring-boot3`; Spring Boot 2 dùng starter tương ứng cho Boot 2. Nếu chỉ dùng Spring Cloud CircuitBreaker factory, không cần thêm annotation chỉ để có fallback vì API `run(...)` đã nhận hàm fallback.

Ví dụ dependency cho ứng dụng Spring Boot 3 dùng annotation native:

```xml
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-spring-boot3</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Hãy quản lý phiên bản Resilience4j bằng dependency management của dự án và dùng artifact tương ứng với phiên bản Spring Boot; không trộn starter Boot 2 với ứng dụng Boot 3.

## 6. Lời gọi reactive: abstraction và API gốc

Với `Mono` hoặc `Flux`, Spring Cloud cung cấp `ReactiveCircuitBreakerFactory`. Ví dụ:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> getInventory(String sku) {
    return reactiveCircuitBreakerFactory.create("inventory").run(
        inventoryClient.fetch(sku),
        error -> Mono.just(InventoryResult.unavailable(sku))
    );
}
```

Nếu dùng Resilience4j native với Reactor, thêm module tích hợp Reactor và áp dụng `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> getInventory(
        String sku,
        CircuitBreaker inventoryBreaker) {
    return inventoryClient.fetch(sku)
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            io.github.resilience4j.circuitbreaker.CallNotPermittedException.class,
            error -> Mono.just(InventoryResult.unavailable(sku))
        );
}
```

`transformDeferred(...)` áp dụng operator khi subscription diễn ra, phù hợp với cách thực thi lazy của Reactor. `onErrorResume(...)` trong ví dụ chỉ xử lý trường hợp circuit breaker từ chối lời gọi; nếu cần fallback cho lỗi từ dịch vụ phụ thuộc, hãy thêm nhánh xử lý tương ứng và giữ nguyên thông tin nguyên nhân để quan sát. Không gọi `block()` trong luồng reactive chỉ để dùng API đồng bộ vì thao tác đó có thể chặn event loop.

## 7. Cấu hình và chia sẻ trạng thái đúng cách

Khi dùng Spring Cloud CircuitBreaker, cấu hình instance theo ID mà factory tạo. Khi dùng Resilience4j Spring Boot starter, cấu hình cũng có thể được bind vào registry do integration quản lý. Ví dụ cấu hình YAML có thể được dùng làm nền cho instance `inventory`:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
    instances:
      inventory:
        baseConfig: default
```

Nếu dùng Spring Boot starter và muốn YAML được áp dụng, hãy inject registry đã được Spring cấu hình. Không tự tạo `CircuitBreakerRegistry.ofDefaults()` rồi kỳ vọng nó tự nhận các thuộc tính YAML; registry được tạo thủ công với cấu hình mặc định không tự động kế thừa cấu hình do một bean khác quản lý.

Một điểm dễ nhầm là hai breaker có cùng tên chưa chắc đã chia sẻ cùng trạng thái. Nếu Spring Cloud factory quản lý một instance còn ứng dụng tự tạo một registry độc lập rồi lấy thêm `inventory`, đó có thể là hai đối tượng khác nhau. Chúng có bộ đếm, trạng thái và metric riêng. Nếu chủ đích là dùng chung một trạng thái, hãy thống nhất nơi tạo instance và tiêm cùng đối tượng hoặc dùng đúng registry/backend được integration quản lý.

Tránh bọc cùng một lời gọi đồng thời bằng Spring Cloud circuit breaker, annotation native và một decorator native khác nếu không có chủ đích. Khi đó một lỗi có thể được ghi nhận nhiều lần ở các breaker khác nhau; fallback ngoài có thể che trạng thái từ breaker trong; metric cũng khó giải thích. Thông thường, chọn một cơ chế ở ranh giới gọi dịch vụ và đặt tên instance mô tả rõ dependency được bảo vệ.

## 8. Theo dõi, kiểm thử và lựa chọn cách tích hợp

Hai cách truy cập có thể cung cấp số liệu và sự kiện của Resilience4j khi backend được cấu hình tương ứng. Dùng Micrometer và hệ thống giám sát để theo dõi trạng thái, số lời gọi thành công, thất bại, chậm và bị từ chối. Khi dùng Spring Cloud abstraction, xác minh ID mà factory tạo đúng với ID cấu hình. Khi dùng native API, xác minh service nhận đúng instance từ registry dự kiến.

Kiểm thử nên xác nhận ít nhất ba hành vi: lời gọi được thực hiện khi breaker `CLOSED`; lời gọi mới bị từ chối khi breaker `OPEN`; và fallback hoặc xử lý lỗi trả về kết quả theo chính sách khi bị từ chối. Với API native, có thể dùng `CircuitBreakerRegistry` để lấy breaker và kiểm tra trạng thái. Với Spring Cloud abstraction, kiểm thử qua service đang dùng factory để xác minh cả wiring và fallback. Đặt cửa sổ và số mẫu nhỏ trong profile test để tạo kết quả xác định, đồng thời reset hoặc tạo instance mới giữa các bài kiểm thử để trạng thái không rò sang test khác.

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng Spring Cloud cần API ít phụ thuộc implementation | Spring Cloud CircuitBreaker với Resilience4j backend |
| Muốn đổi backend hoặc giữ abstraction ở tầng nghiệp vụ | Spring Cloud CircuitBreaker |
| Cần truy cập trực tiếp registry, event, config và decorator | Resilience4j native API |
| Dùng annotation `@CircuitBreaker` và fallback theo method | Resilience4j Spring Boot integration |
| Dùng Reactor với abstraction của Spring Cloud | `ReactiveCircuitBreakerFactory` |
| Dùng Reactor trực tiếp với breaker native | `CircuitBreakerOperator` từ module Reactor |

Hãy ưu tiên Spring Cloud CircuitBreaker khi ứng dụng muốn giữ ranh giới phụ thuộc ở abstraction của Spring Cloud và chỉ cần các thao tác gọi, fallback, cấu hình theo ID. Chọn API gốc của Resilience4j khi cần thao tác sâu với registry, event, decorator hoặc annotation của thư viện. Dù chọn cách nào, cần quản lý instance tập trung, dùng cấu hình nhất quán, xác định fallback theo nghiệp vụ và theo dõi trạng thái thực tế. Như vậy circuit breaker bảo vệ đúng lời gọi phụ thuộc mà không tạo thêm trạng thái khó kiểm soát trong ứng dụng Spring Cloud.
