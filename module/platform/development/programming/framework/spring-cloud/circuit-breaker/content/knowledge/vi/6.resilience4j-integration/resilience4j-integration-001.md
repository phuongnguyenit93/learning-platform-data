# Resilience4JCircuitBreakerFactory và các thành phần được phối hợp

Spring Cloud CircuitBreaker cung cấp một lớp API thống nhất để ứng dụng bảo vệ lời gọi đến dịch vụ phụ thuộc. Khi chọn Resilience4j làm implementation, ứng dụng thường nhận một factory tên là **Resilience4JCircuitBreakerFactory** cho luồng blocking. Factory tạo ra các Circuit Breaker theo tên, kết hợp cấu hình Resilience4j và các cơ chế liên quan như TimeLimiter, Bulkhead, executor và bộ phát sự kiện.

Hiểu vai trò của factory và các thành phần phối hợp giúp tổ chức cấu hình theo từng dịch vụ phụ thuộc. Mỗi dịch vụ có thể có ngưỡng lỗi, sliding window, thời gian chờ, timeout và giới hạn đồng thời riêng. Factory chịu trách nhiệm tạo đối tượng bảo vệ theo cấu hình; Circuit Breaker thực hiện quyết định cho phép hoặc từ chối lời gọi trong lúc chạy.

## 1. Factory là gì và tạo ra thành phần nào?

**Resilience4JCircuitBreakerFactory** là điểm khởi tạo Circuit Breaker trong tích hợp Spring Cloud CircuitBreaker với Resilience4j cho lời gọi blocking. Spring Boot auto-configuration cung cấp factory khi starter tương ứng đã có trên classpath và cấu hình ứng dụng phù hợp.

Ứng dụng thường inject factory vào service hoặc gateway rồi gọi **create(id)** để lấy một Circuit Breaker có tên:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private final Resilience4JCircuitBreakerFactory circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            Resilience4JCircuitBreakerFactory circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        CircuitBreaker breaker = circuitBreakerFactory.create("inventory");
        return breaker.run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

Trong ví dụ, tên **inventory** là định danh cấu hình cho lời gọi đến dịch vụ tồn kho. Khi gọi **create("inventory")**, factory tạo hoặc lấy Circuit Breaker tương ứng với định danh đó. Supplier chứa thao tác gọi dịch vụ phụ thuộc; hàm fallback xử lý lỗi được chuyển đến từ lời gọi được bảo vệ, bao gồm trường hợp Circuit Breaker từ chối khi OPEN.

Không nên dùng cùng một tên cho các dịch vụ phụ thuộc có hành vi và chính sách bảo vệ khác nhau. Nếu Catalog và Inventory có độ trễ, lưu lượng hoặc mức độ quan trọng khác nhau, hãy đặt các định danh riêng, ví dụ **catalog** và **inventory**. Nhờ vậy, cấu hình, trạng thái, metric và log có thể được theo dõi độc lập.

Factory là thành phần tạo Circuit Breaker; nó không tự quyết định dữ liệu fallback có hợp lệ về nghiệp vụ hay không. Ứng dụng vẫn phải định nghĩa hành vi khi dịch vụ phụ thuộc không sẵn sàng, chẳng hạn đọc cache, trả thông báo có thể thử lại hoặc phát sinh lỗi nghiệp vụ.

## 2. Các thành phần chính trong tích hợp

Một lời gọi được bảo vệ có thể phối hợp nhiều thành phần. Mỗi thành phần giải quyết một khía cạnh riêng:

| Thành phần | Vai trò | Ví dụ cấu hình hoặc API |
|---|---|---|
| Resilience4JCircuitBreakerFactory | Tạo Circuit Breaker theo định danh và cấu hình ứng dụng | **create("inventory")** |
| CircuitBreaker | Theo dõi kết quả lời gọi và quyết định CLOSED, OPEN hoặc HALF_OPEN | **CircuitBreakerConfig** |
| CircuitBreakerRegistry | Quản lý các Circuit Breaker và cấu hình tương ứng của Resilience4j | Registry theo tên instance |
| TimeLimiter | Giới hạn thời gian chờ của một thao tác bất đồng bộ hoặc thao tác được tích hợp qua executor | **TimeLimiterConfig** |
| Bulkhead | Giới hạn số lời gọi đồng thời hoặc tài nguyên dành cho một dịch vụ | **BulkheadConfig** hoặc **ThreadPoolBulkheadConfig** |
| Executor hoặc scheduler | Thực thi tác vụ và hỗ trợ cơ chế timeout theo mô hình tích hợp | Executor được cấu hình cho factory |
| Customizer | Điều chỉnh cấu hình mặc định, cấu hình theo ID hoặc gắn hành vi bổ sung | **Customizer<Resilience4JCircuitBreakerFactory>** |
| Event publisher và metrics | Phát sự kiện chuyển trạng thái, ghi nhận số lời gọi và hỗ trợ giám sát | State transition, Micrometer |

**CircuitBreaker** là phần lõi của cơ chế ngắt mạch. Nó ghi nhận kết quả theo sliding window, tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm và chuyển trạng thái khi điều kiện cấu hình được đáp ứng. Khi OPEN, nó từ chối lời gọi mới; khi HALF_OPEN, nó chỉ cho phép số lượng probe được cấu hình.

**TimeLimiter** giải quyết giới hạn thời gian. Một lời gọi có thể được Circuit Breaker cho phép nhưng vẫn chờ quá lâu. TimeLimiter giúp giới hạn thời gian chờ để ứng dụng không giữ tài nguyên vô thời hạn. Timeout có thể được tính là lỗi hoặc lời gọi chậm tùy cách cấu hình Circuit Breaker.

**Bulkhead** giới hạn mức độ đồng thời mà một dịch vụ phụ thuộc có thể chiếm dụng. Circuit Breaker phản ứng với tỷ lệ lỗi hoặc độ trễ được ghi nhận; Bulkhead giới hạn tài nguyên đang được sử dụng cùng lúc. Khi Bulkhead hết sức chứa, lời gọi có thể bị từ chối bằng ngoại lệ riêng, chẳng hạn **BulkheadFullException**.

Các thành phần có thể được kết hợp nhưng không thay thế nhau. Một hệ thống có thể cần cả timeout, Circuit Breaker và Bulkhead: timeout giới hạn thời gian chờ, Circuit Breaker ngăn tiếp tục gọi khi dịch vụ có dấu hiệu không khỏe, còn Bulkhead ngăn một dịch vụ chiếm hết tài nguyên dành cho các phần khác.

## 3. Cấu hình mặc định bằng Customizer

Spring Cloud cho phép cấu hình factory bằng Spring bean kiểu **Customizer**. Cách này phù hợp khi muốn áp dụng một chính sách mặc định cho các Circuit Breaker được tạo trong ứng dụng.

Ví dụ sau cấu hình cửa sổ đếm, số lời gọi tối thiểu, ngưỡng lỗi và thời gian chờ của TimeLimiter:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        CircuitBreakerConfig circuitBreakerConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(15))
                .permittedNumberOfCallsInHalfOpenState(3)
                .build();

        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .build();

        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(circuitBreakerConfig)
                .timeLimiterConfig(timeLimiterConfig)
                .build()
        );
    }
}
~~~

**configureDefault** nhận một hàm tạo cấu hình từ định danh Circuit Breaker. Cấu hình mặc định này được sử dụng cho những ID không có cấu hình riêng phù hợp. Đối số **id** giúp tạo cấu hình theo tên, nếu cần có thể dùng nó để chọn chính sách khác nhau.

Trong ví dụ:

- Cửa sổ **COUNT_BASED** có kích thước 20 mẫu.
- Chỉ bắt đầu đánh giá tỷ lệ lỗi khi có ít nhất 10 lời gọi.
- Ngưỡng lỗi 50% là điều kiện để Circuit Breaker có thể mở.
- Thời gian giữ trạng thái OPEN là 15 giây.
- HALF_OPEN chỉ cho phép tối đa ba lời gọi thăm dò.
- TimeLimiter giới hạn thời gian chờ ở hai giây.

Đây là giá trị minh họa. Cần điều chỉnh theo độ trễ bình thường, lưu lượng, mức độ quan trọng và khả năng phục hồi của từng dịch vụ phụ thuộc. Không nên áp dụng một timeout hoặc ngưỡng lỗi chung cho tất cả dịch vụ nếu đặc tính của chúng khác nhau.

## 4. Cấu hình riêng cho từng định danh

Khi các dịch vụ phụ thuộc có đặc tính khác nhau, dùng **configure** để áp dụng cấu hình riêng cho một hoặc nhiều ID. Cấu hình theo ID giúp Catalog có thời gian chờ ngắn, trong khi Inventory có thể cần thời gian chờ dài hơn vì thao tác nghiệp vụ khác nhau.

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class NamedCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryConfiguration() {
        CircuitBreakerConfig inventoryConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
                .slidingWindowSize(30)
                .minimumNumberOfCalls(15)
                .failureRateThreshold(40)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        TimeLimiterConfig inventoryTimeLimiter =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(3))
                .build();

        return factory -> factory.configure(
            builder -> builder
                .circuitBreakerConfig(inventoryConfig)
                .timeLimiterConfig(inventoryTimeLimiter),
            "inventory"
        );
    }
}
~~~

Ở đây, **inventory** dùng cửa sổ theo thời gian 30 giây, tối thiểu 15 lời gọi, ngưỡng lỗi 40%, thời gian OPEN 20 giây, hai probe ở HALF_OPEN và timeout ba giây. Khi gọi **create("inventory")**, factory dùng cấu hình gắn với ID đó.

Có thể khai báo cấu hình cho nhiều ID trong một lần gọi **configure**, nhưng chỉ nên nhóm các ID khi chúng thực sự cần cùng chính sách. Nếu từng dịch vụ có SLA, lưu lượng hoặc đặc điểm lỗi khác nhau, hãy tách cấu hình để việc điều chỉnh không gây ảnh hưởng ngoài ý muốn.

## 5. Cấu hình qua application.yml

Resilience4j cũng hỗ trợ cấu hình theo instance trong **application.yml**. Cách này giúp tách chính sách khỏi mã Java và thuận tiện điều chỉnh theo môi trường triển khai.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
      catalog:
        timeoutDuration: 2s
~~~

Tên dưới **instances** phải khớp với ID mà ứng dụng truyền vào factory, chẳng hạn **create("inventory")**. Nếu cấu hình được khai báo cho ID **inventory** nhưng code lại tạo **create("stock-service")**, cấu hình theo instance đó sẽ không áp dụng như dự kiến.

Khi dùng cả YAML properties và Java Customizer, cần hiểu quy tắc ưu tiên của phiên bản Spring Cloud và Resilience4j đang sử dụng. Spring Cloud CircuitBreaker hỗ trợ cấu hình qua properties và tài liệu của phiên bản có quy định thứ tự ưu tiên giữa properties với Java Customizer. Tránh khai báo cùng một tham số cho cùng một ID ở nhiều nơi nếu không có lý do; khi cần kết hợp, hãy xác định rõ lớp cấu hình nào là nguồn quyết định cuối cùng và kiểm tra cấu hình hiệu lực khi ứng dụng khởi động.

## 6. Gắn hành vi bổ sung sau khi Circuit Breaker được tạo

Factory cung cấp **addCircuitBreakerCustomizer** để đăng ký thao tác tùy chỉnh lên đối tượng Circuit Breaker đã được tạo. Một trường hợp thường dùng là đăng ký listener theo dõi chuyển trạng thái.

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerEventConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEventListener() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                    log.info(
                        "Circuit Breaker inventory chuyển trạng thái: {}",
                        event.getStateTransition()
                    )
                ),
            "inventory"
        );
    }
}
~~~

Customizer này chỉ gắn listener cho Circuit Breaker có ID **inventory**. Khi trạng thái chuyển từ CLOSED sang OPEN, OPEN sang HALF_OPEN hoặc HALF_OPEN trở lại CLOSED/OPEN, ứng dụng có thể ghi nhận sự kiện để hỗ trợ vận hành.

Có thể đăng ký listener cho các sự kiện khác như lời gọi thành công, thất bại hoặc bị từ chối. Tuy nhiên, không nên ghi log quá chi tiết ở mức ERROR cho mọi lời gọi bị từ chối, vì trong thời gian OPEN có thể có rất nhiều yêu cầu. Metric tổng hợp thường phù hợp hơn để quan sát lưu lượng và tỷ lệ lỗi; log nên tập trung vào chuyển trạng thái hoặc những tình huống cần điều tra.

## 7. TimeLimiter và executor phối hợp với factory

TimeLimiter đặt giới hạn thời gian cho thao tác được bảo vệ. Trong tích hợp Spring Cloud CircuitBreaker với Resilience4j, cấu hình TimeLimiter được đưa vào **Resilience4JConfigBuilder** cùng cấu hình Circuit Breaker. Khi ứng dụng dùng API blocking và timeout cần thực thi tác vụ trên executor, factory có thể được cấu hình với một executor phù hợp thông qua **configureExecutorService**.

Ví dụ tạo executor có tên riêng cho tác vụ được quản lý:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService circuitBreakerExecutor() {
        return Executors.newScheduledThreadPool(8);
    }

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> configureCircuitBreakerExecutor(
            ScheduledExecutorService circuitBreakerExecutor) {
        return factory ->
            factory.configureExecutorService(circuitBreakerExecutor);
    }
}
~~~

Kích thước executor cần được chọn theo tải dự kiến và thời gian xử lý. Nếu executor dùng chung cho nhiều tác vụ, một nhóm lời gọi bị treo hoặc chạy lâu có thể ảnh hưởng đến các tác vụ khác. Cần theo dõi hàng đợi, số luồng đang hoạt động và thời gian chờ.

Timeout không đảm bảo mọi thao tác I/O bên dưới tự dừng ngay lập tức. Khả năng hủy tác vụ phụ thuộc vào client, executor và cách thao tác được triển khai. Với client blocking, hãy cấu hình timeout ở tầng HTTP/database tương ứng để thao tác mạng thực sự có giới hạn. Với reactive client, ưu tiên cơ chế timeout và hủy subscription phù hợp với pipeline; không chặn event loop bằng lời gọi đồng bộ.

## 8. Bulkhead được phối hợp như thế nào?

Bulkhead tạo giới hạn tài nguyên cho từng dịch vụ phụ thuộc. Trong tích hợp Spring Cloud CircuitBreaker với Resilience4j, hỗ trợ Bulkhead có thể được kích hoạt khi dependency Bulkhead của Resilience4j có mặt trên classpath. Tích hợp hỗ trợ hai kiểu phổ biến:

- **SemaphoreBulkhead:** giới hạn số lời gọi đồng thời bằng semaphore; lời gọi vượt giới hạn bị từ chối.
- **FixedThreadPoolBulkhead:** cô lập lời gọi trong thread pool và hàng đợi có giới hạn.

Kiểu Bulkhead và cách cấu hình phụ thuộc phiên bản cùng thuộc tính tích hợp đang dùng. Spring Cloud CircuitBreaker Resilience4j có thuộc tính **spring.cloud.circuitbreaker.resilience4j.enableSemaphoreDefaultBulkhead** để chọn SemaphoreBulkhead làm kiểu mặc định trong cấu hình tương ứng. Trước khi bật, cần xem tài liệu của release train đang dùng và kiểm tra ảnh hưởng lên luồng blocking hoặc reactive.

Bulkhead không phải một Circuit Breaker thứ hai. Ví dụ, Circuit Breaker **inventory** có thể vẫn CLOSED nhưng Bulkhead đã hết số slot đồng thời. Khi đó lời gọi bị Bulkhead từ chối; không có nghĩa là tỷ lệ lỗi của dịch vụ đã khiến Circuit Breaker chuyển sang OPEN. Nên ghi nhận riêng các ngoại lệ và metric của hai cơ chế để xác định đúng nguyên nhân.

Cần lựa chọn giới hạn đồng thời theo khả năng chịu tải của dịch vụ phụ thuộc và tài nguyên phía gọi. Giới hạn quá cao có thể không bảo vệ được hệ thống; giới hạn quá thấp có thể từ chối lưu lượng hợp lệ ngay cả khi dịch vụ phụ thuộc vẫn khỏe.

## 9. Blocking factory và reactive factory

**Resilience4JCircuitBreakerFactory** phục vụ API blocking. Với ứng dụng reactive, Spring Cloud CircuitBreaker cung cấp factory tương ứng là **ReactiveResilience4JCircuitBreakerFactory**. Cả hai cùng tích hợp Resilience4j nhưng trả về kiểu Circuit Breaker phù hợp với mô hình thực thi.

| Nội dung | Blocking | Reactive |
|---|---|---|
| Factory | **Resilience4JCircuitBreakerFactory** | **ReactiveResilience4JCircuitBreakerFactory** |
| API Spring Cloud | **CircuitBreakerFactory** | **ReactiveCircuitBreakerFactory** |
| Kết quả lời gọi | Giá trị đồng bộ hoặc kiểu trả về đồng bộ | **Mono** hoặc **Flux** |
| Fallback | Hàm trả về giá trị tương ứng | Hàm trả về publisher tương ứng |
| Lưu ý | Timeout và executor cần phù hợp với thao tác blocking | Không gọi **block()** trên reactive pipeline |

Ví dụ reactive sử dụng factory reactive và publisher:

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.ReactiveResilience4JCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final ReactiveResilience4JCircuitBreakerFactory circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryGateway(
            ReactiveResilience4JCircuitBreakerFactory circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Không inject factory blocking rồi ép publisher thành giá trị đồng bộ bằng **block()** trong WebFlux. Làm vậy có thể chặn luồng xử lý reactive, làm giảm khả năng mở rộng và gây nghẽn khi tải tăng.

## 10. Theo dõi trạng thái và hiệu quả bảo vệ

Resilience4j cung cấp sự kiện và metric để quan sát hoạt động của Circuit Breaker. Khi tích hợp với Micrometer, ứng dụng có thể xuất metric về số lời gọi thành công, thất bại, bị từ chối, trạng thái hiện tại và các lần chuyển trạng thái. Tên metric và tag cụ thể phụ thuộc phiên bản, registry và cấu hình tích hợp.

Khi theo dõi, nên phân biệt các nhóm tín hiệu:

| Tín hiệu | Cách diễn giải |
|---|---|
| Số lời gọi thành công và thất bại | Kết quả của những lời gọi đã được cho phép thực thi |
| Số lời gọi không được phép | Lời gọi bị Circuit Breaker từ chối khi OPEN hoặc không được cấp quyền ở trạng thái tương ứng |
| Tỷ lệ lỗi và tỷ lệ lời gọi chậm | Cơ sở để xác định nguyên nhân Circuit Breaker mở |
| Số lần chuyển trạng thái | Cho biết Circuit Breaker ổn định hay liên tục mở và đóng |
| Timeout | Cho biết lời gọi vượt quá thời gian chờ được cấu hình |
| Bulkhead bị từ chối | Cho biết giới hạn đồng thời hoặc hàng đợi đã hết sức chứa |
| Fallback được sử dụng | Cho biết ứng dụng đang phục vụ yêu cầu bằng hành vi dự phòng |

Tên Circuit Breaker nên được giữ nhất quán giữa code, properties, log và dashboard. Ví dụ, nếu service gọi **create("inventory")**, metric và cấu hình nên dùng cùng định danh **inventory**. Không dùng tên có giá trị động theo từng request hoặc người dùng, vì số lượng instance và tag có thể tăng không kiểm soát.

Cần xem trạng thái cùng với tín hiệu của dịch vụ phụ thuộc. OPEN trong thời gian ngắn có thể là hành vi bảo vệ đúng. Nếu Circuit Breaker liên tục chuyển CLOSED → OPEN → HALF_OPEN → OPEN, hãy xem lại sức khỏe dịch vụ, ngưỡng, sliding window, timeout, số probe và thời gian chờ. Nếu số lời gọi bị Bulkhead từ chối tăng nhưng Circuit Breaker vẫn CLOSED, hãy kiểm tra giới hạn đồng thời và năng lực xử lý.

## 11. Những lỗi thường gặp khi phối hợp các thành phần

1. **Dùng một ID cho nhiều dịch vụ có đặc tính khác nhau.** Cấu hình và metric bị trộn lẫn, khiến khó điều chỉnh chính sách cho từng dịch vụ.
2. **Chỉ cấu hình Circuit Breaker mà bỏ qua timeout.** Lời gọi được cho phép vẫn có thể chờ lâu và chiếm tài nguyên nếu tầng client không có giới hạn phù hợp.
3. **Coi BulkheadFullException là lỗi do Circuit Breaker mở.** Hai cơ chế từ chối vì nguyên nhân khác nhau; cần phân loại riêng.
4. **Dùng executor quá nhỏ hoặc dùng chung thiếu kiểm soát.** Tác vụ timeout hoặc lời gọi chậm có thể chiếm luồng và làm các lời gọi khác bị chậm theo.
5. **Đăng ký Customizer trùng lặp cho cùng ID.** Cấu hình bị phân tán ở nhiều bean, khó xác định chính sách hiệu lực.
6. **Định nghĩa cùng tham số ở YAML và Java mà không hiểu thứ tự ưu tiên.** Cấu hình chạy thực tế có thể khác với giá trị người phát triển đang đọc trong một file.
7. **Gắn listener tạo log quá nhiều.** Khi Circuit Breaker OPEN, số lần từ chối lớn có thể làm log tăng đột biến.
8. **Dùng factory blocking trong reactive pipeline.** Việc chặn luồng làm mất lợi ích non-blocking và có thể gây nghẽn event loop.

## 12. Tình huống thực hành

Một ứng dụng đơn hàng gọi hai dịch vụ phụ thuộc: Inventory để kiểm tra số lượng và Catalog để lấy thông tin sản phẩm. Hai dịch vụ có đặc tính khác nhau nên ứng dụng tạo hai Circuit Breaker với định danh riêng.

- **inventory:** cửa sổ theo thời gian 30 giây, tối thiểu 15 lời gọi, ngưỡng lỗi 40%, OPEN 20 giây, hai probe HALF_OPEN và timeout ba giây.
- **catalog:** cửa sổ theo số lượng 20 lời gọi, tối thiểu 10 mẫu, ngưỡng lỗi 50%, OPEN 10 giây, ba probe HALF_OPEN và timeout hai giây.

Factory tạo hai instance theo ID. Circuit Breaker ghi nhận kết quả và quyết định trạng thái. TimeLimiter giới hạn thời gian chờ của thao tác. Bulkhead giới hạn số lời gọi đồng thời để Inventory hoặc Catalog không chiếm hết tài nguyên của ứng dụng. Customizer đăng ký listener chuyển trạng thái; metric được gắn theo tên để dashboard phân biệt hai dịch vụ.

Khi Inventory phản hồi chậm và timeout tăng, Circuit Breaker có thể chuyển OPEN sau khi đủ mẫu và đạt ngưỡng. Các yêu cầu mới bị từ chối sớm và đi vào fallback theo chính sách nghiệp vụ. Nếu Bulkhead đầy trước khi Circuit Breaker mở, lời gọi bị từ chối do giới hạn đồng thời; dashboard cần thể hiện đây là sự kiện khác. Sau thời gian OPEN, số probe giới hạn được gửi đến Inventory. Nếu dịch vụ phục hồi, Circuit Breaker trở lại CLOSED; nếu kết quả vẫn xấu, nó chuyển về OPEN.

Qua tình huống này, hãy xác định được:

- Factory nào tạo instance cho từng dịch vụ và ID nào được dùng.
- Cấu hình nào áp dụng mặc định, cấu hình nào riêng theo ID.
- Thành phần nào tạo timeout, thành phần nào giới hạn đồng thời và thành phần nào quyết định mở mạch.
- Sự kiện hoặc metric nào chứng minh lời gọi bị Circuit Breaker từ chối, timeout hay Bulkhead từ chối.
- Fallback nào được chạy và dữ liệu dự phòng có đáp ứng yêu cầu nghiệp vụ hay không.

## Kết luận

**Resilience4JCircuitBreakerFactory** là điểm tạo Circuit Breaker theo định danh trong tích hợp Spring Cloud CircuitBreaker với Resilience4j cho luồng blocking. Factory phối hợp cấu hình Circuit Breaker, TimeLimiter, Bulkhead và executor; Customizer giúp áp dụng chính sách mặc định, cấu hình riêng theo ID và đăng ký listener cho sự kiện. Ứng dụng reactive sử dụng factory reactive tương ứng. Đặt tên nhất quán, phân biệt rõ trách nhiệm của từng thành phần và theo dõi metric riêng sẽ giúp bảo vệ từng dịch vụ phụ thuộc mà vẫn giữ được khả năng vận hành và điều chỉnh chính sách.
