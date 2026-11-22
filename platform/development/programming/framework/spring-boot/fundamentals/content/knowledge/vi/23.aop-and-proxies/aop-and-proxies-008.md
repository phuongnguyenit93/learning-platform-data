# @Transactional, @Async, @Cacheable và điều kiện hạ tầng tương ứng

Trong Spring Boot, ba annotation `@Transactional`, `@Async` và `@Cacheable` thường xuất hiện ngay trên phương thức service. Chúng trông giống những chỉ dẫn đơn giản, nhưng thực tế mỗi annotation cần **hạ tầng riêng** để có hiệu lực:

- `@Transactional` cần bộ xử lý giao dịch và transaction manager phù hợp.
- `@Async` cần cơ chế xử lý bất đồng bộ được bật và một executor để thực thi công việc.
- `@Cacheable` cần cơ chế caching được bật và một cache manager để lưu, tìm kết quả.

Trong cấu hình proxy phổ biến của Spring, cả ba còn phụ thuộc vào **đường đi của lời gọi phương thức**. Annotation không tự thay đổi cách Java gọi phương thức; framework phải nhận diện và chặn lời gọi qua một Spring AOP proxy thích hợp.

Bài học tập trung vào điều kiện kích hoạt từng cơ chế, cách nhận biết khi hạ tầng chưa sẵn sàng và cách kết hợp chúng mà không nhầm lẫn ranh giới transaction, thread hoặc cache.

## 1. Annotation chỉ là metadata, không phải hạ tầng thực thi

Một phương thức có thể khai báo:

~~~java
@Transactional
public void placeOrder() {
    // ...
}
~~~

Nhưng khi JVM thực thi một lời gọi Java thông thường, nó không tự đọc `@Transactional` để mở transaction. Cần có một interceptor được Spring đăng ký, xác định phương thức có áp dụng transaction hay không và gọi transaction manager trước/sau phần code nghiệp vụ.

Cơ chế tương tự xảy ra với async và cache:

| Annotation | Advice/interceptor cần thực hiện | Thành phần hạ tầng cốt lõi |
|---|---|---|
| `@Transactional` | Mở hoặc tham gia transaction; commit/rollback theo kết quả | `PlatformTransactionManager` hoặc `ReactiveTransactionManager` |
| `@Async` | Đưa lời gọi tới executor để xử lý ngoài luồng gọi | `Executor` / `TaskExecutor`, async processing được bật |
| `@Cacheable` | Tìm key trong cache; gọi phương thức nếu miss; lưu kết quả theo chính sách | `CacheManager`, caching processing được bật |

Có thể hình dung:

~~~text
Bean A gọi Bean B
       |
       v
Spring proxy của B
       |
       +--> Advisor / interceptor tương ứng
       |      |
       |      +--> TransactionManager
       |      +--> Executor
       |      +--> CacheManager
       |
       v
Phương thức thật của B (target)
~~~

Một bean có thể được áp dụng nhiều advisor. Việc phương thức có annotation chỉ là một điều kiện; còn cần các bean hạ tầng, cấu hình kích hoạt và lời gọi phù hợp.

## 2. @Transactional: điều kiện để giao dịch được quản lý

`@Transactional` thuộc `org.springframework.transaction.annotation`. Nó mô tả ranh giới giao dịch và các thuộc tính như `propagation`, `isolation`, `readOnly`, `timeout` hay `rollbackFor`.

Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;

    public CheckoutService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void checkout(Order order) {
        orderRepository.save(order);
        // Những thao tác dữ liệu khác trong cùng transaction...
    }
}
~~~

Khi một bean khác gọi `checkoutService.checkout(order)` qua proxy, transaction interceptor có thể yêu cầu transaction manager bắt đầu hoặc tham gia giao dịch, chạy phương thức rồi commit/rollback theo cấu hình.

### Hạ tầng bắt buộc

Cần phân biệt các phần sau:

1. **Spring transaction infrastructure:** có các lớp transaction và bộ xử lý `@Transactional`.
2. **Transaction management được kích hoạt:** Spring đăng ký các advisor/interceptor cần thiết.
3. **Transaction manager:** thực hiện giao dịch thực tế cho tài nguyên, ví dụ JDBC, JPA hoặc R2DBC.
4. **Lời gọi qua proxy:** trong proxy mode, điểm vào được advised phải đi qua bean proxy.

Với cấu hình Spring thuần, có thể bật hỗ trợ annotation qua:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class TransactionConfiguration {
}
~~~

Trong ứng dụng Spring Boot, transaction auto-configuration thường đảm nhiệm việc bật hỗ trợ annotation khi các điều kiện phù hợp, chẳng hạn có transaction manager bean. Vì vậy không phải dự án Boot nào cũng phải tự khai báo `@EnableTransactionManagement`.

Nhưng **có `@Transactional` trên classpath không đồng nghĩa luôn có transaction manager**. Nếu ứng dụng không cấu hình tài nguyên giao dịch và không có bean manager phù hợp, Spring không thể tự suy ra cách commit dữ liệu.

### Các transaction manager thường gặp

| Công nghệ truy cập dữ liệu | Transaction manager ví dụ | Lưu ý |
|---|---|---|
| JDBC | `JdbcTransactionManager` / `DataSourceTransactionManager` | Quản lý JDBC transaction trên DataSource |
| JPA | `JpaTransactionManager` | Quản lý transaction qua JPA EntityManager |
| R2DBC | `R2dbcTransactionManager` | Reactive transaction dùng Reactor context |
| Tài nguyên hoặc hệ thống đặc biệt | Manager do integration cung cấp | Cần cấu hình theo tài nguyên thực tế |

Với JDBC/JPA, transaction imperative thường gắn với thread hiện tại. Với reactive transaction, trạng thái giao dịch được mang theo reactive context, không nên suy diễn theo `ThreadLocal` của luồng imperative.

Ví dụ dependency Gradle khi dùng JPA:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Dependency này cung cấp hạ tầng JPA/transaction liên quan. Ứng dụng vẫn phải cung cấp cấu hình datasource, driver và kết nối phù hợp để transaction thực sự hoạt động.

### Rollback mặc định và các thuộc tính thường dùng

~~~java
@Transactional(
        readOnly = true,
        timeout = 5
)
public Order getOrder(Long id) {
    return orderRepository.findById(id)
            .orElseThrow();
}
~~~

`readOnly = true` là một hint cho transaction manager và data access infrastructure; nó **không phải cơ chế bảo vệ tuyệt đối** khiến mọi thao tác ghi trong mọi database đều thất bại.

Theo quy tắc mặc định thường gặp, Spring rollback transaction khi phương thức được advised ném `RuntimeException` hoặc `Error`; checked exception không tự gây rollback trừ khi có cấu hình hoặc quy tắc riêng:

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void importData() throws BusinessCheckedException {
    // ...
}
~~~

Nếu phương thức tự bắt exception rồi trả về bình thường, interceptor thường không thể biết rằng code muốn rollback. Khi cần, hãy để exception truyền ra ngoài hoặc áp dụng một chiến lược rollback tường minh.

## 3. @Async: cần bật async processing và có executor

`@Async` thuộc `org.springframework.scheduling.annotation`. Nó yêu cầu Spring thực thi lời gọi phù hợp thông qua một executor thay vì xử lý toàn bộ phần việc trên luồng của caller.

Điều kiện quan trọng nhất là **phải bật xử lý async**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
}
~~~

Spring Boot có thể tự cấu hình executor khi điều kiện của task execution auto-configuration khớp. Tuy nhiên, có sẵn một executor bean **không tự động bật** `@Async`. `@EnableAsync` (hoặc cấu hình tích hợp tương đương) mới kích hoạt các thành phần nhận diện annotation và tạo advice.

### Ví dụ service bất đồng bộ

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportGenerator {

    @Async("reportsExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Minh họa công việc tạo báo cáo.
        String result = "report-" + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Cấu hình executor dành riêng cho tác vụ báo cáo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ReportsAsyncConfiguration {

    @Bean("reportsExecutor")
    ThreadPoolTaskExecutor reportsExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("reports-");
        return executor;
    }
}
~~~

Giá trị `"reportsExecutor"` trong `@Async` chọn executor có qualifier/name tương ứng. Nếu bỏ qualifier, Spring áp dụng quy tắc tìm executor mặc định hoặc fallback theo cấu hình async thực tế.

Một bean khác gọi:

~~~java
CompletableFuture<String> result =
        reportGenerator.generate("daily-sales");
~~~

Khi lời gọi đi qua async proxy, phần thân `generate()` được thực thi thông qua executor. Caller nhận một đối tượng `CompletableFuture` để theo dõi kết quả. Nếu lập tức gọi `result.join()`, caller lại đợi kết quả và có thể làm mất lợi ích về thời gian của xử lý bất đồng bộ.

### Kiểu trả về và xử lý exception

Trong cơ chế `@Async` thông thường, phương thức có thể trả về `void`, `Future<T>` hoặc `CompletableFuture<T>`.

- Với `CompletableFuture`, caller có thể xử lý thành công/thất bại qua các stage như `thenApply` hoặc `exceptionally`.
- Với `void`, caller không nhận future để quan sát lỗi. Uncaught exception được đưa tới `AsyncUncaughtExceptionHandler` nếu có cấu hình thích hợp.
- Exception trong tác vụ async không tự trở thành exception đồng bộ của lời gọi caller sau khi công việc đã được gửi tới executor.

Các vấn đề như executor đầy queue, shutdown hoặc từ chối task cũng cần chính sách xử lý rõ ràng. Không nên mặc định mọi task async sẽ luôn được chấp nhận.

### @Async không tự mang theo transaction của caller

Một transaction imperative thông thường sử dụng state gắn với thread. Tác vụ `@Async` lại chạy trên thread do executor quản lý, nên **không tự kế thừa transaction thread-bound của caller**.

Ví dụ:

~~~java
@Transactional
public void submitOrder() {
    orderRepository.save(order);
    emailService.sendConfirmation(order);
}
~~~

Nếu `emailService.sendConfirmation()` được chạy bởi `@Async`, tác vụ gửi email có thể bắt đầu trước khi transaction bên ngoài commit. Nếu transaction rollback, email có thể vẫn đã được gửi.

Khi muốn phát sự kiện chỉ sau commit, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)`, outbox pattern hoặc cơ chế tin nhắn tin cậy. Không nên kết hợp `@Async` và `@Transactional` một cách máy móc rồi giả định transaction được truyền qua thread.

## 4. @Cacheable: cần bật caching và có CacheManager

`@Cacheable` thuộc `org.springframework.cache.annotation`. Nó mô tả việc Spring có thể tra cứu kết quả phương thức theo key, bỏ qua phần thân khi cache hit, hoặc gọi phương thức rồi lưu kết quả khi cache miss.

Điểm kích hoạt thường dùng:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CachingConfiguration {
}
~~~

Có `spring-boot-starter-cache` trên classpath **chưa đủ** nếu ứng dụng chưa bật caching processing. `@EnableCaching` đăng ký phần cơ chế xử lý annotation; `CacheManager` cung cấp cache thực tế.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Khi có dependency và điều kiện phù hợp, Spring Boot có thể tự cấu hình `CacheManager` với một cache provider như Caffeine. Nếu không có provider phù hợp, cấu hình mặc định có thể dùng simple in-memory cache tùy môi trường và phiên bản. Production nên chọn provider và chính sách lưu trữ rõ ràng.

### Ví dụ @Cacheable

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookup {

    private final ProductRepository productRepository;

    public ProductLookup(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public Product findBySku(String sku) {
        return productRepository.findBySku(sku)
                .orElseThrow();
    }
}
~~~

Lần đầu caller đi qua proxy gọi `findBySku("A-100")`:

1. Cache interceptor tạo key từ biểu thức `#sku`.
2. Nếu key chưa có trong cache `products`, interceptor gọi phương thức thật.
3. Kết quả có thể được lưu vào cache theo chính sách hiện tại.
4. Caller nhận kết quả.

Ở các lần gọi sau với cùng key, interceptor có thể trả kết quả trong cache mà không gọi repository.

Một cấu hình Caffeine minh họa:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: products
    caffeine:
      spec: maximumSize=1000,expireAfterWrite=10m
~~~

`cache-names` xác định các cache cần tạo tùy provider; `caffeine.spec` định nghĩa kích thước và thời gian hết hạn trong ví dụ. Cần cân nhắc dữ liệu stale, eviction và việc nhiều instance có cache cục bộ riêng.

### Các annotation cache liên quan

| Annotation | Vai trò |
|---|---|
| `@Cacheable` | Tra cứu và có thể bỏ qua lời gọi phương thức khi cache hit |
| `@CachePut` | Luôn gọi phương thức, sau đó cập nhật cache theo kết quả |
| `@CacheEvict` | Xóa entry hoặc toàn bộ cache theo cấu hình |
| `@Caching` | Kết hợp nhiều annotation cache cho một phương thức |

`@Cacheable` hỗ trợ `key`, `condition`, `unless` và các tùy chọn khác. Ví dụ:

~~~java
@Cacheable(
        cacheNames = "products",
        key = "#sku",
        condition = "#sku != null",
        unless = "#result == null"
)
public Product findBySku(String sku) {
    // ...
}
~~~

`condition` được xem xét trước khi gọi phương thức; `unless` có thể dùng kết quả sau lời gọi để quyết định không lưu. Không nên sử dụng cache nếu kết quả phụ thuộc vào quyền truy cập, ngữ cảnh request hoặc dữ liệu dễ thay đổi mà key không thể hiện đủ những yếu tố đó.

## 5. Ba annotation khác nhau ở đâu?

| Tiêu chí | @Transactional | @Async | @Cacheable |
|---|---|---|---|
| Vấn đề giải quyết | Tính nhất quán giao dịch | Chuyển công việc tới executor | Tránh tính toán/truy vấn lặp lại |
| Annotation kích hoạt phổ biến | `@EnableTransactionManagement` hoặc Boot auto-configuration khi phù hợp | `@EnableAsync` | `@EnableCaching` |
| Hạ tầng cần thiết | Transaction manager | Executor | Cache manager |
| Hiệu ứng | Commit/rollback theo transaction boundary | Có thể đổi thread và thời điểm xử lý | Có thể không chạy thân phương thức khi hit |
| Rủi ro thường gặp | Không có manager, sai propagation, self-invocation | Chạy đồng bộ, mất context thread, task bị reject | Cache stale, key sai, cache chưa bật |
| Quan hệ với self-invocation | Lời gọi nội bộ bỏ qua transactional advice | Lời gọi nội bộ bỏ qua async advice | Lời gọi nội bộ bỏ qua cache advice |

Cả ba có thể dùng Spring AOP proxy, nhưng **không chia sẻ cùng transaction manager, executor hoặc cache manager**. Có một trong các hạ tầng này không có nghĩa hai hạ tầng còn lại tự xuất hiện.

## 6. Các điều kiện hạ tầng trong Spring Boot

Spring Boot có nhiều auto-configuration hỗ trợ cấu hình mặc định theo classpath và những bean đã tồn tại. Dù vậy, nên phân biệt giữa **tạo hạ tầng** và **bật xử lý annotation**.

### Transaction

Trong ứng dụng JDBC/JPA, khi có các dependency và cấu hình kết nối phù hợp, Boot có thể tạo `PlatformTransactionManager`. Nếu transaction management conditions khớp, Boot hỗ trợ kích hoạt xử lý `@Transactional` mà không cần code cấu hình tường minh.

Nếu có nhiều transaction managers, một lời gọi có thể cần chọn manager qua qualifier hoặc cấu hình transaction management:

~~~java
@Transactional("ordersTransactionManager")
public void updateOrder() {
    // ...
}
~~~

Tên phải khớp bean manager thực tế. Không nên tin rằng Spring luôn chọn đúng manager khi ứng dụng có nhiều datasource hoặc mô hình giao dịch.

### Async

Boot có cơ chế `TaskExecutionAutoConfiguration` để cung cấp executor thích hợp theo điều kiện. Nhưng một project có executor bean chưa chắc đã bật xử lý annotation async; **`@EnableAsync` vẫn là bước quyết định** trong cấu hình proxy-based async thông thường.

Executor không chỉ quyết định số thread: cần quan tâm queue capacity, giới hạn concurrency, khả năng từ chối tác vụ, shutdown và quan sát lỗi. Nên dùng executor riêng cho nhóm workload có hành vi rất khác nhau.

### Caching

Boot có cache auto-configuration để tạo `CacheManager` phù hợp với provider và các điều kiện liên quan. `@EnableCaching` cung cấp interceptor nhận diện `@Cacheable`; khi thiếu cache infrastructure, việc khởi tạo có thể thất bại hoặc annotation không có hiệu lực như mong muốn tùy cấu hình.

Một ví dụ cấu hình cache manager tường minh:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class LocalCacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

`ConcurrentMapCacheManager` chỉ thích hợp để minh họa hoặc dùng cache local đơn giản. Nó không cung cấp các chính sách phân tán, đồng bộ nhiều instance hoặc eviction theo thời gian như một số cache provider khác.

### @SpringBootApplication không tự bật tất cả

`@SpringBootApplication` kích hoạt auto-configuration và component scanning, nhưng không nên diễn giải rằng mọi annotation framework đều đã có đầy đủ hạ tầng. Tính năng nào cũng phụ thuộc điều kiện của mình.

Một cấu hình ứng dụng có thể chủ động bật async và cache:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
@EnableCaching
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Ví dụ này **không tự tạo database hoặc transaction manager**. Nếu các service dùng `@Transactional`, ứng dụng vẫn cần hạ tầng giao dịch phù hợp với công nghệ lưu trữ đang dùng.

## 7. Proxy và self-invocation: vì sao có annotation vẫn không chạy?

Trong proxy-based AOP, advice được áp dụng khi caller gọi phương thức **qua proxy Spring**.

~~~text
Controller
    |
    v
OrderService proxy
    |
    +--> Transaction advice
    |
    v
OrderService target.placeOrder()
~~~

Nhưng nếu target tự gọi một phương thức khác của chính nó:

~~~java
@Service
public class ProductService {

    public Product loadForOrder(String sku) {
        return findCached(sku);
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public Product findCached(String sku) {
        return loadProduct(sku);
    }
}
~~~

Lời gọi `findCached(sku)` trong `loadForOrder()` tương đương với `this.findCached(sku)`. Nó không quay lại proxy, nên caching advice của `findCached()` bị bỏ qua trong lời gọi này.

Nguyên tắc tương tự áp dụng cho:

~~~java
public void doWork() {
    saveInNewTransaction(); // @Transactional không tạo ranh giới mới ở đây
    sendAsync();            // @Async không chuyển qua executor ở đây
    readFromCache();        // @Cacheable không tra cache ở đây
}
~~~

Đối với transaction, nếu phương thức ngoài đã mở transaction, phương thức trong vẫn có thể chạy **trong transaction hiện hữu**. Điều bị bỏ qua là advice riêng của phương thức trong, chẳng hạn `REQUIRES_NEW` hoặc timeout riêng.

Một số giới hạn khác cũng cần lưu ý:

- `private` method không được intercept theo cơ chế class-based proxy vì không thể override.
- `final` method không thể được class-based proxy override.
- JDK interface proxy chỉ phơi bày các phương thức qua interface được proxy.
- Lời gọi trong constructor hoặc một số bước khởi tạo sớm có thể diễn ra khi proxy chưa sẵn sàng cho cách sử dụng mong muốn.

Chuyển từ JDK dynamic proxy sang CGLIB không sửa được self-invocation. Vấn đề chính vẫn là **đường gọi có đi qua proxy hay không**.

## 8. Giải pháp: đặt ranh giới advice ở giữa các bean

Cách rõ ràng nhất thường là tách chức năng cần advice sang bean độc lập rồi inject bean đó vào caller.

Ví dụ, một workflow cần tạo order trong transaction và gửi thông báo async:

~~~java
@Service
public class CheckoutService {

    private final OrderWriter orderWriter;
    private final NotificationSender notificationSender;

    public CheckoutService(
            OrderWriter orderWriter,
            NotificationSender notificationSender) {
        this.orderWriter = orderWriter;
        this.notificationSender = notificationSender;
    }

    public void checkout(Order order) {
        orderWriter.save(order);
        notificationSender.sendAsync(order.getId());
    }
}
~~~

Bean có ranh giới transaction:

~~~java
@Service
public class OrderWriter {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void save(Order order) {
        repository.save(order);
    }
}
~~~

Bean có ranh giới async:

~~~java
@Service
public class NotificationSender {

    @Async("reportsExecutor")
    public void sendAsync(Long orderId) {
        // Gửi thông báo bằng executor đã cấu hình.
    }
}
~~~

Trong ví dụ này, `CheckoutService` gọi hai dependency thông qua bean của Spring, tạo cơ hội cho các advice riêng của `OrderWriter` và `NotificationSender` thực thi.

Tuy nhiên, thứ tự `save()` trả về và `sendAsync()` được gọi **không bảo đảm thông báo chỉ được gửi sau khi commit của một transaction bên ngoài khác**. Nếu cần atomicity với sự kiện gửi thông báo, phải thiết kế theo ranh giới commit thực tế, chẳng hạn transactional outbox hoặc event sau commit.

## 9. Kết hợp @Transactional và @Async

Đặt cả hai annotation trên một phương thức có thể làm thứ tự advice và ngữ cảnh thread khó hiểu. Ví dụ:

~~~java
@Async
@Transactional
public void processInBackground() {
    // ...
}
~~~

Ý định có thể là mở transaction trong thread nền, nhưng để biết chắc hạ tầng nào can thiệp trước/sau cần xét cấu hình proxy/advisor và executor.

Một thiết kế thường dễ reasoning hơn là:

~~~text
Caller
  |
  v
AsyncCoordinator proxy
  |
  v
Executor thread
  |
  v
TransactionWorker proxy
  |
  v
Transaction mở ở executor thread
  |
  v
Thao tác dữ liệu
~~~

Ví dụ:

~~~java
@Service
public class AsyncCoordinator {

    private final TransactionWorker worker;

    public AsyncCoordinator(TransactionWorker worker) {
        this.worker = worker;
    }

    @Async("reportsExecutor")
    public CompletableFuture<Void> process(String id) {
        worker.processTransaction(id);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

~~~java
@Service
public class TransactionWorker {

    @Transactional
    public void processTransaction(String id) {
        // Thao tác dữ liệu trong thread đang gọi.
    }
}
~~~

Khi `AsyncCoordinator.process()` được gọi qua async proxy, body của nó chạy trong executor thread; lời gọi sang bean `TransactionWorker` đi qua transactional proxy và transaction được mở ở thread đó.

Cần xử lý exception trong future và tránh gửi dữ liệu mutable không thread-safe giữa các task. Nếu business cần kết quả đồng bộ và tính nhất quán chặt, không phải mọi thao tác đều nên dùng `@Async`.

## 10. Kết hợp @Transactional và @Cacheable

Cache và database có mô hình nhất quán khác nhau. Database transaction có commit/rollback; cache có thể lưu hoặc loại bỏ entry tùy advice và provider.

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#sku")
@Transactional(readOnly = true)
public Product getProduct(String sku) {
    return productRepository.findBySku(sku)
            .orElseThrow();
}
~~~

Khi cache hit, caching interceptor có thể trả kết quả mà không gọi phần thân. Vì vậy, không nên giả định mọi lần gọi `getProduct()` đều thực hiện truy vấn hoặc có cùng hành vi transaction ở thân phương thức.

Việc advisor cache và transaction bao quanh nhau theo thứ tự nào còn phụ thuộc cấu hình advisor ordering. Với cập nhật dữ liệu, đừng tự suy luận rằng việc ghi cache luôn xảy ra **sau khi database commit**.

Một mô hình thường gặp:

~~~java
@Transactional
public void updateProduct(Product product) {
    productRepository.save(product);
    // Việc cập nhật/xóa cache cần chính sách nhất quán riêng.
}
~~~

Nếu ứng dụng dùng `@CacheEvict` hoặc `@CachePut`, cần xác định thời điểm cache thay đổi so với transaction commit và cách xử lý rollback. Có thể cân nhắc cache transaction-aware hoặc phát event sau commit khi yêu cầu tính nhất quán cao.

Cũng cần lưu ý: nếu một phương thức được gọi nhiều lần trong cùng instance qua self-invocation, cache advice sẽ bị bỏ qua dù cache manager đã tồn tại và cache names đúng.

## 11. Không phải mọi lời gọi cần advice đều thích hợp với @Async hoặc cache

Một vài giới hạn thiết kế quan trọng:

**Transaction:** chỉ có ý nghĩa trên những tài nguyên được transaction manager quản lý. Không thể dùng một JDBC transaction đơn lẻ để tự động đảm bảo atomicity cho HTTP request hoặc một hệ thống bên ngoài không tham gia giao dịch.

**Async:** không làm CPU chạy nhanh hơn một cách thần kỳ. Nó chuyển việc sang executor; nếu số task vượt năng lực xử lý, queue sẽ tăng và có thể bị reject. Cần quản lý concurrency, timeout và shutdown.

**Cache:** tăng hiệu quả với phép đọc lặp lại nhưng tạo bài toán dữ liệu cũ. Khi nguồn dữ liệu thay đổi, cần chính sách invalidation hoặc TTL. Nếu cache key không bao gồm tenant/user/context, có thể trả sai dữ liệu cho đối tượng khác.

**Proxy:** không phải mọi đoạn code tạo bằng `new` đều là Spring bean. Nếu một object được khởi tạo thủ công ngoài ApplicationContext, không nên mong Spring tự áp dụng transaction, async hoặc caching advice lên các method của object đó.

## 12. Chẩn đoán khi annotation không có hiệu lực

Khi `@Transactional`, `@Async` hoặc `@Cacheable` không hoạt động như kỳ vọng, nên phân biệt lỗi **hạ tầng** với lỗi **đường gọi**.

| Triệu chứng | Điểm cần xem |
|---|---|
| Có `@Transactional` nhưng không có giao dịch | Transaction manager, hỗ trợ annotation, bean proxy, self-invocation |
| `REQUIRES_NEW` không tạo transaction độc lập | Lời gọi nội bộ, transaction manager được chọn, boundary của caller |
| Có `@Async` nhưng vẫn chạy trên request thread | `@EnableAsync`, caller có đi qua proxy, executor |
| Task async không chạy hoặc bị mất | Executor bị reject, shutdown, exception handling |
| Có `@Cacheable` nhưng luôn truy vấn | `@EnableCaching`, `CacheManager`, cache name/key, self-invocation |
| Cache trả dữ liệu cũ hoặc sai | TTL/invalidation, cache provider, key và ngữ cảnh request |
| Bean có annotation nhưng không được advise | Bean có được Spring quản lý không, method visibility, final/private, proxy type |

### Kiểm tra proxy

Trong một điểm kiểm thử hoặc chẩn đoán phù hợp, có thể dùng:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(someServiceBean);
~~~

Kết quả `true` cho biết bean là Spring AOP proxy, **không chứng minh** phương thức cụ thể đang được transaction, async hoặc cache interceptor xử lý. Cần quan sát hành vi thực tế và các advisor áp dụng.

### Kiểm tra transaction hiện tại

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
~~~

Đây là kiểm tra có ích cho transaction imperative trong thread hiện tại, không phải cơ chế chẩn đoán chung cho reactive transaction. Nếu lời gọi nằm trong transaction do caller khác mở, kết quả `true` không chứng minh interceptor ở phương thức đang kiểm tra đã chạy.

### Quan sát async thread và cache hit

Trong phương thức `@Async`, có thể ghi thread name để phân biệt caller thread với executor thread. Trong phương thức `@Cacheable`, có thể đếm số lần code gọi repository để biết thân phương thức có bị bỏ qua khi cache hit không.

Các kiểm tra này nên được đặt trong test hoặc logging chẩn đoán, tránh ghi dữ liệu nhạy cảm và tránh đưa log chi tiết không cần thiết vào production.

## 13. Gợi ý kiểm thử từng hạ tầng

Một bộ test cho ứng dụng Spring Boot có thể xác nhận:

1. **Transaction:** gọi service từ bean khác và kiểm tra transaction hoạt động, rollback khi có exception phù hợp.
2. **Propagation:** kiểm tra `REQUIRES_NEW` qua hai bean khác nhau, không qua `this.method()`.
3. **Async:** gọi method qua Spring bean, nhận future, xác nhận công việc được chuyển sang executor và lỗi được phản ánh theo hợp đồng.
4. **Cache:** gọi cùng key hai lần qua proxy, xác nhận repository được gọi số lần dự kiến; thay key thì cache miss.
5. **Infrastructure missing:** với cấu hình test tối giản, quan sát tác động khi thiếu activation annotation hoặc manager tương ứng.
6. **Integration:** kiểm tra việc gửi sự kiện sau commit, invalidation cache và shutdown executor khi có nhiều advisor.

Không nên kết luận AOP hoạt động chỉ vì test gọi trực tiếp phương thức trên object được tạo bằng `new`. Một test kiểu unit không dựng ApplicationContext sẽ không có các proxy Spring như trong ứng dụng thật.

Khi sử dụng `@SpringBootTest` hoặc context runner, cần nhớ rằng test cũng có thể tự chạy bên trong transaction, làm kết quả khác kỳ vọng nếu không xác định ranh giới test transaction.

## 14. Quy trình chọn và sử dụng đúng

Khi thêm một annotation AOP vào Spring Boot service:

1. Xác định yêu cầu thực tế: giao dịch, bất đồng bộ hay cache.
2. Kiểm tra dependency của cơ chế đó đã có trên classpath chưa.
3. Bảo đảm tính năng được kích hoạt: transaction management, async processing hoặc caching.
4. Cấu hình đúng manager/executor/cache provider; xác định tên bean nếu có nhiều lựa chọn.
5. Đặt method tại điểm vào có thể được gọi qua Spring proxy, tránh self-invocation.
6. Kiểm tra kiểu trả về, exception handling và ngữ cảnh thread nếu dùng `@Async`.
7. Kiểm tra transaction boundary, propagation và rollback semantics nếu dùng `@Transactional`.
8. Thiết kế cache key, thời hạn lưu và invalidation nếu dùng `@Cacheable`.
9. Khi kết hợp nhiều annotation, xét thứ tự advisor, transaction commit và tính nhất quán dữ liệu.
10. Kiểm thử hành vi thực tế qua bean do Spring quản lý, thay vì chỉ kiểm tra annotation có tồn tại.

Điểm cần nhớ là **annotation, proxy và hạ tầng thực thi là ba phần khác nhau**. `@Transactional` cần transaction manager; `@Async` cần async processing và executor; `@Cacheable` cần caching processing và cache manager. Trong proxy mode, cả ba chỉ có cơ hội can thiệp khi lời gọi đi qua proxy phù hợp. Tách đúng ranh giới bean và cấu hình hạ tầng rõ ràng giúp tránh những lỗi khó nhận biết trong ứng dụng Spring Boot.

