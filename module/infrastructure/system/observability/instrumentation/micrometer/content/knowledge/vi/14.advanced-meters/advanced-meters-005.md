# Giới hạn loại meter có hỗ trợ MeterProvider theo phiên bản

`MeterProvider` trong Micrometer là một tiện ích tạo meter từ một cấu hình chung, sau đó bổ sung tag thay đổi theo từng lần ghi nhận. Thay vì tạo lại một builder mỗi khi cần một tổ hợp tag mới, ứng dụng tạo provider một lần bằng `withRegistry(registry)`, rồi gọi `withTag(...)` hoặc `withTags(...)` để lấy meter tương ứng.

API này không áp dụng cho mọi loại meter. Tài liệu Micrometer liệt kê đúng bốn loại có thể dùng `MeterProvider`: `Counter`, `Timer`, `LongTaskTimer` và `DistributionSummary`. Các builder tương ứng cung cấp `withRegistry(MeterRegistry)`. API được giới thiệu từ Micrometer 1.12.0; ở phiên bản cũ hơn, mã gọi `withRegistry` hoặc kiểu `Meter.MeterProvider` sẽ không biên dịch.

Vì vậy, trước khi áp dụng cần xác định phiên bản `micrometer-core` thực tế mà ứng dụng đang resolve, chọn đúng loại meter và kiểm soát các giá trị tag động. Provider giảm boilerplate và việc tạo builder lặp lại; nó không giới hạn cardinality thay cho ứng dụng.

## 1. MeterProvider giải quyết vấn đề gì?

Một tình huống phổ biến là kết quả của thao tác chỉ được biết khi thao tác kết thúc. Ví dụ, ứng dụng chạy một job và muốn đo thời lượng theo trạng thái `success` hoặc `failure`.

Nếu tạo builder tại mỗi lần hoàn tất:

~~~java
Timer.Sample sample = Timer.start(registry);

Result result = job.execute();

Timer timer = Timer.builder("job.execution")
        .tag("job.name", "nightly")
        .tag("status", result.status())
        .register(registry);

sample.stop(timer);
~~~

Mỗi lần chạy đều tạo một `Timer.Builder` mới. Các thuộc tính cố định như tên, mô tả và `job.name` cũng bị lặp lại ở nhiều vị trí. Với một đường xử lý chạy thường xuyên, đây là boilerplate không cần thiết và tạo thêm đối tượng builder cho garbage collector.

`MeterProvider` cho phép tách cấu hình thành hai phần:

- **Tag cố định:** được khai báo khi tạo builder và provider, ví dụ `job.name=nightly`.
- **Tag động:** chỉ được xác định tại thời điểm cần meter, ví dụ `status=success` hoặc `status=failure`.

Provider giữ mẫu cấu hình chung và dùng các tag truyền vào để đăng ký hoặc lấy lại meter tương ứng.

## 2. Phiên bản bắt đầu hỗ trợ

`Meter.MeterProvider<T>` và phương thức `withRegistry(MeterRegistry)` trên các builder được hỗ trợ có từ Micrometer **1.12.0**.

| Phiên bản Micrometer | Khả năng dùng MeterProvider |
|---|---|
| 1.11.x trở xuống | Không có API MeterProvider/withRegistry được giới thiệu ở 1.12.0 |
| 1.12.0 trở lên | Có API trên các builder được hỗ trợ |
| Các nhánh hiện hành | Vẫn giới hạn ở Counter, Timer, LongTaskTimer và DistributionSummary theo tài liệu Micrometer |

Đây là mốc phiên bản của Micrometer, không phải mốc phiên bản Spring Boot. Spring Boot quản lý phiên bản Micrometer thông qua dependency management/BOM. Một dự án nâng Spring Boot hoặc ghi đè dependency có thể resolve phiên bản `micrometer-core` khác với dự đoán nếu không kiểm tra dependency tree.

Trước khi viết code, hãy xem phiên bản thực tế:

Với Gradle:

~~~shell
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
~~~

Với Maven:

~~~shell
mvn dependency:tree -Dincludes=io.micrometer:micrometer-core
~~~

Nếu kết quả là 1.11.x hoặc cũ hơn, không thể chỉ thêm import để dùng API này. Cần nâng Micrometer lên phiên bản tương thích thông qua BOM hoặc dependency management phù hợp, đồng thời bảo đảm các module Micrometer trong ứng dụng không bị lệch phiên bản.

## 3. Bốn loại meter được hỗ trợ

Theo tài liệu Meter Provider của Micrometer, chỉ bốn loại sau có builder cung cấp `withRegistry`:

| Loại meter | Kiểu provider | Ví dụ tag động |
|---|---|---|
| `Counter` | `MeterProvider<Counter>` | Kết quả sự kiện, nhóm kết quả |
| `Timer` | `MeterProvider<Timer>` | Trạng thái thao tác được biết khi kết thúc |
| `LongTaskTimer` | `MeterProvider<LongTaskTimer>` | Nhóm tác vụ được biết khi bắt đầu |
| `DistributionSummary` | `MeterProvider<DistributionSummary>` | Loại payload hoặc nhóm batch |

Các loại `Gauge`, `FunctionCounter`, `FunctionTimer`, `TimeGauge` và `MultiGauge` không nằm trong danh sách MeterProvider được hỗ trợ. Không nên giả định rằng mọi meter đều có thể gọi `withRegistry` chỉ vì chúng đều được quản lý bởi `MeterRegistry`.

## 4. MeterProvider là kiểu lồng trong Meter

Trong API Micrometer, `MeterProvider` là interface lồng bên trong `Meter`, có kiểu tổng quát:

~~~java
import io.micrometer.core.instrument.Meter.MeterProvider;
~~~

Provider có các cách lấy meter:

- `withTag(String key, String value)`: thêm một tag động.
- `withTags(String... tags)`: thêm nhiều tag theo cặp key/value.
- `withTags(Iterable<? extends Tag> tags)`: thêm một tập Tag.

Ví dụ:

~~~java
Counter counter = counterProvider.withTag("outcome", "success");

Timer timer = timerProvider.withTags(
        "status", "success",
        "region", "ap-southeast"
);
~~~

Các tag cố định khai báo trên builder được giữ lại; các tag truyền qua provider được thêm vào khi tạo meter. Giá trị trả về là meter cụ thể, vì vậy có thể gọi `increment()`, `record()` hoặc `start()` tùy loại.

## 5. Dùng MeterProvider với Counter

Counter phù hợp với sự kiện có giá trị tích lũy. Nếu trạng thái sự kiện chỉ được biết sau khi xử lý, provider có thể tạo meter theo một tag kết quả đã được giới hạn.

~~~java
final class JobMetrics {
    private final MeterProvider<Counter> executions;

    JobMetrics(MeterRegistry registry) {
        this.executions = Counter.builder("job.executions")
                .description("Number of completed job executions")
                .tag("job.name", "nightly-import")
                .withRegistry(registry);
    }

    void recordCompletion(String outcome) {
        executions.withTag("outcome", outcome).increment();
    }
}
~~~

Ở đây `job.name` là tag cố định. `outcome` là tag động vì kết quả chỉ có sau khi job hoàn tất. Mỗi lần ghi nhận, provider trả về Counter theo tổ hợp tag tương ứng.

Tập giá trị của `outcome` cần được chuẩn hóa, ví dụ chỉ gồm `success`, `failure` và `cancelled`. Không truyền exception message hoặc request ID vào tag.

## 6. Dùng MeterProvider với Timer

Timer thường cần tag kết quả được xác định ở cuối thao tác. `Timer.Sample` cho phép bắt đầu đo trước, sau đó chọn Timer cụ thể khi dừng sample.

~~~java
final class JobMetrics {
    private final MeterProvider<Timer> executionTimer;
    private final MeterRegistry registry;

    JobMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.executionTimer = Timer.builder("job.execution")
                .description("Job execution duration")
                .tag("job.name", "nightly-import")
                .withRegistry(registry);
    }

    void execute(Runnable operation) {
        Timer.Sample sample = Timer.start(registry);
        String status = "success";

        try {
            operation.run();
        } catch (RuntimeException | Error error) {
            status = "failure";
            throw error;
        } finally {
            sample.stop(executionTimer.withTag("status", status));
        }
    }
}
~~~

Sample bắt đầu trước khi chạy công việc. Trong `finally`, provider trả về Timer có tag `status` phù hợp và sample ghi thời lượng vào Timer đó. Nhờ vậy cả thành công và thất bại đều được đo, còn tag kết quả được quyết định ở thời điểm kết thúc.

Không đưa loại exception hoặc nội dung lỗi tùy ý vào tag `status`. Nếu cần phân loại lỗi, hãy ánh xạ về một danh mục nhỏ, ổn định như `timeout`, `validation`, `dependency` hoặc `unknown`.

## 7. Dùng MeterProvider với LongTaskTimer

LongTaskTimer theo dõi thời lượng của các tác vụ còn đang chạy. Tag động thường được biết trước lúc bắt đầu, ví dụ loại đồng bộ hoặc nhóm tác vụ.

~~~java
final class RefreshMetrics {
    private final MeterProvider<LongTaskTimer> activeRefreshes;

    RefreshMetrics(MeterRegistry registry) {
        this.activeRefreshes = LongTaskTimer.builder("data.refresh.active")
                .description("Active data refresh tasks")
                .withRegistry(registry);
    }

    void refresh(String source, Runnable operation) {
        LongTaskTimer timer = activeRefreshes.withTag("source", source);
        LongTaskTimer.Sample sample = timer.start();
        try {
            operation.run();
        } finally {
            sample.stop();
        }
    }
}
~~~

Provider tạo hoặc lấy LongTaskTimer theo tag `source`. Sample được dừng trong `finally` để tác vụ thất bại cũng không bị báo cáo active vô thời hạn.

Giá trị `source` phải đến từ tập đã kiểm soát, ví dụ `inventory`, `pricing` hoặc `catalog`. Nếu mỗi lần chạy truyền một UUID hoặc batch ID riêng, số meter sẽ tăng theo số lần chạy và tạo cardinality không giới hạn.

## 8. Dùng MeterProvider với DistributionSummary

DistributionSummary ghi nhận phân phối của một đại lượng số không phải thời gian, ví dụ kích thước payload hoặc số bản ghi trong batch.

~~~java
final class PayloadMetrics {
    private final MeterProvider<DistributionSummary> payloadSizes;

    PayloadMetrics(MeterRegistry registry) {
        this.payloadSizes = DistributionSummary.builder("request.payload.size")
                .description("Request payload size")
                .baseUnit("bytes")
                .withRegistry(registry);
    }

    void record(String payloadType, int bytes) {
        payloadSizes.withTag("type", payloadType).record(bytes);
    }
}
~~~

Tên, mô tả và đơn vị được định nghĩa một lần. Tag `type` phân loại payload tại thời điểm ghi. Hãy dùng danh mục hữu hạn như `json`, `xml` hoặc `binary`, không dùng tên file hoặc URL đầy đủ.

## 9. Vì sao Gauge không có trong danh sách?

Gauge quan sát trạng thái hiện tại của một đối tượng hoặc hàm đọc. Cách sử dụng thông thường là đăng ký Gauge với một object sống đủ lâu rồi cập nhật trạng thái của chính object đó.

~~~java
final class QueueMetrics {
    private final AtomicInteger depth = new AtomicInteger();

    QueueMetrics(MeterRegistry registry) {
        Gauge.builder("jobs.queue.depth", depth, AtomicInteger::get)
                .description("Current queue depth")
                .register(registry);
    }

    void enqueued() {
        depth.incrementAndGet();
    }

    void dequeued() {
        depth.updateAndGet(value -> Math.max(0, value - 1));
    }
}
~~~

Gauge không cần tạo lại theo từng tag kết quả sau mỗi lần thao tác hoàn tất. Nếu cần một Gauge cho từng nhóm queue, hãy đăng ký mỗi nhóm có kiểm soát một lần với tag ổn định và giữ object trạng thái tương ứng. Không dùng `MeterProvider<Gauge>` vì builder Gauge không cung cấp API `withRegistry` như bốn loại được liệt kê.

## 10. Các meter khác không nằm trong danh sách

Các loại sau không được tài liệu Meter Provider liệt kê là có hỗ trợ:

| Loại meter | Cách đăng ký thông thường |
|---|---|
| `Gauge` | `Gauge.builder(...).register(registry)` với object trạng thái sống lâu |
| `FunctionCounter` | `FunctionCounter.builder(...).register(registry)` quan sát nguồn dữ liệu tích lũy |
| `FunctionTimer` | `FunctionTimer.builder(...).register(registry)` quan sát count và total time từ nguồn dữ liệu |
| `TimeGauge` | `TimeGauge.builder(...).register(registry)` với hàm đọc và TimeUnit |
| `MultiGauge` | Tạo MultiGauge và gọi `register(rows, ...)` để cập nhật các hàng theo mô hình của nó |

Nếu cần tag thay đổi cho một trong các loại này, hãy thiết kế vòng đời đăng ký rõ ràng. Ví dụ, có thể đăng ký Gauge riêng cho từng nhóm đã biết trước, hoặc xây dựng một component quản lý các meter theo danh mục hữu hạn. Tránh tạo meter mới với tag không giới hạn.

Không nên tự tạo một interface `MeterProvider` khác rồi gán tên giống API Micrometer để làm cho các loại meter không hỗ trợ trông như có cùng contract. Nếu dự án cần abstraction chung, hãy đặt tên riêng và định nghĩa rõ vòng đời, caching, tag và giới hạn cardinality.

## 11. Phiên bản cũ hơn 1.12.0: dùng cách nào?

Khi dự án chưa thể nâng Micrometer lên 1.12.0, có thể tiếp tục dùng builder và đăng ký meter khi biết đủ tag:

~~~java
Timer.Sample sample = Timer.start(registry);

Result result = job.execute();

Timer timer = Timer.builder("job.execution")
        .tag("job.name", "nightly-import")
        .tag("status", result.status())
        .register(registry);

sample.stop(timer);
~~~

Đây là cách hoạt động trước MeterProvider. Nó vẫn hợp lệ, nhưng mỗi lần đi qua đường code tạo một builder mới. Nếu dùng một số meter đơn giản, registry cũng có các phương thức tiện ích như `registry.counter(name, tags...)` hoặc `registry.timer(name, tags...)`; hãy chọn API phù hợp với nhu cầu metadata và cấu hình distribution.

Nếu dynamic tag được biết sau khi thao tác hoàn tất, `Timer.Sample` đặc biệt hữu ích vì Timer đích chỉ cần được chọn ở lúc gọi `stop(timer)`. Không cần MeterProvider để dùng pattern này.

## 12. MeterProvider không thay thế kiểm soát cardinality

Provider làm cho việc tạo meter theo tag gọn hơn, nhưng mỗi tổ hợp tag khác nhau vẫn có thể tạo một meter ID khác trong registry. Nếu tag động có hàng triệu giá trị, registry và backend vẫn phải quản lý hàng triệu chuỗi thời gian.

Ví dụ an toàn hơn:

~~~java
provider.withTag("status", "success");
provider.withTag("status", "failure");
~~~

Ví dụ có nguy cơ cardinality cao:

~~~java
provider.withTag("request.id", requestId);
provider.withTag("customer.id", customerId);
~~~

Không dùng request ID, user ID, customer ID, order ID, timestamp, URL động hoặc nội dung exception làm tag metrics. Đưa định danh cần điều tra vào log hoặc trace theo chính sách dữ liệu của ứng dụng.

Hãy dự tính số tổ hợp tag trước khi triển khai. Nếu có 3 trạng thái, 4 nguồn và 2 chế độ, số meter tối đa cho tên đó có thể là 24 tổ hợp. Khi thêm một tag chứa giá trị không giới hạn, số tổ hợp không còn dự đoán được.

## 13. Kiểm thử MeterProvider

SimpleMeterRegistry đủ để kiểm tra provider trả về meter theo tag và các lần ghi nhận được tổng hợp đúng:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

MeterProvider<Counter> provider = Counter.builder("job.executions")
        .tag("job.name", "nightly")
        .withRegistry(registry);

provider.withTag("status", "success").increment(2.0);
provider.withTag("status", "failure").increment();

assertThat(registry.get("job.executions")
        .tag("job.name", "nightly")
        .tag("status", "success")
        .counter()
        .count()).isEqualTo(2.0);

assertThat(registry.get("job.executions")
        .tag("job.name", "nightly")
        .tag("status", "failure")
        .counter()
        .count()).isEqualTo(1.0);
~~~

Nên kiểm tra thêm:

1. Provider giữ lại các tag cố định đã cấu hình trong builder.
2. Tag động tạo đúng meter cho từng giá trị hợp lệ.
3. Gọi lại cùng tổ hợp tag lấy lại meter hiện có và ghi tiếp vào cùng chuỗi thời gian.
4. Không có tag ID động lọt vào registry.
5. Mỗi loại meter được dùng đúng API và đúng ngữ nghĩa.
6. Code biên dịch với phiên bản Micrometer được khai báo trong BOM của ứng dụng.

Nếu cần xác minh exporter, hãy kiểm thử thêm registry cụ thể. Unit test với SimpleMeterRegistry chỉ xác minh lớp Micrometer; nó không chứng minh tên hoặc định dạng backend xuất ra.

## 14. Các lỗi thường gặp

**Cho rằng mọi Meter đều hỗ trợ MeterProvider.** Chỉ Counter, Timer, LongTaskTimer và DistributionSummary có hỗ trợ theo tài liệu. Gauge và các loại khác cần cách đăng ký riêng.

**Dùng API với Micrometer trước 1.12.0.** `MeterProvider` và `withRegistry` chưa có ở các phiên bản cũ. Kiểm tra dependency thực tế thay vì chỉ nhìn phiên bản Spring Boot khai báo.

**Nhầm MeterProvider với MeterRegistry.** Registry quản lý meter; MeterProvider là template để lấy meter cùng loại với các tag bổ sung.

**Tạo provider cho mỗi request.** Việc đó làm mất lợi ích tái sử dụng cấu hình. Khởi tạo provider một lần trong component và dùng lại.

**Đưa tag cố định vào mỗi lần gọi.** Khai báo tag không thay đổi trên builder; chỉ truyền phần tag động qua `withTag` hoặc `withTags`.

**Dùng tag động không kiểm soát.** Provider vẫn đăng ký meter theo từng tổ hợp tag. Hãy giới hạn tập giá trị.

**Cho rằng provider lưu kết quả nghiệp vụ.** Provider chỉ tạo hoặc lấy lại meter; nó không thay thế kho dữ liệu bền vững và không lưu trạng thái nghiệp vụ.

**Dùng MeterProvider để thay thế Gauge.** Gauge cần quan sát trạng thái hiện tại của object sống lâu. Hãy đăng ký một lần và cập nhật object đó.

## 15. Checklist chọn API

Trước khi dùng MeterProvider, hãy kiểm tra:

- [ ] Phiên bản Micrometer thực tế từ 1.12.0 trở lên.
- [ ] Loại meter là Counter, Timer, LongTaskTimer hoặc DistributionSummary.
- [ ] Builder của loại meter có phương thức `withRegistry(MeterRegistry)`.
- [ ] Tag cố định được khai báo một lần trên builder.
- [ ] Tag động chỉ gồm các giá trị có tập hữu hạn và đã chuẩn hóa.
- [ ] Provider được tạo một lần và tái sử dụng.
- [ ] Đã cân nhắc Timer.Sample nếu tag kết quả chỉ có sau khi thao tác hoàn tất.
- [ ] Với Gauge hoặc loại không hỗ trợ, đã dùng API đăng ký riêng phù hợp.
- [ ] Unit test xác minh meter theo từng tổ hợp tag.
- [ ] Build kiểm tra tương thích với phiên bản Micrometer thực tế.

## 16. Kết luận

`MeterProvider` là tiện ích cho các meter cần giữ một cấu hình chung và bổ sung tag động. Trong Micrometer, API này có từ 1.12.0 và chỉ hỗ trợ bốn loại: Counter, Timer, LongTaskTimer và DistributionSummary. Mỗi builder tương ứng cung cấp `withRegistry(registry)`; provider trả về meter qua `withTag` hoặc `withTags`.

Với Gauge, FunctionCounter, FunctionTimer, TimeGauge và MultiGauge, hãy dùng cách đăng ký riêng của từng loại. Trước khi áp dụng cần kiểm tra phiên bản `micrometer-core` được resolve, giữ provider ở vòng đời component và giới hạn tập tag động. Làm đúng các điểm này giúp giảm builder lặp lại, giữ cấu hình nhất quán và tránh tạo cardinality không kiểm soát.

## Tài liệu tham khảo

- [Micrometer – Meter Provider](https://docs.micrometer.io/micrometer/reference/concepts/meter-provider.html)
- [Micrometer 1.12.13 – Meter Provider](https://docs.micrometer.io/micrometer/reference/1.12/concepts/meter-provider.html)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
