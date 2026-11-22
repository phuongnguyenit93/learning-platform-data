# Phân biệt dữ liệu mở rộng được giữ lại và thuộc tính bị bỏ qua

Trong một API có cấu trúc mở, client có thể gửi thêm thuộc tính mà phiên bản server hiện tại chưa biết. Jackson cần một chính sách rõ ràng cho những thuộc tính này: từ chối payload, bỏ qua chúng hay giữ lại để ứng dụng có thể đọc và phát ra lần nữa.

Ba cách xử lý này có ý nghĩa khác nhau. Mặc định, Jackson thường báo lỗi khi gặp property không được ánh xạ. Annotation **@JsonIgnoreProperties(ignoreUnknown = true)** cho phép bỏ qua property không biết, nhưng dữ liệu đó sẽ mất khỏi object Java. Annotation **@JsonAnySetter** có thể thu thập các property chưa biết vào một Map; kết hợp với **@JsonAnyGetter**, ứng dụng có thể ghi chúng trở lại JSON ở cùng cấp với các property thông thường.

Chọn đúng chính sách giúp cân bằng giữa tương thích phiên bản, khả năng bảo toàn dữ liệu và kiểm soát schema.

## 1. Property đã biết và property chưa biết

Giả sử server đang có DTO:

~~~java
public class EventRequest {
    private String eventId;
    private String eventType;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
~~~

Server biết hai property eventId và eventType. Client mới có thể gửi thêm:

~~~json
{
  "eventId": "evt-42",
  "eventType": "USER_CREATED",
  "priority": 3,
  "sourceRegion": "ap-southeast-1"
}
~~~

Hai trường đầu được ánh xạ vào DTO. Hai trường sau chưa có thuộc tính tương ứng trong lớp Java hiện tại.

Một property chưa biết không nhất thiết là dữ liệu sai. Nó có thể là:

- Trường mới được thêm trong phiên bản API mới hơn.
- Metadata do một hệ thống trung gian đính kèm.
- Thuộc tính mở rộng theo từng đối tác.
- Dữ liệu mà dịch vụ hiện tại chỉ cần chuyển tiếp mà không diễn giải.

Tuy nhiên, cũng có thể đó là lỗi chính tả hoặc một trường không được phép gửi. Vì vậy, không nên mặc định rằng mọi property lạ đều cần được chấp nhận.

## 2. Hành vi mặc định: từ chối property không biết

Trong cấu hình Jackson Databind thông thường, **DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES** được bật mặc định. Nếu JSON có một key mà Jackson không thể ánh xạ vào property nào và không có cơ chế xử lý unknown property khác, quá trình deserialize sẽ thất bại.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

EventRequest request = mapper.readValue(
    """
    {
      "eventId": "evt-42",
      "eventType": "USER_CREATED",
      "priority": 3
    }
    """,
    EventRequest.class
);
~~~

Nếu EventRequest không khai báo priority, Jackson có thể ném UnrecognizedPropertyException, một subtype của JsonMappingException.

Chế độ nghiêm ngặt phù hợp khi:

- Hợp đồng API đóng và mọi field đều phải được khai báo.
- Muốn phát hiện typo như eventTye thay vì âm thầm bỏ qua.
- Payload cần được kiểm tra chặt trước khi vào domain.
- Việc nhận thêm field có thể gây ảnh hưởng đến bảo mật hoặc logic nghiệp vụ.

Nếu server cần tương thích với client mới hơn, có thể chọn một trong các chiến lược bên dưới.

## 3. Bỏ qua property không biết bằng @JsonIgnoreProperties

Nếu server chỉ cần các field đã biết và không cần giữ lại phần mở rộng, có thể dùng:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class EventRequest {
    private String eventId;
    private String eventType;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
~~~

Khi đọc payload có thêm priority và sourceRegion, Jackson gán hai property đã biết rồi bỏ qua các property còn lại.

Kết quả object chỉ chứa:

~~~text
eventId   = "evt-42"
eventType = "USER_CREATED"
~~~

Nếu serialize object này trở lại JSON, hai field không biết ban đầu không xuất hiện vì chúng chưa từng được lưu vào object.

### 3.1. Bỏ qua là mất dữ liệu

Giả sử một gateway đọc message của client mới, sau đó ghi lại message để chuyển đến dịch vụ tiếp theo. Nếu gateway dùng ignoreUnknown = true, các trường mở rộng bị loại bỏ ngay khi deserialize.

~~~text
JSON đầu vào
  eventId
  eventType
  priority       <--- chưa biết
  sourceRegion   <--- chưa biết
       |
       v
EventRequest
  eventId
  eventType
       |
       v
JSON đầu ra
  eventId
  eventType
~~~

Đây có thể là hành vi đúng với một endpoint chỉ quan tâm đến hai trường. Nhưng nó không phù hợp với một proxy hoặc gateway có nhiệm vụ chuyển tiếp dữ liệu mà không làm mất metadata.

### 3.2. Bỏ qua unknown property ở cấp ObjectMapper

Có thể tắt feature trên mapper:

~~~java
ObjectMapper mapper = new ObjectMapper()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Cách này ảnh hưởng rộng đến các lớp được đọc bằng mapper đó. Một typo trong bất kỳ DTO nào cũng có thể bị bỏ qua mà không báo lỗi.

Nếu chỉ một DTO có schema mở, annotation trên lớp thường giới hạn chính sách rõ ràng hơn cấu hình global.

### 3.3. Đừng nhầm với @JsonIgnoreProperties(value = ...)

Annotation cũng có thể chỉ định các tên property cụ thể cần bỏ qua:

~~~java
@JsonIgnoreProperties({"internalNote", "legacySecret"})
public class EventRequest {
    // ...
}
~~~

Đây là danh sách property đã biết hoặc tên cụ thể muốn bỏ qua. Nó khác với ignoreUnknown = true, vốn cho phép bỏ qua mọi property chưa được nhận diện.

Bỏ qua property có chủ đích có thể cần thiết khi DTO không nên nhận hoặc phát ra một trường nhất định. Hãy xác định rõ đó là chính sách loại bỏ field cụ thể hay chính sách chấp nhận schema mở.

## 4. Giữ lại property mở rộng bằng @JsonAnySetter

Khi muốn thu thập property không biết thay vì bỏ chúng, dùng **@JsonAnySetter**. Annotation này đánh dấu một method nhận tên property và giá trị của nó.

~~~java
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class EventRequest {
    private String eventId;
    private String eventType;

    private final Map<String, Object> extensions = new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    public Map<String, Object> getExtensions() {
        return extensions;
    }
}
~~~

Khi Jackson gặp priority hoặc sourceRegion, nó không tìm thấy property đã biết nên gọi:

~~~java
addExtension("priority", 3);
addExtension("sourceRegion", "ap-southeast-1");
~~~

Object Java giữ được các giá trị mở rộng trong Map. Các property thông thường vẫn được ánh xạ theo getter/setter hoặc annotation như trước.

### 4.1. @JsonAnySetter không tạo property Java riêng cho mỗi key

Các key động được lưu chung trong Map. Ứng dụng có thể truy cập:

~~~java
Object priority = request.getExtensions().get("priority");
Object sourceRegion = request.getExtensions().get("sourceRegion");
~~~

Điều này phù hợp khi số lượng hoặc tên field mở rộng không cố định theo phiên bản.

Có thể viết method xử lý riêng để lấy kiểu mong đợi và xác thực:

~~~java
Object rawPriority = request.getExtensions().get("priority");

if (rawPriority instanceof Number number) {
    int priority = number.intValue();
    // Kiểm tra giới hạn priority theo nghiệp vụ
}
~~~

Không nên ép kiểu trực tiếp nếu không biết dữ liệu do client gửi. Giá trị trong Map có thể là String, Number, Boolean, Map, List hoặc null tùy cấu trúc JSON và cấu hình Databind.

## 5. Ghi lại property mở rộng bằng @JsonAnyGetter

**@JsonAnySetter** giải quyết chiều đọc. Để các key trong Map được phát ra như những property ngang hàng trong JSON, dùng **@JsonAnyGetter**:

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class EventRequest {
    private String eventId;
    private String eventType;

    private final Map<String, Object> extensions = new LinkedHashMap<>();

    // Getter/setter cho eventId và eventType

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> extensionProperties() {
        return extensions;
    }
}
~~~

Với payload:

~~~json
{
  "eventId": "evt-42",
  "eventType": "USER_CREATED",
  "priority": 3,
  "sourceRegion": "ap-southeast-1"
}
~~~

Jackson đọc hai field đã biết vào thuộc tính riêng và lưu hai field còn lại trong extensions. Khi serialize, @JsonAnyGetter đưa các entry trong Map trở lại cùng cấp:

~~~json
{
  "eventId": "evt-42",
  "eventType": "USER_CREATED",
  "priority": 3,
  "sourceRegion": "ap-southeast-1"
}
~~~

Nếu chỉ có @JsonAnySetter mà không có @JsonAnyGetter, dữ liệu vẫn nằm trong object Java nhưng không tự động được trải phẳng ra JSON theo cách trên. Nếu Map có getter thông thường không bị bỏ qua, nó có thể được serialize thành một property riêng như extensions; đó là cấu trúc khác với yêu cầu giữ key mở rộng ở cấp ngoài.

## 6. Lưu giá trị mở rộng bằng Object hay JsonNode?

Có hai lựa chọn phổ biến cho kiểu giá trị của Map.

### 6.1. Map<String, Object>

~~~java
private final Map<String, Object> extensions = new LinkedHashMap<>();

@JsonAnySetter
public void addExtension(String name, Object value) {
    extensions.put(name, value);
}
~~~

Jackson Databind ánh xạ JSON vào các kiểu Java tổng quát. Một số kết quả thường gặp:

| JSON value | Kiểu Java tổng quát thường nhận |
|---|---|
| "text" | String |
| true / false | Boolean |
| 123 | Kiểu số nguyên phù hợp với giá trị/cấu hình |
| 12.5 | Kiểu số thập phân theo cấu hình |
| null | null |
| {"a":1} | Map |
| [1,2] | List |

Ưu điểm là dễ thao tác bằng Java collections và có thể chuyển trực tiếp sang logic ứng dụng. Nhược điểm là cấu trúc JSON lồng nhau trở thành Map/List không có schema cụ thể; kiểu số có thể phụ thuộc feature và cấu hình mapper.

Nếu cần giữ số thập phân chính xác hơn trong các untyped value, có thể xem xét **DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS**. Với số nguyên lớn, cân nhắc **USE_BIG_INTEGER_FOR_INTS**. Cấu hình này ảnh hưởng cách Jackson tạo kiểu số Java khi không có kiểu đích cụ thể.

### 6.2. Map<String, JsonNode>

Nếu cần giữ cấu trúc JSON mở dưới dạng node, có thể dùng JsonNode:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    extensions.put(name, value);
}

@JsonAnyGetter
public Map<String, JsonNode> extensionProperties() {
    return extensions;
}
~~~

Cách này cho phép phân biệt rõ:

- isTextual()
- isNumber()
- isBoolean()
- isObject()
- isArray()
- isNull()

Ví dụ đọc extension lồng nhau:

~~~java
JsonNode metadata = request.extensionProperties().get("metadata");

if (metadata != null && metadata.isObject()) {
    String region = metadata.path("region").asText(null);
    JsonNode labels = metadata.path("labels");
}
~~~

JsonNode phù hợp khi server cần giữ hoặc kiểm tra cấu trúc mở mà chưa muốn ánh xạ vào class cụ thể. Tuy vậy, nó không bảo toàn nguyên văn byte, khoảng trắng, thứ tự escape hay cách viết số ban đầu; nó giữ cấu trúc và giá trị JSON ở dạng cây.

### 6.3. Chọn kiểu nào?

| Nhu cầu | Kiểu phù hợp |
|---|---|
| Ứng dụng cần thao tác như Java values | Map<String, Object> |
| Cần kiểm tra loại node và cấu trúc JSON lồng nhau | Map<String, JsonNode> |
| Schema extension đã biết và ổn định | Map có kiểu value cụ thể hoặc DTO riêng |
| Cần giữ byte/text gốc chính xác | Lưu raw payload riêng, không chỉ dùng Map/JsonNode |

Không có một kiểu Map phù hợp cho mọi tình huống. Hãy chọn theo cách ứng dụng sẽ đọc, xác thực và chuyển tiếp extension data.

## 7. Ví dụ hoàn chỉnh giữ lại extension data

Ví dụ dưới đây dùng JsonNode để bảo toàn kiểu cấu trúc của giá trị mở rộng:

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class PartnerEvent {
    private static final Set<String> RESERVED_NAMES =
        Set.of("eventId", "eventType");

    private String eventId;
    private String eventType;

    private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

    @JsonProperty("eventId")
    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    @JsonProperty("eventType")
    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        if (RESERVED_NAMES.contains(name)) {
            throw new IllegalArgumentException(
                "Extension name is reserved: " + name
            );
        }

        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> extensionProperties() {
        return Collections.unmodifiableMap(extensions);
    }
}
~~~

Đọc JSON:

~~~java
ObjectMapper mapper = new ObjectMapper();

PartnerEvent event = mapper.readValue(
    """
    {
      "eventId": "evt-42",
      "eventType": "USER_CREATED",
      "priority": 3,
      "metadata": {
        "region": "ap-southeast-1",
        "labels": ["new", "partner"]
      }
    }
    """,
    PartnerEvent.class
);
~~~

Đọc extension:

~~~java
JsonNode priority = event.extensionProperties().get("priority");
JsonNode metadata = event.extensionProperties().get("metadata");

int priorityValue = priority.intValue();
String region = metadata.path("region").asText();
~~~

Ghi lại:

~~~java
String output = mapper.writeValueAsString(event);
~~~

Các extension sẽ xuất hiện lại ở cấp ngoài của object JSON. Thứ tự và cách định dạng văn bản có thể khác nguồn ban đầu; mục tiêu ở đây là giữ cấu trúc và giá trị, không giữ nguyên từng byte.

## 8. Giới hạn tên property và tránh xung đột

@JsonAnyGetter trải Map ra cùng cấp với các property thông thường. Vì vậy, key trong Map không nên trùng tên với property đã khai báo.

Ví dụ nếu object có property eventId, nhưng Map cũng chứa key eventId, serialization có thể tạo ra hai key cùng tên hoặc kết quả phụ thuộc cấu hình/thứ tự xử lý. Điều đó làm payload khó hiểu và có thể bị các consumer diễn giải khác nhau.

Nên dành một tập tên riêng cho extension và từ chối tên bị chiếm dụng:

~~~java
private static final Set<String> RESERVED_NAMES =
    Set.of("eventId", "eventType");
~~~

Trong ứng dụng lớn, có thể quản lý reserved names tập trung hoặc đặt extension trong một namespace riêng như extensions nếu hợp đồng API cho phép. Cách lồng namespace tránh va chạm với property mới được bổ sung trong các phiên bản tương lai, nhưng cấu trúc JSON sẽ khác với kiểu any-getter trải phẳng.

Cũng cần xác định chính sách khi JSON đầu vào chứa cùng một key nhiều lần. Map thông thường chỉ giữ một entry cho mỗi key; giá trị trước có thể bị ghi đè. Nếu duplicate key là vấn đề bảo mật hoặc tính toàn vẹn, cần phát hiện và từ chối ngay trong quá trình đọc thay vì dựa vào Map để giữ lịch sử.

## 9. Unknown property và tương thích phiên bản API

Giữ extension data là một cách hỗ trợ forward compatibility: server phiên bản cũ có thể đọc payload của client phiên bản mới mà vẫn giữ các field mà nó chưa hiểu.

Ví dụ:

- Client v1 gửi eventId, eventType.
- Client v2 bổ sung priority.
- Client v3 bổ sung metadata.

Server v1 dùng @JsonAnySetter có thể giữ priority và metadata dù chưa có logic nghiệp vụ cho chúng. Khi chuyển tiếp, @JsonAnyGetter phát lại các field đó.

Tuy nhiên, giữ lại không đồng nghĩa với hiểu hoặc hỗ trợ chúng. Server vẫn cần:

- Không dùng extension field chưa được xác thực cho quyết định bảo mật hoặc quyền truy cập.
- Kiểm soát kích thước và độ sâu dữ liệu mở rộng.
- Có chính sách versioning và allowlist cho các field mà nghiệp vụ thật sự sử dụng.
- Tránh phát lại dữ liệu nhạy cảm hoặc metadata nội bộ cho consumer không được phép nhận.
- Xác định extension nào chỉ được giữ để forward, extension nào được xử lý và extension nào phải từ chối.

Với API public, việc chấp nhận mọi field lạ có thể làm client tin rằng server đã hiểu field đó. Tài liệu API nên nói rõ field mở rộng được giữ, bỏ qua hay bị từ chối.

## 10. Bảo mật khi giữ dữ liệu mở rộng

Một Map nhận mọi key chưa biết tạo ra một vùng dữ liệu linh hoạt, nhưng cũng mở rộng bề mặt đầu vào.

Một số nguyên tắc:

1. Giới hạn kích thước request và kích thước extension data.
2. Giới hạn độ sâu object/array lồng nhau.
3. Không tự động bind extension vào class tùy ý dựa trên tên class do client gửi.
4. Không dùng extension chưa xác thực để quyết định quyền, vai trò hoặc chính sách truy cập.
5. Lọc các key nội bộ hoặc key có thể làm xung đột với property chuẩn.
6. Xác thực kiểu và miền giá trị trước khi dùng extension trong nghiệp vụ.
7. Khi forward payload, xác định consumer nào được phép nhận từng nhóm metadata.

Đặc biệt, không bật polymorphic default typing rộng rãi chỉ để xử lý dữ liệu mở. Extension data nên được giữ dưới dạng JSON value thông thường (JsonNode, Map/List hoặc scalar), sau đó chuyển đổi sang kiểu cụ thể bằng quy tắc allowlist khi cần.

## 11. Kiểm thử giữ lại và bỏ qua property

Nên kiểm thử rõ chính sách đã chọn. Ví dụ với lớp có @JsonAnySetter và @JsonAnyGetter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class PartnerEventTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void retainsUnknownPropertiesAndWritesThemBack() throws Exception {
        String json = """
            {
              "eventId": "evt-42",
              "eventType": "USER_CREATED",
              "priority": 3,
              "metadata": {
                "region": "ap-southeast-1"
              }
            }
            """;

        PartnerEvent event = mapper.readValue(json, PartnerEvent.class);

        assertEquals("evt-42", event.getEventId());
        assertTrue(event.extensionProperties().containsKey("priority"));

        JsonNode metadata = event.extensionProperties().get("metadata");
        assertEquals("ap-southeast-1", metadata.path("region").asText());

        JsonNode output = mapper.readTree(
            mapper.writeValueAsString(event)
        );

        assertEquals(3, output.path("priority").intValue());
        assertEquals(
            "ap-southeast-1",
            output.path("metadata").path("region").asText()
        );
    }
}
~~~

Với DTO dùng @JsonIgnoreProperties(ignoreUnknown = true), test nên xác nhận field lạ không làm deserialize thất bại và không xuất hiện trong JSON serialize lại. Với cấu hình mặc định, test nên xác nhận payload có field không được khai báo bị từ chối.

Những test này làm rõ sự khác biệt giữa ba chính sách: fail, ignore và retain.

## 12. So sánh các cơ chế xử lý property không biết

| Cơ chế | Deserialize property lạ | Có giữ dữ liệu trong object? | Serialize lại |
|---|---|---|---|
| Mặc định FAIL_ON_UNKNOWN_PROPERTIES | Báo lỗi | Không | Không có object hoàn chỉnh từ payload lỗi |
| @JsonIgnoreProperties(ignoreUnknown = true) | Bỏ qua | Không | Field lạ không xuất hiện |
| Tắt FAIL_ON_UNKNOWN_PROPERTIES toàn mapper | Bỏ qua | Không | Field lạ không xuất hiện |
| @JsonAnySetter | Thu thập vào Map | Có | Chỉ khi có cơ chế serialize tương ứng |
| @JsonAnySetter + @JsonAnyGetter | Thu thập vào Map | Có | Trải Map thành property cùng cấp |

Hãy chọn theo ý nghĩa của ứng dụng:

- **Fail:** hợp đồng đóng, muốn phát hiện dữ liệu ngoài schema.
- **Ignore:** chỉ cần các field đã biết, không cần chuyển tiếp dữ liệu lạ.
- **Retain:** cần gateway, proxy, adapter hoặc hệ thống có schema mở giữ lại dữ liệu chưa hiểu.

## 13. Lựa chọn cấu trúc extension trong API

Có hai kiểu hợp đồng thường gặp.

### 13.1. Extension được trải phẳng bằng any-getter

~~~json
{
  "eventId": "evt-42",
  "eventType": "USER_CREATED",
  "priority": 3,
  "sourceRegion": "ap-southeast-1"
}
~~~

Ưu điểm là payload gọn và tương thích với API đã có. Nhược điểm là extension key có thể va chạm với property chuẩn trong tương lai.

### 13.2. Extension nằm trong một object riêng

~~~json
{
  "eventId": "evt-42",
  "eventType": "USER_CREATED",
  "extensions": {
    "priority": 3,
    "sourceRegion": "ap-southeast-1"
  }
}
~~~

Ưu điểm là namespace rõ ràng, giảm nguy cơ xung đột. DTO có thể khai báo:

~~~java
private Map<String, JsonNode> extensions;
~~~

Cấu trúc này không cần @JsonAnyGetter nếu muốn Map xuất hiện dưới key extensions như một property bình thường. Chọn một cấu trúc và công bố rõ trong schema API; không nên để server lúc thì trải phẳng, lúc thì lồng object tùy payload.

## 14. Ghi nhớ

- Property không biết có thể bị từ chối, bỏ qua hoặc giữ lại; ba lựa chọn có hệ quả khác nhau.
- Mặc định Jackson thường bật FAIL_ON_UNKNOWN_PROPERTIES, nên property không ánh xạ được có thể gây UnrecognizedPropertyException.
- @JsonIgnoreProperties(ignoreUnknown = true) bỏ qua field lạ nhưng không giữ chúng trong object.
- @JsonAnySetter nhận tên và giá trị property chưa biết, thường lưu vào Map.
- @JsonAnyGetter trải các entry trong Map thành property ở cùng cấp khi serialize.
- Map<String, Object> thuận tiện cho Java values; Map<String, JsonNode> giữ cấu trúc JSON rõ ràng hơn.
- Giữ extension data không có nghĩa server hiểu hoặc tin cậy dữ liệu đó; vẫn phải xác thực, giới hạn kích thước và kiểm soát việc forward.
- Tránh key extension trùng property chuẩn và xác định chính sách cho duplicate key.
- Dùng fail cho schema đóng, ignore khi không cần dữ liệu lạ, retain khi cần chuyển tiếp hoặc bảo toàn extension.

