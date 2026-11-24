# Tra cứu bằng find, get, tên và tập tag

`MeterRegistry` không chỉ tạo và quản lý meter mà còn cung cấp API để tìm lại meter đã đăng ký. Hai cách tra cứu thường dùng là `find(name)` và `get(name)`. Cả hai bắt đầu bằng tên metric, sau đó có thể bổ sung điều kiện theo tag và loại meter như Counter, Gauge, Timer hoặc DistributionSummary.

Tra cứu rất hữu ích khi cần kiểm tra một meter đã tồn tại, đọc số đo trong test, xác minh instrumentation hoặc tìm tất cả meter thuộc một nhóm. Tuy nhiên, tra cứu trong registry chỉ làm việc với các meter đang được đăng ký trong bộ nhớ của registry đó; nó không truy vấn dữ liệu lịch sử trong Prometheus hay một metrics backend khác.

## 1. Tra cứu meter theo tên và tag

Trong Micrometer, một meter được nhận diện bởi tên và tập tag. Ví dụ, hai meter sau có cùng tên nhưng khác tag nên là hai meter khác nhau:

```java
Counter webOrders = registry.counter(
    "orders.created",
    "channel", "web"
);

Counter mobileOrders = registry.counter(
    "orders.created",
    "channel", "mobile"
);
```

Có thể hình dung:

```text
orders.created{channel=web}
orders.created{channel=mobile}
```

Khi chỉ tra cứu theo tên `orders.created`, registry có thể tìm thấy cả hai meter. Khi bổ sung `channel=web`, kết quả được giới hạn vào meter có tag đó.

Tên metric là điểm bắt đầu của truy vấn. Tag giúp chọn đúng chiều dữ liệu. Nếu tên và tag chưa đủ để xác định duy nhất một meter, hãy lấy toàn bộ kết quả phù hợp thay vì giả định chỉ có một meter.

## 2. Dùng find() khi kết quả có thể không tồn tại

`MeterRegistry.find(String name)` bắt đầu một phép tìm kiếm và trả về đối tượng `Search`. Có thể nối thêm điều kiện bằng `tag(...)` hoặc `tags(...)`, rồi lấy meter theo loại mong muốn.

Ví dụ:

```java
Counter counter = registry.find("orders.created")
    .tag("channel", "web")
    .counter();

if (counter != null) {
    double count = counter.count();
    // Sử dụng số lần tạo đơn đã ghi nhận
}
```

Nếu không có meter phù hợp, `counter()` trả về `null`. Vì vậy, `find()` phù hợp khi meter có thể chưa được đăng ký, ví dụ trong ứng dụng tùy cấu hình, trong test hoặc khi một thành phần tùy chọn chưa được khởi tạo.

Có thể tìm theo nhiều tag cùng lúc:

```java
Timer timer = registry.find("http.server.requests")
    .tags(
        "method", "GET",
        "status", "200"
    )
    .timer();
```

`tags(...)` nhận các cặp key/value, vì vậy số phần tử truyền vào phải là số chẵn. Nếu chỉ cần một điều kiện, dùng `tag(key, value)` giúp đoạn code dễ đọc hơn.

### Lấy tất cả meter phù hợp

Nếu một tên có nhiều tổ hợp tag, có thể dùng `meters()` để lấy tất cả meter thỏa điều kiện:

```java
Collection<Meter> orderMeters = registry.find("orders.created")
    .meters();

for (Meter meter : orderMeters) {
    System.out.println(meter.getId());
}
```

Khi không có kết quả, `find(...).meters()` trả về collection rỗng. Phương thức `meter()` trả về meter đầu tiên phù hợp hoặc `null` nếu không có meter.

Vì `meter()` và các accessor theo loại như `counter()` chỉ lấy một kết quả, không nên dùng chúng khi điều kiện tìm kiếm có thể khớp nhiều tổ hợp tag mà ứng dụng cần xử lý tất cả. Khi đó, dùng `meters()`, `counters()`, `timers()` hoặc accessor collection tương ứng.

## 3. Dùng get() khi meter bắt buộc phải tồn tại

`MeterRegistry.get(String name)` tạo một `RequiredSearch`. Nó hoạt động tương tự `find()` ở cách bổ sung điều kiện, nhưng có ngữ nghĩa bắt buộc: nếu không có meter thỏa tất cả điều kiện tìm kiếm, Micrometer ném `MeterNotFoundException`.

Ví dụ:

```java
Counter counter = registry.get("orders.created")
    .tag("channel", "web")
    .counter();

double created = counter.count();
```

Đoạn code trên giả định meter `orders.created{channel=web}` chắc chắn đã được đăng ký. Nếu giả định đó sai, lời gọi sẽ ném exception thay vì trả về `null`.

Có thể dùng `get()` khi sự tồn tại của meter là một điều kiện bắt buộc, chẳng hạn trong test xác nhận instrumentation hoặc trong bước kiểm tra cấu hình sau khi các component đã khởi tạo.

### So sánh find() và get()

| Tiêu chí | `find(name)` | `get(name)` |
|---|---|---|
| Kiểu search | `Search` | `RequiredSearch` |
| Khi không có meter phù hợp | Trả về `null` hoặc collection rỗng tùy accessor | Ném `MeterNotFoundException` |
| Khi nào nên dùng | Meter có thể chưa tồn tại | Meter bắt buộc phải tồn tại |
| Có hỗ trợ lọc theo tag | Có | Có |
| Có hỗ trợ lấy theo loại meter | Có | Có |

Chọn API theo kỳ vọng của luồng xử lý. Nếu thiếu meter là trạng thái bình thường, `find()` giúp xử lý có điều kiện. Nếu thiếu meter là lỗi cấu hình hoặc lỗi instrumentation, `get()` làm lỗi được phát hiện rõ ràng.

## 4. Tên metric được so khớp như thế nào?

`find(name)` và `get(name)` bắt đầu với tên metric cụ thể. Ví dụ:

```java
Meter meter = registry.find("orders.created").meter();
```

Tên được so khớp theo giá trị tên, không phải truy vấn chuỗi con như tìm kiếm văn bản. Nếu cần tìm nhiều tên theo một điều kiện, API `Search` hỗ trợ predicate cho tên:

```java
import io.micrometer.core.instrument.search.Search;

Collection<Meter> orderMeters = Search.in(registry)
    .name(name -> name.startsWith("orders."))
    .meters();
```

Predicate giúp liệt kê các meter theo quy ước tiền tố, nhưng cần dùng có chủ đích. Với ứng dụng có nhiều meter, truy vấn theo tiền tố rộng có thể trả về collection lớn. Đối với mã nghiệp vụ cần một meter cụ thể, tên chính xác thường rõ ràng và ít tốn công xử lý hơn.

## 5. Tag được so khớp như thế nào?

Các điều kiện tag trong `Search` có nghĩa meter phải chứa những cặp key/value được yêu cầu. Đây là phép khớp theo các tag đã chỉ định, không nhất thiết yêu cầu meter chỉ có đúng các tag đó.

Ví dụ registry có các meter:

```text
orders.created{channel=web}
orders.created{channel=web, region=sg}
orders.created{channel=mobile}
```

Truy vấn:

```java
Collection<Meter> webOrders = registry.find("orders.created")
    .tag("channel", "web")
    .meters();
```

có thể trả về cả hai meter có `channel=web`, bao gồm meter có thêm tag `region=sg`.

Nếu cần đúng một meter, hãy truyền đủ tập tag dự kiến:

```java
Counter webOrdersInSingapore = registry.find("orders.created")
    .tags(
        "channel", "web",
        "region", "sg"
    )
    .counter();
```

Một số điểm cần nhớ:

- `tag(key, value)` lọc theo một cặp tag.
- `tags(key1, value1, key2, value2)` lọc theo nhiều cặp tag.
- `tagKeys(...)` có thể giới hạn kết quả theo sự hiện diện của tag key khi không cần chỉ định value.
- Các điều kiện tag kết hợp với nhau để thu hẹp kết quả.
- Nếu điều kiện còn khớp nhiều meter, `meters()` hoặc accessor collection giúp tránh bỏ sót kết quả.

Đừng giả định `tags(...)` là phép so sánh bằng tuyệt đối toàn bộ tag set. Nếu cần một meter duy nhất, hãy chỉ rõ mọi chiều tag có trong danh tính đó và kiểm tra kết quả trong test.

## 6. Tra cứu theo loại meter

Sau khi chỉ định tên và tag, có thể yêu cầu meter theo loại cụ thể:

| Accessor | Loại meter trả về |
|---|---|
| `counter()` | Counter |
| `gauge()` | Gauge |
| `timer()` | Timer |
| `summary()` | DistributionSummary |
| `functionCounter()` | FunctionCounter |
| `functionTimer()` | FunctionTimer |
| `longTaskTimer()` | LongTaskTimer |
| `timeGauge()` | TimeGauge |
| `meter()` | Meter bất kỳ phù hợp với điều kiện tìm kiếm |

Ví dụ:

```java
Timer requestTimer = registry.find("http.server.requests")
    .tag("method", "GET")
    .timer();

DistributionSummary payloadSize = registry.find("http.request.size")
    .tag("format", "json")
    .summary();

Gauge queueDepth = registry.find("worker.queue.depth")
    .tag("queue", "email")
    .gauge();
```

Với `find()`, nếu không có meter thuộc loại được yêu cầu thì accessor trả về `null`. Với `get()`, nếu không có meter thỏa điều kiện và loại yêu cầu, accessor ném `MeterNotFoundException`.

Điều kiện loại rất hữu ích khi một metric name có nhiều meter theo các tag khác nhau hoặc khi kiểm tra một instrumentation cụ thể. Nó cũng giúp phát hiện sai giả định: nếu mã mong đợi Timer nhưng registry chỉ có Counter cùng tên và tag, truy vấn Timer không thể trả về Counter.

## 7. Ví dụ hoàn chỉnh với SimpleMeterRegistry

`SimpleMeterRegistry` lưu số đo trong bộ nhớ và phù hợp cho ví dụ, kiểm thử tra cứu mà không cần backend bên ngoài.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Collection;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeterRegistryLookupTest {

    @Test
    void findsMeterByNameTagsAndType() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter webOrders = registry.counter(
            "orders.created",
            "channel", "web"
        );
        webOrders.increment(3);

        registry.counter(
            "orders.created",
            "channel", "mobile"
        ).increment(2);

        Counter found = registry.find("orders.created")
            .tag("channel", "web")
            .counter();

        assertThat(found).isSameAs(webOrders);
        assertThat(found.count()).isEqualTo(3.0);

        Collection<Meter> allOrderMeters = registry.find("orders.created")
            .meters();

        assertThat(allOrderMeters).hasSize(2);
    }

    @Test
    void findReturnsNullWhenNoMeterMatches() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter missing = registry.find("orders.created")
            .tag("channel", "web")
            .counter();

        assertThat(missing).isNull();
    }

    @Test
    void getThrowsWhenRequiredMeterDoesNotExist() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        assertThatThrownBy(() ->
            registry.get("orders.created")
                .tag("channel", "web")
                .counter()
        ).isInstanceOf(
            io.micrometer.core.instrument.search.MeterNotFoundException.class
        );
    }

    @Test
    void findsTimerByExactNameAndTags() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Timer timer = registry.timer(
            "orders.processing",
            "operation", "create"
        );
        timer.record(() -> { });

        Timer found = registry.find("orders.processing")
            .tags("operation", "create")
            .timer();

        assertThat(found).isSameAs(timer);
        assertThat(found.count()).isEqualTo(1);
    }
}
```

Các test trên kiểm tra bốn hành vi quan trọng: tìm đúng meter theo tên và tag, lấy tất cả meter phù hợp, xử lý trường hợp không tìm thấy bằng `find()`, và phát hiện meter bắt buộc bị thiếu bằng `get()`.

## 8. Kiểm tra toàn bộ registry khi debug

Khi chưa biết tên meter nào đã được đăng ký, có thể duyệt qua danh sách meter hiện có:

```java
registry.getMeters().forEach(meter -> {
    System.out.printf(
        "name=%s, type=%s, tags=%s%n",
        meter.getId().getName(),
        meter.getId().getType(),
        meter.getId().getTags()
    );
});
```

Hoặc dùng `forEachMeter(...)`:

```java
registry.forEachMeter(meter ->
    log.debug(
        "Meter name={}, type={}, tags={}",
        meter.getId().getName(),
        meter.getId().getType(),
        meter.getId().getTags()
    )
);
```

Đây là cách hữu ích để kiểm tra instrumentation sau khi Spring context khởi động. Có thể xác minh một bean đã đăng ký meter mong muốn, xem tag chung nào đang được áp dụng và tìm các meter trùng tên nhưng khác tag.

Không nên dùng việc duyệt toàn bộ registry trong mỗi request. Đây là thao tác chẩn đoán hoặc kiểm tra, không phải cách lấy số đo tối ưu trong hot path. Nếu ứng dụng cần đọc meter thường xuyên, hãy giữ tham chiếu đến meter sau khi đăng ký hoặc tra cứu trong lúc khởi tạo component.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `find()` tạo meter nếu chưa có | `find()` chỉ tìm meter đang tồn tại |
| `get()` trả về `null` khi không có | `get()` yêu cầu kết quả và ném `MeterNotFoundException` |
| Chỉ truyền một tag là khớp đúng toàn bộ danh tính | Meter có thêm tag khác vẫn có thể phù hợp |
| `meter()` luôn trả về tất cả meter cùng tên | `meter()` trả về một meter đầu tiên phù hợp; dùng `meters()` để lấy tất cả |
| `find(name)` tìm chuỗi con trong tên | Tên chuỗi được so khớp chính xác; dùng predicate nếu cần quy tắc tên |
| Tra cứu registry đọc dữ liệu từ Prometheus | Tra cứu chỉ kiểm tra meter đã đăng ký trong registry hiện tại |
| Tra cứu liên tục trong mỗi lần cập nhật là tối ưu | Nên giữ meter reference trong field khi có thể |

Một lưu ý nữa: `find()` và `get()` không thay thế API đăng ký như `registry.counter(...)`, `registry.timer(...)` hoặc builder `register(registry)`. Các API đăng ký có thể tạo meter mới nếu chưa tồn tại; các API tra cứu chỉ kiểm tra meter đã có.

## 10. Checklist khi tra cứu meter

- [ ] Xác định đúng registry đang chứa meter cần tìm.
- [ ] Dùng tên metric chính xác.
- [ ] Bổ sung các cặp tag cần thiết để thu hẹp kết quả.
- [ ] Nhớ rằng điều kiện tag có thể khớp meter chứa thêm tag khác.
- [ ] Chọn accessor đúng loại meter.
- [ ] Dùng `find()` khi kết quả có thể không tồn tại và xử lý `null`.
- [ ] Dùng `get()` khi meter bắt buộc phải tồn tại và muốn phát hiện thiếu meter.
- [ ] Dùng `meters()` hoặc collection accessor nếu truy vấn có thể khớp nhiều meter.
- [ ] Dùng `getMeters()` hoặc `forEachMeter(...)` khi cần kiểm tra toàn registry.
- [ ] Giữ tham chiếu meter trong component thay vì tra cứu lặp lại trong hot path.

`find()` và `get()` giúp truy vấn meter đã đăng ký theo tên, tag và loại. Dùng `find()` cho trường hợp tùy chọn, `get()` cho điều kiện bắt buộc, và lấy collection khi có thể tồn tại nhiều tổ hợp tag. Hiểu rõ cách khớp tag và phạm vi của registry giúp việc kiểm tra instrumentation chính xác, tránh đọc nhầm meter và hỗ trợ chẩn đoán cấu hình observability.

## Tài liệu tham khảo

- [Micrometer MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html) — mô tả `find(name)`, `get(name)` và các API quản lý meter.
- [Micrometer Search API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/search/Search.html) — điều kiện tìm kiếm theo tên, tag, loại và cách lấy một hoặc nhiều kết quả.
- [Micrometer RequiredSearch API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/search/RequiredSearch.html) — tra cứu bắt buộc và ngoại lệ khi không có meter phù hợp.
- [Micrometer Registry reference](https://docs.micrometer.io/micrometer/reference/concepts/registry.html) — cách registry quản lý meter và khuyến nghị giữ tham chiếu meter khi phù hợp.

