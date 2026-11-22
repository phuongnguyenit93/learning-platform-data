# 22.8. Điều tra pinning của virtual thread trong môi trường Java 21

**Pinning** là một tình huống quan trọng khi chẩn đoán ứng dụng Java 21 dùng virtual threads: một virtual thread đang thực hiện thao tác **blocking** nhưng **không thể unmount** khỏi platform thread đang mang nó (*carrier thread*). Carrier vì vậy bị giữ trong lúc chờ, thay vì được JVM tái sử dụng để chạy virtual thread khác. Nếu tình huống xảy ra **thường xuyên và kéo dài**, throughput/concurrency có thể giảm mạnh dù ứng dụng đã dùng rất nhiều virtual threads.

Pinning **không phải exception**, không mặc nhiên là deadlock và không tự chứng minh ứng dụng đang lỗi. Một khối `synchronized` ngắn chỉ cập nhật vài biến trong bộ nhớ thường không gây tác động đáng kể. Câu hỏi vận hành cần trả lời là: **đang block ở đâu, mất bao lâu, xuất hiện bao nhiêu lần, carrier có bị chiếm hết trong lúc tải cao hay không và liệu đó có phải nguyên nhân của độ trễ hiện tại?**

Bài thực hành này cố ý tập trung **JDK 21** (virtual threads đã là tính năng chính thức từ JEP 444); yêu cầu chạy các ví dụ bằng **JDK 21+**, nhưng phần pinning do `synchronized` phản ánh hành vi **JDK 21**. **JDK 24 thay đổi hành vi này nhờ JEP 491**; vì vậy cùng một ví dụ có thể cho kết quả rất khác trên JDK 24 trở lên. Không lấy kết quả từ JDK 24/25/26 rồi kết luận JDK 21 không có vấn đề.

## 1. Virtual thread, platform thread và carrier

Một platform thread thường gắn với một OS thread. Virtual thread là `java.lang.Thread` nhưng được JVM lên lịch chạy trên một số lượng nhỏ hơn platform threads, gọi là **carriers**. Khi một virtual thread thực hiện blocking operation mà JDK hỗ trợ unmount, runtime có thể tách virtual thread khỏi carrier trong lúc chờ; carrier được trả về scheduler để chạy công việc khác.

```text
                JVM virtual-thread scheduler
                          │
           ┌──────────────┴──────────────┐
           ▼                             ▼
       Carrier #1                    Carrier #2
           │                             │
           ▼                             ▼
       Virtual A                     Virtual B
           │                             │
           │ blocking I/O có thể unmount │
           ▼                             ▼
    A được tạm lưu                  B tiếp tục chạy
           │
           └─ Carrier #1 rảnh để chạy Virtual C
```

Điều làm virtual threads hiệu quả với workload I/O-bound là **nhiều công việc có thể đang chờ** nhưng không cần chiếm tương ứng từng OS thread. Virtual threads **không làm CPU chạy nhanh hơn** và không tự tạo thêm CPU cores. Một dịch vụ CPU-bound hoặc bị giới hạn DB connection pool vẫn có thể nghẽn dù có hàng nghìn virtual threads.

Khi pinning xảy ra:

```text
Virtual A mounted trên Carrier #1
          │
          ▼
Vào synchronized / native context (trong JDK 21)
          │
          ▼
Thực hiện một blocking operation
          │
          ▼
Không thể unmount khỏi Carrier #1
          │
          ▼
Carrier #1 cũng phải chờ, không chạy Virtual C
```

**Không đồng nhất hai khái niệm**: virtual thread có thể **mounted** khi đang chạy bình thường, và có thể **pinned** do ràng buộc runtime khiến không thể unmount trong khi chờ. Chỉ thấy virtual thread có carrier không phải bằng chứng pinning. Vấn đề cần điều tra là **blocking trong lúc pinned**.

## 2. Những trường hợp pinning đặc trưng của JDK 21

Oracle JDK 21 mô tả hai nguồn chính:

1. Virtual thread đang thực thi **bên trong `synchronized` block/method** và gặp thao tác có thể làm nó block. Ví dụ: chờ network/DB, `Thread.sleep()`, `BlockingQueue.take()` hoặc hoạt động chờ phù hợp với cơ chế của VM.
2. Virtual thread đang chạy **native method** hoặc foreign function trong những ngữ cảnh VM không thể tách continuation khỏi carrier.

Điều cần ghi nhớ:

- **Chỉ sử dụng `synchronized` không tự động là sự cố**. Nếu critical section chỉ thao tác trong RAM trong vài microseconds, không có blocking đáng kể thì chi phí pinning có thể không đáng kể.
- **Pinning không nhất thiết đồng nghĩa lock contention**. Một virtual thread có thể **đã giữ lock thành công**, sau đó ngủ hoặc chờ I/O trong critical section. Chính thao tác chờ khi vẫn giữ monitor làm carrier bị giữ. Không cần có thread thứ hai tranh lock.
- **Chờ để vào monitor** và **giữ monitor rồi chờ I/O** là hai điểm khác nhau. Event `jdk.JavaMonitorEnter` nói về tranh chấp monitor; `jdk.VirtualThreadPinned` nói về virtual thread không thể rời carrier khi blocked. Đừng thay thế hai event cho nhau.
- **Native/foreign frame** còn giới hạn khả năng unmount. Không khẳng định đổi mọi `synchronized` sang `ReentrantLock` sẽ giải quyết pinning do thư viện native hoặc foreign calls.
- **Không tự suy pinning từ trạng thái WAITING**. Một virtual thread đang chờ nhưng đã unmount có thể là hành vi bình thường, giúp tiết kiệm OS threads.
- **Không suy ra mỗi lần block đều phát JFR pinned event**. Tùy event settings, threshold, phạm vi recording, thời điểm, JVM và cơ chế blocking.

### Bảng phân biệt nhanh

| Hiện tượng | Diễn giải chính xác hơn | Bằng chứng nên xem |
| --- | --- | --- |
| `synchronized` cập nhật counter ngắn, không chờ | Thường không phải mục tiêu tối ưu pinning đầu tiên. | Latency critical section, JFR pinned events, mức thường xuyên. |
| `synchronized` giữ lock rồi `Thread.sleep(300)` | Trong JDK 21 là ví dụ có thể giữ carrier trong lúc chờ. | `jdk.VirtualThreadPinned`, `-Djdk.tracePinnedThreads=...`. |
| `ReentrantLock.lock()` rồi `Thread.sleep(300)` | Lock API có cơ chế hỗ trợ virtual-thread park/unmount trên JDK 21; không có nghĩa đoạn code chạy song song khi lock bị tranh. | JFR, concurrency throughput, lock wait. |
| Một method native thực hiện blocking lâu | Có thể pinned do native frame; không giải quyết bằng đổi monitor ngoài. | JFR stack, native profiler/JNI/FFM callsite, thời lượng. |
| Nhiều virtual threads `WAITING` nhưng CPU/carriers vẫn hoạt động bình thường | Chờ có thể đang unmount hợp lệ. | Scheduler/concurrency, JFR, throughput và pending work. |
| Thread pool/DB pool ít connection nên requests chờ | Giới hạn bên ngoài scheduler có thể là nút thắt. | Connection acquire wait, queued requests, downstream latency. |
| Carrier bận CPU lâu | Có thể là CPU-bound code, không phải pinning. | CPU samples, profiling, JFR pinned event có thực sự xuất hiện không? |

## 3. Dấu hiệu nhận biết pinning gây vấn đề vận hành

Đừng chỉ tìm thấy một stack rồi tuyên bố nguyên nhân. Một chuỗi bằng chứng thuyết phục hơn là:

- Dịch vụ đang có **throughput thấp hơn dự kiến**, request queue tăng, p95/p99 latency tăng trong giờ cao điểm.
- Có nhiều event `jdk.VirtualThreadPinned` với **duration dài**, lặp lại ở **cùng method/callsite** trong cửa sổ sự cố.
- Stack trace cho thấy một blocking call nằm **bên trong monitor** hoặc qua native frame.
- Số platform carriers hữu dụng không đủ để phục vụ lượng virtual threads runnable trong thời điểm bất thường, hoặc các stack samples cho thấy carriers bị giữ trong những đoạn chờ.
- Sau khi thu nhỏ critical section/giảm blocking dưới monitor, **pinning events giảm** và throughput/p99 cải thiện dưới **cùng workload**.

Một vài event pinning 25–40 ms chỉ xảy ra khi khởi động chưa chắc đáng sửa. Mặt khác, event 200 ms lặp **hàng nghìn lần mỗi giây** có thể làm hỏng khả năng scale của virtual-thread-per-task architecture, ngay cả khi heap/GC không tăng rõ.

**Không có một ngưỡng số lượng pinning event áp dụng cho mọi hệ thống.** Cần xem event rate, duration, service level objectives (SLO), concurrency, số carriers và workload.

## 4. Quy tắc phiên bản: đừng dùng kiến thức JDK mới cho JDK 21

| Runtime | Hành vi cần chú ý | Công cụ và cách diễn giải |
| --- | --- | --- |
| **Java 17** | Không có virtual threads chính thức trong `java.lang.Thread` theo Java 21; ví dụ `Thread.ofVirtual()` không biên dịch trên JDK 17. | Bài thực hành này **không dành cho Java 17**. |
| **Java 21** | Virtual threads chính thức. Blocking trong `synchronized` hoặc native/foreign code có thể pin carrier. | JFR `jdk.VirtualThreadPinned` mặc định enabled ngưỡng **20 ms**; `jdk.tracePinnedThreads` hỗ trợ in stack. |
| **Java 22–23** | Phần lớn nguyên tắc pinning do `synchronized` giống JDK 21; xác minh trên bản đang chạy. | Không dùng kết quả chạy của JDK 24+ để kết luận cho bản này. |
| **Java 24 trở lên** | JEP 491 cho phép virtual threads đồng bộ `synchronized` mà không bị pin chỉ vì monitor theo cơ chế cũ; native/foreign và giới hạn khác vẫn có thể liên quan. | `jdk.VirtualThreadPinned`, trace property và fields có thể khác; dùng tài liệu đúng phiên bản. |

**Khẳng định quan trọng:** trong **JDK 21**, không có chuyện “mọi `synchronized` đều là anti-pattern”; khuyến nghị là tránh **blocking lâu/thường xuyên khi đang giữ monitor**. Khi có kế hoạch nâng JDK 24+, JEP 491 có thể thay đổi ưu tiên sửa nhưng vẫn cần kiểm chứng code và library native.

Đừng giả định API `VirtualThreadSchedulerMXBean` có sẵn trên Java 21 chỉ vì thấy trong tài liệu JDK mới: interface này được công bố ở **JDK 24**. Với JDK 21, ưu tiên JFR, `jcmd Thread.dump_to_file`, JVM metrics hiện có và trace property; không đưa ví dụ yêu cầu MXBean JDK 24 vào mã Java 21.

## 5. Bằng chứng ưu tiên: JFR `jdk.VirtualThreadPinned`

Java Flight Recorder (JFR) ghi event `jdk.VirtualThreadPinned` khi virtual thread đã blocked trong lúc pinned đủ lâu theo cấu hình event. Oracle JDK 21 nêu **mặc định enabled** với **threshold 20 ms** cho `jdk.VirtualThreadPinned`. Điều này có nghĩa:

- Một lần pinning/blocking **ngắn hơn threshold** có thể **không xuất hiện**.
- File không ghi đúng khoảng sự cố, event bị tắt hoặc ngưỡng bị tăng sẽ làm mất cơ hội quan sát.
- Duration cho biết **khoảng blocking while pinned** được ghi theo event; nó **không** phải tổng thời gian CPU, và không tự chứng minh service latency bằng duration đó.
- Stack trace chỉ ra chỗ runtime nhận diện pinned blocking; hãy truy về **application frame** và cấu trúc `synchronized`/native quanh đó.
- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` mặc định **không bật**; đừng kỳ vọng tìm đủ vòng đời mọi virtual thread trong recording mặc định.

### Tạo recording JFR trên Java 21 cho bài thực hành

Khi chạy chương trình độc lập (sẽ tạo ở phần 7), bật recording từ lúc khởi động:

```bash
java -XX:StartFlightRecording=filename=sync-pinning.jfr,settings=default,dumponexit=true \
  -Djdk.tracePinnedThreads=short \
  -Djdk.virtualThreadScheduler.parallelism=2 \
  VirtualThreadPinningLab sync
```

Lệnh dùng dấu `\` để xuống dòng trong Bash/Linux/macOS. Trên PowerShell hoặc CMD dùng một dòng tương đương, **không** copy dấu `\` cuối dòng làm cú pháp PowerShell. Tên tệp phải chưa có hoặc được xử lý theo chính sách ghi file của môi trường; ghi vào thư mục hiện tại có quyền. `dumponexit=true` yêu cầu dump file khi JVM thoát theo đường bình thường; không bảo đảm file hoàn chỉnh nếu tiến trình bị `SIGKILL`/`OOMKilled`.

Tệp `sync-pinning.jfr` chỉ có sau khi recording ghi xong. Dùng:

```bash
jfr summary sync-pinning.jfr
jfr print --events jdk.VirtualThreadPinned sync-pinning.jfr
```

Đầu tiên, `jfr summary` kiểm tra file, time window và số event. Sau đó, `jfr print` liệt kê từng `jdk.VirtualThreadPinned` có trong file, với timestamp/duration/stack fields theo bản JVM. Nếu tên event không xuất hiện hoặc count là 0, đừng suy ra “chắc chắn không có pinning”: xem thời điểm capture, JDK version, runtime mode, threshold và workload.

### JFR từ JVM đang chạy

Nếu service không khởi động bằng JFR, trong một cửa sổ ngắn có quyền attach và đã phê duyệt, có thể:

```bash
jcmd -l
jcmd <pid> help JFR.start

jcmd <pid> JFR.start \
  name=vthread_diag \
  settings=default \
  duration=60s \
  filename=/var/diag/vthread-60s.jfr
```

Thay `<pid>` và đường dẫn bằng giá trị thật. Thư mục phải tồn tại và JVM đích có quyền ghi. Trong container, file nằm ở filesystem/mount của JVM đích, không tự xuất hiện ở terminal operator. Nếu đang có recording JFR phù hợp, **ưu tiên kiểm tra `jcmd <pid> JFR.check` và dump recording đó** thay vì mở recording mới không cần thiết.

Đọc file bằng JFR command của **JDK 21** hoặc phiên bản tương thích. Với file lớn, chỉ lọc event cần thiết, tránh `jfr print` toàn bộ stdout hàng GiB.

## 6. Công cụ thứ hai: `-Djdk.tracePinnedThreads=full|short`

JDK 21 có system property đặc biệt để chẩn đoán pinning:

```bash
# In nhiều frame khi virtual thread bị blocked while pinned
java -Djdk.tracePinnedThreads=full YourMainClass

# Chỉ in những frame đáng chú ý
java -Djdk.tracePinnedThreads=short YourMainClass
```

Đây là ví dụ cú pháp với `YourMainClass` là tên class của chương trình chạy, **không phải tên class có sẵn trong bài**. Ví dụ có thể chạy hoàn chỉnh xuất hiện ở phần 7.

- `full` in stack trace chi tiết tới stderr, đánh dấu các frame native/khung giữ monitor.
- `short` rút gọn về các khung gây vấn đề, ít output hơn.
- Output trace có thể phụ thuộc số lần gặp stack, cơ chế gộp/lọc, JVM và lúc chạy; **không xem số dòng log là số event thực tế**.
- Với hệ thống rất nhiều pinning, trace đầy đủ có thể làm ngập log và tiêu thụ CPU/I/O. Chỉ bật trên staging hoặc một instance/cửa sổ có kiểm soát.
- Đây là **JDK system property**, không phải Java source API; đặt trước tên main class trong câu lệnh `java`. Không chỉ gõ `-Djdk.tracePinnedThreads` vào biến ứng dụng rồi giả định JDK nhận được.

Nên dùng **JFR làm bằng chứng có timestamp và duration**, sau đó dùng trace property để nhận dạng nhanh callsite khi tái hiện được trong điều kiện có kiểm soát. Hai nguồn có thể bổ sung nhau, không buộc phải cùng số lượng event.

## 7. Bài thực hành chạy được trên Java 21: mô phỏng và so sánh

Mục tiêu: tạo **nhiều virtual threads**, mỗi thread thực hiện `Thread.sleep(250)` bên trong **monitor riêng** (chế độ `sync`) hoặc bên trong **ReentrantLock riêng** (chế độ `lock`). Dùng monitor/lock riêng để **tránh cố tình serial hóa tất cả task trên cùng một mutex**; nhờ vậy khác biệt chủ yếu là carrier có thể được giải phóng trong lúc chờ hay không.

**Lưu ý về JVM optimizer:** nếu một object lock chỉ tồn tại cục bộ và không escape, compiler có thể loại bỏ monitor không quan sát được. Ví dụ này lưu monitor trong mảng `static` để tránh một demo bị khóa tối ưu mất; đây là một lý do phải đo event thật thay vì chỉ nhìn source có `synchronized`.

Tạo file `VirtualThreadPinningLab.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class VirtualThreadPinningLab {
    private static final int TASK_COUNT = 12;
    private static final Object[] MONITORS = new Object[TASK_COUNT];
    private static final ReentrantLock[] LOCKS =
            new ReentrantLock[TASK_COUNT];

    static {
        for (int i = 0; i < TASK_COUNT; i++) {
            MONITORS[i] = new Object();
            LOCKS[i] = new ReentrantLock();
        }
    }

    private static void perform(int id, String mode)
            throws InterruptedException {
        if ("sync".equals(mode)) {
            synchronized (MONITORS[id]) {
                Thread.sleep(250);
            }
        } else {
            ReentrantLock lock = LOCKS[id];
            lock.lock();
            try {
                Thread.sleep(250);
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"sync".equals(args[0]) && !"lock".equals(args[0]))) {
            System.err.println("Usage: java VirtualThreadPinningLab sync|lock");
            System.exit(2);
        }

        String mode = args[0];
        AtomicInteger completed = new AtomicInteger();
        List<Future<Void>> futures = new ArrayList<>();

        long start = System.nanoTime();
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < TASK_COUNT; i++) {
                final int id = i;
                Callable<Void> job = () -> {
                    perform(id, mode);
                    completed.incrementAndGet();
                    return null;
                };
                futures.add(executor.submit(job));
            }

            for (Future<Void> f : futures) {
                f.get();
            }
        }
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        System.out.println("mode=" + mode +
                " completed=" + completed.get());
        System.out.println("elapsedMs=" + elapsedMs);
    }
}
```

Biên dịch bằng **JDK 21**; không cần `--enable-preview`:

```bash
java -version
javac -version
javac VirtualThreadPinningLab.java
```

Chạy hai lượt **riêng biệt** trên cùng máy/JDK, giữ scheduler parallelism cố định để dễ quan sát:

```bash
# Trường hợp 1: chờ trong synchronized trên JDK 21
java -Djdk.virtualThreadScheduler.parallelism=2 \
  -Djdk.tracePinnedThreads=short \
  -XX:StartFlightRecording=filename=sync-pinning.jfr,settings=default,dumponexit=true \
  VirtualThreadPinningLab sync

# Trường hợp 2: chờ trong ReentrantLock
java -Djdk.virtualThreadScheduler.parallelism=2 \
  -XX:StartFlightRecording=filename=lock-pinning.jfr,settings=default,dumponexit=true \
  VirtualThreadPinningLab lock
```

**Stdout phần xác định** nếu cả hai lượt chạy thành công, không tính dòng JFR/JVM agent và stack trace stderr:

```text
mode=sync completed=12
elapsedMs=<giá trị đo thực tế>
```

```text
mode=lock completed=12
elapsedMs=<giá trị đo thực tế>
```

`<giá trị đo thực tế>` là **ký hiệu mô tả giá trị động**, không phải literal stdout. Lệnh thực sẽ in số nguyên không âm (ms) phụ thuộc máy, JIT, GC, lịch scheduler và tải. Không khẳng định thời gian `sync` luôn bằng 1.500 ms hay `lock` luôn bằng 250 ms. Hai lượt có tổng **12 task thành công** theo logic chương trình; chế độ `sync` trên JDK 21 có thể làm nhiều carriers bị giữ khi ngủ, trong khi `ReentrantLock` thường cho phép unmount lúc `Thread.sleep`.

Đọc lại hai file:

```bash
jfr summary sync-pinning.jfr
jfr print --events jdk.VirtualThreadPinned sync-pinning.jfr

jfr summary lock-pinning.jfr
jfr print --events jdk.VirtualThreadPinned lock-pinning.jfr
```

**Kết quả kỳ vọng ở mức định tính trên HotSpot JDK 21:** recording `sync` có thể có các `jdk.VirtualThreadPinned` với stack nằm trong `perform(...)` và `Thread.sleep(...)`, trong khi recording `lock` thường có ít hoặc không có event cùng nguyên nhân. Số event, duration và elapsed time không cố định. Khi không thấy event, xem `jfr summary`, cấu hình JFR, đúng JDK 21, source chạy thực và sự kiện có vượt 20 ms hay không.

### Tại sao mỗi task dùng một monitor riêng?

Nếu cả 12 task cùng sử dụng một monitor, chúng bị **serialized vì mutual exclusion** ngay cả trước khi xét pinning. Đổi sang **cùng một ReentrantLock** vẫn serialized, không thể tự làm mọi task sleep song song khi lock còn bị giữ. Demo dùng lock/monitor riêng để tách **carrier pinning** khỏi **contended lock**; trong ứng dụng thật, nếu dữ liệu thật sự phải được bảo vệ bởi một mutex, không thể bỏ tính loại trừ chỉ để lấy throughput.

## 8. Java 21: đọc số event pinned từ file bằng API thay vì đếm log

Để so hai recording một cách có số liệu, có thể duyệt `jdk.VirtualThreadPinned` trong file bằng `jdk.jfr.consumer.RecordingFile`. Ví dụ không load toàn bộ file vào `List` và không giả định event duration là CPU time.

Tạo `PinnedEventSummary.java`:

```java
import java.nio.file.Path;
import java.util.Locale;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class PinnedEventSummary {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java PinnedEventSummary file.jfr");
            System.exit(2);
        }

        long count = 0;
        long totalNanos = 0;
        long maxNanos = 0;

        try (RecordingFile file =
                     new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"jdk.VirtualThreadPinned".equals(
                        event.getEventType().getName())) {
                    continue;
                }

                long duration = event.getDuration().toNanos();
                count++;
                totalNanos += duration;
                maxNanos = Math.max(maxNanos, duration);
            }
        }

        System.out.printf(Locale.ROOT,
                "pinnedEvents=%d sumPinnedMs=%.2f maxPinnedMs=%.2f%n",
                count, totalNanos / 1_000_000.0,
                maxNanos / 1_000_000.0);
    }
}
```

Biên dịch và chạy:

```bash
javac PinnedEventSummary.java
java PinnedEventSummary sync-pinning.jfr
java PinnedEventSummary lock-pinning.jfr
```

Một dòng kết quả có dạng `pinnedEvents=8 sumPinnedMs=2012.34 maxPinnedMs=257.89` nhưng **đây chỉ là minh họa**, không phải kết quả được xác minh cho máy cụ thể. `sumPinnedMs` là **tổng duration của các event**, và **có thể lớn hơn wall-clock elapsed** do nhiều virtual threads pinned đồng thời. Nó **không phải CPU time hay số milliseconds JVM bị đóng băng hoàn toàn**. `maxPinnedMs` cho biết event dài nhất trong file, không phải p99 latency của request.

Số event có thể không đếm hết những pinning ngắn hơn JFR threshold hoặc những hoạt động nằm ngoài recording time window. Khi báo cáo, nêu file, cấu hình, count, sum, max, loại ứng dụng và số request/task tương ứng — không so hai workload khác nhau rồi suy ra cải thiện.

## 9. Cách đọc stack trace: tìm chỗ giữ monitor quanh blocking call

Giả sử JFR hoặc trace stderr có stack chỉ ra `VirtualThreadPinningLab.perform`, `Thread.sleep` và vị trí `synchronized`. Cách phân tích:

1. Xác nhận **đây là virtual thread** và event type thật sự `jdk.VirtualThreadPinned`, không chỉ một CPU sample hoặc `jdk.ThreadPark`.
2. Ghi **timestamp, duration, tên virtual thread, callsite** được công cụ hiển thị; event fields chi tiết có thể khác giữa JDK versions.
3. Mở đúng source/JAR version; tìm **critical section** chứa thao tác chờ. Một trace chỉ thấy method có `synchronized` không đủ: cần biết method đã gọi gì khi giữ lock.
4. Tách **blocking I/O** khỏi **in-memory protected state**: có thể thu hẹp monitor mà vẫn giữ bất biến dữ liệu không?
5. Nếu stack vào JNI/native/FFM, xác minh thư viện và phiên bản; đừng tự quy mọi pinning cho `synchronized` của application code.
6. Nhìn phân bố **count/duration/cửa sổ tải**. Một trace hiếm khi khởi động không đồng nghĩa thủ phạm của p99.
7. Sau thay đổi, so cả **event pinning** và **throughput/latency/error rate** trên cùng workload.

### Những cấu trúc cần tìm trong code

```java
// Rủi ro trong JDK 21: giữ monitor rồi gọi I/O/đợi lâu
synchronized (sessionLock) {
    response = remoteClient.fetch();  // có thể block mạng
    cache.put(key, response);
}
```

Đây là **đoạn minh họa**, không phải file chạy độc lập. Nếu `remoteClient.fetch()` thực sự chờ network lâu, virtual thread có thể pinned trong lúc gọi bên trong `synchronized`.

Một hướng thay đổi khi semantics cho phép:

```java
// Không giữ monitor trong lúc I/O.
Response response = remoteClient.fetch();

synchronized (sessionLock) {
    cache.put(key, response);
}
```

**Không tự áp dụng máy móc.** Việc chuyển fetch ra ngoài monitor có thể phá vỡ tính atomic của check–then–act, tạo duplicate requests, đọc stale state hoặc làm concurrent update sai. Với state shared, cần xác định bất biến nghiệp vụ, versioning/compare-and-set, re-check trong lock hoặc thiết kế synchronization phù hợp rồi kiểm thử.

### Thay `synchronized` bằng `ReentrantLock` khi cần giữ lock qua blocking

Nếu workflow thật sự cần mutual exclusion xuyên suốt một blocking operation, Java 21 cho phép sử dụng `java.util.concurrent.locks.ReentrantLock`:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

void updateSession() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(200);  // minh họa một đoạn blocking
        updateStateSafely();
    } finally {
        lock.unlock();
    }
}
```

Đây là **fragment trong một class**, có `updateStateSafely()` là tên method nghiệp vụ minh họa, **không phải chương trình tự biên dịch**. `ReentrantLock` tương thích hơn với cách virtual threads park/unmount khi chờ trong JDK 21; nhưng **nếu nhiều tác vụ tranh cùng lock**, chúng vẫn phải chờ nhau. Giữ lock qua I/O dài làm tăng lock hold time; thay API lock không xóa tính nối đuôi do thiết kế concurrency.

Trước khi refactor, xem `wait()/notify()/notifyAll()`, reentrancy, exception paths, interrupt handling và lock ordering. Không được đổi `synchronized` sang `ReentrantLock` mà để lại code dựa vào intrinsic monitor semantics một cách không tương thích.

## 10. Thread dump trên JDK 21 hỗ trợ điều tra như thế nào?

JDK 21 có `jcmd Thread.dump_to_file` để xuất thread dump chứa **platform threads và virtual threads**, giúp quan sát nhiều stack tại một thời điểm. Đây là công cụ **bổ sung** cho JFR: thread dump không tự cho biết mọi lần pinning đã xảy ra trước snapshot.

```bash
# Tìm PID đúng JVM
jcmd -l

# Kiểm tra lệnh và options trên JVM đang chạy
jcmd <pid> help Thread.dump_to_file

# Một ảnh chụp tại thời điểm nghi ngờ, JSON để phân tích tự động
jcmd <pid> Thread.dump_to_file -format=json /var/diag/vthreads.json
```

Đường dẫn file nằm trong filesystem của **JVM đích**, phải có quyền ghi và dung lượng. Theo tài liệu Java 21, dump virtual threads có thể thể hiện cấu trúc thread/task nhưng **không bao gồm mọi object addresses, lock/JNI/heap statistics** giống kiểu traditional dump. Vì vậy, không dùng JSON dump làm “bằng chứng chính xác có bao nhiêu carrier bị pinned trong cả phút”; vẫn cần JFR events và metrics tương ứng.

Trên ứng dụng tạo lượng lớn virtual threads, thread dump có thể có kích thước rất lớn và chi phí đáng kể. Đừng chạy liên tục trên production chỉ vì lệnh tạo JSON. Nếu dùng `jcmd <pid> Thread.print -l`, đây là loại traditional thread dump có khác biệt phạm vi và không thay thế đúng chức năng `Thread.dump_to_file` cho virtual threads trên JDK 21.

### Khi nào nên dùng dump?

- JFR cho một callsite nghi vấn nhưng chưa rõ **stack ở thời điểm tải cao**.
- Nhiều request treo, cần xem **nhiều virtual threads** đang chờ gì.
- Scheduler queue/concurrency có biểu hiện bất thường và muốn quan sát ứng dụng ở một mốc.

Nếu chỉ cần phân bố pinning duration/callsite trong 60 giây, **JFR recording** thường phù hợp hơn một dump duy nhất vì nó có **nhiều event gắn timestamp**.

## 11. Phân biệt pinning với saturation và các nút thắt khác

Không phải cứ dùng virtual threads rồi thấy p99 cao là pinning. Đặt ba nhóm metric cạnh nhau:

| Nhóm | Cần kiểm tra | Ý nghĩa |
| --- | --- | --- |
| **Pinning trực tiếp** | `jdk.VirtualThreadPinned` count/duration/top stack, trace property. | Có bằng chứng carrier bị giữ vì blocked while pinned không? |
| **Throughput/latency** | Requests/s, p50/p95/p99, error/timeout, queue wait và completion rate. | Pinning có thực sự ảnh hưởng kết quả người dùng không? |
| **Capacity khác** | CPU usage, DB pool pending/active, HTTP connection limits, socket waits, locks, GC pauses, downstream SLA. | Có nguyên nhân khác làm mọi virtual threads chờ không? |

Ví dụ với một service gọi DB: có thể 50.000 virtual threads, DB pool chỉ cho 50 connections. Nếu nhiều task chờ lấy connection nhưng **unmount được**, carrier không nhất thiết bị pinned; throughput vẫn bị giới hạn bởi DB. Giảm pinning event về 0 không tự làm DB phục vụ 5.000 queries đồng thời. Ngược lại, nếu network call bị gọi **trong synchronized** trên JDK 21 và pin carrier, thêm virtual threads có thể không tăng concurrency hiệu quả.

**Carrier count không phải số virtual threads.** Một scheduler có vài platform threads vẫn có thể phục vụ rất nhiều virtual threads đang chờ, nhờ unmount. Không được dùng `Thread.activeCount()` hoặc số OS threads như số virtual requests đang xử lý. Mốc hiệu năng phải gắn với business operation, scheduler load và pinning events.

### Tham số scheduler có phải “cách sửa”?

JDK 21 có implementation-specific properties như `jdk.virtualThreadScheduler.parallelism` ảnh hưởng mức parallelism mục tiêu của scheduler; trong lab ta đặt `2` để dễ thấy biến động. Điều này **không phải khuyến nghị đặt `2` trên production**. Tăng scheduler parallelism có thể thay đổi triệu chứng, nhưng không sửa đoạn blocking-in-monitor và có thể tăng số OS threads, memory/CPU scheduling cost. **Đừng tuning scheduler trước khi xác nhận nguyên nhân.**

Nếu đang dùng pool các virtual threads tự tạo theo mô hình “cache virtual threads” hoặc cố reuse chúng như platform thread pool, xem lại thiết kế. Virtual thread thường được dùng **mỗi task một virtual thread**; giới hạn concurrency với một downstream nên dùng `Semaphore` hoặc policy phù hợp, không phải cố biến virtual threads thành tài nguyên khan hiếm như OS threads.

## 12. Thực hành phân tích một incident giả định

**Tình huống:** sau khi chuyển request handlers sang `Executors.newVirtualThreadPerTaskExecutor()` trên JDK 21, throughput không tăng tương ứng và p99 tăng trong giờ cao điểm.

### Thu thập tối thiểu

1. Kiểm tra phiên bản `java -version` tại **process đang chạy**, không chỉ SDK trên máy phát triển; xác nhận Java 21, runtime vendor và image.
2. Lấy request rate, p95/p99, errors, CPU, active DB connections, queue wait và GC time trong cửa sổ sự cố.
3. Kiểm tra recording đang có (`jcmd <pid> JFR.check`). Nếu chưa có, cân nhắc JFR `default` ngắn; bảo đảm file/disk/quyền.
4. `jfr summary file.jfr` rồi `jfr print --events jdk.VirtualThreadPinned file.jfr`.
5. Nhóm event theo **stack/callsite**, đếm số event và thống kê duration; ghi thời gian và sample counts.
6. Nếu đã tái hiện trên staging, chạy `-Djdk.tracePinnedThreads=short` và xem những frame giữ monitor/native.
7. Chụp virtual-thread dump chỉ khi cần một snapshot live của các stack mà JFR chưa đủ thông tin.
8. Đối chiếu với các giới hạn khác (DB pool/CPU/IO) và thử thay đổi tối thiểu trên cùng load.

### Mẫu bảng dữ liệu để đọc

Những con số dưới đây là **giả định**, không phải output JFR thực:

| Khoảng 1 phút | Request/s | p99 response | `VirtualThreadPinned` events | p95 pinned duration | DB pool pending |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trước refactor | 500 | 820 ms | 2.800 | 240 ms | 0 |
| Sau thu nhỏ critical section | 730 | 310 ms | 35 | 25 ms | 0 |

Nếu cùng workload/hardware và không có thay đổi lớn khác, đây là tín hiệu mạnh rằng việc sửa blocking-under-monitor đã giảm carrier pinning và cải thiện throughput/tail latency. Nhưng không chứng minh quan hệ nhân quả tuyệt đối chỉ từ hai dòng bảng; cần kiểm tra CPU, GC, deployment, request mix, error/rejection và lặp thử nghiệm.

Nếu thay vào đó `p99` gần như không đổi dù pinned events giảm, điều tra tiếp **DB/network bottleneck, serialization, queue wait, lock contention hoặc CPU**. Mục tiêu là cải thiện service, không chỉ làm đẹp số event.

### Lưu các bằng chứng cần thiết

Một báo cáo có thể ghi:

```text
Runtime: OpenJDK 21.x, one JVM / one pod
Window: 14:00-14:01 UTC (example)
JFR settings: default; pinned threshold = 20 ms
Pinned events: count, durations, top application callsites
JVM flags: scheduler parallelism, relevant startup flags
Traffic: request rate, p95/p99 latency, errors, queue depth
Hypothesis: blocking I/O inside synchronized method retains carriers
Fix/test: shorten monitor scope or use ReentrantLock where safe
Validation: same workload, JFR recording and latency comparison
Limitations: JFR threshold; unrecorded short events; version-specific behavior
```

Không gửi toàn bộ HPROF/JFR/stack trace chứa dữ liệu khách hàng vào ticket công khai. Ghi lại checksum, storage owner, retention và các quyền truy cập khi quy trình yêu cầu.

## 13. Những lỗi suy luận hay gặp

- **“Virtual thread bị WAITING là pinned.”** Sai: có thể nó đã unmount và carrier đang phục vụ thread khác.
- **“Cứ dùng `synchronized` là phải thay.”** Sai: chỉ cần ưu tiên **blocking dài và thường xuyên khi đang giữ monitor** trên Java 21.
- **“Pinning gây deadlock.”** Pinning không mặc nhiên là deadlock; nó có thể làm giảm concurrency, còn deadlock là chu kỳ phụ thuộc lock riêng.
- **“Không có lock contention thì không có pinning.”** Sai: một thread duy nhất có thể giữ monitor rồi block trong critical section.
- **“`Thread.sleep()` lúc nào cũng pin.”** Sai: ngoài bối cảnh pinned, virtual thread có thể unmount; cần xem frame và runtime.
- **“`jdk.VirtualThreadPinned` đếm mọi lần pinning.”** Sai: event threshold mặc định 20 ms, cài đặt và capture window quyết định những gì được ghi.
- **“JFR pinned event duration chính là CPU time.”** Sai: đó là thời gian blocking while pinned được ghi theo event.
- **“Tổng pinned duration 8 giây nghĩa application dừng 8 giây.”** Sai: các event có thể chồng thời gian trên nhiều carriers.
- **“Dùng `ReentrantLock` là mọi tác vụ chạy cùng lúc.”** Sai: mutual exclusion vẫn chặn các task tranh cùng lock.
- **“Đổi mọi synchronized sang ReentrantLock chắc chắn giữ nguyên semantics.”** Sai: `Object.wait/notify`, lock ordering, exception, reentrancy và interrupt policy cần xem lại.
- **“Tăng số virtual threads sẽ giải quyết carrier pinning.”** Sai: không thêm được carrier đang rảnh nếu chúng bị giữ bởi long-lived blocking sections.
- **“Tăng scheduler parallelism là nguyên nhân đã được sửa.”** Sai: có thể che triệu chứng và tăng OS thread overhead.
- **“`Thread.dump_to_file` có đủ thông tin như HPROF hoặc dump lock truyền thống.”** Sai: virtual-thread dump có phạm vi riêng và là một snapshot.
- **“Một trace stderr bằng một JFR event duy nhất.”** Sai: in trace có thể được giới hạn/gộp; dùng JFR theo thời gian để định lượng.
- **“Dùng JDK 24 chạy lại demo mà không thấy pinning thì báo Java 21 không có lỗi.”** Sai: JEP 491 thay đổi hành vi `synchronized` từ JDK 24.
- **“JDK 21 có sẵn mọi MXBean virtual-thread scheduler thấy trên JDK 26.”** Sai: kiểm tra `Since` của API, đặc biệt `VirtualThreadSchedulerMXBean` từ JDK 24.
- **“Chỉ có event pinning là đủ để kết luận SLA bị ảnh hưởng.”** Chưa đủ: phải đối chiếu request latency, throughput và bottleneck khác.

## 14. Checklist vận hành theo Java 21

**Xác minh:**

- [ ] Đúng **JDK 21** trên JVM đang chạy; `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` được dùng thật.
- [ ] Biết workload I/O-bound hay CPU-bound, request rate, downstream concurrency và SLO.
- [ ] Bản ghi JFR có đúng cửa sổ sự cố, event `jdk.VirtualThreadPinned` có enabled/threshold phù hợp.
- [ ] Không dùng biểu đồ số platform threads làm số virtual threads.

**Thu bằng chứng:**

- [ ] Bắt đầu với metrics/log/JFR recording sẵn có; hạn chế tác động production.
- [ ] `jfr summary` rồi `jfr print --events jdk.VirtualThreadPinned`, ghi timestamp/duration/stack.
- [ ] Nếu cần tái hiện, bật `-Djdk.tracePinnedThreads=short` hoặc `full` trên staging có kiểm soát.
- [ ] Dùng `Thread.dump_to_file` khi cần snapshot thread, hiểu giới hạn và overhead.
- [ ] Không hạ JFR threshold về 0 trên mọi instance trước khi đánh giá event rate, disk và overhead.

**Phân tích và sửa:**

- [ ] Chỉ ra callsite thực sự **blocked while pinned**, phân biệt monitor, native/foreign và DB pool limit.
- [ ] Ưu tiên tách I/O chờ lâu ra ngoài `synchronized` nếu không vi phạm invariant; nếu phải giữ lock, cân nhắc `ReentrantLock` và kiểm thử semantics.
- [ ] Không thay đổi toàn bộ synchronization strategy hay scheduler flags một cách máy móc.
- [ ] Đánh giá trước/sau cùng JDK 21, cùng workload/hardware, cùng JFR settings.
- [ ] Xem **throughput, p99, errors, lock waits, DB pending và pinning event metrics** cùng nhau.
- [ ] Nếu nâng JDK 24+, đọc lại JEP 491 và đo lại; không mang kết luận version-specific đi nguyên xi.

**Kết luận:** Trong **Java 21**, vấn đề pinning cần điều tra là **blocking khi virtual thread không thể unmount khỏi carrier**. Hãy dùng `jdk.VirtualThreadPinned` (mặc định ngưỡng **20 ms**) để đo thời điểm/độ dài/callsite, kết hợp `-Djdk.tracePinnedThreads` để tái hiện stack và dữ liệu throughput/latency để xác định mức ảnh hưởng. Sửa **đoạn giữ monitor trong lúc chờ** hoặc thay mô hình đồng bộ thích hợp mà vẫn giữ đúng invariants; không thay hàng loạt `synchronized` chỉ vì chúng tồn tại. Cuối cùng, kiểm tra **đúng phiên bản JDK** vì JDK 24 đã đổi đáng kể cách `synchronized` tương tác với virtual threads.

### Tài liệu tham khảo chính thức

- [Oracle JDK 21 — Virtual Threads: Scheduling, Pinning, JFR và thread dump](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads (final trong JDK 21)](https://openjdk.org/jeps/444)
- [Oracle JDK 21 — `jcmd` diagnostic commands, `JFR.start` và `Thread.dump_to_file`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary` và `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning, JDK 24](https://openjdk.org/jeps/491)
- [Oracle JDK 21 — `Executors.newVirtualThreadPerTaskExecutor()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newVirtualThreadPerTaskExecutor())
- [Oracle JDK 21 — RecordingFile JFR consumer API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)