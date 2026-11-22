# Constraint trên request field và path/query parameter

## 1. Mục tiêu

HTTP request có thể mang dữ liệu trong JSON body, path variable hoặc query string. Mỗi vị trí có cách binding khác nhau, nhưng đều có thể chịu constraints như bắt buộc, độ dài, định dạng, giới hạn số hoặc quy tắc nghiệp vụ.

Ví dụ: GET /api/orders/101/items?page=0&size=20&sku=BOOK-42. Giá trị 101 là path variable orderId; page, size và sku là query parameters.

Bài học thuộc chương Constraints của SPRING_REST_DOCS. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown rồi tích hợp build và CI.

Sau bài học, bạn có thể phân biệt validation trên body DTO, query model và method parameters; áp dụng Bean Validation; mô tả constraints bằng REST Docs descriptors; kiểm tra cả request hợp lệ lẫn validation error.

> Vị trí dữ liệu quyết định cách Spring bind và validate; descriptor của REST Docs quyết định cách dữ liệu được trình bày. Hai việc cần được nối bằng HTTP tests và mô tả rõ ràng.

## 2. Ba vị trí dữ liệu và descriptor

| Vị trí | Ví dụ | Validation | REST Docs |
| --- | --- | --- | --- |
| JSON body | {"quantity":2} | DTO property | requestFields(...) |
| Path | /api/orders/{orderId} | Controller parameter/domain lookup | pathParameters(...) |
| Query | ?page=0&size=20 | @RequestParam hoặc query DTO | queryParameters(...) |

requestFields mô tả body; pathParameters mô tả biến URI; queryParameters mô tả query string. Descriptor không tự kiểm tra miền giá trị. parameterWithName("page").description("Trang bắt đầu từ 0") chỉ mô tả parameter, không kiểm tra page âm.

## 3. Constraint trên JSON request field

### 3.1. DTO và Bean Validation

~~~java
import jakarta.validation.constraints.*;

public record CreateOrderItemRequest(
    @NotBlank @Size(min = 3, max = 30) String sku,
    @NotNull @Min(1) @Max(100) Integer quantity,
    @Size(max = 250) String note
) {}
~~~

| Field | Constraint | Ý nghĩa |
| --- | --- | --- |
| sku | NotBlank, Size 3–30 | Mã sản phẩm phải có nội dung và độ dài hợp lệ. |
| quantity | NotNull, Min 1, Max 100 | Số lượng bắt buộc, từ 1 đến 100. |
| note | Size max 250 | Ghi chú có thể vắng mặt, tối đa 250 ký tự. |

NotNull khác NotBlank. NotNull cấm null; NotBlank dành cho chuỗi và yêu cầu ký tự không phải whitespace. Absent, explicit null và empty string là các trạng thái khác nhau.

Controller kích hoạt validation cho DTO:

~~~java
@PostMapping("/api/orders/{orderId}/items")
public ResponseEntity<OrderItemResponse> addItem(
        @PathVariable long orderId,
        @Valid @RequestBody CreateOrderItemRequest request) {
    OrderItemResponse created = orderService.addItem(orderId, request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Ví dụ yêu cầu Bean Validation provider và cấu hình Spring MVC phù hợp.

### 3.2. Test và mô tả request fields

~~~java
mockMvc.perform(post("/api/orders/{orderId}/items", 101)
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"sku":"BOOK-42","quantity":2,"note":"Giao giờ hành chính"}
            """))
    .andExpect(status().isCreated())
    .andDo(document("order-items-create",
        requestFields(
            fieldWithPath("sku")
                .description("Mã sản phẩm; bắt buộc, dài 3–30 ký tự"),
            fieldWithPath("quantity")
                .description("Số lượng; bắt buộc, từ 1 đến 100"),
            fieldWithPath("note")
                .description("Ghi chú tùy chọn; tối đa 250 ký tự")
                .optional()
        )
    ));
~~~

Đây là method bổ sung vào lớp test đã cấu hình. Constraint được ghi trong description để template mặc định hiển thị. requestFields kiểm tra descriptor khớp payload theo chế độ đang dùng; optional là quy tắc descriptor, không thay thế Bean Validation và không chứng minh giới hạn 250 được thực thi.

### 3.3. ConstraintDescriptions cho DTO properties

~~~java
ConstraintDescriptions constraints =
    new ConstraintDescriptions(CreateOrderItemRequest.class);

String rules = String.join("; ",
    constraints.descriptionsForProperty("quantity"));

FieldDescriptor quantityField =
    fieldWithPath("quantity").description("Số lượng. " + rules);
~~~

ConstraintDescriptions tìm property constraints qua Bean Validation Validator. Phải đưa kết quả vào descriptor; REST Docs không tự thêm chúng vào bảng mặc định. Nếu JSON field name khác Java property cần mapping riêng. Class-level/cross-field và domain rules cần mô tả/test riêng.

## 4. Constraint trên path variable

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
@Validated
class OrderItemController {
    @GetMapping("/{orderId}/items")
    public List<OrderItemResponse> listItems(
            @PathVariable @Min(1) @Max(999999999) long orderId) {
        return orderService.listItems(orderId);
    }
}
~~~

Ví dụ giả định method validation được kích hoạt phù hợp version Spring. Với nhiều cấu hình MVC trước đây, @Validated trên bean kết hợp method validation infrastructure; Spring Framework 6.1+ có tích hợp method validation MVC riêng. Xác minh cấu hình thực tế, không giả định annotation chắc chắn hoạt động chỉ vì được khai báo.

Giá trị không parse được thành long có thể gây binding/conversion error; giá trị parse được nhưng ngoài range có thể gây validation error. Đây là hai failure mode khác nhau.

Test và descriptor:

~~~java
mockMvc.perform(get("/api/orders/{orderId}/items", 101))
    .andExpect(status().isOk())
    .andDo(document("order-items-list",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng; số nguyên dương")
        )
    ));
~~~

Dùng request builder giữ URI template để REST Docs nhận diện orderId. pathParameters sinh path-parameters.adoc nhưng không tự đọc @Min/@Max trên controller method argument. Constraint được ghi trong description tường minh.

| Path | Ý nghĩa | Cần test |
| --- | --- | --- |
| /api/orders/101/items | ID hợp lệ | Status/body thành công. |
| /api/orders/0/items | Vi phạm Min(1) | Validation error. |
| /api/orders/1000000000/items | Vượt Max | Validation error. |
| /api/orders/abc/items | Không convert được | Binding/conversion error. |
| /api/orders/999/items | Đúng range, tài nguyên không có | Domain 404. |

Min(1) không chứng minh order tồn tại hay caller có quyền truy cập.

ConstraintDescriptions mặc định tìm property constraints của Java type; không truyền controller class và kỳ vọng nó tự lấy annotation từ method parameter. Với path parameters, mô tả thủ công, dùng helper đọc method annotation hoặc custom metadata/template. Reflection chỉ đọc annotation, không chứng minh validation đã được kích hoạt.

## 5. Constraint trên query parameters

### 5.1. @RequestParam

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
        @RequestParam(required = false)
        @Pattern(regexp = "createdAt,(asc|desc)|total,(asc|desc)") String sort) {
    return orderService.search(page, size, sort);
}
~~~

Contract minh họa: page mặc định 0 và không âm; size mặc định 20, từ 1 đến 100; sort tùy chọn, chỉ nhận giá trị theo pattern. Cần kích hoạt method validation theo version/cấu hình Spring phù hợp.

Nếu size=abc với target int, lỗi có thể phát sinh ở bước binding trước Bean Validation. size=101 parse được nhưng ngoài range. Nên test riêng.

### 5.2. queryParameters snippet

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("page", "0")
        .queryParam("size", "20")
        .queryParam("sort", "createdAt,desc"))
    .andExpect(status().isOk())
    .andDo(document("orders-search",
        queryParameters(
            parameterWithName("page")
                .description("Chỉ số trang không âm; mặc định 0"),
            parameterWithName("size")
                .description("Số phần tử/trang; từ 1 đến 100; mặc định 20"),
            parameterWithName("sort")
                .description("Tùy chọn; createdAt hoặc total kết hợp asc/desc")
                .optional()
        )
    ));
~~~

queryParameters sinh query-parameters.adoc. Descriptor không tự lấy Min, Max, Pattern, defaultValue hoặc required từ method argument. Đưa các giới hạn vào description/helper/template.

### 5.3. Query DTO với @ModelAttribute

~~~java
public class OrderSearchQuery {
    @Min(0)
    private Integer page = 0;

    @Min(1)
    @Max(100)
    private Integer size = 20;

    @Pattern(regexp = "createdAt,(asc|desc)|total,(asc|desc)")
    private String sort;

    // getters/setters
}

@GetMapping("/api/orders")
public Page<OrderResponse> search(@Valid @ModelAttribute OrderSearchQuery query) {
    return orderService.search(query);
}
~~~

Query DTO đưa các parameter thành Java properties, phù hợp với ConstraintDescriptions:

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(OrderSearchQuery.class);
List<String> sizeRules = descriptions.descriptionsForProperty("size");
~~~

Việc validation model attribute phụ thuộc Spring binding/cấu hình. HTTP test phải chứng minh giá trị sai bị từ chối.

queryParameters nhận descriptors theo tên HTTP parameter, không tự lấy DTO metadata. Có thể ghép descriptions vào description của parameterWithName. Helper nên nhận riêng HTTP name, Java property name và description nghiệp vụ để hỗ trợ mapping khác tên.

## 6. Validation errors và binding errors

Ví dụ error body theo contract riêng của ứng dụng:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid parameters",
  "violations": [
    {"field":"size","message":"Số phần tử mỗi trang phải từ 1 đến 100."}
  ]
}
~~~

Đây không phải response mặc định của Spring; ứng dụng có thể dùng Problem Details hoặc schema riêng.

~~~java
@Test
void rejectPageSizeAboveMaximum() throws Exception {
    mockMvc.perform(get("/api/orders").queryParam("size", "101"))
        .andExpect(status().isBadRequest())
        .andDo(document("orders-search-invalid-size"));
}
~~~

~~~java
@Test
void rejectNonPositiveOrderId() throws Exception {
    mockMvc.perform(get("/api/orders/{orderId}/items", 0))
        .andExpect(status().isBadRequest())
        .andDo(document("order-items-invalid-id"));
}
~~~

Hai test giả định method/model validation đã được kích hoạt và exception handler ánh xạ violation thành 400. Tài liệu phải theo response thật.

| Loại lỗi | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Binding/conversion | size=abc | Không chuyển được thành kiểu Java. |
| Constraint validation | size=101 khi max 100 | Giá trị parse được nhưng ngoài miền. |
| Domain validation | Order không tồn tại | Quy tắc nghiệp vụ. |
| Authorization | Caller không có quyền | Chính sách truy cập. |

## 7. Strictness của parameter descriptors

pathParameters và queryParameters kiểm tra parameter thực tế với descriptors. Ở strict mode, parameter có trong request nhưng chưa mô tả có thể làm snippet generation thất bại; descriptor bắt buộc nhưng request không có cũng có thể thất bại.

- optional() cho phép parameter descriptor vắng mặt trong operation.
- relaxedPathParameters(...) và relaxedQueryParameters(...) cho phép parameter bổ sung chưa mô tả.
- Descriptor đã khai báo nhưng không optional vẫn phải được đáp ứng.

optional() là quy tắc tạo snippet, không thay required=false, default value hoặc validation logic ở controller. Với body fields, requestFields có strictness riêng. Không dùng relaxed descriptor chỉ để làm test xanh khi chưa review contract change.

## 8. Cách trình bày constraint

| Cách | Ưu điểm | Lưu ý |
| --- | --- | --- |
| Viết trong description | Dễ dùng với template mặc định | Phải cập nhật khi rule đổi. |
| ConstraintDescriptions + helper | Tái sử dụng metadata DTO property | Không tự đọc method parameters. |
| Descriptor attributes + custom template | Có cột constraint thống nhất | Cần duy trì template theo version. |

Ví dụ: parameterWithName("orderId").description("Mã đơn hàng; số nguyên dương; phải trỏ tới đơn hàng tồn tại"). Mô tả này kết hợp range và domain lookup; @Min(1) chỉ kiểm tra con số.

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders?page=0&size=20")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-search-webtestclient",
        queryParameters(
            parameterWithName("page").description("Chỉ số trang không âm; mặc định 0"),
            parameterWithName("size").description("Số phần tử mỗi trang từ 1 đến 100")
        )
    ));
~~~

Đây là ví dụ gắn descriptors; test size=101 cần test riêng. Dùng module spring-restdocs-webtestclient và cấu hình REST Docs phù hợp.

### 9.2. REST Assured

~~~java
given(spec)
    .filter(document("orders-search-restassured",
        queryParameters(
            parameterWithName("page").description("Chỉ số trang không âm; mặc định 0"),
            parameterWithName("size").description("Số phần tử mỗi trang từ 1 đến 100")
        )
    ))
    .queryParam("page", 0)
    .queryParam("size", 20)
.when()
    .get("/api/orders")
.then()
    .statusCode(200);
~~~

spec phải cấu hình server và REST Docs. Filter có thể ghi operation trước assertion cuối; CI chỉ phát hành khi toàn bộ test suite pass.

## 10. Asciidoctor, Markdown và CI

~~~asciidoc
= Orders API

== Danh sách mặt hàng

=== Path parameters
include::{snippets}/order-items-list/path-parameters.adoc[]

=== HTTP request
include::{snippets}/order-items-list/http-request.adoc[]

=== Query parameters
include::{snippets}/orders-search/query-parameters.adoc[]

=== Request fields
include::{snippets}/order-items-create/request-fields.adoc[]
~~~

Identifier là ví dụ, phải khớp test thực tế. Thuộc tính snippets cần trỏ đến output directory. Markdown renderer thuần không tự hiểu Asciidoctor include; cần template hoặc bước chuyển đổi.

~~~mermaid
flowchart TD
    A["DTO / path / query constraints"] --> B["HTTP tests: valid + invalid + boundary"]
    B --> C{"Assertions pass?"}
    C -->|No| D["Fail CI"]
    C -->|Yes| E["REST Docs descriptors"]
    E --> F["Generate snippets"]
    F --> G["Render docs"]
    G --> H{"Includes pass?"}
    H -->|No| D
    H -->|Yes| I["Review and publish"]
~~~

Khi đổi min/max, regex, default hoặc required behavior, cập nhật tests và descriptions. ConstraintDescriptions hữu ích cho DTO properties; method parameters và domain rules cần helper/review riêng. Render task phải chạy sau test sinh snippets và không include artifact cũ.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| @Min trên PathVariable không chạy | Method validation chưa kích hoạt | Kiểm tra Spring version/config và test HTTP. |
| Query sai kiểu trả lỗi khác violation | Binding xảy ra trước validation | Test input không parse được riêng. |
| ConstraintDescriptions không tìm @Min trên controller parameter | Resolver tập trung property constraints | Mô tả method parameter riêng. |
| Query snippet không có min/max | Descriptor chỉ có description chung | Bổ sung giới hạn bằng helper/template. |
| Path snippet thiếu biến | Không giữ URI template hoặc thiếu descriptor | Dùng request builder phù hợp. |
| optional nhưng server vẫn báo thiếu | Nhầm REST Docs optional với controller required/default | Đồng bộ hai tầng. |
| size=101 vẫn được chấp nhận | Validation chưa kích hoạt | Kiểm tra provider, method validation, boundary test. |
| ID đúng range nhưng 404 | Tài nguyên không tồn tại | Tách domain lookup khỏi range constraint. |
| Relaxed descriptor che parameter mới | Chưa review contract | Xác nhận parameter có công khai. |
| Docs lỗi thời sau khi đổi giới hạn | Description thủ công không cập nhật | Review snippet diff trong CI. |

## 12. Bài thực hành

Endpoint giả định:

~~~text
GET /api/customers/{customerId}/orders?page=0&size=20&status=PAID
~~~

Contract:

- customerId: số nguyên dương; khách hàng phải tồn tại và caller có quyền.
- page: số nguyên không âm, mặc định 0.
- size: từ 1 đến 100, mặc định 20.
- status: tùy chọn, chỉ nhận PENDING, PAID, CANCELLED.

Thực hiện:

1. Chọn validation strategy cho path/query parameters.
2. Tạo query DTO nếu phù hợp và cấu hình Bean Validation.
3. Viết HTTP tests cho customerId=0, page=-1, size=101, size=abc và status không hợp lệ.
4. Phân biệt validation, binding, not found và authorization.
5. Dùng pathParameters/queryParameters mô tả giới hạn, default và optional.
6. Dùng ConstraintDescriptions cho query DTO properties; không giả định nó đọc controller method parameters.
7. Include snippets vào Asciidoctor, review diff và xác nhận CI không publish khi test/descriptor/render thất bại.

**Tiêu chí hoàn thành:** xác định đúng vị trí constraint, kiểm chứng bằng HTTP tests, mô tả chính xác path/query/body và phân biệt validation với binding/domain errors.

## Tài liệu tham khảo

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
