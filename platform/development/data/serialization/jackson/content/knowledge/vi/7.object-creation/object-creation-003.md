# Phân biệt creator dựa trên thuộc tính và creator ủy quyền

Khi Jackson deserialize JSON thành một lớp Java, nó cần biết cách tạo instance. Với POJO có constructor mặc định và setter, Jackson thường tạo object trước rồi gán từng thuộc tính. Nhưng nhiều lớp được thiết kế bất biến, chỉ có constructor tham số hoặc factory method tĩnh. Trong trường hợp đó, Jackson có thể dùng một **creator** để tạo object ngay từ dữ liệu JSON.

Hai cách hoạt động quan trọng của creator là **property-based creator** (creator dựa trên thuộc tính) và **delegating creator** (creator ủy quyền). Khác biệt cốt lõi nằm ở dữ liệu được truyền vào constructor hoặc factory method:

- Property-based creator nhận từng giá trị JSON theo tên thuộc tính, rồi truyền các giá trị đó vào các tham số tương ứng.
- Delegating creator nhận toàn bộ giá trị JSON như một đối số duy nhất; Jackson chuyển đổi toàn bộ giá trị đó sang kiểu của tham số rồi gọi creator.

Hiểu đúng hai chế độ này giúp chọn constructor phù hợp, tránh lỗi khi deserialize constructor một tham số và giữ được hợp đồng JSON rõ ràng.

## 1. Creator trong Jackson là gì?

Creator là constructor hoặc factory method mà Jackson sử dụng để tạo instance khi deserialize. Có thể đánh dấu creator bằng `@JsonCreator`.

Ví dụ một lớp chỉ có constructor nhận tham số:

```java
public class UserId {
    private final long value;

    @JsonCreator
    public UserId(@JsonProperty("value") long value) {
        this.value = value;
    }

    public long getValue() {
        return value;
    }
}
```

Jackson cần xác định JSON cung cấp giá trị cho tham số `value` theo cách nào. JSON có thể là một object chứa field `value`, hoặc một giá trị scalar như số `42`. Hai hình dạng đó tương ứng với hai ý nghĩa creator khác nhau.

Annotation `@JsonCreator` có thể đặt trên:

- Constructor được dùng để tạo instance.
- Factory method tĩnh trả về instance của kiểu cần deserialize.

Ví dụ factory method:

```java
public class UserId {
    private final long value;

    private UserId(long value) {
        this.value = value;
    }

    @JsonCreator
    public static UserId fromValue(@JsonProperty("value") long value) {
        return new UserId(value);
    }

    public long getValue() {
        return value;
    }
}
```

Factory method hữu ích khi việc tạo object cần kiểm tra, chuẩn hóa hoặc áp dụng quy tắc khởi tạo. Jackson vẫn cần biết cách ánh xạ dữ liệu JSON vào tham số của method.

## 2. Property-based creator: mỗi tham số tương ứng một thuộc tính JSON

Property-based creator phù hợp khi JSON đầu vào là một object và các tham số constructor/factory method đại diện cho các thuộc tính trong object đó.

### 2.1. Khai báo bằng @JsonCreator.Mode.PROPERTIES

Giả sử ứng dụng có lớp `Money` bất biến:

```java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
            @JsonProperty("amount") BigDecimal amount,
            @JsonProperty("currency") String currency) {
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

JSON tương ứng:

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Jackson đọc object, tìm các giá trị `amount` và `currency`, chuyển chúng sang kiểu tham số tương ứng rồi gọi constructor. Sau khi constructor hoàn tất, object đã được tạo với các field `final`.

Có thể deserialize bằng:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "amount": 125.50,
      "currency": "USD"
    }
    """;

Money money = mapper.readValue(json, Money.class);
System.out.println(money.getCurrency());
```

Ở chế độ `PROPERTIES`, tên trong `@JsonProperty` là tên thuộc tính JSON mà Jackson dùng để ghép dữ liệu với tham số. Tên tham số Java không nhất thiết tự động là tên JSON; khai báo tường minh giúp hợp đồng rõ ràng và ổn định.

### 2.2. Vì sao cần tên cho tham số creator?

Java không phải lúc nào cũng lưu tên tham số trong bytecode. Nếu muốn Jackson suy ra tên tham số, dự án phải cung cấp metadata phù hợp, ví dụ biên dịch với `-parameters` và sử dụng cơ chế/module hỗ trợ đọc tên tham số. Dù vậy, với creator dựa trên thuộc tính, khai báo `@JsonProperty` trên từng tham số thường dễ hiểu và ít phụ thuộc môi trường build hơn.

Ví dụ không nên dựa vào tên tham số chưa được lưu:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Money(BigDecimal amount, String currency) {
    this.amount = amount;
    this.currency = currency;
}
```

Nếu Jackson không thể xác định tên các tham số, nó không thể biết field JSON nào tương ứng với từng đối số. Có thể phát sinh lỗi creator property không có tên hoặc không thể xây dựng property-based creator.

Khai báo rõ ràng:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Money(
        @JsonProperty("amount") BigDecimal amount,
        @JsonProperty("currency") String currency) {
    this.amount = amount;
    this.currency = currency;
}
```

### 2.3. Dùng factory method với property-based creator

Property-based creator không bắt buộc phải là constructor. Có thể dùng factory method tĩnh:

```java
public class EmailAddress {
    private final String value;

    private EmailAddress(String value) {
        this.value = value;
    }

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public static EmailAddress create(
            @JsonProperty("address") String address) {
        if (address == null || address.isBlank()) {
            throw new IllegalArgumentException("address is required");
        }
        return new EmailAddress(address.trim());
    }

    public String getValue() {
        return value;
    }
}
```

JSON phải có dạng object với property `address`:

```json
{
  "address": "dev@example.com"
}
```

Factory method có thể áp dụng validation hoặc chuẩn hóa dữ liệu trước khi trả về instance. Exception phát sinh trong quá trình tạo object sẽ làm thao tác deserialize thất bại; hãy xử lý và chuyển đổi lỗi ở ranh giới phù hợp của ứng dụng.

### 2.4. Xử lý field thiếu, null và giá trị mặc định

Property-based creator cần có chính sách rõ ràng với field thiếu hoặc có giá trị `null`.

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Money(
        @JsonProperty("amount") BigDecimal amount,
        @JsonProperty("currency") String currency) {
    this.amount = amount;
    this.currency = currency;
}
```

Nếu `currency` không xuất hiện trong JSON, giá trị tham số có thể là `null` nếu kiểu tham số cho phép. Nếu tham số là primitive như `long` hoặc `boolean`, giá trị mặc định của kiểu Java có thể được sử dụng tùy cấu hình và feature của Jackson.

Một số feature liên quan:

| Feature | Tác dụng |
|---|---|
| `FAIL_ON_MISSING_CREATOR_PROPERTIES` | Báo lỗi khi thiếu creator property theo chính sách của feature. |
| `FAIL_ON_NULL_CREATOR_PROPERTIES` | Báo lỗi khi creator property có giá trị null. |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Báo lỗi khi JSON null được gán vào kiểu primitive. |

Có thể cấu hình theo mapper hoặc theo reader:

```java
ObjectReader strictMoneyReader = mapper
    .readerFor(Money.class)
    .with(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .with(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES);
```

Các feature có phạm vi và điều kiện áp dụng riêng. `@JsonProperty(required = true)` cũng có thể diễn đạt yêu cầu cho creator property, nhưng không thay thế việc xác định rõ chính sách null và giá trị mặc định của ứng dụng.

## 3. Delegating creator: toàn bộ JSON được chuyển thành một đối số

Delegating creator phù hợp khi constructor hoặc factory method nhận một giá trị đại diện cho toàn bộ nội dung JSON. Jackson không ghép từng field JSON với nhiều tham số. Thay vào đó, nó deserialize toàn bộ giá trị JSON thành kiểu của một tham số rồi truyền giá trị đó vào creator.

### 3.1. Khai báo bằng @JsonCreator.Mode.DELEGATING

Một lớp `UserId` có thể được biểu diễn trong JSON bằng một số scalar:

```java
public class UserId {
    private final long value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public UserId(long value) {
        this.value = value;
    }

    public long getValue() {
        return value;
    }
}
```

JSON đầu vào là:

```json
42
```

Jackson chuyển số `42` thành `long`, sau đó gọi `new UserId(42)`. Không cần object bọc ngoài như `{"value": 42}`.

Ví dụ sử dụng:

```java
ObjectMapper mapper = new ObjectMapper();

UserId id = mapper.readValue("42", UserId.class);
System.out.println(id.getValue());
```

Đây là điểm khác biệt chính với property-based creator: JSON scalar là toàn bộ đầu vào của creator, chứ không phải một object chứa field có tên trùng với tham số.

### 3.2. Delegating creator với JSON object

Delegating không chỉ dùng cho scalar. Toàn bộ JSON object hoặc array cũng có thể được chuyển thành một tham số duy nhất. Ví dụ, lớp cần nhận một cây JSON để tự quyết định cách xử lý:

```java
public class EventPayload {
    private final String eventType;
    private final JsonNode body;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public EventPayload(JsonNode root) {
        this.eventType = root.path("type").asText();
        this.body = root.path("payload");
    }

    public String getEventType() {
        return eventType;
    }

    public JsonNode getBody() {
        return body;
    }
}
```

JSON vẫn có thể là object:

```json
{
  "type": "user-created",
  "payload": {
    "id": 25,
    "name": "An"
  }
}
```

Jackson chuyển toàn bộ object JSON thành một `JsonNode`, rồi truyền node gốc cho constructor. Constructor tự đọc `type` và `payload`.

Một ví dụ khác là nhận toàn bộ object thành `Map`:

```java
public class Settings {
    private final Map<String, Object> values;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public Settings(Map<String, Object> values) {
        this.values = Map.copyOf(values);
    }

    public Map<String, Object> getValues() {
        return values;
    }
}
```

Trong ví dụ này, JSON object được deserialize thành `Map<String, Object>` trước, rồi map được truyền như một đối số duy nhất cho constructor. Nếu dùng kiểu collection generic, cần bảo đảm Jackson có đủ thông tin kiểu của tham số để chuyển đổi giá trị lồng nhau theo mong muốn.

### 3.3. Delegating creator với factory method

Factory method cũng có thể nhận toàn bộ JSON như một giá trị:

```java
public class Temperature {
    private final BigDecimal celsius;

    private Temperature(BigDecimal celsius) {
        this.celsius = celsius;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static Temperature fromCelsius(BigDecimal value) {
        return new Temperature(value);
    }

    public BigDecimal getCelsius() {
        return celsius;
    }
}
```

JSON là một number:

```json
36.5
```

Jackson chuyển scalar thành `BigDecimal` rồi gọi factory method. Cách này phù hợp với value object có biểu diễn JSON tự nhiên là một scalar.

## 4. So sánh PROPERTIES và DELEGATING

Hai mode có thể cùng sử dụng một constructor một tham số, nhưng ý nghĩa của JSON đầu vào khác nhau.

| Tiêu chí | Property-based (`PROPERTIES`) | Delegating (`DELEGATING`) |
|---|---|---|
| Dữ liệu truyền vào creator | Nhiều giá trị theo tên property | Một giá trị JSON hoàn chỉnh |
| JSON thường gặp | Object có các field được ánh xạ | Scalar, array hoặc object được chuyển thành kiểu tham số |
| Tham số constructor | Mỗi tham số đại diện cho một thuộc tính | Một tham số đại diện cho toàn bộ payload |
| Cách ghép dữ liệu | `@JsonProperty` hoặc metadata tên tham số | Jackson deserialize toàn bộ token/value sang kiểu tham số |
| Trường hợp phù hợp | DTO bất biến có nhiều thuộc tính | Value object, wrapper hoặc kiểu tự xử lý payload |

Ví dụ cùng một lớp một tham số nhưng hai hợp đồng JSON khác nhau:

```java
// Property-based: JSON object {"value": 42}
public class PropertyId {
    private final long value;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PropertyId(@JsonProperty("value") long value) {
        this.value = value;
    }
}

// Delegating: JSON scalar 42
public class ScalarId {
    private final long value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ScalarId(long value) {
        this.value = value;
    }
}
```

Hai class trên minh họa hai hình dạng JSON khác nhau. Nếu đổi mode mà không đổi hợp đồng đầu vào, quá trình deserialize có thể thất bại hoặc không tạo ra kết quả mà API mong đợi.

## 5. Vì sao creator một tham số dễ gây nhầm lẫn?

Constructor một tham số có thể mang hai ý nghĩa:

```java
public UserId(long value) { ... }
```

Tham số `value` có thể đại diện cho:

- Một property có tên `value` trong JSON object.
- Toàn bộ JSON scalar, ví dụ số `42`.

Nếu không khai báo rõ, Jackson có thể phải suy luận dựa trên tên tham số, annotation, metadata và quy tắc của phiên bản/cấu hình đang dùng. Hành vi suy luận này dễ tạo khác biệt khi thay đổi compiler option hoặc nâng phiên bản thư viện.

Với creator một tham số, hãy khai báo mode tường minh khi hợp đồng JSON đã biết:

```java
// Muốn nhận {"value": 42}
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public UserId(@JsonProperty("value") long value) {
    this.value = value;
}
```

Hoặc:

```java
// Muốn nhận 42
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public UserId(long value) {
    this.value = value;
}
```

`JsonCreator.Mode.DEFAULT` cho phép Jackson áp dụng quy tắc suy luận. Mode này hữu ích trong trường hợp phù hợp với quy ước của dự án, nhưng không nên dựa vào suy luận khi một constructor có thể được hiểu theo hai hợp đồng khác nhau. Ghi rõ `PROPERTIES` hoặc `DELEGATING` làm ý định dễ đọc và ít phụ thuộc hơn vào metadata.

## 6. Nhiều tham số và creator dựa trên thuộc tính

Constructor nhiều tham số thường phù hợp tự nhiên với property-based creator:

```java
public class PersonName {
    private final String firstName;
    private final String lastName;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PersonName(
            @JsonProperty("first_name") String firstName,
            @JsonProperty("last_name") String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
```

JSON:

```json
{
  "first_name": "An",
  "last_name": "Nguyen"
}
```

Mỗi tham số creator được ghép với một property riêng. Jackson đọc các field của object, chuyển từng giá trị sang kiểu Java tương ứng rồi gọi constructor.

Với constructor nhiều tham số, nên dùng `@JsonProperty` trên từng tham số. Nếu dự án dựa vào tên tham số được lưu trong bytecode, cần cấu hình compiler và module hỗ trợ phù hợp; không nên giả định mọi môi trường build đều giữ tên tham số.

## 7. Chọn mode cho constructor và factory method

### 7.1. Property-based creator cho DTO bất biến

Chọn `PROPERTIES` khi JSON là object có nhiều thuộc tính độc lập và constructor nhận từng giá trị:

```java
public class Book {
    private final String title;
    private final int pages;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Book(
            @JsonProperty("title") String title,
            @JsonProperty("pages") int pages) {
        this.title = title;
        this.pages = pages;
    }
}
```

Hình dạng JSON phù hợp:

```json
{
  "title": "Effective Java",
  "pages": 416
}
```

Constructor có thể kiểm tra dữ liệu và giữ các field ở trạng thái `final`. Mỗi tham số có tên rõ ràng, vì vậy hợp đồng JSON có thể được đọc trực tiếp từ annotation.

### 7.2. Delegating creator cho value object

Chọn `DELEGATING` khi kiểu Java là wrapper quanh một giá trị duy nhất:

```java
public class OrderNumber {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public OrderNumber(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

JSON có thể chỉ là:

```json
"ORD-2026-001"
```

Jackson chuyển toàn bộ chuỗi JSON thành `String`, sau đó gọi constructor. Đây là cách biểu diễn gọn cho kiểu có một giá trị cốt lõi.

### 7.3. Factory method khi cần kiểm tra hoặc chuẩn hóa

Factory method có thể thực hiện quy tắc khởi tạo trước khi trả về object:

```java
public class CountryCode {
    private final String value;

    private CountryCode(String value) {
        this.value = value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static CountryCode of(String rawValue) {
        if (rawValue == null || rawValue.isBlank()) {
            throw new IllegalArgumentException("Country code is required");
        }
        return new CountryCode(rawValue.trim().toUpperCase(Locale.ROOT));
    }

    public String getValue() {
        return value;
    }
}
```

JSON đầu vào là một chuỗi. Factory method kiểm tra giá trị rồi chuẩn hóa trước khi tạo instance. Cách này tách logic tạo object khỏi phần gọi constructor và phù hợp với domain value object.

## 8. Field thiếu, null và tính hợp lệ của creator property

Property-based creator cần có chính sách rõ ràng đối với dữ liệu thiếu hoặc null. Ví dụ:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Account(
        @JsonProperty("id") long id,
        @JsonProperty("displayName") String displayName) {
    this.id = id;
    this.displayName = displayName;
}
```

Nếu JSON không có `displayName`, tham số tham chiếu có thể nhận `null` tùy cấu hình. Nếu thiếu `id`, kiểu primitive có thể nhận giá trị mặc định theo quy tắc xử lý hiện hành. Nếu JSON cung cấp `null` cho primitive, kết quả còn phụ thuộc feature của Jackson.

Các feature thường cần biết:

| Feature | Ý nghĩa |
|---|---|
| `FAIL_ON_MISSING_CREATOR_PROPERTIES` | Báo lỗi khi thiếu creator property theo chính sách của feature. |
| `FAIL_ON_NULL_CREATOR_PROPERTIES` | Báo lỗi khi creator property có giá trị null. |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Báo lỗi khi JSON null được gán cho kiểu primitive. |

Có thể cấu hình chính sách nghiêm ngặt cho một reader:

```java
ObjectReader accountReader = mapper
    .readerFor(Account.class)
    .with(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .with(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .with(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Các feature có phạm vi và điều kiện áp dụng riêng; không nên bật tất cả một cách máy móc. Hãy xác định field nào thực sự bắt buộc và liệu `null` có ý nghĩa nghiệp vụ riêng hay không. `@JsonProperty(required = true)` có thể diễn đạt yêu cầu đối với creator property, nhưng cần kết hợp với chính sách null phù hợp.

## 9. Những lỗi thường gặp và cách chẩn đoán

### Jackson không tìm được tên tham số

Nếu constructor property-based không có `@JsonProperty`, Jackson có thể không xác định được tên tham số. Kiểm tra bytecode có lưu tên tham số hay không, compiler có bật `-parameters` hay không và module hỗ trợ parameter names đã được cấu hình chưa. Với DTO dùng cho API, khai báo tên tường minh thường ổn định hơn.

### JSON object không deserialize được vào constructor scalar

Một constructor delegating nhận `long` mong đợi giá trị JSON có thể chuyển thành số, chẳng hạn `42`. Nếu gửi `{"value":42}`, đó là JSON object. Muốn nhận object theo từng field, dùng property-based creator với `@JsonProperty("value")`; muốn nhận toàn bộ object như một đối số, dùng delegating creator với kiểu tham số phù hợp như `JsonNode` hoặc `Map`.

### JSON scalar không khớp với property-based creator

Constructor property-based cần các thuộc tính của JSON object. Nếu đầu vào là `"ORD-1"` hoặc `42`, hãy xem xét delegating creator. Không nên chỉ đổi annotation mà không xác nhận hợp đồng JSON mà hệ thống gửi và nhận.

### Có nhiều creator được đánh dấu

Một lớp có nhiều constructor/factory method được đánh dấu có thể khiến Jackson không xác định được creator phù hợp hoặc báo lỗi xung đột. Giữ một creator chính cho từng kiểu dữ liệu và khai báo mode tường minh khi cần. Các constructor phụ phục vụ mã Java thông thường không nhất thiết phải là creator của Jackson.

### Constructor chạy nhưng dữ liệu không hợp lệ

Creator có thể kiểm tra dữ liệu và ném exception. Hãy giữ validation ở vị trí phù hợp, cung cấp thông báo lỗi có ngữ cảnh và xử lý lỗi deserialize tại ranh giới API/message. Không nên nuốt exception rồi tạo object có trạng thái không hợp lệ.

## 10. Checklist lựa chọn nhanh

Trước khi đánh dấu constructor hoặc factory method bằng `@JsonCreator`, hãy tự trả lời:

1. JSON đầu vào là object có nhiều field hay là một giá trị hoàn chỉnh như string, number hoặc array?
2. Mỗi tham số creator tương ứng với một field riêng hay toàn bộ JSON được chuyển thành một tham số?
3. Nếu là property-based, tên từng tham số có được khai báo bằng `@JsonProperty` hoặc metadata được hỗ trợ không?
4. Nếu là delegating, kiểu tham số có thể nhận và biểu diễn toàn bộ giá trị JSON không?
5. Creator một tham số đã khai báo `Mode.PROPERTIES` hoặc `Mode.DELEGATING` rõ ràng chưa?
6. Chính sách field thiếu, null và giá trị mặc định có phù hợp với domain không?
7. Có constructor/factory method khác cũng được Jackson xem là creator không?
8. Đã kiểm tra deserialize bằng đúng `ObjectMapper` và cấu hình của ứng dụng chưa?

## Kết luận

Property-based creator nhận các giá trị theo tên field của JSON object và phù hợp với DTO bất biến có nhiều thuộc tính. Delegating creator nhận toàn bộ JSON như một đối số, phù hợp với value object hoặc kiểu tự diễn giải payload. Với constructor một tham số, hãy chỉ định mode rõ ràng để tránh phụ thuộc vào suy luận tên tham số và cấu hình. Khi đã xác định đúng hình dạng JSON, `@JsonCreator`, `@JsonProperty` cùng chính sách xử lý null giúp Jackson tạo object theo hợp đồng dữ liệu một cách nhất quán.
