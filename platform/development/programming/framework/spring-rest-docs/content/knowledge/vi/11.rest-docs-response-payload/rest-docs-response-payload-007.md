# Ignore trường response có chủ đích trong Spring REST Docs

## 1. Vai trò của ignore trong tài liệu payload

Trong chương **Response payload** của module **SPRING_REST_DOCS**, response JSON có thể chứa cả dữ liệu public và metadata kỹ thuật. Client cần biết mã đơn hàng, trạng thái và tổng tiền; trong khi trace ID nội bộ, tên node xử lý, thời gian chẩn đoán hoặc cache flags có thể không thuộc phần hợp đồng cần trình bày.

Ví dụ:

```json
{
  "id": "ORD-9001",
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "internalTraceId": "trace-7a91",
  "debug": {
    "sourceNode": "node-03",
    "timingMs": 12,
    "flags": {"cacheHit": true}
  }
}
```

Spring REST Docs cung cấp `FieldDescriptor.ignored()` để đánh dấu một path đã biết nhưng chủ động không đưa vào bảng `response-fields.adoc`. Dùng `fieldWithPath("internalTraceId").ignored()` cho field đơn hoặc `subsectionWithPath("debug").ignored()` để bỏ cả nhánh.

**Phạm vi:** ignore là quyết định về tài liệu snippet. Nó không xóa trường khỏi HTTP response, không che byte dữ liệu, không thay đổi serialization và không cung cấp bảo mật.

## 2. Cú pháp cơ bản

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    fieldWithPath("totalAmount").description("Tổng tiền theo VND"),
    fieldWithPath("internalTraceId").ignored()
)
```

Các trường `id`, `status` và `totalAmount` được trình bày. `internalTraceId` được nhận diện là trường cố ý bỏ qua, không xuất hiện như một hàng mô tả thông thường. Việc khai báo tường minh giúp người review hiểu rằng trường đã được xem xét.

Ví dụ gắn vào bài kiểm thử MockMvc:

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Mã định danh đơn hàng"),
        fieldWithPath("status").description("Trạng thái xử lý đơn"),
        fieldWithPath("totalAmount").description("Tổng tiền theo VND"),
        fieldWithPath("internalTraceId").ignored()
    )
))
```

Trong chế độ strict của `responseFields(...)`, các field trong payload cần được mô tả hoặc xử lý có chủ đích. Không nên ignore tất cả field để chỉ giữ lại vài dòng mà không đánh giá tác động đối với contract.

## 3. Phân biệt ignore, optional và relaxed

| Cơ chế | Mục đích | Có trong bảng? | Ý nghĩa |
| --- | --- | --- | --- |
| Mặc định `fieldWithPath(...)` | Tài liệu hóa field | Có | Field được mô tả; thiếu field bắt buộc hoặc field ngoài danh sách có thể làm test thất bại |
| `optional()` | Cho phép field đã tài liệu hóa vắng mặt | Có nếu xuất hiện trong fixture | Nới điều kiện phải có path trong response mẫu |
| `ignored()` | Nhận diện field nhưng không công bố trong bảng | Không | Chủ động loại field khỏi snippet |
| `relaxedResponseFields(...)` | Tài liệu hóa một phần payload | Chỉ field khai báo | Cho phép field ngoài danh sách |

### 3.1. Ignore không có nghĩa là optional

Nếu field luôn xuất hiện nhưng không cần công bố, dùng:

```java
fieldWithPath("internalTraceId").ignored()
```

Nếu field có thể không xuất hiện, nhưng khi có thì client cần hiểu ý nghĩa, dùng:

```java
fieldWithPath("deliveryNote")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Ghi chú giao hàng, có thể vắng mặt");
```

`optional()` nói về sự hiện diện của path. `ignored()` nói về việc không đưa mô tả field vào bảng. Không thay thế lẫn nhau để làm test qua.

### 3.2. Ignore so với relaxed

Biết rõ nhánh debug cần bỏ:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    subsectionWithPath("debug").ignored()
)
```

Chỉ muốn mô tả một phần response và cho phép các field khác ngoài danh sách:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng")
)
```

Relaxed hữu ích cho tài liệu một phần, nhưng field mới có thể xuất hiện mà test không báo lỗi. Nếu chỉ một vài path cụ thể không cần công bố, strict mode cùng ignored descriptor giúp việc rà soát rõ hơn.

## 4. Bỏ qua object lồng nhau

Payload:

```json
{
  "id": "ORD-9001",
  "status": "CONFIRMED",
  "debug": {
    "sourceNode": "node-03",
    "timingMs": 12,
    "flags": {"cacheHit": true}
  }
}
```

Có thể bỏ cả nhánh:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn"),
    subsectionWithPath("debug").ignored()
)
```

Descriptor subsection thể hiện chủ đích loại `debug` cùng các descendant khỏi bảng. Nếu trong nhánh có field public, không ignore cả object. Chọn cụ thể từng path:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    subsectionWithPath("debug")
        .description("Thông tin hỗ trợ được công bố cho client"),
    fieldWithPath("debug.requestId")
        .description("Mã yêu cầu để liên hệ hỗ trợ"),
    fieldWithPath("debug.internalTraceId").ignored(),
    fieldWithPath("debug.sourceNode").ignored()
)
```

Chỉ dùng cách này nếu `debug.requestId` thực sự thuộc public contract. Tên object không tự quyết định tính public hay nội bộ của mọi field con.

## 5. Bỏ qua field trong mảng lặp

Response:

```json
{
  "items": [
    {
      "sku": "BK-01",
      "quantity": 2,
      "warehouseCode": "HCM-01",
      "stockSnapshot": 18
    },
    {
      "sku": "BK-02",
      "quantity": 1,
      "warehouseCode": "HAN-02",
      "stockSnapshot": 7
    }
  ]
}
```

Tài liệu hóa field client cần, bỏ qua metadata trong từng phần tử:

```java
responseFields(
    fieldWithPath("items").description("Danh sách các dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng sản phẩm"),
    fieldWithPath("items[].warehouseCode").ignored(),
    fieldWithPath("items[].stockSnapshot").ignored()
)
```

Path vẫn phải có `[]` vì `items` là array. Nếu toàn bộ nhánh nội bộ của mỗi phần tử cần bỏ qua:

```json
{
  "items": [
    {
      "sku": "BK-01",
      "internal": {
        "source": "ERP",
        "syncBatch": "B-2026-11"
      }
    }
  ]
}
```

```java
responseFields(
    fieldWithPath("items").description("Các dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    subsectionWithPath("items[].internal").ignored()
)
```

Với fixture `"items": []`, path con không có phần tử đại diện. Dùng fixture không rỗng cho test tạo tài liệu cấu trúc; kiểm tra ca mảng rỗng riêng.

## 6. Ví dụ MockMvc hoàn chỉnh

Ví dụ dùng JUnit Jupiter, MockMvc, Jackson và dependency `spring-restdocs-mockmvc`. Controller trả cả field public và metadata chẩn đoán; test chỉ tài liệu hóa phần client cần.

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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderIgnoreInternalFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentPublicOrderFieldsOnly() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 9001)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-9001"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.internalTraceId").isString())
                .andExpect(jsonPath("$.debug.sourceNode").isString())
                .andDo(document("orders-public-fields",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                fieldWithPath("totalAmount")
                                        .description("Tổng tiền theo VND"),
                                fieldWithPath("items")
                                        .description("Các dòng hàng"),
                                fieldWithPath("items[].sku")
                                        .description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity")
                                        .description("Số lượng sản phẩm"),
                                fieldWithPath("internalTraceId").ignored(),
                                subsectionWithPath("debug").ignored(),
                                fieldWithPath("items[].stockSnapshot").ignored()
                        )
                ));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable("id") long id) {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("id", "ORD-" + id);
            body.put("status", "CONFIRMED");
            body.put("totalAmount", 250000);
            body.put("items", List.of(
                    Map.of("sku", "BK-01", "quantity", 2,
                           "stockSnapshot", 18),
                    Map.of("sku", "BK-02", "quantity", 1,
                           "stockSnapshot", 7)
            ));
            body.put("internalTraceId", "trace-7a91");
            body.put("debug", Map.of(
                    "sourceNode", "node-03",
                    "timingMs", 12,
                    "flags", Map.of("cacheHit", true)
            ));
            return body;
        }
    }
}
```

Hai hành vi cần hiểu:

- Assertion `jsonPath("$.internalTraceId").isString()` xác nhận response thực tế vẫn chứa metadata nội bộ.
- Descriptor `fieldWithPath("internalTraceId").ignored()` xác định metadata đó không xuất hiện trong bảng snippet.

Ignore không loại dữ liệu khỏi HTTP body. Bất kỳ người dùng nào nhận response vẫn có thể đọc các byte đó. Nếu dữ liệu không được phép tiết lộ, cần sửa DTO/serializer, áp dụng quyền truy cập hoặc loại bỏ dữ liệu trước khi gửi.

## 7. Ignore không phải cơ chế bảo mật

Giả sử response có:

```json
{
  "id": "CUS-17",
  "displayName": "Khách hàng 17",
  "email": "customer@example.test",
  "accessToken": "secret-token",
  "passwordHash": "hash-value"
}
```

Nếu `accessToken` hoặc `passwordHash` xuất hiện trong response, gọi `ignored()` chỉ khiến chúng không xuất hiện trong bảng mô tả. Nó **không xóa, mã hóa hoặc che** dữ liệu trong response và không ngăn client truy cập.

Với trường không được phép công khai:

1. Không đưa giá trị thật vào response rồi trông chờ tài liệu bỏ qua.
2. Sửa DTO/projection hoặc serializer để trường không được serialize ra HTTP.
3. Áp dụng phân quyền và kiểm thử user không đủ quyền không nhận trường.
4. Dùng dữ liệu giả lập trong fixture; không đưa thông tin cá nhân hoặc secret thật vào snippet.
5. Viết assertion cho các path nhạy cảm không được trả ra.

Ví dụ:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.accessToken").doesNotExist())
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
```

Nếu key có thể tồn tại với giá trị null mà vẫn vi phạm hợp đồng “không được trả”, hãy parse response thành `JsonNode` và xác nhận `!node.has("accessToken")`. Kiểm tra giá trị null không đồng nghĩa khẳng định key hoàn toàn vắng mặt.

## 8. Khi nào ignore, khi nào xóa khỏi response?

| Tình huống | Hướng xử lý | Lý do |
| --- | --- | --- |
| Trace ID được phép công khai để hỗ trợ tra cứu | Có thể ignore khỏi bảng nếu không phải field client cần | Giảm nhiễu tài liệu |
| Debug metadata dành riêng môi trường nội bộ | Cân nhắc loại khỏi response public | Tránh mở rộng contract |
| Password hash, access token hoặc secret | Loại khỏi response và viết test không rò rỉ | Ignore không bảo vệ dữ liệu |
| Trường cũ vẫn được trả để tương thích | Mô tả hoặc ignore theo quyết định versioning | Thay đổi cần được quản lý |
| Field phát sinh bất ngờ chưa rõ nguồn | Điều tra trước, chưa vội ignore | Có thể là lỗi serialize hoặc lộ dữ liệu |
| Field public quan trọng nhưng muốn bảng ngắn | Dùng subsection hoặc trang tham chiếu | Không bỏ thông tin client cần mà không có tài liệu thay thế |

Nếu client bắt đầu phụ thuộc vào một trường đã ignore, trường đó có thể đã trở thành hành vi thực tế. Thay đổi hoặc xóa nó cần được đánh giá về tương thích.

## 9. Giữ strict contract hay dùng relaxed mode?

### 9.1. Liệt kê trường cố ý bỏ qua trong strict mode

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn"),
    fieldWithPath("internalTraceId").ignored(),
    subsectionWithPath("debug").ignored()
)
```

Cách này thể hiện các trường đã biết và loại trừ có chủ đích. Nếu payload phát sinh một field khác chưa có descriptor hay chưa thuộc nhánh được xử lý, strict mode vẫn giúp phát hiện thay đổi đó.

### 9.2. Dùng `relaxedResponseFields` cho tài liệu từng phần

```java
relaxedResponseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn")
)
```

Relaxed cho phép field ngoài danh sách. Phù hợp khi bài test chỉ nhằm ghi một phần cấu trúc hoặc đang chuyển đổi contract. Đổi lại, field mới có thể xuất hiện mà test tài liệu không phát hiện. Nếu chỉ có một nhánh cần loại khỏi bảng, `ignored()` trong `responseFields` strict dễ rà soát hơn.

Field muốn bỏ khỏi bảng thì dùng `ignored()`. Field muốn xuất hiện trong bảng nhưng có thể vắng thì dùng `optional()`, thêm `type(...)` nếu fixture không thể giúp suy ra kiểu.

## 10. Tái sử dụng descriptor

Khi nhiều endpoint dùng cùng metadata kỹ thuật, có thể trừu tượng hóa descriptor:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

static FieldDescriptor[] operationalFields() {
    return new FieldDescriptor[] {
        fieldWithPath("internalTraceId").ignored(),
        subsectionWithPath("debug").ignored()
    };
}
```

Sau đó kết hợp với descriptor public:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng")
).and(operationalFields());
```

Ví dụ chỉ phù hợp khi response thực sự có cùng cấu trúc. Nếu endpoint khác dùng `metadata.traceId` thay cho `internalTraceId`, cần descriptor riêng. Tái sử dụng chỉ đúng khi path và ý nghĩa tương đương.

## 11. Snippet và tài liệu xuất bản

Sau bài kiểm thử `document("orders-public-fields", ...)`, snippet response field thường nằm tại:

```text
build/generated-snippets/
└── orders-public-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Đây là các tệp liên quan; tùy cấu hình còn snippet mặc định khác. Với Maven, thư mục thường là `target/generated-snippets`.

Bảng `response-fields.adoc` chỉ chứa trường được tài liệu hóa; descriptor `ignored()` không xuất hiện thành hàng. Có thể nhúng vào Asciidoctor:

```adoc
= Order API
:snippets: build/generated-snippets

== Xem đơn hàng

=== HTTP response
include::{snippets}/orders-public-fields/http-response.adoc[]

=== Các trường payload được công bố
include::{snippets}/orders-public-fields/response-fields.adoc[]
```

Quy trình build/CI cần chạy HTTP tests trước bước Asciidoctor để snippet được tạo từ response mới nhất. Nếu response thêm field chưa được xử lý trong strict mode, test cần thất bại để nhóm quyết định: công bố trường, ignore có chủ đích, hoặc loại khỏi response thực tế. Nếu xuất bản Markdown, cần converter hoặc template phù hợp; snippet mặc định là Asciidoctor.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field nội bộ vẫn xuất hiện trong bảng | Chưa gọi `ignored()` | Đánh dấu descriptor cụ thể là ignored |
| Dùng `ignored()` để bỏ qua field đang vắng | Nhầm với optional | Dùng `optional()` nếu muốn tài liệu hóa field có thể thiếu |
| Cả nhánh debug biến mất dù còn field public | Ignore subsection quá rộng | Chọn từng field nội bộ hoặc mô tả field public con |
| Field mới không bị phát hiện | Dùng relaxed mode quá rộng | Trở lại strict và khai báo ignore tường minh |
| Trường nhạy cảm vẫn trong HTTP response | Nghĩ ignored sẽ xóa field | Sửa DTO/serialization/access control và test cấm xuất hiện |
| Dùng `items.stockSnapshot` cho array object | Bỏ ký hiệu phần tử lặp | Dùng `items[].stockSnapshot` |
| Ignore nhánh mảng với fixture rỗng | Không có phần tử mẫu để kiểm chứng path con | Test tài liệu với phần tử đại diện |
| Tái sử dụng descriptor sang endpoint khác lỗi | Path/schema khác nhau | Tách descriptor hoặc ghép prefix chính xác |
| Snippet không cập nhật | Test không chạy hoặc thứ tự build sai | Chạy test sinh snippets trước Asciidoctor |

## 13. Bài thực hành

Dùng response đơn hàng ở mục 6:

1. Thêm `internalRequestId` ở root. Dùng `fieldWithPath("internalRequestId").ignored()` và xác nhận field không có hàng trong bảng.
2. Thêm `diagnostics` với `timingMs`, `sourceNode` và `cacheHit`. Dùng `subsectionWithPath("diagnostics").ignored()` để loại cả nhánh.
3. Đưa `diagnostics.requestId` thành public. Thay ignore cả subsection bằng descriptor riêng: mô tả `requestId`, ignore các field nội bộ còn lại.
4. Thêm `items[].warehouseCode` và `items[].stockSnapshot`. Bỏ qua hai path, vẫn mô tả `items[].sku` và `items[].quantity`.
5. Gọi thử `relaxedResponseFields` với hai field `id` và `status`. Thêm field bất ngờ và quan sát vì sao relaxed mode có thể không phát hiện.
6. Cho `accessToken` xuất hiện trong HTTP response rồi đánh dấu ignored. Xác nhận nó vẫn nhìn thấy ở response body và viết assertion bảo đảm API public không trả token.
7. Tạo hai endpoint có cấu trúc debug khác nhau. Quyết định descriptor nào có thể tái sử dụng.
8. Nhúng snippet vào Asciidoctor, xác nhận bảng chỉ chứa field được công bố và pipeline vẫn thất bại khi có field public mới chưa được xử lý trong strict mode.

**Tiêu chí hoàn thành:** bạn biết đánh dấu field hay subsection đã biết nhưng không muốn đưa vào bảng; phân biệt ignore với optional và relaxed; không nhầm ignore tài liệu với bảo mật response; giữ kiểm tra strict cho phần còn lại; và duy trì snippet sinh từ kiểm thử trong build/CI.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): mô tả payload, descriptor, trường optional và ignored.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/org/springframework/restdocs/payload/FieldDescriptor.html): API `ignored()`, `optional()` và `type(...)`.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `responseFields`, `relaxedResponseFields`, `subsectionWithPath` và helper cho payload.
