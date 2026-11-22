# Assertion status, header và body trước document

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, một documentation test cần chứng minh endpoint thực hiện đúng hợp đồng HTTP rồi mới tạo snippet từ exchange đó. Ba nhóm assertion cơ bản của response là **status code**, **headers** và **body**. Chúng trả lời ba câu hỏi khác nhau: server phản hồi trạng thái nào, metadata của response có đúng không và nội dung trả về có đúng không.

Spring REST Docs ghi lại HTTP request/response và kiểm tra các descriptor mà test cung cấp. Nó không tự quyết định status nào là đúng, header nào phải có hay giá trị JSON nào đúng với nghiệp vụ. Những điều đó phải được kiểm tra bằng assertion của MockMvc, WebTestClient hoặc REST Assured.

Sau bài này, bạn có thể:

- Chọn status matcher chính xác cho từng tình huống endpoint.
- Kiểm tra sự tồn tại, giá trị và kiểu của response header.
- Kiểm tra body bằng JSONPath, content assertion hoặc object assertion.
- Phân biệt response không có body, JSON null và field bị thiếu.
- Kết hợp status/header/body assertion với document snippet.
- Viết assertion cho response thành công, lỗi và no-content.
- Tránh matcher quá rộng hoặc phụ thuộc vào dữ liệu ngẫu nhiên.

## 1. Ba lớp assertion trong response

| Lớp | Ví dụ cần xác minh | Assertion thường dùng |
| --- | --- | --- |
| Status | Tạo mới trả 201; không tìm thấy trả 404 | status matcher, statusCode |
| Header | Content-Type là JSON; Location trỏ tới resource mới | header matcher, expectHeader, header assertion |
| Body | ID có kiểu số; tên đúng; error code đúng | JSONPath, body matcher, object comparison |

Ví dụ một endpoint tạo sản phẩm có hợp đồng:

- Trả HTTP 201 Created.
- Trả Content-Type tương thích application/json.
- Trả Location dẫn tới tài nguyên vừa tạo.
- Body chứa id, name và status.

Test nên kiểm tra cả bốn điều này trước khi xem operation là đã được kiểm chứng. Chỉ kiểm tra status 201 có thể bỏ lọt response body sai hoặc Location bị thiếu.

## 2. Status assertion: chọn đúng trạng thái HTTP

### 2.1. Dùng status matcher cụ thể

Với MockMvc:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("products-create"));
```

Các matcher phổ biến:

| Matcher | Status |
| --- | --- |
| isOk() | 200 |
| isCreated() | 201 |
| isAccepted() | 202 |
| isNoContent() | 204 |
| isBadRequest() | 400 |
| isUnauthorized() | 401 |
| isForbidden() | 403 |
| isNotFound() | 404 |
| isConflict() | 409 |
| isTooManyRequests() | 429 |
| isInternalServerError() | 500 |

Với WebTestClient, dùng matcher tương ứng:

```java
.expectStatus().isCreated()
```

Với REST Assured:

```java
.then()
.statusCode(201)
```

Danh sách trên chỉ là các tình huống thường gặp. Hãy dùng status đã được API contract quy định; không ép mọi endpoint tạo mới phải trả 201 nếu hệ thống có hợp đồng khác.

### 2.2. Tránh assertion status quá rộng

Các assertion sau yếu hơn khi API có status cụ thể:

```java
// Chỉ kiểm tra thuộc nhóm 2xx
.andExpect(status().is2xxSuccessful())
```

```java
// Chỉ kiểm tra status thuộc khoảng thành công
.then().statusCode(greaterThanOrEqualTo(200))
```

Nếu endpoint vô tình đổi từ 201 sang 200, assertion rộng vẫn có thể pass. Khi status là một phần hợp đồng, ưu tiên matcher cụ thể. Matcher theo nhóm chỉ phù hợp khi hợp đồng thực sự cho phép nhiều status.

### 2.3. Kiểm tra status của các nhánh lỗi

Tài liệu không chỉ cần luồng thành công:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andDo(document("products-not-found"));
```

Với validation:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": " ",
                  "price": -1
                }
                """))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-invalid"));
```

Status assertion bảo đảm endpoint thực sự xử lý nhánh lỗi theo hợp đồng, trong khi snippet ghi lại response lỗi để tài liệu hóa.

## 3. Header assertion: kiểm tra metadata của response

### 3.1. Content-Type

Nếu endpoint trả JSON, kiểm tra media type:

```java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
```

contentTypeCompatibleWith phù hợp khi chấp nhận media type tương thích, kể cả tham số như charset. Nếu hợp đồng yêu cầu giá trị chính xác và không có biến thể, có thể dùng matcher chính xác hơn:

```java
.andExpect(content().contentType(MediaType.APPLICATION_JSON))
```

WebTestClient:

```java
.expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
```

REST Assured:

```java
.then().contentType(ContentType.JSON)
```

Phân biệt Content-Type và Accept:

- Accept là header request, biểu thị loại response client mong muốn.
- Content-Type là header response, biểu thị loại representation server thực sự gửi.

Kiểm tra Accept trong request không thay thế kiểm tra Content-Type ở response.

### 3.2. Location sau khi tạo resource

Endpoint tạo resource thường trả Location:

```java
.andExpect(status().isCreated())
.andExpect(header().exists(HttpHeaders.LOCATION))
```

Chỉ kiểm tra tồn tại chưa đủ khi hợp đồng yêu cầu URI cụ thể. Có thể kiểm tra giá trị:

```java
.andExpect(header().string(
        HttpHeaders.LOCATION,
        endsWith("/api/products/501")
))
```

Hoặc lấy URI và kiểm tra các thành phần:

```java
MvcResult result = this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andReturn();

URI location = URI.create(
        result.getResponse().getHeader(HttpHeaders.LOCATION));

assertThat(location.getPath()).isEqualTo("/api/products/501");
```

Nếu ID sinh động, dùng fixture hoặc kiểm tra pattern/đường dẫn có cấu trúc thay vì cố định một ID ngẫu nhiên. Location là URI tham chiếu tới resource; đừng vô tình khẳng định host/port của máy local là một phần hợp đồng nếu chúng phụ thuộc môi trường.

### 3.3. Cache-Control, ETag và Retry-After

Một số header ảnh hưởng trực tiếp cách client dùng API:

```java
.andExpect(header().string(
        HttpHeaders.CACHE_CONTROL,
        containsString("no-store")
))
```

```java
.andExpect(header().exists(HttpHeaders.ETAG))
```

```java
.andExpect(header().string(HttpHeaders.RETRY_AFTER, "30"))
```

Chỉ assertion những header thuộc hợp đồng hoặc chính sách mà endpoint phải đảm bảo. Nếu header được middleware/proxy bổ sung theo môi trường, cần chọn phạm vi test phù hợp.

### 3.4. Set-Cookie

Nếu đăng nhập tạo cookie phiên:

```java
.andExpect(header().exists(HttpHeaders.SET_COOKIE))
.andExpect(header().string(
        HttpHeaders.SET_COOKIE,
        allOf(
            containsString("SESSION="),
            containsString("HttpOnly"),
            containsString("Secure"),
            containsString("SameSite=Lax")
        )
))
```

Ví dụ trên minh họa kiểm tra các phần quan trọng của Set-Cookie. Với ứng dụng thực, có thể parse Set-Cookie bằng API cookie phù hợp để kiểm tra tên, Path, Max-Age và các thuộc tính thay vì phụ thuộc toàn bộ thứ tự chuỗi header.

Không include giá trị session hoặc refresh token thật vào tài liệu. Test phải dùng giá trị giả.

## 4. Body assertion bằng JSONPath

### 4.1. Kiểm tra field và giá trị

Response:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

MockMvc:

```java
.andExpect(jsonPath("$.id").isNumber())
.andExpect(jsonPath("$.name").value("Keyboard"))
.andExpect(jsonPath("$.price").value(129.90))
.andExpect(jsonPath("$.status").value("ACTIVE"))
```

JSONPath kiểm tra nội dung response ở cấp field. Dùng assertion vừa đủ để bảo vệ hợp đồng quan trọng:

- Kiểm tra kiểu khi kiểu là điều client phụ thuộc.
- Kiểm tra giá trị chính xác khi giá trị đã xác định.
- Kiểm tra field tồn tại khi field bắt buộc.
- Kiểm tra danh sách có phần tử phù hợp khi endpoint phải trả kết quả.

### 4.2. Kiểm tra field thiếu, null và giá trị rỗng

Ba trường hợp JSON sau khác nhau:

```json
{}
```

```json
{"description": null}
```

```json
{"description": ""}
```

Chúng lần lượt biểu thị field không có, field có giá trị null và field có chuỗi rỗng. Khi hợp đồng phân biệt các trường hợp này, assertion cũng phải phân biệt.

Ví dụ kiểm tra field có mặt và không null:

```java
.andExpect(jsonPath("$.description").exists())
.andExpect(jsonPath("$.description").value(notNullValue()))
```

Kiểm tra giá trị chuỗi rỗng:

```java
.andExpect(jsonPath("$.description").value(""))
```

Nếu API cho phép field bị thiếu, đừng dùng exists() như thể field luôn bắt buộc.

### 4.3. Kiểm tra array và nested object

```json
{
  "items": [
    {"id": 10, "quantity": 2},
    {"id": 11, "quantity": 1}
  ]
}
```

```java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items.length()").value(2))
.andExpect(jsonPath("$.items[0].id").value(10))
.andExpect(jsonPath("$.items[0].quantity").value(2))
```

Nếu thứ tự array không phải một phần hợp đồng, tránh assert phần tử ở index cố định. Thay vào đó, kiểm tra kích thước, sự tồn tại hoặc tập giá trị theo cách không phụ thuộc thứ tự.

### 4.4. Kiểm tra error body

Response lỗi:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request không hợp lệ",
  "violations": [
    {
      "field": "name",
      "message": "Không được để trống"
    }
  ]
}
```

Assertions:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
.andExpect(jsonPath("$.violations").isArray())
.andExpect(jsonPath("$.violations[0].field").value("name"))
```

Đối với danh sách lỗi, nên tránh phụ thuộc thứ tự nếu API không cam kết thứ tự violations. Có thể kiểm tra số lượng hoặc tìm phần tử theo field/code.

## 5. Body assertion bằng content hoặc object comparison

Không phải mọi response đều cần JSONPath.

### 5.1. Response text đơn giản

```java
this.mockMvc.perform(get("/health/message"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
    .andExpect(content().string("service-ready"))
    .andDo(document("health-message"));
```

### 5.2. Body không có nội dung

Với endpoint trả 204:

```java
this.mockMvc.perform(delete("/api/products/{id}", 501))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""))
    .andDo(document("products-delete"));
```

Không khai báo responseFields cho body không tồn tại. Nếu response có JSON literal null thì đó vẫn là body có nội dung và khác với response body rỗng.

### 5.3. So sánh object

Trong một số test có thể deserialize response thành DTO rồi so sánh:

```java
MvcResult result = this.mockMvc.perform(get("/api/products/{id}", 501))
    .andExpect(status().isOk())
    .andReturn();

ProductResponse actual = objectMapper.readValue(
        result.getResponse().getContentAsString(),
        ProductResponse.class);

assertThat(actual.name()).isEqualTo("Keyboard");
assertThat(actual.status()).isEqualTo(ProductStatus.ACTIVE);
```

Cách này hữu ích khi có nhiều quy tắc object, nhưng không nên chỉ so sánh DTO bằng equals nếu equals bỏ qua field quan trọng. Hãy xác định rõ những field và quan hệ nào thuộc hợp đồng HTTP.

## 6. Đặt assertion trước document trong MockMvc

Với MockMvc, chuỗi thông dụng là:

1. perform(...) thực hiện request.
2. andExpect(...) xác minh status, header và body.
3. andDo(document(...)) ghi exchange và tạo snippet.

Ví dụ đầy đủ:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Keyboard",
                  "price": 129.90
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(jsonPath("$.id").isNumber())
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andExpect(jsonPath("$.status").value("ACTIVE"))
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán.")
        ),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm."),
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán."),
            fieldWithPath("status").description("Trạng thái.")
        )));
```

Nếu bất kỳ assertion nào thất bại, test thất bại. Đặt document sau andExpect làm luồng đọc rõ ràng: xác minh endpoint rồi mới ghi lại exchange.

## 7. Đặt assertion và document trong WebTestClient

WebTestClient có pipeline expectation riêng:

```java
this.webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
            "name", "Keyboard",
            "price", 129.90
    ))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().exists(HttpHeaders.LOCATION)
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard")
    .jsonPath("$.status").isEqualTo("ACTIVE")
    .consumeWith(document("products-create",
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm."),
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán."),
            fieldWithPath("status").description("Trạng thái.")
        )));
```

expectStatus và expectHeader xác minh metadata response; expectBody xác minh payload; consumeWith chuyển exchange đã nhận tới REST Docs để sinh snippet.

Nếu body không phải JSON, dùng expectBody với kiểu phù hợp và assertion tương ứng. Không thêm JSONPath vào endpoint trả text/plain hoặc body rỗng.

## 8. Assertion với REST Assured và REST Docs

REST Assured thường dùng given/when/then. REST Docs filter ghi request/response trong filter chain; các assertion then() vẫn phải được thực thi để test chỉ pass khi response hợp đồng là đúng:

```java
given(this.spec)
    .contentType(ContentType.JSON)
    .body("""
            {
              "name": "Keyboard",
              "price": 129.90
            }
            """)
    .filter(document("products-create",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán.")
        )))
    .when()
    .post("/api/products")
    .then()
    .statusCode(201)
    .contentType(ContentType.JSON)
    .header("Location", notNullValue())
    .body("name", equalTo("Keyboard"))
    .body("status", equalTo("ACTIVE"));
```

Khác với chuỗi andExpect rồi andDo của MockMvc, REST Assured gắn document filter vào request specification trước khi response assertions ở then() chạy. Điều cần bảo đảm là test chỉ được coi là đạt và snippet chỉ được xem là output đã kiểm chứng khi toàn bộ assertion then() pass. Kiểm tra cấu hình REST Assured/REST Docs theo đúng phiên bản adapter đang dùng.

## 9. Assertion và descriptor: hai lớp kiểm tra bổ sung

| Tình huống | Assertion | REST Docs descriptor |
| --- | --- | --- |
| Response phải có status 201 | status().isCreated() | HTTP response snippet ghi status thực tế |
| Response phải có Location | header().exists(...) hoặc so URI | responseHeaders mô tả ý nghĩa Location |
| Field name phải là Keyboard | jsonPath("$.name").value(...) | responseFields mô tả field name |
| Field status phải được công bố | jsonPath("$.status").exists() | responseFields yêu cầu mô tả status |
| Error code phải đúng | jsonPath("$.code").value(...) | responseFields mô tả schema lỗi |

Assertion không thay thế descriptor: test có thể xác minh body đúng nhưng tài liệu chưa giải thích field. Descriptor cũng không thay thế assertion: tài liệu có thể liệt kê field status nhưng không biết giá trị "ACTIVE" hay "DELETED" có đúng nghiệp vụ.

Với request side, cũng cần kiểm tra request setup có gửi đúng dữ liệu, content type và header hay không, sau đó dùng request descriptors để kiểm tra phần được công bố.

## 10. Chọn mức độ chặt của assertion

Assertion nên đủ chính xác để bảo vệ hợp đồng, nhưng không nên kiểm tra những chi tiết không ổn định.

| Assertion mong manh | Vấn đề | Cách ổn định hơn |
| --- | --- | --- |
| So toàn bộ JSON string | Thứ tự property, whitespace và formatting thay đổi | JSONPath hoặc JSON-aware comparison |
| So Location bao gồm host/port local | Môi trường test có host/port khác | Kiểm tra path hoặc URI components thuộc hợp đồng |
| So timestamp chính xác theo thời điểm chạy | Giá trị biến đổi theo clock | Dùng Clock cố định hoặc kiểm tra format/range |
| So UUID ngẫu nhiên cố định | Mỗi lần chạy có ID mới | Dùng ID generator giả hoặc kiểm tra format/tính duy nhất |
| Kiểm tra mọi header do proxy sinh | Phụ thuộc hạ tầng | Chỉ assert header endpoint cam kết |
| Dùng mọi status 2xx | Không phát hiện 200 thay cho 201 | Assert status cụ thể khi hợp đồng quy định |

Không làm assertion quá yếu chỉ để giảm test failure. Nếu một giá trị là hợp đồng, hãy kiểm tra nó; nếu chỉ là chi tiết runtime, hãy cố định dependency hoặc kiểm tra thuộc tính ổn định của giá trị.

## 11. Checklist cho response assertion trước document

- [ ] Status code khớp với hợp đồng của operation.
- [ ] Content-Type phù hợp với representation trả về.
- [ ] Header bắt buộc như Location, ETag, Cache-Control hoặc Retry-After được kiểm tra khi thuộc hợp đồng.
- [ ] Set-Cookie được kiểm tra nếu endpoint tạo/cập nhật cookie.
- [ ] Các field body quan trọng tồn tại và có giá trị/kiểu đúng.
- [ ] Nested object và array được kiểm tra theo quy tắc có ý nghĩa.
- [ ] Error response được kiểm tra status, error code và cấu trúc violation.
- [ ] Endpoint 204 được xác minh không có body.
- [ ] Không phụ thuộc timestamp, UUID, thứ tự hoặc host/port ngẫu nhiên.
- [ ] Chỉ sau khi hành vi đã được assertion mới xem snippet là tài liệu đã kiểm chứng.

## 12. Bài thực hành

1. Tạo endpoint POST /api/products trả 201, Location và JSON response.
2. Viết MockMvc test assert status 201, Content-Type, Location và các field name/status.
3. Thêm responseFields để mô tả toàn bộ field của payload.
4. Tạo endpoint GET không tìm thấy resource; assert 404, error code và message.
5. Tạo endpoint DELETE trả 204; assert body rỗng và không khai báo responseFields.
6. Tạo login test phát Set-Cookie; assert tên cookie cùng các thuộc tính bảo mật quan trọng.
7. Viết lại một test bằng WebTestClient hoặc REST Assured, giữ nguyên các điều kiện hợp đồng.
8. Thử đổi status hoặc giá trị body trong endpoint; xác nhận assertion thất bại trước khi chấp nhận tài liệu mới.

**Câu hỏi tự đánh giá**

1. Vì sao status matcher cụ thể tốt hơn is2xxSuccessful khi hợp đồng yêu cầu 201?
2. Content-Type response khác Accept request ở đâu?
3. Khi nào chỉ kiểm tra Location tồn tại là chưa đủ?
4. JSON field thiếu khác field null và chuỗi rỗng như thế nào?
5. Vì sao JSONPath assertion không thay thế responseFields?
6. WebTestClient đặt document ở bước nào sau expectation?
7. REST Assured document filter chạy ở đâu so với then() assertions?
8. Làm sao kiểm tra timestamp hoặc UUID mà không tạo test chập chờn?

## Tài liệu tham khảo chính thức

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): status, header, content và JSONPath expectations.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): exchange, status, header và body assertions.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): tích hợp REST Docs vào HTTP test.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors và kiểm tra payload.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): request/response header descriptors.
- [REST Assured](https://rest-assured.io/): status, header và body assertions với given/when/then.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa status code và các thành phần HTTP.

**Kết luận thực hành:** Trước khi document, hãy chứng minh response đúng ở ba lớp: status, headers và body. Dùng status matcher cụ thể; kiểm tra header thực sự thuộc hợp đồng; kiểm tra các giá trị body quan trọng bằng JSONPath hoặc object assertion. Sau đó dùng descriptor REST Docs để xác minh nội dung được mô tả đầy đủ. Hai lớp kiểm tra cùng nhau giúp snippet được tạo từ một endpoint đã được kiểm chứng thay vì chỉ là bản ghi của một HTTP exchange bất kỳ.
