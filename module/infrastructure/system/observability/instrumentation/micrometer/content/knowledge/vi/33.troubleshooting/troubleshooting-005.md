# Đăng ký trùng, khác loại meter hoặc thiếu nhất quán tập khóa tag

## Mục tiêu

Micrometer cho phép nhiều thành phần trong ứng dụng cùng sử dụng một MeterRegistry. Điều đó thuận tiện khi controller, service, binder và thư viện đều muốn ghi metrics. Tuy nhiên, nếu các thành phần đặt tên meter hoặc tag không theo cùng một quy ước, registry có thể trả lại meter đã tồn tại, từ chối meter mới hoặc exporter không xuất được dữ liệu như mong đợi.

Ba tình huống cần phân biệt:

- Cùng meter name và cùng tag values được đăng ký nhiều lần.
- Cùng meter identity nhưng một nơi tạo Counter, nơi khác tạo Timer hoặc Gauge.
- Cùng metric name nhưng các meter dùng tập tag keys khác nhau.

Hai tình huống đầu liên quan đến identity và loại meter trong MeterRegistry. Tình huống thứ ba còn phụ thuộc registry backend và phiên bản exporter. Prometheus đặc biệt khuyến nghị schema metric nhất quán; một số phiên bản Micrometer Prometheus cũ còn thực thi giới hạn tập tag keys ngay khi đăng ký.

Sau bài này, bạn có thể:

- Nhận biết đăng ký lặp có chủ đích và đăng ký lặp do lỗi thiết kế.
- Xử lý xung đột khi cùng identity được dùng cho nhiều loại meter.
- Chuẩn hóa tập tag keys cho mọi series của cùng metric name.
- Chọn giá trị fallback cho tag tùy chọn mà vẫn giữ đúng ý nghĩa.
- Dùng MeterFilter mà không vô tình gộp hoặc làm mất series.
- Bật thông báo lỗi đăng ký meter và kiểm tra dữ liệu thực tế được export.

## Meter identity được hình thành như thế nào?

Một meter có tên và các tag mô tả dimension. Ví dụ:

~~~text
http.server.requests{
  method="GET",
  route="/orders/{orderId}",
  outcome="SUCCESS"
}
~~~

Trong một registry, name cùng các tag key/value xác định meter cần tìm hoặc tạo. MeterFilter có thể biến đổi Meter.Id trước khi registry lưu meter, vì vậy identity cuối cùng còn phụ thuộc các filter đã cấu hình.

Các trường description và base unit giúp mô tả meter hoặc quy đổi khi export; chúng không phải cách để tạo một meter độc lập cùng name/tag. Nếu cùng identity được đăng ký lần nữa, registry dùng meter đã có. Thay description hoặc cấu hình histogram trong lần register sau không phải cách cập nhật meter cũ.

| Trường hợp | Kết quả thường gặp |
|---|---|
| Cùng name, cùng tag keys và values, cùng loại meter | Dùng lại meter đã đăng ký |
| Cùng name và tags nhưng khác loại meter | MeterRegistry ném IllegalArgumentException |
| Cùng name và tag keys nhưng khác tag values | Tạo các meter/series khác nhau |
| Cùng name nhưng khác tập tag keys | Phụ thuộc registry; Prometheus khuyến nghị schema keys nhất quán |
| MeterFilter biến đổi hai ID khác nhau thành cùng ID | Các registration có thể hội tụ vào cùng meter |

Tag values khác nhau là cách thông thường để tạo các series của cùng một metric. Tag keys cần có schema ổn định để các series có thể được truy vấn và export nhất quán.

## Tình huống 1: đăng ký cùng meter nhiều lần

### Cùng Counter hoặc Timer được đăng ký lặp

Đăng ký cùng name, tags và type nhiều lần không tạo nhiều meter độc lập. Registry trả về meter đã tồn tại:

~~~java
Counter first = registry.counter(
        "business.orders.created",
        "channel", "web"
);

Counter second = registry.counter(
        "business.orders.created",
        "channel", "web"
);

first.increment();
second.increment();
~~~

Hai biến tham chiếu cùng một meter. Sau hai lần increment, count của series là 2. Đây có thể là hành vi mong muốn khi nhiều component cùng ghi một sự kiện vào cùng metric.

Tuy nhiên, đăng ký lặp có thể che giấu cấu hình không nhất quán. Ví dụ, component đầu tạo Timer không bật histogram; component sau đăng ký cùng name/tags nhưng bật percentile histogram. Lần đăng ký sau không tạo một Timer mới để thay cấu hình trước. Hãy cấu hình meter tại một nơi có thẩm quyền và dùng lại meter đó ở các component khác.

### Gauge đăng ký lặp cần chú ý hơn

Gauge thường quan sát một object bằng weak reference. Khi cùng name/tags được đăng ký lại với object khác, registry giữ gauge đầu tiên và bỏ qua registration sau; một số loại meter như Gauge, FunctionCounter và FunctionTimer còn ghi cảnh báo double registration.

Ví dụ dễ gây lỗi:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicInteger;

void registerQueueGauge(MeterRegistry registry) {
    AtomicInteger queueSize = new AtomicInteger();

    Gauge.builder("worker.queue.size", queueSize, AtomicInteger::get)
            .tag("queue", "email")
            .register(registry);
}
~~~

Sau khi phương thức kết thúc, không còn strong reference nào giữ queueSize. Vì Gauge giữ weak reference, object có thể bị garbage collector thu hồi và giá trị gauge có thể không còn hữu ích.

Giữ state object trong một bean hoặc field có vòng đời dài:

~~~java
public final class EmailQueueMetrics {
    private final AtomicInteger queueSize = new AtomicInteger();

    public EmailQueueMetrics(MeterRegistry registry) {
        Gauge.builder("worker.queue.size", queueSize, AtomicInteger::get)
                .tag("queue", "email")
                .register(registry);
    }

    public void updateSize(int size) {
        queueSize.set(size);
    }
}
~~~

Chỉ đăng ký gauge một lần cho state object có vòng đời rõ ràng. Những nơi khác cập nhật state object thay vì tạo gauge mới với cùng identity.

### Cách xử lý đăng ký lặp

1. Xác định việc nhiều component dùng chung meter có phải chủ đích hay không.
2. Nếu cùng sự kiện cần được cộng dồn, inject meter đã tạo hoặc dùng cùng name/tags/type.
3. Nếu cần đại lượng khác, đặt metric name riêng.
4. Đưa description, base unit và distribution configuration về một nơi cấu hình.
5. Với Gauge, giữ state object bằng một field có vòng đời đủ dài.
6. Kiểm tra cảnh báo double registration trong startup log.

Không cố tạo meter mới bằng cách thêm tag giả chỉ để tránh cảnh báo. Làm vậy tạo thêm series và thay đổi ý nghĩa metric.

## Tình huống 2: cùng identity nhưng khác loại meter

### Vì sao xảy ra xung đột?

Giả sử một component tạo Counter:

~~~java
registry.counter(
        "worker.job.execution",
        "queue", "email"
).increment();
~~~

Component khác lại tạo Timer với cùng name và tags:

~~~java
registry.timer(
        "worker.job.execution",
        "queue", "email"
).record(Duration.ofMillis(120));
~~~

Đây là cùng identity nhưng hai loại meter khác nhau. MeterRegistry không thể trả về một Counter khi caller yêu cầu Timer. Micrometer ném IllegalArgumentException với thông báo tương tự:

~~~text
There is already a registered meter of a different type
(CumulativeCounter vs. CumulativeTimer) with the same name
~~~

Tên class cụ thể phụ thuộc registry implementation. Hãy đọc đầy đủ exception để xác định meter đã được đăng ký trước và loại meter đang được yêu cầu.

### Đặt tên theo đại lượng được đo

Counter đếm số sự kiện. Timer đo thời lượng và đồng thời cung cấp count cùng total time. Nếu cần cả số job và thời gian chạy, có thể dùng hai metric name khác nhau:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public final class JobMetrics {
    private final Counter submittedJobs;
    private final Timer jobDuration;

    public JobMetrics(MeterRegistry registry) {
        this.submittedJobs = Counter.builder("worker.jobs.submitted")
                .tag("queue", "email")
                .register(registry);
        this.jobDuration = Timer.builder("worker.job.duration")
                .tag("queue", "email")
                .register(registry);
    }

    public void recordSubmission() {
        submittedJobs.increment();
    }

    public void recordExecution(Duration duration) {
        jobDuration.record(duration);
    }
}
~~~

Trong ví dụ, Counter đếm lượt submit còn Timer đo thời gian thực thi đã hoàn tất; đây là hai sự kiện khác nhau nên có hai tên riêng. Nếu chỉ cần số lần Timer hoàn tất, không cần tạo Counter thứ hai cho cùng sự kiện. Dùng Timer.count() hoặc metric count do backend export.

Quy ước đặt tên gợi ý:

| Đại lượng | Meter | Ví dụ tên |
|---|---|---|
| Số lần job hoàn tất | Counter | worker.jobs.completed |
| Thời gian chạy job | Timer | worker.job.duration |
| Queue size hiện tại | Gauge | worker.queue.size |
| Tổng byte xử lý theo từng payload | DistributionSummary | worker.payload.size |
| Số tác vụ đang chạy và thời gian hiện tại | LongTaskTimer | worker.job.active |

Không dùng cùng một name/tag set cho Counter, Timer, Gauge, DistributionSummary hoặc FunctionCounter. Nếu hai đại lượng khác semantics, chúng cần tên metric riêng ngay cả khi cùng được nhóm trong một dashboard.

### Cùng name nhưng tag values khác nhau vẫn có thể xung đột ở backend

Trong MeterRegistry lõi, tag values khác nhau tạo identity khác nhau. Nhưng một backend như Prometheus còn có quy tắc cho metric family: cùng tên metric không nên đại diện cho các loại dữ liệu khác nhau.

Vì vậy, đừng dựa vào việc thêm tag value để phân biệt Counter với Timer có cùng tên. Đặt metric name riêng theo đại lượng và xác minh tên sau khi registry áp dụng naming convention.

### Hai tên Micrometer khác nhau có thể trùng tên sau khi export

Prometheus exporter có thể thêm hậu tố hoặc sinh các series phụ. Ví dụ, Counter có hậu tố _total; Timer có thể xuất các series count, sum, max và bucket. Vì vậy, hai tên Micrometer khác nhau vẫn có thể ánh xạ thành cùng metric name ở Prometheus:

~~~java
registry.counter("test").increment();
registry.counter("test.total").increment(42);
~~~

Ở các phiên bản Micrometer cũ, trường hợp này có thể khiến một meter bị che khuất trong scrape. Hướng dẫn migration 1.17.0 mô tả cơ chế phát hiện duplicate Prometheus names và registration failure cho trường hợp ánh xạ trùng. Một va chạm khác là Gauge dùng tên trùng với series phụ do Timer tạo ra, chẳng hạn hậu tố _seconds_max.

Khi chẩn đoán, kiểm tra cả tên Micrometer lẫn tên cuối cùng mà exporter sinh ra. Tránh đặt tên ứng dụng trùng với các hậu tố chuẩn mà registry dùng để xuất Counter, Timer hoặc histogram.

## Tình huống 3: tập tag keys không nhất quán

### Ví dụ thiếu tag key

Hai component cùng tạo metric business.payment.attempts:

~~~java
registry.counter(
        "business.payment.attempts",
        "channel", "web"
).increment();

registry.counter(
        "business.payment.attempts",
        "outcome", "rejected"
).increment();
~~~

Meter thứ nhất có tag key channel; meter thứ hai có tag key outcome. Chúng là hai Meter.Id khác nhau, nhưng cùng metric name lại có schema dimension khác nhau.

Prometheus khuyến nghị mọi meter có cùng tên dùng cùng tập tag keys. Các phiên bản Micrometer Prometheus cũ có thể từ chối registration tiếp theo và chỉ ghi warning; điều này khiến một series không xuất hiện trong scrape.

### Cách sửa: luôn cung cấp đủ keys

Nếu hai dimension đều thuộc cùng metric, mọi registration phải cung cấp cả hai key:

~~~java
registry.counter(
        "business.payment.attempts",
        "channel", "web",
        "outcome", "success"
).increment();

registry.counter(
        "business.payment.attempts",
        "channel", "not_applicable",
        "outcome", "rejected"
).increment();
~~~

Trong trường hợp thứ hai, channel=not_applicable có nghĩa dimension channel không áp dụng cho sự kiện đó. Nếu channel thực sự không biết, dùng unknown; nếu giá trị không nằm trong danh sách được hỗ trợ, dùng other. Đừng dùng các giá trị này thay thế lẫn nhau nếu chúng có ý nghĩa nghiệp vụ khác nhau.

Nếu một dimension hoàn toàn không có ý nghĩa đối với một nhóm sự kiện, hãy cân nhắc đặt metric name khác thay vì ép tất cả sự kiện vào cùng schema.

### Phân biệt thiếu tag key và thiếu tag value

Đây là hai trường hợp khác nhau:

~~~java
// Thiếu key: schema không nhất quán.
registry.counter("business.payment.attempts", "channel", "web");
registry.counter("business.payment.attempts", "outcome", "success");

// Có đủ key nhưng giá trị thể hiện không áp dụng.
registry.counter("business.payment.attempts",
        "channel", "web", "outcome", "success");
registry.counter("business.payment.attempts",
        "channel", "not_applicable", "outcome", "rejected");
~~~

Không bỏ cặp key/value khi dữ liệu đầu vào null. Chuẩn hóa thành một giá trị fallback trước khi tạo meter.

## Xây dựng schema tag tập trung

Một cách hiệu quả để tránh sai khác giữa các component là tạo helper sinh tags. Helper phải luôn trả về cùng tập key theo cùng thứ tự quy ước:

~~~java
import io.micrometer.core.instrument.Tags;

public final class PaymentMetricTags {
    private PaymentMetricTags() {
    }

    public static Tags of(
            String channel,
            String outcome) {
        return Tags.of(
                "channel", normalizeChannel(channel),
                "outcome", normalizeOutcome(outcome)
        );
    }

    private static String normalizeChannel(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }
        return switch (value) {
            case "web", "mobile", "store" -> value;
            default -> "other";
        };
    }

    private static String normalizeOutcome(String value) {
        if ("success".equals(value)) {
            return "success";
        }
        if ("rejected".equals(value)) {
            return "rejected";
        }
        if ("failed".equals(value)) {
            return "failed";
        }
        return "other";
    }
}
~~~

Mọi component dùng cùng helper:

~~~java
Counter.builder("business.payment.attempts")
        .tags(PaymentMetricTags.of(channel, outcome))
        .register(registry)
        .increment();
~~~

Không tạo helper riêng trong từng service với quy tắc normalize khác nhau. Nếu cần thêm dimension, cập nhật schema có kiểm soát và thay đổi mọi điểm đăng ký liên quan.

### Tag key là một phần của hợp đồng metric

Với mỗi metric name, ghi rõ:

- Danh sách tag keys bắt buộc.
- Ý nghĩa của từng key.
- Tập giá trị cho phép.
- Giá trị fallback khi không có dữ liệu.
- Component hoặc module sở hữu schema.

Ví dụ:

| Metric name | Tag keys bắt buộc | Giá trị fallback |
|---|---|---|
| business.payment.attempts | channel, outcome | unknown, other |
| worker.job.duration | queue, result | unknown, other |
| http.server.requests | method, route, outcome | UNKNOWN, NOT_FOUND, UNKNOWN |

Thay đổi tag key cần được review như thay đổi API telemetry. Dashboard, alert, recording rule và truy vấn có thể phụ thuộc vào schema đó.

## MeterFilter có thể giúp gì?

MeterFilter cho phép từ chối meter, biến đổi Meter.Id hoặc cấu hình distribution statistics. Filter được áp dụng theo thứ tự và nên được đăng ký trước khi meter đầu tiên được tạo.

### Thêm common tags

Nếu mọi meter cần cùng tag application và region, có thể thêm ở registry:

~~~java
registry.config().commonTags(
        "application", "orders-api",
        "region", "ap-southeast-1"
);
~~~

Common tags hữu ích cho dimension triển khai dùng chung. Chúng không thay thế schema tag riêng của metric. Không khai báo cùng key ở cả common tags và meter-specific tags với giá trị khác nhau; chọn một nguồn có thẩm quyền cho mỗi key.

### Bỏ tag hoặc chuẩn hóa tag value

Một số filter tiện ích:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

import java.util.Set;

registry.config()
        .meterFilter(MeterFilter.ignoreTags("debug.id"))
        .meterFilter(MeterFilter.replaceTagValues(
                "channel",
                value -> Set.of("web", "mobile", "store").contains(value)
                        ? value
                        : "other"
        ));
~~~

ignoreTags() loại tag key khỏi các meter trong registry. replaceTagValues() chuẩn hóa value của một key. Các filter này có thể giảm cardinality hoặc loại dimension không cần thiết, nhưng chúng cũng có thể làm nhiều identity khác nhau hội tụ thành cùng một meter.

Trước khi dùng filter để gộp giá trị, hãy xác nhận việc tổng hợp đó có đúng nghĩa nghiệp vụ. Filter không thể biến hai loại meter khác nhau thành hai metric family hợp lệ nếu chúng vẫn dùng cùng tên.

### Giới hạn số tag values không sửa được schema thiếu key

maximumAllowableTags() giới hạn số giá trị của một tag key cho một nhóm meter name. Nó bảo vệ cardinality; nó không tự thêm tag key bị thiếu cho những meter khác.

Nếu cần chuyển đổi schema, hãy thực hiện ở helper hoặc instrumentation trước khi đăng ký. Dùng MeterFilter như lớp bảo vệ bổ sung, không dùng thay cho một schema thống nhất.

### Cẩn thận khi filter làm hai ID hội tụ

Ví dụ, filter đổi mọi channel ngoài allow-list thành other. Nếu các registration trước đó khác nhau chỉ ở channel, chúng có thể cùng ánh xạ thành một Meter.Id. Cùng type thì dữ liệu có thể được gộp; khác type có thể gây xung đột.

Hãy xem xét cả ID trước filter và sau filter khi chẩn đoán. Không đổi tag key hoặc value toàn cục mà chưa kiểm tra tác động tới các meter đã đăng ký.

## Khác biệt phiên bản Prometheus registry

Không phải mọi phiên bản Prometheus registry xử lý tập tag keys khác nhau theo cùng một cách:

- Các phiên bản Micrometer Prometheus cũ yêu cầu meter cùng name có cùng tập tag keys. Registration không phù hợp có thể bị từ chối; mặc định thường chỉ có warning nên lỗi dễ bị bỏ qua.
- Hướng dẫn migration Micrometer 1.17.0 ghi nhận việc nâng Prometheus Java client lên 1.7.0 và loại bỏ restriction cũ ở registry đối với tập tag names khác nhau.
- Tài liệu Micrometer hiện hành vẫn khuyến nghị mạnh rằng các meter cùng name nên dùng cùng tập tag keys. Cách này giữ schema dễ hiểu, dễ truy vấn và tương thích hơn giữa backend.
- micrometer-registry-prometheus dùng Prometheus Java client mới; micrometer-registry-prometheus-simpleclient dùng client legacy. Hãy kiểm tra dependency và version thực tế trước khi suy luận hành vi.

Vì vậy, schema nhất quán vẫn là lựa chọn an toàn cho instrumentation đa backend và giúp tránh thay đổi hành vi khi nâng cấp.

## Bật lỗi registration để phát hiện sớm

Mặc định một số registration failure có thể chỉ được ghi log. Trong môi trường test, có thể chuyển registration failure thành exception:

~~~java
registry.config().onMeterRegistrationFailed((id, reason) -> {
    throw new IllegalStateException(
            "Meter registration failed: " + id + ": " + reason
    );
});
~~~

Với PrometheusMeterRegistry ở các phiên bản hỗ trợ shortcut, có thể bật:

~~~java
prometheusRegistry.throwExceptionOnRegistrationFailure();
~~~

Đặt cấu hình này trong test hoặc môi trường phát triển để lỗi schema xuất hiện ngay tại điểm đăng ký. Trong production, chọn chính sách phù hợp với khả năng chịu lỗi của ứng dụng; tối thiểu phải thu thập và cảnh báo registration failure.

Listener này xử lý các registration failure được registry báo về. Xung đột cùng identity nhưng khác loại meter được kiểm tra trực tiếp trong MeterRegistry và ném IllegalArgumentException; hãy kiểm thử hoặc bắt lỗi đó riêng.

## Quy trình chẩn đoán

Khi một metric không xuất hiện, bị gộp hoặc có warning, kiểm tra theo thứ tự:

1. Tìm warning hoặc exception tại thời điểm ứng dụng khởi động và khi meter được tạo.
2. Xác định metric name chính xác trước và sau naming convention.
3. Liệt kê tất cả meter cùng name trong registry.
4. So sánh loại meter và tập tag keys của từng Meter.Id.
5. Kiểm tra giá trị tag có null, thiếu hoặc được chuẩn hóa khác nhau không.
6. Kiểm tra common tags và toàn bộ MeterFilter theo thứ tự.
7. Kiểm tra các meter có cùng name nhưng khác loại hoặc bị Prometheus đổi thành cùng metric family không.
8. Đọc scrape output để xác minh meter thật sự được export.
9. So sánh hành vi với version của Micrometer và Prometheus client đang chạy.

Có thể liệt kê meter trong registry:

~~~java
registry.getMeters().stream()
        .filter(meter -> meter.getId().getName()
                .equals("business.payment.attempts"))
        .forEach(meter -> {
            System.out.printf("name=%s, type=%s, tags=%s%n",
                    meter.getId().getName(),
                    meter.getId().getType(),
                    meter.getId().getTags());
        });
~~~

Đoạn này cho thấy meter đã được đăng ký trong registry và các tag hiện có. Nó không thay thế việc kiểm tra scrape output vì exporter còn áp dụng naming convention và quy tắc riêng.

### Dấu hiệu và nguyên nhân thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cảnh báo Gauge đã đăng ký | Nhiều component tạo Gauge cùng ID | Chỉ đăng ký một lần, dùng chung state object |
| IllegalArgumentException khác loại meter | Counter và Timer dùng cùng name/tags | Đổi metric name theo đại lượng |
| Prometheus báo khác tập tag keys | Một số registration thiếu tag | Chuẩn hóa schema và dùng fallback value |
| Meter có trong registry nhưng không có trong scrape | Registration failure hoặc tên export xung đột | Bật failure listener và kiểm tra scrape |
| Histogram config không thay đổi | Meter đã được đăng ký trước với cùng ID | Cấu hình trước registration hoặc dùng ID riêng khi semantics khác |
| Nhiều series ngoài dự kiến | Tag values không được chuẩn hóa hoặc filter tạo ID khác nhau | Chuẩn hóa values và rà soát cardinality |
| Hai meter biến thành cùng series | MeterFilter bỏ/đổi tag làm ID hội tụ | Kiểm tra mapping và ý nghĩa tổng hợp |

## Kiểm thử để ngăn lỗi quay lại

### Kiểm thử đăng ký lặp và khác loại

SimpleMeterRegistry phù hợp để kiểm tra hành vi lõi của MeterRegistry:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeterIdentityTest {

    @Test
    void sameIdentityReturnsTheExistingCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter first = registry.counter(
                    "business.jobs.completed", "queue", "email");
            Counter second = registry.counter(
                    "business.jobs.completed", "queue", "email");

            assertThat(second).isSameAs(first);
        } finally {
            registry.close();
        }
    }

    @Test
    void differentMeterTypeWithSameIdentityFails() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            registry.counter("worker.job.execution", "queue", "email");

            assertThatThrownBy(() ->
                    registry.timer("worker.job.execution", "queue", "email"))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("different type");
        } finally {
            registry.close();
        }
    }
}
~~~

Test thứ nhất xác nhận đăng ký cùng identity không tạo meter thứ hai. Test thứ hai xác nhận xung đột type được phát hiện ngay trong registry lõi.

### Kiểm thử schema tag keys

Kiểm tra helper luôn tạo đủ key, kể cả khi input null:

~~~java
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Tags;
import org.junit.jupiter.api.Test;

import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentMetricTagsTest {

    @Test
    void alwaysReturnsTheSameTagKeySet() {
        Tags tags = PaymentMetricTags.of(null, "success");

        Set<String> keys = tags.stream()
                .map(Tag::getKey)
                .collect(Collectors.toSet());

        assertThat(keys).containsExactlyInAnyOrder("channel", "outcome");
        assertThat(tags.stream()
                .filter(tag -> tag.getKey().equals("channel"))
                .findFirst()
                .orElseThrow()
                .getValue()).isEqualTo("unknown");
    }
}
~~~

### Kiểm thử Prometheus exporter

SimpleMeterRegistry không mô phỏng các quy tắc export của Prometheus. Nếu production dùng Prometheus, cần thêm integration test với đúng dependency và version registry mà ứng dụng triển khai:

- Tạo các meter cùng name qua mọi code path đại diện.
- Gọi scrape() và xác minh các series cần thiết xuất hiện.
- Bật registration failure exception trong test nếu registry version hỗ trợ.
- Xác minh không có warning hoặc registration failure bị bỏ qua.
- Kiểm tra metric names sau khi áp dụng Prometheus naming convention.

Không khóa test vào một hành vi khác phiên bản nếu dự án nâng Micrometer/Prometheus client. Hãy kiểm thử schema mà ứng dụng yêu cầu: các tag keys ổn định, meter type rõ ràng và scrape output hợp lệ.

## Những lỗi thường gặp

**Cho rằng gọi builder nhiều lần tạo nhiều meter.** Cùng identity thường trả về meter đã tồn tại. Nếu muốn đại lượng khác, đặt tên khác.

**Dùng cùng name cho Counter và Timer.** Cùng name/tag identity nhưng khác type sẽ gây exception. Timer đã có count nên thường không cần Counter trùng tên.

**Đăng ký Gauge từ object cục bộ.** Gauge có thể giữ weak reference; giữ state object trong bean hoặc field có vòng đời dài.

**Chỉ thêm tag khi có giá trị.** Các registration của cùng metric name sẽ có tập keys khác nhau. Luôn cung cấp fallback hoặc tách metric name.

**Dùng giá trị fallback không có semantics.** unknown, other và not_applicable cần ý nghĩa riêng, không dùng tùy tiện.

**Cho rằng Prometheus registry mọi version đều xử lý tag keys giống nhau.** Kiểm tra Micrometer và Prometheus client version; vẫn giữ schema thống nhất để tương thích.

**Dùng MeterFilter để che lỗi thiết kế.** Filter có thể loại hoặc đổi tag, nhưng cũng có thể gộp series. Sửa schema ở nguồn trước.

**Đặt common tag trùng với tag cục bộ.** Nhiều nguồn cùng sở hữu một key có thể gây giá trị không nhất quán. Chỉ định một nguồn có thẩm quyền.

**Bỏ qua registration warning.** Một meter không được đăng ký có thể khiến dashboard thiếu dữ liệu dù code vẫn chạy.

**Chỉ test SimpleMeterRegistry.** Test lõi không xác minh naming convention và quy tắc scrape của backend. Thêm integration test exporter đang dùng.

## Checklist triển khai

1. Định nghĩa metric name theo một đại lượng và semantics rõ ràng.
2. Xác định tag key set cố định cho mỗi metric name.
3. Chuẩn hóa tag values và xử lý null bằng fallback có ý nghĩa.
4. Dùng cùng meter type cho cùng identity.
5. Tách Counter, Timer, Gauge và DistributionSummary bằng metric names phù hợp.
6. Đăng ký Gauge một lần và giữ state object đủ lâu.
7. Cấu hình description, base unit và histogram trước lần registration đầu.
8. Đăng ký common tags và MeterFilter trước khi meter được tạo.
9. Kiểm tra filter không làm các ID khác nhau hội tụ ngoài ý muốn.
10. Bật registration failure listener trong test.
11. Kiểm tra tag keys và Meter.Id trong registry.
12. Kiểm tra scrape output bằng đúng Prometheus registry version.
13. Rà soát warning sau khi nâng cấp Micrometer hoặc exporter.

## Kết luận

Lỗi đăng ký meter thường xuất phát từ việc nhiều thành phần không dùng chung một quy ước về name, type và tag schema. Cùng identity được đăng ký lặp sẽ dùng meter đầu tiên; cùng identity nhưng khác type gây lỗi; còn cùng metric name với tập tag keys khác nhau có thể làm exporter từ chối hoặc xử lý khác nhau theo phiên bản. Hãy đặt metric name theo đại lượng, dùng helper tạo tag schema cố định, chuẩn hóa giá trị thiếu, cấu hình MeterFilter trước registration và kiểm thử cả registry lẫn scrape output. Những quy tắc này giúp metrics nhất quán khi ứng dụng mở rộng hoặc thay đổi backend.

## Tài liệu tham khảo

- [Micrometer - MeterRegistry API](https://docs.micrometer.io/micrometer/reference/api.html): cách registry quản lý meter và identity.
- [Micrometer - Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus): yêu cầu schema tag keys nhất quán, scrape output và xử lý registration failure.
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): biến đổi Meter.Id, common tags, ignoreTags, replaceTagValues và giới hạn tag values.
- [Micrometer 1.17 Migration Guide](https://github.com/micrometer-metrics/micrometer/wiki/1.17-Migration-Guide): thay đổi Prometheus Java client và hành vi metric name/label khi nâng cấp.
- [Micrometer MeterRegistry source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java): hành vi đăng ký cùng ID và kiểm tra meter type.
