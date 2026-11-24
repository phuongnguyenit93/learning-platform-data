# Đặt ngân sách CPU, bộ nhớ và số chuỗi cho từng nhóm phép đo

Instrumentation có chi phí. Mỗi lần ghi Counter hoặc Timer đều thực hiện công việc trong ứng dụng; mỗi meter cần đối tượng và trạng thái trong bộ nhớ; mỗi tổ hợp tag có thể tạo một hoặc nhiều time series ở backend. Histogram làm tăng số chuỗi theo số bucket, còn scrape interval quyết định tần suất dữ liệu được thu thập.

Vì vậy, không nên bật mọi meter, mọi tag và mọi histogram rồi mới xử lý chi phí khi hệ thống tăng tải. Hãy đặt ngân sách cho từng nhóm phép đo, xác định giới hạn ở ứng dụng và backend, sau đó đo lại bằng workload đại diện.

Một ngân sách tốt tách ít nhất bốn loại tài nguyên:

- **CPU instrumentation:** thời gian CPU tiêu thụ để tạo, tìm và cập nhật meter.
- **Bộ nhớ ứng dụng:** meter objects, tag identity, histogram và distribution buffers.
- **Active time series:** số chuỗi đang tồn tại trong metrics backend.
- **Ingestion và churn:** số mẫu được scrape, dung lượng lưu trữ và tốc độ xuất hiện/biến mất của series.

Các loại chi phí liên quan với nhau nhưng không thể thay thế cho nhau. Giảm scrape frequency có thể giảm số mẫu mỗi giây, nhưng không làm giảm số meter hoặc active series. Giảm trace sampling không làm giảm chi phí Counter/Timer. Giới hạn số meter trong registry cũng chưa chắc giới hạn chính xác số series nếu một meter xuất nhiều bucket.

## 1. Ngân sách phải gắn với nhóm phép đo

Bắt đầu bằng việc chia instrumentation thành các nhóm có mục đích và mức độ quan trọng khác nhau.

| Nhóm | Ví dụ | Mức độ ưu tiên | Chính sách thường phù hợp |
|---|---|---|---|
| Nền tảng thiết yếu | JVM memory, GC, process, request count | Luôn cần để vận hành | Tag ít, không bật histogram tràn lan |
| Request và dependency quan trọng | HTTP server, HTTP client, database call | Cao | Timer; histogram cho các luồng cần percentile/SLO |
| Nghiệp vụ cốt lõi | Payment, order, checkout | Cao | Counter/Timer với dimensions hữu hạn |
| Tài nguyên và backlog | Queue depth, executor, connection pool | Cao khi có thành phần tương ứng | Gauge và binder có kiểm soát |
| Chẩn đoán chuyên sâu | Chi tiết từng operation hiếm, histogram bổ sung | Theo nhu cầu | Bật có chọn lọc, có thời hạn và chủ sở hữu |
| Tạm thời khi điều tra | Meter thử nghiệm hoặc tag mới | Tạm thời | Theo dõi chi phí, có kế hoạch gỡ bỏ |

Không phải service nào cũng cần đủ các nhóm. Một service không dùng cache không cần ngân sách cho cache binder; một API không có workflow dài có thể không cần LongTaskTimer.

Với mỗi nhóm, ghi rõ:

- Câu hỏi vận hành mà nhóm metric trả lời.
- Meter name và loại meter.
- Tag keys và số giá trị tối đa dự kiến.
- Có histogram hoặc percentile hay không.
- Chủ sở hữu dashboard/alert.
- Ngân sách CPU, heap, active series và ingestion.
- Điều kiện tắt hoặc xem xét lại instrumentation.

## 2. Phân biệt chi phí trong JVM và chi phí ở metrics backend

Micrometer chạy trong ứng dụng, còn Prometheus hoặc hệ thống metrics khác có thể chạy ở hạ tầng riêng. Cần đo cả hai phía.

| Loại chi phí | Phát sinh ở đâu | Yếu tố ảnh hưởng |
|---|---|---|
| CPU ghi meter | JVM ứng dụng | Số lần record, lookup meter, tag, histogram update, contention |
| Heap của meter | JVM ứng dụng | Số meter, số tổ hợp tag, distribution statistics, buffer |
| CPU scrape/export | Ứng dụng và collector | Số series, kích thước exposition, scrape interval, serialization |
| Active series | Metrics backend | Metric families, label combinations, histogram buckets, số instance |
| Ingestion | Metrics backend | Active series chia cho scrape interval |
| Storage | Metrics backend | Số mẫu, retention, compression và churn |
| Network | Ứng dụng/collector/backend | Payload scrape hoặc push, tần suất và số series |

Một MeterRegistry có thể chỉ chứa vài nghìn meter nhưng mỗi Timer histogram xuất nhiều series. Ngược lại, một metric family có ít bucket nhưng nhiều tổ hợp tag vẫn tạo số series rất lớn.

Cũng cần phân biệt meter count với time-series count. Meter count là số meter identity trong registry; time-series count là số chuỗi backend nhìn thấy sau khi áp dụng tag, naming convention và quy tắc export.

## 3. Đặt ngân sách CPU cho instrumentation

CPU overhead xuất hiện khi ứng dụng đăng ký meter, tìm meter theo identity và cập nhật giá trị. Counter increment đơn giản thường nhẹ, nhưng tổng chi phí tăng khi có nhiều lần ghi, nhiều tag combinations, nhiều histogram và nhiều luồng cùng cập nhật.

Các nguồn chi phí thường gặp:

- Tạo meter mới liên tục thay vì đăng ký một lần và tái sử dụng.
- Dùng tag động khiến registry phải tạo thêm meter identity.
- Ghi nhiều Timer hoặc DistributionSummary trong một request nóng.
- Bật histogram cho mọi route hoặc mọi tổ hợp tag.
- Dùng custom handler hoặc filter thực hiện công việc nặng trên mỗi Observation.
- Scrape endpoint chứa quá nhiều series, làm tăng serialization và CPU.

Không thể đưa ra một con số CPU cố định cho mọi Counter hoặc Timer. Kết quả phụ thuộc JDK, CPU, registry, phiên bản Micrometer, workload, concurrency và cách dùng tag. Hãy đặt ngân sách bằng benchmark trên ứng dụng thật.

### Đo chi phí tăng thêm

Một quy trình so sánh:

1. Chạy workload đại diện với instrumentation tối thiểu làm baseline.
2. Bật nhóm meter nền tảng và đo lại.
3. Bật nhóm request Timer và đo lại.
4. Bật histogram cho nhóm quan trọng và đo lại.
5. Bật thêm từng nhóm business hoặc binder và đo lại.
6. So sánh throughput, CPU, allocation rate, latency p50/p95 và heap sau warm-up.

Giữ request rate, payload, concurrency, dữ liệu và thời gian chạy tương đương. Chạy đủ lâu để JVM warm-up và lặp lại nhiều lần. Không kết luận từ một lần chạy ngắn.

JMH phù hợp để đo overhead của một thao tác nhỏ như `Counter.increment()` hoặc `Timer.record()`. Load test hoặc benchmark end-to-end mới cho biết tác động thực tế đến request latency và throughput khi registry, exporter, scrape và concurrency cùng hoạt động.

### Tính CPU cost trên mỗi operation

Có thể ước lượng chi phí tăng thêm:

```text
CPU seconds per operation
    = delta CPU cores / operations per second
```

Ví dụ minh họa: workload ổn định ở 20.000 operations/second. Sau khi bật một nhóm instrumentation, CPU tăng từ 0,80 core lên 0,82 core. Phần tăng là 0,02 core:

```text
0.02 CPU-seconds/second / 20,000 operations/second
= 0.000001 CPU-seconds/operation
= 1 microsecond CPU/operation
```

Đây chỉ là phép quy đổi để so sánh hai lần chạy tương đương. Cần kiểm tra nhiễu đo, background work và độ ổn định workload trước khi gán toàn bộ phần tăng cho instrumentation.

## 4. Đặt ngân sách bộ nhớ trong ứng dụng

Mỗi meter cần lưu identity, tên, loại, tag và trạng thái đo. Một meter có histogram hoặc percentile có thể cần thêm cấu trúc lưu trữ cho phân phối. Khi tag cardinality tăng, số meter identity cũng tăng theo.

Những yếu tố làm heap tăng:

- Nhiều tên meter khác nhau được tạo động.
- Nhiều tổ hợp tag trên cùng meter name.
- Histogram hoặc percentile được bật cho quá nhiều meter.
- Distribution buffer có cấu hình lớn.
- Meter cũ không còn được dùng nhưng vẫn còn được giữ trong registry.
- Registry hoặc custom instrumentation được tạo lặp lại theo request hoặc theo context.

Không nên lấy một mức byte/meter cố định từ ví dụ trên mạng để tính heap. Cấu trúc cụ thể thay đổi theo loại meter, registry, JDK và cấu hình. Hãy đo heap sau warm-up và khi số meter/tag combinations tăng theo workload.

### Đo heap delta

Có thể so sánh:

- Heap sau khi ứng dụng khởi động, trước traffic.
- Heap sau warm-up với instrumentation cơ bản.
- Heap sau khi tạo đủ meter và tag combinations dự kiến.
- Heap khi bật histogram cho nhóm cần percentile.
- Heap khi traffic tăng nhưng số meter identity giữ nguyên.

Dùng heap histogram, Java Flight Recorder hoặc profiler để xác định đối tượng Micrometer và cấu trúc liên quan chiếm bao nhiêu bộ nhớ. Theo dõi cả heap used, allocation rate và garbage collection; chỉ nhìn heap committed không cho biết lượng đối tượng metrics đang sống.

Nếu heap tăng liên tục theo số request, kiểm tra xem tag value hoặc meter name có thay đổi theo từng request hay không. Một registry được thiết kế đúng thường có số meter ổn định sau khi tập tag values hữu hạn đã xuất hiện.

## 5. Tính số tổ hợp tag trước khi tạo meter

Mỗi tổ hợp giá trị tag tạo một meter identity riêng. Nếu meter có nhiều tag, số tổ hợp tiềm năng tăng theo tích số giá trị của từng tag.

Công thức ước lượng:

```text
C = V1 * V2 * ... * Vn
```

Trong đó:

- `C` là số tổ hợp tag tối đa.
- `Vi` là số giá trị dự kiến của tag thứ `i`.
- `n` là số tag keys.

Ví dụ một HTTP Timer có:

- 20 route templates.
- 4 HTTP methods.
- 5 status groups.
- 3 outcomes.

Số tổ hợp tối đa trên một instance:

```text
20 * 4 * 5 * 3 = 1,200
```

Với 6 instance, backend có thể quan sát khoảng:

```text
1,200 * 6 = 7,200
```

label sets. Đây là giới hạn lý thuyết theo các giá trị giả định; số tổ hợp thực tế có thể thấp hơn nếu không phải mọi kết hợp đều xuất hiện.

Không phải tag nào cũng cần tồn tại. Ví dụ `outcome` có thể suy ra từ status group; giữ cả hai chỉ khi dashboard cần phân tích riêng và chi phí tăng thêm đã được chấp nhận.

## 6. Histogram nhân số series lên như thế nào?

Một Counter hoặc Gauge thường tạo một series cho mỗi label set. Classic histogram của Prometheus xuất các bucket cùng `_sum` và `_count`.

Nếu có (B) bucket boundaries và (B) đã bao gồm bucket `+Inf`, số series cơ bản cho một label set xấp xỉ:

```text
S_histogram = B + 2
```

Hai series bổ sung là `_sum` và `_count`. Registry hoặc cấu hình cụ thể có thể export thêm series khác; hãy xác minh exposition thực tế.

Tiếp tục ví dụ trên, nếu histogram có 10 boundaries bao gồm `+Inf`:

```text
7,200 * (10 + 2) = 86,400
```

Một HTTP Timer có thể tạo khoảng 86.400 active series trong ví dụ này, thay vì 7.200 series nếu chỉ xuất một giá trị đơn cho mỗi label set. Con số chưa tính các meter khác và các series phụ do registry tạo.

Đây là lý do phải tính bucket cùng tag combinations trước khi bật histogram. Histogram 10 bucket trên một meter có cardinality thấp có thể hợp lý; cùng cấu hình trên meter có tag tenant hoặc URL động có thể trở thành chi phí rất lớn.

## 7. Tag động có thể phá vỡ ngân sách

Giả sử thêm tag `tenant` có 1.000 giá trị vào ví dụ trước:

```text
7,200 * 1,000 = 7,200,000
```

label sets. Với 12 series cho mỗi histogram label set:

```text
7,200,000 * 12 = 86,400,000
```

Đây là ước lượng 86,4 triệu series cho một nhóm histogram trong tình huống mọi kết hợp đều xuất hiện. Một tag có cardinality cao có thể làm ngân sách tăng theo cấp số nhân khi kết hợp với các chiều khác.

Không dùng các giá trị sau làm metric tags nếu chúng không có tập hữu hạn được kiểm soát:

- Request ID, trace ID, order ID, customer ID.
- URL đầy đủ chứa path variable.
- Email, số điện thoại hoặc định danh người dùng.
- Exception message hoặc SQL động.
- Tên file, tên object hoặc chuỗi tự do từ request.

Dùng route template thay URL động, nhóm exception thành error category và dùng log/trace để điều tra từng ID. Nếu cần phân tích tenant, cân nhắc một tập nhóm tenant hữu hạn hoặc hệ thống analytics phù hợp thay vì tạo một series cho từng tenant.

## 8. Đặt ngân sách active series theo service

Active series budget là giới hạn số chuỗi metrics mà service được phép tạo trong backend. Ngân sách cần bao gồm:

- JVM và process metrics.
- HTTP server/client metrics.
- Database, cache, executor và messaging metrics.
- Business metrics.
- Histogram buckets và các series phụ.
- Common tags, instance labels và số replica.

Có thể đặt ngân sách theo ba cấp:

1. **Toàn service:** tổng active series tối đa.
2. **Nhóm phép đo:** request, JVM, database, business, diagnostics.
3. **Meter family:** giới hạn tổ hợp tag và histogram riêng cho từng meter quan trọng.

Không chia ngân sách chỉ theo số meter. Một meter histogram có thể tạo nhiều series hơn hàng chục Counter đơn giản.

Ví dụ ngân sách minh họa cho một service:

| Nhóm | Budget active series giả định | Ghi chú |
|---|---:|---|
| JVM/process | 1.000 | Built-in metrics và pool tags |
| HTTP request | 8.000 | Histogram chỉ cho route quan trọng |
| Database/cache/executor | 2.000 | Theo số pool và resource thực tế |
| Business metrics | 2.000 | Tag theo channel, provider, outcome |
| Diagnostics | 1.000 | Chỉ bật khi có nhu cầu |
| Dự phòng | 2.000 | Dành cho thay đổi có kiểm soát |
| **Tổng** | **16.000** | Ngân sách ví dụ, không phải mặc định chung |

Các số trên chỉ minh họa cách phân bổ. Ngân sách thực tế phải dựa trên khả năng của Prometheus/metrics backend, số service, số replica, retention, scrape interval và chi phí hạ tầng.

Nếu một nhóm vượt ngân sách, trước hết tìm tag hoặc histogram gây tăng. Không vội tăng giới hạn toàn service vì điều đó có thể che giấu cardinality không kiểm soát.

## 9. Phân biệt active series, samples và series churn

Ba đại lượng này trả lời ba câu hỏi khác nhau:

- **Active series:** có bao nhiêu label sets đang tồn tại tại một thời điểm?
- **Samples ingested:** backend nhận bao nhiêu điểm dữ liệu trong một đơn vị thời gian?
- **Series churn:** có bao nhiêu series mới xuất hiện hoặc cũ biến mất trong một khoảng thời gian?

Với scrape interval (T) giây và (S) active series, tốc độ ingest xấp xỉ:

```text
R_samples = S / T
```

Ví dụ 86.400 active series, scrape mỗi 15 giây:

```text
86,400 / 15 = 5,760
```

Backend nhận khoảng 5.760 samples/second từ nhóm metrics đó, giả sử mọi series đều có mặt trong mỗi lần scrape.

Tăng scrape interval từ 15 giây lên 30 giây sẽ giảm gần một nửa sample rate trong điều kiện tương đương, nhưng active series vẫn là 86.400. Dashboard có độ phân giải thấp hơn và alert có thể phát hiện thay đổi chậm hơn.

Series churn tăng khi tag values liên tục thay đổi, ví dụ URL chứa ID, request ID hoặc tên file. Dù active series tại một thời điểm không quá cao, số series mới trong ngày có thể lớn, làm tăng chi phí index, compaction và storage. Vì vậy, ngân sách phải theo dõi cả active series và churn.

## 10. Tính ingestion và retention

Số mẫu lý thuyết trong một ngày:

```text
N_samples_per_day = S * (86,400 / T)
```

Với 10.000 active series và scrape interval 15 giây:

```text
10,000 * 5,760 = 57,600,000
```

Tức khoảng 57,6 triệu samples mỗi ngày, trước khi tính series không liên tục hoặc các yếu tố vận hành khác.

Dung lượng lưu trữ không thể suy ra chính xác chỉ từ số mẫu. Nó phụ thuộc encoding, compression, label index, churn, retention và implementation của backend. Hãy lấy bytes/sample thực tế từ metrics backend hoặc capacity report của hệ thống đang dùng.

Không giảm scrape interval để xử lý cardinality. Nếu có quá nhiều active series, hãy giảm số meter identity, tag combinations hoặc histogram buckets. Scrape interval chủ yếu điều khiển sample frequency và độ phân giải quan sát.

## 11. Phân bổ histogram theo giá trị vận hành

Histogram hữu ích khi cần percentile có thể tổng hợp giữa nhiều instance hoặc tỷ lệ đáp ứng SLO tại ngưỡng bucket. Nhưng mỗi bucket làm tăng series và chi phí cập nhật.

Nên ưu tiên histogram cho:

- HTTP endpoint quan trọng có latency SLO.
- Payment/provider calls ảnh hưởng trực tiếp đến giao dịch.
- Workflow nghiệp vụ mà p95/p99 hỗ trợ quyết định.
- Các thao tác có volume đủ lớn để percentile ổn định.

Cân nhắc không bật histogram cho:

- Meter chỉ phục vụ đếm tổng.
- Operation hiếm không có yêu cầu percentile.
- Metric có tag cardinality lớn.
- Mọi route động hoặc mọi tổ hợp tag mà không có câu hỏi vận hành cụ thể.

Chọn bucket quanh ngưỡng SLO và vùng phân bố cần quan sát. Bucket quá rộng làm percentile kém chính xác; quá nhiều bucket làm tăng series. SLO boundaries có thể bổ sung các ranh giới quan trọng, nhưng cũng làm tăng số bucket được export.

### Percentile phía ứng dụng và histogram

| Cách đo | Ưu điểm | Chi phí/giới hạn |
|---|---|---|
| `publishPercentiles(...)` | Xuất quantile được tính tại từng instance | Không thể tổng hợp quantile cục bộ thành quantile toàn service; có buffer tính toán |
| `publishPercentileHistogram()` | Backend có thể tổng hợp bucket giữa instance | Tăng số series theo bucket và tag combinations |
| SLO buckets | Có bucket đúng ngưỡng nghiệp vụ | Mỗi ranh giới bổ sung làm tăng series |

Không bật cả hai cách nếu không có nhu cầu. Chọn dựa trên câu hỏi dashboard và khả năng backend.

## 12. Giới hạn cardinality bằng MeterFilter

Có thể dùng `MeterFilter` để đặt giới hạn ở registry. Ví dụ cấu hình Spring:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsBudgetConfiguration {

    @Bean
    MeterFilter limitTotalMeters() {
        return MeterFilter.maximumAllowableMetrics(10_000);
    }

    @Bean
    MeterFilter limitHttpUriValues() {
        return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny()
        );
    }
}
```

Ví dụ giới hạn tổng số meter và giới hạn số giá trị tag `uri` cho HTTP request meter. Khi vượt giới hạn, meter mới có thể bị từ chối theo filter được cấu hình. Điều này bảo vệ registry nhưng có thể làm mất dữ liệu của meter mới; cần theo dõi log và kiểm tra backend để biết filter có kích hoạt hay không.

Các giới hạn này không thay thế việc thiết kế tag. Nếu mọi URL chứa ID, filter chỉ chặn sau khi đã chạm ngưỡng; dữ liệu vẫn bị mất và nguyên nhân cardinality chưa được sửa. Hãy chuẩn hóa route trước khi gắn tag.

Filter được áp dụng ở registry. Nếu ứng dụng có nhiều registry, hãy xác nhận cấu hình filter áp dụng cho từng registry mà ứng dụng sử dụng. Đồng thời kiểm tra tên meter canonical trước khi viết filter; tên sau khi export có thể khác tên Micrometer.

## 13. Chuẩn hóa tag ngay tại instrumentation

Cách tốt nhất là biến giá trị đầu vào thành nhóm hữu hạn trước khi gọi `tag()`.

```java
enum Channel {
    WEB,
    MOBILE,
    STORE,
    OTHER
}

static Channel normalizeChannel(String raw) {
    if (raw == null) {
        return Channel.OTHER;
    }

    switch (raw.toLowerCase(java.util.Locale.ROOT)) {
        case "web":
            return Channel.WEB;
        case "mobile":
            return Channel.MOBILE;
        case "store":
            return Channel.STORE;
        default:
            return Channel.OTHER;
    }
}
```

Sau đó chỉ dùng giá trị enum đã chuẩn hóa:

```java
registry.counter(
    "business.orders.paid",
    "channel",
    normalizeChannel(request.channel()).name().toLowerCase()
).increment();
```

Cách này bảo đảm mọi giá trị bất ngờ được gom vào `other`, thay vì tạo meter mới cho từng chuỗi. Chỉ dùng nhóm `other` khi việc gom nhóm vẫn có ý nghĩa; nếu cần điều tra giá trị gốc, ghi nó trong log có kiểm soát.

## 14. Đặt ngân sách theo cấp độ đo

Một cách thực tế là định nghĩa các tier instrumentation:

| Tier | Mục tiêu | Ví dụ cấu hình | Điều kiện bật |
|---|---|---|---|
| Tier 0 — Core | Luôn theo dõi sức khỏe và throughput | Counter, Gauge, Timer cơ bản, tag ít | Mặc định |
| Tier 1 — SLO | Theo dõi latency và tỷ lệ theo ngưỡng | Histogram/SLO buckets cho meter quan trọng | Khi có SLO/dashboard cần percentile |
| Tier 2 — Diagnostic | Điều tra một nhóm operation cụ thể | Thêm meter hoặc dimension hữu hạn | Có owner, thời hạn và budget |
| Tier 3 — Temporary | Phân tích sự cố ngắn hạn | Instrumentation thử nghiệm | Bật có kiểm soát, gỡ sau điều tra |

Không dùng sampling tùy tiện trên Counter nghiệp vụ nếu yêu cầu là đếm đầy đủ. Nếu muốn giảm chi phí metrics, hãy giảm số meter/tag/bucket hoặc tần suất scrape có cân nhắc. Trace sampling là cơ chế riêng và không thay thế ngân sách metrics.

Mỗi tier cần có tiêu chí promotion/demotion. Ví dụ, một Timer chỉ ở Tier 2 có thể được đưa lên Tier 1 khi nó trở thành một dependency quan trọng có SLO.

## 15. Ngưỡng ngân sách là ví dụ, phải được đo và hiệu chỉnh

Không có con số phù hợp cho mọi hệ thống. Có thể bắt đầu bằng một bảng mục tiêu nội bộ như sau rồi thay bằng dữ liệu thực tế:

| Tài nguyên | Ngưỡng ví dụ để bắt đầu | Cách xác minh |
|---|---|---|
| CPU overhead của instrumentation | Dưới 1% CPU tại workload mục tiêu | So sánh baseline và instrumented load test |
| Heap tăng thêm | Dưới 50 MiB sau warm-up | Heap histogram/JFR |
| Active series cho một service | Dưới 20.000 | Prometheus active series theo service |
| Series churn | Theo dõi series mới/phút; đặt giới hạn theo nền tảng | TSDB/cardinality report |
| Samples per second | Theo quota ingestion của backend | Scrape/ingestion metrics |
| Scrape payload | Dưới giới hạn timeout và response size của scraper | Kích thước exposition và scrape duration |

Các con số trên là ví dụ minh họa cho cách viết ngân sách, không phải khuyến nghị chung hoặc giới hạn của Micrometer. Một service nhiều replica hoặc nhiều endpoint có thể cần mức khác. Ngân sách phải được chấp thuận cùng nhóm vận hành nền tảng và kiểm chứng bằng benchmark.

Nên đặt cả ngưỡng cảnh báo và ngưỡng chặn:

- **Warning:** gần chạm ngân sách, yêu cầu owner đánh giá.
- **Limit:** giới hạn được cấu hình để bảo vệ registry/backend.
- **Review:** định kỳ xem lại meter không còn được dùng hoặc tag không còn giá trị.

Không đặt giới hạn quá thấp khiến meter quan trọng bị từ chối âm thầm. Cần có cảnh báo khi filter cap được kích hoạt và tài liệu hóa metric nào có thể bị mất.

## 16. Quy trình benchmark ngân sách

Một quy trình đánh giá có thể lặp lại sau mỗi thay đổi instrumentation:

1. **Chọn workload:** request mix, concurrency, payload và throughput gần production.
2. **Đo baseline:** CPU, heap, allocation rate, latency, throughput khi nhóm metric đang đánh giá chưa được bật.
3. **Bật Tier 0:** đo lại và ghi nhận delta.
4. **Bật từng nhóm:** HTTP Timer, business metrics, datasource, histogram; không bật tất cả cùng lúc.
5. **Tăng cardinality có kiểm soát:** thử số route/tag combinations dự kiến ở production.
6. **Đo scrape:** thời gian scrape, payload bytes, samples/s và lỗi scrape.
7. **Đo backend:** active series, churn, ingestion và storage.
8. **So sánh với budget:** xác định nhóm nào tiêu thụ phần lớn tài nguyên.
9. **Tối ưu:** bỏ tag thừa, chuẩn hóa giá trị, giảm bucket hoặc tắt histogram ít giá trị.
10. **Lặp lại:** kiểm tra lại latency và độ chính xác dashboard sau tối ưu.

Dùng cùng phiên bản JDK, Micrometer, registry và cấu hình khi so sánh. Nếu nâng cấp dependency, benchmark lại vì implementation và chi phí có thể thay đổi.

## 17. Kiểm tra chi phí và cardinality trong runtime

Ở phía ứng dụng, có thể duyệt số meter để kiểm tra registry inventory:

```java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Map;
import java.util.stream.Collectors;

void inspect(MeterRegistry registry) {
    long meterCount = registry.getMeters().size();

    Map<String, Long> metersByName = registry.getMeters().stream()
        .collect(Collectors.groupingBy(
            meter -> meter.getId().getName(),
            Collectors.counting()
        ));
}
```

Đoạn code cho biết số meter identity trong registry và số identity theo tên. Nó không cho biết trực tiếp số series Prometheus vì một meter histogram có thể export nhiều series.

Ở phía Prometheus, có thể xem số series theo service nếu nhãn `service` được export:

```promql
count({
  service="order-service"
})
```

Truy vấn này đếm series đang tồn tại trong phạm vi selector tại thời điểm truy vấn; nhãn và selector thực tế phụ thuộc relabeling/configuration. Có thể dùng cardinality/status APIs hoặc TSDB status của Prometheus để điều tra series và churn chi tiết hơn.

Kiểm tra endpoint `/actuator/prometheus` để xem tên và nhãn thực tế. Đừng dựa vào meter count của registry để kết luận backend chỉ có cùng số series.

## 18. Các lỗi thường gặp khi lập ngân sách

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ giới hạn số meter | Histogram vẫn tạo nhiều series trên mỗi meter | Tính bucket và tag combinations |
| Dùng URL động làm tag | Series tăng theo request hoặc entity ID | Dùng route template |
| Giảm scrape interval để xử lý cardinality | Active series vẫn giữ nguyên, độ phân giải giảm | Giảm tag combinations hoặc bucket |
| Bật histogram trên mọi Timer | Tăng series, heap và scrape payload | Chỉ bật cho meter có yêu cầu percentile/SLO |
| Dùng một budget cho toàn bộ module | Nhóm thiết yếu có thể bị nhóm diagnostics lấn chỗ | Phân bổ theo nhóm và mức ưu tiên |
| Ước lượng byte/meter cố định | Sai khác theo registry và cấu hình | Đo heap thực tế sau warm-up |
| Chỉ đo CPU ở local | Bỏ qua contention và scrape/export ở production | Benchmark với concurrency và registry thật |
| Không theo dõi series churn | Active series có vẻ ổn nhưng storage/index vẫn tăng | Theo dõi series mới và label churn |
| Filter deny meter mà không cảnh báo | Dashboard mất dữ liệu nhưng khó phát hiện | Theo dõi filter cap và ghi rõ meter bị từ chối |
| Không xem lại meter cũ | Ngân sách bị tiêu thụ bởi instrumentation không còn dùng | Inventory và review định kỳ |

## 19. Checklist trước khi phát hành instrumentation

- [ ] Mỗi nhóm meter có mục đích, owner và dashboard/alert rõ ràng.
- [ ] Đã tách budget CPU, heap, active series, ingestion và churn.
- [ ] Đã tính số tổ hợp tag bằng tích cardinality của từng key.
- [ ] Đã tính số bucket và series phụ của histogram.
- [ ] Đã nhân với số instance/replica và common labels phù hợp.
- [ ] Không dùng ID, URL động hoặc dữ liệu cá nhân làm metric tags.
- [ ] Histogram chỉ bật cho meter cần percentile hoặc SLO.
- [ ] Scrape interval được chọn theo độ phân giải và ingestion budget.
- [ ] MeterFilter có giới hạn bảo vệ nhưng không thay thế tag normalization.
- [ ] Đã benchmark CPU, heap, allocation và request latency.
- [ ] Đã kiểm tra scrape duration, payload, active series và churn.
- [ ] Đã xác nhận filter cap không từ chối meter thiết yếu.
- [ ] Có quy trình review và gỡ instrumentation tạm thời.
- [ ] Đã ghi lại budget và số liệu đo thực tế để so sánh sau nâng cấp.

Ngân sách instrumentation phải phản ánh chi phí trên cả JVM và metrics backend. Hãy tính số meter identity từ tag combinations, nhân thêm bucket của histogram, số instance và tần suất scrape để ước lượng series cùng ingestion. Sau đó benchmark CPU và heap trên workload đại diện, theo dõi active series và churn ở backend, rồi phân bổ giới hạn theo nhóm phép đo. Cách làm này giữ các metrics thiết yếu luôn sẵn có trong khi những phép đo đắt hơn chỉ được bật khi chúng trả lời một câu hỏi vận hành cụ thể.

## Tài liệu tham khảo

- [Micrometer Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — giới hạn meter, tag values và cấu hình registry.
- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html) — chi phí và cấu hình histogram/percentile.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — semantics và distribution statistics của Timer.
- [Prometheus Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/) — cardinality và thiết kế metric.
- [Prometheus Storage](https://prometheus.io/docs/prometheus/latest/storage/) — ingestion, retention và storage engine.

