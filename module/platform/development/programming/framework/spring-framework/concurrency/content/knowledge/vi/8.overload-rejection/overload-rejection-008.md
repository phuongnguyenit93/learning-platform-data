# Không lặp gửi lại tức thời làm quá tải nghiêm trọng hơn

> **Module:** Spring Framework – concurrency  
> **Chủ đề cha:** Quá tải và từ chối  
> **Mục tiêu:** Hiểu vì sao việc gửi lại ngay sau khi bị từ chối hoặc gặp lỗi tạm thời có thể biến tình trạng quá tải thành sự cố dây chuyền; biết thiết kế giới hạn lần thử, thời hạn, backoff, jitter và cơ chế điều phối retry không làm nghẽn thêm executor.

## 1. Vấn đề: hệ thống đang bận lại bị ép làm nhiều hơn

Giả sử một `ThreadPoolTaskExecutor` của Spring đang chạy hết số worker và queue cũng đầy. Lời gọi `execute()` hoặc `submit()` bị từ chối theo chính sách của pool (ví dụ `AbortPolicy` dẫn tới `TaskRejectedException`). Người viết mã thấy lỗi và lập tức gọi lại:

~~~java
for (;;) {
    try {
        executor.execute(task);
        break;
    } catch (TaskRejectedException rejected) {
        // Thử ngay lần nữa, không có giới hạn.
    }
}
~~~

Đây là **phản ví dụ**, không phải đoạn mã nên áp dụng: biến `executor`, `task` và import Spring được lược bỏ. Vòng lặp có thể chiếm CPU của luồng gọi, nộp lại cùng công việc hàng nghìn lần mỗi giây mà không tạo ra một worker hay chỗ trống trong queue. Nếu hàng trăm request cùng thực hiện, chính cơ chế “cố chữa lỗi” làm nghẽn thêm ứng dụng.

Khi sự cố nằm ở một dịch vụ bên ngoài, tình huống cũng tương tự: nếu backend trả `429 Too Many Requests`, `503 Service Unavailable` hoặc timeout do quá tải, tất cả caller lập tức gọi lại sẽ bổ sung lượng yêu cầu ngay lúc backend cần giảm tải để phục hồi. Các yêu cầu retry sử dụng cùng connection pool, CPU, thread và network, kéo dài thời gian xử lý của cả yêu cầu mới.

**Nguyên tắc:** Thất bại do quá tải là tín hiệu để **giảm tốc hoặc dừng nhận thêm việc**, không phải tín hiệu cho một vòng lặp thử lại tức thời.

## 2. Vòng phản hồi dương tạo ra retry storm

Một luồng khuếch đại tải điển hình:

~~~text
Nhiều yêu cầu mới
       |
       v
Pool/DB/downstream đã gần quá tải
       |
       v
Queue chờ dài, deadline vượt ngưỡng, reject/timeout tăng
       |
       v
Caller retry ngay -> tăng số lượt nộp/call
       |
       v
Thêm CPU + thread + connection + queue contention
       |
       v
Latency và lỗi tăng -> càng nhiều retry -> vòng lặp lặp lại
~~~

**Retry storm** là làn sóng yêu cầu thử lại tự duy trì hoặc làm trầm trọng tình trạng quá tải. Khi nhiều client retry cùng một nhịp, có thêm hiện tượng *thundering herd*: nhiều yêu cầu cùng đổ vào backend đúng thời điểm nó vừa mở lại khả năng nhận tải.

Thử lại có thể hữu ích khi lỗi ngắn, không thường xuyên và hệ thống đã có thời gian hồi phục. Nhưng khi nguyên nhân là **thiếu công suất kéo dài**, mỗi lần thử lại là một yêu cầu mới tiêu tốn tài nguyên, thường có khả năng tiếp tục thất bại.

## 3. Nhìn bằng số: một yêu cầu có thể biến thành bao nhiêu lần gọi?

Giả sử có 1.000 yêu cầu nghiệp vụ/s. Nếu mỗi yêu cầu bị lỗi đều được phép thử tối đa **bốn lần thực thi** (lần đầu + ba lần retry) và backend liên tục thất bại, số *attempt* có thể đạt **4.000/s**. Backend chỉ chịu được 800/s thì 4.000 lần thử không làm tăng số kết quả thành công; nó làm việc xếp hàng và phục hồi khó hơn.

Với xác suất một attempt thất bại là `p`, giả định các attempt độc lập và cùng xác suất lỗi, số attempt kỳ vọng khi có tối đa `k` lần thực thi là:

`E[attempts] = 1 + p + p² + ... + p^(k-1)`

Ví dụ `p=0,8`, `k=4`: kỳ vọng `1 + 0,8 + 0,64 + 0,512 = 2,952` lượt cho mỗi yêu cầu. Đây chỉ là mô hình giải thích; trong thực tế, những lỗi quá tải thường **không độc lập**: các attempt liên tiếp đúng giai đoạn nghẽn có thể đều thất bại.

Một nguy cơ khác là **retry tại nhiều tầng**. Nếu gateway, service trung gian và client đến DB đều tự cho phép ba lần thực thi, một hành động ở trên có thể tạo đến `3 × 3 × 3 = 27` lượt truy cập tầng thấp nhất khi các tầng đều phải thử đủ số lần. Cần phân định rõ tầng nào sở hữu retry để tránh nhân bội không chủ ý.

## 4. Phân biệt ba trường hợp thất bại trước khi retry

| Trường hợp | Ý nghĩa | Cách phản ứng |
| --- | --- | --- |
| `TaskRejectedException` ngay khi nộp vào Spring executor | Pool không nhận thêm công việc theo chính sách lúc đó, hoặc đang đóng | Không nộp lại ngay; phản hồi backpressure, lên lịch trễ có giới hạn nếu được phép, hoặc chuyển việc vào queue bền vững |
| Task đã được nhận nhưng gọi dịch vụ khác bị timeout/`429`/`503` | Công việc có thể đã chạy một phần; kết quả ở hệ thống đích có thể chưa rõ | Xác định lỗi tạm thời, idempotency, deadline; có thể retry với backoff và tôn trọng hướng dẫn từ backend |
| Lỗi vĩnh viễn: dữ liệu không hợp lệ, vi phạm bất biến, lỗi lập trình, quyền không hợp lệ | Lặp lại không làm yêu cầu hợp lệ hơn | Fail fast; trả lỗi đúng nguồn gốc và sửa input/code/quyền |

**Lưu ý quan trọng:** `TaskRejectedException` có thể phát sinh **đồng bộ từ lời gọi nộp**, trong khi exception bên trong `Runnable` đã được nhận không nhất thiết quay về luồng caller. Với `submit()`, lỗi của task có thể được giữ trong `Future`; cần `Future.get()` hoặc cơ chế quan sát phù hợp. Không được bắt lỗi từ lời gọi `submit` rồi nghĩ đã bao quát mọi lỗi xảy ra khi chạy.

Ngoài ra, timeout không chứng minh thao tác từ xa **chưa thực hiện**. Nếu một yêu cầu thanh toán đã được ghi nhận nhưng phản hồi mạng bị mất, retry không có idempotency key có thể dẫn đến thanh toán lặp.

## 5. Backoff: cho hệ thống thời gian lấy lại công suất

**Backoff** là khoảng dừng có chủ ý trước lần thử lại. Thay vì thử ngay, client giãn cách các lượt gọi và dừng sau một ngân sách hữu hạn.

Một công thức dễ hiểu là **exponential backoff có trần**:

`delay(n) = min(maxDelay, baseDelay × 2^(n-1))`

Trong đó `n = 1` là **lần retry đầu tiên sau khi attempt ban đầu thất bại**, `baseDelay` là thời gian chờ cơ bản, còn `maxDelay` tránh để khoảng chờ tăng vô tận.

Với `baseDelay = 200 ms` và `maxDelay = 1.600 ms`:

| Lần retry n | Thời gian trước retry khi chưa jitter |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 trở đi | 1.600 ms (chạm trần) |

Đây chỉ là **cách tính thời gian**, không phải chỉ dẫn “cứ retry mãi”. Một chính sách hoàn chỉnh còn giới hạn tổng lần thực thi, thời hạn nghiệp vụ và mức độ retry của toàn dịch vụ.

Không cần dùng `Thread.sleep()` trên worker của pool đang quá tải để thực hiện backoff. Cách đó giữ một worker vô ích, khiến năng lực xử lý vốn thiếu càng nhỏ hơn.

## 6. Vì sao chỉ exponential backoff vẫn chưa đủ?

Nếu 10.000 client đồng thời gặp lỗi và cùng dùng dãy `200 ms → 400 ms → 800 ms`, chúng vẫn có thể phát hàng nghìn request **cùng một khoảnh khắc** sau mỗi mốc. Làn sóng retry được trì hoãn nhưng vẫn đồng bộ.

**Jitter** thêm biến thiên ngẫu nhiên vào khoảng đợi để phân tán lượt thử lại theo thời gian. Một số chính sách thường dùng:

| Chính sách | Cách chọn thời gian | Đặc điểm |
| --- | --- | --- |
| Không jitter | `delay(n)` cố định cho mọi client | Dễ thực hiện nhưng dễ đồng bộ retry |
| Full jitter | Ngẫu nhiên trong `[0, delay(n)]` | Phân tán mạnh; có thể nhận giá trị 0, nên cần cân nhắc yêu cầu không gửi ngay |
| Equal jitter | Ngẫu nhiên trong `[delay(n)/2, delay(n)]` | Có một mức chờ tối thiểu, vẫn phân tán được lượt retry |
| Jitter theo tín hiệu server | Tôn trọng mốc `Retry-After`, thêm phân tán nếu hợp đồng và deadline cho phép | Giảm tranh chấp khi server đã biết thời gian phục hồi tối thiểu |

Với mục tiêu **không gửi lại tức thời**, equal jitter là một lựa chọn minh họa: lần retry đầu tiên có khoảng đợi `100–200 ms` khi delay danh định là `200 ms`; lần thứ hai `200–400 ms`, v.v. Đây **không phải** công thức tối ưu cho mọi tải; mức đợi phải dựa trên SLO, thời gian hồi phục, số caller và hạn xử lý.

Mỗi instance nên có nguồn ngẫu nhiên phù hợp để tránh các client cùng tạo chuỗi delay giống nhau. Không cần tự triển khai bộ sinh số ngẫu nhiên mới khi JDK đã có `ThreadLocalRandom` hoặc cơ chế phù hợp.

## 7. Giới hạn số lần thử, deadline và retry budget

Ba giới hạn giải quyết ba dạng thất bại:

1. **maxAttempts:** ví dụ tổng cộng bốn attempt (một ban đầu, tối đa ba retry), rồi kết thúc với trạng thái thất bại rõ ràng. Đừng nhầm `maxRetries=3` với `maxAttempts=3`.
2. **Deadline end-to-end:** nếu nghiệp vụ chỉ cho phép ba giây, mọi kết nối, chờ pool, backoff và các retry đều phải nằm trong hạn này. Không bắt đầu retry nếu delay cộng thời gian xử lý dự kiến đã vượt deadline.
3. **Retry budget toàn dịch vụ:** dù mỗi yêu cầu được tối đa ba retry, tổng số retry trên tất cả yêu cầu vẫn phải bị khống chế. Ví dụ cấp một số token retry hữu hạn cho mỗi giây hoặc mỗi cửa sổ thời gian để một đợt lỗi không tự nhân tải.

Một deadline có thể làm cho yêu cầu không được thử lại dù chưa chạm `maxAttempts`; retry budget cũng có thể yêu cầu bỏ một retry nếu toàn dịch vụ đang nghẽn. Đây là hành vi đúng khi hệ thống cần bảo vệ khả năng phục vụ các request mới.

**Cần có số đo:** tách số lần gọi ban đầu và số lần thử lại; theo dõi `retry_attempts_total`, `retry_exhausted_total`, `rejected_tasks_total`, độ trễ chờ retry và số yêu cầu hết deadline. Nếu không phân biệt, retry có thể bị ngụy trang thành “lưu lượng tự nhiên”.

## 8. Ví dụ Java 17+ chạy độc lập: không retry ngay, không chiếm thread để ngủ

Ví dụ sau dùng `ScheduledExecutorService` để minh họa ba attempt: hai lần đầu gặp lỗi tạm thời, mỗi lần đều được **lên lịch sau một khoảng đợi**; lần thứ ba thành công. Đây là mô phỏng local có kết quả xác định; không cần thư viện Spring.

Tạo tệp **ScheduledRetryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledRetryDemo {
    private static final int MAX_ATTEMPTS = 3;
    private static final ScheduledExecutorService TIMER =
            Executors.newSingleThreadScheduledExecutor();
    private static final AtomicInteger CALLS = new AtomicInteger();
    private static final CountDownLatch FINISHED = new CountDownLatch(1);

    private static long delayMillis(int failedAttempt) {
        return Math.min(800L, 100L << (failedAttempt - 1));
    }

    private static void attempt(int number) {
        int call = CALLS.incrementAndGet();

        if (call <= 2) {
            System.out.println("Attempt " + call + ": transient failure");

            if (number >= MAX_ATTEMPTS) {
                System.out.println("Retry budget exhausted");
                FINISHED.countDown();
                return;
            }

            long delay = delayMillis(number);
            System.out.println("Retry after " + delay + " ms");
            TIMER.schedule(() -> attempt(number + 1),
                    delay, TimeUnit.MILLISECONDS);
            return;
        }

        System.out.println("Attempt " + call + ": success");
        FINISHED.countDown();
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            TIMER.execute(() -> attempt(1));
            if (!FINISHED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Retry demo timed out");
            }
        } finally {
            TIMER.shutdown();
            if (!TIMER.awaitTermination(5, TimeUnit.SECONDS)) {
                TIMER.shutdownNow();
            }
        }
    }
}
~~~

Chạy với Java 17 trở lên:

~~~bash
javac ScheduledRetryDemo.java
java ScheduledRetryDemo
~~~

**Stdout do chương trình in** khi máy có thể thực thi ba task trong thời hạn chờ năm giây:

~~~text
Attempt 1: transient failure
Retry after 100 ms
Attempt 2: transient failure
Retry after 200 ms
Attempt 3: success
~~~

Giải thích:

- `TIMER.schedule()` chỉ đăng ký lần chạy sau, không vòng lặp thử ngay và không dùng `Thread.sleep()` để giữ một worker trong thời gian backoff.
- `MAX_ATTEMPTS=3` nghĩa là tối đa **ba lần gọi tổng cộng**, không phải ba lần retry sau lần đầu.
- Ví dụ cố ý dùng thời gian cố định `100 ms` và `200 ms` để stdout dễ kiểm tra. Trong hệ thống thật nên bổ sung jitter và deadline.
- Scheduler này thực thi công việc giả lập cực ngắn ngay trên timer thread; **không** đặt một HTTP call hoặc tác vụ DB chậm ngay trong thread scheduler khi thiết kế ứng dụng lớn. Scheduler nên đến thời điểm thích hợp rồi **gửi** việc sang executor có giới hạn, hoặc đưa message trở lại queue/job store.
- Ví dụ chưa có lưu bền hay nhiều JVM: JVM chết thì lịch chờ trong bộ nhớ cũng mất. Nếu công việc bắt buộc phải được hoàn thành sau restart, cần durable queue/job store.

### Tính equal jitter trong Java

Hàm sau minh họa riêng cách chọn khoảng đợi có jitter, có thể dùng trong service sản phẩm với `retryNumber >= 1` và chính sách giới hạn số lần thử:

~~~java
import java.util.concurrent.ThreadLocalRandom;

static long retryDelayMs(int retryNumber) {
    if (retryNumber < 1) {
        throw new IllegalArgumentException("retryNumber starts at 1");
    }
    long cap = 200;
    for (int i = 1; i < retryNumber && cap < 1600; i++) {
        cap = Math.min(1600, cap * 2);
    }
    long minimum = cap / 2;
    return ThreadLocalRandom.current().nextLong(minimum, cap + 1);
}
~~~

Đây là **phương thức minh họa**, không phải tệp Java biên dịch độc lập vì không có khai báo class bao ngoài. Với `retryNumber=1` kết quả nằm trong `[100,200]` ms; với `retryNumber=2` trong `[200,400]` ms. `nextLong(origin, bound)` có biên trên loại trừ, vì vậy dùng `cap + 1` để bao gồm `cap`. Tính trần trước khi cộng 1 để tránh overflow nếu thay đổi thông số; ví dụ này có trần nhỏ và an toàn.

## 9. Áp dụng trong Spring: tách scheduler và executor xử lý việc

Spring Framework cung cấp `TaskExecutor` để thực thi task và `TaskScheduler` để lên lịch chạy sau. `TaskScheduler.schedule(Runnable, Instant)` đặt một tác vụ chạy một lần vào thời điểm chỉ định. Với `ThreadPoolTaskScheduler`, timer quản lý các lượt kích hoạt; `ThreadPoolTaskExecutor` quản lý worker có giới hạn.

Ví dụ cấu hình tích hợp Spring:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class RetryInfrastructure {
    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("work-");
        pool.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Bean("retryScheduler")
    ThreadPoolTaskScheduler retryScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("retry-");
        return scheduler;
    }
}
~~~

Đây là **đoạn cấu hình cho một project Spring**, cần ApplicationContext nạp class này và có dependency Spring thích hợp. Giá trị `4/8/32` là ví dụ minh họa, không phải mặc định hay khuyến nghị áp dụng nguyên xi. Giữ executor hữu hạn để quá tải được thể hiện rõ; một queue cực dài thường chỉ chuyển lỗi reject thành backlog và thời gian chờ không kiểm soát.

Một đường xử lý retry khi **lệnh nộp bị từ chối** có thể tổ chức theo luồng:

~~~text
Nhận command (operationId, deadline)
             |
             v
Thử workExecutor.execute(task)
   | được nhận                 | bị TaskRejectedException
   v                           v
Worker xử lý và             Kiểm tra retry count,
ghi nhận kết quả            deadline, retry budget
                               |
                         còn ngân sách?
                         /         \
                       có         hết
                       |           |
             delay + jitter     báo thất bại/
                       |        lưu trạng thái
                       v
             retryScheduler.schedule(
                 () -> nộp lại command,
                 Instant.now() + delay
             )
                       |
               đến hạn mới thử
~~~

Sơ đồ trên chỉ mô tả retry khi **nộp vào executor bị từ chối**. Nếu worker đã nhận task nhưng task thất bại, cần một đường xử lý khác bắt được kết quả/exception của worker và chỉ retry các lỗi thật sự tạm thời. `Future.get()` hoặc một completion handler thích hợp giúp quan sát; không được tin rằng `execute` trả về bình thường có nghĩa là việc nghiệp vụ đã thành công.

**Không gọi đệ quy tức thời** từ `catch(TaskRejectedException)`: nếu `submitAgain()` tự gọi lại chính nó trong catch thì vẫn là retry nóng. Scheduling một callback sau delay khác về bản chất. Tuy nhiên timer cũng có thể quá tải/từ chối, và lịch trong bộ nhớ không bền; production phải có trạng thái kết thúc, metric và fallback rõ ràng.

## 10. Đặt retry ở đúng tầng và tránh giữ tài nguyên vô ích

Một đoạn mã có vẻ “đơn giản” nhưng gây hại:

~~~java
try {
    doRemoteCall();
} catch (TransientException ex) {
    Thread.sleep(1000);
    doRemoteCall();
}
~~~

Đây là **phản ví dụ không độc lập**, có exception/dependency giả định và thiếu xử lý `InterruptedException`. Dù đã có delay, việc ngủ ngay **trong worker đang khan hiếm** vẫn chiếm thread trong lúc không làm gì. Nếu nhiều worker cùng ngủ, pool không còn slot để xử lý yêu cầu mới. Trường hợp gọi đồng bộ nhỏ, có kiểm soát và không nằm trong pool khan hiếm có thể chấp nhận blocking backoff; cần đánh giá tài nguyên thay vì cấm `sleep` trong mọi ngữ cảnh.

Với công việc dài hạn hoặc số lượng retry lớn, thích hợp hơn là: trả quyền điều khiển cho caller, ghi thời điểm retry dự kiến vào job store, hoặc đăng ký timer rồi nhả worker. Đến hạn, task được đưa lại vào executor/consumer có backpressure. Không để vô hạn delayed jobs tích trong bộ nhớ scheduler, vì chỉ chuyển backlog từ queue này sang queue khác cũng chưa giải quyết công suất.

## 11. Khi nào cần từ bỏ retry và fail fast?

Không phải mọi lỗi đều đáng thử lại:

- **Input sai, lỗi validation, `400`, phần lớn lỗi `401/403` do thiếu quyền:** cần sửa input/quyền; retry ngay hoặc backoff không giải quyết bản chất.
- **Kết quả conflict do bất biến nghiệp vụ:** `409` hay optimistic-lock conflict đôi khi cho phép load lại dữ liệu và thực hiện lại một thao tác nghiệp vụ **được thiết kế an toàn**, nhưng không được retry mù mọi conflict.
- **`429` và `503`:** thường báo throttling/không sẵn sàng; xem `Retry-After` nếu có, tôn trọng giới hạn server, deadline và jitter phù hợp.
- **Timeout và đứt kết nối:** không biết chắc remote có thực hiện thao tác hay chưa; chỉ retry nếu operation idempotent hoặc có idempotency key/kiểm tra trạng thái.
- **Lỗi lập trình, dữ liệu đã bị hủy, thao tác không còn có ý nghĩa:** ghi lỗi/đưa vào kênh xử lý thích hợp thay vì tiêu thêm tài nguyên.
- **Deadline hết, retry budget cạn, circuit breaker mở, hệ thống đang load shedding:** dừng retry, ưu tiên bảo vệ năng lực hệ thống.

Lỗi nhận được ở API client khác với nguyên nhân gốc. Một `503` có thể đến từ gateway hoặc dependency; cần logging/tracing để tìm tầng phát sinh và thống nhất tầng sở hữu retry.

## 12. Idempotency: tránh nhân tác dụng phụ khi đã nhận nhưng chưa phản hồi

Giả sử client gọi API tạo đơn, server đã commit thành công nhưng response bị mất. Client timeout và retry ngay hoặc retry sau một giây vẫn có thể tạo đơn lần hai **nếu nghiệp vụ không chống trùng**.

Một idempotency key ổn định gắn với ý định nghiệp vụ giúp server phát hiện các attempt trùng. Khi xử lý nhiều lần cùng key, server có thể trả kết quả của lần đầu hoặc giữ một trạng thái duy nhất, tùy hợp đồng. Unique constraint/transaction, bảng kết quả theo key, consumer dedupe và outbox có thể là thành phần triển khai.

Quy tắc quan trọng:

1. **Giữ nguyên cùng idempotency key giữa các lần retry** của cùng một ý định; không tạo key mới ở mỗi attempt.
2. Phân biệt key của một nghiệp vụ mới với key của một attempt kỹ thuật.
3. Xác định cách xử lý attempt đang xử lý, thất bại không rõ kết quả và quá hạn lưu key.
4. Không mặc định `Future.cancel(true)` hay timeout có thể hoàn tác tác dụng phụ đã xảy ra.
5. Kiểm thử duplicate và lost response trước khi bật auto-retry cho thao tác ghi dữ liệu/thu tiền.

Backoff hạn chế **áp lực tài nguyên**; idempotency hạn chế **tác dụng phụ lặp**. Hai cơ chế giải quyết hai khía cạnh khác nhau và thường cần đi cùng nhau.

## 13. Phối hợp với backpressure, rate limit và circuit breaker

| Cơ chế | Giải quyết | Quan hệ với retry |
| --- | --- | --- |
| Bounded pool/queue | Giới hạn số tác vụ đồng thời/chờ trong tiến trình | Khi bão hòa phải báo reject thay vì nhận backlog vô hạn |
| Rate limiting | Giới hạn lưu lượng vào theo client/tenant/service | Giảm tải gốc, bao gồm cả retry |
| Backpressure/load shedding | Yêu cầu caller chậm lại hoặc từ chối một phần tải | Retry phải chấp hành tín hiệu này |
| Circuit breaker | Ngừng gọi tạm thời một dependency đang lỗi liên tục | Giảm số attempt vô ích; chỉ thăm dò phục hồi theo chính sách |
| Timeout/deadline | Ngăn một thao tác dùng tài nguyên quá lâu | Không lên lịch retry khi hết thời hạn |
| Exponential backoff + jitter | Trải retry theo thời gian, tránh các đợt đồng bộ | Chỉ dùng khi lỗi có khả năng hồi phục và operation có thể retry |
| Retry budget | Giới hạn retry toàn hệ thống | Ngăn hàng loạt request cùng nhân đôi/nhân ba tải |
| Durable queue/job store | Lưu công việc qua restart, kiểm soát retry ở cấp hệ thống | Cần idempotency, giám sát và quy tắc xử lý lỗi độc hại |

**CallerRunsPolicy** của `ThreadPoolExecutor` có thể khiến luồng nộp phải tự chạy task để tạo backpressure khi pool đang hoạt động và bão hòa. Đây là **một lựa chọn thiết kế**, không phải lý do để thêm vòng lặp retry nóng; nó làm tăng độ trễ caller và cần kiểm soát deadline. Policy này cũng có hành vi đặc biệt khi executor đã shutdown, vì vậy không thể coi là cơ chế đảm bảo task luôn được nhận.

Spring Framework cung cấp abstraction executor/scheduler và cho phép tích hợp các cơ chế bảo vệ. Việc chọn thư viện retry/circuit breaker cụ thể (chẳng hạn Spring Retry hoặc giải pháp resilience riêng) là quyết định kiến trúc bổ sung; **`ThreadPoolTaskExecutor` không tự cấp retry có backoff và jitter cho mọi task**.

## 14. Hai tình huống thực tế

### A. Endpoint tạo báo cáo bị từ chối ở executor

**Trước:** HTTP handler gọi `reportExecutor.submit(job)`; khi gặp `TaskRejectedException`, chạy `while(true)` thử lại. Khi queue đầy, các request thread mắc trong vòng lặp, CPU tăng mà báo cáo không hoàn thành.

**Sau:** xác định API đồng bộ hay nhận job. Với API đồng bộ, có thể trả phản hồi quá tải thích hợp (ví dụ `429` hoặc `503` tùy ý nghĩa dịch vụ) cùng hướng dẫn retry để client không thử dồn dập. Với API job quan trọng, ghi job/idempotency key vào kho bền vững rồi worker tiêu thụ theo giới hạn. Nếu có đường retry trong service, đặt maxAttempts/deadline/budget và scheduler có giới hạn; không chặn request thread vô thời hạn.

### B. Dịch vụ thanh toán downstream chậm

**Trước:** ba tầng đều retry tức thời khi timeout. Một yêu cầu thanh toán có thể bùng thành nhiều cuộc gọi trong lúc payment gateway chậm, rủi ro lặp giao dịch và làm downstream thêm nghẽn.

**Sau:** thống nhất tầng sở hữu retry; dùng cùng idempotency key, giới hạn tổng thời gian, số attempt và retry budget. Tôn trọng rate limit/`Retry-After`, áp backoff jitter, kiểm tra trạng thái thanh toán khi kết quả không rõ ràng. Với lỗi không thể hồi phục hoặc hết deadline, kết thúc có ghi nhận thay vì tạo thêm tải.

## 15. Cách kiểm thử một chính sách retry an toàn

1. **Rejection có kiểm soát:** dùng `CountDownLatch` giữ worker của `ThreadPoolTaskExecutor`, làm đầy queue rồi xác nhận task mới bị reject đúng policy. Không viết test chỉ dựa trên `Thread.sleep()` để hy vọng pool bão hòa.
2. **Không retry nóng:** dùng fake clock/virtual time hoặc scheduler có thể kiểm soát; đo timestamp giữa các attempt và khẳng định lần retry kế tiếp không xảy ra ngay.
3. **Max attempts và deadline:** với dependency luôn lỗi, kiểm tra tổng lượt gọi không vượt trần và kết thúc sau deadline.
4. **Jitter:** kiểm tra delay nằm trong khoảng hợp lệ; kiểm thử giới hạn và seed cố định tại tầng tính toán nếu cần độ lặp lại. Tránh assert một thời điểm ngẫu nhiên chính xác trong test tích hợp.
5. **Retryable vs nonretryable:** xác nhận lỗi input/permission không bị retry; timeout có kết quả không rõ chỉ retry khi idempotent.
6. **Dồn tải đồng thời:** cho nhiều caller nhận lỗi cùng lúc; đo tổng attempt/s và phân bố retry để phát hiện thundering herd.
7. **Lỗi một phần:** giả lập remote xử lý thành công nhưng mất phản hồi; xác nhận idempotency key giúp tránh tạo bản ghi/tác dụng phụ trùng.
8. **Restart/shutdown:** với công việc quan trọng, kiểm tra khả năng phục hồi trong job store; không giả định timer trong bộ nhớ sẽ tồn tại qua process crash.

Theo dõi song song tỷ lệ request gốc, tỷ lệ retry, số bị từ chối, chiều dài queue, active worker, thời gian chờ, tỷ lệ lỗi và p95/p99 latency. Nếu **retry tăng đồng thời với lỗi và backlog**, hệ thống có thể đang tự khuếch đại sự cố.

## 16. Checklist khi thiết kế để tránh retry storm

- Tôi đã phân biệt **reject lúc nộp task** với **lỗi khi task đã chạy**.
- Tôi chỉ retry lỗi thật sự tạm thời và thao tác có khả năng retry an toàn.
- Tôi có `maxAttempts`, deadline tổng, retry budget toàn dịch vụ.
- Tôi dùng delay/backoff và jitter, không có vòng lặp retry tức thời.
- Tôi không giữ worker hiếm hoi chỉ để ngủ trong thời gian backoff.
- Tôi xử lý riêng timeout, cancellation, shutdown và scheduler rejection.
- Tôi tôn trọng tín hiệu `429`, `503`, `Retry-After` khi phù hợp hợp đồng.
- Tôi bảo đảm idempotency cho tác dụng phụ nếu có thể xuất hiện duplicate.
- Tôi quan sát riêng retry rate và load gốc; có kiểm thử saturation và lost response.
- Tôi biết đường xử lý cuối cùng sau khi retry hết ngân sách: trả lỗi, ghi thất bại, chuyển xử lý thủ công hoặc dead-letter theo yêu cầu nghiệp vụ.

**Ghi nhớ:** Khi pool hoặc downstream quá tải, **retry tức thời lấy thêm chính tài nguyên đang thiếu** và tạo vòng phản hồi khiến sự cố kéo dài. Retry đúng phải có **điều kiện**, **giới hạn**, **đợi có jitter**, **ngữ cảnh idempotency**, và một điểm dừng rõ ràng.

## Tài liệu tham khảo

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, queue, từ chối và scheduling.
- [Spring Framework – TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html): `schedule(Runnable, Instant)`.
- [Spring Framework – TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html).
- [Google SRE Book – Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): retry storms, randomized backoff, ngân sách retry và tránh retry nhiều tầng.
- [Java SE 17 – ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): cách lên lịch task mà không giữ worker trong lúc chờ.
