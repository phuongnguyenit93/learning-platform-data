# Lựa chọn vị trí lưu thông tin kiểu trong JSON

Trong mô hình đa hình, một thuộc tính Java có thể tham chiếu đến nhiều lớp con. Ví dụ, một đơn hàng có thể chứa phương thức thanh toán bằng thẻ hoặc tiền mặt; một thông báo có thể mang payload email hoặc SMS. Khi tuần tự hóa, Jackson cần một cách để ghi lại lớp con thực tế. Khi giải tuần tự hóa, nó cần đủ thông tin để chọn đúng lớp Java và tạo đối tượng tương ứng.

Thông tin dùng để nhận diện lớp con thường được gọi là type id, type discriminator hoặc metadata kiểu. Jackson cho phép lựa chọn vị trí đặt thông tin này trong JSON bằng thuộc tính include của annotation JsonTypeInfo. Cùng một tập lớp con có thể được biểu diễn theo nhiều hình dạng JSON: type id nằm trong object, bao object bằng một wrapper, đứng cạnh object dưới dạng thuộc tính bên ngoài, hoặc được suy luận từ tên các thuộc tính.

Việc chọn vị trí lưu type id ảnh hưởng trực tiếp đến hợp đồng JSON, khả năng tương thích với hệ thống khác, cách xử lý object lồng nhau và mức độ an toàn khi đọc dữ liệu. Bài này tập trung vào các chiến lược đặt type metadata và cách chọn chiến lược phù hợp.

## 1. Vì sao JSON cần thông tin kiểu cho đa hình?

Java có thể khai báo biến bằng một kiểu cha hoặc interface, trong khi đối tượng thực tế là một lớp con:

~~~java
Payment payment = new CardPayment();
~~~

Nếu chỉ ghi các thuộc tính của đối tượng, JSON có thể trông như sau:

~~~json
{
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

JSON trên không cho biết rõ đây là CardPayment. Khi đọc vào kiểu Payment, Jackson không thể tự suy ra một lớp con cụ thể chỉ từ khai báo biến Java nếu không có quy tắc subtype hoặc metadata phù hợp.

Thông tin kiểu có thể được ghi trực tiếp trong JSON:

~~~json
{
  "kind": "card",
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

Hoặc bao object bằng một cấu trúc bên ngoài:

~~~json
{
  "card": {
    "amount": 250000,
    "lastFourDigits": "1234"
  }
}
~~~

Hai cách biểu diễn đều có thể chỉ ra CardPayment, nhưng vị trí của type id khác nhau. Đây chính là điều khiển bởi JsonTypeInfo.As.

## 2. Khai báo các subtype và tên kiểu logic

Trước khi chọn vị trí type id, cần khai báo các lớp con Jackson được phép nhận diện. Một cách phổ biến là dùng JsonTypeInfo kết hợp JsonSubTypes và JsonTypeName.

~~~java
public abstract class Payment {
    private long amount;

    public long getAmount() {
        return amount;
    }

    public void setAmount(long amount) {
        this.amount = amount;
    }
}
~~~

~~~java
@JsonTypeName("card")
public class CardPayment extends Payment {
    private String lastFourDigits;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}
~~~

~~~java
@JsonTypeName("cash")
public class CashPayment extends Payment {
    private String currency;

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Tên card và cash là tên kiểu logic được dùng trong hợp đồng JSON. Chúng không buộc client phải biết package hoặc tên lớp Java.

Có thể khai báo các subtype ngay trên kiểu cha:

~~~java
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
~~~

Khi đã khai báo tên trong JsonSubTypes.Type, JsonTypeName trên lớp con có thể không cần thiết cho chính cấu hình đó. Có thể chọn một cách khai báo tập trung hoặc phân tán, miễn tên subtype nhất quán.

Một cách khác là đăng ký tên subtype trong ObjectMapper:

~~~java
mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(CashPayment.class, "cash")
);
~~~

Đăng ký bằng code hữu ích khi subtype đến từ module riêng hoặc khi không muốn gắn annotation vào lớp domain. Dù dùng cách nào, Jackson cần một bảng ánh xạ giữa type id và lớp Java được phép tạo.

## 3. JsonTypeInfo.As là gì?

Annotation JsonTypeInfo có thuộc tính include, nhận một giá trị trong enum JsonTypeInfo.As. Thuộc tính này xác định type id được đặt ở đâu so với dữ liệu object.

Các chiến lược thường dùng:

| Include mode | Vị trí type id | Hình dạng tổng quát |
|---|---|---|
| PROPERTY | Một thuộc tính trong object | {"kind":"card", ...} |
| EXISTING_PROPERTY | Một thuộc tính thông thường đã có trong object | {"kind":"card", ...} |
| WRAPPER_OBJECT | Tên thuộc tính của một object wrapper bao quanh payload | {"card": {...}} |
| WRAPPER_ARRAY | Phần tử đầu của array wrapper | ["card", {...}] |
| EXTERNAL_PROPERTY | Thuộc tính nằm bên cạnh property chứa payload | {"payloadType":"card","payload":{...}} |
| DEDUCTION | Không ghi type id; suy luận từ tên các field | {"lastFourDigits":"1234", ...} |

PROPERTY, EXISTING_PROPERTY, WRAPPER_OBJECT, WRAPPER_ARRAY và EXTERNAL_PROPERTY đều có thể mang type id tường minh. DEDUCTION là cách suy luận từ cấu trúc, không thêm discriminator vào JSON.

Lựa chọn include mode không thay thế việc chọn cơ chế tạo type id. Thuộc tính use của JsonTypeInfo quyết định type id lấy từ đâu, còn include quyết định nó nằm ở đâu.

## 4. PROPERTY: đặt type id thành thuộc tính trong object

As.PROPERTY là chiến lược thường gặp. Jackson thêm một thuộc tính vào JSON object của subtype. Tên thuộc tính được chỉ định bằng property; nếu bỏ qua, Jackson sử dụng tên mặc định theo cấu hình annotation.

Khai báo trên kiểu cha:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
    // Các thuộc tính chung
}
~~~

Khi ghi CardPayment qua kiểu Payment, JSON có hình dạng:

~~~json
{
  "kind": "card",
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

Với CashPayment:

~~~json
{
  "kind": "cash",
  "amount": 50000,
  "currency": "VND"
}
~~~

Khi đọc, Jackson xem giá trị kind, tìm subtype đã đăng ký tương ứng rồi ánh xạ các field còn lại vào lớp con.

~~~java
Payment payment = mapper.readValue(json, Payment.class);
~~~

Nếu kind là card, kết quả có thể là CardPayment; nếu là cash, kết quả có thể là CashPayment. Caller vẫn khai báo kiểu Payment nhưng có thể kiểm tra kiểu runtime hoặc dùng logic đa hình.

PROPERTY thường phù hợp với REST API vì JSON vẫn là object thông thường, dễ đọc bằng mắt, dễ xử lý bằng JSONPath và tương thích với nhiều công cụ.

## 5. WRAPPER_OBJECT: dùng tên object wrapper làm type id

Với As.WRAPPER_OBJECT, Jackson tạo một object bên ngoài. Tên property của wrapper chính là type id; giá trị của property đó là object dữ liệu subtype.

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.WRAPPER_OBJECT
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
}
~~~

JSON đầu ra:

~~~json
{
  "card": {
    "amount": 250000,
    "lastFourDigits": "1234"
  }
}
~~~

Với tiền mặt:

~~~json
{
  "cash": {
    "amount": 50000,
    "currency": "VND"
  }
}
~~~

Khi đọc, Jackson lấy tên key wrapper làm type id và ánh xạ object con vào subtype tương ứng:

~~~java
Payment payment = mapper.readValue(json, Payment.class);
~~~

Wrapper object giúp phân biệt loại payload ngay ở cấp ngoài, không cần dành một field trong object nghiệp vụ cho discriminator. Nó cũng làm thay đổi hình dạng root: dữ liệu không còn là object payment trực tiếp mà là object chỉ có một nhánh wrapper.

Chọn chiến lược này khi hợp đồng muốn biểu diễn mỗi biến thể như một nhánh có tên, hoặc khi payload cần giữ nguyên schema riêng của subtype.

## 6. WRAPPER_ARRAY: type id là phần tử đầu của array

As.WRAPPER_ARRAY biểu diễn subtype bằng một JSON array gồm hai phần tử chính:

1. Type id.
2. Payload của subtype.

Khai báo:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.WRAPPER_ARRAY
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
}
~~~

JSON:

~~~json
[
  "card",
  {
    "amount": 250000,
    "lastFourDigits": "1234"
  }
]
~~~

Hoặc:

~~~json
[
  "cash",
  {
    "amount": 50000,
    "currency": "VND"
  }
]
~~~

Đọc dữ liệu:

~~~java
Payment payment = mapper.readValue(json, Payment.class);
~~~

WRAPPER_ARRAY ngắn gọn và type id có vị trí cố định, nhưng người đọc JSON phải biết phần tử đầu không phải dữ liệu nghiệp vụ mà là metadata kiểu. Một số công cụ hoặc schema đơn giản cũng khó diễn đạt hợp đồng này hơn object có discriminator.

Nên dùng khi giao thức đã quy định dạng tuple hoặc khi tính gọn của wrapper array là yêu cầu rõ ràng. Với API hướng đến con người hoặc cần khả năng mở rộng field, PROPERTY thường dễ hiểu hơn.

## 7. EXISTING_PROPERTY: dùng thuộc tính discriminator vốn có

Trong một số mô hình, discriminator đã là thuộc tính nghiệp vụ của object. Ví dụ, mỗi payment có field kind và lớp con cũng cần giữ field đó như một phần dữ liệu thông thường.

As.EXISTING_PROPERTY yêu cầu Jackson dùng một property đã có trong object làm type id. Jackson không cần chèn thêm một bản type property độc lập theo cơ chế PROPERTY; property đó được ghi như một thuộc tính thông thường của bean.

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.EXISTING_PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
    public abstract String getKind();
}
~~~

Lớp con cung cấp giá trị discriminator:

~~~java
public class CardPayment extends Payment {
    private long amount;
    private String lastFourDigits;

    @Override
    public String getKind() {
        return "card";
    }

    public long getAmount() {
        return amount;
    }

    public void setAmount(long amount) {
        this.amount = amount;
    }

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}
~~~

JSON có dạng:

~~~json
{
  "kind": "card",
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

Khác biệt giữa PROPERTY và EXISTING_PROPERTY nằm ở việc ai sở hữu việc ghi property discriminator. Với PROPERTY, cơ chế type serializer ghi type id. Với EXISTING_PROPERTY, field kind phải được bean cung cấp như một property bình thường; nếu getter không trả đúng type id hoặc property không được serialize, metadata có thể thiếu hoặc sai.

EXISTING_PROPERTY hữu ích khi discriminator là một phần thực sự của schema nghiệp vụ, được dùng ở nhiều hệ thống hoặc cần xuất hiện như field bình thường trong DTO.

## 8. visible: có đưa type id vào quá trình gán thuộc tính không?

Mặc định, type id được dùng để chọn subtype rồi bị tiêu thụ bởi cơ chế xử lý đa hình. Nó không nhất thiết được chuyển tiếp cho deserializer như một thuộc tính dữ liệu thông thường.

Thuộc tính visible của JsonTypeInfo điều khiển hành vi này khi đọc:

- visible = false (mặc định): type id được dùng để chọn subtype và không được chuyển tiếp như token field thông thường cho bean deserializer.
- visible = true: type id vẫn được dùng để chọn subtype, đồng thời được chuyển tiếp để property tương ứng trong lớp con có thể nhận giá trị.

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind",
    visible = true
)
~~~

Nếu lớp con có field kind và setter phù hợp, nó có thể nhận giá trị card từ JSON:

~~~java
public class CardPayment extends Payment {
    private String kind;

    public String getKind() {
        return kind;
    }

    public void setKind(String kind) {
        this.kind = kind;
    }
}
~~~

Chỉ bật visible khi ứng dụng cần giữ discriminator như dữ liệu của object. Nếu không, để mặc định giúp tránh lặp metadata trong mô hình Java.

visible không thay đổi vị trí type id trong JSON. Nó chỉ ảnh hưởng việc type id có tiếp tục được chuyển đến deserializer của subtype hay không.

## 9. EXTERNAL_PROPERTY: đặt type id bên cạnh payload

As.EXTERNAL_PROPERTY đặt type id thành một thuộc tính ngang hàng với property chứa object đa hình. Thay vì nhét discriminator bên trong payload, JSON có hai field cùng cấp:

~~~json
{
  "eventName": "payment-created",
  "payloadType": "card",
  "payload": {
    "amount": 250000,
    "lastFourDigits": "1234"
  }
}
~~~

Ở đây payloadType mô tả kiểu của payload. Đây là khác biệt chính so với PROPERTY, nơi type id nằm bên trong object payload.

Có thể cấu hình ở property:

~~~java
public class Event {
    private String eventName;

    @JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
        property = "payloadType"
    )
    @JsonSubTypes({
        @JsonSubTypes.Type(value = EmailPayload.class, name = "email"),
        @JsonSubTypes.Type(value = SmsPayload.class, name = "sms")
    })
    private NotificationPayload payload;

    public String getEventName() {
        return eventName;
    }

    public void setEventName(String eventName) {
        this.eventName = eventName;
    }

    public NotificationPayload getPayload() {
        return payload;
    }

    public void setPayload(NotificationPayload payload) {
        this.payload = payload;
    }
}
~~~

Kiểu cha và các subtype:

~~~java
public abstract class NotificationPayload {
}

public class EmailPayload extends NotificationPayload {
    private String recipient;
    private String subject;

    // Getter và setter
}

public class SmsPayload extends NotificationPayload {
    private String phoneNumber;
    private String message;

    // Getter và setter
}
~~~

Khi serialize Event có EmailPayload, Jackson có thể tạo JSON dạng:

~~~json
{
  "eventName": "payment-created",
  "payloadType": "email",
  "payload": {
    "recipient": "mai@example.com",
    "subject": "Receipt"
  }
}
~~~

Khi đọc, Jackson dùng payloadType để chọn EmailPayload hoặc SmsPayload cho thuộc tính payload.

EXTERNAL_PROPERTY thường phù hợp với envelope hoặc event schema, nơi metadata mô tả payload được đặt ở cấp bao quanh. Nó giúp object con giữ schema riêng mà không cần thêm discriminator vào chính object con.

### Giới hạn của EXTERNAL_PROPERTY

EXTERNAL_PROPERTY phụ thuộc vào một property cha có thể chứa type id bên cạnh payload. Vì vậy, đây là lựa chọn dành cho metadata của property trong một object bao quanh. Nó không phải cách tổng quát để đặt type id bên ngoài một root value độc lập, vì root không có object cha để chứa sibling property.

Không nên đặt EXTERNAL_PROPERTY trên kiểu cha với kỳ vọng nó hoạt động giống PROPERTY ở mọi ngữ cảnh. Hãy khai báo trên property cần đa hình và kiểm tra hình dạng JSON thực tế.

Với property có giá trị null, việc xuất type id phụ thuộc trạng thái payload và cách serializer xử lý null; không nên giả định luôn có đủ cả hai field. Nếu schema yêu cầu type id ngay cả khi payload null, cần thiết kế biểu diễn riêng và kiểm thử.

## 10. PROPERTY và EXTERNAL_PROPERTY khác nhau ra sao?

Hai chiến lược có thể dùng cùng một type id nhưng tạo ra hai vị trí khác nhau:

PROPERTY:

~~~json
{
  "eventName": "notification",
  "payload": {
    "kind": "email",
    "recipient": "mai@example.com",
    "subject": "Hello"
  }
}
~~~

EXTERNAL_PROPERTY:

~~~json
{
  "eventName": "notification",
  "payloadType": "email",
  "payload": {
    "recipient": "mai@example.com",
    "subject": "Hello"
  }
}
~~~

| Tiêu chí | PROPERTY | EXTERNAL_PROPERTY |
|---|---|---|
| Vị trí type id | Bên trong object payload | Cùng cấp với property payload |
| Payload độc lập | Có discriminator riêng | Payload không chứa discriminator |
| Ngữ cảnh sử dụng | Kiểu cha hoặc property | Chủ yếu ở property của bean bao quanh |
| Tính dễ xử lý độc lập | Cao, payload tự mô tả subtype | Cần cả envelope hoặc sibling metadata |
| Phù hợp | API trả object subtype trực tiếp | Event/envelope có metadata bên ngoài payload |

Nếu payload có thể được lưu, truyền hoặc xử lý độc lập khỏi envelope, PROPERTY thường thuận tiện hơn vì object tự mô tả kiểu. Nếu type metadata thuộc về envelope và payload cần giữ schema thuần nghiệp vụ, EXTERNAL_PROPERTY có thể phù hợp.

## 11. DEDUCTION: suy luận subtype từ tên field

JsonTypeInfo.Id.DEDUCTION cho phép Jackson chọn subtype bằng cách nhìn các tên field xuất hiện trong object. Không có type id được ghi vào JSON.

~~~java
@JsonTypeInfo(use = JsonTypeInfo.Id.DEDUCTION)
@JsonSubTypes({
    @JsonSubTypes.Type(CardPayment.class),
    @JsonSubTypes.Type(CashPayment.class)
})
public abstract class Payment {
}
~~~

Nếu CardPayment có field lastFourDigits còn CashPayment có field cashDeskCode, các JSON sau có thể được phân biệt:

~~~json
{
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

~~~json
{
  "amount": 50000,
  "cashDeskCode": "COUNTER-2"
}
~~~

Jackson xây dựng dấu hiệu nhận dạng từ tên property của các subtype đã biết. Khi các tên field đủ khác nhau để xác định một subtype, nó chọn lớp tương ứng.

### Khi nào DEDUCTION hoạt động tốt?

DEDUCTION phù hợp khi:

- JSON schema không cho phép thêm discriminator.
- Các subtype có tập tên field phân biệt rõ ràng.
- Các tên field có ý nghĩa ổn định và được kiểm soát.
- Ứng dụng chấp nhận việc subtype được suy luận thay vì khai báo trực tiếp.

### Khi nào DEDUCTION thất bại hoặc mơ hồ?

Nếu hai subtype có cùng các tên field hoặc payload chỉ chứa các field chung, Jackson có thể không xác định duy nhất subtype.

Ví dụ:

~~~json
{
  "amount": 50000
}
~~~

Nếu amount là field chung của cả CardPayment và CashPayment, dữ liệu này không đủ dấu hiệu để chọn một lớp con. Jackson có thể báo lỗi vì không thể suy luận subtype duy nhất.

DEDUCTION dựa trên tên field, không dựa trên kiểu giá trị hoặc việc field có giá trị khác null. Việc đổi tên field, thêm field chung hoặc thay đổi schema subtype có thể ảnh hưởng khả năng suy luận. Do đó, cần kiểm thử các payload tối thiểu và các trường hợp chỉ có field giao nhau.

DEDUCTION được hỗ trợ từ Jackson 2.12. Đây là một cơ chế hữu ích khi không thể thay đổi JSON schema, nhưng type id tường minh thường dễ quản lý và ít mơ hồ hơn trong API lâu dài.

## 12. Chọn cách tạo type id bằng JsonTypeInfo.Id

Vị trí type id (include) và nguồn tạo type id (use) là hai quyết định độc lập.

Một số giá trị JsonTypeInfo.Id thường gặp:

| Id mode | Type id lấy từ đâu | Ví dụ |
|---|---|---|
| NAME | Tên logic đăng ký cho subtype | card, cash |
| CLASS | Tên lớp Java đầy đủ | com.example.CardPayment |
| MINIMAL_CLASS | Tên lớp rút gọn tương đối theo package cơ sở | .CardPayment |
| DEDUCTION | Suy luận từ tên field | Không có type id trong JSON |
| CUSTOM | Resolver tùy chỉnh | Mã do ứng dụng định nghĩa |
| NONE | Không dùng type id | Không có discriminator |

Với API công khai, Id.NAME thường là lựa chọn dễ kiểm soát vì type id ổn định và không làm lộ package Java. Id.CLASS và Id.MINIMAL_CLASS gắn JSON với tên lớp và cấu trúc package của ứng dụng; thay đổi package có thể ảnh hưởng hợp đồng dữ liệu.

Không nên mặc định rằng tên lớp Java là một type id an toàn để nhận từ dữ liệu không tin cậy. Đọc tên lớp từ JSON có thể tạo rủi ro nếu hệ thống cho phép các lớp không mong muốn được khởi tạo.

## 13. Dùng Id.NAME với JsonTypeName và JsonSubTypes

Đây là mẫu được khuyến nghị cho phần lớn mô hình đa hình có danh sách subtype biết trước:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
}
~~~

Các tên card và cash là hợp đồng giữa producer và consumer. Nếu lớp CardPayment được chuyển package hoặc đổi tên, JSON vẫn giữ type id card miễn cấu hình tên không đổi.

Có thể khai báo tên trên lớp con:

~~~java
@JsonTypeName("card")
public class CardPayment extends Payment {
}
~~~

Tên này được dùng khi Jackson cần định danh subtype theo Id.NAME, nếu subtype được nhận diện/đăng ký trong cấu hình tương ứng.

## 14. Đăng ký subtype bằng ObjectMapper

Trong một số hệ thống, subtype đến từ plugin hoặc module khác và không tiện khai báo tất cả bằng annotation. Có thể đăng ký:

~~~java
ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(CashPayment.class, "cash")
);
~~~

Nếu kiểu cha đã có JsonTypeInfo(use = Id.NAME, ...), registry cung cấp ánh xạ tên subtype. Có thể gom đăng ký vào một module:

~~~java
SimpleModule paymentModule = new SimpleModule();
paymentModule.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(CashPayment.class, "cash")
);

ObjectMapper mapper = JsonMapper.builder()
    .addModule(paymentModule)
    .build();
~~~

API đăng ký subtype có thể được gọi trực tiếp trên mapper hoặc thông qua module tùy cách tổ chức ứng dụng và phiên bản Jackson. Điều quan trọng là hoàn tất đăng ký trước khi mapper được chia sẻ và sử dụng.

## 15. Dùng Id.CUSTOM với TypeIdResolver

Nếu type id phải tuân theo một hệ mã riêng, có thể triển khai TypeIdResolver. Ví dụ hệ thống bên ngoài dùng mã P01 cho thẻ và P02 cho tiền mặt thay vì tên logic dễ đọc.

Resolver tùy chỉnh cung cấp hai chiều:

- Từ lớp Java sang type id khi serialize.
- Từ type id sang JavaType khi deserialize.

Khung triển khai:

~~~java
public class PaymentTypeIdResolver extends TypeIdResolverBase {

    @Override
    public String idFromValue(Object value) {
        if (value instanceof CardPayment) {
            return "P01";
        }
        if (value instanceof CashPayment) {
            return "P02";
        }
        throw new IllegalArgumentException(
            "Unsupported payment type: " + value.getClass()
        );
    }

    @Override
    public String idFromValueAndType(Object value, Class<?> suggestedType) {
        if (CardPayment.class.isAssignableFrom(suggestedType)) {
            return "P01";
        }
        if (CashPayment.class.isAssignableFrom(suggestedType)) {
            return "P02";
        }
        throw new IllegalArgumentException(
            "Unsupported payment class: " + suggestedType
        );
    }

    @Override
    public JavaType typeFromId(
            DatabindContext context,
            String id) throws IOException {
        return switch (id) {
            case "P01" -> context.constructType(CardPayment.class);
            case "P02" -> context.constructType(CashPayment.class);
            default -> throw new IllegalArgumentException(
                "Unknown payment type id: " + id
            );
        };
    }

    @Override
    public JsonTypeInfo.Id getMechanism() {
        return JsonTypeInfo.Id.CUSTOM;
    }
}
~~~

Gắn resolver:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.CUSTOM,
    include = JsonTypeInfo.As.PROPERTY,
    property = "paymentCode"
)
@JsonTypeIdResolver(PaymentTypeIdResolver.class)
public abstract class Payment {
}
~~~

Ví dụ JSON:

~~~json
{
  "paymentCode": "P01",
  "amount": 250000,
  "lastFourDigits": "1234"
}
~~~

Resolver tùy chỉnh cần xử lý đầy đủ các subtype được phép và từ chối type id không biết. Không nên tạo lớp bằng cách ghép chuỗi package với tên lớp do client gửi.

Chữ ký phương thức của TypeIdResolver và cách khởi tạo resolver có thể thay đổi theo phiên bản Jackson; hãy triển khai đúng interface trong phiên bản dependency của dự án.

## 16. Vị trí type metadata ở root, property và collection

Vị trí annotation quyết định phạm vi đa hình. Có thể khai báo type info trên kiểu cha để mọi lần sử dụng kiểu cha đều mang metadata, hoặc trên một property nếu chỉ vị trí đó cần đa hình.

### Trên kiểu cha

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
}
~~~

Khi serialize một biến root có khai báo kiểu Payment, type info có thể được dùng:

~~~java
Payment payment = new CardPayment();
String json = mapper.writeValueAsString(payment);
~~~

### Trên property

Nếu chỉ một property cần đa hình, có thể đặt annotation trực tiếp trên property:

~~~java
public class Order {
    @JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
    )
    @JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
    })
    private Payment payment;
}
~~~

Annotation ở property cho phép cùng một lớp Java được dùng theo nhiều hợp đồng khác nhau ở các vị trí khác nhau, nếu mô hình và cấu hình được thiết kế phù hợp.

### Trong collection hoặc Map

Khi kiểu phần tử là kiểu cha đa hình, metadata được áp dụng cho từng phần tử:

~~~java
public class PaymentBatch {
    private List<Payment> payments;
    private Map<String, Payment> byReference;
}
~~~

Nếu Payment có JsonTypeInfo, mỗi value Payment trong List hoặc Map được serialize với type id của subtype tương ứng.

Khi đặt JsonTypeInfo trên một property có kiểu container, Jackson áp dụng metadata cho các giá trị nội dung của container (phần tử collection hoặc value của Map), không có nghĩa là type id mô tả chính lớp List hoặc Map. Nếu cần đa hình cho chính kiểu container, cần một mô hình hoặc wrapper phù hợp.

## 17. Type id và tên property bị trùng

Với PROPERTY, tên discriminator có thể trùng với một property dữ liệu của subtype. Ví dụ, subtype đã có field kind nhưng annotation cũng yêu cầu property="kind".

Trong trường hợp này, cần xác định rõ ai chịu trách nhiệm ghi field đó:

- PROPERTY để Jackson ghi type id như metadata.
- EXISTING_PROPERTY để property bean hiện có cung cấp giá trị type id.

Không nên tạo hai nguồn ghi cùng tên field với kỳ vọng Jackson luôn tự hợp nhất đúng. Hãy chọn một cơ chế và viết kiểm tra để xác nhận JSON chỉ có một discriminator với giá trị đúng.

Nếu cần giữ giá trị type id trong thuộc tính Java sau khi đọc, xem xét visible = true và bảo đảm subtype có property nhận giá trị tương ứng.

## 18. defaultImpl khi thiếu hoặc không nhận diện được type id

JsonTypeInfo có thuộc tính defaultImpl để chỉ định lớp mặc định trong một số trường hợp type id bị thiếu hoặc không giải quyết được theo cấu hình. Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind",
    defaultImpl = LegacyPayment.class
)
~~~

Đây có thể là cách hỗ trợ dữ liệu cũ chưa có discriminator hoặc một schema tương thích ngược đã quy định lớp fallback.

Tuy nhiên, defaultImpl không nên được dùng để âm thầm biến mọi type id sai thành một lớp nghiệp vụ tùy ý. Cần phân biệt:

- Type id bị thiếu vì payload đến từ phiên bản cũ.
- Type id không biết vì producer gửi một subtype mới.
- Type id sai hoặc bị giả mạo.

Nếu fallback che giấu dữ liệu không hợp lệ, lỗi tích hợp có thể bị bỏ qua và payload bị diễn giải sai. Hãy xác định rõ chính sách cho từng trường hợp và kiểm thử.

## 19. Không dùng tên lớp tùy ý từ JSON như một cơ chế đăng ký subtype

Các chiến lược Id.CLASS và Id.MINIMAL_CLASS có thể đưa tên lớp Java vào JSON. Khi đọc, Jackson cần phân giải tên lớp thành kiểu Java. Điều này tạo liên kết chặt giữa hợp đồng JSON và cấu trúc package/class.

Rủi ro lớn hơn xuất hiện khi ứng dụng bật cơ chế polymorphic default typing quá rộng hoặc cho phép type id do dữ liệu không tin cậy điều khiển lớp được khởi tạo. Các lớp ngoài dự kiến có thể bị chọn, gây nguy cơ thực thi logic khởi tạo hoặc deserializer nguy hiểm.

Đối với JSON đến từ client, message broker hoặc nguồn ngoài:

- Ưu tiên Id.NAME với danh sách subtype cho phép rõ ràng.
- Không chấp nhận tên lớp bất kỳ chỉ vì class có thể load được.
- Không bật default typing rộng cho dữ liệu không tin cậy.
- Nếu buộc phải dùng default typing, cấu hình PolymorphicTypeValidator giới hạn package hoặc subtype được phép.
- Từ chối type id lạ thay vì tự động nạp lớp.

Ví dụ cấu hình validator cho default typing cần được thiết kế theo đúng miền lớp hợp lệ:

~~~java
PolymorphicTypeValidator validator = BasicPolymorphicTypeValidator.builder()
    .allowIfSubType("com.example.payment")
    .build();

ObjectMapper mapper = JsonMapper.builder()
    .activateDefaultTyping(
        validator,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.PROPERTY
    )
    .build();
~~~

Đoạn mã chỉ minh họa cách giới hạn subtype theo package. Không nên sao chép chính sách package rộng mà không kiểm tra các lớp trong package đó. Với một hierarchy nhỏ, đăng ký Id.NAME tường minh thường dễ kiểm soát hơn.

## 20. Type id có thể được đọc nhưng không ghi hay không?

Một số hợp đồng chỉ cần metadata ở chiều đọc hoặc có quy tắc ghi riêng. Jackson cung cấp nhiều cơ chế để tùy biến serializer/deserializer và type resolver, nhưng không nên giả định mọi include mode có thể chuyển đổi qua lại mà không ảnh hưởng schema.

Ví dụ, EXISTING_PROPERTY dựa trên một getter cung cấp discriminator khi serialize, còn PROPERTY để type serializer tạo discriminator. Nếu chỉ đọc JSON từ bên ngoài mà không muốn phát lại type id theo cùng cách, có thể cân nhắc DTO trung gian hoặc custom serializer cho output.

Khi cần ghi và đọc với hai hợp đồng khác nhau, hãy kiểm tra cả hai chiều:

1. JSON output có đúng vị trí type id không?
2. JSON input có chọn đúng subtype không?
3. Type id có được giữ trong thuộc tính Java khi cần không?
4. Unknown/missing type id có hành vi rõ ràng không?

Không nên chỉ kiểm tra một chiều rồi giả định chiều còn lại hoạt động giống hệt.

## 21. Tương thích ngược khi thay đổi vị trí type id

Thay đổi từ PROPERTY sang WRAPPER_OBJECT hoặc EXTERNAL_PROPERTY là thay đổi schema JSON. Producer và consumer phải thống nhất trước khi triển khai.

Ví dụ cũ:

~~~json
{
  "kind": "card",
  "amount": 250000
}
~~~

Schema mới:

~~~json
{
  "card": {
    "amount": 250000
  }
}
~~~

Consumer đang chờ field kind sẽ không đọc được schema wrapper nếu không được cập nhật. Tương tự, consumer đang chờ type id bên trong payload không thể tự tìm type id ở sibling property nếu cấu hình không thay đổi.

Khi cần chuyển đổi:

- Có thể version endpoint hoặc event schema.
- Có thể dùng adapter ở ranh giới tích hợp để chuyển đổi hình dạng cũ sang mới.
- Có thể hỗ trợ hai phiên bản trong giai đoạn chuyển tiếp bằng DTO hoặc custom deserializer.
- Chỉ bỏ schema cũ sau khi producer và consumer đã được nâng cấp.

Không nên thay đổi include mode âm thầm trong một API đã công bố.

## 22. Lựa chọn vị trí theo đặc điểm hợp đồng

| Nhu cầu | Chiến lược nên xem xét | Lý do |
|---|---|---|
| Object tự mô tả subtype | PROPERTY | Discriminator nằm ngay trong payload |
| Không muốn thêm field vào schema subtype | WRAPPER_OBJECT | Type id nằm ở key wrapper |
| Giao thức biểu diễn dữ liệu dạng tuple | WRAPPER_ARRAY | Type id là phần tử đầu |
| Discriminator đã là field nghiệp vụ | EXISTING_PROPERTY | Dùng lại property hiện có |
| Metadata thuộc envelope bao quanh payload | EXTERNAL_PROPERTY | Type id là sibling của payload |
| Không thể thêm discriminator, subtype có field riêng biệt | DEDUCTION | Suy luận từ tên property |
| Type id theo mã riêng của hệ thống | CUSTOM | Resolver ánh xạ mã và subtype |

Một số nguyên tắc lựa chọn:

- Nếu JSON cần dễ đọc và dễ xử lý bằng công cụ phổ biến, PROPERTY thường là mặc định hợp lý.
- Nếu object con phải giữ schema độc lập, xem xét EXTERNAL_PROPERTY hoặc wrapper.
- Nếu discriminator là field nghiệp vụ, EXISTING_PROPERTY giúp tránh hai nguồn ghi metadata.
- Nếu không thể thay đổi schema đầu vào, DEDUCTION có thể hữu ích nhưng cần bảo đảm các subtype phân biệt được.
- Nếu tên subtype phải ổn định qua các lần đổi package, dùng Id.NAME thay cho tên lớp.

## 23. Kiểm tra hình dạng JSON của từng include mode

Nên viết ví dụ kiểm tra cụ thể thay vì chỉ kiểm tra rằng deserialize không ném lỗi. Ví dụ với PROPERTY:

~~~java
String json = mapper.writeValueAsString(payment);
JsonNode root = mapper.readTree(json);

assertEquals("card", root.get("kind").asText());
assertTrue(root.has("amount"));
~~~

Với WRAPPER_OBJECT:

~~~java
JsonNode root = mapper.readTree(json);

assertTrue(root.has("card"));
assertTrue(root.get("card").has("amount"));
~~~

Với WRAPPER_ARRAY:

~~~java
JsonNode root = mapper.readTree(json);

assertTrue(root.isArray());
assertEquals("card", root.get(0).asText());
assertTrue(root.get(1).isObject());
~~~

Với EXTERNAL_PROPERTY, kiểm tra type id nằm cạnh payload:

~~~java
JsonNode root = mapper.readTree(json);

assertEquals("email", root.get("payloadType").asText());
assertTrue(root.get("payload").has("recipient"));
assertFalse(root.get("payload").has("payloadType"));
~~~

Với DEDUCTION, kiểm tra đúng subtype runtime sau khi đọc:

~~~java
Payment restored = mapper.readValue(json, Payment.class);
assertInstanceOf(CardPayment.class, restored);
~~~

Các assertion cần điều chỉnh theo schema thực tế và phiên bản JUnit đang dùng. Mục tiêu là xác nhận vị trí type metadata đúng như hợp đồng, không chỉ xác nhận object tạo được.

## 24. Kiểm thử subtype không xác định và type id sai

Với Id.NAME, cần kiểm tra trường hợp type id không nằm trong registry:

~~~json
{
  "kind": "crypto",
  "amount": 1000
}
~~~

Nếu crypto không phải subtype được đăng ký, Jackson thường báo lỗi subtype không hợp lệ khi feature FAIL_ON_INVALID_SUBTYPE đang bật. Không nên biến lỗi này thành việc tự tạo lớp bất kỳ.

Cũng cần kiểm tra JSON thiếu discriminator:

~~~json
{
  "amount": 1000
}
~~~

Hành vi phụ thuộc include mode, defaultImpl, cấu hình mapper và subtype resolver. Nếu schema yêu cầu type id, hãy để thiếu type id trở thành lỗi có thể quan sát được thay vì tự đoán một subtype.

Với DEDUCTION, cần kiểm tra:

- Object có field chỉ thuộc subtype A.
- Object có field chỉ thuộc subtype B.
- Object chỉ có các field chung.
- Object chứa field không biết.
- Object chứa field giao nhau của nhiều subtype.

Những trường hợp mơ hồ cần được phát hiện và xử lý rõ ràng.

## 25. Ví dụ tổng hợp: envelope chứa nhiều loại notification

Một event có thể chứa payload thuộc nhiều lớp con:

~~~java
public abstract class NotificationPayload {
}

public class EmailPayload extends NotificationPayload {
    private String recipient;
    private String subject;

    // Getter và setter
}

public class SmsPayload extends NotificationPayload {
    private String phoneNumber;
    private String message;

    // Getter và setter
}
~~~

Chọn type id ở bên ngoài payload:

~~~java
public class NotificationEvent {
    private String eventId;
    private String eventName;

    @JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
        property = "payloadType"
    )
    @JsonSubTypes({
        @JsonSubTypes.Type(value = EmailPayload.class, name = "email"),
        @JsonSubTypes.Type(value = SmsPayload.class, name = "sms")
    })
    private NotificationPayload payload;

    // Getter và setter
}
~~~

Đầu ra cho email:

~~~json
{
  "eventId": "evt-100",
  "eventName": "notification-created",
  "payloadType": "email",
  "payload": {
    "recipient": "mai@example.com",
    "subject": "Welcome"
  }
}
~~~

Đầu ra cho SMS:

~~~json
{
  "eventId": "evt-101",
  "eventName": "notification-created",
  "payloadType": "sms",
  "payload": {
    "phoneNumber": "+84000000000",
    "message": "Your code is 123456"
  }
}
~~~

Đọc lại:

~~~java
NotificationEvent event = mapper.readValue(
    json,
    NotificationEvent.class
);

NotificationPayload payload = event.getPayload();

if (payload instanceof EmailPayload email) {
    sendEmail(email.getRecipient(), email.getSubject());
} else if (payload instanceof SmsPayload sms) {
    sendSms(sms.getPhoneNumber(), sms.getMessage());
}
~~~

Trong ví dụ này, payload giữ cấu trúc riêng của từng loại notification, còn payloadType thuộc envelope. Đây là lý do EXTERNAL_PROPERTY phù hợp với event wrapper.

## 26. Ví dụ cùng một hierarchy với PROPERTY

Nếu payload cần tự mô tả subtype khi được tách khỏi event, có thể đặt discriminator bên trong lớp cha:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "payloadType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = EmailPayload.class, name = "email"),
    @JsonSubTypes.Type(value = SmsPayload.class, name = "sms")
})
public abstract class NotificationPayload {
}
~~~

Khi đó JSON:

~~~json
{
  "eventId": "evt-100",
  "payload": {
    "payloadType": "email",
    "recipient": "mai@example.com",
    "subject": "Welcome"
  }
}
~~~

Nếu chỉ truyền riêng payload, receiver vẫn biết nó là EmailPayload mà không cần envelope. Đổi lại, type id là một phần của schema payload.

## 27. Cấu hình root type và wrapper

Với một root value có kiểu cha Payment, các include mode như PROPERTY, WRAPPER_OBJECT hoặc WRAPPER_ARRAY có thể biểu diễn metadata cùng root value. Ví dụ:

~~~java
Payment payment = new CardPayment();
String json = mapper.writeValueAsString(payment);
~~~

Hình dạng output phụ thuộc annotation trên kiểu cha và include mode đã chọn. Khi đọc, cần truyền kiểu cha làm kiểu đích:

~~~java
Payment restored = mapper.readValue(json, Payment.class);
~~~

Nếu đọc root vào Object mà không có metadata hoặc cấu hình đa hình phù hợp, Jackson không nhất thiết tự chọn subtype mong muốn. Kiểu đích truyền vào và type metadata phải nhất quán.

EXTERNAL_PROPERTY là trường hợp đặc biệt vì nó cần một property bao quanh để chứa type id. Đối với root độc lập, không có sibling property ở cấp cha, do đó nên chọn PROPERTY hoặc wrapper nếu muốn root tự mang metadata.

## 28. Chú ý khi dùng polymorphism với Map và Collection

Giả sử một API trả danh sách Payment:

~~~java
List<Payment> payments = List.of(cardPayment, cashPayment);
String json = mapper.writeValueAsString(payments);
~~~

Nếu Payment có JsonTypeInfo, mỗi phần tử có thể mang type id theo include mode. Với PROPERTY, mỗi object trong array có field kind. Với WRAPPER_OBJECT, mỗi phần tử là object wrapper. Với WRAPPER_ARRAY, mỗi phần tử là array chứa type id và payload.

Khi đọc:

~~~java
List<Payment> restored = mapper.readValue(
    json,
    new TypeReference<List<Payment>>() {}
);
~~~

Generic type đầy đủ cho biết phần tử cần là Payment; type metadata xác định lớp con của từng phần tử.

Đối với Map:

~~~java
Map<String, Payment> byReference = mapper.readValue(
    json,
    new TypeReference<Map<String, Payment>>() {}
);
~~~

Mỗi value Payment có thể được giải quyết subtype riêng. Key của Map vẫn là key của cấu trúc JSON object; type id của value không phải metadata cho key.

## 29. Chọn property name cho discriminator

Tên discriminator nên ổn định, ngắn gọn và không xung đột với thuộc tính nghiệp vụ. Một số tên thường dùng là kind, type, eventType hoặc payloadType.

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
~~~

Khi chọn tên:

- Tránh dùng tên field nghiệp vụ đã có nếu không chủ định dùng EXISTING_PROPERTY.
- Giữ cùng một cách viết giữa các producer và consumer.
- Không đổi tên tùy tiện vì đây là một phần schema JSON.
- Nếu nhiều payload lồng nhau có các hierarchy khác nhau, chọn tên discriminator đủ rõ ngữ cảnh.

Tên property của type id không nhất thiết phải trùng tên interface hoặc lớp Java. Nó thuộc hợp đồng JSON.

## 30. Xử lý subtype mới trong hệ thống phân tán

Trong hệ thống có nhiều producer và consumer, một producer có thể gửi type id mới trước khi consumer được cập nhật. Đây là bài toán tương thích schema.

Ví dụ consumer biết card và cash, nhưng producer mới gửi bankTransfer. Nếu consumer không nhận ra bankTransfer, hành vi mặc định thường là lỗi khi giải quyết subtype.

Các lựa chọn:

- Nâng cấp consumer để đăng ký subtype mới trước khi producer phát dữ liệu mới.
- Version event hoặc API để consumer cũ không nhận schema mới.
- Dùng defaultImpl chỉ khi có một fallback có ý nghĩa nghiệp vụ và an toàn.
- Đọc payload thành JsonNode hoặc một envelope tổng quát ở tầng biên để giữ dữ liệu subtype chưa biết, rồi xử lý sau khi hỗ trợ được bổ sung.

Không nên ánh xạ subtype chưa biết sang một lớp con đã biết chỉ để tránh lỗi nếu hai schema có ý nghĩa khác nhau. Việc diễn giải sai dữ liệu có thể nguy hiểm hơn việc từ chối payload.

## 31. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Jackson không tạo được kiểu cha abstract | Thiếu type info hoặc không có subtype mặc định | Khai báo JsonTypeInfo và subtype hợp lệ |
| Không tìm thấy subtype cho type id | Tên trong JSON không nằm trong registry | Đồng bộ Id.NAME, JsonSubTypes, JsonTypeName hoặc registry |
| JSON có discriminator nhưng field Java không nhận giá trị | visible mặc định là false | Bật visible nếu cần giữ type id trong property |
| Discriminator xuất hiện hai lần | PROPERTY và property bean cùng ghi một tên | Chọn EXISTING_PROPERTY hoặc một nguồn ghi duy nhất |
| Consumer không đọc được wrapper | Include mode hai phía không giống nhau | Đồng bộ As mode và schema |
| EXTERNAL_PROPERTY không hoạt động ở root | Không có object cha để chứa sibling type id | Dùng PROPERTY hoặc wrapper cho root |
| DEDUCTION không chọn được subtype | Các subtype có field chung hoặc payload thiếu dấu hiệu | Dùng type id tường minh hoặc làm schema phân biệt |
| Đổi package làm dữ liệu cũ hỏng | Dùng Id.CLASS/MINIMAL_CLASS | Dùng Id.NAME ổn định |
| Type id lạ gây lỗi | Subtype chưa đăng ký | Version schema hoặc hỗ trợ subtype có kiểm soát |
| Deserialize từ dữ liệu không tin cậy tạo kiểu không mong muốn | Cho phép class name/default typing quá rộng | Dùng Id.NAME allowlist và validator phù hợp |

## 32. Kiểm thử đầy đủ vị trí type id

Với mỗi hierarchy đa hình, nên kiểm tra tối thiểu:

1. Serialize từng subtype và xác nhận type id ở đúng vị trí.
2. Deserialize từng subtype và xác nhận lớp runtime.
3. Đọc JSON thiếu type id.
4. Đọc JSON có type id không biết.
5. Đọc subtype lồng nhau trong object.
6. Đọc subtype trong List và Map.
7. Kiểm tra null payload.
8. Kiểm tra field trùng với tên discriminator nếu mô hình có property tương ứng.
9. Kiểm tra dữ liệu cũ khi thay đổi include mode.

Ví dụ kiểm tra vòng đi-về:

~~~java
Payment original = new CardPayment();

String json = mapper.writeValueAsString(original);
Payment restored = mapper.readValue(json, Payment.class);

assertInstanceOf(CardPayment.class, restored);
~~~

Kiểm tra lớp runtime là quan trọng; chỉ so sánh JSON string có thể phụ thuộc thứ tự field hoặc format. Với vị trí type id, đọc output thành JsonNode rồi xác nhận cấu trúc thường bền vững hơn.

## 33. Nguyên tắc thực hành

- Tách riêng quyết định nguồn type id (use) và vị trí type id (include).
- Ưu tiên Id.NAME với các tên subtype ổn định cho hợp đồng JSON bên ngoài.
- Dùng PROPERTY khi payload nên tự mô tả subtype.
- Dùng WRAPPER_OBJECT hoặc WRAPPER_ARRAY khi schema muốn type id nằm ngoài payload.
- Dùng EXISTING_PROPERTY khi discriminator vốn là thuộc tính của mô hình.
- Dùng EXTERNAL_PROPERTY khi type metadata thuộc envelope bao quanh payload.
- Chỉ dùng DEDUCTION khi các subtype có tập tên field đủ khác biệt.
- Bật visible khi cần gán type id vào property của subtype.
- Chỉ dùng defaultImpl khi fallback có ý nghĩa nghiệp vụ rõ ràng.
- Không cho dữ liệu không tin cậy quyết định lớp Java tùy ý.
- Kiểm tra cả serialization, deserialization, subtype lạ và cấu trúc lồng nhau.
- Coi việc đổi include mode là thay đổi schema cần phối hợp producer/consumer.

Vị trí lưu thông tin kiểu quyết định JSON đa hình tự mô tả đến mức nào và metadata gắn với payload hay với envelope. PROPERTY là lựa chọn dễ dùng cho object tự mô tả; wrapper phù hợp khi muốn bao payload; EXISTING_PROPERTY tận dụng discriminator nghiệp vụ; EXTERNAL_PROPERTY đặt metadata cạnh payload; DEDUCTION suy luận khi không thể thêm type id. Chọn đúng vị trí, dùng tên subtype ổn định và giới hạn tập lớp được phép tạo giúp hợp đồng JSON dễ hiểu, tương thích và an toàn hơn.
