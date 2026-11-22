# Document subsection bên trong request part với Spring REST Docs

## 1. Payload multipart có thể chứa object lồng nhau

Một API tạo hồ sơ có thể nhận part `metadata` dạng JSON. Ngoài các field đơn giản như `name` và `description`, payload còn có object `owner`, object `location` và mảng `contacts`:

```http
POST /api/profiles HTTP/1.1
Content-Type: multipart/form-data; boundary=----ProfileBoundary

------ProfileBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "name": "Engineering team",
  "description": "Nhóm phát triển nền tảng",
  "owner": {
    "id": "USR-42",
    "displayName": "Platform Team",
    "contact": {
      "email": "platform@example.test",
      "phone": "+84-28-5550-0100"
    }
  },
  "location": {
    "country": "VN",
    "city": "Ho Chi Minh City"
  },
  "contacts": [
    {"type": "SUPPORT", "value": "support@example.test"},
    {"type": "SALES", "value": "sales@example.test"}
  ]
}
------ProfileBoundary--
```

Có hai cách thường dùng để giải thích cấu trúc `owner`:

- Liệt kê riêng `owner.id`, `owner.displayName`, `owner.contact.email` và `owner.contact.phone`. Cách này phù hợp khi người đọc cần biết chi tiết từng field.
- Mô tả toàn bộ `owner` như một **subsection**. Cách này phù hợp khi object con có cấu trúc riêng, được giải thích ở schema hoặc đoạn tài liệu khác.

Spring REST Docs hỗ trợ cả hai cách thông qua các `FieldDescriptor` trong `requestPartFields(...)`. Bài này thuộc chương **Part payload** của module **SPRING_REST_DOCS**: dùng kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured để sinh snippet multipart có thể kiểm chứng, sau đó ghép vào Asciidoctor/Markdown và build/CI.

Sau bài học, bạn có thể:

1. Hiểu subsection là object hoặc nhóm field lồng nhau trong payload của một part.
2. Dùng `subsectionWithPath(...)` trong `requestPartFields(...)`.
3. Chọn giữa document một subsection và liệt kê chi tiết các field con.
4. Mô tả subsection lồng nhiều cấp, mảng object và subsection tùy chọn.
5. Tạo snippet từ MockMvc test và đưa snippet vào trang tài liệu API.

## 2. Ôn lại phạm vi requestPartFields(...)

Một multipart request có thể gồm nhiều part. Mỗi part có tên, header và body riêng:

| API | Phạm vi |
| --- | --- |
| `requestParts(...)` | Tên và mô tả các part của multipart request |
| `requestPartBody("metadata")` | Body mẫu của part metadata |
| `requestPartFields("metadata", ...)` | Cấu trúc field trong payload của part metadata |

Ví dụ:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("owner.id").description("Mã người sở hữu"),
    fieldWithPath("owner.displayName").description("Tên hiển thị của người sở hữu")
)
```

Tên part truyền vào `requestPartFields("metadata", ...)` xác định payload cần phân tích. Các descriptor sau đó dùng đường dẫn tương đối với JSON body của chính part ấy. `owner.id` có nghĩa là field `id` bên trong object `owner`, không phải field của request body chính.

Nếu part `metadata` không chứa JSON hợp lệ theo content type mà Spring REST Docs xử lý, snippet field không thể phân tích cấu trúc mong muốn. Vì vậy, test phải gửi part với body và Content-Type khớp contract, thường là `application/json`.

## 3. Subsection là gì?

Subsection là một phần con có cấu trúc bên trong payload. Ví dụ:

```json
{
  "name": "Engineering team",
  "owner": {
    "id": "USR-42",
    "displayName": "Platform Team"
  }
}
```

Có thể document `owner` theo hai cách.

**Mở rộng field con:**

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("owner.id").description("Mã người sở hữu"),
    fieldWithPath("owner.displayName").description("Tên hiển thị")
)
```

**Document subsection như một đơn vị:**

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    subsectionWithPath("owner")
        .description("Thông tin người sở hữu hồ sơ")
)
```

`subsectionWithPath("owner")` mô tả cả nhóm con như một mục trong bảng field. Nó không tạo một bảng đệ quy chứa mọi field con. Nếu người đọc cần biết chi tiết `id`, `displayName` hoặc `contact`, hãy liệt kê các field đó bằng descriptor riêng hoặc cung cấp schema chi tiết ở phần tài liệu khác.

## 4. Cú pháp subsectionWithPath(...)

`subsectionWithPath(...)` thuộc `org.springframework.restdocs.payload.PayloadDocumentation` và trả về một `SubsectionDescriptor`, là một loại field descriptor:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("owner")
    .description("Thông tin người sở hữu")
```

Có thể dùng API này với `requestPartFields(...)`:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    subsectionWithPath("owner").description("Thông tin người sở hữu"),
    subsectionWithPath("location").description("Địa chỉ của hồ sơ")
)
```

Các đường dẫn subsection dùng cùng quy ước JSON path với `fieldWithPath(...)`:

| Payload path | Ý nghĩa |
| --- | --- |
| `owner` | Object owner ở cấp đầu |
| `owner.contact` | Object contact nằm trong owner |
| `location` | Object location ở cấp đầu |
| `contacts[]` | Các phần tử trong mảng contacts |
| `items[].product` | Object product bên trong từng phần tử của mảng items |

Đường dẫn phải tồn tại trong body part được kiểm thử, trừ khi descriptor được đánh dấu optional. Dùng đường dẫn chính xác theo JSON thực tế, bao gồm tên field và vị trí lồng nhau.

### 4.1. Subsection và field descriptor

| API | Khi nào dùng |
| --- | --- |
| `fieldWithPath("owner.id")` | Cần định nghĩa một field cụ thể |
| `subsectionWithPath("owner")` | Muốn gom object con thành một mục |
| `fieldWithPath("contacts[].type")` | Cần định nghĩa field trong từng phần tử mảng |
| `subsectionWithPath("contacts[]")` | Muốn mô tả cấu trúc phần tử mảng như một nhóm |

Không khai báo một subsection để thay thế toàn bộ các field con rồi đồng thời kỳ vọng cùng snippet tự liệt kê chi tiết các field đó. Hãy chọn mức chi tiết phù hợp với độc giả và tránh tạo descriptor chồng lấn cho cùng một phần payload.

## 5. Chọn mức chi tiết phù hợp

Subsection không phải lúc nào cũng là lựa chọn tốt hơn. Tùy cấu trúc và người sử dụng API, có thể chọn:

| Tình huống | Cách document khuyến nghị | Lý do |
| --- | --- | --- |
| Object con có ít field, tất cả đều quan trọng | Liệt kê từng field bằng `fieldWithPath(...)` | Người dùng biết chính xác tên và ý nghĩa |
| Object con lớn hoặc đã có schema riêng | `subsectionWithPath(...)` | Bảng chính gọn và tránh lặp schema |
| Phần con có field nội bộ | Chỉ công bố phần public | Tránh công bố implementation detail |
| Cấu trúc ổn định được nhiều endpoint dùng chung | Subsection kèm tài liệu schema dùng chung | Giảm lặp lại nội dung |
| Phần con thay đổi tùy loại request | Mô tả field và các biến thể | Làm rõ điều kiện xuất hiện |

Một bảng field chỉ có mục `owner` với description “Thông tin người sở hữu” có thể quá tổng quát nếu client cần biết `owner.id` là bắt buộc hay `owner.contact.email` có thể vắng mặt. Trong trường hợp đó, hãy mở rộng subsection hoặc trỏ đến schema được công bố riêng.

## 6. Subsection lồng nhiều cấp

Xét payload:

```json
{
  "name": "Engineering team",
  "owner": {
    "id": "USR-42",
    "profile": {
      "displayName": "Platform Team",
      "department": {
        "code": "ENG",
        "name": "Engineering"
      }
    }
  }
}
```

Có thể document từng cấp:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("owner.id").description("Mã người sở hữu"),
    subsectionWithPath("owner.profile")
        .description("Hồ sơ hiển thị của người sở hữu")
)
```

Trong cách này, `owner.id` được giải thích chi tiết còn `owner.profile` được gom thành subsection. Nếu muốn mở rộng sâu hơn:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("owner.id").description("Mã người sở hữu"),
    fieldWithPath("owner.profile.displayName").description("Tên hiển thị"),
    fieldWithPath("owner.profile.department.code").description("Mã phòng ban"),
    fieldWithPath("owner.profile.department.name").description("Tên phòng ban")
)
```

Hai cách biểu diễn phục vụ hai mục tiêu khác nhau. Nếu đã document `owner.profile` như một subsection, không thêm các descriptor con của nó vào cùng danh sách với kỳ vọng subsection tự mở rộng thành bảng chi tiết. Khi cần cả overview lẫn schema đầy đủ, dùng một đoạn mô tả/schema bổ sung hoặc cấu trúc tài liệu riêng thay vì khai báo đường dẫn chồng lấn.

## 7. Subsection chứa mảng object

JSON part có thể chứa mảng object:

```json
{
  "name": "Engineering team",
  "contacts": [
    {
      "type": "SUPPORT",
      "value": "support@example.test",
      "primary": true
    },
    {
      "type": "SALES",
      "value": "sales@example.test",
      "primary": false
    }
  ]
}
```

Nếu cần document chi tiết từng trường của phần tử:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("contacts[].type").description("Loại địa chỉ liên hệ"),
    fieldWithPath("contacts[].value").description("Giá trị liên hệ"),
    fieldWithPath("contacts[].primary").description("Có phải liên hệ chính không")
)
```

Nếu chỉ cần mô tả rằng `contacts` là danh sách thông tin liên hệ và schema được công bố riêng:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    subsectionWithPath("contacts")
        .description("Danh sách liên hệ; schema phần tử được mô tả trong Contact")
)
```

`contacts` gom cả mảng; `contacts[]` có thể dùng để chỉ phần tử lặp của mảng khi cần mô tả subsection phần tử. Hãy kiểm tra đúng JSON path mà snippet payload hỗ trợ trong phiên bản Spring REST Docs đang dùng và chọn một cách mô tả nhất quán.

## 8. Subsection tùy chọn và giá trị null

Một subsection có thể vắng mặt nếu hợp đồng cho phép. Ví dụ payload:

```json
{
  "name": "Engineering team"
}
```

Mô tả:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    subsectionWithPath("owner")
        .description("Thông tin người sở hữu")
        .optional()
)
```

`optional()` cho phép subsection `owner` không có trong payload test. Nếu `owner` có mặt nhưng giá trị là `null`, đó là trạng thái khác với việc field vắng mặt; hãy quyết định và kiểm thử riêng theo contract. Không mặc định rằng `optional()` có nghĩa mọi trường hợp null, object rỗng hoặc thiếu một vài field con đều hợp lệ.

Nếu `owner` có thể vắng mặt nhưng bên trong `owner`, field `id` bắt buộc khi object xuất hiện, cần mô tả logic này rõ ràng và viết test cho cả hai nhánh:

- Không có `owner`: hợp lệ.
- Có `owner` nhưng thiếu `id`: không hợp lệ.
- Có `owner.id`: hợp lệ nếu các ràng buộc khác được đáp ứng.

## 9. Ví dụ hoàn chỉnh với MockMvc và Spring REST Docs

### 9.1. DTO và controller

Ta dùng part `metadata` chứa object lồng nhau:

```java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

record Owner(String id, String displayName) {}
record Contact(String type, String value) {}
record ProfileMetadata(String name, Owner owner, List<Contact> contacts) {}
record ProfileReceipt(String profileId, String name, String ownerId) {}

@RestController
class ProfileController {

    @PostMapping(
            path = "/api/profiles",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ProfileReceipt create(@RequestPart("metadata") ProfileMetadata metadata) {
        String ownerId = metadata.owner() == null ? null : metadata.owner().id();
        return new ProfileReceipt("PRO-100", metadata.name(), ownerId);
    }
}
```

Controller trên chỉ minh họa việc binding JSON part vào DTO. Hệ thống thực nên đặt validation, authorization và logic lưu hồ sơ trong các thành phần phù hợp.

### 9.2. Tạo multipart part

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "name": "Engineering team",
          "owner": {
            "id": "USR-42",
            "displayName": "Platform Team"
          },
          "contacts": [
            {"type": "SUPPORT", "value": "support@example.test"},
            {"type": "SALES", "value": "sales@example.test"}
          ]
        }
        """.getBytes(StandardCharsets.UTF_8));
```

Part có tên `metadata` và Content-Type `application/json`; body JSON chứa object `owner` cùng mảng `contacts`.

### 9.3. Document subsection trong part

```java
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
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProfilePartSubsectionDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProfileController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsOwnerAndContactsAsSubsections() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "name": "Engineering team",
                  "owner": {
                    "id": "USR-42",
                    "displayName": "Platform Team"
                  },
                  "contacts": [
                    {"type": "SUPPORT", "value": "support@example.test"},
                    {"type": "SALES", "value": "sales@example.test"}
                  ]
                }
                """.getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/profiles").file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.profileId").value("PRO-100"))
                .andExpect(jsonPath("$.name").value("Engineering team"))
                .andExpect(jsonPath("$.ownerId").value("USR-42"))
                .andDo(document("profile-create",
                        requestParts(
                                partWithName("metadata")
                                        .description("Metadata hồ sơ dạng JSON")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("name").description("Tên hồ sơ"),
                                subsectionWithPath("owner")
                                        .description("Thông tin người sở hữu; schema Owner"),
                                subsectionWithPath("contacts")
                                        .description("Danh sách liên hệ; schema Contact")
                        )));
    }
}
```

Trong ví dụ, `requestParts(...)` document part `metadata`; `requestPartFields("metadata", ...)` document `name` và hai subsection `owner`, `contacts`. Assertion xác minh object owner đã được deserialize thành DTO và controller đọc đúng `owner.id`.

Nếu người dùng API cần biết field con của `owner` và `contacts`, thay subsection tương ứng bằng các descriptor cụ thể:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Tên hồ sơ"),
    fieldWithPath("owner.id").description("Mã người sở hữu"),
    fieldWithPath("owner.displayName").description("Tên hiển thị"),
    fieldWithPath("contacts[].type").description("Loại liên hệ"),
    fieldWithPath("contacts[].value").description("Địa chỉ hoặc giá trị liên hệ")
)
```

## 10. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Subsection `owner` không được tìm thấy | JSON part không có owner hoặc path viết sai | Kiểm tra body của đúng part và tên field |
| Snippet chỉ hiện dòng `owner`, không thấy `owner.id` | Đã dùng `subsectionWithPath("owner")` | Thay bằng field descriptors cụ thể nếu cần schema chi tiết |
| Descriptor subsection và field con bị chồng lấn | Vừa khai báo `owner` như subsection, vừa mô tả `owner.id` trong cùng danh sách | Chọn một mức mô tả hoặc tách schema sang phần tài liệu riêng |
| Field con tùy chọn nhưng document thất bại | Descriptor field chưa có `.optional()` | Đánh dấu optional nếu hợp đồng cho phép field vắng |
| Object vắng mặt và object null bị coi như nhau | Chưa xác định semantics của nullability | Viết mô tả và test riêng cho absent, null và object rỗng |
| Mảng không được document như mong đợi | Dùng JSON path sai, thiếu `[]` cho field phần tử | Kiểm tra cấu trúc JSON và dùng path tương ứng |
| JSON part không phân tích được | Content-Type part sai hoặc body không hợp lệ | Gửi `application/json` cùng JSON hợp lệ |
| Snippet sinh được nhưng người đọc không hiểu schema con | Chỉ có subsection description quá ngắn | Viết rõ schema tham chiếu hoặc mở rộng thành field descriptors |

## 11. WebTestClient, REST Assured và tài liệu

Subsection descriptor không phụ thuộc test client. Điều quan trọng là test client gửi đúng multipart part và cơ chế document gắn snippet part payload.

### 11.1. WebTestClient

Có thể dùng `MultipartBodyBuilder` để tạo JSON part:

```java
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder body = new MultipartBodyBuilder();
body.part("metadata", """
        {
          "name": "Engineering team",
          "owner": {"id":"USR-42","displayName":"Platform Team"}
        }
        """)
        .contentType(MediaType.APPLICATION_JSON);

webTestClient.post()
        .uri("/api/profiles")
        .body(BodyInserters.fromMultipartData(body.build()))
        .exchange()
        .expectStatus().isOk();
```

Khi thêm document, dùng `requestPartFields("metadata", subsectionWithPath("owner")...)` trong lời gọi `document(...)` của tích hợp WebTestClient. Đoạn code trên minh họa tạo request; client cần được cấu hình Spring REST Docs trước.

### 11.2. REST Assured

REST Assured có thể gửi JSON part như một multipart part:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"name\":\"Engineering team\","
                        + "\"owner\":{\"id\":\"USR-42\","
                        + "\"displayName\":\"Platform Team\"}}",
                "application/json")
        .when()
        .post("/api/profiles")
        .then()
        .statusCode(200);
```

`documentationFilter` cần được cấu hình với `requestParts(...)` và `requestPartFields("metadata", ...)` chứa subsection descriptor. Overload multipart cụ thể phụ thuộc phiên bản REST Assured; hãy kiểm tra Content-Type và body của part mà request thực sự gửi.

### 11.3. Chèn snippet vào Asciidoctor

Ví dụ tài liệu:

```asciidoc
= Profile API

== Tạo hồ sơ

=== Request parts

include::{snippets}/profile-create/request-parts.adoc[]

=== Metadata fields

include::{snippets}/profile-create/request-part-metadata-fields.adoc[]

=== Multipart request

include::{snippets}/profile-create/http-request.adoc[]
```

Đường dẫn snippet thực tế tùy template format và phiên bản Spring REST Docs. Hãy đọc thư mục `generated-snippets/profile-create` sau khi test chạy rồi dùng đúng tên file, thay vì đoán tên snippet. Nếu dùng Markdown, cấu hình `TemplateFormats.markdown()` và dùng quy trình ghép snippet phù hợp; Markdown cơ bản không có cú pháp include tiêu chuẩn như Asciidoctor.

## 12. Tích hợp build và CI

Luồng triển khai:

1. Khai báo dependency Spring REST Docs tương ứng với MockMvc, WebTestClient hoặc REST Assured.
2. Viết multipart test có JSON part đại diện và assertion cho các field mà ứng dụng thực sự binding.
3. Dùng `requestParts(...)` cho part và `requestPartFields(...)` với `subsectionWithPath(...)` hoặc `fieldWithPath(...)` cho body.
4. Cấu hình thư mục snippet như `build/generated-snippets` (Gradle) hoặc `target/generated-snippets` (Maven).
5. Cho task Asciidoctor phụ thuộc task test và include đúng snippet đã sinh.
6. Chạy test và render tài liệu trong CI. Khi JSON part thay đổi, strict payload snippet giúp phát hiện descriptor không còn phù hợp.

Ví dụ lệnh Gradle khi task đã được khai báo:

```bash
./gradlew test asciidoctor
```

Không nên document toàn bộ subsection bằng một dòng mô tả rồi xem đó là thay thế cho validation. Quy tắc bắt buộc, optional, enum, nullability và quan hệ giữa field phải được thực thi trong ứng dụng và kiểm chứng bằng test riêng.

## 13. Bài tập thực hành

API `POST /api/projects` nhận part `metadata` với payload:

```json
{
  "name": "REST Docs rollout",
  "owner": {
    "userId": "USR-10",
    "team": {
      "code": "PLATFORM",
      "displayName": "Platform Engineering"
    }
  },
  "settings": {
    "visibility": "TEAM",
    "notifications": {
      "email": true,
      "webhook": false
    }
  },
  "labels": [
    {"name": "backend"},
    {"name": "documentation"}
  ]
}
```

Hãy thực hiện:

1. Tạo controller nhận `@RequestPart("metadata")` thành DTO tương ứng.
2. Viết MockMvc test gửi JSON part với `application/json`.
3. Document `name` chi tiết; document `owner`, `settings` và `labels` bằng `subsectionWithPath(...)`.
4. Tạo biến thể thứ hai mở rộng `owner.team.code`, `owner.team.displayName`, `settings.notifications.email` và `labels[].name` bằng `fieldWithPath(...)`.
5. Thử bỏ `settings` khỏi payload; xác định và document đúng tính optional nếu API cho phép.
6. Thêm test cho `owner = null` và object `owner` thiếu `userId`, xác minh kết quả theo validation contract.
7. Sinh snippet và đưa vào Asciidoctor/CI.

**Tiêu chí hoàn thành:** Chọn đúng mức độ chi tiết cho từng subsection; đường dẫn JSON khớp payload; không khai báo descriptor chồng lấn; tài liệu mô tả rõ phần nào được gom và phần nào được giải thích chi tiết.

## 14. Ghi nhớ

`subsectionWithPath(...)` cho phép document một object hoặc nhóm field lồng nhau như một mục trong bảng field của `requestPartFields(partName, ...)`. Dùng nó khi cấu trúc con có schema riêng hoặc quá lớn để liệt kê ở bảng chính; dùng `fieldWithPath(...)` khi người dùng API cần hiểu tên, kiểu và ý nghĩa từng field cụ thể. Kết hợp `requestParts(...)`, `requestPartFields(...)`, kiểm thử multipart và snippet Asciidoctor/Markdown để tài liệu body của part vừa rõ ràng vừa có thể kiểm chứng trong build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
