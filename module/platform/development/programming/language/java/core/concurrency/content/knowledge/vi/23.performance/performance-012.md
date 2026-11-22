# Giới hạn tài nguyên và backpressure để bảo vệ hệ thống

Trong hệ thống Java chạy đồng thời, thêm thread hoặc tiếp nhận thêm task không làm thông lượng tăng vô hạn. CPU có số lõi hữu hạn, heap không thể chứa queue tăng mãi, database chỉ có một lượng connection nhất định, còn API bên ngoài có quota và độ trễ. Khi số việc đến vượt khả năng xử lý trong một khoảng đủ lâu, backlog tăng, response chậm, timeout và retry tạo ra tải mới. **Giới hạn tài nguyên** giữ số công việc đang chiếm tài nguyên trong mức an toàn; **backpressure** truyền tín hiệu bên nhận không theo kịp trở lại bên phát để điều chỉnh nhịp gửi.

Bài này nói về concurrency trong **Java nói chung**, gồm `Executor`, `BlockingQueue`, `Semaphore`, điều khiển tốc độ và `java.util.concurrent.Flow`. Cơ chế tích hợp chuyên biệt với Spring thuộc một chương khác.

## 1. Mô hình tải: producer, queue, worker, downstream

```text
Producer(s) -- admission / demand --> [ bounded queue ] --> Worker(s)
     ^                                                   |
     |<-- accepted / back off / rejected / completed ----|
                                                         v
                                               CPU / DB / API / disk
```

- **Producer** là nơi phát sinh việc: HTTP handler, scheduler, listener, batch importer hoặc thread gọi `execute()`.
- **Queue** đệm burst ngắn và giữ task chưa chạy; queue không tự tăng công suất xử lý.
- **Worker/consumer** thực hiện việc. Số worker không nhất thiết bằng số tác vụ có thể chạy an toàn trên downstream.
- **Admission control** quyết định nhận ngay, chờ có giới hạn, từ chối hoặc hạ cấp khi hệ thống đầy.
- **Backpressure** cho producer biết khả năng nhận tiếp của downstream. Khi có giao thức điều khiển demand, bên nhận tự chỉ định lượng dữ liệu muốn nhận.

Một queue hữu hạn có từ chối task giúp hạn chế backlog nhưng **chưa phải một giao thức backpressure trọn vẹn** nếu producer phớt lờ tín hiệu rồi phát lại vô hạn. Ngược lại, queue có thể được giới hạn và task bị reject nhanh mà không cần producer có khả năng tạm dừng: điều quan trọng là hợp đồng quá tải minh bạch.

## 2. Phân biệt throughput, concurrency, queue depth và rate

| Khái niệm | Câu hỏi | Chỉ số |
|---|---|---|
| Arrival rate | Mỗi giây có bao nhiêu task mới? | `incoming/s` |
| Throughput | Mỗi giây hoàn tất bao nhiêu task? | `completed/s` |
| In-flight concurrency | Có bao nhiêu task đang chạy/giữ tài nguyên? | Active requests, active threads, permits |
| Backlog | Có bao nhiêu task đã nhận nhưng chưa xử lý? | Queue size |
| Queue wait | Task mất bao lâu trước khi được worker lấy? | p50/p95/p99 thời gian chờ |
| Service time | Bản thân việc thực thi lâu bao nhiêu? | p50/p95/p99 xử lý |
| End-to-end latency | Từ lúc yêu cầu tới lúc có kết quả mất bao lâu? | Queue + service + network |
| Rejection/drop | Bao nhiêu việc không được nhận hoặc bị bỏ? | Rejected/s, dropped/s |

Nếu arrival rate 120 task/giây nhưng downstream xử lý tối đa 100 task/giây, backlog tăng xấp xỉ 20 task mỗi giây khi trạng thái này kéo dài. Queue lớn chỉ kéo dài thời gian trước khi đầy và tăng tail latency.

Trong hệ thống ổn định, định luật Little: `L = λ × W`, với `L` là số công việc trung bình đang ở trong hệ thống, `λ` là **tốc độ hoàn tất thực tế**, và `W` là thời gian trung bình một công việc tồn tại trong hệ thống. Ví dụ throughput 80 request/giây, thời gian end-to-end trung bình 0,25 giây, thì có khoảng `80 × 0,25 = 20` request trong hệ thống. Phải đo cùng phạm vi: nếu `L` chỉ đếm task chạy thì `W` phải là thời gian thực thi, không phải cả lúc chờ queue. Đừng lấy arrival rate đang vượt throughput để suy ra trạng thái ổn định giả.

**Queue nên được chọn theo giới hạn thời gian chờ và bộ nhớ**, không chỉ theo số phần tử. Một queue 1.000 phần tử không hữu ích nếu tác vụ ở cuối phải đợi 30 giây trong khi client chỉ chờ 2 giây. Mỗi task cũng có thể giữ một object graph lớn, nên 1.000 `Runnable` không tương đương một lượng RAM cố định.

## 3. Executor với queue hữu hạn

`Executors.newFixedThreadPool(n)` giới hạn số worker, nhưng queue nội bộ (`LinkedBlockingQueue`) không giới hạn sức chứa bằng tham số constructor của factory, nên số task chờ có thể tăng đến khi hết bộ nhớ. `Executors.newCachedThreadPool()` có thể tăng số thread theo tải, không nên xem là một giới hạn tài nguyên. Khi cần kiểm soát cả worker và backlog, tạo `ThreadPoolExecutor` với queue hữu hạn và chính sách từ chối rõ ràng.

Hành vi đáng nhớ của `ThreadPoolExecutor`: trước hết tạo worker đến `corePoolSize`; khi đã đủ core threads, ưu tiên đưa việc vào queue; **khi queue không nhận thêm**, mới mở rộng worker đến `maximumPoolSize`; sau đó reject nếu vẫn hết chỗ. Do vậy nếu muốn tránh latency queue tăng trước khi scale thread, phải cân nhắc thiết kế kích thước queue và core/max; không mặc định max threads sẽ được dùng ngay.

### Ví dụ Java 17 hoàn chỉnh: từ chối task khi đầy

Tạo file `BoundedExecutorDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> first = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // Worker duy nhất đang chạy task thứ nhất.
            Future<?> second = pool.submit(() -> { }); // Queue đầy: 1/1.

            try {
                pool.submit(() -> { }); // Không còn worker/queue trống.
                System.out.println("Không mong đợi: nhận task thứ ba");
            } catch (RejectedExecutionException e) {
                System.out.println("Task thứ ba bị từ chối");
            }

            release.countDown();
            first.get();
            second.get();
            System.out.println("Hai task được hoàn thành");
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac BoundedExecutorDemo.java
java BoundedExecutorDemo
```

Đầu ra xác định:

```text
Task thứ ba bị từ chối
Hai task được hoàn thành
```

`CountDownLatch` đồng bộ điểm task thứ nhất đã chiếm worker, nên task thứ hai nằm trong hàng đợi và task thứ ba chắc chắn chạm giới hạn. Với `AbortPolicy`, `RejectedExecutionException` xuất hiện tại **`submit()`**, không phải khi gọi `Future.get()`. Dù task thứ ba không được nhận, hai task đầu vẫn hoàn tất. Cách demo dùng `awaitTermination` và `shutdownNow` để kết thúc tài nguyên; trong ứng dụng thực tế cần thiết kế shutdown theo hợp đồng việc chưa hoàn thành, thay vì hủy bỏ tùy tiện.

### Chính sách từ chối khi đầy

| Chính sách | Hành vi | Lưu ý |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller có thể phản hồi quá tải hoặc retry có giới hạn |
| `CallerRunsPolicy` | Caller thực thi task khi pool còn hoạt động | Tạo giảm tốc tự nhiên nhưng có thể khóa thread gọi; khi executor shutdown có thể bỏ task |
| `DiscardPolicy` | Bỏ task mà không báo lỗi | Chỉ dùng khi có thể mất task; `Future` của task bị bỏ có thể không hoàn tất |
| `DiscardOldestPolicy` | Bỏ task ở đầu queue rồi thử đưa task mới | Có thể phá thứ tự, mất việc cũ hoặc gây starvation |
| Handler do ứng dụng viết | Có thể chờ timeout, trả lỗi hay chuyển sang durable queue | Cần tránh deadlock, blocking trên event loop và race với shutdown |

Không chọn `DiscardPolicy` cho tác vụ cần bảo toàn (đơn hàng, thanh toán, cập nhật dữ liệu quan trọng). `CallerRunsPolicy` cũng không bảo đảm mọi task sẽ được xử lý sau khi shutdown. Nếu một worker của pool lại nộp việc vào chính pool đầy và **chờ** slot để nộp task con, có thể deadlock vì mọi worker đều bận chờ một queue chẳng ai tiêu thụ.

## 4. Semaphore: giới hạn đúng loại tài nguyên khan hiếm

Thread pool kiểm soát số thread trong pool, nhưng một ứng dụng có thể có nhiều executor, callback bất đồng bộ hoặc virtual threads. Nếu điều cần bảo vệ là **8 request đồng thời tới một API**, hãy dùng `Semaphore` gần nơi gọi API.

Ví dụ class Java có thể biên dịch, không có `main`:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class ApiGate {
    private final Semaphore permits = new Semaphore(8, true);

    String call() throws InterruptedException {
        if (!permits.tryAcquire(200, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Downstream đang quá tải");
        }
        try {
            return callApi();
        } finally {
            permits.release();
        }
    }

    private String callApi() {
        return "OK"; // Minh họa: thay bằng API thực tế.
    }
}
```

`tryAcquire(timeout)` khiến caller chỉ chờ tối đa thời gian cho phép; nếu không lấy được permit thì từ chối. `finally` giải phóng permit cả khi `callApi()` ném lỗi. **Không bao giờ release khi acquire thất bại**, và không thực hiện lời gọi tốn tài nguyên trước khi acquire. Nếu `tryAcquire` bị interrupt, `InterruptedException` lan ra; nhánh này không giữ permit. Fairness `true` giảm hiện tượng chờ quá lâu trong nhiều trường hợp nhưng có chi phí hiệu năng, không bảo đảm thứ tự tuyệt đối ở mọi điểm.

Permit trong `Semaphore` chỉ có tác dụng **trong một JVM**. Nếu có 5 instance và mỗi instance cho 8 kết nối, hệ thống có thể phát tới 40 kết nối đồng thời. Muốn bảo vệ quota toàn cụm cần giới hạn phối hợp (tại gateway, dịch vụ dùng chung, distributed limiter hoặc phân quota có kiểm chứng).

**Virtual threads Java 21+** làm cho việc chờ I/O rẻ hơn về số platform threads nhưng không tạo thêm CPU, database connections, socket quota hay năng lực API bên ngoài. Chúng vẫn cần semaphore, admission limit, deadline và quản lý backlog.

## 5. Rate limit và concurrency limit giải quyết hai vấn đề khác nhau

`Semaphore(8)` cho tối đa 8 tác vụ **đang diễn ra**; một API quota 100 request/giây lại giới hạn số **request được bắt đầu theo thời gian**. Nếu request chỉ mất 1 ms, 8 permit vẫn có thể thông qua hàng nghìn request/giây; nếu mỗi request mất 10 giây, rate 100/s vẫn có thể dẫn tới quá nhiều request đồng thời.

Các kỹ thuật thường dùng:

- **Token bucket:** nhận token với tốc độ trung bình `r`, tối đa `burstCapacity`. Mỗi request tiêu token. Cho phép burst hữu hạn, chặn tốc độ dài hạn.
- **Leaky bucket:** phát request ở nhịp ổn định, có giới hạn bộ đệm/chờ.
- **Fixed-window hoặc sliding-window counter:** giới hạn số lần gọi trong cửa sổ; fixed-window có thể cho burst tại ranh giới hai cửa sổ.
- **Concurrency limiter:** dùng semaphore, worker cap hoặc adaptive in-flight cap; bảo vệ tài nguyên đang bị giữ bởi request chậm.

Hệ thống thường cần kết hợp **rate limit + concurrency limit + bounded queue**. Rate limiter cục bộ trên mỗi JVM không phải quota toàn cụm. Khi tự viết token bucket, nên dùng đồng hồ monotonic để tính elapsed time thay vì phụ thuộc wall clock có thể chỉnh, và kiểm soát overflow, phép làm tròn token.

## 6. Backpressure qua `java.util.concurrent.Flow`

Java 9+ có `Flow.Publisher`, `Flow.Subscriber`, `Flow.Subscription` và `Flow.Processor`. Subscriber xác định nhu cầu bằng `subscription.request(n)`; publisher tuân thủ hợp đồng chỉ gửi `onNext` theo demand dương còn lại, sau khi đã phát sinh subscription. Đây là cơ chế kiểm soát theo tín hiệu có cấu trúc.

```text
Publisher ---- onSubscribe(subscription) --> Subscriber
Publisher <----------- request(1) --------- Subscriber
Publisher ---------------- onNext(item) ---> Subscriber
Publisher <----------- request(1) --------- Subscriber
                  ...
Publisher ------------ onComplete() ------- Subscriber
         hoặc onError(error)
```

Class `OneAtATimeSubscriber.java` dưới đây có thể biên dịch độc lập nhưng không có `main`. Nó chỉ request thêm sau khi `process` đồng bộ kết thúc:

```java
import java.util.concurrent.Flow;

final class OneAtATimeSubscriber<T> implements Flow.Subscriber<T> {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        this.subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(T item) {
        try {
            process(item);
            subscription.request(1);
        } catch (RuntimeException error) {
            subscription.cancel();
            onError(error);
        }
    }

    private void process(T item) {
        System.out.println(item); // Xử lý đồng bộ.
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Lỗi: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Hoàn thành");
    }
}
```

`request(1)` **không** bảo đảm nguồn dữ liệu thực tế tự dừng sản xuất. Publisher có thể có buffer, nguồn I/O không thể tạm dừng hoặc nhiều subscriber với tốc độ khác nhau. Khi `process` chỉ đẩy việc sang một executor bất đồng bộ rồi trả về ngay, việc request tiếp lúc `onNext` kết thúc có thể cho in-flight tăng mạnh; phải trả demand khi **xử lý thực sự xong** và thường cần semaphore hoặc bộ đếm in-flight tương ứng.

`SubmissionPublisher` cung cấp API thuận tiện, nhưng `submit` có thể block khi không có buffer, còn `offer` có biến thể xử lý thiếu capacity và chính sách drop. Nó **không phải** durable queue; producer vẫn phải quyết định xử lý dữ liệu thừa. Không được suy ra memory toàn hệ thống đã bounded chỉ vì subscriber dùng `request(1)`.

## 7. Deadline, timeout, cancellation và retry

Một request có thể tiêu nhiều chặng: queue wait, semaphore wait, database, HTTP rồi serialize response. Nếu deadline end-to-end là 800 ms và đã chờ queue 500 ms, cho phép downstream gọi thêm 2 giây là vô lý. Giữ **remaining budget** qua từng chặng, bỏ công việc không còn kịp đáp ứng; với đo khoảng thời gian trong JVM, dùng nguồn thời gian monotonic như `System.nanoTime()`.

`Future.cancel(true)` yêu cầu ngắt thread, **không bảo đảm** tác vụ dừng hoặc rollback side effect. Tác vụ blocking nên phản hồi `InterruptedException` và kết thúc hợp lý; nếu bắt lỗi rồi không ném tiếp, thường nên đặt lại `Thread.currentThread().interrupt()`. Với API ngoài, timeout không cho biết chắc đối tác đã thực thi hay chưa.

Retry không giới hạn có thể tạo **retry storm**, nhất là khi nhiều tầng mỗi tầng tự retry. Dùng exponential backoff có jitter, giới hạn tổng thời gian/số lần retry, giữ idempotency key ổn định và tôn trọng tín hiệu overload. Việc đã từ chối vì quá tải không nhất thiết nên được retry ngay. Chỉ trả chỉ dẫn retry khi downstream có cơ hội phục hồi; với API ngoài cần kiểm tra trạng thái và idempotency để tránh side effect nhân đôi.

## 8. Bulkhead, fairness và chính sách hạ cấp

Nếu batch import dùng chung queue với request tương tác, batch kéo dài có thể làm request người dùng timeout. **Bulkhead** tạo hạn mức riêng cho các nhóm việc hoặc cho từng downstream: một pool cho CPU-bound, một permit budget cho API chậm, một queue cho job nền. Cần có **giới hạn chung** để nhiều pool độc lập không cùng tiêu cạn RAM/CPU.

Trong ứng dụng nhiều tenant, một tenant có thể chiếm hết permit. Xem xét per-tenant quota, global cap, ưu tiên theo lớp dịch vụ hoặc weighted fair scheduling. Priority không miễn phí: tác vụ ưu tiên thấp có thể bị starvation. `PriorityBlockingQueue` trong Java không có bound dung lượng theo constructor mặc định; muốn ưu tiên mà vẫn hạn chế backlog cần admission riêng.

Khi quá tải, chọn hợp đồng rõ:

| Tính chất công việc | Lựa chọn |
|---|---|
| Request tương tác có deadline ngắn | Từ chối sớm, thông báo overload, hướng dẫn retry có giới hạn |
| Job không thể mất | Ghi vào durable queue và xử lý idempotent; cũng phải giới hạn tốc độ đưa vào |
| Metric/cập nhật cache có thể tính lại | Drop/coalesce theo chính sách công bố và đếm số lần mất |
| Tác vụ đồng nhất theo key, chỉ cần kết quả mới nhất | Gộp yêu cầu theo key khi nghiệp vụ thực sự cho phép |
| Downstream bị suy giảm tạm thời | Hạn chế concurrency, hạ cấp chức năng không thiết yếu, giữ core path |

Thứ tự và tính nhất quán cũng quan trọng: queue FIFO không bảo đảm kết quả hoàn thành đúng thứ tự khi có nhiều worker. Khi giao dịch phải tuần tự theo một khóa nghiệp vụ, phân vùng theo key hoặc bảo vệ bằng transaction/version thay vì hy vọng queue tự đảm bảo.

## 9. Sizing dựa trên phép đo, không dùng con số cứng

Với CPU-bound ít blocking, số worker ban đầu thường quanh số lõi CPU sẵn có rồi benchmark thực tế; tăng thread quá nhiều có thể làm tăng context switching. Với I/O-bound, số task đồng thời có thể cao hơn số lõi, nhưng giới hạn bằng connection quota, memory, timeout và latency. Công thức kinh nghiệm `threads ≈ cores × (1 + waitTime / computeTime)` có thể làm mốc ước lượng cho một workload ổn định; không thay cho profiling.

Ví dụ hệ thống xử lý tối đa 100 task/giây, burst kéo dài 3 giây với tốc độ đến 120 task/giây: backlog phát sinh xấp xỉ `(120 - 100) × 3 = 60` task. Trong queue FIFO, 60 task chờ tốc độ xử lý 100/s mất khoảng 0,6 giây để xả hoàn toàn nếu không có yêu cầu mới và service rate giữ ổn định. Nếu thời gian chờ tối đa cho phép là 100 ms, **không** nên chọn queue 60 chỉ vì RAM chứa nổi; phải hạ tải hoặc tăng công suất.

Một cách thiết kế có hệ thống:

1. Xác định tài nguyên khan hiếm: CPU, heap, DB, API quota, file descriptor, network bandwidth.
2. Đo throughput bền vững, service latency, p95/p99, mức tối đa connection/permit; tránh lấy peak ngắn làm năng lực bền vững.
3. Đặt giới hạn in-flight gần tài nguyên thật và queue capacity theo **queue wait budget**.
4. Chọn chính sách khi đầy: chờ có hạn, reject, drop được phép, coalesce hay durable handoff.
5. Mang deadline qua từng chặng và kiểm soát retry để không khuếch đại tải.
6. Thử tải ổn định, burst, downstream chậm, timeout và shutdown; chỉnh theo số đo.

Đừng đo mỗi latency của những request được nhận mà quên request đã bị từ chối; phải quan sát end-to-end outcome.

## 10. Quan sát và kiểm thử cơ chế bảo vệ

| Tình huống thử | Kết quả kỳ vọng |
|---|---|
| Nhận task trong capacity | Hoàn tất, backlog nằm trong giới hạn |
| Burst vượt worker + queue | Có rejection hoặc backpressure đúng chính sách, không tăng RAM vô hạn |
| Downstream chậm 10 lần | Số request đồng thời không vượt permit, thời gian chờ có giới hạn |
| Producer bỏ qua overload | Rejection được ghi nhận; retry storm không làm toàn hệ thống sụp |
| Worker ném exception/interrupt | Permit được release, counter/in-flight không bị kẹt |
| Một tenant gửi quá nhiều | Hạn mức toàn hệ thống và fairness giữ tài nguyên cho lớp việc khác |
| Executor shutdown lúc queue có việc | Accepted/completed/rejected được phân biệt, không âm thầm mất việc quan trọng |
| Task bị cancel sau khi tạo side effect | Không giả định có rollback; retry dùng idempotency |
| Worker tự submit task con vào pool đầy | Không deadlock do chờ chính queue đang đầy |
| Nhiều JVM dùng chung quota bên ngoài | Tổng tải không vượt hạn mức đã cam kết |

Theo dõi `arrival/s`, `completed/s`, `rejected/s`, `dropped/s`, `activeWorkers`, `queueDepth`, `queueWait`, `permitWait`, `serviceLatency`, `endToEndLatency`, GC, CPU, heap và số connection đang dùng. `ThreadPoolExecutor.getActiveCount()` hay `getQueue().size()` là snapshot quan sát, có thể thay đổi tức thì; không coi là bản ghi transaction chính xác. Gắn metric ở cửa admission và lúc hoàn tất để suy ra tỷ lệ được nhận/từ chối đáng tin.

Tải kiểm thử nên bao gồm burst, chạy dài (soak), downstream fault, timeout và cancellation đồng thời. Nếu queue depth tăng trong khi completion rate dẹt, hệ thống đã vượt capacity; nếu p99 latency tăng mà CPU thấp, có thể bottleneck ở khóa, queue, DB hoặc API ngoài thay vì thiếu thread.

## 11. Sai lầm điển hình

- **Chỉ giới hạn thread:** bỏ qua queue có thể phát triển vô hạn.
- **Tăng queue để “không bao giờ reject”:** che quá tải, làm tăng memory và tail latency.
- **Tăng virtual threads để sửa mọi bottleneck:** downstream quota và connection limit không tự thay đổi.
- **Dùng semaphore JVM-local cho quota toàn cụm:** số instance nhân lên số permit.
- **Dùng rate limit thay cho concurrency limit:** request chậm vẫn tích tụ.
- **Xem `Flow.request(1)` như giới hạn mọi buffer:** upstream hoặc xử lý async có thể giữ nhiều công việc khác.
- **Chờ vô hạn vì cho rằng đó là backpressure:** producer bị chặn có thể chiếm hết thread và làm hệ thống deadlock.
- **Chọn `DiscardPolicy` cho tác vụ quan trọng:** làm mất dữ liệu mà caller không được thông báo.
- **Retry ngay khi quá tải:** gia tăng tải đúng lúc downstream yếu nhất.
- **Coi timeout/cancel là bằng chứng task chưa có tác dụng:** side effect có thể đã xảy ra.
- **Chỉ nhìn throughput trung bình:** bỏ qua tail latency, rejection, fairness và SLA.

Nguyên tắc áp dụng: giới hạn ngay tại tài nguyên cần bảo vệ; đặt queue theo latency budget; truyền tín hiệu quá tải đủ sớm để producer phản ứng; giữ trạng thái task rõ ràng và dùng timeout, cancellation, retry, idempotency đúng ngữ cảnh. **Mục tiêu không phải nhận tất cả task, mà giữ hệ thống vận hành có thể dự đoán khi tải vượt khả năng phục vụ.**
