# Nhận diện lỗi thiếu creator và định nghĩa kiểu không phù hợp

Jackson cần một cách tạo instance khi deserialize. Class mutable có thể dùng constructor không tham số và setter; class immutable thường cần constructor hoặc factory method được khai báo làm creator. Nếu Jackson không tìm được creator phù hợp, lỗi thường là InvalidDefinitionException. Lỗi này khác với MismatchedInputException, xảy ra khi kiểu đích có thể deserialize nhưng JSON token không khớp shape mong đợi.

## 1. Nhận diện nhóm lỗi

| Exception | Ý nghĩa |
|---|---|
| InvalidDefinitionException | Định nghĩa kiểu đích không cung cấp creator/deserializer hợp lệ |
| MismatchedInputException | JSON shape hoặc token không phù hợp kiểu đích |
| ValueInstantiationException | Creator đã được gọi nhưng constructor/factory ném lỗi |
| InvalidTypeIdException | Type discriminator không xác định được subtype |
| JsonParseException | JSON sai cú pháp |

Ví dụ class immutable không có creator metadata:

```java
public final class User {
    private final long id;
    private final String name;

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

Với JSON object đúng cú pháp, Jackson vẫn có thể báo lỗi vì không biết tham số constructor nào ứng với property nào.

## 2. Khai báo constructor bằng JsonCreator

Với class immutable, hãy chỉ rõ constructor được dùng và ánh xạ tên tham số sang tên property JSON bằng JsonProperty:

```java
public final class Account {
    private final String accountNumber;
    private final BigDecimal balance;

    @JsonCreator
    public Account(
            @JsonProperty("accountNumber") String accountNumber,
            @JsonProperty("balance") BigDecimal balance
    ) {
        this.accountNumber = accountNumber;
        this.balance = balance;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}
```

JSON:

```json
{
  "accountNumber": "AC-001",
  "balance": 1250.75
}
```

JsonCreator đánh dấu constructor hoặc static factory method làm creator. JsonProperty cho Jackson biết tham số nào nhận giá trị của property nào. Cách khai báo tường minh này không phụ thuộc vào tên tham số được giữ trong bytecode.

### 2.1. Tên tham số Java không phải lúc nào cũng có sẵn

Đoạn code sau có thể không đủ metadata trên mọi cấu hình:

```java
@JsonCreator
public Account(String accountNumber, BigDecimal balance) {
    this.accountNumber = accountNumber;
    this.balance = balance;
}
```

Tên tham số trong source code không nhất thiết được lưu trong bytecode. Nếu Jackson không khám phá được tên, lỗi có thể nói rằng creator argument không có property name.

Cách rõ ràng nhất là gắn JsonProperty cho từng tham số. Một lựa chọn khác là biên dịch với tùy chọn -parameters và đăng ký ParameterNamesModule.

Maven:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Đăng ký module:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new ParameterNamesModule())
        .build();
```

Module jackson-module-parameter-names phải cùng version line với Jackson Databind. Với contract public, JsonProperty tường minh thường dễ review và ổn định hơn vì tên tham số Java có thể đổi khi refactor.

## 3. Chọn đúng mode của JsonCreator

JsonCreator có thuộc tính mode để chỉ cách Jackson diễn giải các tham số.

### 3.1. PROPERTIES: mỗi tham số nhận một property

Dùng JsonCreator.Mode.PROPERTIES khi JSON là object và mỗi tham số tương ứng với một field:

```java
public final class Coordinate {
    private final double latitude;
    private final double longitude;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Coordinate(
            @JsonProperty("latitude") double latitude,
            @JsonProperty("longitude") double longitude
    ) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}
```

JSON:

```json
{
  "latitude": 10.8231,
  "longitude": 106.6297
}
```

### 3.2. DELEGATING: toàn bộ root value được truyền vào một tham số

Dùng DELEGATING khi class được tạo từ một giá trị đơn hoặc một cấu trúc tổng thể:

```java
public final class UserId {
    private final long value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public UserId(long value) {
        this.value = value;
    }

    public long value() {
        return value;
    }
}
```

JSON là một number root:

```json
101
```

Jackson truyền toàn bộ root number vào constructor. Nó không tìm property có tên value trong object.

### 3.3. DEFAULT và DISABLED

JsonCreator.Mode.DEFAULT để Jackson áp dụng quy tắc nhận diện creator dựa trên metadata và chữ ký. Với constructor một tham số, nếu input shape có thể gây mơ hồ, nên chỉ rõ mode.

JsonCreator.Mode.DISABLED loại một constructor/factory khỏi việc được chọn làm creator trong các tình huống introspection phù hợp. Đây là trường hợp đặc thù, ít dùng trong DTO thông thường.

| Mode | Cách truyền dữ liệu | JSON điển hình |
|---|---|---|
| PROPERTIES | Mỗi tham số nhận một property | {"id":101,"name":"An"} |
| DELEGATING | Toàn bộ root value cho một tham số | 101 hoặc "AC-001" |
| DEFAULT | Jackson tự quyết định theo metadata | Phụ thuộc chữ ký creator |
| DISABLED | Không dùng creator đó | Không có input shape riêng |

### 3.4. Constructor một tham số dễ bị nhầm

Nếu muốn JSON string:

```json
"an@example.test"
```

hãy khai báo:

```java
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public EmailAddress(String value) {
    this.value = value;
}
```

Nếu muốn JSON object:

```json
{"value":"an@example.test"}
```

hãy khai báo:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public EmailAddress(@JsonProperty("value") String value) {
    this.value = value;
}
```

Trước khi sửa constructor, hãy xác định contract muốn root string hay object. Đừng chỉ đổi tên tham số để thử vận may.

## 4. Static factory method cũng là creator

Jackson cho phép dùng static factory method thay constructor. Cách này hữu ích khi object cần validation hoặc constructor được giữ private:

```java
public final class CurrencyCode {
    private final String value;

    private CurrencyCode(String value) {
        this.value = value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static CurrencyCode fromJson(String value) {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency code must have 3 uppercase letters"
            );
        }
        return new CurrencyCode(value);
    }

    public String value() {
        return value;
    }
}
```

JSON:

```json
"USD"
```

Nếu factory được tìm thấy nhưng ném exception, Jackson thường bọc lỗi trong ValueInstantiationException hoặc JsonMappingException phù hợp. Đó là dấu hiệu creator đã chạy; nguyên nhân nằm trong validation hoặc logic khởi tạo, không phải thiếu creator.

## 5. Constructor không tham số và setter

Với class mutable, Jackson có thể tạo object rỗng rồi gán property:

```java
public class Product {
    private long id;
    private String name;
    private BigDecimal price;

    public Product() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

Đây là cách đơn giản khi class được thiết kế mutable. Không bắt buộc mọi model phải có constructor rỗng. Với domain object immutable, property creator thường tốt hơn vì invariant được thiết lập ngay lúc tạo object.

Constructor private hoặc package-private có thể phụ thuộc visibility/access override configuration và giới hạn module của JVM. Với DTO thông thường, hãy ưu tiên creator/constructor có visibility phù hợp thay vì dựa vào việc mapper có thể truy cập private member.

## 6. Java record và creator

Jackson hỗ trợ Java record từ Jackson 2.12. Trong trường hợp thông thường, Jackson sử dụng canonical constructor và component metadata:

```java
public record UserRecord(
        long id,
        String name,
        boolean active
) {
}
```

JSON:

```json
{
  "id": 101,
  "name": "An",
  "active": true
}
```

Deserialize:

```java
UserRecord user = mapper.readValue(json, UserRecord.class);
```

Nếu tên JSON khác tên component, có thể khai báo JsonProperty:

```java
public record UserRecord(
        @JsonProperty("user_id") long id,
        @JsonProperty("display_name") String name,
        boolean active
) {
}
```

Nếu project dùng Jackson cũ hơn 2.12, record support có thể chưa có hoặc chưa đầy đủ. Kiểm tra version Databind thực tế; việc JDK hỗ trợ record không tự động có nghĩa phiên bản Jackson cũ hiểu record.

## 7. Builder pattern cho class immutable

Nếu class chỉ được tạo qua builder, khai báo builder cho Jackson bằng JsonDeserialize(builder = ...):

```java
@JsonDeserialize(builder = ServerConfig.Builder.class)
public final class ServerConfig {
    private final String host;
    private final int port;

    private ServerConfig(Builder builder) {
        this.host = builder.host;
        this.port = builder.port;
    }

    public String getHost() {
        return host;
    }

    public int getPort() {
        return port;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private String host;
        private int port;

        public Builder host(String host) {
            this.host = host;
            return this;
        }

        public Builder port(int port) {
            this.port = port;
            return this;
        }

        public ServerConfig build() {
            return new ServerConfig(this);
        }
    }
}
```

JsonPOJOBuilder(withPrefix = "") báo rằng method host(...) và port(...) là mutator cho property tương ứng. Nếu builder dùng prefix with, có thể khai báo JsonPOJOBuilder(withPrefix = "with").

Với Lombok, @Jacksonized có thể kết hợp với @Builder ở các version hỗ trợ. Hãy kiểm tra generated builder và annotation thực tế; không giả định mọi builder tự động được Jackson nhận diện.

## 8. Non-static inner class không thể tạo độc lập

Non-static inner class giữ tham chiếu ngầm đến instance outer class:

```java
public class Container {
    public class Item {
        private String name;
    }
}
```

Để tạo Container.Item, Java cần một Container:

```java
Container container = new Container();
Container.Item item = container.new Item();
```

Nếu yêu cầu Jackson deserialize Container.Item.class độc lập, nó không có outer instance để truyền vào constructor. Hãy chuyển thành nested class static hoặc DTO top-level:

```java
public class Container {
    public static class Item {
        private String name;

        public Item() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }
}
```

## 9. Abstract class và interface cần subtype mapping

Nếu kiểu đích là interface hoặc abstract class, Jackson không thể khởi tạo trực tiếp:

```java
public interface Payment {
    BigDecimal amount();
}
```

Nếu JSON được đọc thành Payment.class mà không có implementation mapping, Jackson có thể báo lỗi về abstract type hoặc không tìm thấy concrete class. Cần một trong các cách:

- JsonTypeInfo và danh sách subtype được phép.
- SimpleAbstractTypeResolver nếu luôn ánh xạ đến một implementation.
- Custom deserializer nếu quy tắc chọn class đặc thù.
- Deserialize vào concrete class nếu contract chỉ có một kiểu.

Ví dụ polymorphic mapping:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
public interface Payment {
}
```

JSON:

```json
{
  "type": "card",
  "cardNumber": "****1234",
  "amount": 1250.75
}
```

Đây là vấn đề chọn subtype, không phải thiếu no-args constructor ở interface. Không thêm constructor vào abstract/interface để giải quyết lỗi này.

## 10. Missing property, explicit null và creator validation

Có creator hợp lệ không đồng nghĩa mọi JSON đều tạo được object. Cũng không có nghĩa field bị thiếu luôn bị từ chối.

```java
public record CreateUserRequest(
        String username,
        Integer age
) {
}
```

Với input:

```json
{"username":"an"}
```

Jackson có thể truyền null cho wrapper Integer, tùy cấu hình. Nếu cần bắt buộc creator property, có thể bật:

```java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

- FAIL_ON_MISSING_CREATOR_PROPERTIES từ chối creator property bị thiếu.
- FAIL_ON_NULL_CREATOR_PROPERTIES từ chối creator property nhận null.
- FAIL_ON_NULL_FOR_PRIMITIVES từ chối JSON null cho primitive thay vì nhận giá trị mặc định.

JsonProperty(required = true) có thể biểu đạt yêu cầu bắt buộc, đặc biệt với creator property; hành vi phụ thuộc loại property và version. Hãy test cả missing và explicit null.

Các feature trên không thay thế validation nghiệp vụ. Ví dụ age = -2 có thể deserialize thành công nhưng vẫn không hợp lệ; cần Bean Validation hoặc kiểm tra domain.

## 11. Creator nhiều tham số nhưng thiếu tên property

Ví dụ:

```java
public final class Customer {
    private final long id;
    private final String name;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

Với property-based creator, Jackson phải biết tham số nào ứng với property nào. Nếu không có JsonProperty, parameter metadata hoặc cơ chế khám phá tên phù hợp, lỗi có thể nhắc rằng creator argument không có property name.

Sửa bằng cách khai báo rõ:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(
        @JsonProperty("id") long id,
        @JsonProperty("name") String name
) {
    this.id = id;
    this.name = name;
}
```

## 12. Nhiều creator có thể gây mơ hồ

Một class có thể có nhiều constructor và factory method. Nếu nhiều creator cùng được đánh dấu hoặc metadata không nhất quán, Jackson có thể không biết chọn cách tạo object nào.

Không nên khai báo nhiều creator cho cùng một input shape mà không có phân biệt rõ:

```java
public class Identifier {
    private final String value;

    @JsonCreator
    public Identifier(String value) {
        this.value = value;
    }

    @JsonCreator
    public static Identifier fromNumber(long value) {
        return new Identifier(Long.toString(value));
    }
}
```

Hãy chọn một creator JSON tường minh; các constructor/factory khác có thể giữ cho code Java nội bộ nhưng không cần đánh dấu làm JSON creator. Nếu cần nhiều input shape, dùng custom deserializer hoặc contract discriminator rõ ràng.

## 13. Khi creator chạy nhưng constructor thất bại

Ví dụ:

```java
public final class Age {
    private final int value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public Age(int value) {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException("Age is out of range");
        }
        this.value = value;
    }
}
```

Input:

```json
-5
```

Jackson đã tìm được creator và gọi constructor, nhưng constructor từ chối giá trị. Lỗi thường được bọc trong ValueInstantiationException, có cause là IllegalArgumentException.

Phân biệt:

- InvalidDefinitionException: Jackson không có cách hợp lệ để xây dựng kiểu hoặc serializer.
- MismatchedInputException: token/shape/giá trị đầu vào không phù hợp kiểu mong đợi.
- ValueInstantiationException: creator đã chạy nhưng không thể tạo instance thành công.

Exception wrapper cụ thể có thể khác theo version và đường deserialize. Hãy xem cause chain thay vì chỉ nhìn dòng exception cuối cùng.

## 14. Khi nào cần custom deserializer?

Không nên viết custom deserializer chỉ để che lỗi creator nếu JsonCreator đã mô tả được mapping. Custom deserializer phù hợp khi input format thực sự đặc thù, ví dụ:

- Một giá trị có thể là string hoặc object theo contract.
- Cần đọc nhiều field kết hợp để tạo domain value.
- Cần hỗ trợ một format legacy phức tạp.
- Cấu trúc đầu vào không thể mô tả bằng creator thông thường.
- Cần kiểm soát token và thông báo lỗi riêng.

Ví dụ custom deserializer cho UserId nhận string:

```java
public final class UserIdDeserializer extends StdDeserializer<UserId> {
    public UserIdDeserializer() {
        super(UserId.class);
    }

    @Override
    public UserId deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            return (UserId) context.handleUnexpectedToken(
                    UserId.class,
                    parser
            );
        }

        String raw = parser.getText();
        try {
            return new UserId(Long.parseLong(raw));
        } catch (NumberFormatException exception) {
            throw JsonMappingException.from(
                    parser,
                    "UserId must contain a numeric value",
                    exception
            );
        }
    }
}
```

Đăng ký:

```java
SimpleModule module = new SimpleModule("user-id-module");
module.addDeserializer(UserId.class, new UserIdDeserializer());

ObjectMapper mapper = new ObjectMapper()
        .registerModule(module);
```

Custom deserializer tự chịu trách nhiệm kiểm tra token, parse và tạo object. Hãy dùng khi format cần logic riêng, không dùng thay cho creator metadata bị thiếu một cách đơn giản.

## 15. Đọc stack trace và reference chain

Jackson thường bổ sung đường dẫn property vào exception, ví dụ:

```text
through reference chain:
OrderRequest["payment"]->CardPayment["amount"]
```

Đường dẫn giúp xác định lỗi ở root hay property lồng nhau.

Khi debug, đọc theo thứ tự:

1. Exception class đầu tiên có ý nghĩa: InvalidDefinitionException, MismatchedInputException, ValueInstantiationException hay JsonParseException.
2. Thông báo chính: thiếu creator, abstract type, unexpected token, unknown property hay creator throw.
3. Kiểu Java đích đang deserialize.
4. Reference chain/property path.
5. Cause chain nếu constructor/factory ném exception.
6. JSON fragment tương ứng với property lỗi.
7. Mapper, module, mix-in và feature thực tế đang được sử dụng.

Có thể log path:

```java
try {
    User user = mapper.readValue(json, User.class);
} catch (JsonMappingException exception) {
    log.error("JSON mapping failed at {}", exception.getPathReference(), exception);
    throw exception;
}
```

Không nên log toàn bộ payload nếu chứa mật khẩu, token, thông tin cá nhân hoặc dữ liệu thanh toán. Trong production, ghi loại lỗi, target type, path và correlation ID thường hữu ích hơn ghi nguyên JSON nhạy cảm.

## 16. Ma trận chẩn đoán nhanh

| Thông báo hoặc dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| no Creators, like default constructor, exist | Không có no-args constructor hoặc creator được nhận diện | Thêm no-args + setter, hoặc JsonCreator/builder |
| has no property name | Creator nhiều tham số thiếu metadata tên property | JsonProperty hoặc parameter names module + -parameters |
| Cannot construct instance of abstract type | Target là interface/abstract class | Type ID/subtype mapping hoặc concrete target |
| cannot deserialize from Object value | Creator không hỗ trợ object input hoặc không tìm được property creator | Kiểm tra PROPERTIES mode và tham số |
| cannot deserialize from String value | Target mong object nhưng input là string | Kiểm tra JSON shape hoặc dùng delegating creator nếu contract là string |
| cannot deserialize from Array value | Input array nhưng target mong object | Sửa contract hoặc chọn target/format phù hợp |
| ValueInstantiationException | Constructor/factory ném exception | Kiểm tra validation và cause |
| InvalidTypeIdException | Type discriminator thiếu hoặc lạ | Đăng ký subtype, kiểm tra type ID |
| UnrecognizedPropertyException | JSON có field không được class nhận | Sửa tên field hoặc cấu hình unknown property có chủ đích |
| MismatchedInputException | Token/value không khớp target | Kiểm tra shape, scalar type và coercion |
| Lỗi chỉ xảy ra ở runtime khác | Mapper/module/compiler flags khác nhau | Kiểm tra dependency và cấu hình thực tế |

## 17. Test creator độc lập

Với class immutable, test creator đọc được JSON đúng contract:

```java
class AccountCreatorTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void createsAccountFromProperties() throws Exception {
        String json = """
                {
                  "accountNumber": "AC-001",
                  "balance": 1250.75
                }
                """;

        Account account = mapper.readValue(json, Account.class);

        assertEquals("AC-001", account.getAccountNumber());
        assertEquals(
                0,
                new BigDecimal("1250.75").compareTo(account.getBalance())
        );
    }
}
```

Với delegating creator, kiểm tra root scalar:

```java
@Test
void createsUserIdFromNumber() throws Exception {
    UserId id = mapper.readValue("101", UserId.class);

    assertEquals(101L, id.value());
}
```

Với builder, record hoặc abstract type, test đúng hình dạng JSON và kiểu đích tương ứng. Dùng cùng module, naming strategy, coercion và deserialization features như mapper production.

## 18. Test các trường hợp lỗi có chủ đích

Không chỉ test payload hợp lệ. Cần xác nhận hành vi khi creator property bị thiếu hoặc input sai shape.

Ví dụ từ chối property creator bị thiếu:

```java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .build();

String json = """
        {
          "accountNumber": "AC-001"
        }
        """;

assertThrows(
        JsonMappingException.class,
        () -> strictMapper.readValue(json, Account.class)
);
```

Ví dụ JSON sai shape:

```java
String jsonArray = """
        [
          "AC-001",
          1250.75
        ]
        """;

assertThrows(
        MismatchedInputException.class,
        () -> mapper.readValue(jsonArray, Account.class)
);
```

Exception cụ thể phụ thuộc kiểu đích, creator và cấu hình. Hãy kiểm tra đúng nguyên nhân cần khóa trong test, tránh assertion quá rộng chỉ vì có một exception bất kỳ.

## 19. Những cách sửa sai nên tránh

### 19.1. Thêm constructor rỗng vào mọi class

Constructor rỗng có thể giúp Jackson tạo object mutable, nhưng không phù hợp nếu class cần invariant hoặc field final. Đừng làm mất tính bất biến chỉ để né lỗi. Dùng property creator hoặc builder nếu đó là thiết kế của model.

### 19.2. Bật visibility quá rộng

Có thể cấu hình Jackson truy cập private field/constructor, nhưng tăng visibility không tự cung cấp tên tham số creator và không giải quyết mọi kiểu immutable. Hãy khai báo creator rõ ràng thay vì mở toàn bộ private member cho mọi class.

### 19.3. Tắt mọi lỗi unknown property

FAIL_ON_UNKNOWN_PROPERTIES chỉ điều khiển field không được nhận diện; nó không tạo creator cho class. Tắt feature này có thể làm payload có field sai bị bỏ qua âm thầm mà lỗi khởi tạo vẫn còn.

### 19.4. Dùng default typing để chữa lỗi abstract type

Default typing không phải giải pháp chung cho thiếu creator. Với input không tin cậy, polymorphic configuration quá rộng có thể tạo rủi ro bảo mật. Hãy dùng subtype allowlist và logical type ID khi thực sự cần đa hình.

### 19.5. Bắt exception rồi tạo object rỗng

Cách này che lỗi contract và có thể đưa object thiếu dữ liệu vào nghiệp vụ. Hãy trả lỗi input rõ ràng hoặc dùng fallback được định nghĩa rõ trong contract.

## 20. Quy trình xử lý lỗi creator

Khi gặp lỗi deserialize class không có creator phù hợp:

1. Xác định exception đầu tiên có ý nghĩa và kiểu đích.
2. Kiểm tra JSON root/field có đúng shape mà class mong đợi không.
3. Kiểm tra class có no-args constructor và setter/field access hợp lệ hay không.
4. Nếu class immutable, xác định constructor/factory cần dùng.
5. Với constructor nhiều tham số, khai báo JsonCreator(mode = PROPERTIES) và JsonProperty cho từng tham số.
6. Với một tham số đại diện toàn root value, dùng DELEGATING; nếu là một property trong object, dùng PROPERTIES.
7. Nếu dùng record, kiểm tra Jackson version hỗ trợ record.
8. Nếu dùng builder, khai báo JsonDeserialize(builder = ...) và cấu hình JsonPOJOBuilder.
9. Nếu target là abstract/interface, cấu hình subtype hoặc ánh xạ implementation.
10. Kiểm tra parameter metadata, module và mapper thực tế.
11. Nếu creator được gọi rồi lỗi, đọc cause để tìm validation/constructor failure.
12. Viết test cho input hợp lệ, missing/null, sai shape và subtype nếu có.

## 21. Ghi nhớ

Lỗi thiếu creator thường là lỗi định nghĩa kiểu đích: Jackson chưa biết cách tạo instance. Với class mutable, có thể dùng constructor không tham số và setter. Với class immutable, dùng constructor/factory có JsonCreator và JsonProperty; chọn PROPERTIES cho object có nhiều field và DELEGATING khi toàn bộ root value được truyền vào một tham số. Record được hỗ trợ từ Jackson 2.12; builder cần cấu hình riêng; abstract/interface cần subtype mapping.

Phân biệt InvalidDefinitionException với MismatchedInputException và ValueInstantiationException để sửa đúng nguyên nhân. Kiểm tra JSON shape, creator metadata, parameter names, version/module, reference chain và cause. Không thêm constructor rỗng, tắt validation hoặc bật default typing một cách máy móc. Test bằng đúng mapper production và kiểm tra cả payload hợp lệ lẫn các trường hợp thiếu/null/sai kiểu.
