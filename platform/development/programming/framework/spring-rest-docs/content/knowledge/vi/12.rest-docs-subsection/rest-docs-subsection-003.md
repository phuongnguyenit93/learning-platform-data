# subsectionWithPath cho object con trong Spring REST Docs

## 1. Bối cảnh và mục tiêu

**Spring REST Docs** giúp tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Các snippet về request, response, payload, tham số và header được sinh khi test chạy thành công, sau đó được ghép vào tài liệu Asciidoctor/Markdown trong build và CI.

Bài học thuộc nhóm **Subsection**, tập trung vào API `subsectionWithPath(...)` khi payload JSON chứa **object con**. Đây là lựa chọn hữu ích nếu muốn bảng mô tả payload nêu ý nghĩa của toàn bộ object thay vì liệt kê từng field ở mọi cấp.

Ví dụ endpoint trả thông tin người dùng gồm `id`, `enabled`, `roles` và một object `profile` chứa nhiều nhóm dữ liệu. Ở trang tổng quan API, ta chỉ cần giải thích `profile` là gì; phần chi tiết có thể được mô tả riêng hoặc không, tùy hợp đồng API.

Sau khi học xong, bạn có thể:

- Dùng `subsectionWithPath("profile")` trong `responseFields(...)` và `requestFields(...)` để document một object con.
- Hiểu chính xác phạm vi các field được xem là đã document khi dùng descriptor này.
- Phân biệt `subsectionWithPath(...)` với `fieldWithPath(...)` và `beneathPath(...)`.
- Viết test MockMvc sinh snippet tổng quan và snippet chi tiết, cũng như xác định khi nào schema thay đổi làm test thất bại.
- Đưa snippet vào tài liệu Asciidoctor và ràng buộc bước tạo tài liệu với kiểm thử trong build/CI.

## 2. Object con trong payload JSON

Giả sử `GET /users/usr-42` trả về response:

```json
{
  "id": "usr-42",
  "enabled": true,
  "profile": {
    "displayName": "Lan Nguyen",
    "contact": {
      "email": "lan@example.test",
      "phone": "+84900000000"
    },
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "roles": ["READER"]
}
```

Ở cấp gốc, payload có bốn field: `id`, `enabled`, `profile` và `roles`. Nhưng `profile` là một **object con** với các field lồng nhau:

```text
response body
├── id
├── enabled
├── profile
│   ├── displayName
│   ├── contact
│   │   ├── email
│   │   └── phone
│   └── address
│       ├── city
│       └── country
└── roles
```

Nếu muốn bảng tổng quan chỉ hiển thị bốn hàng, có thể khai báo:

```java
responseFields(
    fieldWithPath("id")
        .description("Mã người dùng"),
    fieldWithPath("enabled")
        .description("Trạng thái kích hoạt tài khoản"),
    subsectionWithPath("profile")
        .description("Thông tin hồ sơ của người dùng"),
    fieldWithPath("roles")
        .description("Danh sách vai trò")
)
```

Với `subsectionWithPath("profile")`, Spring REST Docs xem **toàn bộ nhánh `profile` và các field bên dưới** là đã được document trong **snippet này**. Vì vậy bảng tổng quan có một dòng mô tả object `profile`, thay vì bắt buộc thêm tất cả `profile.displayName`, `profile.contact.email`, `profile.address.city`, v.v.

Cú pháp cơ bản:

```java
subsectionWithPath("duongDanDenObject")
    .description("Ý nghĩa của toàn bộ object")
```

Với object nằm sâu hơn, đường dẫn có thể là `subsectionWithPath("profile.address")` nếu bảng đang document trực tiếp payload từ root. Đường dẫn sử dụng cú pháp JSON path của REST Docs: dấu chấm phân tách các cấp object; với các key đặc biệt cần áp dụng cú pháp bracket tương ứng.

## 3. Ví dụ hoàn chỉnh với MockMvc

Đoạn mã sau dùng JUnit 5, Spring MVC Test và Spring REST Docs. Controller thử nghiệm trả JSON cố định để tài liệu không phụ thuộc vào database hay thời điểm chạy. Trong dự án thực tế, thay controller mẫu bằng controller và fixture của ứng dụng.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class UserProfileDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleUserController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentProfileAsSubsection() throws Exception {
        mockMvc.perform(get("/users/{id}", "usr-42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.profile").isMap())
                .andExpect(jsonPath("$.profile.contact.email")
                        .value("lan@example.test"))
                .andDo(document("users-get-profile-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã người dùng"),
                                fieldWithPath("enabled")
                                        .description("Tài khoản đang kích hoạt"),
                                subsectionWithPath("profile")
                                        .description("Thông tin hồ sơ"),
                                fieldWithPath("roles")
                                        .description("Danh sách vai trò")
                        )
                ));
    }

    @RestController
    static class SampleUserController {

        @GetMapping(
                value = "/users/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<String> getUser(@PathVariable String id) {
            if (!"usr-42".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "usr-42",
                      "enabled": true,
                      "profile": {
                        "displayName": "Lan Nguyen",
                        "contact": {
                          "email": "lan@example.test",
                          "phone": "+84900000000"
                        },
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        }
                      },
                      "roles": ["READER"]
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json);
        }
    }
}
```

Đoạn mã sử dụng Java 17+ (text block) và cần các thư viện kiểm thử phù hợp trên test classpath. `RestDocumentationExtension` quản lý context của REST Docs, `documentationConfiguration(restDocumentation)` gắn REST Docs vào MockMvc, còn `document("users-get-profile-overview", ...)` sinh snippet khi HTTP exchange thỏa các assertion.

### Tại sao vẫn cần assertion khi đã có REST Docs?

`responseFields(...)` kiểm tra các descriptor của tài liệu; nó không thay thế mọi kiểm tra hành vi nghiệp vụ. Trong ví dụ:

- `status().isOk()` bảo đảm endpoint trả HTTP 200.
- `jsonPath("$.profile").isMap()` kiểm tra `profile` thực sự là object JSON.
- `jsonPath("$.profile.contact.email")` bảo đảm giá trị quan trọng phù hợp fixture.
- `responseFields(...)` bảo đảm các field cấp gốc đã khai báo có mặt và không xuất hiện field cấp gốc ngoài phạm vi document trong chế độ strict.

Đặc biệt, việc ghi `subsectionWithPath("profile")` **không có nghĩa** REST Docs đang xác minh từng field con theo một schema đầy đủ. Nếu contract cần bảo đảm email, địa chỉ và các quy tắc định dạng, hãy thêm assertion nghiệp vụ và/hoặc một snippet chi tiết riêng.

## 4. Snippet tổng quan được sinh ra như thế nào?

Sau khi test chạy thành công, với identifier `users-get-profile-overview`, thư mục sinh snippet mặc định cho Gradle thường là:

```text
build/generated-snippets/
└── users-get-profile-overview/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    └── response-fields.adoc
```

Các tệp mặc định phụ thuộc vào cấu hình snippet và những thông tin có trong HTTP exchange. Tệp quan trọng nhất của bài là `response-fields.adoc`, do lời gọi `responseFields(...)` tạo ra. Về mặt ý nghĩa, bảng này mô tả:

| Field | Kiểu JSON | Mô tả |
| --- | --- | --- |
| `id` | String | Mã người dùng |
| `enabled` | Boolean | Tài khoản đang kích hoạt |
| `profile` | Object | Thông tin hồ sơ |
| `roles` | Array | Danh sách vai trò |

Bảng chỉ là minh họa nội dung; kiểu hiển thị, tiêu đề cột và cách render thực tế tùy template REST Docs đang dùng.

**Điểm cần nhớ:** `subsectionWithPath("profile")` không tự sinh `response-fields-profile.adoc` hoặc `response-body-profile.adoc`. Nó tạo **một hàng** trong bảng `response-fields.adoc` của payload hiện tại và bao phủ các field con khi REST Docs kiểm tra tính đầy đủ của bảng đó.

## 5. Strict documentation: field mới được xử lý thế nào?

`responseFields(...)` mặc định là strict: một field xuất hiện trong payload mà không được document sẽ làm test thất bại, trừ khi field đó thuộc một subsection đã được bao phủ hoặc có cơ chế khai báo phù hợp.

Dựa trên ví dụ `users-get-profile-overview`:

| Thay đổi response | Kết quả của bảng tổng quan strict | Lý do |
| --- | --- | --- |
| Thêm `profile.nickname` | Thường vẫn pass | `profile` và các hậu duệ đã được `subsectionWithPath("profile")` bao phủ. |
| Thêm `profile.contact.telegram` | Thường vẫn pass | Đây vẫn là field nằm trong nhánh `profile`. |
| Thêm `createdAt` ở root | Fail khi chưa document | `createdAt` là field mới ở cấp gốc, không thuộc subsection đã mô tả. |
| Xóa hoàn toàn `profile` | Fail nếu descriptor vẫn bắt buộc | `profile` được mô tả nhưng không xuất hiện. |
| Xóa `profile.address.country` | Bảng tổng quan vẫn có thể pass | Bảng tổng quan không khai báo riêng `country`. |
| Đổi `profile` từ object sang string | Không nên chỉ dựa vào descriptor | Kết hợp assertion `jsonPath("$.profile").isMap()` để bắt lỗi kiểu JSON. |

Tính strict ở đây có **ranh giới kiểm tra**. Bảng tổng quan bảo vệ các đường dẫn cấp gốc được khai báo, nhưng chủ ý không kiểm soát toàn bộ cấu trúc bên trong `profile`. Đó là lựa chọn thiết kế tài liệu: dễ đọc hơn, đổi lại phạm vi phát hiện thay đổi field con hẹp hơn.

### Một lỗi dễ mắc

Giả sử API thêm field `createdAt` ngoài `profile`. Nếu dùng:

```java
responseFields(
    fieldWithPath("id").description("Mã người dùng"),
    subsectionWithPath("profile").description("Thông tin hồ sơ")
)
```

thì bảng vẫn thiếu cả `enabled`, `roles` và `createdAt` ở root; trong chế độ strict, test thất bại. `subsectionWithPath("profile")` **chỉ** bao phủ `profile`, không bỏ qua những field ở vị trí khác trong JSON.

## 6. Khi muốn kiểm tra chi tiết object con: thêm beneathPath

Đây là khác biệt cốt lõi giữa hai API:

| API | Vai trò | Cách dùng điển hình |
| --- | --- | --- |
| `subsectionWithPath("profile")` | Descriptor bao phủ một object và các hậu duệ trong bảng field hiện tại | `responseFields(subsectionWithPath("profile").description(...))` |
| `beneathPath("profile")` | Extractor chọn subtree để tạo snippet riêng | `responseFields(beneathPath("profile"), ...)` hoặc `responseBody(beneathPath("profile"))` |

Giả sử muốn giữ bảng tổng quan ngắn nhưng vẫn kiểm tra từng trường của `profile`. Thêm **snippet thứ hai** vào cùng lời gọi `document(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

// Bên trong document("users-get-profile-overview", ...):
responseFields(
    beneathPath("profile").withSubsectionId("profile-details"),
    fieldWithPath("displayName")
        .description("Tên hiển thị"),
    fieldWithPath("contact.email")
        .description("Email liên hệ"),
    fieldWithPath("contact.phone")
        .optional()
        .description("Số điện thoại liên hệ nếu có"),
    fieldWithPath("address.city")
        .description("Thành phố"),
    fieldWithPath("address.country")
        .description("Mã quốc gia")
)
```

Ví dụ này là một **đoạn handler bổ sung**: đặt nó sau `responseFields(...)` tổng quan, ngăn cách bằng dấu phẩy trong đối số của `document(...)`.

Khi đó REST Docs sinh thêm `response-fields-profile-details.adoc`. Các đường dẫn trong snippet chi tiết tính **tương đối** từ `profile`: dùng `contact.email`, không dùng `profile.contact.email`. Nếu `profile.nickname` xuất hiện mà chưa được document, bảng chi tiết strict sẽ thất bại; bảng tổng quan với `subsectionWithPath("profile")` vẫn có thể hợp lệ.

Có thể sinh riêng một phần response body bằng handler khác:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;

// Bên trong document("users-get-profile-overview", ...):
responseBody(
    beneathPath("profile").withSubsectionId("profile-details")
)
```

Snippet body có tên `response-body-profile-details.adoc`, phản ánh phần JSON được trích. Chỉ gọi `responseBody(...)` không có nghĩa các field của subsection đã được mô tả và kiểm tra đầy đủ; để bảo vệ schema chi tiết, sử dụng thêm `responseFields(beneathPath(...), ...)`.

## 7. Dùng subsectionWithPath với object sâu hơn

Nếu muốn mô tả riêng `address` mà vẫn liệt kê chi tiết tên và liên hệ, có thể document trực tiếp từ root:

```java
responseFields(
    fieldWithPath("id")
        .description("Mã người dùng"),
    fieldWithPath("enabled")
        .description("Trạng thái kích hoạt"),
    fieldWithPath("profile.displayName")
        .description("Tên hiển thị"),
    fieldWithPath("profile.contact.email")
        .description("Email liên hệ"),
    fieldWithPath("profile.contact.phone")
        .description("Điện thoại liên hệ"),
    subsectionWithPath("profile.address")
        .description("Địa chỉ hồ sơ"),
    fieldWithPath("roles")
        .description("Danh sách vai trò")
)
```

Trong bảng này, `profile.address.city` và `profile.address.country` nằm dưới `profile.address` nên không cần mô tả riêng trong snippet hiện tại. Ngược lại, `profile.contact.email` và `profile.contact.phone` phải có descriptor vì ta **không** bao phủ cả `profile.contact` bằng một subsection descriptor.

Một nguyên tắc thực hành: chọn **ranh giới tài liệu** ở nhánh có ý nghĩa nghiệp vụ. Tránh dùng `subsectionWithPath("profile")` chỉ để test qua khi chưa biết cấu trúc `profile`. Nếu nhóm client cần từng thuộc tính để tích hợp, nên có bảng chi tiết và test tương ứng.

## 8. Với request payload, nguyên tắc vẫn tương tự

`subsectionWithPath(...)` không dành riêng cho response. Ví dụ `POST /users` nhận request JSON:

```json
{
  "username": "lan.nguyen",
  "profile": {
    "displayName": "Lan Nguyen",
    "preferences": {
      "language": "vi",
      "timezone": "Asia/Ho_Chi_Minh"
    }
  }
}
```

Trong handler tài liệu của kiểm thử request, có thể dùng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("username")
        .description("Tên đăng nhập"),
    subsectionWithPath("profile")
        .description("Hồ sơ khởi tạo của người dùng")
)
```

Handler tạo `request-fields.adoc` với hai hàng `username` và `profile`. Đây vẫn là bảng strict cho request cấp gốc, nhưng các field con `profile.displayName` và `profile.preferences.language` được bao phủ bởi `subsectionWithPath("profile")`. Khi cần giải thích các field con cho người tạo client, bổ sung `requestFields(beneathPath("profile"), ...)` trong test có `profile`.

Các công cụ MockMvc, WebTestClient và REST Assured đều có thể dùng descriptor từ `PayloadDocumentation`; điểm khác nằm ở cách gắn `document(...)` vào exchange HTTP:

- **MockMvc:** `.andDo(document("id", requestFields(...)))` hoặc `.andDo(document("id", responseFields(...)))`.
- **WebTestClient:** `.expectBody().consumeWith(document("id", responseFields(...)))`.
- **REST Assured:** `.filter(document("id", responseFields(...)))` trong phần chuẩn bị HTTP request.

Trước khi chạy các ví dụ này, mỗi framework phải được cấu hình extension/configurer hoặc filter của Spring REST Docs theo hướng dẫn chính thức.

## 9. optional, ignored, relaxed và kiểu dữ liệu

### Object có thể vắng mặt

Nếu hợp đồng API cho phép response không chứa `profile`, có thể đánh dấu:

```java
subsectionWithPath("profile")
    .optional()
    .description("Hồ sơ người dùng, nếu đã hoàn thiện")
```

`optional()` cho phép field được document vắng mặt. Cần có **test cho biến thể không có object**, để xác nhận hợp đồng hành vi. Nếu sử dụng thêm `beneathPath("profile")` trong cùng test, extractor cần nhánh hiện diện để trích phần dữ liệu. Vì vậy với response không có `profile`, không gắn extractor này; hãy tạo snippet subsection trong test có dữ liệu.

### Field cố ý không đưa vào bảng

`ignored()` có thể dùng cho descriptor của một field đã biết nhưng không muốn hiện trong tài liệu. Ví dụ, nếu một field nội bộ có mặt trong payload test và thật sự không thuộc tài liệu công khai, có thể chọn descriptor ignored có chủ đích. Không sử dụng `ignored()` để che thay đổi schema mà nhóm phát triển chưa hiểu.

### Chế độ relaxed

`relaxedResponseFields(...)` (hoặc `relaxedRequestFields(...)`) bỏ qua các field chưa được document. Chế độ này hữu ích với tài liệu chọn lọc, nhưng nếu mục đích là phát hiện thay đổi payload ngoài dự kiến, hãy ưu tiên bảng strict kèm `subsectionWithPath(...)` ở đúng nhánh cần tóm tắt.

### Kiểu của object trong bảng

Trong trường hợp muốn hiển thị tường minh loại object, có thể khai báo:

```java
import org.springframework.restdocs.payload.JsonFieldType;

subsectionWithPath("profile")
    .type(JsonFieldType.OBJECT)
    .description("Thông tin hồ sơ")
```

`type(...)` cung cấp kiểu dùng trong tài liệu. Nếu cần chắc chắn runtime trả **JSON object** theo contract, hãy kiểm tra thêm bằng JSON assertion như `jsonPath("$.profile").isMap()` trong MockMvc. Không nên xem mô tả kiểu ở bảng là thay thế cho một assertion kiểm thử dữ liệu thực.

## 10. Ghép snippet vào tài liệu và quy trình build

Với identifier ở mục 3, tài liệu Asciidoctor có thể đưa bảng tổng quan vào:

```asciidoc
= API người dùng
:toc: left

== GET /users/{id}

Trả về trạng thái tài khoản và hồ sơ người dùng.

=== HTTP response

include::{snippets}/users-get-profile-overview/http-response.adoc[]

=== Các trường response tổng quan

include::{snippets}/users-get-profile-overview/response-fields.adoc[]
```

Nếu test đã thêm handler `responseFields(beneathPath("profile").withSubsectionId("profile-details"), ...)`, có thể bổ sung:

```asciidoc
=== Các trường trong profile

include::{snippets}/users-get-profile-overview/response-fields-profile-details.adoc[]
```

Để bảo đảm snippet được sinh trước khi Asciidoctor biên soạn, có thể liên kết task trong Gradle (Groovy DSL; giả định dự án đã cài plugin Asciidoctor, dependency Spring REST Docs và cấu hình test):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Sau đó chạy:

```bash
./gradlew clean test asciidoctor
```

Khi đưa vào CI, nên để test thất bại chặn bước sinh và phát hành tài liệu, tránh công bố snippet không còn tương ứng với API. Đường dẫn output cần thống nhất giữa REST Docs và cấu hình Asciidoctor; với Maven, thư mục thông dụng là `target/generated-snippets`.

Nếu dự án dựng tài liệu Markdown, cần dùng template/snippet và cách nhúng phù hợp với pipeline Markdown đang chọn, thay cho lệnh `include::[]` của Asciidoctor.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test báo có field chưa document | Có field mới ở ngoài nhánh `profile`, hoặc thiếu descriptor cấp gốc | Kiểm tra path trong payload thật và thêm descriptor phù hợp. |
| Test vẫn pass khi thêm field trong `profile` | `subsectionWithPath("profile")` bao phủ các hậu duệ | Thêm bảng strict `responseFields(beneathPath("profile"), ...)` khi cần kiểm chứng cấu trúc con. |
| Test báo path không tìm thấy | Nhầm chữ hoa/chữ thường hoặc khai báo path không đúng cấp | Đối chiếu JSON thực tế và đường dẫn descriptor. |
| Bảng chi tiết báo thiếu `profile.contact.email` | Dùng path có tiền tố `profile` dù đã trích nhánh `profile` | Dùng `contact.email` khi descriptor nằm trong `beneathPath("profile")`. |
| Không sinh tệp `response-fields-profile-details.adoc` | Chỉ khai báo `subsectionWithPath`, chưa thêm handler `beneathPath` | Thêm snippet chi tiết và chạy test. |
| Test trả string thay cho object `profile` | Đổi kiểu dữ liệu ngoài mong đợi; chỉ document type chưa bảo đảm contract | Thêm JSON assertion để kiểm tra object và dữ liệu quan trọng. |
| Tài liệu Asciidoctor báo thiếu snippet | Test chưa sinh snippet, sai identifier hoặc sai path | Kiểm tra thứ tự build, thư mục snippets và tên include. |

## 12. Bài thực hành

Từ `UserProfileDocumentationTest` ở mục 3, hãy thực hiện:

1. **Thử ranh giới strict:** thêm `profile.nickname` vào JSON nhưng giữ nguyên descriptor. Xác minh bảng tổng quan với `subsectionWithPath("profile")` vẫn được sinh. Sau đó thêm `createdAt` ở root; quan sát kết quả test strict.
2. **Document object sâu:** thay `subsectionWithPath("profile")` bằng ba descriptor cho `profile.displayName`, `profile.contact` và `profile.address` (hai descriptor cuối dùng `subsectionWithPath`). Chạy lại và quan sát bảng tổng quan chi tiết hơn.
3. **Tạo bảng chi tiết:** giữ bảng tổng quan ban đầu, đồng thời thêm `responseFields(beneathPath("profile").withSubsectionId("profile-details"), ...)`. Thêm `profile.nickname` và kiểm tra bảng chi tiết strict phát hiện field mới.
4. **Tùy chọn:** cho response thiếu `profile.contact.phone` và đánh dấu descriptor tương ứng trong bảng chi tiết bằng `optional()`. Kiểm tra test vẫn pass; thử bỏ `optional()` để thấy sự khác biệt.
5. **Tài liệu build:** nhúng `response-fields.adoc` và `response-fields-profile-details.adoc` vào Asciidoctor, sau đó chạy `./gradlew clean test asciidoctor` trong môi trường đã cấu hình.

**Tiêu chí hoàn thành:** bạn chỉ ra được chính xác những path mà `subsectionWithPath("profile")` bao phủ, giải thích được vì sao field mới trong `profile` và field mới ở root có thể dẫn đến kết quả kiểm thử khác nhau, đồng thời biết kết hợp bảng tổng quan với bảng chi tiết khi client cần schema đầy đủ.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): cách document field, subsection, path và kiểm tra tính đầy đủ của payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): thiết lập MockMvc, WebTestClient, REST Assured, sinh snippet và tích hợp Asciidoctor/build.

