# Document CRUD resource với request và response fields

## 1. Mục tiêu bài thực hành

Trong capstone này, bạn sẽ tài liệu hóa một REST resource có đủ thao tác CRUD bằng Spring REST Docs và MockMvc. Mỗi thao tác HTTP được kiểm thử với request/response thực tế; descriptor mô tả payload fields, path parameters, query parameters và headers. Snippet sinh ra được ghép thành tài liệu Asciidoctor/Markdown và đưa vào build, CI.

Resource mẫu là Product:

| HTTP method | Endpoint | Mục đích | Status thành công |
| --- | --- | --- | --- |
| GET | /api/products | Liệt kê sản phẩm | 200 OK |
| GET | /api/products/{id} | Xem một sản phẩm | 200 OK |
| POST | /api/products | Tạo sản phẩm | 201 Created |
| PUT | /api/products/{id} | Thay thế thông tin sản phẩm | 200 OK |
| PATCH | /api/products/{id} | Cập nhật một phần | 200 OK |
| DELETE | /api/products/{id} | Xóa sản phẩm | 204 No Content |

Không phải API nào cũng cần cả PUT và PATCH. Bài tập có cả hai để làm rõ request contract thay thế toàn bộ resource và request contract cập nhật một phần.

## 2. Thiết kế payload và hợp đồng resource

Một Product có cấu trúc JSON:

~~~json
{
  "id": "p-42",
  "name": "Mechanical Keyboard",
  "description": "Bàn phím cơ layout 75%",
  "price": 1299000,
  "currency": "VND",
  "active": true
}
~~~

Request tạo sản phẩm không chứa id vì server cấp định danh:

~~~json
{
  "name": "Mechanical Keyboard",
  "description": "Bàn phím cơ layout 75%",
  "price": 1299000,
  "currency": "VND",
  "active": true
}
~~~

Request PATCH chỉ chứa các field cần thay đổi:

~~~json
{
  "price": 1199000,
  "active": false
}
~~~

Các ví dụ dùng dữ liệu giả ổn định. Chọn bộ dữ liệu có thể tái tạo trong test để snippet không thay đổi ngẫu nhiên giữa các lần build.

## 3. DTO và controller mẫu

Định nghĩa request/response DTO riêng để phân biệt field client gửi và field server trả:

~~~java
record CreateProductRequest(String name, String description,
        BigDecimal price, String currency, boolean active) {}

record ReplaceProductRequest(String name, String description,
        BigDecimal price, String currency, boolean active) {}

record UpdateProductRequest(BigDecimal price, Boolean active) {}

record ProductResponse(String id, String name, String description,
        BigDecimal price, String currency, boolean active) {}
~~~

Controller minh họa các route và status:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    List<ProductResponse> list() { /* delegate to service */ }

    @GetMapping("/{id}")
    ProductResponse get(@PathVariable String id) { /* delegate to service */ }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        /* delegate to service */
    }

    @PutMapping("/{id}")
    ProductResponse replace(@PathVariable String id,
            @Valid @RequestBody ReplaceProductRequest request) {
        /* delegate to service */
    }

    @PatchMapping("/{id}")
    ProductResponse update(@PathVariable String id,
            @RequestBody UpdateProductRequest request) {
        /* apply partial update */
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(@PathVariable String id) { /* delegate to service */ }
}
~~~

Các phần thân hàm là điểm nối với service/repository, không phải implementation chạy độc lập. Khi áp dụng vào dự án, bảo đảm DTO, validation và status thực tế khớp hợp đồng đã chọn.

## 4. Cấu hình MockMvc và REST Docs

Với Spring Boot test, có thể dùng cấu hình tự động:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductCrudDocumentationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Nếu dùng cấu hình thủ công, áp dụng documentationConfiguration(...) vào MockMvc builder. Chỉ chọn một cách cấu hình cho mỗi test context để tránh đăng ký REST Docs nhiều lần.

## 5. GET collection: mô tả response fields và query parameters

Endpoint GET /api/products trả về danh sách. Giả sử API hỗ trợ phân trang với page và size:

~~~java
@Test
void listProducts() throws Exception {
    mockMvc.perform(get("/api/products")
                    .queryParam("page", "0")
                    .queryParam("size", "20")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andDo(document("products-list",
                    queryParameters(
                            parameterWithName("page").description("Số trang, bắt đầu từ 0"),
                            parameterWithName("size").description("Số phần tử tối đa mỗi trang")),
                    responseFields(
                            fieldWithPath("items").description("Danh sách sản phẩm"),
                            fieldWithPath("items[].id").description("Mã sản phẩm"),
                            fieldWithPath("items[].name").description("Tên sản phẩm"),
                            fieldWithPath("items[].description").description("Mô tả"),
                            fieldWithPath("items[].price").description("Giá"),
                            fieldWithPath("items[].currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("items[].active").description("Trạng thái hoạt động"),
                            fieldWithPath("page").description("Trang hiện tại"),
                            fieldWithPath("size").description("Kích thước trang"),
                            fieldWithPath("totalElements").description("Tổng số sản phẩm"))));
}
~~~

Ví dụ giả định response có envelope phân trang gồm items, page, size và totalElements. Nếu API trả trực tiếp JSON array hoặc dùng tên field khác, điều chỉnh descriptor theo payload thực tế. Với JSON array gốc, path thường bắt đầu từ [] thay vì items[].

## 6. GET resource: path parameter và response fields

~~~java
@Test
void getProduct() throws Exception {
    mockMvc.perform(get("/api/products/{id}", "p-42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("p-42"))
            .andDo(document("products-get",
                    pathParameters(parameterWithName("id").description("Mã sản phẩm")),
                    responseFields(
                            fieldWithPath("id").description("Mã sản phẩm"),
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("description").description("Mô tả sản phẩm"),
                            fieldWithPath("price").description("Giá sản phẩm"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Sản phẩm đang hoạt động"))));
}
~~~

Trong MockMvc, dùng URI template với biến id để REST Docs nhận diện path parameter. Nếu phiên bản Spring Framework yêu cầu builder chuyên dụng để giữ URI template variables, dùng RestDocumentationRequestBuilders theo hướng dẫn của phiên bản đó.

## 7. POST resource: request fields và response fields

POST tạo resource thường trả 201 Created và representation mới:

~~~java
@Test
void createProduct() throws Exception {
    mockMvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard",
                              "description": "Bàn phím cơ layout 75%",
                              "price": 1299000,
                              "currency": "VND",
                              "active": true
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("p-100"))
            .andDo(document("products-create",
                    requestFields(
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("description").description("Mô tả sản phẩm"),
                            fieldWithPath("price").description("Giá sản phẩm"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Trạng thái hoạt động")),
                    responseFields(
                            fieldWithPath("id").description("Mã sản phẩm do server cấp"),
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("description").description("Mô tả sản phẩm"),
                            fieldWithPath("price").description("Giá sản phẩm"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Trạng thái hoạt động"))));
}
~~~

Không đưa id vào request fields nếu client không gửi id. Đây là khác biệt quan trọng giữa request contract và response contract.

## 8. PUT resource: mô tả request thay thế toàn bộ

PUT thường yêu cầu representation đầy đủ theo hợp đồng API. Nếu tất cả field đều bắt buộc, descriptor nên strict:

~~~java
@Test
void replaceProduct() throws Exception {
    mockMvc.perform(put("/api/products/{id}", "p-42")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard Pro",
                              "description": "Bàn phím cơ có núm xoay",
                              "price": 1499000,
                              "currency": "VND",
                              "active": true
                            }
                            """))
            .andExpect(status().isOk())
            .andDo(document("products-replace",
                    pathParameters(parameterWithName("id").description("Mã sản phẩm")),
                    requestFields(
                            fieldWithPath("name").description("Tên thay thế"),
                            fieldWithPath("description").description("Mô tả thay thế"),
                            fieldWithPath("price").description("Giá thay thế"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Trạng thái hoạt động")),
                    responseFields(
                            fieldWithPath("id").description("Mã sản phẩm"),
                            fieldWithPath("name").description("Tên sản phẩm sau cập nhật"),
                            fieldWithPath("description").description("Mô tả sau cập nhật"),
                            fieldWithPath("price").description("Giá sau cập nhật"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Trạng thái hoạt động"))));
}
~~~

Nếu API cho phép PUT một phần hoặc có field server tự quản lý, descriptor phải phản ánh contract thực tế thay vì suy luận chỉ từ HTTP method.

## 9. PATCH resource: field tùy chọn

PATCH thường nhận một phần payload. Field có thể vắng mặt nên cần đánh dấu optional:

~~~java
@Test
void patchProduct() throws Exception {
    mockMvc.perform(patch("/api/products/{id}", "p-42")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "price": 1199000,
                              "active": false
                            }
                            """))
            .andExpect(status().isOk())
            .andDo(document("products-patch",
                    pathParameters(parameterWithName("id").description("Mã sản phẩm")),
                    requestFields(
                            fieldWithPath("price").optional()
                                    .description("Giá mới nếu cần thay đổi"),
                            fieldWithPath("active").optional()
                                    .description("Trạng thái mới nếu cần thay đổi")),
                    responseFields(
                            fieldWithPath("id").description("Mã sản phẩm"),
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("description").description("Mô tả sản phẩm"),
                            fieldWithPath("price").description("Giá hiện tại"),
                            fieldWithPath("currency").description("Đơn vị tiền tệ"),
                            fieldWithPath("active").description("Trạng thái hiện tại"))));
}
~~~

Descriptor optional không có nghĩa giá trị null và field vắng mặt luôn tương đương. Quy tắc xử lý null, xóa field hoặc bỏ qua field phải được định nghĩa trong API và có test riêng nếu quan trọng.

## 10. DELETE resource: response không có body

DELETE có thể trả 204 No Content. Khi response không có body, không khai báo responseFields cho payload không tồn tại:

~~~java
@Test
void deleteProduct() throws Exception {
    mockMvc.perform(delete("/api/products/{id}", "p-42"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""))
            .andDo(document("products-delete",
                    pathParameters(
                            parameterWithName("id").description("Mã sản phẩm cần xóa"))));
}
~~~

Nếu API trả 200 với body xác nhận xóa hoặc 202 Accepted cho xử lý bất đồng bộ, hãy mô tả response thực tế và giải thích semantics tương ứng.

## 11. Tái sử dụng descriptor mà không làm sai contract

Có thể tái sử dụng mô tả chuẩn cho field thật sự giống nhau, ví dụ currency hoặc active. Tuy nhiên, không dùng chung descriptor chỉ vì tên field giống nhau nếu required/optional hoặc ý nghĩa khác nhau.

~~~java
static FieldDescriptor currencyField() {
    return fieldWithPath("currency")
            .description("Mã tiền tệ theo ISO 4217")
            .attributes(key("example").value("VND"));
}

static FieldDescriptor optionalPatchPriceField() {
    return fieldWithPath("price")
            .optional()
            .description("Giá mới nếu cần thay đổi")
            .attributes(key("unit").value("VND"));
}
~~~

Factory tạo descriptor mới cho từng operation. Giữ request descriptors riêng response descriptors; field id do server cấp không nên được đưa vào request contract nếu client không gửi.

## 12. Biên soạn CRUD snippets thành AsciiDoc

Tạo file api-guide.adoc và include các snippet theo từng operation:

~~~adoc
= Product API
:toc:
:sectnums:

== Liệt kê sản phẩm
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/query-parameters.adoc[]
include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/response-fields.adoc[]

== Xem sản phẩm
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Tạo sản phẩm
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/request-fields.adoc[]
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]

== Thay thế sản phẩm
include::{snippets}/products-replace/http-request.adoc[]
include::{snippets}/products-replace/path-parameters.adoc[]
include::{snippets}/products-replace/request-fields.adoc[]
include::{snippets}/products-replace/http-response.adoc[]

== Cập nhật một phần
include::{snippets}/products-patch/http-request.adoc[]
include::{snippets}/products-patch/path-parameters.adoc[]
include::{snippets}/products-patch/request-fields.adoc[]
include::{snippets}/products-patch/http-response.adoc[]

== Xóa sản phẩm
include::{snippets}/products-delete/http-request.adoc[]
include::{snippets}/products-delete/path-parameters.adoc[]
include::{snippets}/products-delete/http-response.adoc[]
~~~

Chỉ include snippet mà operation thực sự sinh. Nếu endpoint không có body hoặc snippet chưa được cấu hình, không tạo include giả cho file không tồn tại.

## 13. Chạy và kiểm tra toàn bộ quy trình

Thứ tự build:

~~~text
Clean generated snippets
          |
          v
Run MockMvc documentation tests
          |
          v
Verify status and descriptor coverage
          |
          v
Generate CRUD snippets
          |
          v
Run Asciidoctor
          |
          v
Inspect HTML artifact
~~~

Với Gradle:

~~~bash
./gradlew clean test
./gradlew asciidoctor
~~~

Hoặc chạy một lần nếu task asciidoctor đã khai báo dependsOn test:

~~~bash
./gradlew clean asciidoctor
~~~

Sau build, kiểm tra mỗi operation có thư mục snippet riêng; path/query parameter snippets khớp route và filter; request fields không chứa field chỉ do server tạo; response fields mô tả đủ payload; PATCH đánh dấu field có thể vắng mặt đúng hợp đồng; DELETE không include response body nếu status là 204; tài liệu HTML không có include bị thiếu.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| POST request fields có id | Dùng response DTO làm request descriptor | Tách request và response contract |
| PATCH test thất bại khi thiếu field | Descriptor chưa đánh dấu optional | Dùng optional() cho field được phép vắng mặt |
| GET list không tìm thấy field | Response là array hoặc envelope khác giả định | Xem JSON thực tế và sửa path |
| PUT thiếu field nhưng test vẫn qua | Dùng relaxed hoặc optional quá rộng | Dùng strict descriptors cho contract đầy đủ |
| DELETE không có response-fields snippet | Response 204 không có body | Không khai báo responseFields cho body rỗng |
| Path parameter không được sinh | Request builder không giữ URI template variables | Dùng builder REST Docs phù hợp phiên bản |
| Asciidoctor thiếu file include | Identifier sai hoặc test chưa sinh snippet | Đồng bộ document identifier và include path |
| Snippet cũ còn sót | Output directory không được làm sạch | Chạy clean trước documentation tests |

## 15. Bài tập capstone

Hoàn thiện tài liệu CRUD cho Product:

1. Document GET collection có query parameters page, size và response envelope.
2. Document GET item có path parameter id và response fields.
3. Document POST với request fields, response fields và status 201.
4. Document PUT với request representation đầy đủ theo contract.
5. Document PATCH với các field optional và test riêng cho trường hợp chỉ cập nhật một field.
6. Document DELETE với status 204 và không có response body.
7. Thêm response lỗi 404 cho GET/PUT/DELETE và mô tả payload lỗi.
8. Include toàn bộ snippet vào một trang AsciiDoc.
9. Chạy build sạch và kiểm tra HTML.

**Tiêu chí hoàn thành:** mọi thao tác CRUD có documentation test; request/response fields phản ánh đúng DTO; path/query parameters được mô tả; trạng thái optional phù hợp; snippet được sinh từ test hiện tại và tài liệu Asciidoctor build thành công.

## 16. Checklist trước khi đưa vào CI

- [ ] Mỗi thao tác CRUD có test và operation identifier duy nhất.
- [ ] HTTP status và media type được assertion.
- [ ] Request fields và response fields được tách theo DTO.
- [ ] Path/query parameters được mô tả theo route thực tế.
- [ ] PATCH chỉ đánh dấu optional cho field thực sự có thể vắng mặt.
- [ ] DELETE 204 không khai báo response body.
- [ ] Error responses được kiểm tra và tài liệu hóa.
- [ ] Snippet output cũ được làm sạch trước build.
- [ ] AsciiDoc include trỏ đến đúng identifier và file được sinh.
- [ ] CI chạy documentation tests trước Asciidoctor và lưu HTML artifact.

**Ghi nhớ:** Tài liệu CRUD tốt cần mô tả riêng request và response của từng thao tác. GET, POST, PUT, PATCH và DELETE có contract khác nhau; dùng MockMvc assertions cùng strict field descriptors giúp snippet phản ánh chính xác API và phát hiện khi payload thay đổi.
