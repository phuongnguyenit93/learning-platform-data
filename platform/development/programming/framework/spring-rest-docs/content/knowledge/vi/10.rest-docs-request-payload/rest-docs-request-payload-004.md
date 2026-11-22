# Trường mảng, phần tử mảng và chỉ số động trong Spring REST Docs

## 1. Vì sao mảng JSON cần được tài liệu hóa riêng?

Trong REST API, request body thường chứa danh sách sản phẩm, nhãn, địa chỉ, quyền truy cập hoặc các nhóm dữ liệu lồng nhau. Khác với object có một bộ khóa cố định, **mảng có số phần tử và thứ tự thay đổi theo từng request**. Vì vậy, tài liệu cần diễn đạt cấu trúc chung của các phần tử thay vì gắn mô tả vào vị trí đầu tiên, thứ hai hay thứ ba.

Trong chương **Request payload** của **Spring REST Docs**, `requestFields(...)` cho phép khai báo đường dẫn các trường được gửi trong HTTP request; `fieldWithPath(...)` sử dụng ký hiệu `[]` để tham chiếu phần tử của một mảng mà không phụ thuộc chỉ số cụ thể. Snippet được tạo từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi đưa vào tài liệu Asciidoctor hoặc chuỗi xuất Markdown trong build/CI.

Sau bài học, bạn sẽ có thể:

- Phân biệt đường dẫn đến **cả mảng**, **một phần tử bất kỳ** và **trường của object bên trong mảng**.
- Mô tả mảng string, mảng object, mảng trong mảng và object chứa nhiều tầng mảng.
- Hiểu vì sao `items[].sku` thích hợp hơn `items[0].sku` khi mô tả hợp đồng danh sách có chỉ số động.
- Viết bài kiểm thử MockMvc sinh `request-fields.adoc`, kể cả khi thứ tự các phần tử thay đổi.
- Xử lý đúng trường hợp mảng rỗng, mảng vắng mặt, phần tử `null`, trường tùy chọn trong phần tử và các ràng buộc kích thước mảng.

## 2. Ba cấp tài liệu hóa: mảng, phần tử và trường con

Giả sử API `POST /api/orders` nhận JSON:

```json
{
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2,
      "options": [
        { "name": "cover", "value": "hard" }
      ],
      "note": "Gói làm quà"
    },
    {
      "sku": "PEN-002",
      "quantity": 1,
      "options": [
        { "name": "ink", "value": "blue" }
      ]
    }
  ],
  "tags": ["gift", "standard"],
  "batches": [
    ["A-1", "A-2"],
    ["B-1"]
  ]
}
```

Từ JSON này, có ba cấp đường dẫn căn bản:

```text
items            -> cả mảng mặt hàng
items[]          -> một phần tử của mảng items
items[].sku      -> trường sku của một object nằm trong items
```

| JSON path | Cấu trúc được mô tả | Kiểu thường gặp |
| --- | --- | --- |
| `items` | Toàn bộ danh sách mặt hàng | `ARRAY` |
| `items[]` | Một phần tử mặt hàng | `OBJECT` |
| `items[].sku` | Mã của phần tử mặt hàng | `STRING` |
| `items[].quantity` | Số lượng của phần tử mặt hàng | `NUMBER` |
| `items[].options` | Mảng tùy chọn của từng mặt hàng | `ARRAY` |
| `items[].options[]` | Một object tùy chọn | `OBJECT` |
| `items[].options[].name` | Tên của một tùy chọn | `STRING` |
| `tags` | Toàn bộ danh sách nhãn | `ARRAY` |
| `tags[]` | Một nhãn trong danh sách | `STRING` |
| `batches` | Mảng ngoài của các nhóm | `ARRAY` |
| `batches[]` | Một nhóm, bản thân là mảng | `ARRAY` |
| `batches[][]` | Một mã nằm trong một nhóm | `STRING` |

Chú ý rằng `items[]` và `items[].sku` không đồng nghĩa: đường dẫn thứ nhất là **object phần tử**, còn đường dẫn thứ hai là **một trường bên trong object đó**. Tương tự, `tags` là array còn `tags[]` là string.

### 2.1. Khai báo toàn bộ mảng

```java
import org.springframework.restdocs.payload.JsonFieldType;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng của đơn hàng")
```

Đường dẫn `items` giúp giải thích mục đích của danh sách. Nó chưa mô tả đầy đủ từng phần tử có những thuộc tính nào. Do đó, với API công khai, nên có thêm descriptor ở cấp trường con.

### 2.2. Khai báo phần tử mảng

```java
fieldWithPath("items[]")
        .type(JsonFieldType.OBJECT)
        .description("Một mặt hàng trong đơn hàng")
```

Cú pháp `[]` là phần quan trọng. Nó đại diện cho vị trí phần tử **không cố định** trong mảng, phù hợp với danh sách có thể có một, hai hoặc hàng trăm phần tử.

### 2.3. Khai báo các trường của từng phần tử

```java
fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã sản phẩm");

fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng đặt");
```

Trong tài liệu, đây là **mẫu cấu trúc chung** của các phần tử object. Các dòng mô tả này không được nhân bản theo số phần tử đang có trong JSON mẫu.

> `[]` trong đường dẫn của Spring REST Docs là cú pháp để mô tả phần tử mảng. Đừng thay nó bằng placeholder tự đặt như `[i]`, `${index}` hoặc cú pháp JSONPath `[*]` khi chưa kiểm tra quy tắc của API đang dùng.

## 3. Chỉ số động: vì sao không nên gắn tài liệu với `[0]`?

Xét hai request cùng hợp đồng, chỉ khác thứ tự mặt hàng:

**Request A:**

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ]
}
```

**Request B:**

```json
{
  "items": [
    { "sku": "PEN-002", "quantity": 1 },
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

Trong JSON, phần tử đầu tiên có chỉ số `0` và phần tử tiếp theo có chỉ số `1`. Nhưng chỉ số đó chỉ nói về **vị trí trong một request cụ thể**. Nó không quyết định một mặt hàng phải có `sku` hay `quantity` gì.

Để tài liệu hóa cấu trúc dùng chung cho cả hai request, viết:

```java
fieldWithPath("items[].sku")
        .description("Mã sản phẩm của mỗi mặt hàng");

fieldWithPath("items[].quantity")
        .description("Số lượng của mỗi mặt hàng");
```

Nếu tài liệu chỉ trỏ vào `items[0].sku`, mô tả sẽ tập trung vào phần tử **ở chỉ số 0**, không thể hiện rõ rằng tất cả phần tử đều phải tuân thủ cùng một cấu trúc. Chỉ số cụ thể đôi khi hữu ích khi xử lý lỗi ở một phần tử xác định, nhưng không phải cách mặc định để biểu diễn schema của một danh sách có kích thước động.

| Cách viết | Ý nghĩa | Phù hợp cho tài liệu API danh sách? |
| --- | --- | --- |
| `items` | Toàn bộ mảng | Có, để mô tả danh sách |
| `items[]` | Phần tử bất kỳ | Có, để mô tả kiểu phần tử |
| `items[].sku` | Trường `sku` của phần tử bất kỳ | Có, để mô tả cấu trúc dùng chung |
| `items[0].sku` | Trường `sku` ở một vị trí cụ thể | Chỉ dùng khi vị trí đó có ý nghĩa riêng trong hợp đồng |
| `items[i].sku` | Dùng ký tự `i` như biến chỉ số | Không phải placeholder chuẩn cho `fieldWithPath` |

**Ví dụ ngoại lệ:** nếu API định nghĩa `coordinates` là `[latitude, longitude]`, vị trí `0` và `1` có ý nghĩa nghiệp vụ khác nhau. Hợp đồng đó khác với danh sách object cùng cấu trúc. Khi tài liệu hóa, hãy giải thích rõ ý nghĩa vị trí và dùng kỹ thuật phù hợp với thư viện/phiên bản; đừng mặc định mọi mảng đều có các phần tử hoán đổi được.

### `[]` có tự đảm bảo mỗi phần tử đều hợp lệ không?

Không nên suy ra rằng chỉ cần `requestFields(fieldWithPath("items[].sku"))` chạy thành công là **mọi** object trong `items` đã được kiểm tra đầy đủ. REST Docs kiểm tra việc bao phủ và mô tả trường trên **payload mẫu**; đây không phải trình kiểm chứng JSON Schema cho mọi phần tử và mọi request.

Để đảm bảo mỗi mặt hàng có `sku` không rỗng và `quantity` lớn hơn 0, cần validation ở ứng dụng và kiểm thử riêng cho trường hợp một phần tử ở giữa hoặc cuối mảng bị sai.

## 4. Các dạng mảng thường gặp

### 4.1. Mảng giá trị nguyên thủy

```json
{
  "tags": ["urgent", "gift", "fragile"]
}
```

```java
fieldWithPath("tags")
        .type(JsonFieldType.ARRAY)
        .description("Các nhãn của đơn hàng");

fieldWithPath("tags[]")
        .type(JsonFieldType.STRING)
        .description("Một nhãn của đơn hàng");
```

Nếu hợp đồng chỉ cần nói “danh sách nhãn”, có thể chỉ mô tả `tags`. Nếu người dùng cần biết kiểu từng nhãn, giá trị cho phép hoặc ý nghĩa mỗi phần tử, thêm `tags[]` sẽ rõ ràng hơn.

### 4.2. Mảng object với trường tùy chọn

```json
{
  "items": [
    { "sku": "A", "quantity": 1, "note": "Ưu tiên" },
    { "sku": "B", "quantity": 2 }
  ]
}
```

```java
fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã sản phẩm");

fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng");

fieldWithPath("items[].note")
        .type(JsonFieldType.STRING)
        .description("Ghi chú riêng của mặt hàng")
        .optional();
```

`.optional()` cho phép descriptor `items[].note` không cần có dữ liệu tương ứng trong payload mẫu. Tuy nhiên, điều đó không diễn đạt hết quy tắc “cho phép thiếu `note` ở bất kỳ phần tử nào”. Với hợp đồng cần kiểm tra chặt, hãy bổ sung test có nhiều phần tử với các tổ hợp trường khác nhau.

### 4.3. Mảng object chứa mảng object

```json
{
  "items": [
    {
      "sku": "SHIRT-001",
      "options": [
        { "name": "size", "value": "M" },
        { "name": "color", "value": "navy" }
      ]
    }
  ]
}
```

```java
fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng");

fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã mặt hàng");

fieldWithPath("items[].options")
        .type(JsonFieldType.ARRAY)
        .description("Các tùy chọn của mặt hàng");

fieldWithPath("items[].options[].name")
        .type(JsonFieldType.STRING)
        .description("Tên tùy chọn");

fieldWithPath("items[].options[].value")
        .type(JsonFieldType.STRING)
        .description("Giá trị tùy chọn");
```

Đọc `items[].options[].name` từ trái sang phải: đi vào một object thuộc `items`, tiếp tục đi vào một object thuộc `options` của mặt hàng đó, cuối cùng đến trường `name`.

### 4.4. Mảng lồng trong mảng

```json
{
  "batches": [
    ["A-1", "A-2"],
    ["B-1"]
  ]
}
```

```java
fieldWithPath("batches")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách các nhóm mã");

fieldWithPath("batches[]")
        .type(JsonFieldType.ARRAY)
        .description("Một nhóm mã");

fieldWithPath("batches[][]")
        .type(JsonFieldType.STRING)
        .description("Một mã thuộc một nhóm");
```

Mỗi cặp `[]` cho biết một cấp mảng. Nếu cấu trúc phức tạp hơn, chẳng hạn `groups[]` chứa object có `members[]`, đường dẫn trường tên thành viên sẽ là `groups[].members[].name`.

### 4.5. Mảng có các loại phần tử khác nhau

Ví dụ:

```json
{
  "values": ["A", 10, true]
}
```

Đây là một mảng hỗn hợp String, Number và Boolean. Có thể mô tả bản thân `values` bằng `JsonFieldType.ARRAY`, nhưng **không nên tuyên bố** `values[]` có kiểu `STRING`. Nếu hợp đồng chấp nhận các kiểu khác nhau, phải mô tả quy tắc phân loại rõ ràng và có test ứng với từng loại; có thể cần `JsonFieldType.VARIES` hoặc cách tài liệu hóa riêng theo cấu trúc thực tế và phiên bản REST Docs sử dụng. Với API do bạn thiết kế, cấu trúc thống nhất thường giúp client xử lý dễ hơn.

## 5. Bài kiểm thử MockMvc sinh `request-fields.adoc`

Ví dụ triển khai giả định:

- Dự án sử dụng Spring Boot 3.x, Java 17, JUnit 5, MockMvc và Spring REST Docs.
- Endpoint `POST /api/orders` đã tồn tại và trả `201 Created` cho các request hợp lệ.
- Có test dependencies `spring-boot-starter-test` và `spring-restdocs-mockmvc`.

Đoạn kiểm thử dưới đây mô tả danh sách mặt hàng, danh sách tùy chọn, nhãn và mảng lồng nhau. Mục tiêu là sinh snippet dựa trên HTTP request thực sự được gửi.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderArrayDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
            fieldWithPath("items")
                    .type(JsonFieldType.ARRAY)
                    .description("Các mặt hàng của đơn hàng"),
            fieldWithPath("items[].sku")
                    .type(JsonFieldType.STRING)
                    .description("Mã sản phẩm"),
            fieldWithPath("items[].quantity")
                    .type(JsonFieldType.NUMBER)
                    .description("Số lượng đặt"),
            fieldWithPath("items[].options")
                    .type(JsonFieldType.ARRAY)
                    .description("Các tùy chọn cho mặt hàng"),
            fieldWithPath("items[].options[].name")
                    .type(JsonFieldType.STRING)
                    .description("Tên tùy chọn"),
            fieldWithPath("items[].options[].value")
                    .type(JsonFieldType.STRING)
                    .description("Giá trị tùy chọn"),
            fieldWithPath("items[].note")
                    .type(JsonFieldType.STRING)
                    .description("Ghi chú riêng của mặt hàng")
                    .optional(),
            fieldWithPath("tags")
                    .type(JsonFieldType.ARRAY)
                    .description("Các nhãn của đơn hàng"),
            fieldWithPath("tags[]")
                    .type(JsonFieldType.STRING)
                    .description("Một nhãn đơn hàng"),
            fieldWithPath("batches")
                    .type(JsonFieldType.ARRAY)
                    .description("Danh sách nhóm mã"),
            fieldWithPath("batches[]")
                    .type(JsonFieldType.ARRAY)
                    .description("Một nhóm mã"),
            fieldWithPath("batches[][]")
                    .type(JsonFieldType.STRING)
                    .description("Một mã trong nhóm")
    };

    private void verifyAndDocument(String snippetName, String requestJson)
            throws Exception {
        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document(snippetName,
                        requestFields(ORDER_REQUEST_FIELDS)));
    }

    @Test
    void documentOrderWithArrays() throws Exception {
        String requestJson = """
                {
                  "items": [
                    {
                      "sku": "BOOK-001",
                      "quantity": 2,
                      "options": [
                        { "name": "cover", "value": "hard" }
                      ],
                      "note": "Gói làm quà"
                    },
                    {
                      "sku": "PEN-002",
                      "quantity": 1,
                      "options": [
                        { "name": "ink", "value": "blue" }
                      ]
                    }
                  ],
                  "tags": ["gift", "standard"],
                  "batches": [["A-1", "A-2"], ["B-1"]]
                }
                """;

        verifyAndDocument("orders-arrays", requestJson);
    }

    @Test
    void documentOrderWithReorderedItems() throws Exception {
        String requestJson = """
                {
                  "items": [
                    {
                      "sku": "PEN-002",
                      "quantity": 1,
                      "options": [
                        { "name": "ink", "value": "blue" }
                      ]
                    },
                    {
                      "sku": "BOOK-001",
                      "quantity": 2,
                      "options": [
                        { "name": "cover", "value": "hard" }
                      ],
                      "note": "Gói làm quà"
                    }
                  ],
                  "tags": ["standard", "gift"],
                  "batches": [["B-1"], ["A-1", "A-2"]]
                }
                """;

        verifyAndDocument("orders-arrays-reordered", requestJson);
    }
}
```

Hai bài kiểm thử dùng **cùng một bộ `FieldDescriptor`**, trong khi thứ tự của `items`, `tags` và `batches` được đảo. Điều này minh họa vai trò của `[]`: tài liệu mô tả **cấu trúc của phần tử**, không phụ thuộc thứ tự hiện tại. Hai tên snippet khác nhau cũng tránh để hai lần sinh tài liệu ghi vào cùng thư mục.

Khi test vượt qua kỳ vọng HTTP và giai đoạn sinh snippet, đầu ra thường có:

```text
build/generated-snippets/
├── orders-arrays/
│   └── request-fields.adoc
└── orders-arrays-reordered/
    └── request-fields.adoc
```

Trong từng thư mục có thể có thêm các snippet khác như `http-request.adoc`, `http-response.adoc` và `curl-request.adoc` tùy cấu hình. Trường hợp endpoint thực tế trả mã trạng thái khác, hãy điều chỉnh `.andExpect(...)` cho đúng hợp đồng, thay vì thay đổi hành vi endpoint chỉ để chạy ví dụ.

### Kiểm thử này xác nhận gì?

Nó xác nhận request mẫu được gửi tới endpoint, mã HTTP khớp kỳ vọng và các descriptor có thể dùng để sinh bảng request fields. Nó không tự chứng minh:

- `items` luôn có ít nhất một phần tử.
- Mọi phần tử của `items` luôn có `sku` khác rỗng.
- `quantity` luôn là số nguyên dương.
- Các giá trị trong `tags` là duy nhất.
- Mỗi `options` có tên hợp lệ và `value` không rỗng.
- Mọi hoán vị thứ tự đều giữ nguyên kết quả nghiệp vụ.

Muốn kiểm tra các điều kiện này, cần thêm validation và test endpoint với các trường hợp hợp lệ/sai cụ thể.

## 6. Mảng rỗng, trường vắng mặt và giá trị `null`

Ba request dưới đây khác nhau về hợp đồng:

```json
{ "items": [] }
```

```json
{}
```

```json
{ "items": null }
```

| Trường hợp | Ý nghĩa JSON | Điều cần quyết định trong API |
| --- | --- | --- |
| `"items": []` | Trường `items` có mặt, là mảng rỗng | Có chấp nhận danh sách không có mặt hàng? |
| Không có `items` | Không gửi trường `items` | Có được xem là hợp lệ hoặc áp dụng giá trị mặc định? |
| `"items": null` | Có khóa `items`, nhưng giá trị là `null` | Có cho phép `null` hay phải từ chối? |

`.optional()` áp dụng cho mô tả trường **có thể vắng mặt** trong payload được tài liệu hóa. Nó không có nghĩa là mảng được phép rỗng hoặc được phép `null`. Các quy tắc đó cần được thể hiện ở validation và kiểm thử HTTP.

Với **mảng rỗng**, các đường dẫn như `items[].sku` không có phần tử nào để đối chiếu. Vì vậy, bài kiểm thử sinh tài liệu có descriptor trường con bắt buộc có thể thất bại hoặc không có dữ liệu mẫu đại diện. Thực hành tốt là:

1. Sinh bảng trường từ một request có phần tử đại diện.
2. Viết test riêng cho `items: []` để xác nhận hợp đồng nghiệp vụ.
3. Viết test riêng cho việc không gửi `items` và cho `items: null`.
4. Trong mô tả `items`, ghi rõ giới hạn số lượng phần tử, nếu có.

### Thêm Bean Validation để kiểm tra quy tắc thực tế

Ví dụ DTO cho API tạo đơn hàng:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

record CreateOrderRequest(
        @NotEmpty List<@Valid OrderItemRequest> items,
        List<@NotBlank String> tags
) {}

record OrderItemRequest(
        @NotBlank String sku,
        @Min(1) int quantity,
        List<@Valid OrderOptionRequest> options,
        String note
) {}

record OrderOptionRequest(
        @NotBlank String name,
        @NotBlank String value
) {}
```

Ở ví dụ này:

- `@NotEmpty` yêu cầu `items` không là `null` và có ít nhất một phần tử.
- `List<@Valid OrderItemRequest>` kích hoạt validation cho các phần tử object khi framework thực thi validation.
- `@NotBlank` dùng cho các chuỗi cần nội dung.
- `@Min(1)` yêu cầu `quantity` ít nhất là 1.
- `options` và `tags` không bị buộc có phần tử, trừ khi hợp đồng đặt thêm ràng buộc.

Controller cần khai báo `@Valid` thích hợp, chẳng hạn `create(@Valid @RequestBody CreateOrderRequest request)`, cùng dependency validation. Các test HTTP âm tính (negative tests) vẫn cần để khẳng định server từ chối dữ liệu sai theo hợp đồng, ví dụ trả `400 Bad Request`.

**Lưu ý:** ví dụ DTO mô tả các quy tắc cơ bản; muốn xác thực danh sách không có phần tử `null`, tính duy nhất hoặc quan hệ giữa các phần tử, bạn cần thêm ràng buộc và test tương ứng.

## 7. Những nhầm lẫn thường gặp với array path

### 7.1. Nhầm `items.sku` với `items[].sku`

`items` là array, nên không thể nhảy thẳng sang `sku` bằng dấu chấm như một object. Cần đi qua phần tử của mảng: `items[].sku`.

### 7.2. Nhầm `tags` với `tags[]`

`tags` là một mảng; `tags[]` là giá trị phần tử. Nếu `tags` chứa String, mô tả `tags[]` như `JsonFieldType.ARRAY` sẽ sai bản chất dữ liệu.

### 7.3. Dùng `*` thay cho `[]`

`*` thường dùng cho **tên khóa động của object**, chẳng hạn `attributes.*`; `[]` dùng để đi qua **các phần tử array**. Đừng dùng `items.*.sku` để thay thế `items[].sku` khi `items` là mảng.

### 7.4. Coi `.optional()` là validation từng phần tử

Một descriptor `.optional()` có thể vắng mặt trong payload mẫu. Nó không thay thế quy tắc kiểu “trong mỗi object, `sku` phải có mặt và không rỗng”. Hãy kiểm tra cả phần tử đầu, phần tử giữa và phần tử cuối bị thiếu trường quan trọng, nhất là với API nhận danh sách dài.

### 7.5. Mảng object không đồng nhất

Nếu phần tử đầu tiên có `{ "sku": "A" }` và phần tử thứ hai có `{ "productCode": "B" }`, thì một bảng chung chỉ mô tả `items[].sku` có thể gây hiểu nhầm. Cần xác định rõ API có hỗ trợ các biến thể phần tử hay không; khi có nhiều loại, nên có discriminator, quy tắc validation và tài liệu theo từng biến thể.

### 7.6. Chỉ mô tả mảng cha rồi cho rằng đã đầy đủ

Một descriptor như `fieldWithPath("items")` có thể được REST Docs xem là bao phủ cả phần cấu trúc con trong quá trình kiểm tra trường chưa được mô tả. Vì vậy, test không báo lỗi chưa có nghĩa người dùng tài liệu biết về `sku`, `quantity` và `options`. Đối với API cần công bố hợp đồng chi tiết, hãy liệt kê các descriptor con quan trọng.

## 8. Đưa snippet vào Asciidoctor, Markdown và CI

Sau khi test sinh tài liệu chạy thành công, có thể chèn snippet `orders-arrays/request-fields.adoc` vào tài liệu Asciidoctor:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

=== JSON request

include::{snippets}/orders-arrays/http-request.adoc[]

=== Các trường của request payload

include::{snippets}/orders-arrays/request-fields.adoc[]
```

Biến `{snippets}` cần trỏ tới thư mục sinh ra từ test, ví dụ `build/generated-snippets`. Với Gradle và plugin Asciidoctor đã được cấu hình trong dự án, ý tưởng kết nối các task là:

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

Trong CI, thứ tự hợp lý là:

```text
HTTP tests + REST Docs -> generated snippets -> Asciidoctor/Markdown -> tài liệu xuất bản
```

Nếu bài kiểm thử mô tả request thất bại do schema thay đổi, build nên thất bại để không xuất bản tài liệu lỗi thời. Nếu dự án xuất **Markdown**, cần cấu hình template hoặc bước chuyển đổi; không nên mặc định file `request-fields.md` được Spring REST Docs tạo sẵn.

## 9. Bảng xử lý lỗi nhanh

| Hiện tượng | Nguyên nhân có thể gặp | Cách giải quyết |
| --- | --- | --- |
| Descriptor `items[].sku` không khớp | JSON dùng tên mảng khác hoặc cấu trúc không phải array | Đối chiếu JSON thực tế và sửa đường dẫn |
| Descriptor `items.sku` không khớp | Thiếu `[]` tại cấp mảng | Viết `items[].sku` |
| Test chạy với dữ liệu có phần tử nhưng lỗi khi mảng rỗng | Descriptor con bắt buộc không có phần tử đại diện | Tạo test sinh snippet với phần tử đại diện và test rỗng riêng |
| Mô tả của `tags[]` sai kiểu | Nhầm cả array với giá trị phần tử | Tách `tags` (`ARRAY`) và `tags[]` (`STRING`) |
| API vẫn chấp nhận `quantity=0` | Chỉ khai báo descriptor, chưa có validation | Thêm `@Min(1)` và test endpoint |
| Thêm trường vào phần tử nhưng test tài liệu hóa báo lỗi | Chế độ `requestFields` chặt chẽ phát hiện trường chưa mô tả | Bổ sung descriptor, kiểm tra hợp đồng |
| Snippet không xuất hiện sau khi chạy test | Chưa cấu hình REST Docs, `document(...)` hoặc `outputDir` | Kiểm tra cấu hình và tên thư mục output |
| Tài liệu không phân biệt trường có thể bỏ qua | Template hoặc mô tả chưa thể hiện thuộc tính optional | Diễn giải trong `.description(...)` hoặc tùy biến template |

## 10. Bài thực hành và câu hỏi tự đánh giá

Dùng bài test ở mục 5 để thực hiện:

1. **Mảng nguyên thủy:** thêm `"couponCodes": ["WELCOME", "VIP"]`. Khai báo `couponCodes` là `ARRAY` và `couponCodes[]` là `STRING`.
2. **Mảng object sâu hơn:** mỗi phần tử `items` có thêm `"allocations": [{"warehouse": "HCM", "amount": 1}]`. Viết ba descriptor cho mảng, `warehouse` và `amount`.
3. **Thứ tự thay đổi:** đảo vị trí các phần tử trong `items` mà không sửa descriptor. Sinh snippet mới với tên khác và xác nhận đường dẫn `items[].sku` tiếp tục được sử dụng.
4. **Mảng rỗng:** gửi `"items": []` và kiểm tra mã HTTP theo hợp đồng. Nếu `items` phải không rỗng, thêm validation và test trường hợp trả lỗi.
5. **Trường con tùy chọn:** thêm `items[].giftWrap` kiểu Boolean, chỉ có ở một số mặt hàng. Dùng `.optional()` và kiểm tra các biến thể có/không có trường.
6. **Tích hợp build:** include `request-fields.adoc` trong Asciidoctor và chạy chuỗi test → tài liệu. Kiểm tra bảng trường mảng được cập nhật sau khi thêm `couponCodes`.

Tự trả lời các câu hỏi sau trước khi chuyển bài:

- `items`, `items[]` và `items[].sku` khác nhau thế nào?
- Vì sao mảng có chỉ số động nên được mô tả bằng `[]`?
- `batches[][]` biểu diễn cấu trúc gì?
- Khi `items` rỗng, tại sao kiểm thử tài liệu hóa với trường con cần được thiết kế cẩn thận?
- Tại sao `requestFields` không thay thế `@NotEmpty`, `@NotBlank`, `@Min` và các test HTTP âm tính?

**Ghi nhớ:** Mảng là một trường JSON, còn phần tử mảng là một cấp cấu trúc khác. `fieldWithPath("items")` mô tả danh sách, `fieldWithPath("items[]")` mô tả phần tử, và `fieldWithPath("items[].sku")` mô tả một trường của phần tử tại **bất kỳ chỉ số nào**. Khi kết hợp cách mô tả này với kiểm thử và validation đầy đủ, tài liệu Spring REST Docs có thể theo kịp sự thay đổi của payload trong build/CI.
