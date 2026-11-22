# Đối chiếu URI, header và payload sau nâng cấp

## 1. Vì sao cần đối chiếu contract sau nâng cấp?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Nâng cấp**, việc nâng Spring Boot, Spring Framework, Spring REST Docs hoặc thư viện HTTP có thể làm thay đổi cách ứng dụng tạo request/response và cách snippet được sinh. Một thay đổi dependency tưởng như nhỏ vẫn có thể tác động đến URI, header, media type, serialization JSON hoặc kiểu dữ liệu trong payload.

Spring REST Docs tạo snippet từ HTTP exchange trong test. Vì vậy, bộ snippet đã được review và lưu trong version control có thể đóng vai trò baseline để đối chiếu contract trước và sau nâng cấp. Test xác minh hành vi hiện tại; diff snippet giúp reviewer nhận ra thay đổi trong tài liệu.

Mục tiêu của bài:

- Giữ baseline snippet trước khi nâng cấp.
- Chạy cùng documentation tests trên phiên bản mới.
- So sánh URI, request/response headers, status, media type và payload.
- Phân loại thay đổi tương thích và breaking change.
- Cập nhật descriptor và tài liệu sau khi xác nhận contract mới là chủ đích.
- Đưa diff vào review/CI để tránh thay đổi API ngoài ý muốn.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, MockMvc và Asciidoctor**. Quy trình tương tự với WebTestClient hoặc REST Assured.

## 2. Baseline snippet là gì?

Baseline là tập snippet được sinh từ phiên bản API đã được chấp thuận và commit cùng mã nguồn. Một operation có thể có:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    response-fields.adoc
    response-headers.adoc
```

Không phải file snippet nào cũng là contract có cùng mức quan trọng:

| Snippet | Nội dung cần đối chiếu |
| --- | --- |
| http-request.adoc | Method, URI, query string, request headers |
| http-response.adoc | HTTP status và response headers |
| response-body.adoc | JSON/XML payload thực tế |
| request-fields.adoc | Các field request được mô tả |
| response-fields.adoc | Các field response được mô tả |
| path-parameters.adoc / query-parameters.adoc | Tên và ý nghĩa parameter |
| links.adoc | Hypermedia relation và URI |

Baseline có giá trị khi được tạo từ fixture ổn định, không chứa timestamp, random ID, host máy developer hoặc dữ liệu cá nhân. Nếu snippet có giá trị biến thiên, hãy chuẩn hóa bằng fixture hoặc operation preprocessor trước khi lưu baseline.

## 3. Quy trình đối chiếu trước và sau nâng cấp

```text
Phiên bản hiện tại
      |
      v
Chạy documentation tests
      |
      v
Lưu/commit baseline snippets
      |
      v
Nâng dependency hoặc framework
      |
      v
Chạy lại cùng documentation tests
      |
      v
So sánh snippets
      |
      +---- Không đổi ----> Build docs và xác nhận
      |
      +---- Có thay đổi ---> Phân loại contract change
                                  |
                    +-------------+-------------+
                    |                           |
               Có chủ đích                 Ngoài ý muốn
                    |                           |
             Review và cập nhật          Sửa implementation/
             tài liệu, baseline           cấu hình nâng cấp
```

Giữ nguyên test data, operation ID, serializer config và môi trường giữa hai lần tạo snippet. Nếu thay đổi nhiều yếu tố cùng lúc, diff sẽ khó xác định nguyên nhân.

## 4. Đối chiếu URI và HTTP method

URI là phần quan trọng của API contract. Sau nâng cấp, kiểm tra:

- HTTP method có giữ nguyên không.
- Path có đổi prefix, segment, biến hoặc trailing slash không.
- Path parameter có giữ tên và vị trí không.
- Query parameter có đổi tên, default, encoding hoặc semantics không.
- URI template có còn giữ đúng biến và dấu hiệu templated không.
- Host/scheme trong snippet có đổi do cấu hình môi trường không.

Baseline:

```http
GET /api/v1/products/42?page=0&size=20 HTTP/1.1
Accept: application/json
```

Sau nâng cấp:

```http
GET /api/products/42?page=0&size=20 HTTP/1.1
Accept: application/json
```

Việc bỏ /v1 có thể là breaking change với client đang gọi URI cũ. Không chấp nhận diff chỉ vì route mới chạy được trong test; cần xác định versioning policy và khả năng tương thích.

### Test path parameter bằng MockMvc

Giữ URI template khi dựng request:

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/v1/products/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("products-find",
        pathParameters(
            parameterWithName("id")
                .description("Mã sản phẩm")
        )
    ));
```

Nếu framework upgrade làm thay đổi cách tạo URI hoặc encoding, test và snippet giúp phát hiện path parameter không còn khớp.

## 5. Đối chiếu request và response headers

| Header | Điều cần kiểm tra |
| --- | --- |
| Content-Type | Media type, charset và representation |
| Accept | Representation client yêu cầu |
| Location | URI resource được tạo |
| ETag | Validator và conditional request |
| Cache-Control | Chính sách cache |
| Vary | Header ảnh hưởng lựa chọn representation |
| Retry-After | Quy tắc chờ trước khi retry |
| WWW-Authenticate | Challenge xác thực |

Response baseline:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/products/42
```

Sau nâng cấp, response có thể chuyển sang application/hal+json hoặc Location đổi URI. Đây là thay đổi contract cần review vì client có thể deserialize hoặc điều hướng khác.

Descriptor header:

```java
responseHeaders(
    headerWithName("Content-Type")
        .description("Media type của response body"),
    headerWithName("Location")
        .description("URI của sản phẩm vừa tạo")
)
```

Descriptor bắt buộc giúp test thất bại nếu header không còn được trả. Nếu header thực sự optional, đánh dấu optional theo contract; không dùng optional để che regression.

## 6. Đối chiếu payload JSON

So sánh cả cấu trúc lẫn semantics:

- Field mới hoặc bị xóa.
- Field đổi tên hoặc đổi path.
- Kiểu dữ liệu đổi, ví dụ number thành string.
- Nullability hoặc optionality thay đổi.
- Giá trị mặc định hoặc format ngày giờ thay đổi.
- Nested object hoặc array đổi cấu trúc.
- Enum thêm/xóa giá trị.
- Quy tắc escaping, decimal precision hoặc timezone thay đổi.

Baseline:

```json
{
  "id": 42,
  "name": "Keyboard",
  "price": 89.5,
  "active": true
}
```

Response sau nâng cấp:

```json
{
  "id": "42",
  "name": "Keyboard",
  "price": 89.5,
  "active": true,
  "currency": "USD"
}
```

Ở đây id đổi từ number thành string là thay đổi kiểu có thể phá client; currency được thêm có thể tương thích với client tolerant nhưng vẫn cần cập nhật tài liệu và đánh giá schema consumer.

### Dùng responseFields để kiểm tra contract

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm"),
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá bán"),
    fieldWithPath("active").description("Sản phẩm đang kinh doanh")
)
```

Strict mode phát hiện field mới chưa được mô tả. Nếu payload sau nâng cấp có currency, test sẽ nhắc nhóm quyết định có đưa field vào public contract hay không. Khi đã chấp thuận, cập nhật descriptor và tài liệu cùng thay đổi code.

Không chuyển toàn bộ sang relaxedResponseFields(...) chỉ để test vượt qua. Relaxed mode phù hợp khi operation chỉ mô tả một phần payload, nhưng làm giảm khả năng phát hiện field drift.

## 7. Phân loại thay đổi tương thích và breaking

Không phải mọi diff đều là breaking change. Đánh giá theo semantics và cách client tiêu thụ API:

| Thay đổi | Rủi ro thường gặp | Hành động |
| --- | --- | --- |
| Thêm response field tùy chọn | Thường tương thích với client tolerant | Cập nhật descriptor/tài liệu và kiểm tra consumer |
| Xóa response field | Breaking nếu client đang dùng field | Giữ field, version API hoặc có kế hoạch deprecation |
| Đổi tên field | Breaking | Không đổi âm thầm; version hoặc hỗ trợ alias |
| Đổi kiểu field | Thường breaking | Giữ kiểu cũ hoặc version contract |
| Thêm request field optional | Có thể tương thích | Tài liệu hóa và xác định default |
| Thêm request field bắt buộc | Breaking với client cũ | Version hoặc cung cấp default/transition |
| Đổi HTTP status | Có thể đổi luồng client | Đánh giá semantics và retry/error handling |
| Đổi URI/method | Thường breaking | Duy trì route cũ trong giai đoạn chuyển tiếp |
| Thêm link relation | Thường tương thích nếu client bỏ qua relation lạ | Cập nhật links snippet và giải thích capability |
| Xóa link relation bắt buộc | Có thể breaking với client hypermedia | Duy trì relation hoặc version contract |
| Đổi Content-Type | Có thể breaking với deserializer | Kiểm tra Accept negotiation và client |

Khả năng tương thích phụ thuộc client. Thêm response field có thể an toàn với JSON client bỏ qua field lạ, nhưng không an toàn với client dùng strict schema validation. Đừng kết luận chỉ từ diff text; xét contract policy và consumer behavior.

## 8. Chuẩn hóa dữ liệu để diff có ý nghĩa

Snippet không ổn định làm diff nhiễu. Trước khi so sánh:

- Dùng fixture có ID, timestamp và email giả cố định.
- Dùng modifyUris() để chuẩn hóa host/scheme/port.
- Dùng replacePattern() để thay request ID hoặc giá trị ngẫu nhiên.
- Dùng removeHeaders() cho header nội bộ không thuộc contract.
- Dùng modifyHeaders() để giữ header nhưng thay giá trị môi trường.
- Không ghi token hoặc dữ liệu production vào fixture.

Ví dụ:

```java
document("products-find",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("req-[A-Za-z0-9-]+"),
            "REQUEST_ID"
        ),
        removeHeaders("X-Internal-Node", "Server")
    ),
    ...
)
```

Không chuẩn hóa giá trị là một phần contract cần kiểm tra. Nếu Location thay đổi là điều cần phát hiện, đừng thay toàn bộ header bằng placeholder trước khi so sánh.

## 9. So sánh snippet trong Git và CI

Workflow:

1. Commit baseline snippets đã review từ phiên bản hiện tại.
2. Nâng dependency/framework trên branch riêng.
3. Chạy clean test để sinh snippet mới từ cùng documentation tests.
4. So sánh thư mục snippet mới với baseline.
5. Review diff theo operation ID và phân loại thay đổi.
6. Cập nhật descriptor, Asciidoctor include và baseline nếu thay đổi được chấp thuận.
7. Build tài liệu và lưu artifact trong CI.

Ví dụ PowerShell để so sánh hai thư mục:

```powershell
$baseline = "docs-baseline/generated-snippets"
$current = "build/generated-snippets"

git diff --no-index -- "$baseline" "$current"
```

git diff --no-index trả exit code khác 0 khi có khác biệt; trong CI cần xử lý exit code như kết quả diff, không tự động xem mọi diff là build failure. Có thể lưu diff làm artifact để reviewer xem.

Nếu baseline được commit trong repository, lưu nó trong thư mục có chủ đích, ví dụ src/docs/snippets-baseline, và tạo snippet mới trong build directory. Không để task test ghi đè baseline trước khi reviewer xem diff.

## 10. Đồng bộ descriptor và Asciidoctor sau nâng cấp

Khi contract change được chấp thuận:

- Cập nhật descriptor để phản ánh payload/header/parameter/link mới.
- Cập nhật operation ID hoặc include path nếu operation được đổi tên có chủ đích.
- Thêm test cho response variant mới.
- Xem lại optional/ignored/relaxed để không làm mất strict validation.
- Cập nhật nội dung Asciidoctor nếu semantics thay đổi.
- Regenerate baseline snippets bằng đúng phiên bản đã được review.

Ví dụ include:

```asciidoc
== Tìm sản phẩm

=== Response headers
include::{snippets}/products-find/response-headers.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

Build cần bảo đảm test chạy trước Asciidoctor để snippet được tạo từ implementation hiện tại. Cấu hình task dependency và input/output directory phù hợp với project.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Diff có nhiều URI host khác nhau | Snippet phụ thuộc môi trường chạy | Chuẩn hóa URI bằng preprocessor |
| Payload diff ở timestamp/random ID | Fixture không ổn định | Dùng dữ liệu cố định hoặc replacePattern |
| Test không phát hiện field mới | Dùng relaxedResponseFields quá rộng | Giữ strict cho operation đại diện contract đầy đủ |
| Header biến mất sau nâng cấp | Framework/security config thay đổi | Xác minh header có còn thuộc contract và cập nhật implementation |
| Client lỗi sau khi đổi Content-Type | Representation không tương thích | Kiểm tra media type negotiation và client |
| Baseline bị ghi đè tự động | Test ghi snippet vào cùng thư mục baseline | Tách baseline khỏi generated output |
| Mọi diff bị coi là breaking | Không phân loại theo semantics | Review URI, status, header, payload và consumer impact |
| Asciidoctor include lỗi | Snippet đổi operation ID hoặc tên file | Đồng bộ include path với output thực tế |

## 12. Bài thực hành

Giả sử API Catalog có contract:

1. GET /api/v1/products/{id} trả id dạng number, name, price và Content-Type application/json.
2. POST /api/v1/products trả 201 Created và Location trỏ tới resource vừa tạo.
3. Search endpoint dùng query page và size.

Thực hiện:

1. Chạy documentation tests và lưu baseline snippets đã review.
2. Nâng Spring Boot/Spring REST Docs trong branch thử nghiệm.
3. Chạy lại cùng test với fixture không đổi.
4. Đối chiếu URI, method, status, Content-Type, Location, query parameter và response fields.
5. Mô phỏng đổi id từ number sang string và thêm currency; phân loại rủi ro từng thay đổi.
6. Cố ý xóa response field descriptor hoặc đổi header để quan sát strict test failure.
7. Tạo diff artifact trong CI và review trước khi cập nhật baseline.
8. Cập nhật descriptor và Asciidoctor include sau khi contract mới được chấp thuận.

**Tiêu chí hoàn thành:** tạo được baseline snippet ổn định; đối chiếu URI/header/payload; nhận diện breaking và compatible changes; giữ strict validation; review diff trước khi cập nhật tài liệu và baseline.

## 13. Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
