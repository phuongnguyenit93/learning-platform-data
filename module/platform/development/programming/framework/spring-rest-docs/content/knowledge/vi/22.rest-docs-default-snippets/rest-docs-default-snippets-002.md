# http-request, http-response và curl-request

## 1. Vai trò của ba snippet

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP tạo ra những mảnh tài liệu để mô tả hợp đồng REST API. Ba snippet thường được dùng cùng nhau là:

| Snippet | Câu hỏi mà nó trả lời | Người đọc thường dùng |
| --- | --- | --- |
| `http-request.adoc` | Client đã gửi request HTTP nào? | Developer, người debug API, người rà soát hợp đồng HTTP |
| `http-response.adoc` | Server đã trả response HTTP nào? | Developer, người tích hợp API, người kiểm tra status/header/body |
| `curl-request.adoc` | Có thể gửi lại request đó bằng lệnh cURL nào? | Người tích hợp API, người thử API từ terminal |

Ba file này mô tả cùng một operation được test ghi lại, nhưng ở ba hình thức khác nhau. `http-request` là thông điệp request ở mức HTTP; `http-response` là thông điệp response; `curl-request` là lệnh CLI tái hiện request. Chúng bổ sung cho nhau, không phải ba lần gọi API độc lập.

Spring REST Docs sinh các snippet này khi test thực hiện request và gọi cơ chế tài liệu hóa, thường là `document(...)`. Dependency được thêm vào project nhưng test không gọi `document(...)` thì không tự tạo snippet cho endpoint. Nội dung thực tế phụ thuộc method, URI, header, body, response và cấu hình URI/preprocessor tại operation.

Ví dụ trong bài dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Các nguyên tắc tương tự áp dụng cho WebTestClient và REST Assured, nhưng cú pháp test và package tích hợp thay đổi theo client.

## 2. http-request.adoc: thông điệp HTTP mà test gửi

`http-request.adoc` biểu diễn request theo dạng thông điệp HTTP. Nó giúp người đọc kiểm tra method, request target, HTTP version, header và body mà operation đã ghi nhận.

Ví dụ request GET:

```http
GET /api/products/42 HTTP/1.1
Accept: application/json
Host: api.example.com
```

Ví dụ request POST có body:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json
Host: api.example.com

{"name":"Mechanical Keyboard","price":89.5}
```

Những thành phần cần đọc:

- **Method**: GET, POST, PUT, PATCH, DELETE hoặc method khác mà test gửi.
- **Request target/path**: đường dẫn và query string. Path template có thể đã được mở rộng bằng giá trị tham số thực tế.
- **HTTP version**: phiên bản giao thức được ghi trong snippet.
- **Header**: ví dụ Accept, Content-Type, Authorization, If-Match hoặc header do ứng dụng bổ sung.
- **Body**: payload gửi lên server, nếu request có body.

Với request có query string, thông điệp có dạng:

```http
GET /api/products?category=keyboard&active=true HTTP/1.1
Accept: application/json
```

Snippet cho thấy request thực tế được tạo như thế nào. Nó không tự giải thích ý nghĩa nghiệp vụ của category, active hay header. Để tạo bảng mô tả parameter/header, hãy khai báo descriptor riêng như queryParameters(...) hoặc requestHeaders(...).

## 3. http-response.adoc: thông điệp HTTP server trả về

`http-response.adoc` biểu diễn response nhận được sau khi test gửi request. Nó thường gồm status line, response header và body.

Ví dụ response thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 47

{"id":42,"name":"Mechanical Keyboard"}
```

Ví dụ tạo tài nguyên:

```http
HTTP/1.1 201 Created
Location: /api/products/42
Content-Type: application/json

{"id":42,"name":"Mechanical Keyboard"}
```

Ví dụ không tìm thấy tài nguyên:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"title":"Not Found","status":404}
```

Khi đọc response, status code cho biết kết quả ở mức HTTP; header cung cấp metadata như Content-Type, Location, ETag, Cache-Control; body chứa dữ liệu hoặc thông tin lỗi nếu endpoint trả body.

Không phải response nào cũng có body. Endpoint trả 204 No Content có thể chỉ có status và header. `http-response.adoc` vẫn hữu ích vì ghi lại kết quả HTTP ngay cả khi không có JSON.

Snippet phản ánh response do test nhận được; nó không chứng minh mọi trường hợp response của endpoint đã được kiểm tra. Hãy viết assertion cho status/header/body quan trọng và tạo operation riêng cho success, not found, unauthorized hoặc validation failure.

## 4. curl-request.adoc: lệnh gửi lại request

`curl-request.adoc` chuyển request mà test ghi nhận thành lệnh cURL. Ví dụ:

```bash
curl 'https://api.example.com/api/products/42' \
  -i \
  -H 'Accept: application/json'
```

Với POST JSON:

```bash
curl 'https://api.example.com/api/products' \
  -i \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Mechanical Keyboard","price":89.5}'
```

| Thành phần cURL | Ý nghĩa |
| --- | --- |
| URL trong dấu nháy | Địa chỉ và path/query của request |
| -i | Hiển thị response headers cùng response body |
| -X POST | Chỉ định method khi cần thể hiện rõ method |
| -H 'Name: value' | Gửi một HTTP header |
| -d '...' | Gửi dữ liệu body |
| --data-binary | Gửi body theo dạng dữ liệu nhị phân |

REST Docs tạo lệnh này từ operation đã được ghi nhận. Người đọc có thể sao chép và chạy trong terminal, nhưng URL, token và dữ liệu test có thể cần thay theo môi trường của họ.

### cURL và HTTP request khác nhau thế nào?

`http-request.adoc` cho biết request dưới dạng thông điệp HTTP; `curl-request.adoc` trình bày cách thao tác để tạo request bằng công cụ cURL.

| So sánh | http-request.adoc | curl-request.adoc |
| --- | --- | --- |
| Hình thức | HTTP message | Dòng lệnh shell |
| Tập trung vào | Cấu trúc giao thức | Cách gửi lại request |
| Copy chạy trực tiếp? | Không phải lệnh shell | Có, sau khi điều chỉnh host/credential nếu cần |
| Dùng khi | Review/debug giao thức | Thử API hoặc chia sẻ ví dụ |

## 5. Ví dụ tạo cả ba snippet bằng MockMvc

### Dependency

Với ứng dụng Spring MVC dùng Gradle:

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

Controller minh họa:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductResponse find(@PathVariable long id) {
        return new ProductResponse(id, "Mechanical Keyboard");
    }

    record ProductResponse(long id, String name) {}
}
```

### Test và document(...)

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/products")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
            .andDo(document("products-find"));
    }
}
```

Khi test chạy thành công, các file tập trung của bài nằm dưới:

```text
build/generated-snippets/
  products/
    products-find/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

REST Docs còn có thể tạo snippet mặc định khác cho operation, chẳng hạn HTTPie và body. Bài này tập trung vào ba file nói trên.

`outputDir` là thư mục gốc; `products-find` là operation ID truyền vào `document(...)` và trở thành thư mục con. Nếu bỏ outputDir, Spring Boot dùng mặc định theo build tool trong cấu hình thông dụng. Nếu đổi operation ID, đường dẫn include ở tài liệu cũng phải đổi.

### Thêm descriptor cho parameter và field

Ba snippet HTTP cơ bản không tự tạo bảng giải thích tham số hoặc JSON field. Muốn tài liệu đầy đủ hơn, thêm descriptor:

```java
.andDo(document("products-find",
    pathParameters(
        parameterWithName("id")
            .description("Mã định danh sản phẩm")
    ),
    responseFields(
        fieldWithPath("id").description("ID sản phẩm"),
        fieldWithPath("name").description("Tên sản phẩm")
    )
));
```

Khi đó thư mục operation có thêm path-parameters.adoc và response-fields.adoc. Descriptor bổ sung cho request/response thô: snippet HTTP cho thấy dữ liệu truyền đi/nhận về, còn descriptor tạo bảng giải thích hợp đồng.

## 6. Ảnh hưởng của method, URI, header và body

Ba snippet được sinh từ operation đã ghi nhận, nên thay đổi request sẽ làm thay đổi nội dung tương ứng.

| Thay đổi trong test | http-request.adoc | http-response.adoc | curl-request.adoc |
| --- | --- | --- | --- |
| Đổi GET thành POST | Method thay đổi | Response có thể thay status/header/body | Lệnh cURL thể hiện POST |
| Thêm query parameter | Request target có query string | Response có thể khác do tham số | URL cURL có query |
| Thêm Accept | Header request thay đổi | Có thể đổi content negotiation/response | Thêm tùy chọn header |
| Thêm Content-Type | Header request thay đổi | Kết quả phụ thuộc cách server đọc body | Có header tương ứng |
| Thêm JSON body | Body request xuất hiện | Server có thể trả dữ liệu/status khác | Lệnh có phần gửi body |
| Cấu hình URI snippet | URI trong thông điệp thay đổi | URI/host có thể được chuẩn hóa | URL trong lệnh cURL thay đổi |

Đừng nhầm tác động trong snippet với tác động lên ứng dụng. Đổi uriHost trong cấu hình REST Docs chỉ thay URI được ghi lại; nó không khiến client gửi request tới host mới.

## 7. Chuẩn hóa URI và bảo vệ thông tin nhạy cảm

Khi dùng RANDOM_PORT, request thực tế có thể tới localhost với port động. Nếu đưa nguyên địa chỉ đó vào tài liệu công khai, ví dụ cURL không phù hợp cho người tích hợp API.

Có thể cấu hình URI hiển thị trong Spring REST Docs:

```java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/products",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
```

Snippet có thể thể hiện host public trong khi test vẫn gọi embedded server local. Các giá trị uriScheme, uriHost, uriPort không bật TLS và không thay đổi cổng server.

Nếu có header Authorization, cookie hoặc dữ liệu nhạy cảm, không đưa credential thật vào snippet. Dùng token giả dành riêng cho test và redact request header trước khi ghi tài liệu. cURL là lệnh có thể được copy trực tiếp, vì vậy phải kiểm tra kỹ để không phát tán token hoặc URL nội bộ.

## 8. Ghép ba snippet vào Asciidoctor

Đặt file nguồn, ví dụ src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Tìm sản phẩm

=== HTTP request
include::{snippets}/products/products-find/http-request.adoc[]

=== cURL
include::{snippets}/products/products-find/curl-request.adoc[]

=== HTTP response
include::{snippets}/products/products-find/http-response.adoc[]
```

Attribute {snippets} cần trỏ tới thư mục gốc build/generated-snippets. Đường dẫn phía sau attribute phải khớp outputDir và operation ID. Trong ví dụ này:

- Thư mục gốc: build/generated-snippets.
- Output riêng: products.
- Operation ID: products-find.
- Đường dẫn HTTP request: build/generated-snippets/products/products-find/http-request.adoc.

Không cần include mọi snippet vào mọi trang. Tài liệu hướng dẫn tích hợp có thể ưu tiên cURL và response fields; tài liệu debug nội bộ có thể hiển thị request/response nguyên dạng và header.

## 9. Gradle, Maven và CI

Ví dụ Gradle Groovy DSL:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

Chạy build sạch:

```bash
./gradlew clean test asciidoctor
```

Gradle cần biết test tạo snippet và Asciidoctor sử dụng thư mục đó. Khi test thất bại, bước dựng tài liệu không nên dùng snippet cũ để tạo artifact mới.

Với Maven, Asciidoctor Maven Plugin cần đọc target/generated-snippets; goal tài liệu phải chạy sau nhóm test sinh snippet. Nếu snippet đến từ Failsafe integration test, đặt bước biên soạn sau các test đó thay vì ở phase sớm hơn.

CI nên chạy test và dựng tài liệu trong cùng pipeline; chỉ upload/publish HTML sau khi cả hai thành công. Tránh bỏ qua test bằng -x test hoặc -DskipTests nếu snippet cần thiết chỉ do test tạo.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có http-request.adoc | Test chưa gọi document(...), test không chạy hoặc dừng trước bước tài liệu hóa. | Kiểm tra test report và vị trí andDo(document(...))/API tương ứng. |
| Request không có query string như mong đợi | Test tạo URI khác dự định hoặc truyền parameter sai. | Kiểm tra URI thực tế trong test và snippet sau khi chạy. |
| http-response.adoc có status khác thiết kế | Ứng dụng trả status khác hoặc test chưa kiểm tra status. | Thêm assertion status và sửa handler/contract hoặc tài liệu theo kết quả đúng. |
| cURL không chạy trên môi trường người đọc | Host/port local, token giả hoặc dữ liệu phụ thuộc môi trường. | Cấu hình URI public, hướng dẫn thay credential/dữ liệu. |
| cURL thiếu body | Request không gửi body hoặc body được tạo ở operation khác. | Kiểm tra method, content và operation được document. |
| Request có header nhạy cảm | Test ghi token/cookie thật. | Redact header hoặc dùng dữ liệu test giả. |
| Asciidoctor không tìm snippet | snippets sai, outputDir đổi hoặc operation ID không khớp. | Đối chiếu đường dẫn file thực tế với include. |
| Snippet hiển thị localhost/port động | Chưa chuẩn hóa URI trong REST Docs. | Cấu hình uriScheme, uriHost, uriPort hoặc preprocessor. |

## 11. Bài thực hành

Tạo hai operation cho API Catalog:

1. GET /api/products/{id}: kiểm tra status 200, gửi Accept, ghi http-request, http-response và curl-request.
2. POST /api/products: gửi JSON body với Content-Type, xác minh status 201 và Location; tạo lại ba snippet.
3. So sánh request GET và POST trong thư mục snippet. Chỉ ra method, header, URI và body khác nhau ở đâu.
4. Thêm path parameter và request/response field descriptor; xác định file bổ sung xuất hiện.
5. Cấu hình URI công khai trong REST Docs, chạy test trên local port và kiểm tra cURL snippet.
6. Include cả ba snippet trong Asciidoctor, chạy clean test asciidoctor, rồi xác nhận HTML chứa đúng request, response và lệnh cURL mới.

**Tiêu chí hoàn thành:** giải thích được sự khác nhau giữa ba snippet; đọc được method/path/header/body và status/response; biết cURL tái hiện request ra sao; sinh và include đúng file theo operation ID; tài liệu không lộ credential hoặc phụ thuộc port local.

## 12. Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
