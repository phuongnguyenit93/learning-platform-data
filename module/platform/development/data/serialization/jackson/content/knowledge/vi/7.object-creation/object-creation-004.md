# Gắn tên tham số constructor với thuộc tính JSON

Một class Java không nhất thiết phải có constructor không tham số và setter để Jackson tạo object. Với class bất biến, dữ liệu thường được đưa vào qua constructor: mỗi tham số nhận một giá trị, sau đó constructor gán giá trị vào các field final.

Để thực hiện việc này, Jackson cần biết tham số constructor nào tương ứng với thuộc tính JSON nào. Annotation @JsonCreator xác định constructor hoặc factory method được dùng để tạo object; @JsonProperty gắn tên thuộc tính JSON với từng tham số. Khi tên Java và tên JSON khác nhau, annotation này tạo ra mối liên hệ rõ ràng giữa hai phía.

Đây là kỹ thuật quan trọng khi ánh xạ JSON vào DTO bất biến, value object, record hoặc các kiểu không cho phép thay đổi trạng thái sau khi tạo.

## 1. Vì sao Jackson cần biết tên tham số constructor?

Giả sử JSON đầu vào là:

~~~json
{
  "customer_id": "CUS-100",
  "display_name": "Linh"
}
~~~

Trong Java, ta muốn dùng tên thuộc tính theo quy ước camelCase:

~~~java
public final class CustomerRequest {
    private final String customerId;
    private final String displayName;

    public CustomerRequest(String customerId, String displayName) {
        this.customerId = customerId;
        this.displayName = displayName;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Constructor yêu cầu hai giá trị, nhưng JSON lại dùng customer_id và display_name. Jackson cần xác định:

- Tham số customerId nhận giá trị từ thuộc tính customer_id.
- Tham số displayName nhận giá trị từ thuộc tính display_name.

Jackson không thể chỉ dựa vào thứ tự các thuộc tính trong JSON. JSON object không yêu cầu thứ tự field cố định, vì vậy client có thể gửi display_name trước customer_id mà kết quả vẫn phải giống nhau.

Nếu không có thông tin tên tham số hoặc annotation creator phù hợp, Jackson có thể không tìm được cách gọi constructor và báo lỗi kiểu không có creator phù hợp hoặc không xác định được tên property cho tham số.

## 2. Dùng @JsonCreator và @JsonProperty

Cách tường minh và dễ kiểm soát nhất là đánh dấu constructor bằng @JsonCreator và đánh dấu từng tham số bằng @JsonProperty.

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class CustomerRequest {
    private final String customerId;
    private final String displayName;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public CustomerRequest(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("display_name") String displayName
    ) {
        this.customerId = customerId;
        this.displayName = displayName;
    }

    @JsonProperty("customer_id")
    public String getCustomerId() {
        return customerId;
    }

    @JsonProperty("display_name")
    public String getDisplayName() {
        return displayName;
    }
}
~~~

@JsonCreator(mode = JsonCreator.Mode.PROPERTIES) cho Jackson biết constructor này được gọi bằng cách lấy từng giá trị từ thuộc tính của JSON object.

@JsonProperty("customer_id") trên tham số constructor xác định tên field đầu vào tương ứng. Tên tham số Java có thể là customerId, nhưng tên trên JSON vẫn là customer_id.

Các annotation trên getter xác định tên thuộc tính khi serialize object trở lại JSON. Việc khai báo rõ cả hai chiều làm hợp đồng dễ đọc và tránh phụ thuộc vào quy tắc đặt tên mặc định.

Đọc JSON:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "customer_id": "CUS-100",
      "display_name": "Linh"
    }
    """;

CustomerRequest request =
    mapper.readValue(json, CustomerRequest.class);
~~~

Ghi lại JSON:

~~~java
String output = mapper.writeValueAsString(request);
~~~

Kết quả dùng lại tên wire customer_id và display_name như đã khai báo.

## 3. @JsonCreator xác định cách tạo object

@JsonCreator có các chế độ chính:

| Mode | Ý nghĩa |
|---|---|
| PROPERTIES | Lấy các thuộc tính từ JSON object và truyền từng giá trị vào tham số constructor hoặc factory method. |
| DELEGATING | Chuyển toàn bộ giá trị JSON gốc cho một tham số của creator. |
| DEFAULT | Để Jackson áp dụng quy tắc suy luận mặc định dựa trên creator và metadata. |

Với constructor nhiều tham số, chế độ PROPERTIES thường là lựa chọn rõ ràng:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public CustomerRequest(
    @JsonProperty("customer_id") String customerId,
    @JsonProperty("display_name") String displayName
) {
    this.customerId = customerId;
    this.displayName = displayName;
}
~~~

JSON tương ứng là một object có các thuộc tính:

~~~json
{
  "customer_id": "CUS-100",
  "display_name": "Linh"
}
~~~

Jackson tìm từng property theo tên rồi gọi constructor với các giá trị đã ánh xạ. Thứ tự thuộc tính trong JSON không quyết định thứ tự tham số constructor.

### Property-based creator và delegating creator khác nhau

Một constructor có một tham số vẫn có thể có hai ý nghĩa khác nhau.

Nếu constructor nhận một object JSON có thuộc tính value:

~~~java
public final class CustomerCodeRequest {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public CustomerCodeRequest(
        @JsonProperty("value") String value
    ) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

JSON đầu vào phải có dạng:

~~~json
{ "value": "CUS-100" }
~~~

Nếu constructor nhận trực tiếp một chuỗi JSON:

~~~java
public final class CustomerCode {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public CustomerCode(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

JSON đầu vào có dạng:

~~~json
"CUS-100"
~~~

Ở chế độ DELEGATING, Jackson đưa toàn bộ root value vào tham số duy nhất. Ở chế độ PROPERTIES, Jackson tìm property trong object rồi truyền giá trị của property đó vào tham số.

Khi constructor chỉ có một tham số, hãy chọn mode theo hình dạng JSON mà hợp đồng yêu cầu. Việc ghi rõ mode giúp tránh phụ thuộc vào quy tắc suy luận có thể khác giữa các phiên bản hoặc cấu hình.

## 4. Tên tham số Java và tên thuộc tính JSON không bắt buộc giống nhau

Tên tham số constructor là tên trong mã nguồn Java. Tên thuộc tính JSON là tên wire mà hai hệ thống trao đổi. Hai tên này có thể khác nhau:

| Tham số Java | Thuộc tính JSON |
|---|---|
| customerId | customer_id |
| displayName | display_name |
| createdAt | created_at |
| orderNumber | order_no |

@JsonProperty cho phép công bố tên JSON ổn định mà không phải đổi tên biến Java hoặc tên field trong domain model.

Điều này đặc biệt hữu ích khi:

- API cũ dùng snake_case nhưng code Java dùng camelCase.
- Tên JSON là một phần hợp đồng công khai và không thể tùy ý đổi.
- Domain model có tên nội bộ khác với thuật ngữ bên ngoài.
- Một ứng dụng tích hợp với hệ thống có quy tắc đặt tên riêng.

Có thể dùng @JsonNaming hoặc naming strategy toàn cục để chuyển đổi quy tắc tên, ví dụ camelCase sang snake_case. Tuy nhiên, @JsonProperty phù hợp khi một thuộc tính có tên wire cụ thể cần được giữ ổn định.

Nếu cần chấp nhận nhiều tên cũ khi đọc nhưng chỉ phát ra một tên chuẩn khi ghi, có thể xem xét @JsonAlias trên thuộc tính. Alias chủ yếu hỗ trợ deserialization; tên chuẩn khi serialize vẫn được quyết định bởi property chính.

## 5. Không phụ thuộc vào thứ tự thuộc tính JSON

JSON object là tập hợp các cặp tên và giá trị. Hai nội dung sau tương đương về mặt cấu trúc:

~~~json
{
  "customer_id": "CUS-100",
  "display_name": "Linh"
}
~~~

~~~json
{
  "display_name": "Linh",
  "customer_id": "CUS-100"
}
~~~

Với property-based creator, Jackson gắn giá trị theo tên property. Cả hai input đều phải tạo ra cùng một object.

Đây là lý do không nên thiết kế constructor binding theo suy nghĩ “tham số thứ nhất lấy giá trị đầu tiên trong JSON, tham số thứ hai lấy giá trị thứ hai”. JSON object không phải một danh sách positional arguments.

Tên property phải khớp với hợp đồng. Nếu JSON gửi customerId trong khi constructor chờ customer_id, Jackson không tự coi hai tên đó là một nếu không có naming strategy hoặc alias phù hợp.

## 6. Suy luận tên tham số từ metadata của Java

Không phải lúc nào cũng cần ghi @JsonProperty cho mọi tham số. Java có thể lưu tên tham số trong bytecode khi biên dịch với tùy chọn -parameters. Jackson có module hỗ trợ đọc metadata này: jackson-module-parameter-names.

Khai báo dependency, để BOM đang dùng quản lý phiên bản:

~~~groovy
dependencies {
    implementation "com.fasterxml.jackson.module:jackson-module-parameter-names"
}
~~~

Bật lưu tên tham số khi biên dịch bằng Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đăng ký module:

~~~java
import com.fasterxml.jackson.module.paramnames.ParameterNamesModule;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new ParameterNamesModule())
    .build();
~~~

Sau đó, tên tham số có thể được suy ra từ constructor:

~~~java
public final class CustomerRequest {
    private final String customerId;
    private final String displayName;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public CustomerRequest(String customerId, String displayName) {
        this.customerId = customerId;
        this.displayName = displayName;
    }
}
~~~

Trong ví dụ này, tên wire mặc định tương ứng là customerId và displayName, trừ khi naming strategy hoặc annotation khác thay đổi cách đặt tên.

Có ba điều kiện cần phân biệt:

1. Compiler phải giữ tên tham số bằng -parameters.
2. Module parameter names phải có trên classpath và được đăng ký hoặc được framework phát hiện theo cấu hình.
3. Jackson phải xác định constructor là creator phù hợp; ghi rõ @JsonCreator làm ý định này tường minh.

Nếu thiếu -parameters, reflection có thể chỉ trả về tên dạng arg0, arg1 thay vì tên trong source. Module không thể khôi phục tên đã bị mất khỏi bytecode.

Suy luận tên tham số thuận tiện khi tên Java và tên JSON giống nhau. Khi tên wire khác tên Java hoặc là hợp đồng cần ổn định độc lập với quá trình biên dịch, @JsonProperty tường minh thường an toàn hơn.

## 7. Constructor binding với Java record

Record được thiết kế để biểu diễn dữ liệu bất biến. Các thành phần record đồng thời xác định state, accessor và canonical constructor.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerRequest(
    @JsonProperty("customer_id") String customerId,
    @JsonProperty("display_name") String displayName
) {}
~~~

Jackson hỗ trợ Java record từ dòng Jackson 2.12 trở lên. Với phiên bản hỗ trợ record, Jackson có thể sử dụng canonical constructor và tên record component để tạo object.

Khi tên component trùng tên JSON, annotation có thể không cần thiết. Khi wire name khác component name, @JsonProperty giúp ánh xạ rõ ràng.

Đọc JSON:

~~~java
CustomerRequest request = mapper.readValue(
    """
    {
      "customer_id": "CUS-100",
      "display_name": "Linh"
    }
    """,
    CustomerRequest.class
);
~~~

Record giảm lượng code constructor và accessor, nhưng nguyên tắc binding không thay đổi: Jackson vẫn cần biết cách ánh xạ các property JSON vào tham số canonical constructor.

Khi dùng Jackson cũ hơn 2.12, không nên giả định record được hỗ trợ như các phiên bản mới. Hãy kiểm tra phiên bản thực tế và nâng cấp cả bộ dependency theo BOM phù hợp nếu cần.

## 8. Xử lý tham số bị thiếu và giá trị null

Gắn tên tham số với property chỉ giải quyết việc ánh xạ. Nó không tự xác định dữ liệu có hợp lệ hay không.

Ví dụ JSON thiếu display_name:

~~~json
{
  "customer_id": "CUS-100"
}
~~~

Và JSON có display_name nhưng giá trị null:

~~~json
{
  "customer_id": "CUS-100",
  "display_name": null
}
~~~

Hai trường hợp khác nhau:

- **Thiếu property**: producer không gửi trường.
- **Null**: producer gửi trường và giá trị của nó là null.

Có thể đánh dấu creator property là bắt buộc:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public CustomerRequest(
    @JsonProperty(value = "customer_id", required = true)
    String customerId,

    @JsonProperty(value = "display_name", required = true)
    String displayName
) {
    this.customerId = customerId;
    this.displayName = displayName;
}
~~~

required = true thể hiện yêu cầu property phải xuất hiện đối với creator property. Cấu hình FAIL_ON_MISSING_CREATOR_PROPERTIES cũng có thể được dùng để yêu cầu các creator property không bị thiếu.

Ví dụ:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .build();
~~~

Việc property có xuất hiện nhưng mang null là một quy tắc khác. Có thể xem xét FAIL_ON_NULL_CREATOR_PROPERTIES hoặc @JsonSetter(nulls = Nulls.FAIL) tùy cách mô hình hóa và phiên bản Jackson. Với giá trị chuỗi, validation như @NotBlank còn kiểm tra cả chuỗi rỗng hoặc chỉ chứa khoảng trắng.

Jackson tạo object không có nghĩa dữ liệu đã hợp lệ theo nghiệp vụ. Nếu customerId không được rỗng, cần validation rõ ràng ở tầng phù hợp, ví dụ Bean Validation hoặc kiểm tra trong constructor/domain model.

## 9. Constructor nhiều tham số, constructor overload và factory method

Một class có thể có nhiều constructor:

~~~java
public final class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount) {
        this(amount, "VND");
    }

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }
}
~~~

Khi deserialize, Jackson cần biết constructor nào là creator. Nếu có nhiều constructor, không nên để việc chọn constructor phụ thuộc vào suy luận không rõ ràng.

Đánh dấu constructor phù hợp:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Money(
    @JsonProperty("amount") BigDecimal amount,
    @JsonProperty("currency") String currency
) {
    this.amount = amount;
    this.currency = currency;
}
~~~

Hoặc dùng static factory method:

~~~java
public final class Money {
    private final BigDecimal amount;
    private final String currency;

    private Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public static Money create(
        @JsonProperty("amount") BigDecimal amount,
        @JsonProperty("currency") String currency
    ) {
        return new Money(amount, currency);
    }
}
~~~

Factory method hữu ích khi việc tạo object cần kiểm tra điều kiện, chuẩn hóa giá trị hoặc che giấu constructor. Jackson gọi phương thức được đánh dấu để nhận object.

Không đánh dấu nhiều creator cạnh tranh cho cùng một kiểu nếu Jackson không thể phân biệt rõ. Nếu có nhiều cách biểu diễn JSON hợp lệ, hãy thiết kế creator và mode rõ ràng, rồi kiểm tra từng dạng input bằng test.

## 10. Naming strategy và alias

Một mapper có thể dùng naming strategy để chuyển tên property Java sang tên JSON:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Với kiểu Java có thuộc tính customerId, naming strategy có thể tạo tên JSON customer_id.

Khi tham số constructor dựa trên tên suy luận, naming strategy cũng tham gia quá trình xác định tên property theo cấu hình mapper. Nếu hợp đồng yêu cầu một tên đặc biệt hoặc không theo quy tắc chung, khai báo @JsonProperty trực tiếp trên tham số creator giúp ý định rõ ràng hơn.

Nếu cần đọc cả tên cũ và tên mới trong giai đoạn chuyển đổi, có thể dùng alias:

~~~java
public record CustomerRequest(
    @JsonProperty("customer_id")
    @JsonAlias("customerId")
    String customerId
) {}
~~~

Trong ví dụ này, customer_id là tên chuẩn để serialize; customerId là tên bổ sung được chấp nhận khi deserialize. Chỉ thêm alias khi hợp đồng cần hỗ trợ producer cũ. Nếu giữ alias vô thời hạn, ứng dụng sẽ phải tiếp tục hỗ trợ nhiều dạng payload hơn.

## 11. Kiểm tra constructor binding bằng unit test

Test nên kiểm tra ít nhất ba điều:

- Tên JSON khác tên tham số Java vẫn được ánh xạ đúng.
- Thứ tự property trong object không ảnh hưởng đến kết quả.
- Serialize lại dùng tên wire đã công bố.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class CustomerRequestTest {

    record CustomerRequest(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("display_name") String displayName
    ) {}

    private final ObjectMapper mapper = JsonMapper.builder().build();

    @Test
    void bindsConstructorParametersByJsonPropertyName() throws Exception {
        String json = """
            {
              "display_name": "Linh",
              "customer_id": "CUS-100"
            }
            """;

        CustomerRequest request =
            mapper.readValue(json, CustomerRequest.class);

        assertEquals("CUS-100", request.customerId());
        assertEquals("Linh", request.displayName());
    }

    @Test
    void serializesUsingTheDeclaredWireNames() throws Exception {
        CustomerRequest request =
            new CustomerRequest("CUS-100", "Linh");

        String json = mapper.writeValueAsString(request);

        assertEquals(
            mapper.readTree("""
                {
                  "customer_id": "CUS-100",
                  "display_name": "Linh"
                }
                """),
            mapper.readTree(json)
        );
    }
}
~~~

Ví dụ dùng record để test ngắn gọn; Jackson cần phiên bản có hỗ trợ record. Với class thông thường, giữ nguyên nguyên tắc: đánh dấu creator và từng tham số, sau đó kiểm tra getter hoặc property output.

Nếu class có constructor overload, hãy bổ sung test xác nhận đúng creator được gọi. Nếu có tham số bắt buộc hoặc không cho phép null, hãy test riêng trường bị thiếu và trường null để bảo đảm chính sách được thực thi.

## 12. Khi gặp lỗi Jackson không tạo được object

Một số thông báo thường gặp:

- Cannot construct instance ... no Creators, like default constructor, exist: Jackson không tìm thấy creator phù hợp để tạo object.
- Argument ... has no property name: constructor có nhiều tham số nhưng Jackson không biết tên property để gắn với từng tham số.
- Missing required creator property: JSON thiếu một property được đánh dấu bắt buộc hoặc cấu hình reader yêu cầu.
- ValueInstantiationException: constructor hoặc factory method được gọi nhưng phát sinh exception trong quá trình tạo object.

Cách xử lý nên bắt đầu từ nguyên nhân cụ thể:

1. Xác định JSON đầu vào có đúng hình dạng object hoặc scalar mà creator mong đợi không.
2. Kiểm tra @JsonCreator đã đánh dấu đúng constructor hoặc factory method chưa.
3. Kiểm tra từng tham số có @JsonProperty đúng tên wire chưa.
4. Nếu dựa vào tên tham số tự suy luận, xác nhận compiler có -parameters và module parameter names đã được đăng ký.
5. Kiểm tra constructor có ném exception do validation hoặc dữ liệu không hợp lệ không.
6. Kiểm tra phiên bản Jackson và module hỗ trợ đang dùng có tương thích không.

Không nên thêm constructor không tham số và setter chỉ để làm biến mất lỗi nếu mục tiêu thiết kế là class bất biến. Hãy xác định creator là phần của hợp đồng deserialize và cấu hình nó một cách tường minh.

## Kết luận

Jackson có thể tạo object bất biến bằng cách gọi constructor hoặc factory method. @JsonCreator xác định creator được chọn, còn @JsonProperty gắn từng tham số với tên thuộc tính JSON. Nhờ đó, tên Java có thể khác tên wire và việc ánh xạ không phụ thuộc thứ tự field trong JSON object.

Khi tên tham số được suy luận từ bytecode, cần lưu metadata bằng -parameters và đăng ký ParameterNamesModule; với hợp đồng công khai hoặc tên wire khác quy ước Java, annotation tường minh thường dễ kiểm soát hơn. Hãy kiểm tra cả dữ liệu thiếu, null, constructor overload và JSON serialize ngược để bảo đảm hai chiều trao đổi nhất quán.

