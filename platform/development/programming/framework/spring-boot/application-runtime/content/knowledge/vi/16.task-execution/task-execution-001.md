# Luồng main, luồng máy chủ và luồng tác vụ trong vòng đời ứng dụng Spring Boot

## 1. Bài toán: vì sao main() đã kết thúc mà ứng dụng vẫn nhận request?

Khi viết chương trình Java đơn giản, người mới học thường nghĩ rằng toàn bộ ứng dụng kết thúc khi **main(String[] args)** trả về. Với Spring Boot chạy máy chủ nhúng, cách hiểu đó không đúng: **luồng thực thi main**, **các luồng phục vụ HTTP** và **các luồng thực hiện tác vụ nền** có nhiệm vụ và vòng đời khác nhau.

Ví dụ một ứng dụng Spring MVC chạy Tomcat nhúng:

~~~text
Thread "main"
  |
  +-- SpringApplication.run(...)
  |     +-- chuẩn bị Environment, tạo ApplicationContext
  |     +-- refresh(), tạo bean, khởi động web server
  |     +-- chạy ApplicationRunner/CommandLineRunner
  |     +-- phát ApplicationReadyEvent
  |
  +-- run(...) trả về ConfigurableApplicationContext
  +-- main() trả về
                  |
                  | JVM còn những luồng giữ tiến trình hoạt động
                  v
Luồng accept/worker của máy chủ HTTP
  +-- nhận request GET /orders
  +-- gọi Controller -> Service -> Repository
  +-- trả response
                  |
                  v
Luồng thuộc executor/scheduler của ứng dụng
  +-- @Async chạy tác vụ được gửi từ bean khác
  +-- @Scheduled kích hoạt công việc theo lịch
  +-- các listener/message consumer do hạ tầng quản lý
~~~

**Điều cốt lõi:** **SpringApplication.run(...) không phải vòng lặp vô hạn nhận HTTP request trên luồng main**. Nó khởi tạo ApplicationContext và hạ tầng cần thiết; request sau đó được xử lý bởi các luồng mà máy chủ/khung công việc điều phối.

Ba loại luồng cần phân biệt:

- **Luồng main:** thường thực hiện quá trình khởi động đồng bộ. Trong một chương trình Java bình thường, tên luồng này hay là **main**; tên luồng có thể được thay đổi, nên tên không phải hợp đồng API.
- **Luồng máy chủ:** được Tomcat, Jetty, Undertow hoặc Reactor Netty dùng để nhận kết nối và xử lý mạng/request. Mô hình thread phụ thuộc máy chủ và kiểu Servlet/Reactive.
- **Luồng tác vụ:** được TaskExecutor, TaskScheduler, scheduler hoặc thư viện tích hợp dùng để chạy những công việc không nhất thiết nằm trong đường request. **@Async** và **@Scheduled** là hai ví dụ phổ biến.

Bài sử dụng **Java 17+, Spring Boot 3.3.13 và Spring Framework 6.1**. Những tên thread in ra dưới đây là quan sát tại runtime, không phải định danh cố định mà mọi phiên bản hoặc môi trường đều phải dùng.

## 2. Luồng main tham gia giai đoạn nào của SpringApplication?

Ở một ứng dụng điển hình:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

JVM gọi **main(...)** trên một luồng ban đầu. Lệnh **SpringApplication.run(...)** thực hiện bootstrap theo thứ tự khái quát:

1. Chuẩn bị **Environment** và các nguồn cấu hình cần thiết.
2. Tạo **ApplicationContext** thích hợp với loại ứng dụng.
3. Nạp cấu hình và các **BeanDefinition**.
4. Gọi **ApplicationContext.refresh()** để xử lý post-processor, đăng ký các BeanPostProcessor, tạo các singleton thông thường và khởi động hạ tầng cần thiết.
5. Trong ứng dụng web, tạo/khởi động **web server nhúng** theo lifecycle của context.
6. Phát **ApplicationStartedEvent** sau refresh.
7. Chạy các bean **ApplicationRunner** và **CommandLineRunner** theo thứ tự cấu hình.
8. Phát **ApplicationReadyEvent** và thay đổi trạng thái availability sang mức chấp nhận traffic khi startup thành công.
9. Trả về **ConfigurableApplicationContext** cho caller.

Sơ đồ:

~~~text
Java launcher
    |
    v
main(String[] args)
    |
    +-- SpringApplication.run(...)
           |
           +-- prepare Environment
           +-- create ApplicationContext
           +-- refresh ApplicationContext
           |      +-- BeanFactoryPostProcessor
           |      +-- tạo singleton cần thiết
           |      +-- start embedded web server
           |      +-- phát ContextRefreshedEvent
           |
           +-- ApplicationStartedEvent
           +-- ApplicationRunner / CommandLineRunner
           +-- ApplicationReadyEvent
           +-- readiness ACCEPTING_TRAFFIC
           |
           v
       return context
    |
    v
main() kết thúc
    |
    +-- KHÔNG đồng nghĩa context.close()
    +-- KHÔNG đồng nghĩa JVM exit nếu còn non-daemon threads
~~~

**Điểm dễ nhầm:** thứ tự startup trong sơ đồ là thứ tự lifecycle, **không phải lời hứa mọi callback luôn chạy trên duy nhất luồng main**. Các listener mặc định đồng bộ thường chạy ngay trên luồng phát sự kiện, nhưng một ứng dụng có thể cấu hình multicaster bất đồng bộ, tạo tác vụ nền trong callback hoặc dùng hạ tầng riêng.

Nếu một **ApplicationRunner** thực hiện công việc đồng bộ 30 giây, lần gọi **SpringApplication.run(...)** phải chờ runner hoàn tất. Khi đó mốc ready có thể bị trì hoãn dù máy chủ đã tạo các luồng nhận HTTP từ trước.

### 2.1. run() trả về và JVM dừng là hai sự kiện khác nhau

Trong một web app bình thường, sau khi **run(...)** trả về, **main(...)** có thể kết thúc nhưng máy chủ nhúng và các luồng cần thiết vẫn hoạt động, nên tiến trình Java tiếp tục phục vụ request.

JVM thông thường kết thúc khi **không còn non-daemon thread** đang hoạt động (và không có cơ chế giữ tiến trình phù hợp). Spring Boot không yêu cầu bạn tự viết:

~~~java
while (true) {
    // giữ main không kết thúc
}
~~~

Đoạn trên là **anti-pattern**: nó chiếm luồng main, gây khó kiểm soát shutdown và không giải quyết đúng lifecycle. Hãy để Spring Boot và máy chủ nhúng quản lý thời gian sống của ứng dụng.

**Ngoại lệ cần xét:** chương trình **non-web** không có công việc giữ JVM sống có thể thoát khi main kết thúc; các tác vụ nền, scheduler và đặc biệt virtual threads có thể thay đổi tình huống. Đừng suy ra thời gian sống tiến trình chỉ từ sự tồn tại của một bean.

### 2.2. run() trả về không đồng nghĩa server đã ngừng

Một cách khởi chạy web app đúng:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Có thể log hoặc dùng context cho mục đích phù hợp.
// Đừng tự động đóng context của web service tại đây.
~~~

Một cách **không phù hợp cho web service phục vụ lâu dài**:

~~~java
try (ConfigurableApplicationContext context =
             SpringApplication.run(MyApplication.class, args)) {
    // Khi khối try kết thúc, context.close() sẽ được gọi.
}
~~~

**try-with-resources** trong ví dụ thứ hai làm ứng dụng đóng context **ngay khi khối kết thúc**. Cách đó có thể phù hợp cho công cụ CLI muốn chạy xong rồi dừng, nhưng làm máy chủ web vừa khởi động đã bị đóng nếu không có chủ ý.

## 3. Luồng máy chủ nhúng trong ứng dụng Servlet

Khi có dependency **spring-boot-starter-web** và không có cấu hình đặc biệt thay thế, Spring Boot 3.3 thường chọn **Tomcat nhúng** cùng ứng dụng **Spring MVC/Servlet**.

Tomcat dùng các thành phần liên quan đến socket, acceptor, poller và worker/executor để nhận kết nối rồi gọi servlet pipeline. Một luồng request có thể thực thi:

~~~text
HTTP client
    |
    v
Socket / connector của Tomcat
    |
    v
Request worker thread
    |
    +-- Servlet filters
    +-- DispatcherServlet
    +-- HandlerMapping / HandlerAdapter
    +-- @RestController method
    +-- @Service / @Repository
    +-- ghi HTTP response
    |
    v
Worker quay lại pool phục vụ request khác
~~~

Khi code controller gọi:

~~~java
System.out.println(Thread.currentThread().getName());
~~~

trong một Spring MVC application chạy Tomcat, bạn thường thấy tên tương tự:

~~~text
http-nio-8080-exec-1
~~~

**Đây chỉ là ví dụ kiểu tên thường gặp**, không phải bảo đảm tuyệt đối: tên thay đổi theo cổng, connector, phiên bản Tomcat, executor, cấu hình và chế độ thread. Nên dựa vào **vai trò luồng và hạ tầng** hơn là viết logic nghiệp vụ phân nhánh dựa trên tiền tố tên.

### 3.1. Luồng request không phải luồng main

Với endpoint:

~~~java
@RestController
class GreetingController {

    @GetMapping("/greet")
    String greet() {
        return "handled-by=" + Thread.currentThread().getName();
    }
}
~~~

đây là **snippet** trong Spring MVC đã có imports. HTTP request tới **/greet** thường chạy trên luồng worker của server. **main** có thể đã trả về từ trước; vì vậy hai thời điểm và hai luồng không phải một.

### 3.2. Blocking trong Spring MVC ảnh hưởng ra sao?

Nếu request worker gọi I/O đồng bộ rất lâu:

~~~java
@GetMapping("/slow")
String slow() throws InterruptedException {
    Thread.sleep(5000);
    return "done";
}
~~~

thì trong mô hình Servlet thread-per-request thông thường, worker này bị chiếm trong lúc ngủ và không thể xử lý request khác. Đây là **đoạn minh họa độ trễ**, không phải khuyến nghị dùng **Thread.sleep** trong controller.

Khi nhiều request đồng thời, pool worker có giới hạn. Việc tăng số worker không tự sửa lỗi I/O không có timeout, truy vấn database thiếu index hoặc sự cố backend. Cần đo workload, timeout, giới hạn concurrency và dùng đúng cơ chế async hoặc reactive khi phù hợp.

### 3.3. Spring MVC có thể xử lý bất đồng bộ ở cấp HTTP

Controller MVC có thể trả **Callable**, **DeferredResult**, **CompletableFuture**, **WebAsyncTask** hoặc một kiểu reactive được tích hợp phù hợp. Khi đó, Spring MVC có thể nhả luồng request ban đầu rồi dispatch lại sau khi kết quả sẵn sàng.

**Không đồng nhất việc thêm @Async vào một service với toàn bộ request HTTP tự động trở thành non-blocking.** Ví dụ controller gọi **future.join()** vẫn chặn luồng request cho đến khi task hoàn tất, dù task bản thân chạy trên executor khác.

### 3.4. Không dùng chung thread pool cho mọi vai trò một cách tùy tiện

Máy chủ web có cơ chế quản lý request workers; **TaskExecutor** của ứng dụng có thể phục vụ @Async; **TaskScheduler** dành cho công việc theo lịch. Một pool executor bị nghẽn không nhất thiết đồng nghĩa pool Tomcat cũng hết worker, nhưng những dependency dùng chung như CPU, DB pool và network vẫn có thể gây nghẽn toàn hệ thống.

Đối với I/O dài hoặc tác vụ nặng, nên xác định rõ pool nào chịu trách nhiệm, giới hạn hàng đợi, khả năng chịu tải và thời điểm hủy tác vụ.

## 4. Spring WebFlux và Reactor Netty có mô hình luồng khác

Nếu ứng dụng dùng **spring-boot-starter-webflux** với **Reactor Netty** làm server, mô hình phổ biến dựa trên **event-loop threads** thay vì một luồng platform riêng bị chặn cho mỗi request trong toàn bộ thời gian xử lý.

Luồng event loop có thể đảm nhiệm nhiều kết nối:

~~~text
Reactor Netty event loop
    |
    +-- nhận data từ socket A
    +-- xử lý callback phi blocking
    +-- tiếp tục socket B
    +-- tiếp tục xử lý khi có tín hiệu I/O
~~~

Vì một event loop dùng để điều phối nhiều I/O, **blocking call nặng trong event-loop là lỗi thiết kế nghiêm trọng**. Không nên gọi **Thread.sleep**, JDBC blocking hoặc HTTP client blocking ngay trên event-loop mà không có biện pháp chuyển execution phù hợp.

Trong Reactor:

- **subscribeOn(scheduler)** ảnh hưởng nơi subscription/source work được thực hiện.
- **publishOn(scheduler)** chuyển execution context cho các đoạn downstream.
- **Schedulers.boundedElastic()** thường được dùng để cô lập một công việc blocking khi cần tích hợp thư viện không reactive, với giới hạn tài nguyên được quản lý.

Đây là mô tả **mô hình reactive**, không có nghĩa WebFlux tự đưa mọi thao tác blocking sang worker thread. Cũng không nên đổi sang WebFlux chỉ vì muốn chạy một background job.

### 4.1. So sánh Servlet và Reactive

| Đặc điểm | Spring MVC trên Tomcat nhúng | WebFlux với Reactor Netty |
| --- | --- | --- |
| Mô hình thường gặp | Worker thread xử lý servlet request | Event loop và chuỗi reactive |
| Blocking trong handler | Giữ worker trong lúc chờ | Có thể chặn event loop, ảnh hưởng nhiều kết nối |
| Điều phối bất đồng bộ | MVC async support và executor thích hợp | Publisher, Reactor Scheduler, backpressure |
| Tên thread | Có thể dạng **http-nio-...-exec-N** | Có thể dạng **reactor-http-nio-N** |
| Nguyên tắc | Không lạm dụng request worker cho tác vụ rất lâu | Không block event loop |
| Hạn chế | Worker pool/connection pool có giới hạn | Scheduler/pool và downstream vẫn có giới hạn |

**Tên thread trong bảng mang tính minh họa**. Trong hệ thống có WebFlux chạy trên servlet container, cấu hình executor tùy chỉnh hoặc virtual threads, phân công luồng có thể khác bảng.

## 5. Luồng tác vụ do Spring quản lý: @Async và TaskExecutor

Spring Framework hỗ trợ **@Async** cho method được gọi qua proxy. Để bật khả năng này trong một ứng dụng thông thường, thêm **@EnableAsync** vào configuration.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {
}
~~~

Khi một bean khác gọi method có **@Async** và lời gọi được proxy chặn, method có thể chạy trên luồng thuộc **TaskExecutor**, trong khi caller nhận lại một handle như **CompletableFuture** hoặc tiếp tục mà không chờ đối với method void.

~~~text
HTTP request worker
    |
    +-- service.submitTask() qua Spring proxy
    |       |
    |       +-- gửi công việc tới TaskExecutor
    |       |
    |       v
    |     worker của executor chạy method @Async
    |
    +-- controller có thể tiếp tục làm việc khác
~~~

### 5.1. @Async không đồng nghĩa tự tạo Thread mới bằng tay

Ví dụ:

~~~java
@Service
class ReportWorker {

    @Async("reportExecutor")
    public CompletableFuture<String> createReport() {
        String threadName = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(threadName);
    }
}
~~~

Đây là **snippet**, cần có bean executor tên **reportExecutor** và các imports tương ứng. Spring dùng proxy + executor đã chỉ định. Không cần lập trình viên tự gọi:

~~~java
new Thread(() -> createReport()).start();
~~~

Cách tạo Thread thủ công như trên là **anti-pattern** cho tác vụ ứng dụng phổ biến vì khó quản lý shutdown, giới hạn concurrency, exception và quan sát.

### 5.2. Return value và exception của @Async

Method bất đồng bộ có thể trả **CompletableFuture<T>**. Khi gọi:

~~~java
CompletableFuture<String> future = worker.createReport();
~~~

caller có thể dùng **thenApply**, **thenCompose**, **whenComplete**, **exceptionally** để xử lý kết quả/lỗi mà không block ngay. Nếu gọi **future.join()**, caller **bị chặn cho tới khi task hoàn tất**, và exception thường được bọc bằng **CompletionException**.

Với **@Async void**, lỗi không thể truyền qua Future cho caller; Spring có thể log qua **AsyncUncaughtExceptionHandler**. Khi nghiệp vụ cần theo dõi kết quả và xử lý lỗi rõ ràng, nên ưu tiên kiểu trả Future hoặc cơ chế tác vụ/message bền vững thích hợp.

### 5.3. Self-invocation không kích hoạt @Async trong proxy mode

Sai lầm thường gặp:

~~~java
@Service
class BatchService {

    public void start() {
        processAsync(); // Cùng object, không đi qua Spring proxy.
    }

    @Async("reportExecutor")
    public void processAsync() {
        // Có thể vẫn chạy trên caller thread!
    }
}
~~~

Đây là **snippet minh họa lỗi**. Trong proxy mode mặc định, lời gọi nội bộ **this.processAsync()** không được Spring proxy intercept, nên không bảo đảm có chuyển sang executor.

Giải pháp thường là tách method **@Async** sang bean khác, inject bean đó và gọi qua proxy. Đừng cố dựa vào tên method hoặc annotation mà bỏ qua cách dispatch thực tế.

### 5.4. ThreadPoolTaskExecutor và giới hạn tài nguyên

Spring Boot 3.3 có khả năng auto-configure **AsyncTaskExecutor** khi không có Executor bean tùy chỉnh trong context; với Java 17, loại mặc định thông thường là **ThreadPoolTaskExecutor**. Cấu hình và cách chọn executor còn phụ thuộc các bean executor có sẵn trong context.

Ví dụ có thể cấu hình:

~~~properties
spring.task.execution.thread-name-prefix=app-task-
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
~~~

Đây là ví dụ **khi đang sử dụng executor auto-configured**. Nếu ứng dụng đã tự khai báo Executor riêng, cần kiểm tra pool đang dùng thực tế thay vì tin rằng các property này luôn áp dụng lên mọi executor.

**Một pool có kích thước và queue hữu hạn** giúp hạn chế tài nguyên và buộc ứng dụng định nghĩa chính sách khi quá tải. Không để queue tăng vô hạn rồi coi latency tăng cao là lỗi mạng không giải thích được.

## 6. Luồng tác vụ theo lịch: @Scheduled và TaskScheduler

Spring hỗ trợ **@Scheduled** để chạy công việc theo lịch hoặc chu kỳ. Cần bật **@EnableScheduling** trong cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {
}
~~~

Một ví dụ:

~~~java
@Component
class CacheRefreshJob {

    @Scheduled(initialDelay = 1000, fixedDelay = 5000)
    public void refreshCache() {
        System.out.println(
                "SCHEDULED | " + Thread.currentThread().getName());
    }
}
~~~

Đây là snippet có imports tương ứng. **initialDelay** chờ trước lần chạy đầu; **fixedDelay** đo khoảng thời gian từ lúc **lần thực thi trước hoàn tất** đến lúc bắt đầu lần sau (theo đơn vị millisecond trong ví dụ).

**@Scheduled không tự chạy trên luồng HTTP request**. Spring có scheduler chuyên dùng để kích hoạt callback. Trong Boot 3.3 với platform threads, auto-configured scheduler thông thường là **ThreadPoolTaskScheduler** với một thread mặc định, nhưng ứng dụng có thể tạo scheduler riêng hoặc dùng virtual threads trên Java 21+.

### 6.1. fixedDelay, fixedRate, cron

| Cấu hình | Ý nghĩa khái quát | Lưu ý |
| --- | --- | --- |
| **fixedDelay** | Chờ một khoảng sau khi lần trước hoàn tất | Công việc lâu làm lùi lần sau |
| **fixedRate** | Các mốc kích hoạt theo nhịp tính từ lúc bắt đầu | Tùy scheduler, có thể trễ do thiếu thread |
| **cron** | Chạy theo biểu thức lịch | Cần chú ý timezone, DST và server clock |
| **initialDelay** | Trì hoãn lần chạy đầu | Hữu ích khi startup cần thời gian ổn định |

Với scheduler pool chỉ có một thread, một task bị block có thể làm task định kỳ khác trễ. Với nhiều thread hoặc công việc được bàn giao sang executor khác, các tác vụ có thể chạy song song. Vì thế cần thiết kế **idempotence**, chống trùng và tránh chạy chồng khi nghiệp vụ không cho phép.

**Lưu ý:** không nên giả định **@Scheduled** là một job queue bền vững hoặc cơ chế phân tán. Nếu chạy nhiều instance ứng dụng, mỗi instance có thể tự kích hoạt cùng một scheduled method, dẫn đến chạy trùng. Để chỉ một instance xử lý, cần distributed lock, scheduler tập trung hoặc hạ tầng job tương ứng.

### 6.2. Tác vụ scheduled có thể chạy trước ApplicationReadyEvent không?

Có thể. Việc đăng ký và kích hoạt scheduling diễn ra quanh quá trình context refresh; với **initialDelay** ngắn và startup/runners kéo dài, một scheduled callback có thể chạy trong khi các bước trước ready còn tiếp diễn. **Đừng đặt giả định mọi scheduled task chắc chắn chỉ chạy sau ApplicationReadyEvent**.

Nếu tác vụ cần chờ điều kiện ready, hãy thiết kế cổng trạng thái rõ ràng hoặc khởi động scheduler/consumer ở lifecycle phù hợp. Không dùng **Thread.sleep** để đoán khi nào ứng dụng đã ready.

## 7. Ví dụ Java 17+ chạy được: quan sát ba loại luồng

Ví dụ dưới đây có:

1. Luồng **main** gọi SpringApplication.run và tiếp tục sau khi run trả về.
2. **Tomcat** nhận request **GET /threads** trên luồng request worker.
3. **@Async("demoExecutor")** xử lý một method trong pool tên **task-**.
4. **@Scheduled** ghi nhận tên thread của scheduler **sched-**.
5. **ApplicationRunner** và **ApplicationReadyEvent** minh họa các mốc startup.
6. **@PreDestroy** log thời điểm context đóng.

**Phạm vi:** Spring Boot 3.3.13, Java 17+, Spring MVC/Tomcat nhúng. Đây là ví dụ quan sát lifecycle, không phải kiến trúc production hoàn chỉnh.

### 7.1. Cấu trúc Maven

~~~text
thread-life-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/threads/ThreadsRuntimeApplication.java
  src/test/java/com/example/threads/ThreadBoundaryTest.java
~~~

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>thread-life-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.properties:**

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong bài thực hành dùng port 8080. Nếu cổng bị chiếm, hãy đổi cổng hoặc chạy **--server.port=8081** và sửa URL curl tương ứng. Graceful shutdown được bật tường minh để quan sát quá trình đóng context theo cơ chế Boot 3.3.

### 7.2. Mã nguồn duy nhất của ứng dụng

**src/main/java/com/example/threads/ThreadsRuntimeApplication.java:**

~~~java
package com.example.threads;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ThreadsRuntimeApplication {

    public static void main(String[] args) {
        System.out.println("MAIN BEFORE | " +
                Thread.currentThread().getName());

        SpringApplication app =
                new SpringApplication(ThreadsRuntimeApplication.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context = app.run(args);

        System.out.println("MAIN AFTER | " +
                Thread.currentThread().getName() +
                " | active=" + context.isActive());

        // Không đóng context tại đây: HTTP server cần tiếp tục hoạt động.
    }

    @Bean("demoExecutor")
    ThreadPoolTaskExecutor demoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("sched-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(5);
        return scheduler;
    }

    @Bean
    ApplicationRunner printRunnerThread() {
        return args -> System.out.println("RUNNER | " +
                Thread.currentThread().getName());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("READY | " +
                Thread.currentThread().getName());
    }
}

record ThreadSnapshot(
        String requestThread,
        String taskThread,
        String scheduledThread) {
}

@Service
class BackgroundWorker {

    @Async("demoExecutor")
    public CompletableFuture<String> reportThread() {
        String name = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(name);
    }
}

@Component
class ScheduledReporter {

    private final AtomicReference<String> latest =
            new AtomicReference<>("not-yet-run");

    @Scheduled(initialDelay = 1000, fixedDelay = 3000)
    public void recordSchedulerThread() {
        String threadName = Thread.currentThread().getName();
        latest.set(threadName);
        System.out.println("SCHEDULED | " + threadName);
    }

    String latestThreadName() {
        return latest.get();
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("DESTROY | " +
                Thread.currentThread().getName());
    }
}

@RestController
class ThreadInspectionController {

    private final BackgroundWorker worker;
    private final ScheduledReporter scheduledReporter;

    ThreadInspectionController(
            BackgroundWorker worker,
            ScheduledReporter scheduledReporter) {
        this.worker = worker;
        this.scheduledReporter = scheduledReporter;
    }

    @GetMapping("/threads")
    ThreadSnapshot threadSnapshot() {
        return new ThreadSnapshot(
                Thread.currentThread().getName(),
                worker.reportThread().join(),
                scheduledReporter.latestThreadName());
    }
}
~~~

Java cho phép **một public top-level class** và các package-private top-level class/record cùng tệp. **ThreadsRuntimeApplication** là public class có cùng tên file; **BackgroundWorker**, **ScheduledReporter**, **ThreadInspectionController** có annotation stereotype và được component scan trong package **com.example.threads**.

### 7.3. Tại sao ví dụ dùng hai bean thread pool riêng?

- **demoExecutor** là **ThreadPoolTaskExecutor** được chỉ định rõ bằng **@Async("demoExecutor")**. Nó cấp luồng **task-1**, **task-2** khi có tác vụ.
- **taskScheduler** là **ThreadPoolTaskScheduler** mà Spring scheduling infrastructure có thể tìm theo tên thông dụng **taskScheduler**; method **@Scheduled** chạy trên luồng **sched-1** trong cấu hình ví dụ.
- Pool của request HTTP do Tomcat quản lý, **không dùng tên task- hoặc sched-** theo mặc định của cấu hình này.

Vì tách pool, bạn có thể phân biệt trực tiếp các vai trò khi quan sát tên luồng. Trong thực tế, các tên không phải định danh bảo mật và có thể được cấu hình khác.

**Quan trọng:** **worker.reportThread()** được gọi qua bean đã inject vào controller, tức là lời gọi đi qua Spring proxy. Nếu gọi một method @Async bằng **this.method()** trong chính bean đó, với proxy mode thông thường nó sẽ không chuyển sang executor.

### 7.4. Build và chạy

Từ thư mục chứa pom.xml:

~~~bash
mvn -q -DskipTests package
java -jar target/thread-life-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
mvn -q -DskipTests package
java -jar target/thread-life-demo-1.0.0.jar
~~~

Sau khi startup, từ terminal khác:

~~~bash
curl http://localhost:8080/threads
~~~

Một số dòng chương trình có thể xuất hiện ở startup:

~~~text
MAIN BEFORE | main
RUNNER | main
READY | main
MAIN AFTER | main | active=true
~~~

**Đây là thứ tự kỳ vọng của các dòng startup đồng bộ trong cấu hình mẫu**, khi event multicaster mặc định đồng bộ và launcher không đổi tên luồng main. Log của Spring/Tomcat có thể xen giữa; ngoài ra dòng **SCHEDULED** có thể xuất hiện xen vào vì chạy trên thread khác, tùy thời gian startup.

Một response JSON minh họa sau khi scheduler đã chạy ít nhất một lần:

~~~json
{
  "requestThread": "http-nio-8080-exec-1",
  "taskThread": "task-1",
  "scheduledThread": "sched-1"
}
~~~

Đừng assert tên worker request phải chính xác **http-nio-8080-exec-1**: nó có thể là **http-nio-8080-exec-2** hoặc tên khác. Task thread có thể là **task-2** tùy pool. Nếu request đến trước lần **@Scheduled** đầu tiên, trường **scheduledThread** hợp lệ sẽ là **"not-yet-run"**.

Bạn sẽ còn thấy các dòng:

~~~text
SCHEDULED | sched-1
~~~

được in theo chu kỳ khi ứng dụng chạy. Tên cụ thể và số lần in phụ thuộc thời điểm quan sát và cấu hình máy.

### 7.5. Tại sao controller dùng join() chỉ để minh họa?

Controller gọi:

~~~java
worker.reportThread().join()
~~~

nên luồng HTTP worker phải **chờ** cho task async trả kết quả trước khi xây response. Điều này cố ý làm ví dụ đơn giản để hiển thị cả hai thread name trong một HTTP response.

**Không suy ra đây là cách tối ưu cho công việc nặng**. Trong ứng dụng thực, nên cân nhắc trả **CompletableFuture<ThreadSnapshot>** hoặc một loại async response phù hợp để tránh giữ luồng request chỉ trong lúc đợi tác vụ. Với xử lý không cần trả kết quả ngay, dùng job queue có kiểm soát hoặc mô hình event/message thích hợp.

## 8. Kiểm thử xác minh hai ranh giới luồng

Một unit test gọi controller trực tiếp sẽ chạy trên **luồng JUnit test**, chứ không chứng minh request thực sự được máy chủ xử lý bằng worker thread. Vì thế, để kiểm tra ranh giới servlet request và @Async, nên chạy server thực bằng **@SpringBootTest(webEnvironment = RANDOM_PORT)**.

Tạo **src/test/java/com/example/threads/ThreadBoundaryTest.java**:

~~~java
package com.example.threads;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ThreadBoundaryTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void httpWorkerAndAsyncWorkerAreDistinct() {
        @SuppressWarnings("unchecked")
        Map<String, String> body =
                rest.getForObject("/threads", Map.class);

        assertNotNull(body);
        String requestThread = body.get("requestThread");
        String taskThread = body.get("taskThread");

        assertNotNull(requestThread);
        assertNotNull(taskThread);
        assertTrue(taskThread.startsWith("task-"));
        assertNotEquals(requestThread, taskThread);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Test thực sự khởi động embedded server ở một cổng ngẫu nhiên**, tránh xung đột port 8080 với ứng dụng khác trong CI. **TestRestTemplate** gửi request tới server thật. Assertion chỉ kiểm tra **taskThread bắt đầu bằng task-** và **khác requestThread**, không phụ thuộc tên thread của Tomcat theo một pattern cố định.

Vì bài này dùng **join()**, controller sẽ đợi CompletableFuture xong rồi trả JSON. Đó là hành vi đúng của mẫu nhưng không chứng minh request worker đã được giải phóng trong thời gian đợi.

### 8.1. Kiểm thử scheduler mà không dùng sleep tùy tiện

Có thể unit test riêng logic mà method **recordSchedulerThread** gọi, không cần kiểm tra chính xác scheduler gọi nó lúc nào. Nếu mục tiêu là xác nhận wiring/đăng ký **@Scheduled**, dùng context test với cơ chế chờ có timeout và một cờ/CountDownLatch do job cập nhật.

**Không nên assert số lần chạy tuyệt đối sau đúng 1000 ms**, vì CI, GC, tải CPU và startup timing làm việc đo thời gian không ổn định. Với scheduled work, test nên khẳng định một **điều kiện cuối cùng trong khoảng thời gian hợp lý** chứ không đòi thứ tự tuyệt đối giữa luồng scheduler và main.

### 8.2. Kiểm thử lifecycle event

Đối với **ApplicationReadyEvent**, nếu muốn khẳng định listener đã chạy thì dùng một bean test ghi nhận sự kiện hoặc một state quan sát được, không dựa vào việc khớp nguyên văn stdout. Runner đồng bộ trong ví dụ được Boot gọi trước mốc ready.

Không mặc định event listener luôn chạy trên main khi ứng dụng đã cấu hình **ApplicationEventMulticaster** bất đồng bộ: điều kiện thực tế là callback listener được gọi trên **luồng mà event multicast sử dụng**.

## 9. Main, web server và task trong tình huống thực tế

### 9.1. Startup: máy chủ có thể nhận request trước ready

Web server nhúng được tạo/khởi động trong quá trình refresh. **ApplicationRunner** và một số startup callback có thể còn đang chạy sau đó.

~~~text
refresh() tạo/khởi động web server
          |
          +-- server socket có thể đã lắng nghe
          |
ApplicationRunner chạy validation/cache warm-up
          |
ApplicationReadyEvent
          |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Nếu request đi trực tiếp vào cổng trong khoảng giữa các mốc, hệ thống có thể nhận nó **trước khi logic startup bắt buộc hoàn tất**. Trong môi trường điều phối như Kubernetes, readiness probe/routing nên giúp tránh gửi traffic trước khi ứng dụng sẵn sàng.

**Không coi việc log “Tomcat started on port ...” là mốc ứng dụng đã hoàn toàn ready.** Ngược lại, ApplicationReadyEvent không tự bảo đảm mọi external service đã hoạt động nếu ứng dụng chưa kiểm tra chúng.

### 9.2. Request gọi task async rồi đợi

~~~text
HTTP worker             Async executor worker
    |                           |
    +-- gọi service proxy ----->
    |                         chạy task
    |                           |
    +-- join(): chờ <----------+
    |
    +-- gửi HTTP response
~~~

Async task dùng luồng khác, nhưng việc controller chờ bằng join vẫn tiêu tốn thời gian của request worker. Nếu workload cần phản hồi ngay, hãy chọn endpoint async không block hoặc chuyển sang mô hình fire-and-track có job ID và endpoint kiểm tra trạng thái.

### 9.3. Request chỉ gửi tác vụ và trả về ngay

~~~text
HTTP worker
   |
   +-- submit công việc tới bounded executor/queue
   +-- trả 202 Accepted + jobId
           |
           v
Async task worker
   |
   +-- xử lý công việc
   +-- lưu trạng thái kết quả/lỗi
~~~

Đây là **sơ đồ kiến trúc**, không phải logic được triển khai trọn vẹn trong ví dụ ở mục 7. Khi triển khai thật, cần hàng đợi bền vững nếu không được phép mất job khi process chết; **@Async với in-memory executor không tự bảo đảm lưu job hoặc retry sau crash**.

### 9.4. Scheduled job không phụ thuộc một request cụ thể

Một **@Scheduled** method được kích hoạt theo lịch bởi scheduler, không đợi client gửi HTTP. Khi ứng dụng không có request nào, scheduler vẫn có thể chạy. Khi ứng dụng có nhiều replicas, mỗi replica có thể tự chạy scheduled job.

Vì vậy job cần phân biệt **lịch cục bộ** với **lịch phân tán**, và chọn cơ chế leader election/lock/job scheduler nếu chỉ cho phép chạy một lần trên toàn hệ thống.

## 10. Điều gì xảy ra khi dừng ứng dụng?

Khi nhận lệnh dừng bình thường (ví dụ **SIGTERM**, đóng context hoặc thao tác shutdown do runtime quản lý), Spring Boot và Spring Framework có thể thực hiện các bước như:

1. Bắt đầu đóng **ApplicationContext**.
2. Phát **ContextClosedEvent**.
3. Dừng các bean **SmartLifecycle** theo pha.
4. Với graceful shutdown, yêu cầu máy chủ ngừng nhận request mới theo cơ chế hỗ trợ và cho request đang xử lý thời gian hoàn tất.
5. Dừng executor/scheduler, thực hiện destruction callbacks (**@PreDestroy**, **DisposableBean**, destroy method) cho bean.
6. Hoàn tất đóng tài nguyên và cho tiến trình kết thúc khi điều kiện JVM cho phép.

Thứ tự chi tiết giữa thành phần hạ tầng, executor và bean tùy thiết lập phase/dependency và phiên bản. Không nên thiết kế logic phụ thuộc **@PreDestroy chắc chắn chạy trước/ sau một callback của mọi bean khác**.

~~~text
SIGTERM / context.close()
          |
          v
ApplicationContext closing
          |
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop(...)
          +-- graceful web server shutdown
          +-- ngừng scheduler / task executor
          +-- @PreDestroy / destroy callbacks
          |
          v
Tài nguyên được thu hồi
          |
          v
JVM có thể kết thúc
~~~

**Không bảo đảm cleanup chạy khi process bị SIGKILL, JVM crash, máy mất điện hoặc container bị cưỡng bức dừng ngay.** Các công việc không được mất phải có thiết kế lưu trạng thái bền vững và khả năng phục hồi.

### 10.1. Graceful shutdown trong Spring Boot 3.3

Bật tường minh:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Với các embedded servers được Spring Boot 3.3 hỗ trợ, graceful shutdown được thực hiện trong quá trình đóng context, tại một giai đoạn sớm của việc stop **SmartLifecycle**. Server cho các request đang xử lý một khoảng thời gian hoàn tất và ngăn request mới theo cách phụ thuộc loại server.

**Timeout không có nghĩa mọi request hoặc job chắc chắn hoàn tất**. Nếu request giữ kết nối lâu hơn khoảng grace, hệ thống có thể phải kết thúc; nếu container orchestration gửi SIGKILL trước khi grace hoàn tất, cơ hội cleanup bị cắt ngắn. Cần phối hợp **terminationGracePeriodSeconds** (Kubernetes hoặc cơ chế tương đương) với chính sách shutdown của Boot và timeout I/O thực tế.

### 10.2. Shutdown hook là luồng khác

SpringApplication thường đăng ký shutdown hook để đóng context khi JVM đi qua đường shutdown bình thường. Hook **không phải luồng main** và không đồng nghĩa worker HTTP.

Trong ví dụ mục 7, khi dừng bằng Ctrl+C hoặc SIGTERM phù hợp, dòng:

~~~text
DESTROY | SpringApplicationShutdownHook
~~~

có thể xuất hiện với một tên thread tương tự, nhưng **không được khẳng định đó là tên duy nhất**. Nếu code chủ động gọi **context.close()** từ thread khác, **@PreDestroy** có thể chạy trong thread gọi close hoặc luồng do hạ tầng lifecycle sử dụng.

**Không tự tạo một shutdown hook giữ lock vô hạn**. Khi đóng ứng dụng, sử dụng cơ chế lifecycle của Spring, timeout và thứ tự dependency rõ hơn là tự quản lý hàng loạt Thread thủ công.

### 10.3. Task đang chạy khi context đóng

Với **ThreadPoolTaskExecutor** và **ThreadPoolTaskScheduler**, có thể cấu hình hành vi shutdown, chờ công việc trong giới hạn và dừng nhận tác vụ mới. Trong ví dụ, hai pool dùng:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(5);
~~~

Các API này giúp mô tả chính sách chờ nhưng **không bảo đảm tuyệt đối mọi công việc kéo dài đã hoàn tất**. Công việc bị block, job mới bị gửi trong shutdown hoặc lỗi bất thường vẫn cần chiến lược riêng.

Đối với task phải duy trì qua restart/crash, không coi executor in-memory là hàng đợi bền vững. Cần database/outbox/broker và xử lý retry/idempotence phù hợp.

## 11. Virtual threads: ngoại lệ quan trọng trên Java 21+

**Ví dụ chạy được ở mục 7 dùng Java 17 và platform threads**. Trên **Java 21+**, Spring Boot 3.3 có hỗ trợ bật virtual threads:

~~~properties
spring.threads.virtual.enabled=true
~~~

Khi không có Executor bean tùy chỉnh và virtual threads được bật, Boot có thể dùng **SimpleAsyncTaskExecutor** tạo virtual threads cho @Async, và **SimpleAsyncTaskScheduler** cho scheduled work. Những lựa chọn mặc định và property pool thay đổi tùy cấu hình.

**Chú ý:** ví dụ mục 7 đã khai báo riêng **ThreadPoolTaskExecutor** và **ThreadPoolTaskScheduler** và chỉ định executor bằng tên. Vì vậy **bật spring.threads.virtual.enabled=true không tự biến hai custom pools của ví dụ thành virtual-thread pools**.

### 11.1. Daemon threads và JVM keep-alive

Virtual threads là **daemon threads**. Nếu toàn JVM không còn non-daemon thread và không có cơ chế giữ ứng dụng sống, **JVM có thể kết thúc sau khi main trả về**, ngay cả khi bạn kỳ vọng một scheduled task tiếp tục chạy.

Spring Boot 3.3 hỗ trợ:

~~~properties
spring.main.keep-alive=true
~~~

để bảo đảm có cơ chế giữ JVM hoạt động khi các luồng còn lại là daemon. Khi ứng dụng non-web chủ yếu dựa vào @Scheduled chạy trên virtual threads, đây là một cấu hình quan trọng phải kiểm tra.

**Không kết luận mọi web server dùng virtual threads đều sẽ thoát ngay khi main kết thúc**; các luồng của server và cơ chế keep-alive khác nhau theo stack/cấu hình. Cần kiểm tra thực nghiệm với kiểu ứng dụng đang dùng.

### 11.2. Virtual threads không tự sửa blocking, deadlock hay thiếu giới hạn

Virtual threads giúp giảm chi phí thread-per-task trong một số workload blocking I/O. Tuy nhiên:

- Connection pool, remote service và CPU vẫn là tài nguyên hữu hạn.
- Không tạo hàng triệu tác vụ cùng lúc chỉ vì mỗi virtual thread rẻ hơn platform thread.
- Cần theo dõi pinning và các đoạn synchronized/blocking làm giảm hiệu quả theo phiên bản JDK.
- Cần giới hạn concurrency theo khả năng chịu tải của downstream.
- Với reactive stack, không nên dùng virtual threads như lý do để block event loop tùy tiện.

Vì vậy cần phân biệt **khả năng tạo nhiều luồng** với **khả năng hệ thống xử lý đồng thời nhiều công việc**.

## 12. Context propagation và dữ liệu thread-bound

Khi công việc chuyển từ HTTP worker sang async executor thread, những thông tin gắn với thread ban đầu **không tự được chuyển đầy đủ**. Điển hình:

- **MDC** trong logging.
- **SecurityContext** của một số chế độ Spring Security.
- **Transaction context** gắn với thread ở stack imperative.
- **RequestContextHolder** và thông tin request-scoped.
- Bất kỳ **ThreadLocal** tự viết.

Ví dụ:

~~~java
@Async("demoExecutor")
public void process() {
    // Không được mặc định rằng ThreadLocal của HTTP worker
    // tồn tại nguyên vẹn ở task-1.
}
~~~

**Không nên lấy HTTP request object rồi giữ để dùng bất đồng bộ sau khi request đã kết thúc**, trừ khi framework/hợp đồng cho phép. Request attributes có vòng đời riêng.

### 12.1. Cách truyền context an toàn hơn

- Với dữ liệu nghiệp vụ, **truyền ID hoặc immutable DTO rõ ràng** tới method async.
- Với tracing/MDC, sử dụng giải pháp context propagation hoặc **TaskDecorator** tương thích với stack logging/observability.
- Với security, sử dụng **DelegatingSecurityContextAsyncTaskExecutor** hoặc cơ chế security context propagation thích hợp nếu thật sự cần.
- Với transaction, xác định ranh giới transaction ở luồng task; **@Transactional** của caller không tự chuyển nguyên transaction sang @Async worker thread.

Không tự dùng **InheritableThreadLocal** làm giải pháp chung cho thread pool: worker threads tái sử dụng, có thể giữ dữ liệu cũ hoặc rò rỉ giữa các request.

### 12.2. Thread safety của các bean singleton

Một bean singleton có thể được gọi đồng thời từ:

- Nhiều HTTP request workers.
- Một hoặc nhiều @Async worker.
- Scheduler thread.
- Listener/message-consumer threads.

Vì vậy, các field mutable dùng chung trong service cần thiết kế thread-safe. Ví dụ sử dụng **AtomicReference<String>** trong ScheduledReporter để cập nhật tên scheduler thread mà HTTP request worker có thể đọc. Không dùng một field **String lastThread** được cập nhật từ scheduler và đọc từ HTTP worker mà bỏ qua vấn đề visibility/concurrency.

Khi xử lý nhiều tác vụ, xem xét immutable state, **ConcurrentHashMap**, synchronization có giới hạn hoặc giao trách nhiệm cập nhật cho một thành phần dữ liệu thread-safe phù hợp.

## 13. Monitoring và debug ba loại luồng

### 13.1. Log có thread name, nhưng không dựa vào tên để điều khiển nghiệp vụ

Một logging pattern thường có thread name:

~~~text
2026-11-09 INFO [main] Starting application
2026-11-09 INFO [http-nio-8080-exec-1] Handling request
2026-11-09 INFO [task-1] Executing background work
2026-11-09 INFO [sched-1] Scheduled refresh
~~~

Đây là **minh họa**, không phải log chính xác của chương trình ở mục 7. Tên luồng giúp xác định cơ chế đang thực thi, nhưng không phải API ổn định. Nên ghi thêm request ID, trace ID và job ID thích hợp; tránh đưa dữ liệu nhạy cảm vào log.

### 13.2. Dùng thread dump và các dấu hiệu cần tìm

Khi ứng dụng chậm hoặc không dừng:

1. Lấy thread dump bằng công cụ phù hợp như **jcmd** hoặc JDK diagnostic tooling.
2. Xác định thread **RUNNABLE**, **WAITING**, **TIMED_WAITING**, **BLOCKED**.
3. Tìm HTTP workers có nhiều stack ở cùng một I/O/lock.
4. Tìm các **task-*** worker mắc kẹt ở một queue, remote call hoặc synchronized block.
5. Tìm scheduler thread đang thực hiện một job quá lâu.
6. Kiểm tra non-daemon thread nào còn sống sau khi context đáng ra đã đóng.
7. Đối chiếu thread dump với metrics của pool, server connector và backend connection pool.

**RUNNABLE không luôn nghĩa đang dùng CPU liên tục**; một thread ở native I/O có thể được báo trạng thái khác kỳ vọng. Cần kết hợp profiling, metrics và tracing trước khi kết luận.

### 13.3. Chỉ số nên quan sát

| Thành phần | Chỉ số quan trọng | Tại sao |
| --- | --- | --- |
| HTTP server | Active request, worker busy, queue/connection và latency | Phát hiện nghẽn tiếp nhận request |
| Async executor | Active threads, pool size, queue depth, rejection | Phát hiện task backlog/quá tải |
| Scheduler | Task duration, missed runs, error count | Phát hiện job trễ hoặc chạy lỗi |
| Application startup | Startup duration, runner duration, ready transition | Phân biệt chậm startup với chậm runtime |
| Shutdown | Grace period, in-flight requests, task termination time | Đánh giá khả năng dừng an toàn |
| Downstream | DB pool usage, HTTP timeout, retry rate | Hiểu nghẽn ngoài JVM |

Spring Boot Actuator, Micrometer và các hệ thống monitoring có thể hỗ trợ tùy cấu hình. Không khẳng định mọi chỉ số đều tự động có trong mọi starter: cần bật observability/metrics tương ứng.

## 14. Các lỗi thiết kế thường gặp

### 14.1. Nghĩ main thread là request thread

Sai. Sau run, server có worker/event-loop riêng. In **Thread.currentThread().getName()** trong main và controller sẽ cho thấy các luồng khác nhau ở cấu hình thông thường.

### 14.2. Thêm Thread.sleep vào main để giữ server chạy

Không cần trong web app đúng cấu hình. Dùng cơ chế server/lifecycle do Boot quản lý, không viết loop hoặc sleep vô hạn để giữ tiến trình.

### 14.3. Đóng context ngay sau SpringApplication.run trong web service

Một **try-with-resources** hoặc **context.close()** ngay sau run sẽ đóng server. Dùng đóng chủ động khi ứng dụng CLI/test thực sự muốn kết thúc, không dùng cho web app cần hoạt động lâu.

### 14.4. Giả định @Async luôn tạo luồng khác

Không đúng nếu **@EnableAsync** chưa được bật, method không được gọi qua proxy, hoặc code tự gọi **this.method()** trong cùng bean. Kiểm tra wiring và thread thực tế.

### 14.5. Gọi future.join() rồi tưởng đã không block request

Join vẫn đợi kết quả. Task có thể chạy trên worker khác, nhưng HTTP worker đứng chờ. Dùng MVC async return type hoặc kiến trúc job phù hợp khi cần giải phóng request thread.

### 14.6. Cho @Scheduled thực thi cùng một job trên nhiều replicas mà không kiểm soát

Mỗi instance có thể chạy lịch riêng. Nếu job phải chạy toàn hệ thống đúng một lần, cần điều phối phân tán, idempotence và lưu state.

### 14.7. Đưa thao tác JDBC blocking thẳng vào Reactor event loop

Có thể chặn luồng phục vụ nhiều kết nối. Chuyển công việc blocking sang scheduler phù hợp hoặc dùng driver reactive nếu phù hợp; không block event-loop.

### 14.8. Dùng thread pool không có giới hạn và không quản lý lỗi

Queue tăng không kiểm soát có thể dẫn đến memory pressure, latency tăng và task bị trì hoãn lâu. Cần cấu hình pool, queue capacity, rejection policy và monitoring.

### 14.9. Dựa vào thứ tự tuyệt đối giữa scheduled job và ApplicationReadyEvent

Một scheduled job có thể chạy trong khi runner/ready còn tiếp diễn, tùy thời gian và cấu hình. Nếu task phải chạy sau ready, hãy thiết kế điều kiện khởi động rõ ràng.

### 14.10. Trông chờ @PreDestroy luôn chạy khi container bị kill cưỡng bức

Không có bảo đảm cleanup khi SIGKILL/crash. Các tác vụ quan trọng phải có recovery và dữ liệu bền vững.

### 14.11. Coi shutdown grace là bảo đảm mọi async job hoàn tất

Graceful web-server shutdown tập trung vào request/lifecycle. Các executor có chính sách shutdown riêng; timeout hoặc tín hiệu dừng cưỡng bức vẫn có thể cắt ngang job.

### 14.12. Truyền ThreadLocal từ request sang @Async rồi để rò dữ liệu

Không có truyền ngầm đầy đủ, và custom ThreadLocal có thể lưu dữ liệu cũ khi thread pool reuse. Dùng context propagation chuẩn hoặc truyền DTO/ID cụ thể.

### 14.13. Dùng tên thread để kiểm tra nghiệp vụ

Logic kiểu **if (threadName.startsWith("http-"))** rất mong manh. Tên thread có thể đổi theo server hoặc pool, và virtual threads làm mô hình thay đổi. Dùng abstraction, dependency injection và business context thay vì tên luồng.

### 14.14. Dùng @Async/@Scheduled như message queue bền vững

In-memory task executor/scheduler không tự có retry qua restart, dead-letter hoặc exactly-once. Công việc yêu cầu bảo đảm giao nhận cần persistence, broker hoặc job platform phù hợp.

## 15. Checklist trước khi đưa vào production

- [ ] Biết **main**, **HTTP worker/event loop**, **TaskExecutor** và **TaskScheduler** có vai trò khác nhau.
- [ ] Không đóng web ApplicationContext ngay sau run.
- [ ] Không dùng vòng lặp/sleep vô hạn để giữ main sống.
- [ ] Startup runners có timeout và không làm chậm readiness không cần thiết.
- [ ] Biết server có thể mở cổng trước mốc ready.
- [ ] @Async được bật, gọi qua proxy và sử dụng đúng executor.
- [ ] Tách việc cần kết quả ngay khỏi background job có thể trả 202.
- [ ] Không gọi join/get trong request nếu mục tiêu là giải phóng request thread.
- [ ] Pool async có queue/size/rejection/monitoring hợp lý.
- [ ] @Scheduled có đúng fixedDelay/fixedRate/cron và timezone.
- [ ] Job nhiều replicas có chống trùng/idempotence khi cần.
- [ ] Không block Reactor Netty event loop.
- [ ] Có chính sách graceful shutdown và timeout của container phù hợp.
- [ ] Executor/scheduler có chính sách dừng và không nhận job mới không kiểm soát.
- [ ] Không dựa vào @PreDestroy khi SIGKILL/crash.
- [ ] Truyền context/tracing/security/transaction qua ranh giới luồng theo cơ chế thích hợp.
- [ ] Singleton state được thiết kế thread-safe.
- [ ] Trên Java 21+ khi bật virtual threads, đã kiểm tra daemon và keep-alive.
- [ ] Có integration test phân biệt HTTP worker với @Async worker bằng server thật.
- [ ] Log/metrics không lộ secrets và không dùng thread name làm business rule.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Khi **SpringApplication.run(...)** trả về rồi main kết thúc, web server nhúng có chắc chắn dừng ngay không?

**Đáp án:** Không. Context/server vẫn có thể hoạt động và JVM còn các luồng cần thiết để phục vụ request. Chỉ main kết thúc không tương đương context.close hoặc process exit.

**Câu 2.** Một controller Spring MVC xử lý request có chạy trên luồng main không?

**Đáp án:** Thông thường không. Tomcat/servlet container giao request cho worker thread. Không nên viết logic phụ thuộc một tên thread cố định.

**Câu 3.** Vì sao một Spring MVC controller gọi **future.join()** sau khi gọi @Async vẫn có thể gây nghẽn HTTP worker?

**Đáp án:** Vì join chặn caller cho tới khi future hoàn tất. Task dùng worker khác nhưng request worker vẫn phải đợi.

**Câu 4.** Một method có @Async nhưng được gọi bằng **this.method()** trong cùng bean có chắc chạy trên executor không?

**Đáp án:** Không. Với proxy mode thông thường, self-invocation không đi qua Spring proxy nên @Async không được intercept.

**Câu 5.** Một @Scheduled fixedDelay=5000 chạy mất 8 giây; lần sau có bắt đầu đúng 5 giây sau lần bắt đầu trước không?

**Đáp án:** Không. Với fixedDelay, khoảng delay được tính **sau khi lần thực thi trước hoàn tất**, nên lần sau bắt đầu sau khi tác vụ 8 giây đã xong và chờ thêm khoảng 5 giây (không tính độ trễ scheduler khác).

**Câu 6.** Trong WebFlux Reactor Netty, tại sao không gọi Thread.sleep(5000) ngay trên event loop?

**Đáp án:** Vì event loop có thể phục vụ nhiều kết nối; block nó làm chậm nhiều luồng xử lý I/O đồng thời.

**Câu 7.** ApplicationReadyEvent có nghĩa máy chủ mới bắt đầu mở cổng ngay lúc đó?

**Đáp án:** Không. Server có thể được khởi động trong refresh, trước runners và ready event. Ready là một mốc của chuỗi startup, không phải thời điểm duy nhất socket bắt đầu lắng nghe.

**Câu 8.** Có thể dùng @Scheduled để bảo đảm job chỉ chạy một lần trên toàn bộ cụm Kubernetes nhiều replicas không?

**Đáp án:** Không tự động. Mỗi replica có thể kích hoạt job, nên cần điều phối hoặc distributed lock nếu yêu cầu chạy duy nhất.

**Câu 9.** @PreDestroy có chắc được gọi khi container gửi SIGKILL không?

**Đáp án:** Không. SIGKILL và crash không bảo đảm chạy Java shutdown callbacks; cần cơ chế phục hồi bền vững.

**Câu 10.** Dữ liệu từ ThreadLocal của HTTP worker có tự xuất hiện trong @Async worker không?

**Đáp án:** Không bảo đảm. Dùng task decorator/context propagation hoặc truyền DTO/ID cần thiết, và xử lý cleanup đúng cách.

**Câu 11.** Tên thread của Tomcat trong mọi máy có phải **http-nio-8080-exec-1** không?

**Đáp án:** Không. Đó chỉ là ví dụ; tên thay đổi theo cổng, connector, pool, server và cấu hình.

**Câu 12.** Vì sao **spring.main.keep-alive=true** đáng chú ý khi chạy task bằng virtual threads trên Java 21+?

**Đáp án:** Virtual threads là daemon threads nên có thể không giữ JVM sống khi các non-daemon threads đã kết thúc; keep-alive hỗ trợ duy trì tiến trình trong trường hợp này.

## 17. Tổng kết

**Vòng đời Spring Boot có nhiều luồng thực thi với trách nhiệm khác nhau**:

- **main** điều phối bootstrap và các callback đồng bộ của lần chạy.
- **embedded web server** giữ hạ tầng mạng và phân phối request tới servlet workers hoặc reactive event loops.
- **TaskExecutor/TaskScheduler** thực thi công việc async/scheduled theo chính sách riêng.

Sau khi **SpringApplication.run(...)** trả về, ứng dụng web vẫn có thể phục vụ request. Điều đó không có nghĩa main chạy vòng lặp server. Khi đóng context, Spring phối hợp vòng đời server, scheduler, executor và bean destruction; graceful shutdown có thời hạn, không bảo đảm hoàn tất mọi công việc trong mọi tình huống.

Khi thiết kế, cần phân biệt request thread với background worker, tránh block event loop, không cho rằng @Async tự chạy chỉ vì có annotation, và bảo vệ trạng thái dùng chung trước concurrency. Dùng thread names để quan sát, không dùng chúng làm hợp đồng nghiệp vụ. Có test với server thật, giám sát pool/queue và tính đến virtual threads nếu chuyển sang Java 21+.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — SpringApplication, Events and Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Embedded Servlet Containers: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework — Task Execution and Scheduling, @Async, @Scheduled: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — Lifecycle, SmartLifecycle and Shutdown: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html