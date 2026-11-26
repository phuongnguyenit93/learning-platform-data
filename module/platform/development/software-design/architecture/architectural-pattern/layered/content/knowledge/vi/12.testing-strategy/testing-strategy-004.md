# Kiểm thử tầng trình bày về đầu vào, hợp đồng phản hồi và ánh xạ lỗi

> Chương: **Chiến lược kiểm thử**

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, chúng ta học cách tổ chức phần mềm theo kiến trúc phân tầng. Bài này tập trung vào cách kiểm thử tầng Presentation: xác minh request được tiếp nhận và kiểm tra đúng, dữ liệu được chuyển thành lời gọi Application phù hợp, response tuân thủ hợp đồng API và lỗi được ánh xạ thành phản hồi nhất quán.

Tầng Presentation thường gồm controller, request/response DTO, bộ chuyển đổi dữ liệu, cấu hình giao thức và bộ xử lý lỗi ở ranh giới HTTP. Các kiểm thử của tầng này giúp phát hiện lỗi tích hợp giữa Spring MVC, validation, Jackson và hợp đồng API. Chúng không thay thế kiểm thử quy tắc nghiệp vụ hoặc persistence; mục tiêu là xác minh điều mà client quan sát được khi giao tiếp với ứng dụng.

## 1. Tầng Presentation cần bảo đảm điều gì?

Hãy xét API `POST /orders`. Client gửi JSON chứa mã sản phẩm, số lượng và địa chỉ giao hàng. Controller nhận request, kiểm tra cấu trúc đầu vào, chuyển dữ liệu thành command rồi gọi use case. Sau đó, controller chuyển kết quả thành JSON, trả HTTP status và có thể thêm header `Location`.

Một kiểm thử Presentation nên quan tâm đến các câu hỏi:

- Request đúng định dạng có được chuyển tới đúng use case với dữ liệu chính xác không?
- Request thiếu trường, sai kiểu hoặc vi phạm validation có bị từ chối trước khi gọi Application không?
- Response có đúng HTTP status, content type, header và cấu trúc JSON đã công bố không?
- Lỗi nghiệp vụ như sản phẩm không còn được bán có được chuyển thành mã lỗi API ổn định không?
- Lỗi kỹ thuật có bị lộ stack trace, SQL hoặc chi tiết nội bộ ra ngoài không?
- Các thay đổi trong DTO, Jackson hoặc cấu hình Spring có vô tình làm thay đổi hợp đồng API không?

Đây là các hành vi ở ranh giới giao tiếp. Ví dụ, Presentation có thể kiểm tra `quantity` phải là số dương vì đó là điều kiện đầu vào của endpoint. Việc sản phẩm có đang được bán hoặc khách hàng có quyền mua hay không thuộc quy tắc nghiệp vụ và cần được kiểm thử ở Domain/Application.

## 2. Phân biệt kiểm thử controller với kiểm thử toàn bộ hệ thống

Trong Spring, có một số cách kiểm thử phù hợp với các mức khác nhau:

| Cách kiểm thử | Phạm vi | Khi nên dùng |
|---|---|---|
| Unit test controller thuần | Gọi method Java trực tiếp, không chạy Spring MVC pipeline | Kiểm tra logic chuyển đổi rất nhỏ, không phụ thuộc binding/validation/serialization |
| `@WebMvcTest` với MockMvc | Nạp lát cắt web, chạy routing, binding, validation, controller advice và serialization liên quan | Kiểm thử hợp đồng HTTP của controller một cách nhanh |
| `MockMvcBuilders.standaloneSetup(...)` | Dựng một MVC pipeline tối giản quanh controller đã chọn | Kiểm thử tập trung khi không cần Spring application context |
| `@SpringBootTest` với MockMvc hoặc HTTP client | Nạp ứng dụng rộng hơn, có thể gồm security, cấu hình và nhiều bean thật | Kiểm thử tích hợp cấu hình web và nhiều thành phần phối hợp |

Với mục tiêu của bài này, `@WebMvcTest` và MockMvc thường là lựa chọn cân bằng. Request đi qua Spring MVC như khi chạy thật nhưng Application service có thể được thay bằng mock để kiểm soát kết quả. Nhờ vậy, kiểm thử tập trung vào hành vi Presentation thay vì phụ thuộc database hoặc dịch vụ ngoài.

Không nên dùng unit test gọi trực tiếp `controller.create(request)` để kết luận `@Valid` hoạt động. Khi gọi method Java trực tiếp, Spring MVC không thực hiện request binding, Bean Validation, exception resolution hay JSON serialization. Những hành vi đó cần được kiểm thử qua MVC pipeline.

## 3. Xây dựng ví dụ API và hợp đồng dữ liệu

Giả sử API tạo đơn hàng nhận request như sau:

```json
{
  "productId": "a4b1c4c0-2c9d-4a2d-8c9a-8e3b5a8a1001",
  "quantity": 2,
  "shippingAddress": "12 Nguyen Hue, District 1"
}
```

Request DTO biểu diễn hợp đồng đầu vào:

Ứng dụng cần có implementation của Jakarta Bean Validation trên classpath, thường được thêm qua `spring-boot-starter-validation` trong dự án Spring Boot.

```java
public record CreateOrderRequest(
    @NotNull UUID productId,
    @NotNull @Positive Integer quantity,
    @NotBlank @Size(max = 300) String shippingAddress
) {}
```

Response DTO biểu diễn dữ liệu được công khai:

```java
public record OrderResponse(
    UUID id,
    BigDecimal total,
    String status
) {}
```

Controller chuyển request thành command và kết quả thành response:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final CreateOrderUseCase createOrder;

    public OrderController(CreateOrderUseCase createOrder) {
        this.createOrder = createOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        var command = new CreateOrderCommand(
            request.productId(), request.quantity(),
            request.shippingAddress());
        var result = createOrder.execute(command);
        var response = new OrderResponse(
            result.orderId(), result.total(), result.status());

        URI location = URI.create("/orders/" + result.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
```

Ví dụ đã lược bỏ package, import và định nghĩa các kiểu command/result. Controller không tự quyết định quy tắc tạo đơn; nó chỉ chuyển đổi giữa hợp đồng HTTP và API Application.

## 4. Kiểm thử request hợp lệ và ánh xạ dữ liệu

Với `@WebMvcTest`, có thể nạp riêng controller và thay use case bằng mock:

```java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerWebTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    CreateOrderUseCase createOrder;

    @Test
    void createsOrderAndReturnsHttpContract() throws Exception {
        UUID productId = UUID.fromString(
            "a4b1c4c0-2c9d-4a2d-8c9a-8e3b5a8a1001");
        UUID orderId = UUID.fromString(
            "b5c2d5d1-3d0e-5b3e-9d0b-9f4c6b9b2002");

        given(createOrder.execute(any(CreateOrderCommand.class)))
            .willReturn(new CreateOrderResult(
                orderId, new BigDecimal("125000.00"), "PENDING"));

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "productId": "%s",
                      "quantity": 2,
                      "shippingAddress": "12 Nguyen Hue"
                    }
                    """.formatted(productId)))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(header().string("Location", "/orders/" + orderId))
            .andExpect(jsonPath("$.id").value(orderId.toString()))
            .andExpect(jsonPath("$.total").value(125000.0))
            .andExpect(jsonPath("$.status").value("PENDING"));

        then(createOrder).should().execute(argThat(command ->
            command.productId().equals(productId)
                && command.quantity() == 2
                && command.shippingAddress().equals("12 Nguyen Hue")));
    }
}
```

Đoạn mã minh họa sử dụng Mockito BDD và MockMvc; các kiểu `CreateOrderUseCase`, `CreateOrderCommand` và `CreateOrderResult` thuộc Application. Kiểm thử xác minh hai phía của ranh giới:

- **Request đi vào:** JSON được bind thành DTO, rồi các trường được chuyển đúng vào command.
- **Response đi ra:** controller trả `201 Created`, JSON content type, header `Location` và các trường response đúng.

Chỉ kiểm tra `status().isCreated()` là chưa đủ. Một controller có thể trả đúng status nhưng sai body, thiếu header hoặc đổi tên trường JSON. Hãy xác minh các phần của hợp đồng mà client thực sự sử dụng.

## 5. Kiểm thử validation và request sai định dạng

Với `@Valid`, Spring MVC thực hiện validation trước khi gọi method controller. Có thể kiểm thử một trường không hợp lệ:

```java
@Test
void rejectsNonPositiveQuantityBeforeCallingUseCase() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "a4b1c4c0-2c9d-4a2d-8c9a-8e3b5a8a1001",
                  "quantity": 0,
                  "shippingAddress": "12 Nguyen Hue"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
        .andExpect(jsonPath("$.violations[0].field").value("quantity"));

    verifyNoInteractions(createOrder);
}
```

Kiểm thử này chứng minh request bị từ chối trước khi gọi Application. Nên bổ sung trường hợp thiếu `productId`, thiếu `quantity`, địa chỉ rỗng hoặc quá dài theo hợp đồng. Không cần viết một test cho mọi giá trị có thể; hãy chọn các ranh giới quan trọng như null, rỗng, min/max và sai kiểu.

Request JSON sai cú pháp hoặc không chuyển đổi được sang kiểu DTO cũng cần được kiểm thử:

```java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"productId\":"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("MALFORMED_JSON"));

    verifyNoInteractions(createOrder);
}
```

Lỗi validation và lỗi parse JSON đều có thể trả HTTP 400, nhưng mã lỗi nội bộ giúp client phân biệt nội dung không thỏa điều kiện với body không đọc được. Nếu API không cần phân biệt, có thể dùng một mã chung; điều quan trọng là hành vi phải ổn định và được ghi trong hợp đồng.

Ngoài ra, nên kiểm thử `Content-Type` không được hỗ trợ (thường là 415), `Accept` không phù hợp nếu API có thương lượng nội dung, và các trường hợp thiếu header bắt buộc. Chỉ thêm những trường hợp có ý nghĩa với giao thức thực tế của endpoint.

## 6. Chuẩn hóa response lỗi bằng Controller Advice

Không nên để mỗi controller tự tạo một cấu trúc lỗi khác nhau. `@RestControllerAdvice` cho phép ánh xạ exception thành response nhất quán tại ranh giới web.

Ví dụ cấu trúc lỗi:

```java
public record FieldViolation(String field, String message) {}

public record ApiError(
    String code,
    List<FieldViolation> violations
) {}
```

Một handler có thể xử lý lỗi validation, JSON sai và lỗi nghiệp vụ:

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> invalidRequest(
            MethodArgumentNotValidException exception) {
        var violations = exception.getBindingResult().getFieldErrors()
            .stream()
            .map(error -> new FieldViolation(
                error.getField(), error.getDefaultMessage()))
            .toList();

        return ResponseEntity.badRequest()
            .body(new ApiError("INVALID_REQUEST", violations));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> malformedJson(
            HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest()
            .body(new ApiError("MALFORMED_JSON", List.of()));
    }

    @ExceptionHandler(ProductNotSellableException.class)
    ResponseEntity<ApiError> productNotSellable(
            ProductNotSellableException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("PRODUCT_NOT_SELLABLE", List.of()));
    }
}
```

Trong ví dụ, `ProductNotSellableException` là lỗi nghiệp vụ được Application truyền tới ranh giới web. HTTP 409 được chọn vì trạng thái sản phẩm hiện tại xung đột với thao tác đặt hàng; API khác có thể dùng status khác theo semantics và hợp đồng đã công bố. Không có một ánh xạ duy nhất bắt buộc cho mọi hệ thống.

Khi xử lý validation, nên ưu tiên mã lỗi ổn định và tên trường. Nội dung message có thể được bản địa hóa hoặc thay đổi theo phiên bản thư viện; client không nên phải phân tích chuỗi message để quyết định logic.

## 7. Kiểm thử ánh xạ lỗi từ Application sang HTTP

Để kiểm tra lỗi nghiệp vụ, mock use case ném exception rồi xác minh response:

```java
@Test
void mapsBusinessConflictToStableApiError() throws Exception {
    given(createOrder.execute(any(CreateOrderCommand.class)))
        .willThrow(new ProductNotSellableException());

    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "a4b1c4c0-2c9d-4a2d-8c9a-8e3b5a8a1001",
                  "quantity": 2,
                  "shippingAddress": "12 Nguyen Hue"
                }
                """))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("PRODUCT_NOT_SELLABLE"))
        .andExpect(jsonPath("$.violations").isEmpty());
}
```

Kiểm thử này không cần database. Nó xác minh khi Application báo một lỗi nghiệp vụ đã biết, Presentation chuyển nó thành HTTP status và payload đúng. Nên có kiểm thử cho các lỗi quan trọng như không tìm thấy tài nguyên, trạng thái xung đột, không được phép và lỗi validation.

Không nên ánh xạ mọi exception thành 400 hoặc 500 mà không phân biệt. Ví dụ:

| Tình huống | HTTP status thường dùng | Điều cần kiểm tra |
|---|---:|---|
| JSON sai cú pháp hoặc DTO không hợp lệ | 400 | Mã lỗi và thông tin trường phù hợp |
| Không tìm thấy tài nguyên | 404 | Không để lộ truy vấn hoặc stack trace |
| Trạng thái hiện tại xung đột với thao tác | 409 | Mã lỗi ổn định, thông điệp có thể xử lý |
| Người gọi chưa xác thực | 401 | Hành vi challenge và header liên quan nếu có |
| Người gọi không đủ quyền | 403 | Không trả dữ liệu nhạy cảm |
| Lỗi ngoài dự kiến | 500 | Response tổng quát, không lộ chi tiết nội bộ |

Đây là gợi ý phổ biến, không phải bảng ánh xạ cứng cho mọi API. Hãy căn cứ semantics của HTTP, hợp đồng hiện tại và yêu cầu client.

## 8. Kiểm tra response contract kỹ hơn

Response contract không chỉ là một JSON có thể parse. Nó còn gồm status, header, kiểu dữ liệu, quy tắc null/optional và ý nghĩa của từng trường.

Khi kiểm thử response, hãy cân nhắc:

- **Status code:** `201 Created` khi tạo tài nguyên, `200 OK` khi trả kết quả đọc hoặc thao tác thành công theo hợp đồng, `204 No Content` khi không có body.
- **Content type:** `application/json` hoặc media type phiên bản nếu API sử dụng.
- **Header:** `Location` khi tạo tài nguyên, `ETag`, `Cache-Control`, pagination headers hoặc correlation ID nếu được công bố.
- **Body:** tên trường, kiểu dữ liệu, định dạng ngày/giờ, số thập phân, enum và cấu trúc lồng nhau.
- **Null và trường tùy chọn:** trường được bỏ qua hay trả `null`, giá trị mặc định là gì.
- **Không rò rỉ nội bộ:** response không chứa JPA entity, lazy proxy, stack trace, SQL, tên bảng hoặc thông tin bí mật.

Với số tiền, hãy xác định API biểu diễn bằng JSON number hay string và quy tắc làm tròn/đơn vị tiền tệ. Với thời gian, xác định timezone và định dạng, thường dùng ISO-8601. Các chi tiết này cần được kiểm thử vì thay đổi cấu hình Jackson có thể làm thay đổi payload mà không sửa controller.

Nếu response lớn hoặc được nhiều client sử dụng, có thể bổ sung contract test dựa trên OpenAPI hoặc consumer-driven contract. Contract test giúp phát hiện thay đổi không tương thích như xóa trường, đổi kiểu hoặc thay status. Tuy vậy, nó không thay thế kiểm thử hành vi thực tế của controller và exception handler.

## 9. Kiểm thử security và các thành phần web liên quan

Nếu endpoint yêu cầu xác thực hoặc phân quyền, Presentation test cũng nên xác minh ranh giới bảo mật:

- Request không có thông tin xác thực nhận phản hồi phù hợp, thường là 401.
- Người dùng đã xác thực nhưng không có quyền nhận 403.
- Người có quyền được phép đi tới controller và Application.
- Danh tính người dùng được lấy từ security context hoặc principal đáng tin cậy, không tin một `customerId` do client tùy ý gửi nếu API không cho phép.

Trong Spring Security, có thể dùng các annotation test như `@WithMockUser` hoặc request post processor để cung cấp principal. Nếu test slice nạp security filter chain, hãy cấu hình test user và CSRF token đúng với endpoint; không nên tắt toàn bộ filter chỉ để làm test chạy qua nếu mục tiêu là kiểm tra bảo mật.

Nếu một bài kiểm thử chỉ nhằm kiểm tra validation và response mapping, có thể cấu hình bảo mật test phù hợp để tránh nhiễu, nhưng cần có bộ kiểm thử riêng xác minh authentication/authorization. Không nên nhầm một controller test bỏ qua security với bằng chứng endpoint production được bảo vệ đúng.

## 10. Kiểm thử cấu hình serialization và binding

Jackson và Spring MVC tham gia chuyển JSON thành DTO và DTO thành response. Các thay đổi như đổi tên property, enum serialization, định dạng ngày tháng, xử lý unknown fields hoặc cấu hình null có thể làm hỏng client.

Nên có test cho các quy tắc được công bố:

- UUID sai định dạng bị từ chối theo response lỗi đã định nghĩa.
- Enum không được hỗ trợ có thông báo lỗi ổn định.
- Ngày giờ được serialize theo định dạng và timezone mong đợi.
- Trường optional được xử lý đúng khi vắng mặt hoặc có `null`.
- Response không vô tình serialize thêm thuộc tính nội bộ của entity.

Không cần kiểm thử mọi hành vi mặc định của Jackson. Hãy tập trung vào những điểm mà client phụ thuộc hoặc những cấu hình custom có nguy cơ thay đổi hợp đồng.

## 11. Giữ kiểm thử Presentation độc lập với nghiệp vụ và database

Trong `@WebMvcTest`, Application use case thường được mock. Đây là chủ ý: bài kiểm thử muốn xác minh controller gọi đúng hợp đồng và biểu diễn kết quả đúng, không cần xác minh logic tạo đơn hay câu SQL.

Các trách nhiệm nên được phân chia như sau:

| Kiểm thử | Nội dung xác minh |
|---|---|
| Presentation/Web slice | Routing, binding, validation, DTO mapping, HTTP status, headers, JSON và error mapping |
| Application unit test | Điều phối ca sử dụng, gọi repository/port, chuyển đổi lỗi ứng dụng |
| Domain unit test | Quy tắc và bất biến nghiệp vụ |
| Persistence integration test | Query, mapping, transaction và constraint database |
| End-to-end/integration test | Một số luồng quan trọng đi qua nhiều tầng trong cấu hình gần production |

Nếu mock use case, test không chứng minh quy tắc nghiệp vụ thật được thực thi. Nếu dùng database thật trong mọi controller test, test có thể chậm và khó khoanh vùng lỗi. Hãy giữ phần lớn kiểm thử Presentation nhanh bằng web slice, sau đó có một số integration test chọn lọc để xác minh các tầng phối hợp đúng.

## 12. Những lỗi thường gặp khi viết controller test

- **Chỉ gọi method controller trực tiếp:** bỏ qua binding, validation, filter, exception handler và serialization.
- **Chỉ kiểm tra status:** bỏ sót body hoặc header sai.
- **Mock quá nhiều chi tiết nội bộ:** test bị gắn với cách triển khai thay vì hợp đồng quan sát được.
- **Không xác minh use case không được gọi khi request sai:** validation có thể bị cấu hình sai mà test vẫn chỉ kiểm tra response chung.
- **Kiểm tra chuỗi message thay vì mã lỗi ổn định:** test dễ vỡ khi thay đổi ngôn ngữ hoặc validator.
- **Trả entity JPA trực tiếp trong response:** có thể làm lộ cấu trúc lưu trữ hoặc kích hoạt lazy loading.
- **Tắt security filter trong mọi test:** bỏ qua một phần quan trọng của hợp đồng endpoint.
- **Dùng `@SpringBootTest` cho mọi trường hợp:** tăng thời gian chạy và khiến lỗi khó xác định nếu chỉ cần kiểm tra MVC slice.

## 13. Checklist cho một bộ kiểm thử Presentation

Với mỗi endpoint quan trọng, hãy kiểm tra:

1. Request hợp lệ được bind và chuyển thành command đúng.
2. Trường bắt buộc, miền giá trị và định dạng sai được từ chối.
3. JSON sai cú pháp hoặc media type không phù hợp được xử lý theo hợp đồng.
4. Use case không được gọi khi request bị từ chối ở tầng Presentation.
5. Response có status, content type, header và body đúng.
6. Các lỗi nghiệp vụ quan trọng được ánh xạ sang status và mã lỗi ổn định.
7. Lỗi ngoài dự kiến không làm lộ stack trace, SQL hoặc thông tin nhạy cảm.
8. Authentication và authorization được kiểm thử nếu endpoint có yêu cầu bảo mật.
9. Thay đổi DTO hoặc serialization không âm thầm phá vỡ contract của client.

Không nhất thiết phải tạo một test riêng cho mọi tổ hợp đầu vào. Hãy ưu tiên các trường hợp thành công, biên hợp lệ/không hợp lệ, lỗi thường gặp và những phần hợp đồng có tác động lớn tới client.

## Ghi nhớ

- Presentation test xác minh hợp đồng HTTP: request binding, validation, chuyển đổi DTO, status, header, response body và error mapping.
- Dùng MockMvc với `@WebMvcTest` để chạy Spring MVC pipeline mà vẫn mock Application use case.
- Gọi trực tiếp method controller không kiểm tra được `@Valid`, JSON binding, serialization hoặc `@RestControllerAdvice`.
- Kiểm thử cả response thành công và lỗi; ưu tiên mã lỗi ổn định thay vì phụ thuộc chuỗi message.
- Tách kiểm thử Presentation khỏi Domain và persistence để test nhanh, dễ khoanh vùng; bổ sung integration test cho một số luồng phối hợp quan trọng.
- Security, serialization và header cũng là một phần của hợp đồng endpoint khi client phụ thuộc vào chúng.
