# Tái sử dụng subsection trong nhiều operation với Spring REST Docs

## 1. Khi nào cần tái sử dụng subsection?

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Mỗi test thực thi một HTTP exchange và sinh snippet mô tả request, response, payload, header hoặc tham số. Các snippet được biên soạn thành tài liệu Asciidoctor/Markdown và đưa vào quy trình build, CI.

Trong một API, cùng một cấu trúc dữ liệu thường xuất hiện ở nhiều operation. Chẳng hạn object `customer` có thể xuất hiện trong:

- `GET /orders/{id}`: thông tin khách hàng của đơn hàng;
- `GET /invoices/{id}`: thông tin khách hàng được ghi trên hóa đơn;
- `POST /orders`: thông tin khách hàng gửi trong request tạo đơn;
- `PATCH /customers/{id}`: một phần thông tin khách hàng được cập nhật.

Nếu các operation thực sự dùng chung schema, việc viết lại các descriptor cho mỗi test gây lặp, khó đồng bộ và dễ bỏ sót khi contract thay đổi. Ta có thể tách phần mô tả field thành helper dùng lại.

Bài học tập trung vào:

- tái sử dụng descriptor của một subsection giữa nhiều operation;
- tạo mới descriptor bằng helper/factory để tránh chia sẻ trạng thái không cần thiết;
- phân biệt schema dùng chung với path extractor và operation identifier riêng;
- dùng chung cấu trúc cho request hoặc response khi contract tương ứng giống nhau;
- tổ chức snippet theo operation mà vẫn duy trì kiểm chứng strict;
- nhận diện trường hợp không nên tái sử dụng vì schema hoặc ý nghĩa nghiệp vụ đã khác.

**Nguyên tắc nền tảng:** tái sử dụng phần mô tả schema khi contract giống nhau; vẫn khai báo riêng path, operation và phần diễn giải theo ngữ cảnh endpoint.

## 2. Ví dụ: object customer xuất hiện ở nhiều operation

Giả sử các API có cấu trúc khách hàng giống nhau:

```json
{
  "id": "cus-42",
  "displayName": "Ha Nguyen",
  "contact": {
    "email": "ha@example.test",
    "phone": "0900000000"
  }
}
```

Trong response đơn hàng, object nằm ở `customer`. Trong response hóa đơn cũng nằm ở `customer`, còn trong một operation khác có thể nằm ở `buyer` hoặc `accountHolder`.

Một bảng field chi tiết cho object customer có thể mô tả:

| Path tương đối trong object | Ý nghĩa |
| --- | --- |
| `id` | Mã khách hàng |
| `displayName` | Tên hiển thị |
| `contact.email` | Email liên hệ |
| `contact.phone` | Số điện thoại liên hệ |

Nếu tất cả operation cùng cam kết schema này, có thể dùng một factory để tạo bộ descriptor chung. Mỗi test vẫn chọn subsection bằng path riêng:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    customerFields()
)
```

Đối với hóa đơn, cùng schema nhưng vẫn dùng operation identifier riêng:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    customerFields()
)
```

Hai lời gọi giống nhau về fragment, nhưng đặt trong `document("orders-get", ...)` và `document("invoices-get", ...)` khác nhau. Snippet được ghi vào thư mục riêng của từng operation; tên file có thể giống nhau mà không đè lên nhau.

## 3. Phân tách ba thành phần để tái sử dụng

Khi thiết kế helper, cần phân biệt:

| Thành phần | Ví dụ | Có thể dùng chung? |
| --- | --- | --- |
| Schema field của fragment | `id`, `displayName`, `contact.email` | Có, nếu contract và ý nghĩa field giống nhau |
| Path trong payload gốc | `customer`, `buyer`, `accountHolder` | Không mặc định; khai báo theo từng operation |
| Operation identifier | `orders-get`, `invoices-get` | Mỗi bộ snippet cần identifier phù hợp với operation/kịch bản |
| Subsection ID | `customer`, `buyer` | Có thể đặt giống nhau ở hai operation khác thư mục; trong cùng operation cần tránh trùng loại snippet |
| Đoạn mô tả nghiệp vụ | "Khách hàng đặt đơn", "Người mua trên hóa đơn" | Thường cần riêng theo ngữ cảnh, ngay cả khi schema trùng |

Việc tách này giúp helper chỉ làm một nhiệm vụ: mô tả schema con. Nó không nên quyết định endpoint nào đang được document, path nào đang trỏ đến fragment hoặc người đọc cần hiểu fragment theo nghiệp vụ nào.

### 3.1. Đường dẫn tương đối và beneathPath

Một helper chứa các path tương đối với gốc fragment:

```java
fieldWithPath("id")
fieldWithPath("displayName")
fieldWithPath("contact.email")
fieldWithPath("contact.phone")
```

Khi trích `customer`, dùng:

```java
beneathPath("customer")
```

Khi trích `buyer`, dùng:

```java
beneathPath("buyer")
```

Không đưa `customer.` vào helper nếu muốn dùng nó cho nhiều path khác nhau. Nếu path được viết tuyệt đối trong helper, sẽ không thể áp dụng cùng helper cho `buyer`.

### 3.2. Operation identifier và subsection ID

`document("orders-get", ...)` xác định thư mục snippet của operation. `withSubsectionId("customer")` đặt hậu tố cho snippet subsection trong thư mục đó. Hai operation khác nhau có thể cùng sinh `response-fields-customer.adoc` mà không đè nhau:

```text
build/generated-snippets/
├── orders-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
└── invoices-get/
    ├── response-fields.adoc
    └── response-fields-customer.adoc
```

Nhưng trong **cùng một operation**, hai handler cùng loại dùng subsection ID `customer` sẽ nhắm tới cùng một tên file. Nếu chúng mô tả hai nội dung khác nhau, hãy đặt ID riêng có ý nghĩa, ví dụ `billing-customer` và `shipping-customer`.

## 4. Xây dựng helper tạo descriptor dùng chung

Một cách đơn giản là viết factory trả về mảng `FieldDescriptor`:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

final class CustomerDocumentation {

    private CustomerDocumentation() {
    }

    static FieldDescriptor[] customerFields() {
        return new FieldDescriptor[] {
            fieldWithPath("id")
                .description("Mã khách hàng"),
            fieldWithPath("displayName")
                .description("Tên hiển thị"),
            fieldWithPath("contact.email")
                .description("Địa chỉ email liên hệ"),
            fieldWithPath("contact.phone")
                .optional()
                .description("Số điện thoại liên hệ, nếu có")
        };
    }
}
```

Factory tạo **descriptor mới cho mỗi lần gọi**. Cách này làm rõ rằng mỗi snippet có thể thiết lập mô tả, optional hoặc type theo nhu cầu mà không phụ thuộc một mảng descriptor đã được dùng trong test khác.

Không nên gom tất cả operation identifier, path extractor và heading tài liệu vào class helper này. Hãy giữ helper tập trung vào schema field dùng chung.

### 4.1. Sử dụng trong operation GET orders

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng"),
        fieldWithPath("status")
            .description("Trạng thái đơn hàng"),
        subsectionWithPath("customer")
            .description("Khách hàng gắn với đơn hàng"),
        subsectionWithPath("total")
            .description("Tổng giá trị đơn hàng")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        CustomerDocumentation.customerFields()
    )
));
```

### 4.2. Sử dụng trong operation GET invoices

```java
.andDo(document("invoices-get",
    responseFields(
        fieldWithPath("id")
            .description("Mã hóa đơn"),
        fieldWithPath("number")
            .description("Số hóa đơn"),
        subsectionWithPath("customer")
            .description("Khách hàng được ghi trên hóa đơn"),
        subsectionWithPath("amount")
            .description("Tổng tiền hóa đơn")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        CustomerDocumentation.customerFields()
    )
));
```

Hai operation sử dụng cùng factory, nhưng Description ở bảng cha vẫn tùy ngữ cảnh: một bên là khách hàng gắn với đơn hàng, bên kia là khách hàng được ghi trên hóa đơn. Đây là cách giữ phần schema nhất quán nhưng nội dung tài liệu vẫn chính xác với operation.

## 5. Ví dụ MockMvc đầy đủ với hai operation

Ví dụ sau minh họa một test class dùng hai endpoint và cùng helper. Yêu cầu: Java 17+, JUnit 5, Spring MVC Test và `spring-restdocs-mockmvc` trong test classpath.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SharedCustomerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderCustomer() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-901")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-42"))
                .andDo(document("orders-get",
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng"),
                                fieldWithPath("status").description("Trạng thái đơn hàng"),
                                subsectionWithPath("customer")
                                        .description("Khách hàng gắn với đơn hàng")
                        ),
                        responseFields(
                                beneathPath("customer").withSubsectionId("customer"),
                                customerFields()
                        )
                ));
    }

    @Test
    void documentInvoiceCustomer() throws Exception {
        mockMvc.perform(get("/invoices/{id}", "inv-901")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-42"))
                .andDo(document("invoices-get",
                        responseFields(
                                fieldWithPath("id").description("Mã hóa đơn"),
                                fieldWithPath("number").description("Số hóa đơn"),
                                subsectionWithPath("customer")
                                        .description("Khách hàng được ghi trên hóa đơn")
                        ),
                        responseFields(
                                beneathPath("customer").withSubsectionId("customer"),
                                customerFields()
                        )
                ));
    }

    private static FieldDescriptor[] customerFields() {
        return new FieldDescriptor[] {
            fieldWithPath("id").description("Mã khách hàng"),
            fieldWithPath("displayName").description("Tên hiển thị"),
            fieldWithPath("contact.email").description("Email liên hệ"),
            fieldWithPath("contact.phone").optional()
                    .description("Số điện thoại nếu có")
        };
    }

    @RestController
    static class SampleController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> order(@PathVariable("id") String id) {
            if (!"ord-901".equals(id)) {
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {
                          "id": "ord-901",
                          "status": "PAID",
                          "customer": {
                            "id": "cus-42",
                            "displayName": "Ha Nguyen",
                            "contact": {
                              "email": "ha@example.test",
                              "phone": "0900000000"
                            }
                          }
                        }
                        """);
        }

        @GetMapping(value = "/invoices/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> invoice(@PathVariable("id") String id) {
            if (!"inv-901".equals(id)) {
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {
                          "id": "inv-901",
                          "number": "INV-901",
                          "customer": {
                            "id": "cus-42",
                            "displayName": "Ha Nguyen",
                            "contact": {
                              "email": "ha@example.test",
                              "phone": "0900000000"
                            }
                          }
                        }
                        """);
        }
    }
}
```

Trong ví dụ, helper `customerFields()` là method private của test class để minh họa vị trí tái sử dụng. Với dự án lớn, chuyển factory thành class riêng như `CustomerDocumentation` để nhiều test class cùng gọi. Hai operation sinh snippet trong hai thư mục khác nhau, nên cùng subsection ID `customer` không gây xung đột.

## 6. Khi path khác nhau nhưng schema giống nhau

Một cấu trúc khách hàng có thể được đặt ở path khác nhau trong từng response:

- `orders-get`: `customer`;
- `shipments-get`: `recipient.customer`;
- `invoices-get`: `buyer`.

Nếu schema của object cuối cùng giống nhau, factory vẫn có thể dùng lại. Chỉ extractor thay đổi:

```java
responseFields(
    beneathPath("recipient.customer")
        .withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

hoặc:

```java
responseFields(
    beneathPath("buyer")
        .withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

Helper chỉ chứa path tương đối của object. Không hardcode tiền tố path gốc vào từng descriptor. Cách này cho phép cùng bộ schema được tái dùng ở nhiều cấu trúc response.

Tuy nhiên, cần xác nhận object ở các path có **cùng contract**. Nếu `recipient.customer` không có `contact.phone` hoặc `buyer` có thêm `taxId` bắt buộc, việc dùng y nguyên factory có thể làm test strict thất bại. Đó là tín hiệu nên tách schema hoặc mô hình hóa một biến thể, thay vì tự động nới lỏng toàn bộ.

## 7. Tái sử dụng schema cho request và response

`PayloadDocumentation` dùng field descriptor trong cả `requestFields(...)` và `responseFields(...)`, nên cùng một cấu trúc object có thể được document trong request và response khi schema thực sự giống nhau.

Ví dụ `customer` trong request tạo đơn hàng:

```java
requestFields(
    beneathPath("customer").withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

Và trong response lấy đơn hàng:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

Cùng factory không có nghĩa mọi hệ thống nên dùng chung request/response schema. Có những contract khác nhau:

- Request có thể chỉ cần `id` và `displayName`, trong khi response trả cả `contact`.
- Request có thể chứa trường ghi chú được phép chỉnh sửa; response có trường audit do server tạo.
- Response có thể che thông tin nhạy cảm, còn request dùng token hoặc dữ liệu đầu vào khác.
- Một field read-only hoặc write-only cần được mô tả theo đúng hướng dữ liệu.

Trong trường hợp đó, tách rõ `customerRequestFields()` và `customerResponseFields()`. Có thể chia sẻ helper con nhỏ cho các field thực sự trùng, nhưng không nên ép cả hai thành một schema chung chỉ để giảm số dòng code.

## 8. Tái sử dụng mô tả nhưng vẫn giữ ngữ cảnh riêng

Dù descriptor field dùng chung, Description ở bảng cha có thể khác nhau tùy operation:

```java
// Orders
subsectionWithPath("customer")
    .description("Khách hàng sở hữu đơn hàng")

// Invoices
subsectionWithPath("customer")
    .description("Thông tin người mua được ghi trên hóa đơn")
```

Đây không phải mâu thuẫn nếu ý nghĩa của object trong hai contract khác nhau. Nếu hai Description thể hiện hai ngữ nghĩa khác nhau một cách đáng kể, cần xem lại liệu đó có thực sự là một schema nghiệp vụ dùng chung không.

Có thể tạo helper cho descriptor field và helper khác cho subsection ở một số trường hợp, nhưng không nên ẩn các câu văn theo ngữ cảnh vào một factory dùng chung làm người đọc không hiểu operation đang mô tả gì.

Một quy tắc hữu ích:

- **Field schema:** tái sử dụng khi tên, kiểu, optional và semantics của field giống nhau.
- **Extractor path:** khai báo tại từng operation.
- **Parent description:** viết theo vai trò của fragment trong endpoint đó.
- **Operation ID:** đặt riêng theo HTTP action/kịch bản.
- **Subsection ID:** dùng ổn định cho loại fragment, miễn không trùng tên snippet cùng loại trong một operation.

## 9. Khi nào không nên tái sử dụng?

Không nên dùng chung helper chỉ vì hai JSON có cùng tên object.

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Schema khác nhau | Một object có field bắt buộc mà object kia không có | Tách factory hoặc tạo factory theo biến thể rõ ràng |
| Semantics khác nhau | `status` trong customer là trạng thái tài khoản, ở nơi khác là trạng thái kiểm duyệt | Mô tả riêng; cân nhắc schema riêng |
| Request/response khác nhau | Một bên có field write-only, bên kia read-only | Tách request descriptors và response descriptors |
| Version API khác nhau | V1 không có `contact.phone`, V2 có field này | Duy trì contract theo version, tránh một helper làm mất khác biệt |
| Field optional khác nhau | Một operation bắt buộc phone, operation kia cho phép thiếu | Factory riêng hoặc cấu hình rõ ràng theo contract |
| Cấu trúc lồng nhau khác | Một object dùng `contact.email`, object kia dùng `emailAddress` | Tách mapping/descriptor, không ép chung path |

Nếu có hai phiên bản contract, có thể đặt helper theo phiên bản:

```java
customerV1Fields()
customerV2Fields()
```

Nếu khác biệt chỉ nằm ở một field optional nhưng semantics còn lại giống nhau, có thể tạo helper cơ sở và factory mở rộng. Tuy nhiên, ưu tiên cách thể hiện rõ contract hơn là tạo một bộ helper quá tổng quát và khó đọc.

## 10. Đặt tên snippet và tránh ghi đè

Operation identifier tạo thư mục snippet, còn subsection ID tạo hậu tố file. Ví dụ:

```text
build/generated-snippets/
├── orders-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
├── invoices-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
└── shipments-get/
    ├── response-fields.adoc
    └── response-fields-customer.adoc
```

Tên snippet có thể giống nhau giữa các thư mục operation. Nhưng trong cùng thư mục, hai bảng field cùng loại không được vô tình dùng trùng subsection ID:

```java
// Tránh: cả hai đều ghi response-fields-customer.adoc
responseFields(beneathPath("billingCustomer")
    .withSubsectionId("customer"), billingCustomerFields());

responseFields(beneathPath("shippingCustomer")
    .withSubsectionId("customer"), shippingCustomerFields());
```

Hãy dùng `billing-customer` và `shipping-customer` nếu hai bảng cần tồn tại đồng thời trong một operation.

Body và field có prefix khác nhau nên một body và một bảng field có thể cùng subsection ID, ví dụ `response-body-customer.adoc` và `response-fields-customer.adoc`.

## 11. Asciidoctor: tái sử dụng descriptor không đồng nghĩa tái sử dụng đường dẫn include

Mặc dù cùng factory sinh schema cho nhiều operation, mỗi operation có thư mục snippet riêng. Ví dụ:

```asciidoc
== GET /orders/{id}

include::{snippets}/orders-get/response-fields-customer.adoc[]

== GET /invoices/{id}

include::{snippets}/invoices-get/response-fields-customer.adoc[]
```

Có thể tạo một fragment Asciidoctor dùng chung nếu cả hai trang thực sự cần cùng một nội dung và cùng ngữ cảnh. Nhưng nếu mô tả ý nghĩa của customer khác theo từng operation, hãy dùng hai đoạn giải thích riêng và chỉ tái sử dụng phần bảng schema phù hợp.

Không viết đường dẫn include cố định chỉ theo subsection ID mà quên operation identifier. Tên file `response-fields-customer.adoc` không đủ để xác định snippet; cần cả thư mục operation.

## 12. Build và CI

Ví dụ cấu hình Gradle Groovy DSL, giả định đã áp dụng plugin Asciidoctor và cấu hình REST Docs ghi snippet vào `build/generated-snippets`:

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

Chạy:

```bash
./gradlew clean test asciidoctor
```

Trong CI:

1. Chạy tất cả test operation sử dụng schema dùng chung.
2. Đảm bảo fixture của mỗi operation phản ánh cùng contract mà helper mô tả.
3. Kiểm tra test strict phát hiện field mới chưa được document ở tất cả operation liên quan.
4. Xác nhận snippet sinh ra ở đúng thư mục operation và tên subsection ID.
5. Chạy Asciidoctor sau test để phát hiện `include` bị thiếu.
6. Review thay đổi factory khi contract dùng chung thay đổi; tránh một chỉnh sửa làm thay đổi tài liệu nhiều endpoint mà không được kiểm tra.

Tái sử dụng helper làm cho một thay đổi schema có thể ảnh hưởng tới nhiều operation. Đây là lợi ích khi contract thực sự chung, nhưng cũng có nghĩa CI cần chạy đầy đủ các test sử dụng helper. Với Maven, snippet thường được lưu trong `target/generated-snippets` và bước dựng tài liệu cần chạy sau test.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Helper không dùng được cho object ở path khác | Descriptor hardcode tiền tố `customer.` | Dùng path tương đối trong helper và chọn `beneathPath` bên ngoài |
| Test operation hóa đơn fail khi dùng helper customer | Schema hóa đơn không hoàn toàn giống customer ở order | Xác minh contract, tách helper hoặc mô tả biến thể |
| Hai operation ghi đè snippet | Dùng cùng thư mục operation identifier cho bộ tài liệu khác nhau | Đặt identifier riêng theo operation/kịch bản |
| Hai fragment trong một operation ghi cùng file | Subsection ID trùng cho hai snippet cùng loại | Đặt ID riêng theo vai trò |
| Request test fail vì descriptor response không khớp | Request và response có schema/optional khác nhau | Tách factory request và response |
| Bảng chi tiết không phát hiện field mới ở một operation | Test cho operation đó không chạy hoặc dùng relaxed | Chạy đủ test strict và kiểm tra pipeline |
| Mô tả fragment giống nhau nhưng ngữ cảnh sai | Dùng chung description cấp cha quá tổng quát | Viết description theo operation, chỉ chia sẻ field schema |
| Include không tìm thấy snippet | Thiếu operation folder hoặc sai subsection hậu tố | Kiểm tra identifier, ID và output thực tế |

## 14. Bài thực hành

Tạo một helper cho schema `customer` rồi sử dụng trong hai operation `orders-get` và `invoices-get`:

1. **Tạo factory:** viết `customerFields()` trả về descriptor cho `id`, `displayName`, `contact.email` và `contact.phone`.
2. **Dùng ở hai operation:** tạo test MockMvc cho `GET /orders/{id}` và `GET /invoices/{id}`; cả hai gọi factory nhưng dùng operation identifier riêng.
3. **Đổi path:** trong test thứ hai, giả lập object nằm ở `buyer`. Giữ helper dùng path tương đối và thay `beneathPath("customer")` thành `beneathPath("buyer")`.
4. **Thử schema drift:** thêm `customer.segment` chỉ vào response orders. Xác nhận test orders phát hiện field mới, còn test invoices không bị ảnh hưởng nếu response invoice không có thay đổi.
5. **Thử khác biệt optional:** cho phone bắt buộc trong một contract và optional trong contract khác. Quyết định có cần hai factory riêng không; giải thích theo semantics.
6. **Kiểm tra tên file:** mở hai thư mục operation trong `build/generated-snippets` và xác nhận chúng cùng có `response-fields-customer.adoc` nhưng không ghi đè nhau.
7. **Biên soạn:** include bảng customer từ cả hai operation vào tài liệu tương ứng và chạy `./gradlew clean test asciidoctor`.

**Tiêu chí hoàn thành:** bạn tái sử dụng được descriptor mà không hardcode path gốc, phân biệt được schema chung với ngữ cảnh operation riêng và có test chứng minh mọi operation sử dụng helper đều được cập nhật khi contract thay đổi.

## 15. Câu hỏi tự kiểm tra

**1. Có thể tái sử dụng cùng một bộ field descriptor cho nhiều operation không?**

Có, nếu schema, semantics, optional và kiểu dữ liệu thật sự giống nhau. Nên dùng factory tạo descriptor cho từng snippet.

**2. Path của subsection có nên đặt trong helper không?**

Không nên khi muốn tái sử dụng cho nhiều vị trí. Giữ path tương đối trong field descriptors, chọn path gốc bằng `beneathPath(...)` tại từng operation.

**3. Vì sao hai operation có thể dùng cùng subsection ID mà không trùng file?**

Vì chúng nằm trong hai operation directory khác nhau. Nhưng cùng một operation phải tránh hai snippet cùng loại có chung hậu tố.

**4. Có nên dùng chung request và response descriptors?**

Chỉ khi contract hai chiều thật sự giống nhau. Nếu có field read-only, write-only hoặc optional khác nhau, hãy tách bộ descriptor.

**5. Tái sử dụng helper có làm test strict tự động chạy cho mọi operation không?**

Không. Mọi test operation sử dụng helper vẫn phải được thực thi trong build/CI. Helper chỉ chia sẻ mã mô tả, không thay thế việc chạy test.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, subsection extraction và document request/response payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình MockMvc, WebTestClient, REST Assured, sinh snippet và tích hợp Asciidoctor/build.

