# Khởi tạo đối tượng bất biến qua @JsonCreator

Một lớp Java bất biến (immutable) thường có các field `final`, không cung cấp setter và chỉ thiết lập trạng thái khi tạo object. Cách thiết kế này giúp object không bị thay đổi tùy ý sau khi khởi tạo, nhưng cũng đặt ra câu hỏi khi đọc JSON: Jackson sẽ gán dữ liệu vào đâu nếu lớp không có setter?

Jackson giải quyết bài toán này bằng annotation `@JsonCreator`. Annotation đánh dấu constructor hoặc static factory method mà Jackson sẽ gọi để tạo đối tượng. Kết hợp với `@JsonProperty`, ta có thể ánh xạ từng key JSON vào tham số tương ứng và khởi tạo object bất biến chỉ trong một bước.

## 1. Vì sao lớp bất biến cần creator?

Với một JavaBean mutable, Jackson thường có thể tạo object rỗng rồi gán các thuộc tính:

```java
public class User {
    private long id;
    private String name;

    public User() {
    }

    public void setId(long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Cách này yêu cầu object có thể tồn tại ở trạng thái chưa hoàn chỉnh. Trong khi đó, một lớp bất biến thường được thiết kế như sau:

```java
public final class User {
    private final long id;
    private final String name;

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Các field chỉ được gán trong constructor. Không có setter để Jackson gọi sau khi tạo object. Ta cần chỉ cho Jackson biết constructor nào cần dùng và tham số nào nhận giá trị từ từng thuộc tính JSON.

Đó là nhiệm vụ của `@JsonCreator`.

## 2. @JsonCreator và @JsonProperty

Hai annotation thường đi cùng nhau:

| Annotation | Package trong Jackson 2.x | Vai trò |
|---|---|---|
| `@JsonCreator` | `com.fasterxml.jackson.annotation` | Đánh dấu constructor hoặc static factory method dùng để tạo object khi deserialize |
| `@JsonProperty` | `com.fasterxml.jackson.annotation` | Gắn tên thuộc tính JSON với tham số creator |

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class User {
    private final long id;
    private final String name;

    @JsonCreator
    public User(
            @JsonProperty("id") long id,
            @JsonProperty("name") String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

JSON đầu vào:

```json
{
  "id": 42,
  "name": "An"
}
```

Đọc dữ liệu:

```java
ObjectMapper mapper = new ObjectMapper();

User user = mapper.readValue(json, User.class);

System.out.println(user.getId());
System.out.println(user.getName());
```

Jackson đọc các thuộc tính JSON, chuyển đổi giá trị sang kiểu tham số tương ứng, rồi gọi constructor. Sau khi constructor hoàn tất, object `User` đã có đầy đủ trạng thái và không cần setter.

## 3. Property-based creator

Đây là cách dùng phổ biến khi JSON là một object có nhiều key và mỗi key tương ứng với một tham số constructor.

Có thể chỉ rõ mode:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public User(
        @JsonProperty("id") long id,
        @JsonProperty("name") String name) {
    this.id = id;
    this.name = name;
}
```

`JsonCreator.Mode.PROPERTIES` yêu cầu Jackson lấy các giá trị từ các property riêng lẻ của JSON object rồi truyền vào tham số tương ứng.

Luồng xử lý:

```text
JSON object
{
  "id": 42,
  "name": "An"
}
       |
       v
Đọc property "id"   -> tham số id
Đọc property "name" -> tham số name
       |
       v
Gọi constructor User(id, name)
       |
       v
User bất biến đã hoàn chỉnh
```

### 3.1. Tên tham số phải được xác định

Để property-based creator hoạt động ổn định, nên khai báo `@JsonProperty` rõ ràng cho từng tham số.

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Account(
        @JsonProperty("account_id") long id,
        @JsonProperty("owner_name") String owner) {
    // ...
}
```

Nếu không khai báo tên property, Jackson cần metadata tên tham số từ môi trường build hoặc module hỗ trợ. Tên tham số trong bytecode Java không phải lúc nào cũng có sẵn nếu dự án không bật compiler option phù hợp.

Một cách khác là biên dịch với `-parameters` và đăng ký `ParameterNamesModule` trong các trường hợp cần dùng tên tham số thật. Tuy nhiên, với DTO trao đổi qua API, `@JsonProperty` tường minh giúp hợp đồng JSON rõ ràng và không phụ thuộc cấu hình compiler.

### 3.2. Tên JSON khác tên Java

Tên key JSON không cần trùng tên tham số hoặc field Java:

```java
public final class Customer {
    private final String displayName;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Customer(
            @JsonProperty("display_name") String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Payload:

```json
{
  "display_name": "An"
}
```

Jackson ánh xạ `display_name` vào tham số `displayName`. Cách này hữu ích khi API dùng snake_case còn mã Java dùng camelCase.

Có thể kết hợp `@JsonAlias` trên tham số creator nếu cần chấp nhận tên cũ:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(
        @JsonProperty("display_name")
        @JsonAlias({"name", "full_name"})
        String displayName) {
    this.displayName = displayName;
}
```

Tên chuẩn vẫn là `display_name`; alias chỉ bổ sung tên đầu vào được chấp nhận khi deserialize.

## 4. Static factory method làm creator

Không bắt buộc phải dùng constructor. Jackson cũng có thể gọi một static factory method được đánh dấu `@JsonCreator`.

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class Money {
    private final long amount;
    private final String currency;

    private Money(long amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public static Money of(
            @JsonProperty("amount") long amount,
            @JsonProperty("currency") String currency) {

        if (amount < 0) {
            throw new IllegalArgumentException(
                "amount must not be negative"
            );
        }

        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException(
                "currency must not be blank"
            );
        }

        return new Money(amount, currency);
    }

    public long getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Jackson gọi `Money.of(...)` thay vì gọi constructor private trực tiếp. Static factory có một số lợi ích:

- Có thể dùng tên có ý nghĩa như `of`, `from`, `create`.
- Có thể kiểm tra đầu vào trước khi tạo object.
- Có thể trả về subtype hoặc instance được cache nếu mô hình cho phép.
- Constructor có thể được giữ private để kiểm soát cách khởi tạo.

Một creator method cần là static và trả về kiểu phù hợp với kiểu đích đang deserialize.

## 5. Creator mode: PROPERTIES, DELEGATING và DEFAULT

`@JsonCreator` có thuộc tính `mode` để xác định Jackson diễn giải tham số creator như thế nào.

| Mode | Ý nghĩa | Hình dạng JSON thường gặp |
|---|---|---|
| `PROPERTIES` | Mỗi tham số nhận giá trị từ một property JSON | Object `{...}` |
| `DELEGATING` | Toàn bộ giá trị JSON được chuyển vào một tham số creator | String, number, array, object hoặc node tùy kiểu tham số |
| `DEFAULT` | Để Jackson chọn cách diễn giải theo quy tắc creator và metadata | Phụ thuộc chữ ký và metadata |
| `DISABLED` | Vô hiệu hóa một creator được đánh dấu ở nơi khác trong một số trường hợp introspection | Không dùng creator đó |

Với constructor nhiều tham số ánh xạ vào các key object, dùng `PROPERTIES` để thể hiện rõ ý định. Với constructor một tham số đại diện cho toàn bộ JSON value, dùng `DELEGATING`.

### 5.1. Delegating creator cho JSON scalar

Giả sử một kiểu `UserId` chỉ bao bọc một chuỗi:

```java
import com.fasterxml.jackson.annotation.JsonCreator;

public final class UserId {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public UserId(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("UserId is required");
        }
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

JSON đầu vào là một giá trị string đơn:

```json
"usr-42"
```

Đọc:

```java
UserId id = mapper.readValue("\"usr-42\"", UserId.class);
```

Jackson chuyển toàn bộ JSON string thành tham số `value`, rồi gọi constructor.

Nếu dùng property-based creator trong khi JSON chỉ là scalar, Jackson sẽ không có object property tên tương ứng để gán cho tham số. Mode `DELEGATING` mô tả đúng ý định nhận toàn bộ giá trị đầu vào.

### 5.2. Delegating creator với object hoặc cấu trúc tổng quát

Một creator delegating cũng có thể nhận toàn bộ object JSON dưới dạng `JsonNode` hoặc kiểu khác mà Jackson có thể deserialize:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.databind.JsonNode;

public final class Coordinates {
    private final double latitude;
    private final double longitude;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public Coordinates(JsonNode node) {
        this.latitude = node.path("lat").asDouble();
        this.longitude = node.path("lng").asDouble();
    }

    public double getLatitude() {
        return latitude;
    }

    public double getLongitude() {
        return longitude;
    }
}
```

JSON:

```json
{
  "lat": 10.8,
  "lng": 106.7
}
```

Trong trường hợp này, Jackson đưa cả object JSON vào một tham số `JsonNode`. Lớp tự chịu trách nhiệm đọc và xác thực các trường. Cách này linh hoạt, nhưng nếu cấu trúc đã ổn định và có nhiều property, property-based creator thường dễ hiểu và ít mã tùy chỉnh hơn.

### 5.3. Khi nào nên khai báo mode rõ ràng?

Constructor một tham số có thể gây mơ hồ nếu không khai báo mode, vì Jackson phải quyết định tham số đó đại diện cho một property hay toàn bộ JSON value. Kết quả suy luận phụ thuộc metadata và phiên bản.

Vì vậy:

- Dùng `PROPERTIES` cho constructor/factory nhận nhiều tham số gắn với key JSON.
- Dùng `DELEGATING` cho wrapper type hoặc creator nhận toàn bộ một giá trị JSON.
- Ghi rõ mode khi chữ ký có thể được hiểu theo nhiều cách.
- Không dựa vào suy luận mặc định nếu hợp đồng API cần hành vi ổn định.

## 6. Thuộc tính bị thiếu, null và giá trị mặc định

Khi dùng creator, cần phân biệt ba tình huống:

1. JSON không có key.
2. JSON có key với giá trị `null`.
3. JSON có key với một giá trị cụ thể.

Ví dụ:

```json
{
  "id": 42
}
```

Ở đây `name` bị thiếu.

```json
{
  "id": 42,
  "name": null
}
```

Ở đây `name` có mặt nhưng giá trị là null.

Với tham số kiểu tham chiếu, Jackson thường truyền null nếu key có giá trị null. Với tham số primitive như `long` hoặc `boolean`, null không thể biểu diễn trực tiếp; hành vi phụ thuộc cấu hình null handling, và có thể nhận giá trị mặc định của primitive hoặc phát sinh lỗi nếu bật chế độ tương ứng.

### 6.1. Bắt buộc có creator property

Có thể đánh dấu một tham số bắt buộc:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public User(
        @JsonProperty(value = "id", required = true) long id,
        @JsonProperty("name") String name) {
    this.id = id;
    this.name = name;
}
```

`required = true` là metadata để Jackson kiểm tra sự hiện diện của creator property. Có thể kết hợp với các feature như `FAIL_ON_MISSING_CREATOR_PROPERTIES` khi muốn áp dụng chính sách chặt hơn cho các tham số creator bị thiếu. Cần phân biệt kiểm tra "thiếu key" với kiểm tra "key có giá trị null"; hai trường hợp có thể cần chính sách riêng.

### 6.2. Kiểm soát null cho primitive

Nếu không chấp nhận null cho tham số primitive, có thể bật:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
```

Khi đó, JSON có `"id": null` không bị âm thầm chuyển thành giá trị mặc định cho primitive mà bị từ chối.

Đối với kiểu tham chiếu, có thể xác thực trong constructor/factory:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public User(
        @JsonProperty("id") long id,
        @JsonProperty("name") String name) {

    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name is required");
    }

    this.id = id;
    this.name = name;
}
```

Nếu cần áp dụng quy tắc khác nhau cho missing và null, hãy xác định rõ hợp đồng JSON và cấu hình creator tương ứng. Đừng coi một giá trị null là tương đương với việc client không gửi key.

## 7. Validation và exception trong creator

Constructor hoặc static factory là nơi phù hợp để bảo vệ invariant của lớp bất biến. Object chỉ được tạo khi dữ liệu đáp ứng các điều kiện cần thiết.

Ví dụ:

```java
public final class EmailAddress {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public EmailAddress(String value) {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

Khi creator ném exception, Jackson thường bọc lỗi khởi tạo trong exception thuộc nhóm mapping/instantiation, giữ nguyên nguyên nhân gốc để ứng dụng có thể chẩn đoán. Ở tầng API, nên chuyển lỗi thành phản hồi validation phù hợp mà không để lộ stack trace hoặc chi tiết nội bộ cho client.

Không nên nhầm việc gọi creator với việc tự động chạy Bean Validation. Nếu ứng dụng dùng Jakarta Bean Validation, cần tích hợp validator rõ ràng ở tầng phù hợp hoặc gọi validation từ factory/domain service. `@JsonCreator` chỉ xác định cách tạo object.

## 8. Kết hợp creator với các annotation khác

Creator thường kết hợp với những annotation khác để mô tả hợp đồng JSON:

| Annotation | Tác dụng khi dùng với creator |
|---|---|
| `@JsonProperty` | Đặt tên JSON cho từng tham số |
| `@JsonAlias` | Chấp nhận tên cũ cho một tham số |
| `@JsonFormat` | Quy định định dạng cho kiểu dữ liệu cụ thể |
| `@JsonSetter` | Điều khiển cách xử lý null/đầu vào cho property trong các trường hợp được hỗ trợ |
| `@JsonIgnoreProperties` | Điều khiển việc xử lý property không biết ở phạm vi lớp |
| `@JsonInclude` | Chủ yếu điều khiển property được phát ra khi serialize |

Ví dụ creator với alias:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public User(
        @JsonProperty("user_id")
        @JsonAlias({"id", "legacy_id"})
        long userId,

        @JsonProperty("display_name")
        String displayName) {
    this.userId = userId;
    this.displayName = displayName;
}
```

Client cũ có thể gửi `id`, client mới gửi `user_id`; cả hai đều khởi tạo cùng thuộc tính Java `userId`.

## 9. Creator và serialization là hai chiều riêng biệt

`@JsonCreator` điều khiển chiều **deserialize**: JSON thành object. Khi serialize object thành JSON, Jackson introspect lớp theo getter, field, annotation và cấu hình serialization.

Ví dụ lớp bất biến:

```java
public final class Product {
    private final long id;
    private final String name;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Product(
            @JsonProperty("product_id") long id,
            @JsonProperty("product_name") String name) {
        this.id = id;
        this.name = name;
    }

    @JsonProperty("product_id")
    public long getId() {
        return id;
    }

    @JsonProperty("product_name")
    public String getName() {
        return name;
    }
}
```

Đọc rồi ghi lại:

```java
Product product = mapper.readValue(json, Product.class);
String output = mapper.writeValueAsString(product);
```

Getter giúp Jackson có thông tin để serialize. Annotation `@JsonProperty` trên creator parameter không nên được xem là cam kết rằng mọi cấu hình serialization sẽ tự động phát ra đúng cấu trúc mong muốn; hãy khai báo metadata output ở property/getter nếu hợp đồng yêu cầu tên cụ thể và kiểm thử riêng hai chiều.

## 10. So sánh @JsonCreator với Builder

Cả creator và builder đều có thể tạo object bất biến, nhưng phù hợp với quy mô và cách tổ chức dữ liệu khác nhau.

| Tiêu chí | `@JsonCreator` | Builder |
|---|---|---|
| Cách tạo object | Gọi constructor hoặc static factory với tham số | Tạo builder, gọi mutator, rồi gọi build |
| Mức độ cấu hình | Đánh dấu creator và metadata tham số | `@JsonDeserialize(builder=...)` và `@JsonPOJOBuilder` |
| Phù hợp nhất | Lớp có ít hoặc số lượng tham số vừa phải, mapping rõ ràng | Lớp có nhiều thuộc tính tùy chọn và quy tắc tạo phức tạp |
| Giá trị mặc định | Xử lý trong constructor/factory hoặc kiểu dữ liệu | Có thể đặt mặc định ngay trên builder field |
| Validation | Trong constructor/factory hoặc domain factory | Trong build method hoặc domain factory |
| Độ dài mã | Thường ngắn gọn | Thường nhiều mã hơn, nhưng rõ bước thu thập trạng thái |

Quy tắc chọn:

- Dùng `@JsonCreator` nếu object có cấu trúc ổn định và việc truyền các giá trị vào constructor là tự nhiên.
- Dùng builder nếu có nhiều trường tùy chọn, cần giá trị mặc định hoặc cần kiểm tra nhiều điều kiện trước khi tạo object.
- Không cần tạo builder chỉ để tránh một constructor có hai hoặc ba tham số.
- Không nên nhồi toàn bộ logic nghiệp vụ phức tạp vào creator; có thể chuyển logic đó sang domain factory.

## 11. Java record và creator

Java record được thiết kế như kiểu dữ liệu bất biến với các component và canonical constructor. Các phiên bản Jackson hiện đại có hỗ trợ record, vì vậy trong trường hợp đơn giản, không nhất thiết phải tự viết `@JsonCreator` cho canonical constructor.

```java
public record UserRecord(long id, String name) {
}
```

JSON:

```json
{
  "id": 42,
  "name": "An"
}
```

Có thể đọc bằng:

```java
UserRecord user = mapper.readValue(json, UserRecord.class);
```

Nếu cần đổi tên JSON hoặc bổ sung metadata, có thể gắn `@JsonProperty` lên record component:

```java
public record UserRecord(
    @JsonProperty("user_id") long id,
    @JsonProperty("display_name") String name
) {
}
```

Record support phụ thuộc phiên bản Jackson và JDK mà dự án sử dụng. Với major/minor version cũ, hãy kiểm tra khả năng hỗ trợ trước khi dùng. Nếu cần một constructor/factory có quy tắc riêng hoặc muốn kiểm soát rõ mode, `@JsonCreator` vẫn là lựa chọn phù hợp.

## 12. Lỗi thường gặp khi dùng @JsonCreator

**Quên `@JsonProperty` trên tham số.** Jackson không biết key JSON nào tương ứng với tham số, trừ khi có metadata tên tham số phù hợp. Khai báo tên rõ ràng để tránh phụ thuộc compiler.

**Dùng sai mode.** Constructor một tham số nhận scalar nhưng được diễn giải như property-based creator, hoặc constructor nhiều tham số cần map object nhưng metadata không đầy đủ. Hãy chỉ định `PROPERTIES` hoặc `DELEGATING` rõ ràng.

**Creator không truy cập được.** Jackson cần quyền truy cập phù hợp tới constructor hoặc factory. Ưu tiên creator public; nếu dùng visibility đặc biệt, hãy kiểm tra module Java, cấu hình access override và môi trường runtime.

**Tên JSON không khớp.** `@JsonProperty("user_id")` nhưng client gửi `id` thì không tự động tương thích. Thêm `@JsonAlias("id")` nếu cần đọc tên cũ.

**Không phân biệt missing và null.** Primitive không thể chứa null; property bị thiếu cũng không nhất thiết có cùng ý nghĩa với null. Xác định chính sách và cấu hình feature phù hợp.

**Chỉ kiểm thử deserialize.** Creator không tự xác định toàn bộ quy tắc serialization. Kiểm thử riêng JSON đầu vào và đầu ra.

**Đưa quá nhiều logic vào constructor.** Constructor nên bảo vệ invariant và tạo trạng thái hợp lệ. Logic truy cập database, gọi dịch vụ hoặc side effect không nên đặt trong creator được Jackson gọi khi đọc payload.

## 13. Kiểm thử creator

Ví dụ JUnit kiểm tra property-based creator:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class UserCreatorTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void createsImmutableObjectFromProperties() throws Exception {
        User user = mapper.readValue(
            """
            {
              "id": 42,
              "name": "An"
            }
            """,
            User.class
        );

        assertEquals(42L, user.getId());
        assertEquals("An", user.getName());
    }

    @Test
    void serializesUsingExpectedPropertyNames() throws Exception {
        User user = new User(42L, "An");

        String json = mapper.writeValueAsString(user);

        assertEquals(
            """
            {"id":42,"name":"An"}
            """.trim(),
            json
        );
    }
}
```

Với mỗi creator, nên có test cho:

- JSON có đủ các property.
- Property bị thiếu.
- Property có giá trị null.
- Giá trị sai kiểu hoặc không hợp lệ theo invariant.
- Alias nếu có hỗ trợ tên cũ.
- Serialization của object sau khi tạo.
- Delegating creator với đúng hình dạng scalar/object mà nó mong đợi.

## 14. Ghi nhớ

- `@JsonCreator` đánh dấu constructor hoặc static factory method để Jackson tạo object khi deserialize.
- `@JsonProperty` liên kết key JSON với tham số creator; nên khai báo tên rõ ràng.
- `PROPERTIES` dành cho object JSON có các key tương ứng với tham số; `DELEGATING` dành cho creator nhận toàn bộ một giá trị JSON.
- Static factory method có thể kiểm tra dữ liệu trước khi tạo object và giữ constructor private.
- Phân biệt key bị thiếu, key có giá trị null và key có giá trị cụ thể.
- Creator không tự động thay thế Bean Validation và không quyết định toàn bộ cách serialize.
- Dùng `@JsonCreator` cho constructor/factory gọn; dùng builder khi cần nhiều bước thiết lập, giá trị mặc định và validation phức tạp.

