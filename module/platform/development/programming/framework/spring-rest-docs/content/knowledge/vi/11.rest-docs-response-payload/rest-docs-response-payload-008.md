# Xác nhận mọi trường xuất hiện trong payload đã được xử lý

## 1. Vì sao cần kiểm soát toàn bộ response?

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Payload có thể thay đổi khi server thêm field, đổi tên thuộc tính, mở rộng object hoặc serialize thêm metadata. Nếu test chỉ mô tả một vài field quan trọng, thay đổi ngoài dự kiến có thể đi vào API mà không được review.

`responseFields(...)` ở chế độ mặc định (strict) đối chiếu payload thực tế trong test với danh sách `FieldDescriptor`. Mỗi field xuất hiện cần có quyết định rõ ràng: mô tả cho client, ignore có chủ đích hoặc được bao phủ bởi subsection. Ngược lại, descriptor bắt buộc phải tìm thấy path; field được phép vắng phải được đánh dấu `optional()`.

Mục tiêu là bảo đảm không có field mới nào âm thầm xuất hiện mà chưa được xem xét.

## 2. Cơ chế strict của responseFields

Payload ví dụ:

```json
{
  "id": "ORD-1200",
  "status": "CONFIRMED",
  "customer": {
    "id": "CUS-17",
    "displayName": "Khách hàng 17"
  },
  "items": [
    {"sku": "BK-01", "quantity": 2}
  ],
  "totalAmount": 250000,
  "internalTraceId": "trace-1200"
}
```

Bộ descriptor strict xử lý mọi field như sau:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    fieldWithPath("customer").description("Thông tin khách hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.displayName")
        .description("Tên hiển thị khách hàng"),
    fieldWithPath("items").description("Các dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng"),
    fieldWithPath("totalAmount").description("Tổng tiền theo VND"),
    fieldWithPath("internalTraceId").ignored()
)
```

| Field | Quyết định | Lý do |
| --- | --- | --- |
| id, status | Mô tả | Field public client cần hiểu |
| customer, customer.id, customer.displayName | Mô tả | Cấu trúc thông tin khách hàng |
| items, items[].sku, items[].quantity | Mô tả | Array và dữ liệu từng phần tử |
| totalAmount | Mô tả | Tổng tiền và đơn vị |
| internalTraceId | Ignore | Metadata vận hành không cần trong bảng public |

Ở strict mode, field xuất hiện trong payload nhưng chưa được descriptor xử lý sẽ khiến snippet generation thất bại. Descriptor bắt buộc có path không xuất hiện cũng có thể làm test thất bại. Cơ chế hai chiều phát hiện cả thay đổi thêm field và thay đổi làm mất field.

Strict mode chỉ kiểm chứng payload cụ thể đã được test. Nó không tự chứng minh mọi quy tắc nghiệp vụ hoặc mọi biến thể response ở production; cần fixture và assertion riêng cho các nhánh đó.

## 3. Quyết định cho từng field

| Quyết định | Cách khai báo | Khi nào dùng |
| --- | --- | --- |
| Công bố cho client | `fieldWithPath(...).description(...)` | Field thuộc contract client cần hiểu |
| Cho phép vắng mặt | `.optional()`, thêm `.type(...)` khi cần | Field hợp lệ có thể không xuất hiện |
| Có mặt nhưng không công bố | `.ignored()` | Field đã biết nhưng không đưa vào bảng |
| Bao phủ một nhánh | `subsectionWithPath(...)` | Chi tiết nhánh được trình bày ở nơi khác |
| Cho phép field ngoài danh sách | `relaxedResponseFields(...)` | Có chủ đích chỉ tài liệu hóa một phần |

### 3.1. Field public

```java
fieldWithPath("status")
    .description("Trạng thái xử lý đơn hàng");
```

Mô tả nên giải thích ý nghĩa, đơn vị, format, giá trị hợp lệ hoặc cách sử dụng khi cần.

### 3.2. Field nội bộ

```java
fieldWithPath("internalTraceId").ignored()
```

Descriptor này ghi nhận field được xử lý có chủ đích nhưng không hiển thị trong bảng. Ignore không xóa field khỏi HTTP response và không che dữ liệu. Nếu field không được phép gửi client, hãy sửa DTO/serialization và viết test cấm xuất hiện.

### 3.3. Field được phép vắng

```java
fieldWithPath("deliveryNote")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Ghi chú giao hàng, có thể vắng mặt");
```

`optional()` nới yêu cầu xuất hiện trong payload mẫu. Nếu field vắng trong fixture, REST Docs không thể suy ra kiểu từ dữ liệu; khai báo `.type(...)` khi cần. Optional không tự nói giá trị JSON null có được phép hay không.

### 3.4. Subsection

```java
subsectionWithPath("customer")
    .description("Thông tin khách hàng; xem tài liệu Customer response");
```

Subsection ghi nhận nhánh object/array cùng descendant như một đơn vị. Dùng khi field con có tài liệu riêng. Nếu client cần biết chi tiết `customer.id` và `customer.displayName` ngay tại đây, khai báo từng field con.

## 4. Phát hiện field mới và field bị thiếu

### 4.1. Field mới

Payload ban đầu:

```json
{"id": "ORD-1200", "status": "CONFIRMED"}
```

Server thêm `sourceChannel`:

```json
{
  "id": "ORD-1200",
  "status": "CONFIRMED",
  "sourceChannel": "MOBILE"
}
```

Nếu descriptor strict vẫn chỉ có `id` và `status`, tạo snippet sẽ phát hiện `sourceChannel` chưa được xử lý và thất bại. Team cần review: thêm mô tả nếu là field public; ignore nếu là metadata hợp lệ nhưng không công bố; hoặc sửa DTO nếu field không nên có trong response.

Không chuyển sang relaxed chỉ để dập lỗi trước khi biết nguyên nhân field mới xuất hiện.

### 4.2. Field bắt buộc bị thiếu

Descriptor:

```java
fieldWithPath("customer.email")
    .description("Email liên hệ");
```

Fixture:

```json
{
  "customer": {
    "id": "CUS-17",
    "displayName": "Khách hàng 17"
  }
}
```

Path `customer.email` không tồn tại. Nếu email bắt buộc, implementation hoặc fixture không khớp contract. Nếu email được phép vắng, hãy mô tả rõ:

```java
fieldWithPath("customer.email")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Email khách hàng, có thể không được cung cấp");
```

Không đánh dấu mọi descriptor thành optional để làm test qua vì như vậy sẽ mất khả năng phát hiện field bắt buộc bị mất.

## 5. Object lồng, array và field lặp

Object lồng:

```json
{
  "customer": {
    "id": "CUS-17",
    "profile": {
      "displayName": "Khách hàng 17",
      "locale": "vi-VN"
    }
  }
}
```

Path có thể là `customer`, `customer.id`, `customer.profile.displayName` và `customer.profile.locale`. Nếu nhánh profile có tài liệu riêng, dùng `subsectionWithPath("customer.profile")`.

Array object:

```json
{
  "items": [
    {"sku": "BK-01", "quantity": 2, "warehouseCode": "HCM"},
    {"sku": "BK-02", "quantity": 1, "warehouseCode": "HAN"}
  ]
}
```

Path phần tử lặp dùng `[]`:

```java
responseFields(
    fieldWithPath("items").description("Các dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng"),
    fieldWithPath("items[].warehouseCode")
        .description("Mã kho xuất hàng")
)
```

Nếu `warehouseCode` là metadata nội bộ, thay descriptor bằng `.ignored()`. Mô tả array ở cấp cha không tự thay thế việc mô tả field con cần công bố.

### 5.1. Mảng lồng nhiều cấp

```json
{
  "shipments": [
    {
      "packages": [
        {
          "packageId": "P-01",
          "items": [{"sku": "BK-01", "quantity": 2}]
        }
      ]
    }
  ]
}
```

Các path chi tiết gồm `shipments`, `shipments[].packages`, `shipments[].packages[].packageId`, `shipments[].packages[].items`, `shipments[].packages[].items[].sku` và `shipments[].packages[].items[].quantity`. Mỗi tầng array cần `[]` tương ứng; fixture cần có phần tử ở từng cấp được mô tả.

### 5.2. Mảng rỗng và root array

`{"items": []}` vẫn có field `items`, vì vậy có thể mô tả bản thân mảng. Fixture không có field con như `items[].id` để tìm. Tách test sinh tài liệu chi tiết phần tử khỏi test danh sách rỗng.

Nếu root response là `[]`:

```java
responseFields(
    fieldWithPath("[]").description("Danh sách sản phẩm"),
    fieldWithPath("[].id").description("Mã sản phẩm"),
    fieldWithPath("[].name").description("Tên sản phẩm")
)
```

Với root array rỗng, không có phần tử để mô tả chi tiết; dùng fixture có object đại diện và test ca rỗng riêng.

## 6. Ví dụ MockMvc: phát hiện field chưa xử lý

Ví dụ dùng JUnit Jupiter, MockMvc, Jackson và `spring-restdocs-mockmvc`:

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
class StrictResponseFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void everyResponseFieldHasAnExplicitDecision() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 1200)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-1200"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andDo(document("orders-strict-fields",
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                fieldWithPath("customer")
                                        .description("Thông tin khách hàng"),
                                fieldWithPath("customer.id")
                                        .description("Mã khách hàng"),
                                fieldWithPath("customer.displayName")
                                        .description("Tên khách hàng"),
                                fieldWithPath("totalAmount")
                                        .description("Tổng tiền theo VND"),
                                fieldWithPath("internalTraceId").ignored()
                        )
                ));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable("id") long id) {
            Map<String, Object> customer = Map.of(
                    "id", "CUS-17",
                    "displayName", "Khách hàng 17");

            Map<String, Object> response = new LinkedHashMap<>();
            response.put("id", "ORD-" + id);
            response.put("status", "CONFIRMED");
            response.put("customer", customer);
            response.put("totalAmount", 250000);
            response.put("internalTraceId", "trace-1200");
            return response;
        }
    }
}
```

Khi thêm `sourceChannel` vào response mà chưa có descriptor, test sinh snippet strict thất bại. Sau review, thêm mô tả hoặc ignore có chủ đích. Nếu field không nên có trong API public, sửa response và thêm assertion kiểm tra path không tồn tại.

Test trên chỉ kiểm tra fixture HTTP cụ thể. API có nhiều biến thể cần test riêng cho đơn mới tạo, đã thanh toán, đã hủy, quyền truy cập khác nhau hoặc collection rỗng.

## 7. Fixture đại diện cho cấu trúc

| Mục tiêu | Fixture nên có | Lý do |
| --- | --- | --- |
| Field root | Object có field root | Tìm được path |
| Object con | Parent và các field con | Kiểm tra nested paths |
| Array object | Ít nhất một phần tử | Quan sát path phần tử |
| Array lồng | Phần tử tại mỗi tầng | Kiểm tra path nhiều cấp |
| Optional vắng | Fixture bỏ field đó | Chứng minh optional |
| Nullable | Key có giá trị null | Phân biệt null và missing |
| Nhánh ignore | Payload có nhánh thực tế | Xác minh quyết định ignore |
| Root array | Array có phần tử | Mô tả các path con |

Không ép một fixture duy nhất đại diện các nhánh nghiệp vụ không thể đồng thời tồn tại. Ví dụ đơn hàng không thể vừa PAID vừa CANCELLED nếu contract không cho phép. Tạo test và snippet riêng theo từng trạng thái.

Ví dụ identifier:

```text
orders-created-response
orders-paid-response
orders-cancelled-response
orders-empty-collection
```

## 8. Checklist review descriptor

- [ ] Mọi field xuất hiện trong fixture đã được mô tả, ignore hoặc bao phủ bởi subsection.
- [ ] Không có field public mới thiếu mô tả.
- [ ] Path object lồng khớp JSON sau serialization.
- [ ] Path array dùng `[]` ở đúng cấp.
- [ ] Field bắt buộc không bị đánh dấu optional tùy tiện.
- [ ] Field có thể vắng có `optional()` và kiểu rõ ràng nếu cần.
- [ ] Field nullable được phân biệt với field missing.
- [ ] Field nội bộ ignore có lý do; dữ liệu nhạy cảm đã bị loại khỏi response thật.
- [ ] Fixture có phần tử mẫu cho path lặp.
- [ ] Các nhánh response quan trọng có test/snippet riêng.
- [ ] Strict mode được giữ ở nơi cần phát hiện field mới.
- [ ] Asciidoctor dùng snippet mới từ cùng lần chạy test.

## 9. Strict và relaxed

`responseFields(...)` mặc định phù hợp với tài liệu contract cần kiểm soát thay đổi. `relaxedResponseFields(...)` phù hợp khi cố ý chỉ công bố một phần payload hoặc có lý do chuyển đổi contract.

| Đặc điểm | Strict `responseFields` | Relaxed `relaxedResponseFields` |
| --- | --- | --- |
| Field payload chưa khai báo | Có thể làm snippet thất bại | Được cho phép |
| Descriptor bắt buộc nhưng path không có | Có thể làm snippet thất bại | Vẫn phải phù hợp, trừ khi optional |
| Field được ignore | Cần khai báo tường minh | Có thể không cần vì field ngoài danh sách được cho phép |
| Phát hiện field mới | Phù hợp hơn với contract quản lý | Yếu hơn do field lạ có thể lọt qua |
| Trường hợp sử dụng | Tài liệu contract đầy đủ | Tài liệu một phần hoặc migration |

Relaxed không phải cách khắc phục chung cho descriptor sai. Nếu dùng relaxed, nên có schema/assertion riêng kiểm soát các phần payload cần thiết.

## 10. Snippet và CI

Khi test `document("orders-strict-fields", ...)` chạy thành công, snippet thường nằm trong thư mục generated snippets. Với Gradle:

```text
build/generated-snippets/
└── orders-strict-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Với Maven, thư mục phổ biến là `target/generated-snippets`. Vị trí output có thể cấu hình và có thể tạo thêm snippet mặc định.

Asciidoctor nhúng response cùng bảng field:

```adoc
= Order API
:snippets: build/generated-snippets

== Xem đơn hàng

=== HTTP response
include::{snippets}/orders-strict-fields/http-response.adoc[]

=== Các trường response
include::{snippets}/orders-strict-fields/response-fields.adoc[]
```

Thứ tự build: biên dịch test, chạy HTTP tests tạo snippet, dừng nếu descriptor strict chưa bao phủ payload, rồi mới biên soạn Asciidoctor và đóng gói. Khi field mới làm test thất bại, reviewer quyết định công bố, ignore có chủ đích hay loại khỏi response. Nếu xuất bản Markdown, cần template/converter thích hợp; snippet mặc định là Asciidoctor.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test báo field mới chưa được tài liệu hóa | Payload đổi nhưng descriptor chưa cập nhật | Review; mô tả hoặc ignore có chủ đích |
| Test báo field mô tả không tìm thấy | Fixture thiếu path, path sai hoặc serializer đổi tên | Kiểm tra JSON; sửa fixture/path hoặc optional theo contract |
| Chỉ mô tả object cha | Chưa quyết định cho field con | Dùng descriptor con hoặc subsection |
| Field array không tìm thấy | Thiếu `[]` hoặc array rỗng | Sửa path và fixture |
| Optional cho mọi descriptor | Không phát hiện field bắt buộc bị mất | Chỉ optional theo contract |
| Relaxed để build qua | Không review field mới | Giữ strict hoặc nêu lý do relaxed |
| Ignore trường nhạy cảm | Nhầm tài liệu với bảo mật | Loại field khỏi response và viết test |
| Snippet cũ được xuất bản | Task tài liệu chạy trước test | Tạo snippet trước Asciidoctor |

## 12. Bài thực hành

Dùng response đơn hàng ở mục 2:

1. Thêm `sourceChannel` mà không sửa descriptor. Chạy test strict và giải thích lỗi.
2. Quyết định `sourceChannel` là public hay internal. Viết description hoặc đánh dấu ignored.
3. Xóa `customer.displayName` khỏi fixture nhưng giữ descriptor bắt buộc. Quan sát lỗi; quyết định có thật sự optional không.
4. Thêm `items[].warehouseCode`; khai báo mô tả hoặc ignore đúng path.
5. Đổi `items` thành mảng rỗng. Tách test ca rỗng khỏi test cấu trúc phần tử.
6. Thêm object `promotion`. So sánh mô tả field con với `subsectionWithPath("promotion")`.
7. Thử relaxed chỉ với `id` và `status`; thêm field mới rồi so sánh với strict.
8. Tạo snippet riêng cho đơn đã thanh toán và đơn đã hủy.
9. Nhúng snippet vào Asciidoctor và xác nhận test chạy trước xuất bản.

**Tiêu chí hoàn thành:** bạn đọc response JSON và quyết định rõ cho từng field; hiểu lỗi strict khi payload thêm field hoặc thiếu field bắt buộc; tổ chức fixture nested/array/optional/null; chọn strict hay relaxed theo mục đích; và khiến build/CI phát hiện thay đổi response chưa được review.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): quy tắc mô tả payload, field descriptor, optional, ignored và relaxed response fields.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `responseFields`, `relaxedResponseFields`, `subsectionWithPath` và helper mô tả payload.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/org/springframework/restdocs/payload/FieldDescriptor.html): `optional()`, `ignored()` và `type(...)`.
