# Luồng ảo trong Java 21 và phạm vi Spring Boot hỗ trợ

## 1. Virtual thread là gì và vì sao cần hiểu đúng?

**Virtual thread** là một loại **java.lang.Thread** nhẹ do JVM quản lý. Java 21 chuẩn hóa virtual threads theo **JEP 444**, không cần bật tính năng preview. Chúng cho phép code viết theo phong cách đồng bộ, một luồng cho một tác vụ, nhưng có thể phục vụ số lượng rất lớn tác vụ đồng thời đang chờ I/O mà không giữ một OS thread riêng cho mỗi tác vụ.

Đối chiếu:

- **Platform thread**: một Java thread truyền thống thường giữ một OS thread trong suốt vòng đời. Khi đang đợi JDBC, socket hoặc HTTP response, OS thread vẫn bị chiếm.
- **Virtual thread**: JVM có thể mount virtual thread lên một **carrier thread** (platform thread), rồi unmount khi gặp blocking I/O được hỗ trợ, nhường carrier cho virtual thread khác. Khi I/O sẵn sàng, virtual thread được tiếp tục.
- **Không có CPU miễn phí**: mã CPU-bound vẫn cần CPU core. Virtual thread giúp khả năng mở rộng khi **nhiều tác vụ chờ I/O**, không làm một truy vấn DB hay phép tính đơn lẻ tự chạy nhanh.

Sơ đồ khái niệm:

~~~text
Platform thread:
Request A -> waiting for DB ... -> response
(OS thread bi giu trong thoi gian cho)

Virtual thread:
Request A -> waiting for DB -> unmount from carrier
                                |
                                +-> carrier chay request B/C
DB responds -> virtual A resumes -> response
~~~

Virtual thread không phải coroutine ở tầng Spring, không phải Kafka worker mới và không tự chuyển hệ thống sang lập trình reactive. Nó vẫn là Thread của Java, dùng được try/catch, stack trace, synchronized, ThreadLocal và nhiều API đồng bộ.

## 2. So sánh nhanh platform và virtual threads

| Thuộc tính | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Java type | java.lang.Thread | java.lang.Thread |
| Gắn OS thread | Thường gắn lâu dài | Được mount/unmount trên carrier |
| Chi phí tạo/số lượng | Tương đối cao, chịu giới hạn OS | Nhẹ hơn, phù hợp rất nhiều tác vụ đang chờ |
| Định hướng sử dụng | Worker pool, CPU-bound, native calls | Thread-per-request/task với blocking I/O |
| Tái sử dụng thread qua pool | Thường có | **Không nên pool virtual threads** |
| Daemon thread | Có thể daemon/non-daemon | **Luôn daemon** |
| ThreadLocal | Có | Có, nhưng nhiều thread có thể tốn RAM |
| Điều phối | Hệ điều hành điều phối OS thread | JVM điều phối virtual lên carrier |
| Tăng tốc code CPU | Không tự động | Không tự động |

Một request làm việc liên tục trên CPU thường không hưởng lợi đáng kể. Một request dành phần lớn thời gian chờ từ HTTP/JDBC có thể giúp server tăng throughput khi đổi sang virtual threads, **nếu** downstream, connection pool, heap và carrier không trở thành bottleneck mới.

## 3. Các API Java 21 quan trọng

Java 21 hỗ trợ:

- **Thread.startVirtualThread(Runnable)**: tạo và chạy một virtual thread.
- **Thread.ofVirtual().name(...).start(...)**: tạo với builder.
- **Executors.newVirtualThreadPerTaskExecutor()**: executor tạo một virtual thread cho mỗi task.
- **Thread.currentThread().isVirtual()**: xác minh thread hiện tại.
- **Future.get()** hoặc **join()**: phối hợp chờ completion.

Ví dụ ngắn:

~~~java
Thread worker = Thread.ofVirtual().name("io-task").start(
        () -> System.out.println(Thread.currentThread().isVirtual()));
worker.join();
~~~

Đây là đoạn Java 21 minh họa trong một method có thể ném InterruptedException. Khi chạy đúng, nó in true. Không có yêu cầu --enable-preview cho virtual threads của Java 21.

### Chương trình Java 21 chạy độc lập

Tạo **VirtualThreadBasics.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadBasics {
    public static void main(String[] args) throws Exception {
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 3; i++) {
                results.add(executor.submit(() -> {
                    Thread.sleep(40);
                    return Thread.currentThread().isVirtual();
                }));
            }

            for (int i = 0; i < results.size(); i++) {
                System.out.println("task-" + (i + 1)
                        + " virtual=" + results.get(i).get());
            }
        }

        System.out.println(
                "main virtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

Chạy với JDK 21:

~~~bash
javac VirtualThreadBasics.java
java VirtualThreadBasics
~~~

Các dòng của chương trình theo thứ tự:

~~~text
task-1 virtual=true
task-2 virtual=true
task-3 virtual=true
main virtual=false
~~~

Các task có thể hoàn tất theo thứ tự tùy ý, nhưng main đọc **Future** theo thứ tự danh sách nên kết quả in ra xác định. Main bình thường do Java launcher tạo trên platform thread. Thread.sleep(40) chỉ minh họa blocking; không dùng sleep làm cơ chế đồng bộ trong sản phẩm.

**Không cần tạo virtual thread pool kích thước cố định.** Mô hình dự định là một virtual thread mỗi task; giới hạn truy cập database hoặc API phải do connection pool, Semaphore, bulkhead hoặc rate limiter phụ trách.

## 4. Điều kiện Spring Boot hỗ trợ

**Spring Boot 3.2** giới thiệu tích hợp virtual threads. Trong ví dụ chọn **Spring Boot 3.3.x + Spring Framework 6.1.x + Java 21** để có API rõ ràng.

Để bật các integration do Spring Boot quản lý:

~~~properties
spring.threads.virtual.enabled=true
~~~

Điều kiện:

1. **JVM chạy thật phải là Java 21 hoặc cao hơn**, không chỉ sourceCompatibility 21.
2. Spring Boot phải ở một phiên bản hỗ trợ, ví dụ 3.2 trở lên.
3. Property phải có hiệu lực trong profile đang chạy.
4. Component phải dùng **executor/container do Boot cấu hình virtual** hoặc được tự cấu hình thích hợp. Thread do code hay thư viện bên ngoài tự tạo không đổi loại chỉ nhờ property.

**Java 21 không tự bật property.** Nếu không khai báo spring.threads.virtual.enabled=true, Spring Boot 3.3 vẫn dùng executor truyền thống tại những điểm auto-configuration tương ứng.

### Bảng phạm vi tích hợp đáng nhớ

| Thành phần | Hỗ trợ trong Spring Boot 3.2+/3.3 khi bật đúng | Giới hạn |
| --- | --- | --- |
| Embedded Tomcat + Spring MVC | Xử lý HTTP request trên virtual thread | Chỉ với container/cấu hình được Boot hỗ trợ |
| Embedded Jetty servlet | Có hỗ trợ virtual threads khi phiên bản tương thích | Custom executor có thể làm khác |
| Auto-configured applicationTaskExecutor | SimpleAsyncTaskExecutor dùng virtual threads | Không còn pool ThreadPoolTaskExecutor truyền thống |
| @Async kết hợp @EnableAsync | Có thể dùng executor ảo của Boot | Custom Executor/AsyncConfigurer hoặc self-invocation thay đổi kết quả |
| Spring MVC asynchronous request handling | Dùng applicationTaskExecutor được hỗ trợ | Không có nghĩa mọi handler là async |
| Spring for GraphQL Callable async handling | Có thể tận dụng auto TaskExecutor | Phụ thuộc integration và executor thực tế |
| Spring WebFlux blocking offload support | Có thể dùng auto AsyncTaskExecutor | **Reactor Netty event loops không tự đổi thành virtual threads** |
| @Scheduled với auto TaskScheduler | SimpleAsyncTaskScheduler hỗ trợ virtual threads | fixedDelay có giới hạn một scheduler thread |
| Kafka/Rabbit listener integrations do Boot auto-config | Có cấu hình executor ảo ở các integration được hỗ trợ | Không đồng nghĩa mọi poll loop/worker tự tạo đều ảo |
| Custom TaskExecutor/TaskScheduler | Chỉ ảo nếu được cấu hình rõ | Flag Boot không bắt custom pool tự đổi |
| Undertow/server bên ngoài | Phải kiểm tra riêng | Không suy rộng từ Tomcat/Jetty |
| Database, Redis server, Kafka broker | Không bị tác động | Đây là process/hệ thống khác JVM |

Để kiểm chứng một component cụ thể, hãy đo **Thread.currentThread().isVirtual()** ngay trong method đó và kiểm tra executor/container thực tế, thay vì suy luận từ tên class hoặc property.

## 5. Cấu hình tối thiểu và JVM keep-alive

Trong **src/main/resources/application.properties**:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

YAML tương đương:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
~~~

**spring.main.keep-alive=true** quan trọng vì **virtual threads luôn là daemon threads**. JVM có thể thoát nếu không còn non-daemon thread. Trường hợp điển hình là một ứng dụng chỉ có **@Scheduled** và virtual scheduler, không có web server hoặc thành phần khác giữ tiến trình sống.

Không nên bật keep-alive một cách mù quáng cho **CLI/batch cần chạy xong rồi thoát**: property có thể khiến process còn sống sau khi công việc chính hoàn tất. Web server có thể đã có non-daemon thread khác, nhưng không dựa vào một giả định như vậy cho ứng dụng scheduler-only.

Kiểm tra runtime:

~~~bash
java -version
~~~

Đảm bảo Java 21 thật sự được dùng trong container image, process chạy bằng Gradle/Maven và môi trường CI/CD.

## 6. Ví dụ hoàn chỉnh Spring Boot 3.3 và Java 21

Ứng dụng Spring MVC dưới đây kiểm chứng hai đường:

- **HTTP request thread** do embedded Tomcat điều phối.
- **@Async method** chạy qua Spring Boot auto-configured applicationTaskExecutor.

### Cấu trúc tệp

~~~text
virtual-thread-boot-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          VirtualThreadDemo.java
      resources/
        application.properties
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'virtual-thread-boot-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Cần JDK 21, Gradle tương thích và quyền tải dependency hoặc cache sẵn.

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Tệp **src/main/java/example/VirtualThreadDemo.java**:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class VirtualThreadDemo {
    public static void main(String[] args) {
        SpringApplication.run(VirtualThreadDemo.class, args);
    }
}

@Service
class AsyncProbeService {
    @Async
    public CompletableFuture<Boolean> checkAsyncThread() {
        boolean virtual = Thread.currentThread().isVirtual();
        return CompletableFuture.completedFuture(virtual);
    }
}

@RestController
class ThreadProbeController {
    private final AsyncProbeService service;

    ThreadProbeController(AsyncProbeService service) {
        this.service = service;
    }

    @GetMapping("/threads")
    public Map<String, Boolean> checkThreads() throws Exception {
        boolean requestVirtual = Thread.currentThread().isVirtual();
        boolean asyncVirtual =
                service.checkAsyncThread().get(5, TimeUnit.SECONDS);

        return Map.of(
                "requestVirtual", requestVirtual,
                "asyncVirtual", asyncVirtual);
    }
}
~~~

**Tại sao ví dụ có thể chạy:**

- Class public duy nhất trùng tên tệp, các class còn lại package-private.
- @EnableAsync bật hạ tầng proxy cho @Async.
- Controller gọi method async **qua bean AsyncProbeService được inject**, không tự gọi qua this.
- Không có Executor hay AsyncConfigurer tùy chỉnh, nên Spring Boot có thể dùng executor ảo tự cấu hình.
- @Async trả CompletableFuture<Boolean>, controller lấy kết quả bằng get(timeout).
- Dùng starter-web mặc định có embedded Tomcat, thay vì chạy WebFlux Reactor Netty.

### Chạy và đối chiếu

Nếu có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chỉ có Gradle tương thích đã cài, dùng gradle bootRun.

Từ terminal khác:

~~~bash
curl -s http://localhost:8080/threads
~~~

Với Spring Boot 3.3, JDK 21, Tomcat mặc định và virtual=true, hai giá trị dự kiến là:

~~~json
{"requestVirtual":true,"asyncVirtual":true}
~~~

**Không phụ thuộc thứ tự key trong JSON**: Map.of không cam kết thứ tự tuần tự hóa. Hãy so sánh giá trị của requestVirtual và asyncVirtual.

Thử đổi thành:

~~~properties
spring.threads.virtual.enabled=false
~~~

Khởi động lại. Với cấu hình Tomcat và executor thông thường, kết quả dự kiến:

~~~json
{"requestVirtual":false,"asyncVirtual":false}
~~~

Nếu khác, kiểm tra profile override, custom executor, JDK, web container và startup flags. **Dữ liệu trả về chỉ nói về đường thực thi đang được đo**, không chứng minh mọi thread trong ứng dụng đều virtual.

## 7. @Async và auto-configured TaskExecutor

Theo Spring Boot 3.3:

- Nếu không có custom Executor làm thay đổi điều kiện auto-config và virtual threads tắt, Boot thường cấu hình **ThreadPoolTaskExecutor**.
- Nếu virtual threads bật trên Java 21+, Boot thường cấu hình **SimpleAsyncTaskExecutor** với virtual threads.
- Executor này được sử dụng ở những integration được Boot hỗ trợ, như @EnableAsync và Spring MVC asynchronous processing.
- Một **AsyncConfigurer/Executor tùy chỉnh** có thể thay thế executor mặc định.
- Với một số web integration, custom bean muốn được sử dụng phải có tên/kiểu phù hợp, chẳng hạn **applicationTaskExecutor** kiểu **AsyncTaskExecutor**.

**Các property dành cho thread pool không còn ý nghĩa cấu hình virtual-thread pool**. Ví dụ:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

Những thuộc tính này dành cho pool-based ThreadPoolTaskExecutor và không giới hạn virtual threads của SimpleAsyncTaskExecutor. Tuy nhiên **không phải mọi property task execution đều vô hiệu**; prefix/tùy chỉnh khác có thể còn áp dụng tùy phiên bản.

**@Async không tự có virtual threads nếu thiếu @EnableAsync** hoặc lời gọi **this.asyncMethod()** bỏ qua Spring proxy. Với @Async trả void, exception trong worker không tự lan về publisher/caller sau khi task đã submit. Dùng kết quả Future, error handler, metrics hoặc message queue khi cần bảo đảm thực hiện.

## 8. Không pool virtual threads; giới hạn tài nguyên downstream

Virtual thread tương ứng với một task. Nếu cần giới hạn tối đa 20 HTTP calls đồng thời, dùng cơ chế giới hạn **tài nguyên**, không tạo “virtual thread pool size 20”.

Ví dụ minh họa trong một service:

~~~java
private final Semaphore permits = new Semaphore(20);

public String limitedCall() throws InterruptedException {
    permits.acquire();
    try {
        return blockingHttpCall();
    } finally {
        permits.release();
    }
}
~~~

Đây là đoạn minh họa, cần import Semaphore và định nghĩa blockingHttpCall(). Trong production có thể dùng tryAcquire(timeout), rate limiter, bulkhead/circuit breaker và metrics.

Một HikariCP connection pool có 10 connections **không thể chạy 1.000 truy vấn đồng thời chỉ vì có 1.000 virtual threads**. Nhiều virtual threads sẽ đợi connection, có thể gặp timeout và memory pressure. Tương tự, API downstream vẫn có quota và tốc độ xử lý hữu hạn.

| Tài nguyên | Có tăng vô hạn nhờ virtual threads không? |
| --- | --- |
| CPU cores | Không |
| JDBC connections | Không |
| HTTP connection pool | Không |
| Kafka partitions | Không |
| Remote API quota | Không |
| RAM / heap | Không |
| File descriptors | Không |
| Business exactly-once | Không |

Lợi ích đo được là **khả năng giữ nhiều tác vụ đang chờ I/O** với chi phí thread thấp hơn, không phải mở rộng vô hạn các dependency.

## 9. @Scheduled và SimpleAsyncTaskScheduler

Spring Boot 3.3 có thể auto-configure scheduler khi ứng dụng dùng **@EnableScheduling**. Nếu virtual threads bật, scheduler được auto-config thường là **SimpleAsyncTaskScheduler**; khi tắt thường là **ThreadPoolTaskScheduler**.

Ví dụ trích đoạn, cần các import Spring Scheduling:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfig {
}

@Component
class ScheduledProbe {
    @Scheduled(fixedRate = 5000, initialDelay = 5000)
    public void tick() {
        System.out.println(
                "scheduled virtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

Với SimpleAsyncTaskScheduler và fixedRate, công việc có thể chạy trên virtual thread. **Lưu ý quan trọng**: **@Scheduled(fixedDelay=...)** dùng scheduler thread duy nhất trong SimpleAsyncTaskScheduler để giữ fixed-delay semantics. Vì vậy nó **không tương đương một virtual thread độc lập cho mỗi lần gọi** và một fixed-delay task chậm có thể cản các fixed-delay task khác.

Spring Framework 6.1 khuyến nghị cân nhắc **fixedRate hoặc cron** khi muốn tận dụng mô hình virtual per task. Nhưng fixedRate/cron có thể tạo overlapping invocations nếu công việc lâu, nên cần thiết kế chống chạy chồng, lock, rate limiting hoặc scheduler/job riêng.

Đối với scheduler-only app, lưu ý **virtual threads đều daemon**: bật **spring.main.keep-alive=true** nếu không có non-daemon thread nào khác giữ JVM chạy.

## 10. Spring MVC khác Spring WebFlux

### Spring MVC + embedded Tomcat hoặc Jetty

Tích hợp Boot 3.2+ có thể dùng virtual threads cho **servlet request processing** của Tomcat/Jetty. Code controller kiểu đồng bộ vẫn có thể gọi JDBC hoặc HTTP blocking API, trong khi carrier được nhường ở chỗ I/O thích hợp.

Ví dụ minh họa:

~~~java
@GetMapping("/customer")
public Customer customer() {
    return customerRepository.findOneRequired();
}
~~~

Đoạn code không độc lập: Customer và customerRepository là thành phần nghiệp vụ cần định nghĩa. **Virtual threads không làm truy vấn DB nhanh hơn**, nhưng có thể giúp nhiều request chờ đồng thời hiệu quả hơn.

### Spring WebFlux + Reactor Netty

WebFlux trên Reactor Netty dựa vào **event loop** và reactive/non-blocking I/O. Bật spring.threads.virtual.enabled **không chuyển Netty event-loop threads thành virtual threads**. Spring Boot chỉ có thể dùng executor ảo cho những đường **blocking execution support/offload** mà framework tích hợp.

Đừng đặt một blocking JDBC call trực tiếp trên event-loop rồi nghĩ property đã bảo vệ. Cần reactive driver hoặc offload đúng cách. Chọn mô hình servlet blocking + virtual threads hay WebFlux reactive dựa trên workload, thư viện và kỹ năng vận hành, không trộn vô nguyên tắc.

### Các thư viện và thread tùy chỉnh

Thread do ứng dụng tự tạo bằng ThreadPoolExecutor, custom scheduler, Kafka client internal polling, thư viện native, Netty event loop hay một container không do Boot quản lý **không tự đổi**. Dù các tích hợp Kafka/RabbitMQ của Boot có hỗ trợ virtual executor ở những đường nhất định, hãy kiểm tra thực tế từng listener/container, không giả định toàn bộ mọi thread đều ảo.

## 11. Pinning trên JDK 21

Một hạn chế đáng lưu ý trong **JDK 21** là virtual thread bị **pinned** khi gặp một số blocking operations trong vùng **synchronized** hoặc native/foreign call. Carrier không được giải phóng, làm giảm throughput nếu pinning nhiều và kéo dài.

Ví dụ pseudocode Java:

~~~java
private final Object monitor = new Object();

String fetch() {
    synchronized (monitor) {
        return slowBlockingHttpCall();
    }
}
~~~

Nếu slowBlockingHttpCall() thực sự chặn lâu trong synchronized trên JDK21, carrier có thể bị giữ. Điều này **không nhất thiết làm chương trình sai**, nhưng có thể làm khả năng mở rộng kém.

Khi đo thấy pinning thường xuyên, có thể tái cấu trúc critical section hoặc cân nhắc ReentrantLock:

~~~java
private final ReentrantLock lock = new ReentrantLock();

String fetch() {
    lock.lock();
    try {
        return slowBlockingHttpCall();
    } finally {
        lock.unlock();
    }
}
~~~

Hai đoạn trên **không là chương trình độc lập**; cần định nghĩa slowBlockingHttpCall và import ReentrantLock. **Không thay mọi synchronized một cách máy móc.** Monitor ngắn, không blocking dài có thể vẫn phù hợp.

Cách chẩn đoán JDK21:

- JFR event **jdk.VirtualThreadPinned**.
- JVM flag **-Djdk.tracePinnedThreads=full** hoặc **short** theo khả năng JDK21.
- **jcmd** virtual-thread dump/stack trace.
- Benchmark throughput và CPU/carrier utilization.

Lưu ý: JDK mới hơn, đặc biệt từ JDK24, có thay đổi đáng kể về monitor pinning. Bài này tập trung **Java 21**, không khẳng định hành vi synchronized của mọi JDK đều giống JDK21.

## 12. ThreadLocal, transaction và context propagation

Virtual threads vẫn hỗ trợ ThreadLocal, nhưng số lượng thread có thể rất lớn:

- ThreadLocal nặng trên hàng nghìn task làm heap tăng.
- MDC, SecurityContext, transaction context có thể gắn với thread đang chạy; chuyển qua **@Async** là chuyển thread.
- **@Async không tự chuyển Spring transaction** của request sang worker virtual thread.
- Muốn giữ logging/security/tracing context, dùng TaskDecorator hoặc context propagation được framework hỗ trợ, và xác định transaction boundary rõ ràng.
- Không dựa vào thread name hoặc thread ID để làm business key.

Virtual threads giúp ta giữ phong cách code blocking dễ đọc; chúng **không thay đổi quy tắc an toàn của transaction**, cancellation và dữ liệu chia sẻ giữa threads.

## 13. InterruptedException, shutdown và daemon behavior

Một virtual thread vẫn tuân thủ nhiều quy tắc Thread thông thường. Nếu chờ I/O hoặc sleep có khả năng interruption, cần xử lý có trách nhiệm:

~~~java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted", e);
}
~~~

Đây là đoạn minh họa trong method. Không nuốt interruption rồi tiếp tục vòng lặp vô hạn.

Khi dùng ExecutorService tự tạo, hãy đóng executor ở ranh giới lifecycle được quản lý. Với @Async, việc task chạy trên virtual thread **không làm nó tự hoàn thành nếu request đã kết thúc**; cần ownership, timeout, cancellation và error reporting riêng.

**Virtual threads là daemon threads**, do đó nếu chương trình chỉ còn chúng, JVM có thể thoát. Với batch tác vụ cần hoàn tất, main nên đợi Future và đóng executor đúng cách. Với scheduler-only long-lived app, cân nhắc spring.main.keep-alive=true.

## 14. Hiệu năng: đo đúng thứ cần đo

Các số liệu cần so sánh trước/sau bật cờ:

1. **Throughput**: requests/second hoặc tasks/second trên cùng workload.
2. **p50, p95, p99 latency**: virtual threads không đảm bảo giảm độ trễ từng request.
3. **CPU utilization và GC**: không tạo thêm CPU core, heap có thể tăng nếu nhiều tasks tồn đọng.
4. **Database connection wait**, connection timeout và query latency.
5. **HTTP client pool saturation**, downstream rate limits và error rate.
6. **Pinned virtual threads** trên JDK21, thời gian và tần suất pinning.
7. **ThreadLocal/MDC overhead**, context propagation và bộ nhớ.
8. **Executor/task backlog**, backpressure, cancellation và shutdown behavior.
9. **Khả năng khôi phục** khi downstream chậm hoặc ngắt kết nối.
10. **Số replica và resource limits** trong container/Kubernetes.

Một test với một request hoặc một vòng for tạo 1.000 virtual threads **không đủ** để kết luận production sẽ nhanh hơn. Thử workload thực, giữ nguyên DB pool, latency downstream và giới hạn CPU/RAM để so sánh công bằng.

## 15. Checklist bật virtual threads trong dự án

Trước khi triển khai:

- Xác nhận JVM production dùng **Java 21+**.
- Xác nhận Spring Boot **3.2+** và kiểm tra tài liệu đúng phiên bản.
- Bật **spring.threads.virtual.enabled=true** trong profile đúng.
- Đo **Thread.currentThread().isVirtual()** ở controller, @Async, scheduler và consumer mà bạn quan tâm.
- Kiểm tra có **Executor, AsyncConfigurer, TaskScheduler, servlet executor tùy chỉnh** hay không.
- Đừng coi Reactor Netty event loop là servlet thread-per-request.
- Phân tích I/O blocking, JDBC/HTTP connection pool và mức concurrency dự kiến.
- Dùng **Semaphore/rate limit/bulkhead** để giới hạn downstream.
- Với JDK21, kiểm tra pinning ở synchronized/native hot paths.
- Đánh giá ThreadLocal, MDC, security và transaction propagation.
- Xem **@Scheduled(fixedDelay)** và nguy cơ scheduler thread bị chiếm.
- Với scheduler-only app, kiểm tra **spring.main.keep-alive=true**.
- Đo benchmark throughput/latency/memory và thử shutdown.
- Có khả năng rollback property nếu hiệu năng thực giảm.

## 16. Các lỗi hiểu sai thường gặp

**“JDK21 tự làm Spring Boot dùng virtual thread.”** Không. Cần property và tích hợp phù hợp.

**“Virtual threads giúp CPU tăng tốc.”** Không. Lợi ích chính là concurrency với blocking I/O.

**“Mỗi virtual thread có OS thread riêng.”** Không. JVM điều phối trên carrier.

**“Bật property làm mọi ThreadPoolExecutor của thư viện thành ảo.”** Không. Những executor được tạo riêng phải cấu hình riêng.

**“@Async luôn chạy virtual chỉ vì đã thêm annotation.”** Không. Cần @EnableAsync, lời gọi qua proxy và executor phù hợp.

**“spring.task.execution.pool.max-size giới hạn virtual threads.”** Không với SimpleAsyncTaskExecutor dùng virtual threads.

**“Nên pool virtual threads như platform threads.”** Không. Tạo theo task và giới hạn downstream.

**“WebFlux trên Reactor Netty tự chuyển mọi handler sang virtual.”** Không. Event loop vẫn dùng mô hình reactive.

**“@Scheduled(fixedDelay) dùng virtual thread riêng cho mọi lượt.”** Không với SimpleAsyncTaskScheduler trong Spring Framework 6.1.

**“Virtual threads sẽ giữ JVM sống cho scheduler-only process.”** Không. Chúng là daemon.

**“Pinning nghĩa là code Java luôn sai.”** Không; thường là vấn đề throughput khi blocking dài/thường xuyên.

**“Pinning không thể có khi dùng synchronized.”** Sai trên JDK21.

**“DB có 10 connections nhưng 10.000 virtual tasks đều query song song.”** Không. Connection pool vẫn là giới hạn.

**“@Async tự kế thừa transaction caller.”** Không. Transaction context thread-bound cần xử lý riêng.

**“Tăng virtual-thread count luôn tốt hơn.”** Không. Có thể gây overload downstream và tăng memory pressure.

**“Cần bật preview flag cho Thread.ofVirtual ở Java21.”** Không.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Virtual thread trong Java21 có khác loại java.lang.Thread?  
**Đáp án:** Không. Nó vẫn là java.lang.Thread nhưng được JVM quản lý/mount lên carrier.

**Câu 2:** Lúc virtual thread chờ blocking I/O được hỗ trợ, carrier có thể phục vụ task khác không?  
**Đáp án:** Có, nếu virtual thread unmount được và không bị pinning.

**Câu 3:** Java21 cần --enable-preview cho virtual thread không?  
**Đáp án:** Không.

**Câu 4:** Spring Boot bắt đầu hỗ trợ tích hợp virtual threads từ phiên bản nào?  
**Đáp án:** 3.2; cần Java 21 trở lên và bật spring.threads.virtual.enabled=true.

**Câu 5:** Boot 3.3 auto-config TaskExecutor nào khi virtual=true?  
**Đáp án:** SimpleAsyncTaskExecutor sử dụng virtual threads, nếu điều kiện auto-config không bị custom bean thay đổi.

**Câu 6:** Tomcat servlet controller có thể chạy trên virtual thread không?  
**Đáp án:** Có với Spring Boot tích hợp phù hợp; kiểm chứng bằng Thread.isVirtual().

**Câu 7:** Bật property có đổi Netty event-loop threads thành virtual không?  
**Đáp án:** Không.

**Câu 8:** Vì sao fixedDelay có caveat khi dùng SimpleAsyncTaskScheduler?  
**Đáp án:** Các fixed-delay tasks chạy trên scheduler thread duy nhất, khác cơ chế virtual-per-task cho fixedRate/cron.

**Câu 9:** Vì sao scheduler-only app cần lưu ý spring.main.keep-alive?  
**Đáp án:** Virtual threads là daemon, JVM có thể thoát khi không còn non-daemon threads.

**Câu 10:** Virtual thread có giúp một JDBC query 500 ms tự giảm còn 50 ms không?  
**Đáp án:** Không. Nó có thể giúp tăng số request đang chờ đồng thời, không tăng tốc query tự thân.

**Câu 11:** Vì sao không pool virtual threads để giới hạn DB calls?  
**Đáp án:** Pool virtual threads không phải công cụ giới hạn tài nguyên; dùng connection pool, Semaphore hoặc bulkhead.

**Câu 12:** Pinning JDK21 đáng lo khi nào?  
**Đáp án:** Khi blocking I/O trong synchronized/native section diễn ra thường xuyên và lâu, giữ carrier.

**Câu 13:** @Async tự truyền Spring transaction của caller sang virtual thread khác không?  
**Đáp án:** Không. Cần transaction boundary và context propagation phù hợp.

**Câu 14:** Benchmark tối thiểu cần đo những gì?  
**Đáp án:** Throughput, p95/p99 latency, CPU, memory/GC, pinning, connection wait và downstream error/timeout.

**Kết luận:** Virtual threads trong Java 21 cung cấp mô hình **thread-per-task nhẹ**, phù hợp ứng dụng nhiều blocking I/O. **Spring Boot 3.2+** hỗ trợ **có chọn lọc** qua **spring.threads.virtual.enabled=true**, nổi bật ở Tomcat/Jetty servlet, TaskExecutor/@Async, và TaskScheduler; WebFlux Reactor Netty event loops không tự thành virtual threads. Khi áp dụng phải xét **pinning JDK21, daemon keep-alive, fixedDelay, custom executor, ThreadLocal, connection pool và backpressure**, rồi đo hiệu quả thực trước khi triển khai rộng.

### Tài liệu tham khảo

- [OpenJDK — JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Spring Boot — 3.2 Release Notes: Virtual Threads](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 — SimpleAsyncTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html)
