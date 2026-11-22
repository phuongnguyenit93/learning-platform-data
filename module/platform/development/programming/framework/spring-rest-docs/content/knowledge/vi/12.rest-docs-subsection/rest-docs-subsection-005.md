# Trường hợp phần còn lại được mô tả ở tài liệu khác

## 1. Bối cảnh: tài liệu API lớn cần chia thành nhiều phần

**Spring REST Docs** sinh tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Sau khi kiểm thử chạy thành công, các snippet về HTTP request, response, payload, tham số và header có thể được biên soạn vào **Asciidoctor/Markdown**, rồi đưa vào pipeline build và CI.

Bài thuộc chương **Subsection**, tập trung vào tình huống: **một trang tài liệu chỉ giải thích một phần payload, còn các phần còn lại được giải thích chi tiết ở trang hoặc mục tài liệu khác**.

Một response lớn có thể chứa thông tin đơn hàng, khách hàng, giao hàng và tổng tiền. Nếu ghi mọi field vào một bảng duy nhất, người đọc khó tìm thông tin, phần giải thích có thể trùng lặp giữa các endpoint, và tài liệu khó tái sử dụng. Trong trường hợp đó, ta cần tách rõ:

- **Bảng tổng quan:** mô tả contract của endpoint tại cấp cao, chỉ ra các nhóm thông tin.
- **Bảng chi tiết:** mô tả field nằm trong từng nhóm, có thể xuất hiện ở chương/trang khác.
- **Liên kết tài liệu:** hướng người đọc từ bảng tổng quan tới tài liệu chi tiết.
- **Kiểm thử:** xác minh các nhóm dữ liệu được document đúng theo phạm vi mong muốn.

**Mục tiêu học tập:** hiểu cách kết hợp `subsectionWithPath(...)`, `beneathPath(...)`, `responseFields(...)`/`requestFields(...)` để chia tài liệu mà vẫn kiểm soát được những thay đổi ngoài ý muốn của payload; đồng thời biết khi nào nên dùng `relaxedResponseFields(...)` hoặc `ignored()`.

## 2. Ví dụ: một response, nhiều trang tài liệu

Giả sử endpoint `GET /orders/ord-120` trả response `200 OK`:

```json
{
  "id": "ord-120",
  "status": "PAID",
  "customer": {
    "id": "cus-8",
    "name": "Lan Nguyen",
    "contact": {
      "email": "lan@example.test"
    }
  },
  "delivery": {
    "recipient": "Lan Nguyen",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "total": {
    "amount": 250000,
    "currency": "VND"
  }
}
```

Thay vì lập một bảng dài cho toàn bộ response, tài liệu được tổ chức như sau:

```text
Tài liệu API đơn hàng
├── GET /orders/{id}
│   ├── Ví dụ HTTP response đầy đủ
│   ├── id: mã đơn hàng
│   ├── status: trạng thái
│   ├── customer: xem "Thông tin khách hàng"
│   ├── delivery: xem "Thông tin giao hàng"
│   └── total: xem "Quy ước số tiền"
├── Thông tin khách hàng
│   ├── customer.id
│   ├── customer.name
│   └── customer.contact.email
├── Thông tin giao hàng
│   ├── delivery.recipient
│   ├── delivery.address.city
│   └── delivery.address.country
└── Quy ước số tiền
    ├── total.amount
    └── total.currency
```

Các bảng chi tiết ở tài liệu bên dưới có thể sử dụng snippet sinh ra từ **cùng bài kiểm thử**. Mỗi bảng vẫn có khả năng kiểm tra field trong phạm vi của mình.

Ở bảng tổng quan, dùng:

```java
responseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    fieldWithPath("status")
        .description("Trạng thái đơn hàng"),
    subsectionWithPath("customer")
        .description("Thông tin khách hàng; xem mục Thông tin khách hàng"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng; xem mục Thông tin giao hàng"),
    subsectionWithPath("total")
        .description("Tổng tiền; xem mục Quy ước số tiền")
)
```

`subsectionWithPath("customer")` đại diện cho **cả object con** `customer`, bao gồm các hậu duệ như `customer.name`, `customer.contact.email`. Tương tự, descriptor cho `delivery` và `total` bao phủ các nhánh tương ứng.

Bảng tổng quan ở chế độ mặc định **strict**: những field cấp gốc như `id`, `status` và các subsection đã được mô tả; nếu response bất ngờ thêm field `promotionCode` tại cấp gốc, test có thể thất bại vì chưa có descriptor. Tuy nhiên, bảng tổng quan không tự kiểm soát đầy đủ field bên trong mỗi subsection: thêm `customer.vipLevel` có thể vẫn hợp lệ đối với **snippet tổng quan**. Để bảo vệ schema con, cần tạo snippet chi tiết riêng.

## 3. Hai công cụ bổ sung cho nhau

| API Spring REST Docs | Vai trò | Khi nào dùng |
| --- | --- | --- |
| `fieldWithPath("id")` | Mô tả field cụ thể | Field được giải thích trực tiếp trong bảng đang tạo |
| `subsectionWithPath("customer")` | Mô tả cả nhánh và xem các field con là đã document trong snippet hiện tại | Nhánh lớn có bảng/trang chi tiết ở nơi khác |
| `beneathPath("customer")` | Chọn phần payload dưới path làm đầu vào cho snippet riêng | Muốn sinh body hoặc bảng field chi tiết của nhánh |
| `responseFields(beneathPath(...), ...)` | Kiểm tra và mô tả field theo path tương đối với nhánh đã chọn | Tài liệu schema con của response |
| `requestFields(beneathPath(...), ...)` | Tương tự, nhưng áp dụng cho request | Tài liệu schema con của request |
| `responseBody(beneathPath(...))` | Tạo đoạn body chỉ cho nhánh đã chọn | Muốn thêm ví dụ JSON dễ đọc ở trang chi tiết |

**Phân biệt cần ghi nhớ:**

- `subsectionWithPath(...)` là một **field descriptor**. Nó không sinh ra một file JSON con hoặc một bảng chi tiết mới.
- `beneathPath(...)` là một **subsection extractor**. Khi kết hợp với `responseFields(...)` hoặc `requestFields(...)`, descriptor bên trong dùng **path tương đối**: từ `customer`, viết `contact.email` thay vì `customer.contact.email`.
- Việc ghi trong mô tả rằng một nhóm "được document ở tài liệu khác" chỉ là thông tin dành cho người đọc. **Spring REST Docs không tự kiểm tra liên kết giữa hai trang**; nhóm phát triển cần tạo snippet chi tiết và lắp ghép tài liệu chính xác.

## 4. Ví dụ hoàn chỉnh: kiểm thử MockMvc sinh cả phần tổng quan và phần chi tiết

Ví dụ dưới dùng **JUnit 5**, **Java 17+**, **MockMvc**, **Spring MVC** và **Spring REST Docs**. Controller mẫu trả dữ liệu cố định để có thể quan sát trực tiếp các snippet; khi đưa vào dự án thật, thay controller mẫu bằng controller nghiệp vụ và fixture test ổn định.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderSplitDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOverviewAndSeparatedSections() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-120")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-8"))
                .andExpect(jsonPath("$.delivery.address.country").value("VN"))
                .andExpect(jsonPath("$.total.amount").value(250000))
                .andDo(document("orders-get",

                        // (1) Bảng tổng quan: các object con là subsection.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                subsectionWithPath("customer")
                                        .description("Khách hàng; xem mục Khách hàng"),
                                subsectionWithPath("delivery")
                                        .description("Giao hàng; xem mục Giao hàng"),
                                subsectionWithPath("total")
                                        .description("Tổng tiền; xem mục Số tiền")
                        ),

                        // (2) Bảng chi tiết sẽ được nhúng vào trang Khách hàng.
                        responseFields(
                                beneathPath("customer")
                                        .withSubsectionId("customer"),
                                fieldWithPath("id")
                                        .description("Mã khách hàng"),
                                fieldWithPath("name")
                                        .description("Tên hiển thị"),
                                fieldWithPath("contact.email")
                                        .description("Email liên hệ")
                        ),

                        // (3) Bảng chi tiết sẽ được nhúng vào trang Giao hàng.
                        responseFields(
                                beneathPath("delivery")
                                        .withSubsectionId("delivery"),
                                fieldWithPath("recipient")
                                        .description("Người nhận"),
                                fieldWithPath("address.city")
                                        .description("Thành phố giao hàng"),
                                fieldWithPath("address.country")
                                        .description("Mã quốc gia")
                        ),

                        // (4) Bảng chi tiết sẽ được nhúng vào trang Số tiền.
                        responseFields(
                                beneathPath("total")
                                        .withSubsectionId("total"),
                                fieldWithPath("amount")
                                        .description("Số tiền (đơn vị nhỏ nhất theo hợp đồng)"),
                                fieldWithPath("currency")
                                        .description("Mã đơn vị tiền tệ")
                        ),

                        // (5) Ví dụ body riêng cho trang Khách hàng.
                        responseBody(
                                beneathPath("customer")
                                        .withSubsectionId("customer"))
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> findById(@PathVariable String id) {
            if (!"ord-120".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-120",
                      "status": "PAID",
                      "customer": {
                        "id": "cus-8",
                        "name": "Lan Nguyen",
                        "contact": {
                          "email": "lan@example.test"
                        }
                      },
                      "delivery": {
                        "recipient": "Lan Nguyen",
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        }
                      },
                      "total": {
                        "amount": 250000,
                        "currency": "VND"
                      }
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json);
        }
    }
}
```

Cần có JUnit Jupiter, Spring MVC Test và `spring-restdocs-mockmvc` trong test classpath, cùng cấu hình nơi sinh snippet. Mã mẫu sử dụng Java text block nên yêu cầu Java 17+.

Trong test này có **bốn lời gọi `responseFields(...)` khác nhau**. Mỗi lời gọi tạo một snippet: bảng tổng quan dùng ID mặc định, còn ba bảng chi tiết dùng ID của subsection để không đè tên nhau. Các assertion `jsonPath` kiểm tra vài giá trị nghiệp vụ quan trọng; bảng field strict hỗ trợ kiểm chứng schema, nhưng không thay thế kiểm tra nghiệp vụ hoặc validation của API.

### 4.1. Bảng cấp gốc bao phủ các nhánh được giải thích ở nơi khác

Từ gốc của response, bảng tổng quan document năm phần: `id`, `status`, `customer`, `delivery` và `total`. Vì các object con được mô tả bằng `subsectionWithPath`, Spring REST Docs không đòi hỏi field con phải xuất hiện thành hàng trong **bảng tổng quan**.

Cách làm này phù hợp khi trang `GET /orders/{id}` cần giới thiệu cấu trúc response, nhưng hợp đồng khách hàng/giao hàng/tiền tệ đã có phần giải thích chuyên sâu.

### 4.2. Mỗi bảng chi tiết có đường dẫn riêng

Khi khai báo `responseFields(beneathPath("customer").withSubsectionId("customer"), ...)`, REST Docs làm việc với nhánh `customer` đã trích. Bảng chi tiết có:

| Field hiển thị trong bảng chi tiết | Path đầy đủ trong response gốc |
| --- | --- |
| `id` | `customer.id` |
| `name` | `customer.name` |
| `contact.email` | `customer.contact.email` |

Tương tự, với `beneathPath("delivery")`, đường dẫn là `recipient`, `address.city`, `address.country`; với `beneathPath("total")`, đường dẫn là `amount`, `currency`.

Điểm kỹ thuật quan trọng: **các bảng chi tiết là strict độc lập**. Bảng cấp gốc bao phủ toàn bộ `customer`; bảng chi tiết của `customer` vẫn có thể thất bại nếu xuất hiện field mới `customer.phone` mà chưa có descriptor. Sự bao phủ ở một snippet không làm nới lỏng các snippet khác.

### 4.3. Body riêng chỉ là ví dụ, bảng field mới kiểm tra schema

`responseBody(beneathPath("customer").withSubsectionId("customer"))` sinh snippet văn bản phần body được trích từ `customer`. Nó giúp người đọc nhìn cấu trúc JSON ngắn gọn hơn so với toàn bộ HTTP response, nhưng bản thân `responseBody(...)` không cần một danh sách descriptor để kiểm tra mọi field.

Muốn body được hiển thị trong một trang và schema được kiểm chứng, kết hợp **body snippet** với **field snippet** của cùng subsection như ví dụ. Khi trang tài liệu chỉ cần bảng field, có thể bỏ snippet body.

## 5. Những snippet được sinh và cách bố trí chúng

Giả sử output của REST Docs được cấu hình vào `build/generated-snippets` và dùng template Asciidoctor mặc định. Khi test chạy thành công, các tệp quan trọng sẽ nằm dưới `build/generated-snippets/orders-get/`:

| Tệp | Nguồn sinh | Vị trí dự kiến trong tài liệu |
| --- | --- | --- |
| `http-response.adoc` | HTTP exchange đã kiểm thử | Trang endpoint `GET /orders/{id}` |
| `response-fields.adoc` | `responseFields(...)` cấp gốc | Trang endpoint, bảng tổng quan |
| `response-fields-customer.adoc` | `responseFields(beneathPath("customer")...)` | Trang chi tiết khách hàng |
| `response-fields-delivery.adoc` | `responseFields(beneathPath("delivery")...)` | Trang chi tiết giao hàng |
| `response-fields-total.adoc` | `responseFields(beneathPath("total")...)` | Trang quy ước số tiền |
| `response-body-customer.adoc` | `responseBody(beneathPath("customer")...)` | Ví dụ payload của trang khách hàng |

**Chú ý:** `withSubsectionId("customer")` quyết định hậu tố tên snippet. Nếu không đặt ID, REST Docs sử dụng tên mặc định dựa trên `beneathPath` và path. Vì vậy, các lệnh `include` phải sử dụng tên file thực tế được sinh.

### 5.1. Trang endpoint chỉ chứa tổng quan

Ví dụ `src/docs/asciidoc/orders.adoc`:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Tra cứu đơn hàng theo mã định danh.

=== Response mẫu

include::{snippets}/orders-get/http-response.adoc[]

=== Các nhóm dữ liệu của response

include::{snippets}/orders-get/response-fields.adoc[]

Đọc chi tiết tại:

* <<customer-fields,Thông tin khách hàng>>
* <<delivery-fields,Thông tin giao hàng>>
* <<money-fields,Quy ước số tiền>>

include::fragments/customer-fields.adoc[]
include::fragments/delivery-fields.adoc[]
include::fragments/money-fields.adoc[]
```

Ở đây các fragment được nhúng **sau** bảng tổng quan để tạo một tài liệu Asciidoctor có nhiều mục. Nếu dự án dùng **nhiều trang HTML** riêng biệt, thay các tham chiếu anchor bằng liên kết `xref` phù hợp với cấu hình Asciidoctor/Antora của dự án. Đừng dùng liên kết anchor tới một trang chưa được nhúng.

### 5.2. Fragment khách hàng chứa bảng field riêng

`src/docs/asciidoc/fragments/customer-fields.adoc`:

```asciidoc
[[customer-fields]]
== Thông tin khách hàng

Nhánh customer chứa định danh và thông tin liên hệ
của khách hàng được gắn với đơn hàng.

=== Ví dụ JSON của customer

include::{snippets}/orders-get/response-body-customer.adoc[]

=== Các trường customer

include::{snippets}/orders-get/response-fields-customer.adoc[]
```

### 5.3. Fragment giao hàng và số tiền

`src/docs/asciidoc/fragments/delivery-fields.adoc`:

```asciidoc
[[delivery-fields]]
== Thông tin giao hàng

Các trường mô tả người nhận và địa chỉ của đơn hàng.

include::{snippets}/orders-get/response-fields-delivery.adoc[]
```

`src/docs/asciidoc/fragments/money-fields.adoc`:

```asciidoc
[[money-fields]]
== Quy ước số tiền

amount là số nguyên; currency là mã tiền tệ.
Ứng dụng phải quy định rõ đơn vị của amount trong contract.

include::{snippets}/orders-get/response-fields-total.adoc[]
```

**Kết quả:** bảng tổng quan có thể ngắn, còn người đọc vẫn tìm được bảng schema đầy đủ ở các phần khác. Tất cả snippet trong ví dụ này được sinh từ **một HTTP exchange đã kiểm thử**, giúp giảm nguy cơ các bảng được viết thủ công mâu thuẫn với nhau.

## 6. "Mô tả ở nơi khác" có nghĩa gì đối với strict validation?

Trong Spring REST Docs, `responseFields(...)` và `requestFields(...)` mặc định là **strict**: một field mới trong phạm vi snippet nhưng không được bao phủ bởi descriptor phù hợp sẽ khiến kiểm thử thất bại. Việc ghi "xem tài liệu khác" trong `description(...)` **không thay đổi** cơ chế này.

So sánh các tình huống khi API thay đổi:

| Thay đổi trong response | Bảng tổng quan | Bảng chi tiết liên quan |
| --- | --- | --- |
| Thêm `createdAt` ở cấp gốc | Có thể fail: chưa có descriptor cho root field mới | Các bảng subsection không nhìn thấy field root này |
| Thêm `customer.vipLevel` | Có thể vẫn pass: `customer` đã được bao phủ | Bảng `customer` strict có thể fail vì thiếu descriptor `vipLevel` |
| Thêm `delivery.address.street` | Có thể vẫn pass: `delivery` đã được bao phủ | Bảng `delivery` strict có thể fail vì thiếu `address.street` |
| Bỏ `total.currency` | Bảng tổng quan có thể vẫn pass nếu `total` còn tồn tại | Bảng `total` có thể fail do field `currency` bắt buộc bị thiếu |
| Bỏ toàn bộ `customer` | Bảng tổng quan có thể fail vì subsection `customer` bắt buộc | Extractor `beneathPath("customer")` không còn phần dữ liệu để trích như kỳ vọng |

Mỗi bảng chi tiết có phạm vi riêng; đó là lý do nên dùng **tài liệu tổng quan + bảng strict của các nhánh quan trọng** khi API cần đảm bảo schema.

### Không có liên kết kiểm tra tự động giữa các trang

Spring REST Docs không phân tích trang Asciidoctor để xác nhận rằng mọi hàng trong bảng tổng quan có liên kết hợp lệ tới tài liệu chi tiết. Nó cũng không buộc `customer-fields.adoc` phải tồn tại chỉ vì descriptor `customer` ghi "xem mục khách hàng".

Vì vậy, pipeline build cần vừa chạy test sinh snippet, vừa biên soạn tài liệu để phát hiện `include` thiếu file. Có thể bổ sung bước kiểm tra liên kết, anchor hoặc tài liệu xuất ra trong CI nếu dự án có nhiều trang.

### Nếu chưa có tài liệu chi tiết thì sao?

Nếu chỉ khai báo `subsectionWithPath("customer")` ở root mà chưa viết bảng `customer`, test strict cấp gốc vẫn có thể pass. Tài liệu chỉ mới đầy đủ ở mức **tổng quan**, chưa tự chứng minh được contract của từng field khách hàng.

Nếu nhóm thực sự dự định đưa phần chi tiết vào một trang khác, hãy tạo snippet chi tiết và đường dẫn tham chiếu trong cùng quy trình xuất bản. Nếu toàn bộ schema đã được tài liệu hóa ở module khác, vẫn nên có test xác nhận endpoint hiện tại tuân thủ schema đó, đặc biệt khi dữ liệu có thể biến đổi theo endpoint.

## 7. Khi nào chọn relaxedResponseFields hoặc ignored?

Có ba phương án thường bị nhầm khi tài liệu chỉ bàn về một phần response.

### 7.1. Dùng subsectionWithPath khi biết phạm vi của phần còn lại

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái"),
    subsectionWithPath("customer")
        .description("Xem mục Thông tin khách hàng"),
    subsectionWithPath("delivery")
        .description("Xem mục Thông tin giao hàng"),
    subsectionWithPath("total")
        .description("Xem mục Quy ước số tiền")
)
```

Đây là phương án phù hợp với cấu trúc ví dụ: các nhóm còn lại được **đặt tên rõ ràng**. Một field mới ngoài những nhóm này vẫn có thể khiến test strict thất bại.

### 7.2. Dùng relaxedResponseFields khi chỉ muốn chọn vài field, chưa kiểm soát phần còn lại

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    fieldWithPath("status")
        .description("Trạng thái")
)
```

`relaxedResponseFields(...)` không bắt buộc mọi field xuất hiện phải được document. Các field còn lại bị bỏ qua trong phép kiểm tra tính đầy đủ, kể cả một field root mới. Descriptor đã khai báo vẫn cần phù hợp với payload theo những ràng buộc của chúng.

Phương án này phù hợp với trang chỉ giới thiệu một vài field và chủ ý không đặt yêu cầu kiểm tra đầy đủ ở trang đó. **Nó không tự bảo đảm** rằng các field bị bỏ qua thật sự được mô tả tại trang khác. Nếu muốn phân chia tài liệu thành các subsection có tên, phương án ở `7.1` rõ ràng và kiểm chứng tốt hơn.

Tương tự, `relaxedRequestFields(...)` áp dụng cho request payload khi tài liệu chỉ mô tả chọn lọc một số field.

### 7.3. Dùng ignored cho field không cần xuất hiện trong bảng

```java
responseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    fieldWithPath("status")
        .description("Trạng thái"),
    fieldWithPath("internalFlag")
        .ignored(),
    subsectionWithPath("customer")
        .description("Xem mục Thông tin khách hàng"),
    subsectionWithPath("delivery")
        .description("Xem mục Thông tin giao hàng"),
    subsectionWithPath("total")
        .description("Xem mục Quy ước số tiền")
)
```

Ví dụ này giả định payload thực tế có `internalFlag`, một field kỹ thuật đã biết. `ignored()` cho biết field đó được xử lý trong phép kiểm tra tài liệu nhưng không hiện ở bảng. Chỉ dùng khi chủ ý không công bố field; nếu field là thành phần hợp đồng công khai đã được mô tả ở trang khác, `subsectionWithPath(...)` kèm liên kết thường thể hiện ý định tốt hơn.

### Bảng chọn phương án

| Nhu cầu thực tế | API ưu tiên | Điều cần lưu ý |
| --- | --- | --- |
| Nêu tên một object con và dẫn tới tài liệu chi tiết | `subsectionWithPath("object")` | Bảng cấp gốc không kiểm tra chi tiết nội bộ object |
| Sinh bảng kiểm chứng riêng cho object | `responseFields(beneathPath("object"), ...)` | Dùng path tương đối và ID subsection riêng |
| Chỉ muốn JSON minh họa của object | `responseBody(beneathPath("object"))` | Body snippet không tự kiểm tra mọi field |
| Tài liệu chỉ chọn vài field, chấp nhận field khác không được liệt kê | `relaxedResponseFields(...)` | Có thể bỏ sót field root mới |
| Cố ý loại một field đã biết khỏi bảng | `ignored()` | Không đồng nghĩa với mô tả schema ở nơi khác |

## 8. Trường hợp phần request được mô tả ở trang khác

Cách phân chia tương tự có thể áp dụng cho request của `POST /orders`:

```json
{
  "customerId": "cus-8",
  "delivery": {
    "recipient": "Lan Nguyen",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "payment": {
    "method": "CARD",
    "token": "tok_example_only"
  }
}
```

Trang tạo đơn hàng muốn tập trung vào mã khách hàng và chỉ nêu ngắn gọn hai khối được giải thích ở phần khác:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng; xem mục Giao hàng"),
    subsectionWithPath("payment")
        .description("Thông tin thanh toán; xem mục Thanh toán")
)
```

Trang giao hàng có thể nhúng bảng field riêng sinh từ handler:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Người nhận"),
    fieldWithPath("address.city")
        .description("Thành phố"),
    fieldWithPath("address.country")
        .description("Mã quốc gia")
)
```

Trong bài kiểm thử MockMvc của endpoint POST, các handler này được truyền vào cùng `document("orders-create", ...)` và snippet có tên `request-fields.adoc`, `request-fields-delivery.adoc`. Dữ liệu request được đưa vào qua `.contentType(MediaType.APPLICATION_JSON).content(requestJson)`, sau đó kiểm tra HTTP status trước `.andDo(document(...))`.

**Lưu ý:** snippet request chi tiết cần dữ liệu fixture có nhánh cần trích. Nếu một nhánh optional vắng mặt ở một trường hợp sử dụng, hãy sinh tài liệu chi tiết từ ca kiểm thử có nhánh đó và viết ca kiểm thử hành vi riêng cho request không có nhánh.

Không nên dùng giá trị token thanh toán thật trong fixture hoặc snippet xuất bản. Dữ liệu ví dụ trong bài chỉ là dữ liệu giả.

## 9. WebTestClient và REST Assured dùng cùng nguyên tắc

`PayloadDocumentation` cung cấp `fieldWithPath`, `subsectionWithPath`, `beneathPath` và các handler payload cho cả ba lựa chọn HTTP testing. Khác biệt chính nằm ở cách gắn lời gọi `document(...)`.

**WebTestClient:** giả sử `webTestClient` đã cấu hình Spring REST Docs và `document` được static import từ `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-120")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái"),
            subsectionWithPath("customer").description("Xem mục Khách hàng"),
            subsectionWithPath("delivery").description("Xem mục Giao hàng"),
            subsectionWithPath("total").description("Xem mục Số tiền")
        ),
        responseFields(
            beneathPath("customer").withSubsectionId("customer"),
            fieldWithPath("id").description("Mã khách hàng"),
            fieldWithPath("name").description("Tên"),
            fieldWithPath("contact.email").description("Email")
        )
    ));
```

**REST Assured:** giả sử `spec` là `RequestSpecification` đã thiết lập bộ lọc REST Docs và `document` được static import từ `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái"),
            subsectionWithPath("customer").description("Xem mục Khách hàng"),
            subsectionWithPath("delivery").description("Xem mục Giao hàng"),
            subsectionWithPath("total").description("Xem mục Số tiền")
        )
    ))
    .when()
    .get("/orders/ord-120")
    .then()
    .statusCode(200);
```

Các đoạn trên là ví dụ về **handler tài liệu**, chưa bao gồm toàn bộ bước tạo test client/request specification. Dữ liệu nguồn của snippet vẫn là HTTP exchange đã chạy, giúp cập nhật tài liệu cùng với kiểm thử.

## 10. Tích hợp Asciidoctor/Markdown vào Gradle và CI

Sau khi test đã sinh snippet, quá trình dựng tài liệu phải chạy **sau** bước test. Ví dụ với Gradle Groovy DSL, giả định dự án đã áp dụng plugin Asciidoctor và có dependency Spring REST Docs:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Có thể chạy:

```bash
./gradlew clean test asciidoctor
```

Cấu hình này liên kết quá trình kiểm thử với bước biên soạn tài liệu. Nếu một test thất bại vì thiếu descriptor trong bảng chi tiết, bước build tài liệu phụ thuộc test sẽ bị chặn. Nếu trang Asciidoctor `include` tệp snippet chưa được sinh, bước biên soạn phải báo lỗi để nhóm cập nhật identifier hoặc đường dẫn.

Một số quy tắc vận hành:

1. **Tạo snippet từ test có fixture ổn định.** Tránh dựa vào dữ liệu động hoặc tài khoản thật để mẫu JSON thay đổi ngoài ý muốn.
2. **Đặt subsection ID có ý nghĩa.** Ví dụ `customer`, `delivery`, `total` để giữ tên file dễ đọc và tiện tham chiếu.
3. **Dựng tài liệu từ snippet vừa được sinh.** Chạy clean build hoặc kiểm soát dọn các snippet cũ, nhằm hạn chế trường hợp tài liệu vẫn tham chiếu file cũ từ một lần chạy trước.
4. **Kiểm tra liên kết giữa các trang.** Với Asciidoctor, liên kết anchor chỉ có ý nghĩa nếu mục tiêu thực sự có trong tài liệu kết xuất; với nhiều trang dùng cấu hình liên kết phù hợp.
5. **Tránh mô tả trùng tay.** Khi một object được giải thích ở mục riêng, dùng `include` tới snippet, tránh chép lại bảng field ở nhiều trang.
6. **Làm rõ hợp đồng dùng chung.** Nếu `customer` xuất hiện ở nhiều endpoint, phải xác nhận dữ liệu và ràng buộc giống nhau; dùng một tài liệu tham chiếu không thay thế các test xác nhận hành vi của từng endpoint.

Trong dự án Maven, thư mục snippet thông dụng là `target/generated-snippets`. Dù dùng Maven hay Gradle, điều kiện quan trọng là việc chạy test, sinh snippet và dựng tài liệu phải dùng thống nhất đường dẫn đầu ra.

Khi tạo tài liệu Markdown, cần chọn template/snippet và cách ghép file phù hợp với pipeline Markdown. Các ví dụ `include::{snippets}/...[]` trong bài sử dụng Asciidoctor.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bảng tổng quan pass khi `customer` có thêm field mới | `subsectionWithPath("customer")` bao phủ các hậu duệ trong snippet tổng quan | Kiểm tra bảng strict riêng cho `customer` để phát hiện thay đổi |
| Test báo field mới `createdAt` chưa document | Field thêm ở cấp root, ngoài những subsection được mô tả | Bổ sung descriptor cấp root nếu contract cho phép |
| Bảng chi tiết báo thiếu `customer.name` | Đã chọn `beneathPath("customer")` nhưng vẫn viết path có tiền tố `customer.` | Trong bảng chi tiết viết `name` |
| Không tìm thấy `response-fields-customer.adoc` | Không dùng handler `responseFields(beneathPath(...))` hoặc subsection ID khác | Kiểm tra code handler, tên file và thư mục snippets |
| Trang ghi "xem mục Khách hàng" nhưng link không hoạt động | Mục tiêu không được nhúng hoặc anchor sai | Kiểm tra `include::fragments/customer-fields.adoc[]` và ID `[[customer-fields]]` |
| Test pass dù nhiều field chưa document | Dùng `relaxedResponseFields(...)` cho trang mà nhóm mong muốn strict | Dùng subsection descriptor ở đúng nhánh hoặc bổ sung bảng chi tiết strict |
| Tài liệu có bảng field cũ | Build sử dụng snippet từ lần chạy trước | Làm sạch output phù hợp, chạy lại test và dựng tài liệu |
| Subsection vắng mặt ở một biến thể response | Fixture không có nhánh nhưng handler dùng `beneathPath(...)` | Sinh snippet chi tiết ở test có nhánh; viết test khác cho biến thể không có nhánh |
| Nhiều trang lặp lời mô tả và trở nên mâu thuẫn | Sao chép bảng field thủ công | Sử dụng fragment hoặc snippet tham chiếu chung, xác nhận contract tương đương |

## 12. Bài thực hành

Hãy mở rộng `OrderSplitDocumentationTest` với các bài tập:

1. **Phát hiện field mới ở root.** Thêm `createdAt` vào response. Xác minh bảng tổng quan strict báo chưa document; thêm descriptor thích hợp rồi chạy lại.
2. **Phát hiện field mới trong subsection.** Thêm `customer.vipLevel`. So sánh kết quả bảng tổng quan với bảng chi tiết `customer`. Bổ sung descriptor `vipLevel` vào bảng riêng, rồi cập nhật nội dung trang khách hàng.
3. **Chia trang thật.** Tạo `orders.adoc`, `fragments/customer-fields.adoc`, `fragments/delivery-fields.adoc` và `fragments/money-fields.adoc` theo ví dụ. Kiểm tra các anchor dẫn từ bảng tổng quan đến mục chi tiết trong HTML.
4. **So sánh strict và relaxed.** Tạm thay bảng tổng quan bằng `relaxedResponseFields(...)` chỉ có `id` và `status`. Thêm một field root mới, xem test còn phát hiện được thay đổi đó không; sau đó khôi phục phương án có subsection descriptor.
5. **Áp dụng cho request.** Viết test `POST /orders`, sinh `request-fields.adoc` cấp gốc và `request-fields-delivery.adoc` cho nhánh `delivery`. Đối chiếu các path tương đối với JSON gốc.
6. **Build/CI.** Chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình. Cố tình đổi tên một snippet trong `include` để kiểm tra pipeline có phát hiện tài liệu thiếu snippet không.

**Tiêu chí hoàn thành:** bạn giải thích được vì sao mô tả một phần payload ở trang khác không đồng nghĩa với việc bỏ kiểm tra schema, biết đặt `subsectionWithPath` ở bảng tổng quan và `beneathPath` ở bảng chi tiết, đồng thời tạo được các đường dẫn `include` nhất quán.

## 13. Câu hỏi tự kiểm tra

**Câu 1. Nếu `customer` được mô tả ở trang khác, chỉ cần gọi `relaxedResponseFields(...)` là đủ?**

Chưa chắc. `relaxedResponseFields` cho phép các field chưa liệt kê tồn tại mà không báo lỗi về tính đầy đủ. Nếu muốn bảng tổng quan vẫn strict với các field còn lại, dùng `subsectionWithPath("customer")` và các descriptor cần thiết. Để thực sự kiểm tra schema `customer`, tạo snippet chi tiết hoặc test phù hợp.

**Câu 2. `subsectionWithPath("customer")` có sinh `response-fields-customer.adoc`?**

Không. Nó tạo một hàng của bảng field hiện tại và bao phủ nhánh con đối với phép kiểm tra của bảng đó. Snippet chi tiết có thể được sinh bằng `responseFields(beneathPath("customer").withSubsectionId("customer"), ...)`.

**Câu 3. Bảng tổng quan pass, vậy bảng `customer` chắc chắn pass?**

Không. Mỗi bảng có phạm vi và descriptor riêng. Bảng tổng quan có thể cho phép field mới nằm dưới `customer`, nhưng bảng chi tiết strict có thể phát hiện field đó chưa được document.

**Câu 4. Việc dùng lệnh `include` có đảm bảo toàn bộ schema được kiểm chứng?**

Không. `include` là bước ghép tài liệu. Việc kiểm chứng xuất phát từ test HTTP và các snippet handler. Phải chắc chắn snippet chứa các descriptor đầy đủ ở phạm vi cần kiểm tra.

**Câu 5. Khi một subsection là optional hoặc vắng mặt thì sao?**

Có thể dùng `optional()` trên descriptor phù hợp với contract để cho phép field vắng mặt. Tuy nhiên `beneathPath(...)` cần phần dữ liệu thực tế để sinh snippet chi tiết, nên dùng ca kiểm thử có subsection cho tài liệu và ca kiểm thử khác cho biến thể không có subsection.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): mô tả field, document subsection, strict/relaxed field documentation và trích một phần payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): tích hợp MockMvc, WebTestClient, REST Assured, snippets, Asciidoctor và quy trình build.

