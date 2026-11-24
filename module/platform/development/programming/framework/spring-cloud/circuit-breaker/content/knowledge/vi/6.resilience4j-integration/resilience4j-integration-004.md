# Cấu hình riêng theo ID bằng configure

Trong Spring Cloud CircuitBreaker, factory tạo Circuit Breaker theo một ID. ID này đại diện cho một dependency hoặc một luồng gọi cụ thể, chẳng hạn `catalog-read`, `payment-authorize` hay `recommendation-read`. Khi các dependency có mức độ quan trọng, độ trễ và cách xử lý lỗi khác nhau, ta có thể dùng phương thức `configure` để gắn cấu hình riêng cho từng ID.

Cách làm này giúp ứng dụng dùng cùng API Circuit Breaker nhưng áp dụng chính sách phù hợp cho từng lời gọi. Ví dụ, dịch vụ danh mục có thể dùng timeout ngắn và fallback từ cache; cổng thanh toán cần trả lỗi rõ ràng nếu không thể xác nhận giao dịch; dịch vụ gợi ý có thể chấp nhận bỏ qua dữ liệu bổ sung. Bài học tập trung vào cách khai báo cấu hình theo ID, liên kết ID với lời gọi và kiểm tra cấu hình đã được áp dụng.

## 1. ID định danh cấu hình nào?

Khi gọi `factory.create("catalog-read")`, chuỗi `catalog-read` là ID của Circuit Breaker. Factory sử dụng ID để tìm cấu hình đã đăng ký và tạo hoặc lấy Circuit Breaker tương ứng. Vì vậy, ID truyền vào `create(...)` phải khớp chính xác với ID truyền vào `configure(...)`.

Một ứng dụng có thể tổ chức ID theo dependency và mục đích gọi:

| ID | Dependency và luồng gọi | Chính sách minh họa |
|---|---|---|
| `catalog-read` | Đọc thông tin danh mục sản phẩm | Timeout ngắn, mở breaker khi lỗi hoặc chậm, thử cache khi an toàn |
| `payment-authorize` | Yêu cầu cổng thanh toán xác nhận giao dịch | Giới hạn thời gian, fail fast khi dependency suy giảm, không giả lập kết quả thành công |
| `recommendation-read` | Lấy nội dung gợi ý | Có thể bỏ phần gợi ý nếu dependency tạm thời không khả dụng |

ID nên ổn định và có số lượng hữu hạn. Không tạo ID theo từng request, mã người dùng hoặc mã sản phẩm. Nếu mỗi request có một ID mới, ứng dụng có thể tạo ra rất nhiều breaker với cửa sổ thống kê ít mẫu, khó quan sát và khó quản lý.

Nếu hai lời gọi dùng chung một ID, chúng dùng chung chính sách và trạng thái breaker. Điều này chỉ hợp lý khi chúng thực sự cùng dependency, cùng đặc tính và cùng cách xử lý sự cố. Nếu một dependency có hai luồng gọi với ngân sách thời gian hoặc yêu cầu nghiệp vụ khác nhau, hãy cân nhắc dùng hai ID riêng.

## 2. Phân biệt configure và configureDefault

Spring Cloud CircuitBreaker với Resilience4j cung cấp hai cách cấu hình chính:

- `configure(..., "id")` đăng ký cấu hình cho một hoặc nhiều ID cụ thể.
- `configureDefault(...)` định nghĩa cấu hình mặc định được dùng khi ID không có cấu hình riêng.

Ví dụ, ứng dụng có thể đặt timeout mặc định ba giây cho các lời gọi, sau đó cấu hình riêng `catalog-read` với timeout hai giây và cửa sổ quan sát riêng. Những ID khác vẫn dùng cấu hình mặc định.

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerCustomizer() {
    return factory -> {
        // Cấu hình nền cho các ID chưa được chỉ định riêng.
        factory.configureDefault(id -> new Resilience4JConfigBuilder(id)
            .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
            .timeLimiterConfig(TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(3))
                .build())
            .build());

        // Cấu hình riêng cho lời gọi đọc danh mục.
        factory.configure(builder -> builder
            .circuitBreakerConfig(CircuitBreakerConfig.custom()
                .slidingWindowType(SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .build())
            .timeLimiterConfig(TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .build()),
            "catalog-read");
    };
}
```

Trong ví dụ, `configureDefault` cung cấp chính sách nền. Lời gọi có ID `catalog-read` nhận cấu hình đã đăng ký riêng. Các ID khác chưa có cấu hình riêng sẽ dùng mặc định. Nếu truyền nhiều ID vào tham số cuối của `configure`, tất cả các ID đó dùng chung cấu hình được khai báo trong lambda.

Để mã dễ bảo trì, nên gom cấu hình liên quan vào một bean `Customizer` hoặc chia thành các bean theo nhóm dependency. Tránh khai báo nhiều bean cùng cấu hình một ID theo các chính sách khác nhau vì người đọc khó xác định cấu hình cuối cùng được áp dụng.

## 3. Tạo Customizer cho Resilience4J factory

Với lời gọi đồng bộ, Spring Cloud CircuitBreaker cung cấp `Resilience4JCircuitBreakerFactory`. Ta khai báo một bean `Customizer<Resilience4JCircuitBreakerFactory>`; Spring sẽ áp dụng customizer lên factory được auto-configuration tạo ra.

Ví dụ dưới đây tạo cấu hình riêng cho hai dependency. Danh mục là dữ liệu có thể lấy từ cache; thanh toán là thao tác bắt buộc và phải fail fast nếu cổng thanh toán không phản hồi.

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> perIdCircuitBreakerConfig() {
        return factory -> {
            factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowType(SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .slowCallDurationThreshold(Duration.ofSeconds(2))
                    .slowCallRateThreshold(50)
                    .waitDurationInOpenState(Duration.ofSeconds(15))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .build()),
                "catalog-read");

            factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowType(SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(10)
                    .minimumNumberOfCalls(5)
                    .failureRateThreshold(40)
                    .waitDurationInOpenState(Duration.ofSeconds(30))
                    .permittedNumberOfCallsInHalfOpenState(2)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(5))
                    .build()),
                "payment-authorize");
        };
    }
}
```

Các ngưỡng trong ví dụ chỉ để minh họa cách cấu hình theo ID. Với `catalog-read`, cửa sổ có 20 lời gọi và cần tối thiểu 10 mẫu trước khi đánh giá tỷ lệ lỗi; lời gọi từ hai giây trở lên được xem là chậm. Với `payment-authorize`, cấu hình dùng cửa sổ và ngưỡng khác để thể hiện một chính sách độc lập. Giá trị thực tế phải dựa trên latency bình thường, lưu lượng, SLO và ngân sách thời gian của request đầu cuối.

Cấu hình Circuit Breaker và TimeLimiter có nhiệm vụ khác nhau:

- `CircuitBreakerConfig` kiểm soát cửa sổ quan sát, ngưỡng lỗi, ngưỡng lời gọi chậm và chuyển trạng thái CLOSED/OPEN/HALF_OPEN.
- `TimeLimiterConfig` giới hạn thời gian chờ đối với lời gọi được tích hợp qua cơ chế TimeLimiter.
- Timeout không thay thế Circuit Breaker: timeout tạo ra kết quả lỗi hoặc kết thúc chờ; Circuit Breaker dùng kết quả đã quan sát để quyết định có tiếp tục cho phép lời gọi hay không.

Với lời gọi đồng bộ có thể bị chặn, cần xác nhận cách client xử lý interrupt hoặc hủy tác vụ. Hết thời gian chờ không đảm bảo mọi I/O nền đã dừng ngay lập tức. Cấu hình timeout phải đi cùng timeout của HTTP client và giới hạn tài nguyên phù hợp.

## 4. Dùng đúng ID khi gọi dependency

Sau khi đăng ký cấu hình, truyền đúng ID vào factory ở nơi thực hiện lời gọi. Ví dụ:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ProductClient productClient;
    private final ProductCache productCache;

    public ProductQueryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ProductClient productClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.productClient = productClient;
        this.productCache = productCache;
    }

    public ProductDetails findDetails(String productId) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> productClient.fetchDetails(productId),
            cause -> productCache.findUsable(productId)
                .orElseThrow(() ->
                    new CatalogUnavailableException(productId, cause))
        );
    }
}
```

Ở đây, `create("catalog-read")` khớp với ID trong `configure`. Khi dependency lỗi hoặc Circuit Breaker từ chối lời gọi vì đang OPEN, hàm fallback thử lấy dữ liệu cache. Nếu cache không có dữ liệu hợp lệ, fallback ném `CatalogUnavailableException` để caller nhận biết dịch vụ không khả dụng.

Không nên coi fallback là một cách biến mọi lỗi thành thành công. Nếu client trả về lỗi nghiệp vụ như sản phẩm không tồn tại, hãy phân loại lỗi đó riêng và bảo đảm nó không bị đổi thành dữ liệu cache sai. Với thao tác thanh toán, fallback không được trả kết quả “đã thanh toán” khi chưa có xác nhận từ cổng thanh toán.

Ví dụ lời gọi bắt buộc có thể dùng ID riêng:

```java
public PaymentResult authorize(PaymentCommand command) {
    return circuitBreakerFactory.create("payment-authorize").run(
        () -> paymentClient.authorize(command),
        cause -> {
            throw new PaymentUnavailableException(
                "Không thể xác nhận thanh toán lúc này", cause);
        }
    );
}
```

Khi breaker `payment-authorize` OPEN, lời gọi mới bị từ chối nhanh. Ứng dụng trả lỗi phù hợp với hợp đồng API và trạng thái giao dịch cần được xử lý rõ ràng. Nếu kết quả giao dịch chưa xác định do timeout, hệ thống nên tra soát bằng transaction ID hoặc idempotency key trước khi thử lại; không suy diễn timeout đồng nghĩa với giao dịch thất bại hay thành công.

## 5. Phân loại exception riêng cho từng ID

Một trong những lý do nên cấu hình theo ID là mỗi dependency có nhóm lỗi cần tính vào failure rate khác nhau. Resilience4j mặc định xem exception phát sinh trong lời gọi được bảo vệ là lỗi. Có thể điều chỉnh bằng `ignoreExceptions` hoặc `recordExceptions` trong `CircuitBreakerConfig`.

Ví dụ, lỗi không tìm thấy sản phẩm là kết quả nghiệp vụ hợp lệ, không nên làm breaker của danh mục mở. Có thể thêm chính sách bỏ qua exception đó:

```java
CircuitBreakerConfig catalogConfig = CircuitBreakerConfig.custom()
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .ignoreExceptions(ProductNotFoundException.class)
    .build();
```

Khi dùng `recordExceptions`, cần nhớ các exception không nằm trong danh sách record có thể được xem là thành công, trừ khi đồng thời được bỏ qua hoặc được phân loại bằng predicate khác. Vì vậy, chỉ dùng danh sách record khi đã xác định đầy đủ các loại lỗi cần tính. Nếu muốn mặc định tính mọi exception là lỗi và chỉ loại trừ một số kết quả nghiệp vụ, `ignoreExceptions` thường dễ đọc hơn.

Một số nguyên tắc phân loại:

| Loại lỗi | Xử lý thống kê thường phù hợp |
|---|---|
| Timeout, lỗi kết nối, HTTP 5xx từ dependency | Tính là lỗi của dependency |
| Lời gọi chậm vượt ngưỡng | Tính vào slow call rate |
| Không tìm thấy dữ liệu theo nghiệp vụ | Bỏ qua nếu đó là kết quả bình thường của API |
| Request không hợp lệ hoặc thiếu quyền | Xử lý tại tầng validation/bảo mật; không tính nhầm là sự cố dependency |
| Lỗi lập trình như NullPointerException | Điều tra như lỗi ứng dụng; không che bằng fallback chung |

Không nên bỏ qua mọi exception chỉ để breaker ít khi OPEN. Nếu timeout và lỗi kết nối bị bỏ qua, breaker sẽ không phản ánh đúng tình trạng dependency.

## 6. Cấu hình nhiều ID và tổ chức mã

Có thể truyền nhiều ID vào một lời gọi `configure` khi chúng thực sự dùng cùng một chính sách:

```java
factory.configure(builder -> builder
    .circuitBreakerConfig(CircuitBreakerConfig.custom()
        .slidingWindowSize(30)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .build()),
    "customer-read",
    "address-read");
```

Trong ví dụ này, `customer-read` và `address-read` có cùng cửa sổ, ngưỡng lỗi và chính sách mặc định. Nếu sau này một dependency cần timeout hoặc ngưỡng khác, hãy tách nó thành một cấu hình `configure` riêng. Không gom ID chỉ vì chúng được gọi từ cùng một service; điều quan trọng là đặc tính dependency và mục tiêu bảo vệ.

Một cách tổ chức dễ theo dõi là:

- Dùng một hằng số hoặc enum cho các ID để tránh sai chính tả giữa cấu hình và nơi gọi.
- Đặt tên ID theo dependency và loại thao tác, không theo tên controller hoặc người dùng.
- Để mỗi ID có một nơi định nghĩa chính sách rõ ràng.
- Chỉ chia sẻ cấu hình giữa các ID khi các tham số thực sự giống nhau.
- Ghi lại lý do chọn timeout, cửa sổ và ngưỡng để nhóm có thể điều chỉnh dựa trên metric.

Ví dụ khai báo hằng số:

```java
public final class CircuitBreakerIds {
    private CircuitBreakerIds() {}

    public static final String CATALOG_READ = "catalog-read";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";
    public static final String RECOMMENDATION_READ = "recommendation-read";
}
```

Khi đó, dùng `CircuitBreakerIds.CATALOG_READ` trong cả `configure` và `create`. Cách này giảm nguy cơ một ký tự khác nhau khiến cấu hình riêng không được sử dụng.

## 7. Cấu hình ID cho lời gọi reactive

Nếu ứng dụng sử dụng WebFlux và Reactor, dùng `ReactiveResilience4JCircuitBreakerFactory` để cấu hình ID cho luồng reactive. Cấu trúc `configure` tương tự, nhưng factory và API gọi là reactive:

```java
@Bean
Customizer<ReactiveResilience4JCircuitBreakerFactory> reactiveCircuitBreakerCustomizer() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .build())
        .timeLimiterConfig(TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .build()),
        "recommendation-read");
}
```

Khi sử dụng:

```java
public Mono<Recommendation> findRecommendation(String customerId) {
    Mono<Recommendation> request = webClient.get()
        .uri("/recommendations/{customerId}", customerId)
        .retrieve()
        .bodyToMono(Recommendation.class);

    return reactiveCircuitBreakerFactory
        .create("recommendation-read")
        .run(request, cause -> recommendationCache.find(customerId));
}
```

ID `recommendation-read` trong `create` phải trùng với ID đã cấu hình cho reactive factory. Fallback cũng trả về `Mono`; không gọi `block()` bên trong pipeline vì có thể làm nghẽn event loop. Cấu hình cho reactive factory và factory đồng bộ nên được đặt rõ ràng để tránh nhầm API hoặc cho rằng một customizer đã tự áp dụng cho cả hai.

## 8. Thứ tự ưu tiên giữa Java configure và application.yml

Spring Cloud CircuitBreaker cho phép cấu hình Resilience4j bằng Java Customizer hoặc bằng thuộc tính trong `application.yml`. Cấu hình properties có độ ưu tiên cao hơn Java Customizer. Nếu một ID được khai báo ở cả hai nơi, giá trị trong properties có thể ghi đè cấu hình Java tương ứng.

Ví dụ cấu hình theo instance trong YAML:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
  timelimiter:
    instances:
      catalog-read:
        timeoutDuration: 2s
```

Có thể dùng Java `configure` khi muốn khai báo chính sách bằng mã, cần logic dùng chung hoặc muốn tổ chức cấu hình theo bean. Có thể dùng properties khi muốn thay đổi ngưỡng mà không sửa mã và muốn tách cấu hình theo môi trường. Hãy chọn một nguồn quản lý rõ ràng cho mỗi ID. Nếu chủ ý dùng cả hai, ghi rõ giá trị nào được override và xác nhận bằng cấu hình thực tế khi chạy.

Không nên kết luận cấu hình Java không hoạt động chỉ vì metric khác dự kiến. Hãy kiểm tra xem cùng ID có được khai báo trong YAML hoặc profile khác không, và kiểm tra cấu hình theo môi trường đang được nạp.

## 9. Kiểm tra cấu hình theo ID

Sau khi khai báo customizer và sử dụng ID, hãy xác minh theo từng bước:

1. Kiểm tra bean `Customizer` được Spring khởi tạo; ứng dụng không có lỗi khi tạo factory.
2. Đối chiếu chuỗi ID trong `configure` với chuỗi ID truyền vào `create`.
3. Kiểm tra không có cấu hình properties cùng ID vô tình ghi đè Java.
4. Gọi dependency thành công và xác nhận request đi qua đúng client.
5. Mô phỏng lỗi hoặc timeout trong môi trường kiểm thử để xác nhận metric và trạng thái breaker thay đổi theo ngưỡng.
6. Gọi lại khi breaker OPEN để xác nhận lời gọi mới bị từ chối nhanh và fallback hoặc lỗi được trả theo thiết kế.
7. Chờ hết `waitDurationInOpenState`, kiểm tra HALF_OPEN cho phép số lời gọi thăm dò đã cấu hình và breaker phục hồi hoặc mở lại theo kết quả.

Một bài kiểm tra cấu hình không nên chỉ xác nhận ứng dụng khởi động. Hãy quan sát từng ID riêng. Nếu `catalog-read` đang OPEN, không nên suy ra `payment-authorize` cũng OPEN; mỗi ID được dùng để cô lập trạng thái và số liệu của luồng gọi tương ứng.

## 10. Lỗi thường gặp khi dùng configure

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cấu hình riêng không có tác dụng | ID trong `configure` khác ID trong `create` | Dùng hằng số chung và kiểm tra chính tả |
| Hai dependency cùng mở breaker | Vô tình dùng chung một ID | Tách ID nếu chúng cần trạng thái độc lập |
| Breaker không mở dù dependency liên tục lỗi | Exception bị bỏ qua hoặc cấu hình record không bao gồm lỗi cần tính | Kiểm tra phân loại exception và metric |
| Breaker mở quá nhanh | Cửa sổ quá nhỏ hoặc ngưỡng quá thấp so với lưu lượng thực | Đánh giá lại `minimumNumberOfCalls`, window size và threshold |
| Timeout xảy ra nhưng tác vụ nền vẫn chạy | Client hoặc tác vụ không hỗ trợ hủy khi timeout | Cấu hình timeout tại HTTP client, giới hạn tài nguyên và kiểm tra khả năng cancellation |
| Giá trị runtime khác Java Customizer | Properties hoặc profile đang override cùng ID | Kiểm tra `application.yml`, `application-*.yml` và cấu hình được nạp |
| Reactive pipeline bị nghẽn | Có thao tác blocking như `block()` trong fallback | Giữ fallback non-blocking và trả về `Mono`/`Flux` |

## Kết luận

Dùng `configure` khi một dependency hoặc luồng gọi cần chính sách Circuit Breaker riêng. Đặt ID ổn định, đăng ký cấu hình trên đúng factory, rồi truyền chính ID đó vào `create`. Dùng `configureDefault` làm chính sách nền cho các ID chưa có cấu hình riêng. Tách ID theo đặc tính dependency, phân loại exception đúng và kiểm tra cấu hình properties có override Java hay không. Nhờ vậy, từng lời gọi trong ứng dụng Spring Cloud có thể có cửa sổ quan sát, ngưỡng lỗi, timeout và cách fallback phù hợp với yêu cầu của nó.

