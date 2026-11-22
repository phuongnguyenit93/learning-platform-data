# Giới hạn của luồng ảo với CPU, kết nối cơ sở dữ liệu và tác vụ ghim luồng

**Phạm vi:** Java 21+ (virtual threads được chuẩn hóa ở JDK 21 theo JEP 444), Spring Boot trên JVM, trọng tâm Spring MVC/Servlet và các công việc dùng JDBC. Cần phân biệt **JDK 21–23** với **JDK 24+** vì JDK 24 đã thay đổi quan trọng về pinning trong mã `synchronized`. Ví dụ Java độc lập yêu cầu JDK 21+; cấu hình Spring Boot minh họa dùng Spring Boot 3.5.x.

**Điều quan trọng nhất:** Virtual thread giúp một ứng dụng giữ được nhiều **tác vụ đang chờ I/O** với ít platform thread hơn. Nó không làm CPU tính nhanh hơn, không tự tăng số connection của database, không khiến transaction ngắn hơn, và không đảm bảo mọi loại blocking đều giải phóng carrier thread.

## 1. Cơ chế: virtual thread chạy trên carrier thread như thế nào?

Một **platform thread** thường gắn gần với một OS thread. **Virtual thread** vẫn là `java.lang.Thread`, nhưng JVM lên lịch chạy rất nhiều virtual thread trên một số lượng platform thread gọi là **carrier threads**.

- Khi virtual thread **đang thực thi Java trên CPU**, nó phải được gắn (**mounted**) vào một carrier. Một carrier không thể thực hiện đồng thời hai luồng tính toán trên một lõi tại cùng một thời điểm.
- Khi virtual thread thực hiện nhiều thao tác **blocking I/O tương thích** như chờ socket, JDBC I/O hoặc `Thread.sleep`, JVM có thể **unmount** virtual thread và trả carrier về scheduler để chạy việc khác. Khi có kết quả, virtual thread được đưa vào lịch chạy trở lại.
- Một tác vụ có thể đã được tạo nhưng vẫn **đợi carrier**, **đợi connection**, **đợi khóa**, **đợi I/O** hoặc **đợi hệ thống khác**. Số virtual thread lớn không đồng nghĩa số thao tác tiến hành đồng thời trên mọi tài nguyên đều lớn.
- Khi virtual thread bị **pinned** trong lúc block, nó không thể unmount như trường hợp bình thường, nên carrier bị giữ trong khoảng đợi đó. Pinning lặp lại và kéo dài có thể làm throughput sụt giảm.

~~~text
HTTP requests (nhiều)
   │
   ├── Virtual thread A ── tính toán CPU ───────► carrier #1 đang bận
   ├── Virtual thread B ── chờ socket ─────────► unmount; carrier được tái sử dụng
   ├── Virtual thread C ── chờ connection DB ──► virtual thread còn tồn tại, DB pool vẫn có giới hạn
   └── Virtual thread D ── block khi bị pinned ► carrier có thể bị giữ
                                        │
                                        ▼
                           CPU / DB / external services
                           vẫn là các tài nguyên hữu hạn
~~~

Cách dùng phổ biến là **một virtual thread cho một tác vụ** với lập trình đồng bộ dễ đọc: `Executors.newVirtualThreadPerTaskExecutor()`. Không tạo thread pool cố định để tái sử dụng virtual threads; nếu cần giới hạn số việc vào một tài nguyên, dùng **connection pool, semaphore, bulkhead hoặc hàng đợi có kiểm soát**.

### Throughput, latency, concurrency không giống nhau

- **Latency:** thời gian một request đi từ bắt đầu đến kết thúc. Virtual thread thường **không rút ngắn** thời gian một query SQL thực thi trong DB hoặc một thuật toán xử lý CPU.
- **Throughput:** lượng request hoàn tất trên một đơn vị thời gian. Nếu trước đây platform threads bị chiếm khi chờ I/O, virtual threads **có thể** cải thiện throughput bằng cách cho phép thêm request cùng tiến triển.
- **Concurrency:** số tác vụ còn đang hoạt động/chờ trong hệ thống. Concurrency tăng quá khả năng DB, CPU hay dịch vụ bên ngoài sẽ biến thành hàng chờ dài và timeout.

Một cách đọc gần đúng từ **Little's law** khi hệ thống ổn định là `L = λ × W`, với `L` là số request trong hệ thống, `λ` là throughput và `W` là thời gian lưu lại trong hệ thống. Nếu throughput không tăng nhưng thời gian chờ tăng, concurrency tăng chỉ phản ánh **backlog**, không có nghĩa hiệu năng tốt hơn.

## 2. Giới hạn thứ nhất: công việc dùng CPU

### Vì sao thêm virtual thread không tạo ra thêm sức mạnh CPU?

Tính toán nặng như mã hóa, nén, xử lý ảnh, parse dữ liệu rất lớn, thuật toán số hoặc vòng lặp nóng liên tục cần **thời gian CPU thực**. Một virtual thread đang chạy tính toán vẫn chiếm carrier trong thời gian đó. Scheduler có thể thay phiên tác vụ, nhưng không tạo thêm lõi CPU.

Giả sử máy có 4 core CPU hiệu dụng và 1.000 request, mỗi request cần đúng **50 ms CPU** (không chờ I/O). Tổng nhu cầu là `1.000 × 50 ms = 50 s CPU`. Cận dưới lý tưởng cho toàn bộ lô là `50/4 = 12,5 s`, chưa tính overhead, GC, tranh chấp và chi phí khác. Tạo 1.000 virtual thread **không** biến lô đó thành 50 ms.

| Tải công việc | Điều virtual thread cải thiện được | Giới hạn vẫn còn |
| --- | --- | --- |
| Chờ HTTP/JDBC/network nhiều | Giảm việc giữ OS thread khi chờ; có thể tăng số request đang chờ | Băng thông, latency mạng, tốc độ DB và giới hạn kết nối |
| Parse, nén, hash, mã hóa nặng | Code đồng bộ thuận tiện, thread tạo tương đối nhẹ | Số lõi, quota CPU container, GC và RAM |
| Hỗn hợp CPU + I/O | Tận dụng thời gian carrier rảnh khi chờ I/O | Pha CPU vẫn giới hạn throughput khi CPU bão hòa |
| Batch đồng thời rất lớn | Tạo tác vụ dễ hơn so với một platform thread mỗi task | Kích thước queue, heap, file descriptor, bộ nhớ của task và downstream |

**Dấu hiệu nghẽn CPU:** CPU gần quota thực tế, tăng concurrency nhưng throughput không tăng, p95/p99 latency xấu đi, thời gian GC/CPU cao. Trên Kubernetes, nhìn cả **CPU throttling** và `cpu limits`; `availableProcessors()` chỉ giúp hiểu môi trường JVM, không thay thế profiling.

**Ứng xử phù hợp:** tối ưu thuật toán và query; giảm công việc CPU trên request path; giới hạn số công việc tính toán tốn kém theo core/quota; đưa batch nặng sang job/worker phù hợp nếu cần; benchmark throughput ở cùng cấu hình và cùng tải. Không dùng `Thread.sleep` để mô phỏng công việc CPU — sleep là **đợi**, đặc tính khác hoàn toàn.

### Scheduler parallelism có phải nút tăng hiệu năng CPU?

JVM có scheduler để đưa virtual threads lên carriers; parallelism mặc định thường gắn với số processor khả dụng. Có thuộc tính JVM chuyên dụng như `jdk.virtualThreadScheduler.parallelism` để điều chỉnh scheduler trong những tình huống cần đo đạc. **Tăng parallelism không tạo thêm CPU** và không phải cách sửa mặc định cho ứng dụng bị CPU-bound. Nó có thể làm contention và context switching nhiều hơn. Chỉ thay đổi sau khi xác định bottleneck và so sánh bằng tải thực tế.

## 3. Giới hạn thứ hai: connection pool và sức chịu tải của cơ sở dữ liệu

### Virtual thread nhiều không có nghĩa JDBC connection nhiều

Một connection JDBC là tài nguyên liên quan tới server DB, socket, trạng thái phiên và transaction. Trong Spring Boot dùng JDBC/JPA, thường có **DataSource connection pool**, phổ biến là HikariCP. Pool cho phép **tối đa một số connection**, bất kể số virtual thread mà server có thể tạo.

Ví dụ có 500 HTTP requests đồng thời, mỗi request dùng JDBC và HikariCP cho phép 10 connections:
1. Tối đa **10 connection của pool** có thể được checkout đồng thời (giả sử mỗi request cần một connection).
2. Các request còn lại phải **đợi** lấy connection; virtual threads của chúng vẫn tồn tại nhưng không sinh ra thêm DB connection.
3. Khi một request đóng/trả connection cho pool, request khác mới được dùng.
4. Nếu chờ vượt `connectionTimeout`, HikariCP có thể ném exception không lấy được connection; tùy xử lý của ứng dụng, request có thể thất bại với 5xx hoặc mã lỗi được ánh xạ riêng.

**Con số minh họa:** nếu giữ connection trung bình 100 ms, pool tối đa 10 connection cho mức trần rất thô `10/0,1 = 100 lượt dùng connection/giây` **nếu** connection được sử dụng liên tục và thời gian giữ luôn là 100 ms. Đây không phải phép dự báo QPS chính xác: truy vấn DB có thể chậm khi số lượng truy vấn tăng, transaction có nhiều query, lock và bottleneck khác. Một request còn có thể checkout connection nhiều lần.

~~~text
          Spring MVC / virtual threads
              500 requests active
                       │
                       ▼
                HikariCP pool
                maximumPoolSize=10
                    │    │
                 10 connections ─────► Database
                    │                    CPU, I/O, locks,
             Request còn lại            limits, query plans
             đợi connection
             (không tự có thêm
              490 connections)
~~~

Connection pool **tự nó đã là cơ chế giới hạn** số JDBC connection. Không cần đặt thêm một `Semaphore(10)` ngay trước mỗi lần `getConnection()` chỉ để lặp lại đúng giới hạn 10 của pool; semaphore riêng chỉ có ý nghĩa nếu muốn đặt **giới hạn nghiệp vụ khác** (ví dụ giới hạn đồng thời một truy vấn cực đắt hoặc nhiều hệ thống cùng dùng DB).

### Cấu hình Spring Boot/HikariCP minh họa

Khi ứng dụng đã có JDBC datasource và sử dụng HikariCP, có thể đặt trong `src/main/resources/application.properties`:

~~~properties
# Tùy chọn cho Spring Boot 3.2+ chạy Java 21+
spring.threads.virtual.enabled=true

# Hữu ích nếu ứng dụng phụ thuộc vào các virtual daemon threads / scheduled tasks
spring.main.keep-alive=true

# Cấu hình ví dụ, cần điều chỉnh theo tải và giới hạn DB thực tế
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=2000
~~~

- `maximum-pool-size=10`: tối đa 10 connections của một Hikari pool cho một instance; giá trị 10 ở đây là **chọn làm ví dụ**, không phải tiêu chuẩn cho mọi dịch vụ.
- `connection-timeout=2000`: chờ lấy connection tối đa **2.000 ms**, sau đó thất bại nếu vẫn không có. Đây **không** phải timeout cho toàn bộ SQL query hay HTTP request.
- Các property này có tác dụng khi ứng dụng có JDBC datasource/Hikari thực sự, không tạo database hoặc kết nối mới chỉ bằng việc bật virtual threads.
- Nếu triển khai **3 replicas**, mỗi replica pool tối đa 10 thì riêng nhóm service này có thể đồng thời dùng đến **30 connections**; còn phải dành ngân sách cho ứng dụng khác, admin, migrations và giới hạn DB.
- Mặc định HikariCP của bản phát hành cụ thể có thể thay đổi theo cách cấu hình; luôn kiểm tra effective configuration và Actuator/JMX khi tuning.

**Đừng tăng `maximum-pool-size` chỉ vì tăng số virtual thread.** DB vẫn có CPU, IOPS, buffer cache, lock, `max_connections`, transaction throughput và network hữu hạn. Pool quá lớn có thể khiến DB tranh chấp tài nguyên và làm p99 tệ hơn. Chọn pool bằng đo đạc active/pending/idle, thời gian chờ connection, query latency, throughput DB, CPU DB, lock wait và tổng số kết nối trên tất cả replicas.

### Giữ connection/transaction càng lâu càng dễ nghẽn

Nếu một `@Transactional` method truy vấn DB rồi gọi API bên ngoài chậm trong khi connection vẫn đang được giữ, connection bị chiếm suốt thời gian đợi API, ngay cả khi virtual thread được unmount hoàn hảo.

~~~java
// Đoạn code minh họa anti-pattern; không phải chương trình chạy độc lập.
@Transactional
public Receipt createReceipt(Request request) {
    Order order = orderRepository.save(new Order(request.id()));
    ShippingQuote quote = shippingClient.fetchQuote(request.address()); // HTTP có thể chậm
    order.setShippingFee(quote.fee());
    return receiptRepository.save(new Receipt(order));
}
~~~

Tùy cấu hình transaction và thời điểm checkout, ví dụ trên **có thể** giữ connection trong lúc chờ HTTP. Nếu quy tắc nhất quán cho phép, tách I/O bên ngoài khỏi giao dịch DB, dùng timeout rõ ràng và lựa chọn thiết kế xử lý lỗi/compensation. Không di chuyển I/O tùy tiện nếu cần bảo đảm tính nhất quán giao dịch.

Cũng cần lưu ý:
- Đóng `Connection`, `ResultSet`, `PreparedStatement` đúng cách (hoặc dùng JdbcTemplate/JPA với quản lý tài nguyên thích hợp); **rò rỉ connection** làm pool cạn.
- Tối ưu SQL, index, số query, tránh N+1; không coi virtual threads là cách sửa query chậm.
- Giới hạn batch/pagination, timeout query, statement, transaction, HTTP request và connection acquisition **riêng biệt**.
- Thực hiện backpressure/admission control trước khi hệ thống tạo queue vô hạn; cấu hình retry có giới hạn và jitter, tránh retry storm khi DB quá tải.
- Driver JDBC và các thư viện khác có thể có phần native, synchronized hoặc blocking chưa tương thích tốt; kiểm tra bằng profiler/JFR trên **JDK và driver thực dùng**.

## 4. Giới hạn thứ ba: pinning — khi virtual thread giữ carrier

### Pinning là gì, và điều kiện nào mới thực sự gây hại?

**Pinning** xảy ra khi virtual thread **không thể unmount khỏi carrier** trong một tình huống cần chờ. Khi một virtual thread block mà carrier vẫn bị giữ, carrier không sẵn sàng chạy virtual thread khác, làm giảm số carrier hữu dụng.

Cần phân biệt:
- **Không có pinning:** virtual thread gọi I/O tương thích, tự unmount trong thời gian đợi; carrier rảnh để làm việc khác.
- **Có pinning:** trong thời gian block, carrier vẫn bị giữ. Nếu xảy ra thường xuyên/đủ lâu, throughput có thể giảm hoặc phát sinh scheduler starvation.
- **Tranh chấp khóa:** thread đợi mutex/monitor. Khóa là ràng buộc logic ngay cả khi không pinned; thay cơ chế lock không biến một critical section nối tiếp thành đồng thời.
- **Chạy CPU:** virtual thread dùng carrier để tính toán là bình thường; đó **không được gọi là pinning** chỉ vì carrier đang bận.

### Phân biệt chính xác giữa JDK 21–23 và JDK 24+

| Phiên bản JDK | `synchronized` chứa thao tác block | Native/FFM và tình huống runtime đặc biệt | Hướng xử lý |
| --- | --- | --- | --- |
| **21–23** | Blocking bên trong `synchronized` method/block **có thể pin** carrier | Vẫn có khả năng pin | Tìm điểm block kéo dài và thường xuyên, cân nhắc thu nhỏ vùng khóa hoặc dùng `ReentrantLock` đúng chỗ |
| **24+** | **JEP 491** sửa phần pinning do monitor/`synchronized` thông thường: virtual thread có thể unmount khi block trong synchronized | Vẫn còn trường hợp pin liên quan native/FFM và một số tình huống VM/runtime; cần đo | Không thay tất cả `synchronized` một cách máy móc; tiếp tục kiểm tra JFR và contention |

**Không học thuộc mẹo “mọi `synchronized` đều làm pinning” như quy tắc Java vĩnh viễn.** Điều đó đặc biệt sai trên JDK 24+. Cũng không kết luận “từ JDK 24 hoàn toàn không còn pinning”: ứng dụng hoặc dependency vẫn có thể chạy native method, foreign function hay đường mã của JVM làm virtual thread không unmount được.

Ví dụ **trên JDK 21–23** có rủi ro pinning do chờ bên trong monitor:

~~~java
// Đoạn minh họa; sẽ còn serialization khi nhiều task dùng cùng monitor.
private final Object monitor = new Object();

public void doSomething() throws InterruptedException {
    synchronized (monitor) {
        Thread.sleep(300); // JDK 21–23: có thể pin carrier trong lúc ngủ
    }
}
~~~

Trên JDK 24+, vấn đề **pinning do synchronized** được khắc phục, nhưng chỉ một thread vẫn giữ monitor mỗi lúc; nếu cùng monitor được dùng nhiều, tác vụ vẫn **nối tiếp**.

Một cách viết thay thế khi thật sự cần loại bỏ pinning của monitor trên JDK 21–23 là `ReentrantLock`:

~~~java
// Đoạn minh họa, không phải cách làm cho cùng critical section chạy song song.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

public void doSomething() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(300);
    } finally {
        lock.unlock();
    }
}
~~~

`ReentrantLock` có thể giúp virtual thread đợi mà không bị **monitor pinning** trên JDK 21–23. Tuy vậy, ví dụ vẫn **giữ lock 300 ms** nên các task dùng cùng lock phải đợi nhau. Cách tối ưu tốt hơn, **chỉ khi bảo đảm đúng invariant**, là giảm thời gian giữ lock và tránh đưa I/O kéo dài vào vùng khóa. Không nên thay đồng loạt mọi `synchronized` ngắn vì có thể tăng độ phức tạp mà không cải thiện tốc độ.

### Những tình huống cần kiểm tra thực tế

- Thư viện cũ thực hiện I/O trong synchronized block trên **JDK 21–23**.
- JDBC driver, native library, JNI/FFM hoặc đường mã tích hợp với runtime có native frame trong lúc block, kể cả JDK 24+.
- Tranh chấp monitor/lock hoặc class initialization; không phải mọi trường hợp chậm đều là `VirtualThreadPinned`, nên phải đối chiếu JFR và thread dump.
- Gọi blocking API không phù hợp hoặc blocking không được JVM unmount hiệu quả trên phiên bản/library/platform đang dùng.

Pinning **không làm sai kết quả chương trình** theo bản chất; tác động chính là khả năng mở rộng và độ trễ. Một event rất hiếm kéo dài không nhất thiết là bottleneck, trong khi vài chục event mỗi giây ở đường request nóng có thể đáng điều tra.

## 5. Dùng virtual threads trong Spring Boot đúng cách

Trong Spring Boot 3.2+ với Java 21+, bật:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Ở cấu hình Servlet web được Spring Boot hỗ trợ, virtual threads có thể dùng cho việc xử lý request với embedded Tomcat/Jetty và các tích hợp Spring task execution. Spring Boot cũng có thể cấu hình `SimpleAsyncTaskExecutor` dùng virtual threads khi auto-configured; `@Async` và scheduling phụ thuộc cấu hình executor/scheduler thực tế. **Nếu tự đăng ký executor hoặc chỉnh container**, hãy xác minh request/task thật sự chạy trên virtual thread. Không suy luận mọi thread của ứng dụng tự động trở thành virtual thread.

Để kiểm tra một endpoint **chỉ trong môi trường thử nghiệm**, có thể thêm:

~~~java
// Đoạn controller minh họa (Spring MVC); imports/ứng dụng không kèm theo.
@RestController
class ThreadInfoController {
    @GetMapping("/thread-info")
    public String threadInfo() {
        return "virtual=" + Thread.currentThread().isVirtual();
    }
}
~~~

Nếu app có virtual-thread configuration và servlet container tương thích, response được kỳ vọng là `virtual=true` cho request chạy trên virtual thread. Nếu `virtual=false`, kiểm tra Java version, cấu hình web server, custom executor và stack/framework. Không dùng endpoint lộ thông tin vận hành này như API công khai.

**Lưu ý:**
- Khi dùng virtual threads, các property liên quan **platform thread pool size** như một số `spring.task.execution.pool.*` và `server.tomcat.threads.*` có thể không còn tác dụng cho các executor đã chuyển sang virtual threads. **Không** nhầm chúng với giới hạn JDBC pool: `spring.datasource.hikari.maximum-pool-size` **vẫn có tác dụng**.
- Virtual threads là **daemon threads**. Spring Boot hỗ trợ `spring.main.keep-alive=true` để quá trình không thoát khi không còn non-daemon threads, quan trọng với ứng dụng chỉ dựa trên scheduled/background tasks.
- Trong Spring WebFlux/reactive pipeline, virtual threads **không tự thay đổi toàn bộ mô hình event loop**; phải xác định executor cho những phần blocking cụ thể. Bài này tập trung servlet request đồng bộ.
- `@Transactional`, security context, MDC logging thường gắn với **thread context**. Trong một đường xử lý đồng bộ cùng thread, chúng vẫn hoạt động theo hợp đồng thư viện. Nếu tự tách sang `@Async`/executor khác, context **không mặc nhiên được truyền**; cần cơ chế propagation đúng của framework.
- Virtual threads không bảo vệ khỏi quá tải; khi tăng concurrency phải có bảo vệ DB pool, remote calls, rate limits, heap, queue và shutdown cancellation.

## 6. Ví dụ Java 21 chạy độc lập: nhiều virtual threads, chỉ hai “kết nối DB”

Ví dụ sau mô phỏng một pool có **2 slot** bằng `Semaphore`. Đây **không phải DB/JDBC thật**; mục tiêu là chứng minh: dù tạo 12 virtual threads, số tác vụ được phép cùng ở trong đoạn dùng tài nguyên bị chặn tại 2. Trong thực tế **HikariCP chính là giới hạn connection**, nên thường không đặt semaphore trùng lặp.

Tạo đúng một file `VirtualThreadLimitsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLimitsDemo {
    public static void main(String[] args) throws Exception {
        final int jobs = 12;
        final int slots = 2;

        Semaphore simulatedConnections = new Semaphore(slots, true);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<Future<?>> results = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < jobs; i++) {
                results.add(executor.submit(() -> {
                    boolean acquired = false;
                    boolean counted = false;
                    try {
                        simulatedConnections.acquire();
                        acquired = true;
                        int current = active.incrementAndGet();
                        counted = true;
                        peak.accumulateAndGet(current, Math::max);

                        // Chờ I/O giả: giữ slot trong lúc không làm CPU nặng.
                        Thread.sleep(40);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(e);
                    } finally {
                        if (counted) {
                            active.decrementAndGet();
                        }
                        if (acquired) {
                            simulatedConnections.release();
                        }
                    }
                }));
            }

            // get() buộc main chờ kết quả và nhận lỗi từ các task.
            for (Future<?> result : results) {
                result.get();
            }
        }

        System.out.println("jobs=" + jobs);
        System.out.println("simulatedConnectionLimit=" + slots);
        System.out.println("peakWithinLimit=" + (peak.get() <= slots));
        System.out.println("activeAfterCompletion=" + active.get());
    }
}
~~~

**Biên dịch và chạy** với JDK 21 hoặc mới hơn, từ thư mục chứa file:

~~~bash
javac VirtualThreadLimitsDemo.java
java VirtualThreadLimitsDemo
~~~

**Stdout đúng khi tất cả task hoàn tất bình thường:**

~~~text
jobs=12
simulatedConnectionLimit=2
peakWithinLimit=true
activeAfterCompletion=0
~~~

Vì `Semaphore` chỉ có hai permit, `peak` không thể vượt quá 2. Thời gian thực thi và giá trị tuyệt đối của `peak` (có thể 1 hoặc 2 tùy môi trường) **không được dùng làm khẳng định cố định**; chỉ `peakWithinLimit=true` là bất biến được chứng minh. `Thread.sleep(40)` mô phỏng **chờ I/O** chứ không đo CPU/DB; chương trình này không phải benchmark JDBC.

Trong ứng dụng thật, thay mô hình trên bằng `DataSource`/HikariCP cùng timeout phù hợp. Nếu cần giới hạn một **nghiệp vụ đặc biệt** chặt hơn giới hạn connection chung (ví dụ chỉ 3 bản báo cáo SQL rất nặng cùng lúc), mới cân nhắc semaphore/bulkhead riêng cho tác vụ đó.

## 7. Ví dụ Spring Boot + JDBC: connection timeout và transaction

Đoạn code dưới đây là **mảnh ví dụ tích hợp Spring MVC/JdbcTemplate**, không phải chương trình độc lập: cần project Spring Boot, `spring-boot-starter-web`, `spring-boot-starter-jdbc`, JDBC driver, datasource và bảng `products(id, name)` thực tế.

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ProductDto(long id, String name) {}

@Repository
class ProductRepository {
    private final JdbcTemplate jdbc;

    ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    ProductDto find(long id) {
        return jdbc.queryForObject(
            "select id, name from products where id = ?",
            (rs, rowNum) -> new ProductDto(
                rs.getLong("id"), rs.getString("name")),
            id
        );
    }
}

@RestController
@RequestMapping("/api/products")
class ProductController {
    private final ProductRepository repository;

    ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    ProductDto get(@PathVariable long id) {
        return repository.find(id);
    }
}
~~~

**Điều cần hiểu về luồng thực thi:**

~~~text
HTTP request
    │
    ▼
Spring MVC controller trên virtual thread (khi đã bật, stack hỗ trợ)
    │
    ▼
JdbcTemplate cần connection
    │
    ├── Pool còn slot → checkout connection → chạy query → trả connection
    │
    └── Pool hết slot → đợi ≤ connectionTimeout → nhận slot hoặc lỗi
                                    │
                                    ▼
                     DB quyết định tốc độ SQL thật
~~~

Không cần viết `new Thread(...)` trong controller để “được hưởng virtual threads”: container và executor phải được cấu hình đúng; khi đó handler request đã chạy trong môi trường virtual thread. Và việc truy cập DB trong controller trên virtual thread **không** tự làm database chạy truy vấn nhanh hơn.

Với HikariCP/Actuator, theo dõi các số đo tương đương **active connections**, **idle**, **pending/waiting threads**, **connection acquisition timeouts** và **connection usage duration**. Tên metric chính xác phụ thuộc Spring Boot/Micrometer và phiên bản; tra metadata Actuator cho stack thực tế.

## 8. Phát hiện pinning, CPU bottleneck và DB bottleneck

### A. JDK Flight Recorder (JFR)

JFR có event `jdk.VirtualThreadPinned` để chỉ ra lần virtual thread bị pinned quá ngưỡng; tài liệu Java công bố ngưỡng mặc định **20 ms** cho event này. Cần thu dữ liệu **dưới tải có vấn đề**, vì run lúc nhàn rỗi thường không tái hiện.

Có thể khởi động ứng dụng JAR kèm recording (thay `app.jar` bằng JAR thực tế):

~~~bash
java -XX:StartFlightRecording=filename=virtual-threads.jfr,duration=60s,settings=profile -jar app.jar
~~~

Sau khi recording ghi file:

~~~bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
~~~

Nếu **không có event**, không có nghĩa toàn hệ thống không có vấn đề: có thể không đủ tải, sự kiện dưới threshold, JFR chưa thu được đúng khoảng thời gian, hoặc bottleneck thật là CPU/DB. Với JDK 21–23, có thể bật stack trace pinning chi tiết bằng **tùy chọn chỉ còn phù hợp với dòng JDK cũ**:

~~~bash
java -Djdk.tracePinnedThreads=full -jar app.jar
~~~

Từ JDK 24, phần giám sát này đã thay đổi cùng JEP 491; **đừng dựa vào `jdk.tracePinnedThreads` để chẩn đoán JDK 24+**. Ưu tiên JFR, thread dump và profiler hỗ trợ JDK đang chạy.

### B. Thread dump cho virtual threads

Lấy PID của JVM, rồi chạy:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json thread-dump.json
~~~

Dump mới này giúp xem virtual threads, nhóm stack đang chờ JDBC/network/lock và mối quan hệ với carrier; không phải mọi loại thread dump truyền thống đều hiển thị virtual threads như nhau. Kết hợp cùng SQL slow query logs, database metrics, CPU profiler và request traces. Không kết luận chỉ từ số lượng thread ở trạng thái WAITING: virtual threads **được thiết kế để chờ rẻ**.

### C. Bảng chẩn đoán theo triệu chứng

| Triệu chứng quan sát | Giả thuyết cần kiểm tra | Số đo/chứng cứ | Hành động phù hợp |
| --- | --- | --- | --- |
| CPU app ~100% quota, throughput không tăng | CPU-bound hoặc GC/throttling | CPU profile, GC pause, throttling, p95 | Tối ưu tính toán, limit CPU-heavy concurrency, scale CPU hợp lý |
| Hikari active = max, pending cao, timeout | Connection pool/DB bottleneck | Active, pending, acquisition wait, SQL latency | Tối ưu SQL/transaction, query timeout, sizing pool dựa trên DB |
| CPU app thấp, DB CPU/lock wait cao | DB bão hòa hoặc lock contention | DB wait events, slow queries, lock graph | Sửa query/index, khóa, transaction; không đổ lỗi cho scheduler |
| Nhiều `jdk.VirtualThreadPinned` event | Carrier bị giữ khi blocking | JFR stack traces, JDK version | Với JDK 21–23 xét `synchronized`; với JDK 24+ xét native/VM |
| Không có pinning nhưng latency cao | Đợi DB pool, HTTP, rate limit, queue | Tracing và timing từng chặng | Thêm admission control, timeout, tối ưu downstream |
| Vừa tăng virtual concurrency thì RAM tăng | Nhiều task, request body, ThreadLocal/cache, queue | Heap profile, allocations, live tasks | Giới hạn inflight và memory footprint; quản lý lifecycle |
| Thêm virtual threads làm p99 tệ hơn | Overload, contention hoặc DB/cpu limit | Load test concurrency sweep, p95/p99, error rate | Tìm điểm công suất hữu hiệu, áp backpressure |

### D. Thiết kế thử tải để đưa ra kết luận đúng

Thử cùng payload, cùng DB data, cùng JVM heap/quota, cùng number of replicas, cùng driver/JDK và warmed-up workload. Tăng tải theo từng mức (concurrency hoặc offered RPS), ghi lại:
1. **Throughput** hoàn thành, tỷ lệ lỗi/timeout, p50/p95/p99 request latency.
2. **CPU app** (và CPU throttling), GC, RAM, runnable carriers/threads khi cần.
3. **Hikari active/idle/pending**, acquisition wait, timeouts và **DB CPU/query/lock waits**.
4. **JFR pinned events**, thời lượng, stack trace và số lần lặp.
5. Queue depth, inflight requests, thời gian chờ HTTP downstream.

Thử ba cấu hình làm đối chứng: platform threads theo mặc định Spring Boot, virtual threads trên JDK 21, và virtual threads trên JDK 24+ (nếu môi trường cho phép). Không kết luận từ thời gian `Thread.sleep` đơn lẻ; thay bằng workload có tỷ lệ CPU/I/O, query và transaction tương tự thực tế. Mục tiêu là tìm **điểm có throughput hữu ích cao mà latency và lỗi còn chấp nhận được**.

## 9. Sai lầm phổ biến

**Sai lầm 1: “Virtual threads làm mọi endpoint nhanh gấp N lần.”** Không. Chúng làm chi phí chờ I/O bằng thread trở nên thấp hơn; endpoint CPU-bound hoặc bottleneck DB có thể không cải thiện.

**Sai lầm 2: “Cho 10.000 virtual threads thì mở 10.000 JDBC connections.”** Không. Connection pool và DB quyết định số connection; pool 10 vẫn chỉ 10 slot đồng thời.

**Sai lầm 3: “Cứ tăng Hikari pool size lên thật cao.”** Pool lớn hơn có thể làm DB quá tải. Cần tính trên mọi replicas và đo DB capacity.

**Sai lầm 4: “Nếu một thread đang ở `synchronized` là chắc chắn pinning.”** Không. Phải có tình huống blocking và phụ thuộc JDK. JDK 24+ đã khắc phục monitor-related pinning; `synchronized` ngắn không mặc nhiên là vấn đề.

**Sai lầm 5: “Đổi hết `synchronized` sang `ReentrantLock` sẽ làm hệ thống đồng thời hơn.”** Không. Lock vẫn bảo vệ một critical section và các tác vụ vẫn có thể phải đợi; chỉ sửa điểm thật sự gây pinning/giữ khóa dài.

**Sai lầm 6: “CPU thấp nghĩa là không nghẽn.”** Có thể pool DB cạn, DB lock wait, remote service chậm hoặc carrier pinning khiến app throughput thấp dù CPU app còn dư.

**Sai lầm 7: “Không có `VirtualThreadPinned` event nghĩa là virtual threads hoàn hảo.”** Không. JFR có threshold và chỉ ghi khi được thu đúng thời điểm; bottleneck khác vẫn tồn tại.

**Sai lầm 8: “Mọi `@Async`, scheduler, MVC, WebFlux đều tự chạy virtual threads khi bật flag.”** Còn phụ thuộc stack, auto-configuration và custom executor. Kiểm tra `Thread.currentThread().isVirtual()` tại đường đang xử lý.

**Sai lầm 9: “Dùng virtual threads thì không cần timeout và backpressure.”** Ngược lại, số lượng request chờ lớn càng làm timeout, retry budget, connection budget và admission control quan trọng.

**Sai lầm 10: “Số virtual thread không ảnh hưởng RAM.”** Mỗi thread nhẹ hơn platform thread nhưng vẫn có stack/đối tượng/lifecycle; một triệu task cùng giữ request body hoặc tài nguyên có thể ngốn rất nhiều heap.

## 10. Checklist áp dụng và câu hỏi tự kiểm tra

Trước khi bật trên production, trả lời các câu hỏi: **Ứng dụng đang nghẽn cái gì? Tải có chủ yếu chờ I/O không? DB pool đủ và được theo dõi không? JDK đang dùng là 21 hay 24+? Có đường JNI/driver/lock bất thường không? Request/error/timeout/queue được giới hạn không?** Nếu chưa biết, hãy đo trước khi tối ưu.

Tự kiểm tra:

1. Server có 8 cores, 2.000 HTTP requests mỗi request tính toán liên tục 100 ms CPU. Tạo 2.000 virtual threads có làm tất cả hoàn thành trong 100 ms không? Vì sao?
2. HikariCP `maximum-pool-size=8`, 100 virtual threads cùng cần JDBC connection. Tối đa bao nhiêu connection có thể được checkout từ **pool này** tại một thời điểm? 92 request còn lại sẽ làm gì?
3. Query SQL giữ connection 200 ms và pool có 10 slot. Vì sao “nâng thread count” không làm query chạy nhanh gấp 10 lần?
4. JDK 21 có `Thread.sleep(250)` trong `synchronized` ở đường request nóng. Bạn sẽ dùng công cụ nào tìm pinning? Khi nâng lên JDK 24, điều gì thay đổi, và điều gì **không** thay đổi?
5. Cấu hình `spring.threads.virtual.enabled=true` nhưng một tác vụ `@Async` vẫn dùng platform thread. Những custom executor/config nào cần kiểm tra?
6. Một request mở transaction, truy vấn DB, gọi HTTP 2 giây, rồi commit. Vì sao virtual thread không giải quyết được tình trạng Hikari pending cao?

**Gợi ý đáp án:** (1) Không: vẫn cần khoảng 200 giây CPU tổng cộng, cận dưới lý tưởng ~25 giây trên 8 core nếu không có overhead; (2) tối đa 8, còn lại đợi slot hoặc timeout; (3) pool và DB vẫn hữu hạn, thời gian giữ connection chưa giảm; (4) JFR `jdk.VirtualThreadPinned` và thread dump, JDK 24 sửa monitor pinning nhưng vẫn còn serialization do lock và trường hợp native; (5) executor bean tự cấu hình, container, scheduler/stack; (6) transaction có thể giữ JDBC connection khi đợi HTTP, nên cần tối ưu ranh giới transaction.

### Tài liệu chính thức

- Oracle: [Virtual Threads — Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — cơ chế, chẩn đoán pinning, `Semaphore`, ThreadLocal.
- Oracle: [Virtual Threads — Java 24](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html) — hành vi sau thay đổi về `synchronized`, JFR/thread dump.
- Oracle: [Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html) — JEP 491.
- Spring Boot 3.5: [SpringApplication — Virtual threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html) — enable, JDK requirement, keep-alive và lưu ý pinning.
- Spring Boot 3.5: [Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html) — auto-configured executors/schedulers.
- HikariCP: [Configuration](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby) — `maximumPoolSize`, `connectionTimeout` và những giới hạn pool.
