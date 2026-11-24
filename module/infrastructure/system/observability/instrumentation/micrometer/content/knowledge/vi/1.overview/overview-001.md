# Micrometer là gì và giải quyết bài toán gắn phép đo cho ứng dụng JVM

## Tổng quan

Một ứng dụng Java có thể vẫn trả về HTTP 200 trong khi thời gian xử lý tăng dần, hàng đợi công việc phình to hoặc số lần gọi cơ sở dữ liệu lỗi tăng lên. Log giúp điều tra từng sự kiện và trace cho biết một yêu cầu đi qua những thành phần nào; metrics bổ sung góc nhìn định lượng theo thời gian: có bao nhiêu yêu cầu, xử lý mất bao lâu, hiện có bao nhiêu tác vụ đang chờ và tài nguyên đang được sử dụng ra sao.

**Micrometer** là thư viện instrumentation metrics cho JVM. Thư viện cung cấp một API đo lường thống nhất để mã ứng dụng ghi nhận số liệu, sau đó chuyển các số liệu đó qua registry tương ứng để xuất đến hệ thống giám sát như Prometheus, Datadog, Graphite hoặc một backend được hỗ trợ khác. Nhờ vậy, phần mã nghiệp vụ có thể tập trung vào việc đo đúng điều cần đo, còn cách biểu diễn và chuyển dữ liệu đến backend do registry đảm nhiệm.

Micrometer thường được dùng cùng Spring Boot Actuator. Spring Boot có thể tự cấu hình registry khi dependency phù hợp xuất hiện trên classpath, đồng thời cung cấp các metrics nền tảng cho HTTP server, JVM, bộ nhớ, garbage collection, thread và một số tích hợp khác. Ứng dụng vẫn có thể bổ sung metrics nghiệp vụ như số đơn hàng được tạo, số lần thanh toán thất bại hoặc kích thước payload.

Sau bài này, bạn có thể:

- Giải thích vai trò của Micrometer và các thành phần `Meter`, `MeterRegistry`.
- Chọn `Counter`, `Gauge`, `Timer` hoặc `DistributionSummary` theo ý nghĩa dữ liệu.
- Gắn metrics vào ứng dụng Java và Spring Boot.
- Chọn tag có cardinality hữu hạn, tránh tạo quá nhiều time series.
- Kiểm thử instrumentation và đọc các chỉ số để hiểu tình trạng vận hành.

## Bài toán mà Micrometer giải quyết

Giả sử một dịch vụ thương mại điện tử cần theo dõi số đơn hàng, thời gian tạo đơn, số tác vụ đang chờ xử lý và kích thước yêu cầu gửi đến dịch vụ thanh toán. Nếu tự xây dựng một lớp đo lường riêng cho từng backend, mã ứng dụng sẽ bị gắn chặt với giao thức và mô hình dữ liệu của hệ thống giám sát đó. Khi thay backend, nhóm phát triển phải sửa nhiều vị trí trong mã nghiệp vụ.

Micrometer giải quyết vấn đề này bằng cách tách **instrumentation** khỏi **export**:

1. Mã ứng dụng gọi API Micrometer để tăng bộ đếm, ghi nhận thời gian hoặc quan sát một giá trị hiện tại.
2. Một `MeterRegistry` quản lý các meter và cung cấp cách đăng ký, truy xuất, cấu hình chúng.
3. Registry dành cho backend cụ thể chuyển meter sang định dạng mà hệ thống giám sát hiểu được.
4. Backend thu thập, lưu trữ, truy vấn và hiển thị dữ liệu; nhóm vận hành xây dựng dashboard và cảnh báo từ đó.

Ví dụ, mã nghiệp vụ có thể ghi nhận `business.orders.created`. Khi ứng dụng chạy với Prometheus registry, meter được biểu diễn theo quy ước của Prometheus; khi dùng registry khác, cùng phép đo có thể được ánh xạ sang quy ước tương ứng. Tên hiển thị ở backend có thể khác do quy tắc chuẩn hóa tên, nhưng ý nghĩa của phép đo vẫn do ứng dụng xác định.

Micrometer cũng tạo ra một ngôn ngữ đo lường chung trong ứng dụng. Thay vì mỗi nhóm tự đặt cách đếm và đo thời gian, nhóm có thể thống nhất tên metric, đơn vị, tag và ý nghĩa của từng số liệu. Sự nhất quán này giúp dashboard, cảnh báo và việc so sánh giữa các phiên bản trở nên đáng tin cậy hơn.

## Các khái niệm cốt lõi

### Meter và MeterRegistry

**Meter** là một phép đo được đăng ký trong ứng dụng. Một meter thường có các thông tin nhận dạng và mô tả:

- **Name**: tên metric, chẳng hạn `business.orders.created`.
- **Tags**: các cặp khóa–giá trị dùng để phân tách phép đo, chẳng hạn `channel=web` hoặc `outcome=success`.
- **Type**: loại phép đo như counter, gauge hoặc timer.
- **Base unit**: đơn vị cơ sở nếu phù hợp, ví dụ `seconds`, `bytes` hoặc `items`.
- **Description**: mô tả ý nghĩa của metric.

Trong Micrometer, `MeterRegistry` là điểm đăng ký và quản lý meter. Mã ứng dụng thường nhận registry qua constructor injection thay vì tự tạo registry trong từng lớp. Cách này giúp cấu hình registry tập trung, dễ thay backend và dễ dùng registry giả lập trong kiểm thử.

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final MeterRegistry meterRegistry;

    public OrderService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }
}
```

Trong ví dụ trên, Spring cung cấp bean `MeterRegistry` đã được cấu hình. Với ứng dụng Java không dùng Spring, bạn có thể tự tạo một registry phù hợp, chẳng hạn `SimpleMeterRegistry` cho một chương trình nhỏ hoặc kiểm thử.

### Tên metric và tag

Tên metric nên mô tả đại lượng đang đo, có quy ước nhất quán và tránh đưa giá trị biến thiên vào tên. Ví dụ:

- `business.orders.created`: số đơn hàng được tạo.
- `business.orders.create`: thời gian xử lý thao tác tạo đơn.
- `business.orders.items`: phân bố số mặt hàng trong đơn.
- `worker.queue.size`: số tác vụ hiện đang chờ.

Micrometer thường dùng tên dạng phân cấp với dấu chấm. Registry có thể chuyển tên này sang quy ước riêng của backend, chẳng hạn dấu chấm thành dấu gạch dưới trong tên metric Prometheus.

Tag bổ sung chiều phân tích mà không cần tạo một tên metric mới cho từng trường hợp. Ví dụ, `business.orders.created` có thể có tag `channel=web` và `channel=mobile`. Khi truy vấn, bạn có thể xem tổng số đơn hoặc lọc theo từng kênh.

Tag phải có tập giá trị hữu hạn và có ý nghĩa vận hành. Không dùng `userId`, `orderId`, email, mã giao dịch, URL chứa ID cụ thể, nội dung exception hoặc câu SQL làm tag. Những giá trị này có thể tạo ra hàng nghìn hoặc hàng triệu chuỗi time series riêng biệt. Vấn đề này được gọi là **cardinality cao** và sẽ được phân tích ở phần sau.

## Chọn loại meter phù hợp

Micrometer cung cấp nhiều loại meter. Bốn loại thường gặp nhất là `Counter`, `Gauge`, `Timer` và `DistributionSummary`.

| Loại meter | Ý nghĩa | Dùng khi | Ví dụ |
|---|---|---|---|
| `Counter` | Tổng số sự kiện tăng dần | Đếm sự kiện đã xảy ra | Số đơn hàng tạo thành công |
| `Gauge` | Giá trị hiện tại tại thời điểm lấy mẫu | Quan sát trạng thái có thể tăng hoặc giảm | Số tác vụ trong hàng đợi |
| `Timer` | Số lần thực hiện và phân bố thời gian | Đo thời lượng thao tác | Thời gian xử lý thanh toán |
| `DistributionSummary` | Số lần ghi nhận và phân bố giá trị số | Đo đại lượng không phải thời gian | Kích thước payload, số item mỗi đơn |

### Counter: đếm sự kiện tích lũy

`Counter` biểu diễn một giá trị chỉ tăng. Mỗi lần một sự kiện xảy ra, gọi `increment()` hoặc tăng theo một lượng dương. Ví dụ:

```java
Counter orderCreated = Counter.builder("business.orders.created")
        .description("Tổng số đơn hàng được tạo")
        .tag("channel", "web")
        .register(meterRegistry);

orderCreated.increment();
```

Counter thích hợp để đếm số đơn hàng được tạo, số lần gửi email, số lần xử lý thông điệp hoặc số lỗi xảy ra. Không dùng counter để mô tả một giá trị có thể giảm, như số kết nối đang mở hoặc độ dài hàng đợi. Những đại lượng đó cần một gauge.

Counter thường có ý nghĩa nhất khi xem tốc độ thay đổi theo thời gian. Tổng số lần gọi kể từ lúc tiến trình khởi động có thể hữu ích, nhưng người vận hành thường quan tâm số lần gọi mỗi giây hoặc mỗi phút. Backend có thể tính rate từ chuỗi giá trị counter. Vì counter có thể bắt đầu lại khi tiến trình khởi động lại, dashboard nên dùng phép tính rate hoặc increase phù hợp với backend thay vì giả định giá trị tuyệt đối luôn tăng xuyên suốt mọi lần khởi động.

### Gauge: quan sát giá trị hiện tại

`Gauge` lấy mẫu một giá trị tại thời điểm registry hoặc backend đọc metrics. Giá trị có thể tăng hoặc giảm. Ví dụ, số tác vụ đang nằm trong hàng đợi:

```java
AtomicInteger queueSize = new AtomicInteger();

Gauge.builder("worker.queue.size", queueSize, AtomicInteger::get)
        .description("Số tác vụ hiện đang chờ xử lý")
        .register(meterRegistry);
```

Khi tác vụ được thêm vào hàng đợi, tăng `queueSize`; khi lấy tác vụ ra, giảm giá trị. Gauge chỉ quan sát giá trị tại thời điểm được lấy mẫu, vì vậy một thay đổi rất ngắn giữa hai lần scrape có thể không xuất hiện trong dữ liệu.

Micrometer gauge thường giữ tham chiếu yếu đến đối tượng được quan sát. Vì thế, ứng dụng phải giữ một tham chiếu mạnh đến đối tượng đó trong suốt thời gian cần đo. Nếu đối tượng bị garbage collector thu hồi, gauge có thể không còn cung cấp giá trị hữu ích. Hãy đăng ký gauge cho một đối tượng có vòng đời ổn định, chẳng hạn một trường của bean quản lý hàng đợi.

Không dùng gauge để đếm tổng số sự kiện đã xảy ra. Nếu cần đếm số lần tác vụ được thêm vào hàng đợi, dùng counter; nếu cần biết hiện có bao nhiêu tác vụ đang chờ, dùng gauge.

### Timer: đo thời gian thực hiện

`Timer` được thiết kế để ghi nhận thời lượng. Nó theo dõi số lần ghi nhận và tổng thời gian, đồng thời có thể cung cấp các thống kê phân bố như max, percentile hoặc histogram tùy cấu hình và registry. Ví dụ đơn giản:

```java
Timer createOrderTimer = Timer.builder("business.orders.create")
        .description("Thời gian xử lý thao tác tạo đơn")
        .tag("outcome", "success")
        .register(meterRegistry);

createOrderTimer.record(() -> orderRepository.save(order));
```

Đo thủ công với `Timer.Sample` hữu ích khi cần xác định tag kết quả sau khi thao tác kết thúc:

```java
Timer.Sample sample = Timer.start(meterRegistry);
String outcome = "success";

try {
    orderService.create(command);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(meterRegistry.timer(
            "business.orders.create",
            "outcome", outcome));
}
```

Trong ví dụ, `outcome` chỉ nhận hai giá trị hữu hạn là `success` và `error`. `finally` bảo đảm timer được dừng kể cả khi thao tác ném exception. Nếu cần phân loại lỗi chi tiết hơn, hãy dùng một nhóm nhỏ các loại lỗi ổn định đã được thống nhất trước.

Các số liệu thời gian giúp trả lời nhiều câu hỏi khác nhau:

- **Count**: có bao nhiêu lần thao tác được ghi nhận?
- **Total time**: tổng thời gian đã tiêu tốn cho các lần thao tác là bao nhiêu?
- **Mean**: thời gian trung bình là bao nhiêu?
- **Percentile**: 95% thao tác hoàn thành trong thời gian bao lâu (p95)?
- **Histogram**: có bao nhiêu thao tác nằm trong từng khoảng thời gian?

Thời gian trung bình có thể che khuất một nhóm yêu cầu rất chậm. Khi đánh giá trải nghiệm người dùng, p95 hoặc p99 thường giúp phát hiện phần đuôi chậm của phân bố. Percentile phía ứng dụng và histogram phía backend có cách tính, chi phí và khả năng tổng hợp khác nhau; hãy chọn theo yêu cầu truy vấn và khả năng của hệ thống giám sát. Với Prometheus, histogram thường thuận tiện hơn khi cần tổng hợp phân vị từ nhiều instance.

### DistributionSummary: đo phân bố giá trị số

`DistributionSummary` tương tự timer về khả năng thống kê phân bố, nhưng dùng cho giá trị số không phải thời gian. Ví dụ, đo kích thước payload hoặc số mặt hàng trong một đơn:

```java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.response.payload")
        .description("Kích thước payload phản hồi")
        .baseUnit("bytes")
        .register(meterRegistry);

payloadSize.record(responseBytes.length);
```

Không dùng `DistributionSummary` để đo thời lượng nếu `Timer` diễn đạt ý nghĩa rõ hơn. Việc chọn đúng loại meter giúp backend áp dụng quy tắc đơn vị, histogram và truy vấn phù hợp.

### Một số meter khác

Micrometer còn có các loại meter chuyên biệt như `LongTaskTimer` để theo dõi tác vụ kéo dài đang chạy, `FunctionCounter` để quan sát một hàm trả về giá trị tích lũy, `FunctionTimer` để quan sát số lần và tổng thời gian từ một đối tượng có sẵn, hoặc `TimeGauge` để quan sát giá trị thời gian hiện tại. Chỉ dùng các loại này khi mô hình dữ liệu thực sự phù hợp; với phần lớn instrumentation nghiệp vụ ban đầu, bốn loại meter ở trên đã bao phủ những nhu cầu phổ biến.

## Tích hợp Micrometer với Spring Boot

Spring Boot Actuator kết hợp với Micrometer giúp ứng dụng có metrics nền tảng và endpoint phục vụ kiểm tra. Với dự án dùng Gradle và Spring Boot dependency management, cấu hình thường có dạng:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Spring Boot quản lý phiên bản tương thích của Micrometer khi dự án dùng dependency management của Spring Boot. Nếu không dùng Spring Boot dependency management, cần chọn phiên bản registry tương thích với phiên bản `micrometer-core` đang dùng.

Sau khi thêm dependency, có thể cấu hình endpoint và một số thuộc tính metrics trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=orders-api
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Ý nghĩa của các cấu hình:

- `management.endpoints.web.exposure.include` cho phép các endpoint được liệt kê xuất hiện qua web. Endpoint vẫn cần được bảo vệ phù hợp với môi trường triển khai.
- `management.metrics.tags.application` thêm tag chung để phân biệt ứng dụng trong hệ thống giám sát.
- `management.metrics.distribution.percentiles-histogram.http.server.requests` bật histogram cho metric HTTP server requests theo cấu hình Spring Boot/Micrometer tương ứng.

Khi registry Prometheus đã được cấu hình và endpoint được expose, có thể kiểm tra metrics tại `/actuator/prometheus`. Endpoint `/actuator/metrics` cho phép xem các meter mà ứng dụng đang quản lý; có thể truy vấn một meter cụ thể, ví dụ `/actuator/metrics/http.server.requests`. Các endpoint này phục vụ chẩn đoán và kiểm tra, còn Prometheus thường định kỳ scrape endpoint metrics để lưu dữ liệu lịch sử.

Ví dụ cấu hình scrape tối giản ở phía Prometheus:

```yaml
scrape_configs:
  - job_name: orders-api
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["localhost:8080"]
```

Địa chỉ `localhost:8080` chỉ là ví dụ; trong môi trường thực tế, target phải trỏ đến địa chỉ mà Prometheus có thể truy cập. Nếu ứng dụng chạy nhiều instance, cần cấu hình discovery hoặc danh sách target tương ứng.

### Metrics tự động và metrics nghiệp vụ

Tùy dependency và cấu hình, Spring Boot Actuator có thể cung cấp các meter như:

- HTTP server requests: số lần gọi, thời gian xử lý và các chiều như method, status hoặc route.
- JVM memory: mức sử dụng heap và non-heap.
- Garbage collection: số lần và thời gian thu gom rác.
- JVM threads: số thread theo trạng thái.
- CPU và process: một số chỉ số về tiến trình và hệ thống.
- Connection pool, cache hoặc client: metrics tùy thư viện tích hợp.

Các meter tự động giúp có bức tranh nền tảng về ứng dụng. Tuy nhiên, chúng không biết ý nghĩa nghiệp vụ như một đơn hàng được tạo thành công hay một khoản thanh toán bị từ chối. Hãy bổ sung metrics tại ranh giới nghiệp vụ để kết hợp góc nhìn kỹ thuật và sản phẩm.

Một lớp instrumentation có thể đóng gói việc đăng ký và ghi nhận metrics để service nghiệp vụ không phải lặp lại tên metric và tag ở nhiều nơi:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class OrderMetrics {
    private final MeterRegistry registry;
    private final DistributionSummary itemsPerOrder;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.itemsPerOrder = DistributionSummary.builder("business.orders.items")
                .description("Số mặt hàng trong mỗi đơn hàng")
                .baseUnit("items")
                .register(registry);
    }

    public void recordCreated(String channel, int itemCount) {
        registry.counter(
                "business.orders.created",
                "channel", normalizeChannel(channel)
        ).increment();

        itemsPerOrder.record(itemCount);
    }

    public <T> T timeCreate(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.get();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(registry.timer(
                    "business.orders.create",
                    "outcome", outcome
            ));
        }
    }

    private static String normalizeChannel(String channel) {
        return switch (channel) {
            case "web", "mobile", "store" -> channel;
            default -> "other";
        };
    }
}
```

Service nghiệp vụ có thể gọi `orderMetrics.timeCreate(() -> orderRepository.save(order))` để đo thời gian và gọi `orderMetrics.recordCreated(channel, itemCount)` sau khi đơn được tạo thành công. Trong ứng dụng thực tế, hãy xác định rõ điểm ghi nhận để tránh tăng counter trước khi giao dịch được xác nhận thành công. Nếu thao tác tạo đơn nằm trong transaction, thời điểm ghi nhận nên phản ánh đúng định nghĩa nghiệp vụ mà dashboard cần theo dõi.

Ví dụ trên cũng minh họa một nguyên tắc quan trọng: tên metric và tập tag được quản lý tập trung. Khi muốn thay đổi tên, đơn vị hoặc ý nghĩa phép đo, nhóm có thể rà soát một lớp instrumentation thay vì tìm nhiều chuỗi rải rác trong codebase.

## Kiểm soát cardinality và thiết kế tag

Mỗi tổ hợp tên metric và tag tạo thành một chuỗi time series riêng ở backend dạng time series. Nếu metric có tag `channel` gồm 3 giá trị, `outcome` gồm 2 giá trị và `region` gồm 5 giá trị, số tổ hợp tối đa của riêng ba chiều này là 3 × 2 × 5 = 30. Khi thêm một tag `customerId` có hàng trăm nghìn giá trị, số chuỗi có thể tăng đột biến.

Cardinality cao gây tốn bộ nhớ và CPU ở ứng dụng, tăng lượng dữ liệu truyền đi, làm backend lưu trữ đắt hơn và khiến truy vấn chậm. Vì vậy, thiết kế tag là một phần của thiết kế hệ thống, không chỉ là chi tiết khi viết code.

### Quy tắc chọn tag

1. Chỉ dùng chiều phân tích có tập giá trị hữu hạn và được kiểm soát.
2. Ưu tiên các giá trị như `method`, `status`, `outcome`, `channel`, `region` hoặc tên route đã chuẩn hóa.
3. Dùng route template như `/orders/{id}` thay vì URL thực tế như `/orders/928374`.
4. Không đưa ID người dùng, ID đơn hàng, email, token, IP tùy ý, nội dung exception hoặc dữ liệu nhạy cảm vào tag.
5. Chuẩn hóa giá trị đầu vào và gom các giá trị lạ vào nhóm `other` hoặc `unknown` khi phù hợp.
6. Trước khi thêm tag mới, ước lượng số tổ hợp tag và xác định ai sẽ dùng chiều phân tích đó.

Không phải mọi tag có cardinality cao đều sai trong mọi loại hệ thống, nhưng metrics thường được nhân bản trên nhiều instance và được thu thập liên tục. Nếu cần phân tích từng người dùng hoặc từng giao dịch, log hoặc trace thường phù hợp hơn metrics.

### Dùng MeterFilter làm lớp bảo vệ

Micrometer cung cấp `MeterFilter` để chuẩn hóa, loại bỏ hoặc giới hạn meter. Ví dụ sau giới hạn số giá trị tag `channel` được chấp nhận cho một nhóm metric:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;

@Configuration
public class MetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricsCustomizer() {
        return registry -> registry.config()
                .commonTags("application", "orders-api")
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "business.orders.created",
                        "channel",
                        5,
                        MeterFilter.deny()
                ));
    }
}
```

Filter này là hàng rào bổ sung khi có quá nhiều giá trị tag mới. Nó không thay thế việc chuẩn hóa dữ liệu đầu vào và thiết kế allow-list ở lớp nghiệp vụ. Hãy kiểm tra API import theo phiên bản Spring Boot đang dùng; nếu dự án đã có một `MeterRegistryCustomizer`, nên tích hợp cấu hình vào bean hiện có thay vì tạo nhiều cấu hình trùng lặp.

## Kiểm thử instrumentation

Metrics là một phần của hành vi vận hành, vì vậy nên kiểm tra ít nhất ba điều: meter được đăng ký đúng tên, thao tác làm thay đổi số đo như dự kiến và tag chỉ nhận các giá trị đã quy định.

`SimpleMeterRegistry` hữu ích cho unit test vì lưu meter trong bộ nhớ và không cần kết nối đến backend bên ngoài:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMetricsTest {
    @Test
    void recordsCreatedOrders() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Counter counter = registry.counter(
                "business.orders.created",
                "channel", "web"
        );

        counter.increment();

        assertThat(counter.count()).isEqualTo(1.0);
        registry.close();
    }
}
```

Trong test thực tế, nên khởi tạo lớp `OrderMetrics` với `SimpleMeterRegistry`, gọi phương thức instrumentation, rồi truy vấn meter qua registry để kiểm tra kết quả. Đối với timer, có thể kiểm tra `count()` sau khi ghi nhận; đối với summary, kiểm tra `count()` và `totalAmount()`; đối với gauge, thay đổi đối tượng được quan sát rồi xác minh giá trị mới.

Unit test không chứng minh endpoint export hoạt động. Nên có kiểm thử tích hợp ở mức phù hợp để xác nhận Spring tạo đúng registry, endpoint metrics được expose theo cấu hình và tên/tag được chuyển đổi như dự kiến. Trong môi trường staging, kiểm tra thêm việc Prometheus scrape thành công và metric xuất hiện với label mong muốn.

Một số điểm cần chú ý khi kiểm thử:

- Không phụ thuộc vào thứ tự lấy mẫu của gauge; chỉ kiểm tra giá trị tại thời điểm đọc.
- Với timer, tránh khẳng định một thời lượng chính xác tuyệt đối vì thời gian chạy test biến động. Kiểm tra số lần ghi nhận và đơn vị phù hợp.
- Mỗi test nên dùng registry riêng hoặc xóa trạng thái đúng cách để dữ liệu test không ảnh hưởng lẫn nhau.
- Kiểm tra cả trường hợp thành công và thất bại để bảo đảm timer luôn được dừng và tag `outcome` phản ánh đúng kết quả.
- Kiểm tra dữ liệu đầu vào lạ được chuẩn hóa thành nhóm đã định nghĩa, thay vì tạo tag mới không giới hạn.

## Đọc metrics để hiểu tình trạng vận hành

Metrics chỉ hữu ích khi được diễn giải theo câu hỏi vận hành. Một cách tiếp cận phổ biến là theo dõi bốn tín hiệu chính của dịch vụ:

| Tín hiệu | Câu hỏi | Meter hoặc số liệu thường dùng |
|---|---|---|
| Traffic | Hệ thống đang nhận bao nhiêu yêu cầu? | Rate từ counter hoặc HTTP request count |
| Errors | Bao nhiêu yêu cầu thất bại? | Counter theo outcome/status và tỷ lệ lỗi |
| Latency | Yêu cầu mất bao lâu? | Timer, p95/p99 hoặc histogram |
| Saturation | Tài nguyên nào đang gần giới hạn? | Gauge của queue, thread pool, connection pool và mức sử dụng tài nguyên |

Ví dụ, nếu traffic tăng nhưng latency và error rate ổn định, dịch vụ có thể đang xử lý tải tốt. Nếu traffic không đổi nhưng p95 tăng và queue size liên tục đi lên, một thành phần phía sau có thể đang trở thành nút thắt. Nếu error rate tăng cùng lúc với connection pool gần cạn, cần kiểm tra kết nối cơ sở dữ liệu hoặc dịch vụ phụ thuộc.

Không nên đọc một metric riêng lẻ rồi kết luận nguyên nhân. Metrics cho biết điều gì đang thay đổi; log và trace giúp điều tra sự kiện hoặc request cụ thể tạo ra thay đổi đó. Kết hợp ba tín hiệu giúp chuyển từ phát hiện bất thường sang tìm nguyên nhân.

### Một số cách diễn giải thường gặp

- **Counter tăng nhanh**: kiểm tra rate theo cửa sổ thời gian và so sánh với lưu lượng bình thường. Giá trị tích lũy lớn tự nó không nhất thiết là dấu hiệu lỗi.
- **Timer p95 tăng**: phần đáng kể yêu cầu đang chậm hơn. So sánh p50, p95 và p99 để biết vấn đề ảnh hưởng rộng hay chỉ một nhóm nhỏ.
- **Timer count giảm bất thường**: có thể lưu lượng giảm, scrape bị gián đoạn hoặc request không còn đi qua đoạn instrumentation. Kiểm tra traffic và trạng thái thu thập trước khi kết luận.
- **Gauge hàng đợi tăng liên tục**: tốc độ đưa việc vào đang vượt tốc độ xử lý. Xem thêm số worker, thời gian xử lý và lỗi ở consumer.
- **DistributionSummary thay đổi**: payload hoặc kích thước công việc có thể đang lớn hơn, làm tăng bộ nhớ, mạng hoặc thời gian xử lý.

Histogram và percentile cần được cấu hình có chủ đích. Histogram tạo thêm chuỗi dữ liệu theo bucket nhưng cho phép backend tổng hợp phân vị từ nhiều instance. Percentile tính riêng ở từng instance có thể không tổng hợp chính xác thành percentile toàn cụm bằng cách lấy trung bình các percentile. Hãy chọn cách xuất dữ liệu theo mục tiêu phân tích và chi phí lưu trữ.

## Những lỗi thiết kế thường gặp

**Đưa ID duy nhất vào tag.** Mỗi người dùng hoặc đơn hàng tạo một time series riêng, khiến cardinality tăng nhanh. Dùng log hoặc trace khi cần truy vết từng thực thể.

**Dùng counter cho trạng thái hiện tại.** Counter không giảm; số kết nối đang mở và số tác vụ đang chờ nên được biểu diễn bằng gauge.

**Dùng gauge cho sự kiện đã xảy ra.** Giá trị gauge có thể bị bỏ lỡ giữa hai lần lấy mẫu. Nếu cần tổng số sự kiện, hãy dùng counter.

**Tự đo thời gian nhưng quên dừng timer khi có exception.** Dùng `Timer.record(...)` hoặc cấu trúc `try/finally` với `Timer.Sample` để mọi đường thực thi đều kết thúc phép đo.

**Đăng ký meter với tên hoặc tag không nhất quán.** Cùng một khái niệm nhưng nhiều tên khác nhau làm dashboard khó bảo trì. Định nghĩa metric contract gồm tên, đơn vị, loại meter, tag và ý nghĩa.

**Tạo meter mới cho mỗi request bằng giá trị tag tùy ý.** Meter được registry quản lý theo danh tính meter; dữ liệu đầu vào không giới hạn có thể làm số meter tăng liên tục. Chuẩn hóa tag trước khi đăng ký hoặc lấy meter.

**Chỉ theo dõi metrics tự động.** JVM và HTTP metrics không thể thay thế số đo nghiệp vụ. Hãy đo các thao tác cốt lõi mà người dùng và đội vận hành quan tâm.

**Bật mọi histogram mà không tính chi phí.** Histogram và nhiều chiều tag làm tăng số chuỗi dữ liệu. Chỉ bật cho các metric cần phân tích phân bố, chọn bucket phù hợp và theo dõi tác động đến backend.

## Quy trình đưa một metric mới vào ứng dụng

Trước khi viết code, hãy trả lời các câu hỏi sau:

1. **Cần trả lời câu hỏi vận hành nào?** Ví dụ: số đơn tạo thành công mỗi phút hay thời gian tạo đơn ở p95?
2. **Đại lượng cần đo là gì?** Sự kiện tích lũy, trạng thái hiện tại, thời lượng hay phân bố số học?
3. **Loại meter nào diễn đạt đúng nhất?** Chọn counter, gauge, timer hoặc distribution summary.
4. **Tên và đơn vị nào rõ ràng?** Dùng tên ổn định, mô tả được ý nghĩa và không gắn giá trị động vào tên.
5. **Tag nào thực sự cần thiết?** Ước lượng cardinality bằng tích số giá trị có thể có của từng tag.
6. **Đo ở ranh giới nào?** Chọn thời điểm bắt đầu và kết thúc rõ ràng, đặc biệt với transaction, retry và xử lý bất đồng bộ.
7. **Kiểm thử và quan sát ở đâu?** Viết unit test, kiểm tra endpoint export và xác nhận dashboard có thể truy vấn metric.

Một metric tốt có tên dễ hiểu, đơn vị rõ ràng, tag hữu hạn và trả lời được một câu hỏi cụ thể. Nếu không biết ai sẽ dùng metric hoặc quyết định nào sẽ thay đổi nhờ nó, hãy xem lại nhu cầu trước khi thêm phép đo.

## Kết luận

Micrometer cung cấp API metrics thống nhất cho ứng dụng JVM, giúp tách mã instrumentation khỏi backend giám sát. `MeterRegistry` quản lý meter; `Counter` đếm sự kiện, `Gauge` quan sát trạng thái hiện tại, `Timer` đo thời gian và `DistributionSummary` đo phân bố giá trị số. Spring Boot Actuator giúp tích hợp registry, cung cấp metrics nền tảng và expose endpoint để hệ thống giám sát thu thập.

Để metrics có giá trị trong vận hành, hãy định nghĩa rõ ý nghĩa từng phép đo, chọn tag có cardinality hữu hạn, kiểm thử hành vi ghi nhận và đọc các tín hiệu trong bối cảnh traffic, lỗi, latency và saturation. Khi đó, metrics trở thành công cụ quan sát có thể hành động, thay vì chỉ là một tập số liệu được xuất ra từ ứng dụng.
