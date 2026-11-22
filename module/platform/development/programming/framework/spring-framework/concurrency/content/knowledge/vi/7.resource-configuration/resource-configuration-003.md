# Giới hạn theo số kết nối cơ sở dữ liệu hoặc dịch vụ đích

## 1. Vì sao phải giới hạn công việc đồng thời theo tài nguyên đích?

Trong ứng dụng Spring, việc tăng số request thread, dùng `@Async`, mở rộng `ThreadPoolTaskExecutor` hoặc bật virtual threads cho phép nhiều tác vụ tiến triển cùng thời điểm. Nhưng mỗi tác vụ vẫn có thể cần **kết nối JDBC**, **kết nối HTTP**, **suất xử lý của API đối tác**, **giao dịch dài**, bộ nhớ hoặc CPU. Năng lực tiếp nhận việc của executor không đồng nghĩa với năng lực phục vụ của tài nguyên bên dưới.

Ví dụ: một instance Spring có 40 worker xử lý báo cáo, nhưng datasource chỉ cho phép 10 kết nối JDBC. Khi cả 40 worker cùng truy vấn database, chỉ tối đa 10 kết nối của pool đó có thể được cấp đồng thời; các worker còn lại có thể bị giữ trong lúc chờ mượn connection, rồi timeout. Việc tăng worker lên 80 không tạo thêm connection. Nếu database cũng đang bão hòa, tăng pool lên 80 có thể còn làm tình hình tệ hơn vì DB phải xử lý nhiều transaction cùng lúc.

Bài học này giải thích cách **xác định ngân sách tài nguyên**, **giới hạn số hoạt động đồng thời tại điểm gọi**, **cấu hình connection pool và executor**, **xử lý khi chạm trần**, **quan sát hệ thống** và **kiểm chứng dưới tải**. Trọng tâm là mối quan hệ giữa Spring concurrency và số connection/khả năng tiếp nhận của database hoặc dịch vụ đích.

### Bốn giới hạn khác nhau

| Giới hạn | Đếm cái gì? | Ví dụ | Không tự bảo đảm |
| --- | --- | --- | --- |
| Executor concurrency | Số task đang chạy trên một executor | 8 worker `@Async` | Chỉ tối đa 8 truy vấn SQL trên toàn ứng dụng |
| JDBC connection pool | Số connection vật lý pool quản lý, gồm idle và active | HikariCP `maximumPoolSize=12` | Database đủ CPU hoặc mọi transaction nhanh |
| HTTP connection pool | Số kết nối mạng do client quản lý, thường theo remote host | Reactor Netty `maxConnections=16` | Đúng 16 request in-flight, đặc biệt với HTTP/2 |
| Target bulkhead/admission limit | Số cuộc gọi nghiệp vụ được phép đồng thời tới một dependency | 6 thao tác đồng thời gọi service thanh toán | Rate limit 60 requests/giây hoặc quota toàn cluster |

**Connection**, **thread**, **task**, **HTTP request**, **transaction** và **request/giây** là những đơn vị khác nhau. Muốn bảo vệ dịch vụ đích phải chọn giới hạn đúng theo đơn vị dịch vụ đó thực sự bị quá tải.

## 2. Hiểu cơ chế nghẽn: từ executor tới database và API bên ngoài

Một đường xử lý đồng bộ thường có dạng:

```text
HTTP request / scheduled job / message
           |
           v
    Spring controller/service
           |
           v
        executor              <-- có thể có worker/queue riêng
           |
      +----+------+
      |           |
      v           v
 HikariCP      HTTP client    <-- hai loại connection pool khác nhau
      |           |
      v           v
 Database      Remote API     <-- server đích cũng có giới hạn riêng
```

Giả sử luồng xử lý như sau:

1. Request vào Spring; một task được nhận vào executor, chiếm một worker.
2. Task gọi `JdbcTemplate`/JPA; connection pool cho mượn một connection nếu có sẵn.
3. Khi pool hết connection, task có thể **đợi tại bước mượn connection**. Worker trong lúc đó vẫn bị chiếm nếu dùng mô hình blocking.
4. Nếu hết thời gian chờ, HikariCP ném lỗi lấy connection; nếu mượn được, SQL còn phải chờ lock, CPU, I/O hoặc tài nguyên DB.
5. Task trả connection về pool khi phạm vi sử dụng/transaction kết thúc, rồi có thể gọi dịch vụ HTTP khác, lại chịu quy tắc connection pool, timeout và hạn mức phía server.

**Vì sao latency tăng đột ngột khi quá tải?** Công việc đến nhanh hơn năng lực hoàn thành thì người dùng bắt đầu chờ ở nhiều hàng đợi: executor queue, JDBC connection acquisition, DB locks, HTTP pool pending acquisitions hoặc hàng đợi của downstream. Mỗi lớp đều có thể làm tổng thời gian phản hồi dài thêm.

**Vì sao tăng thread không giải quyết được?** Thread chờ kết nối không giúp DB xử lý thêm việc; nó vẫn tốn bộ nhớ, chiếm vị trí trong pool executor và có thể kéo dài timeout của request khác. Số request đang hoạt động tăng mà throughput không tăng tương ứng.

## 3. Giới hạn theo DB connection: HikariCP trong Spring Boot

### 3.1. `maximumPoolSize` và `connectionTimeout`

Với một datasource dùng **HikariCP**, hai cấu hình cơ bản là:

- **`maximumPoolSize`:** số connection tối đa mà pool quản lý, tính cả connection đang được mượn và connection nhàn rỗi. Đây là giới hạn **mỗi pool trên mỗi instance**, không phải giới hạn của toàn DB cluster.
- **`connectionTimeout`:** thời gian tối đa một caller đợi lấy connection từ pool khi chưa có connection sẵn. Đến hạn, HikariCP báo lỗi; đó **không phải** timeout cho câu SQL sau khi đã mượn được connection.

Ví dụ cấu hình trong **`application.yml`** của ứng dụng Spring Boot 3.x dùng HikariCP:

```yaml
spring:
  datasource:
    hikari:
      pool-name: application-db
      maximum-pool-size: 12
      connection-timeout: 2000
```

Đây là **đoạn cấu hình tích hợp**: datasource URL/credentials và JDBC driver phải được cấu hình ở nơi thích hợp. `connection-timeout: 2000` có đơn vị **mili-giây** (2 giây). Khi cả 12 connection đang được dùng và không có connection nhàn rỗi, yêu cầu lấy connection mới sẽ chờ tối đa theo thời hạn đó, rồi báo lỗi nếu không có connection.

Spring Boot thường chọn HikariCP khi HikariCP có trên classpath; các starter JDBC/JPA phổ biến thường kéo HikariCP vào. Nếu ứng dụng chủ động dùng datasource hay connection pool khác, thuộc tính `spring.datasource.hikari.*` **không nhất thiết áp dụng**. Hãy xác minh bean `DataSource` thực tế và các pool được cấu hình, nhất là ứng dụng có nhiều datasource.

Đừng nhầm:

- `maximumPoolSize=12` không có nghĩa là “12 SQL mỗi giây”.
- Cùng một connection có thể chạy nhiều câu SQL **nối tiếp** trong một transaction.
- Một request có thể mượn connection nhiều lần hoặc có lúc giữ nhiều connection tùy thiết kế/transaction.
- Connection được mượn nhưng đang chờ DB lock vẫn chiếm một suất trong pool.
- Tăng `maximumPoolSize` không tự tăng sức mạnh CPU/IOPS của database.

### 3.2. Vì sao transaction dài làm nghẽn pool?

Trong xử lý JDBC thông thường, một transaction đang hoạt động có thể giữ connection cho tới commit hoặc rollback. Nếu code mở transaction rồi gọi HTTP bên ngoài với độ trễ 3 giây, connection có thể bị giữ dù DB không làm việc trong khoảng đó. Tải tăng sẽ làm cạn pool nhanh.

Ví dụ **mẫu cần xem xét lại**:

```java
@Transactional
public void updateAndNotify(Order order) {
    repository.save(order);
    remoteClient.sendNotification(order.getId()); // Có thể đợi mạng lâu.
}
```

Đây là snippet minh họa, không phải class chạy độc lập. Nó còn có rủi ro về nhất quán: DB có thể rollback nhưng remote notification đã gửi; hoặc remote thất bại sau khi tác động ra ngoài. Thiết kế phù hợp thường là giảm phạm vi transaction, tách xử lý ngoài DB ra sau commit hoặc dùng **transactional outbox** khi cần phát sự kiện đáng tin cậy. Không được tự ý tách transaction nếu nghiệp vụ cần bảo đảm nguyên tử ở DB; phải phân tích yêu cầu consistency trước.

Các dấu hiệu cần kiểm tra: thời gian transaction, số connection active, số request chờ mượn connection, truy vấn chậm, lock wait, N+1 query, leak connection và timeout trong lúc DB cao tải.

### 3.3. Connection leak và tài nguyên phải được đóng

Với JDBC thuần, luôn trả connection, statement và result set về đúng vòng đời, thường bằng `try-with-resources`:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT COUNT(*) FROM orders");
     ResultSet rows = statement.executeQuery()) {
    if (rows.next()) {
        return rows.getLong(1);
    }
    return 0L;
}
```

Đây là method-body snippet với `dataSource` đã được inject; class/chữ ký/exception phải được bổ sung khi tích hợp. Không tự đóng connection bên trong một transaction do Spring quản lý theo cách phá vòng đời của transaction. Với `JdbcTemplate`, JPA và quản lý transaction của Spring, ưu tiên cơ chế framework quản lý connection đúng ranh giới.

**Một pool cạn** có thể do tải hợp lệ, transaction giữ connection quá lâu, leak, deadlock hoặc backend chậm. Đừng kết luận cứ “pool nhỏ” là phải tăng size.

## 4. Lập ngân sách kết nối theo số instance và workload

### 4.1. Giới hạn toàn DB và giới hạn mỗi pod

Giả sử database cho phép tối đa **100 connections**, ta dành **20** cho vận hành/phiên quản trị/bảo trì và **20** cho các hệ thống khác. Còn ngân sách **60 connections** dành cho dịch vụ Spring. Nếu dịch vụ chạy **4 instance** và chỉ có một datasource mỗi instance, một trần sơ bộ là:

```text
Ngân sách dịch vụ = 100 - 20 - 20 = 60 connections
Trần sơ bộ mỗi instance = floor(60 / 4) = 15 connections
```

Con số 15 là **ngưỡng ngân sách kết nối**, chưa phải lời khuyên đặt pool đúng 15. Database có thể đạt giới hạn CPU, I/O hoặc lock contention khi số connection active thấp hơn nhiều. Cần thử tải và theo dõi throughput, p95/p99 latency, query wait, DB saturation để chọn giá trị phù hợp.

Nếu autoscaling từ 4 lên 8 instance nhưng giữ `maximumPoolSize=15`, riêng nhóm này có thể giữ tới **120 connections** (cả idle lẫn active tùy vòng đời pool), vượt ngân sách 60. Tính giới hạn theo **số instance cực đại**, không chỉ số pod đang chạy ở thời điểm cấu hình.

Cách tính tổng quát cho các pool tương tự:

```text
Tổng trần connections từ ứng dụng
  = số instance × số pool mỗi instance × maximumPoolSize của từng pool
  (nếu mọi pool cùng kích thước; nếu khác thì cộng trần từng pool)

Ngân sách khả dụng
  = giới hạn DB - phần dành cho hệ thống khác - dự phòng vận hành
```

Cần tính cả datasource read/write, batch worker, migration, admin client, background job và các ứng dụng dùng cùng database. Việc ứng dụng không sử dụng hết connections tại một thời điểm **không** phải lý do để bỏ qua khả năng cùng tăng tải lúc peak.

### 4.2. Không lấy số task bằng số connection một cách máy móc

Nếu một task luôn mượn tối đa **một** connection và không có luồng nào khác truy cập database, executor giới hạn 6 task có thể là một biện pháp kiểm soát số demand. Trong hệ thống thật thường có các luồng HTTP trực tiếp, scheduler, listener và executor khác cùng dùng pool; chúng không bị giới hạn bởi pool executor đó.

Ngoài ra, một tác vụ có thể song song chạy hai query qua hai transaction khác nhau, hoặc giữ connection trong transaction trong khi chờ việc khác. Vì vậy không thể áp công thức chung `maxThreads = maximumPoolSize`.

**Nguyên tắc:** xem connection pool là hàng rào vật lý cuối cùng, còn concurrency limit/bulkhead ở **đúng điểm sinh tải** là lớp kiểm soát phía trước. Dành công suất cho đường xử lý quan trọng; không để batch/background chiếm hết pool khiến request tương tác không còn connection.

## 5. Giới hạn việc nền Spring để dành tài nguyên DB cho request chính

Giả sử pool JDBC có tối đa 12 connection. Ta chỉ cho nhóm tác vụ xuất báo cáo nền sử dụng **tối đa 4 worker cùng lúc**, để các request tương tác còn có cơ hội lấy connection. Đây là giới hạn cho **một nhóm tác vụ**, không phải bảo đảm cứng luôn còn đúng 8 connection vì các luồng khác vẫn có thể chiếm pool.

**Cấu hình Spring Framework/Spring Boot trong ứng dụng có bật async:**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncResourceConfiguration {
    @Bean("reportDbExecutor")
    public ThreadPoolTaskExecutor reportDbExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("report-db-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring quản lý initialize/shutdown theo lifecycle.
    }
}
```

**Sử dụng ở một Spring-managed service:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportCountService {
    private final JdbcTemplate jdbc;

    public ReportCountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Async("reportDbExecutor")
    public CompletableFuture<Long> countOrders() {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Long.class);
        return CompletableFuture.completedFuture(count);
    }
}
```

Đây là hai class tích hợp vào **dự án Spring Boot/Spring Framework đã có datasource, bảng `orders` và dependencies JDBC**, không phải chương trình `javac` độc lập. Với executor này, tối đa bốn task **đang chạy trong nhóm báo cáo** tại một thời điểm; tối đa 16 task nữa có thể đợi trong queue. Khi cả worker và queue đều đầy, chính sách `AbortPolicy` làm submission bị từ chối. Cần xử lý lỗi từ chối tại biên gọi, ví dụ trả phản hồi quá tải hoặc đưa việc vào job store thích hợp.

**Ranh giới quan trọng:**

- `@Async("reportDbExecutor")` chỉ sử dụng executor này khi phương thức được gọi **qua Spring proxy**. Lời gọi nội bộ `this.countOrders()` trong cùng bean thường bỏ qua proxy.
- Bốn task đang chạy không đồng nghĩa chính xác bốn connection đang mượn ở mọi thời điểm: có thể đang tính toán, chờ connection hoặc không dùng DB.
- Các API request thông thường dùng DB trực tiếp không tự đi qua executor `reportDbExecutor`.
- Dữ liệu nghiệp vụ cần transaction phải mở transaction ở **thread làm việc thực sự**. Gọi `@Async` không tự mang transaction imperative của caller sang worker khác.
- `queueCapacity=16` là số chỗ chờ trong executor; nó **không** tăng connection. Queue lớn làm thời gian chờ tăng; đo queue delay để đặt giới hạn.
- Nếu muốn ưu tiên request tương tác khi nghẽn, chỉ giới hạn background worker có thể chưa đủ: vẫn cần đánh giá DB total capacity, query cost và admission control ở các đường khác.

### Khi dùng `SimpleAsyncTaskExecutor` hay virtual threads

`SimpleAsyncTaskExecutor` không tái sử dụng thread, và `setConcurrencyLimit(n)` giới hạn số task đang thực thi qua nó; theo mặc định caller có thể bị chặn khi hết suất. Với Java 21+ và Spring hỗ trợ virtual threads, tạo nhiều virtual thread rẻ hơn platform threads nhưng **không** làm tăng số connection mà HikariCP hoặc downstream cấp được. Vì vậy giới hạn đồng thời tại dependency vẫn cần thiết.

## 6. Giới hạn với dịch vụ đích: connection pool chưa đủ

Đối với dịch vụ HTTP ngoài, có ít nhất ba thứ cần quản lý:

1. **Số kết nối mạng** client có thể mở tới đích.
2. **Số request/operation đang được xử lý** đồng thời tại dịch vụ đích.
3. **Tốc độ request theo thời gian** (requests/giây hoặc requests/phút) mà đối tác cho phép.

Ba đơn vị này thường không bằng nhau. Với HTTP/1.1, request đang sử dụng kết nối thường giữ một connection trong thời gian đó, nhưng còn các chi tiết keep-alive, pooling và proxy. Với **HTTP/2**, nhiều stream/request có thể dùng **cùng một TCP connection**; vì vậy giới hạn 10 connections không có nghĩa chỉ có 10 request đồng thời. Tính năng multiplexing và giới hạn concurrent streams phụ thuộc protocol/implementation.

**Nếu hợp đồng đối tác nói “tối đa 20 request in-flight”**, cần cơ chế admission/bulkhead giới hạn **operation**, không chỉ HTTP connection pool. Nếu hợp đồng nói **100 requests/giây**, cần thêm rate limiter. Nếu đối tác báo 429 hoặc Retry-After, cần chiến lược retry/backoff phù hợp và không gửi dồn cùng lúc.

### Tại sao phải đặt giới hạn theo từng dependency?

Ví dụ service A gọi đồng thời:

- Inventory API: tối đa 10 cuộc gọi in-flight.
- Payment API: tối đa 4 cuộc gọi in-flight.
- Shipping API: tối đa 20 cuộc gọi in-flight.

Đặt chung executor 40 worker **không bảo đảm** từng API được giữ dưới ngưỡng riêng của nó; request có thể cùng chọn Payment và vượt 4. Thiết kế tốt thường có **bulkhead riêng cho Payment, Inventory, Shipping** hoặc pool/bộ điều tiết riêng ở tầng client.

**Bulkhead** là cơ chế cách ly lượng công việc đang hoạt động của từng dependency, giúp một dịch vụ chậm không chiếm toàn bộ tài nguyên của các dịch vụ khác. Nó không thay thế timeout, circuit breaker, rate limiter hay retry budget.

## 7. Ví dụ Java 17 độc lập: giới hạn hai cuộc gọi bằng Semaphore

`java.util.concurrent.Semaphore` là công cụ hữu ích để hiểu cơ chế cấp **permit**: mỗi cuộc gọi muốn đi vào phần bảo vệ phải lấy một permit, và phải trả permit trong `finally`. Ví dụ sau mô phỏng dependency chỉ chịu **hai** operation đồng thời và làm kết quả xác định bằng `CountDownLatch`.

Tạo tệp **`DependencyPermitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class DependencyPermitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch releaseWorkers = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxInFlight = new AtomicInteger();

        Runnable remoteCall = () -> {
            if (!permits.tryAcquire()) {
                throw new IllegalStateException("No capacity for worker");
            }

            try {
                int current = inFlight.incrementAndGet();
                maxInFlight.accumulateAndGet(current, Math::max);
                started.countDown();

                try {
                    // Giữ cả hai permit để kiểm tra tình huống đã đầy.
                    releaseWorkers.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                inFlight.decrementAndGet();
                permits.release();
            }
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(remoteCall);
            Future<?> second = pool.submit(remoteCall);

            try {
                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Workers did not start");
                }

                System.out.println("maxInFlight=" + maxInFlight.get());

                boolean thirdAccepted = permits.tryAcquire();
                if (thirdAccepted) {
                    permits.release();
                }
                System.out.println("thirdAccepted=" + thirdAccepted);
            } finally {
                releaseWorkers.countDown();
            }

            // Future.get() xác nhận hai tác vụ hoàn tất hoặc báo lỗi.
            first.get();
            second.get();

            System.out.println("availableAfter=" + permits.availablePermits());
        } finally {
            releaseWorkers.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac DependencyPermitDemo.java
java DependencyPermitDemo
```

**Standard output dự kiến của chương trình:**

```text
maxInFlight=2
thirdAccepted=false
availableAfter=2
```

**Giải thích:**

- Hai task đã lấy hai permit, tăng số operation đang thực thi và cùng chờ latch. Lời gọi thứ ba từ main có `tryAcquire() == false` vì không còn permit.
- Main mở latch trong `finally`; hai task hoàn thành, trả permit dù một task bị interrupt hoặc lỗi trong vùng bảo vệ.
- Sau `Future.get()` cho cả hai, `availablePermits() == 2`. Như vậy không có permit bị thất lạc trong đường đi bình thường của ví dụ.
- Kết quả dùng latch nên không phụ thuộc vào thứ tự worker được hệ điều hành lên lịch. Đây là mô phỏng **giới hạn operation trong một JVM**, không phải chương trình thực sự gọi database/HTTP.

### Đưa nguyên tắc này vào ứng dụng

Ví dụ method-body snippet cho một **HTTP client blocking**, nơi mọi đường gọi cùng dependency đều qua một gateway có chung semaphore:

```java
private final Semaphore targetSlots = new Semaphore(6);

public TargetResult callTarget(Request request) {
    if (!targetSlots.tryAcquire()) {
        throw new TargetBusyException("Target concurrency limit reached");
    }
    try {
        return blockingHttpClient.call(request);
    } finally {
        targetSlots.release();
    }
}
```

Đoạn trên **chỉ minh họa logic**; `TargetResult`, `Request`, `TargetBusyException` và `blockingHttpClient` là kiểu/biến nghiệp vụ phải định nghĩa khi tích hợp. Tác vụ phải có timeout I/O và xử lý ngoại lệ từ client. Dùng `tryAcquire()` là **fail-fast**; nếu muốn chờ có hạn, có thể dùng `tryAcquire(timeout, unit)` trên thread chặn phù hợp, đồng thời đưa thời gian chờ đó vào end-to-end deadline.

**Ranh giới:** nếu gọi API reactive trả `Mono`/`Flux`, **không được** viết `try { return webClient...bodyToMono(...); } finally { slots.release(); }`; `finally` chạy ngay khi trả publisher, trước khi request async thật hoàn tất. Phải giữ permit cho đến tín hiệu terminal/cancel (ví dụ reactive operator `doFinally`), dùng bulkhead reactive tương thích, và đặc biệt xử lý trường hợp subscription/hủy đúng cách. Không chặn event loop bằng semaphore blocking wait.

Trong môi trường Spring, thư viện như **Resilience4j Bulkhead** cung cấp semaphore bulkhead có `maxConcurrentCalls` và `maxWaitDuration`, phù hợp khi cần tách giới hạn theo từng downstream. Với reactive code, chọn operator tích hợp đúng để permit bao phủ **thời gian thực thi**, không chỉ thời gian dựng publisher.

## 8. HTTP connection pool với WebClient/Reactor Netty

Khi dùng `WebClient` với Reactor Netty, có thể đặt cấu hình connection pool cho một HTTP client riêng. Ví dụ trong ứng dụng Spring WebFlux/WebClient có Reactor Netty:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class TargetClientConfiguration {
    @Bean(destroyMethod = "dispose")
    public ConnectionProvider targetConnectionProvider() {
        return ConnectionProvider.builder("target-api-pool")
                .maxConnections(16)
                .pendingAcquireMaxCount(24)
                .pendingAcquireTimeout(Duration.ofMillis(700))
                .build();
    }

    @Bean
    public WebClient targetWebClient(ConnectionProvider targetConnectionProvider) {
        HttpClient httpClient = HttpClient.create(targetConnectionProvider)
                .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
                .baseUrl("https://api.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Đây là ví dụ **tích hợp**, không chạy độc lập nếu thiếu các dependency `spring-webflux` và `reactor-netty-http`, cũng như endpoint thật. Mục đích của từng cấu hình:

- `maxConnections(16)`: trần connection trong mỗi pool của provider (thường tách theo remote host/port), **không phải** trần số HTTP operation hay requests/giây.
- `pendingAcquireMaxCount(24)`: giới hạn số yêu cầu mượn connection có thể **đợi** khi pool đầy. Hàng đợi pending không nên đặt vô hạn.
- `pendingAcquireTimeout(700 ms)`: thời gian đợi lấy connection. Hết hạn này là lỗi acquire, **không nhất thiết** là downstream response timeout.
- `responseTimeout(3 s)`: giới hạn thời gian response theo cơ chế Reactor Netty; không thay thế connect timeout, DNS deadline hoặc end-to-end API deadline ở mọi đường lỗi.
- `@Bean(destroyMethod = "dispose")`: yêu cầu giải phóng provider khi application context đóng.

**Điểm cần nhớ với HTTP/2:** có thể có nhiều stream trên một kết nối, và quản lý pool/stream tùy phiên bản Reactor Netty. Nếu mục tiêu là “không quá N operation đang chạy đến inventory API”, thêm semaphore/bulkhead theo request ở lớp gọi API vẫn thường rõ nghĩa hơn.

Nhiều client khác như Apache HttpClient, JDK `HttpClient`, Feign hoặc client gRPC có cơ chế quản lý connection riêng. Không sao chép cấu hình Reactor Netty sang các client đó. Hãy kiểm tra implementation được Spring Boot hoặc project thực sự sử dụng, rồi áp các thuộc tính tương ứng.

## 9. Đồng thời, tốc độ và timeout: ba chính sách phải phối hợp

### 9.1. Concurrency limit khác rate limit

- **Concurrency limit:** tối đa **N operation đang xử lý đồng thời**. Một operation 100 ms và một operation 10 giây giữ permit trong các khoảng khác nhau.
- **Rate limit:** tối đa **R requests trên một khoảng thời gian**, ví dụ 60 requests/giây; không tự giới hạn tổng số đang chờ response nếu từng request rất chậm.
- **Connection limit:** số connection của client/server; với HTTP/2, nó không tương đương số request.

Theo Little's Law, trong hệ thống ổn định và cùng đơn vị đo, số công việc trung bình đang trong hệ thống xấp xỉ `L = λ × W` (tốc độ hoàn thành × thời gian ở trong hệ thống). Ví dụ nhận 50 request/giây với thời gian phục vụ 0,4 giây tạo ra khoảng 20 request đang thực thi trung bình, **không phải cam kết p99 hoặc peak**. Độ trễ tăng lên 2 giây mà tốc độ đến giữ nguyên thì nhu cầu in-flight có thể tăng mạnh, khiến queue tích tụ.

Do đó hãy xem giới hạn như một **tài nguyên ngân sách** gắn với lưu lượng, service time, timeout, số instance và đặc điểm phân phối độ trễ. Không tự động nâng concurrency khi thấy queue dài: nếu target đã bão hòa, tăng concurrent calls thường chỉ tăng lỗi và timeout.

### 9.2. Tránh cộng dồn các thời gian chờ

Một request có thể mất thời gian tại nhiều tầng:

```text
Executor queue
    + Hikari connectionTimeout wait
    + DB execution / lock wait
    + HTTP connection pending acquire
    + HTTP connect / response wait
    + retry backoff
    = end-to-end latency (có thể vượt deadline client)
```

Đặt từng timeout 10 giây nhưng HTTP client chỉ cho người dùng chờ 5 giây là không hợp lý nếu các tầng nối tiếp nhau. Ưu tiên xác định **deadline tổng**, phân bổ ngân sách cho từng bước, hủy/từ chối khi quá hạn, và không giữ DB transaction/connection trong khi chờ dịch vụ ngoài lâu hơn cần thiết.

**Hikari `connectionTimeout`** chỉ kiểm soát thời gian mượn connection, không ngắt SQL đang chạy. Đặt query timeout/transaction timeout phù hợp với driver/database; với HTTP client có connection timeout, response timeout và tổng request deadline; phân biệt từng loại để đọc metric đúng.

### 9.3. Retry có thể làm tải đích nặng thêm

Khi DB hay service đích đã đầy, retry tức thời từ hàng trăm request đồng loạt có thể gây **retry storm**: càng chậm càng retry, càng retry càng cạn connection. Retry cần có điều kiện (chỉ lỗi phù hợp), giới hạn số lần, backoff với jitter, tổng deadline và idempotency.

Nếu API bên ngoài yêu cầu rate limit hoặc trả `429 Too Many Requests` kèm `Retry-After`, hãy xử lý theo hợp đồng thay vì chỉ tăng số connection. Với những thao tác có side effect như thanh toán, retry phải gắn với idempotency key/transaction design để không thực hiện trùng.

## 10. Giới hạn cục bộ và giới hạn toàn hệ thống

Giả sử có 5 pod, mỗi pod dùng semaphore 6 permit cho Payment. **Tổng hệ thống có thể có 30 Payment calls đồng thời** nếu mọi pod cùng dùng hết 6 suất. Nếu đối tác chỉ cho phép 10 call in-flight tính trên toàn khách hàng, một semaphore cục bộ mỗi JVM không đủ.

Các hướng xử lý:

| Nhu cầu | Cơ chế thường phù hợp | Điều phải kiểm chứng |
| --- | --- | --- |
| Cần giới hạn thread/task trong một JVM | Executor pool có cấu hình rõ | Tất cả nguồn sinh tải có đi qua executor đó không? |
| Cần giới hạn DB connection mỗi instance | HikariCP `maximumPoolSize` | Tổng trên mọi datasource, pod và workload khác |
| Cần giới hạn operation tới một downstream trong một JVM | Semaphore/Resilience4j bulkhead | Mọi đường gọi có chia sẻ cùng permit không? |
| Cần giới hạn tốc độ chung nhiều pod | Gateway/distributed rate limiter | Đồng hồ, quota, retry, failure mode |
| Cần giới hạn concurrency toàn cluster | Admission control/queue đồng bộ có ownership hoặc service gateway | Lease, fairness, xử lý crash và thu hồi permit |
| Cần công việc bền vững và retry sau restart | Message broker/job queue + bounded consumer | Idempotency, dead-letter, backlog, ordering |

Một giải pháp distributed semaphore/lock cần tính đến tình huống pod crash giữa lúc đang giữ suất: TTL/lease, fencing hoặc xác định khi nào có thể thu hồi permit. Đối với DB, nhiều khi sử dụng **transaction + constraint + atomic update** đúng điều kiện nghiệp vụ sẽ an toàn và đơn giản hơn so với khóa phân tán tự xây.

**Không dùng giới hạn connection làm thay thế kiểm soát dữ liệu.** Một database có 10 connection vẫn có thể gặp lost update, overselling hoặc duplicate insert nếu transaction/constraint không đúng.

## 11. Quan sát và kiểm thử trước khi tối ưu

### 11.1. Những metric cần theo dõi

**Với HikariCP** (khi ứng dụng có Micrometer/Actuator và metric được bật):

- `hikaricp.connections.active`: connection đang được mượn.
- `hikaricp.connections.idle`: connection nhàn rỗi.
- `hikaricp.connections.pending`: caller đang chờ mượn connection.
- `hikaricp.connections.max`: giới hạn connection của pool.
- Timeout khi mượn connection, query latency, slow queries, DB CPU/IOPS, lock waits và transaction duration.

**Với executor:** active threads, pool size, queue size, task reject count, task execution time và thời gian nằm trong queue. Chú ý rằng `maxPoolSize` không bảo đảm executor sẽ nhanh chóng tăng worker tới max nếu hàng đợi còn chỗ.

**Với HTTP/target API:** active/idle/pending connections, pending acquire duration, request in-flight, latency p50/p95/p99, timeout, 429/503/5xx, retry count, quota remaining. Reactor Netty cung cấp metrics cho `reactor.netty.connection.provider.*` khi bật cấu hình phù hợp.

Phải xem **nhiều biểu đồ cùng lúc**: Hikari active=12/12 + pending cao có thể cho biết pool đang đầy, nhưng nếu DB CPU rất thấp và transaction dài do chờ HTTP, giải pháp có thể là giảm thời gian giữ connection, không phải tăng pool.

### 11.2. Bài thử tải có mục tiêu

1. **Chạy tải thấp** để lấy baseline throughput, latency, DB active/idle và downstream response time.
2. **Tăng đồng thời từ từ**, giữ nguyên số pod và workload, xác định điểm throughput ngừng tăng trong khi p95/p99 hoặc pending tăng.
3. **Làm chậm dependency có kiểm soát** (test environment): DB query mất lâu hơn hoặc mock API trễ thêm; xem số task chờ và timeout ở từng tầng.
4. **Đẩy quá hạn mức đã cấu hình**: xác nhận request bị reject/chờ đúng kỳ vọng, queue không tăng vô hạn và các đường nghiệp vụ khác còn khả năng phục vụ.
5. **Thử autoscaling/đa instance**: quan sát tổng DB connections, tổng downstream in-flight và quota khi số pod tăng.
6. **Thử retry và lỗi**: timeout, 429, 503, connection reset, request cancel, shutdown; bảo đảm permit/connection được trả lại, không leak.
7. **Điều chỉnh từng tham số**, rồi đo lại; tránh đồng thời tăng pool, queue, số thread và retry khiến không biết thay đổi nào có tác dụng.

Cần tránh một kiểu test sai: chạy 100 task nhưng không đợi kết quả rồi lập tức đọc metric, kết luận hệ thống không quá tải. Đảm bảo tất cả task đã được submit/counted, có timeout của test, và kiểm tra số task thực thi tối đa, số task bị từ chối, backlog và số task hoàn thành.

## 12. Những lỗi thiết kế thường gặp

### 12.1. “Executor có 50 thread thì Hikari cũng cần 50 connections”

Không nhất thiết. Một task có thể không truy cập DB; ngược lại, luồng HTTP khác cũng dùng DB. Số connection cần dựa trên **mức sử dụng tài nguyên thật** và công suất DB. Với CPU/IOPS yếu, pool lớn thường làm tăng tranh chấp, không tăng throughput.

### 12.2. “Pool 10 connections nghĩa là tối đa 10 request mỗi giây”

Sai: connection có thể xử lý nhiều request nối tiếp; tốc độ còn phụ thuộc query time, transaction length và mức độ sử dụng connection. Đừng trộn **in-flight** với **throughput**.

### 12.3. “Đã giới hạn HTTP connections nên không thể vượt quota API”

Sai với HTTP/2 multiplexing, nhiều request trên một connection hoặc nhiều client/pod. Nếu quota là operation in-flight hay requests/giây, dùng bulkhead/rate limiter đúng nghĩa và tính toàn hệ thống.

### 12.4. “Tăng connectionTimeout sẽ giải quyết pool cạn”

Nó chỉ cho phép caller **chờ lâu hơn** trước khi lỗi; nếu công suất không tăng, queue và latency có thể lớn hơn. Ưu tiên tìm nguyên nhân transaction dài, connection leak, DB lock, slow query và tải vượt năng lực.

### 12.5. “Có @Async thì không giữ request thread”

Một request thread có thể được giải phóng ở phần xử lý phù hợp, nhưng một executor khác vẫn có thể bị kẹt chờ connection; submission cũng có thể bị chặn hoặc từ chối khi pool/queue đầy. Không suy ra hệ thống non-blocking chỉ từ `@Async`.

### 12.6. “Semaphore.tryAcquire() bao quanh việc tạo Mono là đủ”

Sai: với reactive pipeline, tạo `Mono` chỉ mô tả công việc; phép gọi mạng thực tế thường xảy ra lúc subscribe và kết thúc sau đó. Permit phải bao trọn thời gian thực thi, kể cả error/cancel. Dùng operator reactive/bulkhead hỗ trợ lifecycle của publisher.

### 12.7. “Hạn mức 20 per pod bảo đảm tổng không quá 20”

Sai khi chạy nhiều pod. Hãy tính tổng theo số instance cực đại hoặc sử dụng điểm điều phối giới hạn chung.

### 12.8. “Retry nhanh sẽ giúp thoát lỗi quá tải”

Sai khi cùng một dependency đang nghẽn: các đợt retry dồn có thể kéo dài nghẽn và ảnh hưởng request lành. Cần backoff, jitter, tổng retry budget, circuit breaker và idempotency.

### 12.9. “Giữ transaction mở khi gọi remote API không ảnh hưởng pool”

Trong nhiều đường JDBC transaction, connection có thể bị giữ đến khi transaction kết thúc; remote call chậm kéo dài thời gian giữ connection và tăng pending acquisition. Thiết kế lại ranh giới transaction và dùng outbox nếu cần consistency giữa DB và event ngoài.

### 12.10. “Một số cấu hình đẹp là đủ, không cần metric”

Không thể chọn công suất chỉ từ số CPU hoặc lời khuyên chung. Đo dưới tải và lỗi thực tế, kiểm tra cả saturations, p95/p99 và tổng số kết nối qua mọi instance.

## 13. Quy trình lựa chọn cấu hình và tài liệu đối chiếu

Một quy trình thực tế để quyết định concurrency theo DB hoặc dịch vụ đích:

1. **Xác nhận điểm nghẽn:** DB connections, query CPU/locks, HTTP sockets, downstream in-flight quota hay rate quota? Mỗi thứ đòi hỏi cơ chế khác.
2. **Xác định phạm vi:** mỗi task, mỗi executor, mỗi datasource, mỗi remote host, mỗi pod hay toàn cluster. Đếm mọi nguồn tải và số instance cực đại.
3. **Lập ngân sách:** dự phòng cho request ưu tiên và hệ thống khác; chọn concurrency và queue ban đầu theo công suất, không chạy hết trần vật lý.
4. **Giới hạn tại đúng điểm sinh tải:** Hikari pool cho connection; executor cho task nền; semaphore/bulkhead cho operation; rate limiter cho requests/giây; connector pool cho socket.
5. **Quy định hành vi khi đầy:** đợi bao lâu, từ chối như thế nào, thông báo API ra sao, retry ra sao, có cần lưu job bền vững không?
6. **Kiểm soát vòng đời tài nguyên:** đóng connection/permit đúng chỗ, timeout, cancellation, transaction scope, shutdown và handling cho crash/retry.
7. **Kiểm thử có tải và sự cố:** cả khi chạy một instance và nhiều instance, đối chiếu throughput/latency/queue/saturation trước khi thay đổi cấu hình.

### Tài liệu tham khảo

- [Spring Boot 3.5 – SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasource auto-configuration và các loại connection pool.
- [HikariCP – README và cấu hình pool](https://github.com/brettwooldridge/HikariCP): ý nghĩa `maximumPoolSize` và `connectionTimeout`.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `@Async`, thread pool và queue/rejection behavior.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection provider, max connections, pending acquire và metrics.
- [Resilience4j – Bulkhead](https://github.com/resilience4j/resilience4j#73-bulkhead): cách cô lập số concurrent calls theo dependency.
- [Java SE 17 – Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): permit, `tryAcquire` và `release`.

**Ghi nhớ:** số thread chỉ cho biết năng lực điều phối task; **số connection và năng lực của DB/remote service mới giới hạn phần việc có thể thực hiện đồng thời**. Cấu hình đúng phải bảo vệ từng tài nguyên ở phạm vi phù hợp, quy định rõ chờ/từ chối khi đầy và được kiểm chứng bằng metric cùng thử tải.
