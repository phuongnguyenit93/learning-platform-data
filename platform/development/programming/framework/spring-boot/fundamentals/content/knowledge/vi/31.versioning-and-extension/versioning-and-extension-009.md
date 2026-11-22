# Virtual thread và các khả năng phụ thuộc phiên bản JDK, Spring Boot

Virtual thread là loại thread nhẹ do JVM quản lý, được Java đưa vào dạng preview ở JDK 19/20 và chính thức từ **JDK 21**. Nó cho phép ứng dụng tạo một thread cho mỗi tác vụ mà không phải duy trì một OS thread riêng cho từng tác vụ. Với ứng dụng Spring Boot xử lý nhiều request hoặc tác vụ chủ yếu chờ I/O, virtual thread có thể tăng khả năng phục vụ đồng thời và giúp code blocking dễ đọc hơn.

Tuy nhiên, virtual thread không phải chế độ tăng tốc CPU, không làm database hay remote API có capacity vô hạn và không được tích hợp giống nhau ở mọi phiên bản Java/Spring Boot. Cần phân biệt **khả năng của JDK**, **tích hợp của Spring Framework**, **auto-configuration của Spring Boot** và **hành vi của web server hoặc thư viện bên thứ ba**.

Bài học này trình bày cách virtual thread hoạt động, điều kiện phiên bản, cấu hình Spring Boot, ảnh hưởng tới task execution/scheduling, transaction và ThreadLocal, các giới hạn về pinning và tài nguyên, cùng quy trình quyết định có nên bật tính năng này hay không.

## 1. Platform thread và virtual thread

Java từ lâu cung cấp thread thông qua lớp `Thread`. Một platform thread thường được ánh xạ tương đối trực tiếp tới một OS thread. OS chịu trách nhiệm lập lịch và quản lý những thread đó.

Virtual thread cũng là một `Thread`, nhưng JVM quản lý việc lập lịch nó trên một nhóm platform thread được gọi là **carrier threads**. Khi virtual thread thực hiện một thao tác blocking được runtime hỗ trợ, JVM có thể tạm dừng virtual thread và giải phóng carrier để chạy virtual thread khác.

| Đặc điểm | Platform thread | Virtual thread |
|---|---|---|
| Cách quản lý | Gắn với OS thread | JVM lập lịch trên carrier thread |
| Chi phí tạo/giữ thread | Cao hơn | Thấp hơn đáng kể |
| Số lượng phù hợp | Thường bị giới hạn ở mức nhỏ hơn | Có thể tạo số lượng rất lớn |
| Blocking I/O | Có thể giữ OS thread trong lúc chờ | Nhiều thao tác blocking có thể unmount và giải phóng carrier |
| CPU-bound task | Dùng CPU như các thread khác | Không tạo thêm năng lực CPU |
| Thread pooling | Thường dùng pool để giới hạn tài nguyên | Thường dùng một virtual thread cho mỗi task |
| API Java | `Thread` và Executor truyền thống | Vẫn dùng `Thread`, thêm builder/executor hỗ trợ virtual thread |

Nếu hàng nghìn request cùng chờ database hoặc remote API, platform thread có thể bị chiếm giữ trong lúc chờ. Virtual thread cho phép JVM tạm dừng các task đang chờ và dùng carrier cho task khác, nhờ đó giảm số OS thread cần duy trì cho cùng mức concurrency.

### Sơ đồ hoạt động khái quát

~~~text
Application tasks
   |       |       |
   v       v       v
Virtual Virtual Virtual
thread  thread  thread
   \       |       /
    \      |      /
     v     v     v
 JVM virtual-thread scheduler
          |
          v
 Carrier platform threads
          |
          v
       OS threads
~~~

Khi virtual thread bị block tại thao tác được hỗ trợ, JVM có thể unmount nó khỏi carrier. Khi thao tác hoàn tất, virtual thread được đưa vào lịch để tiếp tục chạy trên carrier phù hợp.

Không nên hiểu virtual thread là OS thread “nhẹ hơn” do hệ điều hành cung cấp. Đây là abstraction của JVM, có lifecycle và scheduler riêng.

## 2. Virtual thread có từ phiên bản JDK nào?

| JDK | Trạng thái virtual thread |
|---|---|
| JDK 19 | Preview feature |
| JDK 20 | Preview feature tiếp tục được hoàn thiện |
| JDK 21 | Chính thức (final), không cần bật preview |
| JDK 22 trở lên | Tính năng đã được chuẩn hóa và tiếp tục được cải thiện |

Virtual thread được hoàn thiện qua JEP 444 và trở thành tính năng chính thức trong JDK 21.

### Dùng preview trên JDK 19/20

Ở JDK 19 hoặc 20, ứng dụng phải bật preview ở cả compile và runtime theo quy định của phiên bản JDK:

~~~bash
javac --enable-preview --release 20 Example.java
java --enable-preview Example
~~~

Ví dụ trên minh họa JDK 20; thay số phiên bản cho đúng JDK đang dùng. Preview API có thể thay đổi giữa các bản JDK, vì vậy không nên dùng hướng dẫn JDK 21 nguyên xi cho dự án JDK 19/20.

### Dùng trên JDK 21+

Với JDK 21 trở lên, API virtual thread đã chính thức:

~~~java
Thread thread = Thread.ofVirtual()
        .name("report-task")
        .start(() -> generateReport());

thread.join();
~~~

Không cần `--enable-preview`.

Khi chọn JDK cho ứng dụng Spring Boot, hãy xem cả:
- JDK dùng để biên dịch.
- JDK dùng để chạy ứng dụng.
- JDK được cấu hình trong IDE.
- JDK của Gradle/Maven daemon.
- JDK trong container và production.

Một project compile bằng JDK 21 nhưng production chạy JDK 17 không thể sử dụng virtual thread như tính năng chuẩn của JDK 21.

## 3. Tạo virtual thread bằng Java API

JDK cung cấp nhiều cách tạo và chạy virtual thread.

### Thread.ofVirtual()

~~~java
Thread thread = Thread.ofVirtual()
        .name("report-task")
        .start(() -> generateReport());

thread.join();
~~~

`Thread.ofVirtual()` trả về builder để cấu hình tên hoặc một số thuộc tính phù hợp, sau đó khởi chạy virtual thread.

### Thread.startVirtualThread()

Với tác vụ đơn giản:

~~~java
Thread thread = Thread.startVirtualThread(() -> {
    System.out.println("Running on a virtual thread");
});
~~~

API này tạo và bắt đầu virtual thread trong một bước.

### Executors.newVirtualThreadPerTaskExecutor()

Đối với nhiều tác vụ độc lập, JDK cung cấp executor tạo một virtual thread cho mỗi task:

~~~java
try (var executor =
        Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> first = executor.submit(
            () -> loadCustomer("C-100")
    );

    Future<String> second = executor.submit(
            () -> loadOrders("C-100")
    );

    System.out.println(first.get());
    System.out.println(second.get());
}
~~~

Executor được đóng khi thoát khỏi khối `try`. Việc đóng executor chờ các task đã submit hoàn tất theo lifecycle của `ExecutorService`.

### Vì sao không nên pool virtual thread như platform thread?

Virtual thread được thiết kế để tạo theo task. Một pool cố định gồm vài chục virtual thread có thể tái tạo giới hạn concurrency mà ta muốn tránh.

Thay vào đó:
- Dùng virtual thread per task để thực thi công việc.
- Dùng connection pool để giới hạn database connection.
- Dùng semaphore/bulkhead để giới hạn dịch vụ bên ngoài có capacity thấp.
- Dùng rate limiter khi cần kiểm soát tốc độ request.

Virtual thread rẻ hơn platform thread nhưng tài nguyên mà task sử dụng vẫn có giới hạn.

## 4. Virtual thread phù hợp với workload nào?

Virtual thread đặc biệt hữu ích cho workload có nhiều thời gian chờ:

- HTTP request gọi một hoặc nhiều API bên ngoài.
- Truy vấn database có latency đáng kể.
- Đọc/ghi file hoặc socket.
- Tác vụ xử lý message chủ yếu chờ I/O.
- Một request phối hợp nhiều thao tác blocking độc lập.

Ví dụ:

~~~java
public OrderDetails loadOrderDetails(String orderId) {
    Customer customer = customerClient.findCustomer(orderId);
    List<OrderItem> items = orderRepository.findItems(orderId);
    Payment payment = paymentClient.findPayment(orderId);

    return new OrderDetails(customer, items, payment);
}
~~~

Nếu ba thao tác độc lập và đều blocking, virtual thread của request có thể chờ từng I/O mà không giữ platform thread trong suốt thời gian chờ.

Tuy nhiên, ví dụ trên vẫn gọi tuần tự. Muốn chạy đồng thời ba tác vụ cần một cơ chế concurrency riêng, chẳng hạn executor hoặc structured concurrency theo phiên bản JDK phù hợp. Virtual thread tự nó không biến các lời gọi tuần tự thành song song.

### Workload CPU-bound

Ví dụ tính toán:

~~~java
public BigInteger calculatePrimeRange(int start, int end) {
    // Tính toán số học trong thời gian dài.
}
~~~

Nếu task dành phần lớn thời gian dùng CPU, virtual thread không làm phép tính nhanh hơn. Số carrier thread vẫn bị giới hạn bởi scheduler và số CPU khả dụng.

Đối với CPU-bound workload:
- Giới hạn số task chạy đồng thời theo năng lực CPU.
- Dùng executor phù hợp với CPU parallelism.
- Tối ưu thuật toán trước khi thay loại thread.
- Đo throughput, CPU utilization và latency thực tế.

Virtual thread là công cụ xử lý concurrency có nhiều blocking, không phải thay thế cho tối ưu CPU.

## 5. Spring Boot hỗ trợ virtual thread từ phiên bản nào?

Spring Boot tích hợp cấu hình virtual thread qua property:

~~~properties
spring.threads.virtual.enabled=true
~~~

Property này được giới thiệu trong **Spring Boot 3.2**. Hỗ trợ dựa trên các khả năng của Spring Framework 6.1 và yêu cầu **JDK 21 trở lên** để virtual thread là tính năng chính thức.

| Nền tảng | Điều kiện |
|---|---|
| JDK 21+ | Có virtual thread chính thức |
| Spring Framework 6.1+ | Có các abstraction/integration hỗ trợ virtual thread |
| Spring Boot 3.2+ | Có property `spring.threads.virtual.enabled` để cấu hình hỗ trợ tự động |
| Spring Boot 3.1 trở xuống | Không có property Boot 3.2 này; có thể cần tự cấu hình API phù hợp với JDK/framework |
| Runtime JDK 17 | Không có virtual thread API chuẩn của JDK 21 |

Spring Boot 3.2 có baseline Java 17, nhưng việc chạy ứng dụng trên Java 17 **không có nghĩa** có thể bật virtual thread. Tính năng cần JDK 21+.

### Phân biệt minimum JDK của Boot và JDK cần cho virtual thread

- Một phiên bản Spring Boot có thể hỗ trợ chạy trên JDK 17.
- Cùng phiên bản Boot có thể hỗ trợ virtual thread khi ứng dụng chạy trên JDK 21+.
- Nếu chạy trên JDK thấp hơn, không thể sử dụng API virtual thread chuẩn.

Khi chọn một tổ hợp cụ thể, hãy kiểm tra release notes và compatibility matrix của đúng phiên bản Spring Boot, Spring Framework, JDK và embedded server. Không nên nâng riêng một module Spring lên version khác với BOM chỉ để lấy API virtual thread.

## 6. Bật virtual thread trong Spring Boot

Với Spring Boot 3.2+ và JDK 21+, có thể bật trong file cấu hình:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Hoặc:

~~~properties
spring.threads.virtual.enabled=true
~~~

Khi property được bật, Spring Boot có thể cấu hình các thành phần task execution và scheduling phù hợp để sử dụng virtual thread, nếu ứng dụng không tự cung cấp bean thay thế và các điều kiện auto-configuration tương ứng được đáp ứng.

Ví dụ ứng dụng:

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Không cần tự tạo một virtual thread cho mỗi bean hoặc gắn annotation mới lên từng service. Spring Boot tích hợp tính năng qua các abstraction như `TaskExecutor` và `TaskScheduler`.

### Bật bằng command line

~~~bash
java -jar app.jar --spring.threads.virtual.enabled=true
~~~

Hoặc với Gradle:

~~~bash
./gradlew bootRun --args='--spring.threads.virtual.enabled=true'
~~~

Với Maven Spring Boot plugin, có thể truyền property qua application arguments theo cấu hình plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.threads.virtual.enabled=true
~~~

Cú pháp truyền argument của build plugin có thể cần điều chỉnh theo phiên bản và cách cấu hình project. Sau khi chạy, hãy xác nhận ứng dụng thực sự nhận property và dùng đúng JDK.

## 7. Spring Boot thay đổi những gì khi bật property?

Property không làm mọi thread trong JVM trở thành virtual thread. Nó ảnh hưởng tới những thành phần Spring Boot tự cấu hình và có tích hợp tương ứng.

| Khu vực | Vai trò của virtual thread |
|---|---|
| Auto-configured task executor | Có thể thực thi task trên virtual thread |
| Auto-configured task scheduler | Có thể dùng scheduler tích hợp virtual thread |
| `@Async` | Có thể sử dụng executor do Boot cấu hình nếu không bị executor khác thay thế |
| `@Scheduled` | Có thể dùng scheduler do Boot cấu hình nếu không bị cấu hình khác thay thế |
| Servlet request processing | Phụ thuộc web server và cấu hình/version tương ứng |
| Database connection | Không đổi số connection hoặc capacity của pool |
| Reactive pipeline | Không biến reactive execution thành virtual thread tự động |

Cần hiểu property này là một **tích hợp auto-configuration**, không phải switch toàn JVM.

### Custom bean có thể thay thế auto-configuration

Nếu ứng dụng tự khai báo `TaskExecutor` hoặc `TaskScheduler`, Spring Boot có thể back off khỏi auto-configuration tương ứng. Khi đó, bật `spring.threads.virtual.enabled` không bảo đảm custom executor của ứng dụng sử dụng virtual thread.

Ví dụ custom executor dùng platform thread pool:

~~~java
@Bean
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(32);
    executor.setQueueCapacity(200);
    return executor;
}
~~~

Bean này có semantics của `ThreadPoolTaskExecutor`. Không nên giả định nó tự chuyển thành virtual-thread executor chỉ vì property Boot được bật.

Hãy kiểm tra bean thực tế được inject vào nơi dùng task execution và custom configuration có override auto-configuration hay không.

## 8. TaskExecutor và @Async

`@Async` chuyển lời gọi method sang một executor được Spring chọn. Với Boot có virtual thread support, executor auto-configured có thể sử dụng virtual thread khi property được bật và không có cấu hình khác thay thế.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Service
public class InvoiceService {

    @Async
    public CompletableFuture<String> generateInvoice(String invoiceId) {
        String result = loadAndGenerate(invoiceId);
        return CompletableFuture.completedFuture(result);
    }

    private String loadAndGenerate(String invoiceId) {
        // Công việc có thể chứa blocking I/O.
        return "invoice-" + invoiceId;
    }
}
~~~

Khi method được gọi qua Spring proxy, task được gửi tới executor được chọn cho async processing.

### Chỉ bật property có tự bật @Async không?

Không. Cần phân biệt:
- `spring.threads.virtual.enabled`: cấu hình virtual thread support cho auto-configured task infrastructure tương ứng.
- `@EnableAsync`: bật xử lý `@Async` annotation trong proxy mode.
- `@Async("executorName")`: chọn executor theo tên/qualifier cụ thể.

Nếu `reportExecutor` là custom bean dùng platform thread pool, method được gắn `@Async("reportExecutor")` có thể vẫn chạy trên platform thread dù Boot virtual threads được bật.

### Kiểm tra thread đang chạy

Trong môi trường chẩn đoán, có thể kiểm tra:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
String threadName = Thread.currentThread().getName();
~~~

`Thread.isVirtual()` có từ JDK 21. Test nên xác nhận đúng executor được dùng trong context thật, không chỉ kiểm tra property có giá trị `true`.

Self-invocation vẫn bypass async proxy, bất kể executor có virtual thread hay không. Vì vậy, gọi method `@Async` từ một method khác trong cùng bean có thể không chuyển sang executor.

## 9. TaskScheduler và @Scheduled

`@Scheduled` sử dụng task scheduling infrastructure của Spring. Spring Framework 6.1 có hỗ trợ scheduler phù hợp với virtual thread thông qua `SimpleAsyncTaskScheduler`.

~~~java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

~~~java
@Component
public class CleanupJob {

    @Scheduled(fixedRate = 30_000)
    public void cleanExpiredSessions() {
        // Công việc có thể chờ I/O.
    }
}
~~~

Khi Boot cấu hình scheduler dùng virtual thread, scheduled task có thể được thực thi theo mô hình phù hợp của scheduler đó.

### Fixed-rate, cron và fixed-delay

`SimpleAsyncTaskScheduler` được thiết kế theo mô hình một scheduler thread và có thể khởi chạy task trên virtual thread riêng. Tuy nhiên, fixed-delay task có semantics đặc biệt: task được chạy trên scheduler thread, thay vì luôn fork một virtual thread mới như các loại trigger khác.

Vì vậy:
- Không mặc định mọi scheduled task đều chạy trên một virtual thread riêng.
- Không mặc định nhiều task có thể chạy đồng thời mà không có giới hạn.
- Nếu task dài, cần hiểu overlap, fixed-rate/fixed-delay semantics và cơ chế tránh chạy trùng.

Nếu nghiệp vụ yêu cầu một job chỉ chạy một lần tại một thời điểm trên nhiều instance ứng dụng, cần cơ chế lock/distributed scheduler phù hợp. `@Scheduled` trong một JVM không phải distributed lock.

## 10. Virtual thread và Servlet request processing

Một ứng dụng Spring MVC thường xử lý request trên thread của servlet container. Việc bật virtual thread cho task executor **không tự chứng minh** request HTTP đang chạy trên virtual thread.

Hành vi request thread phụ thuộc:
- Phiên bản embedded server (Tomcat, Jetty hoặc Undertow).
- Hỗ trợ virtual thread của server.
- Cách Spring Boot tích hợp executor vào server.
- Cấu hình connector/server cụ thể.
- Cách ứng dụng deploy nếu dùng external servlet container.

Một số server và phiên bản có hỗ trợ virtual-thread-based request executor, nhưng phải kiểm tra tài liệu server/Boot tương ứng. Đừng suy ra từ việc `@Async` đang chạy trên virtual thread rằng controller request cũng đang chạy trên virtual thread.

Có thể ghi nhận tại controller:

~~~java
@RestController
@RequestMapping("/diagnostics")
public class ThreadDiagnosticsController {

    @GetMapping("/thread")
    public Map<String, Object> threadInfo() {
        Thread thread = Thread.currentThread();

        return Map.of(
                "name", thread.getName(),
                "virtual", thread.isVirtual()
        );
    }
}
~~~

Đây là endpoint chẩn đoán minh họa. Không nên expose thông tin runtime nội bộ ra public production API nếu không có nhu cầu và kiểm soát bảo mật.

Nếu request thread vẫn là platform thread, không nhất thiết cấu hình virtual thread thất bại; có thể server đang dùng executor riêng không bị property task execution thay đổi.

## 11. Virtual thread và Spring MVC blocking I/O

Spring MVC thường dùng mô hình imperative/blocking. Trong một request, controller/service có thể gọi repository hoặc HTTP client đồng bộ.

~~~java
@GetMapping("/orders/{id}")
public OrderView getOrder(@PathVariable String id) {
    Order order = orderService.findById(id);
    Customer customer = customerClient.getCustomer(order.customerId());

    return OrderView.from(order, customer);
}
~~~

Nếu request được xử lý trên virtual thread và các thao tác blocking được JVM hỗ trợ, thread có thể unmount trong lúc chờ I/O. Đây là use case phù hợp.

Nhưng cần xem:
- Client có blocking thật hay không.
- Thư viện có dùng native/foreign call hoặc cơ chế blocking đặc biệt không.
- Database connection pool có đủ capacity không.
- Có semaphore/rate limit để bảo vệ dependency ngoài không.
- Request timeout và cancellation có được xử lý đúng không.

Virtual thread không loại bỏ latency của remote service. Nó chỉ giúp sử dụng thread hiệu quả hơn trong khi chờ.

## 12. Virtual thread và Spring WebFlux

Spring WebFlux được thiết kế theo mô hình reactive/non-blocking, thường dựa trên event loop và reactive streams.

| Tiêu chí | Spring MVC + virtual thread | Spring WebFlux |
|---|---|---|
| Mô hình lập trình | Imperative/blocking có thể dùng virtual thread | Reactive, non-blocking |
| Cách chờ I/O | Virtual thread có thể park/unmount ở thao tác blocking được hỗ trợ | Event loop tiếp tục phục vụ công việc khác khi I/O chưa sẵn sàng |
| API | Thường dùng kiểu trả về đồng bộ hoặc async tùy thiết kế | Mono/Flux và reactive composition |
| Thread context | ThreadLocal gắn với từng thread | Context propagation cần chú ý |
| Mục tiêu | Làm blocking concurrency rẻ hơn | Xử lý nhiều I/O non-blocking qua event-driven model |

Không nên chuyển một ứng dụng WebFlux sang virtual thread chỉ vì nghe rằng virtual thread nhanh hơn. Nếu ứng dụng đã dùng non-blocking client và reactive pipeline hiệu quả, việc chuyển đổi có thể không mang lại lợi ích.

Ngược lại, nếu hệ thống chủ yếu dùng thư viện blocking và cần code imperative dễ hiểu, Spring MVC trên virtual thread có thể là lựa chọn phù hợp.

**Không block event-loop thread bằng code blocking chỉ vì JDK có virtual thread.** WebFlux event loop có mô hình riêng; blocking call cần được điều phối đúng scheduler nếu thật sự bắt buộc.

## 13. ThreadLocal và context propagation

Virtual thread vẫn là thread. Nó hỗ trợ `ThreadLocal` và `InheritableThreadLocal` theo semantics của Java, nhưng mỗi virtual thread có state riêng.

~~~java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

Thread.startVirtualThread(() -> {
    REQUEST_ID.set("req-123");
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
});
~~~

### ThreadLocal không tự chia sẻ giữa các virtual thread

Nếu một task tạo virtual thread mới, ThreadLocal value của thread cha không tự trở thành một context chung mutable. `InheritableThreadLocal` có semantics kế thừa khi tạo thread, nhưng không nên dùng nó làm cơ chế truyền dữ liệu tùy tiện cho hàng nghìn task.

Mỗi virtual thread có thể có ThreadLocal values riêng. Nếu tạo số lượng rất lớn virtual thread và mỗi thread giữ object lớn trong ThreadLocal, bộ nhớ vẫn có thể tăng đáng kể.

### MDC và logging context

Một số logging framework lưu MDC dựa trên ThreadLocal. Khi task chạy trên thread khác, không nên mặc định context MDC của caller được truyền qua mọi cơ chế executor hoặc callback.

Hãy kiểm tra:
- Executor có hỗ trợ context decorator không.
- Spring Security context có được truyền theo executor được chọn không.
- Trace/correlation ID có được propagate không.
- MDC được cleanup sau task hay không.

Virtual thread không tự động giải quyết mọi vấn đề context propagation.

### ThreadLocal và transaction

Spring imperative transaction thường gắn resource và transaction state với thread hiện tại thông qua transaction synchronization infrastructure.

Nếu một method đang ở trong transaction trên một virtual thread và tiếp tục thực thi đồng bộ trên chính thread đó, transaction semantics vẫn có thể hoạt động theo cơ chế imperative bình thường.

Nhưng nếu code chuyển sang một thread khác, kể cả virtual thread khác, transaction context thread-bound **không tự động chuyển sang thread mới**. Điều này cũng đúng với platform thread.

~~~java
@Transactional
public void processOrder() {
    orderRepository.save(order);
    asyncService.processNextStep();
}
~~~

Nếu `processNextStep()` chạy qua `@Async` trên một virtual thread khác, transaction đang mở ở caller không tự động được truyền sang worker thread. Worker cần transaction boundary riêng nếu nó thực hiện thao tác dữ liệu cần transaction.

Không nên nhầm virtual thread với reactive transaction context. Reactive transaction được quản lý qua reactive context theo mô hình riêng.

## 14. Virtual thread, Spring Security và request context

Một số framework dùng ThreadLocal để lưu thông tin hiện tại, ví dụ security context hoặc request context trong mô hình imperative.

Khi request được xử lý trên virtual thread, ThreadLocal có thể hoạt động trong phạm vi thread đó. Nhưng khi task được gửi sang executor khác, context propagation phụ thuộc cơ chế executor và framework integration.

Đối với Spring Security:
- Dùng executor được cấu hình để propagate SecurityContext khi cần.
- Không tự sao chép context bằng cách đọc ThreadLocal rồi giữ object qua nhiều task nếu không hiểu lifecycle.
- Đảm bảo context được cleanup sau khi task kết thúc.
- Kiểm thử quyền truy cập trong luồng async thực tế.

Đối với request-scoped bean:
- Request scope có lifecycle gắn với request.
- Một task async có thể chạy sau khi request kết thúc.
- Không nên giữ reference đến request-scoped object rồi truy cập sau lifecycle của request.
- Hãy truyền dữ liệu cần thiết qua immutable command/value object.

Virtual thread không làm request context sống lâu hơn request.

## 15. Pinning: khi virtual thread giữ carrier

Một virtual thread có thể bị **pinned** vào carrier trong một số tình huống, khiến JVM không thể unmount nó trong lúc blocking. Nếu nhiều virtual thread bị pin lâu, lợi ích về scalability có thể giảm.

Trên JDK 21–23, một nguyên nhân đáng chú ý là virtual thread thực hiện blocking operation trong vùng synchronized monitor theo những trường hợp runtime phải giữ carrier. Native method và một số foreign function call cũng có thể gây pinning.

~~~java
synchronized (lock) {
    blockingNetworkCall();
}
~~~

Nếu lời gọi blocking kéo dài trong monitor, virtual thread có thể giữ carrier trong thời gian đó. Nếu nhiều task cùng làm vậy, số carrier bị chiếm dụng có thể tăng.

### JDK 24 và cải tiến synchronized

JDK 24 đưa vào thay đổi qua JEP 491, giúp virtual thread có thể unmount khi chờ monitor trong các trường hợp trước đây gây pinning do synchronized. Vì vậy, lời khuyên “không bao giờ blocking trong synchronized vì nó luôn pin” không còn đúng cho mọi JDK hiện đại.

Tuy nhiên:
- Native/foreign call vẫn có thể tạo giới hạn hoặc pinning.
- Lock contention vẫn có chi phí.
- Giữ lock trong lúc gọi dịch vụ chậm vẫn có thể làm giảm throughput và gây nghẽn.
- Thư viện cũ có thể có hành vi blocking không tối ưu.

Khi hỗ trợ nhiều JDK, hãy kiểm tra behavior trên **JDK runtime thực tế** thay vì áp dụng một kết luận chung.

### Chẩn đoán pinning

Có thể dùng Java Flight Recorder để quan sát event liên quan virtual thread, trong đó có event `jdk.VirtualThreadPinned` trên các JDK hỗ trợ event tương ứng.

Một số phiên bản JDK cung cấp diagnostic option như `-Djdk.tracePinnedThreads`; tên, khả năng và mức hỗ trợ có thể thay đổi theo version. Ưu tiên JFR và công cụ quan sát được tài liệu JDK đang dùng hỗ trợ.

Không nên tối ưu code chỉ vì thấy từ khóa `synchronized`. Hãy đo pinning duration, số carrier bị giữ và tác động lên latency/throughput.

## 16. Synchronized, locks và contention

Virtual thread không xóa bỏ các vấn đề đồng bộ hóa.

~~~java
private final Object lock = new Object();

public void update() {
    synchronized (lock) {
        updateSharedState();
    }
}
~~~

Dù không bị pin theo cùng cách trên JDK mới, nhiều virtual thread tranh cùng một lock vẫn phải chờ nhau. Chỉ một thread có thể giữ monitor tại một thời điểm.

Các nguyên tắc vẫn quan trọng:
- Giữ critical section ngắn.
- Tránh thực hiện remote I/O khi đang giữ lock.
- Không dùng lock toàn cục cho mọi request nếu có thể chia nhỏ trạng thái.
- Đo contention trước khi thay synchronized bằng abstraction khác.
- Xác định rõ invariants cần bảo vệ.

`ReentrantLock` và các primitive concurrency khác vẫn có thể được sử dụng, nhưng không nên thay thế đồng loạt chỉ vì virtual thread.

## 17. Database connection pool vẫn là giới hạn

Một trong những hiểu lầm lớn là bật virtual thread sẽ cho phép mở hàng nghìn database connection cùng lúc.

Thực tế, connection pool như HikariCP vẫn giới hạn số connection vật lý. Nếu ứng dụng tạo 10.000 virtual thread và tất cả cùng chờ một pool có 30 connection, chỉ một số nhỏ được truy cập database cùng lúc; số còn lại vẫn chờ.

~~~text
10,000 virtual threads
         |
         v
   HikariCP pool
   maxPoolSize = 30
         |
         v
   30 DB connections
         |
         v
      Database
~~~

Đây có thể là điều mong muốn: database có capacity giới hạn và pool bảo vệ nó. Nhưng quá nhiều task chờ connection vẫn tiêu thụ heap, request state và thời gian.

Cần:
- Đặt pool size dựa trên database capacity.
- Dùng timeout lấy connection.
- Giới hạn concurrency ở tầng nghiệp vụ nếu cần.
- Thiết lập request timeout và backpressure/bulkhead.
- Theo dõi pending connection requests và acquisition latency.
- Tránh tạo task vô hạn khi downstream đang quá tải.

Virtual thread làm việc chờ rẻ hơn, nhưng không khiến resource được chờ trở nên vô hạn.

## 18. Remote API, rate limit và bulkhead

Giả sử payment provider chỉ cho phép 100 request đồng thời. Nếu app tạo 10.000 virtual thread gọi provider, provider vẫn có thể trả 429, timeout hoặc làm tăng lỗi.

Một semaphore có thể giới hạn concurrency:

~~~java
@Component
public class PaymentGatewayAdapter {

    private final Semaphore permits = new Semaphore(100);

    public PaymentResult authorize(PaymentRequest request)
            throws InterruptedException {

        permits.acquire();
        try {
            return callProvider(request);
        } finally {
            permits.release();
        }
    }
}
~~~

Đây là ví dụ minh họa một bulkhead đơn giản. Trong ứng dụng thực tế, cần thêm timeout khi chờ permit, xử lý interruption, metric và chính sách từ chối request. Có thể dùng resilience library phù hợp để cung cấp bulkhead/rate limit.

Không nên dùng semaphore không giới hạn thời gian chờ; nếu provider quá tải, task có thể xếp hàng dài và làm latency toàn ứng dụng tăng.

## 19. Virtual thread và structured concurrency

Virtual thread thường được nhắc cùng structured concurrency, nhưng đây là hai tính năng riêng.

- Virtual thread cung cấp cách chạy task đồng thời với chi phí thấp.
- Structured concurrency cung cấp cách tổ chức vòng đời nhóm task con theo phạm vi của task cha.

Structured concurrency trải qua các giai đoạn preview và thay đổi API qua nhiều phiên bản JDK. Không nên lấy code preview từ một JDK rồi dùng nguyên xi trên JDK khác.

Với ứng dụng Spring Boot, trước tiên hãy hiểu virtual thread per task và executor. Chỉ sử dụng structured concurrency khi phiên bản JDK của dự án hỗ trợ API cần thiết và team chấp nhận lifecycle/version requirements của nó.

Không nên cho rằng Spring Boot property `spring.threads.virtual.enabled` tự bật structured concurrency cho mọi request.

## 20. Giữ JVM sống: virtual thread là daemon thread

Virtual thread là daemon thread. Daemon thread không ngăn JVM thoát khi không còn non-daemon thread nào giữ tiến trình sống.

Điều này quan trọng với một số ứng dụng nhỏ hoặc chương trình chỉ tạo virtual thread để chạy công việc nền. Nếu main thread kết thúc và không còn non-daemon thread, JVM có thể thoát dù virtual thread chưa hoàn thành.

~~~java
public static void main(String[] args) {
    Thread.startVirtualThread(() -> {
        performLongRunningWork();
    });
}
~~~

Chương trình có thể kết thúc trước khi task hoàn thành nếu không có cơ chế giữ lifecycle hoặc chờ task.

Cách đúng tùy ứng dụng:
- Chờ task bằng `join()` hoặc future khi cần.
- Quản lý executor trong lifecycle có close/shutdown.
- Với Spring Boot, dùng lifecycle của application và scheduler/executor được quản lý.
- Nếu cấu hình virtual thread khiến ứng dụng phụ thuộc vào virtual threads cho công việc nền, xem xét property `spring.main.keep-alive=true` theo tài liệu phiên bản Boot đang dùng.

Ví dụ:

~~~yaml
spring:
  main:
    keep-alive: true
  threads:
    virtual:
      enabled: true
~~~

`spring.main.keep-alive` giúp Spring Boot giữ JVM sống trong những trường hợp cần thiết khi ứng dụng dùng daemon virtual threads. Không nên thêm property này máy móc cho mọi project; hãy hiểu tiến trình nào đang giữ lifecycle và test shutdown behavior.

## 21. Virtual thread và shutdown của ứng dụng

Một ứng dụng server có lifecycle riêng, nhưng các tác vụ nền vẫn cần được quản lý:

- Task đang chạy có được chờ hoàn thành khi shutdown không?
- Task có thể bị interrupt/cancel không?
- Executor được đóng khi ApplicationContext dừng không?
- Message consumer có ngừng nhận message trước khi đóng resource không?
- Scheduled task đang chạy có được kết thúc theo chính sách mong muốn không?

Virtual thread không tự làm các tác vụ có lifecycle đúng. Hãy dùng Spring-managed executor/scheduler hoặc quản lý executor do ứng dụng tạo trong bean lifecycle phù hợp.

Nếu tự tạo executor:

~~~java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    // Submit tasks và chờ kết quả.
}
~~~

Trong Spring bean lâu dài, không tạo executor mới cho từng request mà không quản lý shutdown. Đưa executor vào lifecycle bean và đóng đúng thời điểm.

## 22. Cấu hình Spring Boot task executor thủ công

Khi cần kiểm soát rõ executor, có thể cấu hình Spring abstraction.

Ví dụ dùng executor virtual-thread-per-task trực tiếp:

~~~java
@Configuration(proxyBeanMethods = false)
public class VirtualTaskConfiguration {

    @Bean(destroyMethod = "close")
    ExecutorService virtualTaskExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
~~~

Sau đó inject `ExecutorService` vào thành phần cần chạy task. Tên bean và qualifier nên rõ ràng nếu ứng dụng có nhiều executor.

Với Spring Framework có `VirtualThreadTaskExecutor`, có thể dùng abstraction đó khi version tương thích:

~~~java
@Bean
TaskExecutor taskExecutor() {
    return new VirtualThreadTaskExecutor("app-");
}
~~~

Hãy xác nhận class/API có mặt trong version Spring Framework được Boot quản lý. Không phải mọi project Spring Boot cũ đều có class này.

### Đừng tạo nhiều executor không có lý do

Một executor cho mỗi bean hoặc mỗi request làm lifecycle và observability phức tạp. Chọn số executor theo loại workload và yêu cầu isolation, không theo số class.

Nếu dùng auto-configuration của Boot, hãy để Boot quản lý executor mặc định trừ khi có yêu cầu cụ thể cần custom. Nếu custom, xác định rõ executor nào được dùng bởi `@Async`, scheduling và các component khác.

## 23. Kiểm tra ứng dụng có thật sự dùng virtual thread

Bật property chỉ là một bước cấu hình. Cần quan sát hành vi runtime.

~~~java
log.info(
        "Thread name={}, virtual={}",
        Thread.currentThread().getName(),
        Thread.currentThread().isVirtual()
);
~~~

Có thể ghi log trong:
- Controller request handler.
- Method được gọi bằng `@Async`.
- Scheduled task.
- Executor task tùy chỉnh.

Đừng chỉ kiểm tra ở main method; main thread có thể là platform thread trong khi một số task khác dùng virtual thread.

### Thread dump và JFR

Các công cụ JDK hiện đại hỗ trợ hiển thị virtual thread trong thread dump. Tùy JDK và công cụ, cách liệt kê có thể khác so với platform thread truyền thống.

Khi điều tra:
- Xem số virtual thread đang tồn tại.
- Xem task đang chờ ở đâu.
- Tìm carrier thread bị bận hoặc pin.
- Kiểm tra lock contention.
- Kết hợp thread dump với JFR và metric ứng dụng.

Không nên kết luận hiệu quả chỉ từ số lượng thread hiển thị. Hãy đo throughput, p95/p99 latency, heap, CPU, connection pool và downstream errors.

## 24. Tác động tới ThreadPoolTaskExecutor và thư viện bên thứ ba

Nhiều thư viện được viết với giả định có thread pool cố định. Khi chuyển sang virtual thread, cần kiểm tra:

- Thư viện có tự tạo thread pool riêng không?
- Có thread affinity hoặc ThreadLocal state sống lâu theo worker không?
- Có assumption rằng cùng task luôn chạy trên một thread không?
- Có giới hạn queue/concurrency dựa trên pool size không?
- Có code dùng thread name để phân loại worker không?

Virtual thread per task thường có lifecycle ngắn. ThreadLocal state không nên được dùng để giữ cache lớn hoặc tài nguyên dài hạn.

Nếu thư viện cần pool để giới hạn số kết nối hoặc request, giữ giới hạn đó ở resource layer. Không bỏ pool chỉ vì virtual thread có chi phí thấp.

## 25. Virtual thread không phải reactive replacement cho mọi ứng dụng

Khi chọn giữa Spring MVC với virtual thread và WebFlux, hãy xem hệ sinh thái hiện có:

- Nếu code và thư viện chủ yếu blocking, MVC + virtual thread có thể đơn giản hóa concurrency.
- Nếu hệ thống đã dùng non-blocking client, reactive streams và cần backpressure end-to-end, WebFlux vẫn phù hợp.
- Nếu một ứng dụng trộn blocking và reactive, phải quản lý boundary cẩn thận.
- Không block event loop để tận dụng virtual thread.
- Không chuyển mọi API trả về Mono/Flux thành blocking call chỉ vì JDK 21 có virtual thread.

Cả hai mô hình đều có thể xử lý concurrency tốt nếu thiết kế phù hợp. Không có một lựa chọn luôn thắng trong mọi workload.

## 26. Quan sát hiệu năng trước và sau khi bật

Một benchmark có ý nghĩa cần cùng workload và cùng điều kiện môi trường.

| Chỉ số | Điều cần quan sát |
|---|---|
| Throughput | Số request/task hoàn thành mỗi giây |
| p50/p95/p99 latency | Phân phối thời gian phản hồi |
| CPU utilization | Có phải workload đang CPU-bound không |
| Heap / GC | Số lượng task và context có làm tăng memory pressure không |
| Connection pool pending | Có nhiều task chờ DB connection không |
| HTTP client pool | Có nghẽn connection hoặc rate limit downstream không |
| Thread pinning | Có virtual thread giữ carrier lâu không |
| Error/timeout rate | Tăng concurrency có làm lỗi hệ thống ngoài tăng không |

Một test tải tốt nên:
1. Dùng workload đại diện.
2. Giữ dữ liệu và môi trường giống nhau.
3. Chạy đủ lâu để loại bỏ startup noise.
4. So sánh cả latency và throughput.
5. Kiểm tra dependency ngoài không bị quá tải.
6. Thử cả tình huống downstream chậm hoặc lỗi.
7. Kiểm tra memory và shutdown behavior.

Nếu throughput tăng nhưng p99 latency hoặc error rate tăng mạnh, thay đổi chưa chắc tốt cho người dùng.

## 27. Các lỗi thường gặp khi bật virtual thread

### Build báo không tìm thấy API virtual thread

Nguyên nhân có thể:
- Compile bằng JDK dưới 21.
- Toolchain trỏ JDK khác với terminal.
- Dùng Spring Framework version không có abstraction đang import.
- Đang dùng preview API nhưng chưa bật cờ đúng cách trên JDK cũ.

Kiểm tra:

~~~bash
java -version
./gradlew -version
mvn -version
~~~

Gradle/Maven daemon có thể dùng JDK khác với shell đang chạy. Kiểm tra cấu hình toolchain và runtime của build tool.

### spring.threads.virtual.enabled không có tác dụng

Kiểm tra:
- Spring Boot version có hỗ trợ property không.
- Runtime JDK có phải 21+ không.
- Profile/config property có được nạp không.
- Custom TaskExecutor/TaskScheduler có làm auto-configuration back off không.
- Method có thực sự chạy qua executor được chọn không.

### @Async vẫn chạy trên platform thread

Kiểm tra:
- `@EnableAsync` đã bật chưa.
- Lời gọi có đi qua Spring proxy không.
- Có dùng `@Async("customExecutor")` không.
- Executor custom là loại nào.
- Bean nào được chọn khi có nhiều TaskExecutor.

### Request thread vẫn là platform thread

Đây có thể là hành vi bình thường nếu servlet container đang dùng executor riêng. Kiểm tra tài liệu embedded server và cấu hình request executor; đừng suy ra request processing từ task executor của Spring.

### Database timeout tăng sau khi bật

Có thể nhiều task hơn cùng tranh connection pool hoặc database. Giới hạn concurrency, xem pool metrics và điều chỉnh timeout/backpressure; đừng chỉ tăng pool size mà không xét database capacity.

### CPU tăng nhưng latency không giảm

Workload có thể CPU-bound, hoặc concurrency tăng làm contention. Virtual thread không tăng số core. Hãy profiling CPU, lock và thuật toán.

### ThreadLocal hoặc MDC bị mất

Task đã chuyển sang thread khác hoặc executor không propagate context. Dùng cơ chế context propagation phù hợp, truyền dữ liệu qua parameter hoặc thiết kế logging context riêng.

### JVM thoát khi task nền còn chạy

Virtual thread là daemon. Quản lý lifecycle và chờ task; xem xét `spring.main.keep-alive` nếu ứng dụng Spring Boot cần giữ JVM sống trong trường hợp đó.

## 28. Ma trận quyết định theo JDK và Spring Boot

| Runtime / Framework | Có thể dùng virtual thread? | Cách tiếp cận |
|---|---|---|
| JDK 17 + Boot 3.2+ | Không có virtual thread chuẩn | Dùng platform thread; không bật property kỳ vọng virtual thread |
| JDK 19/20 + framework tương ứng | Preview | Chỉ dùng nếu chấp nhận preview và bật cờ đúng cách |
| JDK 21 + Boot 3.2+ | Có | Có thể bật `spring.threads.virtual.enabled=true` |
| JDK 21+ + Boot mới hơn tương thích | Có | Dùng tích hợp Boot và kiểm tra custom executor/server |
| Boot cũ + JDK 21 | Java API có | Tự cấu hình theo Spring Framework/API có sẵn; không có Boot property nếu version không hỗ trợ |
| JDK 24+ | Có, với cải tiến runtime như JEP 491 | Đánh giá pinning behavior theo JDK mới, vẫn đo workload thực tế |

Bảng này là hướng dẫn khái quát. Khi chọn một tổ hợp cụ thể, cần xem release notes và compatibility matrix của phiên bản Spring Boot, Spring Framework, JDK và embedded server.

## 29. Quy trình chuyển một ứng dụng sang virtual thread

Có thể tiến hành theo các bước:

**Bước 1 — Kiểm kê runtime.** Xác nhận JDK local, CI, container và production. Xác nhận Spring Boot/Framework version và embedded server.

**Bước 2 — Phân loại workload.** Xác định phần nào blocking I/O, phần nào CPU-bound, phần nào phụ thuộc pool hoặc rate limit.

**Bước 3 — Kiểm tra executor hiện có.** Liệt kê auto-configured và custom `TaskExecutor`/`TaskScheduler`, các executor của thư viện và server.

**Bước 4 — Kiểm tra context propagation.** Xác định transaction, security, MDC, request scope và ThreadLocal được dùng ở đâu.

**Bước 5 — Bật ở môi trường thử nghiệm.** Với JDK 21+ và Boot 3.2+, bật property virtual thread ở profile/test environment có kiểm soát.

**Bước 6 — Xác nhận runtime thread.** Quan sát ở đúng điểm thực thi: request, async task và scheduled job.

**Bước 7 — Kiểm tra resource limits.** Đo DB pool, HTTP client pool, semaphore, queue và rate limit.

**Bước 8 — Chạy tải đại diện.** So sánh throughput, p95/p99 latency, CPU, heap, GC và downstream errors.

**Bước 9 — Kiểm tra lỗi và shutdown.** Thử downstream chậm, timeout, cancellation, task đang chạy lúc shutdown và context propagation.

**Bước 10 — Triển khai có quan sát.** Rollout theo môi trường, theo dõi metric/log và giữ khả năng rollback cấu hình.

Không cần chuyển tất cả executor hoặc mọi tác vụ sang virtual thread cùng lúc. Có thể bắt đầu với một workload blocking phù hợp và mở rộng khi có bằng chứng.

## 30. Ví dụ cấu hình Spring Boot hoàn chỉnh

Một ứng dụng Spring Boot 3.2+ chạy trên JDK 21+ có thể bắt đầu với:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true

logging:
  level:
    com.example: INFO
~~~

Application:

~~~java
@SpringBootApplication
@EnableAsync
@EnableScheduling
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Service async:

~~~java
@Service
public class OrderNotificationService {

    @Async
    public CompletableFuture<Void> sendNotification(OrderId orderId) {
        notificationClient.send(orderId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Scheduled task:

~~~java
@Component
public class ExpiredOrderCleanup {

    @Scheduled(fixedDelayString = "PT1M")
    public void clean() {
        orderRepository.deleteExpiredOrders();
    }
}
~~~

Ví dụ giả định các collaborator như `notificationClient` và `orderRepository` đã được inject qua constructor, cùng các bean hạ tầng tương ứng. Nếu ứng dụng tự cấu hình executor/scheduler hoặc dùng server executor riêng, cần xác nhận thành phần nào thực sự sử dụng virtual thread.

`spring.main.keep-alive` chỉ cần khi lifecycle ứng dụng có nguy cơ không còn non-daemon thread giữ JVM sống. Trong một web application server thông thường, hãy kiểm tra lifecycle thực tế trước khi quyết định.

## 31. Các nguyên tắc cần ghi nhớ

- Virtual thread chính thức từ **JDK 21**; JDK 19/20 dùng preview.
- Tích hợp property `spring.threads.virtual.enabled` có từ **Spring Boot 3.2** và cần JDK 21+.
- Spring Framework cung cấp executor/scheduler abstraction; Boot cấu hình một số thành phần tự động.
- Bật property không biến tất cả thread trong JVM thành virtual thread.
- `@Async` vẫn cần async processing được bật và lời gọi qua proxy.
- Custom executor có thể thay thế auto-configured executor.
- Servlet request thread phụ thuộc embedded server và cấu hình riêng.
- Virtual thread hữu ích cho blocking I/O, không làm CPU-bound task nhanh hơn.
- Database connection pool, HTTP client pool và rate limit vẫn là giới hạn.
- ThreadLocal tồn tại trên virtual thread nhưng context không tự động truyền qua thread boundary.
- Transaction imperative gắn với thread hiện tại; chuyển sang virtual thread khác không tự mang transaction sang.
- Pinning behavior phụ thuộc JDK; JDK 24 cải thiện monitor pinning qua JEP 491.
- Virtual thread là daemon thread; quản lý lifecycle và shutdown rõ ràng.
- Đo workload thật trước khi kết luận tính năng cải thiện hiệu năng.

Virtual thread cung cấp một cách thực thi blocking concurrency hiệu quả hơn, nhưng giá trị thực tế phụ thuộc vào phiên bản JDK, Spring Boot, executor được chọn và capacity của các hệ thống phía sau. Khi hiểu rõ các ranh giới này, bạn có thể áp dụng virtual thread vào workload phù hợp mà vẫn giữ transaction, security context, scheduler và resource management có thể dự đoán được.

