# Meter bị trùng tên trong Spring Boot và Micrometer

Trong chương **Metrics nền tảng** của module **SPRING_BOOT_OBSERVABILITY**, một vấn đề dễ gặp khi thêm metrics vào ứng dụng Spring Boot là **nhiều meter được đăng ký với cùng một tên**. Có trường hợp đó là hành vi bình thường: Micrometer trả lại meter đã đăng ký để mọi nơi cùng ghi nhận vào một chuỗi số liệu. Nhưng cũng có trường hợp tên trùng gây **xung đột loại meter, sai ngữ nghĩa, trùng phép đo hoặc lỗi khi xuất metrics**.

Để thiết lập observability đáng tin cậy bằng Micrometer Observation, metrics, logs và distributed tracing, người học cần phân biệt:

1. **Đăng ký lại đúng cùng một meter**: thường được tái sử dụng.
2. **Cùng tên nhưng khác tags**: có thể là các chuỗi dữ liệu riêng của cùng một họ metric.
3. **Cùng tên nhưng khác loại/định nghĩa**: có thể xung đột ngay trong registry hoặc tại exporter/backend.
4. **Hai phép đo cùng ý nghĩa**: dù không có lỗi kỹ thuật, số liệu có thể bị tính trùng.

Bài này giải thích danh tính của meter, các biểu hiện lỗi, cách kiểm tra và cách thiết kế tên/tag thống nhất để điều tra lỗi, độ trễ mà không phá dashboard.

## 1. Meter là gì, và tên meter có phải là danh tính duy nhất?

Trong Micrometer, **meter** là công cụ ghi số đo như `Counter`, `Gauge`, `Timer`, `DistributionSummary` hoặc `LongTaskTimer`. Nó được đăng ký vào một `MeterRegistry`. Mỗi meter có một `Meter.Id` chứa tên, tags, loại và các metadata như mô tả hoặc đơn vị.

Về mặt đăng ký meter trong một registry, hãy hiểu **tên cộng với tập tags** là phần quan trọng của danh tính. Vì vậy:

| Tên | Tags | Kết quả về mặt danh tính |
| --- | --- | --- |
| `orders.processed` | `outcome=success` | Meter A |
| `orders.processed` | `outcome=success` | **Cùng danh tính** với A; thường nhận lại meter đã có |
| `orders.processed` | `outcome=error` | Meter B, khác A do giá trị tag khác |
| `orders.processed` | `outcome=success,channel=web` | Meter C, khác A do tập tags khác |
| `orders.processed` | Không có tags | Meter D, khác A |

**Loại meter không phải cách để cố tình tạo hai meter khác nghĩa nhưng cùng tên và tags.** Ví dụ một `Counter` và một `Timer` cùng tên/tags sẽ không thể được xem là hai định nghĩa độc lập an toàn. Cách registry phản ứng với xung đột có thể khác giữa phiên bản và implementation, nhưng thiết kế đúng là đặt tên riêng cho hai đại lượng khác nhau.

Tương tự, chỉ đổi `description` hoặc `baseUnit` của một meter đã đăng ký với cùng tên/tags **không tạo ra một series mới**; metadata đã tồn tại có thể tiếp tục được sử dụng. Vì vậy phải giữ ý nghĩa, đơn vị và kiểu của tên metric ổn định.

### Sơ đồ tư duy

```text
MeterRegistry
    |
    +-- orders.processed + {outcome=success} --> Counter A
    |                         ^
    |                         +-- đăng ký lại cùng tên/tags --> dùng A
    |
    +-- orders.processed + {outcome=error}   --> Counter B
    |
    +-- orders.processing.duration + {channel=web}
                              |
                              +--> Timer C
```

Một lỗi ở dashboard không nhất thiết là “trùng tên” trong registry. Cần xác định **đang trùng tên Java, trùng danh tính sau khi tags được ánh xạ, hay trùng tên chuỗi metric ở backend**.

## 2. Trùng tên nhưng cùng loại và cùng tags: cơ chế tái sử dụng

Đây thường là trường hợp hợp lệ. Ví dụ với `micrometer-core`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class SameMeterDemo {
    public static void main(String[] args) {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Counter first = Counter.builder("orders.processed")
                    .tag("outcome", "success")
                    .register(registry);

            Counter second = Counter.builder("orders.processed")
                    .tag("outcome", "success")
                    .register(registry);

            first.increment();
            second.increment();

            System.out.println(first == second);   // true
            System.out.println(first.count());      // 2.0
        }
    }
}
```

Vì hai lần đăng ký có cùng tên/tags và cùng loại `Counter`, registry trả về cùng đối tượng meter. Hai lệnh `increment()` cộng vào **một counter**, chứ không tạo hai counter độc lập. Với `Timer`, việc đăng ký lại cùng danh tính cũng nhằm dùng chung phép đo được lưu trong registry, không tự tạo một lần đo mới.

Đây là lý do `registry.counter("orders.processed", "outcome", "success")` có thể được dùng ở nhiều nơi khi **chúng thật sự ghi cùng một loại sự kiện**.

Tuy nhiên, nếu hai chỗ gọi `increment()` cho **cùng một sự kiện nghiệp vụ**, tổng số đo vẫn bị tăng hai lần. Registry không hiểu một đơn hàng đã được đếm trước đó. **Khử trùng đăng ký meter không đồng nghĩa khử trùng sự kiện được ghi.**

### Khi nào nên tái sử dụng?

- Một domain event được ghi ở đúng **một điểm sở hữu**, còn nhiều đoạn code sử dụng tham chiếu cùng meter.
- Hai nguồn cùng đo một loại sự kiện độc lập nhưng thống nhất tên, đơn vị và tags.
- Một meter được đăng ký ở lúc khởi động và được dùng lặp lại trong hot path.

Không cần tạo meter mới cho mỗi request. Nếu tập tags hữu hạn, có thể lấy lại meter từ registry; với đường gọi tần suất cao, cân nhắc cache tham chiếu theo tập tag cố định để giảm thao tác tìm kiếm/khởi tạo builder. **Không cache meter theo user ID/order ID động**, vì số phần tử cache và số time series sẽ tăng không kiểm soát.

## 3. Cùng tên, khác tags: series hợp lệ hay thiết kế thiếu nhất quán?

Các tag values khác nhau thường tạo các **time series riêng**, đúng mục đích phân tích theo chiều dữ liệu.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public void recordOutcome(MeterRegistry registry, boolean approved) {
    String outcome = approved ? "approved" : "declined";
    Counter.builder("payment.authorization")
            .tag("outcome", outcome)
            .register(registry)
            .increment();
}
```

Kết quả kỳ vọng là hai chuỗi tương ứng `outcome=approved` và `outcome=declined`. Tên `payment.authorization` ở đây **cố ý giống nhau** vì đó là cùng đại lượng, được phân loại bằng một tag.

Nhưng hai điểm instrument có thể đăng ký như sau:

```text
payment.authorization{outcome="approved"}
payment.authorization{provider="bank_a"}
```

Trong registry, chúng có thể là hai danh tính khác nhau. Tuy nhiên, một họ metric có **tập tên nhãn thiếu nhất quán** dễ khiến truy vấn tổng hợp bị sai, và một số exporter/backend (đặc biệt các họ metric kiểu Prometheus) có thể yêu cầu nhất quán về tên/type/label names hoặc báo lỗi đăng ký/xuất dữ liệu.

Hãy thiết kế **một schema tags cho một tên metric**; giá trị có thể khác nhau nhưng nên duy trì cùng các **key** và cùng ngữ nghĩa. Nếu không biết provider, dùng giá trị hữu hạn như `unknown` hoặc `none` theo quy ước của nhóm, thay vì lúc có `provider` lúc không có.

Một metric HTTP với nhãn `uri="/orders/{id}"` đúng hướng chuẩn hóa hơn so với nhãn `uri="/orders/12345"`. Dù tên metric không đổi, URI thô tạo quá nhiều tag values và vẫn gây **cardinality explosion**.

## 4. Cùng tên/tags nhưng khác loại meter: xung đột đăng ký

Đây là lỗi kỹ thuật rõ ràng nhất. Ví dụ cùng một tên và cùng tags được dùng cho hai ý nghĩa khác nhau:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class ConflictingMeterDemo {
    public static void main(String[] args) {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Counter.builder("orders.processing")
                    .tag("channel", "web")
                    .register(registry);

            // Xung đột: cùng name+tags nhưng giờ lại đăng ký Timer.
            Timer.builder("orders.processing")
                    .tag("channel", "web")
                    .register(registry);
        }
    }
}
```

Micrometer registry thông thường không thể đăng ký hai meter có cùng danh tính nhưng khác loại. Đoạn code này minh họa **xung đột dự kiến**, không phải ví dụ chạy thành công; việc báo lỗi có thể là exception hoặc thông báo từ registry tùy môi trường/phiên bản.

Sửa bằng cách đặt tên theo **đại lượng được đo**:

```java
Counter.builder("orders.processed")
        .tag("channel", "web")
        .register(registry);

Timer.builder("orders.processing.duration")
        .tag("channel", "web")
        .register(registry);
```

`Counter` biểu diễn số sự kiện; `Timer` biểu diễn thời lượng và thường đã có **count** của các lần ghi thời gian. Nếu cùng một request đã được `Timer` đo, không nhất thiết cần thêm `Counter` chỉ để đếm số request: count của timer có thể đã trả lời câu hỏi. Chỉ thêm counter khi sự kiện mang nghĩa **khác** (ví dụ số đơn chuyển sang kiểm duyệt thủ công).

### Dấu hiệu của xung đột type

- Lỗi xuất hiện ngay lúc đăng ký meter hoặc lúc instrument đầu tiên được gọi.
- Cùng tên có nơi được định nghĩa là `Counter`, nơi khác là `Timer`, `Gauge` hoặc `DistributionSummary`.
- Một số metric thiếu trên endpoint xuất dữ liệu; registry hoặc exporter có log cảnh báo về tên/loại.
- Sau thay đổi code, cùng tên từng biểu thị “số lần” nay bị dùng cho “thời lượng” hoặc “kích thước”.

Không giải quyết vấn đề bằng cách thêm `service=foo` cho hai loại meter khác nhau rồi giữ nguyên tên. Cách đó có thể tạm tránh trùng danh tính ở registry nhưng vẫn giữ **cùng tên có ngữ nghĩa mâu thuẫn** và có thể làm backend từ chối cả họ metric.

## 5. Trùng tên ở backend dù tên trong Java khác nhau

Đôi khi registry cục bộ chấp nhận hai meter, nhưng exporter ánh xạ cả hai thành cùng một tên metric sau khi:

- Chuyển dấu chấm hoặc dấu gạch sang tên hợp lệ cho backend, ví dụ `orders.processed` có thể thành dạng `orders_processed_...`.
- Thêm hậu tố chỉ loại metric hoặc đơn vị, ví dụ counter, timer, count, sum hay bucket.
- Áp dụng `NamingConvention`, `MeterFilter` hoặc quy tắc đổi tên ở collector.
- Chuẩn hóa các ký tự không được backend hỗ trợ.

Ví dụ **minh họa nguy cơ**:

```text
Tên khai báo trong Java:
  requests.sent
  requests_sent

Sau bước chuẩn hóa dấu phân cách ở một backend:
  requests_sent
  requests_sent
```

Hai tên nhìn khác nhau trong code có thể rơi vào một tên trùng sau khi xuất. Tên Prometheus cụ thể và hậu tố `_total`, `_seconds_count`, `_seconds_sum`, `_bucket` phụ thuộc loại meter, phiên bản registry và cấu hình. **Không suy đoán tên backend chỉ từ tên Java**; cần kiểm tra dữ liệu scrape/export thực tế.

Đặc biệt với timer/histogram, một phép đo có thể xuất thành **nhiều chuỗi** như count, sum và các buckets. Đừng tự tạo metric với tên dễ đụng vào những chuỗi tổng hợp do registry sinh ra.

### Trùng sau khi áp dụng MeterFilter

`MeterFilter` có thể ánh xạ meter ID, đổi tên hoặc sửa tags trước khi đăng ký. Nếu hai meter ban đầu khác nhau nhưng một filter biến chúng thành **cùng tên và tags**, registry có thể xem chúng là cùng danh tính hoặc gặp lỗi loại meter. Vì vậy cần kiểm tra cả cấu hình filter và **ID sau ánh xạ**, đặc biệt khi hai module dùng quy tắc đổi tên khác nhau.

## 6. Trùng phép đo do Micrometer Observation và meter thủ công

Trong ứng dụng Spring Boot, metrics có thể được sinh từ **instrumentation có sẵn của Actuator/Micrometer** và từ các **custom observations**. Khi cấu hình observation handler cho metrics, một observation có thể sinh timer theo tên/convention và low-cardinality key-values tương ứng.

Một lỗi phổ biến là tự tạo thêm timer cho đúng cùng ranh giới:

```java
// Phản ví dụ: đo hai lần cùng phạm vi nghiệp vụ.
Timer.Sample sample = Timer.start(registry);
try {
    return Observation.createNotStarted(
            "payment.authorize", observationRegistry)
            .observe(() -> gateway.authorize(command));
} finally {
    sample.stop(registry.timer("payment.authorize"));
}
```

Đây là đoạn **minh họa anti-pattern**, với `registry` là `MeterRegistry`, `observationRegistry` là `ObservationRegistry` và `gateway/command` là thành phần nghiệp vụ giả định. Nếu observation metric handler cũng ghi timer có cùng tên/tags, phép đo có thể bị **ghi hai lần** vào cùng meter. Nếu bộ tags khác nhau, có thể xuất hiện hai series đo trùng phạm vi nhưng tạo cảm giác là hai đại lượng khác nhau.

Vấn đề có thể bắt nguồn từ nhiều đường:

| Nguồn đầu tiên | Nguồn bổ sung gây trùng | Hệ quả |
| --- | --- | --- |
| HTTP server observation sẵn có | `@Observed` tự thêm lên controller cho cùng request | Đo chồng thời lượng của toàn request |
| HTTP client observation sẵn có | Custom timer cho chính cùng lời gọi HTTP | Tạo dữ liệu trùng hoặc khó diễn giải |
| Custom `Observation` cho bước `payment.authorize` | `Timer` thủ công cùng tên/tags bao đúng toàn bước | Có thể tăng count hai lần |
| Một business event đã có counter ở domain layer | Adapter HTTP/queue cũng tăng cùng counter cho **chính sự kiện đó** | Số lần tăng bị nhân đôi theo đường đi của event |

Thực hành tốt là **chọn một điểm sở hữu phép đo** và dùng observation khi cần kết hợp latency, error và trace nghiệp vụ. Giữ meter thủ công cho số liệu khác nghĩa như số item trong batch, số lần retry hay queue depth.

Hai observation giống tên chưa chắc là lỗi nếu chúng dùng để ghi **các lần thực hiện khác nhau**. Hãy phân biệt **trùng định nghĩa** với **trùng ghi một sự kiện** bằng phạm vi và thời điểm instrument.

## 7. Cách chẩn đoán có hệ thống

Khi thấy cảnh báo meter trùng tên, một metric mất tích hoặc count bất thường, hãy đi từ ứng dụng đến backend thay vì sửa tên ngay lập tức.

### Bước 1: Xác định tên, tags và loại meter trong registry

Có thể in thông tin về meter trong một chương trình thử nghiệm hoặc điểm chẩn đoán nội bộ:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

public void inspect(MeterRegistry registry) {
    for (Meter meter : registry.getMeters()) {
        Meter.Id id = meter.getId();
        if (id.getName().startsWith("orders.")) {
            System.out.printf(
                    "name=%s type=%s tags=%s baseUnit=%s%n",
                    id.getName(),
                    id.getType(),
                    id.getTags(),
                    id.getBaseUnit());
        }
    }
}
```

`registry.getMeters()` chỉ phản ánh các meter đã được đăng ký vào **registry đang kiểm tra**. Với `CompositeMeterRegistry`, cần hiểu thành phần registry con và đường cấu hình; không suy luận rằng dữ liệu xuất đã tới mọi backend.

Tránh ghi toàn bộ tags ra log production nếu chúng có dữ liệu nhạy cảm. Chỉ lọc tên cần xem, môi trường chẩn đoán và nội dung an toàn.

### Bước 2: Đối chiếu các điểm instrument

Với mỗi metric đáng ngờ, ghi rõ:

- Ai tạo meter? Actuator, Spring instrumentation, custom `Observation`, `@Observed` hay `MeterRegistry` trực tiếp?
- Đơn vị/ngữ nghĩa là gì? Count, duration, size, số job đang chạy?
- Tên và **bộ tag key** chuẩn là gì, các value có thuộc tập hữu hạn không?
- Tại một giao dịch, có bao nhiêu lần `record` hoặc `increment` được gọi?
- Có `MeterFilter` đổi tên, xóa tags, thêm common tags hoặc deny meter không?

Ví dụ, nếu một thao tác thanh toán thành công có hai điểm ghi vào `payment.authorize` timer, count có thể tăng 2 cho một lần thanh toán dù không có lỗi registration. Cần sửa **chủ sở hữu instrumentation**.

### Bước 3: Kiểm tra dữ liệu exporter/backend

Với Prometheus và Spring Boot Actuator, chỉ khi đã cài dependency và cấu hình exposure phù hợp mới có endpoint scrape như `/actuator/prometheus`. Xem tên **sau conversion**, type, bộ label keys, suffix và series thực có. Với OTLP hoặc backend khác, kiểm tra phép ánh xạ tên, unit và type theo pipeline tương ứng.

Nếu registry có meter nhưng backend không thấy, xem thêm:

1. Exporter/scrape có hoạt động và lấy đúng instance không?
2. Meter có bị `MeterFilter` từ chối hoặc bị đổi tên không?
3. Type/naming conflict có khiến exporter/backend bỏ metric không?
4. Thời gian scrape/publish đã đủ để meter có giá trị chưa?
5. Label key/value có bị sửa, chuẩn hóa hoặc giới hạn ở collector không?

**Không dùng trace sampling để giải thích mọi metric mất tích.** Trace sampler chỉ điều khiển tracing theo setup; metric handler có thể hoạt động độc lập. Ngược lại, một observation bị `ObservationPredicate` từ chối có thể không sinh meter từ observation đó.

### Bước 4: Đối chiếu hành vi nghiệp vụ

Đặt một kịch bản xác định, chẳng hạn **10 đơn đặt hàng thành công**, và so sánh mức tăng counter hoặc timer count. Đừng chỉ nhìn con số tích lũy từ trước; dùng hiệu số trước/sau hoặc rate trong khoảng có kiểm soát. Với Prometheus, cần tính cả việc counter reset khi process restart, scrape interval và nhiều instance.

## 8. Thiết kế tên và tags để phòng tránh xung đột

Một hợp đồng metric nên quy định **tên, loại, ý nghĩa, đơn vị, bộ tag keys và những nơi được phép ghi**.

| Đại lượng | Tên minh họa trong Micrometer | Loại | Tags hữu hạn | Chủ sở hữu |
| --- | --- | --- | --- | --- |
| Số đơn đã xử lý | `orders.processed` | `Counter` | `outcome=success/error` | Domain service tại thời điểm hoàn tất |
| Thời gian xử lý đơn | `orders.processing.duration` | `Timer` | `channel=web/partner` | Instrumentation của thao tác xử lý |
| Số đơn đang chờ | `orders.queue.depth` | `Gauge` | `queue=priority/standard` | Thành phần quản lý queue |
| Số lần thanh toán retry | `payment.retry` | `Counter` | `provider=a/b,reason=timeout/unavailable` | Retry policy |
| Thời gian xác thực thanh toán | `payment.authorize` | `Observation` tạo timer qua handler nếu có | `provider=a/b,outcome=approved/declined/error` | Payment service |

Các tên là **quy ước đề xuất**, không phải tên mà Spring Boot tự động sinh. Hãy chọn bộ tên phù hợp với convention của hệ thống và kiểm tra mapping ở exporter.

### Quy tắc dễ áp dụng

1. **Một tên – một ý nghĩa và một loại metric.** Đừng để `payment.processed` lúc thì là count, lúc lại là duration.
2. **Thống nhất tag keys** cho mọi series thuộc cùng một tên. Value có thể khác nhưng không nên đưa key xuất hiện ngẫu nhiên theo code path.
3. **Giới hạn cardinality** bằng enum/allowlist. Không dùng `userId`, `orderId`, email, URL đầy đủ, lỗi raw hoặc trace ID làm metric tags.
4. **Tách business event khỏi latency.** Counter đo sự kiện; Timer đo thời lượng và có count; Gauge đo giá trị tức thời.
5. **Kiểm soát thay đổi tên.** Một rename làm dashboard, PromQL, alert và dữ liệu lịch sử không còn khớp; quản lý như thay đổi hợp đồng telemetry.
6. **Kiểm tra tên sau exporter.** Tránh tiền tố/hậu tố có thể trùng với các series do histogram, timer và counter sinh ra.
7. **Tránh “chữa xung đột” bằng tag động.** Thêm `instanceId` hoặc random suffix chỉ để làm cho Meter.Id khác nhau thường tạo cardinality lớn và che mất lỗi thiết kế.

### Lưu ý về description và baseUnit

Metadata `description` giúp con người hiểu metric; `baseUnit` cho biết đơn vị cơ sở nếu meter hỗ trợ. Hai cấu hình này **không phải namespace độc lập**. Nếu một meter đã đăng ký theo cùng name/tags, cấu hình description/unit mới không đảm bảo sẽ được sử dụng. Nếu một nhóm dùng đơn vị milliseconds còn nhóm khác dùng seconds cho cùng tên, cần **chuẩn hóa cách đo và tên** thay vì kỳ vọng registry tự phân biệt.

## 9. Hệ quả tới metrics, logs và distributed tracing

Một lỗi meter trùng tên có thể ảnh hưởng toàn bộ quy trình điều tra:

```text
Alert: orders_processing_duration p95 tăng
               |
               v
Metrics: tên, type, tag keys có nhất quán không?
               |
               v
Traces: request chậm nằm ở order service hay payment provider?
               |
               v
Logs: correlation theo traceId/spanId và error kind
               |
               v
Xác định nguyên nhân và sửa đúng instrumentation
```

- **Metrics:** nếu tên/tags bị xung đột hoặc ghi trùng, tỉ lệ lỗi và latency percentile có thể sai. Một time series sai khiến cảnh báo sai hoặc che giấu sự cố.
- **Traces:** custom observation cần có ranh giới nghiệp vụ riêng. Tên span dễ đọc và context propagation qua thread/service giúp tìm bước thực sự chậm; trùng meter không nhất thiết đồng nghĩa trùng span.
- **Logs:** log có cấu trúc cho biết nguyên nhân lỗi cụ thể. Tránh đưa exception message hoặc traceId vào metric tags để điều tra từng giao dịch; dùng log/trace có tương quan qua context thay cho high-cardinality labels.
- **Sampling và exporter:** trace có thể không được giữ do sampling, trong khi metrics vẫn được ghi. Metric mất có thể do exporter, filter hoặc naming conflict, không thể chẩn đoán chỉ bằng một panel trống.

Với Micrometer Observation, hãy phân biệt **tên observation**, **tên meter cục bộ** và **tên được exporter công bố**. Chúng liên quan nhưng không nhất thiết giống hệt nhau khi convention/registry chuyển đổi.

## 10. Bài thực hành: tìm lỗi trùng tên

Giả sử dịch vụ Spring Boot có các đoạn instrument:

```java
// A: đếm thanh toán thành công
Counter.builder("payment.operation")
        .tag("outcome", "success").register(registry).increment();

// B: đo độ trễ thanh toán, cố dùng cùng tên/tags
Timer.builder("payment.operation")
        .tag("outcome", "success").register(registry)
        .record(() -> authorizePayment());

// C: đếm thanh toán lỗi, dùng cùng tên nhưng outcome khác
Counter.builder("payment.operation")
        .tag("outcome", "error").register(registry).increment();
```

*Đoạn code là tình huống phân tích; `registry` và `authorizePayment()` là thành phần giả định. Trong thực tế, B có thể xung đột ngay khi đăng ký.*

Hãy trả lời:

1. A và B có cùng meter identity không? Vì sao?
2. C có giống A về identity không? Vì sao cần thống nhất loại metric theo tên?
3. Nếu HTTP client đã được instrument, timer ở B có trùng ý nghĩa phép đo nào không?
4. Làm sao giữ được số lần success/error, latency và khả năng liên hệ trace mà không tạo xung đột?

**Gợi ý lời giải:** A và B cùng name/tags nhưng khác loại nên là xung đột. C khác A ở giá trị `outcome`, có thể là series riêng hợp lệ của counter. Cần thống nhất `payment.operation` chỉ dùng cho một đại lượng, chẳng hạn số lần thanh toán, hoặc đặt lại thành `payment.attempts` với loại `Counter`; latency đo bởi một `Timer` tên `payment.authorization.duration` hay observation nghiệp vụ `payment.authorize` có metric handler thích hợp. Nếu observation đã tạo duration/count đúng nhu cầu, tránh thêm timer thủ công cùng ranh giới. Nhóm nên xác minh dữ liệu xuất thực tế trước khi sửa dashboard/alert.

### Checklist kiểm chứng sau khi sửa

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Gọi register hai lần cùng tên, loại và tags | Nhận lại meter đã có; không tạo series mới cùng identity |
| Register `Counter` rồi `Timer` cùng name/tags | Phát hiện xung đột, không âm thầm dùng sai loại |
| Success và error khác giá trị tag | Hai series đúng nghĩa, tag keys nhất quán |
| 10 yêu cầu thành công | Count tăng theo đúng số lần nghiệp vụ, không gấp đôi |
| Có lỗi kỹ thuật | Metric lỗi được phân loại; logs/traces vẫn đủ chi tiết chẩn đoán |
| Chạy nhiều instance và exporter | Tên, type, unit và bộ label keys nhất quán trên backend |
| Nâng cấp phiên bản Micrometer/exporter | Tên backend và hậu tố count/sum/bucket được xác minh lại |
| Thay đổi filter hoặc common tags | Không tạo va chạm mới sau chuẩn hóa ID |

## 11. Khi nào cần sửa tên, khi nào cần sửa điểm ghi?

Nếu **cùng tên/tags được đăng ký với hai loại khác nhau**, hãy phân tách tên theo đại lượng và sửa các nơi phụ thuộc. Nếu **cùng một counter được tăng hai lần cho một sự kiện**, đổi tên chỉ tạo hai bộ số liệu sai: cần bỏ một điểm `increment()` hoặc chuyển quyền ghi về domain owner. Nếu **tên Java khác nhưng tên backend đụng nhau**, cần đổi quy ước tên hoặc filter sau khi kiểm tra mapping exporter. Nếu **metrics không hiển thị nhưng registry không có xung đột**, hãy điều tra ingestion, scrape, publish và filter trước.

**Kết luận:** Tên meter giống nhau tự nó không phải lỗi. Cần phân biệt **danh tính theo tên/tags**, **loại và ý nghĩa của meter**, **số lần ghi phép đo**, và **tên được exporter công bố**. Đăng ký lại meter cùng danh tính có thể là tái sử dụng hợp lệ; đăng ký khác loại hoặc ghi hai lần cùng sự kiện là vấn đề phải sửa. Một hợp đồng tên, đơn vị và tags ổn định giúp metrics chính xác, liên kết được với logs/traces và đủ tin cậy để điều tra lỗi, độ trễ của Spring Boot trên môi trường thực.
