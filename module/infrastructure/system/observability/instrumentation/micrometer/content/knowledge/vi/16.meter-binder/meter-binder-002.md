# Cài đặt bindTo với tên, tag và đối tượng theo dõi được kiểm soát

`MeterBinder` là extension point của Micrometer để gom việc đăng ký một nhóm meter có liên quan vào một thành phần. Interface này có phương thức `bindTo(MeterRegistry registry)`; khi được gọi, binder đăng ký các Counter, Gauge, Timer hoặc meter khác vào registry được truyền vào.

Một binder tốt mô tả các phép đo của một thành phần hoặc một nguồn trạng thái cụ thể. Nó dùng tên ổn định, tag có tập giá trị kiểm soát được và đối tượng theo dõi có vòng đời phù hợp. Với Gauge hoặc FunctionCounter, binder thường giữ tham chiếu đến nguồn dữ liệu rồi đăng ký hàm đọc trên nguồn đó. Khi trạng thái thay đổi, ứng dụng cập nhật chính nguồn dữ liệu; không đăng ký meter mới ở mỗi lần thay đổi.

Trong Spring Boot, các bean triển khai `MeterBinder` được tự động bind vào các MeterRegistry do ứng dụng quản lý. Với ứng dụng Micrometer độc lập, cần gọi `bindTo(registry)` cho registry muốn sử dụng. Phương thức `bindTo` nhận registry làm tham số để cùng một binder có thể đăng ký meter vào nhiều registry khác nhau.

## 1. MeterBinder giải quyết vấn đề gì?

Một thành phần như cache, queue hoặc connection pool có thể cần nhiều phép đo:

- Gauge cho số phần tử hiện tại.
- FunctionCounter cho tổng số lần eviction hoặc lỗi tích lũy từ nguồn dữ liệu.
- Timer cho thời lượng một thao tác.
- Counter cho các sự kiện mà thành phần chủ động ghi nhận.

Nếu từng service tự đăng ký những meter này, tên, tag và cách đo có thể bị lặp lại hoặc không thống nhất. `MeterBinder` gom phần khai báo vào một nơi, giúp mã nghiệp vụ tập trung vào hành vi của thành phần.

Một binder thường có ba trách nhiệm:

1. Nhận một nguồn dữ liệu hoặc đối tượng trạng thái cần quan sát.
2. Đăng ký meter với tên, tag, mô tả và đơn vị phù hợp trong `bindTo`.
3. Cho phép thành phần sở hữu trạng thái cập nhật dữ liệu theo vòng đời ứng dụng.

Binder không phải một registry mới, cũng không phải nơi lưu lịch sử metrics. Nó chỉ kết nối nguồn dữ liệu của ứng dụng với các meter trong registry.

## 2. Cấu trúc của MeterBinder

Interface nằm trong package `io.micrometer.core.instrument.binder`:

~~~java
package io.micrometer.core.instrument.binder;

import io.micrometer.core.instrument.MeterRegistry;

public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
~~~

Một implementation nhận registry rồi đăng ký meter:

~~~java
final class ApplicationMetrics implements MeterBinder {
    @Override
    public void bindTo(MeterRegistry registry) {
        registry.counter("application.events");
    }
}
~~~

Ví dụ này chỉ minh họa contract. Trong ứng dụng thực tế, binder nên đăng ký các meter có ý nghĩa và gắn với trạng thái hoặc hành vi của một thành phần cụ thể.

Không nên giữ một registry toàn cục trong binder. Hãy dùng tham số `registry` của `bindTo` để đăng ký meter vào đúng registry mà framework hoặc ứng dụng yêu cầu.

## 3. Thiết kế tên meter và tag

Tên meter cần mô tả đại lượng hoặc trạng thái, ổn định qua các lần triển khai. Quy ước thường dùng là chữ thường, các thành phần phân tách bằng dấu chấm:

| Tên meter | Ý nghĩa |
|---|---|
| `cache.entries` | Số phần tử hiện có trong cache |
| `cache.evictions` | Tổng số lần phần tử bị loại khỏi cache |
| `queue.depth` | Số phần tử hiện đang chờ |
| `worker.active` | Số worker đang hoạt động |
| `connection.pool.active` | Số kết nối đang được sử dụng |

Tag thể hiện chiều phân loại của cùng một đại lượng. Ví dụ, một binder có thể thêm `cache=catalog` hoặc `pool=primary` nếu tập giá trị được xác định trước.

~~~java
Gauge.builder("cache.entries", cacheState, CacheState::entryCount)
        .tag("cache", "catalog")
        .description("Current number of entries in the catalog cache")
        .register(registry);
~~~

Không đưa các giá trị sau vào tên hoặc tag metrics:

- Cache key, user ID, order ID hoặc request ID.
- Tên file hoặc URL có path/query động.
- Nội dung exception hoặc câu truy vấn đã nội suy tham số.
- Timestamp hoặc UUID tạo mới cho mỗi lần chạy.

Các giá trị này có thể tạo một meter ID mới cho mỗi đối tượng hoặc request, khiến cardinality tăng không giới hạn. Nếu cần định danh chi tiết để điều tra, hãy dùng log hoặc trace; metrics nên tổng hợp theo nhóm ổn định.

## 4. Chọn đúng loại meter cho nguồn dữ liệu

MeterBinder không quyết định loại meter thay cho người thiết kế. Cần chọn theo ngữ nghĩa:

| Nhu cầu | Meter phù hợp | Lý do |
|---|---|---|
| Số phần tử hiện tại trong queue | Gauge | Trạng thái có thể tăng hoặc giảm |
| Tổng số lần cache eviction | Counter hoặc FunctionCounter | Sự kiện tích lũy, không giảm |
| Thời lượng một lần tải cache | Timer | Đo thao tác đã hoàn tất |
| Số lần tải cache hiện đang chạy và thời lượng đang chạy | LongTaskTimer | Quan sát tác vụ chưa hoàn tất |
| Phân bố kích thước payload | DistributionSummary | Đại lượng số không phải thời gian |

Với Counter, ứng dụng chủ động gọi `increment()` khi sự kiện xảy ra. FunctionCounter quan sát một nguồn số tích lũy bên ngoài, chẳng hạn tổng eviction trong cache. Không dùng FunctionCounter cho một giá trị có thể giảm; loại meter này yêu cầu nguồn dữ liệu mang ý nghĩa tích lũy đơn điệu.

Gauge biểu diễn snapshot tại thời điểm thu thập. Không dùng Gauge để đếm tổng số sự kiện, và không dùng Counter để biểu diễn số phần tử hiện tại.

## 5. Ví dụ: bind Gauge và FunctionCounter từ một đối tượng trạng thái

Giả sử ứng dụng có cache catalog. Thành phần cần theo dõi số entry hiện tại và tổng số eviction. Đầu tiên, tạo một đối tượng trạng thái có vòng đời dài:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

final class CacheState {
    private final AtomicInteger entries = new AtomicInteger();
    private final LongAdder evictions = new LongAdder();

    int entryCount() {
        return entries.get();
    }

    long evictionCount() {
        return evictions.sum();
    }

    void entryAdded() {
        entries.incrementAndGet();
    }

    void entryRemoved() {
        entries.updateAndGet(value -> Math.max(0, value - 1));
    }

    void recordEviction() {
        evictions.increment();
    }
}
~~~

Sau đó, binder đăng ký meter dựa trên chính đối tượng này:

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

final class CacheMetrics implements MeterBinder {
    private final CacheState state;

    CacheMetrics(CacheState state) {
        this.state = state;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("cache.entries", state, CacheState::entryCount)
                .tag("cache", "catalog")
                .description("Current number of catalog cache entries")
                .register(registry);

        FunctionCounter.builder(
                        "cache.evictions",
                        state,
                        CacheState::evictionCount)
                .tag("cache", "catalog")
                .description("Total number of catalog cache evictions")
                .register(registry);
    }
}
~~~

Khi cache thay đổi, ứng dụng cập nhật `CacheState`:

~~~java
state.entryAdded();
state.recordEviction();
~~~

Gauge đọc `entryCount()` mỗi khi được lấy mẫu. FunctionCounter đọc tổng eviction tích lũy. Binder chỉ đăng ký meter; nó không cần chạy lại `bindTo` sau mỗi thay đổi trạng thái.

Micrometer Gauge thường giữ tham chiếu yếu đến object được quan sát. Ở ví dụ này, `CacheMetrics` giữ `CacheState` trong field, và bean sở hữu binder có vòng đời ứng dụng. Vì vậy, nguồn dữ liệu vẫn có tham chiếu mạnh trong suốt thời gian cần đo.

## 6. Vì sao bindTo nhận MeterRegistry làm tham số?

Một ứng dụng có thể có nhiều registry, ví dụ một registry xuất Prometheus và một registry xuất đến backend khác. Cùng một binder có thể được gọi với từng registry để đăng ký các meter tương ứng.

Điều này dẫn đến hai nguyên tắc:

- Binder giữ nguồn dữ liệu và quy tắc đặt tên/tag; registry cụ thể được truyền vào khi bind.
- Không lưu một Counter, Gauge hoặc Timer đã đăng ký ở registry đầu tiên vào field rồi dùng lại cho registry khác.

Ví dụ không nên làm:

~~~java
final class BadMetricsBinder implements MeterBinder {
    private Counter counter;

    @Override
    public void bindTo(MeterRegistry registry) {
        if (counter == null) {
            counter = registry.counter("jobs.completed");
        }
    }
}
~~~

Nếu binder được bind vào registry thứ hai, field `counter` vẫn trỏ đến meter của registry đầu tiên. Các thao tác sau đó có thể chỉ cập nhật một backend.

Với meter có trạng thái cập nhật trực tiếp như Gauge hoặc FunctionCounter, nên để binder đăng ký chúng vào từng registry bằng nguồn dữ liệu chung. Với Counter/Timer cần được gọi từ đường nghiệp vụ, hãy thiết kế cách truy cập meter theo từng registry hoặc dùng cơ chế registry/composite phù hợp; không giữ một meter của registry cụ thể trong singleton binder rồi giả định mọi registry đều nhận được số đo.

## 7. Tích hợp MeterBinder với Spring Boot

Trong ứng dụng Spring Boot có Actuator và Micrometer, các bean triển khai `MeterBinder` được framework tự động bind vào các MeterRegistry do context quản lý. Có thể khai báo binder như một bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CacheMetricsConfiguration {
    @Bean
    CacheState cacheState() {
        return new CacheState();
    }

    @Bean
    CacheMetrics cacheMetrics(CacheState state) {
        return new CacheMetrics(state);
    }
}
~~~

Spring Boot nhận bean `CacheMetrics` và gọi `bindTo(registry)` khi cấu hình registry. Ứng dụng không cần gọi `cacheMetrics.bindTo(registry)` thêm lần nữa nếu đã dùng cơ chế tự động này.

Các binder do Micrometer cung cấp cũng được Spring Boot sử dụng để thu thập metrics nền tảng, ví dụ thông tin JVM, hệ điều hành, executor hoặc cache tùy dependency và cấu hình. Chỉ bật các binder cần thiết và kiểm tra tag được xuất ra.

Nếu không dùng Spring Boot, có thể đăng ký thủ công:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
CacheState state = new CacheState();
CacheMetrics binder = new CacheMetrics(state);

binder.bindTo(registry);
~~~

Ứng dụng phải quản lý vòng đời registry thủ công nếu registry có tài nguyên cần giải phóng.

## 8. Cấu hình common tags và MeterFilter

Common tags áp dụng các chiều chung như application hoặc environment cho meter trong registry. Cấu hình nên diễn ra trước khi binder đăng ký meter:

~~~java
registry.config().commonTags(
        "application", "catalog-service",
        "environment", "production"
);

cacheMetrics.bindTo(registry);
~~~

Tag chung phải ổn định và có số lượng giá trị nhỏ. Không dùng request ID, customer ID hoặc tenant ID tùy ý làm common tags.

MeterFilter có thể giới hạn hoặc từ chối meter theo tên/tag khi được đăng ký. Ví dụ:

~~~java
registry.config().meterFilter(
        MeterFilter.denyNameStartsWith("debug.")
);
~~~

Nếu filter từ chối meter do binder đăng ký, meter đó sẽ không xuất hiện như mong đợi. Khi điều tra thiếu metrics, kiểm tra cả binder, MeterFilter, naming convention và registry exporter.

## 9. Bind nhiều meter có liên quan

Một binder có thể đăng ký nhiều meter cùng thuộc một thành phần. Ví dụ, binder của executor có thể đăng ký:

- Gauge số tác vụ đang hoạt động.
- Gauge kích thước hàng đợi.
- Gauge số thread hiện tại.
- FunctionCounter tổng số tác vụ đã hoàn tất nếu nguồn dữ liệu cung cấp bộ đếm tích lũy.

Các meter nên dùng chung một quy ước tag, chẳng hạn `executor=reporting`, để dashboard có thể lọc cùng một thành phần. Mỗi tên vẫn cần biểu diễn đúng một đại lượng.

Không nên biến một binder thành nơi đăng ký mọi metrics của toàn ứng dụng. Hãy chia binder theo thành phần hoặc nguồn dữ liệu, ví dụ `CacheMetrics`, `QueueMetrics`, `WorkerPoolMetrics`. Cấu trúc này giúp người đọc xác định nơi sở hữu trạng thái và nơi khai báo phép đo.

## 10. Binder có thể được bind vào nhiều registry

Vì `bindTo` nhận một registry làm tham số, cùng một binder có thể phục vụ nhiều registry. Mỗi registry quản lý meter riêng, dù chúng cùng đọc từ một đối tượng trạng thái.

~~~java
CacheState state = new CacheState();
CacheMetrics binder = new CacheMetrics(state);

SimpleMeterRegistry first = new SimpleMeterRegistry();
SimpleMeterRegistry second = new SimpleMeterRegistry();

binder.bindTo(first);
binder.bindTo(second);

state.entryAdded();
~~~

Khi mỗi registry thu thập meter, Gauge trong cả hai registry đều đọc từ cùng `CacheState`. Đây là cách phù hợp với nguồn dữ liệu trạng thái có thể chia sẻ.

Không phải mọi cách triển khai binder đều tự động an toàn khi bind nhiều lần. Tránh tạo tác dụng phụ trong `bindTo`, tránh thay đổi trạng thái nghiệp vụ khi đăng ký meter và không giả định `bindTo` chỉ được gọi đúng một lần trong toàn bộ ứng dụng. Nếu binder tạo listener hoặc callback, cần quản lý đăng ký và hủy listener theo vòng đời phù hợp.

## 11. Kiểm thử MeterBinder

Có thể dùng `SimpleMeterRegistry` để kiểm tra binder đã đăng ký đúng tên, tag và loại meter:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class CacheMetricsTest {
    @Test
    void bindsGaugeAndFunctionCounterToRegistry() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CacheState state = new CacheState();
        CacheMetrics binder = new CacheMetrics(state);

        binder.bindTo(registry);

        state.entryAdded();
        state.entryAdded();
        state.recordEviction();

        assertThat(registry.get("cache.entries")
                .tag("cache", "catalog")
                .gauge()
                .value()).isEqualTo(2.0);

        assertThat(registry.get("cache.evictions")
                .tag("cache", "catalog")
                .functionCounter()
                .count()).isEqualTo(1.0);
    }
}
~~~

Kiểm thử này xác minh Gauge đọc trạng thái mới từ cùng object và FunctionCounter phản ánh tổng sự kiện tích lũy.

Nên kiểm tra thêm:

1. Binder đăng ký đầy đủ meter dự kiến.
2. Tên, tag, mô tả và đơn vị đúng quy ước.
3. Nguồn dữ liệu được giữ tham chiếu mạnh trong suốt vòng đời cần đo.
4. FunctionCounter không giảm và không bị dùng cho nguồn trạng thái có thể giảm.
5. Cùng binder có thể bind vào hai registry nếu đây là yêu cầu của ứng dụng.
6. MeterFilter và common tags không làm mất hoặc biến đổi meter ngoài dự kiến.

SimpleMeterRegistry phù hợp cho unit test, nhưng không xác minh định dạng backend. Với Prometheus hoặc registry khác, hãy có kiểm thử tích hợp để kiểm tra endpoint scrape hoặc dữ liệu xuất.

## 12. Những lỗi thường gặp

**Đăng ký meter trong mỗi lần xử lý.** Binder nên đăng ký meter trong `bindTo`; cập nhật trạng thái hoặc ghi số đo diễn ra ở đường nghiệp vụ. Không gọi lại bindTo sau mỗi sự kiện.

**Lưu meter của registry đầu tiên vào field rồi dùng cho mọi registry.** Meter thuộc registry cụ thể. Hãy đăng ký meter vào tham số registry hiện tại, hoặc thiết kế quản lý tham chiếu theo từng registry.

**Dùng tên và tag động không giới hạn.** Mỗi tổ hợp tên/tag có thể tạo một chuỗi thời gian. Chọn danh mục giá trị hữu hạn và chuẩn hóa trước khi đăng ký.

**Dùng Gauge cho số sự kiện tích lũy.** Gauge đọc trạng thái hiện tại. Dùng Counter hoặc FunctionCounter cho tổng sự kiện tùy nguồn dữ liệu.

**Dùng FunctionCounter cho nguồn có thể giảm.** FunctionCounter giả định giá trị tích lũy đơn điệu. Dùng Gauge nếu giá trị biểu diễn trạng thái có thể tăng hoặc giảm.

**Không giữ object được Gauge quan sát.** Gauge có thể giữ tham chiếu yếu; object bị thu hồi có thể làm số đo thành NaN. Binder hoặc component sở hữu trạng thái cần giữ tham chiếu mạnh.

**Gọi bindTo thủ công trong Spring Boot khi binder đã là bean.** Spring Boot tự động bind các bean MeterBinder. Gọi thêm thủ công có thể tạo đăng ký dư thừa hoặc làm luồng cấu hình khó hiểu.

**Đặt tác dụng phụ nghiệp vụ trong bindTo.** Bind chỉ nên đăng ký instrumentation. Không tải cache, mở kết nối nghiệp vụ hoặc thay đổi trạng thái ứng dụng khi framework bind meter.

## 13. Checklist thiết kế MeterBinder

Trước khi đưa binder vào ứng dụng, hãy xác minh:

- [ ] Binder gom các meter thuộc cùng một thành phần hoặc nguồn dữ liệu.
- [ ] `bindTo` đăng ký meter vào đúng registry được truyền vào.
- [ ] Tên meter ổn định và mô tả đúng đại lượng.
- [ ] Tag cố định, có tập giá trị hữu hạn và không chứa ID động.
- [ ] Loại meter đúng ngữ nghĩa: Gauge cho trạng thái, Counter/FunctionCounter cho sự kiện tích lũy, Timer cho thời lượng.
- [ ] Object được Gauge quan sát có vòng đời đủ dài và được giữ tham chiếu mạnh.
- [ ] FunctionCounter đọc nguồn tích lũy không giảm.
- [ ] Binder không giữ meter của registry này để dùng cho registry khác.
- [ ] Spring Boot tự động bind bean MeterBinder; không gọi thủ công lần nữa nếu không có lý do.
- [ ] Unit test xác minh meter, tag và dữ liệu sau khi trạng thái thay đổi.
- [ ] Kiểm thử exporter nếu cần xác nhận định dạng backend.

## 14. Kết luận

`MeterBinder` giúp đóng gói việc đăng ký các meter của một thành phần vào phương thức `bindTo(MeterRegistry)`. Binder nên giữ nguồn dữ liệu có vòng đời phù hợp, đăng ký meter bằng tên và tag ổn định, sau đó để ứng dụng cập nhật nguồn dữ liệu hoặc ghi sự kiện qua đúng API.

Trong Spring Boot, khai báo binder như bean để framework tự động bind vào registry. Với ứng dụng độc lập, gọi `bindTo` cho từng registry cần sử dụng. Hãy thiết kế binder không phụ thuộc vào một registry cụ thể, kiểm soát cardinality, giữ tham chiếu đến object Gauge và kiểm thử cả việc đăng ký lẫn hành vi đọc số đo. Cách tổ chức này tạo instrumentation nhất quán và dễ mở rộng khi ứng dụng có nhiều thành phần hoặc backend metrics.

## Tài liệu tham khảo

- [Micrometer – Meter Binders](https://docs.micrometer.io/micrometer/reference/concepts/meter-binders.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer – Function Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
