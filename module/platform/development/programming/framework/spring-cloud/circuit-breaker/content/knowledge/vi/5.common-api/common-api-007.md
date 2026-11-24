# Phạm vi cấu hình có thể dùng chung giữa các hiện thực

## Mục tiêu

Spring Cloud CircuitBreaker cung cấp một lớp API để ứng dụng gọi dịch vụ phụ thuộc thông qua Circuit Breaker mà không phải gắn trực tiếp mọi lời gọi với một thư viện cụ thể. Lớp trừu tượng này giúp tái sử dụng cách gọi và cách tổ chức mã, nhưng không biến mọi tùy chọn cấu hình của các thư viện thành một bộ thuộc tính giống hệt nhau.

Sau bài học, bạn có thể:

- Phân biệt phần API dùng chung với phần cấu hình riêng của từng implementation.
- Dùng `CircuitBreakerFactory` và `ReactiveCircuitBreakerFactory` để tạo Circuit Breaker theo tên.
- Tổ chức tên instance, fallback và chính sách ứng dụng sao cho có thể thay đổi implementation với ít thay đổi ở tầng gọi.
- Cấu hình mặc định và cấu hình theo instance cho Resilience4j, đồng thời nhận biết giới hạn khi chuyển sang implementation khác.
- Tránh giả định rằng timeout, sliding window, bulkhead, retry và metric có cùng ngữ nghĩa hoặc cùng thuộc tính giữa các implementation.

## API chung và cấu hình riêng là hai lớp khác nhau

Spring Cloud CircuitBreaker định nghĩa abstraction để ứng dụng sử dụng Circuit Breaker. Ở tầng gọi, mã ứng dụng thường cần biết tên của dependency, thao tác cần thực hiện và cách xử lý khi thao tác thất bại. Implementation cụ thể chịu trách nhiệm thực thi chính sách bảo vệ.

| Phần | Có thể tổ chức dùng chung | Phụ thuộc implementation |
|---|---|---|
| Tạo bộ ngắt mạch | Tạo theo tên dependency bằng factory. | Factory bean và starter được cung cấp bởi implementation đã chọn. |
| Gọi đồng bộ | Bao thao tác trong `run` và cung cấp fallback. | Cách đánh giá lỗi, lưu trạng thái và thực thi nội bộ. |
| Gọi reactive | Có abstraction reactive khi implementation hỗ trợ. | Mức hỗ trợ reactive và cách tích hợp publisher phụ thuộc starter/phiên bản. |
| Định danh | Quy ước tên như `catalog`, `payment`, `inventory`. | Quy tắc ánh xạ tên sang instance hoặc nhóm cấu hình. |
| Chính sách nghiệp vụ | Timeout mục tiêu, mức lỗi chấp nhận được, hành vi fallback có thể được mô tả ở cấp ứng dụng. | Cách biểu diễn và áp dụng từng chính sách trong thư viện cụ thể. |
| Cấu hình chi tiết | Có thể tập trung trong một nơi để quản lý. | Thuộc tính YAML, builder, customizer, metric và event thường không tương thích trực tiếp. |

Ví dụ, ứng dụng có thể thống nhất rằng lời gọi tới `catalog` cần giới hạn thời gian chờ, có fallback từ cache và phải được theo dõi độc lập. Resilience4j có thể biểu diễn chính sách này bằng Circuit Breaker, TimeLimiter và Bulkhead. Một implementation khác có thể dùng retry policy hoặc cơ chế giới hạn khác. Ý định của ứng dụng vẫn giống nhau, nhưng không nên giả định mọi implementation cung cấp cùng một thuật toán hay cùng một mức bảo vệ.

## Tạo Circuit Breaker qua factory

Với lời gọi đồng bộ, ứng dụng dùng `CircuitBreakerFactory` để tạo một Circuit Breaker theo tên. Tên này là định danh ổn định của dependency trong ứng dụng và thường cũng là khóa cấu hình instance của implementation.

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogGateway(
            RestClient restClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = restClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Product findProduct(String id) {
        CircuitBreaker breaker = circuitBreakerFactory.create("catalog");

        return breaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(Product.class),
                error -> Product.unavailable(id));
    }
}
```

`Product` và `Product.unavailable` là kiểu dữ liệu ví dụ của ứng dụng. Fallback cần có cùng kiểu kết quả với lời gọi gốc và phải thể hiện rõ dữ liệu không khả dụng hoặc dữ liệu cache. Không nên trả về một đối tượng trông như kết quả đầy đủ nếu ứng dụng không thể bảo đảm nội dung đó chính xác.

Factory cũng có thể nhận tên nhóm bên cạnh tên instance bằng API `create(id, groupName)` nếu implementation hỗ trợ cách ánh xạ đó. Hãy dùng `id` ổn định theo dependency và chỉ dùng group khi cần chia sẻ một cấu hình cho nhiều instance. Không tạo tên mới theo từng request, vì điều đó có thể làm số lượng Circuit Breaker và metric tăng không kiểm soát.

## API reactive

Với ứng dụng Spring WebFlux, `ReactiveCircuitBreakerFactory` tạo một `ReactiveCircuitBreaker`. Lời gọi và fallback đều giữ dạng reactive, tránh chặn luồng bằng cách gọi `block()`.

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveCatalogGateway(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<Product> findProduct(String id) {
        ReactiveCircuitBreaker breaker = circuitBreakerFactory.create("catalog");

        Mono<Product> request = webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);

        return breaker.run(request, error -> Mono.just(Product.unavailable(id)));
    }
}
```

Abstraction reactive giúp giữ cách tổ chức lời gọi tương tự giữa các module ứng dụng. Tuy nhiên, không phải mọi implementation hoặc phiên bản đều hỗ trợ reactive theo cùng cách. Trước khi thay starter, cần xác nhận implementation được chọn cung cấp `ReactiveCircuitBreakerFactory` và có thể thực thi các chính sách cần thiết trong luồng reactive.

## Tên instance là hợp đồng cấu hình của ứng dụng

Nên thống nhất tên Circuit Breaker theo dịch vụ phụ thuộc, chẳng hạn:

| Tên | Dependency | Chính sách ứng dụng điển hình |
|---|---|---|
| `catalog` | Dịch vụ danh mục | Timeout ngắn, fallback đọc cache. |
| `payment` | Cổng thanh toán | Timeout theo SLA, không giả lập giao dịch thành công khi lỗi. |
| `inventory` | Dịch vụ tồn kho | Giới hạn đồng thời, fallback thể hiện trạng thái chưa xác định. |

Tên `catalog` trong mã gọi phải khớp tên instance cấu hình của implementation. Giữ quy ước tên nhất quán giữa mã đồng bộ, reactive, dashboard và cảnh báo giúp thay đổi implementation dễ kiểm soát hơn.

Tên instance cũng không nên đại diện cho một endpoint hoặc tham số biến thiên của request. Ví dụ, không tạo `catalog-product-123` và `catalog-product-456` làm hai Circuit Breaker riêng nếu chúng cùng gọi một dịch vụ danh mục. Circuit Breaker thường bảo vệ một dependency hoặc một nhóm hành vi có cùng đặc tính lỗi.

## Cấu hình Resilience4j: một ví dụ cụ thể

Khi chọn Resilience4j, Spring Cloud CircuitBreaker cung cấp factory và builder tương ứng để cấu hình mặc định hoặc cấu hình riêng theo instance. Đây là API cấu hình của integration Resilience4j, không phải API cấu hình phổ quát cho mọi implementation.

Ví dụ cấu hình mặc định bằng `Customizer`:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
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
}
```

`configureDefault` cung cấp cấu hình mặc định cho các Circuit Breaker do factory tạo. Nếu một dependency cần chính sách khác, có thể dùng `configure` để áp dụng builder cho các ID được chỉ định:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerConfig() {
    return factory -> factory.configure(builder -> builder
                    .circuitBreakerConfig(CircuitBreakerConfig.custom()
                            .slidingWindowSize(10)
                            .minimumNumberOfCalls(5)
                            .failureRateThreshold(40)
                            .build())
                    .timeLimiterConfig(TimeLimiterConfig.custom()
                            .timeoutDuration(Duration.ofMillis(800))
                            .build()),
            "catalog");
}
```

Đoạn cấu hình theo ID là ví dụ minh họa cho integration Resilience4j. Cần giữ các import, kiểu builder và phiên bản Spring Cloud tương thích với dependency management của dự án. Không thể chuyển nguyên `Resilience4JConfigBuilder`, `CircuitBreakerConfig` hoặc `TimeLimiterConfig` sang implementation khác.

Có thể khai báo cấu hình Resilience4j trong YAML để tách chính sách vận hành khỏi mã Java:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
    instances:
      catalog:
        baseConfig: default
      payment:
        baseConfig: default
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
    instances:
      catalog:
        baseConfig: default
      payment:
        baseConfig: default
        timeoutDuration: 800ms
```

`configs.default` là cấu hình dùng làm nền trong Resilience4j; mỗi instance có thể kế thừa bằng `baseConfig` và ghi đè một số thuộc tính. `resilience4j.*` là namespace của Resilience4j. Nếu chuyển sang implementation khác, phải ánh xạ ý định của các giá trị này sang cơ chế cấu hình tương ứng; đổi tên starter không tự chuyển đổi YAML.

## Phần nào thực sự có thể dùng chung?

Một cách thiết kế bền vững là lưu chính sách ở cấp ứng dụng dưới dạng các khái niệm mà nghiệp vụ hiểu, sau đó ánh xạ sang implementation đã chọn. Ví dụ, cấu hình ứng dụng có thể mô tả dependency, thời hạn chờ mục tiêu, ngưỡng lỗi mong muốn và chế độ fallback:

```yaml
app:
  dependency-protection:
    catalog:
      timeout: 2s
      fallback: cache
      availability-target: 99.5
    payment:
      timeout: 800ms
      fallback: unavailable
      availability-target: 99.9
```

Đây là namespace do ứng dụng tự định nghĩa, không phải thuộc tính Spring Cloud CircuitBreaker có sẵn. Một lớp cấu hình của ứng dụng đọc các giá trị này, rồi adapter cho Resilience4j chuyển chúng thành TimeLimiter, CircuitBreaker và Bulkhead. Nếu sau này dùng implementation khác, adapter mới sẽ chuyển chính sách ứng dụng sang các tùy chọn mà implementation đó hỗ trợ.

Không nên cố ép mọi thuộc tính vào một mô hình chung nếu ý nghĩa của chúng khác nhau. Ví dụ:

- `slidingWindowSize` là khái niệm của Circuit Breaker có cửa sổ thống kê; implementation khác có thể không có cửa sổ cùng loại.
- `permittedNumberOfCallsInHalfOpenState` mô tả số probe ở `HALF_OPEN`; không phải mọi thư viện đều có cùng trạng thái hoặc cùng cách cấp phép.
- `TimeLimiter` có thể giới hạn thời gian chờ theo cách riêng; timeout của HTTP client hoặc Reactor không tự động có cùng hành vi hủy tác vụ.
- Bulkhead có thể dùng semaphore hoặc thread pool. Cùng một giới hạn số lời gọi không bảo đảm cùng mô hình tài nguyên hay cùng cách xử lý hàng đợi.
- Retry và Circuit Breaker có thể phối hợp, nhưng chính sách retry không tương đương ngưỡng lỗi và sliding window của Circuit Breaker.

Vì vậy, mô hình dùng chung nên chứa ý định ở cấp ứng dụng và chỉ giữ các thuộc tính có định nghĩa nhất quán. Những khả năng đặc thù cần được biểu diễn như phần mở rộng tùy chọn, có kiểm tra implementation hỗ trợ trước khi bật.

## Khi đổi implementation

Khi thay implementation, hãy rà soát theo từng lớp:

1. **Dependency và auto-configuration:** chọn starter đúng và kiểm tra factory bean được tạo. Không đưa đồng thời nhiều implementation vào classpath nếu cấu hình tự động có thể trở nên mơ hồ.
2. **Tầng gọi:** xác nhận ứng dụng chỉ phụ thuộc vào abstraction Spring Cloud CircuitBreaker ở những nơi cần tính di động. Nếu mã gọi trực tiếp API Resilience4j, phần đó cần được chuyển đổi.
3. **Tên instance:** giữ nguyên quy ước ID ở tầng gọi; ánh xạ chúng sang instance hoặc nhóm cấu hình của implementation mới.
4. **Timeout và fallback:** xác nhận lỗi timeout có được đưa vào Circuit Breaker như dự kiến, fallback có nhận đúng ngoại lệ và thao tác bị hủy đúng cách.
5. **Ngưỡng và trạng thái:** xác định implementation mới có trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`, sliding window và probe tương đương hay không. Nếu khác, chọn chính sách gần nhất và ghi nhận sự khác biệt.
6. **Bulkhead và retry:** kiểm tra giới hạn đồng thời, hàng đợi, số lần thử lại, backoff và thứ tự kết hợp với Circuit Breaker.
7. **Metric và event:** cập nhật dashboard, alert và mã lắng nghe sự kiện vì tên metric, tag và event type có thể khác.
8. **Kiểm thử hành vi:** chạy cùng kịch bản dịch vụ khỏe, lỗi liên tục, phản hồi chậm, phục hồi và quá tải để so sánh kết quả thực tế.

Spring Retry là một ví dụ về implementation có mô hình retry và chính sách thử lại riêng. Không nên sao chép các thuộc tính `resilience4j.circuitbreaker.*` sang cấu hình Spring Retry hoặc kỳ vọng có cùng sliding window, tỷ lệ lỗi, TimeLimiter và Bulkhead. Hãy cấu hình theo API và tài liệu của đúng starter/phiên bản đang dùng, sau đó kiểm tra hành vi qua thử nghiệm.

## Fallback là hợp đồng của ứng dụng

Fallback nằm ở ranh giới giữa bảo vệ kỹ thuật và hành vi sản phẩm. Một số quy tắc có thể dùng chung dù implementation thay đổi:

- Fallback phải tương thích với kiểu trả về của thao tác gốc.
- Fallback không nên gọi lại cùng dependency đang lỗi theo một đường đi không được bảo vệ.
- Dữ liệu cache cần thể hiện được độ cũ nếu điều đó ảnh hưởng quyết định nghiệp vụ.
- Với thanh toán, không được trả về kết quả thành công giả khi không biết giao dịch đã được xử lý hay chưa.
- Cần phân biệt lỗi nghiệp vụ, lỗi đầu vào, lỗi timeout và lỗi do Circuit Breaker từ chối lời gọi.

API fallback của abstraction có thể nhận `Throwable`, nhưng ứng dụng vẫn nên phân loại nguyên nhân trước khi chọn phản hồi. Không phải mọi ngoại lệ đều nên trả cùng một kết quả mặc định.

## Theo dõi và kiểm thử cấu hình

Các tên metric và event phụ thuộc implementation. Với Resilience4j, ứng dụng thường quan sát trạng thái Circuit Breaker, số lời gọi theo kết quả, tỷ lệ lỗi, tỷ lệ lời gọi chậm và số lời gọi bị từ chối qua Micrometer. Implementation khác có thể cung cấp metric với tên, tag hoặc mức chi tiết khác. Nếu cần dashboard dùng chung, hãy chuẩn hóa ở lớp quan sát của ứng dụng thay vì giả định tên metric của thư viện luôn giống nhau.

Một kịch bản kiểm tra cấu hình nên bao gồm:

1. Gửi lời gọi thành công và xác nhận dependency được gọi bình thường.
2. Làm dependency trả lỗi để xác nhận Circuit Breaker ghi nhận lỗi và thực hiện chuyển trạng thái theo cấu hình.
3. Làm dependency phản hồi chậm để xác nhận timeout, hủy tác vụ và fallback hoạt động như dự định.
4. Gửi yêu cầu khi mạch `OPEN` để xác nhận lời gọi bị từ chối nhanh và fallback trả đúng hợp đồng.
5. Khôi phục dependency và quan sát lượt thăm dò `HALF_OPEN` nếu implementation hỗ trợ trạng thái này.
6. Tạo tải đồng thời để kiểm tra Bulkhead nếu đã bật; xác nhận lỗi hết hạn mức không bị nhầm thành lỗi sức khỏe dependency.
7. Đối chiếu metric, log và event với số lời gọi thực tế.

Khi thay implementation, chạy cùng kịch bản với cùng điều kiện tải và cùng chính sách ứng dụng. So sánh cả hành vi người gọi nhìn thấy lẫn tác động tới dependency: số request được chuyển tiếp, thời gian chờ, số lần retry, tỷ lệ fallback và thời gian phục hồi.

## Lỗi thiết kế thường gặp

- **Nhầm abstraction với tính tương thích cấu hình:** API gọi chung không có nghĩa mọi thuộc tính YAML hoặc builder dùng chung.
- **Đưa kiểu Resilience4j vào tầng nghiệp vụ:** điều này khiến việc thay implementation lan ra nhiều lớp mã.
- **Tạo ID theo từng request:** làm tăng số instance, metric và bộ nhớ sử dụng.
- **Dùng chung một timeout cho mọi dependency:** mỗi dịch vụ có SLA và đặc tính phản hồi khác nhau.
- **Fallback che giấu lỗi nghiệp vụ:** có thể khiến người gọi nhận kết quả sai mà không biết trạng thái thực tế.
- **Không kiểm tra hỗ trợ reactive:** có thể làm ứng dụng không khởi tạo được factory hoặc buộc phải chặn luồng.
- **Chuyển YAML nguyên trạng sang implementation khác:** thuộc tính có thể bị bỏ qua hoặc không có cùng ý nghĩa.
- **Không cập nhật dashboard sau khi đổi thư viện:** metric không còn được xuất ra như trước, khiến cảnh báo mất hiệu lực.

Hãy giữ tầng gọi ở mức abstraction mà Spring Cloud CircuitBreaker cung cấp, định danh dependency ổn định và mô tả chính sách ở cấp ứng dụng. Khi cần cấu hình chi tiết như sliding window, probe, TimeLimiter hay Bulkhead, hãy xem đó là khả năng của implementation cụ thể và xác minh lại khi thay đổi thư viện hoặc phiên bản.
