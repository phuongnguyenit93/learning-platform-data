# Chọn mặc định và cấu hình riêng qua BulkheadProvider

Bulkhead giới hạn số công việc được phép chạy đồng thời để một dependency hoặc một nhóm request không chiếm hết tài nguyên của ứng dụng. Trong Spring Cloud CircuitBreaker với Resilience4j, BulkheadProvider là thành phần cung cấp cấu hình Bulkhead cho các lời gọi được bảo vệ. Ta có thể chọn kiểu Bulkhead mặc định cho ứng dụng, khai báo một chính sách nền cho các ID và ghi đè bằng cấu hình riêng cho từng dependency.

Bài này tập trung vào cách chọn giữa SemaphoreBulkhead và FixedThreadPoolBulkhead, cách cấu hình bằng Resilience4jBulkheadProvider, cách liên kết cấu hình với ID được tạo bởi Circuit Breaker factory và cách xác minh giới hạn đồng thời đang hoạt động như mong muốn.

## 1. BulkheadProvider làm nhiệm vụ gì?

Spring Cloud CircuitBreaker cung cấp abstraction để tạo Circuit Breaker và áp dụng các cơ chế bảo vệ đi kèm. Khi dùng Resilience4j, Resilience4jBulkheadProvider cung cấp cấu hình Bulkhead cho các lời gọi. Ta có thể tùy chỉnh provider bằng bean Customizer<Resilience4jBulkheadProvider>.

Hai phương thức thường dùng là:

- **configureDefault(...)**: định nghĩa cấu hình Bulkhead nền cho các ID chưa có cấu hình riêng.
- **configure(..., "id")**: đăng ký cấu hình cho một hoặc nhiều ID cụ thể.

ID cần ổn định và phải khớp với ID truyền vào factory khi tạo Circuit Breaker. Ví dụ, cấu hình catalog-read chỉ áp dụng cho lời gọi được tạo bằng factory.create("catalog-read"). Nếu code gọi factory.create("catalog"), cấu hình catalog-read sẽ không được chọn.

Provider giúp gom chính sách Bulkhead vào một nơi để quản lý. Thay vì tự tạo semaphore hoặc thread pool ở từng service, ứng dụng có thể khai báo giới hạn theo dependency và để Spring Cloud CircuitBreaker áp dụng khi lời gọi đi qua factory tương ứng.

## 2. Chọn kiểu Bulkhead mặc định

Resilience4j hỗ trợ hai kiểu Bulkhead chính:

| Kiểu | Cách bảo vệ | Phù hợp khi |
|---|---|---|
| SemaphoreBulkhead | Dùng semaphore để giới hạn số lời gọi đồng thời; không tạo thread pool riêng | Lời gọi non-blocking hoặc ứng dụng muốn giữ việc thực thi trên thread hiện tại |
| FixedThreadPoolBulkhead | Chạy tác vụ trong thread pool riêng với số thread và hàng đợi có giới hạn | Cần cô lập tác vụ đồng bộ/blocking khỏi tài nguyên xử lý request |

Spring Cloud CircuitBreaker Resilience4j mặc định sử dụng FixedThreadPoolBulkhead. Có thể chọn SemaphoreBulkhead làm kiểu mặc định bằng thuộc tính:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Khi thuộc tính này được bật, provider sử dụng semaphore làm kiểu Bulkhead mặc định. Nếu không bật, cơ chế mặc định là thread-pool Bulkhead.

Không có một lựa chọn tốt cho mọi ứng dụng. Semaphore giới hạn concurrency mà không chuyển công việc sang pool khác, phù hợp với pipeline reactive hoặc lời gọi đã non-blocking. Thread-pool Bulkhead cô lập công việc blocking nhưng tạo thêm thread và hàng đợi; cần đặt kích thước pool và queue cẩn thận.

Với WebFlux, không nên đưa I/O non-blocking vào một thread-pool Bulkhead chỉ vì muốn có giới hạn concurrency. Semaphore thường phù hợp hơn để giới hạn số subscription đồng thời mà vẫn giữ mô hình reactive. Với một SDK đồng bộ hoặc tác vụ blocking, thread-pool Bulkhead có thể cô lập công việc, nhưng client vẫn cần timeout và pool phải có giới hạn.

## 3. Cấu hình mặc định bằng configureDefault

Có thể khai báo một bean để đặt cấu hình nền cho mọi ID chưa được cấu hình riêng:

~~~java
import java.time.Duration;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4jBulkheadConfigurationBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4jBulkheadProvider;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;

@Configuration
public class BulkheadConfiguration {

    @Bean
    Customizer<Resilience4jBulkheadProvider> defaultBulkheadProvider() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(BulkheadConfig.custom()
                    .maxConcurrentCalls(25)
                    .maxWaitDuration(Duration.ZERO)
                    .build())
                .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                    .coreThreadPoolSize(4)
                    .maxThreadPoolSize(8)
                    .queueCapacity(20)
                    .keepAliveDuration(Duration.ofSeconds(20))
                    .build())
        );
    }
}
~~~

Cấu hình nền trên minh họa giới hạn 25 lời gọi đồng thời cho semaphore và thread pool có 4 thread lõi, tối đa 8 thread cùng hàng đợi 20 phần tử. Giá trị này chỉ là ví dụ. Khi ứng dụng chọn SemaphoreBulkhead, cấu hình bulkheadConfig được dùng; khi chọn FixedThreadPoolBulkhead, cấu hình threadPoolBulkheadConfig được dùng.

maxWaitDuration(Duration.ZERO) có nghĩa lời gọi không chờ để lấy slot semaphore khi đã đủ concurrency; nó bị từ chối ngay. Với thread-pool Bulkhead, queueCapacity xác định số tác vụ có thể đợi trong hàng đợi. Hàng đợi càng lớn thì càng có nguy cơ làm tăng latency và giữ request quá lâu. Đừng xem queue là cách tăng năng lực xử lý: nó chỉ giữ công việc chờ cho đến khi thread rảnh.

Nếu ứng dụng chỉ dùng một kiểu Bulkhead, vẫn nên cấu hình đúng phần tương ứng và hiểu rõ kiểu đang được chọn. Việc đặt cả hai cấu hình trong builder giúp có thể chuyển kiểu mặc định bằng property mà không phải viết lại toàn bộ chính sách.

## 4. Cấu hình riêng theo ID bằng configure

Khi một dependency cần giới hạn concurrency khác với phần còn lại của ứng dụng, dùng configure với ID cụ thể.

Ví dụ, Catalog Service chịu được nhiều request đọc đồng thời, còn Payment Service cần giới hạn chặt hơn vì mỗi request tiêu tốn kết nối và có tác động tới giao dịch:

~~~java
@Bean
Customizer<Resilience4jBulkheadProvider> perDependencyBulkheads() {
    return provider -> {
        provider.configure(builder -> builder
            .bulkheadConfig(BulkheadConfig.custom()
                .maxConcurrentCalls(40)
                .maxWaitDuration(Duration.ZERO)
                .build())
            .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(6)
                .maxThreadPoolSize(10)
                .queueCapacity(30)
                .keepAliveDuration(Duration.ofSeconds(20))
                .build()),
            "catalog-read");

        provider.configure(builder -> builder
            .bulkheadConfig(BulkheadConfig.custom()
                .maxConcurrentCalls(8)
                .maxWaitDuration(Duration.ZERO)
                .build())
            .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(2)
                .maxThreadPoolSize(4)
                .queueCapacity(4)
                .keepAliveDuration(Duration.ofSeconds(20))
                .build()),
            "payment-authorize");
    };
}
~~~

Trong ví dụ:

- catalog-read được phép tối đa 40 lời gọi đồng thời với SemaphoreBulkhead; nếu chọn ThreadPoolBulkhead thì dùng pool và queue riêng của ID này.
- payment-authorize chỉ cho phép tối đa 8 lời gọi đồng thời với SemaphoreBulkhead, hoặc dùng pool nhỏ hơn khi chọn ThreadPoolBulkhead.
- Lời gọi không có cấu hình riêng tiếp tục dùng cấu hình từ configureDefault.

Các giá trị cần được tính dựa trên năng lực thực tế của dependency và ứng dụng. Ví dụ, nếu có 5 instance ứng dụng và mỗi instance cho phép 40 lời gọi đồng thời tới Catalog, tổng số lời gọi có thể lên tới khoảng 200. Cần tính concurrency toàn hệ thống, không chỉ giới hạn trên một instance.

Không đặt cùng một ID ở nhiều bean customizer với các giới hạn khác nhau. Khi nhiều cấu hình cùng tác động lên một ID, việc xác định cấu hình cuối cùng trở nên khó hiểu và phụ thuộc thứ tự áp dụng. Hãy duy trì một nơi sở hữu chính sách của mỗi ID.

## 5. Liên kết ID với CircuitBreakerFactory

Cấu hình của provider được chọn theo ID mà ứng dụng truyền vào factory. Ví dụ:

~~~java
@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> catalogClient.fetch(productId)
        );
    }
}
~~~

Ở đây, ID catalog-read được dùng để tìm cấu hình Circuit Breaker và Bulkhead tương ứng. Lời gọi đi qua factory sẽ được áp dụng cơ chế Bulkhead do provider cung cấp cùng các cấu hình resilience khác.

Nếu ID trong provider là catalog-read nhưng service tạo catalog-service, cấu hình riêng sẽ không khớp. Nên khai báo ID dưới dạng hằng số dùng chung:

~~~java
public final class ResilienceIds {
    private ResilienceIds() {}

    public static final String CATALOG_READ = "catalog-read";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";
}
~~~

Dùng ResilienceIds.CATALOG_READ ở cả nơi cấu hình và nơi gọi factory để tránh sai chính tả.

## 6. Cấu hình mặc định và riêng phối hợp như thế nào?

Một chính sách thường có ba lớp:

1. **Kiểu Bulkhead mặc định:** chọn Semaphore hay FixedThreadPool thông qua cấu hình Spring Cloud CircuitBreaker.
2. **Cấu hình nền:** configureDefault đặt giới hạn chung cho ID chưa được khai báo riêng.
3. **Cấu hình theo ID:** configure đặt giới hạn khác cho dependency cụ thể.

Ví dụ, ứng dụng chọn SemaphoreBulkhead mặc định và đặt concurrency chung là 25. ID catalog-read được tăng lên 40, còn payment-authorize giảm xuống 8. Các ID khác dùng giới hạn nền.

Không nên hiểu configureDefault là cấu hình sẽ cộng thêm vào mọi cấu hình riêng. Nó cung cấp cấu hình khi không có cấu hình theo ID. Cấu hình riêng là một chính sách độc lập cho ID tương ứng.

Cũng cần phân biệt hai loại mặc định:

- enableSemaphoreDefaultBulkhead quyết định kiểu Bulkhead mặc định mà Spring Cloud CircuitBreaker sử dụng.
- configureDefault quyết định các tham số Bulkhead mặc định như số lời gọi đồng thời, thời gian chờ hoặc kích thước pool/queue.

Hai cấu hình giải quyết hai câu hỏi khác nhau: dùng cơ chế nào và cơ chế đó có giới hạn ra sao.

## 7. Chọn thông số Bulkhead theo năng lực hệ thống

Không nên đặt concurrency chỉ dựa trên số request tối đa mà API gateway cho phép. Hãy xem xét:

- **Năng lực dependency:** số request đồng thời mà dịch vụ đích có thể xử lý ổn định.
- **Latency:** thời gian trung bình và p95/p99 của lời gọi.
- **Tài nguyên phía gọi:** thread, connection pool, heap, event loop và CPU.
- **Số instance:** giới hạn concurrency nhân với số instance tạo ra tổng tải tới dependency.
- **Mức độ quan trọng:** dependency quan trọng có thể cần một pool riêng để tránh bị các luồng ít quan trọng chiếm tài nguyên.
- **Ngân sách thời gian:** nếu queue chờ lâu hơn deadline request, queue không giúp cải thiện trải nghiệm.

Một cách ước lượng sơ bộ số lời gọi đồng thời là dùng định luật Little:

~~~text
Concurrency trung bình ≈ Throughput × Latency
~~~

Nếu một dependency nhận 100 request/giây và mỗi request mất trung bình 0,2 giây, số lời gọi đang chạy trung bình xấp xỉ 20. Giới hạn thực tế cần có headroom hợp lý, nhưng cũng phải nằm trong khả năng chịu tải của dependency.

Với ThreadPoolBulkhead, cần chọn coreThreadPoolSize, maxThreadPoolSize, queueCapacity và keepAliveDuration dựa trên tính chất tác vụ. Pool quá lớn có thể tạo quá nhiều thread; queue quá lớn làm tăng thời gian chờ; queue bằng 0 hoặc rất nhỏ giúp fail fast nhưng có thể từ chối nhiều request khi có đợt tăng tải ngắn.

Với SemaphoreBulkhead, maxConcurrentCalls giới hạn số lời gọi đồng thời. maxWaitDuration quyết định thời gian chờ slot. Nếu request có deadline ngắn, chờ slot lâu có thể khiến phần thời gian còn lại không đủ cho dependency xử lý. Đặt Duration.ZERO để từ chối ngay khi đầy hoặc một khoảng chờ ngắn phù hợp với ngân sách thời gian.

## 8. Bulkhead và Circuit Breaker phối hợp

Bulkhead và Circuit Breaker bảo vệ hệ thống theo hai cách khác nhau:

| Cơ chế | Câu hỏi nó trả lời | Hành động |
|---|---|---|
| Bulkhead | Có còn slot tài nguyên để thực hiện lời gọi không? | Cho phép, chờ có giới hạn hoặc từ chối |
| Circuit Breaker | Dependency có đang có tỷ lệ lỗi hoặc chậm vượt ngưỡng không? | CLOSED cho gọi, OPEN từ chối, HALF_OPEN cho phép thăm dò |

Bulkhead có thể từ chối lời gọi dù dependency vẫn khỏe, vì ứng dụng chủ động giới hạn concurrency. Circuit Breaker có thể OPEN dù Bulkhead còn slot, vì dependency đang liên tục lỗi hoặc chậm. Khi phối hợp, hãy theo dõi riêng Bulkhead rejection và Circuit Breaker not permitted.

Ví dụ, catalog-read có 40 slot Bulkhead. Dependency bắt đầu timeout hàng loạt và Circuit Breaker chuyển OPEN. Khi đó, request mới bị breaker từ chối trước khi tạo thêm tải tới dependency. Trong một tình huống khác, breaker vẫn CLOSED nhưng 40 slot đã dùng hết; Bulkhead từ chối lời gọi mới để bảo vệ tài nguyên của ứng dụng.

Không dùng Bulkhead thay cho timeout. Một lời gọi có thể giữ slot rất lâu nếu dependency không phản hồi. Cần timeout để giải phóng công việc theo thời hạn và để Circuit Breaker nhận được kết quả.

## 9. Semaphore hay ThreadPool cho reactive và blocking?

Chọn loại Bulkhead theo mô hình thực thi:

| Mô hình lời gọi | Lựa chọn thường phù hợp | Lưu ý |
|---|---|---|
| WebClient và Reactor non-blocking | SemaphoreBulkhead | Giới hạn số subscription mà không chuyển sang thread pool riêng |
| HTTP client đồng bộ/blocking | ThreadPoolBulkhead hoặc SemaphoreBulkhead có kiểm soát | Cô lập blocking I/O và cấu hình timeout client |
| Tác vụ CPU-bound | Pool có giới hạn phù hợp với CPU | Không tạo quá nhiều thread hoặc queue |
| Dependency có quota concurrency thấp | SemaphoreBulkhead | Giới hạn trực tiếp số lời gọi đồng thời |
| Cần cô lập một tác vụ legacy blocking | ThreadPoolBulkhead | Pool và queue riêng, có giới hạn rõ |

Với reactive, việc chọn SemaphoreBulkhead không có nghĩa request được chạy đồng bộ trên event loop; nó chỉ giới hạn số lời gọi đang được bảo vệ. Tránh gọi block() bên trong pipeline để không làm nghẽn event loop.

ThreadPoolBulkhead hữu ích cho tác vụ blocking, nhưng cần nhớ rằng nó tạo thêm thread và hàng đợi. Nếu dùng với một API reactive, hãy xác nhận rõ adapter và cách tích hợp của phiên bản Spring Cloud CircuitBreaker đang dùng. Không nên chuyển mọi Publisher sang thread pool chỉ để có giới hạn concurrency.

## 10. Cấu hình bằng application.yml và provider

Spring Cloud CircuitBreaker Resilience4j hỗ trợ cấu hình instance bằng properties trong application.yml. Có thể khai báo các giới hạn cho từng ID trong file cấu hình:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      catalog-read:
        maxConcurrentCalls: 40
        maxWaitDuration: 0
      payment-authorize:
        maxConcurrentCalls: 8
        maxWaitDuration: 0

  thread-pool-bulkhead:
    instances:
      catalog-read:
        coreThreadPoolSize: 6
        maxThreadPoolSize: 10
        queueCapacity: 30
      payment-authorize:
        coreThreadPoolSize: 2
        maxThreadPoolSize: 4
        queueCapacity: 4
~~~

Cấu hình này minh họa việc bật SemaphoreBulkhead làm mặc định và khai báo thông số instance. Khi chọn SemaphoreBulkhead, phần resilience4j.bulkhead là phần liên quan; khi dùng FixedThreadPoolBulkhead, phần resilience4j.thread-pool-bulkhead được dùng. Cần kiểm tra cấu hình được bind và provider thực tế theo phiên bản thư viện trong dự án.

Có thể chọn quản lý bằng properties hoặc Java Customizer. Nếu cùng một ID được cấu hình ở cả hai nơi, cần hiểu quy tắc ưu tiên của phiên bản Spring Cloud CircuitBreaker/Resilience4j đang dùng và xác minh cấu hình thực tế. Tránh khai báo cùng một giới hạn ở nhiều nơi mà không có chủ đích.

## 11. Xử lý khi Bulkhead đầy

Khi không còn slot, Resilience4j có thể từ chối lời gọi bằng exception phù hợp, chẳng hạn BulkheadFullException với SemaphoreBulkhead hoặc lỗi từ ThreadPoolBulkhead khi queue/thread pool không nhận thêm tác vụ.

Ứng dụng cần ánh xạ tình trạng này thành phản hồi có ý nghĩa:

- Trả trạng thái quá tải hoặc thử lại sau nếu API cho phép.
- Không retry ngay lập tức tại cùng tầng, vì slot vẫn đang đầy.
- Không ghi nhận Bulkhead rejection như lỗi của dependency nếu lời gọi chưa tới dependency.
- Ghi metric riêng về số lần từ chối và mức sử dụng slot.
- Cân nhắc giảm tải hoặc điều chỉnh giới hạn sau khi xem xét năng lực thực tế.

Ví dụ xử lý exception ở tầng API:

~~~java
@ExceptionHandler(BulkheadFullException.class)
ResponseEntity<ApiError> handleBulkheadFull(BulkheadFullException error) {
    ApiError body = new ApiError(
        "DEPENDENCY_CAPACITY_LIMIT",
        "Hệ thống đang bận, vui lòng thử lại sau"
    );

    return ResponseEntity.status(503).body(body);
}
~~~

Status HTTP trả cho caller phải theo hợp đồng API. Nếu đây là giới hạn cục bộ của ứng dụng, 503 có thể phù hợp để báo dịch vụ hiện không thể nhận thêm công việc; một số API có thể dùng 429 nếu giới hạn áp dụng cho caller cụ thể. Không trả 200 với dữ liệu giả chỉ để che việc Bulkhead từ chối.

## 12. Kiểm tra cấu hình BulkheadProvider

Sau khi khai báo provider và ID, kiểm tra theo từng bước:

1. Ứng dụng khởi động và bean Customizer<Resilience4jBulkheadProvider> được nạp.
2. Kiểu Bulkhead mặc định đúng với thuộc tính enableSemaphoreDefaultBulkhead.
3. ID trong configure khớp ID truyền vào CircuitBreakerFactory.create(...).
4. ID chưa có cấu hình riêng dùng cấu hình từ configureDefault.
5. ID có cấu hình riêng nhận đúng concurrency hoặc thread-pool size đã đặt.
6. Khi đạt giới hạn, lời gọi mới bị từ chối hoặc chờ đúng thời gian cấu hình.
7. Khi tác vụ kết thúc hoặc timeout, slot được giải phóng và lời gọi tiếp theo có thể chạy.
8. Metric Bulkhead và Circuit Breaker được theo dõi riêng.

Một kiểm thử concurrency có thể dùng latch hoặc barrier để giữ các tác vụ đang chạy, sau đó gửi thêm lời gọi vượt giới hạn và xác nhận bị từ chối. Không cần chỉ dựa vào thời gian sleep vì điều đó dễ gây flaky test. Hãy giải phóng latch trong finally để test không giữ thread khi assertion thất bại.

Các metric cần theo dõi gồm số lời gọi đồng thời, số lần được chấp nhận, số lần bị từ chối, số tác vụ đang chờ trong queue và độ trễ chờ. Đối chiếu metric với tải thực tế để biết giới hạn có quá thấp hoặc quá cao.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cấu hình riêng không có tác dụng | ID trong provider khác ID trong factory | Dùng hằng số ID chung và kiểm tra tên |
| Mọi dependency dùng cùng giới hạn | Chỉ cấu hình mặc định, chưa khai báo configure | Thêm cấu hình theo ID cho dependency cần chính sách riêng |
| Bulkhead từ chối quá nhiều request | Concurrency thấp, queue nhỏ hoặc lưu lượng tăng đột biến | Đo latency và capacity trước khi điều chỉnh |
| Request chờ quá lâu dù Bulkhead giới hạn | maxWaitDuration hoặc queue quá lớn | Giảm thời gian chờ và đồng bộ với deadline |
| Thread pool tạo quá nhiều thread | maxThreadPoolSize đặt quá cao hoặc nhiều instance | Tính tổng số thread trên tất cả instance |
| Reactive pipeline bị nghẽn | Dùng blocking I/O hoặc block event loop | Giữ non-blocking hoặc cô lập tác vụ blocking đúng cách |
| Không phân biệt được lỗi Bulkhead và breaker | Gộp chung metric hoặc exception handler | Theo dõi Bulkhead rejection và Circuit Breaker not permitted riêng |

## Kết luận

Dùng BulkheadProvider để quản lý chính sách giới hạn tài nguyên theo ID. Chọn SemaphoreBulkhead cho lời gọi non-blocking cần giới hạn concurrency mà không tạo pool riêng; chọn FixedThreadPoolBulkhead khi cần cô lập tác vụ blocking trong pool và queue có giới hạn. Dùng configureDefault làm cấu hình nền, configure cho dependency có yêu cầu riêng và giữ ID nhất quán với factory. Kết hợp Bulkhead với timeout và Circuit Breaker, đo concurrency trên toàn bộ số instance và theo dõi rejection riêng để hệ thống fail fast khi hết năng lực mà không tạo thêm lỗi dây chuyền.

