# path-parameters, query-parameters và form-parameters

## 1. Ba vị trí truyền tham số trong HTTP request

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP tạo snippet để mô tả hợp đồng API. Một request có thể mang tham số trong path của URL, trong query string hoặc trong phần form data của request body. Spring REST Docs cung cấp descriptor riêng cho từng loại:

| Loại tham số | Descriptor | Snippet | Vị trí dữ liệu |
| --- | --- | --- | --- |
| Path parameter | pathParameters(...) | path-parameters.adoc | Placeholder trong URI template, ví dụ /users/{id} |
| Query parameter | queryParameters(...) | query-parameters.adoc | Phần query sau dấu ?, ví dụ ?page=2&size=20 |
| Form parameter | formParameters(...) | form-parameters.adoc | Form body, thường có media type application/x-www-form-urlencoded |

Ba loại này không thể thay thế tùy ý cho nhau. Path parameter thường định danh tài nguyên; query parameter thường lọc, sắp xếp hoặc phân trang; form parameter thường nhận dữ liệu từ HTML form hoặc form-urlencoded client. JSON body có cấu trúc riêng và thường được mô tả bằng requestFields(...), không phải formParameters(...).

Spring REST Docs tạo snippet descriptor khi test gọi document(...) cùng descriptor tương ứng. Nếu chỉ gửi request mà không khai báo descriptor, các bảng tham số này không tự xuất hiện. Ví dụ trong bài dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**.

## 2. Path parameter: biến nằm trong URI template

Path parameter là một phần của đường dẫn endpoint:

```text
GET /api/users/{userId}/orders/{orderId}
```

Với một lần gọi cụ thể, placeholder được thay bằng giá trị:

```text
GET /api/users/42/orders/9001
```

Path parameter phù hợp khi giá trị là một phần định danh hoặc phân cấp của tài nguyên. Ví dụ userId xác định người dùng và orderId xác định đơn hàng thuộc người dùng đó.

Khai báo descriptor:

```java
pathParameters(
    parameterWithName("userId").description("Mã người dùng"),
    parameterWithName("orderId").description("Mã đơn hàng")
)
```

REST Docs tạo file path-parameters.adoc, thường là bảng gồm tên tham số và mô tả. Descriptor có thể đánh dấu tham số optional hoặc ignored theo hợp đồng và trường hợp kiểm thử.

### Ví dụ MockMvc

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/users/{userId}/orders/{orderId}", 42, 9001)
    )
    .andExpect(status().isOk())
    .andDo(document("users-order-find",
        pathParameters(
            parameterWithName("userId").description("Mã người dùng"),
            parameterWithName("orderId").description("Mã đơn hàng")
        )
    ));
```

Với MockMvc và Spring Framework 6.1 trở xuống, dùng các method của RestDocumentationRequestBuilders để giữ URI template trong request, giúp REST Docs truy xuất tên placeholder. Nếu builder khác làm mất template, request có thể chỉ còn path đã mở rộng và việc tài liệu hóa path parameter không xác định được tên biến. Với Spring Framework mới hơn, kiểm tra hướng dẫn của phiên bản dự án.

Path parameter thường phù hợp với endpoint như:

```text
GET    /api/products/{id}
PATCH  /api/products/{id}
DELETE /api/products/{id}
GET    /api/users/{userId}/orders/{orderId}
```

Bộ lọc tùy chọn hoặc lựa chọn sắp xếp thường phù hợp với query parameter hơn nếu chúng không thuộc cấu trúc định danh tài nguyên.

## 3. Query parameter: lọc, phân trang và điều khiển kết quả

Query parameter nằm sau dấu ? trong URL. Nhiều tham số được phân tách bởi &:

```text
GET /api/products?category=keyboard&page=0&size=20&sort=name,asc
```

Trường hợp sử dụng thường gặp:

- Lọc: category, status, active.
- Phân trang: page, size, cursor.
- Sắp xếp: sort, direction.
- Chọn cách biểu diễn: locale, include, fields.

Khai báo query descriptor:

```java
queryParameters(
    parameterWithName("category")
        .description("Danh mục sản phẩm cần lọc"),
    parameterWithName("page")
        .description("Số trang, bắt đầu từ 0"),
    parameterWithName("size")
        .description("Số phần tử trên mỗi trang"),
    parameterWithName("sort")
        .description("Trường và hướng sắp xếp")
)
```

Snippet được sinh là query-parameters.adoc. Nó mô tả query parameter, không phải bảng dành cho path hoặc form data.

### Ví dụ MockMvc

```java
mockMvc.perform(
        get("/api/products")
            .queryParam("category", "keyboard")
            .queryParam("page", "0")
            .queryParam("size", "20")
    )
    .andExpect(status().isOk())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("category").description("Danh mục sản phẩm"),
            parameterWithName("page").description("Số trang"),
            parameterWithName("size").description("Kích thước trang")
        )
    ));
```

Nếu request builder/client khác tạo query string trực tiếp trong URI, descriptor vẫn phải khớp tên parameter mà operation nhận được.

### Optional và relaxed mode

Một query parameter có thể không xuất hiện trong mọi request, ví dụ sort hoặc locale. Đánh dấu optional khi hợp đồng cho phép vắng mặt:

```java
parameterWithName("sort")
    .description("Trường sắp xếp")
    .optional()
```

Trong strict mode, parameter có trong request nhưng chưa được mô tả có thể làm snippet generation thất bại; descriptor bắt buộc nhưng request không có cũng có thể làm test thất bại. Đây là cơ chế giữ tài liệu đồng bộ với request đã test.

Khi chỉ muốn mô tả một phần parameter trong một kịch bản, dùng API relaxed tương ứng, chẳng hạn relaxedQueryParameters(...). Relaxed mode bỏ qua parameter chưa mô tả; dùng có chủ đích để tránh che việc API thêm query parameter ngoài tài liệu.

## 4. Form parameter: dữ liệu form trong request body

Form parameter được gửi trong body, thường với header:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=linh&rememberMe=true
```

Phân biệt query và form:

| Tiêu chí | Query parameter | Form parameter |
| --- | --- | --- |
| Vị trí | URL sau dấu ? | Request body |
| Media type | Nằm trong URL | Thường application/x-www-form-urlencoded |
| Ví dụ | /products?page=0 | username=linh&rememberMe=true |
| Descriptor | queryParameters(...) | formParameters(...) |
| Snippet | query-parameters.adoc | form-parameters.adoc |

Form parameter thường xuất hiện ở form đăng nhập, form tìm kiếm legacy, form HTML hoặc endpoint tương thích hệ thống cũ. Nếu endpoint nhận JSON như {"username":"linh"}, hãy dùng requestFields(...) để mô tả JSON, không dùng form parameter descriptor.

Khai báo form descriptor:

```java
formParameters(
    parameterWithName("username").description("Tên đăng nhập"),
    parameterWithName("rememberMe")
        .description("Có ghi nhớ phiên đăng nhập hay không")
)
```

Snippet sinh ra là form-parameters.adoc. API formParameters(...) có trong Spring REST Docs từ phiên bản 3.0.0; với project cũ hơn, kiểm tra khả năng tương thích trước khi dùng.

### Ví dụ MockMvc

```java
mockMvc.perform(
        post("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("username", "linh")
            .param("rememberMe", "true")
    )
    .andExpect(status().isOk())
    .andDo(document("login-form",
        formParameters(
            parameterWithName("username").description("Tên đăng nhập"),
            parameterWithName("rememberMe")
                .description("Ghi nhớ phiên đăng nhập")
        )
    ));
```

MockMvc .param(...) thêm request parameter; với POST form-urlencoded, các giá trị form được gửi trong form body. Đặt Content-Type phù hợp để test phản ánh đúng cách client gửi dữ liệu.

Form parameter cũng có thể optional:

```java
parameterWithName("rememberMe")
    .description("Ghi nhớ phiên đăng nhập")
    .optional()
```

Nếu form có parameter được gửi nhưng chưa được mô tả, strict formParameters(...) có thể làm operation thất bại. Dùng relaxedFormParameters(...) khi kịch bản chỉ cần mô tả một tập con; những parameter còn lại được bỏ qua.

## 5. Ví dụ hoàn chỉnh: path và query trong một endpoint

Một API tìm kiếm có thể dùng path và query cùng lúc:

```java
@GetMapping("/users/{userId}/orders")
List<OrderResponse> findOrders(
        @PathVariable long userId,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page) {
    // ...
}
```

Test:

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/users/{userId}/orders", 42)
            .queryParam("status", "PAID")
            .queryParam("page", "0")
    )
    .andExpect(status().isOk())
    .andDo(document("user-orders-search",
        pathParameters(
            parameterWithName("userId").description("Mã người dùng")
        ),
        queryParameters(
            parameterWithName("status")
                .description("Lọc theo trạng thái").optional(),
            parameterWithName("page").description("Số trang")
        )
    ));
```

Một endpoint form đơn giản:

```java
@PostMapping(
    path = "/login",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ResponseEntity<Void> login(
        @RequestParam String username,
        @RequestParam(required = false) String returnTo) {
    // ...
    return ResponseEntity.ok().build();
}
```

Test:

```java
mockMvc.perform(
        post("/api/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("username", "linh")
            .param("returnTo", "/dashboard")
    )
    .andExpect(status().isOk())
    .andDo(document("login-form",
        formParameters(
            parameterWithName("username").description("Tên đăng nhập"),
            parameterWithName("returnTo")
                .description("Đường dẫn quay lại").optional()
        )
    ));
```

Trong dự án thật, bảo đảm controller mapping và test dùng cùng context path/API prefix. Không ghi mật khẩu hoặc token thật vào form snippet; ví dụ đăng nhập nên dùng credential giả.

## 6. Kiểm tra descriptor và hợp đồng

Các snippet parameter không chỉ tạo bảng; descriptor còn kiểm tra request mà test ghi nhận.

| Tình huống | Hành vi strict mode thường gặp |
| --- | --- |
| Request có parameter chưa mô tả | Test thất bại vì tài liệu chưa bao phủ parameter |
| Descriptor bắt buộc nhưng request không có parameter | Test thất bại vì descriptor không khớp operation |
| Descriptor optional và request vắng parameter | Được chấp nhận |
| Descriptor ignored | Không hiển thị trong snippet nhưng tránh lỗi do parameter đó |
| Dùng relaxed descriptor | Parameter ngoài danh sách mô tả được bỏ qua |

Strict mode phù hợp khi một operation đại diện cho hợp đồng đầy đủ. Relaxed mode hữu ích khi nhiều endpoint chia sẻ parameter hoặc test chỉ tập trung vào một nhóm tham số. Nếu dùng relaxed ở mọi nơi, API có thể thêm parameter mà tài liệu không phản ánh.

Nên tạo operation riêng cho các biến thể có ý nghĩa: tìm kiếm mặc định, tìm kiếm có filter/sort, gửi form có trường tùy chọn vắng mặt và gửi form với đầy đủ trường. Nếu các biến thể khác nhau về hợp đồng, tách operation ID giúp tài liệu rõ và tránh snippet ghi đè lẫn nhau.

## 7. Include parameter snippet trong Asciidoctor

Ví dụ file src/docs/asciidoc/users.adoc:

```asciidoc
= Users API
:toc: left

== Tìm đơn hàng của người dùng

=== Path parameters
include::{snippets}/user-orders-search/path-parameters.adoc[]

=== Query parameters
include::{snippets}/user-orders-search/query-parameters.adoc[]

== Đăng nhập bằng form

=== Form parameters
include::{snippets}/login-form/form-parameters.adoc[]
```

Attribute {snippets} phải trỏ tới thư mục gốc generated snippets. Đường dẫn phía sau phải khớp operation ID truyền vào document(...). Nếu outputDir đặt riêng, cập nhật attribute snippets cho đúng.

Có thể include thêm HTTP request, cURL hoặc HTTPie cho cùng operation để người đọc xem request đầy đủ bên cạnh bảng tham số.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tạo path-parameters.adoc | Chưa gọi pathParameters(...), hoặc URI template bị mất. | Khai báo descriptor và dùng request builder giữ template. |
| Thiếu query-parameters.adoc | Dùng nhầm API hoặc chưa thêm queryParameters(...). | Dùng RequestDocumentation.queryParameters(...) cho query string. |
| Thiếu form-parameters.adoc | Gửi JSON body hoặc chưa gọi formParameters(...). | Gửi form-urlencoded và khai báo descriptor đúng. |
| Test báo undocumented parameter | Request có parameter chưa mô tả trong strict mode. | Bổ sung descriptor hoặc dùng relaxed mode có chủ đích. |
| Test báo parameter bắt buộc không tồn tại | Descriptor không optional nhưng request không gửi. | Sửa test hoặc đánh dấu optional nếu hợp đồng cho phép. |
| Form parameter không được nhận diện | Content-Type/body không phải form-urlencoded. | Đặt application/x-www-form-urlencoded và gửi form data đúng cách. |
| Query có trong URL nhưng không có trong bảng | Descriptor chưa liệt kê query parameter hoặc client tạo request khác dự kiến. | Đối chiếu request snippet và descriptor. |
| Asciidoctor không tìm thấy snippet | Sai operation ID, outputDir hoặc attribute snippets. | Kiểm tra thư mục sau test và include path. |

## 9. Bài thực hành

Tạo API Orders gồm:

1. GET /api/users/{userId}/orders: path parameter userId, query parameter status, page và size.
2. POST /api/login: nhận form-urlencoded gồm username, password và rememberMe.
3. Viết MockMvc test cho hai endpoint; dùng pathParameters(...), queryParameters(...) và formParameters(...) tương ứng.
4. Tạo trường hợp status và rememberMe optional; xác minh test vẫn chạy khi chúng vắng mặt.
5. Cố ý gửi thêm parameter chưa mô tả để quan sát strict mode thất bại, sau đó bổ sung descriptor hoặc chuyển riêng test cần thiết sang relaxed mode.
6. Include ba snippet parameter vào Asciidoctor và đặt cạnh request snippet tương ứng.
7. Kiểm tra không có password/token thật trong snippet và chạy clean test cùng Asciidoctor.

**Tiêu chí hoàn thành:** phân biệt path, query và form parameter theo vị trí truyền; dùng đúng ba descriptor; giải thích strict/relaxed/optional; đọc ba file snippet tương ứng; tài liệu được sinh lại từ test trong build/CI mà không lộ thông tin xác thực.

## 10. Tài liệu tham khảo

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
