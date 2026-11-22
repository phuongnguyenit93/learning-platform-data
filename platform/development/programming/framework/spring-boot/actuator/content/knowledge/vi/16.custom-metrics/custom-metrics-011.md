# Kiểm soát đăng ký meter trong vòng lặp và giải phóng meter không còn cần thiết

## 1. Hai câu hỏi phải tách riêng

Một dịch vụ xử lý hàng nghìn tác vụ mỗi phút. Mỗi lần xử lý, nó cần tăng số tác vụ thành công hoặc thất bại. Đồng thời, một số nhóm xử lý có thể được tạo và dừng trong lúc ứng dụng chạy.

Trong tình huống này, có hai vấn đề khác nhau:

1. **Đăng ký và ghi nhận:** có cần tìm hoặc tạo phép đo ở mỗi vòng lặp không?
2. **Vòng đời:** khi một nguồn đo thực sự không còn tồn tại, ai gỡ phép đo tương ứng?

Trong Micrometer, một `Meter` là đối tượng phép đo như Counter, Gauge hoặc Timer. `MeterRegistry` quản lý các phép đo đã đăng ký; mã nghiệp vụ dùng những đối tượng đó để ghi nhận hoặc để đọc trạng thái.

Một thiết kế tốt thường giữ số loại phép đo ổn định trong khi số sự kiện có thể tăng rất lớn. Việc xử lý thêm một triệu tác vụ không nên tự động tạo thêm một triệu định danh phép đo.

Bài này dùng hai tình huống: bộ Counter có tập kết quả hữu hạn để ghi nhận trong vòng lặp, và một Gauge có thành phần quản lý vòng đời rõ ràng khi nguồn đo được thay thế.

## 2. Đăng ký lặp cùng định danh không đồng nghĩa tạo meter mới

Một định danh phép đo được phân biệt chủ yếu bằng **tên và tập tag**. Các thiết lập chung hoặc MeterFilter có thể biến đổi tên/tag trước khi registry dùng định danh đó.

Trong registry mới, không có filter đặc biệt, đoạn minh họa sau dùng lại một Counter:

```java
Counter first = registry.counter(
        "demo.loop.events", "outcome", "success");

for (int i = 0; i < 1_000; i++) {
    registry.counter("demo.loop.events", "outcome", "success")
            .increment();
}

Counter again = registry.counter(
        "demo.loop.events", "outcome", "success");
```

Cùng tên và tag, cùng loại Counter, không có thao tác gỡ xen giữa: `first` và `again` trỏ đến cùng Counter. Sau vòng lặp này, Counter có giá trị `1000.0` trong `SimpleMeterRegistry`.

Vì vậy, nhận định “đặt register trong vòng lặp thì mỗi vòng luôn tạo một meter mới” là sai. Tuy nhiên, mỗi lần gọi vẫn đi qua mã xây dựng/tìm phép đo; nếu tạo builder, chuỗi và tag ở từng sự kiện thì còn có chi phí cấp phát, chuẩn hóa và tra cứu.

Khi tập định danh đã biết trước, nên đăng ký một lần rồi giữ tham chiếu để ghi nhận. Không cần đặt lời gọi tìm kiếm registry vào đường xử lý thường xuyên. Mức cải thiện hiệu năng cụ thể phải được đo trong ứng dụng, không suy ra một tỷ lệ cố định.

[Mã MeterRegistry của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java) cho thấy registry tìm phép đo đã có trước khi tạo phép đo mới.

### Những thứ đăng ký lại không giải quyết được

- Truyền một đối tượng nguồn mới vào Gauge cùng tên/tag không có nghĩa Gauge cũ chuyển sang nguồn mới.
- Đổi mô tả ở lần đăng ký sau không nên được dùng như cơ chế cập nhật cấu hình của phép đo đã tồn tại.
- Đăng ký một loại khác, chẳng hạn Gauge vào cùng tên/tag của một Counter đã có, có thể gây lỗi xung đột loại; loại phép đo không phải một cách tạo thêm định danh độc lập cho cùng tên/tag.
- Đổi tag sau mỗi sự kiện làm thay đổi bài toán: registry có thể phải quản lý nhiều phép đo khác nhau.

Các đoạn ngắn trong bài giả định đã có biến `registry` và import phù hợp. Chương trình chạy đầy đủ nằm ở mục 7.

## 3. Tag thay đổi trong vòng lặp mới là nguồn tăng định danh

Ví dụ cần tránh trong mã phục vụ thực tế:

```java
for (String requestId : requestIds) {
    registry.counter("demo.request.events", "request.id", requestId)
            .increment();
}
```

Nếu mỗi request có một ID mới, mỗi ID tạo ra một tổ hợp tên/tag mới. Dùng request ID trong tên phép đo, chẳng hạn ghép vào `demo.request.events.<id>`, cũng tạo vấn đề tương tự.

**Cardinality** trong ngữ cảnh này là số tổ hợp nhãn tạo ra những chuỗi số liệu phân biệt. Một khóa nhãn có rất nhiều giá trị có thể làm tăng bộ nhớ trong ứng dụng, chi phí xuất số liệu và dữ liệu lưu ở hệ thống giám sát.

Giả sử một phép đo có ba nhãn với số giá trị cho phép lần lượt là 2, 3 và 4. Nếu mọi tổ hợp đều xuất hiện, có thể có `2 × 3 × 4 = 24` định danh cho tên đó. Con số không chỉ phụ thuộc riêng từng nhãn.

Số meter trong registry cũng không luôn bằng số chuỗi số liệu bên ngoài. Một Timer có thể xuất nhiều thống kê, và cấu hình histogram có thể tạo thêm nhiều chuỗi cho mỗi tổ hợp tag.

| Nhu cầu | Cách biểu đạt hợp lý |
| --- | --- |
| Đếm tác vụ theo kết quả | Tag có tập giá trị hữu hạn như `success`, `failure` |
| So sánh nhóm xử lý được cấu hình sẵn | Tag tên nhóm thuộc danh sách được kiểm soát |
| Tìm một request cụ thể | Log hoặc trace có định danh tương ứng |
| Theo dõi URL | Dùng mẫu route hoặc nhóm giá trị có giới hạn, theo ý nghĩa cần quan sát |
| Theo dõi từng đối tượng tạm thời | Cân nhắc phép đo tổng hợp trên một nguồn ổn định |

Không giải quyết vấn đề bằng cách chuyển tất cả request ID vào một `ConcurrentHashMap<String, Counter>`. Map an toàn đồng thời vẫn có thể tăng không giới hạn.

Ngay cả một cache có giới hạn cũng chưa đủ: đẩy Counter ra khỏi cache của ứng dụng không tự gỡ Counter khỏi registry. Ngược lại, gỡ khỏi registry mà cache còn giữ đối tượng cũ có thể khiến mã tiếp tục ghi vào một phép đo không còn được đăng ký.

Xem thêm [quy ước tên và giá trị tag của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

## 4. Tách đăng ký khỏi vòng lặp ghi nhận

Nếu chỉ có hai kết quả xử lý, có thể khởi tạo đủ hai Counter và chọn theo enum. Tập định danh được quyết định bởi hợp đồng nghiệp vụ, thay vì bởi chuỗi đầu vào bất kỳ.

Tệp `src/example/lifecycle/OutcomeCounters.java`:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public final class OutcomeCounters {

    public enum Outcome {
        SUCCESS, FAILURE
    }

    private final Map<Outcome, Counter> counters =
            new EnumMap<>(Outcome.class);

    public OutcomeCounters(MeterRegistry registry) {
        Objects.requireNonNull(registry, "registry");

        for (Outcome outcome : Outcome.values()) {
            Counter counter = Counter.builder("demo.jobs.processed")
                    .tag("outcome", outcome.name().toLowerCase(Locale.ROOT))
                    .description("Số tác vụ đã hoàn tất theo kết quả")
                    .register(registry);
            this.counters.put(outcome, counter);
        }
    }

    public void record(Outcome outcome) {
        this.counters.get(Objects.requireNonNull(outcome, "outcome"))
                .increment();
    }

    public double count(Outcome outcome) {
        return this.counters.get(Objects.requireNonNull(outcome, "outcome"))
                .count();
    }
}
```

Vòng lặp trong constructor chạy trên hai hằng enum. Đây là **vòng lặp đăng ký có giới hạn và có chủ đích**, hoàn toàn khác vòng lặp tạo meter cho từng request ID.

Trong đường xử lý tác vụ, gọi `record` để tăng Counter đã có. Map chỉ được điền khi khởi tạo và không bị sửa về sau. Khi dùng đồng thời, thành phần này cần được công bố an toàn cho các luồng, chẳng hạn qua bean Spring; không biến map thành nơi thêm nhãn động sau khởi tạo.

Counter được giữ sống cùng thành phần thống kê và không bị gỡ sau mỗi tác vụ. Gỡ rồi tạo lại Counter liên tục có thể làm mất phần số liệu chưa kịp xuất và tạo các lần bắt đầu lại của bộ đếm. Đặc điểm Counter và cách sử dụng cho số sự kiện được trình bày trong [tài liệu Counter của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

Nếu cần đo thời gian của chính các sự kiện ấy bằng Timer, nhớ rằng Timer đã có số lần ghi nhận; chỉ thêm Counter riêng khi nó trả lời một câu hỏi khác có ý nghĩa.

## 5. Gỡ meter là thay đổi vòng đời, không phải xóa một biến Java

Cách gỡ một phép đo đã đăng ký:

```java
registry.remove(meter);
```

Nên lưu đối tượng được trả về khi đăng ký để dùng đúng định danh đã chịu tác động của cấu hình registry. Tự ghép một `Meter.Id` mới có thể bỏ qua tag chung hoặc biến đổi từ filter.

Cần phân biệt ba nơi giữ trạng thái:

```text
Ứng dụng
    -> map, trường, listener hoặc callback giữ đối tượng phép đo

MeterRegistry
    -> mục đăng ký và các quan hệ phép đo

Hệ thống giám sát bên ngoài
    -> các mẫu số liệu đã nhận và dữ liệu lịch sử
```

Gỡ ở một nơi không tự động xóa ở mọi nơi.

### 5.1. Đối tượng cũ có thể vẫn được ứng dụng sử dụng

Trong `SimpleMeterRegistry`, sau khi Counter đã bị gỡ, một biến Java còn giữ Counter đó vẫn có thể gọi `increment()`. Nó không vì thế tự đăng ký lại.

Nếu đăng ký lại cùng tên/tag, Counter mới bắt đầu với trạng thái riêng. Ghi vào Counter cũ không có nghĩa đang cập nhật Counter mới. Chương trình ở mục 7 chứng minh điều này.

Vì thế, khi gỡ phép đo, cần đồng thời dừng những đường ghi nhận cũ và bỏ tham chiếu trong các cấu trúc thuộc quyền quản lý của thành phần. Không chỉ nhìn thấy `find(...)` trả null rồi kết luận mọi đường sử dụng đã được dọn.

### 5.2. Gỡ meter không buộc GC thu hồi nguồn

Với Gauge, nguồn đo có thể còn được một bean, map hoặc callback giữ mạnh. Gỡ Gauge không buộc nguồn lập tức biến mất. Chiều ngược lại cũng cần lưu ý: nguồn Gauge bị GC thu hồi không chứng minh mục đăng ký đã được dọn đúng vòng đời.

Không dùng `System.gc()` như thủ tục giải phóng meter hoặc làm điều kiện kiểm thử bắt buộc. Việc quản lý đăng ký và việc thu hồi bộ nhớ là hai cơ chế khác nhau.

### 5.3. Dữ liệu đã xuất có vòng đời riêng

Gọi `remove` không gửi một lệnh xóa toàn bộ lịch sử tới hệ thống giám sát. Mẫu đã lưu, cách đánh dấu chuỗi không còn cập nhật và thời hạn giữ dữ liệu phụ thuộc hệ thống bên ngoài.

Gỡ phép đo quá sớm còn có thể khiến một sự kiện ngắn hạn không bao giờ được hệ thống lấy mẫu nhìn thấy. Không hứa rằng thao tác gỡ sẽ xuất thêm “mẫu cuối cùng”.

Vì vậy, tạo hàng loạt tag tùy ý rồi gỡ ngay sau từng request vẫn là thiết kế cần sửa, kể cả khi số meter đang tồn tại đồng thời có vẻ thấp.

## 6. Một thành phần quản lý Gauge có thể đóng đúng một lần

Giả sử ứng dụng có một nhóm xử lý ảnh tên `image`. Ta cần một Gauge thể hiện số công việc đang hoạt động. Thành phần quản lý nhóm cập nhật trạng thái và đóng phần metrics khi nhóm hết vòng đời.

Ví dụ dưới đây chỉ quản lý **phép đo**. Nó không tự dừng executor hay chờ tác vụ nghiệp vụ. Trước khi đóng, thành phần điều phối phải bảo đảm không còn luồng cần cập nhật phép đo.

**Hợp đồng sử dụng:** tại một thời điểm, chỉ một thành phần quản lý định danh `demo.pool.active{pool=image}` trong một registry. Phiên bản mới chỉ được tạo sau khi phiên bản cũ đã đóng xong; không có thành phần khác tự gỡ/đăng ký lại cùng định danh bên ngoài quy trình này.

Tệp `src/example/lifecycle/PoolActiveGauge.java`:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolActiveGauge implements AutoCloseable {

    private final MeterRegistry registry;
    private final AtomicInteger active = new AtomicInteger();
    private final Gauge gauge;
    private boolean closed;

    public PoolActiveGauge(MeterRegistry registry, String poolName) {
        this.registry = Objects.requireNonNull(registry, "registry");

        String name = Objects.requireNonNull(poolName, "poolName").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("poolName must not be blank");
        }

        this.gauge = Gauge.builder(
                        "demo.pool.active", this.active, AtomicInteger::get)
                .tag("pool", name)
                .description("Số công việc đang hoạt động trong nhóm xử lý")
                .register(this.registry);
    }

    public synchronized void setActive(int value) {
        if (this.closed) {
            throw new IllegalStateException("metrics already closed");
        }
        if (value < 0) {
            throw new IllegalArgumentException("active must not be negative");
        }
        this.active.set(value);
    }

    @Override
    public synchronized void close() {
        if (this.closed) {
            return;
        }
        this.closed = true;
        this.registry.remove(this.gauge);
    }
}
```

Trường `active` giữ nguồn đo. Giá trị này phải được thành phần nghiệp vụ cập nhật đúng với đại lượng đã mô tả; Gauge không tự suy ra số công việc từ một executor chưa được cung cấp cho nó.

`synchronized` phối hợp `setActive` và `close`: sau khi đã đóng, các lần cập nhật qua thành phần này bị từ chối. `AtomicInteger` cung cấp cách đọc giá trị an toàn cho hàm Gauge, vốn không dùng khóa của thành phần quản lý.

`close()` có tính **idempotent** trong phạm vi đối tượng: gọi thêm lần nữa không thực hiện một lần gỡ mới. Không đặt giá trị về 0 rồi đăng ký lại để mô phỏng đóng.

### Vì sao gọi close lặp có thể nguy hiểm nếu không kiểm soát?

Trong Micrometer 1.13.0, `remove(Meter)` chuyển sang gỡ theo ID của meter. Nó không phải một phép so sánh rồi gỡ chỉ khi cùng đúng đối tượng Java.

Nếu phiên bản cũ đã bị gỡ, phiên bản mới dùng lại cùng ID, rồi một callback dọn dẹp cũ chạy muộn và tiếp tục gọi `remove`, nó có thể gỡ phép đo mới.

Cờ `closed` trong ví dụ ngăn lần đóng thứ hai của chính đối tượng cũ làm việc đó. Tuy nhiên, cờ này không điều phối được hai đối tượng quản lý độc lập; hợp đồng một nơi quản lý định danh vẫn phải được giữ.

Khi có nhiều luồng tạo/hủy nhóm xử lý, cần một bộ quản lý vòng đời phối hợp các thao tác theo từng khóa. Một lần kiểm tra `find` thấy trống rồi gọi `register` không tự tạo thành thao tác nguyên tử để bảo đảm quyền quản lý.

## 7. Chương trình hoàn chỉnh kiểm chứng các tình huống

Tệp `src/example/lifecycle/MeterLifecycleDemo.java`, sử dụng hai lớp ở mục 4 và 6:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.ArrayList;
import java.util.List;

public final class MeterLifecycleDemo {

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            OutcomeCounters counters = new OutcomeCounters(registry);

            for (int i = 0; i < 6; i++) {
                OutcomeCounters.Outcome outcome = i % 3 == 0
                        ? OutcomeCounters.Outcome.FAILURE
                        : OutcomeCounters.Outcome.SUCCESS;
                counters.record(outcome);
            }

            System.out.println("outcome.meters="
                    + meterCount(registry, "demo.jobs.processed"));
            System.out.println("success="
                    + counters.count(OutcomeCounters.Outcome.SUCCESS));
            System.out.println("failure="
                    + counters.count(OutcomeCounters.Outcome.FAILURE));

            // Chỉ tạo ba ID để minh họa một cách đăng ký cần tránh.
            List<Meter> requestMeters = new ArrayList<>();
            for (int i = 1; i <= 3; i++) {
                Counter counter = registry.counter(
                        "demo.request.events", "request.id", "req-" + i);
                counter.increment();
                requestMeters.add(counter);
            }

            System.out.println("request-id.meters="
                    + meterCount(registry, "demo.request.events"));

            // Thí nghiệm chạy tuần tự: không còn luồng ghi vào các meter này.
            for (Meter meter : requestMeters) {
                registry.remove(meter);
            }
            requestMeters.clear();

            System.out.println("request-id.meters-after-cleanup="
                    + meterCount(registry, "demo.request.events"));

            Counter oldCounter = registry.counter("demo.reused.events");
            oldCounter.increment(5);
            registry.remove(oldCounter);

            System.out.println("removed-counter-registered="
                    + (registry.find("demo.reused.events").counter() != null));

            oldCounter.increment();
            Counter newCounter = registry.counter("demo.reused.events");
            System.out.println("old-counter=" + oldCounter.count());
            System.out.println("new-counter=" + newCounter.count());

            PoolActiveGauge oldPool = new PoolActiveGauge(registry, "image");
            try {
                oldPool.setActive(2);
                System.out.println("active=" + poolValue(registry));
            } finally {
                oldPool.close();
            }

            System.out.println("pool-gauge-after-close="
                    + (registry.find("demo.pool.active")
                            .tag("pool", "image").gauge() != null));

            try (PoolActiveGauge replacement =
                         new PoolActiveGauge(registry, "image")) {
                replacement.setActive(1);
                System.out.println("replacement-active=" + poolValue(registry));

                oldPool.close();
                System.out.println("replacement-after-old-close="
                        + poolValue(registry));
            }
        } finally {
            registry.close();
        }
    }

    private static long meterCount(MeterRegistry registry, String name) {
        return registry.getMeters().stream()
                .filter(meter -> meter.getId().getName().equals(name))
                .count();
    }

    private static double poolValue(MeterRegistry registry) {
        return registry.get("demo.pool.active")
                .tag("pool", "image")
                .gauge()
                .value();
    }
}
```

Chương trình cố ý tạo ba Counter gắn request ID để thấy số mục tăng, rồi dọn chúng trong một thí nghiệm có giới hạn. Phần này không phải mẫu nên đưa vào đường xử lý request thực tế.

Các lời gọi `getMeters` và tìm kiếm trong ví dụ phục vụ kiểm chứng. Không đưa việc quét toàn registry vào mỗi vòng xử lý tác vụ.

### Dependency và lệnh biên dịch

Tạo `pom.xml` ở thư mục gốc của thí nghiệm:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Cần JDK 17+ và Maven. Lần đầu tải dependency cần kết nối Maven Central. Tại thư mục chứa `pom.xml`, chạy trong PowerShell:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/lifecycle/OutcomeCounters.java src/example/lifecycle/PoolActiveGauge.java src/example/lifecycle/MeterLifecycleDemo.java
java -cp "out;lib/*" example.lifecycle.MeterLifecycleDemo
```

Trên Linux/macOS, dùng dấu `:` trong classpath của lệnh chạy:

```bash
java -cp "out:lib/*" example.lifecycle.MeterLifecycleDemo
```

Stdout của chương trình chạy tuần tự:

```text
outcome.meters=2
success=4.0
failure=2.0
request-id.meters=3
request-id.meters-after-cleanup=0
removed-counter-registered=false
old-counter=6.0
new-counter=0.0
active=2.0
pool-gauge-after-close=false
replacement-active=1.0
replacement-after-old-close=1.0
```

Các kết quả chứng minh:

- Sáu sự kiện chỉ dùng hai Counter kết quả.
- Ba giá trị request ID tạo ba mục đăng ký; thao tác dọn xóa các mục đó khỏi registry trong thí nghiệm.
- Counter cũ còn được một biến giữ và tăng thành 6, còn Counter đăng ký mới bắt đầu từ 0.
- Gauge của nhóm xử lý cũ đã được gỡ.
- Đóng đối tượng cũ thêm lần nữa không gỡ Gauge của phiên bản thay thế, nhờ kiểm soát đóng đúng một lần.

Trong Micrometer 1.13.0, registry có `close()` nhưng không triển khai `AutoCloseable`, nên chương trình đóng registry bằng `finally`. Lớp `PoolActiveGauge` tự triển khai `AutoCloseable` nên dùng được với try-with-resources.

## 8. Áp dụng vào Spring Boot Actuator

Trong ứng dụng Boot 3.3 đã có Actuator và auto-configuration metrics, inject `MeterRegistry` do Spring quản lý. Giữ `OutcomeCounters` thành một bean sống cùng ứng dụng, để các dịch vụ dùng nó khi hoàn tất tác vụ.

Ví dụ cấu hình dùng lại hai lớp phía trên:

```java
package example.lifecycle;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    public OutcomeCounters outcomeCounters(MeterRegistry registry) {
        return new OutcomeCounters(registry);
    }

    @Bean(destroyMethod = "close")
    public PoolActiveGauge imagePoolMetrics(MeterRegistry registry) {
        return new PoolActiveGauge(registry, "image");
    }

    @Bean
    public MeterFilter poolTagLimit() {
        return MeterFilter.maximumAllowableTags(
                "demo.pool.", "pool", 8, MeterFilter.deny());
    }
}
```

Đây là cấu hình cho ứng dụng Boot sẵn có, không phải ứng dụng độc lập. Package cần nằm trong vùng quét hoặc được import. Trong ứng dụng đó, để dependency management của Boot chọn phiên bản Micrometer tương thích.

Bean Gauge trong cấu hình này có vòng đời gắn với context. Nếu nhóm xử lý là đối tượng động được tạo/hủy lúc chạy, một bean singleton cố định không thay thế được bộ quản lý vòng đời theo từng nhóm.

Giới hạn tag là một lớp bảo vệ bổ sung. Trong ví dụ, nó áp dụng cho khóa `pool` của những tên bắt đầu bằng `demo.pool.`. Khi giá trị mới vượt giới hạn, filter có thể khiến lần đăng ký đó trả về một meter không ghi nhận số liệu (NOOP). Việc nhận được một đối tượng trả về không tự chứng minh phép đo đã được đăng ký và xuất thành công.

Hãy thiết lập filter trước các phép đo liên quan bằng cơ chế cấu hình của Boot, như [tài liệu metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html) hướng dẫn. Không thêm filter muộn rồi giả định nó sẽ tự dọn tất cả meter đã có.

Giới hạn này cũng không biến các giá trị tag tùy ý thành một thiết kế đúng. Với cách triển khai Micrometer 1.13.0, bộ lọc nhớ những giá trị đã gặp; gỡ một meter không tự trả lại “suất tag” như một cơ chế TTL. Chi tiết nằm trong [MeterFilter.maximumAllowableTags](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

Nếu muốn gom nhiều phép đo thành một bộ dùng chung, có thể dùng MeterBinder để tổ chức phần đăng ký. Việc đó không tự cung cấp thao tác unbind cho mọi nguồn động; trách nhiệm giữ nguồn và gỡ phép đo vẫn cần được xác định.

## 9. Quy trình giải phóng trong hệ thống có nhiều luồng

Một quy trình điển hình cho nguồn động là:

```text
Đang hoạt động
    -> Không nhận thêm công việc sử dụng nguồn cũ
    -> Chờ/điều phối các đường ghi nhận đang chạy theo hợp đồng nghiệp vụ
    -> Gỡ đúng các meter do thành phần quản lý
    -> Gỡ tham chiếu trong map, listener, callback hoặc cache của ứng dụng
    -> Kết thúc vòng đời
```

Tùy nguồn nghiệp vụ, thứ tự dừng tài nguyên và gỡ phép đo có thể cần điều chỉnh để còn quan sát được giai đoạn dừng. Điều phải giữ là không có đường cũ tiếp tục ghi vào meter đã bị thay thế, và không có đường dọn dẹp cũ gỡ phép đo của phiên bản mới.

Nếu một component đăng ký nhiều meter, lưu danh sách những meter thuộc component đó và dọn theo danh sách. Cần xử lý cả trường hợp khởi tạo mới đăng ký được một phần rồi gặp lỗi. Không dùng phép quét theo tên quá rộng để đoán tất cả meter thuộc về mình.

Khi dùng composite registry, quản lý việc đăng ký và gỡ qua đúng registry ban đầu, đồng thời kiểm tra cấu hình xuất thực tế. Không tùy ý gỡ ở một registry con rồi giả định mọi nơi khác đã được dọn.

| Thao tác | Phạm vi cần hiểu |
| --- | --- |
| `registry.remove(meter)` | Gỡ định danh tương ứng khỏi registry đang thao tác |
| Bỏ biến hoặc xóa mục khỏi cache riêng | Bỏ một đường tham chiếu của ứng dụng; không thay thế thao tác gỡ registry |
| `registry.clear()` | Gỡ toàn bộ meter trong registry; không phù hợp để dọn riêng một nhóm |
| `registry.close()` | Kết thúc vòng đời cả registry và hoạt động xuất liên quan; không dùng để dọn một meter trong registry dùng chung |

Không lập một tác vụ định kỳ gọi `clear()` để “chống rò rỉ” trong ứng dụng. Nó có thể gỡ cả JVM/HTTP metrics và các phép đo khác, trong khi những thành phần đang sống vẫn giữ tham chiếu cũ.

Một nguồn được tạo/hủy nhiều lần cần được kiểm tra qua nhiều chu kỳ. Registry trở về số mục kỳ vọng là một bằng chứng hữu ích, nhưng chưa đủ để chứng minh không còn listener, luồng nền hoặc tham chiếu trong ứng dụng.

## 10. Chẩn đoán và bài thực hành

| Biểu hiện | Điều cần kiểm tra |
| --- | --- |
| Số meter tăng gần theo số tác vụ | Tag hoặc tên có chứa ID thay đổi theo từng tác vụ không? |
| Số meter ổn định nhưng cấp phát nhiều trong vòng lặp | Có tạo lại builder/tag hoặc tìm kiếm registry cho mỗi sự kiện không? |
| Counter sau thay thế không tăng như mong đợi | Luồng nghiệp vụ đang giữ Counter cũ hay Counter mới? |
| Gauge của nguồn mới vẫn đọc số cũ | Có đăng ký lại cùng định danh trước khi gỡ nguồn cũ không? |
| Đã remove nhưng bộ nhớ chưa giảm | Còn cache, callback, bean hoặc nguồn giữ tham chiếu không? Có chỉ đang quan sát khác biệt do GC không? |
| Đã gỡ mà backend vẫn còn lịch sử | Đang nhầm trạng thái registry với chính sách dữ liệu bên ngoài không? |
| Gauge mới biến mất sau callback đóng cũ | Quyền quản lý định danh và tính idempotent của cleanup có được bảo đảm không? |
| Không thấy số liệu của tag mới | Có filter giới hạn/từ chối đăng ký không? |

Thực hành:

1. Chạy ba lớp ở mục 4, 6, 7 và đối chiếu đủ 12 dòng stdout.
2. Chạy riêng đoạn mục 2 trên một registry mới, xác nhận 1.000 lần ghi vẫn chỉ dùng một Counter cùng định danh.
3. Tăng số sự kiện ghi qua `OutcomeCounters` nhưng giữ hai hằng enum. Số Counter vẫn là hai; giá trị của chúng tăng theo số sự kiện.
4. Lặp 100 chu kỳ tạo `PoolActiveGauge`, cập nhật, đóng rồi tạo lại cùng tên theo trình tự tuần tự. Sau mỗi lần đóng, Gauge tương ứng phải vắng trong registry; các Counter chung vẫn được giữ.
5. Thử gọi `setActive` sau `close` và kiểm tra lỗi trạng thái. Không tiếp tục dùng thành phần đã đóng.
6. Trong một registry thử nghiệm riêng, cấu hình giới hạn hai giá trị tag rồi thử giá trị thứ ba. Kiểm tra cả kết quả tìm kiếm registry, không chỉ việc lời gọi đăng ký có trả về một đối tượng.
7. Rà một vòng lặp của ứng dụng: xác định tập tên/tag tối đa, nơi giữ tham chiếu meter và điều kiện kết thúc vòng đời. Nếu có cache động, đối chiếu chính sách cache với chính sách registry.

Mục tiêu là giữ phép đo ổn định theo đại lượng cần quan sát, ghi nhận sự kiện qua các tham chiếu phù hợp và gỡ meter theo vòng đời thật của nguồn.
