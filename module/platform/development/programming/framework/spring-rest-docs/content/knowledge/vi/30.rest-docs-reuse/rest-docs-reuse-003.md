# Tái sử dụng parameter descriptors

## 1. Vì sao cần tái sử dụng parameter descriptors?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, các bài kiểm thử HTTP sinh snippet mô tả path parameter, query parameter và form parameter của REST API. Nhiều endpoint có thể chia sẻ cùng quy ước tham số: phân trang, lọc theo trạng thái, khoảng thời gian hoặc mã tài nguyên. Nếu mỗi test tự khai báo tên và mô tả tham số, tài liệu dễ thiếu nhất quán và khó cập nhật khi hợp đồng thay đổi.

Spring REST Docs dùng ParameterDescriptor để mô tả tham số. Các descriptor được truyền cho pathParameters(...), queryParameters(...) hoặc formParameters(...) để tạo snippet tương ứng và kiểm tra request thực tế. Ta có thể gom descriptor dùng chung thành factory method, rồi kết hợp với descriptor đặc thù của từng operation.

Ví dụ:

```text
GET /api/products?status=ACTIVE&page=0&size=20
GET /api/orders?status=PAID&page=0&size=20
GET /api/users?status=ENABLED&page=0&size=20
```

Ba endpoint cùng có page, size và status, nhưng ý nghĩa status khác nhau theo resource. Việc tái sử dụng cần giữ các mô tả chung đúng nghĩa và cho phép mỗi resource cung cấp mô tả riêng khi ngữ nghĩa khác.

Sau bài học, bạn có thể phân biệt ParameterDescriptor với FieldDescriptor; tạo factory cho path/query/form descriptor; ghép nhóm tham số chung với tham số riêng; xử lý optional, ignored và relaxed mode; và giữ strict validation khi contract thay đổi.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Với WebTestClient hoặc REST Assured, API tích hợp test khác nhau nhưng ParameterDescriptor vẫn có thể được tổ chức trong helper dùng chung.

## 2. ParameterDescriptor khác FieldDescriptor

Hai descriptor phục vụ hai vị trí khác nhau trong HTTP:

| Loại | Đối tượng | Ví dụ API | Snippet |
| --- | --- | --- | --- |
| Path parameter | ParameterDescriptor | pathParameters(...) | path-parameters.adoc |
| Query parameter | ParameterDescriptor | queryParameters(...) | query-parameters.adoc |
| Form parameter | ParameterDescriptor | formParameters(...) | form-parameters.adoc |
| JSON payload field | FieldDescriptor | requestFields(...) / responseFields(...) | request-fields.adoc / response-fields.adoc |

Ví dụ:

```http
POST /api/products?dryRun=true HTTP/1.1
Content-Type: application/json

{"name":"Keyboard","price":89.5}
```

- dryRun là query parameter, được mô tả bằng ParameterDescriptor.
- name và price là JSON field trong body, được mô tả bằng FieldDescriptor.

Không dùng requestFields(...) để mô tả query parameter và không dùng queryParameters(...) để mô tả JSON field. Việc chọn đúng descriptor giúp snippet phản ánh đúng vị trí dữ liệu trong HTTP request.

## 3. Tạo factory cho nhóm query parameter dùng chung

Giả sử nhiều endpoint hỗ trợ phân trang. Tạo helper trong test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.request.ParameterDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

public final class CommonParameterDescriptors {

    private CommonParameterDescriptors() {
    }

    public static List<ParameterDescriptor> paginationParameters() {
        return List.of(
            parameterWithName("page")
                .description("Số trang, bắt đầu từ 0"),
            parameterWithName("size")
                .description("Số phần tử trên mỗi trang")
        );
    }
}
```

Một test sử dụng:

```java
queryParameters(
    CommonParameterDescriptors.paginationParameters()
)
```

Danh sách trả về có thể được dùng với overload nhận Iterable/List descriptor của API tương ứng. Nếu phiên bản Spring REST Docs project đang dùng chỉ cung cấp overload varargs tại điểm gọi, chuyển danh sách thành mảng bằng toArray(ParameterDescriptor[]::new).

## 4. Kết hợp tham số chung với tham số riêng

Endpoint tìm sản phẩm có query parameter phân trang cùng bộ lọc category và status:

```java
static List<ParameterDescriptor> productSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonParameterDescriptors.paginationParameters());

    parameters.add(
        parameterWithName("category")
            .description("Danh mục sản phẩm cần lọc")
    );
    parameters.add(
        parameterWithName("status")
            .description("Trạng thái sản phẩm")
    );
    return parameters;
}
```

Ghi operation:

```java
document("products-search",
    queryParameters(productSearchParameters())
)
```

Endpoint danh sách đơn hàng có thể dùng cùng phân trang nhưng thêm customerId và status riêng:

```java
static List<ParameterDescriptor> orderSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonParameterDescriptors.paginationParameters());
    parameters.add(
        parameterWithName("customerId")
            .description("Mã khách hàng")
    );
    parameters.add(
        parameterWithName("status")
            .description("Trạng thái đơn hàng")
    );
    return parameters;
}
```

Tên status giống nhau nhưng mô tả khác vì một cái nói về sản phẩm, một cái nói về đơn hàng. Không nên dùng một mô tả chung chung cho các tham số chỉ vì chúng có cùng tên.

## 5. Factory cho path parameter

Path parameter thường định danh resource. Một số endpoint lồng nhau có thể cùng dùng userId:

```text
GET /api/users/{userId}/orders
GET /api/users/{userId}/addresses
GET /api/users/{userId}/settings
```

Có thể tạo factory:

```java
static ParameterDescriptor userIdParameter() {
    return parameterWithName("userId")
        .description("Mã định danh người dùng");
}
```

Dùng trong operation:

```java
pathParameters(
    userIdParameter()
)
```

Endpoint có thêm biến path riêng:

```java
pathParameters(
    userIdParameter(),
    parameterWithName("orderId")
        .description("Mã đơn hàng")
)
```

Với MockMvc, dùng RestDocumentationRequestBuilders để giữ URI template, giúp REST Docs nhận biết path variable. Nếu chỉ lưu path đã mở rộng mà không giữ template, descriptor có thể không xác định được tên tham số.

## 6. Factory cho form parameter

Form parameter nằm trong request body, thường là form-urlencoded. Ví dụ nhiều endpoint tìm kiếm legacy có thể dùng trường locale:

```http
POST /api/reports/search HTTP/1.1
Content-Type: application/x-www-form-urlencoded

locale=vi&format=csv
```

Factory:

```java
static List<ParameterDescriptor> reportFormatParameters() {
    return List.of(
        parameterWithName("locale")
            .description("Ngôn ngữ của báo cáo"),
        parameterWithName("format")
            .description("Định dạng file xuất")
    );
}
```

Dùng với formParameters(...):

```java
document("report-search-form",
    formParameters(reportFormatParameters())
)
```

Không dùng cùng một factory cho query và form chỉ vì tên parameter giống nhau. Vị trí truyền khác nhau và snippet được tạo cũng khác nhau; tách factory theo vai trò hoặc đặt tên method rõ như commonQueryPaginationParameters() và reportFormParameters().

## 7. Optional, ignored và relaxed mode

Tham số có thể không xuất hiện trong mọi request. Ví dụ sort chỉ được gửi khi người dùng chọn sắp xếp:

```java
static List<ParameterDescriptor> productSearchParameters() {
    return List.of(
        parameterWithName("page")
            .description("Số trang"),
        parameterWithName("size")
            .description("Kích thước trang"),
        parameterWithName("sort")
            .description("Trường sắp xếp")
            .optional()
    );
}
```

Các trạng thái thường dùng:

| Cách dùng | Ý nghĩa |
| --- | --- |
| Descriptor mặc định | Tham số được kỳ vọng có trong request và được mô tả |
| optional() | Tham số có thể vắng mặt |
| ignored() | Tham số không được hiển thị trong snippet và không được kiểm tra như descriptor thông thường |
| relaxedQueryParameters(...) | Cho phép query parameter ngoài danh sách descriptor |
| relaxedPathParameters(...) | Cho phép path parameter ngoài danh sách descriptor |
| relaxedFormParameters(...) | Cho phép form parameter ngoài danh sách descriptor |

Strict mode giúp phát hiện request có parameter chưa được mô tả hoặc descriptor bắt buộc không xuất hiện. Đây là cơ chế có ích khi operation đại diện cho hợp đồng đầy đủ.

Relaxed mode hữu ích khi tài liệu chỉ tập trung vào một phần tham số hoặc test không chịu trách nhiệm mô tả toàn bộ request. Tuy nhiên, không nên dùng relaxed cho mọi operation vì parameter mới có thể đi vào API mà không làm test yêu cầu cập nhật tài liệu.

### Tránh chia sẻ trạng thái descriptor

Các phương thức optional() và ignored() cấu hình descriptor. Nếu giữ một ParameterDescriptor static rồi thay đổi trạng thái trong test, operation khác có thể dùng lại instance đã thay đổi. Vì vậy:

- Ưu tiên factory method tạo descriptor mới cho mỗi operation.
- Chỉ dùng hằng số khi descriptor có cấu hình giống hệt ở mọi nơi.
- Không gọi optional() hoặc ignored() trên instance dùng chung nếu các operation có yêu cầu khác nhau.
- Tách factory bắt buộc và optional nếu ngữ nghĩa hợp đồng khác nhau.

## 8. Ví dụ MockMvc tái sử dụng query và path descriptors

Giả sử có API danh sách đơn hàng theo người dùng:

```java
@GetMapping("/users/{userId}/orders")
List<OrderResponse> findOrders(
        @PathVariable long userId,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
```

Factory:

```java
public final class OrderParameterDescriptors {
    private OrderParameterDescriptors() {}

    public static ParameterDescriptor userId() {
        return parameterWithName("userId")
            .description("Mã định danh người dùng");
    }

    public static List<ParameterDescriptor> orderSearch() {
        return List.of(
            parameterWithName("status")
                .description("Trạng thái đơn hàng")
                .optional(),
            parameterWithName("page")
                .description("Số trang, bắt đầu từ 0"),
            parameterWithName("size")
                .description("Số phần tử trên trang")
        );
    }
}
```

Test:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findOrders() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/users/{userId}/orders", 42)
                    .queryParam("page", "0")
                    .queryParam("size", "20")
            )
            .andExpect(status().isOk())
            .andDo(document("user-orders-search",
                pathParameters(OrderParameterDescriptors.userId()),
                queryParameters(OrderParameterDescriptors.orderSearch())
            ));
    }
}
```

Operation này dùng factory path cho userId và factory query cho status/page/size. Vì status optional nên test có thể chạy mà không gửi status. Nếu server thêm query parameter chưa mô tả, strict query descriptor sẽ báo lỗi.

## 9. Ví dụ tái sử dụng form descriptors

Giả sử endpoint tìm báo cáo nhận form-urlencoded:

```java
@PostMapping(
    path = "/reports/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ReportResult search(
        @RequestParam String locale,
        @RequestParam String format) {
    // ...
}
```

Factory:

```java
static List<ParameterDescriptor> reportFormParameters() {
    return List.of(
        parameterWithName("locale").description("Ngôn ngữ báo cáo"),
        parameterWithName("format").description("Định dạng file xuất")
    );
}
```

Test:

```java
mockMvc.perform(
        post("/api/reports/search")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("locale", "vi")
            .param("format", "csv")
    )
    .andExpect(status().isOk())
    .andDo(document("report-search",
        formParameters(reportFormParameters())
    ));
```

Đặt Content-Type form-urlencoded và dùng dữ liệu form để test khớp hợp đồng. Nếu endpoint nhận JSON body, hãy dùng requestFields(...) thay vì formParameters(...).

## 10. Tổ chức helper và quy ước đặt tên

Có thể đặt helper trong test source set:

```text
src/
  test/
    java/
      com/example/api/docs/
        CommonParameterDescriptors.java
        ProductParameterDescriptors.java
        OrderParameterDescriptors.java
        ReportParameterDescriptors.java
```

Quy ước nên dùng:

- Tên factory thể hiện rõ loại parameter và phạm vi: paginationQueryParameters(), userPathParameters(), reportFormParameters().
- Chia sẻ mô tả khi cả tên, vị trí và ý nghĩa tham số đều giống nhau.
- Tách factory nếu cùng tên parameter nhưng ý nghĩa khác theo resource.
- Factory trả descriptor mới nếu có optional/ignored khác nhau.
- Ghép danh sách bằng ArrayList hoặc helper composition để thêm tham số đặc thù.
- Không phụ thuộc helper test vào service/controller production.

Đừng tạo một lớp CommonParameters chứa mọi tham số của toàn hệ thống. Helper quá tổng quát sẽ che mất ngữ cảnh, khiến mô tả sai nghĩa dù tên parameter giống nhau.

## 11. Include parameter snippets trong Asciidoctor

Ví dụ file src/docs/asciidoc/orders.adoc:

```asciidoc
= Orders API
:toc: left

== Tìm đơn hàng theo người dùng

=== Path parameters
include::{snippets}/user-orders-search/path-parameters.adoc[]

=== Query parameters
include::{snippets}/user-orders-search/query-parameters.adoc[]

== Tìm báo cáo

=== Form parameters
include::{snippets}/report-search/form-parameters.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc generated snippets; phần đường dẫn phía sau phải khớp operation ID. Nếu dùng outputDir riêng, cập nhật attribute trong cấu hình build. Có thể include thêm http-request.adoc hoặc cURL/HTTPie snippet để người đọc xem toàn bộ request cạnh bảng tham số.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query snippet không có parameter mong đợi | Factory không thêm parameter hoặc test tạo request khác. | Đối chiếu query string thực tế với descriptor. |
| Path descriptor không tìm thấy placeholder | URI template bị mất trong MockMvc request builder. | Dùng RestDocumentationRequestBuilders và path template. |
| Form descriptor không khớp request | Content-Type không phải form-urlencoded hoặc test gửi JSON. | Đặt Content-Type phù hợp và dùng formParameters(...). |
| Test báo undocumented parameter | Strict mode phát hiện parameter ngoài descriptor. | Bổ sung mô tả hoặc dùng relaxed mode có chủ đích. |
| Test báo thiếu parameter bắt buộc | Descriptor chưa optional nhưng request không gửi. | Sửa request hoặc đánh dấu optional nếu contract cho phép. |
| Một operation bị optional ngoài ý muốn | Chia sẻ ParameterDescriptor instance đã cấu hình. | Tạo descriptor mới trong factory cho từng operation. |
| Mô tả sai nghĩa dù cùng tên | Dùng chung factory giữa resource có ý nghĩa khác nhau. | Tách factory theo domain/resource. |
| Asciidoctor không tìm snippet | Sai operation ID, outputDir hoặc attribute snippets. | Kiểm tra folder sinh ra sau test và include path. |

## 13. Bài thực hành

Tạo ba operation:

1. GET /api/products: query parameters category, status, page, size.
2. GET /api/users/{userId}/orders: path parameter userId cùng query parameters status, page, size.
3. POST /api/reports/search: form parameters locale và format.

Thực hiện:

1. Tạo CommonParameterDescriptors với factory cho pagination query parameters.
2. Tạo ProductParameterDescriptors và OrderParameterDescriptors, ghép tham số riêng với phân trang chung.
3. Tạo factory riêng cho userId path parameter và report form parameters.
4. Đánh dấu status optional theo hợp đồng; viết thêm một operation strict để phát hiện parameter không được mô tả.
5. Thử dùng chung instance rồi gọi optional() ở một nơi; thay bằng factory mới cho từng operation.
6. Include ba parameter snippets vào Asciidoctor cùng request snippets.
7. Chạy clean test và Asciidoctor; xác nhận tài liệu được sinh từ operation hiện tại.

**Tiêu chí hoàn thành:** phân biệt ParameterDescriptor với FieldDescriptor; tái sử dụng được parameter có cùng ý nghĩa; ghép được tham số riêng theo endpoint; quản lý optional/ignored/relaxed có chủ đích; strict validation vẫn phát hiện hợp đồng thay đổi.

## 14. Tài liệu tham khảo

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — ParameterDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/ParameterDescriptor.html)
