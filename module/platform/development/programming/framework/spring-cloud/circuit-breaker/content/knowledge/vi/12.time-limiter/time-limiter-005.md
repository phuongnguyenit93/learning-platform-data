# Phối hợp TimeLimiter với Future hoặc CompletionStage

`TimeLimiter` giới hạn khoảng thời gian ứng dụng chờ kết quả từ một lời gọi phụ thuộc. Trong Java, Resilience4j cung cấp hai cách tích hợp phổ biến: `Future` cho luồng chờ đồng bộ và `CompletionStage` cho luồng xử lý bất đồng bộ. Chọn đúng cách giúp Spring Cloud Circuit Breaker bảo vệ độ trễ mà vẫn kiểm soát được thread, fallback và kết quả lỗi.

Điểm cần nhớ là TimeLimiter giới hạn thời gian chờ của caller. Nó không tự tạo worker để chạy một tác vụ blocking và cũng không bảo đảm mọi công việc phía dependency dừng ngay khi hết hạn. Muốn bảo vệ tài nguyên, cần kết hợp executor, timeout của client và Bulkhead phù hợp.

## 1. Phân biệt Future và CompletionStage

`Future<T>` biểu diễn kết quả sẽ có trong tương lai. Caller thường lấy kết quả bằng `get()`, hoặc `get(timeout, unit)`. Những thao tác này chặn thread đang gọi cho tới khi có kết quả, lỗi hoặc hết thời gian.

`CompletionStage<T>` biểu diễn một bước trong chuỗi xử lý bất đồng bộ. Caller đăng ký callback như `thenApply`, `thenCompose`, `handle` hoặc `whenComplete`; thread gọi không cần chờ kết quả. `CompletableFuture<T>` triển khai cả `Future<T>` và `CompletionStage<T>`, nhưng cách dùng nó với TimeLimiter phụ thuộc API được chọn.

| Tiêu chí | Future | CompletionStage |
| --- | --- | --- |
| Cách lấy kết quả | `get()` chặn thread | Callback/chain xử lý khi stage hoàn tất |
| API TimeLimiter | `executeFutureSupplier` hoặc `decorateFutureSupplier` | `executeCompletionStage` hoặc `decorateCompletionStage` |
| Scheduler | Không cần scheduler riêng để chờ timeout | Cần `ScheduledExecutorService` để kích hoạt timeout |
| Công việc thực tế chạy ở đâu? | Executor tạo ra Future | Executor hoặc HTTP client bất đồng bộ tạo CompletionStage |
| Hành vi khi timeout | Có thể gọi `Future.cancel(true)` theo cấu hình | Stage được hoàn tất với lỗi timeout; việc dừng tác vụ nguồn phụ thuộc API thực thi |

Chọn `Future` khi API hiện có là đồng bộ và caller chấp nhận chờ trên một thread. Chọn `CompletionStage` khi cần trả kết quả bất đồng bộ, ghép nhiều bước hoặc tránh giữ thread request trong lúc chờ I/O.

## 2. Cấu hình TimeLimiter

Resilience4j cho phép đặt thời hạn và chính sách hủy Future bằng `TimeLimiterConfig`. Ví dụ:

```java
TimeLimiterConfig config = TimeLimiterConfig.custom()
        .timeoutDuration(Duration.ofMillis(800))
        .cancelRunningFuture(true)
        .build();

TimeLimiter timeLimiter = TimeLimiter.of("pricing", config);
```

`timeoutDuration` là thời gian tối đa caller chờ. `cancelRunningFuture` yêu cầu hủy Future đang chạy khi nhánh Future hết hạn. Mặc định của Resilience4j là một giây và `cancelRunningFuture` là `true`; nên cấu hình rõ theo SLA của từng dependency thay vì phụ thuộc mặc định.

Trong ứng dụng Spring Boot, có thể khai báo theo instance trong `application.yml`:

```yaml
resilience4j:
  timelimiter:
    instances:
      pricing:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

ID `pricing` phải trùng với tên instance được dùng trong mã hoặc annotation. Với Spring Cloud CircuitBreaker, `resilience4j.timelimiter.instances.pricing` cũng là cấu hình TimeLimiter cho breaker được tạo bằng ID `pricing`. Cấu hình properties có độ ưu tiên cao hơn Java `Customizer`; nếu giá trị chạy khác bean tùy biến, hãy kiểm tra cấu hình instance và property source.

Spring Cloud CircuitBreaker bật TimeLimiter mặc định cho các execution của implementation Resilience4j. Có thể tắt toàn cục bằng `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter: true`, hoặc chọn bật/tắt theo instance/group bằng `disable-time-limiter-map`. Chỉ tắt khi tầng HTTP client hoặc một cơ chế khác đã đặt deadline tương đương.

## 3. Dùng TimeLimiter với Future

`executeFutureSupplier` nhận một `Supplier<Future<T>>`. Resilience4j lấy Future từ supplier rồi chờ kết quả trong thời hạn cấu hình. Caller thread bị chặn trong khoảng chờ đó; nếu hết hạn, TimeLimiter ném `TimeoutException` và gọi `future.cancel(true)` khi `cancelRunningFuture` là `true`.

Ví dụ gọi dịch vụ định giá bằng client đồng bộ nhưng đưa công việc vào worker pool:

```java
public Price getPrice(String isbn) {
    try {
        return timeLimiter.executeFutureSupplier(
                () -> pricingExecutor.submit(() -> pricingClient.fetch(isbn))
        );
    } catch (TimeoutException ex) {
        return Price.unavailable(isbn);
    } catch (Exception ex) {
        throw new IllegalStateException("Không thể lấy giá sách", ex);
    }
}
```

`pricingExecutor` là `ExecutorService` được quản lý theo vòng đời ứng dụng; `pricingClient.fetch` là lời gọi blocking. Supplier chỉ tạo Future và giao công việc cho executor. `executeFutureSupplier` chờ Future hoàn tất, nên phương thức `getPrice` vẫn là phương thức đồng bộ.

Khi timeout xảy ra, `cancel(true)` yêu cầu thread đang chạy Future nhận interrupt. Đây là cơ chế hủy hợp tác, không phải lệnh dừng cưỡng bức. Tác vụ đang ngủ hoặc chờ ở API có hỗ trợ interrupt có thể dừng; vòng lặp CPU, thư viện bỏ qua interrupt hoặc I/O không hỗ trợ hủy vẫn có thể tiếp tục chạy. Nếu `cancelRunningFuture` là `false`, Future tiếp tục chạy và caller chỉ ngừng chờ kết quả.

Vì thế, hãy cấu hình timeout riêng cho HTTP client, JDBC driver hoặc SDK. Nếu TimeLimiter trả fallback sau 800 ms nhưng HTTP client vẫn giữ socket trong 30 giây, worker và connection vẫn có thể bị chiếm sau khi caller đã nhận kết quả dự phòng.

## 4. Dùng TimeLimiter với CompletionStage

Với CompletionStage, dùng `executeCompletionStage(scheduler, supplier)`. Phương thức trả về stage ngay; một tác vụ trên `ScheduledExecutorService` theo dõi thời hạn và hoàn tất stage với `TimeoutException` nếu deadline đến trước khi nguồn hoàn tất.

Scheduler chỉ dùng để kích hoạt timeout. Nó không tự chạy lời gọi tới dependency. Công việc cần được thực hiện bởi một executor riêng hoặc HTTP client bất đồng bộ. Ví dụ:

```java
public CompletionStage<Price> getPriceAsync(String isbn) {
    Supplier<CompletableFuture<Price>> request = () ->
            CompletableFuture.supplyAsync(
                    () -> pricingClient.fetch(isbn),
                    pricingExecutor
            );

    return timeLimiter.executeCompletionStage(timeoutScheduler, request)
            .exceptionally(error -> Price.unavailable(isbn));
}
```

`pricingExecutor` chạy công việc thực tế; `timeoutScheduler` chỉ lập lịch tác vụ hết hạn. Hai executor này có trách nhiệm khác nhau và nên được tạo, cấu hình, đóng theo vòng đời ứng dụng, không tạo mới cho từng request.

Không viết `CompletableFuture.completedFuture(pricingClient.fetch(isbn))` nếu `fetch` là blocking. Java phải thực thi `fetch` trước khi tạo `completedFuture`, vì vậy thread gọi vẫn bị chặn trước khi TimeLimiter có thể áp dụng deadline. Dùng `supplyAsync` với executor tách biệt hoặc API HTTP trả về CompletionStage thật sự.

Ở nhánh CompletionStage, timeout làm stage được bảo vệ hoàn tất bất thường. Điều đó không đồng nghĩa tác vụ nguồn đã dừng. `CompletionStage` không có hợp đồng hủy tác vụ giống `Future.cancel`; nếu cần dừng I/O, dùng API cancellation của HTTP client hoặc driver và đặt timeout ở chính client.

Khi caller cần lấy kết quả trong một test hoặc tại một ranh giới đồng bộ, `stage.toCompletableFuture().get()` sẽ chặn và có thể ném `ExecutionException` với `TimeoutException` ở phần nguyên nhân. Trong mã ứng dụng bất đồng bộ, tiếp tục bằng `thenApply`, `handle` hoặc `exceptionally` thay vì gọi `get()` hoặc `join()`.

## 5. Kết hợp CompletionStage với Circuit Breaker

Nếu chỉ dùng TimeLimiter, ứng dụng có timeout nhưng chưa có sliding window và trạng thái `CLOSED`/`OPEN`/`HALF_OPEN`. Để Circuit Breaker ghi nhận timeout như một lần thực thi thất bại, hãy bọc CompletionStage bằng cả hai decorator. Circuit Breaker phải quan sát stage đã được TimeLimiter giới hạn:

```java
Supplier<CompletionStage<Price>> request = () ->
        CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );

Supplier<CompletionStage<Price>> timedRequest =
        timeLimiter.decorateCompletionStage(timeoutScheduler, request);

Supplier<CompletionStage<Price>> protectedRequest =
        CircuitBreaker.decorateCompletionStage(circuitBreaker, timedRequest);

return protectedRequest.get()
        .exceptionally(error -> Price.unavailable(isbn));
```

Trong ví dụ, TimeLimiter hoàn tất stage bằng timeout nếu lời gọi quá lâu; Circuit Breaker nhận kết quả stage và ghi nhận lỗi. Fallback được áp dụng sau Circuit Breaker để lỗi timeout vẫn được ghi vào thống kê. Nếu chuyển lỗi thành kết quả thành công trước khi Circuit Breaker quan sát stage, breaker có thể ghi nhận thành công và không mở mạch dù dependency đang chậm.

Thứ tự decorator quyết định lớp nào nhìn thấy lỗi. Khi kết hợp thêm Retry, Bulkhead hoặc RateLimiter, hãy xác định rõ một lần thử được tính như thế nào và tổng thời gian của tất cả lần thử có vượt deadline của request bên ngoài hay không.

## 6. Dùng annotation @TimeLimiter trong Spring Boot

Resilience4j Spring Boot starter cung cấp `@TimeLimiter` qua Spring AOP. Với ứng dụng Spring Boot 3, cần starter `resilience4j-spring-boot3`, Actuator và AOP. Ví dụ:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Annotation phù hợp với phương thức trả về `CompletionStage` hoặc `CompletableFuture`. Ví dụ:

```java
@Service
public class PricingService {
    private final PricingClient pricingClient;
    private final Executor pricingExecutor;

    public PricingService(PricingClient pricingClient, Executor pricingExecutor) {
        this.pricingClient = pricingClient;
        this.pricingExecutor = pricingExecutor;
    }

    @TimeLimiter(name = "pricing", fallbackMethod = "priceFallback")
    public CompletableFuture<Price> getPrice(String isbn) {
        return CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );
    }

    private CompletableFuture<Price> priceFallback(String isbn, Throwable error) {
        return CompletableFuture.completedFuture(Price.unavailable(isbn));
    }
}
```

Fallback có cùng tham số với phương thức gốc và thêm một tham số exception ở cuối. Kiểu trả về phải tương thích với phương thức được bảo vệ. Trong ví dụ, fallback nhận `Throwable` để xử lý timeout và các lỗi thực thi khác.

Phương thức được bảo vệ phải là bean Spring được gọi qua proxy AOP. Lời gọi nội bộ từ một phương thức trong cùng bean có thể bỏ qua proxy. Annotation cũng không tự chuyển một phương thức blocking trả về `Price` thành bất đồng bộ: nếu thân phương thức chạy blocking trước khi trả CompletionStage, thread gọi vẫn bị chặn. Hãy tạo CompletionStage thực sự bằng executor hoặc client bất đồng bộ.

Không dùng `@TimeLimiter` trên phương thức trả về plain value hoặc `Future` trong Spring AOP integration. Với `Future` thuần, dùng API `TimeLimiter.executeFutureSupplier`; với `CompletableFuture`, dùng `@TimeLimiter` hoặc `executeCompletionStage` tùy cách tích hợp.

## 7. Phối hợp với Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker cung cấp `Resilience4JCircuitBreakerFactory` cho lời gọi đồng bộ và cấu hình TimeLimiter theo ID. Ví dụ cấu hình một instance:

```yaml
resilience4j:
  timelimiter:
    instances:
      pricing:
        timeoutDuration: 800ms
        cancelRunningFuture: true

  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
```

Với lời gọi đồng bộ qua `circuitBreakerFactory.create("pricing").run(...)`, Spring Cloud áp dụng TimeLimiter của instance `pricing` và trả kết quả theo API đồng bộ. Cấu hình properties theo instance có ưu tiên cao hơn Java `Customizer`.

Nếu service đã dùng CompletionStage và cần bảo vệ kết quả bất đồng bộ, dùng trực tiếp API CompletionStage của Resilience4j hoặc `@TimeLimiter` của Spring Boot như các ví dụ trước. Không bọc CompletionStage vào `CircuitBreakerFactory.run` như một giá trị đồng bộ rồi cho rằng breaker sẽ chờ stage hoàn tất; cần dùng decorator CompletionStage để Circuit Breaker quan sát cả kết quả cuối cùng.

## 8. Chọn timeout và quản lý tài nguyên

Thời hạn phải phù hợp với SLA và độ trễ bình thường của dependency. Nếu timeout quá ngắn, request hợp lệ bị chuyển thành lỗi; nếu quá dài, caller giữ tài nguyên lâu và fallback đến muộn. Có thể đặt timeout theo từng instance thay vì dùng một giá trị cho tất cả dịch vụ.

Phân biệt các giới hạn:

| Giới hạn | Phạm vi |
| --- | --- |
| Connect timeout | Thời gian thiết lập kết nối tới dịch vụ |
| Read/response timeout | Thời gian chờ dữ liệu phản hồi từ client HTTP |
| TimeLimiter | Thời gian chờ của lời gọi đã được bảo vệ ở tầng ứng dụng |
| Request/gateway deadline | Tổng thời gian xử lý request, có thể bao gồm nhiều dependency và retry |

Timeout của client thường nên hết trước hoặc phù hợp với TimeLimiter để socket và connection được giải phóng. Deadline của gateway phải đủ bao quát thời gian xử lý nội bộ nhưng vẫn nằm trong giới hạn mà caller chấp nhận.

Với Future, caller thread bị chặn trong lúc chờ. Với CompletionStage, caller có thể tiếp tục xử lý bất đồng bộ, nhưng worker và connection vẫn bị giữ nếu tác vụ nguồn không dừng. Dùng Bulkhead để giới hạn số tác vụ đang chạy, theo dõi queue và từ chối sớm khi hệ thống đã hết sức chứa.

## 9. Theo dõi và kiểm chứng

Resilience4j phát các sự kiện `SUCCESS`, `ERROR` và `TIMEOUT` cho TimeLimiter. Khi có Actuator và `resilience4j-micrometer`, có thể theo dõi metrics như `resilience4j.timelimiter.calls` theo tên instance và loại kết quả. Đối chiếu metrics với số lời gọi timeout, số fallback và số tác vụ còn chạy trong executor.

Một kịch bản kiểm chứng nên bao gồm cả hai kiểu API:

1. Tạo tác vụ hoàn thành nhanh hơn timeout; xác nhận Future trả kết quả và CompletionStage hoàn tất bình thường.
2. Tạo tác vụ chậm hơn timeout; xác nhận Future path ném `TimeoutException` sau thời hạn và kiểm tra trạng thái Future/cờ interrupt.
3. Lặp lại Future path với `cancelRunningFuture: false`; xác nhận caller hết chờ nhưng tác vụ nguồn vẫn có thể hoàn tất sau đó.
4. Kiểm tra CompletionStage path; xác nhận phương thức trả stage ngay, stage phát lỗi timeout và kiểm tra xem tác vụ nguồn có tiếp tục chạy hay không.
5. Kết hợp Circuit Breaker; xác nhận timeout được ghi nhận là lỗi, fallback không che mất lỗi trước khi breaker cập nhật thống kê và mạch chuyển trạng thái khi đạt ngưỡng.
6. Kiểm tra executor, scheduler, connection pool và Bulkhead dưới tải đồng thời để phát hiện công việc bị bỏ lại sau timeout.

Trong test, có thể chờ kết quả bằng `Future.get` hoặc `CompletionStage.toCompletableFuture().get` để khẳng định thời điểm hoàn tất. Chỉ dùng thao tác blocking này trong test hoặc tại ranh giới đồng bộ có chủ đích; không đưa nó vào luồng xử lý bất đồng bộ của ứng dụng.

## 10. Lỗi thường gặp

- Dùng `Future.get()` mà quên rằng thread gọi bị chặn trong suốt thời gian chờ.
- Nghĩ `TimeLimiter` tự tạo worker thread để chạy một lời gọi blocking.
- Dùng scheduler của CompletionStage như executor chạy I/O; scheduler chỉ nên xử lý tác vụ timeout ngắn.
- Bọc lời gọi blocking trong `CompletableFuture.completedFuture(...)`, khiến công việc chạy trước khi stage được tạo.
- Cho rằng `cancelRunningFuture: true` đảm bảo mọi tác vụ nguồn dừng ngay; `Future.cancel(true)` chỉ gửi interrupt và CompletionStage không có bảo đảm hủy công việc nguồn.
- Dùng fallback trước Circuit Breaker khiến timeout bị chuyển thành kết quả thành công và không được ghi nhận là lỗi.
- Dùng `@TimeLimiter` trên phương thức không trả CompletionStage/CompletableFuture hoặc gọi nội bộ khiến Spring AOP không áp dụng.
- Đặt TimeLimiter dài hơn timeout của gateway hoặc quá ngắn so với SLA của dependency.
- Không đóng executor và scheduler khi ứng dụng shutdown.

## Tài liệu tham khảo

- [Resilience4j – TimeLimiter](https://resilience4j.readme.io/docs/timeout): `TimeLimiterConfig`, `Future`, `CompletionStage`, scheduler và cách decorate lời gọi.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): cấu hình instance, annotation `@TimeLimiter`, fallback và metrics.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): cấu hình TimeLimiter theo instance, Customizer và tích hợp với factory.
- [Java – CompletionStage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): hợp đồng xử lý bất đồng bộ và chuỗi callback.
- [Java – Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): lấy kết quả, timeout và cancellation.
