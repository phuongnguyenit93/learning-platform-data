# Định cỡ connection pool và tài nguyên khi bật virtual thread

Virtual thread giúp ứng dụng Java phục vụ nhiều tác vụ blocking đồng thời với chi phí thread thấp hơn platform thread. Tuy nhiên, chúng không làm tăng số kết nối database, quota của dịch vụ HTTP, băng thông mạng, file descriptor hoặc năng lực CPU. Khi triển khai production, cần định cỡ các tài nguyên hữu hạn theo khả năng thực tế của từng dependency và kiểm soát số công việc được phép đi vào hệ thống.

Nguyên tắc quan trọng là **không dùng kích thước virtual-thread executor để giới hạn tài nguyên bên ngoài**. Dùng một virtual thread cho mỗi task; giới hạn database connection bằng connection pool, giới hạn request tới dịch vụ bằng semaphore hoặc rate limiter, và giới hạn công việc CPU bằng executor có concurrency hữu hạn.

## 1. Phân biệt virtual thread với connection pool

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được submit. Executor này không phải pool có kích thước cố định và không tái sử dụng virtual thread. Số task có thể được tiếp nhận không tự động bị giới hạn bởi số carrier thread.

Connection pool quản lý một tài nguyên khác: các kết nối vật lý hoặc logic tới database. Mỗi connection đang được một request sử dụng có thể chiếm slot ở database trong suốt thời gian transaction hoặc truy vấn cần kết nối. Số connection tối đa phải tuân theo ngân sách của database và toàn bộ ứng dụng kết nối tới nó.

| Thành phần | Quản lý | Có nên dùng để giới hạn điều gì? |
|---|---|---|
| Virtual-thread-per-task executor | Vòng đời task và virtual thread | Không dùng để giới hạn số database connection hoặc quota dịch vụ ngoài |
| JDBC connection pool | Kết nối database | Giới hạn số connection đang được ứng dụng mượn |
| `Semaphore` | Số tác vụ được vào một vùng công việc | Giới hạn concurrency tới một dependency hoặc tài nguyên dùng chung |
| Rate limiter | Số lần gọi trong một khoảng thời gian | Tuân thủ quota theo giây/phút của dịch vụ |
| CPU executor có giới hạn | Công việc CPU-bound đang chạy và đang chờ | Tránh đưa quá nhiều phép tính nặng vào CPU cùng lúc |

Không tạo một fixed pool gồm virtual thread chỉ để có giới hạn concurrency. Hãy đặt giới hạn tại tài nguyên thực sự cần bảo vệ.

## 2. Lập ngân sách connection database

Kích thước pool của một instance phải nằm trong ngân sách kết nối database dành cho toàn bộ hệ thống. Bắt đầu bằng cách xác định:

1. Giới hạn connection tối đa của database hoặc proxy.
2. Số connection cần dành cho quản trị, migration, monitoring, backup và tác vụ vận hành.
3. Số connection được các ứng dụng khác sử dụng.
4. Số instance tối đa mà hệ thống có thể scale tới, không chỉ số instance trung bình.
5. Số connection pool trong mỗi instance; một ứng dụng có thể có pool riêng cho nhiều datasource.

Công thức ngân sách đơn giản:

\[C_{app} = C_{db} - C_{reserve} - C_{other}\]

\[C_{instance} \leq \left\lfloor \frac{C_{app}}{N_{maxInstances}} \right\rfloor\]

Trong đó `C_db` là giới hạn kết nối database, `C_reserve` là phần dự phòng vận hành, `C_other` là phần dành cho ứng dụng khác và `N_maxInstances` là số instance tối đa có thể chạy đồng thời. Đây là giới hạn ngân sách, không phải khuyến nghị phải dùng hết số connection đó.

Ví dụ: database cho phép 120 connection, hệ thống giữ lại 20 cho quản trị và tác vụ khác, còn 100 dành cho dịch vụ này. Nếu autoscaling có thể chạy tối đa 5 instance, tổng pool maximum của dịch vụ không nên vượt 20 connection mỗi instance. Nếu mỗi instance có hai datasource, cần chia ngân sách 20 đó giữa hai pool.

Khi autoscaling tăng số instance, tổng connection tăng theo. Nếu chỉ cấu hình pool dựa trên một instance rồi scale out mà không tính tổng, database có thể cạn connection dù từng instance vẫn hoạt động bình thường.

## 3. Không chọn pool size chỉ theo số CPU hoặc số virtual thread

Connection pool phục vụ database, nên số lượng connection cần dựa trên khả năng xử lý truy vấn và transaction của database. Các yếu tố ảnh hưởng gồm:

- Throughput của các thao tác database.
- Thời gian trung bình một thao tác giữ connection, bao gồm thời gian query và thời gian ứng dụng giữ connection trong transaction.
- Mức độ song song database có thể xử lý mà không tăng lock contention, I/O wait hoặc queueing.
- Số connection được chia sẻ với ứng dụng và công việc khác.
- Độ biến động của thời gian query, transaction dài và workload cao điểm.

CPU core count là thông tin hữu ích cho CPU-bound task, nhưng không phải công thức trực tiếp để định cỡ JDBC pool. Một database có thể đạt throughput tốt nhất với ít connection hơn nhiều so với số virtual thread đang chờ.

## 4. Dùng Little’s Law để ước lượng concurrency ban đầu

Định luật Little mô tả quan hệ giữa số công việc trung bình đang ở trong hệ thống (`L`), throughput (`λ`) và thời gian trung bình trong hệ thống (`W`):

\[L = \lambda \times W\]

Với connection pool, có thể dùng throughput của các thao tác thực sự giữ connection và thời gian giữ connection trung bình để ước lượng số connection đang bận trung bình.

Ví dụ, dịch vụ thực hiện 100 thao tác database mỗi giây; mỗi thao tác giữ connection trung bình 40 ms (0,04 giây). Số connection bận trung bình ước tính là:

\[L = 100 \times 0.04 = 4\]

Bốn connection là mức bận trung bình theo giả định này, không phải pool size tối ưu được bảo đảm. Cần thêm dữ liệu về peak traffic, p95/p99 thời gian giữ connection, transaction dài, burst và khả năng xử lý của database. Đo thực tế để tìm điểm throughput đạt yêu cầu mà latency và DB resource vẫn nằm trong giới hạn.

Nếu mỗi request gọi database nhiều lần, `λ` trong phép tính phải là tốc độ các thao tác lấy connection, không phải số HTTP request đầu vào. Nếu một request giữ connection xuyên suốt nhiều bước không cần thiết, thời gian giữ connection sẽ tăng và pool cần nhiều slot hơn.

## 5. Đo thời gian giữ connection và tránh giữ connection quá lâu

Connection chỉ nên được mượn trong khoảng thời gian cần truy cập database. Không giữ connection trong lúc gọi HTTP, chờ message broker, sleep hoặc thực hiện phép tính CPU dài.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

static Account loadAccount(DataSource dataSource, long accountId)
        throws Exception {
    String sql = "select id, name from account where id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, accountId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return null;
            }
            return new Account(
                    result.getLong("id"),
                    result.getString("name"));
        }
    }
}
```

`DataSource` trong ví dụ nên được cung cấp bởi connection pool đã cấu hình giới hạn và timeout. `try-with-resources` đóng logical connection sau thao tác; với pooled datasource, connection được trả về pool để tái sử dụng.

JDBC là API blocking, nhưng khả năng virtual thread unmount trong lúc driver chờ I/O phụ thuộc cách driver và runtime thực hiện thao tác. Kiểm tra phiên bản driver đang dùng và đo bằng JFR trên đúng JDK; không giả định mọi driver đều có hành vi giống nhau. Trên Java 21, blocking trong một vùng `synchronized` hoặc native call có thể pin virtual thread vào carrier.

Đừng lấy connection quá sớm rồi mới thực hiện công việc không liên quan. Nếu cần gọi dịch vụ bên ngoài và sau đó ghi kết quả vào database, hãy cân nhắc hoàn tất lời gọi bên ngoài trước, rồi mở transaction ngắn để ghi dữ liệu, miễn là nghiệp vụ cho phép.

## 6. Cấu hình connection pool theo workload

Các thư viện connection pool có tên cấu hình khác nhau, nhưng thường có những tham số tương đương:

| Tham số | Ý nghĩa | Cách chọn |
|---|---|---|
| Maximum pool size | Số connection tối đa pool có thể cấp đồng thời | Không vượt ngân sách connection của instance và database |
| Minimum idle | Số connection nhàn rỗi pool cố gắng duy trì | Chọn theo mức tải nền và chi phí mở connection; không cần đặt bằng maximum mặc định |
| Connection acquisition timeout | Thời gian tối đa chờ mượn connection | Đặt phù hợp với request deadline và SLA |
| Idle timeout | Thời gian connection nhàn rỗi trước khi có thể bị đóng | Theo đặc tính pool và database |
| Maximum lifetime | Tuổi thọ tối đa của connection trong pool | Phối hợp với timeout/rotation của database hoặc proxy |
| Validation/keepalive | Kiểm tra hoặc duy trì connection | Chỉ bật theo nhu cầu và hướng dẫn của pool/database |

Không copy một bộ giá trị cấu hình từ máy khác mà không tính số instance, giới hạn database và đặc tính query. Các tham số như `maximumPoolSize`, `connectionTimeout` hoặc `minimumIdle` là cấu hình của thư viện pool cụ thể, không phải API chuẩn của Java.

Khi pool hết connection, virtual thread có thể chờ để mượn connection. Đây là hành vi chờ có thể phù hợp với virtual thread, nhưng nếu không có acquisition timeout và giới hạn số request đầu vào, số virtual thread chờ có thể tăng cao, giữ memory và làm latency lan rộng.

## 7. Dùng Semaphore để giới hạn concurrency tới dịch vụ ngoài

Không phải dependency nào cũng có connection pool có thể cấu hình theo yêu cầu. Có thể dùng `Semaphore` để giới hạn số lời gọi đang đồng thời sử dụng một dịch vụ, ví dụ API đối tác có giới hạn concurrency.

```java
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class PartnerClient {
    private final HttpClient client;
    private final Semaphore permits;

    PartnerClient(HttpClient client, int maxConcurrentCalls) {
        if (maxConcurrentCalls <= 0) {
            throw new IllegalArgumentException("maxConcurrentCalls must be positive");
        }
        this.client = client;
        this.permits = new Semaphore(maxConcurrentCalls);
    }

    String fetch(HttpRequest request)
            throws IOException, InterruptedException {
        if (!permits.tryAcquire(250, TimeUnit.MILLISECONDS)) {
            throw new java.util.concurrent.RejectedExecutionException(
                    "Partner concurrency limit reached");
        }

        try {
            return client.send(
                    request, HttpResponse.BodyHandlers.ofString()).body();
        } finally {
            permits.release();
        }
    }
}
```

Virtual thread có thể chờ ở `tryAcquire` mà không cần chiếm một platform thread trong suốt thời gian chờ theo cơ chế park hỗ trợ virtual thread. `finally` bảo đảm permit được trả lại khi request thành công hoặc ném exception.

Ví dụ dùng một semaphore công bằng mặc định là `false`; nếu cần fairness, có thể khởi tạo `new Semaphore(maxConcurrentCalls, true)`, nhưng fairness có thể ảnh hưởng throughput. Chọn theo yêu cầu thực tế và đo đạc.

Semaphore giới hạn số lời gọi đồng thời trong một instance. Nếu dịch vụ chạy nhiều replica, tổng concurrency tối đa xấp xỉ `permitsPerInstance × instanceCount`. Quota dùng chung toàn cluster cần rate limiter hoặc cơ chế điều phối phân tán ở tầng phù hợp; semaphore cục bộ không tự chia sẻ trạng thái giữa các instance.

## 8. Phân biệt concurrency limit với rate limit

Semaphore giới hạn số thao tác đang diễn ra cùng lúc. Rate limiter giới hạn số lần bắt đầu thao tác trong một khoảng thời gian. Hai giới hạn này không tương đương:

- Một dịch vụ có thể cho phép tối đa 20 request đồng thời nhưng chỉ 100 request mỗi giây.
- Request có thời gian xử lý ngắn có thể hoàn tất nhanh; concurrency thấp vẫn có thể tạo rate cao.
- Request chậm có thể làm concurrency cao dù rate không lớn.

Nếu dependency công bố cả quota theo giây và giới hạn concurrency, cần thực thi cả hai. Không dùng semaphore thay cho rate limiter hoặc ngược lại.

## 9. Admission control và backpressure ở đầu vào

`newVirtualThreadPerTaskExecutor()` không giới hạn tổng số task được submit. Nếu hệ thống nhận traffic nhanh hơn tốc độ xử lý, việc tạo một virtual thread cho mọi request rồi để tất cả chờ semaphore hoặc connection pool có thể làm tăng số task in-flight, memory, request timeout và độ trễ.

Admission control quyết định có nhận thêm công việc hay không trước khi hệ thống cạn tài nguyên. Có thể thực hiện bằng:

- Giới hạn số request in-flight tại server hoặc gateway.
- Bounded queue cho công việc cần xếp hàng.
- Semaphore ở ranh giới dependency hoặc loại job.
- Rate limit theo client, tenant hoặc API key.
- Từ chối sớm với HTTP 429/503 hoặc phản hồi nghiệp vụ tương ứng khi vượt tải.

Backpressure giúp tầng nhận việc giảm tốc độ khi tầng xử lý phía sau đã đạt giới hạn. Một hệ thống từ chối có kiểm soát thường ổn định hơn hệ thống tiếp nhận không giới hạn rồi để mọi request timeout.

## 10. Mô hình virtual thread-per-task trong production

Java 21 cung cấp `Executors.newVirtualThreadPerTaskExecutor()` để chạy task bằng virtual thread. Executor đóng vai trò quản lý vòng đời task; giới hạn tài nguyên được đặt riêng ở các dependency.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

static void serveBatch(Iterable<Request> requests) {
    try (ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor()) {
        for (Request request : requests) {
            executor.submit(() -> handle(request));
        }
    }
}
```

Ví dụ này thể hiện mô hình thread-per-task. Trong server thực tế, request thường được dispatch bởi framework; không cần tạo một executor mới cho từng request. Executor nên được quản lý theo vòng đời ứng dụng hoặc component và đóng khi shutdown.

Không pool virtual thread để tái sử dụng. Nếu cần giới hạn task, hãy đặt admission control trước khi submit hoặc dùng semaphore/bounded queue tại nơi tài nguyên được sử dụng.

## 11. Định cỡ tài nguyên CPU-bound riêng biệt

Virtual thread không làm một phép tính CPU-bound chạy nhanh hơn. Nếu hàng nghìn virtual thread cùng thực hiện nén, mã hóa, phân tích ảnh hoặc tính toán nặng, chúng vẫn tranh chấp số CPU core hữu hạn.

Có thể tách phần CPU-bound sang executor platform thread có concurrency hữu hạn. `Runtime.getRuntime().availableProcessors()` là điểm bắt đầu để hiểu số processor JVM nhận diện; kích thước thực tế cần benchmark theo CPU quota, GC, tác vụ nền và yêu cầu latency.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

int cpuParallelism = Runtime.getRuntime().availableProcessors();
ExecutorService cpuExecutor =
        Executors.newFixedThreadPool(cpuParallelism);

// Submit phép tính CPU nặng vào cpuExecutor.
Future<Result> result = cpuExecutor.submit(() -> calculate(input));
```

Trong ứng dụng thật, quản lý executor theo vòng đời service và đóng khi shutdown. Nếu executor dùng fixed thread pool mặc định, queue của nó không giới hạn; cần admission control hoặc bounded queue khi lượng CPU task có thể tăng không kiểm soát.

## 12. Ước lượng memory khi có nhiều virtual thread

Virtual thread có chi phí thấp hơn platform thread nhưng không miễn phí. Mỗi task vẫn có thể giữ:

- Stack chunks và trạng thái thực thi của virtual thread.
- Request object, context, trace/span, security principal và dữ liệu nghiệp vụ.
- Buffer để đọc/ghi request hoặc response.
- Các object được tham chiếu trong lúc chờ I/O.
- Future, callback và cấu trúc xếp hàng.

Memory cần dự trù theo số task in-flight và lượng dữ liệu mỗi task giữ lại, không chỉ theo số carrier thread. Một request giữ buffer vài MB trong lúc chờ dịch vụ ngoài có thể tiêu thụ nhiều heap hơn phần trạng thái virtual thread.

`-Xmx` chỉ giới hạn Java heap. Process còn cần native memory cho metaspace, code cache, direct buffer, thư viện native, socket và platform-thread stacks. Khi đặt memory limit container, cần để headroom cho phần ngoài heap.

Không dùng một con số cố định “mỗi virtual thread tốn X KB” làm cơ sở sizing cho mọi ứng dụng. Footprint phụ thuộc stack depth, object graph, ThreadLocal, context propagation và thời gian task giữ dữ liệu. Đo heap, allocation rate và live set dưới tải thực tế.

## 13. Socket, file descriptor và connection tới dịch vụ ngoài

Mỗi socket đang mở thường tiêu thụ file descriptor và tài nguyên ở cả client lẫn server. Virtual thread có thể làm ứng dụng dễ tạo nhiều request đồng thời hơn, nhưng hệ điều hành và dependency vẫn có giới hạn:

- Số file descriptor tối đa của process/container.
- Số socket outbound và ephemeral port.
- Connection limit của HTTP server, database proxy hoặc load balancer.
- Băng thông mạng, TLS handshake CPU và buffer cho mỗi connection.
- Giới hạn kết nối và quota theo tenant của dịch vụ ngoài.

HTTP client thường tái sử dụng connection theo cấu hình và implementation. Không tạo một `HttpClient` mới cho mỗi request nếu mục tiêu là connection reuse; quản lý client theo vòng đời ứng dụng và cấu hình timeout phù hợp.

## 14. Theo dõi pool và dependency

Các metric nên được thu thập ở tầng pool, dependency và ứng dụng:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active connections | Số connection đang được mượn | Luôn chạm maximum có thể cho thấy pool hoặc DB là bottleneck |
| Idle connections | Số connection sẵn sàng | Luôn bằng 0 cùng pending borrowers có thể báo thiếu capacity |
| Pending borrowers | Số request đang chờ connection | Tăng kéo dài cho thấy pool acquisition queueing |
| Acquisition latency | Thời gian mượn connection | p95/p99 tăng làm latency request tăng |
| Acquisition timeout | Số lần không lấy được connection trong hạn | Có thể báo quá tải hoặc DB/network sự cố |
| Query/transaction duration | Thời gian dùng connection | Transaction dài làm giảm số thao tác pool phục vụ được |
| DB CPU, I/O và lock waits | Khả năng xử lý phía database | DB bão hòa thì tăng pool có thể làm tình hình xấu hơn |
| Downstream in-flight, latency, error, 429 | Trạng thái dịch vụ ngoài | Điều chỉnh semaphore/rate limit và retry policy |

Ở tầng JVM, theo dõi heap, allocation rate, GC, CPU, container throttling, socket/file descriptor và JFR. Với Java 21, `ThreadMXBean` chỉ phản ánh platform thread; không dùng số đó để đếm toàn bộ virtual thread hoặc suy ra số request đang hoạt động.

JFR giúp điều tra pinning và hoạt động thread. Khi chạy trên Java 21, blocking trong `synchronized` hoặc native/foreign call có thể pin virtual thread vào carrier. JEP 491 thay đổi monitor pinning từ JDK 24; khi nâng runtime, đánh giá lại bằng JFR trên đúng JDK đang chạy.

## 15. Timeout, retry và transaction

Định cỡ pool phải đi cùng timeout và deadline. Nếu request chờ connection lâu hơn thời gian nghiệp vụ cho phép, request có thể hết hạn trước khi query bắt đầu.

- Đặt connection acquisition timeout ngắn hơn hoặc phù hợp với deadline tổng của request.
- Đặt query timeout và transaction timeout theo đặc tính thao tác, nếu driver/database hỗ trợ.
- Không giữ transaction mở trong lúc gọi HTTP hoặc chờ user input.
- Chỉ retry lỗi tạm thời và thao tác có thể retry an toàn; dùng idempotency key cho thao tác ghi khi phù hợp.
- Dùng exponential backoff và jitter; retry không giới hạn có thể khuếch đại sự cố database.
- Khi dependency đang quá tải, circuit breaker và admission control có thể ngăn request mới tiếp tục dồn vào pool.

Timeout khi chờ pool không giống query timeout. Một request có thể hết thời gian trước khi lấy được connection; một request khác đã lấy connection có thể bị chậm trong query. Theo dõi hai giai đoạn riêng để tìm đúng nguyên nhân.

## 16. Quy trình định cỡ từ staging đến production

1. **Liệt kê dependency:** database, HTTP service, broker, filesystem và giới hạn/quota của từng hệ thống.
2. **Tính budget toàn cluster:** trừ phần reserve và client khác khỏi giới hạn database; dùng số replica tối đa khi chia ngân sách mỗi instance.
3. **Đo workload:** thu thập request rate, số lần gọi dependency trên mỗi request, thời gian giữ connection, latency và peak traffic.
4. **Ước lượng concurrency:** dùng Little’s Law làm điểm xuất phát; kiểm chứng bằng load test thay vì coi kết quả là pool size cuối cùng.
5. **Đặt giới hạn và timeout:** cấu hình pool maximum, acquisition timeout, semaphore, rate limit và admission control.
6. **Chạy tải tăng dần:** đo throughput, p95/p99, pending borrowers, DB CPU, lock waits, heap, CPU và lỗi.
7. **Tìm điểm bão hòa:** nếu DB đã bão hòa, tăng pool thường chỉ làm queue và contention tăng; xem lại query, index, transaction hoặc phân tải.
8. **Kiểm tra scale-out:** xác nhận tổng pool maximum ở số replica lớn nhất vẫn nằm trong budget.
9. **Kiểm tra sự cố:** thử database chậm, connection bị ngắt, dependency trả 429/5xx và request timeout; xác nhận hệ thống giảm tải có kiểm soát.
10. **Theo dõi production:** cảnh báo pool wait, timeout, error rate, DB saturation, heap pressure và container throttling.

## 17. Những cấu hình dễ gây sự cố

- **Pool quá lớn:** database phải quản lý quá nhiều session, tăng memory, lock contention và context switching.
- **Pool quá nhỏ:** pending borrowers tăng và request chờ connection dù database còn khả năng xử lý.
- **Tính pool theo một replica:** autoscaling làm tổng connection vượt giới hạn database.
- **Không đặt acquisition timeout:** virtual thread chờ lâu, giữ context và làm latency dây chuyền tăng.
- **Tạo vô hạn virtual thread cho traffic không giới hạn:** số task chờ và memory tăng dù số kết nối được semaphore/pool giới hạn.
- **Giữ connection trong lúc gọi dịch vụ ngoài:** connection bị chiếm trong thời gian không dùng database.
- **Dùng semaphore cục bộ để tuân thủ quota cluster:** mỗi replica có permit riêng nên tổng request vẫn vượt quota toàn hệ thống.
- **Dùng virtual thread cho CPU-bound không giới hạn:** CPU bão hòa và queue tăng mà throughput không cải thiện.
- **Retry quá nhiều khi pool cạn:** tăng tải vào đúng dependency đang quá tải.

## 18. Cấu hình và kiểm tra với Java 21

Java 21 cung cấp virtual threads ở trạng thái final. Có thể tạo executor cho từng task như sau:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> handleRequest());
}
```

Không cần `--enable-preview`. Executor này không tự giới hạn số task; cấu hình pool, semaphore và admission control ở các ranh giới tài nguyên theo ngân sách đã đo.

JVM có các thuộc tính nâng cao để điều chỉnh scheduler virtual thread, chẳng hạn `jdk.virtualThreadScheduler.parallelism` và `jdk.virtualThreadScheduler.maxPoolSize`. Chỉ xem xét chúng khi đã có bằng chứng scheduler là bottleneck và hiểu tác động lên carrier platform thread. Đây không phải tham số thay thế connection pool, semaphore, rate limiter hoặc giới hạn CPU task.

Khi triển khai trên JDK khác Java 21, kiểm tra tài liệu runtime và hành vi pinning tương ứng. Không bê nguyên một cấu hình scheduler hoặc giả định pinning từ Java 21 sang mọi JDK mới.

## 19. Checklist production

- [ ] Tổng connection pool maximum được tính theo số replica tối đa và ngân sách database.
- [ ] Mỗi datasource/pool có giới hạn và acquisition timeout rõ ràng.
- [ ] Connection chỉ được giữ trong thời gian truy cập database cần thiết.
- [ ] Dependency có giới hạn concurrency và rate phù hợp với quota của nó.
- [ ] Có admission control/backpressure cho lượng request hoặc task đầu vào.
- [ ] CPU-bound work chạy với mức song song hữu hạn và queue được kiểm soát.
- [ ] Heap, direct memory, socket, file descriptor và container memory có headroom.
- [ ] Có metrics active/idle/pending connections, acquisition latency, timeout và query duration.
- [ ] Có metrics in-flight request, latency percentiles, retry, cancellation và rejection.
- [ ] Load test xác nhận throughput, latency và error rate ở tải bình thường lẫn peak.
- [ ] Đã thử nghiệm khi database hoặc dependency chậm và khi scale tới số replica tối đa.
- [ ] JFR và GC logging có thể bật để điều tra pinning, CPU, allocation và GC khi cần.

## 20. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — DataSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [HikariCP — Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
