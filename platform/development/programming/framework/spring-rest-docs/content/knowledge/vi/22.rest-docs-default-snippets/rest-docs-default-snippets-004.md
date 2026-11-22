# request-body và response-body

## 1. Vai trò của hai snippet body

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP tạo snippet từ request và response mà test thực hiện. Hai snippet request-body.adoc và response-body.adoc tập trung vào payload của thông điệp HTTP: dữ liệu client gửi lên và dữ liệu server trả về.

| Snippet | Nội dung | Câu hỏi cần trả lời |
| --- | --- | --- |
| request-body.adoc | Body của HTTP request | Client gửi payload gì? |
| response-body.adoc | Body của HTTP response | Server trả payload gì? |

Hai snippet giúp người đọc xem dữ liệu mẫu. Chúng không tự mô tả ý nghĩa field, quy tắc validation hay schema đầy đủ. Muốn giải thích cấu trúc JSON/XML theo từng field và ràng buộc tài liệu với payload, hãy dùng descriptor như requestFields(...) và responseFields(...).

Spring REST Docs tạo snippet khi test thực hiện request và ghi operation bằng document(...). Body snippet hữu ích khi operation thực sự có payload tương ứng. GET không có request body thường không có nội dung request body đáng kể; response 204 No Content không có response body để tài liệu hóa.

Ví dụ trong bài sử dụng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Cùng nguyên tắc áp dụng với WebTestClient và REST Assured thông qua module tích hợp tương ứng.

## 2. Phân biệt body snippet với HTTP message và field descriptor

Ba tầng thông tin này bổ sung cho nhau:

| Tầng | Snippet/descriptor | Nội dung thể hiện |
| --- | --- | --- |
| HTTP message | http-request.adoc, http-response.adoc | Method, URI/status, header và toàn bộ body trong ngữ cảnh HTTP |
| Payload riêng | request-body.adoc, response-body.adoc | Nội dung body tách riêng |
| Bảng mô tả cấu trúc | request-fields.adoc, response-fields.adoc | Tên field, mô tả và trạng thái optional/ignored |

Ví dụ request:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Mechanical Keyboard","price":89.5}
```

Trong ví dụ:

- http-request.adoc thể hiện method, path, header và body cùng một thông điệp.
- request-body.adoc chỉ chứa JSON payload.
- request-fields.adoc (nếu test khai báo requestFields(...)) tạo bảng giải thích name và price.

Ví dụ response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/42

{"id":42,"name":"Mechanical Keyboard","price":89.5}
```

http-response.adoc giữ status/header cùng payload; response-body.adoc chỉ có JSON; response-fields.adoc giải thích các field. Dùng cả ba khi người đọc cần xem giao thức, payload mẫu và ý nghĩa field.

## 3. request-body.adoc: payload client gửi lên

Request body thường xuất hiện với các thao tác tạo hoặc cập nhật tài nguyên như POST, PUT và PATCH. Payload có thể là JSON, XML, form data, multipart hoặc nội dung nhị phân.

Ví dụ JSON:

```json
{
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true,
  "tags": ["office", "accessory"]
}
```

Snippet này cho người đọc thấy dữ liệu mẫu mà test đã gửi. Nó hữu ích để hiểu định dạng payload, sao chép request mẫu, đối chiếu payload với Content-Type và review thay đổi field giữa các phiên bản API.

Body snippet không thay thế kiểm tra validation. Test vẫn cần assertion cho status và kết quả quan trọng. Nếu chỉ gọi document(...) mà không kiểm tra response hoặc không kiểm soát dữ liệu đầu vào, tài liệu có thể phản ánh một trường hợp không mong muốn.

### Request không có body

Một request GET thông thường chỉ gửi method, path và header:

```http
GET /api/products/42 HTTP/1.1
Accept: application/json
```

Không có payload để đưa vào request-body.adoc. Tùy template/version và cách operation được ghi lại, body snippet có thể rỗng hoặc không được sinh với nội dung đáng kể. Không nên tạo JSON body giả chỉ để làm cho trang tài liệu có đủ mọi file.

## 4. response-body.adoc: payload server trả về

Response body chứa dữ liệu mà client nhận sau khi request được xử lý. Ví dụ:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true
}
```

Snippet giúp người đọc biết server trả dữ liệu ở dạng nào và có payload mẫu để thử nghiệm. Với endpoint trả danh sách, body có thể là JSON array hoặc object bao bọc:

```json
{
  "content": [
    {"id": 42, "name": "Mechanical Keyboard"},
    {"id": 43, "name": "Ergonomic Mouse"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
```

Response lỗi cũng có thể là một phần hợp đồng API:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Product 999 does not exist"
}
```

Tạo operation riêng cho response thành công và lỗi nếu client cần biết cả hai trường hợp. Đừng gộp các kết quả HTTP khác nhau vào một operation ID rồi để snippet cuối cùng ghi đè lẫn nhau.

### Response không có body

Một số response đúng chuẩn không trả payload:

```http
HTTP/1.1 204 No Content
```

Trong tình huống này, response-body.adoc không có dữ liệu để hiển thị hoặc có thể không được tạo theo cấu hình/version. http-response.adoc vẫn thể hiện status và header. Tài liệu nên nói rõ endpoint không trả body, thay vì tự thêm object rỗng khiến người đọc hiểu sai hợp đồng.

## 5. Ví dụ MockMvc tạo request-body và response-body

### 5.1. Controller minh họa

```java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return new ProductResponse(
            42L, request.name(), request.price()
        );
    }

    record CreateProductRequest(String name, BigDecimal price) {}
    record ProductResponse(long id, String name, BigDecimal price) {}
}
```

### 5.2. Dependency

Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.3. Test POST ghi cả request và response body

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/catalog")
class ProductBodyDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createProduct() throws Exception {
        mockMvc.perform(
                post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "name": "Mechanical Keyboard",
                          "price": 89.50
                        }
                        """)
            )
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
            .andDo(document("products-create"));
    }
}
```

Sau khi test chạy thành công, operation products-create có snippet HTTP cơ bản; hai file body tập trung payload nếu request/response có body:

```text
build/generated-snippets/
  catalog/
    products-create/
      http-request.adoc
      http-response.adoc
      request-body.adoc
      response-body.adoc
```

outputDir là thư mục gốc được đặt tường minh; products-create là operation ID và trở thành thư mục con. Cấu trúc chính xác cần căn cứ file thực tế sau khi test chạy vì một số template hoặc response không body có thể không tạo nội dung tương ứng.

### 5.4. Bổ sung descriptor cho JSON field

Nếu muốn giải thích và kiểm tra payload, mở rộng operation:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

document("products-create",
    requestFields(
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("price").description("Giá bán")
    ),
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm"),
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("price").description("Giá bán")
    )
)
```

REST Docs có thể sinh request-fields.adoc và response-fields.adoc ngoài hai body snippet. Bảng field có ý nghĩa khác với payload nguyên bản:

- Body snippet cho thấy dữ liệu ví dụ.
- Field descriptor cho biết từng field có ý nghĩa gì.
- Descriptor được kiểm tra với payload mà test ghi nhận; field mới chưa được mô tả có thể làm test thất bại.

Nếu field có thể vắng mặt hoặc chỉ xuất hiện trong một response variant, đánh dấu optional hoặc ignored có chủ đích theo API descriptor. Không đánh dấu ignored đại trà để che thay đổi hợp đồng ngoài dự kiến.

## 6. Định dạng body và Content-Type

Body snippet cần được đọc cùng Content-Type. Cùng một chuỗi byte có thể được hiểu khác nhau theo media type; tài liệu cần thể hiện chính xác định dạng endpoint nhận hoặc trả.

| Media type | Ví dụ payload | Điểm cần chú ý |
| --- | --- | --- |
| application/json | Object, array, scalar JSON | Dùng field descriptor phù hợp với JSON path |
| application/xml | XML document | Xác minh encoding, namespace và schema |
| text/plain | Văn bản thuần | Không có JSON field descriptor |
| application/x-www-form-urlencoded | Form key/value | Phân biệt request parameter với payload JSON |
| multipart/form-data | Nhiều part, có thể kèm file | Mô tả từng part; tránh in file nhị phân lớn |
| application/octet-stream | Byte stream | Thường không nên đưa toàn bộ byte vào tài liệu |

### JSON và pretty print

Có thể dùng preprocessRequest(prettyPrint()) và preprocessResponse(prettyPrint()) để định dạng body trong snippet:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

document("products-create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint())
)
```

Preprocessor tác động nội dung được ghi vào tài liệu. Nó không thay đổi request mà test gửi hoặc response mà ứng dụng trả. Nếu test cần chứng minh byte-for-byte payload hoặc chữ ký số, không dùng snippet đã pretty print làm bằng chứng về byte gốc.

### XML, text và multipart

Với XML hoặc text, body snippet trình bày nội dung theo template tương ứng. Đảm bảo test gửi Content-Type đúng và response trả Content-Type đúng. Không dùng requestFields/responseFields dành cho JSON một cách máy móc nếu payload không phải cấu trúc JSON mà descriptor mong đợi.

Với multipart, mỗi part có thể chứa metadata JSON và một file. Dùng request-part descriptor để mô tả tên part, content type và metadata; chỉ đưa file mẫu nhỏ, không nhạy cảm nếu cần minh họa. Đừng đưa dữ liệu nhị phân lớn hoặc file thực của khách hàng vào tài liệu.

## 7. Làm đẹp, lọc và bảo vệ body snippet

Body snippet được lấy từ operation; dữ liệu kiểm thử vì thế có thể xuất hiện trong artifact. Trước khi publish, kiểm tra:

- Token, mật khẩu, cookie, API key hoặc thông tin xác thực trong payload.
- Email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân thật.
- ID nội bộ, URL dịch vụ không công khai hoặc dữ liệu production.
- Nội dung lớn/nhị phân khiến tài liệu khó đọc.
- Body có được pretty print hoặc redact nhất quán hay không.

Spring REST Docs hỗ trợ operation preprocessor để định dạng hoặc thay thế nội dung trước khi ghi snippet. Ví dụ pretty print ở mục trước. Khi cần che field nhạy cảm, chọn preprocessor phù hợp phiên bản REST Docs để thay giá trị trước khi lưu. Cách đơn giản nhất thường là dùng fixture giả dành riêng cho test.

Pretty print và redact thay đổi biểu diễn tài liệu; chúng không phải assertion bảo mật. Test vẫn phải kiểm tra ứng dụng không trả nhầm secret trong response nếu đó là yêu cầu bảo mật.

## 8. Include body snippet vào Asciidoctor

Trong src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Tạo sản phẩm

=== Request payload
include::{snippets}/catalog/products-create/request-body.adoc[]

=== Response payload
include::{snippets}/catalog/products-create/response-body.adoc[]

=== Request fields
include::{snippets}/catalog/products-create/request-fields.adoc[]

=== Response fields
include::{snippets}/catalog/products-create/response-fields.adoc[]
```

Attribute {snippets} phải trỏ tới thư mục gốc snippet (ví dụ build/generated-snippets), không phải trực tiếp vào thư mục operation. Đường dẫn include phía sau phải khớp outputDir, thư mục phân nhóm và operation ID. Nếu operation không có body hoặc không khai báo field descriptor, không include file không được sinh ra.

Với Markdown, dùng công cụ ghép nội dung phù hợp và kiểm tra phần mở rộng template (.md thay vì .adoc nếu đã cấu hình Markdown templates). Cú pháp include của Asciidoctor không tự động hoạt động trong Markdown phổ thông.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| request-body.adoc là toàn bộ HTTP request | Nó chỉ chứa payload; method/path/header nằm trong HTTP message snippet. |
| response-body.adoc giải thích schema JSON | Nó hiển thị payload; bảng field cần responseFields(...). |
| Mọi operation đều có cả hai body snippet có nội dung | Request/response không có body thì snippet có thể rỗng hoặc không có nội dung đáng kể. |
| Pretty print thay đổi response ứng dụng | Nó định dạng bản ghi tài liệu, không thay đổi response runtime. |
| Content-Type không quan trọng nếu body là JSON | Content-Type là metadata hợp đồng và ảnh hưởng cách server/client xử lý payload. |
| 204 nên có JSON object rỗng để tài liệu thống nhất | 204 No Content không có body; tài liệu phải phản ánh đúng hợp đồng. |
| Có body snippet nghĩa là schema đã được kiểm tra đầy đủ | Muốn kiểm tra field cần descriptor; muốn kiểm tra hành vi cần assertion. |

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| request-body.adoc rỗng | Request không gửi body hoặc body chưa được cấu hình đúng. | Kiểm tra content, Content-Type và request thực tế. |
| response-body.adoc không có nội dung | Response không có body, ví dụ 204, hoặc operation dừng trước document. | Kiểm tra response status/body và test report. |
| JSON hiển thị trên một dòng khó đọc | Chưa dùng pretty print hoặc template không format body. | Dùng preprocessor prettyPrint nếu phù hợp. |
| request-fields.adoc thất bại | Payload có field chưa được mô tả hoặc descriptor path sai. | Cập nhật field descriptor; kiểm tra nested path/array. |
| Body snippet chứa token hoặc dữ liệu thật | Test dùng fixture không an toàn. | Thay bằng fixture giả hoặc redact trước khi ghi. |
| Multipart snippet quá lớn | File test lớn hoặc body nhị phân được ghi nguyên dạng. | Dùng file nhỏ giả và part descriptor. |
| Asciidoctor không tìm thấy body file | Sai outputDir/operation ID hoặc operation không tạo snippet đó. | Kiểm tra cây thư mục sau test và include path. |
| Snippet hiển thị sai định dạng | Content-Type không đúng hoặc template/preprocessor không phù hợp. | Đối chiếu header và body test thực sự gửi/nhận. |

## 11. Bài thực hành

Tạo API Catalog với hai endpoint:

1. POST /api/products: nhận JSON name, price; trả 201 Created và JSON chứa id, name, price.
2. GET /api/products/{id}: trả JSON chi tiết sản phẩm.

Thực hiện:

1. Viết MockMvc test POST để tạo request-body.adoc và response-body.adoc.
2. Thêm requestFields(...) và responseFields(...); so sánh body snippet với bảng field descriptor.
3. Pretty print JSON request/response và quan sát khác biệt trong snippet.
4. Tạo trường hợp 204 No Content hoặc response lỗi; kiểm tra body snippet phản ánh đúng payload vắng mặt/hiện diện.
5. Tạo operation upload multipart với file giả nhỏ; dùng part descriptor và không đưa file nhị phân lớn vào tài liệu.
6. Include body và field snippets trong Asciidoctor, chạy clean test và dựng tài liệu.
7. Rà soát output để chắc chắn không chứa credential hoặc dữ liệu thật.

**Tiêu chí hoàn thành:** phân biệt body snippet với HTTP message và field descriptor; giải thích khi nào body snippet có dữ liệu; ghi đúng JSON/XML/text/multipart theo Content-Type; định dạng và bảo vệ payload trước khi publish; ghép đúng snippet trong tài liệu.

## 12. Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
