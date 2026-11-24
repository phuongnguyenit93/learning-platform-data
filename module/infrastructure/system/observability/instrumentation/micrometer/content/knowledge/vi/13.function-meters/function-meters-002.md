# FunctionCounter và yêu cầu hàm đếm không giảm theo thời gian

`FunctionCounter` của Micrometer dùng để theo dõi một bộ đếm tích lũy đã tồn tại trong ứng dụng hoặc thư viện khác. Thay vì gọi `increment()` trên meter, Micrometer gọi một hàm đọc để lấy giá trị hiện tại của nguồn dữ liệu khi thu thập metrics.

Giá trị mà hàm đọc trả về phải **không giảm theo thời gian trong vòng đời của nguồn dữ liệu**. Đây là hợp đồng quan trọng nhất của `FunctionCounter`. Nếu giá trị có thể tăng rồi giảm, ví dụ độ dài hàng đợi hoặc số kết nối đang mở, đó là trạng thái hiện tại và nên được biểu diễn bằng `Gauge`.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, bài này giúp bạn nhận biết khi nào nên dùng `FunctionCounter`, cách kết nối nó với một nguồn đếm có sẵn, cách bảo đảm tính đơn điệu và cách tránh lỗi khi nguồn bị reset hoặc thay đổi vòng đời.

## 1. FunctionCounter là gì?

`FunctionCounter` là một loại function-tracking meter. Nó quan sát một đối tượng và gọi một hàm để đọc số đếm tích lũy của đối tượng đó. Micrometer không sở hữu thao tác tăng số đếm; hệ thống nguồn vẫn chịu trách nhiệm cập nhật giá trị.

Ví dụ, một thư viện cache có sẵn số lần cache hit tích lũy. Thay vì sao chép số đếm đó vào một counter khác, bạn có thể đăng ký `FunctionCounter` để Micrometer đọc trực tiếp số liệu của thư viện.

```java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong cacheHits = new AtomicLong();

FunctionCounter.builder("app.cache.hits", cacheHits, value -> value.get())
        .description("Total number of cache hits")
        .register(registry);
```

Khi cache ghi nhận một hit, nguồn dữ liệu tăng giá trị:

```java
cacheHits.incrementAndGet();
```

Micrometer đọc giá trị hiện tại của `cacheHits` ở lần thu thập tiếp theo. Nếu giá trị nguồn là 125 tại lần scrape này và 140 ở lần scrape sau, FunctionCounter báo các giá trị tích lũy tương ứng; backend có thể tính tốc độ tăng từ chênh lệch theo thời gian.

### 1.1. FunctionCounter không phải một counter có API increment

`Counter` thông thường do Micrometer quản lý số lần tăng:

```java
Counter requests = registry.counter("app.requests.completed");
requests.increment();
```

Với `FunctionCounter`, Micrometer chỉ quan sát giá trị từ một nguồn khác:

```java
FunctionCounter completed = FunctionCounter.builder(
        "app.requests.completed", externalStats, stats -> stats.completedCount())
        .register(registry);
```

Không gọi `increment()` trên FunctionCounter. Thao tác làm tăng số đếm phải xảy ra ở nguồn dữ liệu được theo dõi. Nếu ứng dụng không có nguồn tích lũy sẵn và chính ứng dụng kiểm soát điểm phát sinh sự kiện, `Counter` thường đơn giản và phù hợp hơn.

## 2. Vì sao hàm đếm phải không giảm?

Counter biểu diễn tổng số sự kiện đã xảy ra trong một vòng đời. Vì vậy, giá trị hợp lệ chỉ có thể giữ nguyên hoặc tăng:

\[
f(t_2) \geq f(t_1) \quad \text{khi } t_2 > t_1
\]

Ví dụ về các nguồn có tính đơn điệu:

- Tổng số cache hit kể từ khi tiến trình khởi động.
- Tổng số message đã xử lý thành công kể từ khi worker khởi động.
- Tổng số byte đã đọc từ một nguồn thống kê tích lũy.
- Tổng số kết nối được tạo kể từ khi client được khởi tạo.

Ví dụ về các giá trị không phù hợp:

- Số request đang xử lý: tăng khi nhận request, giảm khi hoàn tất.
- Số item hiện có trong queue: tăng khi enqueue, giảm khi dequeue.
- Số connection đang mở: tăng khi mở, giảm khi đóng.
- Dung lượng bộ nhớ hiện đang sử dụng: có thể tăng hoặc giảm.

Những giá trị ở nhóm thứ hai là trạng thái hiện tại, nên dùng `Gauge`. Nếu dùng chúng làm FunctionCounter, khi giá trị giảm, meter không còn tuân thủ hợp đồng counter. Backend có thể diễn giải mức giảm như một lần reset bộ đếm hoặc tạo ra tốc độ âm, tùy hệ thống và cách truy vấn.

## 3. FunctionCounter, Counter và Gauge khác nhau thế nào?

| Tiêu chí | `Counter` | `FunctionCounter` | `Gauge` |
| --- | --- | --- | --- |
| Ý nghĩa | Tổng sự kiện tích lũy | Tổng tích lũy có sẵn ở nguồn bên ngoài | Giá trị trạng thái hiện tại |
| Ai cập nhật số liệu? | Mã ứng dụng gọi `increment()` | Đối tượng nguồn được theo dõi | Đối tượng trạng thái được cập nhật |
| Micrometer làm gì? | Giữ và tăng bộ đếm | Gọi hàm đọc giá trị tích lũy | Gọi hàm đọc giá trị hiện tại |
| Có được giảm không? | Không | Không | Có thể tăng hoặc giảm |
| Ví dụ | Số đơn hàng tạo thành công | Tổng cache hit từ thư viện cache | Số request đang xử lý |

Quy tắc chọn nhanh:

- Ứng dụng cần tự ghi nhận mỗi sự kiện: dùng `Counter`.
- Một thư viện hoặc đối tượng khác đã giữ tổng tích lũy và cung cấp hàm đọc: cân nhắc `FunctionCounter`.
- Giá trị biểu diễn trạng thái có thể tăng hoặc giảm: dùng `Gauge`.

Không tạo một FunctionCounter chỉ để bọc một Counter mà bạn đang kiểm soát. Việc thêm một lớp function-tracking không mang lại lợi ích nếu nguồn dữ liệu không phải một bộ đếm tích lũy độc lập.

## 4. Đăng ký FunctionCounter với nguồn thống kê có sẵn

Ví dụ sau mô phỏng một thành phần cache có bộ đếm hit riêng. `CacheStatistics` là nguồn dữ liệu; `CacheMetrics` chỉ kết nối nguồn đó với Micrometer.

```java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
final class CacheStatistics {
    private final AtomicLong hits = new AtomicLong();

    void recordHit() {
        hits.incrementAndGet();
    }

    double hitCount() {
        return hits.get();
    }
}

@Component
public class CacheMetrics {
    private final CacheStatistics statistics;

    public CacheMetrics(MeterRegistry registry, CacheStatistics statistics) {
        this.statistics = statistics;

        FunctionCounter.builder(
                        "app.cache.hits", statistics, CacheStatistics::hitCount)
                .description("Total number of cache hits")
                .register(registry);
    }
}
```

Trong ví dụ Spring thực tế, `CacheStatistics` cần được tạo và quản lý như một bean hoặc được cung cấp bởi thư viện cache. `CacheMetrics` giữ tham chiếu đến nguồn dữ liệu để nó tồn tại trong suốt thời gian meter cần theo dõi.

Khi cache hit xảy ra, thành phần cache gọi `recordHit()`. Micrometer không cần biết sự kiện đó xảy ra ở đâu; nó chỉ đọc tổng hiện tại qua `hitCount()` trong lần thu thập metrics.

### 4.1. Dùng FunctionCounter với thư viện bên ngoài

Nếu thư viện đã cung cấp đối tượng thống kê, hãy ưu tiên đọc API tích lũy chính thức của thư viện. Ví dụ minh họa:

```java
FunctionCounter.builder(
        "app.client.responses",
        clientStatistics,
        stats -> stats.totalResponses())
    .description("Total responses reported by the client")
    .tag("client", "inventory")
    .register(registry);
```

Tên `totalResponses()` ở đây đại diện cho một API của thư viện giả định. Trước khi dùng API thật, hãy xác minh giá trị đó là tổng tích lũy và không bị giảm trong vòng đời đối tượng. Không chọn một getter chỉ vì tên của nó có chữ `count`; nó có thể trả về số lượng hiện tại thay vì tổng số sự kiện.

## 5. Tính đơn điệu và hành vi reset

Điều quan trọng không chỉ là giá trị thường tăng, mà là nó không giảm trong phạm vi vòng đời mà backend xem là cùng một chuỗi counter.

Giả sử một nguồn trả về:

| Thời điểm | Giá trị | Hợp lệ với FunctionCounter? |
| --- | ---: | --- |
| 10:00 | 100 | Có |
| 10:01 | 125 | Có |
| 10:02 | 125 | Có, giá trị có thể giữ nguyên |
| 10:03 | 141 | Có |
| 10:04 | 0 | Không, nguồn đã giảm/reset |
| 10:05 | 8 | Sau reset, số mới tăng nhưng chuỗi nguồn đã vi phạm tính đơn điệu trong vòng đời hiện tại |

### 5.1. Reset khi tiến trình khởi động lại

Một bộ đếm tích lũy trong bộ nhớ thường bắt đầu lại từ 0 khi tiến trình khởi động lại. Với hệ thống giám sát như Prometheus, một counter time series có thể giảm khi tiến trình restart; Prometheus có cơ chế nhận diện counter reset khi tính `rate()` hoặc `increase()`.

Điều này khác với việc chủ động đặt nguồn về 0 trong khi cùng một tiến trình và cùng một nguồn vẫn đang chạy. Không nên reset một FunctionCounter theo chu kỳ, sau mỗi batch hoặc theo ngày nếu backend đang xem nó là cùng một counter liên tục.

Nếu thư viện nguồn có thể reset số đếm trong cùng vòng đời, hãy tìm một số liệu tích lũy khác không reset, dùng một `Counter` do ứng dụng quản lý để ghi nhận các sự kiện, hoặc chọn một cách biểu diễn phù hợp với semantics thực tế. Không dùng FunctionCounter để theo dõi một giá trị mà hợp đồng không bảo đảm tính đơn điệu.

### 5.2. Không biến bộ đếm thành giá trị theo cửa sổ

Một API có tên như `hitsLastMinute()` thường trả về số hit trong cửa sổ 1 phút. Giá trị này tăng khi có hit và giảm khi hit cũ ra khỏi cửa sổ. Nó không phải tổng tích lũy và không phù hợp với FunctionCounter.

Nếu cần số hit trong một cửa sổ, hãy dùng Counter tích lũy rồi để backend tính `rate()` hoặc `increase()` trên khoảng truy vấn tương ứng. Nếu cần trạng thái số hit trong cửa sổ do ứng dụng tính sẵn, hãy cân nhắc Gauge và mô tả rõ ý nghĩa của nó.

## 6. Giá trị trả về và chi phí của hàm đọc

FunctionCounter được đọc khi registry thu thập metrics. Hàm đọc nên nhanh, an toàn khi nhiều luồng truy cập và không có tác dụng phụ.

Nên:

- Đọc một biến atomic hoặc bộ đếm tích lũy đã được thư viện quản lý an toàn.
- Dùng getter có chi phí ổn định và không thực hiện I/O.
- Trả về giá trị số tích lũy theo cùng một đơn vị trong suốt vòng đời meter.
- Bảo đảm nguồn dữ liệu tồn tại trong thời gian meter được đăng ký.

Tránh:

- Truy vấn database hoặc gọi HTTP trong hàm đọc.
- Tính lại tổng bằng cách duyệt collection lớn ở mỗi lần scrape.
- Trả về số lượng hiện tại có thể giảm.
- Reset nguồn theo chu kỳ.
- Dùng tag có ID động để phân biệt từng đối tượng.

Nếu getter của thư viện thực hiện đồng bộ hóa hoặc tính toán nặng, hãy xem xét cách thư viện cập nhật thống kê. Có thể cần duy trì snapshot tích lũy nhẹ trong ứng dụng, thay vì gọi getter tốn kém mỗi lần scrape.

### 6.1. Giá trị số và độ chính xác

FunctionCounter đọc giá trị dưới dạng số thực `double`. Với bộ đếm nguyên lớn hơn giới hạn biểu diễn chính xác của `double` (khoảng `2^53`), các số nguyên liên tiếp không còn được biểu diễn chính xác. Với hầu hết bộ đếm ứng dụng thông thường, giới hạn này không phải vấn đề thực tế; với hệ thống có số đếm cực lớn hoặc thời gian chạy rất dài, cần hiểu giới hạn biểu diễn và khả năng của backend.

## 7. Quản lý vòng đời nguồn dữ liệu

FunctionCounter theo dõi một đối tượng nguồn. Hãy bảo đảm đối tượng đó được giữ sống trong thời gian cần thu thập metrics. Nếu nguồn là field của một bean singleton do Spring quản lý, vòng đời thường rõ ràng.

```java
@Component
public class ClientMetrics {
    private final ClientStatistics statistics;

    public ClientMetrics(MeterRegistry registry, ClientStatistics statistics) {
        this.statistics = statistics;

        FunctionCounter.builder(
                        "app.client.completed",
                        this.statistics,
                        ClientStatistics::completedCount)
                .register(registry);
    }
}
```

`ClientStatistics` là một dependency được inject và được giữ trong field. Tránh tạo nguồn dữ liệu tạm thời trong constructor rồi bỏ tham chiếu sau khi đăng ký meter. Micrometer function-tracking meters có thể giữ tham chiếu yếu đến đối tượng được theo dõi; chủ sở hữu ứng dụng nên giữ tham chiếu mạnh để nguồn không bị garbage collector thu hồi ngoài ý muốn.

Nếu nguồn dữ liệu bị thay thế khi reconnect hoặc refresh client, hãy xác định rõ liệu meter có tiếp tục theo dõi cùng một bộ đếm tích lũy hay không. Nếu nguồn mới bắt đầu từ 0 nhưng cùng tên và tag vẫn được xem là cùng chuỗi, đó là một lần reset. Có thể cần quản lý lifecycle và identity meter phù hợp thay vì âm thầm đổi object bên dưới.

## 8. Kiểm thử FunctionCounter với SimpleMeterRegistry

Unit test có thể tạo một nguồn tích lũy giả, đăng ký FunctionCounter và xác minh giá trị được đọc từ nguồn tại thời điểm kiểm tra:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class FunctionCounterTest {
    @Test
    void readsMonotonicallyIncreasingSourceValue() {
        try (var registry = new SimpleMeterRegistry()) {
            AtomicLong source = new AtomicLong(10);

            FunctionCounter counter = FunctionCounter.builder(
                            "app.cache.hits", source, value -> value.get())
                    .register(registry);

            assertThat(counter.count()).isEqualTo(10.0);

            source.addAndGet(5);
            assertThat(counter.count()).isEqualTo(15.0);

            source.addAndGet(2);
            assertThat(counter.count()).isEqualTo(17.0);
        }
    }
}
```

Test xác minh meter đọc giá trị nguồn mới nhất mà không cần gọi phương thức tăng trên FunctionCounter. Nguồn `AtomicLong` chỉ tăng nên đáp ứng hợp đồng đơn điệu.

Có thể bổ sung kiểm thử ở lớp adapter để xác nhận getter của thư viện trả về tổng tích lũy, không phải số lượng hiện tại hoặc số liệu theo cửa sổ. Với nguồn có nhiều luồng cập nhật, hãy dùng kiểu dữ liệu thread-safe mà thư viện hỗ trợ và kiểm tra rằng giá trị không bị giảm ngoài dự kiến.

Không cần viết test chủ động reset nguồn rồi mong FunctionCounter hoạt động như một gauge. Thay vào đó, hãy kiểm tra adapter chỉ sử dụng nguồn có semantics tích lũy và ghi nhận các điều kiện reset của thư viện.

## 9. Đọc FunctionCounter trong Prometheus

Với Prometheus registry, FunctionCounter được xuất như một counter theo quy ước đặt tên của registry. Ví dụ meter `app.cache.hits` có thể xuất thành:

```text
app_cache_hits_total
```

Tên thực tế cần được xác nhận ở endpoint `/actuator/prometheus`, vì naming convention và phiên bản registry có thể ảnh hưởng tên cuối cùng.

Để xem tốc độ tăng trung bình mỗi giây trong 5 phút:

```promql
rate(app_cache_hits_total[5m])
```

Để xem tổng số hit tăng thêm trong 15 phút:

```promql
increase(app_cache_hits_total[15m])
```

`rate()` và `increase()` được thiết kế cho counter tích lũy và có thể xử lý reset counter do tiến trình khởi động lại theo semantics Prometheus. Nếu nguồn giảm vì ứng dụng tự reset trong cùng vòng đời, kết quả vẫn có thể gây khó hiểu; đừng dựa vào khả năng xử lý reset của backend để thay thế hợp đồng đơn điệu của FunctionCounter.

## 10. Những lỗi thường gặp

- **Dùng FunctionCounter cho giá trị có thể giảm:** số request đang xử lý hoặc queue depth phải là Gauge.
- **Dùng FunctionCounter dù không có nguồn tích lũy sẵn:** nếu ứng dụng tự kiểm soát sự kiện, Counter thường rõ ràng hơn.
- **Gọi increment trên FunctionCounter:** meter chỉ đọc nguồn; hãy cập nhật đối tượng nguồn.
- **Dùng getter trả về số liệu trong cửa sổ:** số liệu theo cửa sổ có thể giảm khi mẫu cũ hết hạn.
- **Reset nguồn trong cùng vòng đời:** phá vỡ tính đơn điệu và làm rate/increase khó diễn giải.
- **Không giữ nguồn sống:** nguồn bị thu hồi có thể khiến meter không còn đọc được giá trị mong muốn.
- **Getter thực hiện I/O:** làm chậm scrape và tạo tải phụ lên database hoặc dịch vụ khác.
- **Gắn tag động:** mỗi ID tạo thêm meter identity và làm cardinality tăng nhanh.
- **Nhầm giá trị hiện tại với tổng tích lũy:** tên getter có chữ `count` không bảo đảm nó là counter monotonic.

## 11. Checklist chọn và triển khai FunctionCounter

- [ ] Nguồn dữ liệu đã có một giá trị đếm tích lũy.
- [ ] Giá trị nguồn không giảm trong vòng đời của meter.
- [ ] Getter trả về tổng tích lũy, không phải trạng thái hiện tại hoặc số liệu theo cửa sổ.
- [ ] Nếu ứng dụng tự ghi nhận sự kiện, đã cân nhắc dùng `Counter` trực tiếp.
- [ ] Nguồn dữ liệu được giữ sống bởi bean hoặc chủ sở hữu có vòng đời rõ ràng.
- [ ] Getter nhanh, thread-safe và không thực hiện I/O.
- [ ] Tag có cardinality hữu hạn và ổn định.
- [ ] Hành vi reset khi tiến trình hoặc nguồn khởi động lại đã được hiểu.
- [ ] Unit test xác minh FunctionCounter đọc đúng giá trị nguồn bằng `SimpleMeterRegistry`.
- [ ] Endpoint export và truy vấn backend dùng đúng tên counter thực tế.

`FunctionCounter` phù hợp khi một thành phần khác đã sở hữu tổng sự kiện tích lũy và Micrometer chỉ cần quan sát giá trị đó. Hợp đồng không giảm giúp backend diễn giải số liệu như counter, tính tốc độ tăng và phát hiện reset đúng cách. Nếu giá trị nguồn có thể giảm, hãy chọn `Gauge`; nếu ứng dụng tự kiểm soát sự kiện, hãy cân nhắc `Counter` thông thường.
