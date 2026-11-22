# Khi nào cần deserializer riêng thay vì chuyển kiểu mặc định

Jackson có thể chuyển đổi rất nhiều dạng JSON sang kiểu Java mà không cần viết code riêng. Nó tự xử lý object, array, scalar, collection, enum, date/time khi module phù hợp được đăng ký, và nhiều phép chuyển đổi số hoặc chuỗi thông dụng. Với các hợp đồng JSON rõ ràng, dùng databinding mặc định thường là cách đơn giản và dễ bảo trì nhất.

Tuy nhiên, dữ liệu thực tế đôi khi có nhiều cách biểu diễn cho cùng một giá trị, chứa quy tắc chuyển đổi riêng của hệ thống cũ, hoặc cần kết hợp nhiều token JSON để tạo một value object. Khi quy tắc đó không thể mô tả rõ bằng kiểu Java, annotation hoặc cấu hình coercion có sẵn, một **custom deserializer** là lựa chọn phù hợp.

Bài này giải thích cách quyết định khi nào cần deserializer riêng, khi nào nên giữ chuyển đổi mặc định, cách viết và đăng ký deserializer bằng Jackson, cùng các vấn đề về null, lỗi mapping, hiệu năng và kiểm thử.

## 1. Chuyển kiểu mặc định của Jackson đã làm được những gì?

Khi gọi:

```java
User user = mapper.readValue(json, User.class);
```

Jackson chọn deserializer phù hợp với kiểu đích `User`, đọc JSON token và gán giá trị vào các property. Với cấu trúc thông thường, không cần tự đọc từng token.

Ví dụ DTO:

```java
public class User {
    private String id;
    private String name;
    private int age;
    private boolean active;

    // Constructor, getter và setter
}
```

JSON:

```json
{
  "id": "U-100",
  "name": "An",
  "age": 28,
  "active": true
}
```

Jackson có thể chuyển:

- JSON string thành `String`.
- JSON integer thành `int` nếu giá trị nằm trong miền.
- JSON boolean thành `boolean`.
- JSON object thành POJO lồng nhau.
- JSON array thành collection hoặc array Java nếu kiểu phần tử được xác định.
- JSON object thành `Map` nếu kiểu đích là map.

Ví dụ collection:

```java
List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
);
```

Với kiểu tổng quát đã được cung cấp đầy đủ, Jackson biết cách deserialize từng phần tử thành `User`.

### 1.1. Chuyển đổi mặc định không có nghĩa là chấp nhận mọi đầu vào

Jackson vẫn kiểm tra cú pháp JSON, kiểu token và khả năng biểu diễn của kiểu đích. Ví dụ, chuỗi không phải số có thể gây lỗi khi gán vào `int`; số vượt miền `int` không thể được lưu chính xác vào kiểu đó.

Một số phép coercion có thể được bật theo cấu hình, ví dụ chuyển chuỗi số thành số hoặc chuyển floating-point token sang kiểu nguyên. Hành vi cụ thể phụ thuộc phiên bản Jackson và coercion configuration.

Không nên viết custom deserializer chỉ để lặp lại những gì databinding đã hỗ trợ. Trước tiên hãy xác định kiểu JSON thực tế, kiểu Java đích và cấu hình mapper hiện tại.

## 2. Khi nào nên giữ databinding mặc định?

Hãy ưu tiên chuyển đổi mặc định khi JSON đã có cấu trúc tương ứng với class Java và quy tắc ánh xạ chỉ là quy ước thông thường.

Ví dụ:

```json
{
  "first_name": "An",
  "created_at": "2025-01-01T10:00:00Z"
}
```

Nếu vấn đề chỉ là tên field khác Java property, dùng `@JsonProperty` hoặc naming strategy:

```java
public class User {
    @JsonProperty("first_name")
    private String firstName;
}
```

Nếu cần đọc chuỗi thời gian theo format đã hỗ trợ, dùng Java Time module và `@JsonFormat` khi thích hợp:

```java
public class AuditRecord {
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
}
```

Một số nhu cầu phổ biến có giải pháp declarative sẵn:

| Nhu cầu | Nên thử trước |
|---|---|
| Đổi tên JSON property | `@JsonProperty`, naming strategy |
| Chấp nhận tên field cũ và mới | `@JsonAlias` |
| Định dạng ngày giờ | Java Time module, `@JsonFormat` |
| Null bị bỏ qua, từ chối hoặc chuyển thành empty | `@JsonSetter(nulls = ...)` |
| Immutable object nhận dữ liệu qua constructor | `@JsonCreator`, `@JsonProperty` |
| Field JSON không biết trước | `@JsonAnySetter`, `JsonNode` |
| Chọn subtype bằng discriminator | `@JsonTypeInfo`, `@JsonSubTypes` |
| Chuyển một kiểu đầu vào đơn giản sang value object | `Converter` / `StdConverter` |
| Quy tắc chuyển token phức tạp | Custom `JsonDeserializer` |

Nếu một annotation hoặc cấu hình chuẩn đã diễn đạt đúng hợp đồng, dùng nó thường ít code hơn và dễ tương thích với công cụ Jackson hơn.

## 3. Dấu hiệu cho thấy cần deserializer riêng

Custom deserializer hữu ích khi quy tắc chuyển đổi thuộc về cấu trúc hoặc ngữ nghĩa của dữ liệu, không chỉ là đổi tên field.

### 3.1. Một kiểu Java chấp nhận nhiều hình dạng JSON

Ví dụ một value object `Money` có thể đến từ API theo hai dạng:

```json
{
  "total": {
    "amount": 125.50,
    "currency": "VND"
  }
}
```

Hệ thống cũ lại gửi:

```json
{
  "total": "125.50 VND"
}
```

Cả hai dạng đều mang cùng một ý nghĩa domain: số tiền và loại tiền. Nếu không muốn tạo hai DTO khác nhau cho cùng một property, deserializer có thể kiểm tra token hiện tại và đọc theo đúng hình dạng.

### 3.2. Giá trị được tạo từ nhiều token hoặc nhiều field

Một kiểu đích có thể cần kết hợp nhiều phần của JSON:

```json
{
  "coordinates": {
    "latitude": 10.7769,
    "longitude": 106.7009
  }
}
```

Nếu domain type là `GeoPoint` bất biến và constructor cần hai tham số, `@JsonCreator` có thể đã đủ. Nhưng nếu dữ liệu có nhiều dạng đầu vào, cần kiểm tra quan hệ giữa các field, hoặc có quy tắc chuẩn hóa riêng, custom deserializer có thể làm rõ logic hơn.

### 3.3. Quy tắc chuyển đổi đặc thù của hệ thống cũ

Ví dụ API cũ gửi boolean dưới dạng `"Y"`, `"N"`, `"1"`, `"0"`. Nếu chỉ một property cần quy tắc này, có thể dùng converter hoặc deserializer riêng thay vì thay đổi coercion toàn mapper.

### 3.4. Cần xác thực token shape trước khi tạo object

Có property bắt buộc phải là JSON integer, dù Jackson có thể cho phép chuỗi số. Nếu contract yêu cầu token type cụ thể, custom deserializer có thể từ chối ngay khi token không đúng.

### 3.5. Cần chuẩn hóa dữ liệu trước khi object được tạo

Ví dụ mã định danh có thể có dấu cách, prefix cũ hoặc cách viết không thống nhất. Nếu chuẩn hóa là một phần ổn định của quy tắc parse kiểu đó, deserializer/converter có thể đưa dữ liệu về dạng canonical trước khi tạo object.

### 3.6. Cần tạo một kiểu thư viện hoặc kiểu bên thứ ba

Nếu class không do ứng dụng sở hữu và không thể thêm annotation hoặc constructor phù hợp, có thể đăng ký deserializer qua `Module` hoặc dùng mix-in để gắn cấu hình.

## 4. Khi nào custom deserializer là quá mức cần thiết?

Không nên tạo deserializer riêng chỉ vì một trong các lý do sau:

- Muốn đổi tên JSON property.
- Muốn bỏ qua field không biết.
- Muốn map một field vào constructor.
- Muốn chấp nhận alias tên field.
- Muốn format ngày giờ đã được Java Time module hỗ trợ.
- Muốn chuyển một chuỗi đơn giản thành một value object bằng một phép biến đổi duy nhất.
- Muốn validation nghiệp vụ sau khi object đã được tạo.

Custom deserializer làm ứng dụng chịu trách nhiệm trực tiếp cho token traversal, coercion, lỗi, null và tương thích. Nếu logic chỉ có một dòng chuyển đổi, dùng converter thường dễ hiểu hơn.

Cũng không nên nhét toàn bộ validation domain vào deserializer. Deserialize nên tập trung chuyển biểu diễn wire thành kiểu Java. Những quy tắc như “số dư không được âm với tài khoản đang hoạt động” hoặc “người dùng phải có quyền sở hữu đơn hàng” thuộc tầng domain/service.

## 5. So sánh các lựa chọn trước khi viết deserializer

| Cách | Đầu vào phù hợp | Nơi đặt logic | Khi nên chọn |
|---|---|---|---|
| Databinding mặc định | JSON có shape tương ứng DTO | Jackson | Hầu hết object/collection thông thường |
| Annotation | Tên, format, creator, null, polymorphism | Class/property | Quy tắc declarative |
| Coercion configuration | Điều chỉnh chuyển token theo logical type | Mapper/type config | Quy tắc chung cho nhiều property |
| Converter | Một kiểu nguồn chuyển thành một kiểu đích | Converter class | Biến đổi giá trị tương đối đơn giản |
| Custom deserializer | Nhiều token shape, cấu trúc đặc thù, parse phức tạp | `JsonDeserializer` | Cần kiểm soát quá trình đọc JSON |
| Tree model rồi chuyển DTO | Cấu trúc động, discriminator hoặc nhánh thay đổi | Tầng tích hợp | Chỉ biết schema sau khi đọc một phần payload |

Một nguyên tắc hữu ích: chọn giải pháp có phạm vi hẹp nhất vẫn diễn đạt đầy đủ hợp đồng. Property riêng thì dùng property-level annotation; quy tắc chung cho một nhóm kiểu thì cân nhắc mapper config; chỉ khi cần điều khiển cách đọc token mới chuyển sang custom deserializer.

## 6. Ví dụ: Money nhận object hoặc chuỗi legacy

Giả sử domain có kiểu `Money` bất biến:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public final class Money {
    private final BigDecimal amount;
    private final Currency currency;

    public Money(BigDecimal amount, Currency currency) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Currency getCurrency() {
        return currency;
    }
}
```

Hợp đồng mới gửi object:

```json
{
  "amount": 125.50,
  "currency": "VND"
}
```

Hợp đồng cũ gửi chuỗi:

```json
"125.50 VND"
```

Chúng ta muốn cả hai được đọc thành cùng một `Money`, đồng thời từ chối token khác như array hoặc boolean.

### 6.1. Viết StdDeserializer

`StdDeserializer<T>` là lớp tiện ích để triển khai `JsonDeserializer<T>`. Ví dụ:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
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
            DeserializationContext context
    ) throws IOException {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.VALUE_STRING) {
            return parseCompactValue(parser.getText(), parser);
        }

        if (token == JsonToken.START_OBJECT) {
            return parseObject(parser);
        }

        return (Money) context.handleUnexpectedToken(Money.class, parser);
    }

    private Money parseObject(JsonParser parser) throws IOException {
        BigDecimal amount = null;
        Currency currency = null;

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            if (parser.currentToken() == null) {
                throw JsonMappingException.from(
                        parser,
                        "JSON Money object chưa kết thúc"
                );
            }

            if (parser.currentToken() != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(
                        parser,
                        "Expected a field name in Money object"
                );
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if (valueToken == null) {
                throw JsonMappingException.from(
                        parser,
                        "Thiếu giá trị cho field " + fieldName
                );
            }

            if ("amount".equals(fieldName)) {
                amount = readAmount(parser);
            } else if ("currency".equals(fieldName)) {
                currency = readCurrency(parser);
            } else {
                parser.skipChildren();
                throw JsonMappingException.from(
                        parser,
                        "Unknown Money property: " + fieldName
                );
            }
        }

        if (amount == null) {
            throw JsonMappingException.from(parser, "Money thiếu amount");
        }

        if (currency == null) {
            throw JsonMappingException.from(parser, "Money thiếu currency");
        }

        return new Money(amount, currency);
    }

    private BigDecimal readAmount(JsonParser parser) throws IOException {
        JsonToken token = parser.currentToken();

        try {
            if (token == JsonToken.VALUE_NUMBER_INT
                    || token == JsonToken.VALUE_NUMBER_FLOAT) {
                return parser.getDecimalValue();
            }

            if (token == JsonToken.VALUE_STRING) {
                return new BigDecimal(parser.getText().trim());
            }
        } catch (NumberFormatException ex) {
            throw JsonMappingException.from(
                    parser,
                    "amount không phải số thập phân hợp lệ",
                    ex
            );
        }

        throw JsonMappingException.from(
                parser,
                "amount phải là JSON number hoặc chuỗi số"
        );
    }

    private Currency readCurrency(JsonParser parser) throws IOException {
        if (parser.currentToken() != JsonToken.VALUE_STRING) {
            throw JsonMappingException.from(
                    parser,
                    "currency phải là chuỗi mã tiền tệ"
            );
        }

        try {
            return Currency.getInstance(parser.getText().trim());
        } catch (IllegalArgumentException ex) {
            throw JsonMappingException.from(
                    parser,
                    "currency không phải mã ISO 4217 hợp lệ",
                    ex
            );
        }
    }

    private Money parseCompactValue(
            String text,
            JsonParser parser
    ) throws JsonMappingException {
        String[] parts = text.trim().split("\\s+", 2);

        if (parts.length != 2) {
            throw JsonMappingException.from(
                    parser,
                    "Money string phải có dạng '<amount> <currency>'"
            );
        }

        try {
            BigDecimal amount = new BigDecimal(parts[0]);
            Currency currency = Currency.getInstance(parts[1]);
            return new Money(amount, currency);
        } catch (NumberFormatException ex) {
            throw JsonMappingException.from(
                    parser,
                    "amount trong Money string không hợp lệ",
                    ex
            );
        } catch (IllegalArgumentException ex) {
            throw JsonMappingException.from(
                    parser,
                    "currency trong Money string không hợp lệ",
                    ex
            );
        }
    }
}
```

Deserializer kiểm tra token hiện tại:

- `VALUE_STRING`: đọc định dạng legacy.
- `START_OBJECT`: đọc hai field `amount` và `currency`.
- Token khác: báo lỗi kiểu đầu vào không mong đợi.

Với số trong object, `parser.getDecimalValue()` đọc trực tiếp decimal token thành `BigDecimal`, tránh chuyển qua `double`. Với currency, `Currency.getInstance()` xác thực mã tiền tệ theo danh sách ISO 4217 mà JDK hỗ trợ.

Ví dụ trên chọn chính sách từ chối field lạ trong Money object. Nếu hợp đồng cần forward compatibility, có thể bỏ qua field lạ bằng `skipChildren()` thay vì ném lỗi. Hãy chọn rõ chính sách và kiểm thử nó.

### 6.2. Đăng ký deserializer bằng SimpleModule

Có thể đăng ký deserializer cho kiểu `Money` trên mapper:

```java
SimpleModule moneyModule = new SimpleModule();
moneyModule.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = JsonMapper.builder()
        .addModule(moneyModule)
        .build();
```

DTO:

```java
public class Invoice {
    private String id;
    private Money total;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Money getTotal() {
        return total;
    }

    public void setTotal(Money total) {
        this.total = total;
    }
}
```

Jackson dùng deserializer đã đăng ký khi gặp property có kiểu `Money`, kể cả khi property nằm sâu trong object lồng nhau.

### 6.3. Gắn deserializer ở một property

Nếu chỉ một property cần cách đọc riêng, có thể dùng `@JsonDeserialize`:

```java
public class Invoice {
    @JsonDeserialize(using = MoneyDeserializer.class)
    private Money total;

    // Getter/setter
}
```

Cách này giới hạn quy tắc cho property đó. Nếu mọi nơi dùng `Money` đều phải tuân theo cùng wire contract, đăng ký qua module hoặc gắn annotation trên kiểu có thể phù hợp hơn.

Không nên đăng ký global và property-level cùng lúc nếu không có lý do rõ ràng; cấu hình chồng lấp làm việc tìm deserializer thực tế khó hiểu hơn.

## 7. Converter hay custom deserializer?

Nếu đầu vào luôn là một JSON string và chỉ cần biến đổi string thành object, một converter có thể đơn giản hơn.

Ví dụ:

```java
public final class CurrencyCode {
    private final Currency value;

    public CurrencyCode(Currency value) {
        this.value = value;
    }

    public Currency getValue() {
        return value;
    }
}
```

Converter:

```java
import com.fasterxml.jackson.databind.util.StdConverter;

public final class CurrencyCodeConverter
        extends StdConverter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String value) {
        return new CurrencyCode(Currency.getInstance(value.trim()));
    }
}
```

Gắn converter:

```java
public class Payment {
    @JsonDeserialize(converter = CurrencyCodeConverter.class)
    private CurrencyCode currency;
}
```

Converter phù hợp khi Jackson đã có thể đọc input thành kiểu nguồn, ở đây là `String`, rồi ứng dụng chỉ cần chuyển kiểu nguồn đó thành kiểu đích.

Custom deserializer phù hợp hơn khi cần:

- Kiểm tra token có phải string, object, array hay number.
- Đọc nhiều field trong một object.
- Quyết định cách parse theo discriminator.
- Kiểm soát thứ tự hoặc sự hiện diện của token.
- Tạo lỗi gắn với vị trí JSON cụ thể.
- Hỗ trợ nhiều biểu diễn JSON khác nhau cho cùng một kiểu đích.

Đừng dùng custom parser cho một phép chuyển đổi scalar đơn giản nếu converter đã đủ.

## 8. Các cách khác có thể giải quyết vấn đề mà không cần custom deserializer

Trước khi triển khai, hãy kiểm tra các cơ chế sẵn có.

### 8.1. @JsonProperty và @JsonAlias cho tên field

Nếu API cũ dùng `user_name` và API mới dùng `username`:

```java
public class User {
    @JsonProperty("username")
    @JsonAlias("user_name")
    private String username;
}
```

Jackson chấp nhận cả hai tên khi deserialize, nhưng dùng tên chính khi serialize. Không cần viết parser chỉ để đổi tên field.

### 8.2. @JsonCreator cho object bất biến

Nếu JSON đã có field rõ ràng nhưng class không có setter:

```java
public final class Coordinates {
    private final double latitude;
    private final double longitude;

    @JsonCreator
    public Coordinates(
            @JsonProperty("latitude") double latitude,
            @JsonProperty("longitude") double longitude
    ) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}
```

Creator phù hợp khi dữ liệu đã có cấu trúc tương ứng với tham số constructor. Nếu cần chấp nhận nhiều shape khác nhau hoặc kết hợp quy tắc phức tạp, mới cân nhắc deserializer.

### 8.3. @JsonFormat và Java Time module

Nếu input là ngày giờ theo pattern đã biết:

```java
public class AuditRecord {
    @JsonFormat(pattern = "dd/MM/yyyy")
    private LocalDate createdOn;
}
```

Với Jackson 2.x, cần đăng ký `JavaTimeModule` cho các kiểu `java.time`. Chỉ viết deserializer nếu format có quy tắc đặc thù mà formatter chuẩn không thể diễn đạt, ví dụ nhiều pattern legacy cùng tồn tại hoặc đơn vị timestamp phụ thuộc field.

### 8.4. @JsonSetter điều khiển null

Nếu vấn đề chỉ là JSON null:

```java
public class Profile {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Không cần custom deserializer chỉ để giữ giá trị initializer khi input null.

### 8.5. Coercion configuration cho quy tắc chung

Jackson 2.12+ có API coercion để kiểm soát cách một nhóm kiểu xử lý input shape. Ví dụ, nếu toàn bộ integer property phải từ chối JSON string:

```java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Đây là cấu hình phạm vi logical type. Nếu chỉ một property có contract riêng, property-level converter/deserializer thường ít ảnh hưởng hơn.

## 9. Đặt deserializer ở đâu?

Jackson cho phép gắn deserializer ở nhiều phạm vi. Nên chọn phạm vi nhỏ nhất đáp ứng đúng hợp đồng.

| Phạm vi | Cách khai báo | Ảnh hưởng |
|---|---|---|
| Kiểu Java | `@JsonDeserialize(using = ...)` trên class | Mọi nơi deserialize kiểu đó khi annotation được áp dụng |
| Property | Annotation trên field/getter/setter/parameter | Một property cụ thể |
| Content của container | `@JsonDeserialize(contentUsing = ...)` | Phần tử của collection/map/array |
| Mapper/module | `SimpleModule.addDeserializer(...)` | Kiểu được đăng ký trong mapper |
| Kiểu bên thứ ba | Mix-in hoặc module | Thêm cấu hình mà không sửa class gốc |

Ví dụ custom deserializer cho phần tử collection:

```java
public class ImportBatch {
    @JsonDeserialize(contentUsing = MoneyDeserializer.class)
    private List<Money> amounts;

    // Getter/setter
}
```

Nếu deserializer đã đăng ký toàn cục cho `Money.class`, không cần lặp lại `contentUsing`. Dùng content deserializer khi chỉ collection này cần quy tắc khác.

## 10. Deserializer theo ngữ cảnh: ContextualDeserializer

Một số kiểu cần đọc khác nhau tùy property. Ví dụ một kiểu `Identifier` được dùng cho user ID và invoice ID, nhưng mỗi property có prefix hoặc format riêng. Khi đó, một deserializer stateless duy nhất có thể không đủ thông tin.

Jackson hỗ trợ `ContextualDeserializer`. Nó cho phép deserializer nhận `BeanProperty` và tạo một instance đã được cấu hình theo property hiện tại.

Khung triển khai:

```java
public final class IdentifierDeserializer
        extends StdDeserializer<Identifier>
        implements ContextualDeserializer {

    private final String requiredPrefix;

    public IdentifierDeserializer() {
        this(null);
    }

    private IdentifierDeserializer(String requiredPrefix) {
        super(Identifier.class);
        this.requiredPrefix = requiredPrefix;
    }

    @Override
    public JsonDeserializer<?> createContextual(
            DeserializationContext context,
            BeanProperty property
    ) throws JsonMappingException {
        if (property == null) {
            return this;
        }

        // Đọc annotation hoặc metadata của property
        // rồi trả về deserializer đã cấu hình.
        return new IdentifierDeserializer(requiredPrefix);
    }

    @Override
    public Identifier deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        String value = parser.getValueAsString();

        if (value == null) {
            return (Identifier) context.handleUnexpectedToken(
                    Identifier.class,
                    parser
            );
        }

        if (requiredPrefix != null && !value.startsWith(requiredPrefix)) {
            throw JsonMappingException.from(
                    parser,
                    "Identifier không có prefix mong đợi"
            );
        }

        return new Identifier(value);
    }
}
```

Đây là skeleton minh họa vòng đời contextualization; ứng dụng thực tế cần cung cấp annotation hoặc metadata để lấy `requiredPrefix` từ property. Có thể định nghĩa annotation riêng như `@IdentifierPrefix("USR-")`, đọc annotation qua `property.getAnnotation(...)`, rồi tạo deserializer mới chứa cấu hình đó.

Điều quan trọng là không lưu trạng thái của từng lần parse vào field mutable của deserializer dùng chung. Jackson có thể tái sử dụng deserializer. Contextual instance nên giữ cấu hình bất biến; dữ liệu của một record phải nằm trong biến cục bộ của `deserialize()`.

## 11. Xử lý null và property bị thiếu

Một custom deserializer không phải lúc nào cũng được gọi khi JSON value là null. Trong databinding chuẩn, Jackson thường xử lý token null thông qua null value provider và `getNullValue()`; `deserialize()` chủ yếu xử lý token không-null.

Vì vậy, nếu kiểu đích không chấp nhận null, có thể chọn một trong các cách:

- Đặt `@JsonSetter(nulls = Nulls.FAIL)` trên property.
- Dùng Bean Validation như `@NotNull` sau deserialize.
- Override `getNullValue(DeserializationContext)` trong custom deserializer nếu quy tắc null thuộc chính kiểu đó.

Property bị thiếu là tình huống khác: deserializer của property không được gọi vì không có token tương ứng. Nếu field bắt buộc phải xuất hiện, cần required-property/creator semantics hoặc validation sau khi tạo object.

Không nên xem `null` và missing là cùng một trường hợp. Với API cập nhật từng phần, missing có thể nghĩa là giữ nguyên; null có thể nghĩa là xóa; giá trị cụ thể nghĩa là thay thế.

## 12. Xử lý unknown field trong custom deserializer

Khi Jackson tự deserialize POJO, `FAIL_ON_UNKNOWN_PROPERTIES` có thể quyết định cách xử lý field không được nhận diện. Nhưng khi ứng dụng viết custom deserializer và tự duyệt token, chính deserializer chịu trách nhiệm cho các field nó gặp.

Ví dụ trong Money deserializer:

```java
if ("amount".equals(fieldName)) {
    amount = readAmount(parser);
} else if ("currency".equals(fieldName)) {
    currency = readCurrency(parser);
} else {
    parser.skipChildren();
    throw JsonMappingException.from(
            parser,
            "Unknown Money property: " + fieldName
    );
}
```

Nếu thay đoạn throw bằng `skipChildren()` đơn thuần, field lạ sẽ bị bỏ qua bất kể cấu hình unknown-property thông thường. Đây là quyết định riêng của custom deserializer.

Hãy xác định một trong các policy:

- Strict: từ chối field lạ để phát hiện producer gửi sai schema.
- Tolerant: bỏ qua field lạ để hỗ trợ mở rộng tương thích.
- Preserve: giữ field lạ trong `Map<String, JsonNode>` hoặc tree để round-trip.

Không nên vô tình bỏ qua field lạ chỉ vì parser cần tiến đến token tiếp theo.

## 13. Báo lỗi đúng cách

Custom deserializer nên ném exception mapping có thông tin về token và nguyên nhân. Tránh trả null cho input sai hoặc catch exception rồi bỏ qua, vì lỗi sẽ xuất hiện muộn ở tầng nghiệp vụ.

Các loại exception thường gặp:

- `JsonMappingException`: cấu trúc hoặc giá trị JSON không ánh xạ được vào kiểu đích.
- `MismatchedInputException`: token/input shape không phù hợp với kiểu mong đợi.
- `InvalidFormatException`: giá trị có format không hợp lệ cho kiểu đích.
- `JsonParseException`: cú pháp JSON sai ở parser layer.

Ví dụ:

```java
if (parser.currentToken() != JsonToken.VALUE_STRING) {
    return (Money) context.handleUnexpectedToken(Money.class, parser);
}
```

Hoặc tạo lỗi cụ thể:

```java
throw JsonMappingException.from(
        parser,
        "currency phải là chuỗi mã ISO 4217"
);
```

Khi exception phát sinh trong property binding, Jackson thường bổ sung path gồm tên field và vị trí trong object graph. Điều này giúp xác định lỗi nằm ở `invoice.total.currency` thay vì chỉ biết toàn bộ JSON không hợp lệ.

Không đưa raw payload nhạy cảm vào message exception. Thông báo nên mô tả field/token/constraint, còn log cần tuân thủ chính sách masking.

## 14. Deserializer có generic type và collection

Nếu custom deserializer xử lý một kiểu generic như `Envelope<T>`, cần quan tâm tới `JavaType` và contextualization. Không thể giả định type parameter đã được giải quyết chỉ bằng cách viết `Envelope.class`.

Với các collection thông thường, Jackson đã có deserializer chuẩn và biết element type từ `List<User>`. Không cần tự viết deserializer cho list chỉ để lặp qua từng phần tử.

Nếu một generic wrapper có cấu trúc đặc thù, có thể:

- Dùng `@JsonCreator` và property type đầy đủ nếu cấu trúc đã rõ.
- Dùng `JsonNode` cho nhánh động rồi `treeToValue()` với `JavaType` đã dựng.
- Triển khai `ContextualDeserializer` để lấy contained type từ property.
- Dùng deserializer chuẩn của kiểu con thông qua `DeserializationContext` thay vì tự parse lại mọi kiểu.

Khi gọi deserializer khác từ custom deserializer, phải tránh tự tìm lại chính deserializer đang chạy, vì có thể tạo đệ quy. Nếu cần delegate, xác định kiểu nguồn/kiểu con cụ thể và dùng API contextual value deserializer đúng cách.

## 15. Hiệu năng và khả năng tái sử dụng

Custom deserializer được Jackson cache và tái sử dụng trong nhiều lần đọc. Do đó:

- Giữ deserializer stateless hoặc chỉ lưu cấu hình bất biến.
- Không giữ `JsonParser`, object đang deserialize hoặc dữ liệu request trong field.
- Không tạo `ObjectMapper` mới bên trong mỗi lần `deserialize()`.
- Tránh serialize node thành chuỗi rồi parse lại nếu có thể đọc trực tiếp token.
- Dùng tree model khi cấu trúc đủ phức tạp để tree làm code rõ ràng, nhưng cân nhắc bộ nhớ cho payload lớn.
- Dùng streaming parser khi chỉ cần đọc vài field từ object lớn.
- Đăng ký module trước khi mapper được chia sẻ trong ứng dụng.

Một custom deserializer viết tốt có thể nhanh hơn nhiều lớp chuyển đổi thủ công, nhưng một deserializer phức tạp cũng có thể làm tăng allocation và chi phí bảo trì. Hãy đo trên payload thực tế nếu hiệu năng là lý do chính để tùy biến.

## 16. Bảo mật khi đọc dữ liệu không tin cậy

Deserializer là code chạy trên dữ liệu do producer gửi. Không nên coi input đã hợp lệ chỉ vì parser tạo được token.

Các nguyên tắc quan trọng:

- Giới hạn kích thước request, độ sâu lồng nhau và độ dài token bằng parser constraints phù hợp phiên bản.
- Kiểm tra token type trước khi gọi getter.
- Giới hạn độ dài string và số lượng phần tử nếu domain có giới hạn.
- Không tạo class theo tên tùy ý trong JSON.
- Không thực hiện truy vấn database hoặc HTTP side effect trong quá trình parse nếu có thể tách sang service.
- Không để một field JSON điều khiển đường dẫn file, tên class hoặc biểu thức thực thi.
- Xử lý rõ duplicate field nếu contract yêu cầu; có thể bật strict duplicate detection ở parser.
- Trả lỗi mapping có kiểm soát, tránh lộ dữ liệu nhạy cảm.

Đặc biệt, custom deserializer không thay thế allowlist subtype. Nếu payload có discriminator polymorphic, hãy cấu hình subtype logic rõ ràng và không bật class-name default typing rộng cho JSON không tin cậy.

## 17. Kiểm thử custom deserializer

Không chỉ test một input hợp lệ. Một deserializer là boundary của wire contract nên cần test các token shape và trường hợp biên.

Với `MoneyDeserializer`, có thể dùng JUnit:

```java
class MoneyDeserializerTest {
    private final ObjectMapper mapper = createMapper();

    private ObjectMapper createMapper() {
        SimpleModule module = new SimpleModule();
        module.addDeserializer(Money.class, new MoneyDeserializer());

        return JsonMapper.builder()
                .addModule(module)
                .build();
    }

    @Test
    void shouldReadLegacyString() throws Exception {
        Invoice invoice = mapper.readValue(
                """
                {"total":"125.50 VND"}
                """,
                Invoice.class
        );

        assertEquals(
                new BigDecimal("125.50"),
                invoice.getTotal().getAmount()
        );
        assertEquals("VND", invoice.getTotal().getCurrency().getCurrencyCode());
    }

    @Test
    void shouldReadStructuredObject() throws Exception {
        Invoice invoice = mapper.readValue(
                """
                {
                  "total": {
                    "amount": 125.50,
                    "currency": "VND"
                  }
                }
                """,
                Invoice.class
        );

        assertEquals(
                new BigDecimal("125.50"),
                invoice.getTotal().getAmount()
        );
    }

    @Test
    void shouldRejectUnsupportedTokenShape() {
        assertThrows(
                JsonMappingException.class,
                () -> mapper.readValue(
                        """
                        {"total": true}
                        """,
                        Invoice.class
                )
        );
    }

    @Test
    void shouldRejectMissingCurrency() {
        assertThrows(
                JsonMappingException.class,
                () -> mapper.readValue(
                        """
                        {"total":{"amount":125.50}}
                        """,
                        Invoice.class
                )
        );
    }
}
```

Các test này xác nhận hai format được hỗ trợ, token boolean bị từ chối và field bắt buộc không thể thiếu. Có thể bổ sung test cho currency sai, amount sai format, field lạ, null và số decimal có nhiều chữ số.

### 17.1. Kiểm tra cả contract đầu vào và đầu ra

Deserializer chỉ kiểm soát chiều đọc. Nếu serialize `Money` ra một format khác, cần định nghĩa serializer hoặc dùng serializer mặc định tương ứng.

Ví dụ, deserializer chấp nhận cả chuỗi legacy và object mới, nhưng serializer mặc định có thể phát object theo property của class. Điều đó có thể là chủ ý: đọc nhiều phiên bản cũ nhưng chỉ phát canonical format mới.

Nếu muốn output theo định dạng riêng, dùng `JsonSerializer` hoặc `@JsonSerialize`; đừng cố đưa logic ghi vào deserializer.

## 18. Các lỗi triển khai thường gặp

**Viết deserializer cho việc đổi tên field.** Dùng `@JsonProperty` hoặc `@JsonAlias` sẽ rõ hơn.

**Tự parse ngày giờ đã được hỗ trợ.** Đăng ký Java Time module và dùng `@JsonFormat` nếu format chuẩn đáp ứng yêu cầu.

**Không kiểm tra token type.** Gọi `getText()` hoặc `getDecimalValue()` trên token không phù hợp có thể gây lỗi khó hiểu. Kiểm tra `currentToken()` trước.

**Quên null được xử lý riêng.** Explicit JSON null thường đi qua `getNullValue()`/null provider, không nhất thiết gọi `deserialize()`. Dùng `Nulls` hoặc override null handling phù hợp.

**Nhầm missing với null.** Field không xuất hiện không gọi deserializer; null có mặt được xử lý theo null policy.

**Nuốt exception và trả null.** Dữ liệu sai trở thành object thiếu giá trị và lỗi phát sinh ở nơi khác. Hãy ném mapping exception có ngữ cảnh.

**Tạo ObjectMapper mới trong mỗi lần parse.** Điều này tốn tài nguyên và có thể làm mất cấu hình/module chung. Dùng mapper đã cấu hình.

**Lưu trạng thái request trong field deserializer.** Jackson có thể tái sử dụng deserializer. Chỉ lưu cấu hình bất biến và dùng biến cục bộ cho mỗi lần đọc.

**Bỏ qua unknown field ngoài ý muốn.** Khi tự duyệt token, deserializer phải tự quyết định field lạ được từ chối, bỏ qua hay lưu lại.

**Tự gọi lại chính deserializer.** Delegation sai cách có thể tạo đệ quy vô hạn. Xác định rõ kiểu nguồn hoặc kiểu con cần delegate.

**Dùng deserializer để truy vấn persistence.** Việc đọc JSON nên chuyển đổi dữ liệu; service mới giải quyết ID, quyền truy cập và transaction.

## 19. Quy trình quyết định có cần deserializer riêng hay không

Khi gặp một property không đọc được như mong muốn, thực hiện theo trình tự:

1. **Kiểm tra JSON thực tế:** token là string, number, object, array, null hay field bị thiếu?
2. **Kiểm tra kiểu Java đích:** có generic type bị mất hoặc kiểu không phù hợp không?
3. **Kiểm tra cấu hình mapper:** module, date/time, coercion, naming và null policy.
4. **Thử annotation chuẩn:** `@JsonProperty`, `@JsonAlias`, `@JsonFormat`, `@JsonCreator`, `@JsonSetter`.
5. **Cân nhắc converter:** nếu chỉ cần chuyển một kiểu nguồn đơn giản thành kiểu đích.
6. **Chọn tree model:** nếu schema chỉ biết sau khi kiểm tra discriminator hoặc một nhánh JSON.
7. **Viết custom deserializer:** khi cần điều khiển token shape, đọc nhiều field, chuẩn hóa hoặc kiểm tra cấu trúc đặc thù.
8. **Chọn phạm vi đăng ký:** property, class, content hoặc module; dùng phạm vi nhỏ nhất đáp ứng contract.
9. **Định nghĩa null/unknown/error policy:** không để hành vi phụ thuộc ngẫu nhiên vào mặc định.
10. **Kiểm thử dữ liệu thật và trường hợp biên:** cả input hợp lệ, sai format, thiếu, null, token không đúng và payload lớn.

## 20. Kết luận

Databinding mặc định của Jackson nên là lựa chọn đầu tiên khi cấu trúc JSON tương ứng với kiểu Java và chỉ cần các quy tắc ánh xạ thông thường. Annotation, module, coercion configuration, creator constructor và converter đã giải quyết được nhiều nhu cầu mà không cần tự điều khiển parser.

Custom deserializer phù hợp khi cùng một kiểu đích phải nhận nhiều hình dạng JSON, khi cần kết hợp nhiều token, áp dụng quy tắc parse đặc thù hoặc kiểm soát chặt token type và lỗi. Hãy giữ deserializer stateless, xử lý rõ null và unknown field, ném mapping exception có ngữ cảnh, đồng thời đặt logic nghiệp vụ và truy xuất persistence ở tầng thích hợp. Chọn đúng mức tùy biến giúp wire contract linh hoạt mà code vẫn dễ kiểm thử và bảo trì.

## Tài liệu tham khảo

- [Jackson Databind — JsonDeserializer API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonDeserializer.html)
- [Jackson Databind — StdDeserializer API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/std/StdDeserializer.html)
- [Jackson Databind — JsonDeserialize annotation](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonDeserialize.html)
- [Jackson Databind — SimpleModule API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/module/SimpleModule.html)
- [Jackson Databind — ContextualDeserializer API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/ContextualDeserializer.html)
- [Jackson Databind — StdConverter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/util/StdConverter.html)

