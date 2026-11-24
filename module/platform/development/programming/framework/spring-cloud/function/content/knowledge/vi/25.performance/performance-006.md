# Lựa chọn xử lý đồng bộ hoặc phản ứng theo tải thực tế

Spring Cloud Function cho phép biểu diễn nghiệp vụ bằng `Supplier<T>`, `Function<I, O>` và `Consumer<T>`, tra cứu qua `FunctionCatalog`, ghép các hàm thành composition và triển khai cùng logic qua HTTP, sự kiện hoặc môi trường serverless. Khi một function nhận request, gọi database hoặc API bên ngoài rồi trả kết quả, hai mô hình thường được cân nhắc là **đồng bộ (imperative/synchronous)** và **phản ứng (reactive)**.

Lựa chọn này ảnh hưởng đến cách giữ thread, tổ chức I/O, kiểm soát concurrency, truyền lỗi, hủy tác vụ và tiêu thụ bộ nhớ. Nhưng **reactive không tự động nhanh hơn đồng bộ**. Một pipeline reactive có thể xử lý nhiều I/O đang chờ với ít thread chờ hơn nếu toàn bộ đường gọi là non-blocking. Ngược lại, một hàm CPU-bound nhỏ hoặc một ứng dụng dùng JDBC/JPA đồng bộ có thể đơn giản và hiệu quả hơn với mô hình imperative.

Trong chương **Hiệu năng**, bài học này giúp bạn quyết định theo **đặc điểm tải thực tế** thay vì theo xu hướng:

1. Phân biệt lời gọi đồng bộ trả kết quả trực tiếp với publisher `Mono/Flux` hoàn thành về sau.
2. Nhận biết workload CPU-bound, blocking I/O, non-blocking I/O, streaming và batch.
3. Viết hai phiên bản cùng nghiệp vụ bằng `Function<QuoteRequest, QuoteResult>` và `Function<Flux<QuoteRequest>, Flux<QuoteResult>>`.
4. Kiểm soát concurrency, backpressure, queue và thời gian chờ downstream.
5. Tránh `block()` hoặc tự `subscribe()` sai chỗ trong reactive function.
6. Xử lý JDBC/JPA, transaction, context, lỗi và retry theo đúng execution model.
7. Đo p50/p95/p99, throughput, thread usage, allocation và error rate để chọn mô hình phù hợp.

> **Phạm vi ví dụ:** Java 17+ và Spring Cloud Function trên phiên bản Spring Boot/Spring Framework tương thích. `RestClient` có từ Spring Framework 6.1; ví dụ reactive dùng Spring WebFlux, Reactor và `WebClient`. Virtual threads chỉ áp dụng khi chạy JDK 21+ và cấu hình runtime hỗ trợ. Kiểm tra dependency, adapter và API của phiên bản dự án trước khi áp dụng.

## 1. Hai mô hình xử lý khác nhau ở đâu?

### Đồng bộ: trả kết quả ngay trong lời gọi

Một function imperative thường có dạng:

```java
Function<QuoteRequest, QuoteResult>
```

Khi caller gọi `apply(request)`, hàm thực hiện các bước rồi trả `QuoteResult` hoặc ném exception. Nếu thân hàm gọi HTTP đồng bộ hoặc JDBC, thread hiện tại thường **chờ** cho đến khi I/O hoàn tất.

```text
Thread T1
  ├─ nhận request
  ├─ gọi pricing API đồng bộ
  ├─ chờ response             ← thread đang bị chiếm
  ├─ tính kết quả
  └─ trả QuoteResult
```

Điểm mạnh là luồng điều khiển dễ đọc, stack trace trực tiếp, tích hợp thuận với thư viện blocking và transaction đồng bộ. Điểm cần quản lý là **số thread bị giữ khi chờ I/O**.

### Reactive: trả về publisher mô tả công việc

Một hàm reactive có thể có dạng:

```java
Function<Flux<QuoteRequest>, Flux<QuoteResult>>
```

Lời gọi `apply(requests)` thường **xây dựng publisher**, chưa có nghĩa mọi request đã được xử lý. Công việc bắt đầu khi publisher được subscribe. Với I/O non-blocking, thread có thể được giải phóng trong lúc chờ network, rồi tiếp tục khi có signal.

```text
Reactive pipeline
  ├─ nhận signal request
  ├─ gửi I/O non-blocking
  ├─ trả quyền điều khiển cho event loop
  ├─ response đến → tiếp tục pipeline
  └─ phát QuoteResult
```

Điểm mạnh là phối hợp nhiều tác vụ I/O đồng thời với ít thread chờ hơn, composition bất đồng bộ, cancellation và backpressure trong những đoạn hỗ trợ Reactive Streams. Đổi lại, execution model khác: lazy subscription, operator concurrency, context propagation, lỗi theo signal và debugging phức tạp hơn.

| Tiêu chí | Đồng bộ | Reactive |
| --- | --- | --- |
| Kết quả | Giá trị `T` hoặc exception | Publisher `Mono<T>`/`Flux<T>` |
| Thời điểm xử lý | Trong lời gọi method | Thường sau subscription |
| I/O blocking | Giữ thread trong lúc chờ | Có thể nhường thread nếu client non-blocking |
| Concurrency | Thread pool, request threads, virtual threads | Scheduler/event loop và subscriptions |
| Backpressure | Tự giới hạn queue/concurrency | Có protocol Reactive Streams trong publisher chain |
| Stack trace | Thường trực tiếp | Có thể qua nhiều asynchronous boundaries |
| JDBC/JPA | Tích hợp tự nhiên | Blocking; cần cô lập hoặc dùng driver reactive |
| Streaming | Phải tự quản lý iterator/callback | `Flux<T>` biểu diễn luồng phần tử |
| Complexity | Thường thấp hơn với flow tuần tự | Cao hơn nếu team chưa quen Reactor |
| Hiệu năng | Có thể rất tốt với workload phù hợp | Có thể tốt với I/O concurrency/streaming phù hợp |

Không có kết luận “reactive luôn nhanh hơn” hoặc “đồng bộ luôn tốt hơn”. Cần so sánh trên cùng nghiệp vụ, adapter, dependency, tải và SLA.

## 2. CPU-bound và I/O-bound quyết định nhiều hơn cú pháp

Trước khi chọn mô hình, phân loại công việc chính:

| Workload | Ví dụ | Đặc điểm | Hướng nên thử trước |
| --- | --- | --- | --- |
| CPU-bound | Hashing, tính toán, chuyển đổi số lượng lớn | Dùng CPU liên tục, ít chờ I/O | Imperative hoặc reactive với CPU work được giới hạn |
| Blocking I/O | JDBC, JPA, file blocking, SDK đồng bộ | Thread chờ database/network/disk | Imperative; hoặc cô lập blocking work |
| Non-blocking I/O | WebClient/Reactor Netty, R2DBC | Có thể nhường thread khi chờ | Reactive khi concurrency cao |
| Streaming | Event stream, feed dữ liệu liên tục | Cần quản lý tốc độ và memory | Reactive khi adapter/source hỗ trợ |
| Batch hữu hạn | Xử lý 100–10.000 records | Có thể chia lô và giới hạn song song | Cả hai; đo throughput và tail latency |
| Ít request, I/O ngắn | API nội bộ tải thấp | Overhead pipeline có thể không đáng | Imperative thường dễ vận hành |

### CPU-bound không tự được tăng tốc bởi reactive

Nếu function thực hiện một vòng lặp CPU 10 ms và không có I/O, bọc kết quả trong `Mono.fromCallable(...)` không làm phép tính hoàn tất nhanh hơn. Nếu chạy nhiều tác vụ CPU song song hơn số core, hệ thống có thể tăng context switching và contention.

Reactive hữu ích khi một tác vụ có thể **nhường thread trong lúc chờ**, không phải chỉ vì kiểu trả về là `Mono`.

### Blocking I/O không biến thành non-blocking chỉ vì được bọc bằng Mono

`Mono.fromCallable(() -> jdbcRepository.findById(id))` chỉ trì hoãn việc gọi. Nó **không tự chọn scheduler**. Nếu publisher được subscribe trên event loop, JDBC vẫn block event loop.

Khi bắt buộc dùng thư viện blocking trong reactive pipeline, phải cô lập bằng scheduler phù hợp và giới hạn concurrency; tốt hơn nữa, cân nhắc driver non-blocking nếu hệ thống và transaction model cho phép.

## 3. Một nghiệp vụ, hai cách triển khai

Ví dụ dịch vụ báo giá: một request chứa mã sản phẩm và số lượng; hệ thống gọi pricing service, trả tổng tiền. DTO dùng chung:

```java
package demo.performance;

public record QuoteRequest(String sku, int quantity) {}
```

```java
package demo.performance;

public record QuoteResult(
    String sku,
    int quantity,
    long totalVnd
) {}
```

Endpoint bên dưới là host minh họa:

```text
https://pricing.example.internal/v1/quotes
```

Đây không phải API công khai để gọi. Trong ứng dụng thật, host phải đến từ cấu hình tin cậy; không nhận URL tùy ý từ payload người dùng.

### Phiên bản đồng bộ

```java
package demo.performance;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class BlockingQuoteFunctions {

    @Bean("quoteBlocking")
    public Function<QuoteRequest, QuoteResult> quoteBlocking(
        RestClient pricingRestClient
    ) {
        return request -> {
            if (request == null ||
                request.sku() == null ||
                request.sku().isBlank() ||
                request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request"
                );
            }

            QuoteResult result = pricingRestClient.post()
                .uri("/v1/quotes")
                .body(request)
                .retrieve()
                .body(QuoteResult.class);

            if (result == null) {
                throw new IllegalStateException(
                    "Pricing service returned an empty body"
                );
            }
            return result;
        };
    }
}
```

Ví dụ giả định `RestClient` đã được cấu hình và tiêm từ bean dùng chung. Function nhận DTO, validate, gọi API đồng bộ và trả DTO. Trong thời gian HTTP call chờ, thread thực thi function bị giữ.

### Phiên bản reactive

```java
package demo.performance;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class ReactiveQuoteFunctions {

    @Bean("quoteReactive")
    public Function<
        Flux<QuoteRequest>,
        Flux<QuoteResult>
    > quoteReactive(
        @Qualifier("pricingWebClient") WebClient client
    ) {
        return requests -> requests.flatMap(request -> {
            if (request == null ||
                request.sku() == null ||
                request.sku().isBlank() ||
                request.quantity() <= 0) {
                return Mono.error(
                    new IllegalArgumentException(
                        "Invalid quote request"
                    )
                );
            }

            return client.post()
                .uri("/v1/quotes")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(QuoteResult.class);
        }, 16);
    }
}
```

`flatMap(..., 16)` cho phép tối đa 16 inner publishers được xử lý đồng thời **trong subscription của pipeline này**. Đây không phải giới hạn tổng cho mọi invocation hoặc mọi replica. Nếu một publisher đại diện cho stream dài, cần policy phù hợp với tổng tải và downstream.

`flatMap` có thể phát kết quả khác thứ tự input. Khi cần giữ thứ tự, cân nhắc `flatMapSequential(...)` hoặc `concatMap(...)` và đo trade-off throughput/latency.

Hai hàm có cùng contract nghiệp vụ, nhưng không thể so sánh bằng cách chỉ gọi trực tiếp một hàm đồng bộ và một hàm reactive rồi bỏ qua adapter/subscription. Cần chạy cả hai qua đường triển khai tương đương với cùng payload.

## 4. FunctionCatalog và tên function không quyết định execution model

Spring Cloud Function có thể đăng ký function imperative và reactive vào `FunctionCatalog`. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: quoteBlocking
```

Hoặc:

```yaml
spring:
  cloud:
    function:
      definition: quoteReactive
```

Tên function giúp chọn bean/chuỗi để expose hoặc invoke. **Chỉ đổi tên từ `quoteBlocking` sang `quoteReactive` không tự biến JDBC thành non-blocking**; chữ ký, code bên trong, client và adapter phải tương thích.

| Kiểu | Mô tả |
| --- | --- |
| `Function<QuoteRequest, QuoteResult>` | Một giá trị vào, một giá trị ra theo lời gọi đồng bộ |
| `Function<Mono<QuoteRequest>, Mono<QuoteResult>>` | Một publisher vào, một publisher kết quả |
| `Function<Flux<QuoteRequest>, Flux<QuoteResult>>` | Luồng request vào, luồng kết quả ra |
| `Supplier<QuoteResult>` | Cung cấp một giá trị đồng bộ |
| `Supplier<Flux<QuoteResult>>` | Cung cấp một stream |
| `Consumer<QuoteRequest>` | Xử lý một giá trị đồng bộ |
| `Consumer<Flux<QuoteRequest>>` | Tiêu thụ một stream |

Chữ ký thực tế mà adapter hỗ trợ cần được xác nhận theo phiên bản và loại integration. Không giả định mọi broker hoặc serverless adapter đều có semantics streaming/backpressure giống WebFlux.

## 5. Đồng bộ vẫn có thể xử lý concurrency tốt

Một lỗi suy luận phổ biến là: “blocking thì mỗi request cần một platform thread, reactive mới chịu được nhiều request”. Thực tế cần xem:

- Server thread pool và queue policy.
- Outbound connection pool.
- Có dùng virtual threads (JDK 21+) hay không.
- Thời gian trung bình và tail latency của I/O.
- CPU cores, memory, downstream capacity và số replicas.

### Thread-per-request truyền thống

Với request đồng bộ, thread có thể chờ I/O. Nếu 300 request cùng chờ một API mất 200 ms, số thread bị chiếm có thể lớn, tùy server và concurrency policy.

Điều đó không có nghĩa tăng thread pool lên 10.000 là giải pháp. Thread stacks, scheduling và pool downstream có thể trở thành bottleneck.

### Virtual threads là một lựa chọn cho blocking code

JDK 21+ hỗ trợ virtual threads. Với Spring Boot phiên bản/cấu hình tương thích, ứng dụng có thể chạy nhiều tác vụ blocking mà không cần tạo một platform thread cho từng tác vụ chờ.

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Property trên chỉ có ý nghĩa trong phiên bản Spring Boot hỗ trợ và khi runtime là JDK 21+. Cần xác minh các executor/server components được tích hợp với virtual threads đúng cách.

**Virtual threads không làm JDBC hoặc HTTP blocking thành non-blocking**, và không làm database chịu được số kết nối vô hạn. Connection pool, rate limit và downstream capacity vẫn phải giới hạn. Một số native calls hoặc synchronized sections có thể ảnh hưởng khả năng unmount của virtual thread tùy JDK.

Virtual threads đáng để thử khi code dùng JDBC/JPA hoặc SDK blocking, flow tuần tự, cần transaction đồng bộ và team muốn giữ stack trace imperative. Đây là phương án benchmark, không phải khuyến nghị bật trong mọi ứng dụng.

## 6. Reactive chỉ có lợi khi phần chờ chính là non-blocking

Một pipeline có thể chứa:

```text
Function<Flux<Request>, Flux<Response>>
  ├─ WebClient (non-blocking)
  ├─ R2DBC (non-blocking database driver)
  ├─ Reactor operators
  └─ WebFlux / reactive adapter
```

Đường này có cơ hội xử lý nhiều I/O in-flight với ít thread chờ hơn. Nhưng nếu pipeline chứa:

```text
WebClient → JDBC query blocking → legacy SDK blocking
```

thì JDBC/SDK vẫn block. Chúng cần được cô lập hoặc thay bằng client/driver non-blocking; chỉ đổi chữ ký function không giải quyết vấn đề.

### Bọc blocking call bằng boundedElastic

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<Price> findPrice(String sku) {
    return Mono.fromCallable(
        () -> jdbcRepository.findPrice(sku)
    ).subscribeOn(Schedulers.boundedElastic());
}
```

Ví dụ này đặt trong service reactive; `jdbcRepository.findPrice(...)` là blocking. `boundedElastic()` chuyển việc thực thi sang scheduler dành cho blocking tasks thay vì chạy trên event loop.

Tuy nhiên:

1. `boundedElastic` có giới hạn thread/queue theo cấu hình Reactor và phiên bản; không phải tài nguyên vô hạn.
2. Cần giới hạn concurrency của upstream để không dồn quá nhiều task vào queue.
3. Database pool vẫn giới hạn số query/connection hoạt động.
4. Nếu một request có nhiều blocking calls, tổng latency vẫn bao gồm thời gian chờ của chúng.
5. Không chuyển mọi CPU work sang boundedElastic một cách tùy tiện.

Với workload quan trọng, cân nhắc scheduler riêng có giới hạn và lifecycle rõ. Không tạo scheduler mới cho từng invocation.

## 7. CPU-bound: giới hạn parallelism theo tài nguyên thật

Reactive pipeline có thể chạy CPU work trên scheduler parallel:

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

public Flux<Score> calculateScores(Flux<Input> inputs) {
    return inputs
        .publishOn(Schedulers.parallel())
        .map(this::cpuIntensiveCalculation);
}
```

Đây là ví dụ minh họa; `Input` và `Score` là kiểu domain. `Schedulers.parallel()` hướng tới CPU-bound work với parallelism giới hạn theo runtime.

Không phải pipeline nào cũng cần `publishOn(Schedulers.parallel())`. Scheduler boundary có overhead queue/scheduling và có thể làm code khó đọc. Nếu phép tính rất nhỏ, xử lý trên thread hiện tại có thể hiệu quả hơn.

Khi CPU là bottleneck:

- Profile hotspots và allocation trước khi đổi execution model.
- Tránh chạy nhiều phép tính nặng vượt khả năng CPU.
- Chọn batch size/concurrency phù hợp.
- Xem xét thuật toán và cấu trúc dữ liệu trước khi thêm threads.
- Đo throughput và tail latency khi CPU gần bão hòa.

**Reactive không tạo thêm CPU cores**; nó chỉ cung cấp mô hình phối hợp công việc bất đồng bộ.

## 8. Backpressure: kiểm soát tốc độ thay vì chỉ tăng concurrency

Reactive Streams định nghĩa cơ chế subscriber yêu cầu số phần tử có thể tiêu thụ. Backpressure giúp các thành phần trong publisher chain phối hợp tốc độ, nhưng **không tự đảm bảo end-to-end backpressure xuyên mọi adapter/broker**.

Ví dụ `flatMap` với concurrency:

```java
Flux<QuoteResult> results = requests.flatMap(
    request -> callPricing(request),
    16
);
```

Điều này giới hạn số inner publishers đồng thời trong một subscription. Nó không phải giới hạn tổng cho mọi pipeline. Nếu upstream tiếp tục phát nhanh, Reactor operators điều phối demand/buffering theo semantics của từng operator.

| Operator | Concurrency/order | Khi cân nhắc |
| --- | --- | --- |
| `map(...)` | Đồng bộ theo signal, không tạo async concurrency | Phép biến đổi nhanh |
| `concatMap(...)` | Một inner publisher tại một thời điểm, giữ thứ tự | Downstream phải tuần tự |
| `flatMap(..., concurrency)` | Nhiều inner publishers, có thể đảo thứ tự | I/O độc lập, concurrency có giới hạn |
| `flatMapSequential(..., concurrency)` | Xử lý đồng thời, phát kết quả theo thứ tự nguồn | Cần giữ thứ tự |
| `buffer(size)` | Gom phần tử thành batch | API/broker hỗ trợ batch và size có giới hạn |

Không dùng concurrency tối đa chỉ vì có thể. Nếu pricing service chỉ chịu được 50 request đồng thời, đặt `flatMap(..., 500)` ở nhiều replicas có thể gây quá tải. Phải xét số replicas, pool, rate limit, response time, queue và retry.

HTTP WebFlux có thể hỗ trợ reactive request/response body; broker binder có prefetch, batch, ack và concurrency riêng; serverless adapter có thể đưa cả event thành một object hữu hạn. Vì vậy, `Flux<T>` trong function không đảm bảo broker ngừng phát message khi downstream chậm. Kiểm tra adapter cụ thể và đặt giới hạn ở từng boundary.

## 9. Thread pool, connection pool và function concurrency là ba giới hạn khác nhau

| Giới hạn | Điều khiển | Không điều khiển |
| --- | --- | --- |
| Web server request threads | Request threads theo server model | Outbound HTTP connection count |
| Reactor event loops | Nơi xử lý I/O signals | CPU parallelism của mọi tác vụ |
| BoundedElastic scheduler | Blocking tasks được schedule | Database capacity |
| Outbound HTTP pool | Connections đến remote host | Số request được chấp nhận ở ingress |
| JDBC pool | Database connections | HTTP client concurrency |
| `flatMap concurrency` | Inner subscriptions trong pipeline | Tổng concurrency toàn cụm |
| Broker consumer concurrency/prefetch | Delivery/processing từ broker | Outbound HTTP pool |

Một instance có 16 outbound connections nhưng nhận 200 invocations đồng thời; nhiều invocation có thể chờ pool. Nếu pending queue không giới hạn, memory và latency có thể tăng.

**Thiết kế tốt cần nhiều lớp boundedness:** ingress concurrency, pipeline concurrency, connection pool, pending queue và deadline. Một giới hạn riêng lẻ không bảo vệ được toàn hệ thống.

## 10. Dùng Little's Law để ước lượng in-flight work

Little's Law:

\[
L = \lambda W
\]

Trong đó `L` là số công việc đang nằm trong hệ thống trung bình, `λ` là throughput trung bình (request/giây), và `W` là thời gian ở trong hệ thống trung bình (giây).

Ví dụ API nhận **200 request/giây**, thời gian trung bình trong đoạn gọi downstream là **0,25 giây**:

\[
L = 200 \times 0.25 = 50
\]

Khoảng 50 request đang in-flight trung bình trong đoạn đo. Đây không phải khuyến nghị cấu hình pool bằng 50; cần tính burst, tail latency, replicas và downstream capacity.

Nếu có 8 replicas và mỗi replica cho phép 20 inner requests đồng thời, mức concurrency lý thuyết của đoạn pipeline có thể đạt:

\[
8 \times 20 = 160
\]

Nếu downstream chỉ chịu được 80 request đồng thời, cần giảm concurrency per instance, dùng rate limit/bulkhead toàn hệ thống hoặc tăng capacity downstream. Reactive không tự phân phối ngân sách concurrency giữa replicas.

## 11. Transaction: imperative và reactive không dùng chung transaction model

### JDBC/JPA transaction đồng bộ

Spring transaction management truyền thống thường dùng `PlatformTransactionManager` và gắn transaction resources với thread execution context. Code JDBC/JPA đồng bộ phù hợp với function imperative chạy trong cùng transaction boundary.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BlockingOrderService {

    private final OrderRepository repository;

    public BlockingOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderReceipt createOrder(OrderRequest request) {
        return repository.saveAndCreateReceipt(request);
    }
}
```

```java
@Bean
Function<OrderRequest, OrderReceipt> createOrder(
    BlockingOrderService service
) {
    return service::createOrder;
}
```

Ví dụ giả định `OrderRepository` là repository JDBC/JPA và method được gọi qua Spring proxy. Self-invocation trong cùng object có thể bỏ qua proxy semantics; cần kiểm tra cách gọi.

### Reactive transaction

Reactive database như R2DBC thường cần `ReactiveTransactionManager` và transaction context gắn với reactive pipeline, không phải thread-local transaction đồng bộ.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository repository;
    private final TransactionalOperator tx;

    public ReactiveOrderService(
        ReactiveOrderRepository repository,
        TransactionalOperator tx
    ) {
        this.repository = repository;
        this.tx = tx;
    }

    public Mono<OrderReceipt> createOrder(OrderRequest request) {
        return repository.save(request)
            .map(this::toReceipt)
            .as(tx::transactional);
    }

    private OrderReceipt toReceipt(OrderEntity entity) {
        return new OrderReceipt(
            entity.orderId(),
            entity.lineCount(),
            entity.totalVnd()
        );
    }
}
```

Ví dụ giả định có reactive repository và `TransactionalOperator` được cấu hình bằng reactive transaction manager tương thích. Không thể thay repository đó bằng JDBC blocking mà vẫn gọi pipeline là reactive transaction.

### Không chuyển thread tùy tiện giữa transaction boundaries

- JDBC/JPA transaction đồng bộ không tự truyền an toàn qua reactive scheduler boundaries.
- Reactive transaction context cần ở cùng reactive chain và được propagation đúng.
- Không dùng `@Transactional` với manager imperative rồi giả định nó bao trọn một `Flux` async sau khi method đã trả.
- Nếu tích hợp cả reactive và blocking stores, xác định transaction boundaries riêng; không giả định một local transaction tự bao cả hai hệ thống.

Nếu nghiệp vụ cần transaction đồng bộ và database dùng JDBC, **imperative function có thể là lựa chọn ít rủi ro hơn** so với chuyển reactive chỉ để có nhiều request đồng thời.

## 12. Context propagation: security, tracing và correlation

Trong imperative code, nhiều framework dựa vào ThreadLocal để giữ security context, logging MDC hoặc transaction context. Trong reactive code, công việc có thể đổi thread giữa operators; ThreadLocal không tự đi theo mọi signal.

Reactor cung cấp `Context` cho metadata theo subscription; Spring Security, Micrometer Observation và tracing có cơ chế tích hợp tương ứng khi được cấu hình. Không tự copy context bằng cách đọc ThreadLocal ở một thread rồi giả định thread tiếp theo có cùng giá trị.

| Context | Yêu cầu |
| --- | --- |
| Correlation/trace ID | Giữ xuyên async boundaries theo tracing propagation |
| Security principal | Không làm mất hoặc lẫn principal giữa requests |
| Tenant ID | Gắn đúng invocation, không lưu vào singleton mutable |
| Locale | Rõ scope và propagation |
| Transaction context | Dùng transaction manager phù hợp execution model |
| Request-scoped data | Không giữ trong field singleton |

Khi chuyển function imperative sang reactive, cần test security/tracing/tenant isolation chứ không chỉ test output DTO.

## 13. Error handling: exception và reactive error signal

### Imperative

Exception trong `Function.apply(...)` có thể được adapter xử lý theo error mapping của nó. Lỗi có thể là validation, downstream timeout hoặc bug; không nên biến tất cả thành một kết quả mặc định.

```java
@Bean
Function<QuoteRequest, QuoteResult> quote(RestClient client) {
    return request -> {
        try {
            return callPricing(client, request);
        } catch (org.springframework.web.client.ResourceAccessException ex) {
            throw new PricingUnavailableException(
                "Pricing service is unavailable", ex
            );
        }
    };
}
```

Snippet giả định có method `callPricing(...)` và exception class của ứng dụng. Adapter quyết định cách ánh xạ exception ra HTTP status hoặc event error channel.

### Reactive

Trong Reactor, lỗi được phát như terminal signal:

```java
return client.post()
    .uri("/v1/quotes")
    .bodyValue(request)
    .retrieve()
    .bodyToMono(QuoteResult.class)
    .onErrorMap(
        WebClientResponseException.class,
        ex -> new PricingUnavailableException(
            "Pricing service returned an error", ex
        )
    );
```

Đây là phần pipeline reactive, cần exception class và imports tương ứng. `onErrorMap` đổi loại lỗi; nó không biến lỗi thành success.

Với `requests.flatMap(this::callPricing, 16)`, nếu một inner publisher phát error và không có policy xử lý, toàn bộ downstream Flux có thể kết thúc bằng lỗi, hủy inner work còn lại theo semantics của operator.

Nếu contract cho phép kết quả lỗi theo từng item, định nghĩa kiểu kết quả rõ ràng:

```java
public sealed interface QuoteOutcome
    permits QuoteSuccess, QuoteFailure {}

public record QuoteSuccess(QuoteResult value)
    implements QuoteOutcome {}

public record QuoteFailure(String code, String message)
    implements QuoteOutcome {}
```

```java
Flux<QuoteOutcome> outcomes = requests.flatMap(
    request -> callPricing(request)
        .<QuoteOutcome>map(QuoteSuccess::new)
        .onErrorResume(ex -> Mono.just(
            new QuoteFailure("PRICING_FAILED", "Unable to quote")
        )),
    16
);
```

Đây là **partial-result contract**; chỉ dùng nếu caller chấp nhận từng phần tử có thể thất bại độc lập. Không nuốt lỗi tùy tiện rồi trả object rỗng vì sẽ che sự cố và làm sai dữ liệu.

## 14. Retry và cancellation

Reactive publisher hỗ trợ cancellation khi subscriber hủy hoặc client disconnect; nhưng việc hủy **không bảo đảm** mọi I/O bên ngoài đã dừng ngay. Với JDBC/SDK blocking, thread có thể tiếp tục chạy hoặc resource vẫn giữ đến khi operation kết thúc.

| Loại thao tác | Hướng xử lý |
| --- | --- |
| GET idempotent gặp lỗi mạng tạm thời | Retry giới hạn, backoff và jitter nếu contract cho phép |
| POST tạo đơn/thanh toán | Dùng idempotency key; không retry mù quáng |
| HTTP 400 do input | Không retry cùng payload |
| HTTP 429/503 | Tuân thủ throttling/Retry-After và retry budget |
| Pool acquire timeout | Điều tra saturation/concurrency trước khi retry |
| Broker redelivery | Tính cả retry của binder và retry trong function |

Một pipeline reactive có thể dùng retry operators, nhưng số lần thử, backoff và tổng deadline cần cấu hình rõ. Không đặt retry không giới hạn.

- Không gọi `subscribe()` thủ công trong function chỉ để “chạy ngay”; hãy trả publisher để framework/adapter quản lý subscription.
- Không tạo background task không được theo dõi rồi trả success trước khi task hoàn thành nếu contract yêu cầu xử lý xong.
- Khi request bị hủy, cleanup tài nguyên và dừng work có thể dừng.
- Với event broker, xác định semantics ack/nack khi subscription bị cancel.

## 15. Supplier và Consumer trong hai mô hình

| Imperative | Reactive | Ý nghĩa |
| --- | --- | --- |
| `Supplier<T>` | `Supplier<Flux<T>>` | Cung cấp một giá trị hoặc stream |
| `Function<I,O>` | `Function<Flux<I>,Flux<O>>` | Biến đổi một request hoặc stream |
| `Consumer<T>` | `Consumer<Flux<T>>` | Xử lý một event hoặc stream |

Ví dụ supplier reactive:

```java
@Bean
public Supplier<Flux<QuoteResult>> quoteFeed(WebClient client) {
    return () -> client.get()
        .uri("/v1/quote-feed")
        .retrieve()
        .bodyToFlux(QuoteResult.class);
}
```

Ví dụ giả định endpoint trả stream tương thích với decoder; cách trigger supplier phụ thuộc adapter. Không giả định mọi adapter tự subscribe theo cùng semantics.

Ví dụ consumer reactive:

```java
@Bean
public Consumer<Flux<AuditEvent>> auditEvents(
    AuditService auditService
) {
    return events -> events.concatMap(auditService::store);
}
```

Ở đây `AuditService.store(...)` phải trả publisher reactive, ví dụ `Mono<Void>`. `concatMap` xử lý tuần tự để giữ thứ tự. Nếu store là JDBC blocking, không gọi trực tiếp trên event loop.

## 16. WebFlux và MVC là lựa chọn adapter riêng

Đừng nhầm:

- **Imperative/reactive function signature:** cách function xử lý input/output.
- **Web MVC/WebFlux adapter/runtime:** cách HTTP server nhận và trả request.
- **Outbound RestClient/WebClient:** cách function gọi dịch vụ bên ngoài.

Ứng dụng WebFlux vẫn có thể gọi thư viện blocking; blocking I/O không tự biến thành non-blocking. Function imperative cũng có thể được dùng trong ứng dụng có thành phần reactive, nhưng cần hiểu nó chạy ở thread nào và có block event loop hay không.

Khi expose Spring Cloud Function qua HTTP, kiểm tra adapter/phiên bản hỗ trợ function signature và codec tương ứng. Khi chạy qua Spring Cloud Stream, kiểm tra binder concurrency, poller/prefetch, batch, ack và retry. Với serverless, xem handler/event model và giới hạn thời gian nền tảng.

## 17. Chọn mô hình theo loại tải

| Điều kiện thực tế | Hướng nên thử | Điều cần kiểm chứng |
| --- | --- | --- |
| CPU-bound, ít I/O | Imperative hoặc CPU scheduler có giới hạn | CPU saturation, throughput, allocation |
| JDBC/JPA, transaction đồng bộ | Imperative; virtual threads nếu phù hợp | Pool connections, blocking concurrency, transaction |
| HTTP outbound non-blocking, nhiều request chờ | Reactive WebClient | Event loop, pool, pending queue, p99 |
| Nhiều stream dài hoặc dữ liệu theo thời gian | Reactive Flux | Backpressure ở từng boundary, cancellation, memory |
| Ít request, logic đơn giản | Imperative | Latency và chi phí vận hành |
| SDK chỉ có API blocking | Imperative hoặc isolate blocking | Scheduler/thread limit, timeout, cancellation |
| Nhiều API non-blocking cần phối hợp | Reactive | Error/cancellation/context propagation |
| Batch kích thước cố định | Cả hai | Batch size, concurrency, memory và partial failure |
| Team chưa có kinh nghiệm Reactor | Imperative trước nếu đáp ứng SLO | Chi phí học/debug và khả năng bảo trì |

**Chọn mô hình đơn giản nhất đáp ứng SLO và giới hạn tài nguyên.** Nếu imperative đạt throughput, p95/p99 và memory budget với cấu hình thread/virtual thread phù hợp, không cần chuyển reactive chỉ vì ứng dụng có nhiều request.

Nếu workload thực sự I/O-bound, concurrency cao, stream dài và thư viện downstream đều non-blocking, reactive đáng để benchmark vì có thể giảm thread waiting và quản lý backpressure tốt hơn.

## 18. Đo hiệu năng công bằng

Một benchmark tốt phải so sánh cùng công việc:

1. Cùng logic và validation.
2. Cùng request/response schema, payload size và downstream.
3. Cùng JDK, Spring Boot, Spring Cloud Function, CPU/memory và adapter.
4. Cùng concurrency, arrival rate, thời gian warm-up và duration.
5. Cùng connection pool limits, timeout và retry policy.
6. Đo cả error rate, timeout và cancellation.

| Metric | Ý nghĩa |
| --- | --- |
| Throughput (req/s) | Số request hoàn thành mỗi giây |
| p50/p95/p99 latency | Phân phối độ trễ, đặc biệt tail |
| Error/timeout rate | Lỗi dưới tải, không chỉ request thành công |
| Active threads | Thread pool có bão hòa? |
| Event-loop utilization | Reactive I/O loop có bị block? |
| Connection pool active/idle/pending | Outbound I/O có bị nghẽn? |
| CPU utilization | Workload CPU-bound hay thread chờ? |
| Heap/allocation/GC | Chi phí object và pause |
| Queue depth/consumer lag | Upstream đang dồn tải? |
| Cancellation/retry count | Có work bị bỏ dở hoặc khuếch đại? |

Một lần `curl` giúp xác minh endpoint và contract, nhưng không cho biết behavior ở concurrency cao. Dùng load test có arrival rate/concurrency kiểm soát, đủ warm-up và chạy nhiều lượt. Không so một lần imperative trên máy nhàn với một lần reactive khi CPU đang bận.

### Micrometer đo function đồng bộ

```java
import java.util.function.Function;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

@Bean("quoteTimed")
public Function<QuoteRequest, QuoteResult> quoteTimed(
    @org.springframework.beans.factory.annotation.Qualifier("quoteBlocking")
    Function<QuoteRequest, QuoteResult> delegate,
    MeterRegistry registry
) {
    Timer timer = Timer.builder("app.quote.duration")
        .tag("mode", "imperative")
        .register(registry);

    return request -> timer.record(
        () -> delegate.apply(request)
    );
}
```

Timer đo thời gian synchronous delegate hoàn tất, gồm I/O blocking bên trong. Ví dụ giả định có bean `MeterRegistry` và bean `quoteBlocking`; qualifier giúp tránh ambiguity nếu context có nhiều function cùng kiểu.

### Micrometer đo reactive completion

```java
import java.util.function.Function;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import reactor.core.publisher.Flux;

@Bean("quoteReactiveTimed")
public Function<Flux<QuoteRequest>, Flux<QuoteResult>>
        quoteReactiveTimed(
            @org.springframework.beans.factory.annotation.Qualifier("quoteReactive")
            Function<Flux<QuoteRequest>, Flux<QuoteResult>> delegate,
            MeterRegistry registry
        ) {
    Timer timer = Timer.builder("app.quote.stream.duration")
        .tag("mode", "reactive")
        .register(registry);

    return input -> Flux.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        return Flux.defer(() -> delegate.apply(input))
            .doFinally(signal -> sample.stop(timer));
    });
}
```

Đây là timer cho **toàn bộ subscription của stream**, kết thúc khi complete/error/cancel. Nếu stream sống lâu, metric duration không hữu ích cho từng request; đo per-item latency hoặc thời gian đến item đầu. Trong ứng dụng thực, bảo đảm chỉ có một instrumentation layer cho cùng metric để tránh double counting.

### Microbenchmark và load test trả lời hai câu hỏi khác nhau

- **JMH:** đo chi phí code cục bộ, operator hoặc thuật toán trong điều kiện kiểm soát.
- **Load test:** đo API/broker end-to-end, network, queue, concurrency, backpressure và errors.

Không dùng kết quả JMH microseconds để kết luận HTTP p99 production.

## 19. Ví dụ ma trận kết quả giả định

Giả sử cùng API gọi pricing service với workload I/O-bound. Các số liệu sau **chỉ để minh họa**, không phải benchmark Spring Cloud Function:

| Metric | Imperative thread pool | Imperative virtual threads | Reactive WebClient |
| --- | ---: | ---: | ---: |
| Throughput | 700 req/s | 900 req/s | 1.050 req/s |
| Warm p95 | 180 ms | 145 ms | 125 ms |
| Warm p99 | 420 ms | 330 ms | 290 ms |
| CPU | 42% | 44% | 38% |
| Peak threads | 220 | 55 platform + virtual tasks | 24 event-loop/scheduler threads |
| Error rate | 0,1% | 0,1% | 0,1% |

Không thể suy ra reactive luôn tốt hơn từ bảng này. Kết quả thay đổi khi downstream giới hạn concurrency, workload CPU-bound, code reactive có blocking call, scheduler/event loop cấu hình sai, hoặc network chi phối gần như toàn bộ latency.

Một lựa chọn chỉ thành công khi **đáp ứng performance budget, error budget, maintainability và operational requirements**.

## 20. Các lỗi migration phổ biến

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Reactive throughput thấp | JDBC/SDK blocking trên event loop | Dùng non-blocking driver hoặc isolate blocking work |
| `Mono` không chạy | Chưa có subscriber | Trả publisher cho adapter quản lý; test phải subscribe |
| Gọi `subscribe()` trong function rồi trả ngay | Tách work khỏi lifecycle/request | Trả publisher và để framework quản lý |
| Event loop bị block | `block()`, JDBC, file I/O | Không blocking trên event loop |
| Memory tăng dưới tải | Queue/pending/unbounded buffer | Bounded concurrency và queue |
| Kết quả Flux đảo thứ tự | `flatMap` hoàn thành không theo input | `concatMap` hoặc `flatMapSequential` |
| Một lỗi làm hỏng cả batch | Error terminal của Flux | Định nghĩa partial-result hoặc batch-failure contract |
| Transaction không bao hết thao tác | Dùng imperative manager trong reactive chain | Chọn transaction manager phù hợp |
| Security/MDC bị mất | Dựa vào ThreadLocal qua async boundary | Context propagation phù hợp |
| Retry tạo dữ liệu trùng | POST không idempotent | Idempotency key và retry budget |
| p50 đẹp nhưng p99 xấu | Queueing, pool saturation, burst | Theo dõi tail latency và pending |
| Virtual threads vẫn chậm | DB pool/downstream là bottleneck | Giới hạn concurrency và đo I/O |
| Reactive code phức tạp mà không có lợi | Workload thấp hoặc CPU-bound | Dùng imperative nếu đạt SLO |

## 21. Lộ trình chọn và chuyển đổi

1. **Phân loại tải:** CPU-bound, blocking I/O, non-blocking I/O, stream hay batch.
2. **Ghi baseline:** throughput, p50/p95/p99, errors, threads, pool, CPU, heap và GC.
3. **Xác định bottleneck:** function logic, JSON conversion, database, HTTP, broker hay queue.
4. **Chọn biến thể imperative phù hợp:** thread pool hiện tại hoặc virtual threads khi runtime hỗ trợ.
5. **Chỉ thử reactive khi có lý do:** nhiều I/O non-blocking, streaming hoặc concurrency cao.
6. **Kiểm kê mọi blocking call** trong pipeline; không chỉ nhìn chữ ký `Flux`.
7. **Giới hạn concurrency/backpressure/pool** và đặt deadline cho downstream.
8. **Test transaction, security context, cancellation, retry và error mapping.**
9. **Load test cùng adapter và payload**, không so core function với end-to-end endpoint.
10. **Chọn mô hình đáp ứng SLO với độ phức tạp thấp nhất**, giữ lại kết quả và cấu hình để có thể rollback.

### Checklist trước khi quyết định

- [ ] Đã biết phần lớn thời gian là CPU hay I/O.
- [ ] Đã biết thư viện downstream blocking hay non-blocking.
- [ ] Đã đo p95/p99 và error rate dưới tải.
- [ ] Đã tính số replicas, pool size và tổng concurrency.
- [ ] Đã giới hạn queue và pending work.
- [ ] Đã kiểm tra transaction manager và context propagation.
- [ ] Đã kiểm tra cancellation, retry và idempotency.
- [ ] Đã xác minh adapter hỗ trợ function signature.
- [ ] Đã đo cold/first/warm nếu triển khai serverless.
- [ ] Đã so sánh chi phí vận hành và độ phức tạp của team.

## 22. Bài tập thực hành

**Bài 1 — CPU hay I/O?** Một function đọc 3 bảng JDBC, tính tổng và trả JSON. Có nên đổi sang reactive chỉ vì có nhiều request đồng thời?

*Đáp án:* Chưa. JDBC là blocking. Trước tiên đo thời gian DB, transaction, pool và concurrency; có thể dùng imperative với pool/virtual threads phù hợp. Reactive chỉ có lợi nếu thay bằng driver reactive và pipeline non-blocking hoặc cô lập blocking đúng cách.

**Bài 2 — Mono.fromCallable.** Vì sao `Mono.fromCallable(() -> jdbc.find(id))` chưa đủ để không block event loop?

*Đáp án:* Nó trì hoãn callable nhưng chạy trên scheduler subscription hiện tại nếu không chỉ định; cần cô lập blocking work bằng scheduler phù hợp hoặc thay driver.

**Bài 3 — FunctionCatalog.** Đổi `spring.cloud.function.definition=quoteBlocking` thành `quoteReactive` có tự chuyển execution sang non-blocking không?

*Đáp án:* Không. Phải đăng ký function reactive với publisher, dùng non-blocking clients và adapter tương thích.

**Bài 4 — Backpressure.** `flatMap(callRemote, 16)` có nghĩa toàn bộ ứng dụng chỉ có 16 request outbound không?

*Đáp án:* Không. Nó giới hạn inner publishers trong một subscription/pipeline; các invocations và replicas khác vẫn có thể gọi đồng thời.

**Bài 5 — Giữ thứ tự.** 20 requests cần gọi API đồng thời nhưng output phải giữ thứ tự input. Operator nào có thể cân nhắc?

*Đáp án:* `flatMapSequential(..., concurrency)` cho phép xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn; `concatMap` giữ thứ tự với xử lý tuần tự.

**Bài 6 — Virtual threads.** Bật virtual threads có làm database chấp nhận số connection không giới hạn?

*Đáp án:* Không. JDBC pool và capacity database vẫn là giới hạn; virtual threads chỉ thay đổi chi phí giữ thread trong lúc chờ.

**Bài 7 — Transaction.** Một reactive function gọi JDBC repository trong `flatMap` rồi dùng `@Transactional` imperative. Có thể mặc định transaction bao trọn publisher không?

*Đáp án:* Không. Transaction manager đồng bộ thường gắn resources với thread; reactive chain cần transaction manager/context reactive phù hợp.

**Bài 8 — Error của Flux.** Một trong 100 phần tử bị pricing API lỗi. Có phải 99 kết quả còn lại luôn được phát ra không?

*Đáp án:* Không. Error từ một inner publisher có thể kết thúc cả Flux tùy operator/policy. Muốn partial results phải định nghĩa error-as-value hoặc isolation theo từng item.

**Bài 9 — Retry POST.** API tạo thanh toán timeout. Có nên dùng retry ba lần trong reactive pipeline?

*Đáp án:* Chỉ khi contract idempotency bảo đảm, ví dụ idempotency key và retry budget; nếu không có thể tạo thanh toán trùng.

**Bài 10 — Little's Law.** Throughput 200 req/s, thời gian trung bình trong đoạn gọi downstream 0,25 s. In-flight trung bình ước lượng bao nhiêu?

*Đáp án:* `L = 200 × 0,25 = 50` requests. Đây là trung bình của đoạn đo, không phải cấu hình pool chính xác.

**Bài 11 — Event loop.** Reactive function gọi `WebClient` rồi dùng `block()` để lấy response trước khi trả. Điều gì có thể xảy ra?

*Đáp án:* Event loop bị giữ chờ, gây nghẽn các request khác và có thể giảm throughput. Giữ publisher reactive và trả về cho framework.

**Bài 12 — Quyết định.** Một API imperative dùng JDBC và virtual threads đã đạt p99 SLO, code đơn giản, không cần streaming. Có cần chuyển reactive?

*Đáp án:* Không có lý do bắt buộc. Giữ mô hình hiện tại nếu đáp ứng SLO, tài nguyên và vận hành; chỉ chuyển khi workload/bottleneck có bằng chứng phù hợp.

## 23. Ghi nhớ

- **Đồng bộ trả kết quả trực tiếp; reactive trả publisher và xử lý khi subscribe.**
- **Reactive không tự làm công việc nhanh hơn**; lợi ích chính đến từ I/O non-blocking, concurrency và streaming có kiểm soát.
- **CPU-bound không được tăng tốc chỉ nhờ Mono/Flux**; cần tối ưu thuật toán và giới hạn CPU parallelism.
- **JDBC/JPA và SDK blocking vẫn block** khi được bọc trong reactive pipeline; cô lập bằng scheduler phù hợp hoặc chọn driver non-blocking.
- **Virtual threads là lựa chọn đáng thử cho blocking workloads** trên JDK 21+ và Spring Boot tương thích, nhưng không bỏ giới hạn connection pool/downstream.
- **Backpressure trong publisher chain không bảo đảm xuyên mọi adapter/broker**; phải giới hạn concurrency, queue và prefetch ở từng boundary.
- **Transaction, security context, tracing, cancellation và error semantics khác nhau** giữa imperative và reactive; phải kiểm thử khi migration.
- **Đo cùng một đường end-to-end**: throughput, p50/p95/p99, error rate, thread/pool, CPU, heap và queue.
- **Chọn mô hình đơn giản nhất đáp ứng SLO** và đặc điểm tải; không chuyển reactive chỉ vì xu hướng.

**Tài liệu tham khảo:**

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

Các ví dụ giúp thiết kế và so sánh hai execution models. Khi triển khai, cần xác nhận đúng phiên bản Spring Cloud Function, Boot, Reactor, adapter và database driver; đo trên workload đại diện, đồng thời giữ nguyên contract nghiệp vụ và các giới hạn tài nguyên.
