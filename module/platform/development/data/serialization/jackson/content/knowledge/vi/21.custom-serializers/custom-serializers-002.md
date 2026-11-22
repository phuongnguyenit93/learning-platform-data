# Thiết kế serializer cho một kiểu giá trị nghiệp vụ

Trong ứng dụng Java, nhiều kiểu dữ liệu đại diện cho khái niệm nghiệp vụ có quy tắc riêng: tiền tệ (`Money`), khoảng thời gian (`DateRange`), số điện thoại (`PhoneNumber`), mã đơn hàng hoặc tọa độ. Những kiểu này thường được thiết kế thành value object để bảo vệ invariant và cung cấp hành vi có ý nghĩa.

Khi đưa value object vào JSON, cấu trúc Java không phải lúc nào cũng là cấu trúc JSON mà API muốn công bố. Một kiểu `Money` có thể được biểu diễn thành object gồm số tiền và mã tiền tệ, thành chuỗi `"125000.50 VND"`, hoặc thành một cấu trúc khác theo hợp đồng. Nếu cách ánh xạ mặc định của Jackson không đáp ứng hợp đồng, có thể viết custom serializer.

Jackson cung cấp `JsonSerializer<T>` và lớp tiện ích `StdSerializer<T>` để định nghĩa cách ghi một giá trị Java thành JSON. Serializer dùng `JsonGenerator` để ghi token và `SerializerProvider` để truy cập các serializer/dịch vụ của Databind. Sau đó, serializer được gắn bằng `@JsonSerialize` hoặc đăng ký qua module như `SimpleModule`.

## 1. Khi nào cần custom serializer?

Giả sử ứng dụng có value object `Money`:

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Kiểu này mang hai thông tin: số tiền và loại tiền. Nó có thể xuất hiện trong nhiều domain object:

~~~java
public class InvoiceResponse {
    private String invoiceNo;
    private Money total;
    private Money tax;

    // Getter và setter.
}
~~~

Nếu không có cấu hình riêng, Jackson có thể serialize `Money` dựa trên các property mà nó nhận diện từ record hoặc class. Điều đó có thể tạo ra JSON phù hợp về mặt kỹ thuật nhưng chưa chắc phù hợp với hợp đồng API.

Ví dụ API muốn:

~~~json
{
  "invoiceNo": "INV-2026-001",
  "total": {
    "amount": "125000.50",
    "currency": "VND"
  },
  "tax": {
    "amount": "10000.00",
    "currency": "VND"
  }
}
~~~

Custom serializer hữu ích khi:

- JSON cần có cấu trúc khác với property Java mặc định.
- Một value object cần được biểu diễn thống nhất ở nhiều DTO.
- Cần chuẩn hóa định dạng, ví dụ mã tiền tệ viết hoa hoặc timestamp theo hợp đồng.
- Cần ẩn chi tiết nội bộ của value object khỏi JSON.
- Cần ghi một giá trị dưới dạng scalar hoặc object có cấu trúc riêng.
- Cần áp dụng quy tắc serialization chuyên biệt mà annotation đơn giản không diễn đạt được.

Không nên viết serializer chỉ để thay đổi một tên field đơn giản nếu `@JsonProperty` đã giải quyết được. Serializer tùy biến tạo thêm mã cần kiểm thử và bảo trì; chỉ dùng khi hợp đồng biểu diễn thực sự cần logic riêng.

## 2. Xác định hợp đồng JSON trước khi viết code

Trước khi triển khai serializer, hãy quyết định JSON phải biểu diễn điều gì. Cùng một `Money` có nhiều hình thức hợp lệ nhưng không tương đương.

### 2.1. Dạng object

~~~json
{
  "amount": "125000.50",
  "currency": "VND"
}
~~~

Ưu điểm là tên field rõ nghĩa, dễ mở rộng thêm metadata như đơn vị hoặc nguồn quy đổi. Consumer có thể kiểm tra từng trường. Đây là lựa chọn phù hợp cho API nghiệp vụ cần mô tả rõ giá trị và loại tiền.

### 2.2. Dạng chuỗi

~~~json
"125000.50 VND"
~~~

Dạng này ngắn gọn, dễ hiển thị, nhưng consumer phải parse chuỗi theo một format cụ thể. Nếu thay đổi dấu phân cách, quy ước dấu thập phân hoặc vị trí mã tiền tệ, hợp đồng có thể bị ảnh hưởng.

### 2.3. Dạng số JSON

~~~json
{
  "amount": 125000.50,
  "currency": "VND"
}
~~~

JSON number thuận tiện cho nhiều client, nhưng một số nền tảng như JavaScript thường parse number thành kiểu dấu phẩy động binary64. Giá trị tài chính có thể mất độ chính xác ở phía consumer. Nếu yêu cầu giữ chính xác thập phân xuyên nền tảng, biểu diễn amount bằng chuỗi thập phân là một lựa chọn an toàn hơn; nếu hợp đồng bắt buộc number, cần tài liệu hóa miền giá trị và độ chính xác.

Trong bài này, serializer dùng object với `amount` là chuỗi thập phân và `currency` là mã ISO 4217. Đây là quyết định hợp đồng cho ví dụ, không phải quy tắc bắt buộc của Jackson hay mọi API.

## 3. Viết serializer bằng StdSerializer

Jackson có thể triển khai trực tiếp `JsonSerializer<Money>`. Trong thực tế, `StdSerializer<Money>` thường tiện hơn vì cung cấp sẵn kiểu đích và một số hành vi nền tảng.

~~~java
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

        generator.writeStartObject();
        generator.writeStringField(
            "amount",
            value.amount().toPlainString()
        );
        generator.writeStringField(
            "currency",
            value.currency().getCurrencyCode()
        );
        generator.writeEndObject();
    }
}
~~~

Giải thích:

- `extends StdSerializer<Money>` khai báo serializer dành cho kiểu `Money`.
- `super(Money.class)` cung cấp kiểu Java mà serializer xử lý.
- `serialize(...)` được Jackson gọi khi cần ghi một giá trị `Money` khác null.
- `JsonGenerator` ghi cấu trúc JSON theo thứ tự token.
- `SerializerProvider` chứa ngữ cảnh serialization và các serializer đã đăng ký; ví dụ này chưa cần gọi trực tiếp provider.
- `toPlainString()` tạo chuỗi thập phân không dùng ký pháp số mũ, giúp hợp đồng ví dụ dễ đọc.
- `Currency.getCurrencyCode()` trả mã tiền tệ như `VND`, `USD`, `EUR`.

Với `BigDecimal`, không nên gọi `doubleValue()` rồi ghi thành số dấu phẩy động nếu cần giữ chính xác. Nếu hợp đồng muốn JSON number thay vì chuỗi, có thể thay cách ghi amount bằng:

~~~java
generator.writeNumberField("amount", value.amount());
~~~

`JsonGenerator` tự escape chuỗi và ghi token đúng cấu trúc. Không tự ghép JSON bằng nối chuỗi hoặc `writeRaw()` cho dữ liệu nghiệp vụ; làm vậy dễ tạo JSON không hợp lệ hoặc bỏ sót escaping.

## 4. Gắn serializer bằng @JsonSerialize

Có thể gắn serializer ngay trên kiểu value object:

~~~java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = MoneySerializer.class)
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Khi Jackson gặp `Money`, annotation chỉ định serializer cần dùng. Cách này phù hợp khi kiểu `Money` do ứng dụng sở hữu và một biểu diễn JSON duy nhất được dùng ở mọi nơi.

Cũng có thể đặt annotation trên property nếu chỉ một thuộc tính cần serializer riêng:

~~~java
public class InvoiceResponse {
    @JsonSerialize(using = MoneySerializer.class)
    private Money total;

    private Money internalCalculation;
}
~~~

Trong ví dụ, `total` dùng serializer tùy biến; `internalCalculation` vẫn theo quy tắc serializer đang áp dụng cho kiểu `Money` ở nơi khác. Hãy tránh tạo nhiều biểu diễn khác nhau cho cùng một value object nếu hợp đồng không có lý do rõ ràng.

## 5. Đăng ký serializer bằng SimpleModule

Nếu không muốn sửa class `Money`, hoặc muốn gom quy tắc serialization vào cấu hình Jackson, hãy đăng ký serializer qua module:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule moneyModule = new SimpleModule("MoneyModule");
moneyModule.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(moneyModule);
~~~

Sau khi đăng ký, các property kiểu `Money` được xử lý bằng `MoneySerializer` theo cấu hình module.

Có thể dùng `JsonMapper` builder:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(moneyModule)
    .build();
~~~

### 5.1. Khi nào dùng annotation, khi nào dùng module?

| Tiêu chí | `@JsonSerialize` | `SimpleModule` |
|---|---|---|
| Vị trí cấu hình | Trên class hoặc property | Tại cấu hình mapper |
| Có cần sửa class nguồn? | Có nếu đặt trên class; không nếu đặt trên property của DTO | Không |
| Tác động | Kiểu hoặc property được gắn annotation | Các mapper đăng ký module |
| Phù hợp | Kiểu thuộc ứng dụng, có một quy tắc cố định | Kiểu bên thứ ba hoặc chính sách theo ứng dụng/tích hợp |
| Khả năng tái sử dụng | Annotation đi cùng class/property | Module có thể dùng ở nhiều mapper |

Hãy chọn một nơi làm nguồn cấu hình rõ ràng. Nếu annotation trên kiểu và module cùng đăng ký serializer cho một kiểu, cần kiểm thử serializer thực tế được chọn trong cấu hình của dự án; tránh để nhiều cơ chế cùng định nghĩa một hợp đồng mà không có chủ đích.

### 5.2. Đăng ký trong Spring Boot

Với Spring Boot, có thể cung cấp module bean để mapper do framework quản lý tự đăng ký:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfiguration {
    @Bean
    public Module moneyModule() {
        SimpleModule module = new SimpleModule("MoneyModule");
        module.addSerializer(Money.class, new MoneySerializer());
        return module;
    }
}
~~~

Spring Boot thường tự phát hiện các bean `Module` và đăng ký vào `ObjectMapper` được auto-configure. Cách tích hợp cụ thể có thể phụ thuộc phiên bản Boot và cách ứng dụng đã tùy chỉnh mapper. Không tạo `new ObjectMapper()` trong controller chỉ để sử dụng serializer, vì mapper đó có thể thiếu module và chính sách chung của ứng dụng.

## 6. Dùng SerializerProvider khi cần serialize giá trị lồng nhau

Một serializer nghiệp vụ có thể cần ghi thêm giá trị thuộc kiểu khác. Thay vì tự tạo serializer hoặc chuyển thành chuỗi thủ công, hãy dùng `SerializerProvider` để ủy quyền cho Jackson:

~~~java
provider.defaultSerializeValue(value.someNestedValue(), generator);
~~~

Phương thức này sử dụng serializer phù hợp đã đăng ký cho giá trị lồng nhau. Nếu giá trị là null, provider dùng null serializer mặc định.

Ví dụ một value object phức tạp có trường `effectiveAt`:

~~~java
generator.writeFieldName("effectiveAt");
provider.defaultSerializeValue(value.effectiveAt(), generator);
~~~

Nếu `effectiveAt` là `Instant`, mapper cần có module Java Time phù hợp và cấu hình định dạng đúng. Custom serializer không nên tự format mọi kiểu con bằng `toString()` vì có thể phá vỡ naming strategy, date format hoặc serializer chuyên biệt của ứng dụng.

## 7. Xử lý null đúng cách

Jackson thường không gọi phương thức `serialize()` của serializer giá trị cho property null. Việc ghi null được xử lý bởi null serializer của `SerializerProvider` và chính sách null của property/container.

Ví dụ:

~~~java
public class InvoiceResponse {
    private Money total;
}
~~~

Nếu `total == null`, Jackson thường ghi `"total": null` theo chính sách mặc định. Nếu ứng dụng dùng `@JsonInclude(Include.NON_NULL)`, property có thể bị bỏ khỏi JSON.

Không cần viết `if (value == null)` trong `MoneySerializer.serialize()` cho luồng thông thường, vì serializer được gọi với giá trị khác null. Nếu code tự ghi giá trị con có thể null, hãy dùng:

~~~java
provider.defaultSerializeNull(generator);
~~~

hoặc để `defaultSerializeValue()` xử lý null.

Null và một `Money` có amount bằng zero là hai trường hợp khác nhau:

~~~json
{
  "total": null
}
~~~

khác với:

~~~json
{
  "total": {
    "amount": "0.00",
    "currency": "VND"
  }
}
~~~

Đừng biến null thành zero trong serializer nếu hợp đồng nghiệp vụ không quy định rõ. Serializer nên biểu diễn giá trị; việc thiếu, null hay zero phải được quyết định ở domain và DTO.

## 8. Giữ serializer không trạng thái và an toàn khi dùng nhiều thread

`ObjectMapper` thường được chia sẻ giữa nhiều request. Serializer được đăng ký trong mapper cũng có thể được gọi đồng thời từ nhiều thread. Vì vậy, serializer nên không trạng thái (stateless): không giữ dữ liệu của lần serialize trước trong field mutable.

Không nên giữ một `StringBuilder` mutable dùng chung trong serializer. Nếu cần biến tạm, tạo biến local bên trong `serialize()`:

~~~java
String amountText = value.amount().toPlainString();
generator.writeStringField("amount", amountText);
~~~

Không lưu `JsonGenerator`, object đang serialize hoặc request context vào field serializer. Nếu cần thông tin theo property/request, hãy dùng cơ chế contextual hoặc inject/configure serializer theo thiết kế thread-safe.

## 9. Serializer theo ngữ cảnh với ContextualSerializer

Một số kiểu cần format khác nhau theo property. Ví dụ `Money` có thể được hiển thị theo dạng chuỗi ở một field nhưng theo object ở field khác, hoặc scale/đơn vị phụ thuộc annotation. Khi đó, một serializer cố định có thể chưa đủ.

Jackson có `ContextualSerializer`, cho phép serializer nhận metadata của property đang sử dụng nó và tạo một instance phù hợp.

Ví dụ annotation tùy chỉnh khai báo format:

~~~java
@Target({ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface MoneyFormat {
    Style value() default Style.OBJECT;

    enum Style {
        OBJECT,
        STRING
    }
}
~~~

Serializer contextual có thể đọc annotation từ `BeanProperty` trong `createContextual(...)`, rồi trả về instance cấu hình theo style:

~~~java
public final class ContextualMoneySerializer
        extends StdSerializer<Money>
        implements ContextualSerializer {

    private final MoneyFormat.Style style;

    public ContextualMoneySerializer() {
        this(MoneyFormat.Style.OBJECT);
    }

    private ContextualMoneySerializer(MoneyFormat.Style style) {
        super(Money.class);
        this.style = style;
    }

    @Override
    public JsonSerializer<?> createContextual(
            SerializerProvider provider,
            BeanProperty property) {

        MoneyFormat annotation = property == null
            ? null
            : property.getAnnotation(MoneyFormat.class);

        MoneyFormat.Style selected = annotation == null
            ? MoneyFormat.Style.OBJECT
            : annotation.value();

        return new ContextualMoneySerializer(selected);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        if (style == MoneyFormat.Style.STRING) {
            generator.writeString(
                value.amount().toPlainString() + " "
                    + value.currency().getCurrencyCode()
            );
            return;
        }

        generator.writeStartObject();
        generator.writeStringField("amount", value.amount().toPlainString());
        generator.writeStringField(
            "currency",
            value.currency().getCurrencyCode()
        );
        generator.writeEndObject();
    }
}
~~~

Phác thảo này cần các import Jackson (`BeanProperty`, `JsonSerializer`, `ContextualSerializer`, `JsonGenerator`, `SerializerProvider`, `StdSerializer`) và import annotation Java. Sau đó có thể đặt `@MoneyFormat(MoneyFormat.Style.STRING)` trên property cần dạng chuỗi.

Điểm quan trọng:

- `createContextual()` có thể được gọi trong quá trình Jackson resolve serializer cho property.
- Không sửa instance dùng chung; trả về instance mới bất biến chứa style được chọn.
- `property` có thể null trong một số ngữ cảnh root hoặc khi không có property cụ thể; luôn xử lý trường hợp này.
- Nếu chỉ có một format toàn hệ thống, không cần contextual serializer; `StdSerializer` đơn giản dễ bảo trì hơn.

## 10. Serializer không tự cung cấp deserializer

Custom serializer chỉ định cách ghi Java thành JSON. Nó không tự định nghĩa cách đọc JSON trở lại thành value object.

Nếu API cần round-trip `Money`, cần có deserializer tương ứng hoặc một cơ chế creator mà Jackson có thể dùng. Có thể đăng ký cả hai trong module:

~~~java
SimpleModule moneyModule = new SimpleModule("MoneyModule");
moneyModule.addSerializer(Money.class, new MoneySerializer());
moneyModule.addDeserializer(Money.class, new MoneyDeserializer());
~~~

`MoneyDeserializer` phải xác thực `amount` và `currency`, parse `BigDecimal` và tra cứu mã tiền tệ hợp lệ. Nếu JSON dùng amount dạng chuỗi:

~~~java
BigDecimal amount = new BigDecimal(amountNode.textValue());
Currency currency = Currency.getInstance(currencyNode.textValue());
return new Money(amount, currency);
~~~

Không nên cho rằng serialize và deserialize luôn là hai thao tác đối xứng tự động. Hãy xác định rõ:

- JSON có chấp nhận amount dạng number hay chỉ string?
- Có chấp nhận khoảng trắng hoặc dấu phân cách khác không?
- Mã currency có phân biệt hoa/thường không?
- Currency không hợp lệ được báo lỗi như thế nào?
- Scale có được giữ nguyên hay chuẩn hóa theo quy tắc nghiệp vụ?
- Có chấp nhận null hay không?

Nếu ứng dụng chỉ trả response và không bao giờ nhận `Money` từ JSON, custom serializer đơn lẻ có thể đủ. Nếu dùng kiểu này trong request DTO, cần kiểm thử cả chiều đọc.

## 11. Kiểm tra invariant trước khi serialize

Value object nên bảo vệ invariant ngay từ lúc tạo. Ví dụ `Money` không cho phép amount hoặc currency null. Các quy tắc như scale tối đa, làm tròn, số tiền âm có được phép hay không cần nằm ở domain constructor/factory hoặc nghiệp vụ.

Serializer không nên âm thầm sửa dữ liệu:

~~~java
// Không nên tự ý làm tròn trong serializer.
BigDecimal normalized = value.amount().setScale(2, RoundingMode.HALF_UP);
~~~

Việc làm tròn có thể thay đổi giá trị nghiệp vụ. Nếu hợp đồng yêu cầu hai chữ số thập phân, hãy xác định rõ domain có lưu scale cố định hay serializer chỉ định dạng theo một quy tắc đã thống nhất. Nếu có làm tròn, phải có chính sách và test riêng.

Nếu value object không hợp lệ, hãy để constructor/factory từ chối trước khi serializer được gọi. Nếu vẫn có thể nhận trạng thái không hợp lệ do legacy code hoặc reflection, serializer có thể ném lỗi ánh xạ thay vì phát JSON sai:

~~~java
if (value.amount() == null || value.currency() == null) {
    throw JsonMappingException.from(
        generator,
        "Money must contain amount and currency"
    );
}
~~~

Với record có compact constructor và `Objects.requireNonNull`, kiểm tra này thường đã được thực hiện từ lúc tạo object.

## 12. Không tự tạo ObjectMapper bên trong serializer

Một anti-pattern là gọi `new ObjectMapper()` trong `serialize()` để serialize một field con:

~~~java
// Không nên.
String nestedJson = new ObjectMapper().writeValueAsString(value.details());
generator.writeStringField("details", nestedJson);
~~~

Vấn đề:

- Tạo mapper mới lặp lại, gây chi phí và bỏ qua cấu hình ứng dụng.
- Có thể thiếu module, naming strategy, serializer hoặc date format.
- JSON con bị ghi thành một chuỗi chứa JSON thay vì object JSON lồng nhau.
- Dễ tạo vòng serialize lồng nhau khó kiểm soát.

Hãy ghi cấu trúc trực tiếp bằng generator hoặc ủy quyền cho provider:

~~~java
generator.writeFieldName("details");
provider.defaultSerializeValue(value.details(), generator);
~~~

Nếu cần một kiểu đích cụ thể, dùng serializer phù hợp đã được resolve từ provider thay vì tự tạo mapper độc lập.

## 13. Tôn trọng naming, escaping và cấu trúc JSON

Custom serializer chủ động quyết định tên field trong JSON. Naming strategy của mapper không nhất thiết tự đổi các tên được ghi trực tiếp bằng `writeStringField()` hoặc `writeFieldName()` trong serializer.

Ví dụ serializer ghi `currency` thì JSON dùng đúng `currency`, kể cả mapper đang áp dụng snake case cho các bean property khác. Nếu hợp đồng cần `currency_code`, hãy ghi chính tên đó trong serializer hoặc đọc metadata cấu hình phù hợp.

Luôn dùng API typed của `JsonGenerator`:

~~~java
generator.writeStringField("currency", currencyCode);
generator.writeNumberField("quantity", quantity);
generator.writeBooleanField("active", active);
generator.writeStartArray();
generator.writeEndArray();
~~~

Các phương thức này xử lý escaping và cấu trúc token. Không nối chuỗi JSON bằng dấu ngoặc, dấu phẩy hoặc dấu nháy tự tạo. Đặc biệt, tên hoặc giá trị do user cung cấp phải được ghi qua API string để ký tự đặc biệt được escape đúng.

## 14. Xử lý collection và value object lồng nhau

Jackson tự tìm serializer cho từng phần tử trong collection. Nếu `List<Money>` được ghi qua Data Binding, serializer đã đăng ký cho `Money` sẽ được sử dụng cho các phần tử.

Ví dụ:

~~~java
public class CartResponse {
    private List<Money> lineTotals;

    public List<Money> getLineTotals() {
        return lineTotals;
    }

    public void setLineTotals(List<Money> lineTotals) {
        this.lineTotals = lineTotals;
    }
}
~~~

Nếu serializer của một aggregate tự ghi danh sách con, có thể dùng:

~~~java
generator.writeArrayFieldStart("lineTotals");
for (Money item : value.lineTotals()) {
    provider.defaultSerializeValue(item, generator);
}
generator.writeEndArray();
~~~

Cách này giữ việc lựa chọn serializer cho `Money` theo cấu hình mapper. Nếu phần tử null, `defaultSerializeValue()` dùng null serializer tương ứng.

## 15. Kiểm thử custom serializer

Custom serializer nên được kiểm thử qua `ObjectMapper` đã cấu hình thực tế, không chỉ gọi trực tiếp phương thức `serialize()`. Điều đó xác nhận Jackson đã chọn đúng serializer và output đúng cấu trúc.

Ví dụ với JUnit 5:

~~~java
class MoneySerializerTest {
    private final ObjectMapper mapper;

    MoneySerializerTest() {
        SimpleModule module = new SimpleModule("MoneyModule");
        module.addSerializer(Money.class, new MoneySerializer());
        this.mapper = JsonMapper.builder()
            .addModule(module)
            .build();
    }

    @Test
    void writesAmountAndCurrencyAsStrings() throws Exception {
        Money money = new Money(
            new BigDecimal("125000.50"),
            Currency.getInstance("VND")
        );

        JsonNode json = mapper.readTree(mapper.writeValueAsString(money));

        assertEquals("125000.50", json.path("amount").asText());
        assertEquals("VND", json.path("currency").asText());
    }

    @Test
    void usesMoneySerializerInsideAnotherDto() throws Exception {
        InvoiceResponse invoice = new InvoiceResponse();
        invoice.setInvoiceNo("INV-2026-001");
        invoice.setTotal(new Money(
            new BigDecimal("125000.50"),
            Currency.getInstance("VND")
        ));

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(invoice)
        );

        assertEquals(
            "125000.50",
            json.path("total").path("amount").asText()
        );
        assertEquals("VND", json.path("total").path("currency").asText());
    }
}
~~~

Hai test xác nhận serializer hoạt động ở root và khi `Money` là property lồng trong DTO. So sánh `JsonNode` giúp test tập trung vào cấu trúc và giá trị, không phụ thuộc khoảng trắng hoặc thứ tự field.

Nên bổ sung các trường hợp:

- Amount âm nếu domain cho phép (refund/adjustment).
- Amount bằng zero.
- Amount có scale khác nhau như `1.0` và `1.00`.
- Currency code hợp lệ và không hợp lệ ở constructor/deserializer.
- Property Money null và chính sách `@JsonInclude`.
- List chứa Money và phần tử null.
- DTO dùng nhiều property Money.
- Serializer được đăng ký qua Spring Boot/module thực tế.
- Output không chứa field nội bộ của value object.

Nếu serializer hỗ trợ nhiều format theo `ContextualSerializer`, cần test từng annotation style và trường hợp property metadata null.

## 16. Đánh giá tác động đến hợp đồng API

Thay đổi custom serializer có thể làm thay đổi JSON của mọi endpoint dùng kiểu đó. Ví dụ chuyển `amount` từ JSON number sang JSON string:

~~~json
{"amount": 125000.50}
~~~

thành:

~~~json
{"amount": "125000.50"}
~~~

Đây là thay đổi kiểu dữ liệu trong hợp đồng, có thể khiến client cũ không parse được. Tương tự, đổi object thành scalar hoặc đổi tên field có thể là breaking change.

Trước khi thay serializer dùng chung:

- Xác định tất cả DTO/endpoint đang dùng value object.
- Kiểm tra client và consumer của JSON.
- Xác định có cần version API hoặc serializer theo property không.
- Cập nhật schema OpenAPI/JSON Schema nếu có.
- Viết contract test để phát hiện thay đổi ngoài ý muốn.
- Tránh thay đổi mapper singleton theo từng request để phục vụ một endpoint.

Nếu chỉ một endpoint có hợp đồng khác, serializer gắn ở property hoặc DTO riêng có thể phù hợp hơn việc thay đổi serializer toàn cục cho kiểu `Money`.

## 17. Các lỗi thường gặp

### Serializer được viết nhưng Jackson không sử dụng

Nguyên nhân thường là annotation đặt sai class/property hoặc module chưa được đăng ký vào mapper thực tế đang dùng. Hãy kiểm thử qua đúng mapper/HTTP converter của ứng dụng.

### Ghi JSON bằng nối chuỗi

Nối chuỗi không xử lý escaping và dấu phân cách an toàn. Dùng `JsonGenerator` để ghi token có kiểu.

### Chuyển BigDecimal sang double

Việc này có thể làm mất chính xác. Dùng `toPlainString()` nếu hợp đồng dùng chuỗi hoặc `writeNumber(BigDecimal)` nếu hợp đồng yêu cầu JSON number.

### Làm tròn trong serializer

Serializer không nên tự thay đổi giá trị nghiệp vụ. Scale và rounding thuộc domain hoặc hợp đồng được định nghĩa rõ.

### Tạo ObjectMapper mới trong serializer

Mapper mới bỏ qua module và cấu hình ứng dụng, đồng thời có thể biến object lồng thành JSON string. Dùng generator và provider.

### Serializer giữ state mutable

Mapper có thể dùng serializer đồng thời ở nhiều thread. Giữ serializer stateless hoặc tạo instance contextual bất biến.

### Cho rằng serializer cũng xử lý chiều đọc

Serializer chỉ ghi Java thành JSON. Nếu cần đọc JSON thành value object, hãy cung cấp deserializer hoặc creator phù hợp.

### Quên chính sách null

Null thường do null serializer xử lý, không đi qua `serialize()` của serializer giá trị. Kiểm thử riêng null và zero/empty.

### Đổi format nhưng không kiểm tra consumer

Đổi number thành string hoặc object thành scalar là thay đổi hợp đồng. Cần đánh giá compatibility trước khi phát hành.

## 18. Quy trình thiết kế serializer cho value object

1. Xác định ý nghĩa nghiệp vụ và invariant của value object.
2. Định nghĩa JSON contract: object, scalar hay string; tên field, kiểu token, null và format.
3. Xác định có cần giữ chính xác số thập phân, scale, timezone hoặc đơn vị hay không.
4. Chọn `StdSerializer<T>` và triển khai `serialize()` bằng `JsonGenerator`.
5. Dùng `SerializerProvider` cho các giá trị lồng nhau để tái sử dụng cấu hình Jackson.
6. Gắn bằng `@JsonSerialize` nếu quy tắc thuộc kiểu/property, hoặc đăng ký qua `SimpleModule` nếu thuộc cấu hình mapper.
7. Nếu format phụ thuộc property, cân nhắc `ContextualSerializer` với instance bất biến.
8. Xác định riêng cách deserialize nếu ứng dụng nhận kiểu đó từ JSON.
9. Kiểm thử root, property lồng nhau, collection, null và các giá trị biên.
10. Kiểm tra serializer được dùng trong mapper/converter thực tế.
11. Đánh giá ảnh hưởng đến schema và consumer trước khi thay đổi hợp đồng.

## 19. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Tùy biến cách ghi một kiểu Java | `JsonSerializer<T>` hoặc `StdSerializer<T>` |
| Ghi object/array/scalar đúng cấu trúc | `JsonGenerator` |
| Truy cập serializer và chính sách Databind | `SerializerProvider` |
| Gắn serializer cho class/property | `@JsonSerialize(using = ...)` |
| Đăng ký serializer không sửa class nguồn | `SimpleModule.addSerializer(...)` |
| Ghi giá trị lồng nhau theo mapper | `provider.defaultSerializeValue(...)` |
| Format phụ thuộc property | `ContextualSerializer` |
| Xử lý JSON null | Null serializer và `@JsonInclude`/null policy phù hợp |
| Đọc JSON trở lại value object | `JsonDeserializer<T>` hoặc creator riêng |
| Kiểm tra hợp đồng | Test qua `ObjectMapper`/HTTP converter thực tế |

## 20. Kết luận

Custom serializer cho phép Jackson biểu diễn một kiểu giá trị nghiệp vụ theo đúng hợp đồng JSON thay vì phụ thuộc vào cấu trúc Java mặc định. Hãy bắt đầu bằng việc xác định JSON cần là object, chuỗi hay số; sau đó triển khai `StdSerializer<T>` bằng `JsonGenerator`, dùng `SerializerProvider` cho giá trị lồng nhau và đăng ký qua `@JsonSerialize` hoặc `SimpleModule`.

Serializer nên stateless, không tự tạo mapper, không làm tròn hoặc thay đổi giá trị nghiệp vụ ngoài hợp đồng và phải xử lý null theo chính sách rõ ràng. Nếu format phụ thuộc từng property, dùng contextual serializer với cấu hình bất biến. Cuối cùng, serializer chỉ giải quyết chiều ghi; nếu cần round-trip, hãy thiết kế deserializer riêng và kiểm thử cả cấu trúc JSON, độ chính xác dữ liệu, consumer và mapper thực tế của ứng dụng.
