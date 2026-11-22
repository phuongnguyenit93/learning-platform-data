# 14.1. JFR ghi sự kiện gì? Quan hệ giữa event, timestamp, duration và stack trace

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả **Java Flight Recorder (JFR)** thu thập dữ liệu runtime theo mô hình **event** và phân biệt event với log, metric và thread dump.
2. Kể được các **nhóm sự kiện JFR** thường dùng để điều tra CPU, GC, cấp phát, I/O, đồng bộ, thread và hoạt động của JVM.
3. Đọc chính xác ý nghĩa của **event type, timestamp/startTime, duration/endTime, event thread, payload và stack trace** trong một bản ghi.
4. Phân biệt sự kiện **tức thời**, **có khoảng thời gian**, **lấy mẫu** và **định kỳ**; hiểu vì sao một event không nhất thiết có duration đáng kể hoặc stack trace.
5. Tự tạo một file `.jfr`, lọc và đọc event bằng `jfr`/API Java 17+, rồi đặt các event trên trục thời gian mà không suy diễn sai nguyên nhân.

> **Ý chính:** JFR lưu các sự kiện có kiểu và metadata. Mỗi bản ghi event cho biết *điều gì được quan sát*; timestamp định vị nó trên thời gian; duration (nếu có) biểu thị thời lượng sự kiện đo; stack trace (nếu được thu) cho biết chuỗi lời gọi tại **điểm lấy stack**. Bốn thông tin này bổ sung cho nhau nhưng không tự động tạo thành toàn bộ lịch sử thực thi của một request.

## 1. JFR là gì và event khác log thế nào?

**Java Flight Recorder** là hệ thống quan sát tích hợp với HotSpot/JDK, thu các bản ghi sự kiện từ JVM, thư viện JDK và ứng dụng. Các event thường được ghi vào buffer trong runtime, rồi tập hợp thành recording có thể lưu thành file nhị phân `.jfr`. Có thể phân tích bằng công cụ `jfr`, **Java Mission Control (JMC)** hoặc API `jdk.jfr.consumer`.

Mô hình khái niệm:

```text
Ứng dụng + JVM
    |
    | phát sinh event có kiểu/metadata
    v
JFR (event settings, timestamp, duration, payload, stack tùy cấu hình)
    |
    | ghi vào buffer / recording
    v
File .jfr
    |
    +--> jfr summary / jfr print
    +--> Java Mission Control (timeline, bảng, flame graph tùy phân tích)
    +--> RecordingFile / EventStream API
```

So sánh:

| Nguồn | Bản chất | Trả lời tốt câu hỏi nào? | Điểm cần nhớ |
| --- | --- | --- | --- |
| Log ứng dụng | Thông điệp do mã ghi ra, thường là chuỗi văn bản. | Quyết định nghiệp vụ, lỗi, correlation ID, luồng nghiệp vụ đã được log. | Không tự mang CPU/GC/stack của mọi thao tác. |
| Metric | Số đo tổng hợp theo thời gian: tỷ lệ, bộ đếm, gauge. | CPU %, số request/s, pause GC p95, heap used. | Không tự xác định stack của một lần xảy ra. |
| Thread dump | Ảnh chụp stack/trạng thái thread tại thời điểm lấy mẫu. | Thread đang ở đâu, chờ gì tại thời điểm chụp? | Không tự có toàn bộ lịch sử event trước đó. |
| **JFR event** | Bản ghi có type, thời điểm, có thể có duration, thread, stack và field chuyên biệt. | Điều gì xảy ra, vào lúc nào, kéo dài bao lâu, trong ngữ cảnh nào? | Có thể chỉ là mẫu/đã lọc; sự kiện không xuất hiện chưa chắc hoạt động không xảy ra. |

JFR **không** phải một file log liên tục chứa từng lệnh Java, từng method call hoặc mọi object allocation. JVM cố gắng giảm overhead bằng cấu hình chọn event, threshold, sampling, period và buffer. Do đó **phạm vi quan sát phụ thuộc recording settings**.

## 2. JFR ghi những loại sự kiện gì?

Tên event dưới đây là các **ví dụ tiêu biểu** trên HotSpot/JDK hiện đại; event cụ thể có được bật/được phát sinh hay không phụ thuộc **JDK, file cấu hình `.jfc`, threshold và workload**. Không phải tất cả đều hiện diện trong mọi file.

| Nhóm | Ví dụ event JFR | Câu hỏi thực tế |
| --- | --- | --- |
| **GC & heap** | `jdk.GarbageCollection`, các event phase GC, `jdk.GCHeapSummary` | GC diễn ra khi nào, kéo dài bao lâu, heap thay đổi thế nào? |
| **CPU / lấy mẫu thực thi** | `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Những stack nào được lấy mẫu khi chạy? CPU tiến trình/máy biến động ra sao? |
| **Cấp phát bộ nhớ** | `jdk.ObjectAllocationSample`, một số loại allocation event khác tùy JDK/cấu hình | Có những lớp/object nào xuất hiện trong mẫu cấp phát; điểm cấp phát nằm ở stack nào? |
| **I/O** | `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, `jdk.SocketWrite` | I/O nào lâu, bao nhiêu byte, từ thread/stack nào? |
| **Đồng bộ / chờ** | `jdk.JavaMonitorEnter`, `jdk.ThreadPark` | Chờ monitor/park lâu ở đâu, có tranh chấp lock hay queue wait không? |
| **Thread và lifecycle** | `jdk.ThreadStart`, `jdk.ThreadEnd` và các event liên quan platform/virtual thread tùy JDK | Thread xuất hiện/kết thúc thời điểm nào? |
| **Ngoại lệ** | Một số event về exception/throw, thường cần bật rõ khi muốn thu chi tiết | Exception nào được ném và tại call site nào? |
| **Class/JIT/JVM** | Event class loading, compilation, safepoint, flags, môi trường | Runtime đang load class/JIT/stop tại safepoint ra sao? |
| **Ứng dụng tự định nghĩa** | Chẳng hạn `demo.Task`, `app.OrderProcessed` từ lớp kế thừa `jdk.jfr.Event` | Một bước nghiệp vụ bắt đầu/kết thúc khi nào, có metadata nào? |

Để biết **các event type thực sự có mặt trong file**, dùng `jfr summary recording.jfr` hoặc `jfr metadata recording.jfr`; để biết những setting đang bật trên bản recording, kiểm tra cấu hình `.jfc`/recording thực tế. Một dòng `jdk.SocketRead` không xuất hiện có thể do không thực hiện socket read, duration thấp hơn threshold, event bị tắt hoặc recording không bao trùm thời điểm đó.

### Phân biệt bốn kiểu sự kiện thường gặp

1. **Instant event (tức thời):** mô tả một mốc, ví dụ thread start. `startTime` và `endTime` trùng nhau, `duration` bằng 0 theo API `RecordedEvent`. Không đo thời gian *sống của thread* chỉ bằng riêng event start.
2. **Duration event (có khoảng thời gian):** mô tả thao tác từ bắt đầu đến kết thúc, ví dụ socket read, thread park, monitor wait hoặc một event nghiệp vụ tự đo bằng `begin()`/`end()`. Có `startTime`, `endTime` và `duration`; một số sự kiện ngắn có thể bị loại vì **threshold**.
3. **Sampled event:** ví dụ `jdk.ExecutionSample`, chỉ phản ánh điểm lấy mẫu của thread/stack theo chu kỳ hay thuật toán lấy mẫu; **không** có nghĩa mỗi lần gọi method đều tạo một event và cũng không có nghĩa duration của event bằng thời gian CPU mà method đã dùng.
4. **Periodic event:** ví dụ số liệu tải CPU hoặc trạng thái bộ nhớ thu theo chu kỳ. Timestamp đánh dấu mốc thu/ghi số liệu; field metric có thể tổng hợp thông tin qua một cửa sổ thời gian. Không suy ra toàn bộ cửa sổ ấy chính là `duration` của event.

## 3. Cấu trúc một bản ghi event: type, time, thread, payload, stack

Hãy hình dung một `jdk.SocketRead` được ghi nhận với dữ liệu minh họa sau (đây là **bảng giải thích ý nghĩa**, không phải output nguyên văn do `jfr print` tạo ra):

| Thuộc tính | Giá trị minh họa | Nghĩa |
| --- | --- | --- |
| Event type | `jdk.SocketRead` | Định danh **loại** sự kiện. Nhiều bản ghi cùng type có thể tồn tại trong recording. |
| Start timestamp | `2026-10-29T09:30:15.100Z` | Thời điểm thao tác được xem là bắt đầu. |
| Duration | `85 ms` | Khoảng thời gian sự kiện đo: thao tác có thể chờ I/O và không nhất thiết sử dụng CPU liên tục. |
| End timestamp | `2026-10-29T09:30:15.185Z` | Mốc kết thúc tương ứng; về logic bằng start + duration. |
| Event thread | `worker-4` | Thread được gắn với sự kiện tại thời điểm ghi; không phải toàn bộ hệ thống thread liên quan. |
| Payload | Ví dụ địa chỉ/socket, số byte đọc | Field cụ thể do định nghĩa event cung cấp. |
| Stack trace | Chuỗi các frame `class.method(...)` | Call stack tại điểm JFR chụp stack, nếu recording có bật và type hỗ trợ. |

Định dạng thời gian hiển thị trong GUI, `jfr print` hay Java `Instant` có thể khác nhau theo công cụ và múi giờ. Khi so với log, hãy **chuẩn hóa múi giờ** trước, đừng coi timestamp format khác nhau là event xảy ra tại hai thời điểm khác nhau.

Một event type được mô tả bằng metadata (tên, nhãn, category, field descriptors và settings). **Một event instance** là một lần xảy ra cụ thể của event type đó. `jdk.SocketRead` là **type**; 500 lần read trong một recording có thể tạo nhiều **instance** event `jdk.SocketRead` nếu đáp ứng cấu hình.

### 3.1. `timestamp` / `startTime`: khi nào?

API `RecordedEvent.getStartTime()` trả `java.time.Instant`, tức **thời điểm bắt đầu** của event; `getEndTime()` trả thời điểm kết thúc. Nếu là instant event thì hai thời điểm bằng nhau. Nhiều công cụ hiển thị field thời gian tên `startTime`, thường gọi ngắn là *timestamp*.

Không được nhầm:

- **Event time**: thời điểm hoạt động xảy ra/được đo.
- **Commit time**: thời điểm recorder chấp nhận event hoặc dữ liệu tại `commit()` đối với event ứng dụng.
- **Flush/file write time**: lúc dữ liệu ở buffer được đưa vào file; có thể muộn hơn event time.
- **Analysis time**: lúc bạn mở file `.jfr` và xem kết quả.

JFR buffer có thể được ghi ra file sau; vì thế **thời điểm file được sửa** và **thứ tự dòng khi in file** không nên dùng thay timestamp sự kiện. Khi phân tích timeline, lấy timestamp từ metadata event.

### 3.2. `duration`: kéo dài bao lâu?

`RecordedEvent.getDuration()` trả `java.time.Duration` và đo bằng độ phân giải nanosecond trong API. Về ngữ nghĩa:

```text
eventStart ------------------------------------- eventEnd
    |<----------- event duration --------------->|

duration ≈ endTime - startTime
```

Với một thao tác `SocketRead` kéo dài 85 ms, đó là **thời gian thao tác đọc được đo**, có thể bao gồm thời gian bị chặn/chờ dữ liệu/scheduling. Không tự kết luận 85 ms **CPU time**. Cũng không suy ra toàn bộ request HTTP mất đúng 85 ms vì request có thể gồm nhiều bước khác.

Các trường hợp:

- Với **instant event**, duration bằng zero; không phải lỗi.
- Với event có `@Threshold("10 ms")` hoặc setting `threshold=10 ms`, sự kiện dưới 10 ms có thể **không được ghi**, dù thao tác thật sự xảy ra.
- Có event mà ý nghĩa chính là **một số đo trong payload** (tải CPU, số byte, tỷ lệ sử dụng) chứ không phải duration đáng chú ý.
- `Duration.toMillis()` **làm tròn xuống** tới mili giây nguyên; muốn phân tích thao tác ngắn hơn có thể dùng `toNanos()` hoặc giá trị duration chính xác hơn.
- Một event dài bất thường không tự chứng minh phương thức trên stack đang chiếm CPU: đó có thể là **waiting time**, lock, network hoặc scheduling.

### 3.3. `stackTrace`: chương trình đang ở đâu?

`RecordedEvent.getStackTrace()` trả `RecordedStackTrace` hoặc `null`. Khi JFR thu stack cho event do ứng dụng phát ra, `@StackTrace`/setting `stackTrace=true` cho phép ghi chuỗi frame **tại lúc `Event.commit()`**, không tự ghi toàn bộ các method chạy trong suốt duration. Với event JVM, stack thể hiện ngữ cảnh điểm JVM lấy stack cho event đó; riêng event sampling có ý nghĩa là stack **tại điểm lấy mẫu**.

Một stack có thể cho thấy:

```text
com.example.Service.load()
  -> com.example.Client.read()
    -> java.net.Socket...
```

Từ đó bạn có thể đặt câu hỏi “Lời gọi nào dẫn đến socket read?” nhưng chưa thể khẳng định đoạn `Service.load()` sử dụng CPU suốt duration.

**Các giới hạn thiết yếu:**

- Stack trace có thể **vắng mặt** do type/setting/recording không bật stack trace, hoặc JVM không thể thu trong trường hợp cụ thể.
- Stack có thể bị **giới hạn độ sâu**. Tăng số frame được `jfr print` hiển thị không phục hồi các frame vốn **không được ghi**.
- Stack của event tại điểm commit/sampling **không phải causal graph** giữa thread, process hay service. Cần request ID/tracing/log nếu muốn nối các thao tác liên dịch vụ.
- Stack xuất hiện thường xuyên trong **sample** gợi ý vùng cần quan sát; số sample không trực tiếp bằng số lần method được gọi.

### 3.4. Thread và payload có vai trò gì?

`eventThread`/`RecordedEvent.getThread()` chỉ ra thread gắn với lần ghi event nếu được thu; event type cũng có field nghiệp vụ riêng như `bytesRead`, `duration`, địa chỉ, loại GC, số lượng object, operation ID. Một event JFR có thể thiếu một số field, nên không áp một schema cố định cho mọi type/JDK.

Với **virtual threads**, tên thread và carrier thread có thể thay đổi theo thời điểm; không suy ra quan hệ cố định “một virtual thread = một platform thread” chỉ từ một event. Nếu ghép sự kiện của một request, cần khóa tương quan nghiệp vụ đáng tin cậy (ví dụ request ID) nếu ứng dụng đã chủ động ghi.

## 4. Quan hệ giữa bốn thành phần trong một timeline

Cho ba event giả định:

| Sự kiện | Start time | Duration | End time | Stack (nếu được thu) gợi ý |
| --- | --- | --- | --- | --- |
| `app.Request` | 10:00:00.000 | 120 ms | 10:00:00.120 | Vị trí `commit` ở mã xử lý request |
| `jdk.SocketRead` | 10:00:00.020 | 70 ms | 10:00:00.090 | Call path đến thao tác đọc |
| `app.Checkpoint` | 10:00:00.100 | 0 ms | 10:00:00.100 | Vị trí phát event mốc |

```text
10:00:00.000                    .020             .090   .100    .120
    |---------------------------|----------------|------|-------|
Request: [======================================================]
Socket :                             [====================]
Checkpoint:                                               *
```

Đây là **ví dụ diễn giải timeline**, không phải kết quả thật của một JVM. Có thể nói socket read diễn ra **trong khoảng** request, nhưng để khẳng định chúng thuộc **cùng request**, phải có correlation từ thread/context, mã hoặc tracing. Chỉ trùng thời gian trên JVM nhiều request **không đủ**.

Dữ liệu giải quyết các câu hỏi khác nhau:

- **What?** `eventType` và payload.
- **When?** `startTime`, `endTime`.
- **How long?** `duration` nếu event có ý nghĩa khoảng thời gian.
- **Where in code?** `stackTrace` nếu được ghi, cộng với event thread.
- **Why?** Phải kết hợp context, log, threshold, JFR event khác và thử nghiệm; một event đơn lẻ không tự chứng minh root cause.

Một sự kiện duration không nhất thiết ghi hai record start/end riêng; thông thường **một record event** chứa thông tin thời gian đo cả khoảng.

## 5. Thu recording JFR từ một JVM đang chạy bằng `jcmd`

Cần **JDK 17+** có `jcmd` và `jfr`, JVM đích đang chạy, có quyền attach hợp lệ. Để tìm đúng tiến trình:

```bash
jcmd -l
jcmd 12345 help JFR.start
```

`12345` là **PID minh họa**, thay bằng PID JVM thật. Tên option và khả năng theo JDK nên xem bằng `jcmd <PID> help JFR.start`, `help JFR.dump`, `help JFR.stop`.

### Cách A: ghi liên tục rồi tự dump khi cần

```bash
# Khởi động recording có tên, cấu hình ít overhead hơn:
jcmd 12345 JFR.start name=runtime-check settings=default

# Xem recording đang hoạt động:
jcmd 12345 JFR.check

# Tạo file .jfr snapshot của recording đang chạy:
jcmd 12345 JFR.dump name=runtime-check filename=/tmp/runtime-check.jfr

# Khi đã đủ dữ liệu, dừng recording:
jcmd 12345 JFR.stop name=runtime-check
```

- `settings=default` dùng cấu hình JDK được thiết kế cho chi phí thấp; `settings=profile` thường ghi nhiều hơn và nên dùng trong thời gian ngắn khi cần phân tích sâu.
- `JFR.dump` **ghi dữ liệu hiện có ra file nhưng recording tiếp tục chạy**. Không nhầm với `JFR.stop`.
- Đường dẫn `filename` của `JFR.dump` được thực thi **từ JVM đích**. Nếu JVM chạy trong container, file `/tmp/runtime-check.jfr` nằm trong filesystem mà **container JVM** nhìn thấy.
- Dữ liệu thu được phụ thuộc khoảng thời gian recording chạy. Nếu chưa có hoạt động hoặc event bị lọc, file có thể không chứa loại sự kiện bạn tìm.
- Khi cần nhiều snapshot, dùng file tên khác để tránh ghi đè kết quả cũ.

### Cách B: recording tự kết thúc sau thời gian xác định

```bash
jcmd 12345 JFR.start name=short-profile settings=profile duration=60s filename=/tmp/short-profile.jfr
```

Khi đủ thời lượng, JVM dừng recording và lưu file theo cấu hình. Đừng tìm file ngay lúc câu lệnh start trả về mà cho rằng đã thu đủ 60 giây. Tài liệu JFR mô tả thời lượng `duration`, thư mục, tên file và ảnh hưởng của setting; phải kiểm tra trạng thái/file thực tế sau khi hoàn thành.

**Quyền và nguồn lực:** cần đúng user/PID namespace; container tối giản có thể thiếu `jcmd`. JFR tạo dữ liệu nhạy cảm như class/method, đường dẫn và thông tin runtime. Chọn vị trí lưu, thời lượng, quyền truy cập, chính sách lưu trữ phù hợp. Không bật hàng loạt sự kiện rất nhiều stack trace ở tần suất cao mà không đo overhead.

## 6. Dùng `jfr` đọc tên event, timestamp, duration và stack

Giả sử file `runtime-check.jfr` đã có trên máy bạn đang chạy bộ JDK tools (có thể cần sao chép file ra khỏi container trước).

```bash
# Thống kê loại event và số lượng mẫu:
jfr summary runtime-check.jfr

# In event JVM có ghi trong file:
jfr print --events jdk.GarbageCollection runtime-check.jfr

# Tập trung vào I/O, hiển thị nhiều frame hơn nếu file có stack:
jfr print --events jdk.SocketRead,jdk.SocketWrite --stack-depth 12 runtime-check.jfr

# Xuất các event được chọn dưới dạng JSON cho công cụ phân tích:
jfr print --json --events jdk.SocketRead runtime-check.jfr
```

`jfr summary` giúp biết event nào **thực sự có trong recording** và số lượng của chúng. `jfr print` có thể lọc theo tên type hoặc category và tăng số frame được hiển thị với `--stack-depth`. Tùy event/recording mà output có thể không có field stack trace. Tùy chọn `--json` thay đổi **cách in**, không biến recording nhị phân ban đầu thành một schema bất biến giữa mọi JDK.

Khi mở bằng **Java Mission Control**, có thể xem các sự kiện trên timeline, lọc theo thời gian/loại/thread, xem duration và stack nếu có. Cách tiếp cận hiệu quả là kiểm tra **event type và count** trước, sau đó đặt duration và stack vào cùng thời điểm với load/GC/log để hiểu ý nghĩa.

### Đọc event bằng API thay vì parse văn bản

Thư viện JDK `jdk.jfr.consumer.RecordingFile` có các hàm:

```java
RecordedEvent event = recordingFile.readEvent();
Instant startedAt = event.getStartTime();
Instant endedAt = event.getEndTime();
Duration elapsed = event.getDuration();
RecordedStackTrace trace = event.getStackTrace();
```

Đây chỉ là **đoạn minh họa trong ngữ cảnh một `RecordingFile` đã mở**; chương trình hoàn chỉnh và chạy được nằm ở mục 7. Nếu file lớn, đọc từng event bằng `hasMoreEvents()`/`readEvent()` thay vì `RecordingFile.readAllEvents()` để tránh giữ toàn bộ event trong bộ nhớ.

## 7. Thực hành Java 17+: tự tạo hai loại event và kiểm tra bốn thành phần

Bài này tạo **một duration event** và **một instant event** rồi đọc lại từ file `.jfr`, giúp thấy quan hệ time/duration/stack mà không phụ thuộc vào việc một network call hay GC có xảy ra hay không.

Tạo file **`JfrTimelineDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrTimelineDemo {
    @Name("demo.Task")
    @Label("Demo timed task")
    @Category({"Demo", "Learning"})
    static class TaskEvent extends Event {
        @Label("Operation")
        String operation;
    }

    @Name("demo.Checkpoint")
    @Label("Demo checkpoint")
    @Category({"Demo", "Learning"})
    static class CheckpointEvent extends Event {
        @Label("Message")
        String message;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-timeline-demo.jfr").toAbsolutePath();

        try (Recording recording = new Recording()) {
            recording.enable(TaskEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable(CheckpointEvent.class)
                    .withStackTrace();

            recording.start();

            TaskEvent task = new TaskEvent();
            task.operation = "simulate-wait";
            task.begin();
            Thread.sleep(80);
            task.end();
            task.commit();

            CheckpointEvent checkpoint = new CheckpointEvent();
            checkpoint.message = "after-task";
            checkpoint.commit();

            recording.stop();
            recording.dump(file);
        }

        int customEvents = 0;
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                String type = event.getEventType().getName();

                if (!type.equals("demo.Task")
                        && !type.equals("demo.Checkpoint")) {
                    continue;
                }

                customEvents++;
                System.out.println("event=" + type);
                System.out.println("start=" + event.getStartTime());
                System.out.println("end=" + event.getEndTime());
                System.out.println(
                        "durationMs=" + event.getDuration().toMillis());
                System.out.println(
                        "stackPresent=" + (event.getStackTrace() != null));
            }
        }

        System.out.println("customEvents=" + customEvents);
        System.out.println("file=" + file.getFileName());
    }
}
```

Biên dịch và chạy ở thư mục chứa file (không cần dependency Maven/Gradle nào):

```bash
javac --release 17 JfrTimelineDemo.java
java JfrTimelineDemo
```

Kết quả có thể kiểm tra chắc chắn ở **hai dòng cuối**:

```text
customEvents=2
file=jfr-timeline-demo.jfr
```

Các dòng `event`, `start`, `end`, `durationMs`, `stackPresent` đứng trước hai dòng cuối **phụ thuộc thời điểm và cấu hình thực thi**. Bạn sẽ thấy hai event có type `demo.Task` và `demo.Checkpoint` (không nên mặc định mọi bản JDK sắp xếp chúng cùng thứ tự khi duyệt file). `demo.Task` có thời lượng xấp xỉ hoặc lớn hơn 80 ms vì `Thread.sleep(80)` có thể chờ scheduler thêm; `demo.Checkpoint` gọi `commit()` trực tiếp không `begin()` nên thể hiện mốc tức thời với duration bằng 0. `stackPresent` thường là `true` do cấu hình `.withStackTrace()`.

Đọc file vừa tạo:

```bash
jfr summary jfr-timeline-demo.jfr
jfr print --events demo.Task,demo.Checkpoint --stack-depth 12 jfr-timeline-demo.jfr
```

**Giải thích vì sao ví dụ hoạt động:**

- `TaskEvent` và `CheckpointEvent` đều kế thừa `jdk.jfr.Event`; `@Name` đặt tên type để lọc, `@Category` là metadata phân nhóm, các field `operation`/`message` là **payload**.
- `recording.enable(...).withThreshold(Duration.ZERO).withStackTrace()` bật event, không loại duration event ngắn vì threshold, và yêu cầu lấy stack tại commit.
- `task.begin()` trước sleep, `task.end()` sau sleep: duration phản ánh **thời gian trôi qua** giữa hai mốc, kể cả thời gian thread chờ; **không đo CPU time**.
- `task.commit()` ghi event cùng payload và dữ liệu thời gian; stack là vị trí commit trong `main`, không phải toàn bộ 80 ms thực thi.
- `checkpoint.commit()` không có cặp `begin()`/`end()`: mô hình instant event.
- `recording.stop()` đóng khoảng recording; `recording.dump(file)` lưu dữ liệu ra `.jfr` trước khi đóng recording resource.
- `RecordingFile` duyệt nhiều event, kể cả event hệ thống nếu có; ta chỉ in những type bắt đầu bằng `demo.` đã được định danh chính xác.

**Bài tập mở rộng:** đổi `withThreshold(Duration.ZERO)` của `demo.Task` thành `withThreshold(Duration.ofMillis(200))`, giữ sleep khoảng 80 ms, chạy lại từ đầu bằng file mới/tên mới. Duration event đó thường **không được ghi** vì ngắn hơn threshold; `customEvents` thường còn 1. Hiện tượng này minh họa vì sao không tìm thấy một event **không chứng minh** thao tác chưa xảy ra.

## 8. Ghép event với timestamp, duration và stack để điều tra một vấn đề

Giả sử latency request tăng bất thường. Tiến hành theo chuỗi có thể kiểm chứng:

1. **Chọn khoảng thời gian lỗi thực tế.** Ghi timestamp của request từ log, múi giờ, PID, workload và thời gian recording bao phủ.
2. **Kiểm tra recording có event cần thiết:** `jfr summary`; nếu thiếu `jdk.SocketRead` hoặc `jdk.JavaMonitorEnter`, xem cấu hình profile/threshold thay vì suy rằng không có I/O/lock.
3. **Lọc event theo khung thời gian và thread.** Một JVM xử lý nhiều request đồng thời; cần mối nối vững chắc như request ID trong event ứng dụng, context, hoặc trace, nếu muốn quy sự kiện cho một request.
4. **Đọc cả `startTime` và `duration`.** Một socket read 300 ms bên trong request 500 ms có thể là thành phần đáng kể; nhưng phải kiểm tra operation thực sự và sự kiện liên quan. Event `jdk.ExecutionSample` chỉ là mẫu, không đại diện độ dài thao tác.
5. **Mở stack trace đúng ngữ nghĩa.** Với event I/O/chờ, stack gợi ý gọi từ đâu; với event sample, stack ở thời điểm lấy mẫu; với custom event stack ở commit. Có thể cần nhiều event để xác định nguyên nhân.
6. **Đối chiếu GC/CPU/lock/metrics.** GC pause hoặc CPU nóng có thể nằm cùng thời điểm I/O chậm, nhưng trùng thời gian chưa đủ để chứng minh quan hệ nhân quả.
7. **Thu thêm bằng chứng có kiểm soát:** so sánh các recording, điều chỉnh threshold hoặc event settings có mục tiêu, tránh bật toàn bộ event với mọi stack vô thời hạn.

### Ví dụ phân biệt kết luận hợp lệ và kết luận vội

| Dữ liệu trong JFR | Có thể kết luận | Chưa được phép kết luận |
| --- | --- | --- |
| `jdk.SocketRead` duration 250 ms | Một thao tác read được đo khoảng 250 ms. | CPU chạy 250 ms hoặc toàn request chỉ tốn 250 ms. |
| `jdk.ExecutionSample` lặp nhiều ở một stack | Stack được lấy mẫu thường xuyên trong khung recording, có thể cần phân tích CPU. | Method được gọi chính xác bằng số sample hoặc dùng CPU đúng thời gian giữa hai sample. |
| `jdk.JavaMonitorEnter` có duration dài | Có trường hợp chờ monitor đủ dài để JFR ghi. | Toàn bộ hệ thống deadlock hoặc thread bị BLOCKED mãi mãi. |
| `jdk.CPULoad` CPU tăng | Mức CPU quan sát được cao trong kỳ đo. | Một class cụ thể gây CPU cao nếu chưa đối chiếu stack/sample. |
| `RecordedEvent.getStackTrace() == null` | Recording không có stack trace cho event đó. | JVM không chạy Java code hoặc không có call stack. |
| Không thấy event có duration 2 ms | Event không có trong dữ liệu ghi. | Không có thao tác 2 ms: có thể đã bị threshold lọc. |

## 9. Các setting quyết định bạn nhìn thấy gì

Các setting phổ biến theo JDK JFR gồm:

| Setting | Ý nghĩa | Ảnh hưởng đến cách đọc |
| --- | --- | --- |
| `enabled` | Bật/tắt ghi một event type. | Type bị tắt không có instance được ghi. |
| `threshold` | Chỉ ghi duration event đạt ngưỡng thời gian. | Event ngắn có thể không hiện, khiến phân bố duration **bị lệch về các thao tác dài**. |
| `stackTrace` | Yêu cầu stack trace cho event nếu có thể. | Bật có thêm ngữ cảnh nhưng tăng dữ liệu/overhead; tắt hoặc thiếu thì API trả `null`. |
| `period` | Chu kỳ phát event định kỳ. | Ít mẫu hơn không có nghĩa hiện tượng biến mất. |
| Event sampling / profile | Tần suất và nhóm event được lấy mẫu/ghi. | Số sample không phải số lần method chạy. |

Hai cấu hình JDK thường dùng:

- **`default.jfc`** (hoặc `settings=default`): tập event và mức overhead phù hợp ghi lâu hơn.
- **`profile.jfc`** (hoặc `settings=profile`): thu thêm thông tin cho phân tích chuyên sâu, overhead cao hơn; dùng có giới hạn và đo tác động.

JFR không luôn thu **mọi stack**, **mọi allocation**, **mọi exception** hay **mọi lệnh I/O**. Trước khi nói “không có vấn đề”, hãy xác minh **event type có enable không, threshold bao nhiêu, recording bắt đầu/kết thúc lúc nào**.

## 10. Các nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Timestamp của event là lúc file `.jfr` được ghi.” | Event timestamp biểu thị thời điểm hoạt động được quan sát; buffer/dump có thể ghi file muộn. |
| “Event có duration dài tức là CPU-bound.” | Duration thường là elapsed time; có thể bao gồm chờ I/O/lock/scheduler. |
| “Event type là một lần phát sinh duy nhất.” | Một type có nhiều event instance; phân biệt type metadata với event record cụ thể. |
| “JFR ghi mọi lời gọi hàm Java.” | JFR chọn event theo settings, threshold và sampling; không tự ghi mọi method call. |
| “Stack trong duration event thể hiện toàn bộ quá trình chạy.” | Stack thường phản ánh điểm ghi/commit hoặc sampling, không chứa cả chuỗi trạng thái theo thời gian. |
| “Không có stack = không có code Java.” | Stack có thể bị tắt/không có trong recording/truncate. |
| “`jfr print --stack-depth 100` phục hồi stack đầy đủ.” | Chỉ tăng số frame **hiển thị nếu đã ghi đủ frame**; không lấy lại phần chưa thu. |
| “Hai event gần timestamp chắc chắn thuộc cùng request.” | Cần thread/context/correlation và kiểm tra concurrency; chỉ trùng thời gian không đủ. |
| “`JFR.dump` dừng recording.” | `JFR.dump` ghi snapshot trong khi recording có thể tiếp tục; `JFR.stop` là lệnh dừng. |
| “Duration 0 là event lỗi.” | Instant event hợp lệ có duration bằng 0. |

## 11. Câu hỏi tự kiểm tra

1. **JFR event khác event type ở điểm nào?** Event type là **schema/loại**; event là một bản ghi đã xảy ra mang type, time và field cụ thể.
2. **`startTime` và `endTime` của instant event như thế nào?** Bằng nhau, `duration = 0`.
3. **Duration của `jdk.SocketRead` có phải thời gian CPU?** Không. Nó là thời gian thao tác được đo, có thể bao gồm thời gian chờ I/O.
4. **Vì sao một thao tác chậm có thể không có trong JFR?** Recording không bao trùm thời điểm, event disabled, threshold, sampling, cấu hình event hoặc JVM/JDK không hỗ trợ event đó.
5. **Stack trace trong custom JFR event nằm ở thời điểm nào?** Thường được thu khi gọi `Event.commit()` nếu `stackTrace` enabled.
6. **JFR có tự liên kết hai event ở cùng timestamp thành một request không?** Không. Cần correlation ID, ngữ cảnh thread hoặc thông tin tracing có cơ sở.
7. **Nếu muốn biết file có bao nhiêu `jdk.SocketRead` nên chạy lệnh gì trước?** `jfr summary recording.jfr`, rồi `jfr print --events jdk.SocketRead recording.jfr` để xem chi tiết.
8. **Sự kiện `jdk.ExecutionSample` được đọc thế nào?** Là điểm lấy mẫu stack theo cơ chế sampling; không quy mỗi sample thành một method call hay duration.

## Tài liệu tham khảo

- [Oracle JDK 21 — JFR API, package `jdk.jfr`, các setting và định nghĩa event](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Oracle JDK 21 — `jdk.jfr.Event` (`begin`, `end`, `commit`, `shouldCommit`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Oracle JDK 21 — `RecordedEvent` (`getStartTime`, `getEndTime`, `getDuration`, `getStackTrace`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [Oracle JDK 21 — `jcmd` (`JFR.start`, `JFR.dump`, `JFR.check`, `JFR.stop`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr` (`summary`, `print`, `--events`, `--stack-depth`, `--json`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — `RecordingFile` và cách duyệt file lớn](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
