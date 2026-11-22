# Kết hợp generator với serializer đối tượng

Jackson có hai cách tiếp cận bổ trợ nhau khi ghi JSON. `JsonGenerator` cho phép ghi từng token theo thứ tự, còn serializer của Jackson Databind chuyển object Java thành cấu trúc JSON theo kiểu dữ liệu, annotation, module và cấu hình đã đăng ký. Kết hợp hai cơ chế giúp ứng dụng tự kiểm soát phần khung JSON nhưng vẫn tái sử dụng khả năng serialize object của Jackson.

Ví dụ, một thông điệp có thể có phần metadata được ghi thủ công, trong khi payload là một DTO phức tạp:

```json
{
  "event": "user-created",
  "version": 1,
  "payload": {
    "id": 25,
    "name": "An"
  }
}
```

Chương trình có thể dùng `JsonGenerator` để ghi `event`, `version`, mở field `payload`, rồi yêu cầu Jackson serialize DTO `User` vào vị trí hiện tại. Cách làm này giữ được hiệu quả ghi tuần tự và tránh phải tự tạo chuỗi JSON hoặc dựng toàn bộ cây `JsonNode`.

## 1. Hai trách nhiệm: ghi token và serialize object

`JsonGenerator` thuộc Jackson Core. Nó ghi các token JSON như:

- Bắt đầu/kết thúc object: `writeStartObject()` và `writeEndObject()`.
- Bắt đầu/kết thúc array: `writeStartArray()` và `writeEndArray()`.
- Ghi tên field: `writeFieldName()`.
- Ghi giá trị scalar: `writeString()`, `writeNumber()`, `writeBoolean()`, `writeNull()`.

Serializer của Jackson Databind chịu trách nhiệm biến một kiểu Java thành các token tương ứng. Với POJO thông thường, Jackson có thể tự tạo serializer từ getter, field, annotation và cấu hình. Với kiểu đặc biệt, ứng dụng có thể đăng ký custom serializer.

Khi kết hợp hai phần:

1. Code ứng dụng hoặc custom serializer dùng generator để ghi phần cấu trúc cần kiểm soát.
2. Tại một field hoặc vị trí trong array, code yêu cầu Jackson serialize object con.
3. Serializer tương ứng tiếp tục ghi token vào cùng generator.
4. Generator tiếp tục ghi phần còn lại của JSON.

Toàn bộ quá trình ghi vào cùng một output target theo thứ tự, không cần tạo JSON trung gian cho từng object.

## 2. Tạo JsonGenerator gắn với ObjectMapper

Nếu cần gọi serializer của Databind từ generator, hãy tạo generator thông qua `ObjectMapper`:

```java
ObjectMapper mapper = new ObjectMapper();

try (JsonGenerator generator = mapper.createGenerator(writer)) {
    // Ghi token và object
}
```

Generator được tạo bởi mapper sẽ dùng mapper làm `ObjectCodec`. Codec là cầu nối để generator gọi cơ chế serialize của Databind khi gặp một object Java.

Một cách khác là tạo generator từ `JsonFactory` rồi gắn codec:

```java
JsonGenerator generator = mapper.getFactory().createGenerator(writer);
generator.setCodec(mapper);
```

Thông thường, `mapper.createGenerator(...)` rõ ràng và tiện hơn vì mapper tạo generator từ factory của chính nó và gắn cấu hình codec phù hợp.

### 2.1. Ghi một object Java bằng writeObject()

`JsonGenerator.writeObject(value)` yêu cầu codec serialize object tại vị trí hiện tại của generator. Ví dụ:

```java
StringWriter output = new StringWriter();

try (JsonGenerator generator = mapper.createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("event", "user-created");
    generator.writeNumberField("version", 1);

    generator.writeFieldName("payload");
    generator.writeObject(user);

    generator.writeEndObject();
}

String json = output.toString();
```

Sau `writeFieldName("payload")`, generator đang chờ giá trị của field `payload`. `writeObject(user)` ghi object `User` vào đúng vị trí đó. Jackson áp dụng serializer của `User`, bao gồm các quy tắc như `@JsonProperty`, `@JsonIgnore`, naming strategy, module và custom serializer đã đăng ký.

Output có dạng:

```json
{
  "event": "user-created",
  "version": 1,
  "payload": {
    "id": 25,
    "name": "An"
  }
}
```

Các dấu ngoặc, dấu phẩy và escape ký tự được generator xử lý. Không cần tự nối chuỗi cho object con.

### 2.2. Ghi object vào phần tử array

`writeObject()` cũng có thể ghi một object thành phần tử của array:

```java
try (JsonGenerator generator = mapper.createGenerator(output)) {
    generator.writeStartArray();
    generator.writeObject(user1);
    generator.writeObject(user2);
    generator.writeEndArray();
}
```

Mỗi lời gọi `writeObject()` ghi một giá trị JSON hoàn chỉnh. Nếu object là POJO, Jackson gọi serializer tương ứng; nếu object là kiểu scalar hoặc collection, Databind xử lý theo kiểu dữ liệu và cấu hình hiện hành.

### 2.3. Điều kiện để writeObject() hoạt động

`JsonGenerator` cần có `ObjectCodec` để serialize object Java tổng quát. Khi tạo generator từ `ObjectMapper`, codec đã được gắn. Nếu tự tạo generator từ một `JsonFactory` độc lập, hãy gắn mapper hoặc codec phù hợp bằng `setCodec()`.

Nếu generator không có codec, các thao tác ghi token cơ bản như `writeString()` hoặc `writeNumber()` vẫn hoạt động, nhưng generator không thể tự tìm serializer Databind cho một POJO bất kỳ. Trong trường hợp đó, `writeObject()` có thể thất bại hoặc không có hành vi serialize POJO như mong đợi.

## 3. Kết hợp token thủ công với object serializer

Một pattern hữu ích là ghi envelope bằng generator và ủy quyền phần payload cho Jackson.

Giả sử có DTO:

```java
public class User {
    private long id;
    private String name;

    public User() {
    }

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Code ghi envelope:

```java
static void writeEvent(
        ObjectMapper mapper,
        Writer output,
        String eventName,
        User user) throws IOException {

    try (JsonGenerator generator = mapper.createGenerator(output)) {
        generator.writeStartObject();
        generator.writeStringField("event", eventName);
        generator.writeNumberField("schemaVersion", 1);
        generator.writeFieldName("payload");
        generator.writeObject(user);
        generator.writeEndObject();
    }
}
```

Phần metadata có cấu trúc cố định được ghi trực tiếp. Payload vẫn được serialize theo model `User`, do đó không cần lặp lại logic ghi từng field của DTO.

### 3.1. Ghi nhiều payload khác kiểu

Nếu một envelope có thể chứa nhiều loại payload, generator có thể ghi metadata chung rồi serialize object theo runtime type:

```java
static void writeMessage(
        ObjectMapper mapper,
        JsonGenerator generator,
        String type,
        Object payload) throws IOException {

    generator.writeStartObject();
    generator.writeStringField("type", type);
    generator.writeFieldName("payload");
    generator.writeObject(payload);
    generator.writeEndObject();
}
```

Jackson chọn serializer theo kiểu runtime của `payload` và cấu hình polymorphism nếu có. Nếu hệ thống cần hợp đồng type discriminator rõ ràng, hãy ghi field `type` theo quy tắc của ứng dụng và cấu hình deserialization tương ứng. Việc ghi tên event thủ công không tự đăng ký subtype hoặc bật polymorphic deserialization.

### 3.2. Ghi giá trị null

Nếu object con có thể null:

```java
generator.writeFieldName("payload");
generator.writeObject(payload);
```

Jackson sẽ áp dụng serializer null theo cấu hình và ghi JSON `null` trong trường hợp thông thường. Nếu hợp đồng yêu cầu bỏ field khi null, code điều khiển envelope có thể kiểm tra trước:

```java
if (payload != null) {
    generator.writeFieldName("payload");
    generator.writeObject(payload);
}
```

Lưu ý, `@JsonInclude` trên một DTO điều khiển các property bên trong DTO đó. Nó không tự quyết định có ghi field envelope `payload` hay không nếu field này được ghi thủ công bởi generator. Quyết định đó thuộc code đang điều khiển envelope.

## 4. Ghi object trong custom JsonSerializer

Một custom serializer nhận `JsonGenerator` và `SerializerProvider`:

```java
public class AuditEventSerializer extends StdSerializer<AuditEvent> {
    public AuditEventSerializer() {
        super(AuditEvent.class);
    }

    @Override
    public void serialize(
            AuditEvent value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("eventType", value.getEventType());

        generator.writeFieldName("actor");
        provider.defaultSerializeValue(value.getActor(), generator);

        generator.writeFieldName("payload");
        provider.defaultSerializeValue(value.getPayload(), generator);

        generator.writeEndObject();
    }
}
```

Ở đây:

- `generator` ghi cấu trúc object và các field scalar.
- `provider` tìm serializer phù hợp cho object con.
- `defaultSerializeValue()` ghi giá trị bằng serializer mặc định hoặc custom serializer đã đăng ký cho kiểu runtime đó.

Ví dụ, nếu `actor` là `User`, Jackson dùng serializer của `User`. Nếu `payload` là một kiểu có custom serializer riêng, serializer đó được gọi mà không cần `AuditEventSerializer` biết chi tiết cấu trúc payload.

### 4.1. Dùng defaultSerializeField()

Khi muốn ghi cả tên field và giá trị object con, `SerializerProvider.defaultSerializeField()` giúp rút gọn:

```java
provider.defaultSerializeField("actor", value.getActor(), generator);
provider.defaultSerializeField("payload", value.getPayload(), generator);
```

Đoạn này tương đương với việc gọi `writeFieldName()` rồi `defaultSerializeValue()`. Nó cũng sử dụng cơ chế serializer/null serializer của provider.

Một serializer hoàn chỉnh có thể viết:

```java
public class AuditEventSerializer extends StdSerializer<AuditEvent> {
    public AuditEventSerializer() {
        super(AuditEvent.class);
    }

    @Override
    public void serialize(
            AuditEvent value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("eventType", value.getEventType());
        provider.defaultSerializeField("actor", value.getActor(), generator);
        provider.defaultSerializeField("payload", value.getPayload(), generator);
        generator.writeEndObject();
    }
}
```

### 4.2. Đăng ký custom serializer

Có thể đăng ký serializer thông qua `SimpleModule`:

```java
SimpleModule module = new SimpleModule("audit-module");
module.addSerializer(AuditEvent.class, new AuditEventSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Sau khi đăng ký, mọi thao tác serialize `AuditEvent` bằng mapper này sẽ dùng serializer đã đăng ký, bao gồm khi object được ghi qua `generator.writeObject(event)`.

Hãy đăng ký module và hoàn tất cấu hình mapper trước khi mapper được dùng đồng thời. Không đăng ký serializer trong mỗi request hoặc thay đổi mapper dùng chung sau khi hoạt động serialize đã bắt đầu.

## 5. SerializerProvider và việc ủy quyền serializer

`SerializerProvider` cung cấp ngữ cảnh serialize hiện tại: serializer đã được tìm, cấu hình, contextualization, xử lý null và các dịch vụ liên quan. Trong custom serializer, nên dùng provider để serialize object con thay vì tự tạo mapper mới.

Các phương thức thường dùng:

| Phương thức | Tác dụng |
|---|---|
| `defaultSerializeValue(value, generator)` | Ghi giá trị bằng serializer phù hợp, không kèm tên field. |
| `defaultSerializeField(name, value, generator)` | Ghi tên field và serialize giá trị tương ứng. |
| `findValueSerializer(type, property)` | Tìm serializer cho kiểu giá trị trong ngữ cảnh property. |
| `findTypedValueSerializer(type, cache, property)` | Tìm serializer có xử lý type information nếu cấu hình yêu cầu. |
| `defaultSerializeNull(generator)` | Ghi JSON null bằng null serializer mặc định. |

Trong phần lớn custom serializer, `defaultSerializeValue()` hoặc `defaultSerializeField()` là đủ. Chỉ tìm serializer thủ công khi cần cache hoặc điều khiển contextual/type serializer một cách cụ thể.

### 5.1. Vì sao không tạo ObjectMapper mới trong serializer?

Không nên làm như sau:

```java
@Override
public void serialize(
        AuditEvent value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    ObjectMapper mapper = new ObjectMapper();
    mapper.writeValue(generator, value.getPayload());
}
```

Mapper mới không nhất thiết có cùng module, naming strategy, mix-in, custom serializer hoặc cấu hình với mapper của ứng dụng. Nó còn tốn chi phí khởi tạo và có thể tạo recursion nếu serialize lại chính kiểu đang xử lý.

Hãy dùng `provider.defaultSerializeValue(value.getPayload(), generator)`. Cách này giữ payload trong cùng serialization context và tái sử dụng serializer đã được cấu hình.

### 5.2. Tránh gọi lại chính serializer gây recursion

Trong custom serializer của `AuditEvent`, đoạn sau là sai:

```java
provider.defaultSerializeValue(value, generator);
```

`value` vẫn là `AuditEvent`, nên provider tìm lại `AuditEventSerializer`, gọi `serialize()` lần nữa và tiếp tục lặp vô hạn.

Trong serializer của một kiểu, hãy ghi các field cần thiết hoặc ủy quyền cho serializer của các kiểu con. Nếu mục tiêu là mở rộng serializer bean mặc định của cùng kiểu, cần một thiết kế chuyên biệt như modifier/delegate serializer; không gọi trực tiếp lại serializer hiện tại thông qua provider.

## 6. Kết hợp serializer mặc định và custom serializer cho object con

Một custom serializer không cần tự biết mọi kiểu object có thể xuất hiện bên trong. Ví dụ, `Envelope` chứa `User`, `List<Order>` và một timestamp:

```java
public class Envelope {
    private String requestId;
    private Instant createdAt;
    private User user;
    private List<Order> orders;

    // Constructor, getter và setter
}
```

Serializer có thể tự ghi phần metadata và ủy quyền object con:

```java
public class EnvelopeSerializer extends StdSerializer<Envelope> {
    public EnvelopeSerializer() {
        super(Envelope.class);
    }

    @Override
    public void serialize(
            Envelope value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("requestId", value.getRequestId());

        provider.defaultSerializeField("createdAt", value.getCreatedAt(), generator);
        provider.defaultSerializeField("user", value.getUser(), generator);
        provider.defaultSerializeField("orders", value.getOrders(), generator);

        generator.writeEndObject();
    }
}
```

Nếu mapper đã đăng ký `JavaTimeModule`, `Instant` được serialize theo cấu hình Java Time. Nếu `User` hoặc `Order` có annotation hay custom serializer, các quy tắc đó vẫn được áp dụng. Serializer của envelope chỉ quyết định thứ tự và cấu trúc field cấp ngoài.

Đây là lợi ích lớn của việc ủy quyền: serializer tổng hợp không phải lặp lại logic của từng kiểu con.

## 7. Ghi collection và map bằng generator kết hợp serializer

Khi muốn kiểm soát container nhưng vẫn dùng serializer cho từng phần tử, có thể tự mở array rồi ghi object lần lượt:

```java
generator.writeArrayFieldStart("users");
for (User user : users) {
    generator.writeObject(user);
}
generator.writeEndArray();
```

Với map, cần ghi field name của từng entry rồi serialize value:

```java
generator.writeObjectFieldStart("usersById");
for (Map.Entry<String, User> entry : usersById.entrySet()) {
    generator.writeFieldName(entry.getKey());
    generator.writeObject(entry.getValue());
}
generator.writeEndObject();
```

Nếu không cần kiểm soát cấu trúc container, có thể đơn giản ủy quyền cả collection:

```java
generator.writeFieldName("users");
generator.writeObject(users);
```

Jackson sẽ serialize collection và từng phần tử theo serializer đã cấu hình. Tự mở array/map chỉ cần thiết khi muốn chèn metadata, lọc phần tử hoặc thay đổi thứ tự/định dạng cấu trúc.

## 8. Pretty printing và cấu hình generator

Generator có thể ghi JSON compact hoặc dễ đọc. Để dùng default pretty printer:

```java
try (JsonGenerator generator = mapper.createGenerator(writer)) {
    generator.useDefaultPrettyPrinter();
    generator.writeStartObject();
    generator.writeStringField("event", "user-created");
    generator.writeFieldName("payload");
    generator.writeObject(user);
    generator.writeEndObject();
}
```

Pretty printer định dạng cả token ghi thủ công lẫn token do serializer object phát ra, vì tất cả cùng đi qua một generator.

Có thể cấu hình các feature của generator trước khi bắt đầu ghi. Ví dụ, `StreamWriteFeature.AUTO_CLOSE_TARGET` điều khiển việc đóng output target khi generator đóng. Nếu target do caller quản lý và cần tiếp tục sử dụng sau khi đóng generator, hãy tắt auto-close phù hợp hoặc tổ chức vòng đời target ở scope bên ngoài.

Không thay đổi cấu hình generator giữa lúc đang ghi một cấu trúc JSON nếu điều đó có thể làm output không nhất quán. Cấu hình định dạng nên được thiết lập trước khi phát token đầu tiên.

## 9. Quản lý output và tài nguyên

`JsonGenerator` triển khai `Closeable`. Đóng generator sẽ hoàn tất cấu trúc được cấu hình auto-close, flush dữ liệu và giải phóng buffer nội bộ. Dùng `try-with-resources` để tránh rò rỉ tài nguyên:

```java
try (OutputStream output = Files.newOutputStream(path);
     JsonGenerator generator = mapper.createGenerator(output)) {

    generator.writeStartObject();
    generator.writeStringField("status", "ok");
    generator.writeEndObject();
}
```

Nếu generator được tạo trên một `Writer` hoặc `OutputStream` mà thành phần khác sở hữu, hãy xác định ai có trách nhiệm đóng target. `AUTO_CLOSE_TARGET` thường được bật mặc định; có thể tắt khi cần giữ target mở sau khi generator đóng.

Với output byte, nếu cần encoding cụ thể, tạo generator bằng overload phù hợp hoặc cung cấp `OutputStreamWriter` có charset rõ ràng. Ví dụ:

```java
try (Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8);
     JsonGenerator generator = mapper.createGenerator(writer)) {
    // Ghi JSON
}
```

Đừng đóng target trước khi generator hoàn tất. Nếu nhiều thành phần cùng ghi vào một stream, phải bảo đảm các thao tác tuần tự và cùng tuân theo một cấu trúc JSON hợp lệ.

## 10. So sánh các cách ghi object

| Cách | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| `generator.writeObject(value)` | Đang ghi token thủ công và muốn chèn một object | Generator phải có codec phù hợp |
| `provider.defaultSerializeValue(value, generator)` | Đang ở trong custom serializer và muốn serialize object con | Dùng serialization context hiện tại |
| `provider.defaultSerializeField(name, value, generator)` | Cần ghi field name và serialize giá trị con | Hữu ích trong custom serializer |
| `mapper.writeValue(output, value)` | Muốn serialize toàn bộ một giá trị ra output | Mapper điều khiển toàn bộ thao tác ghi |
| `mapper.writerFor(type).writeValue(generator, value)` | Cần writer có kiểu/cấu hình riêng | Phải hiểu vòng đời generator và writer |

Khi đang tự điều khiển cấu trúc bằng generator, `writeObject()` hoặc `SerializerProvider` thường tự nhiên nhất. Khi chỉ muốn ghi một object hoàn chỉnh, `ObjectMapper.writeValue()` đơn giản hơn.

## 11. Những lỗi thường gặp

### Generator không có codec

Token scalar vẫn có thể ghi bình thường, nhưng ghi POJO bằng `writeObject()` cần codec. Tạo generator bằng `mapper.createGenerator()` hoặc gắn mapper bằng `generator.setCodec(mapper)`.

### Ghi field name sai vị trí

`writeFieldName()` chỉ hợp lệ khi generator đang ở trong object và đang chờ một field. Trong array, ghi trực tiếp giá trị bằng `writeObject()` hoặc các phương thức scalar. Hãy theo dõi trạng thái cấu trúc bắt đầu/kết thúc để không tạo JSON sai.

### Tự serialize object con bằng chuỗi JSON

Không gọi `mapper.writeValueAsString(child)` rồi ghi chuỗi đó bằng `writeStringField()`. Cách đó tạo một JSON string chứa văn bản JSON, thay vì object lồng nhau. Dùng `writeObject(child)` hoặc `defaultSerializeField()` để ghi đúng kiểu JSON.

Ví dụ sai:

```java
generator.writeStringField("payload", mapper.writeValueAsString(user));
```

Output sẽ có dạng `"payload": "{\"id\":25,...}"`, tức payload là string.

Ví dụ đúng:

```java
generator.writeFieldName("payload");
generator.writeObject(user);
```

Output có dạng `"payload": {"id":25,...}`, tức payload là object.

### Tạo mapper mới bên trong custom serializer

Mapper mới có thể mất cấu hình/module và tạo recursion. Dùng `SerializerProvider` để ủy quyền object con.

### Gọi lại serializer của chính kiểu hiện tại

`provider.defaultSerializeValue(value, generator)` bên trong serializer của cùng kiểu có thể gọi lại chính serializer đó vô hạn. Hãy ghi các field hoặc ủy quyền cho kiểu con.

### Đóng generator quá sớm

Sau khi generator đóng, không thể tiếp tục ghi token vào nó. Chỉ đóng ở nơi sở hữu vòng đời output; nếu generator được truyền vào một helper, helper thường không nên tự đóng generator của caller.

### Áp dụng @JsonInclude cho field envelope được ghi thủ công

Annotation inclusion trên DTO con chỉ ảnh hưởng property bên trong DTO. Field envelope được ghi bằng generator cần được code điều khiển quyết định có xuất hay không.

## 12. Ví dụ hoàn chỉnh: serializer của envelope ủy quyền payload

Ví dụ dưới đây kết hợp module custom serializer, generator và serializer mặc định của DTO con:

```java
public class EventEnvelope {
    private final String event;
    private final Object payload;

    public EventEnvelope(String event, Object payload) {
        this.event = event;
        this.payload = payload;
    }

    public String getEvent() {
        return event;
    }

    public Object getPayload() {
        return payload;
    }
}

public class EventEnvelopeSerializer extends StdSerializer<EventEnvelope> {
    public EventEnvelopeSerializer() {
        super(EventEnvelope.class);
    }

    @Override
    public void serialize(
            EventEnvelope value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("event", value.getEvent());
        generator.writeNumberField("version", 1);

        if (value.getPayload() != null) {
            provider.defaultSerializeField("payload", value.getPayload(), generator);
        }

        generator.writeEndObject();
    }
}
```

Đăng ký serializer:

```java
SimpleModule eventModule = new SimpleModule("event-module");
eventModule.addSerializer(EventEnvelope.class, new EventEnvelopeSerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(eventModule);
```

Serialize envelope:

```java
EventEnvelope envelope = new EventEnvelope(
    "user-created",
    new User(25, "An")
);

StringWriter output = new StringWriter();
try (JsonGenerator generator = mapper.createGenerator(output)) {
    generator.writeObject(envelope);
}

System.out.println(output);
```

Ở đây, generator gọi `EventEnvelopeSerializer` thông qua mapper. Serializer ghi event và version bằng token thủ công, rồi dùng provider để serialize payload `User`. Kết quả có dạng:

```json
{
  "event": "user-created",
  "version": 1,
  "payload": {
    "id": 25,
    "name": "An"
  }
}
```

Nếu payload là một kiểu Java khác, provider sẽ tìm serializer tương ứng theo mapper đã đăng ký. Serializer envelope không cần biết cấu trúc chi tiết của mọi payload.

## 13. Nguyên tắc lựa chọn

- Dùng generator để kiểm soát cấu trúc JSON, thứ tự field, metadata hoặc xử lý tuần tự.
- Dùng `generator.writeObject()` khi đang ở ngoài custom serializer và generator đã gắn codec.
- Dùng `SerializerProvider.defaultSerializeValue()` hoặc `defaultSerializeField()` khi đang viết custom serializer và cần serialize object con.
- Đăng ký custom serializer bằng module trước khi mapper được chia sẻ.
- Không tự tạo `ObjectMapper` mới trong serializer; hãy giữ cùng serialization context.
- Không serialize object con thành String rồi ghi nó như một JSON string nếu mục tiêu là object/array lồng nhau.
- Theo dõi trạng thái object/array và chỉ ghi field name ở đúng vị trí.
- Xác định quyền sở hữu generator và output target, đóng tài nguyên ở đúng scope.

## Kết luận

`JsonGenerator` và serializer Databind có thể cùng ghi vào một output. Generator kiểm soát phần token và cấu trúc do ứng dụng định nghĩa; `writeObject()` hoặc `SerializerProvider` ủy quyền object con cho serializer phù hợp. Tạo generator từ `ObjectMapper` giúp giữ codec và cấu hình chung, còn custom serializer có thể dùng provider để tái sử dụng serializer mặc định hoặc serializer đã đăng ký cho các kiểu con. Cách kết hợp này tạo JSON tuần tự, rõ ràng và dễ mở rộng mà không phải tự dựng chuỗi hoặc lặp lại logic ánh xạ object.
