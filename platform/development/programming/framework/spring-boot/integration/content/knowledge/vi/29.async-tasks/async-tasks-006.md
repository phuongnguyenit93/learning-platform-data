# Luồng ảo trên Java 21 và giới hạn của tài nguyên bên ngoài

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp hệ thống qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Điểm quan trọng không chỉ là gọi được một API, đọc được một bảng hay nhận được một message: hệ thống còn phải quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát toàn bộ luồng tích hợp.

Một tình huống phổ biến: Order Service nhận 1.000 yêu cầu đồng thời; mỗi yêu cầu cần gọi Inventory API, tra PostgreSQL, đọc Redis rồi ghi outbox để phát sự kiện. Dùng platform threads truyền thống, rất nhiều threads có thể đang **chờ I/O** thay vì tính toán. Java 21 giới thiệu **virtual threads** như một tính năng chính thức (JEP 444): giúp triển khai mô hình thread-per-task với chi phí thread thấp hơn đáng kể trong nhiều tác vụ chờ I/O.

Tuy nhiên, **virtual thread không làm Inventory API nhận được vô hạn requests, HikariCP có thêm JDBC connections, PostgreSQL thực hiện được vô hạn transactions hay broker xử lý vô hạn messages**. Nếu chuyển toàn bộ công việc sang hàng trăm nghìn virtual threads mà không giới hạn concurrency, lỗi có thể chuyển từ “thiếu Java worker threads” thành “DB pool exhausted”, “HTTP 429”, “RabbitMQ unacked tăng”, OOM hoặc timeout dây chuyền.

Bài thuộc chương **Tác vụ bất đồng bộ**, đề mục **Luồng ảo trên Java 21 và giới hạn của tài nguyên bên ngoài**. Trọng tâm là hiểu virtual thread như một **cách tổ chức luồng thực thi**, không phải một cơ chế bảo đảm throughput, transaction hay delivery semantics.

Sau bài học, bạn có thể:

1. Phân biệt Java platform thread, virtual thread, carrier thread và blocking I/O.
2. Biết khi nào virtual threads giúp throughput/đơn giản hóa code và khi nào không có lợi.
3. Sử dụng `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` trên Java 21.
4. Cấu hình `spring.threads.virtual.enabled=true`, `@Async`, `TaskExecutor` và `@Scheduled` phù hợp trong Spring Boot.
5. Nhận diện pinning do `synchronized`/native code trong Java 21 và công cụ quan sát.
6. Giới hạn concurrency của HTTP pools, JDBC/HikariCP, Redis và broker listeners.
7. Tránh mất transaction/security context, ACK sớm và task RAM bị mất khi process crash.
8. Thiết kế semaphore/bulkhead, timeout, retry budget, cancellation, idempotency và outbox.
9. Kiểm thử virtual-thread execution, resource saturation, failure windows và observability.

> **Luận điểm cốt lõi:** Virtual threads giúp **mở rộng số tác vụ có thể chờ I/O**, nhưng giới hạn tài nguyên bên ngoài vẫn còn. Thiết kế đúng cần **bounded concurrency, bounded waiting, deadline, retry có kiểm soát và durability**.

## 1. Platform thread và virtual thread khác nhau thế nào?

### 1.1. Platform thread: một tài nguyên hệ điều hành tương đối đắt

Với Java truyền thống, `new Thread(...).start()` thường tạo **platform thread** được ánh xạ tới một operating-system thread. Stack, scheduler và context switching có chi phí. Nếu 500 worker threads cùng chờ HTTP response, nhiều OS threads bị chiếm nhưng không xử lý CPU hữu ích.

Trong mô hình thread pool:

~~~text
Incoming requests
       |
       v
Queue của executor
       |
       v
Fixed platform-thread workers: 32
       |
       +-- chờ HTTP 200 ms
       +-- chờ JDBC 50 ms
       +-- chờ broker confirm 100 ms
       |
       v
Completed requests
~~~

Khi 32 threads đều đang chờ, task thứ 33 phải xếp hàng, dù CPU còn rảnh.

### 1.2. Virtual thread: thread nhẹ do JVM quản lý

Java 21 virtual thread là một đối tượng `java.lang.Thread` nhưng không gắn cố định 1:1 với OS thread trong suốt vòng đời. JVM scheduler sử dụng một số **carrier platform threads** để chạy virtual threads.

Khi một virtual thread thực hiện một thao tác blocking **mà JDK hỗ trợ unmount**, JVM có thể tháo virtual thread khỏi carrier. Carrier rảnh để chạy virtual thread khác.

~~~mermaid
flowchart TD
    A["Virtual Thread A"] --> C["Carrier thread 1"]
    B["Virtual Thread B"] --> D["Carrier thread 2"]
    C --> E["HTTP I/O wait: A unmount"]
    D --> F["CPU work: B running"]
    E -. "Carrier can run other virtual thread" .-> G["Virtual Thread C"]
    G --> C
    E --> H["I/O ready: A becomes runnable"]
    H --> I["Mount A on an available carrier"]
~~~

Một virtual thread vẫn có identity, stack trace, interruption và `ThreadLocal` semantics; khác biệt chủ yếu nằm ở **lịch trình thực thi và tài nguyên carrier**.

**Không nhầm:** JVM không tự biến mọi blocking operation của mọi native library thành non-blocking. Một số operations pin carrier hoặc dùng blocking native calls; Java 21 có hạn chế cần đo thực tế.

### 1.3. So sánh nhanh

| Khía cạnh | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Đơn vị Java | `Thread` | `Thread` |
| OS thread cố định | Thường một OS thread | Mount lên carrier khi chạy |
| Chi phí tạo nhiều thread | Tương đối cao | Thường thấp hơn đáng kể |
| Chờ I/O JDK hỗ trợ | Platform thread bị chặn | Có thể unmount, carrier dùng làm việc khác |
| CPU-bound task | Dùng CPU core | Vẫn dùng CPU core |
| ThreadLocal | Có | Có, nhưng nhiều thread làm memory cost tăng |
| Interruption | Có | Có |
| Cần giới hạn remote concurrency? | Có | **Vẫn có** |
| Có transaction tự động giữa hệ thống? | Không | **Không** |
| Thay message broker/durable queue? | Không | **Không** |

Virtual threads phù hợp nhiều **blocking I/O tasks**, không phải một thủ thuật làm CPU computation chạy nhanh hơn số cores hiện có.

## 2. Virtual thread là thread-per-task, không phải thread pool cổ điển

Một cách dùng JDK 21:

~~~java
import java.util.concurrent.Executors;

public class VirtualThreadDemo {

    public static void main(String[] args) throws Exception {
        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            var future = executor.submit(() -> {
                System.out.println(
                        "virtual=" +
                        Thread.currentThread().isVirtual());

                Thread.sleep(200);
                return "Inventory loaded";
            });

            System.out.println(future.get());
        }
    }
}
~~~

`Executors.newVirtualThreadPerTaskExecutor()` tạo một **virtual thread mới cho mỗi task được gửi vào**. Nó không phải một pool 10/100 threads cố định, dù thực tế JVM có tập carriers riêng.

- `Thread.sleep(...)` trên virtual thread thường cho phép unmount, không chiếm carrier suốt thời gian ngủ.
- `Future.get()` chờ kết quả và có thể block thread gọi; nếu caller là virtual thread, chờ cũng có thể rẻ hơn về OS threads.
- `try-with-resources` đóng `ExecutorService`; thao tác `close()` của executor có semantics chờ tasks kết thúc, vì vậy chú ý tasks không bao giờ hoàn thành.
- Nếu task ném exception, `Future.get()` báo `ExecutionException`; đừng coi submit thành công là nghiệp vụ thành công.

### 2.1. Thread.ofVirtual()

~~~java
Thread worker = Thread.ofVirtual()
        .name("inventory-lookup-", 0)
        .start(() -> {
            // Blocking I/O call hoặc logic tác vụ.
            loadInventory();
        });

worker.join();
~~~

`Thread.ofVirtual()` phù hợp tác vụ nhỏ hoặc thử nghiệm lifecycle. Với Spring Boot, thường nên để Spring-managed `TaskExecutor`/integration components quản lý thay vì tự tạo threads rải rác trong controller/service.

### 2.2. Vì sao không pool virtual threads?

Virtual threads được thiết kế đủ nhẹ để **tạo theo từng task**. Dùng một fixed pool of virtual threads chỉ để tiết kiệm threads thường không cần thiết và có thể làm nghẽn concurrency không đúng chỗ.

Nếu cần hạn chế **số tasks gọi Inventory**, hãy giới hạn bằng **semaphore, bulkhead, rate limiter hoặc bounded executor admission**, vì giới hạn này phản ánh năng lực của Inventory API, không phản ánh chi phí tạo virtual thread.

### 2.3. Virtual threads không tăng số CPU cores

~~~text
100 CPU-heavy tasks
  -> 8 CPU cores
  -> virtual threads vẫn tranh 8 cores
~~~

Với CPU-bound workloads như mã hóa dữ liệu lớn, compression, image processing hoặc JSON validation khổng lồ, một pool gần số CPU cores thường hợp lý hơn. Tạo 100.000 virtual threads CPU-heavy chỉ tăng scheduling/heap overhead và latency.

## 3. Spring Boot và yêu cầu phiên bản

Spring Boot 3.2+ trên Java 21 cung cấp tích hợp virtual threads qua property:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Với **đúng phiên bản Boot/Spring Framework và auto-configurations hỗ trợ**, property có thể chuyển một số luồng thực thi Spring-managed, chẳng hạn task execution/scheduling và supported servlet web container request processing, sang virtual threads.

**Không có nghĩa** mọi thread trong JVM đều virtual:

- Netty event-loop của WebFlux vẫn tuân theo event-loop model.
- Kafka consumer `poll()` threads không mặc định biến thành virtual threads chỉ vì property.
- RabbitMQ connection/client threads và listener container strategy cần kiểm tra theo Spring AMQP version.
- JDBC driver, Redis native client, HTTP transport threads có lifecycle riêng.
- Một `ThreadPoolTaskExecutor` do ứng dụng tự định nghĩa vẫn chạy theo config của chính bean.
- Một third-party SDK tạo platform threads riêng không tự chuyển sang virtual threads.

### 3.1. Cấu hình ví dụ

~~~yaml
spring:
  threads:
    virtual:
      enabled: true

  main:
    keep-alive: true
~~~

`spring.main.keep-alive=true` hữu ích cho ứng dụng **chỉ có scheduled/background tasks** mà không có non-daemon thread khác giữ JVM sống: virtual threads là **daemon threads** và không tự giữ process tồn tại. Nếu có web server/lifecycle khác giữ process, cần đánh giá nhu cầu thay vì bật theo thói quen.

### 3.2. Kiểm tra những property nào còn tác dụng

Khi Boot dùng virtual-thread-oriented task executor thay thread pool truyền thống, một số `spring.task.execution.pool.*` options (core-size, max-size, queue-capacity...) có thể **không còn điều khiển tài nguyên như trước**. Không copy nguyên "pool size=200" từ platform thread setup rồi nghĩ đó là giới hạn số virtual threads.

Khi cần giới hạn công việc, tạo named executor/bean có concurrency policy hoặc dùng bulkhead ở adapter HTTP/DB; xác minh bean nào được Spring injection và runtime thread hiện tại có `isVirtual() == true`.

## 4. @Async không tự động có virtual thread

`@Async` trong Spring chuyển lời gọi method qua một `Executor` được cấu hình. Virtual thread hay platform thread phụ thuộc **executor thực tế**, không phải bản thân annotation.

### 4.1. Bật @Async

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
}
~~~

Khi dùng Spring Boot, `@EnableAsync` cần được bật trong cấu hình ứng dụng để kích hoạt xử lý annotation (trừ khi một configuration khác đã bật). Không nhầm có `@Async` trên method với việc đã có proxy/executor.

### 4.2. Named SimpleAsyncTaskExecutor dùng virtual threads

~~~java
// AsyncIntegrationConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncIntegrationConfiguration {

    @Bean("inventoryTaskExecutor")
    AsyncTaskExecutor inventoryTaskExecutor() {
        var executor =
                new SimpleAsyncTaskExecutor("inventory-vt-");

        executor.setVirtualThreads(true);
        executor.setConcurrencyLimit(24);
        return executor;
    }
}
~~~

`SimpleAsyncTaskExecutor.setVirtualThreads(true)` có trong các phiên bản Spring Framework hỗ trợ virtual threads (Spring 6.1+). Nó không tái sử dụng một fixed virtual-thread pool: mỗi task được chạy trong thread mới, còn `setConcurrencyLimit(24)` giới hạn số tasks đang thực hiện qua cơ chế throttle của executor.

**Lưu ý:** `setConcurrencyLimit` không đồng nghĩa bounded queue với rejection semantics. Khi đạt giới hạn, caller có thể phải chờ theo behavior của implementation/version. Phải đo request latency và xác định submission wait timeout/rejection ở tầng thích hợp; với API latency-sensitive, có thể cần bulkhead `tryAcquire(timeout)` để fail fast.

### 4.3. @Async trả CompletableFuture

~~~java
// InventoryLookupService.java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookupService {

    private final InventoryGateway gateway;

    public InventoryLookupService(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    @Async("inventoryTaskExecutor")
    public CompletableFuture<InventoryRecord> load(String sku) {
        InventoryRecord result = gateway.getStock(sku);

        return CompletableFuture.completedFuture(result);
    }
}
~~~

`InventoryGateway` và `InventoryRecord` là domain ports/DTO do ứng dụng định nghĩa. Trong ví dụ, `gateway.getStock(...)` là **blocking HTTP call** trên virtual thread. `@Async` proxy trả một future cho caller; method body vẫn chạy đồng bộ **trong thread của executor**.

Nếu method body ném exception, future cần biểu diễn failure; không trả `completedFuture(null)` để che đi HTTP timeout.

### 4.4. @Async proxy và self-invocation

~~~java
@Service
public class OrderService {

    public void process() {
        runAsync(); // Self-invocation: bỏ qua @Async proxy.
    }

    @Async("inventoryTaskExecutor")
    public void runAsync() {
        // Có thể chạy synchronous trên caller thread!
    }
}
~~~

Trong proxy-based Spring AOP mặc định, gọi `this.runAsync()` trong cùng bean **không đi qua proxy**. Kết quả: phương thức có thể vẫn chạy trên platform HTTP request thread và không có asynchronous boundary mong muốn.

**Cách sửa:** tách method async sang Spring bean khác, inject bean đó rồi gọi qua proxy; hoặc tổ chức orchestration bằng explicit `AsyncTaskExecutor`.

### 4.5. Vì sao nên trả Future thay vì void?

Với `@Async void`, caller không nhận được exception qua future; cần `AsyncUncaughtExceptionHandler`/metrics riêng. Với `CompletableFuture<T>`, caller có thể xử lý failure, kết hợp nhiều tasks và đặt timeout/deadline. Dù vậy, future hoàn thành không tự chứng minh remote business operation chắc chắn không bị lặp.

## 5. @Scheduled và virtual threads

Với Spring Framework 6.1+ và Boot hỗ trợ, khi bật virtual threads, Spring có thể dùng `SimpleAsyncTaskScheduler` thay `ThreadPoolTaskScheduler` cho scheduled tasks.

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxScheduler {

    private final OutboxRelay relay;

    public OutboxScheduler(OutboxRelay relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelayString =
            "${app.outbox.interval-ms:1000}")
    public void poll() {
        relay.publishDueEvents();
    }
}
~~~

Để kích hoạt `@Scheduled`, ứng dụng cần `@EnableScheduling` ở configuration. `OutboxRelay` là service do ứng dụng định nghĩa.

### 5.1. Fixed delay khác fixed rate

- `fixedDelay`: lần chạy tiếp theo bắt đầu sau khoảng trễ tính từ **khi lần chạy trước kết thúc**.
- `fixedRate`: mốc kích hoạt theo chu kỳ thời gian; nếu tác vụ chậm, có thể chồng overlap tùy scheduler/concurrency.
- Cron: dựa lịch; phải chú ý timezone, clock và daylight saving.

Với `SimpleAsyncTaskScheduler`, **fixed-delay tasks được thực hiện trên một scheduler thread** theo semantics Spring 6.1. Đây là trường hợp cần đặc biệt lưu ý: virtual threads không có nghĩa mỗi fixed-delay job sẽ tự chạy song song trên virtual thread. Đối với fixed-rate/cron, scheduler có thể tạo các worker threads riêng cho từng execution.

### 5.2. Không tăng job concurrency theo cảm tính

Outbox relay nên claim rows/leases bền vững để nhiều pods không publish trùng ngoài ý muốn; `@Scheduled` và virtual threads không cung cấp distributed lock. Với Quartz, sự phối hợp clustered scheduling cũng phụ thuộc cấu hình job store/cluster, không liên quan trực tiếp đến việc một job chạy trên virtual thread hay không.

### 5.3. JVM có thể thoát khi chỉ còn daemon virtual threads

Java virtual threads là daemon. Một chương trình batch chỉ có virtual-thread scheduled activity có thể kết thúc nếu không còn non-daemon threads. Trong Spring Boot job-only application, cấu hình keep-alive, lifecycle và shutdown đúng để process sống theo yêu cầu.

## 6. Virtual threads cải thiện gì ở blocking I/O?

Giả sử Inventory lookup chờ 250 ms, CPU xử lý payload chỉ mất 5 ms. Với 32 platform worker threads, một lượng lớn thời gian worker bị chiếm do network wait. Virtual threads có thể cho phép nhiều yêu cầu chờ cùng lúc mà không cần hàng trăm OS threads.

Một phép ước lượng theo **Little's Law**:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số operations đang đồng thời (in flight).
- \(\lambda\): throughput trung bình, ví dụ 300 requests/giây.
- \(W\): thời gian trung bình mỗi operation, ví dụ 0,15 giây.

Khi đó \(L \approx 300 \times 0{,}15 = 45\) operations đang chờ/xử lý trung bình. Nếu service có DB pool chỉ 12 connections và mỗi request giữ JDBC connection trong phần lớn 150 ms, bottleneck không còn là số Java threads.

### 6.1. Virtual threads loại bỏ một bottleneck, không loại bỏ bottleneck mới

~~~mermaid
flowchart TD
    A["10.000 virtual threads"] --> B["HTTP connection pool: 32"]
    B --> C["Inventory API: max 100 req/s"]
    A --> D["HikariCP: 12 JDBC connections"]
    D --> E["PostgreSQL: locks + SQL execution"]
    A --> F["Redis client / broker channels"]
    F --> G["Redis or RabbitMQ capacity"]
    C --> H["429 / 503 / rising latency"]
    E --> I["pool wait / timeouts"]
    G --> J["backlog / unacked"]
~~~

**Mở rộng phần chờ ở JVM còn có thể làm lưu lượng đến external systems tăng đột ngột.** Cần đặt các giới hạn riêng cho từng downstream.

### 6.2. Vì sao không chỉ tăng max connections?

Nếu Inventory API chỉ xử lý được 100 req/s, tăng HTTP pool từ 32 lên 500 có thể tạo nhiều requests đồng thời và làm đối tác trả 429/503. Nếu PostgreSQL chỉ chịu được 80 connections cho toàn hệ thống, mỗi pod tăng Hikari max lên 100 sẽ gây quá tải thay vì tăng throughput.

### 6.3. Thread cheap không có nghĩa operation cheap

Mỗi virtual thread vẫn có stack frames, Java objects, context, headers, payload và tài nguyên khác. 100.000 virtual threads đồng thời giữ mỗi task vài KB/MB dữ liệu có thể gây GC pressure/OOM. Memory không bằng 0; chỉ là thread scheduling/stack management thường hiệu quả hơn platform threads khi phần lớn đang chờ.

## 7. JDBC và HikariCP: ví dụ giới hạn số connection

Một `@Transactional` dùng Spring Data JDBC/JPA thường cần JDBC connection do `DataSource`/HikariCP cấp. Dùng virtual threads **không thay số connections**.

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://db.internal:5432/orders}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: order-db
      maximum-pool-size: 12
      connection-timeout: 2000
      max-lifetime: 1800000
~~~

Trong ví dụ, pool có tối đa khoảng 12 JDBC connections **per application instance** theo cấu hình. Nếu 8 pods chạy, tổng tiềm năng khoảng 96 connections, chưa tính admin/jobs/services khác.

### 7.1. Virtual thread chờ Hikari không có JDBC connection

~~~text
200 virtual threads chạy repository.findById()
    |
    +-- 12 threads mượn được JDBC connections
    |
    +-- 188 threads chờ slot pool
               |
               +-- timeout 2s → SQLException/DataAccessException
~~~

Virtual threads có thể giúp chờ slot pool không chiếm nhiều OS threads. Nhưng **throughput của DB không tăng**; nếu chờ quá nhiều, application vẫn tiêu tốn heap, request time và làm khách hàng timeout.

### 7.2. Transaction giữ connection qua HTTP call là anti-pattern

~~~java
@Transactional
public void confirmOrder(Long id) {
    OrderEntity order = orders.findById(id).orElseThrow();
    order.confirm();

    // Dù chạy trên virtual thread, JDBC transaction đang mở.
    inventoryGateway.reserve(order.getExternalId());
}
~~~

Khi partner HTTP chậm 10 giây, SQL transaction/connection và locks có thể bị giữ lâu. Thay platform thread bằng virtual thread **không giải phóng JDBC connection** đã bị transaction giữ.

Thiết kế tốt hơn:

1. Trong local SQL transaction: update order, insert outbox intent.
2. Commit transaction, trả JDBC connection.
3. Outbox relay gọi Inventory/Kafka ngoài SQL transaction.
4. Ghi outcome/attempts trong các SQL transactions ngắn.
5. Dùng idempotency/reconciliation nếu partner timeout sau khi xử lý.

### 7.3. Transaction context không tự vượt thread boundary

Spring transaction thông thường dùng thread-bound context. Ví dụ:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    orders.save(command.toEntity());
    asyncNotifier.notifyInventory(command.orderId());
}
~~~

Nếu `asyncNotifier.notifyInventory(...)` chạy trên thread khác, nó **không tham gia cùng JDBC transaction** của `placeOrder` chỉ vì caller có `@Transactional`. Phần async có thể đọc dữ liệu chưa commit/không nhìn thấy record hoặc chạy khi transaction caller rollback.

**Quy tắc:** Không đưa `@Async` vào giữa một chuỗi thao tác mà bạn muốn atomic theo một local transaction. Ghi durable outbox trong transaction rồi xử lý ngoài transaction.

## 8. HTTP client: connection pool, quota và backpressure

`RestClient` là blocking HTTP API; virtual threads có thể giúp nhiều callers chờ response mà không tiêu tốn nhiều OS threads. Tuy nhiên, HTTP transport vẫn có:

- Connection pool max toàn cục/per route.
- Connection acquisition timeout.
- TCP connect/TLS handshake timeout.
- Response/read timeout.
- Server-side rate limit, concurrency cap và circuit breaker.
- Maximum payload/body size và buffering.
- Connection idle/max lifetime và proxy behavior.

### 8.1. RestClient là API, không phải pool

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.org")
                .build();
    }
}
~~~

Underlying `ClientHttpRequestFactory`/HTTP client quyết định connection reuse. Không assume gọi `RestClient.builder()` tự chọn pool size hoặc timeout phù hợp production. Khi cần Apache HttpClient 5/JDK HttpClient/other transport, cấu hình rõ request factory và connection manager.

### 8.2. Semaphore bulkhead: hạn chế Inventory calls

Một cách độc lập với platform/virtual thread:

~~~java
// InventoryGateway.java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryGateway {

    private final RestClient client;
    private final Semaphore permits = new Semaphore(24);

    public InventoryGateway(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    public InventoryRecord getStock(String sku) {
        boolean acquired;
        try {
            acquired = permits.tryAcquire(
                    200, TimeUnit.MILLISECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Inventory lookup interrupted", ex);
        }

        if (!acquired) {
            throw new DownstreamBusyException(
                    "Inventory concurrency budget exhausted");
        }

        try {
            return client.get()
                    .uri("/v1/stock/{sku}", sku)
                    .retrieve()
                    .body(InventoryRecord.class);
        } finally {
            permits.release();
        }
    }
}
~~~

`InventoryRecord` và `DownstreamBusyException` là DTO/exception ứng dụng cần định nghĩa. `permits` là singleton per application instance (bean `InventoryGateway`), nghĩa là chỉ có khoảng 24 in-flight Inventory lookups trên mỗi pod.

Điểm quan trọng:

- Giới hạn này bảo vệ **external downstream**, không phải “giới hạn số virtual threads trong JVM”.
- `tryAcquire(timeout)` bảo đảm caller không chờ vô hạn để vào bulkhead.
- `finally` trả permit cả khi HTTP timeout/exception.
- Nếu hệ thống có 8 pods, tổng in-flight có thể tới 8 × 24 = 192; phải tính distributed budget.
- Semaphore không phải rate limiter: 24 concurrent calls với mỗi call 10 ms vẫn có thể tạo QPS cao.
- Không cầm JDBC transaction trong khi chờ/giữ HTTP permit nếu có thể tránh.

### 8.3. Rate limit khác concurrent limit

| Công cụ | Điều khiển | Ví dụ |
| --- | --- | --- |
| Semaphore/bulkhead | Số operations in flight | Tối đa 24 Inventory calls mỗi pod |
| Rate limiter | Số requests trong khoảng thời gian | Tối đa 100 calls/giây |
| HTTP connection pool | Số sockets/HTTP connections | 32 connections per route |
| Circuit breaker | Tạm ngừng gọi khi upstream lỗi | Open khi error rate vượt ngưỡng |
| Timeout | Thời gian tối đa của một giai đoạn | Pool wait 200 ms; response 2 s |
| Retry budget | Số attempts/backoff tổng | Tối đa 2 attempts trong deadline |

Một hệ thống ổn định thường cần **kết hợp**, không chọn một công cụ duy nhất.

### 8.4. Đừng giới hạn virtual threads bằng số HTTP sockets

Một tác vụ có thể chờ database, một tác vụ khác chờ HTTP, một tác vụ khác đang serialize payload. Giới hạn số virtual threads toàn ứng dụng chỉ vì HTTP pool 24 có thể làm nghẽn các tác vụ độc lập. Đặt bulkhead đúng **resource boundary** của HTTP Inventory; đồng thời có giới hạn DB, broker và bộ nhớ riêng.

## 9. WebClient, Reactor Netty và virtual threads

`WebClient` là API reactive, thường chạy trên event-loop của Reactor Netty. Virtual threads và reactive programming giải quyết một phần bài toán tương tự (không giữ OS thread chỉ để chờ I/O), nhưng chúng là **hai execution models khác nhau**.

| Trường hợp | Khuyến nghị |
| --- | --- |
| Spring MVC + blocking `RestClient` | Virtual threads có thể giúp nếu I/O-bound |
| Spring WebFlux + `WebClient` reactive chain | Giữ non-blocking pipeline; không block Netty event loop |
| Library chỉ có blocking JDBC API | Virtual thread giúp giảm OS thread blocking overhead, DB pool vẫn là giới hạn |
| CPU-bound transform trong Reactor | Scheduler/bounded worker pool phù hợp; virtual threads không thêm CPU |
| Gọi `WebClient.block()` bên trong event loop | Anti-pattern; có thể gây lỗi/stall |
| Gọi một blocking SDK trên virtual thread ngoài event loop | Có thể hợp lý nếu SDK hỗ trợ, đo pinning và resource usage |

### 9.1. Không đưa .block() lên Netty event loop

~~~java
// Anti-pattern nếu method được gọi trên Reactor Netty event loop:
InventoryRecord record = webClient.get()
        .uri("/v1/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryRecord.class)
        .block();
~~~

Bật `spring.threads.virtual.enabled=true` **không biến event-loop thread thành virtual thread**. Với reactive chain, dùng `flatMap`, operator timeouts, bounded concurrency và non-blocking database/HTTP adapters; nếu phải gọi blocking code, offload có chủ đích khỏi event loop.

### 9.2. Không trộn mô hình chỉ vì nghe nhanh hơn

Có thể dùng WebClient trong MVC app, hoặc RestClient trên virtual threads. Chọn theo độ phức tạp hệ thống, thư viện, observability và throughput đã đo. Virtual threads thường làm code imperative đơn giản hơn trong I/O-bound cases; reactive có ưu điểm về compositional backpressure/streams nhưng yêu cầu hiểu scheduler/operator semantics.

## 10. Redis và cache không trở nên vô hạn

Spring Data Redis thường có `RedisTemplate`/`StringRedisTemplate`, `LettuceConnectionFactory` và Redis client. Lettuce sử dụng event-loop/network I/O của riêng nó; synchronous Redis operations có thể chặn caller.

Virtual threads có thể làm chờ Redis command rẻ hơn về OS threads, nhưng:

- Redis server/network vẫn có capacity và throughput limit.
- Một số lệnh Redis nặng có thể khóa event loop/server execution.
- Shared native connections, transactional pipelines và blocking commands có lifecycle riêng.
- Cache stampede có thể khiến hàng nghìn virtual threads cùng gọi database trên cache miss.
- Timeout/circuit breaker/fallback policy cần được định nghĩa.
- Redis write không tự atomic cùng PostgreSQL transaction.

### 10.1. Cache stampede khi mở concurrency

~~~text
Cache key expires
  -> 5.000 virtual threads read MISS
  -> all call PostgreSQL at once
  -> Hikari pool max 12
  -> huge wait, timeouts, 5xx
~~~

Giải pháp có thể là per-key single-flight, jittered TTL, stale-while-revalidate, bounded DB concurrency hoặc cache warming theo workload. Virtual threads không thay **request coalescing** và **rate limiting**.

### 10.2. ThreadLocal với Redis transaction?

`RedisTemplate` có transaction/pipelining semantics và connection lifecycle riêng. Không share một stateful RedisConnection tùy tiện giữa nhiều virtual threads. Dùng template/factory được framework quản lý và kiểm thử transaction, serialization và timeout theo Redis topology thật.

## 11. Kafka, RabbitMQ và giới hạn consumer

Virtual threads **không thay đổi delivery semantics** của message broker.

### 11.1. KafkaConsumer không thread-safe

`KafkaConsumer` có consumer-group membership, `poll()` loop, partition assignments và offset commits. Đừng cho 1.000 virtual threads gọi `poll()` trên **cùng KafkaConsumer**. Trong Spring Kafka, listener containers thường quản lý consumer instances theo concurrency; một group có số partitions giới hạn song song hữu ích.

~~~text
@KafkaListener container
    -> KafkaConsumer poll()
    -> onMessage(record)
    -> DB transaction commit
    -> offset acknowledgement/commit
~~~

### 11.2. Bẫy offload Kafka record rồi ACK sớm

~~~java
@KafkaListener(topics = "orders.events")
public void unsafeConsume(OrderEvent event) {
    virtualExecutor.submit(() -> processOrder(event));
    // Listener returns, container có thể advance/commit progress
    // trước khi async task xử lý xong, tùy ack mode.
}
~~~

Đây là **anti-pattern** khi phải bảo đảm at-least-once business processing. Partition order và offsets không tự hiểu các `Future` độc lập đang chạy. Nếu muốn xử lý song song trong một partition, cần logic theo dõi completion/commit contiguous offsets, ordering/idempotency rất cẩn thận, hoặc dùng durable work queue/inbox.

### 11.3. RabbitMQ vẫn bị giới hạn prefetch/channels

Một `@RabbitListener` có container-managed consumers, prefetch, channel ACK và retry policy.

- Dùng virtual threads không tự tăng RabbitMQ queue throughput.
- Nếu listener return sớm sau `executor.submit(...)`, `AcknowledgeMode.AUTO` có thể ACK message trước khi task hoàn thành.
- `AcknowledgeMode.MANUAL` đòi ACK trên đúng channel/delivery tag sau business commit.
- Prefetch × consumers × replicas quyết định số deliveries in flight.
- Dead-letter/requeue behavior không thay vì thread là virtual.

Nếu cần async handoff, **ghi durable inbox/work item** rồi ACK source; hoặc dùng supported async listener return semantics của đúng Spring AMQP version và kiểm thử ACK timing.

### 11.4. Broker acknowledgement không phải business commit

Kafka producer future thành công hoặc RabbitMQ publisher confirm ACK chỉ chứng minh broker accepted theo policy. Consumer ACK/offset commit chỉ thể hiện tiến độ consume. SQL business state và downstream HTTP side effect cần được xác nhận riêng.

## 12. Spring Integration: ExecutorChannel và thread boundary

Spring Integration có `DirectChannel`, `ExecutorChannel`, pollers, gateways và adapters. Khi dùng asynchronous channel, message handoff chuyển thread và transaction/security/error-context cũng đổi theo.

~~~mermaid
flowchart TD
    A["HTTP inbound gateway"] --> B["DirectChannel"]
    B --> C["Validate and persist durable intent"]
    C --> D["ExecutorChannel / async handoff"]
    D --> E["Virtual-thread TaskExecutor"]
    E --> F["HTTP/DB/broker adapter"]
    F --> G["Error channel / result"]
~~~

**Đừng nhầm ExecutorChannel với durable message broker.** Một ExecutorChannel thường thực thi trong **memory của JVM**; nếu process crash sau khi request đã được chấp nhận nhưng trước khi task chạy, công việc có thể mất. Virtual threads chỉ thay execution threads, không tăng độ bền.

### 12.1. Transaction không tự vượt channel

Với `DirectChannel`, downstream handlers có thể thực thi trên cùng caller thread. Với `ExecutorChannel`, downstream handler chạy trên thread khác; một thread-bound Spring transaction từ caller **không tự được chuyển** sang đó.

Nếu business flow yêu cầu atomic “ghi order và ghi outgoing event intent”, phải thực hiện cả hai trên cùng SQL transaction **trước khi** chuyển async; sau đó xử lý và retry từ durable outbox.

### 12.2. Error channel và async failures

Một exception xảy ra ở background handler có thể không trở lại HTTP caller như exception đồng bộ. Cần trả kết quả “accepted for processing” trung thực, ghi status vào database, dùng `errorChannel` và error handlers, và đo failures/parking queue riêng. Không trả “đã hoàn thành” chỉ vì task đã được submit.

## 13. Pinning của virtual threads trong Java 21

Virtual thread thường **unmount** khi chờ I/O được JDK hỗ trợ. Nhưng trên Java 21, một số tình huống khiến virtual thread bị **pinned** vào carrier khi block. Hai nguồn quan trọng:

1. Blocking operation thực hiện khi virtual thread đang ở trong `synchronized` method/block.
2. Một số native/foreign function calls hoặc runtime operations không thể unmount.

**Pinning không nhất thiết sai** nếu critical section cực ngắn. Nó đáng lo khi một virtual thread **block lâu trong vùng pinned** khiến carrier không thể chạy thread khác.

### 13.1. Ví dụ dễ gây pinning trên Java 21

~~~java
public class UnsafeCatalogClient {

    private final CatalogGateway gateway;

    public UnsafeCatalogClient(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public synchronized CatalogDto load(String sku) {
        // Blocking HTTP trong synchronized method:
        // Java 21 virtual thread có thể pin carrier.
        return gateway.fetch(sku);
    }
}
~~~

Với 100 virtual threads, method này còn serialize mọi request vì monitor lock, chưa kể pinning nếu I/O block. Tách critical section bảo vệ in-memory state ra khỏi network call:

~~~java
public class SaferCatalogClient {

    private final CatalogGateway gateway;
    private long attempts;

    public SaferCatalogClient(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public CatalogDto load(String sku) {
        synchronized (this) {
            attempts++;
        }

        // Không giữ monitor khi thực hiện blocking I/O.
        return gateway.fetch(sku);
    }
}
~~~

Nếu cần đồng bộ hóa trạng thái lớn, dùng concurrency primitives phù hợp, giữ critical sections ngắn và không hold locks trong lúc gọi remote. Đổi `synchronized` thành `ReentrantLock` có thể giảm một nguồn monitor pinning trong Java 21, **nhưng vẫn có contention và lock-held latency**; không dùng lock để bọc network I/O.

### 13.2. Pinning không đồng nghĩa pool starvation

| Hiện tượng | Nguyên nhân | Tín hiệu |
| --- | --- | --- |
| **Carrier pinning** | Virtual thread block khi không thể unmount | JFR `jdk.VirtualThreadPinned`, trace pinned stacks |
| **JDBC pool starvation** | Quá nhiều tasks chờ mượn JDBC connection | Hikari active gần max, pending tăng |
| **HTTP pool starvation** | Chờ HTTP connection slot | Pool leased/max, pending acquire |
| **CPU saturation** | Các threads làm computation | CPU gần max, runnable work tăng |
| **Partner overload** | Downstream rate/concurrency giới hạn | 429/503, latency tăng |
| **Lock contention** | Nhiều threads chờ synchronized/ReentrantLock | Lock wait/blocked stacks |

Một ứng dụng có thể **không pin carrier** nhưng vẫn chết vì 50.000 virtual threads chờ Hikari pool. Không ưu tiên tối ưu pinning nếu bottleneck thật là database capacity.

### 13.3. Công cụ phát hiện pinning

Trên Java 21, có thể dùng JVM diagnostics:

~~~text
-Djdk.tracePinnedThreads=full
~~~

hoặc:

~~~text
-Djdk.tracePinnedThreads=short
~~~

Các options giúp in stack traces khi virtual thread bị pin trong những trường hợp được JDK hỗ trợ; sử dụng ở test/staging hoặc chẩn đoán có kiểm soát, vì có thể gây noise/overhead. Java Flight Recorder có event **`jdk.VirtualThreadPinned`** để tìm các blocking stacks đáng chú ý; cấu hình event/threshold và công cụ JFR theo JDK version.

**Version caveat:** Java 24 trở lên có thay đổi liên quan đến monitor pinning (JEP 491), nên kết luận “mọi `synchronized` + blocking sẽ pin” là đặc biệt gắn với **Java 21**; khi nâng JDK, phải đo lại theo đúng release. Native/foreign calls và các hình thức blocking khác vẫn cần được xem xét.

## 14. ThreadLocal, MDC và security context

Virtual threads hỗ trợ `ThreadLocal` như platform threads. Nhưng vì chúng có thể được tạo với số lượng lớn, những patterns vốn dựa vào thread pool nhỏ có thể trở nên đắt hoặc sai về ngữ nghĩa:

- Dùng `ThreadLocal` làm cache chứa object lớn cho mỗi thread.
- Giữ JDBC Connection/JPA EntityManager/Redis transaction state trong custom ThreadLocal tự quản lý.
- Dựa vào `InheritableThreadLocal` để truyền credentials qua nhiều async boundaries.
- Trông đợi SLF4J MDC/trace context tự copy khi `@Async` tạo thread khác.
- Dựa vào thread name/ID để làm business identity hoặc distributed lock.

### 14.1. Transaction context vẫn thread-bound

`@Transactional` qua Spring JDBC/JPA thường dùng thread-local resource bindings. Khi chuyển sang virtual thread khác, bạn có **thread khác**. Spring không tự chuyển transaction của caller sang task `@Async`.

Một `@Transactional` được áp trực tiếp lên method chạy trong virtual thread có thể **mở local transaction của chính thread đó**; nó không có nghĩa đã nhập vào transaction của caller.

### 14.2. MDC và trace context qua @Async

Nếu log có traceId/correlationId trong caller MDC, một task async có thể thiếu thông tin nếu executor không được cấu hình propagation. Có thể dùng `TaskDecorator` hoặc observability context propagation được hỗ trợ theo Spring/Micrometer version.

Ví dụ decorator minh họa chỉ truyền MDC (không tự truyền Spring transaction):

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Đây là ví dụ custom decorator; có thể đăng ký với executor hỗ trợ `setTaskDecorator(...)`. Production nên ưu tiên propagation từ Micrometer/Spring Observation khi phù hợp và không copy các secrets/PII không cần thiết vào MDC.

### 14.3. SecurityContext không đồng nghĩa workload identity

`SecurityContextHolder` có chiến lược thread-bound; context của user inbound HTTP không tự hợp lệ trên background worker. Nếu một async task thực sự xử lý dưới quyền user, phải xác định delegated security context theo policy/framework; nếu worker gọi OAuth2 Client Credentials, dùng **service identity** riêng thay vì chuyển tiếp access token của user vào job kéo dài.

Không để một virtual thread của tenant A vô tình dùng header/token/MDC tenant B vì context propagation/reset sai.

## 15. Cancellation, interruption và deadline

Một virtual thread có thể bị interrupt như thread thường. Nhưng **request interruption không tự undo remote side effect** hoặc rollback transaction đã commit.

### 15.1. Timeout của Future khác timeout của I/O

~~~java
try {
    InventoryRecord result =
            inventoryFuture.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    inventoryFuture.cancel(true);
    // Không thể kết luận Inventory API chưa xử lý request.
}
~~~

`Future.get(timeout)` giới hạn thời gian **caller chờ future**. `cancel(true)` yêu cầu interruption nếu task hỗ trợ, nhưng không bảo đảm HTTP request đã bị hủy ở remote, không rollback database đã commit. `CompletableFuture.orTimeout(...)` hoàn tất future theo timeout, nhưng cũng không mặc định hủy công việc I/O ở underlying client.

### 15.2. Phân biệt các deadline

| Deadline/timeout | Nơi áp dụng | Ý nghĩa |
| --- | --- | --- |
| Executor admission | Chờ được phép submit/start | Ngăn task queue/bulkhead wait vô hạn |
| Hikari connection timeout | Chờ JDBC connection | Chưa thực thi SQL khi chưa mượn được |
| HTTP pool acquisition | Chờ socket/route slot | Chưa gửi request khi chưa lấy connection |
| TCP connect/TLS | Kết nối và xác minh server | Không phải thời gian response |
| HTTP read/response | Chờ response | Remote có thể đã commit trước timeout |
| Broker publish confirm | Chờ broker acknowledgement | Không phải consumer processing |
| Business deadline | End-to-end command/event | Tổng thời gian được phép qua retries |
| Graceful shutdown timeout | Cho tasks đang chạy kết thúc | Không mặc định hủy remote side effect |

Một deadline tổng 3 giây nhưng mỗi lớp retry 3 lần × timeout 3 giây sẽ vượt SLA. Tính **remaining deadline budget** và giới hạn số attempts/callbacks.

### 15.3. Xử lý InterruptedException đúng

~~~java
try {
    if (!permits.tryAcquire(
            200, TimeUnit.MILLISECONDS)) {
        throw new DownstreamBusyException("busy");
    }
    try {
        return gateway.load();
    } finally {
        permits.release();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Operation interrupted", ex);
}
~~~

Trong code ứng dụng, không nuốt `InterruptedException` rồi tiếp tục retry vô hạn. Nhưng cancellation chỉ có ý nghĩa nếu driver/client và protocol có cơ chế hủy an toàn, vì remote request có thể đã được xử lý.

## 16. Structured concurrency và ScopedValue trên Java 21

Java 21 có **Structured Concurrency** (JEP 453) và **Scoped Values** (JEP 446) dưới dạng **preview features**. Những API này cho thấy hướng tiếp cận tổ chức child tasks, cancellation và contextual data rõ ràng hơn so với futures không có chủ.

Tuy nhiên, ở **Java 21**, chúng **không phải API stable mặc định** và yêu cầu preview enablement/đúng JDK. Các bản Java sau có thay đổi phiên bản API và trạng thái preview, nên một đoạn `StructuredTaskScope` từ blog Java 21 có thể không compile trên release mới.

Trong bài này, ví dụ production baseline dùng **`ExecutorService`, `CompletableFuture`, Spring TaskExecutor** và explicit resource boundaries. Khi áp dụng preview API vào dự án thật, phải pin JDK, bật preview theo build/runtime/test và có upgrade plan rõ.

### 16.1. Vì sao cấu trúc task quan trọng?

Một HTTP request gọi ba downstreams song song:

~~~text
Order request
  ├── Inventory lookup
  ├── Pricing lookup
  └── Tax lookup
       ↓
Join results or cancel remaining tasks on failure
~~~

Nếu một task fail, không nên bỏ lại hai tasks mồ côi đang chiếm HTTP permits. Dù dùng `CompletableFuture` hay structured concurrency, phải có quy tắc **ownership, deadlines, cancellation và result aggregation**.

### 16.2. Không tạo fire-and-forget vô chủ

~~~java
virtualExecutor.submit(() -> inventoryGateway.reserve(orderId));
return ResponseEntity.accepted().build();
~~~

Nếu chưa có durable work record, HTTP 202 chỉ có nghĩa JVM đã enqueue/submitted một task RAM. Process crash có thể mất work. Với tác vụ nghiệp vụ dài, **HTTP 202 phải gắn với durable operation ID/status** và worker có khả năng recovery, không chỉ một executor.

## 17. Thiết kế fan-out có kiểm soát

Tình huống: một request cần đọc tồn kho của nhiều SKU, mỗi SKU là blocking HTTP call.

Một cách tổ chức có cân bằng tài nguyên:

~~~mermaid
flowchart TD
    A["Request SKU list"] --> V["Validate count and input"]
    V --> C["Bounded fan-out orchestration"]
    C --> B["Inventory bulkhead max 24"]
    B --> H["RestClient / HTTP pool"]
    H --> I["Inventory API"]
    C --> D["Collect results / exceptions"]
    D --> R["Deadline + partial-failure policy"]
~~~

### 17.1. Vì sao chỉ executor per task là chưa đủ?

~~~java
try (var executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    for (String sku : skus) {
        executor.submit(() -> inventoryGateway.getStock(sku));
    }
}
~~~

Nếu `skus` có 100.000 phần tử, code tạo 100.000 tasks. Dù `getStock` có semaphore, các tasks còn lại vẫn có stack/context/payload và phải chờ. Thêm **bounded input size** và **admission policy** ở orchestration level để không tạo hàng nghìn tasks chờ không cần thiết.

### 17.2. Một batch orchestrator có giới hạn đầu vào

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InventoryBatchReader {

    private final InventoryGateway gateway;

    public InventoryBatchReader(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    public List<InventoryRecord> loadBatch(List<String> skus)
            throws InterruptedException, ExecutionException {

        if (skus.isEmpty() || skus.size() > 24) {
            throw new IllegalArgumentException(
                    "Mỗi batch cần 1..24 SKU");
        }

        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<InventoryRecord>> futures =
                    new ArrayList<>();

            for (String sku : skus) {
                futures.add(executor.submit(
                        () -> gateway.getStock(sku)));
            }

            List<InventoryRecord> results = new ArrayList<>();
            for (Future<InventoryRecord> future : futures) {
                results.add(future.get());
            }
            return results;
        }
    }
}
~~~

Đây là ví dụ **fan-out hữu hạn** trong một batch. Với traffic đa request, `InventoryGateway` phải có bulkhead dùng chung ở cấp application như mục 8; nếu không 100 requests × 24 SKU vẫn gây 2.400 simultaneous HTTP calls.

**Hạn chế của ví dụ:** Khi một `future.get()` fail, tasks khác có thể vẫn chạy cho tới khi executor được đóng; `try-with-resources` có thể chờ chúng hoàn tất. Production cần tổng deadline và cancel remaining futures khi phù hợp, đồng thời hiểu cancellation không undo remote side effect.

### 17.3. Nếu muốn hàng triệu items thì làm gì?

- Paginate/chunk input.
- Lưu progress/checkpoint bền vững.
- Dùng bounded worker concurrency.
- Bulk HTTP APIs khi partner hỗ trợ.
- Giữ retry queue/DLQ cho failed items.
- Có per-item operationId/idempotency.
- Tách long-running job khỏi HTTP request timeout.
- Đo backlog age, completed/retry/failed/unknown.

Không tạo một virtual thread cho toàn bộ vài triệu rows rồi chờ qua đêm mà không có durability/recovery.

## 18. Transactional outbox và async task durability

Virtual threads là **runtime execution primitive**; chúng không lưu công việc qua process restart. Với business command cần bảo đảm eventual delivery, dùng transactional outbox:

~~~mermaid
sequenceDiagram
    participant A as HTTP Command
    participant D as PostgreSQL
    participant W as Outbox Worker
    participant P as External Partner
    A->>D: BEGIN update order + INSERT outbox intent
    D-->>A: COMMIT
    A-->>A: Return accepted with operationId
    W->>D: Claim due outbox row
    W->>P: Send idempotent request
    P-->>W: Confirm / reject / timeout
    W->>D: Persist outcome or retry lease
~~~

### 18.1. Outbox bảo vệ điều gì?

Outbox bảo vệ việc **business state commit nhưng công việc async chưa được gửi**. Nếu HTTP request/process crash sau SQL COMMIT, worker khác vẫn tìm được row `PENDING` để xử lý.

Outbox **không tự cung cấp exactly-once delivery**. Nếu partner đã nhận rồi response mất, worker có thể retry. Sử dụng stable `eventId`/`operationId`, partner idempotency keys hoặc status reconciliation.

### 18.2. SQL transaction ngắn, network call ngoài transaction

~~~java
@Transactional
public String acceptOrder(OrderCommand command) {
    orderRepository.createOrder(command);
    String operationId = operationIds.newId();
    outboxRepository.insert(operationId, command);
    return operationId;
}
~~~

Sau transaction, worker xử lý. Snippet giả định `OrderCommand`, `operationIds` và repositories được định nghĩa trong ứng dụng; lưu command vào outbox dưới schema/version và mã hóa phù hợp. **Không gọi HTTP partner trong transaction** hoặc đẩy `@Async` trực tiếp rồi mong JVM luôn sống.

### 18.3. Inbox bảo vệ consumer redelivery

Nếu RabbitMQ/Kafka consumer sử dụng virtual threads cho business handler, message vẫn có thể bị phát lại khi DB COMMIT xong nhưng consumer ACK thất bại. Dùng inbox table có unique `(consumerName,eventId)` và business update trong **cùng SQL transaction**.

Không dùng `ThreadLocal<Set<eventId>>` hoặc in-memory concurrent map làm dedupe bền vững; process mới không có lịch sử.

## 19. Kịch bản capacity budget thực tế

Giả sử có 6 pods Order Service:

| Tài nguyên | Giới hạn mỗi pod | Tổng gần đúng | Rủi ro nếu mở rộng mù |
| --- | ---: | ---: | --- |
| Hikari JDBC connections | 12 | 72 | PostgreSQL hết connections/locks tăng |
| Inventory HTTP concurrent calls | 24 | 144 | Partner rate-limit/503 |
| RabbitMQ listener consumers | 4 | 24 | Unacked tăng, DB overload |
| Prefetch mỗi Rabbit consumer | 10 | Có thể ~240 in flight | Nhiều redelivery sau crash |
| Inbound virtual threads | Theo workload | Có thể rất lớn | Memory/backlog nếu không có admission limit |

Các con số chỉ minh họa. Một pod có 24 Inventory permits không có nghĩa 24 physical HTTP sockets trong mọi transport: HTTP/2 multiplexing, connection reuse và per-route limits có semantics riêng.

### 19.1. Theo dõi bottleneck ở từng tầng

~~~mermaid
flowchart TD
    A["Latency tăng"] --> B{"Ở tầng nào?"}
    B --> C["Carrier pinning / CPU?"]
    B --> D["JDBC pool pending?"]
    B --> E["HTTP pool pending / 429?"]
    B --> F["Rabbit unacked / Kafka lag?"]
    B --> G["Heap/GC / too many tasks?"]
    C --> H["JFR / thread dumps"]
    D --> I["Reduce tx duration / SQL tuning"]
    E --> J["Bulkhead/rate-limit/timeouts"]
    F --> K["Consumer concurrency/idempotency"]
    G --> L["Bound input and queued work"]
~~~

Không chỉ nhìn số virtual threads rồi kết luận JVM “chậm”. Nếu thread count lớn nhưng CPU thấp và Hikari pending tăng, lỗi chính là **DB capacity hoặc transaction duration**.

### 19.2. Budget khi partner có 100 QPS

Nếu Inventory cung cấp quota **100 requests/giây cho toàn bộ client identity**, sáu pods cùng permit 24 chưa đủ: có thể tạo QPS vượt 100 nếu calls nhanh. Cần distributed rate-limit/quota allocation, hoặc per-pod budget bảo thủ dựa trên autoscaling và partner SLA. Semaphore chỉ giới hạn concurrency, **không giới hạn QPS**.

## 20. Kiểm thử virtual thread và giới hạn tài nguyên

### 20.1. Kiểm tra JVM thật sự dùng virtual thread

Unit test Java 21:

~~~java
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class VirtualThreadTest {

    @Test
    void runsOnVirtualThread() throws Exception {
        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            boolean virtual = executor.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            assertTrue(virtual);
        }
    }
}
~~~

Test này chỉ xác nhận JDK executor, **không chứng minh Spring `@Async` được wiring đúng**.

### 20.2. Test @Async qua Spring proxy

Tạo service có:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ThreadInspectionService {

    @Async("inventoryTaskExecutor")
    public CompletableFuture<Boolean> isVirtual() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().isVirtual());
    }
}
~~~

Trong Spring test context đã bật `@EnableAsync` và có named `inventoryTaskExecutor`, inject `ThreadInspectionService` bean rồi gọi:

~~~java
boolean virtual = service.isVirtual().get();
assertTrue(virtual);
~~~

Nếu gọi `new ThreadInspectionService()` hoặc self-invocation, sẽ không kiểm thử Spring proxy. Với Boot property auto-config, test thêm trường hợp không có custom executor để xác minh default bean của version đang dùng.

### 20.3. Load test giới hạn HTTP và JDBC

Dùng MockWebServer/WireMock cho HTTP (khi cần TLS thật, dùng TLS-enabled test server), PostgreSQL Testcontainers cho SQL và tool load test có giới hạn:

1. Tạo 200 tasks chờ I/O với bounded input.
2. Hikari max 8, HTTP bulkhead 16.
3. Đo max active/pending/timeout; không giả định 200 SQL transactions chạy đồng thời.
4. Chèn partner latency 300–1000 ms, lỗi 429/503.
5. Xác minh admission limit và retry budget.
6. Không có permit leak khi exception/interruption.
7. Không có infinite queue hoặc OOM khi burst.
8. Khi process stop/restart, outbox giữ các tasks chưa hoàn thành.

**Không test sức chịu tải trên production partner** khi chưa có quyền và quota. Dùng synthetic data, test tenants/queues và môi trường riêng.

### 20.4. Test pinning Java 21

Tạo một tình huống `synchronized` + blocking HTTP test server để xác minh pinning traces/JFR và so sánh khi tách blocking I/O ra khỏi monitor. Không biến kết luận benchmark ngắn thành khẳng định tổng quát: warmup, GC, CPU core count, carrier scheduler và driver version đều ảnh hưởng.

### 20.5. Test async boundaries và transaction

Một test cần chứng minh:

~~~text
Given SQL transaction đang mở
When caller submit @Async task
Then task không được giả định nhìn thấy uncommitted data
And task không nằm trong caller transaction
~~~

Nên thiết kế lại thành outbox/after-commit workflow nếu cần bảo đảm. `TransactionSynchronization.afterCommit()` có thể trì hoãn submit đến sau commit, nhưng **vẫn không bền** khi process crash sau commit trước submit; outbox đáng tin hơn cho critical work.

### 20.6. Test broker ACK timing

Với RabbitMQ/Kafka Testcontainers:

- Đảm bảo listener không ACK/commit offset trước khi business transaction hoặc durable handoff hoàn thành.
- Simulate DB COMMIT rồi crash trước ACK → redelivery được inbox dedupe.
- Simulate listener error/poison message → retry/DLQ đúng.
- Virtual thread use không làm mất ordering per partition/aggregate.
- Graceful shutdown không đánh dấu pending work là success.

## 21. Observability và diagnostics

### 21.1. JVM/JFR metrics

Các tín hiệu đáng quan sát:

| Tín hiệu | Điều muốn biết |
| --- | --- |
| JFR `jdk.VirtualThreadPinned` | Virtual thread block khi carrier bị pin |
| Carrier/CPU saturation | Số runnable tasks so với CPU cores |
| Heap allocation/GC | Chi phí nhiều tasks/ThreadLocal/payload |
| Thread dump/stack traces | I/O wait vs lock wait vs deadlock |
| Executor active/admission wait | Bao nhiêu tasks chờ vào bulkhead |
| Request p95/p99 latency | Trễ end-to-end |
| Error/timeout count | Deadline, rate limit, overload |

Một số APIs/monitoring của Java 21 truyền thống không phản ánh virtual threads giống OS/platform thread count. Dùng JFR, JVM thread dumps hỗ trợ virtual threads và instrumentation phù hợp, không chỉ dựa vào platform `ThreadMXBean` count.

### 21.2. External resource metrics

| Metric | Chẩn đoán |
| --- | --- |
| `hikaricp.connections.active` | JDBC connections đang được dùng |
| `hikaricp.connections.pending` | Tasks chờ connection |
| `hikaricp.connections.timeout` | Pool acquisition failures |
| HTTP connection pool leased/pending | HTTP bottleneck |
| HTTP 429/503 và response latency | Partner quota/overload |
| Redis command latency/errors | Cache/backend bottleneck |
| Kafka consumer lag/commit failures | Backlog, processing/commit issues |
| RabbitMQ ready/unacked/consumers | Queue pressure, ACK timing |
| Outbox pending oldest age | Việc tích hợp bền vững chưa hoàn tất |
| Inbox duplicate count | Replay đã được xử lý idempotently |
| End-to-end business completion lag | Thời gian thật tới downstream success |

Tên metric thực phụ thuộc Micrometer/Actuator/driver và cấu hình export; không mặc định pool metrics có sẵn nếu custom HTTP transport chưa được instrument.

### 21.3. Trace đúng ranh giới

Một trace hữu ích có spans:

~~~text
HTTP Order Command
  -> SQL transaction / save order + outbox
  -> outbox relay attempt
       -> OAuth2 token acquisition (nếu cần)
       -> Inventory HTTP / connection wait
       -> broker publish ACK
  -> consumer delivery
       -> inbox dedupe + SQL commit
       -> consumer ACK
~~~

Virtual threads làm thay đổi thread execution, **không thay nghĩa của trace parent-child**. Cần propagation qua async boundaries và broker headers theo policy; không đưa secrets/PII vào span attributes.

## 22. Runbook khi bật virtual threads và thấy lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Cần kiểm tra |
| --- | --- | --- |
| Throughput không tăng | Database/partner/broker bottleneck | Hikari pending, HTTP pool/429, broker lag |
| CPU 100% dù nhiều virtual threads | CPU-bound tasks/JSON processing | CPU profiling, serialization, cores |
| p99 tăng mạnh | Quá nhiều tasks chờ pool | Bulkhead/admission latency |
| OOM sau bật virtual threads | Không giới hạn tasks/payload/ThreadLocal | Heap, task count, memory per task |
| Hikari timeout | JDBC pool exhausted/long transaction | Transaction duration, SQL locks |
| HTTP 429/503 tăng | Partner quota/concurrency limit | Rate limiter, QPS, bulkhead |
| JFR pinned events tăng | `synchronized` + blocking I/O/native call | JFR stack traces, JDK version |
| @Async không chạy virtual | Custom platform executor, thiếu proxy/EnableAsync | Bean selection, `isVirtual()` |
| Self-invocation @Async | Bỏ qua Spring proxy | Bean separation/explicit executor |
| @Scheduled job-only app tự thoát | Chỉ có daemon virtual threads | `spring.main.keep-alive`/lifecycle |
| Batch job chạy tuần tự dù bật VT | Fixed-delay semantics/scheduler | `SimpleAsyncTaskScheduler` fixed-delay behavior |
| Missing MDC/trace ID | Không propagate context qua task | TaskDecorator/Observation |
| SQL transaction không chia sẻ | Thread-bound context khác nhau | Transaction boundary/outbox |
| Rabbit unacked tăng | Handler treo, prefetch/ACK sai | Container concurrency, DB pool |
| Kafka data lệch thứ tự | Async offload rồi commit progress sớm | Per-partition ordering/ack policy |
| HTTP timeout nhưng remote có side effect | Unknown outcome | Idempotency/status lookup |
| Process restart mất async jobs | Executor RAM không durable | Outbox/work table/broker |

### 22.1. Không sửa bằng cách tăng tất cả giới hạn

Nếu sau khi bật virtual threads, Inventory 503 tăng, đừng tăng đồng thời HTTP pool, Hikari max và consumer concurrency. Hãy:

1. Xác định resource bottleneck bằng metrics.
2. Giảm concurrency ở boundary gây quá tải.
3. Thiết lập fail-fast/backpressure và bounded retries.
4. Đo lại p95/p99/error rate/throughput.
5. Tính tổng theo replicas.
6. Chỉ tăng limits khi downstream capacity thực sự cho phép.

## 23. Các anti-pattern cần tránh

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| Tạo hàng triệu virtual threads cho input chưa phân trang | Heap/task backlog tăng vô hạn | Bounded batches/admission |
| Dùng virtual threads cho CPU-bound rồi mong tăng tốc | CPU cores không tăng | CPU-sized executors/profiling |
| Pool virtual threads chỉ vì thread phải “tái sử dụng” | Sai mô hình thread-per-task | New virtual thread per task + resource bulkhead |
| Tăng Hikari pool lên hàng nghìn khi bật VT | DB không có thêm capacity | DB budget và short transactions |
| Giữ SQL transaction khi chờ HTTP | Chiếm JDBC connections/locks | Outbox/saga |
| `synchronized` bọc blocking network I/O trên Java 21 | Pin carriers và serialize requests | Short critical sections |
| `@Async` self-invocation | Proxy không chạy | Cross-bean call |
| `@Async void` nuốt lỗi | Không có future xử lý failure | CompletableFuture/error handler |
| ThreadLocal làm cache dữ liệu lớn | Mỗi virtual thread giữ memory | Shared bounded cache |
| Dùng user token từ HTTP request trong job lâu | Expiry/authorization leak | Service identity/delegation rõ |
| Gửi Kafka record vào executor rồi commit offset sớm | Mất/đảo thứ tự khi crash | Durable handoff/controlled ack |
| Rabbit AUTO ACK khi chỉ submit task RAM | Message bị loại trước khi thực hiện | Durable work/async ack semantics |
| `Future.get(timeout)` rồi kết luận remote chưa xử lý | Timeout không rollback remote | Idempotency/reconciliation |
| Dùng `ExecutorChannel` làm durable queue | JVM crash mất tasks | Broker/outbox/work table |
| Bật virtual threads cho WebFlux rồi gọi `block()` trên event loop | Event-loop blocking | Reactive pipeline hoặc offload có chủ đích |
| Giữ task không cancel sau request failure | Orphan tasks, HTTP permits còn giữ | Ownership/cancellation/deadline |
| Tính success theo số submitted tasks | Submission không phải completion | Business outcome metrics |
| Test bằng mocks rồi kết luận concurrency an toàn | Không test pool/broker/transaction | Testcontainers/load tests |

## 24. Checklist trước khi triển khai Java 21 virtual threads

- [ ] Dự án chạy Java 21, Spring Boot/Spring Framework version hỗ trợ cấu hình virtual threads.
- [ ] Đã xác minh executor/HTTP request handler thật sự chạy virtual thread bằng `isVirtual()`.
- [ ] Không giả định Kafka/Rabbit/WebFlux native threads tự chuyển sang virtual threads.
- [ ] @Async có `@EnableAsync`, qua Spring proxy và executor rõ ràng.
- [ ] Các task nền có lifecycle/shutdown và `spring.main.keep-alive` khi cần.
- [ ] Đã đo hiệu quả trên blocking I/O, không chỉ CPU benchmark.
- [ ] Không làm blocking I/O dưới `synchronized` trên Java 21, theo dõi JFR pinning.
- [ ] ThreadLocal/MDC/security context propagation được thiết kế và cleanup an toàn.
- [ ] JDBC Hikari max, HTTP pool max, Redis, broker consumer concurrency có capacity budget.
- [ ] Có bounded admission, semaphore/bulkhead và rate limiter cho partner quotas.
- [ ] Có timeout phân tầng và deadline tổng; retry không nhân attempts vô hạn.
- [ ] Transaction không bị giả định tự chuyển sang @Async thread.
- [ ] Không ACK Kafka/Rabbit trước business commit hoặc durable handoff.
- [ ] Critical tasks được ghi bền bằng outbox/work table/broker, không chỉ executor RAM.
- [ ] EventId/operationId ổn định, inbox/idempotency bảo vệ replay.
- [ ] Có cancellation/interrupt handling, không coi timeout là remote failure chắc chắn.
- [ ] Đã test resource exhaustion, 429/503, connection wait, pinning, broker redelivery.
- [ ] Có metrics cho CPU, JFR pinned events, Hikari, HTTP pool, queue backlog và business lag.
- [ ] Secrets/PII không nằm trong ThreadLocal caches, logs, trace tags hoặc broker payload ngoài contract.
- [ ] Đã kiểm tra tổng limits trên tất cả replicas và scaling policy.

**Ghi nhớ:** **Virtual threads Java 21 làm cho chờ I/O rẻ hơn về platform threads**, nên mô hình code blocking dễ mở rộng hơn trong nhiều tình huống. Nhưng chúng không tạo thêm connections trong HikariCP, không tăng quota HTTP partner, không sửa vấn đề Redis cache stampede, không thay Kafka/Rabbit consumer ACK và không tạo distributed transaction. Tích hợp Spring Boot an toàn phải giới hạn tài nguyên **ở đúng downstream boundary**, duy trì **transaction ngắn, durable async handoff, idempotency, retry có giới hạn và observability**.

## Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): Java 21 virtual threads, design và semantics.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): tạo/quan sát virtual threads và áp dụng.
- [Oracle Java 21 — Virtual Thread Scheduler](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html#GUID-BB3B8D10-01D6-4B63-96EC-885F3209C7C4): carrier scheduler và blocking.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi monitor pinning ở Java sau 21.
- [JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453): Java 21 structured concurrency preview.
- [JEP 446 — Scoped Values (Preview)](https://openjdk.org/jeps/446): contextual data theo scope, preview trong Java 21.
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): `spring.threads.virtual.enabled`, task execution/scheduling.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `@Scheduled`, executor và scheduler.
- [Spring Framework — SimpleAsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html): virtual thread support và concurrency throttle.
- [Spring Framework — Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): thread-bound transaction boundary.
- [Spring Boot — DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): HikariCP và pool sizing.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, WebClient và HTTP transport.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): channels, asynchronous boundaries và error handling.
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): consumer/offset/ack lifecycle.
- [Spring AMQP — Listener Containers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): consumer channels, prefetch và ACK.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): connection pool limits và timeouts.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate delivery và consumer safety.
