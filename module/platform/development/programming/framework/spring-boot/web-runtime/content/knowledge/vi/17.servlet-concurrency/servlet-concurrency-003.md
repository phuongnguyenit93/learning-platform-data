# Callable, DeferredResult và WebAsyncTask trong Spring MVC

## 1. Vì sao Spring MVC có xử lý HTTP bất đồng bộ?

Spring MVC chạy trên Servlet stack: request được một thread của Servlet container nhận, đi qua Filter chain và DispatcherServlet rồi đến controller. Với endpoint đồng bộ, thread xử lý request thường ở lại cho đến khi controller trả kết quả và response hoàn tất. Nếu controller phải chờ một công việc lâu, chẳng hạn gọi dịch vụ ngoài, xử lý báo cáo hoặc chờ một sự kiện, thread này có thể bị giữ trong thời gian chờ.

Servlet 3.0+ có cơ chế **asynchronous request processing**. Spring MVC tích hợp cơ chế đó thông qua các kiểu trả về như Callable, DeferredResult và WebAsyncTask. Khi controller trả một trong các kiểu này, Spring MVC có thể bắt đầu chế độ async của Servlet request, để thread xử lý lượt request đầu tiên thoát khỏi Filter/Servlet chain mà **HTTP response vẫn được giữ mở**. Khi kết quả có sẵn, framework thực hiện một lần **ASYNC dispatch** để hoàn tất response.

~~~text
Client
  |
  v
Servlet container thread #1
  |
  v
Filters -> DispatcherServlet -> Controller
                                   |
                                   +-- trả Callable / DeferredResult / WebAsyncTask
  |
  v
request.startAsync() do hạ tầng Spring MVC quản lý
  |
  +--> thread container #1 trở về pool, response vẫn mở
  |
  +--> Công việc chạy ở worker thread hoặc hoàn tất do event ngoài
  |
  v
Kết quả có sẵn -> ASYNC dispatch
  |
  v
Servlet container thread #2 (có thể là thread khác)
  |
  v
DispatcherServlet hoàn tất kết quả, serialize body, ghi HTTP response
~~~

Thread #1 và #2 trong sơ đồ không nhất thiết là hai thread khác nhau; Servlet container tự phân phối. Điểm quan trọng là **thread không phải chờ kết quả trong toàn bộ thời gian công việc đang chạy**.

**Không nhầm:** bất đồng bộ ở tầng request không tự biến JDBC, RestTemplate, Thread.sleep hoặc SDK blocking thành I/O non-blocking. Với Callable, công việc vẫn có thể chiếm một thread của executor. Giải phóng một Servlet thread không có nghĩa mọi tài nguyên khác đều được giải phóng.

Bài này dùng **Spring Boot 3.5.x, Spring Framework 6.2.x và Java 17+** làm mốc. Các ví dụ thuộc **Spring MVC/Servlet**, không phải WebFlux. Trong Spring Boot 3.x, Servlet API dùng package jakarta.servlet.

## 2. So sánh nhanh ba kiểu trả về

| Tiêu chí | Callable<T> | DeferredResult<T> | WebAsyncTask<T> |
|---|---|---|---|
| Ai tính kết quả? | Spring MVC gửi Callable đến AsyncTaskExecutor | Ứng dụng hoặc sự kiện ngoài tự gọi setResult / setErrorResult | Spring MVC chạy Callable được WebAsyncTask bọc |
| Hình thức trả về | Một hàm không tham số, trả T | Đối tượng giữ trạng thái kết quả sẽ được điền sau | Holder cho Callable, timeout và executor tùy chọn |
| Dùng khi | Đã có một tác vụ có thể viết thành Callable | Kết quả tới từ event, message, callback hoặc nguồn không do controller chủ động chạy | Muốn hành vi Callable nhưng cần timeout hoặc executor riêng cho request |
| Thread xử lý | Worker executor | Tùy nguồn sự kiện: message listener, scheduler, worker, callback | Worker executor mặc định hoặc riêng |
| Hoàn thành | return T hoặc throw exception trong Callable | setResult(T) hoặc setErrorResult(Object) | return T, exception hoặc callback timeout/error |
| Timeout riêng | Dùng WebAsyncTask để cấu hình thuận tiện | Constructor timeout và onTimeout | Constructor timeout và onTimeout |
| Callback lifecycle | Có thể dùng CallableProcessingInterceptor | onTimeout, onError, onCompletion | onTimeout, onError, onCompletion |
| Có thể phục vụ kết quả HTTP thông thường? | Có | Có | Có |

Cả ba đều phù hợp với **một kết quả cuối**. Nếu muốn liên tục gửi nhiều giá trị hoặc server-sent events (SSE), Spring MVC còn có ResponseBodyEmitter và SseEmitter; đó là bài toán streaming khác.

Các kiểu này là **return type của controller**. Đừng dùng chúng như một giải pháp thay thế mọi TaskExecutor, queue, transaction, retry hoặc cơ chế quản lý dữ liệu nghiệp vụ.

## 3. Vòng đời async theo Servlet và Spring MVC

Với Callable hoặc DeferredResult, các bước thường là:

1. Servlet container chuyển request vào các Filters và DispatcherServlet.
2. DispatcherServlet chọn controller; controller trả một đối tượng đại diện cho kết quả tương lai, không trả body hoàn chỉnh ngay.
3. Spring MVC gọi Servlet request.startAsync() thông qua hạ tầng của nó và đăng ký xử lý bất đồng bộ.
4. Thread của dispatch ban đầu thoát khỏi Filter/Servlet chain; client vẫn chờ một HTTP response.
5. Với Callable/WebAsyncTask, framework đưa công việc vào AsyncTaskExecutor. Với DeferredResult, ứng dụng chờ nguồn bên ngoài tự hoàn tất.
6. Khi kết quả hoặc exception có sẵn, Spring MVC yêu cầu Servlet container ASYNC dispatch.
7. DispatcherServlet chạy lại trong một dispatch mới và xử lý **kết quả đã có**, không gọi lại controller method để tạo một tác vụ mới.
8. MVC tiếp tục xử lý return value, message converters, exception resolvers và gửi response.

Spring Framework mô tả cơ chế này trong mục [Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html).

### Những điều không nên suy luận

- HTTP connection **vẫn có thể tồn tại** trong lúc chờ kết quả; async không biến request thành fire-and-forget.
- Request vẫn tiêu tốn tài nguyên như connection, timeout state, một số context và có thể cả bộ nhớ chứa payload.
- Async dispatch sử dụng một Servlet thread để hoàn tất response.
- Nếu công việc chặn một worker thread thì vẫn phải sizing worker pool và downstream connection pool.
- Timeout HTTP request không nhất thiết tự ngắt được JDBC call hoặc thao tác I/O đang treo.
- Async processing không làm thay đổi mặc định hợp đồng của transaction hoặc dữ liệu trong ThreadLocal.

## 4. Callable<T>: Spring MVC tự thực thi công việc

java.util.concurrent.Callable<T> là functional interface có phương thức call() trả về T hoặc ném Exception. Khi controller Spring MVC trả Callable, framework sẽ chạy Callable trên AsyncTaskExecutor được cấu hình cho MVC async support.

Ví dụ controller tối giản:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "result from worker";
}
~~~

Khi controller trả lambda, chuỗi chưa được trả về HTTP ngay. Spring MVC chuyển request sang async mode, gửi lambda tới executor và chờ kết quả. Sau khi Callable hoàn thành, Spring MVC dispatch lại để xử lý giá trị trả về.

Có thể trả Callable<ResponseEntity<MyDto>>, Callable<String>, Callable<ModelAndView> hoặc một return value mà Spring MVC hỗ trợ. Nếu Callable throw exception, Spring MVC dispatch lại và đưa exception qua cơ chế HandlerExceptionResolver/@ExceptionHandler phù hợp.

### Lợi ích và giới hạn

Callable thích hợp khi controller **biết rõ công việc cần làm**, và công việc có thể gói trong một hàm duy nhất. Ví dụ tính báo cáo nhỏ hoặc gọi một dependency blocking qua executor có giới hạn.

Tuy nhiên, nếu công việc mất 10 giây do block, một worker thread vẫn bận 10 giây. Nếu pool có 8 worker, tối đa 8 công việc kiểu đó chạy đồng thời, trừ các cơ chế concurrency khác. Nếu queue dài, request có thể chờ lâu và timeout trước khi tác vụ bắt đầu.

Không tự gọi callable.call() ngay trong controller rồi bọc kết quả để trả về: làm như vậy vẫn chạy đồng bộ trên Servlet thread ban đầu và mất mục đích của async return type.

## 5. DeferredResult<T>: kết quả được hoàn tất từ một nơi khác

DeferredResult<T> không yêu cầu controller cung cấp Callable. Controller tạo một đối tượng đại diện cho kết quả tương lai, đăng ký callback cần thiết, sau đó trả DeferredResult cho Spring MVC. Một thành phần khác hoàn tất kết quả bằng:

~~~java
deferred.setResult(value);
~~~

Hoặc gửi exception để Spring MVC xử lý:

~~~java
deferred.setErrorResult(exception);
~~~

Ví dụ ý tưởng:

~~~java
@GetMapping("/wait-for-event")
public DeferredResult<String> waitForEvent() {
    DeferredResult<String> deferred = new DeferredResult<>(5000L);

    eventRegistry.register(deferred);
    deferred.onCompletion(() -> eventRegistry.remove(deferred));

    return deferred;
}

// Trong message listener hoặc callback của tác vụ khác:
deferred.setResult("event received");
~~~

Đoạn trên là **pseudocode minh họa**, cần eventRegistry và cơ chế nhận event do ứng dụng định nghĩa. Ví dụ hoàn chỉnh không phụ thuộc eventRegistry nằm ở phần 9.

### Khi nào DeferredResult hợp hơn Callable?

- Một message từ RabbitMQ/Kafka hoặc webhook báo đã hoàn thành công việc và controller không sở hữu thread tính kết quả.
- Một tiến trình khác gửi callback theo correlation ID.
- Server cần **long polling** để trả một kết quả duy nhất khi có sự kiện, trong giới hạn timeout.
- Một thư viện đã có callback API và bạn muốn chuyển callback đó thành HTTP response.

Nếu controller chỉ muốn chạy một hàm trên executor rồi trả kết quả, Callable hoặc WebAsyncTask thường đơn giản hơn. Đừng dùng DeferredResult rồi tự tạo một Thread mới cho từng request mà không có executor có giới hạn.

### setResult() và setErrorResult() chỉ có một kết quả thắng

DeferredResult cho phép thiết lập kết quả tối đa một lần thành công. setResult/setErrorResult trả boolean để báo có chấp nhận kết quả hay không. Nếu timeout hoặc completion đã xảy ra, một callback tới muộn có thể không còn hiệu lực.

~~~java
boolean accepted = deferred.setResult(response);
if (!accepted) {
    // Request đã có kết quả hoặc hết vòng đời xử lý.
}
~~~

Không cố gửi hai HTTP responses cho cùng một request. Nếu dùng registry giữ các DeferredResult đang chờ, phải xóa chúng khi completed, timeout hoặc error để tránh memory leak.

## 6. WebAsyncTask<T>: Callable có timeout và executor tùy chỉnh

WebAsyncTask<V> trong package org.springframework.web.context.request.async là holder cho Callable<V>, timeout và executor tùy chọn.

Ví dụ:

~~~java
@GetMapping("/task")
public WebAsyncTask<String> task() {
    WebAsyncTask<String> result =
            new WebAsyncTask<>(3000L,
                    () -> "result from callable");

    result.onTimeout(() -> "fallback after timeout");
    result.onError(() -> "fallback after async error");
    result.onCompletion(() -> {
        // Dọn state, ghi metric hoặc log hoàn tất.
    });

    return result;
}
~~~

WebAsyncTask có thể chọn executor riêng cho request:

~~~java
new WebAsyncTask<>(3000L, chosenExecutor, callable);
~~~

Ở đây chosenExecutor phải là AsyncTaskExecutor phù hợp và callable là Callable<V>. Ví dụ này chỉ minh họa constructor, chưa khai báo hai biến đó.

Các callback:

- onTimeout(Callable<V>): nhận sự kiện timeout trước khi Callable có kết quả. Nó có thể trả giá trị fallback hoặc exception. Callback chạy trên container thread và phải **trả về nhanh, không blocking**.
- onError(Callable<V>): dành cho lỗi trong xử lý async tại tầng container trước khi Callable hoàn tất; **không nên giả định nó thay thế mọi @ExceptionHandler** cho exception của Callable.
- onCompletion(Runnable): được gọi khi async request hoàn tất, kể cả do timeout hoặc lỗi mạng; thích hợp dọn đăng ký/metric. Tránh ghi response một lần nữa ở đây.

WebAsyncTask không biến tác vụ thành fire-and-forget. Nó vẫn là một request HTTP có timeout và lifecycle tương ứng.

## 7. Timeout của request khác timeout của công việc

Spring MVC có nhiều tầng timeout:

| Tầng | Ví dụ | Ý nghĩa |
|---|---|---|
| Servlet async timeout | spring.mvc.async.request-timeout hoặc AsyncSupportConfigurer.setDefaultTimeout | Bao lâu request async được phép chờ theo Servlet lifecycle |
| Per-request timeout | DeferredResult<>(5000L), WebAsyncTask<>(3000L, ...) | Giới hạn riêng cho request được tạo |
| Outbound HTTP client | connection/read/response timeout của WebClient, RestClient hoặc thư viện tương ứng | Bao lâu client chờ downstream |
| Database/query timeout | Driver/query/transaction-specific | Giới hạn truy vấn, lock hoặc transaction |
| Reverse proxy timeout | Nginx/Ingress/Gateway timeouts | Bao lâu proxy chờ upstream HTTP response |
| Client timeout | Browser, mobile client, curl | Bao lâu caller chờ |
| Executor saturation | Worker/queue capacity | Khả năng nhận và thực hiện công việc; không phải timeout HTTP |

Trong Spring Boot 3.5, có thể cấu hình:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 10s
~~~

Giá trị này là **default async request timeout** của MVC khi Boot áp dụng cấu hình đó. Nếu không đặt, default có thể phụ thuộc Servlet container. Không khẳng định mọi Boot/Tomcat/Jetty version đều mặc định 10s hoặc 30s.

Có thể cấu hình bằng Java:

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setDefaultTimeout(10_000L);
}
~~~

Cách này là lựa chọn thay cho cấu hình properties nếu chỉ cần một timeout. Trong project mẫu bên dưới dùng **Java config** để minh họa cả executor, nên không thêm một YAML khác có giá trị mâu thuẫn.

**Quan trọng:** setDefaultTimeout tính theo milliseconds. Theo Javadoc Spring Framework, thời gian Servlet async thường bắt đầu sau khi main request thread thoát và kết thúc khi request được dispatch lại. Nó không đo toàn bộ journey từ DNS, TLS, gateway đến client.

Timeout request **không mặc nhiên cancel công việc đang chạy**. Nếu worker đang gọi external service mà không đặt timeout riêng, task có thể tiếp tục sau khi client đã nhận timeout hoặc kết nối bị đóng. Thiết kế production phải dùng timeout/cancellation ở cấp task hoặc downstream và cleanup tài nguyên.

### Status code khi timeout

Spring MVC có thể xử lý AsyncRequestTimeoutException bằng response 503 nếu không có callback riêng và chưa ghi response. Nhưng nếu controller dùng WebAsyncTask.onTimeout hoặc DeferredResult.onTimeout để trả fallback, status/body tùy giá trị bạn chọn. Proxy có thể tự trả 504 khi hết thời gian chờ upstream; đó không phải bằng chứng Spring MVC đã tự chọn HTTP 504.

Đừng dựa vào chỉ một status để suy ra nơi xảy ra timeout. Xem log, request ID, executor metrics, gateway metrics và những callback đã chạy.

## 8. Cấu hình AsyncTaskExecutor cho Spring MVC trong production

Spring MVC dùng AsyncTaskExecutor để chạy Callable và WebAsyncTask nếu không có executor riêng. Tài liệu Spring Framework khuyến cáo cấu hình executor phù hợp cho production under load.

Spring Boot 3.5 có **task execution auto-configuration**: khi không bị custom Executor bean làm thay đổi điều kiện, Boot có thể tạo AsyncTaskExecutor. Với Java 21+ khi bật virtual threads, loại executor có thể khác so với Java 17 và thread pool truyền thống. Boot cũng có quy tắc về bean tên applicationTaskExecutor cho MVC integration.

**Không chỉ nhìn thấy một Executor bean rồi kết luận MVC chắc chắn đang dùng nó.** Để lựa chọn rõ ràng, có thể override WebMvcConfigurer.configureAsyncSupport và gọi setTaskExecutor với bean được chỉ định. Ví dụ dự án tiếp theo làm đúng như vậy.

### Giới hạn tài nguyên

Một ThreadPoolTaskExecutor có thể điều chỉnh:

- corePoolSize: số worker cơ bản.
- maxPoolSize: tối đa số worker khi cần và queue cho phép.
- queueCapacity: bao nhiêu tác vụ chờ.
- threadNamePrefix: giúp phân biệt thread khi debug.
- rejection policy: hành vi khi pool và queue hết chỗ.
- shutdown policy: cách dừng và đợi task khi deploy.

**Điểm dễ nhầm:** với ThreadPoolExecutor phổ biến, nếu queue là unbounded, pool có thể hiếm khi phát triển vượt corePoolSize; maxPoolSize không phải đảm bảo luôn có thêm worker. Cần thiết kế capacity cho tốc độ đến, thời gian xử lý, timeout và giới hạn nguồn downstream.

CallerRunsPolicy khi executor đầy có thể chạy công việc ngay trên thread submit của request, làm mất mục tiêu giải phóng Servlet thread. AbortPolicy hoặc cách từ chối có kiểm soát sẽ dễ áp dụng backpressure hơn, nhưng phải map task rejection thành response phù hợp (ví dụ 503) khi hệ thống quá tải.

Trong MVC async, bộ nhớ và số pending HTTP requests cũng tăng khi mỗi request chờ kết quả. Async không biến server thành không giới hạn concurrency.

## 9. Ví dụ hoàn chỉnh Spring Boot 3.5.x và Java 17+

Ví dụ tạo ba endpoint trả cùng cấu trúc JSON, giúp kiểm thử rõ sự khác biệt cơ chế.

### 9.1. Dependencies và cấu trúc dự án

Tạo Maven project dùng Spring Boot 3.5.x, Java 17+, có parent hoặc BOM Spring Boot. Các dependencies:

~~~xml
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
~~~

Cấu trúc:

~~~text
src/main/java/example/asyncmvc/
  AsyncMvcApplication.java
  AsyncMvcConfig.java
  AsyncDemoController.java
src/test/java/example/asyncmvc/
  AsyncDemoControllerTest.java
~~~

Spring Boot starter-web thường đưa embedded Tomcat và Spring MVC vào classpath; ví dụ không cần spring-boot-starter-webflux.

### 9.2. Ứng dụng chính

Tệp src/main/java/example/asyncmvc/AsyncMvcApplication.java:

~~~java
package example.asyncmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncMvcApplication.class, args);
    }
}
~~~

Lớp main nằm cùng package hoặc package cha của các cấu hình/controller, giúp component scan tìm đúng bean.

### 9.3. Cấu hình executor có giới hạn và MVC async support

Tệp src/main/java/example/asyncmvc/AsyncMvcConfig.java:

~~~java
package example.asyncmvc;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AsyncMvcConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor mvcExecutor;

    public AsyncMvcConfig(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor mvcExecutor) {
        this.mvcExecutor = mvcExecutor;
    }

    @Bean("mvcAsyncExecutor")
    public static ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("mvc-async-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcExecutor);
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

Điểm chính:

- Bean mvcAsyncExecutor là một ThreadPoolTaskExecutor. Spring quản lý initialization và destruction của bean, không cần code tạo thread thủ công cho mỗi request.
- Bean factory method là static để tránh vòng phụ thuộc khi chính configuration class cần inject executor mà nó khai báo.
- configureAsyncSupport dùng đúng executor đó để chạy Callable do Spring MVC quản lý; mặc định timeout là 10.000 ms.
- queueCapacity hữu hạn giúp tránh giữ vô hạn công việc khi tải cao.
- Code minh họa cấu hình có chủ đích; trong hệ thống thật phải benchmark và chọn kích thước pool phù hợp với CPU, I/O và downstream capacity.

Nếu dự án có nhiều Executor beans, cách tiêm @Qualifier và setTaskExecutor tường minh như trên giúp tránh chọn nhầm bean. Không gắn @EnableWebMvc chỉ để cấu hình async; WebMvcConfigurer đủ để bổ sung mà vẫn giữ Boot MVC auto-configuration.

### 9.4. Controller với đủ Callable, DeferredResult và WebAsyncTask

Tệp src/main/java/example/asyncmvc/AsyncDemoController.java:

~~~java
package example.asyncmvc;

import java.util.concurrent.Callable;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(AsyncDemoController.class);

    private final AsyncTaskExecutor executor;

    public AsyncDemoController(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public record Reply(String source, String status) {}

    @GetMapping("/callable")
    public Callable<ResponseEntity<Reply>> callable() {
        return () -> ResponseEntity.ok(
                new Reply("callable", "ok"));
    }

    @GetMapping("/deferred")
    public DeferredResult<ResponseEntity<Reply>> deferred() {
        DeferredResult<ResponseEntity<Reply>> result =
                new DeferredResult<>(5_000L);

        result.onTimeout(() -> result.setErrorResult(
                new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Result was not ready")));

        result.onError(error -> {
            log.warn("Async request error", error);
        });

        result.onCompletion(() ->
                log.debug("Deferred request completed"));

        try {
            executor.execute(() -> {
                try {
                    boolean accepted = result.setResult(
                            ResponseEntity.ok(
                                    new Reply("deferred", "ok")));
                    if (!accepted) {
                        log.debug("Deferred result arrived too late");
                    }
                } catch (RuntimeException ex) {
                    result.setErrorResult(ex);
                }
            });
        } catch (TaskRejectedException ex) {
            result.setErrorResult(
                    new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Async worker is busy", ex));
        }

        return result;
    }

    @GetMapping("/web-task")
    public WebAsyncTask<ResponseEntity<Reply>> webTask() {
        Callable<ResponseEntity<Reply>> work = () ->
                ResponseEntity.ok(
                        new Reply("webAsyncTask", "ok"));

        WebAsyncTask<ResponseEntity<Reply>> task =
                new WebAsyncTask<>(3_000L, executor, work);

        task.onTimeout(() ->
                ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("webAsyncTask", "timeout")));

        task.onError(() ->
                ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(new Reply("webAsyncTask", "error")));

        task.onCompletion(() ->
                log.debug("WebAsyncTask request completed"));

        return task;
    }
}
~~~

Điểm đáng chú ý:

- /callable: Spring MVC tự gửi Callable vào executor đã đăng ký.
- /deferred: ứng dụng gửi một task qua executor; worker gọi setResult. Mẫu này cố ý minh họa việc **ứng dụng** quyết định khi nào DeferredResult hoàn tất. Nếu chỉ cần chạy một Callable, endpoint /callable đơn giản hơn.
- /deferred có timeout riêng 5 giây, dùng onTimeout để chuyển thành ResponseStatusException HTTP 503. setResult trả false khi kết quả đến quá muộn hoặc đã được thiết lập.
- /web-task: WebAsyncTask bọc Callable, dùng executor chỉ định, timeout 3 giây, có callback timeout/error/completion.
- Không có Thread.sleep trong code chạy: các ví dụ trả kết quả nhanh, dễ test và không giả tạo một deadline không ổn định.
- Những response dạng Reply được Jackson serialize thành JSON qua starter-web.
- TaskRejectedException là tình huống pool quá tải; DeferredResult chủ động chuyển thành lỗi 503. Với Callable/WebAsyncTask, vẫn phải có chính sách xử lý rejection ở framework/API level nếu cần.

**Quan trọng:** onError của WebAsyncTask không nên coi là một catch-all thay thế mọi @ExceptionHandler. Exception do chính Callable throw thường đi qua MVC exception handling khi kết quả async được dispatch. Với hệ thống thật, nên log exception, phân loại domain errors và trả response bảo mật phù hợp.

### 9.5. Chạy ứng dụng

Trong Maven project có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Nếu chưa có cấu hình khác, embedded servlet server thường mở HTTP trên 8080. Gọi:

~~~bash
curl -i http://localhost:8080/api/async/callable
curl -i http://localhost:8080/api/async/deferred
curl -i http://localhost:8080/api/async/web-task
~~~

Khi không gặp timeout hoặc executor saturation, kết quả dự kiến là HTTP 200, Content-Type application/json và body **tương đương**:

~~~json
{"source":"callable","status":"ok"}
~~~

~~~json
{"source":"deferred","status":"ok"}
~~~

~~~json
{"source":"webAsyncTask","status":"ok"}
~~~

Đó là **body JSON kỳ vọng**, không phải toàn bộ stdout của ứng dụng. Header, log, thứ tự properties và tên thread thay đổi theo môi trường. Không hứa rằng mỗi request dùng đúng một thread có tên định sẵn; chỉ có thể kiểm tra bằng log/trace.

## 10. MockMvc: kiểm thử đúng hai giai đoạn của async request

MockMvc thường mô phỏng MVC request mà không mở một HTTP socket thật. Với async controllers, **phải có asyncDispatch** để hoàn tất xử lý trong test.

Tệp src/test/java/example/asyncmvc/AsyncDemoControllerTest.java:

~~~java
package example.asyncmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDemoControllerTest {

    @Autowired
    MockMvc mvc;

    private void assertAsyncResult(
            String path, String expectedSource) throws Exception {

        MvcResult pending = mvc.perform(get(path))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value(expectedSource))
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void callableCompletes() throws Exception {
        assertAsyncResult("/api/async/callable", "callable");
    }

    @Test
    void deferredCompletes() throws Exception {
        assertAsyncResult("/api/async/deferred", "deferred");
    }

    @Test
    void webAsyncTaskCompletes() throws Exception {
        assertAsyncResult("/api/async/web-task", "webAsyncTask");
    }
}
~~~

Vì cả ba endpoint trả về kết quả async:

1. Lượt mvc.perform(get(path)) khởi động request và xác minh request().asyncStarted().
2. MvcResult giữ trạng thái async request ban đầu.
3. asyncDispatch(pending) đợi kết quả async rồi thực hiện một lượt dispatch trong MockMvc.
4. Sau dispatch mới kiểm tra HTTP status và JSON body cuối.

Chạy:

~~~bash
./mvnw test
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd test
~~~

Nếu chỉ gọi perform(get(...)).andExpect(content().string(...)) trên lượt đầu, test có thể quan sát response chưa hoàn tất thay vì JSON cuối. Cách test này tuân theo [Spring Framework MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html).

### Kiểm thử timeout không nên dùng sleep may rủi

Không nên chỉ thêm Thread.sleep(5000) vào bài unit test rồi đặt timeout 3000 ms và hy vọng mọi máy/CI trả kết quả giống nhau. MockMvc không phải Servlet container thật, và việc mô phỏng timeout có thể khác so với server thực. Để kiểm tra timeout, exception, client disconnect và reverse proxy, sử dụng integration test chạy trên RANDOM_PORT với embedded Tomcat/Jetty thật và cơ chế đồng bộ có kiểm soát (CountDownLatch, CompletableFuture hoặc fake external service có tín hiệu rõ).

Cần có test riêng cho:

- Lỗi thrown từ Callable và việc @ControllerAdvice nhận exception.
- DeferredResult.setErrorResult và final status.
- WebAsyncTask.onTimeout fallback.
- Worker pool đầy, task rejection, load burst.
- Client ngắt kết nối và cleanup pending registry.
- Executor/DB shutdown trong deployment.

Đừng kết luận production timeout behavior chỉ từ test gọi controller method như một Java function không qua DispatcherServlet.

## 11. DeferredResult được hoàn tất bởi external event: mô hình thực tế

DeferredResult hữu ích nhất khi kết quả được gửi từ nguồn ngoài thay vì chỉ chạy một Runnable trực tiếp. Một thiết kế thường gặp:

~~~text
HTTP GET /jobs/{id}/wait
          |
          v
Controller tạo DeferredResult, đặt timeout
          |
          v
Registry.put(jobId, deferred)
          |
          v
Controller trả DeferredResult, Servlet thread được giải phóng
          |
          v
Message listener nhận JobCompleted(jobId, result)
          |
          v
Registry.remove(jobId) -> deferred.setResult(result)
          |
          v
Spring MVC ASYNC dispatch -> HTTP response
~~~

Bản phác họa API registry:

~~~java
// Snippet ý tưởng, không phải class Java độc lập:
ConcurrentMap<String, DeferredResult<ResponseEntity<JobReply>>>
        pending = new ConcurrentHashMap<>();

DeferredResult<ResponseEntity<JobReply>> result =
        new DeferredResult<>(15_000L);

DeferredResult<ResponseEntity<JobReply>> previous =
        pending.putIfAbsent(jobId, result);

if (previous != null) {
    // Chọn policy rõ: từ chối, nhiều người chờ, hoặc hủy phiên cũ.
}

result.onCompletion(() -> pending.remove(jobId, result));
~~~

Với jobId một client chờ, pending map phải quản lý đồng thời và cleanup đúng. Nếu nhiều clients có thể chờ cùng job, một map jobId -> một DeferredResult không đủ; cần collection/thread-safe registration và cleanup riêng cho từng request.

Khi message hoàn tất đến:

~~~java
DeferredResult<ResponseEntity<JobReply>> waiting =
        pending.remove(jobId);
if (waiting != null) {
    waiting.setResult(ResponseEntity.ok(jobReply));
}
~~~

Đây là các snippet giải thích kiến trúc; cần JobReply, jobId, jobReply, queue/message listener và cơ chế đồng bộ do hệ thống định nghĩa. Chúng không thay thế ví dụ chạy đầy đủ ở phần 9.

**Các race cần xử lý:**

- Event đến trước khi HTTP request đăng ký DeferredResult: nên có durable job state để client hỏi lại, không chỉ dựa vào pending map.
- Timeout vừa xảy ra thì event đến: setResult có thể trả false. Dữ liệu job nên được lưu ở storage độc lập.
- Client disconnect: onCompletion phải cleanup pending registry.
- Application restart: pending map trong RAM mất; nếu cần độ bền, lưu trạng thái job ở DB/cache/queue.
- Cùng jobId từ hai users: không trả kết quả sai người; phải kiểm tra authentication/authorization và tính sở hữu job.

Đây là lý do DeferredResult thường đi cùng correlation ID, idempotency policy và một nguồn trạng thái lâu bền.

## 12. AsyncHandlerInterceptor và vòng đời Filter khác request đồng bộ

Một HandlerInterceptor thông thường có:

- preHandle trước controller.
- postHandle sau khi handler chạy và trước rendering khi phù hợp.
- afterCompletion khi dispatch xử lý hoàn tất.

Với async controller, **lượt dispatch ban đầu** có thể không gọi postHandle và afterCompletion theo đường đồng bộ thông thường. Nếu interceptor implements AsyncHandlerInterceptor, nó có thể nhận afterConcurrentHandlingStarted khi request chuyển sang async. Lượt ASYNC dispatch về sau có thể chạy lại các bước interceptor phù hợp rồi hoàn tất response.

Ví dụ skeleton:

~~~java
public final class TimingInterceptor implements AsyncHandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        return true;
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Dispatch đầu tiên chuyển sang async;
        // không kết luận request HTTP đã kết thúc.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        // Có thể dọn request resources ở dispatch hoàn tất.
    }
}
~~~

Đoạn skeleton cần imports jakarta.servlet.http.HttpServletRequest/Response và org.springframework.web.servlet.AsyncHandlerInterceptor; không phải file Java độc lập.

Nếu interceptor ghi start time vào request attribute, đừng giả định preHandle chỉ chạy một lần cho toàn bộ HTTP exchange. Kiểm tra REQUEST/ASYNC dispatch, tránh ghi đè start time rồi làm metric sai.

### Filter asyncSupported và DispatcherType.ASYNC

Servlet async cần các Servlet và Filters liên quan khai báo asyncSupported=true. Với custom Filter registrations, phải xem cấu hình DispatcherType.REQUEST và DispatcherType.ASYNC nếu cần filter tham gia async dispatch.

Nhưng **tham gia async dispatch** và **hỗ trợ async request** không phải cùng một ý:

- asyncSupported=true cho biết Filter có thể tham gia request có asynchronous processing.
- Registration dispatcher types điều khiển Filter có được gọi trong ASYNC dispatch hay không.
- OncePerRequestFilter có default logic để tránh chạy lại trong async dispatch, tùy shouldNotFilterAsyncDispatch() và registration.

Đừng vô tình chạy logic authentication, request logging hoặc body reading hai lần chỉ vì async dispatch. Với Spring Security, cần kiểm tra filter chain trên dispatch type và cách bối cảnh bảo mật được khôi phục.

## 13. ThreadLocal, MDC, SecurityContext và transaction không tự truyền mọi nơi

Khi code đi từ Servlet thread sang executor worker thread, ThreadLocal là một điểm dễ sai. Các giá trị như MDC logging context, correlation ID, LocaleContextHolder, RequestContextHolder hoặc custom ThreadLocal không tự xuất hiện trong mọi thread khác.

Một số Spring integrations có cơ chế chuyển context nhất định. Ví dụ Spring Security có tích hợp với Callable thông qua cơ chế MVC async và WebAsyncManagerIntegrationFilter. Tuy vậy, **không coi điều đó là bảo đảm tất cả ThreadLocal/security data đều được truyền vào mọi Runnable mà ứng dụng tự submit**.

Đối với DeferredResult hoàn tất trong một message listener hoặc scheduler, context của request ban đầu có thể không còn trên thread đó. Khi cần thông tin user/correlation:

1. Trích thông tin được phép dùng từ request thành dữ liệu immutable.
2. Truyền dữ liệu một cách tường minh vào job/event.
3. Với observability/trace context, dùng TaskDecorator hoặc context propagation mechanism phù hợp.
4. Dọn MDC và custom ThreadLocal khi worker kết thúc, kể cả exception.

### Transaction và persistence

Không giả định @Transactional trên controller bao bọc toàn bộ Callable body chạy sau đó trên executor. Transaction thường gắn với thread gọi service và transaction interceptor. Nếu công việc async cần transaction:

~~~java
@Service
public class BookingService {

    @Transactional
    public Receipt createBooking(CreateBookingCommand command) {
        // Đặt nghiệp vụ và database work tại service boundary.
    }
}
~~~

Đây là skeleton cần Receipt, CreateBookingCommand và imports; trong ứng dụng thật phải đảm bảo service bean được gọi qua Spring proxy và transaction manager phù hợp.

Nên gọi service transactional từ thread đang thực hiện công việc và kiểm thử rollback/commit. Không dựa vào EntityManager, database session hay một transactional ThreadLocal được tự động kéo từ Servlet thread sang worker.

## 14. Exception từ Callable, DeferredResult và WebAsyncTask

### Callable ném exception

~~~java
@GetMapping("/failure")
public Callable<String> failure() {
    return () -> {
        throw new IllegalStateException("simulated failure");
    };
}
~~~

Spring MVC nhận exception như kết quả của quá trình xử lý async, thực hiện dispatch và chuyển qua exception handling bình thường. Nếu có @RestControllerAdvice bắt một exception phù hợp, handler có thể tạo ProblemDetail/ResponseEntity. Không trả raw exception message nhạy cảm hoặc stacktrace cho client.

### DeferredResult gửi error result

~~~java
DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(5000L);

result.setErrorResult(
        new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "external service unavailable"));
~~~

Đây là đoạn minh họa cần imports; khi framework xử lý error result trong async dispatch, ResponseStatusException có thể được chuyển thành response tương ứng.

### WebAsyncTask timeout fallback

~~~java
WebAsyncTask<String> task =
        new WebAsyncTask<>(2000L, () -> "slow result");

task.onTimeout(() -> "fallback");
~~~

Nếu timeout xảy ra trước khi tác vụ hoàn thành, callback có thể cung cấp kết quả fallback. Nhưng đừng giả định callback timeout có thể hủy thread, rollback transaction hoặc bảo đảm không có side effects. Công việc đã chạy có thể tiếp tục đến khi thực sự hoàn thành hoặc bị hủy bằng cơ chế được thiết kế.

Với onError của WebAsyncTask, có thể trả alternative value cho lỗi xảy ra trong async processing trước khi Callable hoàn tất. Đó không phải catch-all cho mọi exception trong business method; việc chọn exception handler nên dựa vào đường đi thực tế.

### Double completion

DeferredResult.setResult và setErrorResult trả boolean. Nếu callback timeout đã hoàn tất response và message listener gọi setResult sau, giá trị có thể là false. Không log một callback tới muộn như một HTTP success.

Nếu request đã bị client ngắt kết nối, cố ghi response có thể gặp IOException; với streaming có thể phát hiện trễ khi thực hiện write. Các callback completion và cleanup không nên phụ thuộc vào việc client còn đang đọc response.

## 15. Đo lường và giới hạn tải

Giả sử ứng dụng nhận 200 HTTP requests mỗi giây, mỗi task blocking mất trung bình 2 giây. Nếu không có tối ưu, số tác vụ in-flight xấp xỉ 400 theo Little's Law (giả sử trạng thái ổn định và latency đại diện). Đổi sang Callable giúp Servlet thread được giải phóng để nhận request khác, nhưng **executor vẫn phải xử lý khối lượng công việc đó**.

Với worker pool 8 và công việc blocking 2 giây, thông lượng xử lý kiểu tuần tự trên mỗi worker vào khoảng 4 requests/giây (bỏ qua overhead), thấp hơn rất nhiều tốc độ đến 200/giây. Queue sẽ lớn dần hoặc request bị từ chối, nên async không phải cách chữa quá tải nếu downstream không đủ năng lực.

Các chỉ số cần theo dõi:

- Executor active threads, queue depth, completed tasks, rejection count.
- HTTP active requests, Servlet async timeouts, p50/p95/p99 latency.
- Outbound HTTP/database latency và connection pool saturation.
- Tỷ lệ client disconnect, proxy timeout, late DeferredResult completions.
- Tỷ lệ 503/504, exception count, CPU, memory và GC.
- Tỷ lệ request đang chờ external event nếu dùng registry DeferredResult.

**Bốn giới hạn phải đi cùng nhau:** concurrency limit, queue capacity, task/dependency timeout và HTTP async timeout. Chỉ tăng timeout có thể làm tích tụ hàng nghìn request đang chờ.

Nếu muốn streaming hoặc rất nhiều thao tác I/O non-blocking end-to-end, cần so sánh thêm Spring WebFlux, reactive clients và khả năng hệ thống, không chỉ đổi return type thành Callable.

## 16. Phân biệt Servlet async, @Async và WebFlux

| Cơ chế | Phạm vi | Có thể trả HTTP response từ một request đang mở? | Điều đáng nhớ |
|---|---|---|---|
| Spring MVC Callable | HTTP controller Servlet | Có | MVC quản lý executor và ASYNC dispatch |
| Spring MVC DeferredResult | HTTP controller Servlet | Có | Ứng dụng quyết định khi nào hoàn tất kết quả |
| Spring MVC WebAsyncTask | HTTP controller Servlet | Có | Callable + timeout/executor/callback |
| Spring @Async | Phương thức Spring bean | Không tự động chỉ vì thêm annotation | Thực thi method qua task executor/proxy, không thay Servlet async contract |
| CompletableFuture | Abstraction async Java | Có thể được MVC thích ứng trong controller tùy return type support | Không tự bảo đảm non-blocking I/O |
| Spring WebFlux Mono/Flux | Reactive HTTP pipeline | Có | Hợp đồng request/response và I/O khác với Servlet MVC |

**@Async không tương đương Callable return type.** @Async trên service khiến method được thực thi qua một executor nếu được kích hoạt và gọi đúng qua Spring proxy; nó không tự chuyển HttpServletRequest sang Servlet async mode. Ngược lại, controller trả Callable có thể hoạt động không cần gắn @EnableAsync.

**MVC async không phải WebFlux.** Spring MVC vẫn dùng DispatcherServlet, Filters và Servlet async lifecycle. WebFlux dùng DispatcherHandler, reactive request/response abstractions và có thể dùng Reactor Netty. Spring MVC có thể hỗ trợ một số reactive return types khi dependency tương ứng hiện diện, nhưng đó không đồng nghĩa mọi Servlet I/O trở thành non-blocking.

## 17. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc khắc phục |
|---|---|---|
| Controller trả Callable nhưng thread pool vẫn nghẽn | Công việc blocking chiếm worker quá lâu | Đo executor queue/active, đặt downstream timeout, cân chỉnh pool |
| Request async nhận 503 khi chờ lâu | Servlet async timeout hoặc custom fallback | Xác định tầng timeout; kiểm tra callback và proxy |
| Proxy báo 504 trước server | Proxy timeout ngắn hơn server/task timeout | Căn chỉnh timeout và response policy |
| DeferredResult không bao giờ trả kết quả | Không có ai gọi setResult/setErrorResult | Kiểm tra registry/callback/timeout, luôn có fallback |
| Registry tăng bộ nhớ liên tục | Không xóa pending result sau timeout/disconnect | Cleanup trong onCompletion và error path |
| setResult trả false | Timeout/complete đã xảy ra hoặc kết quả đã được thiết lập | Xem race, không phát response lần hai |
| WebAsyncTask callback bị chậm | onTimeout/onError làm I/O blocking trên container thread | Callback trả nhanh, chuyển tác vụ nặng sang nơi khác |
| TaskRejectedException | Executor/queue đã đầy | Cấu hình pool/capacity, trả 503 có chủ đích và đo saturation |
| MVC vẫn xử lý đồng bộ dù khai báo biến Callable | Controller tự gọi call() trước khi return | Trả đối tượng Callable cho MVC, không tự thực thi |
| @Transactional không giữ trên worker | Transaction/thread context không tự propagate | Đặt @Transactional ở service boundary chạy trên worker |
| MDC, SecurityContext biến mất | ThreadLocal không tự chuyển toàn bộ | Dùng propagation phù hợp hoặc truyền metadata rõ ràng |
| Filter không chạy trong ASYNC dispatch | DispatcherType hoặc OncePerRequestFilter setting | Kiểm tra asyncSupported, registration và callback |
| Filter làm async request lỗi startup | Filter/Servlet không hỗ trợ async | Bật asyncSupported đúng với toàn chain khi cần |
| HandlerInterceptor đo 2 lần | REQUEST và ASYNC dispatch có lifecycle khác | Dùng AsyncHandlerInterceptor và request attributes hợp lý |
| MockMvc test chỉ nhìn response rỗng | Chưa gọi asyncDispatch | Assert asyncStarted, rồi asyncDispatch trước kiểm tra body |
| Callable bị lỗi nhưng response không như mong đợi | Exception resolver/advice không xử lý lỗi async | Test exception qua full MVC lifecycle |
| Kết nối client bị ngắt mà task tiếp tục | Async completion không đồng nghĩa task cancellation | Có cancellation/timeout ở nguồn công việc và cleanup |
| Tốc độ không tăng | Downstream bottleneck hoặc pool nhỏ | Tối ưu dependency, caching, queue và capacity trước |

**Đừng dùng Thread.sleep để giải quyết race hoặc tạo business synchronization.** Trong test, dùng CountDownLatch/CompletableFuture/fake message listener có tín hiệu rõ. Trong production, dùng message correlation, transaction và shared state có quản lý.

## 18. Checklist khi đưa async MVC vào production

1. Ứng dụng thật sự chạy Spring MVC/Servlet; không nhầm với WebFlux-only.
2. Servlet và các Filters liên quan hỗ trợ async request.
3. AsyncTaskExecutor có giới hạn worker/queue và rejection policy được thiết kế.
4. Callable phù hợp với công việc do request khởi tạo; DeferredResult phù hợp với external completion; WebAsyncTask dùng khi cần per-request timeout/executor.
5. Có HTTP async timeout, dependency timeout và proxy timeout rõ ràng.
6. Worker/job có cancellation hoặc cleanup khi timeout/client disconnect nếu công việc cho phép.
7. DeferredResult registry không bị memory leak và có policy khi event đến trước hoặc sau.
8. Không giả định ThreadLocal, transaction, MDC và SecurityContext tự truyền qua mọi executor.
9. Không chạy blocking code trong container thread của WebAsyncTask timeout callbacks.
10. Test MockMvc với asyncDispatch và integration test trên Servlet container thật.
11. Test exception, timeout, task rejection, client disconnect và overload.
12. Giám sát executor saturation, active requests, p95/p99 latency và HTTP 5xx.
13. Bảo vệ authentication/authorization cho long polling và correlation ID.
14. Không trả raw stacktrace hoặc message nội bộ từ worker exception.
15. Khi muốn gửi nhiều events, cân nhắc SseEmitter/ResponseBodyEmitter thay vì tạo vô hạn DeferredResult.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 – Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, WebAsyncTask, ASYNC dispatch, error handling và Servlet async configuration.
- [Spring Framework 6.2 – AsyncSupportConfigurer](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): setTaskExecutor, setDefaultTimeout, CallableProcessingInterceptor/DeferredResultProcessingInterceptor.
- [Spring Framework 6.2 – WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): constructors và lifecycle callbacks.
- [Spring Framework 6.2 – DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): setResult, setErrorResult, onTimeout/onError/onCompletion.
- [Spring Framework 6.2 – MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html): request().asyncStarted() và asyncDispatch().
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured AsyncTaskExecutor, applicationTaskExecutor và virtual threads khi Java 21+.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): spring.mvc.async.request-timeout.

## 20. Kết luận

**Callable** để Spring MVC chủ động thực thi một công việc trên executor; **DeferredResult** để một nguồn kết quả ngoài controller quyết định khi nào HTTP response sẵn sàng; **WebAsyncTask** để bọc Callable với timeout, executor và callbacks có chủ đích. Cả ba tận dụng Servlet async để giải phóng thread nhận request ban đầu rồi hoàn tất response bằng một ASYNC dispatch.

Muốn hệ thống chạy tốt, ngoài việc chọn return type phải cấu hình executor, timeout theo nhiều tầng, xử lý lỗi và late completion, bảo vệ context/transaction, quản lý pending requests và kiểm thử đúng lifecycle. Async MVC giảm việc giữ Servlet thread trong lúc chờ, nhưng không thay thế capacity planning và không tự biến công việc blocking thành non-blocking I/O.