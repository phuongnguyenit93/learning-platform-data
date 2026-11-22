# Thiết kế trường phân biệt kiểu theo giá trị nghiệp vụ

Khi một JSON field có thể chứa nhiều kiểu object khác nhau, Jackson cần một dấu hiệu để biết nên tạo class Java nào. Ví dụ, một giao dịch có thể thanh toán bằng thẻ, chuyển khoản hoặc ví điện tử; một message có thể là sự kiện tạo người dùng, cập nhật hóa đơn hoặc hủy đơn hàng. Nếu chỉ khai báo kiểu base như `PaymentMethod` hoặc `DomainEvent`, Jackson chưa đủ thông tin để chọn subtype cụ thể khi deserialize.

Một cách phổ biến là đặt **trường phân biệt kiểu** (type discriminator) trong JSON. Giá trị của trường này mô tả loại nghiệp vụ, chẳng hạn `"method": "bank_transfer"` hoặc `"eventType": "user.registered"`. Jackson ánh xạ các giá trị nghiệp vụ đó tới các subtype Java bằng cơ chế polymorphic type handling.

Thiết kế discriminator tốt cần tách biệt hợp đồng dữ liệu với tên class triển khai. Giá trị như `bank_transfer` nên ổn định dù class được đổi tên từ `BankTransferPayment` sang một tên khác. Bài này tập trung vào cách chọn tên trường và giá trị discriminator, cấu hình `@JsonTypeInfo`, đăng ký subtype, xử lý tương thích và kiểm soát dữ liệu đầu vào.

## 1. Vì sao cần trường phân biệt kiểu?

Giả sử hệ thống có một kiểu thanh toán trừu tượng:

```java
public abstract class PaymentMethod {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Hai subtype có dữ liệu riêng:

```java
public class CardPayment extends PaymentMethod {
    private String lastFourDigits;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}

public class BankTransferPayment extends PaymentMethod {
    private String bankCode;
    private String reference;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}
```

Nếu JSON chỉ có các field dữ liệu:

```json
{
  "amount": 125000,
  "bankCode": "VCB",
  "reference": "TX-900"
}
```

Jackson không thể luôn suy luận rằng object này phải trở thành `BankTransferPayment`. Các field riêng có thể là field mở rộng, bị thiếu hoặc trùng với kiểu khác. Suy luận subtype bằng cách đoán dựa trên sự hiện diện của field dễ tạo hành vi mơ hồ.

Thêm discriminator làm ý định rõ ràng:

```json
{
  "method": "bank_transfer",
  "amount": 125000,
  "bankCode": "VCB",
  "reference": "TX-900"
}
```

Giờ đây, `method = "bank_transfer"` là chỉ dẫn rõ để Jackson chọn `BankTransferPayment`.

Một discriminator có ba vai trò:

1. **Nhận diện biến thể:** cho biết object thuộc loại nghiệp vụ nào.
2. **Chọn subtype:** ánh xạ giá trị trên wire tới class Java cụ thể.
3. **Giữ ổn định hợp đồng:** cho phép đổi tên class hoặc package mà không buộc producer thay đổi JSON.

## 2. Chọn giá trị nghiệp vụ thay vì tên class

Với polymorphism, Jackson có nhiều cách mã hóa type id. Khi JSON đến từ hệ thống bên ngoài, nên ưu tiên tên logic ổn định bằng `JsonTypeInfo.Id.NAME`.

Ví dụ:

| Giá trị discriminator | Subtype Java |
|---|---|
| `card` | `CardPayment` |
| `bank_transfer` | `BankTransferPayment` |
| `digital_wallet` | `WalletPayment` |

Các giá trị này mô tả phương thức thanh toán theo ngôn ngữ nghiệp vụ. Chúng không tiết lộ package hoặc tên class.

Tránh dùng các giá trị như:

```json
{
  "@class": "com.example.payment.BankTransferPayment"
}
```

Tên class là chi tiết triển khai. Khi đổi package, chia module hoặc refactor class, payload cũ có thể không còn deserialize được. Ngoài ra, class-name type id và default typing mở rộng bề mặt rủi ro khi xử lý JSON không tin cậy.

Một discriminator tốt nên có các đặc điểm:

- **Ổn định:** không đổi chỉ vì refactor code.
- **Có ý nghĩa nghiệp vụ:** người tích hợp có thể hiểu giá trị mà không biết class Java.
- **Ngắn và nhất quán:** dùng quy ước như snake_case hoặc dotted name.
- **Không phụ thuộc ngôn ngữ hiển thị:** tránh label đã dịch như `"Chuyển khoản"` hoặc `"Bank transfer"` nếu chúng có thể thay đổi.
- **Không phụ thuộc database ID nội bộ:** ID có thể thay đổi theo môi trường hoặc lần triển khai.
- **Có chính sách versioning:** khi loại nghiệp vụ đổi nghĩa, cần định nghĩa alias hoặc version contract rõ ràng.

Ví dụ, `bank_transfer` tốt hơn `BankTransferPayment`, `com.acme.payments.BankTransferPayment` hoặc `"Chuyển khoản ngân hàng"`.

## 3. Cấu hình discriminator bằng @JsonTypeInfo

Trong Jackson 2.x, annotation `@JsonTypeInfo` thuộc package `com.fasterxml.jackson.annotation`. Nó mô tả cách type metadata được lưu trong JSON và cách Jackson giải quyết subtype.

Ví dụ cơ bản:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "method"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer"),
        @JsonSubTypes.Type(value = WalletPayment.class, name = "digital_wallet")
})
public abstract class PaymentMethod {
    // Các thuộc tính dùng chung
}
```

Các thành phần chính:

- `use = JsonTypeInfo.Id.NAME`: sử dụng tên logic thay vì tên class.
- `include = JsonTypeInfo.As.PROPERTY`: ghi type id thành một JSON property trong object.
- `property = "method"`: tên field discriminator trên wire.
- `@JsonSubTypes`: ánh xạ từng giá trị nghiệp vụ tới subtype Java tương ứng.

JSON đầu vào:

```json
{
  "method": "bank_transfer",
  "amount": 125000,
  "bankCode": "VCB",
  "reference": "TX-900"
}
```

Khi deserialize vào `PaymentMethod.class`, Jackson đọc `method`, tìm mapping `bank_transfer` và tạo `BankTransferPayment`. Sau đó các property còn lại được binding theo class đã chọn.

### 3.1. Đặt annotation trên base type

Đặt `@JsonTypeInfo` trên abstract class hoặc interface giúp mọi property khai báo bằng base type sử dụng cùng quy tắc:

```java
public class PaymentRequest {
    private String requestId;
    private PaymentMethod payment;

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public PaymentMethod getPayment() {
        return payment;
    }

    public void setPayment(PaymentMethod payment) {
        this.payment = payment;
    }
}
```

JSON:

```json
{
  "requestId": "REQ-100",
  "payment": {
    "method": "card",
    "amount": 99000,
    "lastFourDigits": "1234"
  }
}
```

Vì kiểu khai báo của property `payment` là `PaymentMethod`, Jackson sử dụng metadata trên base type để chọn `CardPayment`.

### 3.2. Đặt annotation trên một property cụ thể

Nếu chỉ một property cần polymorphism, có thể đặt annotation tại field hoặc getter của property:

```java
public class WorkflowStep {
    private String name;

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "action"
    )
    @JsonSubTypes({
            @JsonSubTypes.Type(value = EmailAction.class, name = "send_email"),
            @JsonSubTypes.Type(value = WebhookAction.class, name = "call_webhook")
    })
    private Action action;
}
```

Cách này giới hạn quy tắc polymorphism trong property đó. Khi annotation được đặt trên base type, các nơi khác dùng base type cũng có thể chịu cùng chính sách. Hãy chọn vị trí khai báo theo phạm vi hợp đồng thực tế.

## 4. Giá trị type id là tên logic, không phải tên class

Có thể khai báo tên subtype ngay trong `@JsonSubTypes`:

```java
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
```

Giá trị `name` chính là type id mà producer gửi trong JSON. Jackson không cần tên class trùng với chuỗi này.

Có thể dùng `@JsonTypeName` trên subtype để khai báo tên logic:

```java
@JsonTypeName("bank_transfer")
public class BankTransferPayment extends PaymentMethod {
    // ...
}
```

`@JsonTypeName` hữu ích khi muốn tên type đi cùng class subtype. Tuy nhiên, subtype vẫn cần được Jackson biết đến thông qua `@JsonSubTypes`, đăng ký programmatic hoặc cơ chế subtype discovery phù hợp. Chỉ thêm `@JsonTypeName` không phải lúc nào cũng đủ để mọi mapper tự tìm class đó.

### 4.1. Chọn một nguồn mapping rõ ràng

Có thể khai báo tên ở `@JsonSubTypes.Type(name = ...)` hoặc dùng `@JsonTypeName` trên class. Tránh khai báo hai nguồn khác nhau cho cùng một subtype mà không có lý do rõ ràng.

Một quy ước dễ duy trì:

- Base type khai báo discriminator property và danh sách subtype được phép.
- Mỗi subtype có một logical id ổn định.
- Unit test xác nhận JSON output dùng đúng id và input map đúng class.

### 4.2. Đăng ký subtype bằng code

Nếu không muốn đặt danh sách subtype trong annotation, có thể đăng ký bằng mapper:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransferPayment.class, "bank_transfer"),
        new NamedType(WalletPayment.class, "digital_wallet")
);
```

Cách này hữu ích khi subtype đến từ module/plugin hoặc danh sách biến thể được cấu hình ở composition root. Chỉ đăng ký các subtype mà ứng dụng chủ động hỗ trợ; không lấy class name tùy ý từ payload để nạp class.

## 5. Thiết kế tên trường discriminator

Tên field cần thể hiện đúng phạm vi nghiệp vụ. Các tên phổ biến:

| Tên field | Phạm vi thường phù hợp | Ví dụ giá trị |
|---|---|---|
| `type` | Một cấu trúc generic hoặc message chung | `created`, `updated` |
| `kind` | Phân loại một nhóm object | `individual`, `company` |
| `eventType` | Loại domain event | `order.shipped`, `user.registered` |
| `method` | Phương thức thực hiện | `card`, `bank_transfer` |
| `channel` | Kênh giao tiếp hoặc phân phối | `email`, `sms`, `push` |
| `provider` | Nhà cung cấp khi provider quyết định cấu trúc subtype | `provider_a`, `provider_b` |

Không nên chọn một field quá chung như `type` nếu object đã có một property nghiệp vụ khác cũng tên `type`. Ví dụ một event có thể có:

```json
{
  "eventType": "invoice.paid",
  "status": "completed",
  "data": {
    "paymentType": "bank_transfer"
  }
}
```

Ở đây, `eventType` chọn subtype của event envelope; `paymentType` mô tả phương thức thanh toán trong payload. Mỗi field có một trách nhiệm khác nhau.

### 5.1. Dùng code ổn định thay cho label hiển thị

Không dùng label giao diện làm type id:

```json
{
  "method": "Chuyển khoản ngân hàng"
}
```

Nếu giao diện đổi ngôn ngữ sang tiếng Anh hoặc thay cách diễn đạt, contract sẽ bị ảnh hưởng. Thay bằng code ổn định:

```json
{
  "method": "bank_transfer"
}
```

Label hiển thị có thể được tra cứu từ enum hoặc bảng localization ở tầng ứng dụng.

### 5.2. Không dùng giá trị thay đổi theo từng bản ghi

Discriminator chọn loại cấu trúc, không phải ID của instance. Ví dụ `"eventType": "user.registered"` là type id; `"eventId": "evt-100"` là định danh của một event cụ thể. Không dùng event ID, database ID hoặc tên người dùng làm discriminator.

## 6. Dùng As.PROPERTY khi Jackson tự thêm discriminator

`JsonTypeInfo.As.PROPERTY` là lựa chọn thông dụng khi muốn Jackson đưa type id vào object JSON như một field metadata.

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "method"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
public abstract class PaymentMethod {
}
```

Khi serialize một giá trị được khai báo theo base type, Jackson có thể phát:

```json
{
  "method": "card",
  "amount": 99000,
  "lastFourDigits": "1234"
}
```

Field `method` được Jackson thêm như type metadata. Nếu class subtype cũng có một property nghiệp vụ tên `method`, cần quyết định rõ có muốn dùng cùng field đó làm discriminator hay không. Nếu có, hãy xem `As.EXISTING_PROPERTY` ở phần sau để tránh hai nguồn phát sinh cùng một tên.

### 6.1. visible mặc định là false

`@JsonTypeInfo` có thuộc tính `visible`, mặc định là `false`. Khi đó, type id được dùng để chọn subtype nhưng bị loại khỏi luồng property trước khi bean deserializer xử lý các field thông thường.

Điều này phù hợp khi discriminator chỉ là metadata:

```json
{
  "method": "card",
  "amount": 99000,
  "lastFourDigits": "1234"
}
```

Class `CardPayment` không cần có field `method` nếu ứng dụng chỉ cần biết subtype là `CardPayment`.

### 6.2. Khi nào cần visible = true?

Nếu subtype cũng cần lưu giá trị discriminator như một property Java, bật `visible = true`:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "eventType",
        visible = true
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = UserRegisteredEvent.class, name = "user.registered"),
        @JsonSubTypes.Type(value = InvoicePaidEvent.class, name = "invoice.paid")
})
public abstract class DomainEvent {
    private String eventType;

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
```

Với `visible = true`, Jackson vừa dùng `eventType` để chọn subtype, vừa đưa field đó tới deserializer của subtype để binding như property thông thường.

Chỉ bật `visible` khi class có field/setter hoặc cơ chế xử lý tương ứng. Nếu subtype không có property phù hợp, field type id có thể trở thành unknown property hoặc không được xử lý như mong muốn tùy cấu hình.

## 7. Dùng As.EXISTING_PROPERTY khi discriminator đã là property nghiệp vụ

Nhiều mô hình domain đã có sẵn một property như `eventType`, `method` hoặc `kind`. Khi đó, có thể dùng `JsonTypeInfo.As.EXISTING_PROPERTY`: Jackson dùng property hiện hữu làm type id thay vì phát thêm một metadata property độc lập.

Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXISTING_PROPERTY,
        property = "eventType"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = UserRegisteredEvent.class, name = "user.registered"),
        @JsonSubTypes.Type(value = InvoicePaidEvent.class, name = "invoice.paid")
})
public abstract class DomainEvent {
    @JsonProperty("eventType")
    public abstract String getEventType();
}
```

Subtype trả về code cố định:

```java
public class UserRegisteredEvent extends DomainEvent {
    private String userId;

    @Override
    public String getEventType() {
        return "user.registered";
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }
}
```

Serialization tạo một field `eventType` thông qua getter thông thường:

```json
{
  "eventType": "user.registered",
  "userId": "U-100"
}
```

Với `EXISTING_PROPERTY`, serializer không tạo thêm một type-id property riêng bên cạnh property hiện hữu. Do đó, giá trị do getter trả về phải khớp với tên subtype được đăng ký.

### 7.1. visible có ý nghĩa gì với EXISTING_PROPERTY?

`visible` vẫn quyết định type id có được chuyển tiếp vào quá trình binding property hay không. Mặc định `false`: Jackson dùng `eventType` để chọn subtype rồi không chuyển token đó như một property thông thường. Điều này phù hợp với ví dụ getter chỉ đọc ở trên.

Nếu class cần lưu giá trị đầu vào, có thể đặt `visible = true` và cung cấp setter/field tương ứng. Khi đó nên kiểm tra giá trị nhận được khớp với subtype đã chọn, tránh một object `UserRegisteredEvent` nhưng lại lưu `eventType = "invoice.paid"`.

### 7.2. Tránh hai nguồn giá trị discriminator

Không nên vừa để Jackson tự chèn type id bằng `As.PROPERTY`, vừa có getter thông thường phát một property cùng tên với giá trị khác. Điều này dễ dẫn tới xung đột hoặc output không đúng contract.

Quy tắc chọn:

- Discriminator chỉ là metadata do Jackson quản lý: dùng `As.PROPERTY`, thường giữ `visible = false`.
- Discriminator đã là field nghiệp vụ và serializer của DTO chịu trách nhiệm phát nó: cân nhắc `As.EXISTING_PROPERTY`.
- Discriminator cần được giữ lại trong field Java khi deserialize: bật `visible = true` và có mutator rõ ràng.

## 8. Ví dụ đầy đủ: phương thức thanh toán

Định nghĩa base type với logical id:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "method"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer"),
        @JsonSubTypes.Type(value = WalletPayment.class, name = "digital_wallet")
})
public abstract class PaymentMethod {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Các subtype:

```java
public class CardPayment extends PaymentMethod {
    private String lastFourDigits;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}

public class BankTransferPayment extends PaymentMethod {
    private String bankCode;
    private String reference;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}

public class WalletPayment extends PaymentMethod {
    private String walletProvider;
    private String walletAccount;

    public String getWalletProvider() {
        return walletProvider;
    }

    public void setWalletProvider(String walletProvider) {
        this.walletProvider = walletProvider;
    }

    public String getWalletAccount() {
        return walletAccount;
    }

    public void setWalletAccount(String walletAccount) {
        this.walletAccount = walletAccount;
    }
}
```

Request chứa base type:

```java
public class PaymentRequest {
    private String requestId;
    private PaymentMethod payment;

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public PaymentMethod getPayment() {
        return payment;
    }

    public void setPayment(PaymentMethod payment) {
        this.payment = payment;
    }
}
```

JSON chuyển khoản:

```json
{
  "requestId": "REQ-100",
  "payment": {
    "method": "bank_transfer",
    "amount": 125000,
    "bankCode": "VCB",
    "reference": "TX-900"
  }
}
```

Deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

PaymentRequest request = mapper.readValue(json, PaymentRequest.class);

PaymentMethod payment = request.getPayment();

if (payment instanceof BankTransferPayment bankTransfer) {
    System.out.println(bankTransfer.getBankCode());
    System.out.println(bankTransfer.getReference());
}
```

Jackson đọc discriminator và tạo subtype phù hợp. Phần code nghiệp vụ có thể xử lý theo interface/base class, chỉ kiểm tra subtype khi thực sự cần hành vi riêng.

## 9. Serialize polymorphic object đúng declared type

Khi deserialize vào base type, Jackson có target type rõ ràng. Khi serialize, cần lưu ý declared type mà serializer nhìn thấy.

Nếu object được ghi qua một property khai báo `PaymentMethod`, type metadata được áp dụng theo base type. Với root value, nếu gọi mapper trực tiếp bằng một biến có runtime type là `BankTransferPayment`, serializer có thể chỉ nhìn thấy kiểu runtime cụ thể và không đi qua polymorphic metadata được khai báo ở base type.

Khi cần root output có discriminator, hãy cung cấp declared type:

```java
PaymentMethod payment = new BankTransferPayment();

ObjectWriter writer = mapper.writerFor(PaymentMethod.class);
String json = writer.writeValueAsString(payment);
```

Hoặc đặt object trong một DTO có property kiểu `PaymentMethod`. Với collection, khai báo kiểu phần tử đầy đủ:

```java
List<PaymentMethod> payments = loadPayments();

ObjectWriter writer = mapper.writerFor(
        new TypeReference<List<PaymentMethod>>() {}
);

String json = writer.writeValueAsString(payments);
```

Mỗi phần tử sẽ được serialize theo base type và có type id tương ứng. Khi đọc, cũng dùng `TypeReference<List<PaymentMethod>>` để giữ kiểu phần tử.

## 10. Discriminator trong danh sách và object lồng nhau

Một list có thể chứa nhiều subtype khác nhau:

```json
[
  {
    "method": "card",
    "amount": 99000,
    "lastFourDigits": "1234"
  },
  {
    "method": "bank_transfer",
    "amount": 125000,
    "bankCode": "VCB",
    "reference": "TX-900"
  },
  {
    "method": "digital_wallet",
    "amount": 50000,
    "walletProvider": "wallet_x",
    "walletAccount": "A-88"
  }
]
```

Deserialize:

```java
List<PaymentMethod> payments = mapper.readValue(
        json,
        new TypeReference<List<PaymentMethod>>() {}
);
```

Jackson xử lý từng phần tử dựa trên type id của chính phần tử đó.

Với cấu trúc lồng nhau, discriminator nằm bên trong object polymorphic tương ứng:

```json
{
  "orderId": "ORD-1",
  "payment": {
    "method": "card",
    "amount": 99000,
    "lastFourDigits": "1234"
  }
}
```

`method` ở đây chọn subtype của property `payment`, không chọn subtype của `Order`.

Nếu cần discriminator nằm ngoài object property, Jackson có `JsonTypeInfo.As.EXTERNAL_PROPERTY`. Cách này phù hợp với một số schema có cấu trúc như:

```json
{
  "actionType": "send_email",
  "action": {
    "to": "user@example.test",
    "subject": "Welcome"
  }
}
```

Với `EXTERNAL_PROPERTY`, type id là sibling của property polymorphic thay vì nằm bên trong object đó. Cần cấu hình annotation tại property và kiểm thử đúng vị trí của discriminator; cách này không tương đương `As.PROPERTY`.

## 11. Xử lý type id không biết hoặc bị thiếu

Một contract thực tế cần định nghĩa điều gì xảy ra khi producer gửi type id mà consumer chưa hỗ trợ.

Ví dụ:

```json
{
  "method": "crypto_wallet",
  "amount": 50000,
  "walletAddress": "..."
}
```

Nếu `crypto_wallet` chưa được đăng ký, Jackson thường báo lỗi subtype/type id không hợp lệ khi deserialize vào base type. Đây là hành vi tốt cho contract strict vì tránh âm thầm tạo sai kiểu.

### 11.1. Giữ strict behavior khi dữ liệu phải đúng schema

Mặc định `DeserializationFeature.FAIL_ON_INVALID_SUBTYPE` thường được bật. Với discriminator thiếu hoặc không nhận diện, mapper từ chối thay vì tự đoán class.

Đây là lựa chọn phù hợp cho:

- Lệnh thanh toán.
- Event cần xử lý đúng handler.
- Command có tác động nghiệp vụ.
- API mà subtype quyết định validation hoặc quyền thực thi.

### 11.2. defaultImpl là fallback có chủ đích

`@JsonTypeInfo` có thuộc tính `defaultImpl` để chỉ định class dự phòng khi type id thiếu hoặc không giải quyết được, trong phạm vi cơ chế polymorphic type handling hỗ trợ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "eventType",
        defaultImpl = UnknownEvent.class
)
```

Fallback chỉ an toàn nếu class dự phòng có thể biểu diễn dữ liệu chưa biết và ứng dụng xử lý nó như một loại unknown rõ ràng. Đừng dùng một subtype hợp lệ như `UserRegisteredEvent` làm default cho mọi type id lạ; điều đó có thể khiến payload sai bị diễn giải thành nghiệp vụ khác.

`defaultImpl` cũng không tự giữ nguyên toàn bộ JSON dưới dạng raw payload. Nếu cần lưu hoặc chuyển tiếp event chưa biết, tree model hoặc một DTO unknown có trường `JsonNode` sẽ thể hiện mục đích rõ hơn.

### 11.3. Không tắt lỗi rồi giả định dữ liệu đã được xử lý

Tắt `FAIL_ON_INVALID_SUBTYPE` có thể khiến trường hợp không giải quyết được subtype trả về null tùy ngữ cảnh. Điều này không tương đương với hỗ trợ unknown subtype. Nếu downstream không kiểm tra null, record có thể bị bỏ qua hoặc gây lỗi muộn.

Với dữ liệu mở rộng, một pattern rõ ràng là đọc envelope chung bằng `JsonNode`, kiểm tra discriminator theo allowlist, rồi chuyển payload đã biết thành DTO. Type id chưa biết được đưa vào luồng quarantine, lưu raw payload hoặc xử lý như unknown event theo policy.

## 12. Versioning và tương thích giá trị nghiệp vụ

Discriminator là một phần của wire contract. Khi đã phát hành, việc đổi giá trị có thể làm consumer cũ không đọc được payload mới.

Ví dụ ban đầu:

```json
{
  "eventType": "user.created",
  "data": {}
}
```

Sau này nhóm phát triển muốn đổi tên thành `account.registered`. Có ba cách thiết kế:

1. Giữ id cũ nếu ý nghĩa nghiệp vụ không thay đổi.
2. Chấp nhận cả tên cũ và mới trong giai đoạn chuyển đổi bằng mapping alias rõ ràng.
3. Nếu ngữ nghĩa thực sự thay đổi, tạo type id mới và version contract thay vì tái sử dụng id cũ cho một ý nghĩa khác.

Không nên đổi type id chỉ vì đổi tên class. Nếu `UserCreatedEvent` được refactor thành `AccountRegisteredEvent` nhưng ý nghĩa trên wire vẫn như cũ, có thể giữ `user.created` để tương thích consumer.

### 12.1. Alias cho tên cũ

Nếu phải chấp nhận nhiều giá trị cho cùng subtype, hãy định nghĩa alias ở ranh giới deserialization bằng resolver hoặc adapter được kiểm soát. Không giả định mọi cách khai báo lặp `@JsonSubTypes.Type` cho cùng class đều sẽ cho hành vi serialize mong muốn: một class chỉ nên có một tên canonical khi ghi ra.

Một chính sách rõ ràng:

- Canonical id dùng khi serialize.
- Alias cũ chỉ dùng khi deserialize.
- Có metric/log để biết producer nào còn gửi alias cũ.
- Có thời điểm loại bỏ alias sau khi migration hoàn tất.

### 12.2. Không tái sử dụng discriminator cho hai subtype

Một type id không được ánh xạ tới hai class khác nhau trong cùng phạm vi. Nếu `"created"` vừa có nghĩa `UserCreatedEvent` vừa có nghĩa `InvoiceCreatedEvent`, consumer không thể chọn subtype chính xác.

Dùng namespace nghiệp vụ như `user.created`, `invoice.created`, `order.shipped` để tránh xung đột và giúp quan sát log dễ hơn.

## 13. Đăng ký subtype tập trung và module hóa

Trong ứng dụng lớn, danh sách subtype có thể được quản lý tại composition root thay vì đặt hết trong annotation:

```java
ObjectMapper mapper = JsonMapper.builder()
        .build();

mapper.registerSubtypes(
        new NamedType(UserRegisteredEvent.class, "user.registered"),
        new NamedType(InvoicePaidEvent.class, "invoice.paid"),
        new NamedType(OrderShippedEvent.class, "order.shipped")
);
```

Nếu mỗi module nghiệp vụ sở hữu subtype riêng, có thể để module đó cung cấp một hàm đăng ký hoặc một `Module` Jackson. Điều này tránh để package trung tâm phụ thuộc vào mọi class cụ thể.

Tuy nhiên, cần có một registry được kiểm soát. Không nên quét toàn bộ classpath và tự động đăng ký mọi subtype tìm thấy nếu ứng dụng có plugin không đáng tin cậy. Việc đăng ký là một quyết định về loại dữ liệu mà boundary chấp nhận.

## 14. Bảo mật: tránh class-name type id từ JSON không tin cậy

Jackson hỗ trợ các lựa chọn type id như:

- `JsonTypeInfo.Id.NAME`: tên logic được đăng ký.
- `JsonTypeInfo.Id.CLASS`: tên class đầy đủ.
- `JsonTypeInfo.Id.MINIMAL_CLASS`: tên class rút gọn theo package context.
- `JsonTypeInfo.Id.CUSTOM`: resolver tùy chỉnh.

Với JSON từ HTTP client, webhook hoặc message broker bên ngoài, nên ưu tiên `Id.NAME` cùng danh sách subtype allowlist. Tránh bật default typing rộng hoặc dùng class-name type id chỉ vì tiện.

Lý do:

- Payload không nên điều khiển trực tiếp class Java mà ứng dụng khởi tạo.
- Tên class gắn với package và cấu trúc triển khai.
- Classpath thay đổi theo dependency có thể làm thay đổi tập class có thể được chọn.
- Polymorphic deserialization không an toàn có thể mở đường cho gadget chain nếu cấu hình cho phép khởi tạo kiểu nguy hiểm.

Nếu một hệ thống đặc thù bắt buộc dùng class-based type id, cần cấu hình `PolymorphicTypeValidator` theo allowlist package/type chặt chẽ và đánh giá kỹ dữ liệu đầu vào. Với hợp đồng nghiệp vụ thông thường, logical name dễ kiểm soát và bền vững hơn.

## 15. Phân biệt discriminator với enum property thông thường

Một field enum như:

```java
public enum PaymentMethodCode {
    CARD,
    BANK_TRANSFER,
    DIGITAL_WALLET
}
```

có thể mô tả phương thức thanh toán trong domain. Tuy nhiên, enum property thông thường không tự động khiến Jackson tạo subtype. Muốn giá trị đó chọn class polymorphic, cần liên kết nó với type id qua `@JsonTypeInfo`, subtype mapping hoặc custom deserializer.

Ví dụ:

```json
{
  "method": "bank_transfer",
  "bankCode": "VCB"
}
```

Nếu `method` chỉ được bind vào enum field, Jackson sẽ tạo class đã khai báo và gán enum. Nếu `method` là discriminator, Jackson dùng nó để chọn `BankTransferPayment`.

Có thể cùng lúc giữ property enum trong model, nhưng phải chọn rõ `As.EXISTING_PROPERTY` và quy tắc binding. Không nên tạo hai field có cùng tên hoặc hai nguồn dữ liệu không đồng bộ.

## 16. Validation sau khi subtype được chọn

Discriminator chỉ chọn loại object; nó không đảm bảo các field riêng của subtype hợp lệ.

Ví dụ `method = "bank_transfer"` có thể chọn đúng `BankTransferPayment`, nhưng `bankCode` vẫn thiếu hoặc `reference` rỗng. Cần validation riêng:

```java
public class BankTransferPayment extends PaymentMethod {
    @NotBlank
    private String bankCode;

    @NotBlank
    private String reference;

    // Getter/setter
}
```

Với Spring hoặc Bean Validation tích hợp, cần kích hoạt validation ở boundary, chẳng hạn `@Valid`. Nếu xử lý ngoài framework, gọi validator sau khi Jackson deserialize xong.

Cũng nên kiểm tra invariant giữa discriminator và subtype nếu dùng `visible = true` hoặc `EXISTING_PROPERTY`. Ví dụ, một object `CardPayment` không nên giữ field `method = "bank_transfer"`.

## 17. Ví dụ event domain dùng discriminator theo giá trị nghiệp vụ

Base event:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "eventType"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = UserRegisteredEvent.class, name = "user.registered"),
        @JsonSubTypes.Type(value = InvoicePaidEvent.class, name = "invoice.paid"),
        @JsonSubTypes.Type(value = OrderShippedEvent.class, name = "order.shipped")
})
public abstract class DomainEvent {
    private String eventId;
    private Instant occurredAt;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }

    public void setOccurredAt(Instant occurredAt) {
        this.occurredAt = occurredAt;
    }
}
```

Một subtype:

```java
public class UserRegisteredEvent extends DomainEvent {
    private String userId;
    private String email;

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

JSON:

```json
{
  "eventType": "user.registered",
  "eventId": "evt-900",
  "occurredAt": "2025-01-01T10:00:00Z",
  "userId": "U-100",
  "email": "an@example.test"
}
```

Đọc event:

```java
DomainEvent event = mapper.readValue(json, DomainEvent.class);

switch (event) {
    case UserRegisteredEvent registered ->
            handleUserRegistered(registered);
    case InvoicePaidEvent paid ->
            handleInvoicePaid(paid);
    case OrderShippedEvent shipped ->
            handleOrderShipped(shipped);
}
```

Trong ví dụ này, `eventType` là code nghiệp vụ độc lập với tên class. Class có thể được đổi tên hoặc chuyển package mà JSON không phải thay đổi, miễn mapping giữ nguyên.

Nếu ứng dụng cần đọc nhiều event trong một mảng:

```java
List<DomainEvent> events = mapper.readValue(
        json,
        new TypeReference<List<DomainEvent>>() {}
);
```

Mỗi phần tử có discriminator riêng, nên list có thể chứa nhiều subtype.

## 18. Kiểm thử contract của discriminator

Nên test cả hai chiều và các trường hợp sai.

### 18.1. Đọc đúng subtype

```java
@Test
void shouldResolveBusinessTypeIdToBankTransferSubtype() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    PaymentMethod payment = mapper.readValue(
            """
            {
              "method": "bank_transfer",
              "amount": 125000,
              "bankCode": "VCB",
              "reference": "TX-900"
            }
            """,
            PaymentMethod.class
    );

    assertInstanceOf(BankTransferPayment.class, payment);
    BankTransferPayment bank = (BankTransferPayment) payment;
    assertEquals("VCB", bank.getBankCode());
}
```

### 18.2. Serialize đúng logical id

Để test root polymorphic value, ghi qua declared base type:

```java
@Test
void shouldWriteStableBusinessTypeId() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    PaymentMethod payment = new BankTransferPayment();

    String json = mapper.writerFor(PaymentMethod.class)
            .writeValueAsString(payment);

    JsonNode root = mapper.readTree(json);

    assertEquals("bank_transfer", root.path("method").asText());
}
```

Test này giả định object đã được khởi tạo với các giá trị hợp lệ cần thiết. Điều quan trọng là kiểm tra wire value `bank_transfer`, không kiểm tra tên class Java.

### 18.3. Từ chối type id không được đăng ký

```java
@Test
void shouldRejectUnknownBusinessTypeId() {
    ObjectMapper mapper = new ObjectMapper();

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                    """
                    {
                      "method": "unknown_method",
                      "amount": 100
                    }
                    """,
                    PaymentMethod.class
            )
    );
}
```

Nếu contract có fallback, hãy viết test riêng để xác nhận unknown type được đưa đúng vào subtype dự phòng và không bị xử lý nhầm như một loại thanh toán đã biết.

### 18.4. Test các thay đổi contract

Ngoài test cơ bản, nên kiểm tra:

- Discriminator bị thiếu.
- Discriminator là null hoặc sai kiểu.
- Giá trị viết sai chính tả hoặc sai chữ hoa/thường.
- Giá trị alias cũ trong giai đoạn migration.
- Subtype đã biết nhưng thiếu field bắt buộc.
- Serialize root qua base type và serialize trong collection.
- Consumer cũ đọc payload mới hoặc ngược lại theo compatibility policy.

## 19. Checklist thiết kế discriminator

Khi đưa một trường phân biệt kiểu vào hợp đồng JSON:

1. **Chọn phạm vi nghiệp vụ:** payment method, event type, channel hay loại resource?
2. **Đặt tên field rõ nghĩa:** tránh trùng với property `type` khác trong payload.
3. **Chọn logical id ổn định:** `bank_transfer`, `user.registered`, `send_email`.
4. **Ánh xạ id tới subtype allowlist:** dùng `Id.NAME`, `@JsonSubTypes`, `@JsonTypeName` hoặc registry rõ ràng.
5. **Chọn vị trí discriminator:** `As.PROPERTY` nếu Jackson thêm field; `As.EXISTING_PROPERTY` nếu DTO đã có field; `As.EXTERNAL_PROPERTY` nếu schema đặt id cạnh object.
6. **Quyết định visible:** giữ mặc định false nếu type id chỉ là metadata; bật true nếu subtype cần nhận nó như property.
7. **Định nghĩa unknown policy:** từ chối, fallback hoặc xử lý raw payload có chủ đích.
8. **Bảo đảm canonical id:** mỗi subtype có một giá trị ghi ra ổn định; alias cũ chỉ phục vụ migration.
9. **Không dùng class name từ input không tin cậy:** tránh `Id.CLASS` và default typing rộng.
10. **Kiểm thử wire contract:** kiểm tra chính xác giá trị discriminator, subtype được tạo và các trường hợp thiếu/sai.

## 20. Kết luận

Trường phân biệt kiểu giúp Jackson chọn subtype khi một property hoặc root object có nhiều biến thể. Thiết kế bền vững là dùng một giá trị nghiệp vụ ổn định như `bank_transfer` hoặc `user.registered`, ánh xạ nó tới class Java bằng `JsonTypeInfo.Id.NAME` và danh sách subtype được kiểm soát. Nhờ đó, wire contract không bị phụ thuộc vào tên class hoặc package.

`As.PROPERTY` phù hợp khi Jackson tự thêm type id; `As.EXISTING_PROPERTY` phù hợp khi discriminator đã là property nghiệp vụ; `visible` quyết định type id có tiếp tục được binding vào object hay chỉ dùng để chọn subtype. Cần xác định rõ chính sách cho type id thiếu/không biết, giữ canonical id ổn định qua refactor và kiểm thử cả serialize lẫn deserialize. Với JSON từ bên ngoài, logical name allowlist an toàn và dễ bảo trì hơn class-name type id.

## Tài liệu tham khảo

- [Jackson Annotations — JsonTypeInfo API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeInfo.html)
- [Jackson Annotations — JsonSubTypes API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonSubTypes.html)
- [Jackson Annotations — JsonTypeName API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeName.html)
- [Jackson Databind — Polymorphic Deserialization](https://github.com/FasterXML/jackson-docs/wiki/JacksonPolymorphicDeserialization)
- [Jackson Databind — PolymorphicTypeValidator API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/jsontype/PolymorphicTypeValidator.html)

