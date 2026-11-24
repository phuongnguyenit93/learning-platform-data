# Đối chiếu hiện thực được hỗ trợ trong đúng Spring Cloud Release Train

Spring Cloud Circuit Breaker cung cấp một API chung để ứng dụng gọi Circuit Breaker, còn phần thực thi được cung cấp bởi các implementation khác nhau. Mỗi Release Train quản lý một phiên bản Spring Cloud Circuit Breaker tương ứng với một dải Spring Boot và Spring Framework. Vì vậy, danh sách implementation, starter và khả năng reactive phải được kiểm tra trong tài liệu của đúng train mà ứng dụng đang dùng.

Không nên lấy danh sách implementation từ một trang tài liệu cũ rồi áp dụng cho mọi dự án. Ví dụ, tài liệu cũ từng liệt kê Netflix Hystrix; tài liệu hiện tại của Spring Cloud Circuit Breaker đã chuyển sang các implementation khác. Tương tự, Spring Framework Retry chỉ xuất hiện ở các dòng Spring Framework 7 tương ứng với Spring Boot 4, không phải mọi train Spring Cloud.

## 1. Xác định đúng Release Train trước khi chọn implementation

Thực hiện theo thứ tự: xác định phiên bản Spring Boot của ứng dụng, chọn Spring Cloud Release Train tương thích, import Spring Cloud BOM, rồi xem phiên bản `spring-cloud-circuitbreaker` mà train đó quản lý. Tài liệu của project được liên kết từ trang Release Train là nguồn đối chiếu chính cho starter và tính năng.

Ví dụ các phiên bản GA được tài liệu Spring công bố tại thời điểm biên soạn:

| Spring Cloud Release Train | Spring Boot được hỗ trợ trong tài liệu train | Phiên bản spring-cloud-circuitbreaker | Danh mục implementation trong tài liệu project |
| --- | --- | --- | --- |
| `2026.0.0` | `4.2.0` | `5.1.0` | Resilience4J, Spring Retry, Spring Framework Retry |
| `2025.1.5` | `4.0.10` | `5.0.3` | Resilience4J, Spring Retry, Spring Framework Retry |
| `2025.0.3` | `3.5.15` | `3.3.3` | Resilience4J, Spring Retry |
| `2024.0.x` | Spring Boot `3.4.x` | Spring Cloud Circuit Breaker `3.2.x` | Đối chiếu tài liệu `3.2.x` của project |
| `2023.0.x` | Spring Boot `3.3.x`/`3.2.x` | Spring Cloud Circuit Breaker `3.1.x` | Đối chiếu tài liệu `3.1.x` của project |

Bảng này giúp định hướng phiên bản; hãy mở trang Release Train và project reference đúng patch đang dùng trước khi thêm dependency. Train có thể được cập nhật patch, và tài liệu `current` có thể đã trỏ sang một train mới hơn.

Trang Release Train hiện tại còn liên kết trực tiếp tới phiên bản project mà train quản lý. Ví dụ, `2026.0.0` liên kết tới Circuit Breaker `5.1.0`, còn `2025.1.5` liên kết tới `5.0.3`. Với `2025.0.3`, trang train liên kết tới `3.3.3`. Điều này đáng tin cậy hơn việc tự chọn một phiên bản starter mới nhất trên Maven Central.

## 2. Các implementation được liệt kê trong Circuit Breaker project hiện tại

Tài liệu Spring Cloud Circuit Breaker `5.1.0` liệt kê ba implementation: Resilience4J, Spring Retry và Spring Framework Retry. Hai dòng `5.0.x` và `5.1.x` gắn với Spring Boot 4/Spring Framework 7. Tài liệu dòng `3.3.x` dành cho Spring Boot 3.5 liệt kê Resilience4J và Spring Retry; không có Framework Retry trong danh mục của dòng này.

| Implementation | Nền tảng thực thi | Điểm mạnh | Giới hạn cần xác minh |
| --- | --- | --- | --- |
| Resilience4J | Thư viện fault-tolerance riêng, được Spring Cloud bọc qua factory | Circuit Breaker, sliding window, slow-call detection, TimeLimiter, Bulkhead, RateLimiter; hỗ trợ blocking và reactive | Cần chọn đúng starter reactive/non-reactive; cấu hình và module mở rộng phụ thuộc dependency có trên classpath |
| Spring Retry | `CircuitBreakerRetryPolicy`, stateful retry và `RetryTemplate` | Phù hợp ứng dụng đã dùng Spring Retry và cần tái sử dụng `RetryPolicy`, `RetryTemplate`, listener | API tập trung vào lời gọi đồng bộ; không giả định có reactive factory trong train nếu tài liệu không nêu |
| Spring Framework Retry | `RetryTemplate` và `RetryPolicy` gốc của Spring Framework 7, được Spring Cloud bổ sung trạng thái Circuit Breaker | Tích hợp gọn với Spring Framework 7, có retry policy, backoff và timeout mở mạch | Chỉ dành cho các train dùng Spring Framework 7; không hỗ trợ ứng dụng reactive |

Ba implementation cùng được truy cập qua abstraction Spring Cloud, nhưng không có cùng mô hình cấu hình. Resilience4J có cấu hình `resilience4j.circuitbreaker.*` và `resilience4j.timelimiter.*`; Spring Retry dùng `SpringRetryConfigBuilder`; Framework Retry dùng `FrameworkRetryConfigBuilder`. Không sao chép YAML của Resilience4J sang hai implementation Retry rồi kỳ vọng chúng được binding.

## 3. Resilience4J: lựa chọn đầy đủ cho blocking và reactive

Resilience4J là implementation có phạm vi tính năng rộng nhất trong danh mục Spring Cloud Circuit Breaker. Nó phù hợp khi ứng dụng cần Circuit Breaker theo sliding window, phân loại lời gọi chậm, TimeLimiter, Bulkhead hoặc RateLimiter, hoặc cần cùng một implementation cho Spring MVC và WebFlux.

Spring Cloud cung cấp hai starter:

```groovy
dependencies {
    // Spring MVC hoặc lời gọi đồng bộ
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'

    // WebFlux/Reactor
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

Chỉ thêm starter phù hợp với loại lời gọi cần bảo vệ. Starter không reactive cung cấp `Resilience4JCircuitBreakerFactory`; starter Reactor cung cấp `ReactiveResilience4JCircuitBreakerFactory`. Nếu ứng dụng cần cả hai kiểu gọi, kiểm tra hướng dẫn đúng train để biết có thể dùng đồng thời hai starter và các bean factory tương ứng hay không.

Ví dụ cấu hình Circuit Breaker theo ID:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

ID `inventory` phải trùng với ID truyền vào `circuitBreakerFactory.create("inventory")` hoặc `reactiveCircuitBreakerFactory.create("inventory")`. Các thuộc tính trên là cấu hình Resilience4J; chúng không tự áp dụng cho Spring Retry hoặc Framework Retry.

Ví dụ tùy chỉnh factory đồng bộ:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryCustomizer() {
    return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                    .circuitBreakerConfig(CircuitBreakerConfig.custom()
                            .slidingWindowSize(20)
                            .minimumNumberOfCalls(10)
                            .failureRateThreshold(50)
                            .build())
                    .timeLimiterConfig(TimeLimiterConfig.custom()
                            .timeoutDuration(Duration.ofSeconds(2))
                            .build())
                    .build());
}
```

Với reactive, dùng `ReactiveResilience4JCircuitBreakerFactory` và trả `Mono`/`Flux` qua `ReactiveCircuitBreaker`. Không dùng `CircuitBreakerFactory.run` đồng bộ để bọc publisher rồi coi kết quả bất đồng bộ đã được quan sát.

Resilience4J Bulkhead chỉ được Spring Cloud áp dụng khi module `resilience4j-bulkhead` có trên classpath và tích hợp Bulkhead đang bật. Tài liệu Resilience4J mô tả `SemaphoreBulkhead` và `FixedThreadPoolBulkhead`; kiểm tra cấu hình mặc định của đúng train trước khi dựa vào một implementation cụ thể.

## 4. Spring Retry: tái sử dụng RetryTemplate và stateful retry

Spring Retry cung cấp `CircuitBreakerRetryPolicy` kết hợp với `DefaultRetryState`. Spring Cloud tạo `SpringRetryCircuitBreakerFactory`, cho phép cấu hình `RetryPolicy` thông qua `SpringRetryConfigBuilder` và tùy chỉnh `RetryTemplate` sau khi tạo.

Starter được công bố cho Spring Retry:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-spring-retry'
}
```

Ví dụ đặt chính sách retry mặc định:

```java
@Bean
Customizer<SpringRetryCircuitBreakerFactory> retryCustomizer() {
    return factory -> factory.configureDefault(id ->
            new SpringRetryConfigBuilder(id)
                    .retryPolicy(new SimpleRetryPolicy(2))
                    .build());
}
```

Ví dụ trên minh họa cấu hình `RetryPolicy`; hãy chọn chính sách retry theo exception, số lần thử và backoff của dịch vụ. Có thể thêm `RetryListener` qua `addRetryTemplateCustomizers` để quan sát các lần thử hoặc gắn hành vi vận hành.

Spring Retry phù hợp khi hệ thống đã chuẩn hóa các chính sách retry dựa trên Spring Retry hoặc cần tích hợp `RetryTemplate`. Khi so sánh với Resilience4J, hãy đánh giá cách implementation theo dõi lỗi và chuyển trạng thái, số lần retry, backoff, fallback và khả năng reactive. Không giả định nó có cùng `slidingWindowSize`, `slowCallRateThreshold` hay `TimeLimiter` properties như Resilience4J.

## 5. Spring Framework Retry: implementation dựa trên Spring Framework 7

Spring Framework 7 bổ sung retry native với `RetryTemplate` và `RetryPolicy`. Spring Cloud Circuit Breaker cung cấp implementation Framework Retry để bổ sung trạng thái `CLOSED`, `OPEN` và `HALF_OPEN` cho cơ chế retry này.

Starter:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-framework-retry'
}
```

Ví dụ cấu hình mặc định:

```java
@Bean
Customizer<FrameworkRetryCircuitBreakerFactory> frameworkRetryCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(RetryPolicy.withMaxRetries(3)
                            .withBackoff(Duration.ofMillis(100), 2.0))
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build());
}
```

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `retryPolicy(...)` | Quy định số lần thử, thời gian tối đa, backoff và loại exception được thử lại |
| `openTimeout(...)` | Thời gian Circuit Breaker ở `OPEN` trước khi chuyển sang `HALF_OPEN`; tài liệu hiện tại nêu mặc định 20 giây |
| `resetTimeout(...)` | Khoảng thời gian dùng để tự reset về `CLOSED` theo quy tắc của implementation; tài liệu hiện tại nêu mặc định 5 giây |

Framework Retry có semantics khác với sliding window của Resilience4J. Một lần thực thi được xem là thất bại sau khi toàn bộ retry đã cạn thì mạch mở. Trong `OPEN`, lời gọi bị từ chối và fallback có thể chạy. Hết `openTimeout`, một lời gọi được cho phép ở `HALF_OPEN` để kiểm tra phục hồi; thành công thì đóng mạch, thất bại thì mở lại.

Implementation này không hỗ trợ ứng dụng reactive. Chỉ chọn nó khi dự án dùng Spring Framework 7 và lời gọi được bảo vệ là blocking/imperative. Với WebFlux cần Circuit Breaker reactive, dùng Resilience4J theo hướng dẫn của train.

## 6. Sentinel và các tên xuất hiện trong tài liệu Spring Cloud Commons

Trang Spring Cloud Commons mô tả abstraction chung và liệt kê Resilience4J, Sentinel và Spring Retry. Trang đó cũng liên kết sang hướng dẫn Sentinel của Spring Cloud Alibaba. Danh sách này có phạm vi rộng hơn danh mục implementation được đóng gói trong project Spring Cloud Circuit Breaker ở một Release Train cụ thể.

Vì vậy, khi cân nhắc Sentinel, hãy xác minh starter và ma trận tương thích từ Spring Cloud Alibaba tương ứng với Spring Boot/Spring Cloud đang dùng. Không lấy một mục trong trang Commons rồi suy ra rằng train hiện tại có sẵn một starter Sentinel do project `spring-cloud-circuitbreaker` phát hành.

Netflix Hystrix xuất hiện trong tài liệu Spring Cloud cũ, nhưng không có trong danh mục implementation của các tài liệu Circuit Breaker hiện tại được nêu ở bài này. Không thêm Hystrix vào dự án mới chỉ vì tìm thấy một ví dụ từ Hoxton hoặc tài liệu lịch sử.

## 7. Đối chiếu theo nhu cầu ứng dụng

| Nhu cầu | Hướng lựa chọn | Lý do |
| --- | --- | --- |
| Cần WebFlux/Reactor và `Mono`/`Flux` | Resilience4J reactive starter | Project docs xác nhận hỗ trợ blocking và reactive; có `ReactiveCircuitBreakerFactory` |
| Cần sliding window, slow-call threshold, TimeLimiter, Bulkhead và RateLimiter | Resilience4J | Bộ tính năng fault-tolerance phong phú và cấu hình theo instance |
| Dự án hiện có `RetryTemplate`, `CircuitBreakerRetryPolicy` và listener của Spring Retry | Spring Retry | Tái sử dụng chính sách retry và cơ chế stateful retry hiện có |
| Ứng dụng Boot 4/Spring Framework 7 muốn dùng RetryPolicy native, Circuit Breaker imperative gọn | Framework Retry | Dùng API retry native của Spring Framework 7 và cấu hình `openTimeout`/`resetTimeout` |
| Cần Sentinel | Kiểm tra Spring Cloud Alibaba theo train tương ứng | Đây là tích hợp hệ sinh thái riêng; xác minh starter và compatibility matrix độc lập |

Không so sánh chỉ bằng số lượng tính năng. Hãy đánh giá semantics khi mạch mở, cách tính lỗi, cách thử phục hồi, timeout, retry, bulkhead, reactive support, metrics, khả năng vận hành và chi phí chuyển đổi code.

## 8. Import BOM và khai báo đúng starter

Để Spring Cloud quản lý phiên bản starter tương thích với train, import `spring-cloud-dependencies` BOM. Ví dụ Gradle Groovy:

```groovy
ext {
    set('springCloudVersion', '2026.0.0')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

Ví dụ này dành cho dự án dùng Spring Boot tương thích với Spring Cloud `2026.0.0`; tài liệu train hiện tại ghép train này với Spring Boot `4.2.0`. Nếu dự án dùng Boot 3.5, hãy chọn train tương thích như `2025.0.x` và dùng starter/version mà BOM của train đó quản lý.

Với Maven, cấu hình tương đương:

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

<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
  </dependency>
</dependencies>
```

Không pin một phiên bản `spring-cloud-starter-circuitbreaker-*` tùy ý bên cạnh BOM nếu không có lý do tương thích đã được xác minh. Tránh trộn các starter từ nhiều Release Train trong cùng ứng dụng.

## 9. Kiểm tra implementation thực sự được resolve

Sau khi khai báo dependency, kiểm tra dependency tree để biết BOM đã resolve đúng phiên bản và starter đã kéo những module nào.

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-cloud-starter-circuitbreaker --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j,org.springframework.retry
```

Đối chiếu các điểm sau:

1. Phiên bản Spring Boot có nằm trong ma trận tương thích của Release Train không?
2. `spring-cloud-dependencies` BOM có đúng train và patch đang dùng không?
3. Phiên bản `spring-cloud-circuitbreaker` được BOM quản lý có khớp project reference của train không?
4. Starter được resolve có đúng provider và đúng kiểu reactive/non-reactive không?
5. Dependency tree có vô tình kéo hai provider starter cùng tạo `CircuitBreakerFactory` vào một ứng dụng không?
6. Nếu dùng Framework Retry, Spring Framework 7 và Spring Boot 4 có đúng trong dependency graph không?
7. Nếu dùng Sentinel, starter và phiên bản Spring Cloud Alibaba có tương thích với train không?

Ở runtime, kiểm tra bean factory mà ứng dụng inject được. Với Resilience4J imperative là `Resilience4JCircuitBreakerFactory`; với Resilience4J reactive là `ReactiveResilience4JCircuitBreakerFactory`; với Spring Retry là `SpringRetryCircuitBreakerFactory`; với Framework Retry là `FrameworkRetryCircuitBreakerFactory`. Có thể kiểm tra bằng Spring Boot Actuator `beans` trong môi trường phát triển được bảo vệ hoặc bằng một integration test của ApplicationContext.

Thông thường một ứng dụng nên chọn một implementation cho `CircuitBreakerFactory`. Không thêm nhiều starter imperative rồi mong framework tự chọn implementation theo từng ID. Nếu cần cả imperative và reactive, dùng đúng cặp factory mà tài liệu train hỗ trợ; Resilience4J có hai factory riêng cho hai kiểu lời gọi.

## 10. Kiểm thử hành vi trước khi quyết định

Chạy cùng một bộ kịch bản cho implementation đang cân nhắc để so sánh hành vi:

1. Gọi dependency thành công liên tục và xác nhận trạng thái bình thường, latency và metrics.
2. Làm dependency trả lỗi có kiểm soát; xác nhận điều kiện chuyển `CLOSED` sang `OPEN` theo semantics của implementation.
3. Gửi thêm request khi `OPEN`; xác nhận request bị từ chối và fallback được gọi mà không tạo thêm tải lên dependency.
4. Chờ hết thời gian mở mạch; xác nhận số lời gọi thăm dò ở `HALF_OPEN` và điều kiện đóng/mở lại.
5. Làm dependency chậm; xác nhận implementation có phân loại slow call hoặc TimeLimiter đúng như cấu hình.
6. Kiểm tra Retry và backoff; xác nhận tổng số request không vượt giới hạn và không kéo dài quá deadline của request bên ngoài.
7. Với WebFlux, kiểm tra `Mono`/`Flux`, subscription và fallback non-blocking. Nếu provider không có reactive support, loại nó khỏi phương án cho luồng này.
8. Kiểm tra metrics, event, health indicator, log và khả năng truy vết theo ID dependency.

Không so sánh các giá trị cấu hình có cùng tên mà không xét semantics. Ví dụ, `slidingWindowSize` của Resilience4J là cửa sổ đo số mẫu hoặc thời gian; `openTimeout` của Framework Retry là khoảng mạch mở; chúng không phải hai tham số tương đương.

## 11. Các lỗi lựa chọn thường gặp

- Chọn Spring Cloud Release Train không tương thích với Spring Boot hiện có rồi cố sửa bằng cách pin riêng starter.
- Dùng trang `/current` để quyết định dependency cho một dự án đang ở train cũ.
- Nghĩ mọi implementation đều có reactive factory vì abstraction chung có `ReactiveCircuitBreakerFactory`.
- Dùng cấu hình `resilience4j.circuitbreaker.*` cho Spring Retry hoặc Framework Retry.
- Chọn Framework Retry trong ứng dụng WebFlux dù implementation này không hỗ trợ reactive.
- Nhầm Spring Retry với Spring Framework Retry; hai implementation dùng API và builder khác nhau.
- Thấy Sentinel trên trang Spring Cloud Commons rồi mặc định nó có starter từ project Circuit Breaker của train hiện tại.
- Thêm hai provider imperative starter và để auto-configuration tranh nhau đăng ký cùng loại factory.
- Dựa vào tài liệu Hystrix cũ thay vì implementation được công bố cho Release Train hiện tại.

## Tài liệu tham khảo

- [Spring Cloud Release – 2026.0.0](https://docs.spring.io/spring-cloud-release/reference/index.html): Release Train hiện tại, Spring Boot tương thích và phiên bản project Circuit Breaker.
- [Spring Cloud Release – 2025.1.5](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html): ví dụ train Boot 4 và Circuit Breaker 5.0.x.
- [Spring Cloud Release – 2025.0.3](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html): ví dụ train Boot 3.5 và Circuit Breaker 3.3.x.
- [Spring Cloud Circuit Breaker – Implementations](https://docs.spring.io/spring-cloud-circuitbreaker/reference/): danh mục implementation hiện tại và các trang cấu hình theo provider.
- [Spring Cloud Circuit Breaker – Resilience4J](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): starter imperative/reactive, Customizer, Bulkhead và properties.
- [Spring Cloud Circuit Breaker – Spring Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html): `CircuitBreakerRetryPolicy`, `DefaultRetryState` và `SpringRetryConfigBuilder`.
- [Spring Cloud Circuit Breaker – Framework Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html): Spring Framework 7, starter, retry policy, open/reset timeout và giới hạn reactive.
- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): abstraction factory, fallback và các tích hợp trong hệ sinh thái.
