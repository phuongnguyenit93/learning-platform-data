# Phân biệt trường bắt buộc, tùy chọn và có thể null trong response payload

## 1. Mục tiêu của bài học

Trong chương **Response payload** của module **SPRING_REST_DOCS**, tài liệu REST API được sinh từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Mỗi trường JSON cần mô tả không chỉ tên và kiểu dữ liệu, mà còn **có bắt buộc xuất hiện hay không** và **có được trả giá trị `null` hay không**.

Hai thuộc tính này độc lập:

- **Bắt buộc xuất hiện (required / present)**: phản hồi phải chứa key hoặc đường dẫn JSON tương ứng.
- **Tùy chọn (optional / may be absent)**: phản hồi có thể bỏ hẳn key đó.
- **Có thể null (nullable)**: key có thể xuất hiện với giá trị JSON `null`.
- **Không được null (non-null)**: nếu key xuất hiện, giá trị của nó phải khác `null`.

Mục tiêu của bài là hiểu chính xác những khác biệt trên, khai báo `responseFields(...)` và `fieldWithPath(...)` phù hợp, rồi kết hợp assertion để xác minh hợp đồng API. Đây cũng là nền tảng để sinh `response-fields.adoc`, biên soạn tài liệu Asciidoctor/Markdown và kiểm tra thay đổi hợp đồng trong build/CI.

> **Lưu ý cốt lõi:** Spring REST Docs có `FieldDescriptor.optional()` để nới điều kiện **sự hiện diện** của trường. Nó không có modifier `nullable()` tương ứng để tự kiểm chứng việc cho phép hoặc cấm `null`. Tính nullable cần được mô tả rõ và kiểm thử riêng khi quan trọng đối với hợp đồng API.

## 2. Nhận diện ba trạng thái của một key JSON

Xem ba response khác nhau của cùng một endpoint:

### Trường hiện diện và có giá trị

```json
{
  "discountCode": "WELCOME10"
}
```

Key `discountCode` **tồn tại**, và giá trị là chuỗi.

### Trường hiện diện nhưng giá trị null

```json
{
  "discountCode": null
}
```

Key `discountCode` **vẫn tồn tại**, dù giá trị của nó là `null`.

### Trường hoàn toàn vắng mặt

```json
{}
```

Response không chứa key `discountCode`. Đây là một tình huống khác với `"discountCode": null`: client có thể phân biệt hai payload bằng cách kiểm tra sự tồn tại của key.

Hai cặp thuộc tính **required/optional** và **nullable/non-null** tạo ra bốn dạng hợp đồng:

| Hợp đồng trường | Có thể vắng key? | Cho phép giá trị `null`? | Ví dụ hợp lệ |
| --- | --- | --- | --- |
| Bắt buộc, không null | Không | Không | `{"orderId":"ORD-304"}` |
| Bắt buộc, có thể null | Không | Có | `{"discountCode":null}` hoặc chuỗi |
| Tùy chọn, không null | Có | Không, nếu key xuất hiện | `{}` hoặc `{"delivery":{"method":"STANDARD"}}` |
| Tùy chọn, có thể null | Có | Có | `{}`, `{"note":null}` hoặc chuỗi |

Không nên coi hai quy tắc sau là tương đương:

- “Trường `discountCode` phải hiện diện, nhưng có thể mang giá trị `null`” là **required + nullable**.
- “Trường `discountCode` có thể không được trả về” là **optional**, bất kể khi xuất hiện nó có thể null hay không.

Điều này ảnh hưởng trực tiếp đến cách client xử lý response. Một client có thể sử dụng `containsKey("discountCode")` để phân biệt vắng mặt và null, còn một kiểu dữ liệu không hỗ trợ giá trị thiếu có thể làm mất sự khác biệt khi deserialization.

## 3. `responseFields(...)` kiểm tra điều gì?

Spring REST Docs mô tả response bằng các descriptor:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("orderId")
        .description("Mã định danh đơn hàng"),
    fieldWithPath("discountCode")
        .description("Mã ưu đãi; null nếu đơn không có ưu đãi")
)
```

Với `responseFields` mặc định:

1. Một trường **đã khai báo và không đánh dấu optional** mà không tìm thấy trong payload sẽ khiến việc sinh snippet thất bại.
2. Một trường **xuất hiện nhưng chưa được mô tả** cũng có thể khiến việc sinh snippet thất bại.
3. Một trường **đã khai báo với `.optional()`** có thể không xuất hiện mà không bị xem là lỗi thiếu trường.
4. Một đường dẫn xuất hiện với giá trị `null` khác với đường dẫn không xuất hiện; `null` không tự động có nghĩa là “optional”.

Ví dụ khai báo trường có thể vắng:

```java
import org.springframework.restdocs.payload.JsonFieldType;

fieldWithPath("delivery")
    .type(JsonFieldType.OBJECT)
    .optional()
    .description("Thông tin giao hàng; có thể vắng nếu chưa chọn giao hàng");
```

**Chi tiết dễ bỏ sót:** nếu một trường tùy chọn **không xuất hiện trong fixture**, Spring REST Docs không thể suy ra kiểu JSON của trường đó từ response. Để sinh snippet đầy đủ, cần khai báo rõ `.type(JsonFieldType.OBJECT)`, `.type(JsonFieldType.STRING)` hoặc kiểu phù hợp. Chỉ thêm `.optional()` có thể giải quyết lỗi “thiếu trường” nhưng vẫn dẫn tới lỗi “không xác định được kiểu trường”.

### 3.1. `.type(...)` có ý nghĩa gì?

`type(JsonFieldType.STRING)` giúp mô tả kiểu **trong tài liệu được sinh**. Nó không phải là phép kiểm tra tổng quát bảo đảm mọi response có đúng kiểu chuỗi. Khi hợp đồng yêu cầu giá trị khác `null` hoặc kiểu/định dạng cụ thể, hãy thêm assertion riêng.

Các kiểu JSON phổ biến:

| `JsonFieldType` | Dữ liệu JSON tương ứng |
| --- | --- |
| `STRING` | `"ORD-304"` |
| `NUMBER` | `125000` |
| `BOOLEAN` | `true`, `false` |
| `OBJECT` | `{"method":"STANDARD"}` |
| `ARRAY` | `[{"sku":"B-01"}]` |
| `NULL` | `null` |
| `VARIES` | Nhiều lần xuất hiện của một path có kiểu khác nhau |

Khi fixture chỉ chứa `"discountCode": null`, REST Docs có thể suy ra kiểu `NULL` từ dữ liệu. Nếu hợp đồng cho phép `discountCode` là chuỗi hoặc null, hãy chỉ định kiểu `STRING` và diễn giải rõ tính nullable trong `description`.

## 4. Thiết kế hợp đồng response cho đơn hàng

Xét endpoint `GET /api/orders/304` với hai chế độ trả dữ liệu.

**Bản đầy đủ** (`GET /api/orders/304?view=full`):

```json
{
  "orderId": "ORD-304",
  "status": "CONFIRMED",
  "totalAmount": 125000,
  "discountCode": null,
  "delivery": {
    "method": "STANDARD",
    "trackingNumber": null
  },
  "items": [
    {
      "sku": "B-01",
      "quantity": 2,
      "note": null
    }
  ]
}
```

**Bản rút gọn** (`GET /api/orders/304?view=compact`):

```json
{
  "orderId": "ORD-304",
  "status": "CONFIRMED",
  "totalAmount": 125000,
  "discountCode": null,
  "items": [
    {
      "sku": "B-01",
      "quantity": 2
    }
  ]
}
```

Hai payload thể hiện các nhóm trường:

| Path | Hợp đồng ví dụ | Giải thích |
| --- | --- | --- |
| `orderId` | Bắt buộc, không null | Luôn cần mã đơn hàng |
| `status` | Bắt buộc, không null | Luôn có trạng thái đơn |
| `totalAmount` | Bắt buộc, không null | Tổng tiền bằng VND |
| `discountCode` | Bắt buộc, có thể null | Key luôn tồn tại; không có ưu đãi thì null |
| `delivery` | Tùy chọn, không null nếu có | Chế độ compact không trả nhánh giao hàng |
| `delivery.method` | Bắt buộc khi `delivery` có mặt | Điều kiện phụ thuộc vào object cha |
| `delivery.trackingNumber` | Có thể null khi `delivery` có mặt | Chưa có mã theo dõi thì null |
| `items` | Bắt buộc, không null | Mảng dòng hàng |
| `items[].sku` | Bắt buộc trong từng item, không null | Mã sản phẩm |
| `items[].quantity` | Bắt buộc trong từng item, không null | Số lượng |
| `items[].note` | Tùy chọn và có thể null | Một item có thể không có key hoặc có giá trị null |

Các quy tắc trên là **hợp đồng minh họa của API mẫu**, không mặc nhiên đúng với mọi hệ thống. Ví dụ một API khác có thể bỏ hẳn `discountCode` khi không có ưu đãi, hoặc luôn trả `delivery: null` thay vì bỏ key.

## 5. Kiểm thử MockMvc: xác minh cả trường vắng mặt và null

Ví dụ sau dùng JUnit Jupiter, Spring MVC, Jackson và `spring-restdocs-mockmvc`. Lớp controller thử nghiệm tạo hai response để tài liệu hóa chính xác hai biến thể của cùng hợp đồng.

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
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OptionalNullableOrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    private static FieldDescriptor[] orderFields() {
        return new FieldDescriptor[] {
                fieldWithPath("orderId")
                        .description("Mã đơn hàng, luôn hiện diện"),
                fieldWithPath("status")
                        .description("Trạng thái xử lý đơn hàng"),
                fieldWithPath("totalAmount")
                        .description("Tổng tiền đơn hàng, tính bằng VND"),

                // Bắt buộc hiện diện, nhưng giá trị được phép null.
                fieldWithPath("discountCode")
                        .type(JsonFieldType.STRING)
                        .description("Mã giảm giá; null khi không áp dụng"),

                // Object cha có thể vắng trong response compact.
                fieldWithPath("delivery")
                        .type(JsonFieldType.OBJECT)
                        .optional()
                        .description("Thông tin giao hàng; có thể vắng"),

                // Các đường dẫn con cũng có thể vắng nếu thiếu object cha.
                fieldWithPath("delivery.method")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Phương thức giao hàng khi có delivery"),
                fieldWithPath("delivery.trackingNumber")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Mã theo dõi; null khi chưa được cấp"),

                fieldWithPath("items")
                        .description("Các dòng hàng trong đơn"),
                fieldWithPath("items[].sku")
                        .description("Mã sản phẩm trong dòng hàng"),
                fieldWithPath("items[].quantity")
                        .description("Số lượng sản phẩm"),

                // Có thể thiếu ở item hoặc có giá trị null.
                fieldWithPath("items[].note")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Ghi chú của dòng hàng; có thể thiếu hoặc null")
        };
    }

    @Test
    void documentFullOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 304)
                        .param("view", "full")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-304"))
                .andExpect(jsonPath("$.discountCode").hasJsonPath())
                .andExpect(jsonPath("$.discountCode").value(nullValue()))
                .andExpect(jsonPath("$.delivery.method").value("STANDARD"))
                .andExpect(jsonPath("$.delivery.trackingNumber").hasJsonPath())
                .andExpect(jsonPath("$.delivery.trackingNumber")
                        .value(nullValue()))
                .andExpect(jsonPath("$.items[0].note").hasJsonPath())
                .andDo(document("orders-full-response",
                        responseFields(orderFields())));
    }

    @Test
    void documentCompactOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 304)
                        .param("view", "compact")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.discountCode").hasJsonPath())
                .andExpect(jsonPath("$.discountCode").value(nullValue()))
                .andExpect(jsonPath("$.delivery").doesNotHaveJsonPath())
                .andExpect(jsonPath("$.items[0].note").doesNotHaveJsonPath())
                .andDo(document("orders-compact-response",
                        responseFields(orderFields())));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(
                @PathVariable("id") long id,
                @RequestParam(name = "view", defaultValue = "full")
                String view) {

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("orderId", "ORD-" + id);
            body.put("status", "CONFIRMED");
            body.put("totalAmount", 125000);
            body.put("discountCode", null);

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sku", "B-01");
            item.put("quantity", 2);

            if ("full".equals(view)) {
                item.put("note", null);
                Map<String, Object> delivery = new LinkedHashMap<>();
                delivery.put("method", "STANDARD");
                delivery.put("trackingNumber", null);
                body.put("delivery", delivery);
            }

            body.put("items", List.of(item));
            return body;
        }
    }
}
```

Ví dụ dùng `LinkedHashMap` vì nó chấp nhận các giá trị `null` và giúp thể hiện rõ việc **chủ động thêm hoặc bỏ key**. `Map.of(...)` của Java không chấp nhận key hoặc value null, nên không phù hợp để tạo fixture có `discountCode: null`.

Trong ứng dụng thực, có thể thay controller minh họa bằng controller thật và cấu hình `@WebMvcTest`, `@SpringBootTest` hoặc WebTestClient/REST Assured tương ứng. Các descriptor `fieldWithPath` và nguyên tắc bắt buộc/tùy chọn vẫn giữ nguyên.

### 5.1. Vì sao các descriptor con cũng cần `optional()`?

`delivery` có thể vắng ở bản compact, nên các path `delivery.method` và `delivery.trackingNumber` cũng không tồn tại ở bản đó.

Việc đánh dấu `.optional()` trên descriptor con là để **bài kiểm thử sinh tài liệu cho cả hai biến thể** chạy được. Tuy nhiên, điều này không tự đảm bảo quy tắc “nếu `delivery` xuất hiện thì `delivery.method` bắt buộc phải có”. Bài kiểm thử biến thể full cần assertion như:

```java
.andExpect(jsonPath("$.delivery.method").isString())
```

Nếu cần xác minh quy tắc có điều kiện trên nhiều response, có thể kiểm tra `JsonNode` sau khi giải mã hoặc dùng JSON Schema, tùy yêu cầu hệ thống.

### 5.2. Phân biệt các matcher JSONPath trong MockMvc

Các matcher này **không đồng nghĩa**:

| Matcher | Ý nghĩa |
| --- | --- |
| `jsonPath("$.x").hasJsonPath()` | Có key/path, kể cả khi giá trị là `null` |
| `jsonPath("$.x").doesNotHaveJsonPath()` | Không có key/path, kể cả dạng null cũng bị xem là có path |
| `jsonPath("$.x").exists()` | Có giá trị **khác null** tại path |
| `jsonPath("$.x").doesNotExist()` | Không tìm thấy giá trị khác null; có thể vẫn tồn tại key mang null |
| `jsonPath("$.x").value(nullValue())` | Giá trị quan sát được là null |
| `jsonPath("$.x").isString()` | Giá trị quan sát được có kiểu chuỗi |

Để kiểm tra **key có mặt và là null**, dùng `hasJsonPath()` kết hợp `value(nullValue())`. Để xác nhận **key thực sự bị bỏ đi**, dùng `doesNotHaveJsonPath()`. Chỉ dùng `doesNotExist()` để nói “trường vắng mặt” là không đủ chặt vì matcher này xem cả null như một giá trị không tồn tại.

Đường dẫn của `jsonPath("$.delivery.method")` tuân theo cú pháp JSONPath của Spring Test, trong khi descriptor `fieldWithPath("delivery.method")` dùng cú pháp của Spring REST Docs. Hai cú pháp tương tự nhưng không hoàn toàn giống nhau; ví dụ JSONPath có tiền tố `$`.

## 6. Trường có thể null và cách sinh thông tin kiểu

Xét response:

```json
{
  "discountCode": null,
  "trackingNumber": null
}
```

Nếu không chỉ định kiểu, REST Docs chỉ nhìn thấy giá trị `null`. Khi tài liệu cần nói rõ giá trị thường là chuỗi, dùng:

```java
responseFields(
    fieldWithPath("discountCode")
        .type(JsonFieldType.STRING)
        .description("Mã ưu đãi; key bắt buộc, giá trị có thể null"),

    fieldWithPath("trackingNumber")
        .type(JsonFieldType.STRING)
        .description("Mã theo dõi; null trước khi đơn được giao vận chuyển")
)
```

Cả hai trường trong ví dụ trên **không** có `optional()` vì yêu cầu của hợp đồng là key luôn xuất hiện. `.type(JsonFieldType.STRING)` chỉ thể hiện kiểu nghiệp vụ dự kiến trong bảng; phần mô tả cho biết giá trị null có ý nghĩa gì.

Nếu response mẫu là `{}` nhưng bạn viết một field `optional()`, hãy khai báo kiểu tường minh:

```java
fieldWithPath("deliveryDate")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Ngày dự kiến giao, có thể không trả về; định dạng YYYY-MM-DD");
```

Không thể mong REST Docs tự suy ra `STRING` từ một key hoàn toàn không xuất hiện. Nếu chỉ thêm `optional()` mà bỏ `type(...)`, có thể gặp lỗi xác định kiểu khi sinh bảng trường.

### 6.1. Có cần `JsonFieldType.NULL` không?

`JsonFieldType.NULL` mô tả một giá trị JSON null. Dùng kiểu này khi **chính kiểu null** là điều muốn trình bày. Với một trường “chuỗi hoặc null”, thường nên mô tả loại dữ liệu có ý nghĩa nghiệp vụ là `STRING`, rồi giải thích khả năng null trong `description`. Nếu API có một trường luôn null một cách có chủ đích, hãy giải thích lý do tồn tại của nó vì nó ít hữu ích cho người đọc.

### 6.2. Có nên đặt cả `optional()` và `type(...)`?

Có, nếu key **được phép vắng**. `optional()` và `type(...)` giải quyết hai vấn đề khác nhau:

```java
fieldWithPath("couponDescription")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Mô tả ưu đãi; thiếu khi không có chiến dịch");
```

- `optional()`: không xem việc thiếu path là lỗi của descriptor.
- `type(JsonFieldType.STRING)`: giúp bảng trường có kiểu dữ liệu ổn định, ngay cả khi fixture hiện tại không chứa path.
- `description(...)`: nói rõ khi nào trường vắng hoặc null, vì type và optional không truyền tải đầy đủ quy tắc đó.

## 7. Khi parent object, mảng hoặc phần tử lặp có thể vắng

### 7.1. Parent object có thể vắng, có thể null hoặc có object

Ba payload:

```json
{}
```

```json
{"delivery": null}
```

```json
{"delivery": {"method": "STANDARD"}}
```

Nếu `delivery` được phép vắng, dùng:

```java
fieldWithPath("delivery")
    .optional()
    .type(JsonFieldType.OBJECT)
    .description("Thông tin giao hàng; có thể thiếu hoặc null");

fieldWithPath("delivery.method")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Phương thức giao hàng khi delivery có object");
```

Tuy nhiên, quy tắc “`delivery.method` bắt buộc khi `delivery` là object” cần kiểm tra riêng trong các ca có object. Khi cha là null, path `delivery.method` không tồn tại, nên descriptor con phải được tính toán theo các biến thể response được kiểm thử.

Nếu hợp đồng thực tế **bắt buộc key `delivery` xuất hiện** nhưng giá trị có thể null, bỏ `optional()` khỏi descriptor `delivery`, còn descriptor con vẫn có thể optional vì cha đôi khi là null.

### 7.2. Mảng rỗng khác với mảng thiếu và mảng null

```json
{"items": []}
```

```json
{}
```

```json
{"items": null}
```

Ba response không giống nhau:

- `items: []`: key có mặt, giá trị là **mảng rỗng**.
- `{}`: key `items` không có.
- `items: null`: key có mặt, giá trị null.

Nếu hợp đồng yêu cầu `items` luôn là mảng, descriptor `fieldWithPath("items")` chỉ mô tả trường cần có; assertion `jsonPath("$.items").isArray()` cần được dùng để xác minh nó thực sự là mảng, kể cả rỗng. Khi yêu cầu có ít nhất một phần tử, hãy bổ sung kiểm tra kích thước.

Với `fieldWithPath("items[].sku")`, fixture `items: []` không có giá trị `sku` để quan sát. Khi sinh tài liệu chi tiết, nên dùng fixture có ít nhất một phần tử đại diện. Ca mảng rỗng và quy tắc “mọi phần tử đều có `sku`” cần được kiểm thử bằng assertion riêng.

### 7.3. Một số phần tử có field, một số phần tử không có

```json
{
  "items": [
    {"sku": "B-01", "note": "Gói quà"},
    {"sku": "B-02"},
    {"sku": "B-03", "note": null}
  ]
}
```

Descriptor chung có thể là:

```java
fieldWithPath("items[].note")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Ghi chú tùy chọn cho từng dòng hàng, có thể null");
```

Việc tìm thấy path `items[].note` tại một số phần tử không chứng minh tất cả phần tử đều tuân thủ cùng quy tắc về presence/null. Đối với ràng buộc từng phần tử, parse JSON thành `JsonNode` rồi kiểm tra mọi item hoặc dùng JSON Schema. Spring REST Docs giúp tạo tài liệu và phát hiện nhiều thay đổi cấu trúc; nó không thay thế toàn bộ validation của dữ liệu lặp.

## 8. Null trong DTO Java và serialization

Tài liệu `responseFields` phải phản ánh **JSON thực sự trả cho client**, không suy trực tiếp từ việc một field Java có kiểu `String`, `Optional<String>` hoặc gắn annotation `@Nullable`.

Ví dụ, một DTO có giá trị Java null:

```java
record OrderDto(
    String orderId,
    String discountCode
) {}
```

Có thể được serialize thành:

```json
{"orderId":"ORD-304","discountCode":null}
```

Nhưng khi cấu hình Jackson loại bỏ trường null, chẳng hạn:

```java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
record OrderDto(
    String orderId,
    String discountCode
) {}
```

thì JSON có thể trở thành:

```json
{"orderId":"ORD-304"}
```

Do đó **cùng một giá trị Java null** có thể dẫn đến hai hợp đồng response khác nhau tùy cấu hình serialization. Các thiết lập như `@JsonInclude`, `@JsonProperty`, naming strategy, custom serializer và bộ lọc trường đều có thể ảnh hưởng đến path thực tế.

Không nên đánh dấu một trường là `optional()` chỉ vì kiểu Java có thể null. Trước hết hãy kiểm tra JSON qua HTTP test và xác định hợp đồng công khai của API.

## 9. Ghi rõ nullable trong snippet và tài liệu xuất bản

Mặc định `response-fields.adoc` trình bày bảng gồm các thông tin như **Path**, **Type**, **Description**. Để người đọc phân biệt “key có thể thiếu” với “giá trị có thể null”, hãy nêu rõ trong `description`:

```java
fieldWithPath("discountCode")
    .type(JsonFieldType.STRING)
    .description("Luôn có key; null khi không áp dụng mã ưu đãi");

fieldWithPath("delivery")
    .optional()
    .type(JsonFieldType.OBJECT)
    .description("Không xuất hiện khi trả bản compact; nếu có là object");

fieldWithPath("items[].note")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Có thể thiếu hoặc null; chuỗi khi có nội dung");
```

Nếu dự án muốn có hai cột riêng “Required” và “Nullable”, có thể gắn metadata tùy chỉnh vào descriptor, rồi cấu hình **template snippet riêng** để hiển thị. Ví dụ cách đính kèm thuộc tính:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("discountCode")
    .type(JsonFieldType.STRING)
    .attributes(
        key("required").value(true),
        key("nullable").value(true)
    )
    .description("Mã ưu đãi của đơn hàng");
```

Các attribute này là **metadata cho template**, không tự kích hoạt validation và không tự xuất hiện thành cột trong template mặc định. Nếu dùng metadata, cần bảo trì template và bảo đảm nội dung khớp với các assertion của API.

Cả hai kiểm thử ở mục 5 đều sinh bảng trường:

```text
build/generated-snippets/
├── orders-full-response/
│   └── response-fields.adoc
└── orders-compact-response/
    └── response-fields.adoc
```

Với Maven, thư mục thường là `target/generated-snippets`, còn vị trí cụ thể có thể được cấu hình. Khi dùng Asciidoctor:

```adoc
= Order API
:snippets: build/generated-snippets

== Response đầy đủ

include::{snippets}/orders-full-response/response-fields.adoc[]

== Response rút gọn

include::{snippets}/orders-compact-response/response-fields.adoc[]
```

Các snippet trên mặc định ở định dạng Asciidoctor. Khi xuất bản tài liệu Markdown, cần quy trình chuyển đổi hoặc template phù hợp. Trong build/CI, chạy kiểm thử tạo snippet trước bước biên soạn tài liệu; nếu thay đổi payload làm kiểm thử thất bại thì không nên xuất bản tài liệu chưa được cập nhật.

## 10. Những sai lầm thường gặp

| Triệu chứng hoặc hiểu nhầm | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| “Field null nên phải optional” | Nhầm **giá trị null** với **key vắng mặt** | Chỉ dùng `optional()` khi key được phép thiếu |
| Bỏ `optional()` khỏi trường đôi khi không xuất hiện | Descriptor mặc định yêu cầu path có mặt | Thêm `optional()` đúng hợp đồng |
| Đã `optional()` mà sinh snippet vẫn lỗi kiểu | Fixture không có trường nên không suy được type | Thêm `type(JsonFieldType...)` |
| Trường có `null` được mô tả là kiểu `NULL` dù hợp đồng là chuỗi hoặc null | REST Docs suy kiểu từ fixture | Đặt kiểu dự kiến bằng `.type(JsonFieldType.STRING)`, mô tả null |
| `jsonPath(...).doesNotExist()` được dùng để chứng minh key bị bỏ hẳn | Matcher này cũng thành công với giá trị null | Dùng `doesNotHaveJsonPath()` |
| `jsonPath(...).exists()` được dùng để chứng minh key null vẫn có mặt | `exists()` yêu cầu giá trị khác null | Dùng `hasJsonPath()` |
| `delivery` được optional nhưng trường con vẫn bắt buộc | Response thiếu object cha nên path con cũng thiếu | Phân tích các biến thể; dùng optional cho con và kiểm tra điều kiện riêng |
| Một item có `note` khiến mọi item được cho là hợp lệ | Descriptor path lặp không thay thế kiểm tra từng phần tử | Thêm kiểm thử vòng lặp/schema |
| Thêm `.type(STRING)` rồi nghĩ null không còn được trả | Type của descriptor là thông tin tài liệu | Viết assertion non-null/kiểu khi hợp đồng yêu cầu |
| Cấu hình `@JsonInclude(NON_NULL)` làm test fail | Serializer thay đổi sự hiện diện của trường | Xác minh JSON thực tế, cập nhật contract và descriptor |

Trường “required nhưng được phép null” thường xuất hiện với dữ liệu chưa được điền hoặc đang chờ xử lý. Trường “optional nhưng nếu có thì không null” thường xuất hiện trong các biến thể response tối giản. Cần diễn giải cả hai chiều để người tích hợp không xử lý nhầm.

## 11. Bài thực hành

Sử dụng ví dụ đơn hàng ở mục 4 và thử các thay đổi sau:

1. **Từ null sang thiếu:** bỏ `discountCode` khỏi response rút gọn. Giữ descriptor bắt buộc và quan sát lỗi; nếu hợp đồng cho phép thiếu, cập nhật thành `optional()` nhưng vẫn giữ `.type(JsonFieldType.STRING)`.
2. **Từ thiếu sang null:** trả `"delivery": null` ở bản compact. So sánh kết quả của `jsonPath("$.delivery").doesNotHaveJsonPath()` và `hasJsonPath()`. Chỉnh assertion cho đúng hợp đồng dự định.
3. **Kiểu dữ liệu không mong muốn:** thay `"discountCode": null` bằng `"discountCode": 123`. Giữ `type(JsonFieldType.STRING)` và bổ sung assertion để phát hiện kiểu `NUMBER` không hợp lệ.
4. **Parent có điều kiện:** ở bản full, loại bỏ `delivery.method` nhưng giữ `delivery`. Viết assertion bảo đảm `method` là chuỗi khác null khi object cha có mặt.
5. **Mảng rỗng:** trả `"items": []`. Quan sát giới hạn của `items[].sku` và `items[].quantity` trong fixture tài liệu; kiểm thử ca mảng rỗng tách riêng.
6. **Một vài item thiếu trường:** thêm ba dòng hàng với `note` lần lượt là chuỗi, thiếu key và null. Xác nhận mô tả `optional()`, sau đó viết assertion cho từng quy tắc nghiệp vụ.
7. **Đổi serializer:** thêm `@JsonInclude(Include.NON_NULL)` vào DTO mẫu. So sánh JSON trước và sau rồi điều chỉnh descriptor theo hợp đồng công khai.
8. **Tài liệu xuất bản:** nhúng snippet vào Asciidoctor và bảo đảm build chạy các kiểm thử trước bước sinh tài liệu.

**Tiêu chí hoàn thành:** bạn phân biệt được **key không có**, **key có giá trị null** và **key có giá trị khác null**; khai báo `optional()` đúng phạm vi; chỉ định kiểu tường minh khi không thể suy ra từ fixture; dùng assertion phù hợp để kiểm chứng required/non-null/điều kiện theo object cha; đồng thời đưa bảng response vào tài liệu Spring REST Docs được kiểm soát bởi CI.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): quy tắc kiểm tra field, `optional()`, `ignored()`, kiểu JSON và các snippet.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `optional()` và `type(...)`.
- [Spring Framework — JsonPathResultMatchers](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): khác biệt giữa `hasJsonPath()`, `exists()` và `doesNotHaveJsonPath()`.
