# Khai báo đơn vị thời gian đầu vào và chuyển đổi theo registry

Function-tracking timer của Micrometer phù hợp khi một đối tượng hoặc thư viện đã tự duy trì số lần thao tác và tổng thời gian tích lũy. Thay vì gọi record() cho từng sự kiện, ứng dụng cung cấp hai hàm để Micrometer đọc: hàm lấy count và hàm lấy tổng thời gian. Với FunctionTimer, bạn còn phải khai báo đơn vị thời gian mà hàm tổng thời gian trả về.

Đơn vị đầu vào này rất quan trọng. Một thư viện có thể trả tổng thời gian bằng nanosecond, microsecond hoặc millisecond, trong khi registry đích có quy ước đơn vị riêng. Micrometer dùng TimeUnit được khai báo để chuyển tổng thời gian sang base time unit của registry khi export. Nhờ đó cùng một instrumentation có thể làm việc với nhiều registry mà không phải tự viết phép đổi đơn vị cho từng backend.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích FunctionTimer đọc hai hàm tích lũy từ một đối tượng.
- Khai báo đúng TimeUnit cho giá trị tổng thời gian đầu vào.
- Hiểu cách registry chuyển dữ liệu sang base time unit của nó.
- Đọc count, totalTime, mean và baseTimeUnit.
- Bảo đảm count và total time là các giá trị tích lũy không giảm.
- Phân biệt FunctionTimer với Timer và FunctionCounter.

## FunctionTimer hoạt động như thế nào?

FunctionTimer theo dõi hai hàm đơn điệu (monotonic):

- **Count function:** trả về tổng số lần sự kiện đã xảy ra.
- **Total time function:** trả về tổng thời gian đã tiêu tốn cho các sự kiện đó.

Micrometer không nhận từng sự kiện riêng lẻ. Khi registry thu thập hoặc export metrics, implementation đọc các hàm này từ đối tượng nguồn và công bố các giá trị tích lũy. Backend có thể dùng mức tăng của count và total time trong một khoảng để tính throughput và độ trễ trung bình.

~~~mermaid
flowchart TD
    A[Đối tượng nguồn] --> B[Count function]
    A --> C[Total time function]
    B --> D[FunctionTimer]
    C --> D
    E[TimeUnit của tổng thời gian đầu vào] --> D
    D --> F[Chuyển đổi sang base time unit của registry]
    F --> G[Registry export metrics]
    G --> H[Backend tính rate và mean latency]
~~~

Khác với Timer thông thường, FunctionTimer không bao quanh một đoạn mã để tự bấm giờ. Nó quan sát các số liệu tích lũy đã có sẵn trong đối tượng nguồn. Đây là lựa chọn phù hợp khi tích hợp với cache, client hoặc thư viện đã cung cấp sẵn số lần thao tác và tổng thời gian.

## Khai báo đơn vị của hàm tổng thời gian

Builder của FunctionTimer nhận năm đối số quan trọng:

~~~java
FunctionTimer.builder(
    "cache.gets.latency",
    cacheStats,
    CacheStats::getGetOperationCount,
    CacheStats::getTotalGetLatency,
    TimeUnit.MILLISECONDS
).register(registry);
~~~

Đối số cuối cùng là đơn vị của giá trị do getTotalGetLatency() trả về. Nếu hàm đó trả tổng millisecond, khai báo MILLISECONDS. Nếu trả tổng nanosecond, khai báo NANOSECONDS. Micrometer cần thông tin này để diễn giải đúng con số và chuyển nó sang đơn vị cơ sở của registry.

Đây không phải đơn vị mà backend bắt buộc phải nhận. Đơn vị đầu vào mô tả dữ liệu nguồn; đơn vị export do registry quyết định. Ví dụ, một registry có base time unit là seconds sẽ chuyển tổng millisecond thành seconds trước khi công bố.

### Ví dụ chuyển đổi

Giả sử đối tượng nguồn trả về tổng thời gian là 2.500 millisecond:

| Đại lượng | Giá trị |
|---|---:|
| Hàm nguồn trả về | 2.500 |
| TimeUnit đầu vào khai báo | MILLISECONDS |
| Base time unit registry ví dụ | SECONDS |
| Giá trị sau chuyển đổi | 2,5 seconds |

Nếu khai báo nhầm SECONDS trong khi hàm nguồn thực tế trả millisecond, Micrometer sẽ hiểu 2.500 là 2.500 giây. Kết quả export sai lệch 1.000 lần. Ngược lại, nếu nguồn trả nanosecond nhưng khai báo millisecond, tổng thời gian cũng bị diễn giải sai. Vì vậy TimeUnit phải mô tả đúng đơn vị thực tế của hàm nguồn, không phải đơn vị bạn muốn thấy trên dashboard.

## Ví dụ Java hoàn chỉnh

Giả sử lớp thống kê cache đã đếm số lần get và tổng thời gian xử lý. Lớp này giữ các giá trị tích lũy bằng AtomicLong:

~~~java
package example;

import java.util.concurrent.atomic.AtomicLong;

public class CacheStats {
    private final AtomicLong getOperationCount = new AtomicLong();
    private final AtomicLong totalGetLatencyMillis = new AtomicLong();

    public void recordGet(long elapsedMillis) {
        if (elapsedMillis < 0) {
            throw new IllegalArgumentException("elapsedMillis must be non-negative");
        }

        totalGetLatencyMillis.addAndGet(elapsedMillis);
        getOperationCount.incrementAndGet();
    }

    public long getGetOperationCount() {
        return getOperationCount.get();
    }

    public double getTotalGetLatency() {
        return totalGetLatencyMillis.get();
    }
}
~~~

Đăng ký FunctionTimer và chỉ rõ rằng hàm tổng thời gian trả về millisecond:

~~~java
package example;

import io.micrometer.core.instrument.FunctionTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.TimeUnit;

public class FunctionTimerDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();
        CacheStats cacheStats = new CacheStats();

        try {
            // Giả lập cache đã xử lý ba thao tác get.
            cacheStats.recordGet(20);
            cacheStats.recordGet(40);
            cacheStats.recordGet(60);

            FunctionTimer cacheGets = FunctionTimer.builder(
                    "cache.gets.latency",
                    cacheStats,
                    CacheStats::getGetOperationCount,
                    CacheStats::getTotalGetLatency,
                    TimeUnit.MILLISECONDS
                )
                .description("Số lần get và tổng thời gian get của cache")
                .tag("cache", "products")
                .register(registry);

            System.out.println("Count: " + cacheGets.count());
            System.out.println(
                "Total (ms): " + cacheGets.totalTime(TimeUnit.MILLISECONDS)
            );
            System.out.println(
                "Total (seconds): " + cacheGets.totalTime(TimeUnit.SECONDS)
            );
            System.out.println(
                "Mean (ms): " + cacheGets.mean(TimeUnit.MILLISECONDS)
            );
            System.out.println("Registry unit: " + cacheGets.baseTimeUnit());
        } finally {
            registry.close();
        }
    }
}
~~~

Ba lần get có thời lượng 20, 40 và 60 millisecond. Vì vậy count bằng 3, tổng thời gian bằng 120 millisecond và mean bằng 40 millisecond. Khi đọc cùng tổng thời gian bằng SECONDS, kết quả là 0,12 giây.

SimpleMeterRegistry được dùng để minh họa API và cách đọc. Base time unit có thể khác nhau giữa các registry; hãy xem cacheGets.baseTimeUnit() hoặc tài liệu registry cụ thể thay vì giả định mọi backend đều dùng seconds.

## Registry chuyển đổi đơn vị như thế nào?

FunctionTimer nhận TimeUnit của totalTimeFunction. Registry cũng có một base time unit riêng, được implementation chọn theo hệ thống nhận dữ liệu. Khi tạo FunctionTimer, Micrometer giữ đơn vị nguồn và chuyển giá trị tổng thời gian sang base time unit của registry.

Khi gọi totalTime(unit), bạn có thể yêu cầu đọc tổng thời gian ở đơn vị khác:

~~~java
double millis = cacheGets.totalTime(TimeUnit.MILLISECONDS);
double seconds = cacheGets.totalTime(TimeUnit.SECONDS);
double nanos = cacheGets.totalTime(TimeUnit.NANOSECONDS);
~~~

Phương thức baseTimeUnit() cho biết đơn vị cơ sở của timer mà registry dùng để công bố metrics. Đây là cách kiểm tra implementation đang sử dụng đơn vị nào:

~~~java
TimeUnit exportUnit = cacheGets.baseTimeUnit();
System.out.println("FunctionTimer base unit: " + exportUnit);
~~~

Trong code nghiệp vụ, không cần tự chuyển đổi hàm nguồn sang base time unit của từng registry. Hãy trả về một đơn vị ổn định từ thư viện nguồn và khai báo đúng TimeUnit; Micrometer đảm nhiệm phần chuyển đổi.

## Ý nghĩa của count, total time và mean

FunctionTimer cung cấp các thống kê chính:

| API | Ý nghĩa |
|---|---|
| count() | Tổng số lần sự kiện theo hàm count nguồn |
| totalTime(unit) | Tổng thời gian theo đơn vị được yêu cầu |
| mean(unit) | Tổng thời gian chia cho count, theo đơn vị được yêu cầu |
| baseTimeUnit() | Đơn vị thời gian cơ sở mà registry dùng để export |

Mean là thời gian trung bình trên toàn bộ sự kiện được tính trong các hàm nguồn. Ví dụ count là 100 và total time là 2.000 millisecond thì mean là 20 millisecond.

FunctionTimer thường được export thành hai chuỗi tích lũy tương ứng count và total time. Backend có thể tính tốc độ tăng của mỗi chuỗi trong cùng một cửa sổ. Tỷ lệ giữa tốc độ tăng tổng thời gian và tốc độ tăng count cho độ trễ trung bình trong cửa sổ đó.

## Truy vấn với Prometheus

Khi dùng registry Prometheus, timer function thường được biểu diễn bằng các chuỗi count và sum với đơn vị thời gian của Prometheus. Ví dụ minh họa:

~~~text
cache_gets_latency_seconds_count{cache="products"} 300
cache_gets_latency_seconds_sum{cache="products"} 12.0
~~~

Throughput get trung bình trong năm phút:

~~~promql
rate(cache_gets_latency_seconds_count[5m])
~~~

Độ trễ trung bình trong cùng cửa sổ:

~~~promql
rate(cache_gets_latency_seconds_sum[5m])
/
rate(cache_gets_latency_seconds_count[5m])
~~~

Đơn vị của sum trong ví dụ là seconds, do đó kết quả phép chia cũng là seconds mỗi sự kiện. Có thể nhân 1.000 để hiển thị millisecond. Tên metric cụ thể phụ thuộc quy tắc đặt tên và phiên bản registry; hãy kiểm tra endpoint export của ứng dụng.

FunctionTimer cho phép backend tính throughput và mean latency từ hai hàm tích lũy. Nó không giữ từng sample riêng lẻ nên không cung cấp histogram bucket hoặc percentile p95/p99 như một Timer được cấu hình phân phối. Nếu cần phân tích đuôi độ trễ, hãy dùng Timer thông thường hoặc instrumentation hỗ trợ histogram.

## Yêu cầu về tính đơn điệu và vòng đời đối tượng

Micrometer không thể bảo đảm count function và total time function luôn tăng. Khi đăng ký FunctionTimer, ứng dụng cam kết hai hàm này là đơn điệu: giá trị giữ nguyên hoặc tăng, không giảm.

Các điều kiện cần đáp ứng:

- Count là số sự kiện tích lũy từ đầu vòng đời thống kê của đối tượng.
- Total time là tổng thời gian tích lũy cùng phạm vi sự kiện đó.
- Không reset hai giá trị về 0 trong khi FunctionTimer vẫn đang được registry giữ.
- Không dùng giá trị snapshot tạm thời hoặc giá trị chỉ đại diện cho một cửa sổ nếu nó có thể giảm.
- Các hàm đọc phải nhẹ, an toàn khi được gọi lặp lại và không có side effect.

Nếu thư viện nguồn reset thống kê khi clear cache hoặc đổi epoch, FunctionTimer có thể thấy giá trị giảm. Khi đó backend có thể hiểu sai mức tăng hoặc tốc độ. Hãy chọn nguồn số liệu tích lũy không reset, hoặc quản lý vòng đời meter và đối tượng sao cho mỗi chuỗi dữ liệu có một vòng đời nhất quán.

Đối tượng nguồn phải tiếp tục tồn tại và cập nhật trong khi timer được sử dụng. Không truyền một số nguyên hoặc đối tượng wrapper bất biến làm nguồn, vì giá trị đó không thể thay đổi. Cũng không nên tạo đối tượng mới rồi đăng ký lại cùng tên và tag với kỳ vọng registry thay thế nguồn cũ; registry duy trì một meter cho mỗi tổ hợp tên và tag.

Với dữ liệu cập nhật đồng thời, hãy dùng bộ đếm và bộ tích lũy thread-safe. Nếu count và total time được đọc riêng lẻ, một lần scrape có thể nhìn thấy hai giá trị ở hai thời điểm rất gần nhau. Với metrics vận hành, sai khác nhỏ này thường chấp nhận được; nếu cần snapshot nhất quán tuyệt đối, nguồn dữ liệu cần cung cấp cơ chế snapshot phù hợp.

## Chọn FunctionTimer hay Timer?

| Tiêu chí | FunctionTimer | Timer |
|---|---|---|
| Nguồn dữ liệu | Hai hàm tích lũy từ đối tượng có sẵn | Ứng dụng ghi nhận từng lần thao tác |
| Ghi nhận | Registry đọc các hàm khi thu thập | Gọi record hoặc sample khi thao tác diễn ra |
| Count và total time | Có | Có |
| Histogram và percentile | Không phải mục đích của FunctionTimer | Có thể cấu hình |
| Phù hợp | Tích hợp thư viện đã có count và tổng thời gian | Đo thao tác do ứng dụng kiểm soát |

Nếu cache client đã cung cấp tổng số get và tổng latency, FunctionTimer tránh phải thêm một lần record cho từng thao tác. Nếu bạn tự kiểm soát code xử lý và cần histogram, p95 hoặc SLO, Timer thường phù hợp hơn.

FunctionCounter là lựa chọn tương tự khi nguồn chỉ có một hàm count tích lũy và không có tổng thời gian. TimeGauge lại dành cho một giá trị thời gian hiện tại, chẳng hạn thời gian một lease còn hiệu lực; nó không phải bộ đếm thời lượng tích lũy của nhiều sự kiện.

## Kiểm thử đơn vị thời gian

Có thể kiểm thử việc khai báo đơn vị đầu vào bằng SimpleMeterRegistry. Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
CacheStats stats = new CacheStats();
stats.recordGet(500);
stats.recordGet(1_500);

FunctionTimer timer = FunctionTimer.builder(
        "cache.gets.latency",
        stats,
        CacheStats::getGetOperationCount,
        CacheStats::getTotalGetLatency,
        TimeUnit.MILLISECONDS
    )
    .register(registry);

assertEquals(2.0, timer.count());
assertEquals(2_000.0, timer.totalTime(TimeUnit.MILLISECONDS));
assertEquals(2.0, timer.totalTime(TimeUnit.SECONDS));
assertEquals(1_000.0, timer.mean(TimeUnit.MILLISECONDS));

registry.close();
~~~

Bộ kiểm thử này xác nhận tổng thời gian đầu vào 2.000 millisecond được đọc lại thành 2.000 millisecond hoặc 2 seconds. Không nên chỉ kiểm tra một con số mà bỏ qua đơn vị; một phép so sánh số học có thể vẫn chạy nhưng mang ý nghĩa sai nếu TimeUnit bị khai báo nhầm.

Các trường hợp nên kiểm tra thêm:

- Nguồn trả millisecond và builder khai báo MILLISECONDS.
- Nguồn trả nanosecond và builder khai báo NANOSECONDS.
- Đọc cùng timer bằng nhiều đơn vị qua totalTime(unit).
- Count và total time không giảm giữa các lần thu thập.
- Đối tượng nguồn vẫn được cập nhật sau khi meter đăng ký.
- Không đăng ký lại cùng tên/tag với một đối tượng mới rồi giả định nguồn đã được thay thế.

Kiểm thử với SimpleMeterRegistry xác nhận hành vi API và phép chuyển đổi khi đọc. Cần kiểm thử tích hợp với registry đích để xác nhận base unit và tên metric export thực tế.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Độ trễ lớn hơn hoặc nhỏ hơn 1.000 lần | Khai báo sai TimeUnit của hàm tổng thời gian | Dùng đúng đơn vị mà nguồn thực sự trả về |
| Count không thay đổi | Đối tượng nguồn không cập nhật hoặc hàm count đọc sai thuộc tính | Kiểm tra nguồn thống kê và method reference |
| Tổng thời gian giảm | Nguồn reset bộ đếm hoặc chỉ cung cấp giá trị theo cửa sổ | Dùng số liệu tích lũy đơn điệu hoặc quản lý lại vòng đời meter |
| Timer không theo đối tượng mới | Cùng tên/tag đã được đăng ký nên registry tái sử dụng meter cũ | Dùng danh tính meter phù hợp và vòng đời registry rõ ràng |
| Không thấy p95/p99 | FunctionTimer chỉ theo dõi count và total time | Dùng Timer với histogram nếu cần percentile |
| Mean sai | Count và total time không cùng phạm vi sự kiện hoặc đơn vị | Đồng bộ định nghĩa hai hàm và kiểm tra TimeUnit |

## Ghi nhớ

- FunctionTimer quan sát hai hàm tích lũy: count và tổng thời gian.
- Đối số TimeUnit trong builder mô tả đơn vị của giá trị do totalTimeFunction trả về.
- Registry chuyển tổng thời gian sang base time unit mà implementation sử dụng khi export.
- totalTime(unit) và mean(unit) cho phép đọc kết quả theo đơn vị do bên gọi chọn.
- Count và total time phải đơn điệu; Micrometer không tự sửa hoặc bảo đảm điều kiện này.
- Đối tượng nguồn phải tiếp tục được cập nhật trong vòng đời meter; không dùng số nguyên bất biến làm nguồn.
- FunctionTimer phù hợp với thư viện đã có thống kê tích lũy; Timer phù hợp khi ứng dụng tự đo từng thao tác và cần histogram/percentile.
- Luôn xác minh tên metric và đơn vị export ở registry đích.

Khi khai báo đúng đơn vị của hàm tổng thời gian, FunctionTimer giúp tái sử dụng số liệu tích lũy từ thư viện hoặc đối tượng sẵn có. Registry chịu trách nhiệm chuyển đổi sang đơn vị phù hợp với backend, còn ứng dụng giữ một định nghĩa nhất quán về count và tổng thời gian.

## Tài liệu tham khảo

- [Micrometer: Timers — Function-tracking Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — cách khai báo hai hàm tích lũy, đơn vị đầu vào và chuyển đổi theo base unit của registry.
- [Micrometer Core: FunctionTimer API](https://javadoc.io/doc/io.micrometer/micrometer-core/1.16.6/io/micrometer/core/instrument/FunctionTimer.html) — chữ ký builder, count, totalTime, mean và baseTimeUnit.
