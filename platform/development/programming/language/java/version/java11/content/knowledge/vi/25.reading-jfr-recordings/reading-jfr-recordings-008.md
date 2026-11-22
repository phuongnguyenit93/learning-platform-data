# Đọc bản ghi JFR: Giới hạn dữ liệu lấy mẫu và bằng chứng nhân quả (Java 11+)

## 1. Vì sao phải diễn giải JFR thận trọng?

**Java Flight Recorder (JFR)** là cơ chế ghi nhận sự kiện chẩn đoán và profiling tích hợp trong JVM. Trong Java 11, module `jdk.jfr` dùng để ghi sự kiện, còn `jdk.jfr.consumer` cung cấp các lớp `RecordingFile`, `RecordedEvent` và `RecordedStackTrace` để đọc file `.jfr`. Đây vẫn là công nghệ có giá trị trong Java hiện đại.

Một bản ghi JFR có thể giúp kỹ sư phát hiện CPU hotspot, GC pause, tranh chấp khóa, socket/file I/O và một số hành vi ứng dụng. Nhưng cần phân biệt rõ:

- **Quan sát:** “Trong 100 mẫu CPU được thu, phương thức A xuất hiện ở 45 mẫu”.
- **Ước lượng:** “A có thể là vùng code thường xuyên sử dụng CPU trong phạm vi ghi và bộ lọc này”.
- **Giả thuyết:** “A có thể góp phần làm tăng latency”.
- **Bằng chứng nhân quả:** “Khi can thiệp có kiểm soát vào A, triệu chứng thay đổi theo cơ chế dự đoán, được lặp lại và kiểm tra các yếu tố gây nhiễu”.

Chỉ dòng thứ nhất dựa trực tiếp vào phép đếm mẫu. Các dòng sau cần thêm ngữ cảnh và phương pháp kiểm chứng.

**Mục tiêu của bài:**
1. Nhận biết event thực sự, duration event, periodic event và sampled event.
2. Đọc đúng start/end time, duration, thread và stack trong API Java 11.
3. Nêu giới hạn thống kê của sampling, threshold, mất dữ liệu, stack và window.
4. Không nhầm `CPU time` với `wall-clock latency` hoặc thời gian chờ.
5. Phân biệt **tương quan, thứ tự thời gian, happens-before và quan hệ nhân quả**.
6. Kết hợp JFR với metrics, structured logs, tracing và kiểm thử có đối chứng.
7. Chạy một chương trình Java 11 ghi/đọc sự kiện JFR và đưa ra kết luận vừa đúng phạm vi bằng chứng.

Bài tập trung kiến thức còn áp dụng; không dùng cách bật Flight Recorder thương mại hoặc API lỗi thời.

## 2. Các nguồn dữ liệu JFR không giống nhau

| Nhóm dữ liệu | Bản chất | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Instant event** | Một tín hiệu được ghi ở thời điểm cụ thể | Custom outcome event | Không đo tổng thời gian xử lý. |
| **Duration event** | Có khoảng bắt đầu/kết thúc | I/O, lock, custom `Event.begin/end` | Duration không mặc nhiên là CPU time. |
| **Periodic event** | Một phép quan sát theo chu kỳ | `jdk.CPULoad` | Không chứng minh trạng thái giữa hai thời điểm lấy mẫu. |
| **CPU/method sample** | Chụp trạng thái thread/stack tại thời điểm lấy mẫu | `jdk.ExecutionSample` | Không là bộ đếm mọi method call. |
| **Allocation/sample-based telemetry** | Chỉ quan sát những allocation theo cơ chế event | Một số allocation events | Không tự bằng tổng objects hoặc bytes. |
| **Custom application event** | Ứng dụng phát event theo code | `lesson.OperationStep` | Độ bao phủ phụ thuộc code, threshold và cấu hình. |

Một duration event cũng có thể kèm stack trace, còn một sample có thể không có stack. Vì vậy **không phân loại event dựa duy nhất vào việc có stack trace**.

Không xem file JFR như log lịch sử đầy đủ từng request, từng lời gọi hàm hoặc mọi thread state; đây là hệ thống quan sát **có lựa chọn và có chi phí**.

### 2.1. Ví dụ ngữ nghĩa của một event

```java
recording.enable("jdk.FileWrite")
         .withThreshold(Duration.ofMillis(20));
```

Đây là mảnh mã minh họa trong một phương thức, giả định đã có `Recording recording`, import `Duration`.

Nếu file chứa 50 `jdk.FileWrite` events, không có nghĩa ứng dụng chỉ thực hiện 50 lần ghi file. Những lần ghi ngắn hơn ngưỡng, ngoài thời gian recording hoặc không được thu sẽ không xuất hiện. **Count của event đã lọc không phải tổng count nghiệp vụ.**

## 3. Giới hạn thống kê của dữ liệu lấy mẫu

### 3.1. Sample share không phải CPU time chính xác

Giả sử cùng một cửa sổ và bộ lọc có:

| Leaf method trong CPU samples | Số mẫu | Tỷ lệ trong tập 100 mẫu |
| --- | ---: | ---: |
| `PriceEngine.calculate()` | 45 | 45% |
| `JsonSerializer.write()` | 35 | 35% |
| Các phương thức khác | 20 | 20% |

Diễn giải hợp lệ:

> “Trong 100 CPU samples hợp lệ được phân tích, leaf method `PriceEngine.calculate()` có mặt ở 45 samples (45%).”

Diễn giải không hợp lệ nếu thiếu thêm bằng chứng:

> “`PriceEngine.calculate()` chiếm chính xác 45% CPU của toàn bộ hệ thống và làm chậm 45% request.”

Công thức:

```text
observedSampleShare(method)
    = count(samples attributed to method) / count(relevant samples)
```

**Mẫu số** ở đây là tập mẫu đã thu/được lọc. Không phải 100 requests, 100 milliseconds CPU, hay một quần thể thống kê được chọn ngẫu nhiên tuyệt đối.

### 3.2. Mẫu ít thì bất định cao

Hai quan sát đều 40%:

- Method A xuất hiện **2/5** samples.
- Method A xuất hiện **2.000/5.000** samples.

Trường hợp đầu có độ bất định rất lớn. Trường hợp sau có nhiều dữ liệu hơn, nhưng **vẫn phải xét tính đại diện**, vì các samples có thể liên quan chặt chẽ theo thời gian, thread, workload phase và scheduler.

Không mặc nhiên coi các CPU samples là mẫu **iid (độc lập, cùng phân phối)** rồi áp khoảng tin cậy nhị thức để tuyên bố độ chính xác. Với dữ liệu lấy mẫu theo thời gian, sự phụ thuộc và thiên lệch có thể đáng kể.

Báo cáo nên ghi rõ:
- N mẫu ban đầu và N mẫu được phân tích sau bộ lọc.
- Time window, JFR event type, sampling configuration.
- Các thread/host/endpoint được chọn và loại bỏ.
- Số stack traces thiếu/không giải mã được.
- Kết quả lặp lại ở các cửa sổ tương đương hay không.

### 3.3. Một method vắng mặt không chứng minh nó không chạy

Một đoạn code thực thi vài microsecond có thể không trùng thời điểm sampling. Một burst CPU ngắn cũng có thể bị bỏ lỡ. Các nguyên nhân khác:
- Event không được bật hoặc tần suất lấy mẫu quá thưa.
- Bản ghi quá ngắn hoặc không phủ đúng incident window.
- Thread đang chờ I/O/lock/sleep, không nằm trong tập method CPU sampling.
- Stack depth bị giới hạn hoặc bị lọc.
- JIT/inlining hoặc mapping stack làm tên method không xuất hiện như kỳ vọng.
- Dữ liệu đã bị loại khỏi repository trước khi dump.
- Sự kiện bị filter/threshold hoặc điều kiện thu không đạt.

**Không thấy event != xác nhận event không xảy ra.**

## 4. CPU time, elapsed time và blocked time là ba điều khác nhau

Một request chậm 120 ms có thể gồm:

```text
Request 120 ms (số minh họa)
   |
   +-- Java CPU work                15 ms
   +-- Waiting for downstream      85 ms
   +-- Lock/scheduler wait         20 ms
```

CPU sampling có thể chỉ ra `Serializer.encode` là điểm nóng trong 15 ms CPU. Nhưng không giải thích đủ 85 ms chờ remote service. Nếu chỉ nhìn hot methods rồi tối ưu serializer, p99 có thể không cải thiện.

| Cần tìm | Dữ liệu nên xem |
| --- | --- |
| CPU đang chạy ở đâu | `jdk.ExecutionSample`, CPU metrics, hot-method profiling |
| Process/JVM gần hết CPU quota không | `jdk.CPULoad`, `jdk.ThreadCPULoad`, OS/container metrics |
| Có thời gian chờ I/O không | File/socket duration events, client spans, network telemetry |
| Có contention không | Monitor/park/blocking events, lock owner, thread states |
| Có GC ảnh hưởng request không | GC pause events, response latency, thread evidence |
| Một request có bao nhiêu lần retry | Application metrics/tracing/structured logs |
| Một nghiệp vụ xảy ra bao nhiêu lần | Counter hoặc instrumentation có coverage được kiểm chứng |

`RecordedEvent.getDuration()` đo **khoảng thời gian event**, không tự đo CPU time. Trong span dùng `Thread.sleep(30)`, duration vẫn có thể là 30 ms dù thread hầu như không chạy CPU.

## 5. Các thiên lệch quan sát làm sai kết luận

### 5.1. Selection bias do cấu hình

Template `default` và `profile` có event settings khác nhau. Chênh lệch số mẫu có thể đến từ cấu hình `enabled`, `period`, `threshold`, độ sâu stack, thời gian recording hoặc JVM version, chứ không phải workload.

Nếu recording A có 1.000 samples trong 10 phút, B có 500 samples trong 2 phút, **không** thể nói A dùng CPU gấp đôi B. Phải chuẩn hóa thời gian, sampling và xét absolute CPU.

### 5.2. Threshold tạo một phân phối bị cắt

Khi chỉ thu duration events ≥20 ms:
- Các event ngắn hơn vắng mặt.
- Median và mean tính trên file **không đại diện** cho mọi lần thao tác.
- Count cũng không là tổng số lần gọi.
- Nếu A dùng threshold 1 ms, B dùng threshold 20 ms, so trực tiếp mean/median là sai.

Cần giữ cùng threshold hoặc dùng nguồn metrics đầy đủ để đo phân phối thực.

### 5.3. Window bias và warm-up

Startup, JIT, class loading, cache cold, deployment, background jobs và burst traffic có thể làm dữ liệu khác steady state. Một file 30 giây sau deployment không đại diện cho cả ngày.

Nên lặp ở các pha tải tương đương, ghi rõ traffic mix, input size, cache state và cluster conditions.

### 5.4. Mất sự kiện hoặc lịch sử

Event có thể bị disabled, không đạt threshold, không được sampling, không còn trong data retention, hoặc không nằm ở file dump đã chọn. Nếu incident xảy ra trước khi khoảng ghi bắt đầu thì không thể dùng file phủ nhận incident đó.

### 5.5. Stack trace thiếu không có nghĩa thread không có stack

`RecordedEvent.getStackTrace()` trả `null` khi không có stack trace được ghi. `@StackTrace(false)` hoặc `EventSettings.withoutStackTrace()` có thể tạo hành vi đó một cách có chủ đích. Ngoài ra stack depth, JIT/inlining, native frames và async boundaries có thể ảnh hưởng nhận diện caller.

Một flame graph từ những stack rời rạc **không phải log đầy đủ từng invocation**.

### 5.6. Observer effect

Nếu tự bật rất nhiều events, threshold rất thấp, capture stack nặng hoặc dump liên tục, công cụ đo có thể tác động CPU, GC, I/O và latency đang điều tra. Vì vậy không mặc định cứ bật nhiều JFR là bằng chứng tốt hơn.

Cần một ngân sách overhead và thử nghiệm trên workload phù hợp. Dùng `profile` ngắn hạn khi cần điều tra, thay vì bật toàn bộ chi tiết vô hạn.

## 6. Đọc RecordedEvent đúng hợp đồng Java 11

`jdk.jfr.consumer.RecordedEvent` cung cấp:

| Phương thức | Kiểu trả về | Cách hiểu |
| --- | --- | --- |
| `getEventType().getName()` | `String` | Tên loại event, cần kiểm tra trước khi đọc custom fields. |
| `getStartTime()` | `Instant` | Thời điểm bắt đầu sự kiện. |
| `getEndTime()` | `Instant` | Thời điểm kết thúc; instant event có start/end như nhau. |
| `getDuration()` | `Duration` | Khoảng thời gian event, không mặc nhiên CPU time. |
| `getThread()` | `RecordedThread` hoặc null | Thread metadata nếu được thu. |
| `getStackTrace()` | `RecordedStackTrace` hoặc null | Có thể không có stack theo event/settings. |
| `getFields()` | `List<ValueDescriptor>` | Schema của event type. |
| `getString("field")`, `getInt("field")` | Giá trị typed | Chỉ dùng khi field tồn tại và đúng kiểu. |

Ví dụ **mảnh mã trong một phương thức**, cần imports và `Path path` đã xác định:

```java
try (RecordingFile input = new RecordingFile(path)) {
    while (input.hasMoreEvents()) {
        RecordedEvent e = input.readEvent();
        String eventType = e.getEventType().getName();
        Instant start = e.getStartTime();
        Duration duration = e.getDuration();

        // Chỉ truy cập trường riêng sau khi kiểm tra eventType/schema.
        // Không suy ra root cause chỉ từ start/duration.
    }
}
```

`RecordingFile.readAllEvents(path)` có thể thuận tiện với file nhỏ nhưng nạp danh sách toàn bộ events vào memory. Với file lớn, dùng `hasMoreEvents()/readEvent()` để kiểm soát dung lượng bộ nhớ. Tài liệu Java 11 khuyến nghị chỉ đọc `.jfr` từ **nguồn tin cậy**.

### 6.1. Bẫy timestamp

Một duration event có thể bắt đầu ở T1, kết thúc ở T3 và được commit sau T3. Một instant event B bắt đầu tại T2. Nếu sắp xếp theo thời điểm kết thúc/commit, thứ tự khác so với start time. Vì thế cần nói rõ timestamp nào được sử dụng.

Trên nhiều thread, thứ tự `Instant` không tự tạo **happens-before**. Trên nhiều host, còn có clock skew/clock correction. Muốn khôi phục quan hệ giữa request/queue tasks phải dùng thêm message send/receive hoặc trace/span semantics và đồng bộ.

### 6.2. Mẫu không có stdout cố định

Ví dụ đếm CPU samples:

```java
long executionSamples = 0;
try (RecordingFile input = new RecordingFile(path)) {
    while (input.hasMoreEvents()) {
        RecordedEvent e = input.readEvent();
        if ("jdk.ExecutionSample".equals(e.getEventType().getName())) {
            executionSamples++;
        }
    }
}
System.out.println("Observed samples: " + executionSamples);
```

Đây là **mảnh mã minh họa**. Không thể cho stdout cố định vì giá trị phụ thuộc JDK, thời lượng, workload, CPU sampling period và profile. Nó **không phải requests/s**.

Nếu cần đếm samples theo method, phải xác định rõ cách gán leaf/inclusive stack frames, số samples thiếu stack và bộ lọc; công bố mẫu số phù hợp.

## 7. Thứ tự thời gian và bằng chứng nhân quả

### 7.1. Cấp độ bằng chứng

| Cấp | Dữ liệu | Kết luận có thể biện minh |
| --- | --- | --- |
| 1. Đồng xuất hiện | A CPU hotspot và B p99 spike cùng khoảng ghi | Có liên hệ về mặt thời gian, chưa rõ cơ chế. |
| 2. Thứ tự quan sát | A trước B trong cùng timeline có scope rõ | A được ghi nhận trước B; chưa đủ cho causal link. |
| 3. Tương quan nhiều lần | A tăng, B thường tăng trong các cửa sổ so sánh | A là giả thuyết cần kiểm tra confounders. |
| 4. Cơ chế | Trace/code cho thấy A giữ lock R, B chờ R | Có cơ chế giải thích, cần kiểm tra dữ liệu và nguồn khác. |
| 5. Can thiệp có kiểm soát | Thay đổi riêng A, giữ load tương đương, B thay đổi | Bằng chứng nhân quả mạnh hơn. |
| 6. Đối chứng và tái lập | Lặp, rollback A/B/A, kết quả ổn định | Mức tin cậy tăng trong phạm vi thử nghiệm. |

Trong JFR không có một lời gọi `RecordedEvent.getCause()` chung xác định root cause từ một event.

### 7.2. Ví dụ confounder

```text
              Traffic spike C
                /        \
               v          v
        CPU hotspot A    Timeout B
```

Traffic tăng có thể làm A xuất hiện nhiều trong CPU samples **và** làm B timeout, dù A không phải nguyên nhân trực tiếp gây B. Cần phân biệt yếu tố chung C với quan hệ A → B.

Những confounders thường gặp: JVM warm-up, cache miss, input size, retry rate, remote service latency, CPU quota, GC, disk saturation và background jobs.

### 7.3. Happens-before là khái niệm khác thứ tự timestamp

**Java Memory Model** xác định happens-before bằng program order, lock/unlock, volatile, thread start/join và các quy tắc đồng bộ. Hai timestamps từ hai threads không tự chứng minh quan hệ này.

Một pipeline nhiều executor cần thêm evidence như enqueue/dequeue, message ID, span parent, code thực thi và dữ liệu đồng bộ. Nếu không, việc ghép các event theo thời điểm có thể tạo **câu chuyện nhân quả không tồn tại**.

### 7.4. Correlation ID cũng không tự chứng minh causal chain

Các events có cùng `correlationGroup` có thể thuộc một batch hoặc cùng request, nhưng có thể được gắn nhầm, tái sử dụng hoặc thiếu step. Shared key chỉ là một mối liên hệ **do ứng dụng tuyên bố**. Muốn chứng minh bước B bắt nguồn từ A cần semantic của link, việc truyền key/parent span và kiểm chứng đường đi thực tế.

Đừng đưa raw user ID, email, token hay request body vào custom JFR event để dễ correlation. Dùng key synthetic/ephemeral có scope, quyền truy cập và TTL phù hợp.

## 8. Phân tích mẫu CPU và biểu đồ profiler

- **Hot method:** phương thức thường xuất hiện ở leaf hoặc tại vị trí được tính trong tập stack samples. Cần biết công cụ tính **self/leaf** hay **inclusive**.
- **Call tree:** tổng hợp các đường stack được quan sát; không phải call trace của tất cả invocations.
- **Flame graph:** chiều rộng dựa trên samples/trọng số theo cách công cụ xây dựng; không tự biểu diễn duration của từng lần gọi.
- **Blocked time:** có thể vắng mặt trong CPU method sampling; xem I/O, lock, park events và tracing.
- **Tỷ lệ samples:** phải luôn có mẫu số rõ, không chuyển thành phần trăm requests.

Báo cáo đúng:

> Trong 1.200 CPU samples hợp lệ của cửa sổ 10 phút, `Parser.parse` xuất hiện ở 480 leaf samples (40%). Cần đối chiếu CPU metrics, workload và p99 trước khi kết luận nguyên nhân.

Báo cáo sai:

> 40% request bị chậm do Parser.

Đây là ví dụ số liệu **minh họa**, không đại diện cho ứng dụng cụ thể.

## 9. Quy trình điều tra gắn bằng chứng với giả thuyết

### Bước 1 — Đặt câu hỏi có thể kiểm tra

Ví dụ: “Sau release, p99 request tăng từ 200 lên 350 ms khi traffic tương đương; có phải CPU serialization tăng hay downstream wait tăng?”

### Bước 2 — Kiểm tra coverage

Ghi JDK/JVM version, JFR `default/profile`, event names, `enabled`, `period`, `threshold`, stackTrace settings, start/end recording, giới hạn retention, tổng samples và filter.

### Bước 3 — Tách dạng triệu chứng

- CPU hotspot → `jdk.ExecutionSample`, CPU/Thread CPU metrics.
- GC pause → GC events, latency timeline.
- Lock contention → Java monitor/park events.
- I/O wait → socket/file events, client/request spans.
- Business outcome/retry → custom instrumentation và structured logs.

### Bước 4 — Dựng timeline có scope

```text
T0: request received
T1: outbound call starts
T2: GC pause observed
T3: outbound call finishes
T4: serializer runs
T5: response emitted
```

Timeline chỉ cho thứ tự và khoảng trùng, không chứng minh GC làm toàn bộ request chậm. Hãy xem từng duration và thread/request scope.

### Bước 5 — Đối chiếu nguồn độc lập

So JFR với p95/p99/throughput, CPU quota, lock contention, GC time, downstream p99, retry rate và tracing. Nếu mâu thuẫn, kiểm tra sampling window, missing data, clock skew và workload trước khi chọn kết luận.

### Bước 6 — Thử nghiệm nhỏ có đối chứng

Giữ traffic mix, CPU quota, JDK, data size, cache và downstream tương đương; thay một yếu tố, đo nhiều lần, có rollback nếu cần. Quan sát p99/CPU/throughput có dịch chuyển theo dự đoán không.

### Bước 7 — Báo cáo ba lớp

1. **Quan sát:** số event/samples, timestamps, durations và phạm vi.
2. **Giả thuyết:** nguyên nhân có thể, mức tin cậy và confounders.
3. **Kiểm chứng:** thí nghiệm/metrics/tracing hỗ trợ hoặc phủ định, các hạn chế còn lại.

Không viết “JFR chứng minh A gây B” khi chỉ có một flame graph hoặc timeline.

## 10. Ví dụ Java 11 hoàn chỉnh: ghi, đọc và giới hạn suy luận

Chương trình tạo một recording JFR thật, ba duration events theo thứ tự `load`, `validate`, `respond` và một instant event `OutcomeSignal`.

Các event mang cùng một **synthetic correlation key**, không chứa dữ liệu khách hàng. Chương trình đọc lại file, kiểm tra:
- Số event custom đúng như code tạo.
- Giá trị field, thời gian duration dương.
- Cùng nhóm correlation.
- Stack trace của event custom đã tắt.
- Thứ tự start timestamp trong một thread.
- **Không suy luận nhân quả chỉ từ thời gian.**

Vì dùng cấu hình `default`, file có thể có nhiều JVM events khác; phép kiểm tra **chỉ lọc hai event types của demo**. Không coi số event của demo là số CPU samples hoặc bảo đảm mọi sự kiện JVM đã được ghi.

### 10.1. JfrEvidenceDemo.java

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrEvidenceDemo {
    @Name("lesson.OperationStep")
    @Label("Bounded operation step")
    @Category({"Application", "Diagnostics"})
    @StackTrace(false)
    public static class OperationStep extends Event {
        public String correlationGroup;
        public String phase;
        public String status;
        public int units;
    }

    @Name("lesson.OutcomeSignal")
    @Label("Outcome signal")
    @Category({"Application", "Diagnostics"})
    @StackTrace(false)
    public static class OutcomeSignal extends Event {
        public String correlationGroup;
        public String result;
    }

    private static void step(String phase, int units)
            throws InterruptedException {
        OperationStep event = new OperationStep();
        event.begin();
        Thread.sleep(12);
        event.end();
        if (event.shouldCommit()) {
            event.correlationGroup = "synthetic-demo";
            event.phase = phase;
            event.status = "OK";
            event.units = units;
            event.commit();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected new temporary .jfr path");
        }
        Path dump = Path.of(args[0]);

        try (Recording r =
                new Recording(Configuration.getConfiguration("default"))) {
            r.setName("causal-evidence-demo");
            r.setToDisk(true);
            r.setMaxSize(32L * 1024 * 1024);
            r.setMaxAge(Duration.ofMinutes(5));
            r.setDumpOnExit(false);
            r.enable(OperationStep.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            r.enable(OutcomeSignal.class).withoutStackTrace();

            r.start();
            step("load", 6);
            step("validate", 6);
            step("respond", 6);

            OutcomeSignal signal = new OutcomeSignal();
            signal.correlationGroup = "synthetic-demo";
            signal.result = "OK";
            signal.commit();

            r.stop();
            r.dump(dump);
        }

        Map<String, Instant> phases = new HashMap<>();
        int steps = 0, signals = 0;
        boolean sameGroup = true;
        boolean durationsPositive = true;
        boolean stacksAbsent = true;

        try (RecordingFile input = new RecordingFile(dump)) {
            while (input.hasMoreEvents()) {
                RecordedEvent e = input.readEvent();
                String type = e.getEventType().getName();

                if ("lesson.OperationStep".equals(type)) {
                    steps++;
                    sameGroup &= "synthetic-demo".equals(
                            e.getString("correlationGroup"));
                    durationsPositive &= e.getDuration().toNanos() > 0;
                    stacksAbsent &= e.getStackTrace() == null;

                    if (!"OK".equals(e.getString("status"))
                            || e.getInt("units") != 6) {
                        throw new AssertionError("Unexpected phase payload");
                    }
                    phases.put(e.getString("phase"), e.getStartTime());

                } else if ("lesson.OutcomeSignal".equals(type)) {
                    signals++;
                    sameGroup &= "synthetic-demo".equals(
                            e.getString("correlationGroup"));
                    stacksAbsent &= e.getStackTrace() == null;

                    if (!"OK".equals(e.getString("result"))) {
                        throw new AssertionError("Unexpected signal payload");
                    }
                }
            }
        }

        boolean ordered = phases.size() == 3
                && phases.get("load").isBefore(phases.get("validate"))
                && phases.get("validate").isBefore(phases.get("respond"));

        System.out.println("operationSteps=" + steps);
        System.out.println("outcomeSignals=" + signals);
        System.out.println("correlationGroupMatches=" + sameGroup);
        System.out.println("positiveDurations=" + durationsPositive);
        System.out.println("customStacksDisabled=" + stacksAbsent);
        System.out.println("startTimesOrdered=" + ordered);
        System.out.println("causality=" + "notProvenByTimingAlone");
        System.out.println("fileCreated=" + (Files.size(dump) > 0));

        Files.delete(dump);
        System.out.println("demoFileDeleted=" + !Files.exists(dump));

        if (steps != 3 || signals != 1 || !sameGroup
                || !durationsPositive || !stacksAbsent || !ordered) {
            throw new AssertionError("Demo verification failed");
        }
    }
}
```

### 10.2. Lệnh chạy và output đã kiểm chứng

Chạy trong **thư mục test riêng** với đường dẫn file `evidence-demo.jfr` mới; chương trình sẽ xóa file đích sau khi kiểm tra, vì vậy **không dùng đường dẫn tệp quan trọng đang tồn tại**:

```bash
javac -encoding UTF-8 --release 11 JfrEvidenceDemo.java
java JfrEvidenceDemo evidence-demo.jfr
```

**Stdout thực tế trên JDK 24, với compiler target Java 11:**

```text
operationSteps=3
outcomeSignals=1
correlationGroupMatches=true
positiveDurations=true
customStacksDisabled=true
startTimesOrdered=true
causality=notProvenByTimingAlone
fileCreated=true
demoFileDeleted=true
```

### 10.3. Ý nghĩa của kết quả

- `operationSteps=3`: có ba custom duration events đã được ghi/đọc, không là tổng số lời gọi Java của tiến trình.
- `outcomeSignals=1`: có một custom instant event.
- `correlationGroupMatches=true`: cùng key synthetic; **không phải chứng minh causal chain**.
- `positiveDurations=true`: ba khoảng elapsed dương; `Thread.sleep(12)` giải thích phần lớn duration, không đồng nghĩa CPU time.
- `customStacksDisabled=true`: custom events không có stack theo thiết kế, không phải thread không có call stack.
- `startTimesOrdered=true`: cùng một thread thực hiện ba bước tuần tự trong bài thử, start timestamp phản ánh thứ tự.
- `causality=notProvenByTimingAlone`: kết luận phương pháp luận, không là một phép tính root cause.
- `fileCreated=true` và `demoFileDeleted=true`: file được dump, rồi xóa bằng `Files.delete`. Xóa logic không chứng minh secure erase hoặc xóa mọi backup.

**Giới hạn của ví dụ:** không đo CPU method samples, không kiểm chứng retention đã chạm, không instrument async cross-service, không chứng minh completeness của mọi JFR event hoặc root cause của ứng dụng thật.

## 11. So sánh nhiều bản ghi JFR đúng cách

| Điều kiện | Phải giữ tương đương hoặc giải thích khác biệt |
| --- | --- |
| JDK/JVM version | Class/event definitions, stack/JIT behavior |
| Template và setting | `default/profile`, enabled, period, threshold, stackTrace |
| Recording duration | Cửa sổ 2 phút không so raw samples với 20 phút |
| Workload | RPS, input size, endpoint mix, cache state |
| Hạ tầng | CPU quota, cores, memory, OS contention |
| Context | Startup/steady state/incident, dependency health |
| Bộ lọc | Cùng sample types, thread subset, missing-stack policy |
| Data completeness | Retention, dropped/filtered events, timestamp scope |
| Denominator | N samples gốc, N samples hợp lệ sau filter |

Một bảng **giả định**:

| Metric | Baseline | Sau thay đổi |
| --- | ---: | ---: |
| CPU samples hợp lệ | 1.000 | 2.000 |
| Leaf sample share của `Parser.parse` | 30% | 55% |
| p99 request latency | 200 ms | 350 ms |
| Throughput | 800 rps | 1.200 rps |
| Remote service p99 | 70 ms | 180 ms |

Không thể từ đó khẳng định “Parser gây ra toàn bộ p99 tăng”. Workload và downstream cũng khác, là những confounders lớn. Cần đánh giá khi traffic và remote behavior tương đương.

Tỷ lệ 40% CPU samples khi process chỉ dùng 10% CPU quota cũng khác với 40% samples khi process gần 100% quota; để hiểu **độ lớn tuyệt đối**, phải kết hợp CPU metrics.

## 12. Lựa chọn công cụ theo câu hỏi

| Công cụ | Mạnh ở | Hạn chế |
| --- | --- | --- |
| JFR CPU samples | Tìm vùng code dùng CPU | Không đếm mọi calls hoặc chứng minh nguyên nhân |
| JFR duration/GC/lock/I/O events | Phân tích một số hiện tượng JVM | Filter, threshold và co-occurrence bias |
| Metrics | Theo dõi throughput, p99, CPU, errors | Không mô tả đầy đủ từng stack/request |
| Structured logging | Request outcome, retry, error category | Có thể mất dữ liệu và chứa thông tin nhạy cảm |
| Distributed tracing | Request path và parent-child spans | Sampling/propagation errors, thiếu spans |
| Thí nghiệm có đối chứng | Kiểm tra cơ chế nghi ngờ | Cần thiết kế tốt và kiểm soát confounders |

Một chuỗi đáng tin:

```text
JFR indicates a hotspot
     |
Metrics confirm CPU saturation / p99 change
     |
Trace indicates affected request path
     |
Mechanism in code is identified
     |
Controlled change + repeat + rollback
     |
Scoped conclusion with uncertainty
```

Không đưa ra kết luận vượt quá chứng cứ.

## 13. Đọc file bằng CLI và bảo vệ dữ liệu

JDK 11 cung cấp công cụ `jfr`. Với file đã được cấp quyền:

```bash
jfr summary recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
jfr print --events jdk.CPULoad recording.jfr
```

Nếu event không được bật hoặc không được ghi thì output lọc có thể rỗng. Không suy ra CPU bằng 0. Có thể dùng `RecordingFile.readEventTypes()` để xem event types có trong file và kiểm tra schema trước khi truy cập custom fields.

Các quy tắc an toàn:
- Chỉ parse recording từ nguồn tin cậy.
- Với file lớn, đọc theo luồng thay vì `readAllEvents()`.
- Không in hoặc chia sẻ thô stack/path/hostname, request body, token, session ID hay dữ liệu người dùng.
- Không dùng customer ID/email trong correlation key nếu không cần.
- Đặt ACL, encryption, TTL, ownership và kiểm toán truy cập cho file `.jfr`.
- Báo time window, filter và số samples trước khi diễn giải kết quả.

## 14. Những lỗi suy luận phổ biến

| Kết luận sai | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| A có 8/10 samples nên dùng chính xác 80% CPU. | N quá nhỏ; sample share không bằng absolute CPU. | Ghi N và metric CPU độc lập. |
| Không có `ExecutionSample` nghĩa CPU=0. | Disabled/không lấy mẫu/recording thiếu. | Xem event config và CPU metrics. |
| Không có `SocketRead` nghĩa không có network. | Threshold/loại event/coverage. | Xem instrumentation và tracing. |
| Duration 100ms nghĩa CPU 100ms. | Có blocked/sleep/I/O. | Phân biệt elapsed và CPU. |
| Stack chứa A chứng minh A gây lỗi B. | Stack là snapshot. | Kiểm tra cơ chế và logs/traces. |
| A xảy ra trước B nên A gây B. | Post hoc fallacy. | Tìm confounders, đối chứng. |
| Cùng correlation ID là cùng causal chain. | Key có thể chỉ là nhóm. | Định nghĩa semantic parent-child. |
| 50% samples là 50% requests. | Denominator khác. | Đếm requests bằng metric/counter. |
| Hàm không trong samples nghĩa không chạy. | Sampling bỏ qua hàm rất ngắn. | Dùng instrumentation khác. |
| Flame graph là call trace đầy đủ. | Chỉ tổng hợp stack mẫu. | Không gán per-invocation duration. |
| `default` và `profile` có thể so raw count. | Sampling settings khác. | Chuẩn hóa hoặc nêu khác biệt. |
| Nhiều samples hơn là hiệu năng giảm. | Duration/workload/period khác. | So p99, throughput, CPU. |
| Một lần A/B thành công là chứng minh chắc chắn. | Nhiễu và confounding. | Lặp, rollback, đo đủ. |
| Timestamp hai host chứng minh thứ tự tuyệt đối. | Clock skew và lack of propagation. | Dùng trace/correlation đúng. |
| Đọc được JFR nghĩa mọi event đều đủ và an toàn. | Có thể thiếu event và nhạy cảm. | Kiểm toán schema, nguồn, time window. |

## 15. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** 5/10 CPU samples ở method A có nghĩa A dùng 50% CPU của JVM?

**Đáp án:** Không. Đó chỉ là 50% mẫu đang xét; số mẫu ít, chưa đo CPU time tuyệt đối.

**Câu 2.** `jdk.FileWrite` có threshold 20 ms; mean duration đọc từ file là mean của mọi file writes?

**Đáp án:** Không. Những event ngắn hơn threshold bị loại, gây thiên lệch.

**Câu 3.** Request chờ network 100 ms có nhất thiết xuất hiện nhiều ở CPU samples?

**Đáp án:** Không. CPU sampling không phản ánh đầy đủ blocked I/O.

**Câu 4.** `getDuration()` có thể tăng khi `Thread.sleep` không?

**Đáp án:** Có, nếu sleep nằm trong span được instrument; đây là elapsed duration.

**Câu 5.** `getStackTrace()==null` chứng minh thread không có call stack?

**Đáp án:** Không. Có thể tắt stack recording theo settings.

**Câu 6.** Event A bắt đầu trước B. Có đủ nói A gây B?

**Đáp án:** Không. Cần cơ chế và kiểm chứng confounders.

**Câu 7.** Hai events có cùng key có chứng minh happens-before?

**Đáp án:** Không. Happens-before phải dựa trên program order/synchronization theo Java Memory Model.

**Câu 8.** Có thể dùng số `jdk.ExecutionSample` làm requests/s không?

**Đáp án:** Không. Một request có thể có 0 hoặc nhiều CPU samples.

**Câu 9.** Hai bản ghi khác template `default/profile` nên so raw samples ra sao?

**Đáp án:** Phải đối chiếu event settings, duration, workload; không so trực tiếp số thô.

**Câu 10.** Vì sao phải nêu denominator và N samples?

**Đáp án:** Để biết phần trăm thuộc quần thể nào và mức độ thiếu chắc chắn.

**Câu 11.** Dữ liệu cũ bị retention loại, không có event về sự cố. Có thể nói sự cố không xảy ra?

**Đáp án:** Không. Recording không bao phủ khoảng dữ liệu đã bị loại.

**Câu 12.** Trong demo, duration dương có chứng minh CPU cao không?

**Đáp án:** Không. Demo ngủ 12ms trong mỗi span, nên duration chủ yếu do chờ.

**Câu 13.** `startTimesOrdered=true` cùng group key có phải bằng chứng nhân quả?

**Đáp án:** Không. Chúng chỉ xác nhận thứ tự quan sát và một nhóm dữ liệu synthetic.

**Câu 14.** Cần thêm gì để kiểm chứng giả thuyết GC pause gây p99 tăng?

**Đáp án:** GC/p99 timeline, affected threads, CPU/remote metrics, tracing và thí nghiệm có đối chứng.

**Câu 15.** Bật mọi event/stack trace có tăng chất lượng bằng chứng vô hạn không?

**Đáp án:** Không. Có thể tăng overhead, data loss/privacy và làm biến dạng workload.

**Câu 16.** Nếu JFR không có CPU sample, bước đầu tốt nhất là gì?

**Đáp án:** Kiểm tra `enabled/period`, recording window, JDK template và CPU metrics độc lập.

**Câu 17.** Có nên kết luận từ một flame graph mà không xem throughput và load không?

**Đáp án:** Không. Cần cân nhắc confounding do workload và quota.

**Câu 18.** Một thí nghiệm can thiệp đáng tin nên kiểm soát gì?

**Đáp án:** Traffic mix, input, cache, JDK, CPU quota, remote dependencies, thời lượng đo, lặp nhiều lần và rollback khi cần.

## 16. Kết luận và tài liệu chuẩn

- JFR là công cụ quan sát có chọn lọc, không phải lịch sử thực thi đầy đủ.
- **Sampling đưa ra hotspot candidates**, không tự chứng minh mọi lần gọi hay CPU milliseconds thực.
- **Duration event** có thể đo thời gian chờ, không chỉ CPU.
- Template, threshold, sampling period, stack settings và retention ảnh hưởng dữ liệu được nhìn thấy.
- `RecordingFile`/`RecordedEvent` trong Java 11 vẫn áp dụng và cần được diễn giải đúng.
- Tương quan, timestamps, cùng correlation key chưa phải bằng chứng causal chain.
- Có kết luận nguyên nhân đáng tin hơn khi kết hợp JFR, metrics, tracing, code mechanism, thí nghiệm đối chứng và tái lập.
- Ví dụ Java đã kiểm thử chứng minh những sự kiện và metadata được ghi/đọc, đồng thời minh bạch rằng **thời gian không tự chứng minh nguyên nhân**.

**Tài liệu chính thức:**
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Oracle Java SE 11 — RecordedStackTrace](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html).
- [Oracle Java SE 11 — RecordedThread](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html).
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- [Oracle Java SE 11 — Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
- [Oracle Java SE 11 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
- [Oracle Java SE 11 — jfr command](https://docs.oracle.com/en/java/javase/11/tools/jfr.html).
- [OpenJDK — JEP 328 Flight Recorder](https://openjdk.org/jeps/328).