# Carrier threads và scheduling của JVM trong Virtual Threads

## 1. Bức tranh tổng thể: ai lập lịch cho ai?

Từ Java 21, **virtual thread** là một loại `java.lang.Thread` chính thức. Nó giúp ứng dụng tạo nhiều luồng tác vụ đồng thời, đặc biệt khi phần lớn thời gian là chờ I/O, mà không cần một luồng hệ điều hành (OS thread) riêng cho mỗi tác vụ. Virtual thread vẫn thực thi mã Java trên CPU thông qua **platform thread**; JVM không tạo ra CPU hay thực thi mã ở “ngoài” OS thread.

Ba vai trò cần phân biệt:

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| Virtual thread | Đơn vị thực thi logic mà mã ứng dụng tạo, thường một tác vụ trên một thread | Có danh tính, stack, `ThreadLocal` và trạng thái riêng; không sở hữu OS thread suốt vòng đời |
| Carrier thread | Platform thread đang **chở** một virtual thread trong lúc mã của virtual thread chạy | Một carrier có thể lần lượt chạy nhiều virtual threads; cùng một virtual thread có thể chạy trên các carrier khác nhau |
| JVM scheduler và OS scheduler | JVM chọn virtual thread để **mount** lên carrier; OS chọn lúc platform/carrier thread được CPU chạy | Hai tầng lập lịch khác nhau, không có ánh xạ cố định một-một |

Sơ đồ khái niệm (các mũi tên diễn tả những thời điểm khác nhau, không phải tất cả virtual threads chạy đồng thời):

```text
Ứng dụng:     VT-A   VT-B   VT-C   VT-D   VT-E ... VT-N
                \      |      /       \      /
                 JVM virtual-thread scheduler
                          |
             +------------+------------+
             |                         |
          Carrier-1                 Carrier-2   ... (platform threads)
             |                         |
             +----- OS scheduler ------+
                          |
                       CPU cores
```

**Mount** là lúc JVM gắn ngữ cảnh thực thi của virtual thread vào một carrier để nó chạy. **Unmount** là lúc JVM tách ngữ cảnh ấy, thường khi virtual thread chờ một thao tác có hỗ trợ cơ chế đình chỉ. Carrier vừa được giải phóng có thể chạy virtual thread khác. Đó là cách **M virtual threads được ghép lên N platform threads** (M:N scheduling).

Lập lịch virtual threads là chi tiết triển khai của JDK. Những mô tả về `ForkJoinPool`, tham số cấu hình, sự kiện quan sát trong bài này áp dụng cho triển khai OpenJDK/HotSpot hiện đại; không nên coi chúng là cam kết cố định của mọi JVM.

## 2. Một vòng đời mount → park → unmount → remount

Ví dụ một virtual thread đọc dữ liệu qua một API blocking I/O được JDK hỗ trợ:

1. Ứng dụng gọi `Thread.start()` hoặc gửi tác vụ vào `Executors.newVirtualThreadPerTaskExecutor()`. Virtual thread được đưa vào hàng công việc sẵn sàng chạy.
2. JVM scheduler chọn một carrier khả dụng và mount virtual thread. Mã chạy bình thường; trong mã ứng dụng, `Thread.currentThread()` vẫn trả về **virtual thread**, không phải carrier.
3. Tác vụ gọi thao tác chờ, chẳng hạn đọc socket khi chưa có dữ liệu. JDK có thể **park/unmount** virtual thread, lưu trạng thái tiếp tục của stack và nhường carrier. Không phải mọi lời gọi “blocking” đều chắc chắn unmount; phụ thuộc loại thao tác và phiên bản JDK.
4. Khi I/O sẵn sàng, hết thời gian chờ hoặc có tín hiệu đánh thức phù hợp, JDK làm virtual thread **runnable** trở lại và đưa nó về scheduler.
5. Scheduler remount nó lên **một carrier khả dụng bất kỳ**. Mã tiếp tục sau điểm chờ, rồi hoàn thành như một thread bình thường.

```text
VT mới -> runnable -> mounted/running -> chờ I/O
                       ^                    |
                       |                    v
                       +--- runnable <- parked/unmounted
                            (được đánh thức)
```

Một virtual thread có thể park và resume nhiều lần; carrier lúc resume **không bắt buộc là carrier cũ**. Phải phân biệt “được đánh thức và chờ vào hàng runnable” với “ngay lập tức được CPU thực thi”: còn cần scheduler JVM chọn carrier và OS cho carrier chạy.

Điều này không làm thay đổi ngữ nghĩa `synchronized`, `volatile`, `Lock`, `interrupt` hay quy tắc happens-before của Java. Virtual threads đổi cách **sử dụng tài nguyên chờ**, không tự tạo thêm bảo đảm thứ tự thực thi.

## 3. Scheduler mặc định hoạt động như thế nào?

Trong JDK OpenJDK/HotSpot, scheduler mặc định của virtual threads dùng một `ForkJoinPool` theo mô hình **work-stealing** và thiên về tác vụ bất đồng bộ (FIFO). Đây là pool dành cho việc chạy các *continuation* của virtual threads và **khác** với `ForkJoinPool.commonPool()` dùng bởi nhiều tác vụ khác, chẳng hạn một số `CompletableFuture` hoặc parallel streams.

- **Target parallelism**: số carrier platform threads mà scheduler hướng tới để chạy virtual threads. Mặc định gắn với số processor khả dụng do JVM nhìn thấy; đó là **mức song song mục tiêu**, không phải số virtual threads được phép tạo.
- **Runnable queue**: virtual threads đã sẵn sàng nhưng chưa được mount sẽ chờ scheduler. Work-stealing giúp các carrier san sẻ công việc; không hứa hẹn FIFO tuyệt đối trên toàn bộ hệ thống.
- **Compensation**: khi một số hoạt động blocking làm carrier không khả dụng, triển khai có thể tăng số platform threads trong scheduler trong một số tình huống, chịu giới hạn cấu hình và tài nguyên. Cơ chế này không chữa mọi trường hợp pinning hoặc blocking native.
- **OS scheduling**: ngay cả khi có nhiều carrier, số mã chạy CPU đồng thời vẫn phụ thuộc CPU thực tế, mức tải và scheduler của hệ điều hành.

Một vòng lặp CPU rất dài không tự nhiên được virtual-thread scheduler chia đều thành những “time slice” công bằng cho các virtual threads khác. Virtual threads không phù hợp làm phương tiện tăng tốc tính toán CPU-bound; OS preempt carrier không đồng nghĩa JVM preempt tác vụ virtual thread đang giữ carrier.

**Ví dụ tư duy:** 10.000 tác vụ đang chờ phản hồi socket có thể tương ứng với 10.000 virtual threads nhưng chỉ cần một số nhỏ carrier *đang thực thi* mã ở mỗi thời điểm. Ngược lại, 10.000 tác vụ cùng tính toán liên tục vẫn tranh chấp số lõi CPU hữu hạn. Không có phép tính “10.000 virtual threads = 10.000 tác vụ chạy trên CPU đồng thời”.

## 4. Cấu hình scheduler: hiểu đúng trước khi chỉnh

Các thuộc tính sau là **system properties của triển khai JDK**, truyền lúc JVM khởi động:

| Thuộc tính | Ý nghĩa | Không có nghĩa là |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Target parallelism của scheduler; mặc định thường bằng số processor JVM nhận thấy | Giới hạn số virtual threads hay số yêu cầu nghiệp vụ |
| `jdk.virtualThreadScheduler.maxPoolSize` | Giới hạn số platform threads scheduler có thể sử dụng trong các tình huống cần bù trừ; JDK 21/25 mặc định 256 | Giá trị nên tăng tới số tác vụ; cách chữa code bị block lâu |

Ví dụ chạy chương trình minh họa với scheduler chỉ nhắm tới hai carrier:

```bash
javac CarrierSchedulingDemo.java
java -Djdk.virtualThreadScheduler.parallelism=2 CarrierSchedulingDemo
```

Nên bắt đầu từ mặc định, đo các chỉ số hàng đợi/running/pinning và throughput trước khi điều chỉnh. Cố tăng parallelism trên workload CPU-bound có thể làm tăng context switching. Hạ quá thấp có thể khiến tác vụ runnable phải xếp hàng lâu nếu carrier bị giữ bởi mã chạy dài. Giới hạn kết nối mạng, database, RAM, file descriptor hay tốc độ dịch vụ bên ngoài vẫn cần quản lý **riêng**; scheduler không thay thế giới hạn tài nguyên nghiệp vụ.

**Không nhầm** `Executors.newVirtualThreadPerTaskExecutor()` với một pool chứa sẵn N virtual threads: executor này tạo **một virtual thread mới cho mỗi tác vụ**, còn carrier pool nằm ở tầng lập lịch của JDK. Tránh dùng fixed thread pool để “pool virtual threads”. Để giới hạn số truy vấn đồng thời tới một tài nguyên, dùng cơ chế chuyên dụng như `Semaphore`/pool kết nối.

## 5. Thí nghiệm Java 21+: nhiều virtual threads chờ, ít carrier vẫn tiến triển

Tệp **CarrierSchedulingDemo.java** sau tạo 100 virtual threads, cho từng thread dừng ở một `CountDownLatch`, rồi main chỉ mở chốt sau khi cả 100 đã tới điểm chờ. Trong thực thi chuẩn trên JDK 21+, việc chờ latch ở virtual thread không cần chiếm vĩnh viễn một carrier.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CarrierSchedulingDemo {
    public static void main(String[] args) throws InterruptedException {
        final int tasks = 100;
        CountDownLatch allWaiting = new CountDownLatch(tasks);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger virtualCount = new AtomicInteger();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < tasks; i++) {
                executor.submit(() -> {
                    if (Thread.currentThread().isVirtual()) {
                        virtualCount.incrementAndGet();
                    }
                    allWaiting.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            allWaiting.await();
            System.out.println("Da den diem cho: "
                    + (tasks - allWaiting.getCount()));
            release.countDown();
        } // close() đợi các tác vụ đã gửi kết thúc

        System.out.println("Virtual threads: " + virtualCount.get());
    }
}
```

Biên dịch và chạy:

```bash
javac CarrierSchedulingDemo.java
java -Djdk.virtualThreadScheduler.parallelism=2 CarrierSchedulingDemo
```

**Stdout**:

```text
Da den diem cho: 100
Virtual threads: 100
```

Giải thích:

- Mỗi task chạy trong một virtual thread riêng; `Thread.currentThread().isVirtual()` kiểm tra đúng loại thread. Việc tăng biến đếm xảy ra **trước** `countDown()`, nên khi main chờ xong thì số đếm đã đủ 100.
- Mọi task tới `release.await()` và tạm ngừng. Main vẫn có thể tiếp tục, rồi `countDown()` đánh thức các task đang chờ.
- Với `parallelism=2`, chương trình vẫn cho 100 virtual threads đạt tới điểm chờ. Điều này **không đo trực tiếp** số carrier thực tế và không chứng minh mọi thư viện blocking I/O đều unmount; nó minh họa cách virtual threads chia sẻ năng lực chạy.
- `CountDownLatch`, `AtomicInteger` và cơ chế chờ bảo đảm stdout ổn định; thứ tự cụ thể giữa 100 task không được giả định. Trong mã thực tế cần xử lý hoặc báo cáo exception từ `Future` khi muốn phát hiện lỗi tác vụ; `submit` có thể giữ exception trong `Future`.

Bạn có thể đổi `tasks` thành 1.000 nếu môi trường đủ tài nguyên để quan sát tác vụ chờ, nhưng tránh suy diễn benchmark từ một lần chạy. Để so sánh có ý nghĩa, đo CPU, heap, throughput, độ trễ và hàng đợi trên workload gần thực tế.

## 6. Pinning: khi carrier không được giải phóng

**Pinning** xảy ra khi virtual thread đang ở điểm chờ nhưng JVM không thể unmount nó, khiến carrier OS thread bị giữ/block cùng. Tác vụ thường vẫn đúng về mặt logic; rủi ro chính là **giảm khả năng mở rộng** khi nhiều carrier bị giữ lâu.

Cần phân biệt phiên bản:

| Phiên bản | Điều cần biết |
| --- | --- |
| **JDK 21–23** | Blocking bên trong `synchronized` method/block có thể pin carrier. Nếu việc chờ dài và lặp thường xuyên, đây là vấn đề throughput đáng kiểm tra; JDK 21 hỗ trợ `-Djdk.tracePinnedThreads=short` hoặc `full` để khảo sát |
| **JDK 24+** | **JEP 491** cho phép virtual threads unmount khi chờ trong hoặc chờ lấy Java monitor (`synchronized`), nên không còn quy tắc chung “`synchronized` luôn gây pinning” |
| **Các JDK hiện đại** | Những điểm phụ thuộc native/foreign-function frames và một số đoạn mã/hoạt động đặc biệt vẫn có thể pin; cần quan sát trên chính bản JDK và nền tảng đang chạy |

Không nên “đổi toàn bộ `synchronized` sang `ReentrantLock`” theo thói quen. Với JDK 21–23, cân nhắc thay đúng **đoạn blocking dài và thường xuyên** nếu pinning thực sự gây nghẽn. Với JDK 24+, đo lại vì cách xử lý monitor đã thay đổi. Ngoài pinning, **CPU-bound code dài** hay **native blocking** cũng có thể chiếm carrier và gây thiếu tiến triển, dù nguyên nhân không giống nhau.

Đặc biệt, mã có khóa bao trùm I/O sẽ còn có **tranh chấp khóa logic** ngay cả khi không pin. “Không pin carrier” không đồng nghĩa nhiều task có thể cùng vào critical section hoặc dịch vụ phụ thuộc xử lý nhanh hơn.

## 7. Quan sát scheduler và chẩn đoán tắc nghẽn

**JDK 21+:** dùng các khả năng hỗ trợ virtual thread của Java Flight Recorder (JFR) và thread dump:

```bash
# JVM đang chạy: thay PID bằng process id thật
jcmd <PID> Thread.dump_to_file -format=json threads.json

# Ví dụ khởi chạy app có ghi JFR đến khi JVM kết thúc
java -XX:StartFlightRecording=filename=recording.jfr,dumponexit=true CarrierSchedulingDemo

jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

- `jdk.VirtualThreadPinned` giúp phát hiện trường hợp block trong lúc pinned; các cấu hình JFR phổ biến bật sự kiện này với ngưỡng 20 ms, nên không có event **không đủ chứng minh** không có pinning ngắn.
- `jdk.VirtualThreadSubmitFailed` phản ánh thất bại khi đưa tác vụ virtual thread vào lịch chạy, thường cần kiểm tra sức ép tài nguyên.
- `jdk.VirtualThreadStart`/`jdk.VirtualThreadEnd` thường không bật mặc định vì khối lượng sự kiện có thể rất lớn. Bật có chủ đích nếu cần phân tích vòng đời.
- Thread dump giúp xem virtual threads, stack và nơi chờ. Không nên đọc số lượng virtual threads trong dump thành số carrier hay số thread đang chạy CPU.

**JDK 24+:** có thêm công cụ quan sát trực tiếp scheduler:

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

JDK 24 cũng đưa vào `jdk.management.VirtualThreadSchedulerMXBean` (JMX), có các số đo như target parallelism, số carrier đã tạo, ước lượng virtual threads đang mounted và số đang queued; có hỗ trợ chỉnh target parallelism qua MXBean. Các con số là **ảnh chụp/ước lượng nhất thời**, không thể dùng riêng lẻ để kết luận rò rỉ hay deadlock. Các lệnh `Thread.vthread_scheduler` và MXBean **không có trong JDK 21**.

Đọc hiện tượng theo chuỗi nguyên nhân:

1. **Nhiều virtual threads parked** nhưng CPU thấp, throughput bình thường: thường là tác vụ đang chờ I/O/tín hiệu; không tự coi là lỗi.
2. **Nhiều virtual threads runnable/queued**, throughput thấp: kiểm tra carrier bận CPU, tác vụ không nhường tài nguyên, pinning/native blocking, mức parallelism và giới hạn tài nguyên.
3. **Nhiều sự kiện pinned kéo dài**: tìm stack/đường đi tới native hay đoạn blocking, xét phiên bản JDK và tần suất.
4. **CPU gần bão hòa**: profile điểm nóng CPU; tăng số virtual threads không tạo thêm lõi.
5. **Độ trễ cao nhưng scheduler khỏe**: xem connection pool, giới hạn downstream, thời gian I/O, timeouts, số kết nối mở đồng thời.

## 8. Những nhầm lẫn thường gặp

- **“Virtual thread luôn chạy không cần OS thread.”** Sai: khi thực thi mã, nó chạy trên carrier platform thread được OS lập lịch.
- **“Mỗi virtual thread có một carrier riêng.”** Sai: nhiều virtual threads dùng lại tập carrier, mỗi virtual thread có thể remount ở carrier khác.
- **“Mỗi thao tác blocking tự động nhường carrier.”** Sai: phụ thuộc khả năng hỗ trợ unmount, trạng thái pinning và runtime/native boundary.
- **“parallelism=2 chỉ được tạo hai virtual threads.”** Sai: đó là target song song của scheduler, không phải hạn mức số tác vụ.
- **“maxPoolSize là số task tối đa và tăng lên sẽ chữa mọi nghẽn.”** Sai: thuộc tính này quản lý platform threads của scheduler và không sửa mã block/pin hoặc giới hạn I/O bên ngoài.
- **“Gọi `Thread.currentThread()` để xem carrier.”** Sai: khi đang chạy trong virtual thread, lời gọi đó trả về chính virtual thread.
- **“Virtual threads luôn chạy công bằng và nhanh hơn platform threads.”** Sai: không có bảo đảm time-slicing công bằng ở tầng virtual-thread scheduler; điểm mạnh là tiết kiệm tài nguyên **khi chờ**, không tăng tốc CPU.
- **“Từ JDK 24, `synchronized` vẫn pin như JDK 21.”** Sai: JEP 491 thay đổi hành vi với Java monitor, dù những nguyên nhân pinning khác vẫn có thể tồn tại.
- **“Có triệu virtual threads thì bỏ mọi giới hạn.”** Sai: heap, network, socket, file descriptor, connection pools, timeouts và throughput dịch vụ ngoài vẫn hữu hạn.

## 9. Khi áp dụng vào chương trình Java

Suy nghĩ theo **tác vụ**: nếu có nhiều việc độc lập, phần lớn chờ I/O, mô hình một virtual thread cho mỗi tác vụ giúp giữ mã đồng bộ dễ đọc mà không dùng một platform thread trong toàn bộ thời gian chờ. Chọn công cụ concurrency của Java (`ExecutorService`, `Future`, `Semaphore`, `CountDownLatch`, `Lock`, `ThreadLocal`) theo ngữ nghĩa của bài toán; virtual threads không thay thế synchronization, cancellation hay backpressure.

Để đánh giá một ứng dụng thực tế:

1. Xác định phần CPU-bound, I/O-bound, thời gian chờ và giới hạn downstream.
2. Kiểm tra thư viện/I/O dùng JDK API có hỗ trợ park/unmount; đừng giả định mọi native call đều thân thiện với virtual threads.
3. Giữ xử lý `interrupt`, hủy tác vụ, timeout và tài nguyên (`try-with-resources`) rõ ràng.
4. Giới hạn truy cập tài nguyên khan hiếm bằng cơ chế phù hợp, không dùng “số virtual threads” làm bộ giới hạn gián tiếp.
5. Theo dõi JFR, thread dump và (nếu có JDK 24+) scheduler metrics trước khi chỉnh properties.

**Tự kiểm tra:**

1. Một virtual thread ngủ/chờ I/O rồi chạy lại trên carrier khác có làm đổi danh tính `Thread.currentThread()` không? **Không.** Danh tính thread logic vẫn là virtual thread.
2. Vì sao 1.000 virtual threads parked thường không cần 1.000 carrier? **Vì các virtual threads có thể unmount, nhường carrier cho công việc runnable khác.**
3. Vì sao hàng đợi runnable tăng khi CPU bão hòa? **Vì virtual threads chờ lượt mount/chạy trên số carrier/CPU hữu hạn; thêm tác vụ không tăng năng lực CPU.**
4. Tại sao kết luận “mọi synchronized đều pin” lỗi thời? **JEP 491 trong JDK 24 thay đổi cách virtual threads chờ Java monitor mà không giữ carrier.**

## 10. Tài liệu chính thức để đối chiếu theo phiên bản

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): cơ chế mount/unmount, trường hợp pinning cũ và JFR.
- [Oracle Java 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): hướng dẫn vận hành/adoption và pinning hiện đại.
- [Java 25 — Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): đặc điểm virtual thread và system properties của scheduler.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): nền tảng thiết kế và mô hình M:N.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi Java monitor kể từ JDK 24.
- [Java 25 — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): giám sát scheduler từ JDK 24.

