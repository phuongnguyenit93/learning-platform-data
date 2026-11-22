# Chỉ rõ ý nghĩa của fragment được tách riêng trong Spring REST Docs

## 1. Mục tiêu bài học

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP thực thi bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Test thành công sẽ sinh snippet về request, response, payload, header và tham số. Các snippet được biên soạn vào tài liệu Asciidoctor/Markdown và đưa vào build, CI.

Khi payload lớn có nhiều object lồng nhau, nhóm phát triển thường tách một nhánh thành *fragment* (subsection) để bảng tổng quan ngắn hơn. Nhưng một fragment chỉ có JSON hoặc bảng field vẫn chưa chắc đã giúp người đọc hiểu ý nghĩa của nó. Bài học này tập trung vào cách giải thích **fragment được tách riêng đại diện cho dữ liệu gì, có vai trò gì trong contract của endpoint và nên được đọc trong ngữ cảnh nào**.

Có ba lớp thông tin cần phối hợp:

1. **Mô tả ở bảng cha:** dùng `subsectionWithPath(...).description(...)` để giải thích vai trò của nhánh trong payload gốc.
2. **Diễn giải ở tài liệu con:** dùng heading và đoạn văn trước/sau snippet để trình bày ngữ cảnh, mục đích và quy tắc nghiệp vụ.
3. **Mô tả schema của fragment:** dùng `responseFields(beneathPath(...), ...)` hoặc `requestFields(beneathPath(...), ...)` để giải thích từng field con.

`withSubsectionId(...)` chỉ đặt định danh/hậu tố tên snippet. Nó không tự tạo mô tả nghiệp vụ. Tên file `response-fields-payment.adoc` cho biết snippet thuộc nhánh payment, nhưng không giải thích payment là kết quả xử lý tiền, yêu cầu thanh toán hay bản ghi đối soát.

Sau bài học, bạn có thể mô tả fragment nhất quán ở trang tổng quan và trang chi tiết, sinh snippet body/bảng field riêng, giải thích từng field trong ngữ cảnh nghiệp vụ và duy trì strict validation cho schema quan trọng.

## 2. Ví dụ: fragment thanh toán trong response đơn hàng

Giả sử endpoint `GET /orders/ord-520` trả response:

```json
{
  "id": "ord-520",
  "status": "PAID",
  "customer": {
    "id": "cus-27",
    "displayName": "Minh Tran"
  },
  "payment": {
    "method": "CARD",
    "status": "CAPTURED",
    "amount": {
      "value": 450000,
      "currency": "VND"
    },
    "card": {
      "brand": "VISA",
      "last4": "4242"
    },
    "capturedAt": "2026-10-20T08:30:00Z",
    "transactionReference": "txn-demo-520"
  },
  "delivery": {
    "state": "PROCESSING",
    "recipient": "Minh Tran"
  }
}
```

Nhánh `payment` biểu diễn **kết quả xử lý thanh toán gắn với đơn hàng**, gồm phương thức, trạng thái giao dịch, số tiền, thông tin thẻ đã rút gọn, thời điểm capture và mã tham chiếu giao dịch.

```text
GET /orders/{id}
├── id
├── status
├── customer
├── payment  ───────────────┐
└── delivery                │
                            ▼
                 Fragment "payment"
                 ├── method
                 ├── status
                 ├── amount
                 ├── card
                 ├── capturedAt
                 └── transactionReference
```

Tài liệu cần giữ được cả **vị trí của payment trong response gốc** và **ý nghĩa nghiệp vụ của payment**. Nếu chỉ có JSON, người đọc thấy cấu trúc nhưng chưa chắc hiểu cách diễn giải trạng thái và số tiền.

## 3. Lớp thứ nhất: mô tả ý nghĩa trong bảng cha

Trong tài liệu tổng quan endpoint, dùng `subsectionWithPath("payment")` với description có ý nghĩa:

```java
responseFields(
    fieldWithPath("id")
        .description("Mã định danh đơn hàng"),
    fieldWithPath("status")
        .description("Trạng thái tổng thể của đơn hàng"),
    subsectionWithPath("customer")
        .description("Định danh và tên hiển thị khách hàng của đơn hàng"),
    subsectionWithPath("payment")
        .description("Kết quả xử lý thanh toán của đơn hàng, gồm phương thức, trạng thái giao dịch, số tiền và tham chiếu giao dịch"),
    subsectionWithPath("delivery")
        .description("Trạng thái thực hiện giao hàng và người nhận")
)
```

Mô tả nên trả lời câu hỏi: **nhóm dữ liệu này có vai trò gì trong contract của endpoint?** Không nên chỉ lặp lại tên object.

| Mô tả yếu | Mô tả có ý nghĩa |
| --- | --- |
| `Thông tin payment` | Kết quả xử lý thanh toán gắn với đơn hàng, bao gồm phương thức, trạng thái và thông tin giao dịch |
| `Thông tin delivery` | Trạng thái thực hiện giao hàng và thông tin người nhận |
| `Thông tin customer` | Định danh và tên hiển thị của khách hàng đặt đơn |
| `Chi tiết amount` | Giá trị tiền đã được xử lý cùng đơn vị tiền tệ tương ứng |

`subsectionWithPath(...)` là field descriptor. Description của nó xuất hiện trong bảng field của payload gốc; nó không tạo bảng chi tiết hoặc body riêng.

## 4. Lớp thứ hai: diễn giải fragment trong tài liệu con

Khi tách `payment` bằng `beneathPath("payment")`, REST Docs có thể tạo snippet body và bảng field riêng. Nhưng nội dung snippet không tự biết payment là kết quả xử lý thanh toán, cũng không giải thích ý nghĩa capture hay mã tham chiếu.

Trang con nên có heading và đoạn văn do người viết biên soạn:

```asciidoc
== Kết quả xử lý thanh toán

Fragment payment mô tả kết quả xử lý khoản thanh toán gắn với đơn hàng.
Trường status phản ánh trạng thái của giao dịch thanh toán; amount là
giá trị tiền được xử lý và currency xác định đơn vị tiền. Nhánh card chỉ
hiển thị thương hiệu cùng bốn chữ số cuối để nhận diện phương thức thẻ.

=== Ví dụ JSON

include::{snippets}/orders-get/response-body-payment.adoc[]

=== Các trường của fragment payment

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Ba phần có vai trò khác nhau:

- Đoạn văn cung cấp ngữ cảnh nghiệp vụ.
- JSON cho thấy ví dụ dữ liệu cụ thể được trả về.
- Bảng field giải thích schema và từng thuộc tính.

Nếu chỉ nhúng bảng field, người đọc có thể biết payment có status và amount nhưng không hiểu đó là trạng thái thanh toán hay trạng thái đơn hàng. Heading và đoạn diễn giải giải quyết khoảng trống này.

### 4.1. Diễn giải chính xác, tránh suy diễn

Tên field không phải lúc nào cũng thể hiện đầy đủ contract. Trong ví dụ:

- `amount.value` là giá trị tiền của giao dịch.
- `amount.currency` là mã tiền tệ của giá trị đó.
- `card.last4` là bốn chữ số cuối được công bố để nhận diện thẻ.
- `transactionReference` là mã tham chiếu giao dịch.
- `capturedAt` là thời điểm giao dịch được capture theo contract.

Nếu hệ thống có quy tắc cụ thể về đơn vị tiền, múi giờ, nguồn sinh mã tham chiếu hoặc vòng đời capture, chỉ mô tả điều đã được xác định trong contract. Không suy ra quy tắc nghiệp vụ chỉ từ tên field.

## 5. Ví dụ hoàn chỉnh: MockMvc sinh snippet cho fragment

Ví dụ dùng **JUnit 5**, **Java 17+**, Spring MVC Test, MockMvc và Spring REST Docs. Controller mẫu trả JSON cố định để tập trung vào cách sinh tài liệu. Dự án thực tế nên dùng controller ứng dụng và fixture test ổn định.

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
class PaymentFragmentDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SamplePaymentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentPaymentMeaningAndFields() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-520")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.status").value("CAPTURED"))
                .andExpect(jsonPath("$.payment.amount.currency").value("VND"))
                .andExpect(jsonPath("$.payment.card.last4").value("4242"))
                .andDo(document("orders-get",
                        // Bảng cha: giải thích vai trò của các nhánh.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                subsectionWithPath("customer")
                                        .description("Định danh và tên hiển thị khách hàng"),
                                subsectionWithPath("payment")
                                        .description("Kết quả xử lý thanh toán gồm phương thức, trạng thái, số tiền và tham chiếu giao dịch"),
                                subsectionWithPath("delivery")
                                        .description("Trạng thái và người nhận giao hàng")
                        ),
                        // Bảng field chi tiết của riêng payment.
                        responseFields(
                                beneathPath("payment").withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Phương thức thanh toán"),
                                fieldWithPath("status")
                                        .description("Trạng thái giao dịch thanh toán"),
                                fieldWithPath("amount.value")
                                        .description("Giá trị tiền đã xử lý"),
                                fieldWithPath("amount.currency")
                                        .description("Mã đơn vị tiền tệ"),
                                fieldWithPath("card.brand")
                                        .description("Thương hiệu thẻ"),
                                fieldWithPath("card.last4")
                                        .description("Bốn chữ số cuối của thẻ"),
                                fieldWithPath("capturedAt")
                                        .description("Thời điểm giao dịch được capture"),
                                fieldWithPath("transactionReference")
                                        .description("Mã tham chiếu giao dịch")
                        ),
                        // Body snippet riêng cho payment.
                        responseBody(
                                beneathPath("payment").withSubsectionId("payment")
                        )
                ));
    }

    @RestController
    public static class SamplePaymentController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(@PathVariable("id") String id) {
            if (!"ord-520".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-520",
                      "status": "PAID",
                      "customer": {
                        "id": "cus-27",
                        "displayName": "Minh Tran"
                      },
                      "payment": {
                        "method": "CARD",
                        "status": "CAPTURED",
                        "amount": {
                          "value": 450000,
                          "currency": "VND"
                        },
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        },
                        "capturedAt": "2026-10-20T08:30:00Z",
                        "transactionReference": "txn-demo-520"
                      },
                      "delivery": {
                        "state": "PROCESSING",
                        "recipient": "Minh Tran"
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

### 5.1. Vai trò của từng handler

**Bảng cha:** `subsectionWithPath("payment").description(...)` giải thích payment có ý nghĩa gì trong response tổng thể. Bảng này mô tả nhánh như một đơn vị nghiệp vụ.

**Bảng chi tiết:** `responseFields(beneathPath("payment"), ...)` trích nhánh để tạo bảng riêng. Các path tính tương đối từ fragment, vì vậy viết `amount.value` thay cho `payment.amount.value`.

**Body riêng:** `responseBody(beneathPath("payment"))` tạo snippet JSON của nhánh. Snippet body không thay thế việc liệt kê field hoặc kiểm tra schema.

### 5.2. withSubsectionId là tên, không phải mô tả

Trong ví dụ, `withSubsectionId("payment")` đặt hậu tố tên snippet:

- `response-fields-payment.adoc`
- `response-body-payment.adoc`

ID này chỉ hỗ trợ định danh và tham chiếu. Đổi nó thành `payment-result` có thể đổi tên file, nhưng không tự thay đổi mô tả trong bảng hoặc nội dung giải thích nghiệp vụ. Muốn người đọc hiểu fragment, hãy viết Description và phần văn bản quanh snippet.

### 5.3. Mỗi snippet có phép kiểm chứng riêng

Bảng cha bao phủ nhánh `payment`; bảng đó có thể vẫn pass khi xuất hiện field con mới. Bảng chi tiết strict có descriptor riêng, nên có thể phát hiện field mới chưa được document.

Ví dụ, thêm `payment.providerCode`:

- Bảng tổng quan có thể vẫn hợp lệ vì `payment` đã được mô tả như một subsection.
- Bảng chi tiết có thể thất bại vì `providerCode` chưa có descriptor.
- Nếu field mới thuộc contract, hãy thêm descriptor, giải thích ý nghĩa và cập nhật tài liệu con.

Đây là khác biệt giữa **mô tả ý nghĩa nhóm dữ liệu** và **document schema của nhóm dữ liệu**.

## 6. Chọn nội dung theo người đọc

Một fragment có thể được đọc bởi người tích hợp API, người vận hành, nhóm đối soát hoặc nhóm phát triển giao diện. Không nên nhồi toàn bộ bối cảnh vào Description của từng field.

| Người đọc | Câu hỏi cần trả lời | Nơi nên giải thích |
| --- | --- | --- |
| Người đọc trang endpoint | Payment là nhóm dữ liệu gì trong response? | Description của `subsectionWithPath("payment")` ở bảng cha |
| Người tích hợp API | Field nào có và từng field mang nghĩa gì? | Bảng `responseFields(beneathPath("payment"), ...)` |
| Người cần ví dụ payload | Fragment thực tế có cấu trúc gì? | `responseBody(beneathPath("payment"))` và đoạn văn |
| Người cần quy tắc nghiệp vụ | Trạng thái thay đổi thế nào, số tiền được hiểu ra sao? | Tài liệu contract hoặc vòng đời nghiệp vụ được liên kết |
| Người tìm nội dung | Fragment nằm ở mục hoặc trang nào? | Heading, mục lục, anchor và liên kết |

### 6.1. Mẫu biên soạn cho một fragment

Một trang fragment có thể theo cấu trúc:

1. **Tên fragment:** tên nghiệp vụ dễ hiểu, ví dụ "Kết quả xử lý thanh toán".
2. **Vai trò:** fragment mô tả thông tin nào trong request/response.
3. **Vị trí:** path của fragment trong payload gốc.
4. **Ví dụ JSON:** snippet body được trích.
5. **Schema:** bảng field cùng mô tả.
6. **Quy tắc hoặc giới hạn:** đơn vị, trạng thái, tính optional, dữ liệu đã che hoặc điều kiện xuất hiện nếu contract quy định.
7. **Tham chiếu:** liên kết tới tài liệu trạng thái thanh toán, lỗi hoặc quy tắc nghiệp vụ được quản lý riêng.

Ví dụ đoạn giới thiệu:

> Fragment payment mô tả kết quả xử lý thanh toán gắn với đơn hàng. Nó bao gồm phương thức, trạng thái giao dịch, số tiền, thông tin thẻ đã rút gọn, thời điểm capture và mã tham chiếu. Các quy tắc chuyển trạng thái của giao dịch được trình bày ở tài liệu vòng đời thanh toán.

Chỉ ghi quy tắc đã được xác định trong contract hoặc logic thực tế; không suy luận rằng một trạng thái hoặc thời điểm có ý nghĩa cụ thể chỉ từ tên field.

## 7. Áp dụng cho fragment request

Cùng phương pháp áp dụng với request `POST /orders`:

```json
{
  "customerId": "cus-27",
  "delivery": {
    "recipient": "Minh Tran",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    },
    "instructions": "Gọi khi đến nơi"
  },
  "items": [
    {
      "sku": "BK-101",
      "quantity": 1
    }
  ]
}
```

Bảng request ở cấp cha có thể là:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng đặt đơn"),
    subsectionWithPath("delivery")
        .description("Thông tin tổ chức giao đơn gồm người nhận, địa chỉ và hướng dẫn giao hàng"),
    subsectionWithPath("items")
        .description("Danh sách sản phẩm được đặt mua")
)
```

Bảng riêng của fragment delivery:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Tên người nhận"),
    fieldWithPath("address.city")
        .description("Thành phố giao hàng"),
    fieldWithPath("address.country")
        .description("Mã quốc gia"),
    fieldWithPath("instructions")
        .optional()
        .description("Hướng dẫn bổ sung cho nhân viên giao hàng")
)
```

Trang chi tiết cần nói rõ `delivery` được dùng để tổ chức giao đơn, còn bảng field thể hiện cấu trúc dữ liệu. `instructions` được đánh dấu optional theo giả định của ví dụ; chỉ giữ cách đánh dấu này khi contract thực sự cho phép bỏ field.

Với MockMvc, gửi JSON bằng `.contentType(MediaType.APPLICATION_JSON).content(requestJson)` trước khi gọi `.andDo(document(...))`. Với WebTestClient, gắn document sau exchange; với REST Assured, gắn filter document vào request specification đã cấu hình.

## 8. Kết hợp snippet và văn bản trong Asciidoctor

Với identifier `orders-get` và subsection ID `payment`, một trang có thể được biên soạn như sau:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Truy vấn thông tin và trạng thái một đơn hàng.

=== HTTP response

include::{snippets}/orders-get/http-response.adoc[]

=== Các nhóm dữ liệu

include::{snippets}/orders-get/response-fields.adoc[]

=== Kết quả xử lý thanh toán

Fragment payment mô tả kết quả xử lý khoản thanh toán gắn với đơn hàng.
Trường status thuộc giao dịch thanh toán; amount chứa giá trị tiền đã
xử lý và currency xác định đơn vị tiền.

==== Ví dụ JSON

include::{snippets}/orders-get/response-body-payment.adoc[]

==== Các trường

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Đoạn văn giải thích là nội dung được viết trong file Asciidoctor. `response-body-payment.adoc` chỉ chứa fragment JSON đã trích; `response-fields-payment.adoc` chứa bảng field đã khai báo. Các snippet không tự bổ sung mô tả nghiệp vụ ở phần văn xuôi.

Nếu fragment được quản lý trong một tài liệu riêng, hãy đặt heading/đoạn giải thích ở trang đó rồi liên kết từ trang endpoint bằng anchor hoặc cơ chế xref của hệ thống xuất bản. Kiểm tra đích liên kết có thực sự được tạo trong tài liệu đầu ra.

## 9. Tạo snippet với WebTestClient và REST Assured

Các descriptor trong `PayloadDocumentation` dùng cùng nguyên tắc cho các công cụ kiểm thử; nơi gắn `document(...)` mới là khác nhau.

### WebTestClient

Giả sử `webTestClient` đã cấu hình Spring REST Docs và `document` được static import từ `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-520")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-payment",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn hàng"),
            subsectionWithPath("payment")
                .description("Kết quả xử lý thanh toán của đơn hàng"),
            subsectionWithPath("customer")
                .description("Thông tin khách hàng"),
            subsectionWithPath("delivery")
                .description("Thông tin giao hàng")
        ),
        responseFields(
            beneathPath("payment").withSubsectionId("payment"),
            fieldWithPath("method").description("Phương thức thanh toán"),
            fieldWithPath("status").description("Trạng thái giao dịch"),
            fieldWithPath("amount.value").description("Giá trị tiền"),
            fieldWithPath("amount.currency").description("Mã tiền tệ"),
            fieldWithPath("card.brand").description("Thương hiệu thẻ"),
            fieldWithPath("card.last4").description("Bốn số cuối thẻ"),
            fieldWithPath("capturedAt").description("Thời điểm capture"),
            fieldWithPath("transactionReference").description("Mã tham chiếu")
        ),
        responseBody(beneathPath("payment").withSubsectionId("payment"))
    ));
```

### REST Assured

Giả sử `spec` là `RequestSpecification` có filter REST Docs và `document` được static import từ `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-payment-restassured",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn"),
            subsectionWithPath("payment")
                .description("Kết quả xử lý thanh toán của đơn hàng"),
            subsectionWithPath("customer")
                .description("Thông tin khách hàng"),
            subsectionWithPath("delivery")
                .description("Thông tin giao hàng")
        )
    ))
    .when()
    .get("/orders/ord-520")
    .then()
    .statusCode(200);
```

Các đoạn trên minh họa handler tài liệu; chúng giả định client, server và filter đã được cấu hình. Body fragment có thể được thêm bằng `responseBody(beneathPath("payment"))` khi trang cần ví dụ JSON riêng.

## 10. Strict, optional và ý nghĩa phạm vi

### 10.1. Mỗi snippet có ranh giới kiểm tra riêng

| Thay đổi response | Bảng cha có `subsectionWithPath("payment")` | Bảng chi tiết payment strict |
| --- | --- | --- |
| Thêm `payment.providerCode` | Có thể vẫn pass | Fail nếu chưa có descriptor |
| Thêm `createdAt` tại root | Fail nếu chưa có descriptor | Không thuộc phạm vi payment |
| Xóa `payment.status` | Có thể vẫn pass nếu payment còn tồn tại | Fail nếu status là bắt buộc |
| Xóa `payment.card.last4` | Có thể vẫn pass | Fail nếu descriptor bắt buộc |
| Xóa toàn bộ `payment` | Fail nếu subsection bắt buộc | Không có dữ liệu để trích như kỳ vọng |

Bảng cha mô tả payment như một khối. Bảng chi tiết mô tả các field con. Vì thế, không thể kết luận schema fragment được kiểm chứng đầy đủ chỉ vì bảng cha pass.

### 10.2. optional()

Nếu field có thể vắng mặt theo contract:

```java
fieldWithPath("transactionReference")
    .optional()
    .description("Mã tham chiếu nếu giao dịch đã được tạo")
```

Nếu toàn bộ subsection có thể vắng mặt:

```java
subsectionWithPath("payment")
    .optional()
    .description("Thông tin thanh toán nếu đơn hàng đã khởi tạo giao dịch")
```

`optional()` cho phép field được mô tả vắng mặt trong ca test. Nhưng `beneathPath("payment")` cần nhánh có dữ liệu để tạo snippet. Vì thế, dùng test có payment để sinh tài liệu chi tiết và test riêng cho biến thể không có payment.

### 10.3. ignored() và relaxedResponseFields()

`ignored()` dành cho field đã biết nhưng chủ ý không hiển thị trong bảng. Không sử dụng nó để che một field công khai chưa được giải thích.

`relaxedResponseFields(...)` chấp nhận những field chưa được document; vì vậy thay đổi schema ngoài descriptor có thể không bị phát hiện. Khi cần chia payload thành fragment có ý nghĩa rõ ràng, bảng cha strict với subsection descriptor và bảng con strict thường cho biết chính xác hơn phạm vi đã được document.

## 11. Đặt tên fragment và snippet

Tên path JSON và heading nghiệp vụ không cần giống nhau. Có thể dùng:

| Path | Heading dành cho người đọc | Subsection ID |
| --- | --- | --- |
| `payment` | Kết quả xử lý thanh toán | `payment` |
| `delivery` | Thông tin giao hàng | `delivery` |
| `customer` | Thông tin khách hàng | `customer` |
| `items` | Các dòng hàng | `items` |

Một số nguyên tắc:

- ID nên ngắn, ổn định và không phụ thuộc câu văn dài.
- Heading nên thể hiện khái niệm nghiệp vụ, có thể được dịch theo ngôn ngữ tài liệu.
- Đổi subsection ID thì cập nhật đường dẫn `include` tương ứng.
- Không coi subsection ID là trạng thái, version API hoặc quyền truy cập.
- Mô tả của nhánh nằm trong `description(...)`; diễn giải đầy đủ nằm ở trang; mô tả field nằm trong bảng chi tiết.

## 12. Đưa vào build và CI

Với dự án Gradle Groovy DSL đã cấu hình plugin Asciidoctor và dependency Spring REST Docs:

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

Trong CI, nên bảo đảm:

1. Test chạy và sinh snippet trước khi Asciidoctor biên soạn tài liệu.
2. Bảng cha và bảng fragment dùng cùng fixture khi chúng mô tả cùng một response.
3. Đường dẫn include khớp đúng identifier và subsection ID.
4. Heading/đoạn giải thích được lưu cùng tài liệu, không chờ snippet tự sinh cung cấp ngữ cảnh.
5. Fixture không chứa dữ liệu thanh toán thật hoặc thông tin nhạy cảm.

Nếu xuất bản Markdown, dùng template và bước ghép Markdown phù hợp thay cho cú pháp `include::[]`. Với Maven, thư mục snippet thường là `target/generated-snippets`; điều quan trọng là test phải chạy trước bước dựng tài liệu.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang con chỉ hiển thị JSON, không rõ mục đích | Chỉ include `response-body-payment.adoc` | Bổ sung heading và đoạn văn giải thích ý nghĩa fragment |
| Tên file có payment nhưng người đọc không hiểu payment là gì | Nhầm subsection ID với mô tả nghiệp vụ | Viết `description(...)` ở bảng cha và văn bản ở trang con |
| Bảng cha pass dù payment có field mới | `subsectionWithPath("payment")` bao phủ hậu duệ trong snippet tổng quan | Duy trì bảng strict riêng bằng `beneathPath("payment")` |
| Bảng chi tiết không tìm thấy `payment.amount.value` | Dùng path root sau khi đã trích payment | Dùng `amount.value` |
| Không sinh `response-fields-payment.adoc` | Chưa dùng `responseFields(beneathPath(...))` hoặc ID khác | Kiểm tra handler và subsection ID |
| Diễn giải mâu thuẫn với API | Viết từ suy đoán tên field | Đối chiếu contract và logic thực tế |
| Liên kết sang trang con không hoạt động | Anchor/xref không tồn tại trong output | Kiểm tra heading ID, include và liên kết |
| Snippet chứa dữ liệu nhạy cảm | Fixture có thông tin thật | Dùng dữ liệu giả và chỉ công bố phần đã che |
| Tài liệu vẫn cũ dù test mới chạy | Asciidoctor đọc snippet cũ hoặc chạy trước test | Làm sạch output và cấu hình dependency task |

## 14. Bài thực hành

Mở rộng `PaymentFragmentDocumentationTest`:

1. **Mô tả bảng cha:** viết lại Description của `payment` để nêu rõ vai trò thanh toán trong response đơn hàng. Kiểm tra mô tả đã phân biệt với `status` của đơn hàng chưa.
2. **Tạo trang con:** viết heading "Kết quả xử lý thanh toán", diễn giải `method`, `status`, `amount` và `transactionReference`. Nhúng `response-body-payment.adoc` và `response-fields-payment.adoc`.
3. **Thay subsection ID:** đổi `withSubsectionId("payment")` thành `withSubsectionId("payment-result")`, cập nhật tên include. Xác nhận ID chỉ làm đổi tên snippet.
4. **Thử thay đổi schema:** thêm `payment.providerCode`. Kiểm tra bảng cha có thể vẫn pass trong khi bảng chi tiết strict phát hiện field mới; thêm descriptor và giải thích.
5. **Kiểm tra optional:** bỏ `transactionReference` khỏi response và đánh dấu `optional()` theo contract; sau đó bỏ `optional()` để quan sát khác biệt.
6. **Kiểm tra ngữ cảnh:** tạm bỏ heading và đoạn diễn giải khỏi trang con. Viết lại nội dung và chỉ ra những câu hỏi người đọc không thể trả lời khi chỉ còn JSON và bảng field.
7. **Biên soạn build:** chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình; cố tình sửa đường dẫn include để xác nhận pipeline phát hiện snippet bị thiếu.

**Tiêu chí hoàn thành:** bạn giải thích được ý nghĩa fragment ở bảng cha và trang con, phân biệt subsection ID với mô tả nghiệp vụ, tạo được snippet body/bảng field riêng và dùng kiểm thử strict để bảo vệ schema quan trọng.

## 15. Câu hỏi tự kiểm tra

**1. `subsectionWithPath("payment").description(...)` giải quyết điều gì?**

Nó giải thích vai trò của nhánh payment trong bảng field của payload gốc và bao phủ các field hậu duệ trong snippet cha. Nó không sinh body hoặc bảng field chi tiết.

**2. `withSubsectionId("payment")` có hiển thị mô tả payment không?**

Không. Nó đặt định danh/hậu tố tên snippet. Ý nghĩa fragment cần được diễn giải trong `description(...)` hoặc heading và phần văn bản của trang con.

**3. Muốn tạo bảng schema riêng cho payment dùng API nào?**

Dùng `responseFields(beneathPath("payment").withSubsectionId("payment"), ...)` với field path tương đối với fragment. Với request, dùng `requestFields(...)` tương ứng.

**4. Vì sao bảng cha pass nhưng bảng payment fail?**

Bảng cha đã bao phủ toàn bộ nhánh payment. Bảng payment có descriptor riêng và strict trong phạm vi đã trích, nên có thể phát hiện field con mới chưa được document.

**5. Chỉ nhúng body fragment có đủ kiểm chứng schema không?**

Không. `responseBody(...)` tạo ví dụ JSON. `responseFields(...)` mới mô tả và kiểm tra field; assertion nghiệp vụ vẫn cần để xác minh giá trị và quy tắc.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, subsection descriptors, extraction, optional fields và relaxed documentation.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): thiết lập MockMvc, WebTestClient, REST Assured, sinh snippet và tích hợp Asciidoctor/build.

