# Xác nhận hợp đồng thay vì chỉ kiểm tra mã 200

Trong Spring MVC, một request có thể trả về HTTP 200 nhưng vẫn vi phạm điều mà client cần. Response có thể thiếu trường dữ liệu, sai kiểu nội dung, thiếu header quan trọng hoặc chứa giá trị nghiệp vụ không đúng. Vì vậy, một MVC test tốt cần xác nhận hợp đồng response mà client quan sát được, thay vì dừng lại ở việc kiểm tra status.

Hợp đồng response thường gồm status code, content type, headers, cookies, cấu trúc body, giá trị các trường và hành vi khi request không hợp lệ. Với controller trả về view, hợp đồng còn có thể gồm tên view, model attributes, redirect URL và flash attributes. MockMvc cung cấp các `ResultMatcher` để kiểm tra những phần này.

## 1. Mã 200 chỉ xác nhận một phần

Assertion sau đây có ích nhưng chưa đủ:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
```

Nó chỉ chứng minh response có status 200. Test vẫn có thể xanh trong các trường hợp:

- Body rỗng dù client cần một JSON object.
- Response trả `text/plain` thay vì `application/json`.
- JSON có trường `orderId` trong khi hợp đồng yêu cầu `id`.
- Trường `status` có giá trị sai, chẳng hạn `CANCELLED` thay vì `PAID`.
- Header `Location`, `ETag` hoặc header nghiệp vụ cần thiết bị thiếu.
- Một endpoint tạo tài nguyên trả 200 trong khi hợp đồng đã quy định 201 Created.

Thay vì kiểm tra status riêng lẻ, hãy mô tả điều client được phép dựa vào:

| Thành phần hợp đồng | Câu hỏi cần trả lời | Matcher thường dùng |
|---|---|---|
| Status | Request thành công, tạo tài nguyên hay bị từ chối? | `status()` |
| Content type | Response là JSON, HTML hay loại nội dung khác? | `content()` |
| Header và cookie | Có metadata hoặc cookie cần thiết không? | `header()`, `cookie()` |
| Body | Có đúng cấu trúc và giá trị dữ liệu không? | `jsonPath()`, `content()` |
| View và model | MVC chọn đúng view và cung cấp đúng dữ liệu không? | `view()`, `model()` |
| Redirect và flash | Sau thao tác, người dùng được chuyển tới đâu và nhận thông báo gì? | `redirectedUrl()`, `flash()` |

## 2. Xác nhận status theo ngữ nghĩa HTTP

Chọn matcher thể hiện đúng kết quả nghiệp vụ. Một số matcher phổ biến:

```java
status().isOk();                 // 200
status().isCreated();            // 201
status().isAccepted();           // 202
status().isNoContent();          // 204
status().isBadRequest();         // 400
status().isUnauthorized();       // 401
status().isForbidden();          // 403
status().isNotFound();           // 404
status().isConflict();           // 409
status().isUnprocessableEntity();// 422
```

Ví dụ, endpoint tạo đơn hàng có thể trả 201 Created. Endpoint xóa thành công có thể trả 204 No Content nếu hợp đồng không yêu cầu body. Lỗi xác thực có thể là 400 hoặc 422 tùy quy ước API; điều quan trọng là test phải khớp hợp đồng đã chọn.

Không nên ép mọi response thành 200 chỉ để test đơn giản. Status là một phần của giao thức mà client sử dụng để quyết định bước tiếp theo.

## 3. Xác nhận content type và headers

Với JSON API, hãy kiểm tra response khai báo JSON:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.http.MediaType.APPLICATION_JSON;

mockMvc.perform(get("/api/orders/42").accept(APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON));
```

`contentTypeCompatibleWith(...)` phù hợp khi charset hoặc các tham số media type có thể thay đổi nhưng loại nội dung vẫn tương thích. Nếu hợp đồng yêu cầu media type chính xác, có thể dùng `contentType(...)` với giá trị cụ thể.

Kiểm tra header:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/api/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(header().doesNotExist("X-Debug-Token"));
```

Với endpoint tạo tài nguyên, header `Location` thường chỉ ra URL của tài nguyên mới:

```java
mockMvc.perform(post("/api/orders").contentType(APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}"))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/orders/42"));
```

Có thể kiểm tra cookie nếu đó là một phần của hợp đồng:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

mockMvc.perform(post("/login"))
        .andExpect(cookie().exists("SESSION"))
        .andExpect(cookie().httpOnly("SESSION", true));
```

Chỉ xác nhận những header và cookie mà client hoặc bảo mật thực sự phụ thuộc vào. Các giá trị do framework tạo ngẫu nhiên, chẳng hạn session ID hoặc request ID, thường nên kiểm tra sự hiện diện và thuộc tính cần thiết thay vì so sánh một giá trị cố định.

## 4. Xác nhận cấu trúc và giá trị JSON

`jsonPath(...)` cho phép truy vấn một phần của JSON response mà không cần deserialize toàn bộ body thành object trong test.

Ví dụ controller trả về một đơn hàng:

```java
import java.math.BigDecimal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    ResponseEntity<OrderResponse> find(@PathVariable String id) {
        OrderResponse response = new OrderResponse(
                id, "PAID", new BigDecimal("125.00"));
        return ResponseEntity.ok()
                .header("X-Api-Version", "v1")
                .body(response);
    }
}

record OrderResponse(String id, String status, BigDecimal total) {}
```

Test xác nhận hợp đồng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.http.MediaType.APPLICATION_JSON;

@Test
void returnsOrderRepresentation() throws Exception {
    mockMvc.perform(get("/api/orders/42").accept(APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(header().string("X-Api-Version", "v1"))
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.total").isNumber());
}
```

Những assertion này bảo đảm client nhận được JSON, có mã đơn hàng và trạng thái đúng, cùng trường tổng tiền có kiểu số. Nếu chỉ có `status().isOk()`, tất cả các điều kiện body và metadata này đều có thể sai mà test vẫn thành công.

### Các matcher JSONPath hữu ích

```java
jsonPath("$.id").value("42");
jsonPath("$.total").isNumber();
jsonPath("$.paid").isBoolean();
jsonPath("$.items").isArray();
jsonPath("$.customer").isMap();
jsonPath("$.items").isNotEmpty();
jsonPath("$.debug").doesNotExist();
```

Có thể kiểm tra phần tử trong mảng:

```java
jsonPath("$.items[0].sku").value("SKU-001");
jsonPath("$.items[0].quantity").value(2);
jsonPath("$.items.length()").value(1);
```

Đối với điều kiện phức tạp, matcher Hamcrest có thể diễn đạt rõ hơn:

```java
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.greaterThan;

jsonPath("$.items", hasSize(2));
jsonPath("$.total", greaterThan(0.0));
```

JSONPath giúp test tập trung vào phần hợp đồng quan trọng. Không cần assert mọi trường nếu client không phụ thuộc vào chúng; tuy nhiên, các trường định danh, trạng thái, số lượng và giá trị nghiệp vụ thường cần được xác nhận rõ.

## 5. So sánh toàn bộ JSON body

Khi response có cấu trúc nhỏ và ổn định, có thể so sánh body với JSON mong đợi:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(content().json(
                "{\"id\":\"42\",\"status\":\"PAID\",\"total\":125.00}"));
```

So sánh JSON thường ít phụ thuộc vào thứ tự field và khoảng trắng hơn so sánh chuỗi thô. Cần lưu ý chế độ so sánh của overload đang dùng: chế độ lenient thường cho phép field bổ sung và thứ tự mảng có thể linh hoạt; nếu hợp đồng yêu cầu cấu trúc chính xác, hãy chọn strict mode khi phiên bản Spring/JSONAssert hỗ trợ overload đó, hoặc kết hợp các assertion JSONPath cụ thể.

Không nên dùng `content().string(...)` để so sánh JSON chỉ vì chuỗi mong đợi dễ viết. Cách đó có thể khiến test thất bại do thứ tự field hoặc formatting dù nội dung JSON có cùng ý nghĩa. So sánh chuỗi phù hợp hơn với plain text, HTML fragment có chủ ý cố định hoặc body mà định dạng byte/chuỗi chính xác là một phần hợp đồng.

## 6. Xác nhận body rỗng và response không có nội dung

Với endpoint trả 204, hợp đồng thường yêu cầu status 204 và không có body:

```java
mockMvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Không phải endpoint thành công nào cũng cần JSON. Hãy kiểm tra body theo đúng hợp đồng: response 204 không cần JSON; response 201 có thể có body mô tả tài nguyên mới; response 202 có thể trả thông tin theo dõi tác vụ.

## 7. Xác nhận hợp đồng lỗi và validation

Error response cũng là một phần hợp đồng. Client cần biết status, mã lỗi và thông tin trường nào không hợp lệ. Ví dụ một API có thể quy định lỗi validation có dạng:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request is invalid",
  "fieldErrors": [
    { "field": "customerId", "message": "must not be blank" }
  ]
}
```

Test có thể gửi request không hợp lệ và xác nhận cả status lẫn cấu trúc lỗi:

```java
mockMvc.perform(post("/api/orders")
        .contentType(APPLICATION_JSON)
        .content("{\"customerId\":\"\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.fieldErrors[0].field").value("customerId"))
        .andExpect(jsonPath("$.fieldErrors[0].message").isNotEmpty());
```

Để test phản ánh đúng pipeline validation, controller cần dùng `@Valid` hoặc `@Validated` thích hợp và test phải nạp cấu hình validator. Nếu ứng dụng chuẩn hóa exception bằng `@RestControllerAdvice`, hãy nạp advice đó vào MockMvc context. Nếu dùng `standaloneSetup`, có thể đăng ký advice bằng `.setControllerAdvice(...)`.

Ngoài validation, hãy xác nhận các lỗi quan trọng khác theo hợp đồng: tài nguyên không tồn tại, không có quyền truy cập, xung đột trạng thái hoặc dữ liệu không hợp lệ. Đừng chỉ kiểm tra rằng request thất bại; hãy kiểm tra loại lỗi và payload client cần để xử lý.

## 8. Xác nhận MVC view, model và redirect

MockMvc cũng hỗ trợ controller trả về view thay vì JSON. Khi đó, hợp đồng của controller có thể gồm tên view và model attribute:

```java
mockMvc.perform(get("/orders/new"))
        .andExpect(status().isOk())
        .andExpect(view().name("orders/form"))
        .andExpect(model().attributeExists("order"))
        .andExpect(model().attribute("mode", "create"));
```

Với form submit thành công theo Post/Redirect/Get, hãy kiểm tra redirect và flash attribute:

```java
mockMvc.perform(post("/orders")
        .param("customerId", "C-12"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"))
        .andExpect(flash().attribute("message", "Order created"));
```

Các static matcher thường được import từ `MockMvcResultMatchers`: `view()`, `model()`, `redirectedUrl()` và `flash()`. Chúng kiểm tra kết quả MVC mà trình duyệt hoặc view renderer dựa vào.

## 9. Một test nên mô tả nhiều phần của cùng hợp đồng

Ví dụ test hoàn chỉnh thường nối nhiều `andExpect(...)` để mô tả response như một tập điều kiện:

```java
@Test
void createsOrderAccordingToApiContract() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .content("{\"customerId\":\"C-12\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(header().string("Location", "/api/orders/42"))
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.customerId").value("C-12"))
            .andExpect(jsonPath("$.status").value("NEW"));
}
```

Đọc test từ trên xuống có thể hiểu ngay client gửi gì và được cam kết điều gì: tạo tài nguyên thành công, nhận URL tài nguyên, và nhận representation với định danh, chủ sở hữu cùng trạng thái ban đầu.

## 10. Chọn mức độ chi tiết phù hợp

Assert quá ít khiến test bỏ lọt lỗi hợp đồng. Assert mọi chi tiết nội bộ lại khiến test dễ vỡ khi implementation thay đổi mà client không bị ảnh hưởng. Nên tập trung vào các thuộc tính có ý nghĩa với consumer:

- Status code và ý nghĩa của nó.
- Content type và headers/cookies bắt buộc.
- Tên, kiểu và giá trị của các trường JSON mà client sử dụng.
- Cấu trúc lỗi và thông tin validation mà client hiển thị.
- View, model hoặc redirect đối với luồng MVC server-side.

Tránh khóa test vào timestamp hiện tại, ID sinh ngẫu nhiên, thứ tự JSON object, header không thuộc hợp đồng hoặc thông tin debug nội bộ. Nếu giá trị động là một phần hợp đồng, kiểm tra định dạng hoặc quan hệ của nó thay vì hard-code một giá trị thay đổi theo mỗi lần chạy.

Ví dụ, thay vì so sánh một request ID ngẫu nhiên với chuỗi cố định, kiểm tra header tồn tại và không rỗng. Với timestamp, có thể xác nhận trường có định dạng ISO-8601 hoặc nằm trong khoảng hợp lý nếu điều đó thuộc yêu cầu.

## 11. Tổ chức test để dễ đọc và dễ bảo trì

Có thể chia test theo từng hành vi hợp đồng:

- `returnsOrderRepresentation`: xác nhận response thành công.
- `createsOrderAndReturnsLocation`: xác nhận status 201, Location và body.
- `returnsValidationErrorsForInvalidCustomer`: xác nhận status và payload validation.
- `returnsNotFoundWhenOrderDoesNotExist`: xác nhận hợp đồng lỗi 404.

Mỗi test nên gửi một request chính và xác nhận các thuộc tính liên quan. Nếu một endpoint có nhiều nhánh quan trọng, hãy có test riêng cho từng nhánh thay vì gom mọi tình huống vào một test dài.

Khi nhiều test dùng chung JSON request hoặc matcher, có thể trích helper để giảm lặp. Helper nên giữ tên theo ý nghĩa hợp đồng, ví dụ `expectOrderRepresentation(...)`, và không che giấu những assertion quan trọng.

Khi assertion thất bại, `andDo(print())` giúp in request và response để chẩn đoán:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(print())
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("42"));
```

`print()` chỉ hỗ trợ quan sát khi test chạy; nó không thay thế assertion và không làm cho test kiểm tra hợp đồng đầy đủ hơn.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test xanh dù body sai | Chỉ kiểm tra `status().isOk()` | Thêm assertion content type, JSONPath hoặc body theo hợp đồng |
| JSONPath không tìm thấy field | Tên field hoặc cấu trúc JSON khác với giả định | Xem response thực tế và kiểm tra path đúng cấp |
| Test thất bại do content type | Controller trả media type khác hoặc request chưa gửi `Accept` phù hợp | Kiểm tra `produces`, `Accept` và matcher tương thích |
| So sánh JSON thất bại dù dữ liệu tương đương | So sánh chuỗi thô hoặc dùng strict mode không cần thiết | Dùng JSON-aware matcher và chọn strictness theo hợp đồng |
| Test phụ thuộc giá trị ngẫu nhiên | Hard-code ID, timestamp hoặc session token được sinh động | Kiểm tra định dạng, sự hiện diện hoặc quan hệ của giá trị |
| Validation không trả lỗi như dự kiến | Thiếu `@Valid`, validator hoặc controller advice trong test context | Nạp đầy đủ cấu hình validation và exception handling |
| Redirect test không thấy flash attribute | Đang kiểm tra response body thay vì redirect/flash scope | Dùng `redirectedUrl()` và `flash()` |
| Response 204 có body ngoài dự kiến | Controller hoặc advice đang ghi nội dung không phù hợp | Kiểm tra implementation và xác nhận hợp đồng no-content |

## 13. Ghi nhớ

HTTP 200 chỉ nói request được xử lý thành công theo status mà server trả về; nó không bảo đảm response đáp ứng nhu cầu của client. Với MockMvc, hãy kết hợp `status()`, `content()`, `header()`, `cookie()`, `jsonPath()`, `view()`, `model()`, `redirectedUrl()` và `flash()` để kiểm tra những phần thuộc hợp đồng. Chọn assertion tập trung vào status, metadata, cấu trúc và giá trị dữ liệu mà consumer dựa vào. Nhờ vậy, test có thể phát hiện response sai ngay cả khi mã status vẫn là 200.

