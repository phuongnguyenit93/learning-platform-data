# Thiết kế chỉ số nghiệp vụ với tên, đơn vị và tag có phạm vi rõ ràng

## 1. Bắt đầu từ câu hỏi nghiệp vụ

Actuator có thể cho biết ứng dụng còn chạy, CPU đang bận hoặc API phản hồi chậm. Những dữ liệu đó chưa trả lời được các câu hỏi như:

- Bao nhiêu lượt tạo đơn kết thúc bằng lỗi hệ thống?
- Một lượt xử lý tạo đơn thường mất bao lâu?
- Có bao nhiêu đơn mới thực sự được lưu thành công?
- Số mặt hàng trong mỗi đơn khác nhau như thế nào giữa web và ứng dụng di động?

**Chỉ số nghiệp vụ (business metric)** là phép đo một sự kiện hoặc trạng thái có ý nghĩa với hoạt động của sản phẩm. Nó được diễn giải bằng quy tắc nghiệp vụ cụ thể, thay vì chỉ mô tả tài nguyên kỹ thuật.

Ví dụ, `http.server.requests` đo lượt HTTP; nó không tự biết một yêu cầu đã tạo ra đơn mới, trả lại đơn cũ do chống trùng, hay mới chỉ đưa công việc vào hàng đợi.

Trong Micrometer, **meter** là đối tượng thu thập phép đo; **MeterRegistry** quản lý các meter. **Tag** là cặp khóa–giá trị dùng để phân nhóm dữ liệu. Một chuỗi dữ liệu theo thời gian (time series) ở hệ thống giám sát gắn với một tổ hợp nhãn cụ thể; một meter có thể tạo nhiều chuỗi, chẳng hạn số mẫu và tổng thời gian của một timer. Xem [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

Ta đi theo thứ tự:

```text
Câu hỏi cần trả lời
        ↓
Sự kiện/trạng thái và ranh giới đo
        ↓
Loại meter, đơn vị và tên
        ↓
Tag có tập giá trị hữu hạn
        ↓
Điểm ghi nhận trong ứng dụng
        ↓
Truy vấn, kiểm chứng và vận hành
```

Nếu chưa thống nhất “một lần thành công nghĩa là gì”, hãy làm rõ định nghĩa trước khi thêm `Counter`.

## 2. Viết hợp đồng cho phép đo

Một **hợp đồng phép đo** ghi lại ý nghĩa mà người viết code, người đọc dashboard và người thiết lập cảnh báo cùng hiểu. Hợp đồng không nhất thiết là một định dạng công cụ; một bảng ngắn trong tài liệu dự án đã hữu ích.

| Thành phần | Cần làm rõ |
| --- | --- |
| Câu hỏi | Quyết định nào sẽ dựa vào số đo này? |
| Đối tượng | Lượt gọi, lần thử, đơn hàng, mặt hàng hay số dư? |
| Điểm bắt đầu/kết thúc | Tính từ lúc nào đến lúc nào? Ghi ở bước nào? |
| Phạm vi | Một instance, một dịch vụ, một tenant hay toàn hệ thống? |
| Loại meter | Đếm sự kiện, đo khoảng thời gian, quan sát trạng thái hay phân bố giá trị? |
| Đơn vị | Lượt, giây, byte, mặt hàng, đơn vị tiền tệ cụ thể? |
| Tên và mô tả | Có đủ ngữ cảnh khi xem riêng tên không? |
| Tag | Những khóa nào luôn có? Giá trị hợp lệ và giới hạn là gì? |
| Retry/chống trùng | Đếm lần thử hay kết quả duy nhất? |
| Cách truy vấn | Lấy tốc độ, tỷ lệ, tổng hay phân vị trong khoảng thời gian nào? |
| Chủ sở hữu | Nhóm nào duy trì định nghĩa và xử lý khi thay đổi? |

Ví dụ xuyên suốt bài là quy trình tạo đơn tại bước thanh toán. Ta định nghĩa:

1. **Một lượt xử lý gửi đơn** bắt đầu khi dịch vụ ứng dụng tiếp nhận lời gọi và kết thúc khi đã có kết quả của lượt đó. Kết quả thuộc `success`, `business_rejected` hoặc `system_error` trong mô hình minh họa.
2. **Một đơn mới đã commit** chỉ được đếm sau khi giao dịch tạo đơn mới được xác nhận thành công.
3. **Số mặt hàng của đơn** là tổng số lượng sản phẩm, không phải số dòng sản phẩm. Đơn có hai dòng với số lượng 2 và 3 được ghi là 5.
4. Kênh tiếp nhận được chuẩn hóa thành `web`, `mobile` hoặc `other`.

Một hệ thống thực tế có thể cần thêm kết quả `replayed` cho yêu cầu chống trùng. Khi đó phải mở rộng định nghĩa và mã đo cùng nhau: trả lại đơn cũ không làm tăng số đơn mới.

### 2.1. Tách sự kiện nghiệp vụ khỏi số lần thực thi kỹ thuật

Một đơn hàng có thể tạo ra:

```text
1 ý định mua hàng
→ 2 lượt gửi HTTP do người dùng thử lại
→ 3 lần gọi dịch vụ thanh toán do retry nội bộ
→ 1 đơn mới được commit
```

Các con số đều có thể đúng vì chúng đo đối tượng khác nhau. Sai lầm là đặt tên cả bốn thành “số đơn”.

- Muốn biết tải xử lý: đo lượt gọi hoặc lần thử.
- Muốn biết hiệu quả cuối cùng: đo kết quả nghiệp vụ đã được xác nhận.
- Muốn biết việc gọi đối tác có ổn không: đo từng lần gọi đối tác.
- Muốn đếm số khách hàng/đơn duy nhất chính xác: cần nguồn dữ liệu và cơ chế đối soát phù hợp; không suy ra bằng cách cộng mọi lượt gọi.

Số lượt kết thúc trong một cửa sổ thời gian không nhất thiết bằng số lượt bắt đầu trong chính cửa sổ đó vì còn công việc đang chạy. Quan hệ đối soát phải tính cả ranh giới thời gian và trạng thái chưa hoàn tất.

### 2.2. Metrics không thay thế sổ cái nghiệp vụ

Ghi meter và commit DB là hai thao tác khác nhau. Tăng counter trước commit có thể đếm cả giao dịch rollback. Tăng sau commit vẫn có khả năng bỏ sót nếu tiến trình dừng giữa commit và thao tác ghi.

Vì vậy, chỉ số này phục vụ quan sát vận hành, phát hiện xu hướng và cảnh báo. Báo cáo doanh thu chính thức, đối soát thanh toán hoặc số đơn tuyệt đối phải dựa vào dữ liệu bền vững cùng quy tắc xử lý trùng. Đưa sự kiện qua outbox có thể hỗ trợ thiết kế đáng tin cậy hơn, nhưng không tự biến mọi lần tăng counter thành cơ chế đếm duy nhất chính xác.

## 3. Chọn meter phù hợp với đại lượng

| Câu hỏi | Meter phù hợp | Giá trị được ghi |
| --- | --- | --- |
| Bao nhiêu đơn mới đã commit? | `Counter` | Tăng thêm một cho mỗi sự kiện hợp lệ |
| Một lượt gửi đơn mất bao lâu? | `Timer` | Khoảng thời gian của lượt đã kết thúc |
| Mỗi đơn có bao nhiêu mặt hàng? | `DistributionSummary` | Số mặt hàng của từng đơn mới |
| Hiện có bao nhiêu lượt đang xử lý? | `Gauge` | Số đang xử lý tại thời điểm lấy mẫu |
| Công việc dài đang chạy được bao lâu? | `LongTaskTimer`, khi cần | Các công việc còn đang hoạt động |

`Counter` dành cho đại lượng tích lũy tăng. Khi đơn bị hủy, không giảm counter “đơn từng được tạo”; có thể ghi thêm sự kiện “đơn bị hủy”. Nếu muốn quan sát số đơn đang mở, đó là trạng thái hiện tại và có thể tăng hoặc giảm, phù hợp với gauge từ nguồn dữ liệu thích hợp.

`Timer` đã có số lượt được đo. Không cần thêm một counter chỉ để đếm chính những lượt mà timer đã ghi. Tuy nhiên, counter “đơn mới đã commit” vẫn có ý nghĩa riêng vì khác sự kiện với “lượt gửi đơn đã kết thúc”. Tương tự, summary có số mẫu và tổng giá trị; số mẫu của summary mặt hàng là số đơn được đưa vào phép đo, còn tổng là tổng số mặt hàng.

Xem [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) và [Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

Gauge chỉ phản ánh lúc được quan sát. Nếu số đang xử lý tăng rồi giảm giữa hai lần thu thập, biểu đồ có thể bỏ lỡ đỉnh. Khi tạo gauge trên một đối tượng trạng thái, ứng dụng phải giữ đối tượng đó sống và cập nhật nó đúng cách; đăng ký một giá trị bất biến không tạo ra phép đo tự thay đổi.

Tham khảo [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Trong các ví dụ tiếp theo, ta triển khai timer, counter và summary. Gauge là một lựa chọn riêng khi ứng dụng cần theo dõi công việc đang diễn ra.

## 4. Đặt tên theo ý nghĩa, giữ đơn vị nhất quán

### 4.1. Một tên mô tả một đại lượng

Trong mã Micrometer, dùng chữ thường và các phần cách nhau bằng dấu chấm. Tên nên có ngữ cảnh miền nghiệp vụ, đối tượng và sự kiện/đại lượng:

| Tên | Diễn giải |
| --- | --- |
| `checkout.submissions` | Timer cho lượt gửi đơn đã kết thúc |
| `checkout.orders.committed` | Counter cho đơn mới đã commit |
| `checkout.order.items` | Summary cho số mặt hàng của từng đơn mới |
| `checkout.inflight` | Gauge cho lượt đang xử lý, nếu triển khai |

Không có một từ khóa bắt buộc cho mọi tổ chức; điều quan trọng là tên và mô tả thống nhất với hợp đồng.

Các tên như `count`, `success`, `business.metric` hoặc `process.time` thiếu đối tượng và phạm vi. Tên gắn với phương thức như `OrderService.save.call` có thể ổn định kém khi refactor và chưa diễn tả rõ sự kiện nghiệp vụ.

Không tạo tên riêng cho từng kênh như `checkout.web.submissions` và `checkout.mobile.submissions` nếu chúng có cùng ý nghĩa. Giữ một tên `checkout.submissions` rồi dùng tag `channel`. Ngược lại, không gom “lượt gửi đơn” và “lần gọi cổng thanh toán” vào cùng một tên chỉ vì cả hai đều là lời gọi.

Mô tả meter giúp làm rõ điểm ghi nhận, nhưng không thể cứu một tên đang trộn nhiều đại lượng không tương thích. Tham khảo [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

### 4.2. Đơn vị là một phần của hợp đồng

| Đại lượng | Cách xử lý |
| --- | --- |
| Khoảng thời gian | Dùng `Timer`, ghi bằng `Duration` hoặc giá trị kèm `TimeUnit` |
| Kích thước dữ liệu | Thống nhất byte; có thể khai báo `baseUnit("bytes")` |
| Số mặt hàng | Quy định rõ là tổng số lượng hay số dòng; dùng `baseUnit("items")` cho summary |
| Tỷ lệ | Chọn 0–1, không trộn với 0–100 |
| Tiền | Quy định loại tiền và đơn vị nhỏ nhất hoặc đơn vị chính; không cộng các loại tiền khác nhau |

Khai báo `baseUnit` cho một số đo thông thường không có nghĩa Micrometer tự biết chuyển 1.000 mili giây thành một giây. Với thời gian, `Timer` nhận biết đơn vị qua API; với kích thước hoặc tiền, việc chuẩn hóa số đầu vào vẫn thuộc trách nhiệm ứng dụng.

Ví dụ `record(120, TimeUnit.MILLISECONDS)` và `record(Duration.ofMillis(120))` cùng diễn tả 120 ms. Không dùng summary ghi số `120` rồi chỉ đặt `baseUnit("seconds")` để mong hệ thống tự đổi.

Timer có thể được xuất theo đơn vị cơ sở khác nhau tùy registry; Prometheus thường dùng giây. Xem [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Nếu đo tiền thanh toán và tiền hoàn, nên tách dòng sự kiện dương cho thanh toán và hoàn tiền. Không giảm counter thanh toán để biểu diễn hoàn tiền. Metrics dùng số thực và không thay thế phép tính tài chính chính xác trong hệ thống nghiệp vụ.

### 4.3. Tên trong mã và tên xuất ra có thể khác nhau

Micrometer chuyển tên theo quy ước của hệ thống nhận dữ liệu. Tên `checkout.submissions` dùng khi tra trong `MeterRegistry` và endpoint metrics; với Prometheus, timer thường có các series như `checkout_submissions_seconds_count` và `checkout_submissions_seconds_sum` trong dòng phiên bản Micrometer 1.13.

Khi đặt tên trong mã, không tự thêm `_total`, `_count` hoặc `_seconds` theo cách làm trùng hậu tố mà exporter đã sinh. Tên xuất cuối cùng còn phụ thuộc loại meter, đơn vị và cấu hình registry; kiểm tra endpoint thực tế trước khi viết dashboard.

Quy tắc đặt tên của backend không hoàn toàn trùng với tên trong mã. [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/) giải thích vì sao tên xuất cần thể hiện đơn vị và vì sao không dùng nhãn có miền giá trị không giới hạn.

## 5. Tag trả lời câu hỏi phân nhóm, không nhận diện từng giao dịch

Với `checkout.submissions`, hai tag là:

| Khóa | Miền giá trị | Mục đích |
| --- | --- | --- |
| `channel` | `web`, `mobile`, `other` | So sánh các kênh tiếp nhận |
| `outcome` | `success`, `business_rejected`, `system_error` | Tách kết quả xử lý |

Khóa và giá trị phải được chuẩn hóa. `WEB`, `Web`, `web ` không được vô tình trở thành ba nhóm nếu đều cùng nghĩa “web”. Dữ liệu không nằm trong tập cho phép được ánh xạ sang `other`; các giá trị không biết cần được điều tra ở log hoặc một phép đo có giới hạn riêng.

Giữ tập khóa nhất quán **trong cùng một họ meter**: mọi timer `checkout.submissions` đều có `channel` và `outcome`, kể cả nhóm chưa có dữ liệu. Counter `checkout.orders.committed` có thể chỉ cần `channel` vì đó là một họ meter khác.

Các giá trị như `orderId`, `requestId`, `traceId`, email, thông báo ngoại lệ hoặc URL có tham số tùy ý không phù hợp làm tag cho từng giao dịch. Đưa chúng vào log/tracing khi cần tra cứu chi tiết. Băm ID chỉ thay cách biểu diễn; mỗi ID khác nhau vẫn tạo một giá trị tag khác nhau.

Mỗi meter được nhận diện bằng tên và tổ hợp tag. Thay giá trị tag khi ghi nhận không “cập nhật nhãn của meter cũ”, mà thường tra cứu hoặc tạo một meter khác. Vì vậy:

```text
channel=web, outcome=success
channel=web, outcome=system_error
```

là hai meter của cùng một họ, phục vụ hai nhóm kết quả khác nhau.

### 5.1. Tính ngân sách số tổ hợp trước khi triển khai

Với ba kênh và ba kết quả, timer có tối đa:

```text
3 kênh × 3 kết quả = 9 tổ hợp meter trên mỗi instance
```

Nếu thêm hai phương thức thanh toán:

```text
3 × 3 × 2 = 18 tổ hợp
```

Giả sử có 20 instance, riêng timer count và sum đã có thể tạo khoảng `18 × 20 × 2 = 720` chuỗi ở backend; còn max, bucket, nhãn bổ sung và biến động instance sẽ làm số thực tế khác đi.

Đây là ước tính theo tổ hợp có thể phát sinh, không phải công thức chính xác cho mọi registry. Histogram thường nhân chi phí thêm vì mỗi bucket cũng tạo dữ liệu. Một tag có ít giá trị khi đứng riêng vẫn có thể gây nhiều tổ hợp khi kết hợp nhiều chiều.

Trước khi thêm tag, cần trả lời:

1. Có truy vấn hoặc quyết định cụ thể cần chiều này không?
2. Có thể liệt kê và giới hạn miền giá trị không?
3. Có thật sự cần phân nhóm mọi meter bằng chiều này không?
4. Lấy tổng bỏ chiều đó đi còn có ý nghĩa không?
5. Chi phí trên toàn bộ instance và thời gian lưu trữ có chấp nhận được không?

Không đưa `tenant` vào mọi metric theo thói quen. Vài tenant hôm nay có thể thành hàng chục nghìn tenant về sau; khi cần phân tích chi tiết từng khách hàng, hệ thống phân tích nghiệp vụ có thể phù hợp hơn.

### 5.2. Phân biệt tag nghiệp vụ và tag môi trường

`channel` và `outcome` mô tả sự kiện. `application`, `environment` hoặc `region` mô tả nơi ứng dụng chạy.

Trong Spring Boot có thể cấu hình tag chung, ví dụ:

```yaml
management:
  metrics:
    tags:
      application: checkout-service
      environment: local
```

Đây là tag có giá trị cố định theo lần triển khai. Không đặt một dữ liệu thay đổi theo từng request vào tag chung của registry.

Backend có thể đã thêm nhãn như `job` và `instance` khi thu thập. Kiểm tra quy ước hiện có để tránh trùng tên hoặc che nhãn. Thêm common tags phải diễn ra trước khi các meter được đăng ký; trong Boot, dùng cấu hình hoặc `MeterRegistryCustomizer` thay vì sửa registry muộn từ một request handler.

## 6. Ví dụ Java 17 chạy độc lập với Micrometer

Ví dụ ghi bốn kết quả đã biết, dùng thời lượng giả lập để stdout ổn định. Nó kiểm chứng cấu trúc meter, tên, đơn vị và tag; không đo tốc độ của máy và không thực hiện giao dịch DB.

Trong mô hình minh họa, `success` nghĩa là tạo một đơn mới đã commit. Không mô phỏng yêu cầu chống trùng, timeout sau commit hoặc lỗi xảy ra khi gửi phản hồi cho khách hàng. Trong ứng dụng có các tình huống đó, sự kiện commit và kết quả lượt gọi phải được ghi nhận ở các điểm tương ứng, không suy từ một biến kết quả duy nhất.

Tạo một dự án Gradle độc lập với ba tệp sau.

`settings.gradle`:

```groovy
rootProject.name = 'business-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'BusinessMetricsDemo'
}
```

Phiên bản `1.13.0` giúp ví dụ độc lập tái lập được trên dòng Micrometer dùng cùng Spring Boot 3.3. Với ứng dụng Boot, ưu tiên phiên bản do BOM của ứng dụng quản lý thay vì sao chép phiên bản này để ghi đè.

Tệp `src/main/java/BusinessMetricsDemo.java`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.EnumMap;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class BusinessMetricsDemo {
    public enum Channel {
        WEB, MOBILE, OTHER;

        public String tag() {
            return name().toLowerCase(Locale.ROOT);
        }

        public static Channel from(String raw) {
            String value = raw == null ? "" : raw.trim().toLowerCase(Locale.ROOT);
            return switch (value) {
                case "web" -> WEB;
                case "mobile" -> MOBILE;
                default -> OTHER;
            };
        }
    }

    public enum Outcome {
        SUCCESS, BUSINESS_REJECTED, SYSTEM_ERROR;

        public String tag() {
            return name().toLowerCase(Locale.ROOT);
        }
    }

    public static final class CheckoutMetrics {
        private final EnumMap<Channel, EnumMap<Outcome, Timer>> submissions =
                new EnumMap<>(Channel.class);
        private final EnumMap<Channel, Counter> committed =
                new EnumMap<>(Channel.class);
        private final EnumMap<Channel, DistributionSummary> orderItems =
                new EnumMap<>(Channel.class);

        public CheckoutMetrics(MeterRegistry registry) {
            for (Channel channel : Channel.values()) {
                EnumMap<Outcome, Timer> byOutcome = new EnumMap<>(Outcome.class);
                for (Outcome outcome : Outcome.values()) {
                    byOutcome.put(outcome, Timer.builder("checkout.submissions")
                            .description("Completed checkout submission latency")
                            .tags("channel", channel.tag(), "outcome", outcome.tag())
                            .register(registry));
                }
                submissions.put(channel, byOutcome);
                committed.put(channel, Counter.builder("checkout.orders.committed")
                        .description("New orders whose creation transaction committed")
                        .tag("channel", channel.tag())
                        .register(registry));
                orderItems.put(channel, DistributionSummary.builder("checkout.order.items")
                        .description("Item units in each newly committed order")
                        .baseUnit("items")
                        .tag("channel", channel.tag())
                        .register(registry));
            }
        }

        public void recordResult(
                Channel channel, Outcome outcome, Duration duration, int items) {
            Objects.requireNonNull(channel);
            Objects.requireNonNull(outcome);
            Objects.requireNonNull(duration);
            if (duration.isNegative()
                    || (outcome == Outcome.SUCCESS && items <= 0)
                    || (outcome != Outcome.SUCCESS && items != 0)) {
                throw new IllegalArgumentException("Invalid completed result");
            }

            submissions.get(channel).get(outcome).record(duration);
            if (outcome == Outcome.SUCCESS) {
                committed.get(channel).increment();
                orderItems.get(channel).record(items);
            }
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            CheckoutMetrics metrics = new CheckoutMetrics(registry);
            metrics.recordResult(
                    Channel.from("WEB"), Outcome.SUCCESS, Duration.ofMillis(120), 2);
            metrics.recordResult(
                    Channel.from("web"), Outcome.BUSINESS_REJECTED, Duration.ofMillis(40), 0);
            metrics.recordResult(
                    Channel.from("mobile"), Outcome.SYSTEM_ERROR, Duration.ofMillis(80), 0);
            metrics.recordResult(
                    Channel.from("web"), Outcome.SUCCESS, Duration.ofMillis(160), 5);

            long completed = registry.find("checkout.submissions").timers()
                    .stream().mapToLong(Timer::count).sum();
            Timer webSuccess = registry.get("checkout.submissions")
                    .tags("channel", "web", "outcome", "success").timer();
            DistributionSummary webItems = registry.get("checkout.order.items")
                    .tag("channel", "web").summary();

            System.out.println("completed=" + completed);
            System.out.println("web.success.count=" + webSuccess.count());
            System.out.println("web.success.totalMs="
                    + Math.round(webSuccess.totalTime(TimeUnit.MILLISECONDS)));
            System.out.println("web.business_rejected.count="
                    + registry.get("checkout.submissions")
                    .tags("channel", "web", "outcome", "business_rejected").timer().count());
            System.out.println("mobile.system_error.count="
                    + registry.get("checkout.submissions")
                    .tags("channel", "mobile", "outcome", "system_error").timer().count());
            System.out.println("web.orders.committed="
                    + Math.round(registry.get("checkout.orders.committed")
                    .tag("channel", "web").counter().count()));
            System.out.println("web.order.items.total=" + Math.round(webItems.totalAmount()));
            System.out.printf(Locale.ROOT, "web.order.items.mean=%.1f%n", webItems.mean());
            System.out.println("meter.ids=" + registry.getMeters().size());
        } finally {
            registry.close();
        }
    }
}
```

Chạy khi đã có Gradle 8.x và JDK 17:

```bash
gradle -q run
```

Nếu dự án có Gradle Wrapper, thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trên Windows. Lần đầu cần tải dependency từ Maven Central.

Stdout:

```text
completed=4
web.success.count=2
web.success.totalMs=280
web.business_rejected.count=1
mobile.system_error.count=1
web.orders.committed=2
web.order.items.total=7
web.order.items.mean=3.5
meter.ids=15
```

### 6.1. Tự đối chiếu các giá trị

- Có bốn lượt xử lý kết thúc, nên tổng count của các timer bằng 4.
- Hai lượt web thành công mất 120 ms và 160 ms: count bằng 2, tổng thời gian bằng 280 ms.
- Một lượt web bị từ chối nghiệp vụ và một lượt mobile lỗi hệ thống được ghi vào hai nhóm riêng.
- Chỉ hai kết quả thành công trong mô hình này tạo đơn mới: counter của kênh web bằng 2.
- Hai đơn mới có lần lượt 2 và 5 mặt hàng: summary có tổng 7 và trung bình 3,5.
- Có 9 timer, 3 counter và 3 summary, tổng cộng 15 meter ID; đây không phải số chuỗi Prometheus sẽ xuất.
- `Channel.from` chỉ tạo ba giá trị tag đã biết. Dữ liệu lạ không tạo một meter riêng theo từng chuỗi đầu vào.

Các meter được đăng ký trước theo tập enum hữu hạn, nên cả nhóm chưa có sự kiện cũng hiện diện trong registry với count ban đầu bằng 0. Cách này phù hợp khi số tổ hợp nhỏ; không đăng ký trước hàng triệu tổ hợp chỉ để tránh giá trị thiếu.

Phương thức `recordResult` giả định mỗi kết quả được chuyển cho nó đúng một lần. Gọi lại cùng kết quả vẫn tăng số đo; đoạn mã không có cơ chế nhận diện giao dịch đã ghi.

### 6.2. Vì sao dùng cả timer và counter ở đây?

Timer trả lời “bao nhiêu lượt xử lý đã kết thúc và chúng mất bao lâu”. Counter trả lời “bao nhiêu đơn mới đã commit”. Khi có retry, chống trùng hoặc xử lý nhiều bước, hai đại lượng có thể khác nhau.

Không cộng count của timer với counter để tìm “tổng nghiệp vụ”. Chúng không phải hai phần rời nhau của cùng một tổng. Nếu cần một counter chỉ để sao chép count của timer, hãy xem lại sự cần thiết của nó.

## 7. Đưa thiết kế vào ứng dụng Spring Boot

Trong ứng dụng Boot có Actuator, sử dụng `MeterRegistry` do Spring quản lý. Có thể tách lớp `CheckoutMetrics` và các enum trong ví dụ ra các tệp của package ứng dụng, rồi đăng ký đối tượng đo bằng một bean.

Phần cấu hình dưới đây minh họa cách sử dụng trực tiếp lớp lồng của chương trình nếu nó được đưa vào cùng package với cấu hình:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutMetricsConfiguration {
    @Bean
    public BusinessMetricsDemo.CheckoutMetrics checkoutMetrics(
            MeterRegistry registry) {
        return new BusinessMetricsDemo.CheckoutMetrics(registry);
    }
}
```

Đoạn trên là cấu hình trong một ứng dụng Boot đã có lớp `BusinessMetricsDemo` tương ứng; không phải chương trình `main` độc lập. Trong dự án thật, có thể đặt tên và tách lớp theo cấu trúc package của dự án.

Không tự tạo `new SimpleMeterRegistry()` bên trong service sản xuất rồi mong Actuator tự nhìn thấy registry riêng đó. `SimpleMeterRegistry` trong ví dụ chỉ giúp thí nghiệm bộ nhớ đơn giản.

Cũng không dựa vào các phương thức static của `Metrics` thay cho registry được inject khi cần bảo đảm cấu hình, filter và exporter của Spring được áp dụng. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 7.1. Chọn điểm ghi nhận đúng trong luồng nghiệp vụ

Một trình tự thực tế có thể là:

```text
Tiếp nhận lời gọi
  → bắt đầu mẫu thời gian
  → kiểm tra điều kiện nghiệp vụ
  → thực hiện giao dịch
  → commit được xác nhận
  → ghi nhận sự kiện đơn mới và số mặt hàng
  → kết thúc lượt xử lý, ghi timer theo kết quả
```

Không tăng counter đơn mới ngay sau `repository.save(...)` nếu giao dịch vẫn có thể rollback. Với giao dịch khai báo bằng `@Transactional`, việc phương thức thân trả về chưa luôn đồng nghĩa commit đã hoàn tất ở thời điểm code bên trong phương thức đang chạy. Điểm ghi cần phù hợp với ranh giới transaction, chẳng hạn sau lời gọi qua proxy đã hoàn tất nếu đó là ranh giới giao dịch ngoài cùng, hoặc callback sau commit được thiết kế đúng. Nếu phương thức tham gia một giao dịch ngoài, phải chờ giao dịch ngoài ấy commit. Xem [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Nếu commit thành công nhưng phản hồi tới khách hàng gặp lỗi, “đơn mới đã commit” và “lượt gọi kết thúc thế nào” cần được diễn tả độc lập. Đó là lý do phương thức gộp `recordResult` chỉ là mô hình giản lược cho thí nghiệm.

Thời gian của một lượt đồng bộ thường đo bằng `Timer.Sample` rồi dừng khi biết kết quả. Với `CompletableFuture` hoặc luồng phản ứng, gắn điểm kết thúc vào tín hiệu hoàn tất thật, không dừng timer ngay khi trả về đối tượng bất đồng bộ. Chi tiết bao lỗi, hủy và retry phải theo hợp đồng của phép đo.

### 7.2. Bảo vệ ngân sách tag bằng MeterFilter

Ưu tiên giới hạn dữ liệu ngay tại điểm đo như `Channel.from`. Có thể bổ sung lớp bảo vệ registry:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsBudgetConfiguration {
    @Bean
    public MeterFilter checkoutChannelLimit() {
        return MeterFilter.maximumAllowableTags(
                "checkout.", "channel", 3, MeterFilter.deny());
    }
}
```

Filter này áp dụng cho các meter có tên bắt đầu bằng `checkout.` và giới hạn số giá trị `channel` mà nó chấp nhận. Nó không xác định thay nghiệp vụ rằng ba giá trị phải là `web`, `mobile`, `other`; phần ánh xạ giá trị vẫn cần có.

Khi bị từ chối đăng ký, Micrometer có thể trả meter không thực hiện ghi nhận (NOOP). Vì vậy filter bảo vệ tài nguyên nhưng có thể dẫn đến mất số đo nếu dữ liệu vượt hợp đồng. Không coi đây là cơ chế gom mọi giá trị dư thành `other`, cũng không kỳ vọng nó tự xóa các meter đã đăng ký trước đó.

Thứ tự filter có ý nghĩa; một filter chấp nhận sớm có thể ảnh hưởng các bước kiểm tra tiếp theo. Xem [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html). Với Boot, các bean `MeterFilter` được áp dụng vào registry do Spring quản lý.

## 8. Kiểm tra số đo qua Actuator trước khi tạo dashboard

Nếu ứng dụng đã có starter web, starter Actuator và registry Prometheus, cấu hình thí nghiệm cục bộ có thể là:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: checkout-service
      environment: local
```

Đây là cấu hình cho ứng dụng Boot, không phải cho chương trình `SimpleMeterRegistry` độc lập. Hợp nhất với cấu hình đang có, tránh tạo nhiều khóa `management` trùng nhau. Quyền truy cập thực tế còn phụ thuộc bảo mật của ứng dụng và mạng triển khai.

Gọi các endpoint sau sau khi ứng dụng đã ghi nhận sự kiện:

```bash
curl "http://127.0.0.1:8081/actuator/metrics/checkout.submissions"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.submissions?tag=channel:web&tag=outcome:success"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.orders.committed?tag=channel:web"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.order.items?tag=channel:web"
curl "http://127.0.0.1:8081/actuator/prometheus"
```

Trên PowerShell có thể dùng `curl.exe` nếu `curl` đang là alias của lệnh khác.

Kiểm tra:

- Tên và tập tag có đúng hợp đồng không?
- Timer có `COUNT` và `TOTAL_TIME` phù hợp không? Đọc `baseUnit` thay vì mặc định tổng thời gian luôn là ms.
- Count của summary là số đơn được ghi; `TOTAL` là số mặt hàng theo đơn vị đã công bố.
- Bộ lọc tag có thật sự chọn đúng nhóm không?
- Nhóm không có sự kiện là meter count bằng 0, hay hoàn toàn chưa tồn tại?
- Tên xuất Prometheus có đơn vị/hậu tố đúng với truy vấn dự định không?

Khi bỏ bộ lọc tag, endpoint metrics có thể cộng các số đo của nhiều meter phù hợp. Tổng hợp đó chỉ hữu ích nếu các nhóm cùng đại lượng và đơn vị. Không dùng một kết quả tổng để khẳng định mọi kênh đều hoạt động tốt.

## 9. Thiết kế truy vấn cùng với phép đo

Các truy vấn dưới đây minh họa cho tên xuất thông thường của Micrometer 1.13 với Prometheus. Chỉ sử dụng sau khi đã đối chiếu endpoint thực tế.

### 9.1. Tốc độ tạo đơn mới

```promql
sum by (channel) (
  rate(checkout_orders_committed_total{
    application="checkout-service"
  }[5m])
)
```

Kết quả là số đơn mới được ghi nhận trên mỗi giây trong cửa sổ tính toán, không phải tổng số đơn từ trước đến nay.

Counter tăng tích lũy theo vòng đời tiến trình; instance khởi động lại có thể làm số đếm bắt đầu lại. Dùng hàm phù hợp cho counter và giữ khả năng xử lý reset theo từng series trước khi cộng gộp. Tham khảo [Prometheus — Query functions](https://prometheus.io/docs/prometheus/2.55/querying/functions/).

### 9.2. Tỷ lệ lỗi hệ thống trong các lượt đã kết thúc

```promql
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service",
    outcome="system_error"
  }[5m])
)
/
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service"
  }[5m])
)
```

Mẫu số ở đây là **mọi lượt đã kết thúc**, gồm cả từ chối nghiệp vụ. Nếu muốn tỷ lệ lỗi chỉ trong các lượt đủ điều kiện nghiệp vụ, mẫu số phải thay đổi và tên dashboard phải diễn đạt đúng.

Khi mẫu số bằng 0 hoặc series bị mất, kết quả không xác định/không có dữ liệu không đồng nghĩa lỗi bằng 0%. Thiết lập cách xử lý trường hợp này một cách chủ động.

### 9.3. Thời gian trung bình của lượt thành công

```promql
sum by (channel) (
  rate(checkout_submissions_seconds_sum{
    application="checkout-service",
    outcome="success"
  }[5m])
)
/
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service",
    outcome="success"
  }[5m])
)
```

Đơn vị kết quả là giây với các series nêu trên. Đây là trung bình có trọng số theo số lượt. Không lấy trung bình đơn giản của thời gian trung bình từng instance khi lượng xử lý của chúng khác nhau.

Trung bình chưa mô tả phần đuôi phân bố. Nếu cần p95/p99 tổng hợp nhiều instance, thiết kế histogram và ngân sách bucket từ đầu; không cộng hoặc lấy trung bình các phân vị tính riêng ở từng instance.

### 9.4. Một tỷ lệ chỉ có nghĩa khi tử và mẫu tương thích

“Đơn mới / lượt HTTP” có thể thay đổi vì retry hoặc chống trùng, dù hệ thống không có lỗi. “Thanh toán thành công / lần gọi đối tác” đo hiệu quả mỗi lần thử; “đơn thanh toán thành công / đơn cần thanh toán” đo kết quả cuối cùng. Hai tỷ lệ phục vụ hai mục đích khác nhau.

Tử số và mẫu số cần cùng phạm vi dịch vụ, cửa sổ, điều kiện lọc và định nghĩa đối tượng. Nếu dữ liệu đến từ các giai đoạn khác nhau, còn phải xét độ trễ giữa các giai đoạn.

## 10. Giữ định nghĩa ổn định khi hệ thống thay đổi

Một metric là giao diện giữa code và người vận hành. Đổi ý nghĩa mà giữ nguyên tên có thể làm dashboard trông liên tục dù dữ liệu hai giai đoạn không còn so sánh được.

Ví dụ, `checkout.orders.committed` ban đầu đếm đơn mới; sau đó đổi sang đếm mọi lần trả lại đơn, kể cả chống trùng. Biểu đồ tăng chưa chắc là tăng doanh số hay tải thật, mà có thể chỉ là đổi định nghĩa.

Khi thay đổi:

1. Xác định có đổi đối tượng, đơn vị, điểm ghi hoặc tập kết quả không.
2. Nếu ý nghĩa không còn tương thích, chọn tên/hợp đồng mới và cập nhật truy vấn.
3. Khi cần chạy song song để đối chiếu, đặt thời hạn chuyển đổi rõ ràng.
4. Trong giai đoạn nhiều phiên bản cùng chạy, tránh cộng lẫn hai định nghĩa hoặc đếm đôi hai tên cho cùng mục tiêu.
5. Bỏ meter cũ và truy vấn cũ theo kế hoạch sau khi xác minh.

Đổi đơn vị từ đồng sang nghìn đồng mà không thay hợp đồng là lỗi nghiêm trọng dù kiểu dữ liệu Java không đổi. Tương tự, đổi `channel=mobile` thành `channel=app` tạo nhóm dữ liệu mới; không tự coi đó là đổi nhãn hiển thị trên dashboard.

Với cùng tên và tag, registry thường tái sử dụng meter đã đăng ký. Không dựa vào việc đăng ký lại với một mô tả, loại meter hoặc đơn vị khác để thay đổi định nghĩa an toàn. Hãy phát hiện xung đột ở kiểm tra cấu hình và kiểm chứng dữ liệu.

## 11. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt tên `success` | Không biết thành công của hoạt động nào | Thêm miền nghiệp vụ, sự kiện và mô tả |
| Tăng “đơn đã tạo” trước commit | Đếm cả giao dịch rollback | Ghi tại ranh giới xác nhận phù hợp |
| Đếm retry thành nhiều đơn mới | Sai đối tượng cần đo | Tách lần thử khỏi kết quả duy nhất |
| Timer và counter cùng đếm đúng một sự kiện | Dữ liệu dư, dễ khác nhau về điểm ghi | Dùng count của timer khi đáp ứng mục tiêu |
| Trộn ms và giây | Số đo sai nhiều bậc độ lớn | Dùng API có đơn vị và kiểm tra giá trị xuất |
| Dùng `orderId` hoặc email làm tag | Tăng tổ hợp không giới hạn | Giữ thông tin chi tiết trong log/tracing |
| Băm ID rồi vẫn dùng làm tag | Không giảm số giá trị khác nhau | Ánh xạ về nhóm hữu hạn có ý nghĩa |
| Không chuẩn hóa giá trị đầu vào | Cùng một kênh bị tách thành nhiều nhóm | Quy định tập giá trị và giá trị dự phòng |
| Tạo registry riêng trong service | Actuator/exporter không thấy số đo mong đợi | Dùng registry do Spring quản lý |
| Dùng counter cho số đơn đang mở | Không biểu diễn đúng việc tăng và giảm | Dùng gauge từ trạng thái phù hợp |
| Xem tổng counter là số tài chính tuyệt đối | Bỏ qua reset, mất mẫu và trùng sự kiện | Đối soát bằng dữ liệu nghiệp vụ bền vững |
| Chỉ kiểm tra code không lỗi | Vẫn có thể sai ý nghĩa phép đo | Dùng dữ liệu đầu vào và kết quả dự kiến rõ ràng |

## 12. Thực hành thiết kế và kiểm chứng

1. Viết hợp đồng cho câu hỏi “có bao nhiêu lần thanh toán bị từ chối”. Phân biệt từ chối từ đối tác, điều kiện nghiệp vụ không hợp lệ và lỗi kết nối.
2. Cho một giao dịch có ba lần thử gọi đối tác nhưng chỉ một kết quả thanh toán cuối cùng. Liệt kê những meter cần tăng và giá trị tăng; không dùng một counter để thay cả hai khái niệm.
3. Trong ví dụ Java, thêm một kết quả `BUSINESS_REJECTED` của kênh mobile với thời lượng 60 ms. Trước khi chạy, dự đoán tổng lượt, số đơn mới, tổng mặt hàng và số meter ID.
4. Truyền kênh `"new-user-channel-123"` qua `Channel.from`. Giải thích tại sao số meter ID vẫn có giới hạn và dữ liệu đi vào nhóm nào.
5. Tính ngân sách cho bốn kênh, năm kết quả, ba loại phương thức thanh toán và 30 instance. Nêu rõ khác biệt giữa số tổ hợp meter và số series khi bật histogram.
6. Thiết kế metric tiền hoàn: xác định loại tiền, đơn vị, dấu của giá trị và lý do không cộng lẫn các loại tiền.
7. Đề xuất cách thay đổi metric đang đếm “lượt gọi tạo đơn” sang metric đếm “đơn mới đã commit”, gồm tên, giai đoạn chuyển đổi và truy vấn cần cập nhật.

Một thiết kế đạt yêu cầu khi người khác có thể đọc tên, đơn vị, tag và mô tả rồi biết chính xác **đang đo điều gì, ghi ở đâu, có thể cộng nhóm nào và phải hiểu những giới hạn nào**.
