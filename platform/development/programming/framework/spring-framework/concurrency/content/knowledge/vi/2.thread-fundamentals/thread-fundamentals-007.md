# Chờ tài nguyên khác với sử dụng CPU trong Java và Spring Framework

## 1. Hiểu đúng hai loại thời gian của một luồng

Một luồng (thread) có thể **đang tồn tại, đang giữ chỗ trong một thread pool, nhưng hầu như không tiêu thụ CPU**. Phân biệt điều này là nền tảng để chẩn đoán ứng dụng Java/Spring chậm, cấu hình executor và chọn mô hình đồng thời phù hợp.

- **Sử dụng CPU (CPU work):** luồng được CPU thực thi để tính toán, duyệt dữ liệu, mã hóa, parse JSON, xử lý thuật toán, thực hiện logic nghiệp vụ. Trong khoảng thời gian ấy, luồng cần thời gian xử lý thực sự của một lõi CPU.
- **Chờ tài nguyên (waiting):** luồng chưa thể tiếp tục vì phụ thuộc vào điều kiện bên ngoài: phản hồi mạng/cơ sở dữ liệu, kết nối từ pool, khóa do luồng khác giữ, kết quả từ tác vụ khác, dữ liệu từ hàng đợi hoặc bộ hẹn giờ. Luồng có thể không dùng CPU trong thời gian chờ nhưng vẫn chiếm tài nguyên quản lý, và với blocking platform thread, vẫn chiếm một luồng thực thi của pool.

Ví dụ một yêu cầu HTTP tốn 420 ms:

| Giai đoạn | Thời gian minh họa | Hoạt động chủ yếu |
| --- | ---: | --- |
| Xác thực dữ liệu đầu vào | 15 ms | CPU |
| Chờ lấy kết nối từ connection pool | 80 ms | Chờ |
| Chờ câu SQL và dữ liệu trả về | 270 ms | Chờ |
| Ánh xạ kết quả, tạo JSON | 25 ms | CPU |
| Chờ các tác vụ khác/lịch CPU | 30 ms | Chờ hoặc chưa được chạy |
| **Tổng thời gian phản hồi** | **420 ms** | **CPU thực dùng có thể chỉ khoảng 40 ms** |

Các số trong bảng chỉ để minh họa; thời gian CPU thực còn phụ thuộc driver, kernel, GC và cách đo. Một request chậm **không đồng nghĩa** CPU đang bận. Ngược lại, CPU cao không nhất thiết cho biết luồng đang kẹt mạng.

### Wall-clock time và CPU time

- **Wall-clock time:** thời gian thực trôi qua từ lúc bắt đầu đến lúc kết thúc, đo bằng đồng hồ đơn điệu như `System.nanoTime()` khi cần đo khoảng thời gian.
- **Thread CPU time:** lượng thời gian CPU thực thi mã của luồng (thường gồm user và system CPU time), có thể đo bằng `ThreadMXBean` nếu JVM hỗ trợ.
- **Thời gian chờ/không được chạy:** phần còn lại không thể suy ra chính xác chỉ bằng phép trừ, vì còn có thời gian chờ scheduler, GC/safepoint và sai số đo; muốn phân rã chi tiết cần thêm tracing, JFR hoặc metric.

Với **một luồng** trên một lõi tại một thời điểm, tỷ lệ `CPU time / wall-clock time` là chỉ báo gần đúng: gần 100% gợi ý CPU-bound; rất thấp trong lúc request vẫn lâu gợi ý có chờ hoặc bị mất lượt chạy. Với **toàn tiến trình**, các luồng chạy đồng thời trên nhiều lõi nên tổng CPU time có thể lớn hơn wall-clock time.

## 2. CPU-bound và wait-bound khác nhau ở đâu?

| Tình huống | CPU có bận liên tục? | Luồng Java đồng bộ có bị giữ lại? | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| Nén ảnh, tính hash, vòng lặp xử lý dữ liệu lớn | Thường có | Có, trong lúc tính toán | CPU profile, thuật toán, lõi CPU |
| `Thread.sleep(500)` | Gần như không | Có: luồng ngủ không xử lý việc khác | Tránh dùng sleep để đồng bộ |
| Đọc JDBC/HTTP bằng lời gọi blocking | Thường không trong phần đợi I/O | Có | Latency, timeout, connection pool, downstream |
| Chờ `synchronized` do thread khác giữ | Không trong phần chờ lock | Có | Lock contention, critical section |
| Chờ `BlockingQueue.take()` khi hàng đợi trống | Không | Có | Producer/consumer, tốc độ cấp dữ liệu |
| `CompletableFuture.join()` hoặc `Future.get()` chưa có kết quả | Không trong phần đợi | Có | Dependency, khả năng deadlock/starvation |
| I/O bất đồng bộ thực sự qua event loop | Có CPU khi xử lý callback, không chiếm thread lúc chờ | Thông thường không giữ một thread riêng suốt thời gian I/O | Driver nonblocking, callback, backpressure |

**CPU-bound** là công việc có nút thắt ở tốc độ tính toán: thêm nhiều runnable threads hơn số lõi CPU thường chỉ tăng cạnh tranh và context switch. **Wait-bound/I/O-bound** là công việc có thời gian trì hoãn chủ yếu bởi tài nguyên khác: CPU thấp vẫn có thể có throughput thấp, queue dài và timeout. Một request thực tế thường gồm *cả hai pha*; hãy đo từng pha thay vì gán nhãn cả endpoint chỉ dựa vào tên API.

### Chờ không có nghĩa là miễn phí

Với **platform thread**, mỗi lời gọi blocking vẫn giữ một thread cho đến khi tiếp tục hoặc timeout. Nếu có 200 yêu cầu cùng chờ DB và mô hình xử lý dành một thread cho mỗi yêu cầu, có thể có xấp xỉ 200 worker bị chiếm, dù CPU còn rảnh. Chúng vẫn tạo áp lực lên stack memory, thread pool, connection pool, bộ nhớ request và khả năng tiếp nhận việc mới.

Điều kiện chờ lâu có thể đến từ chính hệ thống: pool kết nối quá nhỏ, tài nguyên DB cạn, mutex tranh chấp, hoặc một luồng giữ khóa quá lâu. Tăng số thread thường **không chữa được** nút thắt này và còn làm tăng tải lên downstream.

## 3. Java Thread.State cho biết điều gì, và không cho biết điều gì?

`Thread.State` là ảnh chụp trạng thái ở tầng Java, **không phải đồng hồ CPU** hay bản phân loại chính xác mọi loại I/O:

| State | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| `NEW` | Đã tạo nhưng chưa start | `new Thread(...)` |
| `RUNNABLE` | Đang chạy hoặc đủ điều kiện chạy theo mô hình JVM | Vòng lặp CPU; đôi lúc cả blocking native I/O |
| `BLOCKED` | Đang chờ vào monitor của `synchronized` | Luồng khác đang giữ cùng monitor |
| `WAITING` | Chờ vô hạn đến khi được đánh thức/đủ điều kiện | `Object.wait()`, `Thread.join()`, một số `park()` |
| `TIMED_WAITING` | Chờ có thời hạn | `Thread.sleep(...)`, `wait(timeout)`, `join(timeout)` |
| `TERMINATED` | Đã kết thúc thực thi | Hàm `run()` đã trả về |

Ba điểm dễ hiểu sai:

1. `RUNNABLE` **không chứng minh** thread đang dùng CPU. Luồng có thể chỉ đủ điều kiện được chạy, đang đợi scheduler, hoặc đang ở một lời gọi native I/O mà JVM vẫn báo RUNNABLE.
2. `BLOCKED` trong `Thread.State` nói riêng về chờ **intrinsic monitor** (`synchronized`). Chờ khóa `ReentrantLock`, `Condition` hoặc `LockSupport.park()` có thể xuất hiện là `WAITING/TIMED_WAITING`.
3. `WAITING` chưa cho biết chờ đó hợp lý hay bất thường. Consumer đợi dữ liệu có thể bình thường; một `join()` không bao giờ kết thúc hoặc deadlock thì là lỗi. Cần đọc stack trace, owner của lock và ngữ cảnh nghiệp vụ.

`Thread.sleep()` không nhả monitor đang giữ trong khối `synchronized`; `Object.wait()` thì nhả monitor tương ứng khi chờ và phải gọi khi đang sở hữu monitor. Vì thế ngủ trong critical section có thể khiến nhiều thread khác `BLOCKED` dù thread giữ khóa không dùng CPU.

Khi đọc thread dump, hãy đặt câu hỏi **“đang chờ cái gì, chờ ai, bao lâu và có tiến triển không?”** thay vì kết luận từ một trạng thái đơn lẻ.

## 4. Thực nghiệm Java 21: cùng thời gian trôi qua, CPU khác nhau

Đo hai công việc đều kéo dài khoảng 300 ms: một vòng tính toán liên tục, một lời gọi ngủ. Chương trình độc lập sau chạy được với JDK 21; `ThreadMXBean` lấy CPU time của platform thread đang chạy `main`.

**Tệp `ThreadCostDemo.java`:**

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.TimeUnit;

public class ThreadCostDemo {
    private static final ThreadMXBean MX =
            ManagementFactory.getThreadMXBean();
    private static volatile long sink;

    @FunctionalInterface
    interface Work {
        void run() throws InterruptedException;
    }

    private static void cpuWork() {
        long until = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(300);
        long sum = 0;
        while (System.nanoTime() < until) {
            sum += System.nanoTime() & 1L;
        }
        sink = sum; // Giữ kết quả để JIT không loại bỏ toàn bộ tính toán.
    }

    private static void measure(String name, Work task)
            throws InterruptedException {
        long beforeCpu = MX.getCurrentThreadCpuTime();
        long beforeWall = System.nanoTime();

        task.run();

        long wallNs = System.nanoTime() - beforeWall;
        long cpuNs = MX.getCurrentThreadCpuTime() - beforeCpu;
        System.out.printf(
                "%s: wall=%d ms, cpu=%d ms%n",
                name,
                TimeUnit.NANOSECONDS.toMillis(wallNs),
                TimeUnit.NANOSECONDS.toMillis(cpuNs));
    }

    public static void main(String[] args)
            throws InterruptedException {
        if (!MX.isCurrentThreadCpuTimeSupported()) {
            System.out.println("JVM khong ho tro thread CPU time.");
            return;
        }
        if (!MX.isThreadCpuTimeEnabled()) {
            MX.setThreadCpuTimeEnabled(true);
        }

        measure("CPU work", ThreadCostDemo::cpuWork);
        measure("Sleep", () -> Thread.sleep(300));
    }
}
```

Chạy:

```bash
javac ThreadCostDemo.java
java ThreadCostDemo
```

Kết quả **không cố định**: cả hai dòng thường có `wall` ít nhất xấp xỉ 300 ms; `CPU work` có `cpu` lớn hơn đáng kể `Sleep`, còn `Sleep` chỉ tiêu thụ một lượng CPU rất nhỏ. Nhiễu từ scheduler, JIT, GC và tải của máy làm số thực tế khác nhau. Trên một số JVM, tính năng CPU time không được hỗ trợ/bị vô hiệu hóa hoặc việc bật tính năng bị giới hạn bởi môi trường. Nếu CPU bị tranh chấp nghiêm trọng, `CPU work` có thể có CPU time thấp hơn nhiều so với wall time; đây cũng là lý do không gán nhãn từ một mẫu đơn lẻ.

**Điều cần rút ra:** hai request cùng chậm 300 ms có thể đòi hỏi tài nguyên CPU rất khác nhau. Trước khi tối ưu, phải xác định hệ thống đang *tính* hay *đợi*.

## 5. Luồng request Spring MVC thường đang chờ ở đâu?

Với cách xử lý đồng bộ thường gặp trong Spring MVC:

```text
HTTP request
  -> servlet container worker
  -> controller -> service
  -> chờ lấy DB connection -> gọi JDBC/HTTP blocking
  -> xử lý kết quả bằng CPU -> ghi response
  -> worker có thể nhận request kế tiếp
```

Trong pha chờ JDBC hoặc HTTP blocking, **thread xử lý request bị chiếm nhưng CPU không cần bận liên tục**. Khi lượng request đồng thời vượt khả năng của worker pool, queue sẽ dài hoặc yêu cầu bị từ chối/timeout, dù mức dùng CPU tổng thể còn thấp.

Cần phân biệt các điểm chờ:

- **Chờ connection pool:** request chưa có connection để gửi SQL; xem số kết nối active/idle/pending và giới hạn pool.
- **Chờ database:** đã gửi query nhưng server DB chậm, lock bảng, query thiếu index hoặc mạng có độ trễ.
- **Chờ HTTP downstream:** service khác đang xử lý chậm hoặc timeout quá dài.
- **Chờ đồng bộ:** một lock hoặc `Future.get()` khiến thread bị giữ; đôi lúc có deadlock hoặc thread-pool starvation.
- **Bận CPU trong ứng dụng:** mapping object lớn, serialize JSON, regex phức tạp, nén/mã hóa hoặc thuật toán không hiệu quả.

### `@Async` không tự biến blocking I/O thành nonblocking I/O

Khi một lời gọi được Spring proxy xử lý qua `@Async` và executor được cấu hình, công việc chạy trên worker khác. Thread gọi có thể được giải phóng sớm, nhưng **worker thực hiện blocking JDBC/HTTP vẫn bị chiếm suốt thời gian chờ**.

Nếu thread gọi lập tức `future.get()`/`join()`, nó lại chặn chính mình. Gọi một method `@Async` qua `this.method()` trong cùng bean thường không đi qua Spring proxy nên không có tác dụng bất đồng bộ mặc định. Cần kiểm tra ranh giới proxy, executor thật, queue, cách xử lý exception và cách truyền kết quả.

Với Spring MVC async request như `Callable`/`DeferredResult`, servlet request thread có thể được trả lại container trong thời gian xử lý bất đồng bộ; tuy nhiên một lời gọi I/O blocking được đưa sang executor khác **vẫn chiếm thread của executor đó**. Giải phóng request thread và không dùng thread để chờ I/O là hai tính chất khác nhau.

## 6. Blocking, nonblocking và virtual threads giải quyết những việc khác nhau

### Blocking platform threads

Phong cách tuần tự, dễ đọc: gọi API, đứng chờ kết quả rồi chạy tiếp. Phù hợp khi concurrency vừa phải, thư viện chủ yếu blocking và giới hạn executor/connection pool rõ ràng. Điểm yếu là một số lượng lớn lời gọi I/O chậm sẽ giữ rất nhiều platform threads.

### Nonblocking I/O và Spring WebFlux

Event loop khởi tạo tác vụ I/O rồi xử lý tác vụ khác trong khi chờ dữ liệu; kết quả trở lại qua callback/reactive signal. Mô hình này có thể duy trì nhiều kết nối đồng thời mà không cần một platform thread đứng chờ cho mỗi kết nối, **nếu toàn bộ đường I/O quan trọng đều nonblocking**.

Trong Spring WebFlux, không gọi `Thread.sleep()`, JDBC blocking hoặc `block()` trên event-loop thread. Nếu phải tích hợp thư viện blocking, có thể *chuyển* lời gọi sang scheduler thích hợp:

```java
// Đoạn minh họa bên trong một bean dùng Project Reactor.
Mono<String> loadLegacy() {
    return Mono.fromCallable(() -> {
        Thread.sleep(200); // Mô phỏng API blocking cũ.
        return "data";
    }).subscribeOn(Schedulers.boundedElastic());
}
```

Đoạn trên cần import `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers` trong một class Spring/Reactor; đây là minh họa, **không phải chương trình Java chạy độc lập**. `boundedElastic()` chuyển việc blocking sang nhóm worker có giới hạn; **không làm bản thân `Thread.sleep` trở thành nonblocking**. Nếu có quá nhiều tác vụ, queue và giới hạn concurrency của scheduler vẫn là nút thắt. Không đặt việc CPU nặng kéo dài lên event loop.

### Virtual threads (Java 21+)

Virtual threads cho phép mã có cú pháp blocking tuần tự nhưng khi gặp nhiều thao tác chờ có hỗ trợ, virtual thread có thể được **unmount** khỏi carrier platform thread để carrier chạy việc khác. Điều này giảm chi phí giữ một platform thread cho mỗi thao tác chờ và có lợi cho lượng lớn tác vụ I/O đồng thời.

Tuy nhiên, virtual threads **không làm CPU xử lý nhanh hơn**, không bỏ qua giới hạn DB/HTTP connection pool và không tự sửa timeout hoặc truy vấn chậm. Trên Java 21, một số tình huống như blocking khi đang giữ monitor `synchronized` có thể *pin* virtual thread vào carrier; hãy dùng JFR/diagnostics để phát hiện và đánh giá trường hợp thực tế. Trạng thái/tính khả dụng của CPU-time monitoring cũng có thể khác với platform thread.

Cả ba lựa chọn đều cần giới hạn downstream, timeout, cancellation và đo thực tế; lựa chọn phụ thuộc thư viện I/O, lưu lượng đồng thời, đặc điểm deploy và mô hình lập trình.

## 7. Thread pool: tại sao tăng số thread không phải câu trả lời mặc định?

Với CPU-bound work, số tác vụ thực sự chạy song song thường bị giới hạn bởi **số lõi CPU hiệu dụng**; pool quá lớn tăng scheduling overhead và tranh chấp bộ nhớ/cache.

Với wait-heavy work, nhiều concurrency hơn *có thể* che giấu latency I/O: trong khi task A đợi, task B có thể chạy. Một phép ước lượng kinh điển cho số worker là `N ≈ số lõi × (1 + W/C)`, với `W` là thời gian chờ và `C` là CPU time của mỗi task. Đây chỉ là mô hình tham khảo khi tải ổn định, không phải công thức cấu hình trực tiếp: phải xét CPU quota container, giới hạn kết nối DB, timeout, queue và memory.

Ví dụ hệ thống nhận ổn định 200 request/s, mỗi request có trung bình 250 ms chờ I/O. Theo định luật Little, trung bình riêng pha này có khoảng `200 × 0,25 = 50` request đồng thời đang chờ. Trong mô hình đồng bộ một request giữ một worker suốt pha này, chỉ riêng chờ I/O có thể chiếm khoảng 50 workers. Trong mô hình nonblocking, vẫn có khoảng 50 request đang chờ, nhưng không nhất thiết 50 platform threads phải chờ cùng chúng.

Khi cấu hình `ThreadPoolTaskExecutor`, servlet pool, Reactor scheduler hoặc virtual-thread executor, hãy xem đồng thời:

- **Active threads, queue depth, rejection và saturation:** pool đang thật sự thiếu worker hay task đang mắc kẹt ở dependency?
- **Số kết nối DB/HTTP và latency downstream:** tăng worker có đẩy nhiều yêu cầu hơn vào một dependency vốn đã quá tải không?
- **Timeout và cancellation:** task có cơ chế thoát khi nguồn không phản hồi hay cứ chiếm chỗ vô hạn?
- **Backpressure và concurrency limit:** hệ thống có điều tiết công việc trước khi queue/phân bổ bộ nhớ tăng không?
- **CPU throttling trong container:** mức CPU nhìn từ hệ điều hành host có thể đánh lừa khi container bị giới hạn quota.

Tách biệt pool cho công việc dài/chờ nhiều và công việc nhạy latency khi cần; không dùng một shared executor vô hạn khiến một loại công việc làm nghẽn toàn ứng dụng.

## 8. Cách chẩn đoán khi ứng dụng chậm nhưng CPU thấp

1. **Định nghĩa triệu chứng:** đo throughput, p50/p95/p99 latency, số request đang thực hiện, timeout, error/rejection. CPU thấp chỉ là dấu hiệu, không phải chẩn đoán.
2. **Đo khoảng thời gian từng dependency:** DB connection acquire, SQL execute, HTTP call, lock wait, xử lý CPU và queue executor. Dùng trace/span và metric với cùng correlation id khi có thể.
3. **Xem thread dump theo thời gian:** chạy `jcmd <PID> Thread.print -l` bằng JDK và lấy nhiều mẫu cách nhau một khoảng phù hợp. Tập trung vào stack trace lặp lại, thread giữ lock, `WAITING/BLOCKED`, tên executor; nhớ rằng `RUNNABLE` không chắc đang tốn CPU.
4. **Đo bằng profiler/JFR:** CPU samples giải thích thời gian tính toán; event như `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead`, `jdk.FileRead` (tùy cấu hình thu thập) giúp thấy một số nguồn chờ. Đối chiếu với metric connection pool, DB và downstream.
5. **Kiểm tra môi trường:** CPU quota/throttling, GC pauses, thread creation, socket timeout, scheduler/connection limits. Tái kiểm tra dưới tải đủ đại diện trước và sau thay đổi.

Một phép đo hữu ích là **độ trễ tăng mà CPU không tăng tương ứng**: ưu tiên điều tra chờ connection, lock, DB, mạng và hàng đợi. Nếu **CPU bão hòa, nhiều threads RUNNABLE và CPU profile tập trung ở cùng hàm**, ưu tiên phân tích thuật toán, work per request, số lõi CPU và mức song song.

Thread dump đơn lẻ có thể bị lệch bởi thời điểm sampling. Cần nhiều mẫu, stack trace và metric theo thời gian trước khi kết luận có deadlock hoặc bottleneck.

## 9. Những lỗi phổ biến cần tránh

- **Nhầm blocking với busy CPU:** `Thread.sleep`/`Future.get` có thể làm request chậm nhưng hầu như không tiêu CPU; busy spin ngược lại liên tục chiếm CPU dù “đang chờ cờ”.
- **Busy-wait thay vì đợi có điều kiện:** `while (!done) { }` vừa đốt CPU vừa có vấn đề visibility nếu `done` không đồng bộ đúng. Dùng `CountDownLatch`, `BlockingQueue`, `Condition`, `CompletableFuture` hoặc cơ chế async phù hợp; nếu dùng cờ giữa luồng phải hiểu `volatile`/happens-before.
- **Dùng `Thread.sleep` để đồng bộ:** ngủ một thời gian không đảm bảo task khác đã xong; nên chờ sự kiện/kết quả thực sự, kèm timeout.
- **Tưởng `@Async` hoặc `CompletableFuture` mặc nhiên nonblocking:** bất đồng bộ ở phía caller không làm lời gọi JDBC/HTTP blocking biến mất; `join/get` vẫn chặn thread gọi.
- **Cho blocking task vào event loop:** một thao tác chờ kéo dài có thể chặn tiến trình xử lý nhiều kết nối khác trên cùng loop.
- **Tăng pool để chữa DB chậm:** dễ tạo thêm queue, lock contention và timeout ở downstream.
- **Thiếu timeout/cancellation và xử lý interrupt:** task mắc kẹt vô hạn có thể làm cạn thread. Khi bắt `InterruptedException` mà không truyền tiếp, phải cân nhắc phục hồi interrupt flag bằng `Thread.currentThread().interrupt()` theo hợp đồng của phương thức.
- **Chỉ nhìn CPU tổng hoặc chỉ nhìn `Thread.State`:** CPU thấp không chứng minh hệ thống khỏe, và RUNNABLE không chứng minh tiêu thụ CPU; cần các phép đo bổ sung.

## 10. Vận dụng khi thiết kế tính năng Spring

Trước một tác vụ mới, trả lời theo thứ tự:

1. **Tác vụ chủ yếu tính toán hay chờ dependency?** Xác định bằng profiler, tracing, dữ liệu tải và tỷ lệ CPU/wall time, không dựa vào tên method.
2. **Trong lúc chờ, thread nào đang bị giữ?** Servlet worker, thread của `@Async` executor, Reactor scheduler, hay virtual thread? Có làm nghẽn tác vụ khác cùng pool không?
3. **Tài nguyên nào thực sự giới hạn throughput?** CPU, DB connection, giới hạn đối tác, lock, memory hay queue?
4. **Có thể bỏ chờ blocking ở đúng tầng I/O không?** Chỉ dùng nonblocking nếu driver/client hỗ trợ; nếu vẫn dùng blocking, chọn bounded executor hoặc virtual threads với giới hạn phù hợp.
5. **Làm sao biết thay đổi đã hiệu quả?** So sánh throughput, latency theo phân vị, CPU time, số workers đang bận, queue, thời gian chờ lock/I/O và tỷ lệ timeout dưới cùng kịch bản tải.

**Thông điệp cốt lõi:** một luồng đang chờ không tương đương một luồng đang tính toán. Giải pháp cho bottleneck CPU là giảm hoặc phân phối tính toán; giải pháp cho chờ tài nguyên là tìm đúng dependency, giới hạn concurrency, thiết lập timeout, chọn mô hình I/O phù hợp và quan sát được thời gian chờ.