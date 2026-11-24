# Tính năng đặc thù cần truy cập API của nhà cung cấp

Spring Cloud CircuitBreaker cung cấp một API chung để ứng dụng gọi dịch vụ qua Circuit Breaker mà không phụ thuộc trực tiếp vào thư viện triển khai. Với API chung, mã nghiệp vụ có thể tạo mạch qua `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`, gọi `run(...)` và cung cấp fallback. Cách này giúp thay đổi backend ít ảnh hưởng đến phần gọi dịch vụ.

Tuy nhiên, API chung chỉ biểu diễn những khả năng được chuẩn hóa giữa các backend. Khi cần tính năng riêng của Resilience4j, chẳng hạn đăng ký event listener ở mức native, đọc metrics chi tiết, phân loại exception bằng predicate hoặc điều chỉnh một thành phần chuyên biệt, ứng dụng có thể truy cập API của Resilience4j thông qua các điểm mở rộng của Spring Cloud CircuitBreaker.

## Khi nào nên dùng API chung và khi nào cần API native?

Hãy dùng API chung cho luồng gọi dịch vụ thông thường: tạo Circuit Breaker theo tên, thực thi supplier hoặc publisher, xử lý fallback và giữ mã nghiệp vụ độc lập với nhà cung cấp.

API native phù hợp khi yêu cầu cần một khả năng cụ thể của backend. Ví dụ:

- Đăng ký listener cho sự kiện chuyển trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`.
- Đọc các số liệu chi tiết như số lời gọi thành công, thất bại, chậm hoặc bị từ chối.
- Dùng predicate của Resilience4j để quyết định exception nào được ghi nhận là lỗi và exception nào được bỏ qua.
- Cấu hình thành phần riêng của Resilience4j mà abstraction chung không cung cấp.
- Tích hợp sự kiện hoặc metrics của Resilience4j với hệ thống quan sát hiện có.

API native tạo ra sự phụ thuộc trực tiếp vào nhà cung cấp. Nếu sau này chuyển sang backend khác, những đoạn mã dùng `Resilience4JCircuitBreakerFactory`, `CircuitBreakerRegistry` hoặc các kiểu `io.github.resilience4j.*` cần được xem xét và thay thế. Vì vậy, hãy giữ phần tích hợp native trong lớp cấu hình hoặc adapter nhỏ, để mã nghiệp vụ tiếp tục sử dụng API chung.

## Điểm mở rộng của Spring Cloud CircuitBreaker cho Resilience4j

Khi dùng backend Resilience4j, Spring Cloud CircuitBreaker cung cấp `Resilience4JCircuitBreakerFactory` cho ứng dụng đồng bộ và `ReactiveResilience4JCircuitBreakerFactory` cho ứng dụng reactive. Có thể đăng ký một bean `Customizer` để cấu hình factory hoặc tùy chỉnh Circuit Breaker native sau khi nó được tạo nhưng trước khi factory trả về cho bên gọi.

Ứng dụng đồng bộ dùng starter `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j`; ứng dụng reactive dùng `org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j`. Nên quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án thay vì tự chọn phiên bản riêng cho từng thư viện.

Phương thức `addCircuitBreakerCustomizer(...)` là điểm mở rộng hữu ích để đăng ký event listener. Callback nhận đối tượng Circuit Breaker của Resilience4j, vì vậy có thể gọi trực tiếp `getEventPublisher()`.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryCircuitBreakerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryCircuitBreakerConfiguration.class);

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEvents() {
        return factory -> factory.addCircuitBreakerCustomizer(circuitBreaker ->
            circuitBreaker.getEventPublisher()
                .onStateTransition(event -> log.info(
                    "Circuit Breaker {} chuyển trạng thái: {}",
                    event.getCircuitBreakerName(), event.getStateTransition()))
                .onError(event -> log.warn(
                    "Circuit Breaker {} ghi nhận lỗi: {}",
                    event.getCircuitBreakerName(), event.getThrowable()))
                .onCallNotPermitted(event -> log.debug(
                    "Circuit Breaker {} từ chối lời gọi",
                    event.getCircuitBreakerName())),
            "inventory");
    }
}
```

Customizer trên chỉ áp dụng cho Circuit Breaker có id `inventory`. Khi factory tạo mạch này, listener được gắn vào event publisher của đối tượng Resilience4j. Các sự kiện chuyển trạng thái, lỗi được ghi nhận và lời gọi bị từ chối có thể được đưa vào log hoặc chuyển tiếp đến hệ thống quan sát.

Không đăng ký listener trong mỗi lần gọi dịch vụ. Hãy đăng ký ở thời điểm cấu hình ứng dụng hoặc khi Circuit Breaker được tạo. Nếu một cơ chế tùy chỉnh được gọi lặp lại theo từng lần `run(...)`, việc thêm listener nhiều lần có thể làm log trùng lặp và tăng chi phí xử lý.

Trong trường hợp đang tùy chỉnh trực tiếp các đối tượng Circuit Breaker native qua `Customizer` chung và callback có thể được gọi nhiều lần, Spring Cloud Commons cung cấp `Customizer.once(...)` để chỉ áp dụng callback một lần cho mỗi khóa. Với Resilience4j, có thể dùng tên Circuit Breaker làm khóa:

```java
Customizer.once(
    circuitBreaker -> circuitBreaker.getEventPublisher()
        .onStateTransition(event -> log.info(
            "{}: {}", event.getCircuitBreakerName(), event.getStateTransition())),
    io.github.resilience4j.circuitbreaker.CircuitBreaker::getName);
```

Đăng ký theo tên giúp tránh thêm cùng một event listener nhiều lần cho một mạch. Với cấu hình factory ở ví dụ trước, `addCircuitBreakerCustomizer(...)` vẫn là điểm mở rộng trực tiếp và dễ đọc.

Với ứng dụng reactive, dùng factory reactive tương ứng. Cách đăng ký event listener vẫn tương tự:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.ReactiveResilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ReactiveInventoryCircuitBreakerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ReactiveInventoryCircuitBreakerConfiguration.class);

@Bean
Customizer<ReactiveResilience4JCircuitBreakerFactory> reactiveInventoryEvents() {
    return factory -> factory.addCircuitBreakerCustomizer(circuitBreaker ->
        circuitBreaker.getEventPublisher()
            .onStateTransition(event -> log.info(
                "Reactive Circuit Breaker {}: {}",
                event.getCircuitBreakerName(), event.getStateTransition())),
        "inventory-reactive");
}
}
```

Factory reactive vẫn trả về abstraction reactive cho mã gọi dịch vụ; callback tùy chỉnh chỉ là nơi tích hợp event API native của Resilience4j.

## Cấu hình native khi cần chính sách riêng

`configure(...)` cho phép đặt cấu hình riêng cho một hoặc nhiều id. Ví dụ, dịch vụ tồn kho cần cửa sổ đếm, ngưỡng lỗi và chính sách phân loại exception riêng:

```java
import java.io.IOException;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryPolicy() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .recordException(throwable -> throwable instanceof IOException)
            .build())
        .timeLimiterConfig(TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .build()),
        "inventory");
}
```

Trong ví dụ này, Circuit Breaker chỉ ghi nhận `IOException` theo predicate đã cấu hình. Những exception khác không thỏa predicate sẽ không được tính là lỗi theo chính sách này. Hãy xác định rõ loại exception của client HTTP hoặc client RPC trước khi áp dụng predicate; một predicate quá hẹp có thể khiến lỗi thực tế không làm tăng failure rate.

Spring Cloud CircuitBreaker cũng hỗ trợ cấu hình qua application properties. Theo tài liệu cấu hình Resilience4j, cấu hình properties có độ ưu tiên cao hơn cấu hình Java `Customizer`. Khi một giá trị không có hiệu lực như mong đợi, hãy kiểm tra id, group và cấu hình properties đang được nạp trước khi kết luận callback Java không hoạt động.

## Đọc metrics qua API của Resilience4j

Đối tượng Circuit Breaker native cung cấp metrics chi tiết hơn những gì API chung yêu cầu. Nếu ứng dụng có một bean `CircuitBreakerRegistry` do cấu hình Resilience4j cung cấp và registry đó cũng được factory sử dụng, có thể inject registry rồi lấy Circuit Breaker theo id:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
class InventoryCircuitBreakerMetrics {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryCircuitBreakerMetrics.class);

    private final CircuitBreakerRegistry registry;

    InventoryCircuitBreakerMetrics(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    void logSnapshot() {
        CircuitBreaker circuitBreaker = registry.circuitBreaker("inventory");
        CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

        log.info("state={}, failed={}, successful={}, notPermitted={}, failureRate={}",
            circuitBreaker.getState(),
            metrics.getNumberOfFailedCalls(),
            metrics.getNumberOfSuccessfulCalls(),
            metrics.getNumberOfNotPermittedCalls(),
            metrics.getFailureRate());
    }
}
```

Đoạn mã trên minh họa cách đọc trạng thái và snapshot metrics. Trong ứng dụng thực tế, hãy dùng logger được khai báo trong lớp, đồng thời đưa các số liệu cần thiết vào Micrometer hoặc hệ thống giám sát thay vì gọi `logSnapshot()` theo từng request. Metrics là dữ liệu quan sát tại thời điểm đọc; chúng có thể thay đổi ngay sau đó khi có lời gọi mới hoàn tất.

Khi truy cập registry, cần bảo đảm đây là `CircuitBreakerRegistry` được backend Spring Cloud CircuitBreaker sử dụng. Không giả định mọi cấu hình đều chia sẻ cùng một registry nếu ứng dụng tự khai báo nhiều bean. Nếu tự tạo một registry hoặc gọi `CircuitBreaker.of(...)` độc lập, ứng dụng có thể vô tình tạo một mạch khác với mạch mà `Resilience4JCircuitBreakerFactory` đang dùng. Khi đó, trạng thái và metrics đọc được không phản ánh các request thực tế đi qua factory. Nếu không xác nhận được registry dùng chung, hãy đọc metrics ngay trong callback `addCircuitBreakerCustomizer(...)` đã nhận đúng đối tượng do factory tạo.

## Giữ API native ở ranh giới tích hợp

Một cách tổ chức dễ bảo trì là để service nghiệp vụ gọi API chung, còn lớp cấu hình hoặc adapter chịu trách nhiệm tích hợp với API nhà cung cấp.

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Inventory find(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.find(sku),
            error -> inventoryCache.find(sku)
                .orElseThrow(() -> new InventoryUnavailableException(sku, error)));
    }
}
```

`InventoryService` chỉ biết `CircuitBreakerFactory` và hợp đồng fallback. Nó không cần import `io.github.resilience4j.*`. Cấu hình event, metrics và chính sách native nằm ở lớp cấu hình hoặc adapter riêng. Nếu thay backend, phần service ít có khả năng phải thay đổi; phần tích hợp native sẽ là nơi cần điều chỉnh.

Với API reactive, giữ cùng nguyên tắc: dùng `ReactiveCircuitBreakerFactory` trong luồng xử lý `Mono` hoặc `Flux`, và đặt phần tùy chỉnh provider-specific trong cấu hình reactive tương ứng. Không chuyển một publisher reactive thành lời gọi blocking chỉ để gọi API native; điều đó có thể chặn event-loop và làm mất lợi ích của mô hình reactive.

## Kiểm soát các thao tác quản trị native

Resilience4j có các thao tác quản trị trực tiếp như reset hoặc chuyển mạch sang trạng thái cưỡng bức. Chúng hữu ích trong quy trình vận hành có kiểm soát, ví dụ khi cần mở lại một mạch sau khi khắc phục sự cố hoặc mô phỏng trạng thái để kiểm thử. Đây là thao tác thay đổi trạng thái dùng chung của Circuit Breaker, vì vậy không nên gọi tùy tiện từ endpoint công khai hay từ logic xử lý từng request.

Nếu xây dựng chức năng quản trị, hãy đặt nó sau xác thực và phân quyền phù hợp, ghi audit log gồm người thực hiện, id Circuit Breaker, trạng thái trước và hành động đã yêu cầu. Sau thao tác, tiếp tục theo dõi event và metrics để xác nhận mạch hoạt động như dự kiến. Không coi thao tác ép trạng thái là bằng chứng dịch vụ phụ thuộc đã khỏe; cần kiểm tra bằng lời gọi thử và dữ liệu vận hành.

## Những lỗi thường gặp khi dùng API nhà cung cấp

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Listener phát log nhiều lần | Listener được đăng ký lặp lại trong mỗi request hoặc mỗi lần `run(...)` | Đăng ký trong `Customizer` ở thời điểm tạo mạch; tránh thêm listener liên tục |
| Metrics không khớp traffic | Đọc một registry hoặc Circuit Breaker được tạo độc lập với factory | Dùng registry bean chung do backend tự cấu hình và cùng id |
| Cấu hình Java không có hiệu lực | Cấu hình properties có độ ưu tiên cao hơn | Kiểm tra cấu hình instance, group và id thực tế |
| Chuyển backend làm lỗi biên dịch | Mã nghiệp vụ phụ thuộc trực tiếp vào kiểu Resilience4j | Đưa mã native vào adapter/cấu hình và giữ API chung ở service |
| Mạch mở không đúng như mong đợi | Predicate chỉ ghi nhận một phần exception hoặc bỏ qua nhầm lỗi | Kiểm thử các loại exception đại diện và xác nhận failure rate |
| Endpoint quản trị gây thay đổi ngoài ý muốn | Cho phép gọi thao tác ép trạng thái từ luồng công khai | Tách quyền quản trị, kiểm soát truy cập và ghi audit log |

Trước khi đưa tích hợp native vào production, hãy xác định rõ tính năng nào API chung chưa đáp ứng, kiểm thử đúng id Circuit Breaker, xác nhận listener chỉ được đăng ký một lần, và so sánh metrics native với traffic thực tế. Việc cô lập phần phụ thuộc nhà cung cấp giúp ứng dụng tận dụng được tính năng nâng cao mà vẫn giữ phần lớn mã nghiệp vụ ổn định.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker – Resilience4J specific configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/specific-circuit-breaker-configuration.html)
- [Spring Cloud Commons – Spring Cloud Circuit Breaker API](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html)
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
