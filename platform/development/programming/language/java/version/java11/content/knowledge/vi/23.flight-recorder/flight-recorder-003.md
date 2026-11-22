# Event, recording, chunk và repository trong Java Flight Recorder (Java 11+)

## 1. Vì sao JFR cần cả bốn khái niệm?

**Java Flight Recorder (JFR)** là công cụ giám sát và chẩn đoán tích hợp vào JVM. Với **Java 11**, OpenJDK đã có JFR như một tính năng chính thức theo **JEP 328**. API `jdk.jfr` cho phép tạo sự kiện từ ứng dụng, cấu hình phiên ghi và xuất dữ liệu. Công cụ `jcmd`, `jfr` và JDK Mission Control hỗ trợ vận hành và phân tích.

Một luồng dữ liệu JFR có thể hình dung như sau:

```text
JVM (GC, threads, I/O, CPU samples...)     Ứng dụng (Event.commit())
             |                                      |
             +------------ EVENT ------------------+
                               |
                     Event settings / filters
                               |
                     JFR buffers / recorder
                               |
             +-----------------+------------------+
             |                                    |
       disk=false                           disk=true
   dữ liệu trong buffers           ghi/rotate CHUNKS ở REPOSITORY
             |                                    |
             +-----------------+------------------+
                               |
                   RECORDING: chọn event,
                  thời gian và retention
                               |
                 dump / setDestination / jcmd
                               |
                         output.jfr
                               |
                      jfr / RecordingFile
```

Bốn khái niệm không cùng cấp độ:

| Khái niệm | Định nghĩa | Vai trò |
| --- | --- | --- |
| **Event** | Một bản ghi có kiểu, thời gian, trường dữ liệu và có thể có duration/stack trace | Quan sát một hiện tượng đã xảy ra |
| **Recording** | Phiên thu thập **logic**, có ID, settings, vòng đời và retention | Quyết định thu event nào, giữ bao lâu, xuất khi nào |
| **Chunk** | Đơn vị dữ liệu **JFR nhị phân**, chứa events và thông tin phụ trợ cần để giải mã | Cho phép lưu/luân phiên, đọc và ghép dữ liệu |
| **Repository** | Kho **tạm** do JVM quản lý, chứa chunks của JFR khi ghi disk | Giữ lịch sử trước khi xuất file `.jfr` |

**Đừng nhầm:** `Event.commit()` không tạo riêng một file; một chunk chứa nhiều events; một recording có thể bao trùm nhiều chunks; repository không phải file `.jfr` mà người vận hành mang đi phân tích. Một JVM có thể chạy nhiều recordings đồng thời mà không cần một repository hoàn toàn riêng cho từng recording.

JFR là hệ thống **observability/profiling**, không phải durable audit log. Event có thể bị lọc, mất do áp lực buffers, giới hạn thời gian/lưu trữ hoặc crash. Dữ liệu quan trọng bắt buộc ghi bền vững cần hệ thống nhật ký/giao dịch thích hợp.

## 2. Event: type, instance, metadata và thời điểm ghi

Java 11 có `jdk.jfr.Event`, một class cơ sở để viết **custom event**; JDK cũng cung cấp nhiều built-in event types (GC, threads, I/O, sampling...) tùy phiên bản và cấu hình.

Ví dụ khai báo:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.Step")
@Label("Business Step")
class StepEvent extends Event {
    @Label("Operation")
    String operation;
    @Label("Item Count")
    int items;
}
```

Đây là **class minh họa**, chưa có `main`. Một event instance chỉ trở thành ứng viên để ghi khi ứng dụng gọi `commit()`:

```java
StepEvent e = new StepEvent();
e.operation = "validate";
e.items = 3;
e.begin();
try {
    // Công việc cần đo thời lượng.
} finally {
    e.end();
    e.commit();
}
```

**Cơ chế:**

- `new StepEvent()` chỉ tạo đối tượng Java; **chưa có bản ghi trong repository**.
- `begin()` đánh dấu thời điểm bắt đầu; `end()` kết thúc duration. Event tức thời có thể gọi `commit()` mà không `begin/end`.
- `commit()` yêu cầu JFR ghi event vào pipeline, **không bảo đảm** event được lưu nếu event type bị tắt, duration không đạt `threshold` hoặc buffers thiếu khả năng giữ lại.
- `@Name`, `@Label`, `@Description`, `@Category`, `@Timespan`... là **metadata**, giúp mô tả và hiển thị event type. Chúng không phải một lần ghi event.
- Trường event hỗ trợ Java primitives và các reference types được JFR cho phép như `String`, `Thread`, `Class`. Field có kiểu array, enum hoặc object bất kỳ **không tự được tuần tự hóa thành field JFR**; cần thiết kế dữ liệu được hỗ trợ.

**`isEnabled()`** cho biết ít nhất một recording có bật event type. **`shouldCommit()`** còn xét threshold/duration, hữu ích để không thu thập field đắt tiền cho event chắc chắn không được ghi:

```java
StepEvent e = new StepEvent();
e.begin();
// ... thao tác nghiệp vụ ...
e.end();
if (e.shouldCommit()) {
    e.operation = "validate"; // Có thể gắn thêm metadata tốn kém.
    e.items = 3;
    e.commit();
}
```

Hai đoạn code trên là minh họa cần đặt trong ngữ cảnh có `StepEvent`; bài runnable đầy đủ ở mục 6 sẽ có file và lệnh chạy. **Không dùng JFR làm nơi chứa mật khẩu, access token hay thông tin nhạy cảm nguyên văn**; một file recording có thể được các công cụ chẩn đoán trích xuất.

### Event settings: lọc trước khi ghi

| Setting | Ví dụ | Tác dụng |
| --- | --- | --- |
| `enabled` | `true` / `false` | Bật hoặc tắt một event type trong recording |
| `threshold` | `0` / `10 ms` | Chỉ giữ events có thời lượng đạt ngưỡng |
| `stackTrace` | `true` / `false` | Có thu stack trace hay không; ảnh hưởng kích thước/overhead |
| `period` | `20 ms` / `everyChunk` | Chu kỳ phát một số loại events định kỳ |

Ví dụ API Java 11:

```java
recording.enable(StepEvent.class)
         .withThreshold(Duration.ofMillis(5))
         .withoutStackTrace();
```

Đây là **đoạn minh họa** với biến `recording` kiểu `Recording` và import `Duration`. Nếu một event có duration 1 ms trong khi threshold là 5 ms, nó có thể không xuất hiện trong recording đó dù `commit()` được gọi.

Một **event type** không đồng nghĩa với một **event instance**: metadata `demo.Step` mô tả kiểu dữ liệu, còn mỗi lần `commit()` có thể đóng góp một instance riêng nếu settings cho phép.

## 3. Recording: phiên ghi logic, không phải một file hay một chunk

`jdk.jfr.Recording` implements `AutoCloseable`. Khi tạo một recording, ứng dụng có thể cấu hình **event settings**, tên, disk/memory mode, độ tuổi/dung lượng giữ lại và cách xuất. Ví dụ:

```java
try (Recording recording = new Recording()) {
    recording.setName("app-diagnostics");
    recording.setToDisk(true);
    recording.enable(StepEvent.class).withThreshold(Duration.ZERO);
    recording.start();
    // Ứng dụng phát event tại đây.
    recording.stop();
    recording.dump(Path.of("diagnostics.jfr"));
}
```

Đoạn này minh họa API (cần `StepEvent`, import `Recording`, `Duration`, `Path` và xử lý checked exceptions). `try-with-resources` bảo đảm giải phóng dữ liệu gắn với recording.

**Vòng đời phổ biến:**

| State | Ý nghĩa |
| --- | --- |
| `NEW` | Recording mới được tạo, chưa bắt đầu |
| `DELAYED` | Đã `scheduleStart(delay)`, chờ thời điểm bắt đầu |
| `RUNNING` | Đang thu thập các events được bật |
| `STOPPED` | Đã kết thúc thu, dữ liệu có thể còn để dump |
| `CLOSED` | Đã giải phóng dữ liệu/tài nguyên liên quan |

`start()` bắt đầu phiên ghi; `stop()` dừng thu và **không thể start lại cùng recording**. `close()` dọn tài nguyên và khiến dữ liệu chưa xuất không còn khả dụng; do đó cần dump **trước khi** close nếu muốn lưu.

**Phân biệt các thao tác quan trọng:**

- `recording.dump(path)` **xuất dữ liệu recording thành file `.jfr`**. Có thể gọi khi recording đã bắt đầu, **không nhất thiết phải stop trước**; cho phép lấy snapshot của phiên chạy dài.
- `recording.setDestination(path)` cấu hình file sẽ ghi khi recording **stop**. Đây không phải repository. Khi data được copy thành công, recording có quy tắc tự đóng.
- `recording.getState()` trả state, `getId()` và `getName()` giúp phân biệt recordings.
- `recording.setDumpOnExit(true)` bật dump khi JVM thoát theo điều kiện hỗ trợ, **không phải bảo đảm dữ liệu đầy đủ nếu máy mất điện/crash cứng**.
- `Recording.getSize()` đo dữ liệu của recording trong **disk repository**, không đo số byte của mọi sự kiện JVM từ lúc khởi động; với recording không ghi disk, giá trị là 0.

**Có thể có nhiều recording cùng chạy:** ví dụ recording lâu dài dùng `default.jfc`, một recording chẩn đoán ngắn dùng `profile.jfc`. JFR có hệ thống thu events chung, còn mỗi recording có settings và retention logic riêng. Đừng nghĩ JVM bắt buộc tạo một thread hoặc file chứa riêng mọi event cho từng recording.

### Event settings và recording options khác nhau

**Event settings** (`enabled`, `threshold`, `stackTrace`, `period`) quyết định **thu loại dữ liệu nào**. **Recording options** (`disk`, `duration`, `maxage`, `maxsize`, `filename`) quyết định **cách giữ, giới hạn và xuất** dữ liệu.

JDK có `Configuration.getConfiguration("default")` và `"profile"`: `default` hướng đến quan sát chi phí thấp trong thời gian dài; `profile` thường chi tiết hơn và có overhead cao hơn. Không chọn `profile` liên tục trên mọi workload mà không đo overhead và dung lượng.

## 4. Chunk: đơn vị dữ liệu ghi/rotate, khác ranh giới recording

**Chunk** là một đơn vị nhị phân JFR chứa **events, metadata và những constant pools/thông tin phụ trợ** cần để công cụ phân tích đọc được. JVM chuyển dữ liệu từ buffers sang chunks, và có thể luân phiên chunks khi hệ thống ghi kéo dài.

```text
Trong disk repository (minh họa):
    chunk A: đã hoàn tất
    chunk B: đã hoàn tất
    chunk C: đang ghi
               |
         Recording.dump(...)
               |
               v
       output.jfr có thể gồm
         chunk A + chunk B + ...
```

**Những điều phải nhớ:**

1. **Không có quan hệ 1:1** giữa event và chunk: một chunk chứa nhiều events, và nhiều recording có thể bao trùm những thời kỳ/chunks liên quan.
2. **File `.jfr` có thể chứa nhiều chunks** theo thứ tự thời gian, không phải mỗi chunk đều là một file người dùng cần tự ghép.
3. **Retention thường làm việc theo đơn vị chunk**: khi độ tuổi hoặc kích thước vượt giới hạn, JVM có thể loại chunk cũ. Không suy ra `maxage=30m` sẽ cắt chính xác từng event ở mức nanosecond.
4. **Kích thước và thời điểm quay vòng** phụ thuộc lượng events, JFR options và implementation; không viết assertion “mỗi 12 MB chắc chắn có một chunk đúng bằng 12 MB”.
5. **Dữ liệu chưa flush/unfinished chunk có thể bị mất khi crash**. Công cụ `jfr assemble` có thể ghép những chunk hoàn tất còn nguyên; các phần `.part` chưa hoàn thành có thể bị bỏ qua. Repository không thay thế backup.

Ở HotSpot, `-XX:FlightRecorderOptions=maxchunksize=...` điều chỉnh **kích thước chunk**, trong khi `Recording.setMaxSize(...)` điều chỉnh **lượng dữ liệu giữ cho recording**. Đó là hai giới hạn khác nhau. Khi đặt maxsize quá nhỏ so với maxchunksize, có thể gặp lỗi cấu hình hoặc retention không thể thỏa mãn kỳ vọng. Chọn các giá trị tương thích và đo bằng dữ liệu thực.

## 5. Repository: kho tạm của JVM, không phải `incident.jfr`

Khi `disk=true`, JFR sử dụng **repository tạm** để ghi chunks. Trên JVM HotSpot, vị trí mặc định thường lấy từ vùng temporary của hệ thống và có thể cấu hình bằng JVM option khi khởi chạy:

```bash
java -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository MyApplication
```

**Đây là lệnh minh họa** cho hệ điều hành Unix. `MyApplication` là class ứng dụng giả định; cần tạo/chọn thư mục phù hợp, có quyền ghi, đủ dung lượng và chính sách bảo mật. Không mặc định mọi JVM/provider đều hỗ trợ cùng flags HotSpot.

| Repository | File `.jfr` xuất |
| --- | --- |
| Kho **tạm** do JFR/JVM quản lý | File được `dump`/`setDestination`/`jcmd` tạo ra |
| Có thể chứa nhiều chunks, có file đang ghi | Có thể chứa một hoặc nhiều chunks đã được đóng gói |
| Chunks có thể bị quay vòng/xóa theo policy JFR | File tồn tại theo chính sách lưu/xóa của ứng dụng/ops |
| Không có API chuẩn để ứng dụng tùy tiện sửa từng chunk | Đọc bằng `jfr`, `RecordingFile` hoặc công cụ phân tích |
| Dùng trong thời gian JVM còn ghi/giữ dữ liệu | Đưa vào báo cáo sự cố hoặc storage phân tích độc lập |

**Không được xóa tay file trong repository mà JVM đang sử dụng.** Điều này có thể làm hỏng recording hoặc khiến dump thất bại. Khi muốn giới hạn dung lượng, dùng `maxage`/`maxsize` và policy hệ thống, không can thiệp thủ công vào các chunk đang được ghi.

### Disk mode so với memory mode

- `Recording.setToDisk(true)`: JFR flush dữ liệu xuống disk repository trong quá trình recording, phù hợp khi cần **lịch sử dài** và có nguồn lưu trữ đủ.
- `Recording.setToDisk(false)`: dữ liệu bị giới hạn bởi **bộ đệm bộ nhớ** có sẵn; có thể không giữ đủ lịch sử dưới tải cao. Chế độ này không biến `maxage`/`maxsize` thành kho lưu bền vững.
- `isToDisk()` cho biết mode. Trong Java 11 `Recording`, giá trị mặc định của `isToDisk()` là `true` nếu không đặt; bài demo vẫn cấu hình tường minh để người học nhận biết.
- **JFR không bảo đảm event lossless**: trong mọi mode, có thể mất sự kiện do áp lực buffers hoặc cấu hình filtering. Nếu nghiệp vụ đòi audit không mất thông tin, dùng kênh lưu bền vững riêng.

### Retention: `maxage` và `maxsize`

```java
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(30));
recording.setMaxSize(128L * 1024 * 1024);
```

Đây là **đoạn minh họa**, không phải class chạy độc lập. `setMaxAge` giới hạn **độ tuổi lịch sử** trong disk repository, `setMaxSize` giới hạn **số byte dữ liệu được giữ**. Khi cần tạo chỗ cho dữ liệu mới, JVM loại chunk cũ.

- `setMaxAge(null)` nghĩa là **không đặt giới hạn tuổi**.
- `setMaxSize(0)` nghĩa là **không đặt giới hạn dung lượng**.
- Nếu không đặt cả hai, dữ liệu disk có thể **tăng không giới hạn** cho tới khi filesystem hoặc điều kiện khác giới hạn.
- Cần chọn cửa sổ lịch sử và dung lượng phù hợp SLO/production; việc remove chunks có thể làm một recording chỉ giữ phần gần nhất khi dump.
- Với container có filesystem tạm nhỏ, cạn disk có thể ảnh hưởng JFR và ứng dụng. Dọn output `.jfr` riêng theo policy, vì retention repository không tự xóa mọi file đã xuất.

## 6. Ví dụ Java 11 chạy được: custom Event → Recording → dump → RecordingFile

Chương trình này chạy **không cần mạng**. Nó tạo ba custom events, ghi một disk recording có retention, stop, dump ra file `.jfr` trong thư mục temporary, đọc lại riêng event `demo.BatchStep` rồi dọn tài nguyên.

Lưu thành **`JfrEventRecordingDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.TreeMap;

public class JfrEventRecordingDemo {
    @Name("demo.BatchStep")
    static class BatchStep extends Event {
        String task;
        int step;
    }

    public static void main(String[] args) throws Exception {
        Path temporary = Files.createTempDirectory("jfr-learning-");
        Path output = temporary.resolve("example.jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.setName("chapter-demo");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(5));
                recording.setMaxSize(32L * 1024 * 1024);
                recording.enable(BatchStep.class).withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();

                for (int i = 1; i <= 3; i++) {
                    BatchStep e = new BatchStep();
                    e.task = "part-" + i;
                    e.step = i;
                    e.begin();
                    e.end();
                    e.commit();
                }

                recording.stop();
                System.out.println("stateAfterStop=" + recording.getState());
                System.out.println("diskMode=" + recording.isToDisk());
                recording.dump(output);
            }

            Map<Integer, String> steps = new TreeMap<>();
            try (RecordingFile file = new RecordingFile(output)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();
                    if (event.getEventType().getName().equals("demo.BatchStep")) {
                        steps.put(event.getInt("step"), event.getString("task"));
                    }
                }
            }

            System.out.println("jfrFileExists=" + Files.isRegularFile(output));
            System.out.println("customEventCount=" + steps.size());
            for (Map.Entry<Integer, String> item : steps.entrySet()) {
                System.out.println(item.getKey() + "=" + item.getValue());
            }
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(temporary);
        }
    }
}
```

**Biên dịch và chạy** trên JDK 11 trở lên (JDK 17+ cũng phù hợp). `--release 11` giúp xác nhận code không dùng API được bổ sung sau Java 11:

```bash
javac --release 11 JfrEventRecordingDemo.java
java JfrEventRecordingDemo
```

**Stdout chính xác trên JVM có JFR khả dụng và quyền ghi temporary directory:**

```text
stateAfterStop=STOPPED
diskMode=true
jfrFileExists=true
customEventCount=3
1=part-1
2=part-2
3=part-3
```

**Đã kiểm thử thực tế:** biên dịch bằng `javac --release 11` và chạy bằng OpenJDK 24 cho đúng 7 dòng stdout như trên. Trong môi trường không hỗ trợ JFR, không có module `jdk.jfr` hoặc bị chặn ghi file tạm, chương trình sẽ cần môi trường chạy thích hợp; có thể kiểm tra `FlightRecorder.isAvailable()` từ Java 11.

**Tại sao kết quả ổn định?**

1. `new Recording()` tạo phiên ghi, nhưng chưa ghi event. `enable(BatchStep.class)` bật type mà chương trình quan tâm.
2. `withThreshold(Duration.ZERO)` cho phép những event duration rất ngắn. `withoutStackTrace()` loại phần stack trace của custom events trong demo để giảm dữ liệu không cần thiết.
3. `setToDisk(true)` cho phép ghi xuống repository; `setMaxAge(5m)` và `setMaxSize(32 MiB)` là **retention**, không phải tên output file.
4. `start()` bắt đầu recording; vòng lặp tạo **ba Event instances**, rồi `commit()`. Chúng không trở thành ba file.
5. `stop()` kết thúc ghi; `getState()` là `STOPPED`. `dump(output)` tạo file `example.jfr` cho trình phân tích.
6. `try (Recording...)` sau khi dump sẽ gọi `close()`, giải phóng dữ liệu nội bộ; file output đã dump vẫn tồn tại.
7. `RecordingFile` đọc tất cả event types trong file nhưng **chỉ lấy `demo.BatchStep`**; không giả định JFR chỉ lưu duy nhất một event type.
8. `TreeMap` sắp xếp theo `step` để stdout không phụ thuộc tên thread hoặc thứ tự event khác. Ví dụ không in số chunk hay đường dẫn tạm, vì chúng có thể thay đổi theo môi trường.
9. `finally` xóa file và thư mục mà chính chương trình tạo; chạy xong không để lại artifact JFR. Nếu muốn giữ output để điều tra bằng `jfr`, bỏ phần dọn file một cách có chủ ý và quản lý đường dẫn an toàn.

**Tại sao không assert số chunk?** Một recording rất ngắn có thể tạo một chunk hoặc các ranh giới khác tùy VM; không có hợp đồng “3 events = 3 chunks”. Hãy assert **số và nội dung custom events** như demo, không dựa vào kích thước vật lý của JFR repository.

## 7. Công cụ `jcmd`: ghi và dump một JVM đang chạy

Với một tiến trình Java đang chạy và quyền vận hành phù hợp:

```bash
jcmd <PID> JFR.start name=AppHistory settings=default disk=true maxage=30m maxsize=256m
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=AppHistory filename=incident.jfr
jcmd <PID> JFR.stop name=AppHistory
```

Các dòng trên là **mẫu lệnh, phải thay `<PID>` bằng PID thật**; chúng không phải script Java độc lập. `JFR.start` tạo recording với settings/retention; `JFR.check` xem trạng thái; `JFR.dump` xuất file phân tích; `JFR.stop` kết thúc recording. Một `dump` trong quá trình ghi có thể dùng để lấy snapshot **mà không yêu cầu dừng mọi thu thập**; không xem “dump” và “stop” là cùng một hành động.

Kiểm tra các option chính xác của JVM đang dùng bằng `jcmd <PID> help JFR.start`/`JFR.dump`. Trong production, cần quyền truy cập cùng user phù hợp và kế hoạch quản lý dung lượng, thời gian và quyền đọc file.

Khi muốn tự dừng sau một thời gian, đặt `duration`; khi muốn dump lúc JVM shutdown theo điều kiện hỗ trợ, có `dumponexit`. **Không bảo đảm** dump-on-exit lưu đầy đủ dữ liệu khi crash cứng hoặc mất nguồn.

## 8. Công cụ `jfr` và Java API để đọc file recording

Khi đã có file `incident.jfr`:

```bash
jfr summary incident.jfr
jfr print --events demo.BatchStep incident.jfr
jfr metadata incident.jfr
```

- `jfr summary` hiển thị thông tin tổng quan gồm event types, counts và dung lượng.
- `jfr print` cho phép lọc theo tên event; output bao gồm thời điểm, thread/fields và thông tin cần phân tích.
- `jfr metadata` trình bày kiểu event và mô tả fields.
- `jfr assemble <repository> <file>` dùng để ghép các chunks hoàn tất còn nguyên khi cần khôi phục từ repository.
- `jfr disassemble --output <directory> <file>` tách một recording file thành các phần theo chunk. **Xác minh phiên bản bằng `jfr help` trước khi dùng**, vì một số subcommands/options có thay đổi qua JDK.

**Đọc từ Java 11 bằng `RecordingFile`:**

```java
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if (event.getEventType().getName().equals("demo.BatchStep")) {
            System.out.println(event.getString("task"));
        }
    }
}
```

Đây là **đoạn minh họa** cần biến `path` kiểu `Path`, import `RecordingFile`/`RecordedEvent`. `RecordingFile` nhận **đường dẫn tới file recording**, **không nhận thư mục repository**. Dùng cách duyệt tuần tự cho file lớn để tránh tạo một list toàn bộ events trong bộ nhớ; `RecordingFile.readAllEvents(path)` tiện với file nhỏ nhưng không thích hợp để giữ toàn bộ file hàng GB trong RAM.

Chỉ phân tích file `.jfr` từ nguồn tin cậy, vì nó là đầu vào binary/metadata cho parser. Không đăng nguyên output `jfr print` lên nơi công khai nếu có event chứa customer IDs, file paths hoặc dữ liệu ứng dụng nhạy cảm.

## 9. Kịch bản thực tế: ghi lịch sử liên tục để điều tra sự cố

Ví dụ một ứng dụng backend cần quan sát latency và GC:

1. Khởi động recording nền bằng `settings=default` với disk mode. Chọn `maxage=30m`/`maxsize` dựa trên tốc độ sinh events và dung lượng đĩa.
2. Khi phát hiện sự cố, dùng `JFR.check` rồi `JFR.dump` ra `incident-...jfr`. Chốt quyền truy cập và thời hạn lưu file đó.
3. Phân tích bằng `jfr summary`, `jfr print`, hoặc **JDK Mission Control**; đối chiếu thời điểm GC, thread activity và events nghiệp vụ.
4. Nếu thiếu dữ liệu chi tiết, chạy recording thứ hai với `profile` trong thời gian ngắn; đo overhead thay vì bật sampling nặng vô hạn.
5. Cân nhắc nơi repository nằm trên filesystem/container. Thư mục temporary có thể nhỏ, bị dọn hoặc mất khi container restart.
6. Sau phân tích, xóa file dump theo chính sách; retention của recording **không tự xóa** mọi file `incident.jfr` được export ra nơi khác.
7. Đối với dữ liệu bắt buộc chính xác từng sự kiện (audit, tài chính), dùng durable log riêng. JFR có thể bị sampling/filtering hoặc mất dữ liệu khi overload và crash.

**Một recording đang chạy không buộc phải stop mới lấy dữ liệu.** `dump` có thể tạo snapshot. Nhưng cần hiểu đây chỉ là dữ liệu **đã được ghi/giữ trong cửa sổ retention** ở thời điểm dump, không phải sự bảo đảm đã bắt được mọi event từ lúc service khởi động.

## 10. Lỗi phổ biến và cách tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| `Event.commit()` tự tạo file `.jfr` | Commit gửi event vào pipeline; file do recording/dump tạo |
| Event type tồn tại thì mọi event luôn được lưu | Phụ thuộc enabled, threshold, recording chạy, buffers |
| Một event bằng một chunk | Một chunk chứa nhiều events + metadata |
| Một recording bằng đúng một file chunk | Recording có thể bao trùm nhiều chunks; output `.jfr` có thể chứa nhiều chunks |
| Repository là file `incident.jfr` | Repository là kho tạm; incident file là output được export |
| `setToDisk(false)` vẫn giữ lịch sử vô hạn | Memory buffers có giới hạn |
| `setMaxSize(0)` nghĩa dung lượng bằng 0 | Với API Recording, 0 là không đặt giới hạn maxsize |
| `setMaxAge(null)` nghĩa xóa ngay | `null` nghĩa không đặt giới hạn tuổi |
| `maxage=30m` xóa từng event ở ranh giới thời gian tuyệt đối | Retention theo chunks/flush, có độ hạt và độ trễ |
| `setMaxSize` và `maxchunksize` cùng là một option | Một cái giới hạn data retained, một cái giới hạn chunk size |
| `stop()` chắc chắn đã ghi đúng file mình muốn | Phải setDestination hoặc dump đúng path |
| `close()` là cách export recording | Close giải phóng tài nguyên; cần dump trước |
| Chỉnh/xóa file chunk trong repository đang chạy | Có thể làm hỏng recording; dùng cấu hình JFR |
| JFR là durable audit trail lossless | JFR là chẩn đoán; cần audit pipeline riêng nếu không được mất event |
| Dùng tính năng JFR mới trên source target Java 11 mà không kiểm tra | Cần đối chiếu Javadoc của version target và `--release 11` |

## 11. Câu hỏi tự kiểm tra

**Câu 1:** 1.000 custom events được ghi trong một recording. Có phải sẽ có 1.000 chunk không?

**Đáp án:** Không. Chunk chứa nhiều events; số chunks không suy ra từ số event instances.

**Câu 2:** Recording và repository có cùng nghĩa không?

**Đáp án:** Không. Recording là **phiên thu thập logic** (settings, lifecycle, retention), còn repository là **kho tạm** cho chunks do JFR quản lý khi dùng disk mode.

**Câu 3:** Nếu gọi `recording.stop()` mà không `setDestination` hoặc `dump`, có chắc có file `report.jfr` không?

**Đáp án:** Không. Muốn có output path cụ thể, phải cấu hình/call export và kiểm tra file.

**Câu 4:** Vì sao một file JFR gồm nhiều chunks vẫn đọc bằng `RecordingFile`?

**Đáp án:** File JFR có format gồm một hoặc nhiều chunks; `RecordingFile` là API reader cho file recording và xử lý cấu trúc đó.

**Câu 5:** `setMaxAge(30m)` bảo đảm giữ tất cả events từ đầu chương trình không?

**Đáp án:** Không. Nó chỉ quản lý lịch sử còn được giữ trong khoảng gần nhất; chunks cũ có thể bị loại và một số events có thể không được thu vì settings/buffers.

**Câu 6:** Nếu JVM crash khi một chunk đang ghi, có thể khôi phục mọi event không?

**Đáp án:** Không. Một số chunk hoàn tất còn nguyên có thể dùng `jfr assemble`; dữ liệu chưa flush hoặc chunk chưa hoàn tất có thể mất.

**Câu 7:** Vì sao `RecordingFile` demo lọc `demo.BatchStep`?

**Đáp án:** File `.jfr` có thể có built-in events và metadata; demo cần lấy đúng events ứng dụng, không khẳng định nó là event type duy nhất.

**Câu 8:** Khi cần lưu đầy đủ mỗi giao dịch để phục vụ kiểm toán, chỉ dùng JFR đã đủ chưa?

**Đáp án:** Chưa. JFR không bảo đảm mọi event được lưu vĩnh viễn và không mất; cần durable audit/event log có cơ chế ghi bền vững riêng.

**Ghi nhớ:** **Event** là điều xảy ra, **Recording** là phiên thu thập và cấu hình, **Chunk** là đơn vị dữ liệu JFR, **Repository** là nơi JFR lưu tạm chunks. Dữ liệu đi từ `Event.commit()` qua settings/buffers, vào chunks của repository nếu dùng disk mode, rồi được **dump** ra file `.jfr` để phân tích bằng `jfr` hoặc `RecordingFile`. Dùng `maxage/maxsize` để giữ lịch sử có giới hạn, đừng nhầm kho tạm với file output và đừng coi JFR là audit log không thể mất dữ liệu.

**Nguồn chính thức:** [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328); [Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html); [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html); [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html); [Java SE 11 — FlightRecorder](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html); [Dev.java — Cấu hình JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/); [Dev.java — Công cụ jfr](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/).
