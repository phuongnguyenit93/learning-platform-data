# Virtual Threads và Platform Threads trong Java: khác biệt và cách lựa chọn

> Phạm vi: cơ chế luồng của Java nói chung, tập trung vào Java 21 trở lên. Virtual Threads là tính năng chính thức từ **Java 21** (JEP 444). Các ví dụ bên dưới dùng API chuẩn của JDK, không phụ thuộc framework.

## 1. Bản chất: hai loại `Thread`, hai cách dùng tài nguyên

Trong Java, `Thread` biểu diễn một luồng thực thi: có stack, trạng thái, quyền bị ngắt và danh tính riêng. Từ Java 21 có hai loại:

- **Platform thread**: một `java.lang.Thread` được JVM gắn với một luồng hệ điều hành (OS thread) trong suốt vòng đời. Hệ điều hành lập lịch thực thi luồng đó. Tạo nhiều platform thread tiêu tốn stack native và tài nguyên kernel; số lượng thực tế bị giới hạn khá sớm.
- **Virtual thread**: vẫn là `java.lang.Thread`, nhưng JVM quản lý việc thực thi và lưu/khôi phục trạng thái khi luồng chờ. Virtual thread chỉ **tạm thời chạy trên** một platform thread gọi là **carrier thread**. Nhiều virtual thread có thể lần lượt dùng một số lượng carrier nhỏ, nên phù hợp với lượng lớn tác vụ chờ I/O.

Cả hai vẫn dùng mô hình mã tuần tự quen thuộc: gọi hàm, `try/catch/finally`, `ThreadLocal`, `interrupt()`, `join()`, lock, và các API `java.util.concurrent`. Virtual thread không có CPU riêng, cũng không khiến một công việc tính toán thuần CPU tự chạy nhanh hơn.

### Hình dung lập lịch

```text
Platform threads (thường 1:1):
Task A -> Java platform thread A -> OS thread A
Task B -> Java platform thread B -> OS thread B
Task C -> Java platform thread C -> OS thread C

Virtual threads (nhiều tác vụ chia sẻ carriers):
Task A -> virtual thread A --mount--> carrier 1 -> OS thread 1
          khi chờ I/O --unmount--> carrier 1 rảnh
Task B -> virtual thread B --mount--> carrier 1 -> OS thread 1
Task C -> virtual thread C --mount--> carrier 2 -> OS thread 2
```

**Mount**: JVM cho virtual thread tiếp tục chạy trên một carrier. **Unmount**: virtual thread tạm ngừng, lưu trạng thái tiếp tục và nhường carrier để tác vụ khác chạy; điều này thường xảy ra với thao tác chờ được JDK hỗ trợ, ví dụ nhiều thao tác I/O blocking và `Thread.sleep`. Khi I/O sẵn sàng, virtual thread được đưa vào lịch chạy lại, có thể trên carrier khác.

Vì vậy, một virtual thread **không có quan hệ 1:1 cố định** với một OS thread. Carrier vẫn là platform thread có thật, và các tác vụ đang chạy Java code vẫn cạnh tranh CPU như bình thường.

## 2. Bảng so sánh các điểm cần nhớ

| Tiêu chí | Platform thread | Virtual thread |
|---|---|---|
| Ai lập lịch? | OS lập lịch OS thread tương ứng | JVM lập lịch virtual thread lên carrier; OS vẫn lập lịch carrier |
| Gắn với OS thread | Thường giữ OS thread trong suốt vòng đời | Chỉ gắn carrier khi đang được thực thi; có thể unmount khi chờ |
| Chi phí tạo và duy trì | Tương đối cao: native stack, OS resources | Thấp hơn nhiều cho tác vụ chủ yếu chờ; stack/continuation do JVM quản lý |
| Quy mô thực tế | Thường hàng chục/hàng trăm hoặc vài nghìn tùy môi trường | Có thể hàng chục nghìn đến nhiều hơn khi tài nguyên và workload cho phép |
| `Thread.sleep`, I/O blocking | OS thread thường cũng bị chiếm trong lúc chờ | Với thao tác hỗ trợ unmount, carrier có thể phục vụ việc khác |
| Công việc CPU-bound | Phù hợp nếu số luồng chạy song song được giới hạn hợp lý | Không tăng số lõi CPU hay tăng throughput phép tính |
| Quản lý vòng đời | Thường dùng `newFixedThreadPool` / `newCachedThreadPool` để tái dùng | Tạo một virtual thread cho mỗi tác vụ; **không pool virtual threads** |
| Mức độ tương thích | `Thread` và `java.util.concurrent` | Cũng là `Thread` và hỗ trợ hầu hết API hiện có; kiểm tra giới hạn của thư viện/native call |
| `ThreadLocal` | Có; dễ tái dùng trong pooled threads | Có; nhưng nhiều tác vụ = nhiều bản sao state, dễ đội bộ nhớ nếu cache lớn |
| Daemon | Có thể daemon hoặc non-daemon | Luôn là daemon; không tự giữ JVM sống |
| Chặn do lock/native | Có thể block OS thread | Có thể bị **pinning** hoặc block carrier tùy thao tác và phiên bản JDK |
| Mục tiêu | Số luồng hợp lý, CPU tasks, xử lý nền lâu sống | Nhiều tác vụ độc lập, phần lớn thời gian chờ I/O |

“Virtual thread nhẹ” là nhận xét tương đối, **không đồng nghĩa miễn phí**: mỗi virtual thread vẫn giữ object, stack frame/state, `ThreadLocal` và tài nguyên mà tác vụ sử dụng. Không thể suy ra một ngưỡng số luồng cố định cho mọi máy.

## 3. Ví dụ chạy được: kiểm tra hai loại thread

Tạo tệp **`VirtualVsPlatform.java`**:

```java
public class VirtualVsPlatform {
    public static void main(String[] args) throws InterruptedException {
        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .unstarted(() -> { });

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .unstarted(() -> { });

        platform.start();
        virtual.start();

        platform.join();
        virtual.join();

        System.out.println("platform.isVirtual() = " + platform.isVirtual());
        System.out.println("virtual.isVirtual() = " + virtual.isVirtual());
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac VirtualVsPlatform.java
java VirtualVsPlatform
```

Kết quả chính xác:

```text
platform.isVirtual() = false
virtual.isVirtual() = true
```

`Thread.ofPlatform()` / `Thread.ofVirtual()` tạo builder; `unstarted(...)` tạo luồng chưa khởi chạy; `start()` mới bắt đầu thực thi. Gọi `join()` để bảo đảm luồng kết thúc trước khi in kết quả. `isVirtual()` kiểm tra loại, không phụ thuộc tên thread. Cách ngắn gọn khác là `Thread.startVirtualThread(runnable)`: vừa tạo vừa khởi chạy virtual thread.

**Không nhầm:** virtual thread không phải `CompletableFuture`, cũng không phải object của executor. Executor là cơ chế nhận và quản lý task; task được executor có thể thực thi trên loại thread tương ứng.

## 4. Chờ I/O: tại sao virtual threads có thể tăng throughput

Giả sử mỗi yêu cầu cần khoảng 20 ms làm việc trên CPU và 180 ms chờ một dịch vụ mạng. Một platform thread xử lý tuần tự từng yêu cầu sẽ bị chiếm cả 200 ms. Nếu dùng 100 platform threads, phần lớn thời gian nhiều OS threads đang chờ. Với virtual threads, khi chờ I/O tương thích, carrier có thể nhận task khác, giúp phục vụ nhiều yêu cầu đồng thời mà không cần một OS thread cho mỗi request.

Đây là **lợi ích về khả năng phục vụ nhiều tác vụ đồng thời (scalability/throughput)**; không bảo đảm một request đơn lẻ có latency thấp hơn. Tổng năng lực còn bị giới hạn bởi CPU, database connections, socket/file descriptor, rate limit, remote service và bộ nhớ.

Có thể dùng quy tắc xấp xỉ `L = λ × W` (Little's Law) để hình dung: nếu dòng công việc ổn định đạt 1.000 yêu cầu/giây và mỗi yêu cầu ở trong hệ thống 0,2 giây, trung bình sẽ có khoảng 200 yêu cầu đang xử lý/chờ. Đây là phép tính công suất/độ đồng thời, **không phải phép dự đoán** rằng cứ tạo 200 virtual threads là sẽ đạt 1.000 req/s.

Tác vụ phù hợp: gọi HTTP/database, giao tiếp socket, pipeline đọc kết quả từ nhiều nguồn, hoặc xử lý yêu cầu dạng “mỗi yêu cầu là một flow tuần tự” mà phần lớn thời gian đợi kết quả.

Tác vụ không tự hưởng lợi: nén/giải mã/tính toán số lớn, tính toán ma trận hay vòng lặp CPU-bound thuần túy. Nếu có 8 lõi CPU, 100.000 virtual threads cùng tính toán không biến 8 lõi thành 100.000 lõi; cạnh tranh CPU và scheduler overhead vẫn có.

## 5. Ví dụ chạy được: một virtual thread cho mỗi task

Tạo tệp **`VirtualTaskExecutor.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualTaskExecutor {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Mô phỏng thời gian chờ
                    return "task-" + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Đọc theo thứ tự submit, không phụ thuộc thứ tự hoàn thành.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
```

Chạy:

```bash
javac VirtualTaskExecutor.java
java VirtualTaskExecutor
```

Kết quả chính xác:

```text
task-1: virtual=true
task-2: virtual=true
task-3: virtual=true
```

Mỗi lần `submit` sẽ chạy task bằng một **virtual thread mới**, không giữ sẵn một pool virtual threads để tái dùng. `Future.get()` đợi kết quả hoặc ném lỗi nếu task thất bại; lấy theo thứ tự danh sách khiến phần in ra xác định dù thứ tự scheduler không xác định. `try-with-resources` gọi `ExecutorService.close()`, chờ các task đã gửi kết thúc theo hợp đồng của API.

`Thread.sleep(100)` chỉ mô phỏng “đang chờ” để nhìn rõ mô hình; thời gian chạy thực tế phụ thuộc máy và lập lịch. Trong chương trình thực, phần lớn lợi ích phát sinh từ **I/O blocking tương thích** như network I/O, không phải vì thêm sleep vào code làm ứng dụng nhanh hơn.

### Cùng kiểu công việc nếu dùng platform thread pool

```java
// Đoạn minh họa: các import và main nằm trong ví dụ bên trên.
try (ExecutorService executor = Executors.newFixedThreadPool(3)) {
    // 3 platform worker threads được tái dùng cho các task.
    // Task vượt quá số worker được đưa vào hàng đợi.
}
```

Pool platform threads hữu ích khi muốn giới hạn số worker tốn tài nguyên hoặc số task CPU thực thi song song. Với `newVirtualThreadPerTaskExecutor()`, số virtual threads theo số task được gửi, **không áp dụng giới hạn 3 workers như pool trên**. Do đó phải giới hạn tài nguyên downstream riêng.

## 6. Không pool virtual threads; giới hạn tài nguyên đúng chỗ

Sai lầm phổ biến là coi giới hạn kích thước platform pool là giới hạn nghiệp vụ rồi chuyển sang virtual threads và để mọi task cùng mở kết nối bên ngoài. Virtual threads không làm database, HTTP server hay disk nhanh thêm. Nếu hệ thống chỉ cho phép 10 kết nối hoặc tối đa 10 request đồng thời, ta cần giữ giới hạn đó.

Dùng `Semaphore` để giới hạn truy cập tài nguyên cụ thể. Ví dụ sau là **đoạn minh họa bên trong một phương thức**; `callRemoteService()` đại diện cho lời gọi I/O thật:

```java
Semaphore permits = new Semaphore(10); // Khởi tạo và dùng chung giữa các task

void limitedCall() throws InterruptedException {
    permits.acquire();                 // Chờ tới khi có permit
    try {
        callRemoteService();           // Có nhiều nhất 10 lời gọi cùng vào đây
    } finally {
        permits.release();             // Không rò permit khi có exception
    }
}
```

Trong mã thật cần `import java.util.concurrent.Semaphore;` và định nghĩa `callRemoteService()`; đoạn trên **không phải một lớp biên dịch độc lập**. Nếu `acquire()` bị interrupt thì chưa lấy permit, do đó nằm **ngoài** `try/finally` giải phóng. Không dùng số virtual threads để thay thế giới hạn connection pool hoặc rate limit vốn đã có. Đối với công việc CPU-bound, dùng executor bị giới hạn mức song song phù hợp với CPU thay vì vô hạn task đồng thời.

## 7. Virtual thread blocking khác gì pinning?

**Blocking thông thường:** virtual thread đợi thao tác mà JVM/JDK có thể unmount; carrier được trả về cho scheduler. Ví dụ `Thread.sleep(...)` hoặc nhiều thao tác chờ I/O mạng do JDK hỗ trợ.

**Pinning:** virtual thread vẫn bám trên carrier trong lúc không thể unmount; nếu cùng lúc thực hiện một thao tác chờ dài, OS thread carrier cũng bị chiếm. Khi pinning xảy ra thường xuyên, nhiều carrier bị giữ và ưu thế mở rộng có thể giảm. Pinning không tự làm kết quả tính toán sai.

Phải **phân biệt theo phiên bản JDK**:

- **JDK 21–23:** thực hiện blocking trong `synchronized` block/method có thể pin carrier; các lời gọi native/foreign cũng có thể pin. Chỉ nên thay `synchronized` bằng `ReentrantLock` tại các đoạn **blocking lâu hoặc lặp lại nhiều** khi đã quan sát thấy bottleneck; không cần thay mọi synchronized bảo vệ cập nhật bộ nhớ rất ngắn.
- **JDK 24+ (JEP 491):** JVM đã thay đổi monitor implementation để virtual thread có thể chờ/đi qua `synchronized` mà không bị pin chỉ vì monitor. Vì thế câu “mọi synchronized đều pin virtual thread” **không còn đúng** trên các JDK mới. Một số trường hợp liên quan native/foreign hoặc thao tác runtime đặc biệt vẫn cần kiểm tra thực tế.

Hãy đo trên **phiên bản JDK triển khai thật**, dùng JDK Flight Recorder (JFR) và sự kiện `jdk.VirtualThreadPinned` khi phù hợp, đồng thời theo dõi throughput, latency, CPU, carriers và giới hạn kết nối. Đừng kết luận pinning chỉ từ việc thấy lock hay thời gian chờ. Khi nâng cấp JDK, đánh giá lại workaround cũ dựa trên đo lường.

## 8. Những đặc tính `Thread` vẫn phải quản lý

**Interrupt và hủy:** virtual thread hỗ trợ `interrupt()` như platform thread. Blocking APIs như `Thread.sleep` có thể ném `InterruptedException`. Nếu một hàm không thể xử lý ngay, thường cần truyền tiếp exception hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()`; đừng nuốt tín hiệu hủy rồi tiếp tục vô thời hạn. `Future.cancel(true)` yêu cầu ngắt task khi phù hợp, không bảo đảm một lời gọi I/O tùy ý có thể dừng tức thì.

**Lỗi task:** exception trong `Runnable` có thể được báo qua `UncaughtExceptionHandler`; với `ExecutorService.submit`, lỗi task nằm trong `Future` và `get()` có thể ném `ExecutionException`. Luôn có chiến lược timeout/hủy và xử lý thất bại phù hợp với nghiệp vụ; virtual thread không tự sinh retry hoặc timeout.

**ThreadLocal:** mỗi virtual thread có vùng dữ liệu ThreadLocal riêng; API này vẫn hoạt động. Nhưng mô hình “mỗi task tạo một virtual thread mới” khiến dữ liệu cache đắt tiền trong ThreadLocal thường bị tạo lại cho từng task; số lượng task lớn có thể tăng bộ nhớ/GC. Dùng tham số truyền rõ ràng khi thuận tiện; kiểm tra các thư viện dựa vào ThreadLocal và tránh giữ đối tượng lớn không cần thiết.

**Daemon và vòng đời JVM:** virtual threads luôn là daemon. Một JVM chỉ còn virtual threads đang chạy có thể kết thúc khi tất cả non-daemon threads đã xong. Với ví dụ tự viết, dùng `join()`, `Future.get()` hoặc quản lý vòng đời executor để đợi tác vụ quan trọng; đừng giả định virtual thread sẽ tự giữ process sống.

**Dùng chung dữ liệu:** virtual thread không loại bỏ race condition, deadlock, data race hay vấn đề visibility. Các nguyên tắc `volatile`, `synchronized`, lock, atomics, thread-safe collection và happens-before vẫn giữ nguyên. Ít OS threads hơn không có nghĩa shared mutable state an toàn hơn.

**Tác vụ rất dài hoặc giới hạn ở thư viện:** virtual threads thường phù hợp các công việc có thời hạn rõ ràng, xử lý một request/task rồi kết thúc. Không phải tất cả native calls, driver, thư viện bên thứ ba hoặc lời gọi blocking đều unmount giống nhau. Cần thử nghiệm chính workload và JDK được triển khai.

## 9. Chọn mô hình nào trong thực tế?

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Rất nhiều request độc lập, chủ yếu chờ network/database | Virtual thread cho mỗi request/task | Viết code tuần tự dễ đọc, carrier có thể được tái dùng trong thời gian chờ |
| Công việc CPU-bound liên tục | Platform pool giới hạn theo tài nguyên CPU, hoặc dùng chiến lược parallelism có kiểm soát | Năng lực CPU có giới hạn; virtual thread không tạo thêm lõi |
| Ứng dụng cần tối đa N lời gọi vào một API/database | Virtual threads kèm `Semaphore`/pool kết nối/rate limiter | Giới hạn tài nguyên nghiệp vụ độc lập với loại thread |
| Tác vụ nền lâu sống, cần quản trị số worker rõ ràng | Đánh giá platform threads và executor tương ứng | Thread không nhất thiết nhiều và phải sống lâu |
| Nhiều blocking call nằm trong monitor trên JDK 21–23 | Đo pinning, cải thiện hotspot, cân nhắc JDK 24+ | Tránh giữ carrier quá lâu ở những đường thực thi thường xuyên |
| Đang dùng thư viện có JNI/native blocking | Benchmark và profile thực tế trước khi chuyển | Một số thao tác có thể giữ carrier hoặc chặn tiến độ |

### Checklist chuyển đổi có kiểm soát

1. Xác định workload: tỷ lệ thời gian **CPU** so với **chờ I/O**, số request đồng thời và ràng buộc tài nguyên thực tế.
2. Dùng JDK 21+; thay mô hình platform pool lớn cho I/O bằng `Executors.newVirtualThreadPerTaskExecutor()` khi phù hợp.
3. Giữ timeout, cancellation, rate limit, connection pool và cơ chế shutdown rõ ràng. Nếu cần giới hạn truy cập tài nguyên, chọn `Semaphore` hoặc giới hạn có sẵn của resource pool.
4. Audit `ThreadLocal`, blocking native calls và điểm lock thường xuyên; với JDK 21–23 đặc biệt chú ý blocking trong `synchronized`.
5. Load test cùng một workload trên hai cấu hình, đo **throughput, p95/p99 latency, CPU, bộ nhớ, số kết nối, lỗi/timeouts**; chỉ kết luận khi số liệu và giới hạn bottleneck được xác định.

## 10. Hiểu đúng qua vài câu hỏi tự kiểm tra

- **“Một triệu virtual threads thì một triệu tác vụ chạy CPU đồng thời?”** Không. Tại mỗi thời điểm, những tác vụ đang chạy vẫn cần carrier và CPU thật; nhiều virtual threads có thể ở trạng thái chờ.
- **“Virtual thread luôn nhanh hơn platform thread?”** Không. Virtual threads chủ yếu giúp mở rộng số lượng tác vụ blocking, không cải thiện tốc độ CPU của một task riêng lẻ.
- **“Vẫn phải pool virtual threads để tránh lãng phí?”** Không. Virtual threads được thiết kế để tạo theo từng task; hạn chế downstream bằng resource limit thích hợp.
- **“`synchronized` luôn pin virtual thread?”** Không. Nguy cơ này đặc biệt quan trọng trong JDK 21–23 khi chờ lâu bên trong monitor; JDK 24+ đã xử lý phần lớn vấn đề này qua JEP 491.
- **“Virtual thread loại bỏ nhu cầu đồng bộ, timeout và backpressure?”** Không. Các yêu cầu đó vẫn còn, đôi khi còn quan trọng hơn do số task đồng thời có thể tăng mạnh.

## Tài liệu chính thức để đào sâu

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) — mục tiêu, API và mô hình chính thức của Java 21.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — lập lịch, pinning và hướng dẫn thực hành của bản 21.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — thay đổi về monitor và pinning từ JDK 24.
- [Oracle Java 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html) — góc nhìn tài liệu JDK mới, cần phân biệt với hành vi của JDK 21.

**Ghi nhớ:** Platform thread là luồng JVM gắn chặt với OS thread; virtual thread là luồng Java nhẹ được JVM lên lịch lên carrier theo thời điểm. Chọn virtual threads khi có rất nhiều tác vụ tuần tự độc lập phải chờ I/O, và đo giới hạn thực của hệ thống thay vì suy đoán từ số lượng thread.
