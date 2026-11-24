# Giá trị cực đại theo cửa sổ thời gian và hiện tượng trở về không

Trong Micrometer, `Timer.max(...)` không phải giá trị lớn nhất được ghi nhận kể từ khi ứng dụng khởi động. Đây là giá trị cực đại trong một cửa sổ thời gian có giới hạn. Micrometer giữ các mẫu cực đại trong một bộ đệm xoay vòng; khi các mẫu cũ hết thời hạn và không còn mẫu mới trong cửa sổ, giá trị max có thể giảm rồi trở về `0`.

Hiện tượng này là hành vi có chủ đích của thống kê `TimeWindowMax`, không nhất thiết là lỗi mất dữ liệu. Hiểu đúng cửa sổ thời gian, cấu hình `expiry` và `bufferLength`, cũng như sự khác nhau giữa `max`, `count`, `totalTime` và histogram sẽ giúp bạn đọc dashboard độ trễ chính xác hơn.

## 1. Timer ghi nhận những đại lượng nào?

`Timer` đo thời lượng của các thao tác và số lần thao tác được ghi nhận. Tùy registry và cấu hình thống kê, timer có thể cung cấp nhiều đại lượng:

| Đại lượng | Ý nghĩa | Câu hỏi có thể trả lời |
| --- | --- | --- |
| `count` | Số lần ghi nhận thao tác | Có bao nhiêu thao tác đã được đo? |
| `totalTime` | Tổng thời lượng của các thao tác | Tổng thời gian xử lý được ghi nhận là bao nhiêu? |
| `mean` | Thời lượng trung bình, thường suy ra từ tổng thời lượng và count | Một thao tác trung bình mất bao lâu? |
| `max` | Thời lượng lớn nhất trong cửa sổ thống kê gần đây | Thao tác chậm nhất gần đây mất bao lâu? |
| Percentile | Phân vị thời lượng, nếu được cấu hình | 95% hoặc 99% thao tác hoàn tất trong bao lâu? |
| Histogram | Phân bố số lần ghi nhận theo các bucket | Có bao nhiêu thao tác nằm dưới từng ngưỡng thời gian? |

Ví dụ đăng ký timer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Timer checkoutTimer;

    public CheckoutMetrics(MeterRegistry registry) {
        this.checkoutTimer = Timer.builder("shop.checkout.duration")
                .description("Time spent completing checkout")
                .register(registry);
    }

    public void recordDuration(long duration, TimeUnit unit) {
        checkoutTimer.record(duration, unit);
    }
}
```

Timer ghi nhận các lần đo. Ví dụ, gọi `recordDuration(250, TimeUnit.MILLISECONDS)` ghi nhận một thao tác mất 250 ms. Từ những mẫu này, Micrometer cập nhật các thống kê tương ứng.

## 2. `max` là time-window maximum

Micrometer dùng cơ chế `TimeWindowMax` cho giá trị cực đại của timer. Thay vì giữ lại giá trị lớn nhất vĩnh viễn, cơ chế này giữ các cực đại trong một số khoảng thời gian liên tiếp bằng bộ đệm xoay vòng.

Hai tham số quyết định khoảng lưu giữ:

- **`expiry`**: thời lượng của mỗi slot trong bộ đệm.
- **`bufferLength`**: số slot được giữ trong bộ đệm xoay vòng.

Độ dài cửa sổ xấp xỉ:

\[
T_{window} = expiry \times bufferLength
\]

Ví dụ, nếu `expiry` là 1 phút và `bufferLength` là 3, max được tính trên khoảng thời gian xấp xỉ 3 phút. Khi các slot lần lượt được xoay và mẫu cũ bị loại khỏi cửa sổ, giá trị cực đại có thể giảm.

Nếu không có mẫu mới trong toàn bộ cửa sổ, tất cả slot chứa mẫu cũ sẽ hết hạn. Khi đó `Timer.max(...)` trả về `0`. Một mẫu chậm nhất trước đó không được giữ mãi chỉ vì nó từng là cực đại của ứng dụng.

### 2.1. Vì sao Micrometer dùng cửa sổ thay vì giữ max trọn đời?

Giá trị max trọn đời chỉ có thể giữ nguyên hoặc tăng. Một lần xử lý mất 45 giây do sự cố trong ngày đầu tiên sẽ khiến max luôn là 45 giây, kể cả khi ứng dụng đã ổn định nhiều ngày sau đó. Giá trị như vậy không phản ánh tình trạng độ trễ gần đây.

Time-window max cho phép số liệu phản ánh các mẫu gần đây hơn. Khi mẫu bất thường cũ ra khỏi cửa sổ, max có thể trở về mức thấp hơn. Nếu hệ thống không còn ghi nhận thao tác trong suốt cửa sổ, max trở về 0 để biểu thị rằng không còn mẫu hợp lệ trong cửa sổ thống kê.

Điều này cũng có nghĩa `max=0` không nhất thiết nói rằng thao tác thực tế hoàn thành trong 0 giây. Nó có thể có nghĩa là chưa có mẫu nào trong cửa sổ hiện tại hoặc các mẫu trước đó đã hết hạn.

## 3. Minh họa hiện tượng max giảm và trở về 0

Giả sử cửa sổ có độ dài 3 phút. Ứng dụng ghi nhận các thời lượng sau:

| Thời điểm ghi nhận | Thời lượng | Max trong cửa sổ sau khi ghi |
| --- | ---: | ---: |
| 10:00:10 | 120 ms | 120 ms |
| 10:00:40 | 450 ms | 450 ms |
| 10:01:20 | 180 ms | 450 ms |
| 10:02:10 | 90 ms | 450 ms |
| 10:03:45 | 150 ms | 180 ms; mẫu 450 ms đã ra khỏi cửa sổ 3 phút |
| Sau khi mọi slot cũ hết hạn và không có mẫu mới | — | 0 ms |

Thời điểm chính xác mà một mẫu bị loại phụ thuộc ranh giới xoay slot và thời điểm ghi nhận. Vì vậy, không nên suy luận rằng max luôn trở về 0 đúng một khoảng `expiry` sau lần ghi cuối. Cần xét toàn bộ cửa sổ `expiry × bufferLength` và cách registry xoay bộ đệm.

Một tình huống thường thấy trên dashboard:

1. Có request chậm 5 giây, max tăng lên 5 giây.
2. Các request tiếp theo đều nhanh, khoảng 100 ms. Max vẫn giữ 5 giây trong lúc mẫu chậm còn nằm trong cửa sổ.
3. Khi mẫu 5 giây hết hạn, max giảm về khoảng 100 ms nếu còn mẫu mới trong cửa sổ.
4. Nếu sau đó không có thao tác nào được ghi nhận và toàn bộ cửa sổ trôi qua, max trở về 0.

Đây là lý do biểu đồ max có thể giảm theo thời gian dù ứng dụng không ghi nhận một sự kiện “giảm thời lượng”. Max là thống kê trên tập mẫu gần đây; tập mẫu thay đổi khi cửa sổ xoay.

## 4. Cấu hình expiry và bufferLength

Micrometer cho phép cấu hình thời gian hết hạn và số slot cho thống kê phân phối. Có thể cấu hình trên builder của timer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

Timer timer = Timer.builder("shop.checkout.duration")
        .description("Time spent completing checkout")
        .distributionStatisticExpiry(Duration.ofSeconds(30))
        .distributionStatisticBufferLength(4)
        .register(registry);
```

Với cấu hình trên, mỗi slot có thời lượng 30 giây và bộ đệm có 4 slot. Cửa sổ max xấp xỉ:

\[
30\ seconds \times 4 = 120\ seconds
\]

Nếu không có mẫu mới và toàn bộ các slot đã xoay qua, max trở về 0 sau khoảng cửa sổ này. Thời điểm quan sát được còn phụ thuộc thời điểm bắt đầu/đọc và nhịp xoay của bộ đệm.

### 4.1. Giá trị mặc định

Nếu không cấu hình riêng, `expiry` mặc định phụ thuộc registry: thường lấy step của `StepMeterRegistry`; với registry không có step, mặc định thường là 1 phút. `bufferLength` mặc định thường là 3. Do đó, cửa sổ mặc định thường xấp xỉ ba lần expiry.

Không nên giả định mọi registry đều có cùng cửa sổ mặc định. Hãy kiểm tra loại registry, phiên bản Micrometer và cấu hình `DistributionStatisticConfig` của ứng dụng. Spring Boot cũng có thể áp dụng cấu hình phân phối qua properties hoặc customizer tùy phiên bản.

### 4.2. Chọn cửa sổ phù hợp

| Cửa sổ ngắn | Cửa sổ dài |
| --- | --- |
| Phản ánh thay đổi gần đây nhanh hơn | Giữ dấu vết của mẫu chậm lâu hơn |
| Max có thể giảm nhanh sau một spike | Max ổn định hơn giữa các lần scrape |
| Dễ bị ảnh hưởng bởi khoảng thời gian ít traffic | Có thể giữ lại spike cũ lâu hơn |
| Phù hợp khi cần quan sát biến động ngắn hạn | Phù hợp khi traffic thưa hoặc muốn giữ mẫu gần đây lâu hơn |

Không có một cửa sổ đúng cho mọi ứng dụng. Hãy chọn dựa trên tần suất request, khoảng scrape, mục tiêu dashboard và cách vận hành alert. Cửa sổ rất ngắn có thể làm max trở về 0 thường xuyên ở dịch vụ ít traffic; cửa sổ quá dài có thể khiến spike cũ còn ảnh hưởng dashboard lâu sau khi sự cố đã kết thúc.

## 5. Phân biệt max với count và totalTime

`max` có thể trở về 0 sau khi mẫu hết hạn, trong khi `count` và `totalTime` có thể vẫn giữ tổng tích lũy trong registry có temporality dạng cumulative. Đây là các thống kê có mục đích khác nhau.

Ví dụ, một timer đã ghi nhận 10.000 request và tổng thời gian là 120 giây. Sau một khoảng không có request:

- `count` trong registry cumulative vẫn có thể là 10.000.
- `totalTime` trong registry cumulative vẫn có thể là 120 giây.
- `max` có thể trở về 0 khi các mẫu trong time window hết hạn.

Với registry theo step, count và total time có thể được báo cáo theo từng step thay vì tổng từ lúc tiến trình khởi động. Hãy đọc semantics của backend và registry đang dùng trước khi so sánh số liệu.

Không nên dùng `max=0` để kết luận service không nhận traffic. Hãy xem `count` hoặc tốc độ tăng của count trong cùng khoảng thời gian. Nếu count không tăng nhưng max vẫn lớn hơn 0, có thể mẫu chậm vẫn còn nằm trong cửa sổ. Nếu count tăng mà max bằng 0, hãy kiểm tra đơn vị, cấu hình timer và cách registry export số liệu.

## 6. Phân biệt max với percentile và histogram

Max chỉ cho biết một mẫu cực đại trong cửa sổ. Nó nhạy với một request bất thường và không cho biết phần lớn request có độ trễ ra sao.

Ví dụ, 1.000 request có 999 request mất 50 ms và một request mất 8 giây. Max là 8 giây, nhưng chỉ nhìn max không thể biết đây là một ngoại lệ đơn lẻ hay cả hệ thống đang chậm.

Percentile và histogram cung cấp bối cảnh tốt hơn:

- **p50** mô tả độ trễ ở trung vị.
- **p95** mô tả ngưỡng mà khoảng 95% mẫu nằm dưới hoặc bằng.
- **p99** giúp quan sát tail latency.
- **Histogram** cho phép backend tổng hợp số lượng mẫu theo bucket và tính percentile trên tập dữ liệu đã thu thập.

Ví dụ cấu hình histogram:

```java
Timer requestTimer = Timer.builder("shop.http.server.duration")
        .description("HTTP request duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1)
        )
        .register(registry);
```

Histogram tạo thêm chuỗi thời gian cho các bucket và các thống kê đi kèm, do đó cần cân nhắc cardinality và chi phí lưu trữ. Nếu cần tổng hợp p95/p99 qua nhiều instance, histogram bucket thường phù hợp hơn percentile được tính riêng tại từng instance.

Không nên cộng hoặc lấy trung bình các percentile của từng instance để suy ra percentile toàn cụm. Hãy để backend tính percentile từ bucket đã được tổng hợp đúng cách.

## 7. Đọc max trong Prometheus

Với Prometheus registry, timer thường xuất các chuỗi như count, sum và max theo quy ước tên cùng đơn vị của registry. Một timer có tên `shop.checkout.duration` có thể xuất các chuỗi dạng:

```text
shop_checkout_duration_seconds_count
shop_checkout_duration_seconds_sum
shop_checkout_duration_seconds_max
```

Tên cụ thể cần được xác nhận tại endpoint `/actuator/prometheus`, vì naming convention và phiên bản registry có thể ảnh hưởng tên cuối cùng.

Có thể đọc giá trị max hiện tại bằng cách truy vấn chuỗi `_max`:

```promql
shop_checkout_duration_seconds_max
```

Để quan sát số request trong 5 phút, dùng chuỗi count với `rate`:

```promql
sum(rate(shop_checkout_duration_seconds_count[5m]))
```

Khi dashboard hiển thị `_max = 0`, hãy đối chiếu với count/rate và traffic. Nếu không có mẫu mới trong cửa sổ, max có thể trở về 0 là đúng theo semantics của Micrometer. Không nên tự động coi mọi lần max về 0 là sự cố hoặc dữ liệu bị mất.

## 8. Kiểm thử hiện tượng max trở về 0 bằng MockClock

Không nên dùng `Thread.sleep()` trong unit test để chờ cửa sổ hết hạn. Micrometer cung cấp `MockClock` để tiến thời gian một cách xác định.

Ví dụ dưới đây cấu hình `expiry=10 giây`, `bufferLength=2`, ghi một mẫu 2 giây rồi tiến clock qua toàn bộ cửa sổ 20 giây:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class TimerMaxWindowTest {
    @Test
    void maxReturnsToZeroAfterWindowExpiresWithoutNewSamples() {
        MockClock clock = new MockClock();
        try (var registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock)) {
            Timer timer = Timer.builder("shop.checkout.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(2)
                    .register(registry);

            timer.record(2, TimeUnit.SECONDS);
            assertThat(timer.max(TimeUnit.SECONDS)).isEqualTo(2.0);

            clock.add(Duration.ofSeconds(20));

            assertThat(timer.max(TimeUnit.SECONDS)).isZero();
        }
    }
}
```

Test dùng clock giả để kiểm tra hành vi của time window mà không phải chờ thời gian thực. Khi chạy test trên phiên bản Micrometer cụ thể của dự án, hãy bảo đảm builder hỗ trợ các tùy chọn expiry/buffer length và registry dùng cùng `MockClock` đã truyền vào.

Có thể bổ sung test ghi một mẫu mới trước khi cửa sổ cũ hết hạn để xác minh max được cập nhật và giữ lại theo slot mới. Cũng nên kiểm tra trường hợp mẫu cũ hết hạn nhưng vẫn còn mẫu mới hơn; max lúc đó giảm về giá trị lớn nhất của những mẫu còn trong cửa sổ thay vì lập tức về 0.

## 9. Những nguyên nhân khiến max giảm hoặc trở về 0

- **Mẫu cực đại hết hạn:** một request chậm cũ rời khỏi cửa sổ; max giảm về mẫu lớn nhất còn lại.
- **Không có mẫu mới trong toàn cửa sổ:** các slot lần lượt hết hạn và max trở về 0.
- **Traffic thưa:** dịch vụ ít request có thể thường xuyên không có mẫu trong cửa sổ hiện tại.
- **Thay đổi cấu hình expiry/bufferLength:** cửa sổ mới ngắn hơn có thể khiến max cũ biến mất sớm hơn.
- **Khởi động lại tiến trình:** registry trong bộ nhớ được tạo lại; thống kê trong bộ nhớ của timer bắt đầu lại.
- **Đơn vị hiển thị khác nhau:** max có thể được xuất theo giây trong khi code đọc bằng milliseconds; so sánh sai đơn vị làm biểu đồ hoặc alert khó hiểu.
- **Thay đổi tag:** dashboard đang xem một chuỗi tag cụ thể; traffic chuyển sang tag value khác có thể khiến chuỗi cũ không có mẫu mới và max hết hạn.

Khi điều tra, hãy xác minh tên metric, tag, đơn vị, thời điểm scrape, traffic, loại registry và cấu hình phân phối trước khi kết luận có lỗi.

## 10. Checklist đọc và cấu hình Timer.max

- [ ] Hiểu `max` là cực đại trong time window, không phải cực đại trọn đời.
- [ ] Biết `expiry` và `bufferLength` đang áp dụng cho timer.
- [ ] Ước lượng cửa sổ bằng `expiry × bufferLength`.
- [ ] Không diễn giải `max=0` là thao tác mất 0 giây nếu không có mẫu trong cửa sổ.
- [ ] Đối chiếu max với count/rate để xác định có traffic hay không.
- [ ] Dùng histogram/percentile để hiểu phân bố và tail latency.
- [ ] Tính chi phí cardinality khi bật histogram hoặc thêm tag.
- [ ] Kiểm tra tên và đơn vị thực tế tại endpoint export.
- [ ] Dùng `MockClock` để kiểm thử hết hạn thay vì `Thread.sleep()`.
- [ ] Khi max giảm, xác minh mẫu cũ đã hết hạn trước khi kết luận dữ liệu bị mất.

`Timer.max` hữu ích để quan sát độ trễ cực đại gần đây, nhưng chỉ có ý nghĩa khi bạn biết cửa sổ thống kê và đặt nó cạnh count, throughput cùng phân phối thời lượng. Hiện tượng max trở về 0 sau một khoảng không có mẫu mới là hệ quả của cơ chế time-window, giúp loại bỏ ảnh hưởng của các spike đã quá cũ khỏi số liệu vận hành hiện tại.
