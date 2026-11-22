# Phân biệt tối ưu luồng nền tảng, luồng ảo và mô hình reactive trong Spring Boot

Một web server có thể phục vụ hàng trăm đến hàng nghìn request đồng thời, nhưng cách mỗi request chờ database, HTTP client, filesystem hoặc CPU tạo ra những giới hạn rất khác nhau. Trong Java/Spring Boot hiện đại có ba hướng thường được đặt cạnh nhau:

1. **Luồng nền tảng (platform threads)**: các Java Thread gắn với luồng hệ điều hành; thường chạy theo **pool có số lượng giới hạn**, ví dụ worker threads của Tomcat trong Spring MVC.
2. **Luồng ảo (virtual threads, Project Loom)**: Java Thread nhẹ do JVM lập lịch lên một số carrier platform threads, phù hợp với phong cách code **đồng bộ và blocking I/O** nhưng muốn xử lý nhiều tác vụ đang chờ đồng thời.
3. **Mô hình reactive (Spring WebFlux + Project Reactor)**: ứng dụng biểu diễn công việc bằng **Mono/Flux**, non-blocking I/O và event loops/schedulers, đồng thời có giao thức **demand/backpressure** để quản lý luồng dữ liệu.

Điểm cốt lõi: **virtual threads không biến blocking API thành reactive**, còn **reactive không phải chỉ là dùng nhiều thread hơn**. Cả hai đều có thể tăng khả năng phục vụ I/O-bound workloads nhưng không tự tạo CPU, database connections, memory, network bandwidth hoặc downstream capacity. Với ứng dụng đang chạy ổn định, tối ưu platform thread pool và tài nguyên phía sau có thể đem lại kết quả tốt hơn việc đổi framework.

Bài thuộc **Spring Boot - web-runtime → Hiệu năng và giới hạn**. Phần so sánh được neo vào **Spring Boot 3.3.13, Java 21, Spring MVC trên embedded Tomcat và Spring WebFlux trên Reactor Netty**. Java 17 đủ cho nhiều ứng dụng MVC/WebFlux, nhưng **virtual threads cần Java 21+**. Các ví dụ có project Maven độc lập, test qua HTTP thật, một chương trình Java 21 để xem tác dụng của chờ I/O, và quy trình benchmark/profile. Không có kết luận framework nào luôn nhanh nhất.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích **OS thread, Java platform thread, virtual thread, carrier thread, event loop, task, blocking I/O, non-blocking I/O, CPU-bound, I/O-bound**.
- Phân tích điểm nghẽn bằng **throughput (RPS), latency p50/p95/p99, concurrency, queue time, CPU, heap, GC, số thread, connection pool**.
- Biết khi nào nên tối ưu **server.tomcat.threads.max/min-spare**, accept queue, connection limits, connection/timeouts và downstream pools.
- Dùng **spring.threads.virtual.enabled=true** trên Java 21 với Spring Boot 3.3, quan sát **Thread.currentThread().isVirtual()** trong controller, và biết giới hạn pinning của JDK 21.
- Giải thích vì sao **không pool virtual threads**, không bọc chúng trong một semaphore vô cớ, và vì sao vẫn cần giới hạn concurrency truy cập database/remote APIs.
- Viết endpoint **Spring MVC blocking** và **Spring WebFlux non-blocking** có cùng contract HTTP để so sánh.
- Phân biệt **Mono/Flux, subscribe, publishOn, subscribeOn, Schedulers.boundedElastic, backpressure, cancellation** và những lỗi khi dùng block()/Thread.sleep() trên event loop.
- Hiểu việc thêm **spring-boot-starter-webflux** vào ứng dụng đã có **spring-boot-starter-web** không tự chuyển toàn app thành WebFlux.
- Thiết kế thí nghiệm hiệu năng có kiểm soát, không kết luận chỉ từ một lần chạy hoặc endpoint sleep giả lập.
- Lựa chọn mô hình theo thư viện I/O thực tế, độ phức tạp, SLO, khả năng vận hành và chi phí migration.

## 2. Đầu tiên phải xác định workload

### 2.1. CPU-bound và I/O-bound là hai bài toán khác nhau

**CPU-bound**: thời gian xử lý chủ yếu dùng CPU, ví dụ nén dữ liệu, mã hóa, parse lớn, tính toán hình ảnh. Khi CPU đã bão hòa, tăng số thread hoặc chuyển sang virtual thread có thể làm context switching, contention hoặc memory tăng mà throughput không cải thiện.

**I/O-bound**: phần lớn wall-clock time dành để chờ database, network, filesystem hoặc external API. Trong khi một request đang chờ, CPU có thể rảnh nhưng platform request thread bị giữ. Virtual threads hoặc reactive non-blocking APIs có thể giảm chi phí giữ rất nhiều công việc đang chờ.

~~~text
Request A trên platform thread:
[CPU 5 ms] [waiting DB 200 ms] [CPU 5 ms]
             ^ thread còn bị chiếm

Request A trên virtual thread:
[CPU 5 ms] [waiting DB 200 ms] [CPU 5 ms]
             ^ virtual thread thường unmount,
               carrier có thể chạy request khác

Request A với reactive non-blocking client:
[CPU 5 ms] [async DB/network] [CPU callback 5 ms]
             ^ không giữ worker thread trong lúc đợi;
               completion signal kích hoạt operator tiếp theo
~~~

Đây là sơ đồ khái niệm. Virtual thread **không phải lúc nào cũng unmount** (pinning hoặc native code có thể cản); reactive code **không nhất thiết non-blocking** nếu bên trong gọi JDBC/Thread.sleep/block().

### 2.2. Throughput, latency và concurrency

- **Throughput/RPS**: số request hoàn thành trên mỗi giây, dưới một mức tải nhất định.
- **Latency**: thời gian một request trải qua từ phía client hoặc server. Nên nhìn **p50/p95/p99**, không chỉ average.
- **Concurrency**: số request/tác vụ đang đồng thời in-flight, có thể đang tính toán, chờ I/O hoặc chờ hàng đợi.
- **Queue time**: thời gian request chờ worker/connection trước khi được xử lý.
- **Utilization**: CPU, request worker threads, DB pool, network connections và memory.

Theo **Little's Law** ở trạng thái ổn định, số yêu cầu in-flight trung bình gần bằng **arrival rate × thời gian ở hệ thống**:

\[
L = \lambda W
\]

Nếu 200 request/giây có thời gian trung bình 0,2 giây, hệ thống cần duy trì khoảng **40 request in-flight**. Đây là một ước lượng concurrency, không phải tuyên bố cần 40 CPU cores hoặc 40 DB connections. Request có thể chủ yếu đang chờ.

**Chọn mô hình mà không đo workload là tối ưu mù.** Hãy đo thời gian CPU, JDBC, HTTP client, queue, serialization và lock trước khi đổi thread model.

### 2.3. Cùng một endpoint nhưng ba kiểu chờ

| Mô hình | Cách biểu diễn request đang chờ | Nguy cơ chính |
| --- | --- | --- |
| MVC + platform threads | Giữ một worker thread khi gọi blocking API | Pool cạn; hàng đợi chờ; nhiều OS threads tốn memory. |
| MVC + virtual threads | Giữ virtual thread; khi unmount carrier có thể làm việc khác | Pinned carrier, quá nhiều in-flight tasks, downstream pool/sockets bị quá tải. |
| WebFlux + reactive clients | Dòng signal/continuation; non-blocking I/O không giữ worker tương ứng | Chặn event loop, buffer quá lớn, operator concurrency không giới hạn, khó debug context. |

## 3. Platform threads: truyền thống nhưng không lỗi thời

### 3.1. Luồng nền tảng là gì?

Một **platform thread** trong Java thường là wrapper mỏng quanh một **OS thread**, có stack và chi phí scheduling/resource của hệ điều hành. Các thread này phù hợp cho cả blocking và CPU work, nhưng không thể tăng vô hạn. Vì thế web server truyền thống dùng **pool tái sử dụng** thay vì tạo một OS thread mới cho mọi request.

Trong Spring MVC Servlet trên embedded Tomcat, request được tiếp nhận qua connector, đưa tới worker executor để chạy filter/DispatcherServlet/controller. Khi controller gọi blocking JDBC hoặc một HTTP client đồng bộ, worker thread thường bị giữ cho đến khi operation hoàn tất.

~~~text
Tomcat acceptor / network connector
              |
              v
Worker pool: [P1] [P2] [P3] ... [P16]
              |
              +-- P1 xử lý request A, chờ DB
              +-- P2 xử lý request B, chờ REST API
              +-- P3 xử lý request C, dùng CPU
              ...
              |
Requests vượt khả năng phục vụ -> queue/connection pressure
~~~

### 3.2. Các cấu hình Tomcat quan trọng

Với Spring Boot 3.3, một ví dụ giới hạn trong lab:

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 16
      min-spare: 4
    max-connections: 256
    accept-count: 100
~~~

- **server.tomcat.threads.max**: số worker threads tối đa theo mô hình Tomcat platform thread executor được Boot quản lý.
- **min-spare**: số worker tối thiểu duy trì tùy executor, không phải giới hạn request toàn hệ thống.
- **max-connections**: ngưỡng kết nối connector chấp nhận; khác số request active và khác database pool size.
- **accept-count**: mức backlog/queue khi connector đã tới giới hạn phù hợp; behavior thực tế còn tùy OS/socket implementation.

Không hiểu **max-connections=256** có nghĩa Tomcat có 256 threads hoặc cho 256 request đồng thời chạy handler. HTTP keep-alive kết nối có thể idle, HTTP/2 còn multiplex streams; thread pool và request concurrency không phải cùng một đại lượng.

Khi kích hoạt virtual threads trong Boot, cấu hình pool workers như **server.tomcat.threads.max** không còn là cùng một cơ chế giới hạn mỗi request như khi dùng platform pool. Một số giới hạn connector/network khác vẫn cần được đánh giá.

### 3.3. Tuning đúng thứ tự

Trước khi tăng maxThreads:
1. Đo CPU: nếu CPU 100% liên tục, tăng thread có thể làm chậm hơn.
2. Đo Tomcat busy/current threads và request queue time.
3. Đo HikariCP connection active/idle/pending, DB slow queries và lock waits.
4. Đo outbound HTTP client connection pool, timeout, retry và downstream error rate.
5. Đo memory, GC, filesystem, TLS và serialization overhead.
6. Xác định p95/p99 latency và điểm bắt đầu của saturation.
7. Chỉ sau đó thử điều chỉnh threads, maxConnections, acceptCount và autoscaling.

Ví dụ một service có 16 Tomcat workers nhưng chỉ **8 database connections**, tăng worker pool lên 200 có thể chỉ làm thêm 192 tác vụ chờ DB pool, tăng queue, memory và timeout. Nếu DB là bottleneck, phải tối ưu queries/indexes/transactions, connection acquisition timeout và backpressure/admission control thay vì đổ lỗi Tomcat.

### 3.4. Điều chỉnh thread pool không phải một phép tăng throughput tuyến tính

Khi một request giữ worker trong 300 ms mà CPU thực chỉ chạy 10 ms, tăng concurrency có thể giúp sử dụng CPU rảnh hiệu quả hơn, tới khi bottleneck mới xuất hiện. Nhưng nếu tăng đến mức gây 1000 concurrent DB queries trên một DB đang tải cao, hệ thống có thể mất ổn định.

Các dấu hiệu over-tuning:
- p99 tăng mạnh dù throughput không tăng;
- timeouts và 503 tăng ở phía client;
- hàng đợi DB connection/pool tăng;
- JVM có quá nhiều threads và context switches;
- GC pauses và memory pressure tăng;
- downstream rate limit hoặc circuit breaker mở hàng loạt.

## 4. Virtual threads: mô hình blocking code với thread nhẹ

### 4.1. Java 21 là yêu cầu tối thiểu

Virtual threads trở thành tính năng chính thức trong **Java 21 (JEP 444)**. Một virtual thread vẫn là **java.lang.Thread**, nên code phổ biến như:

~~~java
Thread.currentThread();
Thread.sleep(250);
Thread.currentThread().isVirtual();
~~~

vẫn tồn tại với cùng phong cách lập trình. Điểm khác là JVM lên lịch virtual thread lên một **carrier platform thread**, và với các blocking operations được runtime hỗ trợ, virtual thread **unmount** để carrier có thể chạy tác vụ khác.

~~~text
Virtual threads: V1 V2 V3 V4 V5 V6 ... V1000
                  \ | /  \ | /
Carrier threads:  C1     C2     C3 ...
                (platform/OS threads)
~~~

Đừng hiểu là 1000 virtual threads đồng nghĩa 1000 OS threads. Scheduler có tập carrier giới hạn; số lượng virtual threads có thể nhiều hơn carriers rất lớn khi phần lớn đang chờ I/O.

### 4.2. Virtual threads tăng khả năng mở rộng concurrency, không làm tác vụ CPU nhanh hơn

Nếu mỗi request cần 100 ms CPU tính toán thực, virtual threads không giảm 100 ms đó. CPU cần đủ cores để chạy công việc. Nếu mỗi request chờ external API 500 ms, virtual threads giúp server giữ nhiều request đang đợi mà không phải giữ một platform thread riêng cho mỗi request.

**Virtual threads vẫn dùng heap, stack chunks, ThreadLocal, sockets và các dependencies.** Không có chuyện mỗi virtual thread hoàn toàn miễn phí hoặc số request concurrent vô hạn.

### 4.3. Không pool virtual threads

Cách dùng JDK 21 phù hợp là **một virtual thread cho một task**, chẳng hạn:

~~~java
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> {
        System.out.println(Thread.currentThread().isVirtual());
    }).get();
}
~~~

Đây là snippet sử dụng Java 21; stdout của task là:

~~~text
true
~~~

**Không tạo một fixed-size pool chứa 100 virtual threads rồi dùng nó như Tomcat worker pool truyền thống.** Điều đó loại bỏ lợi ích quản lý concurrency rẻ hơn của virtual threads. Nếu cần giới hạn truy cập một dependency, dùng **Semaphore, rate limiter, bulkhead hoặc connection pool** cho resource đó, chứ không pool threads chỉ để giới hạn số lượng thread.

### 4.4. Chương trình Java 21 độc lập: platform vs virtual khi chờ

Tạo file **ThreadModelsMain.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadModelsMain {

    private static void run(
            String label, ExecutorService executor)
            throws Exception {

        long start = System.nanoTime();
        try (executor) {
            List<Future<Boolean>> futures = new ArrayList<>();

            for (int i = 0; i < 40; i++) {
                futures.add(executor.submit(() -> {
                    Thread.sleep(200);
                    return Thread.currentThread().isVirtual();
                }));
            }

            int virtualCount = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    virtualCount++;
                }
            }

            long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000L;

            System.out.printf(
                "%s: completed=%d, virtual=%d, elapsedMs=%d%n",
                label, futures.size(), virtualCount, elapsedMs);
        }
    }

    public static void main(String[] args) throws Exception {
        run("platform-pool",
                Executors.newFixedThreadPool(4));

        run("virtual-per-task",
                Executors.newVirtualThreadPerTaskExecutor());
    }
}
~~~

Chạy bằng JDK 21:

~~~bash
javac --release 21 ThreadModelsMain.java
java ThreadModelsMain
~~~

Output có **phần xác định**:

~~~text
platform-pool: completed=40, virtual=0, elapsedMs=<số đo thực tế>
virtual-per-task: completed=40, virtual=40, elapsedMs=<số đo thực tế>
~~~

Dòng trên là **mẫu cấu trúc**, không phải stdout literal để copy/assert: elapsedMs phụ thuộc máy, lịch chạy, GC, tải hệ thống và khả năng cấp threads. Với 40 tasks cùng ngủ 200 ms, fixed pool 4 workers có thể mất khoảng 10 đợt chờ; virtual threads có thể cùng chờ nhiều hơn. Đây chỉ là bài học về **concurrency khi chờ**, không phải benchmark hiệu năng HTTP production, bởi Thread.sleep khác database/network thực.

### 4.5. Pinning trong Java 21

Virtual thread có thể bị **pinned** lên carrier khi blocking xảy ra trong một số bối cảnh. Với **JDK 21**, các trường hợp điển hình gồm:
- blocking khi đang nằm trong **synchronized method/block**;
- một số native/foreign calls.

~~~java
private final Object lock = new Object();

// Minh họa lỗi thiết kế: giữ monitor trong thời gian chờ dài.
public void risky() throws InterruptedException {
    synchronized (lock) {
        Thread.sleep(250);
    }
}
~~~

Đây là **method snippet**, không phải class độc lập. Trong JDK 21, frequent long-lived pinning có thể giữ carrier thread và giảm throughput. Đồng thời lock ở đây **tuần tự hóa tất cả callers** bất kể dùng platform hay virtual threads.

**Không kết luận synchronized luôn xấu**. Critical section nhỏ thuần CPU có thể hoàn toàn hợp lý. Nếu có các chỗ synchronized kéo dài xuyên I/O, cân nhắc di chuyển I/O ra ngoài lock, thu hẹp critical section hoặc dùng **ReentrantLock** khi thích hợp. Cần kiểm chứng race/deadlock, không đổi mọi synchronized theo quy tắc máy móc.

**Phiên bản JDK quan trọng:** JDK 24 trở lên đã cải tiến vấn đề monitor-related pinning (JEP 491), nhưng các giới hạn khác và contention vẫn tồn tại. Vì bài lab sử dụng **Java 21**, hãy hiểu caveat của Java 21 thay vì suy diễn hành vi JDK 24/25 ngược lại.

### 4.6. Debug pinning bằng JFR

Một cách thu JFR khi chạy MVC virtual-thread demo:

~~~bash
java -XX:StartFlightRecording=filename=vt.jfr,settings=profile,dumponexit=true \
  -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true
~~~

Sau khi tạo load, kết thúc chương trình bình thường để ghi JFR rồi đọc:

~~~bash
jfr print --events jdk.VirtualThreadPinned vt.jfr
~~~

Trên JDK 21, event **jdk.VirtualThreadPinned** giúp phát hiện các block/pin kéo dài; event threshold mặc định thường 20 ms trong cấu hình JFR tương ứng. Không thấy event **không chứng minh mọi chỗ dùng VT tối ưu**; có thể threshold, settings, workload, thời gian thu chưa phù hợp. Có thể dùng **jcmd** dump các virtual threads trên runtime hỗ trợ:

~~~text
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

Đây là **lệnh mẫu**, thay PID bằng process ID thật. Thread dump/JFR có thể chứa thông tin nội bộ, phải lưu và chia sẻ theo security policy.

### 4.7. ThreadLocal, MDC và virtual threads

Virtual threads hỗ trợ ThreadLocal, nhưng chi phí một ThreadLocal cache trên hàng trăm nghìn virtual threads khác hẳn 20 platform workers được tái sử dụng. Tránh lưu buffer lớn, JDBC connection hoặc user secrets lâu dài trong ThreadLocal per-request. MDC tracing và Spring Security context cần được quản lý đúng scope, dọn sạch sau request, không giả định thread được tái sử dụng mãi.

## 5. Spring Boot 3.3 bật virtual threads như thế nào?

### 5.1. Cấu hình chính xác

Với **Java 21+**, Spring Boot 3.3 hỗ trợ:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
~~~

- **spring.threads.virtual.enabled=true** yêu cầu Boot sử dụng virtual threads trong các tích hợp Boot hỗ trợ, gồm một số web server Servlet request executors.
- **spring.main.keep-alive=true** giữ JVM chạy khi chỉ còn daemon threads, có thể quan trọng với các ứng dụng chạy @Scheduled hoặc background tasks trên virtual threads.
- **Không có nghĩa mọi thread của JVM biến thành virtual thread**. Carrier threads, Netty event loops, JVM services, các third-party thread pools và những executor tự tạo vẫn có thể là platform threads.

Spring Boot tài liệu lưu ý khi dùng virtual threads, một số properties điều chỉnh **thread pool** không còn hiệu lực theo cách cũ, vì virtual threads được lập lịch trên pool carrier dùng chung. Do đó không kết luận tăng server.tomcat.threads.max sẽ tăng số virtual request tasks.

### 5.2. Tomcat Servlet + virtual thread

Spring Boot 3.2+ có integration cho Tomcat và Jetty khi bật virtual threads; HTTP request processing trong controller Servlet có thể chạy trên virtual thread. Kiểm chứng ngay trong controller bằng:

~~~java
boolean virtual =
        Thread.currentThread().isVirtual();
~~~

**Đừng giả định toàn application đã dùng VT chỉ vì JVM là Java 21**. Property phải bật, web runtime hỗ trợ, không bị custom executor/connector override, và phải kiểm tra bằng test HTTP thật.

### 5.3. @Async, @Scheduled và task executors

Khi virtual threads được bật, **applicationTaskExecutor** do Spring Boot tự cấu hình có thể chuyển sang executor sử dụng virtual threads; scheduling tương ứng cũng chịu ảnh hưởng. Nhưng nếu application đã khai báo **Executor**, **ThreadPoolTaskExecutor** hoặc scheduled executor riêng, thì cấu hình/custom bean đó cần được kiểm tra. Spring Boot không chiếm quyền mọi executor do bạn tự tạo.

**Thread.sleep** trong một virtual thread có thể giúp carrier làm việc khác, nhưng hành vi đó vẫn là **blocking-style Java code** và giữ virtual task/request chờ. Đừng chuyển sang @Async chỉ để tránh MVC worker pool nếu bạn chưa xác định latency, cancellation và số lượng task in-flight.

### 5.4. Cẩn thận daemon thread và keep-alive

Virtual threads là daemon threads theo JDK 21. Nếu ứng dụng chỉ còn những virtual threads đó và không có non-daemon thread nào khác, JVM có thể thoát. Boot khuyến nghị **spring.main.keep-alive=true** trong các trường hợp dùng virtual threads. Điều này đặc biệt đáng chú ý với job/scheduler apps, không có nghĩa mọi Spring MVC Tomcat process chắc chắn tự thoát khi bật VT.

## 6. Reactive WebFlux: tối ưu theo non-blocking composition

### 6.1. Reactor không tạo một thread riêng cho mỗi request

WebFlux với Reactor Netty dùng số lượng tương đối nhỏ **event-loop threads** để xử lý network events. Handler trả về **Mono<T>** (0 hoặc 1 item) hoặc **Flux<T>** (0..N items). Reactor biểu diễn các bước xử lý, đăng ký callback và xử lý signal khi I/O completion tới, thay vì giữ một request platform worker thread đợi.

~~~text
Netty event loop
    |
    +-- HTTP request A -> tạo Mono/Flux pipeline
    |                        |
    |                        +-- async I/O đang chờ, thread được trả lại
    |
    +-- HTTP request B -> tạo Mono/Flux pipeline
    |
    +-- I/O A hoàn tất -> onNext/onComplete signal
                             |
                             v
                       serialization/response
~~~

**Không phải mọi operator chạy trên event-loop**: Reactor có schedulers như parallel và boundedElastic; source và publishOn/subscribeOn quyết định nơi operators chạy. Reactive ≠ async magic; nó đòi các thư viện I/O tương thích non-blocking.

### 6.2. Mono/Flux và Reactive Streams backpressure

- **Mono<T>**: publisher phát 0 hoặc 1 value, hoặc error signal.
- **Flux<T>**: publisher phát 0 đến nhiều values, hoặc error signal.
- **Subscriber** đăng ký với publisher và theo protocol có thể thông báo **request(n)**: số item nó sẵn sàng nhận.
- **Backpressure** là việc downstream điều tiết demand từ upstream; không phải hạn mức request HTTP toàn service và không tự giảm số database queries nếu code không phối hợp.
- **Cancellation** cho phép dừng subscription và tài nguyên liên quan nếu operator/driver hỗ trợ.
- **Error/completion** là signals trong stream, khác throwing unchecked exception ra khỏi blocking controller method.

Ví dụ:

~~~java
Flux.range(1, 100)
    .map(n -> n * 2)
    .take(5);
~~~

Đây là **snippet giải thích**, không có subscriber trong đoạn trên nên chỉ mô tả pipeline; khi subscribe, take(5) giới hạn những items consumer cần. Nó không có nghĩa mọi upstream/network operation đã được cancel ngay lập tức nếu driver không hỗ trợ cancel.

### 6.3. block() không biến một library thành non-blocking

Trong WebFlux controller chạy trên Netty event loop, code kiểu:

~~~java
Thread.sleep(250);             // Chặn event loop.
webClient.get()
    .uri("/api/data")
    .retrieve()
    .bodyToMono(String.class)
    .block();                    // Blocking bridge ở sai tầng.
~~~

là **anti-pattern** trong handler reactive. Reactor có thể báo **IllegalStateException** khi gọi block() trên một số non-blocking scheduler threads, ngoài nguy cơ làm nghẽn event loop. Không chữa bằng cách chuyển tất cả operators sang một scheduler vô hạn, vì điều đó làm mất lợi ích reactive.

### 6.4. Chuyển blocking call legacy sang boundedElastic

Nếu buộc gọi một DAO/SDK đồng bộ trong pipeline reactive:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyClient.fetch())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **snippet**, chưa khai báo Result, legacyClient/imports. **Schedulers.boundedElastic()** có giới hạn resources/queue, thích hợp cách ly blocking work khỏi event loops, nhưng **blocking call vẫn chiếm worker của boundedElastic**, không thành reactive I/O. Nếu đủ điều kiện, chuyển sang R2DBC/reactive HTTP driver để I/O non-blocking end-to-end.

**Không nhầm boundedElastic với virtual-thread-per-task.** Với Reactor 3.6+, boundedElastic có option sử dụng virtual threads trên Java 21 khi bật system property cụ thể **reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true**; đây là tùy chọn Reactor riêng, không phải cứ bật spring.threads.virtual.enabled là mọi Reactor operator tự đổi sang VT.

### 6.5. publishOn và subscribeOn

**subscribeOn(scheduler)** tác động nơi subscription/source được thực hiện, còn **publishOn(scheduler)** chuyển nơi xử lý các signals phía sau vị trí operator đó. Chúng không tự bảo đảm backpressure hay giảm I/O latency:

~~~java
Mono.fromCallable(() -> legacyClient.fetch())
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::transformResult);
~~~

Đây là snippet, không tự biên dịch nếu thiếu legacyClient, transformResult. Cần biết transformResult có CPU cost bao nhiêu và schedulers có phù hợp; không thêm publishOn tùy tiện nếu chỉ làm tăng context switching.

### 6.6. Reactive concurrency cũng phải được giới hạn

Một WebFlux pipeline gọi 100.000 HTTP requests đồng thời có thể làm cạn sockets, rate limit hoặc memory. Với Flux.flatMap, hãy truyền concurrency khi phù hợp:

~~~java
Flux.fromIterable(ids)
    .flatMap(
        id -> webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class),
        16);
~~~

Đây là **snippet cần ids, webClient, Item**. Tham số 16 là **mức concurrency ví dụ**, không phải optimum chung. Vẫn cần connection pool, timeouts, rate limiter, retry budget, batching và backpressure thực tế. Tránh dùng onBackpressureBuffer không giới hạn dẫn đến heap tăng vô hạn.

## 7. Decision matrix: chọn mô hình nào?

| Tiêu chí | MVC + platform | MVC + virtual | WebFlux reactive |
| --- | --- | --- | --- |
| Java tối thiểu | Theo Spring Boot (Boot 3: Java 17) | **Java 21+** | Boot 3: Java 17+ |
| Programming style | Imperative, blocking | Imperative, blocking | Publisher/async, non-blocking |
| HTTP runtime điển hình | Tomcat/Servlet worker pool | Tomcat/Servlet với virtual request threads | Reactor Netty event loops |
| I/O blocking JDBC/SDK | Tương thích tự nhiên, giữ worker | Tương thích tự nhiên, virtual task có thể unmount | Phải offload sang boundedElastic hoặc thay bằng reactive driver |
| Non-blocking R2DBC/WebClient | Có thể dùng client reactive nhưng code servlet không tự thành reactive | Tương tự | Phù hợp end-to-end |
| CPU-heavy operations | Giới hạn theo CPU/worker | Không tự tăng CPU | Phải tránh CPU nặng trên event loops; offload phù hợp |
| Backpressure API | Thường kiểm soát ở pool/queue | Kiểm soát bằng bulkhead/resource limits | Reactive Streams demand, operator concurrency/buffers |
| Debug stack trace | Straight-line dễ đọc | Straight-line dễ đọc, nhiều task | Nhiều async boundaries và Reactor Context |
| Lỗi quan trọng | Worker starvation, queue | Pinning JDK 21, tài nguyên downstream | Event-loop blocking, buffer blowup |
| Migration cost | Thấp với MVC hiện có | Thường thấp hơn full WebFlux rewrite | Cao hơn nếu codebase blocking từ đầu |
| Throughput/latency | Phụ thuộc workload và tuning | Phụ thuộc workload, pinning/resources | Phụ thuộc non-blocking pipeline và backpressure |

**Không có ranking mặc định.** Nếu workload CPU-bound, cả virtual và reactive đều không tạo thêm cores. Nếu system chủ yếu đợi blocking JDBC, MVC+virtual threads trên JDK 21+ là phương án đáng thử trước khi rewrite toàn bộ sang WebFlux. Nếu hệ đã sử dụng reactive drivers và streaming, WebFlux có lợi thế rõ trong async composition. Nếu traffic vừa phải và MVC platform đang đạt SLO, ưu tiên tuning và bảo trì.

## 8. Vì sao cần hai Spring Boot projects riêng khi so sánh?

Spring Boot 3.3 chọn **Spring MVC** khi cả **spring-boot-starter-web** và **spring-boot-starter-webflux** xuất hiện trên classpath; behavior này giúp MVC app vẫn dùng reactive WebClient. Thêm WebFlux starter **không tự chuyển server sang reactive**. Vì vậy bài thực hành tách:

~~~text
performance-model-lab/
  mvc-thread-demo/
     pom.xml
     src/main/java/com/example/mvc/
         MvcThreadApplication.java
         WaitController.java
     src/main/resources/application.yml
     src/test/java/com/example/mvc/
         PlatformThreadHttpTest.java
         VirtualThreadHttpTest.java

  webflux-reactive-demo/
     pom.xml
     src/main/java/com/example/reactive/
         ReactiveApplication.java
         ReactiveWaitController.java
     src/main/resources/application.yml
     src/test/java/com/example/reactive/
         ReactiveWaitHttpTest.java
         ReactorDelayTest.java

  LocalLoadProbe.java
~~~

**MVC project** dùng **spring-boot-starter-web**: chạy hai lần bằng config platform/virtual, không cần sửa Java code. **Reactive project** chỉ dùng **spring-boot-starter-webflux**: dùng Reactor Netty và Mono.delay. **LocalLoadProbe** là ứng dụng Java 21 riêng, chạy trên máy kiểm thử và gửi tải đến một server tại một thời điểm.

Không chạy cả MVC và Reactive cùng port 8080. Cần Java 21 cho toàn bộ bài lab vì có virtual thread checks.

## 9. MVC project: chạy platform hoặc virtual threads

### 9.1. mvc-thread-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-thread-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. MvcThreadApplication.java

**src/main/java/com/example/mvc/MvcThreadApplication.java**

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcThreadApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcThreadApplication.class, args);
    }
}
~~~

### 9.3. WaitController.java — cùng một blocking endpoint

**src/main/java/com/example/mvc/WaitController.java**

~~~java
package com.example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WaitController {

    public record WaitReply(
            long simulatedWaitMs,
            boolean virtualThread,
            String threadName) {
    }

    @GetMapping("/wait")
    public WaitReply waitFor(
            @RequestParam(defaultValue = "250") long ms)
            throws InterruptedException {

        long bounded = Math.max(0L, Math.min(ms, 2000L));

        // Chỉ dùng để minh họa thời gian CHỜ, không phải I/O thật.
        Thread.sleep(bounded);

        Thread requestThread = Thread.currentThread();
        return new WaitReply(
                bounded,
                requestThread.isVirtual(),
                requestThread.getName());
    }
}
~~~

Trong **platform mode**, request xử lý trong Tomcat platform worker thread, ví dụ tên bắt đầu bằng http-nio...; **virtualThread=false**. Trong **virtual mode** của Spring Boot/embedded Tomcat được hỗ trợ, controller xử lý trên virtual thread, **virtualThread=true**. Tên thread không ổn định hoặc có thể rỗng với VT, không hardcode nó trong assertions.

Thread.sleep là blocking-style call, cố tình mô phỏng chờ. **Không dùng endpoint có delay điều chỉnh qua query như vậy trong production**: nó có thể bị lạm dụng để tăng số in-flight requests, memory và worker exhaustion. Để đo performance thật, thay sleep bằng downstream I/O trong môi trường test cô lập.

### 9.4. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: mvc-thread-demo
  main:
    keep-alive: true

server:
  port: 8080
  tomcat:
    threads:
      max: 16
      min-spare: 4
    max-connections: 256
    accept-count: 100

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
~~~

Chúng ta **không cố định spring.threads.virtual.enabled trong file**, để bật/tắt qua command-line khi chạy. Thread pool 16 workers chỉ nhằm tạo mức cạnh tranh dễ quan sát trong lab platform mode. Khi bật virtual threads, property max workers không còn là cùng một trần cho request virtual thread; vẫn cần giới hạn external resources.

Management metrics endpoint chỉ được expose cho lab localhost; production không công khai toàn bộ Actuator.

### 9.5. Chạy MVC platform-thread mode

Trong thư mục mvc-thread-demo:

~~~bash
mvn clean package
java -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=false
~~~

Dùng terminal khác:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

HTTP **200**, response có cấu trúc:

~~~json
{
  "simulatedWaitMs": 250,
  "virtualThread": false,
  "threadName": "http-nio-8080-exec-1"
}
~~~

**threadName chỉ minh họa**, không phải stdout cố định. Java/JVM, connector và workload có thể thay đổi. Quan trọng nhất là trường virtualThread=false.

### 9.6. Chạy MVC virtual-thread mode

Dừng process platform mode, sau đó:

~~~bash
java -jar target/mvc-thread-demo-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true
~~~

Gọi:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

Ví dụ cấu trúc:

~~~json
{
  "simulatedWaitMs": 250,
  "virtualThread": true,
  "threadName": ""
}
~~~

Tên virtual thread có thể khác hoặc trống; không đoán tên. **Sự thay đổi boolean** là minh chứng request handler thực sự chạy trên virtual thread với cấu hình đang dùng. Đây **không phải bằng chứng virtual mode nhanh hơn**: phải đo throughput/latency dưới cùng workload và resource limits.

### 9.7. Tại sao dùng một ứng dụng cho hai modes?

Giữ nguyên POM, controller, serialization và HTTP response nghĩa là khác biệt chính nằm ở server execution model. Tuy nhiên tự so sánh hai process khác thời điểm vẫn có nhiễu do CPU load, JIT, GC, network và warmup. Nên chạy lặp, đổi thứ tự các modes và thu metrics. **Platform worker max=16** khiến test mô phỏng một giới hạn khá hẹp; đừng kết luận so sánh đại diện cho mọi Tomcat settings.

## 10. MVC HTTP integration tests: không chỉ dùng MockMvc

**MockMvc** không thực sự dispatch request qua Tomcat worker executor. Nếu bạn test Thread.currentThread().isVirtual() trong MockMvc, có thể đang kiểm tra **JUnit caller thread**, không phải HTTP server thread. Vì bài so sánh thread model, cần **@SpringBootTest(webEnvironment=RANDOM_PORT)** và HTTP request thật.

### 10.1. PlatformThreadHttpTest.java

**src/test/java/com/example/mvc/PlatformThreadHttpTest.java**

~~~java
package com.example.mvc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.threads.virtual.enabled=false")
class PlatformThreadHttpTest {

    @LocalServerPort
    int port;

    @Test
    void mvcUsesPlatformWorkerThreads() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertFalse(body.path("virtualThread").asBoolean());
    }
}
~~~

### 10.2. VirtualThreadHttpTest.java

**src/test/java/com/example/mvc/VirtualThreadHttpTest.java**

~~~java
package com.example.mvc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.threads.virtual.enabled=true")
class VirtualThreadHttpTest {

    @LocalServerPort
    int port;

    @Test
    void mvcUsesVirtualRequestThreads() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertTrue(body.path("virtualThread").asBoolean());
    }
}
~~~

Hai tests sử dụng hai Spring ApplicationContexts vì properties khác nhau. Chúng kiểm tra **tính đúng của mode được bật**, không đo RPS. Test Web server còn chạy trên random port nên không bị xung đột với ứng dụng đang chạy port 8080.

Nếu Java 17 được dùng chạy tests, virtual test không hợp lệ vì property yêu cầu **Java 21+**. Kiểm tra:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu test khác fail do port/config/connector override, xem actual Boot web server và classpath; không mặc định boolean là true chỉ vì property được set trong metadata.

## 11. Reactive WebFlux project độc lập

### 11.1. Khác MVC từ dependency

Đối với WebFlux trên Netty, tạo project riêng chỉ có **spring-boot-starter-webflux**. Đừng thêm **spring-boot-starter-web** vào cùng project lab, vì Boot 3.3 sẽ ưu tiên Spring MVC khi cả hai có trên classpath.

### 11.2. webflux-reactive-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-reactive-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. ReactiveApplication.java

**src/main/java/com/example/reactive/ReactiveApplication.java**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

### 11.4. ReactiveWaitController.java

**src/main/java/com/example/reactive/ReactiveWaitController.java**

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveWaitController {

    public record WaitReply(
            long simulatedWaitMs,
            String strategy,
            boolean virtualThread) {
    }

    @GetMapping("/wait")
    public Mono<WaitReply> waitFor(
            @RequestParam(defaultValue = "250") long ms) {

        long bounded = Math.max(0L, Math.min(ms, 2000L));

        return Mono.delay(Duration.ofMillis(bounded))
                .map(ignored -> new WaitReply(
                        bounded,
                        "mono-delay",
                        Thread.currentThread().isVirtual()));
    }
}
~~~

**Tại sao Mono.delay là non-blocking?** Controller trả Publisher ngay; hệ thống đăng ký timer và chỉ chạy mapping khi timer phát signal. Nó **không gọi Thread.sleep** để giữ một worker trong 250 ms. Operator callback của Mono.delay có thể chạy trên **Reactor scheduler**, không nhất thiết trên Netty event-loop; vì thế boolean virtualThread và thread name **không đủ chứng minh cách Reactor Netty sử dụng event loops**.

**Mô phỏng chỉ có timer** nên chưa chứng minh non-blocking database/HTTP client. Production cần reactive drivers, backpressure hợp lý, timeouts và cancellation semantics xuyên pipeline.

### 11.5. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: webflux-reactive-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
~~~

Không bật spring.threads.virtual.enabled ở reactive project: mục tiêu là kiểm tra mô hình WebFlux/Netty mặc định, không tạo một hybrid không chủ ý. Reactive scheduler có thể sử dụng platform threads ở demo này; **WebFlux non-blocking không đòi mỗi task là virtual thread**.

### 11.6. Chạy WebFlux

Trong thư mục webflux-reactive-demo:

~~~bash
mvn clean package
java -jar target/webflux-reactive-demo-0.0.1-SNAPSHOT.jar
~~~

Dừng ứng dụng MVC trên cổng 8080 trước. Gọi:

~~~bash
curl -i "http://localhost:8080/wait?ms=250"
~~~

Kỳ vọng HTTP 200 và response có cấu trúc:

~~~json
{
  "simulatedWaitMs": 250,
  "strategy": "mono-delay",
  "virtualThread": false
}
~~~

Trường virtualThread trong lab WebFlux thường false với Reactor scheduler mặc định, nhưng không dùng nó để kết luận Netty server/entire app không thể sử dụng VT trong một cấu hình khác. **strategy=mono-delay** mới là thông tin quan trọng của bài.

### 11.7. ReactiveWaitHttpTest.java

**src/test/java/com/example/reactive/ReactiveWaitHttpTest.java**

~~~java
package com.example.reactive;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveWaitHttpTest {

    @LocalServerPort
    int port;

    @Test
    void nonBlockingTimerReturnsJson() throws Exception {
        URI uri = URI.create(
                "http://localhost:" + port + "/wait?ms=0");
        HttpRequest request =
                HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = new ObjectMapper()
                .readTree(response.body());
        assertEquals(0L, body.path("simulatedWaitMs").asLong());
        assertEquals("mono-delay",
                body.path("strategy").asText());
    }
}
~~~

### 11.8. ReactorDelayTest.java — virtual-time test

**src/test/java/com/example/reactive/ReactorDelayTest.java**

~~~java
package com.example.reactive;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorDelayTest {

    @Test
    void virtualTimeTestsDelayWithoutRealWaiting() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1)))
            .expectSubscription()
            .thenAwait(Duration.ofHours(1))
            .expectNext(0L)
            .verifyComplete();
    }
}
~~~

**StepVerifier.withVirtualTime** thay scheduler clock trong bài test ở phạm vi phù hợp; test có thể xác minh timer logic mà không chờ một giờ thật. Đây là **virtual time của Reactor Test**, **khác hoàn toàn virtual threads của Java 21**. Tên giống nhau nhưng ý nghĩa không liên quan.

Chạy:

~~~bash
mvn test
~~~

**Hai Spring Boot projects dùng hai HTTP server pipelines riêng**, và tests này chứng minh endpoint contract chứ **không phải kết luận benchmark performance**.

## 12. Trình tạo tải Java 21 cho cả ba modes

Công cụ dưới đây giúp tự thử một mức request concurrency có kiểm soát trên **localhost**. Đây là một chương trình Java độc lập; nó dùng **client-side platform executor cố định** để gửi HTTP requests đồng thời, giữ logic client giống nhau khi đo các server modes. Tất cả latency tính từ phía client, gồm queue/connection/network và thời gian response; **không tách riêng server processing time**.

Tạo file **LocalLoadProbe.java** ở ngoài hai Maven projects:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LocalLoadProbe {

    record Sample(int status, long elapsedMs) { }

    public static void main(String[] args) throws Exception {
        String target = args.length > 0
                ? args[0]
                : "http://localhost:8080/wait?ms=250";

        int total = args.length > 1
                ? Integer.parseInt(args[1])
                : 200;

        int concurrency = args.length > 2
                ? Integer.parseInt(args[2])
                : 32;

        URI uri = URI.create(target);
        if (!List.of("localhost", "127.0.0.1")
                    .contains(uri.getHost())
                || total < 1 || total > 500
                || concurrency < 1 || concurrency > 100) {
            throw new IllegalArgumentException(
                "Use localhost, 1..500 requests, 1..100 workers");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        long allStart = System.nanoTime();
        List<Future<Sample>> futures = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newFixedThreadPool(concurrency)) {

            for (int i = 0; i < total; i++) {
                futures.add(executor.submit(() -> {
                    long start = System.nanoTime();
                    int status = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding())
                        .statusCode();

                    long elapsedMs =
                        (System.nanoTime() - start) / 1_000_000L;

                    return new Sample(status, elapsedMs);
                }));
            }

            List<Long> times = new ArrayList<>();
            int ok = 0;

            for (Future<Sample> future : futures) {
                Sample sample = future.get();
                if (sample.status() == 200) {
                    ok++;
                }
                times.add(sample.elapsedMs());
            }

            Collections.sort(times);
            int p95Index =
                Math.max(0, (int) Math.ceil(times.size() * 0.95) - 1);

            long wallMs =
                (System.nanoTime() - allStart) / 1_000_000L;

            System.out.printf(
                "total=%d ok=%d errors=%d wallMs=%d p95Ms=%d%n",
                total, ok, total - ok,
                wallMs, times.get(p95Index));
        }
    }
}
~~~

**Giới hạn cố ý:** công cụ chỉ cho localhost và tối đa 500 requests/100 workers, để tránh dùng như load generator không kiểm soát vào hệ thống bên ngoài. Chỉ chạy khi bạn có quyền kiểm thử môi trường đó; không dùng trên production. Kết quả là **closed-loop client load** và p95 bao gồm queue ở client; không đủ thay cho k6/wrk2/Gatling/JMeter hoặc load test open-loop.

Biên dịch và chạy JDK 21:

~~~bash
javac --release 21 LocalLoadProbe.java
java LocalLoadProbe "http://localhost:8080/wait?ms=250" 200 32
~~~

Output dạng:

~~~text
total=200 ok=200 errors=0 wallMs=<phụ thuộc máy> p95Ms=<phụ thuộc máy>
~~~

Nếu server timeouts/connection failures xảy ra, Future.get() có thể ném ExecutionException và chương trình kết thúc với lỗi thay vì in report đủ; cần ghi nhận lỗi đó trong kết quả kiểm thử, **không bỏ qua failed requests để làm RPS trông đẹp hơn**. Với benchmark nghiêm túc, dùng công cụ hỗ trợ latency histograms, warmup, fixed arrival rate, coordination omission correction, ramp-up và error distribution.

## 13. Kế hoạch so sánh có kiểm soát

### 13.1. Ba chế độ cần chạy

1. **MVC + platform**: chạy mvc-thread-demo với spring.threads.virtual.enabled=false.
2. **MVC + virtual**: dừng process cũ, chạy cùng JAR với spring.threads.virtual.enabled=true.
3. **WebFlux**: dừng MVC, chạy webflux-reactive-demo chỉ dùng spring-boot-starter-webflux.

Ở mỗi mode, gọi cùng URL **GET /wait?ms=250**, cùng số requests/concurrency, cùng máy, cùng JDK, cùng heap/resource limits nếu có thể. Bật **/actuator/metrics** trong lab để xem request timings, Tomcat/Netty/JVM metrics phù hợp.

### 13.2. Tránh nhiễu khi benchmark

- **Warmup** trước khi đo: JIT compilation, classloading, connection setup có thể làm vòng đầu chậm.
- **Lặp nhiều vòng**, xen kẽ thứ tự modes, không dựa một lần.
- **Cố định heap, CPU limits, GC, network route và client config**.
- **Đo p95/p99 + throughput + error rate**, không chỉ p50.
- **Theo dõi CPU/GC, live threads, queue, connection pools**, không chỉ latency.
- **Giữ mock delay như nhau**, nhưng không xem sleep timer là biểu diễn thực của DB/JDBC.
- **Không thay đổi worker pool rồi so với virtual mode mà kết luận technology vượt trội**: có thể chỉ do cấu hình platform pool quá thấp.
- **Ghi concurrency cấp client và server**: client pool chỉ 32 tasks nên không thể nhìn thấy giới hạn khi server chịu 1000 requests in-flight.
- **Không bỏ qua lỗi HTTP 5xx/timeouts**; throughput chỉ có ý nghĩa cùng tỷ lệ thành công/SLO.

### 13.3. Kịch bản bài lab

| Kịch bản | Mục tiêu | Điều nên kỳ vọng (không phải cam kết) |
| --- | --- | --- |
| 50 requests, concurrency 4, wait 250 ms | Tải thấp, không bão hòa server | Ba modes có thể gần nhau; overhead khác biệt nhỏ. |
| 200 requests, concurrency 32, wait 250 ms, MVC maxThreads=16 | Thấy worker limit trong platform mode | Virtual/Mono.delay có thể giữ nhiều I/O waits mà không chiếm 32 platform worker threads. |
| 200 requests, concurrency 32, wait 0 ms | Không có chờ đáng kể | Không kỳ vọng virtual/reactive tăng tốc; overhead cũng có thể khác. |
| CPU tính toán thực, concurrency cao | Đo CPU saturation | Tất cả modes chịu giới hạn cores; VT không tăng CPU capacity. |
| Downstream DB pool 8 connections | Kiểm tra resource bottleneck | Concurrency tăng nhưng DB throughput có thể dừng tăng; queue/timeouts vẫn xuất hiện. |
| HTTP downstream có rate limit | Kiểm tra overload | Cần bulkhead/rate limiting/backoff ở mọi mô hình. |

**Các giá trị thử chỉ là đề xuất cho local lab**, không phải configuration production hay benchmark được đo sẵn. Không tuyên bố một mode đạt RPS cụ thể nếu chưa chạy trên môi trường thật.

### 13.4. Phân biệt response-time và service-time

Trong platform mode, khi Tomcat worker pool đã đầy, một request có thể chờ tại server connector/executor trước khi controller bắt đầu. LocalLoadProbe đo từ lúc client gửi đến lúc nhận response; do đó latency cao có thể là **queue + service**.

Trong virtual mode, request có thể vào handler nhanh hơn nhưng mắc kẹt ở DB pool. Trong reactive mode, pipeline có thể không chiếm worker thread nhưng bị queue ở connection pool/operator buffers. Để tìm đúng bottleneck, cần tracing và metrics đặt ở các giai đoạn tương ứng.

## 14. Tối ưu resource pools dưới mỗi mô hình

### 14.1. JDBC và HikariCP

JDBC là blocking API. Với platform threads, worker bị giữ khi query chờ. Với virtual threads, một số blocking I/O JDBC có thể hỗ trợ unmount carrier, nhưng **HikariCP connection pool vẫn có giới hạn** và DB vẫn xử lý hữu hạn queries concurrent. Không nâng maximumPoolSize vô tội vạ: DB server cũng có connection/thread/transaction memory và lock contention.

Nếu một service có 10 DB connections và 1000 virtual requests đồng thời, có thể có rất nhiều request **đang đợi lấy connection**. Thread rẻ không làm DB nhanh hơn. Thiết kế admission control, query optimization, timeouts và rate limiter phù hợp.

### 14.2. Reactive R2DBC

WebFlux + R2DBC phù hợp với non-blocking database access khi driver và framework được hỗ trợ. Nhưng R2DBC cũng có connection pools, buffer limits và transaction semantics. Không giả định reactive driver luôn nhanh hơn JDBC. Nếu hệ thống đã dùng JPA/Hibernate/JDBC đồng bộ nặng, rewrite sang WebFlux có thể tăng độ phức tạp mà không có lợi ích tương xứng.

### 14.3. HTTP client calls

- **MVC platform/virtual**: RestClient hoặc RestTemplate đồng bộ dễ đọc. Virtual threads giúp chờ I/O trong request task nhẹ hơn khi library/runtime tương thích.
- **WebFlux**: WebClient trả Mono/Flux, có thể compose non-blocking requests. Nên dùng managed **WebClient.Builder** của Boot để giữ auto-configured observation/tracing.
- **MVC dùng WebClient**: có thể dùng reactive client trong MVC app; **không đồng nghĩa server đã chuyển WebFlux**. Nếu gọi .block() trong MVC platform worker, vẫn chặn worker; trong MVC virtual thread có thể chờ nhẹ hơn nếu underlying operations phù hợp, nhưng vẫn là blocking boundary.
- **Netty server**: không chạy RestTemplate/JDBC blocking trực tiếp trên event loop.

Ở cả ba, timeout, TLS, connection reuse, retry budget, circuit breaker và credentials đều quan trọng hơn framework marketing.

### 14.4. External rate limits và cascading failure

Virtual threads/reactive có thể dễ khởi tạo nhiều concurrent calls hơn platform pool nhỏ; nếu không có **bulkhead** và rate limiter, bạn có thể làm quá tải partner API, dẫn đến retry storm. Giữ:
- maximum in-flight per downstream;
- deadline propagation và connection/request timeouts;
- bounded retries with backoff/jitter;
- circuit breaker/fallback;
- idempotency keys cho request gây side effects;
- observability cho queue waits và dependency errors.

Tối ưu concurrency là **quản lý tài nguyên có giới hạn**, không phải bỏ hết giới hạn.

## 15. Reactive data streaming và backpressure thực tế

### 15.1. Flux giúp luồng dữ liệu lớn, nhưng không làm bộ nhớ vô hạn

Một endpoint trả Flux hàng triệu records có thể stream dần nếu encoding/transport/consumer xử lý được. Nhưng nếu toàn bộ records đã được load vào List trước, rồi dùng Flux.fromIterable(list), memory cost vẫn rất lớn. Lợi ích backpressure chỉ có khi dữ liệu được sản xuất theo demand đủ tốt và driver không buffer quá mức.

Cần kiểm tra:
- Source có tôn trọng demand không?
- Serialization/HTTP transfer encoding có streaming thật không?
- Có buffer() hoặc collectList() vô ý giữ toàn bộ dữ liệu không?
- Client disconnect có cancel subscription và giải phóng DB cursor không?
- Proxy/CDN có buffer response làm mất streaming không?
- Tốc độ consumer chậm có đẩy memory upstream tăng không?

### 15.2. Reactor Context thay ThreadLocal

Reactive pipeline có thể chạy qua nhiều threads. Một ThreadLocal được đặt ở Netty event-loop request thread không tự động đảm bảo vẫn hiện diện sau publishOn/subscribeOn. Reactor dùng **Context** để lưu metadata theo subscription; Spring/Micrometer có cơ chế context propagation tích hợp tùy version/config. Nếu chuyển code blocking dùng ThreadLocal sang reactive, phải xem tracing, Spring Security context, transactions và MDC cùng một cách, không copy sang static global variables.

### 15.3. Cancellation không có nghĩa remote side effect chưa xảy ra

Khi client hủy subscription, WebClient/driver có thể ngừng đọc response hoặc cancel request, nhưng remote server có thể đã nhận và xử lý POST. Tương tự virtual/platform request timeout không chứng minh DB transaction đã rollback. Dùng idempotency và transaction semantics đúng cho nghiệp vụ, không coi cancellation là xóa side effects.

## 16. Phân biệt concurrency, parallelism và asynchrony

**Concurrency** là nhiều công việc tiến triển đan xen. **Parallelism** là có nhiều công việc chạy CPU cùng thời điểm trên các cores. **Asynchrony** nghĩa là có thể bắt đầu công việc rồi nhận kết quả thông qua callback/Future/Publisher mà không chặn caller tại điểm đó.

- Platform pool 16 threads có thể chạy nhiều request concurrent và một số chạy parallel trên CPU cores.
- 10.000 virtual threads có thể concurrent, nhưng số carriers thực chạy parallel vẫn hữu hạn.
- Reactor Netty có thể multiplex rất nhiều concurrent network operations với ít event loops; computation CPU vẫn cần cores và schedulers.

**Virtual threads không tự cung cấp Reactive Streams backpressure**; bạn phải quản lý concurrency bằng application-level mechanisms. **Reactive backpressure không đảm bảo mỗi operator chạy song song**; đó là hợp đồng demand của publisher/subscriber.

## 17. Khi nào bật virtual threads trong WebFlux?

Bật **spring.threads.virtual.enabled=true** là thay đổi các executor/scheduler được Spring Boot hỗ trợ, nhưng không biến Reactor Netty event-loop request handling thành "mỗi request một virtual thread". WebFlux vẫn là reactive framework và vẫn có quy tắc không chặn event loops.

Một số phần hỗ trợ blocking execution của WebFlux có thể dùng **applicationTaskExecutor** do Boot cấu hình và hưởng lợi từ virtual threads trong những integration cụ thể. Reactor **boundedElastic** có option virtual-thread backing riêng. Nhưng chỉ nên dùng hybrid khi có case được test rõ, không bật nhiều switches rồi tuyên bố toàn hệ thống virtual/reactive.

Nếu workload toàn reactive I/O đúng chuẩn, ít lý do đổi event-loop architecture sang request-per-VT. Nếu phần lớn logic là blocking JDBC SDKs, MVC+VT thường dễ vận hành hơn so với giấu mọi blocking call trong boundedElastic.

## 18. Tối ưu CPU-bound tasks và tránh event-loop starvation

### 18.1. Virtual threads không phải CPU scheduler thần kỳ

Nếu endpoint nén ảnh 100 ms CPU, 1000 virtual tasks cùng chạy vẫn chia nhau CPU cores. Khi CPU bị bão hòa:
- giới hạn concurrency CPU work bằng worker pool/bulkhead;
- tối ưu thuật toán, dữ liệu và allocations;
- sử dụng caching/batching khi đúng;
- cân nhắc tách CPU-heavy jobs sang queue/background workers;
- đo p99 và GC thay vì chỉ tăng tasks.

Đừng tạo hàng triệu virtual threads để gọi một hàm CPU loop không có I/O; memory và scheduling overhead có thể tăng mà không cải thiện tốc độ.

### 18.2. Reactive event loop phải tránh CPU work dài

Trong WebFlux, một operator map thực hiện CPU 500 ms trên event-loop có thể làm chậm nhiều unrelated HTTP requests. Có thể offload CPU-heavy stages sang **Schedulers.parallel()** hoặc executor riêng với concurrency giới hạn, nhưng cần đo overhead và bảo đảm backpressure. Không đổi sang boundedElastic cho mọi CPU task theo phản xạ: boundedElastic chủ yếu dành cho blocking I/O compatibility.

## 19. Quan sát hiệu năng trong production

### 19.1. Metrics cần thu

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| **http.server.requests** latency/count/status | Đo SLO HTTP và lỗi 5xx/4xx theo route template. |
| Tomcat busy/current threads khi platform mode | Xem worker pool saturation; interpretation khác khi VT mode. |
| Netty event-loop lag/blocked duration (nếu có instrumentation) | Phát hiện reactive event-loop starvation. |
| **jvm.threads.live** và virtual thread/JFR events | Quan sát số Java threads và pinning; không dựa vào một metric duy nhất cho số VT. |
| CPU utilization, load, context switches | Phân biệt CPU-bound với waiting. |
| JVM heap, allocation rate, GC pauses | Chi phí request/context/buffers. |
| Hikari active/idle/pending, DB slow queries | Tìm bottleneck JDBC và connection pool. |
| Outbound HTTP client latency, connection pool, timeouts | Xem dependency bottlenecks. |
| Request queue time, 503, rejected executions | Phát hiện overload/backpressure không đủ. |
| Throughput, p95, p99, SLO error budget | Chọn thiết kế theo chất lượng dịch vụ, không chỉ RPS. |

Không gắn user IDs, email, full query strings hoặc raw request bodies vào metric tags: có thể gây **high cardinality**, lộ dữ liệu và làm monitoring tốn chi phí.

### 19.2. JFR và thread dumps

- Dùng Java Flight Recorder để xem CPU profiling, allocations, locks, pinning và threads.
- Với JDK 21 virtual threads, **jdk.VirtualThreadPinned** giúp tìm các monitor/native operations giữ carriers quá lâu.
- Với platform threads, thread dump giúp phát hiện BLOCKED/WAITING, deadlocks và connection pool waits.
- Với Reactor, xem event-loop thread stack khi nghi blocking; dùng Reactor debug/checkpoint hoặc observability hooks có kiểm soát khi cần.

Đừng thu heap dumps/thread dumps có secrets trên production rồi chia sẻ không kiểm soát; chúng có thể chứa token, payload, request paths và user data.

### 19.3. Đo throughput khi request timeout không còn ý nghĩa

Nếu một mode đạt 500 RPS nhưng 20% responses 500/timeout, còn mode khác đạt 450 RPS với 0,1% errors và p99 thấp, không thể gọi mode đầu “nhanh hơn” chỉ dựa RPS. So sánh ở **cùng offered load và latency SLO**, theo accepted/failed request distribution.

## 20. Các hiểu nhầm cần loại bỏ

**1. Virtual thread là platform thread pool lớn.** Sai. Virtual threads được JVM lên lịch lên carriers; không nên pool virtual threads như tài nguyên khan hiếm.

**2. Bật virtual threads thì database nhanh hơn.** Sai. Query vẫn mất thời gian và DB pool vẫn có giới hạn. Lợi ích chính là giảm chi phí chờ đồng thời ở request threads.

**3. Virtual threads làm CPU-bound code chạy nhanh hơn.** Không mặc định; cores vẫn hữu hạn.

**4. Bật spring.threads.virtual.enabled=true khiến mọi thread trở thành virtual.** Sai. Tùy runtime, app executors, custom pools, Netty và library threads.

**5. Spring WebFlux nghĩa là luôn non-blocking.** Không nếu handler gọi JDBC/Thread.sleep/block() trên event loop. Non-blocking phải giữ xuyên các dependencies.

**6. Thêm spring-boot-starter-webflux vào MVC project thì server tự chuyển WebFlux.** Sai theo Boot 3.3; MVC được ưu tiên khi hai starters có mặt.

**7. Mono/Flux là một thread.** Sai. Publisher là abstraction tín hiệu và pipeline; scheduler/context quyết định nơi thực thi.

**8. Reactive backpressure bảo đảm không có quá nhiều HTTP requests.** Không. Demand protocol không tự thay rate limiting, connection pool hoặc bulkhead.

**9. Thread.isVirtual() trả false trong WebFlux thì WebFlux không async.** Sai. Reactive non-blocking không cần virtual threads.

**10. Test MockMvc cho virtualThread=true chứng minh Tomcat VT.** Không. MockMvc có thể chạy trên thread của test runner; dùng real HTTP server tests.

**11. JDK 21 synchronized luôn an toàn cho virtual threads.** Không thể kết luận; frequent long blocking sections trong synchronized có nguy cơ pinning trên JDK21. JDK24 cải thiện monitor pinning nhưng contention vẫn tồn tại.

**12. Đổi framework trước khi đo p95.** Thường là quyết định rủi ro. Đo bottleneck thực để chọn tuning hay migration.

## 21. Lỗi thường gặp và hướng debug

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Bật VT nhưng controller virtualThread=false | Chạy Java 17, property không áp dụng, custom executor/runtime khác | java -version, config active, Tomcat integration và HTTP test thật. |
| MVC platform p99 tăng khi concurrency cao | Worker pool full, DB wait, queue | busy threads, DB pool, response time breakdown, CPU. |
| MVC virtual throughput không cải thiện | Workload CPU-bound, pinning, DB/network limit | CPU, JFR jdk.VirtualThreadPinned, Hikari pending, downstream RPS. |
| JVM memory tăng dù dùng VT | Too many in-flight tasks, ThreadLocal caches, responses/buffers | Heap, allocations, request concurrency, limits. |
| WebFlux throughput thấp khi gọi JDBC | Blocking trên Netty event loop | Thread dump/event-loop lag, dùng boundedElastic hoặc reactive DB driver. |
| WebFlux block() ném IllegalStateException | block() trên Reactor non-blocking scheduler | Compose Mono/Flux; nếu legacy blocking bắt buộc thì offload. |
| WebFlux service OOM khi Flux lớn | Unbounded buffering/collectList/high concurrency | bounded buffers, streaming, demand và operator limits. |
| App vẫn khởi động MVC khi thêm webflux | Có starter-web trên classpath | Tách projects, xem Boot web application type. |
| Throughput tăng nhưng errors tăng | Downstream overload và retry storm | Bulkheads, rate limits, idempotency, latency/error SLO. |
| Test local VT nhanh nhưng production chậm | Real workload khác sleep, pinning, GC, DB | Production-like load and profiling. |
| ThreadLocal context mất khi async/reactive | Thread boundary hoặc Reactor Context không propagate | Instrument context propagation, security/tracing scopes. |
| @Scheduled app tự thoát với VT | Chỉ còn daemon threads | spring.main.keep-alive=true; kiểm tra lifecycle. |
| Tomcat maxThreads tăng nhưng VT mode không thay đổi | Property pool không giới hạn VT tasks như trước | Đo connection limits và resource pools. |
| WebClient tạo trong MVC trả Mono nên nghĩ đã reactive server | Reactive client không quyết định server framework | Kiểm tra Spring web application type. |
| Request timeout nhưng DB vẫn ghi xong | Cancellation/timeout không hoàn tác side effect | Idempotency, transaction semantics, reconciliation. |

### Quy trình điều tra từng bước

1. **Xác định framework thực sự:** Servlet MVC/Tomcat hay WebFlux/Netty? Có cả hai starters không?
2. **Xác định Java runtime/config:** Java 21, spring.threads.virtual.enabled được áp dụng chưa?
3. **Phân loại workload:** CPU busy, DB wait, HTTP wait, lock contention hay queues?
4. **So server/DB/client pool metrics** và xác định saturation đầu tiên.
5. **Kiểm tra tail latency và error rate** ở cùng offered load.
6. **Với VT**, thu JFR pinning/ThreadLocal/heap nếu không scale như kỳ vọng.
7. **Với reactive**, kiểm tra event-loop blocking, scheduler switches, buffer, flatMap concurrency.
8. **Tối ưu một bottleneck** rồi chạy lại workload giống trước; tránh đổi cùng lúc 10 config.
9. **Thêm overload protection** thay vì chỉ tăng số in-flight requests.
10. **Review security, cancellation và correctness**: latency nhanh không có giá trị nếu làm mất transaction consistency.

## 22. Bài tập vận dụng

### Bài 1 — Cơ chế Java 21

Chạy ThreadModelsMain với fixed platform pool=4 và virtual-per-task. So completed count, virtualCount và elapsedMs. Giải thích vì sao 40 Thread.sleep có wall time khác nhau, và vì sao không thể từ đó kết luận hiệu năng database thật.

### Bài 2 — Hai chế độ Spring MVC

Chạy MVC project ở platform rồi virtual mode, gọi GET /wait?ms=250 và xác minh virtualThread boolean. Chạy LocalLoadProbe với 200 requests/concurrency 32, ghi wallMs, p95 và tỷ lệ thành công. Lặp 5 lần, so kết quả chứ không chỉ vòng nhanh nhất.

### Bài 3 — Nâng độ khó platform tuning

Giữ MVC platform mode, thử server.tomcat.threads.max=8, 16, 32 tại cùng load test. Theo dõi CPU, request queue và timeout. Kết luận mức nào đạt SLO tốt nhất, không mặc định càng lớn càng tốt.

### Bài 4 — Event-loop anti-pattern

Trong bản sao WebFlux lab, thử chèn Thread.sleep(250) vào method handler trước khi trả Mono, sau đó đo latency khi concurrency tăng. Phục hồi Mono.delay và giải thích tại sao event loop bị chặn có thể làm chậm nhiều unrelated requests. **Chỉ thử trên môi trường lab**, không đưa endpoint cố tình chặn vào production.

### Bài 5 — Blocking SDK và boundedElastic

Giả định một thư viện legacy dùng JDBC đồng bộ. Minh họa Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) và phân tích worker limit, queue, cancellation. So với phương án MVC + VT khi phần lớn business code đều blocking.

### Bài 6 — DB connection pool 8

Tạo một mock downstream cho phép tối đa 8 operations cùng lúc và latency 100 ms. So trường hợp 16 platform workers, 100 virtual tasks và reactive flatMap(concurrency=8). Giải thích vì sao cả ba có thể bị bound bởi 8 connections, và cách bảo vệ DB khỏi overload.

### Bài 7 — Pinning Java 21

Tạo code có blocking I/O trong synchronized block trên JDK21, thu JFR jdk.VirtualThreadPinned. Thu hẹp synchronized section hoặc thay design locking rồi đo lại. Không đổi mọi synchronization mà không kiểm thử thread safety.

### Bài 8 — Chọn mô hình thực tế

Đưa ra lựa chọn cho ba ứng dụng:
- CRUD REST dùng Spring Data JPA/JDBC blocking, traffic tăng cao và Java 21 đã được phê duyệt.
- Chat/streaming gateway dùng WebClient và R2DBC non-blocking.
- Batch tính toán ảnh dùng CPU 95% thời gian.

Với mỗi ứng dụng, nêu lựa chọn ban đầu, bottleneck, migration cost, giới hạn resource và metric quyết định thành công.

## 23. Checklist trước khi thay thread model ở production

- [ ] Workload đã được profile: CPU-bound hay I/O-bound, bottleneck rõ ràng.
- [ ] Có baseline RPS, p95/p99, errors, CPU, memory, GC, queue, DB pool.
- [ ] Java version phù hợp; VT chỉ trên Java 21+ và JDK-specific pinning được xem xét.
- [ ] Nếu bật VT, kiểm tra controller real HTTP thread.isVirtual() và custom executors.
- [ ] Không tạo fixed virtual-thread pool; giới hạn concurrency bằng resource-level bulkheads.
- [ ] Connection pools, timeouts, retries và downstream rate limits đã kiểm soát.
- [ ] JFR được dùng khi nghi pinning/lock contention trên JDK21.
- [ ] ThreadLocal/MDC/security context không giữ state quá lớn và được dọn đúng scope.
- [ ] Nếu dùng WebFlux, blocking SDKs không chạy trên event loops.
- [ ] Flux/Mono pipelines có backpressure, buffer bounds và cancellation semantics phù hợp.
- [ ] Kiểm tra Boot application type khi có cả web và webflux starters.
- [ ] ApplicationTaskExecutor/@Async/@Scheduled lifecycle được kiểm chứng; keep-alive khi cần.
- [ ] Tests của model thật chạy qua RANDOM_PORT, không chỉ MockMvc.
- [ ] Benchmark có warmup, repeated runs, fixed resources, p95/p99 và error rates.
- [ ] Không log JWT/Authorization/Cookie vào traces/metrics hay profile artifacts.
- [ ] Có plan rollback config nếu tail latency/connection exhaustion xấu đi.
- [ ] Kubernetes readiness/liveness, graceful shutdown và autoscaling không dựa sai vào số threads.
- [ ] Đánh giá cả mức độ dễ debug, bảo trì, đào tạo và compatibility của drivers.

## 24. Câu hỏi tự kiểm tra

**1. Virtual threads tạo thêm CPU cores?** Không. Chúng chủ yếu giảm chi phí nhiều tác vụ chờ I/O đồng thời.

**2. Platform thread pool đã bão hòa thì có phải tăng maxThreads ngay?** Không. Đầu tiên đo CPU, DB/client connection pool, queue và bottleneck.

**3. Virtual thread có thể gọi JDBC blocking được không?** Có. Code imperative vẫn hoạt động; hiệu quả unmount phụ thuộc library/JVM, và DB pool vẫn giới hạn concurrency.

**4. Java 17 có chạy spring.threads.virtual.enabled=true đúng không?** Virtual threads yêu cầu Java 21+, nên không áp dụng trên Java 17.

**5. Có nên pool virtual threads thành 100 workers?** Không phải cách dùng khuyến nghị. Dùng per-task virtual thread và bulkhead cho tài nguyên khan hiếm.

**6. Reactor Mono.delay là virtual thread?** Không. Đây là timer publisher non-blocking theo mô hình Reactor, khác virtual threads của Java.

**7. Có thể gọi Thread.sleep trong WebFlux event loop không?** Không nên; nó chặn event loop và gây starvation.

**8. Reactive backpressure thay thế connection pool/rate limiting?** Không. Backpressure điều tiết nhu cầu item trong stream, không tự giới hạn mọi outbound requests.

**9. Thêm spring-boot-starter-webflux vào app có starter-web có tự chuyển sang Netty server?** Không, Boot 3.3 ưu tiên Spring MVC nếu cả hai starters cùng có.

**10. Thấy virtualThread=false trong Reactor callback có nghĩa WebFlux không concurrent?** Không; non-blocking async concurrency không yêu cầu virtual threads.

**11. JDK21 có vấn đề gì với synchronized?** Blocking dài bên trong monitor có thể pin virtual thread trên carrier, ảnh hưởng throughput.

**12. Benchmark sleep-only có đủ chọn production architecture?** Không. Phải đo workload real I/O/CPU, database pools, error rates và p95/p99 trên môi trường giống production.

## 25. Tài liệu chính thức

1. [Spring Boot 3.3 — SpringApplication: Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): spring.threads.virtual.enabled, thread-pool properties, pinning và keep-alive.
2. [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): applicationTaskExecutor, @Async, @Scheduled và virtual threads.
3. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Spring MVC, Tomcat connector và MVC web runtime.
4. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Spring WebFlux, Reactor, WebFlux dependency, MVC precedence.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): real HTTP RANDOM_PORT integration testing và web application type.
6. [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual threads, carrier scheduling, pinning và JFR.
7. [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual thread programming model, throughput và structured concurrency distinctions.
8. [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): cải tiến monitor pinning trên JDK24.
9. [Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): Mono/Flux scheduling, boundedElastic, publishOn và subscribeOn.
10. [Spring Framework 6.1 — WebFlux Overview](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/new-framework.html): mục tiêu non-blocking I/O của WebFlux và lựa chọn MVC/WebFlux.
11. [Reactive Streams Specification](https://www.reactive-streams.org/): request(n), demand, backpressure và publisher/subscriber contract.

**Kết luận:** tối ưu hiệu năng Spring Boot phải bắt đầu từ **bottleneck và SLO**, không phải từ việc đổi tên framework. Với Spring MVC và traffic vừa phải, tuning platform thread pool, timeouts và downstream resources có thể là đủ. Với Java 21 và ứng dụng chủ yếu **blocking I/O**, **virtual threads** cho phép giữ code imperative dễ đọc trong khi giảm chi phí mỗi request đang chờ, nhưng vẫn cần bảo vệ DB/network và kiểm tra pinning. Với kiến trúc end-to-end **non-blocking** và streaming, **WebFlux/Reactor** cho event-loop I/O, composition và backpressure rõ ràng, đổi lại độ phức tạp pipeline/context. **Không mô hình nào loại bỏ giới hạn CPU, kết nối, bộ nhớ hoặc downstream capacity; hãy thử, đo, kiểm chứng và rollout dần.**