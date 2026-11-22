# Ánh xạ hệ phân cấp có lớp trừu tượng hoặc interface

Trong Java, một API thường khai báo kiểu dữ liệu theo lớp trừu tượng hoặc interface để các thành phần có thể làm việc với nhiều implementation. Ví dụ, một hệ thống thanh toán có thể nhận `Payment`, nhưng object thực tế là `CardPayment` hoặc `BankTransfer`. Khi serialize thành JSON, Jackson cần biểu diễn đủ thông tin để consumer biết object thuộc subtype nào. Khi deserialize, Jackson cần chọn đúng class cụ thể để tạo object.

Đây là bài toán **polymorphic deserialization** (deserialize đa hình). Jackson giải quyết bằng thông tin kiểu (type information) và cơ chế đăng ký subtype. Với hợp đồng JSON trao đổi giữa các hệ thống, cách thường dùng là gán một type ID có ý nghĩa nghiệp vụ như `"card"` hoặc `"bank-transfer"`, rồi ánh xạ ID đó đến các class được phép.

## 1. Vì sao abstract class hoặc interface cần type information?

Một interface không thể được khởi tạo trực tiếp:

```java
public interface Payment {
    BigDecimal amount();
}

public record CardPayment(
        String cardNumber,
        BigDecimal amount
) implements Payment {
}

public record BankTransfer(
        String bankCode,
        String accountNumber,
        BigDecimal amount
) implements Payment {
}
```

Khi ứng dụng có biến kiểu `Payment`, biến đó có thể tham chiếu đến một `CardPayment` hoặc `BankTransfer`. Nếu JSON chỉ chứa các field chung như `amount`, Jackson không thể biết phải tạo implementation nào.

Ví dụ JSON thiếu thông tin subtype:

```json
{
  "amount": 1250.75
}
```

Đối với kiểu đích `Payment`, dữ liệu này chưa đủ để chọn class cụ thể. Jackson cần một type discriminator hoặc một quy tắc khác để xác định subtype.

Type discriminator thường là một field như `type`:

```json
{
  "type": "card",
  "cardNumber": "****1234",
  "amount": 1250.75
}
```

Jackson đọc `type`, tra subtype đã đăng ký và deserialize phần còn lại thành `CardPayment`.

## 2. Khai báo subtype bằng @JsonTypeInfo và @JsonSubTypes

`@JsonTypeInfo` xác định cách type information được biểu diễn trong JSON. `@JsonSubTypes` khai báo những class cụ thể có thể được chọn và type ID tương ứng.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface Payment {
    BigDecimal amount();
}
```

Các lựa chọn trong annotation:

- `use = JsonTypeInfo.Id.NAME`: dùng một tên logic do ứng dụng định nghĩa làm type ID.
- `include = JsonTypeInfo.As.PROPERTY`: ghi type ID như một field trong JSON object.
- `property = "type"`: tên field chứa type ID.
- `@JsonSubTypes.Type`: liên kết type ID với class Java cụ thể.

Các record subtype không cần tự khai báo lại `@JsonTypeInfo`:

```java
public record CardPayment(
        String cardNumber,
        BigDecimal amount
) implements Payment {
}

public record BankTransfer(
        String bankCode,
        String accountNumber,
        BigDecimal amount
) implements Payment {
}
```

Jackson dùng metadata trên base interface `Payment` để xử lý giá trị được khai báo theo kiểu `Payment`.

## 3. Serialize và deserialize qua kiểu base

Khi serialize, ứng dụng có thể giữ biến theo interface nhưng object runtime là subtype cụ thể:

```java
ObjectMapper mapper = new ObjectMapper();

Payment payment = new CardPayment(
        "****1234",
        new BigDecimal("1250.75")
);

ObjectWriter paymentWriter = mapper.writerFor(Payment.class);
String json = paymentWriter.writeValueAsString(payment);
```

Với cấu hình trên, output có dạng:

```json
{
  "type": "card",
  "cardNumber": "****1234",
  "amount": 1250.75
}
```

Khi deserialize, phải yêu cầu Jackson đọc theo kiểu base để cơ chế đa hình được áp dụng:

```java
Payment restored = mapper.readValue(json, Payment.class);

if (restored instanceof CardPayment card) {
    System.out.println(card.cardNumber());
}
```

Jackson đọc type ID `card`, chọn `CardPayment` rồi tạo instance tương ứng. Biến nhận kết quả có kiểu khai báo `Payment`, nhưng object thực tế là `CardPayment`.

Với root value, dùng `writerFor(Payment.class)` giúp khai báo rõ kiểu base mà writer cần serialize. Trong DTO, nếu property được khai báo là `Payment`, Jackson cũng có kiểu khai báo để áp dụng type metadata:

```java
public record PaymentRequest(String requestId, Payment payment) {
}
```

Khi serialize `PaymentRequest`, property `payment` vẫn mang type information theo cấu hình của `Payment`.

## 4. Ánh xạ một hệ phân cấp dùng abstract class

Không chỉ interface, abstract class cũng có thể làm base type:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = EmailNotification.class, name = "email"),
        @JsonSubTypes.Type(value = SmsNotification.class, name = "sms")
})
public abstract class Notification {
    private final String recipient;

    protected Notification(String recipient) {
        this.recipient = recipient;
    }

    public String getRecipient() {
        return recipient;
    }
}
```

Các subtype:

```java
public class EmailNotification extends Notification {
    private final String subject;

    @JsonCreator
    public EmailNotification(
            @JsonProperty("recipient") String recipient,
            @JsonProperty("subject") String subject
    ) {
        super(recipient);
        this.subject = subject;
    }

    public String getSubject() {
        return subject;
    }
}

public class SmsNotification extends Notification {
    private final String phoneNumber;

    @JsonCreator
    public SmsNotification(
            @JsonProperty("recipient") String recipient,
            @JsonProperty("phoneNumber") String phoneNumber
    ) {
        super(recipient);
        this.phoneNumber = phoneNumber;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }
}
```

Ví dụ JSON:

```json
{
  "kind": "email",
  "recipient": "ops@example.test",
  "subject": "Deployment complete"
}
```

Khi đọc thành `Notification.class`, Jackson chọn `EmailNotification`. Constructor creator giúp khởi tạo class bất biến có field `final`; nếu class dùng constructor mặc định và setter, có thể dùng mô hình mutable tương ứng.

## 5. Chọn type ID có ý nghĩa ổn định

`JsonTypeInfo.Id.NAME` cho phép dùng tên logic như `card`, `bank-transfer`, `email` hoặc `sms`. Tên này là một phần của JSON contract, vì vậy nên ổn định và không phụ thuộc tên package/class Java.

Có thể khai báo subtype ngay trong `@JsonSubTypes`, hoặc dùng `@JsonTypeName` trên subtype kết hợp đăng ký subtype:

```java
@JsonTypeName("card")
public record CardPayment(
        String cardNumber,
        BigDecimal amount
) implements Payment {
}
```

Đăng ký subtype bằng mapper:

```java
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);
```

Các import liên quan:

```java
import com.fasterxml.jackson.databind.jsontype.NamedType;
```

Chọn một cơ chế quản lý subtype rõ ràng. Nếu đã khai báo đầy đủ trong `@JsonSubTypes`, thường không cần đăng ký lại cùng các subtype ở nơi khác. Đăng ký bằng mapper phù hợp khi class nằm trong module/plugin riêng hoặc ứng dụng muốn tập trung cấu hình subtype.

Không nên dùng tên class Java hoặc package làm type ID công khai nếu không có yêu cầu đặc biệt. Tên class có thể đổi khi refactor hoặc di chuyển package, làm hỏng payload đã lưu và consumer bên ngoài. Tên logic giúp tách hợp đồng JSON khỏi cấu trúc mã nguồn.

## 6. Các cách đưa type information vào JSON

`JsonTypeInfo.As` xác định vị trí type ID trong JSON. Lựa chọn ảnh hưởng trực tiếp đến hình dạng payload.

### 6.1. PROPERTY: type ID là một field trong object

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
```

JSON:

```json
{
  "type": "card",
  "cardNumber": "****1234",
  "amount": 1250.75
}
```

Đây là dạng dễ đọc và thường phù hợp cho REST API. Type ID nằm cùng object với các thuộc tính nghiệp vụ.

### 6.2. EXISTING_PROPERTY: dùng property đã có trong subtype

Nếu mỗi subtype đã có một property chứa loại của nó, có thể dùng `As.EXISTING_PROPERTY` để Jackson sử dụng property đó làm type ID:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXISTING_PROPERTY,
        property = "type",
        visible = true
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardEvent.class, name = "card"),
        @JsonSubTypes.Type(value = CashEvent.class, name = "cash")
})
public interface PaymentEvent {
    String getType();
}
```

Subtype có thể cung cấp giá trị property:

```java
public record CardEvent(
        String cardNumber,
        BigDecimal amount
) implements PaymentEvent {
    @Override
    @JsonProperty("type")
    public String getType() {
        return "card";
    }
}
```

`EXISTING_PROPERTY` phù hợp khi `type` thực sự là một phần của model. `visible = true` yêu cầu type ID được giữ lại trong luồng property để có thể bind vào thuộc tính subtype nếu cần. Nếu type ID chỉ phục vụ lựa chọn subtype và không cần gán vào object, có thể để `visible` mặc định là `false`.

Không nên khai báo type property vừa được tạo tự động vừa có một property khác cùng tên với giá trị mâu thuẫn. Hãy kiểm soát một nguồn giá trị duy nhất cho discriminator.

### 6.3. WRAPPER_OBJECT: subtype nằm trong tên field bao ngoài

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.WRAPPER_OBJECT
)
```

JSON có dạng:

```json
{
  "card": {
    "cardNumber": "****1234",
    "amount": 1250.75
  }
}
```

Tên property ngoài cùng là type ID. Dạng này gọn và phân biệt subtype rõ, nhưng một số consumer có thể thấy khó đọc hơn field `type` thông thường.

### 6.4. WRAPPER_ARRAY: type ID là phần tử đầu của array

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.WRAPPER_ARRAY
)
```

JSON:

```json
[
  "card",
  {
    "cardNumber": "****1234",
    "amount": 1250.75
  }
]
```

Dạng này thể hiện type ID rõ nhưng không trực quan bằng object property với nhiều API consumer.

### 6.5. EXTERNAL_PROPERTY: type ID nằm cạnh property chứa object

`EXTERNAL_PROPERTY` đặt type ID ở object cha, bên cạnh property có giá trị đa hình. Nó thường được khai báo trên property cụ thể:

```java
public class PaymentEnvelope {
    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
            property = "paymentType"
    )
    @JsonSubTypes({
            @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
            @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
    })
    private Payment payment;

    // Getter/setter hoặc constructor phù hợp.
}
```

JSON:

```json
{
  "paymentType": "card",
  "payment": {
    "cardNumber": "****1234",
    "amount": 1250.75
  }
}
```

Type ID nằm cùng cấp với field `payment`. Cách này hữu ích khi schema muốn giữ object subtype sạch, còn discriminator được đặt ở envelope. `EXTERNAL_PROPERTY` phụ thuộc ngữ cảnh property của object cha và không phải lựa chọn tổng quát cho mọi root value hoặc mọi cấu trúc lồng nhau.

## 7. visible: type ID có được bind như property thông thường không?

Với `include = As.PROPERTY`, Jackson mặc định dùng discriminator để chọn subtype và loại nó khỏi quá trình bind property thông thường. Vì vậy, nếu subtype cũng có field `type`, field đó có thể không nhận giá trị discriminator trừ khi bật `visible = true`.

Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type",
        visible = true
)
```

Chọn `visible = true` khi model cần lưu lại type ID trong một property. Nếu type chỉ là metadata điều khiển deserialize, giữ mặc định `false` thường đơn giản hơn và tránh lặp thông tin trong model.

## 8. Id.NAME, Id.CLASS và các chiến lược chọn subtype

`JsonTypeInfo.Id` quyết định giá trị được dùng để nhận diện subtype.

| Chiến lược | Ý nghĩa | Khi nào cân nhắc |
|---|---|---|
| `NAME` | Tên logic được đăng ký, ví dụ `card` | Hợp đồng API, message event, dữ liệu lưu trữ lâu dài |
| `CLASS` | Tên class đầy đủ gồm package | Chỉ trong môi trường nội bộ được kiểm soát chặt và có lý do tương thích |
| `MINIMAL_CLASS` | Tên class rút gọn tương đối theo package base | Trường hợp nội bộ đặc thù; phụ thuộc cấu trúc package |
| `DEDUCTION` | Suy subtype từ tập hợp tên property | Schema subtype có field phân biệt rõ, không muốn discriminator tường minh |
| `CUSTOM` | Resolver do ứng dụng định nghĩa | Cần quy tắc type ID riêng |

Với dữ liệu từ client, queue, file hoặc hệ thống bên ngoài, `Id.NAME` thường là lựa chọn dễ kiểm soát nhất. Ứng dụng chỉ ánh xạ những ID đã đăng ký đến class được cho phép.

`Id.CLASS` và `Id.MINIMAL_CLASS` đưa tên class vào payload. Nếu dữ liệu không đáng tin cậy có thể điều khiển class được khởi tạo, rủi ro deserialization gadget và thực thi hành vi ngoài dự kiến tăng lên. Không bật default typing rộng hoặc chấp nhận class name tùy ý từ JSON không tin cậy.

### 8.1. Dùng Id.DEDUCTION

Từ Jackson 2.12, có thể dùng `Id.DEDUCTION` để chọn subtype dựa trên tập hợp tên property đặc trưng, không cần field type ID:

```java
@JsonTypeInfo(use = JsonTypeInfo.Id.DEDUCTION)
@JsonSubTypes({
        @JsonSubTypes.Type(CardPayment.class),
        @JsonSubTypes.Type(BankTransfer.class)
})
public interface Payment {
}
```

Ví dụ, `CardPayment` có field `cardNumber`, còn `BankTransfer` có `bankCode` và `accountNumber`. Jackson có thể dùng các property này để suy subtype.

`DEDUCTION` có giới hạn: nếu các subtype có tập property không đủ khác biệt, Jackson không thể chọn duy nhất một subtype và sẽ báo lỗi mơ hồ. Cấu trúc cũng trở nên nhạy cảm với việc thêm/bớt field. Với API công khai hoặc message contract cần ổn định, discriminator tường minh như `type` thường dễ bảo trì hơn.

## 9. Đăng ký subtype tập trung bằng ObjectMapper

Không phải lúc nào ứng dụng cũng muốn đặt `@JsonSubTypes` trên source class. Có thể đăng ký subtype khi cấu hình mapper:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);
```

Nếu base type có `@JsonTypeInfo(use = Id.NAME, ...)`, mapper dùng tên đã đăng ký để resolve subtype. Cách đăng ký tập trung hữu ích khi:

- Base interface thuộc thư viện mà ứng dụng không thể sửa.
- Subtype được cung cấp bởi module/plugin.
- Ứng dụng muốn kiểm soát allowlist ở một nơi.
- Cùng một base type có các subtype được phép khác nhau theo cấu hình triển khai.

Hãy hoàn tất đăng ký module/subtype trước khi mapper bắt đầu được dùng và không thay đổi cấu hình mapper dùng chung theo từng request.

## 10. Xử lý type ID không xác định

Nếu JSON có type ID mà mapper không biết, Jackson thường ném `InvalidTypeIdException` (một dạng lỗi ánh xạ type ID). Ví dụ:

```json
{
  "type": "crypto-wallet",
  "address": "..."
}
```

Nếu `crypto-wallet` chưa được đăng ký, Jackson không thể tự suy ra class phù hợp. Đây thường là hành vi an toàn: payload không hợp lệ theo contract sẽ bị từ chối.

Có thể khai báo `defaultImpl` trong `@JsonTypeInfo` để dùng class mặc định khi thiếu hoặc không resolve được type ID trong những trường hợp được cấu hình:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type",
        defaultImpl = UnknownPayment.class
)
```

`defaultImpl` cần được thiết kế cẩn thận. Nếu payload không biết type ID mà vẫn được ánh xạ vào một class mặc định, ứng dụng có thể vô tình chấp nhận dữ liệu không hiểu hoặc làm mất thông tin subtype. Với nghiệp vụ thanh toán hoặc quyền truy cập, từ chối type không biết thường an toàn và rõ ràng hơn.

Không dùng `defaultImpl` như cách che lỗi contract. Nếu cần tương thích forward với subtype mới, hãy định nghĩa rõ `UnknownPayment` lưu giữ dữ liệu chưa biết ra sao, có được xử lý nghiệp vụ không và có thể serialize lại không.

## 11. Xử lý type ID bị thiếu

Nếu `@JsonTypeInfo` yêu cầu discriminator nhưng JSON không có field đó, Jackson thường không thể chọn subtype và báo lỗi. Đây là điều nên mong đợi khi abstract/interface base không có implementation mặc định.

Có một số lựa chọn:

- Bắt buộc sender gửi type ID theo contract.
- Dùng `defaultImpl` nếu một fallback cụ thể thực sự hợp lệ.
- Dùng `Id.DEDUCTION` nếu schema subtype có thể phân biệt chắc chắn bằng property.
- Tách endpoint hoặc envelope thành các kiểu cụ thể nếu không cần polymorphic payload.

Không nên đoán subtype theo thứ tự khai báo hoặc theo một field ngẫu nhiên không được định nghĩa trong contract.

## 12. Đa hình trong collection và object lồng nhau

Khi một collection khai báo phần tử theo base type, mỗi phần tử có thể là subtype khác nhau. Type information phải được cấu hình trên base type hoặc property tương ứng.

Ví dụ:

```java
public record BatchRequest(List<Payment> payments) {
}
```

JSON:

```json
{
  "payments": [
    {
      "type": "card",
      "cardNumber": "****1234",
      "amount": 1250.75
    },
    {
      "type": "bank-transfer",
      "bankCode": "VCB",
      "accountNumber": "0012345678",
      "amount": 500.00
    }
  ]
}
```

Jackson xử lý từng phần tử theo type ID riêng và tạo danh sách chứa các object subtype tương ứng:

```java
BatchRequest batch = mapper.readValue(json, BatchRequest.class);

for (Payment payment : batch.payments()) {
    switch (payment) {
        case CardPayment card -> processCard(card);
        case BankTransfer transfer -> processTransfer(transfer);
    }
}
```

Pattern matching trong `switch` phụ thuộc phiên bản Java; nếu project chưa hỗ trợ, dùng chuỗi `instanceof` hoặc visitor pattern.

Điểm quan trọng: generic type của collection phải giữ được base type `Payment`. Nếu đọc thành raw `List.class`, Jackson không có đủ thông tin kiểu phần tử để áp dụng polymorphic mapping như mong đợi.

## 13. Đa hình với generic wrapper

Một API thường bọc payload trong envelope generic:

```java
public record ApiResponse<T>(
        String requestId,
        T data
) {
}
```

Nếu `T` là `Payment`, hãy cung cấp kiểu generic đầy đủ khi deserialize:

```java
JavaType paymentResponseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, Payment.class);

ApiResponse<Payment> response = mapper.readValue(
        json,
        paymentResponseType
);
```

Jackson biết `data` có kiểu khai báo `Payment`, vì vậy áp dụng type information của interface để chọn subtype. Nếu chỉ truyền `ApiResponse.class`, tham số generic `Payment` bị mất và payload có thể được đọc thành kiểu tổng quát như `Map`.

## 14. Bảo mật khi deserialize đa hình

Polymorphic deserialization cần được thiết kế như một allowlist các kiểu có thể được tạo. JSON có thể điều khiển type ID, nên nếu mapper cho phép class tùy ý, input không tin cậy có thể khiến ứng dụng khởi tạo các kiểu ngoài dự kiến.

Các nguyên tắc quan trọng:

1. Ưu tiên `JsonTypeInfo.Id.NAME` với danh sách subtype được đăng ký rõ.
2. Không dùng `Id.CLASS` hoặc `Id.MINIMAL_CLASS` cho dữ liệu không tin cậy nếu không có kiểm soát chặt chẽ.
3. Không bật default typing rộng cho mọi object trong mapper nhận dữ liệu từ client hoặc queue.
4. Nếu phải dùng default typing cho một hệ thống nội bộ, cấu hình `PolymorphicTypeValidator` với allowlist package/type hẹp và hiểu rõ các class được phép.
5. Không lấy tên class từ request rồi gọi `Class.forName` hoặc deserialize tùy ý.
6. Kiểm tra type ID, field và giá trị theo schema/nghiệp vụ sau khi chọn subtype.
7. Giới hạn độ sâu, kích thước input và số lượng phần tử phù hợp với hệ thống.

Ví dụ, type ID `card` chỉ nên ánh xạ đến `CardPayment` đã được đăng ký. Không cho payload gửi `com.example.SomeUnexpectedClass` rồi yêu cầu Jackson nạp class đó.

`Id.NAME` không tự làm toàn bộ dữ liệu an toàn. Một subtype đã đăng ký vẫn có thể chứa field nhạy cảm hoặc logic nguy hiểm nếu model được thiết kế không đúng. Hãy giữ allowlist hẹp, dùng DTO cho input và tránh deserialize trực tiếp domain object có side effect.

## 15. Abstract type mapping không phải polymorphic type ID

Jackson cũng có `AbstractTypeResolver` hoặc `SimpleAbstractTypeResolver` để ánh xạ một abstract type sang implementation cụ thể. Cơ chế này khác với polymorphic type ID.

Ví dụ mapping một interface luôn sang một implementation:

```java
SimpleModule module = new SimpleModule();
module.addAbstractTypeMapping(Notifier.class, EmailNotifier.class);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Cách này phù hợp khi ứng dụng có một implementation mặc định cố định cho một abstract type. Nó không tự phân biệt nhiều subtype dựa trên nội dung JSON. Nếu cùng một interface có thể nhận `EmailNotifier`, `SmsNotifier` hoặc `PushNotifier` tùy payload, cần polymorphic type information hoặc logic lựa chọn subtype riêng.

Phân biệt:

| Cơ chế | Cách chọn implementation |
|---|---|
| `@JsonTypeInfo` + subtype registration | Dựa trên discriminator hoặc chiến lược type ID trong JSON |
| `SimpleAbstractTypeResolver` | Ánh xạ abstract type sang một implementation cụ thể đã cấu hình |
| Custom deserializer | Ứng dụng tự đọc dữ liệu và quyết định class theo quy tắc riêng |

Không dùng abstract type mapping một-một khi contract thực sự cần nhiều subtype theo từng record.

## 16. Dùng custom deserializer khi quy tắc chọn subtype đặc thù

Trong một số hệ thống cũ, discriminator không nằm ở một field đơn giản, hoặc việc chọn subtype phụ thuộc nhiều field kết hợp. Khi đó, custom deserializer có thể phù hợp.

Một custom deserializer cho base type thường thực hiện:

1. Đọc payload thành `JsonNode` hoặc buffer token.
2. Lấy các field điều khiển.
3. Kiểm tra chúng theo allowlist.
4. Chọn một class cụ thể.
5. Delegate deserialize phần payload sang mapper/reader phù hợp.

Ví dụ khái niệm:

```java
JsonNode node = parser.getCodec().readTree(parser);
String kind = node.path("kind").asText();

Class<? extends Message> target = switch (kind) {
    case "created" -> CreatedMessage.class;
    case "deleted" -> DeletedMessage.class;
    default -> throw JsonMappingException.from(
            parser,
            "Unsupported message kind: " + kind
    );
};

return codec.treeToValue(node, target);
```

Đây là đoạn minh họa logic chọn subtype, không phải một custom deserializer hoàn chỉnh để sao chép nguyên trạng. Khi triển khai thật, cần tránh gọi lại chính deserializer đang xử lý base type theo cách gây recursion; có thể dùng `ObjectReader` cho subtype hoặc delegate phù hợp. Cần giữ parser context và xử lý lỗi rõ ràng.

Nếu `@JsonTypeInfo` và `@JsonSubTypes` đã giải quyết được contract, nên ưu tiên cấu hình khai báo thay vì custom deserializer để giảm code và dễ bảo trì.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Cannot construct instance of abstract type` | Không có type info hoặc abstract mapping phù hợp | Thêm discriminator và đăng ký subtype, hoặc đọc bằng kiểu cụ thể |
| `InvalidTypeIdException` | Type ID thiếu hoặc không được đăng ký | Kiểm tra JSON discriminator và allowlist subtype |
| Deserialize luôn thành một class không mong muốn | Dùng raw type, defaultImpl hoặc abstract mapping một-một | Kiểm tra declared type và cơ chế chọn subtype |
| Field discriminator không xuất hiện trong object | `visible` mặc định là false | Bật `visible = true` nếu model cần bind field đó |
| Type ID bị ghi trùng hoặc mâu thuẫn | Vừa tạo type property tự động vừa khai báo property cùng tên | Chọn PROPERTY hoặc EXISTING_PROPERTY và một nguồn giá trị duy nhất |
| `Id.DEDUCTION` báo mơ hồ | Các subtype có tập property không đủ khác biệt | Thêm discriminator tường minh hoặc thiết kế schema rõ hơn |
| Payload cũ không đọc được sau refactor | Dùng class name/package làm type ID | Dùng logical name ổn định và chiến lược migration |
| Rủi ro khi nhận JSON ngoài | Cho phép class ID/default typing quá rộng | Dùng `Id.NAME`, subtype allowlist và validation |

## 18. Quy trình thiết kế hệ phân cấp đa hình

Khi một property hoặc root value có kiểu abstract/interface, hãy thực hiện theo trình tự:

1. Xác định base type và các implementation hợp lệ.
2. Chọn type ID logic ổn định cho từng subtype.
3. Khai báo `@JsonTypeInfo` trên base type hoặc property phù hợp.
4. Đăng ký subtype bằng `@JsonSubTypes`, `@JsonTypeName` kết hợp mapper registration hoặc module tập trung.
5. Chọn cách đưa discriminator vào JSON: PROPERTY, EXISTING_PROPERTY, EXTERNAL_PROPERTY hoặc wrapper.
6. Quyết định có cần `visible = true` để bind discriminator vào model hay không.
7. Deserialize bằng kiểu base đầy đủ, kể cả khi nằm trong collection hoặc generic wrapper.
8. Xác định hành vi khi type ID thiếu/không biết; từ chối là mặc định an toàn trong nhiều API.
9. Giữ allowlist subtype hẹp và tránh class-name polymorphism cho dữ liệu không tin cậy.
10. Viết test cho từng subtype, unknown ID, missing ID, nested collection và round-trip serialize/deserialize.

## 19. Ví dụ test cho nhiều subtype

Một test có thể xác nhận Jackson giữ đúng subtype qua hai chiều:

```java
@Test
void readsAndWritesPaymentSubtypes() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Payment original = new CardPayment(
            "****1234",
            new BigDecimal("1250.75")
    );

    String json = mapper.writerFor(Payment.class)
            .writeValueAsString(original);

    assertTrue(json.contains("\"type\":\"card\""));

    Payment restored = mapper.readValue(json, Payment.class);

    assertInstanceOf(CardPayment.class, restored);
    assertEquals(original, restored);
}
```

Nên có thêm test cho `BankTransfer`, collection `List<Payment>`, generic wrapper, type ID không biết và type ID bị thiếu. Nếu dùng `EXISTING_PROPERTY`, `EXTERNAL_PROPERTY` hoặc `DEDUCTION`, hãy test đúng hình dạng JSON tương ứng.

Với dữ liệu không tin cậy, test bảo đảm type ID lạ bị từ chối và không thể chọn class ngoài allowlist. Nếu contract cần `defaultImpl`, test rõ fallback chỉ được dùng trong trường hợp đã định nghĩa.

## 20. Ghi nhớ

Jackson ánh xạ abstract class hoặc interface bằng polymorphic type information: JSON cung cấp type ID, mapper tra subtype đã đăng ký và tạo class cụ thể. `@JsonTypeInfo` quy định chiến lược và vị trí type ID; `@JsonSubTypes`, `@JsonTypeName` hoặc `ObjectMapper.registerSubtypes(...)` liên kết ID với implementation.

Với API và dữ liệu bên ngoài, ưu tiên `JsonTypeInfo.Id.NAME` cùng allowlist subtype và discriminator ổn định. Chọn inclusion phù hợp với schema, hiểu `visible`, xử lý type ID thiếu/không biết rõ ràng, và giữ generic base type khi đọc collection hoặc wrapper. Tránh class-name polymorphism và default typing rộng trên dữ liệu không tin cậy. Nếu chỉ cần một implementation cố định, abstract type mapping có thể đủ; nếu có nhiều subtype theo payload, dùng type ID hoặc custom deserializer có kiểm soát.
