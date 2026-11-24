# Phân biệt đọc số tích lũy có sẵn với gọi increment hoặc record trực tiếp

Không phải ứng dụng nào cũng cần tự gọi `increment()` hoặc `record(...)` mỗi khi có sự kiện. Một số thư viện và thành phần đã duy trì số liệu tích lũy của chúng, chẳng hạn tổng số lần cache được truy cập hoặc tổng thời gian xử lý đã hoàn tất. Nếu có thể đọc các giá trị tích lũy đó, Micrometer cung cấp Function meter để lấy số liệu từ một hàm thay vì cập nhật meter bằng từng sự kiện.

`FunctionCounter` đọc một giá trị đếm tích lũy, còn `FunctionTimer` đọc số lần thực hiện và tổng thời gian tích lũy. Registry gọi các hàm này khi cần quan sát meter. Khác với `Counter` và `Timer` chủ động, mã instrumentation không gọi `increment()` hoặc `record(...)` cho từng sự kiện; nó cung cấp một nguồn dữ liệu đã được cập nhật ở nơi khác.

Điểm quyết định là giá trị nguồn phải có ngữ nghĩa tích lũy và đơn điệu. Nếu nguồn giảm về 0, thay đổi theo trạng thái hiện tại hoặc bị reset trong khi meter vẫn được xuất, backend có thể diễn giải sai tốc độ và tổng số.

## Hai cách ghi nhận số liệu

Micrometer có thể nhận số đo theo hai cách:

1. **Cập nhật trực tiếp:** ứng dụng gọi `Counter.increment()` hoặc `Timer.record(...)` đúng lúc sự kiện xảy ra. Meter tự tích lũy các lần cập nhật.
2. **Đọc số tích lũy:** ứng dụng đăng ký `FunctionCounter` hoặc `FunctionTimer` với một đối tượng và hàm đọc giá trị mà đối tượng đó đã tích lũy. Registry lấy giá trị hiện tại khi quan sát meter.

| Nhu cầu | Meter chủ động | Function meter |
|---|---|---|
| Đếm sự kiện | `Counter.increment()` | `FunctionCounter` đọc tổng số đã tích lũy |
| Đo số lần và tổng thời gian | `Timer.record(...)` | `FunctionTimer` đọc count và total time đã tích lũy |
| Ai cập nhật dữ liệu? | Mã instrumentation cập nhật meter | Thành phần sở hữu trạng thái cập nhật dữ liệu; Micrometer chỉ đọc |
| Khi nào số liệu được lấy? | Khi sự kiện gọi API ghi nhận | Khi registry hoặc backend quan sát meter |
| Có thể ghi nhận từng observation để tạo phân phối? | `Timer` hỗ trợ histogram/percentile theo cấu hình | FunctionTimer chỉ cung cấp count và total time, không tái tạo các observation riêng lẻ |

Hãy dùng meter chủ động khi ứng dụng kiểm soát điểm xảy ra sự kiện và cần ghi nhận từng lần. Function meter phù hợp khi một thư viện đã duy trì số tích lũy đáng tin cậy và cung cấp API đọc chúng.

## FunctionCounter đọc một counter tích lũy

`FunctionCounter` lấy một hàm trả về số lượng tích lũy từ một đối tượng. Ví dụ, một bộ đếm cache nội bộ đã duy trì tổng số lần hit bằng `LongAdder`:

```java
import java.util.concurrent.atomic.LongAdder;

public class CacheStatistics {
    private final LongAdder hits = new LongAdder();

    public void recordHit() {
        hits.increment();
    }

    public double hitCount() {
        return hits.sum();
    }
}
```

Đăng ký nguồn tích lũy đó với Micrometer:

```java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;

public class CacheMetrics {
    public CacheMetrics(MeterRegistry registry, CacheStatistics statistics) {
        FunctionCounter.builder(
                        "cache.hits",
                        statistics,
                        CacheStatistics::hitCount)
                .description("Tổng số lần cache hit")
                .register(registry);
    }
}
```

Trong ví dụ, `CacheStatistics` là nơi duy nhất cập nhật số hit. `FunctionCounter` chỉ đọc `hitCount()` khi registry quan sát meter. Không gọi thêm `registry.counter("cache.hits").increment()` cho cùng các hit đó, vì như vậy sẽ tạo một nguồn đếm thứ hai và dễ dẫn đến số liệu không nhất quán hoặc đếm trùng.

Giá trị trả về của hàm phải là tổng tích lũy không giảm trong vòng đời của meter. `LongAdder.sum()` phù hợp nếu chỉ tăng và không gọi `reset()`. Không dùng số lượng entry cache hiện tại, số request đang hoạt động hoặc độ dài hàng đợi làm FunctionCounter; các đại lượng có thể tăng và giảm đó phù hợp với `Gauge`.

Hàm đọc cần nhanh, không có side effect và an toàn khi được gọi đồng thời. Không thực hiện I/O, truy vấn database hoặc tăng bộ đếm bên trong hàm đọc. Registry có thể lấy số đo nhiều lần trong suốt vòng đời ứng dụng; getter chỉ nên trả về trạng thái tích lũy đã có.

## FunctionTimer đọc count và total time có sẵn

Một số thư viện đã lưu tổng số lần hoàn tất và tổng thời gian thực hiện. Nếu hai giá trị này được duy trì trong cùng một đối tượng, có thể đăng ký `FunctionTimer`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public class JobStatistics {
    private final LongAdder completed = new LongAdder();
    private final LongAdder totalNanos = new LongAdder();

    public void recordCompletion(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("Thời lượng không được âm");
        }
        completed.increment();
        totalNanos.add(elapsedNanos);
    }

    public long completedCount() {
        return completed.sum();
    }

    public double totalTimeNanos() {
        return totalNanos.sum();
    }
}
```

Đăng ký FunctionTimer với đơn vị của hàm tổng thời gian:

```java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.FunctionTimer;
import io.micrometer.core.instrument.MeterRegistry;

public class JobMetrics {
    public JobMetrics(MeterRegistry registry, JobStatistics statistics) {
        FunctionTimer.builder(
                        "jobs.execution",
                        statistics,
                        JobStatistics::completedCount,
                        JobStatistics::totalTimeNanos,
                        TimeUnit.NANOSECONDS)
                .description("Số lần hoàn tất và tổng thời gian thực thi job")
                .register(registry);
    }
}
```

`FunctionTimer` đọc hai đại lượng: số lần hoàn tất và tổng thời gian hoàn tất. `TimeUnit.NANOSECONDS` cho Micrometer biết giá trị do `totalTimeNanos()` trả về đang dùng đơn vị nanosecond để chuyển đổi phù hợp khi xuất dữ liệu. Hàm count phải trả về số lần tích lũy; hàm total time phải trả về tổng thời gian tích lũy theo đơn vị đã khai báo.

Hai giá trị này cần phản ánh cùng một tập sự kiện. Ví dụ chỉ tăng `completed` khi một job hoàn tất và cộng đúng thời lượng của chính lần hoàn tất đó vào `totalNanos`. Nếu count tính cả job thất bại nhưng total time chỉ tính job thành công, mean suy ra từ total/count sẽ không còn mô tả đúng một tập quan sát.

Khi nhiều luồng cập nhật đồng thời, hai hàm đọc có thể được gọi ở hai thời điểm rất gần nhau. Một lần scrape có thể nhìn thấy count vừa tăng nhưng total time chưa được cập nhật, hoặc ngược lại, tùy thứ tự cập nhật nguồn. Sai khác ngắn hạn này thường được chấp nhận với metric vận hành; nếu cần một snapshot nhất quán tuyệt đối, nguồn dữ liệu phải cung cấp cơ chế snapshot đồng bộ và việc đọc count cùng total phải dựa trên cùng snapshot đó.

## Backend suy ra tốc độ và thời gian trung bình

Function meter không phát một sự kiện mới mỗi khi hàm đọc được gọi. Nó cung cấp giá trị tích lũy hiện tại để backend lưu thành chuỗi thời gian. Từ các điểm lấy mẫu theo thời gian, backend có thể tính tốc độ tăng hoặc mức thay đổi trong một cửa sổ.

Với FunctionCounter, nếu tổng hit lần lượt là 1.000, 1.050 và 1.130 ở các lần scrape, backend có thể suy ra số hit mỗi giây trong các khoảng tương ứng. Khi ứng dụng khởi động lại và counter nguồn quay về 0, backend có thể xử lý reset nếu metric được biểu diễn đúng là counter.

Với FunctionTimer, backend có thể lấy tốc độ tăng của count và total time. Thời gian trung bình trong một cửa sổ được suy ra bằng:

\[
\text{mean duration} =
\frac{\text{rate of total time}}{\text{rate of count}}
\]

Ví dụ PromQL minh họa khi registry xuất timer theo quy ước Prometheus:

```promql
sum by (service) (
  rate(jobs_execution_seconds_sum[5m])
)
/
sum by (service) (
  rate(jobs_execution_seconds_count[5m])
)
```

Tên metric cụ thể phụ thuộc tên meter và quy tắc chuẩn hóa của registry. Truy vấn chia tốc độ tăng tổng thời gian cho tốc độ tăng số lần hoàn tất trong cùng cửa sổ, tạo ra thời gian trung bình mỗi lần hoàn tất. Cần xử lý trường hợp count không tăng trong cửa sổ để tránh diễn giải phép chia không xác định.

## Không dùng FunctionCounter cho giá trị tức thời

FunctionCounter mang ngữ nghĩa counter tích lũy, do đó giá trị nguồn không được giảm. Những số liệu dưới đây không phù hợp:

```java
// Sai ngữ nghĩa cho FunctionCounter: số entry có thể tăng và giảm.
FunctionCounter.builder("cache.entries", cache, c -> c.size())
        .register(registry);
```

Số entry hiện tại là trạng thái tại thời điểm đọc. Dùng `Gauge` để biểu diễn:

```java
Gauge.builder("cache.entries", cache, c -> c.size())
        .register(registry);
```

Tương tự, số kết nối đang mở, số tác vụ đang chờ và dung lượng hàng đợi hiện tại là các đại lượng có thể tăng hoặc giảm, nên dùng `Gauge`. Số lần request đã nhận, số lần retry đã thực hiện hoặc tổng số message đã xử lý là các đại lượng tích lũy, có thể phù hợp với Counter hoặc FunctionCounter tùy nơi sở hữu dữ liệu.

## Không reset hoặc thay thế nguồn tích lũy tùy tiện

Nếu nguồn của FunctionCounter bị reset về 0 trong khi meter vẫn tồn tại, chuỗi thời gian giảm đột ngột. Backend có thể hiểu đó là counter reset do tiến trình khởi động lại, mặc dù thực tế ứng dụng chỉ reset thống kê. Nếu nguồn bị thay bằng đối tượng mới, meter có thể đọc một giá trị thấp hơn trước đó hoặc không còn phản ánh cùng vòng đời.

Các quy tắc cần giữ:

1. Không gọi `reset()` trên bộ đếm nguồn khi meter còn được xuất.
2. Không tái sử dụng cùng meter name và tag cho nhiều nguồn có vòng đời tích lũy khác nhau.
3. Nếu cần bắt đầu một chu kỳ mới, thể hiện chu kỳ đó bằng một định danh có vòng đời được kiểm soát hoặc tạo metric mới theo thiết kế rõ ràng; không đưa ID ngẫu nhiên vào tag.
4. Nếu thư viện chỉ cung cấp giá trị tức thời hoặc bộ đếm có thể reset định kỳ, chọn `Gauge` hoặc chuyển đổi sang meter chủ động phù hợp với ngữ nghĩa.
5. Khi ứng dụng khởi động lại, hiểu rằng bộ nhớ tích lũy trong JVM có thể bắt đầu lại; backend cần tính toán counter theo từng chuỗi và xử lý reset đúng cách.

Không cố làm cho FunctionCounter tăng bằng cách trả về `Math.max(previous, current)` hoặc giữ một biến phụ chỉ để che reset. Cách đó tạo ra số liệu giả và có thể che giấu lỗi trong nguồn dữ liệu. Hãy sửa vòng đời nguồn hoặc chọn đúng loại meter.

## Chọn giữa Counter, Timer và Function meter

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Ứng dụng tự kiểm soát sự kiện đơn hàng được tạo | `Counter` | Gọi `increment()` đúng tại điểm sự kiện xảy ra |
| Thư viện cache đã có tổng hit đơn điệu | `FunctionCounter` | Đọc tổng có sẵn, tránh cập nhật song song hai bộ đếm |
| Ứng dụng cần histogram và percentile của từng lần xử lý | `Timer` | Ghi nhận mỗi observation và cấu hình phân phối |
| Thư viện đã có count và total duration tích lũy | `FunctionTimer` | Đọc hai giá trị có sẵn để backend suy ra mean và rate |
| Số tác vụ đang chạy hoặc kích thước cache hiện tại | `Gauge` | Giá trị có thể tăng và giảm |

FunctionTimer không có dữ liệu thời lượng riêng của từng observation. Vì vậy không thể suy ra p95, p99 hoặc histogram chính xác chỉ từ count và total time. Nếu cần phân phối hoặc percentile, phải ghi nhận từng lần bằng `Timer`, hoặc dùng histogram mà nguồn dữ liệu cung cấp.

## Kiểm thử Function meter

Có thể dùng `SimpleMeterRegistry` và một nguồn tích lũy nhỏ để kiểm tra meter đọc đúng giá trị:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.LongAdder;

import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class FunctionCounterTest {
    @Test
    void readsExistingMonotonicCount() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LongAdder source = new LongAdder();

        FunctionCounter counter = FunctionCounter.builder(
                        "test.events", source, LongAdder::sum)
                .register(registry);

        assertThat(counter.count()).isZero();

        source.add(3);
        assertThat(counter.count()).isEqualTo(3.0);

        source.add(2);
        assertThat(counter.count()).isEqualTo(5.0);

        registry.close();
    }
}
```

Test không gọi `increment()` trên FunctionCounter. Nó cập nhật nguồn dữ liệu rồi đọc lại meter để xác nhận FunctionCounter phản ánh giá trị tích lũy hiện tại. Với FunctionTimer, kiểm tra count và total time cùng tăng theo một lần hoàn tất, đồng thời xác nhận đơn vị thời gian được khai báo đúng.

Ngoài unit test, hãy kiểm tra dữ liệu tại exporter/backend để xác nhận metric được biểu diễn với loại counter hoặc timer phù hợp. `SimpleMeterRegistry` xác minh hành vi đọc trong JVM nhưng không chứng minh backend đã scrape đúng, xử lý reset đúng hoặc áp dụng đúng đơn vị.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| FunctionCounter giảm về 0 | Nguồn bị reset hoặc thay bằng đối tượng mới | Giữ nguồn tích lũy đơn điệu trong vòng đời meter |
| Counter bị đếm gấp đôi | Vừa cập nhật meter chủ động vừa đọc cùng nguồn qua FunctionCounter | Chọn một nguồn ghi nhận duy nhất |
| FunctionCounter luôn bằng 0 | Hàm đọc sai đối tượng hoặc nguồn chưa được cập nhật | Kiểm tra hàm đọc và nơi cập nhật dữ liệu gốc |
| Mean của FunctionTimer sai | Count và total time đại diện cho hai tập sự kiện khác nhau hoặc sai đơn vị | Đồng bộ điều kiện cập nhật và khai báo `TimeUnit` chính xác |
| Không có p95 hoặc p99 | FunctionTimer chỉ cung cấp count và total time | Dùng Timer hoặc histogram có dữ liệu phân phối |
| Dùng FunctionCounter cho queue size | Giá trị queue có thể giảm | Dùng Gauge cho trạng thái hiện tại |

## Checklist triển khai

- [ ] Nguồn dữ liệu đã có sẵn số tích lũy và có API đọc nhanh, an toàn khi truy cập đồng thời.
- [ ] FunctionCounter chỉ đọc giá trị đơn điệu không giảm.
- [ ] FunctionTimer đọc count và total time của cùng tập lần thực hiện.
- [ ] Đơn vị của hàm total time được khai báo chính xác.
- [ ] Meter được đăng ký một lần và không bị cập nhật trùng bằng API chủ động.
- [ ] Không reset nguồn khi meter còn được xuất.
- [ ] Giá trị tức thời hoặc có thể giảm được biểu diễn bằng Gauge.
- [ ] Dùng Timer hoặc histogram riêng nếu cần percentile và phân phối.
- [ ] Unit test xác nhận meter đọc lại số liệu nguồn chính xác.
- [ ] Integration test xác minh exporter và backend nhận đúng kiểu metric, đơn vị và hành vi reset.

Function meter là cầu nối giữa dữ liệu tích lũy mà thành phần khác đã sở hữu và hệ thống quan sát Micrometer. `FunctionCounter` đọc tổng số đơn điệu; `FunctionTimer` đọc số lần và tổng thời gian. Khi chọn đúng nguồn, đúng đơn vị và đúng vòng đời, ứng dụng có thể xuất số liệu có sẵn mà không phải ghi nhận lại từng sự kiện. Khi cần cập nhật trực tiếp hoặc phân tích từng observation, hãy dùng `Counter` và `Timer` chủ động.
