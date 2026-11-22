# Xử lý nhiều constructor và phương thức tạo tĩnh

Một class Java có thể cung cấp nhiều constructor hoặc nhiều phương thức tạo tĩnh để tạo object theo những mục đích khác nhau. Khi Jackson đọc JSON, nó phải chọn một con đường cụ thể để tạo instance trước khi gán hoặc truyền các giá trị thuộc tính.

Nếu class có một constructor không tham số và một constructor nhiều tham số, hoặc có nhiều static factory method, việc chọn nhầm creator có thể khiến dữ liệu bị thiếu, giá trị mặc định được giữ lại hoặc Jackson báo lỗi không xác định được cách tạo object.

Trong Jackson, khái niệm quan trọng là **creator**: constructor hoặc static factory method được Jackson sử dụng để khởi tạo object trong quá trình deserialization. Có thể chỉ định creator bằng @JsonCreator và mô tả tham số bằng @JsonProperty. Khi class có nhiều cách tạo object, hãy chỉ rõ creator phù hợp với hợp đồng JSON thay vì dựa vào suy đoán.

## 1. Jackson tạo object như thế nào?

Khi đọc JSON thành Java object, Jackson cần tìm một cách tạo instance của kiểu đích. Tùy cấu trúc class và cấu hình, Jackson có thể sử dụng:

- Constructor không tham số, sau đó gán các thuộc tính qua setter hoặc field có thể truy cập.
- Constructor có tham số, nhận các giá trị thuộc tính từ JSON.
- Static factory method, nhận dữ liệu và trả về instance của kiểu đích.
- Builder, nếu class được cấu hình để Jackson tạo builder rồi gọi các phương thức thiết lập thuộc tính.

Luồng tổng quát:

~~~text
JSON input
    |
    v
Jackson đọc token và tên field
    |
    v
Xác định creator của kiểu Java
    |
    +---- Constructor không tham số
    |
    +---- Constructor có tham số
    |
    +---- Static factory method
    |
    +---- Builder
    |
    v
Tạo instance
    |
    v
Gán/hoàn thiện các thuộc tính
    |
    v
Java object
~~~

Đối với constructor hoặc factory có tham số, Jackson cần biết tham số nào tương ứng với field nào trong JSON. Annotation @JsonProperty thường được dùng để khai báo mối quan hệ này một cách rõ ràng.

Cần phân biệt hai chiều:

- Serialization: Jackson đọc object đã tồn tại và tìm cách biểu diễn các thuộc tính thành JSON.
- Deserialization: Jackson phải tạo object, chọn creator và cung cấp dữ liệu đầu vào.

Một getter có thể giúp Jackson serialize một thuộc tính nhưng không tự động giải quyết được việc gọi constructor nào khi deserialize.

## 2. @JsonCreator dùng để làm gì?

@JsonCreator đánh dấu constructor hoặc static factory method mà Jackson nên sử dụng làm creator khi deserialize.

Ví dụ class có nhiều constructor:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {

    private final String id;
    private final String name;

    public Customer() {
        this("UNKNOWN", "Guest");
    }

    @JsonCreator
    public Customer(
        @JsonProperty("id") String id,
        @JsonProperty("name") String name
    ) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

JSON:

~~~json
{
  "id": "C-100",
  "name": "Minh"
}
~~~

Jackson sử dụng constructor được đánh dấu @JsonCreator và truyền giá trị id, name tương ứng. Constructor không tham số vẫn có thể tồn tại cho mục đích khác, nhưng creator được chỉ định giúp đường đi khi deserialize rõ ràng.

Trong ví dụ này, class có field final nên việc khởi tạo qua constructor phù hợp với mô hình immutable. Object được tạo với đầy đủ giá trị ngay từ đầu.

### 2.1. @JsonProperty trên tham số creator

Với creator có nhiều tham số, hãy dùng @JsonProperty để xác định tên field JSON tương ứng:

~~~java
@JsonCreator
public Customer(
    @JsonProperty("customer_id") String id,
    @JsonProperty("display_name") String name
) {
    this.id = id;
    this.name = name;
}
~~~

JSON:

~~~json
{
  "customer_id": "C-100",
  "display_name": "Minh"
}
~~~

Tên tham số Java có thể khác tên field JSON. Đây là điểm hữu ích khi API dùng snake_case còn Java dùng camelCase.

Nếu không khai báo tên tham số rõ ràng, Jackson có thể cần metadata tên tham số từ compiler hoặc module hỗ trợ tương ứng. Cấu hình compiler với -parameters và sử dụng ParameterNamesModule có thể giúp Jackson suy ra tên tham số trong các trường hợp phù hợp. Tuy nhiên, annotation tường minh thường dễ đọc và ổn định hơn khi hợp đồng JSON quan trọng.

## 3. Các chế độ của @JsonCreator

@JsonCreator có thuộc tính mode để mô tả cách Jackson diễn giải tham số creator.

Ba mode cần biết:

| Mode | Ý nghĩa | Trường hợp điển hình |
|---|---|---|
| PROPERTIES | Mỗi tham số creator tương ứng với một thuộc tính JSON | Constructor/factory nhận nhiều field |
| DELEGATING | Toàn bộ giá trị JSON được chuyển cho một tham số creator | Wrapper quanh String, số, JsonNode hoặc kiểu khác |
| DISABLED | Không sử dụng creator được đánh dấu đó | Khi cần loại một creator khỏi quá trình lựa chọn |

Ngoài ra, mode mặc định là DEFAULT. Jackson sẽ áp dụng quy tắc suy luận phù hợp với creator và phiên bản đang sử dụng. Khi class có nhiều constructor/factory hoặc một tham số có thể được hiểu theo nhiều cách, nên chỉ định mode để tránh mơ hồ.

### 3.1. PROPERTIES: mỗi tham số là một thuộc tính JSON

Đây là cách phổ biến với immutable object có nhiều thuộc tính:

~~~java
public class Money {

    private final long amount;
    private final String currency;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
        @JsonProperty("amount") long amount,
        @JsonProperty("currency") String currency
    ) {
        this.amount = amount;
        this.currency = currency;
    }

    public long getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

JSON tương ứng:

~~~json
{
  "amount": 250000,
  "currency": "VND"
}
~~~

Jackson tìm hai thuộc tính amount và currency, chuyển đổi giá trị sang kiểu Java rồi truyền vào constructor.

PROPERTIES phù hợp khi JSON là một object có nhiều field và mỗi tham số creator đại diện cho một field. Tên tham số nên được khai báo rõ bằng @JsonProperty, đặc biệt khi tên JSON khác tên Java hoặc có nhiều creator.

### 3.2. DELEGATING: truyền toàn bộ giá trị JSON vào một tham số

DELEGATING phù hợp với value object được biểu diễn bằng một giá trị JSON đơn.

Ví dụ EmailAddress được biểu diễn bằng JSON string:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public final class EmailAddress {

    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public EmailAddress(String value) {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

JSON:

~~~json
"minh@example.com"
~~~

Jackson chuyển toàn bộ JSON string thành tham số value của constructor. @JsonValue chỉ định giá trị được dùng khi serialize object thành JSON.

Nếu dùng PROPERTIES trong trường hợp này, Jackson sẽ kỳ vọng một object có field tương ứng với tham số. Điều đó khác với hợp đồng JSON string đơn.

DELEGATING cũng có thể nhận JsonNode hoặc một kiểu đại diện cho toàn bộ cấu trúc JSON. Ví dụ một factory nhận JsonNode có thể tự đọc nhiều field và quyết định cách tạo object. Tuy nhiên, nếu cấu trúc đã ổn định và có nhiều field rõ ràng, PROPERTIES thường thể hiện hợp đồng dễ đọc hơn.

### 3.3. DEFAULT và trường hợp một tham số

Một creator chỉ có một tham số có thể gây mơ hồ:

- Tham số đại diện cho toàn bộ JSON value?
- Hay tham số tương ứng với một property bên trong JSON object?

Hãy chủ động chọn mode.

Ví dụ một value object nhận chuỗi:

~~~java
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public ProductCode(String value) {
    this.value = value;
}
~~~

Ví dụ một object nhận một property có tên code:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public ProductCode(
    @JsonProperty("code") String value
) {
    this.value = value;
}
~~~

Hai creator trên có hợp đồng JSON khác nhau:

~~~json
"SKU-100"
~~~

và:

~~~json
{
  "code": "SKU-100"
}
~~~

Không nên dựa vào suy luận của Jackson khi class có nhiều constructor hoặc factory method một tham số. Mode tường minh giúp code thể hiện chính xác cấu trúc JSON mong muốn.

## 4. Dùng static factory method làm creator

Java class có thể cung cấp static factory method thay cho constructor công khai. Factory method có thể đặt tên theo ý nghĩa nghiệp vụ, kiểm tra đầu vào hoặc trả về subtype phù hợp.

Jackson cho phép đánh dấu static factory method bằng @JsonCreator.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class PaymentStatus {

    private final String code;
    private final String description;

    private PaymentStatus(String code, String description) {
        this.code = code;
        this.description = description;
    }

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public static PaymentStatus fromJson(
        @JsonProperty("code") String code,
        @JsonProperty("description") String description
    ) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }

        return new PaymentStatus(code, description);
    }

    public String getCode() {
        return code;
    }

    public String getDescription() {
        return description;
    }
}
~~~

JSON:

~~~json
{
  "code": "PAID",
  "description": "Payment completed"
}
~~~

Jackson gọi fromJson thay vì constructor private. Factory method chịu trách nhiệm kiểm tra dữ liệu cơ bản và tạo instance.

Static factory có một số lợi thế:

- Tên method thể hiện mục đích tạo object.
- Constructor có thể để private hoặc package-private.
- Có thể chuẩn hóa dữ liệu trước khi tạo object.
- Có thể chọn implementation hoặc subtype theo discriminator nếu hợp đồng được thiết kế rõ.
- Có thể trả về instance đã được cache hoặc instance dùng chung nếu semantics cho phép.

Tuy nhiên, factory method không nên trở thành nơi chứa toàn bộ nghiệp vụ. Kiểm tra cú pháp và invariant của value object có thể nằm ở đây; kiểm tra quyền, trạng thái giao dịch hoặc gọi database vẫn thuộc tầng service/domain phù hợp.

### 4.1. Factory method nhận một giá trị đơn

Ví dụ một enum-like value object nhận chuỗi:

~~~java
public final class OrderState {

    private final String value;

    private OrderState(String value) {
        this.value = value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static OrderState fromValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("State is required");
        }
        return new OrderState(value);
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

JSON:

~~~json
"PROCESSING"
~~~

Factory method nhận toàn bộ JSON string. Khi serialize, @JsonValue xuất lại chuỗi tương ứng.

Nếu giá trị đầu vào có tập hữu hạn, hãy cân nhắc enum Java. Value object như trên phù hợp hơn khi tập giá trị có thể mở rộng hoặc cần biểu diễn các mã từ hệ thống ngoài.

## 5. Xử lý nhiều constructor trong cùng một class

Một class có thể có nhiều constructor phục vụ các cách tạo object khác nhau:

~~~java
public class UserProfile {

    private String id;
    private String name;
    private String locale;

    public UserProfile() {
        this.locale = "vi";
    }

    public UserProfile(String id, String name) {
        this(id, name, "vi");
    }

    public UserProfile(String id, String name, String locale) {
        this.id = id;
        this.name = name;
        this.locale = locale;
    }
}
~~~

Jackson có thể sử dụng constructor không tham số rồi gán thuộc tính nếu các thuộc tính có thể truy cập theo cấu hình. Nhưng nếu muốn deserialize bằng constructor nhiều tham số, hãy đánh dấu creator rõ ràng:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public UserProfile(
    @JsonProperty("id") String id,
    @JsonProperty("name") String name,
    @JsonProperty("locale") String locale
) {
    this.id = id;
    this.name = name;
    this.locale = locale;
}
~~~

Khi constructor nhiều tham số được chỉ định, Jackson có đường tạo object xác định. Tuy nhiên, cần quyết định rõ cách xử lý locale bị thiếu hoặc null. Nếu muốn dùng default locale khi JSON không có field, hãy triển khai quy tắc đó trong creator hoặc dùng một kiểu dữ liệu/adapter phù hợp.

### 5.1. Constructor không tham số và constructor có tham số

Nếu class có constructor không tham số cùng constructor có tham số, đừng giả định Jackson luôn chọn constructor có nhiều tham số nhất.

Cách chọn creator phụ thuộc annotation, khả năng suy luận tham số, visibility và cấu hình Jackson. Khi cần một constructor cụ thể, hãy đánh dấu @JsonCreator và @JsonProperty.

Nếu class dùng setter-based deserialization, constructor không tham số có thể là lựa chọn đơn giản. Nếu class immutable, constructor/factory có tham số thường phù hợp hơn vì các field final được khởi tạo ngay lúc tạo instance.

### 5.2. Nhiều constructor có cùng số tham số

Ví dụ:

~~~java
public class Coordinate {

    private final double latitude;
    private final double longitude;

    public Coordinate(double latitude, double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public Coordinate(String text) {
        String[] parts = text.split(",");
        this.latitude = Double.parseDouble(parts[0]);
        this.longitude = Double.parseDouble(parts[1]);
    }
}
~~~

Hai constructor có ý nghĩa đầu vào khác nhau:

- Constructor hai số tương ứng JSON object có latitude và longitude.
- Constructor chuỗi tương ứng JSON string như "10.7,106.6".

Không nên đánh dấu cả hai constructor là creator nếu cùng một kiểu đích không có cơ chế phân biệt rõ. Hãy chọn một hợp đồng JSON chính, hoặc dùng static factory/DTO adapter riêng cho từng biểu diễn.

Ví dụ chọn JSON object làm hợp đồng:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Coordinate(
    @JsonProperty("latitude") double latitude,
    @JsonProperty("longitude") double longitude
) {
    this.latitude = latitude;
    this.longitude = longitude;
}
~~~

Nếu hệ thống bên ngoài gửi chuỗi, hãy dùng adapter riêng để parse chuỗi thành Coordinate, thay vì khiến một class phải đoán nhiều hình dạng JSON.

## 6. Dùng @JsonCreator với Java record

Record phù hợp với DTO immutable. Record có canonical constructor tương ứng với các component được khai báo.

~~~java
public record Customer(
    String id,
    String name,
    String email
) {}
~~~

Trong các phiên bản Jackson 2 hiện đại có hỗ trợ record, Jackson có thể dùng canonical constructor để deserialize. Nếu hợp đồng JSON cần tên field khác component Java hoặc có nhiều cách tạo, có thể khai báo @JsonCreator và @JsonProperty tường minh:

~~~java
public record Customer(
    @JsonProperty("customer_id") String id,
    @JsonProperty("display_name") String name,
    String email
) {
    @JsonCreator
    public Customer {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("customer_id is required");
        }
    }
}
~~~

Compact canonical constructor vẫn là constructor của record. Nó phù hợp để kiểm tra invariant và chuẩn hóa giá trị trước khi record được tạo.

Không cần thêm constructor phụ chỉ để Jackson deserialize nếu canonical constructor đã đáp ứng hợp đồng. Nếu có nhiều factory method nghiệp vụ, hãy giữ chúng như API tạo object riêng và để creator JSON được xác định rõ.

## 7. Kết hợp constructor và static factory method

Một class có thể có nhiều cách tạo object cho code nghiệp vụ, nhưng chỉ nên có một đường deserialize JSON rõ ràng cho một hình dạng JSON.

Ví dụ:

~~~java
public final class Temperature {

    private final double celsius;

    private Temperature(double celsius) {
        if (celsius < -273.15) {
            throw new IllegalArgumentException("Below absolute zero");
        }
        this.celsius = celsius;
    }

    public static Temperature fromCelsius(double celsius) {
        return new Temperature(celsius);
    }

    public static Temperature fromFahrenheit(double fahrenheit) {
        return new Temperature((fahrenheit - 32) * 5 / 9);
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static Temperature fromJson(double celsius) {
        return fromCelsius(celsius);
    }

    @JsonValue
    public double toJson() {
        return celsius;
    }
}
~~~

JSON:

~~~json
25.0
~~~

Trong code nghiệp vụ, caller có thể chọn fromCelsius hoặc fromFahrenheit. Khi deserialize JSON, Jackson dùng creator fromJson đã được chỉ định. Hợp đồng JSON thống nhất biểu diễn nhiệt độ bằng độ Celsius.

Không đánh dấu tất cả factory method là @JsonCreator chỉ vì chúng đều có thể tạo object. Jackson cần một quy tắc lựa chọn xác định.

## 8. Khi nào nên dùng builder thay cho nhiều constructor?

Nếu class có rất nhiều thuộc tính tùy chọn, constructor nhiều tham số trở nên khó đọc:

~~~java
new SearchRequest(
    keyword,
    category,
    fromDate,
    toDate,
    page,
    size,
    sort,
    includeArchived
);
~~~

Builder làm rõ ý nghĩa từng thuộc tính và phù hợp với object có nhiều trường tùy chọn.

Jackson hỗ trợ builder thông qua @JsonDeserialize(builder = ...) và @JsonPOJOBuilder.

Ví dụ:

~~~java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonPOJOBuilder;

@JsonDeserialize(builder = SearchRequest.Builder.class)
public final class SearchRequest {

    private final String keyword;
    private final int page;
    private final int size;

    private SearchRequest(Builder builder) {
        this.keyword = builder.keyword;
        this.page = builder.page;
        this.size = builder.size;
    }

    public String getKeyword() {
        return keyword;
    }

    public int getPage() {
        return page;
    }

    public int getSize() {
        return size;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private String keyword;
        private int page = 0;
        private int size = 20;

        public Builder keyword(String keyword) {
            this.keyword = keyword;
            return this;
        }

        public Builder page(int page) {
            this.page = page;
            return this;
        }

        public Builder size(int size) {
            this.size = size;
            return this;
        }

        public SearchRequest build() {
            return new SearchRequest(this);
        }
    }
}
~~~

Với @JsonPOJOBuilder(withPrefix = ""), Jackson hiểu các method keyword(), page(), size() là phương thức thiết lập thuộc tính. Mặc định builder thường dùng prefix with, ví dụ withKeyword(); annotation giúp khai báo prefix thực tế.

Builder phù hợp khi:

- Có nhiều field tùy chọn.
- Cần giá trị mặc định.
- Muốn object immutable sau khi build.
- Muốn tránh constructor có quá nhiều tham số.
- Cần kiểm tra invariant ở build().

Nếu class chỉ có hai hoặc ba thuộc tính ổn định, constructor hoặc record có thể đơn giản hơn builder.

## 9. Xử lý tham số thiếu, null và giá trị mặc định

Creator có tham số phải đối mặt với ba tình huống khác nhau:

1. Field không xuất hiện trong JSON.
2. Field xuất hiện với giá trị null.
3. Field có giá trị nhưng không hợp lệ hoặc không chuyển đổi được.

Ví dụ JSON:

~~~json
{
  "id": "C-10",
  "name": null
}
~~~

Field id có mặt, name có mặt nhưng null. Nếu JSON chỉ chứa id, name lại là field bị thiếu. Hai tình huống này không phải lúc nào cũng tương đương.

Jackson có các cấu hình liên quan như:

- FAIL_ON_MISSING_CREATOR_PROPERTIES: báo lỗi khi thiếu creator property theo chính sách được cấu hình.
- FAIL_ON_NULL_CREATOR_PROPERTIES: báo lỗi khi creator property nhận null.
- @JsonProperty(required = true): đánh dấu property là bắt buộc trong metadata của creator/property; hành vi thực tế cần được kiểm tra cùng cấu hình deserialization.
- @JsonSetter(nulls = Nulls.SKIP/FAIL/...) hoặc Nulls.*: điều khiển cách xử lý null cho thuộc tính trong các trường hợp được hỗ trợ.

Ví dụ creator yêu cầu giá trị bắt buộc:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(
    @JsonProperty(value = "id", required = true) String id,
    @JsonProperty(value = "name", required = true) String name
) {
    if (id == null || id.isBlank()) {
        throw new IllegalArgumentException("id is required");
    }
    this.id = id;
    this.name = name;
}
~~~

Nếu muốn enforce thiếu/null ở cấp mapper, có thể bật feature tương ứng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
~~~

Cần lưu ý rằng bật feature toàn mapper có thể ảnh hưởng mọi creator được xử lý bằng mapper đó. Nếu chỉ một hợp đồng yêu cầu strict, hãy dùng mapper hoặc reader riêng và viết test cho cả field thiếu lẫn null.

Không nên dùng giá trị mặc định của Java như 0 hoặc false để âm thầm đại diện cho field bị thiếu nếu hợp đồng yêu cầu người gửi cung cấp dữ liệu. Với thuộc tính tùy chọn, hãy biểu diễn rõ bằng Optional, wrapper type, builder default hoặc quy tắc trong factory method.

## 10. Những lỗi thường gặp khi có nhiều creator

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Jackson không tìm được creator phù hợp | Nhiều constructor nhưng không có metadata đủ rõ | Chỉ định @JsonCreator và @JsonProperty |
| Creator có một tham số nhưng JSON không đúng hình dạng | Không phân biệt PROPERTIES và DELEGATING | Chọn mode rõ ràng, kiểm tra JSON contract |
| Có nhiều creator được đánh dấu | Jackson không có lựa chọn duy nhất hoặc cấu hình xung đột | Chỉ đánh dấu creator cho đường deserialize cần dùng |
| Constructor parameter không có tên | Compiler không giữ metadata và thiếu @JsonProperty | Khai báo tên property tường minh hoặc cấu hình ParameterNamesModule |
| Field bị null sau deserialize | Creator không nhận field hoặc dùng đường khởi tạo khác | Kiểm tra creator thực tế, tên JSON và setter/field visibility |
| Factory method không được gọi | Method không static, sai kiểu trả về hoặc annotation đặt không đúng | Dùng static factory trả về kiểu đích và đặt @JsonCreator |
| JSON string bị hiểu thành object | Creator mode không phù hợp | Dùng DELEGATING cho scalar hoặc PROPERTIES cho object |
| Builder không nhận field | Prefix method không khớp | Cấu hình @JsonPOJOBuilder(withPrefix = ...) |
| Thiếu field bị thay bằng giá trị mặc định | Creator/builder và feature missing/null chưa được xác định | Đặt chính sách required/default rõ ràng và test |

Khi gặp lỗi, hãy đọc phần thông báo Jackson về creator/property để xác định nó không biết cách tạo object, không tìm được tên tham số hay không chuyển đổi được giá trị. Đừng thêm constructor mới theo kiểu thử-và-sai vì có thể làm tăng số lựa chọn mơ hồ.

## 11. Kiểm thử creator và factory method

Mỗi kiểu có nhiều creator nên có test thể hiện đường tạo object được chọn.

Ví dụ kiểm tra constructor PROPERTIES:

~~~java
@Test
void shouldUsePropertiesCreator() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Money money = mapper.readValue(
        """
        {
          "amount": 250000,
          "currency": "VND"
        }
        """,
        Money.class
    );

    assertEquals(250000, money.getAmount());
    assertEquals("VND", money.getCurrency());
}
~~~

Ví dụ kiểm tra factory DELEGATING:

~~~java
@Test
void shouldUseDelegatingFactory() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    EmailAddress email = mapper.readValue(
        "\"minh@example.com\"",
        EmailAddress.class
    );

    assertEquals("minh@example.com", email.value());
}
~~~

Nên kiểm tra thêm:

- JSON object và JSON scalar có đúng hình dạng creator mong đợi không.
- Factory method có kiểm tra invariant không.
- Field thiếu và field null được xử lý đúng chính sách không.
- Constructor phụ có vô tình trở thành creator không mong muốn không.
- Serialization có tạo ra JSON tương thích với creator hay không.
- Các phiên bản Jackson được dự án hỗ trợ có cùng hành vi mong muốn không.

Một test round-trip chỉ xác nhận serialize rồi deserialize cùng một object có thể chưa đủ. Nếu cả serializer và deserializer cùng sai theo một cách, round-trip vẫn có thể thành công. Hãy thêm JSON mẫu cố định để bảo vệ hợp đồng thực tế.

## 12. Quy trình lựa chọn creator cho một class

Khi thiết kế class có nhiều constructor hoặc static factory, hãy thực hiện theo thứ tự:

1. Xác định hình dạng JSON: object, scalar hay cấu trúc lồng nhau.
2. Xác định constructor/factory nào tạo object hợp lệ từ dữ liệu đó.
3. Chọn PROPERTIES nếu tham số tương ứng với từng field; chọn DELEGATING nếu một tham số nhận toàn bộ JSON value.
4. Đặt @JsonCreator ở đúng một đường tạo object cho hợp đồng đó.
5. Dùng @JsonProperty để khai báo tên field cho creator có nhiều tham số hoặc khi cần tên rõ ràng.
6. Quy định rõ field thiếu, null và default.
7. Nếu có nhiều hợp đồng JSON, cân nhắc DTO hoặc adapter riêng thay vì làm creator đoán nhiều hình dạng.
8. Viết test bằng JSON mẫu độc lập và test round-trip.

## 13. Kết luận

Một class có thể có nhiều constructor và nhiều static factory method để phục vụ code nghiệp vụ. Nhưng khi Jackson deserialize, đường tạo object phải xác định và phù hợp với hình dạng JSON.

Dùng @JsonCreator để chọn constructor hoặc factory method, @JsonProperty để ánh xạ tham số với field, PROPERTIES cho JSON object có nhiều thuộc tính và DELEGATING cho một JSON value được chuyển vào một tham số. Khi class có nhiều field tùy chọn, builder có thể dễ bảo trì hơn constructor dài. Với record, canonical constructor thường đã đáp ứng nhu cầu và chỉ cần annotation khi hợp đồng yêu cầu tùy chỉnh.

Hãy giữ invariant trong constructor/factory, giữ hợp đồng JSON rõ ràng và kiểm thử đường tạo object thực tế. Điều đó giúp Jackson tạo được immutable object một cách nhất quán mà không phụ thuộc vào suy đoán khi class có nhiều cách khởi tạo.

