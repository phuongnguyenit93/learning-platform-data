# Xử lý kiểu con không nhận diện và trường phân biệt bị thiếu

Trong JSON đa hình, một property có thể đại diện cho nhiều kiểu Java khác nhau. Ví dụ, payment có thể là thanh toán bằng thẻ, chuyển khoản hoặc ví điện tử; event có thể là sự kiện tạo đơn, hủy đơn hoặc hoàn tiền. Jackson cần biết kiểu con nào phải được tạo khi deserialize. Thông tin đó thường được truyền bằng một **trường phân biệt kiểu** (type discriminator), chẳng hạn kind, type hoặc eventType.

Vấn đề xuất hiện khi discriminator bị thiếu hoặc mang giá trị mà consumer chưa đăng ký. Đây là hai tình huống khác nhau: thiếu discriminator nghĩa là JSON không cung cấp thông tin chọn subtype; discriminator không nhận diện nghĩa là có cung cấp nhưng ID không ánh xạ tới subtype mà consumer biết. Một producer mới có thể thêm subtype trong khi consumer cũ vẫn đang chạy, nên chính sách xử lý cần được thiết kế rõ ràng.

Jackson hỗ trợ các cách xử lý như defaultImpl trong @JsonTypeInfo, feature FAIL_ON_INVALID_SUBTYPE, visible, @JsonAnySetter, đăng ký subtype bằng tên và cơ chế suy luận subtype từ property. Không có một lựa chọn phù hợp cho mọi API. Hãy chọn giữa từ chối, fallback, giữ payload chưa biết hoặc xử lý theo version dựa trên yêu cầu tương thích và mức độ quan trọng của dữ liệu.

## 1. Discriminator trong JSON đa hình

Một hợp đồng đa hình thường dùng một property để chỉ subtype:

```json
{
  "payment": {
    "kind": "card",
    "cardNumber": "****1234",
    "lastFour": "1234"
  }
}
```

Giá trị kind là discriminator. Jackson dùng nó để chọn class CardPayment. Một payload khác có thể dùng cùng property payment nhưng chọn subtype chuyển khoản:

```json
{
  "payment": {
    "kind": "bank-transfer",
    "bankCode": "ABC",
    "accountReference": "ref-82"
  }
}
```

Nếu consumer chỉ biết card và bank-transfer, các tình huống sau cần được xử lý:

| JSON đầu vào | Tình huống | Câu hỏi |
|---|---|---|
| Có "kind": "card" | Type ID đã đăng ký | Tạo CardPayment. |
| Có "kind": "crypto" | Type ID chưa biết | Từ chối, fallback hay giữ payload? |
| Không có kind | Missing type ID | Có subtype mặc định không? |
| Có "kind": null | Explicit null | Xử lý như missing hay từ chối? |
| Có "kind": "" | ID rỗng | Có phải ID hợp lệ không? |

Không nên gộp mọi trường hợp thành “Jackson không tìm được class”. Một ID lạ thường cho biết producer đã mở rộng schema; một ID bị thiếu có thể do payload cũ, lỗi producer hoặc client bỏ quên field bắt buộc.

## 2. Khai báo subtype bằng @JsonTypeInfo và @JsonSubTypes

Ví dụ model thanh toán:

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
public abstract class Payment {
}

public class CardPayment extends Payment {
    private String cardNumber;
    private String lastFour;
    // Getters and setters
}

public class BankTransfer extends Payment {
    private String bankCode;
    private String accountReference;
    // Getters and setters
}
```

Khi deserialize:

```java
Payment payment = mapper.readValue(json, Payment.class);
```

Jackson đọc property kind, tìm tên subtype trong metadata và tạo class tương ứng. Id.NAME dùng tên logic do ứng dụng định nghĩa, không buộc JSON phải chứa tên class Java.

Có thể đặt tên subtype bằng @JsonTypeName trên class thay vì khai báo toàn bộ tên ở @JsonSubTypes:

```java
@JsonTypeName("card")
public class CardPayment extends Payment {
    // ...
}
```

Dù dùng annotation hay đăng ký bằng ObjectMapper.registerSubtypes(...), hãy giữ danh sách subtype được phép rõ ràng. ID trong JSON là một phần của API contract, vì vậy nên ổn định và không phụ thuộc package/class name nội bộ.

## 3. Phân biệt type ID bị thiếu và type ID không nhận diện

Hai payload minh họa:

```json
{
  "amount": 1200
}
```

```json
{
  "kind": "crypto",
  "amount": 1200,
  "wallet": "wallet-9"
}
```

Payload đầu không có discriminator. Payload thứ hai có discriminator nhưng crypto chưa được consumer đăng ký. Khi không có fallback phù hợp, Jackson thường báo lỗi mapping cho cả hai trường hợp vì không xác định được subtype cụ thể.

Với cấu hình mặc định thông thường, DeserializationFeature.FAIL_ON_INVALID_SUBTYPE được bật. Feature này khiến Jackson báo lỗi khi type ID không thể ánh xạ tới subtype hợp lệ, bao gồm trường hợp không có type ID trong các cấu hình đa hình cần ID. Cấu hình mapper/framework có thể thay đổi default, nên hãy kiểm tra mapper thực tế của ứng dụng.

```java
ObjectMapper strictMapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
```

Nếu tắt feature mà không khai báo defaultImpl, Jackson có thể trả về null cho giá trị đa hình không giải quyết được:

```java
ObjectMapper lenientMapper = new ObjectMapper()
    .disable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
```

Đây là hành vi có thể làm mất dữ liệu âm thầm. Property payment có thể trở thành null dù JSON chứa một object có nội dung. Nếu ứng dụng không kiểm tra null sau deserialize, lỗi có thể chỉ xuất hiện ở một bước xử lý phía sau.

Không nên tắt FAIL_ON_INVALID_SUBTYPE toàn cục chỉ để bỏ qua một subtype mới. Nếu muốn hỗ trợ payload chưa biết, dùng fallback cụ thể hoặc một representation có thể giữ dữ liệu.

## 4. Dùng defaultImpl làm subtype fallback

@JsonTypeInfo có thuộc tính defaultImpl. Nó chỉ định class dùng khi type ID không có hoặc không ánh xạ được tới subtype đã đăng ký. Class fallback phải tương thích với kiểu base và có thể được khởi tạo bởi Jackson.

Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind",
    defaultImpl = UnknownPayment.class
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public abstract class Payment {
}

public class UnknownPayment extends Payment {
    // Fallback implementation
}
```

Với cấu hình này, card và bank-transfer vẫn ánh xạ tới subtype tương ứng. Type ID như crypto hoặc payload thiếu kind có thể được ánh xạ vào UnknownPayment.

### 4.1. Fallback phải có ý nghĩa nghiệp vụ

Không nên dùng một subtype mặc định giả vờ là subtype đã biết. Ví dụ, nếu payload crypto được ánh xạ thành CardPayment, ứng dụng có thể đọc nhầm field hoặc thực hiện logic xử lý thanh toán sai.

Một fallback nên thể hiện rõ trạng thái chưa nhận diện, chẳng hạn:

- Giữ lại ID subtype nhận được nếu có.
- Lưu các property chưa biết để xử lý hoặc chuyển tiếp sau.
- Không cho phép thực thi hành động nghiệp vụ đòi hỏi subtype đã xác minh.
- Cung cấp thông tin để log/metric và theo dõi producer mới.

Nếu payload cần được xử lý ngay để thay đổi trạng thái tài chính, quyền hạn hoặc dữ liệu quan trọng, từ chối subtype chưa biết thường an toàn hơn fallback tiếp tục xử lý.

### 4.2. defaultImpl không tự giữ toàn bộ payload

defaultImpl chỉ chọn class fallback. Nó không tự động lưu mọi property mà class đó không khai báo. Nếu muốn giữ field tương lai, fallback class cần có extension map, ví dụ với @JsonAnySetter:

```java
public class UnknownPayment extends Payment {
    private final Map<String, JsonNode> extra = new LinkedHashMap<>();

    @JsonAnySetter
    public void capture(String name, JsonNode value) {
        extra.put(name, value);
    }

    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
```

JsonNode giữ được cấu trúc JSON của value chưa biết, gồm object, array, string, number, boolean và null. Cách này hữu ích khi consumer cần lưu hoặc chuyển tiếp payload trong khi chưa hiểu schema mới.

Nếu cần serialize lại các field mở rộng ở cùng cấp object, có thể bổ sung @JsonAnyGetter cho map. Hãy kiểm thử round-trip với discriminator và các field trùng tên để bảo đảm output đúng contract; không giả định mọi cấu hình type metadata đều tự động flatten extension map như mong muốn.

## 5. Giữ discriminator trong object bằng visible = true

Theo mặc định, khi Jackson dùng property làm type ID, property đó được tiêu thụ để chọn subtype và không nhất thiết được gán như một property bình thường của POJO. Nếu class cần đọc lại giá trị discriminator, đặt visible = true.

Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind",
    visible = true,
    defaultImpl = UnknownPayment.class
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public abstract class Payment {
    private String kind;

    public String getKind() { return kind; }
    public void setKind(String kind) { this.kind = kind; }
}
```

Với visible = true, type ID được chuyển tiếp vào quá trình deserialize như property thông thường. UnknownPayment có thể giữ kind = "crypto" để biết producer đã gửi subtype nào chưa được hỗ trợ. Khi discriminator bị thiếu, kind vẫn không có giá trị.

Nếu visible vẫn là false (mặc định), không nên trông đợi getter getKind() của POJO chứa type ID chỉ vì JSON có property kind. Nếu cần lưu ID, hãy bật visible và khai báo property tương ứng, hoặc dùng một cơ chế xử lý riêng.

Khi bật visible = true, các subtype đã biết cũng nhận discriminator như property bình thường. Base class hoặc subtype cần có property phù hợp, hoặc một any-setter có chủ đích; nếu không, strict unknown-property handling có thể coi discriminator là field lạ sau khi type resolver đã dùng nó.

## 6. Xử lý type ID thiếu khác explicit null

Các payload sau không hoàn toàn giống nhau:

```json
{ "amount": 1200 }
```

```json
{ "kind": null, "amount": 1200 }
```

```json
{ "kind": "", "amount": 1200 }
```

Đầu tiên là discriminator bị thiếu. Payload thứ hai có property nhưng giá trị null. Payload thứ ba có string rỗng, không phải null. Tùy đường xử lý type resolver và phiên bản Jackson, null/empty có thể đi qua nhánh xử lý type ID không hợp lệ; không nên coi chúng là ID subtype hợp lệ.

Nếu hợp đồng cần phân biệt chính xác missing với explicit null, hãy kiểm tra presence ở tree/token layer hoặc dùng custom deserialization strategy. defaultImpl cung cấp fallback cho trường hợp không có/không giải quyết được type ID, nhưng không phải công cụ validation đầy đủ cho mọi quy tắc nghiệp vụ của discriminator.

Ví dụ kiểm tra trước bằng tree:

```java
JsonNode root = mapper.readTree(json);

if (!root.has("kind")) {
    // Discriminator không xuất hiện.
} else if (root.get("kind").isNull()) {
    // Discriminator xuất hiện với explicit null.
} else if (!root.get("kind").isTextual()
        || root.get("kind").textValue().isBlank()) {
    // Sai kiểu hoặc ID rỗng.
} else {
    // Có ID dạng chuỗi; vẫn cần xác nhận ID có được đăng ký.
}
```

Với payload lớn cần streaming, có thể kiểm tra token FIELD_NAME có tên kind, sau đó xác nhận token value và giá trị text. Nếu cần deserialize subtype sau bước kiểm tra, hãy giữ payload hoặc xây dựng parser strategy phù hợp để không phải đọc input hai lần.

## 7. Dùng Id.DEDUCTION khi không có discriminator tường minh

Trong một số schema, producer không gửi field kind. Jackson có thể suy luận subtype dựa trên tên property đặc trưng bằng JsonTypeInfo.Id.DEDUCTION (hỗ trợ từ Jackson 2.12).

Ví dụ:

```java
@JsonTypeInfo(use = JsonTypeInfo.Id.DEDUCTION)
@JsonSubTypes({
    @JsonSubTypes.Type(CardPayment.class),
    @JsonSubTypes.Type(BankTransfer.class)
})
public abstract class Payment {
}

public class CardPayment extends Payment {
    private String cardToken;
    private String lastFour;
    // Getters and setters
}

public class BankTransfer extends Payment {
    private String bankCode;
    private String accountReference;
    // Getters and setters
}
```

JSON có các property đặc trưng của CardPayment có thể được suy luận thành subtype thẻ; JSON có bankCode và accountReference có thể được suy luận thành chuyển khoản.

DEDUCTION không đọc giá trị property để suy luận theo nội dung nghiệp vụ; cơ chế chủ yếu dựa vào tập tên property có mặt trong input. Vì vậy:

- Nếu payload không có đủ field đặc trưng, Jackson có thể không phân biệt được subtype.
- Nếu hai subtype có tập property chồng lấn, payload có thể mơ hồ.
- Nếu payload rỗng hoặc chỉ chứa field chung, không có đủ thông tin để chọn subtype.
- Việc thêm property mới có thể ảnh hưởng khả năng suy luận và tính tương thích.

DEDUCTION không phải cách tổng quát để tự đoán class khi discriminator bị quên. Chỉ dùng khi schema có các field nhận diện đủ khác biệt và được kiểm soát. Nếu subtype mới xuất hiện, consumer cũ vẫn có thể không suy luận được.

## 8. Đăng ký subtype bằng tên ổn định

Tên subtype là một phần của giao thức. Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(BankTransfer.class, "bank-transfer")
);
```

Đăng ký này có thể dùng thay cho hoặc kết hợp với annotation tùy kiến trúc. Dùng ID có ý nghĩa nghiệp vụ ổn định như card, bank-transfer, refund; tránh gửi tên class đầy đủ như com.example.payment.CardPayment.

### 8.1. Vì sao nên thận trọng với Id.CLASS

JsonTypeInfo.Id.CLASS dùng tên class Java làm type ID. Nó làm lộ cấu trúc package và gắn chặt JSON contract với tên class nội bộ. Với input không đáng tin cậy, cơ chế polymorphic typing rộng còn có thể mở rộng bề mặt tấn công nếu cho phép khởi tạo kiểu ngoài dự kiến.

Với API công khai hoặc message từ hệ thống khác, thường nên dùng Id.NAME cùng danh sách subtype được phép. Nếu dùng default typing hoặc class-based polymorphism, cần cấu hình giới hạn kiểu được phép theo hướng dẫn bảo mật của Jackson version đang sử dụng.

## 9. Xử lý subtype chưa biết bằng policy rõ ràng

Không có một policy đúng cho mọi hệ thống. Có thể chọn:

| Policy | Khi nào phù hợp | Cách thực hiện |
|---|---|---|
| Strict reject | Command, thanh toán, quyền hạn, dữ liệu cần hiểu đầy đủ | Không khai báo fallback; giữ FAIL_ON_INVALID_SUBTYPE bật. |
| Fallback subtype | Consumer cần tiếp tục nhận message nhưng có thể cách ly loại chưa biết | defaultImpl là class rõ nghĩa như UnknownEvent. |
| Capture unknown payload | Gateway/event relay cần lưu hoặc chuyển tiếp schema mới | Fallback class dùng @JsonAnySetter/JsonNode. |
| Version-specific handling | Thay đổi subtype là thay đổi contract lớn | DTO và mapping riêng theo API/event version. |
| Custom resolution | ID đến từ registry hoặc quy tắc ánh xạ đặc biệt | TypeIdResolver hoặc custom deserializer có allowlist. |

Không nên chọn fallback chỉ vì muốn hệ thống không phát sinh exception. Nếu consumer không biết semantics của subtype, việc tiếp tục xử lý như một subtype đã biết có thể gây sai dữ liệu nghiêm trọng.

### 9.1. Strict reject

Với strict policy, không cấu hình defaultImpl và giữ feature:

```java
ObjectMapper mapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
```

Producer gửi type ID mới sẽ nhận lỗi mapping. Ở ranh giới API/message, chuyển lỗi này thành response hoặc dead-letter policy phù hợp; không trả stack trace nội bộ cho client.

### 9.2. Fallback và cách ly xử lý nghiệp vụ

Nếu dùng UnknownEvent, hãy để luồng nghiệp vụ nhận diện trạng thái này:

```java
if (event instanceof UnknownEvent unknown) {
    unknownEventStore.save(unknown);
    return;
}

processKnownEvent(event);
```

Ví dụ này lưu/cách ly payload chưa biết và không gọi logic xử lý subtype đã biết. Tên subtype, raw fields, source và version có thể được lưu cùng metadata để phục vụ replay sau khi consumer được nâng cấp.

## 10. Fallback class và unknown fields với JsonNode

Một fallback hữu ích có thể giữ nguyên các property chưa biết:

```java
public class UnknownEvent extends DomainEvent {
    private final Map<String, JsonNode> fields = new LinkedHashMap<>();

    @JsonAnySetter
    public void addField(String name, JsonNode value) {
        fields.put(name, value);
    }

    public Map<String, JsonNode> getFields() {
        return fields;
    }
}
```

Nếu base class khai báo discriminator kind với visible = true, giá trị type ID có thể được gán vào property base class trong khi các property còn lại được capture bởi any-setter. Cần bảo đảm tên discriminator không bị coi là extension field hoặc bị ghi đè ngoài ý muốn.

Nếu cần round-trip payload, cân nhắc @JsonAnyGetter:

```java
@JsonAnyGetter
public Map<String, JsonNode> getFields() {
    return fields;
}
```

Khi serialize lại, extension map có thể được ghi ở cùng cấp object. Hãy kiểm tra trường hợp key trong map trùng với property đã biết hoặc discriminator; không nên cho phép dữ liệu mở rộng ghi đè field chuẩn.

Với yêu cầu bảo toàn byte-for-byte hoặc thứ tự/format gốc, JsonNode chưa đủ vì nó giữ cấu trúc JSON chứ không giữ nguyên cách viết whitespace, escape hay thứ tự lexical như chuỗi gốc trong mọi tình huống. Nếu cần giữ raw payload, lưu riêng raw JSON bytes/string hoặc dùng cơ chế lưu message gốc.

## 11. Custom TypeIdResolver và DeserializationProblemHandler

Khi tên subtype đến từ registry hoặc cần ánh xạ theo tenant/version, @JsonSubTypes tĩnh có thể không đủ. Jackson cho phép triển khai TypeIdResolver để ánh xạ giữa type ID và JavaType.

Một resolver nên:

- Chỉ trả về các subtype đã được cho phép.
- Xử lý ID không biết theo policy được công bố.
- Không nạp class tùy ý dựa trên chuỗi do client gửi.
- Cung cấp danh sách ID hợp lệ cho lỗi/logging nếu có thể.
- Có test cho ID hợp lệ, ID lạ, null và missing.

DeserializationProblemHandler cũng có hook để ứng dụng can thiệp khi type ID không giải quyết được hoặc bị thiếu, tùy API của Jackson version. Đây là lựa chọn nâng cao khi cần policy tập trung. Với một DTO hoặc một subtype fallback đơn giản, defaultImpl thường dễ cấu hình và dễ hiểu hơn.

Nếu viết resolver/handler, tránh trả về subtype mặc định chỉ để nuốt lỗi. Hãy ghi nhận ID lạ và bảo đảm object được trả về có trạng thái thể hiện rõ rằng nó chưa được nhận diện.

## 12. As.PROPERTY, As.EXISTING_PROPERTY và As.EXTERNAL_PROPERTY

Discriminator có thể nằm ở những vị trí khác nhau trong JSON:

### 12.1. As.PROPERTY

Type ID nằm trong chính object:

```json
{
  "kind": "card",
  "cardNumber": "****1234"
}
```

Đây là cách phổ biến và dễ đọc. property = "kind" xác định tên discriminator.

### 12.2. As.EXISTING_PROPERTY

Discriminator cũng là property thực của subtype và serializer dùng property đó làm type ID:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.EXISTING_PROPERTY,
    property = "kind",
    visible = true
)
```

Cách này phù hợp khi model đã có property kind và muốn nó vừa mang dữ liệu domain vừa đóng vai trò discriminator. Phải bảo đảm giá trị property luôn khớp subtype; nếu CardPayment có kind = "bank-transfer", representation sẽ mâu thuẫn.

### 12.3. As.EXTERNAL_PROPERTY

Type ID nằm bên ngoài object đa hình:

```json
{
  "paymentKind": "card",
  "payment": {
    "cardNumber": "****1234"
  }
}
```

Kiểu này hữu ích khi discriminator thuộc về object cha. Cần đặt annotation đúng property và kiểm thử cả thứ tự xuất hiện của external type ID so với value property. Missing external type ID cũng cần policy rõ ràng; không nên giả định nó sẽ được suy ra từ các field bên trong.

## 13. Xử lý discriminator khi deserialize theo tree hoặc streaming

Nếu cần phân biệt missing, null, empty và unknown trước khi tạo subtype, có thể đọc một lớp ngoài thành JsonNode:

```java
JsonNode root = mapper.readTree(json);
JsonNode paymentNode = root.path("payment");

if (!paymentNode.isObject()) {
    throw new IllegalArgumentException("payment must be an object");
}

JsonNode kindNode = paymentNode.get("kind");
if (kindNode == null) {
    throw new IllegalArgumentException("Missing payment kind");
}
if (!kindNode.isTextual() || kindNode.textValue().isBlank()) {
    throw new IllegalArgumentException("Invalid payment kind");
}

Payment payment = mapper.treeToValue(paymentNode, Payment.class);
```

Ví dụ này phù hợp khi payload vừa phải và cần kiểm tra schema trước khi binding. treeToValue vẫn dùng polymorphic metadata của Payment, do đó ID chưa biết sẽ theo policy đã cấu hình.

Với payload lớn, có thể dùng JsonParser để đọc object và kiểm tra discriminator mà không materialize toàn bộ tree. Tuy nhiên, nếu muốn chuyển sang databinding sau khi đã đọc qua stream, cần buffer phần JSON hoặc dùng parser strategy có thể replay. Không thể tùy tiện đọc hết stream rồi mong ObjectMapper đọc lại cùng parser ở đầu input.

## 14. Versioning khi producer thêm subtype mới

Giả sử producer v1 chỉ gửi:

```json
{ "kind": "card", "lastFour": "1234" }
```

Producer v2 bổ sung:

```json
{ "kind": "crypto", "wallet": "wallet-9", "network": "chain-x" }
```

Consumer v1 không biết crypto. Có các hướng triển khai:

1. Nâng cấp consumer để đăng ký subtype mới trước khi producer phát loại message đó.
2. Tạo version event/schema mới nếu subtype làm thay đổi semantics lớn.
3. Dùng fallback chỉ để lưu/cách ly message, sau đó replay khi consumer đã nâng cấp.
4. Nếu consumer chỉ làm relay, capture raw fields và chuyển tiếp mà không diễn giải payload.

Thêm subtype có thể tương thích nếu consumer được thiết kế để bỏ qua hoặc lưu type ID chưa biết. Nhưng với consumer phải thực hiện nghiệp vụ, subtype mới thường không thể được xử lý đúng chỉ bằng cách bỏ qua.

### 14.1. Triển khai consumer trước producer

Một thứ tự rollout an toàn thường là:

1. Phát hành consumer có khả năng nhận diện subtype mới hoặc cách ly subtype chưa biết.
2. Xác nhận consumer mới đã hoạt động trên các instance/partition cần thiết.
3. Sau đó mới bật producer phát subtype mới.
4. Theo dõi tỷ lệ fallback, lỗi type ID và dead-letter.
5. Gỡ fallback tạm thời nếu policy cuối cùng yêu cầu strict và mọi producer đã đồng bộ.

Nếu producer được triển khai trước, consumer cũ có thể bắt đầu lỗi ngay khi message mới đến. Với event queue, cần quyết định retry, dead-letter và replay để message không bị mất hoặc retry vô hạn.

### 14.2. Không tái sử dụng type ID cho semantics khác

Một type ID đã công bố nên giữ cùng ý nghĩa qua các phiên bản. Nếu card ban đầu nghĩa là thẻ ngân hàng nhưng sau này được dùng cho ví điện tử, consumer cũ có thể tạo đúng class nhưng hiểu sai semantics. Hãy tạo ID mới hoặc version hóa event khi ý nghĩa thay đổi không tương thích.

## 15. Kiểm thử các tình huống đa hình

Test nên bao gồm cả subtype đã biết, ID chưa biết, discriminator thiếu và payload không hợp lệ.

### 15.1. Subtype đã đăng ký

```java
@Test
void readsKnownSubtype() throws Exception {
    String json = """
        {"kind":"card","lastFour":"1234"}
        """;

    Payment payment = mapper.readValue(json, Payment.class);

    assertInstanceOf(CardPayment.class, payment);
}
```

### 15.2. Unknown subtype với strict policy

```java
@Test
void rejectsUnknownSubtypeWhenNoFallbackExists() {
    ObjectMapper strict = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);

    String json = """
        {"kind":"crypto","wallet":"wallet-9"}
        """;

    assertThrows(JsonMappingException.class, () ->
        strict.readValue(json, PaymentWithoutFallback.class)
    );
}
```

PaymentWithoutFallback là base type được cấu hình cùng subtype đã biết nhưng không có defaultImpl. Kiểu exception cụ thể có thể khác theo đường đọc/phiên bản; test ở tầng API nên kiểm tra lỗi mapping được chuyển thành response hoặc dead-letter outcome đúng hợp đồng.

### 15.3. Missing discriminator với fallback

```java
@Test
void usesFallbackWhenTypeIdIsMissing() throws Exception {
    String json = """
        {"amount":1200}
        """;

    Payment payment = mapper.readValue(json, Payment.class);

    assertInstanceOf(UnknownPayment.class, payment);
}
```

### 15.4. Unknown discriminator được giữ lại

```java
@Test
void capturesUnknownTypeIdAndAdditionalFields() throws Exception {
    String json = """
        {
          "kind": "crypto",
          "wallet": "wallet-9",
          "network": "chain-x"
        }
        """;

    UnknownPayment payment =
        (UnknownPayment) mapper.readValue(json, Payment.class);

    assertEquals("crypto", payment.getKind());
    assertEquals("wallet-9", payment.getExtra().get("wallet").asText());
    assertEquals("chain-x", payment.getExtra().get("network").asText());
}
```

Test này yêu cầu visible = true và fallback class có property kind cùng any-setter phù hợp.

### 15.5. Missing khác explicit null

Nếu contract phân biệt hai trường hợp, test riêng:

- JSON không có kind.
- JSON có "kind": null.
- JSON có "kind": "".
- JSON có "kind": 123.
- JSON có "kind": "not-registered".

Xác nhận từng trường hợp đi đến fallback hoặc validation error như đã định nghĩa. Đừng chỉ test một payload ID lạ rồi cho rằng mọi trường hợp discriminator lỗi đã được xử lý.

### 15.6. Kiểm thử round-trip và nested polymorphism

Nếu subtype xuất hiện trong list, map hoặc object lồng, test cả cấu trúc cha:

```json
{
  "events": [
    { "kind": "created", "orderId": "o-1" },
    { "kind": "cancelled", "reason": "duplicate" }
  ]
}
```

Xác nhận type ID được phát đúng khi serialize và subtype được tạo đúng khi deserialize. Nếu dùng fallback capture, test việc serialize lại để bảo đảm extension fields không ghi đè discriminator hoặc field chuẩn.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Deserialize báo thiếu type ID | JSON không có discriminator trong As.PROPERTY | Bổ sung field hoặc cấu hình fallback có chủ đích. |
| Unknown subtype làm request lỗi | Type ID chưa đăng ký và strict feature đang bật | Đăng ký subtype, version hóa hoặc dùng fallback/capture. |
| Object đa hình trở thành null | FAIL_ON_INVALID_SUBTYPE bị tắt và không có fallback | Tránh tắt feature toàn cục; kiểm tra null hoặc dùng defaultImpl. |
| Fallback không giữ type ID | visible đang false | Bật visible = true và khai báo property discriminator. |
| Fallback mất field tương lai | Class fallback không có any-setter/tree map | Capture extension field bằng JsonNode. |
| Field lạ bị gán vào property sai | Dùng default subtype không phù hợp | Tạo subtype Unknown riêng, không giả dạng subtype đã biết. |
| DEDUCTION báo mơ hồ | Các subtype có tập property trùng nhau | Dùng discriminator tường minh hoặc thiết kế field nhận diện riêng. |
| ID subtype thay đổi khi refactor package | Dùng Id.CLASS hoặc tên class làm contract | Dùng Id.NAME với ID ổn định. |
| Fallback xử lý message như subtype hợp lệ | Không phân nhánh UnknownPayment ở service | Cách ly/lưu message và không gọi logic subtype đã biết. |

## 17. Quy trình chọn cách xử lý

1. Xác định discriminator là bắt buộc hay có thể thiếu theo contract.
2. Liệt kê subtype được phép và đặt ID ổn định bằng Id.NAME.
3. Quyết định unknown ID là lỗi, fallback, capture hay phải đi qua version mới.
4. Nếu dùng fallback, tạo class riêng thể hiện trạng thái unknown; không ánh xạ sang subtype gần giống.
5. Nếu cần giữ type ID trong object, bật visible = true và khai báo property discriminator.
6. Nếu cần giữ field chưa biết, dùng @JsonAnySetter với JsonNode; cân nhắc @JsonAnyGetter nếu cần serialize lại.
7. Giữ FAIL_ON_INVALID_SUBTYPE bật cho các luồng cần strict; tránh trả null âm thầm.
8. Chỉ dùng Id.DEDUCTION khi các subtype có tập property nhận diện đủ rõ.
9. Với registry động hoặc quy tắc phức tạp, cân nhắc TypeIdResolver/handler có allowlist.
10. Kiểm thử ID đã biết, ID lạ, missing, null, empty, sai kiểu, subtype lồng và round-trip.
11. Rollout consumer hỗ trợ subtype mới trước producer khi hệ thống cho phép.
12. Theo dõi fallback/dead-letter để biết khi nào có thể loại bỏ cơ chế tương thích tạm thời.

Xử lý kiểu con không nhận diện và discriminator bị thiếu là một quyết định về hợp đồng đa hình. defaultImpl giúp chọn fallback, visible giúp giữ type ID như dữ liệu của object, còn @JsonAnySetter có thể lưu field tương lai. Với luồng cần hiểu chính xác semantics, hãy giữ strict mode và từ chối subtype lạ. Với gateway hoặc consumer cần bảo toàn message, hãy capture và cách ly payload. Dù chọn cách nào, đừng để type ID không biết bị biến thành một subtype đã biết hoặc thành null mà không có dấu hiệu rõ ràng.
