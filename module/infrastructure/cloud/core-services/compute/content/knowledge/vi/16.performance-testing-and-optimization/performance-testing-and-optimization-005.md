# Tối ưu số worker, thread pool và mức đồng thời

Một dịch vụ compute có thể có đủ vCPU và RAM nhưng vẫn xử lý request chậm vì số worker quá ít, thread pool bị nghẽn, hàng đợi tăng không giới hạn hoặc nhiều request cùng tranh chấp một dependency. Ngược lại, tăng worker liên tục cũng có thể làm CPU chuyển ngữ cảnh nhiều hơn, tiêu thụ thêm bộ nhớ, làm database quá tải và khiến độ trễ tệ hơn.

Tối ưu concurrency là bài toán cân bằng giữa năng lực xử lý, thời gian chờ, giới hạn tài nguyên và mức tải mà các dependency có thể chịu. Cần đo workload, phân loại tác vụ, ước lượng số worker ban đầu, giới hạn hàng đợi, áp dụng backpressure và kiểm chứng bằng tải thử. Bài học này trình bày cách thực hiện trên VM, container và dịch vụ cloud, kèm ví dụ Java để cấu hình thread pool có kiểm soát.

## 1. Worker, thread, task và concurrency

Các thuật ngữ thường được dùng gần nhau nhưng mô tả những khái niệm khác nhau:

- **Task:** một đơn vị công việc cần thực hiện, ví dụ xử lý một request, chạy một job hoặc ghi một batch dữ liệu.
- **Worker:** thành phần nhận task và thực hiện nó. Worker có thể là một thread, process, coroutine hoặc event loop tùy kiến trúc.
- **Thread:** luồng thực thi được hệ điều hành hoặc runtime lập lịch. Một thread có stack và trạng thái thực thi riêng.
- **Thread pool:** tập hợp thread được tạo và quản lý để tái sử dụng cho nhiều task.
- **Concurrency:** số công việc đang được xử lý hoặc đang tồn tại trong cùng khoảng thời gian.
- **Parallelism:** số công việc thực sự chạy đồng thời trên các đơn vị xử lý khác nhau.
- **In-flight request:** request đã được nhận nhưng chưa hoàn tất.
- **Queue:** nơi lưu task đang chờ worker hoặc tài nguyên tiếp nhận.

Concurrency không đồng nghĩa với parallelism. Một ứng dụng có thể có 500 request đang chờ I/O nhưng chỉ có 8 thread thực thi mã tại một thời điểm. Một CPU 8 vCPU cũng không thể thực hiện song song 500 luồng CPU-bound chỉ vì thread pool có 500 thread.

### Ba mô hình xử lý phổ biến

| Mô hình | Cách hoạt động | Điểm mạnh | Điểm cần chú ý |
|---|---|---|---|
| Thread-per-task | Mỗi task được gán một thread | Đơn giản, dễ viết mã đồng bộ | Chi phí tạo thread và bộ nhớ; cần giới hạn số thread |
| Thread pool | Task được đưa vào queue và thread lấy ra xử lý | Tái sử dụng thread, kiểm soát concurrency | Cần cấu hình pool, queue và chính sách từ chối |
| Event loop / async | Một hoặc vài thread điều phối nhiều tác vụ I/O không chặn | Có thể giữ nhiều kết nối với ít thread | Mọi thao tác chặn phải được xử lý đúng; code async phức tạp hơn |

Không có mô hình tốt nhất cho mọi workload. Tác vụ CPU-bound, I/O-bound, xử lý nền và request latency-sensitive có thể cần cách tổ chức khác nhau.

## 2. Mối quan hệ giữa throughput, latency và concurrency

Ba đại lượng quan trọng:

- **Throughput:** số task hoặc request hoàn tất trong một đơn vị thời gian.
- **Latency:** thời gian từ lúc nhận request đến lúc hoàn tất.
- **Concurrency:** số request hoặc task đang tồn tại trong hệ thống.

Định luật Little mô tả mối quan hệ trong một hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số công việc trung bình đang ở trong hệ thống.
- \(\lambda\) là throughput trung bình, tính theo task/giây.
- \(W\) là thời gian trung bình một task ở trong hệ thống, tính bằng giây.

Ví dụ, một API hoàn tất trung bình 120 request/giây và mỗi request mất 250 ms trong hệ thống. Số request trung bình đang in-flight xấp xỉ:

\[
L = 120 \times 0.25 = 30
\]

Con số 30 là concurrency trung bình quan sát được ở điều kiện đó. Nó không tự động có nghĩa cần cấu hình đúng 30 worker. Một phần thời gian có thể là chờ database hoặc network; một thread có thể phục vụ một request đồng bộ, còn event loop có thể quản lý nhiều request đang chờ I/O.

### Phân biệt service time và response time

Response time gồm thời gian xử lý và thời gian chờ:

\[
Response\ Time = Queue\ Wait + Service\ Time
\]

Nếu service time của một tác vụ chỉ 40 ms nhưng phải đợi 300 ms trong queue, người dùng vẫn thấy latency khoảng 340 ms. Tăng số worker có thể giảm queue wait nếu CPU hoặc dependency còn capacity. Nếu dependency đã bão hòa, tăng worker chỉ đẩy nhiều công việc hơn vào dependency và có thể làm queue ở phía sau tăng.

### Không chỉ nhìn trung bình

Cần theo dõi p50, p95 và p99. Average có thể ổn định trong khi một nhóm request phải chờ rất lâu. Queueing thường làm tail latency tăng nhanh khi mức sử dụng tiến gần 100%.

Khi một tài nguyên gần bão hòa, thời gian chờ có thể tăng phi tuyến. Vì vậy, mục tiêu không phải giữ CPU hoặc worker luôn ở mức 100%, mà là đáp ứng SLO với headroom đủ cho burst và biến động.

## 3. Phân loại workload trước khi chọn worker

### CPU-bound

CPU-bound là workload dành phần lớn thời gian thực hiện tính toán:

- Mã hóa/giải mã hoặc nén dữ liệu.
- Tính toán số học, xử lý ảnh/video.
- Phân tích dữ liệu hoặc chuyển đổi định dạng nặng.
- Tính toán mô hình hoặc xử lý batch CPU-intensive.

Khi CPU-bound, mỗi worker thường chiếm CPU trong phần lớn thời gian task. Tăng số worker vượt số CPU hiệu dụng có thể gây context switching và tranh chấp cache, làm throughput không tăng hoặc giảm.

Điểm khởi đầu thường là số worker gần số CPU hiệu dụng, sau đó benchmark để tìm điểm tối ưu. Một số workload có thể cần ít hơn vì sử dụng bộ nhớ hoặc lock nhiều; một số workload cần hơn một chút nếu có phần chờ ngắn.

### I/O-bound

I/O-bound dành nhiều thời gian chờ:

- Gọi database.
- Gọi API bên ngoài.
- Đọc/ghi file hoặc object storage.
- Chờ message broker.
- Chờ network hoặc dịch vụ khác.

Trong thời gian chờ I/O, thread đồng bộ có thể không sử dụng CPU nhưng vẫn chiếm một worker. Vì vậy, số worker có thể lớn hơn số vCPU để che thời gian chờ.

Tuy nhiên, tăng worker chỉ có ích khi dependency còn capacity. Nếu database chỉ xử lý được 100 query đồng thời mà ứng dụng gửi 1.000 query, thêm worker sẽ làm connection pool và database queue tăng.

### Workload hỗn hợp

Nhiều request vừa tính toán vừa chờ I/O. Nên đo riêng từng giai đoạn nếu có thể:

- CPU time.
- Database wait.
- Network wait.
- File I/O wait.
- Lock wait.
- Queue wait.

Nếu chỉ đo tổng latency, rất khó biết tăng worker hay tối ưu dependency sẽ đem lại lợi ích.

### Bảng định hướng ban đầu

| Đặc tính | Hướng cấu hình ban đầu | Điều cần đo |
|---|---|---|
| CPU-bound | Worker gần CPU hiệu dụng | CPU utilization, throughput, context switch, run queue |
| I/O-bound với I/O đồng bộ | Có thể nhiều worker hơn CPU | Tỷ lệ wait/compute, pool wait, dependency capacity |
| I/O-bound với async | Event loop ít thread, nhiều I/O đang chờ | Event loop lag, in-flight, callback duration |
| Batch dài | Pool riêng và concurrency giới hạn | Job duration, queue age, fairness |
| Request latency-sensitive | Queue ngắn, deadline rõ, overload policy | p95/p99, queue wait, reject rate |

## 4. Ước lượng số worker ban đầu

Không có một công thức duy nhất đúng cho mọi ứng dụng. Có thể dùng các công thức ước lượng để chọn điểm bắt đầu, sau đó đo kiểm.

### CPU-bound

Với tác vụ gần như luôn dùng CPU, số worker ban đầu thường xấp xỉ số CPU hiệu dụng:

\[
N_{workers} \approx N_{CPU}
\]

Nếu tác vụ có thời gian chờ lock, I/O hoặc runtime pause, có thể thử một số cấu hình lớn hơn hoặc nhỏ hơn. Nhưng không nên mặc định nhân đôi worker chỉ để “tận dụng CPU”.

### I/O-bound

Một mô hình ước lượng thường dùng là:

\[
N_{workers} \approx N_{CPU} \times U_{target} \times
\left(1 + \frac{W_{wait}}{W_{compute}}\right)
\]

Trong đó:

- \(N_{CPU}\) là số CPU hiệu dụng.
- \(U_{target}\) là mức CPU utilization mục tiêu, nhỏ hơn hoặc bằng 1.
- \(W_{wait}\) là thời gian chờ I/O trung bình.
- \(W_{compute}\) là thời gian CPU xử lý trung bình.

Ví dụ: VM có 4 CPU hiệu dụng, mục tiêu CPU khoảng 70%, mỗi task dùng CPU 20 ms và chờ I/O 80 ms:

\[
N \approx 4 \times 0.7 \times (1 + 80/20) = 14
\]

14 worker là một điểm thử ban đầu, không phải con số đảm bảo tối ưu. Nếu tất cả worker cùng gọi một database có giới hạn 8 connection, pool database sẽ là giới hạn tiếp theo. Nếu thời gian chờ thay đổi lớn, concurrency cũng cần được kiểm tra ở tải đỉnh.

### Giới hạn bởi dependency

Số worker thực tế không thể được quyết định chỉ từ CPU. Cần xem các giới hạn:

- Số connection database.
- Giới hạn concurrent request của API bên ngoài.
- Số consumer hoặc partition của message broker.
- Giới hạn file descriptor và socket.
- IOPS/throughput của storage.
- Giới hạn rate và quota dịch vụ cloud.
- Số thread hoặc process được phép trong container.

Có thể mô hình hóa concurrency cho một loại công việc như giá trị nhỏ nhất trong các giới hạn phù hợp:

\[
C_{effective} \leq \min(C_{app}, C_{database}, C_{API}, C_{storage}, C_{policy})
\]

Đây là cách suy nghĩ về giới hạn; mỗi dependency có thể có nhiều loại giới hạn và cần đo riêng.

## 5. Xác định số CPU hiệu dụng trong VM và container

Số vCPU hiển thị trong console chưa chắc là số CPU mà process có thể sử dụng liên tục.

### VM và hypervisor

Một VM có thể có 8 vCPU nhưng chịu CPU credit, quota hoặc scheduling contention. Cần xem metric của nền tảng và guest OS:

- vCPU count.
- CPU utilization.
- Steal time nếu guest có thể đo.
- CPU credit balance/consumption trên loại máy burstable.
- Throttling hoặc giới hạn hiệu năng.
- Run queue và latency ứng dụng.

Nếu VM bị giới hạn bởi credit hoặc quota, tăng worker có thể làm nhiều thread tranh nhau phần CPU nhỏ hơn.

### Container và cgroup

Container có thể bị giới hạn CPU bởi cpuset hoặc quota. Ví dụ, node có 16 CPU nhưng container chỉ được cấp quota tương đương 2 CPU. Số worker nên được cân nhắc theo giới hạn của container, không chỉ theo tổng CPU của node.

Trên Linux có thể xem thông tin cgroup tùy phiên bản:

~~~sh
# cgroup v2: quota và period
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective

# cgroup v2: thống kê throttling
cat /sys/fs/cgroup/cpu.stat
~~~

Trong cgroup v2, giá trị cpu.max có dạng quota period; giá trị max thể hiện không đặt quota ở cấp đó. Cần xem cả cgroup cha vì giới hạn có thể được kế thừa.

Với cgroup v1, các file và đường dẫn khác. Kubernetes có thể đặt CPU limit thông qua runtime và cgroup.

### JVM và container awareness

Các JVM hiện đại có thể nhận diện một số giới hạn container và trả về số CPU khả dụng qua Runtime.getRuntime().availableProcessors(). Kết quả phụ thuộc phiên bản JVM, cgroup và cấu hình.

Không giả định mọi runtime hoặc thư viện pool đều tự nhận đúng quota. Hãy kiểm tra giá trị trong container thực tế và so với cpuset/quota. Một số ứng dụng cần cấu hình thread pool rõ ràng thay vì dùng số CPU của host.

## 6. Cấu trúc của một thread pool

Một thread pool thường có các tham số:

- **Core pool size:** số thread nền tảng được giữ ở mức cơ bản.
- **Maximum pool size:** giới hạn trên của số thread.
- **Keep-alive:** thời gian thread vượt core được giữ khi nhàn rỗi.
- **Work queue:** nơi task chờ đến lượt.
- **Rejection policy:** cách xử lý khi pool và queue không nhận thêm task.
- **Thread factory:** cách tạo thread, đặt tên, priority và thuộc tính.
- **Task timeout/deadline:** giới hạn thời gian công việc có thể tiếp tục.
- **Lifecycle:** thời điểm khởi tạo, shutdown và chờ task hoàn tất.

### Pool size và queue hoạt động cùng nhau

Trong Java ThreadPoolExecutor, hành vi tổng quát là:

1. Nếu số thread đang chạy nhỏ hơn core size, pool có thể tạo thread mới.
2. Khi đã đạt core size, task mới thường được đưa vào queue.
3. Khi queue đầy, pool mới tạo thêm thread cho đến maximum size.
4. Khi cả pool đạt maximum và queue đầy, task bị từ chối theo rejection policy.

Vì vậy, một queue không giới hạn có thể khiến maximum pool size hầu như không được sử dụng. Task cứ được xếp vào queue trong khi số thread giữ ở core size.

### Vì sao queue không giới hạn nguy hiểm?

Queue không giới hạn có thể che giấu overload. Khi tốc độ task đến cao hơn tốc độ xử lý:

- Queue tăng liên tục.
- Thời gian chờ tăng.
- Task hết deadline trước khi được chạy.
- RAM tiêu thụ tăng do giữ task và dữ liệu đầu vào.
- GC hoặc paging có thể tăng.
- Hệ thống có thể OOM trước khi báo lỗi rõ ràng.

Queue cần có giới hạn được chọn theo thời gian chờ chấp nhận được và khả năng xử lý burst.

## 7. Cấu hình ThreadPoolExecutor trong Java

Ví dụ sau tạo pool có số worker cố định, queue có giới hạn và từ chối task khi hệ thống đã quá tải:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ApiWorkers {
    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    private final ThreadPoolExecutor executor =
        new ThreadPoolExecutor(
            8,                          // corePoolSize
            8,                          // maximumPoolSize
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(200),
            task -> new Thread(
                task,
                "api-worker-" + SEQUENCE.incrementAndGet()
            ),
            new ThreadPoolExecutor.AbortPolicy()
        );

    public void submit(Runnable task) {
        try {
            executor.execute(task);
        } catch (RejectedExecutionException ex) {
            // Ghi metric và trả lỗi overload phù hợp cho caller.
            throw ex;
        }
    }

    public void shutdown() {
        executor.shutdown();
    }
}
~~~

Số worker 8 và queue 200 chỉ là ví dụ. Cần thay bằng giá trị được đo trong môi trường triển khai. Nếu đây là request path, lớp gọi có thể chuyển rejection thành HTTP 503 hoặc phản hồi overload phù hợp; không nên để exception rơi vào trạng thái không được xử lý.

### Vì sao đặt core bằng maximum?

Pool cố định giúp giới hạn concurrency rõ ràng. Cách này hữu ích khi muốn hành vi ổn định và dễ đo. Nếu workload có burst ngắn, có thể chọn core thấp hơn maximum, nhưng phải hiểu queue và thuật toán tạo thread của ThreadPoolExecutor.

### Chọn rejection policy

Một số policy có sẵn:

- **AbortPolicy:** ném RejectedExecutionException. Caller phải xử lý rõ ràng.
- **CallerRunsPolicy:** thread gọi submit tự chạy task, có thể tạo backpressure bằng cách làm chậm caller. Cần cẩn trọng nếu caller là event loop hoặc thread xử lý request quan trọng.
- **DiscardPolicy:** bỏ task mà không báo lỗi. Chỉ phù hợp nếu mất task đã được chấp nhận là hành vi có chủ đích.
- **DiscardOldestPolicy:** loại task cũ nhất trong queue rồi thử submit task mới. Có thể làm mất công việc quan trọng hoặc phá thứ tự.

Với task nghiệp vụ quan trọng, không dùng policy bỏ task âm thầm. Cần ghi nhận rejection, trả lỗi hoặc lưu công việc vào durable queue phù hợp.

### Cẩn trọng với Executors factory

Executors.newFixedThreadPool() thường sử dụng queue không giới hạn. Executors.newCachedThreadPool() có thể tạo số thread rất lớn khi tải tăng. Các factory này tiện cho ví dụ nhỏ, nhưng production cần kiểm tra queue, maximum thread, timeout và overload behavior.

### Shutdown đúng cách

Khi ứng dụng dừng:

1. Ngừng nhận task mới.
2. Gọi shutdown để không nhận thêm task.
3. Chờ task đang chạy hoàn tất trong thời hạn.
4. Nếu hết thời hạn, hủy task còn lại theo chính sách.
5. Ghi nhận task bị hủy và đảm bảo dữ liệu không ở trạng thái nửa chừng.

Không dùng shutdownNow như thao tác bình thường cho mọi lần restart. Interruption chỉ có tác dụng nếu task và thư viện bên dưới hợp tác xử lý interrupt.

## 8. Virtual threads và concurrency trong Java hiện đại

Virtual threads được chuẩn hóa từ Java 21. Chúng là thread nhẹ do JVM quản lý, giúp viết mã đồng bộ cho workload có nhiều thao tác blocking I/O mà không cần tạo một platform thread cho mỗi tác vụ.

Ví dụ:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestTasks {
    public void handleRequests(Iterable<Runnable> requests) {
        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            for (Runnable request : requests) {
                executor.submit(request);
            }
        }
    }
}
~~~

Ví dụ minh họa mô hình task-per-virtual-thread. Trong ứng dụng thật, cần quản lý thời hạn, lỗi, cancellation và giới hạn tài nguyên phụ thuộc.

### Virtual thread giúp gì?

- Có thể tạo nhiều task đồng bộ mà không cần giữ một platform thread cho mỗi task.
- Code blocking I/O có thể dễ đọc hơn so với callback chain.
- Giảm chi phí thread stack và scheduling so với số lượng rất lớn platform threads.
- Phù hợp với workload nhiều request chờ database hoặc network nếu thư viện tương thích.

### Virtual thread không làm CPU nhanh hơn

Virtual thread không tạo thêm CPU. Nếu 10.000 tác vụ cùng chạy phép tính CPU-bound trên VM có 4 CPU hiệu dụng, chúng vẫn phải chia sẻ 4 CPU đó.

Cần giới hạn concurrency tại dependency như database, API ngoài và file service. Có thể dùng connection pool, semaphore hoặc rate limiter. Không nên tạo hàng nghìn virtual thread rồi để tất cả cùng gọi database nếu database chỉ có thể phục vụ một số lượng connection nhỏ.

### Pinning và thư viện blocking

Một số thao tác có thể giữ carrier thread trong khi virtual thread bị block, tùy JDK và cách sử dụng monitor/native call. Cần kiểm tra hành vi pinning trên phiên bản JVM mục tiêu, cập nhật JDK và dùng công cụ chẩn đoán phù hợp.

Không mặc định mọi thư viện cũ đều tối ưu cho virtual threads. Hãy benchmark cùng workload, dependency và cấu hình production.

### Có nên pool virtual threads?

Thông thường không cần tạo pool để tái sử dụng virtual thread. Mô hình thường dùng là tạo một virtual thread cho mỗi task, rồi giới hạn tài nguyên thực sự khan hiếm bằng semaphore hoặc connection pool. Pooling virtual threads có thể làm mất lợi ích đơn giản của mô hình này.

## 9. Async, event loop và ForkJoinPool

Không phải mọi concurrency đều cần thread pool lớn.

### Event loop

Một event loop có thể quản lý nhiều kết nối bằng non-blocking I/O. Khi một tác vụ chờ network, event loop chuyển sang tác vụ khác thay vì giữ thread chờ.

Một thao tác blocking trên event loop có thể làm tất cả request khác cùng loop bị chậm. Vì vậy:

- Không gọi API blocking trực tiếp trên event loop.
- Đưa tác vụ blocking sang executor riêng.
- Giữ callback ngắn và tránh tính toán CPU nặng trên loop.
- Theo dõi event loop lag và thời gian callback.

### ForkJoinPool

ForkJoinPool dùng work-stealing để xử lý các task có thể chia nhỏ, thường phù hợp với parallel computation. Common pool có thể được dùng ngầm bởi một số API như parallel streams hoặc CompletableFuture async methods không chỉ định executor.

Không nên đưa I/O blocking dài vào common pool mà không hiểu tác động. Các task blocking có thể chiếm worker và làm chậm công việc khác. Dùng executor riêng cho tác vụ blocking hoặc cơ chế quản lý blocking được runtime hỗ trợ.

### CompletableFuture

Nếu dùng CompletableFuture, chỉ định executor phù hợp cho tác vụ CPU hoặc blocking. Không để mọi loại công việc dùng chung pool mặc định nếu workload có thời gian chạy và mức độ ưu tiên khác nhau.

Ví dụ:

~~~java
CompletableFuture.supplyAsync(
    () -> calculateReport(),
    cpuExecutor
);

CompletableFuture.supplyAsync(
    () -> callLegacyBlockingService(),
    ioExecutor
);
~~~

Tách executor giúp CPU task không bị chiếm chỗ bởi request đang chờ I/O.

## 10. Queue, backpressure và overload control

Thread pool chỉ là một phần của hệ thống queueing. Request có thể chờ ở load balancer, web server, executor, connection pool, database, broker hoặc downstream service.

### Bounded queue

Queue có giới hạn giúp hệ thống từ chối hoặc điều tiết tải trước khi RAM bị tiêu thụ vô hạn. Kích thước queue nên liên hệ với thời gian chờ tối đa và tốc độ xử lý.

Theo định luật Little, số task trung bình trong queue gần bằng tốc độ đến nhân thời gian chờ trong queue. Nếu service có thể xử lý 100 task/giây và chỉ chấp nhận queue wait 0,5 giây, queue khoảng 50 task đã tương ứng với nửa giây chờ ở tốc độ đó. Đây chỉ là ước lượng; burst, service time biến động và nhiều worker khiến phân phối chờ phức tạp hơn.

Không chọn queue capacity chỉ vì RAM còn trống. Queue lớn có thể làm request chờ quá deadline và giữ nhiều object trong heap.

### Backpressure

Backpressure là cơ chế làm chậm nguồn phát hoặc từ chối công việc khi downstream không theo kịp.

Các cách triển khai:

- Từ chối sớm với HTTP 429 hoặc 503.
- Giới hạn số request in-flight.
- Dùng semaphore để giới hạn truy cập dependency.
- Điều chỉnh tốc độ producer/consumer.
- Dùng bounded queue.
- Dùng token bucket hoặc leaky bucket rate limiter.
- Đặt deadline và hủy task đã quá hạn.
- Tạm dừng nhận message khi consumer backlog vượt ngưỡng.

### Deadline và timeout

Một request có deadline 1 giây không nên chờ 5 giây trong queue rồi mới bắt đầu. Khi đưa task vào queue, cần cân nhắc thời gian còn lại của deadline. Nếu task đã hết hạn, loại bỏ sớm để không tiêu tốn tài nguyên vô ích.

Timeout nên được truyền xuyên suốt các dependency, nhưng mỗi tầng cần chừa thời gian cho phần còn lại. Ví dụ, request timeout 2 giây thì database query không nên được phép chạy 5 giây.

### Load shedding

Khi quá tải, hệ thống có thể ưu tiên request quan trọng và từ chối request ít ưu tiên. Cần xác định rõ:

- Loại request được bảo vệ.
- Loại request có thể trì hoãn hoặc từ chối.
- Ngưỡng kích hoạt.
- Phản hồi cho client.
- Metric và log cần ghi.
- Cách phục hồi khi tải giảm.

Không nên chỉ tăng timeout để che overload. Timeout dài hơn thường làm request và connection tồn tại lâu hơn, tăng concurrency và khiến quá tải nặng thêm.

## 11. Tối ưu connection pool và giới hạn dependency

Thread pool và connection pool là hai tài nguyên khác nhau.

Một worker có thể cần connection database trong một phần task. Nếu pool database chỉ có 10 connection, tối đa 10 thao tác có thể giữ connection cùng lúc dù thread pool có 100 worker. Các worker còn lại có thể chờ connection.

### Chọn kích thước database pool

Cần xem:

- Giới hạn connection của database.
- Số replica ứng dụng.
- Số pool trong mỗi replica.
- Connection dành cho migration, monitoring và admin.
- Thời gian query và tỷ lệ connection được sử dụng.
- CPU, I/O và lock contention ở database.
- Số transaction đồng thời thực sự cần thiết.

Tổng connection tiềm năng cần được tính ở cấp toàn hệ thống:

\[
Connections_{total} =
Replicas \times PoolSizePerReplica + OtherClients
\]

Ví dụ, 12 replica mỗi replica có pool 20 connection có thể mở tới 240 connection, chưa kể worker, migration và công cụ quản trị. Con số này có thể vượt giới hạn database dù mỗi replica nhìn riêng đều hợp lý.

### Không đặt pool database bằng thread count một cách máy móc

Nếu query ngắn và database có capacity tốt, pool nhỏ có thể đạt throughput cao. Nếu query dài hoặc database đã bão hòa, tăng connection chỉ làm tăng context switching, lock và memory ở database.

Đo connection acquisition wait, active/idle connection, query duration, transaction duration và database CPU/IO.

### Tách pool theo dependency

Một dịch vụ có thể gọi database, API thanh toán và object storage. Nếu tất cả dùng cùng một pool, dependency chậm có thể chiếm hết worker và làm request khác bị đói tài nguyên.

Có thể dùng:

- Executor riêng theo loại workload.
- Semaphore riêng cho dependency.
- Connection pool riêng.
- Timeout và circuit breaker riêng.
- Giới hạn in-flight theo downstream.

Tách pool cần có giới hạn tổng để tránh tạo quá nhiều thread và connection.

## 12. Bulkhead, ưu tiên và tránh thread starvation

Bulkhead chia hệ thống thành các vùng tài nguyên độc lập. Khi một dependency hoặc loại task gặp sự cố, nó không chiếm hết worker của toàn bộ ứng dụng.

Ví dụ:

- Pool cho request đọc dữ liệu.
- Pool cho request ghi dữ liệu.
- Pool cho tác vụ batch.
- Pool cho tác vụ gọi API ngoài.
- Pool riêng cho tác vụ nền không nhạy latency.

### Thread starvation

Thread starvation xảy ra khi task cần một worker nhưng tất cả worker đang bị chiếm bởi task khác. Ví dụ, task cha submit task con vào cùng pool rồi chờ Future của task con; nếu mọi worker đều đang chờ, task con không có worker để chạy.

Cách giảm rủi ro:

- Tránh blocking wait trong cùng pool khi task con cần pool đó.
- Dùng async composition thay vì chờ đồng bộ.
- Dùng executor phù hợp cho task lồng nhau.
- Giữ task ngắn và không giữ worker trong lúc chờ dependency quá lâu.
- Theo dõi active worker, queue wait và task duration.

### Ưu tiên task

Không phải mọi queue đều cần priority. Priority queue có thể khiến task ưu tiên thấp bị starvation. Nếu cần ưu tiên, nên đặt giới hạn cho từng lớp, đảm bảo fairness và theo dõi tuổi của task lâu nhất.

Với request đồng bộ, tách traffic quan trọng và không quan trọng bằng route hoặc pool riêng thường dễ vận hành hơn một queue priority phức tạp.

## 13. Concurrency trong Kubernetes và autoscaling

Kubernetes thêm các lớp giới hạn và điều phối.

### CPU request và limit

- CPU request ảnh hưởng việc scheduler chọn node và cách phân bổ tài nguyên.
- CPU limit đặt mức tối đa CPU container có thể sử dụng theo cơ chế cgroup.
- CPU throttling có thể xảy ra khi container chạm quota dù node vẫn còn CPU idle.

Nếu ứng dụng tự chọn thread count theo CPU của node thay vì CPU container, pool có thể lớn hơn khả năng được cấp. Cần kiểm tra JVM/container awareness và metric throttling.

### Pod replicas và tổng concurrency

Nếu mỗi pod có pool 20 worker và deployment có 10 replica, tổng concurrency lý thuyết của pool là 200 worker. Nếu mỗi worker có thể mở một database connection, tổng connection có thể vượt giới hạn database.

Khi autoscaler tăng replica, tổng connection và concurrency tăng theo. Vì vậy, giới hạn cần được tính ở cấp cluster và dependency, không chỉ ở một pod.

### HPA và queue depth

Horizontal Pod Autoscaler có thể tăng replica dựa trên CPU, memory hoặc custom/external metrics. Với worker tiêu thụ message, queue depth hoặc oldest message age có thể là tín hiệu tốt hơn CPU.

Tuy nhiên, autoscaling có độ trễ: pod mới cần schedule, pull image, bootstrap và warm-up. Queue có thể tăng trước khi capacity mới sẵn sàng. Cần giữ headroom, scale policy và cooldown hợp lý.

### VPA và node autoscaling

VPA điều chỉnh request/limit theo policy và metric; việc áp dụng có thể yêu cầu pod restart tùy chế độ. Node autoscaler bổ sung hoặc loại node khi scheduler không thể xếp pod hoặc node dư tài nguyên.

Các cơ chế này không tự chọn thread pool tối ưu cho ứng dụng. Pool vẫn cần cấu hình phù hợp với CPU quota, memory limit và dependency.

### Graceful shutdown

Khi pod bị scale down hoặc node bảo trì:

- Ngừng nhận request mới.
- Đánh dấu readiness false.
- Drain request đang xử lý.
- Dừng consumer hoặc ngừng nhận message.
- Hoàn tất hoặc lưu checkpoint job.
- Đóng executor và connection pool.
- Thoát trong termination grace period.

Nếu ứng dụng không drain đúng cách, task đang chạy có thể bị ngắt giữa chừng hoặc message được xử lý lặp.

## 14. Concurrency trong serverless

Serverless thường có khái niệm concurrency ở cấp function instance, execution environment hoặc request đồng thời.

Cần phân biệt:

- Concurrency tối đa của function.
- Số execution environment đang hoạt động.
- Concurrency được đặt trước hoặc reserved.
- Số request mà một instance có thể xử lý đồng thời.
- Giới hạn downstream như database connection và API rate.

Một số nền tảng xử lý một invocation trên mỗi execution environment, một số runtime có thể hỗ trợ nhiều request đồng thời. Hành vi phụ thuộc dịch vụ, runtime và cấu hình.

Nếu function scale out nhanh, tổng số connection tới database có thể tăng đột biến. Cần connection proxy, pooler, giới hạn concurrency hoặc kiến trúc queue/batch phù hợp.

Đặt concurrency thấp có thể bảo vệ dependency nhưng làm tăng queue hoặc throttling ở nền tảng. Đặt quá cao có thể gây overload downstream. Đo cold start, duration, concurrent executions, throttles, retries và connection usage.

## 15. Metric cần theo dõi khi tuning worker và thread pool

Một dashboard tuning nên có cả metric pool, runtime, tài nguyên và ứng dụng.

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Pool | Current pool size, active threads, idle threads | Pool đang dùng bao nhiêu worker |
| Pool | Queue depth, oldest task age, queue wait | Công việc đang chờ bao lâu |
| Pool | Completed tasks, rejected tasks | Năng lực và overload |
| Task | Service time, task duration, timeout/cancel | Thời gian xử lý và task hết hạn |
| CPU | Utilization, run queue, throttling, steal | Worker có đủ CPU hay đang tranh chấp |
| Memory | Heap, RSS, thread stack, GC, OOM | Chi phí bộ nhớ của concurrency |
| Runtime | Context switches, thread count, lock contention | Overhead do nhiều thread |
| Dependency | DB pool active/wait, query latency, API rate limit | Downstream có trở thành bottleneck không |
| Application | Throughput, error rate, p95/p99 | Tác động thực tế đến người dùng |
| Queue | Backlog, enqueue/dequeue rate, oldest message age | Producer và consumer có cân bằng không |

### Diễn giải một số mẫu

- Active threads bằng maximum, queue tăng và CPU cao: có thể thiếu CPU hoặc task tính toán quá nặng.
- Active threads bằng maximum, queue tăng nhưng CPU thấp: có thể worker đang chờ dependency hoặc lock.
- Queue thấp, active threads thấp nhưng latency cao: điều tra dependency, DNS, network hoặc thời gian xử lý bên ngoài.
- Rejection tăng: pool/queue đã đạt giới hạn; kiểm tra overload policy và capacity.
- Thread count tăng, context switch tăng nhưng throughput không tăng: có thể oversubscription.
- DB pool wait tăng trong khi worker queue tăng: giới hạn database connection có thể là bottleneck.

### Theo dõi p95/p99 queue wait

Đo riêng queue wait và service time giúp xác định thời gian bị mất ở đâu. Nếu service time ổn định nhưng queue wait tăng, pool hoặc admission control cần được xem xét. Nếu queue wait thấp nhưng service time tăng, cần điều tra task hoặc dependency.

## 16. Quy trình tuning bằng load test

Không tối ưu pool chỉ bằng cảm giác hoặc một lần chạy benchmark.

### Bước 1: xác định SLO và workload

Ghi rõ:

- Request/transaction rate mục tiêu.
- p95/p99 latency tối đa.
- Error rate chấp nhận được.
- Tỷ lệ CPU và memory có thể dùng.
- Loại request và phân phối kích thước task.
- Dependency và giới hạn của chúng.
- Burst, seasonality và thời gian duy trì tải.

### Bước 2: đo baseline

Với cấu hình hiện tại, thu:

- Throughput và p50/p95/p99.
- CPU và throttling.
- RAM, heap, GC và thread count.
- Pool active, queue, reject.
- DB/API connection wait.
- Disk/network và dependency latency.

Không thay đổi nhiều tham số cùng lúc. Nếu đổi pool size, queue size, DB pool và CPU limit trong cùng lần thử, sẽ khó biết nguyên nhân kết quả.

### Bước 3: chọn điểm bắt đầu

- CPU-bound: bắt đầu gần CPU hiệu dụng.
- I/O-bound: ước lượng theo tỷ lệ wait/compute, nhưng giới hạn theo dependency.
- Async: giữ event loop ít thread, giới hạn in-flight và tách blocking work.
- Batch: pool riêng, queue có giới hạn và cơ chế checkpoint.

### Bước 4: tăng tải có kiểm soát

Dùng các kiểu tải phù hợp:

- **Load test:** tải dự kiến trong vận hành.
- **Stress test:** tăng dần tới khi hệ thống mất SLO hoặc chạm giới hạn.
- **Spike test:** tăng tải đột ngột.
- **Soak test:** giữ tải lâu để phát hiện leak, queue tăng hoặc degradation.
- **Capacity test:** tìm throughput tối đa vẫn đáp ứng SLO.

Dùng cả mô hình closed-loop và open-loop khi phù hợp. Closed-loop client gửi request mới sau khi request trước hoàn tất, nên có thể che khuất latency khi server quá chậm. Open-loop giữ tốc độ đến độc lập với response, giúp phát hiện overload và queue buildup rõ hơn.

### Bước 5: thử nhiều cấu hình

Ví dụ thử worker 4, 8, 12, 16 trong cùng điều kiện. Mỗi lần cần:

1. Khởi động từ trạng thái ổn định.
2. Warm-up runtime và cache.
3. Chạy tải theo thời gian cố định.
4. Ghi metric ở mọi lớp.
5. Kiểm tra SLO và error.
6. Ghi chi phí tài nguyên.
7. Lặp lại để giảm ảnh hưởng ngẫu nhiên.

### Bước 6: chọn điểm vận hành

Chọn cấu hình đáp ứng SLO với headroom, không nhất thiết là cấu hình có throughput tối đa trong một thời điểm ngắn. Kiểm tra cả tải burst, dependency slowdown, replica restart và autoscaling.

### Bước 7: triển khai canary và theo dõi

Thay đổi pool trên một nhóm nhỏ instance/pod trước. Theo dõi latency, rejection, CPU, memory, dependency và error rate. Có phương án rollback cấu hình nếu kết quả xấu.

## 17. Ví dụ: tối ưu thread pool cho API gọi database

Một API chạy trên VM 4 vCPU. Mỗi request thực hiện khoảng 15 ms CPU và 85 ms chờ database. Tải mục tiêu là 80 request/giây. Database cho phép ứng dụng dùng tối đa 12 connection.

Ước lượng ban đầu với mục tiêu CPU 70%:

\[
N \approx 4 \times 0.7 \times (1 + 85/15)
\]

\[
N \approx 18.7
\]

Có thể thử khoảng 16 đến 20 worker trong benchmark. Nhưng database pool chỉ có 12 connection, do đó số thao tác query đồng thời vẫn bị giới hạn bởi pool đó. Nếu mỗi request giữ connection trong phần lớn 85 ms, 12 connection có thể trở thành giới hạn throughput.

Nhóm thử ba cấu hình:

| Cấu hình | Worker | DB connections | Kết quả cần quan sát |
|---|---:|---:|---|
| A | 8 | 8 | CPU, DB pool wait, queue wait, p95 |
| B | 16 | 12 | Throughput, DB active/wait, p99 |
| C | 24 | 12 | Rejection, queue, context switch, DB saturation |

Giả sử cấu hình B đạt SLO và cấu hình C không tăng throughput nhưng làm queue wait và p99 cao hơn. Cấu hình B là điểm vận hành tốt hơn dù có ít worker hơn. Nhóm có thể tiếp tục giảm thời gian query hoặc tăng capacity database nếu cần thêm throughput.

Các con số trong ví dụ là giả định để minh họa quy trình. Kết quả thực tế phụ thuộc thời gian query, tỷ lệ cache, transaction, lock và giới hạn database.

## 18. Những lỗi tuning thường gặp

### Tăng worker khi CPU đã bão hòa

Khi CPU gần 100% và run queue cao, thêm worker có thể làm context switching tăng. Hãy profile CPU, tối ưu thuật toán hoặc tăng CPU capacity khi workload thực sự cần.

### Dùng queue không giới hạn

Queue tăng vô hạn làm latency và memory tăng. Chọn queue bounded, deadline và rejection policy.

### Chỉ xem CPU trung bình

CPU trung bình thấp có thể che một core bão hòa hoặc container bị throttling. Xem per-core, run queue, quota và ứng dụng.

### Mở quá nhiều database connection

Mỗi replica có thể có pool riêng. Scale out làm tổng connection tăng. Tính giới hạn toàn cluster và xem database CPU, lock, memory.

### Dùng chung pool cho task không đồng nhất

Task batch dài có thể chiếm worker của request ngắn. Tách pool hoặc giới hạn từng loại workload.

### Retry không giới hạn

Khi dependency chậm, retry đồng loạt tạo thêm tải và làm sự cố lan rộng. Dùng exponential backoff có jitter, giới hạn retry và deadline.

### Timeout quá dài

Request giữ worker và connection lâu hơn, làm concurrency tăng. Đặt timeout theo SLO và dependency budget.

### Không tính memory của thread

Platform thread có stack và overhead riêng. Tăng hàng nghìn thread có thể làm RAM tiêu thụ lớn dù CPU không cao. Theo dõi thread count, RSS, native memory và stack.

### Tuning chỉ trên môi trường dev

Máy dev thường khác CPU quota, network, database, volume, số replica và tải thực tế. Benchmark cần gần với cấu hình production và có thể lặp lại.

## 19. Checklist cấu hình worker và concurrency

### Trước khi cấu hình

- [ ] Đã phân loại task CPU-bound, I/O-bound, async hoặc batch.
- [ ] Đã đo service time, wait time và throughput.
- [ ] Đã xác định CPU hiệu dụng của VM/container.
- [ ] Đã kiểm tra CPU quota, cpuset, credit và throttling.
- [ ] Đã xác định giới hạn database, API, storage và broker.
- [ ] Đã xác định SLO p95/p99 và deadline.
- [ ] Đã tính tổng concurrency khi scale nhiều replica.

### Khi cấu hình pool

- [ ] Core/max thread có lý do và có thể đo.
- [ ] Queue có giới hạn.
- [ ] Rejection policy được xử lý rõ ràng.
- [ ] Có timeout, cancellation và graceful shutdown.
- [ ] Tác vụ CPU và blocking I/O được tách khi cần.
- [ ] Có bulkhead cho dependency quan trọng.
- [ ] DB connection pool không vượt giới hạn toàn hệ thống.
- [ ] Virtual thread hoặc event loop được dùng đúng loại workload.
- [ ] Không có task lồng nhau gây starvation.

### Khi kiểm thử và vận hành

- [ ] Đã đo baseline trước khi thay đổi.
- [ ] Đã thử nhiều mức worker trong điều kiện tải tương đương.
- [ ] Đã đo queue wait riêng với service time.
- [ ] Đã theo dõi active worker, queue, reject và task duration.
- [ ] Đã theo dõi CPU, memory, GC, context switch và throttling.
- [ ] Đã theo dõi connection pool và dependency latency.
- [ ] Đã chạy load, stress, spike và soak test phù hợp.
- [ ] Đã kiểm tra overload, backpressure và load shedding.
- [ ] Đã triển khai canary và có rollback.
- [ ] Đã ghi lại cấu hình tối ưu cùng workload và kết quả benchmark.

## Kết luận

Số worker và thread pool phải phù hợp với loại workload, CPU hiệu dụng, thời gian chờ và giới hạn dependency. CPU-bound thường bắt đầu gần số CPU; I/O-bound có thể cần concurrency cao hơn nhưng phải kiểm soát database, network và queue. Định luật Little giúp ước lượng số công việc in-flight, còn load test xác định điểm vận hành thực tế. Thread pool cần queue bounded, rejection policy và timeout rõ ràng; virtual threads giúp quản lý nhiều tác vụ blocking nhưng không tạo thêm năng lực CPU. Khi theo dõi đồng thời queue wait, service time, throughput, p95/p99, throttling và dependency pool, đội vận hành có thể tăng concurrency đúng chỗ, giữ backpressure và bảo vệ SLO khi tải tăng.
