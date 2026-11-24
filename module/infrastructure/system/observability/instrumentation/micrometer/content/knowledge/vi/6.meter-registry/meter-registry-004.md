# SimpleMeterRegistry để quan sát giá trị trong bộ nhớ

`SimpleMeterRegistry` là một triển khai `MeterRegistry` của Micrometer lưu các phép đo trong bộ nhớ của tiến trình. Ứng dụng có thể đăng ký counter, gauge, timer và distribution summary, cập nhật chúng khi nghiệp vụ chạy, rồi đọc lại giá trị ngay trong Java. Registry này phù hợp cho ví dụ nhỏ, chẩn đoán cục bộ và đặc biệt hữu ích trong unit test instrumentation.

Vì dữ liệu chỉ nằm trong bộ nhớ của tiến trình, `SimpleMeterRegistry` không tự gửi metrics đến Prometheus, Datadog hay hệ thống giám sát từ xa. Khi tiến trình dừng hoặc registry được tạo mới, các giá trị tích lũy trong registry cũ không còn. Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, nó giúp kiểm tra cách dùng meter trước khi xác minh việc export bằng registry dành cho backend thực tế.

## 1. Tạo và sử dụng SimpleMeterRegistry

Lớp `SimpleMeterRegistry` nằm trong package `io.micrometer.core.instrument.simple`. Khi dùng Java độc lập, cần có Micrometer Core trên classpath. Với ứng dụng Spring Boot, Micrometer Core thường đã được đưa vào thông qua Actuator hoặc dependency Micrometer tương ứng.

Tạo registry trực tiếp:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
```

Sau đó đăng ký meter và cập nhật nó:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter created = Counter.builder("orders.created")
        .description("Number of created orders")
        .tag("channel", "web")
        .register(registry);

created.increment();
created.increment(2.0);

double total = registry.get("orders.created")
        .tag("channel", "web")
        .counter()
        .count();

System.out.println(total); // 3.0
```

Registry nhận diện meter bằng tên và tập tag; type, base unit và description mô tả cách meter hoạt động. Khi builder đăng ký lại cùng meter ID với cấu hình tương thích, Micrometer trả về meter đã được đăng ký thay vì tạo một chuỗi đo độc lập cho mỗi lần gọi. Do đó, các thao tác tăng counter cùng meter ID sẽ cộng dồn vào cùng giá trị trong registry đó. Không đăng ký cùng một tên và tập tag với type xung đột.

Trong ví dụ trên, `registry.get(...).tag(...).counter()` là cách lấy meter đã có và đọc số đếm. Có thể dùng `registry.find(...)` khi muốn tìm meter theo cách có thể không tìm thấy:

```java
Counter found = registry.find("orders.created")
        .tag("channel", "web")
        .counter();

if (found != null) {
    System.out.println(found.count());
}
```

`find` trả về `null` nếu không có meter phù hợp. Dùng nó khi cần kiểm tra sự tồn tại mà không muốn tạo meter mới chỉ để đọc.

## 2. Quan sát các loại meter

`SimpleMeterRegistry` hỗ trợ các meter phổ biến của Micrometer. Sau khi ghi nhận, có thể đọc giá trị bằng API tương ứng.

### Counter: đếm sự kiện

Counter biểu diễn một giá trị chỉ tăng, chẳng hạn số đơn hàng được tạo thành công:

```java
Counter ordersCreated = Counter.builder("orders.created")
        .tag("channel", "web")
        .register(registry);

ordersCreated.increment();
ordersCreated.increment(3.0);

double count = registry.get("orders.created")
        .tag("channel", "web")
        .counter()
        .count();
```

Giá trị `count` bằng tổng số lần tăng kể từ khi meter được tạo trong registry. Counter không phải nơi lưu số lượng hiện tại có thể tăng lẫn giảm; với trạng thái hiện tại như số tác vụ đang chờ, hãy dùng gauge.

### Gauge: đọc trạng thái hiện tại

Gauge lấy giá trị từ một đối tượng được theo dõi. Ví dụ dùng `AtomicInteger` để biểu diễn số worker đang hoạt động:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger activeWorkers = new AtomicInteger(2);

Gauge.builder("worker.active", activeWorkers, AtomicInteger::get)
        .register(registry);

activeWorkers.set(5);

double active = registry.get("worker.active")
        .gauge()
        .value();
```

Gauge đọc giá trị tại thời điểm gọi `value()`, vì vậy kết quả phản ánh trạng thái mới nhất mà đối tượng cung cấp. Micrometer thường giữ tham chiếu yếu đến đối tượng được gauge theo dõi. Ứng dụng cần giữ một tham chiếu mạnh đến đối tượng đó trong suốt thời gian cần quan sát; nếu đối tượng bị thu gom bởi garbage collector, gauge có thể không còn đọc được giá trị hữu ích.

Trong ứng dụng thật, đối tượng được theo dõi thường là field có vòng đời phù hợp, chẳng hạn queue hoặc bộ đếm trạng thái do component quản lý. Tránh tạo một object tạm thời chỉ để đăng ký gauge rồi để nó mất tham chiếu ngay sau đó.

### Timer: đo thời lượng

Timer ghi nhận số lần thực hiện và tổng thời gian. Với `SimpleMeterRegistry`, có thể đọc count và tổng thời lượng tích lũy:

```java
import java.util.concurrent.TimeUnit;

Timer processing = Timer.builder("orders.processing")
        .register(registry);

processing.record(25, TimeUnit.MILLISECONDS);
processing.record(40, TimeUnit.MILLISECONDS);

Timer recorded = registry.get("orders.processing").timer();

long count = recorded.count();
double totalMillis = recorded.totalTime(TimeUnit.MILLISECONDS);
```

Sau hai lần record, `count` là 2 và `totalMillis` xấp xỉ 65.0. Thời lượng được lưu nội bộ theo độ phân giải của clock và được chuyển đổi khi đọc bằng `TimeUnit` yêu cầu. Trong code nghiệp vụ, nên dùng `Timer.record(...)` hoặc `Timer.Sample` để đo đúng đoạn công việc cần quan sát.

### DistributionSummary: đo phân phối đại lượng số

Distribution summary phù hợp với đại lượng số không phải thời gian, chẳng hạn kích thước payload hoặc số bản ghi trong một batch:

```java
DistributionSummary payloadSize = DistributionSummary.builder("payload.size")
        .baseUnit("bytes")
        .register(registry);

payloadSize.record(512.0);
payloadSize.record(1024.0);

DistributionSummary recorded = registry.get("payload.size").summary();

long count = recorded.count();
double totalBytes = recorded.totalAmount();
```

Sau hai lần ghi nhận, `count` là 2 và `totalBytes` là 1536.0. `baseUnit` mô tả đơn vị để người đọc hiểu số đo; nó không thay đổi ý nghĩa của giá trị mà ứng dụng truyền vào `record`.

## 3. Ví dụ hoàn chỉnh quan sát nhiều meter

Ví dụ sau đăng ký một counter, gauge, timer và distribution summary trên cùng một registry. Dùng cùng một registry giúp quan sát các meter như một tập dữ liệu trong bộ nhớ:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class InMemoryMetricsExample {
    public static void main(String[] args) {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Counter orders = Counter.builder("orders.created")
                    .tag("channel", "web")
                    .register(registry);
            orders.increment(3.0);

            AtomicInteger activeWorkers = new AtomicInteger(4);
            Gauge.builder("worker.active", activeWorkers, AtomicInteger::get)
                    .register(registry);

            Timer processing = Timer.builder("orders.processing")
                    .register(registry);
            processing.record(25, TimeUnit.MILLISECONDS);
            processing.record(40, TimeUnit.MILLISECONDS);

            DistributionSummary payload = DistributionSummary
                    .builder("payload.size")
                    .baseUnit("bytes")
                    .register(registry);
            payload.record(512.0);
            payload.record(1024.0);

            System.out.println("orders=" + registry.get("orders.created")
                    .tag("channel", "web").counter().count());
            System.out.println("workers=" + registry.get("worker.active")
                    .gauge().value());
            System.out.println("processing.count=" + registry
                    .get("orders.processing").timer().count());
            System.out.println("processing.total.ms=" + registry
                    .get("orders.processing").timer()
                    .totalTime(TimeUnit.MILLISECONDS));
            System.out.println("payload.count=" + registry
                    .get("payload.size").summary().count());
            System.out.println("payload.total=" + registry
                    .get("payload.size").summary().totalAmount());
        }
    }
}
```

Kết quả dự kiến về mặt số lượng là `orders=3.0`, `workers=4.0`, `processing.count=2`, `processing.total.ms` xấp xỉ `65.0`, `payload.count=2` và `payload.total=1536.0`. Giá trị timer có thể có sai số nhỏ do cách đo thời gian và độ phân giải clock.

`try`-with-resources đóng registry khi ví dụ kết thúc. Trong ứng dụng chạy lâu, registry thường được quản lý theo vòng đời của ứng dụng hoặc dependency injection container. Không tạo registry mới cho mỗi request hay mỗi lần thực hiện nghiệp vụ, vì khi đó meter sẽ bị phân tán vào các registry riêng và giá trị không còn được cộng dồn như mong muốn.

## 4. Dùng SimpleMeterRegistry trong unit test

Một lợi ích quan trọng của `SimpleMeterRegistry` là kiểm thử instrumentation mà không cần khởi động Prometheus hoặc một hệ thống giám sát. Mỗi test có thể tạo registry riêng, gọi component cần kiểm tra và xác minh meter sau khi thực thi.

Ví dụ component ghi nhận đơn hàng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {
    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
```

Unit test dùng registry trong bộ nhớ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderMetricsTest {
    @Test
    void incrementsCreatedCounter() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);

            metrics.recordCreated();
            metrics.recordCreated();

            double count = registry.get("orders.created")
                    .tag("channel", "web")
                    .counter()
                    .count();

            assertEquals(2.0, count);
        }
    }
}
```

Test này kiểm tra component đã tăng đúng counter và đăng ký meter với tag mong đợi. Nó không cần mạng, backend metrics hoặc cấu hình export. Có thể áp dụng cách tương tự để kiểm tra timer được record đúng số lần, summary nhận đúng tổng giá trị và gauge đọc trạng thái mới nhất.

Mỗi test nên có registry riêng để dữ liệu không rò rỉ giữa các test. Nếu dùng chung một registry tĩnh, counter có thể tiếp tục tăng từ test trước, khiến kết quả phụ thuộc thứ tự chạy. Đóng registry sau test cũng giúp giải phóng tài nguyên gắn với vòng đời registry.

## 5. Quan sát meter theo tên và tag

Tên meter cùng tag tạo thành định danh dùng để phân biệt các chuỗi đo. Ví dụ, hai counter `orders.created` có tag `channel=web` và `channel=mobile` là hai meter ID khác nhau trong cùng registry.

```java
Counter.builder("orders.created")
        .tag("channel", "web")
        .register(registry)
        .increment(2.0);

Counter.builder("orders.created")
        .tag("channel", "mobile")
        .register(registry)
        .increment(5.0);

double web = registry.get("orders.created")
        .tag("channel", "web").counter().count();
double mobile = registry.get("orders.created")
        .tag("channel", "mobile").counter().count();
```

Có thể duyệt meter đã đăng ký để kiểm tra cấu trúc:

```java
registry.getMeters().forEach(meter -> {
    System.out.println(meter.getId().getName());
    System.out.println(meter.getId().getType());
    System.out.println(meter.getId().getTags());
});
```

Không tạo tag từ giá trị gần như duy nhất như order ID, user ID, request ID hoặc email. Dù `SimpleMeterRegistry` có thể lưu các meter với nhiều tag khác nhau, điều đó không có nghĩa thiết kế đó an toàn khi chuyển sang hệ thống giám sát thật. Cardinality cao sẽ làm tăng số chuỗi dữ liệu và chi phí lưu trữ ở backend. Hãy dùng tag có tập giá trị hữu hạn, ổn định.

## 6. SimpleMeterRegistry và registry dùng để export

Các triển khai `MeterRegistry` có chung API ghi nhận nhưng khác nhau về cách quản lý và xuất dữ liệu.

| Registry | Mục đích | Đặc điểm |
| --- | --- | --- |
| `SimpleMeterRegistry` | Ví dụ, kiểm thử và quan sát cục bộ | Lưu số đo trong bộ nhớ của tiến trình; không tự export đến backend từ xa |
| `PrometheusMeterRegistry` | Công bố metrics cho Prometheus scrape | Chuyển meter sang exposition format Prometheus |
| `OtlpMeterRegistry` | Gửi metrics qua OpenTelemetry Protocol | Export theo cấu hình OTLP và endpoint nhận dữ liệu |
| `StatsdMeterRegistry` | Gửi metrics qua StatsD | Chuyển meter sang thông điệp theo giao thức StatsD |

Nếu ứng dụng Spring Boot cần Prometheus, hãy khai báo Prometheus registry và cấu hình Actuator endpoint. `SimpleMeterRegistry` không thay thế registry adapter đó. Nếu cần kiểm thử việc export, hãy dùng integration test với đúng registry adapter hoặc kiểm tra endpoint export trong môi trường kiểm thử.

Trong một unit test, có thể inject `SimpleMeterRegistry` trực tiếp vào component cần kiểm tra vì constructor nhận abstraction `MeterRegistry`. Ở runtime, Spring có thể inject registry do auto-configuration cung cấp. Cách viết này giữ cho component không phải phụ thuộc vào lớp cụ thể như `SimpleMeterRegistry` hoặc `PrometheusMeterRegistry`.

## 7. Giới hạn cần hiểu khi đọc số đo trong bộ nhớ

`SimpleMeterRegistry` phù hợp để trả lời câu hỏi: “Trong tiến trình và registry này, meter đang ghi nhận giá trị gì?”. Nó không đại diện cho toàn bộ hệ thống phân tán.

Một số giới hạn quan trọng:

- **Phạm vi một tiến trình:** registry chỉ thấy phép đo được ghi vào chính instance đó. Nhiều JVM hoặc nhiều replica không tự chia sẻ dữ liệu.
- **Không lưu bền vững:** khi tiến trình kết thúc hoặc registry bị loại bỏ, dữ liệu trong bộ nhớ mất đi.
- **Không tự export:** registry không tự gửi dữ liệu đến backend và không cung cấp định dạng Prometheus exposition chỉ vì meter đã được đăng ký.
- **Không thay thế kiểm thử tích hợp:** nó xác minh hành vi instrumentation, nhưng không xác minh scrape, xác thực, mạng, định dạng export hoặc truy vấn backend.
- **Giá trị phụ thuộc thời điểm:** gauge đọc trạng thái hiện tại; timer và summary phản ánh những lần ghi nhận đã xảy ra trong vòng đời meter.

Vì vậy, không dùng số liệu từ một `SimpleMeterRegistry` trong một replica để kết luận tổng lưu lượng hoặc tổng trạng thái của toàn bộ cụm. Với mục tiêu đó, cần export metrics từ từng instance và tổng hợp ở backend giám sát.

## 8. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo `SimpleMeterRegistry` cho mỗi request | Mỗi registry chỉ giữ một phần dữ liệu, không có số tổng hợp | Dùng một registry có vòng đời phù hợp với ứng dụng hoặc test |
| Dùng Simple registry và chờ Prometheus scrape | Không có Prometheus exposition endpoint từ registry này | Dùng Prometheus registry cho đường export |
| Dùng chung registry tĩnh giữa các unit test | Số đo bị cộng dồn và test phụ thuộc thứ tự | Tạo registry mới cho mỗi test và đóng sau test |
| Đăng ký gauge với object tạm thời | Object có thể bị garbage collector thu hồi; gauge mất nguồn dữ liệu | Giữ tham chiếu mạnh đến object được theo dõi |
| Dùng counter cho giá trị tăng giảm | Không biểu diễn đúng trạng thái hiện tại | Dùng gauge cho giá trị có thể tăng hoặc giảm |
| Dùng tag có giá trị duy nhất theo request | Tạo cardinality lớn khi chuyển sang registry production | Chuẩn hóa tag về tập giá trị hữu hạn |
| Cho rằng test Simple registry xác minh tên export | Có thể bỏ sót lỗi naming convention hoặc cấu hình registry | Thêm integration test với registry adapter thật |

## 9. Quy trình thực hành

Khi dùng `SimpleMeterRegistry` để quan sát một instrumentation, thực hiện lần lượt:

1. Tạo một `SimpleMeterRegistry` có vòng đời giới hạn cho ví dụ hoặc test.
2. Inject registry vào component qua kiểu `MeterRegistry`.
3. Đăng ký meter bằng tên canonical, type và tag có ý nghĩa.
4. Chạy thao tác nghiệp vụ hoặc test để cập nhật meter.
5. Đọc lại counter, gauge, timer hoặc summary qua API tương ứng.
6. Xác minh giá trị, type và tag; đảm bảo object được gauge theo dõi còn được giữ tham chiếu.
7. Đóng registry khi hoàn thành test hoặc ví dụ.
8. Nếu mục tiêu là vận hành production, kiểm tra lại cùng instrumentation với registry adapter và backend thực tế.

`SimpleMeterRegistry` cung cấp một cách đơn giản để nhìn thấy tác động của instrumentation ngay trong bộ nhớ. Dùng nó để phát triển và kiểm thử logic ghi nhận; dùng registry adapter phù hợp để công bố metrics đến hệ thống giám sát. Tách hai mục tiêu này giúp unit test nhanh, dễ lặp lại và vẫn bảo đảm đường export được xác minh ở cấp tích hợp.
