# FrameworkRetryCircuitBreakerFactory và giới hạn ứng dụng reactive

Spring Cloud CircuitBreaker có nhiều implementation đứng sau cùng một abstraction. Một trong số đó là **Framework Retry**, implementation dựa trên khả năng retry gốc được Spring Framework 7 cung cấp. Factory của implementation này có tên FrameworkRetryCircuitBreakerFactory và dùng RetryTemplate, RetryPolicy của Spring Framework để thực hiện retry kết hợp trạng thái Circuit Breaker.

Điểm cần lưu ý khi chọn implementation là Framework Retry chỉ hỗ trợ lời gọi đồng bộ. Nó không cung cấp reactive Circuit Breaker cho Mono hoặc Flux. Nếu ứng dụng đang dùng Spring WebFlux, WebClient và Reactor, hãy chọn implementation có reactive support như Resilience4j. Việc bọc một Mono bằng API đồng bộ không bảo vệ thời điểm publisher thực sự chạy và có thể khiến Circuit Breaker ghi nhận sai kết quả.

## 1. Framework Retry là gì?

Spring Framework 7 bổ sung khả năng retry native trong nhóm tính năng resilience. Spring Cloud CircuitBreaker cung cấp một implementation Circuit Breaker dựa trên RetryTemplate và RetryPolicy của Spring Framework.

Retry và Circuit Breaker giải quyết hai vấn đề có liên quan nhưng khác nhau:

- **Retry** thử lại một thao tác khi gặp lỗi được cho phép, theo chính sách số lần thử, thời gian hoặc loại exception.
- **Circuit Breaker** theo dõi trạng thái của lời gọi và ngăn những lần gọi mới khi một lần thực thi hoàn chỉnh thất bại theo quy tắc của implementation.

FrameworkRetryCircuitBreakerFactory kết hợp hai phần này. Nó tạo Circuit Breaker theo ID và áp dụng cấu hình retry cùng thời gian chuyển trạng thái. Implementation được mô hình theo CircuitBreakerRetryPolicy của Spring Retry: Circuit Breaker mở sau khi một lần thực thi logic thất bại hoàn toàn, tức là các lần retry bên trong đã hết.

Điều này khác với cách Resilience4j thường được cấu hình bằng sliding window và failureRateThreshold. Framework Retry không chờ một tỷ lệ lỗi trên N lời gọi để mở mạch. Một lần thực thi logic thất bại sau khi đã retry hết chính sách có thể làm mạch mở ngay.

## 2. Điều kiện phiên bản và starter

Framework Retry Circuit Breaker dựa trên API retry của Spring Framework 7. Vì vậy, ứng dụng phải dùng phiên bản Spring Boot, Spring Framework và Spring Cloud tương thích với nhau. Nên quản lý phiên bản bằng Spring Cloud BOM thay vì tự chọn một phiên bản starter độc lập.

Thêm starter sau vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-framework-retry</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-framework-retry'
~~~

Starter cung cấp implementation của CircuitBreakerFactory dựa trên Framework Retry. Khi ứng dụng có starter phù hợp trên classpath, Spring Boot auto-configuration tạo factory để service có thể inject.

Không nhầm starter này với starter Spring Retry cũ:

| Implementation | Nền tảng retry | Factory | Reactive support |
|---|---|---|---|
| Framework Retry | RetryTemplate và RetryPolicy của Spring Framework 7 | FrameworkRetryCircuitBreakerFactory | Không |
| Spring Retry | Spring Retry và CircuitBreakerRetryPolicy | SpringRetryCircuitBreakerFactory | Không có reactive factory tương ứng |
| Resilience4j | Resilience4j Retry/CircuitBreaker và các module liên quan | Resilience4JCircuitBreakerFactory; reactive dùng ReactiveResilience4JCircuitBreakerFactory | Có, qua starter Reactor Resilience4j |

Hãy kiểm tra phiên bản Spring Cloud release train và Spring Boot của dự án trước khi thêm starter. Nếu dự án chưa dùng Spring Framework 7, không thể chỉ thêm Framework Retry starter rồi mong các API retry mới xuất hiện.

## 3. Tạo cấu hình mặc định bằng FrameworkRetryCircuitBreakerFactory

Có thể dùng bean Customizer để cấu hình chung cho tất cả Circuit Breaker được tạo từ factory. FrameworkRetryConfigBuilder nhận ID và cho phép thiết lập RetryPolicy, openTimeout và resetTimeout.

Ví dụ cấu hình mặc định:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> defaultCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(RetryPolicy.withMaxRetries(3))
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build()
    );
}
~~~

Ý nghĩa:

- configureDefault áp dụng cấu hình mặc định cho những Circuit Breaker không có cấu hình riêng.
- RetryPolicy.withMaxRetries(3) cho phép chính sách retry tối đa ba lần thử lại theo cách đếm của RetryPolicy.
- openTimeout(Duration.ofSeconds(20)) đặt thời gian mạch ở OPEN trước khi cho một lời gọi thăm dò ở HALF_OPEN.
- resetTimeout(Duration.ofSeconds(5)) đặt khoảng thời gian reset theo hành vi của implementation; nếu không có lỗi mới trong khoảng này, trạng thái có thể tự trở về CLOSED.

Các giá trị chỉ là ví dụ. Số lần retry, khoảng thời gian mở mạch và reset cần được chọn theo độ trễ dependency, deadline của request và hậu quả nghiệp vụ khi lời gọi thất bại.

## 4. Cấu hình riêng theo ID

Factory cho phép cấu hình một Circuit Breaker cụ thể theo ID. Ví dụ, dependency chậm có thể cần thời gian OPEN dài hơn và số lần retry ít hơn:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> slowCustomizer() {
    return factory -> factory.configure(
            builder -> builder
                    .retryPolicy(RetryPolicy.withMaxRetries(1))
                    .openTimeout(Duration.ofSeconds(30))
                    .resetTimeout(Duration.ofSeconds(10))
                    .build(),
            "slow"
    );
}
~~~

Khi code tạo Circuit Breaker bằng ID slow, cấu hình riêng này được sử dụng. Các ID khác tiếp tục nhận cấu hình mặc định nếu không có cấu hình riêng.

Có thể khai báo nhiều cấu hình trong một Customizer:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> specificCustomizer() {
    return factory -> {
        factory.configure(
                builder -> builder
                        .retryPolicy(RetryPolicy.withMaxRetries(1))
                        .openTimeout(Duration.ofSeconds(30))
                        .resetTimeout(Duration.ofSeconds(10))
                        .build(),
                "slow"
        );

        factory.configure(
                builder -> builder
                        .retryPolicy(RetryPolicy.withMaxRetries(5))
                        .openTimeout(Duration.ofMinutes(2))
                        .resetTimeout(Duration.ofSeconds(15))
                        .build(),
                "critical"
        );
    };
}
~~~

ID trong configure phải khớp với ID truyền vào factory.create. Nên đặt ID theo dependency hoặc nhóm thao tác có cùng đặc tính vận hành, ví dụ inventory, payment hoặc customer-profile. Không tạo ID mới cho từng request vì sẽ làm cấu hình và trạng thái Circuit Breaker khó quản lý.

## 5. Các RetryPolicy có thể kết hợp

Spring Framework 7 cung cấp các chính sách retry có thể dùng trong Framework Retry Circuit Breaker:

| RetryPolicy | Ý nghĩa |
|---|---|
| withMaxRetries(int) | Giới hạn số lần retry |
| withMaxDuration(Duration) | Retry trong một khoảng thời gian tối đa |
| withBackoff(Duration, double) | Tăng thời gian chờ giữa các lần thử theo hệ số backoff |
| forExceptions(Class<?>...) | Chỉ retry các loại exception được chỉ định |
| and(...) | Kết hợp điều kiện chính sách theo phép AND |
| or(...) | Kết hợp điều kiện chính sách theo phép OR |

Ví dụ, chỉ retry IOException và TimeoutException, đồng thời giới hạn số lần thử và tổng thời gian:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> retryPolicyCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(
                            RetryPolicy.withMaxRetries(3)
                                    .and(RetryPolicy.withMaxDuration(
                                            Duration.ofSeconds(5)))
                                    .forExceptions(
                                            IOException.class,
                                            TimeoutException.class)
                    )
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build()
    );
}
~~~

Ví dụ này minh họa việc giới hạn cả số lần retry lẫn thời gian retry và lọc exception. Cần kiểm tra cách kết hợp policy theo API của phiên bản Spring Framework đang dùng để bảo đảm điều kiện được hiểu đúng.

Có thể dùng backoff để tránh gửi lại request liên tục:

~~~java
RetryPolicy retryPolicy = RetryPolicy.withMaxRetries(3)
        .withBackoff(Duration.ofMillis(100), 2.0);
~~~

Khoảng chờ tăng dần giúp giảm áp lực lên dependency đang phục hồi. Với hệ thống có nhiều caller, cần cân nhắc jitter nếu thư viện hoặc lớp điều phối bổ sung hỗ trợ, để các caller không cùng retry tại một thời điểm.

Chỉ retry lỗi có khả năng tạm thời. Không retry lỗi xác thực, dữ liệu không hợp lệ hoặc lỗi nghiệp vụ không thể tự phục hồi. Với thao tác có side effect như tạo đơn hàng hoặc trừ tiền, cần idempotency key hoặc cơ chế chống xử lý trùng lặp.

## 6. Cách Framework Retry Circuit Breaker chuyển trạng thái

Framework Retry Circuit Breaker có ba trạng thái chính:

| Trạng thái | Hành vi |
|---|---|
| CLOSED | Cho phép lời gọi đi qua và retry theo RetryPolicy. Nếu một lần thực thi logic thất bại sau khi hết retry, Circuit Breaker mở |
| OPEN | Từ chối nhanh lời gọi mới và chuyển đến fallback nếu được khai báo; không thực hiện retry cho lời gọi bị từ chối |
| HALF_OPEN | Cho phép một lời gọi thăm dò duy nhất để kiểm tra dependency. Nếu thành công, mạch đóng; nếu thất bại, mạch mở lại |

Luồng trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Một lần thực thi thất bại sau khi hết retry
    OPEN --> HALF_OPEN: Hết openTimeout
    HALF_OPEN --> CLOSED: Lời gọi thăm dò thành công
    HALF_OPEN --> OPEN: Lời gọi thăm dò thất bại
~~~

Khác với một số implementation dùng nhiều lời gọi thăm dò ở HALF_OPEN, Framework Retry Circuit Breaker cho phép một lời gọi thăm dò để kiểm tra khả năng phục hồi. Vì vậy, không nên cấu hình hoặc kỳ vọng một nhóm request đồng thời cùng kiểm tra dependency trong trạng thái này.

Khi mạch đang OPEN, lời gọi bị từ chối ngay và không chạy RetryPolicy. Fallback có thể được gọi để trả kết quả thay thế. Khi hết openTimeout, một lời gọi được phép đi qua để kiểm tra. Nếu lần thăm dò thành công, mạch trở về CLOSED; nếu thất bại, mạch trở lại OPEN.

## 7. Phân biệt openTimeout và resetTimeout

Hai thuộc tính này có tên gần giống nhau nhưng phục vụ các mốc thời gian khác nhau:

- **openTimeout** là thời gian Circuit Breaker ở trạng thái OPEN trước khi chuyển sang HALF_OPEN để thử phục hồi. Giá trị mặc định theo tài liệu implementation là 20 giây.
- **resetTimeout** là khoảng chờ sau một lần thất bại để tự reset trạng thái nếu không có lỗi mới trong khoảng thời gian đó. Giá trị mặc định theo tài liệu implementation là 5 giây.

Ví dụ:

~~~java
new FrameworkRetryConfigBuilder("inventory")
        .retryPolicy(RetryPolicy.withMaxRetries(2))
        .openTimeout(Duration.ofSeconds(20))
        .resetTimeout(Duration.ofSeconds(5))
        .build();
~~~

Không dùng resetTimeout để thay thế openTimeout. Một thuộc tính điều khiển khoảng thời gian trước khi thử ở HALF_OPEN; thuộc tính còn lại điều khiển hành vi tự reset khi không có lỗi mới theo cơ chế của implementation.

Do hành vi thời gian có thể ảnh hưởng trực tiếp đến lưu lượng phục hồi, hãy kiểm tra state transition bằng test và metric trên phiên bản đang chạy. Đặc biệt, không giả định resetTimeout giống waitDurationInOpenState của Resilience4j.

## 8. Dùng factory trong lời gọi đồng bộ

FrameworkRetryCircuitBreakerFactory cung cấp CircuitBreakerFactory, vì vậy API sử dụng là CircuitBreaker đồng bộ. Ví dụ service dùng RestTemplate để gọi dịch vụ sách:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class BookService {

    private final CircuitBreaker bookCircuitBreaker;
    private final RestTemplate restTemplate;

    public BookService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestTemplate restTemplate) {
        this.bookCircuitBreaker =
                circuitBreakerFactory.create("bookService");
        this.restTemplate = restTemplate;
    }

    public String getBookTitle(Long bookId) {
        return bookCircuitBreaker.run(
                () -> restTemplate.getForObject(
                        "/books/{id}", String.class, bookId),
                error -> "Fallback Book"
        );
    }
}
~~~

Trong ví dụ:

1. Factory tạo Circuit Breaker có ID bookService.
2. Supplier thực hiện lời gọi blocking qua RestTemplate.
3. Nếu lỗi xảy ra, RetryPolicy được áp dụng theo cấu hình.
4. Nếu toàn bộ lần thực thi thất bại, Circuit Breaker có thể mở.
5. Fallback nhận Throwable và trả kết quả thay thế.
6. Khi Circuit Breaker OPEN, lời gọi mới được từ chối nhanh và fallback có thể được sử dụng.

Fallback nên có ý nghĩa nghiệp vụ. Chuỗi "Fallback Book" chỉ là minh họa. Trong ứng dụng thực tế, có thể trả dữ liệu cache, trạng thái tạm thời hoặc lỗi nghiệp vụ đã chuẩn hóa. Không trả dữ liệu giả như thể đó là dữ liệu mới nhất.

## 9. Vì sao Framework Retry không hỗ trợ ứng dụng reactive?

Reactive application dùng Mono, Flux và subscription để mô tả công việc bất đồng bộ. Publisher thường chưa thực thi tại thời điểm được tạo; nó bắt đầu khi có subscription và phát tín hiệu onNext, onError hoặc onComplete sau đó.

FrameworkRetryCircuitBreakerFactory cung cấp API đồng bộ CircuitBreakerFactory, không cung cấp ReactiveCircuitBreakerFactory. Do đó, implementation này không bảo vệ được vòng đời reactive của Mono hoặc Flux.

Một lỗi thiết kế thường gặp là truyền một Mono vào supplier của CircuitBreaker đồng bộ:

~~~java
Mono<Book> result = circuitBreaker.run(
        () -> webClient.get()
                .uri("/books/{id}", bookId)
                .retrieve()
                .bodyToMono(Book.class),
        error -> Mono.just(Book.fallback())
);
~~~

Đoạn code này không tạo ra reactive Circuit Breaker. Supplier đồng bộ có thể chỉ trả về đối tượng Mono trước khi HTTP request thực sự được subscribe. Circuit Breaker có nguy cơ ghi nhận việc tạo publisher là thành công, trong khi lỗi mạng hoặc timeout chỉ xuất hiện sau đó trong reactive pipeline. Fallback đồng bộ cũng không tương đương fallback dành cho tín hiệu onError của Reactor.

Không giải quyết vấn đề bằng cách gọi block() trên WebFlux event loop. block() biến luồng xử lý thành chờ đồng bộ, làm mất lợi ích reactive và có thể gây nghẽn event loop hoặc lỗi khi block trên thread không cho phép blocking.

## 10. Chọn Resilience4j cho reactive application

Nếu service dùng WebFlux, WebClient, Mono hoặc Flux, hãy dùng reactive starter của Resilience4j:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

ReactiveCircuitBreakerFactory tạo ReactiveCircuitBreaker theo ID. Phương thức run nhận publisher chính và fallback publisher có cùng kiểu:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class ReactiveBookService {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker bookCircuitBreaker;

    public ReactiveBookService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.bookCircuitBreaker = factory.create("bookService");
    }

    public Mono<Book> getBook(Long bookId) {
        Mono<Book> remoteCall = webClient.get()
                .uri("/books/{id}", bookId)
                .retrieve()
                .bodyToMono(Book.class);

        return bookCircuitBreaker.run(
                remoteCall,
                error -> Mono.just(Book.fallback())
        );
    }
}
~~~

Với Flux, fallback cũng phải trả Flux có cùng kiểu phần tử. ReactiveCircuitBreaker bảo vệ quá trình thực thi publisher, nên lỗi phát sinh khi subscription được quan sát trong reactive pipeline.

Cấu hình Resilience4j cho reactive starter có thể dùng các thuộc tính Circuit Breaker quen thuộc như slidingWindowType, slidingWindowSize, minimumNumberOfCalls, failureRateThreshold và waitDurationInOpenState. Cách cấu hình cụ thể phụ thuộc implementation và phiên bản. Resilience4j cũng cung cấp module Retry, TimeLimiter và Bulkhead để phối hợp với Circuit Breaker trong ứng dụng reactive.

Không nên thêm Framework Retry starter với kỳ vọng nó tự chuyển thành reactive implementation. Nếu một ứng dụng có cả phần blocking và reactive, hãy chọn đúng factory và implementation cho từng luồng. Tránh bọc publisher bằng factory đồng bộ.

## 11. So sánh Framework Retry với Resilience4j

| Tiêu chí | Framework Retry | Resilience4j |
|---|---|---|
| Nền tảng | Spring Framework 7 RetryTemplate và RetryPolicy | Thư viện Resilience4j |
| API Spring Cloud | CircuitBreakerFactory | CircuitBreakerFactory và ReactiveCircuitBreakerFactory |
| Reactive | Không hỗ trợ | Có hỗ trợ với Reactor integration |
| Cách mở mạch | Một lần thực thi logic thất bại sau khi retry hết có thể mở mạch | Có thể dùng failure rate, slow call rate và sliding window |
| HALF_OPEN | Một lời gọi thăm dò | Có thể cấu hình số lời gọi được phép thăm dò |
| Retry | RetryPolicy của Spring Framework | Resilience4j Retry |
| Bulkhead/Rate Limiter | Không phải trọng tâm của implementation này | Có module tương ứng |
| Cấu hình | FrameworkRetryConfigBuilder và Customizer | Customizer, properties và cấu hình Resilience4j |
| Phù hợp | Ứng dụng blocking đã dùng Spring Framework 7 Retry | Ứng dụng cần nhiều chính sách resilience hoặc reactive |

Framework Retry có lợi thế tích hợp với API retry native của Spring Framework 7. Resilience4j phù hợp khi cần cấu hình thống kê lỗi chi tiết, slow-call threshold, sliding window, Bulkhead, Rate Limiter và reactive support.

Không nên chọn chỉ dựa vào số lượng dependency. Hãy xét mô hình xử lý, cách cần đo lỗi và các chính sách cần có. Một ứng dụng blocking đơn giản có thể phù hợp với Framework Retry; một ứng dụng WebFlux hoặc cần nhiều lớp bảo vệ thường phù hợp với Resilience4j.

## 12. Các giới hạn và lỗi triển khai thường gặp

- **Dùng Framework Retry với Spring Framework cũ hơn 7**: các API native Retry cần thiết không có trong phiên bản đó.
- **Nhầm Framework Retry với Spring Retry**: hai implementation có tên gần nhau nhưng dùng API và starter khác nhau.
- **Kỳ vọng có ReactiveCircuitBreakerFactory**: Framework Retry implementation không cung cấp reactive support.
- **Bọc Mono bằng CircuitBreaker đồng bộ**: Circuit Breaker có thể chỉ thấy publisher được tạo, không thấy lỗi xảy ra khi subscription.
- **Gọi block() trong event loop**: có thể làm nghẽn WebFlux và làm hỏng mô hình reactive.
- **Cho rằng mỗi attempt lỗi đều mở mạch**: implementation mở mạch khi một lần thực thi logic hoàn chỉnh thất bại sau khi RetryPolicy đã hết.
- **Retry mọi exception**: lỗi nghiệp vụ hoặc lỗi cấu hình không tự hết khi thử lại.
- **Không giới hạn thời gian tổng thể**: retry nhiều lần có thể vượt deadline của request.
- **Retry thao tác không idempotent**: có thể tạo side effect trùng lặp khi server đã xử lý lần đầu nhưng response bị mất.
- **Nhầm openTimeout với resetTimeout**: hai thuộc tính điều khiển các mốc thời gian khác nhau.
- **Kỳ vọng nhiều lời gọi HALF_OPEN đồng thời**: Framework Retry cho phép một lời gọi thăm dò.
- **Cấu hình ID không thống nhất**: ID trong factory.create phải tương ứng với cấu hình riêng đã khai báo.

## 13. Quy trình lựa chọn và kiểm chứng

Khi triển khai FrameworkRetryCircuitBreakerFactory, có thể thực hiện theo trình tự:

1. Xác nhận ứng dụng dùng Spring Framework 7 và Spring Cloud release train tương thích.
2. Xác định lời gọi cần bảo vệ là blocking hay reactive.
3. Nếu blocking, thêm spring-cloud-starter-circuitbreaker-framework-retry.
4. Cấu hình RetryPolicy, openTimeout và resetTimeout bằng Customizer.
5. Tạo Circuit Breaker theo ID ổn định và bọc lời gọi blocking cùng fallback.
6. Chỉ retry các exception tạm thời, giới hạn số lần thử và ngân sách thời gian.
7. Kiểm tra trạng thái CLOSED, OPEN và HALF_OPEN bằng tình huống thành công, lỗi sau retry và phục hồi.
8. Xác minh một lời gọi thăm dò được thực hiện sau openTimeout và kết quả của nó quyết định đóng hoặc mở lại mạch.
9. Nếu ứng dụng reactive, dùng reactive Resilience4j starter và ReactiveCircuitBreakerFactory thay vì Framework Retry.
10. Theo dõi lỗi, số lần retry, fallback và thời gian phản hồi để điều chỉnh chính sách.

FrameworkRetryCircuitBreakerFactory là lựa chọn cho lời gọi đồng bộ trên nền Spring Framework 7. Nó kết hợp RetryPolicy với trạng thái Circuit Breaker, mở mạch sau khi một lần thực thi logic thất bại hoàn toàn và cho một lời gọi thăm dò ở HALF_OPEN. Implementation không hỗ trợ Mono hoặc Flux; ứng dụng reactive cần ReactiveCircuitBreaker của Resilience4j để Circuit Breaker quan sát đúng vòng đời subscription và tín hiệu lỗi.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker — Configuring Framework Retry Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html)
- [Spring Cloud CircuitBreaker — Tổng quan các implementation và API](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
