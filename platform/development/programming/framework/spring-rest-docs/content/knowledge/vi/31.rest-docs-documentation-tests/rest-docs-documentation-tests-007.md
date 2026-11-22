# Test endpoint thành công, thất bại và biên

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, documentation test cần chứng minh endpoint hoạt động đúng trong những tình huống quan trọng, đồng thời tạo snippet mô tả request và response đã được kiểm chứng. Một bộ test chỉ có happy path thường chưa đủ: client còn cần biết API phản hồi thế nào khi request sai, resource không tồn tại, người dùng không có quyền hoặc dữ liệu nằm đúng tại ranh giới cho phép.

Bài này hướng dẫn thiết kế ba nhóm kịch bản:

1. **Thành công (happy path):** request hợp lệ và endpoint thực hiện đúng hành động.
2. **Thất bại (negative path):** request hoặc ngữ cảnh không thỏa điều kiện và endpoint trả lỗi theo hợp đồng.
3. **Giá trị biên (boundary):** dữ liệu ở ngay giới hạn cho phép và ngay ngoài giới hạn đó.

Sau bài này, bạn có thể:

- Thiết kế bộ kịch bản thành công, thất bại và boundary cho một endpoint.
- Chọn status code và assertion phù hợp với từng trường hợp.
- Kiểm thử validation và quy tắc nghiệp vụ ở các ranh giới.
- Tách operation ID cho từng response khác nhau để snippet không ghi đè nhau.
- Dùng REST Docs để tài liệu hóa cả response thành công và response lỗi.
- Giữ test độc lập, dữ liệu xác định và đủ đại diện cho hợp đồng API.

## 1. Vì sao cần cả ba nhóm kịch bản?

Giả sử endpoint tạo sản phẩm nhận name và price. Một test chỉ gửi dữ liệu hợp lệ có thể chứng minh sản phẩm được tạo, nhưng chưa trả lời:

- name rỗng có bị từ chối không?
- price bằng 0 có hợp lệ không?
- price âm có bị từ chối không?
- name dài đúng giới hạn có được chấp nhận không?
- name vượt giới hạn một ký tự có trả lỗi đúng cấu trúc không?
- request thiếu field bắt buộc có được xử lý đúng không?

Một tài liệu API tốt cần cho người tích hợp biết cả cách gọi thành công lẫn cách xử lý lỗi. Bộ test cũng cần bảo vệ các ranh giới để thay đổi validation không vô tình làm hợp đồng rộng hơn hoặc hẹp hơn.

| Nhóm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Thành công | Xác minh luồng chuẩn | POST hợp lệ trả 201 và resource mới |
| Thất bại | Xác minh điều kiện bị từ chối | POST sai dữ liệu trả 400 |
| Biên | Xác minh ranh giới được phép | name dài đúng max được chấp nhận; max+1 bị từ chối |

Không phải mọi giá trị đều cần một documentation test riêng. Chọn các trường hợp có ý nghĩa với hợp đồng công khai, sau đó bổ sung unit/validation tests chi tiết hơn nếu tổ hợp dữ liệu quá lớn.

## 2. Xác định hợp đồng trước khi viết test

Trước khi viết kịch bản, lập bảng hành vi dự kiến:

| Điều kiện | Kết quả HTTP | Điều cần kiểm tra |
| --- | --- | --- |
| Request hợp lệ | 201 Created | Location, response body, resource đã được tạo |
| Thiếu name | 400 Bad Request | Error code và violation field |
| name chỉ có whitespace | 400 Bad Request | Lỗi validation của name |
| price âm | 400 Bad Request | Lỗi validation hoặc business rule |
| price đúng min/max | 201 Created | Giá trị biên được chấp nhận |
| price ngoài giới hạn | 400 Bad Request | Lỗi chỉ rõ field/điều kiện |
| Resource không tồn tại khi GET | 404 Not Found | Error response |
| Không có quyền | 403 Forbidden hoặc status đã quy định | Security error response |

Các status trong bảng là ví dụ. API có thể dùng status hoặc error schema khác; test phải theo hợp đồng thật, không ép dự án vào một quy ước chưa được thống nhất.

## 3. Chuẩn bị DTO và endpoint mẫu

Ví dụ DTO:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 2, max = 80)
        String name,
        @NotNull
        @DecimalMin("0.01")
        @DecimalMax("1000000.00")
        BigDecimal price
) {
}
```

Controller:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    @PostMapping
    ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse created = this.productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
```

Ví dụ này giả định ứng dụng có Bean Validation provider, exception handler chuẩn hóa lỗi và service tạo resource. Giới hạn name/price là chính sách minh họa; dự án thực tế phải chọn theo nghiệp vụ.

## 4. Kịch bản thành công: happy path

### 4.1. Gửi request hợp lệ

Request:

```json
{
  "name": "Mechanical Keyboard",
  "price": 129.90
}
```

Test MockMvc:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 129.90
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(header().string(
            HttpHeaders.LOCATION,
            endsWith("/api/products/501")))
    .andExpect(jsonPath("$.id").value(501))
    .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
    .andExpect(jsonPath("$.price").value(129.90))
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán.")
        ),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm do server tạo."),
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán.")
        )));
```

Test này kiểm tra status 201, Content-Type JSON, Location, response body và descriptor cho request/response.

### 4.2. Kiểm tra tác động nghiệp vụ

Nếu test chạy với repository/database test thật, có thể xác minh resource đã được lưu:

```java
assertThat(productRepository.findById(501L))
        .isPresent()
        .get()
        .extracting(Product::getName)
        .isEqualTo("Mechanical Keyboard");
```

Nếu dùng service mock, kiểm tra service được gọi với dữ liệu đã parse:

```java
verify(productService).create(argThat(request ->
        request.name().equals("Mechanical Keyboard")
                && request.price().compareTo(new BigDecimal("129.90")) == 0
));
```

Chọn cách xác minh phù hợp với phạm vi test. Không nên giả vờ kiểm tra persistence nếu repository đã được thay bằng mock.

## 5. Kịch bản thất bại: validation error

### 5.1. Thiếu field bắt buộc

Request thiếu name:

```json
{
  "price": 129.90
}
```

Test:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "price": 129.90
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.violations").isArray())
    .andExpect(jsonPath("$.violations[*].field")
            .value(hasItem("name")))
    .andDo(document("products-create-missing-name",
        responseFields(
            fieldWithPath("code").description("Mã lỗi."),
            fieldWithPath("message").description("Thông điệp lỗi."),
            fieldWithPath("violations").description("Danh sách lỗi validation."),
            fieldWithPath("violations[].field").description("Tên field lỗi."),
            fieldWithPath("violations[].message").description("Mô tả lỗi.")
        )));
```

Descriptor phải khớp chính xác error JSON thực tế. Nếu API dùng errors thay cho violations hoặc cấu trúc khác, cập nhật path theo response thật.

### 5.2. Chuỗi chỉ có whitespace

Request:

```json
{
  "name": "   ",
  "price": 129.90
}
```

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(invalidNameJson))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.violations[*].field")
            .value(hasItem("name")))
    .andDo(document("products-create-blank-name",
        responseFields(errorDescriptors)));
```

Test này khác với trường hợp thiếu name. Nó xác minh @NotBlank từ chối chuỗi chỉ chứa whitespace. Nếu muốn tài liệu hóa đầy đủ từng error case, dùng operation ID riêng.

### 5.3. Dữ liệu không hợp lệ không làm thay đổi trạng thái

Ngoài response 400, có thể xác minh service không tạo resource:

```java
verify(productService, never()).create(any());
```

Hoặc kiểm tra repository không có bản ghi tương ứng trong integration test. Đây là assertion hành vi quan trọng: request sai không được tạo dữ liệu một phần.

## 6. Kịch bản thất bại: lỗi nghiệp vụ và resource

Validation không bao phủ mọi lỗi. Một request có thể đúng định dạng nhưng vi phạm quy tắc nghiệp vụ.

Ví dụ mã sản phẩm đã tồn tại:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validRequestJson))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("PRODUCT_ALREADY_EXISTS"))
    .andDo(document("products-create-conflict",
        responseFields(
            fieldWithPath("code").description("Mã lỗi nghiệp vụ."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

Các trường hợp thường cần tài liệu hóa:

| Tình huống | Kết quả ví dụ | Điều cần assert |
| --- | --- | --- |
| Resource không tồn tại | 404 | Error code và message |
| Dữ liệu xung đột | 409 | Mã lỗi domain |
| Không xác thực | 401 | Error body và WWW-Authenticate nếu có |
| Không đủ quyền | 403 | Error body và không thực hiện hành động |
| Quá giới hạn request | 429 | Error body và Retry-After nếu hợp đồng có |
| Dependency tạm thời không khả dụng | 503 | Error response và retry semantics nếu có |

Không cần tạo test tài liệu cho mọi exception nội bộ. Tập trung vào các nhánh lỗi công khai mà client có thể xử lý.

## 7. Kịch bản giá trị biên

### 7.1. Boundary value analysis

Với một giới hạn min/max, các giá trị quan trọng thường là:

- min - 1: ngay dưới giới hạn.
- min: đúng giới hạn dưới.
- min + 1: ngay trên giới hạn dưới.
- max - 1: ngay dưới giới hạn trên.
- max: đúng giới hạn trên.
- max + 1: ngay trên giới hạn trên.

Không phải kiểu dữ liệu nào cũng biểu diễn min - 1 hoặc max + 1 theo cùng cách. Với chuỗi, dùng độ dài; với số, dùng bước nhỏ nhất phù hợp precision; với ngày, dùng đơn vị ngày hoặc thời gian API quy định.

### 7.2. Biên độ dài chuỗi

Với name có độ dài từ 2 đến 80:

| Độ dài | Kết quả dự kiến |
| --- | --- |
| 1 | Không hợp lệ |
| 2 | Hợp lệ |
| 3 | Hợp lệ |
| 79 | Hợp lệ |
| 80 | Hợp lệ |
| 81 | Không hợp lệ |

Ví dụ test helper:

```java
private String repeat(char value, int length) {
    return String.valueOf(value).repeat(length);
}
```

Kiểm tra max:

```java
String nameAtMax = repeat('A', 80);
String nameOverMax = repeat('A', 81);

this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(productJson(nameAtMax, "10.00")))
    .andExpect(status().isCreated())
    .andDo(document("products-create-name-max"));

this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(productJson(nameOverMax, "10.00")))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-name-over-max",
        responseFields(errorDescriptors)));
```

Nếu cùng test class dùng database thật, cần dọn dữ liệu hoặc dùng fixture riêng để lần chạy sau không bị lỗi trùng.

### 7.3. Biên số tiền

Với price trong khoảng 0.01 đến 1,000,000.00:

| Giá trị | Kết quả dự kiến |
| --- | --- |
| 0.00 | Không hợp lệ |
| 0.01 | Hợp lệ |
| 0.02 | Hợp lệ |
| 999,999.99 | Hợp lệ |
| 1,000,000.00 | Hợp lệ |
| 1,000,000.01 | Không hợp lệ |

Với BigDecimal, so sánh bằng compareTo khi cần bỏ qua khác biệt scale:

```java
assertThat(actualPrice.compareTo(new BigDecimal("0.01"))).isZero();
```

Đừng dùng double để biểu diễn tiền trong assertion nếu hợp đồng dùng decimal chính xác. Cũng cần thống nhất API nhận decimal JSON, scale cho phép và cách làm tròn.

### 7.4. Biên collection

Nếu API cho phép từ 1 đến 50 phần tử:

| Số phần tử | Kết quả |
| --- | --- |
| 0 | Không hợp lệ |
| 1 | Hợp lệ |
| 49 | Hợp lệ |
| 50 | Hợp lệ |
| 51 | Không hợp lệ |

Ngoài kích thước collection, kiểm tra phần tử null, trùng lặp và phần tử không hợp lệ nếu các trường hợp đó thuộc hợp đồng.

## 8. Tách operation ID theo kịch bản

Mỗi response khác nhau cần operation ID riêng để snippet không ghi đè:

| Kịch bản | Operation ID gợi ý |
| --- | --- |
| Tạo thành công | products-create |
| Thiếu name | products-create-missing-name |
| Name blank | products-create-blank-name |
| Name vượt max | products-create-name-over-max |
| Price dưới min | products-create-price-under-min |
| Price trên max | products-create-price-over-max |
| Trùng mã sản phẩm | products-create-conflict |

Ví dụ include:

```asciidoc
== Tạo sản phẩm thành công
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]

== Request thiếu tên
include::{snippets}/products-create-missing-name/http-response.adoc[]
include::{snippets}/products-create-missing-name/response-fields.adoc[]

== Tên vượt giới hạn
include::{snippets}/products-create-name-over-max/http-response.adoc[]
include::{snippets}/products-create-name-over-max/response-fields.adoc[]
```

Không dùng cùng operation ID cho test thành công và lỗi validation. Các file http-response.adoc hoặc response-fields.adoc có thể bị ghi đè theo thứ tự test.

## 9. Dùng parameterized test và test matrix

Parameterized test phù hợp để kiểm tra nhiều boundary values:

```java
@ParameterizedTest
@ValueSource(ints = {1, 81})
void rejectsNameOutsideLengthRange(int length) throws Exception {
    String name = "A".repeat(length);

    this.mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content(productJson(name, "10.00")))
        .andExpect(status().isBadRequest());
}
```

Test trên xác minh nhiều dữ liệu nhưng chưa tạo snippet cho từng trường hợp. Nếu muốn tài liệu hóa response, cần operation ID ổn định theo từng tình huống hoặc một test riêng đại diện cho nhóm lỗi. Không tạo ID dựa trên mọi giá trị runtime nếu điều đó sinh ra hàng trăm thư mục không cần thiết.

Một test matrix có thể quản lý các trường hợp:

| Field | Giá trị | Nhóm | Expected |
| --- | --- | --- | --- |
| name | thiếu | Negative | 400 |
| name | blank | Negative | 400 |
| name | 1 ký tự | Boundary below | 400 |
| name | 2 ký tự | Boundary min | 201 |
| name | 80 ký tự | Boundary max | 201 |
| name | 81 ký tự | Boundary above | 400 |
| price | 0.00 | Boundary below | 400 |
| price | 0.01 | Boundary min | 201 |
| price | 1,000,000.00 | Boundary max | 201 |
| price | 1,000,000.01 | Boundary above | 400 |

Test matrix giúp phát hiện khoảng trống coverage, nhưng cần tránh tổ hợp Cartesian product quá lớn nếu các field độc lập.

## 10. MockMvc, WebTestClient và REST Assured

### 10.1. MockMvc

MockMvc đặt assertion trước document:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validRequestJson))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andDo(document("products-create"));
```

### 10.2. WebTestClient

WebTestClient dùng exchange và expectation:

```java
this.webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard")
    .consumeWith(document("products-create"));
```

### 10.3. REST Assured

REST Assured đặt document filter trong request chain và assertion trong then:

```java
given(this.spec)
    .contentType(ContentType.JSON)
    .body(request)
    .filter(document("products-create"))
    .when()
    .post("/api/products")
    .then()
    .statusCode(201)
    .body("name", equalTo("Keyboard"));
```

Adapter REST Docs phải tương thích với phiên bản REST Assured và Spring REST Docs của dự án. Dù dùng client nào, nguyên tắc không đổi: test phải thất bại nếu status/body không đúng hợp đồng.

## 11. Test độc lập và dữ liệu xác định

Documentation tests tạo snippet dùng trong tài liệu; dữ liệu không ổn định khiến tài liệu thay đổi không cần thiết.

Nên:

- Chuẩn bị fixture rõ ràng cho từng kịch bản.
- Làm sạch database hoặc reset mock state giữa test.
- Không phụ thuộc thứ tự chạy.
- Không dùng timestamp, UUID, token hoặc session thật trong snippet.
- Cố định Clock/ID generator khi cần giá trị cụ thể.
- Dùng operation ID riêng cho response khác nhau.
- Chỉ tài liệu hóa một số boundary case đại diện; giữ các kiểm tra chi tiết còn lại trong validation/unit tests.

Nếu test dùng repository thật, xác minh cả trạng thái trước và sau để bảo đảm negative case không tạo dữ liệu. Nếu dùng mock, verify service không được gọi hoặc được gọi đúng theo nhánh.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test happy path pass nhưng API vẫn sai | Chỉ assert status, không kiểm tra body/header | Assert field và header quan trọng |
| Invalid request vẫn tạo resource | Validation chưa kích hoạt hoặc service không bảo vệ rule | Kiểm tra @Valid, provider và side effect |
| Boundary max không ổn định | Tạo chuỗi/decimal sai đơn vị hoặc scale | Dùng length và BigDecimal rõ ràng |
| Test lỗi descriptor | Error payload khác path đã khai báo | Đối chiếu JSON thật rồi sửa descriptor |
| Snippet lỗi ghi đè | Nhiều scenario dùng cùng operation ID | Tách operation ID |
| Test phụ thuộc dữ liệu cũ | Database không reset hoặc fixture trùng | Dọn state và tạo fixture độc lập |
| Assertion phụ thuộc thứ tự violations | API không cam kết thứ tự lỗi | Tìm violation theo field/code thay vì index |
| Test matrix quá lớn | Kết hợp mọi giá trị của mọi field | Chọn boundary độc lập và pairwise khi phù hợp |
| Tài liệu chỉ có response thành công | Chưa viết operation cho lỗi công khai | Thêm error documentation tests |
| Test pass nhưng snippet không đại diện | Fixture không phản ánh cấu trúc thực tế | Chọn dữ liệu mẫu có đủ nested/array fields |

## 13. Bài thực hành

1. Tạo endpoint POST /api/products với name và price có giới hạn.
2. Viết happy-path test, assert 201, Location và response body; tạo operation products-create.
3. Viết test thiếu name, assert 400 và error body; tạo operation riêng.
4. Viết test name chỉ whitespace và price âm.
5. Kiểm tra name có độ dài min, max, min-1 và max+1.
6. Kiểm tra price ở min, max và ngay ngoài hai giới hạn.
7. Xác minh request không hợp lệ không tạo resource hoặc không gọi service create.
8. Include response snippets của success và error vào các section riêng trong AsciiDoc.
9. Chạy test nhiều lần và kiểm tra output snippet ổn định.

**Câu hỏi tự đánh giá**

1. Vì sao happy path không đủ để bảo vệ hợp đồng API?
2. Validation failure khác business conflict ở điểm nào?
3. Boundary value analysis chọn những giá trị nào quanh min/max?
4. Vì sao cần kiểm tra side effect của request không hợp lệ?
5. Khi nào nên tạo operation ID riêng cho một boundary case?
6. Parameterized test có luôn cần tạo snippet cho từng input không?
7. Làm thế nào tránh test phụ thuộc thứ tự validation violations?
8. Vì sao tài liệu hóa một số error response công khai có ích cho client?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): HTTP tests và sinh snippet.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): tích hợp documentation test và snippet.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): kích hoạt validation trong Spring.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): status, header và body assertions.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm tra HTTP exchange.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint, groups và validation metadata.

**Kết luận thực hành:** Xây dựng documentation test theo ba nhóm thành công, thất bại và giá trị biên. Với mỗi nhóm, assert status, headers, body và side effect theo hợp đồng; dùng operation ID riêng cho các response khác nhau; dùng REST Docs để mô tả request/response đã kiểm chứng. Cách này giúp tài liệu hướng dẫn cả cách sử dụng đúng lẫn cách client xử lý khi dữ liệu hoặc ngữ cảnh không hợp lệ.
