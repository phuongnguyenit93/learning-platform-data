# Mô tả trường JSON trong response với Spring REST Docs

## 1. Vì sao cần mô tả từng trường JSON?

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Phần **Response payload** tập trung vào dữ liệu mà server thực sự trả về. Khi response có cấu trúc JSON, người tích hợp API cần biết chính xác trường nào tồn tại, kiểu dữ liệu, ý nghĩa nghiệp vụ, trường nào có thể vắng mặt và cấu trúc của các object/mảng lồng nhau.

Spring REST Docs cung cấp `responseFields(...)` và `fieldWithPath(...)` để gắn các mô tả đó với một HTTP exchange đã được kiểm thử:

```java
responseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("customer.email").description("Email của khách hàng"),
    fieldWithPath("items[].sku").description("Mã hàng của từng dòng sản phẩm")
)
```

Mỗi khai báo là một **`FieldDescriptor`**. Trong cấu hình mặc định, Spring REST Docs đối chiếu các descriptor với JSON thực tế; những trường không được tài liệu hóa hoặc trường bắt buộc không tìm thấy có thể làm kiểm thử sinh tài liệu thất bại. Nếu kiểm thử thành công, snippet `response-fields.adoc` có thể được nhúng vào tài liệu Asciidoctor và đưa vào quy trình build/CI.

Mô tả trường là một phần của hợp đồng API. Tuy nhiên, nó không tự xác nhận mọi quy tắc nghiệp vụ, chẳng hạn `totalAmount` phải bằng tổng các dòng hàng hoặc `status` chỉ được nhận các giá trị cho phép. Những điều kiện đó cần thêm assertion hay phép kiểm tra riêng.

## 2. Một response thực tế để làm mẫu

Xét endpoint `GET /api/orders/1024` trả về HTTP `200 OK` và payload:

```json
{
  "orderId": "ORD-1024",
  "status": "CONFIRMED",
  "customer": {
    "id": 15,
    "email": "lan@example.test"
  },
  "items": [
    {
      "sku": "BK-1",
      "quantity": 2,
      "unitPrice": 125000
    },
    {
      "sku": "BK-2",
      "quantity": 1,
      "unitPrice": 90000
    }
  ],
  "totalAmount": 340000,
  "coupon": null,
  "labels": ["new", "online"],
  "metadata": {
    "trace.id": "req-1024"
  },
  "hasMore": false
}
```

Payload có các trường ở cấp gốc, object lồng nhau, mảng object, mảng chuỗi, giá trị `null`, boolean và cả tên thuộc tính chứa dấu chấm. Mỗi dạng cần chọn đường dẫn phù hợp để Spring REST Docs nhận diện đúng.

## 3. Cú pháp đường dẫn của `fieldWithPath`

`fieldWithPath("...")` dùng **đường dẫn theo cấu trúc JSON**, không phải tên getter Java, tên cột database hay biểu thức JSONPath đầy đủ kiểu `$.customer.id`.

| JSON cần mô tả | Đường dẫn Spring REST Docs | Giải thích |
| --- | --- | --- |
| `"orderId": "ORD-1024"` | `orderId` | Trường ở cấp gốc |
| `"customer": {...}` | `customer` | Toàn bộ object khách hàng |
| `"customer": {"id": 15}` | `customer.id` | Trường trong object lồng nhau |
| `"items": [...]` | `items` | Toàn bộ mảng sản phẩm |
| `"items": [{"sku": "BK-1"}]` | `items[].sku` | `sku` của các phần tử object thuộc mảng |
| `"labels": ["new", "online"]` | `labels` | Mảng chuỗi, thường mô tả như một trường `ARRAY` |
| `"metadata": {"trace.id": "..."}` | `metadata['trace.id']` | Khóa JSON chứa dấu chấm, cần dấu ngoặc và dấu nháy |
| `"hasMore": false` | `hasMore` | Trường boolean ở cấp gốc |

### 3.1. Dấu chấm và dấu ngoặc

Với tên thuộc tính thông thường, dùng dot notation:

```java
fieldWithPath("customer.email")
    .description("Email liên hệ của khách hàng");
```

Spring REST Docs còn hỗ trợ bracket notation, hữu ích khi tên khóa chứa dấu chấm, dấu cách hoặc ký tự đặc biệt. Ví dụ hai cấu trúc sau **khác nhau**:

```json
{
  "customer": {
    "email": "lan@example.test"
  },
  "customer.email": "legacy@example.test"
}
```

```java
fieldWithPath("customer.email")
    .description("Email trong object customer");

fieldWithPath("['customer.email']")
    .description("Trường cấp gốc có tên chứa dấu chấm");
```

Dấu chấm bên trong phần tên khóa được đặt trong `['...']` không có nghĩa là chuyển xuống object con. Tương tự, `metadata['trace.id']` trỏ tới **một khóa duy nhất** tên `trace.id` trong object `metadata`.

### 3.2. Mảng object và ký hiệu `[]`

Với:

```json
{
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "BK-2", "quantity": 1}
  ]
}
```

Có thể mô tả mảng và thuộc tính của từng phần tử:

```java
fieldWithPath("items").description("Các dòng hàng trong đơn");

fieldWithPath("items[].sku")
    .description("Mã sản phẩm của từng dòng hàng");

fieldWithPath("items[].quantity")
    .description("Số lượng sản phẩm trong từng dòng hàng");
```

Ký hiệu `[]` biểu diễn các phần tử của mảng, thích hợp với response có số lượng phần tử thay đổi. Không nên cố định chỉ `items[0].sku` nếu hợp đồng API áp dụng cho mọi dòng hàng; path có chỉ số cụ thể chỉ phù hợp khi có lý do tài liệu hóa một vị trí cố định.

**Mảng rỗng là trường hợp cần chú ý.** Nếu response mẫu chứa `"items": []` thì không có phần tử để tìm `items[].sku`. Với các descriptor bắt buộc, kiểm thử sinh tài liệu có thể thất bại. Hãy chọn fixture có phần tử đại diện để mô tả cấu trúc; kiểm tra mảng rỗng trong bài kiểm thử riêng.

### 3.3. Response có root là một mảng

Không phải API nào cũng trả object ở cấp gốc. Với response:

```json
[
  {"id": 1, "name": "Bút"},
  {"id": 2, "name": "Vở"}
]
```

Có thể mô tả root array và các thuộc tính của phần tử:

```java
responseFields(
    fieldWithPath("[]").description("Danh sách sản phẩm"),
    fieldWithPath("[].id").description("Mã sản phẩm"),
    fieldWithPath("[].name").description("Tên sản phẩm")
)
```

Khi tài liệu hóa root array, đường dẫn không có tiền tố như `data` hay `items` vì các tiền tố đó không tồn tại trong JSON thực tế.

## 4. Bài kiểm thử MockMvc đầy đủ

Ví dụ dưới đây dùng JUnit Jupiter, MockMvc và `spring-restdocs-mockmvc`. Dữ liệu được tạo ngay trong controller thử nghiệm để làm rõ quan hệ giữa response JSON và danh sách descriptor. Cần có Jackson trên classpath để Spring MVC serialize `Map` thành JSON.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderJsonFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderResponseFields() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 1024)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-1024"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.totalAmount").value(340000))
                .andDo(document("orders-get-json-fields",
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Mã duy nhất của đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái xử lý đơn hàng"),
                                fieldWithPath("customer")
                                        .description("Thông tin khách hàng"),
                                fieldWithPath("customer.id")
                                        .description("Mã khách hàng"),
                                fieldWithPath("customer.email")
                                        .description("Email liên hệ của khách hàng"),
                                fieldWithPath("items")
                                        .description("Danh sách các dòng hàng"),
                                fieldWithPath("items[].sku")
                                        .description("Mã sản phẩm của dòng hàng"),
                                fieldWithPath("items[].quantity")
                                        .description("Số lượng sản phẩm"),
                                fieldWithPath("items[].unitPrice")
                                        .description("Đơn giá tính bằng VND"),
                                fieldWithPath("totalAmount")
                                        .description("Tổng tiền đơn hàng tính bằng VND"),
                                fieldWithPath("coupon")
                                        .type(JsonFieldType.STRING)
                                        .optional()
                                        .description("Mã ưu đãi, có thể vắng mặt hoặc null"),
                                fieldWithPath("labels")
                                        .description("Các nhãn phục vụ phân loại"),
                                fieldWithPath("metadata")
                                        .description("Thông tin bổ trợ của response"),
                                fieldWithPath("metadata['trace.id']")
                                        .description("Mã tra cứu yêu cầu"),
                                fieldWithPath("hasMore")
                                        .description("Có còn dữ liệu phân trang hay không")
                        )
                ));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable long id) {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("orderId", "ORD-" + id);
            payload.put("status", "CONFIRMED");
            payload.put("customer", Map.of(
                    "id", 15,
                    "email", "lan@example.test"));
            payload.put("items", List.of(
                    Map.of("sku", "BK-1", "quantity", 2,
                           "unitPrice", 125000),
                    Map.of("sku", "BK-2", "quantity", 1,
                           "unitPrice", 90000)));
            payload.put("totalAmount", 340000);
            payload.put("coupon", null);
            payload.put("labels", List.of("new", "online"));
            payload.put("metadata", Map.of("trace.id", "req-1024"));
            payload.put("hasMore", false);
            return payload;
        }
    }
}
```

Ở đây có hai loại đường dẫn cố ý khác nhau:

- Trong assertion `jsonPath("$.items[0].quantity")`, cú pháp JSONPath đi từ gốc `$` và truy cập phần tử đầu tiên để xác nhận dữ liệu.
- Trong tài liệu `fieldWithPath("items[].quantity")`, Spring REST Docs mô tả trường `quantity` của các phần tử mảng mà không gắn hợp đồng với phần tử đầu tiên.

Giá trị `coupon` là `null` trong fixture, nhưng hợp đồng dự kiến đó là mã ưu đãi kiểu chuỗi khi có giá trị. Vì vậy descriptor dùng `type(JsonFieldType.STRING)` để tài liệu thể hiện kiểu dự kiến, và `optional()` khi API cho phép bỏ hẳn trường đó ở một response khác. Hai đặc điểm này mang ý nghĩa riêng.

Trong ứng dụng Spring Boot, có thể thay controller thử nghiệm bằng controller thực cùng `@WebMvcTest` hoặc `@SpringBootTest` và cấu hình REST Docs phù hợp. Các descriptor vẫn có thể sử dụng với WebTestClient/REST Assured; chỉ phần thiết lập kiểm thử và cách gắn thao tác tài liệu hóa thay đổi.

## 5. Hiểu và chỉ định kiểu dữ liệu JSON

Spring REST Docs thường suy ra kiểu của trường từ JSON đã ghi nhận. Bảng dưới đây dùng các kiểu của `JsonFieldType`:

| Kiểu | Ví dụ | Dùng khi |
| --- | --- | --- |
| `STRING` | `"ORD-1024"` | Chuỗi ký tự, mã định danh, timestamp biểu diễn dưới dạng chuỗi |
| `NUMBER` | `125000`, `2.5` | Số JSON, gồm số nguyên và số thập phân |
| `BOOLEAN` | `true`, `false` | Giá trị luận lý |
| `OBJECT` | `{"id": 15}` | Object JSON |
| `ARRAY` | `["new", "online"]` | Mảng JSON |
| `NULL` | `null` | Giá trị null thực tế |
| `VARIES` | Trường có nhiều kiểu trong dữ liệu mẫu | Khi kiểu trường thay đổi giữa các phần tử/ngữ cảnh được xử lý |

Ví dụ trường `coupon` chỉ trả `null` trong fixture thường không đủ để suy ra rằng hợp đồng nghiệp vụ của nó là chuỗi; việc khai báo rõ giúp bảng sinh ra không gây hiểu nhầm:

```java
fieldWithPath("coupon")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Mã ưu đãi, nếu được áp dụng");
```

Ngoài kiểu JSON, phần mô tả có thể làm rõ đơn vị và định dạng. Ví dụ `totalAmount` là `NUMBER` nhưng người đọc vẫn cần biết số tiền theo VND hay đơn vị nhỏ nhất; `createdAt` là `STRING` nhưng cần biết dùng ISO 8601, múi giờ nào; `status` là `STRING` nhưng phải công bố các giá trị hợp lệ. Không suy các ý nghĩa đó chỉ từ loại dữ liệu.

**Phân biệt hai lớp kiểm tra:** `type(...)` điều khiển thông tin kiểu được dùng trong tài liệu sinh ra; khi cần bảo đảm dữ liệu có kiểu hoặc định dạng bắt buộc, hãy viết assertion/schema validation tương ứng. Không coi bảng trường là phép chứng minh mọi quy tắc định dạng và nghiệp vụ.

## 6. Trường bắt buộc, tùy chọn, bị bỏ qua và `null`

Một field descriptor mặc định đại diện cho trường cần được tìm thấy trong response mẫu. Các modifier hữu ích:

```java
fieldWithPath("invoiceNumber")
    .optional()
    .description("Số hóa đơn, chỉ có sau khi phát hành");

fieldWithPath("debug.traceId")
    .optional()
    .ignored();
```

| Tình huống | Cách khai báo | Ý nghĩa |
| --- | --- | --- |
| Trường phải xuất hiện | `fieldWithPath("orderId")` | Mô tả trường bắt buộc trong fixture tài liệu |
| Trường có thể không xuất hiện | `fieldWithPath("coupon").optional()` | Cho phép không tìm thấy path |
| Trường xuất hiện nhưng không muốn hiện trong bảng | `fieldWithPath("debug.traceId").ignored()` | Đánh dấu đã xử lý mà không đưa vào bảng trường |
| Trường chỉ có `null` trong fixture, dự kiến có kiểu khác | `.type(JsonFieldType.STRING)` | Chỉ định kiểu dự kiến trình bày |
| Trường con của object tùy chọn | Mô tả các đường dẫn con với chiến lược phù hợp | Tránh bắt buộc tìm trường con khi cả object có thể vắng mặt |

Cần phân biệt ba payload:

```json
{"coupon": "SAVE10"}
```

```json
{"coupon": null}
```

```json
{}
```

Trường hợp đầu có chuỗi, trường hợp thứ hai **có trường với giá trị `null`**, còn trường hợp cuối **không có trường**. `optional()` giải quyết việc trường có thể thiếu; nó không thay thế mô tả ngữ nghĩa của `null` hay phép kiểm tra giá trị hợp lệ.

Khi object cha có thể vắng mặt (ví dụ `shippingAddress` chỉ có với đơn giao hàng), hãy thiết kế ví dụ response và các descriptor con nhất quán. Nếu cần mô tả sâu toàn bộ cấu trúc địa chỉ, dùng fixture có `shippingAddress` và xác nhận những trường con được yêu cầu. Nếu tài liệu chỉ cần nói về nhánh địa chỉ ở mức khái quát, xem cách dùng `subsectionWithPath` bên dưới.

## 7. Mô tả từng trường hay chỉ mô tả cả nhánh?

Có ba lựa chọn phổ biến:

**Mô tả chi tiết** khi người sử dụng API cần cấu trúc bên trong:

```java
responseFields(
    fieldWithPath("customer").description("Khách hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.email").description("Email liên hệ")
)
```

**Mô tả một subsection** khi muốn coi toàn bộ nhánh là một mục tài liệu:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    subsectionWithPath("customer")
        .description("Chi tiết khách hàng, được mô tả ở tài liệu riêng")
)
```

`subsectionWithPath("customer")` cho phép bao quát nhánh `customer` và các trường con trong kiểm tra tài liệu hóa. Đổi lại, snippet này không liệt kê riêng `customer.id` và `customer.email`.

**Chỉ mô tả một tập con** khi có lý do chấp nhận các trường khác chưa được tài liệu hóa:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng")
)
```

`relaxedResponseFields` không báo lỗi chỉ vì response có trường ngoài danh sách; các trường đã khai báo vẫn phải được tìm thấy trừ khi được đánh dấu `optional()`. Đây là lựa chọn có đánh đổi: những trường mới có thể xuất hiện mà bài kiểm thử tài liệu không phát hiện. Với API công khai cần theo dõi thay đổi hợp đồng, nên ưu tiên `responseFields` ở chế độ mặc định và khai báo những nhánh cần bỏ qua một cách có chủ đích.

## 8. Thiết kế mô tả trường có ích cho người tích hợp

Một descriptor tốt trả lời **trường dùng để làm gì**, không chỉ dịch lại tên biến.

| Path | Mô tả quá chung | Mô tả hữu ích hơn |
| --- | --- | --- |
| `orderId` | ID | Mã định danh duy nhất dùng để tra cứu đơn hàng |
| `status` | Trạng thái | Trạng thái xử lý; ví dụ `PENDING`, `CONFIRMED`, `CANCELLED` nếu thực tế API hỗ trợ |
| `items[].quantity` | Số lượng | Số đơn vị đặt mua trong một dòng hàng; phải lớn hơn 0 nếu đây là ràng buộc của API |
| `items[].unitPrice` | Giá | Đơn giá của một đơn vị sản phẩm, tính theo VND |
| `totalAmount` | Tổng | Tổng tiền phải thanh toán bằng VND, theo quy tắc tính của dịch vụ |
| `coupon` | Coupon | Mã ưu đãi đã áp dụng; vắng mặt hoặc `null` khi không có ưu đãi |

Các giá trị liệt kê, đơn vị tiền, quy tắc làm tròn, mức độ nhạy cảm và ý nghĩa của giá trị `null` phải được xác nhận từ hợp đồng API thực tế trước khi công bố. Ví dụ ở đây chỉ minh họa cách viết, không tự đặt ra cam kết nghiệp vụ cho một hệ thống đang vận hành.

Một danh sách tự rà soát khi đặt descriptor:

1. Path trùng với JSON sau serialization, bao gồm tên khóa theo `@JsonProperty` hay naming strategy.
2. Với array object, đường dẫn có `[]` ở đúng vị trí.
3. Những khóa chứa dấu chấm được đặt trong bracket notation.
4. Kiểu dữ liệu, định dạng, đơn vị và giá trị có thể thiếu được mô tả rõ.
5. Không vô tình đưa thông tin nội bộ hoặc nhạy cảm vào **response mẫu** và tài liệu xuất bản.
6. Phần mô tả không phụ thuộc vào cách cài đặt nội bộ mà người tích hợp API không cần biết.

## 9. Sinh bảng trường và nhúng vào Asciidoctor

Với tên định danh `orders-get-json-fields` trong lời gọi `document(...)`, build thông dụng tạo:

```text
build/generated-snippets/
└── orders-get-json-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Đây là các tệp tiêu biểu liên quan tới ví dụ; danh sách thực tế phụ thuộc vào cấu hình snippet. Với Maven, thư mục mặc định thường là `target/generated-snippets`; đường dẫn cũng có thể được cấu hình lại.

Bảng trong `response-fields.adoc` thường thể hiện ba cột chính: **Path**, **Type** và **Description**. Từng hàng lấy từ descriptor và dữ liệu được kiểm thử. Trong tài liệu Asciidoctor:

```adoc
= Order API
:snippets: build/generated-snippets

== Xem đơn hàng

=== HTTP response
include::{snippets}/orders-get-json-fields/http-response.adoc[]

=== Các trường JSON
include::{snippets}/orders-get-json-fields/response-fields.adoc[]
```

Hãy đảm bảo task chạy bài kiểm thử tạo snippet hoàn tất trước task biên soạn Asciidoctor. Trong CI, kiểm thử thất bại do khác biệt response/descriptor cần khiến pipeline thất bại để tránh xuất bản tài liệu không phản ánh hợp đồng hiện tại. Nếu dự án muốn trình bày tài liệu cuối dưới dạng Markdown, cần pipeline hoặc template chuyển đổi phù hợp; snippet `response-fields.adoc` mặc định vẫn là Asciidoctor.

## 10. Lỗi hay gặp khi mô tả JSON

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Báo trường response chưa được tài liệu hóa | Có key mới, quên descriptor cho trường con, hoặc sử dụng nhầm đường dẫn | Xem JSON thực tế, bổ sung descriptor đúng path; cân nhắc `subsectionWithPath` khi cần |
| Báo trường đã khai báo không xuất hiện | Path sai, key bị đổi tên, field bị loại khỏi JSON, mảng rỗng | Kiểm tra payload đã serialize; sửa path hoặc dùng `optional()` nếu thực sự được phép thiếu |
| `items.sku` không khớp với mảng object | Thiếu ký hiệu mảng | Dùng `items[].sku` |
| `metadata.trace.id` không khớp với khóa `trace.id` | Dấu chấm trong **tên khóa** bị hiểu thành cấp lồng nhau | Dùng `metadata['trace.id']` |
| Bảng mô tả kiểu `NULL` dù hợp đồng nói kiểu chuỗi | Fixture chỉ có giá trị `null` | Cân nhắc `.type(JsonFieldType.STRING)` và mô tả ngữ nghĩa `null` |
| Mô tả trường thiếu đơn vị hay định dạng | Chỉ ghi lại tên thuộc tính | Bổ sung đơn vị, giá trị hợp lệ, thời gian, ý nghĩa nghiệp vụ |
| Không tìm thấy `response-fields.adoc` | Test chưa chạy, chưa dùng `document`, hoặc vị trí output khác dự kiến | Kiểm tra trạng thái test và cấu hình thư mục generated snippets |
| Nội dung tài liệu cũ sau khi đổi DTO | Bước tài liệu chạy trước hoặc thiếu phụ thuộc vào test | Thiết lập build sinh snippet rồi mới biên soạn tài liệu |

## 11. Bài thực hành

Từ response đơn hàng ở mục 2, hãy thực hiện từng thay đổi:

1. Thêm `"createdAt": "2026-11-17T02:00:00Z"` vào response. Chạy lại bài kiểm thử ở chế độ mặc định, quan sát lỗi thiếu descriptor; thêm mô tả về định dạng thời gian và múi giờ.
2. Chuyển `metadata` từ `{"trace.id": "..."}` sang `{"trace": {"id": "..."}}`. Điều chỉnh path tương ứng từ `metadata['trace.id']` thành `metadata.trace.id` và giải thích vì sao hai path không tương đương.
3. Thử `"items": []`. Quan sát sự khác biệt giữa mô tả mảng `items` và các descriptor con `items[].sku`; tách fixture phục vụ sinh tài liệu cấu trúc khỏi bài kiểm thử ca mảng rỗng.
4. Trả root array thay vì object và viết `responseFields(...)` dùng `[]` cùng `[].id`, `[].name`.
5. Thêm trường tùy chọn `deliveryNote`. Kiểm thử một lần có trường và một lần vắng trường, ghi rõ khi nào nên dùng `optional()`.
6. Chèn `response-fields.adoc` vào tài liệu Asciidoctor và xác minh bảng đã cập nhật sau khi sửa response.

**Kết quả mong đợi:** bạn có thể đọc một JSON response bất kỳ, xác định đúng path cho trường đơn, object, mảng, root array và khóa đặc biệt; viết descriptor với kiểu/ý nghĩa chính xác; phân biệt trường thiếu với `null`; và duy trì bảng response sinh từ bài kiểm thử HTTP trong quy trình build/CI.
