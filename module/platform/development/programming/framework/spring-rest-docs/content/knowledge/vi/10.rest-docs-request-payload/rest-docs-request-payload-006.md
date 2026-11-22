# Trường có thể `null` và nullability trong Spring REST Docs

## 1. Vì sao `null` không đồng nghĩa với trường tùy chọn?

Trong một REST API nhận JSON, hai câu hỏi dưới đây có ý nghĩa khác nhau:

1. **Khóa JSON có bắt buộc phải xuất hiện trong request hay không?** Đây là *presence*, tức tính bắt buộc/tùy chọn của đường dẫn trường.
2. **Nếu khóa xuất hiện, giá trị của nó có được phép là JSON `null` hay không?** Đây là *nullability*, tức tính cho phép giá trị `null`.

Ví dụ, API có thể yêu cầu client luôn gửi khóa `externalReference`, nhưng cho phép giá trị của nó là `null` khi đơn hàng chưa được liên kết với hệ thống ngoài. Một trường khác như `couponCode` có thể **không cần gửi**, nhưng nếu đã gửi thì phải là một chuỗi mã hợp lệ, không được `null`.

Trong chương **Request payload** của **Spring REST Docs**, `fieldWithPath(...)` và `requestFields(...)` mô tả trường JSON trên HTTP request được kiểm thử. `.optional()` điều chỉnh quy tắc **trường có thể vắng mặt** khi sinh snippet; nó **không phải** khai báo nullable. Tài liệu được tạo từ bài kiểm thử MockMvc, WebTestClient hoặc REST Assured, rồi biên soạn dưới dạng Asciidoctor/Markdown và đưa vào build, CI để được tái tạo khi API thay đổi.

Sau bài học, bạn sẽ biết cách:

- Phân biệt **absent**, `null`, chuỗi rỗng, object rỗng và array rỗng.
- Xây dựng bảng hợp đồng dựa trên hai thuộc tính độc lập: **required** và **nullable**.
- Mô tả kiểu của trường có thể `null` bằng `JsonFieldType`, `.type(...)` và `.description(...)`.
- Viết test MockMvc sinh `request-fields.adoc` với cả request có `null` và request thiếu trường tùy chọn.
- Kiểm tra JSON request bằng Jackson; kết hợp Bean Validation và test lỗi để bảo vệ các quy tắc không thể kiểm chứng chỉ bằng snippet.
- Tổ chức thông tin nullability trong tài liệu xuất bản và quá trình build/CI.

## 2. Ma trận required × nullable: bốn hợp đồng khác nhau

Hãy lấy một JSON object chỉ có trường `value` để minh họa.

| Bắt buộc có khóa? | Cho phép `null`? | Payload hợp lệ | Payload không hợp lệ |
| --- | --- | --- | --- |
| Có | Không | `{ "value": "A" }` | `{}` hoặc `{ "value": null }` |
| Có | Có | `{ "value": "A" }` hoặc `{ "value": null }` | `{}` |
| Không | Không | `{}` hoặc `{ "value": "A" }` | `{ "value": null }` |
| Không | Có | `{}`, `{ "value": "A" }` hoặc `{ "value": null }` | Các giá trị sai kiểu/ràng buộc khác |

Ma trận trên nói về **hợp đồng API giả định**. Những trường hợp sai chỉ bị API từ chối khi ứng dụng thực sự triển khai kiểm tra và có test xác minh.

Spring REST Docs cung cấp `.optional()` để mô tả **trục có thể vắng mặt**; một descriptor không gọi `.optional()` là bắt buộc theo quy tắc sinh snippet. `FieldDescriptor` **không có phương thức `.nullable()` tiêu chuẩn** để tự bảo đảm giá trị `null` hợp lệ. Vì vậy, cần mô tả nullability bằng lời, metadata/template khi muốn có cột riêng, và các kiểm thử xử lý dữ liệu.

### Một ví dụ dễ nhầm

```java
fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Mã giảm giá, có thể bỏ qua; nếu gửi phải là chuỗi")
        .optional();
```

`.optional()` nghĩa là **không gửi `couponCode`** thì bước sinh snippet vẫn chấp nhận. Nó không có nghĩa `{"couponCode":null}` hợp lệ theo nghiệp vụ. Nếu client gửi `null`, API phải quyết định xử lý và test riêng.

```java
fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("Luôn gửi khóa; giá trị có thể là null khi chưa có mã ngoài");
```

Descriptor này **không có** `.optional()` vì khóa cần tồn tại trong request mẫu. Tuy vậy, hợp đồng cho phép giá trị `null`. Muốn bảo đảm phía server yêu cầu khóa này thực sự xuất hiện nhưng cho phép `null`, ta cần kiểm tra ở tầng xử lý request, vì DTO Java thông thường có thể biến hai trường hợp *absent* và *explicit null* thành cùng một giá trị `null`.

## 3. Phân biệt absent, `null`, chuỗi rỗng, `{}` và `[]`

Xét năm request đơn giản:

**A — Không có khóa (absent)**

```json
{ "customerId": 42 }
```

**B — Có khóa với giá trị JSON null**

```json
{ "customerId": 42, "note": null }
```

**C — Có khóa với chuỗi rỗng**

```json
{ "customerId": 42, "note": "" }
```

**D — Có khóa với object rỗng**

```json
{ "customerId": 42, "note": {} }
```

**E — Có khóa với array rỗng**

```json
{ "customerId": 42, "note": [] }
```

| Dạng | Khóa `note` có mặt? | Kiểu giá trị JSON | Điều cần quyết định |
| --- | --- | --- | --- |
| Absent | Không | Không tồn tại | Client được phép bỏ qua không? |
| `null` | Có | `null` | Null có ý nghĩa đặc biệt, hoặc bị từ chối? |
| `""` | Có | String | Chuỗi rỗng có hợp lệ không? |
| `{}` | Có | Object | Object rỗng có đúng kiểu và đủ thuộc tính không? |
| `[]` | Có | Array | Danh sách rỗng có được phép không? |

**Không nên coi năm dạng này tương đương.** Ví dụ trong một API cập nhật kiểu PATCH, việc **thiếu khóa** có thể mang nghĩa “giữ nguyên”, còn **khóa có giá trị null** có thể mang nghĩa “xóa giá trị”. Tuy nhiên, ý nghĩa này phụ thuộc loại PATCH và hợp đồng cụ thể; không được tự áp dụng cho mọi endpoint.

Đặc biệt, **“tùy chọn” không tự suy ra “nullable”**, và **“nullable” không tự suy ra “tùy chọn”**.

### Jackson giúp xác định sự khác nhau như thế nào?

Khi kiểm tra request JSON, `JsonNode` của Jackson cung cấp các phương thức rõ ràng:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;

ObjectMapper mapper = new ObjectMapper();

JsonNode absent = mapper.readTree("{\"customerId\":42}");
JsonNode explicitNull = mapper.readTree(
        "{\"customerId\":42,\"note\":null}");
JsonNode emptyString = mapper.readTree(
        "{\"customerId\":42,\"note\":\"\"}");

assertFalse(absent.has("note"));
assertTrue(absent.path("note").isMissingNode());

assertTrue(explicitNull.has("note"));
assertTrue(explicitNull.get("note").isNull());

assertTrue(emptyString.has("note"));
assertTrue(emptyString.get("note").isTextual());
assertEquals("", emptyString.get("note").asText());
```

`has("note")` trả `true` khi trường có mặt, **kể cả khi giá trị là `null`**. `hasNonNull("note")` trả `false` cả khi trường vắng mặt lẫn khi trường có giá trị `null`, nên **không thể dùng riêng nó để phân biệt hai trường hợp**.

```java
assertFalse(absent.hasNonNull("note"));
assertFalse(explicitNull.hasNonNull("note"));
assertTrue(emptyString.hasNonNull("note"));
```

Tương tự, `path("note")` trả một `MissingNode` nếu trường không có mặt, nhưng trả `NullNode` nếu JSON chứa `note: null`. Khi muốn kiểm thử sự **vắng mặt thực sự**, `isMissingNode()` chính xác hơn việc so sánh kết quả `.asText()` với chuỗi rỗng.

## 4. `JsonFieldType.NULL` là gì?

Spring REST Docs hỗ trợ các giá trị `JsonFieldType`: `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL` và `VARIES`. Khi không khai báo kiểu tường minh, thư viện cố gắng suy ra kiểu bằng cách quan sát request payload đang được kiểm thử.

Ví dụ:

```json
{
  "customerId": 42,
  "comment": null
}
```

Trường `comment` đang có giá trị kiểu JSON `null`. Với một request mẫu chỉ có giá trị này, kiểu được suy ra có thể được hiển thị là `null` trong bảng. **Điều đó không có nghĩa hợp đồng của trường chỉ cho phép `null`**. Một request khác có thể gửi chuỗi `"Đóng gói cẩn thận"`.

Nếu hợp đồng nói `comment` là **string hoặc null**, nên chọn kiểu nền một cách rõ ràng:

```java
fieldWithPath("comment")
        .type(JsonFieldType.STRING)
        .description("Ghi chú; có thể là chuỗi hoặc null");
```

Lưu ý:

- `.type(JsonFieldType.STRING)` định dạng **kiểu được ghi trong tài liệu**; nó không tự chuyển `null` thành chuỗi.
- `JsonFieldType.NULL` mô tả một giá trị JSON `null`, **không phải một flag nullable** để dùng chung với `STRING`.
- `JsonFieldType.VARIES` diễn đạt trường có các giá trị thuộc nhiều kiểu trong payload được quan sát; đây cũng **không thay cho quy tắc nullable của API**.
- Nếu API chỉ cho phép String hoặc null, hãy viết rõ điều đó trong mô tả và test từng dạng hợp lệ/không hợp lệ.

Một ví dụ với mảng có hai kiểu giá trị:

```json
{ "labels": [null, "urgent"] }
```

Khi sử dụng đường dẫn `labels[]`, việc suy luận kiểu phụ thuộc các phần tử quan sát được; các giá trị khác kiểu có thể làm kiểu được mô tả thay đổi. Với hợp đồng đã biết kiểu cơ sở, khai báo tường minh và mô tả khả năng null giúp tài liệu không phụ thuộc dữ liệu mẫu duy nhất. Nếu API **không** cho phép phần tử null, cần test để từ chối ví dụ này; descriptor không thay thế validation theo phần tử.

## 5. Bài toán thực tế: API tạo đơn hàng có nhiều dạng nullability

Giả sử `POST /api/orders` nhận dữ liệu:

```json
{
  "orderId": 710,
  "contact": {
    "email": "an@example.com",
    "phone": null
  },
  "externalReference": null,
  "couponCode": "WELCOME",
  "gift": {
    "message": null
  }
}
```

Quy tắc hợp đồng được đặt ra để minh họa:

| Field path | Required? | Nullable? | Quy tắc |
| --- | --- | --- | --- |
| `orderId` | Có | Không | Mã đơn hàng kiểu số |
| `contact` | Có | Không | Object thông tin liên hệ |
| `contact.email` | Có | Không | Email không được rỗng |
| `contact.phone` | Không | Có | Có thể bỏ qua, là string hoặc null |
| `externalReference` | Có | Có | Luôn có khóa, string hoặc null |
| `couponCode` | Không | Không | Có thể bỏ qua; nếu gửi phải là string không rỗng |
| `gift` | Không | Có | Có thể bỏ qua, là object hoặc null |
| `gift.message` | Không | Có | Có thể vắng mặt; nếu có là string hoặc null |

Một payload hợp lệ khác theo hợp đồng ví dụ:

```json
{
  "orderId": 711,
  "contact": {
    "email": "binh@example.com"
  },
  "externalReference": null
}
```

Trong request thứ hai, `contact.phone`, `couponCode`, `gift` đều **absent**. Riêng `externalReference` vẫn hiện diện với giá trị `null`, vì hợp đồng quy định trường này **required + nullable**.

### Descriptor Spring REST Docs

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_FIELDS = {
        fieldWithPath("orderId")
                .type(JsonFieldType.NUMBER)
                .description("Mã đơn hàng, bắt buộc và không được null"),

        fieldWithPath("contact")
                .type(JsonFieldType.OBJECT)
                .description("Thông tin liên hệ, bắt buộc và không được null"),

        fieldWithPath("contact.email")
                .type(JsonFieldType.STRING)
                .description("Email, bắt buộc và không rỗng"),

        fieldWithPath("contact.phone")
                .type(JsonFieldType.STRING)
                .description("Số điện thoại, có thể bỏ qua hoặc gửi null")
                .optional(),

        fieldWithPath("externalReference")
                .type(JsonFieldType.STRING)
                .description("Bắt buộc có khóa; là string hoặc null"),

        fieldWithPath("couponCode")
                .type(JsonFieldType.STRING)
                .description("Mã giảm giá; có thể bỏ qua, nhưng không được null khi gửi")
                .optional(),

        fieldWithPath("gift")
                .type(JsonFieldType.OBJECT)
                .description("Quà tặng; có thể bỏ qua, object hoặc null")
                .optional(),

        fieldWithPath("gift.message")
                .type(JsonFieldType.STRING)
                .description("Thông điệp; có thể bỏ qua, string hoặc null")
                .optional()
};
```

Các trường `contact.phone`, `couponCode`, `gift`, `gift.message` đều cần `.optional()` vì JSON mẫu có thể không chứa chúng. `externalReference` **không** được đánh dấu optional vì hợp đồng yêu cầu khóa này phải tồn tại trong request mẫu, dù giá trị có thể là `null`.

**Giới hạn quan trọng:** Các descriptor dùng để mô tả dữ liệu và kiểm tra việc trường có được tài liệu hóa trong request mẫu hay không. Chúng không tự đảm bảo tất cả điều kiện của bảng hợp đồng phía trên. Đặc biệt, `.type(JsonFieldType.STRING)` không phải bộ kiểm chứng giá trị không null; `.optional()` cũng không phải quyền gửi null.

## 6. Kiểm thử MockMvc có `null` và trường vắng mặt

Ví dụ dưới đây giả định dự án có Spring Boot 3.x, Java 17, JUnit 5, Spring REST Docs và endpoint `POST /api/orders` đã được triển khai để trả **HTTP 201 Created** cho hai payload hợp lệ ở mục 5.

Các test dependencies thường gồm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Bài kiểm thử dùng `@AutoConfigureRestDocs` để sinh snippets trong `build/generated-snippets`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderNullabilityDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private static final FieldDescriptor[] ORDER_FIELDS = {
            fieldWithPath("orderId")
                    .type(JsonFieldType.NUMBER)
                    .description("Mã đơn hàng; bắt buộc, không null"),
            fieldWithPath("contact")
                    .type(JsonFieldType.OBJECT)
                    .description("Thông tin liên hệ; bắt buộc, không null"),
            fieldWithPath("contact.email")
                    .type(JsonFieldType.STRING)
                    .description("Email, bắt buộc và không rỗng"),
            fieldWithPath("contact.phone")
                    .type(JsonFieldType.STRING)
                    .description("Số điện thoại; tùy chọn, có thể null")
                    .optional(),
            fieldWithPath("externalReference")
                    .type(JsonFieldType.STRING)
                    .description("Luôn có khóa; string hoặc null"),
            fieldWithPath("couponCode")
                    .type(JsonFieldType.STRING)
                    .description("Tùy chọn; nếu gửi phải là chuỗi không rỗng")
                    .optional(),
            fieldWithPath("gift")
                    .type(JsonFieldType.OBJECT)
                    .description("Object quà tặng, tùy chọn và nullable")
                    .optional(),
            fieldWithPath("gift.message")
                    .type(JsonFieldType.STRING)
                    .description("Lời nhắn, tùy chọn và nullable")
                    .optional()
    };

    @Test
    void documentOrderWithExplicitNullValues() throws Exception {
        String json = """
                {
                  "orderId": 710,
                  "contact": {
                    "email": "an@example.com",
                    "phone": null
                  },
                  "externalReference": null,
                  "couponCode": "WELCOME",
                  "gift": {
                    "message": null
                  }
                }
                """;

        JsonNode root = objectMapper.readTree(json);
        assertTrue(root.path("contact").has("phone"));
        assertTrue(root.path("contact").path("phone").isNull());
        assertTrue(root.has("externalReference"));
        assertTrue(root.path("externalReference").isNull());
        assertTrue(root.path("gift").path("message").isNull());

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-nullability-explicit-null",
                        requestFields(ORDER_FIELDS)));
    }

    @Test
    void documentOrderWithOptionalFieldsAbsent() throws Exception {
        String json = """
                {
                  "orderId": 711,
                  "contact": {
                    "email": "binh@example.com"
                  },
                  "externalReference": null
                }
                """;

        JsonNode root = objectMapper.readTree(json);
        assertFalse(root.path("contact").has("phone"));
        assertFalse(root.has("couponCode"));
        assertFalse(root.has("gift"));
        assertTrue(root.has("externalReference"));
        assertTrue(root.path("externalReference").isNull());

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-nullability-absent",
                        requestFields(ORDER_FIELDS)));
    }
}
```

Khi HTTP status và tài liệu hóa đều đạt, Spring REST Docs sẽ tạo thư mục tương ứng với hai tên snippet:

```text
build/generated-snippets/
├── orders-nullability-explicit-null/
│   └── request-fields.adoc
└── orders-nullability-absent/
    └── request-fields.adoc
```

Thường còn có những snippet khác như `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, tùy cấu hình của dự án. Dùng hai tên khác nhau để giữ riêng ví dụ **explicit null** và **absent**.

Ở hai bài kiểm thử, `requestFields(ORDER_FIELDS)` dùng chung các descriptor, nhưng test có dữ liệu khác nhau. Việc Jackson assertion chạy trước `mockMvc.perform(...)` là cách **chứng minh ngay trong bài kiểm thử** rằng payload gửi đi có giá trị `null` hay thực sự thiếu khóa, thay vì chỉ nhìn vào lời mô tả.

### Cần kiểm tra thêm gì?

Hai bài test thành công chưa chứng minh được:

- API từ chối `couponCode: null` khi hợp đồng nói không nullable.
- API từ chối request **không có khóa** `externalReference` trong khi khóa này bắt buộc.
- API từ chối `contact: null` hoặc `contact.email: null`.
- API xử lý đúng `gift: null` và `gift: {}` theo hợp đồng.
- API phân biệt PATCH có khóa null và không có khóa nếu đây là endpoint cập nhật.

Các trường hợp này cần test HTTP riêng, với kỳ vọng lỗi hoặc thành công theo contract.

## 7. Khi nào cần validation và kiểm tra sự hiện diện của khóa?

### 7.1. Bean Validation xử lý tốt nhiều quy tắc non-null

Với Jakarta Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record OrderRequest(
        @NotNull Long orderId,
        @NotNull @Valid ContactRequest contact,
        String externalReference,
        String couponCode,
        @Valid GiftRequest gift
) {}

record ContactRequest(
        @NotBlank @Email String email,
        String phone
) {}

record GiftRequest(String message) {}
```

Trong controller, khi nhận `@Valid @RequestBody OrderRequest request`, validation có thể đảm bảo:

- `orderId` và `contact` không là Java `null` sau khi binding.
- `contact.email` không rỗng và đúng định dạng email theo các annotation đang dùng.
- `contact.phone`, `gift` và `gift.message` có thể null nếu không có ràng buộc bổ sung.

Nhưng **`externalReference` là “required + nullable”**: `String externalReference` trong record thông thường nhận giá trị Java `null` cho cả JSON thiếu khóa lẫn JSON có khóa `"externalReference": null`. Bởi vậy chỉ dùng `@NotNull` sẽ **không đúng** hợp đồng, còn không khai báo ràng buộc gì sẽ không kiểm tra sự hiện diện của khóa.

### 7.2. Kiểm tra required + nullable ở mức JSON object

Để phân biệt **absent** và **explicit null** trước khi binding, có thể xử lý `JsonNode` hoặc cơ chế deserialization theo dõi sự hiện diện:

```java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

void requireExternalReferenceKey(JsonNode requestBody) {
    if (!requestBody.has("externalReference")) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "externalReference must be present, even when null"
        );
    }
}
```

Đây là hàm minh họa phần kiểm tra **presence**. Ứng dụng thực cần tích hợp ở controller, deserializer hoặc tầng kiểm tra đầu vào; đồng thời thực hiện các ràng buộc khác trước khi xử lý đơn hàng. Nếu sử dụng OpenAPI hoặc JSON Schema, có thể khai báo field nằm trong danh sách `required` và đồng thời có kiểu cho phép `null`, rồi kiểm chứng bằng validator phù hợp.

### 7.3. Kiểm tra optional nhưng non-null nếu có

Với `couponCode`, hợp đồng cho phép không gửi nhưng từ chối `null`:

```java
void requireNonNullWhenPresent(JsonNode requestBody) {
    if (requestBody.has("couponCode")
            && requestBody.path("couponCode").isNull()) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "couponCode must not be null when supplied"
        );
    }
}
```

Nếu hợp đồng còn yêu cầu kiểu String, không rỗng, đúng mẫu mã coupon, hãy kiểm tra bổ sung `isTextual()`, nội dung và quy tắc nghiệp vụ. Đừng coi việc có `.type(JsonFieldType.STRING)` trong REST Docs là đã thực thi các điều kiện đó.

### 7.4. Kiểm thử âm tính (negative tests)

Sau khi ứng dụng triển khai quy tắc, nên có các bài kiểm thử:

| Request gửi tới endpoint | Kết quả kỳ vọng của hợp đồng ví dụ |
| --- | --- |
| Thiếu `orderId` | HTTP 400 |
| `"contact": null` | HTTP 400 |
| `"contact": { "email": null }` | HTTP 400 |
| Thiếu `externalReference` | HTTP 400 |
| `"externalReference": null` | HTTP 201 |
| Thiếu `couponCode` | HTTP 201 |
| `"couponCode": null` | HTTP 400 |
| Thiếu `gift` | HTTP 201 |
| `"gift": null` | HTTP 201 nếu contract cho phép |

Các mã HTTP trong bảng là **kỳ vọng minh họa**; chúng chỉ xuất hiện khi endpoint xử lý validation và ánh xạ lỗi tương ứng. Spring REST Docs không tự trả HTTP 400 khi phát hiện descriptor hoặc kiểu mô tả không như ý.

## 8. Object nullable và phần tử mảng nullable

### 8.1. Object cha có thể null, trường con có thể biến mất

Xét:

```json
{
  "gift": null
}
```

Và:

```json
{
  "gift": {
    "message": null
  }
}
```

Trong payload thứ nhất, `gift` có mặt với giá trị `null`, nhưng `gift.message` không thể tìm được như một đường dẫn object lồng nhau. Nếu descriptor `gift.message` cũng được dùng cho payload này, nó cần được xem là tùy chọn theo kịch bản hoặc được mô tả trong snippet riêng.

Trong payload thứ hai, object `gift` có mặt và trường con `message` cũng có mặt với giá trị `null`.

```java
fieldWithPath("gift")
        .type(JsonFieldType.OBJECT)
        .description("Quà tặng, có thể bỏ qua hoặc null")
        .optional();

fieldWithPath("gift.message")
        .type(JsonFieldType.STRING)
        .description("Lời nhắn, có thể bỏ qua hoặc null")
        .optional();
```

Nếu API yêu cầu `message` bắt buộc khi `gift` là object, `.optional()` trong snippet dùng chung không thể diễn đạt hết điều kiện này. Khi đó cần kiểm thử thêm trường hợp `{ "gift": {} }` và xác nhận API phản hồi đúng.

### 8.2. Phần tử mảng null

Ví dụ:

```json
{
  "contacts": [
    { "type": "EMAIL", "value": "an@example.com" },
    null
  ]
}
```

`contacts` là array nhưng không phải mọi phần tử đều là object. Dù descriptor `contacts[].type` có thể có dữ liệu trong request mẫu này, điều đó không tự khẳng định phần tử thứ hai là hợp lệ.

Nếu contract **không cho phép null trong danh sách**, dùng Bean Validation với element constraint và test tương ứng:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;

record ContactListRequest(
        List<@NotNull @Valid ContactItem> contacts
) {}

record ContactItem(String type, String value) {}
```

Khi controller kích hoạt validation, ràng buộc `@NotNull` trên mỗi phần tử giúp từ chối phần tử null. Có thể thêm `@NotEmpty` vào cả list nếu cần ít nhất một phần tử. Hãy lưu ý yêu cầu dependency validation và cấu hình kiểm tra constraint trên container elements theo phiên bản framework đang sử dụng.

Nếu API **cho phép phần tử null**, tài liệu phải giải thích ý nghĩa của null và test trường hợp có nhiều phần tử khác nhau. Không nên dùng descriptor phần tử object để khiến người đọc suy ra danh sách luôn đồng nhất trong khi hợp đồng cho phép phần tử null.

## 9. Hiển thị nullability trong bảng tài liệu

Mặc định, `requestFields(...)` sinh bảng những thông tin như `Path`, `Type`, `Description`, dựa trên template snippet. **Không nên giả định luôn có sẵn cột “Nullable”**. Có hai cách thực tế:

### 9.1. Viết rõ trong `.description(...)`

```java
fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("Bắt buộc có khóa; cho phép null");

fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Tùy chọn; nếu gửi phải là string khác null")
        .optional();
```

Đây là lựa chọn đơn giản, dễ đọc và hoạt động với template mặc định.

### 9.2. Gắn metadata để tùy biến template

Spring REST Docs cho phép thêm thuộc tính vào descriptor thông qua `.attributes(...)`. Ví dụ:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("Mã tham chiếu ngoài")
        .attributes(key("nullable").value("Có"));

fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Mã giảm giá")
        .optional()
        .attributes(key("nullable").value("Không"));
```

Sau đó có thể tùy biến template `request-fields` của REST Docs để đọc thuộc tính `nullable` và hiển thị cột tương ứng. **Các thuộc tính tùy chỉnh không tự xuất hiện** trong snippet nếu template hiện tại không sử dụng chúng. Nếu muốn có cả cột “Required”, cũng cần thống nhất cách trình bày thông tin optional trong template.

Đối với tài liệu dành cho client, nên hiển thị rõ cả hai thuộc tính:

| Field | Required | Nullable | Type |
| --- | --- | --- | --- |
| `externalReference` | Yes | Yes | String |
| `couponCode` | No | No | String |
| `gift` | No | Yes | Object |
| `contact.email` | Yes | No | String |

Khi thay đổi một trường từ nullable sang non-nullable, cần cập nhật contract, validation, bài kiểm thử và snippet cùng lúc.

## 10. Đưa snippet vào Asciidoctor và CI

Ví dụ tài liệu nguồn `src/docs/asciidoc/api.adoc`:

```adoc
= Orders REST API
:toc: left

== Tạo đơn hàng

=== Request cho trường có giá trị null
include::{snippets}/orders-nullability-explicit-null/http-request.adoc[]

=== Request khi bỏ qua các trường tùy chọn
include::{snippets}/orders-nullability-absent/http-request.adoc[]

=== Mô tả request fields
include::{snippets}/orders-nullability-explicit-null/request-fields.adoc[]
```

Biến `{snippets}` cần trỏ đúng đến thư mục `build/generated-snippets` hoặc nơi bài kiểm thử lưu kết quả. Với Gradle và plugin Asciidoctor đã được cấu hình:

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

Chuỗi kiểm soát nên là:

```text
Build / CI
    |
    v
HTTP tests (MockMvc / WebTestClient / REST Assured)
    |
    v
Spring REST Docs tạo request-fields.adoc
    |
    v
Asciidoctor kết xuất HTML
    |
    v
Xuất bản tài liệu
```

Nếu dự án cần xuất **Markdown**, hãy dùng template snippet phù hợp hoặc bước chuyển đổi từ AsciiDoc; ví dụ này không mặc định tạo `request-fields.md`. Việc test tài liệu hóa thất bại phải được phản ánh thành build thất bại, để tránh phát hành bảng trường không đồng bộ với payload được kiểm thử.

## 11. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bảng hiển thị kiểu `null` cho trường thực tế là String hoặc null | REST Docs suy luận kiểu từ request mẫu chỉ có `null` | Đặt `.type(JsonFieldType.STRING)` và diễn giải khả năng null |
| Dùng `.optional()` để khẳng định nullable | Nhầm trục presence với nullability | Ghi rõ nullable trong mô tả, thêm test gửi `null` |
| Test tài liệu hóa thành công nhưng API chấp nhận `couponCode: null` trái hợp đồng | Chưa có kiểm tra non-null khi khóa hiện diện | Thêm validation/logic kiểm tra và test âm tính |
| DTO không phân biệt `externalReference` absent với explicit null | Cả hai được deserialize thành Java `null` | Kiểm tra `JsonNode.has`, custom deserializer hoặc cơ chế theo dõi presence |
| `gift: null` khiến descriptor `gift.message` báo thiếu | Đường dẫn con không tồn tại khi object cha là null | Đánh dấu descriptor con tùy chọn hoặc chia kịch bản tài liệu |
| Mảng có phần tử null nhưng server vẫn chấp nhận | Chưa có ràng buộc cho từng phần tử | Dùng container element constraint và test request có null |
| Tài liệu không có cột nullable | Template snippet mặc định không sử dụng metadata nullable | Viết trong mô tả hoặc tùy biến template |
| `JsonFieldType.NULL` bị hiểu là “chuỗi có thể null” | Nhầm giá trị JSON đang quan sát với hợp đồng kiểu | Phân biệt literal null với nullable string/object |
| Dùng `jsonPath(...).doesNotExist()` để xác nhận request absent | Đây là matcher cho **response** và có quy tắc riêng với null | Kiểm tra request body bằng Jackson hoặc assertion theo request |
| Không thấy `request-fields.adoc` | Chưa gắn `requestFields(...)` với `document(...)` hoặc output path sai | Kiểm tra cấu hình REST Docs và thư mục sinh snippets |

## 12. Bài thực hành và tự đánh giá

Bắt đầu từ bài test MockMvc ở mục 6.

1. **Required + nullable:** xóa khóa `externalReference` khỏi JSON nhưng vẫn giữ descriptor không `.optional()`. Quan sát phản hồi của bước tài liệu hóa; sau đó bổ sung test HTTP để bảo đảm server từ chối request thiếu khóa.
2. **Optional + non-nullable:** bổ sung `"couponCode": null` trong request mẫu. Viết test kỳ vọng lỗi theo hợp đồng, sau khi đã thêm validation; giải thích vì sao `.optional()` không giúp từ chối null.
3. **Kiểm tra bằng Jackson:** chạy các assertion `has`, `hasNonNull`, `isNull`, `isMissingNode` trên JSON có `"phone": null` và JSON không có `phone`. Viết một dòng giải thích cho mỗi kết quả.
4. **Object nullable:** gửi `"gift": null`, rồi gửi `"gift": {"message": null}`. So sánh sự có mặt của đường dẫn `gift.message` và kết quả kiểm thử.
5. **Nullable array element:** thử thêm `null` vào `contacts` và bổ sung ràng buộc `List<@NotNull ...>` để chứng minh endpoint từ chối phần tử null nếu hợp đồng yêu cầu.
6. **Tài liệu hóa:** bổ sung cột nullable thông qua metadata/template hoặc ghi rõ trong description. Sinh snippets, include vào Asciidoctor và kiểm tra hai ví dụ `null`/absent hiện diện trong tài liệu HTML.

### Câu hỏi tự đánh giá

- Trường **required + nullable** khác trường **optional + non-nullable** như thế nào?
- Vì sao `JsonFieldType.NULL` không phải là cờ nullable?
- Vì sao `.optional()` không thay thế kiểm thử gửi `null`?
- `JsonNode.has("phone")` và `JsonNode.hasNonNull("phone")` trả kết quả khác nhau khi nào?
- Vì sao record Java với một trường `String` thường không phân biệt được JSON absent và explicit null?
- Trong quy trình build/CI, làm thế nào để việc thay đổi nullability không khiến tài liệu bị lỗi thời?

**Ghi nhớ:** Trong Spring REST Docs, `.optional()` trả lời câu hỏi **“trường có thể không xuất hiện trong JSON không?”**, còn *nullability* trả lời **“khi xuất hiện, trường có thể mang giá trị JSON `null` không?”**. Hai thuộc tính này độc lập. Kết hợp mô tả `requestFields`, kiểu `JsonFieldType`, assertion JSON, validation và test HTTP giúp tài liệu REST API rõ ràng và có thể kiểm chứng trong build/CI.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, trường optional và cách suy luận kiểu JSON.
- [Spring REST Docs — FieldDescriptor](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `type(Object)`, `optional()` và metadata field.
- [Spring REST Docs — JsonFieldType](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/JsonFieldType.html): các kiểu `NULL`, `STRING`, `VARIES`, v.v.
