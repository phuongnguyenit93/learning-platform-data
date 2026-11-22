# Phân biệt request part với form parameter trong Spring REST Docs

## 1. Hai khái niệm gần nhau nhưng khác cách truyền

Form parameter và request part đều có thể mang dữ liệu dạng name/value, nhưng chúng thuộc những cách biểu diễn HTTP khác nhau.

**Form parameter** thường là một giá trị biểu mẫu được gửi theo `application/x-www-form-urlencoded`. Ví dụ:

```http
POST /api/profile HTTP/1.1
Content-Type: application/x-www-form-urlencoded

displayName=Nguyen+An&newsletter=true
```

Body được mã hóa thành các cặp tên/giá trị. Trong Spring REST Docs, dùng `formParameters(...)` cùng `parameterWithName(...)` để mô tả các trường biểu mẫu.

**Request part** là một phần riêng trong body `multipart/form-data`. Mỗi part có tên, nội dung và có thể có header riêng:

```http
POST /api/profile/photo HTTP/1.1
Content-Type: multipart/form-data; boundary=----FormBoundary

------FormBoundary
Content-Disposition: form-data; name="displayName"

Nguyen An
------FormBoundary
Content-Disposition: form-data; name="photo"; filename="avatar.png"
Content-Type: image/png

<bytes ảnh>
------FormBoundary--
```

Trong multipart, `displayName` cũng là một part trên wire, dù nội dung của nó chỉ là text. `photo` là part chứa file. Spring REST Docs dùng `requestParts(...)` và `partWithName(...)` để mô tả cấu trúc multipart.

Bài này thuộc chương **Request parts** của **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi đưa snippet vào Asciidoctor/Markdown và build/CI.

Sau bài học, bạn có thể:

- Phân biệt `application/x-www-form-urlencoded` với `multipart/form-data`.
- Chọn `formParameters(...)` hay `requestParts(...)` theo dạng dữ liệu HTTP thực tế.
- Hiểu vì sao một multipart text part có thể được bind bằng `@RequestParam`.
- Phân biệt `@RequestParam` với `@RequestPart` khi controller nhận JSON hoặc XML.
- Tạo snippet cho form parameter, multipart part và query parameter mà không trộn lẫn các phạm vi.
- Kiểm thử tên, sự hiện diện, kiểu nội dung và validation của các giá trị gửi lên.

## 2. Nhận diện theo Content-Type của request

Cách đáng tin cậy để phân biệt là nhìn vào `Content-Type` của toàn request và cấu trúc body.

| Đặc điểm | Form parameter | Request part |
| --- | --- | --- |
| Content-Type thường dùng | `application/x-www-form-urlencoded` | `multipart/form-data; boundary=...` |
| Cấu trúc body | Các cặp name/value được URL encode | Nhiều phần được phân tách bằng boundary |
| Mỗi giá trị có header riêng? | Không có header part riêng | Có thể có `Content-Disposition`, `Content-Type` |
| Thường dùng cho | Text field, lựa chọn, checkbox | File, JSON/XML part, text part và nội dung khác |
| Spring REST Docs | `formParameters(...)` | `requestParts(...)` |
| Descriptor | `parameterWithName(...)` | `partWithName(...)` |
| Snippet mặc định | `form-parameters.adoc` | `request-parts.adoc` |

Ví dụ hai request có thể cùng gửi giá trị `displayName=Nguyen An`, nhưng cách đóng gói khác nhau:

```text
application/x-www-form-urlencoded
    displayName=Nguyen+An

multipart/form-data
    Part name="displayName"
    Body: Nguyen An
```

Tên giá trị giống nhau không làm hai cấu trúc HTTP trở thành một. Khi chọn snippet, hãy căn cứ vào request được test gửi đi.

## 3. `formParameters(...)` và `parameterWithName(...)`

Spring REST Docs cung cấp `formParameters(...)` trong `RequestDocumentation` để tạo snippet cho form parameter:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("displayName")
        .description("Tên hiển thị của người dùng"),
    parameterWithName("newsletter")
        .description("Người dùng có đăng ký nhận bản tin hay không")
);
```

Snippet sinh ra là `form-parameters.adoc`. Descriptor dùng `ParameterDescriptor`; vì vậy API để tạo descriptor là `parameterWithName(...)`, không phải `fieldWithPath(...)` hay `partWithName(...)`.

Một bài test MockMvc cơ bản:

```java
mockMvc.perform(post("/api/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Nguyen An")
        .param("newsletter", "true"))
    .andExpect(status().isNoContent())
    .andDo(document("profile-update",
        formParameters(
            parameterWithName("displayName")
                .description("Tên hiển thị"),
            parameterWithName("newsletter")
                .description("Đăng ký nhận bản tin")
        )
    ));
```

`.param(...)` trong MockMvc dựng request parameter. Đặt Content-Type `application/x-www-form-urlencoded` làm rõ rằng đây là form body mã hóa URL, không phải JSON body.

### 3.1. Required, optional và ignored

Giống các descriptor request khác, parameter descriptor mặc định được xem là bắt buộc trong snippet. Nếu một form parameter có thể vắng mặt, đánh dấu `.optional()`:

```java
formParameters(
    parameterWithName("displayName")
        .description("Tên hiển thị"),
    parameterWithName("newsletter")
        .description("Đăng ký nhận bản tin")
        .optional()
);
```

Nếu parameter đã biết nhưng không cần xuất hiện trong bảng:

```java
parameterWithName("trackingSource")
    .description("Nguồn theo dõi nội bộ")
    .optional()
    .ignored();
```

`.optional()` cho phép parameter được mô tả vắng mặt trong request mẫu. `.ignored()` giữ parameter khỏi bảng snippet. Hai thuộc tính có mục tiêu khác nhau.

### 3.2. Strict và relaxed form parameters

`formParameters(...)` kiểm tra các form parameter theo descriptor; parameter chưa được mô tả có thể làm snippet thất bại. Khi cần mô tả một phần form và cho phép các parameter bổ sung, dùng `relaxedFormParameters(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;

relaxedFormParameters(
    parameterWithName("displayName")
        .description("Tên hiển thị")
);
```

Relaxed mode thích hợp khi form có phần mở rộng được contract cho phép. Nó làm giảm khả năng phát hiện parameter mới chưa được tài liệu hóa, vì vậy không nên dùng chỉ để tránh sửa descriptor.

## 4. `requestParts(...)` và `partWithName(...)`

Với `multipart/form-data`, body được chia thành nhiều part. Dùng `requestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("displayName")
        .description("Tên hiển thị trong biểu mẫu"),
    partWithName("photo")
        .description("Ảnh đại diện cần tải lên")
);
```

Ở đây cả `displayName` và `photo` đều là part trên wire. Part `displayName` có thể chỉ chứa text; part `photo` chứa file bytes và thường có filename cùng Content-Type riêng.

Spring REST Docs tạo snippet `request-parts.adoc`. Trong strict mode, part có trong request nhưng không được mô tả có thể làm test thất bại; descriptor required nhưng part vắng mặt cũng có thể làm test thất bại. Dùng `.optional()` khi part được phép vắng, `.ignored()` khi part đã biết nhưng không cần hiện trong bảng. `relaxedRequestParts(...)` cho phép các part chưa được mô tả xuất hiện.

Ví dụ multipart upload:

```java
mockMvc.perform(multipart("/api/profile/photo")
        .file(new MockMultipartFile(
            "photo",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes
        ))
        .part(new MockPart(
            "displayName",
            "Nguyen An".getBytes(StandardCharsets.UTF_8)
        )))
    .andExpect(status().isNoContent())
    .andDo(document("profile-photo-upload",
        requestParts(
            partWithName("displayName")
                .description("Tên hiển thị"),
            partWithName("photo")
                .description("Ảnh đại diện PNG")
        )
    ));
```

Ví dụ dùng `MockPart` để thể hiện text part và `MockMultipartFile` để thể hiện file part. Trong test thực tế, `validPngBytes` cần là fixture ảnh hợp lệ nếu endpoint kiểm tra nội dung file.

## 5. Cùng một multipart text part có thể bind bằng `@RequestParam`

Đây là điểm dễ gây nhầm. Cách controller bind dữ liệu và cách dữ liệu được biểu diễn trên wire là hai góc nhìn khác nhau.

Spring MVC có thể expose multipart form fields như request parameters. Vì vậy, một part text tên `displayName` có thể được bind như sau:

```java
@PostMapping(
    path = "/api/profile/photo",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @RequestParam("displayName") String displayName,
        @RequestPart("photo") MultipartFile photo) {
    // Xử lý tên hiển thị và ảnh.
    return ResponseEntity.noContent().build();
}
```

Ở tầng HTTP, `displayName` vẫn được gửi trong một multipart part. `@RequestParam` là cách Spring MVC lấy giá trị đơn giản đó vào method argument; nó không biến request body thành `application/x-www-form-urlencoded`.

Vì vậy:

- Nếu cần tài liệu hóa cấu trúc multipart request trên wire, dùng `requestParts(...)` cho part `displayName` và `photo`.
- Nếu operation là form URL-encoded, dùng `formParameters(...)`.
- Nếu chỉ muốn giải thích một giá trị được controller bind qua `@RequestParam`, hãy xác định request thực tế có phải form URL-encoded, query string hay multipart trước khi chọn snippet.

Đừng chỉ nhìn annotation controller để quyết định snippet. Hãy nhìn HTTP request mà client thực sự gửi.

## 6. `@RequestParam` và `@RequestPart` khác nhau như thế nào?

Spring Framework cho phép cả `@RequestParam` và `@RequestPart` liên kết một multipart part với tham số controller trong các trường hợp phù hợp. Sự khác biệt nổi bật nằm ở cách chuyển đổi nội dung:

- `@RequestParam` thường dùng cho name/value form field đơn giản. Giá trị được chuyển đổi bằng `Converter` hoặc `PropertyEditor` đã đăng ký.
- `@RequestPart` phù hợp với part có nội dung phức tạp như JSON/XML. Spring dùng `HttpMessageConverter` và xét Content-Type của part, tương tự cách `@RequestBody` xử lý body thông thường.

Ví dụ request multipart có text và JSON:

```http
Content-Disposition: form-data; name="category"

COVER
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Bìa sách","displayOrder":1}
```

Controller:

```java
@PostMapping(
    path = "/api/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> create(
        @RequestParam("category") AssetCategory category,
        @RequestPart("metadata") @Valid AssetMetadata metadata) {
    return ResponseEntity.noContent().build();
}
```

`category` là một giá trị name/value đơn giản, có thể chuyển đổi sang enum. `metadata` là JSON object nên được deserialize qua message converter theo `application/json`.

Tài liệu hóa multipart:

```java
requestParts(
    partWithName("category")
        .description("Loại tài sản"),
    partWithName("metadata")
        .description("Metadata JSON của tài sản")
),
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề tài sản"),
    fieldWithPath("displayOrder").description("Thứ tự hiển thị").optional()
)
```

Dù controller nhận `category` qua `@RequestParam`, nó vẫn là part của multipart request và có thể được mô tả trong bảng request parts. `requestPartFields(...)` chỉ dành cho field JSON bên trong `metadata`.

## 7. Không nhầm form parameter với query parameter

Một parameter cũng có thể nằm trong URL query string:

```http
GET /api/products?category=BOOK&page=2
```

Đây là query parameter, không phải form parameter và cũng không phải multipart part.

Spring REST Docs có API riêng:

```java
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("category").description("Loại sản phẩm"),
    parameterWithName("page").description("Số trang")
);
```

Các snippet có phạm vi khác nhau:

| Dạng dữ liệu | Ví dụ | API REST Docs |
| --- | --- | --- |
| Path variable | `/products/{id}` | `pathParameters(...)` |
| Query parameter | `?page=2` | `queryParameters(...)` |
| URL-encoded form parameter | `displayName=Nguyen+An` trong body | `formParameters(...)` |
| Multipart part | `name="photo"` trong multipart body | `requestParts(...)` |
| JSON request body field | `{"name":"An"}` | `requestFields(...)` |

Sử dụng đúng API giúp snippet có tiêu đề, vị trí và ngữ nghĩa chính xác.

## 8. Ví dụ hai operation hoàn chỉnh trong MockMvc

### 8.1. Operation nhận URL-encoded form

Controller:

```java
@PostMapping(
    path = "/api/preferences",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ResponseEntity<Void> updatePreferences(
        @RequestParam String displayName,
        @RequestParam(defaultValue = "false") boolean newsletter) {
    return ResponseEntity.noContent().build();
}
```

Test và snippet:

```java
@Test
void documentUrlEncodedForm() throws Exception {
    mockMvc.perform(post("/api/preferences")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("displayName", "Nguyen An")
            .param("newsletter", "true"))
        .andExpect(status().isNoContent())
        .andDo(document("preferences-update",
            formParameters(
                parameterWithName("displayName")
                    .description("Tên hiển thị"),
                parameterWithName("newsletter")
                    .description("Đăng ký nhận bản tin")
            )
        ));
}
```

Snippet sinh ra:

```text
build/generated-snippets/preferences-update/form-parameters.adoc
```

### 8.2. Operation nhận multipart file và text field

Controller:

```java
@PostMapping(
    path = "/api/profile/photo",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> uploadPhoto(
        @RequestParam("displayName") String displayName,
        @RequestPart("photo") MultipartFile photo) {
    return ResponseEntity.noContent().build();
}
```

Test và snippet:

```java
@Test
void documentMultipartForm() throws Exception {
    MockMultipartFile photo = new MockMultipartFile(
            "photo",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes
    );

    MockPart displayName = new MockPart(
            "displayName",
            "Nguyen An".getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/profile/photo")
            .file(photo)
            .part(displayName))
        .andExpect(status().isNoContent())
        .andDo(document("profile-photo-upload",
            requestParts(
                partWithName("displayName")
                    .description("Tên hiển thị"),
                partWithName("photo")
                    .description("Ảnh đại diện")
            )
        ));
}
```

Snippet sinh ra:

```text
build/generated-snippets/profile-photo-upload/request-parts.adoc
```

Hai operation có thể cùng dùng `@RequestParam` ở controller, nhưng test/documentation dùng snippet khác vì request có Content-Type và cấu trúc body khác nhau.

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient với URL-encoded form

Dùng `BodyInserters.fromFormData(...)` để dựng form body:

```java
webTestClient.post()
    .uri("/api/preferences")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("displayName", "Nguyen An")
        .with("newsletter", "true"))
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(document("preferences-update",
        formParameters(
            parameterWithName("displayName").description("Tên hiển thị"),
            parameterWithName("newsletter").description("Đăng ký nhận bản tin")
        )
    ));
```

### 9.2. WebTestClient với multipart

Dùng `BodyInserters.fromMultipartData(...)`:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("displayName", "Nguyen An");
parts.add("photo", imageResource);

webTestClient.post()
    .uri("/api/profile/photo")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(document("profile-photo-upload",
        requestParts(
            partWithName("displayName").description("Tên hiển thị"),
            partWithName("photo").description("Ảnh đại diện")
        )
    ));
```

### 9.3. REST Assured

URL-encoded form:

```java
given(this.spec)
    .filter(document("preferences-update",
        formParameters(
            parameterWithName("displayName").description("Tên hiển thị"),
            parameterWithName("newsletter").description("Đăng ký bản tin")
        )))
    .formParam("displayName", "Nguyen An")
    .formParam("newsletter", "true")
    .when()
    .post("/api/preferences")
    .then()
    .statusCode(204);
```

Multipart:

```java
given(this.spec)
    .filter(document("profile-photo-upload",
        requestParts(
            partWithName("displayName").description("Tên hiển thị"),
            partWithName("photo").description("Ảnh đại diện")
        )))
    .multiPart("displayName", "Nguyen An")
    .multiPart("photo", imageFile, "image/png")
    .when()
    .post("/api/profile/photo")
    .then()
    .statusCode(204);
```

Cú pháp chi tiết của multipart builder tùy overload và phiên bản REST Assured. Điều quan trọng là Content-Type tổng thể và cấu trúc body cuối cùng phải đúng dạng contract.

## 10. Optional, ignored và relaxed

Cả `formParameters(...)` và `requestParts(...)` đều hỗ trợ quản lý descriptor:

- `.optional()` cho phép parameter/part được mô tả vắng mặt trong request mẫu.
- `.ignored()` nhận diện parameter/part nhưng không hiển thị trong snippet.
- `relaxedFormParameters(...)` cho phép form parameter chưa mô tả.
- `relaxedRequestParts(...)` cho phép multipart part chưa mô tả.

Ví dụ:

```java
formParameters(
    parameterWithName("displayName").description("Tên hiển thị"),
    parameterWithName("referralCode")
        .description("Mã giới thiệu")
        .optional()
);
```

Multipart tương ứng:

```java
requestParts(
    partWithName("photo").description("Ảnh đại diện"),
    partWithName("caption")
        .description("Chú thích ảnh")
        .optional()
);
```

Không dùng `.optional()` để làm cho server chấp nhận thiếu dữ liệu. Đó là quyết định contract và validation của endpoint. REST Docs chỉ kiểm tra request mẫu đang được dùng để tạo snippet.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `requestParts(...)` cho URL-encoded body | Nhầm form field với multipart part | Dùng `formParameters(...)` |
| Dùng `formParameters(...)` cho file upload | File cần cấu trúc multipart | Dùng `requestParts(...)` |
| Text field trong multipart được bind bằng `@RequestParam`, nên tưởng nó là URL-encoded form | Nhầm cách bind ở controller với biểu diễn trên wire | Xem Content-Type; multipart part vẫn là part |
| JSON metadata bị bind sai kiểu | Dùng `@RequestParam` với object phức tạp hoặc Content-Type part không phù hợp | Dùng `@RequestPart` và `application/json` |
| Dùng `fieldWithPath(...)` cho form parameter | Dùng nhầm descriptor payload JSON | Dùng `parameterWithName(...)` |
| Dùng `partWithName(...)` cho query parameter | Nhầm query string với multipart | Dùng `queryParameters(...)` |
| Snippet báo parameter/part thiếu | Descriptor required nhưng request mẫu không gửi | Sửa fixture hoặc `.optional()` theo contract |
| Snippet báo parameter/part dư | Strict mode gặp giá trị chưa khai báo | Bổ sung descriptor, ignore có chủ đích hoặc relaxed theo contract |
| Chọn snippet theo annotation controller | Bỏ qua cấu trúc HTTP thực tế | Chọn theo Content-Type và vị trí dữ liệu trên wire |

## 12. Asciidoctor và build/CI

Có thể include form parameter và multipart part trong cùng tài liệu API:

```adoc
= Profile API
:toc: left

== Cập nhật tùy chọn

include::{snippets}/preferences-update/form-parameters.adoc[]

== Upload ảnh đại diện

include::{snippets}/profile-photo-upload/request-parts.adoc[]
```

Với Gradle và plugin Asciidoctor đã cấu hình, task tài liệu nên phụ thuộc test tạo snippets:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Luồng CI:

```text
HTTP tests
   |
   +--> application/x-www-form-urlencoded
   |       |
   |       +--> formParameters(...)
   |
   +--> multipart/form-data
           |
           +--> requestParts(...)
   |
   v
Generated snippets
   |
   v
Asciidoctor / bước xuất Markdown
   |
   v
Kiểm tra và xuất bản tài liệu
```

Nếu thay form URL-encoded thành multipart để hỗ trợ file upload, cần cập nhật controller consumes, cách dựng request trong test, descriptor snippet và tài liệu Asciidoctor đồng bộ. Không giữ `form-parameters.adoc` cũ rồi trình bày như thể nó mô tả multipart request mới.

Spring REST Docs thường sinh snippet AsciiDoc. Muốn xuất Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định có snippet `.md`.

## 13. Bài thực hành

Dùng hai endpoint mẫu trong bài:

1. Tạo `POST /api/preferences` với Content-Type `application/x-www-form-urlencoded`. Dùng `formParameters(...)` để mô tả `displayName` và `newsletter`.
2. Thêm `referralCode` optional; kiểm tra request có và không có parameter.
3. Tạo `POST /api/profile/photo` với `multipart/form-data`, gồm text part `displayName` và file part `photo`.
4. Dùng `requestParts(...)` để mô tả cả hai part. Xác nhận dù controller dùng `@RequestParam` cho `displayName`, wire format vẫn là multipart.
5. Thêm JSON part `metadata`, bind bằng `@RequestPart`, rồi dùng `requestPartFields(...)` để mô tả field.
6. Thử đổi Content-Type tổng thể từ multipart sang URL-encoded và quan sát endpoint không còn nhận được file như cũ.
7. Include cả `form-parameters.adoc` và `request-parts.adoc` vào Asciidoctor.
8. Chạy test tài liệu hóa và kiểm tra CI phát hiện khi parameter/part mới chưa có descriptor.

### Câu hỏi tự đánh giá

- `formParameters(...)` mô tả loại request nào?
- `requestParts(...)` mô tả thành phần nào của multipart body?
- Một text part trong multipart có thể được bind bằng `@RequestParam` không?
- Vì sao `@RequestParam` không có nghĩa request chắc chắn là URL-encoded form?
- Khi nào `@RequestPart` phù hợp hơn `@RequestParam`?
- `formParameters`, `queryParameters` và `requestParts` khác nhau ở vị trí truyền dữ liệu nào?
- Nếu đổi endpoint từ URL-encoded form sang multipart, những phần nào của test và tài liệu phải cập nhật?

**Ghi nhớ:** Chọn snippet theo cấu trúc HTTP trên wire. `formParameters(...)` dành cho form parameter; `requestParts(...)` dành cho các phần của `multipart/form-data`. Một multipart text part có thể được Spring bind bằng `@RequestParam`, nhưng nó vẫn là part của multipart request. Với nội dung JSON/XML cần message converter theo Content-Type, `@RequestPart` thường là lựa chọn phù hợp.

## Tài liệu tham khảo

- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `formParameters`, `relaxedFormParameters`, `requestParts`, `partWithName` và các parameter snippet.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): tài liệu hóa multipart request và request part payload.
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): cách Spring MVC truy cập form field và multipart file.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): khác biệt chuyển đổi giữa `@RequestPart` và `@RequestParam`.
