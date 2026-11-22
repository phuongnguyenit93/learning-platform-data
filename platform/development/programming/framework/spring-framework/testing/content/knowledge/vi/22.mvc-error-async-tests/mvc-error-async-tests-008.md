# Thời gian chờ và ngoại lệ trong xử lý bất đồng bộ

## 1. Vòng đời bất đồng bộ trong Spring MVC

Spring MVC hỗ trợ controller trả về kiểu bất đồng bộ như `Callable`, `DeferredResult` và `WebAsyncTask`. Khi gặp một trong các kiểu này, Spring bắt đầu xử lý Servlet asynchronous, cho phép thread của container kết thúc việc xử lý ban đầu trong khi kết quả vẫn đang được tạo.

Khi kết quả sẵn sàng, Spring MVC thực hiện một lần dispatch tiếp theo để hoàn tất xử lý response qua các thành phần MVC như return value handler, message converter và exception resolver. Vì vậy, xử lý bất đồng bộ vẫn nằm trong vòng đời request HTTP; nó chỉ tách thời điểm tạo kết quả khỏi thread ban đầu.

Luồng tổng quát:

```text
HTTP request
    |
    v
DispatcherServlet gọi controller
    |
    v
Controller trả về Callable / DeferredResult / WebAsyncTask
    |
    v
Spring bắt đầu Servlet async và giải phóng thread ban đầu
    |
    +-------------------------------+
    |                               |
    v                               v
Kết quả đến trước timeout       Timeout hoặc lỗi xảy ra
    |                               |
    v                               v
Lưu kết quả async               Tạo kết quả timeout/lỗi
    |                               |
    +---------------+---------------+
                    |
                    v
          Async dispatch vào MVC
                    |
                    v
          Tạo response HTTP cuối cùng
```

Thời gian chờ quyết định request được phép ở trạng thái async bao lâu. Ngoại lệ quyết định cách MVC chuyển một lỗi trong quá trình xử lý thành response. Hai vấn đề liên quan với nhau nhưng không đồng nhất: một request có thể timeout dù không có exception nghiệp vụ, và một tác vụ có thể ném exception trước khi hết thời gian chờ.

## 2. Các nguồn timeout cần phân biệt

Trong một request bất đồng bộ có thể tồn tại nhiều giới hạn thời gian:

| Loại thời gian chờ | Phạm vi | Ý nghĩa |
|---|---|---|
| MVC async request timeout | Vòng đời Servlet async do Spring MVC quản lý | Giới hạn thời gian chờ kết quả của `Callable`, `DeferredResult` hoặc kiểu async khác. |
| Timeout theo từng request | `DeferredResult` hoặc `WebAsyncTask` | Ghi đè hoặc xác định thời gian chờ riêng cho một lần xử lý. |
| Timeout của container | Servlet container | Giới hạn async request ở tầng container; giá trị mặc định phụ thuộc cấu hình server/container. |
| Business deadline | Logic ứng dụng hoặc dịch vụ phụ thuộc | Giới hạn thời gian nghiệp vụ, ví dụ chỉ chờ một dịch vụ bên ngoài tối đa vài giây. |
| Client timeout | HTTP client, gateway hoặc reverse proxy | Giới hạn thời gian phía gọi chờ response; có thể ngắn hơn timeout phía server. |

Các timeout này có thể tác động lên cùng request. Ví dụ, gateway có thể ngừng chờ sau 3 giây trong khi server vẫn đang thực hiện tác vụ với deadline 5 giây. Khi thiết kế, cần đặt thời gian chờ phù hợp với toàn bộ chuỗi gọi và chừa khoảng thời gian cho server xử lý lỗi, hoàn tất response và ghi log.

Không nên mặc định rằng mọi timeout đều tự động hủy công việc đang chạy. Việc response HTTP đã timeout không đảm bảo truy vấn cơ sở dữ liệu, lời gọi dịch vụ hoặc tác vụ nền đã dừng. Nếu cần dừng công việc, ứng dụng phải có cơ chế hủy hoặc deadline riêng và tác vụ phải hợp tác với cơ chế đó.

## 3. Cấu hình timeout mặc định cho Spring MVC

Có thể đặt timeout mặc định cho các request async thông qua `WebMvcConfigurer` và `AsyncSupportConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcAsyncConfiguration implements WebMvcConfigurer {

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(10_000L);
    }
}
```

Giá trị được tính bằng milliseconds; ví dụ trên đặt thời gian mặc định là 10 giây. Nếu không cấu hình giá trị này, timeout có thể phụ thuộc mặc định của Servlet container và cấu hình runtime. Vì vậy, ứng dụng cần xác định rõ timeout mong muốn thay vì dựa vào một giá trị mặc định không được kiểm soát.

`AsyncSupportConfigurer` cũng cho phép cấu hình `AsyncTaskExecutor` cho các tác vụ `Callable`. Executor cần có giới hạn thread và hàng đợi phù hợp với tải dự kiến. Một executor không giới hạn có thể làm cạn tài nguyên khi nhiều request chờ đồng thời; executor quá nhỏ hoặc hàng đợi quá dài có thể khiến tác vụ chưa kịp chạy đã tiêu thụ phần lớn thời gian chờ.

Timeout mặc định là chính sách chung. Với một endpoint có thời gian xử lý khác biệt, nên cân nhắc timeout riêng theo request để phản ánh đúng yêu cầu của endpoint đó.

## 4. Timeout riêng với `DeferredResult`

`DeferredResult<T>` phù hợp khi kết quả được hoàn tất bởi một thành phần khác, chẳng hạn callback từ message broker, event listener hoặc một dịch vụ bất đồng bộ. Controller trả `DeferredResult` ngay, còn ứng dụng gọi `setResult(...)` khi có dữ liệu.

Có thể chỉ định timeout bằng constructor và đăng ký callback khi hết thời gian:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class JobController {

    private final JobService jobService;

    JobController(JobService jobService) {
        this.jobService = jobService;
    }

    @GetMapping("/jobs/latest")
    DeferredResult<ResponseEntity<JobView>> latestJob() {
        DeferredResult<ResponseEntity<JobView>> result =
                new DeferredResult<>(3_000L);

        result.onTimeout(() -> result.setErrorResult(
                new JobWaitTimeoutException("No job result arrived in time")));

        jobService.findLatestAsync(
                job -> result.setResult(ResponseEntity.ok(job)),
                error -> result.setErrorResult(error));

        return result;
    }
}
```

`JobService` trong ví dụ đại diện cho thành phần ứng dụng có thể gọi callback thành công hoặc callback lỗi khi công việc hoàn tất. `JobView` là kiểu dữ liệu response của ứng dụng. `JobWaitTimeoutException` là exception nghiệp vụ do ứng dụng định nghĩa.

Callback `onTimeout` được gọi khi request async hết thời gian chờ. Callback có thể cung cấp kết quả thay thế bằng `setResult(...)` hoặc chuyển sang luồng xử lý lỗi bằng `setErrorResult(...)`. Ví dụ chọn cách thứ hai để exception resolver quyết định response lỗi.

`setResult(...)` và `setErrorResult(...)` trả về boolean cho biết kết quả có được chấp nhận hay không. Điều này hữu ích khi callback hoàn tất và callback timeout có thể chạy gần như đồng thời. Chỉ một kết quả được chấp nhận; ứng dụng nên xử lý trường hợp kết quả đến muộn theo chính sách của mình, thay vì giả định lần gọi nào cũng thành công.

Nếu không đăng ký timeout callback hoặc callback không thiết lập kết quả, Spring MVC tiếp tục xử lý timeout theo cơ chế mặc định, thường thông qua `AsyncRequestTimeoutException` và hệ thống `HandlerExceptionResolver`.

## 5. Timeout riêng với `WebAsyncTask`

`WebAsyncTask<T>` bọc một `Callable<T>` và cho phép khai báo timeout cùng các callback cho timeout, lỗi và hoàn tất. Đây là lựa chọn phù hợp khi controller muốn tự xác định thời gian chờ và cách trả kết quả dự phòng cho một tác vụ Callable.

```java
import java.util.concurrent.Callable;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/summary")
    WebAsyncTask<ResponseEntity<String>> summary() {
        Callable<ResponseEntity<String>> work =
                () -> ResponseEntity.ok(reportService.buildSummary());

        WebAsyncTask<ResponseEntity<String>> task =
                new WebAsyncTask<>(2_000L, work);

        task.onTimeout(() -> ResponseEntity
                .status(HttpStatus.GATEWAY_TIMEOUT)
                .body("Report generation timed out"));

        task.onError(() -> ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("Report generation failed"));

        return task;
    }
}
```

Trong ví dụ, callback timeout trả về một response thay thế với status `504`. Callback lỗi trả về response `503`. Đây là chính sách API minh họa; ứng dụng cần chọn status và nội dung phù hợp với ý nghĩa nghiệp vụ và hợp đồng HTTP của mình. Nếu callback timeout không cung cấp kết quả thay thế, Spring MVC xử lý timeout theo luồng exception thông thường.

`WebAsyncTask` cũng có thể nhận tên executor đã được đăng ký để chạy Callable. Khi dùng executor tùy chỉnh, hãy kiểm tra cấu hình executor và năng lực xử lý dưới tải; timeout của request không thay thế cho quản lý thread pool.

## 6. Xử lý exception từ `Callable` và `DeferredResult`

Với `Callable`, exception phát sinh trong tác vụ được Spring MVC ghi nhận như kết quả bất đồng bộ. Khi async dispatch tiếp tục, exception được đưa qua cơ chế giải quyết lỗi MVC. Vì vậy, có thể dùng `@ExceptionHandler` hoặc `@ControllerAdvice` như với xử lý đồng bộ.

Với `DeferredResult`, callback của ứng dụng cần chuyển lỗi thành `setErrorResult(exception)`. Exception phát sinh ở một event listener hoặc thread khác không tự động được ném vào thread xử lý request ban đầu. Nếu chỉ để exception thoát khỏi callback ở thread nền, MVC có thể không biết rằng request đang chờ cần trả lỗi.

Ví dụ khai báo exception handler tập trung:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record ApiError(String code, String message) {
}

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(JobWaitTimeoutException.class)
    ResponseEntity<ApiError> handleJobTimeout(JobWaitTimeoutException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("JOB_WAIT_TIMEOUT", ex.getMessage()));
    }

    @ExceptionHandler(ReportUnavailableException.class)
    ResponseEntity<ApiError> handleReportUnavailable(ReportUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("REPORT_UNAVAILABLE", "Report is temporarily unavailable"));
    }
}
```

`JobWaitTimeoutException` và `ReportUnavailableException` là các kiểu exception do ứng dụng định nghĩa. Handler có thể trả `ResponseEntity`, DTO lỗi hoặc kiểu dữ liệu response khác. Spring MVC xử lý kết quả này trong lần dispatch hoàn tất request async.

Nếu muốn xử lý timeout mặc định do Spring MVC tạo ra, có thể khai báo handler cho `AsyncRequestTimeoutException`:

```java
import org.springframework.web.context.request.async.AsyncRequestTimeoutException;

@ExceptionHandler(AsyncRequestTimeoutException.class)
ResponseEntity<ApiError> handleMvcTimeout(AsyncRequestTimeoutException ex) {
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("ASYNC_REQUEST_TIMEOUT", "The request timed out"));
}
```

Handler này nên được đặt trong `@RestControllerAdvice` cùng các handler phù hợp khác. Việc ánh xạ timeout sang HTTP status nào là quyết định của API; hãy giữ nhất quán với ý nghĩa timeout mà client có thể xử lý.

## 7. Callback vòng đời và xử lý lỗi

`DeferredResult` cung cấp các callback để ứng dụng quan sát vòng đời async:

| Callback | Khi nào được gọi | Mục đích |
|---|---|---|
| `onTimeout(...)` | Request async hết thời gian chờ | Đặt kết quả dự phòng hoặc `setErrorResult(...)`. |
| `onError(...)` | Có lỗi trong quá trình xử lý async ở tầng Servlet | Ghi nhận hoặc phản ứng với lỗi từ quá trình async. |
| `onCompletion(...)` | Request async đã hoàn tất | Giải phóng tài nguyên hoặc ghi nhận kết thúc xử lý. |

Các callback này không thay thế exception handler. Callback phục vụ quản lý vòng đời và kết nối với công việc bất đồng bộ; `@ExceptionHandler` chịu trách nhiệm chuyển exception thành response theo chính sách MVC.

Ví dụ đăng ký callback hoàn tất:

```java
DeferredResult<String> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> result.setErrorResult(
        new JobWaitTimeoutException("The operation took too long")));

result.onError(error -> logger.warn("Async request failed", error));

result.onCompletion(() -> logger.debug("Async request completed"));
```

Đoạn code trên giả định `logger` đã được khai báo trong class. Không nên giữ tài nguyên như lock, connection hoặc request context cho đến khi callback hoàn tất nếu tài nguyên đó có thể được giải phóng sớm hơn. Mọi nhánh thành công, lỗi, timeout và hủy đều cần có chiến lược dọn dẹp phù hợp.

## 8. Kiểm thử async result bằng MockMvc

Với request bất đồng bộ, `MockMvc.perform(...)` thường trả về trước khi response cuối cùng được tạo. Test cần xác nhận request đã bắt đầu async, chờ kết quả hoàn tất, rồi thực hiện `asyncDispatch(...)` để kiểm tra response sau cùng.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.mockito.Mockito.when;

@WebMvcTest(ReportController.class)
class ReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ReportService reportService;

    @Test
    void completesAsyncRequest() throws Exception {
        when(reportService.buildSummary()).thenReturn("ready");

        MvcResult result = mockMvc.perform(get("/reports/summary"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mockMvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().string("ready"));
    }
}
```

Endpoint `/reports/summary` trong ví dụ trả về `WebAsyncTask<ResponseEntity<String>>`; mock `ReportService` tạo nội dung `ready`. `getAsyncResult(5_000L)` chờ tối đa 5 giây để nhận kết quả async; nếu không có kết quả trong giới hạn đó, test thất bại thay vì chờ vô hạn. `asyncDispatch(result)` tiếp tục xử lý kết quả qua Spring MVC để các matcher status và content kiểm tra response cuối cùng.

Có thể kiểm tra exception tương tự: endpoint trả về `Callable` ném một exception nghiệp vụ, test xác nhận `asyncStarted()`, chờ async result, sau đó `asyncDispatch(...)` và kiểm tra status cùng body do `@RestControllerAdvice` tạo ra.

Với timeout thực tế, cần phân biệt hai điều cần kiểm thử:

- Logic timeout của ứng dụng: callback timeout đặt đúng error result hoặc response dự phòng. Có thể kiểm thử riêng callback/đơn vị điều phối bằng cơ chế điều khiển thời gian hoặc scheduler giả nếu ứng dụng đã tách logic này thành thành phần có thể thay thế.
- Hành vi timeout của Servlet container: request thực sự hết hạn và response được hoàn tất theo cấu hình runtime. Nên có kiểm thử tích hợp chạy với embedded Servlet container hoặc môi trường tương đương production, vì mock async context không mô phỏng đầy đủ lịch timeout của mọi container.

Tránh dùng `Thread.sleep(...)` ngắn để đồng bộ test. Cách đó phụ thuộc tải máy và dễ tạo test chập chờn. Hãy dùng `getAsyncResult(timeout)` với giới hạn chờ đủ rộng, latch hoặc công cụ điều khiển thời gian phù hợp với cấu trúc test.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test kiểm tra body ngay sau `perform(...)` nhưng body chưa sẵn sàng | Request đã chuyển sang async và chưa có lần dispatch hoàn tất. | Xác nhận `asyncStarted()`, chờ `getAsyncResult(...)`, rồi gọi `asyncDispatch(...)`. |
| Request timeout dù tác vụ cuối cùng vẫn hoàn thành | Kết quả đến sau giới hạn timeout của request. | Điều chỉnh deadline, tối ưu tác vụ hoặc trả trạng thái timeout theo hợp đồng API. |
| Exception từ thread nền không được chuyển thành response lỗi | Callback bất đồng bộ không gọi `DeferredResult.setErrorResult(...)`. | Chuyển exception vào `DeferredResult` để MVC tiếp tục xử lý qua exception resolver. |
| Timeout response không dừng công việc nền | Timeout kết thúc việc chờ HTTP nhưng công việc có thể vẫn đang chạy. | Thiết kế cancellation/deadline cho tác vụ và giải phóng tài nguyên khi không còn cần kết quả. |
| Nhiều request async bị chậm khi tải tăng | Executor thiếu thread, hàng đợi quá dài hoặc công việc chặn thread quá lâu. | Cấu hình pool có giới hạn, đo queue/rejection và đặt giới hạn concurrency phù hợp. |
| Handler timeout không được gọi như mong đợi | Timeout được xử lý bằng callback riêng, response đã được hoàn tất hoặc exception thuộc loại khác. | Xác định nhánh timeout đang dùng: callback `onTimeout`, `WebAsyncTask` callback hay `AsyncRequestTimeoutException`. |
| Test timeout chạy không ổn định | Phụ thuộc `sleep`, timeout quá ngắn hoặc mock container không mô phỏng lịch timeout thực. | Điều khiển thời gian trong unit test và dùng embedded container cho hành vi timeout thực. |

Một response chỉ có thể được tạo hoặc thay thế khi quá trình xử lý còn cho phép ghi response. Nếu response đã commit hoặc client đã ngắt kết nối, exception handler không thể bảo đảm gửi thêm một response lỗi hoàn chỉnh. Vì vậy, log và metric của tác vụ nền vẫn cần thiết ngay cả khi client không còn nhận được kết quả.

## 10. Nguyên tắc thiết kế timeout và exception

- Đặt timeout mặc định ở cấu hình MVC để có chính sách chung, sau đó chỉ ghi đè theo request khi yêu cầu nghiệp vụ thực sự khác.
- Đặt deadline cho lời gọi phụ thuộc bên ngoài ngắn hơn hoặc tương thích với deadline của request tổng thể, để ứng dụng còn thời gian xử lý kết quả và lỗi.
- Dùng `DeferredResult.setErrorResult(...)` khi exception phát sinh ở callback hoặc thread không phải thread xử lý request ban đầu.
- Dùng `@ControllerAdvice` để giữ định dạng lỗi nhất quán giữa xử lý đồng bộ và bất đồng bộ.
- Phân biệt timeout, lỗi nghiệp vụ, lỗi hạ tầng và client disconnect; mỗi loại có thể cần log, metric và HTTP status khác nhau.
- Không xem timeout HTTP là cơ chế hủy tác vụ. Thiết kế cancellation, deadline và cleanup riêng cho công việc có thể tiếp tục sau khi request kết thúc.
- Kiểm thử kết quả async bằng `asyncDispatch(...)`; kiểm thử lịch timeout của container trong môi trường có Servlet container thực.

## 11. Kết luận

Spring MVC cho phép cấu hình timeout chung qua `AsyncSupportConfigurer` và timeout riêng qua `DeferredResult` hoặc `WebAsyncTask`. Khi kết quả đến muộn, callback timeout có thể cung cấp kết quả dự phòng hoặc chuyển lỗi qua `setErrorResult(...)`. Exception từ `Callable` và exception được chuyển vào `DeferredResult` tiếp tục đi qua cơ chế xử lý lỗi MVC, nên có thể dùng `@ControllerAdvice` để chuẩn hóa response. Khi kiểm thử, cần chờ async result và gọi `asyncDispatch(...)`; hành vi timeout của Servlet container nên được xác nhận bằng kiểm thử tích hợp phù hợp.
