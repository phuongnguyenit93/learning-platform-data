# expectAll để tổng hợp nhiều phép xác nhận

Khi kiểm thử HTTP bằng Spring MockMvc, một request thường có nhiều điều kiện cần xác nhận cùng lúc: status, content type, header, response body, handler được chọn và các thuộc tính khác. Nếu nối nhiều lời gọi `andExpect(...)`, test thường dừng ngay tại assertion đầu tiên bị lỗi. Điều đó khiến mỗi lần chạy chỉ cho thấy một vấn đề, dù response có thể đang sai ở nhiều chỗ.

Spring Framework 5.3 bổ sung `ResultActions.andExpectAll(...)` để thực hiện nhiều `ResultMatcher` trên cùng một kết quả request. Phương thức này tiếp tục chạy các matcher sau khi một assertion thất bại, sau đó báo cáo các lỗi đã thu thập. Nhờ vậy, một lần chạy test có thể chỉ ra nhiều điểm không đúng trong cùng response.

`andExpectAll` đặc biệt hữu ích khi xác nhận hợp đồng HTTP gồm nhiều phần độc lập. Nó không tạo thêm request, không chạy các matcher song song và không làm test thành công khi có assertion thất bại. Nó chỉ thay đổi cách Spring MVC Test thực hiện và báo cáo một nhóm phép xác nhận.

## 1. Vì sao cần tổng hợp nhiều phép xác nhận?

Giả sử endpoint trả về thông tin đơn hàng. Hợp đồng response yêu cầu:

- HTTP status là 200.
- Content type là JSON.
- Header `X-Api-Version` có giá trị `v1`.
- JSON có `id` và `status` đúng.
- Request được ánh xạ đến đúng controller method.

Với cách viết truyền thống:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("READY"));
```

Các lời gọi `andExpect(...)` được thực hiện theo thứ tự. Khi một matcher ném `AssertionError`, chuỗi assertion dừng ở đó. Ví dụ status đúng nhưng header sai thì các assertion JSON ở phía sau có thể chưa chạy.

Với `andExpectAll(...)`, có thể gom các matcher vào một lời gọi:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpectAll(
                status().isOk(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );
```

Nếu một hoặc nhiều matcher thất bại, các matcher còn lại vẫn được thực hiện. Sau đó, Spring báo lỗi assertion tổng hợp để test runner đánh dấu test thất bại.

## 2. andExpectAll thuộc API nào và có từ phiên bản nào?

`andExpectAll(...)` là phương thức của `org.springframework.test.web.servlet.ResultActions`, đối tượng được trả về từ `mockMvc.perform(...)`.

Chữ ký phương thức có dạng:

```java
ResultActions andExpectAll(ResultMatcher... resultMatchers) throws Exception;
```

Các điểm cần nhớ:

- Có từ Spring Framework 5.3.
- Nhận một hoặc nhiều `ResultMatcher` qua tham số varargs.
- Mỗi matcher được áp dụng lên cùng `MvcResult` của request vừa thực hiện.
- Các assertion failure được thu thập; nếu có nhiều lỗi, lỗi đầu tiên được ném ra và các lỗi tiếp theo được gắn dưới dạng suppressed exceptions.
- Nếu tất cả matcher thành công, phương thức trả về `ResultActions` để có thể tiếp tục nối thao tác phù hợp.

Ví dụ import thường dùng:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Nếu dự án dùng Spring Framework trước 5.3, `ResultActions` chưa có `andExpectAll`. Khi đó có thể dùng các lời gọi `andExpect(...)` riêng lẻ hoặc tự xây dựng cách thu thập assertion phù hợp. Chỉ thêm AssertJ không làm xuất hiện phương thức này; cần phiên bản `spring-test` hỗ trợ.

## 3. Cách hoạt động của andExpectAll

`MockMvc.perform(...)` tạo và thực hiện một request mô phỏng, sau đó trả về `ResultActions` gắn với kết quả đó. Mỗi `ResultMatcher` nhận cùng một `MvcResult` để kiểm tra một khía cạnh của request/response.

Với `andExpectAll`, Spring gọi lần lượt các matcher trong danh sách. Nếu một matcher ném `AssertionError`, Spring lưu lỗi đó và tiếp tục matcher tiếp theo. Khi đã chạy hết:

- Không có lỗi: lời gọi hoàn tất bình thường và trả về `ResultActions`.
- Có một lỗi: assertion error đó được ném ra.
- Có nhiều lỗi: assertion error đầu tiên được ném ra, các lỗi còn lại được gắn làm suppressed exceptions.

Luồng xử lý khái quát:

```text
mockMvc.perform(request)
          |
          v
      MvcResult
          |
          v
    andExpectAll(...)
          |
          +--> matcher 1 ----> pass / collect failure
          |
          +--> matcher 2 ----> pass / collect failure
          |
          +--> matcher 3 ----> pass / collect failure
          |
          +--> matcher n ----> pass / collect failure
          |
          v
  All matchers completed
          |
          +--> no failures: continue
          |
          +--> failures: throw first AssertionError
               with remaining failures suppressed
```

Các matcher vẫn chạy tuần tự. `andExpectAll` không tạo một thread cho mỗi matcher và không gửi lại request đến controller.

### Vì sao việc gom lỗi hữu ích?

Khi response không đáp ứng hợp đồng, một assertion fail-fast thường buộc người viết test sửa một lỗi rồi chạy lại để nhìn thấy lỗi tiếp theo. `andExpectAll` cho phép phát hiện nhiều vấn đề độc lập trong một lượt, giảm số vòng lặp khi xử lý response có nhiều trường.

Tuy nhiên, kết quả tổng hợp chỉ hữu ích khi các matcher kiểm tra những điều kiện độc lập và có thể đánh giá trên cùng một response. Nếu matcher sau phụ thuộc vào kết quả của matcher trước, hãy tách logic hoặc viết matcher riêng có thông báo rõ ràng.

## 4. Ví dụ kiểm tra hợp đồng response JSON

Giả sử controller trả về DTO:

```java
public class OrderResponse {

    private final long id;
    private final String status;
    private final String customer;

    public OrderResponse(long id, String status, String customer) {
        this.id = id;
        this.status = status;
        this.customer = customer;
    }

    public long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getCustomer() {
        return customer;
    }
}
```

Controller:

```java
@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    public ResponseEntity<OrderResponse> getOrder(@PathVariable long id) {
        OrderResponse body = new OrderResponse(id, "READY", "alice");

        return ResponseEntity.ok()
                .header("X-Api-Version", "v1")
                .body(body);
    }
}
```

Test:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedOrderResponse() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                        header().string("X-Api-Version", "v1"),
                        jsonPath("$.id").value(42),
                        jsonPath("$.status").value("READY"),
                        jsonPath("$.customer").value("alice")
                );
    }
}
```

Các matcher được đánh giá độc lập trên response. Nếu status đúng nhưng `customer` sai, test vẫn chạy các matcher header, id và status trước khi báo lỗi tổng hợp.

## 5. Dùng andExpectAll cho response lỗi

Các response lỗi thường có nhiều phần cần kiểm tra: status, content type, mã lỗi, thông điệp và thông tin field validation.

Ví dụ response lỗi validation:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request contains invalid fields",
  "fieldErrors": [
    {
      "field": "email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

Test có thể xác nhận nhiều phần cùng lúc:

```java
mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"invalid-email"}
                        """))
        .andExpectAll(
                status().isBadRequest(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                jsonPath("$.code").value("VALIDATION_ERROR"),
                jsonPath("$.message").isNotEmpty(),
                jsonPath("$.fieldErrors[0].field").value("email"),
                jsonPath("$.fieldErrors[0].message").isNotEmpty()
        );
```

Ví dụ giả định endpoint có validation và exception advice tạo đúng cấu trúc JSON trên. Nếu ứng dụng trả status hoặc cấu trúc lỗi khác, matcher phải phản ánh hợp đồng thực tế.

Với response lỗi, tránh chỉ kiểm tra status. Hai response đều có thể là 400 nhưng một response có thể thiếu mã lỗi hoặc sai tên field. `andExpectAll` giúp xác nhận toàn bộ error contract trong một lần thực thi.

## 6. Kết hợp nhiều nhóm matcher

`andExpectAll` nhận mọi `ResultMatcher` phù hợp, vì vậy có thể kết hợp matcher từ nhiều nhóm khác nhau.

| Nhóm | Matcher thường dùng | Điều cần xác nhận |
| --- | --- | --- |
| Status | `status().isOk()`, `isCreated()`, `isBadRequest()` | Mã trạng thái HTTP |
| Header | `header().exists(...)`, `string(...)`, `longValue(...)` | Header response |
| Content | `content().contentType(...)`, `string(...)`, `bytes(...)` | Kiểu và nội dung response |
| JSONPath | `jsonPath(...).value(...)`, `exists()`, `isArray()` | Trường và cấu trúc JSON |
| Handler | `handler().handlerType(...)`, `methodName(...)` | Controller/handler được chọn |
| Cookie | `cookie().exists(...)`, `value(...)` | Cookie response |
| Model | `model().attribute(...)`, `attributeExists(...)` | Model attribute của MVC |
| View | `view().name(...)` | View được chọn |
| Request | `request().asyncStarted()`, `asyncResult(...)` | Trạng thái request và async result |

Ví dụ xác nhận cả handler và response:

```java
mockMvc.perform(get("/api/orders/{id}", 42))
        .andExpectAll(
                handler().handlerType(OrderController.class),
                handler().methodName("getOrder"),
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42)
        );
```

Khi test nhằm kiểm tra routing, matcher handler giúp phát hiện trường hợp một controller khác vô tình nhận request nhưng vẫn trả response có vẻ hợp lệ.

## 7. So sánh andExpect và andExpectAll

| Tiêu chí | `andExpect(...)` | `andExpectAll(...)` |
| --- | --- | --- |
| Số matcher mỗi lời gọi | Một matcher | Một hoặc nhiều matcher |
| Cách thực hiện | Thực hiện matcher hiện tại | Thực hiện lần lượt toàn bộ matcher |
| Khi matcher thất bại | Ném assertion error và dừng chuỗi hiện tại | Ghi nhận lỗi và tiếp tục matcher sau |
| Báo cáo nhiều lỗi | Các lần chạy sau mới phát hiện lỗi tiếp theo | Gộp các assertion failure trong cùng lần chạy |
| Kết quả khi có lỗi | Test thất bại | Test vẫn thất bại sau khi hoàn tất các matcher |
| Phiên bản | Có từ các dòng Spring MVC Test cũ | Có từ Spring Framework 5.3 |

Ví dụ fail-fast:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(jsonPath("$.status").value("READY"));
```

Nếu status sai, matcher header và JSON có thể không được chạy.

Ví dụ tổng hợp:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.status").value("READY")
        );
```

Với cách thứ hai, cả ba điều kiện đều được đánh giá. Dùng `andExpectAll` khi muốn nhận báo cáo nhiều lỗi cùng lúc; dùng `andExpect` khi cần fail-fast hoặc khi một bước kiểm tra chỉ có ý nghĩa sau khi điều kiện trước đã đúng.

## 8. Viết ResultMatcher tùy chỉnh

Khi nhiều test cần kiểm tra cùng một quy tắc, có thể tạo `ResultMatcher` riêng rồi đưa vào `andExpectAll`. `ResultMatcher` là functional interface nhận `MvcResult` và có thể ném exception nếu kết quả không đúng.

Ví dụ kiểm tra header correlation ID:

```java
public final class ApiResultMatchers {

    private ApiResultMatchers() {
    }

    public static ResultMatcher hasCorrelationId() {
        return result -> {
            String value = result.getResponse()
                    .getHeader("X-Correlation-Id");

            assertThat(value)
                    .as("X-Correlation-Id response header")
                    .isNotBlank();
        };
    }
}
```

Sử dụng:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                ApiResultMatchers.hasCorrelationId(),
                jsonPath("$.id").value(42)
        );
```

Custom matcher giúp gom các quy tắc response dùng chung, tránh lặp lại logic trong nhiều test. Hãy đặt thông tin mô tả cho AssertJ assertion hoặc tạo thông báo lỗi rõ ràng để người đọc biết điều kiện nào thất bại.

Một matcher tùy chỉnh nên kiểm tra một hành vi có ý nghĩa. Tránh tạo matcher quá lớn vừa xác nhận status, header, JSON, database và side effect, vì khi đó khó biết chính xác điều kiện nào sai và khó tái sử dụng.

## 9. Những lưu ý khi dùng andExpectAll

### Các matcher cùng kiểm tra một MvcResult

`andExpectAll` không thực hiện lại request cho mỗi matcher. Mọi matcher nhận kết quả của cùng một lần `mockMvc.perform(...)`. Nếu cần kiểm tra hai request khác nhau, phải gọi `perform(...)` hai lần.

### Thứ tự matcher vẫn có ý nghĩa

Các matcher được chạy theo thứ tự truyền vào. Dù assertion failure được thu thập và không dừng nhóm matcher, một matcher có thể phụ thuộc vào dữ liệu do matcher trước chuẩn bị hoặc thay đổi. Hạn chế side effect trong matcher; hãy thiết kế mỗi matcher có thể đọc kết quả độc lập.

### Không phải mọi lỗi đều là AssertionError

Mục tiêu của `andExpectAll` là tổng hợp assertion failures. Một lỗi thực thi bất thường như exception khi đọc dữ liệu hoặc lỗi cấu hình matcher có thể không được xử lý giống một assertion mismatch. Không nên dùng `andExpectAll` để che giấu exception ngoài dự kiến.

### Các matcher phải phù hợp với response hiện tại

Ví dụ `jsonPath(...)` cần response body có thể được đọc như JSON. Nếu response không phải JSON, matcher có thể báo lỗi parse. Nếu muốn xác nhận response là JSON và các field bên trong, có thể đặt matcher content type trước JSONPath để thông báo lỗi dễ hiểu hơn; `andExpectAll` vẫn tiếp tục các matcher khác nếu một matcher thất bại.

### Không làm test phức tạp chỉ để gom mọi thứ

Một test nên xác nhận một hành vi hoặc hợp đồng rõ ràng. Nếu gom quá nhiều điều kiện không liên quan vào một `andExpectAll`, báo cáo lỗi sẽ dài và khó xác định nguyên nhân. Hãy chia test theo tình huống hoặc endpoint khi các hành vi không cùng một mục tiêu.

## 10. Chẩn đoán khi có nhiều assertion thất bại

Khi `andExpectAll` phát hiện nhiều lỗi, assertion đầu tiên được ném ra và các assertion error còn lại được gắn dưới dạng suppressed exceptions. Cách hiển thị cụ thể phụ thuộc test runner và IDE; một số giao diện có thể thu gọn suppressed exceptions.

Để việc chẩn đoán thuận tiện:

- Dùng matcher có thông điệp rõ ràng, đặc biệt với matcher tùy chỉnh.
- Gom các assertion theo một hợp đồng response có liên quan.
- Dùng `andDo(print())` trước `andExpectAll(...)` nếu cần in request/response ngay cả khi assertion sau thất bại.
- Hoặc cấu hình `alwaysDo(print())` trong MockMvc builder để in kết quả cho mọi request trong test scope.
- Đọc suppressed exceptions khi báo cáo chỉ hiển thị assertion đầu tiên.

Ví dụ in kết quả trước khi xác nhận:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(print())
        .andExpectAll(
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );
```

Đặt `andDo(print())` trước `andExpectAll` bảo đảm thao tác in đã chạy trước khi nhóm assertion có thể ném lỗi tổng hợp. Nếu đặt sau `andExpectAll`, khi assertion thất bại thì thao tác in ở phía sau có thể không được thực hiện.

## 11. Dùng expectAll trong test MVC thực tế

Một số trường hợp phù hợp:

### API trả dữ liệu thành công

Xác nhận status, content type, header cache, handler và các trường JSON bắt buộc.

### API trả lỗi validation

Xác nhận status 400, error code, message, tên field và cấu trúc danh sách lỗi.

### API tạo tài nguyên

Xác nhận status 201, `Location` header, content type và ID của tài nguyên mới.

### API yêu cầu xác thực

Xác nhận status 401/403 hoặc redirect theo cấu hình, cùng các header và response body lỗi.

### Controller trả view

Kết hợp matcher handler, status, view name và model attribute để xác nhận MVC chọn đúng handler và chuẩn bị dữ liệu render.

Ví dụ API tạo tài nguyên:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"customer":"alice"}
                        """))
        .andExpectAll(
                status().isCreated(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                header().exists("Location"),
                jsonPath("$.id").isNumber(),
                jsonPath("$.customer").value("alice"),
                jsonPath("$.status").value("NEW")
        );
```

Các matcher trong ví dụ cùng mô tả hợp đồng của một thao tác tạo đơn hàng. Nếu một trường bị thiếu hoặc header `Location` không được tạo, test vẫn báo được các sai lệch khác trong cùng lần chạy.

## 12. andExpectAll và MockMvcTester

`andExpectAll(...)` thuộc API `ResultActions` của MockMvc truyền thống. `MockMvcTester` là API AssertJ mới hơn, có phong cách xác nhận riêng như `hasStatusOk()`, `bodyText()` và `bodyJson()`.

Không nên nhầm hai cơ chế:

```java
// MockMvc ResultActions
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );

// MockMvcTester với AssertJ
assertThat(mvcTester.get().uri("/api/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
```

MockMvcTester phù hợp khi muốn viết assertion theo phong cách AssertJ. `andExpectAll` phù hợp khi cần chạy nhiều `ResultMatcher` và tổng hợp assertion failures. Cả hai đều dựa trên hạ tầng Spring MVC Test và có thể được lựa chọn theo phong cách test của dự án.

## 13. Kết luận

`ResultActions.andExpectAll(...)` cho phép kiểm tra nhiều khía cạnh của cùng một response trong một lần request. Từ Spring Framework 5.3, phương thức này thực hiện lần lượt toàn bộ `ResultMatcher`, thu thập assertion failures và báo lỗi tổng hợp sau khi hoàn tất nhóm matcher.

Hãy dùng `andExpectAll` để xác nhận những hợp đồng HTTP có nhiều điều kiện độc lập như status, header, content type, JSON body và handler. Dùng `andExpect` riêng lẻ khi cần fail-fast hoặc khi bước sau phụ thuộc điều kiện trước. Khi dùng đúng phạm vi, `andExpectAll` giúp một lần chạy test cung cấp nhiều thông tin chẩn đoán hơn mà vẫn giữ assertion gắn với một request cụ thể.
