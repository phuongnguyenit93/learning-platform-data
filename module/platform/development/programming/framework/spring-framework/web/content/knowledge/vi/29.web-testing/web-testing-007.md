# Kiểm thử MVC async, asyncDispatch và phản hồi streaming trong Spring MVC

## 1. Bài toán và mô hình tư duy

Một phương thức controller Spring MVC không nhất thiết trả dữ liệu ngay trên luồng Servlet đang nhận request. Nó có thể trả một công việc bất đồng bộ, sau đó Spring MVC giải phóng luồng tiếp nhận, chờ kết quả và thực hiện một lần **ASYNC dispatch** để hoàn thiện HTTP response. Đối với dữ liệu liên tục hoặc dung lượng lớn, controller còn có thể trả **streaming response** bằng `ResponseBodyEmitter`, `SseEmitter` hoặc `StreamingResponseBody`.

Một bài kiểm thử tốt phải xác minh đúng **cả vòng đời**, thay vì chỉ thấy status 200 ở lần gọi MockMvc đầu tiên. Hai lỗi thường gặp là kiểm tra body trước khi kết quả async sẵn sàng và coi MockMvc là một HTTP server thật có thể đo thời điểm từng chunk dữ liệu đến client.

Sơ đồ:

```text
Test sử dụng MockMvc                       Spring MVC (Servlet stack)
        |                                            |
        | perform(GET /async)                        |
        |------------------------------------------->|
        |                                  DispatcherServlet gọi controller
        |                                             |
        |                                controller trả Callable /
        |                                DeferredResult / Mono ...
        |                                             |
        |                                  request.startAsync()
        |<-------- request().asyncStarted() ----------|
        |                                             |
        |                  Nguồn async tính toán kết quả
        |                                             |
        |  request().asyncResult(...) / getAsyncResult |
        |                   chờ có kết quả             |
        |                                             |
        | perform(asyncDispatch(mvcResult)) ---------->|
        |                                  DispatcherServlet xử lý lại
        |                                  kết quả, lỗi, converter
        |<------------- HTTP status/headers/body -----|
        |                                             |
        v                                             v
 Test kiểm tra response cuối cùng       Với stream: nhiều lần ghi/flush
```

Đối tượng chính của bài:

- `MockMvc` mô phỏng Servlet API và `DispatcherServlet` để kiểm thử Spring MVC mà không khởi động socket HTTP.
- `MvcResult` giữ request/response giả lập và trạng thái xử lý async của một lượt `perform`.
- `request().asyncStarted()` kiểm tra controller đã khởi động async handling.
- `request().asyncResult(...)` kiểm tra giá trị async hoàn tất (có thể chờ kết quả).
- `asyncDispatch(mvcResult)` dựng lượt xử lý tiếp theo có dispatcher type `ASYNC` để Spring MVC hoàn thiện xử lý kết quả.
- `StreamingResponseBody` viết trực tiếp vào `OutputStream`; `ResponseBodyEmitter` và `SseEmitter` phát nhiều phần qua message converters và định dạng SSE.

**Phạm vi:** Spring MVC trên **Servlet stack**, không phải WebFlux với `WebTestClient.bindToController`. Java 17+ và Spring Framework 6.x/Spring Boot 3.x là cơ sở của ví dụ; API MockMvc nền tảng được Spring duy trì ở các bản sau.

## 2. Async MVC khác request đồng bộ và khác WebFlux thế nào?

Trong xử lý đồng bộ, controller trả kết quả ngay và `DispatcherServlet` hoàn thành response trong lượt dispatch ban đầu. Trong xử lý async:

1. Controller trả một kiểu được MVC hỗ trợ như `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>` hoặc một reactive type đơn giá trị (`Mono<T>` khi có adapter phù hợp).
2. Spring gọi `startAsync()` trên Servlet request. Luồng Servlet ban đầu thoát để phục vụ công việc khác trong khi response vẫn mở.
3. Một luồng/callback bên ngoài tạo kết quả, hoặc có lỗi/timeout.
4. Spring thực hiện **ASYNC dispatch** qua Servlet container để xử lý giá trị như một return value MVC, áp dụng `HttpMessageConverter`, exception resolver và hoàn tất response.

| Kiểu controller trả về | Ai tạo kết quả? | Điều quan trọng khi test |
| --- | --- | --- |
| `Callable<T>` | Task executor của Spring MVC thực thi callback trên thread khác | Kiểm tra async bắt đầu, đợi kết quả, dispatch và xác minh response |
| `DeferredResult<T>` | Ứng dụng chủ động gọi `setResult` / `setErrorResult` từ callback/thread khác | Trong test có thể chủ động hoàn thành, tránh phụ thuộc thời gian |
| `WebAsyncTask<T>` | Callable kết hợp cấu hình timeout/executor/interceptor | Test cả nhánh kết quả và timeout theo môi trường thích hợp |
| `Mono<T>` | Publisher reactive được MVC chuyển sang cơ chế async | Test kết quả sau subscription và final dispatch |
| `ResponseBodyEmitter` | Ứng dụng gọi `send` nhiều lần, kết thúc bằng `complete` | Kiểm tra response hữu hạn, các phần body và cách hoàn tất |
| `SseEmitter` | Ứng dụng phát sự kiện SSE qua `send(SseEventBuilder)` | Kiểm tra cấu trúc SSE và hoàn tất với emitter hữu hạn |
| `StreamingResponseBody` | Hàm ghi trực tiếp byte vào `OutputStream` trên executor | Chờ tác vụ ghi xong và kiểm tra byte/headers cuối cùng |

**Async không đồng nghĩa non-blocking I/O.** Spring MVC dựa trên Servlet: khi stream vào response, các thao tác ghi vẫn là I/O có thể chặn và được thực hiện trên thread do executor quản lý. WebFlux có cơ chế I/O khác. Vì vậy bài toán cấu hình `AsyncTaskExecutor`, timeout và tài nguyên trong Spring MVC vẫn quan trọng.

## 3. Quy trình MockMvc chuẩn: perform → async result → asyncDispatch

Tài liệu Spring MVC Test dùng mẫu sau:

```java
MvcResult started = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("done"))
        .andReturn();

mockMvc.perform(asyncDispatch(started))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

Đây là đoạn đặt trong một phương thức `@Test` đã có `MockMvc` và static imports cho `get`, `asyncDispatch`, `request`, `status`, `content`. Chưa có controller tương ứng nên chỉ minh họa luồng kiểm thử.

Diễn giải:

1. `perform(get(...))` mô phỏng HTTP dispatch đầu tiên.
2. `request().asyncStarted()` chứng minh controller chọn nhánh Servlet async. Nếu controller trả kết quả đồng bộ, assertion này phải thất bại — đó là lỗi kiểm thử thiết kế sai, không phải lỗi MockMvc.
3. `request().asyncResult(...)` chờ và đối chiếu giá trị bất đồng bộ do controller phát ra. Đây là **kết quả trung gian của quá trình tính toán**, không nhất thiết là body HTTP đã được serialize.
4. `asyncDispatch(started)` tạo lượt dispatch thứ hai, giúp MVC thực hiện chuyển đổi sang body, hoàn thiện status/headers và chạy exception handling.
5. `content().string(...)` và `status()` ở bước cuối mới xác nhận hợp đồng HTTP.

Không thực hiện một `mockMvc.perform(get(...))` thứ hai để “đợi async”: đó là **HTTP request mới**, có thể chạy nghiệp vụ lần thứ hai. Luôn giữ đúng `MvcResult` của lần đầu và truyền nó cho `asyncDispatch`.

### 3.1 Vì sao kiểm tra status ngay lúc đầu có thể gây hiểu nhầm?

Trong nhiều trường hợp response mock ban đầu có status 200 mặc định, mặc dù thao tác async chưa hoàn tất và có thể thất bại sau đó. Việc `andExpect(status().isOk())` tại dispatch đầu chỉ quan sát trạng thái hiện tại, chưa chứng minh cuối cùng trả 200. Cần assert status và body sau async dispatch, nhất là khi chuyển một exception thành 4xx/5xx bằng `@ExceptionHandler`.

### 3.2 Khi nào dùng MvcResult.getAsyncResult(timeout)?

`MvcResult.getAsyncResult(long timeToWait)` chờ tối đa một khoảng mili giây do test chọn để lấy kết quả async, tránh treo quá lâu khi task không bao giờ hoàn tất. Ví dụ:

```java
MvcResult started = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

Object asyncValue = started.getAsyncResult(2_000);
assertEquals("done", asyncValue);

mockMvc.perform(asyncDispatch(started))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

`assertEquals` đến từ JUnit Jupiter. Mốc 2 giây ở đây là **thời gian chờ tối đa trong test**, khác với timeout của Servlet request do server/MVC cấu hình. Nếu test timeout, hãy kiểm tra luồng công việc, executor và dữ liệu trước khi đơn giản tăng thời gian chờ.

### 3.3 asyncDispatch thực sự làm gì?

Spring MVC Test không có Servlet container để tự dispatch HTTP qua mạng. `MockMvcRequestBuilders.asyncDispatch(mvcResult)` mô phỏng việc container gọi lại `DispatcherServlet` trong pha ASYNC sau khi đã có async result. Khi đó những bộ xử lý return value, converter và exception resolver có thể tạo response cuối.

Đối với một async handler trả object DTO, `request().asyncResult(dto)` kiểm tra DTO; response sau dispatch có thể là JSON hoặc status đặc thù. Không nên so sánh `asyncResult` với JSON đã serialize nếu giá trị controller thực tế là object. Nếu `DeferredResult<ResponseEntity<String>>`, giá trị async là `ResponseEntity`, còn HTTP status/body là kết quả của bước dispatch.

## 4. Dựng môi trường kiểm thử phù hợp

### 4.1 Hai cách tạo MockMvc

- `MockMvcBuilders.standaloneSetup(controller).build()`: nhanh, phù hợp khi test một controller và cấu hình MVC tối thiểu. Nếu cần advice, converters hoặc interceptors cụ thể, phải đăng ký rõ. Không mặc định có toàn bộ context của ứng dụng.
- `@WebMvcTest(MyController.class)` và `@Autowired MockMvc`: nạp MVC test slice; muốn service khác thì cung cấp mock/bean phù hợp. Các filter/Security trong slice có thể ảnh hưởng request.
- `@SpringBootTest` + `@AutoConfigureMockMvc`: nạp ứng dụng rộng hơn trong MockMvc, vẫn dùng Servlet mock. Khi cần kiểm tra I/O streaming theo thời gian thực, có thể chạy server thật với `webEnvironment = RANDOM_PORT`.

Ví dụ nền tảng trong Gradle của Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, AssertJ/Hamcrest và các phụ thuộc kiểm thử thông dụng. Dùng dependency management của Spring Boot để các version đồng bộ. Nếu controller thật dùng Reactor `Mono` hay `Flux`, cần thêm thư viện Reactor phù hợp (thường qua `spring-boot-starter-webflux` hoặc dependency liên quan), nhưng không cần ép mọi bài MVC async phụ thuộc Reactor.

### 4.2 Sơ đồ phạm vi bảo đảm

```text
Unit test trực tiếp Callable/service
     → xác minh logic Java, KHÔNG xác minh Servlet async MVC

MockMvc (standalone / MVC slice / full application context)
     → kiểm tra request mapping, async started/result/dispatch,
       MVC converters, status/headers, body cuối

Server thật + HTTP client
     → kiểm tra network, chunk arrival, flush, SSE còn mở,
       disconnect, proxy, buffering, timeout của connector
```

Không dùng riêng MockMvc để suy luận “client đã nhận chunk sau 100 ms” hoặc “browser tự reconnect SSE”. MockMvc response lưu body ở bộ nhớ và không mô phỏng đầy đủ socket/proxy/buffering.

## 5. Ví dụ hoàn chỉnh: Callable, DeferredResult và lỗi bất đồng bộ

Phần này gồm hai tệp có thể đặt vào một dự án Spring Boot 3.x/Java 17+. Tạo controller trả kết quả theo ba con đường: `Callable`, `DeferredResult` và `setErrorResult`. Với `DeferredResult`, test tự hoàn thành kết quả nên kiểm soát chính xác thời điểm, không cần `Thread.sleep`.

**Tệp `src/main/java/com/example/demo/AsyncDemoController.java`:**

```java
package com.example.demo;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class AsyncDemoController {
    private final AtomicReference<DeferredResult<String>> pending =
            new AtomicReference<>();

    @GetMapping("/async/callable")
    public Callable<String> callable() {
        return () -> "callable-ready";
    }

    @GetMapping("/async/deferred")
    public DeferredResult<String> deferred() {
        DeferredResult<String> result = new DeferredResult<>(5_000L);
        pending.set(result);
        return result;
    }

    public DeferredResult<String> pending() {
        return pending.get();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handle(IllegalArgumentException error) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body("bad-request");
    }
}
```

**Lưu ý kiến trúc:** trường `pending` chỉ làm điểm điều khiển trong ví dụ học tập/test và hỗ trợ đúng **một request đang chờ**. Không dùng `AtomicReference` toàn cục như thiết kế production cho nhiều request đồng thời. Ứng dụng thực cần ánh xạ promise theo ID, service quản lý vòng đời, giới hạn số yêu cầu đang đợi và dọn dẹp khi hoàn thành/timeout/hủy.

**Tệp `src/test/java/com/example/demo/AsyncDemoControllerTest.java`:**

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.context.request.async.DeferredResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class AsyncDemoControllerTest {
    private AsyncDemoController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        controller = new AsyncDemoController();
        mockMvc = standaloneSetup(controller).build();
    }

    @Test
    void callableMustBeDispatchedToProduceHttpBody() throws Exception {
        MvcResult started = mockMvc.perform(get("/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertEquals("callable-ready", started.getAsyncResult(2_000));

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().string("callable-ready"));
    }

    @Test
    void deferredResultCompletesOnlyWhenApplicationSetsIt()
            throws Exception {
        MvcResult started = mockMvc.perform(get("/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        DeferredResult<String> pending = controller.pending();
        assertNotNull(pending);
        pending.setResult("deferred-ready");

        assertEquals("deferred-ready", started.getAsyncResult(2_000));

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-ready"));
    }

    @Test
    void errorResultUsesMvcExceptionHandlingAfterDispatch()
            throws Exception {
        MvcResult started = mockMvc.perform(get("/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        controller.pending().setErrorResult(
                new IllegalArgumentException("invalid"));
        started.getAsyncResult(2_000);

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("bad-request"));
    }
}
```

Chạy trong thư mục dự án Gradle đã có `gradlew` và cấu hình dependency ở trên:

```bash
./gradlew test --tests '*AsyncDemoControllerTest'
```

Windows PowerShell có thể dùng:

```powershell
.\gradlew.bat test --tests '*AsyncDemoControllerTest'
```

Ba test đều có assertion về vòng đời async và response; khi thành công JUnit ghi nhận **3 test thành công** trong báo cáo test. Không có stdout ứng dụng được bảo đảm vì controller/test không gọi `System.out.println` (các log Spring/Gradle tùy cấu hình).

**Điểm quan trọng:** `setErrorResult` của `DeferredResult` được truyền qua async MVC result handling; `@ExceptionHandler` tạo HTTP 400 trong pha dispatch tiếp theo. Kiểm tra `status().isOk()` ở lần dispatch đầu sẽ không phát hiện đường xử lý lỗi này.

### 5.1 Ranh giới của ví dụ với yêu cầu chạy song song

Một endpoint thật không lưu mọi `DeferredResult` vào cùng một `AtomicReference`. Khi có nhiều HTTP request, request B có thể ghi đè reference của request A và khiến A chờ mãi. Dùng concurrency-safe registry có khóa (và cleanup), hoặc một event bus/message listener gắn correlation ID; test nhiều request song song để khẳng định không phát kết quả nhầm phiên.

## 6. Kiểm thử streaming body: điều gì khác với một kết quả async duy nhất?

**Streaming** có hai đặc điểm: kết quả có thể bao gồm nhiều phần được ghi trước khi toàn bộ công việc kết thúc, và một số luồng (như SSE) cố ý sống lâu/không có điểm kết thúc tự nhiên. Đối với kiểu hữu hạn, MockMvc có thể quan sát body sau khi tác vụ đã ghi xong. Đối với luồng vô hạn, phải đổi chiến lược test, không được chờ hoàn thành vô hạn.

### 6.1 StreamingResponseBody ghi byte trực tiếp

`StreamingResponseBody` phù hợp cho download hoặc xuất file lớn. Spring chạy callback ghi vào `OutputStream` dưới cơ chế async của Servlet MVC. Callback thường ghi từng buffer rồi `flush()` khi muốn đẩy dữ liệu xuống tầng response; socket/proxy có thể tiếp tục buffer trong môi trường thực.

**Tệp `src/main/java/com/example/demo/StreamingDemoController.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamingDemoController {

    @GetMapping("/stream/chunks")
    public ResponseEntity<StreamingResponseBody> chunks() {
        StreamingResponseBody stream = output -> {
            output.write("first\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
            output.write("second\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(stream);
    }

    private volatile SseEmitter currentEmitter;

    @GetMapping(path = "/stream/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events() {
        SseEmitter emitter = new SseEmitter(5_000L);
        currentEmitter = emitter;
        return emitter;
    }

    public SseEmitter currentEmitter() {
        return currentEmitter;
    }
}
```

Trong ví dụ này, `/stream/chunks` ghi hai phần rồi hoàn tất. `/stream/events` trả `SseEmitter` và cho phép test chủ động gửi sự kiện/kết thúc; field volatile chỉ dùng trong fixture để test **một kết nối tại một thời điểm**. Trong ứng dụng thật cần registry/session manager, timeout và dọn tài nguyên, không dùng một field chung khi nhiều client stream.

### 6.2 Test StreamingResponseBody bằng MockMvc

Tại sao không nhất thiết phải `asyncDispatch` sau khi stream ghi xong? Với `StreamingResponseBody`, nội dung được viết vào response output stream trong callback; phép kiểm tra có thể chờ async task hoàn thành rồi đọc body đã ghi. Spring cũng có mẫu test chính thức sử dụng `MvcResult::getAsyncResult` để chờ công việc streaming. Với phương thức trả một object cần MVC serialize sau async, `asyncDispatch` vẫn là bước quan trọng.

**Đoạn test** trong class có `MockMvc` đã cấu hình với `StreamingDemoController`:

```java
@Test
void finiteByteStreamHasExpectedBody() throws Exception {
    MvcResult result = mockMvc.perform(get("/stream/chunks"))
            .andExpect(request().asyncStarted())
            .andReturn();

    result.getAsyncResult(2_000); // Đợi callback ghi byte hoàn tất.

    assertEquals("first\nsecond\n",
            result.getResponse().getContentAsString());
    assertEquals(200, result.getResponse().getStatus());
}
```

Trong đoạn này cần static imports `get`, `request` và JUnit `assertEquals`. Assertion kiểm tra **nội dung cuối cùng** và HTTP status mock. Hai lần `flush()` trong controller **không thể được kết luận** là client ngoài mạng nhìn thấy hai gói/chunk riêng, vì MockMvc không có TCP socket/proxy thật.

Nếu ứng dụng muốn assert byte của tập tin, dùng `getResponse().getContentAsByteArray()` và so với dữ liệu byte mong muốn, đặc biệt khi dữ liệu nhị phân không có biểu diễn chuỗi đáng tin.

### 6.3 Khi asyncDispatch vẫn có ý nghĩa với streaming?

Với một số nhánh async return value, thực hiện `asyncDispatch` giúp MVC chạy xử lý hoàn tất hoặc resolver. Riêng callback `StreamingResponseBody` thường đã ghi trực tiếp nội dung lên response; khi test output, chờ `getAsyncResult(timeout)` và đọc mock response là đủ. Không áp dụng máy móc “mọi stream phải có asyncDispatch” cũng không cho rằng `asyncDispatch` tự tạo thêm chunk dữ liệu.

Nếu kiểm thử hợp đồng exception mapping, cần biết lỗi xuất hiện **trước hay sau khi response đã được commit**. Nếu byte đã được gửi ra mạng, server có thể không còn thay được status/body thành một JSON lỗi chuẩn. Với streaming thật, cần kiểm thử client đóng kết nối, mid-stream IOException và cleanup bằng server thật.

## 7. SseEmitter và ResponseBodyEmitter: kiểm thử dòng sự kiện hữu hạn

### 7.1 ResponseBodyEmitter và SseEmitter

`ResponseBodyEmitter` có thể phát nhiều object; mỗi `send(...)` được chuyển bằng `HttpMessageConverter` tương ứng và ghi vào response. `SseEmitter` chuyên cho **Server-Sent Events**, tạo các trường như `id:`, `event:` và `data:` theo giao thức `text/event-stream`.

```text
HTTP response status: 200
Content-Type: text/event-stream

id:evt-1
event:notice
data:ready

id:evt-2
event:notice
data:next

```

Hai dòng trống phân cách event trong SSE. Chỉ cần body cuối có đúng văn bản **chưa đủ** để chứng minh client thực sự nhận từng event ngay khi server flush. Với event chứa dữ liệu nhiều dòng, phải kiểm tra tuân thủ cú pháp SSE và cách JSON được serialize.

Các callback quan trọng:

- `emitter.send(data)` hoặc `emitter.send(SseEmitter.event().id(...).name(...).data(...))` gửi phần dữ liệu.
- `emitter.complete()` báo server hoàn tất luồng thành công; với SSE production có thể chỉ gọi khi client ngắt hoặc có chính sách kết thúc.
- `emitter.completeWithError(error)` kết thúc bằng lỗi nếu vẫn còn có thể xử lý. Nếu `send` ném `IOException` do peer disconnect, tài liệu Spring giải thích container có thể khởi phát async error handling; ứng dụng không nên tự gọi `completeWithError` thêm lần nữa một cách mù quáng trong tình huống đó.
- `onCompletion`, `onTimeout`, `onError` giúp dọn emitter khỏi danh sách kết nối đang hoạt động.

### 7.2 Test SSE hữu hạn, điều khiển thời điểm gửi và complete

Một cách kiểm thử đơn vị rõ ràng là để controller trả emitter, test chủ động gửi một event rồi gọi `complete`, sau đó mới kiểm tra body. Như vậy test không cần `Thread.sleep` và không đợi stream vô hạn:

**Tệp `src/test/java/com/example/demo/StreamingDemoControllerTest.java`:**

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class StreamingDemoControllerTest {
    private StreamingDemoController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        controller = new StreamingDemoController();
        mockMvc = standaloneSetup(controller).build();
    }

    @Test
    void bytesAreWrittenInOrder() throws Exception {
        MvcResult result = mockMvc.perform(get("/stream/chunks"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(2_000);

        assertEquals(200, result.getResponse().getStatus());
        assertEquals("first\nsecond\n",
                result.getResponse().getContentAsString());
    }

    @Test
    void completedSseContainsEventFields() throws Exception {
        MvcResult started = mockMvc.perform(get("/stream/events")
                        .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(request().asyncStarted())
                .andReturn();

        SseEmitter emitter = controller.currentEmitter();
        assertNotNull(emitter);

        emitter.send(SseEmitter.event()
                .id("evt-1")
                .name("notice")
                .data("ready"));
        emitter.complete();
        started.getAsyncResult(2_000);

        mockMvc.perform(
                    org.springframework.test.web.servlet.request
                            .MockMvcRequestBuilders.asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(
                        containsString("id:evt-1\n")))
                .andExpect(content().string(
                        containsString("event:notice\n")))
                .andExpect(content().string(
                        containsString("data:ready\n\n")));
    }
}
```

Chạy:

```bash
./gradlew test --tests '*StreamingDemoControllerTest'
```

Trong test stream hữu hạn, output byte được so theo thứ tự; với SSE, test kiểm tra một số trường có ý nghĩa của event. Không dựa vào lịch nội bộ một luồng `Thread.sleep`, vì scheduler chạy khác nhau giữa máy local và CI. Hai test tạo MockMvc mới trước từng ca, hạn chế việc trạng thái emitter rò giữa các test.

Nếu response được gzip/serialize hoặc đặt charset đặc thù, điều chỉnh matcher để kiểm tra semantics thay vì khẳng định một kiểu chuỗi không ổn định qua converter/configuration. Với SSE, body chứa dấu kết thúc event `\n\n` là hợp đồng định dạng.

### 7.3 Test ResponseBodyEmitter

`ResponseBodyEmitter` không buộc phải theo định dạng SSE. Ví dụ controller nhận emitter và dùng `send` nhiều lần, rồi `complete`:

```java
@GetMapping("/stream/messages")
public ResponseBodyEmitter messages() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(5_000L);
    // Ở production, một service/event callback sẽ giữ emitter để gửi dữ liệu.
    return emitter;
}
```

Đây chỉ là phương thức minh họa, không có nhiệm vụ phát dữ liệu nếu chạy độc lập. Test cần điều khiển emitter trong fixture tương tự `SseEmitter` và chọn `MediaType`/converter rõ ràng. Không nhầm “2 lần send” với “2 TCP packets”; để xác minh thời điểm nhận chunk cần HTTP client kết nối đến server thật.

## 8. Kiểm thử lỗi, timeout và client ngắt kết nối

### 8.1 Nhánh lỗi xảy ra trước khi response commit

Với `DeferredResult`, gọi `setErrorResult(exception)` có thể được xử lý bởi MVC exception resolver trong lượt dispatch. Test phần 5 minh họa rõ response HTTP 400 cuối. Với `Callable`, ném exception trong callable và dùng `@ExceptionHandler`/`@ControllerAdvice`; kiểm tra kết quả sau `asyncDispatch`.

Nên có các ca:

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Callable hoàn tất | `asyncStarted`, async result đúng, dispatch ra status/body |
| DeferredResult hoàn tất sau tín hiệu | Không trả body trước khi `setResult`; final dispatch đúng |
| DeferredResult phát lỗi | Lỗi được map qua MVC exception handler đúng status/body |
| Publisher `Mono` hoàn tất/lỗi trên MVC | Subscription xảy ra, kết quả/error được Spring chuyển tiếp |
| StreamingResponseBody ghi thành công | Header, byte output và trạng thái hoàn tất |
| Emitter hoàn tất sau n event | Đúng thứ tự/syntax, dọn emitter và hoàn tất |
| Async timeout | Callback timeout / response theo chính sách của ứng dụng |
| Client disconnect khi đang stream | Callback/cleanup, ghi lỗi I/O và dừng nguồn tương ứng |

### 8.2 Timeout trong MockMvc là hai loại khác nhau

**Timeout của ứng dụng:** Ví dụ `new DeferredResult<>(5_000L)` quy định thời gian cho async request. Khi chạy trong Servlet container, timeout được container/hạ tầng MVC xử lý theo vòng đời async, có thể kích hoạt `onTimeout` và các interceptor/exception resolver.

**Timeout của test:** `mvcResult.getAsyncResult(2_000)` là giới hạn thời gian một test chờ kết quả. Nó **không tự mô phỏng servlet async timeout** và không tự gọi `onTimeout` của ứng dụng.

Nếu cần test nhánh timeout logic đơn thuần, tách logic callback thành service có thể test trực tiếp hoặc xây hạ tầng điều khiển timeout trong integration test; không dùng `Thread.sleep(5_001)` rồi mong `MockMvc` hành xử như một container production. Spring MVC cho phép cấu hình `AsyncSupportConfigurer`, `DeferredResultProcessingInterceptor`, `CallableProcessingInterceptor` hoặc timeout callbacks tùy kịch bản.

Ví dụ xử lý timeout cho một DeferredResult **minh họa**:

```java
@GetMapping("/async/controlled")
public DeferredResult<String> controlled() {
    DeferredResult<String> result = new DeferredResult<>(3_000L);
    result.onTimeout(() -> result.setErrorResult(
            new IllegalStateException("async request timeout")));
    return result;
}
```

Đoạn này phải được đặt trong controller; cần đăng ký handler phù hợp cho `IllegalStateException` nếu muốn một response cụ thể. Nó không tự tạo công việc trả kết quả và sẽ timeout trên container thật nếu không được hoàn thành. MockMvc test không thể xác minh timer mạng thực chỉ từ đoạn này.

### 8.3 StreamingResponseBody và exception sau khi đã gửi dữ liệu

Ví dụ stream viết header/body một phần rồi gặp `IOException`: response có thể đã commit, không còn thay được status thành 500 hoặc gửi JSON lỗi chuẩn. Hệ thống cần định nghĩa client sẽ phát hiện dữ liệu thiếu thế nào (Content-Length/checksum/định dạng record/trailer tùy hợp đồng), đóng luồng và log rõ nguyên nhân.

Một cuộc gọi `SseEmitter.send` có thể ném `IOException` do client đóng kết nối. Trong Servlet environment, Spring có thể nhận `AsyncListener` lỗi và thực hiện dispatch để xử lý ngoại lệ; không bắt lỗi rồi liên tục gọi `completeWithError` mà không hiểu vòng đời của emitter. Sử dụng `onCompletion`, `onTimeout` và `onError` để xóa emitter khỏi registry và dừng subscription/job liên quan.

### 8.4 Bối cảnh security và filter ở ASYNC dispatch

Nếu dùng Spring Security, Servlet filters hoặc tracing MDC, phải cấu hình chúng hỗ trợ `DispatcherType.ASYNC` theo yêu cầu thực tế. Nếu filter chỉ chạy trên `REQUEST`, các pha security context/tracing/metrics ở dispatch sau có thể khác kỳ vọng. Cũng cần hiểu `OncePerRequestFilter.shouldNotFilterAsyncDispatch()` và thiết lập filter registration; không chỉ assert logic controller rồi khẳng định toàn bộ authorization hoạt động trên async dispatch.

Trong MockMvc standalone, filter/security không tự xuất hiện nếu không add chúng; với Spring Boot test slice/full context, chúng có thể tham gia. Vì vậy mỗi test nên nói rõ cấu hình nào đã được nạp.

## 9. Khi nào cần chạy server thật và WebTestClient?

Spring cho phép dùng `WebTestClient` với `MockMvcWebTestClient` để kiểm thử phần lớn HTTP response, bao gồm async hữu hạn. Tuy nhiên khi binder là MockMvc, **luồng vô hạn không thể được client chủ động cancel trên server** giống kết nối mạng thật. Vì vậy:

- Dùng MockMvc cho `DeferredResult`, `Callable`, stream có kết thúc, định dạng body và status cuối cùng.
- Dùng embedded server + `WebTestClient`/HTTP client thực khi cần quan sát nhiều event qua thời gian, cancel subscription, đóng TCP kết nối hoặc xử lý stream vô hạn.
- Nếu cần chứng minh `flush()` đẩy dữ liệu theo nhịp, kiểm tra end-to-end qua mạng. Proxy/gateway/browser có thể buffer dù ứng dụng đã flush.
- Với SSE stream dài, thường không chờ đến hết luồng; client subscribe, nhận n sự kiện mong đợi, sau đó cancel. Server phải dọn emitter/subscription tương ứng.

Mẫu kiểm thử tích hợp **minh họa** bằng một WebTestClient gắn với server HTTP thật:

```java
FluxExchangeResult<String> response = webTestClient.get()
        .uri("/stream/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

// Test tiêu thụ một số sự kiện rồi hủy subscription.
// Cần dùng StepVerifier / Reactor và server phát SSE thật.
StepVerifier.create(response.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify();
```

Đoạn này đòi hỏi test server đang chạy, `WebTestClient` được cấu hình URL/port thực, server phát tối thiểu hai phần tử phù hợp codec, và dependency `reactor-test`. Không phải chương trình Java độc lập. Với SSE, có thể dùng `ServerSentEvent<T>` để kiểm tra `id`/`event`/`data` đúng kiểu thay vì ép mọi event vào `String`. Tránh viết test sẽ chờ n event khi server không phát, cần thêm timeout trong StepVerifier và chuẩn bị dữ liệu test xác định.

Sự khác nhau giữa **MockMvc Mock HTTP response** và **HTTP response thực** là điểm giới hạn bằng chứng: một assertion body đúng ở MockMvc không đảm bảo client nhận một chunk ngay tại thời điểm server gọi `flush()`.

## 10. Cấu hình executor và độ ổn định kiểm thử

Spring MVC dùng `AsyncTaskExecutor` cho các `Callable` và blocking writes của một số kiểu streaming. Executor mặc định của MVC trong một số cấu hình không phù hợp production dưới tải cao; cần đặt giới hạn thread/queue rõ ràng, timeout hợp lý và theo dõi queue pressure. Ví dụ:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mvc-async-");
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(10_000L);
        configurer.setTaskExecutor(mvcAsyncExecutor());
    }
}
```

Đây là cấu hình mẫu riêng cho môi trường có Spring context; các tham số 4/16/100/10 giây là **giá trị minh họa**, cần chọn theo traffic, mức độ blocking và giới hạn tài nguyên thực. Spring quản lý vòng đời `ThreadPoolTaskExecutor` được tạo thành bean. Nếu context có nhiều executor hoặc yêu cầu tách tải download và task ngắn, cấu hình cần được xem xét để tránh cạn thread khi có nhiều stream dài.

Trong test dùng `standaloneSetup`, cấu hình này **không tự áp dụng** vì standalone chỉ lấy controller và những cài đặt đã đăng ký. Muốn kiểm thử đúng executor production, dùng WebApplicationContext/full integration test hoặc cấu hình MVC tương ứng trong MockMvc setup.

Không dùng `Thread.sleep` để “đợi” kết quả: đó là lựa chọn dễ flake do máy CI khác CPU. Ưu tiên công cụ có điều kiện hoàn tất: `DeferredResult.setResult` do test kiểm soát, `getAsyncResult(timeout)`, `CountDownLatch`/`CompletableFuture` nếu cần, hoặc virtual time cho reactive stream thuần (không nhầm với Servlet async timer).

## 11. Lỗi kiểm thử phổ biến và cách khắc phục

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `mockMvc.perform(get(...)).andExpect(status().isOk())` | Status ban đầu có thể là mặc định, chưa có response cuối | Assert `asyncStarted`, chờ result, `asyncDispatch` rồi kiểm tra status/body |
| Gọi lại `get(...)` thay vì `asyncDispatch(result)` | Tạo request mới, có thể chạy nghiệp vụ hai lần | Giữ `MvcResult` của dispatch đầu |
| Kiểm tra JSON ở `request().asyncResult(...)` khi controller trả DTO | Kết quả async là object trước conversion | Kiểm tra DTO ở asyncResult, JSON sau dispatch |
| Gọi `asyncDispatch` khi async result chưa sẵn | Test race/timeout | Dùng `request().asyncResult` hoặc `MvcResult.getAsyncResult(timeout)` |
| Thấy `asyncStarted` là kết luận nghiệp vụ thành công | Task async có thể lỗi hoặc timeout sau đó | Kiểm tra kết quả cuối và cả nhánh lỗi |
| Sử dụng `Thread.sleep` cố định | Flaky khi CI chậm hoặc scheduling khác | Chủ động hoàn thành `DeferredResult`; chờ điều kiện rõ ràng |
| Dùng MockMvc để khẳng định streaming flush đến browser | Không có socket/proxy/network trong MockMvc | Integration test qua server thật |
| Chờ một SSE stream vô hạn hoàn tất trong MockMvc | Không có điểm hoàn tất, test có thể treo | Test emitter hữu hạn hoặc stream thực với client cancel |
| Coi `getAsyncResult(1000)` là test Servlet timeout | Chỉ giới hạn thời gian chờ của test | Dựng test cho callback/timeout của container riêng |
| Không cấu hình HTTP message converters khi standalone | Body/status khác ứng dụng thật | Đăng ký converter/advice/filter hoặc dùng WebMvcTest/context |
| Không dọn emitter khi timeout/client disconnect | Rò danh sách connection và nguồn dữ liệu | `onCompletion`/`onError`/`onTimeout` + cleanup idempotent |
| Dùng executor không giới hạn hoặc block event callback | Tải cao gây cạn thread/tăng độ trễ | ThreadPoolTaskExecutor có giới hạn, đo queue/backpressure |
| Kiểm thử HTTP 200 sau khi bytes đã gửi nhưng giả định có thể đổi status | Response thực có thể đã commit | Thiết kế stream failure contract và test network |
| Áp dụng cách test Servlet cho WebFlux handler | Khác pipeline async/I/O | Dùng test framework đúng stack |

## 12. Bài tập và câu hỏi tự đánh giá

1. Một controller trả `DeferredResult<String>` và chưa gọi `setResult`. `MockMvc` trả gì sau `perform`? **Một result cho request đã bắt đầu async; chưa có business result cuối.**
2. Tại sao cần `asyncDispatch`? **Để Spring MVC hoàn thiện pha dispatch sau khi có async result, áp dụng converter và exception handling.**
3. Khi nào `request().asyncResult(dto)` nên so với DTO thay vì JSON? **Khi async result là object mà MVC chỉ serialize trong pha dispatch sau.**
4. Với `StreamingResponseBody` ghi hai buffer, body cuối trong MockMvc đúng có chứng minh hai chunk đến client ngay? **Không; MockMvc không quan sát network timing.**
5. Vì sao không chạy vô hạn `SseEmitter` trong MockMvc test? **Luồng không hoàn tất, MockMvc không có kết nối client thật để hủy tương đương.**
6. Khi `DeferredResult.setErrorResult` được gọi, nên kiểm tra response ở đâu? **Sau pha async dispatch và exception handling.**
7. `getAsyncResult(2_000)` có thực hiện timeout callback của server không? **Không; nó chỉ giới hạn thời gian test chờ result.**
8. Kiểm thử người dùng ngắt mạng giữa chừng nên dùng gì? **Một test server thực và client có khả năng đóng/cancel network stream.**

Bài tập thực hành: mở rộng `AsyncDemoController` để trả DTO, thêm `@ExceptionHandler` xử lý lỗi nghiệp vụ, và viết hai test: xác minh DTO ở `asyncResult` và JSON ở pha `asyncDispatch`. Tiếp theo, viết một SSE server có hai event rồi hoàn tất; kiểm tra định dạng bằng MockMvc. Cuối cùng, tạo SSE stream không tự kết thúc và kiểm thử qua `WebTestClient` kết nối server thật để xác nhận việc hủy và dọn emitter.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): cách dùng `asyncStarted`, `asyncResult` và `asyncDispatch`.
- [Spring Framework — Asynchronous Requests, HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `DeferredResult`, `Callable`, `SseEmitter`, `StreamingResponseBody`, executor và timeout.
- [Spring Framework — MockMvc Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/vs-streaming-response.html): giới hạn stream vô hạn của MockMvc.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): môi trường Servlet mô phỏng, mức độ kiểm chứng của MockMvc.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử qua HTTP client và truy xuất server response assertions.
- [Spring Framework — MockMvcRequestBuilders.asyncDispatch Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/request/MockMvcRequestBuilders.html): xây request dispatcher ASYNC từ `MvcResult`.
