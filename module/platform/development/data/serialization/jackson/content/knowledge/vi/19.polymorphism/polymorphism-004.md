# Cấu hình JsonTypeInfo và đăng ký kiểu con

Trong mô hình hướng đối tượng, một thuộc tính có thể được khai báo bằng kiểu cha hoặc interface nhưng object thực tế lại thuộc nhiều kiểu con khác nhau. Ví dụ, một đơn hàng có thể chứa phương thức thanh toán là thẻ ngân hàng, chuyển khoản hoặc ví điện tử. Khi serialize thành JSON, Jackson cần ghi đủ thông tin để bên đọc biết object đó thuộc kiểu con nào. Khi deserialize, Jackson cần dùng thông tin đó để tạo đúng lớp Java.

Jackson giải quyết bài toán này bằng **polymorphic type handling**. Annotation `@JsonTypeInfo` quy định cách đưa thông tin kiểu vào JSON hoặc cách đọc thông tin kiểu từ JSON. Các subtype có thể được khai báo bằng `@JsonSubTypes`, `@JsonTypeName` hoặc đăng ký trực tiếp với `ObjectMapper` thông qua `NamedType`.

Phần quan trọng là hai phía phải thống nhất discriminator (trường nhận diện kiểu) và danh sách subtype được phép. Với dữ liệu từ API bên ngoài, nên dùng tên logic ổn định như `card` hoặc `bank-transfer`, thay vì phụ thuộc vào tên class Java.

## 1. Vì sao cần thông tin kiểu khi deserialize?

Giả sử ứng dụng có kiểu cha `PaymentMethod` và hai kiểu con:

```java
public abstract class PaymentMethod {
    private String accountHolder;

    public String getAccountHolder() {
        return accountHolder;
    }

    public void setAccountHolder(String accountHolder) {
        this.accountHolder = accountHolder;
    }
}
```

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
```

```java
public class BankTransfer extends PaymentMethod {
    private String bankCode;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }
}
```

Một thuộc tính khai báo kiểu `PaymentMethod` không cho biết Jackson nên tạo `CardPayment` hay `BankTransfer`:

```java
public class Order {
    private PaymentMethod paymentMethod;

    public PaymentMethod getPaymentMethod() {
        return paymentMethod;
    }

    public void setPaymentMethod(PaymentMethod paymentMethod) {
        this.paymentMethod = paymentMethod;
    }
}
```

Nếu JSON chỉ có:

```json
{
  "paymentMethod": {
    "accountHolder": "An",
    "lastFourDigits": "1234"
  }
}
```

Jackson thấy kiểu đích là `PaymentMethod`. Vì đây là kiểu trừu tượng, Jackson không thể tự suy ra subtype chỉ từ tên trường `lastFourDigits` một cách đáng tin cậy. Cần có thông tin kiểu rõ ràng, ví dụ:

```json
{
  "paymentMethod": {
    "kind": "card",
    "accountHolder": "An",
    "lastFourDigits": "1234"
  }
}
```

Ở đây `kind` là **type id** hoặc **discriminator**. Giá trị `card` cho Jackson biết phải tạo `CardPayment`.

## 2. Cấu hình @JsonTypeInfo với Id.NAME

`@JsonTypeInfo` định nghĩa cách xử lý type metadata. Một cấu hình thường dùng cho API là:

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
    // Các thuộc tính chung...
}
```

Trong cấu hình này:

- `use = JsonTypeInfo.Id.NAME`: sử dụng tên logic để nhận diện subtype.
- `include = JsonTypeInfo.As.PROPERTY`: ghi type id thành một property trong JSON object.
- `property = "kind"`: tên property chứa type id.
- `@JsonSubTypes`: liệt kê các lớp con được phép cùng tên type id tương ứng.

Khi serialize một `CardPayment` qua kiểu khai báo `PaymentMethod`, JSON có dạng:

```json
{
  "kind": "card",
  "accountHolder": "An",
  "lastFourDigits": "1234"
}
```

Khi deserialize JSON vào `PaymentMethod.class`, Jackson đọc `kind`, tìm subtype đã đăng ký với tên `card`, rồi tạo `CardPayment`.

Tên `card` là một phần của hợp đồng dữ liệu. Bạn có thể đổi tên class Java hoặc chuyển package mà không cần đổi JSON, miễn là giữ mapping type id `card` với subtype tương ứng.

## 3. Vai trò của @JsonSubTypes và @JsonTypeName

`@JsonTypeInfo` quy định cơ chế đa hình, còn `@JsonSubTypes` cung cấp danh sách các subtype cùng tên nhận diện của chúng.

Có thể đặt tên subtype ngay trong `@JsonSubTypes.Type` như ví dụ trước. Một cách khác là đặt tên trên từng subtype bằng `@JsonTypeName`:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public class CardPayment extends PaymentMethod {
    // Các thuộc tính riêng của thẻ...
}
```

```java
@JsonTypeName("bank-transfer")
public class BankTransfer extends PaymentMethod {
    // Các thuộc tính riêng của chuyển khoản...
}
```

Khi đó, base type có thể khai báo danh sách lớp con:

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

`@JsonTypeName` cung cấp tên logic mặc định cho subtype. Nếu muốn hợp đồng rõ ràng và dễ đọc tại một chỗ, có thể khai báo tên ngay trong `@JsonSubTypes.Type`. Không cần lặp lại hai cách đặt tên nếu dự án đã chọn một quy ước nhất quán.

## 4. Đăng ký subtype bằng ObjectMapper và NamedType

Không phải lúc nào cũng có thể sửa source code của base class hoặc subtype để thêm annotation. Ví dụ, các lớp thuộc thư viện bên thứ ba, module plugin hoặc mô hình domain cần giữ độc lập với Jackson.

Trong trường hợp đó, có thể đăng ký subtype theo chương trình:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransfer.class, "bank-transfer")
);
```

Base type vẫn cần cấu hình `@JsonTypeInfo` hoặc cấu hình tương đương để Jackson biết cần dùng type metadata:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
public abstract class PaymentMethod {
}
```

`NamedType` liên kết một class với một type id. Khi mapper xử lý `PaymentMethod`, các tên đã đăng ký giúp Jackson tìm subtype phù hợp.

Nên đăng ký subtype trong giai đoạn khởi tạo mapper, trước khi mapper được chia sẻ cho các request. Tránh thay đổi tập subtype của mapper dùng chung trong lúc ứng dụng đang chạy.

### 4.1. So sánh các cách khai báo subtype

| Cách khai báo | Nơi đặt mapping | Phù hợp khi |
| --- | --- | --- |
| `@JsonSubTypes.Type(value = ..., name = ...)` | Trên base type | Có thể sửa base class và muốn thấy danh sách subtype ngay tại mô hình |
| `@JsonTypeName("...")` | Trên subtype | Muốn subtype tự khai báo tên logic của chính nó |
| `mapper.registerSubtypes(new NamedType(...))` | Cấu hình mapper | Không thể sửa class hoặc muốn quản lý subtype tập trung |
| `mapper.registerSubtypes(Subtype.class)` | Cấu hình mapper | Chấp nhận quy tắc tên mặc định từ metadata/class; nên cân nhắc tên ổn định rõ ràng cho API |

Các cách này có thể phối hợp trong hệ sinh thái Jackson, nhưng nên chọn một nguồn mapping rõ ràng để tránh tên type id mơ hồ hoặc trùng lặp.

## 5. Đọc và ghi một thuộc tính kiểu cha

Khi `@JsonTypeInfo` được đặt trên base class hoặc interface, mọi vị trí sử dụng kiểu đó có thể áp dụng cơ chế polymorphic tương ứng.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

PaymentMethod payment = new CardPayment();
payment.setAccountHolder("An");
((CardPayment) payment).setLastFourDigits("1234");

String json = mapper.writeValueAsString(payment);

PaymentMethod restored = mapper.readValue(json, PaymentMethod.class);
System.out.println(restored.getClass().getSimpleName()); // CardPayment
```

Đoạn code giả định mapper đã có subtype metadata theo annotation hoặc đăng ký chương trình. Trong ứng dụng thật, nên tránh cast nếu có thể thiết kế API trên subtype hoặc method đa hình phù hợp.

Khi serialize, Jackson dùng runtime class của object để xác định subtype và ghi type id. Khi deserialize vào base type, Jackson đọc type id để chọn class cụ thể. Nếu JSON thiếu type id hoặc type id không có trong danh sách, Jackson thường báo lỗi kiểu `InvalidTypeIdException`, trừ khi có cấu hình fallback phù hợp.

## 6. Các vị trí chứa subtype: property, list và map

Polymorphic type metadata không chỉ dùng cho object gốc. Nó cũng hữu ích với thuộc tính lồng nhau và collection khai báo theo base type.

Ví dụ một đơn hàng có danh sách nhiều phương thức thanh toán:

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
      "accountHolder": "An",
      "lastFourDigits": "1234"
    },
    {
      "kind": "bank-transfer",
      "accountHolder": "Binh",
      "bankCode": "VCB"
    }
  ]
}
```

Khi đọc `PaymentBatch.class`, Jackson xử lý từng phần tử của `List<PaymentMethod>` dựa trên type id và tạo đúng `CardPayment` hoặc `BankTransfer`.

Tương tự, `Map<String, PaymentMethod>` có thể chứa nhiều subtype khác nhau:

```java
Map<String, PaymentMethod> methods = mapper.readValue(
        json,
        new TypeReference<Map<String, PaymentMethod>>() {}
);
```

Điều kiện là generic type đích phải được cung cấp đầy đủ và mỗi object value phải có type metadata mà base type yêu cầu.

## 7. Chọn cách đưa type id vào JSON bằng include

Thuộc tính `include` của `@JsonTypeInfo` quyết định vị trí và hình thức type metadata. Một số lựa chọn thường gặp:

| Giá trị | Hình thức JSON khái quát | Khi phù hợp |
| --- | --- | --- |
| `As.PROPERTY` | `{"kind":"card","lastFourDigits":"1234"}` | Discriminator là property cùng cấp với dữ liệu object; phổ biến cho API |
| `As.EXISTING_PROPERTY` | `{"kind":"card","lastFourDigits":"1234"}` | Discriminator đã là property thật của mô hình và được serialize như property thông thường |
| `As.WRAPPER_OBJECT` | `{"card":{"lastFourDigits":"1234"}}` | Tên subtype bao ngoài object dữ liệu |
| `As.WRAPPER_ARRAY` | `["card",{"lastFourDigits":"1234"}]` | Type id và object được đặt trong array hai phần tử |
| `As.EXTERNAL_PROPERTY` | `{"paymentKind":"card","payment":{"lastFourDigits":"1234"}}` | Type id nằm cạnh property chứa object được phân loại; thường dùng ở mức property |

### 7.1. PROPERTY

Đây là lựa chọn thông dụng:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
```

Jackson thêm type id vào object JSON. Bên đọc nhìn thấy discriminator rõ ràng và các field dữ liệu còn lại nằm cùng cấp.

### 7.2. EXISTING_PROPERTY

Chọn `EXISTING_PROPERTY` khi mô hình subtype đã có property discriminator thật, ví dụ `kind` là field/getter trong class. Type serializer sử dụng property đã tồn tại thay vì tạo một property type id riêng.

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXISTING_PROPERTY,
        property = "kind"
)
```

Trong trường hợp này, cần bảo đảm property `kind` được serialize và có giá trị phù hợp. Nếu property không xuất hiện trong output, bên đọc có thể không xác định được subtype.

### 7.3. WRAPPER_OBJECT và WRAPPER_ARRAY

Với `WRAPPER_OBJECT`, type id trở thành tên property bao ngoài:

```json
{
  "card": {
    "accountHolder": "An",
    "lastFourDigits": "1234"
  }
}
```

Với `WRAPPER_ARRAY`, type id và payload được đặt thành hai phần tử:

```json
[
  "card",
  {
    "accountHolder": "An",
    "lastFourDigits": "1234"
  }
]
```

Hai cách này làm type id nổi bật ở cấu trúc bao ngoài, nhưng có thể ít thuận tiện hơn nếu API đã có schema object với discriminator property.

### 7.4. EXTERNAL_PROPERTY

`EXTERNAL_PROPERTY` đặt type id bên ngoài object được phân loại, thường là sibling property của thuộc tính chứa object:

```java
public class Order {
    private String id;

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
            property = "paymentKind"
    )
    private PaymentMethod payment;
}
```

JSON có thể có dạng:

```json
{
  "id": "ORD-1001",
  "paymentKind": "card",
  "payment": {
    "accountHolder": "An",
    "lastFourDigits": "1234"
  }
}
```

`EXTERNAL_PROPERTY` thường được cấu hình trên property cụ thể vì type id nằm cạnh property đó trong object cha. Không nên giả định nó có cùng ý nghĩa khi đặt trên toàn bộ class; hãy kiểm tra đúng vị trí annotation và JSON contract cần tạo.

## 8. visible: có chuyển discriminator thành property Java không?

Mặc định, khi Jackson dùng một property như `kind` làm type id, type id được tiêu thụ cho quá trình chọn subtype và không nhất thiết được gán vào property Java thông thường của subtype.

Nếu subtype cũng có field `kind` và ứng dụng muốn nhận giá trị discriminator vào field đó, có thể bật `visible = true`:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        visible = true
)
```

Khi `visible = true`, type id được chuyển tiếp vào quá trình deserialize như một property thông thường sau khi đã dùng để chọn subtype. Subtype cần có property/accessor hoặc cơ chế nhận giá trị tương ứng nếu muốn lưu nó.

Nếu `kind` chỉ phục vụ Jackson chọn subtype và không cần xuất hiện trong domain object, giữ mặc định `visible = false` thường đơn giản hơn.

## 9. Xử lý thiếu hoặc không biết type id

Với `Id.NAME`, Jackson cần tìm được tên type id trong danh sách subtype đã biết. Hai lỗi phổ biến:

- JSON không có discriminator `kind` trong khi base type yêu cầu type metadata.
- JSON có `kind` nhưng giá trị không được đăng ký, ví dụ `"kind": "crypto-wallet"` trong khi mapper chỉ biết `card` và `bank-transfer`.

Thông thường, Jackson báo lỗi `InvalidTypeIdException` hoặc lỗi subtype tương ứng. Đây là hành vi hữu ích vì payload không rõ kiểu không bị âm thầm ánh xạ sai.

### 9.1. defaultImpl

`@JsonTypeInfo` có thuộc tính `defaultImpl` để chỉ định lớp fallback khi type id bị thiếu hoặc không được giải quyết theo cấu hình. Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        defaultImpl = UnknownPayment.class
)
```

`UnknownPayment` phải là kiểu cụ thể phù hợp với base type và có thể được Jackson tạo từ payload. Fallback có thể hữu ích khi hợp đồng yêu cầu tiếp nhận một dạng dữ liệu không phân loại, nhưng cũng có thể che giấu lỗi chính tả hoặc client gửi type id sai.

Không nên đặt một default subtype tùy tiện chỉ để mọi payload đều deserialize thành công. Nếu các subtype có quy tắc nghiệp vụ khác nhau, việc biến một type id không hợp lệ thành một lớp mặc định có thể dẫn đến xử lý sai dữ liệu.

## 10. Id.NAME, Id.CLASS và lựa chọn an toàn

`JsonTypeInfo.Id` xác định cách type id được biểu diễn:

| Id | Dữ liệu nhận diện | Nhận xét |
| --- | --- | --- |
| `NAME` | Tên logic do ứng dụng đăng ký, ví dụ `card` | Thường phù hợp nhất cho API và message contract |
| `CLASS` | Tên đầy đủ của class Java, gồm package | Gắn JSON với cấu trúc package/class; cần đặc biệt thận trọng với input không tin cậy |
| `MINIMAL_CLASS` | Tên class rút gọn theo package cơ sở | Vẫn phụ thuộc tên class và cấu trúc package |
| `DEDUCTION` | Suy luận subtype từ tập property có mặt | Không dùng discriminator tường minh; có thể mơ hồ khi subtype có field giống nhau |

Với API công khai hoặc dữ liệu đến từ hệ thống ngoài, `Id.NAME` thường là lựa chọn dễ kiểm soát. Ứng dụng chỉ đăng ký các subtype hợp lệ và ánh xạ chúng với tên logic ổn định.

Không nên dùng `Id.CLASS` hoặc bật default typing rộng cho dữ liệu không tin cậy chỉ để tránh phải khai báo subtype. Type metadata dựa trên tên class có thể làm lộ chi tiết triển khai, tạo coupling với package và mở rộng bề mặt rủi ro khi deserialize. Nếu phải dùng cơ chế polymorphic rộng hơn, cần cấu hình validator/allowlist chặt chẽ theo phiên bản Jackson và chỉ cho phép các kiểu thực sự cần thiết.

## 11. Đăng ký subtype tập trung cho nhiều module

Trong ứng dụng có plugin hoặc nhiều module nghiệp vụ, có thể để mỗi module đăng ký subtype của nó vào mapper trung tâm:

```java
public final class JacksonConfiguration {
    public static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransfer.class, "bank-transfer")
        );

        return mapper;
    }
}
```

Trong hệ thống lớn, nên gom đăng ký vào một bước bootstrap rõ ràng. Có thể chia theo module nhưng phải bảo đảm:

- Type id là duy nhất trong phạm vi base type liên quan.
- Subtype thực sự kế thừa hoặc triển khai base type được dùng.
- Tất cả subtype cần đọc đều được đăng ký trước khi mapper phục vụ request.
- Không nhận class tùy ý từ tên do client gửi.
- Các phiên bản dịch vụ giữ mapping type id tương thích theo hợp đồng.

Nếu nhiều module cùng đăng ký một type id cho các lớp khác nhau, cấu hình có thể trở nên khó dự đoán. Hãy quy định namespace hoặc prefix cho type id nếu nhiều nhóm phát triển cùng mở rộng hệ thống.

## 12. Dùng Mix-in khi không thể sửa class gốc

Nếu base class đến từ thư viện ngoài và không thể gắn `@JsonTypeInfo`, Jackson Mix-in cho phép gắn annotation từ một class cấu hình riêng.

Ví dụ:

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
abstract class PaymentMethodMixin {
}
```

Đăng ký mix-in:

```java
mapper.addMixIn(PaymentMethod.class, PaymentMethodMixin.class);
```

Mix-in cho phép bổ sung metadata Jackson mà không sửa source class gốc. Đây là lựa chọn hữu ích khi tích hợp thư viện bên thứ ba hoặc muốn giữ domain model không phụ thuộc annotation Jackson.

## 13. Cấu hình theo property hay theo base class?

Đặt `@JsonTypeInfo` trên base class/interface khi mọi vị trí sử dụng kiểu đó đều cần polymorphic handling theo cùng một quy tắc.

Đặt annotation trên một property cụ thể khi chỉ vị trí đó cần type metadata hoặc cần cách đặt discriminator khác. Ví dụ, cùng một lớp con có thể được sử dụng theo một base type trong message A và theo một property khác trong message B; lúc này cấu hình tại property giúp giới hạn phạm vi.

Tuy nhiên, nếu cấu hình annotation ở nhiều nơi khác nhau, hãy giữ hợp đồng dễ hiểu. Việc một class được deserialize theo nhiều discriminator khác nhau có thể làm tăng độ phức tạp khi debug và tích hợp.

## 14. Ví dụ hoàn chỉnh: danh sách payment polymorphic

Base class:

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
    private String accountHolder;

    public String getAccountHolder() {
        return accountHolder;
    }

    public void setAccountHolder(String accountHolder) {
        this.accountHolder = accountHolder;
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
```

```java
public class BankTransfer extends PaymentMethod {
    private String bankCode;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }
}
```

DTO chứa danh sách:

```java
import java.util.List;

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

Đọc và ghi:

```java
ObjectMapper mapper = new ObjectMapper();

PaymentBatch batch = mapper.readValue(json, PaymentBatch.class);

for (PaymentMethod method : batch.getMethods()) {
    if (method instanceof CardPayment card) {
        System.out.println(card.getLastFourDigits());
    } else if (method instanceof BankTransfer transfer) {
        System.out.println(transfer.getBankCode());
    }
}

String output = mapper.writeValueAsString(batch);
```

Với Java phiên bản trước 16, thay pattern matching `instanceof` bằng cast thông thường sau khi kiểm tra kiểu. Ví dụ minh họa cách Jackson tạo subtype cụ thể; code nghiệp vụ có thể được tổ chức tốt hơn bằng method đa hình hoặc visitor nếu số lượng subtype tăng.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `InvalidTypeIdException` báo thiếu type id | JSON không có discriminator trong khi base type yêu cầu | Kiểm tra `include`, tên property và payload thực tế |
| Không tìm thấy subtype cho type id | Tên gửi lên không khớp mapping đã đăng ký | Kiểm tra `@JsonSubTypes`, `@JsonTypeName`, `NamedType` và chữ hoa/thường |
| Serialize có type id nhưng deserialize thất bại | Mapper đọc không có cùng subtype registration hoặc contract không đồng nhất | Đồng bộ cấu hình giữa hai mapper/service |
| Type id không được gán vào field subtype | `visible` mặc định là false | Bật `visible = true` nếu thật sự cần lưu discriminator thành property |
| Có JSON field trùng discriminator | Vừa có property thật vừa dùng `As.PROPERTY` theo cách tạo duplicate | Cân nhắc `As.EXISTING_PROPERTY` và kiểm tra output |
| Một subtype không được nhận diện trong collection | Collection khai báo kiểu quá tổng quát hoặc thiếu type metadata | Kiểm tra generic type và annotation trên base type |
| Type id thay đổi sau khi refactor package | Đang dùng `Id.CLASS` hoặc `MINIMAL_CLASS` | Chuyển sang `Id.NAME` với tên logic ổn định |

Khi debug, hãy kiểm tra cả JSON đầu vào, kiểu đích của `readValue`, annotation trên base type/property và danh sách subtype của đúng mapper đang được sử dụng. Một mapper thử nghiệm tạo bằng `new ObjectMapper()` có thể không có cùng đăng ký subtype với mapper do framework cấu hình.

## 16. Lưu ý khi tích hợp với Spring Boot

Spring Boot thường cung cấp `ObjectMapper` được cấu hình cho HTTP message converter. Nếu ứng dụng có polymorphic DTO, hãy bảo đảm subtype metadata và subtype registration nằm trong mapper mà converter thực sự sử dụng.

Có thể cấu hình qua bean/customizer hoặc cấu hình mapper theo cơ chế mà phiên bản Spring Boot của dự án hỗ trợ. Tránh tạo một mapper riêng trong controller chỉ để đọc request nếu điều đó làm hành vi khác với mapper chuẩn của ứng dụng.

Với API công khai:

- Công bố discriminator và các type id được hỗ trợ trong tài liệu API.
- Dùng tên logic ổn định, không dùng package/class name làm hợp đồng.
- Chỉ đăng ký các subtype hợp lệ.
- Xử lý type id thiếu hoặc không biết theo chính sách rõ ràng.
- Kiểm tra validation riêng cho từng subtype sau khi deserialize.
- Không coi việc Jackson tạo đúng class là bằng chứng payload hợp lệ về nghiệp vụ.

## 17. Ghi nhớ

- `@JsonTypeInfo` định nghĩa cách Jackson đọc/ghi thông tin subtype; `use` chọn loại type id, `include` chọn vị trí và `property` đặt tên discriminator.
- `JsonTypeInfo.Id.NAME` kết hợp tên logic như `card` và `bank-transfer` thường phù hợp với API.
- `@JsonSubTypes` liệt kê subtype và tên tương ứng; `@JsonTypeName` đặt tên logic trên subtype.
- `ObjectMapper.registerSubtypes(new NamedType(...))` đăng ký subtype bằng code khi không muốn hoặc không thể sửa class.
- `As.PROPERTY` thêm discriminator vào object; `EXISTING_PROPERTY`, wrapper và external property đáp ứng các hình thức JSON khác.
- `visible = true` chuyển type id tiếp tục vào quá trình bind property thông thường; mặc định type id chỉ phục vụ chọn subtype.
- Type id thiếu hoặc không được đăng ký thường gây lỗi; `defaultImpl` chỉ nên dùng khi có fallback nghiệp vụ rõ ràng.
- Tránh `Id.CLASS` và default typing rộng cho dữ liệu không tin cậy; dùng danh sách subtype allowlist.
- Đăng ký subtype và cấu hình mapper trước khi mapper được chia sẻ cho nhiều request.

Khi thiết kế polymorphic JSON, hãy xác định base type, danh sách subtype được phép, tên discriminator và hình thức JSON trước. Sau đó chọn annotation hoặc đăng ký `NamedType` để mapping type id với lớp con. Một hợp đồng dùng tên logic ổn định và allowlist rõ ràng sẽ giúp dữ liệu tương thích khi code được refactor, đồng thời giới hạn những kiểu Java mà input bên ngoài có thể yêu cầu Jackson tạo ra.
