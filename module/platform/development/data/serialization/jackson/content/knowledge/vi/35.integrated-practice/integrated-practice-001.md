# Thiết kế hợp đồng JSON cho khách hàng, đơn hàng và thanh toán

Một API thương mại điện tử thường trao đổi dữ liệu qua nhiều bước: tạo hoặc cập nhật khách hàng, lập đơn hàng, tính giá, khởi tạo thanh toán và theo dõi kết quả. Mỗi bước có dữ liệu, quyền và vòng đời riêng. Nếu các endpoint cùng dùng một entity Java hoặc một DTO tổng quát, contract dễ bị rò rỉ field nội bộ, client có thể gửi dữ liệu không được phép quyết định và thay đổi ở một luồng có thể làm hỏng luồng khác.

Thiết kế hợp đồng JSON tốt cần trả lời rõ:

- Client được gửi những field nào?
- Server tự tính hoặc tự quản lý những field nào?
- ID, tiền tệ, ngày giờ và trạng thái được biểu diễn ra sao?
- Missing, null và giá trị rỗng có ý nghĩa gì?
- Làm sao để retry request không tạo đơn hàng hoặc khoản thanh toán trùng?
- API phản hồi lỗi thế nào để client sửa request?
- Khi thêm field hoặc trạng thái mới, phiên bản client cũ có tiếp tục hoạt động an toàn không?

Bài thực hành này xây dựng contract xuyên suốt cho Customer, Order, OrderItem và Payment, dùng Jackson để ánh xạ JSON trong Spring. Trọng tâm là ranh giới giữa dữ liệu do client cung cấp và dữ liệu do server xác định.

## 1. Bắt đầu từ nghiệp vụ và các tài nguyên API

Không nên bắt đầu bằng cách serialize toàn bộ entity database. Hãy bắt đầu từ các hành động mà client được phép thực hiện.

Một luồng đơn giản:

~~~mermaid
flowchart TD
    A[Client tạo hoặc chọn Customer] --> B[POST /orders]
    B --> C[Server kiểm tra Customer và Product]
    C --> D[Server tính giá, thuế và phí]
    D --> E[Order được tạo ở trạng thái PENDING_PAYMENT]
    E --> F[POST /orders/id/payments]
    F --> G[Server tạo Payment với provider]
    G --> H{Kết quả thanh toán}
    H -->|Được chấp thuận| I[Payment AUTHORIZED hoặc SUCCEEDED]
    H -->|Cần hành động| J[REQUIRES_ACTION]
    H -->|Thất bại| K[FAILED]
    I --> L[Order chuyển sang PAID]
    J --> M[Client hoàn tất bước xác thực]
~~~

Các tài nguyên có trách nhiệm riêng:

| Tài nguyên | Trách nhiệm | Ví dụ dữ liệu |
|---|---|---|
| Customer | Danh tính và thông tin liên hệ | ID, tên, email, địa chỉ |
| Order | Yêu cầu mua hàng và trạng thái xử lý | ID, customer ID, items, totals, status |
| OrderItem | Một sản phẩm và số lượng trong đơn | Product ID, quantity, unit price snapshot |
| Payment | Một lần hoặc một phương thức thử thanh toán | ID, order ID, amount, currency, status, provider reference |

Order mô tả việc mua hàng; Payment mô tả giao dịch tiền. Một order có thể có nhiều payment attempt nếu lần đầu thất bại hoặc cần phương thức khác. Không nên gộp mọi trạng thái thanh toán vào một field mơ hồ của order.

## 2. Tách request DTO, response DTO và entity

Entity thường chứa field phục vụ persistence và logic nội bộ:

~~~java
public class CustomerEntity {
    private UUID id;
    private String name;
    private String email;
    private boolean active;
    private String internalRiskLevel;
    private Instant createdAt;
    private Instant updatedAt;
    // Quan hệ, getter và setter.
}
~~~

Không nên nhận trực tiếp CustomerEntity từ JSON hoặc serialize nó nguyên trạng. Nếu làm vậy, client có thể cố gửi active, internalRiskLevel hoặc các field mà API không công bố. Quan hệ lazy cũng có thể làm response kéo theo object graph lớn hoặc vòng tham chiếu.

Hãy tạo DTO theo use case:

- CreateCustomerRequest: field client được phép cung cấp khi đăng ký.
- UpdateCustomerRequest hoặc CustomerPatchRequest: field được phép sửa.
- CustomerResponse: field được phép công khai.
- CreateOrderRequest: sản phẩm, số lượng và địa chỉ giao hàng.
- OrderResponse: dữ liệu đơn hàng do server xác nhận.
- CreatePaymentRequest: token/phương thức thanh toán được cấp bởi provider.
- PaymentResponse: trạng thái và mã tham chiếu an toàn.

DTO riêng giúp contract ổn định khi entity thay đổi và ngăn mass assignment. Một field đã biết trong entity vẫn có thể là field client không được quyền thay đổi; FAIL_ON_UNKNOWN_PROPERTIES không giải quyết trường hợp đó.

## 3. Quy ước chung cho JSON contract

Trước khi định nghĩa từng tài nguyên, hãy chọn các quy ước dùng chung.

### 3.1. Tên field

Ví dụ này dùng snake_case trên wire và camelCase trong Java:

~~~json
{
  "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
  "created_at": "2026-11-12T08:30:00Z"
}
~~~

Có thể cấu hình naming strategy cho mapper Spring:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

Khi đó customerId được ánh xạ thành customer_id. Nếu một field có tên đặc biệt hoặc phải giữ nguyên wire name qua nhiều lần refactor, dùng @JsonProperty trên property đó.

Không đổi naming strategy toàn cục giữa các lần deploy nếu chưa đánh giá ảnh hưởng tới tất cả endpoint dùng mapper đó.

### 3.2. ID

Dùng ID ổn định, không phụ thuộc vị trí của record trong database. UUID thường được biểu diễn thành JSON string:

~~~json
{
  "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90"
}
~~~

Không dùng array index hoặc số thứ tự hiển thị làm ID tài nguyên. ID trong request cũng không chứng minh client có quyền truy cập tài nguyên đó; server vẫn phải kiểm tra quyền sở hữu và authorization.

### 3.3. Ngày giờ

Dùng kiểu Java theo semantics:
- LocalDate cho ngày lịch, ví dụ ngày sinh hoặc ngày giao dự kiến.
- Instant cho thời điểm tuyệt đối như created_at hoặc paid_at.
- OffsetDateTime khi offset client gửi có ý nghĩa trong contract.
- LocalDateTime chỉ khi timezone được quy định ở nơi khác.

Ví dụ thời điểm:

~~~json
{
  "created_at": "2026-11-12T01:30:00Z"
}
~~~

Nên dùng ISO-8601 và UTC cho timestamp hệ thống. Không dùng chuỗi ngày giờ không có offset cho một sự kiện cần xác định chính xác trên timeline.

### 3.4. Tiền tệ và số tiền

Không dùng double hoặc float để tính tiền. Dùng BigDecimal trong Java hoặc biểu diễn số nguyên theo đơn vị nhỏ nhất của currency.

Ví dụ contract dùng amount_minor:

~~~json
{
  "amount_minor": 2599,
  "currency": "USD"
}
~~~

amount_minor là số nguyên theo exponent của currency: USD thường có hai chữ số thập phân, trong khi VND không có đơn vị thập phân theo quy ước tiền tệ thông dụng. Vì vậy không được mặc định mọi currency đều chia cho 100. Quy tắc exponent cần được định nghĩa theo ISO 4217 hoặc catalog currency mà hệ thống sử dụng.

Với VND:

~~~json
{
  "amount_minor": 250000,
  "currency": "VND"
}
~~~

Đối với giá trị có thể vượt giới hạn integer an toàn của JavaScript, hoặc cần độ lớn lớn hơn long, cân nhắc biểu diễn amount dưới dạng decimal string với scale và rounding rule được công bố. Không thay đổi representation giữa endpoint mà không version contract.

## 4. Thiết kế Customer

Customer chứa thông tin nhận diện và liên hệ. Contract công khai chỉ nên gồm field cần thiết cho use case.

### 4.1. Tạo khách hàng

Request:

~~~json
{
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84901234567",
  "birth_date": "1998-04-12"
}
~~~

Java DTO:

~~~java
public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @Size(max = 30)
        String phone,

        LocalDate birthDate
) {
}
~~~

Các điểm cần chú ý:
- name và email là input cần validation.
- birthDate là LocalDate, không phải timestamp.
- id, active, createdAt và các field kiểm soát nội bộ không xuất hiện trong request đăng ký.
- Email format hợp lệ không đồng nghĩa email đã được xác minh hoặc duy nhất; service/database xử lý các quy tắc đó.

Response:

~~~json
{
  "id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84901234567",
  "birth_date": "1998-04-12",
  "created_at": "2026-11-12T08:30:00Z"
}
~~~

Java response DTO:

~~~java
public record CustomerResponse(
        UUID id,
        String name,
        String email,
        String phone,
        LocalDate birthDate,
        Instant createdAt
) {
}
~~~

Server tạo ID và timestamp. Client không được chọn createdAt hoặc trạng thái active qua request đăng ký.

### 4.2. Cập nhật khách hàng

Nếu chỉ hỗ trợ cập nhật toàn bộ một nhóm field, dùng PUT và mô tả rõ field nào bắt buộc. Nếu hỗ trợ cập nhật một phần, dùng PATCH với semantics rõ ràng.

Ví dụ PATCH:

~~~json
{
  "phone": null
}
~~~

Có thể quy ước:
- Field không xuất hiện: giữ nguyên.
- Field xuất hiện với null: xóa giá trị nếu field cho phép xóa.
- Field có giá trị: thay bằng giá trị mới.

Không nên để client tự suy đoán semantics này. Với field bắt buộc như email, null có thể bị từ chối; với phone tùy chọn, null có thể có nghĩa xóa.

## 5. Thiết kế địa chỉ giao hàng

Địa chỉ nên là object có cấu trúc để server kiểm tra và sử dụng cho tính phí vận chuyển.

~~~json
{
  "recipient_name": "Nguyen An",
  "phone": "+84901234567",
  "address_line_1": "12 Nguyen Hue",
  "address_line_2": "Floor 3",
  "ward": "Ben Nghe",
  "district": "District 1",
  "city": "Ho Chi Minh City",
  "postal_code": "700000",
  "country_code": "VN"
}
~~~

DTO:

~~~java
public record ShippingAddressRequest(
        @NotBlank String recipientName,
        @NotBlank String phone,
        @NotBlank String addressLine1,
        String addressLine2,
        String ward,
        String district,
        @NotBlank String city,
        String postalCode,
        @NotBlank
        @Pattern(regexp = "^[A-Z]{2}$")
        String countryCode
) {
}
~~~

countryCode dùng mã quốc gia hai chữ cái theo quy ước đã chọn, ví dụ VN. Regex chỉ kiểm tra hình dạng; service nên kiểm tra code có nằm trong danh mục được hỗ trợ hay không.

Địa chỉ cần được snapshot vào order tại thời điểm đặt hàng. Nếu chỉ lưu quan hệ đến địa chỉ hiện tại của Customer, việc khách hàng sửa địa chỉ sau đó có thể làm thay đổi thông tin của một order cũ.

## 6. Thiết kế Order và OrderItem

Order request nên mô tả ý định mua hàng. Server chịu trách nhiệm xác định giá, giảm giá, thuế, phí vận chuyển và tổng tiền.

### 6.1. Request tạo đơn hàng

~~~json
{
  "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
  "items": [
    {
      "product_id": "d9c6e5c2-6e4c-4e4e-a2aa-9d2c8e58c1c3",
      "quantity": 2
    },
    {
      "product_id": "5bc87e3b-b6f1-4e0f-b8e9-8a4f3dbb2f10",
      "quantity": 1
    }
  ],
  "shipping_address": {
    "recipient_name": "Nguyen An",
    "phone": "+84901234567",
    "address_line_1": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postal_code": "700000",
    "country_code": "VN"
  },
  "customer_note": "Please call before delivery"
}
~~~

DTO:

~~~java
public record CreateOrderRequest(
        @NotNull
        UUID customerId,

        @NotEmpty
        List<@NotNull @Valid OrderItemRequest> items,

        @NotNull
        @Valid
        ShippingAddressRequest shippingAddress,

        @Size(max = 500)
        String customerNote
) {
}

public record OrderItemRequest(
        @NotNull UUID productId,
        @NotNull @Positive Integer quantity
) {
}
~~~

Không nhận unit_price, discount_amount, tax_amount hoặc total_amount như dữ liệu có thẩm quyền từ client. Client có thể hiển thị giá tham khảo, nhưng server phải lấy giá từ catalog/pricing service và tính lại trước khi tạo order.

Nếu business cho phép client gửi coupon code, đó là input để server kiểm tra eligibility; không nhận số tiền giảm giá do client tự tính.

### 6.2. Server tính tiền và snapshot giá

Giả sử catalog trả về:

| Sản phẩm | Đơn giá | Số lượng | Thành tiền |
|---|---:|---:|---:|
| Keyboard | 1.200.000 VND | 2 | 2.400.000 VND |
| Mouse | 350.000 VND | 1 | 350.000 VND |

Server tạo snapshot:

~~~json
{
  "items": [
    {
      "product_id": "d9c6e5c2-6e4c-4e4e-a2aa-9d2c8e58c1c3",
      "product_name": "Keyboard",
      "quantity": 2,
      "unit_amount_minor": 1200000,
      "line_total_minor": 2400000,
      "currency": "VND"
    },
    {
      "product_id": "5bc87e3b-b6f1-4e0f-b8e9-8a4f3dbb2f10",
      "product_name": "Mouse",
      "quantity": 1,
      "unit_amount_minor": 350000,
      "line_total_minor": 350000,
      "currency": "VND"
    }
  ],
  "subtotal_minor": 2750000,
  "shipping_amount_minor": 30000,
  "discount_amount_minor": 0,
  "tax_amount_minor": 0,
  "total_amount_minor": 2780000,
  "currency": "VND"
}
~~~

Snapshot giữ lại tên và giá tại thời điểm mua, kể cả khi catalog thay đổi sau này. Cần thống nhất rounding, thuế, discount và currency exponent. Mọi phép tính tiền nên thực hiện bằng kiểu decimal/integer chính xác, không dùng floating-point.

### 6.3. Response tạo order

~~~json
{
  "id": "a68c8a77-69a9-4e8e-95aa-5e1e8a2b4a81",
  "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
  "status": "pending_payment",
  "items": [
    {
      "product_id": "d9c6e5c2-6e4c-4e4e-a2aa-9d2c8e58c1c3",
      "product_name": "Keyboard",
      "quantity": 2,
      "unit_amount_minor": 1200000,
      "line_total_minor": 2400000,
      "currency": "VND"
    }
  ],
  "subtotal_minor": 2400000,
  "shipping_amount_minor": 30000,
  "discount_amount_minor": 0,
  "tax_amount_minor": 0,
  "total_amount_minor": 2430000,
  "currency": "VND",
  "created_at": "2026-11-12T08:35:00Z"
}
~~~

Response là trạng thái server đã xác nhận. Không phản chiếu nguyên request rồi giả định tất cả field gửi lên đều được chấp nhận.

## 7. Định nghĩa enum status ổn định

Trạng thái là một phần của contract. Dùng tên wire value rõ ràng và không dùng ordinal.

~~~java
public enum OrderStatus {
    @JsonProperty("pending_payment")
    PENDING_PAYMENT,

    @JsonProperty("paid")
    PAID,

    @JsonProperty("processing")
    PROCESSING,

    @JsonProperty("shipped")
    SHIPPED,

    @JsonProperty("completed")
    COMPLETED,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

Một enum status riêng cho payment:

~~~java
public enum PaymentStatus {
    @JsonProperty("pending")
    PENDING,

    @JsonProperty("requires_action")
    REQUIRES_ACTION,

    @JsonProperty("authorized")
    AUTHORIZED,

    @JsonProperty("succeeded")
    SUCCEEDED,

    @JsonProperty("failed")
    FAILED,

    @JsonProperty("cancelled")
    CANCELLED,

    @JsonProperty("refunded")
    REFUNDED
}
~~~

Không dùng cùng một enum cho Order và Payment chỉ vì cả hai có chữ status. Hai state machine có thể tiến triển khác nhau. Ví dụ payment SUCCEEDED có thể làm order chuyển PAID, nhưng payment REFUNDED không nhất thiết làm order chuyển CANCELLED.

### 7.1. Trạng thái do server điều khiển

Client không nên gửi status: "paid" trong request tạo order hoặc cập nhật hồ sơ. Trạng thái được thay đổi bởi command hợp lệ và logic server.

Một số chuyển trạng thái cần điều kiện:
- PENDING_PAYMENT sang PAID khi payment được xác nhận.
- PAID sang PROCESSING khi fulfillment bắt đầu.
- PROCESSING sang SHIPPED khi có thông tin giao vận.
- SHIPPED sang COMPLETED khi hoàn tất.
- CANCELLED chỉ được chấp nhận nếu order đang ở trạng thái cho phép hủy và chính sách hoàn tiền được xử lý.

Không chỉ kiểm tra enum có giá trị hợp lệ; service phải kiểm tra transition có hợp lệ từ trạng thái hiện tại hay không.

### 7.2. Unknown enum trong response/event

Khi thêm status mới, consumer cũ có thể gặp giá trị chưa biết. Với command input, thường nên strict để tránh client yêu cầu một trạng thái không được hỗ trợ. Với event consumer cần forward compatibility, có thể dùng UNKNOWN hoặc lưu raw event theo chính sách rõ ràng.

Không ánh xạ một trạng thái chưa biết thành PAID, SUCCEEDED hoặc bất kỳ trạng thái có ý nghĩa tài chính nào. Unknown status phải được xử lý an toàn, theo dõi và không kích hoạt hành động nhạy cảm.

## 8. Thiết kế Payment: chỉ nhận thông tin phương thức đã token hóa

Thanh toán là ranh giới nhạy cảm. Không nên thiết kế API để client gửi toàn bộ dữ liệu thẻ rồi lưu vào entity hoặc log.

Một request thanh toán có thể dùng token/payment method reference do payment provider cấp:

~~~json
{
  "payment_method_token": "pm_tok_example_8c12",
  "return_url": "https://shop.example.com/payment/return"
}
~~~

DTO:

~~~java
public record CreatePaymentRequest(
        @NotBlank
        String paymentMethodToken,

        @NotBlank
        @Size(max = 2048)
        String returnUrl
) {
}
~~~

Token vẫn là dữ liệu nhạy cảm: không ghi vào log, không đưa vào URL hoặc analytics, và chỉ truyền đến thành phần được phép xử lý. Không nhận hoặc lưu CVV/CVC. Ưu tiên hosted checkout hoặc tokenization của provider để thông tin thẻ được xử lý trong phạm vi phù hợp.

Request không có amount hoặc currency. Server lấy tổng tiền đã chốt từ order và xác nhận order có thể được thanh toán. Nếu client gửi amount riêng, không được dùng nó làm nguồn sự thật.

### 8.1. Tạo payment cho một order

Endpoint ví dụ:

~~~http
POST /api/v1/orders/{orderId}/payments
Content-Type: application/json
Idempotency-Key: 3d7b2c8e-2b7f-4a5d-91d4-9f2d8b7a1c20
~~~

Body:

~~~json
{
  "payment_method_token": "pm_tok_example_8c12",
  "return_url": "https://shop.example.com/payment/return"
}
~~~

Server cần:
1. Xác thực người gọi và quyền truy cập order.
2. Kiểm tra order thuộc customer phù hợp.
3. Kiểm tra trạng thái order cho phép thanh toán.
4. Tính amount/currency từ snapshot order.
5. Xử lý idempotency key.
6. Gọi provider bằng amount/currency server đã xác định.
7. Lưu provider reference và trạng thái payment.
8. Trả response không chứa secret của provider.

### 8.2. Payment response

~~~json
{
  "id": "2e9eab90-82b8-4c3a-aed8-bccfb8d5c6f4",
  "order_id": "a68c8a77-69a9-4e8e-95aa-5e1e8a2b4a81",
  "status": "requires_action",
  "amount_minor": 2430000,
  "currency": "VND",
  "provider_reference": "pay_ref_91a2",
  "next_action": {
    "type": "redirect",
    "url": "https://payments.example-provider.com/continue/abc"
  },
  "created_at": "2026-11-12T08:40:00Z"
}
~~~

next_action chỉ xuất hiện khi cần client hoàn tất một bước, ví dụ redirect hoặc xác thực bổ sung. URL phải được tạo/kiểm soát từ provider đã tin cậy; không cho client tùy ý cung cấp URL callback để server điều hướng đến.

Không trả:
- PAN đầy đủ.
- CVV/CVC.
- Secret key.
- Access token nội bộ của provider.
- Raw provider response chứa dữ liệu nhạy cảm.

### 8.3. Một order có thể có nhiều payment attempt

Không giả định Order luôn có đúng một Payment. Nếu payment đầu thất bại, khách hàng có thể thử lại bằng phương thức khác. Nên có:
- Order: tổng tiền phải thu và trạng thái fulfillment.
- Payment: từng attempt, provider reference, amount, currency và status.
- Một quy tắc đảm bảo không có hai payment thành công cùng thu cho một order ngoài chủ đích.

Nếu provider hỗ trợ authorization/capture, phân biệt AUTHORIZED với SUCCEEDED/CAPTURED. Không đánh dấu order đã thanh toán chỉ vì provider mới authorize mà chưa capture, trừ khi nghiệp vụ định nghĩa như vậy.

## 9. Idempotency để retry không tạo giao dịch trùng

Client có thể không nhận được response do timeout dù server đã tạo payment. Nếu client gửi lại request, server cần nhận diện đây là cùng một ý định.

Dùng header Idempotency-Key với giá trị duy nhất cho một thao tác logic. Server lưu:
- Key.
- Phạm vi customer/merchant/endpoint.
- Hash hoặc fingerprint của request đã chuẩn hóa.
- Trạng thái xử lý.
- Kết quả/response đã tạo.
- Thời hạn lưu key theo contract.

Quy tắc thường dùng:
- Cùng key và cùng payload: trả lại kết quả trước đó hoặc trạng thái đang xử lý.
- Cùng key nhưng payload khác: từ chối conflict.
- Key mới: tạo thao tác mới nếu order còn đủ điều kiện.

Không dùng idempotency key làm authorization. Kẻ gọi vẫn phải xác thực và có quyền truy cập order.

Ví dụ response khi request đang được xử lý:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/payments/2e9eab90-82b8-4c3a-aed8-bccfb8d5c6f4
~~~

Idempotency cần được thực thi ở server/database, không chỉ giữ trong bộ nhớ một instance vì ứng dụng có thể chạy nhiều node hoặc restart.

## 10. Webhook thanh toán là một contract riêng

Payment provider có thể gửi webhook khi giao dịch thay đổi trạng thái. Webhook không phải response đồng bộ của endpoint tạo payment.

Ví dụ event:

~~~json
{
  "event_id": "evt_8a19",
  "event_type": "payment.succeeded",
  "occurred_at": "2026-11-12T08:42:00Z",
  "data": {
    "provider_payment_id": "pay_ref_91a2",
    "merchant_reference": "2e9eab90-82b8-4c3a-aed8-bccfb8d5c6f4",
    "amount_minor": 2430000,
    "currency": "VND"
  }
}
~~~

Webhook handler cần:
- Xác minh chữ ký theo hướng dẫn provider trên raw request bytes.
- Kiểm tra timestamp/replay window nếu provider hỗ trợ.
- Deduplicate theo event_id.
- Kiểm tra amount/currency và merchant reference khớp payment nội bộ.
- Chuyển trạng thái theo state machine hợp lệ.
- Xử lý event trùng hoặc đến sai thứ tự.
- Trả acknowledgement theo giao thức provider và xử lý bất đồng bộ khi cần.

Không tin field status chỉ vì JSON hợp lệ. Một webhook chưa xác minh chữ ký không được phép đánh dấu order đã thanh toán.

## 11. Tổ chức DTO Java cho toàn bộ luồng

Một nhóm DTO minh họa:

~~~java
public record CreateCustomerRequest(
        @NotBlank @Size(max = 120) String name,
        @NotBlank @Email String email,
        @Size(max = 30) String phone,
        LocalDate birthDate
) {
}

public record CustomerResponse(
        UUID id,
        String name,
        String email,
        String phone,
        LocalDate birthDate,
        Instant createdAt
) {
}

public record CreateOrderRequest(
        @NotNull UUID customerId,
        @NotEmpty List<@NotNull @Valid OrderItemRequest> items,
        @NotNull @Valid ShippingAddressRequest shippingAddress,
        @Size(max = 500) String customerNote
) {
}

public record OrderItemRequest(
        @NotNull UUID productId,
        @NotNull @Positive Integer quantity
) {
}

public record CreatePaymentRequest(
        @NotBlank String paymentMethodToken,
        @NotBlank @Size(max = 2048) String returnUrl
) {
}

public record PaymentResponse(
        UUID id,
        UUID orderId,
        PaymentStatus status,
        long amountMinor,
        String currency,
        String providerReference,
        Instant createdAt
) {
}
~~~

Đây là DTO rút gọn để thể hiện ranh giới contract. Dự án thực tế cần thêm DTO cho địa chỉ, order response, item snapshot, next action và các lỗi validation theo use case.

Không nên tạo một OrderDto dùng chung cho create, update, detail response, admin operation và webhook. Mỗi luồng có quyền và semantics khác nhau.

## 12. Spring Controller thể hiện contract ở ranh giới HTTP

Ví dụ endpoint tạo order:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            Authentication authentication
    ) {
        OrderResponse response =
                orderService.create(request, authentication);

        return ResponseEntity
                .created(URI.create("/api/v1/orders/" + response.id()))
                .body(response);
    }

    @GetMapping("/{orderId}")
    public OrderResponse get(
            @PathVariable UUID orderId,
            Authentication authentication
    ) {
        return orderService.get(orderId, authentication);
    }
}
~~~

Ví dụ tạo payment:

~~~java
@RestController
@RequestMapping("/api/v1/orders/{orderId}/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping
    public ResponseEntity<PaymentResponse> create(
            @PathVariable UUID orderId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody CreatePaymentRequest request,
            Authentication authentication
    ) {
        PaymentResponse response = paymentService.create(
                orderId,
                idempotencyKey,
                request,
                authentication
        );

        return ResponseEntity.accepted().body(response);
    }
}
~~~

Controller nhận DTO đã được Jackson ánh xạ, trigger validation và chuyển cho service. Service mới là nơi kiểm tra quyền, giá, trạng thái order và idempotency. Không đặt logic tính tiền hoặc gọi provider trực tiếp trong DTO/deserializer.

## 13. Cấu hình Jackson trong Spring

Nếu API dùng snake_case và Java Time:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: true
      adjust-dates-to-context-time-zone: false
~~~

Spring Boot thường tự cấu hình Java Time module khi dependency phù hợp có trên classpath. Nếu tự tạo ObjectMapper mới trong controller/service, mapper đó có thể không dùng cùng module, naming strategy hoặc customizer của Spring.

Nên để Spring quản lý mapper và kiểm thử JSON thực tế qua endpoint. Nếu một tích hợp ngoài cần naming hoặc date format khác, tạo DTO/reader/converter riêng theo contract đó thay vì thay đổi mapper global giữa các request.

### 13.1. Unknown property policy

Có hai chiến lược phổ biến:

- Strict command API: từ chối field lạ để phát hiện lỗi chính tả và request gửi field không được hỗ trợ.
- Forward-compatible event consumer: cho phép field mở rộng hoặc giữ unknown payload theo schema đã công bố.

Không bật ignoreUnknown = true cho mọi DTO chỉ để tránh lỗi. Ngược lại, cũng không giả định strict unknown property là giải pháp duy nhất cho mọi event version. Hãy chọn theo loại contract và kiểm thử với producer/consumer thực tế.

## 14. Null, missing và PATCH

JSON có thể biểu diễn:
- Field không xuất hiện.
- Field xuất hiện với null.
- Field xuất hiện với giá trị rỗng như "" hoặc [].
- Field có giá trị bình thường.

Với POST /customers, có thể yêu cầu name/email không null và không rỗng. Với PATCH /customers/{id}, semantics thường khác: missing có nghĩa giữ nguyên, null có thể có nghĩa xóa field tùy chọn.

Jackson @JsonInclude(NON_NULL) chỉ điều khiển field null có được đưa ra JSON output hay không. Nó không tự quyết định cách đọc null input.

Một DTO PATCH có thể giữ presence flag:

~~~java
public class CustomerPatchRequest {

    private String phone;
    private boolean phoneProvided;

    @JsonSetter("phone")
    public void setPhone(String phone) {
        this.phoneProvided = true;
        this.phone = phone;
    }

    public boolean isPhoneProvided() {
        return phoneProvided;
    }

    public String getPhone() {
        return phone;
    }
}
~~~

Service:
- phoneProvided == false: giữ nguyên phone.
- phoneProvided == true và phone == null: xóa phone nếu được phép.
- Có giá trị: cập nhật phone sau khi validate.

Với email hoặc customer ID, có thể cấm null hoặc không cho PATCH field đó. Không dùng một null policy cho tất cả property.

## 15. Lỗi API có cấu trúc và ổn định

Một response lỗi nên cho client biết:
- HTTP status.
- Error code ổn định.
- Field/path gây lỗi nếu xác định được.
- Message có thể hành động.
- Request/correlation ID.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "code": "INVALID_FIELD",
  "detail": "quantity must be greater than zero",
  "field": "$.items[0].quantity",
  "request_id": "req-7f31"
}
~~~

Có thể dùng ProblemDetail của Spring để xây dựng response theo Problem Details format, đồng thời bổ sung extension field như code và field.

Không trả stack trace, SQL, provider secret, raw payment token hoặc toàn bộ request body. Với lỗi mapping của Jackson, tránh trả nguyên văn exception message nếu nó có thể chứa giá trị input. Error code nên là contract ổn định; message có thể được cải thiện mà không làm client phải sửa logic.

## 16. Validation theo từng lớp

Không nên dồn mọi kiểm tra vào Jackson.

| Lớp | Ví dụ kiểm tra |
|---|---|
| JSON parser/Jackson | JSON hợp lệ, token đúng kiểu, field ánh xạ được |
| Bean Validation | Email có hình dạng hợp lệ, quantity dương, name không blank |
| Service/domain | Customer tồn tại, product còn bán, order có thể thanh toán |
| Authorization | Người gọi có quyền xem/sửa order của customer |
| Payment integration | Token hợp lệ, amount/currency khớp, provider response được xác minh |
| Database | Unique constraint, foreign key, transaction consistency |

Ví dụ @Positive chỉ xác nhận quantity dương. Nó không xác nhận product tồn tại hoặc khách hàng có quyền mua product đó. Tương tự, @Email không xác minh người dùng sở hữu địa chỉ email.

## 17. Quy tắc trạng thái và tính nhất quán

Order và Payment có state machine riêng. Một bảng đơn giản:

| Order status | Điều kiện chuyển tiếp ví dụ |
|---|---|
| PENDING_PAYMENT | Đơn đã tạo, chưa xác nhận thanh toán |
| PAID | Payment được xác nhận thành công theo chính sách |
| PROCESSING | Fulfillment bắt đầu |
| SHIPPED | Có thông tin vận chuyển |
| COMPLETED | Đơn hoàn tất |
| CANCELLED | Hủy theo điều kiện nghiệp vụ |

| Payment status | Ý nghĩa |
|---|---|
| PENDING | Đang tạo/xử lý |
| REQUIRES_ACTION | Cần client thực hiện bước bổ sung |
| AUTHORIZED | Provider đã authorize |
| SUCCEEDED | Thu tiền thành công theo contract |
| FAILED | Thất bại |
| CANCELLED | Hủy attempt |
| REFUNDED | Đã hoàn tiền |

Không cập nhật order thành PAID chỉ dựa trên response từ browser redirect. Kết quả cuối cần được xác nhận qua response server-to-server đáng tin cậy hoặc webhook đã xác minh, theo flow provider.

Nếu webhook đến trùng hoặc sai thứ tự, service cần kiểm tra transition và deduplicate event. Không cho một event cũ chuyển payment từ SUCCEEDED về PENDING.

## 18. Versioning và tương thích contract

Khi API đã có client bên ngoài, thay đổi JSON cần được đánh giá theo mức độ tương thích.

Thường ít rủi ro hơn:
- Thêm response field tùy chọn.
- Thêm endpoint mới.
- Thêm alias để đọc tên field cũ trong thời gian migration.
- Thêm enum value khi mọi consumer có chính sách unknown an toàn.

Có thể phá tương thích:
- Đổi tên field hiện tại.
- Đổi kiểu string thành number hoặc ngược lại.
- Đổi null thành missing hoặc ngược lại.
- Đổi đơn vị amount.
- Đổi timezone semantics.
- Xóa enum value hoặc thay ý nghĩa status.
- Thay đổi cách tính total mà không version.

Quy trình đổi tên field:
1. Consumer chấp nhận cả tên cũ và mới qua alias.
2. Server chỉ serialize tên canonical mới hoặc theo version.
3. Theo dõi client còn gửi tên cũ.
4. Thông báo thời hạn chuyển đổi.
5. Gỡ alias khi client cũ đã được loại bỏ.

Không tái sử dụng một enum value cũ cho ý nghĩa mới. Không đổi đơn vị amount_minor mà vẫn giữ nguyên tên field.

## 19. Bảo mật dữ liệu khách hàng và thanh toán

JSON hợp lệ không đồng nghĩa request đáng tin cậy. Cần bảo vệ dữ liệu ở nhiều lớp:

- Chỉ nhận field client được phép cung cấp.
- Kiểm tra quyền truy cập customer/order theo authenticated principal.
- Không tin customer_id trong body nếu nó không khớp danh tính hoặc phạm vi quyền của caller.
- Tính giá và tổng tiền phía server.
- Dùng tokenization/hosted checkout cho dữ liệu thẻ.
- Không nhận hoặc lưu CVV/CVC.
- Không log payment token, access token, thông tin xác thực hoặc raw payload.
- Giới hạn request size, số item và độ dài chuỗi.
- Xác minh chữ ký webhook và chống replay/deduplicate event.
- Dùng HTTPS và chính sách lưu trữ dữ liệu phù hợp.
- Không trả field nội bộ như risk score, internal notes hoặc provider secret trong response.

Đặc biệt, @JsonIgnore hoặc READ_ONLY là biện pháp mapping, không thay thế authorization. Service vẫn phải kiểm tra quyền trước khi thay đổi dữ liệu.

## 20. Kiểm thử contract JSON

Một contract test nên kiểm tra JSON thực tế, không chỉ gọi getter của DTO.

### 20.1. Test tên field và date format

~~~java
@Test
void serializesCustomerUsingSnakeCaseAndIsoDate() throws Exception {
    CustomerResponse response = new CustomerResponse(
            UUID.fromString("7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90"),
            "Nguyen An",
            "an@example.com",
            null,
            LocalDate.of(1998, 4, 12),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    String json = objectMapper.writeValueAsString(response);

    assertTrue(json.contains("\"birth_date\":\"1998-04-12\""));
    assertTrue(json.contains("\"created_at\":\"2026-11-12T08:30:00Z\""));
}
~~~

Nếu mapper dùng NON_NULL, test có thể xác nhận phone không xuất hiện. Nếu contract yêu cầu phone: null, cấu hình/annotation cần được điều chỉnh và test phải phản ánh điều đó.

### 20.2. Test không nhận field server quản lý

~~~java
@Test
void rejectsClientSuppliedOrderStatus() {
    String json = """
            {
              "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
              "items": [],
              "status": "paid"
            }
            """;

    assertThrows(
            JsonProcessingException.class,
            () -> strictMapper.readValue(json, CreateOrderRequest.class)
    );
}
~~~

Test này phù hợp khi command DTO dùng strict unknown property policy. Nếu API chọn ignore unknown, hãy bảo đảm field status vẫn không thể thay đổi entity; test service phải chứng minh status được server quyết định.

### 20.3. Test validation quantity

~~~java
@Test
void rejectsNonPositiveOrderQuantity() throws Exception {
    CreateOrderRequest request = objectMapper.readValue(
            """
            {
              "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
              "items": [
                {
                  "product_id": "d9c6e5c2-6e4c-4e4e-a2aa-9d2c8e58c1c3",
                  "quantity": 0
                }
              ],
              "shipping_address": {
                "recipient_name": "Nguyen An",
                "phone": "+84901234567",
                "address_line_1": "12 Nguyen Hue",
                "city": "Ho Chi Minh City",
                "country_code": "VN"
              }
            }
            """,
            CreateOrderRequest.class
    );

    Set<ConstraintViolation<CreateOrderRequest>> violations =
            validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

### 20.4. Test payment request không nhận amount

CreatePaymentRequest không có amount field. Với strict mapper, client gửi thêm amount_minor phải bị từ chối. Nếu API bỏ qua unknown field, service vẫn phải lấy amount từ order và test cần xác nhận client không thể thay số tiền.

### 20.5. Ma trận test nên có

| Nhóm | Trường hợp |
|---|---|
| Customer | Email sai, name rỗng, birth date sai format |
| Order | Customer không tồn tại, item rỗng, quantity âm/0 |
| Price | Client gửi unit price/total khác giá server |
| Currency | Currency không hỗ trợ hoặc exponent không phù hợp |
| Payment | Token thiếu, token không hợp lệ, amount không lấy từ client |
| Idempotency | Cùng key/cùng body, cùng key/khác body, key mới |
| Authorization | Caller truy cập order của customer khác |
| Status | Transition không hợp lệ, enum mới/unknown |
| Null/PATCH | Missing, null, empty string và giá trị hợp lệ |
| Webhook | Signature sai, event trùng, event đến sai thứ tự |
| Response | Không lộ field nội bộ, secret hoặc dữ liệu thanh toán nhạy cảm |

## 21. Ví dụ tổng hợp: luồng tạo order và payment

Một contract end-to-end có thể tóm tắt:

1. **Tạo order** — POST /api/v1/orders. Client gửi customer_id, items, shipping_address và note tùy chọn. Server xác thực customer/product, tính tiền và trả OrderResponse với status pending_payment.
2. **Khởi tạo payment** — POST /api/v1/orders/{id}/payments. Client gửi payment method token và idempotency key. Server lấy amount/currency từ order đã lưu và gọi provider.
3. **Hoàn tất payment** — Provider trả kết quả hoặc gửi webhook đã xác minh. Server cập nhật Payment và chuyển Order theo state machine.
4. **Đọc trạng thái** — GET /api/v1/orders/{id}. Client nhận trạng thái order, totals và payment summary đã được server xác nhận.

Ví dụ order response sau khi thanh toán:

~~~json
{
  "id": "a68c8a77-69a9-4e8e-95aa-5e1e8a2b4a81",
  "customer_id": "7d61e83d-0f9c-4c87-a1a0-4fd13a2a9f90",
  "status": "paid",
  "total_amount_minor": 2430000,
  "currency": "VND",
  "payment": {
    "id": "2e9eab90-82b8-4c3a-aed8-bccfb8d5c6f4",
    "status": "succeeded",
    "paid_at": "2026-11-12T08:42:00Z"
  },
  "created_at": "2026-11-12T08:35:00Z"
}
~~~

Đây là snapshot response của trạng thái hiện tại. API có thể trả danh sách payment attempts riêng nếu khách hàng đã thử nhiều lần; không nên giả định một order chỉ có một giao dịch.

## 22. Những lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách thiết kế tốt hơn |
|---|---|---|
| Deserialize trực tiếp vào entity | Mass assignment và lộ field nội bộ | Request/response DTO riêng |
| Client gửi total_amount làm nguồn sự thật | Có thể sửa giá | Server tính từ catalog và order |
| Dùng double cho tiền | Sai số làm tròn | Integer minor units hoặc BigDecimal |
| Mặc định currency có hai chữ số lẻ | Sai với currency exponent khác | Quy định exponent theo currency |
| Dùng Date cho ngày sinh | Có thể lệch ngày do timezone | LocalDate |
| Dùng một status cho Order và Payment | State machine nhập nhằng | Enum riêng theo tài nguyên |
| Cho client gửi status: paid | Bỏ qua quy trình thanh toán | Server quản lý transition |
| Gộp payment token vào URL/log | Lộ credential | Gửi body qua HTTPS, redaction log |
| Nhận PAN/CVV trực tiếp | Tăng phạm vi dữ liệu nhạy cảm | Hosted checkout/tokenization |
| Không có idempotency | Retry có thể tạo payment trùng | Idempotency key được lưu bền vững |
| Tin redirect từ browser là đã trả tiền | Có thể giả mạo kết quả | Xác nhận server-to-server/webhook |
| Dùng NON_NULL để định nghĩa PATCH | Nhầm output với input semantics | Presence flag/tri-state rõ ràng |
| Đổi wire name hoặc amount unit âm thầm | Client cũ đọc sai | Alias, versioning và migration |
| Trả entity/provider response nguyên trạng | Lộ thông tin nội bộ | Response DTO allowlist |

## 23. Checklist trước khi công bố API contract

**Customer**
- [ ] Request chỉ chứa field client được phép gửi.
- [ ] Response không lộ field nội bộ.
- [ ] Ngày sinh dùng LocalDate.
- [ ] Email/phone có validation và quy tắc xác minh riêng.
- [ ] Quyền truy cập customer được kiểm tra ở service.

**Order**
- [ ] Items có product ID và quantity hợp lệ.
- [ ] Giá, discount, tax, shipping và total do server tính.
- [ ] Địa chỉ được snapshot tại thời điểm đặt.
- [ ] Currency và amount unit được quy định.
- [ ] Order status do server điều khiển.
- [ ] State transition được kiểm tra.

**Payment**
- [ ] Request dùng token/payment method reference, không nhận CVV/CVC.
- [ ] Amount/currency lấy từ order.
- [ ] Có idempotency cho thao tác tạo payment.
- [ ] Provider reference và secret không bị lộ.
- [ ] Webhook được xác minh chữ ký và deduplicate.
- [ ] Payment state tách biệt order state.

**Jackson/Spring**
- [ ] Naming strategy và date format được kiểm thử.
- [ ] Java Time module được cấu hình đúng.
- [ ] Missing/null/empty có semantics rõ.
- [ ] Unknown property policy được chọn theo loại contract.
- [ ] Bean Validation được kích hoạt bằng @Valid.
- [ ] Error response có code ổn định và không echo secret.
- [ ] Contract test chạy qua mapper/converter thực tế của Spring.

## 24. Những điểm cần nhớ

- Thiết kế JSON từ use case và quyền của client, không serialize thẳng entity database.
- Tách request DTO, response DTO và entity để kiểm soát field được đọc/ghi.
- Dùng UUID hoặc ID ổn định cho tài nguyên; ID không thay thế authorization.
- Dùng LocalDate cho ngày lịch và Instant cho thời điểm tuyệt đối; thống nhất ISO-8601.
- Dùng integer minor units hoặc BigDecimal cho tiền; không dùng double/float.
- Không giả định mọi currency có hai chữ số thập phân.
- Server tính giá, thuế, discount, shipping và total từ nguồn đáng tin cậy.
- Order và Payment có state machine riêng.
- Client không được tự đặt order thành PAID hoặc payment thành SUCCEEDED.
- Dùng payment tokenization/hosted checkout; không nhận hoặc lưu CVV/CVC.
- Dùng idempotency key để xử lý retry an toàn.
- Xác minh webhook, chống replay và deduplicate event.
- Phân biệt missing, null và empty, nhất là với PATCH.
- Jackson mapping, Bean Validation, domain validation và authorization là các lớp khác nhau.
- Dùng error code ổn định, response DTO allowlist và log đã redaction.
- Version contract có kế hoạch; không đổi tên field, đơn vị tiền hoặc semantics timezone âm thầm.

Một hợp đồng JSON tốt cho khách hàng, đơn hàng và thanh toán làm rõ dữ liệu nào đến từ client, dữ liệu nào chỉ server được quyết định và mỗi tài nguyên chuyển trạng thái theo quy tắc nào. Khi DTO được tách theo use case, tiền và ngày giờ có representation chính xác, null/unknown value có semantics rõ ràng, và payment được bảo vệ bằng tokenization cùng idempotency, API sẽ dễ tích hợp, kiểm thử và tiến hóa hơn mà không làm suy yếu tính toàn vẹn của đơn hàng hoặc giao dịch.

