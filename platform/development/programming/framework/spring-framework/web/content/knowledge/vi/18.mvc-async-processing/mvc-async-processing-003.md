# Cấu hình TaskExecutor, timeout và giới hạn tài nguyên trong Spring MVC bất đồng bộ

## 1. Mục tiêu bài học

Spring MVC trên Servlet stack có thể xử lý HTTP theo mô hình bất đồng bộ: controller trả `Callable<T>`, `WebAsyncTask<T>` hoặc `DeferredResult<T>`; Servlet request thread ban đầu rời đi trong khi kết quả được tạo sau đó. Điều này giúp tránh giữ một luồng Servlet chỉ để chờ tác vụ, nhưng không khiến CPU, worker threads, connection, bộ nhớ, hàng đợi hay hệ thống phụ thuộc trở nên vô hạn.

Sau bài học, bạn sẽ:

- Hiểu vòng đời Servlet `REQUEST → startAsync → worker/callback → ASYNC dispatch → response`.
- Phân biệt `Callable`, `WebAsyncTask`, `DeferredResult`, `@Async` và `CompletableFuture`.
- Cấu hình `WebMvcConfigurer.configureAsyncSupport` và `AsyncSupportConfigurer`.
- Đặt `ThreadPoolTaskExecutor` có `corePoolSize`, `maxPoolSize`, `queueCapacity`, chính sách rejection và shutdown.
- Phân biệt Servlet async timeout, timeout riêng mỗi request, client/gateway timeout, downstream HTTP/DB timeout.
- Biết timeout **không tự hủy** mọi tác vụ nền hoặc rollback tác dụng phụ.
- Thiết kế giới hạn tài nguyên: queue, admission control, connection pool, pending DeferredResult, SSE, backpressure và quotas.
- Kiểm tra response cuối của MVC async bằng `MockMvc.asyncDispatch` và thử HTTP thực qua `curl`.
- Nhận diện overload, timeout, disconnect, context propagation và đo queue wait/throughput/latency.

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Jakarta Servlet**. Đây là Spring MVC Servlet stack, không phải WebFlux. Mã `Thread.sleep` trong demo chỉ mô phỏng I/O; production cần timeout/cancellation của downstream thực tế.

## 2. Servlet async hoạt động như thế nào?

Luồng thông thường khi một controller trả `Callable`:

```text
Client
  |
  | GET /async/callable
  v
Servlet container -------------- DispatcherServlet
  |                                  |
  |  REQUEST thread                   | controller trả Callable
  |                                  | request.startAsync()
  |                                  | submit Callable -> AsyncTaskExecutor
  |  REQUEST thread quay về pool       |
  |                                  |
  |                              Worker thread
  |                                  | chạy Callable, I/O/CPU
  |                                  | trả value/throw error
  |                                  v
  |                     Servlet ASYNC dispatch
  |                                  |
  |                     DispatcherServlet xử lý result
  |                     HttpMessageConverter ghi JSON
  v
Client nhận response
```

Một số điểm dễ nhầm:

1. **Chỉ luồng Servlet ban đầu được trả về sớm.** Nếu `Callable` gọi JDBC synchronous, ngủ, chờ outbound HTTP hoặc đọc tệp, **worker vẫn bị block**.
2. **HTTP response vẫn mở** trong khi chờ; TCP connection, request attributes và buffer tương ứng có chi phí.
3. **Callable result cần async dispatch** trở lại Servlet container để Spring MVC hoàn tất xử lý response.
4. Filter và interceptor có lifecycle khác sau khi bắt đầu async; logging/cleanup cần xét cả REQUEST/ASYNC dispatch.
5. Nếu worker không tạo kết quả đúng hạn, Servlet async timeout có thể kích hoạt; không thể mặc định Java task bị hủy ở đúng mốc.
6. Async không tự tăng sức chứa database hoặc outbound HTTP connection pool; tăng workers có thể chỉ làm nhiều request chờ ở tầng thấp hơn.

Spring Framework mô tả rõ quá trình này trong tài liệu chính thức về asynchronous requests.

## 3. Các kiểu xử lý async của Spring MVC

| Return type | Nơi tạo kết quả | Tình huống phù hợp |
| --- | --- | --- |
| `ResponseEntity<T>` đồng bộ | Servlet request thread | Xử lý ngắn, giản đơn |
| `Callable<T>` | MVC `AsyncTaskExecutor` | Giải phóng request thread khi callable chạy việc khác |
| `WebAsyncTask<T>` | MVC executor hoặc executor riêng | Callable cần timeout và callbacks theo request |
| `DeferredResult<T>` | Producer của ứng dụng/event listener | Kết quả đến từ callback/message/job bên ngoài |
| `CompletableFuture<T>` | Executor tạo future do ứng dụng chọn | Pipeline async có timeout/cancellation riêng |
| `@Async` trên bean method | Spring async infrastructure/executor riêng | Công việc bất đồng bộ tại tầng service |
| `SseEmitter`, `ResponseBodyEmitter` | Cơ chế streaming của MVC | Gửi nhiều events/chunks, cần connection budget |

**`DeferredResult` không tự submit business logic vào MVC executor.** Controller đăng ký một placeholder; thread/event source của ứng dụng phải gọi `setResult` hoặc `setErrorResult` khi có kết quả.

**`@Async` không đồng nghĩa MVC async.** `@EnableAsync` và executor của `@Async` có cơ chế cấu hình khác; `configureAsyncSupport` là điểm chủ yếu để chỉ rõ executor cho `Callable` MVC. Không bật `@EnableAsync` chỉ để controller có thể return `Callable`.

Nếu tác vụ đã rất nhanh, mô hình đồng bộ có thể tối ưu hơn. Không thêm async bằng thói quen khi chưa đo thread usage, I/O wait, p95/p99 và nhu cầu mở connection lâu.

## 4. configureAsyncSupport là điểm cấu hình MVC

Spring MVC cho phép override callback của `WebMvcConfigurer`:

```java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(mvcExecutor());
    configurer.setDefaultTimeout(2500L);
}
```

Đây là **đoạn method minh họa** trong class cấu hình đã có `mvcExecutor()`. Mã runnable đầy đủ ở phần sau.

- `setTaskExecutor(AsyncTaskExecutor)` chỉ định executor MVC cho `Callable` và một số trường hợp blocking writes khi MVC thích ứng streaming/reactive return types.
- `setDefaultTimeout(long)` dùng **milli giây** làm timeout mặc định cho async requests khi không override theo return type.
- Khi không đặt default timeout, giá trị phụ thuộc Servlet container/framework configuration, không nên hardcode một con số được ghi nhớ từ phiên bản khác.
- Với `WebAsyncTask`, có thể chỉ định timeout và executor riêng.
- Với `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, có thể cấu hình timeout theo từng object.
- `registerCallableInterceptors(...)` và `registerDeferredResultInterceptors(...)` hỗ trợ timeout/error/completion handling chuyên sâu.

**Phạm vi:** Async timeout không phải deadline toàn HTTP: TCP connect, proxy, servlet filters, argument binding và downstream có lifecycle của chúng. Timeout Servlet async thường bắt đầu sau khi request thread ban đầu hoàn tất xử lý dispatch và kết thúc khi request được dispatch lại.

## 5. Chọn ThreadPoolTaskExecutor thay vì executor không được giới hạn

`ThreadPoolTaskExecutor` là Spring-managed wrapper quanh Java `ThreadPoolExecutor`, cung cấp cách đặt kích thước core/max, hàng đợi, thread prefix, shutdown và metrics.

Ví dụ ban đầu để học:

```text
corePoolSize = 2
maxPoolSize = 4
queueCapacity = 8
keepAliveSeconds = 30
rejection = AbortPolicy
```

Hành vi quan trọng của queue dương:

1. Khi worker count thấp hơn core, executor tạo core worker.
2. Khi core workers đang bận, task mới thường **vào queue trước**.
3. Khi queue đầy, executor mới mở rộng từ core tới max.
4. Khi pool đạt max **và** queue đầy, task mới bị reject.

Với core=2, max=4, queue=8, năng lực lý thuyết tại thời điểm bão hòa là **4 task đang chạy + 8 task chờ**. Con số này không phải giới hạn 12 HTTP connections vì mỗi async request có thể đã được nhận, còn pending DeferredResult hoặc các nguồn async khác không nằm trong MVC callable queue.

**Bẫy thường gặp:** đặt max=100 mà queueCapacity vô hạn khiến pool hiếm khi tăng trên core vì hàng đợi không đầy. Queue dài làm latency đuôi tăng, dẫn tới hàng loạt timeout dù CPU còn trống hoặc downstream đã bão hòa.

`setQueueCapacity(0)` thường tạo `SynchronousQueue` (handoff trực tiếp), giúp mở threads nhanh hơn, nhưng nếu max không đủ sẽ reject nhanh; phải benchmark thay vì coi queue=0 luôn tốt.

## 6. Rejection policy và backpressure

Các chiến lược từ Java `ThreadPoolExecutor`:

| Policy | Hành vi | Hệ quả cho HTTP async |
| --- | --- | --- |
| `AbortPolicy` | Ném exception khi quá tải | Quan sát được, có thể map thành 503 khi phù hợp |
| `CallerRunsPolicy` | Thread submit tự chạy task | Có thể chặn Servlet request thread, trái mục tiêu giải phóng |
| `DiscardPolicy` | Bỏ task | Request có thể chờ đến timeout mà không ai tạo kết quả |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue | Request trước bị mất công việc khó chẩn đoán |
| Custom rejection | Reject theo quota/bulkhead | Cần bao phủ tất cả race và errors |

Với HTTP request-response, tránh silently discard công việc. `AbortPolicy` thường giúp định hình overload rõ, nhưng không mặc định mọi `TaskRejectedException` sẽ được chuyển thành một HTTP status đẹp: nó còn phụ thuộc vị trí xảy ra rejection, MVC exception resolving và response đã commit chưa.

Một phương án production có thể **từ chối request trước khi submit** dựa trên quyền, rate/quota, số pending requests và capacity. Khi reject:
- `429 Too Many Requests` thường phù hợp với quota/rate theo identity.
- `503 Service Unavailable` có thể phù hợp với capacity server/downstream tạm thời.
- `Retry-After` chỉ đặt nếu có chính sách retry đáng tin.
- Retry phải backoff/jitter và có idempotency nếu request có side effects.

Không dùng queue vô hạn chỉ để “tránh thấy 503”. Nó biến overload nhìn thấy được thành thời gian chờ dài, timeout, memory pressure và retry storm.

## 7. Timeout nhiều tầng: thời gian ai kiểm soát?

Giả sử ứng dụng có các mốc ví dụ:

```text
Client timeout       5 s
Gateway timeout      4 s
Servlet async        3 s
WebAsyncTask         2 s
Outbound HTTP read   1 s
DB statement         800 ms
```

Đây chỉ là **ví dụ policy**, không phải các giá trị mặc định.

Các tầng cần phân biệt:

- **Client timeout:** người dùng/chương trình gọi đã ngừng đợi; request ở server có thể vẫn đang chạy.
- **Reverse proxy/gateway timeout:** ingress không đợi upstream nữa, có thể gửi 504 hoặc đóng kết nối; Spring handler có thể không hề biết ngay.
- **Servlet async timeout:** lifecycle request bên server hết hạn, callbacks/interceptors có cơ hội tạo response/error.
- **WebAsyncTask timeout:** override timeout cho callable cụ thể.
- **DeferredResult timeout:** thời gian chờ callback tạo kết quả, không giới hạn producer job bên ngoài.
- **HTTP client connect/read/response timeout:** thuộc chính outbound client.
- **Database query/transaction timeout:** do driver, pool và transaction manager xử lý theo khả năng của chúng.
- **Queue wait:** task chưa bắt đầu nhưng thời gian yêu cầu bất đồng bộ vẫn đang trôi.

**Quy tắc:** Timeout HTTP không tự động cancel mọi I/O, ngắt tất cả worker, rollback transaction hoặc xóa side effect. Ngay cả khi Java task bị interrupt, driver/network call có thể không dừng được ngay. Tác vụ ghi dữ liệu quan trọng cần idempotency key, transaction/uniqueness constraint và mô hình retry rõ ràng.

## 8. WebAsyncTask: timeout và callback riêng từng request

Ví dụ:

```java
WebAsyncTask<ResponseEntity<ResultDto>> task =
        new WebAsyncTask<>(400L, () -> {
            ResultDto result = slowService.compute();
            return ResponseEntity.ok(result);
        });

task.onTimeout(() -> ResponseEntity.status(503)
        .body(new ResultDto("timeout")));

task.onCompletion(() -> recordMetrics());
return task;
```

Đoạn trên là **snippet** cần có bean/service và imports tương ứng; mã hoàn chỉnh ở phần ứng dụng demo.

- `onTimeout(Callable<V>)` trả một kết quả thay thế, có thể là 503 với JSON đã xác định.
- Callback timeout chạy trên container thread và **phải rất nhanh**; không thực hiện query DB dài hoặc gọi network chặn trong callback.
- `onError` xử lý sự cố async tùy policy; không nuốt lỗi business thành 200.
- `onCompletion` có thể dùng cleanup/metrics, cần idempotent và nhẹ.
- Nếu Callable hoàn tất trước deadline, Spring MVC sử dụng kết quả của Callable để tiếp tục ASYNC dispatch.
- Nếu timeout trước, response có thể được hoàn tất bằng fallback; Callable vẫn có thể tiếp tục.
- Nếu response đã commit, không đảm bảo callback có thể đổi status/body thành một JSON lỗi chuẩn.

Đặt timeout riêng 400ms không có nghĩa tác vụ `Thread.sleep(3000)` sẽ bị ngắt chắc chắn lúc 400ms. Deadline request và vòng đời worker là hai khái niệm khác nhau.

## 9. DeferredResult và pending request không sử dụng MVC worker

Ví dụ long polling:

```java
@GetMapping("/events/{id}")
public DeferredResult<ResponseEntity<EventDto>> waitForEvent(
        @PathVariable String id) {

    DeferredResult<ResponseEntity<EventDto>> result =
            new DeferredResult<>(1500L);

    registry.add(id, result);

    result.onTimeout(() -> {
        registry.remove(id, result);
        result.setResult(ResponseEntity.noContent().build());
    });
    result.onCompletion(() -> registry.remove(id, result));

    return result;
}
```

Đây là **đoạn minh họa**, chưa phải tệp runnable: `EventDto` và `registry` phải được ứng dụng cung cấp. Khi event xuất hiện, publisher có thể gọi `result.setResult(ResponseEntity.ok(event))`, kích hoạt async dispatch.

Lưu ý:

- `setResult` trả boolean; sau timeout/completion việc đặt kết quả có thể thất bại.
- `onTimeout` chạy trong lifecycle Servlet async, không thay việc cancel producer job.
- `registry` phải giới hạn số pending entries, dọn trong `onCompletion`/timeout/error; không bao giờ giữ đối tượng `DeferredResult` vô thời hạn.
- 204 trong ví dụ chỉ là **long-poll timeout không có event** theo một API contract giả định; khi đây là lỗi availability, 503 có thể hợp lý hơn.
- Nhiều pending requests vẫn giữ HTTP connections, request/response state và bộ nhớ, dù worker pool rảnh.
- Nếu bạn submit producer vào một executor riêng, executor đó cần queue/timeout/rejection policy riêng; MVC `setTaskExecutor` không tự giới hạn nó.

## 10. Streaming, SSE và giới hạn resource

`SseEmitter`, `ResponseBodyEmitter` và `StreamingResponseBody` cần quan tâm riêng:

- SSE/long polling giữ một HTTP connection lâu; tổng pending sessions phải được giới hạn per user/tenant.
- Khi client chậm, buffers tăng hoặc write bị block; cần backpressure, buffer cap và drop/disconnect policy.
- Spring MVC có thể dùng worker cho blocking writes, nên executor cần được cấu hình và monitor.
- HTTP response có thể đã commit sau khi gửi chunk đầu; nếu phát sinh lỗi giữa stream, không thể đơn giản thay status thành 503 và gửi JSON thông thường.
- Client disconnect có thể gây `IOException`; cần unregister subscriptions, hủy producer phù hợp và cleanup.
- Nếu có heartbeat, đặt tần suất và timeout hợp lý để không biến keep-alive thành overhead quá lớn.
- Không dùng một executor chung quá nhỏ cho tác vụ CPU nặng, stream dài và REST requests ngắn nếu có nguy cơ starvation.
- Với job chạy vài phút, thường phù hợp hơn là `202 Accepted + jobId` rồi client poll trạng thái, thay vì giữ HTTP response mở vô hạn.

Streaming không phải là miễn phí khi hệ thống có hàng nghìn kết nối đồng thời.

## 11. Mã runnable: Spring Boot 3 + Java 17

Tạo Maven project Spring Initializr Java 17+, dependencies:
- `spring-boot-starter-web`
- `spring-boot-starter-test` (test scope)

Ứng dụng demo không cần DB. Nó sử dụng một executor riêng với core=2, max=4, queue=8; MVC default async timeout 2500ms. Một endpoint dùng `Callable`, endpoint còn lại dùng `WebAsyncTask` 400ms để quan sát timeout riêng.

Cấu trúc:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  MvcAsyncConfig.java
  AsyncDemoController.java
src/test/java/com/example/demo/
  AsyncDemoControllerTest.java
```

### 11.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.2. MvcAsyncConfig.java

```java
package com.example.demo;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mvc-async-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(2500L);
    }
}
```

`@Configuration` mặc định proxy bean methods, nên gọi `mvcAsyncExecutor()` từ method trên cùng configuration class sẽ nhận **bean singleton Spring quản lý**, không tạo một executor mới mỗi request. Nếu đổi sang `@Configuration(proxyBeanMethods = false)`, không nên dựa vào lời gọi method trực tiếp này để lấy singleton; cần tiêm bean đã tạo từ cấu hình khác hoặc wiring tường minh.

Pool này là lựa chọn **mang tính bài tập**, không được coi là default phù hợp cho mọi production. `AbortPolicy` giúp rejection có thể quan sát được, nhưng bạn cần admission/error policy phù hợp nếu muốn trả 503 theo hợp đồng.

### 11.3. AsyncDemoController.java

```java
package com.example.demo;

import java.util.concurrent.Callable;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/async")
public class AsyncDemoController {

    @GetMapping("/callable")
    public Callable<WorkResponse> callable(
            @RequestParam(defaultValue = "20") long delayMs) {

        long duration = validateDelay(delayMs);

        return () -> {
            Thread.sleep(duration); // Mô phỏng blocking work.
            return new WorkResponse(
                "done", Thread.currentThread().getName());
        };
    }

    @GetMapping("/timed")
    public WebAsyncTask<ResponseEntity<WorkResponse>> timed(
            @RequestParam(defaultValue = "20") long delayMs) {

        long duration = validateDelay(delayMs);

        WebAsyncTask<ResponseEntity<WorkResponse>> task =
                new WebAsyncTask<>(400L, () -> {
                    Thread.sleep(duration);
                    return ResponseEntity.ok(new WorkResponse(
                        "done", Thread.currentThread().getName()));
                });

        task.onTimeout(() ->
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new WorkResponse("timeout", "container")));

        task.onCompletion(() -> {
            // Có thể ghi metrics/cleanup nhẹ và idempotent.
        });
        return task;
    }

    private long validateDelay(long delayMs) {
        if (delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "delayMs must be between 0 and 5000");
        }
        return delayMs;
    }

    public record WorkResponse(String status, String worker) {}
}
```

Phân tích:

- `/async/callable` trả `Callable` nên công việc được chuyển sang MVC executor; timeout mặc định là 2500ms.
- `/async/timed` trả `WebAsyncTask` với timeout riêng 400ms; callback có thể tạo HTTP 503 khi thời hạn hết.
- `delayMs` bị giới hạn từ 0 đến 5000ms để demo không biến thành endpoint sleep vô hạn. Trong production không đưa endpoint này cho client công khai.
- `worker` ghi tên thread thực thi. Prefix `mvc-async-` do executor tạo, phần số không xác định trước.
- `Thread.sleep` làm nghẽn worker trong demo; ứng dụng thật cần giới hạn/tối ưu I/O và service concurrency.
- Timeout fallback **không bảo đảm** đã dừng sleep hoặc hủy tác dụng phụ; nếu task tiếp tục chạy, kết quả muộn có thể không được dùng làm HTTP body.
- Response không có authentication/authorization trong demo; production phải bảo vệ route và không cho user tùy ý chọn độ dài công việc.

### 11.4. Khởi động

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Nếu `server.port` chưa đổi, truy cập `localhost:8080`. Các file trên cần Spring Boot classpath; `javac AsyncDemoController.java` riêng lẻ không thể biên dịch khi không có Spring dependencies.

## 12. Curl thử async response và timeout

### Thành công với Callable

```bash
curl -i 'http://localhost:8080/async/callable?delayMs=20'
```

Kỳ vọng HTTP 200 và JSON đại diện:

```json
{
  "status": "done",
  "worker": "mvc-async-1"
}
```

`mvc-async-1` **chỉ là ví dụ**: không hardcode thread number trong test. Quan trọng là `status="done"`.

### WebAsyncTask hoàn tất trước deadline

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=20'
```

Khi hệ thống không bị bão hòa, kỳ vọng HTTP 200 với `status="done"`. Tổng thời gian còn có queue wait và thread scheduling; 20ms sleep không đảm bảo mọi HTTP request sẽ trả trong 400ms trên máy quá tải.

### Timeout riêng

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=3000'
```

Với embedded Servlet container bình thường, HTTP thường trở thành **503 Service Unavailable** kèm JSON `status="timeout"` từ callback. Thời điểm response không phải cam kết thời gian thực tuyệt đối, và worker có thể vẫn chạy sau timeout. Nếu gateway ngắt trước, client có thể không thấy JSON fallback của ứng dụng.

### Input sai

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=-1'
```

Kỳ vọng HTTP 400. Nếu `delayMs=abc`, Spring argument conversion có thể tạo 400 trước khi controller trả WebAsyncTask.

## 13. MockMvc phải có asyncDispatch

Với controller trả `Callable`/`WebAsyncTask`, lần `perform` đầu thường chỉ xác nhận request đã bắt đầu Servlet async. Kết quả HTTP thực được xử lý qua dispatch tiếp theo, nên cần gọi `asyncDispatch(...)`.

Tệp `src/test/java/com/example/demo/AsyncDemoControllerTest.java`:

```java
package com.example.demo;

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

    @Test
    void callableReturnsOnAsyncDispatch() throws Exception {
        MvcResult first = mvc.perform(get("/async/callable")
                    .param("delayMs", "0"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("done"));
    }

    @Test
    void webAsyncTaskReturnsOnAsyncDispatch() throws Exception {
        MvcResult first = mvc.perform(get("/async/timed")
                    .param("delayMs", "0"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("done"));
    }

    @Test
    void badInputFailsBeforeAsyncStarted() throws Exception {
        mvc.perform(get("/async/timed").param("delayMs", "-1"))
            .andExpect(status().isBadRequest());
    }
}
```

Chạy tests:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là ví dụ test có thể chạy với dependencies đã nêu, **không tuyên bố đã chạy trong repository của người dùng**. Nếu bật Spring Security, cần setup authentication/authorization phù hợp; việc request bị chặn trước MVC không chứng minh async controller sai.

**Giới hạn của MockMvc:** nó không mô phỏng đầy đủ timeout schedule/error dispatch/network behavior của Servlet container thực, cũng không kiểm tra proxy hoặc disconnect. Muốn xác nhận timeout 400ms và fallback HTTP 503, dùng HTTP integration test với embedded container chạy cổng thật hoặc `curl`; kết quả có thể khác trong môi trường tải cao.

## 14. Java 17 độc lập: bounded queue và reject deterministic

Một ví dụ Java thuần thể hiện vì sao bounded queue tạo rejection rõ. Tệp `BoundedPoolDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // Worker chắc chắn đã bận.
            Future<?> queued = pool.submit(() -> {});

            boolean rejected = false;
            try {
                pool.submit(() -> {}); // 1 running + 1 queued
            } catch (RejectedExecutionException ex) {
                rejected = true;
            } finally {
                release.countDown();
            }

            running.get();
            queued.get();
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("terminated=" +
                pool.awaitTermination(1, TimeUnit.SECONDS));
    }
}
```

Biên dịch và chạy Java 17:

```bash
javac BoundedPoolDemo.java
java BoundedPoolDemo
```

Stdout bình thường:

```text
rejected=true
terminated=true
```

`CountDownLatch` khiến worker chắc chắn đang bận trước khi task thứ hai được queue và task thứ ba bị reject, không phụ thuộc vào phỏng đoán của `Thread.sleep(10)`. `terminated=true` xảy ra khi task đã xong và shutdown hoàn thành trong 1 giây; trên máy bị đình trệ bất thường `awaitTermination` có thể trả false nên đây không phải một deadline real-time chắc chắn.

Trong Spring, `ThreadPoolTaskExecutor` thường chuyển saturation sang `TaskRejectedException` của Spring, cần xử lý đúng tại HTTP/application layer. Không lấy `Executors.newFixedThreadPool` mặc định làm bounded queue mà không xem implementation: queue của factory này có thể tăng không giới hạn.

## 15. Timeout không hủy side effect và retry phải có idempotency

Ví dụ tình huống:

```text
T=0ms     HTTP request bắt đầu
T=50ms    Worker bắt đầu gọi database/payment gateway
T=400ms   Servlet async timeout, client nhận 503
T=800ms   Downstream call còn xử lý
T=1200ms  Transaction hoặc payment có thể commit
T=1400ms  Worker cố trả result nhưng HTTP request đã hoàn tất
```

Đây là một **tình huống khả dĩ**; không phải timeline mặc định của Spring.

Hậu quả: client thấy 503 có thể retry, trong khi thao tác cũ thực sự thành công. Với đơn hàng/thanh toán/ghi dữ liệu, cần:
- Idempotency key do client tạo đúng contract, lưu kết quả ở backend.
- DB unique constraint/transaction bảo đảm không tạo trùng.
- Propagate deadline/cancellation vào outbound client khi được hỗ trợ.
- Không dùng HTTP timeout làm dấu hiệu chắc chắn transaction đã rollback.
- Nếu công việc dài, chuyển sang **job processing có trạng thái**, trả `202 Accepted` cùng job ID; client dùng GET tra status.
- Không cho background job dựa vào `HttpServletRequest` còn tồn tại sau response.

## 16. Admission control, semaphore và request pending

Bounded pool giới hạn **workers + queue**, không tự giới hạn mọi pending HTTP requests, SSE connections hoặc `DeferredResult` registrations. Một bảo vệ hoàn chỉnh cần:

1. Gateway/container giới hạn tổng connections, in-flight requests, request timeouts.
2. Application rate/quota limit theo tenant/user và endpoint.
3. Executor bounded core/max/queue, rejection policy được quan sát.
4. DB connection pool và HTTP client connection pool không bị vượt budget.
5. Giới hạn `DeferredResult`/SSE pending sessions và cleanup.
6. CPU/memory/time budget cho parsing/streaming/response bodies.
7. Bulkhead riêng cho long-running export, báo cáo, CPU-heavy jobs và REST latency thấp.
8. Retry/backoff/circuit breaker để không dồn tải lên downstream đang chậm.

Một `Semaphore` có thể giới hạn số hoạt động, nhưng phải định nghĩa permit đo **HTTP in-flight** hay **worker đang chạy**. Nếu release khi HTTP timeout mà worker vẫn chạy, bạn đã giảm số request pending chứ không thật sự giảm worker occupancy. Nếu chỉ release trong `Callable.finally` mà task bị reject trước khi worker bắt đầu, permit có thể không được trả. Vì vậy semaphore logic cần xét success, rejection, timeout, cancellation, disconnect và cleanup idempotent; không coi một đoạn `tryAcquire/finally release` ngắn là đủ cho mọi trường hợp.

## 17. Servlet Filter, ASYNC dispatcher và interceptor

Để Servlet async hoạt động:

- Servlet và filters liên quan cần `asyncSupported=true` trong registration.
- Filter mapping cần bao gồm `DispatcherType.ASYNC` nếu logic filter cần chạy trên async dispatch.
- `OncePerRequestFilter` có hooks `shouldNotFilterAsyncDispatch()`/`shouldNotFilterErrorDispatch()`; không giả định mọi filter chạy đúng một lần trong toàn request.
- `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` có thể được gọi khi controller khởi tạo async thay vì `postHandle`/`afterCompletion` thông thường của initial dispatch.
- Khi async result được dispatch lại, Spring MVC/filters có thể đi qua một lifecycle bổ sung.
- Logs, metrics, tracing/correlation ID cần tránh đếm hai lần và phải dọn state đúng thời điểm **request hoàn tất**, không chỉ khi initial `chain.doFilter` trở về.

Nếu một Filter bất kỳ trên request chain không hỗ trợ async, `request.startAsync()` có thể thất bại dù controller đã return `Callable`. Đặc biệt cần test WAR deployment trên Servlet container bên ngoài: registration và `DispatcherType` có thể khác embedded server.

## 18. ThreadLocal, SecurityContext, Locale và MDC

Async worker là thread khác. Những context sau **không tự động được propagate đầy đủ** qua mọi executor:

- `RequestContextHolder`/Servlet request attributes.
- `LocaleContextHolder`/locale.
- SLF4J `MDC`.
- Spring Security `SecurityContextHolder`.
- Transaction/JPA persistence context.

Một task nên nhận snapshot immutable của thông tin cần thiết qua method parameters, chẳng hạn `Locale`, correlation ID hoặc user ID đã xác thực. Nếu cần propagation cho Spring Security/tracing/MDC, dùng cơ chế chính thống có lifecycle/cleanup rõ ràng; không tự copy toàn bộ `HttpServletRequest` vào thread pool, và không bật `InheritableThreadLocal` vô điều kiện vì pooled threads tái sử dụng giữa requests.

Ví dụ ý tưởng:

```java
Locale selectedLocale = locale;
String correlationId = safeGeneratedCorrelationId;

return () -> reportService.prepare(
        selectedLocale, correlationId);
```

Đây là snippet minh họa trong controller đã có bean/variables tương ứng. Tránh lấy identity tin cậy từ header client tự khai báo. Worker phải được kiểm tra quyền khi truy cập dữ liệu nhạy cảm theo chính sách phù hợp.

## 19. Kế hoạch capacity và Little's Law

Số request đồng thời không trực tiếp bằng số Java worker threads. Trong trạng thái ổn định:

```text
L = λ × W

L: số request trung bình trong hệ thống
λ: throughput trung bình (request/giây)
W: thời gian lưu trong hệ thống (giây)
```

Nếu app xử lý 100 request/giây với mean latency 0,25 giây thì L xấp xỉ 25 requests đang hiện diện, **không phải cấu hình chính xác 25 worker threads**. Các request có thể chờ async, chờ queue, connection, DB hoặc network; workload peak/p99 khác mean.

Một worker pool có 4 threads, mỗi blocking task chiếm trung bình 300ms, có trần xử lý thô khoảng 4/0,3 ≈ 13 task/giây trước overhead. Nếu arrival liên tục vượt sustainable throughput, queue sẽ đầy; tăng queue 8 thành 800 chỉ trì hoãn rejection, đồng thời làm tail latency/timeouts lớn hơn.

CPU-bound tasks không nên dùng số threads lớn tùy ý; I/O-bound tasks có thể cần concurrency nhiều hơn nhưng phải cân bằng với connection pool, memory và downstream rate limits. Trên nhiều replicas, mỗi pod có executor riêng, tổng concurrency có thể tăng theo số pods; downstream shared DB vẫn có limit chung.

## 20. Metrics và cách debug overload/timeout

| Metric | Điều quan sát |
| --- | --- |
| `poolSize`/`activeCount` | Worker đang dùng, pool có chạm max? |
| `queueSize`/`queueCapacity` | Backlog và độ gần saturation |
| submitted/completed/rejected tasks | Rejection rate và throughput |
| queue wait time | Task phải đợi bao lâu trước khi chạy |
| execution time | Work thực sự mất bao lâu |
| HTTP total latency p50/p95/p99 | Trải nghiệm client gồm queue/dispatch/network |
| Async timeout rate | Deadline có phù hợp không |
| Pending DeferredResult/SSE | Request registrations và connections đang mở |
| DB/HTTP client pool occupancy | Bottleneck downstream |
| CPU, heap, GC, file descriptors | Tài nguyên toàn process |

`ThreadPoolTaskExecutor` có các getters cho pool/active/queue state; có thể expose qua metrics/observability framework phù hợp. Không công khai endpoint trả thông tin nội bộ mà không có authorization.

Quy trình debug:

1. Xác định 503 do `WebAsyncTask.onTimeout`, executor rejection, gateway hay service downstream.
2. Kiểm tra queue wait so với task execution time: độ trễ đến từ hàng đợi hay I/O?
3. Xem `activeCount`, `queueSize`, `maxPoolSize` và rejection.
4. Kiểm tra DB/HTTP connection pools, CPU throttling và memory.
5. Xem các tác vụ tiếp tục sau khi client đã timeout/disconnect.
6. Kiểm tra retry storm từ clients; có idempotency và backoff?
7. Kiểm tra Servlet REQUEST/ASYNC dispatch, filter/interceptor lifecycles, correlation ID.
8. So sánh môi trường local, HTTP integration và gateway thực; MockMvc không bao phủ hết container.
9. Quyết định sửa policy: fail fast, tăng phù hợp worker, giảm queue, tối ưu downstream hoặc chuyển công việc dài sang background jobs.

## 21. Sai lầm phổ biến

1. **Không cấu hình MVC executor** rồi chạy `Callable` tải cao mà không giới hạn concurrency.
2. **Đặt maxPoolSize lớn và để queue không giới hạn**; max không giúp tăng nhanh như nghĩ.
3. **Dùng `CallerRunsPolicy`** và khẳng định servlet thread đã được giải phóng.
4. **Dùng `DiscardPolicy`** khiến request không bao giờ nhận kết quả.
5. **Cho rằng `@EnableAsync` quyết định tất cả MVC Callable processing**.
6. **Coi `DeferredResult` tự tạo worker**; nó chỉ giữ kết quả chờ producer.
7. **Coi MVC timeout tự hủy mọi @Async/background job**.
8. **Coi 503 là bằng chứng DB transaction chưa commit**.
9. **Không đặt timeout outbound HTTP/DB**; worker vẫn chờ rất lâu sau HTTP timeout.
10. **Không đếm queue wait trong end-to-end latency budget**.
11. **Giữ pending DeferredResult hoặc SSE vô hạn**, leak request references.
12. **Không xử lý race khi setResult sau timeout**.
13. **Dùng streaming mà không kiểm soát buffers/backpressure**.
14. **Chạy blocking IO trong onTimeout/onCompletion** trên container thread.
15. **Không cấu hình filter asyncSupported và DispatcherType.ASYNC** đúng.
16. **Đếm metrics hai lần** do REQUEST và ASYNC dispatch.
17. **Mang ThreadLocal request context nguyên trạng qua thread pool**.
18. **Dùng queue lớn để che overload** làm latency và retry storm tăng.
19. **Bắt TaskRejectedException thành 200** hoặc nuốt exception.
20. **Không test bằng asyncDispatch** và tưởng test đã xác minh body.
21. **Dựa MockMvc để xác nhận gateway/Servlet timeout**.
22. **Không tách long jobs khỏi endpoint tương tác ngắn**.
23. **Không giới hạn rate/concurrency theo user/tenant**.
24. **Scale workers vượt DB connection pool** và làm hệ thống chậm hơn.
25. **Không có load test có giới hạn** trong staging để kiểm timeout/rejection.
26. **Vội bật virtual threads** rồi nghĩ DB/socket/memory limits biến mất.
27. **Không dọn producer khi client disconnect**, gây tài nguyên tồn dư.
28. **Không thiết kế graceful shutdown** khi pod đang giữ async requests.

## 22. Checklist triển khai production

### Executor

- [ ] Spring MVC `configureAsyncSupport` dùng đúng `AsyncTaskExecutor` có capacity hữu hạn?
- [ ] Core/max/queue phản ánh loại workload và downstream bottleneck?
- [ ] Đã hiểu queue thường đầy trước khi mở workers vượt core?
- [ ] Rejection có status/error contract đúng, không silently drop?
- [ ] Không vô tình dùng CallerRuns làm block Servlet request threads?
- [ ] Executor cho streams/exports/jobs dài đã được tách nếu cần?
- [ ] Có metrics active/queue/rejected và alerting?
- [ ] Shutdown/draining/termination budget được đặt có chủ đích?

### Timeout

- [ ] MVC default async timeout được xác định rõ và test qua container thật?
- [ ] Request đặc thù dùng `WebAsyncTask`/`DeferredResult` timeout đúng?
- [ ] Gateway/client/downstream timeouts cùng phù hợp latency budget?
- [ ] Timeout/cancellation và transaction side effects được thiết kế riêng?
- [ ] Có idempotency/retry policy cho unsafe writes?
- [ ] Pending DeferredResult/SSE có capacity và cleanup?
- [ ] Callback không block và response đã commit được xử lý an toàn?

### Kiểm thử/vận hành

- [ ] MockMvc kiểm tra `asyncStarted` và `asyncDispatch`?
- [ ] Integration test có trường hợp timeout, reject, disconnect?
- [ ] Có load test giới hạn để đo queue wait/p95/p99 và recovery?
- [ ] Filter/Servlet `ASYNC` registration đúng?
- [ ] SecurityContext, Locale, MDC, tracing không rò giữa threads?
- [ ] Có cách chuyển công việc dài sang `202 Accepted + job status` thay vì request mở lâu?

## 23. Câu hỏi tự kiểm tra

**1.** MVC `Callable` chạy trên thread nào?

**Đáp án:** Thường trên MVC `AsyncTaskExecutor` sau khi servlet request thread ban đầu đã rời dispatch. Servlet async request vẫn giữ response mở.

**2.** `setTaskExecutor` có tự chọn executor cho mọi `@Async` method không?

**Đáp án:** Không. `@Async` là cơ chế riêng; muốn dùng chung phải cấu hình có chủ đích.

**3.** Vì sao maxPoolSize=50 mà pool thực tế chỉ có hai workers?

**Đáp án:** Nếu core=2 và queue chưa đầy, tasks thường tiếp tục vào queue; pool chưa cần tăng lên max.

**4.** Timeout callback của WebAsyncTask có bảo đảm worker đã dừng không?

**Đáp án:** Không. Nó xử lý response lifecycle, không nhất thiết hủy I/O hoặc rollback side effects.

**5.** DeferredResult có tự chạy business work trên MVC executor không?

**Đáp án:** Không. Result được cung cấp từ publisher/event/job của ứng dụng.

**6.** Vì sao không dùng DiscardPolicy mặc định cho HTTP Callable?

**Đáp án:** Task có thể mất âm thầm khiến HTTP request treo đến timeout mà không tạo response.

**7.** CallerRunsPolicy có thể làm gì dưới overload?

**Đáp án:** Chạy task trên thread submit, có thể chính là Servlet thread, làm nghẽn request handling.

**8.** Cần gì trong test để xác minh body cuối của Callable?

**Đáp án:** `request().asyncStarted()`, lấy `MvcResult`, rồi `mvc.perform(asyncDispatch(result))`.

**9.** Có thể dùng MockMvc để khẳng định Servlet container timeout 400ms không?

**Đáp án:** Không đầy đủ. Cần HTTP integration test qua server thật, xét gateway và scheduler.

**10.** Vì sao 503 sau payment request cần idempotency?

**Đáp án:** Work cũ có thể vẫn commit sau timeout; client retry không có idempotency có thể tạo giao dịch trùng.

**11.** Nếu pool có 4 workers và queue 8, số HTTP connections tối đa là 12?

**Đáp án:** Không. Đây chỉ là năng lực task của pool; pending async requests, DeferredResult/SSE và connections vẫn có limits riêng.

**12.** Khi việc chạy nhiều phút, nên giữ WebAsyncTask 5 phút hay chuyển sang job?

**Đáp án:** Thường chuyển sang job queue với `202 Accepted` và endpoint hỏi trạng thái để tách lifetime công việc khỏi HTTP connection.

## 24. Tài liệu tham khảo

- Spring Framework 6.2 — Asynchronous Requests và `configureAsyncSupport`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — `AsyncSupportConfigurer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html
- Spring Framework — `WebAsyncTask` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html
- Spring Framework — `DeferredResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html
- Spring Framework — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/async-requests.html
- Spring Security — MVC Async Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Java 17 — ThreadPoolExecutor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java 17 — ArrayBlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
