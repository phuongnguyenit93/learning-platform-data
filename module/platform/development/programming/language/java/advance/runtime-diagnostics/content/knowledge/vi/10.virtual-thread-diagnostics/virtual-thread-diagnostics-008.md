# 10.8 Đối chiếu hành vi và công cụ theo phiên bản JDK khi phân tích virtual thread

Virtual thread (luồng ảo) là `java.lang.Thread` do Java runtime lập lịch lên một số luồng nền tảng (*carrier/platform thread*). Khi virtual thread chờ một thao tác có thể unmount, carrier được trả lại để chạy việc khác. Vì vậy, virtual thread chủ yếu giúp tăng **khả năng phục vụ nhiều tác vụ chờ I/O**, không làm một phép tính CPU chạy nhanh hơn. Khi chẩn đoán sự cố, **phiên bản JDK đang chạy ứng dụng** quyết định ý nghĩa của hiện tượng pinning, tập lệnh `jcmd` khả dụng, khả năng quan sát scheduler và thậm chí kiểu dữ liệu trong thread dump JSON.

## 1. Mục tiêu và cách xác định phiên bản thực tế

Sau bài này, bạn có thể: xác định mốc thay đổi của virtual thread; phân biệt blocking, pinning và tranh chấp lock; chọn thread dump, JFR, `jcmd` hoặc JMX theo JDK; so sánh kết quả JDK 21–23 với 24+; và sửa công cụ phân tích dump khi chuyển lên JDK 27.

Trước khi diễn giải log, ghi lại **JDK của tiến trình đích**, không chỉ JDK cài trên máy phân tích:

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
```

`<PID>` là PID JVM ứng dụng; thay bằng số thực. `jcmd` thường cần chạy cùng máy, đủ quyền attach và tương thích với JVM đích. Ghi thêm bản cập nhật (ví dụ 21.0.x), nhà cung cấp JDK, hệ điều hành, cấu hình JVM, tải thử và thời điểm thu thập. Không suy luận hành vi chỉ từ `javac -version` vì ứng dụng có thể được biên dịch và vận hành bằng hai JDK khác nhau.

## 2. Bảng đối chiếu nhanh các mốc JDK

| Phiên bản | Trạng thái và hành vi cần nhớ | Công cụ / điểm cần lưu ý khi chẩn đoán |
| --- | --- | --- |
| **JDK 19** | Virtual thread xuất hiện dạng **preview** (JEP 425). API, cách triển khai và khả năng quan sát chưa là hợp đồng ổn định. | Cần `--enable-preview` khi biên dịch/chạy ví dụ dùng API preview; đối chiếu tài liệu riêng của JDK 19. |
| **JDK 20** | Preview lần hai (JEP 436); vẫn chưa phải API ổn định. Pinning do `synchronized` và native/foreign call vẫn là vấn đề. | Dùng công cụ của đúng JDK 20; đừng mặc định output giống JDK 21 trở về sau. |
| **JDK 21** | **Chính thức** theo JEP 444, là bản LTS. Có `Thread.ofVirtual()`, `Thread.startVirtualThread(...)`, `Executors.newVirtualThreadPerTaskExecutor()`. Blocking khi đang giữ monitor `synchronized` có thể pin carrier; native/foreign call cũng có thể pin. | `jcmd Thread.dump_to_file` (text/JSON), JFR các sự kiện virtual thread, và `-Djdk.tracePinnedThreads=full/short` để lần vết pinning trên các bản cũ. |
| **JDK 22–23** | Virtual thread tiếp tục là tính năng chính thức; giới hạn pinning liên quan `synchronized` về cơ bản vẫn tồn tại trong triển khai HotSpot trước JDK 24. | Đối chiếu JFR, thread dump và mã nguồn theo build; các lệnh scheduler riêng của JDK 24 chưa khả dụng. |
| **JDK 24** | **JEP 491**: virtual thread chặn trong/đợi monitor `synchronized` có thể nhả carrier; hiện tượng pinning do monitor được loại bỏ. Native method/foreign function vẫn có thể pin. | Bổ sung `jcmd Thread.vthread_scheduler`, `Thread.vthread_pollers` và `jdk.management.VirtualThreadSchedulerMXBean`. Chuyển sang JFR để chẩn đoán pinning; đừng dùng quy trình phụ thuộc `jdk.tracePinnedThreads` cũ. |
| **JDK 25–26** | Giữ hành vi mới từ JDK 24; virtual thread không yêu cầu bật preview. JFR vẫn hữu ích để tìm các nguyên nhân pinning còn lại, đặc biệt native/foreign frames. | Tiếp tục dùng dump đầy đủ, JFR, hai lệnh `jcmd` mới và scheduler MXBean; kiểm tra tên/trường event với đúng runtime. |
| **JDK 27** | Tiếp tục hỗ trợ virtual thread ổn định; **thay đổi tương thích công cụ** trong thread dump JSON: PID, thread ID, số lượng thread chuyển từ chuỗi sang số; bổ sung `threadDump.formatVersion = 2`. | Parser/ETL cũ giả định các trường này là string có thể lỗi. JFR cũng có thay đổi mặc định về che thông tin nhạy cảm trong command-line, properties và environment (JEP 536). |

**Ranh giới quan trọng:** virtual thread ổn định từ JDK 21; *Structured Concurrency* là API liên quan nhưng có vòng đời preview riêng (JDK 27 vẫn là preview). Không buộc `--enable-preview` chỉ để chạy `Thread.ofVirtual()` ở JDK 21+.

## 3. Hiểu đúng carrier, unmount và pinning theo phiên bản

Một virtual thread có thể trải qua ba tình huống khác nhau:

1. **Chờ mà unmount được:** khi chờ `Thread.sleep`, một số I/O hoặc primitive blocking hỗ trợ virtual thread, runtime cất trạng thái virtual thread và nhường carrier. Nhiều virtual thread chờ không đồng nghĩa nhiều OS thread bị chặn.
2. **Pinning:** virtual thread không thể nhả carrier trong lúc chờ. Trên HotSpot JDK 21–23, việc blocking bên trong `synchronized` là nguyên nhân nổi bật; từ JDK 24, trường hợp monitor này được giải quyết. Native/foreign frames vẫn cần quan sát.
3. **Lock contention:** các tác vụ tranh nhau cùng một monitor/lock và phải lần lượt vào vùng tới hạn. JDK 24 giảm *carrier pinning*, **không loại bỏ tính loại trừ lẫn nhau của `synchronized`**. Nếu 100 yêu cầu cùng chờ một lock, thời gian đáp ứng vẫn có thể xấu dù JFR không còn báo pinning do monitor.

Ví dụ một đoạn mã:

```java
synchronized (lock) {
    blockingCall(); // Ví dụ: thao tác chờ mạng hoặc sleep dài
}
```

- **JDK 21–23:** nếu virtual thread thực sự blocking trong đoạn trên, carrier có thể bị giữ lại. Pinning kéo dài và lặp lại làm giảm khả năng mở rộng; JFR `jdk.VirtualThreadPinned` có thể ghi nhận.
- **JDK 24+:** monitor không còn là nguyên nhân pinning cho loại blocking này. Tuy nhiên, nếu nhiều tác vụ dùng cùng `lock`, chúng vẫn nối hàng vì quy tắc đồng bộ; nếu `blockingCall` đi qua native/foreign code thì vẫn có thể phát sinh pinning từ nguyên nhân đó.
- **Cách sửa theo bằng chứng:** trên JDK 21–23, nếu JFR xác nhận pinning dài, lặp lại trong vùng `synchronized` có I/O, cân nhắc thu hẹp vùng lock, chuyển I/O ra ngoài lock hoặc dùng `ReentrantLock` đúng cách. Trên JDK 24+, ưu tiên phân tích tranh chấp lock và thời gian thao tác trước khi thay cơ chế đồng bộ. Không thay toàn bộ `synchronized` theo phản xạ.

`jdk.VirtualThreadPinned` không có nghĩa virtual thread bị deadlock; nó báo khoảng chờ không nhả được carrier vượt ngưỡng event. Ngược lại, **không thấy event không chứng minh không có vấn đề**: có thể thời lượng dưới ngưỡng, event bị tắt, bản JDK đã sửa pinning theo monitor hoặc tải thử chưa tái hiện.

## 4. Chọn đúng công cụ theo câu hỏi

| Cần biết | Công cụ | Phiên bản / giới hạn diễn giải |
| --- | --- | --- |
| Virtual thread nào đang làm/chờ việc gì? | `jcmd <PID> Thread.dump_to_file -format=text` hoặc `-format=json` | Dùng trên JDK 21+. Dump này hữu ích cho cả platform và virtual thread; là tập quan sát tại nhiều thời điểm, **không phải snapshot nguyên tử** và không tự làm deadlock detection. Có thể thiếu một phần virtual thread trong một số tình huống. |
| Carrier và platform thread đang chạy gì? | `jcmd <PID> Thread.print`, `jstack` | HotSpot dump kiểu truyền thống nhấn mạnh platform thread và các virtual thread **đang mounted**; không thay thế dump chuyên dụng khi phần lớn virtual thread đã unmount. |
| Pinning xảy ra ở đâu, bao lâu? | JFR `jdk.VirtualThreadPinned`; JDK 21–23 có thêm `-Djdk.tracePinnedThreads` | Ngưỡng JFR mặc định là **20 ms** khi event được bật theo cấu hình mặc định; bản ghi ngắn hơn ngưỡng có thể không xuất hiện. Trên JDK 24+, ưu tiên JFR. |
| Virtual thread tạo/kết thúc quá nhiều? | JFR `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` | Hai event thường **tắt mặc định**. Bật có chọn lọc; tải rất lớn có thể tạo lượng sự kiện khổng lồ. |
| Scheduler không nhận/không đưa tác vụ vào chạy? | JFR `jdk.VirtualThreadSubmitFailed` | Thường hướng tới vấn đề tài nguyên hoặc nộp/đánh thức tác vụ thất bại; không đồng nghĩa ngoại lệ nghiệp vụ của từng task. |
| Scheduler có hàng chờ lớn, bao nhiêu carrier đang dùng? | `jcmd <PID> Thread.vthread_scheduler` hoặc `VirtualThreadSchedulerMXBean` | **Từ JDK 24**. Đây là số liệu scheduler, không phải tổng số request nghiệp vụ hay toàn bộ virtual thread trong JVM. |
| Nhiều virtual thread chờ socket/network I/O? | `jcmd <PID> Thread.vthread_pollers` | **Từ JDK 24**. Số liệu poller giúp phân tích I/O mạng; không đo mọi kiểu chờ (lock, sleep, DB pool, file I/O). |
| Có bao nhiêu thread theo `ThreadMXBean`? | `java.lang.management.ThreadMXBean` | Chủ yếu theo dõi **platform thread**, không thống kê/điều khiển virtual thread như một tập đầy đủ. `ThreadGroup.activeCount()/enumerate()` cũng không liệt kê virtual thread như platform thread. |
| Phân tích dump JSON bằng công cụ nội bộ? | Parser của `Thread.dump_to_file` | **JDK 27 đổi schema sang v2**, phải kiểm tra kiểu dữ liệu và `formatVersion`; không khóa parser vào kiểu string của JDK 21–26. |

Các IDE và debugger hỗ trợ virtual thread qua giao thức debug (JDWP/JDI); khả năng nhóm, lọc, hiển thị hàng nghìn virtual thread phụ thuộc **phiên bản IDE/debugger** và JVM, không chỉ API Java. Khi thấy số lượng bất thường, so sánh với JFR và dump thay vì coi một màn hình debugger là nguồn duy nhất.

## 5. Quy trình điều tra sự cố có thể lặp lại

### Bước 1 — Chốt môi trường và triệu chứng

Ghi phiên bản Java runtime, OS, PID, cờ JVM, số CPU nhìn thấy trong container, loại tải (I/O hay CPU), tỷ lệ lỗi, p95/p99 latency, pool kết nối và giới hạn tài nguyên downstream. Phân biệt: throughput giảm, latency tăng, CPU cao, kẹt lock, kết nối cạn hay quá nhiều nhiệm vụ chờ. Virtual thread không thay thế connection pool, semaphore hay giới hạn số request ra dịch vụ khác.

### Bước 2 — Lấy thread dump phù hợp

```bash
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
jcmd <PID> Thread.print
```

Thực tế có thể cần dùng đường dẫn tuyệt đối tới file output và đảm bảo thư mục ghi tồn tại, tiến trình có quyền ghi. Dùng dump text để đọc stack nhanh, JSON để nhóm/filter theo tên, state, thread container và frame. Lấy vài mẫu cách nhau trong khoảng tái hiện để thấy stack có tiến triển hay đứng yên; đừng gộp các lần lấy mẫu thành một snapshot giả.

**Cách đọc kết quả:**
- Nhiều stack `WAITING`/`TIMED_WAITING` ở socket, queue hoặc `park` có thể là chờ hợp lệ. Ghép với thời gian downstream và request trace trước khi kết luận kẹt.
- Một số ít carrier trong `Thread.print` không có nghĩa ứng dụng chỉ có từng ấy virtual thread; phần lớn có thể đang unmounted.
- Dump chuyên dụng không tự thực hiện deadlock detection. Điều tra lock cần thêm quan hệ sở hữu lock, thứ tự lấy lock, log ứng dụng và công cụ phát hiện phù hợp.
- `threadCount` trong JSON có thể lớn hơn độ dài mảng `threads` nếu dump không chứa mọi virtual thread; không dùng `threads.length` làm tổng tuyệt đối.

### Bước 3 — Bật và đọc JFR đúng sự kiện

```bash
jcmd <PID> JFR.start name=vt settings=profile
# Tái hiện tình trạng, sau đó:
jcmd <PID> JFR.dump name=vt filename=vt.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt.jfr
```

Các lệnh trên là cú pháp mẫu cho JVM HotSpot có JFR; kiểm tra `jcmd <PID> help JFR.start` nếu công cụ/bản phân phối khác. Khi cần vòng đời virtual thread, tạo cấu hình JFR riêng bật `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`; mặc định hai event đó thường bị tắt. Trong JDK 26+, event pinning có thể chứa thông tin như `blockingOperation` và `pinnedReason`: hãy xem schema của recording thực tế, không viết parser giả định mọi đời JDK đều có cùng trường.

Trên JDK 21–23 có thể chạy riêng với `-Djdk.tracePinnedThreads=full` hoặc `short` để in stack khi pinning; lựa chọn này phù hợp với công cụ thời đó. Với JDK 24+, dùng JFR thay cho cờ cũ đã bị loại bỏ.

### Bước 4 — Kiểm tra scheduler trên JDK 24+

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

`VirtualThreadSchedulerMXBean` (module `jdk.management`, từ JDK 24) cung cấp chỉ số như `getParallelism()`, `getPoolSize()`, `getMountedVirtualThreadCount()` và `getQueuedVirtualThreadCount()`; có thể thay đổi target parallelism qua JMX nếu được phép. `parallelism` là số carrier mục tiêu cho scheduler, không phải giới hạn số virtual thread đang tồn tại. Mặc định scheduler thường dựa vào số processor khả dụng; `jdk.virtualThreadScheduler.parallelism` là một cấu hình cần ghi nhận khi so sánh.

**Diễn giải kết hợp:** hàng chờ scheduler tăng cùng CPU bão hòa có thể là nhiều tác vụ CPU/không nhường chạy; hàng chờ tăng trong JDK 21–23 kèm pinning dài có thể do thiếu carrier rảnh. Từ JDK 24+, nếu pinning do monitor biến mất nhưng latency còn cao, hãy kiểm tra lock contention, database pool, giới hạn socket, file descriptor, native frames và downstream. Không tăng parallelism như giải pháp đầu tiên khi chưa biết nút thắt.

### Bước 5 — So sánh cùng một workload trên các JDK

Giữ nguyên mã nguồn, dữ liệu, cấu hình tài nguyên, số worker/connection, thời gian warmup và phương pháp đo; đổi duy nhất runtime khi có thể. So sánh: thời gian chờ lock, p95/p99, throughput, CPU, số carrier đang dùng, scheduler queue, JFR pinning và số connection. Bảo toàn file `.jfr`, dump, PID/bản JDK và cấu hình để lần sau tái lập. Nếu đổi đồng thời JDK, framework và kết nối DB, không thể quy ngay thay đổi số liệu cho virtual thread.

## 6. Ví dụ chạy được: xác thực virtual thread trên JDK 21+

Lưu file **`VirtualThreadProbe.java`**:

```java
import java.util.concurrent.Executors;

public class VirtualThreadProbe {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            boolean virtual = executor
                    .submit(() -> Thread.currentThread().isVirtual())
                    .get();
            System.out.println("virtual=" + virtual);
        }
    }
}
```

Biên dịch/chạy với **JDK 21 trở lên**, không cần `--enable-preview`:

```bash
javac VirtualThreadProbe.java
java VirtualThreadProbe
```

Stdout chính xác:

```text
virtual=true
```

Giải thích: executor tạo một virtual thread cho mỗi task; trong task, `Thread.currentThread()` trả về virtual thread đang chạy, nên `isVirtual()` là `true`. `Future.get()` chờ kết quả; `try-with-resources` đóng executor sạch sẽ. `newVirtualThreadPerTaskExecutor()` **không phải pool tái sử dụng virtual thread**. Với JDK 19/20, ví dụ dùng API preview cần compiler/runtime của đúng phiên bản đó và cờ `--enable-preview`; không coi lệnh JDK 21 là hướng dẫn chạy nguyên xi cho preview.

## 7. Ví dụ đối chiếu pinning JDK 21–23 và JDK 24+

Lưu file **`PinningDemo.java`**:

```java
public class PinningDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().start(() -> {
            synchronized (MONITOR) {
                try {
                    Thread.sleep(300);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        worker.join();
        System.out.println("done");
    }
}
```

Biên dịch bằng JDK 21+, rồi chạy trên từng runtime muốn so sánh (biên dịch với target tương thích, ví dụ `javac --release 21 PinningDemo.java` khi dùng compiler mới). Stdout của chương trình không phụ thuộc phiên bản:

```text
done
```

Để thu JFR cho lần chạy thử:

```bash
javac PinningDemo.java
java -XX:StartFlightRecording:filename=pinning.jfr,dumponexit=true PinningDemo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

- Trên **JDK 21–23**, `Thread.sleep(300)` nằm bên trong monitor có thể làm virtual thread pin carrier; nếu recording bật event, thời gian đủ ngưỡng và triển khai đúng kỳ vọng, bạn có thể thấy `jdk.VirtualThreadPinned`.
- Trên **JDK 24+**, cùng `synchronized` không còn tạo pinning do monitor; không nên mong chờ event đó chỉ vì có monitor. Native/foreign code phát sinh trong workload khác vẫn có thể pin.
- Đây là **bài thử cơ chế**, không phải benchmark throughput: chỉ có một virtual thread nên không chứng minh mức cải thiện hiệu năng ứng dụng. Để benchmark, dùng nhiều tác vụ độc lập, điều kiện đo cố định và kiểm tra JFR lẫn metric.

Nếu tải thật liên tục chờ cùng một monitor, nâng cấp JDK 24+ có thể loại bỏ carrier pinning nhưng không làm biến mất hàng chờ lock. Phải đo đồng thời lock wait và scheduler.

## 8. Thay đổi quan trọng ở JDK 27: thread dump JSON v2

Từ **JDK 21 đến JDK 26**, thread dump JSON thường biểu diễn các định danh PID/thread và số lượng thread bằng **chuỗi**. **JDK 27** chuyển các trường này thành **number**, đồng thời thêm `threadDump.formatVersion` bằng `2`. Ví dụ tối giản minh họa phần cấu trúc (không phải file dump đầy đủ):

**Trước JDK 27 (kiểu cũ, trích đoạn):**

```json
{
  "threadDump": {
    "processId": "1234",
    "threadContainers": [
      {
        "threadCount": "1",
        "threads": [{"tid": "8", "name": "main"}]
      }
    ]
  }
}
```

**Từ JDK 27 (kiểu v2, trích đoạn):**

```json
{
  "threadDump": {
    "formatVersion": 2,
    "processId": 1234,
    "threadContainers": [
      {
        "threadCount": 1,
        "threads": [{"tid": 8, "name": "main"}]
      }
    ]
  }
}
```

Khi xây parser/dashboards:

1. Đọc `formatVersion` nếu có; nếu không có thì xem đó là khả năng định dạng legacy, nhưng vẫn validate cấu trúc thực tế.
2. Hỗ trợ cả string và number cho PID, `tid`, `threadCount`, `owner`, `carrier` và các trường định danh liên quan. Dùng kiểu số đủ rộng nếu công cụ cần tính toán; dùng biểu diễn thống nhất khi ghép key/index.
3. Không giả định số phần tử `threads` bằng `threadCount`; cấu trúc nhóm thread và phần thread chưa được lấy mẫu có thể làm chúng khác nhau.
4. Có bài kiểm thử parser với fixture từ JDK 21/24/26 **và** JDK 27. Đừng sửa file JSON thực bằng tìm–thay chuỗi: dễ làm hỏng kiểu dữ liệu hoặc các giá trị text khác.
5. JDK 27 còn có **JFR in-process data redaction** mặc định đối với thông tin nhạy cảm như command-line arguments và giá trị ban đầu của environment/system properties. Khi so sánh recordings cũ–mới, dữ liệu thiếu do redaction không được hiểu thành thay đổi hành vi virtual thread.

Mốc này tác động **định dạng dữ liệu quan sát**, không thay định nghĩa `Thread.isVirtual()` hoặc nguyên tắc lập lịch virtual thread.

## 9. Bốn tình huống chẩn đoán thường gặp

### Tình huống A — Cùng ứng dụng, JDK 21 có pinning event nhưng JDK 24 không còn

**Giả thuyết:** đoạn blocking bên trong `synchronized` từng pin carrier; JEP 491 đã khử nguyên nhân đó. **Xác minh:** cùng tải, cùng cấu hình JFR, đối chiếu stack/số sự kiện pinning và scheduler/latency. **Không kết luận vội:** nếu latency còn cao, đo lock contention và thời gian downstream; event biến mất không đồng nghĩa mọi chờ đợi biến mất.

### Tình huống B — JDK 26 có scheduler queue cao nhưng `Thread.print` trông rất ít thread

**Giả thuyết:** nhiều virtual thread đang unmounted hoặc đang đợi lịch; `Thread.print` chỉ thấy platform và virtual thread mounted ở thời điểm chụp. **Xác minh:** `Thread.dump_to_file`, `Thread.vthread_scheduler`, `Thread.vthread_pollers`, JFR và request trace. **Hành động:** xác định đang bị nghẽn CPU, I/O, downstream, đồng bộ hay native trước khi tăng target parallelism.

### Tình huống C — `ThreadMXBean.getThreadCount()` nhỏ nhưng ứng dụng đang có hàng chục nghìn request

**Giả thuyết:** chỉ số chỉ phản ánh platform thread; virtual thread không được thống kê đầy đủ ở MXBean này. **Xác minh:** thread dump dành cho virtual thread, metric nghiệp vụ và request đang mở. **Hành động:** không dùng duy nhất `ThreadMXBean` để cảnh báo số virtual thread; chọn dữ liệu phù hợp với mục đích.

### Tình huống D — Công cụ đọc dump hoạt động trên JDK 26 nhưng lỗi sau nâng cấp JDK 27

**Giả thuyết:** parser yêu cầu `tid`/`processId` là string trong khi dump v2 trả number. **Xác minh:** kiểm tra `formatVersion` và kiểu JSON thực. **Hành động:** bổ sung parser hỗ trợ schema v1/v2, fixture và regression test; giữ thông tin runtime version trong mỗi artifact chẩn đoán.

## 10. Những ngộ nhận cần tránh

- **“Blocking là pinning.”** Sai. Virtual thread thường *được thiết kế để chờ* và nhả carrier. Chỉ khi carrier không thể được nhả trong lúc chờ mới là pinning theo nghĩa chẩn đoán này.
- **“JDK 24 bỏ `synchronized` hoặc tự hết lock contention.”** Sai. Thay đổi xử lý monitor giúp tránh pin carrier, không thay quy tắc mutual exclusion.
- **“Không có `jdk.VirtualThreadPinned` nghĩa không có nút thắt.”** Sai. Cần xét ngưỡng/cấu hình JFR, tải thực, version và các loại bottleneck khác.
- **“`jstack`, `Thread.print`, `ThreadMXBean` thấy hết virtual threads.”** Sai. Chúng không thay thế thread dump chuyên dụng cho cả các virtual thread unmounted.
- **“Mỗi virtual thread tương ứng một OS thread.”** Sai. Carrier được tái sử dụng; khi virtual thread unmount, nó không chiếm carrier.
- **“Số thread cao thì phải giới hạn bằng virtual-thread pool.”** Sai. Dùng mỗi virtual thread cho một tác vụ; dùng `Semaphore`, connection pool và giới hạn downstream để kiểm soát tài nguyên thực.
- **“Tăng scheduler parallelism chắc chắn tăng throughput.”** Sai. Nếu nghẽn ở CPU, connection, lock hoặc dịch vụ ngoài, thay đổi đó có thể không giúp ích và cần đo.
- **“Dùng cờ preview cho mọi phiên bản.”** Sai. Chỉ preview JDK 19/20 cho virtual thread; từ JDK 21, tính năng đã chính thức. Preview của Structured Concurrency là vấn đề riêng.
- **“JSON thread dump có schema cố định.”** Sai. JDK 27 đổi các trường số và bổ sung `formatVersion`; parser cần tương thích nhiều phiên bản.

## 11. Checklist trước khi kết luận nguyên nhân

- [ ] Đã ghi **runtime JDK + build/vendor**, PID, OS, CPU quota và JVM options của ứng dụng.
- [ ] Đã xác định JDK **21–23** hay **24+** trước khi quy lỗi cho pinning do `synchronized`.
- [ ] Đã phân biệt **blocked, unmounted, pinned, lock contention**, CPU saturation và downstream wait.
- [ ] Đã dùng `Thread.dump_to_file` để nhìn virtual thread, không chỉ `Thread.print`/`ThreadMXBean`.
- [ ] Đã thu JFR đúng event và biết ngưỡng `jdk.VirtualThreadPinned`; không diễn giải sự vắng mặt của event như bằng chứng tuyệt đối.
- [ ] Nếu là JDK **24+**, đã dùng scheduler/pollers command hoặc MXBean khi cần nhìn hàng đợi/carrier.
- [ ] Nếu là **JDK 27**, công cụ parse JSON đã xử lý `formatVersion=2` và các trường số; đã lưu ý redaction trong JFR.
- [ ] Đã đối chiếu stack, JFR, metric/trace và tải đo trước khi đề xuất đổi lock, scheduler hay nâng JDK.

## 12. Tài liệu đối chiếu theo đúng phiên bản

- JEP 425 — Virtual Threads (JDK 19 preview): https://openjdk.org/jeps/425
- JEP 436 — Virtual Threads (JDK 20 second preview): https://openjdk.org/jeps/436
- JEP 444 — Virtual Threads (JDK 21 final): https://openjdk.org/jeps/444
- JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24): https://openjdk.org/jeps/491
- Oracle JDK 21, Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Oracle JDK 26, Virtual Threads và diagnostic tools: https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html
- Oracle JDK 26, lệnh `jcmd`: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
- Oracle JDK 24 Release Notes (scheduler MXBean, `jcmd` pollers/scheduler): https://www.oracle.com/java/technologies/javase/24-relnote-issues.html
- Oracle JDK 27 Release Notes (JDK-8381002 và JFR redaction): https://www.oracle.com/java/technologies/javase/27-relnote-issues.html
- JDK 27 JSON Thread Dump Format: https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/com/sun/management/doc-files/threadDump.html

**Quy tắc thực hành:** luôn gắn câu kết luận với **JDK + phiên bản công cụ + bằng chứng quan sát**. Một dump/JFR “khác đi” sau nâng JDK có thể phản ánh thay đổi scheduler, thay đổi cách capture hoặc thay đổi schema, nên phải phân tích ba khả năng đó riêng trước khi quy là lỗi chương trình.
