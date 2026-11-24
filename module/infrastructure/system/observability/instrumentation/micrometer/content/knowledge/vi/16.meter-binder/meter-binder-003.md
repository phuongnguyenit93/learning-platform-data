# Vòng đời binder, registry và tài nguyên được quan sát

`MeterBinder` là cơ chế đóng gói việc đăng ký một nhóm meter vào `MeterRegistry`. Binder thường biết cách đọc một tài nguyên hoặc một thành phần ứng dụng, sau đó đăng ký các `Counter`, `Gauge`, `Timer` hay meter khác để registry thu thập. Trong ứng dụng Spring Boot, các bean triển khai `MeterBinder` thường được auto-configuration gắn vào registry; trong ứng dụng Java độc lập, bạn gọi `bindTo(registry)` một cách tường minh.

Điểm quan trọng là binder, registry và tài nguyên được quan sát có vòng đời khác nhau. Registry quản lý meter và việc xuất số liệu. Binder mô tả cách đăng ký meter. Tài nguyên như queue, executor, connection pool hoặc cache vẫn thuộc quyền sở hữu của thành phần tạo và vận hành tài nguyên đó. Binder chỉ quan sát tài nguyên; nó không nên vô tình tạo, đóng hoặc thay đổi vòng đời của tài nguyên.

## 1. MeterBinder và phương thức bindTo

`MeterBinder` là interface của Micrometer với phương thức chính:

```java
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
```

Khi gọi `bindTo`, binder đăng ký các meter cần thiết vào registry được truyền vào. Binder có thể đăng ký nhiều meter cho một tài nguyên, ví dụ queue depth, số phần tử đã xử lý hoặc thời lượng xử lý.

Ví dụ đơn giản:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterBinder;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueMetricsBinder implements MeterBinder {
    private final AtomicInteger queueDepth;

    public QueueMetricsBinder(AtomicInteger queueDepth) {
        this.queueDepth = queueDepth;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("app.queue.depth", queueDepth, AtomicInteger::get)
                .description("Current number of queued items")
                .register(registry);
    }
}
```

Binder nhận tham chiếu đến trạng thái queue, rồi đăng ký một gauge. Mỗi lần registry thu thập metrics, callback đọc giá trị hiện tại từ `AtomicInteger`. Binder không tự tạo queue và cũng không quyết định lúc enqueue hoặc dequeue.

## 2. Phân biệt trách nhiệm của binder, registry và tài nguyên

Ba đối tượng cần có ranh giới trách nhiệm rõ ràng:

| Đối tượng | Sở hữu hoặc quản lý | Không nên làm |
| --- | --- | --- |
| `MeterBinder` | Quy tắc đăng ký meter và tham chiếu cần thiết để quan sát tài nguyên | Tự ý đóng tài nguyên hoặc đóng registry dùng chung |
| `MeterRegistry` | Danh tính meter, meter đã đăng ký, cấu hình filter và cơ chế xuất dữ liệu | Quản lý nghiệp vụ của queue, executor hoặc connection pool |
| Tài nguyên được quan sát | Trạng thái và vòng đời vận hành của chính nó | Phụ thuộc vào việc scrape metrics để cập nhật trạng thái |

Ví dụ, một connection pool được tạo bởi cấu hình datasource hoặc thư viện pool. Binder có thể đọc số connection đang active, idle và số lần acquire. Khi ứng dụng dừng, thành phần sở hữu datasource đóng pool theo lifecycle của nó. Việc registry scrape metrics không được quyết định khi nào pool đóng.

Tách biệt các trách nhiệm này giúp thay registry hoặc backend mà không phải thay đổi cách tạo tài nguyên; đồng thời giúp tài nguyên hoạt động bình thường ngay cả khi metrics tạm thời không được thu thập.

## 3. Vòng đời của MeterBinder trong Spring Boot

Trong ứng dụng Spring Boot, một class triển khai `MeterBinder` có thể được khai báo thành bean bằng `@Component` hoặc `@Bean`. Auto-configuration của Actuator nhận các binder bean và áp dụng chúng cho registry được quản lý trong application context.

Ví dụ với `@Bean`:

```java
import io.micrometer.core.instrument.MeterBinder;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueMetricsConfiguration {
    @Bean
    AtomicInteger queueDepthState() {
        return new AtomicInteger();
    }

    @Bean
    MeterBinder queueMetricsBinder(AtomicInteger queueDepthState) {
        return new QueueMetricsBinder(queueDepthState);
    }
}
```

Trong ứng dụng thực tế, trạng thái queue thường nằm trong một bean chuyên trách chứ không chỉ là `AtomicInteger` độc lập. Ví dụ trên tập trung vào việc Spring quản lý binder và trạng thái được inject vào binder.

Với Spring Boot, binder bean thường được gắn vào registry do Actuator auto-configure. Nếu tự tạo registry hoặc thay đổi cách cấu hình metrics, hãy xác minh binder có được áp dụng vào registry mong muốn hay không. Không nên đồng thời để auto-configuration bind một binder và tự bind thủ công vào cùng registry nếu không có lý do rõ ràng.

Khi application context dừng, Spring quản lý lifecycle của các bean. Binder không cần tự đóng registry được inject hoặc registry mà framework quản lý.

## 4. Vòng đời trong ứng dụng Java độc lập

Không có Spring, ứng dụng chịu trách nhiệm tạo registry, tạo tài nguyên, tạo binder và gọi `bindTo`:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public class StandaloneMetricsExample {
    public static void main(String[] args) {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicInteger queueDepth = new AtomicInteger(3);
            QueueMetricsBinder binder = new QueueMetricsBinder(queueDepth);

            binder.bindTo(registry);

            System.out.println(
                    registry.get("app.queue.depth").gauge().value());
        }
    }
}
```

Trong ví dụ, `registry` được tạo và đóng trong cùng phạm vi `try-with-resources`. `queueDepth` là trạng thái được quan sát. Binder đăng ký gauge nhưng không đóng queue state hay registry. Với ứng dụng thực tế, tài nguyên và registry thường được giữ trong một đối tượng application hoặc container có lifecycle rõ ràng.

## 5. Binder cần idempotent với cùng registry

Một binder có thể được gọi nhiều lần với cùng một registry, vì vậy việc `bindTo` nên có tính idempotent: gọi lại không làm tăng số meter trùng lặp hoặc tạo ra nhiều meter cùng ý nghĩa ngoài dự kiến.

Trong Micrometer, registry tra cứu meter theo danh tính gồm tên và tập tag. Đăng ký lại cùng tên, cùng tag và cùng loại meter thường trả về meter đã tồn tại. Dù vậy, binder vẫn cần dùng tên/tag ổn định và không tạo tag mới mỗi lần `bindTo` được gọi.

Ví dụ không nên:

```java
@Override
public void bindTo(MeterRegistry registry) {
    String bindingId = java.util.UUID.randomUUID().toString();
    Gauge.builder("app.queue.depth", queueDepth, AtomicInteger::get)
            .tag("binding", bindingId)
            .register(registry);
}
```

Mỗi lần gọi tạo một tag value mới, do đó tạo một meter identity mới. Registry không thể nhận ra đây là cùng một phép đo.

Ví dụ nên dùng:

```java
@Override
public void bindTo(MeterRegistry registry) {
    Gauge.builder("app.queue.depth", queueDepth, AtomicInteger::get)
            .description("Current number of queued items")
            .register(registry);
}
```

Danh tính meter ổn định, vì vậy việc bind lại cùng binder vào cùng registry có thể tái sử dụng meter đã đăng ký.

Không để hai binder độc lập đăng ký cùng tên và tag nhưng trỏ đến hai tài nguyên khác nhau nếu ý nghĩa của chúng cần được theo dõi riêng. Registry có thể dùng lại meter đã có theo danh tính, khiến nguồn được đăng ký đầu tiên tiếp tục được quan sát. Hãy thống nhất chủ sở hữu meter hoặc phân biệt bằng tag có cardinality hữu hạn khi hai tài nguyên thực sự là hai nhóm cần đo riêng.

### 5.1. Không dùng một cờ bound toàn cục

Binder có thể được bind vào nhiều registry khác nhau. Vì vậy, không nên dùng một boolean như `alreadyBound` để bỏ qua mọi lần bind sau lần đầu:

```java
// Không nên: registry thứ hai sẽ không nhận được meter.
private boolean bound;

@Override
public void bindTo(MeterRegistry registry) {
    if (bound) {
        return;
    }
    bound = true;
    // register meters...
}
```

`bound` chỉ ghi nhận binder đã từng được gọi, không cho biết nó đã được bind vào registry nào. Nếu cần lưu trạng thái đăng ký vì một yêu cầu đặc biệt, trạng thái phải gắn với từng registry và có lifecycle phù hợp. Thông thường, cách đơn giản hơn là để mỗi registry quản lý meter của chính nó và giữ `bindTo` ổn định, idempotent.

## 6. Một binder có thể bind vào nhiều registry

Một binder có thể được áp dụng vào nhiều registry, ví dụ một registry phục vụ Prometheus và một registry khác phục vụ hệ thống quan sát thứ hai. Mỗi lần `bindTo(registry)` cần đăng ký meter vào đúng registry được truyền vào.

```java
try (var prometheusLikeRegistry = new SimpleMeterRegistry();
     var testRegistry = new SimpleMeterRegistry()) {
    AtomicInteger queueDepth = new AtomicInteger(4);
    QueueMetricsBinder binder = new QueueMetricsBinder(queueDepth);

    binder.bindTo(prometheusLikeRegistry);
    binder.bindTo(testRegistry);

    double first = prometheusLikeRegistry.get("app.queue.depth")
            .gauge().value();
    double second = testRegistry.get("app.queue.depth")
            .gauge().value();
}
```

Hai registry có các meter instance riêng, nhưng cả hai có thể quan sát cùng một nguồn `queueDepth`. Khi nguồn thay đổi, lần thu thập tiếp theo ở mỗi registry đọc giá trị mới nhất.

Không lưu một `Meter` lấy từ registry đầu tiên rồi cố dùng chính đối tượng meter đó như thể nó thuộc registry thứ hai. Binder nên đăng ký meter mới theo registry nhận được; registry quản lý meter riêng của mình.

Nếu dùng `CompositeMeterRegistry`, hãy chọn một topology binding nhất quán. Có thể bind vào composite để meter được chuyển tiếp đến các registry con theo cấu hình composite. Tránh vừa bind binder vào composite vừa bind riêng vào từng child một cách tùy tiện, vì có thể tạo dữ liệu trùng hoặc gây khó hiểu khi kiểm tra số meter.

## 7. Tài nguyên được quan sát phải sống đủ lâu

Nhiều meter dạng gauge đọc một object được truyền vào builder. Micrometer thường dùng weak reference cho object được quan sát. Nếu không còn tham chiếu mạnh nào giữ object đó, garbage collector có thể thu hồi object và gauge không còn đọc được giá trị mong muốn.

Vì vậy, tài nguyên hoặc trạng thái cần đo phải được giữ bởi chủ sở hữu có lifecycle phù hợp. Binder có thể giữ tham chiếu đến tài nguyên trong field, nhưng điều đó không thay thế việc xác định ai tạo và ai đóng tài nguyên.

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueState {
    private final AtomicInteger depth = new AtomicInteger();

    public int depth() {
        return depth.get();
    }

    public void itemAdded() {
        depth.incrementAndGet();
    }

    public void itemRemoved() {
        depth.decrementAndGet();
    }
}
```

`QueueState` là trạng thái do queue owner cập nhật. Bean queue hoặc binder giữ tham chiếu mạnh đến `QueueState` trong suốt thời gian queue hoạt động. Callback gauge chỉ đọc `depth()`; nó không tự cập nhật trạng thái.

## 8. Khi tài nguyên được thay thế hoặc đóng

Một số tài nguyên có thể được tạo lại trong vòng đời ứng dụng, ví dụ connection pool được refresh, executor được thay thế hoặc client được reconnect. Nếu binder vẫn tham chiếu đến object cũ, gauge có thể tiếp tục đọc trạng thái cũ sau khi tài nguyên mới đã được đưa vào sử dụng.

Trước khi thay tài nguyên, cần quyết định semantics của metric:

- Nếu metric mô tả trạng thái của một logical resource liên tục, có thể dùng một đối tượng trạng thái ổn định làm nguồn gauge và cập nhật snapshot khi resource thay đổi.
- Nếu metric mô tả một resource instance cụ thể, cần xác định identity của instance và thời điểm meter cũ không còn phù hợp.
- Nếu resource bị đóng vĩnh viễn, không để callback tiếp tục gọi API trên object đã đóng hoặc đã giải phóng.

Với resource động, một lớp adapter có thể giữ tham chiếu đến resource hiện tại bằng `AtomicReference` và cung cấp một snapshot nhanh cho gauge. Khi thay resource, owner cập nhật reference; callback chỉ đọc snapshot hiện tại. Cách này tránh callback truy cập một object đã bị đóng, nhưng cần thiết kế trạng thái sau shutdown rõ ràng.

Không nên tạo tag chứa UUID mới mỗi lần reconnect nếu không có nhu cầu phân tích theo từng incarnation; điều đó làm cardinality tăng theo số lần thay tài nguyên. Nếu cần phân biệt incarnation để điều tra, hãy dùng một chiều có giới hạn hoặc log/trace phù hợp.

## 9. Binder chỉ đăng ký meter, không nên tạo hoặc đóng tài nguyên

Một anti-pattern là tạo executor hoặc connection pool ngay trong `bindTo`:

```java
@Override
public void bindTo(MeterRegistry registry) {
    ExecutorService executor = Executors.newFixedThreadPool(8);
    // register gauges for executor...
}
```

Nếu binder được gọi lại cho registry khác, đoạn code có thể tạo thêm executor. Binder cũng không có trách nhiệm rõ ràng để đóng các executor đã tạo. Điều này dẫn đến rò rỉ thread hoặc tài nguyên.

Thay vào đó, tài nguyên nên được tạo bởi bean hoặc factory chuyên trách. Binder nhận tài nguyên đã tồn tại:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterBinder;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.ThreadPoolExecutor;

public final class ExecutorMetricsBinder implements MeterBinder {
    private final ThreadPoolExecutor executor;

    public ExecutorMetricsBinder(ThreadPoolExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("app.executor.active", executor,
                        ThreadPoolExecutor::getActiveCount)
                .description("Number of active executor threads")
                .register(registry);
        Gauge.builder("app.executor.queue.size", executor,
                        pool -> pool.getQueue().size())
                .description("Current number of queued executor tasks")
                .register(registry);
    }
}
```

Ở đây executor được tạo và shutdown bởi owner. Binder chỉ đăng ký hai gauge đọc trạng thái executor. Với queue có kích thước lớn, hãy kiểm tra độ phức tạp và chi phí của `getQueue().size()` trong implementation đang dùng; callback gauge nên đọc nhanh và không duyệt dữ liệu lớn.

## 10. MeterBinder và MeterRegistryCustomizer khác nhau

Hai cơ chế thường được dùng cùng nhau nhưng có mục đích khác nhau:

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| `MeterBinder` | Đăng ký meter cho một thành phần hoặc tài nguyên | JVM, executor, cache, queue, datasource pool |
| `MeterRegistryCustomizer` | Cấu hình registry trước hoặc trong quá trình thiết lập | Common tags, filter, naming hoặc cấu hình chung |

Ví dụ customizer thêm tag chung:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags() {
    return registry -> registry.config().commonTags(
            "application", "order-service",
            "environment", "production");
}
```

Customizer không thay thế binder. Customizer định cấu hình cách registry hoạt động; binder đăng ký các phép đo cụ thể. Không nên dùng customizer để tạo và sở hữu connection pool hoặc executor.

## 11. Kiểm thử lifecycle và binding

`SimpleMeterRegistry` phù hợp để kiểm tra binder mà không cần kết nối backend. Test sau xác minh bind hai lần vào cùng registry không tạo thêm meter và gauge đọc được trạng thái mới:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class QueueMetricsBinderTest {
    @Test
    void repeatedBindingToSameRegistryIsIdempotent() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicInteger queueDepth = new AtomicInteger(2);
            QueueMetricsBinder binder = new QueueMetricsBinder(queueDepth);

            binder.bindTo(registry);
            int meterCountAfterFirstBind = registry.getMeters().size();

            binder.bindTo(registry);

            assertThat(registry.getMeters()).hasSize(meterCountAfterFirstBind);
            assertThat(registry.get("app.queue.depth").gauge().value())
                    .isEqualTo(2.0);

            queueDepth.set(5);
            assertThat(registry.get("app.queue.depth").gauge().value())
                    .isEqualTo(5.0);
        }
    }
}
```

Có thể kiểm tra binding nhiều registry bằng cách tạo hai `SimpleMeterRegistry`, bind cùng binder vào cả hai rồi xác minh mỗi registry có meter tương ứng. Điều này phát hiện lỗi dùng cờ `bound` toàn cục khiến registry thứ hai bị bỏ qua.

Với tài nguyên có lifecycle riêng, integration test nên xác minh:

- Owner tạo tài nguyên trước khi binder đăng ký meter.
- Binder đọc đúng tài nguyên đang hoạt động.
- Khi resource cập nhật trạng thái, gauge phản ánh giá trị mới.
- Khi resource đóng, callback không tiếp tục gọi API không còn hợp lệ.
- Khi application context dừng, owner đóng resource và Spring đóng registry theo lifecycle của bean.

## 12. Những lỗi thường gặp

- **Binder tự tạo resource trong `bindTo`:** mỗi lần bind có thể tạo thêm thread, pool hoặc client.
- **Binder đóng registry:** registry thường được application context hoặc application owner quản lý.
- **Dùng cờ bound toàn cục:** registry thứ hai không được bind.
- **Tạo tag ngẫu nhiên mỗi lần bind:** cùng binder tạo nhiều meter identity và cardinality tăng.
- **Giữ meter của registry này để dùng cho registry khác:** meter thuộc registry đã đăng ký nó.
- **Không giữ nguồn gauge sống:** weak reference có thể khiến gauge mất nguồn dữ liệu.
- **Không xử lý resource replacement:** binder tiếp tục đọc object cũ hoặc object đã đóng.
- **Đăng ký binder tự động rồi bind thủ công thêm lần nữa:** có thể gây đăng ký lặp hoặc khó kiểm soát cấu hình.
- **Dùng `MeterRegistryCustomizer` thay cho binder:** customizer không phải cơ chế mô tả meter cho một resource cụ thể.
- **Đưa phép tính nặng vào callback:** làm chậm scrape và tăng tải phụ lên ứng dụng.

## 13. Checklist thiết kế MeterBinder

- [ ] Binder triển khai `MeterBinder` và đăng ký meter trong `bindTo(registry)`.
- [ ] Tên và tag ổn định để binding lặp lại cùng registry có tính idempotent.
- [ ] Binder có thể bind độc lập vào nhiều registry.
- [ ] Không dùng một cờ `bound` toàn cục để bỏ qua registry tiếp theo.
- [ ] Meter được đăng ký vào đúng registry truyền vào, không tái sử dụng meter từ registry khác.
- [ ] Tài nguyên được tạo và đóng bởi owner có lifecycle rõ ràng.
- [ ] Binder chỉ quan sát, không tự ý tạo hoặc đóng tài nguyên.
- [ ] Đối tượng gauge được giữ sống và callback đọc nhanh, thread-safe.
- [ ] Có kế hoạch khi tài nguyên được thay thế hoặc shutdown.
- [ ] Spring Boot auto-binding hoặc manual binding được chọn rõ ràng, tránh bind trùng.
- [ ] Unit test xác minh idempotency và binding nhiều registry.

`MeterBinder` giúp gom việc đăng ký meter theo từng thành phần, nhưng độ tin cậy của metrics phụ thuộc vào việc quản lý đúng vòng đời của registry và tài nguyên nguồn. Hãy để owner chịu trách nhiệm tạo, cập nhật và đóng tài nguyên; binder đăng ký meter ổn định vào từng registry; callback chỉ đọc trạng thái hiện tại với chi phí thấp. Khi ba vòng đời này được tách bạch, instrumentation dễ kiểm thử và hoạt động ổn định khi ứng dụng mở rộng hoặc thay đổi backend.
