# Đo thủ công, đo qua thư viện và đo tự động của framework

Micrometer cung cấp một mô hình thống nhất để ghi nhận metrics trong ứng dụng Java. Một ứng dụng có thể tạo số đo ngay trong logic nghiệp vụ, nhận số đo từ các thư viện đang sử dụng, hoặc để framework tự cấu hình instrumentation tại những điểm tích hợp chuẩn như HTTP server, JVM và connection pool.

Ba cách này giải quyết các lớp quan sát khác nhau. Đo thủ công giúp diễn đạt điều chỉ ứng dụng mới hiểu, chẳng hạn số đơn hàng được tạo hoặc thời gian xử lý thanh toán. Instrumentation qua thư viện quan sát trạng thái bên trong của một thành phần đã có sẵn. Instrumentation tự động của framework giúp thu thập các số đo phổ biến mà không cần thêm mã ở từng điểm gọi. Một hệ thống vận hành tốt thường kết hợp cả ba.

## 1. Ba cách instrumentation khác nhau ở đâu?

### Đo thủ công trong mã ứng dụng

Đo thủ công là cách lập trình viên chủ động gọi API Micrometer tại thời điểm một sự kiện xảy ra hoặc một thao tác hoàn tất. Ứng dụng quyết định ý nghĩa của metric, thời điểm ghi nhận, loại meter và tập nhãn.

Ví dụ:

- Tăng counter khi một đơn hàng được xác nhận thành công.
- Đo thời gian gọi cổng thanh toán.
- Ghi nhận giá trị đơn hàng vào distribution summary.
- Quan sát số phần tử hiện có trong hàng đợi xử lý.

Cách này phù hợp với số đo mang ý nghĩa nghiệp vụ hoặc một luồng xử lý riêng của ứng dụng. Đổi lại, mã ứng dụng phải chịu trách nhiệm đặt tên, gắn nhãn, ghi nhận đúng thời điểm và tránh tạo quá nhiều meter.

### Đo qua thư viện instrumentation hoặc binder

Một thư viện instrumentation đã biết cách quan sát một thành phần cụ thể và chuyển trạng thái của thành phần đó thành meter Micrometer. Thành phần được quan sát có thể là JVM, bộ nhớ, class loader, executor, cache, connection pool hoặc một client có hỗ trợ Micrometer.

Micrometer định nghĩa giao diện `MeterBinder` để một binder đăng ký các meter của nó vào `MeterRegistry`. Nhiều binder có sẵn trong hệ sinh thái Micrometer. Ứng dụng có thể dùng chúng mà không phải tự viết mã đọc trạng thái nội bộ của thành phần.

Ví dụ, các binder JVM có thể đăng ký số liệu về bộ nhớ, class loader và bộ xử lý. Một integration cho cache có thể ghi nhận số lần hit, miss và kích thước cache nếu loại cache đó hỗ trợ các số đo tương ứng.

Cách này phù hợp khi thành phần đã có instrumentation đáng tin cậy. Chất lượng và phạm vi số đo phụ thuộc vào binder cũng như khả năng quan sát mà thư viện gốc cung cấp.

### Đo tự động của framework

Framework có thể tự phát hiện các thành phần được hỗ trợ, tạo meter cần thiết và quản lý vòng đời đăng ký. Với Spring Boot Actuator, các cấu hình metrics phổ biến được tự động kết nối khi những dependency phù hợp có mặt trên classpath.

Ví dụ, Spring Boot có thể cung cấp metrics cho HTTP server, JVM, process, datasource và một số cache hoặc client đã tích hợp. Ứng dụng không cần tự gọi counter hay timer ở mỗi request để có các số liệu chuẩn đó.

Instrumentation tự động giúp giảm mã lặp và tạo ra các số đo nhất quán. Tuy nhiên, framework chỉ hiểu những điểm tích hợp mà nó hỗ trợ. Nó không thể tự suy ra một sự kiện nghiệp vụ như “đơn hàng đã được chấp nhận” hoặc “thanh toán bị từ chối do hạn mức”.

### So sánh nhanh

| Tiêu chí | Đo thủ công | Qua thư viện/binder | Tự động của framework |
|---|---|---|---|
| Ai xác định số đo? | Đội phát triển ứng dụng | Tác giả thư viện instrumentation | Framework và integration |
| Phạm vi phù hợp | Nghiệp vụ, luồng xử lý riêng | Trạng thái nội bộ của thành phần | Các điểm tích hợp phổ biến |
| Vị trí cấu hình | Trong mã ứng dụng | Binder hoặc cấu hình thư viện | Auto-configuration |
| Khả năng tùy chỉnh | Cao | Theo API binder | Theo thuộc tính và extension được hỗ trợ |
| Công sức ban đầu | Cần thiết kế và viết mã | Thường thấp | Thường thấp |
| Rủi ro chính | Ghi sai thời điểm, nhãn không kiểm soát | Thiếu số đo hoặc đăng ký trùng | Tưởng rằng mọi nghiệp vụ đều đã được đo |

Các cách này có thể cùng xuất hiện trong một ứng dụng. Một binder có thể được framework tự động phát hiện; vì vậy “qua thư viện” mô tả nơi định nghĩa instrumentation, còn “tự động của framework” thường mô tả cách instrumentation được cấu hình và quản lý.

## 2. Luồng metrics trong kiến trúc Micrometer

Dù meter được tạo thủ công, từ binder hay từ auto-configuration, dữ liệu thường đi qua cùng một luồng:

```text
Logic nghiệp vụ ───────┐
Binder của thư viện ──┼──> MeterRegistry
Framework ────────────┘         |
                                v
                         MeterFilter / tags
                                |
                                v
                       Registry theo backend
                                |
                                v
                  Prometheus, backend metrics...
                                |
                                v
                    Dashboard và cảnh báo
```

`MeterRegistry` là điểm đăng ký và truy cập meter. Counter, gauge, timer và distribution summary được đăng ký vào registry. Các thao tác ghi nhận cập nhật meter tương ứng; registry chuyên biệt chuyển số liệu sang định dạng mà hệ thống giám sát hiểu được.

`MeterFilter` có thể chuẩn hóa hoặc từ chối meter, thêm nhãn chung và giới hạn số giá trị nhãn. Đây là một lớp bảo vệ bổ sung, nhưng thiết kế nhãn đúng ngay từ đầu vẫn là trách nhiệm của người tạo instrumentation.

Cần phân biệt hai việc:

1. **Đăng ký meter:** khai báo một số đo có tên, loại và tập nhãn xác định.
2. **Ghi nhận hoặc lấy giá trị:** tăng counter, ghi thời lượng vào timer, ghi một giá trị vào summary hoặc đọc trạng thái hiện tại qua gauge.

Thông thường, meter có cùng tên và cùng tập nhãn sẽ được registry nhận diện là cùng một meter. Vì vậy, không nên tạo tên metric mới hoặc nhãn mới theo từng request.

## 3. Đo thủ công với các meter của Micrometer

Trước khi chọn API, hãy xác định câu hỏi vận hành cần trả lời. Một metric hữu ích phải có ý nghĩa rõ ràng, đơn vị phù hợp và thời điểm ghi nhận nhất quán.

### Counter: đếm sự kiện tích lũy

Counter tăng đơn điệu khi có sự kiện. Nó phù hợp để đếm số đơn hàng được tạo, số lần xử lý thành công hoặc số lần một thao tác thất bại.

```java
registry.counter(
    "orders.created",
    "channel", "web"
).increment();
```

Counter thường được diễn giải bằng tốc độ tăng trong một khoảng thời gian, chẳng hạn số đơn hàng mỗi giây. Không nên giảm counter để biểu diễn số phần tử đang chờ; trạng thái hiện tại là trường hợp của gauge.

Nếu một timer đã ghi nhận số lần hoàn tất thao tác, trường `count` của timer cũng đã cung cấp số lần đó. Tránh tạo thêm một counter trùng nghĩa chỉ để đếm cùng các lần hoàn tất.

### Gauge: đọc một trạng thái tại thời điểm quan sát

Gauge phản ánh giá trị có thể tăng hoặc giảm, ví dụ độ dài hàng đợi, số kết nối đang hoạt động hoặc số tác vụ đang chờ.

```java
Gauge.builder("jobs.queue.depth", queue, BlockingQueue::size)
    .description("Số công việc đang chờ xử lý")
    .register(registry);
```

Gauge thường đọc giá trị từ một đối tượng được giữ trong bộ nhớ. Hãy giữ tham chiếu mạnh đến đối tượng được đo trong suốt thời gian cần quan sát. Một số cách triển khai gauge giữ tham chiếu yếu; nếu đối tượng bị thu gom rác, gauge có thể không còn cung cấp giá trị mong muốn.

Không nên cập nhật gauge bằng cách tăng hoặc giảm thủ công như counter. Hãy để hàm đọc gauge lấy trạng thái hiện tại từ nguồn dữ liệu có thẩm quyền.

### Timer: đo thời lượng và số lần thực hiện

Timer đo thời gian thực thi và đồng thời ghi nhận số lần hoàn tất. Timer thường phù hợp với thời gian xử lý thanh toán, gọi dịch vụ bên ngoài hoặc thực hiện một tác vụ nền.

```java
Timer paymentTimer = Timer.builder("orders.payment.duration")
    .description("Thời gian xử lý thanh toán")
    .publishPercentileHistogram()
    .register(registry);

paymentTimer.record(() -> paymentGateway.charge(order));
```

`record` bao quanh thao tác cần đo và ghi thời lượng khi thao tác kết thúc. Cách này giúp tránh quên ghi nhận ở nhánh thành công hoặc nhánh lỗi. Nếu cần gắn nhãn phụ thuộc vào kết quả thực thi, có thể dùng `Timer.Sample`, sau đó dừng sample với timer có tập nhãn đã được chuẩn hóa.

Timer cung cấp ít nhất số lần ghi nhận và tổng thời gian. Backend có thể dùng histogram để tính phân vị trên tập dữ liệu được tổng hợp. Percentile được tính cục bộ tại từng registry không thể luôn được gộp chính xác giữa nhiều instance; khi cần phân vị toàn hệ thống, hãy chọn histogram bucket phù hợp với backend.

### Distribution summary: đo phân phối của một đại lượng

Distribution summary ghi nhận các giá trị không nhất thiết là thời lượng, ví dụ kích thước payload, số bản ghi trong một batch hoặc giá trị đơn hàng.

```java
DistributionSummary orderValue = DistributionSummary
    .builder("orders.value")
    .description("Giá trị đơn hàng")
    .baseUnit("VND")
    .register(registry);

orderValue.record(order.totalAmount());
```

Summary có thể cung cấp count, tổng và các thống kê phân phối tùy cấu hình registry. Dùng timer cho thời lượng vì timer có quy ước đơn vị thời gian và API phù hợp; dùng summary cho đại lượng khác.

### Đóng gói instrumentation nghiệp vụ

Không nên rải tên metric và chuỗi nhãn khắp service. Một lớp nhỏ chuyên trách metrics giúp gom quy ước vào một nơi và làm cho luồng nghiệp vụ dễ đọc hơn.

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class OrderMetrics {
    private final MeterRegistry registry;
    private final Timer paymentTimer;
    private final DistributionSummary orderValue;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.paymentTimer = Timer.builder("orders.payment.duration")
            .description("Thời gian xử lý thanh toán")
            .publishPercentileHistogram()
            .register(registry);
        this.orderValue = DistributionSummary.builder("orders.value")
            .description("Giá trị đơn hàng")
            .baseUnit("VND")
            .register(registry);
    }

    public void orderCreated(String channel) {
        registry.counter(
            "orders.created",
            "channel", normalizeChannel(channel)
        ).increment();
    }

    public <T> T recordPayment(Supplier<T> operation) {
        return paymentTimer.record(operation);
    }

    public void recordOrderValue(double amount) {
        orderValue.record(amount);
    }

    private String normalizeChannel(String channel) {
        return switch (channel) {
            case "web", "mobile", "partner" -> channel;
            default -> "other";
        };
    }
}
```

Service dùng `recordPayment` để bao quanh lời gọi cổng thanh toán; gọi `orderCreated` tại điểm đơn hàng thực sự được tạo và commit; gọi `recordOrderValue` khi giá trị đơn hàng đã được xác định. Nếu sự kiện phát sinh trong một transaction, hãy ghi counter trong callback after-commit hoặc qua event listener chạy sau commit. Như vậy, transaction rollback sẽ không làm metric báo một sự kiện thành công chưa từng có hiệu lực.

## 4. Instrumentation qua thư viện và MeterBinder

Khi cần đo một thành phần hạ tầng, trước tiên hãy kiểm tra thư viện đó có cung cấp binder hoặc integration Micrometer hay không. Dùng binder giúp ứng dụng tuân theo cách đo mà thư viện đã thiết kế, thay vì tự đọc các trường nội bộ hoặc tự suy ra trạng thái.

Ví dụ đăng ký một số binder JVM trong ứng dụng Micrometer thuần:

```java
new ClassLoaderMetrics().bindTo(registry);
new JvmMemoryMetrics().bindTo(registry);
new ProcessorMetrics().bindTo(registry);
```

Mỗi binder đăng ký một nhóm meter vào registry. Trong Spring Boot, nhiều binder phổ biến đã được auto-configuration quản lý; chỉ đăng ký thủ công khi ứng dụng thực sự cần và đã xác nhận binder đó chưa được đăng ký ở nơi khác.

Các nhóm integration thường gặp gồm:

- **JVM:** bộ nhớ heap và non-heap, class loader, garbage collection, CPU và process.
- **Executor và thread pool:** số tác vụ đang hoạt động, hàng đợi, số luồng và trạng thái pool khi thư viện cung cấp dữ liệu.
- **Cache:** hit, miss, eviction và kích thước cache.
- **Datasource và connection pool:** kết nối đang hoạt động, kết nối nhàn rỗi, mức sử dụng và thời gian chờ nếu integration hỗ trợ.
- **Client hoặc messaging:** số request, lỗi, thời lượng và trạng thái tiêu thụ khi thư viện có instrumentation tương ứng.

Một binder thường có vòng đời đăng ký riêng. Hãy đăng ký nó một lần trong cấu hình ứng dụng hoặc để framework quản lý như một bean. Không tạo binder mới trên mỗi request, và không đồng thời bật nhiều integration ghi cùng một meter nếu chúng gây trùng số liệu.

Nếu một thành phần nội bộ do đội phát triển sở hữu được dùng ở nhiều nơi, có thể đóng gói instrumentation của nó thành một implementation của `MeterBinder`. Cách này vẫn là instrumentation được viết có chủ đích, nhưng tách phần đo khỏi nơi gọi và giúp tái sử dụng. Chỉ nên làm vậy khi có ranh giới thành phần rõ ràng; với một sự kiện nghiệp vụ đơn giản, gọi meter tại service thường dễ hiểu hơn.

## 5. Instrumentation tự động với Spring Boot

Spring Boot Actuator tích hợp Micrometer và cung cấp auto-configuration cho nhiều nhóm metrics tiêu chuẩn. Cấu hình phổ biến với Prometheus gồm hai dependency:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Phiên bản dependency nên được quản lý bởi Spring Boot dependency management của dự án. Sau đó có thể cấu hình endpoint và nhãn chung trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.tags.application=orders-service
```

Khi registry Prometheus có mặt và endpoint được expose, metrics có thể được lấy tại `/actuator/prometheus`. Chỉ expose endpoint cần thiết và đặt nó sau cơ chế kiểm soát truy cập phù hợp với môi trường triển khai.

Tùy phiên bản Spring Boot, dependency và thành phần đang dùng, auto-configuration có thể cung cấp các nhóm số đo như:

- Request HTTP phía server, thường có tên meter `http.server.requests`.
- Metrics JVM, process và system.
- Metrics của datasource hoặc connection pool được hỗ trợ.
- Metrics cache và một số client đã tích hợp.
- Các binder hoặc `MeterBinder` bean do ứng dụng cung cấp.

Tên meter, tag và tập số đo cụ thể có thể thay đổi theo phiên bản và integration. Hãy kiểm tra endpoint metrics thực tế của ứng dụng thay vì giả định mọi dependency đều tự động tạo cùng một bộ meter.

Auto-configuration không thay thế instrumentation nghiệp vụ. Framework có thể biết một HTTP request mất bao lâu, nhưng không biết request đó đã tạo đơn hàng hợp lệ hay bị từ chối do quy tắc hạn mức. Những sự kiện đó cần được đo tại lớp nghiệp vụ.

## 6. Chọn đúng lớp instrumentation

Có thể dùng các câu hỏi sau để quyết định:

| Câu hỏi cần trả lời | Cách phù hợp |
|---|---|
| Mỗi phút có bao nhiêu đơn hàng được xác nhận? | Counter thủ công tại điểm xác nhận |
| Một thao tác nghiệp vụ mất bao lâu? | Timer thủ công quanh thao tác |
| Hàng đợi hiện có bao nhiêu công việc? | Gauge hoặc binder của hàng đợi |
| JVM đang dùng bao nhiêu heap? | Binder JVM hoặc auto-configuration |
| Connection pool còn bao nhiêu kết nối? | Binder/integration datasource hoặc auto-configuration |
| HTTP endpoint nào có độ trễ cao? | Metrics HTTP tự động của framework |
| Cache có tỷ lệ hit/miss thế nào? | Binder hoặc integration của cache |

Một quy trình lựa chọn thực tế:

1. Xác định câu hỏi vận hành và đơn vị cần đo.
2. Kiểm tra framework hoặc thư viện hiện tại đã cung cấp meter tương ứng chưa.
3. Nếu số đo có ý nghĩa nghiệp vụ, bổ sung instrumentation thủ công ở điểm sự kiện thực sự xảy ra.
4. Nếu số đo thuộc trạng thái nội bộ của thành phần, ưu tiên binder chính thức.
5. Kiểm tra tên meter, tag và số series thực tế sau khi ứng dụng khởi động.
6. Kiểm thử cả giá trị ghi nhận lẫn quy ước nhãn.

Trước khi thêm meter mới, hãy kiểm tra xem timer hoặc meter tự động hiện có đã trả lời cùng câu hỏi chưa. Đo trùng có thể làm dashboard khó diễn giải và khiến người vận hành so sánh hai số liệu có ranh giới khác nhau.

## 7. Kiểm soát nhãn và cardinality

Mỗi tổ hợp tên metric và giá trị nhãn có thể tạo ra một time series riêng. Nếu một metric có nhiều nhãn, số series tăng theo số tổ hợp giá trị của các nhãn đó. Histogram còn tạo thêm nhiều series cho các bucket và thống kê liên quan.

Ví dụ, một metric có:

- `channel`: `web`, `mobile`, `partner` — 3 giá trị.
- `result`: `success`, `failure` — 2 giá trị.
- `region`: 5 khu vực cố định.

Tổ hợp tối đa là 3 × 2 × 5 = 30 series cho metric đó, trước khi tính các bucket histogram. Nếu thêm `order_id` với hàng triệu giá trị, số series có thể tăng rất lớn.

Nhãn nên mô tả một tập giá trị hữu hạn và có ý nghĩa khi lọc hoặc nhóm dữ liệu.

**Nên dùng:**

- `method`: GET, POST, PUT, DELETE.
- `status` hoặc `outcome`: các nhóm trạng thái hữu hạn.
- `channel`: web, mobile, partner, other.
- `uri`: mẫu route như `/orders/{id}`, không phải URL chứa ID thực.
- `region`: mã khu vực thuộc danh sách cấu hình.

**Không nên dùng:**

- ID người dùng, ID đơn hàng hoặc ID request.
- Email, số điện thoại, token hoặc dữ liệu nhạy cảm.
- URL đầy đủ có query string hoặc đường dẫn chứa ID thực.
- Nội dung exception tùy ý hoặc thông điệp lỗi có thể thay đổi theo request.
- Tên tenant tự do nếu số tenant không có giới hạn phù hợp.

Nếu đầu vào đến từ bên ngoài, hãy chuẩn hóa nó thành nhóm giá trị đã biết, như hàm `normalizeChannel` ở ví dụ trên. Có thể cấu hình `MeterFilter` để giới hạn số giá trị của một tag như lớp bảo vệ bổ sung:

```java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "orders.created",
        "channel",
        10,
        MeterFilter.deny()
    )
);
```

Giới hạn này giúp tránh đăng ký vô hạn giá trị tag cho meter được chỉ định. Nó không làm cho thiết kế nhãn tùy ý trở nên an toàn: giá trị bị từ chối có thể khiến dữ liệu không được ghi nhận như mong muốn. Hãy thiết kế tập nhãn hữu hạn trước, sau đó mới dùng filter để bảo vệ thêm.

## 8. Kiểm thử instrumentation

Instrumentation là một phần hành vi có thể kiểm thử. Một bài kiểm thử tốt xác minh rằng đúng sự kiện làm tăng đúng meter, timer ghi nhận số lần hoàn tất và nhãn có giá trị đã chuẩn hóa.

`SimpleMeterRegistry` hữu ích cho unit test vì cho phép đọc meter ngay trong tiến trình mà không cần Prometheus hoặc backend bên ngoài.

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderMetricsTest {
    @Test
    void recordsCreatedOrderWithNormalizedChannel() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.orderCreated("unknown-channel");

        double count = registry.get("orders.created")
            .tag("channel", "other")
            .counter()
            .count();

        assertEquals(1.0, count);
    }
}
```

Các kiểm thử nên bao phủ những trường hợp quan trọng:

- Sự kiện chỉ được đếm sau khi đạt trạng thái nghiệp vụ đã định nghĩa.
- Nhánh thành công và thất bại được ghi nhận theo đúng quy ước.
- Timer tăng count khi thao tác hoàn tất, kể cả khi thao tác kết thúc bằng exception nếu đó là hành vi mong muốn.
- Gauge phản ánh trạng thái nguồn sau khi trạng thái thay đổi.
- Nhãn luôn thuộc tập giá trị được cho phép.
- Không tạo meter mới theo ID hoặc dữ liệu biến thiên ở mỗi lần gọi.

Unit test với `SimpleMeterRegistry` xác minh logic ghi nhận. Một integration test ở cấp ứng dụng có thể kiểm tra registry thật, endpoint Prometheus và cấu hình tag chung. Hai cấp kiểm thử trả lời các câu hỏi khác nhau: một bên xác minh ứng dụng ghi đúng số đo, bên kia xác minh số đo được xuất ra đúng như hệ thống giám sát cần.

## 9. Diễn giải số liệu vận hành

Metric chỉ có giá trị khi được đọc đúng ngữ nghĩa.

### Tốc độ sự kiện

Counter là giá trị tích lũy. Khi cần biết tốc độ, hãy lấy tốc độ tăng theo một cửa sổ thời gian. Với Prometheus, một biểu thức thường gặp cho request là:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

Tên metric xuất Prometheus phụ thuộc vào quy ước chuyển đổi tên và phiên bản integration. Hãy xác nhận tên thực tế trong endpoint trước khi dùng biểu thức này.

### Độ trễ

Timer cung cấp count và tổng thời gian; histogram bucket có thể hỗ trợ tính phân vị. Với Spring Boot, có thể bật histogram cho HTTP server requests bằng thuộc tính sau:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Sau khi xác nhận endpoint Prometheus có các bucket tương ứng, một truy vấn p95 thường có dạng:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Nếu cần so sánh endpoint, giữ thêm nhãn route trong phép nhóm, nhưng chỉ khi route là mẫu đường dẫn có cardinality hữu hạn. Đừng chỉ nhìn trung bình: một nhóm request chậm có thể bị che khuất bởi nhiều request nhanh.

### Mức bão hòa

Gauge về hàng đợi, số luồng đang hoạt động hoặc số kết nối đang dùng giúp nhận ra thành phần sắp cạn tài nguyên. Đọc chúng cùng với throughput và latency: hàng đợi tăng liên tục trong khi tốc độ xử lý không tăng thường là dấu hiệu hệ thống đang bị nghẽn.

Một metric đơn lẻ hiếm khi giải thích được nguyên nhân. Ví dụ, latency tăng có thể đến từ datasource, dịch vụ bên ngoài, CPU hoặc hàng đợi. Kết hợp số đo ở các lớp framework, thư viện và nghiệp vụ giúp thu hẹp vùng cần điều tra.

## 10. Các lỗi thiết kế thường gặp

- **Dùng counter cho trạng thái hiện tại:** counter không phù hợp với số kết nối đang mở hoặc độ dài hàng đợi. Dùng gauge.
- **Dùng gauge cho sự kiện đã xảy ra:** gauge chỉ phản ánh giá trị tại thời điểm lấy mẫu. Dùng counter hoặc timer.
- **Tạo timer và counter trùng nghĩa:** timer đã có count của các lần ghi nhận.
- **Ghi metric sai thời điểm:** ghi nhận thành công trước khi transaction hoặc thao tác nghiệp vụ thực sự hoàn tất.
- **Đưa dữ liệu định danh vào tag:** làm cardinality tăng mạnh và có thể để lộ thông tin nhạy cảm.
- **Đăng ký meter trong vòng lặp nóng với tên hoặc tag biến thiên:** tạo nhiều series và tăng chi phí bộ nhớ, scrape, lưu trữ.
- **Bật histogram cho mọi metric mà không có mục tiêu:** histogram tăng số series và chi phí lưu trữ; chỉ bật khi cần phân tích phân phối.
- **Bật instrumentation hai lần:** binder thủ công và auto-configuration có thể cùng đăng ký một nhóm meter.
- **Cho rằng framework đo được toàn bộ nghiệp vụ:** auto metrics chủ yếu bao phủ các điểm tích hợp chuẩn, còn ý nghĩa nghiệp vụ phải được ứng dụng định nghĩa.

## 11. Checklist trước khi đưa instrumentation vào vận hành

- [ ] Mỗi metric trả lời một câu hỏi vận hành cụ thể.
- [ ] Loại meter phù hợp với dữ liệu: counter, gauge, timer hoặc distribution summary.
- [ ] Tên metric ổn định, có ý nghĩa và không chứa dữ liệu biến thiên.
- [ ] Nhãn có tập giá trị hữu hạn, không chứa ID hoặc dữ liệu nhạy cảm.
- [ ] Điểm ghi nhận phản ánh đúng ranh giới nghiệp vụ.
- [ ] Đã kiểm tra binder hoặc auto-configuration hiện có để tránh đo trùng.
- [ ] Unit test xác minh giá trị và nhãn; integration test xác minh đường xuất metrics khi cần.
- [ ] Histogram và percentile được bật có chủ đích theo nhu cầu truy vấn.
- [ ] Endpoint metrics được bảo vệ phù hợp với môi trường triển khai.

Khi kết hợp đúng ba lớp, framework cung cấp nền tảng quan sát chuẩn, thư viện cung cấp số đo của các thành phần hạ tầng, còn mã nghiệp vụ bổ sung những tín hiệu chỉ ứng dụng mới hiểu. Tất cả đi qua Micrometer để được chuẩn hóa, xuất ra backend và sử dụng trong dashboard hoặc cảnh báo.

