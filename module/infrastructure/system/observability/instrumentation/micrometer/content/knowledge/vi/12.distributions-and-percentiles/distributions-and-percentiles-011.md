# Kiểm chứng phân phối bằng dữ liệu lệch và các giá trị ở phần đuôi

Số trung bình không mô tả đầy đủ một phân phối có đuôi dài. Trong ứng dụng Java, phần lớn request có thể hoàn tất nhanh nhưng một tỷ lệ nhỏ mất nhiều thời gian hơn hàng chục hoặc hàng trăm lần. Nếu chỉ nhìn mean, các trường hợp chậm hiếm gặp có thể bị che khuất; nếu chỉ nhìn maximum, một mẫu đơn lẻ lại có thể khiến đánh giá biến động quá mức.

Micrometer cung cấp histogram và percentile cho `Timer` hoặc `DistributionSummary` để quan sát hình dạng phân phối. Cách kiểm chứng tốt là dùng một tập dữ liệu có độ lệch được biết trước, tính các thống kê kỳ vọng, ghi cùng dữ liệu vào meter, rồi so sánh kết quả snapshot hoặc truy vấn backend. Cần phân biệt percentile tính trong từng JVM với histogram có thể tổng hợp giữa nhiều instance.

## Vì sao cần kiểm tra phần đuôi?

Phân phối thời gian xử lý hoặc kích thước dữ liệu thường không đối xứng. Phần lớn quan sát nằm ở vùng thấp, trong khi một số ít giá trị rất lớn kéo dài đuôi bên phải. Ví dụ, phần lớn request trả lời trong vài mili giây nhưng một số request phải chờ database, retry dịch vụ phụ thuộc hoặc xử lý payload lớn.

Các thống kê thường trả lời những câu hỏi khác nhau:

| Thống kê | Câu hỏi | Giới hạn khi dùng riêng lẻ |
|---|---|---|
| Mean (trung bình) | Tổng lượng chia cho số quan sát là bao nhiêu? | Bị kéo lên bởi giá trị cực lớn và không cho biết mức điển hình |
| Median (p50) | Một nửa quan sát nằm ở dưới mức nào? | Không thể hiện mức chậm của nhóm nhỏ ở phần đuôi |
| p90 / p95 | 90% / 95% quan sát không vượt quá mức nào? | Có thể bỏ qua nhóm rất nhỏ nhưng rất chậm |
| p99 / p99.9 | Phần lớn gần như toàn bộ quan sát không vượt quá mức nào? | Cần đủ số mẫu và độ phân giải histogram phù hợp |
| Max | Quan sát lớn nhất là bao nhiêu? | Rất nhạy với một mẫu bất thường và không thể hiện tần suất |

Đừng xem p99 là thời gian của request chậm nhất. Nếu p99 là 500 ms, điều đó có nghĩa khoảng 99% quan sát không vượt quá mức xấp xỉ đó trong tập dữ liệu và cửa sổ được xét; phần còn lại có thể cao hơn đáng kể.

## Tạo bộ dữ liệu lệch có kết quả kỳ vọng

Một bộ dữ liệu tổng hợp có cấu trúc rõ ràng giúp kiểm chứng mà không phụ thuộc vào tải ngẫu nhiên. Xét 1.000 lần xử lý:

- 900 lần mất 10 ms.
- 80 lần mất 50 ms.
- 20 lần mất 2.000 ms.

Sắp xếp tăng dần, các vị trí p50, p90, p95 và p99 cho kết quả kỳ vọng theo nearest-rank như sau:

| Thống kê | Giá trị kỳ vọng | Diễn giải |
|---|---:|---|
| p50 | 10 ms | Phần lớn request rất nhanh |
| p90 | 10 ms | 90% request không vượt quá 10 ms |
| p95 | 50 ms | Mốc p95 nằm trong nhóm quan sát 50 ms; khoảng 2% mẫu nằm cao hơn |
| p99 | 2.000 ms | Nhóm 2% chậm đã đi vào phần đuôi |
| Max | 2.000 ms | Giá trị lớn nhất trong tập |
| Mean | 53 ms | Tổng thời gian 53.000 ms chia cho 1.000 lần |

Với định nghĩa nearest-rank, percentile (p) lấy phần tử ở vị trí ⌈p \times n⌉ trong dãy đã sắp xếp. Các thư viện và hệ thống có thể dùng cách nội suy hoặc thuật toán ước lượng khác, nên percentile từ histogram có thể không bằng chính xác giá trị trong bảng. Dữ liệu này chủ yếu giúp xác nhận rằng p50 thấp, p95 cao hơn và p99 thể hiện được nhóm chậm ở đuôi.

Mean 53 ms lớn hơn nhiều median 10 ms vì 20 lần xử lý 2 giây đóng góp 40.000 ms vào tổng thời gian. Nếu chỉ báo cáo median, nhóm chậm gần như biến mất; nếu chỉ báo cáo mean, người đọc không biết phần lớn request vẫn hoàn tất trong 10 ms.

## Ghi nhận phân phối bằng Timer

`Timer` phù hợp với thời lượng. Có thể yêu cầu Micrometer xuất percentile tính trong tiến trình bằng `publishPercentiles(...)`, histogram bucket bằng `publishPercentileHistogram()`, hoặc cả hai nếu có nhu cầu rõ ràng:

```java
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class RequestMetrics {
    private final Timer requestDuration;

    public RequestMetrics(MeterRegistry registry) {
        this.requestDuration = Timer.builder("http.server.request.duration")
                .description("Thời gian xử lý HTTP request")
                .publishPercentiles(0.50, 0.90, 0.95, 0.99)
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(2))
                .register(registry);
    }

    public void record(Duration duration) {
        requestDuration.record(duration);
    }
}
```

Các percentile truyền vào nằm trong khoảng từ 0 đến 1: `0.99` là p99. `serviceLevelObjectives(...)` thêm các ranh giới quan trọng để kiểm tra ngưỡng cụ thể. Histogram hỗ trợ backend tính percentile từ dữ liệu gộp; percentile phía client cung cấp góc nhìn từng meter tại từng tiến trình. Cấu hình nhiều bucket và nhiều tổ hợp tag làm tăng số chuỗi, nên chỉ bật các thống kê thực sự cần.

Để đo một đoạn code trực tiếp, dùng `Timer.record(...)` hoặc `Timer.Sample`. Ví dụ:

```java
requestDuration.record(() -> controller.handle(request));
```

Nếu cần chọn tag theo kết quả sau khi thao tác hoàn tất, dùng `Timer.Sample` rồi dừng vào timer có tag `outcome` phù hợp. Không đưa request ID hoặc URL chứa mã tài nguyên vào tag khi phân tích phần đuôi.

## Ghi nhận phân phối không phải thời gian

`DistributionSummary` dùng cho các giá trị như payload size, số bản ghi trong batch hoặc số byte đọc. Cách cấu hình percentile và histogram tương tự `Timer`, nhưng giá trị phải được chuẩn hóa về cùng một đơn vị:

```java
DistributionSummary payloadSize = DistributionSummary.builder("http.request.payload.size")
        .baseUnit("bytes")
        .publishPercentiles(0.50, 0.95, 0.99)
        .publishPercentileHistogram()
        .serviceLevelObjectives(1_024, 10_240, 102_400)
        .register(registry);

payloadSize.record(requestBody.length);
```

Trong ví dụ, `requestBody.length` và các SLO đều dùng byte. Nếu có nguồn dữ liệu báo KiB hoặc MiB, chuyển đổi trước khi ghi nhận. Không ghi byte và số bản ghi vào cùng một summary chỉ vì cả hai đều là số.

Đối với payload có đuôi dài, p99 có thể giúp phát hiện một nhóm request rất lớn gây áp lực bộ nhớ hoặc mạng. Tuy nhiên, percentile không thay thế giới hạn kích thước tối đa; hãy theo dõi thêm số lần vượt giới hạn bằng bucket SLO hoặc metric đếm riêng.

## Kiểm chứng dữ liệu bằng HistogramSnapshot

Với percentile phía client, `takeSnapshot()` cho phép kiểm tra các percentile mà meter đang công bố. Ví dụ sau ghi tập dữ liệu lệch ở trên vào một timer:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.HistogramSnapshot;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.distribution.ValueAtPercentile;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
Timer timer = Timer.builder("test.request.duration")
        .publishPercentiles(0.50, 0.90, 0.95, 0.99)
        .register(registry);

for (int i = 0; i < 900; i++) {
    timer.record(10, TimeUnit.MILLISECONDS);
}
for (int i = 0; i < 80; i++) {
    timer.record(50, TimeUnit.MILLISECONDS);
}
for (int i = 0; i < 20; i++) {
    timer.record(2_000, TimeUnit.MILLISECONDS);
}

HistogramSnapshot snapshot = timer.takeSnapshot();
assertThat(snapshot.count()).isEqualTo(1_000);
assertThat(snapshot.total(TimeUnit.MILLISECONDS)).isEqualTo(53_000);

for (ValueAtPercentile value : snapshot.percentileValues()) {
    System.out.printf("p%.0f = %.2f ms%n",
            value.percentile() * 100,
            value.value(TimeUnit.MILLISECONDS));
}

registry.close();
```

Kiểm tra `count` và `total` giúp xác nhận toàn bộ mẫu đã được ghi nhận. Các giá trị percentile trong snapshot là ước lượng theo cấu hình histogram và implementation của registry; không nên kiểm thử bằng cách yêu cầu mọi backend trả đúng từng mili giây như dữ liệu gốc. Thay vào đó, xác nhận percentile có đủ, thứ tự hợp lý và p99 thể hiện nhóm chậm.

Ví dụ assertion định hướng có thể là:

```java
ValueAtPercentile p50 = findPercentile(snapshot, 0.50);
ValueAtPercentile p95 = findPercentile(snapshot, 0.95);
ValueAtPercentile p99 = findPercentile(snapshot, 0.99);

assertThat(p50.value(TimeUnit.MILLISECONDS)).isLessThan(50);
assertThat(p95.value(TimeUnit.MILLISECONDS)).isGreaterThanOrEqualTo(10);
assertThat(p99.value(TimeUnit.MILLISECONDS)).isGreaterThan(p95.value(TimeUnit.MILLISECONDS));
```

`findPercentile(...)` là helper của test để tìm phần tử có percentile tương ứng trong `snapshot.percentileValues()`. Cần viết helper theo cách so sánh có tolerance phù hợp với cấu hình histogram. Nếu dùng `SimpleMeterRegistry` chỉ để kiểm tra count và total, hãy kiểm tra histogram ở registry/backend đích trong integration test riêng.

## Percentile phía client và histogram có thể tổng hợp

Đây là khác biệt quan trọng khi một dịch vụ chạy nhiều instance:

- **Percentile phía client:** Micrometer tính p50, p95 hoặc p99 trong từng JVM và xuất các giá trị đó. Các percentile của từng instance không thể cộng hoặc lấy trung bình để tạo percentile toàn dịch vụ.
- **Histogram bucket:** mỗi instance xuất số đếm theo cùng các ranh giới bucket. Backend có thể cộng các bucket tương ứng rồi tính percentile trên phân phối đã gộp.

Ví dụ instance A xử lý 10.000 request nhanh và instance B xử lý 100 request chậm. p95 của từng instance không thể được lấy trung bình không trọng số để thành p95 toàn cụm. Ngay cả trung bình có trọng số của percentile cũng không tái tạo được percentile của hợp phân phối. Cần dữ liệu histogram có thể gộp hoặc dữ liệu mẫu gốc để tính percentile tổng thể.

Nếu dùng Prometheus classic histogram, truy vấn p99 theo dịch vụ có dạng:

```promql
histogram_quantile(
  0.99,
  sum by (le, service) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
```

Truy vấn tính tốc độ tăng từng bucket trên cửa sổ 5 phút, cộng các instance theo `service`, sau đó ước lượng p99 từ phân phối đã gộp. Tên metric minh họa phụ thuộc tên meter, đơn vị và quy tắc chuẩn hóa của Prometheus registry; cần đối chiếu endpoint exposition thực tế.

## Đo tỷ lệ quan sát nằm trong phần đuôi

Percentile trả lời một ranh giới của phân phối. Một câu hỏi bổ sung thường hữu ích là có bao nhiêu phần trăm request vượt quá một ngưỡng cụ thể, chẳng hạn 1 giây. Với histogram có bucket `le="1.0"` và tổng `_count`, tỷ lệ vượt quá 1 giây có thể tính như sau:

```promql
1 - (
  sum by (service) (
    rate(http_server_request_duration_seconds_bucket{le="1.0"}[5m])
  )
  /
  sum by (service) (
    rate(http_server_request_duration_seconds_count[5m])
  )
)
```

Bucket `le="1.0"` chứa các quan sát nhỏ hơn hoặc bằng 1 giây. Lấy một trừ tỷ lệ trong bucket sẽ cho tỷ lệ quan sát lớn hơn 1 giây. Kết quả nằm trong khoảng 0 đến 1 khi có mẫu hợp lệ; nhân 100 để hiển thị phần trăm. Nếu không có request trong cửa sổ, mẫu số bằng không hoặc chuỗi không tồn tại; dashboard và alert cần xử lý trường hợp thiếu dữ liệu riêng.

Đối với payload, có thể dùng cách tương tự với bucket byte để biết tỷ lệ request có kích thước vượt 100 KiB. Đây thường là tín hiệu dễ hành động hơn một percentile đơn lẻ khi mục tiêu vận hành là giới hạn kích thước.

## Kiểm tra chất lượng dữ liệu phần đuôi

Một percentile chỉ có ý nghĩa khi có đủ quan sát trong cửa sổ. Nếu chỉ có 20 request, p99 gần như đại diện cho vùng cực trị và dễ thay đổi mạnh khi thêm một mẫu. Khi lưu lượng thấp, hãy xem cả số mẫu, thời gian cửa sổ và độ ổn định của xu hướng.

Các điểm cần kiểm tra:

1. **Độ lệch:** mean lớn hơn nhiều median có thể là dấu hiệu phân phối lệch phải; xác nhận bằng p90, p95 và p99.
2. **Độ dài đuôi:** khoảng cách giữa p95 và p99 cho biết phần đuôi tăng nhanh đến mức nào.
3. **Tần suất vượt ngưỡng:** tính tỷ lệ request vượt một ranh giới vận hành cụ thể.
4. **Số mẫu:** xem count hoặc tốc độ request để biết percentile có đủ dữ liệu.
5. **Phân nhóm:** phân tích theo route template, method hoặc region có tập giá trị hữu hạn để tìm nhóm gây tail latency.
6. **Thời điểm:** so sánh nhiều cửa sổ và phiên bản để xác định tail tăng do tải, triển khai hay dependency.

Không phân nhóm theo request ID, user ID hoặc URL đầy đủ để tìm tail. Dùng trace và log có ID tương quan để điều tra từng request; metric chỉ nên giữ chiều phân tích có cardinality thấp.

## Những cách đọc sai thường gặp

| Cách đọc sai | Vì sao sai | Cách diễn giải phù hợp |
|---|---|---|
| Mean thấp nghĩa là không có request chậm | Nhóm nhỏ ở đuôi có thể bị mean che khuất | Xem thêm p95, p99 và tỷ lệ vượt ngưỡng |
| p99 là request chậm nhất | Khoảng 1% quan sát nằm phía trên p99 | Dùng max để xem cực trị, kết hợp tỷ lệ tail để biết tần suất |
| Lấy trung bình p99 của các instance | Percentile không có tính cộng gộp | Gộp histogram bucket rồi tính quantile ở backend |
| p99 tăng nghĩa mọi request đều chậm | Chỉ phần đuôi có thể tăng | So sánh p50, p95, p99 và count |
| p99 ổn định khi lưu lượng rất thấp | Ít mẫu làm percentile biến động hoặc mất ý nghĩa | Áp dụng điều kiện số mẫu tối thiểu và xem cửa sổ dài hơn |
| Bật histogram không có chi phí | Mỗi bucket nhân theo tag và instance | Giới hạn bucket và tag theo nhu cầu thực tế |

## Checklist kiểm chứng

- [ ] Có bộ dữ liệu lệch với các giá trị phần đuôi đã biết trước.
- [ ] Đã tính count, total và mean kỳ vọng từ dữ liệu gốc.
- [ ] Đã so sánh median, p90, p95, p99 và max thay vì chỉ xem mean.
- [ ] Percentile được cấu hình đúng trong `publishPercentiles(...)` nếu cần số đo phía client.
- [ ] Histogram được bật nếu cần tổng hợp percentile giữa nhiều instance.
- [ ] Đã kiểm tra bucket hoặc snapshot thực tế, có tolerance phù hợp với thuật toán ước lượng.
- [ ] Đã xác minh đơn vị của Timer hoặc DistributionSummary trước khi diễn giải giá trị.
- [ ] Truy vấn tail dùng cùng cửa sổ và cùng tập metric ở tử số, mẫu số.
- [ ] Đã xử lý trường hợp thiếu dữ liệu hoặc số mẫu quá thấp.
- [ ] Tag dùng để phân nhóm có cardinality thấp; trace/log được dùng cho điều tra từng request.

Kiểm chứng phân phối cần nhìn cả vùng điển hình lẫn phần đuôi. Một bộ dữ liệu lệch có kết quả kỳ vọng giúp xác nhận instrumentation và truy vấn có phát hiện được nhóm chậm; histogram cho phép gộp dữ liệu nhiều instance, còn percentile phía client phù hợp để quan sát từng tiến trình. Khi kết hợp p50, p95, p99, max, số mẫu và tỷ lệ vượt ngưỡng, dashboard sẽ mô tả tail rõ ràng hơn nhiều so với một giá trị trung bình duy nhất.
