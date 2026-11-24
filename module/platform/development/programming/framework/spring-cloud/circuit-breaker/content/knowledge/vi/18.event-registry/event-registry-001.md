# CircuitBreakerRegistry và vòng đời các instance có tên

Resilience4j quản lý các circuit breaker thông qua `CircuitBreakerRegistry`. Registry là nơi tạo, tra cứu và quản lý các instance theo tên. Tên instance xác định một state machine cụ thể cùng sliding window, bộ đếm, trạng thái `CLOSED`/`OPEN`/`HALF_OPEN` và các listener sự kiện của nó.

Điểm quan trọng là **cùng tên trong cùng một registry đại diện cho cùng một instance**. Những lời gọi dùng chung instance sẽ chia sẻ trạng thái và số liệu. Hai instance khác tên có thể dùng cùng một cấu hình nhưng vẫn có state machine độc lập. Vì vậy, tên cần phản ánh ranh giới lỗi và chính sách bảo vệ của dependency, còn registry cần có vòng đời phù hợp với ứng dụng.

## Registry quản lý instance như thế nào

Có thể tạo registry trực tiếp bằng API Resilience4j:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import java.time.Duration;

CircuitBreakerConfig defaultConfig = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .slowCallRateThreshold(50)
        .slowCallDurationThreshold(Duration.ofSeconds(2))
        .waitDurationInOpenState(Duration.ofSeconds(10))
        .permittedNumberOfCallsInHalfOpenState(3)
        .build();

CircuitBreakerRegistry registry =
        CircuitBreakerRegistry.of(defaultConfig);

CircuitBreaker catalogBreaker = registry.circuitBreaker("catalog");
CircuitBreaker pricingBreaker = registry.circuitBreaker("pricing");
```

Registry giữ các instance theo tên. `catalogBreaker` và `pricingBreaker` là hai state machine độc lập, dù cùng được tạo từ cấu hình mặc định. Nếu `catalog` chuyển sang `OPEN`, trạng thái đó không tự làm `pricing` chuyển sang `OPEN`.

Khi yêu cầu cùng tên được tra cứu lại trên cùng registry, registry trả instance đã đăng ký thay vì tạo một state machine mới:

```java
CircuitBreaker first = registry.circuitBreaker("catalog");
CircuitBreaker again = registry.circuitBreaker("catalog");

assert first == again;
```

Do đó, không gọi `CircuitBreakerRegistry.ofDefaults()` hoặc tạo registry mới trong mỗi request. Làm như vậy sẽ tạo một tập state machine mới liên tục; các request không còn chia sẻ lịch sử lỗi và breaker khó có đủ dữ liệu để bảo vệ dependency.

## Tách cấu hình dùng chung và instance cụ thể

Registry cho phép đăng ký một cấu hình có tên rồi dùng cấu hình đó để tạo nhiều instance. Các instance có thể dùng chung threshold nhưng giữ trạng thái độc lập:

```java
CircuitBreakerConfig remoteReadConfig = CircuitBreakerConfig.custom()
        .slidingWindowSize(30)
        .minimumNumberOfCalls(15)
        .failureRateThreshold(40)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .build();

CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();
registry.addConfiguration("remoteRead", remoteReadConfig);

CircuitBreaker catalog = registry.circuitBreaker("catalog", "remoteRead");
CircuitBreaker pricing = registry.circuitBreaker("pricing", "remoteRead");
```

`remoteRead` là tên cấu hình; `catalog` và `pricing` là tên instance. Khi catalog lỗi nhiều, breaker catalog có thể mở trong khi breaker pricing vẫn đóng. Đây là khác biệt giữa **chia sẻ chính sách cấu hình** và **chia sẻ trạng thái**.

Chỉ nên dùng chung cấu hình khi các dependency có đặc tính tương tự về latency, tỷ lệ lỗi chấp nhận được và ngân sách phục hồi. Nếu một dependency thường phản hồi trong 50 ms còn dependency khác có thời gian phản hồi bình thường vài giây, chúng có thể cần `slowCallDurationThreshold` khác nhau dù cùng dùng một số thiết lập chung.

## Chọn tên instance theo ranh giới lỗi

Tên instance nên ổn định, có ý nghĩa và có số lượng giới hạn. Ví dụ:

| Tên instance | Phạm vi được bảo vệ | Lý do tách riêng |
|---|---|---|
| `catalog` | Lời gọi đọc catalog | Có thể có latency và ngưỡng lỗi riêng |
| `pricing` | Lời gọi tính giá | Chính sách timeout và mức độ quan trọng khác catalog |
| `payment-authorize` | Lệnh xác thực thanh toán | Cần theo dõi một failure domain nhạy cảm |

Nếu nhiều phương thức cùng gọi một dependency và cần chia sẻ một chính sách, chúng có thể dùng cùng tên. Khi đó, lỗi ở một đường gọi có thể góp phần làm breaker mở cho các đường gọi khác cùng instance. Đây là hành vi mong muốn khi chúng cùng phụ thuộc vào một hệ thống và cùng chịu một failure domain.

Nếu các endpoint có năng lực hoặc yêu cầu bảo vệ khác nhau, dùng instance riêng để thống kê không trộn lẫn. Tránh tạo tên từ `userId`, `requestId`, product ID hoặc dữ liệu tùy ý của caller. Mỗi tên mới có thể tạo thêm instance, sliding window, event stream và metric; tên có cardinality không giới hạn sẽ làm tăng bộ nhớ và số chuỗi metric.

## Vòng đời của registry và breaker

Trong một ứng dụng Spring, registry thường nên là một bean singleton có vòng đời gắn với application context. Các service lấy instance theo tên từ registry dùng chung. Một vòng đời điển hình gồm:

1. **Khởi động ứng dụng:** cấu hình mặc định và cấu hình có tên được đăng ký; registry được tạo một lần.
2. **Khởi tạo service:** service lấy instance như `catalog` từ registry và giữ tham chiếu dùng lại.
3. **Trong quá trình chạy:** mọi lời gọi thuộc cùng ranh giới lỗi dùng instance đó; breaker tích lũy kết quả và chuyển trạng thái.
4. **Theo dõi:** listener nhận sự kiện chuyển trạng thái, lỗi, thành công hoặc lời gọi bị từ chối; metric phản ánh số liệu tổng hợp.
5. **Dừng ứng dụng:** Spring đóng application context và giải phóng bean/tài nguyên theo vòng đời của chúng.

Ví dụ cấu hình registry như bean:

```java
@Configuration
public class CircuitBreakerRegistryConfiguration {

    @Bean
    public CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        return CircuitBreakerRegistry.of(config);
    }
}
```

Service có thể nhận registry qua constructor và lấy instance một lần:

```java
@Service
public class CatalogService {

    private final CircuitBreaker catalogBreaker;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerRegistry registry,
            CatalogClient catalogClient) {
        this.catalogBreaker = registry.circuitBreaker("catalog");
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        return catalogBreaker.executeSupplier(
                () -> catalogClient.findProduct(productId)
        );
    }
}
```

Ví dụ trên minh họa việc tự tạo registry bean. Nếu ứng dụng đã dùng Resilience4j Spring Boot starter và registry được auto-configure từ properties, hãy inject registry do starter cung cấp thay vì khai báo thêm một registry cạnh tranh. Cần chọn một nguồn cấu hình nhất quán để service, annotation và metric cùng quan sát đúng instance.

## Cấu hình instance bằng application.yml

Với Resilience4j Spring Boot integration, có thể khai báo cấu hình dùng chung dưới `configs` và instance dưới `instances`:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remoteRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        slowCallRateThreshold: 50
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 15s
    instances:
      catalog:
        baseConfig: remoteRead
      pricing:
        baseConfig: remoteRead
      payment-authorize:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
```

`catalog` và `pricing` kế thừa cấu hình `remoteRead` nhưng vẫn có instance riêng. `payment-authorize` khai báo chính sách riêng vì lệnh thanh toán có thể cần ngưỡng và thời gian phục hồi khác. Khi sử dụng properties, registry do Spring Boot integration tạo sẽ nhận cấu hình theo phiên bản Resilience4j đang dùng.

Đừng nhầm cấu hình registry Resilience4j với cấu hình `CircuitBreakerFactory` của Spring Cloud Circuit Breaker. Factory là abstraction của Spring Cloud; nó nhận ID và chuyển tới backend tương ứng. Registry là API quản lý instance của Resilience4j. Nếu service dùng `CircuitBreakerFactory.create("catalog")`, hãy để backend/factory quản lý instance theo cơ chế của nó. Nếu service inject `CircuitBreakerRegistry` trực tiếp, hãy dùng registry đó xuyên suốt đường gọi. Không bọc cùng một thao tác bằng cả hai cách chỉ để tạo thêm lớp bảo vệ.

## Tra cứu và quan sát instance

Registry cho phép liệt kê các breaker đã đăng ký. Điều này hữu ích khi kiểm tra số instance đang tồn tại hoặc xây dựng màn hình vận hành:

```java
registry.getAllCircuitBreakers().forEach(circuitBreaker -> {
    log.info("Circuit breaker {} is {}",
            circuitBreaker.getName(),
            circuitBreaker.getState());
});
```

Không nên gọi thao tác liệt kê toàn bộ instance trong mỗi request. Dùng nó cho endpoint quản trị, kiểm tra chẩn đoán hoặc tác vụ quan sát có tần suất phù hợp. Trạng thái tại thời điểm đọc chỉ là snapshot; nó có thể thay đổi ngay sau đó khi request khác hoàn tất.

Có thể đăng ký listener trên event publisher của một instance:

```java
CircuitBreaker catalog = registry.circuitBreaker("catalog");

catalog.getEventPublisher()
        .onStateTransition(event -> log.info(
                "{} transitioned: {}",
                event.getCircuitBreakerName(),
                event.getStateTransition()))
        .onCallNotPermitted(event -> log.warn(
                "{} rejected a call because it is not permitted",
                event.getCircuitBreakerName()))
        .onError(event -> log.warn(
                "{} recorded a failed call",
                event.getCircuitBreakerName(),
                event.getThrowable()));
```

Đăng ký listener một lần khi tạo bean hoặc khởi tạo service, không đăng ký lại trong mỗi lần gọi phương thức. Giữ callback nhẹ và không thực hiện I/O chậm trực tiếp trong luồng xử lý request. Nếu cần gửi thông báo hoặc lưu audit, hãy chuyển sự kiện sang cơ chế xử lý bất đồng bộ có giới hạn.

Sự kiện mô tả điều vừa xảy ra, chẳng hạn một lần chuyển từ `CLOSED` sang `OPEN`. Metric cung cấp số liệu tổng hợp như số lời gọi thành công, lỗi, chậm hoặc bị từ chối. Hai nguồn dữ liệu bổ sung cho nhau: event giúp dựng dòng thời gian, metric giúp đánh giá xu hướng.

## Xóa hoặc thay thế instance

Registry có thể hỗ trợ loại bỏ instance theo tên. Đây là thao tác vòng đời, không phải cách reset breaker sau mỗi request. Trước khi xóa một instance, cần biết service nào đang giữ tham chiếu tới nó.

Khi một instance bị loại khỏi registry, các tham chiếu Java đã được lấy trước đó không tự biến mất. Service đang giữ tham chiếu có thể tiếp tục gọi instance cũ, trong khi lần tra cứu mới theo cùng tên có thể tạo instance khác. Hệ thống lúc đó có thể tồn tại hai state machine cùng tên ở các tham chiếu khác nhau và metric/event trở nên khó giải thích.

Vì vậy:

- Không xóa instance đang được service sử dụng chỉ để làm breaker chuyển về `CLOSED`.
- Dùng API reset/state transition được hỗ trợ nếu mục tiêu là khôi phục trạng thái, sau khi đánh giá tác động vận hành.
- Nếu cần thay đổi cấu hình, dùng cơ chế cập nhật cấu hình được phiên bản Resilience4j hỗ trợ hoặc triển khai quy trình thay thế có phối hợp; bảo đảm mọi consumer chuyển sang cùng instance mới.
- Chỉ xóa instance khi đã ngừng sử dụng, không còn request đang chạy và đã có kế hoạch xử lý listener, metric cùng tham chiếu cũ.

Một registry trong JVM không chia sẻ trạng thái với registry của replica khác. Nếu ứng dụng chạy bốn pod, mỗi pod có instance `catalog` riêng, sliding window và trạng thái breaker riêng. Một pod có thể đang `OPEN` trong khi pod khác vẫn `CLOSED`. Đây là cơ chế bảo vệ cục bộ; nó không phải một state machine phân tán hoặc một bộ điều phối trạng thái toàn cluster.

## Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo registry trong mỗi request | Lịch sử lỗi bị chia nhỏ, breaker không tích lũy đủ mẫu | Dùng registry singleton theo application context |
| Tạo tên instance từ request/user ID | Số instance và metric tăng không giới hạn | Dùng tên cố định theo dependency/failure domain |
| Dùng chung một instance cho dependency độc lập | Lỗi của dependency A có thể làm ngắt lời gọi dependency B | Tách instance theo ranh giới lỗi |
| Tạo nhiều instance cùng tên trong nhiều registry | Các state machine không chia sẻ trạng thái dù có cùng tên | Dùng một registry được quản lý thống nhất |
| Xóa registry entry nhưng service vẫn giữ tham chiếu cũ | Cùng tên có thể tồn tại ở nhiều instance khác nhau | Phối hợp vòng đời và cập nhật consumer |
| Đăng ký event listener mỗi request | Callback bị gọi lặp và tiêu tốn tài nguyên | Đăng ký listener một lần trong lúc khởi tạo |
| Cho rằng registry đồng bộ giữa các pod | Chẩn đoán sai khi các replica có trạng thái khác nhau | Quan sát trạng thái theo từng instance/replica |

## Kiểm thử registry và vòng đời

Một bộ kiểm thử nên xác nhận identity của instance, tính độc lập của state machine và cách listener được đăng ký:

1. Lấy `catalog` hai lần từ cùng registry và xác nhận hai tham chiếu trỏ tới cùng instance.
2. Lấy `catalog` và `pricing`; xác nhận hai instance độc lập dù dùng chung cấu hình.
3. Gây lỗi đủ số lượng trên `catalog`; xác nhận `catalog` chuyển trạng thái theo threshold và `pricing` không bị ảnh hưởng.
4. Đăng ký listener một lần; xác nhận event chuyển trạng thái được nhận đúng số lần dự kiến.
5. Kiểm tra danh sách registry sau khi tạo instance để xác nhận tên và số lượng đúng.
6. Nếu thử remove/recreate, xác nhận service không còn sử dụng tham chiếu cũ trước khi chuyển sang instance mới.
7. Chạy nhiều replica trong integration test nếu cần xác minh trạng thái là cục bộ từng JVM.

Ví dụ kiểm tra identity và sự độc lập:

```java
@Test
void registryReusesNamedInstanceButSeparatesDifferentNames() {
    CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

    CircuitBreaker firstCatalog = registry.circuitBreaker("catalog");
    CircuitBreaker secondCatalog = registry.circuitBreaker("catalog");
    CircuitBreaker pricing = registry.circuitBreaker("pricing");

    assertSame(firstCatalog, secondCatalog);
    assertNotSame(firstCatalog, pricing);
    assertEquals(2, registry.getAllCircuitBreakers().size());
}
```

Khi kiểm tra chuyển trạng thái, cấu hình `minimumNumberOfCalls` và threshold phù hợp để test có thể kích hoạt chuyển trạng thái một cách xác định. Tránh dựa vào thời gian sleep dài; dùng cấu hình nhỏ trong test và quan sát event hoặc state trực tiếp.

## Nguyên tắc vận hành

Hãy xem registry là kho instance sống trong phạm vi một ứng dụng, còn tên instance là định danh của một ranh giới lỗi. Tạo registry một lần, tái sử dụng instance theo tên, chia sẻ cấu hình khi chính sách giống nhau nhưng tách state machine khi dependency độc lập. Theo dõi event và metric từ cùng instance mà service thực sự sử dụng; thay đổi hoặc xóa instance phải đi kèm kế hoạch cập nhật mọi tham chiếu. Cách quản lý này giúp `CLOSED`, `OPEN` và `HALF_OPEN` phản ánh lịch sử của đúng dependency và giữ hành vi bảo vệ ổn định trong suốt vòng đời ứng dụng.
