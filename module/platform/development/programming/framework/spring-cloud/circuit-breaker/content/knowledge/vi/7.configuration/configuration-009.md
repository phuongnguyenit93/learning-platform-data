# Bật hoặc tắt từng tích hợp theo tính năng và phiên bản

Spring Cloud Circuit Breaker cung cấp một API chung nhưng có nhiều backend và tính năng đi kèm. Trong ứng dụng Spring, việc bật hoặc tắt một phần của hệ thống thường phụ thuộc vào starter trên classpath và các thuộc tính auto-configuration. Cần phân biệt ba phạm vi: chọn backend circuit breaker, bật hoặc tắt một tính năng của backend đó, và chọn kiểu thực thi blocking hay reactive.

Với module `SPRING_CLOUD_CIRCUIT_BREAKER`, cách cấu hình phù hợp phụ thuộc vào stack mà ứng dụng đang dùng: Resilience4j, Spring Retry hoặc Framework Retry. Không phải thuộc tính nào cũng áp dụng cho mọi backend. Ví dụ, các thuộc tính dưới `spring.cloud.circuitbreaker.resilience4j` chỉ điều khiển tích hợp Resilience4j; chúng không thay đổi chính sách của `SpringRetryCircuitBreakerFactory` hay `FrameworkRetryCircuitBreakerFactory`.

## Chọn starter theo kiểu ứng dụng

Starter đưa implementation và các cấu hình tự động tương ứng vào classpath. Với Resilience4j, Spring Cloud Circuit Breaker công bố hai starter:

| Starter | Dùng khi | Factory thường dùng |
|---|---|---|
| `spring-cloud-starter-circuitbreaker-resilience4j` | Lời gọi đồng bộ, blocking | `Resilience4JCircuitBreakerFactory` |
| `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | Lời gọi reactive với Reactor | `ReactiveResilience4JCircuitBreakerFactory` |

Khi dùng Spring Cloud BOM, khai báo dependency mà không tự đặt version riêng:

```xml
<dependencies>
    <!-- Chọn starter blocking nếu ứng dụng gọi API đồng bộ. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <!-- Với ứng dụng reactive, dùng starter Reactor thay cho starter blocking. -->
    <!--
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
    -->
</dependencies>
```

Hai dependency trong ví dụ là hai lựa chọn để minh họa. Hãy chọn starter phù hợp với kiểu lời gọi của ứng dụng và phiên bản Spring Cloud BOM; không thêm cả hai chỉ để thử xem auto-configuration nào thắng. Nếu một ứng dụng thực sự cần cả API blocking và reactive, cần kiểm tra các factory được tạo và cách inject trong context của phiên bản đang dùng.

## Tắt toàn bộ auto-configuration Resilience4j

Nếu ứng dụng không muốn Spring Cloud Circuit Breaker tự tạo các bean tích hợp Resilience4j, đặt thuộc tính sau:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enabled: false
```

Thuộc tính `spring.cloud.circuitbreaker.resilience4j.enabled=false` tắt auto-configuration của tích hợp Resilience4j. Phạm vi của nó là backend Resilience4j; nó không phải công tắc chung để tắt mọi implementation của Spring Cloud Circuit Breaker. Việc đặt thuộc tính này cũng không tự loại dependency khỏi classpath. Nếu ứng dụng không còn dùng thư viện Resilience4j ở bất kỳ nơi nào, có thể bỏ starter hoặc loại dependency không cần thiết qua dependency management.

Nếu cần tiếp tục dùng circuit breaker nhưng chỉ muốn tắt một tính năng cụ thể như TimeLimiter hoặc Bulkhead, hãy dùng công tắc riêng của tính năng đó. Tắt toàn bộ auto-configuration sẽ làm factory Resilience4j không được cấu hình theo cơ chế tự động, vì vậy các thuộc tính cấp tính năng không thể thay thế cho việc bật backend.

## Bật hoặc tắt TimeLimiter theo phạm vi

Trong tích hợp Resilience4j, TimeLimiter được bật mặc định. Có thể tắt TimeLimiter trên toàn ứng dụng bằng `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter`:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter: true
```

Khi chỉ một số service không cần TimeLimiter, dùng `disable-time-limiter-map` để đặt giá trị theo group hoặc instance:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter: false
        disable-time-limiter-map:
          catalog: false
          batchGroup: true
          legacyReport: true
```

Trong ví dụ, `catalog` giữ TimeLimiter, còn `batchGroup` và `legacyReport` tắt TimeLimiter. Giá trị `true` trong map nghĩa là tắt; `false` nghĩa là bật. Khi dùng `factory.create(id, groupName)`, key có thể đại diện cho instance hoặc group. Thứ tự ưu tiên là **instance > group > global**. Nếu không có giá trị riêng trong map, ứng dụng dùng giá trị global; nếu không đặt công tắc global, TimeLimiter vẫn được bật theo mặc định.

Các thuộc tính tắt TimeLimiter này thuộc Spring Cloud Circuit Breaker và áp dụng cho cả tích hợp cơ bản lẫn reactive của Resilience4j. Tắt TimeLimiter không tắt CircuitBreaker: trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`, sliding window và ngưỡng lỗi vẫn hoạt động. Tuy nhiên, ứng dụng phải có timeout ở HTTP client hoặc tầng gọi mạng phù hợp nếu không muốn request chờ vô hạn.

## Bật hoặc tắt Bulkhead

Nếu `resilience4j-bulkhead` có mặt trên classpath, Spring Cloud Circuit Breaker Resilience4j tự bọc các lời gọi bằng Bulkhead. Có thể tắt tích hợp Bulkhead bằng thuộc tính riêng:

```yaml
spring:
  cloud:
    circuitbreaker:
      bulkhead:
        resilience4j:
          enabled: false
```

Đây là công tắc của Bulkhead; nó không tắt CircuitBreaker hay TimeLimiter. Nếu bật Bulkhead, Resilience4j cung cấp hai kiểu:

| Kiểu | Cơ chế | Phù hợp khi |
|---|---|---|
| `FixedThreadPoolBulkhead` | Dùng thread pool và hàng đợi có giới hạn | Cần cô lập việc thực thi bằng pool riêng và kiểm soát số tác vụ chờ |
| `SemaphoreBulkhead` | Dùng semaphore để giới hạn số lời gọi đồng thời | Muốn giới hạn concurrency mà không chuyển việc thực thi sang thread pool riêng |

Mặc định, Spring Cloud Circuit Breaker Resilience4j sử dụng `FixedThreadPoolBulkhead`. Để đổi mặc định sang `SemaphoreBulkhead`, đặt:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
```

Việc chọn semaphore thay đổi cách cô lập tài nguyên và xử lý concurrency. Hãy kiểm tra đặc tính blocking/reactive của lời gọi, giới hạn đồng thời, hàng đợi và cách executor hoạt động trước khi đổi kiểu Bulkhead. Cấu hình `maxConcurrentCalls`, `maxThreadPoolSize` và `coreThreadPoolSize` là chính sách của từng Bulkhead instance; chúng không phải công tắc bật/tắt auto-configuration.

## Bật metric theo dependency cần thiết

Metric Resilience4j được tự cấu hình khi có các dependency cần thiết trên classpath. Để thu thập metric, thêm Spring Boot Actuator và Resilience4j Micrometer:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>
</dependencies>
```

`spring-boot-starter-actuator` đã mang theo `micrometer-core`, nên không cần khai báo riêng chỉ để bật metric Resilience4j. Việc có dependency không đồng nghĩa mọi endpoint Actuator đều được công khai; cần cấu hình exposure và bảo mật endpoint theo chính sách vận hành của ứng dụng.

## Phân biệt các backend và yêu cầu phiên bản

Spring Cloud Circuit Breaker có nhiều implementation. Bảng dưới đây giúp chọn đúng integration và tránh áp dụng nhầm thuộc tính:

| Implementation | Dependency/starter | Phạm vi và điều kiện |
|---|---|---|
| Resilience4j blocking | `spring-cloud-starter-circuitbreaker-resilience4j` | API blocking; hỗ trợ CircuitBreaker, TimeLimiter, Bulkhead và metric khi có dependency tương ứng |
| Resilience4j reactive | `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | API Reactor; dùng `ReactiveResilience4JCircuitBreakerFactory` và cùng nhóm thuộc tính Resilience4j được hỗ trợ |
| Spring Retry | `spring-cloud-starter-circuitbreaker-spring-retry` | Dùng `SpringRetryCircuitBreakerFactory` và `SpringRetryConfigBuilder`; cấu hình riêng theo API Spring Retry |
| Framework Retry | `spring-cloud-starter-circuitbreaker-framework-retry` | Dựa trên retry API của Spring Framework 7; không hỗ trợ reactive |

Framework Retry là integration gắn với Spring Framework 7. Nó chỉ phù hợp khi phiên bản Spring Boot, Spring Framework và Spring Cloud release train của ứng dụng tương thích với nhau. Các ứng dụng dùng Spring Framework 6 hoặc Spring Boot 3 không thể chỉ thêm starter Framework Retry để có tính năng này. Khi cần reactive, chọn Resilience4j reactive thay vì Framework Retry.

Spring Retry và Framework Retry là hai integration khác nhau. `spring.cloud.circuitbreaker.resilience4j.enabled`, `disable-time-limiter`, `disable-time-limiter-map` và các công tắc Bulkhead ở trên là các thuộc tính riêng của Resilience4j; không dùng chúng để cấu hình `SpringRetryCircuitBreakerFactory` hoặc `FrameworkRetryCircuitBreakerFactory`. Với các backend retry, chọn đúng starter, inject đúng factory và cấu hình qua `SpringRetryConfigBuilder` hoặc `FrameworkRetryConfigBuilder` theo tài liệu của phiên bản tương ứng.

Phiên bản tài liệu Spring Cloud Circuit Breaker hiện hành có liệt kê Resilience4j, Spring Retry và Framework Retry. Framework Retry dựa vào Spring Framework 7, vì vậy danh sách implementation khả dụng có thể khác ở các release train cũ. Các thuộc tính như `disable-time-limiter-map` cũng cần được đối chiếu với tài liệu của đúng phiên bản dependency; không giả định một thuộc tính mới tồn tại trong mọi bản 3.x hoặc 4.x.

Để quản lý phiên bản an toàn:

1. Dùng Spring Cloud BOM tương thích với Spring Boot đang chạy để quản lý version của starter.
2. Tra tài liệu của đúng Spring Cloud Circuit Breaker release, không chỉ xem trang `current` khi ứng dụng đang ở release train cũ.
3. Kiểm tra Spring Framework major version trước khi chọn Framework Retry.
4. Kiểm tra dependency tree để biết starter và module tùy chọn nào thực sự có mặt trên classpath.
5. Sau khi thay đổi cờ, xác nhận factory tương ứng được tạo hoặc bị loại khỏi application context và kiểm tra hành vi ở runtime.

## Ví dụ cấu hình theo môi trường

Một ứng dụng có thể giữ Resilience4j, chỉ tắt TimeLimiter cho một nhóm batch và tắt Bulkhead nếu không muốn cô lập bằng thread pool/semaphore:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enabled: true
        disable-time-limiter: false
        disable-time-limiter-map:
          catalog: false
          batchGroup: true
        enableSemaphoreDefaultBulkhead: false
      bulkhead:
        resilience4j:
          enabled: false
```

Trong cấu hình này, Resilience4j vẫn cung cấp circuit breaker; TimeLimiter vẫn hoạt động cho `catalog` và các instance không có override; TimeLimiter bị tắt cho group `batchGroup`; Bulkhead auto-configuration bị tắt. Nếu muốn dùng semaphore Bulkhead mặc định, cần bật Bulkhead và đặt `enableSemaphoreDefaultBulkhead: true`.

Không nên bật/tắt các tính năng chỉ để làm cho ứng dụng khởi động thành công mà không kiểm tra tác động. Tắt TimeLimiter có thể khiến request chờ lâu; tắt Bulkhead có thể cho phép quá nhiều lời gọi cùng chiếm tài nguyên; tắt Resilience4j auto-configuration có thể làm mất factory mà code đang inject. Mỗi thay đổi cần đi kèm timeout ở tầng mạng, giới hạn concurrency hoặc implementation thay thế phù hợp.

## Kiểm tra sau khi bật hoặc tắt

Sau khi sửa dependency hoặc thuộc tính, kiểm tra theo thứ tự:

1. **Dependency:** xác nhận starter đúng loại có trong dependency tree và version do Spring Cloud BOM quản lý.
2. **Auto-configuration:** bật điều kiện report của Spring Boot hoặc xem log khởi động để biết cấu hình Resilience4j, Spring Retry hay Framework Retry nào đã được áp dụng.
3. **Factory:** xác nhận factory mà service inject đúng với backend dự kiến; với reactive, kiểm tra `ReactiveResilience4JCircuitBreakerFactory`.
4. **TimeLimiter:** tạo một tác vụ chậm hơn timeout; xác nhận timeout xảy ra khi bật và tác vụ không bị giới hạn bởi TimeLimiter khi đã tắt riêng tính năng đó.
5. **Bulkhead:** tạo concurrency vượt giới hạn; xác nhận lời gọi bị từ chối theo Bulkhead khi bật và kiểm tra giới hạn thay thế khi tắt.
6. **Circuit breaker:** tạo chuỗi lỗi để xác nhận breaker vẫn chuyển trạng thái khi chỉ tắt TimeLimiter hoặc Bulkhead.
7. **Metric:** xác nhận Actuator và Resilience4j Micrometer được nạp nếu cần theo dõi số lời gọi, lỗi, lời gọi chậm và trạng thái.

Kết quả mong đợi là mỗi công tắc chỉ ảnh hưởng đến đúng phạm vi được tài liệu mô tả. Nếu thay đổi một thuộc tính mà không thấy hành vi tương ứng, hãy kiểm tra chính tả property, version Spring Cloud Circuit Breaker, dependency trên classpath và điều kiện auto-configuration trước khi tự thêm một key mới.

## Tài liệu tham khảo

- [Spring Cloud Circuit Breaker — Resilience4j starters và auto-configuration](https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html)
- [Spring Cloud Circuit Breaker — cấu hình TimeLimiter và Bulkhead](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html)
- [Spring Cloud Circuit Breaker — các implementation hiện hành](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud Circuit Breaker — Spring Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html)
- [Spring Cloud Circuit Breaker — Framework Retry và yêu cầu Spring Framework 7](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html)
