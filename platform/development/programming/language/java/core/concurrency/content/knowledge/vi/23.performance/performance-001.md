# Latency, throughput, utilization và độ ổn định trong Java concurrency

## 1. Bốn góc nhìn khác nhau về hiệu năng

Một chương trình Java chạy đồng thời có thể xử lý nhiều việc, nhưng “nhiều thread” không đồng nghĩa với “nhanh hơn”. Cần phân biệt bốn đại lượng để biết hệ thống đang phản hồi nhanh, xử lý được bao nhiêu công việc, sử dụng tài nguyên ra sao và có giữ được chất lượng theo thời gian hay không.

| Đại lượng | Câu hỏi cần trả lời | Cách đo thường gặp | Rủi ro khi chỉ nhìn một chỉ số |
| --- | --- | --- | --- |
| **Latency (độ trễ)** | Một công việc mất bao lâu từ khi được tiếp nhận đến khi hoàn tất? | ms/request; p50, p95, p99 | Trung bình thấp nhưng một số yêu cầu chờ rất lâu |
| **Throughput (thông lượng)** | Trong một khoảng thời gian, hoàn tất bao nhiêu công việc? | requests/s, tasks/s, MB/s | Số yêu cầu bắt đầu cao nhưng số hoàn tất thấp hoặc lỗi nhiều |
| **Utilization (mức sử dụng)** | Bao nhiêu phần năng lực tài nguyên đang bận? | CPU %, thời gian thread bận, mức đầy pool/queue | 100% không nhất thiết hiệu quả; tài nguyên ít bận cũng có thể đang nghẽn nơi khác |
| **Stability (độ ổn định)** | Chất lượng có được duy trì khi tải kéo dài, dao động hoặc tăng đột biến? | Biến động latency/throughput, lỗi, backlog, thời gian phục hồi | Kết quả tốt trong vài giây nhưng suy giảm sau vài phút |

Các đại lượng phải được đo **trên cùng ranh giới công việc và cùng cửa sổ thời gian**. Ví dụ, throughput của cả ứng dụng không nên so trực tiếp với latency của chỉ một bước truy xuất dữ liệu. Với concurrency, cần xét cả yêu cầu bị từ chối, hết hạn, hủy và thất bại; chỉ đếm yêu cầu thành công sẽ bỏ sót tình trạng quá tải.

## 2. Latency: thời gian hoàn tất một công việc

Với một công việc được gửi vào `ExecutorService`, có thể tách:

`latency tổng = thời gian đợi trong hàng đợi + thời gian chờ được lập lịch + thời gian thực thi + thời gian đợi I/O/khóa + phần xử lý sau cùng`.

Đây là cách phân rã theo ý nghĩa; các pha có thể lồng nhau và không được cộng trùng. Điểm bắt đầu phải rõ ràng: từ thời điểm người dùng gửi yêu cầu, từ lúc ứng dụng nhận yêu cầu, hay từ lúc gọi `executor.execute()`? Nếu chỉ bấm đồng hồ khi `Runnable.run()` bắt đầu, ta **bỏ qua queue wait** và dễ đánh giá hệ thống tốt hơn thực tế.

- **Service time**: thời gian thực sự phục vụ một tác vụ sau khi bắt đầu chạy; có thể bao gồm thời gian chờ I/O nếu định nghĩa ở cấp tác vụ.
- **Queueing time**: thời gian từ lúc nhận/gửi đến khi bắt đầu xử lý; thường tăng rất nhanh gần ngưỡng bão hòa.
- **Response time**: thời gian đầu-cuối tại ranh giới hệ thống đã chọn, thường là thứ người dùng quan tâm.
- **Tail latency**: các yêu cầu chậm ở đuôi phân phối, đặc biệt p95/p99, dễ bị ảnh hưởng bởi tranh chấp khóa, GC, scheduler, tải tăng đột ngột và lời gọi ngoại vi chậm.

Ví dụ 100 yêu cầu có 95 yêu cầu xong trong 20 ms và 5 yêu cầu mất 1.000 ms: phần lớn người dùng cảm nhận rất nhanh, nhưng trung bình là 69 ms; p99 gần 1.000 ms. Một giá trị trung bình duy nhất không diễn tả trải nghiệm ở đuôi. p50 là trung vị; p95/p99 là ngưỡng mà khoảng 95%/99% mẫu không vượt quá theo phương pháp ước lượng đã chọn. Với mẫu nhỏ, percentile có độ nhiễu lớn; cần ghi kích thước mẫu, cửa sổ thời gian và thuật toán thống kê.

Độ trễ cũng có hai nghĩa cần phân biệt: **latency của yêu cầu đã hoàn tất** và **thời gian chờ của yêu cầu vẫn đang tồn đọng**. Nếu chỉ thống kê yêu cầu đã hoàn tất, các yêu cầu treo hoặc timeout có thể bị che giấu. Khi phát tải với công cụ benchmark, tránh *coordinated omission*: công cụ gửi yêu cầu tiếp theo chỉ sau khi yêu cầu trước xong sẽ tự giảm tốc lúc hệ thống chậm, khiến các khoảng trễ do nghẽn bị bỏ qua. Muốn khảo sát tải đến cố định, cần bộ phát tải có lịch gửi độc lập, ghi cả các lần trễ lịch, từ chối và timeout.

## 3. Throughput: số công việc hoàn tất trên một đơn vị thời gian

Công thức cơ bản:

`throughput = số công việc hoàn tất / thời gian quan sát`.

Ví dụ hoàn tất 6.000 tác vụ trong 60 giây tương ứng 100 tasks/s. Phải xác định rõ **hoàn tất** gồm những gì: thành công; lỗi; bị từ chối; hay tất cả các kết quả kết thúc. Thông thường cần theo dõi riêng:

- **Arrival rate (λ)**: số công việc đến mỗi giây.
- **Admission rate**: số công việc được nhận vào xử lý; có thể thấp hơn arrival rate vì giới hạn tải.
- **Completion rate**: số công việc kết thúc mỗi giây, phân tách thành công/lỗi.
- **Backlog**: công việc đã nhận nhưng chưa hoàn tất; bao gồm hàng đợi và đang chạy.

Khi arrival rate liên tục vượt completion rate, backlog tăng. Hàng đợi chưa đầy không chứng minh hệ thống khỏe: nó có thể đang tích lũy và làm latency ngày càng cao. Nếu công việc bị loại bỏ, completion rate của phần được nhận có thể trông tốt trong khi tỷ lệ phục vụ yêu cầu tổng thể lại xấu. Luôn báo cáo cả throughput thành công, tỷ lệ từ chối và tỷ lệ lỗi.

Tăng concurrency giúp throughput khi có thời gian chờ hoặc CPU còn nhàn rỗi. Khi CPU đã bão hòa, tăng thread thường chỉ gây thêm context switch, tranh chấp bộ nhớ/khóa và thời gian xếp hàng. Với tác vụ I/O, số công việc đồng thời có thể lớn hơn số lõi CPU, nhưng giới hạn thực tế thường nằm ở kết nối, bộ nhớ, dịch vụ đích hoặc khả năng chịu tải của tài nguyên chung.

## 4. Utilization: bận đến mức nào, và bận ở đâu?

Có thể hình dung utilization của một tài nguyên là:

`utilization ≈ thời gian tài nguyên bận / tổng thời gian tài nguyên có thể phục vụ`.

Định nghĩa này chỉ có ý nghĩa khi nêu rõ **tài nguyên**: CPU, worker trong thread pool, kết nối, ổ đĩa, hay một lock độc quyền. Những thước đo không được đánh đồng:

| Quan sát | Diễn giải có thể đúng | Cần kiểm tra thêm |
| --- | --- | --- |
| CPU gần 100% | Tác vụ tính toán đã chạm giới hạn CPU | CPU quota/cgroup, GC, profiling, context switching |
| CPU thấp nhưng latency cao | Thread đang BLOCKED/WAITING, đợi I/O, lock hoặc queue | Thread dump, JFR, thời gian queue/lock/I/O |
| `activeCount == maximumPoolSize` | Worker của pool đang bận tại thời điểm lấy mẫu | Pool có chờ I/O không, queue có tăng không, task duration |
| Queue còn dài | Khả năng phục vụ không theo kịp trong giai đoạn đó | Arrival/completion rate, tuổi tác vụ cũ nhất |
| CPU thấp mà throughput thấp | Có thể bị nghẽn tài nguyên ngoài CPU | Giới hạn connection, đồng bộ hóa, rate limit |

Ví dụ một thread giữ lock và thực thi chậm có thể khiến 100 thread khác chờ: CPU không nhất thiết cao nhưng latency rất xấu. Ngược lại, chương trình tính toán độc lập tận dụng tốt các lõi thường có CPU cao và throughput tốt; CPU cao **không tự nó là lỗi**. Trong container, cần tính theo CPU quota được cấp, thay vì mặc định số lõi vật lý của host. Phần trăm CPU trên host và phần trăm trong container có thể khác mẫu số.

`ThreadPoolExecutor.getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()` hữu ích để quan sát xu hướng, nhưng là giá trị xấp xỉ/ảnh chụp trạng thái, không tạo thành phép đo nguyên tử nhất quán. Dùng chúng làm metric giám sát thay vì tiêu chí chính xác tuyệt đối cho logic nghiệp vụ.

## 5. Quan hệ giữa latency, throughput, concurrency và tải

**Little's Law** mô tả một hệ thống ổn định dài hạn:

`L = λ × W`

Trong đó `L` là **số công việc trung bình đang ở trong hệ thống**, `λ` là **throughput dài hạn của hệ thống ổn định** (công việc/giây), `W` là **thời gian trung bình một công việc ở trong hệ thống** (giây). Cần dùng cùng ranh giới cho cả ba. Ví dụ throughput ổn định 200 requests/s và response time trung bình 0,1 s thì trung bình khoảng 20 yêu cầu *in-flight*, gồm cả đang chờ và đang chạy. Không suy ra rằng phải có đúng 20 platform thread hay rằng tăng thread lên 20 sẽ đạt 200 requests/s.

Một xấp xỉ sơ bộ cho `m` worker độc lập, mỗi worker có thời gian phục vụ trung bình `S`, là:

`ρ ≈ λ × S / m`.

Chẳng hạn 4 worker, mỗi công việc cần trung bình 20 ms thời gian chiếm worker, với tải đến 150 tasks/s thì `ρ ≈ 150 × 0,02 / 4 = 0,75`. Đây **chỉ là ước lượng tải** trong mô hình giản lược: thời gian chờ lock/I/O, độ phân tán, burst, công việc khác kích thước và độ lệch giữa worker có thể làm kết quả thực tế khác xa.

Khi `ρ` tiến gần 1, độ trễ hàng đợi thường tăng phi tuyến, nhất là khi thời gian phục vụ biến thiên. Một hệ thống có thể đạt throughput cực đại ở mức tải cao nhưng không đáp ứng mục tiêu p99. Vì vậy “capacity” dùng cho sản phẩm nên là **throughput bền vững thỏa đồng thời giới hạn độ trễ và lỗi**, không chỉ giá trị tasks/s cao nhất trong một phép thử ngắn.

Cần phân biệt các thí nghiệm:

1. **Fixed concurrency / closed-loop**: N client luôn có công việc mới khi công việc cũ hoàn tất; khi server chậm, tốc độ phát tải tự giảm.
2. **Fixed arrival rate / open-loop**: cố gửi theo lịch 100, 200, 300 requests/s; phơi bày queue, timeout và sự quá tải rõ hơn.
3. **Burst test**: cho tải đột biến ngắn rồi quay lại bình thường; đo đỉnh hàng đợi và thời gian phục hồi.
4. **Soak test**: duy trì tải đủ lâu để quan sát heap, GC, thread, connection, tài nguyên rò rỉ và suy giảm theo thời gian.

Không lấy kết quả từ các kiểu thử khác nhau rồi coi là cùng một đặc tính hiệu năng.

## 6. Đo lường trong Java cho đúng

Đo **khoảng thời gian** bằng `System.nanoTime()`; không dùng `System.currentTimeMillis()` cho phép đo ngắn vì đồng hồ thực có thể bị điều chỉnh và độ phân giải không ổn định. `nanoTime()` là đồng hồ đơn điệu thích hợp để tính hiệu giữa hai lần gọi trong cùng JVM, không phải timestamp để lưu hay so sánh giữa các máy.

Khi thu thập metric, đánh dấu tối thiểu các thời điểm: **accepted**, **started**, **finished**. Từ đó tính queue wait = started − accepted và end-to-end latency = finished − accepted. Ghi thêm trạng thái kết thúc (success/error/rejected/timeout/canceled), số đang chạy, độ sâu queue và thời gian chờ lâu nhất. Với công việc nhiều pha, đo riêng đoạn chờ I/O, đoạn giữ lock hoặc đoạn chặn trên primitive đồng bộ khi cần.

Đối với các phiên kiểm thử có vài triệu yêu cầu, đừng tự giữ từng duration trong một `List` vô hạn. Có thể dùng histogram giới hạn bộ nhớ hoặc một thư viện đo metric phù hợp; cần công bố cách lấy mẫu/ước lượng percentile. Ghép percentile từ nhiều nhóm bằng trung bình số học là **sai**: phải gộp phân phối/histogram với cách tính tương thích hoặc tính lại từ mẫu.

### Ví dụ Java 17: executor hữu hạn và đo thời gian chờ

Chương trình sau minh họa tách thời gian đợi khỏi thời gian từ lúc gửi tới lúc hoàn tất. Nó dùng `ThreadPoolExecutor` có 2 platform worker và queue giới hạn 4 phần tử. Khi đầy, `CallerRunsPolicy` cho thread gửi chạy tác vụ, tạo áp lực ngược lên nguồn phát tải. Thời gian `sleep` chỉ mô phỏng việc chờ; đây **không phải benchmark chuẩn hay phép đo capacity sản xuất**.

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public class PerformanceDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 20;
        LongAdder completed = new LongAdder();
        ConcurrentLinkedQueue<Long> queueWaitNanos =
                new ConcurrentLinkedQueue<>();
        ConcurrentLinkedQueue<Long> totalNanos =
                new ConcurrentLinkedQueue<>();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.CallerRunsPolicy());

        long testStarted = System.nanoTime();

        for (int i = 0; i < taskCount; i++) {
            long acceptedAt = System.nanoTime();
            pool.execute(() -> {
                long startedAt = System.nanoTime();
                queueWaitNanos.add(startedAt - acceptedAt);

                try {
                    Thread.sleep(30); // Mô phỏng tác vụ chờ I/O.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    totalNanos.add(System.nanoTime() - acceptedAt);
                    completed.increment();
                }
            });
        }

        pool.shutdown();
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            throw new IllegalStateException("Executor timeout");
        }

        long elapsedNanos = System.nanoTime() - testStarted;
        System.out.println("Completed: " + completed.sum());
        System.out.printf(Locale.ROOT,
                "Observed throughput: %.1f tasks/s%n",
                completed.sum() / (elapsedNanos / 1_000_000_000.0));
        System.out.printf(Locale.ROOT,
                "Average queue wait: %.1f ms%n",
                averageMillis(queueWaitNanos));
        System.out.printf(Locale.ROOT,
                "Average submitted-to-finished: %.1f ms%n",
                averageMillis(totalNanos));
    }

    private static double averageMillis(ConcurrentLinkedQueue<Long> samples) {
        return samples.stream()
                .mapToLong(Long::longValue)
                .average()
                .orElse(0.0) / 1_000_000.0;
    }
}
~~~

Lưu thành `PerformanceDemo.java` và chạy:

~~~bash
javac PerformanceDemo.java
java PerformanceDemo
~~~

Dòng đầu của stdout luôn là `Completed: 20` khi chương trình kết thúc bình thường. Ba số đo tiếp theo **không cố định**, vì phụ thuộc scheduler, trạng thái CPU và máy chạy. Trong ví dụ này, `CallerRunsPolicy` có thể chạy tác vụ ngay trên thread `main`; vì thế throughput được quan sát là của toàn bộ phép thử (kể cả main), không phải chỉ hai worker. Cách này cũng làm tốc độ gửi bị chậm lại khi bão hòa, nên không dùng phép thử này để kết luận ứng dụng chịu được một arrival rate cố định.

Nếu tác vụ có thể thất bại, thay `completed` bằng bộ đếm phân loại kết quả; `finally` ở ví dụ chỉ có nghĩa “đường chạy đã kết thúc”, không khẳng định tác vụ thành công. Nếu công việc bị ngắt, phải xác định chính sách hủy và đếm riêng việc hủy. Nếu gọi `execute()` trong khi pool đã `shutdown()`, `CallerRunsPolicy` không đảm bảo chạy tác vụ đó; thiết kế gửi phải có lifecycle rõ ràng.

### Đọc percentile thay vì chỉ average

Giả sử đã thu được một tập `latenciesNanos` không rỗng từ cùng một cửa sổ quan sát, ví dụ mẫu tải. Một cách ước lượng percentile đơn giản là *nearest rank*:

~~~java
import java.util.List;

public class PercentileExample {
    static long percentile(List<Long> latenciesNanos, double p) {
        if (latenciesNanos.isEmpty() || p <= 0 || p > 1) {
            throw new IllegalArgumentException("Invalid samples or p");
        }
        List<Long> sorted = latenciesNanos.stream().sorted().toList();
        int index = (int) Math.ceil(p * sorted.size()) - 1;
        return sorted.get(index);
    }

    public static void main(String[] args) {
        List<Long> ms = List.of(10L, 12L, 15L, 20L, 100L);
        System.out.println("p95 = " + percentile(ms, 0.95) + " ms");
    }
}
~~~

Lưu là `PercentileExample.java`; `javac PercentileExample.java` rồi `java PercentileExample` cho output `p95 = 100 ms`. Ví dụ truyền millisecond cho hàm có tên `latenciesNanos` để minh họa thứ tự thống kê; hàm **trả về cùng đơn vị mà input sử dụng**. Trong hệ thống thực, thống nhất nanos ở tầng đo rồi đổi sang ms khi hiển thị. Nearest-rank chỉ là một quy ước; so sánh hai hệ thống phải dùng phương pháp percentile nhất quán.

## 7. Cách cấu hình concurrency ảnh hưởng cả bốn chỉ số

### 7.1. CPU-bound

Tác vụ như mã hóa, xử lý ảnh hoặc tính toán thuần thường bị giới hạn bởi số lõi khả dụng và hiệu quả cache. Nếu có `P` lõi CPU thực sự được cấp, thử mức song song gần `P` là điểm xuất phát hợp lý, sau đó đo throughput và p99. Thêm hàng trăm platform thread vào tính toán CPU-bound thường không tăng năng lực tính toán; có thể làm tệ hơn vì chuyển ngữ cảnh, tranh chấp cache, allocation và GC. Đừng biến quy tắc gần `P` thành giá trị bất biến: môi trường còn có tiến trình khác, GC và cgroup quota.

### 7.2. I/O-bound

Tác vụ chờ mạng, đĩa hoặc kết quả từ tài nguyên khác có thể hưởng lợi từ concurrency cao hơn số lõi. Nếu dùng pool platform thread, thread bị chặn trong `blocking I/O` vẫn chiếm một worker. Pool quá nhỏ tạo hàng đợi; pool quá lớn dùng nhiều bộ nhớ, connection và tạo áp lực lên hệ thống đích. Cần giới hạn số công việc đang truy cập dịch vụ chậm bằng **bounded queue, semaphore, connection limit, timeout** phù hợp, rồi đo.

Từ Java 21, **virtual thread** phù hợp với nhiều tác vụ blocking I/O: giúp duy trì nhiều tác vụ chờ mà không cần platform thread tương ứng cho mỗi tác vụ. Nó **không tăng số lõi CPU**, không tự sửa database nghẽn và không thay thế cơ chế giới hạn concurrency. Một executor “một virtual thread mỗi task” không áp đặt giới hạn số yêu cầu đang hoạt động; nếu tài nguyên đích chỉ chịu được 50 thao tác đồng thời, hãy đặt giới hạn 50 bằng semaphore hoặc cơ chế tương đương ở ranh giới đó. Với mã dùng `synchronized`, native calls hoặc thư viện blocking đặc biệt, đánh giá tình trạng pinning/carrier và hỗ trợ thư viện trên phiên bản JDK đang chạy bằng JFR và profile thực tế.

### 7.3. Locks, contention và shared state

Lock bảo vệ tính đúng đắn, nhưng làm giảm khả năng chạy song song của đoạn critical section. Tăng worker trong khi nhiều worker cùng tranh một khóa có thể khiến throughput đứng yên và tail latency tăng. Nên:

- Giữ đoạn khóa ngắn; tránh gọi I/O hoặc tác vụ chậm trong khi giữ lock.
- Phân chia trạng thái độc lập khi hợp lý; dùng cấu trúc concurrent đúng hợp đồng như `ConcurrentHashMap`, `LongAdder` cho thống kê tần suất cao.
- Không thay đồng bộ hóa bằng truy cập dữ liệu racy chỉ để benchmark đẹp; correctness luôn là điều kiện tiên quyết.
- Quan sát contention thực tế trước khi tối ưu. `LongAdder.sum()` không phải snapshot nguyên tử tuyệt đối khi có cập nhật đồng thời; phù hợp số liệu giám sát, không phù hợp thay thế một bộ đếm nhất quán bắt buộc.

### 7.4. Backpressure và queue

Queue **không tạo ra năng lực phục vụ mới**; nó chỉ giữ công việc chờ. Queue không giới hạn có thể giảm số lần từ chối ngắn hạn nhưng tạo latency lớn, bộ nhớ tăng và OutOfMemoryError khi quá tải kéo dài. Queue giới hạn buộc phải định nghĩa cách ứng xử khi đầy:

| Chiến lược | Cơ chế | Đánh đổi |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` khi không nhận được việc | Lỗi hiển lộ; caller phải xử lý |
| `CallerRunsPolicy` | Thread gọi `execute` tự xử lý khi pool hoạt động | Backpressure hữu ích; có thể làm chậm cả caller |
| `DiscardPolicy` | Bỏ việc mới mà không báo qua exception | Nguy cơ mất công việc âm thầm |
| `DiscardOldestPolicy` | Loại phần tử đầu queue rồi thử nhận việc mới | Có thể bỏ mất việc cũ; phải hiểu thứ tự/giá trị nghiệp vụ |

Chọn policy theo bảo đảm cần thiết: có thể mất việc không, có cần giữ thứ tự, có cần trả lỗi rõ ràng, retry ở đâu. Timeout, cancellation và overload rejection cũng phải đi vào metric. Khi caller có deadline, việc chờ quá deadline rồi vẫn xử lý tiếp có thể lãng phí tài nguyên và làm hàng đợi khó hồi phục.

## 8. Stability: hiệu năng bền vững khi thời gian và tải thay đổi

Một hệ thống ổn định không phải là hệ thống có latency bằng hệt nhau mọi lúc; đó là hệ thống có khả năng đạt ngưỡng dịch vụ đã chọn, không tích lũy backlog vô hạn và phục hồi sau biến động trong điều kiện được thiết kế. Ví dụ định nghĩa tiêu chí kiểm thử:

- Dưới **150 yêu cầu/giây** trong **15 phút**, p95 ≤ 100 ms, p99 ≤ 300 ms, lỗi + từ chối ≤ 0,5%; tất cả các ngưỡng là **giả định minh họa**, không phải SLO mặc định cho mọi ứng dụng.
- Với burst **300 yêu cầu/giây trong 10 giây**, quan sát queue peak và yêu cầu backlog trở về mức nền trong một khoảng thời gian chấp nhận được.
- Khi duy trì tải lâu, kiểm tra memory/heap, allocation rate, GC pause, thread count, file descriptor/connection và throughput có trôi theo thời gian không.

Những tín hiệu mất ổn định điển hình: p99 tăng dần trong khi throughput không tăng; queue luôn cao; thời gian GC dài hơn; số thread/connection liên tục tăng; retry dồn tải lên hệ thống vừa gặp lỗi; tỷ lệ timeout tăng nhưng log throughput thành công vẫn tương đối đẹp. Tính bền vững đòi hỏi **giới hạn tải, giới hạn queue, deadline, chính sách retry có kiểm soát và quan sát tài nguyên**. Retry đồng loạt ngay sau thất bại có thể tạo retry storm và làm tải thực còn cao hơn tải gốc.

Độ ổn định còn liên quan tới tính đúng đắn: race condition, deadlock, livelock hoặc starvation có thể làm latency vô hạn hay khiến một nhóm công việc không được phục vụ dù CPU còn hoạt động. Không đánh giá một tối ưu concurrency là thành công nếu nó làm sai kết quả, mất tác vụ hoặc phá bảo đảm thứ tự.

## 9. Quy trình thực nghiệm để tìm điểm cân bằng

**Bước 1 — Chốt ranh giới và mục tiêu.** Chọn công việc cụ thể (một request, một task, một batch), định nghĩa success/failure, timeout, measurement start/end và SLO thử nghiệm. Ví dụ: p99 < 200 ms, throughput thành công ≥ 120 tasks/s, lỗi ≤ 0,1% trong 10 phút. Các số này chỉ để minh họa cách lập mục tiêu.

**Bước 2 — Tạo baseline có thể lặp lại.** Ghi JDK version, CPU/quota, RAM, collector, kích thước heap, số worker, queue capacity, kích thước và phân phối công việc, tài nguyên I/O, trạng thái warm-up/JIT và máy phát tải. Tách warm-up khỏi cửa sổ đo; chạy đủ lâu và lặp lại nhiều lần trước khi kết luận. Tránh để máy sinh tải tự bão hòa.

**Bước 3 — Tăng tải theo bậc có kiểm soát.** Thử nhiều arrival rate, không chỉ một lần “đẩy tới chết”. Mỗi bậc theo dõi completion/s, p50/p95/p99, error/reject/timeout, in-flight, queue depth/age, CPU, GC, thread states và trạng thái dịch vụ đích. Nếu còn queue sau bậc trước, chờ hệ thống về nền hoặc thiết lập lại điều kiện thí nghiệm.

**Bước 4 — Xác định giới hạn thực tế.** Tìm mức tải cao nhất mà tất cả ngưỡng đều đạt một cách bền vững. Chú ý “điểm gãy”: throughput đi ngang, p99 tăng vọt, queue tăng hoặc tỷ lệ lỗi tăng. Quan sát queue và tài nguyên giúp phân biệt nghẽn CPU, lock, I/O và giới hạn pool.

**Bước 5 — Đổi một biến mỗi lượt.** Ví dụ pool size 4 → 8, queue 100 → 200 hoặc chuyển một phần công việc I/O sang virtual threads. Giữ workload, định nghĩa metric và thời gian thử tương đương; kiểm tra cả tốc độ, độ trễ, tính đúng đắn và tài nguyên. Có thể tối ưu throughput bằng cách chấp nhận thêm latency, nhưng phải là đánh đổi được đo và phù hợp SLO.

**Bước 6 — Soak/burst/recovery.** Kiểm tra lâu dài, lúc vượt tải và sau khi tải giảm. Cải thiện p50 trong 30 giây nhưng gây heap tăng dần sau 30 phút không được xem là tối ưu thành công.

### Công cụ Java hữu ích

- **JDK Flight Recorder (JFR)**: xem CPU sample, allocation, GC, thread scheduling/park, monitor contention, I/O và các event liên quan; đối chiếu cùng khoảng thời gian p99 tăng.
- **Java Mission Control (JMC)**: đọc và phân tích file JFR, tìm điểm nóng và thời gian chờ.
- **`jcmd <PID> Thread.print` / thread dump**: xem trạng thái thread tại thời điểm cụ thể, tìm lock contention hoặc deadlock. Một dump duy nhất chưa đủ kết luận xu hướng; có thể lấy vài snapshot cách nhau.
- **JMH**: benchmark vi mô cho đoạn Java thuần, có warm-up/fork và cơ chế giảm sai lệch do JIT; không dùng một vòng lặp `nanoTime()` đơn giản để kết luận hiệu năng của một thuật toán nhỏ. Kết quả JMH cũng không tự nói lên response time đầu-cuối hoặc capacity dưới tải thật.
- **CPU/heap/GC profiler và số liệu hệ điều hành**: nhận diện throttling, allocation, GC, context switching và giới hạn ngoài JVM.

## 10. Một số tình huống chẩn đoán thực tế

| Hiện tượng | Giả thuyết cần kiểm chứng | Hướng kiểm tra/điều chỉnh |
| --- | --- | --- |
| Throughput không tăng khi tăng thread, CPU sát giới hạn | CPU-bound, overhead scheduling | CPU profile; thử mức song song sát CPU quota |
| p99 tăng, CPU thấp, nhiều `BLOCKED` | Lock contention | JFR monitor event, thread dump; rút ngắn critical section |
| Queue tăng liên tục, worker bận | Arrival rate vượt tốc độ phục vụ | Tách service time/queue time; giới hạn đầu vào và rà bottleneck |
| p50 ổn, p99 xấu đột ngột | GC, pause, I/O tail, lock, burst | So timestamp p99 với JFR/GC/event upstream |
| Error giảm khi queue tăng nhưng latency vọt | Chuyển overload thành chờ đợi | Queue bounded, timeout, rejection rõ ràng, theo dõi queue age |
| CPU thấp, nhiều thread đợi I/O, heap tăng | Blocked I/O và concurrency không giới hạn | Giới hạn in-flight/connection; thử virtual threads nếu phù hợp |
| Benchmark rất nhanh, production chậm | Workload hoặc ranh giới đo khác | Reproduce payload, arrival pattern, dependency, warm-up, GC |
| Chạy lâu throughput giảm dần | Rò rỉ tài nguyên, accumulation, retry | Soak test và theo dõi heap, connection, queue, GC |

Đừng kết luận chỉ từ một tín hiệu. Ví dụ CPU thấp có thể do lock, nhưng cũng có thể do tải đến thấp; phải ghép **arrival rate + completion rate + queue wait + tài nguyên** mới xác định được nguyên nhân.

## 11. Những lỗi phổ biến cần tránh

1. **Tăng số thread bằng cảm giác:** throughput có thể đã bão hòa; hãy đo cùng p99, CPU, queue và tỷ lệ lỗi trước/sau.
2. **Chỉ báo average latency:** các yêu cầu đuôi chậm bị che; thêm p95/p99, timeout và thời gian chờ của request chưa hoàn tất.
3. **Dùng queue vô hạn để “không từ chối”:** backlog và memory có thể tăng đến khi sụp đổ.
4. **Lấy tốc độ gửi làm throughput:** phải đo số việc *kết thúc* trên cùng cửa sổ thời gian và phân loại kết quả.
5. **Chỉ đo thời gian trong `run()`:** bỏ qua thời gian queue và admission, đánh giá thiếu response time.
6. **Hiểu nhầm virtual thread là CPU song song vô hạn:** virtual thread giúp quản lý tác vụ blocking, không nhân số lõi hay capacity dịch vụ đích.
7. **So sánh benchmark ở môi trường khác:** CPU quota, JIT, warm-up, GC, payload và dependencies có thể lấn át thay đổi code.
8. **Bỏ qua coordinated omission và request chưa hoàn tất:** latency báo cáo có thể đẹp giả lúc hệ thống nghẽn.
9. **Tối ưu mà phá correctness:** data race, deadlock, mất task hoặc cancel sai là thất bại, dù một phép thử ngắn cho throughput cao.
10. **Đo đạc gây nhiễu:** ghi log từng task hoặc lưu vô hạn mọi sample có thể làm chính phép thử chậm; dùng sampling/histogram có kiểm soát.

## 12. Câu hỏi tự kiểm tra

- Một pool có 8 worker, tất cả bận nhưng CPU chỉ 20%. Có thể kết luận thiếu CPU không? **Không**: cần biết worker đang chờ I/O, lock hay scheduler và quan sát queue.
- Throughput giữ nguyên 100 tasks/s nhưng p99 từ 80 ms lên 2 s khi tăng tải. Đây có phải capacity tốt hơn? **Không**: hệ thống có thể đã bão hòa; backlog và tail latency đang xấu đi.
- Có thể dùng `L = λW` để yêu cầu tạo đúng `L` Java thread không? **Không**: `L` là số công việc trong hệ thống, có thể đang queue hoặc chờ I/O, và định luật đòi hỏi điều kiện ổn định.
- Nếu tăng queue size làm giảm rejection, hệ thống chắc chắn tốt hơn? **Không**: có thể đổi lỗi từ chối thành latency/timeout hoặc tăng bộ nhớ; phải đánh giá toàn bộ SLO.
- Vì sao đo p99 trong 10 giây chưa đủ? **Vì** mẫu ít, trạng thái JIT/GC và biến động tải có thể làm kết quả thiếu đại diện; cần lặp, kéo dài và ghi điều kiện đo.

**Nguyên tắc áp dụng:** thiết kế concurrency để đạt **throughput bền vững với latency và tỷ lệ lỗi chấp nhận được**, trong giới hạn tài nguyên rõ ràng; quan sát đúng bottleneck, có backpressure, và xác nhận stability bằng tải kéo dài.