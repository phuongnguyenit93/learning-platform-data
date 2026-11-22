# Đăng ký serializer bằng JsonSerialize theo kiểu hoặc thuộc tính

Jackson có sẵn serializer cho phần lớn kiểu Java thông dụng. Tuy nhiên, đôi khi JSON cần có hình thức khác với cách Jackson mặc định biểu diễn một kiểu dữ liệu. Ví dụ, ứng dụng muốn ghi `Money` thành một object có cấu trúc riêng, ghi `BigDecimal` của một property thành chuỗi để giữ quy ước hiển thị, hoặc thay đổi cách ghi từng phần tử trong một collection.

Bạn có thể viết serializer tùy biến bằng `JsonSerializer` hoặc lớp tiện ích như `StdSerializer`, sau đó gắn serializer vào mô hình bằng annotation `@JsonSerialize`. Annotation này cho phép khai báo serializer ở hai phạm vi quan trọng:

- **Theo kiểu (type-level):** đặt `@JsonSerialize(using = ...)` trên class/record để quy định cách serialize kiểu đó ở mọi nơi Jackson sử dụng annotation của kiểu.
- **Theo thuộc tính (property-level):** đặt annotation trên field hoặc getter để chỉ thay đổi cách ghi một property cụ thể, dù các property khác có cùng kiểu Java vẫn dùng serializer mặc định.

Ngoài `using`, `@JsonSerialize` còn có `contentUsing` cho giá trị bên trong collection/array/map và `keyUsing` cho key của map. Hiểu đúng phạm vi của từng thuộc tính giúp tránh việc vô tình thay serializer của cả container khi mục tiêu chỉ là thay cách ghi các phần tử bên trong.

## 1. Serializer tùy biến là gì?

Serializer là thành phần chuyển một giá trị Java thành token JSON thông qua `JsonGenerator`. Trong Jackson Databind, serializer thường nhận ba tham số:

- Giá trị Java cần ghi.
- `JsonGenerator` dùng để phát ra JSON token.
- `SerializerProvider` cung cấp serializer và các dịch vụ serialization khác.

Một serializer tùy biến thường kế thừa `StdSerializer<T>` để khai báo kiểu Java mà nó xử lý, rồi override `serialize()`.

Ví dụ, kiểu `Money`:

```java
import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {
}
```

Theo mặc định, Jackson có thể serialize record này thành object với hai property `amount` và `currency`. Nhưng một API có thể yêu cầu cấu trúc JSON khác, chẳng hạn:

```json
{
  "currency": "VND",
  "amount": "125000.50"
}
```

Ta có thể viết serializer riêng để quyết định chính xác cấu trúc và kiểu token được ghi.

## 2. Viết serializer bằng StdSerializer

Ví dụ serializer cho `Money`:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;

public class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeStartObject(value);
        generator.writeStringField("currency", value.currency());
        generator.writeFieldName("amount");
        generator.writeNumber(value.amount());
        generator.writeEndObject();
    }
}
```

`StdSerializer<Money>` cho biết serializer xử lý kiểu `Money`. Constructor gọi `super(Money.class)` để cung cấp kiểu mà serializer đại diện. Trong `serialize()`:

1. `writeStartObject(value)` bắt đầu JSON object.
2. `writeStringField(...)` ghi một property string.
3. `writeFieldName(...)` ghi tên property tiếp theo.
4. `writeNumber(...)` ghi `BigDecimal` dưới dạng JSON number.
5. `writeEndObject()` đóng object.

Jackson chịu trách nhiệm escape tên trường và chuỗi theo cú pháp JSON. Không nên tự nối chuỗi JSON bằng dấu nháy hoặc dấu phẩy vì dễ tạo output sai khi dữ liệu chứa ký tự đặc biệt.

`SerializerProvider` được truyền vào để serializer có thể yêu cầu Jackson serialize các giá trị con theo cấu hình hiện hành. Ví dụ, thay vì tự quyết định cách ghi một property phức tạp, có thể dùng:

```java
generator.writeFieldName("amount");
provider.defaultSerializeValue(value.amount(), generator);
```

Cách này cho phép serializer lồng sử dụng serializer phù hợp do Jackson quản lý. Với kiểu scalar đơn giản như `BigDecimal`, gọi trực tiếp `writeNumber()` cũng rõ ràng.

## 3. Đăng ký serializer ở cấp kiểu bằng @JsonSerialize

Nếu muốn mọi lần serialize `Money` đều dùng `MoneySerializer`, đặt `@JsonSerialize` trên chính kiểu đó:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = MoneySerializer.class)
public record Money(BigDecimal amount, String currency) {
}
```

Khi `ObjectMapper` serialize một giá trị `Money`, Jackson đọc annotation trên kiểu và sử dụng `MoneySerializer`.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

Money money = new Money(new BigDecimal("125000.50"), "VND");
String json = mapper.writeValueAsString(money);

System.out.println(json);
```

Kết quả có dạng:

```json
{"currency":"VND","amount":125000.50}
```

Annotation nằm trên kiểu `Money`, vì vậy serializer này được dùng khi kiểu `Money` được serialize như root value hoặc như một giá trị con, miễn là quá trình introspection của Jackson nhìn thấy annotation đó và không có cấu hình cụ thể hơn tại property thay thế nó.

### 3.1. Khi nào nên dùng type-level?

Đặt serializer trên class/record khi cách biểu diễn JSON là quy ước chung của kiểu đó:

- `Money` luôn phải xuất ra theo một cấu trúc chuẩn thống nhất.
- Một kiểu value object có biểu diễn JSON riêng, không phụ thuộc property chứa nó.
- Mọi nơi sử dụng một kiểu domain đều cần cùng một định dạng wire format.
- Kiểu thuộc mã nguồn của ứng dụng và có thể thêm annotation mà không tạo phụ thuộc không mong muốn.

Type-level serializer giúp tránh lặp lại cùng annotation trên nhiều field. Tuy nhiên, nó cũng có phạm vi ảnh hưởng rộng: nếu cùng kiểu được dùng ở nhiều API nhưng mỗi API cần định dạng khác nhau, serializer ở cấp kiểu có thể quá bao quát.

## 4. Đăng ký serializer ở cấp thuộc tính

Đôi khi cùng một kiểu Java cần được ghi theo những cách khác nhau tùy ngữ cảnh. Ví dụ, một DTO cần ghi `BigDecimal total` thành chuỗi để giữ quy ước hiển thị, trong khi các `BigDecimal` khác trong ứng dụng vẫn phải là JSON number.

Viết serializer cho `BigDecimal`:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;
import java.math.BigDecimal;

public class BigDecimalAsStringSerializer extends StdSerializer<BigDecimal> {
    public BigDecimalAsStringSerializer() {
        super(BigDecimal.class);
    }

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeString(value.toPlainString());
    }
}
```

Gắn serializer vào đúng property:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import java.math.BigDecimal;

public class Invoice {
    private BigDecimal subtotal;

    @JsonSerialize(using = BigDecimalAsStringSerializer.class)
    private BigDecimal total;

    public BigDecimal getSubtotal() {
        return subtotal;
    }

    public void setSubtotal(BigDecimal subtotal) {
        this.subtotal = subtotal;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
```

Khi serialize một `Invoice`, `total` được ghi thành JSON string, còn `subtotal` vẫn được ghi bằng serializer mặc định của `BigDecimal`:

```json
{
  "subtotal": 1000.50,
  "total": "1250.75"
}
```

Đây là phạm vi property-level: serializer chỉ được gắn vào `total`. Một property `BigDecimal` khác ở DTO khác hoặc ở cùng class không tự động chịu ảnh hưởng.

### 4.1. Gắn annotation trên field hay getter?

`@JsonSerialize` có thể được đặt trên field hoặc accessor mà Jackson nhận diện. Ví dụ:

```java
public class Invoice {
    private BigDecimal total;

    @JsonSerialize(using = BigDecimalAsStringSerializer.class)
    public BigDecimal getTotal() {
        return total;
    }
}
```

Jackson hợp nhất field, getter và setter thành một logical property theo quy tắc introspection. Hãy đặt annotation ở một vị trí rõ ràng và nhất quán trong dự án. Tránh đặt các serializer xung đột trên cả field và getter của cùng property, vì việc hợp nhất annotation có thể khiến cấu hình khó hiểu và khó bảo trì.

Property-level annotation đặc biệt hữu ích với DTO: nó thể hiện trực tiếp hợp đồng JSON của trường đó mà không thay đổi cách kiểu Java được dùng ở nơi khác.

## 5. Phân biệt using và contentUsing

Một lỗi cấu hình thường gặp là dùng `using` trên collection trong khi mục tiêu chỉ là thay serializer của từng phần tử.

- `using` chỉ định serializer cho **toàn bộ giá trị của property**.
- `contentUsing` chỉ định serializer cho **nội dung bên trong container**, chẳng hạn từng phần tử của collection/array hoặc từng value của map.

Giả sử có danh sách `BigDecimal`:

```java
public class Invoice {
    @JsonSerialize(contentUsing = BigDecimalAsStringSerializer.class)
    private List<BigDecimal> lineAmounts;
}
```

Khi đó, Jackson vẫn dùng serializer collection thông thường để tạo JSON array, nhưng mỗi phần tử `BigDecimal` được ghi bằng `BigDecimalAsStringSerializer`:

```json
{
  "lineAmounts": ["10.50", "20.00", "30.00"]
}
```

Nếu thay bằng:

```java
@JsonSerialize(using = CustomListSerializer.class)
private List<BigDecimal> lineAmounts;
```

thì `CustomListSerializer` chịu trách nhiệm serialize toàn bộ property `lineAmounts`. Serializer này phải tự ghi cấu trúc array và tất cả phần tử. Jackson không tự áp dụng serializer collection mặc định bên trong serializer tùy biến đó.

Bảng so sánh:

| Thuộc tính annotation | Phạm vi | Ví dụ sử dụng |
| --- | --- | --- |
| `using` | Toàn bộ property/value | Thay cách ghi cả `List`, `Map`, DTO hoặc scalar |
| `contentUsing` | Phần tử của collection/array hoặc value của map | Ghi từng `BigDecimal` trong `List<BigDecimal>` thành string |
| `keyUsing` | Key của map | Ghi key `Currency` thành tên mã tiền tệ |

## 6. Tùy biến serializer cho key và value của Map

JSON object biểu diễn key bằng tên property dạng string. Nếu map Java dùng kiểu key khác `String`, Jackson cần serializer key phù hợp. `@JsonSerialize(keyUsing = ...)` cho phép chỉ định serializer dành riêng cho key.

Ví dụ map tỷ giá có key kiểu `Currency` và value kiểu `BigDecimal`:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;

import java.io.IOException;
import java.util.Currency;

public class CurrencyKeySerializer extends StdSerializer<Currency> {
    public CurrencyKeySerializer() {
        super(Currency.class);
    }

    @Override
    public void serialize(
            Currency value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeFieldName(value.getCurrencyCode());
    }
}
```

Gắn serializer cho cả key và value:

```java
public class ExchangeRates {
    @JsonSerialize(
            keyUsing = CurrencyKeySerializer.class,
            contentUsing = BigDecimalAsStringSerializer.class
    )
    private Map<Currency, BigDecimal> rates;

    public Map<Currency, BigDecimal> getRates() {
        return rates;
    }

    public void setRates(Map<Currency, BigDecimal> rates) {
        this.rates = rates;
    }
}
```

JSON đầu ra có thể là:

```json
{
  "rates": {
    "USD": "25450.00",
    "EUR": "27600.00"
  }
}
```

`keyUsing` ghi tên key của object JSON; `contentUsing` ghi value của từng entry. Hai serializer có trách nhiệm khác nhau: serializer key dùng `writeFieldName()`, còn serializer value ghi một JSON value như string, number, object hoặc array.

## 7. So sánh phạm vi type-level và property-level

| Tiêu chí | Type-level | Property-level |
| --- | --- | --- |
| Vị trí annotation | Trên class/record | Trên field/getter/property |
| Phạm vi | Các lần serialize giá trị thuộc kiểu đó | Một property cụ thể |
| Mục đích | Quy ước JSON chung của kiểu | Ngoại lệ theo ngữ cảnh DTO hoặc API |
| Ví dụ | Mọi `Money` có cùng cấu trúc JSON | Chỉ `Invoice.total` ghi thành string |
| Tác động đến nơi dùng khác | Có thể ảnh hưởng mọi nơi dùng kiểu | Không tự thay đổi property khác cùng kiểu |
| Khi phù hợp | Kiểu có một biểu diễn JSON thống nhất | Cùng kiểu cần biểu diễn khác nhau tùy field |

Quy tắc thực tế: nếu serializer mô tả bản chất biểu diễn của kiểu, cân nhắc đặt ở class. Nếu serializer mô tả hợp đồng của một trường cụ thể, đặt ở property.

## 8. Serializer tùy biến có thể dùng SerializerProvider

Trong serializer, không phải lúc nào cũng nên tự viết mọi value con. `SerializerProvider` cho phép yêu cầu Jackson sử dụng serializer phù hợp với cấu hình hiện hành.

Ví dụ một serializer cho `ProductView` cần ghi một object JSON nhưng muốn `price` được serialize theo quy tắc của Jackson:

```java
public class ProductViewSerializer extends StdSerializer<ProductView> {
    public ProductViewSerializer() {
        super(ProductView.class);
    }

    @Override
    public void serialize(
            ProductView value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeStartObject(value);
        generator.writeStringField("name", value.name());

        generator.writeFieldName("price");
        provider.defaultSerializeValue(value.price(), generator);

        generator.writeEndObject();
    }
}
```

`defaultSerializeValue()` yêu cầu provider chọn serializer mặc định phù hợp cho giá trị con. Nếu muốn áp dụng một serializer cụ thể cho value con, có thể lấy serializer qua provider hoặc gọi serializer đã được cung cấp theo cách phù hợp với lifecycle của Jackson.

Tránh gọi `provider.defaultSerializeValue(value, generator)` với chính `value` mà serializer hiện tại đang xử lý. Điều đó có thể khiến Jackson chọn lại cùng serializer, tạo đệ quy vô hạn. Trong serializer tùy biến, hãy ghi cấu trúc trực tiếp hoặc serialize các thuộc tính con, không gọi lại chính nó cho cùng object.

## 9. Serializer cho collection: khi nào cần tự điều khiển toàn bộ?

Nếu yêu cầu JSON của một property là cấu trúc hoàn toàn khác với array mặc định, serializer cho toàn bộ collection có thể phù hợp.

Ví dụ, ứng dụng muốn ghi `List<String>` thành một chuỗi ghép bằng dấu `|`:

```java
public class TagsSerializer extends StdSerializer<List<String>> {
    public TagsSerializer() {
        super((Class<List<String>>) (Class<?>) List.class);
    }

    @Override
    public void serialize(
            List<String> value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeString(String.join("|", value));
    }
}
```

Gắn vào property:

```java
public class Article {
    @JsonSerialize(using = TagsSerializer.class)
    private List<String> tags;
}
```

Kết quả:

```json
{
  "tags": "java|jackson|json"
}
```

Trong ví dụ này, `using` áp dụng cho toàn bộ `List`, vì output không còn là JSON array. Nếu mục tiêu chỉ là biến mỗi tag thành dạng khác nhưng vẫn giữ array, dùng `contentUsing` thay vì serializer toàn bộ list.

Lưu ý về generic type: Java type erasure khiến `List<String>` không có class literal riêng. Ví dụ serializer trên dùng raw `List.class` làm kiểu đại diện và cast có kiểm soát. Với serializer cho collection phức tạp, có thể cần xử lý generic type/contextualization kỹ hơn hoặc viết serializer chuyên biệt cho kiểu container rõ ràng.

## 10. Serializer cho kiểu bên thứ ba bằng Mix-in

Không phải lúc nào bạn cũng có thể sửa class để gắn annotation. Ví dụ, `Currency`, `LocalDate` hoặc một kiểu đến từ thư viện ngoài không thuộc source code của ứng dụng.

Jackson Mix-in cho phép bổ sung annotation cho kiểu đó từ một class riêng:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = ExternalValueSerializer.class)
abstract class ExternalValueMixin {
}
```

Đăng ký mix-in:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalValue.class, ExternalValueMixin.class);
```

Sau khi đăng ký, Jackson sử dụng annotation từ mix-in khi introspect `ExternalValue`. Cách này hữu ích khi muốn áp dụng serializer cho một kiểu bên thứ ba mà không sửa thư viện hoặc tạo wrapper chỉ để phục vụ serialization.

Nếu chỉ một property cần định dạng khác, có thể đặt `@JsonSerialize` trực tiếp trên property của DTO thay vì thay đổi cách biểu diễn toàn bộ kiểu bên thứ ba qua mix-in.

## 11. @JsonSerialize chỉ điều khiển chiều serialize

`@JsonSerialize` xác định cách Java value được ghi thành JSON. Nó không tự định nghĩa cách JSON được đọc ngược thành object Java.

Ví dụ `BigDecimalAsStringSerializer` ghi `BigDecimal` thành JSON string:

```json
{
  "total": "1250.75"
}
```

Khi deserialize vào property `BigDecimal`, Jackson có thể chuyển string số thành `BigDecimal` tùy coercion config và phiên bản, nhưng không nên giả định mọi serializer tùy biến đều có thể được đảo ngược tự động.

Nếu JSON output có cấu trúc không tương ứng với cách deserialize mặc định, hãy viết deserializer tương ứng bằng `@JsonDeserialize(using = ...)` hoặc thiết kế DTO/wire model phù hợp. Serializer và deserializer là hai thành phần riêng:

- `@JsonSerialize(using = ...)`: Java → JSON.
- `@JsonDeserialize(using = ...)`: JSON → Java.

Một serializer có thể ghi nhiều property, đổi tên trường, ghép nhiều giá trị hoặc thay kiểu JSON; Jackson không thể tự suy ra quy tắc đảo ngược tổng quát từ code serializer.

## 12. Xử lý null

Thông thường, khi property có giá trị Java `null`, Jackson sử dụng null serializer theo cấu hình của provider thay vì gọi `serialize()` của serializer thông thường cho một object value. Vì vậy, không nên viết logic trong `serialize()` rồi kỳ vọng nó sẽ xử lý mọi trường hợp property null.

Nếu API cần biểu diễn null theo một quy ước đặc biệt, hãy cấu hình null handling phù hợp ở mapper/property hoặc dùng cơ chế null serializer tương ứng của Jackson. Đồng thời, phân biệt:

- Property không được ghi do inclusion rule.
- Property được ghi với JSON `null`.
- Property có serializer tùy biến cho giá trị khác null.

Đây là các hành vi khác nhau. Hãy kiểm tra output thực tế với `null`, empty value và giá trị thông thường khi serializer tham gia vào DTO.

## 13. Serializer cần được khởi tạo như thế nào?

Khi annotation tham chiếu serializer bằng class:

```java
@JsonSerialize(using = MoneySerializer.class)
```

Jackson cần tạo instance serializer thông qua cơ chế serializer/handler của nó. Cách thông dụng là serializer có constructor không tham số công khai. Serializer nên giữ trạng thái bất biến hoặc không giữ dữ liệu phụ thuộc vào từng lần serialize, vì instance có thể được tái sử dụng giữa nhiều request.

Ví dụ không nên lưu giá trị đang serialize vào field mutable của serializer:

```java
// Không nên: serializer có thể được dùng lại đồng thời.
private String currentCurrency;
```

Hãy dùng biến local trong `serialize()` để giữ dữ liệu của lần gọi hiện tại. Nếu serializer cần dependency hoặc cấu hình phức tạp, cân nhắc đăng ký qua module, `HandlerInstantiator` hoặc cơ chế tích hợp dependency injection phù hợp với framework thay vì phụ thuộc vào constructor annotation đơn giản.

## 14. Khác biệt giữa @JsonSerialize và đăng ký serializer bằng Module

`@JsonSerialize` là cách gắn serializer gần với kiểu hoặc property. Jackson cũng cho phép đăng ký serializer qua `SimpleModule`:

```java
SimpleModule module = new SimpleModule();
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Hai cách phục vụ nhu cầu khác nhau:

| Cách | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| `@JsonSerialize` trên class | Kiểu được gắn annotation | Kiểu thuộc source code ứng dụng và có một quy tắc JSON chung |
| `@JsonSerialize` trên property | Một property | Cùng kiểu Java cần cách ghi khác nhau theo DTO/ngữ cảnh |
| `SimpleModule.addSerializer()` | Mapper đã đăng ký module | Cấu hình tập trung, kiểu bên thứ ba hoặc không muốn domain model phụ thuộc annotation |
| Mix-in kết hợp `@JsonSerialize` | Kiểu bên ngoài nhưng cần annotation metadata | Không thể sửa class gốc nhưng muốn dùng cơ chế annotation |

Nếu cùng một kiểu được cấu hình bằng nhiều cơ chế, cần hiểu thứ tự ưu tiên và cách mapper cụ thể giải quyết serializer. Tránh đăng ký trùng lặp mà không có chủ đích; hãy kiểm thử với đúng `ObjectMapper` mà ứng dụng sử dụng.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Serializer không được gọi | Annotation đặt trên thành phần Jackson không nhận diện hoặc mapper không dùng annotation introspector phù hợp | Kiểm tra visibility, field/getter và cấu hình mapper |
| Toàn bộ collection bị ghi thành một giá trị bất ngờ | Dùng `using` trên collection trong khi chỉ muốn đổi từng phần tử | Dùng `contentUsing` |
| Key map không đổi định dạng | Chỉ cấu hình `contentUsing` mà quên key serializer | Dùng `keyUsing` |
| Serializer bị gọi đệ quy vô hạn | Gọi `defaultSerializeValue()` lại chính object đang được serializer xử lý | Ghi cấu trúc/value con trực tiếp |
| Một kiểu bị thay định dạng ở nhiều API ngoài ý muốn | Đặt serializer ở cấp kiểu nhưng chỉ muốn một property | Chuyển annotation xuống property-level |
| JSON không đọc lại được | Serializer tạo wire format không tương thích với deserializer mặc định | Viết deserializer tương ứng hoặc điều chỉnh hợp đồng |
| Serializer lỗi với null | Mong serializer value thông thường xử lý Java null | Cấu hình null handling riêng |
| Lỗi khi tạo serializer | Serializer có constructor hoặc dependency không phù hợp cơ chế tạo instance | Dùng constructor không tham số hoặc đăng ký qua module/handler phù hợp |

Khi debug, hãy kiểm tra đúng `ObjectMapper` được sử dụng, vị trí annotation, kiểu property sau introspection và serializer thực tế được chọn. Một mapper được tạo thủ công trong unit test có thể không có cùng module hoặc mix-in với mapper do framework cấu hình.

## 16. Quy trình chọn phạm vi đăng ký

1. Xác định kiểu Java cần thay đổi cách ghi.
2. Nếu mọi lần serialize kiểu đó cần cùng biểu diễn, đặt `@JsonSerialize(using = ...)` trên class.
3. Nếu chỉ một field/getter cần cách ghi riêng, đặt annotation trên property.
4. Nếu property là collection/array và chỉ cần thay serializer từng phần tử, dùng `contentUsing`.
5. Nếu property là map và cần thay serializer key/value, dùng `keyUsing` và/hoặc `contentUsing`.
6. Viết serializer bằng `StdSerializer<T>` và ghi JSON qua `JsonGenerator`.
7. Dùng `SerializerProvider` để serialize value con theo cấu hình Jackson khi phù hợp.
8. Nếu không thể sửa class gốc, cân nhắc Mix-in hoặc đăng ký serializer qua module.
9. Nếu output cần đọc ngược theo quy tắc riêng, thiết kế deserializer tương ứng.

## 17. Ghi nhớ

- `@JsonSerialize(using = MySerializer.class)` gắn serializer tùy biến cho kiểu hoặc property được annotation.
- Type-level áp dụng quy ước chung cho kiểu; property-level chỉ thay đổi một property cụ thể.
- `StdSerializer<T>` giúp khai báo kiểu xử lý và override `serialize(value, generator, provider)`.
- Dùng `JsonGenerator` để ghi token JSON; không tự nối chuỗi JSON.
- `using` áp dụng cho toàn bộ property/container; `contentUsing` áp dụng cho phần tử hoặc value bên trong container; `keyUsing` áp dụng cho key của map.
- Dùng `SerializerProvider.defaultSerializeValue()` khi muốn Jackson chọn serializer cho giá trị con; tránh gọi lại chính object đang được serialize.
- `@JsonSerialize` chỉ điều khiển Java → JSON; cần `@JsonDeserialize` nếu muốn quy tắc đọc ngược tùy biến.
- Serializer được tham chiếu bằng class nên có cách khởi tạo phù hợp và không nên giữ trạng thái mutable theo từng request.
- Với kiểu bên thứ ba hoặc cấu hình tập trung, cân nhắc Mix-in hoặc `SimpleModule`.

Khi đăng ký serializer, hãy chọn phạm vi nhỏ nhất đáp ứng hợp đồng JSON. Dùng type-level khi kiểu có một biểu diễn thống nhất; dùng property-level khi chỉ một trường cần khác biệt; dùng `contentUsing` và `keyUsing` khi muốn điều khiển từng phần tử hoặc key/value của container. Cách đặt đúng phạm vi giúp serializer dễ tái sử dụng mà không làm thay đổi ngoài ý muốn các property khác trong ứng dụng.
