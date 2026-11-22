# Cấu hình bộ thực thi tác vụ cho xử lý bất đồng bộ Spring MVC

> **Phạm vi:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, **Spring MVC chạy trên Servlet stack**. Bài giải thích luồng async Servlet, bộ thực thi `AsyncTaskExecutor`, cách Spring Boot cung cấp `applicationTaskExecutor`, cách tinh chỉnh pool và timeout, cách sử dụng `WebMvcConfigurer#configureAsyncSupport`, `Callable`, `WebAsyncTask`, `DeferredResult`, streaming, lỗi từ chối tác vụ, context propagation, đo tải và kiểm thử. Ví dụ Maven chạy trên Spring Boot **3.5.0** với JDK 17.

## 1. Vấn đề: tại sao cần một executor riêng cho MVC async?

Trong Spring MVC đồng bộ, request thường giữ một Servlet container thread trong thời gian method controller và service xử lý. Khi tác vụ chặn lâu (blocking call đến service/DB chậm), Servlet worker bận cho đến khi request kết thúc.

Spring MVC hỗ trợ **asynchronous request processing** theo Servlet API: controller có thể trả về `Callable<T>`, `WebAsyncTask<T>` hoặc `DeferredResult<T>`. Khi đó MVC đưa request vào async mode để Servlet thread ban đầu có thể thoát ra; kết quả được hoàn tất sau rồi dispatch trở lại container thread để ghi HTTP response.

Một câu hỏi vận hành quan trọng xuất hiện: **tác vụ chặn được chạy ở thread pool nào, có bao nhiêu luồng, giới hạn queue ra sao, và nếu timeout/rejection thì ứng dụng xử lý thế nào?** Đây chính là vai trò của `AsyncTaskExecutor`.

**Không đánh đồng các pool:**

| Thành phần | Mục đích | Điều không nên suy ra |
|---|---|---|
| Servlet container thread pool | Nhận/dispatch HTTP requests, chạy Servlet pipeline | Không mặc nhiên là nơi chạy `Callable` của Spring MVC |
| MVC `AsyncTaskExecutor` | Thực thi `Callable` / `WebAsyncTask`; hỗ trợ một số tác vụ async streaming | Không tự làm DB/JDBC trở thành non-blocking |
| Executor dùng cho `DeferredResult` | Do **ứng dụng** quyết định khi xử lý sự kiện/công việc hoàn tất result | MVC không tự gửi logic của bạn vào pool |
| `@Async` executor | Thực thi các method được Spring AOP xử lý bởi `@Async` | Không đồng nghĩa MVC async chỉ vì cùng tên “async” |
| Spring scheduler | Chạy scheduled jobs theo lịch | Không phải mặc định thay thế executor cho MVC |
| Reactor Netty event loop (WebFlux) | Xử lý I/O non-blocking của reactive server | Không phải Servlet MVC worker pool |

Spring MVC có thể giải phóng Servlet thread trong thời gian đợi, nhưng request/connection vẫn tồn tại; không có bảo đảm việc xử lý nhanh hơn hoặc throughput tăng vô hạn. Khi backend gọi blocking API, **một worker thread khác vẫn bị chiếm** trong lúc chờ.

## 2. Luồng Servlet async diễn ra thế nào?

### 2.1. Với Callable<T>

Sơ đồ:

~~~text
Client
  |
  v
Tomcat Servlet worker: REQUEST dispatch
  |
  v
DispatcherServlet -> Controller trả Callable<T>
  |
  +--> Spring MVC gọi startAsync()
  |    và submit Callable vào AsyncTaskExecutor
  |
  +--> Servlet worker ban đầu được trả về container
  |    (HTTP response chưa hoàn tất)
  |
  v
mvc-worker-1: Callable.call() thực thi
  |
  +--> service, DB, remote call, kết quả hoặc exception
  |
  v
Async result được đăng ký với Spring MVC
  |
  v
Servlet container: ASYNC dispatch
  |
  v
DispatcherServlet xử lý kết quả, converter/exception resolver
  |
  v
HTTP status + headers + body gửi tới client
~~~

Điểm chính:

1. Controller được gọi ở lượt HTTP ban đầu và trả một `Callable`, không phải chờ `call()` hoàn tất.
2. Spring MVC kích hoạt Servlet async processing và gửi `Callable` vào `AsyncTaskExecutor`.
3. Nếu result/exception được tạo, container thực hiện **ASYNC redispatch**; `DispatcherServlet` xử lý result một lần nữa.
4. HTTP response được hoàn tất theo cơ chế message conversion, view rendering hoặc exception handling tương ứng.
5. Async timeout/error có thể kích hoạt lifecycle callbacks và exception resolution.

Đây không phải HTTP “fire-and-forget”. Client còn đợi response; ứng dụng phải có cách hoàn tất hoặc timeout request.

### 2.2. Với DeferredResult<T>

`DeferredResult` khác `Callable` ở chỗ **ứng dụng tự quyết định khi nào và từ đâu cung cấp kết quả**:

~~~text
Controller trả DeferredResult<T>
  |
  +--> Spring MVC kích hoạt request async
  |
  +--> một sự kiện/callback/công việc do app quản lý
           |
           +--> deferredResult.setResult(value)
           +--> deferredResult.setErrorResult(exception)
  |
  v
Spring MVC ASYNC redispatch -> response
~~~

MVC **không tự lấy một Callable từ DeferredResult để gửi executor**. Nếu app muốn xử lý bằng thread pool, app phải tự submit một `Runnable`/`Callable` vào một executor đã chọn. Nếu kết quả đến từ Kafka callback, message broker hoặc một event loop khác, có thể không cần một tác vụ blocking mới.

### 2.3. Với WebAsyncTask<T>

`WebAsyncTask` bọc một `Callable` nhưng cho phép thêm timeout, executor riêng cho request, callback timeout/error/completion. Nó phù hợp khi một endpoint cần timeout khác mặc định hoặc cần chính sách tác vụ cụ thể.

Ví dụ fragment:

~~~java
@GetMapping("/task")
public WebAsyncTask<String> task() {
    WebAsyncTask<String> result =
            new WebAsyncTask<>(3000L, () -> "completed");

    result.onTimeout(() -> "timed-out");
    return result;
}
~~~

Đoạn trên là **method fragment** trong controller, không phải class độc lập. `3000L` là **3.000 milliseconds**, không phải 3.000 seconds. Chạy bình thường sẽ trả `completed`; callback timeout chỉ dùng khi request thực sự đạt điều kiện timeout.

## 3. Spring Boot 3.5 tự cấu hình applicationTaskExecutor

Trong ứng dụng Boot thông thường, khi không có `Executor` bean tùy chỉnh gây điều kiện back off, Boot có thể tự cấu hình một `AsyncTaskExecutor` và đăng ký dưới tên **`applicationTaskExecutor`**.

- Khi dùng **platform threads** (ví dụ Java 17), Boot 3.5 thông thường tạo `ThreadPoolTaskExecutor` với cấu hình mặc định hợp lý.
- Khi dùng **virtual threads** (Java **21+**, `spring.threads.virtual.enabled=true`), Boot có thể dùng `SimpleAsyncTaskExecutor` dựa trên virtual threads; các property `spring.task.execution.pool.*` sẽ không còn mang cùng tác dụng.
- Boot tích hợp executor này với nhiều chức năng như Spring MVC async, một số WebFlux/GraphQL/WebSocket và các task khác, tùy bean/cấu hình hiện diện.
- Riêng **Spring MVC**, Boot yêu cầu executor tích hợp có tên **`applicationTaskExecutor`** và kiểu **`AsyncTaskExecutor`**.

Điều này có nghĩa một bean `Executor` tên bất kỳ có thể **không** được Spring MVC chọn như bạn kỳ vọng. Ví dụ định nghĩa `@Bean("taskExecutor") Executor` để dùng với `@Async` không tự bảo đảm MVC `Callable` chạy ở đó.

### 3.1. Chỉnh pool bằng application.properties khi dùng executor auto-configured

Nếu chọn cách giữ Boot tự quản executor, có thể cấu hình:

~~~properties
# Dùng trong phương án A: để Boot tự tạo executor.
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=32
spring.task.execution.pool.keep-alive=30s
spring.task.execution.thread-name-prefix=mvc-worker-
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s

# Timeout cho async HTTP request ở Spring MVC:
spring.mvc.async.request-timeout=5s
~~~

Đây là **phương án A độc lập**. Không tự tạo `@Bean("applicationTaskExecutor")` trong cùng project rồi cho rằng những `spring.task.execution.pool.*` phía trên vẫn tự điều chỉnh bean do bạn tạo thủ công. Các property này chủ yếu có tác dụng với executor **do Boot auto-configure**.

Spring Boot 3.5 mặc định có core size **8** cho platform-thread `ThreadPoolTaskExecutor`; có thể tinh chỉnh bằng các properties. Không nên mặc định giá trị tối ưu cho mọi workload.

**Nuance về queue:**

- `core-size=4` tạo mức core threads.
- `queue-capacity=32` làm queue **có giới hạn**, thay vì để unbounded.
- `max-size=8` mới có ý nghĩa khi queue đã đầy và pool cần mở rộng trên core-size.
- Khi 8 threads bận và queue đã đầy, task mới có thể bị từ chối; không nên để queue vô hạn chỉ để “không thấy lỗi” vì latency và memory có thể tăng không kiểm soát.
- Cần đo service time, arrival rate, CPU, DB pool, giới hạn downstream và deadline để chọn kích thước.

Một queue lớn khiến request đợi rất lâu trước khi bắt đầu thực thi, có thể **timeout dù nghiệp vụ chưa chạy**. Vì vậy queue capacity, request timeout và client/proxy timeout phải được thiết kế cùng nhau.

### 3.2. Nếu có custom Executor bean: vì sao Boot không tự tạo?

Spring Boot 3.5 có điều kiện auto-configuration: khi có bean `Executor` do ứng dụng tạo, Boot có thể **back off** thay vì tạo `AsyncTaskExecutor` mặc định.

Ví dụ chỉ có:

~~~java
@Bean("taskExecutor")
Executor someExecutor() {
    return Executors.newFixedThreadPool(4);
}
~~~

Đây là **fragment** cần import và lifecycle cleanup; nó **không đủ** để bảo đảm MVC async sử dụng executor này. Đặc biệt, `@Async` có quy tắc chọn executor riêng.

Các hướng xử lý hợp lệ:

1. Định nghĩa rõ một bean **`applicationTaskExecutor` có kiểu `AsyncTaskExecutor`** cho MVC.
2. Dùng `WebMvcConfigurer#configureAsyncSupport` để đặt executor cụ thể tại tầng Spring MVC.
3. Nếu muốn Boot vẫn auto-configure executor bất chấp custom Executor, có thể xét property **`spring.task.execution.mode=force`** của Boot **3.5**; đọc kỹ tác động vì nó cũng ảnh hưởng việc chọn executor cho những tích hợp khác và `@Async` khi không có `AsyncConfigurer`.
4. Nếu có nhiều executor, đặt tên và qualifier rõ ràng; dùng `@Async("specificExecutor")` hoặc `AsyncConfigurer` cho công việc nghiệp vụ cần pool riêng.

Không đổi executor cho tất cả framework integrations chỉ để xử lý một endpoint chậm. Với ứng dụng đa dịch vụ, tách pool có thể ngăn một nhóm tác vụ bão hòa ảnh hưởng nhóm còn lại.

### 3.3. spring.task.execution.mode=force dùng khi nào?

Boot 3.5 có thể được cấu hình:

~~~properties
spring.task.execution.mode=force
~~~

Trong phương án này, Boot cố tạo và ưu tiên dùng executor auto-configured cho các integrations, ngay cả khi ứng dụng đăng ký một số Executor tùy chỉnh. Tuy nhiên việc lựa chọn executor cho `@Async` vẫn cần xét `AsyncConfigurer`; đặt `@Primary` hoặc tên `taskExecutor` không có nghĩa chắc chắn override được executor cho mọi integrations dưới chế độ `force`.

**Không bật `force` mặc định** nếu đã có thiết kế rõ ràng nhiều executor; có thể làm thay đổi hành vi task execution của những module khác. Trong bài này, project runnable chọn **phương án B: khai báo bean tường minh**, không bật `force`.

## 4. WebMvcConfigurer#configureAsyncSupport: cách tùy chỉnh ở tầng MVC

Spring Framework cung cấp callback:

~~~java
@Override
public void configureAsyncSupport(
        AsyncSupportConfigurer configurer) {

    configurer.setTaskExecutor(mvcAsyncExecutor);
    configurer.setDefaultTimeout(5000L);
}
~~~

Đoạn này là method trong class `implements WebMvcConfigurer`, với `mvcAsyncExecutor` đã được inject trước đó.

Các API tiêu biểu:

| API | Ý nghĩa |
|---|---|
| `AsyncSupportConfigurer#setTaskExecutor` | Chỉ định `AsyncTaskExecutor` cho MVC `Callable` và blocking writes khi streaming reactive values |
| `setDefaultTimeout(long)` | Timeout mặc định tính bằng **milliseconds** cho MVC async processing |
| `registerCallableInterceptors(...)` | Thêm `CallableProcessingInterceptor` quan sát lifecycle callable |
| `registerDeferredResultInterceptors(...)` | Thêm `DeferredResultProcessingInterceptor` cho các deferred request |
| `WebAsyncTask` | Có thể chỉ định timeout/executor/callback riêng cho một request |
| `DeferredResult(Long timeout)` | Có thể đặt timeout riêng cho một request deferred |

**Thứ tự áp dụng timeout:** default của Servlet container có thể được dùng nếu bạn không đặt timeout ở MVC; cấu hình tại `WebAsyncTask` hoặc `DeferredResult` có thể ghi đè default cho request cụ thể. Ngoài ra còn có deadline của client, ingress và gateway.

**Không thêm `@EnableWebMvc`** chỉ để tùy chỉnh async support trong Spring Boot. `@EnableWebMvc` có thể khiến Boot MVC auto-configuration back off; `@Configuration` + `implements WebMvcConfigurer` đủ cho những override bổ sung.

## 5. Project hoàn chỉnh: một AsyncTaskExecutor có giới hạn + 3 kiểu async endpoint

Mục tiêu project:

- `Callable<ReportView>` để chứng minh Spring MVC submit công việc vào worker pool.
- `WebAsyncTask<ResponseEntity<ReportView>>` với timeout riêng và timeout callback.
- `DeferredResult<ResponseEntity<ReportView>>` được **ứng dụng tự submit** vào cùng executor và hoàn tất bằng `setResult` / `setErrorResult`.
- Pool có kích thước và queue bounded, thread prefix dễ quan sát.
- Thêm advice cho tình huống `TaskRejectedException` có thể phát sinh khi pool bị bão hòa.
- Kiểm thử `MockMvc` với `asyncStarted()` và `asyncDispatch()`.

### 5.1. Cấu trúc project

~~~text
mvc-async-executor-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mvcasync/
    MvcAsyncApplication.java
    ExecutorConfiguration.java
    MvcAsyncConfiguration.java
    ReportService.java
    AsyncReportController.java
    AsyncErrorAdvice.java
  src/test/java/com/example/mvcasync/
    AsyncReportControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-async-executor-demo</artifactId>
    <version>1.0.0</version>
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

`spring-boot-starter-web` dùng Spring MVC và embedded Tomcat trong cấu hình mặc định. **Không cần** `spring-boot-starter-webflux` để sử dụng `Callable`, `DeferredResult` hoặc `WebAsyncTask`.

### 5.3. application.properties

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Demo chọn phương án B: khai báo applicationTaskExecutor bằng Java.
# Không khai spring.task.execution.pool.* ở đây vì chúng
# không tự chỉnh bean ThreadPoolTaskExecutor tạo thủ công.
~~~

### 5.4. Entry point

`src/main/java/com/example/mvcasync/MvcAsyncApplication.java`:

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcAsyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcAsyncApplication.class, args);
    }
}
~~~

### 5.5. ExecutorConfiguration: pool bounded và tên bean chuẩn

`src/main/java/com/example/mvcasync/ExecutorConfiguration.java`:

~~~java
package com.example.mvcasync;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
~~~

Giải thích:

- **Bean name `applicationTaskExecutor`** giúp Spring Boot nhận đúng executor dành cho MVC async.
- Return type `ThreadPoolTaskExecutor` implement `AsyncTaskExecutor`, khác một `Executor` JDK thuần chỉ có method `execute`.
- Core 4, max 8, queue 32 là **giá trị minh họa**, không phải cấu hình đề xuất cho mọi server.
- Thread prefix giúp quan sát worker thread trong tests/logs.
- `ThreadPoolTaskExecutor` là Spring-managed bean, được lifecycle container initialize/close. Không gọi `initialize()` một lần nữa trong code bean khi container đã quản lý.
- `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(10)` thể hiện chủ đích chờ một khoảng trong shutdown; **không** bảo đảm mọi request hoàn tất nếu ingress/client/server đã timeout hoặc process bị kill.

Nếu hệ thống có nhiều executor, cần kiểm tra `@Async`, JPA, WebSocket, bootstrap và các auto-config tích hợp khác có đang dùng bean này không. Có thể tách pool cho tác vụ đặc thù nếu muốn tránh cùng một nhóm việc bão hòa toàn hệ thống.

### 5.6. MvcAsyncConfiguration: chọn pool MVC + timeout

`src/main/java/com/example/mvcasync/MvcAsyncConfiguration.java`:

~~~java
package com.example.mvcasync;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfiguration implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public MvcAsyncConfiguration(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L);
    }
}
~~~

Bài cố ý **chỉ định rõ executor bằng cả bean name và callback `configureAsyncSupport`** để hành vi demo không phụ thuộc suy luận về bean selection khi có cấu hình mở rộng. Trong app Boot đơn giản, chỉ bean `applicationTaskExecutor` hoặc chỉ Boot auto-configured executor thường đã đủ cho integration MVC; việc gọi `setTaskExecutor` ở đây chủ yếu làm rõ điểm mở rộng của Spring MVC.

Giá trị `5_000L` = 5 giây. Đây là **default request timeout**, không phải timeout của mọi JDBC/HTTP call bên trong worker thread. Phải đặt deadline riêng cho downstream IO và có kế hoạch hủy những tác vụ không còn cần thiết.

### 5.7. ReportService: mô phỏng công việc blocking chạy trên worker

`src/main/java/com/example/mvcasync/ReportService.java`:

~~~java
package com.example.mvcasync;

import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public ReportView load(String id) throws InterruptedException {
        // Demo mô phỏng một blocking dependency trong 80ms.
        // Production nên cấu hình timeout cho JDBC/HTTP client thực.
        TimeUnit.MILLISECONDS.sleep(80);

        return new ReportView(
                id, Thread.currentThread().getName());
    }

    public record ReportView(
            String id, String workerThread) {
    }
}
~~~

`sleep(80)` chỉ phục vụ quan sát demo và tạo ranh giới async rõ ràng; **không** khuyến nghị dùng sleep để xử lý business logic. Với JDBC blocking, worker thread vẫn bị chiếm trong lúc chờ; dùng pool và downstream connection limits phù hợp.

### 5.8. AsyncReportController: Callable, WebAsyncTask và DeferredResult

`src/main/java/com/example/mvcasync/AsyncReportController.java`:

~~~java
package com.example.mvcasync;

import java.util.concurrent.Callable;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncReportController {

    private final ReportService service;
    private final AsyncTaskExecutor executor;

    public AsyncReportController(
            ReportService service,
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.service = service;
        this.executor = executor;
    }

    @GetMapping("/callable/{id}")
    public Callable<ReportService.ReportView> callable(
            @PathVariable String id) {

        // Method controller trả ngay Callable.
        // Spring MVC tự submit Callable vào executor đã cấu hình.
        return () -> service.load(id);
    }

    @GetMapping("/web-async-task/{id}")
    public WebAsyncTask<ResponseEntity<ReportService.ReportView>>
            webAsyncTask(@PathVariable String id) {

        WebAsyncTask<ResponseEntity<ReportService.ReportView>>
                task = new WebAsyncTask<>(
                        3_000L,
                        () -> ResponseEntity.ok(service.load(id))
                );

        task.onTimeout(() -> ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ReportService.ReportView(
                        id, "timed-out")));

        return task;
    }

    @GetMapping("/deferred/{id}")
    public DeferredResult<ResponseEntity<ReportService.ReportView>>
            deferred(@PathVariable String id) {

        DeferredResult<ResponseEntity<ReportService.ReportView>>
                result = new DeferredResult<>(3_000L);

        result.onTimeout(() -> result.setErrorResult(
                new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Async result was not produced in time")));

        // Spring MVC KHÔNG tự submit code này cho DeferredResult.
        // Ứng dụng chủ động dùng executor do mình chọn.
        executor.execute(() -> {
            try {
                ReportService.ReportView report = service.load(id);
                result.setResult(ResponseEntity.ok(report));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                result.setErrorResult(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Async task interrupted", ex));
            } catch (Exception ex) {
                result.setErrorResult(ex);
            }
        });

        return result;
    }
}
~~~

**Phân biệt ba nhánh:**

| Endpoint | Ai submit công việc? | Timeout |
|---|---|---|
| `/callable/{id}` | **Spring MVC** submit returned `Callable` | Default 5 giây từ `configureAsyncSupport` |
| `/web-async-task/{id}` | MVC thực thi Callable trong `WebAsyncTask` | Request timeout riêng 3 giây + callback |
| `/deferred/{id}` | **Ứng dụng** gọi `executor.execute`; sau đó `setResult` hoặc `setErrorResult` | DeferredResult riêng 3 giây + error result |

Bài mẫu cố ý dùng chung executor để dễ quan sát. Khi một hệ thống có nhiều workload, có thể dùng executor riêng cho công việc hoàn tất `DeferredResult` nếu không muốn tranh pool với MVC `Callable`/streaming.

**Timeout không mặc nhiên hủy worker:** nếu request đã timeout trong lúc một JDBC call vẫn đang block, thread có thể tiếp tục chạy. `DeferredResult#setResult` sau khi result đã hoàn tất có thể trả `false` (không thay được response đã xong). Production nên có cancellation/cooperative interruption, downstream timeouts và cleanup phù hợp.

### 5.9. AsyncErrorAdvice: xử lý task rejection khi tới tầng MVC

`src/main/java/com/example/mvcasync/AsyncErrorAdvice.java`:

~~~java
package com.example.mvcasync;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class AsyncErrorAdvice {

    @ExceptionHandler(TaskRejectedException.class)
    public ResponseEntity<ProblemDetail> rejected(
            TaskRejectedException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Async capacity is temporarily exhausted");
        body.setTitle("Server busy");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .body(body);
    }
}
~~~

`TaskRejectedException` có thể xuất hiện khi executor không nhận thêm task (ví dụ pool và queue đều bão hòa). Advice xử lý được **khi exception đi qua MVC exception handling và response chưa commit**. Đây không phải bảo đảm mọi dạng overload đều thành 503; nếu lỗi phát sinh ở tầng container, network hoặc sau khi response commit, cần cơ chế xử lý khác.

**Không dùng `CallerRunsPolicy` một cách máy móc** để né rejection: nếu caller là Servlet request thread, chính sách này có thể khiến công việc blocking chạy ngay trên Servlet worker, làm mất tác dụng giải phóng thread của MVC async. Ưu tiên backpressure, capacity limits, 503/429 theo contract và quan sát load.

## 6. Chạy và kiểm tra ứng dụng

Trong thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
mvn clean package
java -jar target/mvc-async-executor-demo-1.0.0.jar
~~~

Gửi các request:

~~~bash
curl -i http://localhost:8080/api/async/callable/42
curl -i http://localhost:8080/api/async/web-async-task/42
curl -i http://localhost:8080/api/async/deferred/42
~~~

Ở điều kiện bình thường, **mỗi endpoint** trả HTTP **200 OK**, body JSON có hai trường:

~~~json
{
  "id": "42",
  "workerThread": "mvc-worker-1"
}
~~~

Tên worker thread có thể khác nhau theo request/thứ tự thread creation, ví dụ `mvc-worker-2` hoặc `mvc-worker-3`; chỉ prefix `mvc-worker-` là được code cấu hình. Body không được kỳ vọng giống hệt về thread suffix hoặc JSON spacing/order.

**Kết quả quan trọng:** `ReportService.load` chạy trên một `mvc-worker-*` do `ThreadPoolTaskExecutor` tạo, không chạy dài trên Servlet HTTP request thread ban đầu. Request vẫn là một HTTP request duy nhất từ góc nhìn client dù bên trong có async redispatch.

### 6.1. Chạy nhiều yêu cầu song song

Ví dụ thử gửi ba request với các ID khác nhau:

~~~bash
curl "http://localhost:8080/api/async/callable/A" &
curl "http://localhost:8080/api/async/callable/B" &
curl "http://localhost:8080/api/async/callable/C" &
wait
~~~

Bash sẽ chạy ba lệnh curl đồng thời. Output có thể xen kẽ vì nhiều tiến trình ghi stdout; thứ tự kết thúc **không xác định**. Dùng kết quả riêng hoặc công cụ load test như k6/JMeter để đo thời gian và throughput.

**Không suy ra throughput từ ba curl request**: cần đo CPU, latency p95/p99, queue depth, downstream connection pool và tổng số concurrent requests.

## 7. Kiểm thử MockMvc: asyncStarted và asyncDispatch

Với controller trả `Callable` hoặc `DeferredResult`, `MockMvc` thường trả về `MvcResult` có async processing **chưa được dispatch hoàn tất**. Chỉ assert HTTP status ngay sau `perform` có thể kiểm tra sai giai đoạn.

Quy trình đúng:

1. `perform(get(...))` và `andExpect(request().asyncStarted())`.
2. Lấy `MvcResult` và có thể đợi `getAsyncResult(timeout)`.
3. `perform(asyncDispatch(result))` để Spring MVC xử lý response sau khi có result.
4. Assert status, headers, JSON và thread prefix.

`src/test/java/com/example/mvcasync/AsyncReportControllerTest.java`:

~~~java
package com.example.mvcasync;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncReportControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void callableRunsOnConfiguredMvcExecutor()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/callable/42"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }

    @Test
    void webAsyncTaskAlsoUsesMvcWorker()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/web-async-task/7"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("7"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }

    @Test
    void deferredResultIsCompletedByApplicationExecutor()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/deferred/9"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("9"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test xác minh:

- Spring MVC thật sự bắt đầu asynchronous processing cho cả ba kiểu.
- Result được dispatch lại và xuất hiện HTTP 200 như contract.
- Business work chạy trên thread prefix của executor cấu hình, không phải controller gọi đồng bộ.
- Test không phụ thuộc cụ thể thread index `-1`, `-2`.

**Giới hạn:** `MockMvc` mô phỏng MVC dispatch trong Spring context nhưng không mở socket tới embedded Tomcat. Nó không kiểm tra Servlet `asyncSupported` flags của custom filters, gateway timeouts, disconnect, thread/connection pool exhaustion hay HTTP/2 behavior. Đối với hệ thống có ingress/proxy hoặc custom Servlet registration, hãy bổ sung `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client thật.

## 8. Đặt timeout chính xác: ba cấp độ khác nhau

Không có một timeout duy nhất đảm bảo mọi request được dừng an toàn. Hãy tách:

| Cấp độ | Ví dụ | Kiểm soát cái gì? |
|---|---|---|
| MVC async request timeout | `spring.mvc.async.request-timeout=5s` hoặc `setDefaultTimeout(5000)` | Bao lâu request được giữ trong async processing trước khi timeout |
| Per-request timeout | `WebAsyncTask(3000L, ...)`, `DeferredResult(3000L)` | Deadline riêng của endpoint đó |
| Downstream operation timeout | JDBC query timeout, HTTP client connect/read/response timeout | Bao lâu **tác vụ thật** được phép chờ backend |
| Proxy/client timeout | ingress, gateway, HTTP client | Bao lâu client/edge chịu chờ HTTP response |

### 8.1. Timeout bắt đầu từ đâu?

Theo Servlet async semantics, timeout thường được tính sau khi Servlet request thread ban đầu thoát ra và kết thúc khi async dispatch hoàn tất. Không coi nó là đồng hồ tuyệt đối tính từ đầu request đã qua mọi filter và middleware.

Một tác vụ `Callable` có thể ngồi chờ trong queue đến khi request timeout. Timeout xử lý response **không nhất thiết interrupt Callable** hoặc dừng IO underlying; worker có thể chạy muộn sau khi client đã nhận lỗi.

### 8.2. Timeout callback không phải phép màu cancellation

Ví dụ:

~~~java
WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(1000L, () -> slowCall());

task.onTimeout(() -> ResponseEntity
        .status(503)
        .body("Timed out"));
~~~

Đây là fragment với `slowCall()` giả định và có thể cần import; không phải project runnable ở mục 5. Callback giúp trả kết quả dự phòng **khi Spring nhận timeout event và response chưa commit**, chứ không đảm bảo dừng `slowCall`.

Nếu công việc có side effects quan trọng (ghi tiền, gửi email), cần thiết kế idempotency key, cancellation semantics và trạng thái tác vụ độc lập thay vì chỉ rely vào HTTP timeout.

### 8.3. Dùng 202 Accepted khi công việc vượt đời request

Nếu business task chạy hàng phút hoặc có nguy cơ client disconnect thường xuyên, đừng giữ async HTTP request mở mãi. Có thể dùng:

1. `POST /jobs` nhận yêu cầu và trả **202 Accepted** với job ID.
2. Backend queue/task service chạy công việc riêng có retry/idempotency.
3. Client gọi `GET /jobs/{id}` để lấy trạng thái hoặc subscribe event.
4. Kết quả được lưu tách khỏi HTTP connection; có TTL/cleanup và authorization.

Spring MVC async thích hợp với công việc cần **một HTTP response sau thời gian chờ ngắn/kiểm soát được**, không thay message queue/job orchestration cho tác vụ kéo dài.

## 9. Pool sizing: core, max, queue và giới hạn hệ thống

Giả sử `core=4`, `max=8`, `queue=32` trong demo. `ThreadPoolTaskExecutor` dùng `ThreadPoolExecutor` phía dưới:

1. Khi có dưới 4 core threads đang chạy, pool có thể tạo thêm core worker.
2. Khi core đã bận, task thường được đưa vào queue còn chỗ.
3. Khi queue đầy và còn room để tăng đến max, pool có thể tạo additional workers.
4. Nếu pool ở max và queue đầy, task mới có thể bị reject.

Đây là hành vi của queue-based ThreadPoolExecutor thông dụng, không phải “mọi thời điểm pool luôn chạy 8 threads”. Giá trị cấu hình phải dựa vào đo tải.

### 9.1. Công thức tư duy dung lượng

Nếu arrival rate khoảng `λ` request/giây và trung bình một task giữ worker trong `W` giây, mức công việc đồng thời trung bình xấp xỉ `L = λ × W` theo Little's Law trong điều kiện ổn định. Đây là **công cụ ước lượng**, không phải quy tắc đặt max threads tự động: distribution, p99, queue, DB pool và resource bottlenecks rất quan trọng.

Ví dụ:

- 40 task/giây × 0,1 giây/task ≈ 4 task đang chạy đồng thời.
- Nếu downstream chậm thành 1 giây/task, cùng arrival rate cần khoảng 40 task đồng thời để không tích queue.
- Bật 40 threads chưa chắc giúp nếu DB connection pool chỉ có 10 connections hoặc CPU đang bão hòa.

Khi arrival rate vượt service capacity trong thời gian dài, queue sẽ tăng cho đến khi hết giới hạn. Đừng chữa bằng queue vô hạn; cần backpressure, load shedding, retry có jitter và tối ưu downstream.

### 9.2. Tách workload và bảo vệ tài nguyên

Nên cân nhắc tách executor nếu:

- Một API có blocking operation rất chậm, có nguy cơ chiếm toàn pool.
- Một nhóm task cần thread context hoặc priority riêng.
- Streaming/file downloads dài hạn cạnh tranh với Callable nhanh.
- Có khối lượng lớn `@Async` business jobs hoặc background tasks.

Dù tách pool, phải có tổng ngân sách threads, DB connections, memory và network. Nhiều executor không tự làm tài nguyên vật lý tăng.

### 9.3. Theo dõi tại runtime

Với `ThreadPoolTaskExecutor`, có thể quan sát:

- `getActiveCount()`: số worker đang thực thi.
- `getPoolSize()` và `getCorePoolSize()`.
- `getQueueSize()`: số task đang chờ.
- Tỷ lệ rejected submissions, HTTP 503/504, async timeouts.
- Request latency p50/p95/p99 và queue wait time.
- Downstream pool saturation/DB slow queries.

Ví dụ fragment dành cho health/metrics nội bộ:

~~~java
ThreadPoolTaskExecutor executor = ...;

int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queued = executor.getQueueSize();
~~~

Đoạn này là **fragment**, `executor` là Spring bean đã inject; không phải class độc lập. Không expose toàn bộ metrics hoặc stacktraces không bảo vệ ra internet. Micrometer/Actuator có thể hỗ trợ dashboard khi được cấu hình.

## 10. @Async khác Servlet MVC asynchronous request

Giả sử service có:

~~~java
@Async
public CompletableFuture<String> calculate() {
    return CompletableFuture.completedFuture("value");
}
~~~

`@Async` chỉ có hiệu lực khi Spring's async method interception được kích hoạt (thường `@EnableAsync`), invocation đi qua Spring proxy, và method/bean phù hợp. Self-invocation hoặc method không proxied có thể không được dispatch sang executor.

Trong khi đó:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "value";
}
~~~

Spring MVC nhận `Callable` return value và tự điều phối trong Servlet async support; **không cần `@EnableAsync`**.

Một method có thể dùng cả hai mô hình, nhưng không nên vô tình tạo **hai lần submit vào hai executor** rồi mất khả năng quan sát/timeout. `CompletableFuture.supplyAsync(...)` nếu không chỉ định executor thường chạy trên `ForkJoinPool.commonPool()`, **không tự dùng `applicationTaskExecutor`**.

Ví dụ đặt executor rõ ràng:

~~~java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> "value", applicationTaskExecutor);
~~~

Đây là fragment có biến `applicationTaskExecutor` trong scope. Khi controller trả `CompletableFuture`, Spring MVC có thể adapter thành async result, nhưng **chính code tạo future** phải quyết định executor của công việc.

## 11. StreamingResponseBody, SseEmitter và reactive return types

### 11.1. StreamingResponseBody

`StreamingResponseBody` cho phép code ghi trực tiếp vào `OutputStream` của response sau khi controller trả về, hữu ích với download lớn. Servlet output writes vẫn có thể **blocking**, nên cần chọn executor và HTTP timeouts phù hợp.

~~~java
@GetMapping("/sample-download")
public StreamingResponseBody download() {
    return outputStream -> {
        outputStream.write("demo".getBytes(
                StandardCharsets.UTF_8));
        outputStream.flush();
    };
}
~~~

Đây là method fragment trong controller, cần imports. Với download thực, không đọc toàn bộ file lớn vào heap; stream từng chunk có giới hạn, quản lý disconnect và authorization.

### 11.2. ResponseBodyEmitter và SseEmitter

`ResponseBodyEmitter` có thể được hoàn tất từ một event callback; `SseEmitter` dùng để gửi SSE. Chúng không đồng nghĩa một Callable được submit vào executor. Application code vẫn phải điều phối việc tạo event, kiểm tra connection state và cleanup emitter.

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(30_000L);
    // Đăng ký emitter với một event source do app quản lý.
    return emitter;
}
~~~

Đây là fragment minh họa, **không chạy thành dịch vụ phát sự kiện hoàn chỉnh** vì chưa có event source hoặc cleanup. Với streaming, write có thể block, client disconnect có thể chỉ được phát hiện khi ghi; cần heartbeat khi thiết kế SSE lâu dài.

### 11.3. Reactive types trong Spring MVC

Spring MVC có thể nhận `Mono<T>`, `Flux<T>` hoặc `CompletionStage<T>` trong một số điều kiện bằng adapter phù hợp. Nhưng đây vẫn là **Servlet stack**, không tự đổi toàn bộ request/response I/O sang Reactor Netty non-blocking như WebFlux. Khi ghi streaming reactive values ra Servlet response, Spring MVC có thể dùng executor cho blocking writes.

**Đừng trộn** Spring MVC `DispatcherServlet` với WebFlux `DispatcherHandler` hoặc mang configuration `WebFluxConfigurer` vào bài toán MVC chỉ vì có từ “async”.

## 12. Servlet asyncSupported và Filter dispatchers

Async MVC cần Servlet container cho phép xử lý bất đồng bộ. Với **Spring Boot MVC mặc định**, DispatcherServlet registration thường đã được cấu hình phù hợp.

Tuy nhiên, custom Servlet/Filter registration có thể phá điều kiện:

- `ServletRegistrationBean` hoặc `FilterRegistrationBean` có `asyncSupported=false`.
- Một filter trong chain không cho phép async mode.
- Filter mapping chỉ xử lý `REQUEST` trong khi logic cần chạy cả lượt `ASYNC` dispatch.
- Filter tự assume mỗi HTTP request chỉ đi qua chain một lần.

Về Servlet API:

~~~text
DispatcherType.REQUEST  -> lượt đầu vào controller
DispatcherType.ASYNC    -> lượt dispatch khi async result đã sẵn sàng
~~~

Với custom `FilterRegistrationBean`, có thể phải đặt `setAsyncSupported(true)` và thêm `DispatcherType.ASYNC` vào dispatcher types **khi filter cần tham gia async dispatch**. Nếu filter chỉ cần xử lý request đầu tiên, không mặc định bật logic lặp lại trên async dispatch gây double logging, double response wrapping hoặc double authentication side effects.

Ví dụ fragment đăng ký filter:

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
~~~

`registration` là một `FilterRegistrationBean<?>` giả định, không phải file runnable. Khi sử dụng, phải biết lifecycle của filter và cấu hình Spring Security vì một số filter tự quyết định có chạy trong async dispatch hay không.

Nếu gặp lỗi như `IllegalStateException: Async support must be enabled on a servlet and for all filters involved`, hãy kiểm tra **Servlet/Filter registrations** trước khi thay thread pool.

## 13. Context propagation: ThreadLocal không tự di chuyển sang worker

Một lỗi khó phát hiện: Servlet thread ban đầu có:

- `SecurityContextHolder` chứa principal.
- `MDC` chứa correlation ID.
- `RequestContextHolder` chứa request attributes.
- `LocaleContextHolder` chứa locale.

Khi `Callable` chạy trên một worker thread khác, **không được mặc định** các `ThreadLocal` trên còn giữ nguyên giá trị. Một pool còn tái sử dụng worker nên truyền/cất context sai cách có nguy cơ leak thông tin qua requests.

Giải pháp tùy nhu cầu:

1. Chuyển **những dữ liệu bất biến cần thiết** thành tham số rõ ràng vào task, ví dụ user ID đã xác thực, locale, request correlation ID.
2. Khi cần security context, dùng các wrapper/strategy chính thức như `DelegatingSecurityContextAsyncTaskExecutor` phù hợp kiến trúc Spring Security và bảo đảm lifecycle được quản lý.
3. Với MDC/trace/locale, xem xét Spring `TaskDecorator` và Micrometer Context Propagation với `ContextSnapshot`/`ThreadLocalAccessor` đã đăng ký phù hợp.
4. Task decorator phải capture ở **thời điểm submit** và reset/restore ở **thời điểm thực thi**, tránh rò rỉ dữ liệu thread-local khi worker tái sử dụng.
5. Async response re-dispatch có thể chạy trên Servlet worker khác với cả initial thread lẫn async worker.

Không copy nguyên `HttpServletRequest` hoặc ORM persistence context sang background task dài hạn mà không nắm lifecycle; request có thể đã timeout/completed trước khi worker dùng nó.

## 14. Exception, rejection và timeout trong MVC async

### 14.1. Callable ném exception

Nếu `Callable#call()` ném exception, Spring MVC có thể đưa exception vào async result rồi giải quyết bằng `@ExceptionHandler`/`@RestControllerAdvice` hoặc resolver khác khi dispatch trở lại. Nên viết test cho business exception thay vì catch toàn bộ và trả 200.

### 14.2. DeferredResult#setErrorResult

Với `DeferredResult`, application có thể gọi:

~~~java
deferredResult.setErrorResult(
    new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Downstream unavailable"));
~~~

Đây là fragment, không phải runnable riêng; MVC có thể xử lý exception đó trong async redispatch. `setErrorResult` sau khi request đã hoàn tất không tạo thêm response thứ hai.

### 14.3. Rejection khi queue đầy

Executor có thể ném `TaskRejectedException` khi không nhận thêm task. Với `DeferredResult` và `executor.execute(...)` trong controller, rejection có thể xảy ra **ngay tại lúc submit**, trước khi method trả DeferredResult.

- Không swallow rejection rồi để request đợi vô hạn.
- Có thể ánh xạ thành 503 Service Unavailable/429 Too Many Requests theo hợp đồng (và thêm Retry-After khi đúng).
- Không trả 200 giả cho request chưa xử lý.
- Có thể kết hợp rate limit/bulkhead/circuit breaker ở biên ứng dụng.
- Nếu rejection xảy ra sau khi response commit hoặc bên ngoài MVC resolver, cần xử lý tương ứng tại nguồn.

### 14.4. Timeout chưa chắc hủy công việc

Timeout request không đồng nghĩa thread/interruption đã được gửi tới task. Một blocking JDBC call không có timeout riêng có thể còn bận. Nếu response đã commit (đặc biệt streaming), bạn không thể đổi status hoặc headers tùy ý.

Với side effects nhạy cảm, dùng idempotency/cancellation/compensating action và job status thay vì tưởng HTTP timeout có chức năng rollback transaction.

## 15. Spring MVC async so với Spring WebFlux

| Khía cạnh | MVC async trên Servlet | WebFlux reactive |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| HTTP server mặc định Boot | Embedded Tomcat | Reactor Netty |
| API tiêu biểu | `Callable`, `WebAsyncTask`, `DeferredResult` | `Mono`, `Flux`, reactive chain |
| Giao thức underlying | Servlet async dispatch, Servlet output có thể blocking | Non-blocking I/O khi sử dụng reactor runtime đúng |
| Executor đối với blocking work | `AsyncTaskExecutor` / application-managed pools | Scheduler hoặc bounded elastic cho blocking work khi bất khả kháng |
| Cấu hình web | `WebMvcConfigurer#configureAsyncSupport` | `WebFluxConfigurer` và reactive configuration |
| Servlet Filter | Có | Không với Reactor Netty; dùng `WebFilter` |
| Thread-per-blocking-task | Có thể có | Nên tránh blocking event loop; offload khi cần |

**Đừng thêm WebFlux starter chỉ để trả `Callable` từ MVC**. Tương tự, việc controller Spring MVC trả `Mono` không có nghĩa app biến thành WebFlux server. Nếu project có cả Web starter và WebFlux starter, Spring Boot thường chọn **Servlet MVC** khi auto-detect.

MVC async hữu ích khi muốn giữ stack Servlet/JDBC/Servlet security hiện có mà giảm thời gian chiếm **initial request thread**. WebFlux phù hợp với end-to-end reactive/nonblocking pipeline nhưng đòi hỏi mô hình lập trình và dependency tương thích.

## 16. Chẩn đoán lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `Callable` chạy trên thread không như mong đợi | Executor MVC chưa đúng bean name hoặc chưa `setTaskExecutor` | Kiểm tra `applicationTaskExecutor`/`WebMvcConfigurer`/thread prefix |
| Có `@Bean("taskExecutor")` nhưng MVC không dùng | Nhầm `@Async` và MVC executor | Đăng ký đúng `applicationTaskExecutor` kiểu `AsyncTaskExecutor` |
| `spring.task.execution.pool.*` không đổi pool size | Đang dùng custom bean thay vì Boot auto-config | Đọc cách bean được tạo, cấu hình bean thủ công hoặc bỏ custom |
| Pool max-size không phát huy | Queue unbounded | Dùng bounded `queue-capacity` và load test |
| HTTP 503 hoặc task rejected | Worker/queue đầy, shutdown hoặc downstream chậm | Đo active/queued/rejected, tăng throughput hoặc load shedding |
| HTTP request timeout nhưng task vẫn chạy | Async timeout không cancel blocking call | Đặt downstream timeout và cancellation strategy |
| `DeferredResult` không bao giờ hoàn tất | Không gọi `setResult/setErrorResult`, event bị mất | Có timeout callback, cleanup và observable state |
| IllegalStateException async not supported | Custom filter/servlet `asyncSupported=false` | Kiểm tra registrations, dispatcher types |
| SecurityContext/MDC bị mất trên worker | ThreadLocal không tự được propagate | TaskDecorator/security context wrappers, explicit context |
| Request log xuất hiện hai lượt | Initial REQUEST + ASYNC redispatch | Log theo request ID và dispatcher type; tránh double-side-effects |
| `CompletableFuture` chạy common pool | Dùng `supplyAsync` không truyền Executor | Truyền executor phù hợp |
| Streaming client disconnect không được biết ngay | Servlet có thể phát hiện khi write lỗi | Heartbeat/cleanup, không dựa vào preemptive disconnect detection |
| Ứng dụng thêm `@EnableWebMvc` và mất Boot defaults | Overriding Boot MVC auto config | Gỡ annotation không cần thiết, dùng WebMvcConfigurer |
| Test nhận response rỗng | Quên `asyncDispatch(result)` trong MockMvc | Test `asyncStarted`, đợi result, asyncDispatch rồi assert |
| Vượt deadline ở gateway dù MVC chưa timeout | Proxy/client timeout ngắn hơn MVC | Đồng bộ ngân sách timeout end-to-end |
| Nhiều HTTP async requests giữ connection lâu | Async giải phóng thread nhưng không giải phóng socket/resources | Giới hạn concurrent requests, backpressure và timeout |

## 17. Checklist trước khi triển khai

- [ ] Đã xác định app dùng **Spring MVC Servlet**, không nhầm với WebFlux.
- [ ] Biết chính xác các endpoints trả `Callable`, `WebAsyncTask`, `DeferredResult` hoặc stream.
- [ ] Có `AsyncTaskExecutor` được MVC thực sự sử dụng, không chỉ một bean `Executor` bất kỳ.
- [ ] Nếu dùng Boot auto-config, properties `spring.task.execution.pool.*` có tác dụng theo version hiện tại.
- [ ] Nếu có custom executor, cấu hình `@Bean("applicationTaskExecutor")` đúng kiểu và lifecycle.
- [ ] Đã đặt core/max/queue bounded theo tải, không copy số cấu hình demo vào production.
- [ ] Đã đặt MVC/per-request timeout cùng downstream/network/client deadlines.
- [ ] Có chính sách rejection và HTTP error contract, không giữ request treo.
- [ ] Không coi timeout là cancellation tự động; có cleanup/interrupt/idempotency khi cần.
- [ ] Servlet/Filter registrations hỗ trợ async và `ASYNC` redispatch đúng phạm vi.
- [ ] Có chính sách context propagation cho security, tracing và request-scoped data.
- [ ] Phân biệt `@Async` executor với MVC async worker; tránh dùng common pool ngẫu nhiên.
- [ ] Có metrics active threads, queued tasks, rejections, timeout và latency p95/p99.
- [ ] Có MockMvc tests với `request().asyncStarted()` và `asyncDispatch(result)`.
- [ ] Có HTTP integration/load tests trên embedded servlet server và ingress production tương tự.
- [ ] Streaming/file download có giới hạn I/O, xử lý disconnect và backpressure phù hợp.

## Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `WebAsyncTask`, `DeferredResult`, streaming, Servlet async dispatch, timeout và cấu hình.
- [Spring Framework 6.2 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): `setTaskExecutor`, `setDefaultTimeout`, callable/deferred interceptors.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, auto-configuration, nhiều executors và `spring.task.execution.mode=force`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.task.execution.*`, `spring.mvc.async.request-timeout` và `spring.threads.virtual.enabled`.
- [Spring Framework 6.2 — MVC Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html): `WebMvcConfigurer` và các điểm mở rộng Servlet MVC.
- [Spring Framework 6.2 — Spring MVC vs WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/overview.html): mô hình Servlet async so với nonblocking/reactive stack.

**Kết luận:** Cấu hình `AsyncTaskExecutor` quyết định **nơi và cách** Spring MVC chạy các tác vụ `Callable`/`WebAsyncTask` và hỗ trợ một số async writes. Spring Boot 3.5 có thể tự cấu hình `applicationTaskExecutor`, hoặc bạn tự khai báo bean đúng tên/kiểu và dùng `WebMvcConfigurer#configureAsyncSupport`. Riêng `DeferredResult` không tự sinh công việc trên executor: ứng dụng phải cung cấp kết quả từ callback hoặc pool của mình. Pool bounded, timeout end-to-end, context propagation, rejection handling và tests `asyncDispatch` mới làm cấu hình MVC async vững chắc.
