# Nhận diện luồng ảo bị ghim và đo hành vi trên JDK 21

## 1. Vấn đề cần giải quyết

**Virtual thread** (luồng ảo) là một `java.lang.Thread` được JVM quản lý, có thể thực thi tác vụ Java đồng thời với nhiều virtual threads khác trên một số lượng nhỏ hơn các **platform threads**. Khi virtual thread thực hiện thao tác blocking được JVM hỗ trợ (như chờ socket hoặc `Thread.sleep`), nó thường có thể **unmount** khỏi platform thread đang chạy nó, trả platform thread này về cho scheduler xử lý công việc khác.

Trên **JDK 21**, trong một số hoàn cảnh, virtual thread **không unmount được khi blocking**. Nó giữ chặt platform thread thực thi mình, gọi là **carrier**, trong suốt khoảng chờ. Trạng thái này gọi là **pinning**.

Điểm cần nhớ:

- Pinning **không tự là lỗi correctness** hay deadlock.
- Pinning **có thể làm giảm khả năng mở rộng** nếu thời gian bị ghim dài và xảy ra thường xuyên khi ứng dụng chịu tải đồng thời lớn.
- Không phải mọi thao tác blocking của virtual thread đều pin carrier.
- Không phải mọi khối `synchronized` đều gây vấn đề: chỉ khi công việc chờ dài/tần suất cao xảy ra trong tình huống pinning, tài nguyên carrier mới bị giữ lâu.
- **JDK 21 khác JDK 24+:** JEP 491 trong JDK 24 thay đổi cách xử lý monitor; nhận định “blocking trong `synchronized` gây pinning” là mô hình cần học trên JDK 21, không phải luật bất biến cho mọi phiên bản Java về sau.

Mục tiêu của bài là **nhận diện đúng pinning trên JDK 21, đo tác động thay vì phỏng đoán, sửa có chọn lọc và đánh giá trong Spring Boot**. Hướng dẫn bao gồm một chương trình Java 21 biên dịch được bằng `javac`, một microbenchmark có đối chứng và ví dụ Spring Boot 3.5.x dùng virtual threads.

## 2. Virtual thread, carrier, mount và unmount

Một virtual thread không đồng nghĩa với một OS thread. JVM scheduling thường vận hành như sau:

~~~mermaid
flowchart TD
    A["Nhiều virtual threads cần chạy"] --> B["Virtual-thread scheduler"]
    B --> C["Carrier / platform threads"]
    C --> D["Virtual thread được mount, chạy mã Java"]
    D --> E{"Có thao tác cần chờ?"}
    E -->|"Không"| D
    E -->|"Blocking hỗ trợ unmount"| F["Unmount virtual thread"]
    F --> G["Carrier rảnh để chạy virtual thread khác"]
    E -->|"Blocking khi bị pinned trên JDK 21"| H["Carrier bị giữ trong lúc chờ"]
    H --> I["Ít carrier rảnh hơn để xử lý công việc khác"]
~~~

**Mount:** virtual thread đang được thực thi trên một carrier. **Unmount:** trạng thái tiếp tục thực thi của virtual thread được cất giữ để carrier có thể chạy virtual thread khác trong lúc công việc đang chờ. Khi sự kiện chờ hoàn tất, JVM có thể lên lịch mount trở lại; không có cam kết virtual thread luôn quay lại cùng một carrier.

### Tại sao pinning ảnh hưởng throughput?

Giả sử có rất nhiều request độc lập, mỗi request chờ I/O 200 ms. Khi virtual threads chờ theo cách unmount được, một số carrier có thể hỗ trợ rất nhiều request đang chờ song song. Nếu mỗi request **giữ** carrier trong 200 ms, concurrency hữu dụng có thể bị giới hạn nhiều hơn bởi số carrier.

Đây là **mô hình lý thuyết**, không phải một con số throughput được bảo đảm. Một ứng dụng thật còn chịu hạn chế từ CPU, connection pools, database, cổng mạng, synchronized contention, GC, heap, logging và các service bên ngoài. Virtual threads được thiết kế để giúp mở rộng concurrency cho workload nhiều I/O, **không làm CPU-bound code chạy nhanh hơn**.

### Tính daemon và vòng đời JVM

Virtual threads trong Java 21 là **daemon threads**. Nếu chỉ còn virtual threads/daemon threads mà không còn non-daemon platform threads, JVM có thể kết thúc. Trong chương trình Java độc lập, các ví dụ sẽ dùng `Thread.join()` hoặc `Future.get()` từ `main` để bảo đảm công việc kết thúc trước khi JVM thoát. Với Spring Boot dựa vào virtual threads cho scheduler/tác vụ nền, có thể cần `spring.main.keep-alive=true` để giữ process chạy; đó là vấn đề **lifecycle**, khác pinning.

## 3. Trường hợp pinning trên JDK 21

Tài liệu Oracle JDK 21 nêu hai trường hợp nền tảng:

1. Virtual thread đang chạy code bên trong một **`synchronized` method hoặc block**.
2. Virtual thread đang thực thi **native method** hoặc foreign function theo cơ chế có thể ghim carrier.

Điểm gây tác động hiệu năng thường là **một thao tác blocking xảy ra trong những vùng đó**. Không nên kết luận chỉ vì nhìn thấy `synchronized` trong stack trace thì toàn bộ ứng dụng có vấn đề.

### Trường hợp A: blocking bên trong Java monitor

~~~java
private final Object monitor = new Object();

public void load() throws InterruptedException {
    synchronized (monitor) {
        // JDK 21: nếu virtual thread chờ ở đây,
        // carrier có thể bị giữ cho đến khi hết chờ.
        Thread.sleep(200);
    }
}
~~~

Đây là **snippet trong một class**, không phải file Java độc lập. `Thread.sleep(200)` mô phỏng một thao tác chờ; trong ứng dụng thật nó có thể tương ứng với blocking network I/O, chờ dữ liệu hoặc một tác vụ thư viện. Khi virtual thread đi ngủ bên trong monitor trên JDK 21, JFR có thể ghi một `jdk.VirtualThreadPinned` event nếu khoảng bị ghim vượt ngưỡng cấu hình.

**Không nên xem `Thread.sleep` là nguyên nhân duy nhất.** Cơ chế pinning liên quan đến **monitor + thao tác chờ**. Chuyển một lời gọi chờ ra ngoài monitor hoặc dùng cơ chế khóa phù hợp có thể cho phép virtual thread unmount.

### Trường hợp B: native/foreign call

Một số thao tác JNI/native và foreign-function invocation có thể giữ virtual thread gắn với carrier. Chuyển mọi `synchronized` sang `ReentrantLock` **không sửa** một đoạn native code đang pin carrier. Nếu JFR chỉ ra stack có native frame, cần phân tích thư viện, driver, API I/O và phiên bản JDK. Có thể cân nhắc dùng platform-thread executor cho đoạn native blocking đặc biệt, giới hạn concurrency hoặc thay phiên bản thư viện.

### Những điều không đồng nghĩa với pinning

| Hiện tượng | Có chắc pin carrier không? | Giải thích |
| --- | --- | --- |
| Virtual thread gọi `Thread.sleep` ngoài monitor trên JDK 21 | Không | Thường là blocking hỗ trợ unmount |
| Virtual thread chờ socket I/O hỗ trợ virtual threads ngoài monitor | Không | JVM thường unmount khi chờ |
| `synchronized` chỉ bảo vệ phép gán trong bộ nhớ rất ngắn | Không thể kết luận có vấn đề | Không có blocking dài; monitor ngắn không nhất thiết gây suy giảm |
| Virtual thread chờ giành `ReentrantLock` | Không theo cùng cơ chế monitor pinning | Lock trong `java.util.concurrent.locks` hỗ trợ cơ chế đợi phù hợp hơn |
| Nhiều virtual threads đang WAITING | Không | WAITING là trạng thái; không tự cho biết carrier đang bị giữ |
| Thread pool/DB connection pool hết slot | Không | Có thể là nghẽn downstream, phải phân biệt bằng metrics |
| Mọi request latency cao | Không | Latency có nhiều nguyên nhân; cần JFR và profiler |
| `jdk.VirtualThreadPinned` xuất hiện một lần | Có một lần bị ghi nhận | Chưa đủ để khẳng định tác động throughput/SLO |
| Không thấy `jdk.VirtualThreadPinned` | Không chứng minh “không bao giờ pin” | Có ngưỡng duration, sampling/recording window và workload |

## 4. JDK 21 cung cấp công cụ quan sát pinning nào?

Ba cách thường dùng để phân tích:

| Công cụ | Mục đích | Khi nào dùng |
| --- | --- | --- |
| `-Djdk.tracePinnedThreads=full` hoặc `short` | In stack trace khi virtual thread blocking trong tình trạng pinned | Debug nhanh trên JDK 21–23 |
| Java Flight Recorder, event `jdk.VirtualThreadPinned` | Ghi sự kiện pinning kéo dài vượt threshold | Đo dưới workload thực, tổng hợp stack và duration |
| `jcmd PID Thread.dump_to_file -format=json ...` | Dump danh sách và stack virtual/platform threads | Xem ai đang chờ và ở đường gọi nào trong một thời điểm |

Các công cụ có độ bao phủ khác nhau: **trace giúp nhận diện điểm code**, **JFR giúp ghi nhận sự kiện và duration**, **thread dump giúp thấy trạng thái thread**, còn **load test** mới cho biết tác động end-to-end.

### 4.1. jdk.tracePinnedThreads

Trên **JDK 21**, đặt JVM property **trước** tên main class hoặc `-jar`:

~~~bash
java -Djdk.tracePinnedThreads=full VirtualThreadPinningLab monitor
~~~

Hoặc rút gọn:

~~~bash
java -Djdk.tracePinnedThreads=short VirtualThreadPinningLab monitor
~~~

`full` in stack trace chi tiết, có đánh dấu các frame liên quan native/monitor; `short` giảm lượng thông tin. Kết quả được JVM in ra tùy trường hợp, thường qua stderr, **không có định dạng stdout cố định** để viết test snapshot cứng.

**Hạn chế:** một stack trace cho biết vị trí nghi vấn, không tự chỉ ra người giữ monitor, business impact hay percentiles. Ngoài ra property này là công cụ đặc trưng của JDK 21–23; không giả định nó còn hiệu lực trên JDK 24+ khi cơ chế pinning và chẩn đoán đã thay đổi.

### 4.2. JFR: jdk.VirtualThreadPinned

Trong Oracle JDK 21, JFR có những event:

- `jdk.VirtualThreadPinned` — virtual thread bị pin và carrier không được giải phóng lâu hơn ngưỡng. Theo tài liệu Oracle JDK 21, event này được bật mặc định với **threshold 20 ms**.
- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` — bắt đầu/kết thúc virtual thread, **thường tắt mặc định** vì số event có thể rất lớn.
- `jdk.VirtualThreadSubmitFailed` — báo tình huống start/unpark thất bại, thường do vấn đề tài nguyên; không phải chỉ số pinning.

Ví dụ khởi chạy một recording cho chương trình nhỏ:

~~~bash
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab monitor
~~~

Sau khi process kết thúc và file `monitor.jfr` được tạo:

~~~bash
jfr print --events jdk.VirtualThreadPinned monitor.jfr
~~~

Nếu muốn xem cả các event hỗ trợ:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed monitor.jfr
~~~

**Lưu ý:** kết quả `jfr print` có thể rỗng nếu chương trình không pin, duration không vượt threshold, recording không bao phủ pha mong muốn hoặc cấu hình JFR khác. Không tự suy rằng event rỗng là bằng chứng tuyệt đối không có pinning. Khi muốn đo event ngắn hơn 20 ms, tùy chỉnh JFR event settings/threshold có kiểm soát; không giảm ngưỡng trong production mà không đánh giá overhead.

### 4.3. Thread dumps qua jcmd

Với một JVM JDK 21 còn chạy, lấy PID (ví dụ lệnh `jcmd -l`) rồi dump:

~~~bash
jcmd PID Thread.dump_to_file -format=text threads.txt
jcmd PID Thread.dump_to_file -format=json threads.json
~~~

Thay `PID` bằng PID thật. Tùy OS, JVM, quyền attach và thời điểm, file được ghi tại working directory của process Java nếu cung cấp relative path. Với JDK 21, `Thread.dump_to_file` có thể bao gồm virtual và platform threads, giúp thấy các stack đang chờ. Nó **khác** một dump `Thread.print` truyền thống; không nên dựa vào việc mọi định dạng đều hiển thị giống nhau các lock/JNI statistics.

Không tự tạo hàng trăm thread dumps mỗi giây trong production: hoạt động thu thập có chi phí và lượng log lớn. Ưu tiên lấy vài snapshots tại thời điểm latency tăng, kết hợp với JFR và request metrics.

## 5. Ví dụ Java 21 đầy đủ: tạo pinning có kiểm soát và đối chiếu

Ví dụ sau chỉ dùng **JDK 21**, không cần Maven hoặc Spring Boot. Nó cố tình gọi `Thread.sleep(250)` trong một monitor để minh họa pinning. Nhánh đối chứng dùng `ReentrantLock`, và nhánh không khóa cho thấy blocking bình thường.

Tạo file **`VirtualThreadPinningLab.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class VirtualThreadPinningLab {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private VirtualThreadPinningLab() {
    }

    public static void main(String[] args)
            throws InterruptedException {

        String mode = args.length == 0 ? "monitor" : args[0];

        if (!mode.equals("monitor")
                && !mode.equals("reentrant")
                && !mode.equals("plain")) {
            throw new IllegalArgumentException(
                    "Use monitor, reentrant or plain");
        }

        Thread virtual = Thread.ofVirtual()
                .name("pinning-lab")
                .start(() -> {
                    System.out.println("virtual="
                            + Thread.currentThread().isVirtual());

                    if (mode.equals("monitor")) {
                        synchronized (MONITOR) {
                            sleep250();
                        }
                    } else if (mode.equals("reentrant")) {
                        LOCK.lock();
                        try {
                            sleep250();
                        } finally {
                            LOCK.unlock();
                        }
                    } else {
                        sleep250();
                    }

                    System.out.println("completed=" + mode);
                });

        // Main là non-daemon; đợi virtual thread để không
        // để JVM kết thúc khi worker vẫn còn chạy.
        virtual.join();
        System.out.println("joined=true");
    }

    private static void sleep250() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Lab sleep was interrupted", e);
        }
    }
}
~~~

### Build và chạy

~~~bash
javac -encoding UTF-8 VirtualThreadPinningLab.java

java VirtualThreadPinningLab monitor
java VirtualThreadPinningLab reentrant
java VirtualThreadPinningLab plain
~~~

Ba chế độ có những dòng **stdout do chương trình tự in**, theo đúng thứ tự. Với `monitor`:

~~~text
virtual=true
completed=monitor
joined=true
~~~

Với `reentrant`:

~~~text
virtual=true
completed=reentrant
joined=true
~~~

Với `plain`:

~~~text
virtual=true
completed=plain
joined=true
~~~

Đây là stdout chủ động của mã Java, **không** gồm các dòng chẩn đoán tùy JVM. `join()` bảo đảm dòng `joined=true` xuất hiện sau khi virtual worker đã in `completed`. Trong chương trình này, `Thread.sleep(250)` là chờ giả lập, không phải phép đo throughput.

### Bật trace để phát hiện pinning

~~~bash
java -Djdk.tracePinnedThreads=full VirtualThreadPinningLab monitor
~~~

Trên **JDK 21**, đường monitor thường tạo cảnh báo stack trace trong quá trình virtual thread ngủ; đường `reentrant` hoặc `plain` không có lý do bị pin bởi **monitor của ví dụ này**. Tuy nhiên cách JVM in stack trace không phải contract output của chương trình. Tránh chép nguyên dòng stack trace có line number cứng vào assertion.

### Ghi JFR cho hai chế độ

~~~bash
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab monitor

java -XX:StartFlightRecording=filename=reentrant.jfr,dumponexit=true,settings=profile \
  VirtualThreadPinningLab reentrant

jfr print --events jdk.VirtualThreadPinned monitor.jfr
jfr print --events jdk.VirtualThreadPinned reentrant.jfr
~~~

**Kỳ vọng quan sát, không phải cam kết số lượng event:** trường hợp monitor có khả năng tạo event pinned vì chờ 250 ms vượt ngưỡng 20 ms; nhánh reentrant không có monitor pinning do đoạn code minh họa. Chênh lệch về stack/duration cần kiểm chứng bằng kết quả JFR thực tế. Chạy hai mode ở hai process mới giúp tránh trộn recording.

### Kết luận rút từ ví dụ

- Virtual threads đều in `virtual=true`, vì thế khác biệt **không** do một nhánh dùng platform thread.
- `Thread.sleep` không tự đồng nghĩa pinning; **ngữ cảnh monitor** trên JDK 21 mới là điều kiện mấu chốt ở đây.
- `ReentrantLock` có thể cho phép virtual thread chờ mà không pin carrier theo cách synchronized, nhưng vẫn giữ **tính loại trừ lẫn nhau** giữa các caller cùng lock.
- Pinning có thể khiến **throughput under load** giảm; một worker duy nhất chờ 250 ms không chứng minh throughput thấp. Phải đo concurrency ở mục 6.

## 6. Microbenchmark có đối chứng: carrier starvation dưới tải đồng thời

Một nhược điểm của ví dụ dùng một monitor chung: nhiều request sẽ **bị serialize bởi chính lock**, dù có pin hay không. Vì vậy nếu đo bằng một lock chung, ta có thể nhầm **lock contention** với **carrier pinning**. Để cô lập hiệu ứng trên JDK 21, ví dụ tiếp theo cấp cho mỗi tác vụ **một monitor riêng**, chỉ phân biệt cách chờ bên trong hay ngoài monitor.

Tạo file **`PinningThroughputLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class PinningThroughputLab {
    private static final int TASKS = 100;
    private static final int SLEEP_MS = 200;

    private PinningThroughputLab() {
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "plain" : args[0];

        if (!mode.equals("plain") && !mode.equals("monitor")) {
            throw new IllegalArgumentException(
                    "Mode must be plain or monitor");
        }

        // Mỗi task có monitor riêng, không tranh chấp
        // cùng một monitor giữa các tác vụ.
        Object[] guards = new Object[TASKS];
        for (int i = 0; i < TASKS; i++) {
            guards[i] = new Object();
        }

        CountDownLatch gate = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            for (int i = 0; i < TASKS; i++) {
                Object monitor = guards[i];

                futures.add(executor.submit(() -> {
                    gate.await();
                    if (mode.equals("monitor")) {
                        synchronized (monitor) {
                            Thread.sleep(SLEEP_MS);
                        }
                    } else {
                        Thread.sleep(SLEEP_MS);
                    }
                    return null;
                }));
            }

            long started = System.nanoTime();
            gate.countDown();

            // Future.get() làm hiện lỗi của task,
            // và đợi đủ TASKS tác vụ hoàn tất.
            for (Future<?> future : futures) {
                future.get();
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            System.out.println("mode=" + mode);
            System.out.println("tasks=" + TASKS);
            System.out.println("elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

Mã sử dụng Java 21 vì `Executors.newVirtualThreadPerTaskExecutor()` và `ExecutorService` dạng `AutoCloseable` đã hỗ trợ trong Java 21. Lambda trả `null` để khớp overload `Callable`, cho phép các lời gọi `gate.await()` và `Thread.sleep(...)` ném `InterruptedException` đúng cách. `Future.get()` chờ các task và đưa exception của chúng về main nếu có.

### Chạy với cùng scheduler parallelism

~~~bash
javac -encoding UTF-8 PinningThroughputLab.java

java -Djdk.virtualThreadScheduler.parallelism=2 \
  PinningThroughputLab plain

java -Djdk.virtualThreadScheduler.parallelism=2 \
  PinningThroughputLab monitor
~~~

JDK 21 có thuộc tính triển khai `jdk.virtualThreadScheduler.parallelism` để điều chỉnh số platform threads thông thường phục vụ scheduling virtual threads, mặc định dựa theo số processors. Đặt `2` **chỉ cho thí nghiệm**, nhằm làm hiện rõ giới hạn carrier ở JDK 21; đừng ép production scheduler về 2 nếu workload thực tế cần mức khác.

Đầu ra có dạng:

~~~text
mode=plain
tasks=100
elapsed_ms=<thời gian đo được>
~~~

Và:

~~~text
mode=monitor
tasks=100
elapsed_ms=<thời gian đo được>
~~~

Phần trong dấu góc là **mô tả số sẽ do chương trình tự tính**, không phải literal stdout hay số hiệu năng cam kết. Tỷ lệ chênh lệch tùy CPU, scheduler, container quota, máy chạy, JDK patch version và thời điểm đo.

### Vì sao hai nhánh có thể khác nhau rất lớn?

- `plain`: virtual threads chờ bằng `Thread.sleep` ngoài monitor, thông thường unmount và nhường carrier.
- `monitor`: trên JDK 21, `Thread.sleep` trong `synchronized` giữ carrier trong lúc chờ. Khi có ít carrier và nhiều tác vụ, các tác vụ tiếp theo phải chờ được lên lịch.
- Mỗi task có một monitor riêng, nên sự khác biệt **không phải do 100 tác vụ tranh một monitor**; đây là một thiết kế thí nghiệm tốt hơn việc dùng một lock chung.

Tuy nhiên benchmark này vẫn là **synthetic lab**: sleep không thay thế database query, TLS/network I/O, application framework, memory pressure hoặc p99 trong production. Nó nhằm chứng minh một cơ chế, không dự báo throughput thực của Spring Boot service.

### Lặp lại và không lấy một con số duy nhất

Nên chạy nhiều process độc lập theo chuỗi xen kẽ:

~~~bash
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab plain
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab monitor
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab monitor
java -Djdk.virtualThreadScheduler.parallelism=2 PinningThroughputLab plain
~~~

Lặp vòng, lấy median và khoảng biến thiên, giữ nguyên JDK, CPU quota và tham số. Nếu muốn đo chính xác microbenchmark của JVM, dùng JMH phù hợp và kiểm soát warm-up/JIT; chương trình trên là lab quan sát trực tiếp, không thay thế phương pháp benchmark nghiêm ngặt.

## 7. Spring Boot 3.5.x + JDK 21: cấu hình và đường đi request

Spring Boot hỗ trợ virtual threads trên Java 21+ bằng property:

~~~properties
spring.threads.virtual.enabled=true
~~~

Theo tài liệu Spring Boot 3.5, những executor/scheduler được Boot auto-configure có thể dùng virtual threads, và web server tích hợp tương ứng có thể xử lý request bằng virtual threads khi có hỗ trợ. **Không suy luận tất cả thread trong process đều là virtual**: request/filter/task executor custom, driver, web stack, SDK và các thư viện có thể dùng platform threads.

Đặc biệt, Spring Boot khuyến nghị xem xét:

~~~properties
spring.main.keep-alive=true
~~~

vì virtual threads đều daemon. Property này giải quyết điều kiện **JVM tiếp tục tồn tại**, không giải quyết carrier pinning. Với web server có các thread giữ process, keep-alive có thể không phải yếu tố quyết định, nhưng có ích khi ứng dụng chủ yếu dựa vào scheduler/virtual-thread tasks.

### Tạo một dự án Spring Boot tối giản để thử nghiệm

Cấu trúc:

~~~text
spring-vt-pinning/
├── pom.xml
└── src/main/
    ├── java/com/example/vtpin/
    │   ├── VirtualPinningApplication.java
    │   └── PinningController.java
    └── resources/
        └── application.yaml
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-vt-pinning</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản `3.5.0` là phiên bản Spring Boot 3.5.x cụ thể để ví dụ có thể build theo dependency management của parent. Không dùng `Thread.ofVirtual()`/API virtual threads với `java.version=17`; code này yêu cầu **JDK 21 khi biên dịch và chạy**.

**File `src/main/resources/application.yaml`:**

~~~yaml
spring:
  application:
    name: spring-vt-pinning
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Cấu hình metrics exposure ở đây chỉ dành cho **môi trường lab/local**. Khi triển khai thật, khóa quyền truy cập Actuator bằng network policy và security phù hợp; đừng tự expose metrics endpoint ra Internet.

**File `src/main/java/com/example/vtpin/VirtualPinningApplication.java`:**

~~~java
package com.example.vtpin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualPinningApplication {

    public static void main(String[] args) {
        SpringApplication.run(VirtualPinningApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/vtpin/PinningController.java`:**

~~~java
package com.example.vtpin;

import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PinningController {
    private final Object monitor = new Object();
    private final ReentrantLock lock = new ReentrantLock();

    @GetMapping("/thread")
    public Map<String, Object> threadInfo() {
        Thread current = Thread.currentThread();
        return Map.of(
                "virtual", current.isVirtual(),
                "name", current.getName());
    }

    @GetMapping("/monitor")
    public String monitor() throws InterruptedException {
        synchronized (monitor) {
            Thread.sleep(200);
        }
        return "monitor-done";
    }

    @GetMapping("/reentrant")
    public String reentrant() throws InterruptedException {
        lock.lock();
        try {
            Thread.sleep(200);
        } finally {
            lock.unlock();
        }
        return "reentrant-done";
    }

    @GetMapping("/plain")
    public String plain() throws InterruptedException {
        Thread.sleep(200);
        return "plain-done";
    }
}
~~~

**Quan trọng:** controller cố ý giữ **một lock chung** để minh họa business code có synchronized hoặc ReentrantLock. Vì mọi request cùng endpoint `/monitor` hoặc `/reentrant` tranh chấp cùng một lock, **không được dùng chênh lệch throughput giữa hai URL này để kết luận riêng tác động pinning**: chính lock serialization cũng giới hạn concurrency. Để cô lập carrier pinning, dùng lab với guard riêng cho mỗi task ở mục 6.

### Chạy và kiểm tra thread request

~~~bash
mvn -q -DskipTests package

java -Djdk.tracePinnedThreads=full \
  -XX:StartFlightRecording=filename=boot-pinning.jfr,dumponexit=true,settings=profile \
  -jar target/spring-vt-pinning-0.0.1-SNAPSHOT.jar
~~~

Trong terminal thứ hai:

~~~bash
curl -s http://127.0.0.1:8080/thread
curl -s http://127.0.0.1:8080/monitor
curl -s http://127.0.0.1:8080/reentrant
curl -s http://127.0.0.1:8080/plain
~~~

Nếu request được xử lý trên virtual thread đúng như cấu hình kỳ vọng, response `/thread` chứa JSON có `"virtual":true`; tên thread thay đổi theo runtime. Ba endpoint còn lại chủ động trả:

~~~text
monitor-done
reentrant-done
plain-done
~~~

Dòng chẩn đoán `jdk.tracePinnedThreads` có thể được JVM in ra **ngoài** HTTP responses. Nếu `/thread` trả `"virtual":false`, **không vội kết luận “virtual threads bị lỗi”**; kiểm tra JDK thực dùng để chạy, web server hiện tại, Spring Boot version, custom executors và request processing path. Benchmark pinning nên thực hiện trên endpoint/task mà `Thread.currentThread().isVirtual()` đã được xác nhận là `true`.

### Kết thúc và đọc recording

Dừng ứng dụng có kiểm soát (ví dụ Ctrl+C) để `dumponexit=true` ghi recording:

~~~bash
jfr print --events jdk.VirtualThreadPinned boot-pinning.jfr
~~~

Khi gọi `/monitor` nhiều lần trên JDK 21 bằng virtual-thread request handler, recording có thể chứa các event từ khối monitor. Lần gọi `/reentrant` và `/plain` không tạo monitor-pinning bởi code Java của ví dụ, nhưng ứng dụng/libraries khác vẫn có thể tạo pinned event. Vì vậy **đọc stack trace của event**, đừng chỉ đếm toàn bộ event trong một recording chung rồi quy cho một URL.

## 8. Đo hành vi có ý nghĩa: time, throughput, latency và error rate

### Thiết lập A/B

Một thiết kế lab tối thiểu:

- **Variant A:** request/tasks có blocking ngoài `synchronized` hoặc dưới `ReentrantLock` phù hợp.
- **Variant B:** cùng loại blocking bên trong `synchronized` của JDK 21.
- Cùng JDK **21 và patch version**, cùng Spring Boot artifact, classpath, JVM flags, CPU quota, heap, GC, logging và downstream.
- Đủ virtual concurrency để áp lực carrier thực sự xuất hiện.
- Giữ response semantics tương đương và kiểm tra không phát sinh dữ liệu sai.
- Thu JFR trong cùng cửa sổ tải, có baseline measurement không profiler nếu JFR overhead ảnh hưởng kết quả.
- Chạy nhiều process/round xen kẽ để giảm nhiễu JIT, cache, scheduler và network.
- Đo warm-up có kiểm soát, đặc biệt khi framework và library init chi phí lớn ở first request.

### Bốn nhóm chỉ số phải tách

| Nhóm | Chỉ số | Trả lời điều gì? |
| --- | --- | --- |
| Pinning diagnostics | Count `jdk.VirtualThreadPinned`, duration, stack/class/method, thời điểm | Có trường hợp pinning kéo dài được ghi nhận không, ở đâu? |
| Scheduler/concurrency | Carrier utilization, runnable backlog, virtual threads waiting, lock contention | Khi pinning xảy ra, scheduler có bị giữ carrier đến mức đáng kể không? |
| HTTP/service | Throughput (req/s), p50/p95/p99 latency, timeout/error rate | Người dùng hoặc downstream thấy tác động gì? |
| Resource | CPU, memory, GC, native threads, connection pool wait, downstream latency | Tác động do pinning hay do giới hạn khác? |

**Không thay thế p99 bằng duration trung bình của pinned event.** Duration phản ánh thời gian carrier bị giữ trong một thao tác; p99 latency là thời gian end-to-end request. Hai chỉ số liên quan nhưng không đồng nhất.

### Dùng load generator có concurrency đại diện

Với Spring Boot lab, có thể dùng k6, wrk, Gatling hoặc JMeter trên máy phát tải tách khỏi app nếu phù hợp. Các case nên bao gồm concurrency thấp/trung bình/cao, đủ thời gian warm-up và một khoảng đo đủ dài. Ghi cả lỗi HTTP 5xx, network timeout, CPU throttling và server resource saturation.

Đừng viết một benchmark dùng duy nhất `curl` tuần tự rồi tuyên bố pinning làm giảm throughput toàn hệ thống: một request 200 ms **chưa** gây cạnh tranh carrier.

### Kiểm soát lock contention

Trong production, đổi `synchronized` sang `ReentrantLock` có thể giữ tính loại trừ nhưng **không** xóa việc các request phải xếp hàng chờ cùng resource. Nếu endpoint có một critical section nắm lock quá lâu, thời gian chờ lock vẫn là bottleneck ngay cả khi virtual thread có thể unmount.

Muốn phân biệt:
1. Đo vị trí `jdk.VirtualThreadPinned` bằng JFR.
2. Đo lock wait/contention riêng.
3. Đo hiệu năng ở cùng input/transaction semantics.
4. Nếu có thể, giảm độ dài critical section hoặc dùng immutable snapshots, concurrent structures, thay vì chỉ đổi loại lock.

## 9. Sửa code bị ghim trên JDK 21

### Hướng 1: không blocking trong synchronized

Code trước:

~~~java
synchronized (monitor) {
    updateState();
    remoteCall();
}
~~~

Nếu `remoteCall()` có thể blocking lâu, đây là ứng viên cần đo. Code sau có thể tách phần việc bên ngoài monitor:

~~~java
synchronized (monitor) {
    updateState();
}

remoteCall();
~~~

**Hai snippet không nhất thiết tương đương về correctness.** Nếu yêu cầu nghiệp vụ là `updateState` và `remoteCall` phải nằm trong cùng critical section, chuyển call ra ngoài có thể tạo race hoặc phá invariant. Chỉ refactor sau khi xác định thread safety, transaction boundary và idempotency.

Một thiết kế tốt hơn có thể tạo snapshot bất biến dưới lock, thả lock, thực hiện I/O, rồi commit state mới có kiểm tra version nếu thực sự cần. Điều này giữ critical section nhỏ mà không bí mật thay đổi tính nhất quán.

### Hướng 2: ReentrantLock

Ví dụ thay monitor block khi vẫn cần loại trừ:

~~~java
private final ReentrantLock lock = new ReentrantLock();

public String load() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(200);
        return "loaded";
    } finally {
        lock.unlock();
    }
}
~~~

Đây là snippet Java của một instance class; import `java.util.concurrent.locks.ReentrantLock`. Dùng `finally` để bảo đảm unlock khi method ném exception. Trên JDK 21, `ReentrantLock` phù hợp với virtual threads hơn khi phải chờ lâu vì nó tránh cơ chế **pinning do monitor**. Tuy vậy, giữ lock trong lúc I/O vẫn có thể làm request khác phải đợi. Có khi giải pháp tốt nhất là **không giữ bất kỳ lock nào qua I/O**, nếu đúng semantics.

### Hướng 3: sửa ở tầng thư viện/driver

Nếu stack trace JFR cho thấy code bị ghim ở một thư viện:
- kiểm tra version có hỗ trợ virtual threads tốt hơn không;
- xem có dùng `synchronized` để giữ resource trong một blocking call không;
- đánh giá thay thư viện/driver hoặc cấu hình client;
- khi có native/JNI blocking, xem xét cô lập vào platform-thread executor có giới hạn concurrency;
- lập performance test có lỗi và tải thật trước khi thay đổi dependency.

**Không nên tự dùng reflection hoặc patch một class thư viện production** chỉ để bỏ `synchronized` mà không có kiểm thử thread safety. Thay đổi lock semantics có thể tạo bug khó tìm hơn pinning.

### Hướng 4: giới hạn nguồn contention

Một code path có 200 virtual threads nhưng chỉ có 10 JDBC connections vẫn phải đợi pool. Virtual threads không xóa capacity của database, HTTP downstream, file descriptors hoặc rate limiter. Dùng semaphore, bounded admission control hoặc connection pool sizing phù hợp để bảo vệ downstream. Đây là biện pháp cho **resource saturation**, không phải lời giải thay thế cho một pinned native call.

## 10. Các case dễ kết luận sai

### Không thấy event vì chưa vượt 20 ms

JFR `jdk.VirtualThreadPinned` mặc định dùng threshold 20 ms trên JDK 21. Một thao tác pin 5 ms nhưng xảy ra hàng nghìn lần có thể vẫn có tổng chi phí. Nếu nghi ngờ, đo dưới tải, điều chỉnh ngưỡng recording trong môi trường kiểm thử, kết hợp trace và latency metrics. Không khẳng định “0 event” = “0 pinning” nếu chưa xét recording window/threshold.

### Thấy synchronized nhưng không có blocking

Một synchronized getter trong bộ nhớ kéo dài vài microseconds thường không đáng sửa. Thay hết bằng `ReentrantLock` không chỉ tốn effort mà còn làm code phức tạp và có thể ảnh hưởng concurrency semantics. Ưu tiên những vị trí **frequent + long-lived blocking** được JFR xác nhận.

### Thấy throughput thấp nhưng không có pinning

Có thể nguyên nhân là DB pool nhỏ, thread pool custom vẫn dùng platform threads, CPU throttling, GC pauses, lock contention hoặc downstream latency. Mỗi loại có phép đo riêng. Một ứng dụng bật virtual threads nhưng có executor riêng chưa đổi sang virtual threads có thể không chạy workload cần thiết trên virtual threads.

### Chạy trên JDK 24 rồi đợi synchronized tạo event giống JDK 21

JEP 491 từ JDK 24 đã xử lý pinning do Java monitors ở mức runtime. Trong một bản JDK mới, demo `synchronized + Thread.sleep` có thể không còn tạo sự kiện pinned kiểu cũ. Đây **không phải failure của demo trên JDK 21**; nó là khác biệt phiên bản phải được ghi trong báo cáo.

### Dùng -Djdk.tracePinnedThreads trên JDK 24+

Đây là cờ diagnostic của JDK 21–23 và không còn là cách đáng tin trên JDK 24+. Ưu tiên JFR, thread dump và tài liệu chính xác của phiên bản JDK đang chạy. Không sao chép một command dòng lệnh rồi kết luận công cụ hỏng nếu chạy nhầm phiên bản.

### Spring Boot báo started nhưng request không dùng virtual threads

Property `spring.threads.virtual.enabled=true` ảnh hưởng những integration được Boot hỗ trợ, không bắt buộc tất cả mã do thư viện sở hữu đổi executor. Kiểm tra ở đúng request/worker bằng `Thread.currentThread().isVirtual()`, và xem `TaskExecutor`/web server custom.

### JVM kết thúc sớm vì chỉ còn daemon threads

Virtual threads luôn daemon. Với ứng dụng không có web server non-daemon hoặc component giữ sống khác, JVM có thể thoát mặc dù scheduled tasks chưa chạy. Dùng `spring.main.keep-alive=true` khi phù hợp; không lẫn lộn đây với hiện tượng pinning.

### Trace hoặc profiler khiến kết quả thay đổi

Trace stack cho nhiều pinning events có thể tạo lượng output lớn, làm latency tăng do logging. Nên:
1. Chạy diagnostic để xác định stack.
2. Chạy A/B baseline với cấu hình công cụ tương đương.
3. Nếu cần JFR cho cả hai nhánh, bật cùng settings và khoảng thời gian.
4. Báo cáo rõ overhead/giới hạn đo.

### Bỏ qua trường hợp pinning không thể sửa bằng Java lock

Native code có thể ghim carrier ngay cả khi code Java bên ngoài dùng `ReentrantLock`. Khi stack có native frames, cần phương án ở tầng thư viện/driver hoặc cô lập workload. Đừng quảng cáo “chỉ cần đổi lock là hết mọi pinning”.

## 11. Khác biệt quan trọng giữa JDK 21 và JDK 24+

**Không gộp mọi JDK >=21 thành một phiên bản hành vi pinning.**

| Vấn đề | JDK 21 | JDK 24+ |
| --- | --- | --- |
| Virtual threads chính thức | Có, theo JEP 444 | Có |
| Blocking bên trong Java `synchronized` có thể pin carrier | Có | Java monitor pinning đã được xử lý bởi JEP 491 |
| Native/foreign blocking có thể pin | Có | Vẫn cần đánh giá |
| `jdk.VirtualThreadPinned` của JFR | Có | Vẫn dùng để chẩn đoán các dạng pinning còn lại |
| `-Djdk.tracePinnedThreads` | Công cụ chẩn đoán phù hợp | Không áp dụng máy móc như ở JDK 21 |
| Kiểm chứng theo workload thực | Bắt buộc | Vẫn bắt buộc |
| Thread scheduler, resource pools, downstream capacity | Có giới hạn | Vẫn có giới hạn |

Spring Boot 3.5 còn nêu trong tài liệu rằng **Java 24+ được khuyến nghị để có trải nghiệm virtual threads tốt hơn**, dù tính năng hỗ trợ từ Java 21. Lý do bao gồm những cải tiến JVM như JEP 491; không nên diễn giải thành việc chuyển JDK mới sẽ giải quyết tất cả bottleneck hoặc loại bỏ toàn bộ native pinning.

Khi tổ chức vẫn triển khai JDK 21 LTS, quy trình phù hợp là đo và sửa có chọn lọc những chỗ pinning ảnh hưởng SLO. Khi chuẩn bị chuyển JDK 24+ hoặc JDK LTS mới hơn, phải **chạy benchmark lại**, vì cùng một source code có thể thay đổi hành vi pinning đáng kể.

## 12. Checklist thực nghiệm chuẩn cho một Spring Boot service trên JDK 21

**Trước khi đo:**
1. Ghi `java -version` để xác nhận đúng JDK 21, không phải Java 17 hoặc 24+.
2. Ghi artifact hash, Spring Boot version, container image, active profile và JVM flags.
3. Xác nhận `spring.threads.virtual.enabled=true` trên đúng môi trường cần đo.
4. Kiểm tra đường request/task thật có `Thread.currentThread().isVirtual()==true`.
5. Ghi số CPU được cấp, CPU quota/throttling, memory limits, GC và downstream capacity.
6. Xác nhận input/response đúng chức năng; pinning performance không được đánh đổi lấy data corruption.

**Thu thập dữ liệu:**
7. Bật `-Djdk.tracePinnedThreads=short/full` trong lượt chẩn đoán; lưu stack traces.
8. Bật JFR `jdk.VirtualThreadPinned` trong một cửa sổ có tải đại diện; giữ log/JFR files có quyền truy cập an toàn.
9. Ghi count/duration/stack của pinned events và tần suất theo phút hoặc theo request.
10. Nếu ứng dụng treo/latency tăng, lấy `jcmd Thread.dump_to_file` một số lần với timestamp.
11. Đo throughput, p50/p95/p99, error/timeout, CPU, GC, RSS và connection pool waiting.
12. Đo khác nhau giữa ít và nhiều concurrent requests; một request tuần tự thường không thể làm rõ carrier starvation.

**Sửa và kiểm chứng:**
13. Ưu tiên xử lý các chỗ thường xuyên blocking dài trong monitor, không đổi mọi synchronized.
14. Giữ nguyên business semantics khi tách I/O khỏi critical section hoặc chuyển sang `ReentrantLock`.
15. Kiểm tra thư viện/native code riêng; không giả định tất cả pinned events do code controller.
16. Chạy lại A/B với cùng artifact điều kiện, trừ đúng thay đổi cần đánh giá.
17. Thu thập cả latency/success và JFR events **sau** sửa để xem cải thiện có thật không.
18. Nếu không có lợi ích rõ và code mới phức tạp hơn, cân nhắc giữ thiết kế cũ, giảm concurrency hoặc nâng JDK theo roadmap.

### Mẫu báo cáo để không bịa kết quả

~~~text
JDK version/build: (ghi từ java -version)
Spring Boot / artifact digest: (ghi thực tế)
Host / CPU quota / container memory: (ghi thực tế)
Workload: endpoint, RPS, concurrency, duration, inputs
Virtual request thread confirmed: true/false
JFR event settings / threshold: (ghi thực tế)
Variant A: monitor-blocking on JDK 21
Variant B: refactored / ReentrantLock / outside monitor
Pinning events per minute, A: (đo)
Pinning events per minute, B: (đo)
Median/p95 pinned duration, A/B: (đo)
Throughput, A/B: (đo)
p95/p99 latency, A/B: (đo)
Timeout/error rate, A/B: (đo)
CPU, RSS, GC, downstream pool wait, A/B: (đo)
Decision: (dựa trên số thực và SLO)
~~~

Các đoạn trong ngoặc là **trường phải điền từ phép đo thật**, không phải kết quả có thể tự kết luận từ một code snippet.

## 13. Tự kiểm tra kiến thức

**Câu 1. Pinning trên JDK 21 là gì?**  
Đó là khi virtual thread bị gắn với carrier trong một thao tác blocking không thể unmount, khiến carrier chưa rảnh để phục vụ virtual thread khác.

**Câu 2. Chỉ nhìn thấy synchronized là đủ để kết luận performance issue không?**  
Không. Cần blocking đủ dài/thường xuyên và số liệu về concurrency, throughput hoặc latency.

**Câu 3. Thread.sleep(250) ngoài synchronized có nhất thiết pin carrier trên JDK 21 không?**  
Không. `Thread.sleep` của virtual thread thông thường hỗ trợ unmount khi không ở vùng pinning.

**Câu 4. JFR event nào ghi trường hợp virtual thread bị pinned lâu?**  
`jdk.VirtualThreadPinned`.

**Câu 5. Ngưỡng mặc định Oracle JDK 21 cho pinned JFR event là bao nhiêu?**  
20 ms.

**Câu 6. JVM flag nào dùng để in pinning stack trace trên JDK 21?**  
`-Djdk.tracePinnedThreads=full` hoặc `short`, đặt trước tên main class/JAR.

**Câu 7. Thread dump chứa virtual threads có thể lấy bằng lệnh nào?**  
`jcmd PID Thread.dump_to_file -format=json threads.json` hoặc dạng text.

**Câu 8. Vì sao benchmark chỉ dùng một shared synchronized lock không cô lập được pinning?**  
Vì các request đã bị serialize do tranh lock, nên throughput thấp có thể do contention thay vì carrier pinning.

**Câu 9. Cách đơn giản để tránh monitor-related pinning trên JDK 21 trong đoạn blocking dài là gì?**  
Khi đúng semantics, chuyển blocking ra ngoài monitor hoặc thay bằng `ReentrantLock`; vẫn phải đánh giá contention.

**Câu 10. Nếu pinning xảy ra trong native method, đổi synchronized Java có giải quyết toàn bộ không?**  
Không; cần phân tích native/JNI/foreign code và thư viện.

**Câu 11. Bật spring.threads.virtual.enabled=true có bảo đảm mọi thread là virtual không?**  
Không. Chỉ những integration hỗ trợ và không bị override custom executor mới chịu cấu hình phù hợp.

**Câu 12. JDK 24+ còn pin vì synchronized giống JDK 21 không?**  
Không theo cơ chế Java monitor cũ: JEP 491 đã xử lý loại pinning đó. Những dạng pinning khác vẫn cần chẩn đoán.

**Câu 13. Một JFR file không có VirtualThreadPinned event có chứng minh không có pinning không?**  
Không. Có thể event không vượt ngưỡng hoặc xảy ra ngoài recording window.

**Câu 14. Vì sao cần đo p95/p99 và throughput ngoài số lượng pinned events?**  
Vì mục tiêu là tác động tới chất lượng dịch vụ; event duration không đồng nhất với response latency hay success rate.

**Câu 15. Virtual threads có phải nhanh hơn platform threads trong CPU-bound loops không?**  
Không. Chúng giúp tăng khả năng scale các workload nhiều blocking I/O, không tự tăng tốc tính toán CPU.

## 14. Tài liệu chính thức và định hướng đọc thêm

- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): carrier/mount/unmount, hai trường hợp pinning, JFR event ngưỡng 20 ms, `jdk.tracePinnedThreads`, `jcmd`.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): thiết kế, scheduling, hạn chế và chẩn đoán trên JDK 21.
- [Oracle JDK 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `Thread.ofVirtual()`, `isVirtual()`, scheduler implementation properties.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.dump_to_file`, diagnostic commands.
- [Oracle JDK 21 — jfr tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): đọc và phân tích các event trong `.jfr` recording.
- [Spring Boot 3.5 — SpringApplication / Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `spring.threads.virtual.enabled`, pinning caveats, `spring.main.keep-alive`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): virtual-thread executors và schedulers được auto-configure.
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi Java monitor pinning từ JDK 24.
- [Oracle JDK 21 — Flight Recorder Configuration](https://docs.oracle.com/en/java/javase/21/jfapi/): cấu hình recording/events và ngưỡng quan sát.

**Kết luận:** Trên **JDK 21**, hãy nhận diện một virtual thread bị pin bằng **stack trace/JFR**, xác nhận rằng đường tác vụ thật dùng virtual threads và đo tác động bằng **throughput, tail latency, error rate, carrier/resource metrics**. Chỉ refactor khi pinning vừa đủ dài, đủ thường xuyên **và** ảnh hưởng hệ thống. Đừng nhầm cơ chế Java 21 với JDK 24+, đừng thay mọi `synchronized` một cách máy móc, và đừng dùng virtual threads để che một bottleneck downstream khác.