# Đăng ký trùng danh tính và giới hạn của đối tượng số bất biến

Function meter của Micrometer đọc số liệu từ một đối tượng và một hàm truy xuất giá trị. Cách này hữu ích khi thư viện hoặc thành phần nghiệp vụ đã duy trì bộ đếm và tổng thời gian của chính nó. Tuy nhiên, registry định danh meter theo tên và tập tag. Nếu đăng ký lại cùng định danh với một đối tượng khác, lần đăng ký sau không thay thế nguồn dữ liệu đang được meter sử dụng.

Một vấn đề khác xuất hiện khi truyền trực tiếp Integer, Long hoặc Double vào function meter. Các lớp wrapper số này là bất biến. Hàm đo tiếp tục đọc đúng đối tượng đã được truyền lúc đăng ký; việc gán biến sang một số mới không làm đối tượng cũ thay đổi. Muốn function meter phản ánh giá trị mới, cần cung cấp một nguồn trạng thái có thể cập nhật và có vòng đời đủ dài.

## 1. Function meter đọc trạng thái từ một đối tượng

Function meter khác với meter được cập nhật trực tiếp qua API increment() hoặc record(). Khi đăng ký function meter, ứng dụng cung cấp:

1. Một đối tượng đang giữ trạng thái.
2. Một hàm đọc một hoặc nhiều giá trị từ đối tượng đó.
3. Tên meter và tập tag dùng để định danh.

Micrometer gọi hàm truy xuất khi registry lấy mẫu hoặc xuất metrics. Ứng dụng không gọi increment() trên FunctionCounter hay record() trên FunctionTimer; thay vào đó, nó cập nhật đối tượng nguồn mà function meter đang quan sát.

Hai loại thường gặp:

- FunctionCounter đọc một giá trị đếm tích lũy từ đối tượng nguồn.
- FunctionTimer đọc số lần hoàn tất và tổng thời gian tích lũy từ đối tượng nguồn.

Ví dụ FunctionCounter:

~~~java
AtomicLong completedJobs = new AtomicLong();

FunctionCounter.builder(
        "jobs.completed",
        completedJobs,
        AtomicLong::doubleValue
    )
    .description("Tổng số công việc đã hoàn tất")
    .register(registry);
~~~

Khi công việc hoàn tất, ứng dụng cập nhật nguồn:

~~~java
completedJobs.incrementAndGet();
~~~

Ở lần đọc tiếp theo, FunctionCounter gọi hàm AtomicLong::doubleValue và lấy giá trị hiện tại của cùng đối tượng AtomicLong.

## 2. Registry nhận diện meter bằng tên và tag

Tên metric và các cặp tag key/value xác định một meter identity trong registry. Ví dụ:

- jobs.completed{worker_pool=mail}
- jobs.completed{worker_pool=report}

Hai meter này có cùng tên nhưng khác tag value, vì vậy là hai identity riêng.

Ngược lại, hai builder có cùng tên và cùng tập tag đang yêu cầu cùng một identity, dù chúng được tạo từ hai object nguồn khác nhau. Registry không xem object nguồn là một chiều định danh bổ sung.

Điều này có hệ quả quan trọng với function meter: khi một identity đã được đăng ký, gọi builder lần nữa với một object khác không phải cách thay nguồn dữ liệu của meter hiện tại. Registry thường trả lại meter đã có cho identity đó. Function đã gắn với nguồn đầu tiên vẫn là nguồn được sử dụng.

Ví dụ:

~~~java
AtomicLong firstSource = new AtomicLong(10);
AtomicLong secondSource = new AtomicLong(100);

FunctionCounter first = FunctionCounter.builder(
        "jobs.completed",
        firstSource,
        AtomicLong::doubleValue
    )
    .register(registry);

FunctionCounter second = FunctionCounter.builder(
        "jobs.completed",
        secondSource,
        AtomicLong::doubleValue
    )
    .register(registry);
~~~

Cả hai builder sử dụng cùng tên và không có tag. Đăng ký second không tạo một series độc lập và cũng không chuyển meter sang secondSource. Registry đã có identity jobs.completed và tiếp tục dùng function meter được đăng ký trước.

Nếu sau đó:

~~~java
firstSource.addAndGet(2);
secondSource.addAndGet(50);
~~~

giá trị meter vẫn đọc từ firstSource. Việc secondSource thay đổi không ảnh hưởng đến meter đã đăng ký.

Không dựa vào việc gọi builder lặp lại để cập nhật object, function hoặc metadata của meter đang tồn tại. Hãy tạo meter đúng một lần trong vòng đời thành phần và giữ nguồn dữ liệu tương ứng ổn định.

## 3. Đăng ký trùng có thể làm số liệu sai như thế nào?

Lỗi thường xuất hiện khi mỗi service hoặc mỗi lần khởi tạo component tự tạo một object nguồn rồi đăng ký cùng tên và tag.

~~~java
public class WorkerMetrics {
    private final AtomicLong completed = new AtomicLong();

    public WorkerMetrics(MeterRegistry registry) {
        FunctionCounter.builder(
                "jobs.completed",
                completed,
                AtomicLong::doubleValue
            )
            .register(registry);
    }
}
~~~

Nếu hai instance WorkerMetrics cùng được tạo với cùng registry và cùng tag, cả hai cùng muốn đăng ký jobs.completed. Registry chỉ có một meter cho identity đó. Một instance có thể cập nhật object mà meter không đọc, dẫn đến số liệu của instance đó không xuất hiện.

Nếu hai instance thực sự cần số liệu riêng, phải xác định một chiều phân biệt có cardinality hữu hạn, ví dụ worker_pool=mail và worker_pool=report. Nếu chúng chỉ là hai instance của cùng một worker pool và cần tổng hợp, có thể dùng một nguồn trạng thái tổng hợp do thành phần sở hữu rõ ràng quản lý.

Không thêm instance ID ngẫu nhiên hoặc task ID vào tag chỉ để tránh xung đột. Cách đó biến mỗi instance hoặc mỗi lần chạy thành một time series mới và có thể làm cardinality tăng không kiểm soát.

### Khác registry thì sao?

Identity được quản lý bên trong từng MeterRegistry. Cùng tên và tag có thể được đăng ký độc lập trên hai registry khác nhau, mỗi registry giữ meter và nguồn của riêng nó.

Điều này hữu ích khi một ứng dụng xuất cùng metric đến nhiều backend. Tuy nhiên, nếu hai registry cùng nhận dữ liệu từ một nguồn logic, cần bảo đảm chúng được cấu hình có chủ đích và không bị scrape hoặc tổng hợp trùng ngoài ý muốn.

## 4. Vì sao Integer và Long bất biến không phù hợp làm nguồn thay đổi?

Các wrapper số như Integer, Long, Double và các lớp Number tương ứng là immutable. Sau khi tạo, giá trị bên trong object không thể thay đổi.

Ví dụ:

~~~java
Long initialValue = 10L;
Long completed = initialValue;

FunctionCounter counter = FunctionCounter.builder(
        "jobs.completed",
        initialValue,
        Number::doubleValue
    )
    .register(registry);

completed = 11L;
~~~

FunctionCounter vẫn gắn với object Long ban đầu có giá trị 10. Biến initialValue tiếp tục giữ tham chiếu mạnh đến object đó, còn lệnh gán completed = 11L chỉ làm biến completed trỏ tới một object Long khác. Nó không thay đổi object đã truyền vào builder. Nếu không còn tham chiếu mạnh nào giữ Long ban đầu, tham chiếu yếu của function meter có thể bị garbage collector thu hồi.

Vì vậy, meter tiếp tục đọc giá trị cũ. Đây là lỗi dễ nhầm vì nhìn vào biến completed, lập trình viên thấy nó đã bằng 11, nhưng function meter không quan sát biến local; nó quan sát object được truyền lúc đăng ký.

Tương tự, đoạn sau không cập nhật nguồn đã đăng ký:

~~~java
Integer active = 3;

Gauge.builder("jobs.active", active, Integer::doubleValue)
    .register(registry);

active = 4;
~~~

Function gauge vẫn đọc object Integer ban đầu. Nếu cần quan sát một trạng thái có thể thay đổi, hãy dùng một object mutable làm nguồn.

## 5. Dùng AtomicLong cho FunctionCounter

AtomicLong là một nguồn phù hợp cho FunctionCounter khi cần một bộ đếm tích lũy có thể được cập nhật từ nhiều thread.

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicLong;

public class JobMetrics {
    private final AtomicLong completedJobs = new AtomicLong();

    public JobMetrics(MeterRegistry registry) {
        FunctionCounter.builder(
                "jobs.completed",
                completedJobs,
                AtomicLong::doubleValue
            )
            .description("Tổng số công việc đã hoàn tất")
            .register(registry);
    }

    public void jobCompleted() {
        completedJobs.incrementAndGet();
    }
}
~~~

AtomicLong có hai vai trò:

- Giữ cùng một object nguồn trong suốt vòng đời meter.
- Cung cấp thao tác cập nhật nguyên tử khi nhiều thread cùng hoàn tất công việc.

FunctionCounter phù hợp với số đếm tích lũy không giảm. Không dùng nó để biểu diễn số tác vụ đang chạy hoặc số kết nối hiện tại vì các trạng thái đó có thể tăng và giảm. Dùng Gauge cho trạng thái hiện tại.

Nếu cần throughput, backend thường tính tốc độ tăng của FunctionCounter theo cửa sổ thời gian. Không reset bộ đếm về 0 theo chu kỳ nếu muốn giữ ngữ nghĩa counter đơn điệu; việc reset có thể làm rate âm hoặc tạo khoảng trống khó diễn giải.

### Dùng LongAdder khi có nhiều cập nhật đồng thời

Với bộ đếm chịu tải ghi rất cao, LongAdder có thể giảm tranh chấp giữa các thread. Nó không kế thừa Number, nhưng function có thể đọc sum():

~~~java
LongAdder completedJobs = new LongAdder();

FunctionCounter.builder(
        "jobs.completed",
        completedJobs,
        adder -> adder.sum()
    )
    .register(registry);

// Khi một công việc hoàn tất:
completedJobs.increment();
~~~

LongAdder phù hợp với bộ đếm tích lũy cần throughput cập nhật cao. Giá trị sum() là snapshot tổng hợp tại thời điểm đọc; trong lúc nhiều thread cập nhật, snapshot có thể phản ánh trạng thái tại một thời điểm hơi khác nhau giữa các lần lấy mẫu. Không dùng LongAdder cho thao tác cần compare-and-set hoặc đọc/ghi một giá trị duy nhất với điều kiện nguyên tử phức tạp.

## 6. Nếu buộc phải quan sát một số bất biến

Nếu nguồn dữ liệu bên ngoài cung cấp Long hoặc Integer bất biến, có thể bọc nó trong một object mutable như AtomicReference. Function meter giữ AtomicReference và đọc giá trị hiện tại thông qua get():

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<Long> completed = new AtomicReference<>(10L);

FunctionCounter.builder(
        "jobs.completed",
        completed,
        reference -> reference.get().doubleValue()
    )
    .register(registry);

// Thay object Long bên trong reference:
completed.set(11L);
~~~

Ở đây object được đăng ký là AtomicReference, không phải Long. AtomicReference vẫn tồn tại và có thể trỏ đến một giá trị Long mới. Function được gọi sẽ đọc giá trị hiện tại trong reference.

Vì đây vẫn là FunctionCounter, giá trị được trả về phải giữ tính tích lũy và không giảm. Nếu snapshot mới có thể nhỏ hơn snapshot cũ, FunctionCounter không còn đúng ngữ nghĩa; hãy dùng Gauge cho trạng thái có thể tăng và giảm.

Với bộ đếm số đơn giản, AtomicLong thường rõ ràng và ít lớp trung gian hơn. Chỉ dùng AtomicReference khi cần thay thế một snapshot immutable hoặc một object trạng thái bất biến phức tạp.

Đảm bảo giá trị bên trong reference không null, hoặc xử lý null trong function một cách rõ ràng. Không để hàm truy xuất ném exception khi registry scrape metrics.

## 7. FunctionTimer cũng cần một object trạng thái có thể cập nhật

FunctionTimer đọc hai đại lượng tích lũy từ một object:

- Count: số lần thao tác đã hoàn tất.
- Total time: tổng thời gian của các lần thao tác đã hoàn tất.

Meter có thể suy ra thời gian trung bình từ tổng thời gian và count. Nó không ghi lại từng lần chạy như Timer và không cung cấp phân phối đầy đủ chỉ từ hai giá trị này.

Ví dụ một lớp trạng thái:

~~~java
import java.util.concurrent.atomic.LongAdder;

public class TaskStatistics {
    private final LongAdder count = new LongAdder();
    private final LongAdder totalNanos = new LongAdder();

    public void record(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("elapsedNanos must be non-negative");
        }
        count.increment();
        totalNanos.add(elapsedNanos);
    }

    public long count() {
        return count.sum();
    }

    public double totalNanos() {
        return totalNanos.sum();
    }
}
~~~

Đăng ký FunctionTimer:

~~~java
import io.micrometer.core.instrument.FunctionTimer;

import java.util.concurrent.TimeUnit;

TaskStatistics statistics = new TaskStatistics();
FunctionTimer.builder(
        "tasks.execution",
        statistics,
        TaskStatistics::count,
        TaskStatistics::totalNanos,
        TimeUnit.NANOSECONDS
    )
    .description("Thời gian thực thi tích lũy của các tác vụ")
    .register(registry);
~~~

Khi một task hoàn tất:

~~~java
long startedAt = System.nanoTime();
try {
    task.run();
} finally {
    statistics.record(System.nanoTime() - startedAt);
}
~~~

FunctionTimer đọc count và totalNanos từ cùng object statistics. Object này phải sống đủ lâu và được cập nhật trong toàn bộ vòng đời của meter.

Trong ví dụ LongAdder, count và totalNanos là hai snapshot được đọc riêng. Khi có cập nhật đồng thời, một lần scrape có thể đọc count ngay trước một lần cập nhật và totalNanos ngay sau lần cập nhật đó. Với metrics tổng hợp, sai khác nhỏ theo thời điểm lấy mẫu thường chấp nhận được. Nếu ứng dụng cần một snapshot nhất quán tuyệt đối giữa nhiều trường, cần thiết kế một nguồn snapshot đồng bộ riêng và cân nhắc chi phí lock.

Nếu cần histogram, percentile hoặc SLO cho từng lần hoàn tất, hãy dùng Timer thông thường thay vì chỉ dựa vào FunctionTimer. FunctionTimer phù hợp khi thành phần nguồn đã duy trì count và tổng thời gian tích lũy và ứng dụng chỉ cần công bố các số liệu tổng hợp đó.

## 8. Quản lý vòng đời và tham chiếu của object nguồn

Function meter thường giữ tham chiếu yếu đến object nguồn. Điều này giúp meter không giữ sống một object graph lớn chỉ vì nó được đăng ký trong registry.

Hệ quả là ứng dụng phải giữ tham chiếu mạnh đến object nguồn trong suốt thời gian meter cần hoạt động. Cách phổ biến là lưu object trong field của singleton bean hoặc thành phần quản lý trạng thái:

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicLong;

@Component
public class JobMetrics {
    private final AtomicLong completedJobs = new AtomicLong();

    public JobMetrics(MeterRegistry registry) {
        FunctionCounter.builder(
                "jobs.completed",
                completedJobs,
                AtomicLong::doubleValue
            )
            .register(registry);
    }
}
~~~

Tránh tạo object ngay trong lời gọi builder rồi không giữ lại ở đâu:

~~~java
FunctionCounter.builder(
        "jobs.completed",
        new AtomicLong(),
        AtomicLong::doubleValue
    )
    .register(registry);
~~~

Sau khi phương thức kết thúc, không còn tham chiếu mạnh đến AtomicLong. Garbage collector có thể thu hồi nó, khiến function meter không còn đọc được trạng thái. Tùy implementation, meter có thể trả về NaN hoặc không cung cấp số đo hợp lệ.

Với FunctionTimer, cũng phải giữ object thống kê và mọi trạng thái cần thiết. Đăng ký meter một lần trong constructor hoặc bước cấu hình, sau đó chỉ cập nhật object nguồn.

## 9. Kiểm thử đăng ký trùng và nguồn bất biến

Có thể dùng SimpleMeterRegistry để kiểm tra rằng cùng identity không chuyển sang nguồn mới chỉ vì builder được gọi lại.

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FunctionCounterIdentityTest {

    @Test
    void duplicateIdentityKeepsOriginalSource() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicLong firstSource = new AtomicLong(10);
            AtomicLong secondSource = new AtomicLong(100);

            FunctionCounter.builder(
                    "jobs.completed",
                    firstSource,
                    AtomicLong::doubleValue
                )
                .register(registry);

            FunctionCounter.builder(
                    "jobs.completed",
                    secondSource,
                    AtomicLong::doubleValue
                )
                .register(registry);

            firstSource.addAndGet(2);
            secondSource.addAndGet(50);

            assertEquals(
                12.0,
                registry.get("jobs.completed").functionCounter().count()
            );
        }
    }
}
~~~

Kiểm thử này chứng minh registry tiếp tục đọc nguồn của lần đăng ký đầu tiên. Hành vi chi tiết khi đăng ký trùng hoặc xung đột loại meter có thể khác nhau theo registry và phiên bản; điều quan trọng là không dựa vào lần đăng ký thứ hai để thay nguồn đã tồn tại.

Kiểm thử giới hạn của Long bất biến:

~~~java
@Test
void immutableLongDoesNotReflectVariableReassignment() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        Long initialValue = 10L;
        Long completed = initialValue;

        FunctionCounter.builder(
                "jobs.completed.immutable",
                initialValue,
                Number::doubleValue
            )
            .register(registry);

        completed = 20L;

        assertEquals(
            10.0,
            registry.get("jobs.completed.immutable")
                .functionCounter()
                .count()
        );
    }
}
~~~

Biến completed trỏ tới Long mới có giá trị 20, nhưng meter vẫn giữ object Long ban đầu có giá trị 10.

Nên có thêm test cho FunctionTimer để xác minh count và total time tăng theo cùng nguồn thống kê, cũng như test vòng đời để đảm bảo object nguồn vẫn được giữ mạnh trong lúc meter cần hoạt động.

## 10. Cách xử lý khi cần thay nguồn hoặc đổi identity

Nếu cần chuyển sang một object nguồn khác, hãy xác định mục tiêu trước:

| Nhu cầu | Cách xử lý |
|---|---|
| Cập nhật giá trị đếm theo thời gian | Giữ một AtomicLong hoặc LongAdder làm nguồn |
| Thay snapshot immutable | Bọc snapshot trong AtomicReference và function đọc reference |
| Hai nhóm số liệu độc lập | Dùng tag có tập giá trị hữu hạn hoặc tên meter riêng |
| Thay nguồn của meter đang tồn tại | Quản lý vòng đời registry/meter và thực hiện migration có kiểm soát |
| Hai backend nhận cùng một số đo | Đăng ký nguồn tương ứng trên từng registry hoặc dùng composite có chủ đích |
| Muốn đếm trạng thái tăng/giảm | Dùng Gauge với nguồn mutable |
| Muốn ghi sự kiện mỗi lần xảy ra | Dùng Counter |
| Muốn đo thời gian từng lần hoàn tất và histogram | Dùng Timer |

Không đổi tag bằng ID duy nhất để ép registry tạo meter mới cho mỗi object. Nếu identity mới có ý nghĩa nghiệp vụ, hãy chọn tag thể hiện một chiều phân loại ổn định. Nếu chỉ muốn thay implementation hoặc object nguồn, không nên tạo một series mới chỉ để né quy tắc đăng ký trùng; hãy quản lý nguồn và vòng đời meter đúng cách.

## 11. Các lỗi thường gặp

- **Đăng ký cùng tên và tag với object mới:** registry không tự chuyển function sang object mới.
- **Cho rằng object nguồn là một phần identity:** registry phân biệt meter chủ yếu bằng tên và tag.
- **Truyền Long hoặc Integer rồi gán biến sang số mới:** meter vẫn đọc object bất biến ban đầu.
- **Dùng FunctionCounter cho trạng thái có thể giảm:** counter tích lũy phải giữ ngữ nghĩa đơn điệu.
- **Tạo object nguồn tạm thời:** tham chiếu yếu có thể khiến object bị garbage collector thu hồi.
- **Đăng ký meter trong mỗi request:** tạo nhiều lần tra cứu/đăng ký và làm khó kiểm soát identity.
- **Dùng cùng tên/tag cho hai loại meter khác nhau:** có thể phát sinh cảnh báo hoặc xung đột đăng ký.
- **Đưa ID vào tag để tránh trùng:** cardinality tăng theo số object hoặc task.
- **Dùng FunctionTimer khi cần histogram:** count và total time không thay thế phân phối từng lần hoàn tất.
- **Không giữ nguồn thống kê đủ lâu:** function meter mất dữ liệu khi object nguồn không còn tồn tại.

## 12. Checklist triển khai

- [ ] Tên meter và tag được xác định ổn định trước khi đăng ký.
- [ ] Không có hai nguồn khác nhau cùng cạnh tranh một identity trong cùng registry.
- [ ] FunctionCounter đọc một bộ đếm tích lũy không giảm.
- [ ] FunctionTimer đọc count và tổng thời gian tích lũy từ cùng nguồn logic.
- [ ] Không truyền trực tiếp wrapper số bất biến nếu cần quan sát giá trị thay đổi.
- [ ] Nguồn mutable như AtomicLong, LongAdder hoặc AtomicReference được giữ trong field có vòng đời phù hợp.
- [ ] Hàm truy xuất nhanh, không có side effect và không ném exception khi scrape.
- [ ] Không đưa ID duy nhất vào tag.
- [ ] Đã kiểm thử đăng ký trùng identity và hành vi của nguồn đầu tiên.
- [ ] Đã kiểm thử vòng đời object nguồn và dữ liệu FunctionTimer.
- [ ] Dùng Timer hoặc Counter trực tiếp khi cần semantics mà function meter không cung cấp.

Function meter phù hợp khi ứng dụng đã có một object trạng thái tích lũy và muốn Micrometer đọc nó theo chu kỳ. Hãy đăng ký mỗi identity một lần, giữ nguồn dữ liệu có thể cập nhật và tồn tại đủ lâu, đồng thời không dùng wrapper số bất biến làm nguồn cho giá trị cần thay đổi. Những quy tắc này giúp tránh meter trùng, số liệu đứng yên và dữ liệu bị mất khi object nguồn bị thu hồi.

