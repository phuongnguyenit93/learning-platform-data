# Đọc một vùng dữ liệu thành cây để xử lý cục bộ

Khi viết custom deserializer trong Jackson, đôi khi ứng dụng không cần xử lý toàn bộ JSON theo từng token. Thay vào đó, một property có cấu trúc linh hoạt hoặc thay đổi theo loại sự kiện, trong khi phần còn lại của DTO vẫn có schema cố định. Ta có thể đọc riêng giá trị của property đó thành một cây `JsonNode`, kiểm tra các trường cần thiết, rồi chuyển một phần node sang kiểu Java phù hợp.

Đây là cách kết hợp **Streaming API** với **Tree Model**: parser vẫn đọc document bên ngoài theo luồng và Databind vẫn xử lý các property khác như bình thường; custom deserializer chỉ materialize vùng JSON mà nó chịu trách nhiệm thành cây cục bộ.

Ví dụ một envelope có `eventId`, `receivedAt` và `payload`. Cấu trúc `payload` thay đổi theo `kind`, nên custom deserializer có thể đọc riêng payload thành `JsonNode`, xem `kind`, rồi chuyển `data` thành DTO tương ứng. Những field bên ngoài payload vẫn do Jackson bind trực tiếp vào `EventEnvelope`.

## 1. Vì sao cần đọc một vùng JSON thành cây?

Có hai cách tiếp cận phổ biến khi xử lý JSON:

- **Streaming API:** `JsonParser` đọc từng token. Cách này tiết kiệm bộ nhớ và kiểm soát chính xác thứ tự xử lý, nhưng code phải tự quản lý trạng thái object, array và field.
- **Tree Model:** `JsonNode` biểu diễn JSON thành cây object/array/value. Cách này dễ truy cập theo tên trường và kiểm tra cấu trúc, nhưng cần giữ vùng JSON đã đọc trong bộ nhớ.

Custom deserializer thường cần một điểm cân bằng. Ví dụ:

- Một property có schema động, nhưng các property còn lại có kiểu rõ ràng.
- Một trường `payload` có nhiều biến thể và cần xem discriminator trước khi chọn DTO.
- Chỉ cần đọc một phần object để kiểm tra hoặc chuẩn hóa dữ liệu.
- Muốn giữ lại một số field chưa biết trong dạng `JsonNode` để xử lý sau.
- Muốn dùng các API tiện lợi như `path()`, `get()`, `isObject()`, `isArray()` trên vùng dữ liệu đang deserialize.

Trong các trường hợp này, không nhất thiết phải đọc toàn bộ document gốc bằng `ObjectMapper.readTree()`. Custom deserializer có thể đọc đúng value hiện tại mà Jackson giao cho nó.

## 2. Parser đang đứng ở đâu khi custom deserializer được gọi?

Giả sử DTO bên ngoài:

```java
public class EventEnvelope {
    private String eventId;

    @JsonDeserialize(using = EventPayloadDeserializer.class)
    private EventPayload payload;

    private Instant receivedAt;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public EventPayload getPayload() {
        return payload;
    }

    public void setPayload(EventPayload payload) {
        this.payload = payload;
    }

    public Instant getReceivedAt() {
        return receivedAt;
    }

    public void setReceivedAt(Instant receivedAt) {
        this.receivedAt = receivedAt;
    }
}
```

Khi Databind đọc JSON và đến property `payload`, Jackson gọi `EventPayloadDeserializer.deserialize(...)`. Parser được đặt tại token đầu tiên của **giá trị payload**. Nếu payload là object, token hiện tại thường là `START_OBJECT`; nếu là array, token hiện tại là `START_ARRAY`; nếu là scalar, parser đứng ở token scalar tương ứng.

JSON đầu vào:

```json
{
  "eventId": "EVT-1001",
  "payload": {
    "kind": "invoice.paid",
    "data": {
      "invoiceId": "INV-9001",
      "amount": 1250.50
    },
    "trace": {
      "source": "billing",
      "attempt": 1
    }
  },
  "receivedAt": "2026-11-12T08:30:00Z"
}
```

Deserializer của `payload` chỉ nhận value tương ứng với object `payload`. Nó không nhận object `EventEnvelope` bên ngoài làm node hiện tại. Sau khi custom deserializer đọc xong payload, Jackson tiếp tục đọc các property còn lại của envelope theo luồng thông thường.

Đây là điểm mấu chốt của xử lý cục bộ: **vùng cây được tạo ra bắt đầu từ value mà deserializer đang phụ trách, không tự động bao gồm toàn bộ document gốc**.

## 3. Đọc value hiện tại thành JsonNode bằng ObjectCodec

Trong custom deserializer, cách phổ biến là lấy `ObjectCodec` từ parser rồi gọi `readTree()`:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;

public class EventPayloadDeserializer extends StdDeserializer<EventPayload> {
    public EventPayloadDeserializer() {
        super(EventPayload.class);
    }

    @Override
    public EventPayload deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        JsonNode payloadNode = parser.getCodec().readTree(parser);

        // Xử lý riêng cây payloadNode tại đây.
        return new EventPayload("unknown", payloadNode);
    }
}
```

`parser.getCodec()` thường là `ObjectMapper` hoặc một `ObjectCodec` tương thích do Jackson gắn với parser khi Databind gọi custom deserializer. `readTree(parser)` đọc một JSON value bắt đầu tại vị trí parser hiện tại và tạo node tương ứng.

Với payload object, kết quả thường là `ObjectNode`; với payload array là `ArrayNode`; với scalar là node giá trị; với JSON null, tree API biểu diễn bằng `NullNode` nếu lời gọi đọc tree được thực hiện cho token null.

Trong custom deserializer được gọi bởi `ObjectMapper`, codec thường đã có sẵn. Nếu deserializer cũng được gọi trong một môi trường tự tạo parser không gắn codec, hãy kiểm tra null và báo lỗi cấu hình rõ ràng thay vì giả định codec luôn tồn tại:

```java
ObjectCodec codec = parser.getCodec();
if (codec == null) {
    throw JsonMappingException.from(
            parser,
            "Parser cần ObjectCodec để đọc subtree thành JsonNode"
    );
}

JsonNode payloadNode = codec.readTree(parser);
```

## 4. readTree() tiêu thụ một value, không phải một token đơn lẻ

Một lỗi thường gặp là nghĩ `readTree()` chỉ đọc token hiện tại. Trên thực tế, nó đọc toàn bộ value JSON tại vị trí parser đang đứng:

- Nếu value là string, nó đọc string đó.
- Nếu value là number hoặc boolean, nó đọc scalar tương ứng.
- Nếu value là object, nó đọc object đến `END_OBJECT` tương ứng, bao gồm toàn bộ object con.
- Nếu value là array, nó đọc array đến `END_ARRAY` tương ứng, bao gồm toàn bộ phần tử lồng nhau.

Ví dụ parser đang đứng tại `START_OBJECT` của `payload`. Sau `codec.readTree(parser)`, parser đã tiêu thụ toàn bộ payload object và đứng ở token kết thúc của value đó. Jackson có thể tiếp tục với property tiếp theo của object envelope.

Không gọi thêm `parser.nextToken()` bên trong custom deserializer chỉ để “đóng” subtree sau khi `readTree()` đã hoàn tất. Việc di chuyển parser thêm có thể bỏ qua token tiếp theo mà Databind cần đọc.

Quy tắc cần nhớ: custom deserializer phải tiêu thụ đúng value mà nó chịu trách nhiệm và để parser ở vị trí mà contract của Databind mong đợi khi method trả về.

## 5. Kiểm tra cấu trúc cây trước khi đọc field

Sau khi có `JsonNode`, hãy kiểm tra node gốc và các trường quan trọng trước khi gọi phương thức lấy giá trị:

```java
if (payloadNode == null || !payloadNode.isObject()) {
    throw JsonMappingException.from(
            parser,
            "payload phải là JSON object"
    );
}

JsonNode kindNode = payloadNode.get("kind");
if (kindNode == null || !kindNode.isTextual()) {
    throw JsonMappingException.from(
            parser,
            "payload.kind phải là chuỗi"
    );
}

String kind = kindNode.textValue();
```

Việc kiểm tra `isObject()` ngăn code giả định payload luôn là object. `get("kind")` trả Java `null` nếu field không tồn tại; nếu field tồn tại với JSON null, kết quả là `NullNode`, do đó `isTextual()` vẫn trả false.

Có thể dùng `path()` để tránh Java null khi truy cập nhiều tầng:

```java
JsonNode invoiceIdNode = payloadNode.path("data").path("invoiceId");
if (!invoiceIdNode.isTextual()) {
    throw JsonMappingException.from(parser, "data.invoiceId phải là chuỗi");
}
```

`path()` trả `MissingNode` khi field không tồn tại. Hãy phân biệt `MissingNode` và `NullNode` nếu hợp đồng cần phân biệt trường bị thiếu với trường được gửi rõ ràng là null.

## 6. Ví dụ: đọc discriminator rồi chuyển data thành DTO tương ứng

Giả sử payload có hai loại sự kiện:

```json
{
  "kind": "invoice.paid",
  "data": {
    "invoiceId": "INV-9001",
    "amount": 1250.50
  }
}
```

hoặc:

```json
{
  "kind": "user.created",
  "data": {
    "userId": "USR-42",
    "email": "an@example.com"
  }
}
```

Khai báo các kiểu dữ liệu:

```java
import java.math.BigDecimal;

public record InvoicePaidData(String invoiceId, BigDecimal amount) {
}

public record UserCreatedData(String userId, String email) {
}

public record EventPayload(String kind, Object data) {
}
```

Custom deserializer:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectCodec;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;

public class EventPayloadDeserializer extends StdDeserializer<EventPayload> {
    public EventPayloadDeserializer() {
        super(EventPayload.class);
    }

    @Override
    public EventPayload deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        ObjectCodec codec = parser.getCodec();
        if (codec == null) {
            throw JsonMappingException.from(parser, "Không có ObjectCodec trên parser");
        }

        JsonNode root = codec.readTree(parser);
        if (!root.isObject()) {
            throw JsonMappingException.from(parser, "payload phải là object");
        }

        JsonNode kindNode = root.get("kind");
        if (kindNode == null || !kindNode.isTextual()) {
            throw JsonMappingException.from(parser, "payload.kind phải là chuỗi");
        }

        JsonNode dataNode = root.get("data");
        if (dataNode == null || dataNode.isNull() || !dataNode.isObject()) {
            throw JsonMappingException.from(parser, "payload.data phải là object");
        }

        String kind = kindNode.textValue();
        Object data = switch (kind) {
            case "invoice.paid" -> codec.treeToValue(dataNode, InvoicePaidData.class);
            case "user.created" -> codec.treeToValue(dataNode, UserCreatedData.class);
            default -> throw JsonMappingException.from(
                    parser,
                    "Không hỗ trợ payload kind: " + kind
            );
        };

        return new EventPayload(kind, data);
    }
}
```

Đoạn code dùng switch expression của Java 14+ (hoặc Java 17 trở lên với cú pháp phổ biến hiện nay). Nếu dự án dùng Java 8/11, có thể thay bằng switch statement và gán `data` trong từng nhánh.

Luồng xử lý:

1. Đọc đúng value `payload` thành `JsonNode root`.
2. Xác nhận payload là object.
3. Đọc `kind` và kiểm tra đó là string.
4. Lấy node con `data` và kiểm tra cấu trúc.
5. Dựa vào discriminator để chọn class Java.
6. Gọi `codec.treeToValue(dataNode, SomeDto.class)` để chuyển riêng node `data` thành DTO.
7. Trả về `EventPayload` cho Databind gán vào property của envelope.

Nhờ vậy, `payload` có thể linh hoạt theo `kind`, còn `eventId` và `receivedAt` vẫn được Jackson deserialize theo kiểu đã khai báo trong `EventEnvelope`.

## 7. treeToValue() chuyển một node con thành kiểu Java

Sau khi đã có `JsonNode`, bạn không cần serialize node thành chuỗi JSON rồi gọi `readValue()` lần nữa. `ObjectCodec.treeToValue()` có thể chuyển trực tiếp node thành kiểu Java:

```java
InvoicePaidData data = codec.treeToValue(dataNode, InvoicePaidData.class);
```

Điều này tránh tạo thêm một chuỗi JSON trung gian. Jackson vẫn dùng cơ chế Databind để ánh xạ property của node vào DTO, bao gồm module, annotation và cấu hình phù hợp của codec.

Một cách khác là mở parser trên node:

```java
try (JsonParser subtreeParser = dataNode.traverse(codec)) {
    InvoicePaidData data = context.readValue(subtreeParser, InvoicePaidData.class);
}
```

Với cách này, `traverse(codec)` tạo parser đọc từ cây node và `DeserializationContext.readValue()` bind node thành kiểu đích. Khi dùng parser riêng, hãy quản lý vòng đời bằng try-with-resources.

Thông thường `treeToValue()` ngắn gọn và dễ hiểu hơn khi chỉ cần chuyển một node. Dùng `traverse()` khi cần làm việc với API parser hoặc muốn xử lý theo token trên chính subtree đó.

## 8. Giữ lại vùng dữ liệu động dưới dạng JsonNode

Không phải lúc nào cũng cần chuyển node con thành DTO. Nếu ứng dụng cần lưu hoặc chuyển tiếp dữ liệu mở rộng, có thể giữ node dưới dạng `JsonNode`:

```java
public record EventPayload(String kind, JsonNode data) {
}
```

Trong custom deserializer, sau khi xác thực `kind` và `data`, trả trực tiếp node:

```java
return new EventPayload(kind, dataNode.deepCopy());
```

`deepCopy()` hữu ích khi ứng dụng muốn giữ một bản sao độc lập có thể thay đổi mà không phụ thuộc vào node gốc có thể còn được dùng ở nơi khác. Nếu chỉ đọc và giữ nguyên node, việc copy có thể không cần thiết.

Giữ `JsonNode` phù hợp khi:

- Payload có nhiều trường không biết trước.
- Gateway cần chuyển tiếp phần dữ liệu mà không hiểu hết schema.
- Ứng dụng chỉ đọc vài trường nhưng vẫn cần lưu phần còn lại.
- Các phiên bản event có thêm field mà consumer cũ chưa sử dụng.

Đổi lại, code nghiệp vụ phải tự kiểm tra kiểu node khi truy cập. Nếu schema đã ổn định, DTO có kiểu cụ thể thường an toàn và dễ bảo trì hơn.

## 9. Dùng node để lấy một phần và bỏ qua phần còn lại

Một subtree có thể chứa nhiều field nhưng custom deserializer chỉ cần một số trường. Ví dụ:

```json
{
  "kind": "invoice.paid",
  "data": {
    "invoiceId": "INV-9001",
    "amount": 1250.50,
    "currency": "VND",
    "debug": {
      "source": "billing",
      "traceId": "abc-123"
    }
  }
}
```

Nếu chỉ cần `invoiceId` và `amount`, có thể đọc trực tiếp:

```java
JsonNode data = root.path("data");

String invoiceId = data.path("invoiceId").asText();
BigDecimal amount = data.path("amount").decimalValue();
```

`currency` và `debug` vẫn tồn tại trong cây nhưng không cần xử lý. Nếu cần kiểm tra nghiêm ngặt, không nên dùng `asText()` hoặc `decimalValue()` trước khi xác nhận node có kiểu mong đợi:

```java
JsonNode amountNode = data.get("amount");
if (amountNode == null || !amountNode.isNumber()) {
    throw JsonMappingException.from(parser, "data.amount phải là JSON number");
}
BigDecimal amount = amountNode.decimalValue();
```

Nếu cần giữ các field chưa biết, có thể lưu toàn bộ `data` node. Nếu cần từ chối field ngoài schema, hãy liệt kê tên được phép và kiểm tra `fieldNames()`/`fields()` trước khi trả kết quả.

## 10. Phân biệt field thiếu, null và giá trị rỗng

Tree Model giúp phân biệt rõ các trạng thái đầu vào:

```json
{}
```

Không có field `data`.

```json
{"data": null}
```

Field có mặt nhưng là JSON null.

```json
{"data": {}}
```

Field có mặt và là object rỗng.

```json
{"data": ""}
```

Field có mặt và là string rỗng.

Trong code:

```java
JsonNode data = root.get("data");

if (data == null) {
    // Field bị thiếu.
} else if (data.isNull()) {
    // Field có JSON null.
} else if (data.isObject() && data.isEmpty()) {
    // Object rỗng.
} else if (data.isTextual() && data.textValue().isEmpty()) {
    // Chuỗi rỗng.
}
```

Đừng gộp các trạng thái này nếu chúng có ý nghĩa nghiệp vụ khác nhau. Ví dụ, `data` thiếu có thể là lỗi hợp đồng, `null` có thể có nghĩa không có payload, object rỗng có thể là payload hợp lệ nhưng không có thuộc tính, còn string rỗng có thể là sai kiểu.

## 11. Null ở cấp property và getNullValue()

Một chi tiết quan trọng: Jackson thường xử lý JSON null cho property trước khi gọi `deserialize()` của custom deserializer. Do đó, nếu input là:

```json
{
  "payload": null
}
```

thì `EventPayloadDeserializer.deserialize()` có thể không được gọi; Jackson dùng null handling của deserializer/property. Nếu cần quy định riêng giá trị Java khi JSON null, có thể override `getNullValue()`:

```java
@Override
public EventPayload getNullValue(DeserializationContext context) {
    return null;
}
```

Ví dụ trên vẫn trả null, tương đương hành vi thường gặp, nhưng cho thấy điểm mở rộng. Có thể trả một sentinel hoặc object mặc định nếu hợp đồng cho phép, song cần cân nhắc sự khác nhau giữa JSON null và property bị thiếu.

Nếu muốn JSON null bị từ chối, có thể cấu hình null handling ở property bằng `@JsonSetter(nulls = Nulls.FAIL)` hoặc dùng cơ chế phù hợp với mô hình. Không nên chỉ kiểm tra `root.isNull()` trong `deserialize()` rồi cho rằng mọi trường hợp null đều đi qua method đó.

## 12. Chỉ đọc subtree, không đọc lại toàn bộ document

Trong custom deserializer, không nên làm như sau:

```java
JsonNode wholeDocument = mapper.readTree(parser);
```

với ý định lấy toàn bộ document gốc khi parser thực tế đang ở giữa một property. `readTree(parser)` chỉ đọc value bắt đầu tại vị trí parser hiện tại. Nếu parser đang ở `payload`, kết quả là cây payload; các field như `eventId` hoặc `receivedAt` ở object cha không nằm trong cây đó.

Điều này là chủ đích và giúp giới hạn phạm vi xử lý. Nếu custom deserializer cần dữ liệu từ property anh em hoặc từ object cha, hãy xem xét thiết kế DTO khác, dùng contextual deserializer hoặc chuyển trách nhiệm xử lý lên cấp DTO cha. Không nên cố đọc ngược token đã được Databind tiêu thụ.

## 13. Lợi ích và chi phí bộ nhớ của subtree

Đọc một vùng thành cây giúp code dễ hiểu và dễ truy cập, nhưng không phải zero-copy hoặc lazy parsing. Jackson phải tạo các node cho toàn bộ value được đọc.

Giả sử document có kích thước 20 MB, nhưng property `payload` chỉ chiếm 200 KB. Custom deserializer đọc riêng `payload` thành cây có thể giới hạn vùng cần materialize vào khoảng payload đó, trong khi phần envelope được Databind xử lý theo luồng. Tuy nhiên, nếu chính payload chứa một mảng lớn 200 MB, cây cục bộ vẫn có thể tiêu tốn bộ nhớ lớn.

Các chi phí cần cân nhắc:

- Mỗi object/array/value trong subtree tạo node tương ứng.
- Cây giữ các string, number và cấu trúc lồng nhau trong bộ nhớ.
- `deepCopy()` có thể nhân đôi lượng dữ liệu node.
- `treeToValue()` tạo thêm object graph DTO từ node, nên có thể tạm thời tồn tại đồng thời cây và DTO.
- Nếu chuyển node thành chuỗi JSON rồi parse lại, sẽ phát sinh thêm chi phí cấp phát và xử lý không cần thiết.

Nếu subtree lớn hoặc chỉ cần một vài trường, streaming trực tiếp trên parser có thể phù hợp hơn. Nếu cần truy cập nhiều lần vào nhiều nhánh của một vùng nhỏ/vừa, Tree Model thường đơn giản hơn.

## 14. So sánh đọc subtree thành cây với xử lý token trực tiếp

| Tiêu chí | Đọc subtree thành JsonNode | Đọc token trực tiếp |
| --- | --- | --- |
| Cách truy cập | Theo tên field và index | Theo thứ tự token hiện tại |
| Code cho schema linh hoạt | Thường ngắn và dễ đọc | Cần quản lý trạng thái parser |
| Bộ nhớ | Giữ toàn bộ subtree | Có thể xử lý từng token và bỏ dữ liệu đã đọc |
| Truy cập lặp lại | Dễ vì node còn trong cây | Khó hơn; thường phải buffer hoặc đọc lại nguồn |
| Xử lý payload lớn | Có thể tốn nhiều bộ nhớ | Phù hợp hơn nếu xử lý tuần tự |
| Chuyển node con thành DTO | Dùng `treeToValue()` | Bind trực tiếp từ parser hoặc parser con |
| Phù hợp | Property nhỏ/vừa, cần kiểm tra nhiều trường | Payload lớn, chỉ cần đọc một lượt hoặc cần tối ưu bộ nhớ |

Không có lựa chọn nào luôn tốt hơn. Chọn theo kích thước subtree, mức độ linh hoạt của schema và số lần ứng dụng cần truy cập dữ liệu.

## 15. Giữ custom deserializer an toàn và dễ kiểm thử

Custom deserializer nằm ở ranh giới dữ liệu bên ngoài, vì vậy nên kiểm tra cấu trúc và báo lỗi rõ ràng:

- Kiểm tra root node đúng kiểu mong đợi.
- Kiểm tra discriminator tồn tại, là string và thuộc danh sách được hỗ trợ.
- Kiểm tra các field bắt buộc và kiểu dữ liệu của chúng.
- Giới hạn kích thước request/subtree ở tầng parser hoặc HTTP server.
- Không tự động chấp nhận mọi cấu trúc chỉ vì `JsonNode` có thể biểu diễn chúng.
- Giữ nguyên `JsonMappingException` hoặc tạo lỗi mapping có thông điệp đủ rõ để xác định property lỗi.
- Không gọi lại chính deserializer cho cùng kiểu trên cùng dữ liệu, vì có thể tạo đệ quy vô hạn.

Nên có test cho các trường hợp: payload hợp lệ của từng kind, thiếu `kind`, `kind` sai kiểu, kind không hỗ trợ, thiếu `data`, `data` null, `data` sai kiểu và field bổ sung. Đây là các ranh giới mà custom deserializer cần định nghĩa hành vi rõ ràng.

## 16. Tránh gọi lại chính custom deserializer

Một lỗi nguy hiểm là trong `EventPayloadDeserializer`, gọi `context.readValue(parser, EventPayload.class)` để nhờ Jackson đọc tiếp cùng kiểu `EventPayload`. Vì kiểu này đang được gắn chính custom deserializer, Jackson có thể gọi lại nó, tạo vòng đệ quy.

Nếu cần chuyển một phần subtree sang kiểu khác, hãy gọi:

```java
InvoicePaidData data = codec.treeToValue(dataNode, InvoicePaidData.class);
```

Kiểu đích `InvoicePaidData` có deserializer riêng hoặc cơ chế binding mặc định, nên không gọi lại `EventPayloadDeserializer` trừ khi cấu hình của nó có quan hệ đặc biệt.

Nếu cần deserialize phần dữ liệu thành cùng một kiểu nhưng với cấu hình khác, hãy thiết kế kiểu wire model riêng, dùng `ObjectReader` có cấu hình phù hợp hoặc tạo một đường xử lý tách biệt. Tránh tái nhập cùng custom deserializer mà không có điều kiện dừng rõ ràng.

## 17. Một custom deserializer hoàn chỉnh gắn với property

Khai báo DTO envelope:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.time.Instant;

public class EventEnvelope {
    private String eventId;

    @JsonDeserialize(using = EventPayloadDeserializer.class)
    private EventPayload payload;

    private Instant receivedAt;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public EventPayload getPayload() {
        return payload;
    }

    public void setPayload(EventPayload payload) {
        this.payload = payload;
    }

    public Instant getReceivedAt() {
        return receivedAt;
    }

    public void setReceivedAt(Instant receivedAt) {
        this.receivedAt = receivedAt;
    }
}
```

Đăng ký module Java Time nếu ứng dụng dùng `Instant`:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
```

Sau đó đọc toàn bộ envelope:

```java
EventEnvelope envelope = mapper.readValue(json, EventEnvelope.class);

System.out.println(envelope.getEventId());
System.out.println(envelope.getPayload().kind());
System.out.println(envelope.getPayload().data().getClass());
```

Jackson xử lý `eventId` và `receivedAt` bằng cơ chế binding thông thường. Khi đến `payload`, custom deserializer đọc riêng subtree, kiểm tra `kind`, chuyển `data` thành DTO tương ứng và trả object `EventPayload`.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Cây chỉ chứa một phần nhỏ hơn mong đợi | Parser đang đứng ở property value, không phải root document | Xác định đúng phạm vi của custom deserializer |
| Property kế tiếp của DTO cha bị bỏ qua | Custom deserializer gọi `nextToken()` dư sau `readTree()` | Để Databind tiếp tục sau khi đã tiêu thụ đúng subtree |
| `NullPointerException` khi gọi `readTree()` | Parser không có codec trong cách tạo parser thủ công | Kiểm tra `getCodec()` hoặc dùng codec được cấu hình |
| Không phân biệt được field thiếu và null | Chỉ dùng `asText()`/`asInt()` mà không kiểm tra node | Dùng `get()`, `isNull()` và `isMissingNode()` phù hợp |
| Bộ nhớ tăng mạnh | Subtree quá lớn hoặc vừa giữ cây vừa tạo DTO/copy | Dùng streaming trực tiếp hoặc giới hạn kích thước |
| Custom deserializer đệ quy vô hạn | Gọi lại cùng kiểu đang được custom deserializer xử lý | Chuyển node con sang kiểu khác hoặc dùng wire model riêng |
| JSON null không đi qua `deserialize()` | Jackson xử lý null bằng null provider | Override `getNullValue()` hoặc cấu hình null handling |

## 19. Khi nào nên đọc subtree thành cây?

Nên dùng cách này khi vùng dữ liệu cần xử lý có kích thước vừa phải, cấu trúc không hoàn toàn cố định và ứng dụng cần truy cập nhiều trường theo tên. Nó cũng phù hợp khi cần chọn kiểu DTO theo discriminator hoặc giữ lại dữ liệu mở rộng dưới dạng `JsonNode`.

Hãy ưu tiên streaming trực tiếp nếu subtree rất lớn, chỉ cần đọc một lượt hoặc cần kiểm soát chặt lượng bộ nhớ. Nếu toàn bộ payload có schema ổn định, dùng Databind vào DTO thông thường sẽ đơn giản hơn việc viết custom deserializer.

## 20. Ghi nhớ

- Trong custom deserializer, parser được đặt tại value mà deserializer chịu trách nhiệm, thường là property hiện tại chứ không phải toàn bộ document cha.
- `parser.getCodec().readTree(parser)` đọc value hiện tại thành một `JsonNode` subtree.
- `readTree()` tiêu thụ toàn bộ value object/array lồng nhau; không gọi `nextToken()` dư sau đó.
- Dùng `isObject()`, `isArray()`, `isTextual()` và `isNumber()` để kiểm tra kiểu node trước khi lấy dữ liệu.
- Dùng `get()` hoặc `path()` để truy cập field; phân biệt field thiếu (`MissingNode`/Java null) với JSON null (`NullNode`).
- `codec.treeToValue(node, Type.class)` chuyển node con thành DTO mà không cần tạo chuỗi JSON trung gian.
- Có thể giữ `JsonNode` nếu payload động cần được chuyển tiếp hoặc xử lý sau.
- Đọc subtree thành cây vẫn materialize toàn bộ vùng đó trong bộ nhớ; với payload lớn, streaming trực tiếp thường phù hợp hơn.
- Custom deserializer cần định nghĩa rõ hành vi cho null, field thiếu, discriminator không hỗ trợ và dữ liệu sai kiểu.

Khi cần xử lý một property JSON linh hoạt, hãy để Jackson đọc document cha theo cơ chế Databind, rồi dùng custom deserializer để đọc riêng value của property đó thành `JsonNode`. Cách kết hợp này giữ phần DTO ổn định ở dạng có kiểu, đồng thời cho phép kiểm tra, chọn kiểu và chuyển đổi cục bộ đối với vùng dữ liệu có cấu trúc động.
