# 15.1. JDK Mission Control là công cụ riêng để mở và phân tích bản ghi

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **JDK Flight Recorder (JFR)**, tệp **`.jfr`**, tiện ích dòng lệnh **`jcmd`/`jfr`** và ứng dụng đồ họa **JDK Mission Control (JMC)**.
- Giải thích vì sao có JDK và tạo được bản ghi JFR **không đồng nghĩa** máy đã cài JMC.
- Tạo một bản ghi, chuyển tệp sang máy phân tích, mở bằng JMC và khảo sát các event trong đúng khoảng thời gian.
- Dùng **Automated Analysis Results**, Memory, Code, Threads/Locks, I/O và Events để tìm dấu hiệu cần điều tra, đồng thời nhận biết giới hạn của dữ liệu được thu thập.
- Tránh kết luận sai từ cảnh báo tự động, mẫu CPU, thống kê allocation, ngưỡng event hoặc khoảng thời gian không bao phủ sự cố.

**Môi trường:** Java 17+ phù hợp với ví dụ có API `jdk.jfr`; tên menu và chi tiết giao diện JMC có thể hơi khác tùy bản phát hành. JMC là ứng dụng desktop có bản phân phối riêng, có thể chạy trên máy khác máy sinh ra recording.

## 1. Tách rõ nơi ghi dữ liệu và nơi phân tích

**JDK Flight Recorder (JFR)** là cơ chế ghi sự kiện chẩn đoán/profiling tích hợp trong JVM/JDK. Các sự kiện có thể mô tả hoạt động CPU sampling, garbage collection, cấp phát, thread, lock, I/O, môi trường JVM và sự kiện do ứng dụng tự định nghĩa. JFR lưu dữ liệu kèm thời gian, thuộc tính, tên thread và stack trace **khi loại event/cấu hình cho phép**.

**JDK Mission Control (JMC)** là **bộ công cụ đồ họa phân tích** các dữ liệu đó. JMC có khả năng kết nối/quan sát JVM đang chạy qua các cơ chế tương ứng, nhưng chức năng mở một tệp `.jfr` đã có là **phân tích offline** và không cần tiến trình gốc tiếp tục chạy.

| Thành phần | Chức năng chính | Điểm cần nhớ |
|---|---|---|
| **JFR trong JVM** | Phát và thu thập event từ hoạt động runtime | Thu thập được những gì tùy cấu hình event, thời gian và JVM |
| **Tệp `.jfr`** | Dữ liệu recording dạng **binary** | Không phải text log, heap dump `.hprof` hay core dump |
| **`jcmd`** | Gửi lệnh `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` tới JVM đang chạy | Công cụ dòng lệnh đi cùng JDK phù hợp; cần attach/quyền đối với JVM |
| **`jfr`** | Kiểm tra tệp recording đã tạo qua CLI (ví dụ `summary`, `print`) | Hữu ích khi máy không có giao diện đồ họa |
| **JMC** | Mở và phân tích recording với timeline, bảng, biểu đồ, luật gợi ý | **Cài/chạy riêng** nếu bản JDK không đóng gói JMC; không bắt buộc có JVM gốc để mở `.jfr` |

Luồng cơ bản:

```text
Java application + JVM (có JFR)
       |
       | start recording (CLI, JVM option, API hoặc JMC)
       v
   JFR events
       |
       | dump/stop -> lưu file
       v
  incident.jfr (binary file)
       |
       | sao chép sang máy phân tích nếu cần
       v
   JDK Mission Control
       |
       +-- Automated Analysis Results
       +-- Memory / Code / Threads / Locks / I/O / System
       +-- Event Browser, Timeline, Stack Trace
       |
       v
   Giả thuyết -> đối chiếu code, logs, metrics -> xác minh
```

**Hai nhầm lẫn thường gặp:**

1. `java -version` hoặc lệnh `jfr` chạy được **không chứng minh JMC đã cài**. JMC cần tải/cài từ bản phân phối riêng phù hợp hệ điều hành; thông thường không thể giả định có lệnh `jmc` trên `PATH`.
2. Muốn đọc `incident.jfr` bằng JMC **không cần** mở JMX/management port tới production: chỉ cần tệp recording hợp lệ. Kết nối live là một workflow bổ sung, có điều kiện truy cập riêng.

## 2. Chuẩn bị JDK Mission Control đúng cách

### 2.1. Lấy ứng dụng JMC

Tìm bản phát hành JMC phù hợp hệ điều hành và Java runtime để chạy ứng dụng từ nguồn chính thức:

- Trang [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html) cung cấp download, hướng dẫn và thông tin hỗ trợ.
- Dự án [OpenJDK JMC](https://github.com/openjdk/jmc) chứa mã nguồn và thông tin về các bản phân phối/dự án.

JMC có giao diện ứng dụng desktop dựa trên Eclipse RCP. Việc cài đặt thường là tải gói tương ứng hệ điều hành, giải nén/cài ứng dụng và khởi chạy executable được phân phối kèm. **Không áp dụng máy móc lệnh cài đặt của một bản JMC cho mọi JDK/OS**: kiểm tra tài liệu của chính bản JMC đã chọn.

Bạn có thể tạo recording trên máy Linux/server và mở nó ở JMC chạy trên Windows/macOS/Linux của máy phát triển. Không cần cài JMC trên server chỉ để phân tích tệp offline.

### 2.2. Xác minh ba lớp môi trường

Trên máy có JDK:

```bash
java -version
jcmd -h
jfr help
```

Những lệnh này kiểm tra **Java/JFR CLI**, không phải lệnh khởi chạy JMC. Sau khi cài, mở **JDK Mission Control** từ executable/menu của bản phân phối. Tệp `.jfr` có thể đến từ Java/JDK khác phiên bản JMC; mức tương thích định dạng, event và khả năng hiển thị phụ thuộc bản công cụ. Khi một tệp không mở được, hãy kiểm tra phiên bản JMC, phiên bản JDK tạo recording và trạng thái tệp trước khi khẳng định file hỏng.

### 2.3. Cách mở tệp

1. Khởi chạy ứng dụng **JDK Mission Control**.
2. Trong menu ứng dụng, chọn **File → Open File...** (tên có thể hơi khác theo phiên bản), chọn tệp `incident.jfr`; hoặc mở recording từ danh sách/file browser trong JMC.
3. Chờ JMC đọc/index recording và hiển thị trang phân tích. Với các bản JMC hiện hành, điểm bắt đầu thường là **Automated Analysis Results**.
4. Xác nhận recording đúng **ứng dụng, JVM, khoảng thời gian**, rồi mới đọc cảnh báo hoặc biểu đồ.

Không dùng trình soạn thảo văn bản để xem dữ liệu binary `.jfr` rồi kết luận file rỗng khi thấy ký tự lạ. Nếu chưa cài JMC, `jfr summary` hoặc `jfr print` giúp kiểm tra tệp bằng CLI.

## 3. Tạo recording JFR để mở trong JMC

Có nhiều đường tạo file. Chọn đường phù hợp vòng đời của JVM và mục đích chẩn đoán.

### 3.1. Bắt đầu khi ứng dụng khởi động

Ví dụ với ứng dụng Java đóng gói thành JAR chạy được:

```bash
java -XX:StartFlightRecording=name=Startup,duration=60s,settings=profile,filename=startup.jfr -jar app.jar
```

Khi cấu hình `duration` kết thúc, JFR ghi tệp `startup.jfr` theo đường dẫn yêu cầu. Đây là recording một khoảng thời gian xác định; nó thuận tiện khi cần đo **startup** hoặc tái hiện một kịch bản trong môi trường kiểm soát. Thay `app.jar` và thời lượng bằng ứng dụng/trường hợp thực tế.

**`settings=default` và `settings=profile` khác nhau:** preset `profile` thường thu thêm event phục vụ profiling, đổi lại tăng overhead/dung lượng. Không coi `profile` là mặc định tối ưu cho mọi production workload.

### 3.2. Ghi trên JVM đang chạy bằng jcmd

Trước hết xác định PID của JVM mục tiêu:

```bash
jcmd -l
```

Trong những lệnh sau, **thay `<PID>` bằng số PID thật**; các dòng lệnh minh họa không chạy nguyên văn với dấu ngoặc nhọn:

```bash
jcmd <PID> JFR.start name=Incident settings=profile duration=2m filename=incident.jfr
jcmd <PID> JFR.check
```

Khi recording hoàn tất sau 2 phút, JFR có thể ghi `incident.jfr`. Muốn chụp một phần dữ liệu **trong lúc recording còn chạy**:

```bash
jcmd <PID> JFR.dump name=Incident filename=incident-now.jfr
```

**`JFR.dump` không dừng recording đang chạy.** Với một recording chạy liên tục, có thể tự chọn thời điểm dump hoặc gọi `JFR.stop name=Incident filename=incident-final.jfr` để kết thúc và lưu. Hãy chỉ chạy `stop` khi thực sự muốn dừng; recording có `duration` thường tự kết thúc khi hết hạn.

`jcmd` phải có khả năng truy cập JVM mục tiêu, thường cùng máy và quyền người dùng phù hợp. Container, JVM attach bị tắt hoặc môi trường bị khóa có thể khiến lệnh không kết nối được. Không cần mở port JMX cho workflow `jcmd` local.

### 3.3. Tạo recording từ JMC khi đã kết nối JVM

JMC cũng có phần **JVM Browser** để khám phá JVM có thể quản lý. Khi tìm được đúng JVM:

1. Nhấp phải JVM trong **JVM Browser**, chọn **Start Flight Recording...**.
2. Chọn recording **có thời lượng** hay **liên tục**, tên/tệp đích và template.
3. Chọn loại event, threshold, khả năng lấy stack trace theo nhu cầu.
4. Bắt đầu recording, rồi dump hoặc đợi recording có thời lượng kết thúc.
5. Mở recording vừa có trong JMC để phân tích.

Đường này cần JMC kết nối đúng JVM qua môi trường/quyền được hỗ trợ; nếu chỉ có file `.jfr` từ production, **bỏ qua bước kết nối** và mở file offline như mục 2.3.

## 4. Thực hành Java: tự tạo .jfr mà không cần server hay JMX

Ta tạo một **custom JFR event** gồm tên bước công việc, thời điểm bắt đầu, thời lượng và stack trace. Ví dụ chạy độc lập bằng **Java 17+**, tự ghi ra `mission-control-demo.jfr`; sau đó mở file trong JMC.

Tạo tệp **`MissionControlDemo.java`**:

```java
import java.nio.file.Path;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class MissionControlDemo {
    @Name("demo.WorkUnit")
    @Label("Demo work unit")
    static class WorkUnit extends Event {
        @Label("Task")
        String task;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("mission-control-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkUnit.class).withStackTrace();
            recording.start();

            for (int i = 1; i <= 3; i++) {
                WorkUnit event = new WorkUnit();
                event.task = "batch-" + i;
                event.begin();
                Thread.sleep(30);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Created: " + output.getFileName());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp nguồn:

```bash
javac MissionControlDemo.java
java MissionControlDemo
jfr summary mission-control-demo.jfr
jfr print --events demo.WorkUnit mission-control-demo.jfr
```

**Dòng stdout chính xác do chương trình in:**

```text
Created: mission-control-demo.jfr
```

Trong phần `jfr print`, phải thấy **ba event** thuộc type `demo.WorkUnit`, với `task = "batch-1"`, `"batch-2"`, `"batch-3"`. Các giá trị `startTime`, `duration` (thường ít nhất cỡ 30 ms do `sleep`), `javaThreadId` và line number trong stack trace **thay đổi theo lần chạy và JDK**, nên không đưa chúng thành stdout cố định. Ví dụ đã được kiểm tra thực tế với OpenJDK 24: biên dịch thành công, tệp `.jfr` được tạo, `jfr print` đọc được cả ba event và stack trace.

**Giải thích mã:**

- `@Name("demo.WorkUnit")` đặt tên event type để lọc trong CLI/JMC; `@Label` đặt nhãn dễ đọc.
- `Recording` tạo một phiên ghi JFR trong chính JVM. `enable(WorkUnit.class).withStackTrace()` bật event và thu stack trace cho type này.
- `event.begin()`, `event.end()` đo khoảng thời gian; `commit()` phát event vào recording.
- `recording.stop()` rồi `dump(Path)` lưu recording; khối `try` đóng tài nguyên.
- Tệp có thể có **những event JVM khác** ngoài ba event custom, tùy recording/JDK. Dùng bộ lọc `demo.WorkUnit` để phân biệt.
- Tệp này có dữ liệu giúp chứng minh **mở/analyze recording**, chưa đủ để tự tạo ra nút thắt CPU, memory leak hoặc lock contention thực tế.

### Mở ví dụ trong JMC

1. Chạy chương trình và xác nhận file `mission-control-demo.jfr` tồn tại.
2. Trong JMC chọn **File → Open File...**, trỏ tới tệp đó.
3. Tìm mục **Events / Event Browser** (tên/đường dẫn UI tùy phiên bản), lọc type `demo.WorkUnit`.
4. Kiểm tra ba event, giá trị `task`, thời lượng và stack trace; chọn từng event để xem chi tiết.
5. So sánh số event trong JMC với lệnh `jfr print --events demo.WorkUnit mission-control-demo.jfr`.

Đây là kiểm tra end-to-end: **Java code → JFR binary file → JMC mở file → thấy event**. Không cần kết nối live tới JVM đã chạy xong.

## 5. Đọc giao diện JMC theo câu hỏi chẩn đoán

Các bản JMC có thể đổi tên trang hoặc bố trí, nhưng luồng phân tích tương đối ổn định: bắt đầu ở **Automated Analysis Results**, lọc khoảng thời gian, rồi đi tới trang chuyên sâu và event cụ thể.

### 5.1. Automated Analysis Results: gợi ý, chưa phải kết luận

JMC áp dụng các **analysis rules** lên những event thực sự có trong file, cho biết những điểm đáng chú ý qua điểm số/cảnh báo. Một số bản hiển thị màu vàng/đỏ cho kết quả cần ưu tiên và có nút xem cả kết quả OK.

Cách dùng:

1. Ghi lại dấu hiệu được rule nêu: tên hiện tượng, thời gian, mức độ và dữ liệu liên quan.
2. Nhấp vào kết quả để chuyển tới biểu đồ/event giải thích cảnh báo.
3. Thu hẹp khoảng thời gian của sự cố và đối chiếu log/metrics/request traces.
4. Kiểm tra recording có **event cần thiết** hay không trước khi kết luận “không thấy cảnh báo nghĩa là bình thường”.

**Rule score không phải chứng minh root cause.** “Nhiều allocation”, “GC pause dài” hoặc “lock contention” là chỉ dấu cần kiểm tra ngữ cảnh workload, mục tiêu latency và mối quan hệ nhân quả.

### 5.2. Chọn đúng time range trước khi đọc biểu đồ

JFR là tập event **có timestamp**; một recording có thể chứa startup, warm up, thời gian bình thường và thời gian sự cố. Hãy chọn khoảng sự cố trong timeline/range navigator và bảo đảm các bảng/biểu đồ đang phản ánh phạm vi đó.

Ví dụ một ứng dụng có spike độ trễ vào phút 02:10–02:20 của recording dài 10 phút:

- Tập trung vào cửa sổ xảy ra spike và so sánh với một cửa sổ bình thường ngay trước đó.
- Nếu GC pause trùng thời điểm latency spike, đó là **tương quan theo thời gian**; cần xem pause duration, thread behavior và dữ liệu request để kiểm tra quan hệ nhân quả.
- Nếu recording bắt đầu **sau** sự cố hoặc đã hết trước lúc sự cố, JMC không thể tự khôi phục những event không từng được ghi.

Khi đọc event, kiểm tra timestamp, timezone của UI/máy và khoảng coverage để tránh so sai thời gian với application logs.

### 5.3. Trang nào phù hợp vấn đề nào?

| Nghi vấn | Nơi thường xem trong JMC | Các dữ liệu cần xem và giới hạn |
|---|---|---|
| **CPU cao** | Code / Method Profiling / Hot Methods | Execution samples, stack traces, thread context; tỷ lệ mẫu **không phải** thời gian chính xác tuyệt đối của từng lời gọi |
| **Allocation pressure** | Memory / Allocation / TLAB | Điểm cấp phát, class, thread, stack, allocation rate; sự kiện **sampling** không có nghĩa mọi object đều được ghi |
| **GC pause và heap behavior** | Memory / Garbage Collections / JVM Internals | Thời điểm và duration GC, heap before/after, tần suất; không tự chứng minh leak |
| **Lock contention** | Threads / Locks / Java Monitor | Các event blocked/wait và stack; threshold event có thể bỏ những lần chờ ngắn |
| **I/O latency** | I/O / File / Socket | Event duration, thread, địa chỉ/đối tượng và stack khi có; phải xem event có bật và threshold phù hợp |
| **Thread behavior** | Threads / Event Browser | Hoạt động/đợi/chạy theo các event đã ghi; không giả định đây là snapshot đầy đủ mọi thread |
| **Môi trường bất thường** | System / Environment / JVM Information | JDK, OS, cấu hình runtime, CPU/cgroup nếu event hỗ trợ |
| **Custom event** | Events / Event Browser | Lọc theo type, thuộc tính và thread; kết quả phụ thuộc sự kiện do ứng dụng thực sự phát |

Không phải mọi recording đều chứa đủ các view/stack. Nếu event type thiếu hoặc bị tắt, trang tương ứng có thể rỗng; không nên đồng nhất “không có dữ liệu” với “không có vấn đề”.

## 6. Workflow chẩn đoán có thể lặp lại

### 6.1. Phân tích spike độ trễ

**Triệu chứng:** p99 latency tăng rõ trong khoảng một phút.

1. Xác định cửa sổ spike trong **ứng dụng metrics/logs** và kiểm tra recording thực sự bao phủ khoảng đó.
2. Trong JMC đặt đúng **time range**, xem Automated Analysis Results để lấy các giả thuyết đầu tiên.
3. Xem **I/O** có các socket/file operations lâu; xem **Threads/Locks** có monitor contention; xem **Memory/GC** có pause trùng thời điểm; xem **Code** có method execution samples nổi bật.
4. Mở các event đặc trưng, kiểm tra timestamp, duration, thread, stack trace và method/class liên quan.
5. Đối chiếu với request ID, downstream response time, database metrics và thread dump/CPU OS nếu cần.

Ví dụ, socket read 400 ms trên một request chậm là dấu hiệu chờ I/O; không thể quy 400 ms đó thành “CPU Java dùng 400 ms”. CPU sampling có thể không thấy nhiều mẫu của thread đang chờ I/O dù latency lớn.

### 6.2. Phân tích CPU nóng

**Triệu chứng:** CPU của process tăng, throughput giảm.

1. Ghi JFR ở khoảng có tải, sử dụng event execution sampling được bật (thường cần cấu hình profiling phù hợp).
2. Trong **Code/Method Profiling**, xem nhóm stack/method xuất hiện thường xuyên ở mẫu.
3. Đối chiếu thread, event time range, JVM GC/compiler activity và CPU ở OS.
4. Xem code, kiểm chứng bằng benchmark/profiler/trace tại vị trí nghi vấn.

**Lưu ý:** Sampling có sai lệch thống kê, chịu chu kỳ lấy mẫu, safepoint/configuration và stack depth. “25% samples” không được phát biểu thành “method chạy đúng 25% tổng wall-clock time”. Các method ngắn/ít được lấy mẫu vẫn có thể quan trọng với từng request.

### 6.3. Phân tích memory và GC

**Triệu chứng:** GC nhiều hoặc heap tăng dần.

1. Dùng **Memory** để xem heap usage, allocation rate và pause/event GC trong khoảng sự cố.
2. Xem loại đối tượng và stack của các event allocation có thu thập.
3. So sánh nhiều giai đoạn workload tương đương; chú ý warm up và các cache hợp lệ.
4. Khi nghi leak thực sự, dùng heap dump/histogram/retained-object analysis thích hợp để xác định **đối tượng còn sống**, vì JFR allocation samples không phải bằng chứng về **retained heap**.

Giới hạn rất quan trọng: một class có nhiều allocation **không nhất thiết** chiếm nhiều heap sau GC; nhiều đối tượng ngắn hạn được tạo rồi giải phóng là hiện tượng phổ biến.

## 7. Vì sao JMC có thể không hiện điều bạn mong chờ?

Tệp JFR được tạo từ **event có bật**, thời lượng và threshold cụ thể. Phân tích chất lượng recording trước khi chẩn đoán ứng dụng.

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| JMC mở được file nhưng không có CPU method samples | Sampling event tắt, duration quá ngắn, workload chưa chạy | `jfr summary`, event settings, ghi lại có profiling phù hợp |
| Không thấy lock contention dù request bị chậm | Sự cố do I/O hoặc event monitor threshold quá cao | Kiểm tra I/O và threshold/event count; dùng thêm thread dump |
| Không thấy stack trace | Event type không bật stack, cấu hình stack trace bị tắt, giới hạn stack depth | Xem cấu hình event; thu recording khác nếu cần |
| Một vài event allocation đại diện lượng bytes rất lớn | Event sampling/ước lượng, không liệt kê từng object | Phân biệt sample count, estimated allocated bytes và retained heap |
| Automated Analysis Results không cảnh báo | Rule không thấy vấn đề theo dữ liệu/threshold của nó, hoặc recording không đủ | Đọc trực tiếp event và đối chiếu metrics/logs |
| JMC có cảnh báo nhưng app vẫn đạt SLO | Ngưỡng rule chung không khớp yêu cầu thực tế | Xem workload, SLA/SLO, mức độ/tần suất và ảnh hưởng thực |
| JMC không mở/không hiểu event mới | Recording không hoàn chỉnh, version/format hoặc event không được phiên bản JMC hỗ trợ | `jfr summary`, kiểm tra phiên bản JMC/JDK và file integrity |
| JMC không liệt kê JVM production | Vấn đề live connection, JMX, quyền truy cập hoặc network | Nếu chỉ cần phân tích, lấy file `.jfr` và mở offline |

### Chọn cấu hình ghi phù hợp

Hai preset phổ biến của JDK là **`default.jfc`** và **`profile.jfc`**; template dùng để quyết định event nào, threshold và stack trace. `profile` thường có nhiều dữ liệu hơn và có thêm chi phí. Nếu cần các event custom, hãy bật event type tương ứng. Nếu cần bắt một sự cố hiếm, hãy thiết kế **thời gian lưu, giới hạn dung lượng, chu kỳ ghi/dump** đủ để file chứa đúng giai đoạn cần điều tra.

JFR có mục tiêu overhead thấp ở cấu hình thông dụng, **không có nghĩa bằng 0**. Bật mọi event, giảm ngưỡng xuống quá thấp, bật stack trace cho sự kiện tần suất cực lớn hoặc thu heap root có thể tăng chi phí CPU, I/O và dung lượng. Kiểm tra tác động khi thay cấu hình trên production.

## 8. Cách phối hợp JMC và các công cụ khác

- **`jfr summary incident.jfr`:** xác nhận file đọc được, xem những loại event có trong recording và số lượng/tổng kích thước. Đây là bước nhanh trước khi mở GUI.
- **`jfr print --events jdk.GarbageCollection incident.jfr`:** xem một event type cụ thể bằng text nếu recording có event đó; loại event có sẵn phụ thuộc phiên bản/cấu hình.
- **JMC:** khai thác timeline, bảng, lọc event, biểu đồ, stack và automated analysis; thuận tiện để phát hiện mẫu theo thời gian.
- **Application logs/metrics/traces:** giải thích hiện tượng tác động đến request thật, định danh transaction và downstream; JMC không tự thay thế correlation ID ứng dụng.
- **Thread dump, heap dump, OS/container metrics:** bổ sung khi cần snapshot chính xác về lock/thread, retained heap, RSS/cgroup hoặc sự cố ngoài phạm vi event.

Không đánh đồng các tệp: **`.jfr`** lưu sự kiện chẩn đoán theo thời gian; **`.hprof`** là heap dump, thường phân tích bằng công cụ heap chuyên dụng; **thread dump dạng text** là ảnh chụp trạng thái thread. Mỗi loại phục vụ câu hỏi khác nhau.

Recording có thể chứa thông tin nhạy cảm về class/method, host, đường dẫn, thread name, endpoint hoặc **field do ứng dụng tự đưa vào custom event**. Khi đưa file ra môi trường phân tích, áp dụng quy trình truy cập/giữ dữ liệu phù hợp với ứng dụng.

## 9. Những lỗi phổ biến

1. **“JFR đã có trong JDK nên JMC chắc chắn được cài cùng.”** Sai: JFR là cơ chế ghi trong JDK/JVM, còn JMC có gói ứng dụng riêng. Kiểm tra công cụ thực sự đã cài.
2. **“Muốn mở tệp `.jfr` bắt buộc server vẫn sống và JMX mở.”** Sai: JMC có thể đọc offline một recording đã lưu hoàn chỉnh.
3. **“File mở được thì toàn bộ event cần thiết đều có.”** Sai: recording chỉ có event đã cấu hình, thuộc thời gian được giữ lại và vượt qua threshold/sampling.
4. **“JMC cảnh báo đỏ là đã tìm ra nguyên nhân.”** Sai: đó là nhận định từ rule, cần kiểm tra event, thời gian, ảnh hưởng và code thực.
5. **“Không có cảnh báo là JVM không có vấn đề.”** Sai: thiếu event, recording sai cửa sổ hoặc rule không bao phủ sự cố có thể làm thiếu tín hiệu.
6. **“Nhiều allocation nghĩa là memory leak.”** Sai: allocation rate không đồng nghĩa số đối tượng còn sống sau GC.
7. **“Method chiếm nhiều sample thì chắc chắn chiếm tương ứng wall time.”** Sai: sampling không đo trực tiếp thời gian của từng lời gọi.
8. **“JFR và JMC có nhiệm vụ giống nhau.”** Sai: JFR chủ yếu **thu dữ liệu**, JMC chủ yếu **hiển thị và phân tích** dữ liệu đó.
9. **“Có tệp của production thì phải mở live connection.”** Sai: chuyển file về máy chẩn đoán an toàn thường đã đủ cho workflow offline.
10. **“`JFR.dump` làm dừng recording.”** Sai: dump tạo file snapshot nhưng recording tiếp tục chạy; muốn dừng thì dùng `JFR.stop` hoặc thời lượng kết thúc.

## 10. Checklist trước khi kết luận từ JMC

1. Xác nhận **JMC đã cài độc lập** và phiên bản đủ đọc file recording.
2. Xác nhận file đúng JVM, PID/ứng dụng, JDK, **time range**; chạy `jfr summary` nếu cần.
3. Kiểm tra event quan trọng **có được bật**, threshold, stack trace và thời gian giữ dữ liệu.
4. Bắt đầu bằng **Automated Analysis Results** để định hướng, sau đó mở **event/stack/timeline** làm bằng chứng.
5. Phân biệt **sample**, **duration event**, **instant event**, **count** và **estimated allocation**.
6. Đối chiếu với log, trace, business metrics, thread/heap dump hay OS metrics theo bản chất sự cố.
7. Ghi nhận giả thuyết và bước xác minh; không gọi cảnh báo chung là root cause khi chưa kiểm tra.

### Tự kiểm tra

- Một JVM trên server chạy JFR nhưng server không cài JMC. Làm thế nào để phân tích recording bằng máy laptop?
- Tại sao file `.jfr` vẫn mở được sau khi JVM đã tắt?
- Tại sao một trang CPU profiling trong JMC có thể rỗng dù ứng dụng đã hoạt động?
- Điều gì khiến số allocation samples không bằng số object được tạo?
- Vì sao một cảnh báo GC/lock trong Automated Analysis Results cần đối chiếu với ứng dụng trước khi kết luận?
- Trong ví dụ `MissionControlDemo`, mỗi custom event được phát ở bước nào và bạn kiểm tra chúng ở đâu?

## Tài liệu chính thức

- [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): nguồn tải ứng dụng, mô tả vai trò JMC và tài liệu.
- [JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): tạo/mở recording, Automated Analysis Results, các trang phân tích.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [OpenJDK JMC](https://github.com/openjdk/jmc): dự án mã nguồn mở của công cụ JDK Mission Control.
- [Java SE 21 — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): APIs cho recording và custom event.
