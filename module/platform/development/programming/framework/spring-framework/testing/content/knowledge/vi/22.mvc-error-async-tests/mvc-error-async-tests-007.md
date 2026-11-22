# asyncDispatch để kiểm tra kết quả sau hoàn tất

## Vì sao cần asyncDispatch trong kiểm thử MVC?

Spring MVC hỗ trợ controller xử lý yêu cầu bất đồng bộ bằng các kiểu trả về như **Callable**, **DeferredResult**, **WebAsyncTask** và **CompletionStage**. Với các kiểu này, controller có thể khởi tạo công việc rồi trả quyền điều khiển về Servlet container trong khi kết quả vẫn chưa sẵn sàng. Khi công việc hoàn tất, Spring MVC tiếp tục xử lý kết quả và tạo HTTP response.

Trong kiểm thử bằng MockMvc, một request bất đồng bộ có hai giai đoạn quan sát:

1. Request ban đầu đi qua DispatcherServlet và controller. Spring bắt đầu async processing, sau đó lần dispatch đầu kết thúc khi kết quả cuối cùng chưa được gửi về response.
2. Khi kết quả bất đồng bộ đã sẵn sàng, test thực hiện async dispatch để Spring MVC tiếp tục xử lý kết quả, chạy các bước xử lý return value và hoàn tất response.

**asyncDispatch(mvcResult)** hỗ trợ giai đoạn thứ hai. Nó sử dụng MvcResult thu được từ request ban đầu để tạo một lần dispatch tiếp theo trong cùng luồng xử lý của MockMvc. Nhờ đó, test có thể xác nhận HTTP status, header và body cuối cùng sau khi công việc bất đồng bộ hoàn tất.

Điểm quan trọng là **request().asyncStarted()** và **asyncDispatch(...)** phục vụ hai mục đích khác nhau:

- **request().asyncStarted()** xác nhận request đã chuyển sang chế độ xử lý bất đồng bộ.
- **asyncDispatch(mvcResult)** tiếp tục xử lý kết quả đã hoàn tất để tạo response cuối cùng.

Chỉ xác nhận async đã bắt đầu chưa chứng minh controller trả về response đúng. Muốn kiểm tra kết quả MVC sau hoàn tất, test cần thực hiện async dispatch và đặt các assertion response ở lần dispatch đó.

## Luồng kiểm thử bằng MockMvc

Trình tự cơ bản:

~~~text
mockMvc.perform(request ban đầu)
        |
        v
DispatcherServlet gọi controller
        |
        v
Controller trả Callable / DeferredResult / kiểu async khác
        |
        v
Spring bắt đầu async processing
        |
        v
MvcResult ghi nhận trạng thái async
        |
        v
Kết quả async được cung cấp
        |
        v
mockMvc.perform(asyncDispatch(mvcResult))
        |
        v
Spring MVC xử lý kết quả và hoàn tất response
        |
        v
Assert status, header, content type và body
~~~

Trong code, **asyncDispatch** được import tĩnh từ MockMvcRequestBuilders; matcher **asyncStarted()** nằm trong MockMvcResultMatchers.request():

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
~~~

Luôn giữ lại MvcResult của lần request đầu tiên. Đối tượng này chứa thông tin cần thiết để MockMvc tiếp tục dispatch cùng request đã chuyển sang chế độ async.

## Kiểm tra controller trả về Callable

Callable<T> là trường hợp dễ thấy nhất: Spring MVC chạy callable bằng async task executor, nhận giá trị trả về rồi dispatch kết quả để hoàn tất response.

Ví dụ controller trả về một chuỗi:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/report")
    Callable<String> report() {
        return () -> "report-ready";
    }
}
~~~

Test cần thực hiện hai lần perform:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ReportControllerTests {

    // Giả sử mockMvc đã được cấu hình với ReportController.

    @Test
    void returnsTheCompletedCallableResult() throws Exception {
        MvcResult mvcResult = mockMvc.perform(get("/api/report"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(mvcResult))
                .andExpect(status().isOk())
                .andExpect(content().string("report-ready"));
    }
}
~~~

Ở lần perform đầu, test chỉ xác nhận request đã bắt đầu async processing và lấy MvcResult. Ở lần perform thứ hai, asyncDispatch(mvcResult) chuyển kết quả của callable qua phần xử lý còn lại của Spring MVC. Vì vậy, status và body được kiểm tra ở lần dispatch thứ hai.

Không nên đặt assertion body cuối cùng vào lần request đầu rồi cho rằng asyncStarted() đồng nghĩa response đã hoàn tất. Lúc đó request mới chỉ chuyển sang chế độ async; kết quả có thể chưa sẵn sàng và response cuối chưa được tạo.

## Kiểm tra DeferredResult khi test chủ động hoàn tất kết quả

DeferredResult<T> phù hợp khi kết quả được cung cấp bởi một thành phần khác, ví dụ callback, message listener hoặc một service quản lý tác vụ. Controller trả DeferredResult ngay, còn thành phần tạo kết quả gọi setResult(...) hoặc setErrorResult(...) khi công việc hoàn tất.

Ví dụ controller ủy quyền việc tạo báo cáo cho service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredReportController {

    private final ReportService reportService;

    DeferredReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/report/deferred")
    DeferredResult<String> report() {
        return reportService.generate();
    }
}
~~~

Trong test, tạo DeferredResult do test kiểm soát. Sau khi request ban đầu trả về và xác nhận async đã bắt đầu, test hoàn tất deferred result rồi thực hiện async dispatch:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.context.request.async.DeferredResult;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DeferredReportControllerTests {

    // reportService là mock; mockMvc đã được cấu hình với controller này.

    @Test
    void dispatchesAfterDeferredResultIsCompleted() throws Exception {
        DeferredResult<String> deferredResult = new DeferredResult<>();
        given(reportService.generate()).willReturn(deferredResult);

        MvcResult mvcResult = mockMvc.perform(get("/api/report/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        deferredResult.setResult("deferred-report-ready");

        mockMvc.perform(asyncDispatch(mvcResult))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-report-ready"));
    }
}
~~~

Test không cần chờ bằng một khoảng sleep tùy ý. Nó chủ động cung cấp kết quả thông qua setResult(...), sau đó yêu cầu MockMvc tiếp tục dispatch. Cách này giúp điều khiển rõ thời điểm hoàn tất và tránh phụ thuộc vào tốc độ của một hệ thống bên ngoài.

Trong ứng dụng thực tế, test có thể hoàn tất DeferredResult thông qua callback hoặc API của service thay vì gọi trực tiếp setResult. Điều cần bảo đảm là kết quả đã được đặt trước khi thực hiện async dispatch.

## Kiểm tra giá trị async thô trước khi dispatch

MvcResult còn cho phép đọc concurrent result được tạo ra bởi xử lý bất đồng bộ. Matcher **request().asyncResult(...)** có thể dùng để xác nhận giá trị đó trước khi tiếp tục dispatch:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/api/report"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("report-ready"))
        .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk())
        .andExpect(content().string("report-ready"));
~~~

Assertion asyncResult(...) kiểm tra giá trị mà quá trình async trả về. Assertion sau asyncDispatch(...) kiểm tra response HTTP được Spring MVC tạo từ giá trị đó. Hai assertion này xác nhận hai tầng khác nhau:

- Giá trị async thô: kết quả từ Callable, DeferredResult hoặc kiểu async tương ứng.
- Kết quả MVC cuối: status, header, content type và body sau khi Spring xử lý return value.

Với DeferredResult, chỉ dùng matcher asyncResult(...) sau khi thành phần tạo kết quả đã gọi setResult(...) hoặc setErrorResult(...). Nếu chưa hoàn tất, matcher phải chờ kết quả và có thể hết thời gian chờ.

Không bắt buộc phải kiểm tra cả hai tầng trong mọi test. Nếu mục tiêu là hợp đồng HTTP, assertion ở lần async dispatch thường là phần quan trọng nhất. Kiểm tra async result thô hữu ích khi muốn phân biệt lỗi ở tác vụ nền với lỗi chuyển đổi kết quả thành response.

## Kiểm tra response JSON sau async dispatch

Nếu controller trả DTO hoặc ResponseEntity, Spring MVC vẫn sử dụng các HttpMessageConverter để tạo response sau khi kết quả async được dispatch. Có thể kiểm tra JSON bằng các matcher thông thường ở lần dispatch thứ hai:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/api/report/summary"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "reportId": 42,
                  "state": "READY"
                }
                """, true));
~~~

Không cần một bộ matcher riêng cho async response. Sau khi async dispatch hoàn tất, test dùng status(), header(), content() và jsonPath() như với response MVC thông thường.

## Xử lý lỗi và timeout trong async request

Kết quả bất đồng bộ có thể là lỗi thay vì giá trị thành công. Ví dụ Callable ném exception hoặc DeferredResult được hoàn tất bằng setErrorResult(...). Khi async dispatch tiếp tục, Spring MVC xử lý exception theo cơ chế exception resolver, @ExceptionHandler hoặc @ControllerAdvice đang áp dụng.

Ví dụ service trả về DeferredResult và test hoàn tất nó bằng lỗi:

~~~java
DeferredResult<String> deferredResult = new DeferredResult<>();
given(reportService.generate()).willReturn(deferredResult);

MvcResult mvcResult = mockMvc.perform(get("/api/report/deferred"))
        .andExpect(request().asyncStarted())
        .andReturn();

deferredResult.setErrorResult(new IllegalStateException("Report failed"));

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isInternalServerError())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("REPORT_FAILED"));
~~~

Status và JSON ở ví dụ trên phụ thuộc @ControllerAdvice của ứng dụng ánh xạ IllegalStateException thành response lỗi như vậy. Nếu ứng dụng dùng exception mapping khác, assertion phải phản ánh đúng hợp đồng đó. Mục tiêu là kiểm tra response sau khi exception được xử lý trong lần dispatch tiếp theo.

Async request cũng có thể hết thời gian chờ. DeferredResult có thể được tạo với timeout và callback xử lý timeout; WebAsyncTask cũng hỗ trợ timeout riêng. Nếu cần kiểm tra timeout, hãy điều khiển timeout bằng cấu hình hoặc callback rõ ràng, rồi xác nhận response cuối qua async dispatch. Không dựa vào Thread.sleep(...) để đoán thời điểm timeout.

MockMvc có thể cấu hình thời gian chờ cho async request bằng setAsyncRequestTimeout(...) trên builder, ví dụ:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setAsyncRequestTimeout(5_000L)
        .build();
~~~

Thời gian chờ này đặt giới hạn cho việc MockMvc chờ kết quả async trong test. Nó không thay thế timeout nghiệp vụ của DeferredResult hoặc WebAsyncTask; hai loại timeout có mục đích khác nhau. Khi test thất bại do không nhận được kết quả, cần xác định đó là tác vụ chưa hoàn tất, timeout của tác vụ, hay thời gian chờ của test.

## Những điểm cần chú ý khi dùng asyncDispatch

### Phải lấy MvcResult từ request đã bắt đầu async

asyncDispatch(...) cần MvcResult của lần request ban đầu. Nếu request không chuyển sang async processing, việc gọi async dispatch không phù hợp và sẽ thất bại. Matcher request().asyncStarted() giúp phát hiện sớm controller đã thực sự khởi động async hay chưa.

### Không gọi lại endpoint để lấy kết quả

Lần dispatch thứ hai phải dùng asyncDispatch(mvcResult), không phải get("/api/report") lần nữa. Gọi lại endpoint sẽ tạo một request mới, có thể khởi chạy một tác vụ mới và không kiểm tra kết quả của request ban đầu.

### Đặt assertion response ở lần dispatch cuối

Lần đầu dùng để xác nhận async đã bắt đầu và lấy MvcResult. Lần sau dùng để xác nhận response cuối. Việc tách hai giai đoạn giúp test chỉ rõ lỗi nằm ở bước khởi tạo async hay bước hoàn tất xử lý MVC.

### Đảm bảo kết quả thực sự hoàn tất

Với Callable, Spring quản lý việc thực thi và cung cấp concurrent result. Với DeferredResult, ứng dụng hoặc test phải gọi setResult(...) hay setErrorResult(...). Nếu không có kết quả trước giới hạn chờ, async dispatch có thể timeout hoặc thất bại.

### Không dùng Thread.sleep để đồng bộ test

Thread.sleep(...) chỉ trì hoãn thread kiểm thử, không chứng minh tác vụ nền đã xong. Ưu tiên điều khiển DeferredResult, CompletableFuture, latch hoặc tín hiệu hoàn tất có thể quan sát. Khi kiểm tra một tác vụ thực sự chạy nền, hãy chờ điều kiện hoàn tất với timeout hữu hạn để test không treo vô thời hạn.

### Phân biệt xử lý MVC với hành vi của Servlet container thật

MockMvc kiểm tra tích hợp Spring MVC trong môi trường Servlet mô phỏng. Nó rất phù hợp để xác nhận Callable hoặc DeferredResult được dispatch và chuyển thành response đúng. Tuy nhiên, test này không thay thế kiểm thử trên embedded server thật nếu cần xác nhận hành vi riêng của container, socket, connector, thread pool hoặc triển khai filter async ở môi trường chạy thực tế.

## Quy trình kiểm thử async hoàn chỉnh

1. Gửi request ban đầu bằng mockMvc.perform(...).
2. Xác nhận request đã bắt đầu async bằng request().asyncStarted().
3. Lưu MvcResult bằng andReturn().
4. Bảo đảm công việc async đã tạo ra kết quả. Với DeferredResult, test hoặc callback gọi setResult(...) / setErrorResult(...).
5. Nếu cần phân biệt kết quả của tác vụ với response MVC, kiểm tra thêm request().asyncResult(...) hoặc mvcResult.getAsyncResult(...) với thời gian chờ phù hợp.
6. Gọi mockMvc.perform(asyncDispatch(mvcResult)).
7. Kiểm tra status, header, content type và body cuối cùng bằng các matcher MVC thông thường.

asyncDispatch là bước nối giữa kết quả bất đồng bộ và response cuối cùng của Spring MVC. Khi test tách rõ lần request ban đầu, thời điểm hoàn tất và lần dispatch tiếp theo, nó có thể xác nhận chính xác cả trạng thái async lẫn hợp đồng HTTP mà client thực sự nhận được.
