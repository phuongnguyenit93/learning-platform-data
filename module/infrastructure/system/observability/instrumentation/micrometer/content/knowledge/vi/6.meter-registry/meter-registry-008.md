# Tiêm registry vào thành phần ứng dụng để quản lý quyền sở hữu

`MeterRegistry` là điểm tập trung để đăng ký, tra cứu và xuất các meter của ứng dụng. Trong ứng dụng Java có dependency injection, registry nên được tạo và quản lý ở cấp ứng dụng, sau đó được tiêm vào những thành phần cần ghi nhận số liệu. Cách tổ chức này giúp các component dùng chung một registry, giữ vòng đời meter ổn định và để Spring quản lý cấu hình cũng như vòng đời của registry.

Khi thiết kế instrumentation Micrometer, hãy phân biệt hai trách nhiệm: registry quản lý tập meter đã đăng ký; component ứng dụng sở hữu tham chiếu đến meter mà nó dùng và quyết định thời điểm cập nhật số đo. Component không nên tự tạo một registry riêng cho mỗi lần gọi, cũng không nên đóng registry dùng chung khi hoàn tất một thao tác nghiệp vụ.

## 1. Vai trò và phạm vi sở hữu của MeterRegistry

`MeterRegistry` là abstraction chính của Micrometer. Các loại meter như `Counter`, `Gauge`, `Timer` và `DistributionSummary` được đăng ký vào registry. Registry cung cấp API chung cho mã ứng dụng, còn implementation cụ thể chịu trách nhiệm lưu trữ hoặc xuất dữ liệu theo backend.

Một ứng dụng thường có một registry chính được quản lý trong application context. Spring Boot có thể tự cấu hình registry phù hợp dựa trên các dependency có mặt, ví dụ Prometheus registry khi ứng dụng có dependency tương ứng. Mã nghiệp vụ chỉ cần phụ thuộc vào kiểu `MeterRegistry`, nhờ đó không phải biết dữ liệu sẽ được xuất đến backend nào.

Có thể hiểu ranh giới trách nhiệm như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring application context | Tạo, cấu hình, chia sẻ và quản lý vòng đời bean registry. |
| `MeterRegistry` | Đăng ký và quản lý meter trong phạm vi registry; cung cấp dữ liệu cho backend. |
| Component instrumentation | Khai báo meter cần dùng, giữ tham chiếu đến meter và cập nhật khi sự kiện xảy ra. |
| Component nghiệp vụ | Gọi API nghiệp vụ hoặc instrumentation tại đúng điểm cần đo. |
| Backend giám sát | Thu thập, lưu trữ, truy vấn và hiển thị dữ liệu đã xuất. |

Registry là tài nguyên dùng chung của ứng dụng. Một component có thể đăng ký meter vào registry và component khác có thể tìm lại meter có cùng danh tính trong registry đó. Danh tính được xác định bởi tên và tập tag; vì vậy, nhiều nơi cùng ghi nhận một đại lượng cần thống nhất tên, tag key và tag value.

## 2. Tiêm MeterRegistry bằng constructor injection

Trong Spring, cách rõ ràng nhất là nhận `MeterRegistry` qua constructor. Ví dụ sau tạo một component chuyên quản lý metric đơn hàng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final Counter ordersCreated;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("shop.orders.created")
                .description("Number of successfully created orders")
                .tag("result", "success")
                .register(registry);
    }

    public void recordCreated() {
        ordersCreated.increment();
    }
}
```

Spring tạo `OrderMetrics` và truyền bean `MeterRegistry` đã được cấu hình vào constructor. Component đăng ký counter một lần trong quá trình khởi tạo, giữ tham chiếu bằng field `final`, rồi chỉ tăng counter khi được gọi.

Constructor injection có một số lợi ích:

- Dependency được thể hiện rõ trong chữ ký constructor.
- Component không thể được tạo hợp lệ nếu thiếu registry.
- Field có thể là `final`, giúp tham chiếu không bị thay đổi sau khi khởi tạo.
- Unit test có thể truyền một `SimpleMeterRegistry` trực tiếp mà không cần khởi động toàn bộ Spring context.
- Component không cần tra cứu bean qua `ApplicationContext` hoặc dùng một biến registry toàn cục.

Với một constructor duy nhất, Spring hỗ trợ tự động inject mà không cần đặt `@Autowired` trên constructor.

## 3. Tách instrumentation khỏi logic nghiệp vụ

Không phải class nào cũng cần biết về Micrometer. Có thể gom thao tác đo vào một component nhỏ như `OrderMetrics`, sau đó inject component này vào service nghiệp vụ.

```java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;
    private final OrderMetrics metrics;

    public OrderService(OrderRepository repository, OrderMetrics metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }

    public Order create(CreateOrderCommand command) {
        Order order = repository.save(Order.from(command));
        metrics.recordCreated();
        return order;
    }
}
```

Ở ví dụ này, service chỉ gọi một phương thức có ý nghĩa nghiệp vụ. `OrderMetrics` chịu trách nhiệm chi tiết về tên metric, loại meter và tag. Việc tách này giúp thay đổi cách đo mà không làm rối logic tạo đơn hàng.

Điểm gọi metric cần khớp với ý nghĩa được mô tả. Nếu `shop.orders.created` có nghĩa là số đơn đã lưu thành công, hãy tăng counter sau khi thao tác lưu thành công. Nếu muốn đếm số lần thử tạo đơn, hãy dùng một metric riêng với tên và mô tả thể hiện đúng ý nghĩa đó.

Không nhất thiết phải tạo một class metrics cho mọi class nghiệp vụ. Hãy nhóm metric theo trách nhiệm hoặc phạm vi nghiệp vụ có liên quan. Một component instrumentation nên dễ đọc, có tên meter rõ ràng và có số lượng phương thức vừa đủ để người gọi không phải biết chi tiết registry.

## 4. Đăng ký meter một lần, cập nhật nhiều lần

Thông thường, meter nên được đăng ký trong constructor hoặc một bước khởi tạo của bean, sau đó được giữ lại để tái sử dụng. Không tạo registry và đăng ký lại toàn bộ meter mỗi lần xử lý request.

Ví dụ với timer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class PaymentMetrics {
    private final Timer paymentTimer;

    public PaymentMetrics(MeterRegistry registry) {
        this.paymentTimer = Timer.builder("shop.payment.processing")
                .description("Time spent processing a payment")
                .register(registry);
    }

    public <T> T recordProcessing(java.util.function.Supplier<T> operation) {
        return paymentTimer.record(operation);
    }

    public void recordExternalDuration(long duration, TimeUnit unit) {
        paymentTimer.record(duration, unit);
    }
}
```

`Timer` được tạo một lần và dùng lại cho nhiều lần xử lý. API `record(Supplier)` đo thời gian chạy của thao tác và ghi nhận cả khi thao tác kết thúc bằng exception. Nếu thời gian đã được đo ở một nơi khác, `record(duration, unit)` cho phép ghi nhận thời lượng cùng đơn vị rõ ràng.

Với tag có tập giá trị hữu hạn, có thể đăng ký meter tương ứng theo từng tổ hợp hợp lệ rồi giữ lại tham chiếu. Nếu dùng API tra cứu/đăng ký theo tên và tag tại thời điểm gọi, Micrometer vẫn tra cứu meter theo danh tính trong registry; tuy vậy, phải bảo đảm tập tag không tăng không giới hạn. Tránh gắn ID request, ID người dùng hoặc dữ liệu tự do vào tag.

## 5. Quyền sở hữu và vòng đời của Gauge

Gauge thường đọc một trạng thái hiện tại từ một đối tượng khác. Component đăng ký gauge cần giữ đối tượng trạng thái sống đủ lâu, thường là field của bean cùng vòng đời ứng dụng.

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class QueueMetrics {
    private final AtomicInteger queueDepth = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder("shop.queue.depth", queueDepth, AtomicInteger::get)
                .description("Current number of items waiting in the queue")
                .register(registry);
    }

    public void updateQueueDepth(int depth) {
        queueDepth.set(depth);
    }
}
```

`QueueMetrics` giữ tham chiếu mạnh đến `queueDepth`; gauge đọc giá trị hiện tại từ đối tượng đó khi registry thu thập số liệu. Nếu chỉ truyền một đối tượng tạm thời vào gauge rồi không giữ tham chiếu nào khác, đối tượng có thể bị garbage collector thu hồi và gauge không còn phản ánh trạng thái mong muốn.

Hãy xác định rõ ai cập nhật trạng thái được gauge quan sát. Nếu hàng đợi có API đọc độ dài hiện tại, có thể dùng API đó làm nguồn trạng thái; nếu nhiều luồng cập nhật, chọn cấu trúc dữ liệu an toàn với concurrency. Không tạo gauge mới cho mỗi request.

## 6. Không tự tạo registry trong component nghiệp vụ

Một lỗi thường gặp là component tự tạo `SimpleMeterRegistry` hoặc registry backend riêng:

```java
// Không nên làm trong component ứng dụng đang chạy production.
public class OrderService {
    private final MeterRegistry registry = new SimpleMeterRegistry();
}
```

Registry này không tự động trở thành registry mà Spring Boot đang export. Kết quả là metric có thể được ghi vào một registry cục bộ nhưng không xuất hiện ở endpoint giám sát mà nhóm vận hành đang scrape. Nếu mỗi component tạo một registry, ứng dụng còn có nhiều tập meter riêng, khó cấu hình và khó quản lý vòng đời.

Hãy inject registry do application context quản lý:

```java
@Component
public class OrderMetrics {
    private final Counter ordersCreated;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = registry.counter("shop.orders.created");
    }
}
```

`SimpleMeterRegistry` vẫn rất hữu ích trong unit test hoặc ví dụ độc lập. Điểm khác biệt là trong test, test sở hữu registry và đóng nó sau khi dùng; trong ứng dụng Spring Boot, registry dùng chung được quản lý ở cấp context.

## 7. Vòng đời của registry trong Spring Boot

Khi có Actuator và dependency registry tương ứng, Spring Boot có thể tự cấu hình `MeterRegistry` và tích hợp các meter với endpoint hoặc backend. Component chỉ cần inject abstraction.

Ví dụ cấu hình dependency Maven cho ứng dụng xuất metrics qua Prometheus:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Phiên bản nên được quản lý theo Spring Boot dependency management. Khi ứng dụng khởi động, Spring tạo application context, cấu hình registry phù hợp với classpath và cung cấp bean để các component inject. Khi context dừng, lifecycle của bean do Spring quản lý.

Không nên gọi `close()` trên registry được inject vào một component nghiệp vụ. Đó là tài nguyên dùng chung; đóng nó từ một service có thể làm ảnh hưởng đến các component khác và luồng export metrics. Nếu ứng dụng tự tạo một registry riêng cho một mục đích rõ ràng, hãy đăng ký nó như bean hoặc quản lý lifecycle một cách tường minh, bao gồm cả việc đóng tài nguyên khi ứng dụng dừng.

### 7.1. Cấu hình chung cho registry

Các tag chung như tên ứng dụng hoặc môi trường có thể được cấu hình ở cấp registry thay vì lặp lại ở từng meter. Với Spring Boot, có thể dùng `MeterRegistryCustomizer`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsCommonConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
                "application", "order-service",
                "environment", "production"
        );
    }
}
```

Common tags được áp dụng ở cấp registry và trở thành chiều phân loại chung trong dữ liệu xuất. Hãy giữ giá trị có cardinality thấp, ổn định và phù hợp với phạm vi registry. Không đặt request ID hoặc user ID làm common tag.

Thứ tự khởi tạo giữa customizer và đăng ký meter cần được Spring Boot quản lý theo cơ chế auto-configuration. Nếu tự tạo registry hoặc tự đăng ký meter trước khi customizer được áp dụng, hãy kiểm tra cấu hình thực tế để bảo đảm mọi meter nhận cùng bộ tag chung.

## 8. Khi nào cần CompositeMeterRegistry?

`CompositeMeterRegistry` cho phép một meter được ghi nhận qua registry tổng hợp và chuyển tiếp đến một hoặc nhiều registry con. Điều này hữu ích khi cùng một ứng dụng cần xuất metrics đến nhiều backend hoặc kết hợp registry trong một cấu hình có chủ đích.

Ví dụ minh họa độc lập:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

CompositeMeterRegistry composite = new CompositeMeterRegistry();
SimpleMeterRegistry localRegistry = new SimpleMeterRegistry();

composite.add(localRegistry);

Counter counter = composite.counter("shop.orders.created");
counter.increment();
```

Trong ứng dụng Spring Boot, không nên tự tạo thêm composite nếu auto-configuration đã cung cấp một registry phù hợp. Hãy xác định rõ ai tạo composite, ai thêm registry con và ai đóng chúng. Cấu hình nhiều registry không có kế hoạch có thể dẫn đến dữ liệu xuất trùng hoặc lifecycle khó kiểm soát.

Mã nghiệp vụ vẫn nên nhận `MeterRegistry`, không cần phụ thuộc `CompositeMeterRegistry` trừ khi component thực sự quản lý chức năng tổng hợp registry.

## 9. Kiểm thử component được tiêm registry

Vì `OrderMetrics` nhận registry qua constructor, unit test có thể tạo registry nhẹ rồi inject trực tiếp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderMetricsTest {
    @Test
    void recordsCreatedOrdersInInjectedRegistry() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new OrderMetrics(registry);

            metrics.recordCreated();
            metrics.recordCreated();

            assertThat(registry.get("shop.orders.created")
                    .counter().count()).isEqualTo(2.0);
        }
    }
}
```

Test kiểm tra đúng registry được truyền vào component nhận số liệu. `try-with-resources` đóng registry sau khi test kết thúc, vì test tạo và sở hữu nó.

Với Spring integration test, có thể inject registry trong test context và kiểm tra meter sau khi gọi service. Khi làm vậy, không tự đóng registry dùng chung của Spring. Hãy để context quản lý lifecycle và chỉ kiểm tra meter được tạo trong registry đó.

Một số kiểm tra nên có:

- Component khởi tạo được khi registry được inject.
- Meter được đăng ký với đúng tên, loại và tag.
- Gọi phương thức instrumentation làm số đo thay đổi như mong đợi.
- Hai component dùng cùng registry và cùng danh tính sẽ ghi nhận vào cùng meter.
- Gauge vẫn đọc được trạng thái vì component giữ đối tượng nguồn sống đủ lâu.
- Không có registry riêng bị tạo ngoài ý muốn trong đường chạy production.

## 10. Những lỗi về ownership và lifecycle thường gặp

- **Tạo registry theo request:** mỗi request tạo một registry mới khiến meter bị phân tán và không được backend chính thu thập.
- **Tạo registry trong từng service:** các component không còn dùng chung tập meter, cấu hình export cũng không nhất quán.
- **Đóng registry được inject:** một component đóng tài nguyên dùng chung có thể ảnh hưởng toàn ứng dụng.
- **Dùng static global registry:** dependency bị ẩn, khó kiểm thử và dễ gây rò rỉ trạng thái giữa các application context hoặc test.
- **Đăng ký meter lặp lại ở nhiều nơi với tên/tag khác nhau:** dữ liệu bị chia thành nhiều chuỗi thời gian dù nhóm phát triển tưởng đang đo cùng đại lượng.
- **Không giữ đối tượng cho gauge:** gauge có thể không còn tham chiếu đến trạng thái cần đo.
- **Đưa logic backend vào service nghiệp vụ:** thay đổi registry làm lan rộng thay đổi qua nhiều lớp ứng dụng.
- **Cấu hình nhiều registry không rõ chủ sở hữu:** có thể xuất trùng, thiếu registry con hoặc đóng sai thời điểm.

## 11. Checklist thiết kế MeterRegistry

- [ ] Ứng dụng có registry được tạo và quản lý ở cấp application context.
- [ ] Component nhận `MeterRegistry` qua constructor injection.
- [ ] Meter được đăng ký một lần khi component khởi tạo và được tái sử dụng.
- [ ] Component chỉ cập nhật meter mà nó phụ trách; không đóng registry dùng chung.
- [ ] Logic nghiệp vụ gọi API instrumentation có ý nghĩa, không cần biết backend cụ thể.
- [ ] Gauge có đối tượng trạng thái được giữ sống và cập nhật an toàn.
- [ ] Tag có tập giá trị hữu hạn và được chuẩn hóa.
- [ ] Registry riêng hoặc composite chỉ được tạo khi có mục đích rõ và lifecycle được quản lý.
- [ ] Unit test inject `SimpleMeterRegistry` và đóng registry do test tạo.
- [ ] Integration test để Spring quản lý registry trong context.

Khi tiêm `MeterRegistry` đúng ranh giới, ứng dụng có một nơi thống nhất để quản lý meter, còn từng component chỉ chịu trách nhiệm về phép đo mà nó tạo ra. Cách tổ chức này làm cho instrumentation dễ kiểm thử, dễ thay backend và dễ duy trì trong suốt vòng đời ứng dụng.
