# Giá trị thiếu, null, kiểu số và thời gian trong hợp đồng dữ liệu Spring JMS

## 1. Bản chất vấn đề: hợp đồng dữ liệu chứ không chỉ là một class Java

Trong hệ thống dùng Spring Framework JMS, producer gửi message tới một queue/topic; consumer thường nhận message **sau một khoảng thời gian** và có thể chạy ở phiên bản ứng dụng khác. MessageConverter/Jackson giúp chuyển đổi giữa đối tượng Java và dữ liệu trong JMS Message, nhưng không thể tự biết hết **ý nghĩa nghiệp vụ** của từng field.

Giả sử consumer nhận ba JSON document:

~~~json
{"orderId":"O-42","discount":0}
{"orderId":"O-42","discount":null}
{"orderId":"O-42"}
~~~

Chúng không nhất thiết tương đương:

1. **discount = 0**: có thể là mức giảm hợp lệ bằng không.
2. **discount = null**: producer chủ động truyền một giá trị null, tùy contract có thể nghĩa là không biết/chưa được tính hoặc yêu cầu xóa.
3. **discount không xuất hiện**: producer không gửi field đó. Trong event phiên bản cũ, đây có thể là field chưa được hỗ trợ; trong patch, có thể là “không thay đổi”.

Nếu lập trình viên deserialize cả ba thành một Java primitive int với giá trị mặc định 0, thông tin phân biệt đã bị mất. Tương tự, số tiền chuyển sang double có thể bị sai chính xác, còn thời gian không có timezone có thể bị hiểu lệch giữa hai service.

Mục tiêu của bài:

- Định nghĩa rõ **missing**, **explicit null**, **empty**, **zero** và **default**.
- Chọn kiểu số không mất precision và kiểu thời gian không mơ hồ.
- Thiết kế hợp đồng payload khi dùng TextMessage/JSON, MapMessage và JMS message properties.
- Dùng Jackson/JmsTemplate đúng vai trò, không cho converter tự quyết business semantics.
- Xử lý tương thích schema, validation và lỗi chuyển đổi trong các consumer bất đồng bộ.
- Thực hành với Java 17, Spring Boot, Jackson, ActiveMQ Artemis.

## 2. Tách ba lớp: payload, JMS metadata và Java object

~~~mermaid
flowchart LR
    A["Domain object Java"] --> B["ObjectMapper / MessageConverter"]
    B --> C["JMS Message: TextMessage JSON hoặc MapMessage"]
    C --> D["Broker: queue/topic"]
    D --> E["JMS Message"]
    E --> F["Parse + validate contract"]
    F --> G["Domain object consumer"]
~~~

Một JMS message có:

| Lớp | Chứa gì? | Ví dụ | Quy tắc |
| --- | --- | --- | --- |
| Standard JMS headers | Thông tin vận chuyển JMS | JMSMessageID, JMSTimestamp, JMSExpiration, JMSType | API/protocol quy định; không đồng nhất với field nghiệp vụ. |
| JMS properties | Metadata kiểu đơn giản để filter/routing | SchemaVersion, TenantId, EventKind | Tên/kiểu theo JMS; selector có thể truy cập. |
| Message body | Payload nghiệp vụ | JSON trong TextMessage, key/value trong MapMessage | Hợp đồng dữ liệu do producer/consumer thống nhất. |
| Java DTO | Biểu diễn trong một ứng dụng | record OrderCreated(...) | Không phải wire format và có thể tiến hóa theo thời gian. |

**JmsTemplate không tự chuẩn hóa null/số/thời gian.** Nó chỉ dùng MessageConverter được cấu hình. Converter tạo/đọc message; việc một field được phép thiếu, được phép null, có giới hạn số nào, dùng timezone nào là trách nhiệm của **contract và validation**.

Một minh họa với default SimpleMessageConverter:

~~~java
jmsTemplate.convertAndSend("orders.events", jsonText);
String json =
        (String) jmsTemplate.receiveAndConvert("orders.events");
~~~

Snippet này cần bean jmsTemplate và jsonText. Default SimpleMessageConverter chuyển String ↔ TextMessage; nó **không parse JSON thành record nghiệp vụ**. Nếu dùng MappingJackson2MessageConverter hoặc converter tùy chỉnh, hành vi nhận có thể khác. Không mặc định rằng Spring tự nhận mọi schema JSON.

## 3. Các trạng thái khác nhau phải được ghi vào hợp đồng

| Trạng thái | JSON ví dụ | Ý nghĩa tiềm năng | Lỗi khi gộp chung |
| --- | --- | --- | --- |
| Field thiếu | {} | Chưa hỗ trợ, không biết, hoặc “không thay đổi” | Tự gán 0/null và đánh mất thông tin vắng mặt. |
| Explicit null | {"note":null} | Không có giá trị hoặc chủ động xóa (tùy nghiệp vụ) | Tưởng là thiếu field, không phát hiện lệnh clear. |
| Chuỗi rỗng | {"note":""} | Giá trị được cung cấp nhưng rỗng | Coi như null dù có thể mang nghĩa khác. |
| Chuỗi chỉ khoảng trắng | {"note":"   "} | Dữ liệu không hợp lệ hoặc input cần chuẩn hóa | Trim âm thầm làm mất ý nghĩa. |
| Số 0 | {"quantity":0} | Số đếm bằng không | Coi 0 thành “chưa có thông tin”. |
| false | {"enabled":false} | Trạng thái được chủ động tắt | Coi false là field vắng mặt. |
| Mảng rỗng | {"items":[]} | Tập hợp có kích thước 0 | Nhầm với chưa load/không hỗ trợ. |
| Object rỗng | {"details":{}} | Có object nhưng chưa có thuộc tính | Nhầm với null hoặc thiếu object. |

### 3.1. Quy tắc quan trọng: missing khác null

Hãy hỏi trước khi coding:

- Field có **required** không? Nếu required, cả missing và null có thể bị coi là invalid.
- Nếu optional, **missing** nghĩa là gì? Không có dữ liệu ở phiên bản cũ, dùng default, hay “không thay đổi”?
- **Null** có được gửi không? Nó có khác missing không?
- Giá trị **0**, **false**, **""**, **[]** có được giữ nguyên là giá trị hợp lệ không?
- Khi producer nâng phiên bản, consumer cũ gặp field mới sẽ làm gì?

Tránh quy tắc chung “mọi null và empty đều đổi thành default”. Điều đó có thể đúng ở một field UI nhưng sai hoàn toàn với message biểu diễn giao dịch hoặc lệnh cập nhật.

### 3.2. Event snapshot khác partial update

Hai kiểu message có ý nghĩa null thường khác nhau:

**Event snapshot:** mô tả trạng thái tại một thời điểm.

~~~json
{
  "eventType": "customer.snapshot.v1",
  "customerId": "C-42",
  "displayName": "An",
  "phone": null
}
~~~

Nếu contract quy định phone null là “chưa biết số điện thoại”, nó có thể hợp lệ. Nhưng nếu phone thiếu trong snapshot, có thể là producer cũ không hỗ trợ field đó. Ứng dụng cần policy xác định, thay vì gộp null và missing.

**Partial update/patch:** mô tả thay đổi cần áp dụng:

~~~json
{
  "eventType": "customer.patch.v1",
  "customerId": "C-42",
  "changes": {
    "phone": null
  }
}
~~~

Trong một **quy ước patch do ứng dụng xác định**: không có phone trong changes nghĩa là giữ nguyên, có phone:null nghĩa là xóa, có phone:"..." nghĩa là thay. Đây là ví dụ về *business semantics*, không phải hành vi mặc định của JMS hay Jackson.

Nếu gửi patch kiểu này, DTO Java chỉ có String phone thường **không đủ** để phân biệt field không xuất hiện với explicit null. Cần parsing trên JSON tree, wrapper ba trạng thái hoặc schema patch chuyên dụng.

## 4. Ví dụ hợp đồng JSON có kiểu được định nghĩa chặt

Giả sử hệ thống trao đổi event order.created.v1:

~~~json
{
  "eventId": "evt-0042",
  "schemaVersion": 1,
  "orderId": "O-42",
  "currency": "USD",
  "total": "10.25",
  "quantity": 2,
  "occurredAt": "2026-10-30T10:00:00Z",
  "customerNote": null
}
~~~

Ví dụ chủ động dùng **total là decimal string**, không phải JSON floating-point, để consumer ở nhiều ngôn ngữ giữ nguyên giá trị thập phân khi cần. Một contract khác có thể dùng JSON number đi vào BigDecimal, hoặc tiền theo **integer minor units**; quan trọng là hai phía thống nhất.

| Field | JSON type | Java type khuyến nghị | Required? | Quy tắc hợp đồng |
| --- | --- | --- | --- | --- |
| eventId | string | String | Có | Không rỗng, duy nhất theo domain, không đổi theo redelivery. |
| schemaVersion | integer | int hoặc Integer sau validation | Có | Bắt đầu từ 1; parser phải từ chối kiểu String "1" nếu contract integer. |
| orderId | string | String | Có | Định danh, không được chuyển thành số để tính toán. |
| currency | string | String / enum được kiểm soát | Có | Ví dụ USD; quy tắc số chữ số thập phân theo hợp đồng. |
| total | string decimal | BigDecimal sau parse | Có | Ví dụ "10.25", đúng precision/scale, không NaN/Infinity. |
| quantity | integer | long/Long hoặc int/Integer | Có | Phạm vi được công bố, ví dụ quantity >= 0. |
| occurredAt | string ISO-8601 UTC | Instant | Có | Thời điểm sự kiện UTC; có hậu tố Z. |
| customerNote | string hoặc null | Wrapper ba trạng thái nếu cần | Tùy chọn | Missing/null/empty có ý nghĩa riêng. |

Đừng lấy DTO Java làm đặc tả duy nhất. Contract cần mô tả **wire type**, điều kiện required, nullability, range, thời gian, đơn vị và cách tiến hóa phiên bản.

### 4.1. Payload contract và JMS properties phải thống nhất

Có thể thêm JMS metadata:

~~~java
message.setJMSType("order.created.v1");
message.setIntProperty("SchemaVersion", 1);
message.setStringProperty("TenantId", "tenant-a");
~~~

Đây là snippet, biến message là jakarta.jms.Message vừa được tạo. JMSType là **header chuẩn**, SchemaVersion/TenantId là **properties do ứng dụng đặt**. Nếu body cũng chứa schemaVersion=1, producer phải bảo đảm chúng khớp; nếu khác nhau, consumer nên từ chối hoặc đưa vào đường lỗi có kiểm soát.

Selector có thể lọc SchemaVersion=1, nhưng **không tự kiểm tra** body có trường schemaVersion, total hoặc occurredAt đúng kiểu. Selector là tuyến lọc metadata, không phải hệ thống schema validation.

## 5. Jackson: phát hiện field thiếu và explicit null trước khi bind DTO

Trong Jackson, đọc JSON dưới dạng **JsonNode/ObjectNode** cho phép giữ riêng các trạng thái:

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode missing = mapper.readTree("{\"noteOwner\":\"n/a\"}");
JsonNode explicitNull = mapper.readTree("{\"customerNote\":null}");
JsonNode empty = mapper.readTree("{\"customerNote\":\"\"}");

// Field vắng mặt:
System.out.println(missing.has("customerNote"));         // false

// Field tồn tại nhưng là JSON null:
System.out.println(explicitNull.has("customerNote"));    // true
System.out.println(explicitNull.get("customerNote").isNull()); // true

// Field tồn tại và là chuỗi rỗng:
System.out.println(empty.hasNonNull("customerNote"));    // true
System.out.println(empty.get("customerNote").asText().isEmpty()); // true
~~~

Đây là snippet Java có import com.fasterxml.jackson.databind.JsonNode/ObjectMapper và được gọi trong method có throws JsonProcessingException; không phải một class main độc lập. Dòng comment chỉ mô tả giá trị in tương ứng.

### 5.1. get, path, has và hasNonNull

| API | Field thiếu | Field là JSON null |
| --- | --- | --- |
| node.has("x") | false | true |
| node.hasNonNull("x") | false | false |
| node.get("x") | Java null | NullNode |
| node.path("x") | MissingNode | NullNode |
| node.path("x").isMissingNode() | true | false |
| node.get("x").isNull() | Lỗi NullPointerException nếu không kiểm tra get trước | true |

**Sai lầm phổ biến:** dùng node.path("x").asText() hoặc DTO nullable rồi suy ra missing và null là như nhau. Nhiều phương thức convenience có default/fallback khiến hai trạng thái bị gộp. Khi nghiệp vụ cần phân biệt, trước tiên kiểm tra **có key hay không**, sau đó mới kiểm tra giá trị.

### 5.2. Một mô hình ba trạng thái

Nếu contract thực sự cần ba trường hợp missing/null/value, có thể khai báo wrapper Java 17:

~~~java
sealed interface FieldValue<T>
        permits Absent, ExplicitNull, Present {}

record Absent<T>() implements FieldValue<T> {}
record ExplicitNull<T>() implements FieldValue<T> {}
record Present<T>(T value) implements FieldValue<T> {}
~~~

Những record/interface trên là snippet; cần thêm một parser áp dụng cho từng field. Ví dụ:

~~~java
static FieldValue<String> readOptionalText(
        JsonNode root, String name) {

    if (!root.has(name)) {
        return new Absent<>();
    }
    JsonNode value = root.get(name);
    if (value.isNull()) {
        return new ExplicitNull<>();
    }
    if (!value.isTextual()) {
        throw new IllegalArgumentException(
                name + " must be string or null");
    }
    return new Present<>(value.textValue());
}
~~~

Với snippet này, value="" vẫn là **Present("")**, không trở thành absent/null. Tại nơi xử lý patch, ứng dụng có thể triển khai chính sách:

- Absent -> không đổi dữ liệu cũ.
- ExplicitNull -> xóa dữ liệu nếu hợp đồng cho phép.
- Present("") -> lưu chuỗi rỗng hoặc reject, tùy nghiệp vụ.

Đừng mặc định mọi event đều cần một wrapper như trên; nó thích hợp khi semantics ba trạng thái thực sự quan trọng.

### 5.3. Vì sao primitive và record có thể che giấu missing?

~~~java
record OrderDto(int quantity, boolean confirmed, String note) {}
~~~

Nếu chỉ bind JSON vào kiểu này mà không validate, consumer rất dễ nhầm **quantity=0** với field quantity thiếu/null; boolean false cũng dễ bị hiểu nhầm. Với một số cấu hình Jackson, null cho primitive có thể được coerce thành giá trị mặc định, còn field thiếu có thể nhận giá trị mặc định của Java.

Đối với field bắt buộc, nên **validate JSON shape trước**, hoặc bật các chế độ strict tương ứng của Jackson và kiểm thử với phiên bản thư viện thực tế:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
mapper.enable(
        DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES);
~~~

Đây là snippet cần ObjectMapper/DeserializationFeature đã import. Những cấu hình strict này có tác động tới toàn bộ quá trình bind và cần được chọn đúng theo schema; không thay thế validation cho số âm, precision, format thời gian, chuỗi rỗng, hoặc các trường hợp optional.

**Cảnh báo với @JsonProperty(required=true):** nó không nhất thiết enforce mọi field trong mọi kiểu binding/setter giống nhau. Nên có schema validation hoặc custom validation rõ ràng và integration tests cho đường parse dùng thật.

### 5.4. @JsonInclude và mất phân biệt null

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
record CustomerEvent(String name, String phone) {}
~~~

Đoạn trên là snippet. Với NON_NULL, giá trị phone=null bị bỏ khỏi JSON khi serialize; nếu phía nhận cần phân biệt **explicit null** với **missing**, policy này vô tình xóa mất thông tin. Các lựa chọn khác như NON_ABSENT/NON_EMPTY cũng có thể khiến field biến mất khi serialize. Hãy chọn policy include/omit theo hợp đồng, đừng bật globally mà không kiểm thử wire output.

## 6. Kiểu số: integer, decimal, precision và range

### 6.1. Zero không phải missing

~~~json
{"quantity":0}
~~~

Quantity=0 là **một giá trị được gửi**. Nó có thể hợp lệ (giỏ hàng không có mặt hàng) hoặc invalid (lệnh mua yêu cầu quantity >=1) nhưng phải được xét theo domain rule.

Không viết:

~~~java
int quantity = node.path("quantity").asInt(0);
// Không phân biệt missing, null, sai kiểu và giá trị 0 hợp lệ.
~~~

Hãy validate tồn tại, JSON type và range:

~~~java
JsonNode q = node.get("quantity");

if (q == null || !q.isIntegralNumber()
        || !q.canConvertToInt()) {
    throw new IllegalArgumentException(
            "quantity must be a 32-bit JSON integer");
}
int quantity = q.intValue();
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity cannot be negative");
}
~~~

Snippet này không chấp nhận quantity="2", quantity=2.0, quantity=null, quantity thiếu hoặc số quá lớn cho int. Nếu contract cho phép long, dùng canConvertToLong/longValue và kiểm tra range theo business.

### 6.2. Không dùng double/float cho số tiền cần tính chính xác

Java double biểu diễn nhị phân, nên nhiều giá trị thập phân như 0.1 không có biểu diễn chính xác. Ví dụ:

~~~java
double x = 0.1 + 0.2;
System.out.println(x == 0.3); // false

BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
System.out.println(a.add(b).toPlainString()); // 0.30
~~~

Đây là snippet có import java.math.BigDecimal. Với tiền tệ, tỷ giá, số lượng đo lường đòi hỏi precision cao, dùng **BigDecimal** hoặc **integer minor units** và xác định rõ đơn vị. Không dùng new BigDecimal(0.1), vì nó nhận sai số đã có trong double; hãy dùng new BigDecimal("0.1") hoặc BigDecimal.valueOf(double) khi đầu vào buộc là double và semantics được hiểu rõ.

### 6.3. Chọn wire representation cho decimal

Ba cách phổ biến:

**A. JSON number + BigDecimal ở consumer**

~~~json
{"amount":10.25,"currency":"USD"}
~~~

Hợp lệ khi tất cả consumer thật sự đọc thành decimal chính xác (ví dụ Jackson BigDecimal) và không trung chuyển qua kiểu floating-point làm mất precision. Với JSON tree hoặc Map không type, cân nhắc:

~~~java
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
~~~

Bật tính năng này giúp Jackson generic floating number không mặc nhiên thành double trong các đường bind phù hợp; tuy nhiên cách giữ scale/trailing zeros phụ thuộc đường parse và config. Phải kiểm thử nếu 10.20 khác 10.2 có ý nghĩa trong contract.

**B. Decimal string**

~~~json
{"amount":"10.25","currency":"USD"}
~~~

Parser nhận String và dùng new BigDecimal(text), có thể validate được pattern, range và scale. Cách này tránh nhiều rủi ro JSON number bị JS consumer làm tròn, nhưng nhược điểm là schema phải ghi rõ kiểu **string**, không được nửa service gửi string nửa service gửi number.

**C. Integer minor units**

~~~json
{"amountMinor":1025,"currency":"USD","scale":2}
~~~

Giá trị 1025 tương đương 10.25 USD khi scale=2. Với JPY hoặc loại tài sản khác, đơn vị nhỏ nhất phải được công bố rõ; không tự giả định mọi currency có 2 chữ số. Integer minor units cần kiểm soát overflow và quy tắc scale. Đừng dùng tên amountMinor mà quên mô tả currency/unit.

### 6.4. Scale, rounding, range

~~~java
BigDecimal amount = new BigDecimal("10.25");
amount = amount.setScale(2, RoundingMode.UNNECESSARY);
if (amount.signum() < 0) {
    throw new IllegalArgumentException(
            "Amount must be nonnegative");
}
~~~

Snippet này cần import BigDecimal/RoundingMode. UNNECESSARY buộc giá trị không cần làm tròn khi đưa về scale, tránh tự cắt tiền. Với hợp đồng chỉ cho phép **đúng hai chữ số** ở wire format, còn nên kiểm tra regex/JSON schema trước khi BigDecimal parse để nhận diện "10.2" khác "10.20" nếu yêu cầu là lexical/canonical.

BigDecimal.equals(...) còn so cả scale: new BigDecimal("10.0").equals(new BigDecimal("10.00")) là false; compareTo(...) cho thấy giá trị số học bằng nhau. Quy tắc nghiệp vụ về tính bằng nhau, biểu diễn và lưu trữ cần tách bạch.

### 6.5. JSON integer lớn và giới hạn JavaScript

Java long có 64-bit signed range; JavaScript Number chỉ bảo toàn integer chính xác tới **2^53 - 1**. Nếu gửi một ID số dài hoặc epoch nanosecond vượt safe integer qua JavaScript, có thể bị thay đổi bit giá trị.

**Khuyến nghị:** ID là opaque string, không phải số để cộng trừ. Nếu consumer dùng nhiều ngôn ngữ, cân nhắc integer lớn ở dạng string với schema cụ thể; nếu dùng JSON integer number thì ghi rõ giới hạn chính xác và kiểu của mọi consumer.

### 6.6. NaN, Infinity và chia cho 0

JSON chuẩn không có literal NaN, Infinity hoặc -Infinity. Không sử dụng chúng như “missing amount”; đó là trạng thái dữ liệu không hợp lệ. Nếu cảm biến có giá trị không đo được, dùng nullable field hoặc trạng thái riêng:

~~~json
{"temperature":null,"quality":"NO_READING"}
~~~

Trong hệ thống tài chính, dùng một error/status field được enum hóa thay cho sentinel như -1, Double.NaN hay magic number 999999999.

## 7. Kiểu thời gian: Instant, OffsetDateTime, LocalDate và zone

Thời gian là nguồn lỗi tinh vi: 2026-10-30 10:00 có thể là 10 giờ tại Hà Nội, Tokyo hay UTC. Nếu producer và consumer hiểu khác nhau, cùng một timestamp có thể lệch nhiều giờ.

### 7.1. Chọn kiểu theo ý nghĩa nghiệp vụ

| Ý nghĩa | Wire format đề xuất | Java type | Ví dụ |
| --- | --- | --- | --- |
| Một thời điểm tuyệt đối | ISO-8601/RFC3339 có offset; khuyên UTC Z | Instant / OffsetDateTime | "2026-10-30T10:00:00Z" |
| Ngày lịch không có giờ | ISO date | LocalDate | "2026-10-30" |
| Giờ địa phương phục vụ lịch hẹn | LocalDateTime **kèm** ZoneId hoặc offset được công bố | LocalDateTime + ZoneId | "2026-10-30T09:00:00", "Asia/Ho_Chi_Minh" |
| Khoảng thời lượng | ISO-8601 duration hoặc số với đơn vị rõ ràng | Duration | "PT15M" hoặc durationMs=900000 |
| Mốc epoch tuyệt đối | integer với đơn vị trong tên/schema | Instant.ofEpochMilli(...) | occurredAtEpochMs:1793354400000 |
| Timezone cần giữ tên vùng/quy tắc DST | IANA Zone ID | ZoneId | "Europe/Paris" |

Mốc epoch trong bảng chỉ là **ví dụ về định dạng**, không cần tính tay để hiểu contract. Khi triển khai, kiểm thử mốc cụ thể bằng thư viện thời gian và đồng bộ timezone hệ thống.

### 7.2. Vì sao Instant thường phù hợp cho event time?

~~~java
Instant occurredAt =
        Instant.parse("2026-10-30T10:00:00Z");

System.out.println(occurredAt);
// 2026-10-30T10:00:00Z
~~~

Instant biểu diễn một điểm trên timeline, không phụ thuộc timezone mặc định của máy. Cùng Instant có thể hiển thị ở Asia/Ho_Chi_Minh và Europe/Paris khác nhau nhưng vẫn là cùng một thời điểm.

**Không lưu LocalDateTime đơn độc để mô tả một event time tuyệt đối.** LocalDateTime không có offset/ZoneId nên không biết nó nằm ở đâu trên timeline. Nếu nhận LocalDateTime vì hệ thống nguồn chỉ có “giờ địa phương”, phải có ZoneId được quy định rõ và chính sách cho giờ trùng/không tồn tại khi chuyển DST.

### 7.3. Date-only không phải instant tại 00:00 UTC

Ngày sinh, ngày giao hàng hoặc ngày quyết toán thường là **ngày lịch**, ví dụ:

~~~json
{"deliveryDate":"2026-11-01"}
~~~

Nếu biến LocalDate thành Instant theo một timezone tùy ý rồi deserialize ở nơi khác, ngày lịch có thể bị lệch. Hãy giữ LocalDate trong contract date-only. Khi cần một thời điểm deadline tuyệt đối (ví dụ hết hạn cuối ngày), xác định timezone và thời điểm hết hạn cụ thể.

### 7.4. Epoch seconds và milliseconds

~~~java
Instant fromSeconds =
        Instant.ofEpochSecond(1_700_000_000L);
Instant fromMillis =
        Instant.ofEpochMilli(1_700_000_000_000L);

// Hai giá trị cùng biểu diễn một thời điểm.
System.out.println(fromSeconds.equals(fromMillis)); // true
~~~

Đây là snippet Java 17 và số mẫu. Dù cả hai đều là integer, đơn vị khác nhau **1.000 lần**. Tránh tên trường timestamp không nói đơn vị. Nên đặt occurredAtEpochMs, scheduledAtEpochSeconds, timeoutMs..., hoặc chọn ISO-8601 string.

Tương tự, Kafka timestamp, Unix seconds, database timestamp, JMS header và ZonedDateTime không tự có cùng đơn vị/múi giờ. Chuyển đổi bằng API đã kiểm thử thay vì nhân chia số tùy tiện.

### 7.5. JavaTimeModule với Jackson

Khi dùng các kiểu java.time trong DTO, cấu hình Jackson cho đúng:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

record EventTime(Instant occurredAt) {}
String json = mapper.writeValueAsString(
        new EventTime(
                Instant.parse("2026-10-30T10:00:00Z")));
~~~

Snippet cần import ObjectMapper, JavaTimeModule, SerializationFeature, Instant và khai báo record EventTime trong ngữ cảnh hợp lệ. Với cấu hình trên, wire format dạng chuỗi ISO-8601 là lựa chọn dễ đọc và dễ trao đổi. Khi Spring Boot tạo ObjectMapper tự động từ classpath Jackson Java Time, nhiều module đã được đăng ký; **đừng giả định ObjectMapper tự tạo bằng new ObjectMapper() cũng giống Boot's ObjectMapper**.

### 7.6. Thời gian nghiệp vụ khác JMS transport timestamps

JMS có các header JMSTimestamp, JMSExpiration và JMSDeliveryTime. Chúng biểu thị thông tin **vận chuyển**; không thay thế những field như occurredAt, approvedAt, paidAt hoặc businessDeadline.

Ví dụ:

~~~json
{
  "occurredAt": "2026-10-30T10:00:00Z",
  "businessDeadline": "2026-10-30T10:05:00Z"
}
~~~

Nếu message được gửi lại sau một phút, JMSMessageID và JMSTimestamp có thể thay đổi, nhưng occurredAt vẫn là thời điểm sự kiện gốc. Nếu cần biết tác vụ có còn hợp lệ hay không, kiểm tra businessDeadline/state; không chỉ so JMSExpiration hoặc thời gian receive.

## 8. JMS MapMessage và message properties: khác JSON object

MapMessage là một loại JMS message có body gồm tên và giá trị kiểu đơn giản. Nó **không phải JSON document** và không tự hỗ trợ BigDecimal, Instant hay các DTO tùy ý trong MapMessage body.

Ví dụ:

~~~java
MapMessage message = session.createMapMessage();
message.setString("eventId", "evt-0042");
message.setInt("quantity", 0);
message.setString("amount", "10.25");
message.setLong("occurredAtEpochMs", 1793354400000L);
~~~

Snippet cần JMS Session và import jakarta.jms.MapMessage. Nếu cần tiền dạng decimal, đặt String có canonical format như "10.25" rồi parse BigDecimal ở consumer. Nếu chọn timestamp epoch, ghi rõ đơn vị ms và xác nhận giá trị theo một Instant cụ thể bằng test; **không** giả định MapMessage chứa trực tiếp Instant.

### 8.1. itemExists phân biệt field thiếu

~~~java
if (message.itemExists("quantity")) {
    int qty = message.getInt("quantity");
} else {
    // Field quantity không tồn tại trong MapMessage body.
}
~~~

Theo Jakarta Messaging, MapMessage.getObject("name") có thể trả null nếu field thiếu; còn itemExists("name") phân biệt có entry hay không. Khi cần nhận diện missing, **không chỉ gọi getInt/getLong/getString và đoán**. Một số primitive getter đọc null có thể dẫn đến exception theo quy tắc chuyển kiểu của JMS, không phải tự trả zero.

Trạng thái null explicit trong JMS MapMessage cần xét hỗ trợ và cách producer đặt field theo provider/contract. Nếu ba trạng thái missing/null/value là trọng tâm, JSON trong TextMessage thường dễ biểu diễn và validate tường minh hơn.

### 8.2. JMS message properties có giới hạn kiểu

~~~java
message.setStringProperty("TenantId", "tenant-a");
message.setIntProperty("SchemaVersion", 1);
message.setLongProperty("OccurredAtEpochMs", 1793354400000L);
~~~

JMS properties chỉ cho các kiểu primitive/wrapper và String được chuẩn hỗ trợ. **BigDecimal và Instant không phải JMS property types hợp lệ**; không gửi trực tiếp:

~~~java
// Không hợp lệ cho JMS property chuẩn:
message.setObjectProperty("Amount", new BigDecimal("10.25"));
// Có thể ném MessageFormatException.
~~~

Đó là anti-pattern, không phải mã để chạy. Tương tự MapMessage.setObject("Amount", BigDecimal) không phải phương thức chuẩn để gửi BigDecimal object. Chuyển sang String có schema, integer minor units hoặc body JSON.

### 8.3. Property type khác String cũng khác selector type

~~~java
message.setStringProperty("SchemaVersion", "1");
~~~

Trông giống số nhưng thực tế là String. Nếu consumer có selector SchemaVersion >= 1 với numeric literal thì kết quả có thể không match theo ý muốn. Hãy dùng setIntProperty("SchemaVersion", 1) và khai báo kiểu trên contract.

Đừng tự coi missing/explicit null ở message property giống JSON null. JMS selectors dùng logic ba giá trị TRUE/FALSE/UNKNOWN khi thiếu property; các setter/getter và kiểu dữ liệu JMS khác với JSON object. Để validate payload, đọc body bằng converter/parser riêng thay vì suy từ selector.

## 9. MappingJackson2MessageConverter trong Spring JMS: đúng và đủ

Spring Framework 6.x cung cấp **org.springframework.jms.support.converter.MappingJackson2MessageConverter** để chuyển đối tượng Java thành JSON JMS message, và ngược lại.

### 9.1. Những default dễ gây bất ngờ

- Converter mặc định **tạo BytesMessage**, không phải TextMessage. Muốn JSON text dễ đọc, gọi setTargetType(MessageType.TEXT).
- Để converter có thể khôi phục đối tượng Java khi nhận, thường phải cấu hình **type-id message property** bằng setTypeIdPropertyName(...).
- Nếu không cấu hình mapping, type ID có thể là tên Java class; dùng ID ổn định theo hợp đồng thay vì buộc consumer biết class name của producer.
- Converter **không tự validate schema nghiệp vụ**, cũng không tự biết missing/null/zero nào hợp lệ.
- ObjectMapper áp dụng rule về null inclusion, numeric coercion và JavaTimeModule; thống nhất cấu hình giữa các service.

### 9.2. Cấu hình converter có type mapping

~~~java
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Bean
MessageConverter messageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setObjectMapper(objectMapper);
    converter.setTypeIdPropertyName("PayloadType");
    converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedV1.class));
    return converter;
}
~~~

Đây là **snippet cấu hình** trong Spring @Configuration, cần khai báo class/record OrderCreatedV1 riêng. Các nơi gửi/nhận phải dùng cùng type-id mapping và cấu hình converter; đừng mặc định custom JmsTemplate và listener factory riêng tự đồng bộ nếu không gắn converter vào cả hai.

Ví dụ DTO:

~~~java
record OrderCreatedV1(
        String eventId,
        BigDecimal total,
        Instant occurredAt,
        String customerNote) {}
~~~

Đây là snippet cần import BigDecimal, Instant. Mapping kiểu này chưa đủ để phân biệt “customerNote thiếu” với “customerNote=null” sau khi bind; cần validate JSON tree trước khi mất thông tin hoặc dùng kiểu DTO/deserialize chuyên dụng. Nếu chọn wire contract decimal string, phải định nghĩa cơ chế đọc BigDecimal từ String rõ ràng; Jackson có thể coerce trong một số cấu hình nhưng **không nên dựa vào ép kiểu ngầm**.

### 9.3. Dùng JSON tree tại boundary khi cần strict contract

Nếu consumer cần kiểm tra chính xác field thiếu/null, giới hạn số và timezone, có thể dùng hướng:

1. Nhận TextMessage/JSON String.
2. Parse bằng ObjectMapper.readTree(...).
3. Validate required, nullability, JSON type, decimal lexical format, time zone/instant, range.
4. Chuyển sang DTO/domain object đã được đảm bảo invariant.
5. Xử lý nghiệp vụ và commit/ack theo cấu hình.

Đây cũng là lý do một số hệ thống chủ động dùng default String ↔ TextMessage converter, thay vì chuyển thẳng sang record bằng Jackson converter. Lựa chọn nào cũng hợp lệ nếu kiểm soát đầy đủ contract.

## 10. Dự án chạy được: Java 17 + Spring Boot 3.3 + Artemis

Ứng dụng thực hành đưa **ba JSON document** qua một queue JMS rồi parse và validate bằng Jackson:

- Message 1 có customerNote:null.
- Message 2 **không có** customerNote.
- Message 3 có customerNote:"" (chuỗi rỗng).

Cả ba dùng cùng total="0.10" và occurredAt ở UTC. Chương trình in kết quả ba trạng thái, giữ nguyên độ chính xác BigDecimal và Instant. Ví dụ dùng JmsTemplate với default String/TextMessage converter để **kiểm soát việc validate ở boundary**, không dựa vào deserialization ngầm.

### 10.1. Yêu cầu

- JDK 17+, Maven, Docker.
- Cổng TCP 61616 chưa bị chiếm.
- Broker Artemis cho phép sử dụng queue demo (image mặc định cho môi trường học thường auto-create).
- Môi trường phát triển dùng mật khẩu demo; không dùng trong production.

Khởi động broker:

~~~bash
docker run --detach --rm --name contract-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ broker sẵn sàng. Kiểm tra log bằng docker logs contract-demo-broker nếu client không kết nối được.

Cấu trúc project:

~~~text
jms-contract-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmscontract/JmsContractDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.3.13 là phiên bản cố định **để tái lập demo API Jakarta JMS/Spring 6**, không phải khuyến nghị dùng phiên bản đã hết vòng hỗ trợ làm dependency production. Khi triển khai thật, chọn Spring Boot/Jackson còn được bảo trì và chạy lại integration tests theo phiên bản đó.

### 10.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
spring.jms.template.receive-timeout=5s
~~~

Cấu hình dùng broker native bên ngoài; không yêu cầu HTTP server. Khi không khai báo MessageConverter bean tùy chỉnh, Spring Boot/JmsTemplate trong dự án này dùng converter String ↔ TextMessage cho dữ liệu String.

### 10.4. JmsContractDemoApplication.java

~~~java
package example.jmscontract;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsContractDemoApplication.class, args);
    }

    record ParsedEvent(
            String eventId,
            BigDecimal total,
            Instant occurredAt,
            String noteState) {}

    @Bean
    CommandLineRunner demonstrate(
            ConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        return args -> {
            JmsTemplate jms = new JmsTemplate(connectionFactory);
            jms.setReceiveTimeout(5_000L);

            // Queue tên ngẫu nhiên để tránh backlog từ lượt chạy trước.
            String queue = "demo.contract." +
                    UUID.randomUUID().toString().replace("-", "");

            String explicitNull = """
                    {
                      "eventId": "e-1",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z",
                      "customerNote": null
                    }
                    """;

            String absent = """
                    {
                      "eventId": "e-2",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z"
                    }
                    """;

            String empty = """
                    {
                      "eventId": "e-3",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z",
                      "customerNote": ""
                    }
                    """;

            jms.convertAndSend(queue, explicitNull);
            jms.convertAndSend(queue, absent);
            jms.convertAndSend(queue, empty);

            for (int i = 0; i < 3; i++) {
                Object incoming = jms.receiveAndConvert(queue);
                if (!(incoming instanceof String json)) {
                    throw new IllegalStateException(
                            "Expected JSON TextMessage");
                }

                ParsedEvent event = parseContract(
                        objectMapper, json);

                System.out.printf(
                        "%s | note=%s | amount=%s | at=%s%n",
                        event.eventId(),
                        event.noteState(),
                        event.total().toPlainString(),
                        event.occurredAt());
            }
        };
    }

    private static ParsedEvent parseContract(
            ObjectMapper mapper,
            String json) throws JsonProcessingException {

        JsonNode root = mapper.readTree(json);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException(
                    "Payload must be a JSON object");
        }

        String id = requiredText(root, "eventId");
        JsonNode version = root.get("schemaVersion");
        if (version == null
                || !version.isIntegralNumber()
                || !version.canConvertToInt()
                || version.intValue() != 1) {
            throw new IllegalArgumentException(
                    "schemaVersion must be integer 1");
        }

        String moneyText = requiredText(root, "total");
        if (!moneyText.matches(
                "(0|[1-9][0-9]*)\\.[0-9]{2}")) {
            throw new IllegalArgumentException(
                    "total must have exactly two decimals");
        }
        BigDecimal money =
                new BigDecimal(moneyText)
                        .setScale(2, RoundingMode.UNNECESSARY);

        String timeText = requiredText(root, "occurredAt");
        if (!timeText.endsWith("Z")) {
            throw new IllegalArgumentException(
                    "occurredAt must be UTC ISO-8601");
        }
        Instant occurredAt = Instant.parse(timeText);

        String noteState;
        if (!root.has("customerNote")) {
            noteState = "missing";
        } else {
            JsonNode note = root.get("customerNote");
            if (note.isNull()) {
                noteState = "null";
            } else if (note.isTextual()) {
                noteState = note.textValue().isEmpty()
                        ? "empty" : "text";
            } else {
                throw new IllegalArgumentException(
                        "customerNote must be string or null");
            }
        }

        return new ParsedEvent(id, money, occurredAt, noteState);
    }

    private static String requiredText(
            JsonNode root, String field) {

        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid text field: " + field);
        }
        return value.textValue();
    }
}
~~~

### 10.5. Chạy và stdout dự kiến

Từ thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Khi broker đã chạy, queue được auto-create và không có consumer cạnh tranh, các dòng **do System.out.printf trong chương trình** in ra là:

~~~text
e-1 | note=null | amount=0.10 | at=2026-10-30T10:00:00Z
e-2 | note=missing | amount=0.10 | at=2026-10-30T10:00:00Z
e-3 | note=empty | amount=0.10 | at=2026-10-30T10:00:00Z
~~~

Spring Boot/provider có thể in log trước/sau. Demo dùng queue ngẫu nhiên và một consumer đồng bộ duy nhất để hạn chế message tồn từ lần chạy trước. Nếu broker chưa sẵn sàng, thiếu quyền auto-create hoặc receive timeout, chương trình sẽ báo lỗi chứ không có stdout mong đợi.

Dừng container khi xong:

~~~bash
docker stop contract-demo-broker
~~~

### 10.6. Điều cần quan sát

1. Cùng một trường customerNote, chương trình giữ được **ba trạng thái** vì parse JsonNode trước khi bind.
2. Decimal "0.10" đi qua JMS dưới dạng TextMessage JSON và thành BigDecimal; toPlainString vẫn là "0.10", không có lỗi double.
3. occurredAt được parse thành Instant UTC, không phụ thuộc timezone mặc định của JVM.
4. schemaVersion bị validate là JSON integer bằng 1; string "1" không được chấp nhận âm thầm.
5. total đòi đúng 2 chữ số sau dấu chấm; null, missing, số float và string sai pattern bị reject rõ ràng.
6. Nếu thay String bằng Java record trong JmsTemplate.convertAndSend mà không cấu hình JSON converter, kết quả không còn tự động giống ví dụ này; default converter không biết chuyển arbitrary record.
7. Producer/consumer vẫn dùng **JMS queue**, còn contract validation là trách nhiệm của code ứng dụng.

### 10.7. Mở rộng demo để thấy lỗi được phát hiện

Thử thay một JSON string ở ví dụ bằng dữ liệu:

~~~json
{
  "eventId": "e-invalid",
  "schemaVersion": "1",
  "total": 0.10,
  "occurredAt": "2026-10-30 10:00:00"
}
~~~

Validator sẽ từ chối vì schemaVersion không phải JSON integer; nếu sửa version, validator tiếp tục phát hiện total phải là string; sửa tiếp sẽ tới vấn đề time format. Việc validate theo thứ tự không có nghĩa những lỗi còn lại không tồn tại.

Thử các giá trị:

- total="0.1": bị reject vì thiếu một chữ số thập phân theo lexical contract.
- total="0.10": hợp lệ, BigDecimal giữ scale 2.
- total=0.10: bị reject vì wire contract yêu cầu String, không âm thầm ép.
- total=null hoặc missing: bị reject.
- customerNote="" hoặc null hoặc missing: ba trạng thái hợp lệ khác nhau.
- customerNote=0: bị reject vì sai kiểu.
- occurredAt="2026-10-30T10:00:00Z": hợp lệ.
- occurredAt="2026-10-30T10:00:00": bị reject vì thiếu Z/offset và không thể biết múi giờ.
- schemaVersion=2: bị reject cho tới khi producer/consumer thống nhất contract v2.

Đây là contract mẫu cố ý chặt để dễ quan sát. Không có quy tắc JMS buộc mọi ứng dụng lưu decimal ở dạng String hay bắt buộc event time dùng Z; ứng dụng phải quyết định và kiểm thử.

## 11. Thiết kế tiến hóa schema mà không phá consumer cũ

Producer và consumer có thể deploy lệch phiên bản. Mọi thay đổi về null, number và time đều có khả năng trở thành breaking change.

### 11.1. Thêm field mới

Ví dụ v1 không có couponCode, v2 bổ sung:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-0043",
  "couponCode": null
}
~~~

Consumer v1 có thể bỏ qua field không biết nếu contract cho phép. Consumer v2 cần phân biệt missing ở dữ liệu v1 và explicit null ở dữ liệu v2 nếu semantics khác nhau. Không bắt buộc mọi service nâng đồng loạt, nhưng phải có compatibility matrix.

### 11.2. Những thay đổi dễ gây lỗi

| Thay đổi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| optional -> required | Message cũ thiếu field, consumer mới reject | Default theo version, rollout hai bước hoặc schema v2. |
| field nullable -> non-null | Dữ liệu cũ có explicit null | Migration/compatibility policy, không “coerce” ngầm. |
| JSON number -> string | Parser/selector/schema cũ nhận sai kiểu | Version hóa contract; không trộn wire types cùng một version. |
| int -> long | Consumer hoặc JS Number có thể không đủ range | Kiểm thử giới hạn, công bố numeric range. |
| double -> decimal | Thay đổi precision và quy tắc rounding | Dùng decimal string/minor units; migration rõ. |
| local datetime -> UTC instant | Khác semantics, có thể lệch timezone | Version và chuyển đổi được kiểm chứng từ nguồn. |
| timestamp seconds -> milliseconds | Chênh 1.000 lần | Đổi tên field kèm đơn vị hoặc tăng schemaVersion. |
| null -> omitted bởi NON_NULL | Mất lệnh clear trong patch | Đổi serialization policy hoặc dùng wrapper 3 trạng thái. |

### 11.3. Phương pháp rollout an toàn

1. **Định nghĩa v2**: giữ nguyên v1, ghi schema mới với nullability/range/time format.
2. **Consumer đi trước**: deploy consumer đọc v1 và v2, kiểm thử bằng payload v1/v2 thực.
3. **Producer đi sau**: bắt đầu gửi v2 khi tất cả consumer tương thích.
4. **Giám sát**: metric theo schemaVersion, lỗi parse, dead-letter, độ trễ/backlog; không gộp hết thành “JMS error”.
5. **Dọn v1 khi an toàn**: xác minh queue tồn đọng, durable subscriptions và replay streams trước khi bỏ v1.

Với message tồn trong queue nhiều ngày, schema backward compatibility thường quan trọng hơn dữ liệu REST đồng bộ chỉ tồn tại trong một request.

## 12. Validation, exception và retry trong consumer

### 12.1. Phân biệt lỗi contract và lỗi tạm thời

| Lỗi | Nhóm thường gặp | Hành động phù hợp |
| --- | --- | --- |
| Missing required field | Permanent contract error | Không retry vô hạn cùng payload; đưa vào DLQ/quarantine và cảnh báo producer. |
| Explicit null ở field non-nullable | Permanent contract error | Báo sai contract; giữ message để điều tra phù hợp. |
| Decimal sai kiểu, overflow | Permanent contract error | Reject và log reason/correlation id. |
| Thời gian thiếu timezone | Permanent contract error hoặc migration | Version-based handling; không tự đoán timezone. |
| Broker/network tạm mất | Transient transport failure | Retry/reconnect theo container/provider. |
| Database tạm unavailable | Transient dependency failure | Retry có backoff, idempotency, deadline. |
| Business state đã đổi | Domain conflict | Policy riêng: bỏ qua, bù, cảnh báo hoặc reject. |

Trong @JmsListener, exception khi parse/validation có thể ảnh hưởng transaction, acknowledgement và redelivery theo cấu hình listener container/broker. Nếu một message **vĩnh viễn invalid** bị rollback lặp lại mà không có retry limit, hệ thống có thể tạo poison-message loop.

Chọn rõ:

- Max delivery attempts và backoff.
- DLQ/quarantine, cho phép truy vết MessageID, eventId, schemaVersion, validation reason.
- Phương án reprocess sau khi sửa producer/parser.
- Masking/redaction khi log payload chứa PII hoặc token.
- Idempotency khi replay/redelivery, không dùng JMSMessageID làm business ID nếu một event có thể được republish.

### 12.2. Không tự vá payload sai bằng coercion mặc định

Ví dụ JSON gửi quantity="0" thay vì numeric 0:

~~~json
{"quantity":"0"}
~~~

Nếu contract yêu cầu integer, consumer không nên tự chấp nhận string trừ khi có quy tắc backward compatibility chính thức. Tương tự, occurredAt thiếu offset không được tự gắn timezone hiện tại của server. Coercion giúp “chạy qua”, nhưng có thể làm các service hiểu khác nhau mà khó phát hiện.

## 13. Kiểm thử hợp đồng producer-consumer

### 13.1. Ma trận test quan trọng

| Trường | Input | Mong đợi |
| --- | --- | --- |
| Required eventId | Missing/null/"" | Reject có lý do rõ ràng. |
| Optional customerNote | Missing | Ghi nhận trạng thái absent. |
| Optional customerNote | Explicit null | Ghi nhận trạng thái null. |
| Optional customerNote | Empty string | Ghi nhận giá trị rỗng, không tự coi null. |
| quantity | 0 | Hợp lệ hay không theo business, không đồng nhất missing. |
| quantity | "2" | Reject nếu contract yêu cầu JSON integer. |
| quantity | 2147483648 | Reject nếu Java int/range vượt giới hạn. |
| total | "0.10" | Parse BigDecimal chính xác, scale đúng. |
| total | 0.1 / null / missing | Reject nếu wire contract yêu cầu String. |
| total | "-1.00", "1e3", "1.234" | Reject theo chính sách canonical 2 decimals không âm. |
| occurredAt | UTC ISO-8601 có Z | Parse thành Instant; ổn định qua JVM timezone. |
| occurredAt | Local datetime không offset | Reject nếu contract là UTC instant. |
| occurredAtEpochMs | milliseconds | Không nhầm với seconds. |
| schemaVersion | 1 / 2 / "1" | Route đúng version; reject version hoặc type không được hỗ trợ. |
| message property SchemaVersion | int / String | Selector chỉ match theo đúng kiểu đã thống nhất. |
| replay/redelivery | Cùng eventId | Side effect chỉ thực hiện một lần theo idempotency policy. |

### 13.2. Những cấp kiểm thử cần có

- **Unit tests** cho JsonNode validation, BigDecimal, Instant, missing/null/zero.
- **Serialization round-trip tests**: producer object -> JSON -> consumer DTO, so sánh semantics.
- **Golden message fixtures**: JSON mẫu được version hóa, dùng cùng một bộ test ở nhiều service/ngôn ngữ.
- **Broker integration tests**: chạy thật JmsTemplate/MessageConverter, gửi vào Queue, nhận và xác minh headers/properties/body.
- **Compatibility tests**: consumer phiên bản mới đọc event cũ; consumer cũ đọc message mới nếu có yêu cầu backward compatibility.
- **DST/timezone tests**: chạy dưới các timezone JVM khác nhau, kiểm tra giá trị Instant/LocalDate không bị thay.
- **Retry/DLQ tests**: message sai vĩnh viễn không làm treo queue và được quản lý theo policy.

Nếu hệ thống có schema registry/JSON Schema, việc xác thực schema là lớp cần thiết nhưng **chưa đủ** cho business rules như amount>=0, currency scale, deadline hoặc trạng thái chuyển đổi.

## 14. Checklist thiết kế một contract đáng tin cậy

1. Xác định loại message (event/command/snapshot/patch) và semantics của từng field.
2. Tạo bảng required, nullable, optional; nêu rõ missing khác explicit null hay không.
3. Xác định liệu zero, false, "", [] là giá trị hợp lệ hay cần reject.
4. Không để Java primitive mặc định che mất required field chưa được gửi.
5. Với tiền, chọn BigDecimal/decimal string/minor units và giới hạn scale/range.
6. Với IDs, dùng String nếu không cần tính toán; tránh mất precision trên JavaScript consumers.
7. Chọn Instant/OffsetDateTime cho timestamp tuyệt đối; LocalDate cho date-only.
8. Với epoch timestamp, ghi rõ seconds/milliseconds, timezone và precision.
9. Tách JMSTimestamp/JMSExpiration khỏi occurredAt/businessDeadline.
10. Cấu hình MessageConverter và ObjectMapper nhất quán, kiểm tra target type và type-id property.
11. Tránh áp NON_NULL/NON_EMPTY globally nếu contract cần explicit null.
12. Validate ngay khi nhận trước khi áp dụng side effect; phân loại lỗi contract và lỗi hạ tầng.
13. Version hóa payload, giữ fixtures và test khả năng đọc các message cũ trong queue.
14. Dùng idempotency key, audit, monitoring và DLQ/quarantine cho message invalid.
15. Kiểm thử đúng wire format qua JMS broker thật, không chỉ serialize/deserialize object trong unit test.

## 15. Câu hỏi tự kiểm tra

**1. Missing và null khác nhau thế nào?** Missing là key không tồn tại; explicit null là key có mặt với giá trị JSON null. Ý nghĩa nghiệp vụ phụ thuộc loại event/patch và hợp đồng.

**2. Tại sao int quantity không phù hợp để tự xác định field có bị thiếu?** Vì giá trị mặc định có thể là 0, trùng với một giá trị hợp lệ; cần validate presence/type trước khi bind hoặc dùng wrapper thích hợp.

**3. total=0 có giống total=null không?** Không. Zero là numeric value; null là trạng thái không có giá trị.

**4. Tại sao dùng BigDecimal thay vì double cho tiền?** Để tránh lỗi biểu diễn binary floating-point khi cần tính toán decimal chính xác.

**5. BigDecimal("10.0") và BigDecimal("10.00") có equals bằng nhau không?** Không, equals so scale. compareTo cho thấy chúng bằng nhau về trị số.

**6. LocalDateTime có biểu diễn một instant tuyệt đối không?** Không. Nó thiếu zone/offset; muốn một thời điểm tuyệt đối cần thông tin timezone hoặc dùng Instant.

**7. Epoch 1_700_000_000 là seconds hay milliseconds?** Không thể biết chỉ từ tên timestamp. Contract phải ghi rõ đơn vị; ofEpochSecond và ofEpochMilli sẽ cho kết quả rất khác.

**8. JMS MapMessage có gửi trực tiếp BigDecimal hoặc Instant được không?** Không theo tập type chuẩn. Dùng String, primitive/integer unit hoặc payload JSON tùy contract.

**9. MappingJackson2MessageConverter mặc định tạo TextMessage không?** Không. Trong Spring Framework 6.x, target type mặc định là BytesMessage; cần setTargetType(MessageType.TEXT) nếu muốn TextMessage.

**10. Vì sao thêm @JsonInclude(NON_NULL) có thể phá hợp đồng patch?** Vì nó bỏ explicit null khỏi JSON và làm consumer không phân biệt được với key missing.

### Bài tập

1. Chạy ví dụ mục 10 và chứng minh note=null, note=missing, note=empty được in khác nhau.
2. Đổi total thành JSON number 0.10; giải thích vì sao validator từ chối dù về toán học là cùng số.
3. Viết phiên bản contract lưu amountMinor=10, currency=USD, scale=2; quy đổi ra 0.10 bằng BigDecimal.
4. Tạo JSON quantity="2" rồi sửa thành quantity=2; viết unit test để xác nhận sai kiểu bị reject.
5. Thử occurredAt thiếu Z, có offset +07:00, LocalDateTime thiếu timezone; ghi rõ trường hợp nào contract chấp nhận.
6. Tạo DTO có int quantity, deserialize missing và explicit null bằng Jackson config khác nhau; giải thích rủi ro.
7. Gửi MapMessage với quantity=0 rồi dùng itemExists/getInt để phân biệt field tồn tại với field không tồn tại.
8. Cấu hình MappingJackson2MessageConverter TEXT + PayloadType, gửi và nhận một DTO hợp lệ, sau đó thử thiếu type-id property.
9. Lập ma trận backward compatibility cho v1 không có customerNote và v2 có explicit null.
10. Giả lập poison message có total="invalid" trong một listener transacted, thiết kế giới hạn retry và quarantine an toàn.

## 16. Tài liệu tham khảo

- Jakarta Messaging 3.1 specification — Message bodies, MapMessage type conversions, properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging — MapMessage API: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/mapmessage
- Spring Framework 6.2 — Sending a Message / Using JMS Message Converters: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — MappingJackson2MessageConverter: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Jackson Databind JsonNode: https://fasterxml.github.io/jackson-databind/javadoc/2.17/com/fasterxml/jackson/databind/JsonNode.html
- Jackson JavaTimeModule: https://github.com/FasterXML/jackson-modules-java8
- Java 17 — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — Instant, OffsetDateTime, LocalDate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Spring Boot 3.3.13 release (demo version): https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
