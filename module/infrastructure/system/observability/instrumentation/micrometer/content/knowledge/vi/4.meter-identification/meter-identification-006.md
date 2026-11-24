# Đăng ký nhiều lần cùng tên và tag sử dụng lại meter như thế nào

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, Micrometer giúp ứng dụng Java ghi nhận counter, gauge, timer và distribution summary qua một API thống nhất. Để các số liệu có thể tổng hợp và phân tích, ứng dụng cần đăng ký meter với tên và tag ổn định. Khi nhiều thành phần trong cùng ứng dụng đăng ký lại cùng một meter, `MeterRegistry` có cơ chế nhận diện và tái sử dụng meter đã tồn tại.

Bài này giải thích cách Micrometer xác định một meter, điều gì xảy ra khi đăng ký lặp, các trường hợp tạo meter riêng, xung đột loại meter và những điểm cần chú ý với `Gauge`. Các ví dụ sử dụng API Micrometer Core và `SimpleMeterRegistry` để minh họa hành vi trong một registry.

## 1. Meter được nhận diện bằng tên và tag

Trong một `MeterRegistry`, định danh của meter dựa trên tên và tập tag của nó. Có thể hiểu một meter là một chuỗi số liệu có tên, được chia thành các chiều phân tích bởi các cặp key/value của tag.

Ví dụ, hai lời gọi sau đăng ký cùng một meter:

```java
Counter first = registry.counter(
    "orders.created",
    "channel", "web");

Counter second = registry.counter(
    "orders.created",
    "channel", "web");
```

Vì tên đều là `orders.created` và tag đều là `channel=web`, registry tìm thấy meter đã đăng ký và trả lại chính meter đó. `first` và `second` tham chiếu cùng một đối tượng `Counter`; chúng không phải hai bộ đếm độc lập.

```java
first.increment();
second.increment();

System.out.println(first.count());  // 2.0
System.out.println(second.count()); // 2.0
```

Việc đăng ký lần thứ hai không đặt counter về 0 và không tạo thêm một series riêng. Hai biến cùng cập nhật một counter đã được registry quản lý.

| Lời gọi đăng ký | Kết quả trong cùng registry |
| --- | --- |
| Cùng tên, cùng key/value tag | Tái sử dụng meter đã có |
| Cùng tên, tag có value khác | Tạo meter có định danh khác |
| Cùng tên, có thêm hoặc thiếu tag | Tạo meter có định danh khác |
| Tên khác, tag giống nhau | Tạo meter có định danh khác |
| Cùng tên và tag nhưng loại meter khác | Xung đột loại meter; không thể dùng chung định danh cho hai loại |

Thứ tự truyền các tag không mang ý nghĩa phân biệt. Điều cần giữ ổn định là tập cặp key/value tag. Ví dụ, `channel=web` và `region=apac` mô tả cùng tập chiều dù thứ tự các cặp được truyền vào khác nhau.

## 2. Cùng tên nhưng tag khác sẽ tạo chuỗi số liệu khác

Tag là chiều phân tích của meter. Khi một tag value thay đổi, Micrometer xem đó là một định danh khác. Điều này cho phép phân tích số đơn hàng theo kênh:

```java
Counter webCounter = registry.counter(
    "orders.created", "channel", "web");
Counter mobileCounter = registry.counter(
    "orders.created", "channel", "mobile");

webCounter.increment(3);
mobileCounter.increment(5);
```

Hai meter có cùng tên `orders.created`, nhưng có tag lần lượt là `channel=web` và `channel=mobile`. Chúng giữ số đếm riêng. Với backend dạng time series như Prometheus, chúng thường được biểu diễn thành hai series cùng tên metric nhưng khác label.

Tag cần có tập giá trị hữu hạn và mang ý nghĩa phân tích rõ ràng. Các giá trị như `channel`, `payment_method`, `result` có thể phù hợp nếu được giới hạn trong danh sách đã biết. Những giá trị thay đổi gần như theo từng request như `orderId`, `userId`, email, trace ID, URL thô hoặc timestamp sẽ tạo rất nhiều định danh khác nhau.

Ví dụ, nếu mỗi đơn hàng dùng một `orderId` làm tag thì mỗi ID tạo một meter riêng. Số lượng meter và time series có thể tăng liên tục, làm tăng bộ nhớ, dung lượng lưu trữ và chi phí truy vấn. Hãy dùng tag để mô tả nhóm có thể tổng hợp; dùng log hoặc trace để tra cứu một đơn hàng hay request cụ thể.

## 3. Cơ chế tái sử dụng trong MeterRegistry

Các phương thức tiện ích của registry như `counter(...)`, `timer(...)` hoặc `summary(...)` thực hiện việc tìm hoặc đăng ký meter theo định danh. Các builder cũng kết thúc bằng việc đăng ký vào registry:

```java
Counter counter = Counter.builder("orders.created")
    .description("Number of orders created")
    .tag("channel", "web")
    .register(registry);

Timer timer = Timer.builder("orders.create.duration")
    .description("Time spent creating an order")
    .tag("result", "success")
    .register(registry);
```

Khi một meter cùng định danh và cùng loại đã tồn tại, lời gọi `register(registry)` trả về meter hiện có. Hành vi này cũng áp dụng khi hai bean khác nhau cùng dùng một `MeterRegistry` được Spring Boot quản lý và đăng ký đúng cùng tên/tag.

Phạm vi tái sử dụng là từng registry. Hai đối tượng `SimpleMeterRegistry` khác nhau có bộ meter và số liệu độc lập. Tương tự, hai tiến trình ứng dụng có registry riêng; hệ thống giám sát thường tổng hợp series từ nhiều instance dựa trên các label của môi trường triển khai.

Vì vậy, hãy để các thành phần trong cùng ứng dụng nhận `MeterRegistry` dùng chung qua dependency injection. Không tự tạo registry mới trong controller, service hoặc mỗi lần xử lý request. Việc tạo registry riêng khiến meter bị tách khỏi registry mà exporter đang đọc.

## 4. Đăng ký một lần, giữ tham chiếu để ghi nhận nhiều lần

Registry có thể trả về meter đã có ngay cả khi code gọi phương thức đăng ký nhiều lần. Tuy nhiên, với đường xử lý thường xuyên, nên đăng ký meter một lần trong lúc khởi tạo bean và giữ tham chiếu để dùng lại. Cách này làm rõ nơi định nghĩa metric, tránh lặp cấu hình và không phải tra cứu registry trên mỗi thao tác.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class OrderMetrics {
    private final Counter createdFromWeb;
    private final Timer createTimer;

    public OrderMetrics(MeterRegistry registry) {
        this.createdFromWeb = Counter.builder("orders.created")
            .description("Number of orders created from web")
            .tag("channel", "web")
            .register(registry);

        this.createTimer = Timer.builder("orders.create.duration")
            .description("Time spent creating an order")
            .register(registry);
    }

    public void orderCreatedFromWeb() {
        createdFromWeb.increment();
    }

    public <T> T recordCreate(Supplier<T> operation) {
        return createTimer.record(operation);
    }
}
```

Trong ví dụ này, constructor đăng ký hai meter khi Spring tạo bean `OrderMetrics`. Mỗi lần nghiệp vụ tạo đơn hoàn tất, ứng dụng gọi `orderCreatedFromWeb()` để tăng counter; `recordCreate(...)` ghi thời lượng vào timer đã đăng ký. Các lần ghi nhận tiếp theo cập nhật meter hiện có.

Nếu nhiều bean cùng đăng ký một meter, chúng vẫn có thể nhận về cùng đối tượng. Dù vậy, nên thống nhất tên, tag, đơn vị và ý nghĩa metric tại một vị trí dễ tìm. Hai nhóm code vô tình dùng chung tên/tag cho hai khái niệm khác nhau sẽ làm số liệu bị cộng dồn và rất khó phát hiện chỉ bằng cách xem dashboard.

## 5. Loại meter cũng phải nhất quán

Tên và tag xác định định danh. Loại meter quyết định cách ghi nhận và cách diễn giải số liệu. Vì vậy, cùng tên và tag phải được dùng cho cùng một loại meter.

Ví dụ, đoạn code sau tạo xung đột:

```java
Counter databaseCalls = registry.counter(
    "database.operation", "system", "orders");

// Cùng tên và tag nhưng yêu cầu loại Timer.
Timer databaseLatency = registry.timer(
    "database.operation", "system", "orders");
```

Lời gọi thứ hai không thể biến counter hiện có thành timer. Registry phát hiện cùng định danh nhưng khác loại meter và báo lỗi đăng ký (thường là `IllegalArgumentException`). Không dùng chung tên/tag cho `Counter`, `Timer`, `Gauge` hoặc `DistributionSummary` nếu chúng biểu diễn các phép đo khác nhau.

Hãy chọn tên mô tả đúng đại lượng và loại meter ngay từ đầu:

| Mục đích | Ví dụ tên | Loại phù hợp |
| --- | --- | --- |
| Đếm số đơn được tạo | `orders.created` | `Counter` |
| Đo thời gian tạo đơn | `orders.create.duration` | `Timer` |
| Quan sát số đơn đang chờ xử lý | `orders.queue.depth` | `Gauge` |
| Đo kích thước payload đơn hàng | `orders.payload.size` | `DistributionSummary` |

Tên khác nhau giúp người đọc hiểu ý nghĩa của số liệu và tránh xung đột khi nhiều thành phần cùng đăng ký meter.

## 6. Cấu hình ở lần đăng ký đầu tiên

Builder cho phép khai báo description, base unit và cấu hình phân phối như histogram, percentile hoặc SLO. Các thông tin này mô tả cách meter được xuất và thống kê. Chúng không phải chiều tag để tạo một meter song song.

Ví dụ, hai đoạn code sau dùng cùng tên và tag nhưng khai báo histogram khác nhau:

```java
Timer first = Timer.builder("orders.create.duration")
    .tag("result", "success")
    .publishPercentileHistogram()
    .register(registry);

Timer second = Timer.builder("orders.create.duration")
    .tag("result", "success")
    .register(registry);
```

`second` nhận lại timer đã đăng ký. Lời gọi thứ hai không tạo timer thứ hai và cũng không thay thế cấu hình histogram của meter đang tồn tại. Vì thế, cần định nghĩa cấu hình meter nhất quán ở nơi khởi tạo, trước khi các thành phần khác bắt đầu sử dụng nó.

Điều tương tự cần được lưu ý với description và base unit: đăng ký lặp không phải cơ chế cập nhật metadata cho meter đã tạo. Tránh để các bean khác nhau khai báo cùng tên/tag với mô tả hoặc cấu hình phân phối mâu thuẫn.

## 7. Trường hợp đặc biệt của Gauge

`Gauge` khác với counter và timer ở chỗ nó quan sát giá trị hiện tại của một đối tượng. Nó không tích lũy số lần sự kiện xảy ra. Khi registry lấy số liệu, hàm đọc của gauge được gọi để lấy giá trị mới nhất.

```java
import io.micrometer.core.instrument.Gauge;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger pendingOrders = new AtomicInteger();

Gauge.builder("orders.queue.depth", pendingOrders, AtomicInteger::get)
    .description("Number of orders waiting to be processed")
    .register(registry);

pendingOrders.incrementAndGet();
pendingOrders.addAndGet(2);
```

Gauge quan sát `pendingOrders`; giá trị sẽ là 3 khi registry đọc nó sau các cập nhật trên. Ứng dụng thay đổi đối tượng được quan sát, còn registry chỉ đọc giá trị khi cần xuất metric.

Một lưu ý quan trọng: nếu đăng ký lại cùng tên/tag bằng một đối tượng khác, registry trả về gauge đã tồn tại. Gauge cũ tiếp tục quan sát đối tượng được truyền vào ở lần đăng ký đầu tiên; đối tượng mới không tự thay thế nguồn dữ liệu.

```java
AtomicInteger firstQueue = new AtomicInteger(2);
AtomicInteger secondQueue = new AtomicInteger(9);

Gauge firstGauge = Gauge.builder(
        "orders.queue.depth", firstQueue, AtomicInteger::get)
    .register(registry);

Gauge secondGauge = Gauge.builder(
        "orders.queue.depth", secondQueue, AtomicInteger::get)
    .register(registry);
```

Hai lời gọi có cùng định danh. `secondGauge` trỏ đến gauge đã đăng ký; gauge đó vẫn quan sát `firstQueue`. Vì vậy, không dùng thao tác đăng ký lặp để chuyển gauge từ một collection hoặc object sang object khác. Hãy giữ một object sống lâu và cập nhật chính object đó.

Một số gauge giữ tham chiếu yếu đến object được quan sát. Nếu object không còn tham chiếu mạnh ở nơi khác, garbage collector có thể thu hồi nó và gauge có thể trả về `NaN`. Hãy giữ collection, queue hoặc atomic value trong một bean sống lâu; chỉ dùng tùy chọn giữ tham chiếu mạnh khi đã cân nhắc vòng đời và bộ nhớ của object.

## 8. Bộ lọc có thể thay đổi định danh

`MeterFilter` cho phép từ chối meter, đổi tên, thêm/bớt tag hoặc cấu hình thống kê trước khi meter được đăng ký. Vì vậy, định danh cuối cùng trong registry có thể khác với tên/tag ban đầu mà code truyền vào.

Ví dụ, một filter chuẩn hóa tên hoặc bỏ một tag có thể khiến hai lời gọi vốn khác nhau trở thành cùng một định danh sau khi áp dụng filter. Khi đó chúng có thể dùng chung meter. Ngược lại, filter có thể từ chối đăng ký khiến meter không xuất hiện trong registry.

```java
import io.micrometer.core.instrument.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsConfiguration {

@Bean
MeterFilter commonPrefix() {
    return MeterFilter.renameTag(
        "orders.created",
        "source",
        "channel");
}
}
```

Đây là ví dụ minh họa việc chuẩn hóa key tag. Khi dùng filter trong ứng dụng thật, hãy kiểm tra kỹ các key/value sau khi biến đổi để tránh làm hai chiều phân tích khác nhau bị gộp ngoài ý muốn. Cấu hình filter nên được thiết lập sớm, nhất quán trước khi meter được đăng ký.

## 9. Kiểm thử hành vi đăng ký lặp

`SimpleMeterRegistry` phù hợp để kiểm thử logic đăng ký mà không cần kết nối backend metrics. Test có thể xác minh hai lần đăng ký cùng định danh trả về cùng meter, số đếm được cộng dồn, và tag khác tạo meter riêng.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

class MeterIdentityTest {
    @Test
    void reusesMeterWithSameNameAndTags() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter first = registry.counter(
            "orders.created", "channel", "web");
        Counter second = registry.counter(
            "orders.created", "channel", "web");

        assertSame(first, second);

        first.increment();
        second.increment();

        assertEquals(2.0, first.count());
    }

    @Test
    void createsDifferentMeterWhenTagValueChanges() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter web = registry.counter(
            "orders.created", "channel", "web");
        Counter mobile = registry.counter(
            "orders.created", "channel", "mobile");

        assertNotSame(web, mobile);

        web.increment(2);
        mobile.increment(4);

        assertEquals(2.0, web.count());
        assertEquals(4.0, mobile.count());
    }
}
```

Hai kiểm thử trên chứng minh hành vi cốt lõi của định danh. Có thể bổ sung kiểm thử cho trường hợp đăng ký khác loại meter cùng tên/tag và trường hợp Gauge được đăng ký lại với object khác. Ở cấp tích hợp, hãy kiểm tra endpoint metrics của ứng dụng để xác nhận tên và tag thực tế sau khi các `MeterFilter` đã được áp dụng.

## 10. Quy tắc thực hành

Khi thiết kế instrumentation, hãy thống nhất tên meter và tập tag trước khi nhiều thành phần cùng sử dụng. Mỗi tổ hợp tên/tag nên biểu diễn đúng một ý nghĩa và một loại meter. Đăng ký meter trong constructor hoặc cấu hình bean, giữ tham chiếu để ghi nhận ở đường xử lý thường xuyên, và để Spring Boot cung cấp registry dùng chung.

Khi xem số liệu, hãy nhớ rằng đăng ký lặp cùng tên/tag trong cùng registry dùng chung một meter và cộng dồn các lần ghi nhận. Tag khác tạo chuỗi số liệu khác; registry khác giữ dữ liệu độc lập. Với `Gauge`, object được quan sát ở lần đăng ký đầu tiên cần có vòng đời đủ dài. Những nguyên tắc này giúp metric ổn định, dễ đọc và có cardinality được kiểm soát khi ứng dụng mở rộng.
