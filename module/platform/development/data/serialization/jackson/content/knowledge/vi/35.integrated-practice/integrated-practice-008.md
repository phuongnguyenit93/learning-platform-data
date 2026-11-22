# Thiết kế đa hình bằng tên kiểu nghiệp vụ được phép

Một API thường nhận dữ liệu thuộc nhiều biến thể nhưng cùng một nhóm nghiệp vụ. Ví dụ, một đơn hàng có thể được thanh toán bằng thẻ đã token hóa hoặc chuyển khoản; một hệ thống thông báo có thể gửi email, SMS hoặc push; một event có thể là `invoice.paid`, `user.created` hoặc `order.cancelled`.

Trong Java, các biến thể này thường được biểu diễn bằng một base class hoặc interface cùng nhiều subtype. Khi serialize/deserialize JSON, Jackson cần một dấu hiệu để biết object cụ thể thuộc subtype nào. Dấu hiệu đó là **type id** — một tên nhận diện kiểu được đặt trong hợp đồng dữ liệu.

Với dữ liệu từ client hoặc hệ thống bên ngoài, nên dùng những tên nghiệp vụ ổn định và chỉ cho phép một danh sách subtype đã được ứng dụng đăng ký. Ví dụ:

```json
{
  "kind": "card",
  "tokenReference": "tok_7f31",
  "lastFourDigits": "4242"
}
```

Giá trị `card` mô tả biến thể nghiệp vụ của phương thức thanh toán. Nó không tiết lộ package Java, không phụ thuộc tên class và không cho client quyền yêu cầu Jackson tạo một class bất kỳ. Jackson ánh xạ type id này tới subtype đã được allowlist trong cấu hình.

## 1. Bài toán đa hình khi đọc JSON

Giả sử một đơn hàng có property `paymentMethod`. Trong Java, property được khai báo bằng kiểu cha:

```java
public class OrderRequest {
    private PaymentMethod paymentMethod;

    public PaymentMethod getPaymentMethod() {
        return paymentMethod;
    }

    public void setPaymentMethod(PaymentMethod paymentMethod) {
        this.paymentMethod = paymentMethod;
    }
}
```

`PaymentMethod` có thể có nhiều subtype:

```java
public abstract class PaymentMethod {
    private String payerName;

    public String getPayerName() {
        return payerName;
    }

    public void setPayerName(String payerName) {
        this.payerName = payerName;
    }
}
```

```java
public class CardPayment extends PaymentMethod {
    private String tokenReference;
    private String lastFourDigits;
}
```

```java
public class BankTransfer extends PaymentMethod {
    private String bankCode;
    private String accountReference;
}
```

Khi Jackson đọc JSON vào `OrderRequest`, nó biết kiểu khai báo của `paymentMethod` là `PaymentMethod`. Vì `PaymentMethod` là abstract, Jackson không thể khởi tạo trực tiếp kiểu đó. Nếu không có type metadata hoặc cơ chế subtype khác, Jackson không biết nên tạo `CardPayment` hay `BankTransfer`.

JSON cần mang một type id:

```json
{
  "paymentMethod": {
    "kind": "card",
    "payerName": "An Nguyen",
    "tokenReference": "tok_7f31",
    "lastFourDigits": "4242"
  }
}
```

Jackson đọc `kind`, tra mapping subtype đã đăng ký và tạo `CardPayment`.

## 2. Dùng @JsonTypeInfo với Id.NAME

`@JsonTypeInfo` xác định cách Jackson đọc/ghi thông tin kiểu đa hình. Với API JSON, cấu hình thường dùng là `Id.NAME` kết hợp `As.PROPERTY`:

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
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public abstract class PaymentMethod {
    // Các property dùng chung...
}
```

Ý nghĩa các thuộc tính:

- `use = JsonTypeInfo.Id.NAME`: dùng tên logic đã đăng ký làm type id.
- `include = JsonTypeInfo.As.PROPERTY`: đưa type id vào một property trong JSON object.
- `property = "kind"`: tên property chứa type id.
- `@JsonSubTypes`: khai báo các subtype mà base type cho phép cùng tên nghiệp vụ tương ứng.

Khi deserialize, Jackson chỉ chấp nhận các type id đã biết cho `PaymentMethod`. `card` được ánh xạ tới `CardPayment`, còn `bank-transfer` được ánh xạ tới `BankTransfer`.

Ví dụ JSON cho chuyển khoản:

```json
{
  "kind": "bank-transfer",
  "payerName": "An Nguyen",
  "bankCode": "VCB",
  "accountReference": "acct_91ab"
}
```

Tên type id là một phần của API contract. Nó cần được thống nhất giữa client, service, message producer và consumer.

## 3. Đặt tên nghiệp vụ bằng @JsonTypeName

Có thể đặt type id trên từng subtype bằng `@JsonTypeName`:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public class CardPayment extends PaymentMethod {
    private String tokenReference;
    private String lastFourDigits;

    public String getTokenReference() {
        return tokenReference;
    }

    public void setTokenReference(String tokenReference) {
        this.tokenReference = tokenReference;
    }

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}
```

```java
@JsonTypeName("bank-transfer")
public class BankTransfer extends PaymentMethod {
    private String bankCode;
    private String accountReference;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getAccountReference() {
        return accountReference;
    }

    public void setAccountReference(String accountReference) {
        this.accountReference = accountReference;
    }
}
```

Base type có thể liệt kê class con mà không lặp lại tên:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(CardPayment.class),
        @JsonSubTypes.Type(BankTransfer.class)
})
public abstract class PaymentMethod {
}
```

Jackson lấy tên từ `@JsonTypeName` của subtype. Cách này hữu ích khi mỗi subtype tự sở hữu tên nghiệp vụ của nó. Cách khai báo tên ngay trong `@JsonSubTypes.Type(value = ..., name = ...)` cũng hợp lệ; hãy chọn một quy ước rõ ràng để tránh mapping tên bị phân tán hoặc trùng lặp.

Không nên dùng tên class Java như `CardPayment` làm hợp đồng nếu API cần ổn định qua refactor. Tên `card` có thể giữ nguyên dù class được đổi tên, chuyển package hoặc thay cách triển khai nội bộ.

## 4. Ví dụ hoàn chỉnh với ObjectMapper

Giả sử `PaymentMethod` đã có `@JsonTypeInfo` và subtype mapping như các phần trên. Ta có thể deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "paymentMethod": {
            "kind": "card",
            "payerName": "An Nguyen",
            "tokenReference": "tok_7f31",
            "lastFourDigits": "4242"
          }
        }
        """;

OrderRequest request = mapper.readValue(json, OrderRequest.class);

PaymentMethod method = request.getPaymentMethod();
System.out.println(method.getClass().getSimpleName()); // CardPayment
```

Có thể xử lý theo subtype:

```java
if (method instanceof CardPayment card) {
    System.out.println(card.getTokenReference());
} else if (method instanceof BankTransfer transfer) {
    System.out.println(transfer.getBankCode());
}
```

Pattern matching cho `instanceof` như ví dụ yêu cầu Java 16 trở lên. Với Java cũ hơn, kiểm tra kiểu rồi cast theo cách thông thường.

Khi serialize, Jackson có thể ghi type id cùng object:

```java
String output = mapper.writeValueAsString(request);
```

JSON sẽ có `kind: "card"` trong object `paymentMethod`, cùng các property của `CardPayment`.

Nếu serialize subtype trực tiếp ở root và muốn cố định declared type cho writer, có thể dùng:

```java
String output = mapper.writerFor(PaymentMethod.class)
        .writeValueAsString(method);
```

Điều này làm rõ rằng giá trị root được ghi theo hợp đồng của base type `PaymentMethod`.

## 5. Đăng ký subtype bằng NamedType

Không phải lúc nào cũng có thể sửa base class để thêm `@JsonSubTypes`. Ví dụ, base type thuộc thư viện ngoài, subtype được cung cấp bởi plugin hoặc ứng dụng muốn quản lý allowlist ở một cấu hình tập trung.

Jackson cho phép đăng ký subtype bằng `ObjectMapper.registerSubtypes()` và `NamedType`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);
```

Base type vẫn cần khai báo cách sử dụng type metadata:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
public abstract class PaymentMethod {
}
```

`NamedType` liên kết class Java với một tên logic. Cấu hình này hữu ích khi danh sách subtype được quyết định bởi ứng dụng lúc bootstrap.

### 5.1. Chỉ đăng ký subtype được phép

Hãy xem danh sách subtype như allowlist:

```java
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);
```

Không đăng ký một tập class được lấy trực tiếp từ input hoặc scan tùy tiện toàn bộ package rồi coi mọi class tìm thấy là subtype được phép. Module/plugin có thể bổ sung subtype, nhưng việc bổ sung phải đi qua cấu hình tin cậy và được xem xét như thay đổi API contract.

Đăng ký subtype nên diễn ra trong giai đoạn khởi tạo mapper, trước khi mapper được dùng đồng thời. Không thay đổi allowlist trên mapper dùng chung trong lúc request đang chạy.

## 6. Chọn một nguồn mapping rõ ràng

Có ba cách phổ biến để liên kết type id với subtype:

| Cách | Nơi khai báo | Khi phù hợp |
| --- | --- | --- |
| `@JsonSubTypes.Type(value = ..., name = ...)` | Base class/interface | Danh sách subtype nhỏ, cố định và có thể sửa base type |
| `@JsonTypeName("...")` | Từng subtype | Muốn subtype tự khai báo tên nghiệp vụ |
| `registerSubtypes(new NamedType(...))` | Cấu hình mapper | Base type bên thứ ba, plugin hoặc allowlist tập trung |

Các cơ chế có thể phối hợp, nhưng không nên để nhiều nơi khai báo cùng một tên theo những mapping khác nhau. Ví dụ, `card` không được lúc thì ánh xạ `CardPayment`, lúc lại ánh xạ một class khác tùy mapper hoặc module được đăng ký.

Một quy ước dễ bảo trì:

- Base type định nghĩa `@JsonTypeInfo`.
- Subtype dùng `@JsonTypeName` hoặc mapping tường minh trong một registry duy nhất.
- Bootstrap đăng ký subtype cho từng mapper.
- Test xác nhận tất cả type id công khai đều ánh xạ đúng một class.

## 7. Tên kiểu nghiệp vụ phải ổn định

Type id là dữ liệu trao đổi giữa các hệ thống. Hãy chọn tên theo khái niệm nghiệp vụ, không theo cách triển khai Java.

Nên dùng:

```text
card
bank-transfer
invoice.paid
user.created
email
sms
```

Tránh dùng:

```text
com.example.payment.CardPayment
CardPaymentV2Impl
org.company.internal.BankTransferStrategy
```

Tên nghiệp vụ ổn định giúp:

- Refactor class hoặc package mà không phá JSON contract.
- Nhiều ngôn ngữ lập trình cùng hiểu type id.
- Tài liệu API dễ đọc.
- Dễ quản lý tương thích giữa producer và consumer.
- Không làm lộ cấu trúc nội bộ của ứng dụng.

Nên quy định chính xác chữ hoa/thường, dấu phân cách và cách version hóa. Ví dụ `bank-transfer` và `BankTransfer` là hai type id khác nhau nếu mapping được khai báo như vậy. Không nên tự chuẩn hóa tên theo kiểu không rõ ràng ở runtime.

## 8. Không dùng Id.CLASS cho dữ liệu từ bên ngoài

Jackson có nhiều loại type id:

| `JsonTypeInfo.Id` | Giá trị nhận diện | Nhận xét |
| --- | --- | --- |
| `NAME` | Tên logic do ứng dụng đăng ký | Phù hợp cho hợp đồng API và allowlist subtype |
| `CLASS` | Tên đầy đủ class Java | Gắn JSON với package/class nội bộ; không phù hợp cho input không tin cậy |
| `MINIMAL_CLASS` | Tên class rút gọn theo package cơ sở | Vẫn phụ thuộc cấu trúc class/package |
| `DEDUCTION` | Suy subtype từ tập property có mặt | Không có discriminator tường minh và có thể mơ hồ |

Với API nhận JSON từ client, `Id.NAME` thường là lựa chọn dễ kiểm soát nhất. Client gửi một tên nghiệp vụ; Jackson chỉ ánh xạ tên đó tới class đã đăng ký.

`Id.CLASS` có thể khiến JSON chứa tên class đầy đủ. Điều này làm lộ chi tiết triển khai và khiến payload phụ thuộc package. Quan trọng hơn, nếu kết hợp với cơ chế polymorphic rộng hoặc default typing cho input không tin cậy, dữ liệu bên ngoài có thể tác động đến việc chọn kiểu Java được khởi tạo. Đây là bề mặt rủi ro không cần thiết cho API nghiệp vụ.

Không thay `Id.NAME` bằng `Id.CLASS` chỉ để khỏi phải khai báo danh sách subtype. Việc allowlist rõ ràng là một phần của thiết kế bảo mật và hợp đồng dữ liệu.

## 9. Tránh bật default typing rộng

Jackson có cơ chế default typing để thêm type metadata cho nhiều kiểu theo chính sách mapper. Đây là một tính năng rộng, không tương đương với việc khai báo một base type cụ thể có danh sách subtype được phép.

Với dữ liệu không tin cậy:

- Tránh bật default typing toàn cục chỉ để deserialize object graph đa hình.
- Không cho client cung cấp tên class Java tùy ý.
- Dùng `@JsonTypeInfo(use = Id.NAME)` trên base type cần đa hình.
- Đăng ký chính xác subtype hợp lệ.
- Nếu một ứng dụng thực sự cần default typing cho dữ liệu nội bộ, phải dùng validator/allowlist chặt chẽ theo API của phiên bản Jackson đang dùng và chỉ áp dụng cho dữ liệu tin cậy.

Một allowlist theo base type có phạm vi hẹp và dễ kiểm thử hơn một chính sách tự động áp dụng type metadata cho nhiều class trong toàn ứng dụng.

## 10. Type id chỉ chọn subtype, không cấp quyền nghiệp vụ

Nếu JSON gửi:

```json
{
  "kind": "bank-transfer",
  "bankCode": "VCB",
  "accountReference": "acct_91ab"
}
```

Jackson xác định object là `BankTransfer`. Điều này chỉ chứng minh type id nằm trong danh sách subtype đã biết. Nó không chứng minh:

- Người gửi được phép dùng phương thức thanh toán đó.
- Tài khoản ngân hàng thuộc người dùng hiện tại.
- Ngân hàng được hỗ trợ tại quốc gia/tenant hiện tại.
- Phương thức thanh toán đã được kích hoạt hoặc xác minh.
- Số tiền, trạng thái hoặc tài khoản đáp ứng quy tắc domain.

Sau deserialize, ứng dụng vẫn phải validation các field và kiểm tra authorization/domain trong service. Không dùng subtype hợp lệ như bằng chứng rằng thao tác nghiệp vụ được phép.

## 11. Xử lý type id không tồn tại hoặc không hợp lệ

Nếu JSON chứa type id chưa được đăng ký:

```json
{
  "kind": "crypto-wallet",
  "walletReference": "wallet_123"
}
```

Jackson không thể ánh xạ `crypto-wallet` tới subtype đã biết. Với cấu hình thông thường, quá trình deserialize báo lỗi type id không hợp lệ/không được giải quyết, thường là `InvalidTypeIdException`.

Đây là hành vi tốt cho API strict: dữ liệu có biến thể không được hỗ trợ sẽ bị từ chối rõ ràng thay vì âm thầm biến thành một class mặc định không phù hợp.

Có thể bật rõ ràng feature từ chối subtype không hợp lệ:

```java
mapper.enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
```

Hãy kiểm tra cấu hình thực tế vì feature có thể được thay đổi ở mapper/reader. Không nên tắt chỉ để request lạ không báo lỗi; nếu tắt, ứng dụng cần định nghĩa rõ cách xử lý giá trị không phân loại và tránh tiếp tục nghiệp vụ với object null hoặc trạng thái thiếu dữ liệu.

## 12. Cẩn trọng với defaultImpl

`@JsonTypeInfo` có thuộc tính `defaultImpl` để chỉ định lớp dự phòng trong một số trường hợp type id bị thiếu hoặc không được giải quyết:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        defaultImpl = UnknownPayment.class
)
```

Một `UnknownPayment` có thể hữu ích nếu hệ thống chỉ cần lưu giữ payload chưa biết để chuyển tiếp hoặc phân tích sau. Tuy nhiên, fallback có thể che giấu lỗi client gửi sai tên, typo hoặc producer đã phát hành type id mới mà consumer chưa hỗ trợ.

Không nên dùng một subtype mặc định có thể thực hiện thanh toán hoặc hành động nghiệp vụ. Nếu cần forward compatibility, hãy thiết kế một envelope riêng có `kind` dạng string và `payload` dạng `JsonNode`, rồi để tầng ứng dụng quyết định xử lý type id chưa biết. Cách này làm rõ rằng payload chưa được hiểu, thay vì giả vờ nó là một subtype nghiệp vụ đã biết.

Ví dụ envelope linh hoạt:

```java
public record EventEnvelope(
        String kind,
        JsonNode payload
) {
}
```

Consumer có thể lưu hoặc chuyển tiếp `payload` chưa biết mà không khởi tạo một implementation nghiệp vụ tùy tiện. Trước khi xử lý, vẫn phải kiểm tra `kind` có nằm trong allowlist của phiên bản consumer hay không.

## 13. visible quyết định type id có trở thành property thông thường không

Mặc định, type id được Jackson dùng để chọn subtype và không nhất thiết được chuyển tiếp thành một property Java bình thường.

Nếu subtype cần nhận giá trị `kind` như một field thông thường, có thể bật `visible = true`:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        visible = true
)
```

Khi `visible = true`, Jackson vẫn dùng `kind` để chọn subtype, đồng thời chuyển type id vào quá trình deserialize property. Subtype cần có property/accessor phù hợp nếu muốn lưu giá trị đó.

Chỉ bật `visible` khi domain object thực sự cần lưu discriminator. Nếu `kind` chỉ phục vụ chọn subtype, giữ mặc định thường giúp mô hình Java gọn hơn và tránh lưu hai nguồn thông tin có thể không đồng nhất.

## 14. Đặt đa hình ở base type hay property cụ thể

Đặt `@JsonTypeInfo` trên base class/interface khi mọi vị trí sử dụng kiểu đó đều cần cùng một hợp đồng discriminator:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
public abstract class PaymentMethod {
}
```

Nếu chỉ một property cần polymorphic handling, có thể đặt annotation ở property:

```java
public class AuditRecord {
    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "eventType"
    )
    @JsonSubTypes({
            @JsonSubTypes.Type(value = LoginEvent.class, name = "login"),
            @JsonSubTypes.Type(value = PaymentEvent.class, name = "payment")
    })
    private AuditEvent event;
}
```

Property-level hữu ích khi cùng một kiểu Java được dùng ở nhiều vị trí nhưng chỉ một vị trí cần type metadata hoặc cần discriminator khác. Hãy giữ cấu hình rõ ràng để người đọc biết allowlist áp dụng ở phạm vi nào.

## 15. Đa hình trong collection

Một collection khai báo bằng base type có thể chứa nhiều subtype:

```java
public class PaymentBatch {
    private List<PaymentMethod> methods;

    public List<PaymentMethod> getMethods() {
        return methods;
    }

    public void setMethods(List<PaymentMethod> methods) {
        this.methods = methods;
    }
}
```

JSON:

```json
{
  "methods": [
    {
      "kind": "card",
      "payerName": "An",
      "tokenReference": "tok_7f31",
      "lastFourDigits": "4242"
    },
    {
      "kind": "bank-transfer",
      "payerName": "Binh",
      "bankCode": "VCB",
      "accountReference": "acct_91ab"
    }
  ]
}
```

Khi đọc `PaymentBatch`, Jackson xử lý từng phần tử theo type id của nó. Mỗi phần tử phải có discriminator hợp lệ và subtype tương ứng phải được đăng ký.

Đừng chỉ kiểm tra collection không rỗng. Mỗi subtype có field riêng và cần validation riêng sau khi deserialize.

## 16. Đăng ký subtype qua Module

Trong ứng dụng nhiều module, có thể đóng gói subtype registry vào một `SimpleModule`:

```java
SimpleModule paymentModule = new SimpleModule("payment-types");
paymentModule.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(paymentModule);
```

Base type vẫn phải khai báo `@JsonTypeInfo` hoặc có cấu hình type resolver tương đương. Module chỉ đăng ký các subtype và tên tương ứng.

Nên gom registry vào một nơi có tên rõ ràng. Tránh để nhiều module độc lập đăng ký cùng một type id cho các class khác nhau. Nếu hệ thống cho phép plugin mở rộng subtype, plugin phải được tin cậy và đăng ký qua bootstrap có kiểm soát; không cho request runtime tự nạp class theo tên.

## 17. Version hóa tên kiểu nghiệp vụ

Type id có thể tồn tại lâu hơn một phiên bản class. Khi nghiệp vụ thay đổi, cần quyết định type id cũ có còn được hỗ trợ hay không.

Một số chiến lược:

### 17.1. Giữ type id ổn định khi thay đổi nội bộ

Nếu `card` vẫn có cùng ý nghĩa nghiệp vụ, có thể đổi class hoặc thêm field optional mà không đổi type id.

### 17.2. Thêm type id mới cho một biến thể nghiệp vụ khác

Nếu semantics thay đổi đáng kể, có thể thêm type id như `card-tokenized-v2` hoặc `instant-bank-transfer`. Không nên đổi ý nghĩa của `card` âm thầm nếu consumer cũ hiểu khác.

### 17.3. Duy trì alias trong giai đoạn chuyển tiếp

Có thể đăng ký hai tên cho cùng một subtype trong thời gian migration:

```java
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(CardPayment.class, "card-v1")
);
```

Việc hỗ trợ alias cần được ghi trong API contract và có kế hoạch loại bỏ. Khi serialize, ứng dụng cần một tên canonical duy nhất; đừng để output thay đổi tùy ngẫu nhiên theo alias đầu vào.

### 17.4. Consumer cũ gặp type id mới

Consumer cũ có thể từ chối type id mới. Đây thường là lựa chọn an toàn cho nghiệp vụ cần xử lý chính xác. Nếu consumer phải forward payload chưa biết, dùng envelope giữ `kind` và raw `JsonNode` thay vì fallback vào một subtype nghiệp vụ không tương thích.

## 18. Validation theo subtype

Sau khi Jackson chọn subtype, Bean Validation có thể kiểm tra constraint trên class cụ thể. Ví dụ:

```java
public class CardPayment extends PaymentMethod {
    @NotBlank
    private String tokenReference;

    @Pattern(regexp = "\\d{4}")
    private String lastFourDigits;
}
```

```java
public class BankTransfer extends PaymentMethod {
    @NotBlank
    private String bankCode;

    @NotBlank
    private String accountReference;
}
```

Trong DTO chứa payment:

```java
public class OrderRequest {
    @NotNull
    @Valid
    private PaymentMethod paymentMethod;
}
```

Khi Bean Validation chạy trên `OrderRequest`, `@Valid` cascade vào instance subtype thực tế và áp dụng constraint tương ứng. Jackson chỉ chọn class; Bean Validation mới kiểm tra các field của class đó.

Các kiểm tra như token thuộc người dùng hiện tại, bank code được phép hoặc payment method đang hoạt động vẫn cần service/domain logic. Không đặt toàn bộ authorization vào constraint annotation.

## 19. Không đưa bí mật thanh toán vào ví dụ hoặc payload đa hình

Một subtype thanh toán không nên nhận số thẻ đầy đủ, CVV hoặc dữ liệu xác thực nhạy cảm chỉ vì JSON cho phép một field có tên như vậy. Hãy dùng token/reference do payment provider cấp và xử lý dữ liệu nhạy cảm theo yêu cầu bảo mật riêng.

Ví dụ tốt hơn:

```json
{
  "kind": "card",
  "tokenReference": "tok_7f31",
  "lastFourDigits": "4242"
}
```

Type id `card` chọn biến thể nghiệp vụ. `tokenReference` tham chiếu credential đã được quản lý ở hệ thống thanh toán; `lastFourDigits` chỉ phục vụ hiển thị nếu chính sách cho phép. Không đưa PAN/CVV vào DTO log hoặc error sample.

## 20. Unknown type id và forward compatibility

Khi API cần từ chối mọi biến thể không biết, hãy để Jackson báo lỗi type id và chuyển lỗi thành response phù hợp. Khi hệ thống cần tiếp nhận event mới để lưu hoặc forward, không nên tự tạo class dựa trên tên do producer gửi.

Một cách thiết kế envelope:

```java
public record IncomingEvent(
        String kind,
        JsonNode data,
        String schemaVersion
) {
}
```

Service kiểm tra:

```java
switch (event.kind()) {
    case "invoice.paid" -> handleInvoicePaid(
            mapper.treeToValue(event.data(), InvoicePaidData.class)
    );
    case "user.created" -> handleUserCreated(
            mapper.treeToValue(event.data(), UserCreatedData.class)
    );
    default -> storeForLaterOrReject(event);
}
```

Nhánh default phải có chính sách rõ: từ chối, đưa vào queue chờ phiên bản consumer mới hoặc lưu payload đã giới hạn để điều tra. Không chuyển tiếp payload không biết tới một handler có quyền thực hiện nghiệp vụ chỉ vì nó đã deserialize thành envelope.

## 21. Bảo vệ mapper và registry subtype

`ObjectMapper` nên được cấu hình hoàn chỉnh trước khi chia sẻ cho nhiều request:

```java
public final class JacksonConfiguration {
    public static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransfer.class, "bank-transfer")
        );

        mapper.enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
        return mapper;
    }
}
```

Không thay đổi danh sách subtype trên mapper dùng chung sau khi ứng dụng đã bắt đầu xử lý request. Nếu một integration cần allowlist khác, hãy tạo mapper riêng được cấu hình trước hoặc dùng base type/envelope riêng.

Không cho plugin không tin cậy đăng ký class vào mapper đang xử lý request công khai. Registry subtype là một phần của ranh giới tin cậy của ứng dụng.

## 22. Kiểm thử allowlist và type id

Hãy kiểm tra cả hai chiều:

- Serialize subtype tạo đúng tên nghiệp vụ.
- Deserialize type id hợp lệ tạo đúng subtype.
- Type id không được đăng ký bị từ chối.
- Thiếu type id bị xử lý theo chính sách đã định.
- Chữ hoa/thường hoặc dấu phân cách không đúng bị từ chối nếu contract phân biệt.
- Collection chứa nhiều subtype hợp lệ được đọc đúng.
- Subtype mới không vô tình xuất hiện chỉ vì thêm một class vào classpath.
- Mapper production có đúng registry như mapper trong test.

Ví dụ test JUnit:

```java
@Test
void readsOnlyRegisteredPaymentTypes() throws Exception {
    String json = """
            {
              "kind": "card",
              "payerName": "An",
              "tokenReference": "tok_7f31",
              "lastFourDigits": "4242"
            }
            """;

    PaymentMethod method = mapper.readValue(json, PaymentMethod.class);
    assertInstanceOf(CardPayment.class, method);
}

@Test
void rejectsUnknownPaymentType() {
    String json = """
            {
              "kind": "arbitrary-class-name",
              "value": "x"
            }
            """;

    assertThrows(
            InvalidTypeIdException.class,
            () -> mapper.readValue(json, PaymentMethod.class)
    );
}
```

Tùy phiên bản Jackson và API overload, exception có thể được bọc bởi exception mapping cấp cao hơn. Trong test tích hợp, có thể kiểm tra cause hoặc loại exception gốc thay vì phụ thuộc vào thông điệp đầy đủ.

## 23. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thể khởi tạo abstract base type | Thiếu `@JsonTypeInfo` hoặc type id | Khai báo discriminator và subtype registry |
| `InvalidTypeIdException` | Type id thiếu hoặc không có trong allowlist | Kiểm tra tên `kind`, `@JsonSubTypes`, `@JsonTypeName`, `NamedType` |
| Tên type id thay đổi sau refactor | Dùng class name thay tên nghiệp vụ | Dùng `Id.NAME` và id ổn định |
| Module mới khiến subtype không còn được nhận diện | Mapper/registry thực tế khác test hoặc mapping trùng | Kiểm tra bootstrap và đăng ký subtype tập trung |
| JSON serialize không có discriminator | Giá trị được ghi theo kiểu concrete hoặc đường serialize không dùng base type metadata | Kiểm tra annotation và dùng writer theo base type khi cần |
| Type id được chọn nhưng field không lưu vào DTO | `visible` mặc định false | Bật `visible = true` nếu subtype cần property đó |
| Consumer cũ không đọc type id mới | Producer phát hành subtype chưa được consumer hỗ trợ | Version hóa contract hoặc dùng envelope forward-compatible |
| Subtype hợp lệ nhưng request vẫn không được phép | Nhầm type id với authorization | Kiểm tra quyền và domain sau deserialize |

## 24. Quy trình thiết kế đa hình bằng tên nghiệp vụ

1. Xác định base type hoặc interface đại diện cho nhóm nghiệp vụ.
2. Liệt kê các biến thể thực sự được phép trong API.
3. Đặt type id ngắn, ổn định và có ý nghĩa nghiệp vụ cho từng subtype.
4. Cấu hình `@JsonTypeInfo(use = Id.NAME, include = As.PROPERTY, property = "kind")` trên base type hoặc property cụ thể.
5. Đăng ký subtype qua `@JsonSubTypes`, `@JsonTypeName` hoặc `NamedType` trong bootstrap.
6. Không nhận class name từ JSON và không bật default typing rộng cho input không tin cậy.
7. Quy định rõ hành vi khi type id thiếu hoặc không được hỗ trợ.
8. Version hóa type id và duy trì alias trong thời gian migration nếu cần.
9. Validate field của subtype sau deserialize và kiểm tra domain/authorization riêng.
10. Test type id hợp lệ, không hợp lệ, thiếu, collection nhiều subtype và output serialization.

## 25. Ghi nhớ

- Đa hình JSON cần type id để Jackson chọn subtype khi property được khai báo bằng base class/interface.
- `@JsonTypeInfo` định nghĩa cơ chế type metadata; `Id.NAME` dùng tên logic được đăng ký.
- `As.PROPERTY` đặt discriminator trong object JSON, ví dụ `kind`.
- `@JsonSubTypes` liệt kê subtype được phép; `@JsonTypeName` đặt tên nghiệp vụ trên subtype; `NamedType` đăng ký mapping bằng code.
- Chọn một nguồn mapping rõ ràng và tránh để cùng type id trỏ tới các class khác nhau.
- Type id nên ổn định theo nghiệp vụ, không phụ thuộc package hoặc tên class Java.
- Với input không tin cậy, ưu tiên allowlist `Id.NAME`; tránh `Id.CLASS`, `MINIMAL_CLASS` và default typing rộng.
- Type id chỉ chọn implementation; nó không chứng minh người gửi có quyền dùng subtype hoặc thao tác nghiệp vụ.
- Type id không biết thường nên bị từ chối; chỉ dùng fallback nếu có mô hình forward-compatible rõ ràng.
- `visible = true` chuyển type id vào property binding thông thường; mặc định type id chỉ phục vụ chọn subtype.
- `@Valid` có thể cascade vào subtype thực tế; validation và authorization vẫn là bước riêng sau deserialize.
- Đăng ký subtype trước khi mapper được chia sẻ; không cho input hoặc plugin không tin cậy tự nạp class.
- Kiểm thử cả type id được chấp nhận, type id bị từ chối và tên được serialize ra.

Thiết kế đa hình an toàn bắt đầu từ hợp đồng nghiệp vụ: mỗi biến thể có một tên nhận diện ổn định, và ứng dụng chỉ ánh xạ những tên đã được phê duyệt tới các subtype cụ thể. Với `JsonTypeInfo.Id.NAME` cùng danh sách allowlist rõ ràng, Jackson có thể đọc nhiều biến thể trong cùng một base type mà không buộc JSON phụ thuộc cấu trúc class nội bộ hoặc cho phép client chọn kiểu Java tùy ý.
