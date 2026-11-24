# Lưu meter hoặc MeterProvider để hạn chế tạo đối tượng lặp lại

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, instrumentation thường nằm trên đường xử lý được gọi hàng trăm hoặc hàng nghìn lần mỗi giây. Nếu mỗi lần xử lý đều tạo `Meter.Builder`, gắn tag, đăng ký meter rồi mới ghi nhận, ứng dụng sẽ tạo thêm object tạm và thực hiện thao tác tra cứu registry lặp lại. Chi phí riêng lẻ có thể nhỏ, nhưng ở hot path nó tạo thêm allocation và công việc cho garbage collector.

Micrometer khuyến nghị giữ tham chiếu đến meter khi tên và tag cố định. Khi một phần tag thay đổi theo kết quả xử lý, `MeterProvider` cho phép tạo trước một template rồi bổ sung các tag biến thiên mà không phải tạo builder mới ở mỗi lần gọi. Cần hiểu registry vẫn định danh meter theo tên và tập tag: tái sử dụng builder hoặc provider không làm mất cardinality nếu tag nhận vô số giá trị khác nhau.

## 1. Phân biệt tạo meter và ghi nhận dữ liệu

Một meter thường được đăng ký một lần trong registry và được cập nhật nhiều lần trong suốt vòng đời ứng dụng. Ví dụ, `Counter` được tạo với tên `orders.created` và tag `channel=web`; mỗi đơn hàng mới chỉ cần gọi `increment()` trên counter đó.

```java
Counter ordersCreated = Counter.builder("orders.created")
    .tag("channel", "web")
    .register(registry);

ordersCreated.increment();
ordersCreated.increment();
```

Hai thao tác increment không tạo hai meter. Chúng cập nhật cùng meter đã đăng ký. Đây là mô hình cần hướng tới: khai báo cấu hình meter ở ranh giới khởi tạo thành phần, sau đó tái sử dụng tham chiếu meter trong các lần xử lý.

Với Spring Boot, bean instrumentation thường là singleton. Có thể inject `MeterRegistry` qua constructor, tạo meter trong constructor và lưu vào field `final`. Service nghiệp vụ chỉ gọi phương thức của bean metrics, không phải tự tạo builder ở mỗi request.

## 2. Registry đã tra cứu và tái sử dụng meter theo định danh

Micrometer quản lý meter trong `MeterRegistry`. Một meter được nhận diện bởi tên cùng tập tag; loại meter và các thuộc tính định nghĩa khác cũng phải nhất quán. Khi đăng ký lại cùng định danh trong cùng registry, registry trả về meter đã tồn tại thay vì tạo một meter độc lập khác cho cùng tên/tag.

```java
Counter first = Counter.builder("orders.created")
    .tag("channel", "web")
    .register(registry);

Counter second = Counter.builder("orders.created")
    .tag("channel", "web")
    .register(registry);

// first và second tham chiếu cùng meter trong registry.
```

Điều đó có nghĩa gọi `register()` lặp lại với cùng định danh không nhất thiết làm số meter tăng. Tuy nhiên, mỗi lần gọi builder vẫn tạo `Builder` và có thể tạo các object tag tạm; registry vẫn phải thực hiện tra cứu để tìm meter. Ở hot path, giữ tham chiếu trực tiếp giúp tránh cả bước dựng builder lẫn tra cứu lặp lại.

Nếu tag khác nhau, đó là một định danh khác và registry sẽ tạo hoặc lấy một meter khác. Ví dụ `channel=web` và `channel=mobile` là hai time series riêng. Đây là hành vi đúng khi các chiều phân tích có tập giá trị hữu hạn, nhưng nguy hiểm nếu tag lấy từ ID duy nhất của từng request.

## 3. Trường hợp tag cố định: lưu meter trong field

Nếu tên và tag đã biết khi bean khởi tạo, hãy tạo meter một lần rồi giữ trong field:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Counter accepted;
    private final Counter rejected;
    private final Timer processing;

    public CheckoutMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("checkout.requests")
            .description("Accepted checkout requests")
            .tag("result", "accepted")
            .register(registry);

        this.rejected = Counter.builder("checkout.requests")
            .description("Rejected checkout requests")
            .tag("result", "rejected")
            .register(registry);

        this.processing = Timer.builder("checkout.processing")
            .description("Time spent processing checkout requests")
            .register(registry);
    }

    public void accepted() {
        accepted.increment();
    }

    public void rejected() {
        rejected.increment();
    }

    public <T> T recordProcessing(java.util.function.Supplier<T> operation) {
        return processing.record(operation);
    }
}
```

Ở đây, `accepted`, `rejected` và `processing` được tạo một lần khi Spring khởi tạo bean. Mỗi request chỉ gọi `increment()` hoặc `record(...)`. Đây là lựa chọn đơn giản và thường có chi phí thấp nhất khi tag không thay đổi.

Không cần lưu meter trong một map nếu chỉ có một vài meter cố định; field `final` giúp code rõ ràng và tránh tra cứu theo tên/tag ở mỗi lần xử lý.

## 4. Cách thường gây allocation trong hot path

Đoạn code sau tạo builder mới mỗi lần method được gọi:

```java
public void jobCompleted(String status) {
    Counter.builder("jobs.completed")
        .tag("job.type", "invoice")
        .tag("status", status)
        .register(registry)
        .increment();
}
```

Nếu method chạy rất thường xuyên, mỗi lần gọi sẽ tạo builder và các cấu trúc tag, sau đó thực hiện tra cứu/đăng ký vào registry. Với một tập `status` nhỏ, registry vẫn có thể trả lại meter cũ cho cùng định danh; vấn đề còn lại là allocation và lookup lặp lại.

Có thể thay bằng `MeterProvider` để tạo template một lần, hoặc tạo sẵn meter cho mọi trạng thái hợp lệ nếu tập giá trị rất nhỏ và cố định. Không nên kết luận rằng mỗi lần gọi `register()` luôn tạo một meter mới; registry được thiết kế để tái sử dụng meter cùng định danh.

## 5. MeterProvider là gì?

`Meter.MeterProvider<T>` là một interface tiện ích để tạo hoặc lấy meter từ một template chung, chỉ bổ sung các tag thay đổi. Builder được cấu hình một lần với tên, description, base unit và các tag cố định; `withRegistry(registry)` tạo provider. Sau đó `withTag(...)` hoặc `withTags(...)` trả về meter theo các tag bổ sung. Provider không phải một cache meter riêng; registry vẫn quản lý việc tạo mới hoặc trả lại meter đã có theo định danh.

`MeterProvider` có từ Micrometer 1.12.0. API này hiện được hỗ trợ cho `Counter`, `Timer`, `LongTaskTimer` và `DistributionSummary`. Không phải mọi loại meter đều có `withRegistry(...)` trả về provider.

Ví dụ tạo provider cho counter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter.MeterProvider;
import io.micrometer.core.instrument.MeterRegistry;

public class JobMetrics {
    private final MeterProvider<Counter> completedJobs;

    public JobMetrics(MeterRegistry registry) {
        this.completedJobs = Counter.builder("jobs.completed")
            .description("Number of completed jobs")
            .tag("job.type", "invoice")
            .withRegistry(registry);
    }

    public void completed(String status) {
        completedJobs.withTag("status", normalizeStatus(status)).increment();
    }

    private String normalizeStatus(String status) {
        return switch (status) {
            case "success", "failure", "cancelled" -> status;
            default -> "other";
        };
    }
}
```

Builder và các thuộc tính cố định chỉ được cấu hình một lần trong constructor. Mỗi lần hoàn tất job, code lấy meter tương ứng với tag `status` bằng provider rồi gọi `increment()`.

## 6. Dùng MeterProvider cho Timer khi tag chỉ biết sau khi xử lý

Một trường hợp thường gặp là kết quả hoặc trạng thái chỉ được biết sau khi thao tác kết thúc. `Timer.Sample` cho phép bắt đầu đo trước, sau đó chọn timer đích khi đã có kết quả:

```java
import io.micrometer.core.instrument.Meter.MeterProvider;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class JobExecutionMetrics {
    private final MeterRegistry registry;
    private final MeterProvider<Timer> executionTimers;

    public JobExecutionMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.executionTimers = Timer.builder("job.execution")
            .description("Execution duration of background jobs")
            .tag("job.name", "invoice")
            .withRegistry(registry);
    }

    public Result execute(Job job) {
        Timer.Sample sample = Timer.start(registry);
        String status = "failure";
        try {
            Result result = job.execute();
            status = normalizeStatus(result.status());
            return result;
        }
        finally {
            sample.stop(executionTimers.withTag("status", status));
        }
    }

    private String normalizeStatus(String status) {
        return switch (status) {
            case "success", "failure", "cancelled" -> status;
            default -> "other";
        };
    }
}
```

`Timer.Sample` đo từ lúc `Timer.start(registry)` đến khi `stop(timer)` được gọi. Provider chọn timer có tag trạng thái tương ứng mà không cần dựng `Timer.Builder` sau mỗi job. Nếu thao tác ném exception, `finally` vẫn dừng sample và ghi thời lượng vào timer `status=failure` trước khi exception truyền về caller.

Nếu cần đo cả checked exception, hãy mở rộng chữ ký và nhánh xử lý phù hợp với API nghiệp vụ. Mọi đường kết thúc cần dừng sample đúng một lần. Không gọi `stop()` hai lần cho cùng một sample.

## 7. Khi nào dùng registry lookup trực tiếp?

Nếu tag thay đổi theo ngữ cảnh, không phải lúc nào cũng cần `MeterProvider`. Có thể gọi trực tiếp API registry:

```java
registry.counter(
    "jobs.completed",
    "job.type", "invoice",
    "status", status
).increment();
```

Micrometer registry tra cứu meter theo định danh và trả về meter đã có nếu tồn tại. Tài liệu Micrometer lưu ý việc lookup này thường là một hash lookup và đủ nhanh cho phần lớn trường hợp. Nếu cần tối ưu allocation ở hot path, `MeterProvider` tránh tạo builder mới; nếu tag set nhỏ và rất thường dùng, có thể giữ meter cụ thể trong map có giới hạn.

Không nên tối ưu mù quáng. Chọn cách đơn giản trước, sau đó đo allocation rate và CPU bằng profiler hoặc benchmark trong workload đại diện. Nếu chi phí lookup không đáng kể so với công việc chính, giữ code dễ hiểu có thể tốt hơn việc thêm cache thủ công.

## 8. So sánh ba cách tái sử dụng

| Cách | Phù hợp khi | Chi phí mỗi lần ghi | Lưu ý |
| --- | --- | --- | --- |
| Giữ `Counter`/`Timer` trong field | Tên và toàn bộ tag cố định | Gọi trực tiếp meter | Lựa chọn ưu tiên cho tag tĩnh |
| Giữ `MeterProvider` | Một phần tag thay đổi theo tập giá trị có kiểm soát | Lấy meter theo tag rồi ghi | Tránh tạo builder mỗi lần; vẫn có lookup theo định danh |
| Gọi `registry.counter(...)`/`registry.timer(...)` | Cần API ngắn gọn, tần suất vừa phải hoặc tag được xác định tại chỗ | Registry lookup | Thường đủ nhanh cho đa số use case |

Với tập giá trị động rất nhỏ, cố định và được gọi cực thường xuyên, có thể khởi tạo sẵn `EnumMap<Status, Counter>` trong constructor. Cách này bỏ lookup ở mỗi lần ghi nhưng cần quản lý tập meter hữu hạn rõ ràng. `MeterProvider` thường là thỏa hiệp tốt giữa cấu hình dùng chung và tag động; `withTag()` vẫn phải tạo/chuẩn hóa tag và tra cứu meter trong registry, nên không có nghĩa là hoàn toàn không còn allocation.

Ví dụ tạo sẵn meter cho một enum trạng thái:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Collections;
import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;

enum JobStatus {
    SUCCESS, FAILURE, CANCELLED
}

public class JobStatusMetrics {
    private final Map<JobStatus, Counter> counters;

    public JobStatusMetrics(MeterRegistry registry) {
        EnumMap<JobStatus, Counter> byStatus = new EnumMap<>(JobStatus.class);
        for (JobStatus status : JobStatus.values()) {
            byStatus.put(status, Counter.builder("jobs.completed")
                .tag("status", status.name().toLowerCase(Locale.ROOT))
                .register(registry));
        }
        this.counters = Collections.unmodifiableMap(byStatus);
    }

    public void completed(JobStatus status) {
        counters.get(status).increment();
    }
}
```

Vì số trạng thái được cố định bởi enum, mọi meter được đăng ký trước và lần ghi chỉ tra cứu trong map. Cách này có thể phù hợp với hot path cực nóng; cần cân nhắc chi phí và độ phức tạp so với `MeterProvider`.

## 9. MeterProvider không giải quyết cardinality cao

Provider giúp tái sử dụng template và tránh tạo builder lặp lại; nó không gom các giá trị tag khác nhau vào cùng một meter. Mỗi tổ hợp tên và tag khác nhau vẫn là một meter riêng trong registry.

Ví dụ nguy hiểm:

```java
// Không dùng ID duy nhất cho mỗi job làm tag.
completedJobs.withTag("job.id", jobId).increment();
```

Nếu mỗi job có ID riêng, số meter/time series tăng theo số job. Dù chỉ có một `MeterProvider`, registry vẫn phải đăng ký hoặc tra cứu từng tổ hợp tag và giữ meter tương ứng. Điều đó làm tăng bộ nhớ, chi phí scrape, ingest và truy vấn backend.

Hãy dùng tag có tập giá trị hữu hạn như `job.type`, `status`, `region` hoặc `result`. Đưa `jobId`, `userId`, request ID, email và URL thô vào log hoặc trace khi cần truy vết một thực thể cụ thể.

## 10. Chuẩn hóa giá trị tag trước khi lấy meter

Giá trị tag nên được chuẩn hóa về tập cho phép trước khi truyền vào provider. Nếu lấy trực tiếp chuỗi do người dùng hoặc hệ thống bên ngoài cung cấp, có thể phát sinh hàng nghìn giá trị gần giống nhau do chữ hoa/thường, khoảng trắng hoặc dữ liệu bất thường.

```java
import java.util.Locale;

private String normalizeChannel(String channel) {
    if (channel == null) {
        return "unknown";
    }

    return switch (channel.toLowerCase(Locale.ROOT)) {
        case "web", "mobile", "partner" -> channel.toLowerCase(Locale.ROOT);
        default -> "other";
    };
}
```

Chuẩn hóa vừa kiểm soát cardinality vừa giúp dashboard có nhóm nhất quán. Không dùng giá trị `null` hoặc chuỗi rỗng như một cách biểu diễn nhiều trạng thái khác nhau; hãy quy về một giá trị như `unknown` hoặc `other` theo quy ước nghiệp vụ.

## 11. Meter và MeterProvider có thể dùng chung giữa các thread

Trong ứng dụng server, nhiều request có thể cập nhật cùng một meter đồng thời. Các meter Micrometer tiêu chuẩn và registry được thiết kế để sử dụng trong môi trường đa luồng. Vì vậy, có thể lưu meter/provider trong field `final` của bean singleton và gọi chúng từ nhiều thread.

Không tạo một meter riêng cho mỗi thread chỉ để tránh tranh chấp nếu không có yêu cầu đo riêng. Làm vậy thường tạo thêm series và khiến số liệu bị phân mảnh. Nếu cần tách theo worker pool, dùng tag `executor` với tập tên pool hữu hạn.

Đối với `MeterProvider`, giữ một provider dùng chung và gọi `withTag(s)` cho mỗi lần cần meter. Provider không phải nơi lưu trạng thái nghiệp vụ của request; nó chỉ là cách tạo/lấy meter từ cấu hình chung. Provider dùng chung được với nhiều thread vì các meter và registry Micrometer tiêu chuẩn hỗ trợ cập nhật đồng thời; dữ liệu nghiệp vụ riêng của request vẫn phải nằm trong biến cục bộ hoặc context phù hợp.

## 12. Kiểm thử tái sử dụng meter và MeterProvider

Có thể dùng `SimpleMeterRegistry` để kiểm tra meter được cập nhật đúng và các tag hợp lệ tạo đúng nhóm meter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter.MeterProvider;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MeterProviderTest {
    @Test
    void reusesTemplateForBoundedStatusValues() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        MeterProvider<Counter> provider = Counter.builder("jobs.completed")
            .tag("job.type", "invoice")
            .withRegistry(registry);

        provider.withTag("status", "success").increment();
        provider.withTag("status", "success").increment();
        provider.withTag("status", "failure").increment();

        assertEquals(2.0, registry.get("jobs.completed")
            .tag("job.type", "invoice")
            .tag("status", "success")
            .counter().count(), 0.0);

        assertEquals(1.0, registry.get("jobs.completed")
            .tag("job.type", "invoice")
            .tag("status", "failure")
            .counter().count(), 0.0);
    }
}
```

Test xác minh hai lần ghi cùng tag `success` cập nhật cùng counter và `failure` có meter riêng. Nếu cần kiểm tra số meter, có thể kiểm tra `registry.getMeters()` sau khi đã ghi nhận từng nhóm giá trị hợp lệ. Không nên viết test phụ thuộc implementation nội bộ của hash map trong registry.

## 13. Đo hiệu quả trước và sau tối ưu

Mục tiêu của việc giữ meter/provider là giảm allocation và công việc lặp lại trong hot path, không phải thay đổi ý nghĩa metrics. Khi đánh giá:

- Giữ nguyên tên, tag và số lần ghi nhận giữa hai phiên bản.
- So sánh allocation rate, số object `Meter.Builder`/tag được tạo và CPU.
- Dùng workload có tần suất và phân phối tag gần production.
- Quan sát GC pause và throughput khi chạy đủ lâu.
- Kiểm tra số meter/time series không tăng ngoài dự kiến.

Microbenchmark cần tránh đo lẫn thời gian khởi tạo registry và warm-up vào thời gian ghi nhận. Trong hệ thống thật, profiler hoặc allocation recording có thể cho biết builder/tag có thực sự là nguồn allocation đáng kể hay không.

Không đặt mục tiêu loại bỏ mọi allocation. Micrometer và registry vẫn có thể tạo object khi lần đầu đăng ký một định danh tag mới. Mục tiêu là tránh tạo builder lặp lại trên mỗi thao tác và giữ số tổ hợp meter trong phạm vi được kiểm soát.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Có builder mới mỗi request | Builder đang được tạo trong method hot path thay vì constructor/khởi tạo bean |
| Registry có ít meter nhưng allocation vẫn cao | Đăng ký cùng định danh trả lại meter cũ, nhưng builder và tag tạm vẫn được tạo lặp lại |
| Số meter tăng liên tục | Tag có giá trị duy nhất như ID, URL hoặc dữ liệu người dùng |
| MeterProvider không giảm số series | Provider tránh builder allocation, không loại bỏ meter theo từng tag khác nhau |
| Dữ liệu không được chia theo status | Status chưa được đưa vào `withTag()` hoặc code luôn dùng một meter cố định |
| Không compile được `withRegistry()` | Micrometer version cũ hơn 1.12.0 hoặc loại meter không hỗ trợ MeterProvider |
| Timer ghi nhận sai trạng thái | Không chọn timer theo kết quả cuối hoặc sample không được stop đúng một lần |
| Dùng map cache nhưng bộ nhớ tăng | Map lưu tag value không giới hạn và giữ thêm tham chiếu tới meter |

Khi điều tra, kiểm tra phiên bản Micrometer, vị trí tạo builder, tên/tag thực tế, số meter trong registry và allocation profile. Đừng nhầm việc registry tái sử dụng meter cùng định danh với việc builder không tạo object tạm.

## 15. Nguyên tắc áp dụng

Với tag cố định, tạo meter trong constructor hoặc giai đoạn khởi tạo và lưu vào field `final`. Với tag thay đổi nhưng có tập giá trị hữu hạn, tạo `MeterProvider` một lần bằng `withRegistry(registry)` rồi lấy meter bằng `withTag()` hoặc `withTags()`. Nếu chỉ cần lookup đơn giản và không nằm trên hot path, API trực tiếp của registry thường đã đủ nhanh.

`MeterProvider` có từ Micrometer 1.12.0 và hỗ trợ `Counter`, `Timer`, `LongTaskTimer` cùng `DistributionSummary`. Nó tránh tạo builder lặp lại nhưng không loại bỏ lookup theo định danh và không giải quyết cardinality cao. Chuẩn hóa tag, giới hạn tập giá trị, dùng chung meter/provider an toàn giữa các thread và đo bằng profiler trước khi tối ưu sâu hơn.

## Tài liệu tham khảo

- [Micrometer: Meter Provider](https://docs.micrometer.io/micrometer/reference/concepts/meter-provider.html)
- [Micrometer: Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer API: Meter.MeterProvider](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Meter.MeterProvider.html)
