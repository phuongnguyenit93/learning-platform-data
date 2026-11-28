# Chẩn đoán pinning và tác vụ chặn theo hành vi của JDK đang dùng

> **Bối cảnh:** Java 27 — chương **Virtual threads và ngữ cảnh tác vụ**. Bài học giải thích cách nhận biết một virtual thread đang chặn (*blocking*), đang giữ carrier (*pinning*) hay chỉ đang chờ tài nguyên; cách dùng JDK Flight Recorder (JFR), `jcmd` và số liệu scheduler để chẩn đoán. Nội dung được điều chỉnh theo hành vi **JDK đang thực sự chạy**; không áp dụng máy móc những khuyến cáo đã lỗi thời từ JDK 21–23.

## 1. Mục tiêu: không gộp mọi tác vụ chậm thành pinning

Virtual thread là một `java.lang.Thread` nhẹ, được JDK lập lịch lên một **platform thread** gọi là *carrier thread*. Virtual threads phù hợp cho nhiều công việc độc lập có phần lớn thời gian chờ I/O. Chúng tăng khả năng phục vụ nhiều yêu cầu đồng thời, **không khiến CPU tính toán nhanh hơn**.

Trong một ứng dụng dùng virtual threads, khi thấy latency tăng hoặc nhiều tác vụ đang “đứng”, có thể có các nguyên nhân rất khác nhau:

1. **Blocking bình thường, có unmount:** virtual thread tạm chờ socket, timer hoặc một operation hỗ trợ virtual-thread-aware blocking; carrier được giải phóng để chạy tác vụ khác.
2. **Pinning:** virtual thread không thể unmount trong một khoảng chặn, khiến carrier phải chờ cùng nó.
3. **Lock contention:** các tác vụ chờ một monitor hoặc lock có người sở hữu; có thể chờ lâu nhưng không nhất thiết pin carrier trên JDK hiện hành.
4. **Resource bottleneck:** connection pool, database, giới hạn API, semaphore hoặc hàng đợi hết capacity.
5. **CPU saturation:** tác vụ tính toán chiếm carrier vì thực sự dùng CPU, không phải “pinning” theo nghĩa scheduler không thể unmount một tác vụ chặn.
6. **Deadlock hoặc lỗi phối hợp:** hai hay nhiều thread chờ nhau, hoặc một điều kiện không bao giờ được phát tín hiệu.

**Chẩn đoán đúng là ghép triệu chứng với bằng chứng về trạng thái thread, JFR event, thời lượng, stack trace và độ bão hòa tài nguyên.** Không chỉ dựa vào tên một method như `synchronized`, `sleep`, `read` hoặc `wait`.

### 1.1. Quy trình rút gọn

~~~text
Ứng dụng chậm / throughput giảm
          │
          ▼
Kiểm tra phiên bản JDK thực tế và cấu hình runtime
          │
          ▼
Có JFR jdk.VirtualThreadPinned không?
          ├── Có ──▶ stack + pinnedReason + carrier + thời lượng
          │                 │
          │                 ▼
          │           Phân loại nguyên nhân
          │
          └── Không ──▶ kiểm tra threshold/cửa sổ JFR;
                          thread dumps, scheduler, I/O, CPU,
                          contention và resource pools
          │
          ▼
Sửa đúng bottleneck, kiểm thử và đo lại
~~~

Một lần chạy không có pinned event **không chứng minh** tất cả virtual threads đều không từng pin. Có thể chưa bật recording, pin dưới ngưỡng, xảy ra ngoài cửa sổ đo, hoặc vấn đề thực tế nằm ở loại chặn khác.

## 2. Carrier, mount, unmount và pinning

Khi virtual thread được lập lịch:

- **Mount:** JVM đặt virtual thread lên một carrier để chạy code.
- **Running:** virtual thread dùng CPU thông qua carrier.
- **Unmount:** nếu một operation chặn theo cách runtime hỗ trợ, JVM tạm ngưng virtual thread và trả carrier cho scheduler.
- **Remount:** khi có thể tiếp tục, scheduler gán virtual thread lên một carrier sẵn có. Carrier tiếp theo không nhất thiết trùng carrier trước đó.
- **Pinned:** virtual thread tạm thời không thể unmount trong một tình huống nhất định. Nếu bị chặn khi pinned, carrier có thể cũng bị giữ lại.

~~~text
Chặn có thể unmount
  Virtual thread V1 ── chạy trên carrier C1 ── socket wait
                                  │
                                  └─ V1 unmount
                                     C1 chạy V2, V3, ...
                         socket ready
                                  │
                                  └─ V1 được schedule lại

Chặn khi pinned
  Virtual thread V4 ── chạy trên carrier C2 ── blocking call
                         │
                         └─ không unmount được
                            C2 bị giữ trong thời gian chặn
~~~

**Pinning không có nghĩa là sai về tính đúng đắn**. Nó có thể làm giảm khả năng mở rộng khi xảy ra **thường xuyên**, **đủ lâu** và giữ nhiều carrier đúng lúc hệ thống cần chạy nhiều tác vụ khác.

### 2.1. Phân biệt “đang ở carrier” với “carrier đang bị ghim”

Một virtual thread **đang chạy code Java bình thường** luôn phải chạy trên một carrier; điều này không phải bằng chứng pinning. Thuật ngữ *pinning* hữu ích khi virtual thread **cần chặn nhưng không thể nhường carrier** theo cơ chế thông thường.

Tương tự:

- Một virtual thread có trạng thái `WAITING` không mặc nhiên pin carrier.
- Một monitor đang có thread chờ không mặc nhiên gây pinning.
- Một socket request chậm không chứng minh carrier cũng chậm theo.
- Scheduler có nhiều queued virtual threads không đủ để khẳng định pinning; vẫn cần điều tra CPU, resource wait và những operation đang chạy.

### 2.2. Các loại blocking có ý nghĩa khác nhau

| Hoạt động | Điều cần quan sát | Kết luận không được vội đưa ra |
| --- | --- | --- |
| `Thread.sleep(...)` trên virtual thread | Thời gian sleep, năng lực scheduler, JFR `jdk.ThreadSleep` | “Sleep luôn pin carrier” |
| Socket read hỗ trợ virtual threads | Độ trễ mạng, `jdk.SocketRead`, trạng thái poller | “Network I/O lâu nghĩa là carrier bị chiếm” |
| Chờ vào `synchronized` | Monitor contention, thời gian giữ khóa, JDK version | “Synchronized luôn gây pinning” |
| `Object.wait()` | Điều kiện, notify, JDK version | “Wait chắc chắn giữ carrier” |
| `Semaphore.acquire()` | Số permit và thời gian chờ | “Nhiều task WAITING là bug scheduler” |
| JDBC / connection pool | Pool active/idle/pending, driver và DB latency | “JDBC chậm là pinning của JVM” |
| JNI / foreign function | Native frames, callback, `pinnedReason` | “Mọi native call đều làm hệ thống nghẽn” |
| CPU-heavy loop | CPU profile, hot methods, số core | “CPU bận là virtual-thread pinning” |

## 3. Hành vi pinning phụ thuộc phiên bản JDK

Đây là phần quan trọng nhất trước khi sửa code. Một hướng dẫn đúng cho JDK 21–23 có thể **không còn đúng đối với Java 27**.

### 3.1. Mốc thay đổi từ JEP 491

| Giai đoạn runtime | Blocking trong `synchronized` | `Object.wait()` | Trường hợp pinning còn cần quan tâm |
| --- | --- | --- | --- |
| JDK 21–23 | Có thể pin virtual thread trong tình huống blocking khi giữ monitor | Cũng chịu giới hạn triển khai monitor cũ | Native/foreign + monitor |
| **JDK 24 trở lên** | JEP 491 cho phép virtual thread chặn/unmount phù hợp khi giữ monitor | Triển khai monitor/wait được cải tiến để không pin chỉ vì monitor | Native/foreign frames; một số tình huống VM/class initialization |
| **Java 27** | Áp dụng hành vi hiện hành của JDK 24+ | Không giữ khuyến cáo pinning do monitor của JDK 21–23 | Dùng JFR để xác nhận nguyên nhân thực tế |

JEP 491 — **Synchronize Virtual Threads without Pinning** — được tích hợp từ **JDK 24**. Virtual threads vẫn có thể **tranh chấp monitor và chờ**; thay đổi là việc phải chờ monitor không còn mặc định đồng nghĩa với giữ một carrier vì cơ chế synchronized thông thường. Nếu có một native/VM frame khiến virtual thread không unmount được, các operation khác như contended monitor enter vẫn có thể xuất hiện như `blockingOperation` trong sự kiện pinned.

**Hệ quả cho Java 27:** đừng thay mọi `synchronized` bằng `ReentrantLock` chỉ để loại bỏ loại pinning mà JEP 491 đã xử lý. Giữ `synchronized` khi nó là cơ chế khóa đúng và đơn giản; tối ưu thời gian giữ khóa nếu có contention thực.

### 3.2. Thuộc tính chẩn đoán cũ không còn phù hợp

Các bài hướng dẫn cho JDK 21–23 đôi khi dùng:

~~~text
-Djdk.tracePinnedThreads=full
-Djdk.tracePinnedThreads=short
~~~

Đây là **thông tin lịch sử để nhận diện cấu hình cũ**, **không phải khuyến nghị chạy trên Java 27**. Từ JDK 24, thuộc tính `jdk.tracePinnedThreads` không còn phát trace pinning như trước; đặt nó trong JVM arguments Java 27 không phải một bước xác minh pinning đáng tin cậy.

**Trên Java 27, ưu tiên JFR `jdk.VirtualThreadPinned`** với stack trace, nguyên nhân, carrier và duration; kết hợp thread dump/scheduler metrics để xác định bottleneck.

### 3.3. JDK version là của process, không phải của IDE

Ví dụ kiểm tra runtime đang chạy:

~~~java
public class RuntimeCheck {
    public static void main(String[] args) {
        System.out.println(System.getProperty("java.version"));
        System.out.println(System.getProperty("java.runtime.version"));
        System.out.println(Runtime.version());
        System.out.println(Runtime.version().feature());
    }
}
~~~

Lệnh kiểm tra terminal:

~~~text
java -version
javac -version
jcmd <pid> VM.version
jcmd <pid> VM.command_line
~~~

`java -version` trong terminal có thể chỉ shell PATH/JAVA_HOME hiện hành, **khác runtime của server process** đang chẩn đoán, đặc biệt trong container, IDE, service manager hoặc custom runtime image. Ưu tiên kiểm tra **đúng process PID** trước khi áp dụng quy tắc JDK 24+.

Nếu một hệ thống có nhiều instance, phải xác nhận **mọi instance** đang cùng phiên bản và cùng cấu hình scheduler/JFR trước khi so sánh kết quả.

## 4. Các trường hợp còn pinning trên Java 27

Bản hướng dẫn Java SE 27 hiện hành mô tả pinning khi virtual thread đang thực thi **native method** hoặc **foreign function**. Các tình huống liên quan VM, ví dụ chờ khởi tạo class, cũng có thể được phản ánh trong event `jdk.VirtualThreadPinned`.

### 4.1. Native/foreign frame

Các đoạn code sử dụng JNI hoặc Foreign Function & Memory API có thể tạo native/foreign frames trên stack. Nếu virtual thread cần chặn khi một frame như vậy vẫn còn hiện diện, nó có thể không unmount được, giữ carrier.

Ví dụ khái niệm:

~~~text
Virtual thread
    └── Java method
         └── native / foreign call
               └── callback vào Java
                    └── blocking / parking
                          └── carrier có thể bị giữ
~~~

Đây là sơ đồ, **không phải ví dụ biên dịch được**. Mức độ ảnh hưởng phải được đo trên thư viện và workload thật. Không nên tự viết native code chỉ để cố tạo pinning trong một tutorial cơ bản.

### 4.2. VM operation và class initialization

Một số tình huống nội bộ VM, như thread chờ quá trình khởi tạo class do thread khác thực hiện, có thể cản khả năng unmount và được báo bằng JFR `pinnedReason`. Nếu stack trỏ vào `<clinit>` hoặc lớp đang khởi tạo:

- Xem có I/O, lock hoặc chờ dài hạn trong static initializer không.
- Di chuyển công việc lâu sang bước khởi tạo có quản lý rõ hơn nếu phù hợp.
- Không giả định mọi lần class loading đều là pinning.
- Không “sửa” bằng cách bỏ synchronization bảo vệ shared state.

### 4.3. Pinning có thể là triệu chứng, không phải gốc rễ

Một native callback đang chờ DB timeout 30 giây có thể làm một carrier bị giữ. Tuy nhiên nguyên nhân gốc có thể là **timeout của DB**, **connection pool cạn** hoặc **tắc nghẽn mạng**. Nhiệm vụ chẩn đoán gồm cả hai câu hỏi:

1. **Carrier bị giữ vì sao?** — Phân loại pinning/native/VM.
2. **Tác vụ phải đợi lâu vì sao?** — Phân loại tài nguyên, timeout, contention, logic.

Chỉ giảm pinning mà bỏ qua độ trễ nguồn ngoài có thể giúp throughput nhưng không cải thiện latency của từng yêu cầu.

## 5. JDK Flight Recorder: công cụ chính để thấy pinning

JFR là cơ chế ghi nhận sự kiện của JDK. Trong Java 27, `jdk.VirtualThreadPinned` được dùng để chẩn đoán một virtual thread bị pin và carrier không được giải phóng quá **ngưỡng thời lượng của cấu hình ghi**. Hướng dẫn Java SE 27 mô tả event này **được bật mặc định với ngưỡng 20 ms** trong cấu hình thông dụng.

Các event liên quan:

| JFR event | Cung cấp điều gì | Lưu ý |
| --- | --- | --- |
| `jdk.VirtualThreadPinned` | Khoảng thời gian pinned blocking, stack, lý do/operation và carrier | Event dưới threshold có thể không được ghi |
| `jdk.VirtualThreadSubmitFailed` | Scheduler không thể nhận việc submit/start/unpark trong trường hợp tài nguyên bất thường | Không đồng nghĩa mọi lần queue dài đều có event |
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu | Mặc định disabled; bật cho bài toán đếm lifecycle nếu thực sự cần |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc | Mặc định disabled; volume rất lớn nếu tạo nhiều task |
| `jdk.SocketRead`, `jdk.SocketWrite` | Quan sát các operation I/O socket | I/O lâu chưa chắc pin |
| `jdk.FileRead`, `jdk.FileWrite` | Quan sát operation file I/O | Cần xem backend/OS và native stack |
| `jdk.JavaMonitorEnter` | Thời gian chờ monitor bị contention | Contention khác pinning |
| `jdk.ThreadPark`, `jdk.ThreadSleep` | Hoạt động park/sleep | Không tự chứng minh carrier bị giữ |

**Quan trọng:** event được bật hay không, threshold, stack trace và sampling tùy **recording settings**. Không nên kết luận dựa trên giả định “mặc định luôn giống nhau” khi production đang dùng file `.jfc` riêng.

### 5.1. Ghi JFR ngay khi khởi động

Ví dụ với ứng dụng có main class `com.acme.Main`:

~~~bash
java -XX:StartFlightRecording:filename=virtual-threads.jfr,settings=profile,dumponexit=true -cp app.jar com.acme.Main
~~~

Với ứng dụng được đóng gói thành executable JAR:

~~~bash
java -XX:StartFlightRecording:filename=virtual-threads.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Các lệnh là lựa chọn **minh họa**: cần thay path/main class cho đúng artifact đang chạy. `dumponexit=true` ghi recording khi JVM thoát; nếu chương trình chạy lâu, bạn có thể chọn ghi từ một process đang hoạt động bằng `jcmd`.

### 5.2. Ghi JFR trên JVM đang chạy

Từ máy/container có quyền truy cập process và JDK tools:

~~~bash
jcmd <pid> JFR.start name=PinCapture settings=profile duration=60s filename=pinning.jfr
~~~

Lệnh bắt đầu recording 60 giây. Nếu muốn xem recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Một lựa chọn khác là chạy recording rồi dump theo yêu cầu:

~~~bash
jcmd <pid> JFR.start name=PinCapture settings=profile
jcmd <pid> JFR.dump name=PinCapture filename=pinning.jfr
jcmd <pid> JFR.stop name=PinCapture
~~~

Các lệnh `jcmd` phải thực thi với quyền phù hợp trên máy của **JVM đích**, thường cùng effective user và đủ attach permission. Trong container hoặc custom runtime image không có `jcmd`/`jfr`, cần dùng bộ công cụ chẩn đoán JDK tương thích và đúng process namespace. **Không** thử trên process khác rồi gán kết quả cho production instance đang gặp lỗi.

### 5.3. Xem sự kiện pinned

~~~bash
jfr summary pinning.jfr
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

Xem thêm các sự kiện gợi ý bottleneck:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed,jdk.JavaMonitorEnter,jdk.SocketRead,jdk.FileRead pinning.jfr
~~~

Khi một hệ thống tạo rất nhiều virtual threads, bật `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` có thể tạo khối lượng event lớn. Chỉ bật nếu thực sự cần thống kê lifecycle và đã xác định khả năng chịu tải của recording.

### 5.4. Cách đọc một VirtualThreadPinned event

Một bản ghi thường bao gồm những thông tin như:

~~~text
jdk.VirtualThreadPinned {
    duration = ... ms
    blockingOperation = "LockSupport.park"      # ví dụ
    pinnedReason = "Native or VM frame on stack" # ví dụ
    carrierThread = "ForkJoinPool-...-worker-..."
    eventThread = "...virtual..."
    stackTrace = [...]
}
~~~

Đây là **cấu trúc minh họa**, không phải một JFR event đã đo từ hệ thống thực. Tên trường/giá trị phản ánh dạng sự kiện được tài liệu Java SE 27 mô tả.

Hướng đọc:

1. **duration:** thời lượng một lần pinned blocking, không phải tổng latency cả request.
2. **blockingOperation:** operation tại điểm chặn (`LockSupport.park`, `Object.wait`, contended monitor enter...).
3. **pinnedReason:** nguyên nhân ngăn virtual thread unmount (native/VM frame, class initialization...).
4. **carrierThread:** platform thread đang bị giữ.
5. **eventThread và stackTrace:** virtual thread và đường gọi dẫn tới điểm chặn.

Ví dụ `blockingOperation = "Contended monitor enter"` trên Java 27 **không tự suy ra “monitor gây pinning như JDK 21”**: hãy xem **pinnedReason**; monitor contention có thể diễn ra trong lúc một native/VM frame đã làm virtual thread pinned.

### 5.5. Vì sao không thấy VirtualThreadPinned event?

Có nhiều khả năng:

- Không có pinning đủ dài trong workload đã ghi.
- Recording không chạy đúng lúc hoặc trên đúng process.
- Event bị tắt hoặc threshold quá cao.
- Stack trace/event bị sampling hoặc cấu hình công cụ hạn chế.
- Vấn đề thực tế là DB/pool/I/O wait có unmount, CPU saturation hoặc lock contention.
- Pinning xảy ra quá ngắn, ít thường xuyên nên không phải bottleneck đáng kể.

**Không tự tạo kết luận tuyệt đối “không pin” từ một JFR rỗng**. Hãy kiểm tra event configuration, tái hiện workload và đối chiếu metrics/dumps khác.

## 6. Thread dumps: phân biệt mounted virtual threads và các thread đang chờ

JDK cung cấp hai cách dump với mục tiêu khác nhau.

### 6.1. Thread.print truyền thống

~~~bash
jcmd <pid> Thread.print
~~~

Tài liệu Java SE 27 mô tả output kiểu HotSpot VM dump hiển thị **platform threads và virtual threads đang mounted**, gồm stack trace. Công cụ hữu ích để tìm CPU loops, điểm đang giữ monitor hoặc vấn đề runtime khác, nhưng **không phải cách đáng tin cậy để liệt kê mọi virtual thread đang unmounted**.

### 6.2. Thread.dump_to_file: xem cả virtual threads

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Hoặc dùng định dạng văn bản mặc định nếu không cần JSON:

~~~bash
jcmd <pid> Thread.dump_to_file threads.txt
~~~

Lệnh này cung cấp thông tin về nhiều virtual threads, kể cả những thread đang chờ. Các đặc tính quan trọng:

- Không tạo một **snapshot nguyên tử của toàn VM**; dump có thể ghi thời điểm của từng thread.
- Có thông tin thread state và các loại lock trong `java.util.concurrent`.
- Không tự chạy phân tích deadlock.
- Không bao gồm đầy đủ dữ liệu như object addresses, JNI statistics và heap statistics trong HotSpot dump truyền thống.
- Định dạng JSON phù hợp để phân tích bằng công cụ riêng, nhưng không suy luận “mọi WAITING thread đều pinned”.

**Lưu ý khác biệt tài liệu công cụ:** phần hướng dẫn Core Libraries có ví dụ định dạng văn bản với `-format=text`, trong khi manpage `jcmd` mô tả tùy chọn mặc định dạng text/plain. Để giảm khả năng nhầm khi viết runbook, có thể **bỏ `-format` cho văn bản mặc định** hoặc dùng `-format=json`; trước khi tự động hóa, xác nhận cú pháp bằng `jcmd <pid> help Thread.dump_to_file` trên đúng JDK runtime.

### 6.3. Cách phân tích dump

Khi mở dump:

1. Nhóm theo stack trace tương tự nhau: bao nhiêu virtual threads đang ở cùng một điểm chặn?
2. Xem nơi chặn là `Semaphore.acquire`, `BlockingQueue.take`, `SocketInputStream`, monitor hay code của driver.
3. So khớp request/task identifiers nếu ứng dụng có logging hoặc context tracing.
4. Xem có trạng thái `BLOCKED`, `WAITING`, `TIMED_WAITING` hay CPU-heavy `RUNNABLE` nào nổi bật.
5. Đối chiếu JFR `jdk.VirtualThreadPinned`, monitor contention và I/O events.

**Thread state là mô tả ở cấp Java API, không phải bộ phân loại hoàn chỉnh “pinned/unmounted”.** Một virtual thread `WAITING` có thể đã nhường carrier; dùng JFR để xác nhận pinning thực sự.

## 7. Kiểm tra scheduler, pollers và số liệu MXBean

Nếu triệu chứng là throughput giảm hoặc virtual tasks không được chạy tiếp, hãy thu thập số liệu scheduler cùng lúc với JFR và thread dump.

### 7.1. jcmd Thread.vthread_scheduler

~~~bash
jcmd <pid> Thread.vthread_scheduler
~~~

Lệnh cung cấp tổng quan scheduler, carrier platform threads, công việc đang chạy/chờ và trạng thái thực thi mà JVM hỗ trợ hiển thị. Những con số như target parallelism, worker pool size, queued/active tasks giúp đánh giá scheduler bận đến đâu.

**Đừng đọc một queued count lớn và kết luận “đã pinning”.** Queued tasks có thể đến từ CPU saturation, bursts, lock/resource contention, blocked resume, hoặc hoạt động bình thường khi tạo nhiều tác vụ.

### 7.2. jcmd Thread.vthread_pollers

~~~bash
jcmd <pid> Thread.vthread_pollers
~~~

Lệnh mô tả thông tin về pollers phục vụ socket/network I/O của virtual threads. Nó hỗ trợ phân biệt phần lớn virtual threads đang chờ network readiness với carrier threads đang thực thi hoặc bị chặn theo cách khác.

Không sử dụng số lượng poller đơn lẻ làm thước đo pinning. Nếu ứng dụng có network delays, hãy đối chiếu `jdk.SocketRead`, latency phía downstream, retry/timeout và số pending requests.

### 7.3. VirtualThreadSchedulerMXBean

Từ JDK 24, module `jdk.management` cung cấp `VirtualThreadSchedulerMXBean` để quan sát scheduler.

~~~java
import java.lang.management.ManagementFactory;
import jdk.management.VirtualThreadSchedulerMXBean;

public class SchedulerSnapshot {
    public static void main(String[] args) {
        var bean = ManagementFactory.getPlatformMXBean(
                VirtualThreadSchedulerMXBean.class);

        if (bean == null) {
            System.out.println("Scheduler MXBean unavailable");
            return;
        }

        System.out.println("targetParallelism=" + bean.getParallelism());
        System.out.println("poolSize=" + bean.getPoolSize());
        System.out.println("mounted=" + bean.getMountedVirtualThreadCount());
        System.out.println("queued=" + bean.getQueuedVirtualThreadCount());
    }
}
~~~

Với ứng dụng **named module**, cần có dependency tới module `jdk.management` để biên dịch code trên:

~~~java
module com.acme.diagnostics {
    requires java.management;
    requires jdk.management;
}
~~~

Các số liệu mounted/queued là **ước lượng** và một số method có thể trả `-1` khi không biết. `poolSize` có thể lớn hơn target parallelism theo implementation. `setParallelism` có tồn tại nhưng **không nên chỉnh trong production chỉ để “xóa số queued”** khi chưa hiểu nguyên nhân; tăng carrier có thể che bottleneck tạm thời và làm thay đổi đặc tính vận hành.

## 8. Ví dụ thực nghiệm: blocking bình thường và monitor contention

Đây là demo thuần Java 27 để phân biệt việc **nhiều virtual threads bị chặn** với trường hợp **có tranh chấp lock**. Không sử dụng JNI/FFM nên **không phải demo cố tình tạo pinning**.

### 8.1. Ví dụ nhiều tác vụ sleep độc lập

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class VirtualSleepDemo {
    public static void main(String[] args) throws Exception {
        long start = System.nanoTime();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var tasks = new ArrayList<Future<?>>();

            for (int i = 0; i < 100; i++) {
                tasks.add(executor.submit(() -> {
                    Thread.sleep(Duration.ofMillis(200));
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        }

        System.out.println(
                "elapsedMs=" + (System.nanoTime() - start) / 1_000_000);
    }
}
~~~

Mỗi task ngủ khoảng 200 ms; với tài nguyên phù hợp, nhiều virtual threads có thể ngủ đồng thời vì JVM có thể unmount chúng. **Không khẳng định thời gian đo luôn là 200 ms**: startup, warmup, scheduling, hệ điều hành và tải máy ảnh hưởng phép đo.

Điểm cần kiểm tra:

- Nhiều virtual threads ở trạng thái chờ là bình thường.
- `Thread.sleep` trên virtual thread không có nghĩa nó cố tình chiếm carrier trong suốt thời gian sleep.
- Nếu benchmark chậm, cần xem CPU, scheduler, môi trường và JFR trước khi gắn nhãn pinning.

### 8.2. synchronized có thể làm throughput giảm mà không pin

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class MonitorContentionDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var tasks = new ArrayList<Future<?>>();

            for (int i = 0; i < 10; i++) {
                tasks.add(executor.submit(() -> {
                    synchronized (LOCK) {
                        Thread.sleep(Duration.ofMillis(100));
                    }
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        }
    }
}
~~~

Tất cả 10 task tranh chấp **một monitor** và mỗi task giữ monitor trong lúc sleep. Dù Java 27 không pin carrier **chỉ vì synchronized**, các task vẫn phải chờ nhau để lấy monitor. Tổng thời gian có thể tăng đáng kể do **serialization theo khóa**, không phải do thiếu carrier.

**Bài học:** không xóa `synchronized` chỉ vì latency xấu. Nếu dữ liệu bên trong cần mutual exclusion, hãy thay đổi phạm vi khóa hoặc thiết kế ownership để tránh giữ monitor khi sleep/I/O không cần thiết. Nếu việc cập nhật cần nguyên tử, không được đưa check/update ra ngoài lock tùy tiện.

## 9. Chẩn đoán theo triệu chứng: pinning, contention, pool hay CPU?

Khi một hệ thống bị chậm, hãy bắt đầu từ **bằng chứng có thể quan sát**, không bắt đầu từ việc đổi toàn bộ loại lock.

| Triệu chứng | Dữ liệu nên thu thập | Nguyên nhân đáng kiểm tra |
| --- | --- | --- |
| JFR có nhiều `jdk.VirtualThreadPinned` dài, cùng stack | `pinnedReason`, `blockingOperation`, carrier, frequency | JNI/FFM/native callback, VM/class initialization |
| Ít hoặc không có pinned event, nhưng hàng nghìn task `WAITING` | Thread dump và metrics pool/queue | Chờ DB connection, semaphore, socket hoặc downstream |
| Nhiều task `BLOCKED` trên cùng monitor | `jdk.JavaMonitorEnter`, monitor owner, thời gian critical section | Lock contention hoặc lock scope quá rộng |
| Scheduler queued cao cùng CPU luôn bận | CPU profile, mounted count, runnable stacks | CPU-bound workload, hot loop, quá nhiều tác vụ tính toán |
| Thread dump cho thấy nhiều socket read chờ lâu | `jdk.SocketRead`, request timeout, server latency | Downstream/network latency, không tự suy ra pin |
| Nhiều task chờ connection pool | Metrics active/idle/pending/acquire time | DB quá tải hoặc pool quá nhỏ so với workload |
| JFR có `jdk.VirtualThreadSubmitFailed` | Scheduler/resource diagnostics, container limits, heap | Lỗi submit/unpark; cần điều tra khả năng tài nguyên |
| JFR có pinned event nhưng latency chính không tăng | Tần suất, duration, carrier occupancy, p95/p99 | Pinning nhỏ/ít xảy ra có thể không phải bottleneck chính |
| Một số tác vụ vĩnh viễn không hoàn tất | Thread stacks, lock order, timeout, external wait | Deadlock, lost signal, không có timeout, dependency lỗi |
| Sau khi cập nhật JDK, pinning trong synchronized không còn nhưng vẫn chậm | Trước/sau JEP 491, CPU, pool, monitor contention | Đã hết monitor pinning, vẫn còn serialization hoặc bottleneck khác |

### 9.1. Đừng đánh giá bằng một con số duy nhất

Các số liệu cần ghép theo **cùng khoảng thời gian**:

- Request rate, throughput và p50/p95/p99 latency.
- Số request/tác vụ đang chạy, đang chờ, bị timeout và bị hủy.
- Số `jdk.VirtualThreadPinned`, tổng thời gian, khoảng thời gian dài nhất, phân bố theo stack.
- CPU utilization, số core có sẵn và GC pauses.
- Scheduler parallelism, carrier pool size, mounted/queued virtual threads.
- Connection pool active/idle/pending, DB/network latency, retry rate.
- Số monitor contention events và thời gian chờ tại cùng một lock.

Một sự kiện pinning 30 ms xuất hiện một lần trong 10 phút rất khác với hàng nghìn sự kiện mỗi giây cùng giữ nhiều carriers. **Ưu tiên vấn đề theo tác động lên throughput và latency**, không theo việc một event có tên đáng lo.

## 10. Quy trình điều tra từng bước trên Java 27

Đây là một runbook có thể áp dụng khi service dùng virtual threads có dấu hiệu giảm throughput.

### Bước 1 — Xác nhận đúng tiến trình và phiên bản

~~~bash
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
~~~

Đối chiếu PID với process đang phục vụ traffic lỗi, và phiên bản runtime. Nếu thật sự là JDK 24+ (trong đó có Java 27), **không áp dụng mặc định cách chữa “synchronized gây pinning” dành cho JDK 21–23**.

Kiểm tra môi trường thực tế: container limits, CPU quota, số processors mà JVM thấy, JVM flags và version thư viện/native integrations.

### Bước 2 — Thu JFR khi có workload đại diện

~~~bash
jcmd <pid> JFR.start name=PinCapture settings=profile duration=60s filename=pinning.jfr
~~~

Chọn thời gian bao phủ giai đoạn hệ thống đang chậm. Nếu tải có chu kỳ dài, dùng recording dài hơn hoặc bổ sung phép đo từ metrics. Lưu ý quyền ghi file và dung lượng disk.

Nếu recording chưa hoàn tất, có thể dùng:

~~~bash
jcmd <pid> JFR.check
~~~

Khi đã có `pinning.jfr`:

~~~bash
jfr summary pinning.jfr
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

Kiểm tra cấu hình event và threshold nếu không có kết quả; **không kết luận ngay rằng không xảy ra pinning**.

### Bước 3 — Lấy thread dump và số liệu scheduler cùng thời điểm

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
jcmd <pid> Thread.vthread_scheduler
jcmd <pid> Thread.vthread_pollers
~~~

Nếu cần tìm platform thread đang chiếm CPU hoặc virtual thread đang mounted:

~~~bash
jcmd <pid> Thread.print
~~~

Lưu ý `Thread.print` không bao gồm mọi unmounted virtual thread, còn `Thread.dump_to_file` không cung cấp một snapshot nhất quán toàn JVM hay phân tích deadlock tự động.

### Bước 4 — Nhóm stack và nguồn chặn

Từ JFR/dump, trả lời:

- Các task đang chặn ở **monitor**, **`LockSupport.park`**, **socket**, **semaphore**, **DB connection acquisition**, **file I/O** hay native callback?
- Có một stack lặp lại chiếm phần lớn thời gian chặn không?
- Native/VM frame có xuất hiện trong pinned event và `pinnedReason` không?
- Số lượng blocked tasks tăng do giới hạn downstream hay do task tạo quá nhanh?
- Carrier pool có nhiều queued tasks ngay cả khi CPU không bận không?

**Đừng sửa hàng loạt** khi chưa biết stack nào chiếm phần lớn impact.

### Bước 5 — Sửa đúng nguyên nhân và đo lại

- Native/foreign pinning → xem lại native call/callback hoặc thư viện phụ thuộc; giảm blocking trong native stack khi có thể.
- Monitor contention → thu nhỏ critical section đúng cách, thay đổi ownership, giảm gọi I/O khi giữ lock.
- Pool cạn → kiểm tra leak, timeout, query chậm, concurrency budget; điều chỉnh giới hạn dựa trên năng lực thật.
- CPU-heavy → giảm công việc CPU, dùng batching/algorithm phù hợp, giới hạn concurrency.
- I/O chậm → đo downstream, timeout, retry, backpressure.
- Deadlock → sửa lock ordering, dependency cycles và phối hợp task.

Sau sửa, chạy cùng workload hoặc cùng tập kịch bản so sánh p95/p99 latency, throughput, CPU, pool waits, pinned events và số queued tasks. **Sự kiện pinning giảm mà throughput không đổi** là tín hiệu cần tiếp tục tìm bottleneck khác.

## 11. Khi nên và không nên thay synchronized

### 11.1. Trên Java 27, synchronized vẫn phù hợp cho shared invariant

Ví dụ bộ đếm thread-safe:

~~~java
public final class Counter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int value() {
        return value;
    }
}
~~~

Các thao tác dùng **cùng monitor instance**, nên bảo vệ được read-modify-write và visibility của `value`. Đổi sang `ReentrantLock` sẽ không tự làm chương trình nhanh hơn; từ JDK 24+ cũng **không cần đổi chỉ để né monitor pinning**.

### 11.2. Vẫn phải giảm thời gian giữ monitor khi có contention

Ví dụ kém hiệu quả:

~~~java
public final class ReportService {
    private final Object lock = new Object();
    private long processed;

    public void recordWithSlowExternalCall(Runnable externalCall) {
        synchronized (lock) {
            externalCall.run(); // có thể block lâu, gọi code bên ngoài
            processed++;
        }
    }
}
~~~

Vấn đề ở đây là **external call được giữ trong critical section**, làm các request tranh chấp và có thể tạo deadlock qua callback. Trên Java 27, nó **không đồng nghĩa monitor làm pin carrier**.

Một thiết kế có thể cải tiến bằng cách tách tác vụ I/O khỏi phần cập nhật state:

~~~java
public final class ReportService {
    private final Object lock = new Object();
    private long processed;

    public void record(Runnable externalCall) {
        java.util.Objects.requireNonNull(externalCall, "externalCall");
        externalCall.run();

        synchronized (lock) {
            processed = Math.addExact(processed, 1);
        }
    }

    public long processed() {
        synchronized (lock) {
            return processed;
        }
    }
}
~~~

**Điều kiện quan trọng:** phiên bản tách I/O ra ngoài lock chỉ phù hợp khi contract cho phép nhiều `externalCall` thực hiện song song, và cập nhật `processed` sau khi I/O hoàn tất là chính xác. Nếu cần giao dịch nguyên tử xuyên hai hành động, phải thiết kế một cơ chế transaction/ordering khác; không thu nhỏ lock mù quáng.

### 11.3. Khi nào dùng ReentrantLock?

`ReentrantLock` có thể phù hợp nếu cần:

- `tryLock()` hoặc lấy khóa với timeout.
- `lockInterruptibly()`.
- Nhiều `Condition` riêng.
- Chính sách lock khác với intrinsic monitor.

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class GuardedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    public int increment() {
        lock.lock();
        try {
            return ++value;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Phải `unlock()` trong `finally` sau khi lấy khóa thành công. **Không chọn ReentrantLock chỉ vì tên “virtual thread”.** Chọn nó theo yêu cầu về API khóa, khả năng interrupt/timeout hoặc contention đã được đo.

## 12. Giới hạn tài nguyên: không pool virtual threads để chữa nghẽn

Định hướng Java hiện đại là **virtual thread cho từng task** khi phù hợp, không tạo một pool virtual threads cố định chỉ để mô phỏng pool platform threads.

Ví dụ sử dụng `Executors.newVirtualThreadPerTaskExecutor()`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualTasks {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Integer>> futures = new ArrayList<>();

            for (int i = 0; i < 20; i++) {
                final int id = i;
                futures.add(executor.submit(() -> id * id));
            }

            for (Future<Integer> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Không có `newFixedThreadPool(n)` dành cho virtual threads ở đây. Nếu phía dưới chỉ chịu được 10 concurrent calls, **giới hạn đúng tài nguyên đó**, thay vì dùng số virtual threads tối đa bằng 10 và đánh mất lợi thế mô hình một task/một virtual thread.

### 12.1. Semaphore để giới hạn downstream

~~~java
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;

public final class LimitedCalls {
    private final Semaphore permits = new Semaphore(10);

    public <T> T call(Callable<T> action) throws Exception {
        Objects.requireNonNull(action, "action");

        permits.acquire();
        try {
            return action.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Tối đa 10 lời gọi bên trong `action` được thực thi đồng thời qua instance `LimitedCalls` này. Những virtual threads khác có thể chờ permit mà không nhất thiết giữ carrier.

**Nhưng:** semaphore không tự tăng capacity của database hoặc API. Nếu 10 requests đang giữ permit mà tất cả chờ timeout dài, các requests còn lại vẫn phải chờ. Theo dõi `pending`, thời gian đợi permit, timeout và khả năng retry.

Nếu thư viện đã có connection pool giới hạn kết nối, việc thêm một semaphore **trùng giới hạn** có thể làm hệ thống có hai hàng đợi khó giám sát; chỉ thêm khi có lý do về chính sách tải hoặc phân vùng tài nguyên.

### 12.2. Timeout và cancellation là yêu cầu riêng

Virtual threads không tự cung cấp timeout cho mọi hoạt động I/O. Cần cấu hình timeout theo API gọi ra:

- HTTP client request/connect timeout theo hợp đồng thư viện đang dùng.
- JDBC/query timeout nếu driver hỗ trợ.
- Thời gian chờ permit hoặc connection pool.
- Deadline tổng yêu cầu, kiểm soát retry và idempotency.

Nếu caller hủy một task, việc hủy có **thực sự ngắt hoạt động** hay không tùy operation/driver/native library. Không coi `Future.cancel(true)` là bảo đảm mọi native I/O kết thúc tức thì. Cần kiểm tra support interrupt/cancellation của thư viện.

## 13. Native/JNI/FFM pinning: cách xử lý thực tế

Vì JDK 27 vẫn có thể pin khi virtual thread chạy qua native hoặc foreign frames, các ứng dụng dùng thư viện native phải đo bằng JFR.

### 13.1. Khi JFR cho thấy native frame

Nếu pinned event có:

~~~text
pinnedReason = "Native or VM frame on stack"
blockingOperation = "LockSupport.park"
stackTrace = ... native callback / library method ...
~~~

thì nên:

1. Tìm đường gọi từ code ứng dụng tới JNI/FFM hoặc một thư viện nội bộ.
2. Xác nhận blocking operation xảy ra **trong khi frame native/foreign còn trên stack**.
3. Đo tần suất, duration, số carrier bị giữ và tác động lên throughput.
4. Tìm API hoặc phiên bản thư viện xử lý blocking theo cách ít giữ carrier hơn.
5. Nếu native operation khó sửa, cân nhắc tách sang một thành phần có concurrency budget rõ ràng, thay vì phóng nhiều virtual tasks gọi native blocking không giới hạn.
6. Đo lại sau thay đổi; đừng mặc định việc “chạy native ở một executor khác” tự giảm latency.

Một call native rất ngắn và không block lâu có thể **không phải vấn đề đáng ưu tiên**. Điều cần quan tâm là thời gian carrier thực sự bị giữ trong operation chặn, không chỉ sự tồn tại của JNI/FFM trong codebase.

### 13.2. Class initialization: trường hợp dễ bỏ sót

Nếu `pinnedReason` nhắc đến việc chờ khởi tạo một class, hãy xem static initializer có đang:

- Thực hiện kết nối mạng hoặc đọc dữ liệu lớn.
- Lấy lock hoặc chờ một task có thể cần chính class đang khởi tạo.
- Gọi code do plugin hoặc library khác cung cấp.
- Gặp dependency cycle/khởi tạo lồng nhau.

Hướng xử lý là làm cho quá trình khởi tạo class **ngắn và xác định**, chuyển I/O dài sang lifecycle service có timeout/ownership rõ, không xóa tùy tiện synchronization.

### 13.3. Không quy tất cả file I/O cho virtual thread pinning

Một operation file I/O có thể dùng **blocking OS call** và ảnh hưởng carrier tùy nền tảng, JDK, thư viện và loại file. Tuy nhiên, hiện tượng carrier bận vì blocking file I/O **không nhất thiết được phân loại hoặc phát ra `jdk.VirtualThreadPinned` như native-frame pinning**.

Cần phân biệt:

- **Pinning do frame:** virtual thread không thể unmount vì native/VM frame khi gặp điểm chặn.
- **Blocking ở mức OS hoặc thư viện:** carrier platform thread có thể bị giữ do call không hỗ trợ unmount phù hợp.
- **Contention ở tài nguyên lưu trữ:** nhiều operations xếp hàng, latency cao dù không có event pinned.

Dùng JFR file I/O events, stack traces, OS disk metrics và thời gian thực hiện từng call để xác định. Không tuyên bố `Files.readString()` “luôn pin” hoặc “không bao giờ giữ carrier” trên mọi môi trường.

## 14. Ngữ cảnh tác vụ và khả năng truy vết

Để chẩn đoán pinning có ý nghĩa, cần liên kết JFR stack với **request/task** cụ thể. Không chỉ biết `Thread-123`, mà cần biết tác vụ đó đang xử lý request nào, dependency nào và tại thời điểm nào.

Một số thực hành:

- Đặt tên virtual thread dễ nhận diện khi quản lý thread thủ công, tránh nhét dữ liệu nhạy cảm vào tên.
- Ghi `traceId`/`requestId` ở log theo hợp đồng của logging framework.
- Đặt các khoảng I/O quan trọng vào trace spans để đo latency nguồn ngoài.
- Phân biệt thời gian chờ permit/connection, thời gian thực sự gọi DB/network, thời gian xử lý CPU.
- Không cache các đối tượng lớn vào `ThreadLocal` cho từng virtual thread; số lượng virtual threads có thể rất lớn.
- Đảm bảo mọi request context được dọn đúng lifetime, đặc biệt với `ThreadLocal` trong code cũ.

Virtual threads hỗ trợ `ThreadLocal` nhưng mỗi task có thể sinh một virtual thread riêng. Không dùng assumption của fixed platform-thread pool rằng thread local sẽ được tái sử dụng lâu dài qua nhiều request.

Ví dụ tên thread khi tạo thủ công:

~~~java
Thread worker = Thread.ofVirtual()
        .name("invoice-task-")
        .start(() -> {
            System.out.println(Thread.currentThread().getName());
        });

worker.join();
~~~

Tên thread ở đây chỉ là nhãn minh họa; nếu muốn đặt tên có số thứ tự hoặc danh tính tác vụ, hãy thiết kế naming theo API `Thread.Builder` đang dùng và giới hạn độ dài. Đừng đưa email, token, số thẻ hay thông tin riêng tư vào tên thread.

## 15. Kịch bản thực tế: service chậm sau khi tăng concurrency

Giả sử sau khi bật virtual threads, một service có tình trạng sau:

- Tăng số request đồng thời thì throughput không còn tăng.
- Thread dump có hàng nghìn virtual threads ở `WAITING`.
- JFR không thấy `jdk.VirtualThreadPinned` đáng kể.
- DB pool chỉ có 20 connections, nhiều request xếp hàng đợi connection.
- DB query p95 tăng từ hàng chục lên hàng trăm mili giây.

**Cách phân tích hợp lý:**

1. Không có bằng chứng pinning đáng kể; `WAITING` là trạng thái phù hợp với việc chờ pool.
2. Virtual threads giúp tránh giữ platform thread cho mỗi request đang chờ, nhưng **không tạo thêm kết nối DB**.
3. Tác nhân chính có thể là capacity của DB, query chậm, transaction giữ connection lâu hoặc retry storms.
4. Việc tăng `jdk.virtualThreadScheduler.parallelism` có thể **không cải thiện** throughput do giới hạn nằm ở DB.
5. Cần đo pool acquire wait, query duration, transaction length, index, timeout và lưu lượng đến.

Hướng sửa có thể là tối ưu query, rút ngắn transaction, điều chỉnh pool phù hợp với DB, hạn chế upstream concurrency hoặc thêm caching khi có thể; không thay hết `synchronized` bằng `ReentrantLock` nếu không thấy monitor contention.

### 15.1. Kịch bản ngược: native blocking thật sự giữ carrier

Giả sử JFR cho thấy rất nhiều `jdk.VirtualThreadPinned` cùng stack native callback, duration dài, trong khi scheduler queue tăng và CPU không bận. Đây mới là tình huống hợp lý để ưu tiên điều tra **khả năng unmount/việc giữ carrier** của thư viện native và tiến hành cải tiến hoặc thay thế đường gọi đó.

Cần xác nhận cùng thời gian tải và có sự cải thiện khi thay đổi code native hoặc giảm blocking trong đường gọi; không dựa vào một stack snapshot rồi khẳng định nguyên nhân cuối cùng.

## 16. Kiểm thử để không nhầm hiện tượng với nguyên nhân

Một bài kiểm thử hữu ích nên có ít nhất ba kiểu workload độc lập:

| Kịch bản | Mục tiêu kiểm tra | Kết quả cần diễn giải |
| --- | --- | --- |
| Nhiều virtual threads `Thread.sleep` | Unmount-friendly wait | Nhiều task có thể chờ đồng thời; không tự suy ra pinning |
| Nhiều virtual threads tranh chấp một monitor | Lock contention | Tổng thời gian tăng do serialization ngay cả khi không pin |
| Native/foreign callback có operation chặn, **nếu ứng dụng thật có** | Pinning còn lại | JFR event với reason/duration/stack nếu vượt threshold |

Không thêm JNI/FFM giả chỉ để tạo test “đầy đủ”. Nếu hệ thống thật không dùng native integration, việc test cùng một nguồn I/O/driver thực tế có giá trị hơn.

### 16.1. Cách thu thập kết quả kiểm thử

Với cùng phiên bản JDK và cấu hình, ghi nhận:

- Number of tasks, arrival rate, duration và timeout.
- CPU utilization và scheduler queued/mounted metrics.
- JFR pinned events và monitor/socket/file events.
- p50/p95/p99 latency, throughput và error rate.
- DB/HTTP pool metrics cùng thời điểm.

Thực hiện warmup hợp lý, lặp lại nhiều lần, tránh lấy một số wall-clock rồi kết luận. Nếu workload được chạy trên container, theo dõi CPU quota và giới hạn tài nguyên.

### 16.2. Thận trọng với việc thay đổi scheduler parallelism

JDK có thiết lập `jdk.virtualThreadScheduler.parallelism` để điều chỉnh target scheduler parallelism trong một số ngữ cảnh. Đây có thể là tham số hữu ích cho **thực nghiệm có kiểm soát**, nhưng:

- Không phải giải pháp mặc định cho pinning hoặc downstream pool saturation.
- Tăng số carriers có thể làm tăng memory/resource usage.
- Kết quả có thể phụ thuộc CPU quota và workload hiện tại.
- Cần kiểm tra phiên bản JDK, scope áp dụng và metrics khi chỉnh.

Cách đáng tin cậy nhất là **sửa đường blocking gây nghẽn** và đo lại. Đừng cố giải quyết mọi delay bằng cách tăng thread count.

## 17. Những sai lầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách làm hiện hành |
| --- | --- | --- |
| “Mọi synchronized block đều pin virtual thread” | Chỉ đúng với giới hạn monitor ở JDK 21–23, không đúng nguyên trạng cho Java 27 | Dựa trên JEP 491 và bằng chứng JFR |
| “Virtual thread WAITING nghĩa là carrier cũng WAITING” | Virtual thread có thể đã unmount | Xem JFR, thread dump, scheduler |
| “Không có pinned event là chắc chắn không pin” | Có threshold, cửa sổ ghi và cấu hình | Xác nhận recording settings và workload |
| “JFR VirtualThreadPinned là mọi loại blocking” | Event tập trung vào blocking **khi pinned** | Kết hợp socket/monitor/park events |
| “Một native call nghĩa là throughput giảm” | Chỉ khi carrier bị giữ đủ dài/thường xuyên mới ảnh hưởng đáng kể | Đo duration, tần suất và impact |
| “Thay tất cả synchronized bằng ReentrantLock” | Có thể tăng độ phức tạp mà không sửa lock contention | Giữ lock đúng, giảm thời gian giữ khi cần |
| “Thêm carrier sẽ chữa được pool DB cạn” | Scheduler không tạo thêm connection | Kiểm tra capacity, timeout và truy vấn |
| “Sleep chậm là pinning” | Sleep của virtual thread thường hỗ trợ unmount | Đối chiếu scheduler/JFR và hoàn cảnh |
| “Nhiều thread chờ monitor chứng minh pinning” | Lock contention và pinning là hai loại hiện tượng | Dùng JavaMonitorEnter và pinnedReason |
| “jcmd Thread.print liệt kê mọi virtual thread” | Chủ yếu platform + mounted virtual threads | Dùng Thread.dump_to_file cho góc nhìn đầy đủ hơn |
| “Tăng virtual thread pool sẽ tăng throughput” | Không nên pool virtual threads theo mô hình fixed worker | Task per virtual thread, budget theo downstream |
| “Trace flag cũ còn hữu ích ở Java 27” | `jdk.tracePinnedThreads` không còn cung cấp trace pinning như JDK 21–23 | Dùng JFR pinned event |
| “Thread dump cho biết chắc chắn deadlock” | Dump_to_file không tự phát hiện deadlock | Phân tích lock cycles và công cụ phù hợp |
| “Mọi file I/O đều là VirtualThreadPinned” | File I/O blocking phụ thuộc OS/JDK/library; pinning là khái niệm cụ thể | Đo file events, OS metrics và stack |
| “Hủy Future sẽ luôn ngắt native operation” | Cancellation phụ thuộc thư viện và operation | Thiết kế timeout/interrupt và kiểm thử |

## 18. Checklist chẩn đoán trước khi sửa production

- [ ] Đã kiểm tra **đúng PID** và **đúng JDK version** của JVM đang gặp lỗi.
- [ ] Phân biệt hành vi JDK 21–23 với JDK 24+/Java 27 theo JEP 491.
- [ ] Không dựa vào `-Djdk.tracePinnedThreads` để chẩn đoán Java 27.
- [ ] Đã thu JFR với thời gian bao phủ workload có vấn đề.
- [ ] Đã kiểm tra cấu hình event/threshold và có/không có `jdk.VirtualThreadPinned`.
- [ ] Khi có pinned event, đã xem `pinnedReason`, `blockingOperation`, carrier, duration và stack.
- [ ] Không gán nhãn pinning chỉ từ `WAITING` hoặc `BLOCKED`.
- [ ] Đã thu `Thread.dump_to_file` khi cần xem nhiều unmounted virtual threads.
- [ ] Đã xem `Thread.vthread_scheduler`/`Thread.vthread_pollers` nếu liên quan scheduling/network wait.
- [ ] Đã so khớp CPU usage, scheduler queue, request latency và resource pool metrics.
- [ ] Đã tìm monitor contention, deadlock, DB pool starvation và downstream I/O latency.
- [ ] Đã xác định bottleneck có đến từ native/foreign/class initialization hay không.
- [ ] Không bỏ lock đang bảo vệ invariant chỉ để tăng throughput.
- [ ] Đã chọn concurrency budget tại đúng tài nguyên thay vì pool virtual threads cố định.
- [ ] Các operation bên ngoài có timeout/cancellation policy phù hợp.
- [ ] Không nhầm cải thiện unmount với cải thiện latency một request.
- [ ] Đã kiểm thử trước/sau với cùng workload và cùng JDK/configuration.
- [ ] Bằng chứng JFR/dump/log có thời điểm, request context và quyền truy cập phù hợp; không phát tán dữ liệu nhạy cảm.
- [ ] Đã ghi lại quyết định sửa và kết quả đo trong runbook của dịch vụ.

## 19. Nguồn chính thức và tài liệu tra cứu

- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — mount/unmount, carrier, pinned virtual threads, JFR, `jcmd`, scheduler và tài liệu adoption.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — loại bỏ monitor-related pinning từ JDK 24; khác biệt với khuyến cáo cho JDK 21–23.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — virtual threads chính thức từ Java 21, task-per-thread.
- [Java SE 27 — jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — `Thread.print`, `Thread.dump_to_file`, `Thread.vthread_scheduler`, `Thread.vthread_pollers` và `JFR.start`.
- [Java SE 27 — jfr Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html) — in và phân tích JFR recordings.
- [Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html) — chẩn đoán JVM đang chạy, JFR và `jcmd`.
- [Java SE 27 API — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html) — target parallelism, pool size, mounted và queued virtual-thread estimates.
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html) — virtual thread creation, sleep, interruption và lifecycle.
- [Java SE 27 API — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html) — `newVirtualThreadPerTaskExecutor()`.
- [Java SE 27 API — Semaphore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html) — concurrency budget ở tài nguyên.
- [Java SE 27 API — ReentrantLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html) — các khả năng lock/timeout/interrupt.

**Kết luận:** Trên Java 27, một virtual thread **chặn** không đồng nghĩa với **pin carrier**, và `synchronized` không còn tự gây loại pinning mà JEP 491 đã xử lý từ JDK 24. Chẩn đoán cần dựa vào phiên bản runtime thật, `jdk.VirtualThreadPinned` (đặc biệt `pinnedReason`), thread dumps, scheduler metrics và thời gian chờ nguồn ngoài. Sửa đúng nguyên nhân — native/VM pinning, monitor contention, pool saturation, CPU hoặc I/O — sẽ hiệu quả hơn thay thế lock hay tăng số carrier theo thói quen.
