# Xung đột khi cùng danh tính được đăng ký bằng các loại meter khác nhau

Trong Micrometer, một meter được đăng ký vào `MeterRegistry` bằng tên metric và các tag mô tả ngữ cảnh. Registry dùng danh tính đó để tìm meter đã tồn tại hoặc tạo meter mới. Vì vậy, cùng một danh tính không thể đại diện ổn định cho hai loại phép đo có ngữ nghĩa khác nhau, chẳng hạn vừa là `Counter` vừa là `Gauge`.

Xung đột thường xuất hiện khi nhiều thành phần cùng instrument một hoạt động: một nơi đăng ký counter, nơi khác đăng ký gauge với cùng tên và tag; hoặc một meter tùy chỉnh trùng với meter do Spring Boot tự động tạo. Khi đó, ứng dụng có thể gặp lỗi ngay tại thời điểm đăng ký, hoặc một lần đăng ký bị bỏ qua nếu đó là trường hợp đăng ký lặp cùng loại. Với registry xuất metrics, còn có thể xuất hiện ràng buộc bổ sung ở cấp metric family của backend.

Bài học này giải thích cách nhận diện xung đột, cách tái hiện bằng `SimpleMeterRegistry`, cách tìm nguồn đăng ký trùng và cách thiết kế tên metric để tránh xung đột.

## 1. Danh tính của meter trong Micrometer

Trong một `MeterRegistry`, danh tính của meter chủ yếu được xác định bởi:

- **Tên metric:** tên ổn định mô tả đại lượng cần đo, ví dụ `jobs.completed`.
- **Tập tag:** các cặp key/value mô tả chiều phân tích, ví dụ `queue=email` hoặc `region=ap-southeast-1`.

Có thể hình dung danh tính như sau:

```text
Meter ID = metric name + tag set
```

Ví dụ:

| Tên | Tags | Danh tính |
|---|---|---|
| `jobs.completed` | `queue=email` | `jobs.completed{queue=email}` |
| `jobs.completed` | `queue=video` | `jobs.completed{queue=video}` |
| `jobs.completed` | `queue=email, region=ap-southeast-1` | Một danh tính khác |
| `jobs.failed` | `queue=email` | Một danh tính khác |

Hai meter có cùng tên nhưng tag khác nhau thường là hai meter riêng biệt trong registry. Ngược lại, nếu cả tên và tập tag giống nhau, registry coi chúng là cùng một danh tính. Loại meter không phải là cách để tạo một danh tính độc lập thứ hai cho cùng tên và tag.

Một registry có thể áp dụng `MeterFilter` để đổi tên hoặc chuẩn hóa tag trước khi lưu meter. Do đó, hai meter ban đầu khác nhau vẫn có thể trở thành cùng danh tính sau khi filter biến đổi. Khi điều tra, cần xem cả tên và tag sau khi áp dụng filter.

Danh tính được quản lý trong phạm vi từng `MeterRegistry`. Hai registry độc lập có thể chứa meter cùng tên và tag. Tuy nhiên, nếu chúng cùng export sang một backend hoặc cùng một namespace, các quy tắc của backend vẫn cần được đáp ứng.

## 2. Vì sao không thể dùng cùng danh tính cho nhiều loại meter?

Mỗi loại meter có cách ghi nhận và diễn giải khác nhau:

| Loại meter | Ý nghĩa | Cách cập nhật |
|---|---|---|
| **Counter** | Số sự kiện tích lũy | Tăng bằng `increment()` |
| **Gauge** | Giá trị trạng thái hiện tại | Đọc từ một đối tượng hoặc hàm cung cấp giá trị |
| **Timer** | Số lần thực hiện và thời lượng | Ghi nhận thời gian bằng `record(...)` |
| **DistributionSummary** | Phân bố của một đại lượng số | Ghi nhận mẫu bằng `record(value)` |

Giả sử ứng dụng đăng ký:

```java
Counter completed = registry.counter(
    "jobs.completed",
    "queue", "email"
);
```

Một lớp khác lại đăng ký:

```java
Gauge.builder(
        "jobs.completed",
        queueState,
        QueueState::size
    )
    .tag("queue", "email")
    .register(registry);
```

Cả hai lời gọi đều yêu cầu cùng tên `jobs.completed` và cùng tag `queue=email`, nhưng một meter là Counter và meter còn lại là Gauge. Registry đã có meter cho danh tính này và không thể trả về một đối tượng vừa có hành vi Counter vừa có hành vi Gauge.

Trong các phiên bản Micrometer hiện hành, quy trình đăng ký kiểm tra loại meter đã tồn tại. Khi loại được yêu cầu không khớp với loại của meter hiện có, `MeterRegistry` ném `IllegalArgumentException` với thông báo cho biết đã có meter khác loại cùng tên. Chi tiết thông báo có thể thay đổi theo phiên bản, nhưng nguyên nhân là cùng danh tính đang được dùng cho các loại meter không tương thích.

## 3. Phân biệt đăng ký lặp và xung đột loại meter

Không phải mọi lần đăng ký lại đều là xung đột loại. Cần phân biệt các trường hợp sau:

| Trường hợp | Kết quả thường gặp |
|---|---|
| Cùng tên, cùng tag, cùng loại meter | Registry trả về meter đã tồn tại; không tạo một meter độc lập thứ hai |
| Cùng tên, cùng tag, khác loại meter | Đăng ký thất bại do loại meter không khớp; thường ném `IllegalArgumentException` |
| Cùng tên, tag khác nhau, cùng loại meter | Registry có thể quản lý các meter riêng biệt |
| Cùng tên, tag khác nhau, khác loại meter | Có thể tồn tại như các ID riêng trong core registry, nhưng backend có thể áp dụng quy tắc cùng metric family phải cùng loại |
| Cùng danh tính trong hai registry độc lập | Mỗi registry quản lý meter riêng; việc export vẫn phụ thuộc quy tắc backend |

Đăng ký lặp một Gauge hoặc function-tracking meter với cùng danh tính cũng cần chú ý. Registry chỉ giữ một meter cho danh tính đó; việc đăng ký lại không thay thế đối tượng hoặc hàm đang được theo dõi. Micrometer có thể ghi cảnh báo rằng Gauge, FunctionCounter hoặc FunctionTimer đã được đăng ký và lần đăng ký mới bị bỏ qua.

Ví dụ, nếu một Gauge đã theo dõi `queueA::size`, việc đăng ký lại cùng tên và tag với `queueB::size` không có nghĩa registry chuyển sang theo dõi `queueB`. Gauge ban đầu vẫn là meter được giữ lại. Đây là lỗi dễ bị nhầm với xung đột loại vì log có thể chỉ nói registration bị ignored.

## 4. Tái hiện xung đột bằng SimpleMeterRegistry

Có thể tái hiện lỗi trong unit test mà không cần kết nối Prometheus hay một hệ thống giám sát bên ngoài.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeterIdentityConflictTest {

    @Test
    void rejectsDifferentMeterTypesForTheSameIdentity() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter counter = registry.counter(
            "jobs.completed",
            "queue", "email"
        );
        counter.increment();

        AtomicInteger queueSize = new AtomicInteger(3);

        assertThatThrownBy(() ->
            Gauge.builder(
                    "jobs.completed",
                    queueSize,
                    AtomicInteger::get
                )
                .tags(Tags.of("queue", "email"))
                .register(registry)
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
```

Test tạo Counter trước, sau đó cố gắng tạo Gauge với cùng tên và tag. Lời gọi đăng ký Gauge phải thất bại vì danh tính đó đã thuộc về Counter.

Có thể kiểm tra trường hợp đăng ký cùng loại để hiểu registry tái sử dụng meter:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void reusesMeterWithTheSameIdentityAndType() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    Counter first = registry.counter(
        "jobs.completed",
        "queue", "email"
    );

    Counter second = registry.counter(
        "jobs.completed",
        "queue", "email"
    );

    assertThat(second).isSameAs(first);
}
```

Kết quả mong đợi là hai biến tham chiếu đến cùng một Counter trong registry. Nếu hai lớp đều gọi `increment()`, chúng cùng cập nhật một meter. Vì vậy, đăng ký lặp cùng loại có thể không gây exception nhưng vẫn làm số đo tăng từ nhiều nơi ngoài dự kiến. Đây là vấn đề về quyền sở hữu instrumentation và ngữ nghĩa số liệu, cần được xem xét ngay cả khi ứng dụng không gặp lỗi runtime.

## 5. Những tình huống thực tế gây xung đột

### Một meter tự động và một meter tùy chỉnh trùng nhau

Spring Boot Actuator và các instrumentation tích hợp có thể tự đăng ký meter cho HTTP server, JVM, datasource, cache hoặc các thành phần nền tảng khác. Nếu mã ứng dụng tạo meter tùy chỉnh với cùng tên và tag sau khi filter áp dụng, hai nơi có thể đụng cùng danh tính.

Ví dụ, ứng dụng tự tạo một Counter có tên đã được một instrumentation khác dùng làm Timer. Khi cả hai đăng ký vào cùng registry với cùng tag, đăng ký thứ hai không phù hợp với loại đã tồn tại.

Cách xử lý là kiểm tra các meter có sẵn trước khi tạo meter tùy chỉnh, giữ nguyên tên chuẩn của instrumentation tự động và chọn tên riêng có ý nghĩa cho số đo nghiệp vụ.

### Hai lớp nghiệp vụ dùng chung một tên nhưng hiểu khác ý nghĩa

Một lớp dùng `payment.amount` để đo tổng giá trị thanh toán bằng DistributionSummary; lớp khác dùng cùng tên để đo số giao dịch bằng Counter. Cùng tên nhưng đơn vị và ý nghĩa khác nhau khiến dashboard không thể diễn giải thống nhất.

Ngay cả khi đổi tag để hai ID khác nhau, việc đặt cùng tên cho hai đại lượng không cùng ngữ nghĩa vẫn gây khó khăn cho backend và người đọc dashboard. Hãy đặt tên riêng, ví dụ:

- `payment.amount`: phân bố giá trị thanh toán.
- `payment.transactions`: số giao dịch.

### MeterFilter làm hai danh tính nhập thành một

Một filter có thể chuẩn hóa tên hoặc tag. Ví dụ, hai tag `region=SG` và `region=Singapore` có thể bị chuẩn hóa thành cùng giá trị `region=Singapore`. Nếu hai nơi đăng ký hai loại meter khác nhau, chúng có thể đụng nhau sau bước mapping.

Khi thêm filter, cần đánh giá tác động lên tất cả meter hiện có. Không nên loại bỏ tag hoặc gộp giá trị tag nếu việc đó khiến các meter khác loại hoặc khác ý nghĩa trở thành cùng danh tính.

### Hai meter khác ID nhưng đụng metric family khi export

Danh tính ở Micrometer core và quy tắc đặt tên của backend là hai lớp khác nhau. Một Timer có thể được chuyển thành nhiều chuỗi metric khi export, với hậu tố cho đơn vị thời gian và thống kê. Một meter khác có tên trùng với một tên đã được tạo ra trong quá trình chuyển đổi có thể gây xung đột ở backend, dù hai `Meter.Id` ban đầu không giống nhau.

Với Prometheus, các chuỗi thuộc cùng metric family phải tuân theo loại và cấu trúc descriptor nhất quán. Vì vậy, không chỉ kiểm tra tên và tag trong Java; cần xem cả tên sau naming convention và định dạng mà registry xuất ra. Quy tắc kiểm tra và thời điểm phát hiện có thể khác nhau giữa các phiên bản registry.

## 6. Cách tìm nguồn gây xung đột

Khi gặp lỗi đăng ký meter khác loại, hãy điều tra theo thứ tự:

1. **Đọc đầy đủ exception và log.** Xác định tên meter, loại hiện có và loại đang được yêu cầu. Ghi lại cả tag nếu thông báo hoặc log cung cấp.
2. **Tìm mọi nơi đăng ký tên đó.** Tìm `registry.counter(...)`, `registry.gauge(...)`, `registry.timer(...)`, `DistributionSummary.builder(...)`, custom meter và các annotation instrumentation.
3. **Kiểm tra instrumentation tự động.** Xem Actuator, Spring Integration, thư viện client, datasource, cache hoặc các thành phần khác có đăng ký meter tương ứng không.
4. **Kiểm tra MeterFilter.** Xem filter có đổi tên, thêm, xóa hoặc chuẩn hóa tag làm hai ID khác nhau nhập thành một không.
5. **Kiểm tra registry thực tế.** Liệt kê các meter đã đăng ký và xem loại, tên, tag của chúng.
6. **Kiểm tra tên sau khi export.** Nếu lỗi xuất hiện ở bước scrape hoặc publish, xem naming convention, hậu tố và quy tắc của backend.

Có thể in các meter đang có trong registry khi debug:

```java
registry.getMeters().forEach(meter -> {
    System.out.println(
        "name=" + meter.getId().getName()
            + ", type=" + meter.getId().getType()
            + ", tags=" + meter.getId().getTags()
    );
});
```

Đoạn mã này hữu ích trong môi trường kiểm thử hoặc debug. Tránh in toàn bộ meter liên tục trong luồng xử lý production vì registry có thể chứa nhiều meter và tag.

## 7. Thiết kế để tránh xung đột

### Chọn tên theo đại lượng và ngữ nghĩa

Tên metric cần phản ánh rõ đại lượng được đo. Không tái sử dụng tên chỉ vì các số đo cùng liên quan đến một nghiệp vụ.

Ví dụ:

| Đại lượng | Loại meter phù hợp | Tên đề xuất |
|---|---|---|
| Số job hoàn tất | Counter | `jobs.completed` |
| Số job đang chờ | Gauge | `jobs.queue.depth` |
| Thời gian xử lý job | Timer | `jobs.processing` |
| Kích thước payload job | DistributionSummary | `jobs.payload.size` |

Cách đặt tên này làm rõ sự khác biệt giữa sự kiện, trạng thái, thời lượng và phân bố giá trị.

### Dùng tag cho chiều phân tích, không dùng tag để che xung đột

Tag phù hợp để phân nhóm cùng một đại lượng, ví dụ `queue=email` và `queue=video` cho số job hoàn tất. Tag không nên được dùng chỉ để né xung đột giữa Counter và Gauge.

Thêm tag `type=counter` hoặc `type=gauge` để tách hai phép đo cùng tên thường tạo ra một metric family khó hiểu, và có thể vẫn vi phạm quy tắc của backend. Khi ngữ nghĩa khác nhau, hãy đổi tên metric.

### Quy định nơi sở hữu instrumentation

Với mỗi metric quan trọng, nên xác định thành phần chịu trách nhiệm đăng ký và cập nhật nó. Một meter có thể được nhiều lớp sử dụng thông qua cùng đối tượng Counter hoặc Timer đã được inject, nhưng không nên để các lớp tự đăng ký lại cùng tên với ngữ nghĩa riêng.

Có thể tạo một component chuyên trách metrics nghiệp vụ, cung cấp các phương thức như `recordJobCompleted()`, `recordQueueDepth(...)` hoặc `recordJobDuration(...)`. Các service gọi phương thức đó thay vì tự xây dựng meter ở nhiều vị trí.

### Chuẩn hóa tên và tag trước khi đăng ký

Tập tag cần ổn định, có số lượng giá trị kiểm soát và nhất quán giữa các nơi instrument. Nếu có MeterFilter để chuẩn hóa tag, hãy kiểm tra xem phép biến đổi có thể làm các meter trùng danh tính hay không.

Với Prometheus, các meter cùng metric family cũng cần có bộ tag key nhất quán và loại dữ liệu phù hợp. Do đó, quy ước đặt tên và tag nên được thiết kế cùng backend xuất metrics.

## 8. Phân biệt lỗi ở Micrometer core và lỗi ở backend

| Lớp phát hiện | Dấu hiệu | Hướng kiểm tra |
|---|---|---|
| Micrometer core | `IllegalArgumentException` khi đăng ký cùng ID bằng class meter khác | Tên, tag, thứ tự đăng ký và MeterFilter |
| Micrometer core, đăng ký lặp cùng loại | Cảnh báo Gauge hoặc function meter đã tồn tại; lần đăng ký mới bị bỏ qua | Nơi tạo meter đầu tiên và đối tượng đang được theo dõi |
| Registry exporter | Lỗi khi đăng ký, publish hoặc scrape dù ID core khác nhau | Naming convention, metric family, loại và descriptor sau khi export |
| Dashboard/backend query | Metric không xuất hiện hoặc bị gộp ngoài dự kiến | Tên sau chuyển đổi, tag keys, quy tắc tổng hợp và cấu hình backend |

Không nên xử lý mọi lỗi bằng cách đổi tag ngẫu nhiên hoặc xóa meter khỏi registry. Trước hết cần xác định xung đột nằm ở danh tính Micrometer hay ở tên và descriptor sau khi export.

## 9. Checklist kiểm tra

- [ ] Xác nhận tên metric và toàn bộ tag của hai lần đăng ký.
- [ ] Xác định loại meter đã được đăng ký trước và loại đang được yêu cầu.
- [ ] Kiểm tra các instrumentation tự động và meter tùy chỉnh cùng dùng registry.
- [ ] Kiểm tra MeterFilter có làm thay đổi tên hoặc tag không.
- [ ] Dùng `SimpleMeterRegistry` để viết test tái hiện xung đột.
- [ ] Dùng một tên metric riêng cho mỗi đại lượng có ngữ nghĩa khác nhau.
- [ ] Không dùng tag `type` để che việc dùng sai tên metric.
- [ ] Xác nhận các meter cùng metric family đáp ứng quy tắc của backend.
- [ ] Kiểm tra tên và tag sau khi registry chuyển đổi để export.
- [ ] Xác định một nơi sở hữu việc đăng ký và cập nhật meter nghiệp vụ.

Khi cùng một danh tính được đăng ký bằng các loại meter khác nhau, registry không thể diễn giải danh tính đó theo hai ngữ nghĩa độc lập. Hãy xác định rõ đại lượng cần đo, chọn một loại meter phù hợp và đặt tên riêng khi ý nghĩa khác nhau. Kết hợp kiểm tra ID sau filter, kiểm thử bằng SimpleMeterRegistry và xác minh định dạng export sẽ giúp phát hiện xung đột sớm, trước khi nó ảnh hưởng đến việc thu thập và diễn giải metrics.

## Tài liệu tham khảo

- [Micrometer MeterRegistry source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java) — cách registry tìm meter theo ID và kiểm tra loại khi đăng ký.
- [Micrometer Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html) — vai trò của registry và nguyên tắc một meter cho mỗi tổ hợp tên và tag.
- [Micrometer Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html) — hành vi khi đăng ký lại Gauge với cùng danh tính.
- [Micrometer 1.18 Migration Guide](https://github.com/micrometer-metrics/micrometer/wiki/1.18-Migration-Guide) — các kiểm tra bổ sung của Prometheus registry đối với xung đột metric family.

