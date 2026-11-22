# Kiểm thử cấu trúc, kiểu và khả năng đọc lại kết quả

Khi viết custom serializer cho Jackson, việc kiểm tra rằng `writeValueAsString(...)` không ném exception là chưa đủ. Serializer có thể tạo ra JSON hợp lệ về cú pháp nhưng sai cấu trúc, sai kiểu giá trị, thiếu field, ghi nhầm `null`, hoặc dùng tên property không đúng hợp đồng. Một serializer và deserializer được viết cùng một cách sai còn có thể đọc lại dữ liệu của nhau thành công, khiến lỗi contract bị che khuất.

Một bộ test tốt cần kiểm tra độc lập ba khía cạnh:

1. **Cấu trúc JSON:** root là object hay array, field nào xuất hiện, object/array lồng nhau có đúng hình dạng không.
2. **Kiểu và giá trị JSON:** string, number, boolean, null và các giá trị số/ngày giờ có đúng kiểu, đúng nội dung không.
3. **Khả năng đọc lại:** JSON được deserialize bằng kiểu đích và cấu hình mapper mà consumer thực sự sử dụng, sau đó tạo ra dữ liệu Java đúng.

Trong Jackson, `JsonNode` rất hữu ích để kiểm tra cấu trúc và kiểu mà không phụ thuộc khoảng trắng hoặc thứ tự trình bày. `ObjectReader` và `ObjectMapper.readValue(...)` giúp kiểm tra khả năng đọc lại theo kiểu đích. Với serializer tùy biến, nên kết hợp cả kiểm tra JSON độc lập và kiểm tra round-trip.

## 1. Vì sao cần kiểm tra nhiều hơn việc JSON parse được?

Giả sử ứng dụng có DTO:

```java
public record InvoiceDto(
        String invoiceNumber,
        BigDecimal total,
        boolean paid
) {
}
```

Contract yêu cầu:

```json
{
  "invoiceNumber": "INV-2026-001",
  "total": 1250.75,
  "paid": true
}
```

Serializer có thể vô tình ghi `total` thành string:

```json
{
  "invoiceNumber": "INV-2026-001",
  "total": "1250.75",
  "paid": true
}
```

JSON thứ hai vẫn hợp lệ về cú pháp. Nhưng consumer mong đợi JSON number và có thể từ chối hoặc xử lý khác. Một test chỉ gọi `readTree(json)` mà không kiểm tra kiểu cũng sẽ pass.

Tương tự, các lỗi sau đều có thể tạo JSON parse được:

- Ghi `"items": { ... }` trong khi contract yêu cầu array.
- Ghi `"enabled": "true"` thay vì boolean `true`.
- Bỏ field bắt buộc hoặc ghi sai tên field.
- Ghi `null` thay cho field bị bỏ qua, hoặc ngược lại.
- Ghi số tiền thành `double` khiến mất độ chính xác.
- Ghi ngày giờ không có offset trong khi consumer cần một instant xác định.
- Đặt object lồng nhau sai cấp nhưng vẫn đúng grammar JSON.

Do đó, test phải xác nhận cả hình dạng và kiểu của từng phần dữ liệu quan trọng.

## 2. Dùng JsonNode để kiểm tra cấu trúc output

Sau khi serialize, có thể parse JSON thành `JsonNode`:

```java
String json = mapper.writeValueAsString(value);
JsonNode root = mapper.readTree(json);
```

Tree model cho phép kiểm tra field theo tên, duyệt object/array và xác định loại node. Ví dụ:

```java
assertTrue(root.isObject());
assertEquals("INV-2026-001", root.get("invoiceNumber").asText());
assertTrue(root.get("total").isNumber());
assertTrue(root.get("paid").isBoolean());
```

Những assertion này kiểm tra ý nghĩa JSON thay vì so sánh nguyên văn chuỗi. Nếu pretty printer thêm newline hoặc đổi khoảng trắng, test vẫn pass miễn cấu trúc và giá trị không đổi.

### 2.1. Kiểm tra root object và các field bắt buộc

```java
assertNotNull(root);
assertTrue(root.isObject());
assertTrue(root.has("invoiceNumber"));
assertTrue(root.has("total"));
assertTrue(root.has("paid"));
```

`has(name)` trả về `true` khi field tồn tại, kể cả khi giá trị của field là JSON `null`. Đây là điểm quan trọng khi contract phân biệt field có mặt với field bị thiếu.

Nếu cần kiểm tra field tồn tại và không null, dùng:

```java
assertTrue(root.hasNonNull("invoiceNumber"));
```

Không dùng `asText()` hoặc `asInt()` một cách máy móc để kiểm tra kiểu. Các phương thức chuyển đổi tiện ích có thể trả giá trị mặc định hoặc chuyển kiểu từ node khác, làm test bỏ sót việc serializer ghi sai token. Hãy kiểm tra `isTextual()`, `isIntegralNumber()`, `isNumber()` hoặc `isBoolean()` trước.

### 2.2. Kiểm tra field không được phép xuất hiện

Nếu serializer phải ẩn field nội bộ:

```java
assertFalse(root.has("internalNote"));
assertFalse(root.has("databaseId"));
```

Kiểm tra field bị loại bỏ quan trọng không kém kiểm tra field bắt buộc. Một serializer có thể vô tình xuất thêm dữ liệu nội bộ do thay đổi getter, annotation hoặc cấu hình mapper.

## 3. Phân biệt thiếu field, JSON null và giá trị mặc định

Ba trường hợp sau không tương đương:

```json
{}
```

```json
{"middleName":null}
```

```json
{"middleName":""}
```

Trong `JsonNode`:

- Field không tồn tại: `root.has("middleName")` là `false`; `root.get(...)` trả `null`.
- Field có JSON null: `root.has(...)` là `true`; node có `isNull()`.
- Field có string rỗng: node có `isTextual()` và `asText()` là chuỗi rỗng.

Ví dụ test:

```java
assertFalse(root.has("omittedField"));

assertTrue(root.has("nullableField"));
assertTrue(root.get("nullableField").isNull());

assertTrue(root.has("emptyText"));
assertTrue(root.get("emptyText").isTextual());
assertEquals("", root.get("emptyText").textValue());
```

Nếu contract yêu cầu null được ghi rõ, hãy kiểm tra `isNull()`. Nếu contract yêu cầu bỏ field null, hãy kiểm tra `has(...)` là `false`. Đừng chỉ kiểm tra `path(...).isMissingNode()` nếu muốn phân biệt null với missing.

## 4. Kiểm tra kiểu JSON chính xác

Jackson cung cấp các phương thức kiểm tra loại node. Một số phương thức thường dùng:

| JSON type | Kiểm tra trong JsonNode | Ví dụ |
|---|---|---|
| Object | `isObject()` | `{ "id": 1 }` |
| Array | `isArray()` | `[1, 2]` |
| String | `isTextual()` | `"hello"` |
| Integral number | `isIntegralNumber()` | `42` |
| Floating-point/decimal number | `isFloatingPointNumber()` hoặc `isNumber()` | `12.50` |
| Boolean | `isBoolean()` | `true` |
| Null | `isNull()` | `null` |

Với contract chỉ yêu cầu “number”, `isNumber()` thường phù hợp. Nếu contract bắt buộc số nguyên, dùng `isIntegralNumber()`. Nếu contract yêu cầu number dạng decimal, hãy kiểm tra bằng typed deserialization hoặc các API node tương ứng và lưu ý cấu hình tree model.

Ví dụ:

```java
JsonNode quantity = root.get("quantity");
assertNotNull(quantity);
assertTrue(quantity.isIntegralNumber());
assertEquals(3, quantity.intValue());

JsonNode price = root.get("price");
assertNotNull(price);
assertTrue(price.isNumber());
assertEquals(1250.75, price.doubleValue(), 0.000001);
```

Với số tiền hoặc giá trị cần độ chính xác thập phân, không nên chỉ dùng `doubleValue()` để xác nhận giá trị. Có thể đọc JSON vào kiểu `BigDecimal` hoặc dùng `decimalValue()` rồi so sánh bằng `compareTo(...)`:

```java
BigDecimal actual = root.get("price").decimalValue();
assertEquals(0, new BigDecimal("1250.75").compareTo(actual));
```

Tree model có thể chọn node số cụ thể tùy cấu hình mapper và token đầu vào. Nếu test cần xác nhận kiểu Java chính xác là `BigDecimal`, hãy deserialize field vào DTO/kiểu đích `BigDecimal` và kiểm tra trực tiếp giá trị đó.

## 5. Kiểm tra array và object lồng nhau

Khi serializer ghi collection, hãy kiểm tra node là array, số phần tử, thứ tự và hình dạng từng phần tử:

```java
JsonNode items = root.get("items");

assertNotNull(items);
assertTrue(items.isArray());
assertEquals(2, items.size());

JsonNode first = items.get(0);
assertTrue(first.isObject());
assertEquals("P-100", first.get("productCode").asText());
assertTrue(first.get("quantity").isIntegralNumber());
```

Nếu array có thứ tự nghiệp vụ, kiểm tra đúng thứ tự phần tử. Nếu contract xem dữ liệu là tập hợp không thứ tự, không nên viết test phụ thuộc thứ tự iteration ngẫu nhiên của `HashSet`; hãy kiểm tra membership hoặc chuẩn hóa thứ tự trước khi serialize.

Đối với object lồng nhau:

```java
JsonNode shipping = root.get("shippingAddress");
assertTrue(shipping.isObject());
assertEquals("Ho Chi Minh City", shipping.get("city").asText());
assertEquals("VN", shipping.get("countryCode").asText());
```

Kiểm tra đúng cấp rất quan trọng. Field `city` nằm trực tiếp ở root và field `city` nằm trong `shippingAddress` là hai cấu trúc khác nhau dù giá trị giống nhau.

## 6. Ví dụ custom serializer cho kiểu Money

Giả sử domain có kiểu tiền:

```java
public record Money(
        String currency,
        BigDecimal amount
) {
}

public record Invoice(
        String invoiceNumber,
        Money total
) {
}
```

Custom serializer ghi `Money` thành một object gồm `currency` và `amount`:

```java
public final class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator gen,
            SerializerProvider provider
    ) throws IOException {
        gen.writeStartObject();
        gen.writeStringField("currency", value.currency());
        gen.writeNumberField("amount", value.amount());
        gen.writeEndObject();
    }
}
```

Đăng ký serializer:

```java
SimpleModule module = new SimpleModule("money-module");
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Khi serialize:

```java
Invoice invoice = new Invoice(
        "INV-2026-001",
        new Money("USD", new BigDecimal("1250.75"))
);

String json = mapper.writeValueAsString(invoice);
```

JSON dự kiến:

```json
{
  "invoiceNumber": "INV-2026-001",
  "total": {
    "currency": "USD",
    "amount": 1250.75
  }
}
```

Test không nên chỉ so sánh string nguyên văn. Hãy kiểm tra shape và kiểu:

```java
JsonNode root = mapper.readTree(json);
JsonNode total = root.get("total");

assertTrue(root.isObject());
assertEquals("INV-2026-001", root.get("invoiceNumber").textValue());
assertTrue(total.isObject());
assertEquals("USD", total.get("currency").textValue());
assertTrue(total.get("amount").isNumber());
assertEquals(
        0,
        new BigDecimal("1250.75").compareTo(total.get("amount").decimalValue())
);
```

Các assertion xác nhận custom serializer ghi `Money` thành object, `currency` là string và `amount` là JSON number. Nếu serializer vô tình dùng `writeStringField("amount", ...)`, test `isNumber()` sẽ thất bại.

## 7. Kiểm tra khả năng đọc lại bằng kiểu đích thực tế

Sau khi kiểm tra JSON độc lập, deserialize về kiểu Java mà consumer sẽ sử dụng:

```java
Invoice restored = mapper.readValue(json, Invoice.class);

assertEquals("INV-2026-001", restored.invoiceNumber());
assertEquals("USD", restored.total().currency());
assertEquals(
        0,
        new BigDecimal("1250.75").compareTo(restored.total().amount())
);
```

Trong ví dụ này, `Money` là record nên Jackson có thể deserialize object gồm `currency` và `amount` bằng cơ chế record/creator mặc định. Nếu custom serializer tạo một shape khác với shape mà deserializer mong đợi, test đọc lại sẽ phát hiện lỗi.

Nếu serializer ghi một giá trị string hoặc array thay cho object, cần có custom deserializer tương ứng. Test nên dùng chính `ObjectMapper`, `ObjectReader`, module và feature giống production. Một mapper test được tạo khác cấu hình có thể cho kết quả không phản ánh ứng dụng.

## 8. Round-trip test không thể thay thế contract test

Round-trip test thường có dạng:

```java
String json = mapper.writeValueAsString(original);
Invoice restored = mapper.readValue(json, Invoice.class);
assertEquals(original, restored);
```

Đây là kiểm tra hữu ích, nhưng có một giới hạn quan trọng: serializer và deserializer có thể cùng tuân theo một format sai so với contract bên ngoài.

Ví dụ contract yêu cầu:

```json
{"amount":1250.75}
```

Nhưng serializer và deserializer cùng dùng string:

```json
{"amount":"1250.75"}
```

Round-trip nội bộ vẫn có thể thành công. Consumer khác lại mong JSON number và bị lỗi.

Vì vậy, hãy kết hợp:

- **Contract assertion:** kiểm tra JSON output theo schema/hình dạng độc lập.
- **Type assertion:** kiểm tra đúng loại token và giá trị.
- **Readback assertion:** deserialize bằng kiểu đích và xác nhận object.
- **Negative assertion:** xác nhận input sai hoặc type không hợp lệ bị từ chối.

Không dùng round-trip như bằng chứng duy nhất rằng serializer đúng.

## 9. Dùng ObjectReader và ObjectWriter để cố định cấu hình test

`ObjectWriter` và `ObjectReader` giúp test sử dụng đúng kiểu đích và cấu hình chuyên biệt mà ứng dụng dự định dùng:

```java
ObjectWriter writer = mapper.writerFor(Invoice.class);
ObjectReader reader = mapper.readerFor(Invoice.class);

String json = writer.writeValueAsString(invoice);
Invoice restored = reader.readValue(json);
```

Điều này đặc biệt hữu ích khi:

- Root value được serialize qua base type hoặc interface.
- Mapper có mix-in, view hoặc filter.
- Cấu hình date/time hoặc coercion khác nhau theo reader/writer.
- Ứng dụng có nhiều contract output cho cùng một class.

Test cần dùng đúng reader/writer mà endpoint hoặc message consumer sử dụng. Nếu production dùng `writerFor(BaseType.class)` nhưng test gọi `writeValueAsString(value)` trực tiếp, hai đường serialize có thể áp dụng metadata khác nhau.

## 10. Kiểm tra serializer đã được đăng ký và thực sự được gọi

Một lỗi thường gặp là custom serializer đã viết đúng nhưng module chưa được đăng ký, hoặc mapper được test không phải mapper của ứng dụng. JSON vẫn serialize thành công bằng serializer mặc định, khiến test không phát hiện custom serializer chưa hoạt động.

Ví dụ module registration:

```java
SimpleModule module = new SimpleModule("money-module");
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = JsonMapper.builder()
        .addModule(module)
        .build();
```

Test nên xác nhận một đặc điểm chỉ custom serializer mới tạo ra, ví dụ object shape `{currency, amount}`. Nếu default serializer tạo shape khác, assertion sẽ thất bại khi module không được đăng ký.

Với serializer được khai báo bằng annotation:

```java
public record InvoiceView(
        String invoiceNumber,
        @JsonSerialize(using = MoneySerializer.class)
        Money total
) {
}
```

Test cần serialize chính DTO/property này bằng mapper có bật annotation. Nếu `MapperFeature.USE_ANNOTATIONS` bị tắt, annotation sẽ không được xử lý theo cách thông thường.

Không nên chỉ mock `JsonGenerator` để xác nhận một vài lời gọi được thực hiện. Mock có thể hữu ích cho nhánh logic rất hẹp, nhưng test với generator thật và parse output sẽ kiểm tra được cấu trúc JSON cuối cùng.

## 11. Kiểm tra string, escaping và tên field

Custom serializer có thể nhận dữ liệu chứa dấu ngoặc kép, backslash, newline hoặc Unicode. Hãy test bằng giá trị có ký tự đặc biệt:

```java
String input = "He said: \"Hello\"\\next line\nXin chào";
String json = mapper.writeValueAsString(new Message(input));

JsonNode root = mapper.readTree(json);
assertEquals(input, root.get("text").textValue());
```

Test này kiểm tra rằng sau serialize rồi parse, string giữ đúng nội dung ban đầu. Không cần so sánh chuỗi escape nguyên văn vì Jackson có thể có các cách escape hợp lệ khác nhau theo cấu hình.

Nếu custom serializer tạo field name động, cũng cần test key có dấu ngoặc kép hoặc ký tự đặc biệt. Hãy dùng `writeFieldName(...)`; không tự ghép tên field vào raw JSON.

## 12. Kiểm tra số và độ chính xác

Serializer số cần được kiểm tra ở ranh giới kiểu dữ liệu:

- Số nguyên âm, 0 và số nguyên lớn.
- Số thập phân có scale như `1.00`.
- Giá trị rất nhỏ hoặc rất lớn.
- `BigDecimal` có nhiều chữ số.
- `float`/`double` gần ranh giới làm tròn.
- Giá trị không hữu hạn như `NaN` và `Infinity` nếu model có thể chứa chúng.

Ví dụ kiểm tra `BigDecimal`:

```java
BigDecimal amount = new BigDecimal("12345678901234567890.1200");
String json = mapper.writeValueAsString(amount);

BigDecimal restored = mapper.readValue(json, BigDecimal.class);
assertEquals(0, amount.compareTo(restored));
```

Nếu scale là một phần của contract, `compareTo(...)` chưa đủ vì `1.0` và `1.00` so sánh số học bằng nhau nhưng có scale khác nhau. Khi đó, kiểm tra thêm `scale()` hoặc `equals(...)` tùy ý nghĩa cần giữ.

Không nên kiểm tra number bằng cách lấy text và so sánh chuỗi trừ khi lexical form là một phần của contract. JSON number `1`, `1.0` và `1e0` có thể biểu diễn cùng giá trị số trong nhiều ngữ cảnh nhưng khác cách viết.

## 13. Kiểm tra ngày giờ và timezone

Nếu custom serializer định dạng `Instant`, `OffsetDateTime` hoặc `ZonedDateTime`, hãy kiểm tra cả kiểu JSON và thông tin thời gian cần giữ.

Ví dụ contract yêu cầu UTC ISO string:

```java
JsonNode timestamp = root.get("occurredAt");
assertTrue(timestamp.isTextual());
assertEquals("2026-11-12T09:30:00Z", timestamp.textValue());
```

Nếu contract yêu cầu giữ offset nguồn:

```java
OffsetDateTime restored = mapper.readValue(
        "\"2026-11-12T16:30:00+07:00\"",
        OffsetDateTime.class
);

assertEquals(ZoneOffset.ofHours(7), restored.getOffset());
```

Nếu contract yêu cầu giữ ZoneId, kiểm tra `getZone()` sau khi deserialize và cấu hình Java Time module phù hợp. Chỉ so sánh instant có thể bỏ qua việc offset hoặc ZoneId đã bị thay đổi.

Test ngày giờ nên bao gồm UTC, offset dương/âm, phần nano giây nếu cần và các trường hợp daylight saving time nếu ứng dụng dùng `ZonedDateTime` theo vùng.

## 14. Kiểm tra serializer với null và property inclusion

Một custom serializer cho kiểu `Money` thông thường không nhất thiết được gọi khi property có giá trị null; Jackson có thể xử lý null bằng null serializer riêng. Nếu contract yêu cầu null được ghi như JSON null, hãy kiểm tra output:

```java
Invoice invoice = new Invoice("INV-EMPTY", null);
JsonNode root = mapper.readTree(mapper.writeValueAsString(invoice));

assertTrue(root.has("total"));
assertTrue(root.get("total").isNull());
```

Nếu contract yêu cầu bỏ field null:

```java
assertFalse(root.has("total"));
```

Hai chính sách này phải được cấu hình nhất quán bằng `@JsonInclude`, inclusion của mapper hoặc custom null serializer phù hợp. Không giả định custom serializer sẽ tự quyết định mọi trường hợp null.

Nếu custom serializer có `getNullValue(...)` hoặc ứng dụng đăng ký null serializer riêng, hãy test nhánh đó độc lập. Null handling có thể là một phần quan trọng của contract API.

## 15. Kiểm tra collection, map và thứ tự

Nếu custom serializer ghi array, hãy kiểm tra:

- Root hoặc field đúng là array.
- Số phần tử đúng.
- Mỗi phần tử có đúng kiểu.
- Thứ tự phần tử đúng nếu contract có thứ tự.
- Empty collection được ghi thành `[]`, `null` hay bỏ field theo contract.

Với map:

```java
JsonNode attributes = root.get("attributes");
assertTrue(attributes.isObject());
assertEquals("blue", attributes.get("color").textValue());
assertEquals(3, attributes.get("priority").intValue());
```

Nếu map key là kiểu không phải String và có custom key serializer, kiểm tra tên field đã được mã hóa đúng và có thể khôi phục bằng key deserializer tương ứng. Đồng thời test hai key khác nhau không bị mã hóa thành cùng field name.

Không khẳng định thứ tự object property trong test trừ khi contract thật sự yêu cầu byte/order ổn định. JSON object về mặt data model là tập member; test cấu trúc thường nên truy cập field theo tên. Array lại có thứ tự nên cần kiểm tra thứ tự nếu nó mang ý nghĩa.

## 16. Kiểm tra token trực tiếp bằng JsonParser

`JsonNode` phù hợp với kiểm tra cấu trúc. Nếu custom serializer cần bảo đảm thứ tự token, không tạo token thừa hoặc ghi đúng một root value, có thể kiểm tra bằng `JsonParser`:

```java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    assertEquals(JsonToken.START_OBJECT, parser.nextToken());

    assertEquals(JsonToken.FIELD_NAME, parser.nextToken());
    assertEquals("invoiceNumber", parser.currentName());
    assertEquals(JsonToken.VALUE_STRING, parser.nextToken());

    assertEquals(JsonToken.FIELD_NAME, parser.nextToken());
    assertEquals("total", parser.currentName());
    assertEquals(JsonToken.START_OBJECT, parser.nextToken());

    // Tiếp tục kiểm tra các token của object total.
}
```

Kiểm tra token hữu ích khi thứ tự ghi là một phần của giao thức hoặc serializer tạo cấu trúc streaming phức tạp. Với phần lớn API JSON, kiểm tra bằng `JsonNode` dễ bảo trì hơn vì không phụ thuộc thứ tự field object.

Để bảo đảm chỉ có một root value, có thể bật `DeserializationFeature.FAIL_ON_TRAILING_TOKENS` trên mapper/reader khi đọc lại. Nếu output có nhiều root value ngoài ý muốn, test sẽ phát hiện.

## 17. Phát hiện duplicate field name

Một serializer có thể ghi cùng tên field nhiều lần. Một số consumer giữ giá trị đầu, một số giữ giá trị cuối, còn một số báo lỗi. Đừng chỉ parse bằng mapper mặc định rồi kiểm tra `JsonNode`, vì khi dữ liệu được đưa vào tree, thông tin duplicate có thể đã bị ghi đè.

Có thể tạo parser factory với strict duplicate detection:

```java
JsonFactory strictFactory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper strictMapper = new ObjectMapper(strictFactory);

assertThrows(
        JsonParseException.class,
        () -> strictMapper.readTree(json)
);
```

Test này có thể dùng để xác nhận output của serializer không có duplicate member name. Nếu contract cho phép field trùng (thường không nên), phải định nghĩa rõ cách consumer xử lý; trong hầu hết API, duplicate field nên bị từ chối.

## 18. Kiểm tra khả năng đọc lại với input hợp lệ và không hợp lệ

Readback test nên bao gồm dữ liệu bình thường và các trường hợp biên:

- Field bắt buộc bị thiếu.
- Field có JSON null.
- Field có sai token type, ví dụ string thay cho number.
- Enum hoặc discriminator không xác định.
- Số vượt phạm vi kiểu Java.
- Ngày giờ sai định dạng hoặc thiếu offset.
- Object/array có cấu trúc lồng nhau không đúng.
- Có trailing root token.

Ví dụ kiểm tra number sai kiểu:

```java
String invalid = """
        {
          "invoiceNumber": "INV-1",
          "total": "1250.75",
          "paid": true
        }
        """;

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readerFor(Invoice.class).readValue(invalid)
);
```

Đoạn test này chỉ đúng nếu mapper được cấu hình nghiêm ngặt để không coercion string thành số và DTO/serializer contract mong đợi `total` là object `Money` trong ví dụ trước. Hãy điều chỉnh kiểu đích và coercion theo contract thực tế; không sao chép assertion exception mà chưa xác định cấu hình mapper.

Với custom deserializer, hãy kiểm tra exception type/message phù hợp khi dữ liệu không hợp lệ. Không nên bắt mọi lỗi rồi trả object mặc định vì điều đó làm input sai được chấp nhận âm thầm.

## 19. Dùng JUnit 5 cho một test đầy đủ

Ví dụ sau gom kiểm tra cấu trúc, kiểu, giá trị và readback cho custom serializer `MoneySerializer`:

```java
class MoneySerializerTest {
    private final ObjectMapper mapper = JsonMapper.builder()
            .addModule(moneyModule())
            .build();

    private static SimpleModule moneyModule() {
        SimpleModule module = new SimpleModule("money-module");
        module.addSerializer(Money.class, new MoneySerializer());
        return module;
    }

    @Test
    void writesExpectedStructureAndTypes() throws Exception {
        Invoice invoice = new Invoice(
                "INV-2026-001",
                new Money("USD", new BigDecimal("1250.75"))
        );

        String json = mapper.writeValueAsString(invoice);
        JsonNode root = mapper.readTree(json);

        assertTrue(root.isObject());
        assertEquals("INV-2026-001", root.get("invoiceNumber").textValue());

        JsonNode total = root.get("total");
        assertTrue(total.isObject());
        assertEquals("USD", total.get("currency").textValue());
        assertTrue(total.get("amount").isNumber());
        assertEquals(
                0,
                new BigDecimal("1250.75").compareTo(total.get("amount").decimalValue())
        );
    }

    @Test
    void canReadSerializedValueBack() throws Exception {
        Invoice invoice = new Invoice(
                "INV-2026-001",
                new Money("USD", new BigDecimal("1250.75"))
        );

        String json = mapper.writeValueAsString(invoice);
        Invoice restored = mapper.readerFor(Invoice.class).readValue(json);

        assertEquals(invoice.invoiceNumber(), restored.invoiceNumber());
        assertEquals(invoice.total().currency(), restored.total().currency());
        assertEquals(0, invoice.total().amount().compareTo(restored.total().amount()));
    }
}
```

Hai test có mục đích khác nhau. Test đầu kiểm tra JSON contract trực tiếp. Test thứ hai xác nhận Jackson có thể đọc output về kiểu Java. Nếu chỉ giữ test thứ hai, format sai nhưng serializer/deserializer cùng hiểu vẫn có thể không bị phát hiện.

## 20. Dùng parameterized test cho nhiều trường hợp

Khi serializer có nhiều giá trị biên, JUnit 5 parameterized test giúp kiểm tra cùng một contract với nhiều input:

```java
@ParameterizedTest
@CsvSource({
        "USD, 0.00",
        "USD, 1.25",
        "EUR, 999999.99",
        "JPY, 1000"
})
void writesMoneyAsObject(String currency, String amountText) throws Exception {
    Money money = new Money(currency, new BigDecimal(amountText));

    String json = mapper.writeValueAsString(money);
    JsonNode root = mapper.readTree(json);

    assertTrue(root.isObject());
    assertEquals(currency, root.get("currency").textValue());
    assertTrue(root.get("amount").isNumber());
    assertEquals(
            0,
            new BigDecimal(amountText).compareTo(root.get("amount").decimalValue())
    );
}
```

Nếu dữ liệu có dấu phẩy, quote hoặc Unicode, dùng `@MethodSource` để truyền object phức tạp thay vì cố mã hóa vào CSV. Parameterized test đặc biệt hữu ích cho serializer format, enum, date/time và key encoding.

## 21. Kiểm tra theo JSON Schema hoặc contract fixture

Với API có schema độc lập, có thể kiểm tra output bằng JSON Schema validator. Schema mô tả root type, required fields, property types, array item shape, enum và constraint.

Ví dụ schema giản lược cho invoice:

```json
{
  "type": "object",
  "required": ["invoiceNumber", "total", "paid"],
  "properties": {
    "invoiceNumber": {"type": "string"},
    "total": {
      "type": "object",
      "required": ["currency", "amount"],
      "properties": {
        "currency": {"type": "string"},
        "amount": {"type": "number"}
      }
    },
    "paid": {"type": "boolean"}
  }
}
```

Schema test bổ sung cho assertion `JsonNode`, nhất là khi contract được chia sẻ với consumer hoặc team khác. Schema không thay thế kiểm tra logic serializer đặc thù, và validator phải dùng đúng dialect/format mà contract công bố.

Golden fixture cũng hữu ích khi output phải tương thích với một payload mẫu đã được chấp nhận. Nên parse fixture và so sánh cấu trúc nếu khoảng trắng hoặc thứ tự field không thuộc contract. Chỉ so sánh byte/string nguyên văn khi format lexical thực sự là yêu cầu.

## 22. Không phụ thuộc thứ tự property nếu contract không yêu cầu

JSON object không nên được xem là một danh sách field có thứ tự trong hầu hết API contract. Test như sau thường quá chặt:

```java
assertEquals(
        "{\"invoiceNumber\":\"INV-1\",\"paid\":true}",
        json
);
```

Chỉ một thay đổi pretty printer hoặc thứ tự property cũng làm test thất bại dù dữ liệu không đổi.

Thông thường, hãy kiểm tra:

```java
JsonNode root = mapper.readTree(json);
assertEquals("INV-1", root.get("invoiceNumber").textValue());
assertTrue(root.get("paid").booleanValue());
```

Nếu output được dùng làm byte canonical, chữ ký hoặc hash và thứ tự là một phần của thuật toán, hãy test canonical bytes theo chuẩn đó. Không dùng một test string tùy ý để thay thế kiểm tra chuẩn canonicalization.

## 23. Test serializer có context hoặc thuộc tính động

Một số serializer dùng `SerializerProvider`, `BeanProperty`, annotation hoặc context attribute để thay đổi cách ghi. Ví dụ serializer có thể cần currency mặc định hoặc format theo một property.

Khi đó, test phải tạo đúng `ObjectWriter`/mapper context mà production sử dụng:

```java
ObjectWriter writer = mapper.writer()
        .withAttribute("defaultCurrency", "USD");

String json = writer.writeValueAsString(value);
```

Nếu serializer cần `ContextualSerializer`, test nên serialize qua property DTO thật thay vì gọi serializer trực tiếp. Điều này bảo đảm Jackson gọi `createContextual(...)` với metadata property tương ứng.

Không nên dựa vào trạng thái mutable dùng chung trong serializer singleton để truyền dữ liệu giữa request. Test song song hoặc nhiều property có thể phát hiện state leakage. Serializer thường nên stateless; context per-call nên được truyền qua provider/writer attribute hoặc cơ chế contextual phù hợp.

## 24. Test hiệu ứng của module và thứ tự đăng ký

Ứng dụng có thể đăng ký nhiều module, mix-in và custom serializer. Cấu hình cuối cùng có thể ảnh hưởng serializer được chọn. Hãy tạo mapper trong test theo cùng factory/configuration path với production.

Một test tích hợp nên xác nhận:

- Module custom đã được đăng ký.
- Annotation hoặc mix-in được bật.
- Serializer tùy biến được chọn cho đúng kiểu/property.
- Serializer mặc định không ghi đè ngoài dự kiến.
- Mapper không bị cấu hình lại sau khi đã dùng.
- `ObjectWriter`/`ObjectReader` được endpoint sử dụng đúng kiểu.

Nếu project có một lớp `ObjectMapper` factory hoặc Spring configuration, nên dùng chính bean/configuration đó trong test tích hợp thay vì tạo một mapper mới với `new ObjectMapper()` rồi tự đăng ký một phần module.

## 25. Test lỗi và thông báo từ custom serializer

Custom serializer có thể phát hiện dữ liệu không hợp lệ trước khi ghi:

```java
if (value.amount().signum() < 0) {
    throw JsonMappingException.from(
            gen,
            "Money amount must not be negative"
    );
}
```

Test nên xác nhận input sai bị từ chối:

```java
Money invalid = new Money("USD", new BigDecimal("-1.00"));

assertThrows(
        JsonMappingException.class,
        () -> mapper.writeValueAsString(invalid)
);
```

Nếu contract cho phép số âm, bỏ rule này và kiểm tra giá trị được ghi đúng. Test phải phản ánh nghiệp vụ thật, không tự thêm giới hạn chỉ để serializer dễ xử lý.

Nếu exception được wrap trong `JsonMappingException` hoặc `JsonProcessingException`, hãy kiểm tra cause khi cần phân biệt lỗi serializer với lỗi I/O. Không nên phụ thuộc toàn bộ message dài có thể thay đổi theo phiên bản Jackson; ưu tiên exception type và một phần thông điệp ổn định do ứng dụng kiểm soát.

## 26. Một số lỗi test thường gặp

| Test không tốt | Vấn đề | Cách cải thiện |
|---|---|---|
| Chỉ assert JSON không null | Không kiểm tra cấu trúc | Parse thành `JsonNode` và kiểm tra root/field |
| Chỉ gọi `readTree` | JSON parse được nhưng type sai vẫn pass | Assert `isTextual`, `isNumber`, `isBoolean`, `isArray`... |
| Chỉ round-trip và so sánh object | Serializer/deserializer có thể cùng sai | Thêm contract assertions độc lập |
| So sánh toàn bộ JSON string | Nhạy với whitespace/property order | So sánh tree trừ khi byte order là contract |
| Dùng `asInt()` để kiểm tra number | Có thể che coercion từ string hoặc default | Kiểm tra `isIntegralNumber()` trước |
| Chỉ test giá trị thông thường | Bỏ sót null, empty, precision và Unicode | Dùng boundary/parameterized tests |
| Test bằng mapper tự tạo khác production | Bỏ sót module/feature thực tế | Dùng mapper bean hoặc factory production |
| Parse tree mà không strict duplicate detection | Duplicate field có thể đã bị ghi đè | Dùng parser với `STRICT_DUPLICATE_DETECTION` |
| Bỏ qua trailing tokens | Có thể chấp nhận nhiều root value | Bật `FAIL_ON_TRAILING_TOKENS` khi phù hợp |
| Mock JsonGenerator cho toàn bộ test | Không kiểm tra JSON cuối cùng | Dùng generator thật và parse output |

## 27. Quy trình viết test cho custom serializer

Với mỗi custom serializer, có thể áp dụng trình tự sau:

1. Viết một input đại diện và xác định JSON contract mong đợi bằng ví dụ rõ ràng.
2. Serialize bằng đúng mapper/writer production.
3. Parse output thành `JsonNode`.
4. Kiểm tra root type, field bắt buộc, field bị loại bỏ và cấp lồng nhau.
5. Kiểm tra token type của string, number, boolean, null, array và object.
6. Kiểm tra giá trị, precision, null policy, escaping và thứ tự array nếu có ý nghĩa.
7. Deserialize bằng `ObjectReader` và kiểu đích thực tế.
8. So sánh object đã đọc lại với dữ liệu nguồn theo quy tắc domain.
9. Thử input biên và input sai; xác nhận lỗi được báo đúng.
10. Nếu contract yêu cầu, kiểm tra duplicate field, trailing tokens hoặc JSON Schema.
11. Chỉ so sánh byte/string nguyên văn khi lexical representation thực sự là một phần của contract.

Không cần mọi serializer đều có hàng chục test giống nhau. Hãy tập trung vào các quyết định mà serializer tự thực hiện: đổi shape, đổi tên, định dạng scalar, lọc field, ghi null, chuyển key hoặc xử lý subtype.

## 28. Ghi nhớ

Kiểm thử custom serializer cần xác nhận JSON output đúng cấu trúc, đúng kiểu token và có thể được consumer đọc lại. `JsonNode` giúp kiểm tra object/array, field, null/missing và loại giá trị mà không phụ thuộc whitespace. `ObjectReader` hoặc `readValue(...)` kiểm tra khả năng deserialize về kiểu Java đích.

Round-trip là cần thiết nhưng chưa đủ vì serializer và deserializer có thể cùng hiểu một format sai. Hãy thêm contract assertion độc lập, kiểm tra number/BigDecimal và date/time theo đúng kiểu, test null/escaping/collection/unknown values, và dùng strict duplicate detection khi cần. Dùng mapper/module/writer giống production; chỉ so sánh JSON nguyên văn khi thứ tự, whitespace hoặc byte encoding thật sự thuộc contract.
