# Bật spring.threads.virtual.enabled trong Spring Boot: cách cấu hình, cơ chế và kiểm chứng

## 1. Mục tiêu bài học

Trong Spring Boot, thuộc tính **spring.threads.virtual.enabled** là công tắc cấu hình cho phép các thành phần **được Spring Boot tự cấu hình và có hỗ trợ virtual threads** sử dụng luồng ảo của Java. Đây là một cách tận dụng Project Loom từ Java 21 để xử lý số lượng lớn công việc có thời gian chờ I/O theo mô hình viết code đồng bộ dễ đọc.

Ví dụ điển hình:

- Một REST API gọi dịch vụ HTTP khác và đợi phản hồi.
- Một tác vụ **@Async** chờ kết quả truy vấn hoặc xử lý I/O.
- Một ứng dụng chạy các công việc **@Scheduled** có thời gian chờ ngoài hệ thống.
- Một hệ thống nhiều request cùng chờ database/network, muốn giảm chi phí giữ một platform thread riêng cho mỗi tác vụ.

Những điều cần phân biệt ngay từ đầu:

1. **Bật thuộc tính không biến toàn bộ Java threads thành virtual threads.** Nó thay đổi các tích hợp cụ thể mà Spring Boot biết cách cấu hình.
2. **Virtual thread không tự tăng tốc một tác vụ CPU-bound.** Lợi ích chính nằm ở khả năng duy trì nhiều tác vụ chờ I/O với chi phí thread thấp hơn.
3. **Bật virtual threads không tự giải quyết giới hạn của connection pool, downstream API, database, bộ nhớ hay quota.**
4. **Java 21 trở lên là bắt buộc.** Tài liệu Spring Boot 3.5 còn khuyến nghị Java 24+ nếu điều kiện triển khai cho phép, vì các cải tiến của JVM với virtual threads.
5. Cần quan sát **Thread.currentThread().isVirtual()** ở đúng nơi thực hiện tác vụ, không chỉ xem property đã được đọc là true.

Bài tập trung vào **Spring Boot 3.5.x và Java 21+** để nêu rõ API, kết quả và tài liệu tham chiếu. Nếu đang dùng Boot major version khác, cần kiểm tra tài liệu chính thức đúng phiên bản.

## 2. Virtual thread là gì?

Java có hai nhóm thread thường được so sánh:

- **Platform thread:** gắn với tài nguyên luồng của hệ điều hành theo mô hình truyền thống. Khi một platform thread bị blocking I/O, nó thường chiếm một OS thread trong thời gian chờ.
- **Virtual thread:** Java Thread nhẹ được JVM quản lý và lên lịch chạy trên các **carrier platform threads**. Trong những blocking operations tương thích, JVM có thể tạm **unmount** virtual thread khỏi carrier để carrier phục vụ tác vụ khác.

Hình dung:

~~~text
Kiểu platform-thread-per-request:

Request A -> OS thread #1 -> đợi network
Request B -> OS thread #2 -> đợi database
Request C -> OS thread #3 -> đợi network
...

Kiểu virtual-thread-per-request:

Request A -> VirtualThread A --- đợi network, carrier rảnh
Request B -> VirtualThread B --- đợi database, carrier rảnh
Request C -> VirtualThread C --- chạy trên carrier khi tới lượt
                     |
               JVM scheduler
                     |
         Một tập carrier platform threads
~~~

Virtual threads vẫn là **java.lang.Thread**. Có thể dùng **Thread.currentThread()**, **ThreadLocal** và exception semantics thông thường theo Java API. Tuy nhiên số virtual threads có thể lớn hơn nhiều so với số platform threads, nên mô hình sử dụng **ThreadLocal caches**, thread affinity hoặc tác vụ blocking bên trong native code cần được đánh giá lại.

Java 21 có API:

~~~java
Thread.startVirtualThread(() -> {
    System.out.println(Thread.currentThread().isVirtual());
});
~~~

Đây là **mảnh Java minh họa**; chương trình phải chờ thread kết thúc nếu muốn chắc chắn nhìn thấy output trước khi main thoát. Có thể dùng **Thread.ofVirtual()** hoặc **Executors.newVirtualThreadPerTaskExecutor()** khi ứng dụng tự quản lý tác vụ.

**Thuộc tính Spring Boot không cần thiết để sử dụng trực tiếp các API Java ở trên.** Nó giúp Spring Boot chọn implementation hỗ trợ virtual threads cho các thành phần được auto-configure.

## 3. Bật spring.threads.virtual.enabled như thế nào?

### Cách 1: application.properties

Tạo hoặc cập nhật **src/main/resources/application.properties**:

~~~properties
spring.threads.virtual.enabled=true
~~~

Đây là cách ngắn nhất khi đã chạy Spring Boot trên JDK 21 trở lên.

### Cách 2: application.yml

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Hai file không cần khai báo cùng một property ở nhiều chỗ nếu không có mục đích override cụ thể.

### Cách 3: command-line argument

~~~bash
java -jar app.jar --spring.threads.virtual.enabled=true
~~~

Trong đó **app.jar** là tên minh họa cho executable JAR của dự án, không phải đường dẫn file được tạo sẵn. Spring Boot xử lý command-line arguments khi dùng SpringApplication.run theo cơ chế mặc định.

### Cách 4: environment variable

Trên Linux/macOS, có thể truyền biến môi trường theo quy tắc relaxed binding thông thường:

~~~bash
SPRING_THREADS_VIRTUAL_ENABLED=true java -jar app.jar
~~~

Trong Windows PowerShell, có thể đặt **$env:SPRING_THREADS_VIRTUAL_ENABLED = "true"** trước khi chạy JAR trong cùng terminal. Không ghi giá trị bí mật vào command-line để thử nghiệm; property này chỉ là boolean.

### Cách 5: chỉ bật ở một profile

~~~properties
# application-virtual.properties
spring.threads.virtual.enabled=true
~~~

Khi bật profile **virtual** bằng **--spring.profiles.active=virtual**, cấu hình này được nạp theo quy tắc ConfigData. Có thể dùng profile để benchmark canary trước khi bật cho mọi instance.

**Một cấu hình đủ rõ để học:**

~~~properties
spring.application.name=virtual-thread-demo
spring.main.web-application-type=none
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Hai thuộc tính cuối có ý nghĩa khác nhau:

- **spring.threads.virtual.enabled=true:** yêu cầu Spring Boot dùng virtual threads trong các thành phần được hỗ trợ.
- **spring.main.keep-alive=true:** yêu cầu Boot giữ JVM sống phù hợp trong trường hợp các thread duy trì ứng dụng chỉ là daemon threads. Điều này đặc biệt quan trọng với ứng dụng chạy **@Scheduled** mà không có web server hoặc non-daemon thread nào khác.

**Không dùng Java 17 rồi mong property tự biến JDK thành Java 21.** Kiểm tra runtime thật bằng **java -version**, Java target/source và base image trong Docker.

## 4. Spring Boot thay đổi thành phần nào khi bật property?

Theo tài liệu **Task Execution and Scheduling** của Spring Boot 3.5, trong điều kiện ứng dụng không khai báo những executor/scheduler tùy biến khiến auto-configuration phải rút lui:

| Cơ chế | Khi virtual threads không bật | Khi virtual threads được bật |
| --- | --- | --- |
| Auto-configured **AsyncTaskExecutor** | **ThreadPoolTaskExecutor** | **SimpleAsyncTaskExecutor** dùng virtual threads |
| Auto-configured **TaskScheduler** | **ThreadPoolTaskScheduler** | **SimpleAsyncTaskScheduler** được cấu hình dùng virtual threads |
| **@Async** với **@EnableAsync** | Thường chạy qua platform-thread executor do Boot cung cấp | Có thể chạy qua virtual-thread executor nếu resolution chọn executor đó |
| Tích hợp Spring MVC async request | Dùng applicationTaskExecutor phù hợp | Có thể dùng executor được cấu hình virtual threads |
| Spring WebFlux blocking execution support | Dùng executor theo cấu hình Boot | Có thể chuyển phần blocking offload sang virtual-thread executor |
| Tomcat/Jetty servlet request processing được Boot hỗ trợ | Threading mặc định của server | Có thể xử lý request trên virtual threads với cấu hình Boot hỗ trợ |

**Điều kiện quan trọng:** các dòng trong bảng là cơ chế **auto-configuration**, không phải lời hứa mọi thư viện hoặc mọi đoạn code trong tiến trình đều được chuyển.

### 4.1. Task execution

Spring Boot có thể tự tạo bean **applicationTaskExecutor** thuộc kiểu **AsyncTaskExecutor**. Với Java 21+ và virtual threads enabled, implementation thông thường là **SimpleAsyncTaskExecutor** đã bật chế độ virtual threads. Nó có thể được dùng bởi những tích hợp như **@Async** (khi bật @EnableAsync), MVC async, WebFlux blocking execution support, một số WebSocket/GraphQL/JPA bootstrap scenarios theo điều kiện trong tài liệu.

**SimpleAsyncTaskExecutor không phải ThreadPoolTaskExecutor.** Nó tạo thread mới cho mỗi task; khi dùng virtual threads, chi phí tạo thread nhẹ hơn nhưng vẫn có giới hạn tài nguyên bên dưới. Nó không vận hành như một pool có core size, max size và queue capacity.

### 4.2. Task scheduling

Khi Boot tự cấu hình scheduler và virtual threads enabled, implementation thường là **SimpleAsyncTaskScheduler**. Nó được thiết kế xoay quanh cách lên lịch trên một scheduler thread và có thể khởi chạy những task executions trên các threads riêng.

**Lưu ý quan trọng của Spring Framework:** với **SimpleAsyncTaskScheduler**, các scheduled tasks dùng **fixed delay** được thực hiện trên **một scheduler thread** để bảo đảm semantics fixed delay, vì vậy **fixed rate hoặc cron triggers** thường phù hợp hơn khi muốn tận dụng virtual-thread-per-task. Không nên khẳng định mọi method **@Scheduled** luôn thực thi trên virtual thread.

### 4.3. Servlet Web server

Spring Boot đã có hỗ trợ virtual threads trong các tích hợp web server tương ứng từ dòng Boot 3.2. Với embedded **Tomcat** hoặc **Jetty** được Boot cấu hình và Java runtime phù hợp, servlet request handling có thể dùng virtual threads.

Đối với **Spring WebFlux dùng Reactor Netty**, không nên suy đoán toàn bộ event-loop threads sẽ trở thành virtual threads chỉ vì property bật. WebFlux có mô hình event loop và cơ chế offload riêng; cần đo và quan sát đúng thread thực tế.

### 4.4. Tích hợp bên ngoài Spring Boot

Thư viện tự tạo platform thread bằng **new Thread(...)**, tạo **Executors.newFixedThreadPool(...)**, hay tự quản lý worker pool **không tự động đổi sang virtual threads**. Nếu một message broker client hoặc database driver có thread pool nội bộ, chính thư viện và cấu hình của nó quyết định threading.

Vì vậy **spring.threads.virtual.enabled=true** là một lựa chọn **có phạm vi**, không phải JVM flag biến mọi Thread thành virtual thread.

## 5. Ví dụ chạy được Java 21+ và Spring Boot 3.5.x

Ví dụ dưới đây kiểm chứng ba điều:

1. Property **spring.threads.virtual.enabled** được Environment đọc là true.
2. **AsyncTaskExecutor** tự cấu hình dùng virtual threads.
3. Một method trong bean khác có **@Async** chạy trên virtual thread.
4. Method **ApplicationRunner** bản thân nó vẫn chạy trên platform thread của bootstrap thông thường — bật property không đổi toàn bộ luồng thực thi.

Để output rõ ràng, ví dụ không dùng sleep dài, không sử dụng web server và **đợi các CompletableFuture hoàn tất trước khi in**. Dự án Maven dùng **Java 21+**, không dùng Java 17.

### 5.1. Tạo project

Tạo project bằng Spring Initializr với:

- **Spring Boot 3.5.x**.
- **Java 21** hoặc bản Java mới hơn được phiên bản Boot/JDK hỗ trợ.
- **Maven**.
- Group **com.example**, artifact **virtual-thread-demo**, package **com.example.demo**.
- Dependency **Spring Boot Starter**. Không cần Spring Web cho bài thử executor.

Giữ Maven Wrapper, parent/BOM và Spring Boot Maven Plugin do Initializr sinh. Phần dependency tối thiểu tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **mảnh XML của POM**, không phải pom.xml đầy đủ. Java version trong project cần là 21 hoặc cao hơn.

### 5.2. File cấu hình

Tạo **src/main/resources/application.properties**:

~~~properties
spring.application.name=virtual-thread-demo
spring.main.web-application-type=none
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Ứng dụng chạy không có web server, nhưng sử dụng **keep-alive** để nhấn mạnh yêu cầu duy trì JVM khi chỉ có daemon virtual threads. Ví dụ đóng context chủ động nên không cần một process chạy vĩnh viễn.

### 5.3. File Java đầy đủ

Tạo **src/main/java/com/example/demo/VirtualThreadDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
public class VirtualThreadDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             VirtualThreadDemoApplication.class, args)) {
            // Spring Boot đã thực thi ApplicationRunner trong run().
            // Đóng context sau khi hoàn tất bài kiểm tra.
        }
    }

    @Bean
    ApplicationRunner inspectVirtualThreads(
            Environment environment,
            AsyncTaskExecutor taskExecutor,
            ThreadProbeService service) {

        return args -> {
            boolean enabled = environment.getProperty(
                    "spring.threads.virtual.enabled",
                    Boolean.class, false);

            System.out.println("property=" + enabled);
            System.out.println("runnerVirtual="
                    + Thread.currentThread().isVirtual());
            System.out.println("executorClass="
                    + taskExecutor.getClass().getSimpleName());

            CompletableFuture<Boolean> executorResult =
                    new CompletableFuture<>();

            taskExecutor.execute(() -> {
                boolean virtual = Thread.currentThread().isVirtual();
                executorResult.complete(virtual);
            });

            System.out.println("executorVirtual="
                    + executorResult.join());

            // Gọi qua Spring bean proxy, không tự gọi cùng class.
            boolean asyncVirtual = service.inspect().join();
            System.out.println("asyncVirtual=" + asyncVirtual);
        };
    }

    @Service
    public static class ThreadProbeService {

        @Async
        public CompletableFuture<Boolean> inspect() {
            boolean virtual = Thread.currentThread().isVirtual();
            return CompletableFuture.completedFuture(virtual);
        }
    }
}
~~~

**Kiểm tra code:**

- Public class **VirtualThreadDemoApplication** khớp tên file.
- **@SpringBootApplication** kích hoạt Boot auto-configuration và component scan.
- **@EnableAsync** cho Spring quản lý việc thực thi **@Async**.
- **ThreadProbeService** là một Spring bean độc lập trong nested static class; method **inspect()** được gọi từ **ApplicationRunner ở bean khác**, đi qua proxy.
- **AsyncTaskExecutor** được inject từ auto-configuration khi project không có custom Executor/AsyncConfigurer.
- Lệnh **taskExecutor.execute(...)** có lambda block, trả **void** đúng chữ ký Runnable; không có overload ambiguity.
- **CompletableFuture.join()** làm output ổn định theo thứ tự in, dù thứ tự thực thi nền có thể khác.
- **Thread.currentThread().isVirtual()** là API Java 21; không thể biên dịch source trên JDK 17.
- **try-with-resources** chỉ đóng ApplicationContext sau khi SpringApplication.run đã hoàn thành; runner chạy trong quá trình run.

Không sử dụng self-invocation cho @Async: nếu gọi **this.inspect()** từ bên trong cùng bean thay vì qua Spring proxy, annotation @Async có thể không được áp dụng.

### 5.4. Chạy với virtual threads bật

Từ thư mục gốc project Maven:

~~~bash
# Kiểm tra JDK runtime và Maven wrapper:
java -version
./mvnw -version

# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell/cmd dùng:
# .\mvnw.cmd spring-boot:run
~~~

Với JDK 21+, Boot 3.5.x, không có custom executor và cấu hình ví dụ như trên, **các dòng do ứng dụng tự in** dự kiến:

~~~text
property=true
runnerVirtual=false
executorClass=SimpleAsyncTaskExecutor
executorVirtual=true
asyncVirtual=true
~~~

Đây là **phần stdout được chương trình in**, không phải toàn bộ console; Maven/Spring Boot cũng ghi log khởi động. Chương trình không cần lắng nghe HTTP. **runnerVirtual=false** nhắc rằng ApplicationRunner đang chạy trên thread bootstrap của quá trình startup, trong khi các task được gửi tới executor và @Async được thực thi bởi virtual threads.

### 5.5. Chạy lại với virtual threads tắt

Đóng gói executable JAR:

~~~bash
./mvnw package
~~~

Nếu artifact/version từ Initializr là **virtual-thread-demo / 0.0.1-SNAPSHOT**, so sánh bằng:

~~~bash
java -jar target/virtual-thread-demo-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false
~~~

Nếu tên artifact hoặc version khác, thay đúng tên JAR thật trong thư mục target.

**Trong cùng cấu hình không có custom Executor**, output tiêu biểu khi tắt:

~~~text
property=false
runnerVirtual=false
executorClass=ThreadPoolTaskExecutor
executorVirtual=false
asyncVirtual=false
~~~

So sánh hai lần chạy:

| Quan sát | Bật true | Tắt false |
| --- | --- | --- |
| Environment property | true | false |
| Main/runner bootstrap thread | platform | platform |
| Auto-configured AsyncTaskExecutor | SimpleAsyncTaskExecutor virtual | ThreadPoolTaskExecutor |
| Task gửi vào auto executor | virtual thread | platform thread |
| @Async trong bean riêng | virtual thread | platform thread |

**Điều kiện:** bảng dùng trường hợp mặc định, không khai báo executor/scheduler tùy chỉnh. Với ứng dụng thật, hãy đo **isVirtual()** tại các workload tương ứng thay vì chỉ đọc class name.

## 6. Vì sao spring.task.execution.pool.* không còn hiệu lực như trước?

Khi Boot tự chọn **ThreadPoolTaskExecutor**, các thuộc tính:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=32
spring.task.execution.pool.queue-capacity=200
~~~

điều chỉnh một **platform thread pool** theo chính sách của Spring Boot.

Khi Boot tự chọn **SimpleAsyncTaskExecutor dùng virtual threads**, **không có cùng kiểu core/max/queue pool**. Vì vậy các thuộc tính cấu hình pool như trên **không còn điều chỉnh số virtual threads theo cách bạn dự tính**; Spring Boot Reference nêu rõ các thuộc tính thread-pool không còn tác dụng khi dùng virtual threads.

Đừng kết luận virtual threads có giới hạn concurrency = 32 vì vẫn nhìn thấy **max-size=32** trong file cấu hình cũ. Một số thuộc tính khác của executor (ví dụ thread name prefix) có thể còn liên quan tùy implementation và version; phải kiểm tra chính xác thay vì khẳng định toàn bộ namespace **spring.task.execution** đều bị bỏ qua.

Tương tự, **SimpleAsyncTaskScheduler** bỏ qua các thuộc tính liên quan scheduler pool. Không kỳ vọng **spring.task.scheduling.pool.size=10** tạo một pool 10 virtual threads.

### Giới hạn concurrency ở đâu?

Virtual threads nhẹ nhưng **hệ thống ngoài không vô hạn**:

- Một database pool có thể chỉ có 20 kết nối.
- Một HTTP upstream có rate limit 100 requests/second.
- CPU chỉ có số core hữu hạn.
- Một node có RAM và file descriptor hữu hạn.
- Một downstream service có thể bị quá tải nếu cùng lúc gọi hàng chục nghìn requests.

**Giải pháp:** giới hạn tại điểm tài nguyên thực, ví dụ connection pool, semaphore, rate limiter, bulkhead, queue có backpressure hoặc một executor có concurrency limit được cấu hình chủ đích. Không dùng platform-thread count để ngầm làm rate limiter và sau đó nghĩ việc bỏ giới hạn này không có hậu quả.

Ví dụ minh họa bằng Java 21:

~~~java
Semaphore permits = new Semaphore(30);

try {
    permits.acquire();
    try {
        callRemoteService();
    } finally {
        permits.release();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

Đây là **mảnh code minh họa**, cần import **java.util.concurrent.Semaphore**, định nghĩa **callRemoteService()** và chính sách xử lý interruption phù hợp. Ý nghĩa là giới hạn **30 calls đồng thời** tại ranh giới dịch vụ ngoài, không cố cấu hình 30 platform threads.

Không nên dùng semaphore theo cách giữ permit trong lúc tác vụ khác quên release. Try/finally là bắt buộc để tránh rò rỉ permits.

## 7. @Async và @EnableAsync khi bật virtual threads

**@Async** không tự hoạt động chỉ vì property virtual threads=true. Trong ứng dụng Spring sử dụng proxy-based async execution, thường cần:

1. **@EnableAsync** để bật xử lý method được đánh dấu @Async.
2. Method thuộc **Spring-managed bean** được gọi **qua proxy**.
3. Executor được resolve đúng từ Spring hoặc **AsyncConfigurer**.
4. Nếu method trả **CompletableFuture**, xử lý lỗi và kết quả ở caller thay vì fire-and-forget không kiểm soát.

Ví dụ:

~~~java
@Service
public class PricingService {

    @Async
    public CompletableFuture<Long> findPrice() {
        return CompletableFuture.completedFuture(100L);
    }
}
~~~

Đây là **mảnh code minh họa**, cần imports, package và một ứng dụng có @EnableAsync. Tác vụ này chỉ có tính chất demo; vì không có I/O blocking, virtual thread không đem lại lợi ích đáng kể.

### Các tình huống property=true nhưng @Async vẫn là platform thread

- Có bean **Executor** tùy biến khiến auto-configuration của Boot back off.
- Có **AsyncConfigurer** chọn executor khác.
- Method được gọi trực tiếp qua **this.method()** nên không được proxy intercept.
- Code không sử dụng Spring-managed @Async mà tự tạo platform thread.
- Một thư viện tự dùng thread pool của chính nó.
- Một số task được gọi trên platform thread theo quyết định của ứng dụng.

Spring Boot 3.5 có cơ chế:

~~~properties
spring.task.execution.mode=force
~~~

Khi dùng **force** trong điều kiện được tài liệu hỗ trợ, Boot có thể vẫn cấu hình **applicationTaskExecutor** dù có custom Executor bean, và ưu tiên executor do Boot tự cấu hình cho các tích hợp được nêu rõ. Tuy nhiên một **AsyncConfigurer** tùy biến vẫn có thể quyết định executor của @Async. Không dùng force mù quáng nếu hệ thống cần phân luồng riêng cho từng workload.

### Cách xác minh thay vì suy đoán

Trong method mà bạn thực sự muốn chạy trên virtual thread:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
log.info("virtualThread={}", virtual);
~~~

Đây là mảnh code minh họa với logger **log** đã được định nghĩa. Hãy đo cả thread type và throughput/latency/CPU, tránh đẩy tên luồng của từng request lên monitoring với cardinality quá lớn.

## 8. @Scheduled và chú ý đặc biệt với virtual threads

Khi có **@EnableScheduling**, Boot có thể tự cấu hình TaskScheduler. Với virtual threads enabled, Spring Boot 3.5 thường cung cấp **SimpleAsyncTaskScheduler** thay cho ThreadPoolTaskScheduler nếu không bị bean tùy biến override.

Minh họa một scheduled task:

~~~java
@Component
public class HeartbeatJob {

    @Scheduled(fixedRate = 5000)
    public void tick() {
        System.out.println("virtual="
                + Thread.currentThread().isVirtual());
    }
}
~~~

Đoạn code **không độc lập** vì cần package/import Component và Scheduled, **@EnableScheduling** trên một configuration class và runtime còn sống đủ lâu. Dùng **fixedRate** để thể hiện cơ chế scheduler tạo task execution riêng; output cụ thể phụ thuộc scheduler, version và cấu hình đã inject.

### Vì sao fixedDelay cần chú ý?

Theo Spring Framework 6.2, **SimpleAsyncTaskScheduler** dùng một scheduler thread và có ngoại lệ quan trọng: **fixed-delay tasks chạy trên scheduler thread**, nhằm giữ semantics thời gian delay tính từ khi task trước hoàn tất. Khi số lượng fixed-delay tasks lớn hoặc có blocking I/O dài, một scheduler thread có thể thành nút nghẽn.

**Khuyến nghị tài liệu Spring:** cân nhắc **fixedRate** hoặc **cron triggers** nếu muốn khai thác mô hình virtual-thread-per-task của SimpleAsyncTaskScheduler.

Cần nhắc rằng fixedRate/cron không có nghĩa có thể chạy tràn lan task CPU-bound hay bỏ concurrency protection. Scheduler chỉ định lúc khởi chạy; tài nguyên downstream vẫn có giới hạn.

### Vì sao cần spring.main.keep-alive=true?

Các **virtual threads là daemon threads**. JVM có thể kết thúc khi không còn non-daemon threads, dù những virtual threads định kỳ vẫn đang chờ chạy. Một ứng dụng **non-web chủ yếu chạy @Scheduled** có thể bất ngờ thoát sau khi bootstrapping hoàn tất nếu không có thread nào khác giữ JVM sống.

Spring Boot 3.5 khuyến nghị:

~~~properties
spring.main.keep-alive=true
~~~

Đây là property giúp Boot duy trì JVM trong hoàn cảnh đó. Nó không thay thế chính sách shutdown: khi ApplicationContext được đóng bình thường, các thành phần lifecycle vẫn phải được dừng và tài nguyên giải phóng.

Đối với chương trình CLI chạy một lần rồi thoát, có thể **không cần** keep-alive; demo ở mục 5 dùng try-with-resources để đóng context có kiểm soát. Đối với scheduler service chạy lâu dài, nên kiểm tra keep-alive và trạng thái liveness/readiness thực tế.

## 9. Virtual threads trong Spring MVC và WebFlux

### Với Spring MVC trên Tomcat/Jetty

Khi sử dụng embedded servlet server được Boot cấu hình hỗ trợ virtual threads, controller xử lý request có thể chạy trên virtual thread. Nếu muốn quan sát trực tiếp ở Spring MVC, có thể dùng một controller riêng:

~~~java
@RestController
class ThreadInfoController {

    @GetMapping("/thread-info")
    Map<String, Object> threadInfo() {
        return Map.of(
                "virtual", Thread.currentThread().isVirtual(),
                "threadName", Thread.currentThread().getName());
    }
}
~~~

Đây là **mảnh code minh họa**, cần package và imports **java.util.Map**, **RestController**, **GetMapping** trong project có **spring-boot-starter-web**, Java 21+ và Boot servlet server phù hợp.

Trong dự án **Spring MVC / embedded Tomcat** mặc định của Spring Boot 3.5, khi property được bật và server sử dụng virtual-thread request executor, trường **virtual** dự kiến là true ở controller. Hãy kiểm tra trên bản Boot/server cụ thể thay vì viết assertion không có điều kiện cho mọi servlet container hoặc cấu hình custom.

### Với Spring WebFlux

WebFlux/Reactor Netty sử dụng mô hình event-loop/non-blocking. Bật property không biến tất cả event-loop threads thành virtual threads. Các integration **blocking execution support** có thể dùng executor do Boot cấu hình virtual threads trong một số đường thực thi, nhưng cần xem **đoạn code nào thật sự offload blocking work**.

Một lưu ý: nếu đặt blocking JDBC call trực tiếp vào event-loop của WebFlux, bật property không tự đảm bảo call đó được chuyển sang một virtual thread. Kiểm tra Reactor scheduling, task execution support và code instrumentation.

## 10. Những giới hạn hiệu năng và rủi ro kỹ thuật

### 10.1. Virtual threads tối ưu concurrency, không tự tăng CPU throughput

Nếu workload là tính toán CPU nặng:

~~~text
1 task: 500ms tính toán CPU
1.000 task: đều cần nhiều CPU cycles
~~~

Tạo 1.000 virtual threads không làm xuất hiện thêm CPU cores. Virtual threads phù hợp khi phần lớn thời gian mỗi task đang **đợi I/O**. Với CPU-bound work, vẫn cần giới hạn số tác vụ chạy song song theo core và memory budget.

### 10.2. Pinning và phiên bản JDK

Trên **Java 21**, một số blocking operations trong vùng **synchronized** hoặc native frames có thể khiến virtual thread **bị pinned vào carrier platform thread**, làm giảm khả năng mở rộng concurrency.

**Java 24** có JEP 491, cải thiện mạnh việc đồng bộ hóa virtual threads: khi blocking trong vùng synchronized tương ứng, JVM có thể giải phóng carrier thay vì giữ pin như trước. Điều đó không có nghĩa không thể có mọi dạng pinning hoặc blocking không hợp tác trên Java 24+. Boot 3.5 khuyến nghị Java 24+ để có trải nghiệm virtual threads tốt hơn, nếu nền tảng và compatibility cho phép.

Khi điều tra:

- Dùng **Java Flight Recorder (JFR)** và các sự kiện liên quan virtual threads/pinning.
- Tận dụng **jcmd** và thread dumps theo JDK version.
- Đọc tài liệu JVM đúng bản đang chạy.
- Đo tỷ lệ blocked/waiting, carrier saturation và throughput dưới tải thực.

Đừng kết luận cả ứng dụng "đã hết pinning" chỉ vì chuyển từ Java 21 lên một JDK mới hơn.

### 10.3. ThreadLocal vẫn hoạt động nhưng mô hình cache có thể tốn kém

Nhiều virtual threads đồng nghĩa có thể có rất nhiều ThreadLocal values. Một thư viện dùng **ThreadLocal.withInitial(...)** để cache buffer lớn có thể tạo số buffer tương ứng **mỗi virtual thread**, chứ không được tái sử dụng như một pool nhỏ platform threads.

Cần rà soát:

- ThreadLocal giữ object nặng và thời gian sống của dữ liệu.
- SecurityContext/MDC propagation khi chạy async.
- Context propagation qua những thread boundaries khác nhau.
- Các thư viện yêu cầu thread affinity hoặc thao tác native đặc thù.

Không giả định ThreadLocal hoàn toàn bị cấm trong virtual threads; vấn đề là **chi phí và ngữ nghĩa sử dụng** khi số threads có thể rất lớn.

### 10.4. Giới hạn của connection pools và upstream APIs

Ví dụ có 10.000 virtual threads cùng gọi JDBC nhưng pool chỉ có 30 connections. Phần lớn sẽ **chờ connection**; số task Java tăng không biến 30 connections thành 10.000 connections. Khi quá tải, request latency hoặc memory usage vẫn tăng.

Cần:

- Đặt timeout của JDBC pool, connect/read timeout cho HTTP clients.
- Điều tiết concurrency bằng semaphore/bulkhead.
- Đo queueing time và downstream saturation.
- Định nghĩa retry với backoff/jitter, tránh bão retry.
- Giảm fan-out vô hạn tới downstream service.

### 10.5. Virtual threads không tự bảo đảm structured concurrency hoặc cancellation

Bật property không biến mọi nhóm tác vụ thành một cấu trúc có deadline, propagate interruption, join và failure handling. Đối với @Async hoặc CompletableFuture, caller vẫn phải quản lý kết quả, timeout và exception. Không fire-and-forget những tác vụ có side effect quan trọng chỉ vì virtual threads rẻ hơn.

### 10.6. Security, monitoring và độ ổn định

Số lượng virtual threads lớn đòi hỏi cách quan sát khác:

- CPU utilization, heap usage và GC.
- HTTP request concurrency/latency p95/p99.
- DB connection pool active/pending.
- Downstream timeouts/retries/rate limiting.
- Scheduler delays và task execution errors.
- JFR events, thread dump sampling.
- Runtime cancellations khi shutdown.

Những con số này phải so sánh cùng tải và cùng môi trường trước/sau khi bật property. Không so sánh máy local idle với production traffic rồi quy lợi ích cho virtual threads.

## 11. Các lỗi thường gặp khi bật property

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Build hoặc chạy trên Java 17 | Virtual threads yêu cầu Java 21+ | Nâng JDK build/runtime và base image phù hợp |
| Đặt property=true nhưng runnerVirtual=false | Runner vẫn chạy trên bootstrap thread | Kiểm tra bên trong executor/@Async hoặc HTTP request |
| @Async vẫn thấy virtual=false | Custom Executor/AsyncConfigurer hoặc self-invocation | Kiểm tra proxy, executor thực tế và Boot auto-configuration |
| Bean applicationTaskExecutor khác dự kiến | Custom Executor hoặc chế độ task execution | Xem Spring Boot task execution configuration |
| Đặt spring.task.execution.pool.max-size nhưng không giới hạn virtual threads | SimpleAsyncTaskExecutor không phải thread pool | Giới hạn concurrency ở tài nguyên thực |
| @Scheduled không chạy sau khi app boot | Daemon virtual threads không giữ JVM sống | Xem spring.main.keep-alive=true |
| fixedDelay jobs chậm/tuần tự | SimpleAsyncTaskScheduler dùng scheduler thread cho fixed delay | Cân nhắc fixedRate/cron và workload phù hợp |
| Spring WebFlux event-loop vẫn là platform | Không phải mọi event loop đổi thành virtual | Phân biệt non-blocking/reactive và blocking offload |
| Bật virtual nhưng throughput giảm | Pinning, downstream contention, ThreadLocal overhead | Profiling và benchmark; xem JDK 24+ |
| Hàng nghìn task đợi DB gây timeout | Connection pool hạn chế | Bounded concurrency, pool timeout, backpressure |
| Ứng dụng thoát khi chỉ có scheduler | Không còn non-daemon thread | Kiểm tra keep-alive, lifecycle |
| Tự tạo new Thread hoặc fixed thread pool vẫn platform | Property chỉ tác động tích hợp do Boot quản lý | Cấu hình executor/virtual thread per task rõ ràng |
| Tắt property nhưng thread vẫn virtual ở thư viện tùy chỉnh | Thư viện dùng Java API tạo virtual threads trực tiếp | Tìm nguồn tạo thread của thư viện |
| Kết quả benchmark thay đổi không rõ | Tải, warm-up, JDK, pool limit khác nhau | Giữ A/B conditions, ghi p95/p99 và resource metrics |

## 12. Kế hoạch bật virtual threads trong production

Không cần chuyển cả hệ thống một lần. Có thể làm theo quy trình:

### Bước 1: Xác định phiên bản và workload

- Xác nhận **java -version** trong container/host thật.
- Chọn Spring Boot version đã hỗ trợ property và integrations tương ứng.
- Liệt kê các luồng cần cải thiện: servlet requests, @Async jobs, scheduled jobs hoặc blocking integrations.
- Phân loại CPU-bound vs I/O-bound.

### Bước 2: Kiểm tra các executor tùy chỉnh

Tìm **Executor**, **AsyncTaskExecutor**, **AsyncConfigurer**, **ThreadPoolTaskExecutor**, task scheduler beans và các thư viện tự quản lý thread pool. Quyết định liệu property của Boot có tác động vào đường xử lý mong muốn hay không.

**Không tự preflight những executor beans bằng cách tạo thêm một bean trùng tên** khi chưa hiểu resolution rules. Có thể đo type class và **isVirtual()** tại chính tác vụ.

### Bước 3: Thử A/B có kiểm soát

Chạy cùng workload với:

~~~properties
# Nhóm A
spring.threads.virtual.enabled=false
~~~

và:

~~~properties
# Nhóm B
spring.threads.virtual.enabled=true
~~~

Giữ cố định JDK, RAM/CPU limits, số replicas, database pool, concurrency, request mix và downstream services. Đo throughput, p95/p99 latency, lỗi, heap/GC và mức dùng resources.

### Bước 4: Kiểm soát tài nguyên

Bổ sung hoặc kiểm tra limits ở network clients, DB pools, rate limiters, semaphores/bulkheads. Với workloads có tác vụ định kỳ, kiểm tra keep-alive và scheduler fixed-delay behavior.

### Bước 5: Chạy canary/rollback

Bật cho một tỷ lệ nhỏ instance hoặc qua profile/env property. Có đường rollback bằng cách đặt:

~~~properties
spring.threads.virtual.enabled=false
~~~

và restart/redeploy theo quy trình rollout của hệ thống. Đây là **thuộc tính bootstrap**, không tự thay đổi executor đang chạy khi sửa file properties trong runtime mà không có cơ chế reconfiguration riêng.

### Bước 6: Đánh giá failure modes

Kiểm tra shutdown, cancellation, upstream outage, DB pool exhaustion, CPU spike, service overloaded, scheduler callbacks và các native libraries. Nếu một thư viện dùng ThreadLocal caching lớn hoặc giữ monitor lâu trên Java 21, chú ý pinning/memory overhead.

## 13. Bài tập kiểm tra hiểu biết

**Câu 1.** Có phải chỉ cần khai báo **spring.threads.virtual.enabled=true** là mọi Thread trong ứng dụng trở thành virtual thread?

**Câu 2.** Vì sao **Thread.currentThread().isVirtual()** trong ApplicationRunner có thể trả false trong khi @Async trả true?

**Câu 3.** Khi virtual threads được bật, Boot thường auto-configure những class nào cho AsyncTaskExecutor và TaskScheduler, nếu không có custom beans cản trở?

**Câu 4.** Tại sao **spring.task.execution.pool.max-size=8** không tự giới hạn số virtual threads?

**Câu 5.** Một method @Async được gọi qua **this.method()**. Property true có bảo đảm method chạy bất đồng bộ trên virtual thread không?

**Câu 6.** Vì sao ứng dụng non-web chủ yếu chạy @Scheduled cần chú ý **spring.main.keep-alive**?

**Câu 7.** Với SimpleAsyncTaskScheduler, vì sao Spring khuyến nghị fixedRate/cron hơn fixedDelay để khai thác virtual threads?

**Câu 8.** Java 24 đã giải quyết hết mọi vấn đề hiệu năng virtual threads chưa? Nó cải thiện loại pinning nào?

**Câu 9.** Một service dùng 10.000 virtual threads đồng thời gọi DB với pool 20 connections. Điều gì là bottleneck?

**Câu 10.** Bật property true trên WebFlux có tự chuyển mọi Reactor Netty event-loop thread thành virtual threads không?

**Đáp án gợi ý:**

1. Không, chỉ những đường tích hợp/auto-configuration được hỗ trợ hoặc code Java tự dùng virtual threads.
2. Runner chạy trên thread startup; @Async được dispatch qua executor của Boot khi cấu hình đúng.
3. SimpleAsyncTaskExecutor virtual và SimpleAsyncTaskScheduler virtual.
4. Vì executor virtual không phải ThreadPoolTaskExecutor với core/max/queue semantics đó.
5. Không; self-invocation bỏ qua proxy-based @Async.
6. Virtual threads là daemon; JVM có thể thoát khi không còn non-daemon thread.
7. Fixed-delay chạy trên một scheduler thread; fixed-rate/cron phù hợp thread-per-task hơn.
8. Không; JEP 491 cải thiện synchronized monitor pinning nhưng các bottlenecks khác vẫn có.
9. DB pool/downstream throughput, không phải số lượng virtual threads.
10. Không; WebFlux có event-loop/non-blocking model và blocking offload riêng.

## 14. Ghi nhớ và tài liệu chính thức

**Công tắc Spring Boot:**

~~~properties
spring.threads.virtual.enabled=true
~~~

**Điều kiện: Java 21+; ưu tiên kiểm chứng trên JDK đang chạy thực tế.**

Khi sử dụng Spring Boot 3.5 auto-configuration thông thường:

~~~text
spring.threads.virtual.enabled = true
        |
        +--> auto AsyncTaskExecutor
        |      SimpleAsyncTaskExecutor (virtual threads)
        |
        +--> auto TaskScheduler (nếu cần)
        |      SimpleAsyncTaskScheduler (virtual-thread aligned)
        |
        +--> một số tích hợp Boot/Web Server được hỗ trợ
               |
               v
        Kiểm tra Thread.currentThread().isVirtual()
        tại tác vụ thực tế
~~~

**Ba điểm không được bỏ sót:** thay đổi này không chuyển mọi thread; thread pool tuning không còn giống trước; virtual threads là daemon và cần kiểm tra keep-alive cho scheduler-only applications. Luôn đo bằng workload thực tế thay vì giả định property=true đồng nghĩa nhanh hơn.

### Tài liệu nguồn

1. Spring Boot 3.5 Reference — SpringApplication / Virtual Threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
3. Spring Framework 6.2 Reference — Task Execution, SimpleAsyncTaskExecutor, SimpleAsyncTaskScheduler: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
4. Java 21 API — Thread.isVirtual(): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#isVirtual()
5. OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
6. OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24): https://openjdk.org/jeps/491

Ví dụ runnable nhắm tới **Spring Boot 3.5.x, Spring Framework 6.2.x, JDK 21+**. Trước khi áp dụng production, đối chiếu tài liệu chính thức của đúng Spring Boot/JDK version, custom executors, servlet container và cơ chế scheduling đang dùng.