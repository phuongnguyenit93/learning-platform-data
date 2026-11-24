# Chọn baseUnit và hệ số scale phù hợp với miền giá trị

Khi dùng `DistributionSummary`, cần xác định rõ đơn vị của giá trị đầu vào và đơn vị mà hệ thống muốn lưu, phân tích, công bố. Micrometer cung cấp hai thiết lập có vai trò khác nhau: `baseUnit` mô tả đơn vị của phép đo; `scale` nhân giá trị được ghi nhận với một hệ số trước khi lưu vào summary. Chọn đúng cả hai giúp count, tổng, max, histogram và percentile có cùng ý nghĩa.

Ví dụ, một ứng dụng nhận kích thước payload theo KiB nhưng muốn metrics biểu diễn bằng byte. Có thể đặt `baseUnit("bytes")` và `scale(1024.0)`. Khi ứng dụng gọi `record(1.5)`, summary ghi nhận 1536 byte. `baseUnit` tự nó không chuyển đổi số liệu; phép nhân do `scale` thực hiện.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `DistributionSummary` phù hợp để quan sát phân phối của đại lượng số như kích thước payload, số phần tử trong batch hoặc kích thước thông điệp. Bài này tập trung vào việc chọn đơn vị chuẩn và chuyển đổi giá trị sao cho các số đo được diễn giải đúng ở registry và backend.

## 1. Phân biệt baseUnit và scale

Hai thiết lập thường được dùng cùng nhau nhưng giải quyết hai vấn đề khác nhau:

| Thiết lập | Vai trò | Có thay đổi giá trị ghi nhận không? |
| --- | --- | --- |
| `baseUnit` | Mô tả đơn vị của đại lượng mà summary biểu diễn | Không. Đây là metadata của meter |
| `scale` | Nhân từng giá trị đầu vào trước khi ghi nhận | Có. Count không đổi, nhưng tổng, max và phân phối dựa trên giá trị đã scale |

Ví dụ:

```java
DistributionSummary payload = DistributionSummary.builder("payload.size")
        .baseUnit("bytes")
        .scale(1024.0)
        .register(registry);

payload.record(1.5); // đầu vào là 1.5 KiB, được ghi thành 1536 bytes
```

Ở đây:

- `baseUnit("bytes")` nói rằng giá trị summary được diễn giải theo byte.
- `scale(1024.0)` chuyển đầu vào từ KiB sang byte.
- `record(1.5)` truyền 1,5 KiB; summary lưu giá trị sau chuyển đổi là 1536.
- Count tăng một lần, tổng tăng 1536 và max hiện tại là 1536.

Nếu bỏ `.scale(1024.0)`, `record(1.5)` chỉ ghi 1,5 nhưng meter vẫn mang metadata `bytes`. Kết quả đó sai đơn vị dù tên base unit trông có vẻ đúng. Ngược lại, nếu scale giá trị thành byte nhưng khai báo base unit là `kilobytes`, dữ liệu cũng bị mô tả sai.

## 2. Xác định đơn vị chuẩn trước khi chọn scale

Trước khi tạo summary, hãy xác định ba điều:

1. API hoặc nguồn dữ liệu cung cấp giá trị đầu vào theo đơn vị nào?
2. Đội vận hành muốn đọc và so sánh số liệu theo đơn vị nào?
3. Hệ thống nhận hoặc quy ước metrics của tổ chức mong đợi đơn vị nào?

Đơn vị đầu ra nên thống nhất trên toàn bộ ứng dụng. Với kích thước dữ liệu, byte thường là đơn vị chuẩn thuận tiện để tổng hợp và so sánh. Với số lượng phần tử, có thể dùng `items` hoặc một tên đơn vị phù hợp. Với tỷ lệ, hãy xác định rõ giá trị là phần trăm hay tỷ lệ từ 0 đến 1; đừng để dashboard phải đoán.

### Phân biệt kB, KiB, MB và MiB

Các tiền tố thập phân và nhị phân có hệ số khác nhau:

| Đơn vị đầu vào | Quy đổi sang byte | Hệ số scale |
| --- | ---: | ---: |
| kB (kilobyte thập phân) | 1 kB = 1.000 bytes | `1000.0` |
| KiB (kibibyte) | 1 KiB = 1.024 bytes | `1024.0` |
| MB (megabyte thập phân) | 1 MB = 1.000.000 bytes | `1_000_000.0` |
| MiB (mebibyte) | 1 MiB = 1.048.576 bytes | `1_048_576.0` |

Không dùng lẫn `KB`, `KiB` và `kB` nếu nguồn dữ liệu có quy ước cụ thể. Nếu API trả về KiB, hãy dùng hệ số 1024; nếu trả về kB thập phân, hãy dùng hệ số 1000. Một hệ số sai làm mọi thống kê tổng và phân phối sai theo cùng tỷ lệ.

## 3. Chuyển đổi KiB sang byte bằng scale

Giả sử ứng dụng đọc kích thước payload từ một thư viện trả về KiB. Ta muốn backend hiển thị tất cả kích thước theo byte:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public class PayloadMetrics {
    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary.builder("payload.size")
                .description("Payload size received by the service")
                .baseUnit("bytes")
                .scale(1024.0)
                .register(registry);
    }

    public void recordKiB(double sizeKiB) {
        payloadSize.record(sizeKiB);
    }
}
```

Khi nhận ba payload có kích thước 1,5 KiB, 2 KiB và 4 KiB:

```java
payloadMetrics.recordKiB(1.5);
payloadMetrics.recordKiB(2.0);
payloadMetrics.recordKiB(4.0);
```

Các giá trị summary được ghi nhận theo byte:

| Giá trị đầu vào | Giá trị sau scale |
| ---: | ---: |
| 1,5 KiB | 1.536 bytes |
| 2 KiB | 2.048 bytes |
| 4 KiB | 4.096 bytes |
| **Tổng** | **7.680 bytes** |

Count là 3, tổng là 7.680 bytes và max là 4.096 bytes. Percentile hoặc histogram, nếu được cấu hình, cũng dựa trên các giá trị đã chuyển đổi theo scale.

Tên metric canonical vẫn là `payload.size`. Registry có thể công bố đơn vị trong tên theo naming convention của backend, chẳng hạn Prometheus có thể hiển thị dạng `payload_size_bytes`. Hãy kiểm tra endpoint export thực tế để xác nhận tên và đơn vị.

## 4. Khi đầu vào đã là đơn vị chuẩn

Nếu nguồn dữ liệu đã trả kích thước theo byte, không cần chuyển đổi:

```java
DistributionSummary payloadBytes = DistributionSummary
        .builder("payload.size")
        .baseUnit("bytes")
        .register(registry);

payloadBytes.record(1536.0);
```

Không đặt `scale(1024.0)` trong trường hợp này, vì giá trị 1536 byte sẽ bị nhân thêm lần nữa thành 1.572.864. Chỉ dùng scale khi đơn vị đầu vào khác đơn vị chuẩn đã chọn.

Nếu nhiều component có nguồn dữ liệu ở đơn vị khác nhau, hãy chuyển đổi chúng về cùng đơn vị trước khi ghi vào cùng meter ID. Ví dụ một component trả byte, component khác trả KiB: component thứ nhất ghi trực tiếp, component thứ hai nhân 1024 trước khi ghi. Không để cùng một meter nhận giá trị có đơn vị khác nhau.

## 5. Scale ảnh hưởng đến những thống kê nào?

Với hệ số scale `s`, một giá trị đầu vào `x` được ghi nhận thành `x * s`. Count vẫn đếm số lần `record`, còn các thống kê về độ lớn dựa trên giá trị sau chuyển đổi.

| Thống kê | Tác động của scale |
| --- | --- |
| `count()` | Không đổi; mỗi lần ghi nhận hợp lệ vẫn là một quan sát |
| `totalAmount()` | Tổng các giá trị sau scale |
| `max()` | Giá trị lớn nhất sau scale |
| Histogram/bucket | Giá trị được phân loại theo miền sau scale |
| Percentile | Phân vị được tính trên các giá trị sau scale |

Ví dụ, nếu ghi `[1, 2, 4]` với scale 1024, count vẫn là 3; tổng đổi từ 7 thành 7168; max đổi từ 4 thành 4096. p50 hoặc p95 cũng được biểu diễn theo byte nếu đầu ra đã được chuẩn hóa thành byte.

Vì scale ảnh hưởng đến mọi giá trị đo, hãy chọn hệ số ngay khi thiết kế meter. Thay đổi scale khi ứng dụng đang chạy hoặc giữa các phiên bản triển khai có thể làm thay đổi ý nghĩa của time series, dù tên metric vẫn giữ nguyên. Nếu cần thay đổi đơn vị chuẩn, hãy cân nhắc thay đổi hợp đồng metric, dashboard và alert đồng bộ; không để cùng một series chứa dữ liệu trước và sau chuyển đổi với đơn vị khác nhau.

## 6. Chọn baseUnit theo miền dữ liệu

Base unit cần ngắn gọn, rõ nghĩa và nhất quán. Một số ví dụ:

| Miền dữ liệu | Tên meter gợi ý | baseUnit gợi ý | Scale thường gặp |
| --- | --- | --- | ---: |
| Payload đã tính bằng byte | `payload.size` | `bytes` | `1.0` |
| Payload đầu vào tính bằng KiB | `payload.size` | `bytes` | `1024.0` |
| Số phần tử trong batch | `batch.items` | `items` | `1.0` |
| Số message đầu vào tính theo nghìn message | `messages.received` | `messages` | `1000.0` |
| Tỷ lệ đầu vào là phần trăm 0–100, muốn lưu dạng 0–1 | `cache.hit.ratio` | `ratio` | `0.01` |

Các tên đơn vị trong bảng là lựa chọn thiết kế; hãy kiểm tra quy ước naming convention và backend mà ứng dụng sử dụng. Với đại lượng đếm, nếu mỗi lần ghi nhận đã là số item thực tế, thường chỉ cần scale 1. Với tỷ lệ, phải thống nhất liệu 0,75 có nghĩa là 75% hay 0,75%; đặt tên, description và đơn vị để người đọc không nhầm.

Không dùng `DistributionSummary` để đo thời gian chỉ vì thời lượng là một số. Với độ trễ hoặc thời lượng thao tác, `Timer` cung cấp ngữ nghĩa thời gian, count, tổng thời gian và các cấu hình phân phối phù hợp hơn. Distribution summary dành cho các đại lượng số không phải thời gian.

## 7. Cấu hình histogram và SLO theo đơn vị sau scale

Khi cần phân tích phân phối, có thể bật percentile hoặc histogram trên summary. Các ngưỡng bucket và SLO cần được xác định theo đơn vị mà summary thực sự ghi nhận sau scale.

Ví dụ với payload đầu vào theo KiB và summary lưu theo byte:

```java
DistributionSummary payload = DistributionSummary.builder("payload.size")
        .baseUnit("bytes")
        .scale(1024.0)
        .serviceLevelObjectives(1024.0, 10_240.0, 102_400.0)
        .publishPercentiles(0.50, 0.90, 0.99)
        .register(registry);
```

Các ngưỡng trong ví dụ tương ứng 1 KiB, 10 KiB và 100 KiB sau khi chuyển sang byte. Nếu ngưỡng được khai báo theo KiB trong khi giá trị histogram đã là byte, kết quả phân nhóm sẽ sai. Hãy ghi rõ đơn vị ngay cạnh ngưỡng trong tài liệu cấu hình và kiểm tra dữ liệu bucket ở registry đang dùng.

Percentile phía client và histogram phía backend có đặc điểm khác nhau. Percentile được tính trong từng instance không thể cộng hoặc tổng hợp trực tiếp thành percentile toàn cụm. Histogram với bucket tương thích cho phép backend tổng hợp các bucket của nhiều instance rồi tính percentile xấp xỉ. Khi dùng Prometheus, cần bật histogram phù hợp và truy vấn các chuỗi bucket thực tế đã export.

Ví dụ truy vấn p95 trên histogram Prometheus sau khi xác nhận tên metric và label:

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(payload_size_bytes_bucket[5m]))
)
```

Nếu cần phân tích theo loại payload hoặc endpoint, có thể giữ lại các label có cardinality thấp trong phép tổng hợp. Không đưa tên file, URL đầy đủ hoặc ID request vào tag chỉ để phân biệt từng payload.

## 8. Kiểm thử baseUnit và scale bằng SimpleMeterRegistry

Unit test có thể xác minh count, tổng và max sau khi scale. Không cần khởi động backend bên ngoài:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PayloadMetricsTest {
    @Test
    void recordsPayloadSizeInBytesWhenInputIsKibibytes() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            DistributionSummary payload = DistributionSummary
                    .builder("payload.size")
                    .baseUnit("bytes")
                    .scale(1024.0)
                    .register(registry);

            payload.record(1.5);
            payload.record(2.0);
            payload.record(4.0);

            DistributionSummary recorded = registry
                    .get("payload.size")
                    .summary();

            assertThat(recorded.count()).isEqualTo(3L);
            assertThat(recorded.totalAmount()).isEqualTo(7680.0);
            assertThat(recorded.max()).isEqualTo(4096.0);
        }
    }
}
```

Test xác nhận scale được áp dụng lên các giá trị đo. `SimpleMeterRegistry` phù hợp để kiểm tra hành vi instrumentation trong bộ nhớ; nó không xác minh tên export hoặc đơn vị mà Prometheus công bố. Với phần export, hãy thêm integration test hoặc kiểm tra endpoint `/actuator/prometheus` của ứng dụng.

Nên có test cho trường hợp đầu vào đã ở đơn vị chuẩn để bảo đảm không scale lần thứ hai. Nếu dùng histogram hoặc SLO, hãy kiểm tra bucket và ngưỡng ở đúng đơn vị đầu ra.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `baseUnit` tự chuyển đổi giá trị | Số đo vẫn giữ giá trị đầu vào nhưng bị gắn nhãn đơn vị sai | Dùng `scale` để chuyển đổi và `baseUnit` để mô tả đơn vị sau chuyển đổi |
| Khai báo baseUnit đúng nhưng chọn scale sai | Tổng, max và percentile sai theo hệ số | Xác nhận đơn vị nguồn và hệ số đổi đơn vị |
| Scale dữ liệu đã ở đơn vị chuẩn | Giá trị bị nhân thêm một lần | Dùng scale 1 hoặc bỏ cấu hình scale |
| Nhầm kB thập phân với KiB nhị phân | Kết quả lệch theo hệ số 1000/1024 | Ghi rõ quy ước đơn vị từ nguồn dữ liệu |
| Cùng meter nhận dữ liệu ở nhiều đơn vị | Một time series trộn các giá trị không thể so sánh | Chuẩn hóa mọi đầu vào trước khi record |
| Đặt SLO theo đơn vị đầu vào thay vì sau scale | Bucket hoặc ngưỡng không phản ánh miền dữ liệu | Khai báo ngưỡng theo đơn vị summary ghi nhận |
| Dùng DistributionSummary để đo thời gian | Mất ngữ nghĩa và quy ước chuẩn của Timer | Dùng `Timer` cho duration |
| Thay đổi scale mà giữ nguyên ý nghĩa metric | Lịch sử time series trộn hai đơn vị | Quản lý thay đổi như một thay đổi hợp đồng metric |

## 10. Quy trình chọn đơn vị và scale

Khi thêm một `DistributionSummary`, hãy thực hiện theo trình tự:

1. Xác định đại lượng cần đo và xác nhận nó không phải thời lượng.
2. Ghi rõ đơn vị nguồn mà code nhận được.
3. Chọn một đơn vị chuẩn để dashboard, alert và backend cùng sử dụng.
4. Tính hệ số chuyển đổi từ đơn vị nguồn sang đơn vị chuẩn; dùng scale 1 nếu hai đơn vị đã giống nhau.
5. Khai báo `baseUnit` theo đơn vị sau chuyển đổi và `scale` theo hệ số đã tính.
6. Xác nhận mọi component ghi vào cùng meter đều dùng cùng đơn vị đầu vào hoặc cùng quy tắc chuyển đổi.
7. Đặt histogram, percentile và SLO theo miền giá trị sau scale.
8. Kiểm thử count, tổng, max và phân phối với `SimpleMeterRegistry`.
9. Kiểm tra tên metric và đơn vị trong endpoint export của registry production.

`baseUnit` mô tả đại lượng mà hệ thống nhận sẽ đọc; `scale` chuẩn hóa các giá trị trước khi Micrometer lưu chúng. Khi đơn vị nguồn, đơn vị chuẩn và hệ số chuyển đổi được xác định nhất quán, count, tổng, max và phân phối có thể được so sánh đúng giữa các instance và được diễn giải chính xác ở hệ thống giám sát.
