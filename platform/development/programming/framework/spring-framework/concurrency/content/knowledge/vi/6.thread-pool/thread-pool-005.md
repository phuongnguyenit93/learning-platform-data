# Vì sao hàng đợi không giới hạn làm maxPoolSize khó phát huy tác dụng

> **Module:** Spring Framework – concurrency · **Chủ đề cha:** Nhóm luồng  
> **Câu hỏi chính:** Vì sao cấu hình `corePoolSize = 2`, `maxPoolSize = 16` nhưng một `ThreadPoolTaskExecutor` dùng hàng đợi rất lớn lại thường chỉ chạy khoảng hai worker, trong khi hàng nghìn công việc chờ trong queue?

## 1. Câu trả lời cốt lõi

Với `ThreadPoolTaskExecutor` thông thường của Spring, cơ chế điều phối bên dưới là `java.util.concurrent.ThreadPoolExecutor`. Khi số worker đã đạt `corePoolSize`, executor **ưu tiên đưa task mới vào hàng đợi trước khi tạo thêm worker vượt mức core**. Chỉ khi việc đưa vào hàng đợi **không thành công** và tổng số worker chưa đạt `maximumPoolSize`, nó mới thử tạo worker bổ sung.

Do đó, với hàng đợi **không giới hạn trên thực tế**, thao tác thêm task vào queue hầu như luôn thành công. Điều kiện kích hoạt tăng từ `corePoolSize` lên `maxPoolSize` gần như không xuất hiện. Kết quả thường là ít worker đang xử lý, nhiều task chờ, độ trễ cao và bộ nhớ tăng. Việc đặt `maxPoolSize` rất lớn **không tự khiến pool tăng đến mức đó**.

Đây là quy tắc của **ThreadPoolExecutor và các adapter dùng nó**, không phải quy luật của mọi implementation `TaskExecutor`. Chẳng hạn, `SimpleAsyncTaskExecutor` không vận hành bằng cùng cơ chế thread pool/queue.

## 2. Ba thông số quyết định hành vi

| Thông số | Vai trò | Điều nó không có nghĩa |
| --- | --- | --- |
| `corePoolSize` | Số worker cơ bản mà executor ưu tiên tạo khi tiếp nhận công việc; mặc định worker core thường được giữ lại kể cả lúc nhàn rỗi | Không phải giới hạn tuyệt đối của tổng worker |
| `maxPoolSize` | Trần số worker mà executor có thể tạo khi cần | Không phải mục tiêu số worker mà executor tự cố đạt |
| `queueCapacity` | Số task có thể chờ trong queue, quyết định khi nào lời gọi `offer` thất bại và executor thử mở rộng worker | Không phải số task chạy đồng thời; task đang chạy thường không nằm trong queue |

`poolSize` là số worker hiện có, `activeCount` là số worker đang thực hiện task (ước lượng tức thời), còn `queueSize` là số task còn đang chờ. Đọc riêng `poolSize` mà không nhìn `queueSize` dễ dẫn đến kết luận sai về mức tải.

Một queue dung lượng 100 không đồng nghĩa với hệ thống chạy 100 task song song: nếu core chỉ có 2 và queue chưa đầy, thường chỉ 2 task được chạy, các task khác chờ.

## 3. Vì sao nhánh mở rộng thường không được kích hoạt?

`ThreadPoolExecutor.execute` ưu tiên tạo worker tới `corePoolSize`; tiếp theo thử `workQueue.offer(task)`; chỉ khi offer không thành công mới cố tạo worker tới `maxPoolSize`, rồi từ chối khi không thể nhận thêm. Implementation thật còn có các bước kiểm tra shutdown và cạnh tranh đồng thời.

**Nút thắt của bài này chính là điều kiện offer thất bại.** Với `LinkedBlockingQueue(Integer.MAX_VALUE)`, offer có thể thành công cực nhiều lần, nên nhánh mở rộng worker gần như không được thực hiện. Bài “Thứ tự nhận tác vụ: tạo luồng cơ bản, xếp hàng, mở rộng rồi từ chối” trình bày thuật toán chi tiết; ở đây ta đánh giá hệ quả **queue gần vô hạn** qua backlog, latency và khả năng mở tới max.

## 4. Vì sao hàng đợi rất lớn giữ pool gần corePoolSize?

Giả sử:

- `corePoolSize = 2`;
- `maxPoolSize = 16`;
- queue dạng `LinkedBlockingQueue` dung lượng cực lớn;
- các task là công việc chậm, cả hai worker ban đầu đều bận.

Khi task thứ ba đến, pool có 2 worker nên thử đưa vào queue. Thao tác này thành công. Task thứ tư, thứ năm và hàng trăm task sau cũng được enqueue vì queue vẫn còn chỗ. Pool không có lý do đi đến nhánh tạo worker thứ ba, thứ tư… thứ mười sáu.

~~~text
core = 2, max = 16, queue gần như không giới hạn

Worker #1: [TASK A đang chạy]
Worker #2: [TASK B đang chạy]
Queue:     [C][D][E][F][G][H][... nhiều task nữa ...]
Workers #3 ... #16: chưa được tạo

task mới -> queue.offer(...) thành công -> vẫn chỉ hai worker
~~~

Nếu task đến trung bình nhanh hơn hai worker hoàn thành, lượng chờ sẽ tích lũy. Tăng `maxPoolSize` từ 16 lên 64 **không trực tiếp thay đổi nhánh quyết định**: chừng nào `offer` còn thành công thì pool vẫn ưu tiên queue.

Với **queue thật sự không giới hạn** của mô hình JDK, Javadoc chỉ rõ worker thường không vượt `corePoolSize`; `maximumPoolSize` do đó không phát huy tác dụng. Với queue mặc định của Spring có giới hạn kỹ thuật `Integer.MAX_VALUE`, về mặt lý thuyết có thể đầy; nhưng thực tế nguy cơ thiếu bộ nhớ/tăng độ trễ thường đến rất lâu trước lúc chạm giới hạn số phần tử này. Vì vậy tài liệu và người vận hành thường gọi nó là “hàng đợi không giới hạn”.

## 5. Cấu hình mặc định của ThreadPoolTaskExecutor trong Spring

Với bản thân class `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`, các giá trị mặc định tiêu biểu là:

| Property | Giá trị mặc định của class | Tác động |
| --- | --- | --- |
| `corePoolSize` | `1` | Một worker cơ bản |
| `maxPoolSize` | `Integer.MAX_VALUE` | Trần rất cao trên lý thuyết |
| `queueCapacity` | `Integer.MAX_VALUE` | Queue dương có khả năng chứa rất nhiều task |
| `keepAliveSeconds` | `60` | Thời gian giữ worker vượt core khi nhàn rỗi (nếu có) |
| `allowCoreThreadTimeOut` | `false` | Worker core thường không timeout |

`ThreadPoolTaskExecutor` tạo `LinkedBlockingQueue` khi `queueCapacity > 0`, còn `queueCapacity <= 0` dùng `SynchronousQueue` (giao task trực tiếp, không chứa backlog). Đây là các mặc định/nhánh tạo queue của **class Spring**, không phải lời khẳng định rằng mọi ứng dụng **Spring Boot** luôn dùng đúng các số này: cấu hình tự động của Boot, version, properties và bean executor tùy chỉnh có thể thay đổi chúng.

Hệ quả dễ bất ngờ: mặc dù `maxPoolSize` mặc định cực lớn, instance `ThreadPoolTaskExecutor` dùng toàn bộ giá trị mặc định thường có hành vi gần một worker xử lý từng task, với queue rất dài.

## 6. So sánh cùng một tải với ba loại queue

Giả sử `core = 2`, `max = 6`, có **sáu task** được gửi liên tiếp; tất cả đều chặn trên một latch nên chưa task nào hoàn tất lúc đo.

| Queue | Hai task đầu | Task 3 và 4 | Task 5 và 6 | Kết quả lúc đo |
| --- | --- | --- | --- | --- |
| `LinkedBlockingQueue(Integer.MAX_VALUE)` | Tạo 2 worker | Chờ trong queue | Tiếp tục chờ | 2 worker; 4 task chờ |
| `LinkedBlockingQueue(2)` | Tạo 2 worker | Lấp queue 2 vị trí | Queue đầy → tạo thêm 2 worker | 4 worker; 2 task chờ |
| `SynchronousQueue` | Tạo 2 worker | Không thể giữ trong queue → tạo thêm 2 worker | Tạo thêm 2 worker nữa | 6 worker; 0 task chờ |

Nhận xét quan trọng: cấu hình **queue có giới hạn** tạo cơ hội để `maxPoolSize` phát huy tác dụng, nhưng cũng có thể dẫn tới reject khi cả queue và pool đầy. **Queue bằng 0** khiến executor mở rộng sớm hơn, đồng thời có thể nhanh chạm giới hạn worker. Không có cấu hình nào tự động phù hợp mọi loại tải.

Một hệ quả ít được chú ý: với queue hữu hạn, task đến sau lúc queue đã đầy có thể được giao trực tiếp cho worker vừa tạo, trong khi task cũ vẫn chờ trong queue. **Không được dựa vào thứ tự nộp là thứ tự bắt đầu hoặc hoàn thành**, trừ khi có cơ chế bảo đảm thứ tự riêng.

## 7. Ví dụ Java 17+ độc lập: chứng minh bằng số đo

Ví dụ sau dùng trực tiếp JDK `ThreadPoolExecutor`, là nền tảng cho cơ chế đang giải thích. Nó **không cần dependency Spring**, do đó chạy độc lập để kiểm chứng đúng chính sách worker–queue trước khi đặt vào ứng dụng Spring.

Lưu vào tệp **QueueGrowthDemo.java**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueGrowthDemo {
    static void demonstrate(String label, BlockingQueue<Runnable> queue,
                            int expectedRunning) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            2, 6, 30, TimeUnit.SECONDS, queue);
        CountDownLatch started = new CountDownLatch(expectedRunning);
        CountDownLatch release = new CountDownLatch(1);

        try {
            for (int i = 0; i < 6; i++) {
                pool.execute(() -> {
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            System.out.printf("%s: pool=%d, queue=%d%n",
                label, pool.getPoolSize(), pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        demonstrate("Almost unbounded",
            new LinkedBlockingQueue<>(Integer.MAX_VALUE), 2);
        demonstrate("Bounded 2",
            new LinkedBlockingQueue<>(2), 4);
        demonstrate("Direct handoff",
            new SynchronousQueue<>(), 6);
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac QueueGrowthDemo.java
java QueueGrowthDemo
~~~

**Stdout khi các worker khởi chạy trong thời hạn 10 giây**:

~~~text
Almost unbounded: pool=2, queue=4
Bounded 2: pool=4, queue=2
Direct handoff: pool=6, queue=0
~~~

Giải thích:

- Cả ba lần chạy đều dùng `core=2`, `max=6`, sáu task và cùng chức năng task.
- `CountDownLatch release` giữ task đang chạy chưa hoàn thành, tránh kết quả bị nhiễu vì worker kết thúc quá nhanh.
- `started` xác nhận đủ số worker dự kiến đã bắt đầu trước khi đo. Vì không có task nào vượt qua `release.await()`, số worker/queued tại thời điểm in ổn định theo từng cấu hình.
- Khi kết thúc, `release.countDown()` giải phóng công việc, `shutdown()` và `awaitTermination()` dọn tài nguyên; nếu worker không thoát trong thời hạn, mới gọi `shutdownNow()`.
- Ví dụ mô phỏng **cách nhận và xếp hàng**, chưa đo throughput của một hệ thống có DB, network hoặc giới hạn downstream. Không suy ra rằng “nhiều worker hơn” luôn tốt hơn.

## 8. Cấu hình tương ứng trong Spring Framework

Dưới đây là **đoạn tích hợp Spring**, phải đặt trong dự án có `spring-context` và được ApplicationContext nạp; không phải tệp Java chạy độc lập chỉ bằng `javac`.

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class PoolConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Với `queueCapacity=2`, khi hai worker core bận và hai task khác đã chiếm hết queue, các task mới mới có thể khiến pool tăng lên ba, bốn… tối đa sáu worker. Khi queue và sáu worker đều đầy, `AbortPolicy` từ chối task.

Nếu đổi duy nhất sang `setQueueCapacity(Integer.MAX_VALUE)`, các task thường tiếp tục vào queue; việc tăng từ hai lên sáu worker hiếm xảy ra. Nếu đặt `setQueueCapacity(0)`, Spring dùng `SynchronousQueue`: không còn hàng chờ nội bộ, worker mới có thể được tạo sớm hơn đến giới hạn max, rồi task bị từ chối khi không còn khả năng nhận.

**Lưu ý:** hãy đối chiếu executor **thực sự** được `@Async` hoặc service lựa chọn. Nếu nhiều bean `TaskExecutor` tồn tại, cần chỉ rõ qualifier/tên executor thích hợp. Ngoài ra, với proxy mode thông thường, `this.methodAnnotatedAsync()` trong cùng một bean không đi qua `@Async` interceptor. Bài toán hàng đợi chỉ có ý nghĩa khi lời gọi thực sự được nộp đến pool đang xem xét.

### Không chỉ thay maxPoolSize

Cấu hình này chưa đủ để kỳ vọng pool mở rộng:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(64);
executor.setQueueCapacity(Integer.MAX_VALUE);
~~~

Thay `maxPoolSize` từ 6 thành 64 không giải quyết nút thắt nếu queue vẫn chấp nhận mọi task. Cần điều chỉnh **tương quan** giữa core, max và queue theo mục tiêu latency, sức chứa thực và khả năng downstream.

## 9. Không nên suy ra queue càng nhỏ thì càng tốt

Ba chiến lược phổ biến có đánh đổi khác nhau:

| Chiến lược | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Queue rất dài | Hấp thụ burst ngắn mà ít tạo thêm worker; giảm biến động tạo thread | Độ trễ chờ tăng, giữ reference/task trong RAM, dễ che giấu tình trạng quá tải, max không được dùng |
| Queue hữu hạn | Giới hạn backlog; pool có thể mở rộng khi queue đầy; overload rõ ràng | Phải chọn rejection/backpressure; số worker lớn có thể làm cạn connection pool và tăng contention |
| `queueCapacity = 0` | Giao task trực tiếp; pool tăng worker nhanh khi toàn bộ worker bận | Dễ tăng thread mạnh, chạm max và reject sớm; không có bộ đệm cho burst |

Điều chỉnh `corePoolSize` lên mức phù hợp có thể giúp số worker hiện diện sớm hơn ngay cả khi queue dài. Nhưng cũng cần tính **CPU**, memory, blocking I/O, số connection DB, limit của API bên ngoài, timeout và khả năng tranh chấp. Một pool với 64 worker nhưng DB chỉ có 10 connection có thể tạo thêm rất nhiều worker chờ connection thay vì xử lý nhanh hơn.

`allowCoreThreadTimeOut(true)` cho phép core worker hết hạn khi nhàn rỗi; `keepAliveSeconds` liên quan thời gian sống của worker thừa. Hai tham số này **không đổi thứ tự ưu tiên queue trước mở rộng vượt core**, nên không phải lời giải trực tiếp cho hiện tượng max không được dùng. `prestartAllCoreThreads` chỉ tạo sẵn các worker core, không tự tăng đến max.

## 10. Khi queue đầy: từ chối là một phần thiết kế

Pool có giới hạn sẽ có lúc đạt công suất tối đa. Nếu mọi worker bận và queue đầy, việc nộp task mới đi tới `RejectedExecutionHandler`. Với `ThreadPoolTaskExecutor`, lời gọi thông qua Spring có thể thể hiện việc từ chối bằng `TaskRejectedException` (một dạng `RejectedExecutionException`).

Cần quyết định ở tầng gọi:

- **Abort/reject rõ ràng:** trả thông báo quá tải hoặc lỗi thích hợp; không âm thầm giả vờ đã nhận task.
- **CallerRunsPolicy:** trong điều kiện executor đang chạy, task có thể chạy ngay trên caller thread, khiến caller chậm lại và tạo backpressure; phải chấp nhận tác động đến request latency. Khi executor shutdown, chính sách này có hành vi riêng và không bảo đảm nhận việc.
- **Retry có giới hạn:** chỉ khi tác vụ idempotent và có backoff/jitter; retry liên tục ngay vào pool đang đầy có thể làm tình hình xấu hơn.
- **Durable queue/job store:** nếu không được phép mất nhiệm vụ khi JVM chết, phải dùng cơ chế lưu công việc ngoài memory và xử lý phục hồi. Queue của executor không phải kho bền vững.

Không sử dụng `DiscardPolicy`/biến thể bỏ task một cách im lặng cho nghiệp vụ cần xác nhận hoàn tất, trừ khi chính sách bỏ việc được định nghĩa rất rõ.

## 11. Cách chẩn đoán trong một ứng dụng chạy thật

Hãy đo đồng thời những đại lượng sau, tốt nhất khi có tải tăng dần:

1. **Pool:** `corePoolSize`, `maxPoolSize`, `poolSize`, `activeCount` và peak pool size.
2. **Queue:** capacity, số phần tử đang chờ, thời gian chờ từ lúc `submit/execute` đến khi bắt đầu chạy; với queue gần như không giới hạn, số pending có thể tăng rất lâu.
3. **Lỗi/overload:** số task bị từ chối, timeout, retry, cancellation và task đang dang dở lúc shutdown.
4. **Thời gian công việc:** tổng thời gian chạy, tỉ lệ I/O wait, thời gian transaction và mức sử dụng connection pool.
5. **Áp lực tài nguyên:** heap, số thread, CPU, GC, downstream rate limits và latency phía dịch vụ phụ thuộc.

Dấu hiệu điển hình của vấn đề đang hỏi:

~~~text
corePoolSize = 2
maxPoolSize = 32
poolSize = 2
activeCount ≈ 2
queueSize tăng liên tục
rejectedCount ≈ 0
p95/p99 thời gian hoàn tất tăng
~~~

Khi quan sát được mẫu này, cần kiểm tra `queueCapacity` và chính sách queue **trước khi chỉ tiếp tục tăng `maxPoolSize`**. Nếu task có thời gian chờ dài, kiểm tra luôn downstream; pool tăng thêm worker có thể chỉ làm số connection chờ tăng.

Một bài thử tải hợp lý phải xét thời điểm tăng tải, thời điểm hệ thống ổn định, burst ngắn, saturation kéo dài và giai đoạn giảm tải. Chọn cấu hình theo SLO (latency/throughput), bộ nhớ, số connection và tỷ lệ từ chối chấp nhận được.

## 12. Những hiểu nhầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`maxPoolSize=32` nghĩa là pool sẽ có 32 worker khi tải tăng.” | Pool chỉ tăng vượt core khi queue không nhận thêm và còn dưới max. |
| “Không thấy reject nghĩa là hệ thống còn rất khỏe.” | Queue lớn có thể nhận việc mãi dù thời gian chờ tăng không kiểm soát. |
| “Queue lớn làm task chạy song song nhiều hơn.” | Queue chứa task **chờ**; worker mới là nơi xử lý song song. |
| “Chỉ cần tăng maxPoolSize để chữa chậm.” | Nếu queue chưa đầy, đổi max thường không chạm nhánh tạo thêm worker. |
| “Đặt queue=0 luôn nhanh và an toàn hơn.” | Dễ mở rộng đến max, tạo contention và reject; cần hiểu tải thực. |
| “Đặt core=max nghĩa là không có queue.” | Pool fixed-size vẫn có queue nếu được cấu hình. |
| “Queue capacity mặc định là vô hạn về mặt toán học.” | Trong `ThreadPoolTaskExecutor` mặc định là `Integer.MAX_VALUE`, cực lớn nhưng vẫn là số hữu hạn. |
| “Executor bảo đảm FIFO completion.” | Queue có thể FIFO cho task đang chờ, nhưng nhiều worker và đường tạo worker bổ sung không bảo đảm thứ tự hoàn tất tổng thể. |
| “Công việc được enqueue sẽ tồn tại qua restart.” | In-memory executor queue không bền vững qua process crash. |

## 13. Quy trình chỉnh cấu hình có kiểm soát

1. **Xác nhận đúng executor:** kiểu bean, `@Async` qualifier, implementation thực tế, các property được áp dụng và vòng đời bean.
2. **Đo điểm nghẽn:** worker đang bận, queue wait, thời gian thực thi, CPU, DB connections, remote latency; tìm rõ là thiếu worker hay hệ thống phía sau bão hòa.
3. **Đặt mục tiêu:** mức song song tối đa được phép, thời gian chờ mong muốn, số job được giữ trong bộ nhớ, chính sách khi không thể nhận thêm.
4. **Chọn bộ ba:** core đáp ứng tải bình thường, max phù hợp tài nguyên, queue hữu hạn hấp thụ burst cho phép. Có thể chọn queue=0 khi cần direct handoff và đã thiết kế overload.
5. **Định nghĩa chính sách reject và recovery:** xác nhận task đã nhận, trả lỗi, retry/backoff, idempotency, durable jobs cho công việc quan trọng.
6. **Kiểm thử tăng tải và lỗi:** dùng latch trong unit test để khống chế bão hòa; tích hợp test với DB/API thật để phát hiện contention, timeout, deadlock và bottleneck.
7. **Theo dõi sau thay đổi:** đánh giá throughput, queue wait, p95/p99, rejection, memory và downstream trước khi kết luận tối ưu.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Với `core=2`, `max=20` và queue còn rất nhiều chỗ, 100 task dài hạn được nộp liên tiếp. Tại sao pool có thể vẫn chỉ khoảng hai worker?

Vì sau khi đạt core, task mới được enqueue thành công. Executor chưa cần chạy nhánh tạo worker bổ sung đến max. Các task còn lại chờ trong queue.

**Câu 2.** Với `core=2`, `max=6`, `queueCapacity=2`, sáu task chặn đồng thời thì dự kiến trạng thái là gì?

Hai task dùng worker core, hai task xếp hàng, hai task đến sau khiến mở rộng worker. Khi giữ nguyên bằng latch, có bốn worker và hai task đang chờ, như ví dụ Java.

**Câu 3.** Vì sao không thể đặt queue=0 rồi coi là giải quyết xong vấn đề?

Vì cấu hình này chuyển áp lực từ hàng đợi sang worker và rejection, vẫn bị giới hạn bởi CPU, số connection, downstream, lỗi và độ trễ. Đúng hay không phải được đánh giá qua tải thực và SLO.

**Kết luận:** Với `ThreadPoolExecutor`, nhánh **ưu tiên enqueue sau core** giải thích trực tiếp tại sao queue gần như không giới hạn khiến `maxPoolSize` khó phát huy tác dụng. Muốn pool có cơ hội tăng vượt core, cần một chính sách queue có điểm bão hòa; muốn hệ thống xử lý tốt, còn phải thiết kế giới hạn tải, độ trễ, từ chối và tài nguyên downstream.

## Tài liệu tham khảo chính thức

- [Java SE 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — phần *Core and maximum pool sizes* và *Queuing*.
- [Spring Framework: ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — mặc định core/max/queue, đặc điểm tạo LinkedBlockingQueue và SynchronousQueue.
- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — cấu hình executor, scheduler và tích hợp `@Async`.
- [Java SE 17: LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html) và [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html) — bản chất hai loại queue.
