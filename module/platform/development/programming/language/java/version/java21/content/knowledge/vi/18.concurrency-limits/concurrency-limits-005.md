# Backpressure tại điểm tiếp nhận công việc

Backpressure là cách hệ thống điều tiết lượng công việc đi vào khi năng lực xử lý phía sau có giới hạn. Ở điểm tiếp nhận request, ứng dụng cần quyết định nhận ngay, đưa vào một hàng đợi có giới hạn, chờ trong một khoảng ngắn hay từ chối sớm. Nếu cứ nhận mọi request rồi để chúng chờ vô hạn, hàng đợi sẽ tiêu thụ bộ nhớ, latency tăng và timeout có thể lan sang nhiều dịch vụ.

Trong Java 21, có thể triển khai backpressure bằng các cơ chế chuẩn như **Semaphore**, **ThreadPoolExecutor** với hàng đợi hữu hạn và chính sách từ chối rõ ràng. Virtual thread giúp xử lý nhiều tác vụ đang chờ I/O, nhưng không thay thế giới hạn admission: số request được nhận phải phù hợp với năng lực downstream và ngân sách thời gian của hệ thống.

## 1. Backpressure bắt đầu ở đâu?

Một request thường đi qua nhiều tầng:

1. Server nhận kết nối hoặc request.
2. Ứng dụng kiểm tra xác thực, quota và khả năng tiếp nhận.
3. Request được xử lý trực tiếp hoặc đưa vào queue.
4. Worker gọi database, HTTP service hoặc message broker.
5. Kết quả được trả về và tài nguyên được giải phóng.

Nếu tầng 4 chỉ xử lý được 100 thao tác đồng thời nhưng tầng 1 tiếp nhận 2.000 request cùng lúc, phần chênh lệch phải được xử lý bằng queue, giới hạn đồng thời hoặc từ chối. Không có cơ chế nào khiến năng lực downstream tự tăng chỉ vì caller nhận thêm request.

Backpressure tốt truyền tín hiệu quá tải ngược về caller đủ sớm để caller giảm tốc, thử lại sau hoặc báo lỗi có kiểm soát. Nó giữ cho lượng công việc đang chờ nằm trong giới hạn có thể phục vụ.

## 2. Phân biệt concurrency limit, queue limit và rate limit

Ba giới hạn thường được kết hợp nhưng giải quyết các vấn đề khác nhau:

| Cơ chế | Giới hạn điều gì? | Câu hỏi cần trả lời |
|---|---|---|
| Concurrency limit | Số thao tác đang thực thi hoặc giữ tài nguyên cùng lúc | Bao nhiêu request được gọi dependency đồng thời? |
| Queue limit | Số công việc đã nhận nhưng chưa được xử lý | Hệ thống chấp nhận chờ tối đa bao nhiêu công việc? |
| Rate limit | Số công việc được nhận hoặc bắt đầu trong một đơn vị thời gian | Hệ thống cho phép bao nhiêu request mỗi giây? |

Ví dụ, một dịch vụ có thể giới hạn 40 lời gọi database đồng thời, giữ tối đa 100 công việc trong queue và cho mỗi tenant gửi tối đa 50 request/giây. Ba con số cần được hiệu chỉnh độc lập theo tài nguyên và hợp đồng dịch vụ.

**Semaphore** thường giới hạn concurrency. **ArrayBlockingQueue** hoặc queue hữu hạn của ThreadPoolExecutor giới hạn số công việc chờ. Rate limiter cần thuật toán riêng như token bucket hoặc leaky bucket; Semaphore không tự giới hạn số request mỗi giây.

## 3. Vì sao không nên dùng hàng đợi không giới hạn?

Hàng đợi không giới hạn làm hệ thống có vẻ tiếp nhận tốt trong thời gian đầu, nhưng khi tốc độ đến lớn hơn tốc độ xử lý, backlog sẽ tăng liên tục. Request có thể chờ lâu hơn deadline của chính nó, giữ payload và context trong heap, rồi cuối cùng timeout hoặc bị client hủy.

Với một queue ổn định, định luật Little cho biết:

**L = λ × W**

Trong đó L là số công việc trung bình trong toàn hệ thống, λ là throughput trung bình và W là thời gian trung bình một công việc ở trong hệ thống. Khi chỉ xét queue, dùng **Lq = λ × Wq**, trong đó Lq là số công việc chờ trung bình và Wq là thời gian chờ trung bình trong queue. Khi throughput không thể tăng thêm, queue lớn hơn thường chỉ làm thời gian chờ tăng.

Hãy đặt queue capacity theo ngân sách chờ thực tế. Nếu dịch vụ xử lý được khoảng 200 task/giây và chỉ chấp nhận chờ thêm tối đa 0,25 giây, định luật Little ước lượng số task chờ trung bình khoảng 50 trong điều kiện ổn định. Đây không phải công thức xác định queue capacity tối đa; hãy dùng nó làm điểm khởi đầu rồi kiểm chứng bằng latency phân vị và tải thực tế, đồng thời chừa headroom cho dao động.

Không chọn queue capacity chỉ dựa trên lượng RAM còn trống. Một queue có thể vừa bộ nhớ nhưng vẫn làm request chờ quá lâu và vi phạm SLO.

## 4. Dùng Semaphore để giới hạn request đang đi vào dependency

Với ứng dụng dùng virtual thread, một cách trực tiếp là kiểm tra permit tại điểm tiếp nhận trước khi gọi dịch vụ phụ thuộc. Nếu không còn permit, từ chối sớm hoặc chờ trong một khoảng thời gian có giới hạn.

~~~java
import java.util.concurrent.Semaphore;

enum AdmissionResult {
    COMPLETED,
    OVERLOADED
}

class ReportEndpoint {
    private final Semaphore slots = new Semaphore(40);

    AdmissionResult handle(ReportRequest request) {
        if (!slots.tryAcquire()) {
            return AdmissionResult.OVERLOADED;
        }

        try {
            generateReport(request);
            return AdmissionResult.COMPLETED;
        } finally {
            slots.release();
        }
    }

    private void generateReport(ReportRequest request) {
        // Có thể gọi database hoặc dịch vụ phụ thuộc bằng API blocking.
    }
}

record ReportRequest(String reportId) {
}
~~~

Semaphore cho phép tối đa 40 lời gọi giữ permit cùng lúc. Lời gọi thứ 41 không phải đợi vô hạn mà nhận kết quả OVERLOADED để tầng HTTP có thể trả phản hồi phù hợp, ví dụ **503 Service Unavailable**. Nếu giới hạn này gắn với quota của một client cụ thể, **429 Too Many Requests** có thể phù hợp hơn.

**tryAcquire()** không xếp thêm waiter trong Semaphore. Nếu chọn **tryAcquire(timeout, unit)**, caller được chờ tối đa thời gian chỉ định; thời gian chờ đó vẫn phải nằm trong deadline tổng thể. Với virtual thread, thao tác chờ có thể nhường carrier khi runtime hỗ trợ, nhưng số virtual thread đang chờ vẫn tiêu thụ bộ nhớ và trạng thái.

Permit phải được trả trong **finally** để không bị rò rỉ khi downstream ném exception hoặc thread bị interrupt. Chỉ gọi release sau khi đã acquire thành công.

## 5. Tạo hàng đợi hữu hạn với ThreadPoolExecutor

Với công việc cần worker cố định, chẳng hạn xử lý CPU-bound hoặc một pipeline có số worker được kiểm soát, có thể dùng **ThreadPoolExecutor** cùng **ArrayBlockingQueue**. Queue hữu hạn khiến executor từ chối task mới khi cả worker lẫn queue đều đã đầy.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

class BoundedWorkQueue implements AutoCloseable {
    private final ThreadPoolExecutor executor;

    BoundedWorkQueue() {
        ThreadFactory factory = Thread.ofPlatform()
                .name("report-worker-", 0)
                .factory();

        executor = new ThreadPoolExecutor(
                8,
                8,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(64),
                factory,
                new ThreadPoolExecutor.AbortPolicy()
        );
    }

    boolean submit(Runnable task) {
        try {
            executor.execute(task);
            return true;
        } catch (RejectedExecutionException overloaded) {
            return false;
        }
    }

    @Override
    public void close() {
        executor.close();
    }
}
~~~

Trong ví dụ, tối đa 8 task chạy cùng lúc và tối đa 64 task chờ trong queue. Khi cả hai giới hạn đều đạt, **AbortPolicy** ném RejectedExecutionException ngay tại lời gọi execute(). Tầng tiếp nhận có thể chuyển kết quả này thành phản hồi quá tải thay vì tiếp tục nhận thêm việc.

Các con số 8 và 64 chỉ là ví dụ. Worker count cần phù hợp với loại công việc và tài nguyên; queue capacity cần phù hợp với ngân sách chờ. Với CPU-bound task, số worker thường được hiệu chỉnh quanh năng lực CPU. Với I/O-bound task, cần đánh giá thời gian chờ và giới hạn downstream thay vì chỉ dựa vào số lõi.

Executor trong ví dụ cần được đóng theo vòng đời ứng dụng. Vì Java 21 hỗ trợ ExecutorService trong try-with-resources, caller có thể quản lý BoundedWorkQueue bằng try-with-resources; close() chờ các task đã nhận hoàn tất. Không tạo một executor mới cho mỗi request.

## 6. Chọn RejectedExecutionHandler có chủ đích

Khi executor đầy, chính sách từ chối quyết định chuyện gì xảy ra với task mới:

| Chính sách | Hành vi | Điểm cần cân nhắc |
|---|---|---|
| **AbortPolicy** | Ném RejectedExecutionException | Caller biết ngay task không được nhận; phù hợp để ánh xạ thành overload response |
| **CallerRunsPolicy** | Thread gọi execute chạy task nếu executor chưa shutdown | Tạo backpressure lên caller, nhưng có thể block request thread hoặc event loop |
| **DiscardPolicy** | Bỏ task mới mà không báo lỗi | Chỉ phù hợp khi mất task là chấp nhận được và có metric riêng |
| **DiscardOldestPolicy** | Bỏ task đầu queue rồi thử submit task mới | Có thể làm mất công việc cũ; cần chính sách nghiệp vụ rõ ràng |

Ở ranh giới HTTP hoặc event loop, **CallerRunsPolicy** có thể làm thread tiếp nhận request thực thi công việc blocking, kéo theo latency của nhiều request khác. Nếu caller là event-loop thread, việc này có thể làm nghẽn toàn bộ loop.

Với request cần phản hồi rõ ràng, AbortPolicy thường dễ kiểm soát hơn: nhận hoặc từ chối là quyết định tường minh. Nếu task có thể bỏ, hãy ghi nhận số lượng bị bỏ và bảo đảm caller không tưởng rằng công việc đã được tiếp nhận.

## 7. Kết hợp virtual thread với admission control

Virtual thread phù hợp với tác vụ I/O-bound vì có thể chờ blocking I/O mà không cần giữ một platform thread cho mỗi request. Tuy nhiên, **Executors.newVirtualThreadPerTaskExecutor()** tạo virtual thread cho mỗi task và không giới hạn số task đang chờ.

Không cần tạo một pool nhỏ để tái sử dụng virtual thread. Hãy giới hạn số tác vụ được phép đi vào tài nguyên đang khan hiếm bằng Semaphore, connection pool hoặc rate limiter:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

class VirtualTaskIngress implements AutoCloseable {
    private final Semaphore databaseSlots = new Semaphore(30);
    private final ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor();

    boolean submit(String customerId) {
        if (!databaseSlots.tryAcquire()) {
            return false;
        }

        try {
            executor.execute(() -> {
                try {
                    loadCustomerFromDatabase(customerId);
                } finally {
                    databaseSlots.release();
                }
            });
            return true;
        } catch (RejectedExecutionException submissionFailure) {
            databaseSlots.release();
            throw submissionFailure;
        }
    }

    private void loadCustomerFromDatabase(String customerId) {
        // Thực hiện thao tác blocking với database.
    }

    @Override
    public void close() {
        executor.close();
    }
}
~~~

Ví dụ lấy permit trước khi submit để từ chối ngay khi database đã có đủ 30 thao tác đang chạy hoặc chờ trong vùng được bảo vệ. Nếu submit thất bại, catch trả lại permit. Khi task bắt đầu và hoàn tất, finally trả permit.

Trong ứng dụng thực tế, cần quản lý trường hợp task bị hủy sau khi được submit nhưng trước khi bắt đầu: khi đó finally trong task chưa chạy. Nếu API cho phép hủy task đang chờ, hãy thiết kế ownership của permit và trạng thái task sao cho permit được trả đúng một lần khi task hoàn tất, bị hủy trước khi chạy hoặc bị từ chối. Không gọi release từ nhiều đường kết thúc mà không có cơ chế bảo đảm exactly-once.

Semaphore ở ví dụ giới hạn công việc được nhận cho dependency, nhưng executor per-task vẫn có thể tạo nhiều virtual thread cho các công việc khác. Hãy kết hợp giới hạn ở đầu vào của từng tài nguyên và giới hạn tổng request đang được server giữ.

Semaphore trong ví dụ là giới hạn trong một instance ứng dụng. Nếu chạy 5 replica và mỗi replica có 30 permit, tổng số lời gọi có thể đồng thời lên tới khoảng 150. Nếu downstream có quota chung cho toàn cụm, hãy chia ngân sách theo số replica hoặc áp dụng giới hạn tập trung ở gateway/dịch vụ đích; không giả định semaphore cục bộ tự tạo ra quota toàn hệ thống.

## 8. Không để waiter vô hạn ở trước Semaphore

Đoạn mã sau giới hạn số task đã lấy permit nhưng cho phép mọi virtual thread chờ permit vô thời hạn:

~~~java
slots.acquire();
try {
    callDownstream();
} finally {
    slots.release();
}
~~~

Nếu request đến liên tục trong khi downstream chậm, số virtual thread đang chờ acquire có thể tiếp tục tăng. Để backpressure thực sự, chọn một trong các cách:

- Dùng **tryAcquire()** để từ chối ngay khi không còn capacity.
- Dùng **tryAcquire(timeout, unit)** với thời gian chờ nhỏ, nằm trong request deadline.
- Giới hạn số request được server tiếp nhận đồng thời trước khi tạo task.
- Đưa công việc vào queue hữu hạn và từ chối khi queue đầy.
- Với message broker, giảm số message được consume hoặc số message in-flight theo năng lực xử lý.

Không biến một semaphore thành hàng đợi vô hạn chỉ vì mỗi waiter là virtual thread. Virtual thread giảm chi phí platform thread, nhưng mỗi waiter vẫn giữ trạng thái, stack continuation và dữ liệu request.

## 9. Trả phản hồi quá tải và hướng dẫn retry

Khi không nhận được công việc, tầng HTTP cần trả kết quả thể hiện đúng nguyên nhân:

| Tình huống | Phản hồi thường dùng |
|---|---|
| Client vượt quota hoặc rate limit riêng | **429 Too Many Requests** |
| Dịch vụ tạm thời hết capacity chung | **503 Service Unavailable** |
| Request sai hoặc không hợp lệ | 4xx tương ứng với lỗi đầu vào; không dùng overload để che validation |

Nếu biết thời điểm có thể thử lại, server có thể cung cấp **Retry-After**. Client nên dùng backoff và jitter, đồng thời tôn trọng deadline tổng thể. Không retry liên tục ngay sau khi nhận 429/503 vì điều đó làm tăng tải tại đúng thời điểm hệ thống đang quá tải.

Đối với thao tác ghi, retry cần idempotency hoặc idempotency key. Một timeout hoặc lỗi kết nối không chứng minh server chưa thực hiện thao tác; request có thể đã được xử lý nhưng response bị mất.

Nếu công việc không thể mất và người gửi cần xác nhận tiếp nhận, có thể ghi bền vững vào broker hoặc durable queue trước khi trả accepted. Queue trong bộ nhớ của ThreadPoolExecutor không phải nơi lưu trữ bền vững: process dừng có thể làm mất các task chưa chạy.

## 10. Theo dõi tín hiệu backpressure

Để biết giới hạn có đang hoạt động đúng, theo dõi:

| Metric | Điều cần quan sát |
|---|---|
| In-flight tasks | Số task đang giữ capacity |
| Available semaphore permits | Mức sử dụng giới hạn concurrency |
| Queue size và remaining capacity | Backlog và phần dung lượng còn lại |
| Queue wait time | Request phải chờ bao lâu trước khi bắt đầu |
| Rejected submissions | Số task bị từ chối do hết capacity |
| 429/503 response rate | Mức độ overload nhìn từ client |
| Downstream latency và error rate | Dịch vụ được bảo vệ có cải thiện hay không |
| Timeout và cancellation | Công việc chờ quá deadline hoặc bị client hủy |
| Heap và số virtual thread đang sống | Hàng đợi/waiter có giữ quá nhiều trạng thái không |

Theo dõi cả số lượng lẫn thời gian chờ. Queue size có thể thấp ở thời điểm lấy mẫu nhưng queue wait vẫn cao nếu worker bị chặn lâu. Metric label nên có cardinality hữu hạn; dùng trace hoặc log có cấu trúc cho từng request.

## 11. Quy trình chọn giới hạn ban đầu

1. Xác định tài nguyên cần bảo vệ: database connection, HTTP quota, CPU worker, broker hoặc một vùng critical resource.
2. Đo throughput ổn định và latency p95/p99 của tài nguyên dưới workload đại diện.
3. Chọn concurrency limit không vượt năng lực đã kiểm chứng, có khoảng dự phòng cho biến động.
4. Đặt queue capacity từ ngân sách chờ; không giữ request lâu hơn deadline hữu ích.
5. Chọn chính sách overload: từ chối ngay, chờ ngắn, giảm tốc consumer hoặc degrade chức năng ít quan trọng.
6. Thử tải vượt ngưỡng để xác nhận queue không tăng vô hạn và client nhận phản hồi đúng.
7. Kiểm tra retry không khuếch đại lưu lượng và capacity được giải phóng khi task lỗi, timeout hoặc bị hủy.

Giới hạn phải được hiệu chỉnh theo từng dependency. Một semaphore bảo vệ database không nên tự động dùng chung cho HTTP service khác nếu hai dịch vụ có năng lực và thời gian xử lý khác nhau.

## 12. Checklist backpressure tại ingress

- [ ] Có giới hạn số request hoặc task được nhận đồng thời.
- [ ] Mọi queue trong bộ nhớ đều có capacity hữu hạn.
- [ ] Không dùng hàng đợi không giới hạn để che giấu downstream chậm.
- [ ] Chọn Semaphore cho giới hạn in-flight và rate limiter cho giới hạn tốc độ.
- [ ] Trả permit trong finally và xử lý đúng trường hợp submit thất bại hoặc task bị hủy trước khi chạy.
- [ ] Chọn RejectedExecutionHandler phù hợp; không vô tình chạy blocking work trên event loop.
- [ ] Với virtual thread, không tạo vô hạn waiter chờ permit.
- [ ] Ánh xạ overload thành 429 hoặc 503 theo nguyên nhân.
- [ ] Client retry có backoff, jitter, deadline và idempotency khi cần.
- [ ] Theo dõi queue age, wait time, rejection, in-flight và downstream latency.
- [ ] Thử tải vượt ngưỡng để xác nhận hệ thống từ chối có kiểm soát.

## Tài liệu tham khảo

- [Java SE 21 API: Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 21 API: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Java SE 21 API: RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- [Java SE 21 API: Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
