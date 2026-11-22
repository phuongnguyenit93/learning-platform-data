# isEnabled, shouldCommit và tránh tính dữ liệu không cần (JFR API — Java 11)

**Java Flight Recorder (JFR)** là cơ chế thu thập sự kiện vận hành, hiệu năng và dữ liệu chẩn đoán ngay trong JVM. Từ Java 11, API JFR công khai thuộc module **`jdk.jfr`** cho phép ứng dụng tự định nghĩa event, đo duration, ghi field và đọc lại file `.jfr`. JFR được thiết kế có overhead thấp, nhưng **đoạn mã ứng dụng tự tạo dữ liệu cho event vẫn có thể rất tốn kém**: serialize DTO lớn, định dạng JSON, dựng stack trace, đọc thông tin bổ sung, chuyển bytes sang hex hoặc tính chuỗi debug ở đường nóng.

Hai guard quan trọng:

- **`event.isEnabled()`**: loại event này có **đang được bật ở ít nhất một recording chạy trong JVM** không? Dùng ở đầu instrumentation để tránh làm các việc chỉ phục vụ JFR khi event bị tắt.
- **`event.shouldCommit()`**: instance này **có đủ điều kiện được ghi ở thời điểm kiểm tra** không? Với duration event, kết quả còn phụ thuộc **threshold**. Gọi sau `end()`, trước khi tạo field chẩn đoán đắt tiền.

**Thứ tự hữu ích nhất cho một duration event:**

```text
Tạo một instance event
         |
     isEnabled() ?
      |         |
    false      true
      |         |
      |       begin()
      |         |
      +---- chạy công việc nghiệp vụ bình thường
                |
              end()
                |
          shouldCommit() ?
             |       |
            false   true
             |       |
          bỏ qua   tính chi tiết chẩn đoán
                    gán event fields
                    commit()
```

**Không dùng hai guard này để quyết định có chạy nghiệp vụ hay không.** Chúng chỉ kiểm soát chi phí **instrumentation**; xác thực quyền, ghi transaction, thực hiện request hoặc tính kết quả nghiệp vụ phải giữ nguyên.

Bài học thuộc nhóm **JFR API** của Java 11, chỉ sử dụng những API vẫn có trên các JDK hiện đại. Các chương trình đầy đủ được kiểm tra bằng **`javac --release 11`**; không dựa vào API Flight Recorder cũ hoặc package nội bộ không được hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt enabled state, duration threshold và actual recording output.
2. Hiểu chính xác `Event.isEnabled()`, `Event.shouldCommit()`, `begin()`, `end()`, `commit()`.
3. Chọn vị trí kiểm tra guard để tránh tính dữ liệu chẩn đoán khi recording tắt hoặc event bị lọc.
4. Đo duration chỉ của nghiệp vụ, không để chi phí formatting/serialization làm kết quả đo bị phình.
5. Cấu hình `Recording.enable(Class).withThreshold(Duration)`, `withoutThreshold()`, `withoutStackTrace()`.
6. Biết xử lý `try/finally` cho success và failure, không nuốt lỗi nghiệp vụ.
7. Đọc file `.jfr` qua `RecordingFile`, lọc custom event và kiểm tra fields.
8. Hiểu ngưỡng tối thiểu khi **nhiều recording đồng thời** trong cùng JVM; không nhầm `shouldCommit` thành bộ lọc riêng của một file.
9. Tránh tạo payload lớn, lộ thông tin nhạy cảm và những chi phí đo đạc không cần thiết.
10. Chạy ba ví dụ Java 11, biết đối chiếu stdout và giới hạn tính ổn định của thử nghiệm duration.

## 2. Hiểu đúng hai phương thức

| Tình huống | `isEnabled()` | `shouldCommit()` (sau `end()`) | Quyết định |
| --- | --- | --- | --- |
| Không có recording nào chạy | `false` | `false` | Không tạo metadata cho JFR |
| Recording chạy nhưng loại event bị disable | `false` nếu không có recording khác bật | `false` | Không tạo metadata |
| Loại event bật, duration **nhỏ hơn threshold** | **`true`** | **`false`** | Đã đo duration, không làm enrichment |
| Loại event bật, duration **đạt threshold** | **`true`** | **`true`** | Có thể gán field và commit |
| Loại event bật, threshold `0` | `true` | Thường `true` với event hợp lệ | Event ngắn cũng được xét ghi |
| Recording start/stop hoặc đổi settings lúc công việc chạy | Có thể đổi giữa các thời điểm | Có thể đổi | Không được coi một guard là kết quả bất biến |
| Nhiều recording bật cùng event với threshold khác nhau | `true` | Dùng **threshold nhỏ nhất** trong các recording đang chạy | Không suy ra từng file chắc chắn có/không event |

### `isEnabled()` kiểm tra điều gì?

Javadoc Java SE 11: `isEnabled()` trả `true` nếu **ít nhất một recording đang chạy** và setting `enabled` của event là `true`; ngược lại `false`. Nó **không kiểm tra duration threshold**.

Do đó, ghi:

```java
if (event.isEnabled()) {
    event.details = expensiveSerialize(request);
}
```

là chưa tối ưu nếu event có ngưỡng duration và phần lớn request nhanh. Bạn vẫn serialize dữ liệu cho các event sẽ không được giữ.

### `shouldCommit()` kiểm tra điều gì?

Javadoc Java SE 11: `shouldCommit()` xét enabled setting và **duration đủ threshold**, trong đó threshold được lấy là **minimum threshold giữa các recording đang chạy**. Đây là lời gợi ý chính thức để bỏ các thao tác thu thập dữ liệu đắt tiền nếu event không thể ghi.

Không được hiểu `shouldCommit() == true` là xác nhận file `.jfr` đã có event. Có thể có thay đổi setting, giới hạn retention, recording lifecycle hoặc nhiều recording cùng chia sẻ việc thu thập.

### Vì sao cần cả hai?

- `isEnabled()` có thể được gọi **trước nghiệp vụ**, giúp bỏ hẳn một số công tác instrument khi JFR tắt.
- `shouldCommit()` có ý nghĩa hơn **sau khi có duration hoàn chỉnh**, tránh làm detail cho event ngắn hơn threshold.
- Nếu dùng chỉ `isEnabled`: bỏ qua được trường hợp tắt event, nhưng vẫn tốn chi phí cho event bị lọc bởi threshold.
- Nếu dùng chỉ `shouldCommit` ở đầu: duration chưa phản ánh công việc, việc quyết định có thể sai mục đích.

## 3. Vòng đời của một JFR duration event

Custom event đơn giản:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.Operation")
@Label("Operation")
class OperationEvent extends Event {
    @Label("Operation ID")
    String operationId;
}
```

Đây là **class snippet**, chưa có `main`.

Các phương thức chính:

| API Java 11 | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `begin()` | Bắt đầu đo thời gian | Gọi trước operation |
| `end()` | Kết thúc đo thời gian | Gọi sau `begin()`; nên dùng `finally` |
| `isEnabled()` | Kiểm tra có recording enable event hay không | Không xét ngưỡng thời gian |
| `shouldCommit()` | Kiểm tra event có đủ điều kiện để ghi | Tốt nhất sau `end()` |
| `commit()` | Ghi values, timestamp, duration vào JFR | Nếu đã `begin` nhưng chưa `end`, nó tự end |
| `set(int,Object)` | Gán field trong event được tạo động bằng `EventFactory` | Không phải setter thường dùng cho subclass |

### Tại sao explicit `end()` quan trọng?

Giả sử nghiệp vụ thực tế mất 3 ms, còn chuyển một object graph thành JSON chẩn đoán mất 50 ms. Nếu bạn gọi:

```java
event.begin();
doBusinessWork();
event.details = expensiveJson(); 
event.commit(); // Tự end nếu chưa end().
```

thì **thời gian tạo JSON cũng bị tính vào duration**. Một thao tác nhanh có thể bị đánh dấu chậm *chỉ vì instrumentation đắt tiền*.

Đúng hơn:

```java
event.begin();
try {
    doBusinessWork();
} finally {
    event.end();
}
if (event.shouldCommit()) {
    event.details = expensiveJson();
    event.commit();
}
```

Đây là hai **snippet**, với các hàm và event tự định nghĩa. Snippet thứ hai chỉ có đường commit khi business work hoàn thành bình thường; nếu cần ghi cả lỗi, xem ví dụ thứ ba bên dưới.

**Nguyên tắc đo:** đặt `end()` **trước enrichment**. Nếu `shouldCommit() == false`, không gọi formatter, không tạo payload và thường không cần `commit()`. Nếu đủ điều kiện, gán fields rồi `commit()`.

### Bảo vệ phần nghiệp vụ bằng `try/finally`

```java
WorkEvent event = new WorkEvent();
boolean enabled = event.isEnabled();
if (enabled) {
    event.begin();
}
try {
    runBusinessOperation(); // Luôn chạy dù JFR tắt.
} finally {
    if (enabled) {
        event.end();
    }
}
```

Đây là snippet với `WorkEvent`/`runBusinessOperation` đã được khai báo. Khi business code ném ngoại lệ, `finally` vẫn bảo đảm thời gian được kết thúc. Muốn ghi event lỗi, cần đặt phần `shouldCommit`/`commit` vào flow bao phủ cả đường exception.

## 4. Cấu hình event và threshold trong `Recording`

`jdk.jfr.Recording` của Java 11 cho phép bắt đầu, dừng và lưu recording:

```java
try (Recording recording = new Recording()) {
    recording.enable(WorkEvent.class)
            .withThreshold(Duration.ofMillis(100))
            .withoutStackTrace();
    recording.start();

    // Công việc ứng dụng được instrument ở đây.

    recording.stop();
    recording.dump(Path.of("work.jfr"));
}
```

Đây là snippet trong phương thức xử lý ngoại lệ, có imports `Recording`, `Duration`, `Path`; `WorkEvent` là custom event đã định nghĩa. Trong ứng dụng thật, tracing được bật hoặc cấu hình bởi bên vận hành/agent, không nhất thiết do business code tự tạo mỗi request.

| Setting | Ý nghĩa |
| --- | --- |
| `recording.enable(WorkEvent.class)` | Bật loại event cho recording |
| `recording.disable(WorkEvent.class)` | Tắt loại event trong recording này |
| `withThreshold(Duration.ofMillis(100))` | Đòi duration đạt khoảng 100 ms |
| `withoutThreshold()` | Bỏ duration threshold, tương đương ngưỡng 0 |
| `withoutStackTrace()` | Không thu stack trace cho loại event |
| `recording.start()` / `stop()` | Quản lý vòng đời thu |
| `recording.dump(Path)` | Ghi file `.jfr` để phân tích |
| `recording.close()` | Giải phóng tài nguyên recording |

`@Threshold("20 ms")` trên class event định nghĩa **threshold mặc định**, còn EventSettings có thể override. `@Enabled(false)` là mặc định tắt, nhưng vẫn có thể bật bằng recording configuration. **Không đọc annotation rồi suy luận event đang enabled**: hãy dùng `isEnabled()` tại runtime.

Ví dụ:

```java
@Name("demo.SlowQuery")
@Threshold("20 ms")
class SlowQueryEvent extends Event {
    String queryCategory;
}
```

Đây là class snippet, cần imports `Name`, `Threshold`, `Event`.

**Không coi ngưỡng 100 ms là chuẩn chung.** Nó chỉ phục vụ bài thực hành. Giá trị production phải dựa trên tần suất event, mục tiêu profiling, latency SLO, disk budget, overhead, stack trace nhu cầu và lượng dữ liệu nhạy cảm.

## 5. Ví dụ 1 — `isEnabled`/`shouldCommit` loại bỏ enrichment thừa

Chương trình độc lập **`JfrGuardDemo.java`** gồm ba tình huống: recording tắt; recording bật nhưng event nhanh; recording bật và event vượt ngưỡng 100 ms. Phép tạo `expensiveDetail` chỉ được gọi sau `shouldCommit`.

`Thread.sleep(250)` mô phỏng slow operation; không phải benchmark đo performance. Trên hệ thống chịu tải nặng, một công việc “fast” có thể bị treo bởi scheduler lâu bất thường; stdout bên dưới là kết quả đã kiểm chứng trên môi trường thử nghiệm thông thường, không phải bảo đảm mọi máy luôn có scheduler giống nhau.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrGuardDemo {
    @Name("demo.WorkEvent")
    @Label("Work event")
    @Category({"Demo", "Business"})
    static final class WorkEvent extends Event {
        @Label("Job ID")
        String jobId;
        @Label("Diagnostic detail")
        String detail;
    }

    private static final AtomicInteger DETAIL_BUILDS =
            new AtomicInteger();

    static final class Outcome {
        final boolean enabled;
        final boolean eligible;
        Outcome(boolean enabled, boolean eligible) {
            this.enabled = enabled;
            this.eligible = eligible;
        }
    }

    private static String expensiveDetail(String id) {
        DETAIL_BUILDS.incrementAndGet();
        return "diagnostic-for-" + id;
    }

    private static Outcome performWork(String jobId, long delayMs)
            throws InterruptedException {
        WorkEvent event = new WorkEvent();
        boolean enabled = event.isEnabled();
        if (enabled) {
            event.begin();
        }
        try {
            if (delayMs != 0) {
                Thread.sleep(delayMs);
            }
            // Business work must run even when JFR event is disabled.
        } finally {
            if (enabled) {
                event.end();
            }
        }

        boolean eligible = enabled && event.shouldCommit();
        if (eligible) {
            event.jobId = jobId;
            event.detail = expensiveDetail(jobId);
            event.commit();
        }
        return new Outcome(enabled, eligible);
    }

    public static void main(String[] args) throws Exception {
        Path recordingFile = Files.createTempFile("jfr-guard-", ".jfr");
        try {
            try (Recording disabled = new Recording()) {
                disabled.disable(WorkEvent.class);
                disabled.start();
                Outcome result = performWork("disabled", 0);
                System.out.println("Disabled isEnabled: " + result.enabled);
                System.out.println("Disabled shouldCommit: " + result.eligible);
                disabled.stop();
            }

            try (Recording recording = new Recording()) {
                recording.enable(WorkEvent.class)
                        .withThreshold(Duration.ofMillis(100))
                        .withoutStackTrace();
                recording.start();

                Outcome fast = performWork("fast", 0);
                Outcome slow = performWork("slow", 250);

                System.out.println("Fast isEnabled: " + fast.enabled);
                System.out.println("Fast shouldCommit: " + fast.eligible);
                System.out.println("Slow isEnabled: " + slow.enabled);
                System.out.println("Slow shouldCommit: " + slow.eligible);
                recording.stop();
                recording.dump(recordingFile);
            }

            List<RecordedEvent> appEvents =
                    RecordingFile.readAllEvents(recordingFile).stream()
                            .filter(e -> e.getEventType().getName()
                                    .equals("demo.WorkEvent"))
                            .collect(Collectors.toList());

            System.out.println("Expensive detail builds: " +
                    DETAIL_BUILDS.get());
            System.out.println("Recorded work events: " +
                    appEvents.size());
            System.out.println("Recorded job ID: " +
                    appEvents.get(0).getString("jobId"));
            System.out.println("Recorded detail: " +
                    appEvents.get(0).getString("detail"));
        } finally {
            Files.deleteIfExists(recordingFile);
        }
    }
}
```

Biên dịch và chạy trên một JDK hỗ trợ `jdk.jfr`:

```sh
javac --release 11 -encoding UTF-8 JfrGuardDemo.java
java JfrGuardDemo
```

**Stdout đã kiểm chứng:**

```text
Disabled isEnabled: false
Disabled shouldCommit: false
Fast isEnabled: true
Fast shouldCommit: false
Slow isEnabled: true
Slow shouldCommit: true
Expensive detail builds: 1
Recorded work events: 1
Recorded job ID: slow
Recorded detail: diagnostic-for-slow
```

### Giải thích

**Disabled:** recording duy nhất tắt event, `isEnabled()` là `false`. Business code vẫn chạy nhưng không tạo metadata JFR.

**Fast:** event được bật, nhưng duration chưa qua threshold, `shouldCommit()` là `false`. `expensiveDetail` **không** chạy. Đây chính là khác biệt giữa hai guard.

**Slow:** duration mô phỏng 250 ms vượt threshold 100 ms. `shouldCommit()` là `true`, code tính `diagnostic-for-slow`, gán fields và gọi `commit()`.

**Counter:** `Expensive detail builds: 1` chứng minh hàm chỉ chạy một lần dù có ba operation. Đây là giá trị ổn định trong điều kiện test đã kiểm chứng.

**Readback:** `RecordingFile.readAllEvents` trả cả những event khác của JVM nếu có. Vì thế code lọc **`demo.WorkEvent`** trước khi đếm và đọc `getString("jobId")`/`getString("detail")`. Dữ liệu có thể tồn tại trong file cho tới khi bị xóa theo lifecycle.

**Lưu ý exception path:** chương trình này gọi `end()` trong `finally` nhưng phần commit nằm **sau** finally. Nếu nghiệp vụ ném ngoại lệ, method thoát trước đoạn ghi event; đó là giới hạn của ví dụ tập trung vào guard. Phần sau có chương trình ghi được event khi thất bại.

## 6. Nhiều recording đồng thời — ngưỡng nhỏ nhất có hiệu lực

Một JVM có thể có **nhiều JFR recordings chạy cùng lúc**: recording liên tục của APM, recording phục vụ điều tra, hoặc session được tạo bởi người vận hành.

Ví dụ:
- Recording A enable `ProbeEvent` **không có threshold**.
- Recording B enable cùng loại `ProbeEvent` với threshold **5 giây**.

`Event.shouldCommit()` dùng **minimum threshold across running recordings** theo Javadoc Java 11. Vì vậy, một event chỉ mất vài microseconds vẫn có thể được `shouldCommit() == true` khi A và B cùng chạy.

**Chi tiết dễ hiểu sai:** JFR có thể thu các sự kiện theo chính sách tổng hợp để phục vụ nhiều recording. Một file cấu hình threshold 5 giây **không được bảo đảm chỉ chứa event >= 5 giây** nếu JVM đồng thời có recording khác đặt ngưỡng thấp hơn. Đã có trường hợp thực nghiệm file của cả hai recording đều có sự kiện ngắn.

### Ví dụ 2 — đối chiếu threshold khi chỉ có một recording và khi có hai

Tạo file **`JfrMultipleRecordingDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public class JfrMultipleRecordingDemo {
    @Name("demo.MultiThresholdEvent")
    static final class ProbeEvent extends Event {
        String message;
    }

    private static long count(Path file) throws Exception {
        return RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("demo.MultiThresholdEvent"))
                .count();
    }

    public static void main(String[] args) throws Exception {
        Path lowFile = Files.createTempFile("jfr-low-", ".jfr");
        Path highFile = Files.createTempFile("jfr-high-", ".jfr");
        try {
            try (Recording onlyHigh = new Recording()) {
                onlyHigh.enable(ProbeEvent.class)
                        .withThreshold(Duration.ofSeconds(5));
                onlyHigh.start();
                ProbeEvent probe = new ProbeEvent();
                probe.begin();
                probe.end();
                System.out.println("Only high-threshold isEnabled: " +
                        probe.isEnabled());
                System.out.println("Only high-threshold shouldCommit: " +
                        probe.shouldCommit());
                onlyHigh.stop();
            }

            try (Recording low = new Recording();
                 Recording high = new Recording()) {
                low.enable(ProbeEvent.class).withoutThreshold();
                high.enable(ProbeEvent.class)
                        .withThreshold(Duration.ofSeconds(5));
                low.start();
                high.start();

                ProbeEvent event = new ProbeEvent();
                event.begin();
                event.end();
                System.out.println("Two-recording isEnabled: " +
                        event.isEnabled());
                boolean eligible = event.shouldCommit();
                System.out.println("Two-recording shouldCommit: " +
                        eligible);
                if (eligible) {
                    event.message = "short";
                    event.commit();
                }

                low.stop();
                high.stop();
                low.dump(lowFile);
                high.dump(highFile);
            }
            System.out.println("Low-threshold recording events: " +
                    count(lowFile));
            System.out.println("High-threshold recording events: " +
                    count(highFile));
        } finally {
            Files.deleteIfExists(lowFile);
            Files.deleteIfExists(highFile);
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 JfrMultipleRecordingDemo.java
java JfrMultipleRecordingDemo
```

**Stdout đã kiểm chứng trong môi trường JFR thử nghiệm:**

```text
Only high-threshold isEnabled: true
Only high-threshold shouldCommit: false
Two-recording isEnabled: true
Two-recording shouldCommit: true
Low-threshold recording events: 1
High-threshold recording events: 1
```

### Diễn giải

- Với **chỉ một recording** threshold 5 giây, event tức thời là enabled nhưng **không đủ duration**.
- Khi có recording thứ hai **không threshold**, minimum threshold bằng 0: `shouldCommit` thành true.
- Hai file trên runtime đã kiểm thử đều chứa custom event ngắn, dù B yêu cầu 5 giây.
- Không suy diễn rằng file recording thứ B sẽ **luôn luôn** nhận đúng 1 event ở mọi JDK/provider/retention policy. Kết luận bền vững là **setting tổng hợp có thể khiến mỗi recording ghi nhiều dữ liệu hơn cấu hình riêng** và `shouldCommit` không trả quyết định cho từng file.
- Nếu muốn đánh giá một ngưỡng riêng trong QA, hãy quản lý/ghi nhận **tất cả recording đồng thời**, không chỉ một Recording do test tự tạo.

## 7. Chạy khi business code có exception: đo cả thành công và thất bại

Một instrumenter cần giữ nguyên ngữ nghĩa nghiệp vụ:

1. Khi thành công, trả kết quả bình thường.
2. Khi thất bại, giữ nguyên exception cho caller.
3. Nếu JFR enabled và event qua threshold, có thể ghi `outcome` của cả success/failure.
4. Không tính diagnostics đắt tiền khi event không đủ điều kiện.
5. Không để lỗi tạo diagnostics **che mất lỗi nghiệp vụ**.

Ví dụ 1 bỏ qua event lỗi vì commit đặt sau `finally`. Ví dụ 3 đưa phần `shouldCommit`/`commit` vào `finally`.

### Ví dụ 3 — chương trình Java hoàn chỉnh

Tạo file **`JfrFailurePathDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public class JfrFailurePathDemo {
    @Name("demo.JobOutcome")
    static final class JobEvent extends Event {
        String outcome;
        String diagnostic;
    }

    private static int builds;

    static void execute(int input) {
        JobEvent event = new JobEvent();
        boolean enabled = event.isEnabled();
        String outcome = "OK";
        if (enabled) {
            event.begin();
        }
        try {
            if (input < 0) {
                throw new IllegalArgumentException("invalid input");
            }
            System.out.println("Business result: " + (input * 2));
        } catch (RuntimeException error) {
            outcome = error.getClass().getSimpleName();
            throw error;
        } finally {
            if (enabled) {
                event.end();
                if (event.shouldCommit()) {
                    event.outcome = outcome;
                    builds++;
                    event.diagnostic = "summary-" + outcome;
                    event.commit();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-outcome-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(JobEvent.class).withoutThreshold()
                        .withoutStackTrace();
                recording.start();
                execute(5);
                try {
                    execute(-1);
                } catch (IllegalArgumentException error) {
                    System.out.println("Caught business failure: " +
                            error.getClass().getSimpleName());
                }
                recording.stop();
                recording.dump(file);
            }
            List<String> outcomes = RecordingFile.readAllEvents(file).stream()
                    .filter(e -> e.getEventType().getName()
                            .equals("demo.JobOutcome"))
                    .map(e -> e.getString("outcome"))
                    .sorted()
                    .collect(Collectors.toList());
            System.out.println("Recorded outcomes: " +
                    String.join(", ", outcomes));
            System.out.println("Diagnostic builds: " + builds);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 JfrFailurePathDemo.java
java JfrFailurePathDemo
```

**Stdout đã kiểm chứng:**

```text
Business result: 10
Caught business failure: IllegalArgumentException
Recorded outcomes: IllegalArgumentException, OK
Diagnostic builds: 2
```

Ở đây exception từ `execute(-1)` vẫn đi về `main`; JFR không nuốt nó. `finally` tạo event với outcome `IllegalArgumentException` khi event đủ điều kiện. Kết quả được **sort** trước khi in để không dựa vào thứ tự các events trong file.

**Đối với production**, phần instrumentation trong `finally` nên là **best-effort**: không blocking I/O, không khởi phát tác vụ quan trọng, không ném exception mới che mất exception nghiệp vụ. Nếu formatter có thể throw, phải cô lập lỗi diagnostics; có thể dùng một safe summary đã có sẵn thay vì serialize dữ liệu lớn. Ví dụ trên cố ý nối chuỗi đơn giản để phần tạo fields không phát sinh lỗi phụ.

## 8. Những dữ liệu nên và không nên đưa vào JFR

`jdk.jfr.Event` hỗ trợ các loại field phù hợp như Java primitive, `String`, `Thread` và `Class`. Các field `static` và `transient` không được ghi; arrays, enum và arbitrary object reference không trở thành field được ghi như bạn có thể kỳ vọng.

Ví dụ minh họa:

```java
@Name("demo.Inventory")
class InventoryEvent extends Event {
    int count;             // Primitive được hỗ trợ.
    long bytes;            // Primitive được hỗ trợ.
    String status;         // String được hỗ trợ.
    Class<?> handlerType;  // Class được hỗ trợ.
    Thread currentThread;  // Thread được hỗ trợ.
    transient Object raw;  // Không được lưu.
    static int global;     // Không được lưu.
}
```

Đây là class snippet, cần imports `Name`/`Event`.

**Có ích và ít tốn chi phí:** operation type, result count, status code, bytes processed, loại lỗi, duration, correlation ID được tổ chức cho phép.

**Nên tránh hoặc chỉ tính có điều kiện:** JSON lớn, recursive `toString`, request/response payload, hex dump, secondary DB lookup, stack trace tự tạo, string joining trên list khổng lồ.

**Không bao giờ ghi bừa bãi:** password, access token, cookie, khóa API, thông tin định danh nhạy cảm, raw body có PII, thông tin thanh toán. File `.jfr` có thể được lưu lâu hơn execution time và được chuyển tới hệ thống phân tích khác; phải có permission, retention và redaction policy.

### JFR không phải transaction/audit log

- JFR có thể lọc event theo threshold.
- Recording có thể bị tắt, thay cấu hình, stop hoặc bị giới hạn retention.
- JFR không bảo đảm event xuất hiện trong một file cụ thể khi `shouldCommit` true.
- Không sử dụng JFR event để thay các audit records bắt buộc theo quy định, transaction journal hoặc metric có cam kết vận hành.

Instrumentation chỉ để **quan sát**, không được làm thay đổi độ đúng của business workflow.

## 9. Chi phí của `isEnabled` và cách đặt guard trong hot path

`new WorkEvent()` vẫn là thao tác tạo object theo Java source, dù event tắt. JIT có thể tối ưu một số đường chạy, nhưng **không cam kết zero-allocation hoặc zero-overhead**. Lợi ích lớn hơn của `isEnabled` là tránh:

- Dựng chuỗi chỉ phục vụ observability.
- Tạo object chẩn đoán không dùng đến.
- Tìm metadata phức tạp khi recording tắt.
- Thu thập deep stack/extra context không cần.
- Chiếm CPU/memory ở các request có tần suất cao.

Nếu công việc tạo field rất rẻ và event ít xảy ra, code đơn giản `event.commit()` có thể đủ. Khi event gọi hàng triệu lần, benchmark có kiểm soát sẽ giúp quyết định có cần `isEnabled`/`shouldCommit` hay sampling/threshold.

**Không cache kết quả `isEnabled` vào static final boolean tính lúc khởi động**, vì JFR có thể được bật/tắt trong khi process đang chạy. Một snapshot cũ sẽ khiến chương trình bỏ mất events khi operator start recording sau đó.

**Không dùng `shouldCommit` làm thay thế `isEnabled` ở điểm rất sớm của duration event**. Chỉ khi duration đã được đo thì nó mới diễn đạt đủ ý định về threshold.

### Event instance và thread

Mỗi operation nên có **một event instance riêng**. Đừng share một instance qua nhiều thread hoặc request rồi dùng `begin/end` như counter toàn cục; fields của event là mutable state. Với asynchronous code, cần định nghĩa rõ thời điểm bắt đầu/kết thúc của logical operation và nơi commit hợp lệ, tránh cross-thread race.

Một event duration có thể đo các tác vụ đang chờ async nếu bạn thiết kế lifecycle tương ứng, nhưng việc gắn thời điểm vào đúng logical operation là trách nhiệm của ứng dụng. `isEnabled` vẫn chỉ là guard cho data collection, không điều khiển scheduling/cancellation của nghiệp vụ.

### Stack trace và threshold

`EventSettings.withoutStackTrace()` giúp giảm chi phí thu stack khi chỉ cần duration/status. Nhưng nếu sự cố cần biết call path, tắt stack sẽ mất thông tin. Không áp đặt `withoutStackTrace()` lên mọi event chỉ vì muốn performance; chọn theo use case và chính sách môi trường.

## 10. Đọc dữ liệu .jfr bằng API Java 11

Trong lab:
- `Recording.dump(Path)` ghi file.
- `RecordingFile.readAllEvents(Path)` tải tất cả events ra List.
- `RecordedEvent.getEventType().getName()` cho tên event.
- `RecordedEvent.getDuration()` cho duration.
- `RecordedEvent.getString("field")` đọc field kiểu `String`.

**Với recording lớn, không nên dùng `readAllEvents`** vì nó có thể giữ lượng dữ liệu lớn trong RAM. Đọc lần lượt:

```java
try (RecordingFile reader = new RecordingFile(path)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        if ("demo.WorkEvent".equals(event.getEventType().getName())) {
            // Xử lý từng event, không giữ cả file trong memory.
        }
    }
}
```

Đây là **snippet trong method**, cần `Path path`, imports `RecordingFile`/`RecordedEvent`, xử lý IOException. Theo Javadoc, chỉ nên đọc `RecordingFile` từ **nguồn đáng tin cậy**; đừng đưa file nhị phân không tin cậy vào process có quyền cao mà không có kiểm soát.

### Dùng công cụ `jfr` của JDK

Có thể kiểm tra file đã lưu bằng:

```sh
jfr print --events demo.WorkEvent work.jfr
```

Lệnh này chỉ chạy khi `work.jfr` **thực sự tồn tại**. Ba demo ở trên cố ý xóa file tạm trong `finally`; nếu muốn thực hành với `jfr print`, bạn có thể giữ file trong một thư mục lab có kiểm soát rồi xóa thủ công sau khi đọc. Đừng lưu file JFR chứa dữ liệu nhạy cảm trong một folder công khai.

## 11. Sự khác nhau giữa JFR, logging và metrics

| Cơ chế | Mục đích | Ghi chú |
| --- | --- | --- |
| **JFR custom event** | Điều tra performance/behavior, duration, thread/stack tùy settings | Có thể enable/disable/threshold |
| Application log | Ghi sự kiện vận hành và lỗi có ngữ nghĩa | Có log level, retention, redaction riêng |
| Metric | Counters, gauges, histograms cho SLO/alerts | Quản lý cardinality và sampling |
| Distributed trace | Theo dõi một request xuyên hệ thống | Có context propagation và sampling |

Không dùng `isEnabled` để quyết định có tăng một metric giao dịch bắt buộc hay không; nó là trạng thái JFR, không phải business configuration. Không coi `shouldCommit(false)` có nghĩa nghiệp vụ chưa chạy hoặc hoạt động nhanh chắc chắn thành công.

## 12. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `isEnabled` cho event có threshold | Vẫn tính detail cho event quá ngắn | Dùng `shouldCommit` sau `end` |
| Dùng `shouldCommit` trước `end` | Duration chưa hoàn chỉnh | Kết thúc timing rồi mới kiểm tra |
| Gán expensive fields trước `end` | Tăng duration giả tạo | Enrichment sau `end` |
| Gọi `commit` trước khi gán fields | Recorded fields thiếu giá trị | Gán trước commit |
| Chỉ commit sau `try/finally` dù cần lỗi | Exception path không tạo event | Dùng mẫu với commit trong `finally` |
| Instrumentation ném exception mới trong `finally` | Che mất business exception | Thiết kế best-effort và fault isolation |
| Dùng guard để không chạy business code | Kết quả thay đổi khi JFR bật/tắt | Guard chỉ instrument |
| Coi `isEnabled` true nghĩa event chắc chắn được ghi | Bỏ qua threshold/recording lifecycle | Quan sát file, hiểu `shouldCommit` |
| Coi `shouldCommit` true nghĩa mỗi recording đều có | Phụ thuộc settings tổng hợp/retention | Không coi là per-file guarantee |
| Một recording threshold cao đang chạy cùng recording threshold thấp | File high threshold có thể chứa event ngắn | Hiểu minimum threshold/thu thập chung |
| Không có recording mà vẫn serialize DTO lớn | Mất CPU/memory vô ích | Guard `isEnabled` trước formatter |
| `@Enabled(true)` nên luôn ghi event | Khi recording không chạy vẫn có thể disabled | Kiểm tra state runtime |
| Cache `isEnabled` khi JVM start | Bỏ events khi settings đổi | Kiểm tra đúng thời điểm |
| Tạo event rất lớn cho mọi request | Làm tăng overhead và kích thước JFR | Giới hạn field schema/length |
| Dùng enum/array/DTO làm field bất kỳ | Dữ liệu không được ghi như mong đợi | Dùng kiểu JFR hỗ trợ |
| Ghi secrets trong diagnostics | Rò rỉ qua file JFR | Redact/minimize |
| Đọc file JFR lớn bằng `readAllEvents` | OOM/GC overhead | Duyệt `RecordingFile` từng event |
| Áp `withoutThreshold()` cho hot event suốt ngày | Tăng lượng event | Đặt threshold phù hợp |

## 13. Bài tập thực hành

### Bài 1 — dự đoán hai guard

Xét ba trường hợp: không recording; recording bật threshold 100 ms và operation 5 ms; recording bật threshold 100 ms và operation 200 ms. Nêu `isEnabled`/`shouldCommit` và quyết định có dựng expensive JSON không. Tại sao `isEnabled(true)` chưa đủ?

### Bài 2 — thay đổi threshold

Chạy `JfrGuardDemo.java` với threshold 100 ms và đọc counter. Đổi sang `withoutThreshold()`, dự đoán số events và lần tạo detail. Lưu ý test có thể khác khi JVM có recording khác chạy đồng thời.

### Bài 3 — duration bị phình

Đưa `expensiveDetail(jobId)` lên trước `end()`. Dự đoán duration có thể tăng ra sao và vì sao threshold có thể cho kết quả sai ý định. Sửa về `end → shouldCommit → enrich → commit`.

### Bài 4 — hai recording

Chạy `JfrMultipleRecordingDemo.java`. Giải thích vì sao chỉ có recording high threshold thì `shouldCommit=false`, nhưng khi thêm recording low threshold thì thành `true`. Vì sao file high vẫn có thể chứa event ngắn?

### Bài 5 — exception path

Chạy `JfrFailurePathDemo.java`. Phân tích tại sao exception `IllegalArgumentException` được rethrow mà event thất bại vẫn ghi. Viết kế hoạch xử lý nếu formatter trong `finally` ném một exception khác.

### Bài 6 — bảo vệ dữ liệu

Một class event có field `request.toString()` chứa cookie, token và raw body. Thiết kế schema mới chỉ gồm operation type, result count, outcome, duration và correlation ID được phép; field nào phải redact?

### Bài 7 — đọc recording lớn

Viết lại bộ lọc `demo.WorkEvent` bằng `RecordingFile.hasMoreEvents`/`readEvent` và không giữ tất cả events trong một list. Khi nào nên dùng `readAllEvents`?

### Bài 8 — benchmark instrumentation

So sánh ba trạng thái: JFR tắt; JFR bật threshold cao; JFR bật threshold thấp. Đo CPU, allocations, throughput, GC và kích thước file. Chỉ kết luận khi có đủ mẫu và môi trường đo ổn định.

### Checklist hoàn thành

- [ ] Phân biệt enabled event, event qua threshold và event đã nằm trong một file.
- [ ] Biết `isEnabled()` dùng guard sớm.
- [ ] Biết `shouldCommit()` dùng sau `end()` để tránh enrichment tốn chi phí.
- [ ] Không để formatter làm tăng duration nghiệp vụ.
- [ ] Không bỏ business logic khi JFR disabled.
- [ ] Biết `Recording.enable/disable`, `withThreshold/withoutThreshold` và `withoutStackTrace`.
- [ ] Chạy được ba chương trình Java 11 và đối chiếu stdout.
- [ ] Hiểu minimum threshold khi có nhiều recording trong một JVM.
- [ ] Giữ exception nghiệp vụ khi ghi JFR ở `finally`.
- [ ] Tránh dữ liệu nhạy cảm và file JFR quá lớn.

## 14. Tài liệu chính thức vẫn áp dụng

1. [Java SE 11 — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): `isEnabled`, `shouldCommit`, `begin`, `end`, `commit`, field types và minimum threshold.
2. [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): bật/tắt event, start/stop/dump recording.
3. [Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withThreshold`, `withoutThreshold`, `withoutStackTrace`.
4. [Java SE 11 — Threshold annotation](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Threshold.html): mặc định `@Threshold("20 ms")`.
5. [Java SE 11 — JFR package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): settings và các annotations.
6. [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file JFR tuần tự hoặc nhỏ bằng `readAllEvents`.
7. [Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): event type, duration và field access.
8. [Oracle JFR API Programmer’s Guide — Event Threshold](https://docs.oracle.com/en/java/javase/26/jfapi/event-threshold.html): ngưỡng thu events và cách vận hành.
9. [Java SE 25 — Event](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): xác nhận API được duy trì trên JDK LTS hiện đại.

**Kết luận:** `isEnabled()` tránh đo đạc/enrichment không cần khi event bị tắt; `shouldCommit()` sau `end()` tránh tạo dữ liệu đắt tiền cho duration events bị lọc. Đặt guard đúng chỗ, giữ business logic độc lập, quản lý exception và metadata an toàn, đồng thời hiểu rằng **nhiều JFR recordings đồng thời có thể dùng threshold tối thiểu và cùng thu những sự kiện ngắn**.