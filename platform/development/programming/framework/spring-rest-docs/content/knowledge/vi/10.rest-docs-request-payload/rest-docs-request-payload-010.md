# Đối chiếu payload thực tế với field descriptors trong Spring REST Docs

## 1. Mục tiêu

Spring REST Docs sinh tài liệu từ các bài kiểm thử HTTP. Với request JSON, `requestFields(...)` sử dụng các `FieldDescriptor` để kiểm tra và mô tả cấu trúc payload được gửi trong test. Nhờ đó, khi JSON thay đổi mà tài liệu chưa được cập nhật, bài kiểm thử có thể phát hiện sai lệch trước khi tài liệu được xuất bản.

Hai API chính là:

- `fieldWithPath("...")`: tạo descriptor cho một đường dẫn JSON.
- `requestFields(...)`: nhận các descriptor và tạo snippet `request-fields.adoc`.

Ví dụ `POST /api/orders` nhận:

```json
{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ],
  "note": "Giao sau 17 giờ"
}
```

Khai báo:

```java
requestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng đặt"),
    fieldWithPath("note").description("Ghi chú giao hàng")
)
```

Bài học thuộc chương Request payload của SPRING_REST_DOCS: tạo REST API documentation có thể kiểm chứng từ MockMvc, WebTestClient hoặc REST Assured, rồi kết hợp snippet với Asciidoctor/Markdown và build/CI.

Sau bài này, bạn có thể phân tích payload được dùng để sinh snippet, nhận biết field dư hoặc thiếu, sửa path sai, phân biệt strict và relaxed mode, cũng như thiết kế test phát hiện contract drift.

## 2. Payload nào được đối chiếu?

Với MockMvc, payload thường được truyền bằng `.content(...)`:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andDo(document("orders-create",
        requestFields(ORDER_FIELDS)
    ));
```

Spring REST Docs sử dụng request được ghi nhận trong operation để tạo snippet. Với WebTestClient và REST Assured, tài liệu hóa cũng được gắn vào HTTP request thực tế thông qua module tích hợp tương ứng.

Descriptor phải theo JSON wire format. Tên property trong DTO Java không nhất thiết giống tên khóa sau khi Jackson serialize.

Ví dụ:

```java
record CreateOrderRequest(
        @JsonProperty("customer_id") Long customerId,
        String note
) {}
```

JSON gửi đi:

```json
{
  "customer_id": 42,
  "note": "Giao sau 17 giờ"
}
```

Descriptor đúng:

```java
fieldWithPath("customer_id")
        .description("Mã khách hàng");
```

Descriptor `customerId` không khớp khóa JSON `customer_id`. Khi test dùng object Java thay vì JSON viết sẵn, kết quả còn phụ thuộc `ObjectMapper`, naming strategy, annotation, module và cấu hình serialize. Vì vậy, khi điều tra mismatch, hãy kiểm tra nội dung JSON thực sự được gửi.

## 3. Cách đối chiếu descriptors

Có thể mô hình hóa luồng xử lý như sau:

```text
Request body trong HTTP test
          |
          v
Đọc cấu trúc JSON
          |
          v
Đối chiếu FieldDescriptor
          |
          +--> Đường dẫn đã được mô tả
          |
          +--> Field dư chưa được mô tả
          |
          +--> Descriptor bắt buộc nhưng field vắng mặt
          |
          v
Sinh request-fields.adoc hoặc báo lỗi
```

Với `requestFields(...)` strict:

- Field có trong payload cần được mô tả hoặc được bao phủ bởi descriptor phù hợp.
- Descriptor bắt buộc cần tìm thấy field tương ứng trong payload mẫu.
- `.optional()` cho phép descriptor vắng mặt trong payload mẫu.
- `.ignored()` nhận diện field nhưng không đưa nó thành một dòng trong bảng.
- Field mới chưa được mô tả có thể làm sinh snippet thất bại.

Một descriptor ở cấp object hoặc subsection cha có thể được xem là bao phủ phần cấu trúc con trong kiểm tra field dư. Vì vậy, test thành công không chứng minh mọi field con đều có description riêng. Nếu client cần biết `items[].sku`, `items[].quantity` và các thuộc tính khác, hãy khai báo chúng rõ ràng.

| Khái niệm | Ý nghĩa | API |
| --- | --- | --- |
| Path matching | Đường dẫn trỏ đúng JSON field | `fieldWithPath(...)` |
| Presence | Field có thể vắng không | `.optional()` |
| Visibility | Field có xuất hiện trong bảng không | `.ignored()` |
| Unspecified fields | Có chấp nhận field chưa khai báo không | `relaxedRequestFields(...)` |
| Type display | Kiểu hiển thị trong snippet | `.type(JsonFieldType.X)` |
| Business validation | Dữ liệu có hợp lệ theo nghiệp vụ không | Bean Validation và test API |

## 4. Các loại mismatch phổ biến

### 4.1. Field mới trong payload

Payload:

```json
{
  "customerId": 42,
  "note": "Giao buổi chiều",
  "discountCode": "WELCOME"
}
```

Descriptor chưa có `discountCode`:

```java
requestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("note").description("Ghi chú giao hàng")
)
```

Strict mode có thể báo `discountCode` chưa được tài liệu hóa. Hãy quyết định:

- Thêm descriptor nếu client cần sử dụng field.
- Dùng `.ignored()` nếu field đã biết nhưng không cần công bố trong operation.
- Dùng `relaxedRequestFields(...)` nếu contract chủ đích cho phép phần mở rộng chưa liệt kê.

Không chuyển sang relaxed mode chỉ để test chạy qua. Trước hết phải xác định ý nghĩa của field mới và tác động tới contract.

### 4.2. Descriptor bắt buộc nhưng payload thiếu field

Payload mẫu:

```json
{ "customerId": 42 }
```

Descriptor:

```java
fieldWithPath("note")
        .description("Ghi chú giao hàng");
```

Nếu `note` thực sự tùy chọn, thêm `.optional()`:

```java
fieldWithPath("note")
        .description("Ghi chú giao hàng")
        .optional();
```

Nếu contract yêu cầu `note`, fixture phải bổ sung field. Không dùng `.optional()` để che payload test thiếu dữ liệu bắt buộc.

### 4.3. Sai tên hoặc sai cấp object

Payload:

```json
{
  "shippingAddress": {
    "city": "Hà Nội"
  }
}
```

Path sai `shipping.address.city`; path đúng `shippingAddress.city`. Đường dẫn phải theo đúng tên khóa JSON, phân biệt chữ hoa/thường và cấp object.

### 4.4. Sai cú pháp array

Payload:

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

`items.sku` thiếu cấp array; dùng `items[].sku`. Ký hiệu `[]` mô tả phần tử ở vị trí bất kỳ. Nếu mảng rỗng, không có phần tử đại diện cho descriptor con; hãy tạo test sinh snippet với một phần tử mẫu và test empty array riêng.

### 4.5. Absent và null

JSON không có khóa:

```json
{ "customerId": 42 }
```

JSON có khóa giá trị null:

```json
{ "customerId": 42, "note": null }
```

`.optional()` nói rằng field được phép vắng trong payload mẫu; nó không phải cờ nullable. Nếu hợp đồng cho phép String hoặc null, mô tả rõ điều đó và viết test tương ứng. DTO Java thông thường có thể không phân biệt được absent và explicit null sau khi binding; nếu sự khác biệt quan trọng, kiểm tra JSON trước khi bind hoặc dùng cơ chế theo dõi presence.

## 5. Ví dụ MockMvc phát hiện contract drift

Giả định endpoint `POST /api/orders` tồn tại, trả `201 Created` khi request hợp lệ; dự án đã có Spring Boot, JUnit 5, MockMvc và dependency `spring-restdocs-mockmvc`.

### 5.1. Descriptor

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_FIELDS = {
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
                .description("Số lượng đặt"),
        fieldWithPath("note")
                .type(JsonFieldType.STRING)
                .description("Ghi chú giao hàng")
                .optional()
};
```

### 5.2. Test sinh snippet

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
class OrderPayloadContractDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ],
                  "note": "Giao sau 17 giờ"
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(ORDER_FIELDS)));
    }
}
```

Khi request HTTP và descriptors phù hợp, snippet được tạo tại `build/generated-snippets/orders-create/request-fields.adoc` cùng các snippet khác tùy cấu hình.

Nếu thêm `discountCode` vào JSON nhưng không cập nhật descriptor, strict mode có thể báo field chưa được mô tả. Nếu thêm descriptor mới nhưng fixture không có field, dùng `.optional()` chỉ khi contract cho phép thiếu; nếu field bắt buộc, phải cập nhật fixture.

### 5.3. Test cho biến thể có và không có optional field

```java
@Test
void documentOrderWithoutOptionalNote() throws Exception {
    String json = """
            {
              "customerId": 42,
              "items": [
                { "sku": "BOOK-001", "quantity": 2 }
              ]
            }
            """;

    mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isCreated())
            .andDo(document("orders-create-without-note",
                    requestFields(ORDER_FIELDS)));
}
```

Dùng tên snippet riêng để tránh hai test ghi đè kết quả của nhau. Hai test với cùng descriptor thể hiện một biến thể có `note` và một biến thể absent `note`.

## 6. Strict, relaxed, ignored và subsection

### Strict `requestFields(...)`

Dùng khi muốn mọi field trong payload được xem xét. Phù hợp với API public có contract cần review khi thay đổi.

### `relaxedRequestFields(...)`

```java
relaxedRequestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng")
)
```

Field chưa khai báo được phép tồn tại. Đổi lại, test không còn là hàng rào phát hiện mọi field mới.

### `.ignored()`

```java
fieldWithPath("clientTraceId")
        .description("Mã tracing nội bộ")
        .ignored();
```

Field đã biết nhưng không hiển thị trong bảng. Nếu có thể vắng, thêm `.optional()`. Hai thuộc tính này không thay thế nhau.

### `subsectionWithPath(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("shippingAddress")
        .description("Thông tin địa chỉ giao hàng");
```

Dùng để mô tả cả một nhánh object như subsection. Nếu người dùng API cần biết từng trường con, khai báo riêng `shippingAddress.street`, `shippingAddress.city` hoặc liên kết tới schema chi tiết.

## 7. Kiểm tra type và payload serialize

`FieldDescriptor` có thể chỉ định kiểu hiển thị:

```java
fieldWithPath("quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng đặt");
```

Các kiểu thường gặp là `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL` và `VARIES`. `.type(...)` là thông tin cho snippet, không phải JSON Schema validator. Nếu payload gửi `"quantity": "2"` dưới dạng String trong khi hợp đồng yêu cầu Number, cần validation và test API để phát hiện.

Jackson có thể ảnh hưởng JSON được gửi:

- `@JsonProperty` thay tên khóa.
- Naming strategy có thể đổi camelCase thành snake_case.
- `@JsonInclude` có thể bỏ field null khi serialize.
- Giá trị mặc định trong DTO/builder có thể làm fixture khác dự kiến.

Khi mismatch, kiểm tra trực tiếp JSON thực sự gửi trước khi sửa descriptor.

## 8. Request preprocessors

Spring REST Docs hỗ trợ operation preprocessors để chuẩn hóa request hoặc response trước khi ghi snippet. Ví dụ pretty print:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("orders-create",
        preprocessRequest(prettyPrint()),
        requestFields(ORDER_FIELDS)
));
```

Cần phân biệt request gửi đến endpoint với request đã preprocess để ghi snippet. Pretty print chủ yếu định dạng JSON để dễ đọc. Nếu preprocessor thay đổi body hoặc loại field, phải xác nhận snippet vẫn phản ánh đúng contract mà client sử dụng. Không loại field khỏi snippet rồi cho rằng nó đã được kiểm tra như request gốc.

Ưu tiên fixture giả lập, không dùng dữ liệu bí mật thực. Preprocessor che dữ liệu trong snippet không tự bảo vệ log hoặc test report.

## 9. Quy trình điều tra lỗi mismatch

1. Đọc JSON test và xác nhận tên khóa, kiểu và cấu trúc.
2. Đọc descriptor, kiểm tra path, `[]`, chữ hoa/thường.
3. Phân loại lỗi: field dư, field required thiếu, nhánh rỗng hay type không nhất quán.
4. Đối chiếu contract: required, optional, nullable hay ignored.
5. Sửa fixture, descriptor hoặc validation đúng với contract.
6. Chạy lại test tài liệu hóa và kiểm tra snippet mới.

| Triệu chứng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Field chưa tài liệu hóa | JSON có field mới | Thêm descriptor, ignore có chủ đích hoặc relaxed nếu contract mở |
| Field bắt buộc bị thiếu | Fixture thiếu field hoặc path sai | Kiểm tra JSON và `.optional()` theo contract |
| Path lồng nhau không khớp | Sai tên khóa/cấp object | Đối chiếu JSON wire format |
| Path mảng không khớp | Thiếu `[]` hoặc mảng rỗng | Dùng array path và fixture có phần tử |
| Field con không có dòng riêng | Object cha/subsection bao phủ nhánh | Thêm descriptor chi tiết nếu cần |
| Type hiển thị sai | Suy luận từ payload mẫu không đại diện | Khai báo type rõ, kiểm thử validation |
| Payload test khác JSON gửi | Jackson config hoặc preprocessor | Kiểm tra request sau serialize |
| Snippet cũ | Test không chạy hoặc output cũ | Kiểm tra task và thư mục sinh snippet |

## 10. Build và CI

Với Gradle và plugin Asciidoctor đã được cấu hình:

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

Tài liệu Asciidoctor:

```adoc
= Orders API

== Tạo đơn hàng

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
```

Luồng CI:

```text
HTTP tests
   |
   v
Spring REST Docs đối chiếu payload và descriptors
   |
   v
Generated snippets
   |
   v
Asciidoctor / bước xuất Markdown
   |
   v
Kiểm tra và xuất bản
```

Nếu muốn review thay đổi snippet trong pull request, có thể lưu output làm artifact hoặc so sánh với tài liệu đã review. Không sửa snippet sinh tự động bằng tay để che mismatch; hãy sửa fixture hoặc descriptor là nguồn sinh.

Spring REST Docs thường sinh snippet AsciiDoc. Nếu cần Markdown, cấu hình template hoặc bước chuyển đổi; không mặc định sẽ có `request-fields.md`.

## 11. Bài thực hành

1. Thêm `discountCode` vào JSON nhưng chưa thêm descriptor. Quan sát strict `requestFields(...)` phát hiện field mới.
2. Thêm descriptor và mô tả rõ ý nghĩa cho client.
3. Bỏ `note` khỏi JSON. Vì descriptor đã `.optional()`, xác nhận snippet vẫn sinh được.
4. Đổi `items[].sku` thành `items.sku`, quan sát lỗi rồi sửa.
5. Đổi khóa JSON `customerId` thành `customer_id`. Cập nhật descriptor theo wire format.
6. Gửi `quantity` dạng String thay vì Number. Thêm validation và test âm tính.
7. Dùng `prettyPrint()` và so sánh snippet trước/sau.
8. Include snippet trong Asciidoctor và bảo đảm task tài liệu phụ thuộc test.

### Câu hỏi tự đánh giá

- `requestFields(...)` đối chiếu descriptor với dữ liệu nào?
- Vì sao descriptor phải theo JSON wire format thay vì tên property Java?
- Khi nào field mới làm strict snippet thất bại?
- `.optional()`, `.ignored()` và `relaxedRequestFields(...)` khác nhau thế nào?
- Vì sao descriptor object cha không đảm bảo mọi field con có description riêng?
- `.type(JsonFieldType.NUMBER)` có thay thế validation không?
- Preprocessor ảnh hưởng snippet ra sao?

**Ghi nhớ:** `FieldDescriptor` là hợp đồng mô tả mà Spring REST Docs dùng để đối chiếu với payload của bài kiểm thử. Strict `requestFields(...)` giúp phát hiện field mới hoặc descriptor không còn khớp. `.optional()`, `.ignored()` và relaxed mode chỉ nên dùng theo đúng contract. Kết hợp fixture HTTP đại diện, validation nghiệp vụ và build CI giúp tài liệu REST API luôn có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `fieldWithPath`, relaxed fields và payload snippets.
- [Spring REST Docs — Operation Preprocessors](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html): chuẩn hóa request/response trước khi ghi snippet.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): descriptor, type, optional, ignored và attributes.
