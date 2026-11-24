# Kiểm chứng số liệu từ cache hoặc thư viện cung cấp thống kê nội bộ

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, không phải lúc nào ứng dụng cũng trực tiếp sở hữu từng sự kiện cần đo. Cache, connection pool, client HTTP hoặc thư viện xử lý nền có thể đã tự duy trì thống kê như số lần hit/miss, số lần load, tổng thời gian load hoặc số kết nối đang dùng. Micrometer cung cấp *function meters* để đọc các số liệu đó từ object nguồn và xuất chúng qua `MeterRegistry`.

Hai loại function meter thường dùng là `FunctionCounter` và `FunctionTimer`. Chúng cho phép Micrometer lấy giá trị tích lũy từ hàm đọc trên object tại thời điểm registry thu thập số liệu. Bài này dùng thống kê cache Caffeine làm ví dụ, giải thích cách đối chiếu giá trị nguồn với meter, kiểm tra đơn vị và vòng đời object, đồng thời chỉ ra khi nào nên dùng binder có sẵn thay vì tự tạo function meter.

## 1. Function meter giải quyết vấn đề gì?

Giả sử thư viện cache đã đếm số lần hit và miss. Nếu ứng dụng tự gọi `Counter.increment()` ở mọi vị trí truy cập cache, instrumentation có thể bị lặp hoặc bỏ sót khi có nhiều đường truy cập khác nhau. Function meter cho phép đọc số liệu mà thư viện đã tích lũy sẵn:

```java
FunctionCounter hits = FunctionCounter.builder(
        "product.cache.hits",
        cache,
        currentCache -> currentCache.stats().hitCount())
    .register(registry);
```

Micrometer giữ meter và gọi hàm đọc khi cần lấy số liệu. Ứng dụng không gọi `hits.increment()`; giá trị counter đến từ `cache.stats().hitCount()`.

Điều này hữu ích khi:

- Thư viện đã có thống kê tích lũy và cung cấp getter ổn định.
- Ứng dụng muốn xuất thống kê nội bộ qua cùng hệ metrics.
- Không thể hoặc không cần sửa code bên trong thư viện để instrument từng sự kiện.
- Cần thống nhất cách xuất số liệu từ nhiều thành phần qua Micrometer.

Function meter là adapter đọc số liệu có sẵn. Nó không tự tạo ra thống kê mới và không thay thế cơ chế đo của thư viện nguồn.

## 2. Phân biệt FunctionCounter, FunctionTimer và meter ghi trực tiếp

`Counter` và `Timer` thông thường nhận cập nhật khi ứng dụng gọi `increment()` hoặc `record(...)`. Function meter đọc các bộ đếm/thống kê mà object nguồn đã tích lũy.

| Meter | Cách cập nhật | Dữ liệu nguồn phù hợp | Ý nghĩa |
| --- | --- | --- | --- |
| `Counter` | Ứng dụng gọi `increment()` | Sự kiện ứng dụng tự instrument | Số sự kiện tích lũy |
| `FunctionCounter` | Micrometer gọi hàm đọc | Một giá trị đếm chỉ tăng từ thư viện | Số sự kiện tích lũy do thư viện quản lý |
| `Timer` | Ứng dụng gọi `record(...)` hoặc dừng sample | Từng lần thực thi mà ứng dụng kiểm soát | Số lần và thời lượng đã ghi nhận |
| `FunctionTimer` | Micrometer đọc count và tổng thời gian | Bộ thống kê tích lũy của thư viện | Số lần và tổng thời gian đã được thư viện ghi nhận |
| `Gauge` | Micrometer đọc trạng thái hiện tại | Giá trị có thể tăng hoặc giảm | Trạng thái tại thời điểm lấy mẫu |

Giá trị của `FunctionCounter` phải đơn điệu không giảm. Hai hàm của `FunctionTimer` cũng phải trả về count và tổng thời gian tích lũy, không giảm trong vòng đời meter. Nếu nguồn là giá trị hiện tại có thể tăng giảm, chẳng hạn kích thước cache hoặc số kết nối đang mở, hãy dùng `Gauge`.

Không đăng ký `Counter` và `FunctionCounter` cùng tên/tag để biểu diễn cùng một dữ liệu. Tương tự, không dùng `Timer` và `FunctionTimer` cùng định danh cho cùng một thống kê. Cùng tên và tag trong registry là cùng một định danh meter; loại meter khác nhau có thể gây xung đột hoặc khiến cấu hình không đúng ý nghĩa.

## 3. Nguồn thống kê từ Caffeine

Caffeine có thể ghi nhận thống kê khi cache được tạo với `recordStats()`. Nếu không bật tùy chọn này, các số liệu thống kê có thể luôn bằng 0.

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheConfiguration {
    @Bean
    Cache<String, Product> productCache() {
        return Caffeine.newBuilder()
            .maximumSize(10_000)
            .recordStats()
            .build();
    }
}
```

Sau khi bật thống kê, cache cung cấp `cache.stats()` với các giá trị tích lũy như:

- `hitCount()`: số lần tìm thấy phần tử trong cache.
- `missCount()`: số lần không tìm thấy phần tử.
- `loadCount()`: tổng số lần load.
- `totalLoadTime()`: tổng thời gian dành cho các lần load, tính bằng nanosecond.
- `loadSuccessCount()` và `loadFailureCount()`: số lần load thành công và thất bại.

Đây là số liệu của cache kể từ khi bộ thống kê của cache bắt đầu hoạt động. `stats()` cung cấp snapshot thống kê tại thời điểm gọi; function meter nên gọi getter trên cache sống để đọc snapshot mới nhất, thay vì giữ một snapshot cũ được tạo một lần.

## 4. Đăng ký FunctionCounter cho hit và miss

Có thể tạo hai function counter để xuất số hit và miss:

```java
import com.github.benmanes.caffeine.cache.Cache;
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheMetrics {
    private final Cache<String, Product> cache;
    private final FunctionCounter hits;
    private final FunctionCounter misses;

    public ProductCacheMetrics(
            MeterRegistry registry,
            Cache<String, Product> productCache) {
        this.cache = productCache;

        this.hits = FunctionCounter.builder(
                "product.cache.hits",
                cache,
                current -> current.stats().hitCount())
            .description("Number of product cache hits")
            .register(registry);

        this.misses = FunctionCounter.builder(
                "product.cache.misses",
                cache,
                current -> current.stats().missCount())
            .description("Number of product cache misses")
            .register(registry);
    }
}
```

Field `cache` giữ tham chiếu mạnh tới object nguồn trong suốt vòng đời bean. Điều này quan trọng vì function meter có thể chỉ giữ tham chiếu yếu tới object được quan sát; nếu object nguồn bị GC, meter không thể tiếp tục đọc thống kê.

Hai function counter không tự tăng theo request. Khi cache nhận một hit hoặc miss, Caffeine cập nhật bộ thống kê của nó. Ở lần scrape hoặc lấy mẫu tiếp theo, Micrometer đọc giá trị mới từ `cache.stats()`.

## 5. Đăng ký FunctionTimer cho số lần và tổng thời gian load

Khi thư viện cung cấp cả số lần thực hiện và tổng thời gian tích lũy, `FunctionTimer` có thể biểu diễn hai giá trị đó như một timer:

```java
import io.micrometer.core.instrument.FunctionTimer;
import java.util.concurrent.TimeUnit;

FunctionTimer loads = FunctionTimer.builder(
        "product.cache.load",
        cache,
        current -> current.stats().loadCount(),
        current -> current.stats().totalLoadTime(),
        TimeUnit.NANOSECONDS)
    .description("Cumulative time spent loading products into cache")
    .register(registry);
```

Các tham số có ý nghĩa:

1. Object nguồn là cache đang giữ thống kê.
2. Hàm count trả về số lần load tích lũy.
3. Hàm total time trả về tổng thời gian load tích lũy.
4. `TimeUnit.NANOSECONDS` khai báo đơn vị của giá trị do hàm tổng thời gian trả về.

Micrometer chuyển tổng thời gian sang đơn vị phù hợp với backend khi xuất. Với Prometheus, timer thường được biểu diễn bằng `_count` và `_sum` theo giây. Luôn khai báo đúng đơn vị nguồn; nếu đưa nanosecond nhưng khai báo millisecond, kết quả thời gian sẽ sai theo hệ số một triệu.

`FunctionTimer` không có dữ liệu thời lượng riêng của từng lần load. Nó chỉ biết tổng số lần và tổng thời gian tích lũy. Vì vậy, có thể tính thời lượng trung bình, nhưng không thể khôi phục p95/p99 từ hai giá trị này. Nếu cần histogram hoặc percentile, hãy instrument từng lần thực thi bằng `Timer`, hoặc dùng binder của thư viện có hỗ trợ phân phối chi tiết.

## 6. Tổ chức bean hoàn chỉnh

Ví dụ dưới đây gom các function meter của cache vào một bean. Trong ứng dụng, cache và bean metrics đều là singleton nên object nguồn tồn tại đủ lâu để Micrometer đọc.

```java
import com.github.benmanes.caffeine.cache.Cache;
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.FunctionTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class ProductCacheMetrics {
    private final Cache<String, Product> cache;
    private final FunctionCounter hits;
    private final FunctionCounter misses;
    private final FunctionTimer loads;

    public ProductCacheMetrics(
            MeterRegistry registry,
            Cache<String, Product> productCache) {
        this.cache = productCache;

        this.hits = FunctionCounter.builder(
                "product.cache.hits", cache,
                current -> current.stats().hitCount())
            .description("Number of product cache hits")
            .register(registry);

        this.misses = FunctionCounter.builder(
                "product.cache.misses", cache,
                current -> current.stats().missCount())
            .description("Number of product cache misses")
            .register(registry);

        this.loads = FunctionTimer.builder(
                "product.cache.load", cache,
                current -> current.stats().loadCount(),
                current -> current.stats().totalLoadTime(),
                TimeUnit.NANOSECONDS)
            .description("Cumulative time spent loading products into cache")
            .register(registry);
    }
}
```

Các field `hits`, `misses` và `loads` giữ lại tham chiếu meter để code có thể dùng trong kiểm thử hoặc tra cứu. Việc ghi nhận vẫn do cache quản lý; không gọi `increment()` hoặc `record()` trên các function meter.

## 7. Kiểm chứng số liệu nguồn với số liệu Micrometer

Muốn xác nhận function meter phản ánh đúng thư viện, hãy tạo một kịch bản có kết quả dự đoán được. Với cache Caffeine đã bật `recordStats()`:

1. Truy cập một key chưa có: phát sinh một miss và một lần load nếu dùng phương thức load.
2. Truy cập lại cùng key: phát sinh một hit.
3. Đọc `cache.stats()` để lấy giá trị nguồn.
4. Đọc `FunctionCounter.count()` và `FunctionTimer.count()/totalTime(...)` để so sánh.

Ví dụ kiểm thử:

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.FunctionTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CacheFunctionMetersTest {
    @Test
    void mirrorsCaffeineCumulativeStatistics() {
        Cache<String, String> cache = Caffeine.newBuilder()
            .recordStats()
            .build();

        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        FunctionCounter hits = FunctionCounter.builder(
                "test.cache.hits", cache,
                current -> current.stats().hitCount())
            .register(registry);

        FunctionCounter misses = FunctionCounter.builder(
                "test.cache.misses", cache,
                current -> current.stats().missCount())
            .register(registry);

        FunctionTimer loads = FunctionTimer.builder(
                "test.cache.load", cache,
                current -> current.stats().loadCount(),
                current -> current.stats().totalLoadTime(),
                TimeUnit.NANOSECONDS)
            .register(registry);

        cache.get("product-1", key -> "book"); // miss và load
        cache.get("product-1", key -> "unused"); // hit

        assertEquals(cache.stats().hitCount(), hits.count(), 0.0);
        assertEquals(cache.stats().missCount(), misses.count(), 0.0);
        assertEquals(cache.stats().loadCount(), loads.count());
        assertTrue(loads.totalTime(TimeUnit.NANOSECONDS) >= 0.0);
    }
}
```

Test này kiểm tra function meters đọc cùng bộ thống kê mà cache cung cấp. Thời gian load có thể rất ngắn, vì vậy không nên khẳng định một giá trị thời lượng cố định. Điều cần xác minh là đơn vị được khai báo đúng và tổng thời gian không âm.

## 8. Kiểm tra monotonicity và reset của nguồn

Function counter có hợp đồng quan trọng: hàm đọc phải trả về một giá trị tích lũy không giảm. Nếu thư viện reset thống kê về 0 trong khi meter vẫn tồn tại, giá trị function counter sẽ giảm và vi phạm semantics của counter. Hệ giám sát có thể diễn giải sai tốc độ hoặc phát hiện reset không đúng cách.

Trước khi đăng ký function meter, hãy xác minh:

- Getter trả về tổng tích lũy kể từ khi object được tạo hoặc kể từ một mốc ổn định.
- Giá trị không giảm trong vòng đời của meter.
- Không có thao tác reset stats chạy định kỳ dưới cùng tên/tag.
- Nếu cache được thay thế hoặc reset, vòng đời meter và object nguồn được quản lý tương ứng.

Nếu thư viện chỉ cung cấp thống kê theo từng cửa sổ và giá trị có thể giảm, không ép dữ liệu đó vào `FunctionCounter`. Có thể dùng `Gauge` cho một giá trị hiện tại, hoặc tự tạo `Counter` bằng cách quan sát chênh lệch qua một cơ chế có trạng thái rõ ràng và xử lý reset đúng cách.

Với `FunctionTimer`, count và tổng thời gian cũng cần tích lũy. Nếu count tăng nhưng total time bị reset hoặc giảm, các phép tính trung bình và rate sẽ không còn đáng tin cậy.

## 9. Kiểm tra đơn vị, tần suất lấy mẫu và chi phí getter

Function meter được đọc khi registry thu thập hoặc xuất số liệu. Hàm đọc nên nhẹ, có thể gọi lặp lại và không gây side effect. Getter không nên:

- Gọi database hoặc HTTP service.
- Thực hiện thao tác có thể block lâu.
- Thay đổi hoặc reset thống kê nguồn.
- Tạo object lớn hoặc tính toán lại toàn bộ dữ liệu mỗi lần scrape.

Đối với `FunctionTimer`, đơn vị của hàm total time phải khớp với `TimeUnit` truyền vào builder. Đối với `DistributionSummary` hoặc `Gauge` khác, đơn vị cũng cần được thống nhất giữa nguồn, meter và dashboard.

Micrometer không lấy lại từng sự kiện bị bỏ lỡ giữa hai lần scrape. Nó đọc snapshot tích lũy hiện tại. Nếu muốn xem tốc độ sự kiện, dùng `rate()` trên counter ở backend; nếu muốn trung bình thời lượng trong một khoảng, tính từ tốc độ tăng của `_sum` chia cho tốc độ tăng của `_count`.

Ví dụ PromQL, giả sử exporter chuẩn hóa tên metric thành dạng dưới đây:

```promql
rate(product_cache_hits_total[5m])
```

Tốc độ load mỗi giây:

```promql
rate(product_cache_load_seconds_count[5m])
```

Thời gian load trung bình trong cửa sổ 5 phút:

```promql
rate(product_cache_load_seconds_sum[5m])
/
rate(product_cache_load_seconds_count[5m])
```

Tên metric thực tế phụ thuộc quy tắc đặt tên của registry và phiên bản exporter; hãy kiểm tra endpoint exposition trước khi dùng truy vấn.

## 10. Khi nào dùng binder có sẵn?

Một số thư viện phổ biến đã có integration hoặc `MeterBinder` của Micrometer. Binder thường hiểu rõ cấu trúc nội bộ, tên metric, tag và các trường thống kê mà thư viện hỗ trợ. Nếu binder cung cấp đầy đủ dữ liệu cần thiết, hãy ưu tiên nó thay vì tự đăng ký function meter cho cùng số liệu.

Function meter phù hợp khi:

- Chưa có binder cho thư viện đang dùng.
- Binder hiện tại không xuất một trường thống kê cần thiết.
- Ứng dụng cần ánh xạ một getter tích lũy riêng sang Micrometer.
- Muốn adapter nhỏ cho một object thống kê nội bộ.

Không bật binder và function meter trùng lặp cho cùng một chỉ số nếu không có chủ đích. Điều đó có thể tạo metric trùng nghĩa, tăng cardinality và khiến dashboard đếm hai lần khi tổng hợp.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| FunctionCounter luôn bằng 0 | Chưa bật thống kê nguồn như `recordStats()`, hoặc getter đang đọc snapshot cũ |
| FunctionCounter giảm sau một thời gian | Nguồn đã reset hoặc getter không trả giá trị tích lũy |
| FunctionTimer có count nhưng thời gian sai | Khai báo sai `TimeUnit` hoặc getter trả về đơn vị khác với đơn vị đã khai báo |
| Function meter ngừng cập nhật | Object nguồn bị GC hoặc bean không giữ tham chiếu mạnh tới object |
| Giá trị meter khác `cache.stats()` | So sánh ở hai thời điểm khác nhau khi cache vẫn đang nhận request; hãy đồng bộ hoặc đọc tuần tự |
| Prometheus không có metric mong đợi | Registry/exporter không xuất meter đó, sai tên metric hoặc meter đăng ký vào registry khác |
| Số liệu cache bị đếm hai lần | Binder và function meter cùng xuất một thống kê, hoặc instrumentation thủ công lặp lại sự kiện |
| p95 không có dữ liệu từ FunctionTimer | FunctionTimer chỉ đọc count và tổng thời gian; cần Timer/histogram để có phân phối |

Khi đối chiếu số liệu, hãy tạo một khoảng kiểm thử không có request đồng thời để so sánh chính xác. Trong môi trường tải thật, cache có thể thay đổi giữa hai lần đọc nên chênh lệch nhỏ không nhất thiết là lỗi. Điều quan trọng là nguồn và function meter cùng tăng theo một định nghĩa, cùng đơn vị và cùng vòng đời.

## 12. Nguyên tắc áp dụng

Function meters giúp đưa thống kê tích lũy từ cache hoặc thư viện vào `MeterRegistry` mà không phải instrument lại từng sự kiện. Dùng `FunctionCounter` cho giá trị đếm đơn điệu; dùng `FunctionTimer` khi nguồn cung cấp count và tổng thời gian tích lũy; dùng `Gauge` cho trạng thái có thể tăng giảm. Giữ object nguồn sống đủ lâu, không reset bộ đếm trong vòng đời meter và khai báo đúng đơn vị thời gian.

Trước khi triển khai, hãy xác nhận thống kê nguồn đã được bật, chạy kịch bản có kết quả dự đoán được, so sánh getter nguồn với function meter và kiểm tra dữ liệu tại endpoint export. Nếu thư viện đã có binder phù hợp, dùng binder làm nguồn instrumentation thống nhất và tránh xuất trùng cùng một thống kê.
