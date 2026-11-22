# Tùy chỉnh template cho request và response trong Spring REST Docs

## 1. Vì sao cần một bộ template cho cả request và response?

Spring REST Docs tạo snippet từ các bài kiểm thử HTTP. Với một operation, phần request mô tả client gửi gì; phần response mô tả server trả gì. Hai phía thường có cấu trúc tương đồng nhưng mang ý nghĩa khác nhau:

- Request fields mô tả dữ liệu client phải gửi, gồm field bắt buộc, tùy chọn và các quy tắc đầu vào.
- Response fields mô tả dữ liệu server trả về, gồm định danh, trạng thái, timestamp hoặc các liên kết mà client có thể sử dụng.
- Request body và response body cung cấp ví dụ payload nguyên bản.
- HTTP request và HTTP response thể hiện phương thức, URI, headers, status và nội dung trên wire.

Template mặc định giúp tạo bảng dễ đọc. Khi tài liệu API cần ngôn ngữ nhất quán, tiêu đề riêng, cột bổ sung hoặc quy tắc trình bày theo design system, ta có thể override template cho từng snippet bằng Mustache.

Trong **SPRING_REST_DOCS**, các snippet được sinh từ test HTTP với MockMvc, WebTestClient hoặc REST Assured. Tùy chỉnh template chỉ thay đổi cách dữ liệu được trình bày; các descriptor vẫn được dùng để đối chiếu payload thực tế với contract tài liệu hóa. Bài này tập trung vào cách tổ chức template song song cho request và response, truyền metadata cho từng phía và kiểm tra output trước khi Asciidoctor kết xuất tài liệu.

Sau bài học, bạn có thể:

- Xác định template nào tương ứng với request và response snippet.
- Override `request-fields.snippet` và `response-fields.snippet` đúng classpath.
- Dùng descriptor attributes và snippet attributes cho dữ liệu trình bày.
- Tạo tiêu đề, cột và thứ tự trường nhất quán nhưng vẫn thể hiện đúng ngữ nghĩa từng phía.
- Mở rộng cách làm cho request body, response body và HTTP message snippets.
- Kiểm tra template bằng các bài test tài liệu hóa và đưa output vào build/CI.

## 2. Những snippet request/response thường gặp

Khi gọi `document(...)`, Spring REST Docs có thể tạo nhiều snippet. Mỗi snippet có một vai trò và template riêng.

| Phía | Snippet | Mục đích |
| --- | --- | --- |
| Request | `http-request.adoc` | Request HTTP được gửi: method, URI, headers và body |
| Request | `request-body.adoc` | Body nguyên bản của request |
| Request | `request-fields.adoc` | Bảng mô tả các field trong payload |
| Request | `request-headers.adoc` | Bảng mô tả HTTP request headers |
| Request | `request-parameters.adoc` | Bảng mô tả request parameters |
| Response | `http-response.adoc` | HTTP response nhận được: status, headers và body |
| Response | `response-body.adoc` | Body nguyên bản của response |
| Response | `response-fields.adoc` | Bảng mô tả các field trong response payload |
| Response | `response-headers.adoc` | Bảng mô tả HTTP response headers |

Không phải operation nào cũng sinh tất cả các snippet. Ví dụ, `request-fields.adoc` chỉ được tạo khi test cấu hình `requestFields(...)`; `response-fields.adoc` cần `responseFields(...)`.

Tên file template được đặt theo tên snippet nhưng bỏ phần mở rộng output. Ví dụ:

- `request-fields.adoc` được tạo từ `request-fields.snippet`.
- `response-fields.adoc` được tạo từ `response-fields.snippet`.
- `http-request.adoc` được tạo từ `http-request.snippet`.
- `http-response.adoc` được tạo từ `http-response.snippet`.

Vì vậy, nếu muốn hai bảng request và response có giao diện riêng, hãy tạo hai template tương ứng thay vì cố dùng một file template cho mọi snippet.

## 3. Cơ chế tìm template theo format

Spring REST Docs dùng Mustache để render snippet. Template được tìm trên classpath trong package:

```text
org/springframework/restdocs/templates/<format-id>/
```

Với format Asciidoctor mặc định, format ID là `asciidoctor`. Để override hai bảng fields, tạo:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    ├── request-fields.snippet
                    └── response-fields.snippet
```

Các file trên được đưa lên test classpath khi chạy test sinh snippet. Khi Spring REST Docs tìm template `request-fields`, template trong resource test có thể thay thế nội dung mặc định tương ứng.

Nếu dự án sử dụng format khác, package phải dùng đúng format ID của format đó. Không đặt template Markdown trong thư mục `asciidoctor` hoặc template Asciidoctor trong thư mục `markdown`.

Cấu trúc có thể mở rộng:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   ├── response-fields.snippet
│   ├── request-body.snippet
│   ├── response-body.snippet
│   ├── http-request.snippet
│   └── http-response.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

Chỉ tạo template cho snippet thực sự cần tùy biến. Việc override `request-fields.snippet` không tự thay đổi `response-fields.snippet`; hai template độc lập.

## 4. Phân biệt dữ liệu request và response

`requestFields(...)` và `responseFields(...)` đều nhận `FieldDescriptor`, nhưng dữ liệu được đối chiếu thuộc hai payload khác nhau.

Ví dụ endpoint `POST /api/orders` nhận:

```json
{
  "customerId": 42,
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ],
  "note": "Giao sau 17 giờ"
}
```

Response:

```json
{
  "orderId": "ORD-2026-0042",
  "status": "CREATED",
  "totalAmount": 250000,
  "createdAt": "2026-11-17T09:30:00Z"
}
```

Descriptor request:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng tạo đơn"),
    fieldWithPath("items")
        .description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng đặt"),
    fieldWithPath("note")
        .description("Ghi chú giao hàng")
        .optional()
);
```

Descriptor response:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Mã đơn hàng được tạo"),
    fieldWithPath("status")
        .description("Trạng thái hiện tại của đơn hàng"),
    fieldWithPath("totalAmount")
        .description("Tổng tiền đơn hàng, tính bằng VND"),
    fieldWithPath("createdAt")
        .description("Thời điểm tạo đơn theo ISO-8601")
);
```

Request và response có thể dùng chung kiểu cột `Path`, `Type`, `Description`, nhưng tiêu đề và các cột bổ sung nên phản ánh đúng ý nghĩa:

- Request có thể thêm `Required` hoặc `Constraints`.
- Response có thể thêm `Nullable`, `Example` hoặc `Stability` nếu nhóm thực sự quản lý metadata đó.
- Không nên thêm một cột chung mà không có dữ liệu hoặc không có quy ước rõ ràng.

Path phải luôn giữ nguyên tên JSON thật để Spring REST Docs đối chiếu payload. Label, ghi chú hoặc constraint chỉ là metadata cho template.

## 5. Dùng attributes cho từng field và cho cả snippet

Có hai cấp metadata.

### 5.1. Attributes cấp descriptor

Gắn thông tin riêng cho từng field bằng `.attributes(...)`:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("customerId")
    .description("Mã khách hàng tạo đơn")
    .attributes(
        key("label").value("Mã khách hàng"),
        key("constraints").value("Số nguyên dương")
    );
```

Với response:

```java
fieldWithPath("orderId")
    .description("Mã định danh đơn hàng")
    .attributes(
        key("label").value("Mã đơn hàng"),
        key("example").value("ORD-2026-0042")
    );
```

Template đọc đúng các key này qua Mustache, ví dụ `{{label}}`, `{{constraints}}` và `{{example}}`. Nếu descriptor không có attribute tùy chỉnh, template nên có fallback hoặc để cell trống.

### 5.2. Attributes cấp snippet

Có thể truyền attributes cho toàn snippet qua overload của `requestFields(...)` và `responseFields(...)`:

```java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
    attributes(key("title").value("Dữ liệu client gửi lên")),
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("items").description("Danh sách mặt hàng")
);

responseFields(
    attributes(key("title").value("Dữ liệu server trả về")),
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng")
);
```

`title` thuộc toàn snippet. Template tương ứng có thể đọc `{{title}}` để hiển thị tiêu đề khác nhau cho bảng request và response.

Có thể dùng một quy ước metadata chung như `title`, `label`, `constraints`, `example`, nhưng chỉ đưa vào template những cột thực sự có ý nghĩa.

## 6. Tạo template cho request fields

File:

`src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet`

Ví dụ:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Trường request|Path JSON|Kiểu|Mô tả|Ràng buộc

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Giải thích:

- `{{#title}}...{{/title}}` chỉ hiển thị title khi có attribute.
- `{{#fields}}...{{/fields}}` lặp qua các field descriptor.
- `{{label}}` là tên dễ đọc do test gắn thêm.
- `{{^label}}...{{/label}}` là nhánh fallback khi chưa đặt label.
- `{{path}}`, `{{type}}`, `{{description}}` là dữ liệu mô tả field.
- `{{constraints}}` là metadata tùy chỉnh, không tự chạy validation.

Request template dùng tiêu đề cột “Trường request” và “Ràng buộc” để nhấn mạnh dữ liệu client phải cung cấp. Với field optional, có thể ghi thêm trạng thái vào constraint hoặc thêm một attribute riêng như `presence` nếu dự án có quy ước thống nhất.

Không thay `path` bằng `label`. Nếu client cần biết chính xác JSON phải gửi, path kỹ thuật phải được giữ trong bảng.

## 7. Tạo template cho response fields

File:

`src/test/resources/org/springframework/restdocs/templates/asciidoctor/response-fields.snippet`

Ví dụ:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Trường response|Path JSON|Kiểu|Mô tả|Ví dụ

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{example}}

{{/fields}}
|===
```

Response template có thể thay cột `Ràng buộc` bằng `Ví dụ`, vì client thường cần hiểu dạng dữ liệu nhận được. Ví dụ có thể được gắn vào descriptor:

```java
fieldWithPath("orderId")
    .description("Mã đơn hàng được tạo")
    .attributes(key("label").value("Mã đơn hàng"))
    .attributes(key("example").value("ORD-2026-0042"));

fieldWithPath("totalAmount")
    .description("Tổng tiền đơn hàng, tính bằng VND")
    .attributes(key("label").value("Tổng tiền"))
    .attributes(key("example").value("250000"));
```

Đây là metadata tài liệu do nhóm duy trì. Spring REST Docs không tự suy ra ví dụ nghiệp vụ từ mọi response và không kiểm tra `example` có còn đúng với dữ liệu production hay không. Nên chọn giá trị ví dụ an toàn, ổn định và đại diện cho contract.

### 7.1. Khi muốn hai bảng có giao diện giống nhau

Nếu design system yêu cầu request và response có cùng cột, hãy dùng một bộ cột chung:

```adoc
|Tên trường|Path JSON|Kiểu|Mô tả|Ghi chú
```

Tuy nhiên, giá trị cột `Ghi chú` nên khác nhau theo từng phía:
- Request: giá trị bắt buộc, độ dài, range hoặc constraint.
- Response: nullable, ý nghĩa trạng thái, format hoặc example.

Template giống nhau về bố cục không có nghĩa ngữ nghĩa của request và response giống nhau.

## 8. Override template cho request body và response body

`request-body.adoc` và `response-body.adoc` chứa body nguyên bản được ghi nhận từ operation. Nếu muốn thêm tiêu đề hoặc format phần body, có thể tạo:

```text
request-body.snippet
response-body.snippet
```

trong cùng thư mục format:

```text
org/springframework/restdocs/templates/asciidoctor/
```

Template body cần được thiết kế theo dữ liệu body mà Spring REST Docs cung cấp cho snippet tương ứng. Trước khi override, xem template mặc định của đúng phiên bản dependency để giữ lại các biến và cấu trúc cần thiết. Không sao chép template của một snippet khác vì model dữ liệu giữa `request-body` và `response-body` có thể khác.

Tương tự, muốn thay đổi cách trình bày HTTP message tổng thể, có thể override:

```text
http-request.snippet
http-response.snippet
```

Các template này có phạm vi lớn hơn bảng field: chúng trình bày HTTP message và có thể chứa method/status, URI, headers và nội dung. Chỉ override khi thực sự cần; nếu chỉ muốn đổi tiêu đề của bảng fields, chỉnh `request-fields.snippet` và `response-fields.snippet` sẽ có phạm vi tác động hẹp hơn.

## 9. Ví dụ MockMvc dùng cả request và response templates

Giả định endpoint `POST /api/orders` nhận JSON request và trả JSON response với status `201 Created`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderRequestResponseDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                    {
                      "customerId": 42,
                      "items": [
                        { "sku": "BOOK-001", "quantity": 2 }
                      ]
                    }
                    """))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(
                                attributes(key("title")
                                        .value("Thông tin client gửi lên")),
                                fieldWithPath("customerId")
                                        .description("Mã khách hàng tạo đơn")
                                        .attributes(
                                                key("label").value("Mã khách hàng"),
                                                key("constraints").value("Số nguyên dương")
                                        ),
                                fieldWithPath("items")
                                        .description("Danh sách mặt hàng")
                                        .attributes(key("label").value("Danh sách mặt hàng")),
                                fieldWithPath("items[].sku")
                                        .description("Mã sản phẩm")
                                        .attributes(key("label").value("Mã sản phẩm")),
                                fieldWithPath("items[].quantity")
                                        .description("Số lượng đặt")
                                        .attributes(
                                                key("label").value("Số lượng"),
                                                key("constraints").value("Số nguyên lớn hơn 0")
                                        )
                        ),
                        responseFields(
                                attributes(key("title")
                                        .value("Thông tin server trả về")),
                                fieldWithPath("orderId")
                                        .description("Mã đơn hàng được tạo")
                                        .attributes(
                                                key("label").value("Mã đơn hàng"),
                                                key("example").value("ORD-2026-0042")
                                        ),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng")
                                        .attributes(
                                                key("label").value("Trạng thái"),
                                                key("example").value("CREATED")
                                        ),
                                fieldWithPath("totalAmount")
                                        .description("Tổng tiền đơn hàng, tính bằng VND")
                                        .attributes(
                                                key("label").value("Tổng tiền"),
                                                key("example").value("250000")
                                        )
                        )
                ));
    }
}
```

Imports và response body là ví dụ; cần thay bằng endpoint, JSON fixture và response thực tế của dự án. Mục đích là minh họa hai loại snippet được sinh từ cùng một operation nhưng dùng attributes riêng.

Sau khi test chạy thành công, output có thể gồm:

```text
build/generated-snippets/
└── orders-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

`request-fields.adoc` được render bằng `request-fields.snippet`; `response-fields.adoc` được render bằng `response-fields.snippet`. Mỗi template dùng đúng metadata của phía tương ứng.

## 10. Dùng WebTestClient hoặc REST Assured

Template được nạp từ test classpath theo format, không gắn chặt với MockMvc. Nếu test sử dụng WebTestClient hoặc REST Assured nhưng chọn cùng template format, nội dung template vẫn được tái sử dụng.

Ví dụ WebTestClient:

```java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestBody)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-create",
        requestFields(
            attributes(key("title").value("Thông tin client gửi lên")),
            fieldWithPath("customerId").description("Mã khách hàng")
        ),
        responseFields(
            attributes(key("title").value("Thông tin server trả về")),
            fieldWithPath("orderId").description("Mã đơn hàng")
        )
    ));
```

Ví dụ REST Assured:

```java
given(this.spec)
    .filter(document("orders-create",
        requestFields(
            attributes(key("title").value("Thông tin client gửi lên")),
            fieldWithPath("customerId").description("Mã khách hàng")
        ),
        responseFields(
            attributes(key("title").value("Thông tin server trả về")),
            fieldWithPath("orderId").description("Mã đơn hàng")
        )))
    .contentType("application/json")
    .body(requestBody)
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
```

Cấu trúc đầy đủ của test và cách gắn `document(...)` phụ thuộc module tích hợp. Nguyên tắc tùy biến template không đổi: descriptor và snippet attributes được cung cấp trong lời gọi tạo snippet; Mustache template trên test classpath quyết định cách render.

## 11. Kiểm soát field chưa mô tả và metadata tùy biến

Tùy biến giao diện không làm giảm trách nhiệm kiểm tra payload. `requestFields(...)` và `responseFields(...)` strict vẫn kiểm tra field theo descriptor như trước:

- Field có trong payload nhưng chưa được mô tả có thể làm test thất bại.
- Descriptor bắt buộc nhưng không có trong payload có thể làm test thất bại.
- `.optional()` cho phép field được mô tả vắng mặt trong payload mẫu.
- `.ignored()` nhận diện field nhưng không hiển thị dòng tương ứng trong bảng.

Attribute `label`, `constraints` hoặc `example` chỉ cung cấp thêm dữ liệu để template trình bày. Nó không thay đổi path, không làm field optional và không thực thi Bean Validation.

Ví dụ một field optional ở request:

```java
fieldWithPath("note")
    .description("Ghi chú giao hàng")
    .optional()
    .attributes(
        key("label").value("Ghi chú"),
        key("constraints").value("Tối đa 500 ký tự")
    );
```

Field response thường không cần dùng quy tắc bắt buộc giống request. Nếu response có trường nullable, mô tả rõ nullability trong description hoặc metadata riêng và bảo đảm template thể hiện đúng quy ước.

Không nên tạo cột `Required` hay `Nullable` nhưng để trống hoặc suy đoán từ một payload mẫu. Hãy đặt metadata từ contract thực tế và duy trì cùng nguồn với validation/schema nếu có thể.

## 12. Escape dữ liệu khi render bảng

Khi template Asciidoctor tạo bảng, ký tự `|` trong description có thể được hiểu là dấu phân tách cột. Template cần xử lý nội dung cell đúng cách. Với template Asciidoctor, có thể sử dụng lambda `tableCellContent` cho các cell văn bản:

```adoc
|{{#tableCellContent}}{{description}}{{/tableCellContent}}
```

Nếu thêm `label`, `constraints` hoặc `example`, hãy cân nhắc escape các giá trị đó theo cùng cách:

```adoc
|{{#tableCellContent}}{{label}}{{/tableCellContent}}
|{{#tableCellContent}}{{constraints}}{{/tableCellContent}}
```

Cơ chế escaping cụ thể phụ thuộc format template. Với Markdown, kiểm tra renderer của dự án và escape pipe trong bảng theo Markdown flavor đang dùng. Không giả định một lambda của Asciidoctor tự tồn tại trong format khác.

Ngoài ký tự pipe, cần kiểm tra:
- Nội dung có xuống dòng hoặc markup inline.
- Ký tự `<`, `>` hoặc dấu ngoặc trong mô tả.
- Giá trị do test fixture cung cấp có phải dữ liệu nhạy cảm không.
- Template có fallback khi một attribute vắng mặt không.

## 13. Tổ chức và bảo trì template

Một cấu trúc dễ quản lý:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   ├── response-fields.snippet
    │   ├── request-body.snippet
    │   └── response-body.snippet
    └── markdown/
        ├── request-fields.snippet
        └── response-fields.snippet
```

Một số nguyên tắc:

1. **Giữ request và response riêng.** Điều này cho phép hai bảng có tiêu đề, cột và fallback phù hợp với ý nghĩa.
2. **Dùng chung quy ước attributes.** Ví dụ `label`, `example`, `constraints` cần có định nghĩa rõ để các nhóm sử dụng nhất quán.
3. **Có fallback.** Descriptor không có label vẫn phải hiển thị path; field không có example không được làm vỡ bảng.
4. **Không copy template tùy tiện.** Khi nâng phiên bản Spring REST Docs, template mặc định có thể thay đổi. Đối chiếu lại template override với phiên bản dependency mới.
5. **Chỉ override phạm vi cần thiết.** Nếu chỉ cần thêm cột fields, không cần override `http-request` hay `http-response`.
6. **Review template như mã nguồn.** Thay đổi một Mustache block có thể ảnh hưởng mọi operation dùng cùng format trên test classpath.

Nếu dự án có nhiều module, đặt templates trong test resources của module cần áp dụng. Tránh đưa template quá đặc thù vào thư viện dùng chung nếu các module có quy ước tài liệu khác nhau.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Request table đổi nhưng response table giữ mặc định | Chỉ override `request-fields.snippet` | Tạo `response-fields.snippet` riêng |
| Template không được nạp | Sai package format ID hoặc tên file | Kiểm tra `templates/asciidoctor` và tên snippet |
| Label không xuất hiện | Attribute key và Mustache variable khác nhau | Đồng bộ `key("label")` với `{{label}}` |
| Title không hiện | Chưa truyền snippet attribute `title` hoặc template không render | Truyền `attributes(key("title")...)` và thêm block Mustache |
| Cột example trống | Một số field không có metadata example | Dùng fallback hoặc để trống có chủ ý |
| Bảng bị lệch cột | Số cell trong header và mỗi row không khớp | Kiểm tra từng cột và block `fields` |
| Description chứa `|` làm vỡ bảng | Chưa escape nội dung cell | Dùng `tableCellContent` với Asciidoctor |
| Response dùng nhầm cột constraint của request | Copy nguyên template mà không xét ngữ nghĩa | Thiết kế response columns theo contract |
| Template body không hoạt động | Copy biến Mustache từ template fields | Đối chiếu template mặc định đúng snippet và version |
| Template Markdown không được dùng | Đặt trong thư mục Asciidoctor hoặc chưa chọn format Markdown | Dùng đúng format ID và cấu hình template tương ứng |
| Test vẫn chạy nhưng tài liệu sai nhãn | Attribute được nhập thủ công và lỗi thời | Review metadata cùng API contract |
| Build CI dùng output cũ | Snippet không được sinh lại trước Asciidoctor | Bảo đảm task tài liệu phụ thuộc test |

## 15. Asciidoctor và build/CI

Tài liệu nguồn có thể include request và response snippet cạnh nhau:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Các trường request
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]

=== Các trường response
include::{snippets}/orders-create/response-fields.adoc[]
```

Nếu template đã sinh tiêu đề bên trong snippet, tránh đặt thêm title trùng ngay trước include. Nếu title được quản lý ở Asciidoctor, đặt title đúng cú pháp trước nội dung include.

Với Gradle và plugin Asciidoctor đã được cấu hình, task tài liệu cần phụ thuộc vào test sinh snippet:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Đảm bảo plugin `spring-restdocs-asciidoctor` và thuộc tính snippets được cấu hình theo hướng dẫn build mà dự án sử dụng.

Luồng CI:

```text
HTTP tests
    |
    +--> requestFields / requestHeaders / requestParts
    |
    +--> responseFields / responseHeaders
    |
    v
Request & response descriptors + attributes
    |
    v
Mustache request/response templates
    |
    v
Generated snippets
    |
    v
Asciidoctor / Markdown builder
    |
    v
Kiểm tra và xuất bản tài liệu
```

Mỗi khi thay đổi template, cần chạy lại ít nhất các test tài liệu hóa đại diện cho request và response. Kiểm tra cả trường hợp attribute có và không có, field lồng nhau, optional và nội dung chứa ký tự đặc biệt. Không chỉnh file trong `build/generated-snippets` bằng tay; hãy sửa descriptor hoặc template nguồn.

## 16. Bài thực hành

Dùng operation `POST /api/orders`:

1. Tạo template `request-fields.snippet` với cột `Trường request`, `Path`, `Kiểu`, `Mô tả`, `Ràng buộc`.
2. Tạo template `response-fields.snippet` với cột `Trường response`, `Path`, `Kiểu`, `Mô tả`, `Ví dụ`.
3. Gắn `label` và `constraints` cho request descriptors.
4. Gắn `label` và `example` cho response descriptors.
5. Truyền hai giá trị `title` khác nhau cho `requestFields(...)` và `responseFields(...)`.
6. Chạy test và so sánh hai file `request-fields.adoc` và `response-fields.adoc`.
7. Bỏ attribute `label` khỏi một field; kiểm tra fallback vẫn hiển thị path.
8. Thêm dấu `|` vào description và xác nhận bảng không vỡ.
9. Tạo template Markdown trong đúng format package và sinh lại snippet ở format đó.
10. Include cả request và response vào Asciidoctor, chạy build/CI và review generated output.

### Câu hỏi tự đánh giá

- Vì sao request và response có template riêng?
- `request-fields.snippet` tạo ra snippet nào?
- Attribute cấp descriptor khác attribute cấp snippet ở đâu?
- Vì sao template phải được đặt theo format ID trên test classpath?
- `requestFields(...)` và `responseFields(...)` có thể dùng cùng một bộ attributes không?
- Vì sao `label` không được thay thế path JSON?
- Khi nào cần override `http-request.snippet` thay vì chỉ `request-fields.snippet`?
- Làm thế nào để xử lý field không có metadata tùy chỉnh?
- Vì sao cần kiểm tra template ở cả request và response trong CI?

**Ghi nhớ:** Request và response là hai phía của cùng một contract nhưng có mục đích khác nhau. Dùng `request-fields.snippet` và `response-fields.snippet` riêng để trình bày đúng ngữ nghĩa; dùng descriptor attributes cho từng field và snippet attributes cho tiêu đề hoặc metadata chung. Template quyết định giao diện, còn test và descriptor tiếp tục kiểm chứng payload thực tế.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates, template classpath và extra attributes.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `responseFields`, payload và fields snippets.
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html): các snippet mặc định và cách cấu hình snippet generation.
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): preprocessors cho request và response trước khi ghi snippet.
