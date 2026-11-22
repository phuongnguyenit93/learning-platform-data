# Quản lý giá trị enum và kiểu con mới

Enum và kiểu con đa hình thường được dùng để mô tả trạng thái, loại sự kiện, phương thức thanh toán hoặc các biến thể của một mô hình dữ liệu. Khi ứng dụng trao đổi JSON với nhiều service hoặc nhiều phiên bản client, tập giá trị này có thể thay đổi theo thời gian: producer bắt đầu gửi một enum constant mới hoặc một subtype mới, trong khi consumer cũ chưa được cập nhật.

Nếu consumer không biết giá trị mới, Jackson có thể từ chối deserialize. Đây thường là hành vi an toàn vì dữ liệu không bị diễn giải sai. Tuy nhiên, một hợp đồng dữ liệu cần có chính sách tương thích rõ ràng: khi nào từ chối, khi nào ánh xạ về UNKNOWN, khi nào giữ payload để xử lý sau và cách triển khai thay đổi mà không làm hỏng các consumer đang chạy.

Cần phân biệt hai tình huống:

- **Enum value mới**: discriminator là một giá trị trong tập enum, ví dụ status = "ON_HOLD".
- **Subtype mới**: discriminator chọn một class concrete trong hierarchy, ví dụ type = "shipment-delayed".

Hai tình huống có API Jackson và chiến lược fallback khác nhau. Bài học này trình bày cách quản lý cả hai để JSON contract có thể tiến hóa mà vẫn giữ được tính rõ ràng và an toàn.

## 1. Vì sao giá trị mới có thể làm consumer cũ lỗi?

Giả sử service đơn hàng ban đầu công bố:

~~~json
{
  "id": "ORD-100",
  "status": "PENDING"
}
~~~

Java enum:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Sau một lần nâng cấp, producer bổ sung trạng thái ON_HOLD:

~~~json
{
  "id": "ORD-100",
  "status": "ON_HOLD"
}
~~~

Consumer cũ không có constant ON_HOLD. Với cấu hình mặc định, Jackson thường báo lỗi mapping khi không thể chuyển chuỗi đó thành enum constant.

Tình huống tương tự xảy ra với polymorphic type. Ban đầu consumer biết các event:

~~~json
{
  "type": "order-created",
  "orderId": "ORD-100"
}
~~~

Producer mới gửi thêm:

~~~json
{
  "type": "order-paused",
  "orderId": "ORD-100",
  "reason": "inventory-check"
}
~~~

Nếu subtype order-paused chưa được đăng ký ở consumer, Jackson không biết class nào cần tạo.

Đây là vấn đề tương thích giữa các phiên bản của producer và consumer. Chỉ thêm enum constant hoặc subtype vào một service chưa bảo đảm toàn bộ hệ thống có thể đọc dữ liệu mới.

## 2. Phân biệt enum và polymorphic subtype

| Nội dung | Enum value | Polymorphic subtype |
|---|---|---|
| Giá trị JSON | Một scalar, thường là string | Discriminator trong object hoặc cấu trúc bọc |
| Ví dụ | "PAID" | {"type":"card-payment", ...} |
| Kiểu Java | Một constant trong enum | Một class concrete trong hierarchy |
| Cơ chế Jackson | Enum deserializer | Type resolver và subtype deserializer |
| Cấu hình fallback | Enum default/null/custom creator | defaultImpl hoặc problem handler |
| Rủi ro chính | Giá trị mới bị từ chối hoặc bị diễn giải sai | Class mới không được nhận diện hoặc fallback mất dữ liệu |

Không nên xử lý unknown enum và unknown subtype bằng cùng một thủ thuật. Enum là tập giá trị hữu hạn, còn subtype có thể có nhiều field, hành vi và cấu trúc payload khác nhau.

## 3. Cách Jackson đọc enum theo mặc định

Jackson thường ánh xạ tên enum constant từ chuỗi JSON:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

~~~java
OrderStatus status = mapper.readValue(
        "\"PAID\"",
        OrderStatus.class
);
~~~

Kết quả là OrderStatus.PAID.

Nếu JSON chứa giá trị không tồn tại:

~~~java
OrderStatus status = mapper.readValue(
        "\"ON_HOLD\"",
        OrderStatus.class
);
~~~

Jackson thường ném lỗi mapping như InvalidFormatException. Đây là lựa chọn strict: consumer phát hiện ngay giá trị nằm ngoài tập đã biết.

Strict mode phù hợp khi mọi trạng thái đều có ý nghĩa nghiệp vụ cụ thể và consumer không thể xử lý an toàn trạng thái chưa biết. Ví dụ, một payment processor không nên tự coi một trạng thái thanh toán mới là PAID hoặc CANCELLED.

## 4. Đặt tên enum ổn định trong JSON

Tên enum constant trong Java không nhất thiết phải là tên xuất hiện trên wire. Hợp đồng JSON nên dùng tên ổn định, dễ đọc và độc lập với việc refactor code.

### 4.1. Dùng @JsonProperty trên enum constant

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum OrderStatus {

    @JsonProperty("pending")
    PENDING,

    @JsonProperty("in-progress")
    IN_PROGRESS,

    @JsonProperty("completed")
    COMPLETED,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "in-progress"
}
~~~

Jackson ánh xạ giá trị in-progress vào OrderStatus.IN_PROGRESS. Việc đổi tên constant Java sau này không nhất thiết làm thay đổi tên wire nếu annotation vẫn giữ nguyên.

### 4.2. Dùng @JsonValue và @JsonCreator

Khi cần logic chuyển đổi rõ ràng hơn, có thể định nghĩa wire value bằng @JsonValue và parser bằng @JsonCreator:

~~~java
public enum OrderStatus {
    PENDING("pending"),
    IN_PROGRESS("in-progress"),
    COMPLETED("completed"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }

    @JsonCreator
    public static OrderStatus fromWireValue(String value) {
        for (OrderStatus status : values()) {
            if (status.wireValue.equals(value)) {
                return status;
            }
        }

        throw new IllegalArgumentException(
                "Unsupported order status"
        );
    }
}
~~~

Cách này giúp kiểm soát:
- Tên JSON không phụ thuộc tên constant.
- Có thể hỗ trợ alias cũ trong factory.
- Có thể chuẩn hóa giá trị nếu contract cho phép.
- Có thể quyết định rõ unknown value sẽ bị từ chối hay chuyển thành UNKNOWN.

Không nên dùng ordinal của enum làm hợp đồng JSON. Thứ tự constant có thể thay đổi khi thêm hoặc sắp xếp lại enum; giá trị số cũ khi đó có thể trỏ đến trạng thái khác.

Cũng nên thận trọng với toString() làm wire format. toString() thường phục vụ hiển thị/debug và có thể bị sửa vì lý do nội bộ. Hãy dùng một wire value được định nghĩa rõ ràng.

## 5. Chấp nhận enum value chưa biết bằng UNKNOWN

Nếu consumer có thể tiếp tục hoạt động an toàn khi gặp trạng thái chưa biết, có thể định nghĩa một constant dự phòng:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Bật feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(
                DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
        )
        .build();
~~~

Khi Jackson gặp enum value không có constant tương ứng, nó có thể dùng constant được đánh dấu @JsonEnumDefaultValue:

~~~java
OrderStatus status = mapper.readValue(
        "\"ON_HOLD\"",
        OrderStatus.class
);

assert status == OrderStatus.UNKNOWN;
~~~

Cách này phù hợp khi:
- Consumer có thể hiển thị "trạng thái chưa biết".
- Consumer chỉ ghi nhận hoặc chuyển tiếp message.
- Quy tắc nghiệp vụ không yêu cầu hành động cụ thể cho mọi trạng thái.
- Hệ thống có cách theo dõi tần suất unknown value.

Không dùng UNKNOWN nếu code phía sau vẫn xử lý nó như một trạng thái nghiệp vụ bình thường. Ví dụ, không nên mặc định UNKNOWN thành trạng thái có thể giao hàng hoặc hoàn tiền.

### 5.1. Feature READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE

Feature này dùng enum constant được đánh dấu @JsonEnumDefaultValue làm fallback. Nếu không có constant phù hợp được đánh dấu, không nên kỳ vọng Jackson tự chọn một giá trị bất kỳ; hãy kiểm tra cấu hình và test để bảo đảm hành vi mong muốn.

Annotation chỉ đánh dấu constant dự phòng. Cần bật DeserializationFeature tương ứng để Jackson sử dụng nó cho unknown enum value.

### 5.2. Chuyển unknown enum thành null

Jackson cũng có feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(
                DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL
        )
        .build();
~~~

Khi gặp giá trị enum không nhận diện, Jackson có thể trả null.

Cách này chỉ phù hợp khi null có ý nghĩa rõ ràng trong model và tầng nghiệp vụ xử lý null an toàn. Nếu null bị hiểu là "không được chọn", "chưa có dữ liệu" hoặc "dùng mặc định", các ý nghĩa có thể bị nhập làm một.

Có thêm một giới hạn thực tế: một số collection như EnumSet và EnumMap không chấp nhận null element/key. Unknown enum được ánh xạ thành null có thể bị bỏ qua hoặc không thể thêm vào collection như mong muốn. Hãy kiểm thử trường hợp collection thay vì chỉ test một enum field đơn.

### 5.3. So sánh ba chính sách enum

| Chính sách | Hành vi khi gặp giá trị mới | Khi nên dùng |
|---|---|---|
| Strict mặc định | Ném lỗi mapping | Giá trị mới không thể xử lý an toàn |
| READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE | Dùng constant @JsonEnumDefaultValue | Có trạng thái UNKNOWN rõ nghĩa |
| READ_UNKNOWN_ENUM_VALUES_AS_NULL | Trả null | Null được hợp đồng cho phép và xử lý rõ ràng |

Không bật feature global chỉ vì một enum có nhu cầu fallback. Nếu các enum trong cùng ObjectMapper có yêu cầu khác nhau, cân nhắc custom deserializer hoặc mapper/reader được cấu hình riêng cho phạm vi phù hợp.

## 6. Custom enum creator để hỗ trợ alias và unknown value

Một factory @JsonCreator có thể hỗ trợ tên cũ và tên mới:

~~~java
public enum OrderStatus {
    PENDING,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED,
    UNKNOWN;

    @JsonCreator
    public static OrderStatus fromJson(String value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case "pending" -> PENDING;
            case "in-progress", "processing" -> IN_PROGRESS;
            case "completed", "done" -> COMPLETED;
            case "cancelled", "canceled" -> CANCELLED;
            default -> UNKNOWN;
        };
    }

    @JsonValue
    public String toJson() {
        return switch (this) {
            case PENDING -> "pending";
            case IN_PROGRESS -> "in-progress";
            case COMPLETED -> "completed";
            case CANCELLED -> "cancelled";
            case UNKNOWN -> "unknown";
        };
    }
}
~~~

Ở đây processing và done là alias đầu vào. Khi serialize, mỗi constant chỉ có một wire value chính thức.

Ưu điểm:
- Có thể giữ tương thích với tên cũ trong giai đoạn chuyển đổi.
- Có thể chuẩn hóa chữ hoa/chữ thường theo quy tắc cụ thể.
- Có thể ánh xạ unknown vào UNKNOWN.
- Không phụ thuộc vào tên Java constant.

Cần hiểu rằng custom @JsonCreator tự quyết định việc chuyển đổi. Nếu factory trả UNKNOWN cho mọi giá trị lạ, feature READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE không còn là nơi quyết định chính sách cho các chuỗi được factory xử lý. Hãy chọn một cơ chế làm nguồn sự thật, tránh nhiều fallback chồng lên nhau.

## 7. Giá trị enum phân biệt chữ hoa và chữ thường

Theo cách mặc định, tên enum thường được so khớp có phân biệt chữ hoa/chữ thường. Ví dụ PENDING và pending có thể được coi là hai giá trị khác nhau nếu wire mapping không quy định alias.

Có thể bật khả năng đọc enum không phân biệt chữ hoa/chữ thường bằng MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS)
        .build();
~~~

Khi bật, consumer có thể chấp nhận các cách viết khác nhau như PAID, paid hoặc Paid tùy cơ chế enum mapping.

Chỉ bật khi hợp đồng cho phép. Việc chấp nhận rộng hơn có thể che lỗi producer hoặc tạo nhiều cách biểu diễn cho cùng một giá trị. Với wire value có dấu gạch ngang hoặc alias tùy chỉnh, @JsonCreator thường cho phép kiểm soát chính xác hơn.

## 8. Thêm enum constant mà vẫn giữ tương thích

Khi producer thêm một enum constant mới, hãy xem xét cả chiều cũ và chiều mới:

~~~mermaid
flowchart TD
    A[Producer thêm enum value] --> B{Consumer có biết value?}
    B -->|Có| C[Deserialize thành constant tương ứng]
    B -->|Không| D{Có chính sách unknown?}
    D -->|Strict| E[Mapping error]
    D -->|UNKNOWN fallback| F[Nhận UNKNOWN và theo dõi]
    D -->|Null fallback| G[Nhận null, cần xử lý null]
~~~

Ví dụ ma trận:

| Producer | Consumer | Kết quả |
|---|---|---|
| Phiên bản cũ chỉ gửi PENDING/PAID | Phiên bản mới biết thêm ON_HOLD | Consumer mới đọc được giá trị cũ |
| Phiên bản mới gửi ON_HOLD | Consumer cũ strict | Consumer cũ báo lỗi |
| Phiên bản mới gửi ON_HOLD | Consumer cũ có UNKNOWN fallback | Consumer cũ tiếp tục với UNKNOWN |
| Phiên bản mới gửi ON_HOLD | Consumer cũ ánh xạ unknown thành null | Consumer cũ phải xử lý null an toàn |

Fallback không tự làm cho hệ thống tương thích về nghiệp vụ. Consumer nhận UNKNOWN có thể vẫn cần từ chối thao tác, yêu cầu cập nhật hoặc chuyển message vào hàng đợi xử lý sau.

## 9. Polymorphic subtype và type discriminator

Với interface hoặc abstract class, Jackson cần type metadata để chọn class concrete khi deserialize.

Ví dụ hierarchy:

~~~java
public interface DomainEvent {
    String getEventId();
}

public class OrderCreated implements DomainEvent {
    private String eventId;
    private String orderId;

    // Constructor, getter và setter.
}

public class OrderCancelled implements DomainEvent {
    private String eventId;
    private String orderId;
    private String reason;

    // Constructor, getter và setter.
}
~~~

Khai báo subtype:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = OrderCreated.class, name = "order-created"),
        @JsonSubTypes.Type(value = OrderCancelled.class, name = "order-cancelled")
})
public interface DomainEvent {
    String getEventId();
}
~~~

JSON:

~~~json
{
  "type": "order-created",
  "eventId": "EVT-001",
  "orderId": "ORD-100"
}
~~~

Jackson dùng type id order-created để chọn OrderCreated.

Tên type id là một phần của wire contract. Nên dùng tên logic ổn định thay vì tên class đầy đủ. Khi đổi package hoặc refactor tên class, producer vẫn có thể tiếp tục gửi order-created.

### 9.1. Dùng @JsonTypeName cho subtype

~~~java
@JsonTypeName("order-created")
public class OrderCreated implements DomainEvent {
    // Field và method.
}
~~~

@JsonTypeName đặt tên logic cho subtype. Jackson vẫn cần subtype được biết thông qua @JsonSubTypes, registerSubtypes hoặc một cơ chế resolver tương ứng.

### 9.2. Đăng ký subtype bằng module/mapper

Nếu không thể sửa base class hoặc muốn đăng ký tập subtype ở một nơi:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .build();

mapper.registerSubtypes(
        new NamedType(OrderCreated.class, "order-created"),
        new NamedType(OrderCancelled.class, "order-cancelled")
);
~~~

Cách đăng ký cần được thực hiện trước khi mapper được dùng để xử lý request. ObjectMapper sau khi cấu hình nên được tái sử dụng, không thay đổi registry tùy tiện giữa các request.

## 10. Điều gì xảy ra khi consumer gặp subtype mới?

Giả sử producer mới gửi:

~~~json
{
  "type": "order-paused",
  "eventId": "EVT-900",
  "orderId": "ORD-100",
  "reason": "inventory-check"
}
~~~

Consumer cũ chỉ biết order-created và order-cancelled. Type id order-paused không ánh xạ đến class nào.

Với cấu hình strict thông thường, Jackson báo lỗi như InvalidTypeIdException (một loại JsonMappingException). Đây là hành vi hợp lý khi consumer không có quy tắc xử lý event mới.

Không nên tự đoán class dựa trên tên type id hoặc tải class theo tên do payload cung cấp. Hãy dùng allowlist subtype đã đăng ký.

## 11. Cách xử lý unknown subtype bằng defaultImpl

@JsonTypeInfo có thuộc tính defaultImpl để chỉ định kiểu dự phòng khi type id không được nhận diện hoặc thiếu, tùy cấu hình và ngữ cảnh.

Ví dụ:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type",
        visible = true,
        defaultImpl = UnknownEvent.class
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = OrderCreated.class, name = "order-created"),
        @JsonSubTypes.Type(value = OrderCancelled.class, name = "order-cancelled")
})
public interface DomainEvent {
    String getEventId();
}
~~~

Lớp fallback có thể giữ type id và những field chưa biết:

~~~java
public class UnknownEvent implements DomainEvent {

    private String type;
    private String eventId;
    private Map<String, JsonNode> additionalProperties =
            new LinkedHashMap<>();

    @Override
    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    @JsonAnySetter
    public void addProperty(String name, JsonNode value) {
        additionalProperties.put(name, value);
    }

    @com.fasterxml.jackson.annotation.JsonAnyGetter
    public Map<String, JsonNode> getAdditionalProperties() {
        return additionalProperties;
    }
}
~~~

Với visible = true, type id được đưa tiếp vào quá trình deserialize như một property thông thường. Điều này giúp UnknownEvent giữ lại tên subtype chưa biết. @JsonAnySetter có thể lưu các property chưa được khai báo vào map.

Cách này phù hợp với consumer cần:
- Nhận message mới mà không làm hỏng toàn bộ luồng.
- Ghi nhận type id chưa biết.
- Lưu hoặc chuyển tiếp payload để xử lý sau.
- Theo dõi loại event mới xuất hiện.

### 11.1. Fallback không có nghĩa là hiểu được event mới

UnknownEvent chỉ giữ dữ liệu. Nó không có hành vi nghiệp vụ của OrderPaused.

Không được xử lý UnknownEvent như OrderCreated hoặc OrderCancelled. Consumer nên:
- Lưu message vào vùng chờ.
- Chuyển tiếp đến thành phần hiểu type id đó.
- Ghi metric/alert về unknown subtype.
- Bỏ qua có chủ đích nếu hợp đồng cho phép và sự kiện không ảnh hưởng trạng thái.
- Từ chối nếu không thể bỏ qua an toàn.

Nếu event mới ảnh hưởng tồn kho, thanh toán hoặc quyền truy cập, bỏ qua nó có thể làm sai trạng thái hệ thống.

### 11.2. Kiểm soát dữ liệu field chưa biết

UnknownEvent dùng JsonNode map để giữ property bổ sung. Đây là một cách giữ payload có cấu trúc, nhưng vẫn cần giới hạn kích thước và độ sâu JSON theo yêu cầu hệ thống.

Không nên ghi toàn bộ map ra log. Có thể lưu payload trong kho có kiểm soát quyền hoặc chỉ ghi type id, request ID và số lượng field.

### 11.3. Serialize lại UnknownEvent

Khả năng deserialize unknown subtype thành UnknownEvent không tự bảo đảm serialize lại sẽ phát ra đúng type id gốc. Nếu cần round trip hoặc forward message, hãy thiết kế rõ cách serializer giữ type id và các property gốc. Có thể cần custom serializer/type resolver hoặc lưu nguyên raw JSON theo một cơ chế riêng.

Hãy kiểm thử cả chiều đọc và ghi; không giả định defaultImpl tự tạo một wire representation có thể round-trip hoàn hảo.

## 12. Xử lý unknown subtype bằng DeserializationProblemHandler

Trong các hệ thống cần chính sách tập trung, Jackson có DeserializationProblemHandler. Handler có thể can thiệp khi type id không được giải quyết và trả về một JavaType đã được ứng dụng cho phép.

Cơ chế này hữu ích khi:
- Có nhiều base type dùng chung chính sách unknown.
- Cần ghi metric hoặc cảnh báo khi gặp type id mới.
- Muốn chọn fallback theo registry do ứng dụng kiểm soát.
- Muốn giữ logic subtype policy ngoài annotation của model.

Handler chỉ nên trả về kiểu concrete nằm trong allowlist. Không dùng type id từ JSON để gọi Class.forName() hoặc tải class tùy ý.

Một lựa chọn khác là để strict mode hoạt động và xử lý InvalidTypeIdException ở tầng message consumer. Khi không có chiến lược fallback thực sự an toàn, từ chối message và đưa vào dead-letter queue thường rõ ràng hơn việc tạo object giả định.

## 13. FAIL_ON_INVALID_SUBTYPE và chính sách strict

Jackson có DeserializationFeature.FAIL_ON_INVALID_SUBTYPE. Khi bật, lỗi không giải quyết được polymorphic type id thường làm quá trình deserialize thất bại. Đây là lựa chọn mặc định an toàn trong nhiều cấu hình.

Nếu tắt feature này, unresolved subtype có thể được biểu diễn bằng null trong những trường hợp không có default implementation phù hợp. Điều này có thể gây lỗi muộn ở code nghiệp vụ nếu null không được xử lý.

Không nên tắt feature global chỉ để tránh exception. Nếu muốn fallback, hãy dùng defaultImpl hoặc handler với một kiểu unknown có ý nghĩa rõ ràng. Nếu không có fallback an toàn, giữ strict mode để message bị từ chối ngay tại ranh giới deserialize.

## 14. Dùng unknown subtype và unknown enum có trách nhiệm

Hai kiểu fallback có thể được thiết kế song song nhưng cần semantics riêng.

Ví dụ:
- OrderStatus.UNKNOWN: trạng thái đơn hàng chưa được consumer biết.
- UnknownEvent: event có type id chưa đăng ký, giữ payload để chuyển tiếp hoặc xử lý sau.

Không nên ánh xạ mọi subtype mới về một event hiện có. Cũng không nên ánh xạ enum mới về một trạng thái có hành vi nghiệp vụ cụ thể.

~~~mermaid
flowchart TD
    A[JSON input] --> B{Discriminator}
    B -->|Enum field| C[Enum deserializer]
    B -->|Polymorphic type| D[Type resolver]
    C --> E{Enum value known?}
    E -->|Yes| F[Known enum constant]
    E -->|No| G[Reject / UNKNOWN / null]
    D --> H{Subtype known?}
    H -->|Yes| I[Known concrete subtype]
    H -->|No| J[Reject / UnknownEvent / handler]
~~~

Fallback phải tạo ra một trạng thái mà mọi consumer phía sau hiểu đúng. Nếu downstream code không xử lý UNKNOWN hoặc UnknownEvent, fallback chỉ chuyển exception thành một lỗi khó phát hiện hơn.

## 15. Tương thích khi thêm subtype mới

Khi thêm subtype mới vào hierarchy, hãy xem xét các phiên bản:

| Producer | Consumer | Kết quả |
|---|---|---|
| Producer cũ gửi order-created | Consumer mới biết cả cũ và mới | Đọc bình thường |
| Producer mới gửi order-paused | Consumer mới đã đăng ký subtype | Đọc thành subtype mới |
| Producer mới gửi order-paused | Consumer cũ strict | Báo unknown type id |
| Producer mới gửi order-paused | Consumer cũ có UnknownEvent fallback | Nhận fallback, không có logic của subtype mới |
| Producer mới gửi subtype cũ với field mới | Consumer cũ | Phụ thuộc chính sách unknown property |

Một subtype mới thường là thay đổi additive đối với consumer đã cập nhật. Nhưng nó không tự tương thích với consumer cũ strict.

Đối với message queue, có thể có consumer cũ tiếp tục chạy sau khi producer mới đã deploy. Hãy kiểm tra toàn bộ nhóm consumer, retry queue và dead-letter queue trước khi phát producer event mới.

## 16. Chiến lược rollout an toàn

Một quy trình thường dùng:

1. **Mở rộng consumer trước**: triển khai phiên bản biết enum value hoặc subtype mới.
2. **Giữ nguyên giá trị cũ**: không đổi tên wire value đã phát hành.
3. **Kiểm tra khả năng đọc dữ liệu cũ**: consumer mới phải tiếp tục đọc payload phiên bản trước.
4. **Triển khai producer sau**: chỉ bắt đầu phát giá trị mới khi các consumer cần thiết đã sẵn sàng.
5. **Theo dõi unknown**: metric về enum UNKNOWN, unknown subtype, InvalidFormatException và InvalidTypeIdException.
6. **Có kế hoạch rollback**: producer có thể ngừng phát giá trị mới nếu consumer gặp lỗi diện rộng.
7. **Dọn alias/fallback có thời hạn**: chỉ bỏ tên cũ khi tất cả consumer và dữ liệu lưu trữ đã chuyển đổi.

Với hệ thống event-driven, triển khai consumer trước producer thường giảm rủi ro. Nếu không thể nâng cấp đồng thời mọi consumer, hãy dùng một contract version hoặc capability negotiation để producer biết tập type id consumer hỗ trợ.

## 17. Giữ wire value cũ khi đổi tên enum hoặc subtype

Không nên đổi trực tiếp wire value đã phát hành chỉ vì muốn đổi tên class hoặc enum constant.

Ví dụ, Java đổi IN_PROGRESS thành PROCESSING nhưng JSON vẫn cần giữ in-progress:

~~~java
public enum OrderStatus {
    PENDING,
    PROCESSING,
    COMPLETED;

    @JsonCreator
    public static OrderStatus fromJson(String value) {
        return switch (value) {
            case "pending" -> PENDING;
            case "in-progress", "processing" -> PROCESSING;
            case "completed" -> COMPLETED;
            default -> throw new IllegalArgumentException(
                    "Unsupported order status"
            );
        };
    }

    @JsonValue
    public String toJson() {
        return switch (this) {
            case PENDING -> "pending";
            case PROCESSING -> "in-progress";
            case COMPLETED -> "completed";
        };
    }
}
~~~

Consumer chấp nhận cả tên cũ và tên mới trong giai đoạn chuyển đổi, nhưng serializer chỉ phát một wire value chính thức.

Với subtype, có thể giữ tên type id cũ trong @JsonSubTypes hoặc đăng ký alias về cùng một class. Không tái sử dụng type id cũ cho một ý nghĩa khác, vì payload đã lưu hoặc message đang chờ có thể bị diễn giải sai.

## 18. Unknown property là vấn đề riêng với unknown subtype

Khi type id đã được nhận diện, subtype có thể vẫn nhận thêm field mới mà consumer cũ chưa biết.

Ví dụ:

~~~json
{
  "type": "order-created",
  "eventId": "EVT-001",
  "orderId": "ORD-100",
  "sourceRegion": "ap-southeast-1"
}
~~~

Consumer cũ biết OrderCreated nhưng không biết sourceRegion. Hành vi phụ thuộc cấu hình unknown property:
- Strict: lỗi khi gặp property chưa được ánh xạ.
- Ignore: bỏ qua field chưa biết.
- @JsonAnySetter: lưu field bổ sung vào map.
- Tree/DTO: giữ payload theo schema linh hoạt.

Đây khác với unknown subtype:
- Unknown property: class đã biết, nhưng có field mới.
- Unknown subtype: discriminator chọn một class chưa đăng ký.

Một hệ thống forward-compatible cần quyết định riêng cho cả hai. Bỏ qua unknown property không giúp Jackson tạo class khi type id chưa biết.

## 19. Kiểm thử enum evolution

Test nên bao gồm:
- Giá trị enum cũ vẫn đọc được.
- Giá trị mới được ánh xạ về constant tương ứng ở consumer mới.
- Giá trị chưa biết bị từ chối trong strict mode.
- Giá trị chưa biết thành UNKNOWN khi bật default feature.
- Null được xử lý đúng theo hợp đồng.
- Wire value khi serialize vẫn ổn định.
- Alias cũ tiếp tục đọc được nếu đang trong giai đoạn migration.

Ví dụ với default enum:

~~~java
@Test
void mapsUnknownEnumValueToUnknown() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(
                    DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
            )
            .build();

    OrderStatus status = mapper.readValue(
            "\"ON_HOLD\"",
            OrderStatus.class
    );

    assertEquals(OrderStatus.UNKNOWN, status);
}
~~~

Test strict mode:

~~~java
@Test
void rejectsUnknownEnumValueByDefault() {
    assertThrows(
            JsonProcessingException.class,
            () -> strictMapper.readValue(
                    "\"ON_HOLD\"",
                    OrderStatus.class
            )
    );
}
~~~

## 20. Kiểm thử unknown polymorphic subtype

Với subtype đã biết:

~~~java
@Test
void readsKnownSubtype() throws Exception {
    String json = """
            {
              "type": "order-created",
              "eventId": "EVT-001",
              "orderId": "ORD-100"
            }
            """;

    DomainEvent event = mapper.readValue(json, DomainEvent.class);

    assertInstanceOf(OrderCreated.class, event);
}
~~~

Với subtype chưa biết ở strict mode:

~~~java
@Test
void rejectsUnknownSubtypeInStrictMode() {
    String json = """
            {
              "type": "order-paused",
              "eventId": "EVT-900",
              "orderId": "ORD-100"
            }
            """;

    assertThrows(
            InvalidTypeIdException.class,
            () -> strictMapper.readValue(json, DomainEvent.class)
    );
}
~~~

Nếu dùng UnknownEvent fallback, hãy test:
- Class thực tế là UnknownEvent.
- Type id order-paused được giữ lại.
- Các field chưa biết được lưu theo chính sách.
- Downstream handler không xử lý UnknownEvent như event đã biết.
- Serialize lại có giữ được type id và payload theo contract nếu yêu cầu forward.

Không chỉ test rằng fallback không ném exception. Cần test xem fallback có giữ đủ thông tin để hệ thống xử lý an toàn hay không.

## 21. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Thêm enum constant mà không kiểm tra consumer cũ | Consumer cũ có thể lỗi mapping | Chọn strict hoặc UNKNOWN trước khi producer phát |
| Dùng enum ordinal trong JSON | Thứ tự constant thay đổi làm đổi nghĩa | Dùng wire string ổn định |
| Dùng tên class làm type id công khai | Refactor package/class có thể phá contract | Dùng Id.NAME và logical type |
| Ánh xạ enum lạ thành PAID/PENDING | Dữ liệu mới bị diễn giải sai nghiệp vụ | Dùng UNKNOWN hoặc từ chối |
| Ánh xạ mọi subtype lạ về một subtype đã biết | Có thể tạo object sai semantics | Dùng UnknownEvent hoặc strict mode |
| Tắt FAIL_ON_INVALID_SUBTYPE global | Có thể tạo null ngoài dự kiến | Dùng defaultImpl/handler có kiểm soát |
| Bật defaultImpl nhưng không lưu type id | Mất thông tin subtype gốc | Dùng visible=true và lưu discriminator nếu cần |
| Bỏ qua unknown field và nghĩ đã hỗ trợ unknown subtype | Hai vấn đề khác nhau | Cấu hình riêng property và type resolver |
| Cho payload chọn class tùy ý | Rủi ro tạo class không được phép | Dùng subtype allowlist |
| Đổi type id đã phát hành | Message cũ không còn đọc được | Giữ alias hoặc mapping cũ |
| Thêm producer trước consumer | Message mới đến consumer chưa sẵn sàng | Rollout consumer trước producer |
| Dùng UNKNOWN nhưng downstream không xử lý | Lỗi chuyển thành trạng thái sai âm thầm | Định nghĩa hành vi UNKNOWN ở từng tầng |

## 22. Nguyên tắc bảo mật cho polymorphic deserialization

Type discriminator có thể ảnh hưởng class được tạo. Vì vậy, chỉ cho phép những subtype mà ứng dụng chủ động đăng ký.

Nên:
- Dùng JsonTypeInfo.Id.NAME với logical name.
- Đăng ký subtype rõ ràng bằng @JsonSubTypes hoặc NamedType.
- Giữ danh sách subtype nhỏ và có kiểm soát.
- Từ chối type id không biết nếu không có fallback an toàn.
- Dùng defaultImpl là một class unknown chuyên dụng nếu cần giữ payload.
- Giới hạn kích thước và độ sâu của dữ liệu unknown.
- Không gọi Class.forName() dựa trên type id trong JSON.
- Tránh default typing rộng cho dữ liệu từ client hoặc message không đáng tin cậy.

Không nên dùng Id.CLASS như một cách tiện lợi để producer gửi tên class Java tùy ý. Wire contract nên mô tả logical type, không phơi bày cơ chế tổ chức class nội bộ.

## 23. Checklist thiết kế hợp đồng enum và subtype

Trước khi phát hành giá trị mới, hãy xác nhận:

- Enum có wire value ổn định, không phụ thuộc ordinal hoặc tên class.
- Unknown enum có chính sách cụ thể: reject, UNKNOWN hoặc null.
- Nếu dùng UNKNOWN, mọi consumer downstream biết cách xử lý.
- Subtype mới có logical type id ổn định.
- Consumer cần thiết đã đăng ký subtype trước khi producer phát type id.
- Unknown subtype có chính sách strict, defaultImpl hoặc problem handler rõ ràng.
- Nếu cần forward unknown payload, type id và field chưa biết được giữ lại.
- Unknown property được xử lý độc lập với unknown subtype.
- Type id cũ và enum alias cũ vẫn được hỗ trợ trong thời gian migration.
- Không dùng class name từ payload để tạo object tùy ý.
- Có metric/alert khi unknown enum hoặc subtype xuất hiện.
- Có test dữ liệu cũ, dữ liệu mới, unknown value và round trip.
- Có kế hoạch rollback producer nếu consumer gặp lỗi.

Quản lý enum value và kiểu con mới là một phần của quản lý phiên bản hợp đồng JSON. Enum fallback cần phản ánh đúng semantics của trạng thái chưa biết; subtype fallback cần giữ được type id và dữ liệu đủ để chuyển tiếp hoặc xử lý sau. Khi dùng wire name ổn định, subtype allowlist, chính sách unknown rõ ràng và rollout consumer trước producer, hệ thống có thể tiếp nhận thay đổi theo từng phiên bản mà không diễn giải dữ liệu mới thành một trạng thái cũ sai nghĩa.
