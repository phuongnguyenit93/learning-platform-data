# Thiết kế mô tả không phụ thuộc thứ tự trường JSON

## 1. Vì sao không nên phụ thuộc thứ tự key trong JSON object?

Trong chương **Response payload** của module **SPRING_REST_DOCS**, `responseFields(...)` mô tả các trường JSON thông qua `fieldWithPath(...)`. Một lỗi thiết kế thường gặp là cho rằng key phải xuất hiện theo đúng thứ tự trong fixture hoặc theo thứ tự thuộc tính trong DTO Java.

JSON object là tập hợp các cặp tên/giá trị. Thứ tự các member không mang ý nghĩa trong mô hình dữ liệu JSON. Vì thế hai payload sau biểu diễn cùng một object:

```json
{
  "id": "ORD-2100",
  "status": "CONFIRMED",
  "totalAmount": 250000
}
```

```json
{
  "totalAmount": 250000,
  "id": "ORD-2100",
  "status": "CONFIRMED"
}
```

Khi tài liệu hóa response bằng Spring REST Docs, descriptor xác định **path và ý nghĩa của field**, không xác định vị trí byte hay thứ tự key trong object JSON. Nếu contract chỉ thay đổi thứ tự key mà giữ nguyên tên, cấu trúc và giá trị theo path, đó không phải thay đổi schema.

Bài học này tập trung vào:

- Phân biệt thứ tự key trong object với thứ tự phần tử của array.
- Viết descriptor theo path ổn định, không dựa vào vị trí field trong JSON.
- Tổ chức fixture và DTO để test không phụ thuộc thứ tự insert/serialization.
- Phân biệt thứ tự khai báo descriptor với thứ tự key của response.
- Kiểm tra response bằng path/value thay vì so sánh JSON dạng chuỗi.
- Duy trì snippet Spring REST Docs ổn định trong build và CI.

## 2. Ba loại thứ tự cần phân biệt

| Loại thứ tự | Có ý nghĩa trong contract JSON? | Ví dụ | Cách xử lý |
| --- | --- | --- | --- |
| Thứ tự key trong object | Không | `id` đứng trước hay sau `status` | Không viết test phụ thuộc thứ tự key |
| Thứ tự phần tử trong array | Có thể có | Dòng hàng đứng ở vị trí 0 hay 1 | Kiểm thử thứ tự nếu nghiệp vụ quy định |
| Thứ tự khai báo FieldDescriptor | Ảnh hưởng cách tổ chức/trình bày snippet | `id` được khai báo trước `status` | Sắp xếp descriptor có chủ đích, dễ đọc |

Đừng suy luận rằng vì object JSON không có thứ tự key nên mọi cấu trúc JSON đều không có thứ tự. Array là một chuỗi phần tử có vị trí; với endpoint trả danh sách đã sắp theo ngày tạo, độ ưu tiên hoặc thứ tự hiển thị, client có thể phụ thuộc vào thứ tự đó.

### 2.1. JSON object không phải danh sách field có chỉ số

Ví dụ object:

```json
{
  "customer": {
    "id": "CUS-18",
    "displayName": "Khách hàng 18"
  },
  "orderId": "ORD-2100"
}
```

Các path vẫn là `orderId`, `customer.id` và `customer.displayName`. Không có path kiểu `field[0]` hoặc `field[1]` dành cho thứ tự key của object.

Đối với `responseFields`, khai báo:

```java
responseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("customer").description("Khách hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.displayName")
        .description("Tên hiển thị của khách hàng")
)
```

có thể dùng với payload có thứ tự key khác nhau, miễn đường dẫn và cấu trúc dữ liệu vẫn đúng.

### 2.2. JSON array có thứ tự

Payload array:

```json
{
  "items": [
    {"sku": "BK-01", "quantity": 2},
    {"sku": "BK-02", "quantity": 1}
  ]
}
```

`items[0]` và `items[1]` là hai vị trí khác nhau. Descriptor tổng quát:

```java
responseFields(
    fieldWithPath("items").description("Danh sách dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng")
)
```

mô tả cấu trúc field ở các phần tử lặp, nhưng không xác định rằng phần tử BK-01 phải đứng đầu. Nếu API cam kết sắp xếp, hãy viết assertion riêng cho thứ tự:

```java
.andExpect(jsonPath("$.items[0].sku").value("BK-01"))
.andExpect(jsonPath("$.items[1].sku").value("BK-02"))
```

Nếu API không cam kết thứ tự, tránh assertion vị trí cụ thể. Có thể kiểm tra sự hiện diện của các giá trị hoặc tập hợp mã sản phẩm thay vì buộc một thứ tự tùy ý.

## 3. Viết descriptor theo tên path, không theo vị trí key

Một descriptor nên xác định path trực tiếp:

```java
fieldWithPath("orderId")
    .description("Mã định danh đơn hàng");

fieldWithPath("status")
    .description("Trạng thái xử lý đơn hàng");

fieldWithPath("totalAmount")
    .description("Tổng tiền theo VND");
```

Không có API kiểu “field thứ nhất”, “field thứ hai” trong `fieldWithPath` để phụ thuộc vào vị trí key của object. Tránh tự viết logic chọn phần tử của một danh sách tên field theo vị trí trong response rồi tạo descriptor tương ứng.

Với object lồng, path vẫn thể hiện tên field:

```json
{
  "pricing": {
    "currency": "VND",
    "payableAmount": 320000,
    "discountAmount": 50000
  }
}
```

```java
responseFields(
    fieldWithPath("pricing").description("Thông tin tính tiền"),
    fieldWithPath("pricing.currency").description("Mã tiền tệ"),
    fieldWithPath("pricing.payableAmount")
        .description("Tổng tiền phải thanh toán bằng VND"),
    fieldWithPath("pricing.discountAmount")
        .description("Khoản giảm giá bằng VND")
)
```

Dù serializer ghi `currency` trước `payableAmount` hay ngược lại, path vẫn giữ nguyên. Nếu tên JSON thay đổi từ `payableAmount` sang `amountDue`, đó là thay đổi contract; cần sửa descriptor, assertion và tài liệu, không phải vấn đề thứ tự.

## 4. Thứ tự descriptor và cách tổ chức bảng tài liệu

Thứ tự khai báo descriptor thể hiện ý đồ của người viết test. Một danh sách được nhóm logic giúp snippet dễ đọc và dễ review:

```java
responseFields(
    // Nhận diện tài nguyên
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),

    // Khách hàng
    fieldWithPath("customer").description("Thông tin khách hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.displayName")
        .description("Tên hiển thị"),

    // Tổng tiền
    fieldWithPath("pricing").description("Thông tin tính tiền"),
    fieldWithPath("pricing.subtotalAmount")
        .description("Tiền hàng trước giảm/phí, VND"),
    fieldWithPath("pricing.discountAmount")
        .description("Khoản giảm giá, VND"),
    fieldWithPath("pricing.payableAmount")
        .description("Số tiền phải thanh toán, VND")
)
```

Đừng cố sắp xếp descriptor để bắt chước thứ tự key serializer chỉ vì hai danh sách trông giống nhau. Nên nhóm theo ý nghĩa nghiệp vụ hoặc cấu trúc object; khi schema thêm field, người review dễ nhận ra vị trí phù hợp.

Nếu cần bảng snippet có thứ tự hiển thị ổn định, hãy thống nhất thứ tự khai báo descriptor trong test và template của dự án. Mục tiêu là tính nhất quán của tài liệu. Thứ tự hiển thị không được diễn giải thành một ràng buộc wire-level cho object JSON.

## 5. Ví dụ MockMvc: đổi thứ tự key nhưng giữ nguyên contract

Ví dụ sau dùng JUnit Jupiter, MockMvc, Jackson và `spring-restdocs-mockmvc`. Controller trả cùng một dữ liệu nhưng tạo map theo hai cách insert key khác nhau dựa vào query parameter. Hai bài test dùng cùng descriptor.

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ResponseFieldOrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    private static org.springframework.restdocs.payload.FieldDescriptor[]
    orderDescriptors() {
        return new org.springframework.restdocs.payload.FieldDescriptor[] {
            fieldWithPath("orderId").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn"),
            fieldWithPath("totalAmount")
                .description("Tổng tiền theo VND")
        };
    }

    @Test
    void documentOrderWithFirstKeyOrder() throws Exception {
        mockMvc.perform(get("/api/order").param("layout", "first")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2100"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.totalAmount").value(250000))
                .andDo(document("order-fields-layout-first",
                        responseFields(orderDescriptors())));
    }

    @Test
    void documentOrderWithSecondKeyOrder() throws Exception {
        mockMvc.perform(get("/api/order").param("layout", "second")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2100"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.totalAmount").value(250000))
                .andDo(document("order-fields-layout-second",
                        responseFields(orderDescriptors())));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/order",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(
                @RequestParam(name = "layout", defaultValue = "first")
                String layout) {

            Map<String, Object> body = new LinkedHashMap<>();

            if ("second".equals(layout)) {
                body.put("totalAmount", 250000);
                body.put("status", "CONFIRMED");
                body.put("orderId", "ORD-2100");
            } else {
                body.put("orderId", "ORD-2100");
                body.put("status", "CONFIRMED");
                body.put("totalAmount", 250000);
            }
            return body;
        }
    }
}
```

Điểm đáng chú ý:

- `LinkedHashMap` giữ thứ tự insert khi serialize, nên fixture có thể tạo hai cách sắp xếp key khác nhau để minh họa.
- Hai test dùng cùng `orderDescriptors()`; chúng xác minh bằng JSON path và giá trị, không so sánh nguyên chuỗi JSON.
- Cả hai response đều có cùng path và dữ liệu. Thay đổi thứ tự key không cần sửa descriptor.
- Hai identifier snippet riêng giúp review từng HTTP exchange. Trong thực tế, nếu không cần tài liệu hóa hai biến thể chỉ khác thứ tự key, chỉ cần một fixture đại diện; không nên tạo test dư thừa chỉ để kiểm tra serializer.

Ví dụ này minh họa tính độc lập với thứ tự key trong object. Nó không khuyến khích thêm query parameter `layout` vào API thật chỉ để thay đổi thứ tự serialization.

## 6. Vì sao không nên so sánh raw JSON string?

Một assertion như:

```java
.andExpect(content().string(
    "{\"orderId\":\"ORD-2100\",\"status\":\"CONFIRMED\","
  + "\"totalAmount\":250000}"))
```

phụ thuộc vào thứ tự key và cách trình bày chuỗi. Nó có thể fail dù response vẫn mang cùng object JSON hợp lệ.

Thay vào đó, kiểm tra các thuộc tính bằng JSON path:

```java
.andExpect(jsonPath("$.orderId").value("ORD-2100"))
.andExpect(jsonPath("$.status").value("CONFIRMED"))
.andExpect(jsonPath("$.totalAmount").value(250000))
```

Hoặc parse sang cây JSON khi cần so sánh nhiều giá trị:

```java
JsonNode body = objectMapper.readTree(
        result.getResponse().getContentAsString());

assertEquals("ORD-2100", body.path("orderId").asText());
assertEquals("CONFIRMED", body.path("status").asText());
assertEquals(250000, body.path("totalAmount").asInt());
```

So sánh `JsonNode` theo cấu trúc object thường không phụ thuộc thứ tự member; tuy nhiên khi bên trong có array, thứ tự phần tử vẫn được giữ và có thể ảnh hưởng kết quả equality.

Nếu cần xác nhận một tập field bắt buộc, hãy kiểm tra từng path hoặc dùng schema validator. Không viết test chỉ kiểm tra số lượng key nếu client còn cần kiểu, giá trị và cấu trúc con đúng.

## 7. DTO Java và serializer

Thứ tự key khi serialize có thể phụ thuộc vào:

- Loại object/map được trả về và thứ tự iteration của nó.
- Cấu hình thư viện JSON và serializer tùy chỉnh.
- Annotation hoặc naming strategy ảnh hưởng tên field.
- Cấu hình sort property nếu ứng dụng chủ động bật.
- Phiên bản thư viện hoặc thay đổi cấu trúc DTO.

Không nên coi thứ tự hiện tại trong output của Jackson là cam kết API trừ khi hệ thống thực sự có yêu cầu định dạng đặc biệt bên ngoài JSON data model. Nếu một client cần thứ tự key để parse JSON thì client đó đang dựa vào giả định không phù hợp với định dạng.

Một DTO thông thường:

```java
record OrderResponse(
    String orderId,
    String status,
    long totalAmount
) {}
```

Có thể tạo một object JSON có các field tương ứng. Để kiểm thử contract, dùng path theo tên JSON sau serialization, không dựa vào vị trí tham số record. Nếu ứng dụng dùng `@JsonProperty` đổi tên `totalAmount` thành `amountDue` thì descriptor phải theo key JSON cuối cùng.

Ví dụ:

```java
@JsonProperty("amountDue")
long totalAmount
```

Khi đó path cần mô tả là `amountDue`. Đây là thay đổi tên field, khác hoàn toàn với việc key `totalAmount` xuất hiện trước hay sau key `status`.

## 8. Descriptor tái sử dụng và tính ổn định

Nếu nhiều endpoint có cùng response contract, có thể tạo bộ descriptor dùng lại:

```java
static FieldDescriptor[] basicOrderFields() {
    return new FieldDescriptor[] {
        fieldWithPath("orderId")
            .description("Mã đơn hàng"),
        fieldWithPath("status")
            .description("Trạng thái đơn hàng"),
        fieldWithPath("totalAmount")
            .description("Tổng tiền theo VND")
    };
}
```

Sau đó dùng trong nhiều test:

```java
responseFields(basicOrderFields())
```

Lợi ích là thứ tự mô tả nhất quán và khi ý nghĩa field thay đổi có thể cập nhật một nơi. Tuy nhiên chỉ tái sử dụng khi **schema và ý nghĩa nghiệp vụ thực sự giống nhau**. Cùng tên `status` trong order response và payment response có thể mang vòng đời khác; không nên gom chỉ vì path hoặc tên trường trông giống nhau.

Khi một endpoint thêm field riêng, có thể kết hợp descriptor chung với descriptor bổ sung:

```java
responseFields(basicOrderFields()).and(
    fieldWithPath("paymentStatus")
        .description("Trạng thái thanh toán")
)
```

Ví dụ minh họa cơ chế kết hợp. Trong strict mode, mọi field thực tế của response vẫn phải được xử lý; descriptor dùng chung không miễn trừ yêu cầu bao phủ payload.

## 9. Thứ tự phần tử array là câu chuyện khác

Với response:

```json
{
  "items": [
    {"sku": "BK-01", "position": 1},
    {"sku": "BK-02", "position": 2}
  ]
}
```

Đổi vị trí hai phần tử làm thay đổi array:

```json
{
  "items": [
    {"sku": "BK-02", "position": 2},
    {"sku": "BK-01", "position": 1}
  ]
}
```

Đây không chỉ là thay đổi cách trình bày object mà là thay đổi thứ tự phần tử trong array. Nếu API cam kết sắp xếp theo `position`, hãy test:

```java
.andExpect(jsonPath("$.items[0].position").value(1))
.andExpect(jsonPath("$.items[1].position").value(2))
```

Nếu API không cam kết thứ tự, tránh assertion cố định index. Có thể kiểm tra tập giá trị bằng cách parse array và so sánh sau khi sắp xếp trong test, hoặc xác minh các phần tử xuất hiện mà không yêu cầu vị trí.

Với `responseFields`, descriptor `items[].sku` mô tả cùng một field ở các phần tử. Nó không áp đặt thứ tự sắp xếp của array. Hợp đồng về sắp xếp cần được giải thích và assertion riêng.

## 10. Fixture và snippet ổn định trong CI

Để tránh nhiễu do thứ tự key, nên:

1. Xác minh contract bằng path và giá trị, không so sánh chuỗi JSON cứng nếu không có lý do.
2. Sử dụng fixture có cấu trúc rõ ràng; nếu dùng map có thứ tự insert, chỉ dùng nó để tạo dữ liệu dễ đọc hoặc kiểm thử tình huống serializer cụ thể.
3. Giữ danh sách descriptor được nhóm theo chủ đề nghiệp vụ, nhất quán giữa các endpoint có cùng contract.
4. Không coi thay đổi thứ tự key là breaking change.
5. Kiểm thử array order riêng nếu API định nghĩa sorting.
6. Cho test REST Docs chạy trước Asciidoctor; xem thay đổi snippet cùng thay đổi code và descriptor.

Ví dụ cấu trúc snippets Gradle:

```text
build/generated-snippets/
├── order-fields-layout-first/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── order-fields-layout-second/
    ├── http-response.adoc
    └── response-fields.adoc
```

Với Maven, thư mục mặc định thường là `target/generated-snippets`. Vị trí output có thể tùy chỉnh.

Asciidoctor có thể nhúng response và field table:

```adoc
= Order API
:snippets: build/generated-snippets

== Order response

=== HTTP response
include::{snippets}/order-fields-layout-first/http-response.adoc[]

=== Response fields
include::{snippets}/order-fields-layout-first/response-fields.adoc[]
```

Trong tài liệu cuối, không cần duy trì hai ví dụ chỉ khác thứ tự key nếu điều đó không phục vụ người đọc; có thể giữ một snippet đại diện. Việc có hai test trong bài học chỉ nhằm minh họa rằng descriptor truy xuất theo tên path, không dựa vào vị trí key.

Build/CI nên chạy HTTP test sinh snippet trước khi biên soạn Asciidoctor. Nếu path bị đổi tên hoặc field bị mất, strict descriptor/assertion giúp phát hiện; nếu chỉ đảo thứ tự key trong object, test theo path vẫn thành công.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test fail sau khi serializer đảo thứ tự key | Assertion so sánh raw JSON string | Dùng JSON path hoặc parse JSON object |
| Descriptor bị viết theo thứ tự field Java | Nhầm tham số DTO với vị trí JSON | Dùng path theo tên JSON sau serialization |
| Đổi thứ tự array nhưng test không phát hiện | Chưa có assertion thứ tự dù contract yêu cầu sorting | Kiểm tra index/order hoặc schema nghiệp vụ |
| Test ép array order dù contract không cam kết | Dựa vào thứ tự tình cờ của fixture | Kiểm tra tập phần tử thay vì vị trí |
| Bảng tài liệu thay đổi thứ tự hàng ngoài ý muốn | Descriptor được sắp xếp lại hoặc template đổi | Thống nhất thứ tự khai báo descriptor và template |
| Field đổi tên nhưng coi là khác thứ tự key | Không phân biệt key order với path/name | Cập nhật contract, descriptor và versioning nếu cần |
| Strict test bỏ qua field mới | Dùng relaxed quá rộng | Dùng strict và xử lý field mới có chủ đích |
| Snippet khác nhau chỉ do dữ liệu fixture | Fixture không ổn định | Chuẩn hóa fixture và chỉ thay đổi điều cần kiểm tra |

## 12. Bài thực hành

Dùng response đơn hàng có `orderId`, `status` và `totalAmount`:

1. Tạo hai `LinkedHashMap` với thứ tự insert key khác nhau nhưng cùng value. Trả cả hai từ test endpoint và xác nhận cùng bộ assertion JSON path đều thành công.
2. Viết một assertion so sánh raw JSON string, quan sát nó fail khi đảo thứ tự key dù object không đổi. Thay bằng assertion theo path.
3. Khai báo `FieldDescriptor` trong một method dùng chung cho hai test; giữ thứ tự descriptor ổn định.
4. Đổi tên key `totalAmount` thành `amountDue` bằng serializer/DTO. Quan sát đây là thay đổi path thực sự và cập nhật descriptor.
5. Tạo array `items` có hai phần tử. Đổi thứ tự phần tử; viết assertion để xác nhận thứ tự nếu contract yêu cầu hoặc kiểm tra tập giá trị nếu contract không yêu cầu.
6. Tạo object lồng `pricing` với các field tiền tệ theo thứ tự key khác nhau. Xác nhận các descriptor `pricing.*` vẫn hoạt động.
7. Sinh snippet và xem thay đổi nào ảnh hưởng đến bảng field, thay đổi nào chỉ là thứ tự key của response.

**Tiêu chí hoàn thành:** bạn phân biệt được thứ tự key object với thứ tự array; hiểu descriptor hoạt động theo path; không viết assertion phụ thuộc raw JSON string; tổ chức descriptor dễ đọc, ổn định; và kiểm tra đúng những thứ tự mà hợp đồng API thực sự quy định.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): mô tả payload bằng field path và sinh response fields snippet.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): định nghĩa JSON object, array và ngữ nghĩa thứ tự.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): kiểm thử response qua MockMvc và assertion theo path.
