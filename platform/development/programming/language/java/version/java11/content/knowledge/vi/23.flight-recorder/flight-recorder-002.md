# Flight Recorder: Phân biệt JFR, heap dump, thread dump và profiler lấy mẫu (Java 11+)

> **Phạm vi:** Chẩn đoán hiệu năng và sự cố trong ứng dụng JVM bằng **Java Flight Recorder (JFR)**, **heap dump**, **thread dump** và **sampling profiler**. Bài học tập trung vào **loại câu hỏi mỗi công cụ trả lời**, cách thu thập chứng cứ trên Java 11+, chi phí vận hành, cách phối hợp khi điều tra production và những kết luận **không** được suy ra từ một ảnh chụp hay một mẫu thống kê. Các cơ chế được mô tả vẫn hiện hành trên JDK mới; khi chạy lệnh hãy kiểm tài liệu và `jcmd <PID> help <command>` của đúng JVM đang triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích điểm khác nhau giữa **dòng sự kiện theo thời gian**, **ảnh chụp đồ thị object**, **ảnh chụp trạng thái thread**, và **mẫu stack được lấy định kỳ hoặc theo sự kiện**.
2. Chọn đúng công cụ cho CPU cao, độ trễ tăng, heap tăng, `OutOfMemoryError`, deadlock, lock contention, thread leak, allocation pressure và I/O chậm.
3. Phân biệt **JFR recording** (`.jfr`) với **heap dump** (`.hprof`), **thread dump** (thường dạng text) và **profile/flame graph** (`.html`, `.jfr` hoặc định dạng do profiler hỗ trợ).
4. Biết rằng JFR **bản thân cũng có method sampling**, nên “JFR” và “sampling profiler” là **hai khía cạnh giao nhau**, không phải hai công cụ luôn loại trừ nhau.
5. Dùng `jcmd JFR.start`/`JFR.check`/`JFR.dump`/`JFR.stop`, `jfr summary` và `jfr print` với giới hạn thời gian, dung lượng, quyền truy cập và cleanup phù hợp.
6. Dùng `jcmd Thread.print -l`, `GC.class_histogram` và `GC.heap_dump` đúng tình huống; nhận biết chi phí pause, khả năng kích hoạt GC và dữ liệu nhạy cảm.
7. Đọc mẫu CPU và wall-clock đúng cách; biết sampled hot path không tự chứng minh chính xác số lần gọi hoặc độ trễ từng request.
8. Tạo một recording JFR custom event bằng **`jdk.jfr` API Java 11** và đọc lại bằng `jdk.jfr.consumer.RecordingFile`.
9. Tạo một **thread snapshot** không cần `jcmd` bằng `ThreadMXBean` để minh họa `BLOCKED`/lock owner.
10. Lập quy trình điều tra có thể tái lập: đặt giả thuyết → ghi nhận thời điểm/scope → thu thập đúng bằng chứng → phân tích → thử sửa → đo lại.
11. Bảo vệ JFR/heap dump/thread dump khỏi rò dữ liệu; giới hạn chi phí quan sát trên production.

## 2. Bốn loại bằng chứng: khác nhau từ bản chất

### 2.1. Java Flight Recorder (JFR)

JFR là **cơ chế ghi sự kiện gắn vào JVM/JDK**, thu thập các sự kiện có timestamp và các thuộc tính liên quan như GC pause, thread park, monitor blocked, socket/file I/O, CPU load, exception, allocation sampling hoặc execution sampling tùy **cấu hình ghi**. JFR có thể ghi qua **một khoảng thời gian**, thường được phân tích bằng **JDK Mission Control (JMC)** hoặc công cụ `jfr`.

JFR phù hợp câu hỏi: “Điều gì xảy ra quanh thời điểm p99 tăng? Thread chờ ở đâu? GC chiếm bao nhiêu thời gian? Những stack/method nào thường xuất hiện khi JVM đang làm việc?”

JFR **không phải heap dump**: không mặc định lưu **toàn bộ đối tượng đang sống và mọi đường tham chiếu**. JFR cũng **không phải thread dump tức thời đầy đủ**: event có thể chỉ lấy sample hoặc chỉ xảy ra khi điều kiện/threshold được đáp ứng.

### 2.2. Heap dump

Heap dump là một **snapshot bộ nhớ heap dạng object graph**, thường theo định dạng **HPROF**: object instances, classes, fields, references, arrays và thông tin cần thiết để phân tích những object còn giữ bộ nhớ.

Heap dump phù hợp câu hỏi: “Object nào giữ nhiều heap? Tại sao `Map` lớn vẫn reachable? Chuỗi tham chiếu nào giữ hàng triệu instance và không được GC giải phóng?”

Heap dump **không cho toàn bộ dòng thời gian** nguyên nhân tạo object; một snapshot ở thời điểm sau sự cố không tự cho biết lúc nào từng object được cấp phát hay thread nào đã tạo nó.

### 2.3. Thread dump

Thread dump là **snapshot trạng thái các thread tại một thời điểm**, gồm tên/ID, stack frames, trạng thái như `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và có thể lock owner / synchronizers.

Thread dump phù hợp câu hỏi: “Thread nào đang chờ monitor? Có vòng deadlock? Request worker đang nằm ở stack nào? Có hàng trăm thread cùng đợi một khóa?”

Một thread dump **không phải timeline**, không chỉ ra số byte heap còn sống, và cũng **không phải CPU profile chính xác** chỉ vì một thread đang có trạng thái `RUNNABLE`.

### 2.4. Sampling profiler (profiler lấy mẫu)

Sampling profiler quan sát **stack đang chạy hoặc các sự kiện** ở những thời điểm/chu kỳ lấy mẫu, sau đó tổng hợp thành **flame graph**, top methods hoặc call tree. Công cụ có thể đo **CPU**, **wall-clock**, **allocation**, **lock contention**, hoặc sự kiện hiệu năng phần cứng tùy implementation.

Sampling profiler phù hợp câu hỏi: “Đường gọi nào chiếm nhiều mẫu CPU? JVM đang đốt CPU vào tính toán gì? Dòng thực thi nào thường nằm trên stack khi đo?”

Vì là **lấy mẫu**, kết quả có **sai số thống kê**, phụ thuộc cửa sổ quan sát, sample frequency, loại sự kiện, khả năng stack unwinding và bias của profiler. Nó không phải đếm chính xác mọi method invocation.

## 3. Bảng so sánh cốt lõi

| Tiêu chí | JFR | Heap dump | Thread dump | Sampling profiler |
| --- | --- | --- | --- | --- |
| **Bản chất dữ liệu** | **Events theo thời gian**, có metadata/stack tùy event | **Đồ thị object** ở một thời điểm | **Thread states/stacks** tại một thời điểm | **Các stack samples** được tổng hợp |
| **Dạng đầu ra thường gặp** | `.jfr` | `.hprof` | Text, có thể dạng khác tùy JDK/tool | Flame graph/call tree, `.html`, `.jfr`, collapsed stacks... |
| **Độ dài quan sát** | Từ vài giây đến continuous bounded recording | Một lần chụp | Một lần hoặc nhiều lần chụp rời | Một phiên có thời gian/số mẫu |
| **Trả lời tốt nhất** | Tương quan CPU/GC/lock/I/O/latency theo thời gian | Heap retention và GC roots | Blocked/deadlocked threads và stack hiện tại | Hot paths CPU/wall/alloc tùy mode |
| **Đọc từng object reference** | Không đầy đủ như heap dump | **Có** nếu dump/analysis hỗ trợ | Không | Không |
| **Thấy xu hướng GC theo thời gian** | **Có** nếu ghi event phù hợp | Không trực tiếp | Không | Chỉ nếu profiler có event phù hợp |
| **Thấy stack bị BLOCKED ngay khi chụp** | Có thể có event/stack liên quan nhưng không bảo đảm snapshot hiện tại | Không | **Có** | Wall sample có thể quan sát; CPU mode thường bỏ lỡ thread ngủ/chờ |
| **Chi phí vận hành** | Thường thấp với `default.jfc`, tăng theo settings | **Cao**, có thể pause/GC và ghi file rất lớn | Thường thấp hơn heap dump nhưng phụ thuộc số thread | Tùy profiler/mode/frequency/symbolization |
| **Dữ liệu dễ nhạy cảm** | Thread names, stacks, event payload/path; tùy cấu hình | **Rất cao:** object có thể chứa token/password/dữ liệu khách hàng | Stack, thread names, lock metadata, có thể lộ đường dẫn/tên nội bộ | Method names, stacks, native symbols, metadata |
| **Điểm mù chính** | Event không bật, threshold/sampling bỏ sót | Không có dòng thời gian allocation | Một ảnh chụp ngắn không nói trend | Sample bias, không nhìn được toàn bộ object graph |

**Không chọn bằng tên công cụ**. Hãy bắt đầu từ **triệu chứng và câu hỏi điều tra**. Nhiều sự cố cần kết hợp hai hoặc nhiều loại bằng chứng, thay vì tìm một công cụ “mạnh nhất”.

## 4. Chi phí quan sát: thấp không có nghĩa bằng không

JFR được thiết kế cho production monitoring. Theo tài liệu Oracle, `default.jfc` thường có chi phí rất thấp, và cấu hình continuous tiêu chuẩn có thể phù hợp vận hành lâu dài. Tuy nhiên:

- Overhead **không phải số cố định được bảo đảm**. Nó phụ thuộc loại event, threshold, tần suất ghi stack trace, lượng allocation, tốc độ event, phần cứng và tải ứng dụng.
- `profile.jfc` thường bật thêm dữ liệu phục vụ phân tích chuyên sâu; dùng **có thời hạn** với tải tương đương sản xuất và cân nhắc CPU/disk overhead.
- Một số JFR event hoặc cấu hình **heap statistics/old object analysis** có thể gây GC/overhead đáng kể. Đừng nhầm mọi chức năng JFR đều “nhẹ như nhau”.
- Nếu JFR ghi vào disk repository, cần cap dung lượng/retention, kiểm quyền đọc file, tốc độ ghi và filesystem trống.
- Heap dump có thể gây **stop-the-world pause** và cần dung lượng rất lớn. Tài liệu `jcmd GC.heap_dump` của JDK mới mô tả **impact cao**, mặc định thường yêu cầu full GC trừ khi dùng tùy chọn khác. Không tạo dump nặng giữa peak traffic mà chưa đánh giá rủi ro.
- Thread dump trên JVM nhiều nghìn threads có thể tốn thời gian/kích thước file đáng kể. Lấy nhiều bản liên tiếp phải có interval/limit.
- Sampling profiler ở frequency rất cao, với native stacks/perf events hoặc allocation mode, có thể tác động đến hiệu năng và cần quyền hệ điều hành. Chạy sampling “không thấy overhead” trên dev **không bảo đảm** giống production.

## 5. JFR lưu những gì và không lưu những gì?

Một JFR recording chứa **events**, chẳng hạn:

- `jdk.CPULoad`: tải CPU của JVM/máy theo mốc thời gian.
- `jdk.ThreadCPULoad`: thống kê tải CPU theo thread.
- `jdk.ExecutionSample` và những execution sampling events được bật: mẫu stack để suy luận hot methods.
- `jdk.GarbageCollection`, `jdk.GCPhasePause`: sự kiện và pause GC.
- `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`: liên quan monitor/park và thời gian đợi (tùy cấu hình threshold).
- `jdk.SocketRead`/`jdk.SocketWrite`, `jdk.FileRead`/`jdk.FileWrite`: I/O operations (khi có và được bật).
- Các sự kiện liên quan allocation sampling, object-count/heap statistics, thread lifecycle hoặc custom events tùy JDK/settings.

**Tên event có thể có ở schema nhưng bị tắt/threshold mặc định**, hoặc không xuất hiện nếu workload không phát sinh sự kiện đáp ứng điều kiện. **Không có một event trong tệp không chứng minh hiện tượng không xảy ra.**

### JFR custom events

Ứng dụng có thể tạo event bằng API `jdk.jfr.Event`. Điều này hữu ích để gắn **ngữ cảnh nghiệp vụ có kiểm soát** vào timeline (ví dụ xử lý một batch, phase ingest, latency của một hoạt động). Không ghi trực tiếp payload HTTP, thông tin người dùng, token hoặc khóa bí mật vào JFR events.

### default.jfc và profile.jfc

Hai cấu hình đi kèm JDK thường nằm trong:

~~~text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
~~~

- `default.jfc`: điểm xuất phát cho **continuous recording** với mức event/overhead phù hợp hơn.
- `profile.jfc`: nhiều sự kiện/chi tiết hơn, dùng khi **điều tra hoặc profiling có giới hạn**.
- Settings tách khỏi việc **chọn thời gian recording và retention**. Có thể cùng profile settings nhưng duration/maxsize khác nhau.
- Nếu một event quan trọng chưa bật hoặc threshold quá cao, dùng **configuration riêng** dựa trên file copy và test. Đừng sửa file mặc định trong JDK installation.
- Trên JDK mới có thêm cấu hình/công cụ quản lý event; nếu dự án còn dùng Java 11, chỉ dùng tính năng mà JDK 11 hỗ trợ hoặc ghi rõ khác biệt phiên bản.

## 6. Dùng jcmd để lấy JFR trên JVM đang chạy

`jcmd` là công cụ chẩn đoán đi kèm **JDK đầy đủ**, có thể gửi yêu cầu đến JVM đang chạy. Thường cần cùng máy hoặc namespace thích hợp, quyền OS phù hợp, và JVM cho phép attach. Trong container, phải xét PID namespace và đặc quyền thực tế.

### 6.1. Xác định process

~~~bash
jcmd -l
~~~

Lệnh này liệt kê các JVM có thể quan sát. **Không** copy một PID từ ví dụ rồi gửi lệnh vào production; xác nhận PID/service/container/user trước. Trong một số môi trường attach bị hạn chế, `jcmd -l` có thể không liệt kê tiến trình mong đợi.

### 6.2. Start JFR có giới hạn

~~~bash
jcmd <PID> JFR.start name=IncidentA settings=default maxage=20m maxsize=128m
~~~

**Lệnh mẫu, không phải một lệnh đã chạy trên production.** `<PID>` phải thay bằng PID thật; `maxage/maxsize` là các giới hạn retention phù hợp với recording có disk repository theo options của JDK mục tiêu. Hãy chạy `jcmd <PID> help JFR.start` để xác minh cú pháp/khả năng của build đang dùng.

Sau đó:

~~~bash
jcmd <PID> JFR.check
~~~

### 6.3. Dump snapshot mà không cần đợi JVM dừng

~~~bash
jcmd <PID> JFR.dump name=IncidentA filename=/secure/incident-a.jfr
~~~

`JFR.dump` là thao tác xuất dữ liệu ghi ra file từ một recording. **Đừng mặc định nó giống `JFR.stop`**. Nếu muốn dừng hẳn recording, có lệnh riêng:

~~~bash
jcmd <PID> JFR.stop name=IncidentA
~~~

Lưu ý:

- Chọn đường dẫn tồn tại, có đủ dung lượng và **quyền ghi đối với JVM mục tiêu**; file có thể được tạo từ process target, không phải chỉ từ shell `jcmd`.
- Có thể có nhiều recording song song, nên đặt `name` cụ thể và xác minh qua `JFR.check`.
- Với recording ngắn, có thể dùng `duration=...` và `filename=...` từ `JFR.start` thay cho chuỗi lệnh thủ công.
- Không để một recording `profile` chạy vô hạn nếu workload overhead cao hoặc chạm giới hạn disk.
- Kiểm lại chính sách xử lý các file chứa dữ liệu nhạy cảm trước khi copy ra máy khác.

### 6.4. Phân tích file bằng CLI

~~~bash
jfr summary /secure/incident-a.jfr
jfr print --events jdk.CPULoad /secure/incident-a.jfr
jfr print --events jdk.ExecutionSample /secure/incident-a.jfr
~~~

`jfr summary` cho biết thống kê event types; `jfr print` in ra events/fields, có thể rất nhiều dòng. Với file lớn, lọc event/cửa sổ thời gian hoặc dùng **JDK Mission Control** cho biểu đồ timeline/hot threads/GC/lock. Không chia sẻ raw output công khai.

**Quan trọng:** Cấu hình `default.jfc` có thể lấy ít execution samples hơn `profile.jfc`. Vì vậy, một recording ngắn không có nhiều `jdk.ExecutionSample` chưa đủ kết luận “ứng dụng không dùng CPU”.

## 7. JDK Mission Control: đọc JFR trực quan

JFR là **recording engine/API**, còn **JDK Mission Control (JMC)** là bộ công cụ GUI phân tích/giám sát, được phân phối riêng; **không mặc định nằm trong mọi JDK installation**.

Trong JMC, người điều tra thường bắt đầu với:

1. **Overview / automated analysis**: khoảng thời gian và các cảnh báo đáng chú ý.
2. **Threads**: thread activity, chờ monitor, park, locks, thread changes.
3. **Code / method profiling**: execution samples, hot methods/call tree, stack traces.
4. **Memory**: allocation pressure, GC events, heap usage trends; kiểm event hiện có trước khi suy luận.
5. **I/O**: socket/file operations, latency nếu event được bật.
6. **Event browser**: tìm đúng event name/threshold/payload để xác minh giả thuyết.
7. **Time range filtering**: cô lập thời điểm incident, so sánh trước–trong–sau.

Không nhìn một flame graph rồi bỏ qua timeline. Một hot method xuất hiện dày trong toàn bộ recording **chưa chắc** là nguyên nhân của spike 3 giây cần xử lý. Chọn cửa sổ incident và so sánh baseline.

## 8. Ví dụ Java 11 hoàn chỉnh: tạo và đọc JFR recording

Ví dụ **không cần server, attach, JMC hoặc Internet**. Nó:

- Dùng `jdk.jfr.Recording` với cấu hình `profile`.
- Đăng ký custom event `lesson.WorkUnit`.
- Ghi đúng **ba sự kiện** có chỉ số 1, 2, 3.
- Dump ra tệp tạm `.jfr`, đọc lại bằng `RecordingFile`.
- Chỉ đếm đúng event type đã tạo, rồi xóa tệp tạm.

Tạo file **`JfrRecordingDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

import java.nio.file.Files;
import java.nio.file.Path;

public class JfrRecordingDemo {

    @Name("lesson.WorkUnit")
    @Label("Work unit")
    static class WorkUnit extends Event {
        @Label("Index")
        int index;
    }

    public static void main(String[] args) throws Exception {
        Path output = Files.createTempFile(
                "jfr-lesson-", ".jfr");
        long matched = 0;

        try {
            try (Recording recording = new Recording(
                    Configuration.getConfiguration("profile"))) {

                recording.setName("lesson");
                recording.enable(WorkUnit.class);
                recording.start();

                for (int i = 1; i <= 3; i++) {
                    WorkUnit event = new WorkUnit();
                    event.index = i;
                    event.commit();
                }

                recording.stop();
                recording.dump(output);
            }

            try (RecordingFile reader = new RecordingFile(output)) {
                while (reader.hasMoreEvents()) {
                    RecordedEvent event = reader.readEvent();

                    if ("lesson.WorkUnit".equals(
                            event.getEventType().getName())) {
                        matched++;
                    }
                }
            }

            System.out.println(
                    "jfr.file.created="
                            + Files.isRegularFile(output));
            System.out.println(
                    "jfr.customEvents=" + matched);
        } finally {
            Files.deleteIfExists(output);
        }
    }
}
~~~

Biên dịch với API Java 11, chạy bằng JDK có module `jdk.jfr`:

~~~bash
javac --release 11 JfrRecordingDemo.java
java JfrRecordingDemo
~~~

**Stdout đã kiểm chứng bằng chạy thực tế:**

~~~text
jfr.file.created=true
jfr.customEvents=3
~~~

### Những gì ví dụ chứng minh

- Một JFR recording thật được tạo trong process.
- Có thể lưu file `.jfr` và đọc event bằng API `jdk.jfr.consumer`.
- Custom event có thể được đếm bằng **event type name**.
- Không cần giả lập record format bằng JSON hoặc ghi log thủ công.
- Không cần dự đoán tổng số JVM events, vì chúng phụ thuộc JDK/settings/workload; chỉ assert **ba custom events** ổn định.
- Tệp tạm được xóa sau ví dụ, nên không để artifact có thể chứa sự kiện nội bộ nằm trong filesystem.
- Bài demo dùng `profile` để minh họa API; trong production continuous recording thường ưu tiên `default` và có resource limits.

**Không kết luận** demo đã kiểm tra attach `jcmd` từ process bên ngoài, hoặc đã đo overload dưới tải production. Những điều đó đòi hỏi thử nghiệm ở môi trường mục tiêu.

## 9. Heap dump: đọc object graph, không phải profile theo thời gian

Một **heap dump** giúp nhìn thấy:

- Loại object, số instances và kích thước trong snapshot.
- References giữa các object.
- GC roots và đường giữ các object còn reachable.
- **Retained size**: lượng bộ nhớ có thể giải phóng nếu một object/nhóm object không còn bị giữ qua reference graph, theo mô hình của công cụ phân tích.
- **Dominator tree**: object/nhóm object nào giữ phần lớn heap.
- Những collection/map/cache lớn hoặc classloader giữ references bất thường.

### 9.1. Lấy heap dump có kiểm soát

~~~bash
jcmd <PID> GC.heap_dump filename=/secure/heap-incident.hprof
~~~

Đây là **lệnh minh họa**, chưa chạy trên production. Trên JDK 11, tài liệu Oracle Troubleshooting Guide trình bày `GC.heap_dump` qua `jcmd`; một số JDK dùng dạng positional filename, hãy xác nhận bằng `jcmd <PID> help GC.heap_dump`. Mục tiêu là tạo một **HPROF snapshot**, không phải chỉ in histogram.

**Cảnh báo vận hành:**

- Lệnh có **impact cao**; theo implementation/version có thể yêu cầu full GC trước khi dump. Điều này làm thay đổi heap state và tạo pause.
- File có thể tương đương kích thước heap lớn; chuẩn bị disk quota, dung lượng trống, đường dẫn và quyền truy cập. Container có thể bị ảnh hưởng bởi I/O/memory/disk.
- HPROF có thể chứa **secret, token, password, PII, session data và dữ liệu khách hàng** dưới dạng object field/string/array. Xem nó như dữ liệu rất nhạy cảm, mã hóa/kiểm soát truy cập/retention.
- Không khởi tạo dump nhiều lần khi JVM đang gần `OutOfMemoryError` hoặc traffic peak mà chưa xem xét rủi ro.
- Dump thường chỉ mô tả trạng thái heap **tại thời điểm chụp**, không đầy đủ native memory, thread stacks hoặc mọi off-heap allocation.

### 9.2. Histogram nhẹ hơn dump nhưng vẫn có giá

~~~bash
jcmd <PID> GC.class_histogram
~~~

Histogram tổng hợp **số lượng và kích thước object theo class**. Đây là bước định hướng phù hợp hơn khi chỉ cần biết class nào đang tăng, nhưng:

- Không hiện toàn bộ object references và dominator tree.
- Không chứng minh được một object/class gây leak; một số lượng lớn có thể bình thường theo workload.
- Có thể có chi phí đáng kể và ảnh hưởng GC/heap tùy tùy chọn/JDK.
- Nếu muốn xem toàn bộ object kể cả unreachable, phải đọc contract của `-all` trên đúng JDK; không lạm dụng flag chỉ vì muốn “thêm dữ liệu”.

### 9.3. Phân tích heap dump đúng phương pháp

Dùng công cụ phân tích HPROF phù hợp như **Eclipse Memory Analyzer (MAT)** hoặc công cụ tương đương:

1. Mở heap dump được thu thập an toàn.
2. Kiểm **heap size**, class histogram và số instances bất thường.
3. Dùng **Dominator Tree** tìm nhóm giữ retained heap.
4. Với object đáng ngờ, xem **Path to GC Roots** để xác định ai giữ references.
5. Đối chiếu code: static caches, map không eviction, listener không unsubscribe, ThreadLocal, classloader, queue, sessions, buffers.
6. Kiểm **shallow size** khác **retained size**: một object `HashMap` nhỏ vẫn có thể giữ hàng GB các entries nếu nó chi phối vòng đời của graph.
7. So sánh nhiều snapshot/metrics theo thời gian với tải tương đương; một ảnh chụp đơn lẻ không chứng minh **leak**.
8. Sửa ownership/cleanup/retention policy và đo lại heap sau GC trong điều kiện tương đương.

**Không coi “object lớn nhất” mặc nhiên là leak**. Một bộ cache có kích thước lớn nhưng giới hạn rõ có thể là thiết kế hợp lệ. Câu hỏi quyết định là **tại sao object còn reachable và có phù hợp với vòng đời không**.

### 9.4. HeapDumpOnOutOfMemoryError

Có thể cấu hình JVM để hỗ trợ điều tra OutOfMemory:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/secure/dumps -jar app.jar
~~~

**Lệnh minh họa**, không chạy ứng dụng thật trong bài. Hãy kiểm chính sách lưu file, dung lượng disk, quyền đọc, alert và cleanup. Dump khi OOME không phải bảo đảm file sẽ luôn được tạo (có thể hết disk/quyền ghi/tài nguyên), nên cần monitoring, metrics và giải pháp khôi phục song song.

## 10. Thread dump: ảnh chụp stack, trạng thái và khóa

Thu thập bằng `jcmd`:

~~~bash
jcmd <PID> Thread.print -l
~~~

Dùng `-l` để yêu cầu thông tin `java.util.concurrent` locks/synchronizers theo JVM hỗ trợ. Trong incident thường redirect output vào file bảo vệ bằng quyền OS phù hợp.

### 10.1. Ý nghĩa của Thread.State

| State | Diễn giải đúng | Điều không nên suy ra |
| --- | --- | --- |
| `NEW` | Thread chưa bắt đầu | Không có hoạt động khác |
| `RUNNABLE` | Có thể đang thực thi hoặc trong tác vụ native/I/O tùy platform | **Không** đồng nghĩa tiêu thụ 100% CPU |
| `BLOCKED` | Đang chờ lấy **object monitor** (ví dụ `synchronized`) | Không đại diện mọi loại lock hoặc I/O wait |
| `WAITING` | Đang chờ vô hạn qua `wait`/`join`/`park`... | Không mặc nhiên là deadlock |
| `TIMED_WAITING` | Đang chờ có timeout/sleep/parkNanos | Không chứng minh hệ thống lỗi |
| `TERMINATED` | Thread đã kết thúc | Không có trong mọi dump vì thread có thể đã biến mất |

**Đặc biệt:** `ReentrantLock` có thể sử dụng `LockSupport.park`, nên thread đang chờ nó **không nhất thiết ở trạng thái `BLOCKED`**. Đọc stack và thông tin synchronizer/lock owner; đừng kết luận chỉ từ một chữ `WAITING`.

### 10.2. Deadlock, contention và thread leak

- **Deadlock:** có vòng chờ tài nguyên hoặc monitor/synchronizer, không thể tiến triển. Một số dump/tool có hỗ trợ nhận diện deadlock; xác minh vòng chờ thật.
- **Contention:** nhiều thread chờ một lock nhưng vẫn có tiến triển. Stack và owner snapshot giúp tìm điểm nghẽn; JFR `JavaMonitorEnter` hoặc lock profiler giúp xem **thời lượng/tần suất**.
- **Thread leak:** số thread hoặc worker tăng dần mà không giảm; một dump có thể cho dấu hiệu nhưng **trend metrics hoặc nhiều dump** mới chứng minh xu hướng.
- **Slow requests:** nếu nhiều request threads có cùng stack chờ HTTP client/database/lock, đó là manh mối, nhưng nên đối chiếu duration/trace metrics và JFR I/O events.
- **CPU hot loop:** một dump có thể trúng hot stack hoặc không; dùng execution sampling/CPU profiler trong một khoảng thời gian để có cơ sở thống kê.

### 10.3. Nhiều thread dump cách nhau theo thời gian

Khi sự cố có hiện tượng “đứng”:

~~~bash
jcmd <PID> Thread.print -l > thread-1.txt
# Chờ một khoảng đo có chủ đích, ví dụ 5 giây.
jcmd <PID> Thread.print -l > thread-2.txt
# Nếu cần, lấy thêm một snapshot thứ ba.
~~~

Đây là **quy trình minh họa**, không phải script tự động chụp production. So sánh:

- Cùng thread có kẹt cùng frame/lock owner?
- Lock owner có thay đổi và đang tiến triển?
- Số threads có tăng?
- Có thread luôn nằm tại một operation?
- Thời gian lấy dump có trùng peak latency hay đã muộn?

Không tự động khẳng định “cùng stack ở hai dump = deadlock”. Một consumer có thể hợp lệ đang đợi công việc hoặc sleep trong cùng method.

## 11. Ví dụ Java 11: tạo thread snapshot mà không cần attach

Mục tiêu đoạn demo là minh họa **một thời điểm chụp stack**. Chương trình tạo hai thread:

- `demo-lock-holder` giữ một monitor;
- `demo-lock-blocked` cố lấy cùng monitor và bị `BLOCKED`.

Main dùng `ThreadMXBean` để đọc trạng thái và tên lock owner, sau đó giải phóng monitor. Không cần chạy `jcmd` hay có tiến trình JVM thứ hai.

Tạo file **`ThreadSnapshotDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadSnapshotDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws Exception {
        CountDownLatch holding = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                holding.countDown();

                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-holder");

        Thread blocked = new Thread(() -> {
            synchronized (LOCK) {
                // The lock was acquired after the snapshot.
            }
        }, "demo-lock-blocked");

        owner.start();
        holding.await();
        blocked.start();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);

        while (blocked.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.yield();
        }

        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        ThreadInfo info =
                bean.getThreadInfo(blocked.getId(), 8);

        if (info == null
                || info.getThreadState() != Thread.State.BLOCKED) {
            throw new AssertionError(
                    "Expected a blocked thread");
        }

        System.out.println(
                "thread.state=" + info.getThreadState());
        System.out.println(
                "thread.lockOwner=" + info.getLockOwnerName());
        System.out.println(
                "thread.stackPresent="
                        + (info.getStackTrace().length > 0));

        release.countDown();
        owner.join();
        blocked.join();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 11 ThreadSnapshotDemo.java
java ThreadSnapshotDemo
~~~

**Stdout đã kiểm bằng thực thi trên JDK:**

~~~text
thread.state=BLOCKED
thread.lockOwner=demo-lock-holder
thread.stackPresent=true
~~~

### Bài học từ ví dụ

- `CountDownLatch` đảm bảo owner đã giữ monitor trước khi blocked thread được tạo; sau đó main chờ trạng thái `BLOCKED` với deadline hữu hạn.
- `ThreadMXBean.getThreadInfo(threadId, maxDepth)` lấy **snapshot** tại thời điểm gọi; tham số `8` giới hạn độ sâu stack.
- `ThreadInfo.getLockOwnerName()` nói thread đang giữ monitor mà blocked thread chờ; trong fixture là `demo-lock-holder`.
- Đây **không phải deadlock**: owner được main cho thoát khi gọi `release.countDown()`, nên blocked thread cuối cùng chạy tiếp.
- Ví dụ cố ý tạo contention, giúp thấy vì sao **`BLOCKED` không đồng nghĩa deadlock**.
- Ví dụ không tạo tệp thread dump và không kiểm attach `jcmd`. Với JVM production, `jcmd Thread.print` cho snapshot rộng hơn từ bên ngoài, khi quyền attach cho phép.
- Với hệ thống thật, thread IDs, số frames, lock owner và timing thay đổi; không assert tên/stack cố định ngoài fixture kiểm soát.

## 12. Sampling profiler: CPU, wall-clock, allocation là ba mục tiêu khác nhau

### 12.1. CPU-time sampling

CPU sampler lấy mẫu khi thread đang sử dụng **CPU time** (tùy mode/profiler/OS). Kết quả thiên về những đường gọi thực sự thực thi nhiều tính toán.

Đọc hot path theo chiều đúng:

~~~text
http-worker
  -> Service.calculate
      -> Codec.parse
          -> Parser.match          [nhiều CPU samples]
~~~

Nếu phần lớn samples rơi vào `Parser.match`, đây là ứng viên tối ưu CPU trong **cửa sổ đo**. Nhưng:

- 40% samples **không nhất thiết** bằng 40% thời gian của một request đơn lẻ.
- Số mẫu nhỏ có sai số cao.
- CPU sampler thường **không giải thích trực tiếp** tại sao request phải chờ socket/database 2 giây nhưng CPU chỉ dùng 5 ms.
- Native/kernel frames có thể cần thêm symbol/debug information và quyền OS.

### 12.2. Wall-clock sampling

Wall-clock mode lấy mẫu stack theo **thời gian thực trôi qua**, có thể bắt cả những thread đang ngủ, park hoặc chờ I/O tùy profiler và bộ lọc.

Phù hợp với latency lớn nhưng CPU không cao. Tuy nhiên:

- Một thread có nhiệm vụ hợp lệ là chờ queue có thể xuất hiện nhiều mẫu mà **không gây nghẽn**.
- Muốn kết luận “request chậm vì DB”, cần phối hợp tracing/metrics, stack mẫu và I/O timing, không chỉ thấy `SocketInputStream.read`.
- Phải biết profiler đang sample **all threads** hay chỉ nhóm request worker; nếu không sẽ làm sai tỷ trọng.

### 12.3. Allocation sampling

Allocation profiler thu mẫu nơi objects được tạo. Nó phù hợp câu hỏi “Tại sao GC quá thường xuyên hoặc throughput kém do tạo objects?”

Nhưng:

- **Allocation rate** khác **retained heap**. Code có thể tạo nhiều objects ngắn hạn mà không leak.
- Một object được cấp phát ở hotspot A nhưng giữ sống bởi cache B cần **heap dump/GC roots** để xác định nguyên nhân retention.
- Sampling allocation không phải bản liệt kê đầy đủ mọi object trong heap.
- Một số mode hỗ trợ “live object sampling” nhưng phương pháp/overhead/ý nghĩa tùy profiler. Không đánh đồng với HPROF full graph.

### 12.4. Công cụ async-profiler

**async-profiler** là một sampling profiler độc lập với JFR engine tích hợp JDK, có hỗ trợ các mode như CPU, allocations, locks và một số OS/platform counters.

Ví dụ theo tài liệu dự án (**cần cài đúng phiên bản và quyền OS**):

~~~bash
asprof -e cpu -d 30 -f cpu.html <PID>
~~~

Lệnh minh họa dùng syntax của công cụ `asprof`, **không phải executable đi kèm JDK 11**. Một số chế độ yêu cầu HotSpot, Linux `perf_events` hoặc quyền container/host phù hợp; build hỗ trợ hệ điều hành có thể thay đổi theo bản phát hành. Không ép áp dụng một lệnh profiler trên mọi JVM/vendor/platform.

Một số profiler có thể **ghi kết quả dưới định dạng `.jfr`** để phân tích bằng JMC. **Định dạng output giống nhau không có nghĩa engine/sampling semantics giống nhau.** Kiểm metadata và loại event để biết dữ liệu đến từ JFR JVM hay sampling profiler riêng.

### 12.5. Sampling profiler không phải instrumentation profiler

- **Sampling**: quan sát một phần hoạt động, overhead thường thấp hơn công cụ instrument mọi lời gọi, đổi lại kết quả là **ước lượng**.
- **Instrumentation/tracing**: chèn hooks vào method hoặc requests để đo đúng event/latency cụ thể (theo thiết kế), nhưng tăng overhead và tạo nhiều data hơn.
- **JFR**: có cả các sự kiện được instrument trong JVM và **execution samples**; vì vậy không nằm độc quyền ở một trong hai nhãn.

## 13. Đọc flame graph đúng cách

Trong flame graph thường gặp:

- **Độ rộng một frame** phản ánh tỷ lệ mẫu/metric đã được tổng hợp vào stack đó, **không phải vị trí thời gian**.
- **Trục đứng** biểu diễn độ sâu call stack, thường caller phía dưới/callee phía trên.
- **Các khối có tên giống nhau** ở nhiều nơi có thể là cùng method được gọi từ nhiều call paths.
- **Màu sắc** thường để trực quan, không mặc định là “đỏ = tệ”, trừ khi công cụ/legend định nghĩa như vậy.
- **Nhiều mẫu ở một method** cần đối chiếu với volume/throughput trước khi sửa; đôi khi method chiếm nhiều CPU vì nó làm đúng công việc cần thiết.
- CPU flame graph và wall flame graph **không thể so sánh trực tiếp bằng cùng ý nghĩa**. Một cái tôn trọng CPU time, cái kia tôn trọng elapsed/wait time.
- Nếu có JIT inlining, native frames, GC threads hoặc mã compiler, hiểu cách profiler ánh xạ frames trước khi kết luận chính xác method Java nào dùng thời gian.

### Một ví dụ điều tra

~~~text
CPU usage: 90%
    |
    v
CPU profiling -> 60% sampled stacks qua JSON serializer
    |
    v
So với baseline/tải tương đương
    |
    v
Kiểm JSON allocations bằng JFR allocation events
    |
    v
Tối ưu serialization / cache có giới hạn
    |
    v
Đo lại CPU, GC, throughput, p95/p99
~~~

Đây là **quy trình giả định**, không phải kết quả benchmark cụ thể. Không tối ưu dựa vào một flame graph mẫu ngắn mà không kiểm workload.

## 14. Chọn công cụ theo triệu chứng: bảng quyết định nhanh

| Triệu chứng | Bắt đầu bằng | Khi cần mở rộng | Tránh nhầm |
| --- | --- | --- | --- |
| **CPU 95% kéo dài** | JFR `profile` có thời hạn hoặc CPU sampling profiler | OS process CPU, thread CPU samples, JIT/native stacks | Thread dump một lần không đo % CPU |
| **p99 latency tăng, CPU thấp** | JFR timeline I/O/park/lock, request tracing | Wall-clock profiling + một số thread dumps | CPU profile có thể bỏ lỡ I/O wait |
| **Heap tăng sau GC qua nhiều giờ** | Heap usage metrics, JFR GC/allocation trends | Histogram, sau đó heap dump khi cần roots | Allocation hotspots khác retention |
| **OutOfMemoryError: Java heap space** | Heap metrics, heap dump theo policy | MAT retained size/path to GC roots | JFR mặc định không chứa toàn object graph |
| **Full GC/pause kéo dài** | JFR GC events, GC logs | Heap histogram/dump nếu nghi live set lớn | Dump có thể kích hoạt GC bổ sung |
| **Nhiều request threads BLOCKED** | Thread dump -l | JFR monitor contention / lock profiling | WAITING không tự là deadlock |
| **Nghi deadlock** | Thread dumps/deadlock detector | JFR lock events, kiểm thứ tự acquire | Một snapshot thiếu vòng chờ chưa đủ loại trừ |
| **Thread count tăng không giảm** | Thread count metrics, nhiều thread dumps | JFR thread lifecycle events | Số thread cao chưa đủ chứng minh leak |
| **Tạo nhiều object/GC liên tục** | JFR allocation samples/profiler allocation | Histogram, heap dump nếu còn giữ objects | Không phải allocation cao nào cũng là leak |
| **Native memory tăng, heap ổn định** | Process RSS, Native Memory Tracking nếu đã cấu hình | Native allocation profiler/OS tools | Heap dump không bao quát mọi native memory |
| **I/O chậm theo từng request** | Tracing + JFR socket/file events | Wall-clock samples, downstream metrics | CPU thấp không có nghĩa request nhanh |
| **Tắc nghẽn không ổn định, xảy ra vài giây** | JFR bounded continuous recording | Alerts trigger dump, trace correlation | Chụp dump sau sự cố có thể đã quá muộn |

### Hãy đặt câu hỏi trước khi thu thập

- “Đối tượng nào đang giữ bộ nhớ?” → **heap dump**.
- “Ở một thời điểm các thread đang làm gì?” → **thread dump**.
- “Từ 10:00 đến 10:05 GC/lock/I/O/CPU thay đổi ra sao?” → **JFR**.
- “Hot method nào thường xuất hiện khi CPU đang cao?” → **CPU sampling profiler hoặc JFR execution samples**.
- “Request mất 3 giây nhưng CPU gần 0 vì sao?” → **JFR latency events + tracing + wall profiling**.
- “Object được cấp phát ở đâu, tốc độ bao nhiêu?” → **allocation sampler/JFR allocation events**.
- “Tại sao object vẫn không bị GC?” → **heap dump + retained graph/GC roots**.

## 15. Quy trình điều tra CPU cao: JFR và profiler lấy mẫu

**Tình huống:** máy chủ báo CPU tăng từ 40% lên 90% trong 5 phút, throughput gần như không đổi.

1. **Xác nhận phạm vi:** CPU của host hay JVM? Có process khác tranh CPU? Đo metrics theo cùng time window.
2. **Thu thập timeline:** JFR recording `profile` có thời hạn, đủ bao trùm khoảng sự cố. Nếu đã có default continuous recording, dump bản gần nhất trước.
3. **Đọc CPU samples:** tìm những methods/call paths có nhiều samples. Kiểm top threads và native frames nếu phù hợp.
4. **Nếu cần chi tiết sâu hơn:** chạy async-profiler CPU trong một cửa sổ được phép, với interval đủ số mẫu nhưng không quá nặng.
5. **Đối chiếu GC:** Nếu `GCPhasePause` tăng hoặc allocation tăng, có thể CPU đang dùng đáng kể cho GC, không chỉ business logic.
6. **Đặt giả thuyết cụ thể:** ví dụ một parser chạy vòng lặp lặp lại vì cache miss; cần thêm metrics/log để xác nhận.
7. **Sửa và đo lại:** CPU, throughput, p95/p99, heap allocation rate, GC pauses trên workload tương đương.

Không kết luận “60% CPU nằm ở method X” chỉ từ **một** stack trace hay từ tên thread đang RUNNABLE trong dump.

## 16. Quy trình điều tra heap tăng: JFR → histogram → heap dump

**Tình huống:** heap sau GC tăng đều qua nhiều giờ dù lưu lượng không tăng.

1. **Theo dõi baseline:** heap used sau GC/old-gen, GC frequency, allocation rate và request volume. Phân biệt cache warm-up với leak.
2. **JFR recording:** dùng events GC và allocation trong cửa sổ đủ dài để quan sát xu hướng, xác định classes/methods tạo nhiều objects.
3. **Histogram:** trong điều kiện an toàn, lấy class histogram để xem types tăng. Nếu cần, so sánh histogram ở hai thời điểm tương đương.
4. **Heap dump:** chỉ khi cần **object graph/GC roots** để tìm ai đang giữ references, và có dung lượng/permission/maintenance window thích hợp.
5. **MAT/dominator tree:** tìm dominators/retained sizes, path to GC roots, phân biệt strong/soft/weak references nếu analysis cung cấp.
6. **Kiểm code:** caches không eviction, `ThreadLocal` chưa clear, listeners, queues, sessions, classloader lifetimes, buffer references.
7. **Đưa ra fix:** loại retention không hợp lệ hoặc thêm bounded policy; không chỉ tăng `-Xmx` để che triệu chứng.
8. **Regression:** load test tương đương, heap sau GC ổn định và latency không xấu đi.

### Ví dụ “allocation cao nhưng không leak”

Một JSON serializer tạo rất nhiều strings tạm khi phục vụ 10.000 requests/s. JFR/allocation profiler thấy allocation rate cao; GC cũng tăng. Tuy nhiên **heap sau GC ổn định** và heap dump không cho thấy retained graph bất thường. Đây có thể là vấn đề **allocation pressure**, **không phải memory leak**.

### Ví dụ “retention cao nhưng không phải hot allocator”

Một global cache chứa các bản ghi lớn được tải vào rất ít lần nhưng giữ suốt thời gian chạy. Sampling allocation gần đây có thể không còn thấy nhiều allocations ở cache, trong khi heap dump có **retained size lớn** và path to GC roots qua static map. Lúc này heap dump trả lời đúng câu hỏi hơn.

## 17. Quy trình điều tra latency tăng nhưng CPU thấp

**Tình huống:** p99 HTTP tăng 200 ms → 4 s, CPU JVM chỉ 20%.

1. Kiểm metrics request, errors, downstream latency và pool saturation.
2. Dùng JFR timeline tại khoảng sự cố: `ThreadPark`, `JavaMonitorEnter`, socket/file read/write events và GC pauses (nếu được bật).
3. Chụp 2–3 thread dumps tại những mốc có ý nghĩa, không nhất thiết cần hàng trăm dumps.
4. So sánh stack các request worker: khóa, DB pool, socket read, queue, semaphore, sleep hay GC safepoint?
5. Dùng wall-clock profiler khi cần nhìn tần suất các waiting stacks; CPU profiling thường không bao trùm thread đang chờ.
6. Kiểm external service bằng tracing và network metrics; một stack `read()` không tự chứng minh bên nào chậm.
7. Sửa timeout/pool/backpressure/lock granularity hoặc upstream; đo lại p99 và throughput.

**Bẫy:** thấy hàng trăm threads ở `WAITING` rồi gọi là deadlock. Nhiều worker hợp lệ đang chờ queue có thể nằm ở `WAITING` suốt thời gian JVM khỏe mạnh. Phải xem ownership, progress, pool metrics và vòng chờ cụ thể.

## 18. Một gói lệnh chẩn đoán có giới hạn (tham khảo)

Các ví dụ dưới đây dành cho **HotSpot-based JDK** có `jcmd`/`jfr` và quyền attach hợp lệ. Thay `<PID>` bằng PID đã kiểm xác thực. **Không** dán nguyên các lệnh vào production nếu chưa có approval/đánh giá chi phí.

### Kiểm process và lệnh hỗ trợ

~~~bash
jcmd -l
jcmd <PID> help
jcmd <PID> help JFR.start
jcmd <PID> help Thread.print
jcmd <PID> help GC.heap_dump
~~~

### Recording ngắn có nhiều sự kiện để chẩn đoán

~~~bash
jcmd <PID> JFR.start name=Diag271 settings=profile duration=60s filename=/secure/diag271.jfr
~~~

Nếu chọn duration và filename, khi recording kết thúc theo thời hạn, file được tạo theo cấu hình; phải bảo đảm JVM còn chạy/không bị lỗi và đường dẫn ghi được. **Đây là ví dụ lệnh tài liệu, không phải output đã được kiểm từ live JVM tại đây.**

### Recording bounded liên tục và snapshot khi có sự cố

~~~bash
jcmd <PID> JFR.start name=IncidentRing settings=default maxage=30m maxsize=128m
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=IncidentRing filename=/secure/snapshot.jfr
jfr summary /secure/snapshot.jfr
jcmd <PID> JFR.stop name=IncidentRing
~~~

### Thread snapshot

~~~bash
jcmd <PID> Thread.print -l > /secure/threads.txt
~~~

### Histogram trước, heap dump sau khi đã cân nhắc

~~~bash
jcmd <PID> GC.class_histogram > /secure/class-histogram.txt
jcmd <PID> GC.heap_dump filename=/secure/heap.hprof
~~~

### CPU sampling profiler riêng (nếu đã cài đặt)

~~~bash
asprof -e cpu -d 30 -f /secure/cpu.html <PID>
~~~

**Không coi đây là một script chạy đồng loạt.** Đây là **menu thao tác**: chọn đúng thứ cần thiết, điều chỉnh duration/file size/permissions/traffic window. Chạy heap dump chỉ khi thực sự cần object graph. `asprof` không thuộc JDK; kiểm tài liệu phiên bản công cụ đã cài.

### Cần những quyền gì?

- `jcmd` thường cần cùng user/namespace và JVM bật khả năng attach; trong container có thể bị hạn chế bởi security settings.
- JFR file path là đường dẫn do target JVM dùng; tạo thư mục/permission trước.
- CPU profiling với native/OS events có thể cần quyền bổ sung; không nới quyền production chỉ vì tiện profiler.
- Nếu attach không hoạt động, đừng tự tắt policy bảo mật. Dùng JFR startup option có phê duyệt hoặc môi trường kiểm thử phù hợp.
- Ghi lại **timestamp, timezone, PID, JDK build, container/pod ID, CPU/memory limits và phiên bản ứng dụng** để kết quả phân tích có ngữ cảnh.

## 19. Phân biệt đúng các loại overhead và rủi ro

| Công cụ | Rủi ro chính | Cách giảm thiểu |
| --- | --- | --- |
| JFR default bounded | Event/buffer/disk overhead | Bounded size/time, chọn events hữu ích, đo impact |
| JFR profile | Nhiều stack/events/threshold thấp, có thể tăng overhead | Chạy có thời hạn, test trước, không bật sự kiện nặng không cần |
| Heap dump | JVM pause, full GC, I/O/disk khổng lồ, secrets | Maintenance window khi có thể, space/quota, access control, retention |
| Thread dump | Tạo snapshot nhiều thread, tác động latency ngắn | Chụp có mục tiêu, ít lần, bảo vệ file |
| CPU sampling profiler | Sample overhead, native permissions/symbols | Interval phù hợp, profile ngắn, allowlisted target |
| Wall profiler | Nhiều threads/waits gây volume dữ liệu | Filter threads và scope, chọn interval |
| Allocation profiler | Ghi nhiều allocation-related events | Sampling/rate limit, so sánh theo workload |
| Continuous tracing toàn phương thức | Có thể rất tốn CPU/disk | Không mặc định bật mọi method; dùng selective instrumentation |

Trong cloud/container, heap dump có thể **đầy ephemeral storage** và làm pod bị evict; JFR recording quá dài cũng có nguy cơ tương tự. Đừng bỏ qua filesystem limits, cgroup/CPU quota và GC ảnh hưởng latency.

## 20. Bảo mật chứng cứ: JFR và dump là dữ liệu nhạy cảm

**Heap dump** có rủi ro cao nhất vì object graph có thể chứa trực tiếp:

- Password/token/API key, session cookie, Authorization headers;
- Email/số điện thoại/PII hoặc bản ghi dữ liệu khách hàng;
- Payload request/response, cache và cấu hình kết nối;
- Khóa/mật mã ở dạng bytes đang được lưu trong heap, dù nguồn khóa nằm ở secret store.

**JFR/thread dump/profiles** có thể lộ method/class/package names, endpoint/đường dẫn, tên thread và metadata của ứng dụng; tùy custom event có thể chứa dữ liệu cụ thể.

Biện pháp tối thiểu:

1. Chỉ thu thập khi có **mục đích, quyền và thời hạn retention**.
2. Tạo file trong thư mục **quyền truy cập hạn chế**, không đặt trong web static directory hoặc shared temp không kiểm soát.
3. Mã hóa và kiểm quyền khi chuyển file sang máy phân tích.
4. Không đưa file thô vào issue tracker/chat công khai.
5. Không bật custom JFR events chứa raw payload, token hay PII.
6. Đặt retention/cleanup phù hợp. Xóa file theo quy định sau khi phân tích.
7. Ghi audit: ai chạy, ở môi trường nào, thời gian nào, mục đích gì.
8. Với SaaS/multi-tenant, cân nhắc redaction/approval theo chính sách dữ liệu của tổ chức.

## 21. Những suy luận sai cần tránh

| Nhận định sai | Vì sao sai | Cách đọc đúng |
| --- | --- | --- |
| “JFR là heap dump gọn.” | JFR là event stream | Dùng heap dump để xem object graph |
| “JFR có stack sample nên không cần profiler khác.” | JFR execution sampling có mục tiêu/độ chi tiết riêng | Chọn profiler phù hợp nếu cần CPU/native/wall detail |
| “Không thấy event = không có sự cố.” | Event có thể disabled/threshold bỏ qua | Kiểm recording settings và thời lượng |
| “default.jfc luôn <1% overhead mọi môi trường.” | Overhead phụ thuộc workload/settings | Đo impact thực, cap event/duration |
| “profile.jfc phù hợp bật vô hạn trong mọi production.” | Có thể tốn hơn default | Chạy có giới hạn/approval |
| “Heap dump cho thấy method đã cấp phát object.” | Snapshot giữ object graph, không phải full allocation history | Dùng allocation events/profiler |
| “Object lớn nhất là memory leak.” | Có thể là cache/lifecycle hợp lệ | Retained path, growth across GC và business context |
| “Allocation rate cao = leak.” | Object có thể chết nhanh | Theo dõi retained heap/GC |
| “Một thread dump đủ chứng minh deadlock.” | Một WAITING có thể bình thường | Xác nhận vòng chờ/owner, nhiều ảnh chụp |
| “RUNNABLE nghĩa là đang đốt CPU.” | RUNNABLE có thể gồm native/I/O và scheduling | Dùng CPU samples/thread CPU metrics |
| “BLOCKED nghĩa là CPU cao.” | BLOCKED là chờ monitor | Xem lock owner/contention |
| “Thread dump là CPU profiler.” | Chỉ snapshot stack, không thống kê đại diện | Dùng sampling trên một cửa sổ |
| “CPU profiler chứng minh request chậm vì mạng.” | CPU samples có thể bỏ lỡ wait | Dùng JFR I/O/wall-clock/tracing |
| “50% samples nghĩa là 50% thời gian của mọi request.” | Sample % không tương đương per-request latency | Xem metric/profile window |
| “Wall-clock hot frame là lỗi CPU.” | Có thể là chờ queue/sleep hợp lệ | Phân loại running vs waiting |
| “JFR heap statistics không tốn overhead.” | Một số heap statistics có GC/impact đáng kể | Bật có mục tiêu và thời hạn |
| “GC.heap_dump là thao tác nhẹ, chụp khi nào cũng được.” | High impact, file lớn, có thể full GC | Chuẩn bị capacity và incident policy |
| “Thread dump không nhạy cảm vì chỉ là text.” | Có thể chứa chi tiết code/paths/names | Bảo vệ file |
| “.jfr nghĩa là chỉ do JDK JFR tạo.” | Profiler khác có thể xuất JFR-compatible data | Kiểm provenance/event metadata |
| “PID giống nhau trên host và container.” | PID namespaces có thể khác | Xác thực đúng JVM target |
| “Có jcmd là sẽ attach được mọi JVM.” | Attach/permission/security có giới hạn | Xem policy và runtime version |

## 22. Ma trận kiểm thử kiến thức và công cụ

| Tình huống kiểm thử | Cách kiểm | Điều kiện PASS |
| --- | --- | --- |
| JFR custom event | Chạy `JfrRecordingDemo` | File tạo được; đọc đúng **3** `lesson.WorkUnit` |
| JFR command availability | `jcmd <PID> help JFR.start` | JVM mục tiêu hỗ trợ command và quyền attach |
| JFR recording bounded | `JFR.start/JFR.check/JFR.dump` | Snapshot hợp lệ, có metadata/events cần thiết |
| JFR empty method sample | Kiểm event settings/time window | Không kết luận workload không dùng CPU |
| Thread monitor contention | `ThreadSnapshotDemo` | `BLOCKED`, lock owner đúng fixture |
| Thread dump production | `Thread.print -l` | Có target threads/frames và thời điểm phù hợp |
| Deadlock test | Test có vòng chờ kiểm soát, analysis tool | Xác minh lock ownership cycle, không chỉ WAITING |
| Allocation pressure | JFR allocation events/profiler, GC metrics | Nhìn được allocation hotspot/trend |
| Heap retention | HPROF + MAT | Truy được dominator/GC roots đáng nghi |
| Full heap dump impact | Benchmark ở staging | Ước lượng pause, I/O, disk trước production |
| CPU hot loop | CPU sampling ở khoảng đủ dài | Hot path có mẫu thống kê, tái lập được |
| I/O wait | Tracing, JFR I/O, wall profile | Latency liên hệ đúng downstream/wait stack |
| File quyền truy cập | Permission/audit/retention test | Không lộ artifact cho người không có quyền |
| JDK update | Re-run diagnostics smoke tests | Commands/format/events mục tiêu vẫn hoạt động |

### Lưu ý về tính tái lập

- **Hai Java demos** ở mục 8 và 11 đã được biên dịch với `javac --release 11` và chạy thực tế.
- **Các ví dụ `jcmd` gắn vào JVM khác và `asprof`** được trình bày theo tài liệu và phải được chạy lại trên JVM/OS production phù hợp. Chúng không phải phần stdout đã kiểm nghiệm trong hai Java demos.
- Không assert toàn bộ nội dung JFR recording vì số JVM events phụ thuộc JDK/provider/OS. Chỉ assert custom events của fixture.
- Không dùng `Thread.sleep(1000)` rồi cho rằng chắc chắn thread đang BLOCKED. Demo dùng `CountDownLatch` và kiểm trạng thái với deadline.
- Khi đo production, ghi đầy đủ khoảng thời gian, JDK build, cấu hình JFR/profiler, số mẫu và các metric liên quan.

## 23. Checklist điều tra production

- [ ] Đã xác định **câu hỏi** cần trả lời trước khi chọn công cụ.
- [ ] Có metrics/timestamp/timezone/host/container/PID và version ứng dụng.
- [ ] Với CPU cao: chọn JFR execution samples hoặc CPU sampling profiler theo nhu cầu.
- [ ] Với latency thấp CPU: xem JFR lock/I/O/park, thread dumps và wall profile/traces.
- [ ] Với memory leak: xem heap **sau GC**, rồi dump khi cần graph/GC roots.
- [ ] Không dùng heap dump làm thay thế cho allocation profile.
- [ ] Không dùng thread dump một lần như số liệu %CPU hoặc bằng chứng leak.
- [ ] Với JFR, chọn `default` vs `profile` có chủ đích, kiểm event settings/threshold.
- [ ] Có giới hạn duration/maxsize/maxage/disk, và biết nơi file được ghi.
- [ ] Đã đánh giá pause/GC/disk/memory cost trước `GC.heap_dump`.
- [ ] Profiler ngoài JDK được cài đặt/phê duyệt đúng version/platform/permission.
- [ ] Recording/profile window khớp thời điểm incident; có baseline để so sánh.
- [ ] Không diễn giải số mẫu quá ít như kết luận thống kê chắc chắn.
- [ ] Tệp JFR/HPROF/threads/flame graph được xử lý như thông tin nhạy cảm.
- [ ] Có kết quả đo **sau khi sửa** để xác nhận latency, CPU, GC và memory cải thiện.
- [ ] Không dùng cờ license/unlock thương mại JFR từ hướng dẫn JDK 8 cũ cho Java 11+.
- [ ] Kiểm lại `jcmd help`/tài liệu của đúng JDK đang chạy thay vì giả định lệnh của bản mới có trên Java 11.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Cần biết object nào đang giữ 2 GB heap và đường tham chiếu từ GC root. Dùng JFR hay heap dump?

**Đáp án:** **Heap dump** với MAT/dominator tree/path-to-GC-roots. JFR allocation events có thể gợi ý chỗ cấp phát nhưng không thay thế full retained object graph.

**Câu 2.** Cần biết p99 tăng đột ngột trong 90 giây kèm GC/lock/I/O. Dùng gì?

**Đáp án:** **JFR recording** có timestamp và các event phù hợp, kết hợp tracing/metrics. Thread dumps có thể bổ trợ tại những mốc quan trọng.

**Câu 3.** Một thread `RUNNABLE` trong thread dump có chắc đang dùng hết một core CPU không?

**Không.** Trạng thái chỉ là snapshot theo JVM semantics; phải dùng CPU metrics/sampling để đánh giá mức dùng CPU.

**Câu 4.** Sampling profiler cho thấy method A chiếm 45% samples. Có thể nói “45% request latency nằm ở A” không?

**Không.** Sample % phụ thuộc metric (CPU/wall/alloc) và cửa sổ profiling, không phải phân bổ độ trễ từng request.

**Câu 5.** JFR có phải luôn là “profiling không lấy mẫu” không?

**Không.** JFR có **execution sampling** và nhiều sự kiện được instrument trong JVM. “JFR” là hệ thống recording, không đối lập tuyệt đối với sampling.

**Câu 6.** Vì sao một heap dump không cho biết code nào đã tạo tất cả objects?

**Vì** heap dump ghi **trạng thái object graph hiện tại**, không phải trace cấp phát của từng object theo thời gian. Muốn allocation sites cần JFR allocation events hoặc profiler allocation.

**Câu 7.** `GC.class_histogram` khác `GC.heap_dump` thế nào?

**Histogram** cho class counts/sizes tổng hợp; **heap dump** có object references để phân tích retained graph. Cả hai có thể có chi phí, nhưng heap dump nặng hơn nhiều trong nhiều trường hợp.

**Câu 8.** Thấy hàng trăm threads ở `WAITING`, có đủ để kết luận deadlock không?

**Không.** Cần xem lock owners, vòng chờ, stack, tiến triển và workload. Nhiều worker đang chờ queue hợp lệ.

**Câu 9.** Vì sao JFR `default.jfc` ít events hơn `profile.jfc`?

**Vì** default cân bằng dữ liệu/overhead để chạy lâu, còn profile thường lấy thêm chi tiết khi cần điều tra ngắn hạn. Không bật profile vô hạn nếu chưa đo overhead.

**Câu 10.** JFR/heap dump có thể đẩy lên issue tracker công khai vì “chỉ là file chẩn đoán” không?

**Không.** Cả hai có thể chứa metadata và bí mật, đặc biệt HPROF có raw object data. Cần permission, encryption, redaction và retention.

**Câu 11.** Một file `.jfr` có thể là output của async-profiler chứ không chỉ engine JFR JVM không?

**Có.** Một số profiler ghi data tương thích JFR. Xem provenance/metadata, event semantics và công cụ thu thập.

**Câu 12.** Heap vẫn ổn định sau GC nhưng allocation rate rất cao. Đó là memory leak?

**Không nhất thiết.** Đây có thể là allocation pressure của objects ngắn hạn; cần theo dõi retained heap/roots để kết luận leak.

## 25. Tài liệu tham khảo chính thức và hiện hành

1. [Oracle Java 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): `jcmd`, JFR, `GC.heap_dump`, `GC.class_histogram` và `Thread.print`.
2. [Oracle JDK 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): chẩn đoán JVM hiện đại, JFR/JMC, thread/heap dump, command overview.
3. [Oracle JDK 27 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc`, event settings và overhead trade-offs.
4. [dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): recording options, configurations, custom events và cách cấu hình phù hợp JDK.
5. [Oracle JDK 26 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU/GC/lock/latency events, giới hạn sampling và heap statistics overhead.
6. [Oracle Java 11 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo/điều khiển recording bằng Java API.
7. [Oracle Java 11 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): khai báo custom events.
8. [Oracle Java 11 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc events từ `.jfr`.
9. [Oracle Java 11 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/ThreadMXBean.html) và [`ThreadInfo`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/ThreadInfo.html): thread stack snapshot, lock owner và deadlock APIs.
10. [Oracle Java 11 — `Thread.State`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Thread.State.html): semantics của `RUNNABLE`, `BLOCKED`, `WAITING` và `TIMED_WAITING`.
11. [async-profiler — Official documentation](https://github.com/async-profiler/async-profiler) và [Profiler options](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilerOptions.md): các chế độ sampling CPU/wall/alloc, interval, kết quả và quyền thực thi.
12. [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/): phân tích HPROF, dominator tree và paths-to-GC-roots.

**Kết luận:** **JFR** cung cấp bối cảnh sự kiện **theo thời gian** và có thể lấy mẫu hot methods; **heap dump** cung cấp **đồ thị object còn được giữ trong heap**; **thread dump** cho biết **stack/trạng thái thread tại một thời điểm**; **sampling profiler** thống kê **những đường gọi xuất hiện trong các mẫu CPU/wall/alloc**. Chọn công cụ theo câu hỏi, kiểm overhead và quyền truy cập, phối hợp nhiều nguồn chứng cứ và **đo lại sau khi sửa**. Những nguyên tắc này phù hợp từ Java 11 đến JDK hiện đại.