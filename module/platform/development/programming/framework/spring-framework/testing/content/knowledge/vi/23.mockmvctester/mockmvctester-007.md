# Xác nhận lỗi hoặc kết quả bất đồng bộ

`MockMvcTester` cung cấp API AssertJ để kiểm tra request và response của Spring MVC. Với request thành công, test thường xác nhận status và body. Với request lỗi hoặc xử lý bất đồng bộ, cần hiểu rõ request đã kết thúc theo cách nào: exception được Spring MVC giải quyết thành HTTP response, exception thoát khỏi quá trình dispatch, hay request mới chỉ bắt đầu xử lý async và chưa có response cuối cùng.

`MockMvcTester` vẫn chạy trên hạ tầng MockMvc. Nó không thay đổi luồng xử lý của `DispatcherServlet`, `HandlerExceptionResolver` hoặc cơ chế async của Spring MVC. Khi cần kiểm tra chi tiết vòng đời async, có thể lấy `MvcResult` bên dưới và dùng `asyncDispatch(...)` của MockMvc.

## 1. Ba loại kết quả cần phân biệt

Trong một bài kiểm thử MVC, “request lỗi” có thể chỉ những tình huống khác nhau:

1. **Exception được giải quyết:** controller ném exception, sau đó `@ExceptionHandler`, `@ControllerAdvice` hoặc resolver mặc định chuyển nó thành response HTTP. Test nhận được status và body để kiểm tra.
2. **Exception không được giải quyết:** không có resolver nào xử lý exception, vì vậy lỗi có thể thoát khỏi quá trình dispatch. MockMvc ghi nhận lỗi thực thi thay vì một response bình thường hoàn chỉnh.
3. **Request async:** controller trả về `Callable`, `DeferredResult`, `CompletableFuture` hoặc kiểu async khác. Lần dispatch đầu có thể kết thúc khi công việc nền chưa hoàn tất; test phải dispatch kết quả async để kiểm tra response cuối cùng.

Ba tình huống này không thể được kiểm tra bằng cùng một assertion. Status 500, chẳng hạn, có thể là response do ứng dụng chủ động tạo ra, còn exception không được giải quyết có thể khiến lời gọi MockMvc ném lỗi ra ngoài.

## 2. Kiểm tra exception được giải quyết thành HTTP response

Đây là tình huống thường gặp nhất khi controller sử dụng `@ExceptionHandler` hoặc `@RestControllerAdvice`. Controller ném exception, nhưng Spring MVC bắt và chuyển exception đến resolver phù hợp. `MockMvcTester` nhận được kết quả HTTP để AssertJ kiểm tra.

Ví dụ exception:

```java
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}
```

Controller:

```java
@RestController
public class OrderController {

    @GetMapping("/orders/{id}")
    public Map<String, Object> find(@PathVariable long id) {
        if (id == 77L) {
            throw new OrderNotFoundException(id);
        }
        return Collections.<String, Object>singletonMap("id", id);
    }
}
```

Exception handler:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(
            OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

Test dùng MockMvcTester:

```java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void returnsNotFoundWhenOrderDoesNotExist() {
        assertThat(mvc.get().uri("/orders/{id}", 77))
                .hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson()
                .extractingPath("$.error")
                .isEqualTo("Order 77 was not found");
    }
}
```

Test kiểm tra response mà client nhận được: HTTP 404 và JSON có trường `error`. Exception đã được giải quyết, nên test không cần bắt exception bằng `assertThrows`.

Có thể kiểm tra thêm content type hoặc header nếu chúng là một phần của hợp đồng API. Với lỗi validation, authentication hoặc authorization, cần nạp đúng cấu hình tương ứng để response được tạo theo chính sách của ứng dụng.

## 3. Đọc exception đã được Spring MVC giải quyết

Khi cần xác nhận loại exception gốc, có thể lấy `MvcTestResult` rồi đọc `MvcResult` bên dưới. `MvcTestResult` biểu diễn kết quả thực thi request của MockMvcTester; với request đã được dispatch thành công, `getMvcResult()` cung cấp kết quả MVC chi tiết.

```java
MvcTestResult testResult = mvc.get().uri("/orders/{id}", 77);

assertThat(testResult.getMvcResult().getResolvedException())
        .isInstanceOf(OrderNotFoundException.class);
```

`getResolvedException()` trả về exception được ghi nhận trong quá trình exception resolution, hoặc `null` nếu không có exception được giải quyết. Exception có thể xuất hiện ở đây ngay cả khi `@RestControllerAdvice` đã xử lý nó và response 404 đã được tạo thành công.

Để xác nhận đầy đủ hành vi, nên kết hợp kiểm tra exception với status và body:

```java
MvcTestResult testResult = mvc.get().uri("/orders/{id}", 77);

assertThat(testResult)
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.error")
        .isEqualTo("Order 77 was not found");

assertThat(testResult.getMvcResult().getResolvedException())
        .isInstanceOf(OrderNotFoundException.class);
```

Assertion về status/body cho biết kết quả quan sát được; assertion về `getResolvedException()` cho biết nguyên nhân đã được MVC xử lý. Không nên dùng riêng exception để kết luận response contract đúng.

## 4. Kiểm tra exception không được giải quyết

Nếu controller ném exception và không có `HandlerExceptionResolver` nào xử lý, exception có thể thoát khỏi `DispatcherServlet`. Khác với exception được ánh xạ thành response, đây là lỗi thực thi request.

Ví dụ endpoint cố ý ném lỗi không có handler:

```java
@RestController
public class DiagnosticController {

    @GetMapping("/diagnostics/failure")
    public String fail() {
        throw new IllegalStateException("Unexpected diagnostic failure");
    }
}
```

MockMvcTester giữ thông tin lỗi thực thi trong `MvcTestResult`. Có thể kiểm tra failure và nguyên nhân bằng AssertJ:

```java
MvcTestResult testResult = mvc.get().uri("/diagnostics/failure");

assertThat(testResult.getFailure())
        .isNotNull()
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

`getFailure()` là lỗi thực thi được MockMvcTester ghi nhận khi request không tạo được kết quả dispatch bình thường. Tùy vị trí phát sinh, exception có thể được bọc trong một exception khác; vì vậy `hasRootCauseInstanceOf(...)` thường hữu ích hơn việc phụ thuộc vào một lớp wrapper cụ thể.

Nếu ứng dụng đã có exception handler toàn cục chuyển `IllegalStateException` thành HTTP 500, request sẽ được giải quyết và test nên kiểm tra response 500 cùng body. Khi đó không nên kỳ vọng `getFailure()` có exception chưa được xử lý.

### Không nhầm response lỗi với failure của test

| Tình huống | Điều test nhận được | Cách xác nhận |
| --- | --- | --- |
| `@ExceptionHandler` tạo HTTP 404 | Kết quả HTTP bình thường | `hasStatus(HttpStatus.NOT_FOUND)` và kiểm tra body |
| Resolver mặc định ánh xạ exception thành status | Kết quả HTTP bình thường | Kiểm tra status, header và body theo cấu hình |
| Exception thoát khỏi dispatch | Failure trong `MvcTestResult` | Kiểm tra `getFailure()` và root cause |
| Request bị Spring Security từ chối trước controller | Response bảo mật như 401, 403 hoặc redirect | Kiểm tra status/redirect và cấu hình filter chain |

Một response 500 được tạo có chủ đích vẫn là response HTTP; nó không nhất thiết là failure của MockMvcTester. Ngược lại, exception không được giải quyết có thể khiến test phải kiểm tra failure thay vì status.

## 5. Request bất đồng bộ trong Spring MVC

Controller có thể trả kết quả async để không giữ request thread trong suốt thời gian chờ công việc hoàn tất. Spring MVC hỗ trợ một số kiểu trả về như:

- `Callable<T>`: Spring MVC chạy tác vụ trong executor và xử lý kết quả khi callable hoàn tất.
- `DeferredResult<T>`: thành phần khác có thể hoàn tất kết quả sau đó, chẳng hạn callback từ một dịch vụ hoặc event.
- `CompletionStage<T>`/`CompletableFuture<T>`: kết quả được cung cấp khi future hoàn thành.
- `WebAsyncTask<T>`: cho phép cấu hình thêm timeout, executor và callback cho tác vụ async.

Trong MockMvc, request async có hai giai đoạn chính:

1. Dispatch ban đầu gọi controller và nhận ra kết quả chưa sẵn sàng. Request chuyển sang trạng thái async.
2. Khi kết quả hoàn tất, test dùng `asyncDispatch(...)` để tiếp tục xử lý kết quả qua `DispatcherServlet` và nhận response cuối cùng.

Sơ đồ:

```text
MockMvc request
      |
      v
Initial DispatcherServlet dispatch
      |
      v
Controller returns Callable / DeferredResult / Future
      |
      v
Async started; initial MvcResult returned
      |
      v
Background work completes
      |
      v
asyncDispatch(initialMvcResult)
      |
      v
Final MVC dispatch and response
      |
      v
Assert final status, headers and body
```

`MockMvcTester` có thể thực hiện request đầu và cung cấp `MvcTestResult`. Để điều khiển rõ hai giai đoạn và dùng `asyncDispatch`, lấy `MvcResult` bên dưới rồi dùng MockMvc tương ứng.

## 6. Xác nhận async đã bắt đầu và kiểm tra kết quả cuối

Ví dụ controller trả `Callable`:

```java
@RestController
public class AsyncOrderController {

    @GetMapping("/async-orders/{id}")
    public Callable<Map<String, Object>> findAsync(@PathVariable long id) {
        return () -> Collections.<String, Object>singletonMap("id", id);
    }
}
```

Test có thể dùng MockMvcTester cho request ban đầu, rồi dùng MockMvc để dispatch kết quả async:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AsyncOrderControllerTest {

    @Autowired
    private MockMvcTester mvcTester;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCompletedAsyncResult() throws Exception {
        MvcTestResult initialResult =
                mvcTester.get().uri("/async-orders/{id}", 12);

        MvcResult initialMvcResult = initialResult.getMvcResult();
        assertThat(initialMvcResult.getRequest().isAsyncStarted()).isTrue();

        mockMvc.perform(asyncDispatch(initialMvcResult))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(12));
    }
}
```

Lần thực thi đầu chỉ xác nhận request đã chuyển sang async. Assertion `isAsyncStarted()` cho biết Spring MVC đã bắt đầu xử lý bất đồng bộ; nó không khẳng định response cuối đã được ghi. `asyncDispatch(...)` đưa kết quả hoàn tất trở lại luồng dispatch để test kiểm tra status và JSON cuối cùng.

Trong ví dụ này, `Callable` hoàn thành nhanh nên async result thường đã sẵn sàng khi `asyncDispatch` được gọi. Với `DeferredResult` hoặc tác vụ phụ thuộc một callback bên ngoài, test phải hoàn tất deferred result theo cách kiểm soát được trước khi dispatch. Có thể dùng latch, callback test hoặc một fake collaborator để tránh phụ thuộc thời gian thực.

### Vì sao dùng cả MockMvcTester và MockMvc?

MockMvcTester thuận tiện cho request và assertion theo AssertJ. API async của MockMvc đã có cơ chế tường minh `asyncDispatch(MvcResult)`, phù hợp khi cần điều khiển vòng đời dispatch. Có thể dùng tester cho request đầu, sau đó unwrap `MvcResult` để dùng cơ chế async sẵn có.

Nếu một test cần nhiều thao tác mức thấp như `asyncDispatch`, `MvcResult`, `request().asyncResult(...)` hoặc interceptor result, dùng MockMvc truyền thống cho phần đó vẫn hợp lý. MockMvcTester không buộc mọi thao tác phải chuyển thành một assertion chain.

## 7. Kiểm tra giá trị async trả về

Với một `Callable` trả về giá trị, kết quả cuối được xử lý như response MVC bình thường. Sau khi async dispatch, có thể xác nhận JSON hoặc text bằng matcher MockMvc:

```java
MvcResult initial = mockMvc.perform(get("/async-orders/12"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(12));
```

Nếu muốn dùng AssertJ để xác nhận dữ liệu sau async dispatch, lấy `MvcResult` cuối và kiểm tra response content hoặc deserialize body thành kiểu cần thiết:

```java
MvcResult completed = mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andReturn();

assertThat(completed.getResponse().getContentAsString())
        .contains("\"id\":12");
```

Trong dự án có `ObjectMapper`, có thể deserialize JSON body thành DTO rồi assert thuộc tính. Cách này tránh phụ thuộc vào khoảng trắng hoặc thứ tự field trong JSON.

## 8. Xử lý lỗi trong tác vụ async

Tác vụ async cũng có thể thất bại. Ví dụ `Callable` ném exception:

```java
@GetMapping("/async-orders/failure")
public Callable<String> failAsync() {
    return () -> {
        throw new IllegalStateException("Async order lookup failed");
    };
}
```

Nếu có `@ExceptionHandler` phù hợp, Spring MVC có thể giải quyết exception trong lần async dispatch cuối và tạo response HTTP. Test cần dispatch kết quả async rồi kiểm tra status/body:

```java
MvcResult initial = mockMvc.perform(get("/async-orders/failure"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.error").value("Async order lookup failed"));
```

Ví dụ giả định ứng dụng có exception advice chuyển `IllegalStateException` thành JSON 500 với trường `error`. Nếu không có resolver phù hợp, async dispatch có thể ném exception thay vì trả response 500. Hãy xác định rõ test đang muốn xác nhận response lỗi đã được xử lý hay failure chưa được xử lý.

Với `DeferredResult`, ứng dụng có thể đặt exception bằng `setErrorResult(exception)`. Kết quả này đi qua cơ chế xử lý exception của Spring MVC trong async dispatch. Vì vậy, nên test cả trường hợp hoàn tất thành công và trường hợp hoàn tất bằng lỗi nếu chúng là các nhánh nghiệp vụ quan trọng.

## 9. Timeout và tính ổn định của async test

Async test có thể trở nên không ổn định nếu phụ thuộc vào thời gian chạy thật. Một số nguyên tắc giúp test dễ kiểm soát:

- Không dùng `Thread.sleep(...)` để đoán khi nào tác vụ đã hoàn tất.
- Dùng `CountDownLatch`, `CompletableFuture` có thể điều khiển, hoặc fake collaborator để đồng bộ test với tác vụ.
- Cấu hình timeout phù hợp cho async request nếu tác vụ có thể mất thời gian.
- Xác nhận request thực sự đã bắt đầu async trước khi gọi `asyncDispatch`.
- Không gọi `asyncDispatch` khi request chưa ở trạng thái async.
- Kiểm tra response cuối cùng sau dispatch, không chỉ kiểm tra kết quả trung gian.

Ví dụ dùng `DeferredResult` có thể để test giữ một tham chiếu và hoàn tất nó sau khi xác nhận request đã bắt đầu. Trong ứng dụng thật, giá trị thường được hoàn tất bởi callback từ một dịch vụ; test có thể dùng fake dịch vụ để chủ động gọi callback.

## 10. Kết hợp MockMvcTester với exception và async result

Khi một endpoint async trả về kết quả lỗi, có thể tách test thành các bước:

1. Dùng `MockMvcTester` gửi request ban đầu.
2. Lấy `MvcResult` từ `MvcTestResult`.
3. Xác nhận request đã bắt đầu async.
4. Hoàn tất tác vụ async trong test nếu cần điều khiển callback.
5. Dùng `asyncDispatch(initialMvcResult)` để chạy dispatch cuối.
6. Kiểm tra status và response body cuối cùng.
7. Nếu exception được giải quyết, kiểm tra `getResolvedException()` trên `MvcResult` cuối khi cần xác nhận loại exception.

Ví dụ cấu trúc:

```java
MvcTestResult initialTestResult = mvcTester.get().uri("/async-orders/failure");
MvcResult initialMvcResult = initialTestResult.getMvcResult();

assertThat(initialMvcResult.getRequest().isAsyncStarted()).isTrue();

MvcResult finalResult = mockMvc.perform(asyncDispatch(initialMvcResult))
        .andExpect(status().isInternalServerError())
        .andReturn();

assertThat(finalResult.getResolvedException())
        .isInstanceOf(IllegalStateException.class);
```

Ví dụ giả định lỗi async được `HandlerExceptionResolver` giải quyết thành HTTP 500. Nếu lỗi không được giải quyết, async dispatch có thể ném exception và test cần xác nhận failure thay vì mong đợi `MvcResult` cuối.

## 11. Chọn assertion theo loại kết quả

| Mục tiêu | API gợi ý | Điều được xác nhận |
| --- | --- | --- |
| Exception được advice chuyển thành 404 | `hasStatus(HttpStatus.NOT_FOUND)` và `bodyJson()` | Response lỗi mà client nhận được |
| Exception được MVC giải quyết | `getMvcResult().getResolvedException()` | Loại exception được ghi nhận trong exception resolution |
| Exception thoát khỏi dispatch | `getFailure()` | Lỗi thực thi request chưa tạo response dispatch bình thường |
| Request async đã bắt đầu | `getMvcResult().getRequest().isAsyncStarted()` | Dispatch đầu chuyển sang chế độ async |
| Async result hoàn tất | `asyncDispatch(initialMvcResult)` | Kết quả cuối sau khi xử lý async |
| Async exception được advice xử lý | `asyncDispatch(...)` rồi kiểm tra status/body và resolved exception | Response lỗi cuối cùng |
| Async exception không được xử lý | Kiểm tra exception/failure khi async dispatch | Lỗi thoát khỏi luồng dispatch cuối |

## 12. Kết luận

Với `MockMvcTester`, exception được giải quyết thường được kiểm tra như một response HTTP bình thường: xác nhận status, body và nếu cần thì đọc `MvcResult.getResolvedException()`. Exception không được giải quyết được biểu diễn như failure của request và có thể kiểm tra qua `MvcTestResult.getFailure()`.

Request bất đồng bộ cần hai giai đoạn: dispatch ban đầu và dispatch kết quả bằng `asyncDispatch(...)`. `MockMvcTester` có thể tạo request đầu theo phong cách AssertJ; khi cần kiểm soát vòng đời async, lấy `MvcResult` bên dưới và dùng MockMvc để hoàn tất dispatch. Luôn kiểm tra response cuối cùng và phân biệt rõ lỗi đã được Spring MVC xử lý với exception còn thoát khỏi quá trình dispatch.
