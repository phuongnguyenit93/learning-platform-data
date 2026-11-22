# Khi nào cần serializer riêng thay vì annotation

Jackson cung cấp nhiều annotation để điều khiển cách một kiểu Java được biểu diễn thành JSON. Có thể đổi tên field, bỏ thuộc tính, định dạng ngày giờ, chọn một giá trị đại diện hoặc điều khiển null mà không cần viết thêm code serialize. Tuy nhiên, annotation chỉ mô tả được những quy tắc mà Jackson đã hỗ trợ hoặc những tùy chọn mà annotation cung cấp.

Khi logic biểu diễn phức tạp hơn, cần tạo một cấu trúc JSON đặc biệt, phải tính toán từ nhiều thuộc tính, hoặc cần tái sử dụng cùng một quy tắc cho một kiểu dữ liệu ở nhiều nơi, custom serializer có thể phù hợp hơn.

Quyết định nên bắt đầu từ hình dạng JSON mà hợp đồng yêu cầu:

- Nếu chỉ cần đổi tên, bỏ field hoặc chọn định dạng có sẵn, hãy ưu tiên annotation.
- Nếu một kiểu cần được chuyển thành một JSON shape riêng hoặc cần logic ghi token tùy chỉnh, hãy cân nhắc serializer.
- Nếu quy tắc chỉ áp dụng cho một property, có thể gắn serializer ngay tại property.
- Nếu mọi lần serialize một kiểu đều cần cùng quy tắc, đăng ký serializer theo kiểu trong module.
- Nếu cần đọc JSON ngược lại, hãy thiết kế deserializer hoặc creator tương ứng; serializer chỉ giải quyết chiều ghi.

## 1. Annotation phù hợp với những quy tắc biểu diễn phổ biến

Jackson có nhiều annotation để mô tả cách property được phát ra JSON:

| Nhu cầu | Annotation thường dùng |
|---|---|
| Đổi tên thuộc tính | @JsonProperty |
| Bỏ thuộc tính | @JsonIgnore |
| Bỏ một nhóm thuộc tính | @JsonIgnoreProperties |
| Chỉ đọc hoặc chỉ ghi | @JsonProperty(access = ...) |
| Định dạng ngày giờ hoặc số | @JsonFormat |
| Biểu diễn object bằng một giá trị duy nhất | @JsonValue |
| Bỏ qua null hoặc giá trị rỗng | @JsonInclude |
| Sắp xếp thứ tự property | @JsonPropertyOrder |
| Thêm thông tin subtype | @JsonTypeInfo và các annotation liên quan |

Ví dụ, nếu chỉ cần đổi tên field từ camelCase sang tên wire đã thống nhất, annotation là đủ:

~~~java
public record UserResponse(
    @JsonProperty("user_id") Long userId,
    @JsonProperty("display_name") String displayName
) {}
~~~

Nếu cần định dạng một ngày:

~~~java
public record EventResponse(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate eventDate
) {}
~~~

Nếu một value object chỉ cần được ghi thành chuỗi:

~~~java
public record CustomerCode(String value) {
    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Các trường hợp này không cần serializer riêng. Annotation thể hiện trực tiếp ý định và giữ code đơn giản.

Không nên viết custom serializer chỉ để đổi tên property, bỏ một field hoặc tạo định dạng mà @JsonFormat đã hỗ trợ. Serializer tự viết tạo thêm mã cần bảo trì và có thể vô tình thay đổi hành vi null, kiểu dữ liệu hoặc metadata mà Jackson vốn xử lý đúng.

## 2. Khi annotation không còn diễn tả đủ quy tắc

Custom serializer trở nên hữu ích khi cách biểu diễn không còn là một tùy chọn đơn lẻ.

Một số dấu hiệu:

- Một object Java cần được chuyển thành cấu trúc JSON khác đáng kể so với các property mặc định.
- Output được tính từ nhiều field hoặc cần kết hợp, chuẩn hóa dữ liệu trước khi ghi.
- Quy tắc serialize có điều kiện theo giá trị, trạng thái hoặc ngữ cảnh.
- Một kiểu dùng trong nhiều module cần một cách biểu diễn thống nhất.
- Cần ghi token theo thứ tự hoặc cấu trúc cụ thể bằng JsonGenerator.
- Cần hỗ trợ một kiểu thư viện bên ngoài mà không thể sửa class để thêm annotation.
- Cần kiểm soát chính xác cách ghi một kiểu đặc biệt hoặc định dạng wire riêng.

Ví dụ, một Money object có amount và currency:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

Nếu JSON cần có cấu trúc:

~~~json
{
  "amount": "1250.50",
  "currency": "VND",
  "display": "1.250,50 ₫"
}
~~~

thì annotation thông thường không thể tự tính display từ amount và currency theo quy tắc locale cụ thể. Một serializer có thể thực hiện phép định dạng đó.

Tuy nhiên, nếu JSON chỉ cần amount và currency dưới dạng hai field thông thường, Jackson đã có thể serialize record mà không cần custom serializer. Hãy viết serializer vì có yêu cầu biểu diễn thực sự, không chỉ vì muốn kiểm soát mọi field.

## 3. So sánh annotation và custom serializer

| Tiêu chí | Annotation | Custom serializer |
|---|---|---|
| Đổi tên hoặc bỏ field | Rất phù hợp | Thường quá phức tạp cho nhu cầu này |
| Định dạng chuẩn có sẵn | Ưu tiên @JsonFormat và annotation tương ứng | Dùng khi quy tắc vượt khả năng cấu hình có sẵn |
| Tạo JSON shape tùy chỉnh | Bị giới hạn bởi annotation | Có thể ghi object, array hoặc scalar theo ý muốn |
| Tính toán từ nhiều field | Không linh hoạt | Phù hợp |
| Tái sử dụng cho kiểu thư viện bên ngoài | Có thể qua mix-in trong một số trường hợp | Đăng ký qua module |
| Quy tắc phụ thuộc property | Annotation tại property thường dễ hiểu | Có thể dùng serializer theo property hoặc ContextualSerializer |
| Khả năng bảo trì | Ít code, ý định rõ | Cần test và duy trì logic riêng |
| Deserialize ngược | Annotation có thể hỗ trợ cả hai chiều tùy loại | Serializer không tự cung cấp deserializer |

Một quy tắc thực tế: dùng annotation để cấu hình hành vi Jackson đã biết; dùng serializer khi phải lập trình cách tạo JSON output.

## 4. Custom serializer là gì?

Serializer là thành phần nhận một giá trị Java và ghi biểu diễn JSON của giá trị đó vào JsonGenerator.

Trong Jackson Databind, có thể mở rộng StdSerializer<T>. Kiểu T là kiểu Java mà serializer xử lý.

Ví dụ serializer cho Money:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
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
        generator.writeStringField("amount", value.amount().toPlainString());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Serializer này ghi Money thành JSON object với hai field. amount được ghi thành chuỗi decimal bằng toPlainString(), vì hợp đồng ví dụ muốn giữ cách biểu diễn decimal dưới dạng string.

Nếu hợp đồng yêu cầu JSON number, dùng writeNumberField hoặc writeNumber với BigDecimal thay vì writeStringField:

~~~java
generator.writeNumberField("amount", value.amount());
~~~

Không được tùy tiện đổi number thành string hoặc ngược lại. Kiểu JSON là một phần của hợp đồng và consumer có thể dựa vào nó.

JsonGenerator chịu trách nhiệm ghi dấu ngoặc, dấu phân cách, escape chuỗi và token JSON. Không nên tự ghép chuỗi JSON bằng StringBuilder trong serializer.

## 5. Gắn serializer bằng @JsonSerialize

Nếu custom serializer chỉ dành cho một kiểu hoặc một điểm sử dụng cụ thể, có thể gắn trực tiếp bằng @JsonSerialize.

~~~java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = MoneySerializer.class)
public record Money(
    BigDecimal amount,
    String currency
) {}
~~~

Sau đó dùng ObjectMapper bình thường:

~~~java
ObjectMapper mapper = new ObjectMapper();

Money money = new Money(new BigDecimal("1250.50"), "VND");

String json = mapper.writeValueAsString(money);
~~~

Jackson chọn MoneySerializer khi serialize Money.

Cách gắn ở cấp kiểu có nghĩa là mọi nơi dùng kiểu Money qua mapper đó đều nhận biểu diễn đã định nghĩa trên class, trừ khi có cấu hình cục bộ khác được áp dụng.

Có thể gắn serializer ở cấp property khi chỉ một field cần cách biểu diễn riêng:

~~~java
public record InvoiceResponse(
    String invoiceId,

    @JsonSerialize(using = MaskedPhoneSerializer.class)
    String customerPhone
) {}
~~~

Ví dụ này phù hợp nếu cùng kiểu String nhưng chỉ customerPhone cần được che bớt. Không nên đăng ký một serializer cho String toàn mapper chỉ để che số điện thoại, vì điều đó sẽ ảnh hưởng mọi chuỗi trong ứng dụng.

## 6. Đăng ký serializer bằng SimpleModule

Nếu không thể sửa class nguồn, chẳng hạn kiểu thuộc thư viện bên ngoài, hoặc muốn tập trung cấu hình ở tầng ứng dụng, hãy đăng ký serializer qua module.

~~~java
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.databind.json.JsonMapper;

SimpleModule module = new SimpleModule();
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();
~~~

Khi mapper serialize Money, module cung cấp serializer cho kiểu đó.

Cách đăng ký qua module hữu ích khi:

- Kiểu Java thuộc thư viện không thể thêm annotation.
- Không muốn đặt annotation Jackson vào domain model.
- Ứng dụng cần chọn cách serialize riêng theo integration.
- Nhiều DTO hoặc service dùng chung một kiểu wire representation.
- Cần đóng gói các serializer liên quan thành một module cấu hình.

Module nên được đăng ký khi xây dựng ObjectMapper, trước khi mapper được chia sẻ và sử dụng. Không nên thay đổi danh sách module trên mapper đang được dùng đồng thời.

Có thể tạo nhiều mapper hoặc writer với cấu hình khác nhau nếu hai integration có hợp đồng wire khác nhau. Hãy đặt tên và phạm vi rõ ràng để tránh một serializer toàn cục vô tình làm thay đổi API khác.

## 7. Serializer toàn kiểu và serializer riêng cho property

Có hai phạm vi thường gặp:

**Serializer toàn kiểu** áp dụng cho mọi giá trị của kiểu Java đó trong mapper. Có thể gắn @JsonSerialize trên class hoặc đăng ký qua module.

**Serializer theo property** chỉ áp dụng cho một property cụ thể. Ví dụ một trường String được che, trong khi các String khác vẫn được ghi nguyên bản.

Một serializer theo property:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;

public final class MaskedPhoneSerializer extends StdSerializer<String> {

    public MaskedPhoneSerializer() {
        super(String.class);
    }

    @Override
    public void serialize(
            String value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        String masked = value.length() <= 4
            ? "****"
            : "*".repeat(value.length() - 4) + value.substring(value.length() - 4);

        generator.writeString(masked);
    }
}
~~~

Sử dụng:

~~~java
public record CustomerResponse(
    String name,

    @JsonSerialize(using = MaskedPhoneSerializer.class)
    String phone,

    String note
) {}
~~~

Kết quả chỉ phone bị che. name và note vẫn dùng String serializer mặc định.

Đây là một ví dụ về logic riêng theo property. Trong hệ thống thực tế, hãy xác định cách xử lý chuỗi null, chuỗi rỗng, ký tự Unicode và số điện thoại ngắn hơn quy tắc che. Không nên dùng cùng một thuật toán masking cho mọi định dạng định danh nếu hợp đồng có nhiều loại dữ liệu.

## 8. Dùng ContextualSerializer khi quy tắc phụ thuộc property

Đôi khi serializer cần biết metadata của property đang được serialize. Ví dụ, cùng một kiểu Money nhưng một field cần hiển thị hai chữ số thập phân, field khác cần không có phần thập phân.

Có thể dùng ContextualSerializer để Jackson cung cấp BeanProperty tương ứng:

~~~java
public final class MoneySerializer
        extends StdSerializer<Money>
        implements ContextualSerializer {

    private final int scale;

    public MoneySerializer() {
        this(2);
    }

    private MoneySerializer(int scale) {
        super(Money.class);
        this.scale = scale;
    }

    @Override
    public JsonSerializer<?> createContextual(
            SerializerProvider provider,
            BeanProperty property) {

        if (property == null) {
            return this;
        }

        MoneyScale annotation =
            property.getAnnotation(MoneyScale.class);

        if (annotation == null) {
            return this;
        }

        return new MoneySerializer(annotation.value());
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        BigDecimal amount = value.amount()
            .setScale(scale, RoundingMode.HALF_UP);

        generator.writeStartObject();
        generator.writeNumberField("amount", amount);
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

MoneyScale là annotation do ứng dụng định nghĩa, ví dụ:

~~~java
@Target({ElementType.FIELD, ElementType.RECORD_COMPONENT, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface MoneyScale {
    int value();
}
~~~

Sử dụng:

~~~java
public record InvoiceResponse(
    @MoneyScale(0) Money roundedTotal,
    @MoneyScale(2) Money exactTotal
) {}
~~~

Ví dụ này minh họa cách serializer nhận metadata theo property. Khi triển khai, cần import các kiểu reflection, Jackson và BigDecimal/RoundingMode tương ứng. Cũng cần quyết định rõ rounding là quy tắc hiển thị hay thay đổi giá trị nghiệp vụ; serializer chỉ nên định dạng output, không làm thay đổi object nguồn.

ContextualSerializer phù hợp khi serializer có một lõi xử lý chung nhưng cách trình bày phụ thuộc metadata của từng property. Nếu mỗi property có logic hoàn toàn khác nhau, serializer riêng theo property có thể dễ hiểu hơn.

## 9. Serializer có thể tạo object, array hoặc scalar

Custom serializer không bị giới hạn ở việc ghi các field giống class Java.

Ví dụ Money có thể được ghi thành scalar string:

~~~java
@Override
public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    generator.writeString(
        value.amount().toPlainString() + " " + value.currency()
    );
}
~~~

Output:

~~~json
"1250.50 VND"
~~~

Hoặc ghi thành array nếu wire contract yêu cầu tuple:

~~~java
@Override
public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    generator.writeStartArray();
    generator.writeNumber(value.amount());
    generator.writeString(value.currency());
    generator.writeEndArray();
}
~~~

Output:

~~~json
[1250.50, "VND"]
~~~

Ba dạng object, string và array đều có thể đại diện cho Money, nhưng chúng là ba hợp đồng JSON khác nhau. Hãy chọn dạng mà consumer cần và ghi rõ trong tài liệu API.

Nếu chỉ cần biểu diễn một object bằng một scalar ổn định, @JsonValue có thể đơn giản hơn custom serializer. Serializer phù hợp hơn khi cần nhiều bước, tính toán hoặc cấu trúc phức tạp.

## 10. Serializer cho Map key là một trường hợp riêng

Map được serialize thành JSON object, trong đó key Java trở thành tên property JSON. Serializer cho value thông thường không xử lý key.

Ví dụ:

~~~java
Map<Currency, BigDecimal> balances;
~~~

Nếu Currency là kiểu tùy chỉnh, cần định nghĩa cách chuyển key thành tên field. Jackson có key serializer:

~~~java
module.addKeySerializer(Currency.class, new CurrencyKeySerializer());
~~~

Hoặc dùng annotation keyUsing ở property:

~~~java
@JsonSerialize(keyUsing = CurrencyKeySerializer.class)
Map<Currency, BigDecimal> balances;
~~~

Cần phân biệt:

- using: serializer cho giá trị property.
- contentUsing: serializer cho phần tử bên trong collection hoặc value của container.
- keyUsing: serializer cho key của Map.

Nếu chỉ viết serializer cho value Currency mà Map đang dùng Currency làm key, serializer đó không tự quyết định tên field JSON. Đây là một trường hợp cần serializer chuyên biệt theo vai trò.

## 11. Serializer không thay thế deserializer

Custom serializer chỉ định cách ghi Java object thành JSON. Nó không tự định nghĩa cách đọc JSON trở lại thành object Java.

Ví dụ serializer Money ghi:

~~~json
{
  "amount": "1250.50",
  "currency": "VND"
}
~~~

Để đọc lại, Jackson cần biết cách tạo Money từ object này. Có thể dùng constructor creator:

~~~java
public record Money(
    BigDecimal amount,
    String currency
) {
    @JsonCreator
    public Money(
        @JsonProperty("amount") String amount,
        @JsonProperty("currency") String currency
    ) {
        this(new BigDecimal(amount), currency);
    }
}
~~~

Hoặc viết JsonDeserializer<Money> nếu định dạng đầu vào phức tạp, cần hỗ trợ nhiều dạng cũ hoặc có quy tắc kiểm tra đặc biệt.

Khi serializer đổi shape từ object sang string hoặc array, deserializer mặc định có thể không đọc được dạng đó. Nếu ứng dụng cần round-trip, hãy thiết kế cả hai chiều và test bằng payload thật.

Nếu output chỉ dành cho export một chiều, không nhất thiết phải có deserializer. Nhưng điều đó cần được hiểu là một hợp đồng chỉ xuất dữ liệu, không phải một biểu diễn có thể đọc ngược tự động.

## 12. Xử lý null và empty value

Serializer thông thường xử lý giá trị khác null. Jackson thường quản lý null thông qua null serializer riêng, vì vậy không nên giả định phương thức serialize() của custom serializer sẽ được gọi với value bằng null.

Nếu cần quy tắc null đặc biệt, hãy xem xét:

- @JsonInclude để bỏ qua null hoặc empty khi serialize.
- @JsonSerialize(nullsUsing = ...) để chỉ định serializer cho null ở property phù hợp.
- Cấu hình null serializer ở cấp mapper/provider khi chính sách áp dụng rộng.
- @JsonSetter hoặc deserializer khi quy tắc liên quan đến chiều đọc.

Nếu serializer cần ảnh hưởng đến việc xác định một giá trị có được xem là empty cho NON_EMPTY hay không, có thể override isEmpty(SerializerProvider, T) trong serializer.

Ví dụ, một mã rỗng có thể được xem là empty:

~~~java
@Override
public boolean isEmpty(SerializerProvider provider, CustomerCode value) {
    return value == null || value.value() == null || value.value().isBlank();
}
~~~

Việc xem một giá trị là empty chỉ ảnh hưởng các chính sách inclusion tương ứng; nó không tự chuyển chuỗi rỗng thành null hoặc thay đổi giá trị Java.

Hãy test null, empty string, empty collection và object rỗng riêng biệt. Đây là những trạng thái khác nhau trong JSON và có thể mang ý nghĩa khác nhau trong hợp đồng.

## 13. Tránh gọi lại ObjectMapper một cách đệ quy trong serializer

Trong custom serializer, nên ghi token trực tiếp bằng JsonGenerator. Không nên gọi lại mapper.writeValueAsString(value) với chính kiểu đang được serializer xử lý, vì điều đó có thể gọi lại serializer và tạo đệ quy.

Không nên:

~~~java
@Override
public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    String json = mapper.writeValueAsString(value);
    generator.writeRawValue(json);
}
~~~

Nếu mapper dùng serializer này cho Money, writeValueAsString(value) lại gọi MoneySerializer, rồi lặp tiếp.

Hãy ghi trực tiếp:

~~~java
generator.writeStartObject();
generator.writeNumberField("amount", value.amount());
generator.writeStringField("currency", value.currency());
generator.writeEndObject();
~~~

Nếu muốn ủy quyền cho serializer mặc định của một kiểu con hoặc một thuộc tính khác, có thể dùng provider.findValueSerializer(...) hoặc provider.defaultSerializeValue(...) với kiểu/giá trị phù hợp. Cần tránh gọi lại chính serializer đang chạy cho cùng giá trị.

Việc ghi trực tiếp token cũng giúp serializer kiểm soát rõ kiểu JSON, cấu trúc lồng nhau và thứ tự ghi.

## 14. Đăng ký serializer ở đúng phạm vi

Có ba cách tổ chức thường gặp:

| Cách đăng ký | Phạm vi |
|---|---|
| @JsonSerialize trên class | Kiểu đó khi được serialize bởi mapper hỗ trợ annotation. |
| @JsonSerialize trên property | Chỉ property được đánh dấu. |
| SimpleModule.addSerializer(...) | Kiểu được đăng ký trong mapper sử dụng module. |

Nếu domain model không nên phụ thuộc Jackson, đăng ký qua module có thể giữ ranh giới tốt hơn. Nếu một DTO công khai có một property đặc biệt, annotation tại property có thể dễ đọc và tự mô tả hơn.

Với kiểu thư viện bên ngoài, module là lựa chọn thường dùng vì không thể sửa class nguồn. Mix-in có thể bổ sung annotation mà không sửa class gốc, nhưng custom serializer vẫn cần được triển khai nếu hành vi vượt quá annotation có sẵn.

Không nên đăng ký serializer toàn cục cho kiểu phổ biến như String, Integer hoặc BigDecimal trừ khi toàn bộ ứng dụng thực sự muốn thay đổi cách biểu diễn kiểu đó. Một serializer quá rộng có thể âm thầm ảnh hưởng nhiều API.

## 15. Khi nào nên dùng converter thay vì serializer?

Jackson có JsonSerializer và JsonDeserializer, nhưng cũng có khái niệm converter. Converter chuyển một kiểu Java sang kiểu khác, sau đó Jackson serialize kiểu kết quả theo cơ chế thông thường.

Ví dụ, một value object có thể chuyển thành String:

~~~java
public final class CustomerCodeConverter
        extends StdConverter<CustomerCode, String> {

    @Override
    public String convert(CustomerCode value) {
        return value.value();
    }
}
~~~

Gắn converter:

~~~java
@JsonSerialize(converter = CustomerCodeConverter.class)
private CustomerCode customerCode;
~~~

Converter phù hợp khi logic chủ yếu là ánh xạ từ kiểu nguồn sang một kiểu đích đã được Jackson hỗ trợ. Serializer phù hợp khi cần trực tiếp điều khiển quá trình ghi token, cấu trúc object/array hoặc metadata output.

Một số quy tắc đơn giản:

- Chuyển value object thành String: cân nhắc @JsonValue hoặc converter.
- Định dạng ngày giờ chuẩn: cân nhắc @JsonFormat.
- Ghi một object tùy biến gồm nhiều field được tính toán: custom serializer.
- Ghi Map key: key serializer.
- Ghi phần tử collection theo quy tắc riêng: content serializer.

## 16. Kiểm thử custom serializer

Một custom serializer nên được kiểm tra bằng output JSON thực tế. Chỉ kiểm tra phương thức serialize không ném exception là chưa đủ.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.junit.jupiter.api.Test;

class MoneySerializerTest {

    private final ObjectMapper mapper;

    MoneySerializerTest() {
        SimpleModule module = new SimpleModule();
        module.addSerializer(Money.class, new MoneySerializer());

        mapper = JsonMapper.builder()
            .addModule(module)
            .build();
    }

    @Test
    void writesMoneyAsExpectedObject() throws Exception {
        Money money = new Money(new BigDecimal("1250.50"), "VND");

        String json = mapper.writeValueAsString(money);
        JsonNode tree = mapper.readTree(json);

        assertEquals("1250.50", tree.path("amount").asText());
        assertEquals("VND", tree.path("currency").asText());
    }
}
~~~

Nếu serializer ghi amount thành JSON number, hãy kiểm tra isNumber() và decimalValue() thay vì asText() để bảo đảm đúng kiểu wire.

Nên có test cho:

- Giá trị bình thường và biên.
- Null và empty.
- Số decimal, scale và rounding.
- Locale/timezone nếu serializer có định dạng phụ thuộc môi trường.
- Property-level serializer và type-level serializer.
- Collection/map chứa kiểu được serialize.
- Map key nếu có key serializer.
- Deserializer tương ứng nếu cần round-trip.
- JSON output không có field ngoài hợp đồng.

Không nên dùng test chỉ so sánh chuỗi khi thứ tự object property không phải một phần hợp đồng. Có thể parse JSON thành JsonNode rồi kiểm tra cấu trúc và kiểu giá trị. Nếu thứ tự hoặc canonical bytes thực sự là yêu cầu, test riêng chính sách đó.

## 17. Quy trình quyết định trước khi viết serializer

Trước khi tạo class serializer mới, hãy trả lời:

1. Yêu cầu chỉ là đổi tên, bỏ field, định dạng ngày giờ hoặc chọn scalar value không?
2. Jackson đã có annotation hoặc feature cho chính xác nhu cầu đó chưa?
3. Output có cần tính toán từ nhiều property hoặc thay đổi cấu trúc JSON không?
4. Quy tắc áp dụng cho toàn kiểu hay chỉ một property?
5. Kiểu Java có thể được sửa annotation hay thuộc thư viện bên ngoài?
6. Có cần đọc JSON trở lại không?
7. Null, empty và lỗi định dạng được xử lý ra sao?
8. Có cần serializer cho Map key hoặc collection content riêng không?
9. Có thể dùng converter thay vì điều khiển JsonGenerator trực tiếp không?
10. Có test chứng minh output khớp wire contract không?

Một custom serializer tốt có phạm vi rõ ràng, ghi đúng kiểu JSON và có test cho các trường hợp biên. Nếu chỉ thay thế một annotation bằng nhiều dòng code, hãy xem lại liệu serializer có thực sự cần thiết.

## Kết luận

Annotation là lựa chọn đầu tiên cho những quy tắc biểu diễn Jackson đã hỗ trợ như đổi tên, bỏ field, định dạng ngày giờ, chọn giá trị scalar hoặc điều khiển inclusion. Custom serializer phù hợp khi cần tạo JSON shape riêng, tính toán từ nhiều dữ liệu, điều kiện ghi phức tạp hoặc tái sử dụng một quy tắc wire đặc biệt.

Dùng @JsonSerialize để gắn serializer tại class hoặc property, hoặc đăng ký qua SimpleModule khi cần áp dụng cho kiểu không thể sửa hay cho một mapper cụ thể. Ghi token bằng JsonGenerator, xử lý null theo cơ chế riêng, phân biệt value serializer với key/content serializer và thiết kế deserializer nếu cần đọc ngược. Kiểm thử JSON đầu ra theo hợp đồng sẽ giúp tránh việc custom code vô tình thay đổi kiểu dữ liệu hoặc làm mất thông tin.

