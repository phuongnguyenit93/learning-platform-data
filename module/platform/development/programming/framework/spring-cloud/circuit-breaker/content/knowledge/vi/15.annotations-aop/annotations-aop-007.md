# Kiểu trả về đồng bộ, bất đồng bộ và reactive

Resilience4j tích hợp với Spring AOP bằng các annotation như `@CircuitBreaker`, `@Retry`, `@RateLimiter`, `@Bulkhead` và `@TimeLimiter`. Cách một annotation bảo vệ lời gọi phụ thuộc vào kiểu trả về của phương thức. Một phương thức trả `Stock` thực thi đồng bộ; một phương thức trả `CompletableFuture<Stock>` công bố kết quả bất đồng bộ; còn `Mono<Stock>` hoặc `Flux<Stock>` mô tả một pipeline reactive được thực thi khi có subscription.

Với Spring Cloud Circuit Breaker, ứng dụng cũng có thể chọn API tường minh qua `CircuitBreakerFactory` cho lời gọi đồng bộ hoặc `ReactiveCircuitBreakerFactory` cho `Mono`/`Flux`. Hiểu đúng ranh giới kiểu trả về giúp Circuit Breaker quan sát đúng thời điểm thành công, lỗi, timeout và fallback, đồng thời tránh chặn event-loop của WebFlux.

## 1. Ba kiểu thực thi và thời điểm ghi nhận kết quả

| Kiểu trả về | Cách thực thi | Khi nào biết kết quả? | API thường dùng |
| --- | --- | --- | --- |
| `T` hoặc `void` | Phương thức chạy đồng bộ trên thread gọi | Khi thân phương thức kết thúc hoặc ném exception | Annotation AOP đồng bộ; `CircuitBreakerFactory` |
| `CompletableFuture<T>` / `CompletionStage<T>` | Phương thức trả về một handle cho công việc bất đồng bộ | Khi stage hoàn tất thành công hoặc lỗi | Annotation AOP cho async; API decorator CompletionStage |
| `Mono<T>` / `Flux<T>` | Pipeline reactive, thường lazy và non-blocking | Khi subscriber kích hoạt và publisher phát tín hiệu terminal hoặc lỗi | Annotation với `resilience4j-reactor`; Reactor operators; `ReactiveCircuitBreakerFactory` |

Annotation không tự biến một phương thức blocking trả về `T` thành bất đồng bộ. Nếu thân phương thức gọi HTTP client đồng bộ và chờ 5 giây, thread gọi vẫn bị giữ trong 5 giây. Tương tự, khai báo kiểu trả về `CompletableFuture` nhưng gọi blocking trước khi tạo future vẫn chặn thread gọi.

Với `Mono`/`Flux`, việc tạo publisher thường chưa gửi request. Circuit Breaker cần bọc pipeline để permission và kết quả được ghi nhận theo subscription. Không tự gọi `subscribe()` trong service/controller và không gọi `.block()` trong luồng WebFlux.

## 2. Chuẩn bị dependency cho annotation và reactive

Với Spring Boot 3 dùng Resilience4j trực tiếp, starter cần Actuator và Spring AOP:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Nếu ứng dụng dùng WebFlux và muốn dùng các annotation/reactive extension của Resilience4j với Reactor, thêm `resilience4j-reactor` theo BOM đang quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'io.github.resilience4j:resilience4j-reactor'
}
```

Spring Cloud CircuitBreaker có các starter riêng. Lời gọi đồng bộ dùng `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j`; lời gọi reactive dùng `org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j`. Quản lý phiên bản bằng Spring Cloud BOM tương thích với Spring Boot. Chọn một đường tích hợp làm API chính cho từng lời gọi để tránh bọc cùng dependency bằng hai Circuit Breaker độc lập.

## 3. Kiểu trả về đồng bộ: T và void

Với phương thức trả về giá trị thông thường, annotation AOP bọc thời gian thực thi của phương thức. Nếu thân phương thức trả về bình thường, kết quả được ghi nhận là thành công; nếu ném exception, aspect có thể ghi nhận lỗi và gọi fallback.

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock stockFallback(String sku, CallNotPermittedException error) {
        return Stock.unavailable(sku, "CIRCUIT_OPEN");
    }

    public Stock stockFallback(String sku, Throwable error) {
        return Stock.unavailable(sku, "DEPENDENCY_ERROR");
    }
}
```

Trong ví dụ, `getStock` trả `Stock` trực tiếp. `CallNotPermittedException` xảy ra khi Circuit Breaker không cấp quyền gọi, chẳng hạn mạch đang `OPEN`; fallback tổng quát xử lý lỗi còn lại. Các kiểu `Stock`, `InventoryClient` và constructor chỉ minh họa cấu trúc ứng dụng.

Phương thức đồng bộ phù hợp với client blocking và Spring MVC, nhưng thread gọi phải chờ. Nếu cần giới hạn thời gian chờ cho lời gọi blocking, hãy cấu hình timeout ngay trên HTTP client/driver và xem xét `TimeLimiter` thông qua API hỗ trợ Future hoặc Spring Cloud CircuitBreaker. `@TimeLimiter` không thể đo thời gian một phương thức đã trả về giá trị đồng bộ sau khi nó hoàn tất.

Không dùng `@TimeLimiter` trên phương thức trả `String`, `Stock`, primitive hoặc `void` rồi kỳ vọng nó tự chuyển công việc sang thread khác. Nếu cần cách chạy đồng bộ có deadline, dùng API `executeFutureSupplier` của Resilience4j hoặc factory Spring Cloud với cấu hình TimeLimiter; cân nhắc thêm Bulkhead để giới hạn số công việc blocking.

## 4. Kiểu trả về bất đồng bộ: CompletableFuture và CompletionStage

`CompletableFuture<T>` là một implementation của cả `Future<T>` và `CompletionStage<T>`. Nó cho phép phương thức trả về ngay trong khi công việc tiếp tục trên executor. Resilience4j hỗ trợ các aspect như `@CircuitBreaker`, `@Retry`, `@RateLimiter` và `@Bulkhead` với kiểu bất đồng bộ `CompletableFuture`. `@TimeLimiter` cũng cần một kết quả bất đồng bộ để gắn deadline.

```java
@Service
public class PricingService {
    private final PricingClient pricingClient;
    private final Executor pricingExecutor;

    public PricingService(PricingClient pricingClient, Executor pricingExecutor) {
        this.pricingClient = pricingClient;
        this.pricingExecutor = pricingExecutor;
    }

    @CircuitBreaker(name = "pricing", fallbackMethod = "priceFallback")
    @TimeLimiter(name = "pricing")
    public CompletableFuture<Price> getPrice(String isbn) {
        return CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );
    }

    public CompletableFuture<Price> priceFallback(String isbn, Throwable error) {
        return CompletableFuture.completedFuture(Price.unavailable(isbn));
    }
}
```

`pricingExecutor` là executor do ứng dụng quản lý vòng đời. `supplyAsync` đưa lời gọi blocking vào executor đó; nếu `pricingClient` đã có API async thật sự, hãy dùng trực tiếp CompletionStage mà client trả về thay vì bọc thêm một thread.

Trong ví dụ, TimeLimiter không khai báo fallback riêng để `TimeoutException` truyền ra ngoài aspect của nó. Theo thứ tự aspect mặc định, Circuit Breaker nằm bên ngoài TimeLimiter nên có thể ghi nhận timeout trước khi `priceFallback` chuyển lỗi thành kết quả dự phòng. Nếu fallback của TimeLimiter xử lý lỗi trước, aspect Circuit Breaker bên ngoài có thể chỉ nhìn thấy một stage hoàn tất thành công.

Không viết `CompletableFuture.completedFuture(pricingClient.fetch(isbn))` khi `fetch` là blocking. Java sẽ gọi `fetch` trước khi tạo future, nên thread hiện tại vẫn bị chặn. Cũng không dùng `ForkJoinPool.commonPool()` một cách mặc định cho I/O blocking nếu chưa đánh giá tải và chính sách thread của ứng dụng.

`@TimeLimiter` giới hạn thời gian chờ stage theo cấu hình của instance `pricing`. `cancelRunningFuture` có thể yêu cầu hủy Future khi hết hạn, nhưng cancellation không đảm bảo mọi tác vụ nguồn dừng ngay. Hãy cấu hình timeout trên HTTP client/driver và xác minh API client có hỗ trợ hủy request.

Với AOP, ưu tiên khai báo `CompletableFuture` rõ ràng để aspect nhận diện kiểu trả về. API lập trình của Resilience4j có thể nhận `Future` trong `executeFutureSupplier`, nhưng điều đó không có nghĩa mọi annotation aspect đều hỗ trợ `Future` thuần theo cùng cách. Kiểm tra tài liệu của phiên bản đang dùng; không dùng `Future` thuần cho `@TimeLimiter` nếu aspect yêu cầu `CompletionStage`.

## 5. Kiểu trả về reactive: Mono và Flux

`Mono<T>` phát tối đa một phần tử; `Flux<T>` có thể phát nhiều phần tử. Cả hai thường chỉ bắt đầu công việc khi có subscription. Resilience4j cung cấp module `resilience4j-reactor` để các aspect/reactive operators xử lý publisher. Với Spring Cloud CircuitBreaker, có thể dùng `ReactiveCircuitBreakerFactory` để bọc `Mono` hoặc `Flux` và cung cấp fallback trả về publisher.

Ví dụ dùng annotation với `Mono`:

```java
@Service
public class ReactiveInventoryService {
    private final WebClient webClient;

    public ReactiveInventoryService(WebClient webClient) {
        this.webClient = webClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Mono<Stock> getStock(String sku) {
        return webClient.get()
                .uri("/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(Stock.class);
    }

    public Mono<Stock> stockFallback(String sku, CallNotPermittedException error) {
        return Mono.just(Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    public Mono<Stock> stockFallback(String sku, Throwable error) {
        return Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }
}
```

Fallback có kiểu `Mono<Stock>` tương thích với phương thức gốc. Có thể dùng `Flux<T>` tương tự; fallback phải trả `Flux<T>`. Nếu fallback cũng phát lỗi, lỗi tiếp tục tới subscriber. Chỉ dùng `Flux.empty()` khi hợp đồng nghiệp vụ thật sự cho phép coi sự cố là luồng không có phần tử.

Với reactive, permission của Circuit Breaker được xét khi pipeline được subscribe. Mỗi subscription có thể tạo một lần thực thi riêng. Vì vậy, tránh subscribe nhiều lần vào cùng publisher nếu không muốn gửi request nhiều lần. Dùng `cache()` hoặc `share()` chỉ khi ngữ nghĩa chia sẻ kết quả giữa subscriber phù hợp với ứng dụng; hai operator này có ảnh hưởng tới vòng đời và việc thực thi lại pipeline.

### Bọc reactive bằng Spring Cloud CircuitBreaker

Nếu ứng dụng dùng abstraction của Spring Cloud, có thể dùng `ReactiveCircuitBreakerFactory` thay cho annotation:

```java
public Mono<Stock> getStock(String sku) {
    Mono<Stock> request = webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);

    return reactiveCircuitBreakerFactory.create("inventory").run(
            request,
            error -> Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"))
    );
}
```

`ReactiveCircuitBreakerFactory.create("inventory")` tạo breaker có ID `inventory`. Phương thức `run` nhận `Mono` hoặc `Flux` và hàm fallback nhận `Throwable`, trả publisher tương ứng. Cách này làm ranh giới bảo vệ hiện rõ trong mã và không phụ thuộc vào việc method invocation đi qua proxy annotation.

### TimeLimiter với Reactor

Reactor cần một timeout áp dụng cho vòng đời publisher. Có thể dùng `TimeLimiterOperator` từ `resilience4j-reactor`, hoặc toán tử `.timeout(...)` của Reactor khi deadline chỉ cần ở tầng pipeline. Ví dụ dùng operator của Resilience4j:

```java
Mono<Stock> protectedRequest = Mono.fromCallable(() -> blockingInventoryClient.getStock(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .transformDeferred(TimeLimiterOperator.of(timeLimiter))
        .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
        .onErrorResume(error -> Mono.just(
                Stock.unavailable(sku, "DEPENDENCY_ERROR_OR_TIMEOUT")));
```

`subscribeOn(Schedulers.boundedElastic())` chuyển lời gọi blocking sang scheduler phù hợp cho tác vụ blocking, không chạy nó trên event-loop. `TimeLimiterOperator` đặt timeout cho publisher; `CircuitBreakerOperator` ở ngoài để quan sát cả lỗi timeout. Fallback `onErrorResume` được đặt sau hai operator để Circuit Breaker nhìn thấy lỗi trước khi chuyển thành dữ liệu dự phòng.

Với `Mono`, timeout áp dụng cho thời gian chờ tín hiệu hoàn tất. Với `Flux`, Reactor timeout thường theo dõi khoảng im lặng giữa các tín hiệu; một luồng phát phần tử đều đặn có thể tiếp tục lâu hơn `timeoutDuration`. Nếu nghiệp vụ cần giới hạn tổng thời gian sống của toàn bộ stream, hãy định nghĩa deadline tổng riêng và kiểm thử đúng semantics đó, không mặc định timeout giữa các tín hiệu là giới hạn tổng thời gian.

Với WebClient vốn đã non-blocking, không cần bọc lời gọi trong `fromCallable` hoặc chuyển sang `boundedElastic`. Có thể bọc trực tiếp publisher WebClient. Khi dùng annotation `@TimeLimiter` với `Mono`/`Flux`, bảo đảm `resilience4j-reactor` có mặt và kiểm tra phiên bản starter/aspect đang dùng; operator tường minh là lựa chọn dễ kiểm soát khi cần xác định chính xác timeout áp dụng cho pipeline.

## 6. Bảng tương thích thực hành

| Annotation / API | T đồng bộ | CompletableFuture / CompletionStage | Mono / Flux |
| --- | --- | --- | --- |
| `@CircuitBreaker` | Có | Có | Có với Reactor extension |
| `@Retry` | Có | Có | Có với Reactor extension |
| `@RateLimiter` | Có | Có | Có với Reactor extension |
| `@Bulkhead` | Có; mặc định semaphore | Có; có thể chọn thread-pool bulkhead | Có với Reactor extension |
| `@TimeLimiter` | Không dùng với plain value/void | Dùng với CompletionStage/CompletableFuture | Có với Reactor extension ở các phiên bản hỗ trợ; kiểm tra dependency và version |
| Spring Cloud `CircuitBreakerFactory` | API đồng bộ | Không phải API reactive chuyên biệt | Không; dùng factory reactive |
| Spring Cloud `ReactiveCircuitBreakerFactory` | Không | Không | Có; nhận Mono/Flux |

Bảng mô tả cách dùng phổ biến của Spring Boot starter và Spring Cloud CircuitBreaker. Chi tiết return type được hỗ trợ, package AOP và cách fallback có thể thay đổi theo major/minor version. Kiểm tra dependency tree và tài liệu đúng release train trước khi áp dụng vào dự án.

## 7. AOP proxy: vì sao annotation đôi khi không chạy?

Annotation Resilience4j được thực thi bởi Spring AOP aspect. Spring tạo proxy cho bean và aspect chỉ chạy khi lời gọi đi qua proxy đó. Vì vậy:

- Đặt annotation trên phương thức của bean do Spring quản lý, chẳng hạn `@Service` hoặc `@Component`.
- Gọi phương thức từ bean khác thông qua dependency injection để lời gọi đi qua proxy.
- Lời gọi nội bộ `this.getStock(...)` trong cùng bean thường không đi qua proxy, nên aspect có thể bị bỏ qua.
- Không gọi trực tiếp constructor để tự tạo instance của service có annotation; instance đó không được Spring proxy.
- Kiểm tra proxy mode và khả năng proxy phương thức của class trong dự án. Với JDK proxy, phương thức phải nằm trên interface được proxy; với class-based proxy, các giới hạn của proxy class như phương thức `final` cần được lưu ý.

Ví dụ self-invocation dễ gây nhầm:

```java
@Service
public class OrderService {
    public Order getOrder(String id) {
        return loadProtected(id);
    }

    @CircuitBreaker(name = "orders")
    public Order loadProtected(String id) {
        return orderClient.getOrder(id);
    }
}
```

`getOrder` gọi `loadProtected` qua `this` bên trong cùng bean, vì vậy lời gọi có thể bỏ qua proxy và `@CircuitBreaker` không được áp dụng. Có thể tách phần được bảo vệ thành một bean riêng rồi inject vào `OrderService`, hoặc dùng API decorator/factory tường minh.

## 8. Fallback phải khớp kiểu trả về

Fallback method của annotation thường nằm trong cùng class với phương thức được bảo vệ, nhận cùng tham số nghiệp vụ và thêm đúng một tham số exception ở cuối. Kiểu trả về cần tương thích với kiểu trả về gốc:

| Phương thức được bảo vệ | Kiểu fallback |
| --- | --- |
| `Stock getStock(String sku)` | `Stock fallback(String sku, Throwable error)` |
| `CompletableFuture<Price> getPrice(String isbn)` | `CompletableFuture<Price> fallback(String isbn, Throwable error)` |
| `Mono<Stock> getStock(String sku)` | `Mono<Stock> fallback(String sku, Throwable error)` |
| `Flux<Event> events(String id)` | `Flux<Event> fallback(String id, Throwable error)` |

Nếu có nhiều fallback cùng tên với các kiểu exception khác nhau, Resilience4j chọn kiểu khớp cụ thể nhất. Có thể có fallback tổng quát nhận `Throwable`, nhưng không nên nuốt mọi lỗi. Giữ nguyên lỗi đầu vào hoặc lỗi lập trình mà ứng dụng không thể phục hồi.

Fallback cho `CompletableFuture` phải trả future đã hoàn tất hoặc một future async mới; fallback cho `Mono`/`Flux` phải trả publisher. Không gọi `.block()` trong fallback reactive và không trả `Stock` trực tiếp từ fallback của `Mono<Stock>`.

## 9. Thứ tự các aspect và tác động lên kết quả

Khi đặt nhiều annotation trên cùng phương thức, thứ tự aspect quyết định lớp nào nhìn thấy lỗi và số lần lời gọi được ghi nhận. Resilience4j mô tả thứ tự mặc định theo dạng lồng nhau:

```text
Retry(
  CircuitBreaker(
    RateLimiter(
      TimeLimiter(
        Bulkhead(method)
      )
    )
  )
)
```

Với thứ tự này, Retry ở ngoài nên có thể thực hiện lại toàn bộ chuỗi bên trong; Circuit Breaker có thể quan sát từng lần thực thi tùy vị trí của nó trong chuỗi. Nếu muốn Circuit Breaker chỉ ghi nhận kết quả sau toàn bộ lượt Retry, cần thiết kế thứ tự phù hợp và xác minh bằng test. Có thể cấu hình order của aspect qua các thuộc tính `resilience4j.retry.retryAspectOrder`, `resilience4j.circuitbreaker.circuitBreakerAspectOrder`, `resilience4j.ratelimiter.rateLimiterAspectOrder`, `resilience4j.timelimiter.timeLimiterAspectOrder` và `resilience4j.bulkhead.bulkheadAspectOrder`.

Nếu thứ tự phức tạp hoặc cần kiểm soát chính xác cách decorator bao quanh publisher, dùng functional chaining thay vì xếp nhiều annotation. Ghi rõ một lỗi được tính là một lần gọi hay nhiều lần thử; điều đó ảnh hưởng trực tiếp tới sliding window và ngưỡng mở mạch.

## 10. Kịch bản kiểm chứng theo từng kiểu trả về

Kiểm thử bằng mock client hoặc mock server để điều khiển kết quả và độ trễ:

1. **Đồng bộ:** gọi method trả `T` với dependency thành công rồi lỗi. Xác nhận aspect ghi nhận kết quả và fallback đồng bộ có kiểu trả về đúng.
2. **Bất đồng bộ:** trả một `CompletableFuture` hoàn tất bình thường, sau đó một future hoàn tất exceptional. Xác nhận Circuit Breaker ghi nhận kết quả khi stage hoàn tất, không phải lúc method trả future.
3. **Timeout async:** làm future hoàn tất chậm hơn `timeoutDuration`. Xác nhận caller nhận timeout/fallback; kiểm tra cancellation và trạng thái tác vụ nguồn.
4. **Reactive Mono:** xác nhận pipeline chưa gọi dependency trước subscription; subscribe một lần thì có một request; lỗi upstream đi tới fallback.
5. **Reactive Flux:** kiểm tra publisher phát nhiều phần tử, hoàn tất bình thường và phát lỗi giữa luồng. Xác nhận semantics fallback đúng với hợp đồng API.
6. **AOP proxy:** gọi bean từ một bean khác rồi so sánh với self-invocation. Xác nhận trường hợp qua proxy có aspect và trường hợp nội bộ không được bảo vệ như mong đợi.
7. **Thiếu Reactor extension:** chạy kiểm tra cấu hình với và không có `resilience4j-reactor` để xác nhận ứng dụng đã nạp đúng extension cho Mono/Flux.
8. **Aspect order:** kết hợp Retry và Circuit Breaker, tạo một lỗi rồi phục hồi ở lần sau; kiểm tra số lần gọi, số lỗi ghi vào sliding window và fallback.

Không chỉ kiểm tra giá trị cuối cùng. Với CompletableFuture và Reactor, hãy xác nhận thời điểm ghi nhận kết quả, số lần subscription, số request thực tế và exception được chuyển qua từng lớp bảo vệ.

## 11. Lỗi thường gặp

- Dùng `@TimeLimiter` trên phương thức trả plain value và mong đợi AOP tự chạy phương thức trên worker thread.
- Trả `CompletableFuture` nhưng thực hiện I/O blocking trước khi future được tạo.
- Dùng `Future` thuần cho annotation async mà không xác minh return type mà aspect của phiên bản hỗ trợ.
- Dùng `Mono`/`Flux` nhưng thiếu `resilience4j-reactor`, khiến extension reactive không được đăng ký.
- Gọi `.block()` hoặc `subscribe()` trong service WebFlux, làm chặn event-loop hoặc tạo subscription ngoài dự kiến.
- Gọi phương thức có annotation qua self-invocation nên không đi qua Spring AOP proxy.
- Fallback trả `T` trong khi phương thức gốc trả `Mono<T>` hoặc `CompletableFuture<T>`.
- Đặt fallback trước Circuit Breaker và biến lỗi thành dữ liệu thành công trước khi breaker ghi nhận.
- Dùng cùng lúc Spring Cloud factory và annotation Resilience4j cho cùng một lời gọi mà không có chủ đích, tạo nhiều breaker độc lập.
- Không kiểm tra thứ tự aspect khi kết hợp Retry, Circuit Breaker, TimeLimiter và Bulkhead.

## Tài liệu tham khảo

- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): starter, AOP annotations, return types, fallback method và aspect order.
- [Resilience4j – Examples for Reactor](https://resilience4j.readme.io/docs/examples-1): CircuitBreakerOperator, RateLimiterOperator, BulkheadOperator, RetryOperator và hỗ trợ Mono/Flux.
- [Resilience4j – TimeLimiter](https://resilience4j.readme.io/docs/timeout): TimeLimiter với Future/CompletionStage và scheduler.
- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` và cách bọc Mono/Flux.
- [Spring Cloud CircuitBreaker – Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): starter đồng bộ/reactive và cấu hình implementation.
