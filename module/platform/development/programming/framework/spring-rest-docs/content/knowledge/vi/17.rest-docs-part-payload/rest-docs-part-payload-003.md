# partBody và dữ liệu thô của part trong Spring REST Docs

## 1. Khi nào cần document nguyên body của một part?

Multipart request cho phép client gửi nhiều phần nội dung trong cùng một HTTP request. Ví dụ API nhập dữ liệu nhận một part `manifest` dạng JSON, một part `signature` dạng văn bản và một part `file` chứa dữ liệu nhị phân:

```http
POST /api/imports HTTP/1.1
Content-Type: multipart/form-data; boundary=----ImportBoundary

------ImportBoundary
Content-Disposition: form-data; name="manifest"
Content-Type: application/json

{"source":"warehouse","version":2,"items":[{"sku":"A-10","quantity":5}]}
------ImportBoundary
Content-Disposition: form-data; name="signature"
Content-Type: text/plain; charset=UTF-8

approved-by=ops;batch=2026-11
------ImportBoundary
Content-Disposition: form-data; name="file"; filename="inventory.csv"
Content-Type: text/csv

sku,quantity
A-10,5
------ImportBoundary--
```

Trong tài liệu API, ta có thể cần ba mức mô tả:

- Tên và mục đích của từng part: `requestParts(...)`.
- Cấu trúc field của một part JSON: `requestPartFields("manifest", ...)`.
- Nội dung body của part như một khối nguyên vẹn: `requestPartBody("manifest")`.

Người tích hợp có thể cần nhìn thấy nguyên JSON manifest hoặc chuỗi chữ ký đúng định dạng để tạo request tương thích. Bảng field không thể hiện được toàn bộ ví dụ payload; `requestPartBody(...)` tạo snippet body riêng cho part đã chọn.

**Spring REST Docs** sinh snippet từ kiểm thử HTTP. Trong module **SPRING_REST_DOCS**, kỹ thuật này áp dụng cùng MockMvc, WebTestClient hoặc REST Assured để tài liệu multipart có thể kiểm chứng và được ghép vào Asciidoctor/Markdown cũng như build/CI. Bài thuộc chương **Part payload**, tập trung vào `requestPartBody(...)` và dữ liệu thô của một part.

Sau bài học, bạn có thể:

1. Hiểu `requestPartBody(partName)` document nội dung body của một part cụ thể.
2. Phân biệt snippet body thô với `requestPartFields(...)` và `requestParts(...)`.
3. Viết MockMvc test multipart để sinh snippet cho JSON, text hoặc XML part.
4. Xác định trường hợp nào body snippet phù hợp và khi nào nên mô tả metadata thay vì dump nội dung nhị phân.
5. Đưa snippet của part vào tài liệu và kiểm thử trong CI.

## 2. Ba mức mô tả của multipart request

Giả sử request gồm `manifest`, `signature` và `file`:

| Mức mô tả | API Spring REST Docs | Nội dung được thể hiện |
| --- | --- | --- |
| Part nào có mặt? | `requestParts(...)` | Tên và mô tả part |
| Body part có schema field nào? | `requestPartFields("manifest", ...)` | Các field và đường dẫn trong payload JSON |
| Body part chứa nội dung gì? | `requestPartBody("manifest")` | Nội dung body của part như snippet độc lập |

Ví dụ kết hợp:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

document("inventory-import",
    requestParts(
        partWithName("manifest").description("Manifest JSON của lô nhập"),
        partWithName("signature").description("Chữ ký xác nhận của bộ phận vận hành"),
        partWithName("file").description("File CSV chứa dữ liệu hàng hóa")
    ),
    requestPartFields("manifest",
        fieldWithPath("source").description("Nguồn dữ liệu"),
        fieldWithPath("version").description("Phiên bản schema"),
        fieldWithPath("items").description("Danh sách mặt hàng")
    ),
    requestPartBody("manifest"),
    requestPartBody("signature")
);
```

Ba nhóm snippet bổ sung cho nhau. `requestParts(...)` mô tả part, `requestPartFields(...)` giải thích schema JSON, còn `requestPartBody(...)` cho người đọc thấy payload mẫu đầy đủ của từng part được chọn. Không cần chọn duy nhất một API nếu tài liệu thực sự cần cả ba góc nhìn.

## 3. Cú pháp requestPartBody(...)

`requestPartBody(...)` thuộc `org.springframework.restdocs.payload.PayloadDocumentation` và nhận tên part cần document:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("manifest")
```

Tên `manifest` phải khớp với tên part trong multipart request. Ví dụ controller khai báo `@RequestPart("manifest")`, request builder tạo part tên `manifest` và snippet cũng dùng cùng tên đó.

Snippet body riêng biệt giúp thể hiện payload như một tài liệu mẫu. Theo quy ước snippet mặc định, file được tạo cho part có tên `request-part-{partName}-body.adoc`, chẳng hạn:

```text
request-part-manifest-body.adoc
request-part-signature-body.adoc
```

Kiểm tra tên file thực tế trong thư mục snippet được sinh bởi phiên bản và cấu hình Spring REST Docs của dự án trước khi viết đường dẫn include cố định.

### 3.1. requestPartBody không phải requestBody

`requestBody()` mô tả body chính của HTTP request. Trong multipart, body chính là toàn bộ nội dung multipart có boundary và nhiều part. `requestPartBody("manifest")` chọn body của riêng part `manifest`, không document toàn bộ multipart envelope.

### 3.2. requestPartBody không phải requestPartFields

Nếu JSON part có cấu trúc:

```json
{
  "source": "warehouse",
  "version": 2,
  "items": [
    {"sku": "A-10", "quantity": 5}
  ]
}
```

`requestPartBody("manifest")` cho người đọc xem payload JSON mẫu. `requestPartFields("manifest", ...)` tạo bảng mô tả các đường dẫn như `source`, `version`, `items[].sku` và `items[].quantity`. Nếu client cần cả ví dụ hoàn chỉnh lẫn giải thích từng trường, hãy dùng cả hai.

### 3.3. Dữ liệu thô không đồng nghĩa byte-for-byte

Tên API nhấn mạnh body của part, nhưng snippet tài liệu không nên được xem là bản dump nhị phân có thể dùng để khôi phục mọi byte gốc. Spring REST Docs xử lý payload theo cơ chế snippet và content type. Với JSON/XML/text, đầu ra phù hợp để đọc như nội dung mẫu; với dữ liệu nhị phân, việc biểu diễn thành văn bản có thể vô nghĩa hoặc không phù hợp. Hãy dùng snippet mô tả part và tài liệu riêng cho định dạng file khi cần.

## 4. Ví dụ: document JSON manifest bằng requestPartBody

### 4.1. Controller minh họa

Controller nhận manifest dạng chuỗi JSON để ví dụ tập trung vào body của part:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ImportController {

    @PostMapping(
            path = "/api/imports",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ImportReceipt importData(
            @RequestPart("manifest") String manifest,
            @RequestPart("signature") String signature) {

        return new ImportReceipt("IMP-2026-001", manifest.length(), signature);
    }
}

record ImportReceipt(String importId, int manifestLength, String signature) {}
```

Trong ứng dụng thực, part JSON có thể được chuyển đổi thành DTO bằng `@RequestPart("manifest") ImportManifest`. Dùng `String` trong ví dụ giúp làm rõ body mà không phụ thuộc vào logic mapping schema.

### 4.2. Tạo multipart part trong MockMvc

`MockMultipartFile` cho phép thiết lập tên part, filename, content type và bytes của body:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile manifest = new MockMultipartFile(
        "manifest",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "source": "warehouse",
          "version": 2,
          "items": [
            {"sku": "A-10", "quantity": 5}
          ]
        }
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile signature = new MockMultipartFile(
        "signature",
        "",
        MediaType.TEXT_PLAIN_VALUE,
        "approved-by=ops;batch=2026-11".getBytes(StandardCharsets.UTF_8));
```

`filename` được để trống vì hai part trên là text payload, không phải file upload. Content-Type phải phù hợp với định dạng của từng part.

### 4.3. Test document raw part body

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ImportPartBodyDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ImportController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsRawManifestAndSignatureBodies() throws Exception {
        MockMultipartFile manifest = new MockMultipartFile(
                "manifest",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "source": "warehouse",
                  "version": 2,
                  "items": [
                    {"sku": "A-10", "quantity": 5}
                  ]
                }
                """.getBytes(StandardCharsets.UTF_8));

        MockMultipartFile signature = new MockMultipartFile(
                "signature",
                "",
                MediaType.TEXT_PLAIN_VALUE,
                "approved-by=ops;batch=2026-11".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/imports")
                        .file(manifest)
                        .file(signature))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.importId").value("IMP-2026-001"))
                .andExpect(jsonPath("$.signature").value("approved-by=ops;batch=2026-11"))
                .andDo(document("inventory-import",
                        requestParts(
                                partWithName("manifest")
                                        .description("Manifest JSON của lô nhập"),
                                partWithName("signature")
                                        .description("Chữ ký văn bản của bộ phận vận hành")
                        ),
                        requestPartBody("manifest"),
                        requestPartBody("signature")
                ));
    }
}
```

Trong test:

1. Mỗi `MockMultipartFile` tạo một part độc lập.
2. `requestParts(...)` document tên và ý nghĩa hai part.
3. `requestPartBody("manifest")` sinh snippet chứa body manifest; `requestPartBody("signature")` sinh snippet body chữ ký.
4. Assertion response xác nhận request đã được controller nhận và xử lý theo ví dụ. Nếu cần chứng minh toàn bộ manifest được parse đúng, hãy thêm assertion cho các field tương ứng.

## 5. Dùng requestPartBody cho JSON, XML và text

### 5.1. JSON part

JSON thường là lựa chọn phù hợp khi body có cấu trúc và người đọc cần thấy nguyên payload mẫu:

```java
requestPartBody("metadata")
```

Đặt Content-Type của part là `application/json`. Nếu muốn thêm bảng định nghĩa field:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên đối tượng"),
    fieldWithPath("enabled").description("Trạng thái kích hoạt")
)
```

Ví dụ JSON cho biết hình dạng tổng thể; bảng field giải thích từng trường.

### 5.2. XML part

Một API tích hợp hệ thống cũ có thể nhận XML:

```xml
<shipment>
  <reference>SHIP-100</reference>
  <warehouse>HCM-01</warehouse>
  <quantity>5</quantity>
</shipment>
```

Part nên có Content-Type phù hợp, chẳng hạn `application/xml`. Khi document bằng `requestPartBody("shipment")`, snippet thể hiện XML mẫu để người tích hợp tái tạo payload. Nếu contract yêu cầu schema XSD hoặc namespace cụ thể, nên công bố schema và giải thích trong tài liệu endpoint.

### 5.3. Text part

Ví dụ text:

```text
approved-by=ops;batch=2026-11
```

Part `text/plain` thường không cần JSON field descriptors. `requestPartBody("signature")` phù hợp để document chuỗi đầy đủ, delimiter và quy ước encoding. Nếu chuỗi chứa bí mật, token hoặc dữ liệu cá nhân, không dùng dữ liệu thật trong snippet; thay bằng fixture giả lập an toàn.

## 6. Khi nào không nên dump body part?

### 6.1. File nhị phân

Với part file:

```http
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

...binary bytes...
```

Không nên dựa vào snippet text của `requestPartBody("file")` để trình bày nội dung PDF, ảnh, ZIP hoặc file nhị phân khác. Thay vào đó:

- Dùng `requestParts(...)` để mô tả part.
- Document tên file, media type, quy tắc kích thước và định dạng ở phần mô tả phù hợp.
- Nếu cần cung cấp file mẫu, phân phối fixture/documentation asset qua quy trình riêng của dự án.

### 6.2. Payload quá lớn

Không nên đưa hàng nghìn dòng JSON hoặc XML vào trang API chỉ để chứng minh format. Có thể dùng `requestPartBody(...)` cho một mẫu đại diện nhỏ, rồi mô tả giới hạn kích thước, phân trang hoặc schema riêng. Nếu payload có nhiều cấu trúc, cân nhắc snippet field và file schema liên kết.

### 6.3. Payload chứa dữ liệu nhạy cảm

Snippet được xuất bản có thể được đọc bởi người ngoài nhóm phát triển. Dùng dữ liệu giả, không đưa token truy cập, mật khẩu, chữ ký thật hoặc dữ liệu người dùng thật vào payload test. `requestPartBody(...)` không tự che dữ liệu.

## 7. Kết hợp part body với các loại snippet khác

Một tài liệu multipart hoàn chỉnh có thể có:

| Snippet | Mục đích |
| --- | --- |
| `request-parts.adoc` | Tên và mô tả các part |
| `request-part-manifest-body.adoc` | Body mẫu của manifest |
| `request-part-signature-body.adoc` | Body mẫu của signature |
| `request-part-manifest-fields.adoc` | Bảng field của manifest nếu dùng `requestPartFields(...)` |
| `http-request.adoc` | Request HTTP tổng thể |
| `http-response.adoc` | Response HTTP |
| `response-fields.adoc` | Field của response JSON nếu được document |

Tên snippet cụ thể do Spring REST Docs và template format tạo ra. Sau khi chạy test, hãy kiểm tra file output thực tế trong `generated-snippets` rồi dùng đúng đường dẫn trong trang tài liệu.

Trong Asciidoctor:

```asciidoc
= Import API

== Nhập lô hàng

=== Request parts

include::{snippets}/inventory-import/request-parts.adoc[]

=== Manifest body

include::{snippets}/inventory-import/request-part-manifest-body.adoc[]

=== Signature body

include::{snippets}/inventory-import/request-part-signature-body.adoc[]

=== HTTP request

include::{snippets}/inventory-import/http-request.adoc[]
```

Biến `{snippets}` cần trỏ đến output folder. Nếu dùng Markdown, chọn template Markdown và dùng công cụ ghép snippet tương ứng; Markdown cơ bản không có directive `include` chuẩn như Asciidoctor.

## 8. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy part để tạo body snippet | Tên trong `requestPartBody("manifest")` không khớp request | Đồng bộ tên part ở MockMultipartFile, controller và descriptor |
| Có snippet request parts nhưng không có snippet body | Chỉ khai báo `requestParts(...)` | Thêm `requestPartBody(partName)` cho part cần ví dụ body |
| Dùng `requestPartFields(...)` nhưng cần một ví dụ JSON đầy đủ | Bảng field không thể hiện toàn bộ payload mẫu | Bổ sung `requestPartBody(...)` |
| Snippet body chứa nội dung không đọc được | Đang document part nhị phân | Chỉ document metadata của file, không dump byte vào trang |
| Part JSON bị parse lỗi trước khi tạo snippet | Content-Type hoặc JSON body không phù hợp converter/controller | Gửi part `application/json` đúng định dạng và kiểm tra binding |
| Body snippet không phản ánh giá trị mà client cần gửi | Fixture test khác với contract hoặc mô tả đã lỗi thời | Dùng fixture đại diện cho contract, assertion và document chung một request |
| Include file báo không tồn tại | Đoán sai tên snippet hoặc identifier | Đọc output folder thực tế và sửa đường dẫn include |
| Snippet lộ dữ liệu thật | Test fixture dùng token hoặc dữ liệu người dùng | Thay bằng dữ liệu giả trước khi xuất bản |

## 9. WebTestClient và REST Assured

`requestPartBody(...)` là descriptor snippet của payload; tích hợp test client chịu trách nhiệm xây multipart request và gắn `document(...)`.

### 9.1. WebTestClient

WebTestClient có thể tạo multipart body bằng `MultipartBodyBuilder`. Ví dụ minh họa cách gửi part:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("manifest", """
        {"source":"warehouse","version":2}
        """)
        .contentType(MediaType.APPLICATION_JSON);
builder.part("signature", "approved-by=ops;batch=2026-11")
        .contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
        .uri("/api/imports")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isOk();
```

Trong bài test được cấu hình REST Docs, gắn snippet `requestPartBody("manifest")` và `requestPartBody("signature")` vào lời gọi `document(...)` theo API tích hợp WebTestClient. Ví dụ trên minh họa phần tạo request; `webTestClient` cần được cấu hình với Spring REST Docs trước đó.

### 9.2. REST Assured

REST Assured hỗ trợ multipart qua `multiPart(...)`:

```java
given()
        .filter(documentationFilter)
        .multiPart("manifest",
                "{\"source\":\"warehouse\",\"version\":2}",
                "application/json")
        .multiPart("signature", "approved-by=ops;batch=2026-11", "text/plain")
        .when()
        .post("/api/imports")
        .then()
        .statusCode(200);
```

`documentationFilter` cần được cấu hình với Spring REST Docs và descriptor tương ứng có `requestPartBody(...)`. Cần xác minh overload multipart và cách gắn snippet theo phiên bản REST Assured tích hợp trong dự án.

## 10. Build và CI

Quy trình cơ bản:

1. Khai báo tích hợp Spring REST Docs phù hợp với test client: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient` hoặc `spring-restdocs-restassured`.
2. Tạo multipart test có payload part đại diện, định nghĩa Content-Type cho mỗi part.
3. Gắn `requestParts(...)` và `requestPartBody(...)`; bổ sung `requestPartFields(...)` nếu cần schema field.
4. Cấu hình thư mục snippet như `build/generated-snippets` (Gradle) hoặc `target/generated-snippets` (Maven) làm output.
5. Cho task Asciidoctor phụ thuộc task test; include đúng snippet body đã được sinh.
6. Chạy test và render tài liệu trong CI để phát hiện part bị đổi tên, body thay đổi hoặc snippet/include bị thiếu.

Ví dụ lệnh Gradle sau khi dự án đã cấu hình task:

```bash
./gradlew test asciidoctor
```

Khi body mẫu thay đổi, snippet được sinh lại từ test. Nếu contract thay đổi, cần cập nhật fixture, assertion và phần mô tả để bảo đảm tài liệu phản ánh request được hỗ trợ.

## 11. Bài tập thực hành

Thiết kế endpoint `POST /api/batches` nhận ba part:

- `metadata`: JSON gồm `batchId`, `createdBy`, `labels`.
- `checksum`: text/plain chứa chuỗi SHA-256 hex.
- `archive`: file ZIP nhị phân.

Yêu cầu:

1. Tạo controller nhận `@RequestPart("metadata")`, `@RequestPart("checksum")` và `@RequestPart("archive")`.
2. Viết MockMvc test tạo ba `MockMultipartFile` với Content-Type tương ứng.
3. Dùng `requestParts(...)` mô tả cả ba part.
4. Dùng `requestPartBody("metadata")` và `requestPartBody("checksum")` để sinh snippet body; không dump nội dung ZIP bằng snippet text.
5. Nếu cần giải thích cấu trúc metadata, thêm `requestPartFields("metadata", ...)`.
6. Assert response hoặc service invocation nhận đúng batchId và checksum; không dùng checksum/dữ liệu bí mật thật trong fixture.
7. Include snippet body vào Asciidoctor và chạy test cùng render tài liệu trong CI.

**Tiêu chí hoàn thành:** Người đọc thấy được ví dụ body của metadata và checksum, hiểu rõ part archive là file nhị phân, tên part và Content-Type khớp với request thực tế, snippet được sinh từ test.

## 12. Ghi nhớ

`requestPartBody(partName)` document body của một part được chọn như một snippet payload độc lập. Dùng `requestParts(...)` để giới thiệu tên part và `requestPartFields(...)` để giải thích schema field của JSON/object payload; kết hợp cả ba khi tài liệu cần mô tả tên part, body mẫu và cấu trúc dữ liệu. Với part nhị phân, ưu tiên mô tả tên, filename, Content-Type và ràng buộc file thay vì dump byte vào tài liệu. Kết nối test multipart, snippet Asciidoctor/Markdown và CI để ví dụ part body luôn xuất phát từ request kiểm thử.

### Tài liệu tham khảo

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
