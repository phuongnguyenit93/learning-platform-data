# Thêm trường mà vẫn giữ tương thích với bên đọc cũ

Một hợp đồng JSON thường được nhiều phiên bản ứng dụng sử dụng cùng lúc. Khi producer phát hành phiên bản mới, consumer cũ có thể vẫn đang chạy trong một thời gian: mobile app chưa được cập nhật, một dịch vụ downstream triển khai theo lịch riêng, một job cũ vẫn đọc file import hoặc một message trong queue được xử lý bởi consumer chưa nâng cấp.

Một thay đổi tưởng như nhỏ là thêm field vào JSON object có thể làm consumer cũ thất bại nếu nó từ chối property chưa biết. Ngược lại, nếu consumer được thiết kế để bỏ qua field lạ, việc thêm một field tùy chọn thường là thay đổi tương thích. Điều kiện quan trọng là field mới không làm thay đổi ý nghĩa của field cũ, không thay đổi cấu trúc hiện có và không trở thành dữ liệu bắt buộc đối với bên đọc cũ.

Trong Jackson, cần kiểm tra chính sách FAIL_ON_UNKNOWN_PROPERTIES, cách xử lý field bị thiếu và field có giá trị null, cũng như các kiểu dữ liệu lồng nhau. Bài này tập trung vào cách mở rộng JSON object bằng field mới trong khi giữ cho reader cũ tiếp tục hoạt động.

## 1. Hiểu đúng chiều tương thích

Giả sử phiên bản đầu của API trả:

~~~json
{
  "id": 42,
  "name": "Mai"
}
~~~

Phiên bản producer mới thêm email:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Reader cũ chỉ biết id và name. Nó có thể xử lý JSON mới nếu bỏ qua field email. Đây là chiều **producer mới → reader cũ**, thường được gọi là forward compatibility ở phía reader: thành phần cũ tiếp tục đọc dữ liệu được tạo bởi phiên bản mới.

Chiều ngược lại cũng quan trọng. Reader mới có thể nhận JSON cũ chưa có email. Nó cần xử lý việc field này vắng mặt bằng một giá trị mặc định, giá trị null hoặc một quy tắc nghiệp vụ phù hợp. Đây là chiều **reader mới → dữ liệu cũ**, thường được gọi là backward compatibility ở phía reader.

Hai chiều có điều kiện khác nhau:

| Chiều kiểm tra | Thay đổi | Điều kiện cần |
|---|---|---|
| Producer mới → reader cũ | JSON có thêm field | Reader cũ bỏ qua hoặc lưu giữ field chưa biết |
| Reader mới → producer cũ | JSON chưa có field mới | Reader mới chấp nhận field vắng mặt và có giá trị mặc định hợp lý |

Một thay đổi chỉ tương thích khi các consumer thực tế đều đáp ứng điều kiện tương ứng. Không nên kết luận "thêm field luôn an toàn" nếu chưa biết chính sách reader.

## 2. Khi nào thêm field là thay đổi tương thích?

Thêm field vào một JSON object thường là thay đổi additive. Nó có khả năng tương thích cao nếu thỏa các điều kiện:

- Field mới là tùy chọn đối với reader cũ.
- Reader cũ bỏ qua property không nhận diện hoặc có cơ chế giữ field mở rộng.
- Reader mới chấp nhận payload cũ không có field mới.
- Field mới không làm thay đổi kiểu, tên hoặc ý nghĩa của field hiện có.
- Cấu trúc object cha và các object lồng nhau vẫn giữ nguyên.
- Không có validator, JSON Schema hoặc gateway từ chối property bổ sung.
- Consumer không phụ thuộc vào danh sách field chính xác hoặc chữ ký của toàn bộ JSON.

Ví dụ thêm nickname vào object User thường an toàn hơn việc đổi name thành displayName, bởi consumer cũ vẫn có thể đọc name.

~~~json
{
  "id": 42,
  "name": "Mai",
  "nickname": "M"
}
~~~

Ngược lại, các thay đổi sau không còn là bổ sung field đơn thuần:

- Đổi id từ number sang string.
- Đổi name thành object có first và last.
- Đổi đơn vị hoặc ý nghĩa của amount.
- Xóa field cũ ngay khi consumer vẫn đang dùng.
- Đổi discriminator của subtype.
- Chuyển object thành array hoặc thay đổi thứ tự phần tử.

Một field mới chỉ an toàn khi nó thực sự bổ sung thông tin và không phá vỡ cách diễn giải dữ liệu cũ.

## 3. Reader cũ phải xử lý property chưa biết

Jackson Databind có feature DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES. Khi feature này bật, nếu JSON có property mà kiểu Java không nhận diện và property đó không được xử lý bởi bất kỳ cơ chế phù hợp nào, Jackson có thể ném UnrecognizedPropertyException.

Ví dụ reader cũ:

~~~java
public class OldUser {
    private long id;
    private String name;

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
}
~~~

Reader nhận JSON mới:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Nếu mapper bật FAIL_ON_UNKNOWN_PROPERTIES, Jackson có thể thất bại khi gặp email. Nếu mapper tắt feature, Jackson bỏ qua field không được model nhận diện và vẫn tạo được OldUser.

Điều này cho thấy tính tương thích phụ thuộc vào cấu hình reader, không chỉ vào cấu trúc JSON.

## 4. Cấu hình mapper để bỏ qua field lạ

Có thể tắt feature trên một mapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Hoặc với mapper đã được tạo nhưng chưa đưa vào sử dụng:

~~~java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Sau khi tắt, reader có thể đọc JSON có thêm property mà class Java không khai báo.

~~~java
OldUser user = mapper.readValue(json, OldUser.class);
~~~

Field email không được lưu vào OldUser, nhưng các field đã biết như id và name vẫn được gán.

Trong ứng dụng dùng Spring Boot, ObjectMapper thường được auto-configure và một số feature có thể đã được bật hoặc tắt theo cấu hình framework. Vì vậy, cần kiểm tra mapper thực tế được message converter hoặc service sử dụng. Không nên suy luận từ một new ObjectMapper() trong unit test rồi cho rằng cấu hình production giống hệt.

## 5. Bỏ qua field lạ ở cấp class

Nếu chỉ một DTO cần chấp nhận property chưa biết, có thể dùng JsonIgnoreProperties(ignoreUnknown = true):

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class OldUser {
    private long id;
    private String name;

    // Getter và setter
}
~~~

Annotation này cho biết các property không được nhận diện trên kiểu đó có thể bị bỏ qua khi deserialize.

Ưu điểm là phạm vi được thể hiện ngay trên DTO. Một mapper vẫn có thể giữ chế độ strict cho các kiểu khác, trong khi riêng DTO tích hợp với nguồn có schema mở được phép nhận field mới.

Có thể dùng mix-in nếu không sửa được class:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public abstract class OldUserMixin {
}
~~~

~~~java
ObjectMapper partnerReader = baseMapper.copy();
partnerReader.addMixIn(OldUser.class, OldUserMixin.class);
~~~

Khi dùng mix-in, phạm vi thay đổi gắn với mapper đã đăng ký mix-in. Nếu chỉ một luồng tích hợp cần tolerant parsing, hãy dùng mapper chuyên biệt thay vì thay đổi mapper toàn ứng dụng.

## 6. Bỏ qua toàn cục hay theo từng DTO?

Hai cách có phạm vi khác nhau:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| Tắt FAIL_ON_UNKNOWN_PROPERTIES trên mapper | Mọi kiểu được mapper đọc, trừ trường hợp có xử lý riêng | Hợp đồng chung chủ trương tolerant với field bổ sung |
| JsonIgnoreProperties(ignoreUnknown = true) | Kiểu được gắn annotation | Chỉ một số DTO chấp nhận field mở rộng |
| Mix-in với ignoreUnknown = true | Target type trên mapper chuyên biệt | Không sửa class hoặc cần phạm vi mapper riêng |
| JsonAnySetter | Các field chưa biết được chuyển vào handler/Map | Muốn giữ lại dữ liệu mở rộng thay vì bỏ qua |

Không có một lựa chọn đúng cho mọi hệ thống. Với API nội bộ cần phát hiện lỗi schema sớm, chế độ strict có thể hữu ích. Với consumer phải sống qua nhiều phiên bản producer, chế độ tolerant thường phù hợp hơn.

Nếu tắt feature toàn cục, một lỗi đánh máy như emial cũng có thể bị bỏ qua thay vì báo lỗi. Hãy cân nhắc giữa khả năng mở rộng và khả năng phát hiện payload sai.

## 7. Giữ field lạ thay vì bỏ qua bằng JsonAnySetter

Có trường hợp reader cũ muốn tiếp tục đọc field đã biết nhưng cũng cần giữ lại property mới để chuyển tiếp, ghi log có kiểm soát hoặc xử lý sau. JsonAnySetter cho phép nhận property không được khai báo thành field riêng:

~~~java
public class ExtensibleUser {
    private long id;
    private String name;
    private final Map<String, JsonNode> extra =
        new LinkedHashMap<>();

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

    @JsonAnySetter
    public void putExtra(String name, JsonNode value) {
        extra.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
~~~

Khi đọc:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com",
  "preferences": {
    "theme": "dark"
  }
}
~~~

Các field đã biết được gán vào property tương ứng. email và preferences được đưa vào map extra dưới dạng JsonNode.

JsonAnySetter không chỉ bỏ qua field lạ; nó chuyển trách nhiệm xử lý field đó cho phương thức được đánh dấu. JsonAnyGetter có thể phát các entry trong map trở lại JSON khi serialize. Nếu dùng cả hai, cần tránh trùng tên giữa property cố định và key trong map.

## 8. Khi nào nên dùng JsonAnySetter?

JsonAnySetter phù hợp với các cấu trúc có phần mở rộng được dự kiến trong hợp đồng:

- Metadata tùy chọn do nhiều producer bổ sung.
- Thuộc tính cấu hình theo plugin.
- Extension fields của một event envelope.
- Dữ liệu cần được đọc rồi chuyển tiếp mà không mất field chưa biết.

Không nên dùng nó để che mọi lỗi schema. Nếu DTO cần đúng một số field cụ thể, bỏ qua typo có thể khiến lỗi producer khó phát hiện.

Một chính sách cân bằng là:

- Các field cốt lõi được khai báo rõ và validate.
- Các field mở rộng được thu vào một vùng extension riêng.
- Các tên field không hợp lệ hoặc trùng field cốt lõi bị xử lý có chủ đích.
- Giới hạn kích thước/số lượng extension để tránh payload quá lớn.

## 9. Reader mới phải xử lý JSON cũ thiếu field mới

Khi producer cũ chưa gửi email, reader mới vẫn cần tạo được đối tượng. Cách xử lý phụ thuộc kiểu property và cách tạo object.

Với JavaBean có constructor rỗng và field initializer:

~~~java
public class User {
    private long id;
    private String name;
    private String locale = "vi-VN";

    // Getter và setter
}
~~~

Nếu JSON cũ không có locale, Jackson không gọi setter cho property đó; giá trị khởi tạo trong field có thể được giữ nguyên.

Với reference field không có initializer, giá trị thường là null. Với primitive như int hoặc boolean, giá trị mặc định Java là 0 hoặc false.

Không nên dựa vào primitive default nếu 0/false có ý nghĩa nghiệp vụ khác với "chưa được cung cấp". Khi cần phân biệt, dùng wrapper (Integer, Boolean) hoặc một kiểu biểu diễn trạng thái rõ ràng.

## 10. Giá trị mặc định cho field mới

Giả sử reader mới thêm marketingEnabled:

~~~java
public class User {
    private long id;
    private String name;
    private boolean marketingEnabled = false;

    // Getter và setter
}
~~~

Payload cũ:

~~~json
{
  "id": 42,
  "name": "Mai"
}
~~~

Khi đọc payload này, field marketingEnabled không được gán và giá trị initializer false vẫn còn. Đây có thể là mặc định hợp lý nếu hành vi cũ tương ứng với việc không bật marketing.

Một ví dụ khác:

~~~java
public class ReportSettings {
    private String timezone = "UTC";
}
~~~

Nếu payload cũ không có timezone, reader mới dùng UTC. Chỉ chọn default khi có ý nghĩa rõ ràng và phù hợp với dữ liệu lịch sử.

Giá trị mặc định không nên chỉ được chọn để tránh exception. Nó phải bảo toàn cách diễn giải của dữ liệu cũ.

## 11. Phân biệt field vắng mặt và field có giá trị null

Hai payload sau không nhất thiết mang cùng ý nghĩa:

~~~json
{
  "name": "Mai"
}
~~~

~~~json
{
  "name": "Mai",
  "locale": null
}
~~~

Payload thứ nhất không gửi locale. Payload thứ hai gửi locale tường minh với giá trị null.

Với JavaBean, nếu property bị thiếu, setter thường không được gọi và field initializer được giữ lại. Nếu property có mặt với null, Jackson có thể gọi setter với null hoặc áp dụng chính sách null của property.

Ví dụ:

~~~java
public class User {
    private String locale = "vi-VN";

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

Khi field vắng mặt, locale có thể giữ vi-VN. Khi JSON có locale null, setter có thể gán null. Vì vậy, cần xác định chính sách riêng cho missing và explicit null.

## 12. Dùng JsonSetter(nulls = Nulls.SKIP) khi cần giữ default với null

Nếu muốn cả trường hợp thiếu field lẫn trường hợp explicit null đều giữ giá trị khởi tạo, có thể dùng Nulls.SKIP:

~~~java
public class User {
    private String locale = "vi-VN";

    public String getLocale() {
        return locale;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

Khi JSON có locale null, Jackson bỏ qua việc gọi setter cho null theo chính sách này; giá trị initializer vẫn được giữ.

Nếu muốn explicit null bị từ chối, có thể xem xét Nulls.FAIL:

~~~java
@JsonSetter(nulls = Nulls.FAIL)
public void setLocale(String locale) {
    this.locale = locale;
}
~~~

Chọn SKIP, FAIL hoặc SET theo đúng ý nghĩa của hợp đồng. Không nên tự động coi null tương đương với missing nếu client cần khả năng xóa một giá trị bằng cách gửi null.

## 13. JsonProperty(defaultValue) không tự động là cơ chế gán default

JsonProperty có thuộc tính defaultValue, nhưng trong Jackson Databind 2.x, giá trị này chủ yếu là metadata mô tả default cho công cụ/schema hoặc introspection. Không nên giả định Jackson tự gán giá trị đó vào property khi JSON thiếu field.

Ví dụ:

~~~java
@JsonProperty(defaultValue = "vi-VN")
private String locale;
~~~

Khai báo trên không thay thế cho initializer, setter hoặc logic trong creator để đảm bảo locale nhận vi-VN.

Nếu cần default thực sự, hãy triển khai rõ:

~~~java
private String locale = "vi-VN";
~~~

hoặc:

~~~java
public void setLocale(String locale) {
    this.locale = locale == null ? "vi-VN" : locale;
}
~~~

hoặc xử lý trong constructor/factory. Cách chọn phụ thuộc việc muốn áp dụng default khi field vắng mặt, khi field null hay trong cả hai trường hợp.

## 14. Constructor-based deserialization cần default tường minh

Với immutable class dùng JsonCreator, field không được gán qua setter. Giá trị mặc định phải được quyết định trong constructor hoặc factory:

~~~java
public final class User {
    private final long id;
    private final String name;
    private final String locale;

    @JsonCreator
    public User(
            @JsonProperty("id") long id,
            @JsonProperty("name") String name,
            @JsonProperty("locale") String locale) {
        this.id = id;
        this.name = name;
        this.locale = locale == null ? "vi-VN" : locale;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getLocale() {
        return locale;
    }
}
~~~

Ví dụ này gán default khi locale bị thiếu và khi giá trị là null. Nếu cần phân biệt hai trường hợp, dùng creator có khả năng quan sát trạng thái presence hoặc thiết kế một kiểu input riêng.

Không nên đánh dấu field mới là required trong creator nếu vẫn cần đọc payload cũ không có field đó. required = true trên creator property có thể khiến dữ liệu cũ không còn đọc được. Với property thông thường, required không phải cơ chế validation phổ quát; hãy kiểm tra đúng ngữ cảnh creator và bổ sung validation sau bind khi cần.

## 15. Không thay đổi kiểu field cũ khi thêm field mới

Một thay đổi additive nên giữ nguyên tất cả property hiện có:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Đừng đồng thời đổi id từ number sang string:

~~~json
{
  "id": "42",
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Jackson có thể coercion một số scalar tùy cấu hình, nhưng consumer khác có thể không chấp nhận. Hơn nữa, kiểu dữ liệu là một phần hợp đồng; dựa vào coercion ngầm khiến kết quả khác nhau giữa ngôn ngữ hoặc phiên bản.

Nếu cần thay kiểu, hãy dùng field mới:

~~~json
{
  "id": 42,
  "idText": "42",
  "name": "Mai"
}
~~~

Giữ field cũ trong giai đoạn chuyển tiếp, tài liệu hóa field mới và chỉ xóa field cũ sau khi consumer đã được nâng cấp.

## 16. Không đổi ý nghĩa của field hiện có

Một thay đổi có thể giữ nguyên tên và kiểu nhưng vẫn phá tương thích nếu ngữ nghĩa thay đổi.

Ví dụ trước đây:

~~~json
{
  "amount": 1250
}
~~~

Consumer hiểu amount là số tiền theo đơn vị đồng. Producer mới bắt đầu gửi amount theo đơn vị nghìn đồng nhưng vẫn giữ tên và kiểu number. JSON parse thành công, mapping thành công, nhưng kết quả nghiệp vụ sai.

Nếu cần đổi đơn vị, hãy thêm field có tên rõ:

~~~json
{
  "amount": 1250,
  "amountInThousandVnd": 1.25
}
~~~

Hoặc version schema để phân biệt semantics. Tính tương thích không chỉ là Jackson có deserialize được hay không; consumer phải tiếp tục diễn giải đúng dữ liệu.

## 17. Thêm field vào object lồng nhau

Một thay đổi thường bị bỏ sót là thêm field vào nested object:

Phiên bản cũ:

~~~json
{
  "id": 42,
  "address": {
    "city": "Ha Noi"
  }
}
~~~

Phiên bản mới:

~~~json
{
  "id": 42,
  "address": {
    "city": "Ha Noi",
    "postalCode": "100000"
  }
}
~~~

Dù object root không thêm property mới, object address đã thêm postalCode. Nếu reader cũ dùng một Address DTO strict, nó vẫn có thể ném UnrecognizedPropertyException.

~~~java
public class Address {
    private String city;
}

public class User {
    private long id;
    private Address address;
}
~~~

Chính sách tolerant phải áp dụng ở đúng kiểu nested:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class Address {
    private String city;
}
~~~

Hoặc cấu hình mapper bỏ qua unknown properties cho toàn bộ kiểu đọc. Cần kiểm tra mọi tầng lồng nhau, vì việc root DTO bỏ qua field lạ không tự động đảm bảo tất cả nested DTO đều có cùng annotation nếu mapper đang ở chế độ strict.

## 18. Thêm field trong phần tử collection

JSON array có thể chứa object:

~~~json
{
  "users": [
    {
      "id": 1,
      "name": "Mai",
      "email": "mai@example.com"
    },
    {
      "id": 2,
      "name": "An",
      "email": "an@example.com"
    }
  ]
}
~~~

Reader cũ cần xử lý field mới bên trong từng phần tử User. Chính sách unknown-field trên kiểu User hoặc mapper sẽ quyết định kết quả.

Một array có thể chứa hàng nghìn object; chỉ cần một phần tử có field không được nhận diện cũng có thể khiến toàn bộ lần deserialize thất bại nếu reader strict.

Hãy kiểm thử:

- Field mới xuất hiện ở phần tử đầu.
- Field mới chỉ xuất hiện ở một phần tử sau.
- Một số phần tử có field mới, một số không có.
- Nested object trong phần tử cũng có field mới.

## 19. Không thêm phần tử tùy tiện vào JSON array có ý nghĩa vị trí

Thêm field vào object thường dễ tương thích hơn thêm phần tử vào array.

Ví dụ array dạng tuple:

~~~json
[
  42,
  "Mai"
]
~~~

Consumer có thể hiểu phần tử thứ nhất là id, phần tử thứ hai là name. Nếu producer thêm email:

~~~json
[
  42,
  "Mai",
  "mai@example.com"
]
~~~

Consumer cũ có thể từ chối vì số phần tử khác dự kiến hoặc vô tình diễn giải sai nếu vị trí bị thay đổi.

Nếu cần mở rộng schema, ưu tiên object có tên field:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Nếu giao thức buộc phải dùng array, cần quy định rõ phần tử mở rộng có thể được bỏ qua hay không, có version/length marker không và cách reader cũ xử lý phần tử dư.

## 20. Enum là một trường hợp đặc biệt

Thêm field mới có thể an toàn, nhưng thêm một giá trị enum vào field hiện có có thể làm reader cũ thất bại.

Giả sử reader cũ:

~~~java
public enum Status {
    NEW,
    PAID,
    CANCELLED
}
~~~

Producer mới thêm trạng thái REFUNDED:

~~~json
{
  "status": "REFUNDED"
}
~~~

Reader cũ không biết giá trị enum mới. Jackson có thể ném InvalidFormatException hoặc lỗi mapping tương ứng.

Một số chính sách có thể dùng:

- Bảo đảm reader được nâng cấp trước khi producer phát giá trị enum mới.
- Dùng READ_UNKNOWN_ENUM_VALUES_AS_NULL nếu null có ý nghĩa phù hợp.
- Dùng READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE với một enum constant được đánh dấu JsonEnumDefaultValue.
- Thay enum bằng một kiểu string/value object mở nếu miền giá trị cần mở rộng độc lập.

Ví dụ fallback:

~~~java
public enum Status {
    NEW,
    PAID,
    CANCELLED,
    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE)
    .build();
~~~

Fallback chỉ an toàn nếu consumer có thể xử lý UNKNOWN mà không làm sai nghiệp vụ. Không nên biến trạng thái quan trọng như REFUNDED thành UNKNOWN rồi tiếp tục thanh toán hoặc đối soát như thể không có khác biệt.

## 21. Thêm subtype mới cũng không giống thêm field

Với polymorphic JSON, thêm một subtype mới có thể làm reader cũ thất bại dù object vẫn có các field quen thuộc.

Ví dụ producer mới:

~~~json
{
  "kind": "bank-transfer",
  "amount": 500000,
  "bankCode": "ABC"
}
~~~

Reader cũ chỉ đăng ký card và cash. Khi gặp bank-transfer, Jackson không biết subtype nào cần tạo và có thể ném InvalidTypeIdException.

Để giữ tương thích:

- Nâng cấp consumer để biết subtype mới trước khi producer phát nó.
- Hoặc thiết kế một subtype fallback có ý nghĩa và xử lý an toàn.
- Hoặc dùng envelope/JsonNode ở tầng biên để giữ payload chưa biết.
- Không cho phép type id tùy ý biến thành tên class Java được nạp từ input.

Thêm field trong một subtype đã biết và thêm một subtype mới là hai thay đổi schema khác nhau. Cần test riêng.

## 22. JsonIgnoreProperties và dữ liệu cần được giữ lại

JsonIgnoreProperties(ignoreUnknown = true) bỏ qua property lạ khi deserialize. Nó không tự giữ lại dữ liệu đó để serialize lại.

Ví dụ reader cũ đọc:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com"
}
~~~

Sau khi bind vào OldUser chỉ có id và name, rồi serialize lại:

~~~json
{
  "id": 42,
  "name": "Mai"
}
~~~

Field email đã bị mất. Nếu consumer cũ đóng vai trò proxy và cần chuyển tiếp toàn bộ field chưa biết, bỏ qua unknown không đủ. Dùng JsonAnySetter để giữ extension data hoặc chuyển tiếp nguyên payload bằng JsonNode/streaming theo nhu cầu.

Đây là khác biệt giữa **tolerant reader** và **lossless forwarder**:

- Tolerant reader tiếp tục xử lý field đã biết và bỏ qua phần chưa biết.
- Lossless forwarder giữ được dữ liệu chưa biết khi phát lại hoặc chuyển tiếp.

## 23. JSON Schema có thể làm thay đổi kết quả tương thích

Ngay cả khi Jackson reader bỏ qua field lạ, một thành phần khác vẫn có thể từ chối JSON:

- JSON Schema đặt additionalProperties: false.
- API gateway kiểm tra schema cũ.
- OpenAPI client generator tạo validator strict.
- Contract test so sánh object chính xác.
- Message broker schema registry áp dụng compatibility policy.
- Một consumer dùng parser khác với Jackson.

Ví dụ schema strict:

~~~json
{
  "type": "object",
  "properties": {
    "id": { "type": "integer" },
    "name": { "type": "string" }
  },
  "required": ["id", "name"],
  "additionalProperties": false
}
~~~

Schema trên từ chối email dù Jackson có thể bỏ qua field đó. Nếu muốn cho phép field bổ sung, schema có thể bỏ additionalProperties: false hoặc định nghĩa policy mở rộng phù hợp.

Không nên chỉ kiểm thử bằng ObjectMapper nếu luồng production còn có gateway, validator hoặc schema registry.

## 24. Field mới có nên xuất hiện khi null?

Producer mới có thể luôn ghi field:

~~~json
{
  "id": 42,
  "email": null
}
~~~

Hoặc chỉ ghi khi có giá trị:

~~~json
{
  "id": 42
}
~~~

Jackson có thể điều khiển inclusion:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
private String email;
~~~

Hoặc cấu hình ở cấp class:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String email;
}
~~~

Với reader cũ, cả hai hình dạng thường đều tương thích nếu unknown field được bỏ qua. Nhưng với reader mới, null và missing có thể mang ý nghĩa khác nhau. Hãy định nghĩa rõ:

- Missing: producer không cung cấp thông tin.
- Null: producer chủ động biểu thị không có giá trị hoặc xóa giá trị.
- Empty string: có giá trị nhưng rỗng.

Không nên dùng ba trạng thái này thay thế nhau mà không có quy tắc.

## 25. Field mới có phải required không?

Nếu producer mới bắt đầu phát một field mới, không nên ngay lập tức yêu cầu mọi reader cũ phải hiểu field đó.

Với reader mới, nếu field mới cần thiết cho logic:

- Đảm bảo mọi producer đã phát field trước khi triển khai reader phụ thuộc vào nó.
- Hoặc có default có ý nghĩa khi đọc dữ liệu cũ.
- Hoặc version schema/endpoint để phân biệt payload.

Không nên dùng JsonProperty(required = true) một cách tùy tiện trên field mới rồi mong dữ liệu cũ vẫn đọc được. Trong Jackson, required chủ yếu có ý nghĩa với creator properties; nó không phải hệ thống validation tổng quát cho mọi field. Dù vậy, nếu creator yêu cầu field mới, payload cũ có thể thất bại.

Validation nghiệp vụ nên chạy sau bước bind và có thông báo riêng cho trường hợp thiếu dữ liệu.

## 26. Thêm field nhưng không làm thay đổi output của consumer cũ

Một reader cũ có thể deserialize JSON mới rồi serialize lại bằng model cũ. Field mới bị bỏ qua và không xuất hiện trong output tiếp theo.

Ví dụ:

~~~java
OldUser oldUser = oldMapper.readValue(newJson, OldUser.class);
String forwarded = oldMapper.writeValueAsString(oldUser);
~~~

Kết quả có thể không chứa email. Nếu consumer cũ chỉ hiển thị hoặc tính toán từ field đã biết, điều này không sao. Nếu nó hoạt động như proxy, cache, event bridge hoặc read-modify-write service, việc mất field có thể làm hỏng dữ liệu.

Trước khi bật ignoreUnknown, hãy xác định reader có cần round-trip dữ liệu hay không. Nếu phải bảo toàn field chưa biết, dùng map extension hoặc giữ nguyên JsonNode/payload.

## 27. Dùng JsonNode cho proxy hoặc dữ liệu có phần mở rộng

Nếu consumer cần đọc một phần JSON nhưng vẫn giữ các field khác, có thể giữ payload dưới dạng tree:

~~~java
JsonNode root = mapper.readTree(json);
String name = root.path("name").asText();
~~~

Khi cần thay đổi một field và giữ phần còn lại:

~~~java
ObjectNode object = (ObjectNode) root;
object.put("processed", true);

String forwarded = mapper.writeValueAsString(object);
~~~

Cách này giữ được các property chưa biết về mặt cấu trúc JSON. Cần kiểm tra root thực sự là object trước khi cast và xác định chính sách cho field trùng hoặc dữ liệu nhạy cảm.

Tree model giữ toàn bộ payload trong bộ nhớ. Với message lớn hoặc stream rất lớn, streaming parser/generator có thể tiết kiệm bộ nhớ hơn.

## 28. Thêm field vào event và message bất đồng bộ

Trong hệ thống event-driven, producer và consumer thường được triển khai độc lập. Producer có thể phát event mới trong khi consumer cũ vẫn đang xử lý backlog.

Ví dụ event cũ:

~~~json
{
  "eventId": "evt-42",
  "eventType": "user-created",
  "data": {
    "id": 42,
    "name": "Mai"
  }
}
~~~

Event mới thêm source:

~~~json
{
  "eventId": "evt-42",
  "eventType": "user-created",
  "source": "mobile",
  "data": {
    "id": 42,
    "name": "Mai"
  }
}
~~~

Consumer cũ cần chấp nhận field source ở envelope. Nếu thêm field vào data, DTO nested của consumer cũng cần tolerant. Cần kiểm tra cả hai tầng.

Với event, nên duy trì nguyên tắc:

- Không đổi ý nghĩa eventType đã công bố.
- Field mới nên optional hoặc có default cho reader mới.
- Consumer cũ phải bỏ qua field mở rộng hoặc giữ lại nếu forward.
- Không phát giá trị enum/subtype mới trước khi consumer tương ứng sẵn sàng.
- Xử lý message cũ trong backlog khi triển khai schema mới.

## 29. Thêm field vào API response

Với REST API, field bổ sung thường được xem là thay đổi không phá vỡ nếu client tuân theo nguyên tắc chỉ đọc field cần thiết và bỏ qua field chưa biết.

Tuy nhiên, có client không tuân theo nguyên tắc này:

- Client sinh code từ schema strict.
- Client so sánh response với snapshot chính xác.
- Client dùng record/constructor yêu cầu đúng số field.
- Client validate additionalProperties: false.
- Client parse JSON thành một kiểu đóng không hỗ trợ unknown fields.

Vì vậy, API contract cần ghi rõ consumer phải bỏ qua field chưa biết nếu muốn hỗ trợ additive evolution.

Ví dụ tài liệu:

~~~text
Clients must ignore response properties they do not recognize.
New optional response properties may be added without changing
the API version.
~~~

Nếu client không thể tuân theo quy tắc này, cần version hoặc một hợp đồng endpoint riêng.

## 30. Thêm field vào request body có rủi ro khác response

Với response, server thường là producer và client là reader. Với request, client là producer và server là reader.

Khi client mới thêm field vào request gửi đến server cũ, server cũ cần bỏ qua hoặc hiểu field mới. Nếu server strict, request có thể bị từ chối.

Ví dụ client mới gửi:

~~~json
{
  "name": "Mai",
  "preferredLanguage": "vi"
}
~~~

Server cũ chỉ có name. Nếu FAIL_ON_UNKNOWN_PROPERTIES bật, server có thể trả 400.

Không nên giả định quy tắc tolerant cho response tự động áp dụng cho request. Hãy xác định riêng:

- Server có chấp nhận request field mới từ client mới không?
- Field đó có ảnh hưởng nghiệp vụ hay chỉ là metadata tùy chọn?
- Server cũ có thể bỏ qua mà vẫn xử lý đúng không?
- Nếu không hiểu field, có cần trả lỗi thay vì âm thầm bỏ qua?

Trong API command, field lạ đôi khi nên bị từ chối vì client có thể nghĩ server đã thực hiện một hành động mà thực tế server đã bỏ qua. Quyết định này phải dựa trên semantics của request.

## 31. Phân biệt additive response với additive command

Một field mới trong response thường chỉ bổ sung thông tin để client có thể dùng khi hiểu nó. Một field mới trong command/request có thể thay đổi hành động mà client yêu cầu.

Ví dụ response:

~~~json
{
  "id": 42,
  "name": "Mai",
  "avatarUrl": "https://example.test/avatar.png"
}
~~~

Client cũ có thể bỏ qua avatarUrl.

Ví dụ request:

~~~json
{
  "transferAmount": 100000,
  "executeImmediately": true
}
~~~

Nếu server cũ bỏ qua executeImmediately, hành vi có thể khác với điều client mới mong đợi. Với command, field lạ không phải lúc nào cũng nên được bỏ qua.

Hãy định nghĩa policy cho request và response riêng. Có thể response tolerant nhưng request strict, hoặc ngược lại tùy giao thức.

## 32. Rollout an toàn khi producer và consumer được triển khai độc lập

Nếu field mới được reader mới sử dụng, trình tự triển khai có thể ảnh hưởng tương thích.

Một rollout hai pha thường an toàn:

1. Triển khai reader mới trước, để nó chấp nhận payload cũ và có thể đọc field mới.
2. Xác nhận tất cả consumer cần field đã được nâng cấp.
3. Triển khai producer mới bắt đầu phát field.
4. Theo dõi lỗi deserialize và hành vi nghiệp vụ.
5. Chỉ sau khi mọi consumer cần thiết đã hiểu field mới, mới dựa vào field đó cho logic bắt buộc.

Nếu field chỉ là metadata tùy chọn và consumer cũ bỏ qua an toàn, producer có thể phát sớm hơn, nhưng vẫn cần kiểm tra gateway/schema registry và consumer strict.

~~~text
Giai đoạn 1: Reader mới chấp nhận cả JSON cũ và JSON mới
              |
              v
Giai đoạn 2: Nâng cấp các consumer cần field mới
              |
              v
Giai đoạn 3: Producer bắt đầu phát field mới
              |
              v
Giai đoạn 4: Theo dõi lỗi và hành vi thực tế
              |
              v
Giai đoạn 5: Chuyển field thành yêu cầu nghiệp vụ
             (chỉ khi toàn bộ consumer đã sẵn sàng)
~~~

Không nên triển khai producer trước rồi ngay lập tức khiến consumer cũ phải phụ thuộc vào field mới.

## 33. Duy trì hai field trong giai đoạn đổi tên

Nếu muốn đổi name thành displayName, có thể giữ cả hai trong một giai đoạn:

~~~json
{
  "name": "Mai",
  "displayName": "Mai"
}
~~~

Consumer cũ tiếp tục đọc name; consumer mới có thể ưu tiên displayName và fallback sang name.

Reader mới:

~~~java
public class User {
    private String name;
    private String displayName;

    public String effectiveDisplayName() {
        return displayName != null ? displayName : name;
    }
}
~~~

Khi producer phát cả hai, cần đảm bảo giá trị đồng nhất. Nếu chúng khác nhau, phải có quy tắc ưu tiên và log/validation để phát hiện.

Không nên duy trì hai field đồng nghĩa vô thời hạn. Hãy tài liệu hóa giai đoạn deprecation và thời điểm ngừng phát field cũ.

## 34. Dùng JsonAlias để reader mới chấp nhận tên cũ

JsonAlias có thể giúp reader mới nhận nhiều tên đầu vào cho cùng một property:

~~~java
public class User {
    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;
}
~~~

Reader mới có thể đọc cả:

~~~json
{
  "name": "Mai"
}
~~~

và:

~~~json
{
  "displayName": "Mai"
}
~~~

JsonAlias chủ yếu ảnh hưởng chiều deserialize; khi serialize, tên property chuẩn vẫn là tên được xác định bởi JsonProperty/property metadata. Vì vậy, nó hữu ích cho giai đoạn reader chấp nhận schema cũ và mới.

Nếu cả hai tên cùng xuất hiện trong một JSON object, cần xác định hành vi theo thứ tự token và cấu hình thực tế, hoặc từ chối payload mâu thuẫn bằng validation. Không nên để hai field cùng đại diện một giá trị mà không có quy tắc.

## 35. Đặt chính sách default theo đúng ý nghĩa nghiệp vụ

Default của field mới cần được chọn cẩn thận:

| Field mới | Default có thể cân nhắc | Câu hỏi cần trả lời |
|---|---|---|
| locale | vi-VN hoặc locale hệ thống | Có thể suy ra từ user hay tenant không? |
| enabled | false | Không cung cấp có thực sự đồng nghĩa tắt? |
| tags | Danh sách rỗng | Rỗng có khác với chưa biết không? |
| createdAt | Không tự tạo thời điểm hiện tại | Có nguồn dữ liệu đáng tin cậy nào không? |
| status | Enum UNKNOWN hoặc trạng thái mặc định | Consumer có xử lý unknown an toàn không? |
| currency | Không nên tự đoán | Có thể suy ra từ account/order không? |

Đặc biệt, không nên gán Instant.now() cho một field createdAt bị thiếu nếu dữ liệu cũ thực sự không biết thời điểm tạo. Default giả tạo có thể làm sai báo cáo hoặc audit.

Default là một phần của schema evolution. Nó cần được tài liệu hóa và kiểm thử như một quy tắc dữ liệu.

## 36. Kiểm thử producer mới với reader cũ

Một bài kiểm thử tương thích nên dùng DTO đại diện cho phiên bản reader cũ, rồi đọc JSON do producer mới tạo:

~~~java
class OldUser {
    private long id;
    private String name;

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
}

class NewUser {
    private long id;
    private String name;
    private String email;

    // Getter và setter
}
~~~

Producer mới serialize NewUser:

~~~java
String json = newMapper.writeValueAsString(newUser);
~~~

Reader cũ deserialize:

~~~java
OldUser restored = oldMapper.readValue(json, OldUser.class);

assertEquals(newUser.getId(), restored.getId());
assertEquals(newUser.getName(), restored.getName());
~~~

Test cần dùng cấu hình mapper tương ứng với reader cũ. Nếu reader cũ strict, test nên thất bại để cho thấy việc thêm field phá hợp đồng. Nếu hợp đồng yêu cầu tolerant, cấu hình reader cũ theo đúng policy và xác nhận field đã biết vẫn giữ nguyên.

## 37. Kiểm thử với mapper strict và tolerant

Có thể thể hiện rõ sự khác nhau:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();

ObjectMapper tolerantMapper = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Với JSON mới:

~~~java
assertThrows(
    UnrecognizedPropertyException.class,
    () -> strictMapper.readValue(json, OldUser.class)
);

OldUser user = tolerantMapper.readValue(json, OldUser.class);
assertEquals("Mai", user.getName());
~~~

Test này chứng minh điều kiện tương thích nằm ở reader. Không nên chỉ test producer mới serialize được JSON; phải test consumer cũ có đọc được JSON đó không.

## 38. Kiểm thử reader mới với payload cũ

Reader mới cần được test bằng fixture JSON cũ không có field mới:

~~~java
String oldJson = """
    {
      "id": 42,
      "name": "Mai"
    }
    """;

User restored = newMapper.readValue(oldJson, User.class);

assertEquals("vi-VN", restored.getLocale());
~~~

Test nên xác nhận default thực tế, không chỉ xác nhận deserialize không ném lỗi. Nếu field mới có initializer, constructor logic hoặc Nulls policy, test cần bao gồm:

- Field bị thiếu.
- Field có giá trị null.
- Field có giá trị hợp lệ.
- Field có giá trị sai kiểu.
- Field có giá trị rỗng nếu khác null.

## 39. Kiểm thử nested object và collection

Ví dụ fixture mới:

~~~json
{
  "users": [
    {
      "id": 1,
      "name": "Mai",
      "email": "mai@example.com"
    },
    {
      "id": 2,
      "name": "An",
      "email": "an@example.com"
    }
  ]
}
~~~

Reader cũ cần đọc được toàn bộ collection nếu policy là bỏ qua field mới:

~~~java
OldUserBatch batch =
    oldMapper.readValue(json, OldUserBatch.class);

assertEquals(2, batch.getUsers().size());
assertEquals("Mai", batch.getUsers().get(0).getName());
~~~

Nên có fixture riêng cho field mới trong nested object, không chỉ root object. Một mapper strict có thể thành công ở root nhưng thất bại ở nested DTO nếu chỉ root được gắn ignoreUnknown = true.

## 40. Kiểm thử enum và subtype mới riêng

Thêm field mới không chứng minh enum và polymorphic hierarchy vẫn tương thích.

Test enum:

~~~java
String json = """
    {"status":"REFUNDED"}
    """;

// Kiểm tra reader cũ có fallback hoặc báo lỗi theo policy đã định.
~~~

Test subtype:

~~~java
String json = """
    {
      "kind": "bank-transfer",
      "amount": 500000
    }
    """;

// Kiểm tra reader cũ xử lý type id mới theo policy đã định.
~~~

Nếu consumer cũ không hỗ trợ subtype mới, không nên xem đó là lỗi "unknown field". Type id là dữ liệu điều khiển việc tạo lớp và cần chính sách riêng.

## 41. Contract test nên kiểm tra những gì?

Một bộ contract test cho việc thêm field nên kiểm tra:

1. Producer mới vẫn phát các field cũ với đúng tên và kiểu.
2. Producer mới có thể phát field bổ sung.
3. Reader cũ chấp nhận field bổ sung theo policy.
4. Reader mới đọc được payload cũ thiếu field mới.
5. Field thiếu và field null có hành vi đúng.
6. Nested object và collection cũng tương thích.
7. Enum và type discriminator không bị thay đổi ngoài dự kiến.
8. JSON Schema/gateway/schema registry cho phép additive field nếu có.
9. Proxy/forwarder không làm mất field chưa biết nếu cần round-trip.
10. Consumer strict vẫn phát hiện lỗi khi policy yêu cầu strict.

Test nên sử dụng fixture versioned được lưu trong repository để bảo vệ các payload đã phát hành trước đó.

## 42. Snapshot test không nên yêu cầu JSON giống hệt khi schema được phép mở rộng

Nếu test chỉ so sánh toàn bộ JSON string, việc thêm field có thể làm test thất bại dù thay đổi tương thích:

~~~java
assertEquals(
    "{\"id\":42,\"name\":\"Mai\"}",
    mapper.writeValueAsString(user)
);
~~~

Khi hợp đồng cho phép field bổ sung, hãy kiểm tra các field cốt lõi:

~~~java
JsonNode node = mapper.readTree(
    mapper.writeValueAsString(user)
);

assertEquals(42, node.get("id").asLong());
assertEquals("Mai", node.get("name").asText());
assertTrue(node.has("email"));
~~~

Snapshot vẫn có ích để phát hiện thay đổi ngoài ý muốn, nhưng cần được cập nhật có chủ đích khi schema mở rộng. Không nên dùng snapshot như một hợp đồng cấm mọi field mới nếu hệ thống tuyên bố hỗ trợ additive evolution.

## 43. Kiểm tra cấu hình Jackson thực tế

Một test có thể tạo ObjectMapper mới nhưng production dùng mapper được Spring cấu hình, có module, mix-in, naming strategy và feature khác nhau.

Để test gần production:

- Dùng cùng factory/configuration tạo mapper.
- Kiểm tra FAIL_ON_UNKNOWN_PROPERTIES trên mapper đang được inject.
- Kiểm tra mix-in hoặc annotation ảnh hưởng target type.
- Kiểm tra custom deserializer có xử lý unknown property không.
- Kiểm tra JsonAnySetter và JsonIgnoreProperties trên nested DTO.

Không nên thay đổi mapper production trong lúc chạy để thử policy. Hãy tạo mapper test riêng hoặc dùng cấu hình test tương ứng.

## 44. Bảo đảm field mới không phá JSON Schema và OpenAPI

Nếu OpenAPI schema được khai báo:

~~~yaml
User:
  type: object
  properties:
    id:
      type: integer
    name:
      type: string
~~~

Việc bổ sung email vào schema giúp client mới biết field này. Nhưng cần xem schema có đóng object hay không, generator có tạo model strict không và gateway có validate theo schema cũ không.

Nếu JSON Schema dùng additionalProperties: false, field mới sẽ bị từ chối cho đến khi schema validator được cập nhật. Nếu schema cho phép additionalProperties, reader có thể tiếp nhận field chưa biết, tùy công cụ.

OpenAPI mô tả hợp đồng; nó không tự bảo đảm mọi client generator sẽ bỏ qua field chưa biết. Hãy kiểm tra code được sinh ra và runtime parser của các client quan trọng.

## 45. Versioning khi additive change không đủ

Nếu thay đổi không thể giữ tương thích, có thể cần version:

- Version URL như /v1/users và /v2/users.
- Version header hoặc media type.
- Version event type/schema.
- Field version trong envelope.

Ví dụ envelope:

~~~json
{
  "schemaVersion": 2,
  "eventType": "user-created",
  "data": {
    "id": 42,
    "displayName": "Mai"
  }
}
~~~

Version giúp consumer biết schema nào đang được gửi. Tuy nhiên, chỉ thêm schemaVersion không tự giải quyết việc reader cũ không biết field đó; reader cũ vẫn cần bỏ qua field mới hoặc nhận một endpoint/topic riêng.

Versioning phù hợp khi đổi cấu trúc, kiểu dữ liệu, semantics hoặc quy tắc bắt buộc mà không thể triển khai như một additive change an toàn.

## 46. Quy tắc deprecate và xóa field cũ

Thêm field mới có thể là bước đầu của quá trình đổi tên hoặc đổi cấu trúc. Nên có lộ trình:

1. Thêm field mới và tiếp tục phát field cũ.
2. Cập nhật reader để đọc field mới, fallback field cũ.
3. Theo dõi tỷ lệ consumer đã chuyển sang field mới.
4. Đánh dấu field cũ deprecated trong tài liệu.
5. Ngừng phát field cũ trong một phiên bản có thông báo.
6. Chỉ xóa field cũ khi consumer không còn phụ thuộc.

Không nên xóa field cũ chỉ vì consumer chính đã được nâng cấp. Có thể còn consumer ít được quan sát như batch job, dashboard, script hoặc tích hợp đối tác.

## 47. Các tình huống thêm field không an toàn

| Tình huống | Vì sao có thể phá tương thích | Hướng xử lý |
|---|---|---|
| Reader cũ bật FAIL_ON_UNKNOWN_PROPERTIES | Field mới gây UnrecognizedPropertyException | Cập nhật reader hoặc policy tolerant |
| JSON Schema đóng bằng additionalProperties false | Validator từ chối field mới | Cập nhật schema/gateway trước |
| Field mới nằm trong nested DTO strict | Reader root vẫn có thể thất bại ở object con | Kiểm tra và cấu hình nested type |
| Field mới là required creator property | Payload cũ thiếu field và không tạo được object | Default trong creator hoặc rollout reader trước |
| Field mới có explicit null nhưng setter không chấp nhận | Payload có field null gây lỗi hoặc mất default | Định nghĩa null policy |
| Thêm enum value | Reader cũ không nhận diện giá trị mới | Rollout consumer hoặc fallback an toàn |
| Thêm subtype/type id | Reader cũ không resolve subtype | Đồng bộ subtype registry/version |
| Reader cũ làm proxy | Unknown field bị bỏ và mất khi phát lại | Giữ extension data hoặc JsonNode |
| Client request strict | Server cũ từ chối field client mới gửi | Tách policy request và response |
| Field mới làm thay đổi semantics | JSON parse được nhưng kết quả nghiệp vụ sai | Field mới/version schema, tài liệu hóa semantics |

## 48. Checklist triển khai một field mới

Trước khi producer bắt đầu phát field:

- Xác định field mới là optional hay required.
- Xác định default khi field bị thiếu.
- Xác định hành vi khi field có null.
- Kiểm tra reader cũ có bỏ qua unknown properties không.
- Kiểm tra nested DTO, collection và Map.
- Kiểm tra enum/subtype nếu field mới liên quan polymorphism.
- Kiểm tra JSON Schema, OpenAPI, gateway và schema registry.
- Xác định consumer có round-trip hoặc forward payload không.
- Cập nhật tài liệu và contract tests.
- Lập thứ tự rollout producer/consumer.
- Theo dõi lỗi deserialize sau khi phát hành.

Sau khi phát hành:

- Theo dõi UnrecognizedPropertyException ở consumer strict.
- Theo dõi mapping errors của reader mới khi nhận payload cũ.
- Kiểm tra tỷ lệ field mới bị thiếu hoặc null.
- Xác nhận consumer dùng field mới đã thực sự nhận dữ liệu.
- Không xóa field cũ trước khi hoàn tất giai đoạn deprecation.

## 49. Ví dụ tổng hợp: thêm email vào User một cách tương thích

Phiên bản đầu:

~~~java
public class UserV1 {
    private long id;
    private String name;

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
}
~~~

Phiên bản mới:

~~~java
public class UserV2 {
    private long id;
    private String name;
    private String email;
    private String locale = "vi-VN";

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

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

Reader cũ tolerant:

~~~java
ObjectMapper oldReader = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Reader mới:

~~~java
ObjectMapper newReader = new ObjectMapper();
~~~

Payload mới:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": "mai@example.com",
  "locale": "vi-VN"
}
~~~

Reader cũ đọc được id và name, bỏ qua email và locale. Reader mới đọc payload cũ:

~~~json
{
  "id": 42,
  "name": "Mai"
}
~~~

và giữ default locale là vi-VN. Như vậy, hai chiều tương thích được kiểm tra riêng:

- Reader cũ chấp nhận field mới.
- Reader mới chấp nhận payload cũ thiếu field mới.

Nếu reader cũ cần forward toàn bộ dữ liệu, cần bổ sung cơ chế giữ unknown properties thay vì bỏ qua.

## 50. Nguyên tắc thực hành

- Xem thêm field vào object là additive change có điều kiện, không phải luôn an toàn.
- Phân biệt producer mới → reader cũ với reader mới → payload cũ.
- Kiểm tra FAIL_ON_UNKNOWN_PROPERTIES trên mapper thực tế.
- Dùng JsonIgnoreProperties(ignoreUnknown = true) cho DTO cần tolerant parsing.
- Dùng JsonAnySetter nếu cần giữ field mở rộng thay vì bỏ qua.
- Đặt default rõ ràng cho field mới khi đọc payload cũ.
- Phân biệt missing, null và empty.
- Dùng JsonSetter(nulls = Nulls.SKIP) hoặc Nulls.FAIL khi semantics yêu cầu.
- Không coi JsonProperty(defaultValue = ...) là cơ chế tự gán default.
- Với creator-based DTO, xử lý field mới trong constructor/factory và tránh required nếu cần đọc dữ liệu cũ.
- Giữ nguyên tên, kiểu và semantics của field hiện có.
- Kiểm tra field mới trong nested object và collection.
- Xem enum mới và subtype mới là thay đổi hợp đồng riêng.
- Kiểm tra JSON Schema, OpenAPI, gateway và các parser ngoài Jackson.
- Phân biệt response tolerant với request strict khi cần.
- Giữ unknown fields nếu consumer đóng vai trò proxy hoặc forwarder.
- Rollout reader trước producer khi reader mới cần field mới.
- Duy trì field cũ trong giai đoạn deprecation.
- Viết contract test cho cả hai chiều và các payload version cũ.

Thêm field vào JSON object có thể giữ tương thích với bên đọc cũ khi field đó thực sự tùy chọn và reader cũ chấp nhận property chưa biết. Reader mới cũng phải có cách xử lý payload cũ thiếu field, bao gồm default và chính sách null rõ ràng. Khi kiểm tra cả nested object, enum, subtype, schema validator và khả năng forward dữ liệu, việc mở rộng hợp đồng sẽ có cơ sở an toàn hơn thay vì chỉ dựa vào việc Jackson đọc được một ví dụ đơn lẻ.
