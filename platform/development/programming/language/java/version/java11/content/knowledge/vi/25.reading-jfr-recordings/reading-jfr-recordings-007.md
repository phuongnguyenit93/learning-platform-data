# Đọc bản ghi JFR — Tương quan sự kiện nghiệp vụ với sự kiện JVM (Java 11+)

## Mục tiêu học tập

**Java Flight Recorder (JFR)** ghi các sự kiện do JVM phát ra và cả custom event do ứng dụng chủ động định nghĩa. Một recording có thể chứa đồng thời `jdk.ThreadSleep`, `jdk.GarbageCollection`, `jdk.SocketRead`, `jdk.ExecutionSample` và một event nghiệp vụ như `demo.BusinessAction`. Nhưng việc các event nằm trong cùng tệp **không tự động cho biết JVM event nào thuộc request nào hoặc gây ra độ trễ nào**.

Bài học này hướng dẫn **đọc bản ghi JFR và tương quan sự kiện nghiệp vụ với sự kiện JVM** bằng API **Java 11** vẫn còn áp dụng trên JDK hiện đại. Nội dung gồm cơ chế ghép bằng thời gian, thread và correlation ID; tình huống đồng bộ/bất đồng bộ; các hạn chế của sampling và event threshold; chương trình Java 11 chạy được, test chống ghép nhầm, quy trình sản xuất và bài tập.

Kết thúc bài, bạn sẽ biết:

1. Định nghĩa custom business event có `requestId`, `operation`, `success`, dữ liệu định lượng và thời gian bắt đầu/kết thúc.
2. Bật custom event cùng event JVM trong một recording và ghi ra file `.jfr`.
3. Đọc `RecordingFile`, `RecordedEvent`, `RecordedThread`, tên event, duration, thread ID, start/end time và stack trace.
4. Ghép JVM event vào **business event đồng bộ** bằng **cùng thread + khoảng thời gian**.
5. Ghép **asynchronous child event** với parent bằng **correlation ID được truyền rõ ràng**, sau đó ghép JVM event trên thread của child.
6. Kiểm tra false positives: một `ThreadSleep` nằm ngoài mọi request không được gán nhầm cho request chỉ vì cùng thread.
7. Hiểu correlation khác causation: thấy GC/CPU/sleep đồng thời với request chậm chưa đủ xác nhận root cause.
8. Xử lý sự kiện thiếu do threshold, sampling, retention, JVM khác, clock skew, thread pooling hoặc context propagation sai.
9. Kiểm thử mã với `javac --release 11` và ghi nhận output chính xác, tránh dùng API chỉ có trên các JDK mới hơn.

**Special Note:** ưu tiên JFR API còn hiện hành. Không dựa vào `-XX:+UnlockCommercialFeatures` hay cơ chế cấp phép cũ đã lỗi thời từ trước Java 11. Những công cụ bổ sung ở JDK mới không phải điều kiện bắt buộc cho source Java 11.

## 1. Bài toán: “request chậm” liên quan đến event JVM nào?

Giả sử ứng dụng xử lý hai nghiệp vụ:

```text
Cùng JVM / cùng khoảng ghi JFR

MAIN THREAD:
  [BusinessAction req-A ------------------]
       [jdk.ThreadSleep 130ms]
                         [ThreadSleep 75ms]   (ngoài giao dịch)
                                              [BusinessAction req-B -------------]
                                                  [jdk.ThreadSleep 130ms]

WORKER THREAD:
       [AsyncStage req-A ----]
          [jdk.ThreadSleep 55ms]
```

Trong recording:

- `demo.BusinessAction` và `demo.AsyncStage` do ứng dụng phát, chủ động ghi `requestId`.
- `jdk.ThreadSleep` do JVM cung cấp, có thời gian/thread, **không có requestId**.
- Một sleep cố ý nằm **ngoài cả A và B**; nếu thuật toán chỉ group theo thread ID, nó có thể bị gán sai.
- AsyncStage có cùng ID req-A nhưng ở thread khác; nếu chỉ group theo thread ID, nó không được liên kết với parent.

Khi đọc file, cần phân biệt **ba cấp độ kết nối**:

| Cấp | Bằng chứng | Có thể kết luận | Không thể kết luận |
| --- | --- | --- | --- |
| **Explicit ID** | Hai custom events có cùng request/trace ID | Cả hai gắn với context do ứng dụng định nghĩa | JVM đã tự xác thực ID hay chúng có parent-child causality |
| **Thread + interval** | Built-in event cùng Java thread và nằm trong business time window | Event xảy ra trong cửa sổ thực thi của thread đó | Nó chắc chắn gây ra thất bại nghiệp vụ |
| **JVM-wide overlap** | GC/CPU/heap events trùng thời gian và JVM | Có một biến động JVM cần điều tra | Biến động ấy là nguyên nhân duy nhất của latency |

**Tương quan (*correlation*) không bằng nhân quả (*causation*).** Với demo chúng ta biết mã gọi `Thread.sleep` nên ngủ góp phần vào duration; với hệ thống thật, không thể chỉ từ trùng mốc thời gian mà kết luận “GC gây request chậm”.

## 2. Dữ liệu nền tảng trong một RecordedEvent

Các API sau có trong module `jdk.jfr.consumer` từ Java 11:

| API | Dữ liệu | Lưu ý |
| --- | --- | --- |
| `e.getEventType().getName()` | Tên event type, ví dụ `demo.BusinessAction` | Nên dùng event name, không hardcode ID số |
| `e.getStartTime()` | `Instant` lúc bắt đầu event | Instant event có start/end giống nhau |
| `e.getEndTime()` | `Instant` lúc kết thúc | Dùng để so interval |
| `e.getDuration()` | `Duration` elapsed time | Không tự đồng nghĩa CPU time |
| `e.getThread()` | `RecordedThread` hoặc `null` | Nhiều JVM-wide events không có Java thread |
| `e.getStackTrace()` | `RecordedStackTrace` hoặc `null` | Có thể bị tắt hoặc truncated |
| `e.getString("requestId")` | ID từ field của custom event | Không gọi trên event không có field đó |
| `e.getBoolean("success")` | Boolean outcome của custom event | Outcome do ứng dụng ghi |
| `e.getLong("payloadBytes")` | Số bytes từ custom event | Annotation chỉ mô tả đơn vị |
| `e.getFields()` | Metadata để kiểm tra schema | Hữu ích với nhiều phiên bản event |

Trên `RecordedThread`:

- `getJavaThreadId()`: giá trị tương ứng `Thread.getId()`; có thể là **-1** nếu không phải Java thread.
- `getId()`: ID được JFR sử dụng cho thread trong lifetime JVM; không đồng nhất với Java thread ID.
- `getJavaName()`: tên Java thread, có thể `null` hoặc trùng giữa nhiều threads.

Khi muốn join theo Java thread, phải **kiểm tra thread khác null và Java thread ID hợp lệ**. Không được dùng cặp `-1 == -1` hoặc hai `null` như bằng chứng hai events có chung thread.

### Elapsed time khác CPU time

Nếu business event có `getDuration() = 130ms`, điều đó có thể bao gồm:

- CPU thực thi Java/native code.
- Chờ lock, condition, thread park hoặc sleep.
- Network/file I/O blocking.
- Đợi thread scheduling.
- GC pause hoặc thời gian hệ thống bị ảnh hưởng bởi runtime.

Không biến mọi 130ms thành “CPU consumed 130ms”. Để phân loại, kết hợp các events/thread states/stack và metrics phù hợp.

## 3. Định nghĩa custom business event có ID tương quan

Một event type nên có tên có namespace, field business ít nhạy cảm và duration rõ ràng.

```java
@Name("demo.BusinessAction")
@Label("Business action")
@Description("One business operation with a non-sensitive test ID")
@Category({"Example", "Business"})
static final class BusinessAction extends Event {
    @Label("Request ID")
    String requestId;

    @Label("Operation")
    String operation;

    @DataAmount(DataAmount.BYTES)
    long payloadBytes;

    boolean success;
}
```

Đây là **đoạn khai báo minh họa**, chưa độc lập. Định nghĩa đầy đủ nằm trong chương trình phần 7.

**Ý nghĩa schema:**

- `@Name` giúp phân biệt event bằng tên `demo.BusinessAction` khi đọc file hoặc lọc bằng `jfr print`.
- `requestId` là **context do ứng dụng tạo và truyền**, không do JVM tự đính vào `ThreadSleep`, `GC` hay `SocketRead`.
- `operation` nên là danh mục có cardinality thấp (như `reserve`, `cancel`), không ghi nguyên URL chứa dữ liệu cá nhân.
- `success` do nghiệp vụ quyết định, không suy từ việc JFR ghi event thành công.
- `payloadBytes` thật sự phải đo bằng bytes; `@DataAmount(BYTES)` **không tự chuyển đổi** giá trị nếu code đưa bits vào.

**Quy tắc bảo mật:** correlation ID nên là chuỗi thử nghiệm hoặc ID an toàn, không chứa email, số điện thoại, JWT, token truy cập, số thẻ, secret, dữ liệu khách hàng hoặc payload request. Tệp JFR có thể được xuất/trao đổi cho nhóm vận hành, nên phải áp dụng quyền truy cập và retention.

### Một duration business có phạm vi do code đặt

```java
BusinessAction action = new BusinessAction();
action.requestId = safeRequestId;
action.operation = "reserve";
action.begin();

try {
    doBusinessWork();
    action.success = true;
} finally {
    action.end();
    action.commit();
}
```

Đây là đoạn minh họa với `safeRequestId`/`doBusinessWork()` do ứng dụng định nghĩa. Gọi `begin()` và `end()` ở ranh giới cần đo; nếu chỉ đặt quanh lời gọi DB, event **không đại diện** toàn bộ request từ gateway. Khi có exception, ghi kết quả phù hợp trong `finally` mà không làm che lỗi ban đầu hoặc log payload nhạy cảm.

### Java 11 Event API

- `Event.begin()` bắt đầu interval.
- `Event.end()` kết thúc interval.
- `Event.commit()` ghi payload, timestamp/duration theo settings.
- `Event.isEnabled()` và `Event.shouldCommit()` giúp tránh tính payload tốn kém nếu event sẽ không được ghi.
- `@Label/@Description/@Category` và các unit annotations là metadata, **không phải cơ chế xác thực hay che dữ liệu**.

Không mặc định `commit` phải làm mọi request chậm đáng kể; JFR thường được tối ưu nhưng overhead phụ thuộc event rate, stack traces và recording settings.

## 4. Bật event nghiệp vụ và JVM event trong cùng recording

Mã Java 11:

```java
try (Recording recording = new Recording()) {
    recording.enable(BusinessAction.class)
            .withThreshold(Duration.ZERO)
            .withStackTrace();
    recording.enable("jdk.ThreadSleep")
            .withThreshold(Duration.ZERO)
            .withStackTrace();

    recording.start();
    // Sinh business events và các JVM events liên quan.
    recording.stop();
    recording.dump(file);
}
```

Đây là **đoạn minh họa** cần `BusinessAction`, `Duration` và `Path file`. Ví dụ chạy được ở phần 7 còn bật custom `AsyncStage`.

Vì sao cần enable rõ?

- Nếu không bật event type, JFR có thể không ghi nó.
- Với `jdk.ThreadSleep`, `withThreshold(Duration.ZERO)` giúp ghi cả những sleeps ngắn trong fixture.
- `withStackTrace()` cho phép kiểm tra call path, nhưng stack collection có chi phí.
- `Recording.start/stop/dump` tạo file `.jfr` để phân tích offline.
- Trong fixture, `recording.dump(file)` được thực hiện **sau stop**; đây là API Java, khác cú pháp `jcmd JFR.dump` nhưng đều xuất dữ liệu recording.

**Không bật mọi event và mọi stack với threshold zero vô hạn trên production.** Với môi trường tải lớn, dùng cấu hình `default`/`profile` hoặc custom JFC, giới hạn thời gian/retention và đo overhead.

### Thao tác với JVM đã chạy bằng jcmd

Nếu chương trình đã có custom event class phát đều đặn, có thể ghi JFR mà không phải gắn recorder vào business source:

```bash
jcmd -l
jcmd 12345 JFR.start name=Incident settings=profile disk=true maxage=10m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=Incident filename=incident.jfr
jcmd 12345 JFR.stop name=Incident
```

`12345` chỉ là PID minh họa. Settings `profile` **không chắc** bật đúng tất cả custom/JVM event/threshold bạn cần; phải kiểm tra JFC và `jcmd PID help JFR.start` trên JVM thật. `JFR.dump` tạo snapshot mà **không dừng** recording; `JFR.stop` mới kết thúc.

## 5. Đọc file JFR: API, schema và xử lý kích thước lớn

Ví dụ nhỏ:

```java
List<RecordedEvent> all = RecordingFile.readAllEvents(file);

for (RecordedEvent e : all) {
    System.out.println(e.getEventType().getName());
    System.out.println(e.getStartTime());
    System.out.println(e.getEndTime());
}
```

Đây là đoạn minh họa cần imports và `Path file`. **Chỉ gọi `getString("requestId")`** trên event type thực sự có field này (ví dụ `demo.BusinessAction`, `demo.AsyncStage`); JVM event `jdk.ThreadSleep` không có context đó.

### Khi file .jfr lớn: đọc từng event

Javadoc Java 11 lưu ý `RecordingFile.readAllEvents(Path)` dành cho trường hợp nhỏ, không phải cách đọc hiệu quả những file quá lớn. Dùng:

```java
try (RecordingFile reader = new RecordingFile(file)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent e = reader.readEvent();
        // Lọc event types, time window, lưu dữ liệu tổng hợp.
    }
}
```

Đây là đoạn minh họa; nếu tự thêm **tất cả** events vào một List không giới hạn thì vẫn có thể hết heap. Với recording lớn, chỉ giữ subset cần phân tích, bucket theo time ranges hoặc tạo index phù hợp. Chỉ mở file JFR từ nguồn đáng tin, kiểm soát IO và giới hạn dữ liệu nhạy cảm.

### Đừng giả định event list ở thứ tự nghiệp vụ

JFR ghi dữ liệu từ nhiều thread/chunk; file order không phải bằng chứng causality giữa những operations chạy đồng thời. Dùng `Instant` start/end để sắp timeline và giữ ID parent/child.

Nếu muốn sort List:

```java
List<RecordedEvent> ordered = new ArrayList<>(all);
ordered.sort(Comparator.comparing(
        RecordedEvent::getStartTime));
```

Đây là đoạn minh họa có imports `ArrayList`, `Comparator` và List. **Không sort trực tiếp List** từ `readAllEvents` mà không biết nó có modifiable không: Javadoc không bảo đảm điều đó.

### Phân biệt một JVM và nhiều JVM

- Java thread ID chỉ có ý nghĩa trong **phạm vi JVM**.
- Timestamps trong cùng recording giúp dựng relative timeline; ghép across hosts phải xét clock skew.
- Nếu nhiều snapshots chồng lặp từ cùng recording, cần xử lý duplicate events/time windows để tránh đếm hai lần.
- Nếu bản ghi bắt đầu sau incident, các events trước đó không thể được khôi phục.
- Sampling, thresholds, repository retention có thể bỏ dữ liệu.

## 6. Thuật toán ghép: thread + time window và explicit ID

### 6.1. Same-thread containment

Với event JVM `jvm` và business span `business`, một điều kiện **nằm hoàn toàn bên trong** là:

```text
jvm.startTime >= business.startTime
jvm.endTime   <= business.endTime
jvm.javaThreadId == business.javaThreadId
```

Java:

```java
private static boolean within(
        RecordedEvent inner, RecordedEvent outer) {
    Instant s = inner.getStartTime();
    Instant e = inner.getEndTime();
    return !s.isBefore(outer.getStartTime())
            && !e.isAfter(outer.getEndTime());
}
```

Dùng `java.time.Instant`. Với Java thread:

```java
private static long threadId(RecordedEvent e) {
    RecordedThread t = e.getThread();
    return t == null ? -1L : t.getJavaThreadId();
}
```

Trong **code tổng quát**, phải loại `threadId <= 0` khỏi phép join; `-1` là giá trị “không có Java thread”, không phải một thread chung. Mẫu phần 7 dùng `jdk.ThreadSleep` và custom events có Java thread hợp lệ.

**Vì sao dùng cả hai điều kiện?** Thread pools thường xử lý A, B, C nối tiếp trên cùng thread. Nếu chỉ group theo thread, một sleep giữa A và B bị gán nhầm. Nếu chỉ so timestamp, sleep của worker khác có thể gán nhầm vào A đang chạy cùng lúc.

### 6.2. Time overlap khác containment

Một JVM event có thể **chồng lặp một phần** với request, dù không nằm trọn trong interval:

```text
contained:   child.start >= parent.start AND child.end <= parent.end
overlap:     a.start < b.end AND b.start < a.end
             (với hai duration intervals có độ dài dương)
```

- `contained` phù hợp khi event ngắn xảy ra trong một stage cụ thể.
- `overlap` phù hợp phân tích GC pause/long lock wait và business interval.
- Instant events có start=end cần định nghĩa phép so khoảng riêng; không áp mù quáng điều kiện overlap cho độ dài 0.
- Chồng lặp có thể có nhiều parent requests; cần ghi rõ mức **confidence**.

Một event `jdk.GarbageCollection` không nhất thiết có Java thread mang ngữ cảnh request; ghép **same JVM + time overlap** để nêu giả thuyết, sau đó xem pause duration và các metrics khác trước khi kết luận.

### 6.3. Cross-thread: ID trước, thread/time sau

Khi request req-A gửi task sang worker:

```text
main thread:
  BusinessAction(requestId=req-A)
         |
         +-- submit task with req-A context
                    |
worker thread:      v
  AsyncStage(requestId=req-A)
         |
         +-- jdk.ThreadSleep (worker thread, inside stage)
```

Chuỗi suy luận:

1. `BusinessAction(req-A) ↔ AsyncStage(req-A)`: join trực tiếp bằng explicit ID do app truyền.
2. `AsyncStage(req-A) ↔ jdk.ThreadSleep(worker)`: join same worker thread + stage window.
3. `BusinessAction(req-A) ↔ jdk.ThreadSleep(main)`: join same main thread + business window.

**JVM event không có requestId tự nhiên**. Nó được nối qua một custom stage có ID. Nếu không phát stage event hoặc không propagate context, file JFR có thể không đủ dữ liệu để nối worker JVM events về request A.

### 6.4. Các yếu tố có thể gây false positives

- Nested spans cùng thread và cùng time window.
- Một thread có nhiều logical requests interleaved.
- Async tasks được gửi đi rồi hoàn thành sau khi parent event đã commit.
- Background work cùng thời gian nhưng không liên quan request.
- Retry/fan-out tạo nhiều stages với cùng request ID.
- Thread-local context không được cleanup, ID cũ bám thread pool.
- Worker thread được tái sử dụng, thread name trùng nhau.
- Event được commit ở thread khác nơi bắt đầu duration.
- Recording thiếu event vì threshold/sampling.

**Giải pháp:** khi có nhiều spans, thêm `spanId`/`parentSpanId` và rules rõ ràng về parent-child; không ép event vào một parent duy nhất chỉ từ thread+time.

## 7. Chương trình Java 11 hoàn chỉnh, đã biên dịch/chạy

Ví dụ `JfrBusinessCorrelationDemo.java` tạo **hai business requests**, một **async child**, một sleep ngoài giao dịch và các `jdk.ThreadSleep` bên trong chúng. Recording xuất ra file JFR; consumer đọc lại, assert mọi kết quả.

Đây là fixture kiểm soát, **không phải production request handler hoặc distributed tracer**. Không cần thư viện ngoài JDK, không dùng `HexFormat`, `RecordingStream` hay API JDK mới chỉ có sau Java 11.

### 7.1. Mã nguồn

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public final class JfrBusinessCorrelationDemo {
    @Name("demo.BusinessAction")
    @Label("Business action")
    @Description("One business operation with a non-sensitive test ID")
    @Category({"Example", "Business"})
    static final class BusinessAction extends Event {
        @Label("Request ID")
        String requestId;
        @Label("Operation")
        String operation;
        @DataAmount(DataAmount.BYTES)
        long payloadBytes;
        boolean success;
    }

    @Name("demo.AsyncStage")
    @Label("Async processing stage")
    @Category({"Example", "Business"})
    static final class AsyncStage extends Event {
        @Label("Request ID")
        String requestId;
        String stageName;
    }

    private static void perform(String requestId, boolean async)
            throws InterruptedException {
        BusinessAction action = new BusinessAction();
        action.requestId = requestId;
        action.operation = "reserve";
        action.payloadBytes = 2048L;
        action.begin();

        AtomicReference<Throwable> workerFailure =
                new AtomicReference<>();
        Thread worker = null;
        if (async) {
            worker = new Thread(() -> {
                try {
                    AsyncStage stage = new AsyncStage();
                    stage.requestId = requestId;
                    stage.stageName = "inventory";
                    stage.begin();
                    Thread.sleep(55);
                    stage.end();
                    stage.commit();
                } catch (Throwable ex) {
                    workerFailure.set(ex);
                }
            }, "inventory-worker");
            worker.start();
        }

        Thread.sleep(130);
        if (worker != null) {
            worker.join();
            if (workerFailure.get() != null) {
                throw new IllegalStateException(
                        "Async worker failed", workerFailure.get());
            }
        }
        action.success = true;
        action.end();
        action.commit();
    }

    private static long threadId(RecordedEvent event) {
        RecordedThread thread = event.getThread();
        return thread == null ? -1L : thread.getJavaThreadId();
    }

    private static boolean within(RecordedEvent inner,
            RecordedEvent outer) {
        Instant s = inner.getStartTime();
        Instant e = inner.getEndTime();
        return !s.isBefore(outer.getStartTime())
                && !e.isAfter(outer.getEndTime());
    }

    private static int countSleepInside(
            List<RecordedEvent> sleeps, RecordedEvent span) {
        int count = 0;
        for (RecordedEvent sleep : sleeps) {
            if (threadId(sleep) == threadId(span)
                    && within(sleep, span)) {
                count++;
            }
        }
        return count;
    }

    private static RecordedEvent find(
            List<RecordedEvent> events,
            String name, String requestId) {
        RecordedEvent found = null;
        for (RecordedEvent event : events) {
            if (name.equals(event.getEventType().getName())
                    && requestId.equals(event.getString("requestId"))) {
                if (found != null) {
                    throw new AssertionError(
                            "Duplicate event " + name);
                }
                found = event;
            }
        }
        if (found == null) {
            throw new AssertionError("Missing event " + name);
        }
        return found;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-business-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(BusinessAction.class)
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
                recording.enable(AsyncStage.class)
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
                recording.enable("jdk.ThreadSleep")
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
                recording.start();

                perform("req-demo-A", true);
                Thread.sleep(75); // Outside any business operation.
                perform("req-demo-B", false);

                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> all =
                    RecordingFile.readAllEvents(file);
            List<RecordedEvent> sleeps = new ArrayList<>();
            int businessCount = 0;
            for (RecordedEvent event : all) {
                String name = event.getEventType().getName();
                if ("jdk.ThreadSleep".equals(name)) {
                    sleeps.add(event);
                }
                if ("demo.BusinessAction".equals(name)) {
                    businessCount++;
                }
            }

            RecordedEvent a = find(
                    all, "demo.BusinessAction", "req-demo-A");
            RecordedEvent b = find(
                    all, "demo.BusinessAction", "req-demo-B");
            RecordedEvent async = find(
                    all, "demo.AsyncStage", "req-demo-A");

            int aSleep = countSleepInside(sleeps, a);
            int bSleep = countSleepInside(sleeps, b);
            int asyncSleep = countSleepInside(sleeps, async);
            int outsideMain = 0;
            for (RecordedEvent sleep : sleeps) {
                if (threadId(sleep) == threadId(a)
                        && !within(sleep, a)
                        && !within(sleep, b)) {
                    outsideMain++;
                }
            }

            boolean asyncDifferentThread = threadId(async) > 0
                    && threadId(async) != threadId(a);
            boolean asyncInsideBusiness = within(async, a);
            boolean stackPresent = a.getStackTrace() != null
                    && !a.getStackTrace().getFrames().isEmpty()
                    && async.getStackTrace() != null
                    && !async.getStackTrace().getFrames().isEmpty();
            boolean successValues = a.getBoolean("success")
                    && b.getBoolean("success")
                    && a.getLong("payloadBytes") == 2048
                    && b.getLong("payloadBytes") == 2048;
            boolean intervalsValid =
                    a.getDuration().toMillis() >= 100
                    && b.getDuration().toMillis() >= 100;

            if (businessCount != 2 || sleeps.size() < 4
                    || aSleep != 1 || bSleep != 1
                    || asyncSleep != 1 || outsideMain != 1
                    || !asyncDifferentThread || !asyncInsideBusiness
                    || !stackPresent || !successValues
                    || !intervalsValid) {
                throw new AssertionError(
                        "JFR correlation failed: "
                        + "business=" + businessCount
                        + ", sleeps=" + sleeps.size()
                        + ", a=" + aSleep + ", b=" + bSleep
                        + ", async=" + asyncSleep
                        + ", outside=" + outsideMain);
            }

            System.out.println("businessCount=" + businessCount);
            System.out.println("threadSleepEventsAtLeast4="
                    + (sleeps.size() >= 4));
            System.out.println("sameThreadSleepA=" + aSleep);
            System.out.println("sameThreadSleepB=" + bSleep);
            System.out.println(
                    "outsideBusinessSleep=" + outsideMain);
            System.out.println("asyncMatchedByRequestId=true");
            System.out.println(
                    "asyncDifferentThread=" + asyncDifferentThread);
            System.out.println(
                    "asyncWithinBusiness=" + asyncInsideBusiness);
            System.out.println("asyncThreadSleep=" + asyncSleep);
            System.out.println(
                    "businessStacksPresent=" + stackPresent);
            System.out.println(
                    "payloadAndSuccessValid=" + successValues);
            System.out.println(
                    "durationsAtLeast100ms=" + intervalsValid);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Về điều kiện thread:** helper `countSleepInside` trong fixture chỉ gặp các events gắn với Java threads có ID hợp lệ; với dữ liệu production tổng quát phải kiểm tra `threadId > 0` trước khi so sánh. Hai event cùng `-1` không được tính là cùng thread. Chương trình in kết quả kiểm thử ngắn, **không in raw .jfr, stack trace hoặc request payload**.

### 7.2. Lệnh chạy

Lưu tệp đúng tên `JfrBusinessCorrelationDemo.java` và chạy:

```bash
javac --release 11 -encoding UTF-8 JfrBusinessCorrelationDemo.java
java JfrBusinessCorrelationDemo
```

**Stdout đã kiểm tra thực tế sau khi biên dịch theo Java 11 và chạy trên JDK hỗ trợ JFR:**

```text
businessCount=2
threadSleepEventsAtLeast4=true
sameThreadSleepA=1
sameThreadSleepB=1
outsideBusinessSleep=1
asyncMatchedByRequestId=true
asyncDifferentThread=true
asyncWithinBusiness=true
asyncThreadSleep=1
businessStacksPresent=true
payloadAndSuccessValid=true
durationsAtLeast100ms=true
```

Chương trình đã **biên dịch với `javac --release 11 -encoding UTF-8` và chạy thành công**. Nó kiểm tra kết quả trước khi in; nếu thiếu một JVM event dự kiến hoặc match sai, sẽ ném `AssertionError`. Đây là một fixture có timing/sleep chủ đích, không phải khẳng định mọi JDK sẽ luôn thu đúng cùng số background events ở mọi cấu hình.

**Lưu ý Java 11:** biên dịch bằng `--release 11` trên JDK mới chứng minh code dùng API/classfile target Java 11. Để chứng minh tính tương thích **runtime JDK 11** của một sản phẩm, CI phải chạy thêm thật trên JDK 11. Không suy từ compile thành runtime verification.

### 7.3. Giải thích các assertion

| Output | Chứng minh |
| --- | --- |
| `businessCount=2` | Có hai business events mang req-A và req-B |
| `threadSleepEventsAtLeast4=true` | Tối thiểu 4 sleeps chủ động được JFR thu; không hardcode mọi background sleep |
| `sameThreadSleepA=1` | Một sleep trên main thread nằm trong interval A |
| `sameThreadSleepB=1` | Một sleep trên main thread nằm trong interval B |
| `outsideBusinessSleep=1` | Sleep giữa A/B không bị gán nhầm |
| `asyncMatchedByRequestId=true` | Event con có cùng req-A, do app propagate |
| `asyncDifferentThread=true` | Async stage không ở main thread |
| `asyncWithinBusiness=true` | Async stage nằm trong window A |
| `asyncThreadSleep=1` | Một sleep của worker nằm trong stage |
| `businessStacksPresent=true` | JFR đã thu stack cho business/async |
| `payloadAndSuccessValid=true` | Fields business được đọc chính xác |
| `durationsAtLeast100ms=true` | Hai business spans chứa sleep tối thiểu 100ms |

**Cảnh báo chống suy diễn:** `asyncMatchedByRequestId=true` là **nhãn kết quả test**, không phải trường requestId mà `jdk.ThreadSleep` tự có. Tầng ứng dụng tạo custom events để dựng chuỗi bằng chứng.

### 7.4. Vì sao cần sleep ngoài request?

Sleep 75ms nằm giữa hai business durations trên cùng main thread. Nếu query chỉ làm:

```text
WHERE jvm.threadId = business.threadId
```

nó có thể ghép sleep ngoài giao dịch cho cả A và B. Test đúng cần **cùng thread và time window**. Với những sự kiện nằm chồng nhau nhiều parent spans, nên quản lý thêm `spanId/parentSpanId` hoặc quy tắc deepest enclosing span.

### 7.5. Async stage minh họa điều gì?

Async stage bắt đầu trên `inventory-worker`, có cùng requestId req-A nhưng thread khác. JVM `ThreadSleep` trong worker không thể được match với thread của business event A; nó chỉ được nối vào request A bằng cách:

```text
req-A BusinessAction
       |
       | explicit requestId
       v
req-A AsyncStage on worker
       |
       | worker thread + stage interval
       v
jdk.ThreadSleep on worker
```

Đây là mô hình có thể mở rộng khi ứng dụng tạo nhiều child stages với IDs được propagate. Trong distributed hệ thống, cần trace/span context qua network; JFR không tự truyền ID sang JVM khác.

## 8. Các loại JVM events và độ tin cậy của phép nối

| JVM event | Cách liên quan business span | Cẩn trọng |
| --- | --- | --- |
| `jdk.ThreadSleep` | Cùng thread + interval | Sleep có thể là chủ đích; không có requestId |
| `jdk.ThreadPark` | Thread+time; đối chiếu stack/duration | Có thể là executor/lock/condition wait |
| `jdk.JavaMonitorEnter` | Thread+time; xem lock and stack | Threshold có thể loại wait ngắn |
| `jdk.SocketRead`/`jdk.SocketWrite` | Thread/time và endpoint metadata nếu có | Connection pooling/multiplexing có thể gây nhầm |
| `jdk.FileRead`/`jdk.FileWrite` | Thread/time và file/path metadata | Path có thể nhạy cảm; background I/O |
| `jdk.ExecutionSample` | Thread/sample time/stack | **Sampling**, không phải đếm mọi method call |
| `jdk.ObjectAllocationSample` | Sample time/stack/thread | Không đại diện mọi allocation |
| `jdk.GarbageCollection` | Cùng JVM + time overlap, đối chiếu pause | JVM-wide, không thể gán nguyên nhân cho một request chỉ bằng overlap |
| `jdk.CPULoad` | Time series/metrics toàn process | Không phải CPU time riêng request |
| Custom `demo.BusinessAction` | Explicit request/trace ID | ID do app cung cấp, có thể sai nếu propagation lỗi |

Các event types không nhất thiết được bật trong mọi JFR profile. Hãy kiểm tra schema và settings thật bằng `jfr summary`, `jfr metadata` hoặc `RecordingFile.readEventTypes()` trước khi dựa vào event. Tên và tính khả dụng cũng có thể khác theo JDK vendor/version.

### Phân tích GC chồng lặp với request

Giả sử request A chậm khi có `jdk.GarbageCollection`. Một quy trình thận trọng:

1. Xác định event thuộc **cùng JVM instance**.
2. Kiểm tra GC pause thực sự và overlap interval với request.
3. So thời điểm, duration và số request bị ảnh hưởng.
4. Đối chiếu GC metrics, heap usage, allocation rate và pause event types.
5. Loại các giả thuyết lock, I/O, network, queueing và CPU saturation khác.
6. Nếu khả thi, tái hiện/load test để xác định mức đóng góp.

**Không kết luận “GC là nguyên nhân” từ một overlap duy nhất.** GC cycle còn có thể gồm những pha concurrent không dừng application. Cần phân biệt sự kiện bắt đầu/kết thúc GC với khoảng pause thực.

## 9. Async, thread pools và distributed context

### Trong một JVM

- Truyền `requestId`/`traceId` vào task rõ ràng, hoặc dùng context propagation mechanism phù hợp.
- Mỗi stage quan trọng nên phát custom event với ID và duration.
- Nên có `spanId`/`parentSpanId` nếu cần phân biệt nhiều stages song song.
- `ThreadLocal` của main thread **không tự động truyền** sang mọi task trong thread pool.
- Nếu dùng ThreadLocal wrapper, phải cleanup trong `finally` để tránh rò ID giữa requests.
- Không dùng thread names làm key duy nhất; chúng có thể trùng/đổi.
- Một worker có thể xử lý request A rồi B trên cùng Java thread ID; time window và ID vẫn cần thiết.

### Qua nhiều JVM/service

- Dùng distributed trace context, ví dụ chuẩn propagation theo hệ thống observability đã chọn, qua HTTP/message queues.
- Mang trace/span IDs vào custom JFR events hoặc backend phân tích với quyền hạn phù hợp.
- Nhận diện JVM/process/node khi merge nhiều recording files; thread ID của service A không liên quan ID giống hệt ở service B.
- Đồng bộ thời gian giữa hosts và hiểu clock skew; không so timestamps cross-host như thứ tự nhân quả chắc chắn khi clocks lệch.
- Xem retries, fan-out, batching và async queues; cùng traceId có thể có nhiều spans.
- Đừng chỉ lấy requestId do client gửi rồi tin nó là khóa nội bộ duy nhất nếu nó có thể bị giả mạo hoặc gây cardinality explosion.

**Causal parent-child** là thông tin của hệ thống tracing/business protocol, không thể tự suy từ một bộ `Instant` nếu nhiều tác vụ đồng thời.

## 10. Sampling, threshold và dữ liệu vắng mặt

Không thấy JVM event trong .jfr **không chứng minh hành vi không xảy ra**. Những nguyên nhân có thể là:

1. Recording chưa bắt đầu hoặc đã dừng vào thời điểm đó.
2. Event type chưa được enable.
3. Threshold loại những events quá ngắn.
4. Sampling/periodic events chỉ thu một số mốc.
5. Disk repository/maxage/maxsize đã loại dữ liệu cũ.
6. JFR buffer chưa flush trước crash hoặc file snapshot tạo quá sớm.
7. Runtime/vendor/profiles khác nhau có event types/settings khác.
8. Đọc nhầm JVM/node/PID hoặc sai time window.
9. Consumer lọc sai tên event, schema hoặc thread ID.
10. Clock/timezone/interval boundary làm phép join không còn match.

Ví dụ:

```java
recording.enable(BusinessAction.class)
        .withThreshold(Duration.ofMillis(100));
```

Business events dưới 100ms có thể bị bỏ, khiến bạn không có parent để nối JVM event. Nếu `jdk.ThreadSleep` cũng dùng threshold 10ms, sleeps ngắn 1–5ms không xuất hiện. Vì vậy **correlation algorithm cần trạng thái “không đủ bằng chứng”**, không chỉ true/false tuyệt đối.

### Stack trace và sampling

`RecordedEvent.getStackTrace()` có thể là `null` nếu stack không được ghi. Stack trace có thể bị truncated và số frames khác giữa JDK builds. `ExecutionSample` là mẫu của runtime, không phải log toàn bộ phương thức của một request. Khi nhiều threads chạy song song, stack sample cung cấp bằng chứng hữu ích nhưng không tự trả lời “đã mất chính xác bao nhiêu milliseconds trong nghiệp vụ A”.

## 11. Công cụ CLI và phân tích file offline

Giả sử bạn có file `incident.jfr` đúng JVM và recording:

```bash
jfr summary incident.jfr
jfr metadata incident.jfr
jfr print --events demo.BusinessAction incident.jfr
jfr print --events demo.AsyncStage incident.jfr
jfr print --events jdk.ThreadSleep incident.jfr
```

- `jfr summary` kiểm tra những event types nào đã xuất hiện.
- `jfr metadata` giúp xem fields/content types và xác định name cần lọc.
- `jfr print` đọc timestamps, durations, thread và payload.
- JDK Mission Control giúp xem timeline, stack, CPU, GC và event browser trực quan.

Không giả định một file production có event tên `demo.BusinessAction`; đây là tên custom do fixture định nghĩa. Khi phân tích service thật, lọc theo **tên custom events do service phát** và kiểm tra schema từ recording.

**Để tránh dữ liệu sai:** không cộng một event hai lần khi hai snapshot JFR chồng lặp về thời gian; không ghép hai JVM chỉ vì thread IDs giống nhau.

## 12. Runbook production: từ độ trễ đến giả thuyết có kiểm chứng

**Bước 1 — Định vị đúng process và time window.** Xác định service, JVM instance/PID/node, version, khoảng request latency tăng và file JFR tương ứng.

**Bước 2 — Kiểm tra recording settings.** Những event gì được bật? Threshold/sampling/stack? File retention tối đa? Nếu dữ liệu thiếu, ghi rõ limitation.

**Bước 3 — Đọc custom business spans.** Lọc theo tên, operation/result và ID an toàn. Nhìn duration distribution/latency outliers, tránh chỉ nhìn một request ngẫu nhiên.

**Bước 4 — Nối custom child stages qua ID.** Đánh dấu thread chuyển tiếp, parent/child span, retry/fan-out. Chỉ chọn quan hệ parent nếu schema thực sự định nghĩa nó.

**Bước 5 — Nối JVM events.** Với mỗi business/async stage có thread ID hợp lệ, tìm event cùng JVM, cùng Java thread, trong khoảng thời gian (hoặc overlap theo loại event).

**Bước 6 — Xem global JVM context.** So GC pauses, process CPU, heap/threads và các events JVM-wide trong khoảng incident. Đây là bối cảnh, không phải một request key.

**Bước 7 — Kiểm tra root cause.** Đối chiếu stack, duration, metrics/logs/traces và trạng thái tài nguyên. Tránh tuyên bố nhân quả từ overlap.

**Bước 8 — Báo cáo có độ tin cậy.** Với mỗi nhận định, ghi loại bằng chứng: direct ID, thread+window heuristic, hoặc same-JVM overlap. Nếu không có dữ liệu do sampling, nêu rõ.

**Bước 9 — Bảo mật.** File .jfr có thể chứa names, paths, classes, stacks và custom fields. Kiểm soát quyền truy cập, mã hóa, retention, xóa/ẩn dữ liệu nhạy cảm khi chia sẻ.

**Bước 10 — Kết thúc recording đúng mục tiêu.** Dừng các recording/profile không cần thiết, tránh thu dữ liệu vô hạn và gây disk pressure.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Tưởng mọi JVM event có `requestId` | Đọc field không tồn tại hoặc gán ID giả | Explicit ID chỉ ở custom events đã thiết kế |
| Chỉ group theo thread | Gán nhầm sleep ngoài request | Thread ID + time window |
| Chỉ group theo timestamp | Ghép event từ thread khác | Process/thread/context cùng thời gian |
| Coi GC overlap là root cause | Kết luận sai | Kiểm tra GC pause và bằng chứng bổ sung |
| Coi elapsed duration là CPU time | Đánh giá sai hiệu năng | Xem thread states, sampling và I/O |
| Chỉ dùng same-thread để nối async | Mất liên kết worker | Propagate requestId/traceId |
| Không cleanup ThreadLocal context | Gắn request B vào ID request A | finally cleanup |
| Coi hai `null` threads là một thread | Ghép sai JVM-wide events | Bỏ join nếu thread không hợp lệ |
| Dùng thread name duy nhất | Tên có thể trùng/đổi | Identity + process + time |
| Đo time window theo chỉ một mốc | Event có duration bị gán sai | Start/end interval |
| Coi mọi event thiếu là không xảy ra | Blind spot do recording settings | Kiểm tra threshold/sampling/retention |
| Dùng `readAllEvents` cho file khổng lồ | OOM | Streaming/aggregation |
| Sort trực tiếp readAllEvents List | Không bảo đảm modifiable | Copy List trước sort |
| So JVM trên hai hosts bằng thread ID | ID không toàn cục | JVM ID/trace context/clock sync |
| Ghi JWT/email vào custom event | Rò thông tin từ file JFR | ID không nhạy cảm + file access policy |
| Không xem nested spans | Một event gán nhiều parents | parentSpanId/deepest span policy |
| Bật mọi event+stack với threshold zero vô hạn | Overhead/disk/privacy risk | Scope/threshold/retention và đo thực tế |

## 14. Thiết kế kiểm thử correlation và QA

Một test tốt phải bao gồm **positive** và **negative cases**.

### Positive

- Custom `demo.BusinessAction` ghi được req-A và req-B.
- `jdk.ThreadSleep` trong A/B cùng main thread được match.
- Child `demo.AsyncStage` có req-A dù thread khác.
- JVM ThreadSleep trong child được match qua child thread/time.
- Duration, payload, boolean outcome và stack thực sự được ghi.
- File `.jfr` mở/đọc được sau recording stop/dump.

### Negative

- Một JVM event **ngoài cả hai business intervals** không được gán vào A/B.
- Một event trên worker không thể tự nhận requestId do JVM sinh.
- Nếu same thread nhưng khác request window, không match.
- Event không có Java thread ID hợp lệ không được join bằng `-1`.
- Nếu thiếu event do threshold/sampling, hệ thống ghi “không đủ dữ liệu”, không suy ra không có hoạt động.
- Nếu nhiều nested spans, kết quả có thể nhiều parent; không tự chọn một nếu không có rule.
- Không assert exact stack frames/PID/timestamps và tất cả background event counts giữa mọi JDK/vendor.

### CI matrix

| Chiều | Test nên có |
| --- | --- |
| Java source target | `javac --release 11` |
| Runtime Java 11 | Chạy thật JDK 11 nếu cam kết tương thích |
| Runtime hiện tại | JDK/vendor/version của production |
| JVM event settings | Enabled/threshold/stack đúng |
| Business context | Sync, async, retries, fan-out |
| File | .jfr nhỏ và streaming file lớn |
| Time | Interval containment, overlap và boundary |
| Thread | Java thread ID hợp lệ, thread reuse |
| Distributed | Clock skew và trace propagation |
| Data safety | Không có PII/secret trong event payload |
| Negative controls | Event ngoài request bị loại, event thiếu được giải thích |

## 15. Bài tập và đáp án

**Bài 1.** Có thể gọi `getString("requestId")` trên `jdk.ThreadSleep` rồi chắc chắn có giá trị không? **Không.** Built-in event không mang business context mặc định.

**Bài 2.** Hai requests A/B chạy tuần tự cùng worker; một sleep xảy ra giữa chúng. Chỉ so thread ID có đúng không? **Không**; cần time window.

**Bài 3.** AsyncStage chạy ở thread khác BusinessAction; nối bằng gì? **Explicit request/trace ID** được ứng dụng truyền.

**Bài 4.** JVM ThreadSleep trong async stage có ID req-A trực tiếp không? **Không**. Nối qua stage custom event có ID, rồi worker thread/time.

**Bài 5.** JVM GC event có overlap request thì có chứng minh GC gây request chậm? **Không**; cần pause duration và nguồn bằng chứng khác.

**Bài 6.** Business duration 130ms có phải tiêu thụ 130ms CPU? **Không**, elapsed time có cả sleep/I/O/wait.

**Bài 7.** `RecordedEvent.getThread()==null`, có thể join bằng `-1==-1` không? **Không**.

**Bài 8.** Tại sao không trực tiếp sort List từ `readAllEvents`? Vì Javadoc không bảo đảm List có thể modify; tạo `new ArrayList<>(events)` trước.

**Bài 9.** Không thấy `jdk.ThreadSleep` trong file; kết luận application chưa gọi sleep? **Không**. Kiểm tra enabled, threshold, time window và retention.

**Bài 10.** `jdk.ExecutionSample` cho đếm đủ mọi method call của request? **Không**, đó là sampled evidence.

**Bài 11.** Hai JVM có `Thread.getId()==17` thì có cùng logical thread? **Không**, ID thuộc JVM riêng.

**Bài 12.** Có nên dùng email/JWT làm correlation ID trong JFR không? **Không**; dùng ID không nhạy cảm.

**Bài 13.** Lệnh nào xem event schema/file? **`jfr summary`**, `jfr metadata` và `jfr print --events ...`.

**Bài 14.** Khi một event JVM nằm trong hai nested spans, hệ thống nên làm gì? **Đặt policy parent/deepest span hoặc dùng parentSpanId**; không chọn tùy tiện.

**Bài 15.** `javac --release 11` trên JDK mới chứng minh có thể chạy trên JDK 11 thật chưa? **Chưa**; cần runtime test bằng JDK 11.

### Checklist trước khi kết luận incident

1. Đúng JVM/process/node và khoảng ghi?
2. Custom event schema/ID do app định nghĩa có nhất quán?
3. Event types/threshold/sampling/retention được kiểm tra?
4. Đã so đúng start/end/duration, không chỉ timestamp một điểm?
5. Với same-thread join, Java thread IDs hợp lệ?
6. Có loại event ngoài request để tránh false positives?
7. Async contexts được propagate qua boundaries?
8. Có phân biệt explicit ID join và heuristic thread+time?
9. Có xét nested/retry/fan-out và event trên JVM khác?
10. Có hiểu JVM-wide GC/CPU chỉ là bối cảnh?
11. Có kiểm tra stack, metrics, logs/traces trước khi kết luận causation?
12. Có bảo vệ ID, event payload và file JFR?
13. Đã chạy kiểm thử trên đúng JDK/runtime cần hỗ trợ?
14. Có ghi rõ mức độ tin cậy và dữ liệu còn thiếu?

## Tài liệu tham khảo

- [Oracle Java SE 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): custom JFR Event và Recording API.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): begin/end/commit/isEnabled/shouldCommit.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable, start, stop và dump.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): readAllEvents, hasMoreEvents, readEvent và cảnh báo file lớn.
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): getStartTime/getEndTime/getDuration/getThread/getStackTrace.
- [Oracle Java SE 11 — RecordedThread](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): getJavaThreadId/getId/getJavaName.
- [Oracle Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): đọc các custom payload fields.
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold và stack settings.
- [Oracle Java SE 25 — jdk.jfr.consumer](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): JFR consumer APIs vẫn hiện hành.
- [Oracle Java SE 25 — jfr tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): jfr summary/metadata/print.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): tích hợp JFR vào OpenJDK.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): UI phân tích JVM events và runtime performance.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền ngữ cảnh phân tán qua nhiều dịch vụ.

**Kết luận:** hãy đặt **ID nghiệp vụ ở custom JFR events**, liên kết JVM events trong xử lý đồng bộ bằng **Java thread + khoảng thời gian**, và truyền ID qua async stages trước khi ghép JVM events của worker. Một JVM-wide event trùng giờ chỉ là bối cảnh, không tự chứng minh nguyên nhân. Đọc `RecordingFile`, kiểm tra schema/settings/stack, tránh false positives và sampling blind spots, kết hợp metrics/logs/traces và quản lý bảo mật file JFR.