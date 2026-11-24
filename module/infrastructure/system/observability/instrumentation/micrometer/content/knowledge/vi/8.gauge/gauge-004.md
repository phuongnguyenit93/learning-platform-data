# Dùng AtomicInteger hoặc AtomicLong cho trạng thái có thể thay đổi

Gauge trong Micrometer biểu diễn giá trị của một trạng thái tại thời điểm được đọc. Khi trạng thái đó được cập nhật bởi nhiều thread, một biến số nguyên thông thường có thể không đủ an toàn. `AtomicInteger` và `AtomicLong` cung cấp các thao tác đọc, ghi và cập nhật nguyên tử, phù hợp để làm nguồn dữ liệu cho Gauge.

Ví dụ thường gặp là số tác vụ đang chạy, số request đang hoạt động, số kết nối đang được sử dụng hoặc tổng số byte hiện có trong một bộ đệm. Ứng dụng cập nhật atomic value khi trạng thái thay đổi; Gauge đọc giá trị hiện tại từ đối tượng đó khi registry lấy mẫu.

## 1. Gauge đo trạng thái hiện tại

Gauge khác Counter ở ngữ nghĩa:

- Counter đếm sự kiện tích lũy và chỉ tăng.
- Gauge phản ánh trạng thái có thể tăng hoặc giảm.
- Timer ghi nhận thời lượng và số lần thực hiện.
- Distribution summary ghi nhận phân phối của một đại lượng.

Giả sử ứng dụng cần biết số tác vụ đang chạy đồng thời. Khi một tác vụ bắt đầu, giá trị tăng một; khi tác vụ kết thúc, giá trị giảm một. Giá trị tại một thời điểm là trạng thái hiện tại, vì vậy Gauge phù hợp.

~~~text
Tác vụ bắt đầu      activeJobs = activeJobs + 1
Tác vụ kết thúc     activeJobs = activeJobs - 1
Gauge đọc           activeJobs hiện tại
~~~

Nếu mục tiêu là đếm tổng số tác vụ đã bắt đầu trong suốt thời gian chạy, hãy dùng Counter. Không dùng Gauge thay thế Counter chỉ vì cả hai đều chứa một số nguyên.

## 2. Vì sao cần AtomicInteger hoặc AtomicLong?

Trong ứng dụng đa luồng, nhiều thread có thể cập nhật cùng một biến. Phép cộng hoặc trừ thông thường gồm thao tác đọc, tính toán và ghi lại. Khi các bước này xen kẽ, một cập nhật có thể bị mất.

Ví dụ với biến int dùng chung:

~~~java
private int activeJobs;

public void jobStarted() {
    activeJobs++;
}
~~~

Nếu hai thread cùng đọc giá trị 5 trước khi ghi, cả hai có thể cùng ghi 6. Giá trị đúng phải là 7 nhưng kết quả chỉ còn 6. Đây là race condition do phép tăng không nguyên tử.

Có thể đồng bộ bằng synchronized, nhưng AtomicInteger cung cấp các thao tác cập nhật nguyên tử thuận tiện cho những trạng thái số đơn giản:

~~~java
private final AtomicInteger activeJobs = new AtomicInteger();

public void jobStarted() {
    activeJobs.incrementAndGet();
}

public void jobFinished() {
    activeJobs.decrementAndGet();
}
~~~

Các thao tác trên được thực hiện nguyên tử. Nhiều thread cùng gọi incrementAndGet() sẽ không làm mất lần tăng.

### AtomicInteger và AtomicLong khác nhau thế nào?

| Kiểu | Phạm vi số nguyên | Trường hợp phù hợp |
|---|---:|---|
| AtomicInteger | -2.147.483.648 đến 2.147.483.647 | Số request hoặc tác vụ đồng thời, số phần tử có giới hạn |
| AtomicLong | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Byte, dung lượng, số lượng có thể lớn hoặc bộ đếm trạng thái dài hạn |

Chọn kiểu theo giới hạn thực tế của đại lượng. Dùng AtomicInteger cho số tác vụ đồng thời thường là đủ. Dùng AtomicLong cho tổng byte hoặc số lượng có thể vượt giới hạn của int.

Micrometer đọc giá trị Gauge dưới dạng số thực double. Vì vậy, dù nguồn là AtomicLong, các số nguyên rất lớn vượt quá khoảng biểu diễn chính xác của double (xấp xỉ 2^53) có thể mất độ chính xác khi xuất metrics. Với trạng thái vận hành thông thường, giới hạn này hiếm khi là vấn đề; không dùng Gauge làm kênh lưu trữ số nguyên chính xác tuyệt đối.

## 3. Đăng ký AtomicInteger làm nguồn Gauge

Micrometer có thể đăng ký một Gauge đọc trực tiếp giá trị từ AtomicInteger:

~~~java
AtomicInteger activeJobs = new AtomicInteger();

Gauge.builder("jobs.active", activeJobs, AtomicInteger::get)
    .description("Số tác vụ đang chạy")
    .register(registry);
~~~

Ba thành phần quan trọng:

1. "jobs.active" là tên metric.
2. activeJobs là đối tượng giữ trạng thái có thể thay đổi.
3. AtomicInteger::get là hàm đọc giá trị hiện tại khi Gauge được lấy mẫu.

Sau khi đăng ký, cập nhật atomic value sẽ làm thay đổi giá trị Gauge ở lần đọc tiếp theo:

~~~java
activeJobs.incrementAndGet();
// Gauge đọc được 1

activeJobs.incrementAndGet();
// Gauge đọc được 2

activeJobs.decrementAndGet();
// Gauge đọc được 1
~~~

Không cần đăng ký lại Gauge sau mỗi lần tăng hoặc giảm. Meter được đăng ký một lần; đối tượng atomic tiếp tục cung cấp trạng thái mới.

### Giữ tham chiếu mạnh đến đối tượng được đo

Gauge của Micrometer thường giữ tham chiếu yếu đến đối tượng nguồn để tránh việc meter giữ toàn bộ object graph sống mãi. Vì vậy, ứng dụng phải giữ tham chiếu mạnh đến đối tượng được đo trong suốt thời gian cần quan sát.

Cách an toàn là giữ atomic value trong một field của bean hoặc thành phần có vòng đời dài:

~~~java
@Component
public class JobState {
    private final AtomicInteger activeJobs = new AtomicInteger();

    public JobState(MeterRegistry registry) {
        Gauge.builder("jobs.active", activeJobs, AtomicInteger::get)
            .description("Số tác vụ đang chạy")
            .register(registry);
    }
}
~~~

Tránh tạo atomic object chỉ dùng trong lời gọi đăng ký:

~~~java
Gauge.builder(
    "jobs.active",
    new AtomicInteger(),
    AtomicInteger::get
).register(registry);
~~~

Sau khi constructor hoặc phương thức kết thúc, không còn tham chiếu mạnh nào giữ đối tượng đó. Nó có thể bị garbage collector thu hồi, khiến Gauge không còn đọc được giá trị mong muốn. Một giá trị Gauge không còn nguồn hợp lệ có thể được biểu diễn là NaN tùy registry và backend.

## 4. Dùng AtomicLong cho dung lượng hoặc tổng byte hiện tại

Khi trạng thái có thể lớn hơn phạm vi của int, dùng AtomicLong. Ví dụ, ứng dụng cần quan sát tổng số byte đang nằm trong bộ đệm:

~~~java
private final AtomicLong bufferedBytes = new AtomicLong();

public void bytesAdded(long count) {
    if (count < 0) {
        throw new IllegalArgumentException("count must be non-negative");
    }
    bufferedBytes.addAndGet(count);
}

public void bytesReleased(long count) {
    if (count < 0) {
        throw new IllegalArgumentException("count must be non-negative");
    }

    bufferedBytes.updateAndGet(current -> {
        if (count > current) {
            throw new IllegalStateException("buffered byte count would become negative");
        }
        return current - count;
    });
}
~~~

Đăng ký Gauge đọc giá trị:

~~~java
Gauge.builder("buffer.bytes.current", bufferedBytes, AtomicLong::get)
    .description("Tổng số byte hiện có trong bộ đệm")
    .baseUnit("bytes")
    .register(registry);
~~~

addAndGet cập nhật nguyên tử số byte tăng thêm. updateAndGet thực hiện cập nhật dựa trên giá trị hiện tại và kiểm tra không cho kết quả âm. Hàm cập nhật có thể được gọi lại khi có tranh chấp, vì vậy lambda chỉ nên tính toán từ đầu vào và giá trị hiện tại; không đặt side effect bên trong lambda.

Nếu một thành phần khác đã là nguồn dữ liệu có thẩm quyền về dung lượng, có thể dùng set(currentValue) để đồng bộ snapshot. Tuy nhiên, nếu nhiều thread cùng cập nhật theo delta, hãy dùng thao tác nguyên tử như addAndGet hoặc updateAndGet thay vì đọc rồi ghi tách rời.

## 5. Tích hợp Gauge với Spring Boot

Trong Spring Boot, có thể tạo một bean chuyên quản lý trạng thái và đăng ký Gauge trong constructor. Ví dụ sau theo dõi số tác vụ đang chạy:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

@Component
public class JobMetrics {
    private final AtomicInteger activeJobs = new AtomicInteger();

    public JobMetrics(MeterRegistry registry) {
        Gauge.builder("jobs.active", activeJobs, AtomicInteger::get)
            .description("Số tác vụ đang chạy")
            .register(registry);
    }

    public <T> T trackJob(Supplier<T> operation) {
        activeJobs.incrementAndGet();
        try {
            return operation.get();
        } finally {
            activeJobs.decrementAndGet();
        }
    }

    public int activeJobs() {
        return activeJobs.get();
    }
}
~~~

Service sử dụng wrapper để theo dõi vòng đời tác vụ:

~~~java
public Result process(Job job) {
    return jobMetrics.trackJob(() -> jobProcessor.process(job));
}
~~~

Việc tăng giá trị diễn ra trước khi xử lý và giảm trong finally. Vì vậy, nếu xử lý kết thúc bình thường hoặc ném exception, số tác vụ đang chạy vẫn được giảm đúng một lần.

Chỉ tăng sau khi tác vụ thực sự được nhận và bắt đầu thực thi. Nếu tăng ngay khi submit vào executor nhưng tác vụ bị từ chối hoặc bị hủy trước khi chạy, cần có đường xử lý tương ứng để giảm lại; nếu không Gauge có thể bị lệch.

Trong ứng dụng có nhiều loại tác vụ, hãy chọn tên và tag có cardinality thấp, chẳng hạn worker_pool=mail hoặc worker_pool=report. Không gắn task ID, request ID hoặc tên file tùy ý vào tag.

## 6. Cập nhật atomic state an toàn trong nhiều thread

Các API thường dùng của AtomicInteger và AtomicLong gồm:

| API | Ý nghĩa |
|---|---|
| get() | Đọc giá trị hiện tại |
| set(value) | Ghi giá trị mới |
| incrementAndGet() | Tăng một và trả về giá trị sau khi tăng |
| getAndIncrement() | Tăng một và trả về giá trị trước khi tăng |
| decrementAndGet() | Giảm một và trả về giá trị sau khi giảm |
| addAndGet(delta) | Cộng delta và trả về kết quả |
| compareAndSet(expect, update) | Chỉ cập nhật nếu giá trị hiện tại bằng expect |
| updateAndGet(function) | Tính và cập nhật nguyên tử theo hàm |

Với Gauge, thường chỉ cần get() để đọc và các thao tác cập nhật để thay đổi trạng thái. Chọn API theo ý nghĩa nghiệp vụ; đừng dùng set nếu nhiều thread đang cộng/trừ delta vì một lần set có thể ghi đè cập nhật vừa xảy ra từ thread khác.

### Bảo đảm cặp tăng/giảm

Với số tác vụ đang hoạt động, mỗi lần tăng phải có một lần giảm tương ứng. Cấu trúc try/finally giúp bảo đảm điều này:

~~~java
activeJobs.incrementAndGet();
try {
    executeJob();
} finally {
    activeJobs.decrementAndGet();
}
~~~

Không viết:

~~~java
activeJobs.incrementAndGet();
executeJob();
activeJobs.decrementAndGet();
~~~

Nếu executeJob() ném exception, dòng giảm sẽ không chạy và Gauge bị tăng sai vĩnh viễn.

Cũng cần đảm bảo không gọi giảm hai lần cho cùng tác vụ, chẳng hạn vừa giảm trong callback hoàn tất vừa giảm trong nhánh xử lý hủy. Atomic operation bảo đảm thao tác cập nhật không bị mất; nó không tự hiểu quy tắc vòng đời của tác vụ.

### Tránh trạng thái âm

Nếu Gauge biểu diễn số lượng đang hoạt động hoặc dung lượng hiện tại, giá trị âm thường cho thấy lỗi quản lý vòng đời. Hãy thiết kế điểm tăng/giảm rõ ràng và kiểm thử các đường success, failure, timeout, cancellation và rejection.

Không che giấu lỗi bằng cách luôn ép giá trị âm về 0 sau mỗi lần giảm. Việc clamp có thể làm dashboard trông hợp lệ nhưng che mất lỗi đếm. Nên phát hiện invariant bị vi phạm tại nơi cập nhật và sửa nguyên nhân.

## 7. Gauge là snapshot, không phải lịch sử sự kiện

Gauge được lấy mẫu khi registry hoặc backend đọc metrics. Nếu một giá trị tăng từ 0 lên 10 rồi trở về 0 giữa hai lần scrape, backend có thể chỉ nhìn thấy 0 ở cả hai lần đọc. Gauge không lưu lại đỉnh hoặc mọi thay đổi trung gian.

Ví dụ:

~~~text
t0: scrape -> activeJobs = 0
t1: 10 tác vụ chạy đồng thời
t2: tất cả tác vụ kết thúc
t3: scrape -> activeJobs = 0
~~~

Dashboard không thể kết luận rằng số tác vụ đã từng đạt 10 chỉ từ hai mẫu Gauge trên.

Nếu cần quan sát số lượng hiện tại, dùng Gauge. Nếu cần đếm tổng số tác vụ đã chạy, dùng Counter. Nếu cần biết thời gian thực thi, dùng Timer. Nếu cần theo dõi giá trị lớn nhất hoặc phân phối theo thời gian, cân nhắc một meter hoặc cơ chế thống kê phù hợp với câu hỏi đó.

### Theo dõi giá trị đỉnh

Có thể dùng một AtomicInteger hoặc AtomicLong riêng để lưu mức cao nhất đã quan sát:

~~~java
private final AtomicInteger peakActiveJobs = new AtomicInteger();

private void updatePeak(int current) {
    peakActiveJobs.accumulateAndGet(current, Math::max);
}
~~~

Đăng ký peakActiveJobs như một Gauge riêng. Giá trị này biểu diễn đỉnh kể từ lần reset gần nhất, không phải số tác vụ đang hoạt động. Nếu cần đỉnh theo từng cửa sổ thời gian, phải thiết kế chu kỳ reset và đồng bộ rõ ràng; không dùng chung tên metric cho hai ngữ nghĩa khác nhau.

## 8. Kiểm thử Gauge dựa trên AtomicInteger

Có thể dùng SimpleMeterRegistry để kiểm tra giá trị Gauge mà không cần Prometheus:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AtomicGaugeTest {

    @Test
    void gaugeReadsLatestAtomicIntegerValue() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicInteger activeJobs = new AtomicInteger(2);

            Gauge.builder("jobs.active", activeJobs, AtomicInteger::get)
                .register(registry);

            assertEquals(
                2.0,
                registry.get("jobs.active").gauge().value()
            );

            activeJobs.incrementAndGet();

            assertEquals(
                3.0,
                registry.get("jobs.active").gauge().value()
            );

            activeJobs.set(0);

            assertEquals(
                0.0,
                registry.get("jobs.active").gauge().value()
            );
        }
    }
}
~~~

Kiểm thử xác minh Gauge đọc giá trị hiện tại của cùng đối tượng atomic sau các lần cập nhật. Không cần đăng ký lại meter sau khi thay đổi giá trị.

Với lớp quản lý tác vụ, nên kiểm thử cả trường hợp thành công và exception:

- Giá trị tăng trong khi tác vụ đang thực thi.
- Giá trị trở về mức ban đầu khi tác vụ hoàn tất.
- Giá trị vẫn được giảm khi tác vụ ném exception.
- Nhiều tác vụ đồng thời không làm mất lần tăng/giảm.
- Giá trị không âm sau khi tất cả tác vụ kết thúc.

Nếu cần kiểm thử concurrency, dùng latch hoặc barrier để điều khiển thời điểm các thread bắt đầu và kết thúc, thay vì dựa vào Thread.sleep hoặc timing ngẫu nhiên.

## 9. Các lỗi thường gặp

- **Dùng int++ hoặc long++ trên biến dùng chung:** phép tăng không nguyên tử, có thể mất cập nhật khi nhiều thread chạy đồng thời.
- **Tạo atomic object tạm thời khi đăng ký Gauge:** object có thể bị garbage collector thu hồi vì Gauge thường giữ tham chiếu yếu.
- **Đăng ký Gauge nhiều lần trong mỗi lần cập nhật:** làm phức tạp registry và không cần thiết; đăng ký một lần, cập nhật atomic value.
- **Quên giảm trong nhánh exception:** Gauge của tác vụ đang chạy bị cao hơn thực tế.
- **Giảm hai lần khi hoàn tất và hủy:** số lượng có thể trở thành âm.
- **Dùng Gauge để đếm tổng sự kiện:** Gauge chỉ biểu diễn snapshot; Counter phù hợp hơn.
- **Gọi set từ nhiều thread trong khi các thread khác cộng delta:** cập nhật có thể ghi đè nhau nếu nguồn giá trị không được đồng bộ.
- **Dùng AtomicInteger cho giá trị có thể vượt giới hạn int:** có nguy cơ tràn số; cân nhắc AtomicLong.
- **Đọc một cấu trúc dữ liệu đắt tiền trong hàm Gauge:** thao tác lấy mẫu có thể gây tải hoặc cạnh tranh lock; ưu tiên hàm đọc nhanh và không có side effect.
- **Dùng Gauge để lưu lịch sử hoặc giá trị đỉnh:** cần meter và logic thống kê riêng cho những mục tiêu đó.

## 10. Checklist triển khai

- [ ] Đại lượng thực sự là trạng thái có thể tăng và giảm.
- [ ] Đã chọn AtomicInteger hoặc AtomicLong theo phạm vi giá trị.
- [ ] Atomic object được giữ trong field có vòng đời đủ dài.
- [ ] Gauge được đăng ký một lần với tên và tag ổn định.
- [ ] Hàm đọc Gauge nhanh, an toàn và không có side effect.
- [ ] Các cập nhật dùng thao tác nguyên tử phù hợp.
- [ ] Tác vụ tăng/giảm theo cặp, kể cả khi có exception hoặc cancellation.
- [ ] Có kiểm soát invariant để trạng thái không âm.
- [ ] Không đưa ID hoặc giá trị cardinality cao vào tag.
- [ ] Đã kiểm thử cập nhật liên tục và nhiều thread.
- [ ] Đã xác định rõ Gauge là snapshot và không dùng nó thay cho lịch sử sự kiện.

Khi một trạng thái số được cập nhật đồng thời bởi nhiều thread, hãy giữ nó trong một atomic object có vòng đời rõ ràng, đăng ký Gauge đọc đối tượng đó đúng một lần và cập nhật bằng các thao tác nguyên tử. Cách làm này giúp số đo phản ánh trạng thái hiện tại mà không làm mất cập nhật do race condition.

