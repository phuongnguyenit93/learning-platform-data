# Đăng ký `JsonSubTypes` hoặc kiểu con qua cấu hình module

Đa hình (polymorphism) trong JSON xuất hiện khi một property có kiểu khai báo là lớp cha hoặc interface, nhưng giá trị thực tế có thể thuộc nhiều lớp con. Ví dụ, một hệ thống thanh toán có thể nhận `CardPayment`, `BankTransferPayment` hoặc `CashPayment` thông qua cùng một property `payment` có kiểu Java là `Payment`.

Khi deserialize JSON thành kiểu cha, Jackson cần biết phải tạo lớp con nào. Khi serialize, Jackson cũng cần biết tên kiểu nào phải được ghi vào JSON để phía đọc có thể khôi phục đúng lớp con. Cơ chế phổ biến là dùng một **type discriminator** như `"kind": "card"` cùng với danh sách các subtype được phép.

Jackson hỗ trợ khai báo subtype ngay trên lớp cha bằng `@JsonSubTypes`, hoặc đăng ký các subtype bằng `NamedType` qua `SimpleModule`/`ObjectMapper`. Hai cách này giải quyết phần ánh xạ tên kiểu logic sang lớp Java. Cách biểu diễn discriminator thường được khai báo riêng bằng `@JsonTypeInfo`.

Các ví dụ trong bài dùng Jackson 2.x với package `com.fasterxml.jackson`. Hãy chọn một danh sách subtype rõ ràng, có tên wire ổn định và chỉ cho phép các kiểu mà ứng dụng chủ động hỗ trợ.

## 1. Bài toán đa hình khi deserialize

Giả sử có một lớp cha trừu tượng:

```java
public abstract class Payment {
    private String reference;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}
```

Hai lớp con biểu diễn hai cách thanh toán:

```java
public class CardPayment extends Payment {
    private String last4;

    public String getLast4() {
        return last4;
    }

    public void setLast4(String last4) {
        this.last4 = last4;
    }
}

public class BankTransferPayment extends Payment {
    private String bankCode;
    private String accountNumber;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public void setAccountNumber(String accountNumber) {
        this.accountNumber = accountNumber;
    }
}
```

Một request có thể khai báo:

```java
public class PaymentRequest {
    private String orderId;
    private Payment payment;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public Payment getPayment() {
        return payment;
    }

    public void setPayment(Payment payment) {
        this.payment = payment;
    }
}
```

JSON có thể chứa một trong các dạng:

```json
{
  "orderId": "ORD-100",
  "payment": {
    "kind": "card",
    "reference": "PAY-100",
    "last4": "4242"
  }
}
```

Hoặc:

```json
{
  "orderId": "ORD-101",
  "payment": {
    "kind": "bank_transfer",
    "reference": "PAY-101",
    "bankCode": "VCB",
    "accountNumber": "0123456789"
  }
}
```

Nếu chỉ gọi `readValue(json, PaymentRequest.class)` mà không cấu hình đa hình, Jackson biết property `payment` cần kiểu `Payment` nhưng không thể tự quyết định phải tạo `CardPayment` hay `BankTransferPayment`. Vì `Payment` là abstract, việc tạo instance trực tiếp không thể thực hiện.

## 2. Phân biệt `@JsonTypeInfo` và `@JsonSubTypes`

Hai annotation này thường được dùng cùng nhau nhưng có nhiệm vụ khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `@JsonTypeInfo` | Quy định cách thông tin kiểu được biểu diễn trong JSON và cách Jackson tìm type id |
| `@JsonSubTypes` | Liệt kê các lớp con được hỗ trợ và tên logic tương ứng |
| `@JsonTypeName` | Đặt tên logic mặc định cho một lớp con |
| `NamedType` | Đăng ký một lớp con cùng tên logic qua cấu hình Java/module |

Ví dụ, `@JsonTypeInfo` có thể quy định discriminator nằm trong property `kind`; `@JsonSubTypes` quy định `"card"` ánh xạ tới `CardPayment.class` và `"bank_transfer"` ánh xạ tới `BankTransferPayment.class`.

Chỉ khai báo `@JsonSubTypes` mà không có cơ chế polymorphic type information thì chưa đủ để Jackson biết khi nào phải đọc discriminator. Ngược lại, chỉ khai báo `@JsonTypeInfo` mà không có subtype mapping phù hợp thì Jackson có thể đọc được type id nhưng không biết lớp con nào được phép tạo.

## 3. Đăng ký lớp con bằng `@JsonSubTypes`

Cách trực tiếp nhất là đặt `@JsonTypeInfo` và `@JsonSubTypes` trên lớp cha hoặc interface:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
public abstract class Payment {
    private String reference;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}
```

Giải thích cấu hình:

- `use = JsonTypeInfo.Id.NAME`: JSON chứa tên logic do ứng dụng định nghĩa, không chứa tên class Java.
- `include = JsonTypeInfo.As.PROPERTY`: type id được ghi như một property trong JSON object.
- `property = "kind"`: tên field discriminator là `kind`.
- `@JsonSubTypes.Type(..., name = "card")`: type id `card` ánh xạ tới `CardPayment`.
- `@JsonSubTypes.Type(..., name = "bank_transfer")`: type id `bank_transfer` ánh xạ tới `BankTransferPayment`.

Tên `card` và `bank_transfer` là một phần hợp đồng JSON. Chúng nên ổn định ngay cả khi tên lớp Java thay đổi.

### 3.1. Deserialize thành lớp con tương ứng

```java
ObjectMapper mapper = new ObjectMapper();

PaymentRequest request = mapper.readValue(json, PaymentRequest.class);
Payment payment = request.getPayment();

if (payment instanceof CardPayment card) {
    System.out.println(card.getLast4());
} else if (payment instanceof BankTransferPayment transfer) {
    System.out.println(transfer.getBankCode());
}
```

Khi JSON có `"kind": "card"`, Jackson tạo `CardPayment`; khi có `"kind": "bank_transfer"`, Jackson tạo `BankTransferPayment`. Sau deserialize, property vẫn có kiểu khai báo là `Payment`, nhưng object thực tế là lớp con tương ứng.

### 3.2. Serialize object lớp con với type id

Khi `payment` là property có kiểu khai báo `Payment`, Jackson có thông tin polymorphic từ lớp cha:

```java
PaymentRequest request = new PaymentRequest();
request.setOrderId("ORD-100");

CardPayment card = new CardPayment();
card.setReference("PAY-100");
card.setLast4("4242");

request.setPayment(card);

String output = mapper.writeValueAsString(request);
```

Output có thể có dạng:

```json
{
  "orderId": "ORD-100",
  "payment": {
    "kind": "card",
    "reference": "PAY-100",
    "last4": "4242"
  }
}
```

Jackson ghi discriminator để phía nhận có thể khôi phục subtype. Thứ tự property trong JSON không nên được xem là cố định trừ khi hợp đồng quy định rõ.

## 4. Đăng ký tên kiểu bằng `@JsonTypeName`

Nếu muốn đặt tên logic ngay trên từng lớp con, có thể dùng `@JsonTypeName`:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public class CardPayment extends Payment {
    private String last4;

    public String getLast4() {
        return last4;
    }

    public void setLast4(String last4) {
        this.last4 = last4;
    }
}
```

```java
@JsonTypeName("bank_transfer")
public class BankTransferPayment extends Payment {
    private String bankCode;
    private String accountNumber;

    // getters và setters
}
```

Khi lớp cha đã khai báo `@JsonTypeInfo`, `@JsonTypeName` cung cấp tên logic cho subtype. Tuy nhiên, Jackson vẫn cần biết những lớp con nào thuộc hệ phân cấp đa hình. Có thể liệt kê chúng bằng `@JsonSubTypes` hoặc đăng ký qua module như phần tiếp theo.

Nếu `@JsonSubTypes.Type` đã khai báo `name` rõ ràng, việc thêm `@JsonTypeName` với cùng giá trị có thể bị lặp thông tin. Chọn một nguồn tên làm chuẩn và giữ nhất quán.

## 5. Đăng ký subtype qua `SimpleModule`

Trong dự án lớn, đôi khi không muốn lớp cha phụ thuộc trực tiếp vào các lớp con. Ví dụ, lớp `Payment` nằm trong module domain, còn các phương thức thanh toán được bổ sung bởi module tích hợp. Khi đó, có thể giữ `@JsonTypeInfo` trên lớp cha và đăng ký subtype trong cấu hình Jackson.

Lớp cha chỉ khai báo cách đọc discriminator:

```java
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
public abstract class Payment {
    private String reference;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}
```

Tạo module đăng ký các tên subtype:

```java
import com.fasterxml.jackson.databind.jsontype.NamedType;
import com.fasterxml.jackson.databind.module.SimpleModule;

public class PaymentSubtypeModule extends SimpleModule {
    public PaymentSubtypeModule() {
        super("payment-subtypes");

        registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransferPayment.class, "bank_transfer")
        );
    }
}
```

Đăng ký module với mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new PaymentSubtypeModule());
```

Khi deserialize `Payment`, Jackson sử dụng type id `kind` do `@JsonTypeInfo` quy định và tra tên trong subtype registry đã được module đăng ký.

### 5.1. Dùng `SimpleModule` trực tiếp mà không tạo lớp module riêng

Với cấu hình nhỏ, có thể tạo module tại nơi khởi tạo mapper:

```java
SimpleModule module = new SimpleModule("payment-subtypes");
module.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransferPayment.class, "bank_transfer")
);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Đây là cách phù hợp khi subtype list ngắn và chỉ thuộc một ứng dụng. Nếu danh sách được dùng ở nhiều nơi hoặc module đại diện cho một nhóm tích hợp riêng, tạo lớp `PaymentSubtypeModule` giúp cấu hình có tên và dễ tái sử dụng.

### 5.2. Đăng ký trực tiếp bằng `ObjectMapper.registerSubtypes()`

Không nhất thiết phải tạo `SimpleModule` chỉ để đăng ký subtype. `ObjectMapper` cũng cung cấp API trực tiếp:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransferPayment.class, "bank_transfer")
);
```

API này có cùng mục tiêu đăng ký các subtype được biết trước. Chọn `SimpleModule` khi muốn gom đăng ký subtype cùng các cấu hình module khác; dùng `ObjectMapper.registerSubtypes()` khi cấu hình đơn giản và được quản lý tập trung tại nơi tạo mapper.

**Lưu ý:** đăng ký subtype chỉ cung cấp ánh xạ lớp con. Nó không tự bật polymorphic typing cho mọi property. Kiểu cơ sở vẫn cần `@JsonTypeInfo`, annotation tương đương trên property, mix-in hoặc một cơ chế type resolver được cấu hình rõ ràng.

## 6. Đăng ký lớp con chỉ bằng `Class<?>` và `@JsonTypeName`

Nếu subtype tự khai báo tên qua `@JsonTypeName`, có thể đăng ký class mà không lặp tên trong `NamedType`:

```java
@JsonTypeName("card")
public class CardPayment extends Payment {
    // ...
}

@JsonTypeName("bank_transfer")
public class BankTransferPayment extends Payment {
    // ...
}
```

```java
SimpleModule module = new SimpleModule("payment-subtypes");
module.registerSubtypes(
        CardPayment.class,
        BankTransferPayment.class
);

mapper.registerModule(module);
```

Tên logic được lấy từ `@JsonTypeName`. Nếu không khai báo tên tường minh, Jackson có thể dùng tên lớp đơn giản làm tên mặc định tùy cấu hình/annotation discovery; không nên dựa vào tên mặc định đó làm wire contract lâu dài. Với API công khai, `NamedType(MySubtype.class, "stable-name")` hoặc `@JsonTypeName("stable-name")` giúp hợp đồng rõ ràng hơn.

## 7. So sánh đăng ký bằng annotation và module

| Tiêu chí | `@JsonSubTypes` trên lớp cha | `SimpleModule.registerSubtypes()` / `ObjectMapper.registerSubtypes()` |
|---|---|---|
| Nơi khai báo | Lớp cha/interface | Cấu hình Jackson |
| Phụ thuộc giữa module domain và lớp con | Lớp cha cần tham chiếu lớp con | Có thể giữ registry ở module cấu hình |
| Dễ đọc danh sách subtype | Rõ ngay tại base type | Rõ tại nơi khởi tạo mapper/module |
| Phù hợp | Hệ phân cấp nhỏ, ổn định | Ứng dụng/module có subtype mở rộng hoặc được lắp ghép theo cấu hình |
| Tên wire | `name` trong `@JsonSubTypes.Type` hoặc `@JsonTypeName` | `NamedType` hoặc `@JsonTypeName` |
| Cách bật type metadata | Vẫn cần `@JsonTypeInfo` hoặc cấu hình tương đương | Vẫn cần `@JsonTypeInfo` hoặc cấu hình tương đương |

Hai cách có thể được sử dụng trong cùng một ứng dụng, nhưng cần tránh đăng ký cùng type id theo nhiều nguồn với ý nghĩa không nhất quán. Nên có một nơi làm chuẩn cho mapping tên wire sang lớp Java.

## 8. Dùng subtype registration với interface

Đa hình không bắt buộc lớp cha phải là abstract class. Một interface cũng có thể là kiểu khai báo:

```java
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "eventType"
)
public interface DomainEvent {
}
```

Các event cụ thể:

```java
public class UserCreated implements DomainEvent {
    private Long userId;
    private String email;

    // getters và setters
}

public class OrderPlaced implements DomainEvent {
    private String orderId;
    private BigDecimal total;

    // getters và setters
}
```

Đăng ký:

```java
SimpleModule eventModule = new SimpleModule("domain-events");
eventModule.registerSubtypes(
        new NamedType(UserCreated.class, "user_created"),
        new NamedType(OrderPlaced.class, "order_placed")
);
mapper.registerModule(eventModule);
```

Deserialize:

```java
DomainEvent event = mapper.readValue(json, DomainEvent.class);
```

Jackson tạo implementation tương ứng với `eventType`. Đây là mẫu thường gặp trong event-driven architecture, nơi một topic có thể chứa nhiều loại event nhưng consumer cần một kiểu cha chung để xử lý.

## 9. Đa hình trong collection và generic wrapper

Nếu một array chứa nhiều subtype khác nhau, khai báo element type là lớp cha và giữ đầy đủ generic metadata:

```java
List<Payment> payments = mapper.readValue(
        json,
        new TypeReference<List<Payment>>() {}
);
```

JSON:

```json
[
  {
    "kind": "card",
    "reference": "PAY-1",
    "last4": "4242"
  },
  {
    "kind": "bank_transfer",
    "reference": "PAY-2",
    "bankCode": "VCB",
    "accountNumber": "0123456789"
  }
]
```

Mỗi phần tử được xử lý theo type id riêng. Kết quả là `List<Payment>` nhưng mỗi phần tử có runtime class tương ứng.

Với wrapper generic:

```java
ApiResponse<List<Payment>> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<List<Payment>>>() {}
);
```

Điều kiện là property generic bên trong wrapper phải được ánh xạ tới kiểu cơ sở `Payment` để Jackson áp dụng polymorphic type information. Dùng `ApiResponse.class` hoặc `List.class` sẽ làm mất thông tin generic cần thiết.

## 10. Kiểm soát vị trí discriminator bằng `JsonTypeInfo.As`

`include` quyết định type id được đặt ở đâu. Một số lựa chọn thường gặp:

| Cách include | Hình thức JSON minh họa | Khi phù hợp |
|---|---|---|
| `As.PROPERTY` | `{"kind":"card","last4":"4242"}` | Discriminator là một property của object |
| `As.EXISTING_PROPERTY` | Dùng property discriminator đã có trong subtype | Model đã có field `kind` và muốn dùng chính field đó |
| `As.WRAPPER_OBJECT` | `{"card":{"last4":"4242"}}` | Type id trở thành tên object bao quanh payload |
| `As.WRAPPER_ARRAY` | `["card",{"last4":"4242"}]` | Type id và payload được đóng thành array hai phần tử |
| `As.EXTERNAL_PROPERTY` | `{"paymentKind":"card","payment":{"last4":"4242"}}` | Discriminator nằm bên cạnh property đa hình trong object cha |

Ví dụ wrapper object:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.WRAPPER_OBJECT
)
public abstract class Payment {
    // ...
}
```

JSON có dạng:

```json
{
  "card": {
    "reference": "PAY-100",
    "last4": "4242"
  }
}
```

Khi chọn cách include, hãy xem xét schema mà hệ thống khác mong đợi. `As.PROPERTY` thường dễ đọc và tương thích với API object thông thường; wrapper phù hợp khi giao thức muốn type id tách khỏi các field của subtype.

### 10.1. `visible = true` có ý nghĩa gì?

Với `As.PROPERTY`, mặc định type id được Jackson dùng để chọn subtype rồi không chuyển tiếp như một property thông thường cho deserializer của lớp con. Nếu muốn property discriminator cũng được gán vào field của subtype, có thể đặt `visible = true`:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        visible = true
)
```

Chỉ bật `visible = true` nếu lớp con thực sự có property `kind` cần nhận giá trị. Nếu không, có thể để mặc định để tránh xử lý trùng hoặc tạo thêm property không cần thiết.

### 10.2. `As.EXISTING_PROPERTY`

Nếu mỗi subtype đã có property `kind`, có thể dùng chính property đó làm type id:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXISTING_PROPERTY,
        property = "kind",
        visible = true
)
```

Trong trường hợp này, subtype cần cung cấp property `kind` với giá trị tương ứng. Phải bảo đảm giá trị đó khớp với tên subtype registry; nếu property bị thiếu hoặc không khớp, quá trình đọc/ghi có thể thất bại hoặc tạo JSON không đúng hợp đồng.

## 11. Đặt type information ở lớp cha hay riêng property?

Thông thường, đặt `@JsonTypeInfo` trên base class/interface khi mọi lần sử dụng kiểu đó đều cần đa hình:

```java
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME,
              include = JsonTypeInfo.As.PROPERTY,
              property = "kind")
public abstract class Payment {
}
```

Nếu chỉ một property cần đa hình, có thể đặt annotation trên property:

```java
public class AuditRecord {
    private String id;

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "kind"
    )
    private Payment payment;

    // getters và setters
}
```

Subtype của `Payment` vẫn được đăng ký bằng `@JsonSubTypes` trên base type hoặc qua `NamedType` trong module. Đặt `@JsonTypeInfo` trên property giúp giới hạn cách sử dụng discriminator vào đúng vị trí này khi lớp cơ sở không cần polymorphic typing ở mọi nơi. Nếu cùng kiểu `Payment` được dùng ở nhiều nơi và đều có chung hợp đồng, đặt annotation trên base type sẽ tránh lặp cấu hình.

## 12. Dùng Mix-in khi không thể sửa lớp cha

Nếu base class thuộc thư viện bên ngoài hoặc generated code, có thể bổ sung `@JsonTypeInfo` bằng mix-in:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
abstract class PaymentMixin {
}
```

Đăng ký:

```java
mapper.addMixIn(Payment.class, PaymentMixin.class);
```

Hoặc mix-in chỉ đặt `@JsonTypeInfo`, còn subtype được đăng ký bằng `NamedType` trong module. Cách kết hợp này hữu ích khi muốn giữ lớp nguồn độc lập với Jackson nhưng vẫn kiểm soát đầy đủ type metadata trong ứng dụng.

## 13. Xử lý type id không nhận diện được

Khi JSON gửi một type id không nằm trong subtype registry, ví dụ:

```json
{
  "kind": "crypto_wallet",
  "reference": "PAY-999"
}
```

nhưng mapper chỉ đăng ký `card` và `bank_transfer`, Jackson thường báo lỗi invalid subtype/type id thay vì tự tạo một lớp tùy ý. Đây là hành vi nên giữ đối với input không tin cậy.

Có thể cấu hình `defaultImpl` trong `@JsonTypeInfo` để chọn một lớp fallback cho type id thiếu hoặc không hợp lệ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        defaultImpl = UnknownPayment.class
)
```

Chỉ dùng fallback nếu nghiệp vụ có một kiểu đại diện an toàn cho dữ liệu chưa biết. `UnknownPayment` cần được thiết kế để giữ hoặc từ chối dữ liệu phù hợp, không được vô tình biến một payment không nhận diện thành payment hợp lệ.

Một lựa chọn khác là giữ hành vi fail-fast và chuyển lỗi thành phản hồi API có kiểm soát. Với command hoặc payment request, từ chối subtype không biết thường an toàn hơn việc âm thầm gán một loại mặc định.

## 14. Đặt tên subtype ổn định và duy nhất

Tên subtype là một phần của JSON contract. Nên dùng tên logic ngắn, rõ nghĩa và không phụ thuộc package/class Java:

```text
card
bank_transfer
cash
```

Tránh dùng tên class đầy đủ như `com.example.payment.CardPayment` làm type id công khai. Nếu đổi package hoặc refactor tên class, payload đã lưu hoặc client cũ có thể không còn đọc được.

Các tên logic trong cùng một base type cần duy nhất. Không đăng ký hai lớp khác nhau dưới cùng một type id như `card`. Nếu cần đổi tên type id, có thể hỗ trợ alias đầu vào trong giai đoạn chuyển đổi bằng subtype registration tương ứng hoặc custom type resolver, nhưng cần quyết định rõ tên nào được ghi ra ở output mới.

Nên duy trì bảng mapping trong tài liệu hợp đồng:

| Type id JSON | Lớp Java | Trạng thái |
|---|---|---|
| `card` | `CardPayment` | Đang hỗ trợ |
| `bank_transfer` | `BankTransferPayment` | Đang hỗ trợ |
| `cash` | `CashPayment` | Đang hỗ trợ |

Không dùng tên hiển thị đã dịch theo locale làm discriminator. Type id cần ổn định giữa các ngôn ngữ và phiên bản ứng dụng.

## 15. Tránh dùng `Id.CLASS` hoặc default typing rộng cho JSON không tin cậy

Jackson hỗ trợ các kiểu type id khác ngoài `Id.NAME`, chẳng hạn `Id.CLASS` hoặc `Id.MINIMAL_CLASS`. Với `Id.CLASS`, JSON có thể mang tên class Java đầy đủ. Điều này gắn payload với cấu trúc code và có thể mở rộng bề mặt rủi ro nếu dữ liệu bên ngoài được quyền đề xuất class cần khởi tạo.

Đối với request từ client, message queue hoặc file do bên ngoài cung cấp, nên ưu tiên:

- `JsonTypeInfo.Id.NAME` với tên logic do ứng dụng kiểm soát.
- Danh sách subtype được đăng ký tường minh.
- Chỉ những lớp con thực sự được phép trong use case đó.
- Xử lý lỗi khi type id không hợp lệ hoặc không được nhận diện.

Không bật default typing toàn cục cho dữ liệu không tin cậy chỉ để giải quyết một property đa hình. Nếu một hệ thống thực sự cần polymorphic typing rộng, phải dùng `PolymorphicTypeValidator` chặt chẽ, giới hạn class được phép và đánh giá rủi ro theo version Jackson. Với phần lớn API, registry tên logic tường minh dễ kiểm soát hơn.

## 16. Đăng ký subtype theo ranh giới module của ứng dụng

Một ứng dụng có thể chia lớp cha và lớp con thành các module khác nhau:

```text
payment-domain
  └── Payment (abstract)

payment-card
  └── CardPayment

payment-bank
  └── BankTransferPayment

application-json
  └── PaymentSubtypeModule
```

Module cấu hình JSON có thể phụ thuộc vào các module subtype và đăng ký các lớp con được phép cho ứng dụng:

```java
public final class ApplicationJacksonConfiguration {
    public ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();

        SimpleModule paymentTypes = new SimpleModule("payment-types");
        paymentTypes.registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransferPayment.class, "bank_transfer")
        );

        mapper.registerModule(paymentTypes);
        return mapper;
    }
}
```

Ưu điểm của cách này là module domain không cần biết mọi implementation cụ thể. Ứng dụng quyết định subtype nào được bật bằng cách lắp ghép module tương ứng. Một triển khai không được đăng ký sẽ không nằm trong allowlist polymorphic của mapper đó.

Không nên đăng ký mọi implementation có thể tìm thấy trên classpath một cách tự động. Việc subtype nào được chấp nhận nên là quyết định cấu hình có chủ đích.

## 17. Đăng ký module trước khi sử dụng mapper

`ObjectMapper` có thể được tái sử dụng giữa nhiều luồng sau khi cấu hình hoàn tất. Vì vậy, hãy đăng ký module và subtype trong giai đoạn khởi tạo:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new PaymentSubtypeModule());

// Sau khi hoàn tất cấu hình, mới chia sẻ mapper cho ứng dụng.
```

Không nên thêm subtype vào mapper đang được nhiều request sử dụng như một cách thay đổi registry theo từng request. Nếu hai nhóm endpoint cần danh sách subtype khác nhau, tạo mapper/reader được cấu hình riêng hoặc đặt ranh giới type rõ ràng theo use case.

Nếu framework đã quản lý `ObjectMapper`, hãy đăng ký module qua cơ chế cấu hình của framework để mapper được dùng bởi HTTP message converter cũng nhận cùng subtype registry. Tạo một mapper mới trong service có thể khiến unit test chạy đúng nhưng request thực tế vẫn dùng mapper khác.

## 18. Kiểm thử cả chiều đọc và chiều ghi

Một bài test nên xác nhận:

1. Type id đúng tạo ra đúng lớp con.
2. Các field riêng của lớp con được ánh xạ.
3. Serialize qua kiểu cha ghi đúng type id logic.
4. Type id không được hỗ trợ bị từ chối theo chính sách.

Ví dụ JUnit 5:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class PaymentPolymorphismTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsCardSubtype() throws Exception {
        String json = """
                {
                  "kind": "card",
                  "reference": "PAY-100",
                  "last4": "4242"
                }
                """;

        Payment payment = mapper.readValue(json, Payment.class);

        CardPayment card = assertInstanceOf(CardPayment.class, payment);
        assertEquals("PAY-100", card.getReference());
        assertEquals("4242", card.getLast4());
    }

    @Test
    void writesLogicalTypeIdForBaseType() throws Exception {
        CardPayment card = new CardPayment();
        card.setReference("PAY-100");
        card.setLast4("4242");

        String json = mapper.writerFor(Payment.class)
                .writeValueAsString(card);

        assertEquals("card", mapper.readTree(json).path("kind").asText());
    }
}
```

Trong ví dụ này, mapper cần được tạo bằng annotation `@JsonSubTypes` như phần 3 hoặc đăng ký module như phần 5. `writerFor(Payment.class)` làm rõ kiểu khai báo ở root để Jackson áp dụng metadata đa hình của base type.

### 18.1. Kiểm thử module registration

Nếu subtype được đăng ký bằng module, test nên dùng đúng mapper factory của ứng dụng:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new PaymentSubtypeModule());

Payment payment = mapper.readValue(json, Payment.class);
```

Không chỉ kiểm tra module có được gọi `registerModule()` hay không. Cần kiểm tra JSON thực tế được deserialize thành đúng subtype và serialize ra đúng discriminator.

### 18.2. Kiểm thử type id lạ

```java
String unknown = """
        {
          "kind": "crypto_wallet",
          "reference": "PAY-999"
        }
        """;

assertThrows(JsonProcessingException.class,
        () -> mapper.readValue(unknown, Payment.class));
```

Kiểu exception cụ thể có thể là subtype của `JsonMappingException` tùy tình huống và version. Trong test chi tiết, có thể bắt exception Jackson cụ thể để kiểm tra nguyên nhân; ở tầng API, chuyển nó thành lỗi input có kiểm soát.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cannot construct instance of abstract class | Chỉ khai báo base type, chưa có polymorphic metadata | Thêm `@JsonTypeInfo` hoặc cấu hình type resolver |
| Could not resolve type id | Type id không có trong subtype registry | Đăng ký subtype đúng tên hoặc từ chối payload không hợp lệ |
| Có `@JsonSubTypes` nhưng vẫn không chọn được subtype | Thiếu `@JsonTypeInfo` hoặc discriminator không đúng property | Kiểm tra `use`, `include`, `property` và JSON input |
| Module đã đăng ký nhưng type id vẫn không được nhận diện | Mapper runtime không phải mapper đã đăng ký module | Đăng ký vào mapper thực sự được framework sử dụng |
| Serialize không có discriminator ở root | Root được serialize theo kiểu concrete thay vì base type hoặc metadata không nằm ở vị trí được áp dụng | Dùng `writerFor(BaseType.class)` hoặc bọc trong property có kiểu base |
| Type id thay đổi sau khi refactor package | Dùng `Id.CLASS` hoặc tên class mặc định | Dùng `Id.NAME` với tên wire tường minh |
| Lớp con không nhận property discriminator | `visible` mặc định là false | Bật `visible = true` nếu subtype cần field discriminator |
| Hai subtype cùng tên logic | Registry có type id trùng | Đặt tên duy nhất và kiểm soát mapping tại một nơi |
| Client có thể chọn subtype ngoài dự kiến | Registry quá rộng hoặc default typing không an toàn | Chỉ đăng ký subtype được phép cho use case |

## 20. Quy trình lựa chọn và cấu hình

Khi thiết kế một hierarchy đa hình, có thể đi theo trình tự:

1. Xác định kiểu cơ sở là abstract class hay interface và property nào cần đa hình.
2. Chọn tên discriminator ổn định, ví dụ `kind`, `eventType` hoặc `paymentType`.
3. Dùng `JsonTypeInfo.Id.NAME` để tách tên wire khỏi tên class Java.
4. Nếu subtype list nhỏ và cố định, khai báo `@JsonSubTypes` trên base type.
5. Nếu subtype được lắp ghép theo module hoặc base class không nên phụ thuộc lớp con, đăng ký `NamedType` qua `SimpleModule` hoặc `ObjectMapper.registerSubtypes()`.
6. Chỉ định rõ tên cho mỗi subtype; bảo đảm không trùng.
7. Đăng ký module trước khi mapper được chia sẻ.
8. Kiểm thử deserialize, serialize, collection generic và type id không hợp lệ.
9. Không bật default typing rộng hoặc cho phép class name tùy ý từ JSON không tin cậy.

## 21. Ghi nhớ

Đa hình trong Jackson cần cả cách biểu diễn type id và mapping type id sang lớp con. `@JsonTypeInfo` định nghĩa discriminator; `@JsonSubTypes` khai báo các subtype ngay trên base type; `NamedType` đăng ký subtype qua `SimpleModule` hoặc `ObjectMapper`. `@JsonTypeName` có thể đặt tên logic ngay trên lớp con.

Hãy dùng tên logic ổn định với `JsonTypeInfo.Id.NAME`, đăng ký đúng các lớp con được phép và cấu hình mapper trước khi sử dụng. Kiểm thử cả hai chiều serialize/deserialize, đặc biệt với root value, property lồng nhau và collection generic. Cách làm này giúp hệ thống mở rộng subtype có kiểm soát mà không buộc JSON contract phụ thuộc trực tiếp vào tên class Java.
