# Phân biệt query parameter với path parameter trong Spring REST Docs

## 1. Hai vị trí truyền dữ liệu trong URI

Một REST API thường dùng cả **path parameters** và **query parameters**. Ví dụ:

```http
GET /api/products/42/reviews?rating=5&page=0 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Trong URI trên, `42` là giá trị định danh sản phẩm nằm trong đường dẫn (path), còn `rating=5` và `page=0` nằm sau dấu `?` trong query string. Trong Spring MVC, giá trị path thường binding bằng `@PathVariable`; query string thường binding bằng `@RequestParam`.

Vị trí của dữ liệu quyết định cách định tuyến, cách binding và snippet cần dùng khi tạo tài liệu. Nếu nhầm hai loại, controller có thể không nhận đúng dữ liệu hoặc Spring REST Docs không ghi tham số vào đúng bảng.

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Bài này thuộc chương **Query parameters**, giúp bạn phân loại đúng dữ liệu trong URI và sử dụng `pathParameters(...)` hoặc `queryParameters(...)` tương ứng khi sinh snippet Asciidoctor/Markdown và đưa kiểm thử vào build/CI.

Sau bài học, bạn có thể:

1. Nhận diện path parameter, query parameter và các thành phần URI liên quan.
2. Liên hệ `@PathVariable` với `pathParameters(...)`, `@RequestParam` với `queryParameters(...)`.
3. Viết kiểm thử MockMvc document một request có cả path lẫn query parameters.
4. Phân biệt identifier tài nguyên với tiêu chí lọc, phân trang và sắp xếp.
5. Xác minh các lỗi thường gặp khi dùng sai snippet hoặc sai vị trí tham số.

## 2. Path parameter là gì?

Path parameter là một giá trị nằm trong một segment của đường dẫn URL và được ánh xạ vào biến trong path template.

Ví dụ route template:

```text
/api/products/{productId}
```

Request cụ thể:

```http
GET /api/products/42 HTTP/1.1
```

Spring MVC binding:

```java
@GetMapping("/api/products/{productId}")
public Product getProduct(@PathVariable Long productId) {
    return productService.findById(productId);
}
```

`{productId}` là placeholder trong template; `42` là giá trị cụ thể mà client gửi trong request. Path parameter thường xác định tài nguyên hoặc một thành phần trong cấu trúc tài nguyên:

| Route template | Path parameter | Ý nghĩa |
| --- | --- | --- |
| `/api/products/{id}` | `id` | Sản phẩm cụ thể |
| `/api/orders/{orderId}/items/{itemId}` | `orderId`, `itemId` | Một item thuộc đơn hàng |
| `/api/users/{userId}/addresses/{addressId}` | `userId`, `addressId` | Địa chỉ thuộc người dùng |

Path parameter thường là một phần của cấu trúc route. Nếu ID sản phẩm là bắt buộc, route chứa placeholder `{productId}` không khớp khi thiếu segment ID.

## 3. Query parameter là gì?

Query parameter nằm trong phần query string của URI, bắt đầu sau dấu `?`. Các cặp tên/giá trị thường được phân tách bởi dấu `&`:

```http
GET /api/products?category=phone&status=ACTIVE&page=0&size=20 HTTP/1.1
```

Ở đây, `category`, `status`, `page` và `size` là query parameters. Spring MVC thường binding chúng bằng `@RequestParam`:

```java
@GetMapping("/api/products")
public ProductPage search(
        @RequestParam(required = false) String category,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return productService.search(category, status, page, size);
}
```

Query parameters thường diễn tả các tùy chọn cho một thao tác trên tài nguyên hoặc collection:

- Lọc: `status=ACTIVE`, `category=phone`.
- Tìm kiếm: `q=wireless`.
- Phân trang: `page=0&size=20`.
- Sắp xếp: `sort=price,asc`.
- Chọn biểu diễn: `view=summary` hoặc `locale=vi`.

Nhiều query parameters có thể vắng mặt hoặc lặp, tùy hợp đồng endpoint. Các quy tắc default, giá trị hợp lệ, số lần lặp và điều kiện phụ thuộc phải được quy định rõ trong ứng dụng.

## 4. So sánh path parameter và query parameter

| Tiêu chí | Path parameter | Query parameter |
| --- | --- | --- |
| Vị trí | Trong path, thường gắn với placeholder `{name}` | Sau `?`, theo cặp `name=value` |
| Ví dụ | `/products/42` | `/products?status=ACTIVE` |
| Spring MVC | `@PathVariable` | `@RequestParam` |
| Spring REST Docs | `pathParameters(...)` | `queryParameters(...)` |
| Snippet mặc định | `path-parameters.adoc` | `query-parameters.adoc` |
| Vai trò thường gặp | Chỉ ra tài nguyên hoặc thành phần đường dẫn | Lọc, tìm kiếm, phân trang, sắp xếp, tùy chọn |
| Có thể vắng mặt? | Route có placeholder thường yêu cầu segment tương ứng; có thể có route khác không chứa nó | Có thể optional theo hợp đồng |
| Có thể lặp? | Không theo cách query key lặp; path có thể có nhiều placeholder ở vị trí khác nhau | Có thể lặp cùng tên, ví dụ `tag=java&tag=spring` |

### 4.1. Không phân loại theo tên biến

Tên `id` có thể xuất hiện ở nhiều vị trí:

```http
GET /api/products/42/reviews?userId=7&page=0 HTTP/1.1
```

Trong ví dụ này, `42` là path value của `productId`; `userId=7` và `page=0` là query parameters. Ý nghĩa của dữ liệu không tự quyết định loại tham số; **vị trí trên URI** quyết định. Một query parameter có tên `productId` vẫn là query parameter nếu nó được gửi sau dấu `?`.

### 4.2. Có thể dùng cả hai trong một request

API lấy đánh giá của một sản phẩm, lọc theo điểm và phân trang:

```http
GET /api/products/42/reviews?rating=5&page=0&size=10 HTTP/1.1
```

Controller có thể nhận:

```java
@GetMapping("/api/products/{productId}/reviews")
public ReviewPage findReviews(
        @PathVariable Long productId,
        @RequestParam(required = false) Integer rating,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "10") int size) {
    return reviewService.findByProduct(productId, rating, page, size);
}
```

Khi document, tách hai nhóm descriptor theo đúng vị trí.

## 5. Spring REST Docs: dùng đúng snippet cho từng loại

Spring REST Docs cung cấp hai API khác nhau trong `org.springframework.restdocs.request.RequestDocumentation`:

- `pathParameters(...)` mô tả các biến trong URI template.
- `queryParameters(...)` mô tả các tên xuất hiện trong query string.

Ví dụ:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

document("product-reviews",
    pathParameters(
        parameterWithName("productId")
            .description("ID của sản phẩm cần xem đánh giá")
    ),
    queryParameters(
        parameterWithName("rating")
            .description("Lọc theo điểm đánh giá, từ 1 đến 5")
            .optional(),
        parameterWithName("page")
            .description("Trang bắt đầu từ 0; mặc định 0")
            .optional(),
        parameterWithName("size")
            .description("Số đánh giá mỗi trang; mặc định 10")
            .optional()
    )
);
```

Khi test document chạy thành công, Spring REST Docs tạo hai snippet riêng:

```text
product-reviews/
  path-parameters.adoc
  query-parameters.adoc
  http-request.adoc
  http-response.adoc
  curl-request.adoc
```

Mỗi tên cần một descriptor trong nhóm tương ứng. Không khai báo `productId` trong `queryParameters(...)` nếu request chỉ có path segment `/products/42`; cũng không khai báo `rating` trong `pathParameters(...)` nếu nó nằm sau dấu `?`.

### 5.1. Path parameter và tính bắt buộc

Một route template `/products/{productId}` yêu cầu giá trị `productId` để match route. Nếu request không có segment đó, request thường không đi vào handler tương ứng. Vì thế, descriptor path thường là bắt buộc:

```java
pathParameters(
    parameterWithName("productId")
        .description("ID của sản phẩm")
)
```

Không nên dùng `optional()` để che mâu thuẫn của route: một path placeholder bắt buộc trong mapping thì request document cần cung cấp giá trị. Nếu một endpoint có hai route khác nhau, hãy document chúng như các request/operation riêng.

### 5.2. Mô tả giá trị mặc định cho query

Với query parameter như `page`:

```java
queryParameters(
    parameterWithName("page")
        .description("Trang bắt đầu từ 0; mặc định 0")
        .optional()
)
```

`optional()` cho phép request document không có `page`. Nội dung "mặc định 0" chỉ là phần mô tả hợp đồng; giá trị mặc định thực tế phải nằm trong cấu hình/logic controller và được test riêng.

## 6. Ví dụ hoàn chỉnh: path kết hợp query với MockMvc

### 6.1. Controller minh họa

Endpoint lấy review theo sản phẩm; điểm đánh giá và phân trang là query parameters:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReviewController {

    @GetMapping("/api/products/{productId}/reviews")
    public String findReviews(
            @PathVariable Long productId,
            @RequestParam(name = "rating", required = false) Integer rating,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "10") int size) {

        return "productId=" + productId
                + ";rating=" + (rating == null ? "ALL" : rating)
                + ";page=" + page
                + ";size=" + size;
    }
}
```

### 6.2. Cấu hình MockMvc và test tài liệu

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ReviewDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ReviewController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPathAndQueryParametersSeparately() throws Exception {
        mockMvc.perform(get("/api/products/{productId}/reviews", 42)
                        .queryParam("rating", "5")
                        .queryParam("page", "0")
                        .queryParam("size", "10"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "productId=42;rating=5;page=0;size=10"))
                .andDo(document("product-reviews",
                        pathParameters(
                                parameterWithName("productId")
                                        .description("ID của sản phẩm cần xem review")
                        ),
                        queryParameters(
                                parameterWithName("rating")
                                        .description("Điểm đánh giá, từ 1 đến 5")
                                        .optional(),
                                parameterWithName("page")
                                        .description("Trang bắt đầu từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Số review mỗi trang; mặc định 10")
                                        .optional()
                        )));
    }
}
```

Phân tích request:

1. `get("/api/products/{productId}/reviews", 42)` thay placeholder bằng giá trị path `42`.
2. `queryParam("rating", "5")`, `queryParam("page", "0")` và `queryParam("size", "10")` thêm dữ liệu sau dấu `?`.
3. Assertion response xác nhận Spring MVC binding đúng cả `@PathVariable` lẫn `@RequestParam`.
4. `pathParameters(...)` tạo bảng cho `productId`; `queryParameters(...)` tạo bảng cho `rating`, `page`, `size`.

Với cấu hình Gradle output snippets ở `build/generated-snippets`, identifier `product-reviews` tạo thư mục có:

```text
build/generated-snippets/product-reviews/
  path-parameters.adoc
  query-parameters.adoc
  http-request.adoc
  http-response.adoc
  curl-request.adoc
```

Tên thư mục Maven thường nằm dưới `target/generated-snippets/product-reviews/` nếu cấu hình tương ứng được sử dụng.

## 7. Đưa hai snippet vào tài liệu Asciidoctor

Trong trang Asciidoctor của API reviews, chèn hai file snippet:

```asciidoc
= Product Reviews API

== Lấy đánh giá của sản phẩm

GET /api/products/{productId}/reviews

=== Path parameters

include::SNIPPETS/product-reviews/path-parameters.adoc[]

=== Query parameters

include::SNIPPETS/product-reviews/query-parameters.adoc[]

=== HTTP request

include::SNIPPETS/product-reviews/http-request.adoc[]

=== HTTP response

include::SNIPPETS/product-reviews/http-response.adoc[]
```

Trong cấu hình dự án, thay tiền tố `SNIPPETS` ở ví dụ trên bằng đường dẫn snippet đã cấu hình (thường thông qua attribute của Asciidoctor). Nếu dùng template Markdown, có thể chọn `TemplateFormats.markdown()`; bước biên soạn cần ghép snippet theo công cụ của dự án vì Markdown thuần không cung cấp cú pháp `include` chuẩn như Asciidoctor.

## 8. Lỗi thiết kế API thường gặp

### 8.1. Đặt identifier tài nguyên trong query mà không có lý do

Ví dụ:

```http
GET /api/products?id=42
```

Không phải API nào dùng query `id` cũng sai; tuy nhiên, khi `id` xác định duy nhất tài nguyên, route `/api/products/42` thường thể hiện resource-oriented design rõ ràng hơn. Query `id` có thể phù hợp nếu endpoint tìm kiếm hỗ trợ nhiều ID:

```http
GET /api/products?id=42&id=43
```

Hãy chọn cấu trúc dựa trên hợp đồng nghiệp vụ, không dựa trên tên tham số đơn lẻ.

### 8.2. Dùng path cho một bộ lọc tùy chọn

Ví dụ route `/api/products/status/ACTIVE` có thể dùng khi trạng thái là thành phần cố định trong cấu trúc tài nguyên. Nếu endpoint là danh sách sản phẩm với nhiều tiêu chí lọc tùy chọn, query như `/api/products?status=ACTIVE` thường linh hoạt hơn. Cần cân nhắc khả năng kết hợp nhiều bộ lọc và cách bookmark/chia sẻ URL.

### 8.3. Khai báo descriptor sai nhóm

| Sai sót | Hệ quả | Sửa |
| --- | --- | --- |
| Đưa `productId` vào `queryParameters(...)` dù nó nằm trong `/products/42` | REST Docs báo query parameter chưa được mô tả hoặc descriptor không khớp | Đưa `productId` vào `pathParameters(...)` |
| Đưa `page` vào `pathParameters(...)` dù request dùng `?page=0` | REST Docs không tìm thấy path variable tương ứng | Đưa `page` vào `queryParameters(...)` |
| Request có query `sort` nhưng không có descriptor | Strict query snippet thất bại | Thêm descriptor và mô tả |
| URI template không có `{productId}` nhưng descriptor có `productId` | Path descriptor không khớp route template | Sửa route template hoặc descriptor theo endpoint thật |
| Dùng URL cố định `/products/42` nhưng muốn tài liệu hóa tên placeholder | Không có template variable để REST Docs nhận diện | Dùng `get("/products/{productId}", 42)` khi test MockMvc |

## 9. Encoding và kiểu dữ liệu của path/query

Cả path parameters và query parameters đều có thể chứa ký tự phải percent-encode, nhưng vị trí component khác nhau. Dùng URI builder hoặc HTTP request builder để encode đúng component. Không encode toàn URI bằng encoder dành cho giá trị query.

- Path: `/products/42`; placeholder `{productId}` được thay bằng giá trị cụ thể.
- Query: `/products?name=wireless%20earbuds`; `%20` biểu diễn dấu cách trong giá trị query.
- Dữ liệu có `/`, `?`, `&`, `#` cần xử lý theo component. Không giả định dấu gạch chéo được encode trong path sẽ luôn được server giữ như một ký tự của một segment; proxy và container có thể áp dụng chính sách riêng.

Với Spring MVC, chuyển kiểu dữ liệu cũng phụ thuộc vị trí nhưng đều qua cơ chế binding/conversion. Ví dụ:

```java
@GetMapping("/api/products/{productId}")
public Product get(@PathVariable Long productId) { ... }

@GetMapping("/api/products")
public ProductPage find(@RequestParam(defaultValue = "0") int page) { ... }
```

Nếu `productId=abc` hoặc `page=abc`, conversion có thể thất bại và ứng dụng thường trả HTTP 400. Spring REST Docs không tự xác minh giá trị `Long` hay `int`; cần có test riêng cho trường hợp hợp lệ/không hợp lệ.

## 10. WebTestClient và REST Assured

### 10.1. WebTestClient

Với WebTestClient đã cấu hình Spring REST Docs, gửi path qua URI template và query qua URI builder:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder
                .path("/api/products/{productId}/reviews")
                .queryParam("rating", 5)
                .queryParam("page", 0)
                .build(42))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("product-reviews-webclient",
                pathParameters(
                        parameterWithName("productId").description("ID sản phẩm")
                ),
                queryParameters(
                        parameterWithName("rating").description("Điểm review").optional(),
                        parameterWithName("page").description("Trang từ 0").optional()
                )));
```

### 10.2. REST Assured

REST Assured cũng tách path parameters và query parameters. Cách gắn filter document tùy cấu hình tích hợp REST Docs:

```java
given()
        .filter(documentationFilter)
        .pathParam("productId", 42)
        .queryParam("rating", 5)
        .queryParam("page", 0)
        .when()
        .get("/api/products/{productId}/reviews")
        .then()
        .statusCode(200);
```

Trong filter tài liệu hóa, khai báo `pathParameters(...)` cho `productId` và `queryParameters(...)` cho `rating`, `page`. Chỉ gọi `pathParam(...)`/`queryParam(...)` là chưa tạo snippet; thao tác `document(...)` vẫn phải được gắn vào filter.

## 11. Build và CI

Để kiểm tra tài liệu tự động:

1. Cấu hình Spring REST Docs cho MockMvc, WebTestClient hoặc REST Assured.
2. Đặt output snippet trong thư mục ổn định như `build/generated-snippets` (Gradle) hoặc `target/generated-snippets` (Maven).
3. Cho task Asciidoctor phụ thuộc task test và include đúng hai snippet `path-parameters.adoc` và `query-parameters.adoc`.
4. Chạy test và biên soạn tài liệu trong CI. Nếu đổi route placeholder hoặc thêm query parameter mà không cập nhật descriptor, test document strict sẽ phát hiện.

Ví dụ lệnh Gradle sau khi dự án cấu hình task tương ứng:

```bash
./gradlew test asciidoctor
```

Đối với endpoint dùng đồng thời path và query, thay đổi route `/products/{productId}` và thay đổi bộ lọc `?status=...` là hai thay đổi hợp đồng khác nhau. Test và tài liệu nên thể hiện mỗi thay đổi ở đúng nhóm snippet.

## 12. Bài tập thực hành

Hãy xây dựng tài liệu cho endpoint:

```http
GET /api/customers/CU-42/orders?status=PAID&status=SHIPPED&page=0&size=10 HTTP/1.1
```

Hợp đồng:

- `customerId` nằm trong path, bắt buộc và xác định khách hàng.
- `status` là query parameter tùy chọn, có thể lặp; chỉ nhận `PENDING`, `PAID`, `SHIPPED`, `CANCELLED`.
- `page` và `size` là query parameters tùy chọn, mặc định lần lượt là 0 và 10.
- `size` nằm trong khoảng 1–100.

Yêu cầu:

1. Tạo controller dùng `@PathVariable` cho `customerId`, `@RequestParam` cho `status`, `page`, `size`.
2. Viết MockMvc test bằng `get("/api/customers/{customerId}/orders", "CU-42")` và `.queryParam(...)` cho các bộ lọc.
3. Gắn `pathParameters(parameterWithName("customerId")...)` riêng với `queryParameters(...)` cho ba tham số query.
4. Xác nhận response chứa đúng giá trị đã binding và test lỗi cho status không hợp lệ hoặc size vượt giới hạn.
5. Sinh hai snippet, include vào Asciidoctor và chạy build/CI.

**Tiêu chí hoàn thành:** Không nhầm giá trị path với query; mỗi tham số nằm trong đúng nhóm descriptor; request hợp lệ sinh đủ snippet; kiểm tra validation/giá trị được thực hiện ngoài descriptor.

## 13. Ghi nhớ

Path parameters nằm trong các segment của path template và thường binding bằng `@PathVariable`; query parameters nằm sau dấu `?` và thường binding bằng `@RequestParam`. Trong Spring REST Docs, dùng `pathParameters(...)` cho placeholder của route và `queryParameters(...)` cho tên trong query string. Một request có thể dùng đồng thời hai nhóm; hãy tạo hai snippet riêng và kiểm thử cả binding lẫn quy tắc giá trị trước khi đưa tài liệu vào build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — `@PathVariable` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html)
- [Spring Framework — `@RequestParam` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
