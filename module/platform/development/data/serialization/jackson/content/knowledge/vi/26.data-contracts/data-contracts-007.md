# Quản lý loại bỏ trường và thay đổi kiểu dữ liệu

## 1. Vì sao thay đổi schema JSON cần kế hoạch?

JSON thường được trao đổi giữa nhiều thành phần có vòng đời phát hành độc lập: ứng dụng mobile, backend, worker, dịch vụ tích hợp, file lưu trữ và message broker. Khi một phiên bản producer thay đổi tên field, bỏ field hoặc đổi kiểu dữ liệu, consumer cũ có thể không còn đọc được payload.

Jackson ánh xạ JSON vào Java theo tên property, kiểu Java, annotation và cấu hình của ObjectMapper. Vì vậy, một thay đổi nhỏ trong JSON có thể ảnh hưởng đến:

- Deserialization của consumer đang chạy phiên bản cũ.
- Serialization của producer mới.
- Dữ liệu JSON đã lưu từ nhiều tháng hoặc nhiều năm trước.
- Gateway đọc rồi ghi lại payload.
- Các job replay message hoặc khôi phục dữ liệu từ backup.
- Các client không thể nâng cấp đồng thời với server.

Quản lý schema evolution là quá trình thay đổi hợp đồng theo từng bước để producer và consumer vẫn giao tiếp được trong giai đoạn chuyển tiếp. Cần xem xét cả hai chiều:

- **Đọc:** phiên bản ứng dụng hiện tại có thể đọc JSON được tạo bởi phiên bản trước hoặc phiên bản sau không?
- **Ghi:** JSON do phiên bản hiện tại tạo ra có còn được consumer cũ chấp nhận không?

Không nên xem việc đổi tên field trong một lớp Java là refactor nội bộ nếu tên field đó xuất hiện trong JSON. Khi tên hoặc kiểu JSON thay đổi, đó là thay đổi hợp đồng dữ liệu.

## 2. Phân biệt thay đổi cộng thêm và thay đổi phá vỡ tương thích

Một số thay đổi thường ít rủi ro hơn nếu consumer được thiết kế để chấp nhận chúng:

- Thêm field tùy chọn.
- Thêm một giá trị mặc định cho field mới khi field không xuất hiện.
- Bổ sung alias để đọc tên cũ và tên mới.
- Ngừng phát một field sau khi consumer đã ngừng phụ thuộc vào nó.

Những thay đổi sau thường có nguy cơ phá vỡ tương thích:

- Xóa field mà consumer cũ yêu cầu.
- Đổi tên field nhưng không còn chấp nhận tên cũ.
- Đổi kiểu JSON, ví dụ number thành object hoặc string thành array.
- Đổi đơn vị hoặc ý nghĩa nghiệp vụ trong khi giữ nguyên tên và kiểu.
- Làm field tùy chọn trở thành bắt buộc mà không có giai đoạn chuyển tiếp.
- Đổi cấu trúc từ object thành array hoặc ngược lại.

Một thay đổi có thể tương thích với consumer mới nhưng không tương thích với consumer cũ. Vì vậy, cần đánh giá producer và consumer riêng, thay vì chỉ kiểm tra một chiều.

## 3. Ma trận tương thích giữa reader và writer

Giả sử có hai phiên bản hợp đồng: V1 và V2. Writer là thành phần tạo JSON; reader là thành phần đọc JSON.

| Writer | Reader | Câu hỏi cần kiểm tra |
|---|---|---|
| V1 | V1 | Hành vi hiện tại có còn đúng không? |
| V1 | V2 | Reader mới có đọc được dữ liệu cũ và gán default phù hợp không? |
| V2 | V1 | Reader cũ có chấp nhận field mới, tên mới hoặc kiểu mới không? |
| V2 | V2 | Hành vi mới có đúng hợp đồng không? |

Một số thuật ngữ hữu ích:

- **Backward compatibility:** reader mới đọc được dữ liệu do writer cũ tạo.
- **Forward compatibility:** reader cũ có thể đọc dữ liệu do writer mới tạo, thường cần bỏ qua hoặc giữ lại thông tin mới mà nó chưa biết.
- **Full compatibility:** cả hai chiều đều được hỗ trợ trong phạm vi thay đổi đã định nghĩa.

Ví dụ, thêm một field optional có thể backward-compatible nếu reader mới xử lý được trường hợp field bị thiếu. Nhưng nếu reader cũ bật strict unknown-property handling, writer mới phát field đó có thể làm reader cũ thất bại. Khi đó thay đổi chưa forward-compatible.

## 4. Thêm field mới một cách an toàn

Giả sử V1 có:

~~~json
{
  "id": "P-100",
  "name": "Keyboard"
}
~~~

V2 bổ sung category:

~~~json
{
  "id": "P-100",
  "name": "Keyboard",
  "category": "ACCESSORY"
}
~~~

DTO Java mới:

~~~java
public class Product {
    private String id;
    private String name;
    private String category = "GENERAL";

    // getters/setters
}
~~~

Với bean mutable và property bị thiếu, Jackson thường không gọi setter của property đó; initializer category có thể được giữ nguyên. Vì vậy, reader V2 có thể đọc payload V1 và nhận category GENERAL.

Tuy nhiên, nếu dùng constructor hoặc record, cần xem xét cách Jackson tạo object khi tham số bị thiếu. Các feature như FAIL_ON_MISSING_CREATOR_PROPERTIES và quy tắc creator có thể khiến payload cũ không đọc được nếu field mới bị xem là bắt buộc.

Một field mới nên được thiết kế như optional trong giai đoạn chuyển tiếp:

- Chọn default có ý nghĩa nghiệp vụ.
- Không dùng null để thay thế default nếu null mang ý nghĩa khác.
- Đảm bảo consumer cũ xử lý unknown field theo chính sách phù hợp.
- Chỉ bắt buộc field sau khi producer và consumer cần thiết đã được nâng cấp.

Không nên thêm một field bắt buộc rồi giả định mọi dữ liệu cũ sẽ tự có giá trị.

## 5. Đổi tên field bằng @JsonAlias

Jackson cung cấp annotation @JsonAlias để chấp nhận một hoặc nhiều tên thay thế khi deserialize:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {
    @JsonProperty("displayName")
    @JsonAlias({"name", "full_name"})
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Jackson có thể đọc cả ba tên:

~~~json
{"displayName": "Lan"}
~~~

~~~json
{"name": "Lan"}
~~~

~~~json
{"full_name": "Lan"}
~~~

Khi serialize, tên property chính được chọn bởi @JsonProperty là displayName. Alias chỉ phục vụ chiều đọc; nó không làm Jackson phát ra tất cả tên cũ.

Đây là một cách triển khai **dual-read, single-write**:

- Reader chấp nhận tên cũ và tên mới.
- Writer chỉ phát một tên canonical mới.

Cách này giúp dữ liệu cũ tiếp tục được đọc trong khi producer dần chuyển sang tên mới.

### Không nhầm @JsonAlias với đổi tên Java property

Đổi tên field Java từ name sang displayName không tự bảo đảm JSON cũ vẫn được đọc. Nếu hợp đồng trước đó dùng name, cần alias hoặc một cơ chế migration tương đương.

Nếu chỉ dùng:

~~~java
@JsonProperty("displayName")
private String displayName;
~~~

thì tên name không tự trở thành alias. Payload cũ có thể bị xem là unknown property khi strict mode được bật, hoặc bị bỏ qua khi mapper được cấu hình tolerant.

## 6. Xử lý khi payload gửi đồng thời tên cũ và tên mới

Trong giai đoạn migration, có thể gặp payload chứa cả hai tên:

~~~json
{
  "name": "Lan",
  "displayName": "Lan Nguyen"
}
~~~

Không nên dựa vào thứ tự property trong JSON để định nghĩa giá trị thắng. Nếu cả hai tên cùng ánh xạ vào một property, kết quả có thể phụ thuộc thứ tự xuất hiện và đường binding cụ thể.

Hợp đồng nên quy định rõ một trong các lựa chọn:

- Producer chỉ được gửi một trong hai tên.
- Nếu gửi cả hai, giá trị phải giống nhau.
- Nếu gửi cả hai với giá trị khác nhau, từ chối payload.

Nếu cần từ chối trường hợp trùng tên, có thể đọc qua JsonNode trước khi bind hoặc viết custom deserializer/validation ở tầng DTO để kiểm tra presence của cả hai key.

Ví dụ kiểm tra trước:

~~~java
JsonNode root = mapper.readTree(json);

if (root.has("name") && root.has("displayName")) {
    throw new IllegalArgumentException(
            "Send either name or displayName, not both"
    );
}

Customer customer = mapper.treeToValue(root, Customer.class);
~~~

Đây là cách rõ ràng khi xung đột tên có ý nghĩa nghiệp vụ. Với payload lớn hoặc streaming, có thể thực hiện kiểm tra khi duyệt token thay vì dựng toàn bộ cây.

## 7. Bỏ field khỏi JSON output nhưng vẫn đọc dữ liệu cũ

Đôi khi ứng dụng muốn ngừng phát một field nhưng vẫn cần đọc field đó từ dữ liệu cũ. Có thể dùng JsonProperty.Access hoặc JsonIgnoreProperties tùy mục tiêu.

### WRITE_ONLY và READ_ONLY

JsonProperty.Access điều khiển hướng truy cập:

| Access | Serialization | Deserialization |
|---|---|---|
| AUTO | Theo visibility và cấu hình thông thường | Theo visibility và cấu hình thông thường |
| READ_ONLY | Có thể serialize property | Không dùng input để ghi property |
| WRITE_ONLY | Không serialize property | Cho phép đọc từ JSON vào property |
| READ_WRITE | Cho phép cả hai chiều | Cho phép cả hai chiều |

Ví dụ field legacy chỉ còn được đọc:

~~~java
public class Customer {
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String legacyCode;

    // getter/setter
}
~~~

Tên WRITE_ONLY được hiểu theo góc nhìn property Java: property có thể được ghi vào object khi deserialize nhưng không được xuất ra khi serialize. Điều này phù hợp với field cũ cần nhận trong giai đoạn migration nhưng không muốn tiếp tục phát.

Ngược lại, READ_ONLY phù hợp với giá trị do server tạo và chỉ gửi ra client, chẳng hạn computed status hoặc server-generated identifier.

### JsonIgnoreProperties với allowGetters/allowSetters

Có thể bỏ qua field theo tên:

~~~java
@JsonIgnoreProperties(
        value = {"legacyCode"},
        allowSetters = true
)
public class Customer {
    private String legacyCode;
}
~~~

allowSetters = true cho phép chiều setter/deserialization đối với property bị liệt kê, trong khi property vẫn bị bỏ qua khi serialize. Đây là một cách giữ khả năng đọc nhưng ngừng phát field.

allowGetters = true có ý nghĩa ngược lại: cho phép getter/serialization của property bị liệt kê, trong khi chiều setter/deserialization bị bỏ qua.

Hãy chọn một cơ chế nhất quán cho DTO. Tránh gắn @JsonIgnore, @JsonProperty(access=...) và @JsonIgnoreProperties chồng chéo lên cùng property mà không kiểm thử thứ tự và metadata hiệu lực.

## 8. Bỏ field hoàn toàn bằng @JsonIgnore

Nếu một property không còn thuộc hợp đồng ở cả hai chiều, có thể dùng @JsonIgnore:

~~~java
public class Customer {
    private String id;

    @JsonIgnore
    private String internalMemo;
}
~~~

Property internalMemo không được serialize và không được deserialize theo cấu hình thông thường.

Tuy nhiên, @JsonIgnore không phải công cụ migration nếu vẫn cần đọc dữ liệu legacy. Khi cần chấp nhận field cũ nhưng không phát field đó, hãy dùng WRITE_ONLY hoặc ignore property theo hướng phù hợp.

Ngoài ra, nếu dữ liệu cũ có field đã bị @JsonIgnore, strict unknown-property handling và metadata ignore có thể ảnh hưởng cách Jackson xử lý field đó. Hãy kiểm thử đúng payload cũ và cấu hình mapper thực tế.

## 9. Loại bỏ field theo từng giai đoạn

Một field không nên bị xóa đột ngột nếu có nhiều producer/consumer hoặc dữ liệu lưu trữ dài hạn. Một quy trình an toàn có thể gồm:

~~~text
Giai đoạn 1: Công bố field mới
      |
      v
Giai đoạn 2: Reader chấp nhận cả tên/field cũ và mới
      |
      v
Giai đoạn 3: Writer chuyển sang chỉ phát field mới
      |
      v
Giai đoạn 4: Theo dõi consumer và dữ liệu còn dùng field cũ
      |
      v
Giai đoạn 5: Ngừng đọc field cũ sau thời hạn hỗ trợ
      |
      v
Giai đoạn 6: Xóa mapping legacy và dọn dữ liệu đã migrate
~~~

Ví dụ đổi name thành displayName:

1. Thêm displayName vào hợp đồng mới.
2. Consumer mới dùng @JsonAlias("name") để đọc cả hai.
3. Producer bắt đầu phát displayName.
4. Theo dõi log/metric để biết còn payload name hay không.
5. Sau khi mọi nguồn dữ liệu đã chuyển đổi, loại bỏ alias name trong một phiên bản hợp đồng sau.

Nếu producer cũ vẫn hoạt động, consumer mới nên tiếp tục đọc tên cũ trong suốt thời gian đó. Không xóa alias chỉ vì một dịch vụ đã nâng cấp.

## 10. Thay đổi kiểu dữ liệu: đánh giá JSON token, không chỉ kiểu Java

Thay đổi kiểu dữ liệu có thể diễn ra ở hai lớp:

1. Kiểu JSON: string, number, boolean, object, array hoặc null.
2. Kiểu Java: String, Integer, Long, BigDecimal, enum, LocalDate hoặc một POJO.

Jackson có thể thực hiện một số coercion giữa kiểu JSON và Java, tùy cấu hình, logical type và phiên bản. Không nên dựa vào coercion ngầm như một cam kết tương thích.

Ví dụ:

| Kiểu cũ | Kiểu mới | Rủi ro |
|---|---|---|
| int | long | Có thể đọc số cũ, nhưng cần kiểm tra miền giá trị và writer/reader |
| Integer | String | JSON number cũ có thể không còn được chấp nhận theo chính sách strict |
| String | Integer | Chuỗi cũ có thể chứa ký tự không phải số hoặc format khác nhau |
| String | enum | Giá trị cũ có thể không nằm trong tập enum mới |
| String ngày giờ | object ngày giờ | Cấu trúc JSON thay đổi hoàn toàn |
| object | array | Consumer cũ thường không ánh xạ được |
| array | object | Consumer cũ thường không ánh xạ được |
| number | object có amount/currency | Đây là thay đổi cấu trúc và semantics, cần migration rõ |

Hãy kiểm tra các giá trị biên: null, missing, số âm, số rất lớn, decimal, chuỗi rỗng, enum chưa biết và timezone.

## 11. Ví dụ đổi int thành long

V1:

~~~java
public class InvoiceV1 {
    private int quantity;
    // getter/setter
}
~~~

V2:

~~~java
public class InvoiceV2 {
    private long quantity;
    // getter/setter
}
~~~

JSON number nguyên trong phạm vi int có thể được đọc vào long mà không mất giá trị. Tuy nhiên, cần kiểm tra:

- Consumer cũ vẫn dùng int có thể bị overflow nếu writer mới phát số lớn hơn Integer.MAX_VALUE.
- Database column, validation và tính toán downstream có thể vẫn giới hạn int.
- Các hệ thống khác có thể dùng number format hoặc schema khác.
- Số nguyên JSON quá lớn có thể vượt miền long.

Một lộ trình an toàn:

1. Nâng cấp consumer và storage để chấp nhận long trước.
2. Đảm bảo mọi nơi tính toán, validation và serialization đã hỗ trợ miền mới.
3. Sau đó mới cho producer phát giá trị vượt giới hạn int.
4. Theo dõi lỗi overflow và kiểm thử các giá trị sát biên.

Nếu cần hỗ trợ reader cũ, writer mới phải tiếp tục giới hạn giá trị trong miền int cho đến khi reader cũ được loại bỏ.

## 12. Ví dụ đổi number thành string hoặc string thành number

Giả sử V1 phát:

~~~json
{"accountNumber": 123456}
~~~

V2 muốn giữ account number dưới dạng string để bảo toàn số 0 ở đầu:

~~~json
{"accountNumber": "00123456"}
~~~

Đây không chỉ là đổi kiểu Java. Giá trị number cũ đã mất các số 0 đầu, vì vậy không thể suy ra chính xác chuỗi ban đầu từ mọi dữ liệu V1.

Một chiến lược là tạo field mới:

~~~json
{
  "accountNumber": 123456,
  "accountNumberText": "00123456"
}
~~~

Trong giai đoạn chuyển tiếp:

- Reader mới đọc field mới nếu có, nếu không thì chuyển đổi từ field cũ theo quy tắc được công bố.
- Writer phát cả hai field trong thời gian consumer cũ còn cần field number.
- Sau khi consumer cũ được nâng cấp, writer ngừng phát accountNumber number.
- Reader tiếp tục nhận field cũ trong thời gian replay dữ liệu cũ.

Nếu dùng cùng một tên field nhưng đổi từ number sang string, custom deserializer có thể chấp nhận cả hai token trong giai đoạn chuyển tiếp:

~~~java
public class AccountNumberDeserializer
        extends StdDeserializer<String> {

    public AccountNumberDeserializer() {
        super(String.class);
    }

    @Override
    public String deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.VALUE_STRING) {
            return parser.getText();
        }

        if (token == JsonToken.VALUE_NUMBER_INT) {
            return parser.getBigIntegerValue().toString();
        }

        throw JsonMappingException.from(
                parser,
                "Expected an account number string or integer"
        );
    }
}
~~~

Cách này giúp reader chấp nhận hai kiểu JSON, nhưng không khôi phục được số 0 đầu đã mất trong dữ liệu cũ. Việc chuyển đổi phải có quy tắc nghiệp vụ rõ ràng.

## 13. Thay đổi enum và giá trị mới

Enum thường được serialize thành tên chuỗi:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

JSON:

~~~json
{"status": "PAID"}
~~~

Nếu producer mới thêm SHIPPED, consumer cũ có thể ném InvalidFormatException khi không nhận diện giá trị enum đó. Thêm enum constant là thay đổi có thể phá forward compatibility.

Có thể chọn:

- Giữ strict và từ chối enum lạ nếu trạng thái ảnh hưởng logic quan trọng.
- Dùng @JsonEnumDefaultValue kết hợp READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE để ánh xạ giá trị không biết về một constant fallback.
- Dùng READ_UNKNOWN_ENUM_VALUES_AS_NULL nếu null là fallback phù hợp.
- Dùng kiểu wrapper/domain riêng để giữ nguyên raw string cho giá trị chưa biết.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Cấu hình:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(
                DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
        )
        .build();
~~~

Fallback UNKNOWN chỉ phù hợp khi nghiệp vụ có thể xử lý an toàn một trạng thái chưa biết. Không nên ánh xạ trạng thái thanh toán lạ thành PAID hoặc CANCELLED vì có thể làm thay đổi kết quả nghiệp vụ.

Nếu cần giữ chính xác giá trị chưa biết để gateway chuyển tiếp, lưu raw string hoặc JsonNode thay vì chỉ ánh xạ thành UNKNOWN.

## 14. Đổi cấu trúc object: dùng DTO trung gian

Giả sử V1:

~~~json
{
  "amount": 120000,
  "currency": "VND"
}
~~~

V2 muốn nhóm dữ liệu thành:

~~~json
{
  "money": {
    "value": 120000,
    "currencyCode": "VND"
  }
}
~~~

Đây là thay đổi cấu trúc. @JsonAlias không thể tự biến object amount/currency thành object money lồng nhau. Cần một lớp DTO trung gian hoặc custom deserializer đọc cả hai hình dạng.

Ví dụ DTO chuyển tiếp:

~~~java
public class PaymentPayload {
    private BigDecimal amount;
    private String currency;
    private Money money;

    public Money toDomain() {
        if (money != null) {
            return money;
        }
        if (amount != null && currency != null) {
            return new Money(amount, currency);
        }
        throw new IllegalArgumentException(
                "Payment amount and currency are required"
        );
    }

    // getters/setters
}
~~~

Đây là mô hình đọc cả hai dạng, sau đó chuẩn hóa về domain model Money. Trong thời gian chuyển tiếp, writer có thể phát dạng mới hoặc cả hai dạng tùy khả năng của consumer. Tránh duy trì hai nguồn giá trị mâu thuẫn mà không có quy tắc ưu tiên.

## 15. Dùng schemaVersion để chọn đường chuyển đổi

Khi thay đổi lớn, một field version rõ ràng giúp reader biết payload thuộc hợp đồng nào:

~~~json
{
  "schemaVersion": 2,
  "id": "P-100",
  "money": {
    "value": 120000,
    "currencyCode": "VND"
  }
}
~~~

Có thể đọc root thành JsonNode rồi dispatch theo version:

~~~java
JsonNode root = mapper.readTree(json);

int version = root.path("schemaVersion").asInt(1);

Payment payment = switch (version) {
    case 1 -> mapper.treeToValue(root, PaymentV1.class).toDomain();
    case 2 -> mapper.treeToValue(root, PaymentV2.class).toDomain();
    default -> throw new IllegalArgumentException(
            "Unsupported schemaVersion: " + version
    );
};
~~~

Ví dụ giả định version 1 là mặc định cho dữ liệu lịch sử chưa có field schemaVersion. Chỉ dùng default này nếu hệ thống thực sự biết rằng mọi payload không có version đều theo V1. Không nên đoán phiên bản từ hình dạng JSON nếu các phiên bản có cấu trúc chồng lấn hoặc mơ hồ.

Ưu điểm của versioned DTO:

- Mỗi phiên bản có quy tắc ánh xạ rõ ràng.
- Có thể viết test fixture riêng cho từng phiên bản.
- Logic chuyển đổi được tập trung ở adapter.
- Domain model không cần mang theo mọi field legacy.

Nhược điểm:

- Cần duy trì DTO và adapter cho các phiên bản còn được hỗ trợ.
- Cần định nghĩa chính sách cho version không biết.
- Cần quyết định khi nào có thể loại bỏ adapter cũ.

## 16. Tách DTO transport khỏi domain model

Không nên để domain model phải mang mọi chi tiết tương thích JSON trong thời gian dài. Một thiết kế thường dùng là:

~~~text
JSON V1 ----> DTO V1 ----\
                          \
JSON V2 ----> DTO V2 ------> Adapter / Upcaster ---> Domain model
                          /
JSON V3 ----> DTO V3 ----/
~~~

DTO mô tả hợp đồng của từng phiên bản. Adapter chuyển chúng về một mô hình domain hiện tại. Khi serialize, domain model có thể được chuyển sang DTO phiên bản writer cần phát.

Ví dụ:

~~~java
public record CustomerV1(
        String id,
        String name
) {
}

public record CustomerV2(
        String id,
        String displayName,
        String preferredLanguage
) {
}

public record Customer(
        String id,
        String displayName,
        String preferredLanguage
) {
}
~~~

Adapter:

~~~java
Customer toDomain(CustomerV1 source) {
    return new Customer(
            source.id(),
            source.name(),
            "vi"
    );
}

Customer toDomain(CustomerV2 source) {
    return new Customer(
            source.id(),
            source.displayName(),
            source.preferredLanguage()
    );
}
~~~

Ví dụ dùng default vi chỉ hợp lý nếu nghiệp vụ quy định ngôn ngữ mặc định như vậy. Adapter là nơi thực hiện quy tắc migration, không phải nơi tự đặt giá trị tùy tiện.

## 17. Migration dữ liệu JSON đã lưu

Thay đổi DTO không tự chuyển đổi các JSON document đã lưu trong database, object storage hoặc message archive. Dữ liệu lịch sử vẫn mang schema cũ cho đến khi được migrate hoặc đọc qua adapter.

Một quy trình migration dữ liệu có thể gồm:

1. Thống kê số lượng và phiên bản dữ liệu hiện có.
2. Tạo reader có thể đọc schema cũ.
3. Chuyển dữ liệu sang cấu trúc mới bằng một adapter có kiểm thử.
4. Ghi vào vùng hoặc cột mới, không ghi đè dữ liệu gốc ngay từ đầu.
5. Kiểm tra số lượng, khóa định danh, checksum hoặc các invariant nghiệp vụ.
6. Chuyển reader sang dữ liệu mới.
7. Giữ khả năng rollback trong thời hạn đã định.
8. Chỉ xóa dữ liệu cũ sau khi đã xác nhận migration và backup.

### Migration lặp an toàn

Một job migration có thể bị chạy lại sau timeout hoặc sự cố. Nên thiết kế idempotent:

- Ghi theo khóa ổn định.
- Lưu schema version đích.
- Không chuyển đổi lại bản ghi đã ở version đích.
- Dùng transaction hoặc staging table nếu có thể.
- Ghi lỗi riêng để có thể retry các bản ghi thất bại.

Ví dụ cập nhật version:

~~~json
{
  "schemaVersion": 2,
  "id": "P-100",
  "money": {
    "value": 120000,
    "currencyCode": "VND"
  }
}
~~~

Nếu job đọc schemaVersion = 2, nó không nên áp dụng lại chuyển đổi V1 sang V2. Với dữ liệu không có version, chỉ gán version mặc định khi quy tắc lịch sử đã được xác nhận.

## 18. Giữ unknown fields khi làm gateway hoặc proxy

Một gateway có thể cần đọc vài field để định tuyến nhưng vẫn phải chuyển tiếp field mà phiên bản hiện tại chưa biết. Nếu deserialize thẳng vào DTO hẹp rồi serialize lại, unknown fields có thể bị mất.

Hai lựa chọn:

- Đọc payload thành JsonNode, chỉ sửa các field cần thiết rồi ghi lại.
- Dùng @JsonAnySetter và @JsonAnyGetter để lưu các property mở rộng trên DTO.

Ví dụ Tree Model:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(json);

String id = root.path("id").asText();
root.put("traceId", "T-123");

String forwarded = mapper.writeValueAsString(root);
~~~

Các field chưa biết vẫn nằm trong cây JSON. Cách này giữ cấu trúc và giá trị JSON nhưng không giữ nguyên byte gốc, khoảng trắng hoặc cách escape ban đầu.

Nếu gateway cần bảo toàn payload nguyên văn, hãy giữ raw payload riêng và chỉ phân tích bản sao để định tuyến. Không nên giả định JsonNode round-trip là byte-for-byte preservation.

## 19. Unknown properties và chiến lược tương thích

Jackson thường bật FAIL_ON_UNKNOWN_PROPERTIES trong cấu hình ObjectMapper mặc định. Khi reader cũ gặp field mới mà không có cơ chế xử lý, nó có thể ném UnrecognizedPropertyException.

Có thể chấp nhận field chưa biết bằng:

~~~java
ObjectMapper tolerantMapper = new ObjectMapper()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Hoặc ở cấp DTO:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class LegacyConsumerRequest {
    private String id;
    private String name;
}
~~~

Cách này tăng forward tolerance nhưng bỏ field chưa biết. Nếu ứng dụng cần đọc rồi ghi lại payload mà vẫn giữ field đó, dùng JsonNode hoặc any-setter map.

Không nên tắt unknown-property failure trên mọi mapper mà không cân nhắc. Strict mode giúp phát hiện lỗi chính tả, field ngoài hợp đồng hoặc producer phát sai schema. Có thể dùng mapper tolerant cho một ranh giới tích hợp cụ thể và mapper strict cho request nội bộ cần validation chặt.

## 20. Ngừng phát field cũ nhưng giữ khả năng đọc

Một chiến lược phổ biến là dual-read, single-write:

~~~java
public class Product {
    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;
}
~~~

Serialization chỉ phát displayName. Deserialization nhận displayName hoặc name.

Nếu field cũ cần đọc nhưng tuyệt đối không được xuất lại, có thể dùng:

~~~java
public class Product {
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String legacyName;
}
~~~

Ở đây WRITE_ONLY cho phép nhận giá trị vào object khi deserialize nhưng không phát giá trị đó khi serialize. Hãy chọn mô hình DTO sao cho field legacy không vô tình được ghi trở lại từ domain model.

Nếu field cũ chứa dữ liệu nhạy cảm, cần cân nhắc cả logging, debugging và việc giữ field trong object sau khi deserialize. WRITE_ONLY chỉ điều khiển serialization; nó không tự xóa giá trị khỏi bộ nhớ hoặc ngăn ứng dụng truy cập getter.

## 21. Kiểm thử hợp đồng qua các phiên bản

Một test chỉ serialize rồi deserialize bằng cùng một phiên bản không đủ để phát hiện lỗi schema evolution. Nên lưu fixture đại diện cho từng phiên bản writer và chạy qua reader hiện tại.

Ma trận test ví dụ:

| Test | Payload | Reader mong đợi |
|---|---|---|
| T01 | V1 thiếu field mới | Reader V2 áp dụng default đúng |
| T02 | V2 có field mới | Reader V1 strict/tolerant theo hợp đồng |
| T03 | Field dùng tên cũ | Reader mới nhận qua @JsonAlias |
| T04 | Field dùng tên mới | Reader mới nhận tên canonical |
| T05 | Payload có cả hai alias | Quy tắc xung đột được thực hiện |
| T06 | Field cũ không còn được phát | Serializer không xuất tên legacy |
| T07 | Field legacy chỉ đọc | Deserializer nhận nhưng serializer không phát |
| T08 | Kiểu number trong miền cũ | Reader mới chuyển đổi không mất dữ liệu |
| T09 | Number vượt miền kiểu cũ | Reader cũ bị chặn hoặc giá trị bị giới hạn đúng chính sách |
| T10 | Enum value mới | Strict/fallback policy hoạt động như thiết kế |
| T11 | Version không hỗ trợ | Bị từ chối rõ ràng |
| T12 | JSON lịch sử không có schemaVersion | Được xử lý theo quy tắc legacy đã công bố |

Ví dụ test alias:

~~~java
class CustomerContractTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsLegacyNameAndWritesCanonicalName() throws Exception {
        Customer customer = mapper.readValue(
                "{\"name\":\"Lan\"}",
                Customer.class
        );

        assertEquals("Lan", customer.getDisplayName());

        JsonNode output = mapper.readTree(
                mapper.writeValueAsString(customer)
        );

        assertEquals("Lan", output.path("displayName").asText());
        assertFalse(output.has("name"));
    }
}
~~~

Test này xác nhận alias chỉ áp dụng ở chiều đọc và writer dùng tên canonical.

### Fixture nên được lưu cùng mã nguồn

Có thể tổ chức:

~~~text
src/test/resources/contracts/
    customer-v1.json
    customer-v2.json
    payment-v1.json
    payment-v2.json
~~~

Mỗi fixture nên có test xác nhận reader hiện tại đọc được hoặc từ chối theo đúng chính sách. Khi thay đổi DTO hoặc ObjectMapper configuration, test contract giúp phát hiện sự cố trước khi phát hành.

## 22. Theo dõi quá trình loại bỏ field

Không nên xóa alias hoặc code legacy chỉ dựa vào giả định rằng mọi producer đã nâng cấp. Có thể theo dõi:

- Số payload còn dùng tên field cũ.
- Số payload có schemaVersion cũ.
- Số lần reader dùng default vì field bị thiếu.
- Số lần gặp unknown property.
- Số record bị từ chối do type mismatch.
- Số message được chuyển đổi bởi adapter legacy.

Metric nên tránh ghi raw value nhạy cảm. Thường chỉ cần tên field, schema version, producer identifier và số lần xuất hiện.

Khi không còn payload legacy trong khoảng thời gian hỗ trợ đã định, nhóm phát triển có thể loại bỏ alias và adapter cũ trong một thay đổi schema có kiểm soát.

## 23. Các lỗi thường gặp khi đổi schema

### Chỉ đổi tên field Java

Tên Java mới không tự bảo đảm tên JSON cũ được nhận. Dùng @JsonAlias hoặc DTO adapter để hỗ trợ payload cũ.

### Dùng @JsonIgnore khi vẫn cần đọc dữ liệu cũ

@JsonIgnore thường loại property khỏi cả hai chiều. Nếu cần đọc nhưng không ghi, dùng WRITE_ONLY hoặc allowSetters theo mục tiêu.

### Tắt FAIL_ON_UNKNOWN_PROPERTIES toàn cục

Điều này có thể che giấu lỗi chính tả hoặc producer phát sai field. Chọn phạm vi tolerant phù hợp và theo dõi unknown fields.

### Đổi int thành long nhưng quên consumer cũ

Reader cũ có thể overflow khi writer mới phát giá trị vượt miền int. Chỉ phát giá trị lớn sau khi consumer cần thiết đã nâng cấp.

### Đổi number thành string nhưng quên dữ liệu đã mất

Chuyển number thành string không khôi phục được số 0 đầu đã mất trong dữ liệu cũ. Cần nguồn dữ liệu hoặc quy tắc chuyển đổi được xác nhận.

### Thêm enum constant mà không có fallback

Consumer cũ có thể từ chối giá trị enum mới. Chọn strict rejection hoặc fallback rõ ràng, không ánh xạ bừa sang trạng thái nghiệp vụ khác.

### Chỉ kiểm thử phiên bản mới với chính nó

Điều này bỏ sót lỗi khi reader mới nhận dữ liệu cũ hoặc reader cũ nhận dữ liệu mới. Dùng fixture nhiều phiên bản.

### Migration dữ liệu trực tiếp không có rollback

Job lỗi giữa chừng có thể để dữ liệu ở trạng thái hỗn hợp. Dùng staging, version, checkpoint và idempotency.

## 24. Quy trình thực hiện một thay đổi schema

Trước khi sửa DTO hoặc mapper, hãy thực hiện theo trình tự:

1. Xác định field nào được thêm, đổi tên, bỏ hoặc đổi kiểu.
2. Ghi lại JSON cũ và JSON mới bằng ví dụ cụ thể.
3. Liệt kê producer, consumer, storage và job replay có liên quan.
4. Xác định backward/forward compatibility cần giữ trong giai đoạn triển khai.
5. Chọn cách đọc chuyển tiếp: @JsonAlias, tolerant unknown fields, custom deserializer hoặc versioned DTO.
6. Chọn tên và kiểu canonical mà writer mới sẽ phát.
7. Đặt default cho dữ liệu thiếu và định nghĩa rõ null.
8. Nếu đổi kiểu, kiểm tra miền giá trị, coercion và mất mát dữ liệu.
9. Nếu bỏ field, ngừng phát trước, theo dõi rồi mới ngừng đọc.
10. Nếu dữ liệu đã lưu cần chuyển đổi, lập migration có checkpoint và rollback.
11. Thêm contract tests cho mọi phiên bản còn được hỗ trợ.
12. Theo dõi metric sau phát hành và chỉ dọn code legacy khi đã hết thời hạn tương thích.

## 25. Kết luận

Quản lý loại bỏ field và thay đổi kiểu dữ liệu là công việc quản lý hợp đồng JSON qua nhiều phiên bản. Thêm field tùy chọn thường dễ tương thích hơn xóa field hoặc đổi kiểu, nhưng vẫn cần reader cũ chấp nhận unknown property và reader mới xử lý dữ liệu thiếu. @JsonAlias hỗ trợ dual-read, single-write khi đổi tên; @JsonProperty.Access và JsonIgnoreProperties cho phép kiểm soát chiều đọc/ghi của field legacy. Thay đổi kiểu cần đánh giá JSON token, miền giá trị, coercion và nguy cơ mất dữ liệu; thay đổi cấu trúc lớn nên dùng DTO theo phiên bản và adapter. Với dữ liệu lưu lâu dài, cần schemaVersion hoặc quy tắc legacy rõ ràng cùng migration có thể chạy lại và rollback. Hãy kiểm thử reader/writer chéo phiên bản bằng fixture thực tế, theo dõi việc sử dụng field cũ và chỉ loại bỏ đường tương thích sau khi các producer, consumer và dữ liệu lịch sử đã sẵn sàng.
