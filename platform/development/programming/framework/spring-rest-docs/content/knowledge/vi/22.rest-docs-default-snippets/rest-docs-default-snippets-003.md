# httpie-request và các snippet request tương ứng

## 1. Vai trò của HTTPie snippet

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP tạo ra tài liệu có thể kiểm chứng từ request và response mà test thực hiện. Bài này tập trung vào snippet HTTPie và những snippet request đi kèm: HTTP message, body, path/query parameter, header, JSON field và multipart part.

Các snippet request phục vụ những nhu cầu khác nhau:

| Snippet | Nội dung | Mục đích |
| --- | --- | --- |
| httpie-request.adoc | Lệnh HTTPie tái hiện request | Chạy thử API bằng HTTPie |
| curl-request.adoc | Lệnh cURL tái hiện request | Chạy thử API bằng cURL |
| http-request.adoc | Thông điệp HTTP request | Rà soát method, path, header và body |
| request-body.adoc | Payload request | Xem dữ liệu gửi lên |
| path-parameters.adoc | Bảng path parameter | Giải thích biến trong URI template |
| request-parameters.adoc | Bảng request parameter | Giải thích query/form parameter được mô tả |
| request-headers.adoc | Bảng request header | Giải thích header có ý nghĩa gì |
| request-fields.adoc | Bảng field payload | Mô tả và kiểm tra cấu trúc JSON/form |
| request-parts.adoc | Bảng multipart part | Mô tả các phần trong multipart request |

Không phải tất cả file được tạo tự động cho mọi operation. HTTPie, cURL và HTTP message là các biểu diễn request mặc định thường gặp. Bảng parameter, header, field và multipart chỉ được tạo khi test khai báo descriptor phù hợp và client/module hỗ trợ API đó.

Ví dụ sử dụng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. WebTestClient và REST Assured có API tích hợp riêng; nguyên tắc operation ID và ghép snippet vẫn tương tự.

## 2. httpie-request.adoc: lệnh HTTPie sinh từ request

HTTPie là công cụ dòng lệnh để gửi HTTP request với cú pháp ngắn gọn. Spring REST Docs tạo httpie-request.adoc từ request đã ghi nhận, giúp người tích hợp sao chép lệnh và thử endpoint.

Ví dụ request GET:

```bash
http GET :8080/api/products/42 Accept:application/json
```

Ví dụ POST gửi JSON:

```bash
http POST :8080/api/products \
  Accept:application/json \
  name="Mechanical Keyboard" \
  price:=89.5
```

Trong cú pháp HTTPie:

- http là lệnh CLI.
- GET, POST, PATCH, PUT hoặc DELETE là HTTP method.
- :8080/api/products là shorthand URL sử dụng host mặc định và port chỉ định.
- Accept:application/json là header theo cú pháp Header:Value.
- name="Mechanical Keyboard" biểu diễn giá trị text trong JSON object.
- price:=89.5 biểu diễn giá trị JSON không phải chuỗi; := yêu cầu HTTPie parse giá trị theo kiểu JSON.

Lệnh thực tế REST Docs tạo phụ thuộc method, URL, header, body và cách request được xây dựng. Ví dụ trên minh họa cú pháp HTTPie; không phải mọi request body được tự động chuyển thành đúng các đối số JSON như ví dụ thủ công. Hãy đọc snippet đã sinh để biết chính xác lệnh của phiên bản REST Docs đang dùng.

### Khi nào dùng HTTPie?

HTTPie snippet hữu ích khi người đọc muốn thử endpoint từ terminal, gửi JSON/header với cú pháp dễ đọc, chia sẻ request tái hiện lỗi hoặc đối chiếu một request mẫu với http-request.adoc.

HTTPie snippet không phải bằng chứng test đã chạy chương trình HTTPie. Request gốc có thể được gửi bằng MockMvc, WebTestClient hoặc REST Assured; REST Docs tạo lệnh HTTPie để mô phỏng lại request đó.

## 3. So sánh HTTPie, cURL và HTTP message

Ba snippet thường mô tả cùng một request nhưng khác hình thức:

| Tiêu chí | httpie-request.adoc | curl-request.adoc | http-request.adoc |
| --- | --- | --- | --- |
| Hình thức | Lệnh HTTPie | Lệnh cURL | Thông điệp HTTP |
| Mục đích | Gửi request bằng HTTPie | Gửi request bằng cURL | Đọc cấu trúc giao thức |
| Header | Cú pháp HTTPie | Dùng -H | Hiển thị trực tiếp |
| Body JSON | Key/value hoặc dữ liệu đầu vào | -d/--data | Payload sau phần header |
| Chạy trực tiếp | Có, sau khi điều chỉnh URL/credential | Có, sau khi điều chỉnh URL/credential | Không phải lệnh terminal |

Ví dụ cùng request POST:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Mechanical Keyboard","price":89.5}
```

```bash
curl 'http://localhost:8080/api/products' \
  -i \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Mechanical Keyboard","price":89.5}'
```

```bash
http POST :8080/api/products \
  Content-Type:application/json \
  Accept:application/json \
  name="Mechanical Keyboard" \
  price:=89.5
```

Ví dụ minh họa cùng method, URL, header và dữ liệu JSON. Cách biểu diễn chính xác trong snippet có thể thay đổi theo phiên bản HTTPie/REST Docs và loại body mà client ghi nhận.

## 4. Các snippet request liên quan

### 4.1. http-request.adoc

Đây là request dưới dạng HTTP message, thường gồm method, request target, protocol, header và body. Nó giúp debug request mà không phụ thuộc cú pháp của một CLI cụ thể.

### 4.2. request-body.adoc

Snippet chứa payload request, thường là JSON, form data hoặc nội dung khác:

```json
{
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "tags": ["office", "accessory"]
}
```

Body thô giúp người đọc nhìn thấy dữ liệu mẫu nhưng không giải thích ý nghĩa từng field. Dùng requestFields(...) để tạo request-fields.adoc và kiểm tra cấu trúc payload.

### 4.3. path-parameters.adoc

Path parameter nằm trong URI template, ví dụ GET /api/products/{id}. Khi test gọi id = 42, request được mở rộng thành /api/products/42. Descriptor giữ lại ý nghĩa placeholder:

```java
pathParameters(
    parameterWithName("id")
        .description("Mã định danh sản phẩm")
)
```

Với MockMvc, nên dùng RestDocumentationRequestBuilders để giữ URI template cho việc trích xuất path parameter. Nếu builder không giữ template, REST Docs có thể không xác định được tên biến sau khi URI đã mở rộng.

### 4.4. request-parameters.adoc

Request parameter thường là query parameter hoặc form parameter được mô tả qua requestParameters(...) và API tương ứng của client.

Ví dụ:

```text
GET /api/products?category=keyboard&page=0
```

Descriptor:

```java
requestParameters(
    parameterWithName("category").description("Danh mục cần lọc"),
    parameterWithName("page").description("Số trang, bắt đầu từ 0")
)
```

Không nhầm query parameter với path parameter. Query nằm sau dấu ?, còn path parameter là placeholder trong URI template. Tên snippet và cách trích xuất cụ thể cần đối chiếu API của client/module đang dùng.

### 4.5. request-headers.adoc

Header là metadata gửi cùng request:

```text
Accept: application/json
Content-Type: application/json
If-Match: "v3"
```

Descriptor:

```java
requestHeaders(
    headerWithName("Accept")
        .description("Định dạng phản hồi mong muốn"),
    headerWithName("Content-Type")
        .description("Định dạng payload request")
)
```

Header có thể ảnh hưởng content negotiation, conditional request, cache, xác thực hoặc trace. Không phải mọi header nội bộ đều nên trở thành tài liệu công khai.

### 4.6. request-fields.adoc

Khi payload có cấu trúc, dùng requestFields(...) để mô tả field:

```java
requestFields(
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá bán"),
    fieldWithPath("tags").description("Danh sách nhãn")
)
```

Snippet sinh ra là bảng mô tả field, đồng thời hỗ trợ kiểm tra payload thực tế so với tài liệu. Nếu có field mới chưa được mô tả, test có thể thất bại. Với field lồng nhau, array hoặc field tùy chọn, dùng path descriptor phù hợp và đánh dấu optional/ignored có chủ đích.

### 4.7. Multipart request

Với multipart request, mỗi part có thể có tên, content type và payload riêng. Ví dụ endpoint upload:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Guide"}
------Boundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...binary content...
------Boundary--
```

REST Docs cung cấp descriptor về request part để mô tả các phần được gửi. Với multipart, body thô có thể phức tạp hoặc không phù hợp hiển thị toàn bộ byte file. Dùng request-part descriptor và part field API được client hỗ trợ; tránh đưa dữ liệu nhị phân lớn vào tài liệu.

## 5. Ví dụ MockMvc sinh HTTPie và snippet request

### Controller mẫu

```java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductResponse find(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String locale) {
        return new ProductResponse(id, "Bàn phím cơ", locale);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return new ProductResponse(42L, request.name(), "vi");
    }

    record CreateProductRequest(String name, BigDecimal price) {}
    record ProductResponse(long id, String name, String locale) {}
}
```

### Dependency

Gradle Groovy DSL:

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

### Test ghi operation

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.post;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.requestParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/catalog")
class ProductRequestDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findProduct() throws Exception {
        mockMvc.perform(
                get("/api/products/{id}", 42)
                    .queryParam("locale", "vi")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andDo(document("products-find",
                pathParameters(
                    parameterWithName("id").description("Mã sản phẩm")
                ),
                requestParameters(
                    parameterWithName("locale").description("Ngôn ngữ")
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Định dạng phản hồi mong muốn")
                )
            ));
    }

    @Test
    void createProduct() throws Exception {
        mockMvc.perform(
                post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Bàn phím cơ\",\"price\":89.5}")
            )
            .andExpect(status().isCreated())
            .andDo(document("products-create",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("Định dạng payload gửi lên")
                ),
                requestFields(
                    fieldWithPath("name").description("Tên sản phẩm"),
                    fieldWithPath("price").description("Giá bán")
                )
            ));
    }
}
```

Lớp test ghi hai operation riêng. products-find có path parameter, query parameter và request header; products-create có request header và JSON request fields. Với mỗi operation, REST Docs cũng tạo các snippet request cơ bản, bao gồm HTTPie và HTTP message theo template mặc định.

### Cấu trúc output

Với outputDir là build/generated-snippets/catalog, cấu trúc dự kiến:

```text
build/generated-snippets/
  catalog/
    products-find/
      http-request.adoc
      curl-request.adoc
      httpie-request.adoc
      request-body.adoc
      path-parameters.adoc
      request-parameters.adoc
      request-headers.adoc
    products-create/
      http-request.adoc
      curl-request.adoc
      httpie-request.adoc
      request-body.adoc
      request-headers.adoc
      request-fields.adoc
```

Đây là sơ đồ các snippet mong đợi theo operation và descriptor đã khai báo. Body snippet phụ thuộc request body có nội dung hay không; output thực tế còn phụ thuộc template format và phiên bản REST Docs.

## 6. Include snippet vào Asciidoctor

File src/docs/asciidoc/products.adoc có thể chọn các phần cần trình bày:

```asciidoc
= Products API
:toc: left

== Tìm sản phẩm

=== HTTP request
include::{snippets}/catalog/products-find/http-request.adoc[]

=== HTTPie
include::{snippets}/catalog/products-find/httpie-request.adoc[]

=== Path parameters
include::{snippets}/catalog/products-find/path-parameters.adoc[]

=== Query parameters
include::{snippets}/catalog/products-find/request-parameters.adoc[]

=== Request headers
include::{snippets}/catalog/products-find/request-headers.adoc[]

== Tạo sản phẩm

=== HTTPie
include::{snippets}/catalog/products-create/httpie-request.adoc[]

=== Request fields
include::{snippets}/catalog/products-create/request-fields.adoc[]
```

Attribute {snippets} phải trỏ tới thư mục gốc build/generated-snippets, không phải thư mục operation. Với Maven, thư mục mặc định thường là target/generated-snippets. Nếu test dùng outputDir riêng, điều chỉnh attribute theo đúng gốc đó.

Không nhất thiết include mọi snippet vào mọi trang. HTTPie phù hợp với hướng dẫn thực hành; HTTP message phù hợp với tài liệu giao thức; request fields và parameter table phù hợp để giải thích hợp đồng.

## 7. URI và credential trong HTTPie snippet

Khi test dùng RANDOM_PORT, snippet có thể chứa localhost và port được cấp động. Để tài liệu công khai dùng host phù hợp, cấu hình URI hiển thị của Spring REST Docs:

```java
@AutoConfigureRestDocs(
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
```

Cấu hình chỉ tác động nội dung snippet, không làm HTTPie/cURL trong test gửi request tới host public và không bật TLS cho embedded server.

Nếu HTTPie snippet chứa Authorization, cookie hoặc dữ liệu nhạy cảm, không dùng credential thật. Dùng token giả dành riêng cho test và redact header trước khi ghi tài liệu. HTTPie là lệnh có thể copy trực tiếp, vì vậy phải kiểm tra để không phát tán token production hoặc URL nội bộ.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| httpie-request chứng minh test dùng HTTPie | Test có thể dùng MockMvc/WebTestClient/REST Assured; HTTPie chỉ là cách biểu diễn request. |
| httpie-request và http-request giống nhau | Một file là lệnh CLI; file kia là HTTP message. |
| request-body mô tả ý nghĩa field | Nó hiển thị payload; bảng field cần requestFields(...). |
| Query parameter và path parameter là một loại | Query nằm sau dấu ?; path parameter là placeholder trong URI template. |
| Mọi operation có mọi snippet request | File phụ thuộc body, descriptor và module client. |
| Đổi uriHost làm client gọi host mới | URI snippet thay đổi; base URL client không đổi. |
| Có header trong request snippet nghĩa là đã giải thích header | Bảng mô tả cần requestHeaders(...). |

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có httpie-request.adoc | Operation chưa được ghi bằng document(...), test chưa chạy hoặc output ở folder khác. | Kiểm tra test report, operation ID và outputDir. |
| HTTPie command chứa host/port local | URI ghi nhận từ test server. | Cấu hình uriScheme, uriHost, uriPort. |
| Lệnh HTTPie không gửi JSON như mong đợi | Khác biệt giữa JSON body, form field và cú pháp HTTPie. | Kiểm tra http-request/request-body; điều chỉnh lệnh theo payload. |
| Thiếu request-parameters.adoc | Chưa khai báo descriptor hoặc client không trích xuất parameter đó. | Dùng API descriptor phù hợp và xác minh output. |
| Thiếu path-parameters.adoc | URI template không được giữ hoặc chưa khai báo pathParameters(...). | Dùng request builder REST Docs và khai báo descriptor. |
| request-fields báo field chưa mô tả | Payload có field mới chưa được descriptor bao phủ. | Cập nhật hợp đồng hoặc đánh dấu optional/ignored có chủ đích. |
| Snippet lộ Authorization | Test dùng credential thật hoặc chưa redact. | Dùng token giả và preprocess header. |
| Asciidoctor không tìm thấy HTTPie file | Sai attribute snippets, operation ID hoặc extension. | Đối chiếu output folder và include path. |

## 10. Bài thực hành

Với API Catalog, thực hiện:

1. Viết test GET /api/products/{id} có path parameter, query locale và header Accept; sinh HTTPie cùng các snippet request.
2. Viết test POST /api/products gửi JSON body; khai báo requestHeaders(...) và requestFields(...).
3. Mở httpie-request.adoc, http-request.adoc và request-body.adoc; đối chiếu method, URL, header và payload.
4. Include HTTPie, path parameter, request parameter, request header và request fields trong Asciidoctor.
5. Cấu hình URI public cho snippet nhưng giữ client test gọi local server; xác nhận hai địa chỉ phục vụ hai mục đích.
6. Thêm header xác thực giả, redact trước khi ghi snippet và kiểm tra không có credential trong output.
7. Chạy clean test asciidoctor; xác nhận tài liệu được sinh từ snippet mới.

**Tiêu chí hoàn thành:** giải thích HTTPie snippet khác HTTP message và cURL ra sao; biết snippet request nào là cơ bản và snippet nào cần descriptor; xác định đúng operation ID/output folder; mô tả request mà không làm lộ credential; ghép được nội dung cần thiết vào tài liệu.

## 11. Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Request Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parameters.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [HTTPie — Documentation](https://httpie.io/docs/cli)
