# `ignore` và trường không cần mô tả trong operation với Spring REST Docs

## 1. Bài toán: payload có nhiều field nhưng operation chỉ cần mô tả một phần

Một REST API có thể nhận JSON chứa dữ liệu nghiệp vụ cùng metadata phục vụ vận hành, tracing, tương thích ngược hoặc mở rộng theo phiên bản client. Người sử dụng API cần hiểu các trường như `customerId` và `items`, nhưng không nhất thiết cần một dòng riêng cho `clientTraceId`, `legacySource` hay `internalFlags` trong bảng request fields của từng operation.

Ví dụ `POST /api/orders` nhận:

```json
{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ],
  "clientTraceId": "trace-7f91",
  "legacySource": "mobile-v1",
  "internalFlags": {
    "migration": false
  }
}
```

Với **Spring REST Docs**, có ba lựa chọn thường gặp:

- `.ignored()` trên `FieldDescriptor`: nhận diện một field đã biết nhưng không đưa nó vào bảng snippet fields.
- `relaxedRequestFields(...)`: tài liệu hóa một phần payload và cho phép các field khác chưa có descriptor.
- Không gọi `requestFields(...)` nếu operation không cần bảng mô tả từng field; có thể chỉ đưa request HTTP hoặc request body vào tài liệu.

Ba lựa chọn này tác động khác nhau đến việc kiểm tra payload. Chọn đúng cơ chế giúp tài liệu tập trung vào thông tin người dùng API cần, trong khi vẫn giữ được kiểm tra hữu ích cho hợp đồng request.

## 2. `.ignored()` trong `FieldDescriptor`

`fieldWithPath(...)` tạo descriptor cho một đường dẫn JSON. Gọi `.ignored()` để đánh dấu descriptor không cần xuất hiện trong snippet fields.

```java
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Mã tương quan dùng cho tracing")
        .ignored();
```

Khi descriptor được truyền vào `requestFields(...)`, field `clientTraceId` được nhận diện trong cấu hình tài liệu hóa nhưng không thành một dòng trong bảng `request-fields.adoc`.

Ví dụ:

```java
requestFields(
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("Mã khách hàng"),
    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng"),
    fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Mã trace kỹ thuật")
        .ignored()
);
```

Bảng snippet trình bày các descriptor được công bố; `clientTraceId` không xuất hiện trong bảng.

### 2.1. Ignore không có nghĩa là optional

Hai phương thức giải quyết hai câu hỏi độc lập:

| Phương thức | Câu hỏi | Tác dụng |
| --- | --- | --- |
| `.ignored()` | Có hiển thị descriptor trong snippet không? | Không hiển thị field đó |
| `.optional()` | Descriptor có được phép vắng trong payload mẫu không? | Cho phép field vắng mặt khi tài liệu hóa |

Nếu field luôn có trong payload nhưng không cần công bố, `.ignored()` là đủ. Nếu field kỹ thuật có thể xuất hiện hoặc không tùy client, kết hợp cả hai:

```java
fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Mã trace do client cung cấp")
        .optional()
        .ignored();
```

Trong trường hợp này, `.optional()` cho phép field vắng mặt trong request mẫu; `.ignored()` giữ field khỏi bảng fields nếu nó xuất hiện. Không thêm `.optional()` chỉ để xử lý lỗi test nếu hợp đồng thực tế yêu cầu field luôn có.

### 2.2. Ignore một object hoặc một nhánh

Một nhánh kỹ thuật có thể được xem như một đơn vị:

```json
{
  "internalFlags": {
    "migration": false,
    "sourceRegion": "ap-southeast"
  }
}
```

```java
fieldWithPath("internalFlags")
        .type(JsonFieldType.OBJECT)
        .description("Metadata vận hành nội bộ")
        .ignored();
```

Khi chỉ muốn bỏ qua cả nhánh, có thể khai báo descriptor ở cấp object. Nếu một số trường con vẫn cần xuất hiện trong tài liệu, hãy thiết kế descriptor theo đúng mức chi tiết đó thay vì ignore toàn bộ object cha.

### 2.3. Khi nào nên dùng?

| Tình huống | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Field kỹ thuật đã biết, không cần giải thích cho client | `clientTraceId` | `.ignored()` |
| Field cũ tiếp tục được chấp nhận để tương thích | `legacySource` | `.ignored()` nếu không cần công bố ở operation này |
| Field có thể thiếu, nhưng nếu có vẫn không cần hiển thị | `clientTraceId` | `.optional().ignored()` |
| Field có ý nghĩa nghiệp vụ đối với client | `couponCode`, `deliveryMode` | Mô tả đầy đủ, không ignore |
| Field nhạy cảm hoặc bí mật | `internalToken` | Rà soát contract và việc truyền dữ liệu; `.ignored()` không phải biện pháp bảo mật |

Không nên dùng `.ignored()` để che giấu field quan trọng chỉ vì descriptor bị thiếu hoặc test đang báo lỗi. Nếu client cần biết field có thể gửi, kiểu dữ liệu và ràng buộc, hãy mô tả field đó.

## 3. So sánh strict fields, ignored fields và relaxed fields

### 3.1. `requestFields(...)`: kiểm tra chặt

```java
requestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng")
)
```

Với `requestFields(...)`, Spring REST Docs kiểm tra payload dựa trên các descriptor. Trong chế độ chặt, field có trong JSON nhưng chưa được mô tả có thể khiến quá trình sinh snippet thất bại. Đây là tín hiệu hữu ích khi nhóm muốn mọi field mới đều được xem xét trước khi cập nhật tài liệu.

### 3.2. `requestFields(...)` kết hợp `.ignored()`

```java
requestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng"),
    fieldWithPath("clientTraceId")
        .description("Mã trace kỹ thuật")
        .ignored()
)
```

Field đã biết được khai báo rõ ràng trong operation và không xuất hiện trong bảng. Strict mode vẫn giữ vai trò phát hiện những field khác chưa được xử lý. Cách này phù hợp khi chỉ có một số field kỹ thuật đã biết cần bỏ khỏi bảng.

### 3.3. `relaxedRequestFields(...)`: cho phép field chưa khai báo

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng")
)
```

`relaxedRequestFields(...)` phù hợp khi operation chỉ mô tả một phần payload và chấp nhận các field khác chưa có descriptor. Ví dụ object `preferences` được thiết kế như một map mở rộng, có thể xuất hiện key mới theo phiên bản client.

Các descriptor đã khai báo vẫn có quy tắc hiện diện riêng. Nếu một descriptor bắt buộc vắng mặt trong payload mẫu, hãy dùng `.optional()` khi contract cho phép.

### 3.4. Bảng so sánh

| Cơ chế | Field được khai báo | Field có trong payload nhưng chưa khai báo | Field được hiển thị |
| --- | --- | --- | --- |
| `requestFields(...)` | Kiểm tra theo descriptor | Có thể làm snippet thất bại | Có, trừ descriptor ignored |
| `requestFields(...)` + `.ignored()` | Nhận diện nhưng bỏ khỏi bảng | Vẫn được strict mode phát hiện | Chỉ field không ignored |
| `relaxedRequestFields(...)` | Mô tả theo descriptor | Được phép tồn tại | Chỉ descriptor đã khai báo |
| Không tạo fields snippet | Không có kiểm tra field-level bằng snippet này | Không kiểm tra field-level bằng snippet này | Không có bảng |

Quy tắc lựa chọn:

- Dùng `.ignored()` khi biết rõ field nào không cần công bố nhưng vẫn muốn strict mode phát hiện field dư khác.
- Dùng `relaxedRequestFields(...)` khi payload có phần mở rộng chưa thể liệt kê hết và điều đó là chủ đích của contract.
- Không gọi `requestFields(...)` nếu operation không yêu cầu bảng field-level; dùng request mẫu hoặc body snippet khi phù hợp.

## 4. Ví dụ operation có metadata kỹ thuật

Giả sử endpoint tạo đơn hàng có contract:

- `customerId` và `items` là dữ liệu nghiệp vụ cần công bố.
- `clientTraceId`, `legacySource`, `internalFlags` là metadata kỹ thuật đã biết nhưng không cần xuất hiện trong bảng.
- Một field mới chưa được nhóm xem xét cần được phát hiện trong strict mode.

### 4.1. Khai báo descriptor

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("Mã khách hàng đặt hàng"),
    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng đặt"),

    fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Mã liên kết log")
        .ignored(),
    fieldWithPath("legacySource")
        .type(JsonFieldType.STRING)
        .description("Tên nguồn client cũ")
        .ignored(),
    fieldWithPath("internalFlags")
        .type(JsonFieldType.OBJECT)
        .description("Các cờ nội bộ")
        .ignored()
};
```

Nếu `legacySource` có thể vắng mặt trong một số request, descriptor có thể viết:

```java
fieldWithPath("legacySource")
    .type(JsonFieldType.STRING)
    .description("Tên nguồn client cũ")
    .optional()
    .ignored()
```

### 4.2. Bài kiểm thử MockMvc

Ví dụ giả định dự án đã có Spring Boot, JUnit 5, MockMvc và dependency `spring-restdocs-mockmvc`; endpoint `/api/orders` trả `201 Created` với payload hợp lệ.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderIgnoredFieldsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentPublicFieldsAndIgnoreTechnicalFields() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ],
                  "clientTraceId": "trace-7f91",
                  "legacySource": "mobile-v1",
                  "internalFlags": {
                    "migration": false
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create-public-fields",
                        requestFields(ORDER_REQUEST_FIELDS)));
    }
}
```

Sau khi test HTTP và bước tạo snippet thành công, `request-fields.adoc` chỉ trình bày các descriptor nghiệp vụ. Các field ignored không trở thành dòng trong bảng.

Nếu JSON được bổ sung `newClientOption` mà descriptor chưa thay đổi, strict `requestFields(...)` có thể phát hiện field chưa được xử lý. Nhóm cần quyết định có mô tả, ignore có chủ đích hay cập nhật contract. Không nên tự động chuyển toàn bộ operation sang relaxed mode chỉ để làm build xanh.

### 4.3. Ignore không biến field thành dữ liệu an toàn

`.ignored()` chỉ tác động đến snippet tài liệu. Nó không:

- Xóa field khỏi HTTP request.
- Ngăn ứng dụng đọc hoặc ghi field.
- Che field trong log, tracing hoặc database.
- Mã hóa hoặc bảo vệ dữ liệu nhạy cảm.
- Kiểm soát quyền client gửi field.

Nếu field chứa token, thông tin cá nhân hoặc dữ liệu bí mật, cần thiết kế contract, xác thực, phân quyền, logging và lưu trữ an toàn. Ẩn một dòng trong `request-fields.adoc` không phải biện pháp bảo mật.

## 5. Operation không cần bảng fields: chỉ tài liệu hóa request body

Không phải operation nào cũng cần bảng mô tả từng field. Một endpoint có thể nhận một payload opaque, dữ liệu chuyển tiếp, nội dung được định nghĩa trong một schema riêng hoặc một tài liệu khác.

Nếu operation chỉ cần minh họa body, có thể dùng snippet body mà không gọi `requestFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestBody;

mockMvc.perform(post("/api/imports")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json))
    .andExpect(status().isAccepted())
    .andDo(document("imports-create",
        requestBody()
    ));
```

`requestBody()` tạo snippet về nội dung request body; nó không tạo bảng path/type/description như `requestFields(...)`. Khi chỉ cần ví dụ HTTP, operation cũng có thể dùng `http-request.adoc` và bỏ qua snippet body riêng nếu nội dung đó đã đủ.

Nguồn Asciidoctor có thể include:

```adoc
== Nhập dữ liệu

=== HTTP request
include::{snippets}/imports-create/http-request.adoc[]

=== Request body
include::{snippets}/imports-create/request-body.adoc[]
```

Hãy kiểm tra cấu hình và phiên bản Spring REST Docs đang dùng để xác nhận các snippet được tạo ra đúng tên và format mà tài liệu include. Nếu client cần biết ý nghĩa từng field, chỉ body mẫu là chưa đủ; cần bảng `requestFields(...)` hoặc schema được liên kết rõ ràng.

## 6. Khi nào dùng `relaxedRequestFields(...)`?

Giả sử API có object `preferences` cho phép mở rộng key:

```json
{
  "customerId": 42,
  "preferences": {
    "newsletter": true,
    "theme": "dark",
    "futureFlag": "enabled"
  }
}
```

Operation hiện chỉ muốn công bố `customerId` và `preferences.newsletter`, còn các thuộc tính khác được thiết kế mở rộng theo phiên bản client:

```java
relaxedRequestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    fieldWithPath("preferences.newsletter")
        .description("Có nhận bản tin hay không")
)
```

Các field như `preferences.theme` và `preferences.futureFlag` được phép có mặt dù chưa có descriptor. Đây là lựa chọn phù hợp cho map mở rộng hoặc payload tương thích nhiều phiên bản.

Đổi lại, một field mới có thể xuất hiện mà không làm snippet thất bại. Vì vậy:

- Chỉ dùng relaxed mode khi việc mở rộng là một phần có chủ đích của contract.
- Mô tả rõ phần nào có schema mở rộng và nơi client tìm hiểu quy tắc.
- Viết test riêng cho key quan trọng, giá trị hợp lệ và giới hạn.
- Không dùng relaxed mode cho toàn bộ payload công khai nếu nhóm muốn phát hiện mọi thay đổi schema.

### So sánh với wildcard

Nếu phần mở rộng là một map có kiểu đồng nhất, có thể dùng `fieldWithPath("attributes.*")` để mô tả các key con động, tùy cấu trúc JSON. Wildcard mô tả một nhóm đường dẫn đã biết; relaxed mode cho phép các field chưa khai báo. Hai cách này không thay thế nhau trong mọi trường hợp.

## 7. Field có thể không cần mô tả ở một operation

Descriptor thuộc về snippet của operation cụ thể. Một field có thể được mô tả ở endpoint telemetry nhưng được ignore trong endpoint tạo đơn hàng. Điều này hợp lý nếu ý nghĩa và contract của field được tài liệu hóa ở vị trí khác dễ tìm.

| Nhu cầu của operation | Cách làm | Kết quả |
| --- | --- | --- |
| Field quan trọng, client cần biết | `fieldWithPath(...).description(...)` | Có dòng trong bảng |
| Field đã biết nhưng không cần trình bày | `.ignored()` | Được nhận diện, không có dòng trong bảng |
| Field có thể vắng và không cần trình bày | `.optional().ignored()` | Có thể absent và không hiển thị |
| Chấp nhận field bổ sung chưa liệt kê | `relaxedRequestFields(...)` | Không cần descriptor cho field dư |
| Chỉ cần ví dụ body | `requestBody()` hoặc HTTP request snippet | Không có bảng field-level |
| Field ngoài contract nhưng client vẫn gửi | Xem lại contract, deprecate hoặc reject theo chính sách | Tránh che giấu dữ liệu không được hỗ trợ |

Không có quy tắc rằng một field phải được mô tả giống nhau trong mọi operation. Nhưng nếu client dựa vào field để tạo request hợp lệ, tài liệu ở ít nhất một nơi dễ tìm cần giải thích ý nghĩa, phạm vi và trạng thái hỗ trợ.

## 8. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field kỹ thuật vẫn xuất hiện trong bảng | Quên `.ignored()` hoặc truyền nhầm descriptor | Đánh dấu descriptor cụ thể `.ignored()` |
| Test báo field chưa được tài liệu hóa | Strict mode gặp field dư | Thêm descriptor, ignore field đã biết hoặc chủ động dùng relaxed mode |
| `.ignored()` bị hiểu là cho phép thiếu field | Nhầm việc ẩn dòng với optional | Thêm `.optional()` nếu field có thể vắng |
| Relaxed mode làm lọt field mới | Field dư được cho phép có chủ đích | Dùng relaxed chỉ cho phần mở rộng, bổ sung test riêng |
| Không có bảng fields dù cần ý nghĩa từng trường | Chỉ sinh `requestBody()` | Bổ sung `requestFields(...)` hoặc schema riêng |
| Dùng ignore để che field nhạy cảm | Nghĩ không có trong snippet là an toàn | Rà soát request, logging, phân quyền và lưu trữ |
| Bảng thiếu chi tiết field con | Chỉ mô tả object cha hoặc ignore cả nhánh | Khai báo descriptor con cần công bố |
| Không tìm thấy `request-body.adoc` | Chưa tạo body snippet hoặc tên output khác | Kiểm tra `requestBody()`, output directory và tên snippet |

## 9. Đưa snippet vào Asciidoctor và CI

Sau khi test sinh snippet thành công, tài liệu Asciidoctor có thể include bảng fields và body snippet:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

=== Các trường request công khai
include::{snippets}/orders-create-public-fields/request-fields.adoc[]

=== Request body của operation import
include::{snippets}/imports-create/request-body.adoc[]
```

Với Gradle và plugin Asciidoctor đã được cấu hình, task tài liệu cần phụ thuộc test sinh snippet:

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

Luồng CI điển hình:

```text
HTTP tests
   |
   v
Spring REST Docs snippets
   |
   v
Asciidoctor / bước chuyển Markdown
   |
   v
Kiểm tra và xuất bản tài liệu
```

Nếu strict snippet thất bại do field mới, nhóm cần quyết định field đó có cần công bố, ignore có chủ đích hay contract đang mở rộng. Không nên đổi mọi `requestFields` sang `relaxedRequestFields` chỉ để build xanh, vì sẽ mất tín hiệu phát hiện thay đổi payload.

Spring REST Docs mặc định thường sinh snippet AsciiDoc. Nếu dự án cần Markdown, phải cấu hình template Markdown hoặc bước chuyển đổi tương ứng; không mặc định có file `request-fields.md`.

## 10. Bài thực hành

Sử dụng endpoint tạo đơn hàng ở mục 4:

1. Thêm `clientVersion` kiểu String vào payload và descriptor `.ignored()`. Chạy test, kiểm tra field không xuất hiện trong `request-fields.adoc`.
2. Bỏ `clientTraceId` khỏi request mẫu, thêm `.optional().ignored()`, chạy test và xác nhận descriptor vẫn phù hợp.
3. Thêm `unexpectedFlag` chưa có descriptor. Quan sát strict `requestFields(...)` phát hiện field mới; quyết định có mô tả, ignore hoặc từ chối field này.
4. Tạo operation import chỉ cần body mẫu, dùng `requestBody()` và include snippet trong Asciidoctor. So sánh với bảng fields.
5. Dùng `relaxedRequestFields(...)` cho object `preferences` mở rộng. Bổ sung một key mới và quan sát khác biệt với strict mode.
6. Xem xét một field nhạy cảm giả lập. Giải thích vì sao `.ignored()` không bảo vệ dữ liệu khỏi request, log hoặc hệ thống lưu trữ.

### Câu hỏi tự đánh giá

- `.ignored()` giải quyết vấn đề gì? Nó có làm field trở thành optional không?
- `.optional().ignored()` kết hợp hai thuộc tính nào?
- `relaxedRequestFields(...)` khác `requestFields(...)` thế nào khi payload có field chưa khai báo?
- Khi operation không cần bảng fields, snippet nào có thể cung cấp request body?
- Vì sao ignore field nhạy cảm không làm việc gửi hoặc ghi log field đó trở nên an toàn?
- Trong CI, khi strict snippet thất bại vì field mới, nhóm nên xem xét điều gì trước khi thay đổi chế độ kiểm tra?

**Ghi nhớ:** `.ignored()` giúp nhận diện một field đã biết nhưng không đưa nó vào bảng snippet; `.optional()` cho phép field vắng mặt trong payload mẫu; `relaxedRequestFields(...)` cho phép field chưa được liệt kê; còn `requestBody()` phù hợp khi chỉ cần nội dung body. Chọn cơ chế theo mục tiêu của operation để tài liệu tập trung mà vẫn giữ được tín hiệu kiểm tra hữu ích.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `relaxedRequestFields`, `requestBody` và mô tả payload.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): descriptor, `.ignored()` và `.optional()`.
