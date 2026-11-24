# Đối chiếu count, totalTime, mean và max bằng dữ liệu có thời lượng biết trước

Micrometer Timer đo thời lượng của các lần thực hiện một thao tác và số lần thao tác được ghi nhận. Bốn thống kê cơ bản giúp trả lời bốn câu hỏi khác nhau: có bao nhiêu lần thực hiện, tổng thời gian đã tiêu tốn là bao nhiêu, thời lượng trung bình là bao nhiêu và lần thực hiện dài nhất trong cửa sổ thống kê là bao nhiêu.

Để hiểu chính xác các thống kê này, hãy bắt đầu bằng một bộ dữ liệu có thời lượng đã biết. Khi ghi trực tiếp các Duration cố định vào Timer, ta có thể tính kết quả bằng tay rồi đối chiếu với API. Cách kiểm chứng này tách biệt ngữ nghĩa thống kê khỏi sai số của đồng hồ và thời gian thực thi trên máy.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của count, totalTime, mean và max trong Timer.
- Tính thủ công bốn thống kê từ một tập thời lượng đã biết.
- Ghi các Duration cố định vào Timer và đọc kết quả bằng TimeUnit.
- Viết kiểm thử đối chiếu kết quả mong đợi với giá trị Micrometer trả về.
- Phân biệt mean với median và percentile.
- Hiểu giới hạn của max theo cửa sổ thời gian và cách tổng hợp dữ liệu từ nhiều instance.

## 1. Bốn thống kê trả lời bốn câu hỏi

Timer ghi nhận các lần thực hiện cùng một loại thao tác. Mỗi lần ghi nhận đóng góp vào số lần thực hiện và tổng thời lượng.

| Thống kê | Câu hỏi | Ý nghĩa |
| --- | --- | --- |
| `count()` | Có bao nhiêu lần được ghi nhận? | Tổng số lần thực hiện đã được Timer ghi nhận trong phạm vi thống kê của registry |
| `totalTime(unit)` | Tất cả các lần cộng lại mất bao lâu? | Tổng thời lượng của các lần thực hiện, được chuyển sang đơn vị yêu cầu |
| `mean(unit)` | Trung bình một lần mất bao lâu? | Tổng thời lượng chia cho số lần ghi nhận |
| `max(unit)` | Lần dài nhất mất bao lâu? | Thời lượng lớn nhất được quan sát trong cửa sổ thống kê max |

Bốn giá trị có liên hệ với nhau nhưng không thể thay thế nhau. Count cao không có nghĩa latency cao. Total time lớn có thể do có nhiều request, do từng request chậm hoặc do cả hai. Mean cho biết mức trung bình, trong khi max cho biết một cực trị quan sát được trong cửa sổ max.

## 2. Dùng bộ dữ liệu có thời lượng biết trước

Giả sử một thao tác thanh toán được ghi nhận bốn lần với thời lượng:

| Lần thực hiện | Thời lượng |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 300 ms |
| 4 | 400 ms |

Từ dữ liệu này, có thể tính thủ công:

**Count**

Có bốn lần thực hiện nên:

`count = 4`

**Total time**

Cộng tất cả thời lượng:

`totalTime = 100 + 200 + 300 + 400 = 1.000 ms`

**Mean**

Lấy tổng thời lượng chia cho số lần:

`mean = 1.000 / 4 = 250 ms`

**Max**

Thời lượng lớn nhất trong bốn lần là:

`max = 400 ms`

Kết quả mong đợi:

| Thống kê | Kết quả |
| --- | ---: |
| count | 4 |
| totalTime | 1.000 ms |
| mean | 250 ms |
| max | 400 ms |

Bộ dữ liệu cố định giúp ta biết chính xác kết quả phải nhận được. Nếu dùng `System.nanoTime()` hoặc đo một lời gọi dịch vụ thực, thời lượng phụ thuộc CPU, lịch chạy thread, GC và môi trường, nên không phù hợp để kiểm chứng phép tính cơ bản.

## 3. Ghi Duration đã biết vào Timer

Có thể tạo Timer từ MeterRegistry rồi ghi trực tiếp từng Duration:

```java
import java.time.Duration;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.MeterRegistry;

public final class PaymentMetrics {

    private final Timer paymentDuration;

    public PaymentMetrics(MeterRegistry registry) {
        this.paymentDuration = Timer.builder("checkout.payment.duration")
                .description("Thời lượng xử lý thanh toán")
                .register(registry);
    }

    public void recordKnownSamples() {
        paymentDuration.record(Duration.ofMillis(100));
        paymentDuration.record(Duration.ofMillis(200));
        paymentDuration.record(Duration.ofMillis(300));
        paymentDuration.record(Duration.ofMillis(400));
    }

    public Timer paymentDuration() {
        return paymentDuration;
    }
}
```

Mỗi lời gọi `record(Duration)` ghi nhận một quan sát. Sau bốn lần ghi nhận, Timer có bốn mẫu thời lượng. Khi đọc thống kê, hãy chỉ rõ đơn vị mong muốn:

```java
long count = paymentDuration.count();
double totalMillis = paymentDuration.totalTime(TimeUnit.MILLISECONDS);
double meanMillis = paymentDuration.mean(TimeUnit.MILLISECONDS);
double maxMillis = paymentDuration.max(TimeUnit.MILLISECONDS);
```

Trong đoạn mã này, cần import thêm:

```java
import java.util.concurrent.TimeUnit;
```

Micrometer lưu thời lượng theo độ chính xác nội bộ của implementation và chuyển đổi sang TimeUnit khi đọc hoặc xuất. Dùng cùng một đơn vị cho totalTime, mean và max giúp so sánh trực tiếp, tránh nhầm lẫn giữa nanosecond, millisecond và second.

## 4. Kiểm thử đối chiếu bốn thống kê

SimpleMeterRegistry cho phép kiểm tra Timer mà không cần khởi động backend giám sát. Ta tạo registry mới, ghi bốn Duration cố định, rồi đối chiếu kết quả.

```java
import static java.util.concurrent.TimeUnit.MILLISECONDS;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TimerStatisticsTest {

    @Test
    void calculatesCountTotalMeanAndMaxFromKnownDurations() {
        var registry = new SimpleMeterRegistry();

        Timer timer = Timer.builder("checkout.payment.duration")
                .description("Thời lượng xử lý thanh toán")
                .register(registry);

        timer.record(Duration.ofMillis(100));
        timer.record(Duration.ofMillis(200));
        timer.record(Duration.ofMillis(300));
        timer.record(Duration.ofMillis(400));

        assertThat(timer.count()).isEqualTo(4L);
        assertThat(timer.totalTime(MILLISECONDS)).isEqualTo(1000.0);
        assertThat(timer.mean(MILLISECONDS)).isEqualTo(250.0);
        assertThat(timer.max(MILLISECONDS)).isEqualTo(400.0);
    }
}
```

Kiểm thử trên kiểm tra bốn thuộc tính riêng biệt. Nếu count đúng nhưng totalTime sai, hãy kiểm tra đơn vị hoặc cách ghi duration. Nếu totalTime đúng nhưng mean sai, hãy kiểm tra số lần được ghi nhận và cách tính trung bình. Nếu max khác kết quả mong đợi, hãy xem cấu hình cửa sổ max và thời điểm đọc.

### Kiểm tra qua MeterRegistry

Nếu muốn kiểm tra cách lấy Timer theo tên và tag từ registry, có thể dùng:

```java
Timer timer = registry.get("checkout.payment.duration")
        .tag("provider", "card")
        .timer();
```

Tên và tag trong truy vấn phải khớp với Meter.Id đã đăng ký. Nếu có nhiều provider, mỗi tổ hợp tag tương ứng với một meter riêng và các thống kê được tính riêng cho từng meter.

## 5. Công thức và cách diễn giải

Với các thời lượng được ghi nhận `d1, d2, ..., dn`, các thống kê có thể diễn giải như sau:

**Count**

`count = n`

Count là số quan sát Timer đã ghi nhận. Nó không phải số thread, số người dùng hay số lần gọi dự kiến. Một lần thực hiện chỉ đóng góp khi code instrumentation thực sự ghi thời lượng vào Timer.

**Total time**

`totalTime = d1 + d2 + ... + dn`

Total time cộng thời lượng của mọi lần được ghi nhận. Nếu cùng một Timer đo xử lý request, total time là tổng thời gian xử lý của các request đã ghi nhận, không phải thời gian đồng hồ thực tế mà tiến trình đã tồn tại.

**Mean**

`mean = totalTime / count`

Mean là trung bình số học. Nếu chưa có quan sát nào, count bằng 0 và không có thời lượng trung bình có ý nghĩa để diễn giải. Không nên tự chia cho 0 trong truy vấn hoặc code phân tích.

**Max**

`max = max(d1, d2, ..., dn)`

Max là thời lượng lớn nhất mà cơ chế thống kê max đang giữ. Với Micrometer, max của Timer thường là thống kê theo cửa sổ thời gian (time-window max), không nhất thiết là giá trị lớn nhất kể từ lúc ứng dụng khởi động.

## 6. Phân biệt max theo cửa sổ với max trọn đời

Một điểm quan trọng khi đọc Timer là max có thể được quản lý theo cửa sổ thời gian. Micrometer sử dụng cơ chế time-window cho thống kê max; thời hạn và số cửa sổ đệm phụ thuộc DistributionStatisticConfig và cấu hình registry.

Điều đó có nghĩa:

- Max phản ánh giá trị lớn nhất còn nằm trong cửa sổ thống kê hiện tại.
- Khi quan sát cũ hết hạn và không có mẫu mới lớn hơn, max có thể giảm hoặc trở về 0 sau khi cửa sổ hết hiệu lực.
- Max không nên được hiểu là đỉnh lớn nhất từ khi process khởi động.
- Các registry và cấu hình khác nhau có thể có hành vi cửa sổ khác nhau.

Ví dụ, một request mất 2 giây được ghi nhận và trở thành max. Sau khi cửa sổ chứa quan sát đó hết hạn, nếu chỉ có các request 100–200 ms được ghi nhận trong cửa sổ mới, max có thể phản ánh 200 ms. Điều đó không có nghĩa request 2 giây chưa từng xảy ra; nó đã ra khỏi cửa sổ max.

Nếu cần giữ lịch sử các cực trị trong thời gian dài, hãy dựa vào hệ thống lưu trữ metrics và khoảng thời gian truy vấn phù hợp. Không dùng một lần đọc `timer.max()` như một kho lưu lịch sử.

## 7. Mean không phải median hay percentile

Mean là trung bình số học, còn median (p50) và percentile mô tả vị trí trong phân phối. Chúng có thể khác xa nhau khi dữ liệu lệch hoặc có một số request rất chậm.

Ví dụ, với các thời lượng:

`10 ms, 10 ms, 10 ms, 10 ms, 950 ms`

Ta có:

- Count = 5.
- Total time = 990 ms.
- Mean = 198 ms.
- Median = 10 ms.
- Max = 950 ms.

Mean bị kéo lên bởi một quan sát rất lớn. Nó không cho biết phần lớn request hoàn tất trong khoảng bao lâu. Nếu cần phân tích phân phối latency, hãy cấu hình histogram hoặc percentile phù hợp với backend và mục tiêu quan sát. Percentile được tính và tổng hợp có quy tắc riêng; không thể khôi phục chính xác phân phối chỉ từ count, totalTime, mean và max.

## 8. Tổng hợp dữ liệu từ nhiều instance

Khi một dịch vụ chạy trên nhiều instance, không nên lấy trung bình cộng các mean riêng lẻ nếu số request mỗi instance khác nhau.

Giả sử:

| Instance | Count | Total time | Mean |
| --- | ---: | ---: | ---: |
| A | 100 | 10.000 ms | 100 ms |
| B | 10 | 5.000 ms | 500 ms |

Trung bình cộng hai mean là 300 ms, nhưng không phản ánh trung bình của toàn bộ 110 request.

Mean tổng hợp đúng được tính từ tổng thời lượng chia tổng số lần:

`global mean = (10.000 + 5.000) / (100 + 10) ≈ 136,36 ms`

Vì vậy, khi truy vấn metrics từ nhiều instance, hãy tổng hợp total time và count trước, rồi tính tỷ lệ. Cách này giữ trọng số theo số quan sát của từng instance.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm totalTime với thời gian chạy của process | Đánh giá sai mức tiêu thụ thời gian | Hiểu totalTime là tổng các duration được ghi |
| Dùng count làm số request thành công | Bao gồm mọi lần được ghi, có thể cả request lỗi | Phân loại kết quả bằng tag hoặc meter riêng |
| Đọc mean mà không kiểm tra count | Diễn giải trung bình khi chưa có quan sát | Kiểm tra count trước khi kết luận |
| So sánh thời lượng ở đơn vị khác nhau | Sai lệch hàng nghìn hoặc hàng triệu lần | Dùng cùng TimeUnit |
| Coi max là đỉnh từ lúc khởi động | Bỏ sót ý nghĩa time-window | Kiểm tra cấu hình expiry và buffer |
| Dùng mean thay cho p95 hoặc p99 | Không nhận biết được đuôi latency | Cấu hình histogram/percentile |
| Trung bình cộng mean của từng instance | Instance ít request có trọng số quá lớn | Cộng totalTime và count trước |
| Dùng thời gian thực để test phép tính | Test phụ thuộc môi trường và tải | Ghi Duration cố định đã biết |

## 10. Checklist kiểm chứng Timer

Khi xây dựng hoặc review instrumentation, hãy kiểm tra:

1. Mỗi lần thực hiện cần đo có gọi Timer record đúng một lần không?
2. Bộ dữ liệu kiểm thử có thời lượng biết trước không?
3. Count có bằng số mẫu đã ghi không?
4. Total time có bằng tổng các mẫu sau khi đổi sang cùng đơn vị không?
5. Mean có bằng totalTime chia count không?
6. Max có bằng mẫu lớn nhất trong cửa sổ max hiện tại không?
7. Có hiểu rõ cấu hình time-window của registry không?
8. Có phân biệt mean với median và percentile không?
9. Khi tổng hợp nhiều instance, có cộng count và totalTime trước khi tính mean không?

## Kết luận

Count cho biết số lần được ghi nhận; totalTime là tổng thời lượng; mean là totalTime chia count; max là giá trị lớn nhất mà thống kê max đang giữ trong cửa sổ của nó. Dùng các Duration cố định như 100, 200, 300 và 400 ms giúp kiểm chứng chính xác count = 4, totalTime = 1.000 ms, mean = 250 ms và max = 400 ms.

Khi đọc metrics production, cần xem đơn vị, phạm vi thống kê và cấu hình cửa sổ. Mean không mô tả đầy đủ phân phối latency, còn max không nhất thiết là cực trị trọn đời. Kết hợp count, totalTime, mean, max với histogram hoặc percentile khi cần sẽ giúp diễn giải hiệu năng chính xác hơn.
