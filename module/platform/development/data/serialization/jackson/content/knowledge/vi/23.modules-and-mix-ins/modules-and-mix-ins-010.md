# Thiết kế module có thể kiểm thử độc lập với ứng dụng

Jackson Module là một gói cấu hình có thể đăng ký vào `ObjectMapper` để bổ sung cách Jackson hiểu và xử lý các kiểu dữ liệu. Module có thể cung cấp serializer, deserializer, key serializer, mix-in, ánh xạ kiểu trừu tượng, modifier và một số thành phần mở rộng khác. Khi thiết kế module tốt, phần tích hợp Jackson có thể được kiểm thử bằng một mapper nhỏ trong unit test, không cần khởi động toàn bộ ứng dụng Spring hoặc kết nối database, HTTP hay message broker.

Mục tiêu của một module độc lập là đóng gói một quy tắc JSON có ranh giới rõ ràng. Ví dụ, module tiền tệ có thể định nghĩa cách ghi và đọc value object `Money`; module đối tác có thể gắn mix-in cho kiểu thư viện bên thứ ba; module thời gian có thể chuẩn hóa một số kiểu legacy. Ứng dụng chỉ chịu trách nhiệm đăng ký module và cấu hình những phần thuộc hợp đồng của nó.

Để đạt được khả năng kiểm thử độc lập, module cần phụ thuộc vào API Jackson và các kiểu domain cần thiết, tránh phụ thuộc vào Spring context, repository, HTTP request, biến môi trường hoặc một mapper toàn cục. Các thành phần bên trong module nên nhận cấu hình qua constructor hoặc được tạo từ những giá trị bất biến, sau đó có thể được kiểm thử trực tiếp.

## 1. Jackson Module là gì?

Trong Jackson Databind, `Module` là cơ chế đóng gói các thành phần mở rộng và đăng ký chúng vào mapper. Một module có thể bổ sung:

- Serializer cho kiểu Java.
- Deserializer cho kiểu Java.
- Serializer/deserializer cho tên khóa của `Map`.
- Mix-in annotation cho class mà ứng dụng không thể sửa.
- Ánh xạ abstract type sang implementation.
- Bean serializer/deserializer modifier.
- Value instantiator hoặc các thành phần mở rộng khác của Databind.

`SimpleModule` là lớp tiện ích để đăng ký các thành phần phổ biến mà không cần tự triển khai toàn bộ API `Module`. Với nhiều ứng dụng, kế thừa `SimpleModule` là cách đơn giản và dễ kiểm thử.

Cần phân biệt Jackson Module với Java Platform Module System (JPMS). Jackson Module là một đối tượng cấu hình Databind được đăng ký vào `ObjectMapper`; nó không phải file `module-info.java` và không thay thế module Java ở cấp hệ thống.

## 2. Xác định ranh giới của module

Một module nên có một mục đích dễ mô tả. Ví dụ:

- `MoneyJacksonModule`: quy tắc JSON cho `Money`.
- `PartnerApiJacksonModule`: serializer, deserializer và mix-in dành cho hợp đồng đối tác.
- `LegacyDateJacksonModule`: cách xử lý một số kiểu ngày giờ legacy.
- `ThirdPartyTypesJacksonModule`: mix-in cho các kiểu thư viện bên ngoài.

Tránh tạo một module khổng lồ chứa mọi tùy chỉnh của ứng dụng. Khi module có nhiều quy tắc không liên quan, việc đăng ký, kiểm thử, thay đổi và tái sử dụng trở nên khó khăn.

Một module độc lập nên có các đặc điểm:

1. Có tên và trách nhiệm rõ ràng.
2. Không tự tạo hoặc giữ một `ObjectMapper` toàn cục.
3. Không truy cập Spring bean, repository, database hay HTTP request.
4. Nhận các tùy chọn cần thiết qua constructor hoặc cấu hình bất biến.
5. Không phụ thuộc vào thứ tự khởi tạo của toàn bộ ứng dụng.
6. Có unit test đăng ký module vào mapper tối giản.
7. Có thể được ứng dụng khác tái sử dụng mà không phải sao chép logic.
8. Không âm thầm thay đổi những kiểu dữ liệu ngoài phạm vi đã công bố.

## 3. Ví dụ: tạo Money value object

Ta dùng `Money` làm kiểu nghiệp vụ xuyên suốt bài học. Giá trị gồm số tiền và đơn vị tiền tệ:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Hợp đồng JSON của module được xác định là một object:

~~~json
{
  "amount": "125000.50",
  "currency": "VND"
}
~~~

Amount được biểu diễn bằng chuỗi thập phân để tránh client phải parse giá trị tài chính qua kiểu dấu phẩy động binary64. Currency là mã ISO 4217. Đây là lựa chọn hợp đồng của ví dụ; một hệ thống khác có thể chọn JSON number nếu miền giá trị và consumer cho phép.

Module sẽ cung cấp cả serializer và deserializer để kiểu `Money` có thể được ghi và đọc theo cùng một cấu trúc.

## 4. Viết serializer và deserializer tách biệt

Serializer chịu trách nhiệm chuyển `Money` thành JSON. Nó không cần biết ứng dụng đang chạy trong Spring, đang ghi HTTP response hay đang xuất file.

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

Deserializer đọc cấu trúc tương ứng và tạo lại value object:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.DeserializationContext;
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

        JsonNode root = parser.getCodec().readTree(parser);
        if (root == null || !root.isObject()) {
            throw JsonMappingException.from(
                parser,
                "Money must be a JSON object"
            );
        }

        JsonNode amountNode = root.get("amount");
        JsonNode currencyNode = root.get("currency");

        if (amountNode == null || !amountNode.isTextual()) {
            throw JsonMappingException.from(
                parser,
                "Money.amount must be a decimal string"
            );
        }

        if (currencyNode == null || !currencyNode.isTextual()) {
            throw JsonMappingException.from(
                parser,
                "Money.currency must be a string"
            );
        }

        try {
            BigDecimal amount = new BigDecimal(amountNode.textValue());
            Currency currency = Currency.getInstance(currencyNode.textValue());
            return new Money(amount, currency);
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser,
                "Invalid Money value",
                exception
            );
        }
    }
}
~~~

Trong code thực tế, hãy quyết định rõ có cho phép field thừa hay không, có chấp nhận amount dạng JSON number hay chỉ string, có giới hạn scale hay không và lỗi nào được trả về cho client. Ví dụ trên cố ý yêu cầu amount là chuỗi và currency là chuỗi để hợp đồng không mơ hồ.

Serializer và deserializer là hai thành phần riêng. Có thể chỉ đăng ký serializer nếu ứng dụng chỉ xuất dữ liệu; nhưng nếu `Money` được dùng trong request DTO hoặc cần round-trip, module nên cung cấp deserializer tương ứng.

## 5. Đóng gói chúng trong SimpleModule

Tạo một lớp module chịu trách nhiệm đăng ký các handler:

~~~java
import com.fasterxml.jackson.databind.module.SimpleModule;

public final class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule() {
        super("MoneyJacksonModule");
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
~~~

Lớp module chỉ cần biết kiểu `Money` và các serializer/deserializer tương ứng. Nó không cần biết mapper nào sẽ sử dụng, mapper thuộc ứng dụng nào hoặc request đến từ đâu.

Đăng ký module vào mapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new MoneyJacksonModule())
    .build();
~~~

Sau khi đăng ký, Databind tự chọn `MoneySerializer` khi ghi `Money` và `MoneyDeserializer` khi đọc `Money`.

### 5.1. Vì sao nên tạo module riêng?

Nếu đăng ký serializer trực tiếp ở nhiều nơi và mỗi nơi tự xây dựng handler, quy tắc có thể bị phân tán. Khi gom vào `MoneyJacksonModule`, ta có một đơn vị cấu hình có tên, có thể đăng ký, kiểm thử và tái sử dụng như một thành phần.

Module cũng giúp ứng dụng tránh phải biết chi tiết serializer nào cần gắn cho kiểu nào. Composition root chỉ cần đăng ký module theo hợp đồng.

## 6. Kiểm thử module độc lập bằng ObjectMapper tối giản

Đây là phần cốt lõi của yêu cầu “kiểm thử độc lập với ứng dụng”. Unit test không cần tạo Spring application context, không cần khởi tạo controller và không cần kết nối database. Chỉ cần một mapper được cấu hình với module đang kiểm thử.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.math.BigDecimal;
import java.util.Currency;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MoneyJacksonModuleTest {
    private ObjectMapper mapper;

    @BeforeEach
    void setUp() {
        mapper = JsonMapper.builder()
            .addModule(new MoneyJacksonModule())
            .build();
    }

    @Test
    void serializesMoneyUsingTheModuleContract() throws Exception {
        Money money = new Money(
            new BigDecimal("125000.50"),
            Currency.getInstance("VND")
        );

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(money)
        );

        assertEquals("125000.50", json.path("amount").asText());
        assertEquals("VND", json.path("currency").asText());
    }

    @Test
    void deserializesMoneyUsingTheModuleContract() throws Exception {
        String json = """
            {
              "amount": "125000.50",
              "currency": "VND"
            }
            """;

        Money money = mapper.readValue(json, Money.class);

        assertEquals(new BigDecimal("125000.50"), money.amount());
        assertEquals(Currency.getInstance("VND"), money.currency());
    }

    @Test
    void roundTripsMoney() throws Exception {
        Money original = new Money(
            new BigDecimal("10.25"),
            Currency.getInstance("USD")
        );

        String json = mapper.writeValueAsString(original);
        Money restored = mapper.readValue(json, Money.class);

        assertEquals(original, restored);
    }
}
~~~

Các test này chứng minh module hoạt động với Jackson Databind mà không phụ thuộc vào cấu hình của ứng dụng. Chúng cũng giúp phát hiện trường hợp module quên đăng ký serializer hoặc deserializer.

Một test module độc lập nên tập trung vào hợp đồng JSON của module: token, tên field, kiểu dữ liệu, null, giá trị biên và round-trip nếu được hỗ trợ. Test không cần khởi động Spring chỉ để xác nhận serializer ghi đúng object.

## 7. Kiểm thử dữ liệu không hợp lệ

Module không chỉ cần xử lý dữ liệu hợp lệ. Deserializer cần từ chối dữ liệu không phù hợp với hợp đồng.

~~~java
@Test
void rejectsNumericAmountWhenContractRequiresString() {
    String json = """
        {
          "amount": 125000.50,
          "currency": "VND"
        }
        """;

    assertThrows(
        JsonMappingException.class,
        () -> mapper.readValue(json, Money.class)
    );
}

@Test
void rejectsUnknownCurrencyCode() {
    String json = """
        {
          "amount": "100.00",
          "currency": "NOT_A_CURRENCY"
        }
        """;

    assertThrows(
        JsonMappingException.class,
        () -> mapper.readValue(json, Money.class)
    );
}
~~~

Có thể bổ sung test cho JSON root không phải object, thiếu amount hoặc currency, amount rỗng/sai cú pháp/quá lớn, currency null hoặc mã không tồn tại, field thừa nếu hợp đồng yêu cầu strict schema, giá trị âm hoặc scale không được domain cho phép, và JSON null.

Nếu module có giới hạn nghiệp vụ như amount tối đa hoặc scale, hãy xác định liệu đó là invariant của `Money` hay chính sách của API. Quy tắc thuộc domain nên được bảo vệ ở constructor/factory; module tập trung chuyển đổi JSON và báo lỗi có ngữ cảnh.

## 8. Module có thể kiểm thử bằng nhiều mapper cấu hình khác nhau

Một module nên phối hợp với các cấu hình mapper thông thường mà không cần kiểm soát toàn bộ mapper. Ví dụ, cùng module có thể được dùng với naming strategy hoặc feature khác:

~~~java
ObjectMapper snakeCaseMapper = JsonMapper.builder()
    .addModule(new MoneyJacksonModule())
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();

ObjectMapper strictMapper = JsonMapper.builder()
    .addModule(new MoneyJacksonModule())
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Serializer ghi trực tiếp tên token bằng `JsonGenerator`, nên tên `amount` và `currency` được quyết định bởi serializer. Naming strategy dành cho bean property không tự động đổi tên mà serializer ghi thủ công. Đây là điều cần tài liệu hóa trong module contract.

Đối với deserializer, việc bật strict unknown properties ở mapper không nhất thiết tự động kiểm soát field thừa bên trong custom deserializer. Nếu deserializer tự đọc `JsonNode`, chính nó phải kiểm tra tập key cho phép nếu cần strict schema.

## 9. Kiểm thử mix-in trong một module

Module không chỉ đăng ký serializer/deserializer. Nó còn có thể gắn mix-in cho class mà ứng dụng không sở hữu, ví dụ một kiểu từ thư viện bên thứ ba.

Giả sử thư viện cung cấp:

~~~java
public class VendorAddress {
    public String getStreetName() { /* ... */ }
    public String getPostalCode() { /* ... */ }
}
~~~

Ứng dụng muốn đổi tên JSON mà không sửa class thư viện. Tạo mix-in:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

abstract class VendorAddressMixin {
    @JsonProperty("street")
    abstract String getStreetName();

    @JsonProperty("postal_code")
    abstract String getPostalCode();
}
~~~

Đăng ký mix-in trong module:

~~~java
public final class VendorApiJacksonModule extends SimpleModule {
    public VendorApiJacksonModule() {
        super("VendorApiJacksonModule");
        setMixInAnnotation(
            VendorAddress.class,
            VendorAddressMixin.class
        );
    }
}
~~~

Unit test có thể tạo mapper chỉ với module này rồi kiểm tra output của `VendorAddress`. Không cần chạy ứng dụng chính hoặc gọi vendor service.

Mix-in nên được đặt cùng module sở hữu hợp đồng tích hợp. Nếu mix-in chỉ có ý nghĩa với một đối tác, không nên gắn nó vào module dùng chung cho mọi API vì có thể làm thay đổi JSON ngoài phạm vi.

## 10. Khi nào cần triển khai Module hoặc ghi đè setupModule?

Với các trường hợp thông thường, `SimpleModule` đủ dùng. Khi cần đăng ký một cơ chế nâng cao như `BeanSerializerModifier`, có thể ghi đè `setupModule()`:

~~~java
public final class AuditJacksonModule extends SimpleModule {
    public AuditJacksonModule() {
        super("AuditJacksonModule");
    }

    @Override
    public void setupModule(SetupContext context) {
        super.setupModule(context);

        context.addBeanSerializerModifier(
            new AuditBeanSerializerModifier()
        );
    }
}
~~~

Gọi `super.setupModule(context)` để các serializer, deserializer, mix-in hoặc cấu hình đã đăng ký qua API của `SimpleModule` được cài đặt. Sau đó mới thêm modifier hoặc extension khác.

Nếu triển khai trực tiếp `Module`, cần cung cấp tên, version và đăng ký các thành phần qua `SetupContext`. Cách này có thể cần thiết cho module phức tạp, nhưng tạo nhiều mã nền hơn. Chỉ chọn khi API của `SimpleModule` không đáp ứng mục tiêu.

Mọi thành phần được thêm vào `SetupContext` nên có thể được kiểm thử riêng. Ví dụ modifier có thể có unit test kiểm tra cách nó thay đổi serializer của một bean cụ thể; module test kiểm tra modifier đã được đăng ký vào mapper.

## 11. Tránh để module phụ thuộc vào ứng dụng

Một module khó kiểm thử độc lập thường chứa logic thuộc tầng ứng dụng. Ví dụ:

~~~java
public final class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule(ApplicationContext context) {
        MoneyService service = context.getBean(MoneyService.class);
        // Đăng ký serializer sử dụng service.
    }
}
~~~

Thiết kế này buộc unit test phải tạo Spring context hoặc giả lập container chỉ để kiểm tra Jackson. Nó cũng làm module khó tái sử dụng trong command-line tool, batch job hoặc ứng dụng khác.

Tương tự, tránh truy cập repository từ serializer/deserializer, gọi HTTP hoặc message broker trong quá trình serialize, đọc trực tiếp biến môi trường hoặc file cấu hình trong serializer, dùng static global mapper, lưu request/session context vào serializer dùng chung, gọi `new ObjectMapper()` bên trong serializer để xử lý object lồng nhau, hoặc thực hiện nghiệp vụ như tính giá, phân quyền hay quyết định trạng thái trong serializer.

Serializer và deserializer nên là adapter chuyển đổi giữa model Java và JSON. Logic nghiệp vụ nên được xử lý trước hoặc sau ranh giới này.

Nếu serializer thực sự cần một tham số cấu hình, hãy truyền giá trị đó qua constructor của module hoặc serializer:

~~~java
public final class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule(int scale) {
        super("MoneyJacksonModule");
        addSerializer(Money.class, new MoneySerializer(scale));
    }
}
~~~

Tham số nên được xác thực và lưu bất biến. Module có thể được kiểm thử với nhiều cấu hình bằng cách tạo module/mapper riêng cho từng test.

## 12. Tránh thay đổi ObjectMapper toàn cục từ module

Module nên đăng ký các thành phần thuộc phạm vi của nó. Không nên dùng module như một cách âm thầm thay đổi mọi feature của ứng dụng mà không tài liệu hóa.

Nếu module cần bật một feature để serializer hoạt động, hãy cân nhắc feature đó có thật sự là điều kiện của serializer không, có thể xử lý cục bộ trong serializer/deserializer không, feature có ảnh hưởng đến các kiểu khác không, và việc bật feature có phải một phần công khai của module contract không.

Các cấu hình ảnh hưởng rộng như timezone mặc định, unknown property handling, default typing hoặc visibility nên thường được quản lý tại composition root của ứng dụng. Nếu module yêu cầu một cấu hình toàn cục, hãy công bố rõ và có test chứng minh tác động.

Không sửa mapper sau khi mapper đã được dùng bởi nhiều thread. Cấu hình mapper/module cần hoàn tất trước khi ứng dụng bắt đầu xử lý request.

## 13. Module có thể được đóng gói thành thư viện riêng

Khi module có thể tái sử dụng, có thể đặt nó trong một Gradle/Maven module riêng, ví dụ:

~~~text
money-jackson/
  src/
    main/
      java/
        com/example/money/
          MoneyJacksonModule.java
          MoneySerializer.java
          MoneyDeserializer.java
    test/
      java/
        com/example/money/
          MoneyJacksonModuleTest.java
~~~

Thư viện nên khai báo dependency Jackson phù hợp và tránh kéo theo framework không cần thiết. Nếu module chỉ dùng Jackson Databind, không cần thêm Spring Boot chỉ để đăng ký serializer.

Ứng dụng sử dụng thư viện:

~~~gradle
dependencies {
    implementation("com.example:money-jackson:1.0.0")
}
~~~

Sau đó đăng ký module tại cấu hình mapper:

~~~java
@Bean
ObjectMapper objectMapper() {
    return JsonMapper.builder()
        .addModule(new MoneyJacksonModule())
        .build();
}
~~~

Trong ứng dụng Spring Boot, nên tích hợp module với mapper do Boot quản lý bằng bean `Module` hoặc cơ chế customizer tương ứng. Không thay mapper mặc định nếu chỉ cần bổ sung module và framework đã cấu hình các module khác.

### 13.1. Quản lý phiên bản Jackson

Jackson gồm các artifact như `jackson-core`, `jackson-annotations` và `jackson-databind`. Module nên dùng phiên bản tương thích với ứng dụng tiêu thụ nó. Tránh đóng gói một bộ Jackson khác biệt hoặc ép ứng dụng nâng/hạ version không cần thiết.

Các lưu ý:

- Dùng dependency management/BOM của dự án để giữ các artifact Jackson tương thích.
- Không khai báo nhiều phiên bản `jackson-databind` xung đột trong cùng runtime.
- Kiểm tra API đang dùng có tồn tại trong phiên bản tối thiểu mà thư viện hỗ trợ không.
- Nếu module phát hành công khai, công bố dải phiên bản Jackson được hỗ trợ.
- Kiểm thử với các phiên bản mục tiêu nếu thư viện cần hỗ trợ nhiều dòng Jackson.
- Không giả định mã biên dịch với Jackson 2.x sẽ không cần điều chỉnh khi chuyển sang Jackson 3.x.

## 14. Đăng ký module tường minh và tự động

Cách dễ kiểm soát nhất là đăng ký module rõ ràng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new MoneyJacksonModule())
    .build();
~~~

Jackson cũng có cơ chế tìm module qua `findAndRegisterModules()` trong những ứng dụng đóng gói module theo cơ chế service discovery. Cơ chế tự động giúp giảm cấu hình thủ công nhưng làm các module được phát hiện phụ thuộc vào classpath và metadata service loader.

Với module nghiệp vụ quan trọng, đăng ký tường minh thường giúp người đọc hiểu mapper đang dùng những quy tắc nào. Nếu dùng auto-discovery, cần kiểm tra artifact đã khai báo provider đúng cách và có test xác nhận module thực sự được phát hiện.

Không nên vừa đăng ký thủ công vừa tự động phát hiện cùng một module nếu chưa hiểu hành vi trùng lặp của phiên bản đang dùng. Chọn một chính sách đăng ký và ghi rõ trong cấu hình ứng dụng.

## 15. Kiểm thử module theo nhiều cấp

Một module độc lập có thể được kiểm thử theo các cấp sau:

| Cấp test | Mục tiêu | Có cần khởi động ứng dụng? |
|---|---|---|
| Unit test serializer | Token và cấu trúc JSON do serializer ghi | Không |
| Unit test deserializer | Kiểu đầu vào, validation và lỗi mapping | Không |
| Module registration test | Mapper thực sự sử dụng handler của module | Không |
| Mix-in test | Annotation từ mix-in có hiệu lực | Không |
| Compatibility test | Module hoạt động với cấu hình Jackson mục tiêu | Không cần Spring |
| Integration test | Spring Boot đăng ký module vào HTTP converter | Có thể cần context MVC |
| Contract test | Response/request thực tế phù hợp schema API | Thường cần tầng ứng dụng hoặc test slice |

Không cần dùng integration test để kiểm tra mọi trường hợp của serializer. Unit test module nên bao phủ phần lớn logic chuyển đổi. Integration test chỉ xác nhận ranh giới tích hợp: framework đã đăng ký module và endpoint sử dụng đúng mapper.

## 16. Kiểm thử rằng module không làm thay đổi kiểu ngoài phạm vi

Module tốt chỉ tác động đến các kiểu mà nó sở hữu hoặc được thiết kế để mở rộng. Nên có test xác nhận kiểu Java thông thường vẫn serialize theo mặc định:

~~~java
@Test
void doesNotChangeUnrelatedTypes() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .addModule(new MoneyJacksonModule())
        .build();

    String json = mapper.writeValueAsString(
        new SimpleMessage("hello")
    );

    assertEquals("{\"value\":\"hello\"}", json);
}

public record SimpleMessage(String value) {
}
~~~

Test này giúp phát hiện module vô tình cài modifier hoặc cấu hình rộng làm thay đổi bean không liên quan.

Nếu module có `BeanSerializerModifier`, mix-in toàn cục hoặc default typing, phạm vi ảnh hưởng có thể rộng hơn serializer cho một class. Khi đó, cần test cả kiểu nằm trong và ngoài phạm vi.

## 17. Kiểm thử đăng ký trùng và thứ tự module

Một ứng dụng có thể đăng ký nhiều module. Nếu hai module cùng đăng ký serializer cho một kiểu, kết quả phụ thuộc quy tắc đăng ký và thứ tự xử lý của Jackson. Không nên để hai module cùng sở hữu một kiểu mà không có quy ước.

Ví dụ cấu hình dễ gây nhầm:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new LegacyMoneyModule())
    .addModule(new MoneyJacksonModule())
    .build();
~~~

Nếu cả hai module đều đăng ký serializer cho `Money`, người đọc khó biết hợp đồng nào có hiệu lực. Hãy có một module duy nhất sở hữu serializer cho kiểu đó, hoặc tạo mapper riêng cho hai hợp đồng khác nhau.

Test cấu hình hoàn chỉnh có thể xác nhận output của mapper sau khi tất cả module được đăng ký. Nhưng unit test của từng module vẫn nên chạy độc lập để lỗi được định vị nhanh.

## 18. Thiết kế cấu hình module bằng constructor

Nếu module cần tùy chọn, hãy mô hình hóa chúng thành một cấu hình nhỏ, bất biến và kiểm tra ngay khi tạo:

~~~java
public record MoneyJsonSettings(boolean amountAsString) {
}
~~~

Module nhận cấu hình:

~~~java
public final class ConfigurableMoneyModule extends SimpleModule {
    public ConfigurableMoneyModule(MoneyJsonSettings settings) {
        super("ConfigurableMoneyModule");

        if (settings.amountAsString()) {
            addSerializer(Money.class, new MoneyStringSerializer());
        } else {
            addSerializer(Money.class, new MoneyNumberSerializer());
        }
    }
}
~~~

Trong ứng dụng, cấu hình được tạo từ application properties rồi truyền vào module. Trong unit test, test có thể tạo trực tiếp settings mà không cần Spring configuration binding.

Nếu tùy chọn làm thay đổi kiểu token hoặc cấu trúc JSON, nó là một phần của API contract. Không nên để giá trị mặc định phụ thuộc vào môi trường máy chạy mà không được tài liệu hóa.

## 19. Những lỗi thường gặp

### Tạo ObjectMapper bên trong module

Module không nên tự tạo mapper để xử lý dữ liệu. Mapper do ứng dụng sở hữu và module chỉ đăng ký thành phần mở rộng. Nếu module tạo mapper riêng, nó có thể bỏ qua cấu hình chung và tạo hai chính sách JSON khác nhau.

### Phụ thuộc vào Spring context

Serializer lấy service từ application context làm unit test trở nên nặng và khiến thư viện không thể dùng ngoài Spring. Hãy đưa logic nghiệp vụ ra khỏi serializer hoặc truyền một cấu hình bất biến.

### Đăng ký module nhưng test không dùng module

Test chỉ gọi serializer trực tiếp không chứng minh mapper thực tế đã đăng ký đúng. Hãy tạo mapper qua builder và gọi `writeValueAsString()`/`readValue()` để kiểm tra registration.

### Module có quá nhiều trách nhiệm

Một module trộn tiền tệ, ngày giờ, security, entity và mọi API đối tác sẽ khó tái sử dụng. Tách theo hợp đồng hoặc nhóm kiểu có liên quan.

### Không kiểm tra phiên bản Jackson

API của Jackson có thể thay đổi giữa các dòng major. Khai báo dependency và API hỗ trợ cần phù hợp với phiên bản ứng dụng.

### Hai module cùng đăng ký một kiểu

Khi có nhiều serializer cho cùng kiểu, kết quả phụ thuộc registration/configuration. Xác định một nơi sở hữu hoặc tách mapper theo hợp đồng.

### Dùng module để thay đổi chính sách toàn cục bất ngờ

Các feature như default typing, visibility hoặc unknown property handling có thể ảnh hưởng toàn bộ ứng dụng. Công bố rõ tác động và kiểm thử các kiểu không liên quan.

### Dùng module test thay cho integration test

Unit test module chứng minh logic Jackson; nó không chứng minh Spring MVC đang dùng đúng mapper. Cần một test tích hợp nhỏ ở ranh giới framework nếu ứng dụng có yêu cầu đó.

## 20. Quy trình thiết kế và kiểm thử module độc lập

1. Xác định kiểu nghiệp vụ hoặc kiểu bên thứ ba mà module cần hỗ trợ.
2. Viết JSON contract trước: tên field, kiểu token, null, format và dữ liệu không hợp lệ.
3. Triển khai serializer/deserializer hoặc mix-in thành các class nhỏ, không phụ thuộc application service.
4. Tạo một lớp `SimpleModule` để đăng ký các thành phần đó.
5. Nếu cần tùy chọn, truyền cấu hình bất biến qua constructor.
6. Tạo `ObjectMapper` tối giản trong unit test và đăng ký duy nhất module cần kiểm tra.
7. Test serialize, deserialize, round-trip, lỗi đầu vào và các giá trị biên.
8. Test kiểu không liên quan để xác nhận phạm vi ảnh hưởng.
9. Kiểm tra module với phiên bản Jackson được hỗ trợ và tránh dependency conflict.
10. Đăng ký module tại composition root hoặc qua cơ chế tích hợp framework.
11. Bổ sung integration/contract test ở ứng dụng để xác nhận mapper thực tế đã nhận module.
12. Tài liệu hóa thứ tự đăng ký, cấu hình toàn cục và các thay đổi JSON có thể ảnh hưởng consumer.

## 21. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Đóng gói serializer/deserializer | Kế thừa `SimpleModule` |
| Đăng ký serializer | `addSerializer(Type.class, serializer)` |
| Đăng ký deserializer | `addDeserializer(Type.class, deserializer)` |
| Áp dụng annotation cho class bên thứ ba | `setMixInAnnotation(Target.class, Mixin.class)` |
| Cấu hình module cho mapper test | `JsonMapper.builder().addModule(...).build()` |
| Cần extension Databind nâng cao | Ghi đè `setupModule()` và gọi `super.setupModule(context)` |
| Module cần tùy chọn | Constructor nhận cấu hình bất biến |
| Tích hợp Spring Boot | Đăng ký bean `Module` hoặc customizer phù hợp |
| Tránh phụ thuộc ứng dụng | Không gọi Spring context, repository hoặc HTTP từ serializer |
| Kiểm thử độc lập | Unit test với mapper tối giản, không khởi động application context |
| Kiểm thử framework | Integration test riêng cho mapper/converter thực tế |
| Tránh xung đột | Một module sở hữu rõ serializer của từng kiểu |

## 22. Kết luận

Một Jackson Module có thể kiểm thử độc lập khi nó đóng gói một hợp đồng JSON có ranh giới rõ ràng và không phụ thuộc vào vòng đời của ứng dụng. `SimpleModule` thường đủ để đăng ký serializer, deserializer và mix-in. Các handler nên là thành phần nhỏ, không trạng thái, chỉ chuyển đổi dữ liệu và nhận cấu hình cần thiết qua constructor.

Hãy tạo `ObjectMapper` tối giản trong unit test, đăng ký module rồi kiểm tra serialize, deserialize, round-trip, dữ liệu lỗi và những kiểu không liên quan. Việc này xác nhận module hoạt động mà không cần khởi động Spring hoặc kết nối hạ tầng. Sau đó, ứng dụng chỉ cần đăng ký module tại composition root; một integration test nhỏ có thể xác nhận framework đang sử dụng đúng mapper. Tách rõ unit test của module và test tích hợp của ứng dụng giúp lỗi dễ định vị, module dễ tái sử dụng và hợp đồng JSON được kiểm soát tốt hơn.
