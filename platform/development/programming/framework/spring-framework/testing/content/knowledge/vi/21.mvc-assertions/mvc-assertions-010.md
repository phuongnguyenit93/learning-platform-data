# Handler được chọn và ngoại lệ được giải quyết

Khi kiểm thử Spring MVC bằng `MockMvc`, chỉ xác nhận HTTP status và response body đôi khi chưa đủ để biết request đã đi qua đúng controller hay chưa. Một URL có thể khớp nhiều mapping, một handler có thể ném exception, và Spring MVC có thể chuyển exception đó cho một thành phần xử lý khác.

Spring MVC Test cung cấp các matcher để xác nhận handler được chọn. `MvcResult` còn cho phép đọc handler thực tế và exception mà Spring MVC đã giải quyết. Kết hợp hai nguồn thông tin này giúp test trả lời hai câu hỏi riêng biệt:

- Request đã được ánh xạ đến đúng handler method chưa?
- Nếu handler ném exception, Spring MVC đã xử lý exception đó và tạo response mong đợi chưa?

Điểm quan trọng là handler được chọn ban đầu vẫn là controller method đã nhận request. `@ExceptionHandler` hoặc `HandlerExceptionResolver` xử lý exception sau đó không thay thế giá trị handler ban đầu trong `MvcResult`.

## 1. Luồng xử lý request trong Spring MVC

Trong một request đồng bộ thông thường, `DispatcherServlet` điều phối các thành phần chính theo trình tự khái quát:

1. Nhận request từ Servlet API.
2. Hỏi các `HandlerMapping` để tìm handler phù hợp với URL, HTTP method và các điều kiện mapping khác.
3. Nhận `HandlerExecutionChain`, bao gồm handler và các interceptor liên quan.
4. Chọn `HandlerAdapter` phù hợp để gọi handler.
5. Thực thi controller method và xử lý kết quả trả về.
6. Nếu controller ném exception, chuyển exception qua chuỗi `HandlerExceptionResolver`.
7. Ghi response hoặc render view.

Ví dụ controller:

```java
@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        return Collections.singletonMap("id", id);
    }
}
```

Với request `GET /products/12`, `RequestMappingHandlerMapping` có thể chọn method `ProductController.findById(long)`. Spring MVC Test ghi nhận handler đã được chọn trong `MvcResult`, để test có thể xác nhận việc định tuyến.

## 2. Xác nhận handler bằng MockMvc result matchers

Spring MVC Test cung cấp `handler()` trong `MockMvcResultMatchers`. Một số matcher thường dùng:

- `handler().handlerType(ProductController.class)` xác nhận kiểu controller chứa handler method.
- `handler().methodName("findById")` xác nhận tên method được chọn.
- `handler().methodCall(...)` có thể xác nhận lời gọi handler theo biểu thức method khi phù hợp với API của phiên bản Spring đang dùng.

Ví dụ:

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void selectsProductHandler() throws Exception {
        mockMvc.perform(get("/products/{id}", 12))
                .andExpect(status().isOk())
                .andExpect(handler().handlerType(ProductController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(jsonPath("$.id").value(12));
    }
}
```

Trong test này, status và body xác nhận kết quả HTTP; hai matcher `handler()` xác nhận Spring MVC đã chọn đúng controller và method. Nếu một mapping khác vô tình nhận request, assertion về handler sẽ giúp phát hiện vấn đề ngay cả khi response tình cờ vẫn có status 200.

### Những điều kiện có thể ảnh hưởng đến handler được chọn

Spring MVC chọn handler dựa trên các điều kiện của mapping, không chỉ dựa trên đường dẫn:

- Path và path variable, ví dụ `/products/{id}`.
- HTTP method như GET, POST hoặc DELETE.
- Request parameters được khai báo trong mapping.
- Headers, bao gồm điều kiện `headers`.
- Media type trong `consumes` và `produces`.
- Các điều kiện mapping tùy chỉnh do ứng dụng định nghĩa.

Ví dụ hai method có cùng path nhưng khác điều kiện:

```java
@RestController
@RequestMapping("/reports")
public class ReportController {

    @GetMapping(params = "format=summary")
    public String summary() {
        return "summary";
    }

    @GetMapping(params = "format=detail")
    public String detail() {
        return "detail";
    }
}
```

Test có thể xác nhận cả kết quả và method được chọn:

```java
mockMvc.perform(get("/reports").param("format", "summary"))
        .andExpect(handler().handlerType(ReportController.class))
        .andExpect(handler().methodName("summary"))
        .andExpect(content().string("summary"));

mockMvc.perform(get("/reports").param("format", "detail"))
        .andExpect(handler().handlerType(ReportController.class))
        .andExpect(handler().methodName("detail"))
        .andExpect(content().string("detail"));
```

Những assertion này đặc biệt hữu ích khi nhiều method dùng chung path hoặc khi API có mapping phụ thuộc header, query parameter hay content type.

## 3. Đọc handler trực tiếp từ MvcResult

Nếu cần kiểm tra thêm thông tin ngoài các matcher có sẵn, lấy `MvcResult` bằng `.andReturn()`:

```java
MvcResult result = mockMvc.perform(get("/products/{id}", 12))
        .andExpect(status().isOk())
        .andReturn();

Object selectedHandler = result.getHandler();
assertThat(selectedHandler).isInstanceOf(HandlerMethod.class);

HandlerMethod handlerMethod = (HandlerMethod) selectedHandler;
assertThat(handlerMethod.getBeanType()).isEqualTo(ProductController.class);
assertThat(handlerMethod.getMethod().getName()).isEqualTo("findById");
```

Với controller dùng annotation như `@GetMapping`, handler thường là `HandlerMethod`. Đối tượng này cung cấp bean type, method và metadata của method được chọn. Tuy nhiên, `MvcResult.getHandler()` có kiểu trả về tổng quát `Object`: các loại handler khác như resource handler có thể không phải `HandlerMethod`.

Do đó, chỉ ép kiểu sang `HandlerMethod` sau khi xác nhận kiểu đối tượng. Nếu test có thể nhận resource handler hoặc handler khác, hãy kiểm tra kiểu trước hoặc dùng matcher phù hợp với handler mong đợi.

`MvcResult` còn cung cấp thông tin khác như request, response, model and view, interceptor và exception đã được giải quyết. Đây là đối tượng hữu ích khi test cần phân tích nhiều khía cạnh của một lần dispatch.

## 4. Handler được chọn và exception được giải quyết là hai thông tin khác nhau

Giả sử controller tìm sản phẩm nhưng không tìm thấy dữ liệu:

```java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
    }
}

@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        if (id == 404L) {
            throw new ProductNotFoundException(id);
        }
        return Collections.<String, Object>singletonMap("id", id);
    }
}
```

Một `@RestControllerAdvice` xử lý exception:

```java
@RestControllerAdvice
public class ProductExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("message", exception.getMessage()));
    }
}
```

Khi request `GET /products/404` được xử lý, `ProductController.findById` vẫn là handler đã nhận request. Method này ném `ProductNotFoundException`; sau đó Spring MVC tìm một exception resolver có thể xử lý exception. `ProductExceptionHandler.handleNotFound` tạo response 404 và body JSON.

Vì vậy:

- `handler().methodName("findById")` xác nhận controller method ban đầu được chọn.
- `MvcResult.getResolvedException()` cho biết exception nào đã được Spring MVC giải quyết.
- `status().isNotFound()` và assertion trên body xác nhận kết quả xử lý exception được gửi về client.

`handler()` không xác nhận `@ExceptionHandler` method đã được gọi. Exception handler thuộc giai đoạn xử lý exception sau khi controller handler ban đầu đã được chọn.

## 5. Xác nhận exception đã được giải quyết

Ví dụ test đầy đủ:

```java
@WebMvcTest(ProductController.class)
@Import(ProductExceptionHandler.class)
class ProductControllerExceptionTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void resolvesProductNotFoundException() throws Exception {
        MvcResult result = mockMvc.perform(get("/products/{id}", 404))
                .andExpect(handler().handlerType(ProductController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message")
                        .value("Product 404 was not found"))
                .andReturn();

        assertThat(result.getResolvedException())
                .isInstanceOf(ProductNotFoundException.class);
    }
}
```

Test này xác nhận cả ba phần: request được định tuyến đến đúng controller method, exception mong đợi đã được xử lý, và client nhận status/body tương ứng.

### getResolvedException() cho biết điều gì?

`MvcResult.getResolvedException()` trả về exception được phát hiện và giải quyết trong quá trình dispatch, hoặc `null` nếu không có exception được ghi nhận là đã giải quyết. Đây là exception gốc phát sinh trong quá trình xử lý handler, không phải một đối tượng đại diện cho response body.

Một exception được `@ExceptionHandler` xử lý vẫn có thể xuất hiện trong `getResolvedException()`. Điều này không có nghĩa exception còn bị ném ra ngoài; nó cho biết Spring MVC đã nhận exception đó và xử lý trong exception resolution flow.

Không dùng riêng `getResolvedException()` để kết luận client đã nhận response đúng. Một exception có thể được xử lý nhưng status hoặc body vẫn không đúng yêu cầu. Hãy kết hợp assertion về exception với status, header và response body.

## 6. Spring MVC giải quyết exception bằng cách nào?

`DispatcherServlet` sử dụng chuỗi `HandlerExceptionResolver` để tìm cách xử lý exception phát sinh trong quá trình gọi handler. Một số resolver thường gặp:

| Resolver | Vai trò thường gặp |
| --- | --- |
| `ExceptionHandlerExceptionResolver` | Tìm và gọi `@ExceptionHandler` trong controller hoặc `@ControllerAdvice` |
| `ResponseStatusExceptionResolver` | Xử lý exception mang `@ResponseStatus` và `ResponseStatusException` |
| `DefaultHandlerExceptionResolver` | Ánh xạ một số exception chuẩn của Spring MVC sang HTTP status phù hợp |
| Resolver tùy chỉnh | Xử lý các exception theo quy tắc do ứng dụng đăng ký |

Các resolver được gọi theo thứ tự cấu hình. Resolver có thể trả về `ModelAndView` để cho biết đã xử lý exception, trả về kết quả rỗng theo hợp đồng của resolver, hoặc để exception tiếp tục được xem xét bởi resolver khác. Nếu không resolver nào xử lý được, exception có thể thoát khỏi `DispatcherServlet` và được Servlet container xử lý.

### @ExceptionHandler trong controller hoặc @ControllerAdvice

`@ExceptionHandler` có thể được khai báo ngay trong controller:

```java
@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        throw new ProductNotFoundException(id);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<Map<String, String>> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("message", exception.getMessage()));
    }
}
```

Hoặc khai báo ở cấp ứng dụng bằng `@ControllerAdvice`/`@RestControllerAdvice`, như ví dụ trước. Cách dùng advice giúp nhiều controller chia sẻ quy tắc xử lý lỗi.

Spring có thể chọn handler method dựa trên kiểu exception phù hợp và các điều kiện mapping của exception handler. Handler cục bộ của controller và advice toàn cục có thứ tự ưu tiên theo quy tắc của Spring. Khi nhiều handler có thể xử lý cùng một exception, nên viết test để xác nhận response thực tế theo cấu hình đang dùng.

### ResponseStatusException và @ResponseStatus

Ngoài `@ExceptionHandler`, ứng dụng có thể dùng `ResponseStatusException`:

```java
@GetMapping("/legacy-products/{id}")
public Map<String, Object> findLegacy(@PathVariable long id) {
    throw new ResponseStatusException(
            HttpStatus.GONE, "This product endpoint is no longer available");
}
```

Hoặc đánh dấu exception bằng `@ResponseStatus`:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String customerId) {
        super("Customer " + customerId + " was not found");
    }
}
```

Test nên xác nhận status và các thông tin response mà ứng dụng cam kết. Nội dung body có thể phụ thuộc cấu hình error response, `ErrorAttributes`, controller advice hoặc phiên bản Spring Boot; đừng giả định mọi kiểu exception đều tạo body giống nhau.

## 7. Phân biệt exception đã giải quyết và exception chưa giải quyết

Nếu một `HandlerExceptionResolver` xử lý được exception, Spring MVC có thể hoàn tất dispatch và trả response. Test thường lấy được `MvcResult`, có thể kiểm tra `getResolvedException()`, status và body.

Nếu không resolver nào xử lý exception, exception có thể được ném ra khỏi quá trình dispatch. Khi đó, `mockMvc.perform(...)` có thể ném exception thay vì trả về một kết quả bình thường để gọi `.andReturn()`. Trong trường hợp này, test có thể dùng `assertThatThrownBy` hoặc `assertThrows` để xác nhận exception được propagate, tùy exception wrapper mà phiên bản/framework đang sử dụng.

Ví dụ kiểm tra exception không được xử lý:

```java
assertThatThrownBy(() -> mockMvc.perform(get("/unhandled-error")))
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

Ví dụ này minh họa ý tưởng kiểm tra exception đi ra khỏi MockMvc. Kiểu wrapper và chuỗi cause cụ thể phụ thuộc nơi exception phát sinh và phiên bản Spring. Khi có thể, nên kiểm tra loại exception gốc và không phụ thuộc vào thông điệp wrapper nội bộ.

Một trường hợp khác là không có handler nào được tìm thấy. Tùy cấu hình, request có thể được chuyển đến resource handler, được xử lý thành 404, hoặc tạo exception như `NoHandlerFoundException`/`NoResourceFoundException`. Do đó, không phải mọi status 404 đều đồng nghĩa với việc một controller method đã chạy và ném exception.

## 8. Những lỗi không đi qua HandlerExceptionResolver

`HandlerExceptionResolver` thuộc luồng dispatch của `DispatcherServlet`. Các lỗi xảy ra trước khi request đến `DispatcherServlet` có thể nằm ngoài luồng này.

Ví dụ, Spring Security filter chain có thể từ chối request trước khi controller được gọi. Khi đó:

- Có thể không có controller handler được chọn.
- `MvcResult.getResolvedException()` thường không phải nơi để tìm nguyên nhân authorization bị từ chối.
- Response 401, 403 hoặc redirect thường được tạo bởi thành phần bảo mật như `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`.

Với lỗi trong filter tùy chỉnh, Servlet container hoặc connector, cũng cần xác định lỗi xảy ra trước hay trong `DispatcherServlet`. Không nên kỳ vọng mọi exception của ứng dụng đều xuất hiện trong `getResolvedException()`.

Khi test Spring Security, hãy xác nhận filter chain tham gia MockMvc và kiểm tra status/redirect theo cấu hình security. Khi cần kiểm tra controller advice, hãy bảo đảm request đã vượt qua filter chain để đến MVC handler.

## 9. Xác nhận cả handler lẫn exception trong các tình huống thực tế

### Mapping đúng nhưng handler ném exception

Đây là trường hợp phổ biến: URL khớp controller, controller chạy, nhưng dữ liệu không tồn tại. Test nên xác nhận handler ban đầu và kết quả exception resolution:

```java
MvcResult result = mockMvc.perform(get("/products/404"))
        .andExpect(handler().handlerType(ProductController.class))
        .andExpect(handler().methodName("findById"))
        .andExpect(status().isNotFound())
        .andReturn();

assertThat(result.getResolvedException())
        .isInstanceOf(ProductNotFoundException.class);
```

### Sai HTTP method

Nếu mapping chỉ hỗ trợ GET nhưng test gửi POST, handler method GET không được chọn. Spring có thể trả 405 Method Not Allowed nếu path tồn tại nhưng HTTP method không phù hợp. Test nên kiểm tra status và không khẳng định handler method GET đã được gọi:

```java
mockMvc.perform(post("/products/12"))
        .andExpect(status().isMethodNotAllowed());
```

Tùy cấu hình resource handler và mapping, chi tiết dispatch có thể khác; hãy viết assertion theo hành vi API đã xác định.

### Không thỏa điều kiện params, headers hoặc media type

Nếu request không thỏa `params`, `headers`, `consumes` hoặc `produces`, Spring có thể trả 400, 406 hoặc 415 tùy trường hợp. Những lỗi này thường được ánh xạ bởi resolver mặc định hoặc advice tùy chỉnh. Khi test mapping có điều kiện, hãy xác nhận cả handler method được chọn cho request hợp lệ và status/error response cho request không hợp lệ.

### Kiểm tra view và model

Với controller trả view thay vì JSON, có thể dùng `view()` và `model()` matcher:

```java
mockMvc.perform(get("/products"))
        .andExpect(handler().handlerType(ProductPageController.class))
        .andExpect(handler().methodName("list"))
        .andExpect(view().name("products/list"))
        .andExpect(model().attributeExists("products"));
```

Các matcher này xác nhận handler và kết quả render logic của Spring MVC, không chứng minh template được render chính xác trong browser. Nếu cần kiểm tra HTML thực tế hoặc tích hợp template engine, cần thêm test phù hợp với view technology.

## 10. Request bất đồng bộ và exception

Với controller trả `Callable`, `DeferredResult` hoặc kiểu kết quả async khác, lần `perform` đầu tiên có thể chỉ xác nhận request đã bắt đầu xử lý bất đồng bộ. Muốn kiểm tra kết quả cuối cùng, lấy `MvcResult`, chờ async hoàn tất theo cơ chế test, rồi gọi `asyncDispatch`:

```java
MvcResult initialResult = mockMvc.perform(get("/async-products/12"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initialResult))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(12));
```

Nếu tác vụ async ném exception, exception resolution có thể diễn ra ở lần async dispatch. Hãy kiểm tra response cuối cùng sau `asyncDispatch`, và lấy `MvcResult` của lần dispatch cuối nếu cần đọc exception đã giải quyết.

Không nên kết luận handler cuối cùng đã hoàn tất chỉ từ `MvcResult` ban đầu. Với async request, test cần phân biệt trạng thái bắt đầu async và response sau khi dispatch kết quả.

## 11. Cách viết assertion rõ ràng

Một test MVC tốt thường kết hợp các assertion theo thứ tự giúp người đọc hiểu request đi qua đâu và kết quả là gì:

1. Xác nhận handler type và method nếu định tuyến là điều cần kiểm tra.
2. Xác nhận HTTP status.
3. Xác nhận content type, header hoặc response body.
4. Nếu có exception, xác nhận loại exception trong `getResolvedException()`.
5. Nếu test view, xác nhận view name và model attributes.

Ví dụ tổng hợp:

```java
MvcResult result = mockMvc.perform(get("/products/404")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(handler().handlerType(ProductController.class))
        .andExpect(handler().methodName("findById"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.message").value("Product 404 was not found"))
        .andReturn();

assertThat(result.getResolvedException())
        .isInstanceOf(ProductNotFoundException.class);
```

Không cần lặp lại mọi assertion trong tất cả test. Nếu test chỉ quan tâm response contract, status và body có thể là đủ. Nếu test nhằm kiểm tra routing hoặc exception resolution, bổ sung handler matcher và resolved exception để làm rõ điều đang được xác nhận.

## 12. Bảng chọn matcher và thông tin MvcResult

| Điều cần xác nhận | API thường dùng | Ý nghĩa |
| --- | --- | --- |
| Controller class được chọn | `handler().handlerType(...)` | Kiểu bean chứa handler |
| Handler method được chọn | `handler().methodName(...)` | Tên method đã nhận request |
| Handler object thực tế | `MvcResult.getHandler()` | Đối tượng handler được chọn |
| Thông tin method của annotated controller | `HandlerMethod` | Bean type, method và metadata |
| Exception được MVC giải quyết | `MvcResult.getResolvedException()` | Exception gốc được ghi nhận trong quá trình resolution |
| HTTP status | `status()` | Status gửi về client |
| Response body | `content()`, `jsonPath()` | Dữ liệu trả về |
| View name | `view().name(...)` | View được chọn để render |
| Model attribute | `model().attribute(...)` | Dữ liệu đưa vào model |
| Async request | `request().asyncStarted()`, `asyncDispatch(...)` | Trạng thái và kết quả dispatch bất đồng bộ |

Hãy nhớ rằng `getHandler()` và `getResolvedException()` trả lời hai câu hỏi khác nhau. Một giá trị cho biết request được định tuyến đến đâu; giá trị còn lại cho biết exception nào đã được xử lý trong quá trình dispatch.

## 13. Kết luận

Handler matcher của MockMvc giúp xác nhận Spring MVC chọn đúng controller type và handler method dựa trên request. `MvcResult.getHandler()` cho phép đọc sâu hơn về handler đã chọn, còn `getResolvedException()` cho biết exception được giải quyết trong quá trình dispatch.

Khi controller ném exception, handler ban đầu vẫn là controller method. `@ExceptionHandler`, `@ControllerAdvice` hoặc resolver mặc định xử lý exception và tạo response sau đó. Vì vậy, hãy kết hợp assertion về handler, exception, status và body để xác nhận toàn bộ hành vi cần kiểm tra. Với lỗi xảy ra ngoài `DispatcherServlet`, chẳng hạn lỗi bị Spring Security filter chặn trước controller, hãy kiểm tra ở tầng filter/security tương ứng thay vì dựa vào `getResolvedException()`.
