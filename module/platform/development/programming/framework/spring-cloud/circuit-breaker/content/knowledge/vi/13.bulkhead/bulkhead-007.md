# Bulkhead trong reactive: khả năng hỗ trợ theo phiên bản

## Vì sao reactive vẫn cần Bulkhead?

Trong ứng dụng Spring WebFlux, một request thường được xử lý bằng pipeline `Mono` hoặc `Flux`. Mô hình non-blocking giúp thread không phải đứng chờ I/O, nhưng không tự giới hạn số request đang hoạt động. Khi một dịch vụ phụ thuộc chậm, nhiều subscription có thể cùng tồn tại, giữ bộ nhớ, connection, buffer và các tài nguyên khác. Nếu không có giới hạn đồng thời, một dependency suy giảm vẫn có thể làm cạn tài nguyên của ứng dụng gọi.

Bulkhead giới hạn lượng công việc được phép đi qua một vùng bảo vệ. Với reactive, điều quan trọng là giới hạn subscription hoặc công việc đồng thời mà không chặn event-loop. Resilience4j cung cấp `SemaphoreBulkhead` phù hợp để kiểm soát số lời gọi đang hoạt động; `ThreadPoolBulkhead` dành cho trường hợp cần thực thi supplier trên thread pool riêng, thường hữu ích với tác vụ blocking hoặc API đồng bộ cũ.

Bulkhead và Circuit Breaker giải quyết hai vấn đề khác nhau:

| Cơ chế | Câu hỏi được trả lời | Tác dụng |
| --- | --- | --- |
| Bulkhead | Có bao nhiêu lời gọi được phép hoạt động cùng lúc? | Giới hạn đồng thời và cô lập tài nguyên. |
| Circuit Breaker | Dependency có đang thất bại hoặc chậm vượt ngưỡng không? | Ngăn lời gọi mới khi có đủ bằng chứng dependency suy giảm. |
| Timeout / TimeLimiter | Ứng dụng chờ một lời gọi tối đa bao lâu? | Giới hạn thời gian chờ. |

Kết hợp ba cơ chế giúp giới hạn số subscription, phát hiện dependency lỗi và kết thúc việc chờ trong thời hạn phù hợp. Bulkhead không thay thế timeout; một lời gọi chiếm permit quá lâu vẫn có thể giữ hết năng lực đồng thời.

## Phân biệt hai loại Bulkhead của Resilience4j

Resilience4j có hai kiểu Bulkhead chính:

| Kiểu | Cách giới hạn | Đặc điểm khi dùng reactive |
| --- | --- | --- |
| `SemaphoreBulkhead` | Cấp permit cho tối đa `maxConcurrentCalls` lời gọi đồng thời. | Có thể áp dụng trực tiếp lên `Mono` hoặc `Flux` bằng `BulkheadOperator`, không cần chuyển sang thread khác. |
| `ThreadPoolBulkhead` | Chạy supplier trên pool riêng, với giới hạn thread và hàng đợi. | Trả về `CompletionStage`; phù hợp để cô lập tác vụ blocking hoặc supplier đồng bộ. Không nên dùng chỉ để chuyển một pipeline WebClient non-blocking sang pool khác. |

Với WebFlux và `WebClient`, thường nên bắt đầu bằng `SemaphoreBulkhead`. Nó giới hạn số subscription đi vào pipeline, trong khi I/O vẫn chạy theo mô hình reactive. Chọn `ThreadPoolBulkhead` khi cần cách ly một thư viện blocking, ví dụ JDBC cũ hoặc HTTP client đồng bộ, để công việc blocking không chạy trên event-loop.

## Khả năng hỗ trợ phụ thuộc vào stack và phiên bản

Có ba lớp cần phân biệt khi đánh giá hỗ trợ reactive:

1. **Spring Cloud Circuit Breaker abstraction:** cung cấp `ReactiveCircuitBreakerFactory` và `ReactiveCircuitBreaker` để tạo và thực thi circuit breaker trên `Mono` hoặc `Flux`.
2. **Resilience4j Reactor integration:** cung cấp các operator reactive như `CircuitBreakerOperator` và `BulkheadOperator` để kết hợp trực tiếp với Reactor publisher.
3. **Auto-configuration của starter:** quyết định factory nào được tạo, cấu hình nào được áp dụng mặc định và Bulkhead có được gắn tự động vào lời gọi hay không.

Không nên suy ra rằng có `ReactiveCircuitBreakerFactory` là chắc chắn đã có Bulkhead trong pipeline. Hợp đồng abstraction và hành vi auto-configuration có thể khác nhau theo release train Spring Cloud, phiên bản Spring Boot, starter imperative/reactive và cấu hình Resilience4j. Một số tổ hợp có thể cung cấp tích hợp Bulkhead ở factory; tổ hợp khác yêu cầu ứng dụng áp dụng operator trực tiếp.

Trước khi triển khai, hãy kiểm tra đúng phiên bản đang dùng:

- Xác nhận ứng dụng dùng WebFlux/Reactor và starter reactive phù hợp.
- Kiểm tra runtime dependency graph có module Resilience4j Reactor (`resilience4j-reactor`) và Bulkhead cần thiết.
- Đọc tài liệu Spring Cloud Circuit Breaker của đúng release train để biết reactive factory có áp dụng Bulkhead tự động hay không và lựa chọn loại Bulkhead mặc định.
- Kiểm tra cấu hình property của đúng phiên bản thay vì sao chép property từ một release train khác.
- Xác nhận runtime behavior bằng metrics: số lời gọi đồng thời, số lần bị từ chối và trạng thái Circuit Breaker.

Nếu starter đã tự áp dụng Bulkhead, không thêm một `BulkheadOperator` thứ hai một cách vô tình. Hai lớp giới hạn cùng lúc có thể tạo ra hai ngưỡng khác nhau, làm giảm năng lực thực tế và khiến việc giải thích lỗi từ chối khó hơn. Nếu abstraction không cung cấp cách cấu hình Bulkhead reactive theo yêu cầu, có thể tạo `SemaphoreBulkhead` và áp dụng thủ công trong pipeline như ví dụ tiếp theo.

## Áp dụng SemaphoreBulkhead lên Mono

Ví dụ tạo một Bulkhead giới hạn tối đa 24 subscription đồng thời cho dependency `catalog`:

```java
import java.time.Duration;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogBulkheadConfiguration {

    @Bean
    Bulkhead catalogBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(24)
            .maxWaitDuration(Duration.ZERO)
            .build();

        return Bulkhead.of("catalog", config);
    }
}
```

`maxConcurrentCalls` đặt giới hạn số lời gọi được cấp permit. `maxWaitDuration(Duration.ZERO)` yêu cầu từ chối ngay khi không còn permit, thay vì giữ thread để chờ. Với reactive pipeline, không nên dùng thời gian chờ dài theo cách chặn event-loop. Giá trị 24 chỉ là ví dụ; cần chọn theo connection pool, năng lực dependency, giới hạn bộ nhớ và mục tiêu latency.

Áp dụng operator cho một `Mono`:

```java
Mono<CatalogItem> item = webClient.get()
    .uri("/catalog/{id}", productId)
    .retrieve()
    .bodyToMono(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

`transformDeferred` tạo phép trang trí theo từng lần subscribe. Permit được dùng khi subscription đi qua Bulkhead và được giải phóng khi publisher kết thúc hoặc subscription bị hủy theo vòng đời operator. Khi hết permit, publisher phát lỗi từ chối Bulkhead, thường là `BulkheadFullException`. Caller cần quyết định cách ánh xạ lỗi quá tải này thành response phù hợp.

Với `Flux`, cách áp dụng tương tự:

```java
Flux<CatalogItem> items = webClient.get()
    .uri("/catalog")
    .retrieve()
    .bodyToFlux(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

Bulkhead giới hạn subscription đến pipeline, không phải số phần tử được phát ra bởi một `Flux`. Một subscription có thể phát nhiều phần tử nhưng vẫn chiếm một permit cho đến khi kết thúc hoặc bị hủy. Nếu cần giới hạn số phần tử xử lý đồng thời bên trong một luồng, hãy xem xét `flatMap` với `concurrency` phù hợp; đó là một giới hạn khác với Bulkhead dành cho dependency.

## Kết hợp với ReactiveCircuitBreakerFactory

Nếu Spring Cloud Circuit Breaker cung cấp `ReactiveCircuitBreakerFactory`, ứng dụng có thể dùng abstraction đó cho circuit breaker và đặt Bulkhead operator bên ngoài publisher được bảo vệ:

```java
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<CatalogView> find(String productId) {
    Mono<CatalogView> primary = webClient.get()
        .uri("/catalog/{id}", productId)
        .retrieve()
        .bodyToMono(CatalogItem.class)
        .map(CatalogView::available);

    Mono<CatalogView> protectedByCircuitBreaker =
        reactiveCircuitBreakerFactory.create("catalog").run(
            primary,
            error -> Mono.just(CatalogView.unavailable(productId))
        );

    return protectedByCircuitBreaker
        .transformDeferred(BulkheadOperator.of(catalogBulkhead))
        .onErrorResume(BulkheadFullException.class,
            error -> Mono.just(CatalogView.overloaded()));
}
```

Trong ví dụ, Bulkhead nằm ngoài publisher đã được Circuit Breaker bọc. Khi hết permit, Bulkhead từ chối subscription trước khi pipeline Circuit Breaker bắt đầu; lỗi từ chối được xử lý riêng bằng `onErrorResume`. Nhờ đó, tình trạng ứng dụng gọi đã hết năng lực đồng thời không bị tính nhầm thành lỗi của dependency. `CatalogView.overloaded()` biểu thị ứng dụng hiện quá tải; nó khác với `CatalogView.unavailable()` dùng khi lời gọi chính gặp lỗi.

Đây là cách kết hợp thủ công khi factory không tự gắn Bulkhead phù hợp. Nếu phiên bản starter đã tích hợp Bulkhead, hãy chọn một nơi quản lý chính sách và tránh áp dụng trùng. Nếu muốn Circuit Breaker ghi nhận cả lỗi từ chối Bulkhead, cần chủ động cấu hình predicate và hiểu rằng failure rate lúc đó phản ánh cả quá tải ở ứng dụng gọi, không chỉ sức khỏe dependency.

## Vì sao không nên block để chờ permit?

Reactor chạy callback trên các scheduler và event-loop. Nếu một thread event-loop bị chặn để chờ semaphore hoặc chờ một tác vụ đồng bộ, thread đó không thể xử lý các subscription khác. Điều này làm mất lợi ích của mô hình non-blocking và có thể tạo ra tắc nghẽn trên chính ứng dụng gọi.

Với `SemaphoreBulkhead`, cấu hình chờ nên ngắn và thường là từ chối ngay. Không gọi `block()` để đợi publisher có permit; hãy để lỗi từ chối đi theo pipeline reactive và ánh xạ nó thành phản hồi quá tải. Nếu nghiệp vụ cần xếp hàng, dùng một hàng đợi có giới hạn và cơ chế backpressure được thiết kế riêng thay vì giữ event-loop chờ permit.

## Khi nào dùng ThreadPoolBulkhead?

`ThreadPoolBulkhead` hữu ích khi phải gọi một API blocking mà chưa thể chuyển sang reactive. Nó thực thi supplier trên thread pool riêng và trả về `CompletionStage`; có thể chuyển kết quả thành `Mono`:

```java
import java.util.concurrent.CompletionStage;

import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import reactor.core.publisher.Mono;

public Mono<CatalogItem> findLegacy(String productId) {
    CompletionStage<CatalogItem> stage = threadPoolBulkhead.executeSupplier(
        () -> blockingCatalogClient.find(productId)
    );

    return Mono.fromCompletionStage(stage);
}
```

`blockingCatalogClient.find` chạy trên pool do ThreadPoolBulkhead quản lý, không chạy trực tiếp trên event-loop. Hãy giới hạn `coreThreadPoolSize`, `maxThreadPoolSize` và `queueCapacity`; hàng đợi cần hữu hạn để áp lực không tích tụ vô hạn. Khi pool và hàng đợi đầy, lời gọi bị từ chối và ứng dụng cần xử lý lỗi quá tải.

Không dùng `ThreadPoolBulkhead` để bọc một lời gọi `WebClient` vốn đã non-blocking chỉ nhằm “thêm bất đồng bộ”. Việc chuyển sang pool khác có thể tạo thêm thread, queue và context propagation cần quản lý mà không cải thiện I/O. Với một API reactive, `SemaphoreBulkhead` thường là lựa chọn đơn giản hơn.

Việc hủy subscription reactive không nhất thiết dừng được tác vụ blocking đã bắt đầu trên thread pool. Do đó, vẫn phải cấu hình timeout cho HTTP client blocking, giới hạn thời gian chờ và xử lý kết quả đến muộn. Không dựa vào việc caller hủy `Mono` để bảo đảm thao tác ở hệ thống đích đã dừng.

## Cấu hình qua Spring Cloud và Resilience4j

Resilience4j cho phép cấu hình instance Bulkhead theo tên. Ví dụ cấu hình semaphore bulkhead trong `application.yml`:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0ms
```

Với ThreadPoolBulkhead, cấu hình nằm trong nhóm `thread-pool-bulkhead`:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacyCatalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
```

Các thuộc tính và cách starter gắn instance vào factory có thể thay đổi theo phiên bản. Cần đối chiếu schema cấu hình và tài liệu của đúng release train. Nếu tự lấy `Bulkhead` từ registry và áp dụng `BulkheadOperator`, hãy bảo đảm tên instance và chính sách của registry trùng với ý định vận hành; không đồng thời để factory tạo một Bulkhead khác cho cùng lời gọi mà không chủ đích.

## Chọn giới hạn đồng thời

Không nên đặt `maxConcurrentCalls` chỉ dựa trên số thread của máy. Với WebClient, mỗi request có thể không chiếm một thread riêng nhưng vẫn sử dụng connection, buffer, bộ nhớ và năng lực xử lý phía server. Hãy dựa vào:

- Giới hạn connection của HTTP client và số request có thể chạy đồng thời trên mỗi connection.
- Năng lực xử lý thực tế và giới hạn concurrency mà dependency công bố.
- Thời gian phản hồi mục tiêu và mức tăng latency khi tải tăng.
- Kích thước response, lượng dữ liệu giữ trong bộ nhớ và số subscription đồng thời.
- Số instance ứng dụng. Nếu mỗi instance có Bulkhead riêng, tổng tải có thể bằng giới hạn mỗi instance nhân với số instance.

Ví dụ, nếu mỗi instance cho phép 24 lời gọi và hệ thống chạy 5 instance, dependency có thể nhận đến khoảng 120 lời gọi đồng thời từ dịch vụ này, chưa kể các caller khác. Cần tính giới hạn toàn hệ thống và phân bổ ngân sách concurrency theo từng dependency.

## Quan sát và xử lý lỗi từ chối

Nên theo dõi các chỉ số của Bulkhead cùng Circuit Breaker:

- Số lời gọi đang sử dụng permit và số permit còn trống.
- Số lời gọi bị từ chối do không còn permit.
- Thời gian giữ permit và latency của publisher.
- Số subscription bị hủy trước khi hoàn tất.
- Số lỗi Circuit Breaker, số lời gọi bị từ chối khi mạch `OPEN` và failure rate của dependency.

`BulkheadFullException` và `CallNotPermittedException` mang ý nghĩa khác nhau. Lỗi đầu cho biết giới hạn đồng thời của Bulkhead đã hết; lỗi sau cho biết Circuit Breaker đang chặn lời gọi. Có thể ánh xạ chúng thành response quá tải và dependency tạm thời không khả dụng riêng biệt để log, metric và client hiểu đúng nguyên nhân.

Không đưa ID người dùng, request ID hoặc nội dung exception vào metric tag. Dùng nhóm nguyên nhân hữu hạn như `bulkhead_full`, `circuit_open`, `timeout` và `dependency_error`; thông tin chi tiết để trong log hoặc trace có correlation ID.

## Kiểm thử theo phiên bản đang triển khai

Trước khi đưa vào production, tạo một dependency giả lập có thể trì hoãn response và gửi nhiều subscription đồng thời. Kiểm tra các tình huống:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Số subscription thấp hơn giới hạn | Tất cả được cấp permit và chạy bình thường. |
| Số subscription vượt giới hạn | Phần vượt bị từ chối hoặc chờ theo đúng `maxWaitDuration`. |
| Publisher hoàn tất | Permit được giải phóng để subscription tiếp theo có thể chạy. |
| Subscription bị hủy | Permit được giải phóng theo semantics của operator; xác nhận bằng kiểm thử thực tế. |
| Circuit Breaker `OPEN` | Lời gọi bị Circuit Breaker từ chối và không đi đến dependency. |
| Bulkhead đầy khi Circuit Breaker `CLOSED` | Lời gọi bị Bulkhead từ chối; kiểm tra nó không vô tình làm tăng failure rate dependency nếu đó không phải chính sách mong muốn. |
| Dùng ThreadPoolBulkhead cho client blocking | Công việc chạy trên pool riêng, queue có giới hạn và event-loop không bị block. |

Để xác nhận hỗ trợ theo phiên bản, kiểm tra cả dependency graph, auto-configuration report và hành vi runtime. Chỉ thấy bean `ReactiveCircuitBreakerFactory` chưa đủ để kết luận Bulkhead đã được áp dụng. Hãy xác nhận operator hoặc factory thực sự giới hạn số subscription, từ chối khi hết permit và giải phóng permit sau khi kết thúc hoặc hủy.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Cho rằng reactive tự giới hạn concurrency. | Nhiều subscription có thể đồng thời giữ tài nguyên và gây quá tải. | Dùng Bulkhead hoặc giới hạn concurrency phù hợp. |
| Cho rằng `ReactiveCircuitBreakerFactory` luôn tự có Bulkhead. | Pipeline có thể không hề được giới hạn đồng thời. | Kiểm tra đúng starter, release train và cấu hình runtime. |
| Áp dụng cả auto Bulkhead và `BulkheadOperator` thủ công. | Hai lớp giới hạn chồng nhau và từ chối sớm ngoài dự kiến. | Chỉ rõ một nơi sở hữu chính sách hoặc ghi rõ lý do khi cần nhiều tầng. |
| Chờ permit bằng cách block event-loop. | Làm nghẽn các subscription khác. | Từ chối nhanh hoặc dùng hàng đợi reactive có giới hạn. |
| Dùng ThreadPoolBulkhead cho WebClient non-blocking. | Tạo thêm thread hop và queue không cần thiết. | Ưu tiên SemaphoreBulkhead operator cho pipeline reactive. |
| Xem BulkheadFullException là lỗi dependency. | Failure rate có thể tăng do ứng dụng gọi hết capacity. | Phân biệt lỗi từ chối Bulkhead với lỗi dependency trong metrics và predicate. |
| Chỉ tính giới hạn trên một instance. | Tổng concurrency của nhiều instance vượt năng lực dependency. | Nhân giới hạn theo số instance và caller khác trong hệ thống. |

Reactive Bulkhead có thể bảo vệ ứng dụng mà vẫn giữ pipeline non-blocking, nhưng cách tích hợp cụ thể phụ thuộc starter và phiên bản. Hãy xác nhận hành vi của `ReactiveCircuitBreakerFactory`, kiểm tra Resilience4j Reactor operator khi cần áp dụng thủ công, chọn SemaphoreBulkhead cho subscription reactive và dành ThreadPoolBulkhead cho tác vụ blocking cần cô lập. Khi tách rõ giới hạn đồng thời khỏi lỗi của dependency, hệ thống có thể kiểm soát quá tải mà không làm sai số liệu Circuit Breaker.
