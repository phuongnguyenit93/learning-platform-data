# Viết module cho kiểu giá trị riêng và kiểm thử chuyển đổi hai chiều

Trong domain model, nhiều giá trị không nên được biểu diễn bằng `String`, `long` hoặc `BigDecimal` ở mọi nơi. Ví dụ, mã đơn hàng, mã tài khoản, địa chỉ email, số điện thoại, tiền tệ và mã quốc gia có quy tắc hợp lệ riêng. Ta có thể đóng gói mỗi giá trị thành một **value object** để bảo vệ invariant và làm rõ ý nghĩa của kiểu dữ liệu.

Khi Jackson serialize/deserialize các kiểu riêng này, ứng dụng cần quyết định wire representation: một chuỗi, một số hay một object JSON có nhiều field. Nếu muốn giữ domain class độc lập với annotation Jackson, có thể viết một **Jackson module** đăng ký serializer và deserializer cho các value object. Module gom quy tắc chuyển đổi vào một nơi, giúp nhiều endpoint và mapper dùng cùng contract.

Phần thực hành này xây dựng `OrderId` dưới dạng JSON string và `Money` dưới dạng JSON object. Sau đó đăng ký chúng trong `SimpleModule`, kiểm tra chiều Java → JSON và JSON → Java, kiểm tra round-trip, nested object, collection, map key, null và input sai.

## 1. Value object và wire representation

Value object biểu diễn một giá trị có ý nghĩa và quy tắc riêng. Ví dụ:

```java
OrderId id = OrderId.of("ORD-00001234");
```

Giá trị này khác một `String` tùy ý vì nó phải tuân theo format mã đơn hàng. Nếu mọi method đều nhận `String`, code có thể vô tình truyền email vào vị trí order ID. Dùng `OrderId` giúp compiler phân biệt hai khái niệm.

Jackson cần biết cách biểu diễn value object trong JSON. Có hai lựa chọn thường gặp:

**Scalar representation:** value object được biểu diễn bằng một JSON primitive.

```json
"ORD-00001234"
```

**Structured representation:** value object được biểu diễn bằng object có field rõ ràng.

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Chọn representation dựa trên public contract và khả năng tiến hóa. Mã định danh thường phù hợp với scalar string. Một giá trị tiền gồm amount và currency thường phù hợp với object để không mất đơn vị tiền.

## 2. Tạo value object bất biến

Ví dụ `OrderId` là một class bất biến. Constructor không public để mọi instance đều đi qua factory method kiểm tra định dạng.

```java
import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderId {
    private static final Pattern FORMAT = Pattern.compile("ORD-[0-9]{8}");

    private final String value;

    private OrderId(String value) {
        this.value = value;
    }

    public static OrderId of(String value) {
        Objects.requireNonNull(value, "OrderId must not be null");
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "OrderId must match ORD- followed by 8 digits"
            );
        }
        return new OrderId(value);
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderId)) return false;
        OrderId that = (OrderId) other;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }
}
```

Điểm quan trọng:

- Value object tự bảo vệ invariant, không phụ thuộc Jackson.
- `equals()` và `hashCode()` dựa trên giá trị bên trong để test và dùng làm map key ổn định.
- `toString()` hỗ trợ log/debug, nhưng không nên dùng `toString()` như một serializer ngầm nếu wire format cần kiểm soát.
- Factory method từ chối giá trị sai thay vì tạo object không hợp lệ.

Jackson deserializer sẽ gọi `OrderId.of()`. Nhờ đó, dữ liệu JSON không thể tạo một `OrderId` vượt qua validation của domain type.

## 3. Serializer và deserializer cho scalar value object

Serializer chuyển `OrderId` thành JSON string. Deserializer yêu cầu token đầu vào là JSON string, sau đó gọi factory method.

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdScalarSerializer;

import java.io.IOException;

public final class OrderIdSerializer extends StdScalarSerializer<OrderId> {
    public OrderIdSerializer() {
        super(OrderId.class);
    }

    @Override
    public void serialize(
            OrderId value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeString(value.value());
    }
}
```

Deserializer:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdScalarDeserializer;

import java.io.IOException;

public final class OrderIdDeserializer extends StdScalarDeserializer<OrderId> {
    public OrderIdDeserializer() {
        super(OrderId.class);
    }

    @Override
    public OrderId deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            return (OrderId) context.handleUnexpectedToken(OrderId.class, parser);
        }

        String rawValue = parser.getText();
        try {
            return OrderId.of(rawValue);
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser,
                "Invalid OrderId value: " + exception.getMessage(),
                exception
            );
        }
    }
}
```

Deserializer xử lý hai lớp kiểm tra:

1. **JSON type:** chỉ nhận token `VALUE_STRING`. Số, boolean, object và array không tự động bị chuyển thành string.
2. **Domain value:** chuỗi phải thỏa `OrderId` format. Nếu không, Jackson ném mapping exception có nguyên nhân là lỗi validation của value object.

Không nên gọi `parser.getValueAsString()` rồi chấp nhận mọi token nếu contract quy định JSON string. Coercion rộng có thể khiến một client gửi `1234` trong khi contract yêu cầu `"1234"` mà vẫn được chấp nhận.

## 4. Tạo value object có cấu trúc

Ví dụ `Money` gồm amount và currency:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public final class Money {
    private final BigDecimal amount;
    private final Currency currency;

    private Money(BigDecimal amount, Currency currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public static Money of(BigDecimal amount, Currency currency) {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");
        return new Money(amount, currency);
    }

    public BigDecimal amount() {
        return amount;
    }

    public Currency currency() {
        return currency;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Money)) return false;
        Money that = (Money) other;
        return amount.compareTo(that.amount) == 0
            && currency.equals(that.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount.stripTrailingZeros(), currency);
    }
}
```

`BigDecimal.equals()` phân biệt scale, ví dụ `125.5` và `125.50` không bằng nhau theo `equals()`, dù giá trị số học bằng nhau. Trong ví dụ, `Money.equals()` dùng `compareTo()` để so sánh giá trị số học và `hashCode()` chuẩn hóa scale bằng `stripTrailingZeros()` để giữ hợp đồng equals/hashCode.

Ví dụ không đặt giới hạn scale cố định vì số chữ số thập phân phụ thuộc currency và domain. Ứng dụng thực tế có thể kiểm tra scale, rounding mode, giá trị âm hoặc giới hạn amount trong factory/service theo quy tắc nghiệp vụ.

## 5. Serializer cho Money object

Representation JSON được chọn:

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Serializer:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;

public final class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject(value);
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField(
            "currency",
            value.currency().getCurrencyCode()
        );
        generator.writeEndObject();
    }
}
```

`writeNumberField()` ghi `BigDecimal` thành JSON number, không biến amount thành chuỗi. Consumer phải hỗ trợ decimal semantics phù hợp. Nếu contract yêu cầu giữ scale hoặc tránh khác biệt numeric handling giữa ngôn ngữ, có thể chọn decimal string hoặc integer minor units thay cho JSON number; phải quyết định trước khi phát hành contract.

## 6. Deserializer cho Money object

Deserializer cần xác nhận root là object, hai field bắt buộc có kiểu phù hợp và currency code hợp lệ.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.Currency;

public final class MoneyDeserializer extends StdDeserializer<Money> {
    public MoneyDeserializer() {
        super(Money.class);
    }

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode node = parser.getCodec().readTree(parser);
        if (node == null || !node.isObject()) {
            return (Money) context.handleUnexpectedToken(Money.class, parser);
        }

        JsonNode amountNode = node.get("amount");
        JsonNode currencyNode = node.get("currency");

        if (amountNode == null || !amountNode.isNumber()) {
            throw JsonMappingException.from(
                parser,
                "Money field 'amount' must be a JSON number"
            );
        }

        if (currencyNode == null || !currencyNode.isTextual()) {
            throw JsonMappingException.from(
                parser,
                "Money field 'currency' must be a JSON string"
            );
        }

        try {
            BigDecimal amount = amountNode.decimalValue();
            Currency currency = Currency.getInstance(currencyNode.textValue());
            return Money.of(amount, currency);
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser,
                "Invalid Money value: " + exception.getMessage(),
                exception
            );
        }
    }
}
```

Deserializer này đọc object thành `JsonNode` rồi kiểm tra field. Cách này dễ viết và phù hợp với object nhỏ. Với payload lớn hoặc cần kiểm soát streaming chặt hơn, có thể đọc token trực tiếp bằng `JsonParser` để tránh tạo tree trung gian.

Lưu ý: custom deserializer tự chịu trách nhiệm kiểm tra cấu trúc mà nó đọc. `FAIL_ON_UNKNOWN_PROPERTIES` không tự động kiểm tra các field bên trong `MoneyDeserializer` như khi Jackson bind một bean thông thường. Nếu contract cần từ chối field lạ, hãy kiểm tra `node.fieldNames()` và reject các key ngoài allowlist. Nếu muốn hỗ trợ extension field, cần định nghĩa rõ cách giữ hoặc bỏ chúng.

## 7. Gom serializer và deserializer trong một SimpleModule

`SimpleModule` là cách thuận tiện để đăng ký serializer/deserializer cho các kiểu cụ thể.

```java
import com.fasterxml.jackson.databind.module.SimpleModule;

public final class DomainValueModule extends SimpleModule {
    public DomainValueModule() {
        super("domain-value-module");

        addSerializer(OrderId.class, new OrderIdSerializer());
        addDeserializer(OrderId.class, new OrderIdDeserializer());

        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
```

Module có một trách nhiệm: định nghĩa cách các domain value types được chuyển đổi qua Jackson. Khi thêm kiểu mới, đăng ký serializer và deserializer tương ứng trong module này hoặc tách module theo bounded context nếu số lượng type lớn.

### 7.1. Đăng ký module với ObjectMapper

Cách trực tiếp:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new DomainValueModule());
```

Hoặc dùng `JsonMapper` builder:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new DomainValueModule())
    .build();
```

Đăng ký module trước khi mapper được sử dụng. Sau khi cấu hình xong, tái sử dụng mapper thay vì thay đổi module theo từng request.

### 7.2. Đừng quên mapper ở từng boundary

Ứng dụng có thể có nhiều mapper/factory:

- Spring MVC JSON `HttpMessageConverter`.
- Kafka/Rabbit message serializer.
- Redis/cache serializer.
- File import/export.
- HTTP client gọi service khác.
- Test fixture utility.

Đăng ký module trên một mapper không làm các mapper độc lập khác tự nhận module. Hãy kiểm tra mọi boundary cần hiểu `OrderId` và `Money`.

### 7.3. Module auto-discovery

`findAndRegisterModules()` tìm các Jackson module được khai báo qua cơ chế service provider trên classpath. Một custom `SimpleModule` không tự được tìm thấy chỉ vì class nằm trong project. Nếu muốn auto-discovery, cần đóng gói module và khai báo provider metadata phù hợp; nếu không, đăng ký tường minh qua Spring configuration hoặc mapper builder.

## 8. Dùng value object trong DTO và nested object

Sau khi module được đăng ký, DTO có thể dùng type domain trực tiếp:

```java
import java.util.List;

public class CreateOrderRequest {
    private OrderId orderId;
    private Money total;
    private List<OrderId> relatedOrders;

    public OrderId getOrderId() {
        return orderId;
    }

    public void setOrderId(OrderId orderId) {
        this.orderId = orderId;
    }

    public Money getTotal() {
        return total;
    }

    public void setTotal(Money total) {
        this.total = total;
    }

    public List<OrderId> getRelatedOrders() {
        return relatedOrders;
    }

    public void setRelatedOrders(List<OrderId> relatedOrders) {
        this.relatedOrders = relatedOrders;
    }
}
```

JSON:

```json
{
  "orderId": "ORD-00001234",
  "total": {
    "amount": 125.50,
    "currency": "USD"
  },
  "relatedOrders": [
    "ORD-00001235",
    "ORD-00001236"
  ]
}
```

Jackson áp dụng serializer/deserializer của `OrderId` cho property đơn lẻ và phần tử collection. `Money` dùng representation object đã định nghĩa. DTO không cần biết regex hoặc currency parsing; invariant nằm trong value object, còn wire mapping nằm trong module.

## 9. Map key cần key serializer và key deserializer riêng

JSON object key luôn là string. Khi một value object được dùng làm key của `Map`, serializer/deserializer thông thường không đủ vì key không được ghi như JSON value; Jackson dùng cơ chế key serializer và key deserializer.

Đăng ký thêm trong module:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.KeyDeserializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public final class OrderIdKeySerializer extends JsonSerializer<OrderId> {
    @Override
    public void serialize(
            OrderId value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {
        generator.writeFieldName(value.value());
    }
}

public final class OrderIdKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context) throws IOException {
        try {
            return OrderId.of(key);
        } catch (IllegalArgumentException exception) {
            throw context.weirdKeyException(
                OrderId.class,
                key,
                "Expected an OrderId in ORD-######## format"
            );
        }
    }
}
```

Đăng ký:

```java
addKeySerializer(OrderId.class, new OrderIdKeySerializer());
addKeyDeserializer(OrderId.class, new OrderIdKeyDeserializer());
```

Khi đó:

```java
Map<OrderId, String> labels = new LinkedHashMap<>();
labels.put(OrderId.of("ORD-00001234"), "priority");
```

có thể được serialize thành:

```json
{
  "ORD-00001234": "priority"
}
```

Không cần key serializer nếu value object chỉ xuất hiện ở vị trí JSON value. Hãy chỉ đăng ký phần mở rộng này khi domain type thực sự được dùng làm map key.

## 10. @JsonValue và @JsonCreator so với custom module

Với một value object đơn giản, Jackson annotation có thể đủ:

```java
public final class OrderId {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public OrderId(String value) {
        this.value = validate(value);
    }

    @JsonValue
    public String value() {
        return value;
    }
}
```

`@JsonValue` chỉ định giá trị được dùng khi serialize object; `@JsonCreator(DELEGATING)` nhận scalar JSON và chuyển thành instance.

| Cách | Phù hợp khi | Trade-off |
|---|---|---|
| `@JsonValue` + `@JsonCreator` | Một type đơn giản, chấp nhận Jackson annotation trong domain type | Domain phụ thuộc Jackson; dễ hiểu và ít code |
| Custom serializer/deserializer | Một type cần logic mapping riêng hoặc kiểm soát token/error rõ | Cần viết và test code chuyển đổi |
| `SimpleModule` | Nhiều type dùng chung policy hoặc domain không muốn phụ thuộc Jackson | Tập trung registration, phải bảo đảm mọi mapper đều cài module |
| Mix-in | Không thể sửa class gốc nhưng muốn gắn metadata Jackson | Cấu hình có thể khó tìm nếu nhiều mix-in |

Không cần tạo module cho mọi scalar wrapper nếu annotation đã đáp ứng contract. Module có lợi khi muốn giữ domain module độc lập với Jackson hoặc muốn gom nhiều mapping thành một integration adapter.

## 11. Kiểm thử serializer: Java value → JSON

Test serializer cần xác nhận đúng wire representation. Đừng chỉ kiểm tra chuỗi output nếu thứ tự field trong object không phải contract.

```java
class DomainValueModuleSerializationTest {
    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new DomainValueModule())
        .build();

    @Test
    void serializesOrderIdAsString() throws Exception {
        String json = mapper.writeValueAsString(
            OrderId.of("ORD-00001234")
        );

        assertEquals("\"ORD-00001234\"", json);
    }

    @Test
    void serializesMoneyAsObject() throws Exception {
        Money money = Money.of(
            new BigDecimal("125.50"),
            Currency.getInstance("USD")
        );

        JsonNode json = mapper.readTree(mapper.writeValueAsBytes(money));

        assertEquals(new BigDecimal("125.50"), json.get("amount").decimalValue());
        assertEquals("USD", json.get("currency").asText());
    }
}
```

Với `OrderId`, scalar JSON string là contract nên so sánh chuỗi chính xác là hợp lý. Với `Money`, test tree theo field/value để không phụ thuộc thứ tự field output.

## 12. Kiểm thử deserializer: JSON → Java value

Kiểm tra input hợp lệ:

```java
class DomainValueModuleDeserializationTest {
    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new DomainValueModule())
        .build();

    @Test
    void deserializesOrderIdFromString() throws Exception {
        OrderId id = mapper.readValue(
            "\"ORD-00001234\"",
            OrderId.class
        );

        assertEquals(OrderId.of("ORD-00001234"), id);
    }

    @Test
    void deserializesMoneyFromObject() throws Exception {
        Money money = mapper.readValue(
            """
            {
              "amount": 125.50,
              "currency": "USD"
            }
            """,
            Money.class
        );

        assertEquals(new BigDecimal("125.50"), money.amount());
        assertEquals(Currency.getInstance("USD"), money.currency());
    }
}
```

Test deserializer độc lập giúp xác định lỗi ở chiều đọc. Nếu chỉ test round-trip và serializer/deserializer cùng sai theo một cách, hai lỗi có thể che lẫn nhau.

## 13. Kiểm thử round-trip hai chiều

Round-trip test xác nhận một value object sau serialize rồi deserialize vẫn bằng giá trị ban đầu:

```java
@Test
void orderIdRoundTrips() throws Exception {
    OrderId original = OrderId.of("ORD-00001234");

    String json = mapper.writeValueAsString(original);
    OrderId restored = mapper.readValue(json, OrderId.class);

    assertEquals(original, restored);
}

@Test
void moneyRoundTrips() throws Exception {
    Money original = Money.of(
        new BigDecimal("125.50"),
        Currency.getInstance("USD")
    );

    byte[] json = mapper.writeValueAsBytes(original);
    Money restored = mapper.readValue(json, Money.class);

    assertEquals(original, restored);
}
```

Round-trip là kiểm tra cần thiết nhưng không đủ. Serializer và deserializer có thể cùng dùng một representation không đúng contract. Vì vậy, cần thêm golden JSON độc lập:

```java
@Test
void readsPublishedOrderIdRepresentation() throws Exception {
    OrderId restored = mapper.readValue(
        "\"ORD-00001234\"",
        OrderId.class
    );

    assertEquals(OrderId.of("ORD-00001234"), restored);
}
```

Golden fixture phải được định nghĩa theo API contract, không được tạo tự động từ serializer đang kiểm thử.

## 14. Kiểm thử nested object và collection

Định nghĩa envelope:

```java
public class OrderEnvelope {
    private OrderId orderId;
    private Money total;
    private List<OrderId> relatedOrders;

    public OrderEnvelope() {
    }

    // Getter và setter
}
```

Test:

```java
@Test
void roundTripsValueObjectsInsideAnotherDto() throws Exception {
    OrderEnvelope original = new OrderEnvelope();
    original.setOrderId(OrderId.of("ORD-00001234"));
    original.setTotal(Money.of(
        new BigDecimal("125.50"), Currency.getInstance("USD")
    ));
    original.setRelatedOrders(List.of(
        OrderId.of("ORD-00001235"),
        OrderId.of("ORD-00001236")
    ));

    byte[] json = mapper.writeValueAsBytes(original);
    OrderEnvelope restored = mapper.readValue(json, OrderEnvelope.class);

    assertEquals(original.getOrderId(), restored.getOrderId());
    assertEquals(original.getTotal(), restored.getTotal());
    assertEquals(original.getRelatedOrders(), restored.getRelatedOrders());
}
```

Test nested quan trọng vì module có thể hoạt động khi serialize trực tiếp một `OrderId` nhưng không được đăng ký trên mapper thực sự dùng cho DTO hoặc generic collection. Test ở cấp envelope xác nhận module áp dụng xuyên suốt object graph.

## 15. Kiểm thử map key

Nếu module có đăng ký key serializer/deserializer, kiểm tra cả hai chiều:

```java
@Test
void roundTripsOrderIdMapKeys() throws Exception {
    Map<OrderId, String> original = new LinkedHashMap<>();
    original.put(OrderId.of("ORD-00001234"), "priority");

    String json = mapper.writeValueAsString(original);

    Map<OrderId, String> restored = mapper.readValue(
        json,
        new TypeReference<Map<OrderId, String>>() {}
    );

    assertEquals(original, restored);
}
```

`TypeReference` giữ generic type để Jackson biết key là `OrderId`. Nếu chỉ truyền `Map.class`, type erasure có thể khiến key được đọc thành `String` thay vì value object.

## 16. Kiểm thử input không hợp lệ

Deserializer là boundary nhận dữ liệu không tin cậy. Hãy test cả JSON type sai và domain value sai.

```java
@Test
void rejectsInvalidOrderIdFormat() {
    assertThrows(JsonMappingException.class,
        () -> mapper.readValue("\"BAD-123\"", OrderId.class));
}

@Test
void rejectsNumberWhenOrderIdRequiresString() {
    assertThrows(JsonMappingException.class,
        () -> mapper.readValue("1234", OrderId.class));
}

@Test
void rejectsMoneyWithMissingCurrency() {
    assertThrows(JsonMappingException.class,
        () -> mapper.readValue(
            "{\"amount\":125.50}",
            Money.class
        ));
}

@Test
void rejectsUnknownCurrencyCode() {
    assertThrows(JsonMappingException.class,
        () -> mapper.readValue(
            "{\"amount\":10,\"currency\":\"NOT_A_CURRENCY\"}",
            Money.class
        ));
}
```

Kiểu exception cụ thể có thể được wrap theo context khi deserialize nested property. Trong test endpoint, có thể cần assert exception cấp cao hơn như `HttpMessageNotReadableException` do Spring bọc lỗi Jackson.

## 17. Null và missing property

Jackson mặc định xử lý JSON `null` riêng với serializer/deserializer của non-null value. Với property value object:

```json
{
  "orderId": null
}
```

custom `OrderIdDeserializer.deserialize()` thường không được gọi cho token null; Jackson dùng null handling của deserializer/context. Nếu null không hợp lệ trong DTO, đặt `@NotNull`/validation hoặc dùng custom null provider theo nhu cầu.

Hai trường hợp cần phân biệt:

```json
{}
```

và:

```json
{"orderId":null}
```

Với Java bean thông thường, cả hai có thể cho property `null` sau binding. Nếu API cần phân biệt absent với explicit null, dùng presence wrapper hoặc JSON Patch/Merge Patch semantics; một custom value deserializer đơn thuần không khôi phục được thông tin key đã vắng mặt.

Test null policy riêng:

```java
@Test
void readsExplicitNullAsNullByDefault() throws Exception {
    OrderId id = mapper.readValue("null", OrderId.class);
    assertNull(id);
}
```

Nếu domain không cho phép null, hãy kiểm tra tại DTO/service boundary thay vì làm serializer/deserializer non-null type tự nhận trách nhiệm cho mọi field presence.

## 18. Kiểm thử custom module với Spring Boot

Trong Spring Boot, cần đăng ký module trên `ObjectMapper` được HTTP message converter sử dụng. Một cách là khai báo `Module` bean:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public Module domainValueModule() {
        return new DomainValueModule();
    }
}
```

Spring Boot thường tự đăng ký các bean Jackson `Module` vào mapper auto-configured. Cơ chế và điều kiện cụ thể phụ thuộc Spring Boot version và cấu hình tùy biến của ứng dụng. Nếu ứng dụng tự khai báo `ObjectMapper` bean hoặc `Jackson2ObjectMapperBuilder`, hãy xác nhận module vẫn được thêm vào mapper cuối cùng.

Test bean mapper:

```java
@SpringBootTest
class SpringDomainValueModuleTest {
    @Autowired
    ObjectMapper objectMapper;

    @Test
    void springManagedMapperUsesDomainValueModule() throws Exception {
        OrderId id = objectMapper.readValue(
            "\"ORD-00001234\"",
            OrderId.class
        );

        assertEquals(OrderId.of("ORD-00001234"), id);
    }
}
```

Test này kiểm tra mapper thực tế được inject trong ứng dụng. Không chỉ test `new ObjectMapper()` riêng nếu production dùng Spring-managed mapper.

### 18.1. Test HTTP boundary

Có thể dùng `@WebMvcTest`/`MockMvc` để kiểm tra request DTO chứa value object được bind đúng:

```java
@WebMvcTest(OrderController.class)
class OrderControllerJsonTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void acceptsOrderIdInPublishedScalarFormat() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "orderId": "ORD-00001234"
                    }
                    """))
            .andExpect(status().is2xxSuccessful());
    }
}
```

Ví dụ cần controller/request DTO và mock service tương ứng trong project. `@MockBean` có thể được thay bằng API mock bean phù hợp với Spring Boot version. Mục tiêu là xác nhận `HttpMessageConverter` dùng module đúng.

## 19. Kiểm thử module độc lập với application

Nên có unit test cho module không phụ thuộc Spring:

- Serializer của từng value type.
- Deserializer của từng value type.
- Round-trip.
- Nested property và collection.
- Map key nếu hỗ trợ.
- Null/missing policy.
- Input sai type và sai domain value.

Sau đó có integration test cho mapper production và HTTP/message boundary. Unit test chứng minh module hoạt động; integration test chứng minh module đã được đăng ký đúng nơi.

## 20. Module registration order và xung đột serializer

Một `ObjectMapper` có thể được đăng ký nhiều module. Nếu hai module cùng đăng ký serializer cho một kiểu, kết quả phụ thuộc cơ chế đăng ký/priority và cách mapper xây dựng serializer cache. Không nên để nhiều module cạnh tranh cùng một type mà không có chủ đích.

Nguyên tắc:

- Mỗi value type nên có một serializer/deserializer canonical cho wire contract.
- Đăng ký module tập trung ở mapper factory/configuration.
- Tránh vừa gắn `@JsonSerialize` trên type/property vừa đăng ký serializer khác cho cùng type nếu không hiểu precedence.
- Khi đổi module, tạo mapper mới hoặc khởi tạo lại context; không thay module trên mapper đang được dùng.
- Test mapper cuối cùng sau khi tất cả module đã được đăng ký.

Nếu một endpoint cần representation khác cho cùng domain type, có thể dùng DTO adapter, property-level serializer hoặc mapper riêng có contract rõ ràng. Không thay đổi global serializer để phục vụ một endpoint đơn lẻ.

## 21. Generic value types và type erasure

`SimpleModule.addSerializer(MyType.class, ...)` phù hợp với kiểu cụ thể. Với generic wrapper như `Value<T>`, Java type erasure làm runtime không luôn biết `T` là kiểu nào.

Ví dụ:

```java
public final class Box<T> {
    private final T value;
    public Box(T value) { this.value = value; }
    public T value() { return value; }
}
```

Nếu serializer cần biết generic parameter để chọn representation, có thể cần:

- `ContextualSerializer`/`ContextualDeserializer` để lấy property/type context.
- `ResolvableSerializer` hoặc cơ chế resolution khi phụ thuộc serializer lồng nhau.
- `Serializers`/`Deserializers` provider đăng ký theo `JavaType`.
- `TypeReference`/`JavaType` khi gọi `readValue()` với generic root type.

Đừng đăng ký một serializer cho `Object.class` chỉ để xử lý mọi wrapper. Nó có thể chiếm quyền xử lý quá rộng và làm hỏng các kiểu khác. Với domain value type không generic, đăng ký theo concrete class thường đơn giản và an toàn hơn.

## 22. Versioning wire representation của value object

Khi đã phát hành JSON representation, nó trở thành contract. Ví dụ đổi `OrderId` từ string:

```json
"ORD-00001234"
```

sang object:

```json
{
  "value": "ORD-00001234"
}
```

là breaking change với consumer đang mong string. Tương tự, đổi `Money.amount` từ number sang string hoặc đổi tên `currency` thành `currencyCode` cũng có thể phá consumer.

Trước khi thay representation:

- Giữ fixture JSON cũ.
- Xác định reader mới có thể nhận cả dạng cũ và mới không.
- Xác định writer mới có cần tiếp tục ghi dạng cũ trong thời gian migration không.
- Version hóa API/message nếu hai dạng không thể cùng hỗ trợ an toàn.
- Kiểm thử consumer ở ngôn ngữ khác, không chỉ Java round-trip.

Một deserializer có thể hỗ trợ nhiều dạng input tạm thời, nhưng cần quy định writer chỉ phát một dạng canonical. Tránh để output thay đổi tùy input cũ vừa đọc.

## 23. Đo lường và giới hạn trách nhiệm của custom module

Custom module nên tập trung vào representation và conversion. Không đưa truy vấn database, authorization hoặc logic workflow vào serializer/deserializer.

Không nên:

- Tra cứu entity trong database khi deserialize `CustomerId`.
- Gọi service bên ngoài khi serialize `Money`.
- Đọc request context hoặc security principal trong serializer dùng chung.
- Tạo side effect khi đọc JSON.
- Dùng serializer để thay thế validation nghiệp vụ.

Serializer/deserializer có thể được cache và tái sử dụng trong nhiều request. Hãy giữ chúng stateless hoặc thread-safe, không lưu mutable request-specific state trong field.

Validation cú pháp và invariant của value object có thể nằm trong deserializer/factory. Kiểm tra nghiệp vụ cần trạng thái hệ thống nên được thực hiện sau binding trong service/domain layer.

## 24. Những lỗi thường gặp

**Tạo value object nhưng không override equals/hashCode.** Round-trip tạo instance mới nên so sánh identity sẽ fail dù giá trị giống nhau. Implement value equality.

**Serializer ghi object trong khi contract yêu cầu scalar string.** JSON shape là một phần API contract. Test exact scalar/object representation.

**Deserializer chỉ chuyển chuỗi mà không gọi factory validation.** Dữ liệu không hợp lệ có thể tạo value object sai invariant. Dùng factory/constructor có kiểm tra.

**Chấp nhận mọi JSON token qua coercion.** Nếu contract yêu cầu string, từ chối number/boolean/object thay vì chuyển chúng thành text.

**Quên đăng ký deserializer.** Serialize có thể thành công nhưng đọc lại fail hoặc dùng default bean mapping. Test cả hai chiều.

**Chỉ đăng ký module trên mapper trong unit test.** Mapper Spring, Kafka hoặc cache có thể khác. Test mọi boundary cần module.

**Dùng value serializer cho map key.** JSON object key cần key serializer/key deserializer riêng.

**Cho rằng FAIL_ON_UNKNOWN_PROPERTIES kiểm tra field trong custom deserializer.** Custom deserializer tự đọc node/token và phải tự định nghĩa unknown-field policy.

**Giả định null đi qua deserialize() như string token.** Jackson có null handling riêng. Xác định null policy và validate required property ở đúng lớp.

**Dùng custom module để chứa logic nghiệp vụ hoặc I/O.** Module nên chuyển representation; service/domain xử lý trạng thái bên ngoài.

**Chỉ test round-trip.** Serializer và deserializer có thể cùng sai theo một contract. Thêm golden input/output độc lập và test semantics.

**Đổi wire shape mà không version hóa.** String thành object hoặc number thành string là thay đổi contract. Có migration/alias hoặc version API/message.

## 25. Quy trình triển khai module cho value types

1. Xác định value object và invariant của nó trong domain.
2. Chọn wire representation rõ ràng: scalar hay structured object.
3. Giữ constructor/factory của value object chịu trách nhiệm invariant, không phụ thuộc Jackson nếu kiến trúc yêu cầu.
4. Viết serializer cho chiều Java → JSON.
5. Viết deserializer cho chiều JSON → Java, kiểm tra token type và domain value.
6. Với structured value, kiểm tra required fields, field types và unknown-field policy.
7. Đăng ký cặp serializer/deserializer trong `SimpleModule`.
8. Nếu type dùng làm JSON map key, đăng ký key serializer/key deserializer riêng.
9. Thêm module vào tất cả mapper/factory thực sự dùng type đó.
10. Test serialize, deserialize, round-trip, nested collection, map key, null và invalid input.
11. Thêm golden fixtures độc lập để xác nhận wire contract.
12. Test mapper Spring/HTTP/message thực tế.
13. Version hóa representation nếu thay đổi sau khi đã phát hành.
14. Giữ serializer/deserializer stateless, không thực hiện I/O hoặc side effect.

## Kết luận

Jackson module cho phép định nghĩa tập trung cách value object được chuyển đổi giữa Java và JSON mà không buộc domain class phải phụ thuộc annotation Jackson. `SimpleModule` đăng ký serializer/deserializer theo kiểu cụ thể; scalar value như `OrderId` có thể được ghi thành string, còn structured value như `Money` có thể được ghi thành object. Deserializer phải kiểm tra JSON token, gọi factory bảo vệ invariant và báo lỗi rõ khi input sai. Nếu value object dùng làm map key, cần key serializer/deserializer riêng. Kiểm thử phải bao gồm từng chiều độc lập, round-trip, golden representation, nested DTO, collection, null, missing và invalid input; sau đó xác nhận module được đăng ký trên mapper Spring hoặc transport thực tế. Giữ module stateless và chỉ chịu trách nhiệm chuyển đổi representation để domain/service tiếp tục quản lý invariant và nghiệp vụ.

## Tài liệu tham khảo

- [Jackson Databind — Custom Serializers and Deserializers](https://github.com/FasterXML/jackson-databind) — API serializer/deserializer và data binding.
- [Jackson Module API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/module/SimpleModule.html) — đăng ký serializer, deserializer và key handlers bằng `SimpleModule`.
- [Jackson JsonSerializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonSerializer.html) — contract của serializer.
- [Jackson JsonDeserializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonDeserializer.html) — contract của deserializer.
- [Spring Boot JSON support](https://docs.spring.io/spring-boot/reference/features/json.html) — tích hợp Jackson mapper và module trong Spring Boot.
