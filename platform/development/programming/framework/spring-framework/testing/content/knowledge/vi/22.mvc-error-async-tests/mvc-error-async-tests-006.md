# asyncStarted với Callable hoặc DeferredResult

Spring MVC hỗ trợ xử lý request bất đồng bộ để giải phóng Servlet request thread trong lúc ứng dụng chờ một công việc hoàn tất. Controller có thể trả về `Callable<T>` hoặc `DeferredResult<T>`. Khi đó, request đi qua một giai đoạn xử lý ban đầu, chuyển sang async mode, rồi được dispatch lần nữa khi kết quả sẵn sàng.

Khi kiểm thử bằng MockMvc, chỉ gọi `perform(...)` và kiểm tra response ngay như một request đồng bộ là chưa đủ. Cần xác nhận request đã bắt đầu async processing bằng `request().asyncStarted()`, lấy `MvcResult` của lần dispatch đầu, chờ hoặc chủ động hoàn tất kết quả, rồi dùng `asyncDispatch(...)` để mô phỏng lần dispatch tiếp theo và kiểm tra response cuối cùng.

## 1. Vì sao Spring MVC có xử lý bất đồng bộ?

Trong mô hình Servlet đồng bộ, một request thường được xử lý trên một Servlet request thread:

1. Container nhận HTTP request và cấp một thread để xử lý.
2. DispatcherServlet gọi controller.
3. Controller thực hiện công việc và trả về kết quả.
4. Spring ghi response.
5. Thread kết thúc việc xử lý request.

Nếu controller phải chờ một tác vụ chậm, chẳng hạn gọi dịch vụ bên ngoài hoặc chờ một kết quả được tạo ở thread khác, request thread có thể bị giữ trong thời gian chờ.

Spring MVC asynchronous processing cho phép controller trả về một kiểu kết quả bất đồng bộ. DispatcherServlet bắt đầu async processing theo Servlet API rồi kết thúc lần dispatch ban đầu. Khi kết quả hoàn tất, Servlet request được dispatch lại để Spring xử lý kết quả và tạo response.

Luồng khái quát:

~~~text
HTTP request
    |
    v
DispatcherServlet / Controller
    |
    | Controller trả Callable hoặc DeferredResult
    v
Spring bắt đầu async processing
    |
    +---- Lần dispatch ban đầu kết thúc
    |
    v
Tác vụ bất đồng bộ hoàn tất
    |
    v
Async dispatch lần thứ hai
    |
    v
Spring xử lý kết quả / exception
    |
    v
HTTP response
~~~

Async processing không có nghĩa là request lập tức hoàn tất. Nó có nghĩa lần dispatch ban đầu đã nhường quyền điều khiển để kết quả được hoàn thành sau đó. Response cuối cùng chỉ được tạo khi async result được dispatch trở lại qua chuỗi xử lý MVC.

## 2. Callable và DeferredResult khác nhau thế nào?

Hai kiểu trả về đều cho phép Spring MVC xử lý request bất đồng bộ, nhưng quyền điều khiển việc hoàn tất kết quả khác nhau:

| Tiêu chí | `Callable<T>` | `DeferredResult<T>` |
|---|---|---|
| Ai cung cấp kết quả? | Spring chạy Callable trên async task executor và lấy giá trị trả về. | Mã ứng dụng hoặc thành phần bên ngoài gọi `setResult(...)` khi kết quả sẵn sàng. |
| Cách controller trả về | Trả một Callable chứa công việc cần thực thi. | Tạo và trả DeferredResult ngay, sau đó hoàn tất nó ở thời điểm khác. |
| Phù hợp với | Một tác vụ có thể được thực thi bởi executor của Spring. | Kết quả đến từ callback, message, event, long polling hoặc một nguồn bất đồng bộ do ứng dụng quản lý. |
| Hoàn tất | Callable return một giá trị hoặc ném exception. | Gọi `setResult` hoặc `setErrorResult`. |
| Timeout/callback | Có thể cấu hình qua async support hoặc dùng `WebAsyncTask` khi cần điều khiển riêng. | Có thể đặt timeout và callback trực tiếp trên DeferredResult. |

Không nên hiểu `Callable` là một kiểu dữ liệu response. Nó là một công việc mà Spring sẽ thực thi. Tương tự, `DeferredResult` là một holder đại diện cho kết quả sẽ được cung cấp sau; controller trả holder đó trước khi giá trị cuối cùng có mặt.

## 3. Callable trong controller

Ví dụ controller trả về một Callable:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting/callable")
    Callable<Greeting> greeting() {
        return () -> new Greeting("Hello from Callable");
    }
}

record Greeting(String message) {}
~~~

Khi nhận request, Spring MVC nhận Callable và chuyển việc thực thi sang async task executor. Khi Callable trả về một Greeting, Spring lưu kết quả và thực hiện async dispatch để tiếp tục xử lý response.

Có thể thực hiện thêm công việc trong Callable:

~~~java
@GetMapping("/reports/{id}")
Callable<Report> report(@PathVariable long id) {
    return () -> reportService.generate(id);
}
~~~

Trong ví dụ này, lời gọi `reportService.generate(id)` chạy trong Callable do async executor thực thi. Không nên đưa công việc cần chạy bất đồng bộ vào trước câu lệnh `return`, vì khi đó controller đã thực hiện công việc trên request thread trước khi trả về.

Ví dụ sau vẫn là xử lý đồng bộ trong controller:

~~~java
@GetMapping("/reports/{id}")
Callable<Report> report(@PathVariable long id) {
    Report report = reportService.generate(id);
    return () -> report;
}
~~~

Ở đây, `generate(id)` đã chạy trước khi Callable được trả về. Callable chỉ trả lại kết quả có sẵn, nên phần công việc tốn thời gian không được chuyển sang async executor.

## 4. DeferredResult trong controller

`DeferredResult<T>` phù hợp khi controller không trực tiếp tạo kết quả trong một Callable. Controller trả về DeferredResult trước, sau đó một thành phần khác hoàn tất nó.

Ví dụ định nghĩa service trả về một DeferredResult:

~~~java
import org.springframework.web.context.request.async.DeferredResult;

interface GreetingService {
    DeferredResult<Greeting> loadGreeting();
}
~~~

Controller chuyển tiếp DeferredResult:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting/deferred")
    DeferredResult<Greeting> greeting() {
        return greetingService.loadGreeting();
    }
}
~~~

Một implementation có thể hoàn tất kết quả từ callback hoặc executor:

~~~java
DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

executor.execute(() -> {
    try {
        Greeting greeting = greetingClient.fetch();
        result.setResult(greeting);
    } catch (Exception exception) {
        result.setErrorResult(exception);
    }
});

return result;
~~~

Trong ví dụ, controller hoặc service tạo DeferredResult với timeout 5 giây, rồi đăng ký công việc trên executor. Khi công việc thành công, `setResult` cung cấp giá trị. Khi thất bại, `setErrorResult` chuyển exception hoặc error object vào quy trình xử lý async của Spring MVC.

Các phương thức hoàn tất quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `setResult(value)` | Hoàn tất DeferredResult bằng kết quả thành công. |
| `setErrorResult(error)` | Hoàn tất bằng một lỗi hoặc exception để Spring xử lý. |
| `onTimeout(callback)` | Đăng ký callback khi DeferredResult timeout. |
| `onError(callback)` | Đăng ký callback khi async request gặp lỗi. |
| `onCompletion(callback)` | Đăng ký callback khi async request hoàn tất. |
| `isSetOrExpired()` | Kiểm tra kết quả đã được đặt hoặc request đã hết hạn hay chưa. |

Không nên gọi `setResult` nhiều lần và giả định mọi lần gọi đều thay đổi kết quả. DeferredResult chỉ nhận một kết quả hoàn tất; nếu đã được set hoặc request đã hết hạn, lần hoàn tất sau không thể thay thế kết quả trước.

## 5. asyncStarted() xác nhận điều gì?

Trong MockMvc, `request().asyncStarted()` là matcher xác nhận Servlet request đã chuyển sang async processing trong lần thực thi request đang được kiểm tra.

Static import:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
~~~

Ví dụ tối thiểu:

~~~java
mockMvc.perform(get("/greeting/callable"))
    .andExpect(request().asyncStarted());
~~~

Matcher này xác nhận một sự kiện ở giai đoạn request ban đầu: async processing đã được khởi động. Nó không xác nhận response cuối cùng có status đúng, JSON đúng hay body đúng. Để kiểm tra những điều đó, cần thực hiện async dispatch và assertion trên kết quả cuối.

Spring cũng cung cấp `request().asyncNotStarted()` để xác nhận request không chuyển sang async mode:

~~~java
mockMvc.perform(get("/greeting/synchronous"))
    .andExpect(request().asyncNotStarted())
    .andExpect(status().isOk());
~~~

Điều này hữu ích khi endpoint được kỳ vọng xử lý đồng bộ hoặc khi muốn xác nhận một nhánh xử lý không vô tình chuyển sang async.

Một điểm dễ nhầm: Callable có thể được executor hoàn tất rất nhanh, thậm chí trước khi test gọi assertion tiếp theo. Request vẫn đã bắt đầu async processing. Vì vậy, `asyncStarted()` không có nghĩa là tại đúng thời điểm assertion, công việc nền chắc chắn còn đang chạy.

## 6. Quy trình kiểm thử async bằng MockMvc

Với một async controller, test thường gồm hai lần gọi MockMvc:

1. Gọi endpoint bằng `perform(...)` như bình thường.
2. Xác nhận request đã bắt đầu async processing bằng `request().asyncStarted()`.
3. Lấy `MvcResult` từ lần dispatch ban đầu.
4. Chờ hoặc chủ động hoàn tất async result.
5. Gọi `asyncDispatch(mvcResult)` để mô phỏng lần dispatch tiếp theo.
6. Xác nhận status, header và response body cuối cùng.

Mẫu tổng quát:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/some-async-endpoint"))
    .andExpect(request().asyncStarted())
    .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk());
~~~

Các import cần thiết:

~~~java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

`asyncDispatch(mvcResult)` sử dụng kết quả async gắn với MvcResult để thực hiện lần dispatch tiếp theo. Nếu async result chưa sẵn sàng, MockMvc chờ theo timeout được cấu hình cho request. Nếu kết quả không hoàn tất trong thời gian chờ, test có thể thất bại vì timeout.

Không gọi `asyncDispatch` với một MvcResult của request đồng bộ. Trước khi dispatch, hãy xác nhận `asyncStarted()` để test thể hiện rõ endpoint thực sự sử dụng async processing.

## 7. Kiểm thử Callable hoàn chỉnh

Với Callable, công việc được Spring thực thi tự động qua async executor. Test không cần tự gọi `setResult`; chỉ cần lấy MvcResult rồi dispatch khi Callable hoàn tất.

Giả sử controller:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallableController {

    @GetMapping("/callable")
    Callable<Greeting> greeting() {
        return () -> new Greeting("Hello from Callable");
    }
}

record Greeting(String message) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class CallableControllerTests {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new CallableController())
            .build();
    }

    @Test
    void dispatchesCallableResult() throws Exception {
        MvcResult initialResult = mockMvc.perform(get("/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mockMvc.perform(asyncDispatch(initialResult))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello from Callable"));
    }
}
~~~

Test này có hai phần assertion riêng:

- Lần dispatch đầu xác nhận request đã chuyển sang async processing.
- Lần dispatch tiếp theo xác nhận kết quả Callable đã được Spring chuyển thành response JSON.

Nếu chỉ viết:

~~~java
mockMvc.perform(get("/callable"))
    .andExpect(status().isOk());
~~~

thì test không mô tả đúng quy trình async. Status của lần dispatch ban đầu không phải nơi phù hợp để xác nhận response cuối của Callable. Hãy lấy MvcResult và thực hiện async dispatch.

## 8. Kiểm thử DeferredResult một cách có kiểm soát

Với DeferredResult, test có thể chủ động quyết định thời điểm hoàn tất kết quả. Đây là cách kiểm thử dễ xác định và không phụ thuộc vào việc một thread nền chạy nhanh hay chậm.

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredGreetingController {

    private final GreetingService greetingService;

    DeferredGreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/deferred")
    DeferredResult<Greeting> greeting() {
        return greetingService.loadGreeting();
    }
}

interface GreetingService {
    DeferredResult<Greeting> loadGreeting();
}
~~~

Test dùng Mockito để cung cấp DeferredResult do test kiểm soát:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.request.async.DeferredResult;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DeferredGreetingControllerTests {

    private GreetingService greetingService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        greetingService = mock(GreetingService.class);
        mockMvc = MockMvcBuilders
            .standaloneSetup(new DeferredGreetingController(greetingService))
            .build();
    }

    @Test
    void dispatchesDeferredResultAfterItIsCompleted() throws Exception {
        DeferredResult<Greeting> pendingResult = new DeferredResult<>();
        when(greetingService.loadGreeting()).thenReturn(pendingResult);

        MvcResult initialResult = mockMvc.perform(get("/deferred"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pendingResult.setResult(new Greeting("Hello from DeferredResult"));

        mockMvc.perform(asyncDispatch(initialResult))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                .value("Hello from DeferredResult"));
    }
}
~~~

Điểm quan trọng là test chỉ gọi `asyncDispatch` sau khi đã gọi `pendingResult.setResult(...)`. Nếu dispatch trước khi DeferredResult hoàn tất, MockMvc sẽ phải chờ và có thể hết timeout. Chủ động giữ DeferredResult trong test giúp kiểm soát chính xác thời điểm kết quả sẵn sàng.

Trong ứng dụng thật, `setResult` thường được gọi bởi callback từ một client bất đồng bộ, một message listener hoặc một thành phần khác. Test không nhất thiết phải dựng toàn bộ hệ thống bên ngoài đó nếu mục tiêu là xác nhận controller tích hợp đúng với DeferredResult.

## 9. Kiểm tra async result trước lần dispatch thứ hai

Ngoài việc kiểm tra response cuối, có thể xác nhận giá trị async result được tạo ra. MockMvc có matcher `request().asyncResult(...)`:

~~~java
mockMvc.perform(get("/callable"))
    .andExpect(request().asyncStarted())
    .andExpect(request().asyncResult(
        new Greeting("Hello from Callable")
    ));
~~~

Hoặc đọc kết quả từ MvcResult:

~~~java
MvcResult initialResult = mockMvc.perform(get("/callable"))
    .andExpect(request().asyncStarted())
    .andReturn();

Object asyncValue = initialResult.getAsyncResult(5_000L);
~~~

`getAsyncResult(timeout)` chờ tối đa số milliseconds được truyền vào để lấy kết quả async. Nếu kết quả không có trong khoảng thời gian đó, phương thức có thể ném lỗi timeout. Dùng timeout tường minh khi muốn test có giới hạn chờ rõ ràng.

Nếu chỉ cần kiểm tra response mà không cần xem object trung gian, `asyncDispatch` thường là đủ. Nếu cần xác nhận chính Callable hoặc DeferredResult tạo ra object nào trước khi Spring serialize nó, hãy kiểm tra async result riêng.

## 10. asyncStarted không đồng nghĩa với async result đã hoàn tất

Hai khái niệm cần phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| Async đã bắt đầu | Request đã chuyển sang async mode; lần dispatch ban đầu kết thúc. |
| Async result đã sẵn sàng | Callable đã trả về hoặc DeferredResult đã được set kết quả/lỗi. |
| Async dispatch đã diễn ra | Request được xử lý lại để Spring tạo response cuối. |
| Request hoàn tất | Response cuối đã được tạo và quá trình async kết thúc. |

Với Callable chạy rất nhanh, async result có thể sẵn sàng gần như ngay lập tức. Với DeferredResult, request có thể chờ lâu hơn cho đến khi thành phần ứng dụng gọi `setResult`. Cả hai vẫn có thể làm `asyncStarted()` trả về thành công.

Vì vậy, test nên xác nhận đúng giai đoạn:

- `asyncStarted()`: xác nhận request chuyển sang async.
- `getAsyncResult(timeout)` hoặc matcher async result: xác nhận giá trị trung gian đã sẵn sàng.
- `asyncDispatch(...)`: đưa kết quả qua quy trình MVC lần nữa.
- `status()`, `jsonPath()`, `content()`: xác nhận response cuối.

## 11. Kiểm thử timeout và lỗi của DeferredResult

DeferredResult có thể được khởi tạo với timeout. Khi hết thời gian mà chưa có kết quả, Spring MVC xử lý async timeout. Ứng dụng có thể đăng ký callback để ghi nhận hoặc thiết lập error result:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.context.request.async.DeferredResult;

DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> result.setErrorResult(
    new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Greeting service timed out"
    )
));
~~~

Khi kết quả async lỗi, Spring tiếp tục xử lý exception trong async dispatch. Các cơ chế như `@ExceptionHandler`, `@ControllerAdvice` và HandlerExceptionResolver vẫn có thể tham gia tạo error response.

Có thể hoàn tất DeferredResult bằng lỗi từ phía ứng dụng:

~~~java
result.setErrorResult(
    new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "Upstream service failed"
    )
);
~~~

Trong test, nên ưu tiên điều khiển error result trực tiếp thay vì chờ timeout thật:

~~~java
DeferredResult<Greeting> pendingResult = new DeferredResult<>();
when(greetingService.loadGreeting()).thenReturn(pendingResult);

MvcResult initialResult = mockMvc.perform(get("/deferred"))
    .andExpect(request().asyncStarted())
    .andReturn();

pendingResult.setErrorResult(
    new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE)
);

mockMvc.perform(asyncDispatch(initialResult))
    .andExpect(status().isServiceUnavailable());
~~~

Ví dụ này giả định ứng dụng có cấu hình xử lý ResponseStatusException phù hợp. Nếu ứng dụng có `@ControllerAdvice` chuyển lỗi sang một response envelope riêng, hãy assertion theo hợp đồng lỗi thực tế của ứng dụng.

Không nên viết test timeout bằng cách sleep một khoảng thời gian cố định rồi hy vọng timeout xảy ra đúng lúc. Cách đó dễ gây flaky test do tốc độ máy và lịch chạy thread. Hãy kiểm soát việc hoàn tất result hoặc dùng cấu hình timeout ngắn có chủ đích và chờ bằng cơ chế đồng bộ thích hợp.

## 12. Callback của DeferredResult

DeferredResult cung cấp callback để ứng dụng quan sát vòng đời:

~~~java
DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> {
    // Ghi nhận timeout hoặc hoàn tất bằng một lỗi phù hợp.
});

result.onError(error -> {
    // Ghi nhận lỗi trong quá trình async.
});

result.onCompletion(() -> {
    // Dọn dẹp tài nguyên gắn với request async.
});
~~~

Các callback có mục đích khác nhau:

- `onTimeout` được gọi khi async request timeout.
- `onError` được gọi khi async processing gặp lỗi.
- `onCompletion` được gọi khi request async hoàn tất, bao gồm các tình huống hoàn tất thông thường hoặc kết thúc do lỗi/timeout.

Không nên đặt toàn bộ logic nghiệp vụ vào `onCompletion`, vì callback này biểu diễn vòng đời kỹ thuật của request. Nếu cần xác nhận nghiệp vụ đã thành công, hãy dựa vào kết quả hoặc event nghiệp vụ cụ thể.

Trong kiểm thử, có thể xác nhận callback được gọi bằng một spy hoặc latch, nhưng chỉ nên làm vậy khi callback là hành vi cần kiểm thử. Đối với bài test controller cơ bản, xác nhận asyncStarted và response cuối thường đủ.

## 13. Cấu hình timeout và executor

Spring MVC sử dụng async task executor để thực thi Callable. Cấu hình executor ảnh hưởng khả năng xử lý tải đồng thời, hàng đợi công việc và cách ứng dụng phản ứng khi quá tải.

Trong Spring MVC Java configuration, có thể cấu hình async support:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebAsyncConfiguration implements WebMvcConfigurer {

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
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

Đây là ví dụ minh họa cấu hình executor và timeout mặc định; trong ứng dụng thật, executor nên được quản lý như một Spring bean để lifecycle và shutdown được Spring quản lý. Khi cấu hình executor riêng, cần xác định rõ số thread, queue capacity và chính sách từ chối tác vụ phù hợp với tải của ứng dụng.

MockMvc có thể cấu hình default async request timeout:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(controller)
    .setAsyncRequestTimeout(5_000L)
    .build();
~~~

Timeout này ảnh hưởng thời gian MockMvc chờ async result trong quá trình test. Nó không thay thế timeout của business client, timeout của DeferredResult hoặc timeout cấu hình trong Servlet container. Các timeout nằm ở những tầng khác nhau và cần được thiết kế nhất quán.

## 14. Lỗi thường gặp khi kiểm thử async

### Chỉ kiểm tra status ở lần dispatch đầu

Request async chưa hoàn tất response cuối ở lần dispatch ban đầu. Hãy lấy MvcResult, sau đó dùng `asyncDispatch` để assertion status và body cuối.

### Quên kiểm tra asyncStarted

Nếu endpoint vô tình chuyển sang xử lý đồng bộ, test có thể không phát hiện sai khác về hành vi. Thêm `request().asyncStarted()` khi async processing là một phần của hợp đồng cần kiểm tra.

### Gọi asyncDispatch cho request đồng bộ

`asyncDispatch` cần MvcResult của một request đã bắt đầu async. Nếu request không async, hãy kiểm tra response ngay ở lần `perform` đầu và dùng `asyncNotStarted()` nếu cần xác nhận điều đó.

### DeferredResult chưa được hoàn tất

Nếu test giữ DeferredResult nhưng không gọi `setResult` hoặc `setErrorResult`, async dispatch phải chờ cho đến khi timeout. Hãy giữ tham chiếu DeferredResult trong test và chủ động hoàn tất nó trước khi dispatch.

### Giả định Callable luôn chạy xong trước assertion

Callable được chạy trên async executor. Thời điểm hoàn tất phụ thuộc executor và tác vụ. Dùng `asyncDispatch` hoặc `getAsyncResult(timeout)` để chờ có giới hạn, thay vì dựa vào tốc độ chạy tình cờ.

### Dùng sleep để đồng bộ test

Sleep không đảm bảo tác vụ đã hoàn tất. Với DeferredResult, hãy gọi setResult trực tiếp. Với Callable, để MockMvc chờ async result theo timeout hoặc dùng latch nếu cần phối hợp một tác vụ bên ngoài.

### Nhầm asyncStarted với response streaming

Async processing của Callable/DeferredResult cho phép response được tạo sau khi công việc hoàn tất. Điều đó không tự động có nghĩa server đang stream từng phần response. Streaming như `ResponseBodyEmitter` hoặc `SseEmitter` có lifecycle và cách kiểm thử riêng.

### Nhầm async request với @Async

`@Async` là cơ chế chạy phương thức trên executor của Spring. Async request trong Spring MVC là cơ chế Servlet request lifecycle cho phép request được dispatch lại sau khi kết quả sẵn sàng. Hai cơ chế có thể được dùng cùng nhau, nhưng không đồng nghĩa. Chỉ việc một service method có `@Async` không tự động làm request MVC chuyển sang async mode; controller cần trả về một kiểu được Spring MVC hỗ trợ cho async processing hoặc tích hợp kết quả theo cách phù hợp.

## 15. Chọn assertion theo mục tiêu kiểm thử

| Mục tiêu | Cách kiểm tra |
|---|---|
| Xác nhận controller thực sự bắt đầu async | `request().asyncStarted()` |
| Xác nhận endpoint vẫn xử lý đồng bộ | `request().asyncNotStarted()` |
| Xác nhận giá trị Callable/DeferredResult đã sẵn sàng | `MvcResult.getAsyncResult(timeout)` hoặc async result matcher |
| Mô phỏng dispatch sau khi async hoàn tất | `asyncDispatch(mvcResult)` |
| Xác nhận response thành công | `status().isOk()`, `content()`, `jsonPath()` sau asyncDispatch |
| Xác nhận error result | Hoàn tất DeferredResult bằng `setErrorResult`, rồi assertion error response sau asyncDispatch |
| Xác nhận timeout | Cấu hình timeout rõ ràng và kiểm tra error handling tương ứng; tránh sleep tùy tiện |

Khi kiểm thử `Callable`, Spring chịu trách nhiệm chạy công việc và cung cấp kết quả cho async dispatch. Khi kiểm thử `DeferredResult`, test thường có thể kiểm soát thời điểm cung cấp kết quả. Trong cả hai trường hợp, `asyncStarted()` xác nhận giai đoạn đầu của request, còn `asyncDispatch(...)` đưa kết quả qua MVC để tạo response cuối cùng.

Nắm rõ hai giai đoạn này giúp test MockMvc mô tả đúng vòng đời request bất đồng bộ, phát hiện trường hợp controller vô tình xử lý đồng bộ, và xác nhận chính xác response thành công hoặc lỗi sau khi công việc hoàn tất.
