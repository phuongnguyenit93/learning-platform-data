# Đăng ký deserializer bằng JsonDeserialize theo kiểu hoặc thuộc tính

Jackson thường có thể tự ánh xạ JSON vào Java object dựa trên constructor, getter, setter, field và kiểu dữ liệu. Nhưng có những hệ thống dùng định dạng đầu vào riêng: ngày được viết theo mẫu cũ, số tiền được gộp thành một chuỗi, mã trạng thái có cách biểu diễn không chuẩn hoặc một API trả cùng kiểu Java theo nhiều hình thức JSON khác nhau.

Khi cần điều khiển cách đọc dữ liệu, Jackson cho phép viết custom deserializer và gắn nó bằng annotation **`@JsonDeserialize`**. Annotation có thể đặt ở cấp kiểu Java để mọi lần deserialize kiểu đó dùng cùng một deserializer, hoặc đặt trên một property để chỉ thay đổi cách đọc của thuộc tính đó.

Khác biệt về phạm vi rất quan trọng:

- **Type-level:** quy tắc gắn với một kiểu Java và được dùng ở mọi nơi kiểu đó được deserialize, trừ khi có cấu hình cụ thể hơn cho property.
- **Property-level:** quy tắc chỉ áp dụng cho một thuộc tính, hữu ích khi cùng một kiểu Java xuất hiện ở nhiều vị trí nhưng mỗi API hoặc field có định dạng đầu vào khác nhau.

`@JsonDeserialize` gắn một deserializer với vị trí cần ánh xạ. Nó không tự biến JSON thành dữ liệu hợp lệ; custom deserializer vẫn phải kiểm tra token, chuyển đổi giá trị và báo lỗi phù hợp.

## 1. Custom deserializer là gì?

Deserializer là thành phần chuyển dữ liệu JSON hiện tại thành một giá trị Java. Trong Jackson Databind, custom deserializer thường kế thừa `StdDeserializer<T>` hoặc triển khai `JsonDeserializer<T>`.

Ví dụ, API có thể gửi tiền theo dạng object:

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Trong khi ứng dụng dùng value object:

```java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Nếu cấu trúc JSON không phù hợp với cách Jackson tự tạo object, có thể viết `MoneyDeserializer` để đọc các field và gọi constructor.

Một deserializer có thể:

- Đọc scalar như string, number hoặc boolean.
- Đọc object hoặc array theo token.
- Dùng `JsonNode` để truy cập cấu trúc cây khi thuận tiện.
- Gọi `DeserializationContext` để tìm deserializer cho kiểu con.
- Kiểm tra dữ liệu và ném lỗi ánh xạ có thông tin vị trí.

## 2. Cấu trúc cơ bản của JsonDeserializer

Custom deserializer có thể được viết như sau:

```java
public class MoneyDeserializer extends StdDeserializer<Money> {
    public MoneyDeserializer() {
        super(Money.class);
    }

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        // Đọc token hiện tại và tạo Money
    }
}
```

Hai tham số chính:

- `JsonParser parser`: parser đang đứng tại giá trị JSON cần deserialize.
- `DeserializationContext context`: ngữ cảnh deserialize, cung cấp cấu hình, thông tin kiểu, xử lý lỗi và API tìm deserializer khác.

Jackson gọi `deserialize()` khi cần chuyển một giá trị JSON thành `Money`. Deserializer không nên tự tạo một `ObjectMapper` mới để đọc lại dữ liệu; hãy dùng parser và context được truyền vào để giữ cùng cấu hình và tránh tạo thêm parser không cần thiết.

### 2.1. Đọc object bằng JsonParser

Có thể duyệt token trực tiếp:

```java
@Override
public Money deserialize(
        JsonParser parser,
        DeserializationContext context) throws IOException {

    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw JsonMappingException.from(parser, "Expected a Money object");
    }

    BigDecimal amount = null;
    String currency = null;

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("amount".equals(fieldName) && valueToken.isNumeric()) {
            amount = parser.getDecimalValue();
        } else if ("currency".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            currency = parser.getText();
        } else {
            parser.skipChildren();
        }
    }

    if (amount == null || currency == null || currency.isBlank()) {
        throw JsonMappingException.from(
            parser,
            "Money requires numeric amount and non-empty currency"
        );
    }

    return new Money(amount, currency);
}
```

Đây là cách đọc streaming: deserializer kiểm tra token và chỉ lấy những field cần thiết. Với object lớn hoặc cần kiểm soát token chặt, cách này tránh tạo một cây JSON trung gian.

### 2.2. Đọc object bằng JsonNode

Nếu cấu trúc object nhỏ và cần truy cập field theo tên, có thể đọc thành tree:

```java
@Override
public Money deserialize(
        JsonParser parser,
        DeserializationContext context) throws IOException {

    JsonNode node = parser.getCodec().readTree(parser);
    JsonNode amountNode = node.get("amount");
    JsonNode currencyNode = node.get("currency");

    if (amountNode == null || !amountNode.isNumber()
            || currencyNode == null || !currencyNode.isTextual()) {
        throw JsonMappingException.from(parser, "Invalid Money representation");
    }

    return new Money(amountNode.decimalValue(), currencyNode.textValue());
}
```

Tree model thường dễ đọc hơn khi field có thể xuất hiện theo thứ tự bất kỳ hoặc có nhiều nhánh điều kiện. Đổi lại, Jackson tạo các node trong bộ nhớ. Với payload lớn, hãy cân nhắc duyệt token trực tiếp.

### 2.3. Xử lý token không mong đợi

Không nên ép mọi token thành string hoặc number mà không kiểm tra. Có thể báo lỗi qua `DeserializationContext`:

```java
return (Money) context.handleUnexpectedToken(Money.class, parser);
```

Hoặc ném `JsonMappingException` với thông điệp cụ thể:

```java
throw JsonMappingException.from(parser, "Expected a Money object");
```

Thông báo nên nêu kiểu mong đợi và dữ liệu không phù hợp. Không nên âm thầm trả về object mặc định nếu dữ liệu sai có thể làm hỏng trạng thái nghiệp vụ.

## 3. Đăng ký deserializer ở cấp kiểu bằng @JsonDeserialize

Đặt `@JsonDeserialize(using = ...)` trên class khi mọi lần deserialize kiểu đó nên dùng cùng một quy tắc:

```java
@JsonDeserialize(using = MoneyDeserializer.class)
public class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

`MoneyDeserializer` được gắn với kiểu `Money`. Khi Jackson deserialize `Money` ở root hoặc một property có kiểu `Money`, deserializer này được dùng theo cấu hình annotation đã phân giải.

JSON đầu vào:

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Sử dụng:

```java
ObjectMapper mapper = new ObjectMapper();

Money money = mapper.readValue(json, Money.class);
```

Jackson thấy annotation trên `Money`, tạo `MoneyDeserializer` và gọi `deserialize()` để tạo object.

### 3.1. Khi nên đặt annotation ở cấp kiểu?

Type-level phù hợp khi định dạng JSON là cách biểu diễn chuẩn của kiểu Java đó trong toàn ứng dụng.

Ví dụ:

- `Money` luôn được nhận từ object có `amount` và `currency`.
- `CountryCode` luôn được nhận từ một chuỗi mã chuẩn hóa.
- `LegacyTimestamp` luôn dùng một format cố định do hệ thống ngoài quy định.
- Một value object có representation đặc biệt cần được đọc giống nhau ở mọi DTO.

Nếu mỗi endpoint có hợp đồng khác nhau cho cùng kiểu Java, annotation cấp kiểu có thể quá rộng. Khi đó nên đặt deserializer ở property hoặc dùng DTO trung gian.

### 3.2. Annotation không thay thế logic serializer

`@JsonDeserialize` chỉ chỉ định cách đọc JSON. Nó không thay đổi cách serialize object thành JSON. Nếu muốn định dạng output riêng, cần dùng `@JsonSerialize(using = ...)` hoặc serializer đã đăng ký.

Ví dụ, `MoneyDeserializer` có thể chấp nhận object đầu vào, trong khi serializer chuẩn vẫn xuất object theo getter. Nếu muốn output thành chuỗi `"125.50 USD"`, cần định nghĩa serializer tương ứng.

## 4. Đăng ký deserializer riêng cho một property

Đôi khi cùng kiểu `Money` xuất hiện ở nhiều vị trí, nhưng một property nhận định dạng cũ. Có thể đặt `@JsonDeserialize` ngay trên property cần ngoại lệ:

```java
public class ProductImport {
    private Money listPrice;

    @JsonDeserialize(using = LegacyMoneyDeserializer.class)
    private Money importedPrice;

    public Money getListPrice() {
        return listPrice;
    }

    public void setListPrice(Money listPrice) {
        this.listPrice = listPrice;
    }

    public Money getImportedPrice() {
        return importedPrice;
    }

    public void setImportedPrice(Money importedPrice) {
        this.importedPrice = importedPrice;
    }
}
```

Trong ví dụ:

- `listPrice` dùng deserializer mặc định gắn với kiểu `Money`.
- `importedPrice` dùng `LegacyMoneyDeserializer` riêng.

JSON có thể chứa hai representation khác nhau:

```json
{
  "listPrice": {
    "amount": 125.50,
    "currency": "USD"
  },
  "importedPrice": "89.90|EUR"
}
```

Đây là lý do property-level hữu ích: cùng một kiểu Java có thể nhận nhiều định dạng đầu vào tùy nguồn dữ liệu hoặc field.

### 4.1. Ví dụ LegacyMoneyDeserializer

Deserializer riêng cho chuỗi có dạng `amount|currency`:

```java
public class LegacyMoneyDeserializer extends StdDeserializer<Money> {
    public LegacyMoneyDeserializer() {
        super(Money.class);
    }

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                parser,
                "Legacy money must be a string in amount|currency format"
            );
        }

        String raw = parser.getText();
        String[] parts = raw.split("\\|", 2);
        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw JsonMappingException.from(
                parser,
                "Invalid legacy money value: " + raw
            );
        }

        try {
            BigDecimal amount = new BigDecimal(parts[0].trim());
            String currency = parts[1].trim();
            return new Money(amount, currency);
        } catch (NumberFormatException ex) {
            throw JsonMappingException.from(
                parser,
                "Invalid amount in legacy money value: " + raw,
                ex
            );
        }
    }
}
```

Deserializer này chỉ chấp nhận JSON string. Nếu nhận object hoặc number, nó báo lỗi rõ ràng thay vì cố chuyển đổi tùy tiện.

### 4.2. Deserialize và kiểm tra hai property

```java
String json = """
    {
      "listPrice": {
        "amount": 125.50,
        "currency": "USD"
      },
      "importedPrice": "89.90|EUR"
    }
    """;

ProductImport product = mapper.readValue(json, ProductImport.class);

System.out.println(product.getListPrice().getCurrency());
System.out.println(product.getImportedPrice().getCurrency());
```

Jackson dùng type-level deserializer cho `listPrice` và property-level deserializer cho `importedPrice`. Kết quả Java của cả hai property vẫn là `Money`.

## 5. Annotation trên field, setter, getter hoặc creator parameter

`@JsonDeserialize` có thể được đặt tại những vị trí mà Jackson xem là metadata của property hoặc kiểu. Trong model thông thường, các vị trí hay dùng gồm:

- Field.
- Setter hoặc getter.
- Tham số constructor/factory method được dùng làm creator property.
- Class/type declaration.

Ví dụ trên setter:

```java
public class ProductImport {
    private Money importedPrice;

    @JsonDeserialize(using = LegacyMoneyDeserializer.class)
    public void setImportedPrice(Money importedPrice) {
        this.importedPrice = importedPrice;
    }

    public Money getImportedPrice() {
        return importedPrice;
    }
}
```

Ví dụ trên creator parameter:

```java
public class ProductImport {
    private final Money importedPrice;

    @JsonCreator
    public ProductImport(
            @JsonProperty("importedPrice")
            @JsonDeserialize(using = LegacyMoneyDeserializer.class)
            Money importedPrice) {
        this.importedPrice = importedPrice;
    }

    public Money getImportedPrice() {
        return importedPrice;
    }
}
```

Đặt annotation trên creator parameter hữu ích với immutable object không có setter. Hãy bảo đảm Jackson nhận diện constructor/factory method đó là creator và có tên property phù hợp, thường bằng `@JsonProperty`.

### 5.1. Tránh đặt annotation mâu thuẫn trên nhiều accessor

Field, getter và setter có thể cùng đại diện một logical property. Nếu đặt các `@JsonDeserialize` khác nhau ở nhiều vị trí, kết quả hợp nhất annotation có thể khó hiểu và phụ thuộc cách Jackson introspect property.

Nên chọn một vị trí rõ ràng cho metadata của property. Nếu dự án có mix-in hoặc naming/visibility tùy chỉnh, hãy viết test với mapper thực tế để xác nhận annotation nào có hiệu lực.

## 6. Phân biệt using, contentUsing và keyUsing

`@JsonDeserialize` có nhiều thuộc tính, không phải tất cả đều chỉ định deserializer cho cùng một cấp dữ liệu.

| Thuộc tính | Áp dụng cho |
|---|---|
| `using` | Chính giá trị của kiểu hoặc property được annotation |
| `contentUsing` | Nội dung bên trong container/reference, ví dụ phần tử collection hoặc value của Map |
| `keyUsing` | Key của Map |
| `as` | Kiểu concrete thay cho kiểu khai báo khi deserialize |
| `contentAs` | Kiểu concrete của nội dung container |
| `keyAs` | Kiểu concrete của key Map |
| `converter` | Converter dùng để chuyển đổi kết quả deserialize |
| `contentConverter` | Converter cho nội dung bên trong container/reference |

Đặc biệt, `using` trên một property kiểu `List<T>` có nghĩa deserializer được áp dụng cho cả property list. Nếu chỉ muốn thay cách deserialize từng phần tử `T`, dùng `contentUsing`.

### 6.1. Deserializer cho toàn bộ collection

Ví dụ một property `tags` cần được đọc bằng custom deserializer của cả list:

```java
public class SearchRequest {
    @JsonDeserialize(using = TagListDeserializer.class)
    private List<String> tags;
}
```

`TagListDeserializer` phải tạo ra `List<String>` hoàn chỉnh. Đây là lựa chọn khi format của toàn bộ property có quy tắc đặc biệt.

### 6.2. Deserializer cho từng phần tử bằng contentUsing

Nếu property là list các ngày và chỉ từng phần tử có format riêng:

```java
public class ScheduleImport {
    @JsonDeserialize(contentUsing = FlexibleLocalDateDeserializer.class)
    private List<LocalDate> dates;
}
```

Với JSON:

```json
{
  "dates": ["31/12/2026", "01/01/2027"]
}
```

Jackson vẫn dùng collection deserializer chuẩn để tạo list, nhưng mỗi phần tử được đọc bằng `FlexibleLocalDateDeserializer`.

Ví dụ deserializer cho một ngày:

```java
public class FlexibleLocalDateDeserializer extends StdDeserializer<LocalDate> {
    private static final DateTimeFormatter FORMATTER =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");

    public FlexibleLocalDateDeserializer() {
        super(LocalDate.class);
    }

    @Override
    public LocalDate deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(parser, "Expected date string dd/MM/yyyy");
        }

        try {
            return LocalDate.parse(parser.getText(), FORMATTER);
        } catch (DateTimeParseException ex) {
            throw JsonMappingException.from(parser, "Invalid date: " + parser.getText(), ex);
        }
    }
}
```

Với collection, `contentUsing` giữ lại collection deserializer chuẩn và chỉ thay deserializer của phần tử.

### 6.3. Deserializer cho key của Map bằng keyUsing

Key JSON object luôn được đọc từ tên field dạng chuỗi. Nếu map dùng key là một kiểu Java riêng, có thể chỉ định key deserializer:

```java
public class MetricsImport {
    @JsonDeserialize(keyUsing = MetricKeyDeserializer.class)
    private Map<MetricKey, BigDecimal> values;
}
```

`MetricKeyDeserializer` thường kế thừa `KeyDeserializer`:

```java
public class MetricKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context) throws IOException {

        try {
            return MetricKey.parse(key);
        } catch (IllegalArgumentException ex) {
            throw context.weirdKeyException(
                MetricKey.class,
                key,
                "Invalid metric key"
            );
        }
    }
}
```

`keyUsing` chỉ thay cách chuyển tên key JSON thành key Java. Deserializer của value vẫn theo kiểu `BigDecimal` hoặc cấu hình riêng.

## 7. Phân biệt using với as và converter

Không phải mọi thuộc tính của `@JsonDeserialize` đều nhận một custom deserializer.

### 7.1. using: chỉ định logic đọc tùy chỉnh

```java
@JsonDeserialize(using = MoneyDeserializer.class)
private Money total;
```

Jackson gọi custom deserializer để đọc giá trị JSON và tạo `Money`.

### 7.2. as: chọn kiểu concrete

`as` dùng khi kiểu khai báo là interface hoặc abstract class nhưng dữ liệu cần được tạo thành một implementation cụ thể:

```java
public class Configuration {
    @JsonDeserialize(as = LinkedHashMap.class)
    private Map<String, Object> properties;
}
```

`as` không phải custom deserializer. Nó chỉ cung cấp kiểu concrete để Jackson thực hiện data binding theo serializer/deserializer phù hợp.

Tương tự, `contentAs` và `keyAs` chỉ định kiểu concrete cho phần tử/value hoặc key của container.

### 7.3. converter: chuyển đổi sau bước deserialize

`converter` cho phép dùng `Converter<IN, OUT>` để biến giá trị đã được deserialize thành kiểu ứng dụng cần. Khác với `using`, converter không nhất thiết phải tự đọc token JSON; Jackson có thể deserialize input thành kiểu trung gian trước rồi mới gọi converter.

Ví dụ:

```java
public class StringToCountryCodeConverter
        extends StdConverter<String, CountryCode> {

    @Override
    public CountryCode convert(String value) {
        return CountryCode.of(value);
    }
}
```

Gắn converter:

```java
public class CustomerImport {
    @JsonDeserialize(converter = StringToCountryCodeConverter.class)
    private CountryCode countryCode;
}
```

Hãy chọn `using` khi cần kiểm soát parser/token hoặc chấp nhận cấu trúc JSON không chuẩn. Chọn `converter` khi đầu vào đã có thể được deserialize thành một kiểu trung gian và chỉ cần chuyển sang kiểu domain.

## 8. Property-level deserializer có thể phụ thuộc metadata của property

Một deserializer đôi khi cần biết nó đang được dùng cho property nào. Ví dụ cùng kiểu `LocalDate` nhưng:

- `startDate` dùng format `dd/MM/yyyy`.
- `invoiceDate` dùng format `yyyyMMdd`.

Có thể viết một deserializer triển khai `ContextualDeserializer`. Jackson gọi `createContextual()` để cung cấp `BeanProperty` tương ứng. Deserializer có thể đọc annotation của property rồi trả về một instance đã cấu hình.

```java
public class PropertyDateDeserializer extends StdDeserializer<LocalDate>
        implements ContextualDeserializer {

    private final DateTimeFormatter formatter;

    public PropertyDateDeserializer() {
        this(DateTimeFormatter.ISO_LOCAL_DATE);
    }

    private PropertyDateDeserializer(DateTimeFormatter formatter) {
        super(LocalDate.class);
        this.formatter = formatter;
    }

    @Override
    public LocalDate deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        try {
            return LocalDate.parse(parser.getText(), formatter);
        } catch (DateTimeParseException ex) {
            throw JsonMappingException.from(parser, "Invalid date value", ex);
        }
    }

    @Override
    public JsonDeserializer<?> createContextual(
            DeserializationContext context,
            BeanProperty property) {

        if (property == null) {
            return this;
        }

        JsonFormat format = property.getAnnotation(JsonFormat.class);
        if (format == null || format.pattern().isEmpty()) {
            return this;
        }

        return new PropertyDateDeserializer(
            DateTimeFormatter.ofPattern(format.pattern())
        );
    }
}
```

Sử dụng:

```java
public class ReportRequest {
    @JsonDeserialize(using = PropertyDateDeserializer.class)
    @JsonFormat(pattern = "dd/MM/uuuu")
    private LocalDate startDate;

    @JsonDeserialize(using = PropertyDateDeserializer.class)
    @JsonFormat(pattern = "uuuuMMdd")
    private LocalDate invoiceDate;
}
```

Jackson tạo contextual instance phù hợp cho từng property. Vì deserializer có thể được cache và tái sử dụng, không nên thay đổi mutable formatter dùng chung trong `createContextual()`. Trả về instance mới bất biến như ví dụ sẽ an toàn và dễ suy luận hơn.

Nếu chỉ cần format ngày chuẩn mà không cần custom parsing, hãy cân nhắc module Java Time và `@JsonFormat` trước khi viết custom deserializer. Custom contextual deserializer phù hợp khi quy tắc đọc phức tạp hơn khả năng cấu hình chuẩn.

## 9. Xử lý null, empty và field bị thiếu

Jackson thường xử lý JSON `null` thông qua `getNullValue()` của deserializer hoặc null handling ở property; phương thức `deserialize()` không nhất thiết được gọi cho token null.

Nếu cần một giá trị đặc biệt khi input là JSON null, có thể override:

```java
@Override
public Money getNullValue(DeserializationContext context) {
    return null;
}
```

Nếu muốn trả một sentinel riêng, chỉ làm vậy khi hợp đồng domain định nghĩa rõ ý nghĩa của sentinel. Không nên dùng một object giả để che giấu dữ liệu thiếu hoặc sai.

Phân biệt các trường hợp:

| JSON đầu vào | Ý nghĩa |
|---|---|
| Không có key | Property bị thiếu; setter thường không được gọi, creator có thể nhận giá trị mặc định/thiếu tùy cấu hình |
| `"field": null` | Có key và giá trị JSON null; null handling được áp dụng |
| `"field": ""` | Chuỗi rỗng; custom deserializer có thể nhận token string |
| `"field": []` | Array rỗng; có thể cần xử lý riêng theo kiểu đích |
| `"field": {}` | Object rỗng; custom deserializer phải xác định có hợp lệ không |

Nếu muốn xử lý null ở property, `@JsonSetter(nulls = ...)` và `Nulls` là cơ chế chuyên biệt. Nếu muốn xử lý field thiếu, hãy xem creator properties, giá trị khởi tạo của field và `DeserializationFeature` liên quan. `@JsonDeserialize` chủ yếu chọn cách đọc giá trị hiện diện.

## 10. Deserializer cần có constructor và cách khởi tạo phù hợp

Khi annotation khai báo:

```java
@JsonDeserialize(using = MoneyDeserializer.class)
```

Jackson cần tạo được instance của `MoneyDeserializer`. Cách đơn giản nhất là cung cấp constructor không tham số public hoặc phù hợp với cơ chế instantiation của Jackson:

```java
public class MoneyDeserializer extends StdDeserializer<Money> {
    public MoneyDeserializer() {
        super(Money.class);
    }
}
```

Nếu deserializer cần dependency như service, repository hoặc cấu hình runtime, không nên tự `new` dependency trong deserializer. Có thể dùng `HandlerInstantiator` hoặc cơ chế tích hợp dependency injection của framework để tạo handler. Một lựa chọn khác là giữ deserializer không trạng thái và đưa phần kiểm tra nghiệp vụ sang service sau deserialize.

Deserializers nên được thiết kế thread-safe. Jackson có thể cache và dùng lại instance giữa nhiều lần đọc. Tránh lưu parser hiện tại, request data hoặc mutable state theo từng lần gọi vào field của deserializer.

## 11. Dùng mix-in khi không thể sửa class nguồn

Nếu class đến từ thư viện ngoài và không thể thêm annotation, có thể dùng Jackson mix-in để bổ sung annotation ở runtime:

```java
@JsonDeserialize(using = ExternalMoneyDeserializer.class)
abstract class ExternalMoneyMixin {
}

ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalMoney.class, ExternalMoneyMixin.class);
```

Mix-in cung cấp annotation như thể chúng được đặt trên kiểu nguồn. Đây là lựa chọn hữu ích khi muốn giữ model bên thứ ba độc lập với Jackson.

Với property trong class ngoài, có thể tạo mix-in tương ứng với field/getter/setter và đặt annotation lên member được Jackson introspect. Cần bảo đảm chữ ký và tên member khớp với class đích.

## 12. So sánh @JsonDeserialize với đăng ký qua Module

`@JsonDeserialize` không phải cách duy nhất để liên kết custom deserializer. Có thể đăng ký theo kiểu bằng `SimpleModule`:

```java
SimpleModule module = new SimpleModule("money-module");
module.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

So sánh:

| Cách | Phạm vi | Phù hợp khi |
|---|---|---|
| `@JsonDeserialize` trên class | Kiểu Java được annotation | Model sở hữu quy tắc đọc chuẩn của chính nó |
| `@JsonDeserialize` trên property | Một thuộc tính | Cùng kiểu Java có nhiều representation tùy field |
| `@JsonDeserialize(contentUsing = ...)` | Phần tử/value trong container | Mỗi phần tử cần parser riêng nhưng container vẫn dùng serializer chuẩn |
| `@JsonDeserialize(keyUsing = ...)` | Key của Map | Key JSON cần chuyển thành kiểu Java tùy chỉnh |
| `SimpleModule.addDeserializer()` | Kiểu Java trong mapper | Muốn cấu hình bên ngoài model hoặc dùng class không thể sửa |
| Mix-in | Kiểu hoặc member được gắn annotation gián tiếp | Không sở hữu source class nhưng muốn dùng annotation semantics |

Module-level registration thường là lựa chọn phù hợp khi chính sách thuộc về ứng dụng hoặc mapper, còn annotation phù hợp khi muốn đặt metadata ngay cạnh model/property. Nếu cùng một kiểu được đăng ký cả qua annotation và module, hãy kiểm tra thứ tự và quy tắc precedence của cấu hình thực tế; tránh đăng ký hai deserializer cạnh tranh mà không có test.

## 13. Kiểm thử deserializer theo kiểu và theo property

Vì hai phạm vi có thể tạo hành vi khác nhau, nên test riêng cả hai.

### 13.1. Test type-level deserializer

```java
@Test
void usesMoneyDeserializerDeclaredOnType() throws Exception {
    String json = """
        {
          "amount": 125.50,
          "currency": "USD"
        }
        """;

    Money money = mapper.readValue(json, Money.class);

    assertEquals(new BigDecimal("125.50"), money.getAmount());
    assertEquals("USD", money.getCurrency());
}
```

Test xác nhận annotation trên class được dùng khi deserialize root `Money`.

### 13.2. Test property-level override

```java
@Test
void usesDifferentDeserializerForLegacyProperty() throws Exception {
    String json = """
        {
          "listPrice": {
            "amount": 125.50,
            "currency": "USD"
          },
          "importedPrice": "89.90|EUR"
        }
        """;

    ProductImport product = mapper.readValue(json, ProductImport.class);

    assertEquals("USD", product.getListPrice().getCurrency());
    assertEquals(new BigDecimal("89.90"), product.getImportedPrice().getAmount());
    assertEquals("EUR", product.getImportedPrice().getCurrency());
}
```

Test xác nhận hai property cùng kiểu `Money` có thể dùng hai representation khác nhau.

### 13.3. Test input sai định dạng

```java
@Test
void rejectsInvalidLegacyMoney() {
    String json = """
        { "importedPrice": "not-a-money-value" }
        """;

    assertThrows(JsonProcessingException.class,
        () -> mapper.readValue(json, ProductImport.class));
}
```

Hãy kiểm tra cả:

- Đúng JSON shape và đúng giá trị.
- Token sai loại, ví dụ number thay cho string.
- Thiếu field bắt buộc bên trong object.
- Null, empty string và whitespace.
- Giá trị không parse được.
- Cùng kiểu xuất hiện ở nhiều property với policy khác nhau.
- Root-level deserialize và property-level deserialize.

## 14. Những lỗi thường gặp

**Đặt deserializer cho collection ở `using` khi chỉ muốn đổi cách đọc phần tử.** `using` áp dụng cho cả property collection; dùng `contentUsing` cho từng phần tử.

**Đặt custom deserializer trên class nhưng mong chỉ một field bị ảnh hưởng.** Type-level áp dụng rộng cho kiểu đó. Dùng property-level nếu chỉ một field cần format riêng.

**Dùng property-level deserializer nhưng không xác nhận annotation được nhận diện.** Kiểm tra field/getter/setter/creator parameter và visibility; viết test với mapper thực tế.

**Không kiểm tra token trước khi đọc.** `getText()` trên token không mong đợi có thể tạo lỗi khó hiểu. Kiểm tra `currentToken()` và báo lỗi có ngữ cảnh.

**Dùng `deserialize()` để xử lý JSON null.** Jackson có đường xử lý null riêng thông qua `getNullValue()` và null handling. Override phương thức phù hợp nếu cần semantics riêng.

**Tạo ObjectMapper mới trong deserializer.** Mapper mới có thể thiếu module/cấu hình và tạo thêm chi phí. Dùng parser, codec và context được truyền vào.

**Lưu state theo request trong deserializer.** Deserializer có thể được cache và dùng lại giữa các thread. Giữ nó bất biến hoặc chỉ lưu cấu hình bất biến.

**Dùng `as` như thể nó là `using`.** `as` chọn kiểu concrete; `using` chỉ định custom deserializer.

**Nhầm deserializer với converter.** Deserializer đọc token JSON; converter biến kiểu trung gian đã được deserialize thành kiểu đích.

**Cho rằng `@JsonDeserialize` thay đổi output JSON.** Annotation này điều khiển input; dùng `@JsonSerialize` cho output.

## 15. Quy trình lựa chọn và đăng ký deserializer

1. Xác định JSON representation cần đọc và kiểu Java đích.
2. Kiểm tra Jackson mặc định hoặc module hiện có đã hỗ trợ representation đó chưa.
3. Nếu toàn bộ kiểu Java có cùng format, đặt `@JsonDeserialize(using = ...)` trên class.
4. Nếu chỉ một property có format riêng, đặt annotation trên field/accessor/creator parameter của property đó.
5. Nếu property là collection/map, xác định cần deserializer cho container (`using`), content (`contentUsing`) hay key (`keyUsing`).
6. Chọn `converter` khi chỉ cần chuyển kiểu trung gian; chọn `using` khi cần điều khiển việc đọc token.
7. Viết deserializer không trạng thái, kiểm tra token và báo lỗi có ngữ cảnh.
8. Xác định chính sách null, empty và field thiếu riêng biệt.
9. Dùng mapper/context hiện tại; không tạo mapper mới trong mỗi lần deserialize.
10. Test root-level, property-level, input sai kiểu và trường hợp cùng kiểu xuất hiện ở nhiều vị trí.

## Kết luận

`@JsonDeserialize(using = ...)` liên kết custom deserializer với kiểu Java hoặc một property cụ thể. Type-level phù hợp khi kiểu có một representation đầu vào chuẩn trên toàn ứng dụng; property-level phù hợp khi cùng kiểu được nhận từ nhiều định dạng khác nhau. Với collection và map, hãy phân biệt `using`, `contentUsing` và `keyUsing`; `as` chọn kiểu concrete còn `converter` chuyển đổi sau khi dữ liệu trung gian đã được deserialize. Custom deserializer cần kiểm tra token, xử lý lỗi rõ ràng, giữ trạng thái an toàn khi được cache và dùng `DeserializationContext` hiện tại để tái sử dụng cấu hình Jackson.
