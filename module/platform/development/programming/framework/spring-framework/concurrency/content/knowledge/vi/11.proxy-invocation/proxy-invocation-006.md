# Tách phương thức bất đồng bộ sang bean cộng tác

## 1. Mục tiêu và vấn đề

Trong Spring Framework, `@Async` cho phép một phương thức được thực thi thông qua `TaskExecutor` mà caller không phải tự tạo `Thread`. Tuy nhiên, với **chế độ proxy mặc định**, annotation được áp dụng khi lời gọi **đi qua Spring proxy**. Nếu một method trên bean gọi method `@Async` khác bằng `this.method()`, đó là lời gọi nội bộ trên đối tượng đích và thường **không được proxy chặn**. Kết quả là code chạy đồng bộ trên thread gọi, trái với mong đợi.

**Tách phương thức bất đồng bộ sang một bean cộng tác** là cách thiết kế đơn giản, rõ trách nhiệm và thường được khuyến nghị: bean thứ nhất điều phối nghiệp vụ; bean thứ hai sở hữu method `@Async` và được inject vào bean điều phối. Lời gọi giữa hai bean đi qua reference do Spring cấp, để interceptor có cơ hội chuyển công việc sang executor.

~~~text
Trước — self-invocation:

Caller -> OrderService.start()
                   |
                   +--> this.sendEmailAsync()
                           ^ 
                           | Không đi qua Spring proxy
                           v
                       Chạy trực tiếp trên thread hiện tại


Sau — tách bean cộng tác:

Caller -> OrderService.start()
                   |
                   +--> EmailWorker proxy.sendAsync()
                               |
                               +--> @Async interceptor
                                         |
                                         +--> TaskExecutor
                                                   |
                                                   +--> worker thread
                                                            |
                                                            +--> EmailWorker target
~~~

**Hai điều kiện cùng cần:** bean thực thi phải được **Spring IoC container quản lý**, và method `@Async` phải được gọi qua cơ chế interception thích hợp (trong proxy mode là **gọi qua proxy**). Chỉ tách class mà vẫn dùng `new EmailWorker()` thì không giải quyết được vấn đề.

## 2. Vì sao gọi nội bộ làm @Async không có hiệu lực?

Spring hỗ trợ xử lý `@Async` qua `@EnableAsync` và hạ tầng AOP. Trong `AdviceMode.PROXY` mặc định, một object được dùng bởi caller có thể là proxy. Proxy kiểm tra những lời gọi đi qua nó, gửi method `@Async` đến executor, rồi thực thi method thật trên worker.

Nhưng bên trong method của **target bean**, biểu thức `this` tham chiếu chính target. Lời gọi `this.asyncMethod()` **không trở lại proxy** để đi qua interceptor.

~~~java
@Service
public class OrderService {
    public void checkout(Order order) {
        saveOrder(order);
        this.sendEmailAsync(order.id()); // KHÔNG kích hoạt @Async qua proxy
    }

    @Async
    public void sendEmailAsync(long orderId) {
        sendEmail(orderId);
    }
}
~~~

Đây là **đoạn code minh họa**, không phải ứng dụng độc lập: các kiểu `Order`, `saveOrder`, `sendEmail` và import chưa được khai báo. Kể cả khi `OrderService` là singleton được container tạo và đã có `@EnableAsync`, dòng `this.sendEmailAsync(...)` vẫn là lời gọi Java nội bộ thông thường. Nó chạy trên thread hiện tại.

Điểm dễ nhầm: gọi `checkout()` **thông qua proxy** không làm **mọi lời gọi nội bộ** bên trong `checkout()` tự động được proxy tiếp tục intercept. Tại ranh giới target, `this` không phải cùng proxy bên ngoài theo cách Spring proxy AOP mặc định vận hành.

### 2.1. Các điều kiện không thể thay thế lẫn nhau

| Điều kiện | Vì sao cần? | Nếu thiếu? |
| --- | --- | --- |
| `@EnableAsync` hoặc hạ tầng async tương ứng | Cho phép Spring đăng ký xử lý annotation | Annotation có thể không tạo async interceptor |
| Worker là bean do container quản lý | Bean được đi qua các bước post-processing/proxy | Object tự tạo bằng `new` không được Spring tự động proxy |
| Method có thể được intercept | Ví dụ public instance method, không final, với kiểu proxy phù hợp | Private/final/static method không thể được proxy can thiệp như kỳ vọng |
| Caller dùng reference được inject từ Spring | Lời gọi đi qua proxy | `this.method()` hoặc `new Worker().method()` bỏ qua proxy |
| Executor đúng tên/kiểu và còn khả năng nhận task | Dispatcher có tài nguyên để gửi task | Có thể bị từ chối hoặc chạy theo chính sách khác |

Một method trả về `CompletableFuture` **không chứng minh** rằng nó đang chạy bất đồng bộ: ngay cả lời gọi Java đồng bộ cũng có thể trả `CompletableFuture.completedFuture(value)`. Phải quan sát ranh giới lời gọi và executor.

## 3. Thiết kế trước – sau: tách coordinator và worker

### 3.1. Trước: một service làm cả điều phối lẫn tác vụ nền

~~~java
@Service
public class ReportService {

    public void requestReport(long reportId) {
        markRequested(reportId);
        generateAsync(reportId); // lời gọi nội bộ
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generateAsync(long id) {
        return CompletableFuture.completedFuture(renderReport(id));
    }
}
~~~

Đoạn trên để giải thích anti-pattern; `markRequested`, `renderReport`, import và executor cần được định nghĩa thêm. `generateAsync(reportId)` **không** đi qua Spring proxy, vì vậy `renderReport` vẫn chạy trên caller thread. Nếu `renderReport` chặn I/O, HTTP request hoặc thread điều phối tiếp tục bị giữ chờ.

Kể cả đổi thành `this.generateAsync(reportId)` hoặc thêm `@Async` vào chính method `requestReport`, cũng chưa giải quyết đúng vấn đề về ranh giới, lifetime và hợp đồng nghiệp vụ. Đánh dấu coordinator là async có thể chỉ chuyển cả workflow sang thread khác, không tạo ra ranh giới rõ giữa lưu trạng thái và dựng báo cáo.

### 3.2. Sau: coordinator chỉ điều phối, worker thực thi async

~~~java
@Service
public class ReportWorker {

    @Async("reportExecutor")
    public CompletableFuture<String> generateAsync(long reportId) {
        String output = renderReport(reportId);
        return CompletableFuture.completedFuture(output);
    }

    private String renderReport(long id) {
        return "report-" + id;
    }
}

@Service
public class ReportCoordinator {
    private final ReportWorker worker;

    public ReportCoordinator(ReportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> requestReport(long id) {
        return worker.generateAsync(id); // đi qua bean được inject
    }
}
~~~

Đây là các class minh họa trong project Spring có component scan, import, `@EnableAsync` và bean `reportExecutor`. **Tách đúng** không phải vì class tên Worker, mà vì `ReportCoordinator` nhận **Spring-managed reference** của `ReportWorker`. Khi `generateAsync` được gọi từ coordinator, Spring proxy có thể gửi method sang executor.

Bảng trách nhiệm:

| Thành phần | Trách nhiệm | Thường chạy ở đâu? |
| --- | --- | --- |
| Controller / consumer | Nhận yêu cầu, validate input, chọn giao thức trả kết quả | HTTP/request/message thread |
| `ReportCoordinator` | Điều phối use case, tạo job ID, kiểm tra quyền, lưu trạng thái yêu cầu | Caller thread (trừ khi chủ động cấu hình khác) |
| `ReportWorker` | Thực thi tác vụ nặng, I/O hoặc CPU theo hợp đồng | Executor thread khi gọi qua `@Async` proxy |
| `TaskExecutor` | Cấp worker, queue, giới hạn độ đồng thời và xử lý quá tải | Hạ tầng thực thi |
| Job store / outbox nếu cần | Lưu việc và trạng thái bền vững, hỗ trợ restart/retry | Hệ lưu trữ bên ngoài process |

Cấu trúc hai bean thường giúp test độc lập, chọn pool riêng và thể hiện rõ chỗ code chuyển sang xử lý nền.

## 4. Các bước triển khai đúng trong ứng dụng Spring

### Bước 1 — bật cơ chế @Async trong ApplicationContext

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("report-worker-");
        return executor;
    }
}
~~~

Đây là **mảnh cấu hình** (cần import từ Spring). `@EnableAsync` bật xử lý asynchronous method execution trong context tương ứng. `ThreadPoolTaskExecutor` là bean do Spring quản lý; Spring sẽ khởi tạo và đóng nó theo lifecycle thích hợp.

Không nên tự tạo `new ThreadPoolTaskExecutor()` trong mỗi request: ngoài việc khó quản lý tài nguyên, bạn còn phải tự initialize/shutdown, và method `@Async` không tự chọn executor mới ấy chỉ vì nó tồn tại.

### Bước 2 — worker là bean của Spring

Worker có thể được tạo bằng `@Service`/`@Component` và component scan, hoặc qua factory method `@Bean`:

~~~java
@Bean
public ReportWorker reportWorker() {
    return new ReportWorker();
}
~~~

Có từ khóa `new` **bên trong factory method `@Bean` không phải lỗi**: object trả về sẽ được container đăng ký và post-process. Lỗi là việc caller tự giữ một object khác được tạo ngoài container, như `new ReportWorker().generateAsync(...)`.

### Bước 3 — inject worker qua constructor, không tạo thủ công

~~~java
public ReportCoordinator(ReportWorker worker) {
    this.worker = worker;
}
~~~

Với constructor injection, dependency được resolve từ Spring context. Trong chế độ proxy, Spring có thể inject proxy tương ứng thay vì target trực tiếp. Điều này giúp ranh giới AOP minh bạch hơn so với tự lấy bean từ `ApplicationContext` trong code nghiệp vụ.

### Bước 4 — gọi public @Async method qua reference cộng tác

~~~java
return worker.generateAsync(reportId);
~~~

Method nên được gọi từ bean **khác**, không phải `this.generateAsync(...)`. Dùng `@Async("reportExecutor")` để chỉ định pool rõ ràng khi có nhiều executor. Không suy ra việc khai báo bean tên `reportExecutor` khiến mọi `@Async` tự chọn nó nếu không có qualifier/quy tắc resolution phù hợp.

### Bước 5 — quyết định hợp đồng trả về và xử lý lỗi

Đối với nghiệp vụ cần kết quả, dùng `CompletableFuture<T>`/`Future<T>` phù hợp. Với fire-and-forget `void`, caller không có Future để quan sát lỗi; cần `AsyncUncaughtExceptionHandler`, logging và cơ chế giám sát phù hợp. `@Async` không cung cấp hàng đợi bền vững hay bảo đảm exactly-once.

Không gọi `future.join()` hoặc `future.get()` ngay sau dispatch nếu mục tiêu là giải phóng thread gọi. Khi thật sự phải đợi kết quả, việc đợi là hợp lệ nhưng cần timeout/cancellation và UX phù hợp.

## 5. Ví dụ hoàn chỉnh, chạy được bằng Java 17 và Spring Framework

Demo cho thấy **cùng một Spring context** có cả anti-pattern self-invocation và cách tách bean đúng. Chúng ta không dựa vào `Thread.sleep()` hoặc thứ tự scheduling ngẫu nhiên để kết luận, mà kiểm tra tên thread và proxy sau khi `Future` hoàn thành.

Sử dụng **JDK 17+, Gradle 8.5+ và Spring Framework 6.1.14**. Demo là ứng dụng command-line, không cần Spring Boot hoặc HTTP server.

### 5.1. Cấu trúc project

~~~text
async-collaborator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncCollaboratorDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'async-collaborator-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.AsyncCollaboratorDemo'
}
~~~

**src/main/java/demo/AsyncCollaboratorDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncCollaboratorDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            String callerThread = Thread.currentThread().getName();

            ReportWorker worker = context.getBean(ReportWorker.class);
            ReportCoordinator coordinator =
                    context.getBean(ReportCoordinator.class);
            LegacyReportService legacy =
                    context.getBean(LegacyReportService.class);

            System.out.println("worker is Spring proxy: " +
                    AopUtils.isAopProxy(worker));

            // Anti-pattern: managed bean nhưng tự gọi method @Async.
            String selfName = legacy.startBySelfCall()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("self-call runs on caller: " +
                    selfName.equals(callerThread));

            // Cách đúng: coordinator gọi method của worker đã inject.
            WorkResult result = coordinator.start("R-42")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("collaborator uses executor: " +
                    result.threadName().startsWith("report-worker-"));
            System.out.println("report ID preserved: " +
                    result.reportId().equals("R-42"));

            // Object tự new không được Spring đăng ký/proxy.
            String manualThread = new ReportWorker()
                    .generateAsync("R-43")
                    .get(5, TimeUnit.SECONDS).threadName();
            System.out.println("manual new runs on caller: " +
                    manualThread.equals(callerThread));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("reportExecutor")
        public ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("report-worker-");
            return executor;
        }

        @Bean
        public LegacyReportService legacyReportService() {
            return new LegacyReportService();
        }

        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public ReportCoordinator reportCoordinator(ReportWorker worker) {
            return new ReportCoordinator(worker);
        }
    }

    public record WorkResult(String reportId, String threadName) { }

    public static class LegacyReportService {

        public CompletableFuture<String> startBySelfCall() {
            return this.buildAsync();
        }

        @Async("reportExecutor")
        public CompletableFuture<String> buildAsync() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }

    public static class ReportWorker {

        @Async("reportExecutor")
        public CompletableFuture<WorkResult> generateAsync(
                String reportId) {

            WorkResult result = new WorkResult(
                    reportId, Thread.currentThread().getName());
            return CompletableFuture.completedFuture(result);
        }
    }

    public static class ReportCoordinator {
        private final ReportWorker worker;

        public ReportCoordinator(ReportWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<WorkResult> start(String reportId) {
            return worker.generateAsync(reportId);
        }
    }
}
~~~

### 5.2. Chạy chương trình

Tại thư mục gốc của project, khi đã có Java 17+ và Gradle:

~~~bash
gradle run
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

Với executor hoạt động bình thường và task hoàn tất trong giới hạn `get(5, TimeUnit.SECONDS)`, **stdout do chương trình tự in chính xác**:

~~~text
worker is Spring proxy: true
self-call runs on caller: true
collaborator uses executor: true
report ID preserved: true
manual new runs on caller: true
~~~

Gradle/Spring có thể thêm log khởi động hoặc thông báo build ngoài năm dòng trên. Tên thread thực tế có thể là `report-worker-1`, nhưng ví dụ kiểm tra **prefix** nên không phụ thuộc hậu tố/số lượng worker.

### 5.3. Vì sao kết quả đúng?

1. `@EnableAsync` được xử lý trong cùng `AnnotationConfigApplicationContext` chứa các bean.
2. `ReportWorker` được tạo qua `@Bean` và đi qua Spring bean post-processing; `AopUtils.isAopProxy(worker)` trả về `true` trong cấu hình mặc định này (class không khai báo interface và method đủ điều kiện proxy).
3. `LegacyReportService` cũng là managed bean, nhưng `startBySelfCall()` gọi `this.buildAsync()` **bên trong target**. Method đánh dấu `@Async` không được proxy chặn; giá trị tên thread bằng caller.
4. `ReportCoordinator` nhận `ReportWorker` qua tham số `@Bean`. Spring inject reference đã qua xử lý; `worker.generateAsync(...)` **đi qua proxy**, rồi `TaskExecutor` chạy code trên worker có prefix `report-worker-`.
5. `new ReportWorker()` tạo object ngoài context; lời gọi trả một CompletableFuture đã hoàn tất nhưng **vẫn chạy đồng bộ** trên caller.
6. Context được đóng bằng `try-with-resources` sau khi các Future đã hoàn tất, tránh để thread pool tồn tại ngoài vòng đời demo.

Đây là **chương trình hoàn chỉnh**; các ví dụ rời ở phần trước cần được đặt vào project Spring có import và cấu hình phù hợp.

## 6. Thiết kế API của hai bean để không che mất lỗi

### 6.1. Giữ ranh giới bất đồng bộ trong API worker

Một phương pháp thực tế là để worker trả `CompletableFuture<ReportResult>` còn coordinator trả lại future đó hoặc transform nó:

~~~java
public CompletableFuture<ReportResult> requestReport(ReportRequest request) {
    validate(request);
    return worker.generateAsync(request)
            .thenApply(this::toResponseModel);
}
~~~

Đây là **mảnh code minh họa**: `ReportResult`, `ReportRequest`, `validate`, `toResponseModel` chưa được định nghĩa. Trong `CompletableFuture`, `thenApply` không có hậu tố `Async` có thể chạy trên thread hoàn thành stage trước hoặc thread caller nếu stage đã hoàn tất. Nếu việc biến đổi nặng, xem xét `thenApplyAsync(..., chosenExecutor)` với executor được chọn rõ ràng.

Nếu coordinator chỉ cần xác nhận yêu cầu đã được tiếp nhận và không chờ kết quả, cần thiết kế **job ID và trạng thái job** riêng, không trả về lời hứa mơ hồ rằng job chắc chắn hoàn tất.

### 6.2. Lỗi trong async worker không giống lỗi synchronous

Với `@Async` trả `CompletableFuture<T>`, lỗi của phần thực thi nên được quan sát qua future:

~~~java
CompletableFuture<ReportResult> future = worker.generateAsync(request);

return future.whenComplete((value, error) -> {
    if (error != null) {
        // Ghi nhận thất bại và cập nhật job status phù hợp.
    }
});
~~~

Đoạn này là minh họa. Đừng coi việc gọi `whenComplete` đã xử lý hoặc phục hồi lỗi: nếu callback không thay đổi trạng thái kết quả, future vẫn hoàn thành lỗi. Có thể dùng `handle`, `exceptionally` hoặc retry có giới hạn khi hợp đồng nghiệp vụ cho phép.

Với `@Async void`, caller không có Future để chờ. Lỗi không tự ném trở lại thread caller vốn đã trả về; cần `AsyncUncaughtExceptionHandler`, logging và theo dõi lỗi.

`@Async` sử dụng executor trong bộ nhớ và có thể gặp **task rejection** khi pool quá tải/shutdown. Không được xem một lời gọi trả bình thường là bảo đảm durability nếu đã chọn rejection handler bỏ việc âm thầm. Với công việc bắt buộc, ưu tiên phản hồi từ chối rõ ràng hoặc durable queue/outbox.

## 7. Transaction: vì sao tách bean còn giúp thấy rõ ranh giới

Trong ứng dụng có `@Transactional`, một hiểu nhầm thường thấy:

~~~java
@Transactional
public void placeOrder(Order order) {
    repository.save(order);
    emailWorker.sendAsync(order.id());
}
~~~

Đây là đoạn minh họa (cần khai báo `Order`, repository và worker). Nếu lời gọi `sendAsync` qua proxy kích hoạt worker khác thread, **transaction gắn với thread của caller không tự đi theo worker**. Worker có thể chạy **trước khi transaction caller commit**. Nếu worker đọc database, nó có thể không thấy record vừa ghi hoặc thấy trạng thái chưa như mong đợi.

Tách worker giúp kiến trúc buộc phải trả lời:

- Worker cần tham số/DTO gì, và có cần đọc lại dữ liệu đã commit từ DB không?
- Khi nào mới được gửi email hoặc phát sự kiện — ngay khi submit hay chỉ sau commit?
- Nếu transaction caller rollback, công việc nền đã gửi phải xử lý thế nào?
- Nếu worker thất bại, ai retry/cập nhật trạng thái? Có cần idempotency không?

Nếu hành động nền chỉ được xảy ra **sau commit**, có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` cho tình huống phù hợp, hoặc **transactional outbox** khi phải có bảo đảm bền vững qua crash/restart. Không chỉ đơn giản thêm `@Async` hoặc `@Transactional` trên cùng method và kỳ vọng công việc tự đợi transaction của caller.

Trong worker, nếu cần transaction riêng, cấu hình ranh giới transaction trên method thực thi với cơ chế Spring phù hợp và lưu ý cách phối hợp nhiều proxy. Một transaction trong worker không phải continuation tự động của transaction caller.

## 8. Dữ liệu, context và tính an toàn luồng

Việc tách bean giải quyết **proxy interception**, không tự giải quyết tất cả bài toán concurrency.

**Không truyền object mutable dùng chung một cách tùy tiện.** Nếu controller nhận request rồi gửi cùng một object có thể bị sửa vào `@Async`, worker có thể đọc giá trị thay đổi giữa chừng. Ưu tiên immutable DTO/record hoặc snapshot dữ liệu tại điểm dispatch; dữ liệu không được thiết kế immutable cần có chính sách ownership rõ ràng.

**Đừng giữ state theo request trong field singleton của worker.** Một `@Service` mặc định là singleton. Nhiều thread pool có thể gọi cùng worker instance đồng thời. Ví dụ `private String currentOrderId` trên singleton có nguy cơ race và lẫn thông tin giữa các tác vụ. Đưa ID vào tham số, local variable hoặc storage đúng scope.

**ThreadLocal không tự truyền sang executor thread.** MDC/tracing, SecurityContext, request attributes và transaction context thường cần cơ chế propagate hoặc truyền dữ liệu rõ ràng. Spring Security có các wrapper phù hợp, còn `TaskDecorator` có thể trang trí Runnable để capture/restore thông tin. Phải cleanup để không rò rỉ context khi pool tái sử dụng thread.

**Cancellation là hợp tác.** `Future.cancel(true)` có thể gửi interrupt khi cấu hình/implementation hỗ trợ, nhưng không ép mọi I/O bên ngoài dừng ngay. Thiết kế timeout và trạng thái job ở tầng nghiệp vụ.

**Thread scheduling không đảm bảo thứ tự.** Nếu coordinator gửi task A rồi task B vào một pool nhiều worker, B có thể hoàn thành trước A. Nếu cần ordering/idempotency, phải thiết kế độc lập.

## 9. Những trường hợp tách bean vẫn chưa đủ

| Trường hợp | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Tách thành hai class nhưng dùng `new ReportWorker()` | Worker không qua container/proxy | Đăng ký bean và inject từ Spring |
| Bean worker có `@Service` nhưng ngoài vùng scan | Bean không được đăng ký | Kiểm tra `@ComponentScan`, cấu hình ứng dụng và profile |
| Có `@Async` nhưng thiếu `@EnableAsync` | Chưa bật infrastructure | Bật async trong ApplicationContext chứa worker |
| Coordinator tự gọi method `@Async` trên chính nó | Self-invocation | Chuyển method sang bean cộng tác khác |
| Gọi private/final/static method qua proxy | Không thỏa khả năng interception | Public, non-final instance method trên bean phù hợp |
| Bean có interface nhưng inject concrete class khi dùng JDK proxy | Proxy có thể chỉ implement interface | Inject qua interface hoặc cấu hình class proxy thích hợp |
| Dùng `@Async` trên method `@Configuration` | Không phải nơi được hỗ trợ như service method | Để `@Configuration` khai báo bean, logic trong service |
| Gọi worker từ `@PostConstruct` của chính worker | Lifecycle/self-call không qua proxy | Điều phối từ bean khác sau startup |
| Đã tách bean nhưng caller gọi `future.get()` ngay | Caller vẫn block đợi kết quả | Trả future hoặc tách job lifecycle |
| Worker chạy rồi nhưng caller thiếu transaction context | ThreadLocal/transaction không tự kế thừa | Xác định ranh giới transaction trong worker hoặc sau commit |
| Worker dùng mutable shared field trên singleton | @Async không cung cấp synchronization | Stateless/immutable hoặc lock/atomic operation phù hợp |
| Tác vụ phải survive restart nhưng chỉ dùng in-memory executor | Task không bền vững | Job store/outbox/message broker |

### 9.1. Vì sao không nên mặc định dùng self-injection?

Một cách thường được nhắc đến là inject chính bean vào một field rồi gọi `selfProxy.asyncMethod()` để đi qua proxy. Cách này có thể cần vòng phụ thuộc/cơ chế lazy injection, khiến code khó hiểu và khó kiểm thử. Nó giấu ý đồ nghiệp vụ trong mẹo AOP thay vì diễn đạt một dependency thực.

Tương tự, `AopContext.currentProxy()` phụ thuộc cấu hình exposeProxy và khiến business logic phụ thuộc hạ tầng Spring AOP. Khi trách nhiệm async thực sự là một công việc riêng, **tách bean cộng tác thường rõ ràng và ít ràng buộc hơn**.

### 9.2. Có phương án không dùng bean thứ hai không?

Có. Ví dụ tự gửi `Runnable`/`Callable` trực tiếp vào `TaskExecutor`, hoặc sử dụng `CompletableFuture.supplyAsync(..., executor)` với executor được inject. Các cách này **không phụ thuộc interception của `@Async`**, nhưng caller phải tự quản lý cách gửi, xử lý lỗi và phối hợp kết quả.

Có thể dùng `@EnableAsync(mode = AdviceMode.ASPECTJ)` và weaving được thiết lập đúng để can thiệp cả self-invocation. Tuy nhiên đây là một chế độ triển khai khác, cần dependency/cấu hình riêng; không phải lựa chọn mặc định cho một ứng dụng chỉ cần tách coordinator và worker.

Không nên tách vô số class chỉ để tránh một `this`: kiến trúc cần có ranh giới trách nhiệm có ý nghĩa. Với service nhỏ, chọn cách direct executor khi phù hợp cũng là thiết kế hợp lệ.

## 10. Kiểm thử đúng ranh giới proxy

Một unit test gọi `new ReportWorker()` **không thể xác nhận** `@Async` hoạt động. Nó chỉ kiểm tra thân method Java. Muốn kiểm tra interception, test cần **ApplicationContext** có `@EnableAsync`, executor và bean thật.

Kịch bản test gợi ý:

1. Lấy worker qua context, dùng `AopUtils.isAopProxy` như một tín hiệu bổ trợ.
2. Gọi method `@Async` từ **bean khác**, nhận `Future` và đợi kết quả có timeout.
3. Kiểm tra worker nhìn thấy thread name có prefix cấu hình; không phụ thuộc số thứ tự cụ thể của thread.
4. Kiểm tra `this.method()` trong phiên bản anti-pattern vẫn chạy trên caller để chứng minh test có giá trị phân biệt.
5. Test exception và rejection; timeout không được xem là kết quả thành công.
6. Test dữ liệu truyền qua worker và tính idempotency khi có retry.

**Tránh test chỉ dựa trên tốc độ** như “method trả về dưới 100ms là async”. Scheduling có thể làm test không ổn định. Kiểm tra đúng executor/proxy và kết quả cụ thể đáng tin hơn.

Trong production, thêm metrics cho active threads, queue depth, rejected tasks, thời gian task chờ và thời gian xử lý. Tên pool riêng (`report-worker-`) giúp đọc log/thread dump, nhưng không thay thế trace ID hoặc correlation ID.

## 11. Checklist khi refactor một method @Async đang self-call

- [ ] Xác định chính xác method nào gọi `this.asyncMethod()` và kỳ vọng async hiện tại.
- [ ] Chỉ tách phần công việc nền có ý nghĩa sang bean `@Service`/`@Component` hoặc `@Bean` riêng.
- [ ] Bật `@EnableAsync` trong context chứa worker.
- [ ] Inject worker vào coordinator bằng constructor; **không tự `new`** worker từ coordinator.
- [ ] Đặt `@Async("executorName")` trên public non-final method của worker khi dùng proxy mode.
- [ ] Cấp executor đúng tên, capacity và rejection policy; tránh queue không kiểm soát.
- [ ] Thiết kế kiểu trả về `void`/`Future`/`CompletableFuture` và cách caller quan sát lỗi.
- [ ] Không dùng `get()`/`join()` ngay sau dispatch khi cần non-blocking caller.
- [ ] Đánh giá transaction và thời điểm commit; dùng after-commit/outbox nếu cần.
- [ ] Truyền immutable request data hoặc DTO, không ghi state của request vào singleton field.
- [ ] Xác minh bằng integration test có Spring context, proxy và worker thread đúng.
- [ ] Có logging/metrics và chiến lược shutdown, timeout, retry, idempotency nếu nghiệp vụ cần.

## 12. Câu hỏi tự kiểm tra

1. **Vì sao `this.generateAsync()` không chạy nền dù bean có `@Service`?** Trong proxy mode, self-invocation gọi target trực tiếp, bỏ qua async interceptor.
2. **Tách phương thức sang class mới rồi `new` class ấy có sửa được không?** Không; worker phải được Spring quản lý và gọi qua proxy.
3. **Một phương thức `@Bean` trả về `new ReportWorker()` có làm worker unmanaged không?** Không. Object trả về được đăng ký thành bean và đi qua bean post-processing phù hợp.
4. **Vai trò khác nhau giữa coordinator và worker là gì?** Coordinator nhận/điều phối use case; worker thực hiện tác vụ cần chạy bằng executor.
5. **Tại sao `CompletableFuture.completedFuture(...)` không chứng minh đang async?** Nó cũng có thể tạo và hoàn thành ngay trên caller thread.
6. **Khi controller gọi worker rồi ngay lập tức `future.get()` thì sao?** Caller vẫn chặn chờ; không đạt mục tiêu giảm thời gian giữ request thread.
7. **Tách bean có tự chuyển transaction của caller sang worker không?** Không; transaction thường gắn với thread, cần ranh giới riêng và chính sách sau commit.
8. **Tại sao không nên dùng shared mutable field trong singleton worker?** Nhiều worker threads có thể cùng thao tác và gây race condition.
9. **Có cách nào tránh tách bean không?** Có: gửi việc trực tiếp vào executor hoặc dùng AspectJ weaving phù hợp, nhưng hợp đồng và độ phức tạp khác.
10. **Làm sao test chắc `@Async` hoạt động?** Gọi qua Spring-managed collaborator trong context đã bật async và kiểm tra thread thực thi/kết quả có timeout.
11. **Có một worker bean đã qua proxy nhưng method được gọi từ constructor/`@PostConstruct` của chính worker thì sao?** Không nên mong proxy interception cho lời gọi nội bộ trong lifecycle; điều phối sau khởi tạo qua bean khác.
12. **Nếu job bắt buộc xử lý qua restart, chỉ tách bean và gắn `@Async` đã đủ chưa?** Chưa. Cần cách lưu công việc bền vững như outbox hoặc job store, cùng retry và idempotency.

**Kết luận:** Tách phương thức bất đồng bộ sang **bean cộng tác được Spring quản lý và inject** giúp chuyển lời gọi từ **self-invocation** thành **cross-bean proxy invocation**. Đây là cách rõ ràng để `@Async` phát huy tác dụng trong proxy mode; còn an toàn luồng, transaction, độ bền công việc, lỗi và kiểm soát quá tải vẫn phải được thiết kế riêng.

### Tài liệu tham khảo chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — @EnableAsync](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Proxying Mechanisms and Self-Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
