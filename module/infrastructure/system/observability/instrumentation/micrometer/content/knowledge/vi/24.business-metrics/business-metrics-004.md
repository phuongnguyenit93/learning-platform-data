# Đo kích thước dữ liệu, số phần tử hoặc lượng công việc mỗi lượt

## Mục tiêu

Nhiều chỉ số nghiệp vụ không chỉ đếm có bao nhiêu sự kiện đã xảy ra. Một hệ thống xử lý batch cần biết mỗi batch chứa bao nhiêu bản ghi; API cần biết response lớn đến mức nào; pipeline cần biết mỗi lượt xử lý bao nhiêu item hoặc bao nhiêu byte. Những giá trị này tạo thành một phân bố, vì vậy chỉ dùng Counter sẽ không trả lời được câu hỏi về kích thước trung bình hay các batch lớn bất thường.

Micrometer cung cấp DistributionSummary để ghi nhận các giá trị số không phải thời lượng. Mỗi lần record(value) tạo một observation. Từ các observation, ứng dụng có thể đọc số mẫu, tổng giá trị, trung bình và max theo cửa sổ thống kê; khi cấu hình histogram, backend còn có thể tính phân vị hoặc số mẫu nằm dưới các ngưỡng đã chọn.

Sau bài này, bạn có thể:

- Chọn đơn vị đo cho payload size, item count và workload mỗi batch.
- Xác định một observation tương ứng với một payload, một batch hay một lần xử lý.
- Phân biệt số batch được ghi nhận với tổng số item đã xử lý.
- Kết hợp DistributionSummary với Counter, Timer hoặc Gauge đúng mục đích.
- Thiết kế tag nghiệp vụ có cardinality hữu hạn.
- Đọc count, sum, mean và histogram trên hệ thống giám sát.

## Xác định chính xác đại lượng nghiệp vụ

Trước khi tạo meter, hãy định nghĩa mỗi observation đại diện cho điều gì. Cùng một con số 500 có thể mang ý nghĩa rất khác nhau:

- Một message có kích thước 500 bytes.
- Một batch có 500 bản ghi.
- Một đơn hàng có 500 item.
- Một lượt đồng bộ xử lý 500 đối tượng.

Tên metric, base unit và thời điểm gọi record() phải mô tả cùng một định nghĩa.

| Câu hỏi nghiệp vụ | Một observation là gì? | Đại lượng nên ghi |
|---|---|---|
| Response lớn đến mức nào? | Một response được tạo hoặc nhận | Số byte của payload |
| Một batch chứa bao nhiêu bản ghi? | Một batch được xử lý | Số record trong batch |
| Một đơn hàng có bao nhiêu item? | Một đơn hàng | Số item của đơn hàng |
| Mỗi lượt đồng bộ xử lý bao nhiêu đối tượng? | Một lượt đồng bộ | Số đối tượng đã xử lý trong lượt |
| Một message chứa bao nhiêu byte? | Một message | Kích thước message |

Định nghĩa cả trạng thái được tính:

- Nếu ghi kích thước payload ngay khi nhận, observation phản ánh payload đã nhận, kể cả khi xử lý sau đó thất bại.
- Nếu chỉ ghi batch sau khi commit thành công, observation phản ánh workload đã hoàn tất.
- Nếu retry một batch, quyết định ghi một observation cho mỗi attempt hay chỉ cho batch logic phải được nêu rõ.

Không thay đổi định nghĩa giữa các phiên bản ứng dụng. Nếu trước đây một observation là batch attempt, nhưng sau đó chuyển thành batch thành công, cùng metric sẽ không còn so sánh trực tiếp được theo thời gian.

## Vì sao dùng DistributionSummary?

DistributionSummary phù hợp với phân bố các đại lượng số không phải thời lượng và không âm:

- Payload size tính bằng bytes.
- Số item trong một đơn hàng.
- Số record mỗi batch.
- Số message được xử lý trong một lượt poll.
- Số đối tượng được đồng bộ trong một chu kỳ.

Mỗi lần record(500) tăng count một và totalAmount thêm 500. Nó không tăng count lên 500. Đây là khác biệt cốt lõi giữa số observation và lượng công việc nằm trong observation.

Ví dụ, ba batch lần lượt có 100, 200 và 300 record:

| Số liệu | Giá trị | Diễn giải |
|---|---:|---|
| count | 3 | Ba batch đã được ghi nhận |
| totalAmount | 600 | Tổng cộng 600 record trong các batch |
| mean | 200 | Trung bình 200 record mỗi batch |
| max | 300 | Batch lớn nhất trong cửa sổ thống kê hiện tại |

Nếu câu hỏi là “đã xử lý bao nhiêu batch?”, count trả lời câu hỏi đó. Nếu câu hỏi là “đã xử lý bao nhiêu record?”, totalAmount trả lời câu hỏi đó.

## Chọn meter theo câu hỏi

Không phải mọi đại lượng đều nên dùng DistributionSummary:

| Câu hỏi | Meter phù hợp | Lý do |
|---|---|---|
| Mỗi batch có bao nhiêu record? | DistributionSummary | Cần phân bố kích thước batch |
| Tổng số batch hoàn tất? | Counter | Chỉ cần đếm sự kiện |
| Tổng số record đã xử lý? | Counter tăng theo số record | Cần tổng lượng item |
| Xử lý một batch mất bao lâu? | Timer | Đại lượng là thời gian |
| Queue hiện có bao nhiêu message? | Gauge | Giá trị có thể tăng và giảm theo thời điểm |
| Mỗi message có bao nhiêu byte? | DistributionSummary | Cần phân bố kích thước payload |

Một quy tắc thực tế là dùng DistributionSummary để mô tả lượng công việc của từng lượt, Counter để đếm sự kiện hoặc tổng lượng, Timer để đo thời gian và Gauge để quan sát trạng thái hiện tại.

## Ví dụ: đo số record trong từng batch

Giả sử một worker đọc dữ liệu theo batch. Ta muốn biết:

1. Có bao nhiêu batch hoàn tất?
2. Mỗi batch có bao nhiêu record?
3. Tổng số record đã xử lý?
4. Batch có vượt ngưỡng vận hành dự kiến hay không?

Có thể dùng một DistributionSummary và hai Counter:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class BatchMetrics {
    private final DistributionSummary batchSize;
    private final Counter completedBatches;
    private final Counter processedRecords;

    public BatchMetrics(MeterRegistry registry, String pipeline) {
        this.batchSize = DistributionSummary.builder("business.batch.size")
                .description("Số record trong mỗi batch đã hoàn tất")
                .baseUnit("records")
                .tag("pipeline", pipeline)
                .publishPercentileHistogram()
                .serviceLevelObjectives(100, 500, 1_000)
                .register(registry);

        this.completedBatches = Counter.builder("business.batch.completed")
                .description("Tổng số batch đã hoàn tất")
                .tag("pipeline", pipeline)
                .register(registry);

        this.processedRecords = Counter.builder("business.records.processed")
                .description("Tổng số record đã xử lý")
                .baseUnit("records")
                .tag("pipeline", pipeline)
                .register(registry);
    }

    public void recordCompletedBatch(int recordCount) {
        if (recordCount < 0) {
            throw new IllegalArgumentException("recordCount must be non-negative");
        }

        batchSize.record(recordCount);
        completedBatches.increment();
        if (recordCount > 0) {
            processedRecords.increment(recordCount);
        }
    }
}
~~~

Khi batch commit thành công, gọi recordCompletedBatch() đúng một lần:

~~~java
List<Record> records = repository.fetchNextBatch(batchLimit);

processor.process(records);
transaction.commit();

batchMetrics.recordCompletedBatch(records.size());
~~~

Nếu processor hoặc transaction thất bại, ví dụ trên không ghi batch hoàn tất. Nếu muốn đo cả batch attempt, hãy tạo một metric riêng có tên thể hiện attempt và ghi nhận ở điểm kết thúc attempt. Không dùng một metric để trộn batch thành công với batch thất bại.

### Diễn giải các meter

Giả sử ba batch hoàn tất có kích thước 100, 200 và 300:

- business.batch.size có count bằng 3 và totalAmount bằng 600.
- business.batch.completed tăng 3.
- business.records.processed tăng 600.

Hai Counter cung cấp tổng tích lũy dễ truy vấn. DistributionSummary bổ sung phân bố kích thước mỗi batch để thấy batch nhỏ, lớn hoặc biến động bất thường.

Không nhất thiết phải tạo cả ba meter nếu hệ thống chỉ cần một câu trả lời. Chọn meter theo nhu cầu dashboard và cảnh báo để tránh tạo metric dư thừa.

## Ví dụ: đo kích thước payload

Với HTTP response hoặc message body, ghi kích thước theo bytes:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class PayloadMetrics {
    private final DistributionSummary responseBytes;

    public PayloadMetrics(MeterRegistry registry, String operation) {
        this.responseBytes = DistributionSummary
                .builder("business.payload.size")
                .description("Kích thước payload được tạo")
                .baseUnit("bytes")
                .tag("operation", operation)
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordResponse(byte[] body) {
        responseBytes.record(body.length);
    }
}
~~~

Đo bằng byte giúp thống nhất với kích thước bộ nhớ và giao thức truyền tải. Nếu dashboard cần hiển thị KiB hoặc MiB, có thể đổi đơn vị ở bước trình bày hoặc tạo metric đã quy đổi với tên và base unit rõ ràng. Không ghi lúc thì bytes, lúc thì kilobytes vào cùng một summary.

Nếu response được nén, hãy xác định đang đo kích thước trước nén hay sau nén. Hai số liệu trả lời câu hỏi khác nhau:

- Kích thước trước nén phản ánh lượng dữ liệu nghiệp vụ.
- Kích thước sau nén phản ánh lượng byte truyền qua mạng.

Nếu cả hai đều cần thiết, dùng hai tên metric riêng, chẳng hạn business.payload.uncompressed.size và business.payload.transmitted.size.

## Ví dụ: số item trong một đơn hàng

Một đơn hàng là một observation. Giá trị ghi là số item của đơn hàng đó:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class OrderMetrics {
    private final DistributionSummary itemsPerOrder;

    public OrderMetrics(MeterRegistry registry) {
        this.itemsPerOrder = DistributionSummary
                .builder("business.order.items")
                .description("Số item trong mỗi đơn hàng được chấp nhận")
                .baseUnit("items")
                .publishPercentileHistogram()
                .serviceLevelObjectives(1, 5, 10, 25, 50)
                .register(registry);
    }

    public void recordAcceptedOrder(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException("itemCount must be non-negative");
        }

        itemsPerOrder.record(itemCount);
    }
}
~~~

Đơn hàng rỗng có itemCount bằng 0 vẫn là một observation hợp lệ nếu domain cho phép. DistributionSummary chấp nhận giá trị 0; giá trị âm bị bỏ qua bởi implementation chuẩn, vì vậy nên xác thực đầu vào để tránh âm thầm mất mẫu.

Nếu có nhiều loại đơn hàng, có thể thêm tag order_type với tập giá trị nhỏ như standard, express hoặc subscription. Không thêm order_id vì mỗi đơn hàng sẽ tạo một time series riêng.

## Chọn đơn vị và scale

### Dùng một đơn vị nhất quán

Base unit nên mô tả đại lượng:

| Metric | Base unit gợi ý |
|---|---|
| Payload size | bytes |
| Batch size | records |
| Items per order | items |
| Messages per poll | messages |
| Work units per run | units |

Đơn vị cần nhất quán giữa mọi instance và phiên bản ứng dụng. Nếu có nhiều currency, nhiều loại đơn vị vật lý hoặc nhiều cách quy đổi, không cộng chúng vào cùng một totalAmount.

### Dùng scale khi cần quy đổi có chủ đích

DistributionSummary.Builder hỗ trợ scale để nhân mỗi giá trị trước khi ghi. Ví dụ, đầu vào là tỷ lệ từ 0 đến 1 nhưng dashboard muốn miền phần trăm từ 0 đến 100:

~~~java
DistributionSummary completionPercent = DistributionSummary
        .builder("business.import.completion")
        .description("Tỷ lệ hoàn tất import theo phần trăm")
        .baseUnit("percent")
        .scale(100)
        .register(registry);

completionPercent.record(0.85); // ghi nhận 85 percent
~~~

Count vẫn là số observation; totalAmount, mean và max phản ánh giá trị sau scale. Ghi rõ cách quy đổi trong description và tên metric để người truy vấn không nhầm 0.85 với 85.

## Đọc phân bố và chọn ngưỡng nghiệp vụ

Count và totalAmount cho biết số mẫu và tổng lượng. Mean cho biết kích thước trung bình. Tuy nhiên, mean có thể che khuất một số batch rất lớn hoặc rất nhỏ.

Ví dụ, các batch có kích thước 10, 10, 10 và 970 record tạo mean 250. Phần lớn batch chỉ có 10 record; một batch rất lớn kéo mean lên. Khi cần hiểu phân bố, hãy bật histogram hoặc percentile histogram và chọn bucket/SLO phù hợp.

Trong ví dụ BatchMetrics, các SLO boundaries 100, 500 và 1.000 record có thể giúp dashboard trả lời:

- Bao nhiêu batch không vượt 100 record?
- Bao nhiêu batch nằm trong các ngưỡng đã quan tâm?
- Phân bố batch size có dịch chuyển khi lưu lượng tăng không?

SLO boundary không tự động biến thành cảnh báo. Nó tạo bucket để backend truy vấn; quy tắc cảnh báo hoặc SLO vẫn cần được định nghĩa ở hệ thống giám sát.

### Percentile phía ứng dụng và histogram phía backend

Micrometer có thể tính percentile phía ứng dụng bằng publishPercentiles(...). Các percentile này hữu ích cho dashboard của một instance, nhưng không thể gộp chính xác percentile của nhiều instance bằng cách lấy trung bình.

Percentile histogram xuất bucket để backend tổng hợp trước khi tính phân vị. Với hệ thống nhiều instance, histogram thường phù hợp hơn nếu cần percentile toàn service. Histogram tạo thêm series cho mỗi bucket và mỗi tổ hợp tag, vì vậy cần giới hạn cardinality và số bucket.

Không so sánh p95 tính phía ứng dụng với p95 histogram phía backend mà không hiểu nguồn và cách tổng hợp của chúng.

## Truy vấn Prometheus

Với Prometheus registry, DistributionSummary thường được xuất thành các chuỗi count và sum. Khi bật histogram, registry còn xuất bucket. Tên metric cuối cùng phụ thuộc naming convention và base unit.

Ví dụ minh họa:

~~~text
business_batch_size_records_count
business_batch_size_records_sum
business_batch_size_records_bucket
~~~

### Số batch mỗi giây

~~~promql
sum by (pipeline) (
  rate(business_batch_size_records_count[5m])
)
~~~

### Số record xử lý mỗi giây

~~~promql
sum by (pipeline) (
  rate(business_batch_size_records_sum[5m])
)
~~~

### Kích thước batch trung bình

~~~promql
sum by (pipeline) (
  rate(business_batch_size_records_sum[5m])
)
/
sum by (pipeline) (
  rate(business_batch_size_records_count[5m])
)
~~~

Đây là mean có trọng số trên các observation trong cửa sổ năm phút. Khi có nhiều instance, cộng sum và count trước khi chia; không lấy trung bình các mean riêng của từng instance.

### Phân vị batch size

Khi đã bật histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, pipeline) (
    rate(business_batch_size_records_bucket[5m])
  )
)
~~~

Thay tên metric và tag bằng dữ liệu thực tế tại endpoint export. Nếu histogram chưa bật, truy vấn bucket sẽ không có dữ liệu.

## Thiết kế tag nghiệp vụ có cardinality thấp

Tag giúp phân tích theo chiều nghiệp vụ, nhưng mỗi tổ hợp tag tạo một time series. Hãy chọn những dimension có số giá trị nhỏ và được kiểm soát:

| Tag phù hợp | Ví dụ |
|---|---|
| pipeline | orders, inventory, billing |
| operation | import, export, reconcile |
| channel | web, mobile, store |
| result | success, rejected, failed |
| order_type | standard, express, subscription |

Tránh đưa các giá trị sau vào tag:

- order_id, customer_id, user_id.
- batch_id hoặc message_id.
- File name hoặc object key duy nhất.
- URL đầy đủ hoặc query string.
- Exception message hoặc payload.

Nếu cần điều tra một batch cụ thể, dùng log hoặc trace với batch ID. Metrics trả lời xu hướng và phân bố của nhiều batch; log/trace cung cấp chi tiết của một batch.

Nếu một chiều nghiệp vụ có quá nhiều giá trị, hãy nhóm trước khi ghi, ví dụ region theo khu vực vận hành hoặc customer_tier theo các gói cố định. Không dựa vào MeterFilter để thay thế việc thiết kế dimension đúng ở nguồn.

## Kiểm thử bằng SimpleMeterRegistry

Unit test nên xác minh một observation tương ứng với một batch và phân biệt count với totalAmount:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class BatchMetricsTest {
    @Test
    void recordsBatchCountAndTotalProcessedRecordsSeparately() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            BatchMetrics metrics = new BatchMetrics(registry, "orders");

            metrics.recordCompletedBatch(100);
            metrics.recordCompletedBatch(200);
            metrics.recordCompletedBatch(300);

            DistributionSummary batchSize = registry.get("business.batch.size")
                    .tag("pipeline", "orders")
                    .summary();
            Counter completedBatches = registry.get("business.batch.completed")
                    .tag("pipeline", "orders")
                    .counter();
            Counter processedRecords = registry.get("business.records.processed")
                    .tag("pipeline", "orders")
                    .counter();

            assertThat(batchSize.count()).isEqualTo(3);
            assertThat(batchSize.totalAmount()).isEqualTo(600.0);
            assertThat(batchSize.mean()).isEqualTo(200.0);
            assertThat(completedBatches.count()).isEqualTo(3.0);
            assertThat(processedRecords.count()).isEqualTo(600.0);
        } finally {
            registry.close();
        }
    }
}
~~~

Test này bắt lỗi phổ biến là hiểu nhầm DistributionSummary.count() thành tổng số item. Nó cũng kiểm tra hai Counter có semantics khác nhau: số batch hoàn tất và tổng record đã xử lý.

Nên kiểm tra thêm:

- Batch rỗng có được tính là observation hay không theo domain.
- Batch thất bại có được ghi ở metric attempt riêng không.
- Đầu vào âm bị từ chối trước khi gọi record().
- Các tag nằm trong tập giá trị cho phép.
- Histogram bucket được export khi cấu hình SLO hoặc percentile histogram.
- PromQL mean và throughput khớp với dữ liệu test.

## Những lỗi thường gặp

**Đếm item bằng count của DistributionSummary.** count là số lần record(), không phải tổng giá trị. Dùng totalAmount hoặc Counter tăng theo số item.

**Không xác định observation boundary.** Ghi một lần cho mỗi item và ghi một lần cho mỗi batch tạo ra hai phân bố khác nhau. Chọn một định nghĩa và giữ ổn định.

**Ghi cả attempt và success vào cùng summary.** Khi retry, cùng một batch logic có thể được tính nhiều lần. Tách metric attempt và completed nếu cả hai đều cần.

**Trộn đơn vị.** Không ghi bytes cùng KiB hoặc records cùng messages vào một meter nếu chúng không cùng ý nghĩa.

**Chỉ nhìn mean.** Một số batch lớn bất thường có thể bị che khuất. Dùng histogram hoặc percentile khi cần xem phân bố.

**Tổng hợp percentile sai cách.** Không lấy trung bình p95 của từng instance để suy ra p95 toàn service. Dùng histogram bucket có thể tổng hợp.

**Đưa định danh riêng vào tag.** ID của batch, đơn hàng hoặc message làm cardinality tăng nhanh. Đưa định danh vào log hoặc trace.

**Dùng DistributionSummary cho thời gian.** Nếu đại lượng là latency, dùng Timer để giữ đúng semantics và đơn vị thời gian.

## Checklist triển khai

1. Định nghĩa một observation tương ứng với payload, batch, order hay processing run.
2. Xác định trạng thái nào được tính: received, attempted, committed hay completed.
3. Chọn DistributionSummary cho phân bố số lượng hoặc kích thước không phải thời gian.
4. Chọn Counter riêng nếu cần đếm batch hoặc tổng item.
5. Dùng Timer cho duration và Gauge cho trạng thái tức thời.
6. Đặt base unit thống nhất và chỉ scale khi có quy tắc quy đổi rõ ràng.
7. Bật histogram/SLO khi cần phân tích ngưỡng hoặc percentile toàn service.
8. Giữ tag nghiệp vụ có cardinality hữu hạn.
9. Tổng hợp mean từ tổng sum chia tổng count.
10. Kiểm thử count, totalAmount, mean và các Counter liên quan.
11. Xác minh tên metric, đơn vị, bucket và truy vấn tại backend.

## Kết luận

Đo kích thước dữ liệu và lượng công việc mỗi lượt cần một định nghĩa observation rõ ràng. DistributionSummary ghi nhận một giá trị cho mỗi payload, batch, đơn hàng hoặc lượt xử lý; count đếm số observation, còn totalAmount cho biết tổng lượng nằm trong các observation đó. Kết hợp summary với Counter khi cần tổng sự kiện hoặc tổng item, dùng histogram khi cần phân bố và percentile, và giữ tag nghiệp vụ có cardinality thấp. Khi các semantics này ổn định, dashboard có thể cho biết không chỉ hệ thống đã làm bao nhiêu việc mà còn mỗi lượt làm nhiều hay ít và phân bố thay đổi ra sao.

## Tài liệu tham khảo

- [Micrometer - Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): ghi nhận giá trị số, scale, histogram, percentile và cấu hình thống kê.
- [Micrometer - Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): percentile phía ứng dụng, percentile histogram và tổng hợp phân vị.
- [Micrometer - Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): semantics của Counter và cách đếm sự kiện/tổng lượng.
- [Prometheus - Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): bucket, count, sum và truy vấn histogram_quantile.
