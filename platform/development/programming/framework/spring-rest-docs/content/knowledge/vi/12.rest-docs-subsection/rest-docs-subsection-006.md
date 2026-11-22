# Phân biệt subsection với field documentation trong Spring REST Docs

## 1. Bối cảnh và mục tiêu

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng dựa trên bài kiểm thử HTTP thực tế bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Khi bài kiểm thử thành công, công cụ sinh các snippet cho request, response, payload, header và tham số. Các snippet sau đó được nhúng vào tài liệu Asciidoctor/Markdown và xây dựng cùng ứng dụng trong build, CI.

Bài này thuộc chương **Subsection**, trả lời câu hỏi quan trọng: **Khi nào cần document từng field, khi nào nên document cả một subsection và khi nào phải trích subsection thành snippet riêng?**

Ba khái niệm thường bị nhầm với nhau:

1. **Field documentation:** dùng `fieldWithPath(...)` trong `requestFields(...)` hoặc `responseFields(...)` để mô tả một đường dẫn cụ thể của JSON.
2. **Subsection documentation:** dùng `subsectionWithPath(...)` để mô tả một nhánh JSON gồm object hoặc array và xem các field hậu duệ của nhánh đó là đã document trong bảng field hiện tại.
3. **Subsection extraction:** dùng `beneathPath(...)` để chọn một phần payload, sau đó kết hợp với `requestFields(...)`, `responseFields(...)`, `requestBody(...)` hoặc `responseBody(...)` nhằm tạo snippet riêng.

Sau bài học, bạn sẽ biết chọn cách viết descriptor tương ứng với độ sâu tài liệu mong muốn, hiểu ranh giới kiểm tra strict, đặt path đúng khi tài liệu được trích riêng và quyết định khi nào cần bổ sung kiểm thử hợp đồng API.

## 2. Ví dụ chung: một response có nhiều tầng dữ liệu

Giả sử API `GET /orders/ord-314` trả JSON:

```json
{
  "orderId": "ord-314",
  "state": "READY",
  "customer": {
    "id": "cus-10",
    "displayName": "An Pham",
    "contact": {
      "email": "an@example.test",
      "phone": "+84900000000"
    }
  },
  "items": [
    {
      "sku": "BK-101",
      "quantity": 2,
      "pricing": {
        "unitAmount": 50000,
        "currency": "VND"
      }
    },
    {
      "sku": "PN-002",
      "quantity": 1,
      "pricing": {
        "unitAmount": 10000,
        "currency": "VND"
      }
    }
  ],
  "total": {
    "amount": 110000,
    "currency": "VND"
  }
}
```

Các field nằm trên nhiều cấp:

```text
response
├── orderId
├── state
├── customer
│   ├── id
│   ├── displayName
│   └── contact
│       ├── email
│       └── phone
├── items[] 
│   ├── sku
│   ├── quantity
│   └── pricing
│       ├── unitAmount
│       └── currency
└── total
    ├── amount
    └── currency
```

Một trang tổng quan endpoint có thể chỉ cần nêu năm thành phần chính. Trong khi đó, người tích hợp API cần biết `customer.contact.email`, `items[].sku` hoặc `items[].pricing.unitAmount` có ý nghĩa gì. Hai nhu cầu này dẫn tới **hai độ sâu document khác nhau**.

## 3. Bảng so sánh các API cốt lõi

| Công cụ | Định nghĩa | Kiểm tra những gì? | Khi nào nên dùng? |
| --- | --- | --- | --- |
| `fieldWithPath("orderId")` | Descriptor của một field tại đường dẫn cụ thể | Sự có mặt của field được mô tả (trừ khi optional), cùng nguyên tắc strict đối với field khác trong snippet | Field lá cần được giải thích rõ |
| `fieldWithPath("customer.contact.email")` | Descriptor field nằm sâu trong object | Đường dẫn cụ thể tới email; không chủ ý bỏ qua toàn bộ các field anh em | Tài liệu schema chi tiết |
| `subsectionWithPath("customer")` | Descriptor cho toàn bộ nhánh `customer` | Nhánh tồn tại (trừ khi optional); các hậu duệ được xem là đã document **trong snippet đó** | Bảng tổng quan ngắn gọn; phần chi tiết sẽ mô tả ở nơi khác |
| `subsectionWithPath("items[].pricing")` | Descriptor cho object `pricing` của các phần tử trong mảng | Bao phủ các field hậu duệ của nhánh `pricing` | Mô tả một object lặp lại ở mức tổng quan |
| `beneathPath("customer")` | Bộ trích xuất một phần payload | Chọn subtree; bản thân không là descriptor field | Sinh snippet body hoặc bảng field riêng của `customer` |
| `responseFields(...)` | Handler sinh bảng field response | Mặc định strict trong phạm vi payload được document | Tài liệu và kiểm chứng các field response |
| `requestFields(...)` | Handler sinh bảng field request | Mặc định strict trong phạm vi payload được document | Tài liệu và kiểm chứng các field request |

**Điểm phân biệt chính:** `fieldWithPath` và `subsectionWithPath` đều tạo **field descriptor** được đặt bên trong `requestFields`/`responseFields`; còn `beneathPath` **không mô tả field nào**. Nó chỉ xác định phần payload mà một snippet khác xử lý.

### 3.1. Field documentation: nêu cụ thể hợp đồng dữ liệu

Ví dụ muốn mô tả chi tiết những field quan trọng:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Mã đơn hàng"),
    fieldWithPath("state")
        .description("Trạng thái xử lý"),
    fieldWithPath("customer.id")
        .description("Mã khách hàng"),
    fieldWithPath("customer.displayName")
        .description("Tên hiển thị của khách hàng"),
    fieldWithPath("customer.contact.email")
        .description("Email liên hệ"),
    fieldWithPath("customer.contact.phone")
        .description("Số điện thoại liên hệ"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng của từng dòng hàng"),
    fieldWithPath("items[].pricing.unitAmount")
        .description("Đơn giá của mỗi sản phẩm"),
    fieldWithPath("items[].pricing.currency")
        .description("Đơn vị tiền tệ của đơn giá"),
    fieldWithPath("total.amount")
        .description("Tổng tiền của đơn hàng"),
    fieldWithPath("total.currency")
        .description("Đơn vị tiền tệ của tổng tiền")
)
```

Bảng có nhiều hàng, phù hợp khi **trang này là nguồn tài liệu schema chi tiết**. Path `items[].sku` chọn field `sku` trong các phần tử của mảng `items`; path `items[0].sku` chỉ nói tới phần tử đầu tiên nên không thích hợp để mô tả danh sách có độ dài thay đổi.

Trong bảng strict, nếu response bổ sung `customer.loyaltyTier` hoặc `items[].discount` mà chưa có descriptor phù hợp, test có thể thất bại. Đây là hành vi hữu ích khi cần phát hiện thay đổi schema ngoài dự kiến.

### 3.2. Subsection documentation: trình bày ý nghĩa cả nhóm

Trang tổng quan chỉ cần năm hàng:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Mã đơn hàng"),
    fieldWithPath("state")
        .description("Trạng thái xử lý"),
    subsectionWithPath("customer")
        .description("Thông tin khách hàng; xem tài liệu khách hàng"),
    subsectionWithPath("items")
        .description("Danh sách các dòng hàng"),
    subsectionWithPath("total")
        .description("Tổng giá trị đơn hàng")
)
```

Trong bảng này, `subsectionWithPath("customer")` coi `customer.id`, `customer.displayName`, `customer.contact.email` và các hậu duệ khác là đã được document. `subsectionWithPath("items")` tương tự cho mọi field bên trong danh sách item. Do đó, đoạn tổng quan có thể hợp lệ dù response bổ sung một field con trong `customer` hoặc `items`.

Nhưng nếu response bổ sung `createdAt` ở **root**, bảng tổng quan strict sẽ không coi `createdAt` thuộc `customer`, `items` hay `total`; test có thể thất bại cho tới khi thêm descriptor hoặc quyết định xử lý rõ ràng.

`subsectionWithPath(...)` phù hợp khi mô tả cả nhánh như một **khái niệm nghiệp vụ**, nhưng không thay thế một tài liệu schema con nếu client cần biết từng field.

### 3.3. Subsection extraction: tạo snippet riêng cho một nhánh

Nếu muốn một bảng độc lập cho `customer`:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer-details"),
    fieldWithPath("id")
        .description("Mã khách hàng"),
    fieldWithPath("displayName")
        .description("Tên hiển thị"),
    fieldWithPath("contact.email")
        .description("Email liên hệ"),
    fieldWithPath("contact.phone")
        .optional()
        .description("Số điện thoại liên hệ, nếu có")
)
```

Ở đây `beneathPath("customer")` trích nhánh `customer` làm phạm vi kiểm tra cho một snippet riêng. Các field descriptor phía sau dùng đường dẫn **tương đối với nhánh đã trích**: `id`, `displayName`, `contact.email`, `contact.phone`. Viết `customer.contact.email` trong bảng đã trích `customer` sẽ tìm sai vị trí.

Nếu muốn thêm một ví dụ JSON của riêng nhánh:

```java
responseBody(
    beneathPath("customer").withSubsectionId("customer-details")
)
```

Snippet body mô tả JSON trong nhánh `customer`, trong khi bảng `responseFields(beneathPath(...), ...)` mô tả các field của nhánh. **Snippet body không tự kiểm tra tính đầy đủ của field**; để bảo vệ schema, giữ bảng field strict hoặc các assertion phù hợp.

## 4. Ví dụ hoàn chỉnh với MockMvc

Ví dụ dùng **JUnit 5**, **Java 17+**, **MockMvc**, **Spring MVC** và **Spring REST Docs**. Controller mẫu trả JSON cố định để tập trung vào cơ chế document. Dự án thật cần thay controller mẫu bằng controller đã cấu hình và các fixture kiểm thử của ứng dụng.

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
class OrderPayloadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrdersController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOverviewAndCustomerDetails() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "ord-314")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-10"))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.total.amount").value(110000))
                .andDo(document("orders-get",

                        // (1) Bảng tổng quan: mô tả toàn bộ các nhóm dữ liệu.
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("state")
                                        .description("Trạng thái xử lý"),
                                subsectionWithPath("customer")
                                        .description("Thông tin khách hàng"),
                                subsectionWithPath("items")
                                        .description("Các dòng hàng"),
                                subsectionWithPath("total")
                                        .description("Tổng giá trị đơn hàng")
                        ),

                        // (2) Bảng chi tiết của nhánh customer.
                        responseFields(
                                beneathPath("customer")
                                        .withSubsectionId("customer-details"),
                                fieldWithPath("id")
                                        .description("Mã khách hàng"),
                                fieldWithPath("displayName")
                                        .description("Tên hiển thị"),
                                fieldWithPath("contact.email")
                                        .description("Email liên hệ"),
                                fieldWithPath("contact.phone")
                                        .optional()
                                        .description("Số điện thoại, nếu có")
                        ),

                        // (3) Đoạn JSON riêng của nhánh customer.
                        responseBody(
                                beneathPath("customer")
                                        .withSubsectionId("customer-details")
                        )
                ));
    }

    @RestController
    public static class SampleOrdersController {

        @GetMapping(value = "/orders/{orderId}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(
                @PathVariable("orderId") String orderId) {

            if (!"ord-314".equals(orderId)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "orderId": "ord-314",
                      "state": "READY",
                      "customer": {
                        "id": "cus-10",
                        "displayName": "An Pham",
                        "contact": {
                          "email": "an@example.test",
                          "phone": "+84900000000"
                        }
                      },
                      "items": [
                        {
                          "sku": "BK-101",
                          "quantity": 2,
                          "pricing": {
                            "unitAmount": 50000,
                            "currency": "VND"
                          }
                        },
                        {
                          "sku": "PN-002",
                          "quantity": 1,
                          "pricing": {
                            "unitAmount": 10000,
                            "currency": "VND"
                          }
                        }
                      ],
                      "total": {
                        "amount": 110000,
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

### 4.1. Những việc từng thành phần đảm nhận

**`status().isOk()` và `jsonPath(...)`:** các assertion đảm bảo endpoint trả HTTP status và một số giá trị nghiệp vụ kỳ vọng. Chúng cần thiết vì tài liệu field không tự kiểm chứng việc tính tổng tiền, trạng thái đơn hàng hay quy tắc số lượng item.

**`responseFields(...)` tổng quan:** tạo bảng ngắn gọn về các field/nhánh cấp gốc. `subsectionWithPath("customer")`, `subsectionWithPath("items")` và `subsectionWithPath("total")` cho phép mỗi nhánh chiếm một hàng.

**`responseFields(beneathPath("customer"), ...)`:** tạo bảng khác cho các field con. Bảng này có phạm vi strict độc lập; việc bảng tổng quan đã bao phủ `customer` không làm bảng chi tiết bỏ qua field mới.

**`responseBody(beneathPath("customer"))`:** tạo đoạn body riêng để đưa vào trang chi tiết khách hàng. Nó không thay thế bảng schema.

### 4.2. Vì sao có thể có hai bảng field trong một test?

Mỗi lời gọi `responseFields(...)` sinh một snippet riêng. Bảng tổng quan có tên mặc định `response-fields.adoc`, còn bảng trích với `withSubsectionId("customer-details")` có tên `response-fields-customer-details.adoc`. Hai snippet dùng chung một response thực tế nhưng có **độ sâu và phạm vi kiểm tra khác nhau**.

Nếu muốn mô tả chi tiết `items`, có thể tạo test/snippet khác với descriptor `items[].sku`, `items[].quantity` và `items[].pricing.unitAmount`. Tránh khai báo hai handler cùng tên snippet mặc định trong cùng identifier: mỗi tài liệu cần tên đầu ra riêng để dễ kiểm soát.

## 5. Cùng một thay đổi, kết quả kiểm tra có thể khác nhau

Giả sử test ở mục 4 chạy với các biến thể response:

| Biến thể | Bảng tổng quan | Bảng chi tiết `customer` | Lý do |
| --- | --- | --- | --- |
| Thêm `customer.loyaltyTier` | Có thể vẫn pass | Fail trong strict mode nếu chưa khai báo `loyaltyTier` | Subsection ở bảng tổng quan bao phủ field con; bảng chi tiết có descriptor riêng |
| Thêm `customer.contact.social` | Có thể vẫn pass | Fail nếu chưa khai báo `contact.social` | Field mới thuộc phạm vi kiểm tra của bảng chi tiết |
| Thêm `items[0].discount` | Có thể vẫn pass | Không liên quan | `items` được bao phủ ở tổng quan; bảng chi tiết đang chọn `customer` |
| Thêm `createdAt` tại root | Fail nếu chưa có descriptor | Không liên quan | Field mới nằm ngoài các subsection đã khai báo |
| Bỏ `customer.displayName` | Bảng tổng quan có thể vẫn pass nếu `customer` còn | Fail vì `displayName` bắt buộc | Bảng chi tiết kiểm tra field cụ thể |
| Bỏ `customer.contact.phone` | Bảng tổng quan có thể vẫn pass | Pass vì descriptor có `optional()` | Theo contract, field phone có thể không hiện diện |
| Bỏ toàn bộ `customer` | Bảng tổng quan fail khi `customer` là bắt buộc | Không thể trích subsection để sinh bảng chi tiết như kỳ vọng | Path extractor cần dữ liệu nhánh tương ứng |

**Tính strict phụ thuộc phạm vi và descriptor của từng snippet.** Không nên hiểu "test đã pass khi document subsection" là mọi field bên trong subsection đã được kiểm chứng đầy đủ.

### Nếu phần còn lại đã được mô tả ở tài liệu khác?

Tình huống này rất phổ biến. Ở trang `GET /orders/{orderId}`, chỉ cần bảng tổng quan ghi `customer` và dẫn tới mục "Schema khách hàng". Trong mục riêng, dùng snippet chi tiết được sinh bằng `responseFields(beneathPath("customer"), ...)`. Cả hai snippet có thể được sinh từ cùng test, giúp tài liệu ngắn và giảm lặp lại.

Dòng mô tả "xem Schema khách hàng" không tự động làm cho REST Docs kiểm tra tài liệu đích tồn tại. Cần nhúng hoặc liên kết đúng trong Asciidoctor/Markdown và cấu hình build báo lỗi khi thiếu snippet.

## 6. Cẩn thận với object, array và path tương đối

### 6.1. Object lồng nhau

Ở response gốc:

- `customer`: đường dẫn của object khách hàng.
- `customer.contact`: đường dẫn object liên hệ.
- `customer.contact.email`: đường dẫn field email.

Trong bảng root, `subsectionWithPath("customer.contact")` chỉ bao phủ nhánh `contact`. Nếu vẫn muốn bảng strict cấp gốc, những field khác như `customer.id` và `customer.displayName` cần descriptor phù hợp.

Khi dùng `beneathPath("customer")`, những đường dẫn field tương ứng là `id`, `displayName` và `contact.email`. Nếu dùng `beneathPath("customer.contact")`, chúng trở thành `email` và `phone`.

### 6.2. Mảng có phần tử object

Path quan trọng:

| Cấu trúc | Path từ root |
| --- | --- |
| Toàn bộ danh sách dòng hàng | `items` |
| Mã sản phẩm của các item | `items[].sku` |
| Số lượng của các item | `items[].quantity` |
| Object định giá trong mỗi item | `items[].pricing` |
| Đơn giá của các item | `items[].pricing.unitAmount` |

Ví dụ bảng chọn lọc từ root:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Mã đơn hàng"),
    fieldWithPath("state")
        .description("Trạng thái"),
    subsectionWithPath("customer")
        .description("Thông tin khách hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng"),
    subsectionWithPath("items[].pricing")
        .description("Thông tin giá của từng item"),
    subsectionWithPath("total")
        .description("Tổng giá trị")
)
```

Đây là một cấu hình khác với `subsectionWithPath("items")`: bảng có thể phát hiện một field mới như `items[].note` chưa được document, trong khi vẫn cố ý gom nhóm dữ liệu `pricing`.

**Trường hợp mảng rỗng:** `items: []` có key `items` nhưng không chứa field `items[].sku`. Nếu snippet bắt buộc field trong mỗi phần tử, test dùng mảng rỗng không phù hợp để sinh bảng chi tiết đó. Hãy sinh tài liệu chi tiết từ fixture có phần tử và có test riêng xác minh phản hồi với mảng rỗng.

### 6.3. Path cho key đặc biệt

Ký hiệu dấu chấm bình thường ngăn các cấp object. Nếu key JSON thật chứa dấu chấm, chẳng hạn `"contact.email"` nằm nguyên trong object, cần path với bracket notation tương ứng như `['contact.email']` thay vì coi dấu chấm là phép tách cấp. Luôn so đường dẫn descriptor với JSON thực nhận trong test.

## 7. Tùy chọn, bỏ qua field và tài liệu relaxed

### 7.1. optional()

Khi một field thực sự không bắt buộc theo contract:

```java
fieldWithPath("contact.phone")
    .optional()
    .description("Số điện thoại, nếu có")
```

Trong bảng đã trích `customer`, path tương đối là `contact.phone`. `optional()` cho phép field này vắng mặt; nó không miễn trừ kiểm tra các field khác và không có nghĩa JSON có thể tùy ý sai kiểu hoặc thiếu các ràng buộc nghiệp vụ.

Nếu **cả subsection `customer`** có thể vắng mặt, descriptor ở bảng tổng quan có thể dùng `subsectionWithPath("customer").optional()`. Khi sinh bảng chi tiết với `beneathPath("customer")`, hãy chọn test có nhánh đó hiện diện; test cho biến thể không có `customer` phải được tổ chức riêng.

### 7.2. ignored()

`ignored()` cho phép khai báo một field được biết đến nhưng chủ ý **không đưa vào bảng tài liệu**:

```java
fieldWithPath("internalTraceCode")
    .ignored()
```

Nó hữu ích khi payload fixture có field kỹ thuật mà tài liệu công khai không cần giải thích. Tuy nhiên, không dùng `ignored()` chỉ để che lỗi thiếu descriptor ngoài ý muốn. Việc bỏ qua field cần được quyết định dựa trên hợp đồng API.

### 7.3. relaxedResponseFields và relaxedRequestFields

Nếu mục tiêu chỉ là giới thiệu một vài field mà không yêu cầu mô tả toàn bộ payload, có thể dùng:

```java
relaxedResponseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    fieldWithPath("state").description("Trạng thái")
)
```

`relaxedResponseFields(...)` cho phép các field chưa có descriptor tồn tại mà không làm thất bại **phép kiểm tra tính đầy đủ** của snippet. Vì vậy, field mới `createdAt` ở root có thể không bị phát hiện bởi bảng này. Các field bắt buộc đã khai báo vẫn được kiểm tra theo descriptor.

So sánh:

| Nhu cầu | Cách ưu tiên | Hạn chế cần biết |
| --- | --- | --- |
| Muốn document tất cả field quan trọng ở trang hiện tại | `responseFields(fieldWithPath(...), ...)` strict | Bảng có thể dài với JSON lồng sâu |
| Muốn document nhóm dữ liệu, các field con có tài liệu riêng | `responseFields(subsectionWithPath(...), ...)` strict | Bảng tổng quan không kiểm tra chi tiết field con |
| Chỉ chọn một phần field; chấp nhận các field còn lại không được liệt kê | `relaxedResponseFields(...)` | Có thể bỏ sót thay đổi field ngoài phạm vi được khai báo |
| Cố ý loại một field cụ thể đã biết khỏi bảng | `ignored()` trên descriptor | Không thay thế việc quyết định schema cần công bố |

Quy tắc này áp dụng tương tự cho `requestFields(...)` và `relaxedRequestFields(...)` khi document request payload.

## 8. Đối chiếu với request field documentation

Ví dụ endpoint `POST /orders` nhận request:

```json
{
  "customerId": "cus-10",
  "items": [
    {
      "sku": "BK-101",
      "quantity": 2
    }
  ],
  "delivery": {
    "recipient": "An Pham",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  }
}
```

Bảng **tổng quan request**:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Khách hàng đặt mua"),
    subsectionWithPath("items")
        .description("Các dòng hàng"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng")
)
```

Bảng **chi tiết request** cho nhánh `delivery`:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Tên người nhận"),
    fieldWithPath("address.city")
        .description("Thành phố"),
    fieldWithPath("address.country")
        .description("Mã quốc gia")
)
```

Để tạo test bằng MockMvc, gửi request với `.contentType(MediaType.APPLICATION_JSON).content(requestJson)`, kiểm tra status trước khi gọi `.andDo(document("orders-create", ...))`. Khi test thành công, có thể sinh `request-fields.adoc` và `request-fields-delivery.adoc` dưới cùng identifier.

**Khác biệt giữa request và response không nằm ở subsection:** cách khai báo descriptor vẫn giống nhau, nhưng request documentation kiểm tra payload client gửi, còn response documentation kiểm tra payload server trả.

## 9. Sinh snippet và ghép vào tài liệu Asciidoctor

Với test `documentOverviewAndCustomerDetails` ở mục 4, output thường đặt tại `build/generated-snippets/orders-get/` trong dự án Gradle đã cấu hình Spring REST Docs:

| Snippet | Được sinh bởi | Vai trò |
| --- | --- | --- |
| `http-response.adoc` | Snippet HTTP response mặc định | Hiển thị response đầy đủ đã kiểm thử |
| `response-body.adoc` | Snippet response body mặc định | Hiển thị JSON response đầy đủ |
| `response-fields.adoc` | `responseFields(...)` cấp root | Bảng tổng quan có `customer`, `items`, `total` |
| `response-fields-customer-details.adoc` | `responseFields(beneathPath("customer").withSubsectionId("customer-details"), ...)` | Bảng chi tiết field của `customer` |
| `response-body-customer-details.adoc` | `responseBody(beneathPath("customer").withSubsectionId("customer-details"))` | JSON được trích riêng từ `customer` |

Các snippet mặc định và đường dẫn cụ thể phụ thuộc vào cấu hình của dự án. Các hậu tố `customer-details` trong bảng trên do `withSubsectionId(...)` quyết định.

Ví dụ `src/docs/asciidoc/orders.adoc`:

```asciidoc
= Order API
:toc: left

== GET /orders/{orderId}

Tra cứu đơn hàng với danh sách sản phẩm và thông tin khách hàng.

=== HTTP response

include::{snippets}/orders-get/http-response.adoc[]

=== Các nhóm dữ liệu của response

include::{snippets}/orders-get/response-fields.adoc[]

=== JSON của customer

include::{snippets}/orders-get/response-body-customer-details.adoc[]

=== Các trường của customer

include::{snippets}/orders-get/response-fields-customer-details.adoc[]
```

Lời gọi `include::{snippets}/...[]` thuộc Asciidoctor; thuộc tính `snippets` phải trỏ đúng thư mục REST Docs đã sinh. Nếu phần chi tiết được đặt ở một tài liệu khác, có thể chuyển hai lệnh `include` cho `customer` sang fragment/trang khách hàng và dùng liên kết từ trang endpoint. Việc tách trang không làm thay đổi dữ liệu đầu vào của snippet.

## 10. Tích hợp vào Gradle và CI

Với dự án đã áp dụng plugin Asciidoctor, JUnit và dependency `spring-restdocs-mockmvc`, ví dụ Gradle (Groovy DSL) có thể ràng buộc bước sinh tài liệu với bước chạy test:

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

Dự án cần cấu hình REST Docs ghi snippet vào `snippetsDir` tương ứng, và Asciidoctor dùng đúng thuộc tính `snippets`. Khi đó trong CI có thể chạy:

```bash
./gradlew clean test asciidoctor
```

Nếu field mới phá vỡ bảng strict, test sẽ thất bại và bước dựng tài liệu phụ thuộc test không thể hoàn thành như một build thành công. Một `include` trỏ sai file snippet cũng cần được coi là lỗi tài liệu trong pipeline. Với Maven, đường dẫn sinh snippet thường là `target/generated-snippets`; nguyên tắc phụ thuộc kiểm thử vẫn giữ nguyên.

Nếu dự án dùng Markdown làm đầu ra, hãy chọn template/snippet và bước lắp ghép Markdown tương ứng. Các ví dụ `include::[]` trong bài dành cho Asciidoctor.

## 11. Dùng với WebTestClient hoặc REST Assured

Các API document payload trong `PayloadDocumentation` có thể tái sử dụng giữa ba phương án kiểm thử; khác biệt chính là chỗ gắn handler `document(...)` vào HTTP exchange.

### WebTestClient

Giả sử `webTestClient` đã được cấu hình với Spring REST Docs và `document` là static import từ `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-314")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        responseFields(
            fieldWithPath("orderId").description("Mã đơn hàng"),
            fieldWithPath("state").description("Trạng thái"),
            subsectionWithPath("customer").description("Khách hàng"),
            subsectionWithPath("items").description("Dòng hàng"),
            subsectionWithPath("total").description("Tổng tiền")
        ),
        responseFields(
            beneathPath("customer").withSubsectionId("customer-details"),
            fieldWithPath("id").description("Mã khách hàng"),
            fieldWithPath("displayName").description("Tên hiển thị"),
            fieldWithPath("contact.email").description("Email"),
            fieldWithPath("contact.phone").optional()
                .description("Điện thoại nếu có")
        )
    ));
```

### REST Assured

Giả sử `spec` là `RequestSpecification` đã thiết lập bộ lọc REST Docs và `document` là static import từ `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseFields(
            fieldWithPath("orderId").description("Mã đơn hàng"),
            fieldWithPath("state").description("Trạng thái"),
            subsectionWithPath("customer").description("Khách hàng"),
            subsectionWithPath("items").description("Dòng hàng"),
            subsectionWithPath("total").description("Tổng tiền")
        )
    ))
    .when()
    .get("/orders/ord-314")
    .then()
    .statusCode(200);
```

Hai đoạn này minh họa vị trí gắn documentation handler; trước khi chạy, mỗi dự án cần cấu hình client/filter, server hoặc controller test tương ứng. Khả năng tạo bảng field tổng quan và chi tiết không phụ thuộc vào cách gửi HTTP request.

## 12. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Bảng `response-fields.adoc` quá dài | Mô tả mọi field lồng nhau ngay trong một bảng tổng quan | Dùng `subsectionWithPath` ở các nhánh lớn và tạo bảng chi tiết riêng khi cần |
| Thêm `customer.vipLevel` nhưng bảng tổng quan vẫn pass | `subsectionWithPath("customer")` bao phủ hậu duệ trong bảng tổng quan | Dùng bảng strict `responseFields(beneathPath("customer"), ...)` để phát hiện field mới |
| Thêm `createdAt` ở root làm test fail | Field mới không thuộc subsection đã document | Thêm descriptor nếu field thuộc contract |
| Bảng chi tiết tìm không thấy `customer.contact.email` | Đã trích `customer` nhưng vẫn ghi path tính từ root | Dùng `contact.email` |
| Snippet riêng cho `customer` không tồn tại | Chỉ gọi `subsectionWithPath("customer")` | Thêm `responseFields(beneathPath("customer")...)` hoặc `responseBody(beneathPath("customer"))` |
| Test dùng mảng rỗng bị lỗi khi document `items[].sku` | Không có phần tử chứa field `sku` | Sinh bảng chi tiết từ fixture có item; kiểm tra mảng rỗng ở ca khác |
| Tài liệu vẫn pass khi response có nhiều field mới | Dùng `relaxedResponseFields(...)` mà không có kiểm tra khác | Dùng strict và descriptor cho ranh giới subsection rõ ràng |
| Asciidoctor không tìm thấy file `response-fields-customer-details.adoc` | Sai subsection ID, identifier hoặc thư mục snippet | So tên file đã sinh với các lệnh `include` |
| Test có giá trị đúng nhưng schema không đúng | Chỉ dùng assertion trên vài field và bỏ qua mô tả schema | Kết hợp assertion nghiệp vụ với field documentation strict |

## 13. Bài thực hành

Thực hiện theo trình tự để kiểm tra hiểu biết về **phạm vi** của mỗi kỹ thuật:

1. **Tạo bảng đầy đủ:** thay các descriptor `subsectionWithPath("customer")`, `subsectionWithPath("items")`, `subsectionWithPath("total")` bằng các `fieldWithPath(...)` chi tiết. Quan sát số hàng của `response-fields.adoc`.
2. **Tạo bảng tóm tắt:** khôi phục bảng tổng quan và giữ bảng chi tiết `customer`. Xác minh cả `response-fields.adoc` lẫn `response-fields-customer-details.adoc` được sinh.
3. **Thêm field vào subsection:** thêm `customer.loyaltyTier` vào JSON. Quan sát vì sao bảng tổng quan vẫn có thể hợp lệ nhưng bảng chi tiết strict thất bại. Thêm descriptor chi tiết mới.
4. **Thêm field ở root:** thêm `createdAt` vào JSON. Xác minh bảng tổng quan strict phát hiện field không nằm trong subsection hiện có.
5. **Đổi phạm vi extractor:** thay `beneathPath("customer")` bằng `beneathPath("customer.contact")`, đổi các descriptor chi tiết thành `email` và `phone`, cập nhật subsection ID và các lệnh `include`.
6. **Kiểm tra biến thể:** thử response không có `customer.contact.phone` với descriptor `optional()`, rồi thử bỏ `optional()`. Viết test khác cho trường hợp toàn bộ `customer` vắng mặt nếu hợp đồng cho phép.
7. **Biên soạn tài liệu:** chạy `./gradlew clean test asciidoctor` sau khi cấu hình dự án, rồi kiểm tra HTML để đối chiếu bảng tổng quan, JSON trích và bảng chi tiết.

**Tiêu chí hoàn thành:** bạn phân biệt rõ ý nghĩa của `fieldWithPath`, `subsectionWithPath`, `beneathPath`; giải thích vì sao các bảng strict ở những phạm vi khác nhau có thể cho kết quả khác nhau; và tạo được tài liệu API vừa dễ đọc vừa có kiểm thử bảo vệ schema quan trọng.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): quy tắc document field, subsection, path JSON và tính đầy đủ của request/response payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): tích hợp MockMvc, WebTestClient, REST Assured, snippet và biên soạn tài liệu trong build.

