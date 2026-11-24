# Chuyển đổi JSON thất bại hoặc nhận Map thay vì POJO

## 1. Tình huống: cùng JSON nhưng function nhận sai kiểu

Bạn tạo một bean **Spring Cloud Function** để xử lý đơn hàng:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

Dữ liệu đến từ HTTP hoặc message broker:

~~~json
{
  "orderId": "ORD-101",
  "amountCents": 150000
}
~~~

Mong đợi: framework chuyển JSON thành `OrderEvent`, rồi hàm nhận một Java object có thể gọi `event.orderId()`.

Nhưng ứng dụng có thể gặp một trong hai hiện tượng:

- **Chuyển đổi thất bại:** log xuất hiện `MessageConversionException`, `JsonProcessingException`, `MismatchedInputException`, `InvalidFormatException`, `ClassCastException` hoặc một HTTP 4xx/5xx do lỗi payload.
- **Không có exception ngay nhưng sai kiểu:** debug cho thấy input là `java.util.LinkedHashMap`, `Map<String,Object>`, `String` hoặc `byte[]` thay vì `OrderEvent`. Lỗi chỉ lộ ra khi code ép kiểu, truy cập thuộc tính hoặc thực hiện logic.

Trong Spring Cloud Function, cùng một `Supplier`, `Function` hoặc `Consumer` có thể được gọi qua `FunctionCatalog`, ghép bằng composition và chạy sau HTTP adapter, Spring Cloud Stream hoặc serverless runtime. Vì vậy JSON đi qua **nhiều ranh giới** trước khi trở thành input của hàm.

**Câu hỏi quan trọng nhất không phải “Jackson có lỗi không?” mà là:**

> **Ở ranh giới nào, framework biết kiểu Java đích là `OrderEvent`, payload đang có kiểu gì và ai thực hiện bước chuyển đổi?**

Chủ đề của bài trong chương **Chẩn đoán** là **“Chuyển đổi JSON thất bại hoặc nhận Map thay vì POJO”**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **chuỗi JSON**, **byte JSON**, **Java Map** và **POJO đã được deserialize**.
2. Hiểu vai trò của `FunctionCatalog`, kiểu generic, `MessageConverter`, `ConversionService` và `contentType`.
3. Xác định lỗi do JSON không hợp lệ, DTO không deserialize được, header sai, mất metadata kiểu hoặc adapter dùng native decoding.
4. Sửa chữ ký `Function<I,O>`, `Function<Message<I>,O>` và `Function<Flux<I>,Flux<O>>` theo hợp đồng dữ liệu thật.
5. Kiểm tra nội dung ở các tầng Spring Cloud Function, HTTP, Spring Cloud Stream, serverless và composition.
6. Biết khi nào dùng `ObjectMapper.convertValue(...)` và khi nào phải `readValue(...)`.
7. Viết kiểm thử Jackson, FunctionCatalog, HTTP và message binding để tái hiện lỗi đúng nơi.
8. Không dùng deserialize động hoặc cấu hình type từ dữ liệu không tin cậy một cách thiếu kiểm soát.

## 2. Bốn hình thái cùng một dữ liệu

Một sự kiện có thể trải qua nhiều dạng:

~~~mermaid
flowchart LR
    W["Wire bytes"] --> S["JSON String"]
    S --> M["Map / LinkedHashMap"]
    S --> P["OrderEvent POJO"]
    W --> P
    M --> P
    P --> B["Business Function"]
~~~

Không phải mọi đường chuyển đổi đều xảy ra tự động. Với JSON:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

bốn giá trị sau khác nhau:

~~~java
byte[] rawBytes = json.getBytes(StandardCharsets.UTF_8);

String rawString = json;

Map<String, Object> asMap = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

OrderEvent pojo = new OrderEvent("ORD-101", 150000L);
~~~

| Hình thái | Kiểu Java quan sát được | Ý nghĩa |
| --- | --- | --- |
| Wire JSON | `byte[]` | Nội dung chưa được Java deserialize |
| JSON text | `String` | Văn bản chứa ký tự JSON, **không phải** `OrderEvent` |
| Generic JSON object | `LinkedHashMap<String,Object>` | Các field đã được phân tích nhưng chưa có class domain cụ thể |
| Domain object | `OrderEvent` | Đã được gán kiểu để business logic dùng trực tiếp |

**`Map` không nhất thiết là lỗi của Jackson.** Nếu framework chỉ được yêu cầu deserialize vào `Object` hoặc `Map`, một `LinkedHashMap` là kết quả hợp lý. Lỗi nằm ở **hợp đồng kiểu đích** nếu business logic yêu cầu `OrderEvent`.

### 2.1. Một lỗi dễ gây nhầm

~~~java
Object value = objectMapper.readValue(json, Object.class);

// Với JSON object thông thường,
// giá trị có thể là LinkedHashMap, không phải OrderEvent.
OrderEvent event = (OrderEvent) value; // Có thể ClassCastException.
~~~

Đọc vào `Object.class` không yêu cầu Jackson tạo `OrderEvent`. Để tạo POJO, cần cung cấp target type:

~~~java
OrderEvent event =
    objectMapper.readValue(json, OrderEvent.class);
~~~

Việc converter trong Spring Cloud Function lấy target type từ đâu là chìa khóa của toàn bài.

## 3. Sơ đồ chẩn đoán từ transport đến function

~~~mermaid
flowchart TD
    INPUT["HTTP body / broker record / serverless event"] --> ADAPTER["Adapter tạo input/message"]
    ADAPTER --> WIRE{"Payload hiện có kiểu gì?"}
    WIRE --> META["contentType + generic target type"]
    META --> CONVERT["MessageConverter hoặc ConversionService"]
    CONVERT --> RESULT{"Kiểu kết quả?"}
    RESULT -->|OrderEvent| BIZ["Business Function.apply"]
    RESULT -->|Map / String / bytes| WRONG["Sai type hoặc thiếu conversion"]
    CONVERT -->|Exception| ERR["Lỗi JSON/schema/converter"]
    BIZ --> OUTPUT["Output serialize / send"]
~~~

Hãy xác định *lỗi đầu tiên* và *bước cuối cùng đã thành công*. Không đổi đồng thời DTO, serializer Kafka, header và function definition khi chưa biết dữ liệu bị sai kiểu ở đâu.

### 3.1. Hai cơ chế chuyển đổi Spring Cloud Function sử dụng

Theo tài liệu Spring Cloud Function:

- **`MessageConverter`** được dùng cho dữ liệu kiểu `Message<?>`, phổ biến khi adapter HTTP hoặc messaging tạo Spring Message chứa payload và headers.
- **`ConversionService`** được dùng cho input **không phải Message** cần đổi kiểu trước khi function xử lý.

Thông thường adapter cung cấp **kiểu đích** qua chữ ký function và **gợi ý định dạng** qua header `contentType`. Function được lấy từ `FunctionCatalog` có thể là wrapper có khả năng conversion và composition; bean gốc lấy trực tiếp từ `ApplicationContext` không mặc định có lớp chuyển đổi này.

### 3.2. Hai nguồn thông tin phải đi cùng nhau

| Thành phần | Ví dụ | Nó nói gì? |
| --- | --- | --- |
| Generic target | `Function<OrderEvent,OrderReceipt>` | Input cần thành `OrderEvent` |
| Message content type | `application/json` | Bytes/String có cấu trúc JSON |
| Content type khác | `text/plain` | Có thể xử lý như chuỗi |
| Content type khác | `application/octet-stream` | Có thể xử lý như bytes |
| Chữ ký tổng quát | `Function<Object,Object>` | Không xác định domain class cụ thể |
| Native binder decoding | Kafka deserializer trả `Map` | Payload đã được client/binder tạo thành `Map` trước tầng conversion của SCF |

**Không có quy tắc “cứ thấy `application/json` thì chắc chắn thành POJO”.** Target type cũng phải được nhận biết và converter phải được gọi đúng ranh giới.

## 4. Định nghĩa DTO để loại trừ lỗi từ Jackson

Bài dùng Java 17+ với `record` để giữ ví dụ đơn giản.

~~~java
package demo.diagnostics.json;

public record OrderEvent(
    String orderId,
    long amountCents
) {}
~~~

~~~java
package demo.diagnostics.json;

public record OrderReceipt(
    String orderId,
    String status
) {}
~~~

Một JSON hợp lệ:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

Test Jackson trước khi kiểm tra broker hoặc FunctionCatalog:

~~~java
ObjectMapper mapper = new ObjectMapper();

OrderEvent event = mapper.readValue(
    "{\"orderId\":\"ORD-101\",\"amountCents\":150000}",
    OrderEvent.class
);

assertEquals("ORD-101", event.orderId());
assertEquals(150000L, event.amountCents());
~~~

Nếu **test Jackson thuần này đã lỗi**, đừng bắt đầu bằng việc đổi `spring.cloud.function.definition` hoặc topic broker. Bạn có thể đang có JSON hỏng, kiểu dữ liệu sai, class thiếu constructor hoặc cấu hình Jackson không phù hợp.

### 4.1. Vấn đề thường gặp ở DTO dạng class

Một POJO class thông thường nên có cách tạo instance mà Jackson có thể sử dụng và thuộc tính có thể được bind theo cấu hình.

~~~java
public class OrderEventBean {

    private String orderId;
    private long amountCents;

    public OrderEventBean() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public long getAmountCents() {
        return amountCents;
    }

    public void setAmountCents(long amountCents) {
        this.amountCents = amountCents;
    }
}
~~~

Với immutable class không có no-arg constructor, có thể khai báo constructor cho Jackson:

~~~java
public final class ImmutableOrderEvent {

    private final String orderId;
    private final long amountCents;

    @JsonCreator
    public ImmutableOrderEvent(
            @JsonProperty("orderId") String orderId,
            @JsonProperty("amountCents") long amountCents) {
        this.orderId = orderId;
        this.amountCents = amountCents;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getAmountCents() {
        return amountCents;
    }
}
~~~

Ví dụ giả định có import `com.fasterxml.jackson.annotation.JsonCreator` và `JsonProperty`.

### 4.2. DTO có tên field khác JSON

Giả sử đối tác gửi:

~~~json
{"order_id":"ORD-101","amount_cents":150000}
~~~

Nếu DTO yêu cầu `orderId` và `amountCents`, field có thể không được bind đúng.

Một cách sửa rõ ràng:

~~~java
public record OrderEventExternal(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("amount_cents") long amountCents
) {}
~~~

Hoặc áp dụng naming strategy phù hợp toàn ứng dụng. Đừng tự đoán Jackson luôn đổi snake_case thành camelCase. Hãy test DTO theo **payload thực tế**.

### 4.3. Null, số, enum và thời gian

- JSON `"150000"` là chuỗi; DTO `long` là số. Jackson có thể coerce theo cấu hình hoặc báo lỗi.
- JSON `null` vào primitive `long` có thể không mang nghĩa bạn muốn; kiểm tra validation và coercion.
- Enum chứa value không khai báo có thể phát `InvalidFormatException`.
- Ngày/giờ ISO và timezone cần kiểu Java tương ứng, module Jackson và định dạng rõ.
- Unknown JSON property có bị bỏ qua hay bị từ chối phụ thuộc cấu hình mapper/DTO.
- Với dữ liệu quan trọng, không chỉ deserialize thành công là đủ: cần kiểm tra business validation.

Không giải quyết vấn đề dữ liệu không hợp lệ bằng cách thay mọi field thành `String` rồi ép kiểu thủ công không kiểm soát.

## 5. FunctionCatalog: khác biệt giữa bean gốc và wrapper

Ví dụ function có chữ ký rõ:

~~~java
package demo.diagnostics.json;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return event -> new OrderReceipt(
            event.orderId(),
            "ACCEPTED"
        );
    }
}
~~~

Có hai cách lấy function:

~~~java
Function<OrderEvent, OrderReceipt> original =
    applicationContext.getBean("acceptOrder", Function.class);

Function<OrderEvent, OrderReceipt> wrapped =
    functionCatalog.lookup(Function.class, "acceptOrder");
~~~

`original` là object business function ban đầu. `wrapped` có thể là function đã được SCF instrument để chuyển đổi input/output và phục vụ composition.

### 5.1. Vì sao gọi trực tiếp với Map dễ gặp ClassCastException?

~~~java
Map<String, Object> payload = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

@SuppressWarnings("unchecked")
Function<Object, Object> raw =
    (Function<Object, Object>) (Function<?, ?>) original;

raw.apply(payload); // Không tự có Jackson binding ở bean gốc.
~~~

Lambda của `Function<OrderEvent,OrderReceipt>` thường kỳ vọng `OrderEvent`. Truyền `Map` vào bean gốc qua cast có thể tạo `ClassCastException`.

Điều đó **không chứng minh** SCF wrapper không chuyển đổi được JSON. Bạn đã bỏ qua ranh giới conversion khi gọi trực tiếp bean.

### 5.2. Vì sao catalog lookup thành công vẫn có lỗi dữ liệu?

~~~java
Function<OrderEvent, OrderReceipt> function =
    functionCatalog.lookup(Function.class, "acceptOrder");

if (function == null) {
    throw new IllegalStateException("Function not registered");
}
~~~

Đoạn này chỉ xác minh **tra cứu function thành công**. Nó chưa chứng minh:

- Có message converter đúng media type.
- Adapter đã tạo `Message` đúng.
- Generic type được suy ra đúng.
- JSON body có field hợp lệ.
- Function được gọi với `OrderEvent`.
- Output có thể serialize.

Đừng sửa tên function khi exception thật nằm ở converter hoặc business logic.

## 6. Nguyên nhân phổ biến nhất của Map thay POJO: mất kiểu đích

So sánh hai bean:

~~~java
// Cung cấp target type rõ ràng.
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

và:

~~~java
// Không khai báo OrderEvent làm input.
@Bean
Function<Object, Object> acceptAnything() {
    return value -> {
        System.out.println(value.getClass().getName());
        return value;
    };
}
~~~

Khi target là `Object`, converter có thể giữ nguyên một payload có sẵn hoặc deserialize JSON object thành `LinkedHashMap`. Điều này bình thường: framework không có thông tin rằng bạn thực sự muốn `OrderEvent`.

### 6.1. Ba kiểu chữ ký rất dễ gây nhầm

| Chữ ký | Khả năng biết kiểu POJO | Ghi chú |
| --- | --- | --- |
| `Function<OrderEvent,OrderReceipt>` | **Rõ** | Ưu tiên nếu hợp đồng ổn định |
| `Function<Message<OrderEvent>,Message<OrderReceipt>>` | **Rõ ở generic payload** | Khi cần đọc/ghi headers |
| `Function<Map<String,Object>,...>` | **Chủ động nhận Map** | Phù hợp dữ liệu linh hoạt, phải tự map |
| `Function<Object,Object>` | Không chỉ rõ POJO | Có thể nhận Map/String/bytes tùy adapter |
| Raw `Function` | Metadata generic bị mất | Converter khó suy target |
| `Function<Message<?>,...>` | Payload type không cụ thể | Dùng khi cố ý xử lý nhiều kiểu |
| `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` | Có generic của từng phần tử | Phải giữ metadata khi đăng ký reactive |

**Không nên ép kiểu**:

~~~java
OrderEvent event = (OrderEvent) message.getPayload();
~~~

nếu `message` có payload `Map`. Phải xác định lý do wrapper không nhận target đúng, hoặc thực hiện chuyển đổi có kiểu rõ ở ranh giới bạn thực sự sở hữu.

### 6.2. Chữ ký bị khai báo quá rộng ở @Bean

~~~java
@Bean
public Function rawOrderHandler() {
    return (Function<Object, Object>) value -> handle(value);
}
~~~

Dạng raw làm mất hợp đồng generic ngay trên bean declaration. Sửa:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> process(event);
}
~~~

Trong ví dụ, `process(OrderEvent)` là phương thức business trả `OrderReceipt`. Spring Cloud Function có thể suy input/output type từ chữ ký `@Bean`, thay vì cần đoán từ lambda body.

### 6.3. Lambda được đăng ký động mất type information

Với ứng dụng dùng `FunctionalSpringApplication`/`FunctionRegistration`, thông tin generic có thể không đủ nếu chỉ truyền một lambda có runtime class synthetic.

Tài liệu chính thức khuyến nghị registration giữ cả function **và metadata kiểu**, ví dụ minh họa:

~~~java
context.registerBean(
    "acceptOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(
        (Function<OrderEvent, OrderReceipt>) event ->
            new OrderReceipt(event.orderId(), "ACCEPTED")
    ).type(FunctionTypeUtils.functionType(
        OrderEvent.class,
        OrderReceipt.class
    ))
);
~~~

Đây là đoạn bên trong một `ApplicationContextInitializer<GenericApplicationContext>`, cần các import `FunctionRegistration`, `FunctionTypeUtils` và `Function` tương ứng theo phiên bản Spring Cloud Function. **Không copy nguyên đoạn vào `@Configuration` thông thường**; functional registration là một kiểu startup khác.

Kiểm tra tài liệu/version của `FunctionRegistration` trước khi áp dụng. Nếu project đã dùng `@Bean Function<OrderEvent,OrderReceipt>` rõ ràng, không cần chuyển mô hình đăng ký chỉ để chữa lỗi JSON.

## 7. Message<T>: payload type và headers là hai chuyện khác nhau

Một `Message<T>` gồm:

- `payload`: dữ liệu chính.
- `headers`: metadata, thường có `contentType`, correlation ID, routing/transport headers.

Ví dụ function cần cả payload và header:

~~~java
@Bean
Function<Message<OrderEvent>, Message<OrderReceipt>> acceptMessage() {
    return message -> {
        OrderEvent event = message.getPayload();

        OrderReceipt receipt =
            new OrderReceipt(event.orderId(), "ACCEPTED");

        return MessageBuilder.withPayload(receipt)
            .setHeader("correlationId",
                message.getHeaders().get("correlationId"))
            .build();
    };
}
~~~

Trong ví dụ có import:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Nếu generic payload thực sự là `OrderEvent` và adapter đi qua wrapper/converter phù hợp, business function có thể làm việc với POJO.

### 7.1. Tại sao Message<?> có thể trả Map?

~~~java
@Bean
Function<Message<?>, String> printPayloadType() {
    return message ->
        message.getPayload().getClass().getName();
}
~~~

Bạn đã yêu cầu `Message<?>` — không chỉ rõ `OrderEvent`. Nếu adapter hoặc client đã deserialize thành `LinkedHashMap`, function có thể thấy Map.

Không thể chỉ đổi:

~~~java
String contentType = "application/json";
~~~

rồi mặc định `Message<?>` biến thành `Message<OrderEvent>`. Header định dạng là **thông tin bổ sung**, không phải định nghĩa class đích.

### 7.2. Đừng nhầm headers với JSON fields

Message có thể có:

~~~text
Headers:
  contentType = application/json
  correlationId = abc-123

Payload bytes:
  {"orderId":"ORD-101","amountCents":150000}
~~~

`contentType` và `correlationId` là message headers. Chúng không phải field `orderId` của `OrderEvent`.

Nếu producer gửi một JSON envelope chứa cả metadata:

~~~json
{
  "headers": {"correlationId": "abc-123"},
  "payload": {"orderId": "ORD-101", "amountCents": 150000}
}
~~~

thì đây là **một cấu trúc JSON khác**, không tự được bóc thành Spring Message chỉ vì các key tên `headers` và `payload`. Khi adapter không biết envelope schema, có thể cần DTO envelope hoặc một bước unwrap rõ ràng.

## 8. contentType: định dạng dữ liệu, không phải class Java đích

Tài liệu Spring Cloud Function mô tả các message converters thông dụng:

| Converter | Content type liên quan | Vai trò |
| --- | --- | --- |
| JSON message converter | `application/json` | Chuyển JSON payload sang POJO phù hợp target type |
| String message converter | `text/plain` | Chuyển sang chuỗi |
| Byte-array converter | `application/octet-stream` | Xử lý bytes, có thể pass-through |

Với Spring Cloud Stream, khi không có header hay binding override, content type mặc định thường là `application/json`. Tuy nhiên, **default này không cứu một signature khai báo `Object`** hoặc một native deserializer đã quyết định trả `Map`.

### 8.1. Thứ tự ưu tiên với Stream

Trong mô hình content-type negotiation của Spring Cloud Stream, thông tin có thể đến từ:

1. **Header trên message**.
2. **Cấu hình binding**.
3. **Giá trị mặc định** (`application/json`).

Ví dụ binding:

~~~properties
spring.cloud.function.definition=acceptOrder
spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json
spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders-out
~~~

Binding name `acceptOrder-in-0` khác broker destination `orders-in`. Dòng trên khai báo media type cho **input binding**, không đổi tên Java function.

Nếu message **đã có header contentType sai**, việc đặt binding content type có thể không ghi đè header như bạn dự đoán. Phải kiểm tra header đến từ producer.

### 8.2. Nhầm text/plain với application/json

Producer gửi:

~~~text
Content-Type: text/plain

{"orderId":"ORD-101","amountCents":150000}
~~~

Nhìn bằng mắt đây là JSON, nhưng metadata bảo rằng payload là text. Tùy adapter/converter, input có thể thành `String` hoặc không thể đổi sang `OrderEvent`.

Đừng chữa bằng việc ép kiểu `String` sang `OrderEvent`. Sửa contract gửi dữ liệu, header hoặc mapping rõ ràng.

### 8.3. application/json không biến Java Map thành POJO một cách kỳ diệu

Nếu một bước upstream đã tạo `Map` và downstream khai báo `Object`, target type tương thích với Map, nên converter có thể không chạy.

Ví dụ:

~~~java
Function<Object, Object> generic = value -> value;

Object value = Map.of("orderId", "ORD-101");
Object result = generic.apply(value);
~~~

Function trên được yêu cầu xử lý `Object`, vì vậy trả `Map` là đúng hợp đồng. Nếu downstream muốn `OrderEvent`, phải làm rõ target ở function signature hoặc mapping có chủ đích.

## 9. Khi nào dùng readValue, convertValue và valueToTree?

Khi code **cố ý** nhận Map/Object do tích hợp linh hoạt, có thể chuyển ở biên bằng Jackson.

### 9.1. Từ JSON String hoặc byte[]: readValue

~~~java
ObjectMapper mapper = new ObjectMapper();

String json =
    "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

OrderEvent fromText =
    mapper.readValue(json, OrderEvent.class);

byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

OrderEvent fromBytes =
    mapper.readValue(bytes, OrderEvent.class);
~~~

`readValue` **parse JSON text hoặc bytes**. Dùng khi bạn thực sự có JSON cần phân tích.

### 9.2. Từ Map đã được deserialize: convertValue

~~~java
Map<String, Object> map = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

OrderEvent event =
    mapper.convertValue(map, OrderEvent.class);
~~~

`convertValue` tạo giá trị có kiểu đích từ object có sẵn. Dùng khi payload đã là Map/List/Java object; không cần serialize Map thành JSON text rồi parse lại.

### 9.3. Tránh nhầm trường hợp

| Dữ liệu đang có | Cách làm phù hợp |
| --- | --- |
| `String` chứa JSON | `readValue(String, Target.class)` |
| `byte[]` chứa JSON | `readValue(byte[], Target.class)` |
| `Map<String,Object>` | `convertValue(map, Target.class)` |
| `OrderEvent` đã đúng kiểu | Dùng trực tiếp; không cần convert lại |
| `JsonNode` | `treeToValue(node, Target.class)` hoặc `convertValue` |
| JSON array thành list DTO | `readValue(json, new TypeReference<List<OrderEvent>>() {})` |

Ví dụ cho danh sách:

~~~java
List<OrderEvent> orders = mapper.readValue(
    jsonArray,
    new TypeReference<List<OrderEvent>>() {}
);
~~~

Nếu chỉ dùng `List.class`, phần tử có thể là `LinkedHashMap` vì Jackson không được cung cấp kiểu `OrderEvent` của list.

### 9.4. Đừng lạm dụng ObjectMapper.convertValue cho mọi dữ liệu

Nếu target type là ổn định, ưu tiên sửa `Function<OrderEvent,...>` và conversion của adapter. Gắn `convertValue` bên trong mọi function có thể che một hợp đồng input sai và làm tốn tài nguyên.

Chỉ chuyển đổi thủ công khi ứng dụng thực sự sở hữu một **biên nhận dữ liệu động**, có validation, kiểm soát lỗi và schema rõ.

## 10. Lỗi ClassCastException với Map: xác định ai đã tạo Map

Một stack trace ví dụ:

~~~text
java.lang.ClassCastException:
  class java.util.LinkedHashMap cannot be cast to
  class demo.diagnostics.json.OrderEvent
~~~

Thông thường một trong các tình huống xảy ra:

1. Function được khai báo `Function<Object,...>` rồi cast trong body.
2. Function nhận `Message<?>` thay vì `Message<OrderEvent>`.
3. Function dùng raw `Function` và generic metadata bị mất.
4. Native deserializer của binder trả `Map`.
5. Một bước composition đã trả `Map` làm input cho bước kế tiếp.
6. Serverless adapter chỉ biết event như JSON object tổng quát.
7. Test tự đưa Map vào bean gốc mà bỏ qua SCF converter.
8. Class trong lambda bị ép kiểu không tương thích với input thực.

### 10.1. Đừng sửa bằng cast

~~~java
// Sai nếu payload là LinkedHashMap:
OrderEvent event = (OrderEvent) payload;
~~~

Một cast không parse JSON và cũng không tạo instance DTO. Đúng hướng là xác định target type hoặc convert:

~~~java
OrderEvent event =
    objectMapper.convertValue(payload, OrderEvent.class);
~~~

Chỉ dùng cách chuyển đổi này nếu `payload` là Java Map/structured object mà bạn đã kiểm tra và muốn chấp nhận như input của function.

### 10.2. Ghi log kiểu, không ghi toàn bộ nội dung

~~~java
String payloadType = payload == null
    ? "<null>"
    : payload.getClass().getName();

log.debug("Payload runtime type={}", payloadType);
~~~

Nếu đang ở Spring Message:

~~~java
log.debug("Payload type={}, contentType={}",
    message.getPayload().getClass().getName(),
    message.getHeaders().get("contentType")
);
~~~

Không log toàn bộ body JSON, token, PII hoặc secret trong production. Chỉ ghi type, contentType, eventId/correlation ID đã được cho phép, function name và error category.

## 11. Khi nào bản thân JSON không hợp lệ?

Không phải cứ nhận Map là do metadata. Một payload có thể không parse được ngay từ đầu.

### 11.1. Sai cú pháp

~~~text
{"orderId":"ORD-101","amountCents":150000
~~~

Thiếu dấu `}`; JSON parser có thể ném `JsonParseException` hoặc exception wrapper.

### 11.2. Sai hình dạng gốc

Function mong một object:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

nhưng producer gửi một array:

~~~json
[
  {"orderId":"ORD-101","amountCents":150000}
]
~~~

Nếu target là `OrderEvent` chứ không phải `List<OrderEvent>`, Jackson có thể không deserialize đúng, báo `MismatchedInputException`.

Ngược lại, khi signature mong `Flux<OrderEvent>`, adapter có thể có quy tắc split array hoặc không, tùy môi trường. Không tự cho rằng mọi adapter chuyển một JSON array thành nhiều `onNext`.

### 11.3. Sai giá trị kiểu

~~~json
{
  "orderId": "ORD-101",
  "amountCents": "not-a-number"
}
~~~

DTO dùng `long`, nên giá trị chuỗi không phải số có thể gây `InvalidFormatException` hoặc lỗi chuyển đổi tương ứng.

### 11.4. JSON bị mã hóa hai lần

Payload thực tế:

~~~json
"{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
~~~

Đây là **JSON string chứa JSON object dạng text**, không phải JSON object trực tiếp. Parser có thể deserialize thành `String` thay vì `OrderEvent`, hoặc báo shape mismatch khi target là POJO.

Kiểm tra producer serialize mấy lần và contract wire định dạng nào. Không “parse hai lần” trong consumer như cách mặc định nếu producer có thể sửa đúng.

### 11.5. Dữ liệu không phải JSON

Một record broker có thể chứa Avro, Protobuf, Java-serialized bytes hoặc message nén. Gắn header `contentType=application/json` không biến các bytes đó thành JSON. Cần đúng serializer/deserializer và schema của transport.

## 12. HTTP adapter: chẩn đoán riêng request body và Content-Type

Khi dùng `spring-cloud-function-web` với web stack tương thích, một function có thể được xuất thành endpoint HTTP.

Ví dụ:

~~~java
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(
        event.orderId(),
        "ACCEPTED"
    );
}
~~~

Gửi JSON:

~~~bash
curl -i -X POST \
  "http://localhost:8080/acceptOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"orderId":"ORD-101","amountCents":150000}'
~~~

Khi web adapter được cấu hình đúng, function có metadata kiểu và Jackson conversion tương thích, adapter có thể chuyển payload JSON thành `OrderEvent`.

### 12.1. Những lỗi cần tách riêng

| Hiện tượng | Tầng nghi ngờ |
| --- | --- |
| HTTP 404 | Route hoặc function definition, **không nhất thiết converter** |
| HTTP 415/406 | Content-Type/Accept hoặc mapping/negotiation của web adapter |
| HTTP 400 do parse | JSON/DTO/converter |
| HTTP 5xx với ClassCastException | Target runtime không đúng hoặc logic cast |
| Function nhận Map | Generic/Object/message conversion không xác định type |
| Response body sai JSON | Output serialization hoặc Content-Type đầu ra |
| HTTP request không có log function | Có thể lỗi **trước invocation** |

Không kết luận mọi converter exception đều phải trả đúng một mã HTTP cố định; status phụ thuộc phiên bản web adapter, exception handler và cách response đã bắt đầu hay chưa.

### 12.2. Content-Type và Accept khác nhau

- `Content-Type` mô tả **body được gửi lên**.
- `Accept` biểu đạt **định dạng response được client mong đợi**.
- `spring.cloud.function.definition` chọn function, không phải media type.
- `spring.cloud.function.web.path` có thể đổi base path; không ảnh hưởng Jackson target type.

Nếu JSON input không parse, đổi `Accept` không giải quyết được vấn đề nguồn. Nếu input đã thành POJO nhưng response serialize sai, hãy kiểm tra output type, converter và header đầu ra.

### 12.3. Đừng nhầm Spring MVC @RequestBody với Function Web Adapter

Một `@RestController` dùng `@RequestBody OrderEvent` có luồng argument resolution của Spring MVC/WebFlux controller. Một functional bean được SCF web adapter xuất thành endpoint có thể đi qua wrapper/converter của SCF.

Hai cách đều có thể dùng Jackson nhưng không nhất thiết có cùng conversion path. Test với **adapter thực tế** được deploy, không suy từ việc `@RestController` trong một test khác hoạt động.

## 13. Spring Cloud Stream: contentType, binding và native deserialization

Với Spring Cloud Stream, function nhận dữ liệu qua binding; message payload có thể được chuyển từ wire bytes thành Java type theo content-type negotiation của framework, **trừ những đường native decoding đặc biệt**.

Ví dụ:

~~~java
@Bean
Consumer<OrderEvent> recordOrder() {
    return event ->
        orderService.record(event);
}
~~~

Cấu hình illustrative:

~~~properties
spring.cloud.function.definition=recordOrder
spring.cloud.stream.bindings.recordOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.recordOrder-in-0.content-type=application/json
~~~

Trong ví dụ, `recordOrder` là tên function, `recordOrder-in-0` là binding name, `orders-in` là broker destination.

### 13.1. Lỗi thường gặp: cấu hình nhầm destination thành binding

Sai ý định:

~~~properties
spring.cloud.stream.bindings.orders-in.content-type=application/json
~~~

nếu binding thực sự tên `recordOrder-in-0`. Property trên có thể không tác động tới binding bạn nghĩ.

Cần kiểm tra tên binding trong log khởi động và cấu hình `spring.cloud.function.definition` thực tế. Với composition, tên binding có thể thay đổi theo definition được chọn.

### 13.2. Native decoding thay đổi nơi deserialize

Spring Cloud Stream có cấu hình per-binding consumer:

~~~properties
spring.cloud.stream.bindings.recordOrder-in-0.consumer.useNativeDecoding=true
~~~

Khi bật **native decoding**, binder/client library (ví dụ Kafka deserializer) chịu trách nhiệm decode input. Việc chuyển input theo `contentType` của binding không còn là con đường mặc định ở ranh giới đó.

Vì vậy có thể xảy ra:

~~~text
Kafka value deserializer
    → LinkedHashMap
    → function tưởng sẽ nhận OrderEvent
~~~

Nếu bạn chọn native JSON deserializer nhưng cấu hình nó chỉ trả `Map`, đừng kỳ vọng property `content-type=application/json` của SCF tự sửa hợp đồng deserializer.

Hướng kiểm tra:

1. `useNativeDecoding` có bật không?
2. Binder đang dùng deserializer nào?
3. Deserializer trả đúng class `OrderEvent`, `Map`, `String` hay bytes?
4. Producer serialize dữ liệu theo schema/format nào?
5. Consumer có đúng class trusted/config và classpath không?
6. Có một converter khác tự động đổi kiểu sau native decoder không? Kiểm tra theo version và adapter, **đừng giả định**.

### 13.3. Kafka JSON serializer/deserializer không đồng nghĩa SCF JsonMessageConverter

Hai hệ thống khác nhau:

| Cơ chế | Nơi chạy | Thông tin cấu hình |
| --- | --- | --- |
| Kafka value deserializer | Kafka client/binder native layer | Binder-specific client config, target class, trusted packages/schema |
| SCF/Stream `MessageConverter` | Khi chuyển Spring Message vào function | Target generic type, message `contentType`, converter stack |
| Jackson trong business code | Trong function do bạn gọi | `ObjectMapper`, DTO, `readValue`/`convertValue` |

Nếu cả native deserializer và business code đều deserialize tiếp, có thể xử lý trùng hoặc tạo một tầng Map/String không mong muốn. Chọn **một hợp đồng dữ liệu rõ ràng** cho mỗi ranh giới.

### 13.4. Error handling trước function

Khi lỗi xảy ra trong broker deserializer hoặc converter trước khi function được gọi, `try/catch` trong body của function **không thể bắt** lỗi đó vì body chưa được thực thi. Retry, DLQ và acknowledgment phải được thiết kế theo binder và điểm phát lỗi.

Không giả định một `onErrorResume` trong reactive function sẽ nhận mọi lỗi từ native Kafka deserializer.

## 14. Message headers và kiểu dữ liệu trong Spring Cloud Stream

Một message đầu vào có thể có:

~~~text
payload runtime type = [B
contentType = application/json
eventId = e-100
~~~

hoặc:

~~~text
payload runtime type = java.util.LinkedHashMap
contentType = application/json
eventId = e-100
~~~

Trường hợp thứ hai chưa chứng minh parser lỗi: dữ liệu đã được biến thành Map trước khi vào function.

### 14.1. Header không nhất thiết tồn tại y nguyên ở mọi transport

Tùy binder, producer và cách truyền headers:

- Header `contentType` có thể được đặt trực tiếp trên message.
- Binding config có thể cung cấp giá trị khi header thiếu.
- Một số hệ thống chuyển đổi hoặc loại bỏ headers trong quá trình đi qua broker/gateway.
- Native encoding/decoding có thể bỏ qua contentType negotiation.
- Header cùng tên ở các transport khác nhau có thể được biểu diễn kiểu `String` hoặc `MimeType`.

Hãy quan sát **header thực sự mà adapter tạo tại ranh giới function**, không chỉ header bạn nghĩ producer đã gửi.

### 14.2. Cẩn thận với headers được copy

Khi trả `Message<OrderReceipt>`, việc copy nguyên headers từ input có thể làm metadata đầu ra không phù hợp với payload mới. Ví dụ copy `contentType=text/plain` từ input cũ sang output POJO có thể khiến serialization ở output sai.

Nên chủ động giữ các header nghiệp vụ cần thiết (correlation ID, event ID) và để adapter tạo hoặc kiểm soát content type cho payload mới theo contract.

## 15. Serverless adapter: JSON event có thể thành Map khi không rõ target type

Trong môi trường serverless, adapter nhận một event JSON từ runtime. Khi function khai báo:

~~~java
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return e -> new OrderReceipt(e.orderId(), "ACCEPTED");
}
~~~

Spring Cloud Function có thể sử dụng metadata của function để chuyển raw event thành `OrderEvent`.

Ngược lại, với:

~~~java
@Bean
Function<Object, Object> inspectEvent() {
    return payload -> payload.getClass().getName();
}
~~~

runtime/adapter có thể deserialize một JSON object thành `Map` vì kiểu đích không rõ.

### 15.1. Phân biệt event envelope với business payload

Một sự kiện từ API Gateway, SQS, EventBridge hoặc nền tảng khác có thể có envelope chứa metadata và body nằm trong một property khác:

~~~json
{
  "requestContext": {"requestId": "req-101"},
  "body": "{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
}
~~~

Đây **không** phải body `OrderEvent` trực tiếp. Nếu function nhận toàn event, sẽ cần target type của envelope hoặc adapter biết cách trích `body`. Nếu body còn là JSON string bên trong envelope, cần xử lý thêm ở ranh giới thích hợp.

Không gắn `Function<OrderEvent,...>` cho mọi event shape mà chưa kiểm tra payload runtime của adapter.

### 15.2. Checklist serverless

1. Handler/entry point có đúng adapter đang deploy?
2. `spring.cloud.function.definition` chọn function nào?
3. Chữ ký generic có đúng kiểu event runtime không?
4. Event là business JSON trực tiếp hay envelope?
5. Body bên trong envelope là object hay JSON string escaped?
6. Mapper/adaptor có dependency và cấu hình Jackson cần thiết không?
7. Có native deserialization hoặc custom converter nào áp dụng không?
8. Có version khác nhau giữa local và artifact deploy không?

Không suy từ việc FunctionCatalog lookup thành công rằng mọi event JSON của platform sẽ tự trở thành đúng POJO nghiệp vụ.

## 16. Reactive function: Flux<OrderEvent> khác Flux<Map>

Một function reactive có thể được đăng ký:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> acceptOrderStream() {
    return incoming -> incoming.map(event ->
        new OrderReceipt(event.orderId(), "ACCEPTED")
    );
}
~~~

Spring Cloud Function/Stream có hỗ trợ reactive signature; khi được adapter cung cấp `Flux`, converter cần biết **kiểu phần tử** `OrderEvent` chứ không chỉ biết outer type `Flux`.

So sánh:

~~~java
@Bean
Function<Flux<Object>, Flux<Object>> passthroughStream() {
    return incoming -> incoming;
}
~~~

Nếu generic phần tử là `Object`, mỗi `onNext` có thể là `Map`/`String`/`byte[]` tùy adapter. Việc dùng `Flux` không tự khôi phục kiểu POJO.

### 16.1. Lỗi xuất hiện muộn khi subscribe

~~~java
Function<Flux<OrderEvent>, Flux<OrderReceipt>> fn =
    catalog.lookup(Function.class, "acceptOrderStream");

Flux<OrderReceipt> out = fn.apply(source);
~~~

Với nguồn cold, các callback `map` chưa chắc chạy cho tới khi có subscription. Nếu phần tử đầu tiên sai kiểu, exception có thể chỉ được phát thành `onError` khi adapter subscribe.

Kiểm tra với `StepVerifier` khi test Reactor trực tiếp:

~~~java
StepVerifier.create(fn.apply(
        Flux.just(new OrderEvent("ORD-101", 150000L))
    ))
    .expectNext(new OrderReceipt("ORD-101", "ACCEPTED"))
    .verifyComplete();
~~~

Test trên kiểm tra logic reactive với **POJO đã đúng kiểu**, chưa kiểm tra chuyển đổi JSON từ wire. Cần integration test adapter để chứng minh conversion ở biên.

### 16.2. Không ép cả batch vào một JSON object

Một request có JSON array:

~~~json
[
  {"orderId":"A","amountCents":100},
  {"orderId":"B","amountCents":200}
]
~~~

không có nghĩa mọi HTTP/Stream adapter sẽ tự chia thành hai `onNext(OrderEvent)`. Một adapter có thể coi đây là một message mang `List`. Kiểm tra contract batching/splitting của adapter và hàm thực tế.

### 16.3. Error signal ảnh hưởng stream dài hạn

Nếu một item không convert được và lỗi lan thành `onError`, một reactive stream dài hạn có thể kết thúc, không tự tiếp tục tới item sau. Phục hồi per-item trong function chỉ hiệu quả nếu event lỗi **đã vào được** function dưới hình thái có thể xử lý.

Nếu lỗi xảy ra **trước** bước đưa item vào pipeline (native deserializer/converter), chính sách lỗi cần được xử lý ở adapter/binder.

## 17. Composition: kiểu đầu ra bước trước làm thay đổi bước sau

Giả sử:

~~~java
@Bean
Function<String, OrderEvent> parseOrder(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Invalid order JSON", error
            );
        }
    };
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

Có thể ghép:

~~~properties
spring.cloud.function.definition=parseOrder|acceptOrder
~~~

Trong ví dụ này, bước `parseOrder` chủ động nhận `String` chứa JSON và trả `OrderEvent`. Bước `acceptOrder` nhận POJO. Hợp đồng của **mỗi mắt xích** cần đúng.

### 17.1. Chữ ký sai ở bước đầu

~~~java
@Bean
Function<String, Object> parseAsGeneric(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, Object.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException("Invalid JSON", error);
        }
    };
}
~~~

Ví dụ sử dụng `com.fasterxml.jackson.core.JsonProcessingException` và xử lý checked exception trong lambda. Nếu parse vào `Object.class`, JSON object có thể thành `LinkedHashMap`. Khi nối vào `acceptOrder`:

~~~properties
spring.cloud.function.definition=parseAsGeneric|acceptOrder
~~~

khả năng chuyển Map sang POJO còn phụ thuộc wrapper/conversion giữa hai function. Không nên dựa vào conversion ngầm khi bước đầu **đáng lẽ phải khai báo và trả `OrderEvent`**.

Sửa hợp đồng:

~~~java
Function<String, OrderEvent> parse =
    json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(error);
        }
    };
~~~

### 17.2. Tránh parse hai lần

Nếu HTTP/Stream adapter đã chuyển JSON bytes thành `OrderEvent`, thêm một `parseOrder` yêu cầu `String` có thể tạo vòng conversion không cần thiết hoặc lỗi.

Có hai cách thiết kế tách bạch:

- **Adapter chuyển đổi:** input `Function<OrderEvent,OrderReceipt>`; producer gửi JSON với content type đúng.
- **Function tự parse raw JSON:** input `Function<String,OrderReceipt>` hoặc `Function<byte[],OrderReceipt>`; function tự quản lý validation và lỗi parse.

Không dùng cả hai mà không có lý do và test hợp đồng rõ ràng.

## 18. Content-Type có tham số type: chỉ dùng khi cần và kiểm soát an toàn

Tài liệu Spring Cloud Function mô tả JSON message converter có thể nhận tham số MIME type, ví dụ:

~~~text
Content-Type: application/json;type=demo.diagnostics.json.OrderEvent
~~~

Điều này có thể giúp chỉ định target type khi function có chữ ký không rõ như `Function<Object,Object>` hoặc raw `Function`.

**Tuy nhiên, không dùng tham số type từ dữ liệu không tin cậy để cho caller yêu cầu deserialize thành class tùy ý.** Tài liệu SCF hiện đại yêu cầu allowlist cho các class được chọn bằng tham số `type`, đặt trong:

~~~text
META-INF/deserializable.types
~~~

Một nội dung minh họa:

~~~text
demo.diagnostics.json.OrderEvent
demo.diagnostics.json.OrderReceipt
~~~

Chỉ cho phép các class đã được đánh giá phù hợp. Không tạo wildcard “mọi class” hoặc đưa danh sách class nội bộ nhạy cảm vào đó chỉ để chữa triệu chứng Map.

### 18.1. Ưu tiên hợp đồng tường minh hơn dynamic type

Nếu nghiệp vụ luôn nhận đơn hàng, giải pháp đơn giản và an toàn hơn thường là:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

thay vì:

~~~java
Function<Object, Object>
~~~

kèm loại Java lấy từ HTTP header. Dynamic type chỉ nên xuất hiện ở các hệ thống thật sự có yêu cầu đa kiểu, có schema registry/allowlist và đường xác thực rõ ràng.

### 18.2. Version compatibility

Cơ chế `META-INF/deserializable.types` và cách xử lý MIME parameter có thể thay đổi theo phiên bản. Đối chiếu tài liệu và dependency/BOM của ứng dụng. Đây **không phải** cách duy nhất hay mặc định để bật POJO conversion.

## 19. Khi nào cần custom MessageConverter?

Các converter mặc định xử lý nhiều trường hợp JSON, String, byte[]. Nếu dữ liệu là format đặc biệt hoặc media type tùy chỉnh, bạn có thể cần `org.springframework.messaging.converter.MessageConverter` riêng.

Ví dụ nhu cầu:

- Dữ liệu định dạng thương mại nội bộ, không phải JSON.
- Một binary format có schema khác JSON.
- Một MIME type mới cần converter chuyên dụng.
- Cần chuyển payload chuẩn hóa đặc thù trước business function.

### 19.1. Đừng viết custom converter để thay một generic signature sai

Nếu vấn đề chỉ là:

~~~java
Function<Object, Object>
~~~

trong khi input thực ra luôn là `OrderEvent`, **sửa chữ ký** nhanh và rõ hơn việc thêm converter override toàn cục.

### 19.2. Custom converter có thể ảnh hưởng toàn ứng dụng

Tài liệu Spring Cloud Function cho phép đăng ký bean `MessageConverter` tùy chỉnh; custom converters có thể được đặt ở thứ tự ưu tiên cao hơn converters mặc định. Nếu converter tự tuyên bố hỗ trợ quá nhiều message types, nó có thể chiếm xử lý cả những payload JSON bình thường và làm regression nơi khác.

Cần test:

1. `supports`/media type chỉ nhận format được thiết kế.
2. Converter từ chối input không phù hợp, không nuốt exception im lặng.
3. Payload được chuyển thành đúng target type.
4. Các function khác vẫn dùng JSON converter mặc định.
5. Headers và encoding được xử lý đúng.
6. Không deserialize tùy ý class từ dữ liệu không tin cậy.

Custom converter phải được đăng ký đúng cách và test ở adapter; chỉ viết class không làm nó tự hoạt động.

## 20. Ma trận nhận diện lỗi theo exception và thời điểm

| Triệu chứng | Thời điểm thường gặp | Giả thuyết cần kiểm tra |
| --- | --- | --- |
| `JsonParseException` | Parse JSON bytes/String | Sai cú pháp/encoding/truncated payload |
| `MismatchedInputException` | Deserialize target class | JSON array/object không khớp shape |
| `InvalidFormatException` | Bind field | Giá trị số/enum/date không đúng format |
| `MessageConversionException` | MessageConverter | contentType, target generic, converter stack |
| `ClassCastException: LinkedHashMap → OrderEvent` | Function invocation | Target bị khai Object/Map, bypass converter, native decoding |
| `IllegalArgumentException` trong `convertValue` | Map → POJO thủ công | Field/constructor/type không khớp |
| `HttpMessageNotReadableException` | Web MVC payload resolution | JSON/DTO không parse được ở web layer |
| Function nhận `byte[]` | Trước/ở invocation | Không giải mã, native decoding, octet-stream |
| Function nhận `String` JSON escaped | Ở converter/function | Content type text/plain hoặc double encoding |
| Output JSON sai | Sau invocation | Output DTO/converter/headers |
| Error trước log đầu tiên trong function | Trước invocation | Adapter/parser/deserializer/converter |
| Error chỉ khi subscribe reactive | Trong pipeline | Inner type mismatch, lazy conversion/operator |

**Exception có thể được bọc qua nhiều tầng.** Hãy tìm *root cause* có message hữu ích và stack frame liên quan Jackson, message converter, binder hoặc function invocation, thay vì dựa vào class exception ngoài cùng.

## 21. Quy trình chẩn đoán có thể thực hiện trong một lần điều tra

~~~mermaid
flowchart TD
    START["Nhận Map hoặc lỗi JSON"] --> STEP1["Xác định adapter và function definition"]
    STEP1 --> STEP2{"JSON thuần có parse thành POJO?"}
    STEP2 -->|Không| DTO["Sửa JSON / DTO / ObjectMapper"]
    STEP2 -->|Có| STEP3{"Function signature có type cụ thể?"}
    STEP3 -->|Không| TYPE["Function<OrderEvent,...>\nMessage<OrderEvent>\nFlux<OrderEvent>"]
    STEP3 -->|Có| STEP4{"Input đến function là Message hay non-Message?"}
    STEP4 -->|Message| HEADER["Kiểm tra payload class,\ncontentType và converter"]
    STEP4 -->|Non-Message| CONV["Kiểm tra ConversionService,\nraw input, wrapper"]
    HEADER --> NATIVE{"Stream native decoding?"}
    NATIVE -->|Có| DRIVER["Kiểm tra Kafka/Rabbit\nserializer/deserializer"]
    NATIVE -->|Không| ADAPTER["Kiểm tra binding/HTTP\nenvelope và metadata"]
    CONV --> ADAPTER
    DTO --> TEST["Test theo từng ranh giới"]
    TYPE --> TEST
    DRIVER --> TEST
    ADAPTER --> TEST
~~~

### 21.1. Checklist kiểm tra nhanh

1. **Function thật sự được chọn là gì?** `spring.cloud.function.definition`, catalog name và composition có đúng không?
2. **Input đến từ đâu?** HTTP, Stream, serverless hay Java caller trực tiếp?
3. **Root JSON là object, array, string hay envelope?** Có bị encode hai lần không?
4. **Jackson thuần có đọc vào `OrderEvent` được không?** Nếu không, sửa DTO/schema trước.
5. **Chữ ký @Bean có cụ thể không?** Tránh raw `Function`/`Object` nếu cần POJO.
6. **Nếu dùng Message/Flux, generic payload/element type có đúng không?**
7. **Function được lấy qua FunctionCatalog wrapper hay bean gốc?**
8. **Payload thực tế là `byte[]`, `String`, `Map` hay `OrderEvent`?**
9. **Header `contentType` thực tế là gì?** Có bị producer/binding ghi đè không?
10. **Nếu Stream, binding name và native decoding có đúng không?**
11. **Nếu serverless, event có envelope/body nested không?**
12. **Lỗi phát ra trước invocation hay bên trong business logic?**
13. **Có custom converter/deserializer nào ưu tiên hơn mặc định không?**
14. **Test mỗi tầng đã tách biệt chưa?** Jackson → catalog → adapter → wire end-to-end.

### 21.2. Không chữa sai tầng

- Chuyển thành `Map` không sửa một JSON bị lỗi cú pháp.
- Đổi `contentType` không sửa một DTO thiếu constructor cần thiết.
- Thêm `@JsonProperty` không khôi phục generic type đã bị khai là `Object`.
- Đổi Kafka topic không làm converter biết class `OrderEvent`.
- Thêm `ObjectMapper.convertValue` trong mọi lambda không sửa được native deserializer thất bại **trước function**.
- Thay `spring.cloud.function.definition` không thay đổi schema của JSON.
- Retry một payload không deserialize được thường chỉ khiến cùng lỗi lặp lại, trừ khi dữ liệu/config đã thay đổi.

## 22. Tạo một function mẫu để kiểm thử đầu cuối

Cấu hình tối thiểu:

~~~java
package demo.diagnostics.json;

import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JsonDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonDiagnosticsApplication.class, args);
    }

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return event -> new OrderReceipt(
            event.orderId(),
            "ACCEPTED"
        );
    }
}
~~~

Dùng đúng các `record OrderEvent` và `OrderReceipt` ở mục 4, đảm bảo ba class thuộc package `demo.diagnostics.json` và project có dependency Spring Cloud Function tương thích.

Cấu hình lựa chọn:

~~~properties
spring.cloud.function.definition=acceptOrder
~~~

Property này chọn **function**, không tự cài web adapter hoặc binder. Với HTTP, cần module web; với Stream, cần Spring Cloud Stream và binder; với serverless, cần adapter/runtime.

## 23. Test Jackson thuần: tách lỗi DTO khỏi framework

Dùng JUnit 5, Jackson và AssertJ:

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class JacksonOrderEventTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void jsonTextBecomesOrderEvent() throws Exception {
        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        OrderEvent event =
            mapper.readValue(json, OrderEvent.class);

        assertThat(event.orderId()).isEqualTo("ORD-101");
        assertThat(event.amountCents()).isEqualTo(150000L);
    }

    @Test
    void mapBecomesOrderEventWhenTargetIsExplicit() {
        Map<String, Object> input = Map.of(
            "orderId", "ORD-101",
            "amountCents", 150000
        );

        OrderEvent event =
            mapper.convertValue(input, OrderEvent.class);

        assertThat(event.orderId()).isEqualTo("ORD-101");
        assertThat(event.amountCents()).isEqualTo(150000L);
    }

    @Test
    void genericObjectIsNotAutomaticallyOrderEvent()
            throws Exception {
        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        Object decoded = mapper.readValue(json, Object.class);

        assertThat(decoded).isInstanceOf(Map.class);
        assertThat(decoded).isNotInstanceOf(OrderEvent.class);
    }
}
~~~

Ba test cùng dùng JSON hợp lệ. Chúng chứng minh **target type** quyết định việc Jackson tạo POJO hay Map.

### 23.1. Thêm test lỗi shape/field

~~~java
@Test
void invalidAmountFailsDeserialization() {
    String invalid =
        "{\"orderId\":\"ORD-101\",\"amountCents\":\"abc\"}";

    assertThatThrownBy(() ->
        mapper.readValue(invalid, OrderEvent.class)
    ).isInstanceOf(JsonProcessingException.class);
}
~~~

Phương thức này đặt trong class test trên, bổ sung static import `org.assertj.core.api.Assertions.assertThatThrownBy` và import `com.fasterxml.jackson.core.JsonProcessingException`.

Test Jackson thuần vẫn **không chứng minh** FunctionCatalog hoặc binder đã chọn converter đúng.

## 24. Test FunctionCatalog: xác minh tên, signature và logic

Một test Spring Boot dùng chính application ở mục 22:

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = JsonDiagnosticsApplication.class)
class CatalogOrderFunctionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void functionIsPresentAndAcceptsTypedPojo() {
        assertThat(catalog.getNames(null))
            .contains("acceptOrder");

        Function<OrderEvent, OrderReceipt> function =
            catalog.lookup(Function.class, "acceptOrder");

        assertThat(function).isNotNull();

        OrderReceipt result = function.apply(
            new OrderEvent("ORD-101", 150000L)
        );

        assertThat(result).isEqualTo(
            new OrderReceipt("ORD-101", "ACCEPTED")
        );
    }
}
~~~

Test này kiểm tra **bean lookup và xử lý POJO**. Nó cố ý đưa một `OrderEvent` đã tạo sẵn, vì thế **chưa kiểm tra chuyển JSON bytes thành POJO**.

### 24.1. Khi nào cần test converter ở catalog layer?

Nếu nghi wrapper sai metadata type, tạo input `Message<byte[]>` với `contentType=application/json` và gọi wrapper qua đúng API/adapter version; assert rằng handler thật được cung cấp `OrderEvent`. Tuy nhiên, kiểu return wrapper có thể thay đổi khi dùng `Message`/conversion. Tránh viết test dựa trên cast output mù quáng.

Một chiến lược ít giòn hơn là instrument/mock business service được function gọi, đưa message bytes qua adapter test và xác minh service được gọi với `OrderEvent` đúng giá trị. Như vậy test chứng minh **conversion thực sự xảy ra**, không chỉ chứng minh wrapper trả object bất kỳ.

## 25. Test HTTP integration: chứng minh JSON được chuyển trước function

Nếu project tích hợp `spring-cloud-function-web` và Spring Boot Web, sử dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng `TestRestTemplate`.

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    classes = JsonDiagnosticsApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.cloud.function.definition=acceptOrder"
)
class HttpJsonConversionTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Test
    void jsonRequestProducesReceipt() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(
            java.util.List.of(MediaType.APPLICATION_JSON)
        );

        String body =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        ResponseEntity<String> response = rest.exchange(
            "/acceptOrder",
            HttpMethod.POST,
            new HttpEntity<>(body, headers),
            String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful())
            .isTrue();

        JsonNode result = mapper.readTree(response.getBody());

        assertThat(result.path("orderId").asText())
            .isEqualTo("ORD-101");
        assertThat(result.path("status").asText())
            .isEqualTo("ACCEPTED");
    }
}
~~~

Test này dùng **HTTP adapter thực** để đi qua các bước body → message → conversion → function → output serialization.

Nếu adapter phiên bản đang dùng có rule root mapping hoặc chọn function path khác, đối chiếu tài liệu web adapter và điều chỉnh URL của test theo mapping thật, không đổi DTO cho đến khi xác định request đã tới đúng route.

### 25.1. Negative test không cần gây side effect

Với payload sai:

~~~json
{"orderId":"ORD-101","amountCents":"not-a-number"}
~~~

Test nên kiểm tra không trả response thành công giả và — nếu dùng service spy — **business action không được gọi**. Đừng gắn cứng HTTP status nếu contract phiên bản adapter không cam kết status đó; quan trọng là lỗi conversion được phân loại và không có side effect.

## 26. Test Spring Cloud Stream: xác minh message qua binding

Nếu sử dụng Spring Cloud Stream, một test đúng nên gửi JSON qua test binder hoặc broker test, không chỉ gọi function với `OrderEvent` có sẵn.

Cấu hình ví dụ:

~~~properties
spring.cloud.function.definition=recordOrder
spring.cloud.stream.bindings.recordOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.recordOrder-in-0.content-type=application/json
~~~

Test phải xác nhận:

1. Binding thực là `recordOrder-in-0`.
2. Test producer gửi UTF-8 JSON bytes với header `contentType` phù hợp hoặc dùng binding content type.
3. Consumer/service nhận đúng `OrderEvent`, không phải `Map`.
4. Thông điệp sai định dạng đi vào cơ chế error handling của binder.
5. Khi `useNativeDecoding=true`, test chính deserializer được cấu hình, không chỉ SCF JSON converter.

### 26.1. Vì sao test trực tiếp FunctionCatalog chưa đủ?

Cùng function:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

có thể chạy đúng khi caller Java đưa `OrderEvent`; nhưng ở Stream, value deserializer có thể trả `Map`, header `contentType` khác, hoặc message được gửi như envelope. Chỉ integration test tại **đường ingress thật** mới phản ánh đầy đủ.

### 26.2. Lỗi conversion không được xử lý như lỗi nghiệp vụ bình thường

Nếu input không parse được **trước khi function được gọi**, `onErrorResume` trong body reactive function hoặc `try/catch` trong business lambda không thể bắt trực tiếp lỗi đó.

Bạn cần cấu hình error channel/retry/DLQ/redelivery theo binder và version, đồng thời tránh retry không giới hạn cho dữ liệu hỏng cố định.

## 27. Các thói quen thiết kế để tránh Map ngoài ý muốn

| Thói quen | Lợi ích |
| --- | --- |
| Khai báo `Function<OrderEvent,OrderReceipt>` | Target type rõ cho wrapper và reviewer |
| Dùng `Message<OrderEvent>` khi cần headers | Giữ metadata mà không bỏ generic payload |
| Dùng `Flux<OrderEvent>` trong reactive signature | Giữ kiểu phần tử của stream |
| Chỉ dùng `Map` khi schema thật sự động | Tránh cast mù quáng |
| Dùng `FunctionRegistration` với type metadata khi functional startup | Không mất generic của lambda đăng ký động |
| Test Jackson DTO trước | Tách lỗi schema khỏi adapter |
| Chỉ định `contentType` đúng tại wire/binding | Converter biết media type |
| Kiểm tra native deserializer khi bật native decoding | Không gán nhầm trách nhiệm cho SCF |
| Không deserialize bằng arbitrary class từ header | Giảm rủi ro bảo mật |
| Không copy `contentType` output không phù hợp | Tránh serialize sai ở bước sau |
| Test adapter với JSON bytes thật | Chứng minh conversion tại ingress |
| Ghi log payload type + correlation ID hợp lệ | Điều tra mà không rò rỉ dữ liệu |

### 27.1. Một contract nên được ghi thành ví dụ có thể chạy

Trong tài liệu API nội bộ, nên có:

~~~text
Function bean: acceptOrder
Input type: OrderEvent(orderId: String, amountCents: long)
Output type: OrderReceipt(orderId: String, status: String)
Wire format: application/json
HTTP path (nếu dùng web adapter): /acceptOrder
Stream input binding (nếu dùng Stream): acceptOrder-in-0
Schema example: {"orderId":"ORD-101","amountCents":150000}
Invalid amount policy: reject or dead-letter, not silently coerce
~~~

Tất cả fields, media type, binding names và response format nên được test đúng adapter, không chỉ ghi trong README.

## 28. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “JSON hợp lệ thì luôn nhận POJO.” | Còn cần target type, converter và adapter đúng. |
| “`application/json` buộc payload phải thành OrderEvent.” | Content type là gợi ý định dạng, không thay generic type. |
| “Nhận LinkedHashMap chứng tỏ Jackson parse lỗi.” | Jackson có thể parse thành Map thành công khi target là `Object`/`Map`. |
| “Cast Map sang POJO là đủ.” | Cast không tạo object domain, cần conversion có target type. |
| “`readValue(json, Object.class)` tự đoán POJO.” | JSON object thông thường có thể thành Map. |
| “`Function<Object,Object>` vẫn để SCF biết OrderEvent.” | Chữ ký không biểu đạt domain target. |
| “`Message<?>` giống `Message<OrderEvent>`.” | Generic payload bị thiếu. |
| “Chỉ cần lấy bean gốc từ context là được SCF convert.” | Bean gốc không tự có wrapper conversion. |
| “Cứ đổi topic Kafka là hết ClassCastException.” | Vấn đề có thể ở deserializer/type, không phải destination. |
| “Native decoding vẫn luôn dựa vào binding contentType.” | Native client deserializer chịu trách nhiệm tạo payload. |
| “`Flux` chắc chắn chia JSON array thành từng event.” | Splitting/batching phụ thuộc adapter và contract. |
| “Jackson DTO không có no-arg constructor thì luôn lỗi.” | Record/`@JsonCreator`/builder phù hợp vẫn deserialize được. |
| “Mọi lỗi JSON có thể bắt trong function.” | Lỗi trước invocation thuộc adapter/converter. |
| “Thêm custom converter sửa được mọi lỗi kiểu.” | Converter có thể che vấn đề và gây regression. |
| “Dùng MIME `type=...` từ user input là an toàn.” | Cần allowlist rõ và kiểm soát dữ liệu không tin cậy. |
| “FunctionCatalog lookup không null chứng minh conversion hoạt động.” | Lookup chỉ chọn function; cần test input/output thực. |
| “Test `ObjectMapper` thành công nghĩa HTTP/broker cũng chạy.” | Adapter có thêm header, serializer và routing. |
| “HTTP 404 là lỗi JSON.” | Có thể route không tồn tại hoặc definition sai. |

## 29. Câu hỏi tự đánh giá

1. JSON object giống hệt nhau có thể trở thành `LinkedHashMap` hoặc `OrderEvent` vì sao?
2. `ObjectMapper.readValue(json, Object.class)` khác `readValue(json, OrderEvent.class)` ở đâu?
3. Vì sao `Map` không nhất thiết chứng minh JSON parser thất bại?
4. Spring Cloud Function dùng `MessageConverter` khi nào, `ConversionService` khi nào?
5. Tại sao `FunctionCatalog` wrapper có thể có conversion còn bean gốc lấy trực tiếp thì không?
6. `contentType=application/json` và `Function<OrderEvent,OrderReceipt>` đóng hai vai trò bổ sung nào?
7. Nếu function khai báo `Function<Object,Object>`, framework có biết phải tạo `OrderEvent` không?
8. Khi dùng `Message<?>`, điều gì thiếu so với `Message<OrderEvent>`?
9. Vì sao `FunctionRegistration` cần thông tin generic trong functional startup?
10. Khi nào dùng `readValue`, khi nào dùng `convertValue`?
11. Vì sao `List.class` có thể cho các phần tử là Map thay vì `List<OrderEvent>`?
12. Nếu JSON là array nhưng target là một `OrderEvent`, lỗi nào có thể xảy ra?
13. Nếu HTTP body là JSON string đã escape chứa một JSON object, dữ liệu có thể bị xử lý thế nào?
14. Vì sao header `contentType` của message có thể ưu tiên hơn binding property trong Stream?
15. `useNativeDecoding=true` chuyển trách nhiệm deserialize sang đâu?
16. Khi Kafka deserializer trả Map, có thể chỉ đổi binding `content-type` để chắc chắn thành POJO không?
17. Vì sao lỗi native deserializer có thể xảy ra trước function?
18. Với `Flux<OrderEvent>`, cần kiểm tra kiểu ngoài `Flux` hay kiểu của từng phần tử?
19. Tại sao composition có thể tạo lỗi kiểu giữa hai function dù cả hai đều được lookup?
20. Khi nào tham số MIME `type=...` được cân nhắc và vì sao cần allowlist?
21. Test Jackson thuần, catalog test và HTTP integration test chứng minh những điều khác nhau nào?
22. Bạn sẽ thu thập những thông tin gì để điều tra `ClassCastException: LinkedHashMap cannot be cast to OrderEvent` mà không log dữ liệu nhạy cảm?
23. Nếu DTO có tên field snake_case khác camelCase, cần kiểm thử và sửa ở đâu?
24. Khi nào nên viết custom MessageConverter và vì sao nó không phải lựa chọn đầu tiên?

## 30. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `FunctionCatalog`, type conversion, `MessageConverter`, `ConversionService`, JSON converter, MIME `type` và allowlist deserialization.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionRegistration`, `FunctionTypeUtils` và generic metadata.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — HTTP path, request/response và web adapter.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html#_content_type_negotiation) — `contentType`, binding, message converters và thứ tự ưu tiên header/binding/default.
- [Spring Cloud Stream — Consumer Properties](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html#_consumer_properties) — `useNativeDecoding` và yêu cầu đối với deserializer.
- [Jackson Databind — ObjectMapper](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html) — `readValue`, `convertValue`, `treeToValue`.
- [Spring Cloud Stream — Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — kiểm thử message binding theo đường ingress.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` cho reactive function.

Bài sử dụng Java 17+ và các API thông dụng của Spring Cloud Function/Stream. Hành vi cụ thể của converter, binder, serializer và serverless adapter phụ thuộc phiên bản Spring Cloud, dependency/BOM và cấu hình thực tế. Cần kiểm tra ở phiên bản đã deploy và test qua chính adapter đó.

**Ghi nhớ:** Khi input JSON không thành POJO mà là `Map`, trước tiên xác định **kiểu dữ liệu đích mà framework biết tại ranh giới chuyển đổi**. Chữ ký `Function<OrderEvent,OrderReceipt>`, `Message<OrderEvent>` hoặc `Flux<OrderEvent>` rõ ràng giúp converter chọn đúng target; `contentType=application/json` chỉ mô tả định dạng. Nếu input đã là `Map`, `ObjectMapper.convertValue(...)` có thể chuyển thành POJO khi bạn chủ động sở hữu bước mapping, nhưng không nên dùng nó để che một hợp đồng type bị khai quá rộng. Với HTTP, Spring Cloud Stream và serverless, hãy kiểm tra từng tầng từ **wire bytes → adapter/message headers → converter hoặc native deserializer → FunctionCatalog wrapper → business function**, rồi xác nhận bằng test ở ranh giới thật.
