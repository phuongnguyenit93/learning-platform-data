# Đặt ngưỡng serviceLevelObjectives cho đại lượng đã được chuẩn hóa

`DistributionSummary` dùng để ghi nhận phân phối của những đại lượng dạng số không phải thời gian, chẳng hạn kích thước payload, số bản ghi trong một batch, số byte đọc hoặc dung lượng tệp. Khi cần biết bao nhiêu quan sát nằm dưới một ngưỡng vận hành, có thể cấu hình các ranh giới bằng `serviceLevelObjectives(...)`.

Điều kiện quan trọng là mọi giá trị được ghi nhận và mọi ngưỡng phải dùng cùng một đơn vị chuẩn. Ví dụ, nếu kích thước payload được chuẩn hóa về byte, hãy ghi mọi payload bằng byte và đặt ngưỡng SLO cũng bằng byte. Việc cấu hình ranh giới chỉ giúp registry xuất các bucket cần thiết; tỷ lệ mục tiêu như 99% quan sát dưới 10 KiB vẫn phải được tính và đánh giá ở hệ thống giám sát.

## Chọn đại lượng và đơn vị chuẩn

Trước khi đặt ngưỡng, xác định chính xác đại lượng mà summary đại diện. Một metric chỉ nên chứa một loại đại lượng có cùng ý nghĩa và cùng đơn vị.

| Đại lượng | Đơn vị chuẩn gợi ý | Ví dụ ngưỡng |
|---|---|---|
| Kích thước HTTP payload | byte | 1 KiB, 10 KiB, 100 KiB |
| Kích thước tệp | byte | 1 MiB, 10 MiB, 100 MiB |
| Số bản ghi trong batch | record | 100, 500, 1.000 record |
| Số phần tử trong một trang kết quả | item | 10, 25, 50 item |
| Số byte đọc hoặc ghi | byte | 4 KiB, 64 KiB, 1 MiB |

Không ghi một số đo bằng KiB rồi ghi số đo tiếp theo bằng byte vào cùng một summary. Backend sẽ coi chúng là cùng một thang đo và kết quả phân phối không còn ý nghĩa. Cũng không dùng `DistributionSummary` để đo thời gian; thời lượng thuộc về `Timer`.

Ví dụ, Java `byte[].length` và `Files.size(path)` trả về kích thước theo byte. Nếu đầu vào đến từ một API báo kích thước theo KiB, hãy chuyển đổi trước khi gọi `record(...)`:

```java
private static final double BYTES_PER_KIB = 1024.0;

double sizeInKiB = request.payloadSizeKiB();
double sizeInBytes = sizeInKiB * BYTES_PER_KIB;
payloadSummary.record(sizeInBytes);
```

Phân biệt KiB với kB và MiB với MB khi thiết kế ngưỡng. Theo quy ước nhị phân, 1 KiB = 1.024 byte và 1 MiB = 1.024 KiB. Nếu hệ thống nghiệp vụ dùng đơn vị thập phân, hãy dùng đúng hệ số đó và thể hiện rõ trong tên hoặc mô tả metric.

## Đăng ký DistributionSummary với SLO boundaries

Micrometer cho phép cấu hình các ranh giới SLO bằng `serviceLevelObjectives(...)`. Với payload, có thể chuẩn hóa về byte và đặt các ranh giới 1 KiB, 10 KiB và 100 KiB:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {
    private static final double BYTES_PER_KIB = 1024.0;

    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary.builder("http.request.payload.size")
                .description("Kích thước HTTP request payload")
                .baseUnit("bytes")
                .serviceLevelObjectives(
                        1 * BYTES_PER_KIB,
                        10 * BYTES_PER_KIB,
                        100 * BYTES_PER_KIB)
                .register(registry);
    }

    public void record(byte[] body) {
        payloadSize.record(body.length);
    }
}
```

`baseUnit("bytes")` mô tả đơn vị của metric cho registry và hệ thống nhận. Nó không tự chuyển đổi giá trị truyền vào `record(...)`; code vẫn phải ghi số byte. Các ngưỡng trong `serviceLevelObjectives(...)` cũng được hiểu theo chính thang giá trị đó.

Sau khi đăng ký, mỗi lần gọi `record(...)` thêm một quan sát vào phân phối. `count()` cho biết số quan sát đã ghi nhận, `totalAmount()` cho biết tổng các giá trị và `max()` cho biết giá trị lớn nhất được giữ theo cơ chế thống kê của registry. Các phép đo này không tự phân loại dữ liệu thành các nhóm nghiệp vụ; bucket SLO cung cấp ranh giới để backend đếm số quan sát nằm trong từng khoảng.

## SLO boundary không phải tỷ lệ mục tiêu

Tên `serviceLevelObjectives(...)` dễ khiến người đọc nghĩ rằng chỉ cần truyền ngưỡng là đã định nghĩa xong SLO. Thực tế, danh sách truyền vào là các ranh giới phân phối cần xuất, không phải phần trăm mục tiêu và cũng không tự tạo cảnh báo.

Ví dụ:

```java
.serviceLevelObjectives(1_024, 10_240, 102_400)
```

Đoạn cấu hình tạo các ranh giới tương ứng 1 KiB, 10 KiB và 100 KiB khi giá trị được ghi bằng byte. Nó không có nghĩa 99% payload phải nhỏ hơn 10 KiB. Mục tiêu 99% là chính sách vận hành cần được đánh giá bằng tỷ lệ quan sát đạt ngưỡng trong một cửa sổ thời gian.

Một định nghĩa có thể kiểm chứng cần nêu cả hai phần:

- **Ranh giới đo:** ví dụ payload không vượt quá 10 KiB, tương đương 10.240 byte.
- **Mục tiêu dịch vụ:** ví dụ ít nhất 99% request trong cửa sổ 5 phút có payload không vượt quá ranh giới đó.

Ranh giới được cấu hình ở instrumentation; tỷ lệ và cửa sổ đánh giá được cấu hình trong truy vấn, dashboard hoặc hệ thống cảnh báo.

## Cách đọc bucket SLO

Với histogram kiểu Prometheus, bucket có nhãn `le` biểu diễn giới hạn trên. Bucket là bucket tích lũy: bucket `le="10240"` bao gồm tất cả quan sát có giá trị nhỏ hơn hoặc bằng 10.240 byte, kể cả những quan sát đã nằm trong các bucket nhỏ hơn.

Giả sử trong một khoảng thời gian có 10.000 payload được ghi nhận và 9.850 payload không vượt quá 10 KiB. Tỷ lệ đạt ngưỡng là:

\[
\frac{9.850}{10.000} = 0{,}985 = 98{,}5\%
\]

Nếu mục tiêu là 99%, tỷ lệ 98,5% trong cửa sổ đó chưa đạt mục tiêu. Chỉ nhìn số lượng bucket mà không chia cho tổng số quan sát sẽ không cho biết tỷ lệ đạt ngưỡng khi lưu lượng thay đổi.

Với tên metric minh họa được Prometheus chuẩn hóa thành `http_request_payload_size_bytes`, có thể tính tỷ lệ payload không vượt quá 10 KiB như sau:

```promql
sum by (service) (
  rate(http_request_payload_size_bytes_bucket{le="10240"}[5m])
)
/
sum by (service) (
  rate(http_request_payload_size_bytes_count[5m])
)
```

Truy vấn lấy tốc độ tăng của bucket 10 KiB chia cho tốc độ tăng tổng số quan sát trong cùng cửa sổ 5 phút. Kết quả là tỷ lệ từ 0 đến 1; nhân 100 nếu dashboard muốn hiển thị phần trăm. Tên metric và cách biểu diễn chuỗi `le` phụ thuộc Prometheus registry cùng quy tắc chuẩn hóa tên. Hãy kiểm tra endpoint exposition thực tế và thay tên hoặc giá trị `le` nếu registry xuất khác.

Nếu muốn kiểm tra mục tiêu 99%, có thể tạo điều kiện cảnh báo khi tỷ lệ nhỏ hơn `0.99` trong thời gian đủ dài để tránh phản ứng với một vài mẫu biến động. Cần kết hợp chính sách lưu lượng tối thiểu: khi không có request, mẫu số bằng không hoặc không có chuỗi, nên không diễn giải trường hợp đó thành tỷ lệ đạt 0%.

## Chọn các ngưỡng có ý nghĩa vận hành

Các ranh giới nên xuất phát từ quyết định mà đội vận hành cần đưa ra. Không nên chọn một dãy số tùy ý chỉ để biểu đồ có nhiều cột. Với payload HTTP, có thể đặt ngưỡng để phân biệt request nhỏ, thông thường và lớn:

| Ranh giới | Giá trị theo byte | Câu hỏi vận hành |
|---|---:|---|
| 1 KiB | 1.024 | Bao nhiêu payload rất nhỏ? |
| 10 KiB | 10.240 | Bao nhiêu payload nằm trong kích thước thông thường? |
| 100 KiB | 102.400 | Bao nhiêu payload vượt mức thông thường? |
| 1 MiB | 1.048.576 | Bao nhiêu payload lớn có thể tạo áp lực bộ nhớ hoặc mạng? |

Nếu ứng dụng có giới hạn request body 256 KiB, có thể thêm ranh giới tại 256 KiB để đo trực tiếp số quan sát chạm hoặc vượt giới hạn đó. Tuy nhiên, bucket `le` đếm giá trị nhỏ hơn hoặc bằng ngưỡng; để đếm giá trị lớn hơn ngưỡng, cần lấy tổng quan sát trừ bucket tương ứng hoặc dùng bucket cao hơn cùng logic truy vấn phù hợp.

Các ranh giới cần bao phủ vùng dữ liệu mà dashboard và cảnh báo sử dụng. Nếu tất cả payload đều nhỏ hơn 1 KiB, những bucket từ 100 KiB trở lên không giúp nhiều cho việc phân tích chi tiết. Nếu payload có thể lên đến hàng chục MiB, chỉ đặt ngưỡng tối đa 100 KiB sẽ không giúp phân biệt vùng kích thước lớn.

## Chuẩn hóa trước khi ghi nhận

Việc chuẩn hóa nên diễn ra tại ranh giới nhận dữ liệu, trước khi gọi `record(...)`. Không nên phụ thuộc vào định dạng đầu vào của từng client.

```java
public void recordUpload(long size, SizeUnit unit) {
    if (size < 0) {
        throw new IllegalArgumentException("Kích thước không được âm");
    }

    long sizeInBytes = switch (unit) {
        case BYTE -> size;
        case KIBIBYTE -> Math.multiplyExact(size, 1_024L);
        case MEBIBYTE -> Math.multiplyExact(size, 1_048_576L);
    };

    uploadSizeBytes.record(sizeInBytes);
}

enum SizeUnit {
    BYTE,
    KIBIBYTE,
    MEBIBYTE
}
```

`Math.multiplyExact(...)` phát hiện tràn số khi chuyển đổi số nguyên. Nếu đầu vào có thể là số thập phân, dùng phép tính `double` có kiểm soát và xác thực miền giá trị trước khi ghi nhận. Không âm thầm đổi đơn vị theo phỏng đoán từ tên trường hoặc định dạng chuỗi.

Với batch size, đơn vị chuẩn có thể là `records` thay vì byte. Hãy dùng một metric khác cho số bản ghi và không tái sử dụng `upload.size` để ghi cả byte lẫn record. Tên, mô tả và base unit nên giúp người đọc hiểu đại lượng mà không phải suy đoán.

## Kết hợp SLO buckets với thống kê phân phối

SLO boundaries hữu ích khi có một số ngưỡng cụ thể cần đếm. Nếu cần phân tích phân phối rộng hơn hoặc ước lượng percentile, có thể cân nhắc bật percentile histogram:

```java
DistributionSummary summary = DistributionSummary.builder("batch.size")
        .baseUnit("records")
        .serviceLevelObjectives(100, 500, 1_000, 5_000)
        .publishPercentileHistogram()
        .register(registry);
```

`serviceLevelObjectives(...)` bổ sung các ranh giới quan trọng cho mục tiêu vận hành. `publishPercentileHistogram()` yêu cầu xuất histogram có các bucket phù hợp để backend ước lượng percentile. Hai cấu hình phục vụ mục đích liên quan nhưng khác nhau: SLO boundaries bảo đảm các ngưỡng được quan sát; histogram percentile hỗ trợ phân tích phân phối rộng hơn. Chúng có thể làm tăng số chuỗi thời gian, nên chỉ bật khi dashboard hoặc cảnh báo thực sự cần.

Percentile tính tại client và percentile tính từ histogram ở backend cũng có đặc tính khác nhau. Giá trị percentile được tính riêng ở từng JVM không thể cộng hoặc lấy trung bình để thành percentile toàn dịch vụ. Histogram bucket có thể được gộp giữa các instance nếu cùng cấu hình và backend hỗ trợ phép tổng hợp.

## Cardinality và chi phí của bucket

Mỗi tổ hợp tên metric và tag tạo một meter trong registry. Khi summary xuất histogram, mỗi bucket có thể tạo thêm một chuỗi ở backend cho mỗi tổ hợp tag và mỗi instance. Vì vậy số chuỗi tăng theo số ranh giới, số tổ hợp tag và số instance.

Ví dụ, một summary có 5 ranh giới SLO và 4 tổ hợp tag được xuất từ 6 instance có thể tạo tối thiểu khoảng:

\[
5 \times 4 \times 6 = 120\text{ chuỗi bucket}
\]

Con số thực tế có thể cao hơn vì registry còn xuất bucket `+Inf`, `_count`, `_sum`, các bucket histogram bổ sung và các measurement khác. Tên metric, cách xuất và filter của backend cũng ảnh hưởng kết quả.

Tag như `endpoint`, `region` hoặc `content_type` chỉ nên dùng khi tập giá trị được kiểm soát. Không dùng `fileName`, `userId`, `requestId` hoặc ID tài nguyên làm tag. Các giá trị đó có thể tạo số tổ hợp rất lớn và làm chi phí ingest tăng nhanh.

## Kiểm thử ngưỡng SLO

Có thể kiểm tra phần ghi nhận bằng `SimpleMeterRegistry`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PayloadMetricsTest {
    @Test
    void recordsNormalizedPayloadSizes() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DistributionSummary summary = DistributionSummary.builder("test.payload.size")
                .baseUnit("bytes")
                .serviceLevelObjectives(1_024, 10_240, 102_400)
                .register(registry);

        summary.record(512);
        summary.record(8_192);
        summary.record(20_000);

        assertThat(summary.count()).isEqualTo(3);
        assertThat(summary.totalAmount()).isEqualTo(28_704);
        assertThat(summary.max()).isEqualTo(20_000);

        registry.close();
    }
}
```

Test này xác nhận ba giá trị đều được ghi theo byte và tổng số cùng tổng lượng đúng. `SimpleMeterRegistry` hữu ích để kiểm tra API instrumentation, nhưng không chứng minh Prometheus đã xuất đúng bucket. Để kiểm tra SLO bucket thực tế, cần dùng registry/backend tương ứng và xác nhận exposition có các ranh giới đã cấu hình.

Khi kiểm thử chuyển đổi đơn vị, thêm các trường hợp ở đúng ranh giới và hai phía của ranh giới, ví dụ 10.239 byte, 10.240 byte và 10.241 byte. Điều này giúp phát hiện lỗi chuyển đổi hoặc sai đơn vị. Với query SLO, kiểm tra cả mẫu số bằng không và trường hợp không có dữ liệu.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Tỷ lệ dưới ngưỡng gần 0% dù payload nhỏ | Ghi giá trị bằng byte nhưng đặt SLO bằng KiB | Chuẩn hóa cả giá trị và ranh giới về cùng đơn vị |
| Bucket không xuất hiện | Registry/exporter không xuất histogram hoặc cấu hình chưa được áp dụng | Kiểm tra exposition và khả năng hỗ trợ histogram của registry |
| SLO đạt 100% nhưng vẫn có payload quá lớn | Ngưỡng được chọn quá cao hoặc query lọc sai metric/tag | Đối chiếu phân phối thực tế và kiểm tra label `le` |
| Tỷ lệ SLO nhảy mạnh khi lưu lượng thấp | Mẫu số nhỏ trong cửa sổ ngắn | Dùng cửa sổ phù hợp và điều kiện lưu lượng tối thiểu |
| Cardinality tăng sau khi bật histogram | Quá nhiều bucket, tag hoặc instance | Chỉ giữ ngưỡng có ý nghĩa và giới hạn tag |
| Dashboard hiển thị đơn vị sai | Nhầm base unit với chuyển đổi tự động | Xác nhận giá trị ghi nhận, base unit và quy tắc chuẩn hóa của backend |

## Checklist triển khai

- [ ] Metric chỉ đại diện cho một đại lượng có ý nghĩa rõ ràng.
- [ ] Giá trị ghi nhận được chuẩn hóa về một đơn vị duy nhất.
- [ ] `baseUnit` mô tả đúng đơn vị và code không dựa vào nó để tự chuyển đổi dữ liệu.
- [ ] Các ngưỡng `serviceLevelObjectives(...)` dùng cùng đơn vị với giá trị ghi nhận.
- [ ] Đã phân biệt SLO boundary với tỷ lệ mục tiêu và quy tắc cảnh báo.
- [ ] Query tính số quan sát đạt ngưỡng chia cho tổng số quan sát trong cùng cửa sổ.
- [ ] Đã xử lý trường hợp không có mẫu hoặc lưu lượng quá thấp.
- [ ] Đã xác minh bucket tại endpoint exposition của registry thực tế.
- [ ] Số bucket và tag được giữ ở mức cần thiết để kiểm soát cardinality.
- [ ] Unit test xác nhận giá trị, count, total và các trường hợp sát ranh giới.

`serviceLevelObjectives(...)` giúp `DistributionSummary` xuất các bucket theo những ranh giới vận hành đã chọn. Để kết quả đáng tin cậy, hãy chuẩn hóa đại lượng trước khi ghi nhận, đặt ngưỡng cùng đơn vị, rồi tính tỷ lệ đạt mục tiêu từ bucket và tổng số quan sát ở backend. Ranh giới tốt phải gắn với quyết định vận hành và đủ ít để cardinality luôn được kiểm soát.
