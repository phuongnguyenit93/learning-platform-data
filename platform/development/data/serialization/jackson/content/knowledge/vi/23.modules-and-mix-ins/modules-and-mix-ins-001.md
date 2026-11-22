# Đóng gói serializer và deserializer bằng SimpleModule

Jackson cho phép tùy biến cách một kiểu Java được ghi thành JSON và cách JSON được đọc thành kiểu Java. Khi chỉ có một property đặc biệt, có thể gắn serializer hoặc deserializer trực tiếp bằng annotation. Nhưng khi một ứng dụng cần tái sử dụng nhiều bộ xử lý, áp dụng chúng cho kiểu thuộc thư viện bên ngoài hoặc giữ domain model không phụ thuộc annotation Jackson, việc đóng gói các thành phần đó thành một module sẽ dễ quản lý hơn.

SimpleModule là lớp tiện ích của Jackson Databind để đăng ký các serializer, deserializer, key serializer, key deserializer và một số thành phần mở rộng khác. Sau khi đăng ký module vào ObjectMapper, các lần serialize và deserialize dùng mapper đó có thể sử dụng những bộ xử lý đã khai báo.

Bài này tập trung vào cách xây dựng module, đăng ký đúng phạm vi và kiểm thử hai chiều. Cần nhớ rằng serializer chỉ quyết định chiều Java sang JSON; muốn đọc lại JSON thành object, phải có deserializer hoặc một cơ chế binding phù hợp.

## 1. Module giải quyết vấn đề gì?

Giả sử ứng dụng có value object Money:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

Jackson có thể serialize record theo cấu trúc property mặc định. Nhưng hợp đồng của một hệ thống bên ngoài yêu cầu một dạng wire riêng, chẳng hạn:

~~~json
{
  "amount": 1250.50,
  "currency": "VND"
}
~~~

Ứng dụng cũng muốn kiểm tra chặt rằng amount phải là JSON number, currency phải là JSON string và không chấp nhận field sai kiểu.

Có thể viết MoneySerializer và MoneyDeserializer. Nếu mỗi class đều được gắn annotation hoặc mỗi service tự tạo mapper riêng, cấu hình có thể bị phân tán. Một module gom các bộ xử lý liên quan vào một đơn vị:

~~~text
Money JSON module
  |
  +-- MoneySerializer
  |
  +-- MoneyDeserializer
  |
  +-- CurrencyKeySerializer
  |
  +-- CurrencyKeyDeserializer
  |
  +-- các cấu hình Jackson liên quan
~~~

ObjectMapper đăng ký module một lần. Các thành phần dùng mapper đó sẽ có cùng chính sách cho những kiểu đã đăng ký.

SimpleModule đặc biệt hữu ích khi:

- Nhiều kiểu cần serializer/deserializer tùy biến.
- Cần đóng gói quy tắc JSON của một integration hoặc bounded context.
- Không thể sửa class vì kiểu thuộc thư viện bên ngoài.
- Domain model không muốn phụ thuộc annotation Jackson.
- Cần đăng ký cách xử lý Map key hoặc các thành phần mở rộng liên quan.
- Muốn cấu hình mapper tập trung và kiểm thử module như một đơn vị.

Nếu chỉ có một property cần đổi tên hoặc định dạng theo khả năng có sẵn, annotation thường đơn giản hơn. Module phù hợp khi có logic xử lý thực sự hoặc một nhóm cấu hình cần tái sử dụng.

## 2. SimpleModule thuộc Jackson Databind

SimpleModule nằm trong package:

~~~java
import com.fasterxml.jackson.databind.module.SimpleModule;
~~~

Nó thuộc jackson-databind, không phải jackson-core. Module làm việc với các API Databind như JsonSerializer, JsonDeserializer, KeyDeserializer và ObjectMapper.

Với Maven, dependency thường được quản lý bằng Jackson BOM để các artifact có cùng phiên bản:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Nếu dự án dùng Spring Boot hoặc một BOM khác, nên để dependency management của dự án quyết định phiên bản thay vì khai báo một phiên bản Jackson riêng lẻ cho module.

Tạo module có tên:

~~~java
SimpleModule moneyModule = new SimpleModule("money-json-module");
~~~

Tên module giúp nhận diện cấu hình khi debug và có ý nghĩa đối với cơ chế nhận diện module đã đăng ký. Với module dùng chung trong ứng dụng, hãy chọn tên rõ ràng và duy nhất.

## 3. Viết serializer cho một kiểu Java

Serializer nhận giá trị Java và ghi token JSON qua JsonGenerator. Có thể kế thừa StdSerializer để khai báo kiểu được xử lý.

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
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Serializer ghi một object có hai field. amount được ghi bằng writeNumberField nên JSON nhận một number; currency được ghi bằng writeStringField nên JSON nhận một string.

Không nên tự ghép chuỗi JSON bằng StringBuilder. JsonGenerator xử lý dấu ngoặc, dấu phẩy, escaping và kiểu token. Nếu đổi writeNumberField thành writeStringField, hợp đồng cũng thay đổi từ number sang string.

Với serializer dùng trong module, constructor của StdSerializer nên khai báo đúng kiểu. Khi đăng ký, truyền cả class và instance serializer để mapping được tường minh.

## 4. Viết deserializer tương ứng

Deserializer thực hiện chiều ngược lại: đọc token từ JsonParser, kiểm tra cấu trúc rồi tạo object Java.

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.math.BigDecimal;

public final class MoneyDeserializer extends StdDeserializer<Money> {

    public MoneyDeserializer() {
        super(Money.class);
    }

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonToken token = parser.currentToken();

        if (token == null) {
            token = parser.nextToken();
        }

        if (token != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(
                parser,
                "Money must be a JSON object"
            );
        }

        BigDecimal amount = null;
        String currency = null;
        boolean amountSeen = false;
        boolean currencySeen = false;

        while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw JsonMappingException.from(
                    parser,
                    "Unexpected end of Money object"
                );
            }

            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(
                    parser,
                    "Expected a property name"
                );
            }

            String name = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if (valueToken == null) {
                throw JsonMappingException.from(
                    parser,
                    "Missing value for property " + name
                );
            }

            switch (name) {
                case "amount" -> {
                    if (amountSeen) {
                        throw JsonMappingException.from(
                            parser,
                            "Duplicate property: amount"
                        );
                    }
                    amountSeen = true;

                    if (valueToken != JsonToken.VALUE_NUMBER_INT
                            && valueToken != JsonToken.VALUE_NUMBER_FLOAT) {
                        throw JsonMappingException.from(
                            parser,
                            "amount must be a JSON number"
                        );
                    }

                    amount = parser.getDecimalValue();
                }
                case "currency" -> {
                    if (currencySeen) {
                        throw JsonMappingException.from(
                            parser,
                            "Duplicate property: currency"
                        );
                    }
                    currencySeen = true;

                    if (valueToken != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                            parser,
                            "currency must be a JSON string"
                        );
                    }

                    currency = parser.getText();
                }
                default -> parser.skipChildren();
            }
        }

        if (!amountSeen || amount == null) {
            throw JsonMappingException.from(parser, "Missing amount");
        }

        if (!currencySeen || currency == null || currency.isBlank()) {
            throw JsonMappingException.from(parser, "Missing or empty currency");
        }

        return new Money(amount, currency);
    }
}
~~~

Deserializer kiểm tra root là object, đọc từng field theo tên và xác nhận loại token trước khi lấy giá trị. amount chấp nhận VALUE_NUMBER_INT hoặc VALUE_NUMBER_FLOAT vì BigDecimal có thể biểu diễn cả hai. currency chỉ chấp nhận VALUE_STRING.

Ví dụ này bỏ qua field không biết bằng skipChildren(). Nếu hợp đồng yêu cầu từ chối field lạ, thay nhánh default bằng JsonMappingException. Chính sách unknown property cần được chọn rõ trong deserializer tùy biến; đừng giả định cấu hình FAIL_ON_UNKNOWN_PROPERTIES sẽ tự kiểm tra các field mà code custom đã tự đọc.

Ví dụ cũng từ chối field amount hoặc currency bị lặp. Với một object có nhiều thuộc tính hơn, có thể dùng Set tên field đã thấy hoặc bật strict duplicate detection ở JsonFactory.

## 5. Đăng ký serializer và deserializer trong SimpleModule

Sau khi có các lớp xử lý, đăng ký chúng vào module:

~~~java
SimpleModule moneyModule = new SimpleModule("money-json-module");

moneyModule.addSerializer(Money.class, new MoneySerializer());
moneyModule.addDeserializer(Money.class, new MoneyDeserializer());
~~~

Các phương thức này ghép kiểu Java với bộ xử lý tương ứng:

- addSerializer(type, serializer) đăng ký cách ghi kiểu.
- addDeserializer(type, deserializer) đăng ký cách đọc kiểu.

Tiếp theo, đăng ký module vào ObjectMapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(moneyModule)
    .build();
~~~

Hoặc với mapper được tạo trực tiếp:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(moneyModule);
~~~

Hai cách đều có mục đích đăng ký module. Dùng builder thường thuận tiện khi muốn hoàn tất cấu hình trước khi tạo mapper. Với ứng dụng có mapper được framework quản lý, cần đăng ký module vào đúng mapper mà HTTP converter hoặc message serializer thực sự sử dụng.

Sau khi mapper được cấu hình xong, hãy chia sẻ mapper đó thay vì tạo mapper mới ở từng request. ObjectMapper được thiết kế để dùng chung sau khi cấu hình hoàn tất; không nên thay đổi cấu hình module trong khi các luồng đang serialize/deserialize.

## 6. Ví dụ sử dụng module hai chiều

Sau khi đăng ký, serialize Money:

~~~java
Money money = new Money(new BigDecimal("1250.50"), "VND");

String json = mapper.writeValueAsString(money);
~~~

JSON nhận được:

~~~json
{
  "amount": 1250.50,
  "currency": "VND"
}
~~~

Deserialize lại:

~~~java
Money restored = mapper.readValue(json, Money.class);
~~~

Deserializer kiểm tra token và tạo Money. Có thể sử dụng cùng mapper cho cả hai chiều.

Round-trip test giúp xác nhận serializer và deserializer thống nhất với nhau. Nếu serializer ghi amount thành JSON string nhưng deserializer chỉ nhận JSON number, hợp đồng hai chiều sẽ không khớp. Khi hai chiều cố ý khác nhau, cần ghi rõ đó là API chỉ xuất hoặc chỉ nhận.

## 7. Đăng ký key serializer và key deserializer cho Map

Một Map được ghi thành JSON object. Giá trị Map được serialize như value thông thường, nhưng key trở thành tên property JSON. Vì vậy, key có cơ chế riêng.

Ví dụ:

~~~java
Map<Currency, BigDecimal> balances;
~~~

Currency là kiểu Java, còn tên field trong JSON phải là chuỗi như USD hoặc VND. Serializer cho value Currency không quyết định cách ghi key này.

Key serializer:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;
import java.util.Currency;

public final class CurrencyKeySerializer extends JsonSerializer<Currency> {

    @Override
    public void serialize(
            Currency value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeFieldName(value.getCurrencyCode());
    }
}
~~~

Key deserializer:

~~~java
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.KeyDeserializer;

import java.io.IOException;
import java.util.Currency;

public final class CurrencyKeyDeserializer extends KeyDeserializer {

    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context) throws IOException {

        try {
            return Currency.getInstance(key);
        } catch (IllegalArgumentException exception) {
            return context.handleWeirdKey(
                Currency.class,
                key,
                "Expected a supported ISO 4217 currency code"
            );
        }
    }
}
~~~

Đăng ký trong cùng module:

~~~java
moneyModule.addKeySerializer(
    Currency.class,
    new CurrencyKeySerializer()
);

moneyModule.addKeyDeserializer(
    Currency.class,
    new CurrencyKeyDeserializer()
);
~~~

Ví dụ Map:

~~~java
Map<Currency, BigDecimal> balances = new HashMap<>();
balances.put(Currency.getInstance("VND"), new BigDecimal("250000"));
balances.put(Currency.getInstance("USD"), new BigDecimal("10.50"));

String json = mapper.writeValueAsString(balances);
~~~

JSON có thể có dạng:

~~~json
{
  "USD": 10.50,
  "VND": 250000
}
~~~

Khi đọc:

~~~java
JavaType mapType = mapper.getTypeFactory()
    .constructMapType(
        Map.class,
        Currency.class,
        BigDecimal.class
    );

Map<Currency, BigDecimal> restored =
    mapper.readValue(json, mapType);
~~~

Key deserializer nhận tên property dạng String và chuyển nó thành Currency. Nếu key không hợp lệ, context.handleWeirdKey báo lỗi mapping theo cơ chế của Jackson.

Hãy phân biệt rõ ba vai trò:

| API đăng ký | Xử lý |
|---|---|
| addSerializer | Giá trị của một kiểu Java. |
| addDeserializer | Đọc giá trị JSON thành một kiểu Java. |
| addKeySerializer | Chuyển Map key thành tên field JSON. |
| addKeyDeserializer | Chuyển tên field JSON thành Map key Java. |

Nếu Map dùng key kiểu tùy chỉnh, cần kiểm tra rằng cách chuyển key thành String là duy nhất. Hai key Java khác nhau không nên bị ghi thành cùng một tên JSON.

## 8. Serializer cho phần tử collection và value của Map

Collection có cấu trúc container, còn phần tử bên trong được serialize theo serializer của kiểu phần tử. Nếu module đã đăng ký MoneySerializer cho Money, các property kiểu List<Money> thường sử dụng serializer Money cho từng phần tử.

~~~java
public record InvoiceResponse(
    String invoiceId,
    List<Money> lineAmounts
) {}
~~~

Không cần đăng ký một serializer riêng cho List<Money> nếu chỉ muốn từng Money được ghi theo MoneySerializer.

Nếu chỉ một property collection cần cách ghi khác, có thể dùng annotation ở property:

~~~java
@JsonSerialize(contentUsing = SpecialMoneySerializer.class)
private List<Money> specialAmounts;
~~~

Các thuộc tính annotation có vai trò khác nhau:

- using: serializer cho chính property.
- contentUsing: serializer cho phần tử collection hoặc value của container.
- keyUsing: serializer cho key của Map.

SimpleModule cũng có thể đăng ký serializer theo kiểu phần tử để tái sử dụng trên nhiều collection. Nếu yêu cầu phụ thuộc generic type phức tạp, không nên cố đăng ký một serializer cho List.class rồi kỳ vọng phân biệt được mọi List<Money>, List<String> và List<OtherType>. Type erasure làm cho mapping theo raw class không đủ thông tin về generic argument. Khi cần xử lý generic type nâng cao, hãy xem xét contextual serializer hoặc extension API phù hợp hơn.

## 9. Module có thể đóng gói nhiều thành phần hơn serializer

SimpleModule còn hỗ trợ đăng ký các thành phần Databind khác, tùy phiên bản Jackson, chẳng hạn:

| Thành phần | Công dụng |
|---|---|
| addSerializer | Serializer cho kiểu giá trị. |
| addDeserializer | Deserializer cho kiểu giá trị. |
| addKeySerializer | Serializer cho Map key. |
| addKeyDeserializer | Deserializer cho Map key. |
| addAbstractTypeMapping | Ánh xạ kiểu trừu tượng sang kiểu triển khai. |
| addBeanSerializerModifier | Điều chỉnh quá trình tạo bean serializer. |
| addBeanDeserializerModifier | Điều chỉnh quá trình tạo bean deserializer. |
| addValueInstantiator | Tùy biến cách tạo instance. |

Ví dụ ánh xạ interface sang implementation:

~~~java
module.addAbstractTypeMapping(
    PaymentMethod.class,
    CardPaymentMethod.class
);
~~~

Khi Jackson cần tạo kiểu PaymentMethod, mapping có thể hướng quá trình tạo object đến CardPaymentMethod. Cần bảo đảm kiểu triển khai tương thích và JSON có đủ thông tin để tạo instance.

Các modifier và value instantiator là cơ chế mở rộng sâu hơn. Nếu chỉ cần serializer/deserializer cho một kiểu cụ thể, các phương thức addSerializer và addDeserializer là đủ; không nên thêm modifier phức tạp khi chưa có nhu cầu.

API cụ thể có thể khác theo dòng Jackson. Hãy tham chiếu phiên bản jackson-databind mà dự án đang dùng trước khi sử dụng các extension nâng cao.

## 10. Phân biệt SimpleModule với mix-in

Module và mix-in giải quyết hai nhu cầu liên quan nhưng khác nhau.

**SimpleModule** đăng ký logic thực thi như serializer, deserializer, key serializer và các thành phần Databind.

**Mix-in** bổ sung metadata annotation cho một class mà không sửa source class đó. Mix-in thường được gắn bằng ObjectMapper.addMixIn().

Ví dụ một class thuộc thư viện bên ngoài:

~~~java
public class VendorUser {
    public Long getId() { ... }
    public String getName() { ... }
}
~~~

Muốn đổi tên property khi serialize, có thể tạo mix-in:

~~~java
abstract class VendorUserMixIn {

    @JsonProperty("user_id")
    abstract Long getId();
}
~~~

Đăng ký:

~~~java
ObjectMapper mapper = new ObjectMapper();

mapper.addMixIn(VendorUser.class, VendorUserMixIn.class);
~~~

Mix-in cho Jackson biết cách áp dụng annotation như thể chúng nằm trên class đích. Nó không tự chứa logic serialize tùy biến.

Nếu class bên ngoài cần một wire format hoàn toàn riêng, module có thể đăng ký serializer/deserializer. Nếu chỉ cần thêm annotation chuẩn như @JsonProperty, @JsonIgnore hoặc @JsonFormat, mix-in có thể đủ.

Có thể kết hợp cả hai: module đóng gói custom handlers, còn mix-in bổ sung annotation cho các property khác. Hãy tránh cấu hình hai cơ chế cùng điều khiển một kiểu theo những cách mâu thuẫn; khi custom serializer đã tự ghi toàn bộ object, nhiều annotation property mặc định có thể không còn tác động đến output đó.

## 11. Đóng gói module thành class dùng lại

Thay vì tạo và đăng ký SimpleModule rải rác, có thể tạo một factory:

~~~java
public final class MoneyJacksonModule {

    private MoneyJacksonModule() {
    }

    public static SimpleModule create() {
        SimpleModule module = new SimpleModule("money-json-module");

        module.addSerializer(Money.class, new MoneySerializer());
        module.addDeserializer(Money.class, new MoneyDeserializer());

        module.addKeySerializer(
            Currency.class,
            new CurrencyKeySerializer()
        );
        module.addKeyDeserializer(
            Currency.class,
            new CurrencyKeyDeserializer()
        );

        return module;
    }
}
~~~

Cách sử dụng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(MoneyJacksonModule.create())
    .build();
~~~

Factory này giúp các ứng dụng dùng chung một cấu hình Money. Nếu module có nhiều thành phần phụ thuộc nhau, có thể tạo constructor hoặc builder riêng thay vì factory static.

Một module có thể được đóng gói thành thư viện nội bộ để nhiều service dùng chung. Khi làm vậy:

- Công bố rõ các kiểu Java được hỗ trợ.
- Tài liệu hóa JSON shape mà serializer tạo ra.
- Tài liệu hóa input mà deserializer chấp nhận.
- Đồng bộ phiên bản Jackson với dependency management của ứng dụng.
- Tránh để module phụ thuộc vào mapper toàn cục hoặc trạng thái mutable của request.
- Có test độc lập cho module và test tích hợp ở ứng dụng sử dụng nó.

## 12. Đăng ký module trong ứng dụng framework

Trong ứng dụng Java thuần, có thể đăng ký trực tiếp bằng JsonMapper.builder() hoặc ObjectMapper.registerModule().

Trong Spring Boot, các phiên bản auto-configuration thông dụng có thể tự phát hiện bean kiểu Module và đăng ký chúng vào ObjectMapper do framework tạo. Ví dụ:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    public Module moneyJacksonModule() {
        return MoneyJacksonModule.create();
    }
}
~~~

Điều này phụ thuộc vào cấu hình và phiên bản Spring Boot. Nếu ứng dụng tự tạo ObjectMapper, dùng custom HttpMessageConverter hoặc có nhiều mapper cho các integration khác nhau, cần đăng ký module vào từng mapper thực sự được sử dụng.

Một lỗi dễ gặp là tạo module đúng nhưng đăng ký vào mapper không được endpoint sử dụng. Unit test với mapper tự tạo vẫn có thể thành công, trong khi HTTP request thực tế tiếp tục dùng mapper mặc định.

Vì vậy, với framework, hãy kiểm tra bean, converter hoặc message codec ở đúng đường dữ liệu. Integration test qua HTTP hoặc message consumer giúp xác nhận module đã được áp dụng thực sự.

## 13. Thứ tự đăng ký và xung đột giữa các module

Một ứng dụng có thể đăng ký nhiều module:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(dateModule)
    .addModule(moneyModule)
    .addModule(apiCompatibilityModule)
    .build();
~~~

Mỗi module có thể bổ sung handler cho các kiểu khác nhau. Tuy nhiên, nếu hai module cùng đăng ký serializer hoặc deserializer cho một kiểu, cấu hình có thể có xung đột hoặc phụ thuộc vào thứ tự đăng ký và cơ chế lookup của phiên bản Jackson.

Không nên để nhiều module cùng định nghĩa một wire representation cho Money mà không có quyết định rõ ràng. Hãy:

- Mỗi kiểu wire có một nơi sở hữu chính.
- Tách mapper nếu hai integration cần biểu diễn khác nhau.
- Đặt tên module rõ ràng.
- Kiểm tra thứ tự đăng ký nếu có override có chủ đích.
- Viết test trên mapper được cấu hình cuối cùng.

Đăng ký cùng một module nhiều lần cũng không phải cách cập nhật serializer. Hãy xây dựng mapper với tập module hoàn chỉnh ngay từ đầu. Nếu cần chính sách khác, tạo mapper hoặc ObjectWriter/ObjectReader phù hợp thay vì thay đổi cấu hình trong lúc xử lý request.

## 14. Giới hạn của đăng ký theo kiểu trong SimpleModule

SimpleModule được thiết kế cho các mapping class-to-handler thông dụng. Khi đăng ký serializer cho một class cơ sở hoặc interface, đừng mặc định rằng mọi subtype đều sẽ được xử lý theo đúng serializer đó trong mọi tình huống.

Ví dụ:

~~~java
module.addSerializer(PaymentMethod.class, new PaymentMethodSerializer());
~~~

Nếu ứng dụng có CardPaymentMethod và BankTransferMethod, hãy kiểm tra cách Jackson chọn serializer cho từng kiểu runtime. Nếu mỗi subtype có JSON shape riêng, đăng ký serializer cụ thể cho từng subtype hoặc dùng cơ chế polymorphic/extension phù hợp.

Tương tự, đăng ký cho raw List.class không cung cấp đủ thông tin để phân biệt List<Money> với List<String>. Serializer cho phần tử Money thường là lựa chọn đúng nếu mọi Money trong collection có cùng wire format.

Khi cần matching theo hệ thống kế thừa, generic type hoặc điều kiện phức tạp, có thể cần API mở rộng như Serializers, Deserializers, BeanSerializerModifier hoặc ContextualSerializer. Hãy chọn extension theo yêu cầu thực tế thay vì biến SimpleModule thành một framework registry quá phức tạp.

## 15. Xử lý null trong custom serializer và deserializer

Jackson thường xử lý giá trị null bằng null serializer riêng. Vì vậy, phương thức serialize() của MoneySerializer thường không được gọi với value null trong đường serialize thông thường.

Nếu muốn property null bị bỏ qua, có thể dùng @JsonInclude hoặc cấu hình inclusion trên mapper. Nếu cần null serializer riêng, có thể dùng nullsUsing ở property hoặc cơ chế provider tương ứng.

Ở chiều đọc, explicit JSON null có thể được xử lý qua getNullValue() của deserializer hoặc cấu hình null phù hợp. Không nên cho rằng deserialize() luôn được gọi với token VALUE_NULL.

Missing property cũng khác explicit null. Deserializer cho một kiểu không tự biết property đã vắng mặt trong object cha nếu Databind không gọi nó cho property đó. Muốn kiểm soát field bắt buộc bị thiếu, cần creator/property validation hoặc custom deserializer cho object cha.

Hãy kiểm thử riêng:
- Property bị thiếu.
- Property có JSON null.
- Property có giá trị đúng kiểu.
- Property có giá trị rỗng.
- Property có token sai kiểu.

## 16. Tránh giữ trạng thái theo từng request trong serializer

Serializer và deserializer được mapper quản lý và có thể được tái sử dụng qua nhiều lần gọi. Không nên lưu dữ liệu tạm của một request vào field mutable của serializer rồi thay đổi khi serialize.

Không nên:

~~~java
public final class MoneySerializer extends StdSerializer<Money> {
    private String currentCurrency;

    // serialize() cập nhật currentCurrency theo từng value
}
~~~

Nếu nhiều luồng cùng sử dụng serializer, trạng thái này có thể bị ghi đè và gây kết quả không xác định.

Serializer nên ưu tiên stateless: nhận value, ghi output, rồi kết thúc. Nếu quy tắc phụ thuộc metadata của property, dùng ContextualSerializer để tạo instance cấu hình theo property thay vì giữ trạng thái request trong một singleton mutable.

Deserializer cũng nên tránh tích lũy dữ liệu giữa các lần gọi. Mọi biến parse như amount, currency và tập field đã thấy phải là biến local trong deserialize().

## 17. Kiểm thử module bằng round-trip test

Test nên tạo mapper bằng đúng module production sử dụng, sau đó kiểm tra cả serialize lẫn deserialize.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

class MoneyJacksonModuleTest {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(MoneyJacksonModule.create())
        .build();

    @Test
    void serializesMoneyUsingModuleSerializer() throws Exception {
        Money money = new Money(new BigDecimal("1250.50"), "VND");

        String json = mapper.writeValueAsString(money);
        JsonNode tree = mapper.readTree(json);

        assertEquals(new BigDecimal("1250.50"), tree.path("amount").decimalValue());
        assertEquals("VND", tree.path("currency").asText());
    }

    @Test
    void deserializesMoneyUsingModuleDeserializer() throws Exception {
        String json = """
            {
              "amount": 1250.50,
              "currency": "VND"
            }
            """;

        Money money = mapper.readValue(json, Money.class);

        assertEquals(new BigDecimal("1250.50"), money.amount());
        assertEquals("VND", money.currency());
    }

    @Test
    void roundTripsMoney() throws Exception {
        Money original = new Money(new BigDecimal("1250.50"), "VND");

        String json = mapper.writeValueAsString(original);
        Money restored = mapper.readValue(json, Money.class);

        assertEquals(original, restored);
    }
}
~~~

Assertion trên so sánh BigDecimal trực tiếp để tránh mất độ chính xác khi chuyển qua double. Với record Money, equals() của BigDecimal phân biệt scale, nên hãy thống nhất scale trong input hoặc so sánh bằng compareTo() nếu hợp đồng không xem scale là khác biệt.

Bổ sung test cho Map key:

~~~java
@Test
void roundTripsCurrencyMapKeys() throws Exception {
    Map<Currency, BigDecimal> balances = Map.of(
        Currency.getInstance("USD"), new BigDecimal("10.50")
    );

    JavaType type = mapper.getTypeFactory().constructMapType(
        Map.class,
        Currency.class,
        BigDecimal.class
    );

    String json = mapper.writeValueAsString(balances);

    Map<Currency, BigDecimal> restored =
        mapper.readValue(json, type);

    assertEquals(balances, restored);
}
~~~

Cần có thêm test cho key không hợp lệ, field thiếu, null, sai token type, unknown field và duplicate field theo chính sách của module.

## 18. Những lỗi thường gặp khi đóng gói module

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Serializer không được gọi | Module chưa đăng ký vào mapper thực tế hoặc kiểu runtime khác kiểu đã đăng ký. | Kiểm tra mapper và kiểu runtime của value. |
| Deserializer không được gọi | Endpoint đang dùng mapper/converter khác. | Kiểm tra đường binding thực tế. |
| Map key vẫn sai định dạng | Chỉ đăng ký value serializer. | Đăng ký key serializer/deserializer riêng. |
| List có phần tử không đúng wire format | Đăng ký serializer cho raw collection thay vì kiểu phần tử. | Đăng ký serializer cho phần tử hoặc dùng contentUsing. |
| Field lạ vẫn được chấp nhận | Custom deserializer tự bỏ qua unknown field. | Thay skip bằng lỗi nếu hợp đồng yêu cầu strict. |
| Null không đi qua deserialize() | Jackson dùng null handling riêng. | Xem getNullValue(), null configuration hoặc nullsUsing. |
| Serializer hoạt động ở unit test nhưng không hoạt động qua HTTP | Test dùng mapper tự tạo khác mapper của framework. | Viết integration test qua đúng endpoint/converter. |
| Hai module ghi cùng một kiểu khác nhau | Mapping bị đăng ký trùng. | Tách mapper hoặc xác định một handler sở hữu duy nhất. |
| Serializer gây lỗi khi chạy song song | Có state mutable dùng chung giữa các request. | Giữ serializer stateless hoặc contextual hóa cấu hình. |

## 19. Quy trình xây dựng một module có thể tái sử dụng

Khi tạo module cho một nhóm kiểu dữ liệu, có thể làm theo trình tự:

1. Xác định các kiểu Java và JSON shape mà module chịu trách nhiệm.
2. Viết serializer cho chiều ghi và deserializer cho chiều đọc nếu cần round-trip.
3. Viết key serializer/key deserializer riêng cho Map key.
4. Quy định rõ null, missing, empty, unknown field và duplicate field.
5. Đăng ký tất cả handler vào một SimpleModule có tên rõ ràng.
6. Đăng ký module vào ObjectMapper trước khi mapper được dùng.
7. Nếu dùng mix-in, đăng ký metadata riêng bằng ObjectMapper.addMixIn().
8. Kiểm thử module độc lập và qua mapper/framework thực tế.
9. Công bố wire contract cùng phiên bản module.
10. Tránh đăng ký handler xung đột cho cùng kiểu trong nhiều module.

Một module tốt gom các quy tắc có cùng trách nhiệm. Không nên tạo một module khổng lồ chứa mọi serializer của ứng dụng nếu các nhóm dữ liệu thuộc các integration hoặc hợp đồng khác nhau. Tách module giúp mapper chỉ nhận đúng chính sách cần thiết.

## Kết luận

SimpleModule giúp đóng gói serializer, deserializer và các bộ xử lý JSON liên quan thành một đơn vị có thể đăng ký vào ObjectMapper. Dùng addSerializer/addDeserializer cho giá trị, addKeySerializer/addKeyDeserializer cho Map key, rồi đăng ký module trước khi mapper bắt đầu được sử dụng.

Hãy giữ serializer/deserializer stateless, kiểm tra token và null theo hợp đồng, xác nhận mapper thực tế đã nhận module và kiểm thử cả hai chiều. Mix-in bổ sung annotation metadata cho class không thể sửa, còn SimpleModule đăng ký logic xử lý; hai cơ chế có thể phối hợp nhưng không thay thế nhau. Khi nhu cầu chỉ là đổi tên hoặc định dạng chuẩn, annotation vẫn gọn hơn; module phù hợp khi cần tái sử dụng một nhóm quy tắc chuyển đổi có logic rõ ràng.

