# Kiểm thử async, streaming và máy khách ngắt kết nối trong Spring Boot web-runtime

## 1. Vấn đề cần kiểm thử: response chưa kết thúc không đồng nghĩa request đã hoàn thành

Trong ứng dụng Spring Boot, một phép kiểm thử `GET /api/hello` trả HTTP 200 thường đơn giản: gửi request, đợi response, assert status/body. Nhưng khi endpoint xử lý bất đồng bộ, trả dữ liệu từng phần hoặc client đóng kết nối giữa chừng, những câu hỏi trở nên khác nhau:

- Controller đã **trả một giá trị Java** hay HTTP response **đã hoàn tất trên mạng**?
- Một `Callable` hoặc `DeferredResult` đã bắt đầu Servlet async processing chưa, có async dispatch và error handling chính xác không?
- Một `Flux` đã được subscribe chưa, phát đủ các phần tử chưa, đã complete/error/cancel chưa?
- Server đã **flush** chunk/SSE event đầu tiên trước khi client ngắt kết nối chưa?
- Client cancel subscription trong test có lan tới server, upstream `WebClient`, database/stream writer và các tài nguyên tạm không?
- Nếu phía server đã commit tác vụ nhưng phía client ngắt kết nối, retry có tạo tác dụng phụ trùng không?
- Test có đang chạy server thật hay chỉ chạy mock controller, khiến lỗi disconnect/socket/buffer không bao giờ xuất hiện?

Bài này thuộc nhóm **Kiểm thử web runtime**, tập trung vào **kiểm thử async, streaming và máy khách ngắt kết nối** trên cả Spring MVC/Servlet và Spring WebFlux/Reactive. Ví dụ chạy với **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1 và Gradle**. Dùng version này làm mốc API để học; production nên sử dụng nhánh Spring Boot còn được hỗ trợ bảo mật và kiểm tra thay đổi khi nâng major version.

Mục tiêu cuối: viết được các bài test có **quan sát đúng tín hiệu**, có deadline hữu hạn, không nhầm `MockMvc` với network test, không “kiểm thử cancellation” bằng một assertion không liên quan tới subscription, và không dùng `Thread.sleep` tùy tiện như cách đồng bộ duy nhất.

## 2. Ba lifecycle khác nhau trong một yêu cầu HTTP

```text
             HTTP client                        Spring Boot server
                  │                                   │
                  ├──── GET /stream ─────────────────►│
                  │                                   ├─ Controller invoked
                  │                                   ├─ Callable/Flux created
                  │                                   ├─ async/Publisher subscribed
                  │                                   ├─ item 1 emitted
                  │◄──────── headers + chunk 1 ───────┤
                  │                                   ├─ item 2 emitted
                  │◄──────── chunk 2 ─────────────────┤
        client closes socket / cancels                 │
                  ╳                                   ├─ error/cancel/close signal
                                                      ├─ resource cleanup
                                                      └─ observation terminated
```

Có ít nhất ba tầng:

1. **Application computation**: controller tạo `Callable`, `DeferredResult`, `Mono`, `Flux` hay `StreamingResponseBody`; nguồn dữ liệu bắt đầu xử lý.
2. **HTTP response pipeline**: message converter/codec encode và server viết dữ liệu ra socket, có thể buffer/flush. Một phần tử phát ra **chưa bảo đảm** đã tới browser.
3. **Transport và client**: connection/socket có thể đóng do client, proxy, server timeout, network reset hoặc app shutdown. Ứng dụng chỉ nhận được tín hiệu khi tầng I/O phát hiện và propagates.

Do đó, test “service đã tạo 10 events” **không thay** test “client thực sự đọc 10 events”. Tương tự, `StepVerifier.thenCancel()` trên một `Flux` thuần **không tự chứng minh** TCP connection bị đóng, trừ khi Publisher thực sự là body của một HTTP client đang nối tới server thật.

### 2.1. Completion, error, cancellation

| Signal | Thường xảy ra khi nào | Điều có thể assert |
|---|---|---|
| `onComplete` | Publisher phát xong hoặc HTTP producer kết thúc thành công | Số events/body cuối, cleanup sau complete |
| `onError` | Logic, codec, I/O hoặc timeout báo lỗi | Loại exception và error mapping nếu response chưa committed |
| `cancel` | Subscriber không muốn dữ liệu tiếp, client disconnect, operator `take`/`timeout` | Subscription nhận cancel; tài nguyên phải dọn |
| Servlet async dispatch | `Callable`/`DeferredResult` tạo giá trị cuối | Response cuối sau `asyncDispatch` |
| Servlet client abort | Socket đóng, writer có thể nhận `IOException` khi ghi tiếp | Cleanup cuối cùng; không cam kết loại/timing IOException |
| HTTP partial response | Headers/chunk đã gửi rồi source lỗi | Client có thể nhận prefix rồi EOF/error; không đòi JSON 500 mới |

**Không đồng nhất `doFinally(CANCEL)` với network disconnect trong mọi trường hợp**. Một operator `take(2)` cũng phát cancellation chủ động ở mức ứng dụng. Muốn kết luận client disconnect, test phải **tác động trực tiếp lên network client** và có chứng cứ socket/response consumption.

## 3. Chọn tầng kiểm thử: một test không thể chứng minh mọi thứ

| Công cụ | Có server thật? | Mạnh về | Không chứng minh |
|---|---|---|---|
| JUnit thuần + fake clock | Không | Business state, timeout policy, cleanup function | HTTP framing/socket |
| `StepVerifier` | Không bắt buộc | Reactive item/error/cancel/demand | TCP disconnect nếu chỉ test Flux local |
| `MockMvc` | Không | MVC mapping, `Callable`/`DeferredResult`, `asyncDispatch`, advice | Servlet container flush/real client abort |
| `@WebMvcTest` | Không | MVC controller slice | Full bean wiring, network/headers parser |
| `WebTestClient.bindToController` | Không | WebFlux handler/codec assertions nhanh | Netty connection/ingress behavior |
| `@WebFluxTest` | Không | WebFlux controller slice, WebTestClient mock | Real socket disconnect |
| `@SpringBootTest(RANDOM_PORT)` | **Có** | Server/port/HTTP client trên mạng thực | CDN/Kubernetes/LB nếu không deploy |
| `WebTestClient.bindToServer` | **Có** | Streaming/SSE body bằng `FluxExchangeResult` | Không thay production ingress |
| JDK `HttpClient` + `BodyHandlers.ofInputStream` | **Có** | Đọc từng chunk và chủ động đóng client stream | Không đảm bảo server phát hiện abort ngay |
| Proxy/ingress staging test | **Có cả edge** | HTTP/2, compression, buffering, timeout, TLS | Không có production load thực nếu không chạy tải |

Theo Spring Boot 3.3: `@SpringBootTest` mặc định dùng mock web environment; `RANDOM_PORT` mới mở embedded web server trên cổng ngẫu nhiên. `MockMvc` hoạt động bằng mock request/response objects, không chạy browser/network socket thật. Tương tự `WebTestClient.bindToController(...)` không chạy Reactor Netty server.

**Chiến lược hợp lý:** unit/reactive tests nhanh và xác định trước; một số integration tests HTTP thật cho stream/cancel; cuối cùng test qua proxy/staging cho các lỗi chỉ xuất hiện ở hạ tầng.

## 4. Spring MVC async: controller trả về nhưng response vẫn đang mở

Spring MVC sử dụng Servlet async processing khi controller trả các kiểu như:
- `Callable<T>`: Spring submit Callable lên `AsyncTaskExecutor`; khi hoàn tất, dispatch lại vào Servlet pipeline.
- `DeferredResult<T>`: ứng dụng quyết định khi nào `setResult` hoặc `setErrorResult`; không tự chạy business task.
- `WebAsyncTask<T>`: wrapper cho Callable với timeout/executor/interceptors.
- `CompletionStage<T>`/`CompletableFuture<T>`: Spring MVC có thể adapt thành async HTTP result.
- `ResponseBodyEmitter`/`SseEmitter`: gửi nhiều chunks/events theo thời gian.
- `StreamingResponseBody`: callback viết bytes vào `OutputStream`; vẫn là blocking writes, chạy trên executor để không chặn Servlet request thread ban đầu.

Ví dụ ngắn:

```java
@GetMapping("/async")
Callable<String> async() {
    return () -> "done";
}
```

Controller trả `Callable` gần như ngay lập tức, nhưng **response chưa chắc đã có body**. Spring MVC sẽ xử lý kết quả ở lần `ASYNC` dispatch tiếp theo. Nếu dùng `MockMvc`, test phải mô phỏng dispatch đó thủ công.

### 4.1. Mẫu MockMvc chuẩn

```java
MvcResult pending = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("done"))
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

Đây là **mảnh test** trong class đã inject `MockMvc` và import statics `MockMvcRequestBuilders.get/asyncDispatch`, `MockMvcResultMatchers.request/status/content`. `request().asyncResult(...)` đợi kết quả async trong thời hạn MockMvc quy định; sau đó `asyncDispatch(...)` kiểm tra response cuối. Nếu chỉ assert body trên `perform(get(...))` ban đầu, bạn có thể đang nhìn một response giả **chưa dispatch**.

### 4.2. DeferredResult không phải @Async

`DeferredResult` không tự sinh thread. Ai đó phải gọi `setResult(...)` hoặc `setErrorResult(...)` và tránh race giữa completion/timeout/client disconnect. Ngược lại, `@Async` trên một service và controller trả HTTP 202 ngay sẽ trở thành **background job rời khỏi request lifecycle**; không được coi là một Servlet async response đang mở.

Nếu dùng `DeferredResult` cho một sự kiện chờ lâu:
- Đặt timeout hữu hạn.
- Đăng ký `onTimeout`, `onError`, `onCompletion`.
- Hủy scheduled task hoặc xóa listener/subscription khi request complete/cancel.
- Kiểm tra `setResult(...)` trả boolean: `false` có thể là result đã set/timeout/complete; không ghi response thêm.
- Dùng một request ID an toàn, không giữ reference của mọi response trong static map vô hạn.

## 5. Streaming trong MVC và WebFlux: định dạng, flush và buffering

Các định dạng thường gặp:

| Định dạng | Producer | Điều client nên kiểm tra |
|---|---|---|
| `text/event-stream` | MVC `SseEmitter` hoặc WebFlux `Flux<ServerSentEvent<T>>` | Data event, ID, thứ tự, heartbeat, reconnect contract |
| `application/x-ndjson` | MVC `StreamingResponseBody` hoặc WebFlux `Flux<T>` | Mỗi dòng là một JSON record hợp lệ, stream kết thúc/đúng framing |
| `application/octet-stream` | MVC `OutputStream` hoặc WebFlux `Flux<DataBuffer>` | Bytes, checksum, file close/cleanup |
| Streaming response body không có format record | Chunks HTTP/2 hoặc chunked HTTP/1.1 | Bytes đến đúng nội dung; không mặc định một chunk=1 event |
| WebSocket | Servlet/WebFlux WebSocket APIs | Handshake, messages, close codes, error/cancel |
| `Mono<T>` / JSON body nhỏ | Một kết quả | Status/body bình thường, không cần StepVerifier streaming |

**Không đồng nhất một Java `onNext` với một TCP packet.** Framework encoder có thể gom buffers; proxy/nginx/compression có thể buffer thêm; HTTP/2 DATA frames không khớp từng JSON object. Tests ứng dụng nên assert **event hoặc record đã decode**, không assert mạng gửi “đúng 3 TCP packets”.

**Headers committed:** nếu server đã gửi status 200 và một chunk, sau đó lỗi xảy ra, nó thường **không thể quay lại thay toàn bộ response thành JSON 500**. Test một stream lỗi giữa chừng nên chấp nhận prefix/EOF hoặc transport failure theo contract, và kiểm tra cleanup/log. Đòi status 500 sau khi đã flush 200 là assertion sai về HTTP.

**Flush:** `StreamingResponseBody` có thể gọi `outputStream.flush()`, nhưng không bảo đảm CDN/browser nhận ngay event nếu proxy buffering/compression còn bật. SSE heartbeat cũng cần gửi các bytes thật; một timer chỉ cập nhật counter không giữ mọi proxy connection sống.

## 6. Khi client ngắt kết nối: điều gì có thể và không thể chắc chắn?

### 6.1. Các cách abort khác nhau

- Client **đã nhận headers**, đọc một dòng SSE, rồi đóng body stream.
- Client hủy `Mono/Flux` trong `WebClient`/`WebTestClient`.
- Browser đóng tab hoặc gọi `AbortController.abort()` khi fetch stream.
- Client gửi TCP FIN hoặc RST, proxy ngắt một HTTP/2 stream.
- Server timeout, pod shutdown hoặc load balancer idle timeout.
- Một reactive operator `take(n)` cancel upstream dù TCP connection vẫn có thể tái sử dụng.

Không phải trường hợp nào cũng dẫn tới **cùng Java exception hoặc cùng HTTP status**. Một Servlet writer có thể chỉ phát hiện client mất khi viết lần kế tiếp, và có thể đã flush dữ liệu vào kernel buffer trước đó. Trong WebFlux, cancellation thường propagates qua reactive subscription, nhưng một callback blocking hoặc side effect đã commit không tự rollback.

### 6.2. Kiểm thử hai điều độc lập

1. **Mức Publisher/resource:** khi bị cancel, `doFinally(CANCEL)` hoặc `usingWhen(asyncCancel)` có chạy không? Đây là **unit test xác định**, có thể dùng `StepVerifier`, không cần network.
2. **Mức network:** khi client đang đọc stream thật đóng kết nối, server có ngừng stream và giải phóng resource không? Dùng `@SpringBootTest(RANDOM_PORT)` và client streaming thực, kiểm tra trạng thái **cuối cùng trong timeout**, không đòi một `IOException` cố định tại mili-giây xác định.

Nếu test chỉ gọi `Thread.sleep(100)` rồi kiểm tra `AtomicBoolean` mà không biết connection đã mở hay chưa, đó là **race condition** trong test. Ưu tiên latch/barrier nhận diện lúc request/subscription thực sự bắt đầu, hoặc đọc được event đầu tiên rồi mới chủ động abort.

## 7. Dự án A: Spring MVC / Servlet async và streaming có thể chạy

Ví dụ tạo một project **Java 17+, Spring Boot 3.3.13, Gradle** gồm:
- `GET /mvc/callable`: phản hồi qua `Callable<String>`.
- `GET /mvc/deferred`: `DeferredResult<String>` được hoàn tất bởi scheduler có quản lý lifecycle.
- `GET /mvc/fail`: exception phát sinh trong Callable, xử lý bởi `@RestControllerAdvice` sau async dispatch.
- `GET /mvc/ndjson`: streaming 30 dòng JSON, flush từng dòng và dọn resource trong `finally`.
- `StreamProbe`: đếm active/finished/write errors; chỉ dùng để test và quan sát đường cleanup.

### 7.1. Cấu trúc

```text
mvc-async-stream-test/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvctest/MvcStreamApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/mvctest/
            ├── MvcAsyncMockTest.java
            └── MvcDisconnectNetworkTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=mvc-async-stream-test
spring.mvc.async.request-timeout=5s
```

Trong production, Servlet async còn cần executor có giới hạn. Mã sau đặt explicit `ThreadPoolTaskExecutor` và `WebMvcConfigurer`, không dùng executor không giới hạn mặc định.

### 7.2. Application, executor, controller và cleanup

**`src/main/java/com/example/mvctest/MvcStreamApplication.java`:**

```java
package com.example.mvctest;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class MvcStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcStreamApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ExecutorBeans {
    @Bean("mvcAsyncExecutor")
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-async-");
        return executor;
    }

    @Bean(destroyMethod = "shutdownNow")
    ScheduledExecutorService deferredScheduler() {
        return Executors.newScheduledThreadPool(1);
    }
}

@Configuration(proxyBeanMethods = false)
class AsyncMvcSupport implements WebMvcConfigurer {
    private final ThreadPoolTaskExecutor executor;

    AsyncMvcSupport(
            @Qualifier("mvcAsyncExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5000L);
    }
}

@Component
class StreamProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger finished = new AtomicInteger();
    final AtomicInteger writeFailures = new AtomicInteger();
}

@RestController
class MvcStreamController {
    private final ScheduledExecutorService scheduler;
    private final StreamProbe probe;

    MvcStreamController(ScheduledExecutorService scheduler,
            StreamProbe probe) {
        this.scheduler = scheduler;
        this.probe = probe;
    }

    @GetMapping("/mvc/callable")
    Callable<String> callable() {
        return () -> {
            Thread.sleep(80);
            return "callable-ok";
        };
    }

    @GetMapping("/mvc/deferred")
    DeferredResult<String> deferred() {
        DeferredResult<String> result = new DeferredResult<>(3000L);
        var scheduled = scheduler.schedule(
                () -> result.setResult("deferred-ok"),
                80, TimeUnit.MILLISECONDS);
        result.onTimeout(() -> result.setErrorResult(
                ResponseEntity.status(504).body("deadline")));
        result.onCompletion(() -> scheduled.cancel(false));
        return result;
    }

    @GetMapping("/mvc/fail")
    Callable<String> fail() {
        return () -> {
            throw new IllegalStateException("simulated async failure");
        };
    }

    @GetMapping(
            path = "/mvc/ndjson",
            produces = "application/x-ndjson")
    StreamingResponseBody ndjson() {
        return output -> {
            probe.active.incrementAndGet();
            try {
                for (int i = 1; i <= 30; i++) {
                    String line = "{\"n\":" + i + "}\n";
                    output.write(
                            line.getBytes(StandardCharsets.UTF_8));
                    output.flush();
                    try {
                        Thread.sleep(60);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IOException(
                                "Stream worker interrupted",
                                interrupted);
                    }
                }
            } catch (IOException writeError) {
                probe.writeFailures.incrementAndGet();
                throw writeError;
            } finally {
                // Kể cả client abort, exception hoặc hoàn tất.
                probe.active.decrementAndGet();
                probe.finished.incrementAndGet();
            }
        };
    }
}

@RestControllerAdvice
class MvcErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<String> handleAsyncError(
            IllegalStateException error) {
        return ResponseEntity.status(503).body("async-error");
    }
}
```

**Vì sao ví dụ này có thể chạy:**
- Chỉ `MvcStreamApplication` là top-level public class đúng tên file. Các class khác package-private ở cùng package, được component scan.
- `ExecutorBeans` định nghĩa executor với pool/queue hữu hạn; `AsyncMvcSupport` ở class khác inject bean, tránh constructor dependency cycle trong chính @Configuration.
- `Callable` của MVC được thực thi trên `mvcAsyncExecutor` và response được dispatch sau khi kết quả hoàn tất.
- `DeferredResult` trả object trước, scheduler đặt result sau; `onTimeout` map 504, `onCompletion` hủy task nếu chưa chạy. `setResult` có thể trả `false` nếu request đã complete, vì thế production không giả định mọi kết quả đặt thành công.
- `StreamingResponseBody` viết chunk bytes; `OutputStream` vẫn là blocking I/O, không nên thực hiện trên một Netty event-loop.
- `StreamProbe.finished` tăng ở `finally`, bất kể 30 dòng được viết đủ hay bị IOException. Vì vậy nó chỉ chứng minh **callback streaming chấm dứt**, không chứng minh client nhận đủ 30 events.
- Trong demo, lỗi `IOException` từ client disconnect có thể được MVC/container ghi log; kiểm thử không phụ thuộc nội dung log cụ thể.
- Scheduler bean có `destroyMethod="shutdownNow"` để không giữ thread sau khi đóng context. Nếu dùng task bất đồng bộ có side effect thật, phải có job durability/lease/retry riêng.

**Lưu ý ứng dụng thực tế:** `Thread.sleep` chỉ mô phỏng delay trong Servlet async worker đã được bố trí; không dùng sleep để đo thời gian flush chính xác hoặc thay timeout production.

## 8. MockMvc kiểm thử Callable, DeferredResult và lỗi sau async dispatch

**`src/test/java/com/example/mvctest/MvcAsyncMockTest.java`:**

```java
package com.example.mvctest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcAsyncMockTest {
    @Autowired
    MockMvc mvc;

    @Test
    void callableIsAsyncAndHasFinalBody() throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/callable"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult("callable-ok"))
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().string("callable-ok"));
    }

    @Test
    void deferredResultIsAsyncAndHasFinalBody() throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/deferred"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult("deferred-ok"))
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-ok"));
    }

    @Test
    void exceptionInsideCallableReachesControllerAdvice()
            throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/fail"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().string("async-error"));
    }
}
```

**Kết quả kỳ vọng**: ba tests pass khi đúng dependencies và môi trường. Không thể khẳng định đã chạy Gradle chỉ từ việc rà soát code.

Điểm rút ra:
- Test 1/2 không được gọi ngay `andExpect(content())` trước `asyncDispatch`.
- Test lỗi cần assert sau dispatch, vì `@ExceptionHandler` xử lý kết quả exception khi request resume.
- MockMvc có thể kiểm tra error handler và MVC mapping, nhưng **không kiểm tra network broken pipe**.
- `request().asyncResult(...)` đợi kết quả async có giới hạn; với test CI chậm, tăng bounded async timeout hợp lý thay vì dùng `Thread.sleep(5000)` cố định.
- Với `DeferredResult` thực tế, bổ sung tests timeout, result/error race và subscription cleanup, nhưng tránh tạo timer vô hạn hoặc dùng static state xuyên test classes.
- Kể cả `@SpringBootTest` trong class này, vì không đặt `RANDOM_PORT` nên không có server socket thật.

### 8.1. Test timeout của DeferredResult cần những gì?

Để test timeout deterministically, nên tách producer và timer thành interface/fake clock có thể điều khiển, hoặc dùng `MockAsyncContext` và testing support của MVC đúng quy trình. Không viết test đợi đúng 3000ms rồi giả định callback sẽ chạy ở cùng millis trên mọi Servlet container/CI.

Ở unit level, có thể gọi `DeferredResult.getResult()` và tự kích hoạt abstraction timeout trong service nếu đã thiết kế policy riêng. Ở integration level, dùng real embedded server `RANDOM_PORT` và timeout ngắn có margin, assert response status/cleanup thay vì deadline tính bằng vài ms.

**Không dùng `@Async` trên một method rồi giả định request trở thành Servlet async**. Nếu controller trả `ResponseEntity.accepted()` sau khi submit task, request đã xong; test `asyncStarted` sẽ không phù hợp.

## 9. Kiểm thử network disconnect với MVC StreamingResponseBody

Để kiểm tra chuyện client thật đọc một dòng rồi đóng kết nối, phải mở **embedded server thực**. `HttpClient.BodyHandlers.ofInputStream()` của Java 17 trả body dạng `InputStream`; test có thể đọc một dòng, sau đó đóng stream để client bỏ phần còn lại.

**`src/test/java/com/example/mvctest/MvcDisconnectNetworkTest.java`:**

```java
package com.example.mvctest;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcDisconnectNetworkTest {

    @LocalServerPort
    int port;

    @Autowired
    StreamProbe probe;

    @Test
    void clientClosesMidStreamAndWriterEventuallyCleansUp()
            throws Exception {
        int before = probe.finished.get();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/mvc/ndjson"))
                .header("Accept", "application/x-ndjson")
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);

        try (InputStream body = response.body()) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            body, StandardCharsets.UTF_8));

            // Chờ bằng cách đọc event thật, không sleep rồi đoán.
            assertThat(reader.readLine()).isEqualTo("{\"n\":1}");

            // Kết thúc try sẽ đóng InputStream trước khi server
            // phát đủ 30 records: client chủ động abort body.
        }

        await().atMost(Duration.ofSeconds(6))
                .untilAsserted(() -> {
                    assertThat(probe.finished.get())
                            .isGreaterThan(before);
                    assertThat(probe.active.get()).isZero();
                });
    }
}
```

**Điều test thực sự chứng minh:** một HTTP response stream thật đã trả status 200, client nhận record đầu, sau đó client **đóng body stream**, và writer có **eventual cleanup** trong thời hạn test. Test **không assert** `writeFailures==1`, vì Java HttpClient/OS/kernel/proxy buffering hoặc thời điểm đóng có thể khiến server ghi thêm hoặc hoàn tất trước khi phát hiện disconnect.

**Bất định hợp lệ:** một request streaming chỉ có 30 records × 60ms, nên `finally` cũng có thể chạy bởi nguồn **hoàn tất bình thường**. Do đó assertion `finished` ở đây chủ yếu kiểm tra **không bị treo/không giữ resource mãi sau abort**, chứ không phải bằng chứng khách đã gây đúng một `IOException`. Nếu muốn khẳng định server đã quan sát transport abort, cần probe/transport hooks rõ ràng, stream dài hơn, bounded signal và kiểm thử tích hợp đúng connector.

Không nên mở một stream vô hạn rồi dùng `await().until(active==0)` nếu adapter không phát hiện client close ngay: test có thể treo nếu còn một worker chờ I/O. Luôn đặt timeout ở client/test và có cleanup trong `finally`.

### 9.1. Test thủ công với curl

Chạy:

```bash
gradle bootRun
```

Ở terminal khác:

```bash
curl --no-buffer --max-time 0.3 \
  http://localhost:8080/mvc/ndjson
```

`--no-buffer` yêu cầu curl không buffer output, `--max-time` giới hạn thời gian, nhưng số dòng hiển thị thay đổi theo CPU/network và không phải stdout bất biến. HTTP status ban đầu có thể là 200 trước khi curl timeout/abort, không có HTTP 500 để assert. Quan sát server `StreamProbe`/logs và kích thước đã gửi để giải thích kết quả.

## 10. SseEmitter/ResponseBodyEmitter: cleanup khi timeout hoặc mất client

MVC `SseEmitter` phù hợp SSE. `ResponseBodyEmitter` dành cho nhiều dữ liệu được serialize/flush dần. Các callbacks thường dùng:

```java
// Mảnh code trong MVC controller/service có quản lý emitter.
SseEmitter emitter = new SseEmitter(30_000L);

emitter.onCompletion(() -> removeFromRegistry(emitter));
emitter.onTimeout(() -> removeFromRegistry(emitter));
emitter.onError(error -> removeFromRegistry(emitter));

return emitter;
```

Mảnh này **không chạy độc lập** vì `removeFromRegistry` là method ứng dụng phải tự viết. Trong production:
- Cleanup phải idempotent vì completion, timeout và error callbacks có thể đến qua các đường gần nhau.
- Nếu một publisher/scheduler liên tục gọi `emitter.send(...)`, khi client mất cần dispose subscription/hủy scheduled future tương ứng.
- Theo Spring MVC docs, khi `emitter.send(...)` ném `IOException` do client đi mất, **không cần và không nên gọi `complete()` hoặc `completeWithError()` thêm chỉ để “báo lỗi”**; container có cơ chế báo lỗi async và MVC sẽ xử lý dispatch. Cleanup resource ứng dụng vẫn cần thực hiện idempotent.
- Nếu SSE dựa trên event broker, subscriber phải được deregister để không giữ reference vào emitter đã đóng.
- Heartbeat có thể là SSE comment hoặc một event nhẹ phù hợp, và phải qua flush/proxy để có ý nghĩa network.
- `SseEmitter` không làm Servlet response writes thành non-blocking; cần bounded executor và kiểm soát slow clients.

**Không test disconnect bằng cách chỉ gọi `emitter.complete()`**: đây là server chủ động kết thúc bình thường, khác browser ngắt kết nối. Cũng không gọi `completeWithError(new IOException(...))` rồi coi đã chứng minh TCP reset.

## 11. Dự án B: Spring WebFlux SSE, NDJSON, timeout và cancellation

Dự án độc lập dùng **Spring Boot 3.3.13 + Java 17+ + `spring-boot-starter-webflux`** và Reactor Netty server. Không thêm `spring-boot-starter-web` trong project này, để không chuyển runtime sang MVC.

Endpoints:
- `GET /flux/sse`: SSE vô hạn, mỗi khoảng thời gian tạo một `tick-N`, đếm subscription/cancel.
- `GET /flux/ndjson`: phát ba JSON records theo thời gian, rồi complete.
- `GET /flux/timeout`: một tác vụ chậm bị timeout, map thành 504 **trước khi commit response**.
- `StreamService`: nguồn `Flux.interval` tách khỏi HTTP để unit test bằng `StepVerifier.withVirtualTime`.

### 11.1. Cấu trúc project

```text
webflux-stream-test/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/fluxtest/ReactiveStreamApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/fluxtest/
            ├── ReactiveStreamingIntegrationTest.java
            └── ReactiveCancellationUnitTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
spring.application.name=webflux-stream-test

# Ví dụ minh họa; production cần cân đối body/buffer/time limits.
spring.codec.max-in-memory-size=256KB
```

### 11.2. WebFlux controller và probe cho cancel

**`src/main/java/com/example/fluxtest/ReactiveStreamApplication.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveStreamApplication.class, args);
    }
}

@Service
class StreamService {
    Flux<Long> ticks(Duration period) {
        return Flux.interval(period);
    }
}

@Component
class ReactiveProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger subscriptions = new AtomicInteger();
    final AtomicInteger cancellations = new AtomicInteger();
}

@RestController
class ReactiveStreamController {

    private final StreamService service;
    private final ReactiveProbe probe;

    ReactiveStreamController(StreamService service,
            ReactiveProbe probe) {
        this.service = service;
        this.probe = probe;
    }

    @GetMapping(
            path = "/flux/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> sse() {
        return service.ticks(Duration.ofMillis(60))
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .data("tick-" + i)
                        .build())
                .doOnSubscribe(s -> {
                    probe.subscriptions.incrementAndGet();
                    probe.active.incrementAndGet();
                })
                .doFinally(signal -> {
                    probe.active.decrementAndGet();
                    if (signal == SignalType.CANCEL) {
                        probe.cancellations.incrementAndGet();
                    }
                });
    }

    @GetMapping(
            path = "/flux/ndjson",
            produces = "application/x-ndjson")
    Flux<Tick> ndjson() {
        return service.ticks(Duration.ofMillis(30))
                .take(3)
                .map(i -> new Tick(i));
    }

    @GetMapping("/flux/timeout")
    Mono<ResponseEntity<String>> timeout() {
        return Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> ResponseEntity.ok("late"))
                .timeout(Duration.ofMillis(100))
                .onErrorResume(TimeoutException.class,
                        error -> Mono.just(
                                ResponseEntity.status(504)
                                        .body("deadline")));
    }
}

record Tick(long index) {}
```

**Giải thích:**
- `Flux.interval` sinh dữ liệu theo thời gian **khi được subscribe**, không gọi `subscribe()` trong controller. WebFlux server quản lý subscription để ghi response.
- SSE là một HTTP response stream với encoding `text/event-stream`, không tự tạo một HTTP request mới cho mỗi tick.
- `doOnSubscribe` đo khi upstream được subscribe, không phải chỉ khi MVC/WebFlux controller method được invoke.
- `doFinally` có thể chạy khi upstream complete/error/cancel; `ReactiveProbe.cancellations` chỉ tăng với `SignalType.CANCEL` ở operator position này.
- `/flux/sse` cố ý vô hạn để test hủy sau hai messages; production phải có max session age, heartbeat/idle timeout và xử lý slow subscriber.
- `/flux/ndjson` có đúng ba records `{"index":0}`, `{"index":1}`, `{"index":2}` nếu codec ghi record Jackson như dự kiến.
- `/flux/timeout` dùng `timeout` **trước khi phát response**, nên có thể trả 504 có chủ đích. Khi đã gửi một vài chunks thì không thể đơn giản đổi status thành 504.
- `record Tick(long index)` là Java record package-private; Jackson trong Spring Boot 3.3 hỗ trợ record serialization/deserialization.
- Các counters chỉ dùng lab. Một counter “cancellations” không tự chứng minh nguyên nhân là browser đóng tab; test phải xác định ai đã cancel.

## 12. WebTestClient với server thật: kiểm tra streaming và cancel

**`src/test/java/com/example/fluxtest/ReactiveStreamingIntegrationTest.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveStreamingIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveProbe probe;

    @Test
    void finiteNdjsonContainsThreeRecordsAndCompletes() {
        FluxExchangeResult<Tick> result = client.get()
                .uri("/flux/ndjson")
                .accept(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0),
                        new Tick(1),
                        new Tick(2))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void clientCancellationReachesRealSseServer() {
        int before = probe.cancellations.get();

        FluxExchangeResult<String> result = client.get()
                .uri("/flux/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(String.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext("tick-0", "tick-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        // Network disconnect -> server cancellation may be async.
        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    assertThat(probe.cancellations.get())
                            .isGreaterThan(before);
                });
    }

    @Test
    void preCommitTimeoutMapsToGatewayTimeout() {
        client.get()
                .uri("/flux/timeout")
                .exchange()
                .expectStatus()
                .isEqualTo(504)
                .expectBody(String.class)
                .isEqualTo("deadline");
    }
}
```

**Kết quả kỳ vọng:** ba tests pass khi WebFlux server/client/codec đúng và machine đủ tài nguyên. Mã đã được rà soát tĩnh, **không tuyên bố Gradle đã được thực thi**. Đọc những điểm đặc biệt:

1. `RANDOM_PORT` + `@AutoConfigureWebTestClient` tạo **HTTP network client thật**. `WebTestClient.bindToController(...)` sẽ không chứng minh disconnect Netty.
2. `returnResult(Tick.class)` trả `FluxExchangeResult<Tick>` để test **body có nhiều records**. Không gọi `expectBodyList`/`collectList()` trên stream vô hạn.
3. `StepVerifier.create(...).expectNext(...).expectComplete().verify(Duration)` assert cả giá trị, thứ tự và completion hữu hạn.
4. `thenCancel()` làm test chủ động dừng consuming body, khác với server `onComplete`. Khi đang đọc HTTP stream thực, việc này thường đóng/hủy client response subscription; server sẽ nhận cancellation khi transport phát hiện.
5. `ReactiveProbe.cancellations` ở server là tín hiệu bất đồng bộ nên dùng Awaitility với giới hạn 5 giây. Không `Thread.sleep(200)` rồi assert tức thời.
6. Bài test cancellation là **end-to-end integration assertion nhạy với HTTP client, server connector và môi trường**. Nếu chạy qua khác proxy/adapter, việc mapping cancel/error hoặc thời điểm đóng có thể khác. Không sửa assertion thành “chắc chắn luôn cancel trong 1 ms” để có vẻ deterministic.
7. `/flux/timeout` có timeout mapping trước khi response committed, vì thế status 504 có ý nghĩa. Nếu source đã phát một SSE event thì error sau đó có thể chỉ kết thúc stream/error, không đổi status.

**Nếu integration test ngắt kết nối flake:** thu thập HTTP client/probe state, thời điểm subscription, timestamp của event đầu tiên, server termination signal, connection/proxy logs. Đặt bounded wait và tách assertion “request đã bắt đầu” khỏi assertion “server đã cleanup”. Không che flake bằng `Thread.sleep(5000)` không có điều kiện.

## 13. Unit tests với StepVerifier: virtual time và cancel không cần socket

Network tests có độ trễ và nondeterminism. Những logic **thuần Reactor** như delay, timeout, retry, sequence, cleanup nên được kiểm tra nhanh bằng `StepVerifier` và khi thích hợp `withVirtualTime(...)`.

**`src/test/java/com/example/fluxtest/ReactiveCancellationUnitTest.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.awaitility.Awaitility.await;

class ReactiveCancellationUnitTest {

    @Test
    void virtualTimeVerifiesTicksAndCancellation() {
        StreamService service = new StreamService();
        AtomicReference<SignalType> last =
                new AtomicReference<>();

        StepVerifier.withVirtualTime(
                        () -> service.ticks(
                                        Duration.ofSeconds(1))
                                .doFinally(last::set))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(0L, 1L)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(SignalType.CANCEL, last.get());
    }

    @Test
    void usingWhenExecutesCancelCleanupExactlyOnce() {
        AtomicInteger cleaned = new AtomicInteger();

        Flux<Long> stream = Flux.usingWhen(
                Mono.just("lease"),
                lease -> Flux.interval(Duration.ofMillis(20)),
                lease -> Mono.fromRunnable(
                        cleaned::incrementAndGet),
                (lease, error) -> Mono.fromRunnable(
                        cleaned::incrementAndGet),
                lease -> Mono.fromRunnable(
                        cleaned::incrementAndGet));

        StepVerifier.create(stream)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        await().atMost(Duration.ofSeconds(2))
                .until(() -> cleaned.get() == 1);
        assertEquals(1, cleaned.get());
    }
}
```

**Lý giải:**
- `withVirtualTime(Supplier<Publisher>)` đòi **tạo Flux bên trong lambda** để `Flux.interval` sử dụng virtual scheduler. Tạo Flux ở ngoài lambda rồi return lại có thể khiến virtual time không hoạt động.
- `thenAwait(Duration.ofSeconds(2))` tăng thời gian ảo, test không phải chờ thật 2 giây cho interval logic.
- `thenCancel()` assert cancellation ở mức Publisher; nó **không mở TCP connection**.
- `Flux.usingWhen` có ba đường cleanup: normal completion, error, cancellation. Trong test ta chủ động cancel sau hai phần tử và đợi callback chạy.
- `cleaned==1` giúp bắt lỗi cleanup bị bỏ qua hoặc gọi trùng trong demo. Nếu resource cleanup thực là async I/O, assert eventual state sau khi cleanup Publisher kết thúc; không dùng một boolean set ngay ở method call rồi khẳng định file đã xóa.
- Mọi `verify(...)` có **deadline hữu hạn**. `StepVerifier.verifyComplete()` không truyền timeout có thể treo vô hạn khi test lỗi; ưu tiên `expectComplete().verify(Duration)`.
- Với `Flux.usingWhen` resource là chuỗi `"lease"` in-memory, chỉ minh họa contract. Đối với file/socket/JDBC connection cần cleanup tương ứng trên **tất cả** signal paths và crash recovery cho process-kill.

## 14. Khi nào StepVerifier.thenCancel thực sự chứng minh client disconnect?

Ba mẫu tương tự cú pháp nhưng khác tầng:

```java
// A. Unit-level: KHÔNG có HTTP socket.
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

```java
// B. Network-level: body của WebTestClient kết nối server thật.
FluxExchangeResult<String> result = realClient.get()
        .uri("/flux/sse")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Mẫu A chỉ kiểm tra Reactor cancellation trên Flux trong test JVM. Mẫu B hủy **HTTP response consumer**, có thể phát tín hiệu đóng/hủy stream tới server qua network stack. Để có bằng chứng đầu cuối, thêm server probe và bounded Awaitility assertion như mục 12. Các fragments này không phải file test standalone; `realClient` phải được khởi tạo qua `WebTestClient.bindToServer` hoặc inject trong `@SpringBootTest(RANDOM_PORT)`.

**Trường hợp C: Browser đóng tab** có thể khác cả hai. Browser/proxy/socket I/O, HTTP/2 stream resets, idle timeout và retry/reconnect cần test trong staging/real browser khi đây là rủi ro chính.

Không định nghĩa metric `client_disconnects` chỉ dựa trên mọi `doFinally(CANCEL)`: `take(n)`, timeout operator và server-side policy cũng có thể cancel. Dùng thông tin từ HTTP connector và lý do hủy được phép ghi để phân loại.

## 15. Kiểm thử backpressure, slow client và buffering

**Backpressure** của `Flux` là cơ chế demand giữa Subscriber và Publisher. Tuy nhiên:
- Java object phát ra không trùng một network chunk.
- TCP/window flow control, Reactor prefetch và HTTP codec buffer có thể làm producer sinh trước nhiều item.
- Servlet `StreamingResponseBody` là blocking writer; nếu client chậm, thread có thể bị giữ khi `write/flush`.
- SSE/NDJSON vô hạn với client chậm có thể tạo queue tích tụ nếu dùng `onBackpressureBuffer()` không giới hạn.
- `WebTestClient` tích lũy toàn body bằng `expectBodyList` trên stream vô hạn sẽ treo hoặc làm cạn memory.

### 15.1. Test demand ở unit level

```java
Flux<Integer> source = Flux.range(1, 100)
        .doOnRequest(n -> recordRequest(n));

StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

Đoạn này là **mảnh minh họa**, `recordRequest(long)` là callback do ứng dụng/test định nghĩa. `StepVerifier.create(source,0)` bắt đầu với demand 0, `thenRequest(2)` gửi yêu cầu 2 items. Với một source khác có `flatMap`/`publishOn`, internal operators có thể prefetch nên con số request upstream không nhất thiết trùng demand của test subscriber.

### 15.2. Test slow network client

Không khẳng định performance chỉ bằng một `Flux.delayElements`. Khi cần test reader chậm:
1. Server phát event đều hoặc theo nguồn hot mô phỏng.
2. Client đọc từng record có controlled delay; có thể dùng JDK InputStream hoặc Reactor client với demand hạn chế.
3. Đo queue occupancy, memory/direct buffers, thời gian blocked writes và event loss policy.
4. Đặt **bounded total duration và max events** để test không treo.
5. Assert behavior theo yêu cầu nghiệp vụ: drop-oldest/latest, disconnect slow subscriber, bounded backpressure hay durable replay.

Trong thực tế NGINX buffering/compression có thể giấu slow client khỏi application tạm thời. Nếu cần chứng minh hệ thống qua proxy không làm tràn memory, phải có riêng test staging proxy/ingress — không chỉ localhost Reactor Netty.

## 16. DataBuffer: cleanup đúng trên success/error/cancel

Trong WebFlux, `DataBuffer` đôi khi bọc Netty pooled/ref-counted buffers. Lỗi phổ biến là giữ `DataBuffer` sau callback đã kết thúc hoặc bỏ buffer qua `filter`/`skip` mà không release.

Spring Framework DataBuffer docs yêu cầu:
- Nếu application là consumer cuối của buffer, release qua `DataBufferUtils.release(buffer)` khi đọc xong.
- Nếu operator discard/cancel các buffers đang giữ, thêm `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở pipeline phù hợp.
- Nếu buffer được giữ qua asynchronous boundary, cần `retain/release` đúng owner contract; double-release cũng gây lỗi.
- Dùng `DataBufferUtils.join(source, maxByteCount)` khi thật sự cần aggregate và có byte limit; nếu stream lớn, ưu tiên streaming.
- Nếu dùng encoder/WebFlux server `response.writeWith(...)`, server response writer thường chịu trách nhiệm consume/release outgoing DataBuffer theo contract. **Không release outgoing buffer trước khi server viết**.
- Với file stream, lifecycle cần đóng file channel khi cancel/error. `DataBufferUtils.read(path,...,bufferSize)` có contract quản lý channel trên terminal/cancel.

**Ví dụ minh họa viết file download, không phải class standalone:**

```java
// Trong WebFlux handler có Path path đã được kiểm tra quyền,
// ServerHttpResponse response và DataBufferFactory tương ứng.
Flux<DataBuffer> content = DataBufferUtils.read(
        path, response.bufferFactory(), 8192);

return response.writeWith(content);
```

Nếu path là temp file do ứng dụng sở hữu, cần dùng `Mono.usingWhen` hoặc lifecycle manager để **xóa file khi send hoàn tất, lỗi và hủy**, có thể offload `Files.deleteIfExists` lên boundedElastic. Nhưng nhớ: **SIGKILL/crash sẽ không chạy cleanup callbacks**; cần sweeper/orphan reconciliation.

Đừng viết:

```java
// KHÔNG AN TOÀN:
return DataBufferUtils.join(rawDataBuffers)
        .map(buffer -> expensiveWork(buffer))
        .doOnNext(buffer -> buffer.release());
```

Mã trên là **pseudocode sai**: `join` không có max byte cap, kiểu result của `map` không chắc là buffer, `DataBuffer` interface không có `release()` method theo cách viết, và cleanup không được đảm bảo ở mọi đường. Dùng `DataBufferUtils.release` với owner/scope rõ và test cả cancel/error, không copy đoạn này.

### 16.1. Test cleanup bị race

Ví dụ một upload được client hủy đúng lúc server chuẩn bị commit:
- Thông báo client abort có thể tới trước/sau disk write.
- File temp có thể đã được tạo nhưng chưa được đăng ký vào cleanup manager.
- `usingWhen` cleanup có thể chạy khi reactive subscription bị cancel, nhưng không chạy nếu app tách một `subscribe()` ra ngoài.
- Nếu commit đã thành công, cancel không tự rollback database/file đã public.
- Nếu app nhận body streaming và release không đúng, Netty direct memory có thể tăng trong load test.

Test nên kiểm tra **state cuối cùng** (staging file không còn, permanent file chỉ tồn tại sau atomic commit, không orphan), dùng bounded polling và idempotency. Không assert thứ tự chính xác giữa socket FIN và callback CPU scheduler vì các sự kiện đó có race hợp lệ.

## 17. Async, streaming và HTTP status khi lỗi xảy ra giữa chừng

| Thời điểm lỗi | HTTP status/body có thể thế nào? | Test nên assert |
|---|---|---|
| Trước headers/commit | Có thể map sang 4xx/5xx + ProblemDetail | Status/error body + observation |
| Sau headers nhưng chưa ghi body | Status có thể đã committed | Không mặc định đổi thành 500 |
| Sau chunk SSE/NDJSON đầu tiên | Client nhận prefix, rồi stream lỗi/EOF | Prefix hợp lệ, terminal/cleanup, logs |
| Khi client đã đóng | Server có thể thấy IOException/CANCEL hoặc phát hiện muộn | Eventual cleanup, không exception class cố định |
| Downstream HTTP call đã xử lý nhưng response mất | Client thấy timeout/connection reset | Idempotency, reconciliation, không retry blind |
| Codec JSON lỗi giữa streamed records | Có thể hủy response/chỉ gửi một phần | Error path/partial data/cleanup, không đòi JSON 500 mới |

**Ví dụ chống pattern sai:** đang gửi SSE 200, gặp exception, rồi cố `ResponseEntity.status(500)` để thay response. Khi response đã committed, framework có thể không thể thay headers/status. Ứng dụng nên terminate stream, log an toàn, hoặc gửi application-level error event **nếu protocol còn có thể viết và policy cho phép**, rồi close. Không cố che connection failure bằng một chuỗi text nói “HTTP 500” trong SSE mà dashboard hiểu là status 500.

### 17.1. Kiểm thử fault injection hữu ích hơn sleep

Thay vì chờ random 200ms rồi cắt mạng:
1. Dùng `CountDownLatch` hoặc `Sinks.One` để biết server đã vào handler.
2. Đợi client đọc được **event đầu** thật.
3. Chủ động close/cancel response consumer.
4. Đợi bounded cho cleanup signal.
5. Kiểm tra trạng thái tài nguyên sau cùng và xác định không còn task/queue orphan.
6. Lặp dưới concurrency nhỏ rồi tăng trong stress/chaos suite.

Nếu test muốn tiêm lỗi sau event số 2, source có thể `concatWith(Mono.error(...))`, miễn đảm bảo status đã committed hoặc event đã thực sự flush. Trong MockMvc, không có mạng nên kết quả status/committed-state không chứng minh behavior socket thật.

## 18. Timeout: phân biệt bốn deadline

Một request streaming/async thường chịu nhiều deadline:

| Deadline | Ví dụ | Tác động |
|---|---|---|
| MVC async request timeout | `spring.mvc.async.request-timeout=5s`, `DeferredResult(3000L)` | Container/MVC request async lifecycle |
| Reactive Publisher timeout | `Mono.timeout(Duration)` | Phát timeout error/cancel upstream theo pipeline |
| HTTP client response timeout | Reactor Netty `responseTimeout`, JDK client timeout | Client không đợi mãi |
| Test verification timeout | `StepVerifier.verify(Duration)`, Awaitility `atMost` | Test suite không treo vô hạn |

Chúng **không thay thế nhau**. Một test có `StepVerifier.verify(Duration.ofSeconds(2))` không tự đặt server processing timeout. Một client timeout 1s không ngăn downstream đã nhận request tiếp tục ghi DB. Một Servlet MVC async timeout không bảo đảm giải phóng blocking JDBC query ngay lập tức.

Trong test:
- Dùng một timeout verification **lớn hơn** timeout nghiệp vụ với margin cho CI.
- Không assert chính xác 100ms trên wall-clock nếu scheduler/network có jitter.
- Test callback cleanup bằng bounded eventual assertion, không bằng một `Thread.sleep(100)`.
- Nếu dùng `withVirtualTime`, tạo publisher trong supplier sau khi virtual scheduler được thiết lập.
- Không chuyển toàn bộ real network tests thành virtual time vì sockets/TCP không chạy theo Reactor virtual clock.

## 19. Client disconnect không phải transaction rollback

Một nghiệp vụ tạo đơn hàng có thể đã ghi DB ngay trước khi client cancel response. Nếu client retry với cùng request mà server không có idempotency, bạn có thể tạo hai đơn.

```text
Client A                   Server B                   Database
   │ POST /orders             │                           │
   ├─────────────────────────►│                           │
   │                          ├── INSERT order ──────────►│
   │                          │◄── COMMIT ✓ ───────────────┤
   │    client abort          │                           │
   ╳                          ├── response write fails    │
   │                          │                           │
   ├── retry same POST ──────►│                           │
   │                          └── insert duplicate? ─────►│
```

**Cancellation là best effort** với công việc có thể hủy; nó không rollback side effects đã commit và không bảo đảm remote server/DB hiểu tương ứng. Tests cần tách:
- **Network cancellation test:** server dừng stream/cleanup sau client abort.
- **Business idempotency test:** hai attempts cùng key chỉ tạo **một** business object; transaction/outbox/inbox/unique constraint theo domain.
- **Background-work test:** nếu HTTP trả 202 trước job hoàn tất, task có durable handoff, retry/recovery sau SIGKILL.
- **Resource test:** temporary files/locks/subscriptions được dọn dù client ngắt.

Một status 200 ghi trước connection reset không chứng minh caller đã nhận đủ response; một `doFinally(CANCEL)` không chứng minh database chưa commit. Đây là hai lớp kiểm thử khác nhau.

## 20. Observability cho async, stream và disconnect

Một dashboard server chỉ đo completed HTTP responses có thể bỏ sót những kết nối bị hủy trước khi observation kết thúc, nhất là khi JVM bị kill. Nên kết hợp:

- HTTP request duration, status/outcome, 5xx/499 (nếu proxy cung cấp), aborted connection count ở proxy/server.
- Active MVC async requests, streaming executor pool/queue/blocked writes.
- Active WebFlux subscriptions, `ON_COMPLETE`/`ON_ERROR`/`CANCEL`, thời gian giữ stream.
- SSE/NDJSON message emitted **và** delivered/acknowledged nếu application protocol hỗ trợ; không đánh đồng hai chỉ số.
- Reactor Netty pooled/direct memory, DataBuffer leak detection trong test/staging.
- Client-side latency/errors/timeouts và downstream call spans.
- Resource cleanup durations, temp files còn sót, orphan subscriptions/timers.
- Queue overflow và slow consumer policy: drops, replay requests, rejected connects.
- HTTP/2 stream resets, ingress/nginx buffering/idle timeouts.
- Thread pool saturation và Servlet async timeouts.

**Không dùng raw request URI/user ID/token làm metric label có cardinality lớn**. Với stream có personal data, không log nguyên payload/body hoặc cookie/Authorization headers. Client disconnect là một sự kiện phổ biến; không nên ghi đầy đủ stack trace cho mọi tab browser đóng.

Đối với metrics phân biệt nguyên nhân:
- Application-level `CANCEL` do `take(2)`.
- Client response consumer cancel.
- Transport EOF/RST hoặc proxy timeout.
- Server/app shutdown.
- Deadline enforced/timeout.

Các nguyên nhân này có thể trùng signal ở Reactor. Muốn phân biệt tốt hơn phải kết hợp instrumentation ở client/proxy/server; **đừng đoán chỉ từ một tag**.

## 21. Error cases khi test bị flaky

| Triệu chứng | Nguyên nhân có thể | Cách sửa test |
|---|---|---|
| MockMvc body rỗng dù controller trả Callable | Chưa `asyncDispatch` | Assert asyncStarted/result rồi dispatch |
| `asyncStarted()` false | Controller trả synchronous value hoặc @Async job detached | Kiểm tra return type và request lifecycle |
| DeferredResult test thỉnh thoảng timeout | Scheduler chạy trễ, timeout quá sát, shared state | Bounded wait, fake clock hoặc event-controlled producer |
| MockMvc disconnect test luôn pass | MockMvc không có socket | Chuyển sang RANDOM_PORT và real client |
| SSE test treo vì `expectBodyList` | Stream vô hạn, client chờ complete | `returnResult(...).getResponseBody()` + `thenCancel` |
| WebTestClient cancel nhưng server probe không tăng ngay | Transport cancellation đến bất đồng bộ | Đợi bounded; kiểm tra thực sự bind live server |
| Server vẫn gửi một vài events sau client abort | OS/codec/proxy buffering | Không assert immediate stop, kiểm tra cleanup cuối |
| `IOException` khác nhau giữa Tomcat/Jetty/Netty | Runtime/OS/socket behavior khác | Không hardcode exception class cho abort |
| Status 200 rồi stream lỗi nhưng test đòi 500 | Headers đã committed | Assert prefix + terminal error/close |
| `withVirtualTime` chờ thật hoặc không emit | Flux tạo ngoài supplier, custom Scheduler | Tạo timed operators trong lambda |
| Test dùng `verifyComplete()` và treo CI | Không có verification timeout, Flux không complete | `expectComplete().verify(Duration)` |
| `StepVerifier.thenCancel` local pass, client vẫn giữ socket | Test không kết nối server | Viết network integration test riêng |
| DataBuffer leak khi cancel | Filter/flatMap giữ buffer không release | `doOnDiscard`, usingWhen, owner policy |
| MVC streaming làm đầy thread pool | Writer blocking, executor không bounded | Cấu hình MVC async executor, slow client test |
| Rate test không ổn định theo milliseconds | CI/network scheduler jitter | Assert order/upper bounds có margin |
| Test timeout 504 nhưng nhận 200 | Timeout áp sau data emitted, fallback khác | Kiểm tra placement `timeout`/`onErrorResume` |
| HTTP/2/proxy staging khác localhost | Buffer/ingress keepalive/compression | Thêm e2e test qua proxy |
| Sau test process không exit | Scheduler/executor thread chưa shutdown | Bean managed lifecycle, close clients/resources |
| Retry sau disconnect gây duplicate | Không có idempotency/reconciliation | Test key uniqueness + business state |
| Metrics thiếu aborted request | Server observation chưa stop hoặc proxy reject trước app | Kết hợp client/proxy metrics |
| Test concurrency có leaks | Dùng static maps/sinks không cleanup | Per-test resources, `@AfterEach`, bounded polls |

## 22. Ma trận kiểm thử nên có trước khi release

| Nhóm | Trường hợp | Điều cần chứng minh |
|---|---|---|
| MVC async | `Callable` hoàn tất bình thường | asyncStarted → asyncResult → asyncDispatch → 200/body |
| MVC async lỗi | Callable ném exception | Advice/status mapping sau dispatch |
| MVC DeferredResult | setResult trước deadline | Response được dispatch, không treo |
| MVC timeout | Producer không trả | Timeout/error path, callback cleanup |
| MVC SSE | Gửi nhiều events | IDs/data/format và đúng thứ tự |
| MVC NDJSON | Client đọc nhiều lines | Mỗi dòng JSON hợp lệ, flush hữu hạn |
| MVC client abort | Đọc event 1 rồi close body | Writer/registration cleanup eventual; không giả định IOException type |
| WebFlux finite stream | Ba NDJSON objects | Đủ value/order và onComplete |
| WebFlux infinite SSE | Đọc hai events rồi cancel | Client consumer cancel, server eventually releases subscription |
| Reactor virtual time | 2 ticks sau 2 giây ảo | Không chờ thật, đúng thứ tự |
| Reactor cleanup | usingWhen cancel | Cleanup đúng một lần |
| WebFlux timeout | Mono chậm hơn budget | HTTP 504 trước response commit |
| Stream partial error | Lỗi sau event đầu | Partial body/EOF/error, không đòi đổi status |
| WebFlux DataBuffer | Cancel khi đang stream | Release đúng, không tăng direct memory |
| Slow client | Client đọc rất chậm | Memory/queue bound, policy drop/replay rõ |
| Upload abort | Đóng request body giữa chừng | Temp stage cleanup, không commit file partial |
| Download abort | Đóng response sớm | File channel/subscription cleanup |
| Downstream abort | Caller mất kết nối lúc WebClient đang chờ | Cancel best effort, không suy rollback upstream |
| Client retry | Mất response sau DB commit | Idempotency/unique key tránh duplicate |
| Proxy/ingress | Streaming qua NGINX/CDN/HTTP2 | Không bị buffer/timeout ngoài ý muốn |
| Graceful shutdown | SIGTERM giữa SSE/request | Bounded close/reconnect, không treo deployment |
| Observability | Error, complete, cancel, 499/5xx | Đúng layer, không lộ sensitive payload |

Các unit tests nên chạy ở mỗi commit. Network abort tests có thể nằm trong integration suite với retry **có kiểm soát** khi CI thiếu ổn định; đừng dùng retry vô hạn che lỗi. Proxy/ingress/chaos tests nên chạy ở staging hoặc trước release đối với các API streaming quan trọng.

## 23. Checklist thực hành và sản phẩm

- [ ] Chọn đúng Servlet MVC hay WebFlux runtime, không import nhầm APIs.
- [ ] MVC async tests dùng `asyncStarted` + `asyncResult` + `asyncDispatch`.
- [ ] Không coi `@Async` job sau 202 là một HTTP async request đang mở.
- [ ] Dùng `@SpringBootTest(RANDOM_PORT)` khi kiểm tra socket, flush và client disconnect.
- [ ] SSE/NDJSON tests dùng `FluxExchangeResult` + `StepVerifier`, không gom stream vô hạn.
- [ ] Assert finite stream có completion, infinite stream có cancellation và cleanup.
- [ ] Đặt verification/await/test deadlines rõ ràng.
- [ ] Tạo timed Flux bên trong supplier của `withVirtualTime`.
- [ ] Khi kiểm tra client abort, đợi client nhận event đầu rồi mới close/cancel.
- [ ] Phân biệt Publisher CANCEL ở local test và transport disconnect thật.
- [ ] Không assert loại/timing `IOException` cố định cho client abort Servlet.
- [ ] Có cleanup idempotent cho SseEmitter/ResponseBodyEmitter/DeferredResult.
- [ ] Có bounded executor cho MVC blocking streaming writes.
- [ ] DataBuffer owners rõ ràng, release trên success/error/cancel, không double release.
- [ ] Không gửi 500/ProblemDetail sau khi HTTP headers đã committed.
- [ ] Timeout phía client, server, Publisher và test là những giới hạn riêng.
- [ ] Có test concurrent slow clients, queue/backpressure và memory/disk limits.
- [ ] Có idempotency/reconciliation cho side effect hoàn tất trước khi response mất.
- [ ] Test resource cleanup cả khi JVM crash bằng orphan sweeper/recovery.
- [ ] Test staging qua gateway/HTTP2/ingress nếu production có tầng đó.
- [ ] Metrics/log/tracing phân biệt complete/error/cancel và redaction PII/secrets.

## 24. Câu hỏi tự kiểm tra

**1. Khi MockMvc test `Callable<String>`, vì sao không assert body ngay ở lần perform GET đầu tiên?**  
Vì MVC chuyển sang Servlet async; controller đã trả Callable nhưng response cuối chưa dispatch. Cần kiểm tra asyncStarted/asyncResult rồi `asyncDispatch`.

**2. `@Async void` service chạy sau khi controller trả HTTP 202 có phải một HTTP in-flight request không?**  
Không. HTTP response đã kết thúc, job tách lifecycle; muốn durability cần DB/queue/lease/retry thay vì chỉ trông graceful shutdown.

**3. `WebTestClient.bindToController(...)` có kiểm tra được broken pipe khi browser đóng tab không?**  
Không. Nó dùng mock server; phải mở embedded server trên random port và cho client đóng/hủy response stream thật.

**4. Tại sao không `collectList()` trên `Flux.interval` SSE vô hạn?**  
Vì Flux không complete; việc gom có thể không bao giờ trả và tăng memory. Dùng `FluxExchangeResult` và `StepVerifier.thenCancel`.

**5. Khi `StepVerifier.thenCancel()` trên một Flux thuần, có chứng minh TCP socket đã đóng không?**  
Không. Nó chỉ hủy subscription trong JVM test. Chỉ khi Flux thuộc HTTP client đang nối server thật và có server-side evidence mới là end-to-end test.

**6. Server có thể vẫn gửi một số chunks sau khi client abort không?**  
Có. Kernel/proxy buffering và thời điểm phát hiện disconnect bất đồng bộ; tránh assert dừng tức thì.

**7. Sau khi đã flush SSE 200, source ném exception thì có đổi status thành HTTP 500 không?**  
Không được mặc định. Response có thể đã committed; client có thể nhận prefix rồi EOF/error, test phải kiểm tra đúng thực tế đó.

**8. Tại sao `StepVerifier.withVirtualTime` cần Supplier tạo Flux trong lambda?**  
Để timed operators được dựng sau khi virtual scheduler được cài. Nếu Flux đã tạo trước, nó có thể dùng scheduler thật.

**9. `Flux.usingWhen` giúp kiểm tra gì khi cancel?**  
Nó có async cleanup callback riêng cho normal/error/cancel. Test có thể hủy stream và assert resource được dọn chính xác.

**10. Nếu client abort sau khi server commit DB, cancellation có rollback commit không?**  
Không. Cần idempotency, transaction boundary và reconciliation.

**11. Test MVC stream có `finished==1` sau client close đã chứng minh server thấy đúng một IOException chưa?**  
Chưa. Nó chứng minh callback không còn active trong thời hạn; stream hữu hạn có thể complete bình thường trước khi phát hiện abort.

**12. Một StepVerifier test có deadline 5s có làm HTTP server timeout sau 5s không?**  
Không. Đó là test verification deadline. Server/codec/client timeout được cấu hình riêng.

## 25. Tài liệu chính thức

1. Spring Framework — **MockMvc Async Requests**, `request().asyncStarted`, `asyncResult` và `asyncDispatch`: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
2. Spring Framework — **MVC Asynchronous Requests**, `Callable`, `DeferredResult`, `StreamingResponseBody`, `SseEmitter` và lưu ý khi `IOException` xuất hiện sau client disconnect: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
3. Spring Boot 3.3 — **Testing Spring Boot Applications**, `MOCK` so với `RANDOM_PORT` và WebTestClient/MockMvc: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
4. Spring Framework — **WebTestClient Streaming Responses**, `FluxExchangeResult` + `StepVerifier` + `thenCancel`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
5. Spring Framework — **WebFlux @ResponseBody**, reactive streams và codecs: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
6. Spring Framework — **Data Buffers and Codecs**, pooled memory, ownership, `DataBufferUtils.release`, `doOnDiscard`: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
7. Spring Framework — **WebFlux Reactive Core** và kiểm thử non-blocking runtime: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Project Reactor — **Testing with StepVerifier / Virtual Time**: https://projectreactor.io/docs/core/release/reference/testing.html
9. Project Reactor — **Using Resources and the Finally Block**, `doFinally`, `usingWhen`: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
10. Spring Boot 3.3 — **Graceful Shutdown** và request đang chạy khi context đóng: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html

**Kết luận:** Kiểm thử async, streaming và client disconnect cần đi qua đúng **lifecycle** và **tầng quan sát**. Với MVC, dùng `asyncDispatch` để khẳng định HTTP result sau `Callable/DeferredResult`; với streaming/network, dùng server `RANDOM_PORT` và client thật đọc event rồi đóng/hủy stream; với WebFlux, dùng `FluxExchangeResult` và `StepVerifier` để kiểm tra events, completion/cancellation, kết hợp server probe để xác minh transport cancel. Cleanup trên complete/error/cancel phải được thử riêng, với bounded deadlines và idempotency cho tác dụng phụ đã commit.