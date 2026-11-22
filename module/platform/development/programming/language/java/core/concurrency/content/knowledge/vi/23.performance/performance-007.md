# Little's Law: liên hệ lượng tác vụ, thời gian chờ và throughput trong Java concurrency

Khi phân tích hiệu năng của một chương trình Java xử lý nhiều công việc đồng thời, ta thường quan sát ba số: số task đang ở trong hệ thống, số task hoàn thành mỗi giây và thời gian mỗi task phải chờ/xử lý. **Little's Law** là quy luật định lượng nối ba số đo đó. Nó hữu ích với thread pool, hàng đợi, semaphore, pipeline bất đồng bộ và hệ thống có backpressure trong **Java concurrency nói chung**.

## 1. Công thức L = λW

Trong trạng thái vận hành ổn định, với cùng một ranh giới đo và cùng loại phần tử:

\[
\boxed{L=\lambda W}
\]

| Ký hiệu | Ý nghĩa | Đơn vị và ví dụ |
| --- | --- | --- |
| **L** | Số task trung bình có mặt trong ranh giới đo, thường gọi là *work in progress* hoặc *in-flight* | task, ví dụ 24 |
| **λ** (lambda) | Tốc độ task đã được chấp nhận và rời hệ thống về dài hạn; khi ổn định là throughput | task/giây, ví dụ 120/s |
| **W** | Thời gian trung bình một task lưu lại trong chính ranh giới đó | giây, ví dụ 0,2 s |

Ví dụ: hệ thống hoàn tất trung bình 120 task/giây, mỗi task ở trong hệ thống trung bình 200 ms:

\[
L=120\ \mathrm{task/s}\times 0{,}2\ \mathrm{s}=24\ \mathrm{task}
\]

Tức là trung bình tại một thời điểm có **24 task đang chờ hoặc chạy**, nếu ranh giới đo là toàn bộ giai đoạn từ được nhận vào đến hoàn tất.

Từ cùng công thức:

\[
W=\frac{L}{\lambda},\qquad \lambda=\frac{L}{W}
\]

Các biến phải dùng **đơn vị nhất quán**: 200 ms = 0,2 s; 2 phút = 120 s. Nếu λ tính theo task/giây nhưng W vẫn để ms, kết quả bị sai 1.000 lần.

**L không phải số thread, W không chỉ là CPU time, λ không mặc nhiên là số request gửi tới.** Chúng phụ thuộc vào cách xác định hệ thống đang đo. Định luật diễn tả quan hệ của các giá trị trung bình, không phải cách tự động làm throughput tăng lên bằng việc mở thêm worker.

## 2. Đặt ranh giới đúng trong một executor

Giả sử một task đi qua một hàng đợi trước khi được worker chạy:

~~~text
                         một ranh giới đo
            ┌─────────────────────────────────────┐
admit ------>| QUEUED ---------> RUNNING           |-----> leave
            | Wq (đang chờ)    Ws (đang thực thi)   |
            └─────────────────────────────────────┘
               Lq task            Ls task

                 W = Wq + Ws
                 L = Lq + Ls
~~~

Với một luồng task ổn định và hai giai đoạn nối tiếp không chồng lấn:

\[
L_q=\lambda W_q,\qquad L_s=\lambda W_s
\]

\[
L=L_q+L_s=\lambda(W_q+W_s)=\lambda W
\]

- **Wq** là độ trễ chờ từ admission/enqueue đến khi worker bắt đầu chạy.
- **Ws** là thời gian chạy trên worker, có thể bao gồm chờ khóa hoặc I/O; không nhất thiết bằng CPU time.
- **W** là tổng response/residence time ở trong executor.
- **Lq** là lượng task trung bình trong queue, còn **Ls** là lượng task trung bình đang chiếm worker.
- **L** gồm cả queued và running, không chỉ một trong hai.

Nếu task được chạy ngay, Wq có thể bằng hoặc gần 0. Nếu ứng dụng chuyển task sang executor thứ hai, ranh giới của executor thứ nhất chấm dứt khi task rời nó; muốn đo end-to-end phải bao gồm cả hai stage và giai đoạn chờ giữa chúng.

Khi task bị hủy, timeout hoặc bị reject, phải định nghĩa xem nó có được chấp nhận hay không, khi nào rời hệ thống và outcome nào được tính. Không thể lấy latency của **request hoàn chỉnh** rồi nhân throughput của **subtask** trong một pipeline fork/join; các đơn vị quan sát đã khác nhau.

## 3. Vì sao công thức đúng: diện tích task-thời gian

Gọi N(t) là số task đang có mặt tại thời điểm t. Diện tích phía dưới đồ thị N(t) biểu diễn tổng số **task-giây** được tích lũy:

\[
A=\int_0^T N(t)\,dt
\]

Nếu đầu cửa sổ chưa có task và cuối cửa sổ mọi task đều đã rời đi, mỗi task i đóng góp một khoảng Wᵢ giây, nên:

\[
A=\sum_{i=1}^{n}W_i
\]

Số task trung bình theo thời gian là \(L=A/T\). Throughput trên cửa sổ đầy đủ này là \(\lambda=n/T\). Thời gian lưu lại trung bình là \(W=(\sum_i W_i)/n\). Ghép lại:

\[
L=\frac{\sum_i W_i}{T}=\frac{n}{T}\times\frac{\sum_i W_i}{n}=\lambda W
\]

Đây là trực giác bảo toàn số lượng và thời gian; không cần từng task phải xử lý nhanh như nhau hoặc thời gian xử lý có phân phối xác suất đặc biệt.

**Cẩn thận với cửa sổ cắt ngang task:** nếu bắt đầu đo khi đã có task đang chờ hoặc kết thúc đo khi còn backlog, phải tính phần hiện diện nằm trong cửa sổ của những task chưa hoàn tất. Lấy mean latency chỉ của task đã hoàn thành trong một cửa sổ ngắn có thể gây **completion bias**: task chậm vẫn nằm trong queue nên bị bỏ khỏi mẫu.

## 4. Điều kiện steady state và ý nghĩa của throughput

Để dùng các số đo dài hạn như Little's Law trong vận hành, hệ thống phải tương đối **ổn định**:

- Tốc độ task được chấp nhận vào ranh giới xấp xỉ tốc độ rời đi trong dài hạn.
- Backlog không tăng vô hạn.
- Các mức trung bình của throughput, response time và occupancy có ý nghĩa trong khoảng quan sát đủ dài.
- Đo tại cùng một ranh giới, cùng một tập task và cùng pha workload.

Ví dụ producer đưa đến 150 task/s, executor bền vững chỉ xử lý 120 task/s và vẫn chấp nhận toàn bộ: hàng đợi tăng khoảng **30 task mỗi giây**. Sau 20 giây, backlog có thể tăng khoảng 600 task. Trong tình huống backlog tăng mãi, **không có giá trị L ổn định dài hạn**, nên không thể dùng một phép tính Little's Law steady state để suy ra buffer đủ dùng mãi.

Phân biệt ba tốc độ:

| Metric | Nội dung |
| --- | --- |
| **Offered load** | Số lần gọi gửi task vào cửa hệ thống, kể cả bị reject |
| **Admitted rate** | Số task thực sự được hệ thống chấp nhận |
| **Departure rate** | Số task rời ranh giới: hoàn tất, lỗi hoặc hủy theo hợp đồng đo |

Trong trạng thái ổn định và một quần thể task được theo dõi nhất quán, admitted rate cân bằng departure rate về dài hạn. Nếu có reject, offered load có thể lớn hơn admitted rate. Nếu chỉ đếm successful completion nhưng W/L lại bao gồm task lỗi và hủy, công thức sẽ lệch bởi cách định nghĩa khác nhau.

Đối với một batch hữu hạn được quan sát đầy đủ từ lúc rỗng đến khi drain xong, phép bảo toàn ở mục 3 vẫn hữu ích, kể cả khi arrival rate thay đổi trong batch. **Không nhầm phép tính theo batch đầy đủ với việc hệ thống đã chứng minh throughput ổn định để capacity planning.**

## 5. Ví dụ: số tác vụ nhiều hơn nhưng throughput không cao hơn

Giả sử một pool có throughput đều **120 task/s** và thời gian mỗi task chiếm worker trung bình **150 ms**. So sánh hai kịch bản:

| Chỉ số | A: ít chờ | B: nhiều chờ |
| --- | ---: | ---: |
| Throughput λ | 120 task/s | 120 task/s |
| Queue wait Wq | 50 ms | 350 ms |
| Worker time Ws | 150 ms | 150 ms |
| Tổng W | 200 ms | 500 ms |
| Lq = λWq | 6 task | 42 task |
| Ls = λWs | 18 task | 18 task |
| L = λW | 24 task | 60 task |

B có trung bình **60 task trong hệ thống** so với 24 của A, nhưng **không xử lý thêm được task/giây nào**. Khác biệt nằm ở 36 task chờ thêm trong queue. Nếu worker hoặc downstream đang bão hòa, tăng queue capacity chỉ cho phép lưu nhiều việc hơn, đồng thời đẩy latency lên cao.

Tương tự, nếu X = 100 task/s không đổi và W tăng từ 0,2 s lên 1 s, L tương ứng tăng từ 20 lên 100 task. Đây là dấu hiệu cần kiểm tra backlog, contention, downstream, GC và lock wait, không thể mặc định tăng số worker là giải pháp.

## 6. Java 17: chương trình tính toán độc lập

Đặt toàn bộ mã sau trong **LittleLawCalculator.java**:

~~~java
import java.util.Locale;

public class LittleLawCalculator {
    static void show(String label, double throughputPerSecond,
                     double queueMillis, double serviceMillis) {
        double totalMillis = queueMillis + serviceMillis;
        double queueCount = throughputPerSecond * queueMillis / 1000.0;
        double runningCount = throughputPerSecond * serviceMillis / 1000.0;
        double totalCount = throughputPerSecond * totalMillis / 1000.0;

        System.out.printf(Locale.ROOT,
                "%s: X=%.0f task/s, W=%.0f ms, L=%.1f task (Lq=%.1f, Ls=%.1f)%n",
                label, throughputPerSecond, totalMillis,
                totalCount, queueCount, runningCount);
    }

    public static void main(String[] args) {
        show("A", 120, 50, 150);
        show("B", 120, 350, 150);

        double targetUtilization = 0.75;
        int estimatedWorkers = (int) Math.ceil(
                120 * (150.0 / 1000.0) / targetUtilization);
        System.out.println("Workers estimated at 75%: " + estimatedWorkers);
    }
}
~~~

Chạy:

~~~bash
javac LittleLawCalculator.java
java LittleLawCalculator
~~~

Stdout **xác định**:

~~~text
A: X=120 task/s, W=200 ms, L=24.0 task (Lq=6.0, Ls=18.0)
B: X=120 task/s, W=500 ms, L=60.0 task (Lq=42.0, Ls=18.0)
Workers estimated at 75%: 24
~~~

Các số trên là đầu vào giả định để tính theo công thức, không phải dữ liệu Java runtime đo được. Cần benchmark riêng để khẳng định một workload thực sự có thể duy trì X và W tương ứng.

## 7. Từ L = λW đến dự trù số worker

Giá trị **Ls = λWs** cho biết có bao nhiêu task trung bình đang thực hiện. Nếu mỗi task chiếm trọn một worker trong toàn bộ Ws, mức hoạt động trung bình của pool c worker xấp xỉ:

\[
\rho\approx\frac{\lambda W_s}{c}
\]

Với λ = 120/s, Ws = 0,15 s, ta có Ls = 18. Pool 18 worker tương đương sử dụng trung bình gần 100% khả năng phục vụ theo mô hình đơn giản. Nếu chọn mức sử dụng mục tiêu 75%:

\[
c\gtrsim\left\lceil\frac{18}{0{,}75}\right\rceil=24
\]

**24 chỉ là ước lượng khởi đầu**, cần đo với workload thật. Sizing phải xét:

- **CPU-bound:** throughput tối đa chịu giới hạn của số core thực và CPU time mỗi task. Nếu mỗi task tốn 150 ms CPU, 120 task/s đòi khoảng **18 core-giây CPU mỗi giây**; tăng số Java thread không biến máy 8 core thành 18 core.
- **I/O-bound:** task giữ worker nhưng thường chờ socket/DB; tăng concurrency có thể che latency I/O nếu còn connection, memory và downstream capacity, nhưng quá nhiều task có thể khiến hệ thống khác bão hòa.
- **Blocking/lock contention:** Ws tăng khi tranh chấp khóa hoặc connection, làm Ls tăng mà throughput có thể đứng yên.
- **Asynchronous stages:** một logical request có thể không giữ một thread suốt W; do đó XW là số request in-flight, không tự động là số platform thread phải tạo.
- **Virtual threads (ở Java phiên bản hỗ trợ):** giảm chi phí thread khi chờ I/O trong nhiều trường hợp, nhưng không bỏ qua giới hạn cơ sở dữ liệu, memory hoặc phép cân bằng L = λW.

Không dùng giá trị L trung bình làm **queue capacity**. Capacity cần tính thêm burst, đuôi latency, mức RAM chấp nhận được, timeout, backpressure và chính sách reject/drop. Số trung bình 6 task trong queue không bảo đảm queue 6 chỗ sẽ không bao giờ đầy.

## 8. Đo trong ThreadPoolExecutor: metric nào tương ứng với L, W, λ?

| Metric cần đo | Cách lấy trong Java | Hạn chế |
| --- | --- | --- |
| Queue hiện tại | ThreadPoolExecutor.getQueue().size() | Snapshot của queue biến động, không phải trung bình theo thời gian |
| Worker đang làm việc | ThreadPoolExecutor.getActiveCount() | API công bố đây là **ước lượng** |
| Task đã hoàn tất | ThreadPoolExecutor.getCompletedTaskCount() | Ước lượng; không tự phân biệt nghiệp vụ thành công hay lỗi |
| Queue wait | startRunNanos − admittedNanos | Đo bằng System.nanoTime() |
| Service wall time | finishedNanos − startRunNanos | Bao gồm cả thời gian blocking |
| Total response/residence time | finishedNanos − admittedNanos | Phải đo cùng ranh giới với queue và running |
| Throughput X | Số task rời ranh giới / số giây | Trừ/đếm riêng rejected, xác định rõ lỗi và hủy |
| L quan sát | Trung bình theo thời gian của queued + running | Có thể lấy mẫu đều theo thời gian hoặc tích phân bằng counter trên mỗi transition |

**System.nanoTime()** dùng để đo elapsed time trong cùng JVM, tránh sai lệch do chỉnh đồng hồ hệ thống. Đừng dùng System.currentTimeMillis() để đo chính xác thời lượng ngắn.

Nếu dùng CompletableFuture hay ForkJoinPool, cần hiểu một request nghiệp vụ có thể sinh ra nhiều Runnable, stage và continuation. Xác định metric theo request hoặc theo từng subtask một cách nhất quán; tuyệt đối không dùng số lượng subtask trong queue để thế chỗ số request đang in-flight khi W đo trên request.

Với sampling, muốn ước lượng L theo thời gian thì nên sample định kỳ hoặc đo thời gian mỗi mức occupancy tồn tại. Một snapshot đúng vào đỉnh burst không phải time-average. Đặc biệt, các hàm getActiveCount/getCompletedTaskCount của ThreadPoolExecutor chỉ cung cấp thông tin giám sát xấp xỉ, không phải một phép snapshot nguyên tử của toàn hệ thống.

## 9. Java 17: một phép đo với queue giới hạn và rejection

Ví dụ sau tạo pool có 4 worker, queue tối đa 32 task, dùng **AbortPolicy** để từ chối khi đầy. Chương trình thử gửi 240 tác vụ, mỗi tác vụ giả lập 15 ms xử lý và được gắn timestamp. Kết quả sẽ biến động theo lịch chạy của máy, vì đây là thí nghiệm concurrency thật.

Lưu **LittleLawExecutorProbe.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class LittleLawExecutorProbe {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                4, 4, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                new ThreadPoolExecutor.AbortPolicy());

        LongAdder completed = new LongAdder();
        LongAdder rejected = new LongAdder();
        LongAdder queueWaitNanos = new LongAdder();
        LongAdder runNanos = new LongAdder();
        LongAdder residenceNanos = new LongAdder();
        AtomicInteger sampledPeakQueue = new AtomicInteger();

        long windowStart = System.nanoTime();
        try {
            for (int i = 0; i < 240; i++) {
                long submittedAt = System.nanoTime();
                try {
                    executor.execute(() -> {
                        long startedAt = System.nanoTime();
                        try {
                            TimeUnit.MILLISECONDS.sleep(15);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        } finally {
                            long finishedAt = System.nanoTime();
                            queueWaitNanos.add(startedAt - submittedAt);
                            runNanos.add(finishedAt - startedAt);
                            residenceNanos.add(finishedAt - submittedAt);
                            completed.increment();
                        }
                    });
                    sampledPeakQueue.accumulateAndGet(
                            executor.getQueue().size(), Math::max);
                } catch (RejectedExecutionException e) {
                    rejected.increment();
                }
            }
        } finally {
            executor.shutdown();
        }

        if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Executor did not terminate");
        }

        double seconds = (System.nanoTime() - windowStart) / 1e9;
        long n = completed.sum();
        double throughput = n / seconds;
        double meanQueueMs = queueWaitNanos.sum() / (double) n / 1e6;
        double meanRunMs = runNanos.sum() / (double) n / 1e6;
        double meanResidenceSec = residenceNanos.sum() / (double) n / 1e9;
        double inferredMeanInFlight = throughput * meanResidenceSec;

        System.out.printf(Locale.ROOT,
                "completed=%d, rejected=%d, peakQueueSample=%d%n",
                n, rejected.sum(), sampledPeakQueue.get());
        System.out.printf(Locale.ROOT,
                "X=%.1f task/s, Wq=%.1f ms, Ws=%.1f ms, " +
                "W=%.1f ms, L=X*W=%.1f task%n",
                throughput, meanQueueMs, meanRunMs,
                meanResidenceSec * 1000, inferredMeanInFlight);
    }
}
~~~

Chạy:

~~~bash
javac LittleLawExecutorProbe.java
java LittleLawExecutorProbe
~~~

Chương trình in **hai dòng số liệu**, có mẫu định dạng như sau:

~~~text
completed=<n>, rejected=<n>, peakQueueSample=<n>
X=<x> task/s, Wq=<ms> ms, Ws=<ms> ms, W=<ms> ms, L=X*W=<l> task
~~~

Các ký hiệu trong ngoặc nhọn ở mẫu trên là vị trí dành cho giá trị chạy thực tế, **không phải stdout cố định**. Đừng khẳng định số rejected hay peakQueue luôn giống nhau: worker có thể kịp nhận thêm task ngay trong vòng lặp gửi.

Giải thích cách đọc:

1. **completed** đếm các task đã được pool xử lý xong; **rejected** đếm lần gửi bị từ chối, không đưa vào trung bình W.
2. **Wq** tính từ ngay trước thao tác execute đến khi callback bắt đầu. Khoảng này gồm thời gian chờ nhận việc và một phần overhead gọi API. **Ws** tính từ callback bắt đầu đến khi hoàn tất. **W** là tổng.
3. **X** tính trên cả cửa sổ từ trước batch đến khi tất cả task được nhận đã kết thúc, gồm pha xử lý backlog. Nó là throughput **của batch**, chưa phải chứng cứ về tốc độ steady state dài hạn.
4. **L = XW** là số tác vụ trung bình theo thời gian trong **chính cửa sổ batch đầy đủ**, dựa trên số task được nhận và đã hoàn tất. Đây không phải **peakQueueSample**: giá trị đỉnh chỉ đo queue tại các thời điểm lấy mẫu, còn L gồm queued + running và là trung bình.
5. Nếu cần metric sản xuất chính xác hơn, thêm metric admission/rejection/cancellation theo định nghĩa nghiệp vụ, histogram queue wait và response time, và lấy mẫu time-weighted occupancy trong giai đoạn tải ổn định.

Với benchmark thật, phải warm-up JVM, đo theo từng cửa sổ có tải ổn định, kiểm tra CPU/GC/downstream, percentiles và hàng đợi, thay vì kết luận từ một burst 240 task duy nhất.

## 10. Kiểm tra tính nhất quán của metrics

Giả sử trong một giai đoạn ổn định quan sát:

- Throughput X = **250 task/s**.
- Mean W = **80 ms = 0,08 s**.
- Time-average queued task = **9**.
- Time-average running task = **11**.

Theo Little's Law:

\[
L_{\mathrm{expected}}=250\times0{,}08=20\ \mathrm{task}
\]

Metric occupancy cũng cho **9 + 11 = 20**, một phép kiểm tra hợp lý. Nếu metric lại báo L = 50, cần kiểm tra:

1. W có đo từ admission hay chỉ từ lúc worker bắt đầu chạy?
2. L có đếm cả task trong một queue khác hoặc nhiều subtask của cùng request?
3. X có vô tình chỉ đếm thành công còn W/L bao gồm task lỗi và hủy?
4. Các metric có được tính trên cùng khoảng thời gian và cùng quần thể không?
5. Hệ thống đang startup, chịu burst, shutdown hay backlog tăng liên tục?
6. Phần lớn task chậm có còn nằm trong queue, làm mẫu độ trễ của completed task bị lệch không?

Mục đích phép so sánh này là tìm lỗi định nghĩa hoặc đo lường, không phải buộc hệ thống phải đạt một cấu hình cụ thể.

## 11. Những tình huống thực tế cần diễn giải cẩn thận

### CPU đã bão hòa

Khi CPU chạy hết năng lực, thêm worker có thể làm tăng context switch và lock contention. Nếu X giữ nguyên nhưng W tăng, L tăng theo. Dữ liệu đó giúp chẩn đoán backlog, nhưng không có nghĩa tăng số thread một lần nữa sẽ cải thiện throughput.

### Producer phát nhanh hơn consumer

Offered 180 task/s, throughput chỉ 130 task/s, không reject và luôn nhận vào: backlog tăng xấp xỉ **50 task mỗi giây**, không thể có trạng thái ổn định lâu dài. Cần giảm tốc nguồn, dùng bounded queue và admission control, tạo backpressure hoặc tăng công suất xử lý thật. Với dữ liệu cho phép mất có thể cân nhắc drop/coalesce có kiểm soát; với dữ liệu phải giữ đủ cần thiết kế cơ chế bền vững và retry phù hợp.

### Pipeline nhiều stage

Stage A có X = 200 task/s và W = 20 ms nên LA = 4 task; stage B có cùng X và W = 80 ms nên LB = 16 task. Nếu mỗi task đi qua A rồi B đúng một lần, không overlap và không tạo thêm task, tổng L ≈ 20, tổng W = 100 ms. Nhưng nếu mỗi request ở A sinh ra ba subtask ở B, throughput theo **subtask** của B có thể là 600/s; không thể dùng λ=200/s trên L của B.

### Công việc có nhiều nhóm độ trễ

Nếu có task ngắn và dài, dùng mean W **có trọng số theo tần suất task**. Không lấy trung bình đơn giản của mean hai nhóm có lưu lượng rất khác nhau. Với nhóm i, có thể phân tích riêng Li = λi Wi rồi cộng Li nếu các nhóm không bị đếm trùng.

### Tail latency

Little's Law dùng **mean W**, không phải median, p95, p99. Hai ứng dụng có cùng throughput và mean latency có thể có tail latency rất khác. Không thay p99 vào công thức rồi gọi kết quả là “p99 số task đồng thời”. Muốn đạt SLO cần thêm histogram latency, burst analysis, mô hình hàng đợi và phép thử tải.

## 12. Checklist khi áp dụng Little's Law vào dự án Java

1. **Định nghĩa một ranh giới**: queue, toàn executor hay end-to-end; xác định start/end thật của task.
2. **Chọn đơn vị công việc nhất quán**: request, job, event hay subtask; nêu cách xử lý lỗi, timeout, cancellation và rejection.
3. **Thu thập X, W, L cùng kỳ**: throughput theo thời gian, mean residence time trên task phù hợp và time-average in-flight.
4. **Đo thêm Wq và Ws**: biết thời gian nằm trong queue hay đang chiếm worker. Kiểm tra quan hệ Lq + Ls ≈ X(Wq + Ws).
5. **Kiểm tra sự ổn định**: backlog trend, input rate so với completion, rejected/dropped, worker utilization, CPU/GC và tài nguyên downstream.
6. **Không nhầm mean với peak**: queue capacity, SLA và p95/p99 cần dữ liệu phân phối, burst và chính sách quá tải.
7. **Thay đổi cấu hình có kiểm chứng**: giới hạn in-flight, bounded queue, thread pool, timeout, backpressure, phân tách workload; luôn đo lại throughput và latency sau thay đổi.
8. **Không loại bỏ task chưa hoàn thành khỏi bài toán đo**: bảo toàn ranh giới thời gian để tránh completion bias.

## Tài liệu tham khảo

- [Little's Law — National Academies](https://www.nationalacademies.org/read/1867/chapter/22): quan hệ giữa số task trung bình, throughput và thời gian lưu lại trong trạng thái ổn định.
- [ThreadPoolExecutor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue, worker, thống kê xấp xỉ, saturation và rejection.
- [System.nanoTime — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): đo khoảng thời gian trong cùng JVM.
- [ArrayBlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): hàng đợi có dung lượng giới hạn.

**Ghi nhớ:** Khi đo nhất quán và hệ thống vận hành ổn định, **số task trung bình đang hiện diện = throughput × thời gian ở trong hệ thống**. Little's Law giúp phân biệt queue buildup, đo in-flight và kiểm tra tính nhất quán của metrics; nó không tự nâng công suất CPU hay quyết định mọi cấu hình thread pool.