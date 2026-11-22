# Xử lý tên thuộc tính khác nhau giữa Java và JSON

Tên thuộc tính trong mô hình Java và tên trường trong JSON không nhất thiết phải giống nhau. Java thường dùng camelCase, trong khi API có thể dùng snake_case, kebab-case, tên viết tắt hoặc tên đã tồn tại từ một phiên bản hợp đồng cũ. Jackson cung cấp naming strategy và annotation để ánh xạ các tên này mà không buộc phải đổi tên field hoặc getter trong mã Java.

Ví dụ, lớp Java có thuộc tính firstName, nhưng JSON của đối tác sử dụng first_name:

~~~java
public class Customer {
    private String firstName;
}
~~~

~~~json
{
  "first_name": "Mai"
}
~~~

Jackson cần một quy tắc cho biết first_name tương ứng với thuộc tính Java firstName. Quy tắc đó có thể áp dụng chung cho nhiều thuộc tính, khai báo riêng cho một thuộc tính, hoặc chấp nhận nhiều tên đầu vào để tương thích ngược.

## 1. Tên Java và tên JSON là hai khái niệm riêng

Jackson làm việc với các thuộc tính logic (logical properties) được phát hiện từ field, getter, setter, constructor hoặc annotation. Tên thuộc tính logic này được liên kết với tên bên ngoài trong JSON.

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Tên thuộc tính Java | firstName | Tên trong mô hình và mã ứng dụng |
| Tên thuộc tính JSON | first_name | Tên xuất hiện trong văn bản JSON |
| Tên thay thế khi đọc | given_name | Tên cũ hoặc tên khác được chấp nhận ở đầu vào |
| Naming strategy | SNAKE_CASE | Quy tắc chuyển tên thuộc tính Java sang quy ước JSON |

Việc đổi tên trong JSON không nhất thiết làm thay đổi tên Java. Ứng dụng vẫn có thể gọi customer.getFirstName() trong khi JSON sử dụng first_name.

## 2. Đổi tên một thuộc tính bằng @JsonProperty

@JsonProperty khai báo tên thuộc tính bên ngoài mà Jackson sử dụng khi ánh xạ. Đây là lựa chọn trực tiếp khi chỉ một hoặc một vài thuộc tính có tên khác với tên Java.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {
    @JsonProperty("first_name")
    private String firstName;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
~~~

Khi đọc:

~~~java
String json = """
    {
      "first_name": "Mai"
    }
    """;

ObjectMapper mapper = new ObjectMapper();
Customer customer = mapper.readValue(json, Customer.class);

System.out.println(customer.getFirstName());
~~~

Khi ghi:

~~~java
String output = mapper.writeValueAsString(customer);
~~~

Tên thuộc tính được ghi ra là first_name. Vì vậy, @JsonProperty("first_name") thường áp dụng cho cả hai chiều: đọc tên JSON đó vào thuộc tính Java và dùng tên đó khi ghi thuộc tính ra JSON.

Có thể đặt annotation trên field, getter, setter hoặc tham số constructor. Jackson kết hợp metadata của các thành phần này thành một thuộc tính logic. Nên chọn một vị trí rõ ràng và tránh khai báo các tên xung đột trên field, getter và setter của cùng thuộc tính.

### Đặt tên trên getter hoặc setter

Khi muốn mô tả rõ chiều ghi hoặc chiều đọc, có thể dùng @JsonGetter và @JsonSetter:

~~~java
public class Customer {
    private String firstName;

    @JsonGetter("first_name")
    public String getFirstName() {
        return firstName;
    }

    @JsonSetter("first_name")
    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
~~~

@JsonGetter đánh dấu getter và tên thuộc tính dùng khi tuần tự hóa; @JsonSetter đánh dấu setter và tên thuộc tính dùng khi giải tuần tự hóa. Với trường hợp thông thường cần cùng một tên ở cả hai chiều, @JsonProperty thường ngắn gọn và dễ hiểu hơn.

## 3. Đổi tên hàng loạt bằng PropertyNamingStrategies

Khi nhiều thuộc tính cùng tuân theo một quy ước, có thể cấu hình naming strategy ở cấp ObjectMapper. Ví dụ, PropertyNamingStrategies.SNAKE_CASE chuyển tên Java dạng camelCase thành snake_case.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Với lớp:

~~~java
public class UserProfile {
    private String firstName;
    private String lastName;
    private String phoneNumber;

    // Constructor, getter và setter
}
~~~

JSON tương ứng có thể có dạng:

~~~json
{
  "first_name": "An",
  "last_name": "Nguyen",
  "phone_number": "0900000000"
}
~~~

Naming strategy được áp dụng trong quá trình Jackson khám phá thuộc tính của các lớp được xử lý bởi mapper. Vì vậy, quy tắc cũng có thể tác động đến các thuộc tính trong object lồng nhau và phần tử của collection, miễn là chúng là thuộc tính của bean được Jackson ánh xạ.

Một số naming strategy dựng sẵn thường gặp:

| Strategy | Ví dụ tên Java | Tên JSON điển hình |
|---|---|---|
| LOWER_CAMEL_CASE | firstName | firstName |
| SNAKE_CASE | firstName | first_name |
| KEBAB_CASE | firstName | first-name |
| LOWER_DOT_CASE | firstName | first.name |
| UPPER_CAMEL_CASE | firstName | FirstName |
| UPPER_SNAKE_CASE | firstName | FIRST_NAME |

Tên và hành vi cụ thể của strategy dựng sẵn phụ thuộc phiên bản Jackson. Trong dự án, hãy dùng các hằng trong PropertyNamingStrategies có sẵn ở phiên bản Databind đang sử dụng.

### Cấu hình naming strategy cho một lớp

Không phải lúc nào toàn bộ mapper cũng dùng chung một quy ước. Nếu chỉ một DTO cần tên snake_case, có thể dùng @JsonNaming:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class PartnerRequest {
    private String requestId;
    private String customerCode;

    // Constructor, getter và setter
}
~~~

Khi mapper đọc hoặc ghi PartnerRequest, Jackson áp dụng quy tắc snake_case cho các thuộc tính của lớp này. Những lớp khác vẫn theo cấu hình naming strategy chung của mapper.

@JsonNaming hữu ích khi một tích hợp có quy ước riêng, nhưng không muốn ảnh hưởng đến các DTO còn lại.

## 4. Chấp nhận nhiều tên đầu vào bằng @JsonAlias

Trong thực tế, một API có thể từng sử dụng tên customerName, sau đó đổi thành customer_name. Một số nguồn dữ liệu cũ vẫn gửi tên trước đây. Nếu muốn đọc được cả tên mới và tên cũ mà không thay đổi tên chuẩn khi ghi, có thể dùng @JsonAlias.

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {
    @JsonProperty("customer_name")
    @JsonAlias({"customerName", "full_name"})
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Các JSON sau đều có thể được đọc vào cùng thuộc tính name:

~~~json
{"customer_name": "Mai"}
~~~

~~~json
{"customerName": "Mai"}
~~~

~~~json
{"full_name": "Mai"}
~~~

Khi ghi đối tượng Customer, tên chuẩn là customer_name. Các alias chỉ được dùng để nhận diện tên khi giải tuần tự hóa; chúng không tạo ra nhiều trường trong JSON đầu ra.

Đây là điểm khác biệt quan trọng:

| Annotation | Đọc JSON | Ghi JSON |
|---|---|---|
| @JsonProperty("customer_name") | Nhận tên chuẩn customer_name | Ghi tên customer_name |
| @JsonAlias("customerName") | Chấp nhận thêm tên customerName | Không đổi tên chuẩn khi ghi |

@JsonAlias có từ Jackson 2.9. Nếu dự án sử dụng phiên bản cũ hơn, cần kiểm tra khả năng hỗ trợ hoặc xử lý tên cũ bằng một cơ chế tương thích khác.

### Alias không phải là quy tắc đổi tên hàng loạt

Alias phù hợp để chấp nhận một số tên cũ hoặc tên không đồng nhất của một thuộc tính. Nếu mọi thuộc tính đều có cùng quy ước camelCase sang snake_case, nên dùng naming strategy. Việc liệt kê alias cho hàng chục thuộc tính làm mô hình khó đọc và khó duy trì.

Không nên gán cùng một alias cho nhiều thuộc tính khác nhau. Khi một tên đầu vào có thể khớp với nhiều thuộc tính, dữ liệu trở nên mơ hồ và kết quả ánh xạ khó dự đoán.

## 5. Chỉ định quyền đọc và ghi của thuộc tính

Có trường hợp tên JSON giống nhau nhưng thuộc tính chỉ được phép đi theo một chiều. Ví dụ, API nhận mật khẩu khi tạo tài khoản nhưng không được trả mật khẩu trong response.

@JsonProperty hỗ trợ access để giới hạn chiều truy cập:

~~~java
public class AccountRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    // Constructor, getter và setter
}
~~~

Trong ngữ cảnh Jackson:

- WRITE_ONLY: thuộc tính được nhận khi đọc JSON vào Java, nhưng không được ghi ra JSON.
- READ_ONLY: thuộc tính được ghi ra JSON, nhưng bị bỏ qua khi đọc JSON vào Java.
- READ_WRITE: cho phép cả đọc và ghi; đây là hành vi thông thường.
- AUTO: để Jackson xác định theo cách phát hiện thuộc tính và cấu hình mặc định.

Ví dụ, khi đọc:

~~~json
{
  "username": "mai",
  "password": "secret"
}
~~~

Thuộc tính password có thể được gán vào đối tượng. Khi ghi đối tượng đó thành JSON, password không xuất hiện vì được đánh dấu WRITE_ONLY.

Không nên nhầm WRITE_ONLY trong JsonProperty.Access với tên gọi của thao tác Java. WRITE_ONLY có nghĩa JSON được phép ghi giá trị vào thuộc tính Java, còn thuộc tính không được xuất ra JSON. Hãy đọc quyền truy cập theo góc nhìn của luồng JSON.

## 6. Tên thuộc tính trong object lồng nhau

Naming strategy và annotation vẫn áp dụng cho các lớp con. Ví dụ:

~~~java
public class Address {
    private String postalCode;
    private String streetName;

    // Getter và setter
}

public class Customer {
    private String fullName;
    private Address shippingAddress;

    // Getter và setter
}
~~~

Với naming strategy snake_case ở mapper, JSON có thể là:

~~~json
{
  "full_name": "Mai Nguyen",
  "shipping_address": {
    "postal_code": "700000",
    "street_name": "Nguyen Hue"
  }
}
~~~

Quy tắc được áp dụng cho fullName, shippingAddress, postalCode và streetName theo từng lớp. Nếu chỉ một thuộc tính con có tên đặc biệt, có thể đặt @JsonProperty trực tiếp trên thuộc tính đó.

Với collection chứa DTO, tên trường của từng phần tử cũng được xử lý theo cấu hình của kiểu DTO:

~~~json
{
  "customers": [
    {
      "full_name": "Mai Nguyen"
    },
    {
      "full_name": "An Tran"
    }
  ]
}
~~~

Ở đây customers là thuộc tính của lớp bao; full_name là thuộc tính của từng Customer. Hai cấp có thể dùng cùng naming strategy hoặc được tùy chỉnh riêng theo lớp.

## 7. Ánh xạ tên trong constructor và record

Với lớp bất biến không có setter, Jackson có thể dùng constructor được đánh dấu @JsonCreator. Tên tham số cần được liên kết với tên JSON bằng @JsonProperty:

~~~java
public class Person {
    private final String firstName;

    @JsonCreator
    public Person(
            @JsonProperty("first_name") String firstName) {
        this.firstName = firstName;
    }

    public String getFirstName() {
        return firstName;
    }
}
~~~

JSON:

~~~json
{
  "first_name": "Mai"
}
~~~

Jackson sử dụng tên trong @JsonProperty để truyền giá trị cho tham số constructor. Khi ghi, getter getFirstName() vẫn được liên kết với thuộc tính logic tương ứng và có thể sử dụng tên bên ngoài đã khai báo.

Java record cũng có thể mô tả dữ liệu bất biến:

~~~java
public record Person(
    @JsonProperty("first_name") String firstName,
    @JsonProperty("last_name") String lastName
) {
}
~~~

Record component có tên Java riêng, trong khi annotation chỉ định tên JSON. Jackson hỗ trợ record trong các phiên bản hiện đại của dòng 2.x; với dự án cũ, cần xác nhận phiên bản Jackson và cấu hình creator đang dùng.

## 8. Khi không thể sửa lớp Java: dùng Mix-in

Một số lớp đến từ thư viện bên ngoài hoặc mã nguồn được sinh tự động. Nếu không thể thêm annotation trực tiếp, Jackson cho phép khai báo Mix-in để bổ sung metadata mà không sửa lớp gốc.

Giả sử có lớp bên thứ ba:

~~~java
public class ExternalUser {
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Có thể tạo Mix-in:

~~~java
abstract class ExternalUserMixin {
    @JsonProperty("display_name")
    abstract String getDisplayName();

    @JsonProperty("display_name")
    abstract void setDisplayName(String displayName);
}
~~~

Đăng ký với mapper:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
~~~

Jackson dùng annotation trong Mix-in khi xử lý ExternalUser. Cách này phù hợp để tùy chỉnh tên thuộc tính của lớp không thuộc quyền sở hữu của ứng dụng. Mix-in cần được đăng ký trong giai đoạn cấu hình mapper, trước khi mapper được chia sẻ và sử dụng.

## 9. Tên thuộc tính, chữ hoa chữ thường và tên thay thế

Tên JSON thường được so khớp chính xác theo quy tắc ánh xạ. Ví dụ first_name, First_Name và FIRST_NAME là các chuỗi khác nhau. Nếu API chỉ khác chữ hoa chữ thường, có thể cân nhắc MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES)
    .build();
~~~

Tùy chọn này cho phép so khớp tên thuộc tính không phân biệt chữ hoa chữ thường khi đọc. Nó không thay thế naming strategy và cũng không khai báo các tên tùy ý như given_name hoặc customer_title; với các tên khác biệt về từ ngữ, dùng @JsonAlias.

Phân biệt các nhu cầu:

| Nhu cầu | Cơ chế |
|---|---|
| firstName trong Java tương ứng first_name trong JSON | Naming strategy hoặc @JsonProperty |
| Chỉ một lớp dùng snake_case | @JsonNaming |
| Đọc được cả customer_name và customerName | @JsonAlias |
| Bỏ qua khác biệt chữ hoa/chữ thường khi đọc | ACCEPT_CASE_INSENSITIVE_PROPERTIES |
| Lớp thư viện ngoài cần tên JSON riêng | Mix-in |
| Chỉ nhận giá trị khi đọc, không xuất khi ghi | JsonProperty.Access.WRITE_ONLY |

## 10. Naming strategy không tự đổi mọi key của Map

Naming strategy chủ yếu áp dụng cho các thuộc tính bean mà Jackson khám phá. Một Map<String, Object> có key động như customerName không nhất thiết được đổi thành customer_name chỉ vì mapper dùng SNAKE_CASE.

Ví dụ:

~~~java
Map<String, Object> data = new LinkedHashMap<>();
data.put("customerName", "Mai");

String json = mapper.writeValueAsString(data);
~~~

Key của Map được xử lý theo cơ chế key serializer, không phải naming strategy của thuộc tính bean. Nếu hợp đồng yêu cầu đổi tên key động, cần chủ động chuẩn hóa key trước khi ghi hoặc đăng ký key serializer/deserializer phù hợp. Đối với key là một kiểu Java tùy chỉnh, Jackson cũng có cơ chế chuyển đổi key riêng.

## 11. Tránh xung đột tên thuộc tính

Khi nhiều thành phần cùng mô tả một thuộc tính, Jackson cần hợp nhất metadata của field, getter, setter và creator. Một số nguyên tắc giúp tránh xung đột:

- Dùng cùng tên JSON cho field, getter và setter nếu đặt annotation ở nhiều vị trí.
- Không ánh xạ hai thuộc tính Java khác nhau về cùng một tên JSON nếu không có thiết kế rõ ràng.
- Không dùng cùng một alias cho nhiều thuộc tính.
- Chỉ dùng naming strategy toàn cục khi các DTO trong phạm vi mapper thật sự theo cùng quy ước.
- Nếu một DTO có hợp đồng tên khác biệt, cân nhắc @JsonNaming hoặc @JsonProperty cục bộ.
- Khi thay đổi tên chuẩn của API, dùng alias để đọc dữ liệu cũ trong giai đoạn chuyển tiếp; ghi ra một tên chuẩn thống nhất.

Ví dụ một thuộc tính được đọc bằng tên cũ nhưng luôn ghi theo tên mới:

~~~java
public class Customer {
    @JsonProperty("display_name")
    @JsonAlias("name")
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Đầu vào có thể là {"name":"Mai"} hoặc {"display_name":"Mai"}. Đầu ra dùng tên chuẩn display_name. Nhờ đó, ứng dụng có thể tiếp nhận hợp đồng cũ trong khi dần chuyển sang hợp đồng mới.

## 12. Kiểm tra cả hai chiều đọc và ghi

Khi cấu hình tên thuộc tính, nên kiểm tra riêng hai chiều. Một cấu hình có thể giúp đọc được tên mong muốn nhưng vẫn ghi ra tên khác, đặc biệt khi dùng alias hoặc annotation chỉ áp dụng một chiều.

Ví dụ kiểm tra tên chuẩn và alias:

~~~java
ObjectMapper mapper = new ObjectMapper();

String oldJson = """
    {"name":"Mai"}
    """;

Customer customer = mapper.readValue(oldJson, Customer.class);

String newJson = mapper.writeValueAsString(customer);
System.out.println(newJson);
~~~

Kết quả ghi sử dụng tên chuẩn display_name, dù đầu vào dùng alias name.

Với naming strategy, có thể kiểm tra round-trip:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();

UserProfile profile = new UserProfile();
profile.setFirstName("An");
profile.setLastName("Nguyen");

String json = mapper.writeValueAsString(profile);
UserProfile copy = mapper.readValue(json, UserProfile.class);
~~~

Round-trip giúp xác nhận tên thuộc tính được ghi ra có thể được đọc lại vào đúng thuộc tính Java. Tuy nhiên, nếu ứng dụng cần tương thích với nhiều phiên bản API, vẫn cần kiểm tra từng tên đầu vào cũ và tên đầu ra chuẩn theo hợp đồng.

## 13. Lựa chọn cơ chế phù hợp

| Tình huống | Cách nên dùng | Lý do |
|---|---|---|
| Tất cả DTO dùng camelCase trong Java, snake_case trong JSON | Cấu hình SNAKE_CASE ở ObjectMapper | Một quy tắc chung, ít annotation lặp lại |
| Chỉ một DTO dùng quy ước tên riêng | @JsonNaming | Giới hạn phạm vi theo lớp |
| Một thuộc tính có tên JSON cố định khác tên Java | @JsonProperty | Rõ ràng ở đúng thuộc tính |
| API cũ và mới dùng nhiều tên cho cùng trường | @JsonAlias kết hợp tên chuẩn | Đọc tương thích, ghi thống nhất |
| Tên đọc và tên ghi khác nhau có chủ đích | @JsonSetter và @JsonGetter, hoặc quyền truy cập của @JsonProperty | Mô tả rõ từng chiều |
| Lớp thuộc thư viện ngoài | Mix-in | Không cần sửa mã nguồn gốc |
| Key động trong Map cần đổi tên | Chuẩn hóa key hoặc key serializer | Naming strategy bean không xử lý key Map tùy ý |

Trong quá trình thiết kế hợp đồng JSON, nên giữ tên Java dễ đọc theo quy ước của ngôn ngữ và mô tả tên bên ngoài bằng cấu hình Jackson. Cách này giúp mô hình Java không bị phụ thuộc quá chặt vào cách đặt tên của một API cụ thể, đồng thời cho phép tiếp nhận tên cũ và ghi ra tên chuẩn một cách có kiểm soát.
