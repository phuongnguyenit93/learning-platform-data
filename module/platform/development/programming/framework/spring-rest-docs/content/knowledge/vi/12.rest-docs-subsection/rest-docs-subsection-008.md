# Đặt tên subsection snippet theo operation trong Spring REST Docs

## 1. Vì sao cần quy ước tên snippet?

**Spring REST Docs** sinh tài liệu REST API từ các bài kiểm thử HTTP chạy bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Mỗi lần kiểm thử gọi `document(...)` với một identifier, REST Docs ghi các snippet tương ứng vào thư mục của identifier đó. Khi payload có object hoặc mảng lồng nhau, `beneathPath(...)` có thể tạo thêm snippet body hoặc bảng field dành riêng cho subsection.

Khi một API có nhiều operation, ví dụ `GET /orders/{id}`, `POST /orders` và `PATCH /orders/{id}`, mỗi operation có thể cùng có nhánh `customer` hoặc `items`. Đặt tên snippet nhất quán giúp người viết:

- xác định snippet thuộc operation nào;
- phân biệt bảng tổng quan với bảng chi tiết của từng subsection;
- tránh ghi đè hoặc tham chiếu nhầm file khi một operation có nhiều fragment;
- tổ chức lệnh `include` trong Asciidoctor dễ đọc, dễ bảo trì;
- thay đổi cách trình bày mà vẫn giữ identifier ổn định.

Bài học phân biệt **operation identifier** và **subsection ID**, xây dựng quy tắc đặt tên, sinh nhiều snippet cho cùng operation và tham chiếu chúng trong tài liệu.

## 2. Hai tầng tên: operation và subsection

Spring REST Docs sử dụng hai giá trị có nhiệm vụ khác nhau:

**Operation identifier** là đối số đầu tiên của `document("orders-get", ...)`. Nó xác định thư mục nơi các snippet của lần document được ghi. Với identifier `orders-get`, thư mục mặc định trong Gradle thường là:

```text
build/generated-snippets/
└── orders-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
```

Các snippet thực tế phụ thuộc handler nào đã được gọi. Identifier nên thể hiện operation hoặc kịch bản tài liệu, ví dụ `orders-get`, `orders-create`, `orders-cancel`.

**Subsection ID** được đặt trên extractor bằng `withSubsectionId("customer")` hoặc `withSubsectionId("items")`. Nó xác định hậu tố tên của snippet được trích. Ví dụ:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    fieldWithPath("id").description("Mã khách hàng"),
    fieldWithPath("displayName").description("Tên hiển thị")
)
```

Trong thư mục `orders-get`, handler trên sinh `response-fields-customer.adoc`. Nếu đồng thời gọi `responseBody(beneathPath("customer").withSubsectionId("customer"))`, snippet body tương ứng có tên `response-body-customer.adoc`.

Cấu trúc kết hợp là:

```text
build/generated-snippets/
└── orders-get/                    <- operation identifier
    ├── response-fields.adoc       <- bảng tổng quan
    ├── response-fields-customer.adoc
    ├── response-body-customer.adoc
    ├── response-fields-items.adoc
    └── response-body-items.adoc
```

**Ghi nhớ:** operation identifier xác định *nhóm snippet theo operation/kịch bản*; subsection ID xác định *nhánh được document bên trong nhóm đó*. Subsection ID không tự tạo thư mục mới.

## 3. Quy tắc đặt operation identifier

Nên chọn identifier ngắn, mô tả endpoint và hành động, không phụ thuộc câu văn trong tài liệu. Một quy ước dễ dùng là:

```text
<resource>-<operation>
```

Ví dụ:

| HTTP method và endpoint | Operation identifier gợi ý | Ý nghĩa |
| --- | --- | --- |
| `GET /orders/{id}` | `orders-get` | Lấy một đơn hàng |
| `GET /orders` | `orders-list` | Liệt kê đơn hàng |
| `POST /orders` | `orders-create` | Tạo đơn hàng |
| `PATCH /orders/{id}` | `orders-update` | Cập nhật một phần đơn hàng |
| `DELETE /orders/{id}` | `orders-delete` | Xóa đơn hàng |
| `GET /orders/{id}/payments` | `orders-payments-list` | Lấy các giao dịch thanh toán của đơn hàng |

Identifier không phải một phần của URL và không bắt buộc có cấu trúc cố định theo framework. Đây là tên định danh tài liệu do nhóm dự án chọn. Điều quan trọng là tên phải dễ dự đoán, ổn định và không trùng giữa các bộ snippet có nội dung khác nhau.

### 3.1. Khi cùng một operation có nhiều kịch bản

Một endpoint có thể có nhiều kịch bản có ý nghĩa riêng:

- `GET /orders/{id}` trả thành công;
- cùng endpoint trả `404 Not Found` khi không tìm thấy đơn;
- cùng endpoint trả `403 Forbidden` khi người dùng không có quyền.

Nếu mỗi kịch bản sinh bộ snippet riêng, có thể dùng identifier riêng:

| Kịch bản | Identifier gợi ý |
| --- | --- |
| Đơn hàng tồn tại | `orders-get-found` |
| Không tìm thấy đơn | `orders-get-not-found` |
| Không có quyền xem | `orders-get-forbidden` |

Cách này giữ từng ví dụ HTTP và tài liệu tương ứng trong thư mục riêng. Nếu nhiều test cùng ghi vào một identifier và cùng tên snippet, các lần chạy có thể ghi đè nội dung hoặc khiến tài liệu khó xác định nguồn. Chỉ dùng chung identifier khi chủ ý tạo một bộ tài liệu thống nhất và đã kiểm soát tên snippet giữa các test.

### 3.2. Đừng đưa nội dung mô tả dài vào identifier

Tên như `orders-get-customer-information-and-delivery-details` dài, khó đọc và dễ thay đổi khi nội dung tài liệu được biên tập. Giữ identifier ở dạng ngắn như `orders-get`; phần diễn giải thuộc `description(...)` và văn bản Asciidoctor.

## 4. Quy tắc đặt subsection ID

Subsection ID nên phản ánh tên nhánh hoặc khái niệm được trích. Ví dụ:

| JSON path | Subsection ID gợi ý | Tên snippet field |
| --- | --- | --- |
| `customer` | `customer` | `response-fields-customer.adoc` |
| `delivery` | `delivery` | `response-fields-delivery.adoc` |
| `items` | `items` | `response-fields-items.adoc` |
| `payment` | `payment` | `response-fields-payment.adoc` |
| `items[].pricing` | `item-pricing` | `response-fields-item-pricing.adoc` |
| `delivery.address` | `delivery-address` | `response-fields-delivery-address.adoc` |

Khi chọn ID:

1. **Ổn định:** ưu tiên một tên ngắn, không thay đổi chỉ vì câu mô tả được viết lại.
2. **Dễ hiểu:** dùng tên thể hiện nhánh hoặc khái niệm trong payload.
3. **Duy nhất trong operation:** nếu hai extractor cùng tạo loại snippet, đặt ID khác nhau để file không trùng.
4. **Nhất quán:** bảng field và body của cùng fragment thường dùng cùng subsection ID, để có cặp tên dễ dự đoán.
5. **Dễ liên kết:** ID cần dễ đọc trong lệnh `include`, nhưng heading nghiệp vụ vẫn là nơi giải thích đầy đủ cho người đọc.

`withSubsectionId("item-pricing")` chỉ ảnh hưởng tên snippet. Path extractor vẫn là `items[].pricing`; nó không thay đổi cấu trúc JSON hoặc cách descriptor truy cập field.

## 5. Ví dụ: một operation sinh nhiều subsection snippet

Giả sử `GET /orders/{id}` trả:

```json
{
  "id": "ord-810",
  "status": "PAID",
  "customer": {
    "id": "cus-25",
    "displayName": "Hoa Le"
  },
  "delivery": {
    "recipient": "Hoa Le",
    "address": {
      "city": "Da Nang",
      "country": "VN"
    }
  },
  "payment": {
    "method": "CARD",
    "status": "CAPTURED",
    "amount": {
      "value": 300000,
      "currency": "VND"
    }
  }
}
```

Test có thể sinh bảng tổng quan, ba bảng field riêng và một body fragment cho payment:

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái đơn hàng"),
        subsectionWithPath("customer")
            .description("Thông tin khách hàng"),
        subsectionWithPath("delivery")
            .description("Thông tin giao hàng"),
        subsectionWithPath("payment")
            .description("Kết quả xử lý thanh toán")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        fieldWithPath("id").description("Mã khách hàng"),
        fieldWithPath("displayName").description("Tên hiển thị")
    ),
    responseFields(
        beneathPath("delivery").withSubsectionId("delivery"),
        fieldWithPath("recipient").description("Người nhận"),
        fieldWithPath("address.city").description("Thành phố"),
        fieldWithPath("address.country").description("Mã quốc gia")
    ),
    responseFields(
        beneathPath("payment").withSubsectionId("payment"),
        fieldWithPath("method").description("Phương thức"),
        fieldWithPath("status").description("Trạng thái thanh toán"),
        fieldWithPath("amount.value").description("Giá trị tiền"),
        fieldWithPath("amount.currency").description("Mã tiền tệ")
    ),
    responseBody(
        beneathPath("payment").withSubsectionId("payment")
    )
));
```

Các snippet liên quan được lưu dưới một operation identifier:

```text
build/generated-snippets/orders-get/
├── http-response.adoc
├── response-body.adoc
├── response-fields.adoc
├── response-fields-customer.adoc
├── response-fields-delivery.adoc
├── response-fields-payment.adoc
└── response-body-payment.adoc
```

Tên file cụ thể phụ thuộc loại snippet và handler đã được khai báo. Đoạn ví dụ trên minh họa các handler được gọi trong cùng một `document`; các bảng field có subsection ID khác nhau nên có tên riêng, trong khi bảng tổng quan dùng tên mặc định `response-fields.adoc`.

### 5.1. Cùng một ID cho body và field của một fragment

Có thể dùng `withSubsectionId("payment")` cho cả `responseFields(...)` và `responseBody(...)`. Hai loại snippet có prefix khác nhau:

- `response-fields-payment.adoc`
- `response-body-payment.adoc`

Vì vậy chúng không xung đột. Ngược lại, nếu có **hai bảng response field khác nhau** cùng dùng subsection ID `payment` trong cùng operation, cả hai cùng nhắm tới một tên file `response-fields-payment.adoc`. Hãy cấp ID riêng cho từng bảng hoặc thay đổi cách tổ chức các operation document.

## 6. Sinh snippet request và response theo cùng quy ước

Quy tắc định danh subsection không chỉ dành cho response. Với `POST /orders`, request có `delivery` và `items`:

```json
{
  "customerId": "cus-25",
  "delivery": {
    "recipient": "Hoa Le",
    "address": {
      "city": "Da Nang",
      "country": "VN"
    }
  },
  "items": [
    {
      "sku": "BOOK-09",
      "quantity": 1
    }
  ]
}
```

Có thể dùng:

```java
.andDo(document("orders-create",
    requestFields(
        fieldWithPath("customerId").description("Mã khách hàng"),
        subsectionWithPath("delivery").description("Thông tin giao hàng"),
        subsectionWithPath("items").description("Danh sách dòng hàng")
    ),
    requestFields(
        beneathPath("delivery").withSubsectionId("delivery"),
        fieldWithPath("recipient").description("Người nhận"),
        fieldWithPath("address.city").description("Thành phố"),
        fieldWithPath("address.country").description("Mã quốc gia")
    ),
    requestFields(
        beneathPath("items").withSubsectionId("items"),
        fieldWithPath("[].sku").description("Mã sản phẩm"),
        fieldWithPath("[].quantity").description("Số lượng")
    ),
    requestBody(
        beneathPath("delivery").withSubsectionId("delivery")
    )
));
```

Trong snippet chi tiết được trích bằng `beneathPath("delivery")`, path bắt đầu từ nhánh delivery: `recipient`, `address.city`, `address.country`. Khi trích mảng `items`, path đi từ root của mảng; trong ví dụ này dùng `[].sku` và `[].quantity` để chỉ các phần tử array. Hãy xác nhận path theo cấu trúc JSON thực tế và phiên bản REST Docs trong dự án.

Các tên file minh họa:

```text
build/generated-snippets/orders-create/
├── request-fields.adoc
├── request-fields-delivery.adoc
├── request-fields-items.adoc
└── request-body-delivery.adoc
```

Như vậy, `orders-create` xác định operation tạo đơn hàng, còn `delivery` và `items` phân biệt các fragment request của operation đó.

## 7. Một operation có nhiều fragment cùng loại: tránh va chạm tên

Một lỗi dễ xảy ra là dùng cùng ID cho hai subsection extractor khác path:

```java
responseFields(
    beneathPath("billingAddress").withSubsectionId("address"),
    fieldWithPath("city").description("Thành phố thanh toán")
),
responseFields(
    beneathPath("shippingAddress").withSubsectionId("address"),
    fieldWithPath("city").description("Thành phố giao hàng")
)
```

Cả hai đều cố ghi `response-fields-address.adoc` trong cùng operation. Nội dung có thể bị ghi đè hoặc xung đột tùy cấu hình và quá trình thực thi. Nên đặt tên theo **vai trò nghiệp vụ**:

```java
responseFields(
    beneathPath("billingAddress").withSubsectionId("billing-address"),
    fieldWithPath("city").description("Thành phố thanh toán")
),
responseFields(
    beneathPath("shippingAddress").withSubsectionId("shipping-address"),
    fieldWithPath("city").description("Thành phố giao hàng")
)
```

Đầu ra sẽ phân biệt:

- `response-fields-billing-address.adoc`
- `response-fields-shipping-address.adoc`

Không nhất thiết đặt subsection ID bằng chính JSON path. Nếu hai path khác nhau nhưng cùng một khái niệm, tên ID cần làm rõ ý nghĩa với người đọc và tránh trùng. Ngược lại, nếu path giống nhau nhưng hai bảng phục vụ độc giả hoặc phạm vi khác nhau, hãy dùng ID biểu đạt mục đích tài liệu.

## 8. Liên kết tên snippet trong Asciidoctor

Operation identifier và subsection ID được kết hợp trong đường dẫn include:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Truy vấn đơn hàng theo mã định danh.

=== Response tổng quan

include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

=== Khách hàng

Thông tin định danh và tên hiển thị của khách hàng được gắn với đơn hàng.

include::{snippets}/orders-get/response-fields-customer.adoc[]

=== Giao hàng

Nhánh delivery mô tả người nhận và địa chỉ giao đơn.

include::{snippets}/orders-get/response-fields-delivery.adoc[]

=== Thanh toán

Nhánh payment mô tả kết quả xử lý khoản thanh toán của đơn hàng.

include::{snippets}/orders-get/response-body-payment.adoc[]
include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Cấu trúc đường dẫn gồm:

```text
{snippets}/{operation-identifier}/{snippet-name}
```

Ví dụ `orders-get` là thư mục; `response-fields-payment.adoc` là tên snippet trong thư mục ấy. Đừng đảo hai giá trị hoặc đưa subsection ID thành một phần của URL endpoint.

### 8.1. Khi tài liệu được chia thành nhiều file

Có thể đưa phần chi tiết vào fragment Asciidoctor riêng rồi include vào trang operation:

```asciidoc
// orders.adoc
== GET /orders/{id}

include::{snippets}/orders-get/response-fields.adoc[]

include::fragments/order-customer.adoc[]
include::fragments/order-payment.adoc[]
```

```asciidoc
// fragments/order-payment.adoc
=== Thanh toán

Payment thể hiện phương thức, trạng thái, số tiền và thông tin tham chiếu
giao dịch của khoản thanh toán gắn với đơn hàng.

include::{snippets}/orders-get/response-body-payment.adoc[]
include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Trong tài liệu nhiều trang, dùng cơ chế liên kết xref/anchor mà hệ thống xuất bản hỗ trợ. Snippet ID không tự tạo page anchor và operation identifier cũng không thay thế tiêu đề endpoint.

## 9. Những lỗi đặt tên phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Include không tìm thấy thư mục | Nhầm operation identifier với subsection ID | Kiểm tra đối số đầu tiên của `document(...)` |
| Include không tìm thấy file subsection | Subsection ID trong include khác `withSubsectionId` | Đồng bộ hậu tố tên snippet |
| Hai bảng field ghi cùng một file | Hai extractor cùng loại dùng trùng subsection ID trong một operation | Đặt ID khác nhau, ví dụ `billing-address` và `shipping-address` |
| Body và bảng field bị hiểu là xung đột | Nghĩ rằng cùng subsection ID gây trùng mọi snippet | Body và field có prefix khác nhau; dùng cùng ID cho cặp snippet cùng fragment là hợp lý |
| Mỗi operation sinh snippet vào cùng thư mục ngoài ý muốn | Tái sử dụng operation identifier cho các bộ tài liệu độc lập | Chọn identifier riêng cho từng operation/kịch bản |
| Tên file dài và khó dự đoán | Dùng cả câu mô tả làm subsection ID | Giữ ID ngắn; chuyển mô tả sang `description(...)` và heading |
| Người đọc không biết fragment có ý nghĩa gì | Chỉ nhìn tên snippet và path | Viết description nghiệp vụ ở bảng cha và văn bản ở phần chi tiết |
| Đổi ID nhưng trang tài liệu vẫn dùng tên cũ | Không cập nhật các lệnh `include` | Tìm và sửa mọi tham chiếu của snippet cũ |

## 10. Tổ chức test và build với Gradle/CI

Ví dụ cấu hình Gradle Groovy DSL, giả định dự án đã áp dụng plugin Asciidoctor và có dependency Spring REST Docs:

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

Để tên snippet dễ duy trì trong CI:

1. Tổ chức operation identifier theo resource và hành động, ví dụ `orders-get` và `orders-create`.
2. Đặt subsection ID theo ý nghĩa fragment, tránh trùng giữa hai bảng cùng loại trong một operation.
3. Giữ ID ổn định; khi đổi ID phải cập nhật các `include` tương ứng.
4. Không cho hai kịch bản độc lập ghi chung một operation identifier nếu chúng sinh snippet trùng tên.
5. Kiểm tra build sau khi thay đổi ID để phát hiện file include không tồn tại.
6. Dùng fixture giả, tránh dữ liệu nhạy cảm trong snippet response hoặc request.

Với Maven, output snippet thường nằm trong `target/generated-snippets`. Nguyên tắc đặt tên operation/subsection không đổi; chỉ đường dẫn gốc của biến `snippets` thay đổi theo build.

## 11. Bài thực hành

Áp dụng các quy ước trên cho API đơn hàng:

1. **Đặt operation ID:** tạo identifier cho `GET /orders/{id}`, `GET /orders` và `POST /orders`. Giải thích vì sao mỗi bộ snippet thuộc một thư mục.
2. **Đặt subsection ID:** trong `orders-get`, trích `customer`, `delivery`, `payment`. Dùng cùng ID cho body và field của cùng fragment.
3. **Tránh trùng tên:** thêm hai object `billingAddress` và `shippingAddress`. Dùng các ID riêng `billing-address` và `shipping-address` rồi xác nhận tên file đầu ra.
4. **Phân biệt operation và scenario:** viết hai test `GET /orders/{id}`, một test thành công và một test không tìm thấy. Đặt identifier riêng nếu hai test sinh response snippet khác nhau.
5. **Cập nhật tài liệu:** thêm các lệnh `include` tương ứng vào Asciidoctor. Đổi subsection ID một lần, tìm và sửa các tham chiếu cũ.
6. **Kiểm tra build:** chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình; xác nhận mọi snippet được tham chiếu đều tồn tại.

**Tiêu chí hoàn thành:** bạn phân biệt được operation identifier với subsection ID, dự đoán đúng đường dẫn snippet, chọn ID không trùng cho các fragment cùng loại và có thể tổ chức bộ snippet theo operation mà không làm trang tài liệu khó bảo trì.

## 12. Câu hỏi tự kiểm tra

**1. `document("orders-get", ...)` xác định điều gì?**

Nó xác định operation identifier, tức tên nhóm/thư mục chứa các snippet sinh ra từ lần document đó.

**2. `withSubsectionId("payment")` xác định điều gì?**

Nó định danh subsection extractor và đặt hậu tố cho snippet tương ứng, ví dụ `response-fields-payment.adoc`.

**3. Có thể dùng cùng subsection ID cho body và bảng field không?**

Có. `response-body-payment.adoc` và `response-fields-payment.adoc` có prefix khác nhau nên tạo thành cặp snippet của cùng fragment.

**4. Khi nào cần subsection ID khác nhau?**

Khi trong cùng operation có nhiều snippet cùng loại cần được tách riêng, ví dụ bảng billing address và shipping address đều là response field snippets.

**5. Thay subsection ID có đổi JSON path không?**

Không. Path do `beneathPath(...)` xác định; subsection ID chỉ ảnh hưởng định danh/tên snippet và các tham chiếu tới file đó.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): cách dùng subsection extractor, field documentation và đặt ID cho subsection.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình document operation, snippet output và tích hợp Asciidoctor/build.

