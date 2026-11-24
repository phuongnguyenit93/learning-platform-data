# Bảo vệ lời gọi blocking và luồng WebClient với cùng mục tiêu nghiệp vụ

## Mục tiêu thực hành

Một ứng dụng Spring Cloud cần lấy thông tin sản phẩm từ `catalog-service`. Có hai cách triển khai phổ biến: gọi HTTP đồng bộ bằng `RestTemplate`, hoặc tạo pipeline reactive bằng `WebClient`. Cả hai cách đều cần đạt cùng mục tiêu nghiệp vụ: lấy được dữ liệu sản phẩm khi dependency khỏe, phản hồi có ý nghĩa khi dependency lỗi và ngăn request mới tiếp tục dồn vào một dịch vụ đang suy giảm.

Trong bài này, ta xây dựng hai đường gọi độc lập cho cùng nghiệp vụ tra cứu sản phẩm. Đường blocking dùng `CircuitBreakerFactory`; đường reactive dùng `ReactiveCircuitBreakerFactory`. Mỗi đường có timeout phù hợp với HTTP client, fallback cùng ngữ nghĩa và metrics riêng.

Sau khi hoàn thành, cần phân biệt được:

- Cách đặt Circuit Breaker quanh một supplier đồng bộ so với một publisher `Mono`.
- Vì sao `CircuitBreakerFactory` và `ReactiveCircuitBreakerFactory` là hai API khác nhau.
- Cách đặt timeout ở HTTP client hoặc trong pipeline reactive.
- Cách giữ cùng hợp đồng response dù implementation blocking hay reactive.
- Cách kiểm tra trạng thái `CLOSED`, `OPEN`, `HALF_OPEN` và xác nhận fallback không che mất lỗi dependency.

## Mô hình và hợp đồng nghiệp vụ

Hai cách triển khai đều truy vấn cùng endpoint `GET /products/{id}` của `catalog-service`:

```text
                    Product API
                         |
              Chọn một implementation
                    /          \
                   /            \
           Blocking path      Reactive path
           RestTemplate       WebClient
                |                 |
       CircuitBreakerFactory  ReactiveCircuitBreakerFactory
                |                 |
                +--------+--------+
                         |
                   catalog-service
```

Hợp đồng trả về dùng chung một kiểu `ProductView` với ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `CURRENT` | Lấy được dữ liệu hiện tại từ catalog. |
| `UNAVAILABLE` | Không lấy được dữ liệu do dependency lỗi hoặc Circuit Breaker từ chối. |
| `NOT_FOUND` | Catalog xác nhận sản phẩm không tồn tại, nếu API biểu diễn trường hợp này theo hợp đồng nghiệp vụ. |

Không trả số lượng bằng 0, giá bằng 0 hoặc object rỗng khi lời gọi thất bại. Những giá trị đó có thể bị hiểu nhầm là dữ liệu thật. Fallback `UNAVAILABLE` phải phân biệt rõ với `NOT_FOUND`.

Hai implementation là hai lựa chọn cho cùng use case. Trong một request nghiệp vụ, chỉ gọi một đường phù hợp với stack của ứng dụng. Không gọi cả blocking lẫn reactive chỉ để “thử cả hai”, vì như vậy tạo hai request đến dependency và có thể nhân tải khi hệ thống đang lỗi.

## 1. Khai báo dependency và chọn stack

Quản lý phiên bản Spring Boot và Spring Cloud bằng các BOM tương thích. Với Resilience4j, ứng dụng dùng đường blocking cần provider Spring Cloud Circuit Breaker imperative; đường WebFlux cần provider Reactor:

```xml
<dependencies>
    <!-- Chọn dependency theo stack của ứng dụng. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <!-- Chỉ thêm khi ứng dụng thực sự có pipeline WebFlux/Reactor. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

Nếu dự án chỉ dùng MVC và `RestTemplate`, chỉ cần provider imperative. Nếu dự án chỉ dùng WebFlux và `WebClient`, dùng reactive provider. Nếu một ứng dụng thực sự cần cả hai API, kiểm tra runtime dependency graph và auto-configuration của đúng release train để xác nhận cả hai factory được tạo mà không có xung đột. Không thêm cả hai starter một cách máy móc.

Tên artifact Gateway/Starter và điều kiện auto-configuration có thể thay đổi theo release train. Để Spring Cloud BOM quản lý version của starter, không override Spring Cloud Circuit Breaker hoặc Resilience4j riêng lẻ nếu chưa xác minh ma trận tương thích.

## 2. Tạo kiểu dữ liệu dùng chung

Hai đường gọi dùng chung response domain. Ví dụ dùng record; nếu ứng dụng chạy Java cũ hơn, có thể thay bằng class bất biến thông thường:

```java
public record Product(String id, String name, long priceInCents) {}

public enum ProductState {
    CURRENT,
    UNAVAILABLE,
    NOT_FOUND
}

public record ProductView(
    String id,
    String name,
    Long priceInCents,
    ProductState state
) {
    public static ProductView current(Product product) {
        return new ProductView(
            product.id(), product.name(), product.priceInCents(),
            ProductState.CURRENT
        );
    }

    public static ProductView unavailable(String id) {
        return new ProductView(id, null, null, ProductState.UNAVAILABLE);
    }

    public static ProductView notFound(String id) {
        return new ProductView(id, null, null, ProductState.NOT_FOUND);
    }
}
```

`priceInCents` là `Long` để trạng thái unavailable không bị biểu diễn thành giá 0. Ở API thực tế, có thể dùng một response DTO riêng, nhưng giữ cùng semantics giữa hai implementation để client không phải hiểu hai kiểu lỗi khác nhau.

Validation dữ liệu đầu vào nên diễn ra trước vùng Circuit Breaker. Ví dụ, nếu `productId` rỗng thì trả lỗi validation ngay; không ghi nhận lỗi local đó như lỗi của `catalog-service`.

## 3. Cấu hình Circuit Breaker theo hai ID

Dùng hai ID ổn định để theo dõi từng execution path:

- `catalogBlocking` dành cho lời gọi đồng bộ.
- `catalogReactive` dành cho publisher WebClient.

Ví dụ `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBlocking:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      catalogReactive:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
```

Hai cấu hình có ngưỡng giống nhau để so sánh hành vi. Tên riêng giúp dashboard phân biệt hai đường thực thi. Tuy nhiên, hai ID này tạo hai trạng thái Circuit Breaker độc lập; chúng không chia sẻ sliding window hay trạng thái chỉ vì cùng trỏ đến một backend. Nếu cả hai path chạy trong cùng ứng dụng và cùng gửi tải đến catalog, phải tính tổng lưu lượng của cả hai khi đặt ngân sách concurrency.

Nếu muốn dùng chung một breaker state cho cả hai đường, cần một thiết kế/provider hỗ trợ cùng registry và cùng instance một cách rõ ràng. Không giả định imperative và reactive factory tự động chia sẻ trạng thái. Trong thực hành này, tách ID để dễ quan sát và tránh trộn hai loại call path.

## 4. Đường blocking với RestTemplate

### Cấu hình HTTP client timeout

Với lời gọi blocking, timeout nên được cấu hình ngay ở HTTP client. Ví dụ dùng `RestTemplateBuilder`:

```java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class BlockingHttpConfiguration {

    @Bean
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder
            .setConnectTimeout(Duration.ofMillis(300))
            .setReadTimeout(Duration.ofSeconds(2))
            .build();
    }
}
```

Connect timeout giới hạn thời gian thiết lập kết nối; read timeout giới hạn thời gian chờ dữ liệu phản hồi theo semantics của request factory đang dùng. Đây không nhất thiết là deadline tổng của toàn bộ nghiệp vụ. Nếu cần deadline tổng, quản lý thêm ở tầng gọi và bảo đảm nó phù hợp với timeout của client.

### Bọc lời gọi bằng CircuitBreakerFactory

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

@Service
public class BlockingProductService {
    private final RestTemplate catalogRestTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public BlockingProductService(
            RestTemplate catalogRestTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogRestTemplate = catalogRestTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductView find(String productId) {
        validate(productId);

        return circuitBreakerFactory.create("catalogBlocking").run(
            () -> {
                try {
                    Product product = catalogRestTemplate.getForObject(
                        "http://catalog-service/products/{id}",
                        Product.class,
                        productId
                    );
                    if (product == null) {
                        throw new IllegalStateException("Catalog returned an empty body");
                    }
                    return ProductView.current(product);
                } catch (HttpClientErrorException.NotFound notFound) {
                    return ProductView.notFound(productId);
                }
            },
            error -> ProductView.unavailable(productId)
        );
    }

    private void validate(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("productId is required");
        }
    }
}
```

Trong ví dụ, HTTP 404 được chuyển thành kết quả nghiệp vụ `NOT_FOUND`, không phải fallback unavailable. Các lỗi kết nối, timeout và server 5xx tiếp tục thoát khỏi supplier để Circuit Breaker có thể phân loại. Fallback chỉ tạo trạng thái `UNAVAILABLE`.

`RestTemplate` mặc định chuyển response 4xx/5xx thành exception. Khi thay error handler hoặc HTTP client, xác nhận lại mapping status để tránh vô tình biến 503 thành response bình thường. Với hệ thống thật, base URL nên lấy từ cấu hình hoặc service discovery thay vì hard-code.

## 5. Đường reactive với WebClient

### Cấu hình WebClient

WebClient thường dùng Reactor Netty. Cấu hình connect/response timeout ở HTTP client và thêm timeout trong pipeline nếu cần giới hạn thời gian hoàn tất của publisher:

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveHttpConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
            .responseTimeout(Duration.ofSeconds(2));

        return builder
            .baseUrl("http://catalog-service")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
```

Timeout ở Reactor Netty giới hạn các giai đoạn mạng theo cấu hình client. Có thể thêm `Mono.timeout(...)` để đặt giới hạn thời gian cho pipeline tổng hợp. Hai lớp timeout cần được phối hợp; không đặt các giá trị mâu thuẫn khiến request bị hủy quá sớm hoặc chờ lâu hơn deadline nghiệp vụ.

### Bọc publisher bằng ReactiveCircuitBreakerFactory

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductService {
    private final WebClient catalogWebClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveProductService(
            WebClient catalogWebClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogWebClient = catalogWebClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductView> find(String productId) {
        if (productId == null || productId.isBlank()) {
            return Mono.error(new IllegalArgumentException("productId is required"));
        }

        Mono<ProductView> primary = Mono.defer(() ->
            catalogWebClient.get()
                .uri("/products/{id}", productId)
                .retrieve()
                .onStatus(
                    status -> status.value() == 404,
                    response -> response.createException()
                )
                .bodyToMono(Product.class)
                .timeout(Duration.ofSeconds(2))
                .map(ProductView::current)
                .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    error -> Mono.just(ProductView.notFound(productId))
                )
        );

        return circuitBreakerFactory.create("catalogReactive").run(
            primary,
            error -> Mono.just(ProductView.unavailable(productId))
        );
    }
}
```

`Mono.defer` trì hoãn việc tạo request cho đến khi có subscription. `ReactiveCircuitBreakerFactory` bọc publisher và nhận fallback publisher. Khi HTTP client phát lỗi kết nối, timeout hoặc lỗi server, integration có thể ghi nhận theo chính sách Circuit Breaker rồi chuyển sang fallback.

Trong ví dụ, 404 được ánh xạ thành `NOT_FOUND`; các lỗi còn lại có thể đi đến fallback `UNAVAILABLE`. Hãy kiểm tra đúng kiểu exception và cách `onStatus` hoạt động trong phiên bản Spring WebFlux đang dùng. Nếu cần để Circuit Breaker ghi nhận 404 là lỗi, không chuyển nó thành kết quả domain bên trong publisher trước khi breaker quan sát.

Không gọi `block()` hoặc `subscribe()` thủ công trong service này. Trả `Mono` về controller để WebFlux quản lý subscription, cancellation và error handling theo vòng đời request.

## 6. So sánh ranh giới bảo vệ

| Nội dung | Blocking | Reactive |
| --- | --- | --- |
| HTTP client | `RestTemplate` | `WebClient` |
| Factory | `CircuitBreakerFactory` | `ReactiveCircuitBreakerFactory` |
| Kiểu kết quả | `ProductView` | `Mono<ProductView>` |
| Supplier | `Supplier<T>` đồng bộ | `Mono<T>` được subscribe sau |
| Timeout chính | Connect/read timeout của HTTP client | Timeout của Reactor Netty và/hoặc `Mono.timeout` |
| Fallback | Hàm trả `ProductView` | Hàm trả `Mono<ProductView>` |
| Threading | Thread gọi chờ kết quả HTTP | Pipeline non-blocking, không block event-loop |

Điểm chung là Circuit Breaker bao quanh lời gọi đến dependency và fallback giữ cùng ngữ nghĩa nghiệp vụ. Điểm khác là blocking call thực thi ngay trong supplier khi được gọi; reactive call được thực thi khi publisher được subscribe. Vì vậy, với reactive phải kiểm soát số subscription để không gửi request trùng.

## 7. Cấu hình phân loại lỗi

Không phải mọi exception đều là dấu hiệu dependency suy giảm. Validation sai là lỗi caller; 404 có thể là kết quả nghiệp vụ; timeout, lỗi kết nối và 5xx thường là tín hiệu cần ghi nhận.

Với Resilience4j, có thể cấu hình instance để bỏ qua một số lỗi nghiệp vụ cụ thể. Ví dụ dưới đây chỉ minh họa cách phân loại cho một dependency; cần kiểm tra kiểu exception thực tế của HTTP client:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBlocking:
        ignoreExceptions:
          - com.example.catalog.InvalidProductRequestException
      catalogReactive:
        ignoreExceptions:
          - com.example.catalog.InvalidProductRequestException
```

Không bỏ qua toàn bộ `RuntimeException`, `RestClientException` hoặc `WebClientResponseException`; các nhóm rộng này có thể bao gồm lỗi kết nối và lỗi server cần được ghi nhận. Cũng không coi mọi HTTP 4xx là lỗi hạ tầng. Nếu 429 biểu thị dependency quá tải, cân nhắc phân loại nó là lỗi; nếu 404 là sản phẩm không tồn tại, chuyển thành `NOT_FOUND` theo hợp đồng API.

Nếu có lỗi bị bọc trong `CompletionException` hoặc wrapper của client, kiểm tra cause trước khi định nghĩa predicate. Cấu hình exception cho imperative và reactive factory có thể cần được áp dụng qua cơ chế provider tương ứng; xác nhận tên instance và runtime behavior thay vì giả định một customizer áp dụng cho cả hai factory.

## 8. Không để fallback che mất sự cố

Fallback giúp giữ trải nghiệm nhưng có thể làm response cuối trông như thành công. Vì vậy, đo riêng:

- Số lần gọi blocking và reactive.
- Số lần supplier/publisher bắt đầu thực thi.
- Số timeout, lỗi kết nối, HTTP 5xx và lỗi bị bỏ qua.
- Số lần Circuit Breaker từ chối khi `OPEN`.
- Số lần fallback được gọi và số lần fallback tự thất bại.
- Latency của đường chính và latency của fallback.

Dùng breaker ID làm tag có giới hạn, ví dụ `catalogBlocking` và `catalogReactive`. Không đưa product ID, user ID, URL đầy đủ hoặc exception message vào metric tag. Các giá trị có cardinality cao nên nằm trong log hoặc distributed trace.

Hai breaker trong ví dụ có state riêng. Nếu `catalogBlocking` mở nhưng `catalogReactive` vẫn đóng, điều đó không nhất thiết là sai; có thể hai path có lưu lượng hoặc lịch sử lỗi khác nhau. Dashboard nên hiển thị riêng từng ID và đồng thời tổng hợp request thực tế đến backend để đánh giá tổng tải.

## 9. Kiểm thử đường blocking

Dùng mock HTTP server hoặc WireMock để kiểm soát response của catalog. Với blocking service, kiểm tra:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Catalog trả 200 | Trả `ProductView` trạng thái `CURRENT`. |
| Catalog trả 404 | Trả trạng thái `NOT_FOUND` theo mapping nghiệp vụ. |
| Catalog trả 503 | Circuit Breaker ghi nhận lỗi và fallback trả `UNAVAILABLE`. |
| Kết nối bị từ chối | HTTP client ném lỗi transport; fallback được gọi. |
| Read timeout | Supplier kết thúc trong giới hạn timeout; breaker ghi nhận theo cấu hình. |
| Breaker `OPEN` | Supplier không gọi HTTP client; fallback trả `UNAVAILABLE`. |
| Probe ở `HALF_OPEN` thành công | Breaker có thể trở về `CLOSED` sau đủ kết quả thử. |

Để xác nhận breaker mở, tạo đủ số kết quả theo `minimumNumberOfCalls` và `slidingWindowSize`. Không chỉ gọi một lần rồi kỳ vọng trạng thái `OPEN` nếu cấu hình yêu cầu nhiều mẫu.

## 10. Kiểm thử đường reactive

Với `WebClient`, dùng mock server và `StepVerifier` để xác nhận tín hiệu publisher:

```java
StepVerifier.create(reactiveProductService.find("p-100"))
    .expectNextMatches(view -> view.state() == ProductState.CURRENT)
    .verifyComplete();
```

Kiểm tra thêm các trường hợp:

- Response 404 được chuyển thành `NOT_FOUND`.
- Response 503 hoặc lỗi kết nối đi đến fallback `UNAVAILABLE`.
- Timeout phát ra trong publisher được Circuit Breaker quan sát theo cấu hình.
- Khi breaker `OPEN`, không có HTTP request mới đến mock server và fallback được phát ra.
- Một subscription tạo đúng một request; không gọi `subscribe()` bên trong service.
- Hủy subscription giải phóng tài nguyên theo semantics của WebClient và operator.

Nếu dùng `Mono.defer`, mỗi subscription có thể tạo một request mới. Đừng subscribe cùng publisher nhiều lần nếu nghiệp vụ chỉ cần một lần gọi. Đếm số request tại mock server để phát hiện việc gọi trùng; số lần gọi method Java không đủ để chứng minh số request mạng.

## 11. Kiểm thử cùng mục tiêu nghiệp vụ

Viết contract test dùng cùng bộ trường hợp cho hai implementation. Có thể tạo một interface test hoặc test suite dùng chung để xác nhận cả blocking và reactive đều trả cùng semantics:

| Đầu vào từ catalog | Blocking result | Reactive result |
| --- | --- | --- |
| HTTP 200 với sản phẩm hợp lệ | `CURRENT` | `CURRENT` |
| HTTP 404 | `NOT_FOUND` | `NOT_FOUND` |
| HTTP 503 | `UNAVAILABLE` sau fallback | `UNAVAILABLE` sau fallback |
| Connection timeout | `UNAVAILABLE` sau fallback | `UNAVAILABLE` sau fallback |
| Circuit Breaker `OPEN` | `UNAVAILABLE`, không gọi backend | `UNAVAILABLE`, không subscribe đến request backend |

Hai path cần thống nhất response domain nhưng không nhất thiết chia sẻ trạng thái Circuit Breaker. Nếu kiểm thử so sánh trạng thái breaker, hãy kiểm tra riêng `catalogBlocking` và `catalogReactive`. Nếu muốn so sánh tổng số request, reset mock server và metrics giữa các test để tránh kết quả của test trước ảnh hưởng test sau.

## 12. Chọn execution model phù hợp

Blocking call phù hợp với service MVC đồng bộ hoặc thư viện cũ chưa có API reactive. Cách này dễ đọc và tích hợp với code đồng bộ, nhưng mỗi request đang chờ thường giữ một thread. Cần giới hạn thread pool, connection pool và timeout.

WebClient phù hợp với WebFlux hoặc khi cần pipeline non-blocking. Nó không tự bảo đảm mọi thứ đều có concurrency vô hạn; vẫn phải giới hạn connection, concurrency, queue và thời gian xử lý. Không chuyển một API blocking sang WebClient bằng cách gọi `block()` rồi cho rằng đã thành reactive.

Không dùng hai implementation cùng lúc cho một request để dự phòng cho nhau. Nếu muốn chuyển traffic giữa hai execution model, quyết định ở tầng routing hoặc deployment và theo dõi tải tổng. Cũng không nên để cùng một request thực hiện blocking call trước rồi reactive call sau khi lỗi; cách đó nhân latency và tải dependency.

## 13. Quy trình thực hành hoàn chỉnh

1. Tạo DTO/domain `ProductView` dùng chung với các trạng thái `CURRENT`, `NOT_FOUND` và `UNAVAILABLE`.
2. Cấu hình timeout cho `RestTemplate` và `WebClient` theo deadline nghiệp vụ.
3. Cấu hình hai Circuit Breaker ID riêng và ngưỡng thử nghiệm trong Resilience4j.
4. Implement đường blocking bằng `CircuitBreakerFactory.create("catalogBlocking").run(...)`.
5. Implement đường reactive bằng `ReactiveCircuitBreakerFactory.create("catalogReactive").run(...)`.
6. Giữ validation bên ngoài vùng bảo vệ và chỉ đặt lời gọi dependency trong supplier/publisher.
7. Ánh xạ 404 thành `NOT_FOUND`; để timeout, lỗi kết nối và 5xx được phân loại theo chính sách; fallback trả `UNAVAILABLE`.
8. Kiểm thử success, not found, 5xx, connection failure, timeout, `OPEN` và `HALF_OPEN` cho cả hai path.
9. Đếm request thực tế đến mock server, xác nhận reactive publisher không bị subscribe trùng.
10. Đối chiếu metrics theo breaker ID và kiểm tra fallback không che mất lỗi dependency.

## Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng imperative factory để bọc `Mono` | Publisher không được bảo vệ theo reactive semantics. | Dùng `ReactiveCircuitBreakerFactory`. |
| Dùng reactive factory cho supplier blocking | Có thể block event-loop hoặc làm sai execution model. | Dùng factory imperative cho lời gọi đồng bộ. |
| Không đặt timeout ở HTTP client | Thread hoặc subscription giữ tài nguyên quá lâu. | Đặt connect/read/response timeout và deadline tổng. |
| Đặt fallback trước Circuit Breaker | Breaker có thể thấy kết quả thành công và không tăng failure rate. | Đặt fallback ở ngoài operator hoặc dùng fallback function của factory. |
| Chuyển 404 thành lỗi hạ tầng | Circuit Breaker mở vì sản phẩm không tồn tại. | Ánh xạ 404 theo hợp đồng domain. |
| Subscribe nhiều lần vào publisher cold | Một nghiệp vụ tạo nhiều HTTP request. | Giữ một subscription trong request lifecycle và kiểm tra bằng mock server. |
| Gọi cả blocking và reactive cho cùng request | Tăng gấp đôi tải và latency. | Chọn một execution path cho mỗi request. |
| Nghĩ hai factory tự chia sẻ trạng thái | Metrics và state bị diễn giải sai. | Dùng ID riêng và quan sát từng factory/instance. |
| Chỉ kiểm tra response cuối cùng | Fallback che khuất sự cố dependency. | Đo primary, fallback và state transition riêng. |

## Kết quả cần đạt

Hai implementation phải phục vụ cùng hợp đồng nghiệp vụ nhưng giữ đúng đặc điểm của từng execution model. Blocking path dùng `CircuitBreakerFactory` và timeout của HTTP client đồng bộ; reactive path dùng `ReactiveCircuitBreakerFactory`, publisher `Mono` và timeout trong pipeline/client. Cả hai phân loại lỗi nhất quán, trả fallback `UNAVAILABLE` có ý nghĩa và được quan sát bằng ID riêng. Khi kiểm thử được success, not found, timeout, fallback và trạng thái `OPEN`/`HALF_OPEN`, ta có thể chứng minh dependency được bảo vệ mà không làm sai semantics của response hoặc vô tình gửi request trùng.
