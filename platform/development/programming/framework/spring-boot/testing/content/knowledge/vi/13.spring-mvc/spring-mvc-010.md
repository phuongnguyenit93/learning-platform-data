# Async request, asyncDispatch và xử lý phản hồi bất đồng bộ trong Spring MVC

Một controller Spring MVC có thể trả ngay một đối tượng đại diện cho kết quả tương lai, thay vì hoàn thành toàn bộ nghiệp vụ trên Servlet request thread. Spring MVC dùng **Servlet asynchronous request processing** để thả thread phục vụ request ban đầu, chờ tác vụ/callback hoàn tất, rồi thực hiện **ASYNC dispatch** để render HTTP response cuối cùng. Những kiểu return value quan trọng gồm **Callable**, **DeferredResult**, **CompletionStage**, **CompletableFuture** và **WebAsyncTask**.

Khó khăn chính trong kiểm thử là phân biệt **kết quả bất đồng bộ trung gian** với **HTTP status, headers và body cuối cùng**. Khi dùng **MockMvc** thuần, một lời gọi **perform(get(...))** không tự tái hiện lượt dispatch của servlet container. Test nên xác nhận **request().asyncStarted()**, quan sát kết quả async qua **request().asyncResult(...)** hoặc **MvcResult.getAsyncResult(...)**, sau đó gọi **mockMvc.perform(asyncDispatch(mvcResult))** để assert response cuối. Đây là trọng tâm của bài.

Ví dụ thực hành dùng Java 17, Spring Boot 3.4.5, JUnit Jupiter và Gradle. Để test chạy ổn định, ta điều khiển chính xác lúc future hoàn tất bằng **complete** hoặc **completeExceptionally**, không dùng Thread.sleep.

## 1. Mô hình hai pha của Servlet async request

Khi endpoint trả về một Callable, quy trình có thể được hình dung như sau:

~~~text
HTTP client gửi GET /api/quotes/callable?region=HN
    |
    v
Servlet container thread A
  DispatcherServlet gọi controller
  controller trả Callable<Quote>
  Spring MVC gọi startAsync() và đăng ký async processing
  thread A rời request; kết nối/response còn mở
    |
    v
AsyncTaskExecutor chạy Callable trên worker thread B
  lấy Quote hoặc exception
    |
    v
Servlet container thực hiện ASYNC dispatch
    |
    v
DispatcherServlet xử lý lại async result
  HttpMessageConverter -> JSON nếu thành công
  HandlerExceptionResolver -> response lỗi nếu exception
    |
    v
Client nhận HTTP status + headers + body
~~~

Với DeferredResult, Spring MVC đăng ký request async nhưng **không tự spawn một worker để sinh kết quả**: nguồn sự kiện/callback của ứng dụng phải gọi **setResult(value)** hoặc **setErrorResult(error)**. Với CompletableFuture, Spring MVC nhận thông báo khi future hoàn tất; việc công việc có thực sự chạy trên thread khác không phụ thuộc vào nơi tạo future và cách nó hoàn tất.

Hai pha cần phân biệt:

| Pha | Điều gì chắc chắn? | Điều chưa thể khẳng định? |
| --- | --- | --- |
| Bắt đầu async | Request đã bật Servlet async, handler trả một async holder phù hợp | Giá trị đã được tạo đúng, serializer thành công, status cuối cùng đã cố định |
| Có async result | Task/callback đã trả giá trị hoặc lỗi | HTTP body/headers đã render như client sẽ nhận |
| Async dispatch | Spring MVC xử lý kết quả, chuyển exception và render response | Đã kiểm thử network, timeout thật hoặc tải production |
| Client thực nhận response | Transport đã hoàn tất trong real-server test | Mọi đường lỗi/concurrency khác đều chính xác |

**Không phải cứ tên method có chữ async thì request thật sự bất đồng bộ.** Nếu controller trả một Quote đồng bộ, không có cơ sở để assert asyncStarted. Ngược lại, một CompletedFuture đã hoàn tất vẫn có kiểu return value async, nhưng không chứng minh đã chạy background work.

## 2. Chọn đúng kiểu trả về

| Kiểu | Cách có kết quả | Khi thích hợp | Cạm bẫy |
| --- | --- | --- | --- |
| Callable<T> | Spring MVC thực thi callable bằng AsyncTaskExecutor | Di chuyển một tác vụ sang worker do MVC quản lý | Code blocking vẫn block worker |
| DeferredResult<T> | Ứng dụng tự hoàn thành từ callback/event | Tương tác sự kiện hoặc dịch vụ trả kết quả muộn | Không gọi setResult thì sẽ chờ đến timeout |
| CompletableFuture<T> | CompletionStage hoàn tất trong framework/library/executor | Dependency đã trả future | completedFuture chỉ bọc giá trị đã có |
| WebAsyncTask<T> | Callable kèm timeout, executor và callback | Một endpoint cần cấu hình async riêng | Timeout servlet khác timeout của test |
| ResponseBodyEmitter / SseEmitter | Phát nhiều chunk/event | SSE hoặc HTTP streaming | Có thêm flush, disconnect, thứ tự, resource cleanup |
| StreamingResponseBody | Ghi OutputStream ở worker | Dữ liệu lớn dạng stream | Xử lý backpressure và lỗi I/O riêng |

Ba handler minh họa độc lập về cú pháp:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "ready";
}

@GetMapping("/future")
public CompletableFuture<String> future() {
    return CompletableFuture.completedFuture("ready");
}

@GetMapping("/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);
    result.setResult("ready");
    return result;
}
~~~

Đây chỉ là **trích đoạn**; cần lớp controller/import phù hợp và không biểu diễn một tác vụ thật sự đang chờ. Ở production, DeferredResult thường hoàn tất từ thread khác hoặc callback; hoàn tất ngay khi tạo chỉ minh họa API. Dự án đầy đủ bên dưới cho phép test giữ future pending rồi complete có kiểm soát.

## 3. Quy trình kiểm thử MockMvc chuẩn: bắt đầu, đợi, dispatch

Spring Framework hướng dẫn kiểm thử async theo hai lượt:

~~~java
MvcResult first = mockMvc.perform(
                get("/api/quotes/callable").param("region", "HN"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult(new Quote("HN", 25_000)))
        .andReturn();

mockMvc.perform(asyncDispatch(first))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.region").value("HN"))
        .andExpect(jsonPath("$.fee").value(25_000));
~~~

Đây là **trích đoạn**, dựa vào class Quote được định nghĩa ở phần 5. Cần chú ý chức năng của từng thao tác:

- **request().asyncStarted()**: xác nhận async processing đã bật cho request.
- **request().asyncResult(expected)**: đợi async result xuất hiện và kiểm tra giá trị trung gian; với record Quote, equals so sánh các thành phần theo giá trị.
- **andReturn()**: lấy MvcResult để tái sử dụng khi dispatch.
- **asyncDispatch(first)**: ra lệnh MockMvc thực hiện lượt **ASYNC dispatch** thay cho container thật.
- **status(), content(), jsonPath() sau dispatch**: kiểm tra status, content type và JSON cuối.

**Không chỉ assert asyncResult rồi kết luận hợp đồng HTTP đúng.** Một Quote Java hợp lệ vẫn có thể bị render sai JSON hoặc bị exception resolver xử lý không đúng. Ngược lại, một test chỉ assert JSON sau một perform thông thường có thể đang kiểm tra pha chưa hoàn tất.

Nếu kết quả không có equality ổn định, có thể dùng **first.getAsyncResult(5_000L)** để lấy và kiểm tra đối tượng đã sinh, rồi vẫn phải dispatch để xác nhận response HTTP. Con số 5.000 ở đây chỉ là **thời gian chờ của MockMvc test**, không chứng minh timeout của Servlet container hoặc status 504.

## 4. Hợp đồng nghiệp vụ dùng xuyên suốt ví dụ

Dự án tên spring-mvc-async-guide có ba endpoint:

- **GET /api/quotes/callable?region=HN** trả Callable<Quote>.
- **GET /api/quotes/future?region=HCM** trả CompletableFuture<Quote>.
- **GET /api/quotes/deferred?region=HN** trả DeferredResult<Quote> được nối với một CompletableFuture.

Service có quy tắc sau: HN có fee 25.000; vùng hợp lệ khác có fee 18.000. Vùng FAIL ném QuoteUnavailableException với message **pricing service unavailable**. Spring REST advice đổi exception này thành **HTTP 503** cùng JSON có **code=QUOTE_UNAVAILABLE** và message từ exception. Thiếu query parameter region là lỗi MVC binding, dự kiến **HTTP 400** trước khi controller đi vào async processing.

Dự án chỉ dùng memory, không cần database hoặc HTTP service bên ngoài. Unit/web MVC tests có thể stub service. Full-context test dùng service thật để kiểm tra wiring và exception handling.

## 5. Dự án Java 17+/Spring Boot 3.4.5 có thể dựng và chạy

Cấu trúc:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/mvcasync/AsyncDemoApplication.java
src/main/java/com/example/mvcasync/Quote.java
src/main/java/com/example/mvcasync/QuoteUnavailableException.java
src/main/java/com/example/mvcasync/QuoteService.java
src/main/java/com/example/mvcasync/QuoteController.java
src/main/java/com/example/mvcasync/ApiErrorHandler.java
src/test/java/com/example/mvcasync/QuoteControllerWebMvcTest.java
src/test/java/com/example/mvcasync/QuoteFullContextTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-mvc-async-guide'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
~~~

Dùng Gradle Wrapper tương thích với Java 17 và Boot 3.4.x. Spring MVC được cung cấp bởi spring-boot-starter-web. Spring Boot 3.4.x quản lý Spring Framework 6.2, do đó annotation **@MockitoBean** trong test hoạt động; Boot 3.3/Framework 6.1 không có annotation này, cần thay bằng cơ chế mocking đúng version, không tự trộn Spring Test mới vào project cũ.

### 5.1. Application, model và exception

**src/main/java/com/example/mvcasync/AsyncDemoApplication.java**

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/mvcasync/Quote.java**

~~~java
package com.example.mvcasync;

public record Quote(String region, int fee) {
}
~~~

**src/main/java/com/example/mvcasync/QuoteUnavailableException.java**

~~~java
package com.example.mvcasync;

public class QuoteUnavailableException extends RuntimeException {
    public QuoteUnavailableException(String message) {
        super(message);
    }
}
~~~

Quote là record Java 17, có equals/hashCode theo thành phần. Điều này làm assertion với **request().asyncResult(new Quote(...))** có nghĩa rõ ràng. Exception là domain exception do ví dụ tự định nghĩa; status HTTP của nó không mặc định là 503, mà do advice ở dưới quyết định.

### 5.2. Service thật: phân biệt giá trị đồng bộ và completed future

**src/main/java/com/example/mvcasync/QuoteService.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    public Quote quote(String region) {
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException("region must not be blank");
        }
        if ("FAIL".equals(region)) {
            throw new QuoteUnavailableException(
                    "pricing service unavailable");
        }
        return new Quote(
                region,
                "HN".equals(region) ? 25_000 : 18_000);
    }

    public CompletableFuture<Quote> quoteAsync(String region) {
        // Minh hoa kieu tra ve future, khong spawn background thread.
        return CompletableFuture.completedFuture(quote(region));
    }
}
~~~

Ở đây **quoteAsync** tính giá đồng bộ trước rồi trả **completedFuture**. Điều này không làm phát sinh công việc background. Ta cố ý thiết kế vậy để ví dụ dễ chạy, còn trong web MVC slice test, Mockito sẽ cung cấp một future **pending** để kiểm tra đúng luồng hoàn tất chậm. Nếu ứng dụng thật dùng HTTP async client, event listener hoặc một executor riêng, method quoteAsync có thể trả một future chưa hoàn tất, miễn giữ nguyên contract.

### 5.3. Controller với Callable, CompletableFuture và DeferredResult

**src/main/java/com/example/mvcasync/QuoteController.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/callable")
    public Callable<Quote> callable(@RequestParam String region) {
        return () -> service.quote(region);
    }

    @GetMapping("/future")
    public CompletableFuture<Quote> future(@RequestParam String region) {
        return service.quoteAsync(region);
    }

    @GetMapping("/deferred")
    public DeferredResult<Quote> deferred(@RequestParam String region) {
        DeferredResult<Quote> result = new DeferredResult<>(5_000L);

        service.quoteAsync(region).whenComplete((quote, failure) -> {
            if (failure == null) {
                result.setResult(quote);
            } else {
                Throwable cause = failure instanceof CompletionException
                        && failure.getCause() != null
                        ? failure.getCause()
                        : failure;
                result.setErrorResult(cause);
            }
        });
        return result;
    }
}
~~~

**Giải thích:**

- Endpoint **/callable** không thực thi quote ngay khi tạo lambda; Spring MVC sẽ sử dụng AsyncTaskExecutor để thực thi Callable sau khi controller trả nó.
- Endpoint **/future** chuyển future do service trả về cho return value handler của MVC. Việc tính toán trong quoteAsync đã đồng bộ ở code demo, nhưng return type có thể được MVC xử lý theo async semantics.
- Endpoint **/deferred** tạo DeferredResult với timeout 5 giây và nối callback của future. Khi future thành công, gọi setResult; khi thất bại, gọi setErrorResult để MVC giải quyết exception.
- Nhánh lỗi unwrap một lớp CompletionException vì một số API future chuyển lỗi theo wrapper này. Không được khẳng định mọi lỗi future chỉ có một lớp wrapper; nếu contract yêu cầu root cause nhiều cấp, cần kiểm tra chuỗi cause đúng cách.
- Nếu quoteAsync **ném ngay trước khi trả CompletableFuture**, endpoint deferred chưa kịp trả DeferredResult và lỗi có thể đi qua xử lý đồng bộ; test của luồng async cần làm rõ điểm lỗi xảy ra trước hay sau asyncStarted.

Không gọi **join()** trên request thread để đợi kết quả, vì đó là cách dễ biến endpoint bất đồng bộ thành blocking endpoint. Không đặt vòng lặp polling bận chờ DeferredResult trong controller.

### 5.4. Advice biến exception thành HTTP contract

**src/main/java/com/example/mvcasync/ApiErrorHandler.java**

~~~java
package com.example.mvcasync;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(QuoteUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError unavailable(QuoteUnavailableException exception) {
        return new ApiError(
                "QUOTE_UNAVAILABLE", exception.getMessage());
    }

    public record ApiError(String code, String message) {
    }
}
~~~

Nếu một Callable ném QuoteUnavailableException hoặc DeferredResult trả lỗi này qua setErrorResult, Spring MVC có thể dùng HandlerExceptionResolver và advice để tạo status **503** và JSON của ApiError trong **lượt dispatch cuối**. Khi exception đến từ code khác hoặc không được advice xử lý, status/body không nhất thiết giống vậy.

## 6. WebMvcTest: MockMvc test có điều khiển future

Lớp này giữ controller và Spring MVC thật nhưng **dùng @MockitoBean thay QuoteService**, phù hợp với web slice. Việc dùng future chưa hoàn tất rồi complete trực tiếp từ test giúp tránh đua lịch thread và không cần Thread.sleep.

**src/test/java/com/example/mvcasync/QuoteControllerWebMvcTest.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.CompletableFuture;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerWebMvcTest {
    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private QuoteService service;

    @Test
    void callableProducesJsonAfterAsyncDispatch() throws Exception {
        when(service.quote("HN")).thenReturn(new Quote("HN", 25_000));

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult(
                        new Quote("HN", 25_000)))
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));

        verify(service).quote("HN");
    }

    @Test
    void futureFinishesAtTimeControlledByTest() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("HCM")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/future")
                                .param("region", "HCM"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertFalse(pending.isDone());
        assertTrue(pending.complete(new Quote("HCM", 18_000)));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HCM"))
                .andExpect(jsonPath("$.fee").value(18_000));

        verify(service).quoteAsync("HCM");
    }

    @Test
    void deferredHandlesAsyncSuccess() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("HN")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/deferred")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertTrue(pending.complete(new Quote("HN", 25_000)));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));
    }

    @Test
    void deferredErrorIsMappedToHttp503() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("FAIL")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/deferred")
                                .param("region", "FAIL"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertTrue(pending.completeExceptionally(
                new QuoteUnavailableException(
                        "pricing service unavailable")));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_UNAVAILABLE"))
                .andExpect(jsonPath("$.message")
                        .value("pricing service unavailable"));
    }

    @Test
    void missingParameterFailsBeforeAsyncBegins() throws Exception {
        mockMvc.perform(get("/api/quotes/callable"))
                .andExpect(status().isBadRequest())
                .andExpect(request().asyncNotStarted());
    }
}
~~~

Các bằng chứng độc lập:

1. **callableProducesJsonAfterAsyncDispatch**: Callable được chạy; asyncResult trả Quote đúng; JSON và content-type đúng ở lượt dispatch thứ hai.
2. **futureFinishesAtTimeControlledByTest**: future vẫn pending sau lượt đầu, test chủ động complete; không dùng timing giả định. Status/body được assert sau dispatch.
3. **deferredHandlesAsyncSuccess**: callback chuyển kết quả future sang DeferredResult.setResult rồi MVC tạo response cuối.
4. **deferredErrorIsMappedToHttp503**: callback chuyển lỗi future bằng setErrorResult, advice trả 503 JSON ở lượt dispatch thứ hai. Đây **không phải test timeout**.
5. **missingParameterFailsBeforeAsyncBegins**: thiếu RequestParam bị MVC xử lý đồng bộ trước khi controller trả holder; assert asyncNotStarted mới đúng.

Trong MVC slice, QuoteService là mock nên các test **không** chứng minh thuật toán tính phí thật hay dependency của service hoạt động. Test dùng @MockitoBean chứ không phải @Mock thuần vì controller cần một **Spring bean** để constructor injection thành công.

## 7. Full context test: service thật, vẫn dùng MockMvc hai pha

**src/test/java/com/example/mvcasync/QuoteFullContextTest.java**

~~~java
package com.example.mvcasync;

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
class QuoteFullContextTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void callableUsesRealService() throws Exception {
        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult(
                        new Quote("HN", 25_000)))
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));
    }

    @Test
    void callableExceptionBecomes503() throws Exception {
        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "FAIL"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_UNAVAILABLE"));
    }
}
~~~

So với WebMvcTest, class này tải service thật và controller thật trong cùng application context. Nó xác nhận tính phí và exception mapping của đường MVC → service, nhưng vẫn là **MockMvc mô phỏng request**. Chưa có TCP socket, real browser hoặc container-level timeout test. Muốn quan sát HTTP transport và timeout thật, dùng SpringBootTest(webEnvironment = RANDOM_PORT) cùng HTTP client, executor/servlet container thích hợp.

## 8. Lệnh chạy và kết quả kỳ vọng

Khi dự án đã có Gradle Wrapper tương thích với Spring Boot 3.4.5:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.mvcasync.QuoteControllerWebMvcTest
./gradlew test --tests com.example.mvcasync.QuoteFullContextTest
./gradlew bootRun
~~~

Trên Windows, thay ./gradlew bằng gradlew.bat. Sau bootRun ở cổng mặc định có thể thử:

~~~bash
curl -i "http://localhost:8080/api/quotes/callable?region=HN"
curl -i "http://localhost:8080/api/quotes/future?region=HCM"
curl -i "http://localhost:8080/api/quotes/deferred?region=HN"
curl -i "http://localhost:8080/api/quotes/callable?region=FAIL"
~~~

Kỳ vọng các test **PASS** nếu code và môi trường đúng như cấu hình; đây là **kỳ vọng suy ra từ mã**, không phải stdout build đã được quan sát. Kỳ vọng response thành công HN có region=HN và fee=25000; HCM có fee=18000; request FAIL có HTTP 503 và code QUOTE_UNAVAILABLE. Jackson không cam kết thứ tự khóa JSON theo cách làm hợp đồng test, nên kiểm tra từng field bằng jsonPath thay vì so raw text toàn bộ.

## 9. Timeout của Servlet không giống timeout chờ trong MockMvc

Đây là nguồn nhầm lẫn phổ biến nhất:

| Cơ chế | Ví dụ | Ai kích hoạt? | Điều chứng minh |
| --- | --- | --- | --- |
| Async request timeout | new DeferredResult<>(5000L) | Servlet container/asynchronous request machinery | Request bị hết hạn theo cấu hình thực tế |
| Chờ kết quả trong test | first.getAsyncResult(5000L) | MockMvc/JUnit test | Test đã đợi tối đa bao lâu |
| Lỗi async có chủ đích | pending.completeExceptionally(error) | Code test hoặc thư viện | Exception mapping khi async result báo lỗi |
| Timeout fallback | DeferredResult.onTimeout(...) | Lifecycle timeout của request | Logic fallback nếu timeout thật sự xảy ra |
| Executor queue saturation | Rejection khi pool/queue quá tải | Thread pool/task submission | Khả năng đáp ứng theo tải và cấu hình |

Nếu test tạo future pending rồi **không complete** và gọi getAsyncResult(100L), test có thể bị lỗi do **hết thời gian chờ của test**. Nó **không tự chứng minh** client thực nhận HTTP 504, cũng không chắc đã gọi DeferredResult.onTimeout. Với MockMvc không có Servlet container thực thực hiện timer/ASYNC dispatch tự động như môi trường chạy thật.

Đây là trích đoạn minh họa một timeout fallback, **không thuộc project runnable**:

~~~java
DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(2_000L);

result.onTimeout(() -> result.setResult(
        ResponseEntity.status(504).body("gateway timeout")));

result.onCompletion(() -> {
    // Release per-request listener or registration.
});
~~~

Callback chỉ có ý nghĩa khi timeout event thực sự được phát. Một test thật về timeout cần dùng embedded Servlet container/HTTP client hoặc hạ tầng test mô phỏng đúng lifecycle. Không viết Thread.sleep(2000) rồi coi như đã kiểm tra timeout theo chuẩn.

### WebAsyncTask và tùy biến timeout

WebAsyncTask<T> bọc Callable<T> và có thể cấu hình timeout/executor/callback riêng cho endpoint. Chẳng hạn, trích đoạn sau là ý tưởng:

~~~java
@GetMapping("/slow")
public WebAsyncTask<String> slow() {
    return new WebAsyncTask<>(2_000L, () -> slowService.fetch());
}
~~~

Không có class slowService trong project ví dụ; đây là **trích đoạn** cho một service thực tế. Nó không đồng nghĩa Callable đã hoàn tất sau 2 giây. Cần xác định timeout handler/error response thực tế và kiểm tra ở đúng tầng.

## 10. Executor, Servlet async support và concurrency

Spring MVC thường dùng AsyncTaskExecutor để chạy Callable. Executor mặc định của MVC không mặc nhiên phù hợp với production khi có nhiều công việc blocking; hệ thống nên có thread pool/queue được giới hạn, timeout, metrics và rejection policy rõ ràng.

Trích đoạn cấu hình minh họa (cần import Spring configuration/Web MVC classes, không thuộc project runnable):

~~~java
@Configuration(proxyBeanMethods = false)
class AsyncMvcConfiguration implements WebMvcConfigurer {
    private final AsyncTaskExecutor executor;

    AsyncMvcConfiguration(
            @Qualifier("mvcTaskExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L);
    }

    @Bean("mvcTaskExecutor")
    static ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-async-");
        return pool;
    }
}
~~~

ThreadPoolTaskExecutor là Spring-managed bean nên lifecycle initialization/shutdown được container xử lý. Những kích thước pool ở trên chỉ để giải thích cách cấu hình, không phải khuyến nghị hiệu năng chung. Cần điều chỉnh theo tải, CPU/IO ratio và backpressure; nếu worker gọi JDBC hay blocking HTTP, Servlet thread được giải phóng nhưng **worker vẫn bị giữ**.

Servlet và filter cần hỗ trợ asyncSupported, và filter mapping có thể cần DispatcherType.ASYNC. Với Spring Boot embedded container cấu hình thông thường, Spring MVC async thường hoạt động sẵn; nếu ứng dụng tùy biến servlet/filter registration hoặc triển khai WAR, hãy kiểm tra những flag đó và test trên container thật.

### ThreadLocal, security và transaction

MDC logging, SecurityContext, RequestAttributes và transaction thường phụ thuộc thread. Đừng cho rằng mọi ThreadLocal trên request thread ban đầu tự được chuyển sang worker của Callable/CompletableFuture. Spring Security có các tích hợp/propagation riêng, nhưng custom MDC hoặc context vẫn cần kiểm soát rõ.

Tương tự, @Transactional ở một request/controller thread không tự mở transaction xuyên mọi worker thread. Đặt transaction boundary ở service được thực thi trên worker nếu thao tác DB cần transaction, và viết integration test phù hợp. Chỉ dùng MockMvc để thấy status 200 không chứng minh transaction isolation, security context propagation hoặc cancellation đã đúng.

## 11. Xử lý lỗi, late completion và client disconnect

DeferredResult.setResult và setErrorResult trả boolean cho biết việc đặt kết quả có thành công hay không. Nếu async request đã hết hạn hoặc được xử lý, một callback đến muộn có thể không thay được response nữa. Với CompletableFuture, **complete** và **completeExceptionally** chỉ thành công khi future chưa hoàn tất; test kiểm tra giá trị boolean để phát hiện completion trùng/đến sai thời điểm.

Client disconnect không tự bảo đảm job đang chạy bị hủy. Ứng dụng thực cần chính sách cancellation/cleanup rõ ràng cho HTTP client, event listener, DB query hoặc streaming. Trong Servlet async, error/timeout/completion callbacks có thể xảy ra cạnh tranh; không lập trình giả định cứ đặt result là chắc chắn client nhận được.

Đối với async exception, phải phân biệt:

- **Lỗi trước khi asyncStarted:** lỗi binding, thiếu RequestParam hoặc service ném trước khi trả async holder. Có thể trả 400/500 theo đường đồng bộ, không được ép asyncDispatch.
- **Lỗi bên trong Callable:** xuất hiện trên worker, sau đó được MVC đưa vào async result và xử lý trong dispatch.
- **Lỗi do future hoàn tất exceptional:** callback có thể thấy CompletionException wrapper; cần bảo toàn cause và gửi đúng error result.
- **Timeout servlet:** chỉ xuất hiện khi async lifecycle thực sự hết hạn; là cơ chế khác với completeExceptionally.
- **Lỗi serialize response:** async result có thể đúng nhưng JSON serialization thất bại sau dispatch; đó là lý do cần assert body/status cuối.

Đối với StreamingResponseBody, SseEmitter hoặc ResponseBodyEmitter, việc ghi từng chunk, flush, thứ tự event, media type text/event-stream, heartbeat và lỗi client cần test riêng. Một test JSON đơn-value dùng asyncDispatch không bao phủ các đặc tính đó.

## 12. So sánh Spring MVC async, @Async và WebFlux

**Spring MVC async** xử lý một HTTP request theo Servlet asynchronous contract, giữ response mở rồi dispatch lại để hoàn thành. **@Async** lại là phương thức chạy async thông qua Spring AOP và executor: một service @Async có thể trả CompletableFuture, nhưng nếu controller gọi join() ngay, HTTP request vẫn bị chặn. Ngược lại Callable return type của MVC không yêu cầu @EnableAsync.

**Spring WebFlux** xây trên reactive web runtime và có các semantics khác về I/O/backpressure. MVC có thể nhận một số reactive types qua adapters nhưng không tự biến thành WebFlux. Khi chọn cách test, xác định ứng dụng thực sự dùng servlet MVC, reactive WebFlux hay trộn các thư viện vì lý do khác.

MockMvc có quy trình asyncDispatch tường minh. Nếu dùng WebTestClient gắn qua MockMvc hoặc reactive stack theo cơ chế hỗ trợ, framework test client có thể thực hiện các bước tương ứng tự động; không sao chép nguyên mọi lệnh MockMvc sang WebTestClient.

## 13. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Phương án đúng |
| --- | --- | --- |
| jsonPath thất bại ở perform lần đầu | HTTP response cuối chưa qua async dispatch | Assert asyncStarted, dùng asyncDispatch rồi assert JSON |
| asyncDispatch báo async chưa bắt đầu | Controller trả sync hoặc lỗi xảy ra trước return async | Test đúng đường sync; kiểm tra request().asyncStarted() |
| Test rơi vào timeout trong getAsyncResult | Future/DeferredResult chưa hoàn tất | Controlled completion, timeout chờ hợp lý, tránh sleep |
| Test xanh ở asyncResult nhưng JSON sai | Bỏ qua message converter/exception resolver | Assert sau asyncDispatch |
| Future hoàn tất quá nhanh để chứng minh async worker | Dùng completedFuture sau tính toán sync | Kiểm tra executor/concurrency riêng |
| WebMvcTest xanh nhưng production service lỗi | QuoteService được @MockitoBean mock | Bổ sung unit/full-context test |
| Test 503 được coi là timeout thật | Dùng completeExceptionally / setErrorResult | Phân biệt async error với Servlet timeout |
| Servlet async filter không chạy ở dispatch | Filter mapping không có ASYNC dispatcher type | Xem asyncSupported và DispatcherType.ASYNC |
| Context/security mất trên worker | ThreadLocal không tự propagate | Dùng cơ chế propagation được hỗ trợ |
| Hết pool dưới tải | Nhiều job blocking, queue/thread không phù hợp | Giới hạn pool/queue, load test và metrics |
| Job tiếp tục sau khi client bỏ kết nối | Chưa quản lý cancellation và cleanup | Thiết kế timeout/cancel/resource lifecycle |
| Test flaky do sleep hoặc timing | Scheduling khác nhau giữa máy và CI | Dùng Future, latch, callback và controlled completion |

## 14. Chiến lược kiểm thử và bài tập tự kiểm tra

Một bộ test hợp lý thường có:

1. **Unit test service** để xác nhận thuật toán, input và exception theo contract Java.
2. **@WebMvcTest với future kiểm soát** để kiểm tra asyncStarted, asyncDispatch, JSON, exception handling và request validation.
3. **@SpringBootTest @AutoConfigureMockMvc** để kiểm tra wiring thật cùng Spring MVC mà vẫn không mở server.
4. **@SpringBootTest(webEnvironment = RANDOM_PORT)** khi cần kiểm tra Servlet container, HTTP/network, async timeout, filter dispatch, cancellation và security context thực.
5. **Load/concurrency tests** khi rủi ro nằm ở executor saturation, latency, throughput hoặc backpressure.

**A.** Controller trả Callable nhưng test chỉ assert JSON ở perform đầu. Có đủ không? **Không**; cần asyncDispatch để kiểm tra phản hồi cuối.

**B.** request().asyncResult(expectedQuote) xanh. Có chứng minh content-type, JSON và status cuối đúng không? **Không**; nó xác nhận giá trị async trung gian.

**C.** Service trả CompletableFuture.completedFuture(quote()). Có bảo đảm phép tính ở worker thread không? **Không**; quote() chạy trước khi tạo completed future.

**D.** DeferredResult được setErrorResult(Throwable) và dispatch trả HTTP 503. Có chứng minh Servlet timeout không? **Không**; đây là xử lý lỗi async, không phải timeout lifecycle.

**E.** getAsyncResult(100L) hết thời gian. HTTP client có chắc nhận 504 không? **Không**; thời gian chờ của test là cơ chế riêng.

**F.** Dùng MockMvc với @MockitoBean service. Có chứng minh repository/database/remote client thật không? **Không**, chỉ chứng minh phần controller/MVC có stub.

**G.** Thiếu request parameter dẫn tới HTTP 400 trước khi controller chạy. Có nên ép asyncStarted? **Không**, request này không kích hoạt async.

**H.** Servlet async giúp giải phóng request thread trong lúc chờ, có nghĩa toàn bộ tác vụ blocking biến mất không? **Không**, blocking có thể chuyển sang worker; phải quản lý executor.

### Checklist trước khi chốt bài test

- Return type thực sự hỗ trợ async, và controller có đi vào nhánh đó với input đã thử?
- Lượt đầu đã assert asyncStarted, và biết async result được tạo khi nào?
- Có chờ/hoàn tất future bằng cơ chế chắc chắn, không phụ thuộc Thread.sleep?
- Đã dùng asyncDispatch và assert **HTTP status, content-type/body cuối**?
- Có test thành công, lỗi sau asyncStarted và lỗi đồng bộ trước asyncStarted?
- Khi có advice, đã kiểm tra exception mapping sau dispatch?
- Đã phân biệt timeout MockMvc với timeout real Servlet container?
- Executor và ThreadLocal/security/transaction context có được thiết kế theo tải thực?
- Async cancellation, client disconnect và resource cleanup có test ở tầng phù hợp?
- Có phân biệt web slice dùng mock với full-context dùng service thật?
- Các test có độc lập, không giữ future pending hoặc thread leak giữa các ca?

**Kết luận:** Kiểm thử phản hồi bất đồng bộ trong Spring MVC cần hiểu rõ **bắt đầu async → hoàn tất result → ASYNC dispatch → HTTP response**. Trong MockMvc thuần, request().asyncStarted() và request().asyncResult(...) kiểm tra pha đầu, còn mockMvc.perform(asyncDispatch(result)) mới kiểm tra status và body cuối. Dùng controlled CompletableFuture giúp test ổn định; timeout, networking, threading và cancellation phải được xác nhận bằng những integration tests chuyên biệt khi đó là yêu cầu.

## Tài liệu chính thức

- Spring Framework 6.2 — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html
- Spring Framework 6.2 — Asynchronous Requests in Spring MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — MockMvc asyncDispatch API: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/web/servlet/request/MockMvcRequestBuilders.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
