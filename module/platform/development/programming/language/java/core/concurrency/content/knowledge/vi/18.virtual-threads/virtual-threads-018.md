# Giới hạn của ThreadMXBean và cách dùng jcmd Thread.dump_to_file để quan sát Virtual Threads

## 1. Vì sao kiểm tra thread theo cách cũ dễ dẫn đến kết luận sai?

Từ Java 21, **virtual thread** là một `java.lang.Thread` do JVM quản lý. Nó phù hợp với nhiều công việc đồng thời phải chờ I/O; JVM có thể tạm dừng một virtual thread và dùng platform thread (carrier) để chạy công việc khác. Một ứng dụng có thể đang có hàng nghìn virtual threads trong khi số platform threads tương đối ít.

Vì vậy, việc kiểm tra một giá trị như `ManagementFactory.getThreadMXBean().getThreadCount()` rồi kết luận “ứng dụng chỉ có vài chục thread” **không đúng với tổng số virtual threads**. API này được định nghĩa để quản lý **platform threads**, không quản lý virtual threads. Muốn nhìn thấy stack của virtual threads tại một thời điểm, hãy dùng công cụ chẩn đoán hỗ trợ chúng như `jcmd <PID> Thread.dump_to_file`.

Phạm vi bài này là Java SE/JDK nói chung. Các ví dụ sử dụng **JDK 21+** và chạy được mà không cần framework.

## 2. Hiểu ranh giới: platform thread, carrier và virtual thread

- **Platform thread**: thread Java gắn với một luồng hệ điều hành. `ThreadMXBean` tập trung theo dõi nhóm này.
- **Virtual thread**: thread Java nhẹ, được JVM lập lịch. Một tác vụ đang chờ có thể tạm thời không chiếm carrier.
- **Carrier thread**: platform thread mà scheduler đang dùng để chạy một virtual thread trong khoảng nó được mount. Một carrier có thể lần lượt phục vụ nhiều virtual threads, nên **không có tỷ lệ 1:1**.

Ví dụ: một ứng dụng có 4.000 virtual threads đang chờ tác vụ I/O. `ThreadMXBean.getThreadCount()` có thể vẫn chỉ báo một lượng platform threads nhỏ. Hai giá trị đo **hai đối tượng khác nhau**; giá trị nhỏ của `ThreadMXBean` không chứng minh ứng dụng không có tồn đọng tác vụ.

```text
                Java process (JVM)
┌───────────────────────────────────────────────┐
│  Virtual threads (công việc logic)            │
│  VT-1  ─── chờ I/O                             │
│  VT-2  ─── chờ I/O                             │
│  VT-3  ─── đang chạy                           │
│  VT-4  ─── có thể sẵn sàng chạy                │
│  ...                                          │
│                     │                         │
│           JVM scheduler/carriers              │
│                     ▼                         │
│  Platform threads (OS threads)                 │
│  carrier-A, carrier-B, main, GC/JVM threads... │
└───────────────────────────────────────────────┘
  ThreadMXBean       → platform threads
  jcmd dump_to_file  → platform + virtual threads
```

Hình trên chỉ minh họa sự khác nhau về phạm vi quan sát, không mô tả số carrier cố định hay bảo đảm cách JVM lập lịch một tác vụ cụ thể.

## 3. ThreadMXBean hỗ trợ gì, giới hạn ở đâu?

`java.lang.management.ThreadMXBean` lấy qua `ManagementFactory.getThreadMXBean()` (hoặc JMX với ObjectName `java.lang:type=Threading`). Theo Java SE 21, giao diện này **không hỗ trợ theo dõi/quản lý virtual threads**.

| Phương thức | Giá trị trong ứng dụng có virtual threads |
| --- | --- |
| `getThreadCount()` | Số **platform threads** đang sống; không cộng số virtual threads |
| `getPeakThreadCount()` | Đỉnh số platform threads, không phải đỉnh số virtual threads |
| `getTotalStartedThreadCount()` | Số platform threads từng được khởi động, không cộng virtual threads |
| `getAllThreadIds()` | ID của các platform threads đang sống; không liệt kê ID virtual threads |
| `dumpAllThreads(...)` | `ThreadInfo`/stack của platform threads, không dump mọi virtual thread |
| `getThreadInfo(virtualThreadId)` | Trả `null` cho ID virtual thread, dù virtual thread đó còn sống |
| `findDeadlockedThreads()` / `findMonitorDeadlockedThreads()` | Phát hiện chu trình deadlock trong phạm vi platform threads; không phát hiện chu trình có virtual thread |
| `getThreadCpuTime(id)` | API CPU-time quản lý platform threads; không dùng làm bộ đo CPU-time của từng virtual thread |

Một số sai lầm thường gặp:

- Đặt cảnh báo “số thread tổng” theo `getThreadCount()` rồi nghĩ rằng nó đã tính mọi virtual thread.
- Gọi `dumpAllThreads(true, true)` và coi đó là ảnh chụp đầy đủ mọi công việc concurrent.
- Tìm virtual thread trong `getAllThreadIds()` và suy diễn rằng thread chưa được tạo vì không thấy ID.
- Dùng `Thread.getAllStackTraces()` để liệt kê hết virtual threads: từ JDK 21 API này cũng chỉ trả về platform threads.
- Thấy nhiều carrier thì cho rằng có bằng ấy virtual threads, hoặc thấy ít carrier thì cho rằng có ít yêu cầu.

**ThreadMXBean vẫn hữu ích** cho việc xem platform threads, thông tin đồng bộ liên quan và xu hướng số carrier/OS threads, nhưng phạm vi của nó phải được ghi rõ trên dashboard. Nếu cần số tác vụ đang chạy, đang chờ I/O, thời gian xử lý và timeout của ứng dụng, hãy bổ sung metric ở tầng xử lý tác vụ. Đừng cố suy số virtual threads chỉ từ platform-thread count.

## 4. Thực hành: một chương trình Java 21 có 12 virtual threads đang chờ

Ví dụ sau giữ 12 virtual threads sống trong lúc người học chạy `jcmd` từ cửa sổ terminal khác. Để dễ tìm trong dump, các virtual threads đều có tên bắt đầu bằng `demo-vt-`. Chương trình tự in PID của JVM, so sánh với `ThreadMXBean` và giữ trạng thái khoảng 90 giây.

Tạo file `VirtualThreadDumpDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class VirtualThreadDumpDemo {
    private static final int WORKERS = 12;

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < WORKERS; i++) {
            Thread thread = Thread.ofVirtual()
                    .name("demo-vt-" + i)
                    .start(() -> {
                        ready.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
            workers.add(thread);
        }

        // Tất cả virtual threads đã đi đến đoạn báo ready.
        ready.await();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long sampleVirtualThreadId = workers.get(0).threadId();
        boolean listed = Arrays.stream(bean.getAllThreadIds())
                .anyMatch(id -> id == sampleVirtualThreadId);

        System.out.println("virtualThreadsStarted=" + WORKERS);
        System.out.println("sampleVirtualThreadListedByMXBean=" + listed);
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("platformThreadsByMXBean=" + bean.getThreadCount());
        System.out.println("Run jcmd in another terminal within 90 seconds");

        try {
            Thread.sleep(90_000);
        } finally {
            // Cho virtual threads kết thúc và tránh rò công việc ở ví dụ.
            release.countDown();
            for (Thread thread : workers) {
                thread.join();
            }
        }
    }
}
```

Biên dịch/chạy bằng **JDK 21 trở lên**:

```bash
javac VirtualThreadDumpDemo.java
java VirtualThreadDumpDemo
```

Ví dụ phần đầu output (PID và số platform threads **không cố định**):

```text
virtualThreadsStarted=12
sampleVirtualThreadListedByMXBean=false
pid=<PID thực tế do chương trình in>
platformThreadsByMXBean=<số thay đổi theo JVM/môi trường>
Run jcmd in another terminal within 90 seconds
```

Vì sao `false` là kết quả mong đợi? `workers.get(0)` là một virtual thread còn sống, nhưng `ThreadMXBean.getAllThreadIds()` theo đặc tả chỉ liệt kê platform threads. `getThreadCount()` cũng có thể đổi theo hoạt động của JVM/scheduler; không có giá trị tuyệt đối nào đúng cho tất cả máy. Dòng `CountDownLatch.await()` khiến tác vụ virtual thread có stack đang chờ rõ ràng trong dump.

Mẹo khi luyện tập: hãy mở hai terminal, chạy chương trình trong terminal thứ nhất, dùng PID do chương trình vừa in trong terminal thứ hai. Nếu hết 90 giây, chạy lại chương trình và lấy PID mới. Không lấy PID của tiến trình `jcmd` thay cho PID ứng dụng.

## 5. Dùng jcmd Thread.dump_to_file từng bước

`jcmd` là tiện ích đi kèm **JDK**, gửi diagnostic command đến một JVM đang chạy. Lệnh `Thread.dump_to_file` tạo thread dump vào file, gồm **platform threads và virtual threads**. So với `ThreadMXBean.dumpAllThreads()`, đây là công cụ thích hợp để quan sát nhiều virtual threads, kể cả virtual threads bị chặn chờ công việc.

### Bước 1: xác định đúng JVM và quyền truy cập

Chạy từ terminal khác trên cùng máy/môi trường có thể attach đến tiến trình Java:

```bash
jcmd -l
```

Lệnh này hữu ích để liệt kê các Java processes nhìn thấy từ môi trường của `jcmd`. Trong container hoặc JVM không hiển thị được trong `jcmd -l`, dùng PID in từ `ProcessHandle.current().pid()`, `ps`, hoặc công cụ tiến trình tương ứng. Đừng mặc định PID ở host giống PID trong container khác PID namespace.

Điều kiện thông thường: công cụ `jcmd` phải tương thích với JVM đích, quyền người dùng đủ để attach, JVM chưa tắt và không chặn Attach API bằng cấu hình. Kiểm tra lệnh chẩn đoán hiện có cho **JVM đích**:

```bash
jcmd 12345 help
jcmd 12345 help Thread.dump_to_file
```

Thay **12345** bằng PID thật. Cú pháp, tùy chọn và định dạng có thể khác giữa các phiên bản JDK; nguồn chính xác khi thao tác là kết quả `help` của JVM đang chạy.

### Bước 2: tạo dump dạng JSON

Trên Linux/macOS, chọn **đường dẫn tuyệt đối** trong filesystem mà tiến trình Java đích có quyền ghi:

```bash
jcmd 12345 Thread.dump_to_file -format=json /tmp/virtual-threads-12345.json
```

Trên Windows, dùng một thư mục đã tồn tại và có thể ghi, chẳng hạn `C:\temp`:

```powershell
jcmd 12345 Thread.dump_to_file -format=json C:\temp\virtual-threads-12345.json
```

Đây là **mẫu lệnh**: PID và đường dẫn phải thay cho đúng môi trường. Đường dẫn được JVM đích sử dụng để ghi file, nên chạy `jcmd` ở host ngoài container không tự động đưa dump ra filesystem của host. Với container, nên chạy `jcmd` bên trong cùng container/namespace hoặc lấy file dump ra bằng cơ chế quản lý container sau khi tạo.

Tạo tên file mới cho mỗi lần dump để tránh lỗi file đã tồn tại. Một số phiên bản hỗ trợ tùy chọn `-overwrite`/`-overwrite=true`; hãy kiểm tra bằng `jcmd <PID> help Thread.dump_to_file` rồi chỉ dùng khi muốn thay thế file cũ.

### Bước 3: tạo dump dạng văn bản

Không ghi `-format` thì định dạng mặc định thường là **plain text** theo `help` của JVM hỗ trợ lệnh:

```bash
jcmd 12345 Thread.dump_to_file /tmp/virtual-threads-12345.txt
```

Hướng dẫn Virtual Threads của Oracle cho Java 21 còn minh họa `-format=text`. Tài liệu của các JDK mới có thể mô tả tên định dạng plain là `plain`. Để tránh phụ thuộc cách đặt tên tùy phiên bản, hãy ưu tiên **`-format=json`** khi cần xử lý bằng công cụ, hoặc dùng mặc định dạng text sau khi đã kiểm tra `help` trên JVM đích.

### Bước 4: xem kết quả

Một thread dump JSON thường có đối tượng gốc `threadDump`, thông tin tiến trình/thời điểm và dữ liệu thread containers. Các phần tử được nhóm theo container của thread; cấu trúc và trường có thể thay đổi theo phiên bản JDK. Với ví dụ trên, hãy tìm chuỗi `demo-vt-` và stack chứa `CountDownLatch.await`.

```bash
# Linux/macOS: chỉ lọc để định vị vị trí trong JSON;
# không dùng grep như trình phân tích JSON có cấu trúc.
grep -n "demo-vt-" /tmp/virtual-threads-12345.json
```

Ví dụ lọc bằng PowerShell khi chạy Windows:

```powershell
Select-String -Path C:\temp\virtual-threads-12345.json -Pattern 'demo-vt-'
```

Khi cần đếm/nhóm thread theo tên hoặc stack, nên dùng **JSON parser** phù hợp với cấu trúc của bản dump thật, không dựa vào việc “mỗi thread là một dòng JSON”. Đọc file dump trực tiếp bằng editor cũng hữu ích khi chẩn đoán một số lượng thread vừa phải.

## 6. Cách đọc virtual thread dump để trả lời câu hỏi thực tế

Dùng một lần dump như **ảnh chụp trạng thái tại thời điểm lấy**. Một dump có thể cho thấy virtual thread đang ở stack nào và đang chờ thao tác gì; nó không tự cho biết thời gian đã chờ bao lâu, nguyên nhân gốc hoặc quãng thời gian trước đó.

| Quan sát | Ý nghĩa có thể xảy ra | Việc nên kiểm chứng thêm |
| --- | --- | --- |
| Nhiều `demo-vt-*` chờ `CountDownLatch.await` | Đúng với thử nghiệm đang cố tình giữ thread | Sau `release.countDown()` chúng có biến mất không? |
| Nhiều virtual threads cùng chờ pool kết nối hoặc semaphore | Nút cổ chai ở quyền truy cập tài nguyên giới hạn | Pool max/active/pending, timeouts, thời gian giữ resource |
| Nhiều stack chờ I/O mạng | Bên ngoài trả lời chậm hoặc có nhiều lời gọi in-flight | Timeout, latency, tỷ lệ lỗi của dịch vụ ngoài |
| Nhiều stack lặp lại tại một khóa/đồng bộ | Có thể có contention hoặc thiết kế khóa chưa phù hợp | Đường sở hữu khóa, thời gian giữ khóa, trạng thái ở nhiều lần dump |
| Số platform threads thấp nhưng dump có rất nhiều virtual threads | `ThreadMXBean` đang đo một tập khác | Đếm và đo tasks trong ứng dụng, quan sát tốc độ vào/ra |

Quy trình thực tế:

1. Ghi nhận triệu chứng cụ thể: request chậm, timeout, dùng tài nguyên cao hoặc không tiến triển.
2. Xác nhận PID, phiên bản JDK, thời điểm lấy và chính sách dữ liệu nhạy cảm trong stack.
3. Lấy một dump bằng `Thread.dump_to_file`; nếu vấn đề kéo dài, lấy vài dump cách nhau hợp lý để so sánh stack có tiến triển hay không.
4. Nhóm theo tên thread, đường stack nổi bật và trạng thái chờ; đối chiếu với metric I/O, connection pool, queue và logs.
5. Xác định tài nguyên nào bị nghẽn, kiểm tra giới hạn đồng thời, timeout, đóng tài nguyên và tốc độ đầu vào trước khi thay đổi cấu hình.

**Giải thích đúng về trạng thái chờ:** virtual thread đang chờ I/O không nhất thiết tiêu tốn một carrier trong suốt thời gian chờ. Chờ có thể là hoạt động bình thường khi workload nhiều I/O. Vấn đề là hàng đợi tăng liên tục, độ trễ xấu đi, tài nguyên không trả về hoặc công việc không còn hoàn thành.

## 7. So sánh với Thread.print, jstack và các API trong code

`Thread.print` và `jstack` theo truyền thống hữu ích khi điều tra platform threads, native frames và vấn đề liên quan JVM/monitor. Tuy nhiên, đặc biệt trong JDK 21, đừng trông chờ một **traditional thread dump** của chúng liệt kê tất cả virtual threads đang unmounted. Cách được Oracle hướng dẫn để nhìn virtual threads là `jcmd Thread.dump_to_file`.

| Công cụ | Khi nên dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| `ThreadMXBean` | Theo dõi số platform threads, stack/đồng bộ của platform threads và JMX metrics | Loại trừ virtual threads |
| `Thread.getAllStackTraces()` | Stack của platform threads thông qua Java API | Không bao quát mọi virtual threads |
| `jcmd <PID> Thread.print` | Traditional dump; thông tin platform threads/JVM bổ trợ | Không thay cho dump đầy đủ virtual threads, mức độ hiển thị tùy JDK |
| `jcmd <PID> Thread.dump_to_file` | Snapshot platform + virtual threads, xuất text/JSON | Không đầy đủ metadata truyền thống như object addresses, native/JNI/heap; khả năng thông tin lock phụ thuộc phiên bản |
| JDK Flight Recorder (JFR) | Phân tích sự kiện, khoảng thời gian, nguyên nhân latency/pinning | Cần cấu hình recording và sự kiện tương ứng |
| Metrics do ứng dụng ghi | Đếm tasks, độ trễ, timeout, queue, resource usage | Phải đặt phép đo tại đúng luồng nghiệp vụ và tài nguyên |

Không suy ra rằng `ThreadMXBean.findDeadlockedThreads() == null` chứng minh **không có deadlock nào** trong ứng dụng sử dụng virtual threads: nó chỉ được thiết kế cho các chu trình deadlock của platform threads. Để xác định sự cố tương tác nhiều khóa/tài nguyên, hãy phân tích stack, thay đổi trạng thái qua nhiều thời điểm và luồng điều khiển nghiệp vụ.

## 8. Quan sát lâu dài: JFR, metric ứng dụng và scheduler (JDK 24+)

Thread dump giúp trả lời **“đang xảy ra chuyện gì bây giờ?”**; JFR và metrics giúp trả lời **“nó diễn ra bao lâu, với tần suất nào và có xu hướng gì?”**.

Trên Java 21, JFR có các sự kiện như:

- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`: vòng đời virtual thread; **mặc định bị tắt** để tránh overhead khi số lượng thread rất lớn.
- `jdk.VirtualThreadPinned`: sự kiện virtual thread bị pin dài hơn ngưỡng đã cấu hình; theo hướng dẫn Java 21, sự kiện này mặc định bật với threshold 20 ms.
- `jdk.VirtualThreadSubmitFailed`: không thể submit/unpark virtual thread, có thể do vấn đề tài nguyên.

Có thể cấu hình recording theo yêu cầu, rồi đọc các sự kiện liên quan trong file `recording.jfr`:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

`recording.jfr` phải là file đã được ghi từ một JFR recording; lệnh trên **chỉ đọc**, không khởi tạo recording. Những thiết lập/sự kiện cụ thể nên kiểm tra theo bản JDK đang dùng.

Từ **JDK 24**, JDK bổ sung `jdk.management.VirtualThreadSchedulerMXBean`, cung cấp các chỉ số về scheduler như target parallelism, số carrier platform threads trong scheduler và số virtual threads đang đợi scheduler được lập lịch (các giá trị có thể là ước lượng). Đây là **MXBean khác** với `java.lang.management.ThreadMXBean`, và **không có sẵn trên JDK 21**.

Ví dụ cách lấy bean trên **JDK 24+** (đoạn minh họa, yêu cầu môi trường đã có module `jdk.management`):

```java
import java.lang.management.ManagementFactory;
import jdk.management.VirtualThreadSchedulerMXBean;

VirtualThreadSchedulerMXBean scheduler =
        ManagementFactory.getPlatformMXBean(VirtualThreadSchedulerMXBean.class);

if (scheduler != null) {
    System.out.println("parallelism=" + scheduler.getParallelism());
    System.out.println("carrierPoolSize=" + scheduler.getPoolSize());
    System.out.println("queuedVirtualThreads~=" + scheduler.getQueuedVirtualThreadCount());
}
```

Đoạn trên là **snippet**, không phải một lớp Java hoàn chỉnh; `jdk.management.VirtualThreadSchedulerMXBean` chỉ có từ JDK 24. `getQueuedVirtualThreadCount()` phản ánh virtual threads chờ **scheduler**, không đồng nghĩa số tác vụ đang chờ connection pool, semaphore hay kết quả I/O. Không dùng nó làm tổng số virtual threads tồn tại trong process.

Ở tầng ứng dụng, nên có các phép đo rõ ràng:

- Số tác vụ virtual-thread được bắt đầu/hoàn thành/hủy, số tác vụ in-flight và thời gian chờ.
- Tỷ lệ lỗi, timeout của I/O bên ngoài, active/idle/waiting của connection pool.
- Queue/admission backlog và số yêu cầu bị từ chối khi quá tải.
- CPU, memory, GC và các chỉ số platform-thread/carrier riêng biệt.

Khi chẩn đoán vấn đề, dùng JFR hoặc các công cụ profile thích hợp cùng dump/metrics thay vì chỉ xem một số `getThreadCount()`.

## 9. Lỗi phổ biến và cách tự kiểm tra

**Không thấy virtual thread trong `ThreadMXBean` → kết luận thread đã chết.** Kiểm tra `Thread.isVirtual()` và `Thread.isAlive()` khi đã có tham chiếu đến thread; dùng `jcmd Thread.dump_to_file` để quan sát stack. `ThreadMXBean` bỏ sót virtual threads theo thiết kế.

**Dump không chứa tên `demo-vt-*`.** Kiểm tra tiến trình còn sống, PID có đúng, có lấy dump trước khi các thread kết thúc không, và đã chạy đúng chương trình Java 21+ chưa. Thử lại khi các virtual threads đang chờ `CountDownLatch`.

**Dùng `jcmd` sai môi trường/container.** Kiểm tra attach permission, namespace PID, file path từ góc nhìn JVM đích, quyền ghi và tài khoản chạy công cụ. Xem `jcmd <PID> help Thread.dump_to_file`. Nếu tiến trình không cho attach, chẩn đoán theo cơ chế quản lý JVM/container hiện hành.

**Cho rằng file dump có toàn bộ metadata truyền thống.** Định dạng dump tối ưu cho virtual threads không cung cấp mọi thông tin như object addresses, JNI hoặc heap; dữ liệu về khóa có khác biệt theo JDK. Kết hợp `Thread.print`/JFR/metrics khi cần các góc nhìn đó.

**Đếm số lần xuất hiện chữ “virtual” trong file làm số thread chính xác.** Một stack hoặc metadata có thể chứa nhiều lần từ khóa. Hãy parse thread entries theo định dạng thực tế hoặc đo số in-flight tại ứng dụng.

**Lấy một dump rồi kết luận deadlock/leak.** Snapshot đơn lẻ không cho biết xu hướng. So sánh nhiều lần lấy dump và dữ liệu pool/queue; xác định tài nguyên nào không được giải phóng và tác vụ nào không tiến triển.

**Bật tất cả JFR start/end events trong tải rất lớn mà không cân nhắc.** Vòng đời virtual thread có thể xảy ra với tần suất cao. Cấu hình sự kiện, thời gian ghi và dung lượng recording theo mục tiêu điều tra.

## 10. Bài tập kiểm chứng

1. Chạy `VirtualThreadDumpDemo.java`, kiểm tra hai dòng chắc chắn: `virtualThreadsStarted=12` và `sampleVirtualThreadListedByMXBean=false`.
2. Dùng PID chương trình in ra để chạy `jcmd <PID> help Thread.dump_to_file`, sau đó xuất một JSON dump.
3. Tìm tên `demo-vt-0`, stack đợi `CountDownLatch.await` và xác nhận đó là virtual thread trong dump.
4. Chờ ví dụ kết thúc, chạy lại một lần và lấy dump sau khi bạn thay `WORKERS` từ 12 thành 100. So sánh số virtual threads tìm được với `getThreadCount()`; không kỳ vọng platform-thread count tăng tuyến tính.
5. Giải thích vì sao `ThreadMXBean` vẫn hữu ích để theo dõi platform threads, và dùng công cụ nào để chẩn đoán virtual threads cùng các nút cổ chai I/O.

## Tóm tắt kiến thức

- `ThreadMXBean` chỉ quản lý **platform threads**; `getThreadCount()`, `getAllThreadIds()`, `dumpAllThreads()` không cho tổng số hay stack đầy đủ của virtual threads.
- `jcmd <PID> Thread.dump_to_file -format=json <absolute-file>` là cách chuẩn từ JDK 21 để tạo thread dump gồm cả **platform và virtual threads**.
- Dump là **snapshot**. Phân tích stack với thời điểm và kết hợp metric/JFR để kết luận về contention, I/O, deadlock hoặc quá tải.
- `jdk.management.VirtualThreadSchedulerMXBean` từ JDK 24 có phạm vi scheduler, **không phải** cách thay thế hoàn toàn `ThreadMXBean` và không đo mọi virtual threads đang sống.

## Tài liệu chính thức

1. [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): giới hạn phạm vi platform threads, `getThreadInfo`, `getAllThreadIds` và deadlock detection.
2. [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): thread dump qua `jcmd`, carrier, debugging và JFR.
3. [Java SE 22 — jcmd command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html): cách dùng diagnostic commands và tham số `Thread.dump_to_file`.
4. [Java SE 24 — VirtualThreadSchedulerMXBean API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): những chỉ số scheduler bổ sung từ JDK 24.
