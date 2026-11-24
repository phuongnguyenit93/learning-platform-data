# Ứng dụng với kích thước dữ liệu, số phần tử hoặc lượng công việc mỗi lượt

DistributionSummary trong Micrometer dùng để ghi nhận phân phối của các giá trị số không phải thời lượng. Nó phù hợp khi ứng dụng cần biết mỗi payload lớn bao nhiêu, mỗi batch có bao nhiêu phần tử hoặc mỗi lượt xử lý đảm nhận lượng công việc nào. Từ các lần ghi nhận, Micrometer cung cấp số mẫu, tổng lượng, trung bình và giá trị lớn nhất; khi cấu hình thêm histogram hoặc percentile, hệ thống giám sát có thể phân tích hình dạng phân phối.

Điểm quan trọng là mỗi lần gọi `record(amount)` đại diện cho một quan sát. Nếu ghi kích thước của từng payload, count là số payload được đo, còn totalAmount là tổng số byte của chúng. Nếu ghi số phần tử của từng batch, count là số batch, còn totalAmount là tổng số phần tử được xử lý qua các batch đã ghi nhận.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn DistributionSummary cho dữ liệu số không phải thời lượng.
- Phân biệt số lần ghi nhận với tổng lượng dữ liệu hoặc công việc.
- Chọn base unit và bảo đảm giá trị ghi nhận dùng đúng đơn vị.
- Instrument kích thước payload, số phần tử mỗi batch và lượng công việc mỗi lượt.
- Kiểm chứng count, totalAmount, mean và max bằng dữ liệu đã biết.
- Cấu hình histogram, percentile và ngưỡng phân phối phù hợp.
- Giới hạn tag cardinality và kiểm tra chi phí metrics.

## 1. Khi nào dùng DistributionSummary?

DistributionSummary ghi nhận các giá trị số độc lập theo từng lần quan sát. Nó hữu ích khi cần phân tích một tập giá trị có thể lớn nhỏ khác nhau, chẳng hạn:

- Kích thước request hoặc response tính bằng byte.
- Số bản ghi trong mỗi batch import/export.
- Số phần tử được xử lý trong một lượt worker.
- Số message được gom trong một lần flush.
- Số item được tính toán hoặc cập nhật trong một lần thao tác.
- Lượng dữ liệu được đọc, ghi hoặc chuyển đổi trong mỗi lần xử lý.

Hãy dùng DistributionSummary khi giá trị cần ghi nhận là một đại lượng số có ý nghĩa và muốn phân tích phân phối của nó. Nếu chỉ cần đếm số sự kiện, Counter đơn giản hơn. Nếu cần quan sát giá trị hiện tại có thể tăng hoặc giảm, dùng Gauge. Nếu đại lượng là thời gian thực hiện, dùng Timer.

| Nhu cầu | Meter phù hợp | Ví dụ |
| --- | --- | --- |
| Đếm số batch đã chạy | Counter | Một lần increment cho mỗi batch |
| Đo số phần tử trong từng batch | DistributionSummary | Ghi 100, 200, 300 phần tử |
| Quan sát số phần tử hiện còn trong queue | Gauge | Đọc queue size hiện tại |
| Đo thời gian xử lý batch | Timer | Ghi duration của mỗi batch |
| Đo kích thước từng payload | DistributionSummary | Ghi số byte của mỗi payload |

Có thể dùng nhiều loại meter cùng lúc cho một thao tác. Ví dụ, một worker có thể dùng Counter để đếm số batch, DistributionSummary để đo số phần tử mỗi batch và Timer để đo thời gian xử lý mỗi batch. Mỗi meter trả lời một câu hỏi riêng.

## 2. Hiểu count, totalAmount, mean và max

Giả sử worker xử lý bốn batch, số phần tử lần lượt là 100, 200, 300 và 400.

| Batch | Số phần tử |
| ---: | ---: |
| 1 | 100 |
| 2 | 200 |
| 3 | 300 |
| 4 | 400 |

Các thống kê của DistributionSummary được hiểu như sau:

| Thống kê | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| count | 4 | Có bốn lần ghi nhận, tức bốn batch |
| totalAmount | 1.000 | Tổng cộng 1.000 phần tử trong các batch |
| mean | 250 | Trung bình 250 phần tử mỗi batch |
| max | 400 | Batch lớn nhất được quan sát có 400 phần tử |

**Count** là số lần gọi ghi nhận hợp lệ, không phải tổng số phần tử. Trong ví dụ này, count bằng 4 vì có bốn batch.

**Total amount** là tổng các giá trị được ghi. Với batch size, tổng này tương ứng tổng số phần tử qua các batch đã ghi nhận. Với payload size, tổng này tương ứng tổng byte của các payload đã ghi.

**Mean** là trung bình số học của các giá trị đã ghi:

`mean = totalAmount / count`

**Max** là giá trị lớn nhất mà thống kê max đang giữ trong cửa sổ thời gian của nó. Không nên mặc định xem max là giá trị lớn nhất từ khi process khởi động; hành vi time-window phụ thuộc cấu hình thống kê.

## 3. Ghi kích thước payload theo byte

Một trường hợp phổ biến là đo kích thước payload request. Nếu ứng dụng nhận một mảng byte, `payload.length` cho biết số byte của payload.

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class PayloadMetrics {

    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary
                .builder("http.request.payload")
                .description("Kích thước payload request")
                .baseUnit("bytes")
                .register(registry);
    }

    public void record(byte[] payload) {
        if (payload == null) {
            return;
        }

        payloadSize.record(payload.length);
    }
}
```

Mỗi payload được ghi nhận một lần. Ví dụ, ba payload có kích thước 512, 1.024 và 2.048 byte sẽ tạo ra:

- count = 3 payload.
- totalAmount = 3.584 bytes.
- mean = khoảng 1.194,67 bytes mỗi payload.
- max = 2.048 bytes trong cửa sổ max hiện tại.

Base unit `bytes` mô tả đơn vị của giá trị. Nó không tự chuyển đổi số đo. Nếu gọi `record(1024)`, giá trị được ghi là 1.024 byte theo quy ước của ứng dụng. Nếu muốn ghi kilobyte, cần tự chuyển đổi giá trị và khai báo base unit tương ứng.

Với `byte[]`, `length` là số byte. Với `String`, `length()` trả về số đơn vị UTF-16 code unit, không phải số byte UTF-8. Nếu cần đo kích thước chuỗi khi truyền qua mạng, hãy đo byte sau khi mã hóa:

```java
import java.nio.charset.StandardCharsets;

int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
payloadSize.record(utf8Bytes);
```

Không đưa nội dung payload vào tag hoặc tên meter. Chỉ ghi số đo tổng hợp về kích thước.

## 4. Đo số phần tử trong mỗi batch

DistributionSummary phù hợp để hiểu kích thước batch và cách hệ thống gom việc. Ví dụ, một worker đọc các bản ghi từ queue rồi xử lý theo batch.

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class BatchMetrics {

    private final DistributionSummary batchSize;

    public BatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary
                .builder("worker.batch.size")
                .description("Số phần tử trong mỗi batch")
                .baseUnit("items")
                .register(registry);
    }

    public void recordBatchSize(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException(
                    "itemCount must not be negative"
            );
        }

        batchSize.record(itemCount);
    }
}
```

Giả sử worker ghi nhận các batch có 10, 20, 20, 50 và 100 phần tử:

- count = 5 batch.
- totalAmount = 200 items.
- mean = 40 items mỗi batch.
- max = 100 items trong cửa sổ max hiện tại.

Các thống kê này giúp trả lời liệu worker có thường xử lý batch quá nhỏ, có batch rất lớn hay kích thước batch thay đổi mạnh giữa các lần chạy. Khi kết hợp với Timer đo thời gian xử lý, có thể đánh giá sự đánh đổi giữa throughput và latency.

Nếu batch rỗng là một lần xử lý có ý nghĩa, có thể ghi nhận giá trị 0 để phân phối thể hiện các batch rỗng. Nếu batch rỗng có nghĩa không có batch nào được tạo, hãy không ghi nhận. Điều quan trọng là thống nhất ngữ nghĩa của một lần record trong toàn bộ instrumentation.

## 5. Đo lượng công việc mỗi lượt xử lý

Không phải lúc nào số phần tử cũng phản ánh đúng lượng công việc. Ví dụ, một batch có 10 ảnh nhỏ có thể xử lý nhanh hơn batch có 10 ảnh lớn. Một worker có thể định nghĩa đại lượng công việc theo byte, số trang, số phép tính, số record đã biến đổi hoặc một đơn vị nghiệp vụ có thể cộng được.

Hãy chọn một đơn vị có ý nghĩa:

| Công việc | Đại lượng có thể ghi nhận | Base unit minh họa |
| --- | --- | --- |
| Nén file | Số byte đầu vào hoặc đầu ra mỗi lượt | bytes |
| Xử lý ảnh | Số pixel hoặc số ảnh mỗi batch | pixels hoặc images |
| Import dữ liệu | Số record được đọc hoặc ghi mỗi lượt | records |
| Tính toán | Số phần tử hoặc operation được xử lý | items hoặc operations |
| Đồng bộ dữ liệu | Số bản ghi được đồng bộ mỗi lượt | records |
| Gửi message | Số message trong mỗi lần flush | messages |

Ví dụ, một lượt import có thể ghi số record thực sự được xử lý:

```java
public void importBatch(List<ImportRecord> records) {
    int processed = process(records);

    importedRecordsPerBatch.record(processed);
}
```

Cần quyết định rõ ghi số phần tử đầu vào, số phần tử được xử lý thành công hay số phần tử đầu ra. Đây là ba đại lượng khác nhau khi có validation hoặc lỗi một phần. Nếu cần theo dõi riêng, dùng meter riêng hoặc tag kết quả với tập giá trị hữu hạn như `result=success` và `result=partial`.

Không cộng các đơn vị không tương thích vào cùng một DistributionSummary. Ví dụ không ghi byte, số record và thời gian vào cùng một meter chỉ vì tất cả đều là số. Name, base unit và ngữ nghĩa của một meter phải nhất quán.

## 6. Tạo và đọc DistributionSummary

Có thể tạo DistributionSummary trực tiếp từ MeterRegistry:

```java
DistributionSummary summary = DistributionSummary
        .builder("worker.batch.size")
        .description("Số phần tử trong mỗi batch")
        .baseUnit("items")
        .register(registry);

summary.record(100);
summary.record(200);
summary.record(300);
summary.record(400);

long count = summary.count();
double total = summary.totalAmount();
double mean = summary.mean();
double max = summary.max();
```

Khác với Timer, DistributionSummary không nhận TimeUnit khi đọc. Giá trị được ghi theo đơn vị mà ứng dụng quy ước và base unit mô tả. Vì vậy, hãy giữ cùng đơn vị trong toàn bộ đường đi của dữ liệu.

Có thể dùng builder để khai báo tag có cardinality được kiểm soát:

```java
DistributionSummary.builder("worker.batch.size")
        .description("Số phần tử trong mỗi batch")
        .baseUnit("items")
        .tag("worker", "invoice")
        .tag("result", "success")
        .register(registry);
```

Tag nên đến từ danh mục cấu hình hoặc enum hữu hạn. Không dùng batch ID, message ID, user ID hoặc tên file tùy ý làm tag.

## 7. Kiểm thử với dữ liệu đã biết

Dùng SimpleMeterRegistry để xác minh các thống kê từ bộ dữ liệu cố định:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class DistributionSummaryTest {

    @Test
    void calculatesStatisticsForKnownBatchSizes() {
        var registry = new SimpleMeterRegistry();

        DistributionSummary summary = DistributionSummary
                .builder("worker.batch.size")
                .baseUnit("items")
                .register(registry);

        summary.record(100);
        summary.record(200);
        summary.record(300);
        summary.record(400);

        assertThat(summary.count()).isEqualTo(4L);
        assertThat(summary.totalAmount()).isEqualTo(1000.0);
        assertThat(summary.mean()).isEqualTo(250.0);
        assertThat(summary.max()).isEqualTo(400.0);
    }
}
```

Bài kiểm thử xác nhận mỗi lần record được tính là một quan sát và các thống kê được tính theo đúng dữ liệu. Nên có thêm test cho:

- Một quan sát duy nhất.
- Giá trị bằng 0 nếu đó là dữ liệu hợp lệ.
- Nhiều lần ghi cùng một giá trị.
- Batch size thay đổi theo từng lần.
- Giá trị đầu vào âm hoặc không hợp lệ theo chính sách của ứng dụng.
- Các tag khác nhau tạo thành các meter riêng.

Không dùng thời gian chạy thật để kiểm tra DistributionSummary. Giá trị cần ghi là dữ liệu nghiệp vụ như byte hoặc số phần tử, vì vậy có thể kiểm thử bằng các con số cố định.

## 8. Histogram và percentile

Count, totalAmount, mean và max chưa mô tả đầy đủ hình dạng phân phối. Hai nhóm payload có thể có cùng mean nhưng khác nhau đáng kể: nhóm thứ nhất có kích thước gần nhau, nhóm thứ hai có nhiều payload nhỏ và một số payload rất lớn.

Histogram và percentile giúp quan sát sự phân tán:

- p50 cho biết trung vị, một nửa quan sát không vượt quá ngưỡng này.
- p90 hoặc p95 cho thấy vùng giá trị cao của phần lớn quan sát.
- p99 giúp quan sát đuôi phân phối, nhưng cần đủ số mẫu để diễn giải ổn định.
- Histogram cho biết số quan sát nằm trong các khoảng giá trị.

Có thể cấu hình percentile trên DistributionSummary:

```java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload")
        .description("Kích thước payload request")
        .baseUnit("bytes")
        .publishPercentiles(0.50, 0.90, 0.95, 0.99)
        .register(registry);
```

Các percentile được tính trong tiến trình và được xuất như các giá trị thống kê của meter. Chúng hữu ích khi muốn đọc percentile tại từng instance, nhưng không thể cộng hoặc lấy trung bình percentile của nhiều instance để có percentile toàn hệ thống.

Nếu backend hỗ trợ histogram, có thể cấu hình percentile histogram:

```java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload")
        .description("Kích thước payload request")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .register(registry);
```

Histogram tạo thêm chuỗi thời gian và làm tăng chi phí lưu trữ, ingest và truy vấn. Đổi lại, backend hỗ trợ có thể tổng hợp bucket giữa các instance để tính percentile toàn cục. Cần xác nhận khả năng và quy tắc của backend đang dùng.

### Chọn ngưỡng histogram theo miền dữ liệu

Với kích thước payload, các ngưỡng có thể là 1 KiB, 4 KiB, 16 KiB, 64 KiB và 256 KiB. Với số phần tử batch, ngưỡng có thể là 10, 50, 100, 500 và 1.000. Ngưỡng phải phản ánh cách ứng dụng sử dụng dữ liệu và các giới hạn vận hành thực tế.

Không sao chép cùng một cấu hình histogram cho mọi DistributionSummary. Payload byte và số record có miền giá trị khác nhau. Hãy cân nhắc số bucket, độ rộng khoảng và mục tiêu truy vấn trước khi bật histogram.

## 9. Diễn giải số đo trong vận hành

Các thống kê có thể được dùng để phát hiện những thay đổi khác nhau:

| Quan sát | Cách diễn giải có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Mean payload tăng | Request hoặc response trung bình lớn hơn | Thay đổi API, client hoặc dữ liệu đầu vào |
| Max tăng đột biến | Có payload hoặc batch rất lớn trong cửa sổ max | Một route, tenant hoặc loại tác vụ tạo dữ liệu lớn |
| Count tăng, totalAmount tăng tương ứng | Có nhiều payload hoặc batch hơn | Lưu lượng và tần suất công việc |
| Count ổn định nhưng totalAmount tăng | Mỗi payload hoặc batch trung bình lớn hơn | Thay đổi kích thước dữ liệu hoặc cách gom batch |
| p95 tăng nhưng mean ít thay đổi | Phần đuôi phân phối lớn hơn | Một nhóm dữ liệu lớn hoặc một số lượt xử lý bất thường |
| Batch size giảm liên tục | Worker có thể đang xử lý các lô nhỏ hơn | Cấu hình batch, thời gian chờ gom dữ liệu hoặc tốc độ producer |

Không kết luận nguyên nhân chỉ từ một meter. Ví dụ, payload mean tăng có thể do request lớn hơn, nhưng cũng có thể do tag hoặc cách ghi nhận thay đổi. Hãy đối chiếu với count, Timer, kết quả xử lý và các chiều tag đã được duyệt.

## 10. Ngân sách cardinality và dữ liệu an toàn

Mỗi tổ hợp name và tag có thể tạo một meter riêng. Nếu dùng tag có giá trị tùy ý như batch ID, file name, user ID hoặc request ID, số meter có thể tăng nhanh.

Nên dùng tag như:

- `worker=invoice` nếu danh sách worker được cấu hình hữu hạn.
- `result=success|failed|partial`.
- `format=json|csv|xml|other`.
- `source=api|queue|scheduled`.

Không dùng nội dung payload, tên file do người dùng gửi, mã batch hoặc ID của đối tượng nghiệp vụ làm tag. Với dữ liệu nhạy cảm, chỉ ghi số đo tổng hợp và tuân theo chính sách bảo vệ dữ liệu của ứng dụng.

Nếu cần giới hạn cardinality, có thể dùng MeterFilter:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;

@Bean
MeterFilter batchWorkerTagLimit() {
    return MeterFilter.maximumAllowableTags(
            "worker.batch.size",
            "worker",
            10,
            MeterFilter.deny()
    );
}
```

Ví dụ này giới hạn số giá trị tag `worker` cho nhóm meter có tên bắt đầu bằng `worker.batch.size`. Tên meter, tag key và giới hạn phải khớp với instrumentation thực tế. MeterFilter là lớp bảo vệ bổ sung; hãy chuẩn hóa dữ liệu trước khi tạo meter và theo dõi số meter bị từ chối.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng Counter để ghi số phần tử mỗi batch | Chỉ biết số lần, không biết kích thước từng batch | Dùng DistributionSummary |
| Dùng Timer cho kích thước payload | Sai ngữ nghĩa vì payload size không phải thời lượng | Dùng DistributionSummary |
| Nhầm count với totalAmount | Diễn giải sai số batch thành số item | Đặt tên thống kê rõ ràng |
| Ghi byte nhưng khai báo base unit khác | Dashboard hiển thị đơn vị sai | Thống nhất đơn vị ghi nhận và base unit |
| Dùng String.length() làm số byte UTF-8 | Đánh giá sai kích thước truyền tải | Đo byte sau khi encode |
| Trộn nhiều đại lượng vào một summary | Không thể diễn giải tổng và trung bình | Tách meter theo name và unit |
| Dùng ID động làm tag | Cardinality tăng mạnh | Dùng enum hoặc danh mục hữu hạn |
| Bật histogram quá rộng | Tăng số chuỗi và chi phí backend | Chọn bucket theo miền dữ liệu |
| Lấy trung bình percentile từ nhiều instance | Kết quả tổng hợp sai | Dùng histogram có thể tổng hợp ở backend |
| Chỉ xem mean | Bỏ qua các giá trị lớn ở đuôi phân phối | Xem thêm histogram và percentile |

## 12. Checklist triển khai

Trước khi đưa DistributionSummary vào ứng dụng, hãy kiểm tra:

1. Giá trị cần đo có phải số lượng hoặc kích thước không phải thời gian không?
2. Một lần `record()` đại diện cho đúng một quan sát nào?
3. Count là số payload, batch hay lượt xử lý?
4. TotalAmount có đơn vị và ý nghĩa rõ ràng không?
5. Base unit có khớp với giá trị thực tế được ghi không?
6. Mean và max có được diễn giải trong đúng phạm vi thống kê không?
7. Có cần histogram hoặc percentile để quan sát đuôi phân phối không?
8. Histogram có ngân sách số bucket và cardinality phù hợp không?
9. Tag có tập giá trị hữu hạn, không chứa dữ liệu nhạy cảm không?
10. Kiểm thử có dùng dữ liệu số cố định và kiểm tra các thống kê chính không?

## Kết luận

DistributionSummary phù hợp để đo phân phối của các đại lượng số không phải thời lượng như kích thước payload, số phần tử mỗi batch và lượng công việc mỗi lượt. Count cho biết số quan sát, totalAmount là tổng các giá trị đã ghi, mean là giá trị trung bình và max là giá trị lớn nhất trong cửa sổ thống kê hiện tại.

Hãy định nghĩa rõ một lần record đại diện cho điều gì, thống nhất đơn vị và base unit, rồi chọn histogram hoặc percentile khi cần hiểu phân phối sâu hơn. Kết hợp DistributionSummary với Counter, Gauge và Timer giúp quan sát được cả số lượt, trạng thái, kích thước công việc và thời gian xử lý mà vẫn giữ ngữ nghĩa từng metric rõ ràng.
