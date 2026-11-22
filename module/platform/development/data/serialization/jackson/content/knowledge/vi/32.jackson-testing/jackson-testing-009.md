# Kiểm thử serializer, deserializer và module tùy biến

Khi Jackson chuyển đổi một Java object thành JSON hoặc đọc JSON thành Java object, nó sử dụng serializer và deserializer tương ứng với kiểu dữ liệu. Serializer quyết định cách ghi giá trị ra token/JSON; deserializer quyết định cách đọc token và tạo giá trị Java. Khi định dạng mặc định không đáp ứng hợp đồng dữ liệu, ứng dụng có thể viết serializer/deserializer riêng và đăng ký chúng qua Jackson module.

Custom serializer/deserializer là code thực thi trong đường xử lý dữ liệu. Vì vậy, chỉ kiểm tra rằng class đã compile hoặc module đã đăng ký là chưa đủ. Cần kiểm thử hợp đồng JSON ở cả hai chiều, giá trị biên, token sai kiểu, null, object lồng nhau, collection, lỗi chuyển đổi và mapper thực tế của ứng dụng. Với module tùy biến, cần xác nhận mapper sử dụng đúng handler và các cấu hình khác không vô tình ghi đè hành vi mong đợi.

Bài học sử dụng Jackson 2.x, Java 17 và JUnit 5. Các ví dụ dùng `com.fasterxml.jackson`. Nếu dự án dùng Jackson 3.x, hãy đối chiếu API/package và module compatibility của đúng major version trước khi áp dụng.

## 1. Phân biệt serializer, deserializer và module

Một serializer chuyển Java value thành JSON token:

```text
Java value
    |
    v
JsonSerializer<T>
    |
    v
JsonGenerator
    |
    v
JSON output
```

Deserializer thực hiện chiều ngược lại:

```text
JSON input
    |
    v
JsonParser
    |
    v
JsonDeserializer<T>
    |
    v
Java value
```

Module là đơn vị đóng gói cấu hình Databind. Một module có thể đăng ký serializer, deserializer, key serializer/deserializer, subtype, mix-in, modifier hoặc các extension point khác.

| Thành phần | Trách nhiệm |
|---|---|
| `JsonSerializer<T>` | Ghi một giá trị Java kiểu `T` ra JSON |
| `JsonDeserializer<T>` | Đọc JSON token và tạo giá trị Java kiểu `T` |
| `SimpleModule` | Đăng ký các handler và cấu hình Databind thông dụng |
| `ObjectMapper` | Quản lý cấu hình, serializer/deserializer cache và thao tác đọc/ghi |
| `ObjectReader` / `ObjectWriter` | Đóng gói cấu hình đọc/ghi bất biến cho use case cụ thể |

Một test tốt cần chứng minh kết quả quan sát được: JSON có đúng hình dạng/giá trị không, object sau deserialize có đúng không và lỗi được phát hiện đúng khi input không hợp lệ.

## 2. Tổ chức code ví dụ: kiểu `Money`

Giả sử API muốn biểu diễn tiền dưới dạng một chuỗi duy nhất:

```json
"VND 1500.00"
```

Trong Java, ta muốn dùng value object gồm currency và amount thay vì nối chuỗi ở mọi nơi:

```java
import java.math.BigDecimal;

public record Money(String currency, BigDecimal amount) {
}
```

Quy ước wire format:

- Currency là mã gồm ba chữ cái in hoa, ví dụ `VND`, `USD`, `EUR`.
- Có đúng một dấu cách giữa currency và amount.
- Amount dùng biểu diễn decimal với dấu chấm, không dùng dấu phân cách hàng nghìn.
- Giá trị được serialize bằng `BigDecimal.toPlainString()` để tránh scientific notation.

Ví dụ:

| Java value | JSON |
|---|---|
| `new Money("VND", new BigDecimal("1500.00"))` | `"VND 1500.00"` |
| `new Money("USD", new BigDecimal("12.5"))` | `"USD 12.5"` |

Đây là một hợp đồng do ứng dụng định nghĩa. Nếu API cần biểu diễn currency và amount thành object JSON, hãy dùng object serializer thông thường thay vì ép mọi thứ thành chuỗi.

## 3. Viết custom serializer

Custom serializer kế thừa `JsonSerializer<T>` và triển khai `serialize()`:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public final class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(Money value,
                          JsonGenerator generator,
                          SerializerProvider provider) throws IOException {
        String text = value.currency() + " " + value.amount().toPlainString();
        generator.writeString(text);
    }
}
```

Serializer không cần tự tạo dấu ngoặc kép hoặc escape JSON. `JsonGenerator.writeString()` chịu trách nhiệm ghi một JSON string hợp lệ, bao gồm escaping ký tự cần thiết.

Không làm:

```java
generator.writeRaw("\"" + value.currency() + " " + value.amount() + "\"");
```

`writeRaw()` bỏ qua một phần bảo vệ của generator. Nếu giá trị chứa dấu quote, backslash hoặc ký tự điều khiển, code tự nối chuỗi có thể tạo JSON sai hoặc lỗ hổng injection. Hãy dùng API typed của `JsonGenerator` như `writeString`, `writeNumber`, `writeStartObject`, `writeFieldName` và `writeEndObject`.

### 3.1. Xác định trách nhiệm của serializer

Serializer nên tập trung vào việc biểu diễn giá trị thành JSON. Nó không nên:

- Gọi database hoặc HTTP service.
- Thực hiện transaction hay thay đổi trạng thái nghiệp vụ.
- Đọc file hoặc gọi shell command.
- Lấy user hiện tại từ global mutable state.
- Thay đổi object đang serialize.

Nếu output phụ thuộc ngữ cảnh, dùng cơ chế Jackson phù hợp như contextual serializer, provider attribute hoặc DTO/output model được tạo trước khi serialize. Không đưa side effect vào serializer vì serializer có thể được cache và gọi ở nhiều luồng.

## 4. Viết custom deserializer

Deserializer đọc token hiện tại từ `JsonParser`, kiểm tra loại token rồi chuyển đổi thành Java value.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MoneyDeserializer extends JsonDeserializer<Money> {
    private static final Pattern FORMAT = Pattern.compile(
            "^([A-Z]{3}) ([+-]?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?)$");

    @Override
    public Money deserialize(JsonParser parser,
                             DeserializationContext context) throws IOException {
        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                    parser,
                    "Money must be represented as a JSON string");
        }

        String text = parser.getText();
        Matcher matcher = FORMAT.matcher(text);
        if (!matcher.matches()) {
            throw JsonMappingException.from(
                    parser,
                    "Expected money in the form 'CCC amount'");
        }

        try {
            String currency = matcher.group(1);
            BigDecimal amount = new BigDecimal(matcher.group(2));
            return new Money(currency, amount);
        } catch (NumberFormatException exception) {
            throw JsonMappingException.from(
                    parser,
                    "Invalid decimal amount in money value",
                    exception);
        }
    }
}
```

Deserializer kiểm tra `JsonToken.VALUE_STRING` trước khi đọc text. Nếu input là number, object hoặc array, nó báo mapping error có vị trí parser thay vì cố chuyển đổi ngầm.

Regex trong ví dụ chỉ là format minh họa. Trong hệ thống thật, hãy quyết định có chấp nhận số âm, số 0, số chữ số thập phân, currency nào và whitespace ra sao. Kiểm tra format và quy tắc nghiệp vụ là hai việc khác nhau: serializer/deserializer có thể đảm bảo cú pháp wire format, còn giới hạn số tiền hoặc currency được phép nên thuộc validation/domain layer.

### 4.1. Phân biệt parse error và mapping error

Nếu JSON thiếu dấu ngoặc hoặc dấu quote, Jackson Core parser có thể ném `JsonParseException`. Nếu JSON hợp lệ nhưng token không phù hợp với `MoneyDeserializer`, lỗi thường là `JsonMappingException` hoặc subtype.

Ví dụ:

```json
"VND 1500.00"
```

là JSON hợp lệ và đúng custom format.

```json
1500
```

là JSON hợp lệ nhưng sai token type mà deserializer yêu cầu.

```text
"VND 1500.00
```

là JSON syntax sai. Không nên bắt tất cả lỗi bằng một exception tùy ý rồi báo rằng custom deserializer đã thất bại; hãy giữ được sự phân biệt giữa parser và mapping.

## 5. Đóng gói serializer/deserializer trong `SimpleModule`

Tạo module:

```java
import com.fasterxml.jackson.databind.module.SimpleModule;

public final class MoneyModule extends SimpleModule {

    public MoneyModule() {
        super("money-module");
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
```

Đăng ký module trên mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new MoneyModule());
```

Từ đó, khi Databind gặp `Money`, mapper có thể chọn serializer/deserializer đã đăng ký.

Module nên được cấu hình ở một nơi tập trung, ví dụ mapper configuration của ứng dụng. Không đăng ký module cho từng request và không thay đổi mapper sau khi nó đã được chia sẻ cho nhiều luồng.

### 5.1. Đăng ký nhiều handler trong một module

Một module có thể đăng ký nhiều kiểu:

```java
public final class DomainJsonModule extends SimpleModule {
    public DomainJsonModule() {
        super("domain-json-module");
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
        addSerializer(PhoneNumber.class, new PhoneNumberSerializer());
        addDeserializer(PhoneNumber.class, new PhoneNumberDeserializer());
    }
}
```

Gom các handler có cùng mục đích giúp việc đăng ký và kiểm thử cấu hình đơn giản hơn. Tuy nhiên, đừng tạo một module khổng lồ không có ranh giới rõ ràng; có thể tách module theo domain hoặc integration.

### 5.2. `SimpleModule` phù hợp khi nào?

`SimpleModule` phù hợp với đăng ký theo kiểu cụ thể, ví dụ `Money.class`, `PhoneNumber.class` hoặc `LegacyStatus.class`.

Với generic type cần phân biệt `Box<String>` và `Box<Integer>`, đăng ký serializer/deserializer theo raw class có thể không đủ vì cả hai có cùng raw type `Box.class`. Khi cần lựa chọn theo `JavaType`/generic parameter, dùng extension point nâng cao như `Serializers`, `Deserializers`, `BeanSerializerModifier` hoặc `BeanDeserializerModifier`, hay thiết kế value type riêng để handler không phải đoán generic argument.

## 6. Kiểm thử serializer qua output JSON

Dùng JUnit 5:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class MoneyModuleTest {
    private ObjectMapper mapper;

    @BeforeEach
    void setUp() {
        mapper = new ObjectMapper();
        mapper.registerModule(new MoneyModule());
    }

    @Test
    void serializesMoneyAsCanonicalString() throws Exception {
        Money money = new Money("VND", new BigDecimal("1500.00"));

        String json = mapper.writeValueAsString(money);
        JsonNode node = mapper.readTree(json);

        assertTrue(node.isTextual());
        assertEquals("VND 1500.00", node.asText());
    }
}
```

Test parse output thành `JsonNode` để xác nhận đây là JSON string, không chỉ kiểm tra nội dung trông giống chuỗi. Nếu serializer vô tình ghi `1500.00` thành JSON number hoặc object, assertion kiểu node sẽ phát hiện.

Có thể kiểm tra chuỗi JSON chính xác khi format string là wire contract, nhưng cấu trúc/type assertion thường bền vững hơn trước thay đổi whitespace hoặc formatting không liên quan.

## 7. Kiểm thử deserializer với input hợp lệ

```java
@Test
void deserializesCanonicalMoneyString() throws Exception {
    Money money = mapper.readValue("\"VND 1500.00\"", Money.class);

    assertEquals("VND", money.currency());
    assertEquals(new BigDecimal("1500.00"), money.amount());
}
```

Kiểm tra từng thành phần giúp test chỉ ra lỗi nằm ở currency hay amount. `BigDecimal.equals()` có phân biệt scale, vì vậy `1500.00` khác `1500.0` theo equality. Nếu hợp đồng chỉ quan tâm giá trị số học, dùng `compareTo()`:

```java
assertEquals(0, money.amount().compareTo(new BigDecimal("1500.0")));
```

Nếu scale là một phần của hợp đồng tiền tệ, hãy giữ assertion scale cụ thể. Không chuẩn hóa scale tùy tiện trong test vì điều đó có thể che mất khác biệt quan trọng của dữ liệu tài chính.

## 8. Kiểm thử round-trip

Round-trip kiểm tra một value được serialize rồi deserialize có trở lại đúng giá trị cần thiết không:

```java
@Test
void roundTripsMoney() throws Exception {
    Money original = new Money("USD", new BigDecimal("12.50"));

    byte[] json = mapper.writeValueAsBytes(original);
    Money restored = mapper.readValue(json, Money.class);

    assertEquals(original, restored);
}
```

Round-trip hữu ích khi serializer và deserializer được thiết kế thành một cặp cho cùng wire format. Tuy nhiên, nó không thay thế test độc lập:

- Serializer và deserializer có thể cùng sai theo một cách đối xứng.
- Cả hai có thể cùng chấp nhận một format không đúng contract.
- Một test round-trip không chứng minh payload do client cũ gửi vẫn đọc được.
- Một test round-trip không kiểm tra lỗi khi input sai kiểu hoặc sai format.

Vì vậy, cần có test output canonical, test input canonical, test round-trip và test negative riêng.

## 9. Kiểm thử token sai kiểu và format không hợp lệ

Custom deserializer nên từ chối input không đúng contract:

```java
@Test
void rejectsNumberToken() {
    assertThrows(JsonMappingException.class,
            () -> mapper.readValue("1500", Money.class));
}

@Test
void rejectsMalformedMoneyText() {
    assertThrows(JsonMappingException.class,
            () -> mapper.readValue("\"1500 VND\"", Money.class));
}

@Test
void rejectsUnknownCurrencyShape() {
    assertThrows(JsonMappingException.class,
            () -> mapper.readValue("\"VN 1500.00\"", Money.class));
}
```

Các test này xác nhận parser không tự coercion một JSON number thành string hoặc chấp nhận chuỗi không đúng format.

### 9.1. Test malformed JSON riêng

```java
@Test
void malformedJsonFailsBeforeMoneyDeserializerCanReadValue() {
    assertThrows(JsonProcessingException.class,
            () -> mapper.readValue("\"VND 1500.00", Money.class));
}
```

Lỗi cú pháp có thể phát sinh trước khi custom deserializer được gọi. Nếu cần xác nhận riêng loại lỗi, bắt `JsonParseException` theo version Jackson đang dùng. Không gộp test này vào nhóm invalid money format.

### 9.2. Kiểm tra thông tin path khi deserialize property lồng nhau

Ví dụ:

```java
public record Invoice(Money total) {
}
```

Input:

```json
{
  "total": "1500 VND"
}
```

Jackson có thể bọc lỗi ở property `total`. Test có thể kiểm tra path/reference chain:

```java
@Test
void reportsInvalidNestedMoneyProperty() {
    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue("{\"total\":\"1500 VND\"}", Invoice.class));

    assertFalse(exception.getPath().isEmpty());
    assertEquals("total", exception.getPath().get(0).getFieldName());
}
```

Không phụ thuộc toàn bộ exception message vì wording có thể thay đổi giữa Jackson version. Path và exception type thường ổn định hơn cho mục đích test.

## 10. Kiểm thử null semantics

Thông thường, Jackson xử lý JSON `null` qua null value provider; `deserialize()` của custom deserializer không nhất thiết được gọi cho token null. Mặc định, `null` cho reference type sẽ trở thành Java `null`, trừ khi có cấu hình/annotation null handling khác.

Test:

```java
@Test
void mapsJsonNullToJavaNullByDefault() throws Exception {
    Money money = mapper.readValue("null", Money.class);
    assertNull(money);
}

@Test
void writesNullAsJsonNull() throws Exception {
    String json = mapper.writeValueAsString(null);
    assertEquals("null", json);
}
```

Nếu cần custom null semantics cho kiểu cụ thể, có thể override `getNullValue(DeserializationContext)` hoặc cấu hình null handling ở property bằng annotation/configuration phù hợp. Hãy test riêng null ở root và null ở nested property vì property-level setting có thể khác default toàn mapper.

Không dùng `deserialize()` để giả định nó sẽ nhận mọi trường hợp null. Nếu logic cần phân biệt field bị thiếu với field explicit null, DTO thông thường có thể chưa đủ; cần biểu diễn trạng thái absent/null/value bằng kiểu hoặc deserializer chuyên biệt.

## 11. Kiểm thử custom handler trong object lồng nhau

Module đăng ký theo kiểu `Money.class` nên được áp dụng cả khi `Money` là property của một object khác:

```java
public record Invoice(String id, Money total) {
}
```

Test serialize:

```java
@Test
void usesMoneySerializerForNestedProperty() throws Exception {
    Invoice invoice = new Invoice(
            "INV-100",
            new Money("VND", new BigDecimal("1500.00")));

    JsonNode json = mapper.readTree(mapper.writeValueAsString(invoice));

    assertEquals("INV-100", json.path("id").asText());
    assertTrue(json.path("total").isTextual());
    assertEquals("VND 1500.00", json.path("total").asText());
}
```

Test deserialize:

```java
@Test
void usesMoneyDeserializerForNestedProperty() throws Exception {
    Invoice invoice = mapper.readValue(
            """
            {"id":"INV-100","total":"VND 1500.00"}
            """,
            Invoice.class);

    assertEquals("INV-100", invoice.id());
    assertEquals(new Money("VND", new BigDecimal("1500.00")), invoice.total());
}
```

Đây là test quan trọng vì ứng dụng hiếm khi serialize mọi value object ở root. Phần lớn custom type xuất hiện trong DTO, collection, map hoặc object graph lồng nhau.

## 12. Kiểm thử collection và map

Custom serializer/deserializer theo kiểu có thể được áp dụng cho từng phần tử collection:

```java
@Test
void serializesMoneyCollection() throws Exception {
    List<Money> values = List.of(
            new Money("VND", new BigDecimal("100")),
            new Money("USD", new BigDecimal("2.50")));

    JsonNode json = mapper.readTree(mapper.writeValueAsString(values));

    assertTrue(json.isArray());
    assertEquals("VND 100", json.get(0).asText());
    assertEquals("USD 2.50", json.get(1).asText());
}
```

Deserialize collection:

```java
@Test
void deserializesMoneyCollection() throws Exception {
    List<Money> values = mapper.readValue(
            "[\"VND 100\",\"USD 2.50\"]",
            new TypeReference<List<Money>>() {});

    assertEquals(2, values.size());
    assertEquals("VND", values.get(0).currency());
    assertEquals("USD", values.get(1).currency());
}
```

Với map, cần phân biệt map value và map key. `addSerializer(Money.class, ...)` đăng ký serializer cho value kiểu `Money`; nó không tự biến `Money` thành JSON object key. JSON object key là string, vì vậy nếu `Money` được dùng làm key, cần key serializer/deserializer riêng và một quy ước chuỗi key rõ ràng.

## 13. Kiểm thử key serializer và key deserializer

Giả sử map dùng `CurrencyCode` làm key. Module có thể đăng ký:

```java
addKeySerializer(CurrencyCode.class, new CurrencyCodeKeySerializer());
addKeyDeserializer(CurrencyCode.class, new CurrencyCodeKeyDeserializer());
```

Serializer key thường ghi tên field qua `JsonGenerator.writeFieldName(...)`; key deserializer nhận tên field từ parser/context. Test cần xác nhận:

- Key được ghi thành tên JSON mong muốn.
- Key hợp lệ được đọc lại đúng kiểu.
- Key sai format bị từ chối.
- Hai key khác nhau không bị chuẩn hóa thành cùng một chuỗi gây ghi đè.

Không kiểm thử key serializer bằng `writeValueAsString(key)` vì API đó kiểm tra scalar serializer, không phải map key serializer. Hãy đặt key trong `Map<CurrencyCode, Value>` rồi serialize/deserialize map để đi qua đúng extension point.

## 14. Kiểm thử module registration

Một module có thể compile nhưng chưa được đăng ký vào mapper production. Test cần chứng minh mapper thực tế sử dụng handler:

```java
@Test
void registeredModuleControlsMoneyWireFormat() throws Exception {
    ObjectMapper configuredMapper = new ObjectMapper()
            .registerModule(new MoneyModule());

    String json = configuredMapper.writeValueAsString(
            new Money("EUR", new BigDecimal("9.99")));

    assertEquals("\"EUR 9.99\"", json);
}
```

Nếu module không được đăng ký, Jackson có thể xử lý `Money` theo bean introspection hoặc báo lỗi tùy kiểu/model. Assertion output canonical xác nhận module đã thực sự tham gia.

### 14.1. Module ID và đăng ký lặp

Đặt tên module có ý nghĩa:

```java
super("money-module");
```

Tên module giúp chẩn đoán và hỗ trợ cơ chế đăng ký module của Jackson. Nếu dùng `MapperFeature.IGNORE_DUPLICATE_MODULE_REGISTRATIONS`, module có type ID trùng có thể bị bỏ qua theo cấu hình. Không dựa vào việc đăng ký lặp để thay thế handler cũ; hãy tạo mapper với một cấu hình cuối cùng rõ ràng và test module được chọn.

### 14.2. Đăng ký qua `findAndRegisterModules()`

`ObjectMapper.findAndRegisterModules()` tìm module qua cơ chế service loading. Cách này tiện nếu dependency cung cấp service metadata và môi trường runtime giữ lại metadata đó.

Tuy nhiên, test không nên phụ thuộc ngầm vào classpath nếu module là một phần bắt buộc của contract. Với module nghiệp vụ quan trọng, đăng ký tường minh trong mapper configuration thường dễ đọc và dễ kiểm soát hơn. Nếu production chủ đích dùng auto-discovery, hãy có integration test xác nhận mapper production đã nạp module.

## 15. Kiểm thử annotation-level serializer/deserializer

Ngoài đăng ký toàn kiểu qua module, Jackson cho phép chỉ định handler ở class hoặc property bằng annotation:

```java
public class LegacyRecord {
    @JsonSerialize(using = LegacyCodeSerializer.class)
    @JsonDeserialize(using = LegacyCodeDeserializer.class)
    private LegacyCode code;

    // getter và setter
}
```

Test cần xác nhận property đó dùng custom handler và property cùng kiểu ở nơi khác có giữ policy mặc định/module policy mong muốn không.

Annotation-level handler hữu ích khi format chỉ đúng cho một property. Module registration hữu ích khi kiểu value có cùng wire representation ở mọi nơi. Tránh dùng annotation và module để khai báo hai format khác nhau cho cùng một vị trí mà không có test thể hiện rõ handler nào được ưu tiên.

## 16. Kiểm thử custom deserializer khi token sai cấu trúc

Deserializer cho một scalar nên kiểm tra token type. Deserializer cho object cần kiểm tra field name và token boundary:

```java
@Override
public Coordinate deserialize(JsonParser parser,
                              DeserializationContext context) throws IOException {
    if (!parser.isExpectedStartObjectToken()) {
        return (Coordinate) context.handleUnexpectedToken(
                Coordinate.class, parser);
    }

    Integer x = null;
    Integer y = null;

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        parser.nextToken();

        if ("x".equals(fieldName)) {
            x = parser.getIntValue();
        } else if ("y".equals(fieldName)) {
            y = parser.getIntValue();
        } else {
            context.handleUnknownProperty(
                    parser, this, Coordinate.class, fieldName);
        }
    }

    if (x == null || y == null) {
        throw JsonMappingException.from(parser, "Coordinate requires x and y");
    }

    return new Coordinate(x, y);
}
```

Đây là skeleton minh họa; triển khai production cần xử lý `END_OBJECT`/end-of-input, null, duplicate field, unknown property và coercion đúng policy. Với phần lớn object thông thường, nên để Jackson tạo bean/record bằng default deserializer và chỉ custom hóa property thực sự có format đặc biệt. Viết lại toàn bộ object binding làm tăng trách nhiệm và nguy cơ bỏ sót feature của Databind.

Test negative nên bao gồm:

- Root token không phải object.
- Field bắt buộc bị thiếu.
- Field có token sai kiểu.
- Field không biết.
- Field lặp.
- JSON kết thúc giữa chừng.
- Giá trị vượt phạm vi Java type.

## 17. Kiểm thử deserializer có contextual behavior

Một deserializer có thể triển khai `ContextualDeserializer` nếu cách đọc phụ thuộc annotation hoặc generic type của property. Khi đó, test chỉ gọi `readValue()` ở root có thể chưa bao phủ contextual path.

Ví dụ, một `FlexibleCodeDeserializer` có thể đọc cùng kiểu `Code` theo pattern khác nhau tùy property annotation. Test cần tạo model có ít nhất hai property dùng cùng kiểu nhưng metadata khác nhau:

```java
public record PartnerPayload(
        @CodeFormat("[A-Z]{3}-[0-9]{2}") Code externalCode,
        @CodeFormat("[0-9]{6}") Code internalCode) {
}
```

Sau đó deserialize một payload có cả hai field và xác nhận mỗi property dùng đúng pattern. Đồng thời test một input chỉ hợp lệ với pattern của property thứ nhất nhưng được gửi vào property thứ hai; deserializer phải từ chối.

Với contextual deserializer, tránh lưu `BeanProperty` hoặc trạng thái request mutable vào một instance được chia sẻ. `createContextual()` nên tạo instance cấu hình bất biến cho property. Test cần xác nhận hai property không rò cấu hình lẫn nhau khi mapper được dùng đồng thời.

## 18. Kiểm thử custom serializer/deserializer có generic type

Một `SimpleModule` đăng ký theo raw class có thể không phân biệt các kiểu như:

```java
Box<String>
Box<Integer>
```

Cả hai đều có raw class `Box.class`, nhưng nội dung cần deserialize khác nhau. Nếu custom handler phụ thuộc generic parameter, hãy kiểm thử bằng `JavaType` cụ thể:

```java
JavaType type = mapper.getTypeFactory()
        .constructParametricType(Box.class, String.class);

Box<String> box = mapper.readValue(json, type);
```

Test ít nhất hai parameter type khác nhau và nested generic type. Nếu module hiện tại chỉ đăng ký theo raw class, hãy xác nhận nó không vô tình đọc mọi `Box<T>` theo cùng một kiểu. Có thể cần `ContextualDeserializer`, `Deserializers` hoặc type-specific adapter.

## 19. Kiểm thử module modifier

Module có thể đăng ký `BeanSerializerModifier` hoặc `BeanDeserializerModifier` để thay đổi cách Jackson tạo handler cho bean. Khi dùng modifier, test nên đi qua mapper sau khi đăng ký module và kiểm tra output/input của bean thực tế.

Ví dụ, modifier có thể thay serializer cho một bean type hoặc điều chỉnh property writer. Các modifier thường tác động ở giai đoạn xây dựng serializer/deserializer và kết quả có thể được cache. Vì vậy:

- Đăng ký module trước khi mapper được sử dụng.
- Không thay modifier động theo request.
- Test cả bean có annotation và bean không có annotation.
- Test nested property để xác nhận modifier được áp dụng đúng phạm vi.
- Test mapper mới sau khi cấu hình thay đổi; không mong cache cũ tự phản ánh cấu hình vừa sửa.

Nếu modifier chỉ phục vụ một kiểu cụ thể, cân nhắc đăng ký serializer/deserializer tường minh vì code dễ hiểu và test hơn.

## 20. Kiểm thử thứ tự và xung đột cấu hình

Một property có thể đồng thời chịu ảnh hưởng từ:

- Annotation `@JsonSerialize`/`@JsonDeserialize`.
- Mix-in annotation.
- Serializer/deserializer đăng ký trong module.
- Module modifier.
- Default serializer/deserializer của Databind.

Không nên dựa vào giả định chung rằng “module luôn thắng” hoặc “annotation luôn thắng” trong mọi tình huống. Jackson hợp nhất metadata theo loại extension point và property context. Khi có cấu hình chồng lấn, viết test trên mapper cuối cùng để xác nhận handler thực sự được dùng.

Một cách kiểm tra hữu ích là dùng hai handler có output marker khác nhau trong test fixture, sau đó xác nhận output marker của handler được chọn. Không giữ marker/debug serializer trong production.

## 21. Kiểm thử custom serializer không làm lộ dữ liệu

Serializer thường là nơi quyết định field nào được xuất ra. Nếu model chứa token, password hoặc thông tin nội bộ, test cần xác nhận chúng không xuất hiện trong JSON output.

Ví dụ:

```java
@Test
void doesNotSerializeInternalSecret() throws Exception {
    ApiCredential credential = new ApiCredential("client-1", "secret-value");

    String json = mapper.writeValueAsString(credential);
    JsonNode node = mapper.readTree(json);

    assertFalse(node.has("secret"));
    assertFalse(json.contains("secret-value"));
}
```

Nếu custom serializer tự viết object output, cần kiểm tra mọi field được ghi có nằm trong allowlist không. Không chỉ test rằng field cần có tồn tại; test cả field nhạy cảm không được xuất.

Serializer không thay thế authorization. Việc ẩn field trong output không ngăn code service hoặc endpoint khác truy cập giá trị.

## 22. Kiểm thử determinism và canonical representation

Nếu custom serializer tạo representation dùng cho chữ ký, hash hoặc cache key, output có thể cần tính xác định. Khi đó, test cần kiểm tra:

- Cùng input tạo cùng bytes trong cùng contract/version.
- Thứ tự field có được quy định không.
- Decimal có giữ scale hay chuẩn hóa không.
- Date/time có timezone và precision ổn định không.
- Unicode normalization có phải một phần của contract không.
- Null/missing/empty có representation riêng không.

Đừng dùng JSON output thông thường làm canonical byte sequence cho chữ ký nếu chưa có quy tắc canonicalization rõ ràng. JSON object property order không phải lúc nào cũng là hợp đồng. Nếu chữ ký phụ thuộc bytes, dùng canonical JSON specification hoặc một encoding/signature scheme được thiết kế cho mục đích đó.

## 23. Kiểm thử exception mapping và error path

Custom deserializer có thể ném `JsonMappingException` với parser context. Jackson thường bọc hoặc bổ sung path khi lỗi xảy ra trong nested property/list.

Ví dụ test một phần tử lỗi trong list:

```java
@Test
void reportsInvalidMoneyInsideCollection() {
    String json = "[\"VND 10\",\"not-money\"]";

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, new TypeReference<List<Money>>() {}));

    assertFalse(exception.getPath().isEmpty());
}
```

Với root collection, path có thể chứa index thay vì field name. Test nên kiểm tra phần path cần thiết, không cố định toàn bộ message/stack trace.

Ở tầng API, chuyển mapping error thành response ổn định, ví dụ `INVALID_FIELD_FORMAT`. Không trả stack trace hoặc raw input có thể chứa secret cho client.

## 24. Kiểm thử thread safety và lifecycle

Jackson mapper thường được chia sẻ sau khi cấu hình xong; serializer/deserializer có thể được cache và gọi đồng thời. Custom handler nên là stateless hoặc chỉ chứa cấu hình bất biến.

Không lưu dữ liệu theo request vào field instance:

```java
// Không nên: trạng thái này có thể bị chia sẻ giữa các request.
private String currentCurrency;
```

Hãy dùng biến local trong `serialize()`/`deserialize()`, hoặc dùng contextual instance bất biến khi property cần cấu hình riêng.

Nếu handler cần cache nội bộ, dùng cấu trúc thread-safe và có giới hạn. Tránh giữ `JsonParser`, `JsonGenerator`, request object hoặc `BeanProperty` mutable sau khi callback kết thúc.

Một concurrency test có thể serialize/deserialize cùng kiểu từ nhiều thread và xác nhận không rò dữ liệu giữa request. Tuy nhiên, trước hết thiết kế handler stateless; concurrency test chỉ là bổ sung, không thay thế thiết kế đúng.

## 25. Kiểm thử mapper production trong Spring

Trong Spring Boot, module có thể được đăng ký qua bean `Module` và được auto-configured `ObjectMapper` nạp tùy version/cấu hình:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public Module moneyModule() {
        return new MoneyModule();
    }
}
```

Không giả định mọi ứng dụng Spring đều dùng đúng một mapper. Có thể có mapper riêng cho HTTP, message broker, file import hoặc `@Qualifier` khác nhau.

Test cấu hình bean:

```java
@SpringBootTest
class MoneyModuleConfigurationTest {
    @Autowired
    ObjectMapper objectMapper;

    @Test
    void applicationMapperUsesMoneyModule() throws Exception {
        String json = objectMapper.writeValueAsString(
                new Money("VND", new BigDecimal("1500.00")));

        assertEquals("\"VND 1500.00\"", json);
    }
}
```

Test này xác nhận mapper được inject trong application context có module. Nếu endpoint dùng một mapper khác, hãy test đúng HTTP message converter hoặc gọi endpoint bằng `MockMvc`/`WebTestClient`.

## 26. Dùng `@JsonTest` khi phù hợp

Spring Boot cung cấp test slice `@JsonTest` cho các thành phần JSON như `ObjectMapper`, Jackson modules và JSON testers. Nó có thể giúp test serializer/deserializer mà không cần khởi tạo toàn bộ ứng dụng.

Ví dụ:

```java
@JsonTest
class MoneyJsonSliceTest {
    @Autowired
    JacksonTester<Money> json;

    @Test
    void writesMoneyAsString() throws Exception {
        Money money = new Money("VND", new BigDecimal("1500.00"));

        assertThat(json.write(money))
                .extractingJsonPathStringValue("$")
                .isEqualTo("VND 1500.00");
    }
}
```

Để test slice nạp custom module, cần bảo đảm module được import hoặc được cấu hình trong test context theo phiên bản Spring Boot. Nếu test slice không tự nạp bean module của ứng dụng, thêm cấu hình test rõ ràng. Không coi `@JsonTest` tự động chứng minh HTTP endpoint dùng cùng mapper.

## 27. Test contract với golden files

Khi wire format ổn định và có nhiều payload mẫu, có thể lưu JSON fixtures trong `src/test/resources`:

```text
src/test/resources/json/
  money-v1.json
  invoice-v1.json
  partner-event-v2.json
```

Test đọc fixture:

```java
String json = Files.readString(
        Path.of("src/test/resources/json/money-v1.json"),
        StandardCharsets.UTF_8);

Money money = mapper.readValue(json, Money.class);
assertEquals("VND", money.currency());
```

Golden fixture hữu ích cho compatibility test với payload đã được producer phát hành. Giữ fixture đại diện cho version cũ và mới; khi thay serializer, test đảm bảo output mới không vô tình phá contract.

Không lưu token thật, password hoặc dữ liệu cá nhân trong fixture. Dùng dữ liệu giả đã được tạo riêng cho test.

## 28. Test compatibility khi format thay đổi

Giả sử version cũ dùng JSON object:

```json
{
  "currency": "VND",
  "amount": 1500.00
}
```

Version mới dùng chuỗi:

```json
"VND 1500.00"
```

Nếu cần hỗ trợ cả hai trong giai đoạn migration, deserializer có thể chấp nhận hai token shape hoặc ứng dụng có thể dùng versioned DTO/reader. Khi đó, test cần ghi rõ:

- Input legacy vẫn đọc được.
- Input canonical mới đọc được.
- Output luôn dùng representation canonical mới.
- Input không thuộc hai format bị từ chối.
- Thời điểm loại bỏ legacy format được quản lý bằng version/deprecation policy.

Không mở rộng parser mãi mãi để chấp nhận mọi biến thể cũ. Hãy ghi lại compatibility window và có metric để biết còn producer nào dùng format cũ.

## 29. Test module không ghi đè các kiểu không liên quan

Một module domain nên chỉ tác động kiểu đã đăng ký. Test một kiểu thông thường song song:

```java
@Test
void leavesOrdinaryStringSerializationUnchanged() throws Exception {
    String json = mapper.writeValueAsString("hello");
    assertEquals("\"hello\"", json);
}
```

Nếu module đăng ký modifier toàn cục, test thêm bean không thuộc domain để bảo đảm không làm thay đổi serializer ngoài ý muốn.

Với module có nhiều handler, test từng handler độc lập và ít nhất một object graph tích hợp để phát hiện tương tác.

## 30. Test không phụ thuộc thứ tự property

Nếu serializer ghi object với nhiều field, không nên mặc định JSON property order là contract. Ví dụ:

```java
JsonNode expected = mapper.readTree("""
        {"id":"INV-100","total":"VND 1500.00"}
        """);
JsonNode actual = mapper.readTree(mapper.writeValueAsString(invoice));

assertEquals(expected, actual);
```

So sánh tree kiểm tra cấu trúc và giá trị mà không buộc serializer phải ghi property theo thứ tự văn bản cố định. Nếu downstream ký trên bytes hoặc yêu cầu canonical order, cần một contract canonicalization riêng và test bytes theo đúng chuẩn đó.

## 31. Kiểm thử module theo ma trận

Một bộ test đầy đủ có thể được tổ chức như sau:

| Nhóm test | Ví dụ | Điều cần chứng minh |
|---|---|---|
| Serializer unit/contract | `Money` → JSON string | Type và format output đúng |
| Deserializer unit/contract | JSON string → `Money` | Currency/amount đúng |
| Round-trip | Object → JSON → object | Giá trị được bảo toàn theo contract |
| Invalid token | Number/object thay cho string | Mapping từ chối token sai |
| Invalid value | Chuỗi tiền sai format | Deserializer báo mapping error |
| Null | Root/property null | Null policy đúng |
| Nested object | `Invoice.total` | Module áp dụng ở property lồng nhau |
| Collection | `List<Money>` | Handler áp dụng cho từng phần tử |
| Map key | `Map<CurrencyCode, ...>` | Key serializer/deserializer đúng |
| Module registration | Mapper production/test | Module thực sự được nạp |
| Annotation interaction | Property có `using` | Handler đúng được chọn |
| Contextual behavior | Hai property cùng type, annotation khác | Metadata không rò giữa property |
| Generic type | `Box<String>` và `Box<Integer>` | Generic argument được xử lý đúng |
| Error path | Nested/list item sai | Path chỉ đúng property/index |
| Concurrency | Nhiều thread dùng mapper | Handler không chia sẻ state sai |
| Regression | Golden payload cũ/mới | Contract tương thích |
| Integration | HTTP converter/message mapper | Đúng mapper ở ranh giới thật |

Không phải mọi module đều cần tất cả nhóm. Chọn test theo extension point thực sự sử dụng, nhưng luôn có test output/input canonical, negative case và registration.

## 32. Tổ chức test và fixture

Một cấu trúc thư mục có thể là:

```text
src/test/java/
  com/example/json/
    MoneySerializerTest.java
    MoneyDeserializerTest.java
    MoneyModuleTest.java
    MoneyModuleIntegrationTest.java
    MoneyContractCompatibilityTest.java

src/test/resources/
  json/
    money-v1.json
    invoice-v1.json
```

Tách test serializer/deserializer giúp lỗi dễ xác định. Test module tập trung vào đăng ký và tương tác. Integration test xác nhận mapper được framework quản lý. Compatibility test dùng fixture để bảo vệ wire contract qua các lần nâng cấp.

Nếu module chỉ có một handler rất nhỏ, có thể gom unit test trong một class. Đừng tạo quá nhiều class test rỗng; cấu trúc cần phản ánh ranh giới thực tế của code.

## 33. Các lỗi thường gặp khi kiểm thử custom handler

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Serializer không được gọi | Module chưa đăng ký hoặc mapper khác đang được dùng | Test mapper cuối cùng và cấu hình production |
| JSON output là object thay vì string | Custom serializer không được chọn | Kiểm tra type registration và annotation/property override |
| Deserializer chấp nhận token sai | Không kiểm tra `JsonToken` | Kiểm tra token trước khi đọc giá trị |
| Null test không đi qua `deserialize()` | Jackson xử lý null qua null provider | Override/test `getNullValue()` hoặc property null policy |
| Round-trip pass nhưng contract sai | Hai handler cùng sai theo một cách | Test input và output canonical độc lập |
| Nested property dùng handler mặc định | Module/target type không được áp dụng như dự kiến | Test object graph và kiểm tra mapper configuration |
| Map key không được chuyển đổi | Chỉ đăng ký value serializer | Đăng ký key serializer/deserializer riêng |
| Generic type đọc sai tham số | Handler chỉ được đăng ký theo raw class | Dùng contextual/type-aware extension point |
| Test phụ thuộc exception message | Message thay đổi giữa version | Assert exception type và path cần thiết |
| Test pass nhưng HTTP sai | HTTP converter dùng mapper khác | Integration test qua endpoint/converter |
| Concurrency làm lẫn dữ liệu | Custom handler giữ mutable request state | Handler stateless hoặc contextual immutable |
| Module registration bị bỏ qua | Duplicate module ID hoặc auto-discovery khác môi trường | Đăng ký tường minh và test module cuối cùng |

## 34. Quy trình phát triển một module tùy biến

Khi cần thêm một serializer/deserializer, thực hiện theo thứ tự:

1. Định nghĩa wire contract bằng JSON mẫu cho input và output.
2. Xác định handler áp dụng cho toàn kiểu, một property, map key hay generic type.
3. Viết serializer dùng API typed của `JsonGenerator`.
4. Viết deserializer kiểm tra token, format và phạm vi dữ liệu.
5. Xác định null, missing, unknown field và lỗi mapping.
6. Đóng gói handler vào `SimpleModule` hoặc extension point phù hợp.
7. Đăng ký module trước khi mapper được sử dụng.
8. Viết test output, input, round-trip, negative và null.
9. Test nested object, collection/map và property context nếu có.
10. Test mapper thực tế của framework/integration.
11. Kiểm tra handler stateless/thread-safe và không có side effect.
12. Giữ fixture compatibility để bảo vệ contract qua nâng cấp.

## 35. Ghi nhớ

Serializer quyết định cách ghi Java value thành JSON; deserializer đọc token và tạo Java value; module đóng gói các handler cùng cấu hình Databind. Một custom handler cần được kiểm thử ở mức wire contract: output có đúng token type/format không, input canonical có tạo đúng object không, input sai có bị từ chối không, null và lỗi nested có được xử lý đúng không.

Hãy kiểm thử riêng serializer và deserializer, bổ sung round-trip nhưng không chỉ dựa vào round-trip, xác nhận module đã đăng ký trên mapper thực tế, và bao phủ object lồng nhau, collection, map key, generic/contextual type nếu ứng dụng dùng. Giữ custom handler bất biến, không có side effect và dùng API typed của generator/parser. Khi module được kiểm tra bằng cả unit test lẫn integration test, các thay đổi wire format sẽ dễ phát hiện và ít gây lỗi tương thích hơn.
