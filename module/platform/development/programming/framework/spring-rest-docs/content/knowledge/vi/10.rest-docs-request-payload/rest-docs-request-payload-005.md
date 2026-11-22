# Trường object tùy chọn và `absent()` trong Spring REST Docs

## 1. Vì sao phải phân biệt object tùy chọn và object vắng mặt?

Một REST API thường có phần request body chỉ cần thiết trong một số tình huống. Ví dụ, endpoint tạo đơn hàng cho phép khách **nhận tại cửa hàng** hoặc **giao tận nơi**:

- Khi `deliveryMode` là `PICKUP`, client không cần gửi object `delivery`.
- Khi `deliveryMode` là `SHIP`, client phải gửi `delivery` với tên người nhận và địa chỉ.
- Object `gift` có thể được bỏ qua ở cả hai trường hợp; khi có, nó chứa thông tin quà tặng.

Nếu tài liệu luôn hiển thị `delivery` như trường bắt buộc, request `PICKUP` sẽ bị mô tả sai. Nếu chỉ đánh dấu `delivery` là tùy chọn mà không giải thích điều kiện `SHIP`, client có thể hiểu nhầm rằng mình được bỏ qua địa chỉ trong mọi trường hợp.

Trong chương **Request payload** của **Spring REST Docs**, bài học này tập trung vào ba việc có liên quan nhưng khác nhau:

1. **Tài liệu hóa** một object có thể vắng mặt bằng `fieldWithPath(...).optional()` trong `requestFields(...)`.
2. **Xác nhận một khóa JSON thực sự vắng mặt** trong request mẫu bằng assertion, tương ứng với ý tưởng *absent* được nhắc trong tên bài.
3. **Kiểm thử hợp đồng nghiệp vụ**: khi nào object được bỏ qua, khi nào phải có, và nếu có thì trường con nào bắt buộc.

Spring REST Docs tạo snippet từ bài kiểm thử HTTP qua MockMvc, WebTestClient hoặc REST Assured. Các snippet có thể đưa vào tài liệu Asciidoctor/Markdown và được tạo lại trong build/CI để phát hiện sai lệch giữa tài liệu và hành vi kiểm thử.

### Lưu ý quan trọng về tên `absent()`

**`FieldDescriptor` trong Spring REST Docs không có phương thức `.absent()`**. Các phương thức liên quan là `.optional()` và `.ignored()`. Vì vậy, đoạn sau **không phải API hợp lệ** của Spring REST Docs:

```java
// SAI: FieldDescriptor không có absent()
fieldWithPath("delivery").description("Thông tin giao hàng").absent();
```

Trong bài này, **absent** có nghĩa *khóa JSON không xuất hiện trong payload*. Muốn tài liệu hóa khả năng này, dùng `.optional()`; muốn xác minh một request mẫu thiếu khóa, dùng assertion trên JSON thật. Đây là hai mục tiêu khác nhau. Không tự tạo ra phương thức `absent()` hoặc nhầm nó với một hàm của thư viện kiểm thử khác.

## 2. Thiết kế hợp đồng API cho object tùy chọn

Giả sử `POST /api/orders` nhận một trong hai request dưới đây.

### 2.1. Giao tận nơi: có object `delivery` và `gift`

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "deliveryMode": "SHIP",
  "delivery": {
    "recipient": {
      "name": "Nguyễn Minh An",
      "phone": "0900000000"
    },
    "address": {
      "street": "12 Nguyễn Huệ",
      "city": "TP. Hồ Chí Minh"
    },
    "instructions": "Gọi trước khi giao"
  },
  "gift": {
    "message": "Chúc mừng sinh nhật"
  }
}
```

### 2.2. Nhận tại cửa hàng: không có object `delivery` và `gift`

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "deliveryMode": "PICKUP"
}
```

Cả hai trường hợp được giả định là **hợp lệ** và endpoint trả `201 Created`. Hợp đồng yêu cầu:

| Đường dẫn | Kiểu JSON | Trạng thái theo hợp đồng | Ý nghĩa |
| --- | --- | --- | --- |
| `customerId` | Number | Bắt buộc | Khách hàng đặt hàng |
| `deliveryMode` | String | Bắt buộc | `PICKUP` hoặc `SHIP` |
| `delivery` | Object | Có điều kiện | Phải có nếu `deliveryMode=SHIP`; bỏ qua nếu `PICKUP` |
| `delivery.recipient` | Object | Có điều kiện | Thông tin người nhận khi giao hàng |
| `delivery.recipient.name` | String | Có điều kiện | Tên người nhận khi giao hàng |
| `delivery.recipient.phone` | String | Tùy chọn | Số điện thoại người nhận |
| `delivery.address` | Object | Có điều kiện | Địa chỉ khi giao hàng |
| `delivery.address.street` | String | Có điều kiện | Số nhà, tên đường khi giao hàng |
| `delivery.address.city` | String | Có điều kiện | Thành phố khi giao hàng |
| `delivery.instructions` | String | Tùy chọn | Ghi chú cho người giao hàng |
| `gift` | Object | Tùy chọn | Thông tin quà tặng |
| `gift.message` | String | Có điều kiện | Nội dung thông điệp nếu gửi `gift` |

**Có điều kiện** không phải thuộc tính riêng của `FieldDescriptor`. Trong snippet dùng chung cho cả `SHIP` và `PICKUP`, các đường dẫn này cần `.optional()` để chấp nhận request `PICKUP`; điều kiện “bắt buộc khi giao hàng” phải được mô tả bằng lời và kiểm thử nghiệp vụ riêng.

## 3. Cách dùng `.optional()` cho cả object cha và các trường con

Để tạo bảng request fields từ cả hai biến thể, khai báo:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
        fieldWithPath("customerId")
                .type(JsonFieldType.NUMBER)
                .description("Mã khách hàng"),

        fieldWithPath("deliveryMode")
                .type(JsonFieldType.STRING)
                .description("Hình thức nhận hàng: PICKUP hoặc SHIP"),

        fieldWithPath("delivery")
                .type(JsonFieldType.OBJECT)
                .description("Thông tin giao hàng; bắt buộc khi deliveryMode=SHIP")
                .optional(),

        fieldWithPath("delivery.recipient")
                .type(JsonFieldType.OBJECT)
                .description("Người nhận hàng khi deliveryMode=SHIP")
                .optional(),

        fieldWithPath("delivery.recipient.name")
                .type(JsonFieldType.STRING)
                .description("Tên người nhận; bắt buộc khi giao hàng")
                .optional(),

        fieldWithPath("delivery.recipient.phone")
                .type(JsonFieldType.STRING)
                .description("Số điện thoại người nhận, có thể bỏ qua")
                .optional(),

        fieldWithPath("delivery.address")
                .type(JsonFieldType.OBJECT)
                .description("Địa chỉ; bắt buộc khi giao hàng")
                .optional(),

        fieldWithPath("delivery.address.street")
                .type(JsonFieldType.STRING)
                .description("Số nhà, tên đường; bắt buộc khi giao hàng")
                .optional(),

        fieldWithPath("delivery.address.city")
                .type(JsonFieldType.STRING)
                .description("Thành phố; bắt buộc khi giao hàng")
                .optional(),

        fieldWithPath("delivery.instructions")
                .type(JsonFieldType.STRING)
                .description("Ghi chú giao hàng, có thể bỏ qua")
                .optional(),

        fieldWithPath("gift")
                .type(JsonFieldType.OBJECT)
                .description("Thông tin quà tặng, có thể bỏ qua")
                .optional(),

        fieldWithPath("gift.message")
                .type(JsonFieldType.STRING)
                .description("Lời nhắn; bắt buộc nếu có object gift")
                .optional()
};
```

Có ba nguyên tắc cần ghi nhớ.

**Thứ nhất, `.optional()` là thuộc tính của từng descriptor.** Đánh dấu `delivery` là tùy chọn không tự biến các descriptor `delivery.recipient.name` và `delivery.address.city` thành tùy chọn. Nếu toàn bộ object có thể thiếu trong một request mẫu, các đường dẫn con cũng phải được xét phù hợp.

**Thứ hai, thêm `.type(JsonFieldType.OBJECT)` cho object không luôn xuất hiện.** Nếu request mẫu thiếu object, Spring REST Docs không thể suy ra kiểu thực tế từ chính trường đó; khai báo tường minh giúp nội dung bảng ổn định. Với trường con, đặt kiểu rõ ràng vì chúng cũng có thể vắng mặt.

**Thứ ba, `optional()` không thực thi quy tắc bắt buộc có điều kiện.** Đoạn khai báo trên cho phép một request `SHIP` không có `delivery` vượt qua **phần kiểm tra trường bắt buộc của snippet**, nếu các descriptor đó đều tùy chọn; nó không đảm bảo endpoint chấp nhận request. Muốn bảo vệ hợp đồng nghiệp vụ, cần kiểm tra validation hoặc test riêng.

### Khi object cha có mặt, trường con có bắt buộc không?

Xét ba trường hợp:

```json
{ "deliveryMode": "PICKUP" }
```

```json
{
  "deliveryMode": "SHIP",
  "delivery": { "address": {} }
}
```

```json
{
  "deliveryMode": "SHIP",
  "delivery": {
    "recipient": { "name": "An" },
    "address": { "street": "12 Nguyễn Huệ", "city": "TP. Hồ Chí Minh" }
  }
}
```

Request thứ nhất được phép không có `delivery`. Request thứ hai **không hợp lệ theo hợp đồng ví dụ** vì thiếu tên người nhận và trường địa chỉ bắt buộc. Request thứ ba thỏa các trường giao hàng căn bản. Tuy nhiên, chỉ dùng `.optional()` trên các descriptor dùng chung không phân biệt hết ba trường hợp này. Cần có kiểm thử điều kiện nghiệp vụ ở bước xử lý HTTP.

## 4. Phân biệt `absent`, `null` và object rỗng `{}`

Đây là phần dễ gây nhầm lẫn nhất khi tài liệu hóa object JSON.

**Vắng mặt hoàn toàn (absent):**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP"
}
```

**Khóa tồn tại, giá trị bằng `null`:**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP",
  "delivery": null
}
```

**Khóa tồn tại, giá trị là object rỗng:**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP",
  "delivery": {}
}
```

| Trường hợp | Có khóa `delivery`? | Giá trị JSON | Cách hiểu |
| --- | --- | --- | --- |
| Absent | Không | Không có giá trị | Client bỏ qua trường |
| `null` | Có | `null` | Client gửi trường với giá trị null |
| `{}` | Có | Object rỗng | Client gửi object nhưng không có trường con |
| `[]` | Có | Array rỗng | Khác kiểu object mà hợp đồng mong đợi |

Như vậy, **“được phép bỏ qua object” không tự động có nghĩa “được phép gửi `null`”**. Tùy API, request `PICKUP` có thể được thiết kế để chấp nhận cả hai, hoặc chỉ chấp nhận absent. Một số ứng dụng dùng `null` như tín hiệu xóa dữ liệu khi cập nhật, trong khi một số khác từ chối `null`. Cần quyết định và kiểm thử cụ thể.

### Xác nhận absent bằng Jackson

Để khẳng định JSON request **không có tên khóa**, dùng `JsonNode.has(...)` hoặc `isMissingNode()`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

ObjectMapper mapper = new ObjectMapper();

JsonNode absent = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP"}
        """);

assertFalse(absent.has("delivery"));
assertTrue(absent.path("delivery").isMissingNode());

JsonNode explicitNull = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP","delivery":null}
        """);

assertTrue(explicitNull.has("delivery"));
assertTrue(explicitNull.get("delivery").isNull());

JsonNode emptyObject = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP","delivery":{}}
        """);

assertTrue(emptyObject.has("delivery"));
assertTrue(emptyObject.get("delivery").isObject());
assertTrue(emptyObject.get("delivery").isEmpty());
```

`has("delivery")` trả `true` ngay cả khi giá trị là `null`. Vì vậy, đừng dùng phép kiểm tra “giá trị khác null” để chứng minh trường **không hề có mặt**. Với cấu trúc lồng nhau, có thể kiểm tra `root.path("delivery").path("address").isMissingNode()`, đồng thời kiểm tra object cha nếu cần phân biệt vắng cả nhánh với thiếu một trường con.

### Nếu gặp `absent()` trong mã kiểm thử khác

Tên `absent()` có thể là tên helper tự viết, một matcher hoặc cú pháp của một thư viện khác. Không suy đoán rằng nó thuộc Spring REST Docs. Với bài này, dùng API thực sự của thư viện mình đang gọi:

| Mục tiêu | API phù hợp | Áp dụng ở đâu |
| --- | --- | --- |
| Trường có thể thiếu trong snippet | `fieldWithPath("delivery").optional()` | Spring REST Docs `requestFields(...)` |
| Xác nhận request JSON thiếu khóa | `assertFalse(root.has("delivery"))` | JUnit + Jackson, kiểm tra nội dung request |
| Xác nhận request JSON thiếu cả đường dẫn | `root.path("delivery").isMissingNode()` | Jackson `JsonNode` |
| Xác nhận **response** JSON thiếu hẳn đường dẫn | `jsonPath("$.delivery").doesNotHaveJsonPath()` | MockMvc response matcher |
| Response không có giá trị khác null ở path | `jsonPath("$.delivery").doesNotExist()` | MockMvc response matcher |

Hai matcher `jsonPath(...)` trong bảng áp dụng cho **response body** mà MockMvc nhận được, không tự kiểm tra request body đã gửi. `doesNotExist()` cho phép đường dẫn có giá trị `null`, còn `doesNotHaveJsonPath()` yêu cầu đường dẫn thực sự không có, kể cả không tồn tại dưới dạng null. Nếu kiểm tra request, hãy đọc đúng nội dung request như ví dụ Jackson thay vì gắn response matcher vào request.

## 5. Bài kiểm thử MockMvc với object đầy đủ và object absent

Giả định:

- Dự án có Spring Boot, JUnit 5, MockMvc, Jackson và Spring REST Docs MockMvc.
- Endpoint `POST /api/orders` đã được triển khai theo hợp đồng ở mục 2.
- Endpoint trả `201 Created` cho cả request `SHIP` hợp lệ và request `PICKUP` hợp lệ.
- Dự án có `spring-boot-starter-test` và `spring-restdocs-mockmvc` trong test dependencies.

Ví dụ dưới đây dùng một **bộ descriptor chung**, nhưng hai request JSON khác nhau. Test `PICKUP` xác nhận `delivery` và `gift` thật sự **absent** trước khi gửi HTTP request.

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
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OptionalObjectRequestDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    private static final FieldDescriptor[] FIELDS = {
            fieldWithPath("customerId")
                    .type(JsonFieldType.NUMBER)
                    .description("Mã khách hàng"),
            fieldWithPath("deliveryMode")
                    .type(JsonFieldType.STRING)
                    .description("PICKUP hoặc SHIP"),

            fieldWithPath("delivery")
                    .type(JsonFieldType.OBJECT)
                    .description("Bắt buộc khi giao hàng; bỏ qua khi nhận tại cửa hàng")
                    .optional(),
            fieldWithPath("delivery.recipient")
                    .type(JsonFieldType.OBJECT)
                    .description("Người nhận khi giao hàng")
                    .optional(),
            fieldWithPath("delivery.recipient.name")
                    .type(JsonFieldType.STRING)
                    .description("Tên người nhận; bắt buộc khi giao hàng")
                    .optional(),
            fieldWithPath("delivery.recipient.phone")
                    .type(JsonFieldType.STRING)
                    .description("Số điện thoại người nhận")
                    .optional(),
            fieldWithPath("delivery.address")
                    .type(JsonFieldType.OBJECT)
                    .description("Địa chỉ; bắt buộc khi giao hàng")
                    .optional(),
            fieldWithPath("delivery.address.street")
                    .type(JsonFieldType.STRING)
                    .description("Tên đường; bắt buộc khi giao hàng")
                    .optional(),
            fieldWithPath("delivery.address.city")
                    .type(JsonFieldType.STRING)
                    .description("Thành phố; bắt buộc khi giao hàng")
                    .optional(),
            fieldWithPath("delivery.instructions")
                    .type(JsonFieldType.STRING)
                    .description("Lưu ý khi giao hàng")
                    .optional(),

            fieldWithPath("gift")
                    .type(JsonFieldType.OBJECT)
                    .description("Thông tin quà tặng, có thể bỏ qua")
                    .optional(),
            fieldWithPath("gift.message")
                    .type(JsonFieldType.STRING)
                    .description("Thông điệp khi có quà tặng")
                    .optional()
    };

    @Test
    void documentShippingOrderWithOptionalObjects() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "deliveryMode": "SHIP",
                  "delivery": {
                    "recipient": {
                      "name": "Nguyễn Minh An",
                      "phone": "0900000000"
                    },
                    "address": {
                      "street": "12 Nguyễn Huệ",
                      "city": "TP. Hồ Chí Minh"
                    },
                    "instructions": "Gọi trước khi giao"
                  },
                  "gift": {
                    "message": "Chúc mừng sinh nhật"
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-shipping",
                        requestFields(FIELDS)));
    }

    @Test
    void documentPickupOrderWithAbsentObjects() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "deliveryMode": "PICKUP"
                }
                """;

        JsonNode requestBody = objectMapper.readTree(json);
        assertFalse(requestBody.has("delivery"));
        assertFalse(requestBody.has("gift"));

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-pickup",
                        requestFields(FIELDS)));
    }
}
```

### Vì sao dùng hai tên snippet khác nhau?

Hai bài kiểm thử đều dùng một bộ `FIELDS`, nhưng đầu vào khác nhau. Nếu cùng ghi vào thư mục `orders-create` trong quá trình chạy test, các snippet có thể bị ghi đè và gây khó khăn khi xem ví dụ payload. Đặt tên riêng giúp lưu vết rõ từng kịch bản:

```text
build/generated-snippets/
├── orders-shipping/
│   ├── http-request.adoc
│   └── request-fields.adoc
└── orders-pickup/
    ├── http-request.adoc
    └── request-fields.adoc
```

Các snippet bổ sung như `http-response.adoc`, `curl-request.adoc` phụ thuộc cấu hình. Trong tài liệu cuối, có thể dùng `request-fields.adoc` của một kịch bản để mô tả hợp đồng dùng chung và include `http-request.adoc` của cả hai kịch bản để minh họa object có mặt/vắng mặt.

### `requestFields(...)` xác nhận được gì?

- Các descriptor đã khai báo được Spring REST Docs dùng để tạo bảng tài liệu.
- Những trường không đánh dấu `.optional()` phải xuất hiện trong payload mẫu khi snippet được tạo.
- Ở chế độ chặt chẽ, các trường **chưa được tài liệu hóa** có thể khiến quá trình sinh snippet thất bại.
- Các descriptor `.optional()` có thể không xuất hiện trong một request mẫu.

Tuy nhiên, việc test sinh snippet thành công **không khẳng định** quy tắc “`delivery` bắt buộc nếu mode là `SHIP`”. Quy tắc này phải được kiểm thử ở tầng nghiệp vụ hoặc validation.

## 6. Kiểm chứng quy tắc bắt buộc có điều kiện

Chúng ta muốn ba test nghiệp vụ sau:

| Dữ liệu gửi | Kết quả mong đợi theo hợp đồng ví dụ |
| --- | --- |
| `PICKUP`, không có `delivery` | `201 Created` |
| `SHIP`, có `delivery.recipient.name`, `delivery.address.street`, `delivery.address.city` | `201 Created` |
| `SHIP`, thiếu `delivery` hoặc thiếu các trường địa chỉ bắt buộc | `400 Bad Request` hoặc lỗi được API quy định |

Với Spring Boot và Jakarta Bean Validation, có thể biểu diễn phần điều kiện qua DTO và validator. Ví dụ dưới đây minh họa ý tưởng; hãy thống nhất annotation, kiểu enum, quy tắc lỗi với dự án thực tế:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record CreateOrderRequest(
        @NotNull Long customerId,
        @NotBlank String deliveryMode,
        @Valid DeliveryRequest delivery,
        @Valid GiftRequest gift
) {
    @AssertTrue(message = "delivery is required when deliveryMode is SHIP")
    public boolean isDeliveryConsistent() {
        return !"SHIP".equals(deliveryMode) || delivery != null;
    }
}

record DeliveryRequest(
        @NotNull @Valid RecipientRequest recipient,
        @NotNull @Valid AddressRequest address,
        String instructions
) {}

record RecipientRequest(
        @NotBlank String name,
        String phone
) {}

record AddressRequest(
        @NotBlank String street,
        @NotBlank String city
) {}

record GiftRequest(
        @NotBlank String message
) {}
```

Trong controller, dùng `@Valid` trên đối tượng đầu vào:

```java
@PostMapping("/api/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Lưu đơn hàng và trả kết quả theo hợp đồng API
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Đây là phần triển khai minh họa, giả định import và dependency validation đã được cấu hình. Với `@Valid` lồng nhau, khi `delivery` hiện diện, các trường trong `DeliveryRequest`, `RecipientRequest` và `AddressRequest` được kiểm tra. Khi `delivery` vắng mặt, quy tắc `isDeliveryConsistent()` quyết định có chấp nhận hay không theo `deliveryMode`.

Với một hợp đồng phức tạp hơn, có thể thay `@AssertTrue` bằng custom constraint cấp class hoặc logic nghiệp vụ để diễn đạt quy tắc rõ ràng và tái sử dụng được. Ngoài ra, vẫn nên dùng kiểu enum thay cho chuỗi tự do nếu chỉ chấp nhận `SHIP` và `PICKUP`.

### Test HTTP âm tính cho `SHIP` thiếu object

```java
@Test
void rejectShippingOrderWithoutDelivery() throws Exception {
    String json = """
            {
              "customerId": 42,
              "deliveryMode": "SHIP"
            }
            """;

    mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isBadRequest());
}
```

Khi endpoint triển khai đúng validation và cách ánh xạ lỗi, test này phải thành công. **Không sử dụng cùng kỳ vọng `201` cho request không hợp lệ**. Có thể sinh snippet về lỗi riêng nếu API cần tài liệu hóa các response validation, nhưng phần đó thuộc kịch bản HTTP lỗi, không phải giải pháp thay thế cho descriptor của request thành công.

## 7. Khi nào dùng `subsectionWithPath`, `ignored()` hoặc `relaxedRequestFields`?

Đôi khi một object tùy chọn quá lớn, và tài liệu tổng quan chỉ cần biết nó chứa nhóm thông tin gì. Khi đó có thể cân nhắc:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("delivery")
        .description("Thông tin giao hàng khi deliveryMode=SHIP")
        .optional()
```

`subsectionWithPath("delivery")` ghi nhận cả nhánh `delivery` như một subsection. Nó thích hợp cho tài liệu tổng quan, vì các trường con được xem là thuộc phần đã mô tả ở mức subsection. Nếu client cần biết `recipient.name` hoặc `address.city`, hãy cung cấp tài liệu chi tiết riêng hoặc khai báo `fieldWithPath(...)` cho từng trường trong bảng.

So sánh ba cơ chế dễ nhầm với `.optional()`:

| Cơ chế | Tác dụng chính | Có nghĩa “object được phép absent”? |
| --- | --- | --- |
| `.optional()` | Cho phép descriptor vắng mặt trong payload được tài liệu hóa | Có, theo mức kiểm tra snippet |
| `.ignored()` | Không đưa descriptor vào bảng; trường/nhánh được xem là đã nhận diện | Không diễn đạt hợp đồng tùy chọn |
| `relaxedRequestFields(...)` | Bỏ qua các trường payload chưa được mô tả | Không tự biến descriptor bắt buộc thành tùy chọn |
| `subsectionWithPath("delivery")` | Mô tả cả nhánh dưới một hàng | Không tự là tùy chọn; có thể thêm `.optional()` |

Với tài liệu API cần nắm đầy đủ request payload, dùng `requestFields(...)` chặt chẽ và `.optional()` đúng trường thường dễ bảo trì hơn. Nới lỏng quá mức có thể khiến một trường mới xuất hiện trong JSON mà không được bổ sung vào tài liệu.

## 8. Đưa hai biến thể vào Asciidoctor hoặc Markdown

Sau khi test thành công, có thể soạn nguồn Asciidoctor:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

`delivery` là object tùy chọn khi `deliveryMode=PICKUP`.
Khi `deliveryMode=SHIP`, phải gửi thông tin người nhận và địa chỉ.

=== Ví dụ nhận tại cửa hàng

include::{snippets}/orders-pickup/http-request.adoc[]

=== Ví dụ giao tận nơi

include::{snippets}/orders-shipping/http-request.adoc[]

=== Mô tả các trường request

include::{snippets}/orders-shipping/request-fields.adoc[]
```

Cần cấu hình `{snippets}` trỏ tới thư mục chứa snippet, thường là `build/generated-snippets`. Với Gradle và plugin Asciidoctor đã cài, luồng build có thể khai báo:

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

Khi các test tạo snippet thất bại, build CI phải dừng trước bước xuất bản tài liệu. Nếu dự án xuất **Markdown**, cần template snippet Markdown hoặc bước chuyển đổi phù hợp; Spring REST Docs trong ví dụ mặc định tạo `.adoc`, không tự sinh `request-fields.md`.

Một bảng riêng trong tài liệu có thể làm rõ điều kiện khó thể hiện bằng cột optional mặc định:

| Điều kiện | Trường liên quan | Yêu cầu |
| --- | --- | --- |
| `deliveryMode=PICKUP` | `delivery` | Được bỏ qua |
| `deliveryMode=SHIP` | `delivery` | Phải có |
| `delivery` có mặt | `delivery.recipient.name` | Không rỗng |
| `delivery` có mặt | `delivery.address.street`, `delivery.address.city` | Không rỗng |
| Không có `gift` | `gift.message` | Không yêu cầu |
| Có `gift` | `gift.message` | Bắt buộc theo hợp đồng ví dụ |

Nếu template snippet đang dùng không hiển thị cột “Optional”, hãy ghi rõ trạng thái trong `.description(...)` hoặc tùy biến template.

## 9. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không biên dịch được `.absent()` trên `FieldDescriptor` | Đây không phải phương thức của Spring REST Docs | Dùng `.optional()` và assertion JSON để xác nhận absent |
| Request `PICKUP` thiếu `delivery` khiến bước sinh snippet lỗi | Descriptor `delivery` hoặc trường con chưa đánh dấu optional | Xem lại mọi descriptor của nhánh có thể vắng mặt |
| `delivery` tùy chọn nhưng `delivery.address.city` vẫn báo thiếu | `.optional()` của object cha không lan sang descriptor con | Dùng `.optional()` cho descriptor con phù hợp |
| `SHIP` thiếu `delivery` nhưng test tài liệu vẫn tạo snippet | Descriptor cho nhánh có điều kiện đều optional | Thêm validation và negative test cho điều kiện `SHIP` |
| Tưởng `delivery: null` giống absent | Khóa có mặt dù giá trị null | Dùng `JsonNode.has`/`isMissingNode` và định nghĩa hợp đồng rõ ràng |
| `delivery: {}` được chấp nhận dù thiếu trường con | Chưa có validation cho các trường lồng nhau | Dùng `@Valid`, `@NotNull` và `@NotBlank` phù hợp |
| Bảng chỉ có `delivery`, thiếu chi tiết người nhận/địa chỉ | Chỉ mô tả object cha hoặc subsection | Thêm descriptor trường con có ý nghĩa với client |
| Không tìm thấy `request-fields.adoc` | Không gọi `requestFields(...)`, cấu hình REST Docs thiếu hoặc đường dẫn output sai | Kiểm tra test, tên snippet và `outputDir` |
| Tài liệu dùng `responseFields` cho request | Chọn nhầm chiều dữ liệu | Dùng `requestFields(...)` cho request body |

## 10. Bài thực hành

Hãy bắt đầu từ bộ descriptor và hai test trong mục 5:

1. **Xác nhận object absent:** in ra hoặc kiểm tra `JsonNode.has("delivery")` cho ba JSON ở mục 4. Giải thích vì sao `false` chỉ xuất hiện khi khóa thực sự vắng mặt.
2. **Thêm object tùy chọn:** bổ sung `invoice` có `companyName`, `taxCode`; object `invoice` được phép vắng mặt khi khách không yêu cầu hóa đơn. Thêm descriptor `invoice` và các trường con với `.optional()` phù hợp; tạo hai request có và không có `invoice`.
3. **Bắt buộc có điều kiện:** với `deliveryMode=SHIP`, gửi `delivery` nhưng bỏ `delivery.address.city`. Thêm validation để API trả lỗi. Giải thích vì sao chỉ dùng `.optional()` không phát hiện đầy đủ lỗi này.
4. **Kiểm tra `null`:** gửi `"delivery": null` với `PICKUP`. Quyết định rõ hợp đồng của API có chấp nhận tình huống này hay không; viết test tương ứng.
5. **Xuất tài liệu:** sinh hai thư mục snippet `orders-shipping` và `orders-pickup`, include hai HTTP request trong Asciidoctor, kèm bảng điều kiện bắt buộc theo `deliveryMode`.
6. **Mô phỏng thay đổi hợp đồng:** thêm trường `delivery.contactEmail` vào JSON `SHIP` nhưng chưa có descriptor. Quan sát lỗi trong chế độ `requestFields` chặt chẽ, rồi cập nhật descriptor và tài liệu.

### Câu hỏi tự đánh giá

- Tại sao `delivery.optional()` không làm `delivery.address.city` tự động optional?
- Absent khác `null` và `{}` như thế nào?
- `FieldDescriptor` có API `.absent()` không? Muốn chứng minh khóa không có mặt thì kiểm tra ở đâu?
- Vì sao một object được tài liệu hóa là optional vẫn có thể **bắt buộc theo điều kiện nghiệp vụ**?
- Nếu chỉ mô tả object cha, bảng snippet có đủ thông tin để client điền đúng các trường con không?
- Khi API bổ sung trường mới vào object, CI nên phản ứng như thế nào?

**Ghi nhớ:** Trong Spring REST Docs, `.optional()` là cách tài liệu hóa một trường hoặc object **được phép vắng mặt** ở payload mẫu. **Absent** là trạng thái thực tế của JSON và có thể được xác nhận bằng assertion trên request; nó **không** phải phương thức `.absent()` của `FieldDescriptor`. Khi object tùy chọn có các trường con bắt buộc theo điều kiện, hãy kết hợp descriptor, mô tả bằng lời, validation và test HTTP để tài liệu phản ánh đúng hợp đồng API.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `fieldWithPath`, các trường optional và snippet.
- [Spring REST Docs — `FieldDescriptor` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): các phương thức thực tế, bao gồm `optional()`, không có `absent()`.
- [Spring Framework — `JsonPathResultMatchers` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): phân biệt `doesNotExist()` và `doesNotHaveJsonPath()` trên **response**.
