# Khi nào hợp đồng dữ liệu cần nhận diện kiểu con

Một hợp đồng JSON cần nhận diện kiểu con khi cùng một vị trí dữ liệu có thể chứa nhiều biến thể object, và consumer phải biết mỗi object thuộc kiểu cụ thể nào để deserialize hoặc xử lý đúng.

Ví dụ, một hệ thống nhận nhiều loại sự kiện thanh toán: thanh toán bằng thẻ, chuyển khoản hoặc ví điện tử. Các loại sự kiện có thể cùng kế thừa một lớp PaymentEvent, nhưng mỗi loại có các thuộc tính và quy tắc xử lý riêng. Nếu JSON chỉ chứa các field mà không có cách xác định biến thể, consumer có thể không biết phải tạo CardPaymentEvent hay BankTransferEvent.

Jackson hỗ trợ polymorphic deserialization thông qua thông tin kiểu (type information). Hợp đồng JSON thường mang một discriminator như kind hoặc eventType để chỉ rõ kiểu con. Jackson dùng giá trị đó để chọn lớp Java phù hợp.

Không phải object nào cũng cần discriminator. Nếu endpoint luôn nhận một kiểu cụ thể, hoặc các biến thể được tách thành endpoint/schema riêng, kiểu con có thể đã được xác định từ ngữ cảnh. Chỉ thêm nhận diện kiểu khi nó giải quyết một nhu cầu thực tế của hợp đồng.

## 1. Đa hình trong Java và JSON

Trong Java, một biến có kiểu cha có thể tham chiếu đến nhiều kiểu con:

~~~java
abstract class PaymentEvent {
    private String eventId;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }
}

class CardPaymentEvent extends PaymentEvent {
    private String cardLastFour;

    public String getCardLastFour() {
        return cardLastFour;
    }

    public void setCardLastFour(String cardLastFour) {
        this.cardLastFour = cardLastFour;
    }
}

class BankTransferEvent extends PaymentEvent {
    private String bankReference;

    public String getBankReference() {
        return bankReference;
    }

    public void setBankReference(String bankReference) {
        this.bankReference = bankReference;
    }
}
~~~

Một biến có kiểu PaymentEvent có thể chứa instance CardPaymentEvent hoặc BankTransferEvent:

~~~java
PaymentEvent event = new CardPaymentEvent();
~~~

Khi làm việc trong Java, runtime object cho biết kiểu thực tế. Nhưng JSON không có khái niệm class Java. JSON chỉ chứa object, array, string, number, boolean và null.

Ví dụ:

~~~json
{
  "eventId": "evt-100",
  "cardLastFour": "4242"
}
~~~

Nếu khai báo kiểu đích là PaymentEvent, Jackson cần biết có phải tạo CardPaymentEvent hay không. Chỉ nhìn các field có thể suy luận được trong một số thiết kế, nhưng cách suy luận đó dễ mơ hồ khi các subtype có field trùng nhau hoặc schema thay đổi.

Một discriminator làm rõ hợp đồng:

~~~json
{
  "eventType": "card-payment",
  "eventId": "evt-100",
  "cardLastFour": "4242"
}
~~~

Giá trị eventType xác định biến thể. Consumer không cần đoán từ tên field.

## 2. Khi nào hợp đồng cần nhận diện kiểu con?

Nên cân nhắc type discriminator khi có một hoặc nhiều tình huống sau:

- Một property hoặc một phần tử collection được khai báo bằng interface hoặc abstract class nhưng payload có nhiều subtype.
- Một endpoint nhận nhiều loại event dùng chung envelope.
- Một message queue hoặc webhook có nhiều loại message cùng đi qua một topic/endpoint.
- Một field có thể chứa nhiều cấu trúc JSON khác nhau và consumer phải chọn DTO tương ứng.
- Cần giữ hợp đồng ổn định khi thêm subtype mới mà không đổi endpoint hoặc envelope.
- Consumer cần dispatch tới handler riêng theo loại payload.

Ví dụ các vị trí thường cần đa hình:

| Vị trí trong hợp đồng | Các biến thể | Lý do cần nhận diện |
|---|---|---|
| Event payload | OrderCreated, OrderCancelled, OrderShipped | Mỗi event có dữ liệu và handler riêng |
| Payment method | Card, BankTransfer, Wallet | Mỗi phương thức có field riêng |
| Notification content | Email, SMS, Push | Mỗi loại có cấu trúc recipient/content khác nhau |
| Rule configuration | RangeRule, RegexRule, ThresholdRule | Mỗi rule có tham số riêng |
| Workflow action | Approve, Reject, Escalate | Mỗi action có dữ liệu và hành vi riêng |
| Document item | Invoice, Receipt, CreditNote | Cùng một danh sách có nhiều loại tài liệu |

Ví dụ một danh sách event:

~~~json
[
  {
    "eventType": "order-created",
    "eventId": "e-1",
    "orderId": "o-10"
  },
  {
    "eventType": "order-cancelled",
    "eventId": "e-2",
    "orderId": "o-11",
    "reason": "CUSTOMER_REQUEST"
  }
]
~~~

Một List<OrderEvent> có thể chứa nhiều kiểu con. Discriminator giúp Jackson tạo đúng từng phần tử trong danh sách.

### 2.1. Khi không cần discriminator

Không cần polymorphic type metadata nếu kiểu đích đã rõ từ ngữ cảnh:

- Endpoint /orders chỉ nhận CreateOrderRequest.
- Endpoint /customers chỉ nhận CustomerRequest.
- Một property luôn có kiểu Address và không có subtype.
- Các biến thể đã được tách thành các endpoint hoặc message channel riêng.
- Consumer chỉ cần xử lý một cấu trúc JSON cố định.

Nếu mỗi endpoint đã có DTO cụ thể, thêm type discriminator chỉ làm payload phức tạp và tạo thêm quy tắc cần duy trì.

### 2.2. Khi nên dùng DTO riêng thay vì đa hình

Nếu hai payload có ít điểm chung và hành vi độc lập, hai DTO/endpoints có thể dễ hiểu hơn một hierarchy đa hình.

Ví dụ, CreateEmployeeRequest và CreateSupplierRequest có thể cùng có field name nhưng khác hẳn quy tắc validation và authorization. Không nhất thiết phải tạo một PersonRequest có nhiều subtype chỉ để tái sử dụng vài thuộc tính.

Đa hình phù hợp khi các subtype thực sự thuộc cùng một khái niệm trong domain và có thể được xử lý qua một abstraction chung.

## 3. Discriminator là một phần của hợp đồng dữ liệu

Discriminator là một property hoặc cấu trúc trong JSON dùng để xác định subtype. Các tên thường gặp:

- type
- kind
- eventType
- messageType
- payloadType
- schemaType

Ví dụ:

~~~json
{
  "kind": "bank-transfer",
  "eventId": "evt-200",
  "bankReference": "BNK-8891"
}
~~~

Giá trị discriminator nên là mã logic ổn định, được công bố trong schema hoặc tài liệu API.

Nên dùng tên như card-payment hoặc bank-transfer thay vì tên class Java như com.example.payment.CardPaymentEvent. Tên class là chi tiết triển khai; đổi package hoặc refactor class không nên buộc producer phải thay JSON.

Một discriminator tốt cần:

- Duy nhất trong phạm vi hierarchy.
- Có quy tắc casing rõ ràng.
- Ổn định qua các lần refactor.
- Có mô tả ý nghĩa và field bắt buộc của từng subtype.
- Có chính sách khi consumer nhận mã chưa biết.
- Có kế hoạch tương thích khi thêm subtype mới.

## 4. Khai báo subtype bằng @JsonTypeInfo và @JsonSubTypes

Cách phổ biến trong Jackson là đặt @JsonTypeInfo trên base class hoặc interface, sau đó khai báo các subtype được phép.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = OrderCreatedEvent.class,
        name = "order-created"
    ),
    @JsonSubTypes.Type(
        value = OrderCancelledEvent.class,
        name = "order-cancelled"
    )
})
public abstract class OrderEvent {
    public String eventId;
}
~~~

Các kiểu con:

~~~java
public class OrderCreatedEvent extends OrderEvent {
    public String orderId;
}

public class OrderCancelledEvent extends OrderEvent {
    public String orderId;
    public String reason;
}
~~~

JSON cho subtype thứ nhất:

~~~json
{
  "eventType": "order-created",
  "eventId": "e-1",
  "orderId": "o-10"
}
~~~

JSON cho subtype thứ hai:

~~~json
{
  "eventType": "order-cancelled",
  "eventId": "e-2",
  "orderId": "o-11",
  "reason": "CUSTOMER_REQUEST"
}
~~~

Đọc JSON:

~~~java
OrderEvent event = mapper.readValue(json, OrderEvent.class);
~~~

Jackson đọc eventType, tra subtype đã đăng ký và tạo class tương ứng.

### 4.1. Vai trò của từng annotation

| Annotation | Vai trò |
|---|---|
| @JsonTypeInfo | Bật xử lý thông tin kiểu và quy định cách tìm/đặt type id |
| @JsonSubTypes | Liệt kê các subtype và tên logic tương ứng |
| @JsonTypeName | Đặt tên logic cho một subtype |
| @JsonCreator | Chỉ định constructor/factory để tạo subtype nếu cần |
| @JsonProperty | Đặt tên hoặc metadata cho property thông thường |

@JsonSubTypes chỉ khai báo subtype; nó thường đi cùng @JsonTypeInfo để Jackson biết phải dùng type id trong quá trình deserialize.

### 4.2. Dùng @JsonTypeName trên subtype

Có thể chuyển tên subtype vào chính class con:

~~~java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("order-created")
public class OrderCreatedEvent extends OrderEvent {
    public String orderId;
}
~~~

Base class:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(OrderCreatedEvent.class),
    @JsonSubTypes.Type(OrderCancelledEvent.class)
})
public abstract class OrderEvent {
    public String eventId;
}
~~~

Tên @JsonTypeName giúp class tự công bố logical name của mình. Nếu không đặt tên rõ, Jackson có thể dùng tên đơn giản của class trong một số cách đăng ký; với hợp đồng công khai, nên khai báo mã rõ ràng và ổn định.

Có thể khai báo tên tại @JsonSubTypes.Type hoặc @JsonTypeName. Hãy thống nhất một nơi làm nguồn định nghĩa để tránh hai tên bị lệch nhau.

## 5. Chọn cách biểu diễn type id bằng @JsonTypeInfo.As

@JsonTypeInfo có thuộc tính include để xác định type id xuất hiện ở đâu trong JSON.

Các cách thường dùng:

| Include mode | Cấu trúc JSON | Khi phù hợp |
|---|---|---|
| PROPERTY | Discriminator là một property trong object | API/event envelope thông thường |
| EXISTING_PROPERTY | Dùng property thật của subtype làm type id | DTO đã có field type/kind |
| WRAPPER_OBJECT | Tên type id là key bao quanh object | Format cần wrapper object |
| WRAPPER_ARRAY | Type id và payload nằm trong array | Format compact hoặc giao thức đã quy định |
| EXTERNAL_PROPERTY | Type id nằm bên cạnh payload property | Một field cần subtype do sibling field quyết định |

### 5.1. PROPERTY: discriminator nằm trong object

Đây là lựa chọn thường dễ đọc nhất:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
~~~

JSON:

~~~json
{
  "kind": "card",
  "numberLastFour": "4242"
}
~~~

Consumer có thể nhìn payload và biết ngay object thuộc biến thể nào.

Với PROPERTY, type id thường được Jackson dùng như metadata và không tự động bind thành property Java thông thường. Nếu cần giữ giá trị discriminator trong field của subtype, xem tùy chọn visible ở phần sau.

### 5.2. EXISTING_PROPERTY: dùng property có sẵn trong DTO

Nếu subtype đã có property kind là dữ liệu nghiệp vụ, có thể dùng EXISTING_PROPERTY:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.EXISTING_PROPERTY,
    property = "kind",
    visible = true
)
public abstract class Notification {
    public String kind;
}
~~~

Subtype:

~~~java
public class EmailNotification extends Notification {
    public String email;
    public String subject;
}
~~~

Object cần cung cấp giá trị kind đúng với subtype, ví dụ:

~~~java
EmailNotification email = new EmailNotification();
email.kind = "email";
email.email = "user@example.com";
email.subject = "Welcome";
~~~

JSON:

~~~json
{
  "kind": "email",
  "email": "user@example.com",
  "subject": "Welcome"
}
~~~

EXISTING_PROPERTY hữu ích khi discriminator là một field thực sự của mô hình dữ liệu và được serialize như property thông thường. Cần bảo đảm giá trị field khớp subtype; nếu field kind có thể bị đặt sai, output có thể tự mâu thuẫn.

Tùy cách dùng, visible=true giúp type id tiếp tục được đưa vào quá trình bind property thay vì chỉ được tiêu thụ như metadata. Nếu subtype cần giữ field kind, hãy kiểm tra cả chiều đọc và ghi bằng test.

### 5.3. WRAPPER_OBJECT

Với WRAPPER_OBJECT, type id trở thành tên property bao quanh payload:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.WRAPPER_OBJECT
)
~~~

JSON:

~~~json
{
  "card": {
    "numberLastFour": "4242"
  }
}
~~~

Tên key card xác định subtype. Bên trong là object của subtype.

Cách này phù hợp với một số giao thức đã quy định wrapper, nhưng thường ít trực quan hơn PROPERTY khi cần nhìn các field chung như eventId cùng cấp với discriminator.

### 5.4. WRAPPER_ARRAY

WRAPPER_ARRAY đặt type id và payload trong một array:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.WRAPPER_ARRAY
)
~~~

JSON có dạng:

~~~json
[
  "card",
  {
    "numberLastFour": "4242"
  }
]
~~~

Consumer cần biết phần tử đầu là type id, phần tử thứ hai là object. Đây là cấu trúc có thứ tự nên phải tuân thủ đúng hợp đồng.

### 5.5. EXTERNAL_PROPERTY

EXTERNAL_PROPERTY đặt type id ở bên ngoài object payload, thường là sibling property:

~~~java
public class MessageEnvelope {

    public String messageId;

    @JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
        property = "payloadType"
    )
    @JsonSubTypes({
        @JsonSubTypes.Type(value = InvoicePayload.class, name = "invoice"),
        @JsonSubTypes.Type(value = RefundPayload.class, name = "refund")
    })
    public MessagePayload payload;
}
~~~

JSON:

~~~json
{
  "messageId": "m-10",
  "payloadType": "invoice",
  "payload": {
    "invoiceNumber": "INV-100",
    "amount": 250000
  }
}
~~~

EXTERNAL_PROPERTY phù hợp khi discriminator là metadata của envelope chứ không thuộc nội dung payload. Cách này được dùng ở ngữ cảnh property; không nên kỳ vọng nó hoạt động như PROPERTY khi đặt trên base class ở mọi vị trí.

Nếu payload bị thiếu hoặc payloadType không khớp, deserialization cần được kiểm thử để xác định lỗi và chính sách fallback.

## 6. Chọn loại type id bằng JsonTypeInfo.Id

@JsonTypeInfo.use quyết định cách Jackson xác định subtype từ type id.

| Id | Cách xác định | Đánh giá khi thiết kế hợp đồng |
|---|---|---|
| NAME | Tên logic được đăng ký | Thường phù hợp cho API/event |
| CLASS | Tên đầy đủ của class Java | Gắn chặt hợp đồng với triển khai, có rủi ro bảo mật |
| MINIMAL_CLASS | Tên class rút gọn theo package cơ sở | Vẫn phụ thuộc tên class/package |
| DEDUCTION | Suy luận từ tập property | Chỉ phù hợp khi các subtype có cấu trúc đủ khác biệt |
| CUSTOM | Bộ resolver do ứng dụng định nghĩa | Dùng khi cần quy tắc ánh xạ đặc biệt |

### 6.1. NAME: logical type id

Đây thường là lựa chọn tốt nhất cho hợp đồng công khai:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "type"
)
~~~

JSON:

~~~json
{
  "type": "bank-transfer",
  "reference": "BNK-100"
}
~~~

Tên bank-transfer không tiết lộ package hay tên class. Ứng dụng có thể đổi class BankTransferPayload thành BankTransferCommand mà không cần đổi hợp đồng nếu logical name được giữ nguyên.

### 6.2. CLASS và MINIMAL_CLASS

CLASS dùng tên class đầy đủ, ví dụ com.example.payment.CardPayment. MINIMAL_CLASS dùng dạng rút gọn dựa trên package context.

Hai cách này tạo sự phụ thuộc trực tiếp giữa JSON và cấu trúc class Java. Refactor package, đổi tên class hoặc di chuyển module có thể phá vỡ payload đã lưu hoặc client cũ.

Đặc biệt, không nên nhận class name tùy ý từ dữ liệu không tin cậy rồi để Jackson khởi tạo kiểu theo tên đó. Đây là ranh giới deserialization nhạy cảm và có thể mở ra nguy cơ khởi tạo kiểu ngoài dự kiến.

Với API, webhook, message broker và file upload, ưu tiên logical NAME với danh sách subtype được phép.

### 6.3. DEDUCTION: suy luận subtype từ property

Từ Jackson 2.12, có thể dùng Id.DEDUCTION trong một số trường hợp:

~~~java
@JsonTypeInfo(use = JsonTypeInfo.Id.DEDUCTION)
@JsonSubTypes({
    @JsonSubTypes.Type(CardPayload.class),
    @JsonSubTypes.Type(BankPayload.class)
})
public interface PaymentPayload {}
~~~

Ví dụ CardPayload có field cardLastFour, còn BankPayload có field bankReference. Jackson có thể suy luận subtype dựa trên tập tên property xuất hiện trong JSON.

Cách này không cần discriminator riêng, nhưng chỉ hoạt động khi các subtype có tập property đủ khác biệt để nhận diện.

Nếu hai subtype cùng có field amount và reference, hoặc một payload chỉ chứa các field chung, Jackson có thể không xác định được subtype duy nhất. Unknown property, field tùy chọn và schema evolution cũng có thể làm suy luận khó ổn định.

DEDUCTION không dựa trên giá trị field như "method": "card" theo cách discriminator tường minh; nó dựa vào dấu hiệu cấu trúc property. Vì vậy, chỉ dùng khi cấu trúc subtype thật sự phân biệt và được kiểm thử.

## 7. Nhận diện subtype trong List và Map

Polymorphic metadata đặc biệt hữu ích khi collection chứa nhiều subtype của cùng base type.

Ví dụ:

~~~java
List<OrderEvent> events = mapper.readValue(
    json,
    new TypeReference<List<OrderEvent>>() {}
);
~~~

JSON:

~~~json
[
  {
    "eventType": "order-created",
    "eventId": "e-1",
    "orderId": "o-10"
  },
  {
    "eventType": "order-cancelled",
    "eventId": "e-2",
    "orderId": "o-11",
    "reason": "DUPLICATE"
  }
]
~~~

Jackson xử lý từng phần tử theo base type OrderEvent, đọc discriminator và tạo subtype phù hợp.

Map cũng có thể chứa giá trị đa hình:

~~~java
Map<String, PaymentEvent> eventsById =
    mapper.readValue(
        json,
        new TypeReference<Map<String, PaymentEvent>>() {}
    );
~~~

Mỗi value cần có type metadata tương ứng. Nếu collection được khai báo bằng Object hoặc Map<String, Object>, Jackson không nhất thiết biết cần áp dụng hierarchy nào; hãy khai báo base type rõ ràng trong DTO hoặc TypeReference/JavaType.

## 8. Giữ discriminator trong property Java bằng visible

Mặc định, type id được Jackson dùng như metadata để chọn subtype. Sau khi chọn xong, nó thường không được bind như một property thông thường.

Nếu ứng dụng cần giữ eventType trong object:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType",
    visible = true
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = OrderCreatedEvent.class, name = "order-created"),
    @JsonSubTypes.Type(value = OrderCancelledEvent.class, name = "order-cancelled")
})
public abstract class OrderEvent {
    public String eventType;
    public String eventId;
}
~~~

visible=true cho phép type id tiếp tục đi vào quá trình deserialization của subtype. Khi đó property eventType có thể nhận giá trị order-created.

Chỉ bật visible khi ứng dụng thực sự cần field đó trong object. Nếu type id chỉ dùng để chọn subtype, để mặc định false sẽ tránh việc lưu trùng metadata trong mô hình Java.

Cần kiểm tra rằng property eventType không bị thay đổi thành giá trị mâu thuẫn với subtype khi serialize. Nếu cần một getter cố định cho từng subtype, có thể triển khai rõ ở class con.

## 9. Xử lý subtype không biết hoặc type id bị thiếu

Hợp đồng đa hình cần quy định điều gì xảy ra khi consumer nhận:

- Discriminator không xuất hiện.
- Discriminator có mặt nhưng giá trị null.
- Discriminator có giá trị chưa đăng ký.
- Discriminator có kiểu JSON sai.
- Discriminator hợp lệ nhưng payload thiếu field bắt buộc của subtype.
- Discriminator hợp lệ nhưng payload có field không phù hợp.

Ví dụ type id mới:

~~~json
{
  "eventType": "order-returned",
  "eventId": "e-9",
  "orderId": "o-20"
}
~~~

Nếu consumer chưa đăng ký OrderReturnedEvent, Jackson thường báo lỗi không tìm thấy subtype/type id. Đây là hành vi strict giúp phát hiện schema mới.

### 9.1. defaultImpl

@JsonTypeInfo có thuộc tính defaultImpl để chỉ định class fallback trong một số trường hợp type id không có hoặc không giải quyết được:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType",
    defaultImpl = UnknownOrderEvent.class
)
~~~

Default implementation phải có khả năng nhận payload theo cách Jackson có thể deserialize. Có thể dùng một DTO giữ các field chung hoặc JsonNode nếu cần giữ payload động.

Tuy nhiên, fallback không tự động bảo toàn raw type id trong mọi cấu hình. Nếu cần lưu chính xác mã chưa biết, hãy thiết kế field riêng hoặc giữ raw JSON. Cũng cần kiểm tra hành vi khi discriminator missing và khi discriminator unknown theo phiên bản Jackson và feature đang dùng.

Không nên dùng defaultImpl để biến mọi payload sai thành một object rỗng rồi tiếp tục nghiệp vụ. Unknown subtype có thể cần được cách ly hoặc báo lỗi.

### 9.2. FAIL_ON_INVALID_SUBTYPE

DeserializationFeature.FAIL_ON_INVALID_SUBTYPE điều khiển một số trường hợp subtype không thể giải quyết. Tắt feature có thể dẫn đến null cho trường hợp không xác định thay vì lỗi, tùy ngữ cảnh và cấu hình.

Không nên tắt feature toàn cục chỉ để bỏ qua một subtype mới. Nếu null fallback là hợp đồng, cần thể hiện rõ ở DTO/service và test rằng null không làm sai nghiệp vụ.

### 9.3. Chính sách khuyến nghị theo loại dữ liệu

| Dữ liệu | Hướng xử lý thường phù hợp |
|---|---|
| Lệnh thanh toán hoặc giao dịch | Strict, từ chối subtype không biết |
| Event có thể forward mà không xử lý | Giữ raw payload/type id hoặc quarantine |
| Metadata phụ cho giao diện | Có thể fallback nếu an toàn |
| Cấu hình workflow | Strict để tránh chạy sai hành động |
| Event versioned | Logical type id, schema version và rollout tương thích |

## 10. An toàn khi deserialize đa hình

Polymorphic deserialization làm Jackson tạo class dựa trên dữ liệu đầu vào. Vì vậy, danh sách kiểu được phép là một phần quan trọng của ranh giới tin cậy.

### 10.1. Ưu tiên logical NAME và allowlist subtype

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = SafeCardPayload.class, name = "card"),
    @JsonSubTypes.Type(value = SafeBankPayload.class, name = "bank")
})
public interface PaymentPayload {}
~~~

Consumer chỉ chấp nhận những subtype được công bố trong hierarchy. Producer không thể tùy ý yêu cầu Jackson khởi tạo bất kỳ class nào chỉ bằng cách gửi tên package.

Đăng ký subtype nên tập trung tại module cấu hình rõ ràng và được review như một thay đổi hợp đồng.

### 10.2. Tránh bật default typing rộng cho input không tin cậy

Jackson có default typing để thêm type metadata cho một số kiểu khai báo tổng quát. Không bật default typing rộng cho JSON đến từ HTTP, webhook, message broker, file upload hoặc nguồn không tin cậy.

Các cấu hình dùng CLASS/MINIMAL_CLASS hoặc default typing có thể làm dữ liệu đầu vào điều khiển kiểu Java được khởi tạo. Đây là rủi ro đáng kể nếu classpath có các kiểu có hành vi nguy hiểm khi được tạo hoặc deserialize.

Nếu một ứng dụng thật sự cần default typing trong một ranh giới được kiểm soát, cần dùng PolymorphicTypeValidator với allowlist hẹp và hiểu rõ phạm vi. Với hợp đồng API thông thường, logical type name cùng subtype được đăng ký rõ ràng thường đơn giản và an toàn hơn.

### 10.3. Không dùng Object làm base type quá rộng

Nếu một property khai báo Object, nhiều kiểu giá trị khác nhau có thể được chấp nhận. Điều đó làm giảm khả năng kiểm soát schema và tăng độ phức tạp của polymorphic binding.

Hãy tạo base interface/abstract class chỉ chứa các biến thể thực sự cùng domain. Một hierarchy nhỏ và có mục đích giúp allowlist dễ review và test hơn.

## 11. Phân biệt discriminator với schema version

Discriminator trả lời câu hỏi: object thuộc biến thể nào?

Schema version trả lời câu hỏi: payload tuân theo phiên bản cấu trúc nào?

Hai khái niệm có thể cùng xuất hiện:

~~~json
{
  "eventType": "order-created",
  "schemaVersion": 2,
  "eventId": "e-100",
  "orderId": "o-20",
  "source": "mobile"
}
~~~

eventType chọn subtype OrderCreatedEvent. schemaVersion cho biết phiên bản của hợp đồng event đó.

Không nên nhồi version vào tên subtype nếu hai chiều có thể thay đổi độc lập. Ví dụ order-created-v2 vừa trộn loại event vừa trộn version. Có thể dùng khi version thực sự tạo ra một subtype khác, nhưng phải công bố rõ quy ước.

Một consumer có thể cần cả hai bước:

1. Chọn loại event từ eventType.
2. Chọn cách đọc hoặc migrate dữ liệu theo schemaVersion.

Nếu chỉ thêm field mới mà subtype cũ vẫn tương thích, không nhất thiết tạo class con mới. Nếu cấu trúc và semantics thay đổi đáng kể, có thể cần versioned DTO hoặc adapter.

## 12. Khi nào dùng custom type resolver?

Các annotation tiêu chuẩn đủ cho phần lớn hợp đồng. Custom resolver có thể phù hợp khi:

- Type id được mã hóa theo quy tắc đặc thù.
- Nhiều alias cùng ánh xạ đến một subtype.
- Type id được tra từ registry nội bộ có allowlist.
- Có quy tắc tương thích giữa mã cũ và mã mới.
- Việc chọn subtype phụ thuộc metadata đã được chuẩn hóa.

Custom resolver cần được giới hạn và kiểm thử cẩn thận. Không dùng resolver để tải class tùy ý theo tên do payload gửi. Hãy ánh xạ qua danh sách subtype được phép.

Ví dụ đơn giản hơn là static registry trong code:

~~~java
Map<String, Class<? extends PaymentPayload>> TYPES = Map.of(
    "card", CardPayload.class,
    "bank", BankPayload.class
);
~~~

Một adapter có thể kiểm tra type id trong JsonNode rồi chọn class từ registry. Cách này hữu ích khi cần logic dispatch trước khi gọi databind. Tuy nhiên, nếu @JsonTypeInfo đã giải quyết được hợp đồng, không cần viết custom resolver chỉ để thay vài dòng annotation.

## 13. Thiết kế subtype sao cho hợp đồng dễ hiểu

Một hierarchy tốt nên có:

- Base type chứa field và semantics chung.
- Subtype chứa field riêng của biến thể.
- Discriminator có tên rõ và giá trị ổn định.
- Danh sách subtype được phép có chủ sở hữu.
- Validation riêng cho từng subtype.
- Quy tắc unknown subtype và version được công bố.

Ví dụ:

~~~text
PaymentEvent
    |
    +-- CardPaymentEvent
    |      - cardLastFour
    |      - authorizationCode
    |
    +-- BankTransferEvent
    |      - bankReference
    |      - bankCode
    |
    +-- WalletPaymentEvent
           - walletProvider
           - walletTransactionId
~~~

JSON tương ứng:

~~~json
{
  "type": "card",
  "amount": 150000,
  "cardLastFour": "4242"
}
~~~

~~~json
{
  "type": "bank-transfer",
  "amount": 150000,
  "bankReference": "BNK-8891",
  "bankCode": "VCB"
}
~~~

~~~json
{
  "type": "wallet",
  "amount": 150000,
  "walletProvider": "ExamplePay",
  "walletTransactionId": "w-100"
}
~~~

Không nên đưa field riêng của subtype lên base class chỉ để tránh polymorphic binding. Điều đó tạo nhiều field nullable và khiến một object có thể mang tổ hợp field không hợp lệ.

## 14. Kết hợp đa hình với validation

Jackson chọn subtype và bind field. Việc đó không tự chứng minh payload hợp lệ về nghiệp vụ.

Ví dụ:

~~~java
public class CardPaymentEvent extends PaymentEvent {
    @NotBlank
    public String cardLastFour;

    @NotBlank
    public String authorizationCode;
}
~~~

Sau khi deserialize, ứng dụng vẫn cần chạy Bean Validation hoặc validation domain cho subtype tương ứng.

Có thể tổ chức handler theo subtype:

~~~java
public void handle(PaymentEvent event) {
    switch (event) {
        case CardPaymentEvent card -> handleCard(card);
        case BankTransferEvent bank -> handleBank(bank);
        case WalletPaymentEvent wallet -> handleWallet(wallet);
    }
}
~~~

Pattern matching for switch phụ thuộc phiên bản Java. Với Java cũ hơn, dùng instanceof hoặc visitor pattern.

Điểm quan trọng là validation và xử lý nghiệp vụ nên nhận kiểu con đã được xác định. Đừng chỉ kiểm tra event.getClass().getSimpleName() hoặc tự suy đoán loại từ một field tùy ý.

## 15. Kiểm thử hợp đồng đa hình

Một bộ test nên xác nhận cả việc chọn subtype lẫn hình dạng JSON.

Ví dụ base type:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = OrderCreatedEvent.class, name = "order-created"),
    @JsonSubTypes.Type(value = OrderCancelledEvent.class, name = "order-cancelled")
})
public abstract class OrderEvent {
    public String eventId;
}
~~~

### 15.1. Test deserialize subtype đúng

~~~java
@Test
void readsOrderCreatedSubtype() throws Exception {
    String json = """
        {
          "eventType": "order-created",
          "eventId": "e-1",
          "orderId": "o-10"
        }
        """;

    OrderEvent event = mapper.readValue(json, OrderEvent.class);

    assertInstanceOf(OrderCreatedEvent.class, event);
    assertEquals("o-10", ((OrderCreatedEvent) event).orderId);
}
~~~

### 15.2. Test subtype khác

~~~java
@Test
void readsOrderCancelledSubtype() throws Exception {
    String json = """
        {
          "eventType": "order-cancelled",
          "eventId": "e-2",
          "orderId": "o-11",
          "reason": "DUPLICATE"
        }
        """;

    OrderEvent event = mapper.readValue(json, OrderEvent.class);

    assertInstanceOf(OrderCancelledEvent.class, event);
}
~~~

### 15.3. Test serialization giữ discriminator

Khi serialize qua base type, dùng writer có khai báo kiểu gốc để làm rõ ngữ cảnh:

~~~java
@Test
void writesTypeIdForBaseType() throws Exception {
    OrderCreatedEvent event = new OrderCreatedEvent();
    event.eventId = "e-1";
    event.orderId = "o-10";

    String json = mapper.writerFor(OrderEvent.class)
        .writeValueAsString(event);

    JsonNode tree = mapper.readTree(json);

    assertEquals("order-created", tree.path("eventType").asText());
}
~~~

### 15.4. Test unknown và missing discriminator

Nên kiểm tra:

- eventType có giá trị đã đăng ký.
- eventType chưa biết.
- eventType bị thiếu.
- eventType là null.
- eventType có kiểu number hoặc object.
- Payload thiếu field bắt buộc của subtype.
- Payload có field sai kiểu.
- Collection chứa nhiều subtype.
- Serialization và deserialization round-trip.
- Type id cũ vẫn được hỗ trợ khi đổi tên class hoặc nâng version.

Test JSON literal quan trọng hơn việc chỉ kiểm tra round-trip. Serializer và deserializer có thể cùng thay đổi theo một cách khiến round-trip vẫn thành công nhưng phá vỡ hợp đồng bên ngoài.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Base type là abstract/interface nhưng không có type metadata | Jackson không biết tạo subtype nào | Thêm discriminator hoặc dùng DTO cụ thể |
| Chỉ khai báo @JsonSubTypes | Có danh sách subtype nhưng thiếu cơ chế chọn type id | Kết hợp @JsonTypeInfo hoặc cơ chế resolver phù hợp |
| Dùng tên class làm type id công khai | Refactor package/class phá hợp đồng | Dùng Id.NAME với mã ổn định |
| Dùng DEDUCTION khi subtype có field trùng | Không suy luận được hoặc chọn không ổn định | Thêm discriminator tường minh |
| Bật default typing rộng | Input có thể điều khiển class được tạo | Dùng allowlist subtype và logical name |
| Không quy định unknown type | Consumer có thể lỗi hoặc bỏ dữ liệu không kiểm soát | Chọn strict, fallback hoặc raw payload |
| Dùng defaultImpl để nuốt mọi lỗi | Payload sai vẫn đi vào nghiệp vụ | Chỉ fallback khi có semantics rõ |
| Discriminator không khớp subtype field | Object serialize ra tự mâu thuẫn | Test type id và property hiện có |
| Khai báo base type quá rộng | Nhiều kiểu không liên quan lọt vào hierarchy | Dùng interface/abstract class theo domain |
| Không test collection polymorphic | Phần tử có thể bị deserialize sai kiểu | Test List<BaseType> và Map value |

## 17. Quy trình quyết định có cần nhận diện kiểu con

1. Xác định vị trí JSON có thể chứa nhiều biến thể hay không.
2. Xác định các biến thể có thực sự cùng một abstraction trong domain không.
3. Nếu kiểu đích luôn cố định theo endpoint, dùng DTO cụ thể.
4. Nếu cùng một base type có nhiều subtype, quyết định discriminator.
5. Chọn logical type id ổn định bằng JsonTypeInfo.Id.NAME cho hợp đồng bên ngoài.
6. Chọn cách đặt type id: PROPERTY thường là mặc định dễ hiểu; chọn mode khác khi schema yêu cầu.
7. Đăng ký allowlist subtype và định nghĩa unknown type policy.
8. Tách discriminator khỏi schema version nếu hai khái niệm độc lập.
9. Validate field riêng của từng subtype sau khi binding.
10. Test subtype đã biết, subtype mới, discriminator missing/null/sai kiểu và collection đa hình.
11. Kiểm tra tương thích khi thêm subtype hoặc đổi tên class.
12. Không bật default typing rộng cho input không tin cậy.

## 18. Nguyên tắc nên giữ

- Chỉ dùng polymorphic type metadata khi một vị trí JSON thực sự chứa nhiều subtype.
- Kiểu đích cụ thể theo endpoint thường không cần discriminator.
- Dùng discriminator logic như eventType hoặc kind, không gắn hợp đồng với package Java.
- @JsonTypeInfo bật cơ chế nhận diện; @JsonSubTypes hoặc registry định nghĩa subtype được phép.
- PROPERTY là lựa chọn dễ đọc cho phần lớn API/event.
- EXISTING_PROPERTY phù hợp khi discriminator đã là field của DTO.
- EXTERNAL_PROPERTY phù hợp khi type id nằm ở envelope bên ngoài payload property.
- DEDUCTION chỉ phù hợp khi các subtype có tập property đủ khác biệt.
- Quy định rõ hành vi với type id thiếu hoặc chưa biết.
- Ưu tiên allowlist và tránh default typing rộng với dữ liệu không tin cậy.
- Tách discriminator khỏi schema version khi chúng có vòng đời khác nhau.
- Test cả deserialize, serialize, collection, unknown subtype và backward compatibility.

Một hợp đồng cần nhận diện kiểu con khi consumer nhận nhiều biến thể object tại cùng một vị trí và phải tạo đúng class để xử lý. Discriminator tường minh giúp producer và consumer thống nhất loại payload, còn Jackson dùng @JsonTypeInfo cùng danh sách subtype để thực hiện binding. Hãy chọn logical type id ổn định, chỉ đăng ký các subtype được phép, quy định unknown type và kiểm thử thay đổi schema trước khi phát hành.

