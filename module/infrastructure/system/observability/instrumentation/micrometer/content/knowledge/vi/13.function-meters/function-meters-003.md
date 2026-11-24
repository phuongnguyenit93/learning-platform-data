# FunctionTimer theo dõi hàm đếm cùng tổng thời gian tích lũy

## Mục tiêu

Một số thư viện và thành phần hạ tầng đã tự theo dõi số lần thao tác cùng tổng thời gian tiêu tốn. Ví dụ, cache có thể cung cấp tổng số lần get và tổng latency của các lần get; connection pool hoặc client thư viện cũng có thể cung cấp các thống kê tích lũy tương tự.

Nếu ứng dụng đã có một đối tượng giữ hai số liệu này, không nhất thiết phải đo lại từng thao tác bằng Timer. Micrometer có FunctionTimer để đọc hai hàm từ đối tượng trạng thái:

- Hàm đếm trả về tổng số lần sự kiện đã xảy ra.
- Hàm thời gian trả về tổng thời gian tích lũy của tất cả sự kiện.

Micrometer lấy các giá trị này khi registry thu thập hoặc xuất metrics. FunctionTimer không nhận từng lần record() và không tự cộng thời gian vào đối tượng nguồn.

Sau bài này, bạn có thể chọn đúng trường hợp dùng FunctionTimer, đăng ký bằng builder, cung cấp hàm đếm và hàm tổng thời gian, chọn TimeUnit, đọc count/totalTime/mean, hiểu yêu cầu đơn điệu và kiểm thử meter.

## FunctionTimer là gì?

FunctionTimer là một dạng timer theo dõi hai hàm tích lũy:

1. **Count function:** trả về số lần thao tác đã xảy ra từ đầu vòng đời của đối tượng thống kê.
2. **Total time function:** trả về tổng thời gian đã tiêu tốn cho tất cả thao tác đó.

Hai giá trị phải giữ nguyên hoặc tăng theo thời gian. Chúng không được giảm. Micrometer không thể tự bảo đảm điều kiện này; khi đăng ký FunctionTimer, ứng dụng cam kết rằng hai hàm được cung cấp có tính đơn điệu.

Ví dụ một cache đã cung cấp:

- getOperationCount(): tổng số lần đọc cache kể từ khi cache được tạo.
- getTotalGetLatencyNanos(): tổng thời gian của tất cả lần đọc cache, tính bằng nanosecond.

Ta có thể đăng ký một FunctionTimer gắn với đối tượng cache stats đó. Registry sẽ đọc hai giá trị tích lũy và chuyển chúng thành metrics theo quy ước của monitoring backend.

### Khi nào nên dùng?

FunctionTimer phù hợp khi một đối tượng có sẵn đã cung cấp cả:

- Bộ đếm tích lũy của một loại thao tác.
- Tổng thời gian tích lũy của chính loại thao tác đó.

Ví dụ:

- Thống kê get của cache.
- Thống kê request của một HTTP client hoặc database client có sẵn số lần gọi và tổng latency.
- Thống kê thao tác của một thư viện bên thứ ba mà ứng dụng không trực tiếp kiểm soát từng điểm ghi nhận.

Nếu ứng dụng tự sở hữu luồng xử lý và có thể đo từng lần thao tác, Timer thông thường thường dễ hiểu và linh hoạt hơn.

## Đăng ký FunctionTimer bằng builder

API builder nhận tên metric, đối tượng nguồn, hai hàm đọc số liệu và đơn vị thời gian của hàm tổng thời gian:

~~~java
FunctionTimer.builder(
        "cache.gets.latency",
        cacheStats,
        CacheStats::getGetOperationCount,
        CacheStats::getTotalGetLatencyNanos,
        TimeUnit.NANOSECONDS
)
.description("Số lần get cache và tổng thời gian xử lý")
.tags("cache", "products")
.register(registry);
~~~

Các tham số có ý nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| name | Tên metric ổn định |
| obj | Đối tượng giữ trạng thái thống kê tích lũy |
| countFunction | Hàm trả về tổng số lần thao tác |
| totalTimeFunction | Hàm trả về tổng thời gian của các thao tác |
| totalTimeFunctionUnit | Đơn vị của giá trị mà totalTimeFunction trả về |
| description | Mô tả ý nghĩa metric |
| tags | Các chiều phân tích có tập giá trị được kiểm soát |

Ví dụ trên nói rằng getTotalGetLatencyNanos() trả về nanosecond, vì vậy phải truyền TimeUnit.NANOSECONDS. Micrometer chuyển đổi tổng thời gian sang base unit phù hợp với registry khi xuất dữ liệu.

FunctionTimer cũng có thể được đăng ký thông qua API registry.more().timer(...). Builder tĩnh trên FunctionTimer thuận tiện khi cần cấu hình description, tags và đăng ký meter ở một nơi.

## Xây dựng đối tượng thống kê nguồn

Nếu thư viện hiện tại chưa cung cấp thống kê phù hợp, ứng dụng có thể tạo một đối tượng giữ hai giá trị tích lũy. Ví dụ dưới đây dùng LongAdder để cập nhật đồng thời:

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class CacheStats {
    private final LongAdder getOperationCount = new LongAdder();
    private final LongAdder totalGetLatencyNanos = new LongAdder();

    public void recordGet(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("elapsedNanos must be non-negative");
        }

        totalGetLatencyNanos.add(elapsedNanos);
        getOperationCount.increment();
    }

    public long getGetOperationCount() {
        return getOperationCount.sum();
    }

    public double getTotalGetLatencyNanos() {
        return totalGetLatencyNanos.sum();
    }
}
~~~

Mỗi lần cache get hoàn tất, instrumentation gọi recordGet(elapsedNanos). Hai hàm getter chỉ đọc tổng tích lũy:

~~~java
long started = System.nanoTime();
try {
    cache.get(key);
} finally {
    cacheStats.recordGet(System.nanoTime() - started);
}
~~~

Ví dụ này tính cả những lần get kết thúc bằng exception. Nếu metric chỉ được định nghĩa cho thao tác thành công, hãy cập nhật count và total time ở nhánh thành công; điều quan trọng là hai hàm nguồn phải luôn cùng tuân thủ định nghĩa và chỉ tăng theo thời gian.

~~~java
FunctionTimer cacheGetTimer = FunctionTimer
        .builder(
                "cache.gets.latency",
                cacheStats,
                CacheStats::getGetOperationCount,
                CacheStats::getTotalGetLatencyNanos,
                TimeUnit.NANOSECONDS
        )
        .description("Thống kê tích lũy các lần đọc cache")
        .register(registry);
~~~

Trong ứng dụng thật, nếu cache hoặc thư viện đã cung cấp count và total latency, hãy dùng trực tiếp các getter đó. Không tạo thêm bộ đếm thứ hai chỉ để phục vụ FunctionTimer nếu nguồn dữ liệu đã có cùng ý nghĩa.

LongAdder phù hợp với nhiều luồng cập nhật vì giảm tranh chấp khi cộng dồn. Tuy nhiên, việc đọc hai LongAdder là hai lần đọc riêng, không tạo một snapshot nguyên tử của cả cặp giá trị. Khi có cập nhật đồng thời, count và total time có thể phản ánh hai thời điểm rất gần nhau nhưng không hoàn toàn giống nhau. Với dashboard vận hành, sai khác ngắn hạn này thường chấp nhận được; nếu nghiệp vụ yêu cầu snapshot nhất quán tuyệt đối, cần một cơ chế thống kê nguồn cung cấp snapshot đồng bộ.

Các hàm đọc phải nhẹ và nhanh. Chúng được gọi khi registry thu thập metrics, vì vậy không nên thực hiện truy vấn database, gọi HTTP hoặc chờ khóa lâu bên trong các hàm này.

## Đọc count, totalTime và mean

Sau khi đăng ký, FunctionTimer cung cấp các phương thức đọc:

~~~java
double count = cacheGetTimer.count();
double totalSeconds = cacheGetTimer.totalTime(TimeUnit.SECONDS);
double meanMillis = cacheGetTimer.mean(TimeUnit.MILLISECONDS);
~~~

Giả sử cache đã ghi nhận ba lần get:

| Lần get | Thời gian |
|---:|---:|
| 1 | 2 ms |
| 2 | 4 ms |
| 3 | 6 ms |

Các giá trị tích lũy là:

- count = 3.
- totalTime(MILLISECONDS) = 12.
- mean(MILLISECONDS) = 12 / 3 = 4.

count() trả về tổng số lần thao tác; totalTime(unit) trả về tổng thời gian đã tiêu tốn sau khi quy đổi sang đơn vị yêu cầu; mean(unit) là thời gian trung bình mỗi lần thao tác. Nếu count bằng 0, mean được trả về bằng 0.

Đây là số liệu tích lũy do đối tượng nguồn cung cấp. Chúng không phải thời gian của riêng lần gọi gần nhất hay của một cửa sổ ngắn. Backend có thể tính tốc độ thay đổi của count và total time để phân tích trong một khoảng thời gian.

## Điều kiện đơn điệu của hai hàm

Đây là điều kiện quan trọng nhất khi dùng FunctionTimer.

### Count phải không giảm

Hàm đếm phải biểu diễn tổng số lần thao tác từ đầu vòng đời thống kê:

~~~java
long getGetOperationCount() {
    return totalGetCount;
}
~~~

Nếu cache có 100 lần get, sau đó có thêm 20 lần, giá trị phải đi từ 100 lên 120. Không được trả về số lần get trong phút vừa qua nếu giá trị đó có thể giảm về 0 ở phút tiếp theo.

### Total time phải không giảm

Hàm tổng thời gian cũng phải là tổng tích lũy:

~~~java
double getTotalGetLatencyNanos() {
    return totalGetLatencyNanos;
}
~~~

Nếu tổng thời gian đã là 500 ms, các thao tác mới chỉ có thể làm tổng tăng lên, ví dụ 540 ms. Không được trả về latency của request gần nhất hoặc tổng thời gian của cửa sổ vừa kết thúc.

### Không reset đối tượng nguồn trong khi meter còn hoạt động

Một số API thống kê có phương thức reset, clear hoặc tạo lại thống kê khi cache được xóa. Nếu count hoặc total time trở về 0 trong khi FunctionTimer vẫn đăng ký với cùng tên và tags, hợp đồng đơn điệu bị phá vỡ.

Hãy kiểm tra vòng đời của đối tượng nguồn:

- Đối tượng thống kê có bị reset khi clear cache không?
- Số liệu có được khởi tạo lại khi reconnect tới hệ thống bên ngoài không?
- Có thao tác rollover hoặc thay thế đối tượng nguồn không?
- Các getter có trả về số liệu tích lũy từ cùng một mốc bắt đầu không?

Nếu nguồn có thể reset, không nên gắn trực tiếp nó với FunctionTimer trong cùng vòng đời meter. Có thể chọn Timer thông thường để ghi từng lần thao tác, hoặc thiết kế lại ranh giới vòng đời và identity metric theo cách ổn định, có cardinality được kiểm soát.

### Không truyền số nguyên bất biến làm đối tượng nguồn

Không dùng một giá trị long, Long, int hoặc Integer làm obj:

~~~java
// Sai: số nguyên bất biến không thể phản ánh thay đổi theo thời gian.
FunctionTimer.builder(
        "cache.gets.latency",
        Long.valueOf(100),
        value -> value,
        value -> value.doubleValue(),
        TimeUnit.NANOSECONDS
);
~~~

FunctionTimer giữ đối tượng nguồn và gọi các hàm để đọc giá trị hiện tại. Một wrapper số nguyên bất biến không thể tự thay đổi sau khi đăng ký. Hãy truyền một đối tượng thống kê có trạng thái thay đổi theo thời gian hoặc đối tượng thư viện đang quản lý các số liệu tích lũy.

## Phân biệt FunctionTimer với Timer thông thường

Hai meter đều biểu diễn số lần thao tác và tổng thời gian, nhưng cách thu thập dữ liệu khác nhau:

| Tiêu chí | Timer | FunctionTimer |
|---|---|---|
| Nguồn dữ liệu | Mã ứng dụng ghi từng thời lượng | Đọc hai hàm tích lũy từ đối tượng nguồn |
| Ghi nhận | record(), recordCallable(), Sample | Không có thao tác record trên meter |
| Count | Số lần Timer được ghi | Giá trị do count function trả về |
| Tổng thời gian | Timer tự cộng dồn | Giá trị do total time function trả về |
| Histogram/percentile | Có thể cấu hình nếu registry hỗ trợ | Không có phân bố từng mẫu để tạo histogram/percentile |
| Phù hợp khi | Ứng dụng kiểm soát điểm đo | Thư viện đã cung cấp count và tổng thời gian tích lũy |

FunctionTimer chỉ quan sát hai tổng tích lũy. Nó không biết thời lượng của từng lần thao tác, vì vậy không thể tự tính p95, p99 hoặc histogram từ các hàm này. Nếu cần phân vị latency, hãy dùng Timer với histogram phù hợp hoặc lấy phân bố từ hệ thống nguồn có hỗ trợ.

Không đăng ký cả Timer và FunctionTimer cho cùng một thao tác chỉ để đếm hai lần. Chỉ dùng song song khi chúng đo các phạm vi khác nhau hoặc khi có mục đích so sánh rõ ràng.

## Cách registry xuất FunctionTimer

Một lợi ích của FunctionTimer là cho phép từng registry chọn cách biểu diễn phù hợp với monitoring backend.

- Với backend nhận giá trị tích lũy như Prometheus, count và total time thường được xuất thành các chuỗi tích lũy.
- Với một số push registry, Micrometer có thể chuẩn hóa thành tốc độ tăng trong mỗi publishing interval.

Nhờ vậy, mã instrumentation không phải tự tính rate theo cách riêng cho từng backend.

Ví dụ, Prometheus có thể hiển thị một cặp chuỗi count và total time với hậu tố phụ thuộc base unit, chẳng hạn:

~~~text
cache_gets_latency_seconds_count 1200
cache_gets_latency_seconds_sum 3.6
~~~

Tên thực tế phụ thuộc registry, quy tắc chuẩn hóa metric và phiên bản Micrometer. Hãy kiểm tra endpoint export của ứng dụng trước khi viết truy vấn.

Từ các chuỗi tích lũy, PromQL có thể tính throughput:

~~~promql
rate(cache_gets_latency_seconds_count[5m])
~~~

Và latency trung bình trong cửa sổ năm phút:

~~~promql
rate(cache_gets_latency_seconds_sum[5m])
/
rate(cache_gets_latency_seconds_count[5m])
~~~

Nếu có nhiều instance, cần tổng hợp tử số và mẫu số trước khi chia để có mean có trọng số:

~~~promql
sum by (cache) (
  rate(cache_gets_latency_seconds_sum[5m])
)
/
sum by (cache) (
  rate(cache_gets_latency_seconds_count[5m])
)
~~~

Thay metric name và label bằng dữ liệu thật của backend. Với push registry, hãy đọc cách registry chuẩn hóa giá trị theo publishing interval trước khi áp dụng truy vấn dạng rate.

## Kiểm thử FunctionTimer

Có thể dùng SimpleMeterRegistry để kiểm tra meter đọc đúng hai hàm tích lũy:

~~~java
import io.micrometer.core.instrument.FunctionTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class FunctionTimerTest {
    @Test
    void readsCumulativeCountAndTotalTimeFromSource() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            CacheStats stats = new CacheStats();

            FunctionTimer timer = FunctionTimer
                    .builder(
                            "cache.gets.latency",
                            stats,
                            CacheStats::getGetOperationCount,
                            CacheStats::getTotalGetLatencyNanos,
                            TimeUnit.NANOSECONDS
                    )
                    .register(registry);

            stats.recordGet(TimeUnit.MILLISECONDS.toNanos(2));
            stats.recordGet(TimeUnit.MILLISECONDS.toNanos(4));
            stats.recordGet(TimeUnit.MILLISECONDS.toNanos(6));

            assertThat(timer.count()).isEqualTo(3.0);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(12.0);
            assertThat(timer.mean(TimeUnit.MILLISECONDS)).isEqualTo(4.0);
        } finally {
            registry.close();
        }
    }
}
~~~

Test này xác minh rằng meter đọc trạng thái mới nhất từ object sau khi đăng ký. FunctionTimer không cần được gọi record() cho từng thao tác; đối tượng nguồn thay đổi, rồi registry/meter đọc các hàm tích lũy.

Nên bổ sung các kiểm tra sau trong dự án thật:

- Count không giảm khi có thao tác mới.
- Total time không giảm khi có thao tác mới.
- Đơn vị hàm tổng thời gian được khai báo đúng.
- Đối tượng nguồn không bị reset trong vòng đời meter.
- Getter không thực hiện I/O hoặc công việc chậm.
- Tag ổn định và có cardinality hữu hạn.
- Metric export có tên và đơn vị như mong đợi.

## Những lỗi thường gặp

**Trả về số liệu của cửa sổ thay vì số liệu tích lũy.** Count hoặc total time có thể giảm khi cửa sổ trượt. Hãy dùng tổng tích lũy từ cùng một mốc bắt đầu.

**Dùng nguồn có thể reset.** Khi cache clear hoặc client reconnect làm số liệu trở về 0, meter đã đăng ký sẽ không còn tuân thủ hợp đồng đơn điệu.

**Nhầm totalTimeFunctionUnit.** Nếu hàm trả nanosecond nhưng khai báo MILLISECONDS, Micrometer quy đổi sai tổng thời gian. Đơn vị phải mô tả đúng dữ liệu trả về.

**Dùng đối tượng số bất biến.** Long hoặc Integer không tự cập nhật sau khi đăng ký. Truyền state object có getter đọc giá trị tích lũy.

**Kỳ vọng có percentile hoặc histogram.** FunctionTimer chỉ có count và total time, không lưu từng observation. Dùng Timer nếu cần phân bố latency.

**Đặt công việc nặng trong getter.** Getter được gọi khi registry thu thập metrics. Không gọi database hoặc dịch vụ mạng từ count function hay total time function.

**Dùng tag không ổn định.** Không gắn request ID, cache entry ID hoặc dữ liệu người dùng vào tag. Dùng tên cache, loại thao tác hoặc nhóm có tập giá trị hữu hạn.

## Checklist đưa FunctionTimer vào ứng dụng

1. Đối tượng nguồn đã có count tích lũy và tổng thời gian tích lũy.
2. Cả hai hàm không bao giờ giảm trong vòng đời meter.
3. Đơn vị trả về của total time function khớp TimeUnit truyền vào builder.
4. Đối tượng nguồn có vòng đời đủ dài và không bị reset ngoài dự kiến.
5. Getter nhanh, không thực hiện I/O và an toàn khi được gọi đồng thời với cập nhật.
6. Dùng FunctionTimer.builder(...) để đăng ký đúng object và hai hàm.
7. Không dùng FunctionTimer nếu cần histogram, max hoặc percentile từ từng mẫu.
8. Tag có cardinality hữu hạn.
9. Kiểm thử count, totalTime, mean và tính đơn điệu.
10. Kiểm tra dữ liệu export và cách backend chuẩn hóa cumulative value hoặc rate.

## Kết luận

FunctionTimer là lựa chọn phù hợp khi một đối tượng nguồn đã giữ sẵn hai số liệu tích lũy: số lần thao tác và tổng thời gian đã tiêu tốn. Micrometer đọc hai hàm này khi registry thu thập metrics, rồi để registry quyết định cách xuất theo backend. Để dữ liệu đáng tin cậy, count và total time phải đơn điệu, không bị reset trong vòng đời meter, hàm tổng thời gian phải khai báo đúng đơn vị và getter phải nhẹ. Nếu cần ghi từng lần thao tác hoặc phân tích histogram/percentile, hãy dùng Timer thông thường.

## Tài liệu tham khảo

- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): phần Function-tracking Timers, builder và yêu cầu hai hàm tích lũy đơn điệu.
- [Micrometer - FunctionTimer API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/FunctionTimer.html): chữ ký builder, count, totalTime, mean và baseTimeUnit.
- [Micrometer - MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html): đăng ký function timer và vai trò của đối tượng nguồn.
