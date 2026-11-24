# Tạo meter bằng phương thức tiện ích hoặc builder

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `MeterRegistry` là điểm đăng ký và quản lý các meter mà ứng dụng dùng để ghi nhận hoạt động. Micrometer cung cấp hai cách tạo meter phổ biến: gọi phương thức tiện ích trực tiếp trên registry hoặc cấu hình meter bằng builder rồi đăng ký vào registry. Cả hai cách đều tạo meter trong cùng registry và dùng chung cơ chế nhận diện theo tên cùng tag.

Bài này trình bày cách chọn giữa hai cách tạo, cách ghi nhận dữ liệu sau khi tạo và cách áp dụng cho `Counter`, `Timer`, `DistributionSummary` cùng `Gauge`. Ví dụ dùng Micrometer Core; trong Spring Boot, hãy inject `MeterRegistry` đã được cấu hình thay vì tự tạo registry trong từng bean.

## 1. Hai cách tạo meter

Phương thức tiện ích của `MeterRegistry` phù hợp khi cần một meter đơn giản với tên và tag. Ví dụ:

```java
Counter ordersCreated = registry.counter(
    "orders.created",
    "channel", "web");

Timer createDuration = registry.timer(
    "orders.create.duration",
    "result", "success");

DistributionSummary payloadSize = registry.summary(
    "orders.payload.size",
    "format", "json");
```

Mỗi lời gọi tìm meter có cùng định danh trong registry; nếu chưa có thì đăng ký meter mới, nếu đã có thì tái sử dụng meter đó. Sau khi lấy được meter, ứng dụng gọi phương thức ghi nhận tương ứng như `increment()` hoặc `record(...)`.

Builder cho phép khai báo thêm mô tả, đơn vị cơ sở và cấu hình phân phối trước khi đăng ký:

```java
Timer createDuration = Timer.builder("orders.create.duration")
    .description("Time spent creating an order")
    .tag("result", "success")
    .publishPercentileHistogram()
    .register(registry);
```

`register(registry)` đưa meter vào registry và trả về meter đã đăng ký. Builder phù hợp khi cấu hình mặc định chưa đủ, chẳng hạn cần bật histogram cho timer, đặt SLO hoặc cung cấp description để người vận hành hiểu metric.

| Nhu cầu | Cách nên dùng | Lý do |
| --- | --- | --- |
| Counter đơn giản với vài tag | `registry.counter(...)` | Ngắn gọn, dễ đọc |
| Timer đơn giản, không cần tùy chỉnh thống kê | `registry.timer(...)` | Tạo và lấy timer trực tiếp |
| Summary đơn giản | `registry.summary(...)` | Ghi nhận đại lượng nhanh chóng |
| Cần description hoặc base unit | Builder | Khai báo metadata tại chỗ đăng ký |
| Cần histogram, percentile hoặc SLO | Builder | Cấu hình thống kê phân phối rõ ràng |
| Gauge cần mô tả hoặc hàm đọc tùy chỉnh | `Gauge.builder(...)` | Nêu rõ object được quan sát và cách đọc giá trị |

Hai cách này không tạo hai cơ chế lưu trữ khác nhau. Nếu phương thức tiện ích và builder dùng cùng registry, tên, tag và loại meter, lời gọi sau sẽ nhận lại meter đã đăng ký trước đó. Vì vậy, hãy thống nhất nơi khai báo cấu hình để tránh thành phần đầu tiên đăng ký meter vô tình quyết định cấu hình mà các thành phần sau phải dùng.

## 2. Tạo Counter

`Counter` dùng để đếm sự kiện chỉ tăng, chẳng hạn số đơn được tạo hoặc số lần một tác vụ được chấp nhận. Cách tiện ích ngắn gọn:

```java
Counter ordersCreated = registry.counter(
    "orders.created",
    "channel", "web");

ordersCreated.increment();
ordersCreated.increment(3);
```

Counter trên biểu diễn số đơn hàng được tạo từ kênh `web`. Nếu cần metadata hoặc muốn gom phần khai báo metric ở một nơi, dùng builder:

```java
Counter ordersCreated = Counter.builder("orders.created")
    .description("Number of orders created")
    .tag("channel", "web")
    .register(registry);
```

Sau khi đăng ký, cách cập nhật counter giống nhau:

```java
ordersCreated.increment();
```

Không dùng counter để ghi một giá trị có thể tăng rồi giảm, như số request đang hoạt động tại thời điểm hiện tại. Trường hợp đó phù hợp với `Gauge`. Với thao tác đã được đo bằng `Timer`, timer vốn đã có số lần ghi nhận (`count`), vì vậy không cần tạo counter trùng nghĩa chỉ để đếm cùng những lần hoàn tất đó.

## 3. Tạo Timer

`Timer` đo thời lượng và số lần một thao tác được ghi nhận. Với phép đo đơn giản, lấy timer từ registry rồi dùng `record`:

```java
Timer createDuration = registry.timer("orders.create.duration");

Order order = createDuration.record(
    () -> orderService.create(command));
```

`record(Supplier)` đo thời gian thực thi của hàm và trả lại kết quả. Nếu thao tác phát sinh exception, exception được truyền tiếp ra caller; timer vẫn ghi nhận thời lượng của lần thực thi.

Khi cần phân tích percentile hoặc histogram ở backend hỗ trợ, dùng builder để khai báo thống kê:

```java
Timer createDuration = Timer.builder("orders.create.duration")
    .description("Time spent creating an order")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1))
    .register(registry);
```

Sau đó ghi nhận như với timer được tạo bằng phương thức tiện ích:

```java
Order order = createDuration.record(
    () -> orderService.create(command));
```

Nếu tag chỉ được biết sau khi thao tác hoàn tất, có thể dùng `Timer.Sample` để chọn timer đích khi dừng phép đo:

```java
Timer successTimer = Timer.builder("orders.create.duration")
    .tag("result", "success")
    .register(registry);
Timer failureTimer = Timer.builder("orders.create.duration")
    .tag("result", "failure")
    .register(registry);

Timer.Sample sample = Timer.start(registry);
try {
    Order order = orderService.create(command);
    sample.stop(successTimer);
    return order;
} catch (RuntimeException exception) {
    sample.stop(failureTimer);
    throw exception;
}
```

Hai timer có cùng tên nhưng khác tag `result`, nên là hai meter riêng. Trong ứng dụng thật, hãy đăng ký chúng một lần khi khởi tạo bean, không tạo builder mới cho mỗi request.

## 4. Tạo DistributionSummary

`DistributionSummary` đo phân phối của một đại lượng không phải thời gian, ví dụ kích thước payload, số phần tử trong batch hoặc số byte được xử lý. Với trường hợp đơn giản:

```java
DistributionSummary payloadSize = registry.summary(
    "orders.payload.size",
    "format", "json");

payloadSize.record(payload.length);
```

Khi cần đơn vị và histogram, dùng builder:

```java
DistributionSummary payloadSize =
    DistributionSummary.builder("orders.payload.size")
        .description("Size of an order payload")
        .baseUnit("bytes")
        .tag("format", "json")
        .publishPercentileHistogram()
        .register(registry);
```

Rồi gọi `record(...)` với giá trị cần quan sát:

```java
payloadSize.record(payload.length);
```

`Timer` và `DistributionSummary` đều hỗ trợ thống kê phân phối, nhưng chúng có ý nghĩa khác nhau: timer đo thời gian và chuẩn hóa đơn vị thời gian; summary ghi nhận giá trị số do ứng dụng cung cấp. Chọn đúng loại giúp backend và người đọc hiểu số liệu chính xác.

## 5. Tạo Gauge

`Gauge` quan sát giá trị hiện tại của một object. Phương thức tiện ích có thể đăng ký một object cùng hàm đọc giá trị:

```java
AtomicInteger pendingOrders = new AtomicInteger();

registry.gauge(
    "orders.queue.depth",
    pendingOrders,
    AtomicInteger::get);

pendingOrders.addAndGet(4);
```

Phương thức `registry.gauge(...)` trả lại object trạng thái được truyền vào để có thể tiếp tục sử dụng object đó; metric được đăng ký trong registry. Khi registry lấy số liệu, Micrometer gọi hàm đọc để lấy giá trị hiện tại. Với cách tiện ích này, hãy giữ tham chiếu mạnh tới `pendingOrders` trong bean hoặc thành phần quản lý queue.

Builder hữu ích khi cần description hoặc muốn biểu đạt rõ cấu hình gauge:

```java
Gauge.builder(
        "orders.queue.depth",
        pendingOrders,
        AtomicInteger::get)
    .description("Number of orders waiting to be processed")
    .register(registry);
```

Gauge không tích lũy mỗi lần thay đổi giá trị. Nếu queue tăng từ 2 lên 5 rồi giảm còn 3, gauge phản ánh giá trị hiện tại khi được đọc; nó không ghi lại chuỗi các giá trị 2, 5 và 3. Muốn đo số sự kiện đã xảy ra, hãy dùng counter; muốn ghi nhận phân phối của các giá trị theo từng lần thao tác, hãy cân nhắc `DistributionSummary`.

Một số gauge giữ tham chiếu yếu đến object được quan sát. Nếu object bị garbage collector thu hồi, gauge có thể không còn giá trị hợp lệ. Vì vậy, object như queue, collection hoặc atomic state cần có vòng đời đủ dài và được quản lý bởi bean sống lâu.

## 6. Ví dụ kết hợp trong một bean Spring

Ví dụ sau tập trung khai báo meter trong constructor và giữ lại tham chiếu để sử dụng trong các phương thức nghiệp vụ:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

@Component
public class CheckoutMetrics {
    private final Counter ordersCreated;
    private final Timer createDuration;
    private final DistributionSummary payloadSize;
    private final AtomicInteger pendingOrders = new AtomicInteger();

    public CheckoutMetrics(MeterRegistry registry) {
        this.ordersCreated = registry.counter(
            "orders.created", "channel", "web");

        this.createDuration = Timer.builder("orders.create.duration")
            .description("Time spent creating an order")
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
            .register(registry);

        this.payloadSize = DistributionSummary.builder("orders.payload.size")
            .description("Size of an order payload")
            .baseUnit("bytes")
            .tag("format", "json")
            .register(registry);

        Gauge.builder(
                "orders.queue.depth",
                pendingOrders,
                AtomicInteger::get)
            .description("Number of orders waiting to be processed")
            .register(registry);
    }

    public void orderCreated() {
        ordersCreated.increment();
    }

    public <T> T recordCreate(Supplier<T> operation) {
        return createDuration.record(operation);
    }

    public void recordPayload(byte[] payload) {
        payloadSize.record(payload.length);
    }

    public void setPendingOrders(int count) {
        pendingOrders.set(count);
    }
}
```

Trong bean này, counter và summary được tạo bằng phương thức tiện ích/builder tương ứng với nhu cầu; timer được cấu hình histogram và SLO bằng builder; gauge quan sát `pendingOrders`, là field sống cùng bean. Mỗi meter có một trách nhiệm đo lường riêng và được đăng ký một lần trong constructor.

## 7. Tên, tag và đơn vị cần nhất quán

Dù tạo bằng cách nào, meter vẫn cần tên ổn định, tag có cardinality thấp và đơn vị phù hợp. Ví dụ, các tên `orders.created`, `orders.create.duration` và `orders.payload.size` mô tả ba đại lượng khác nhau. Tag `channel=web` có thể hữu ích nếu số kênh được giới hạn; `orderId` hoặc `userId` thường không phù hợp vì mỗi giá trị có thể tạo một time series mới.

Builder không làm giảm cardinality tự động. Nếu builder đăng ký meter với tag chứa ID duy nhất cho mỗi request, ứng dụng vẫn tạo ra số lượng meter rất lớn. Hãy kiểm soát tập giá trị tag ở nơi tạo meter và chuẩn hóa các route HTTP thành route pattern.

Với meter có đơn vị, hãy khai báo base unit phù hợp khi builder hỗ trợ và ghi nhận giá trị theo cùng đơn vị. Ví dụ, payload được ghi theo byte thì `baseUnit("bytes")`; thời lượng của `Timer` được Micrometer xử lý theo đơn vị thời gian và backend có thể xuất dạng giây. Không trộn millisecond với second trong cùng một meter.

## 8. Kiểm thử hai cách tạo meter

`SimpleMeterRegistry` cho phép kiểm tra việc phương thức tiện ích và builder cùng đăng ký một định danh sẽ nhận lại cùng meter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

class MeterCreationTest {
    @Test
    void convenienceMethodAndBuilderReuseSameCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter fromRegistry = registry.counter(
            "orders.created", "channel", "web");
        Counter fromBuilder = Counter.builder("orders.created")
            .tag("channel", "web")
            .register(registry);

        assertSame(fromRegistry, fromBuilder);

        fromRegistry.increment();
        assertEquals(1.0, fromBuilder.count());
    }
}
```

Test xác nhận hai API dùng chung registry và định danh sẽ tái sử dụng meter. Các kiểm thử khác có thể xác minh tag khác tạo meter khác, timer ghi nhận số lần/thời lượng, summary ghi nhận giá trị và gauge đọc trạng thái hiện tại. Test với `SimpleMeterRegistry` không thay thế kiểm thử tích hợp endpoint của backend; nếu cần xác nhận histogram hoặc định dạng xuất, hãy kiểm tra registry/exporter tương ứng.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không thấy meter trong endpoint export | Meter được đăng ký vào registry khác với registry exporter đang dùng; meter bị filter từ chối; code chưa chạy đến điểm đăng ký |
| Builder không bật histogram như mong đợi | Meter cùng tên/tag đã được đăng ký trước với cấu hình khác; backend không hỗ trợ kiểu thống kê đó; cấu hình được đặt sai registry |
| Hai thành phần cập nhật cùng một counter | Chúng đăng ký cùng tên/tag trong cùng registry và đang dùng chung meter; kiểm tra xem việc cộng dồn có đúng ý nghĩa không |
| Gauge trả về `NaN` hoặc không đổi | Object bị thu hồi, object được quan sát không được cập nhật hoặc hàm đọc trả về giá trị không hợp lệ |
| Số lượng series tăng nhanh | Tag có giá trị không giới hạn như ID, URL thô hoặc dữ liệu người dùng |
| Timer và summary cho số liệu khó hiểu | Chọn sai loại meter hoặc ghi nhận các giá trị không cùng đơn vị/ý nghĩa |

Khi không chắc nên dùng API nào, hãy bắt đầu từ câu hỏi vận hành: cần đếm sự kiện, quan sát trạng thái hiện tại, đo thời gian hay ghi nhận phân phối của một đại lượng? Sau khi chọn đúng loại meter, dùng phương thức tiện ích cho cấu hình đơn giản và builder khi cần mô tả hoặc điều chỉnh thống kê.

## 10. Nguyên tắc áp dụng

Phương thức tiện ích của `MeterRegistry` giúp tạo meter nhanh và dễ đọc cho các trường hợp phổ biến. Builder cung cấp nơi khai báo chi tiết khi cần description, base unit, histogram, percentile hoặc SLO. Cả hai đều đăng ký vào registry và tuân theo cùng quy tắc tái sử dụng theo tên cùng tag.

Hãy đăng ký meter một lần trong bean sống lâu, giữ tham chiếu để ghi nhận nhiều lần, inject registry dùng chung và định nghĩa tag có cardinality được kiểm soát. Với Gauge, giữ object được quan sát đủ lâu và cập nhật chính object đó. Cách tổ chức này giúp số liệu có ý nghĩa nhất quán từ lúc ứng dụng ghi nhận đến khi backend giám sát đọc và phân tích.
