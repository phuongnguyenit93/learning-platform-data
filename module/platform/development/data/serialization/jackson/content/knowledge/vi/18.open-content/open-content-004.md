# Làm phẳng cấu trúc bằng JsonUnwrapped

Một DTO Java thường chứa các object con để mô hình hóa dữ liệu theo nhóm. Ví dụ, `Customer` có thể chứa `ContactName` và `Address`. Cách serialize mặc định của Jackson giữ cấu trúc lồng nhau: mỗi object con trở thành một JSON object nằm dưới property tương ứng.

Trong một số hợp đồng API, client cần nhận các thuộc tính của object con trực tiếp ở cấp cha. Jackson cung cấp annotation **`@JsonUnwrapped`** để làm phẳng một property kiểu POJO khi serialize và deserialize. Thay vì ghi một object wrapper, Jackson ghi các property của object con vào cùng object JSON với các property của cha.

`@JsonUnwrapped` có thể thêm `prefix` hoặc `suffix` để phân biệt tên property sau khi làm phẳng. Đây là cách hữu ích để chuyển đổi giữa model Java có cấu trúc và JSON có cấu trúc phẳng mà không phải tự viết serializer/deserializer cho trường hợp POJO thông thường.

## 1. Cấu trúc lồng nhau mặc định

Giả sử ứng dụng có hai lớp:

```java
public class ContactName {
    private String firstName;
    private String lastName;

    public ContactName() {
    }

    public ContactName(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }
}

public class Customer {
    private long id;
    private ContactName name;

    public Customer() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public ContactName getName() {
        return name;
    }

    public void setName(ContactName name) {
        this.name = name;
    }
}
```

Khi serialize một `Customer` bình thường, Jackson tạo object `name` lồng bên trong:

```json
{
  "id": 25,
  "name": {
    "firstName": "An",
    "lastName": "Nguyen"
  }
}
```

Đây là cấu trúc tự nhiên nếu API muốn thể hiện rõ quan hệ giữa `Customer` và `ContactName`. Nhưng nếu hợp đồng yêu cầu `firstName` và `lastName` nằm ngang hàng với `id`, ta có thể dùng `@JsonUnwrapped`.

## 2. Làm phẳng POJO bằng @JsonUnwrapped

Đặt annotation trên property chứa object con:

```java
public class Customer {
    private long id;

    @JsonUnwrapped
    private ContactName name;

    public Customer() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public ContactName getName() {
        return name;
    }

    public void setName(ContactName name) {
        this.name = name;
    }
}
```

Jackson ghi các property của `ContactName` trực tiếp vào object JSON cha:

```json
{
  "id": 25,
  "firstName": "An",
  "lastName": "Nguyen"
}
```

Tên property Java `name` không còn xuất hiện như một wrapper JSON. Các property bên trong `ContactName` được đưa lên cùng cấp với `id`.

### 2.1. Ví dụ serialize

```java
ObjectMapper mapper = new ObjectMapper();

Customer customer = new Customer();
customer.setId(25L);
customer.setName(new ContactName("An", "Nguyen"));

String json = mapper.writeValueAsString(customer);
System.out.println(json);
```

Kết quả có cấu trúc phẳng:

```json
{
  "id": 25,
  "firstName": "An",
  "lastName": "Nguyen"
}
```

### 2.2. Ví dụ deserialize

`@JsonUnwrapped` cũng cho phép Jackson ánh xạ các property phẳng trở lại object con:

```java
String json = """
    {
      "id": 25,
      "firstName": "An",
      "lastName": "Nguyen"
    }
    """;

Customer customer = mapper.readValue(json, Customer.class);

System.out.println(customer.getId());
System.out.println(customer.getName().getFirstName());
```

Jackson nhận các field `firstName` và `lastName` ở object cha, sau đó chuyển chúng vào các property tương ứng của `ContactName`.

Điều này giúp giữ model Java có cấu trúc trong khi đáp ứng hợp đồng JSON phẳng. Không cần viết code thủ công để copy từng field từ JSON cha vào object con trong trường hợp POJO được hỗ trợ thông thường.

## 3. Thêm prefix để phân biệt tên property

Khi object cha có nhiều object con, tên property bên trong chúng có thể trùng nhau. Ví dụ `BillingAddress` và `ShippingAddress` đều có `city`, `street` và `postalCode`. Nếu làm phẳng cả hai mà không đổi tên, JSON có thể có tên field trùng lặp.

`@JsonUnwrapped` hỗ trợ thuộc tính `prefix`:

```java
public class Customer {
    private long id;

    @JsonUnwrapped(prefix = "billing_")
    private Address billingAddress;

    @JsonUnwrapped(prefix = "shipping_")
    private Address shippingAddress;

    // Getter và setter
}
```

Với `Address` có các property `street`, `city` và `postalCode`, JSON có dạng:

```json
{
  "id": 25,
  "billing_street": "12 Nguyen Hue",
  "billing_city": "Ho Chi Minh City",
  "billing_postalCode": "700000",
  "shipping_street": "8 Le Loi",
  "shipping_city": "Da Nang",
  "shipping_postalCode": "550000"
}
```

Prefix được thêm vào tên property của object con trong JSON. Khi deserialize, Jackson dùng cùng quy tắc để nhận diện và loại prefix trước khi gán giá trị cho property bên trong object con.

### 3.1. Prefix có thể biểu diễn namespace của object con

Prefix không chỉ dùng để tránh trùng tên. Nó còn giúp người đọc JSON nhận ra nguồn gốc của từng field:

```json
{
  "customer_id": 25,
  "contact_firstName": "An",
  "contact_lastName": "Nguyen"
}
```

Một cấu hình tương ứng:

```java
public class Customer {
    @JsonProperty("customer_id")
    private long id;

    @JsonUnwrapped(prefix = "contact_")
    private ContactName contact;
}
```

Tên JSON của property cha và prefix của object con cần được thiết kế nhất quán theo hợp đồng API. Không nên chọn prefix chỉ dựa trên tên field Java nếu API đã có tên chuẩn riêng.

## 4. Dùng suffix để phân biệt tên property

Ngoài prefix, annotation hỗ trợ `suffix` để nối chuỗi vào cuối tên property của object con:

```java
public class Measurement {
    private String sensorId;

    @JsonUnwrapped(suffix = "_value")
    private Reading reading;

    // Getter và setter
}
```

Nếu `Reading` có các property `temperature` và `humidity`, JSON sẽ có các tên như:

```json
{
  "sensorId": "S-01",
  "temperature_value": 28.5,
  "humidity_value": 0.72
}
```

Suffix hữu ích khi tên field cần mang một hậu tố chung theo quy ước của giao thức hoặc khi prefix đã được dùng cho một mục đích khác.

### 4.1. Kết hợp prefix và suffix

Có thể sử dụng cả hai:

```java
public class Measurement {
    @JsonUnwrapped(prefix = "environment_", suffix = "_reading")
    private Reading reading;
}
```

Các property con sẽ được thêm phần đầu và phần cuối theo cấu hình, ví dụ `environment_temperature_reading`. Cách đặt tên này có thể hữu ích cho schema cũ, nhưng không nên làm tên JSON quá dài hoặc khó đọc nếu không có yêu cầu tương thích cụ thể.

## 5. Dùng @JsonUnwrapped trên field hoặc accessor

Annotation có thể đặt trên field hoặc getter tương ứng với property cần làm phẳng:

```java
public class Customer {
    private long id;
    private ContactName name;

    public long getId() {
        return id;
    }

    @JsonUnwrapped(prefix = "name_")
    public ContactName getName() {
        return name;
    }

    public void setName(ContactName name) {
        this.name = name;
    }
}
```

Jackson dùng annotation trong quá trình introspection property. Nếu field và getter cùng đại diện cho một logical property, nên đặt annotation nhất quán và tránh tạo các khai báo xung đột.

Nếu model dùng Lombok, record, builder hoặc accessor tùy chỉnh, hãy xác định accessor thực tế mà Jackson nhìn thấy. Không nên giả định annotation đặt trên một field luôn hoạt động như mong muốn nếu visibility hoặc cách tạo property đã bị thay đổi.

### 5.1. Tắt unwrapping bằng enabled = false

`@JsonUnwrapped` có thuộc tính `enabled`. Có thể đặt `false` để vô hiệu hóa unwrapping ở vị trí annotation đó:

```java
@JsonUnwrapped(enabled = false)
private ContactName name;
```

Trong trường hợp này, property được xử lý theo cấu trúc lồng nhau thông thường thay vì làm phẳng. Thuộc tính này hữu ích khi annotation được cung cấp qua cấu hình hoặc meta-annotation nhưng một property cụ thể cần giữ wrapper.

## 6. Xử lý xung đột tên sau khi làm phẳng

Tên property của object cha và object con có thể trùng nhau. Ví dụ:

```java
public class Customer {
    private String id;

    @JsonUnwrapped
    private ExternalReference reference;
}

public class ExternalReference {
    private String id;
}
```

Cả `Customer.id` và `ExternalReference.id` đều có thể được serialize thành key `id`. JSON có thể xuất hiện hai key cùng tên hoặc trở nên mơ hồ với client. Khi deserialize, không thể biểu diễn rõ hai giá trị khác nhau bằng một key duy nhất.

Giải pháp là dùng prefix hoặc suffix:

```java
public class Customer {
    private String id;

    @JsonUnwrapped(prefix = "external_")
    private ExternalReference reference;
}
```

Kết quả:

```json
{
  "id": "C-25",
  "external_id": "CRM-900"
}
```

### 6.1. Kiểm tra xung đột trong toàn bộ object

Khi thiết kế JSON phẳng, hãy kiểm tra tên sau khi áp dụng:

- Tên property trực tiếp của object cha.
- Tên property của object con sau prefix/suffix.
- Tên do `@JsonProperty` hoặc naming strategy tạo ra.
- Tên từ các object khác cũng được unwrapped.

Không chỉ kiểm tra source field. Hai field Java khác tên vẫn có thể tạo cùng tên JSON sau khi áp dụng annotation hoặc naming strategy.

JSON object có key trùng lặp không phải hợp đồng an toàn: parser và client có thể xử lý key lặp theo cách khác nhau, chẳng hạn giữ giá trị đầu hoặc cuối. Hãy bảo đảm các tên sau khi làm phẳng là duy nhất.

## 7. @JsonUnwrapped làm việc với loại dữ liệu nào?

`@JsonUnwrapped` được thiết kế để làm phẳng property kiểu POJO có các property con mà Jackson có thể introspect và serialize/deserialize như một object.

Ví dụ phù hợp:

```java
public class Person {
    private String firstName;
    private String lastName;
}

public class Employee {
    @JsonUnwrapped
    private Person person;
}
```

Các kiểu cấu trúc như `Map`, `Collection` hoặc array không thể được unwrapped theo cùng cơ chế property-based này:

```java
public class Report {
    @JsonUnwrapped
    private Map<String, Object> attributes; // Không phải trường hợp JsonUnwrapped hỗ trợ
}
```

Một map có các key động, còn collection/array có phần tử theo chỉ số; chúng không có tập bean property cố định để Jackson đưa lên object cha. Nếu cần làm phẳng map, hãy xem `@JsonAnyGetter` và `@JsonAnySetter` hoặc viết serializer/deserializer tùy chỉnh.

### 7.1. Không dùng JsonUnwrapped để flatten collection

Nếu object con chứa `List<String> tags`, bản thân property `tags` vẫn là một property của POJO và có thể được serialize bình thường bên trong object cha:

```java
public class ProfileDetails {
    private String displayName;
    private List<String> tags;
}

public class Profile {
    @JsonUnwrapped
    private ProfileDetails details;
}
```

JSON có thể có dạng:

```json
{
  "displayName": "An",
  "tags": ["java", "jackson"]
}
```

Điều này khác với việc đặt `@JsonUnwrapped` trực tiếp lên một property `List` hoặc `Map`. Annotation làm phẳng các bean property của POJO; giá trị collection bên trong từng property vẫn giữ hình dạng JSON array như bình thường.

## 8. Hạn chế với polymorphic type information

`@JsonUnwrapped` không phù hợp với polymorphic type handling cần ghi type id như `@JsonTypeInfo`. Khi object con bị làm phẳng, không còn một object wrapper riêng để đặt metadata type theo cấu trúc thông thường. Vì vậy, kết hợp unwrapping với type information polymorphic có thể không được hỗ trợ hoặc không tạo được hợp đồng JSON mong muốn.

Ví dụ, nếu `PaymentDetails` có nhiều subtype và dùng `@JsonTypeInfo` để phân biệt `CardPayment` với `BankTransfer`, không nên giả định có thể unwrapped property đó mà vẫn giữ cơ chế type id mặc định.

Các lựa chọn thiết kế:

- Giữ object con lồng nhau để type metadata có vị trí rõ ràng.
- Đưa discriminator thành property tường minh trong object cha và tự ánh xạ subtype theo hợp đồng API.
- Dùng custom serializer/deserializer nếu định dạng phẳng là yêu cầu bắt buộc.

Hãy kiểm tra cả chiều serialize và deserialize. Việc output có thể được ghi theo một cấu trúc tùy chỉnh không có nghĩa Jackson tự suy ra subtype tương ứng khi đọc lại.

## 9. Creator, immutable object và model đặc biệt

`@JsonUnwrapped` đơn giản nhất khi object con là bean có thể được tạo và gán property theo cách thông thường. Với object bất biến chỉ có constructor tham số, factory method, record hoặc creator-based deserialization, việc phân phối các field phẳng vào tham số creator phức tạp hơn.

Không nên giả định rằng thêm `@JsonUnwrapped` vào constructor parameter là đủ cho mọi phiên bản Jackson và mọi kiểu creator. Hãy kiểm tra khả năng hỗ trợ của phiên bản đang dùng và viết round-trip test với đúng mapper production.

Nếu mô hình bất biến không tương thích với cách unwrapping đang dùng, các lựa chọn thực tế gồm:

- Dùng DTO trung gian có setter/default constructor để nhận JSON phẳng, rồi chuyển sang domain object bất biến.
- Viết custom deserializer để đọc field phẳng và gọi constructor/factory method.
- Giữ JSON lồng nhau nếu không có yêu cầu bắt buộc phải flatten.

Đối với custom serializer của object con, Jackson cần serializer hỗ trợ cơ chế unwrapping. Một serializer tùy chỉnh chỉ ghi một object thông thường có thể không thể tự động được chuyển thành các field phẳng. Khi viết serializer riêng, cần triển khai/hỗ trợ unwrapping tương ứng hoặc điều khiển cấu trúc ở serializer của object cha.

## 10. Dùng @JsonAnyGetter khi cần flatten Map

Nếu mục tiêu là đưa các entry của một `Map<String, Object>` lên object cha, `@JsonAnyGetter` phù hợp hơn `@JsonUnwrapped`:

```java
public class Event {
    private String type;
    private Map<String, Object> attributes = new LinkedHashMap<>();

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    @JsonAnyGetter
    public Map<String, Object> getAttributes() {
        return attributes;
    }
}
```

Với dữ liệu:

```java
event.setType("user-created");
event.getAttributes().put("userId", 25);
event.getAttributes().put("source", "web");
```

Output có dạng:

```json
{
  "type": "user-created",
  "userId": 25,
  "source": "web"
}
```

`@JsonAnyGetter` lấy các entry của map và ghi chúng như property bổ sung trong object. Đây là cơ chế phù hợp với tên field động.

Để nhận lại các field không được khai báo thành property thông thường, có thể dùng `@JsonAnySetter`:

```java
public class Event {
    private String type;
    private Map<String, Object> attributes = new LinkedHashMap<>();

    @JsonAnySetter
    public void addAttribute(String name, Object value) {
        attributes.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> getAttributes() {
        return attributes;
    }
}
```

`@JsonAnyGetter`/`@JsonAnySetter` giải quyết property động; `@JsonUnwrapped` giải quyết bean property cố định của một POJO con. Hai cơ chế có mục đích khác nhau.

## 11. Kết hợp JsonUnwrapped với naming strategy và JsonProperty

Jackson có thể áp dụng naming strategy cho property của object con. Nếu mapper dùng snake case:

```java
ObjectMapper mapper = new ObjectMapper()
    .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Các property Java `firstName` và `lastName` thường được xuất thành `first_name` và `last_name`. Nếu object con có prefix, tên cuối cùng chịu ảnh hưởng của cả quy tắc tên property và cấu hình unwrapping. Hãy kiểm tra JSON thực tế bằng mapper đang dùng, nhất là khi prefix/suffix cũng chứa dấu gạch dưới hoặc khi property có `@JsonProperty`.

Ví dụ dùng tên JSON tường minh:

```java
public class ContactName {
    @JsonProperty("given_name")
    private String firstName;

    @JsonProperty("family_name")
    private String lastName;
}

public class Customer {
    @JsonUnwrapped(prefix = "contact_")
    private ContactName name;
}
```

Hợp đồng mong muốn là các field phẳng có tiền tố `contact_` cùng tên JSON đã quy định cho property con. Với naming strategy hoặc mix-in phức tạp, test serialize và deserialize là cách xác nhận chính xác nhất.

## 12. JsonUnwrapped và JsonInclude

`@JsonInclude` có thể được dùng cho property bên trong object con đã được unwrapped. Ví dụ:

```java
public class ContactName {
    private String firstName;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String middleName;

    private String lastName;
}

public class Customer {
    @JsonUnwrapped(prefix = "name_")
    private ContactName name;
}
```

Nếu `middleName` là null, field `name_middleName` bị bỏ theo chính sách inclusion của property đó. Các property còn lại được đưa lên object cha.

Hãy phân biệt hai quyết định:

- `@JsonUnwrapped` quyết định property con được đặt ở cấp JSON nào và tên được biến đổi ra sao.
- `@JsonInclude` quyết định property/value nào bị bỏ theo điều kiện inclusion.

Nếu object con là null, không có các bean property con để làm phẳng. Nếu hợp đồng cần biểu diễn trạng thái “object con chưa có” một cách rõ ràng, hãy thiết kế một field trạng thái riêng hoặc dùng cấu trúc lồng nhau thay vì dựa vào wrapper đã bị loại bỏ.

## 13. Kiểm thử serialize và deserialize

Vì `@JsonUnwrapped` thay đổi tên và cấp của nhiều property, nên kiểm tra cả hai chiều. Ví dụ JUnit:

```java
class CustomerUnwrappedTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void serializesNamePropertiesAtCustomerLevel() throws Exception {
        Customer customer = new Customer();
        customer.setId(25L);
        customer.setName(new ContactName("An", "Nguyen"));

        JsonNode json = mapper.readTree(mapper.writeValueAsString(customer));

        assertEquals(25, json.get("id").asLong());
        assertEquals("An", json.get("firstName").asText());
        assertEquals("Nguyen", json.get("lastName").asText());
        assertFalse(json.has("name"));
    }

    @Test
    void deserializesFlatPropertiesIntoNestedObject() throws Exception {
        String json = """
            {
              "id": 25,
              "firstName": "An",
              "lastName": "Nguyen"
            }
            """;

        Customer customer = mapper.readValue(json, Customer.class);

        assertEquals(25L, customer.getId());
        assertNotNull(customer.getName());
        assertEquals("An", customer.getName().getFirstName());
        assertEquals("Nguyen", customer.getName().getLastName());
    }
}
```

Test xác nhận JSON không có wrapper `name`, nhưng object Java sau deserialize vẫn có `ContactName` được khởi tạo và gán các giá trị tương ứng.

### 13.1. Kiểm tra prefix và suffix

Khi dùng prefix/suffix, test nên xác nhận đúng tên JSON và không còn tên cũ:

```java
JsonNode json = mapper.readTree(mapper.writeValueAsString(customer));

assertTrue(json.has("contact_firstName"));
assertTrue(json.has("contact_lastName"));
assertFalse(json.has("firstName"));
assertFalse(json.has("name"));
```

Sau đó deserialize JSON có các key prefixed để xác nhận Jackson loại prefix khi ánh xạ về object con.

### 13.2. Kiểm tra tên bị trùng

Nếu object cha và object con có thể tạo cùng tên, hãy thêm test cho cấu hình prefix/suffix và xác nhận mọi key là duy nhất. Không chỉ kiểm tra output bằng cách đọc lại `JsonNode`, vì một tree parser có thể giữ một trong các giá trị khi JSON đầu vào có key trùng. Nên kiểm tra chính sách tên từ thiết kế và test output text/stream khi cần phát hiện duplicate key.

## 14. Lựa chọn giữa JsonUnwrapped và các cách làm phẳng khác

| Cơ chế | Dùng khi | Đặc điểm |
|---|---|---|
| `@JsonUnwrapped` | Một property POJO có tập bean property cố định cần đưa lên object cha | Hỗ trợ prefix/suffix và mapping hai chiều trong trường hợp được hỗ trợ |
| `@JsonAnyGetter` | Cần ghi các entry Map như property động | Phù hợp với key không biết trước |
| `@JsonAnySetter` | Cần nhận các property JSON không khai báo vào Map hoặc handler | Thường kết hợp với any-getter để round-trip dữ liệu mở |
| Custom serializer/deserializer | Cấu trúc phẳng có quy tắc đặc biệt, polymorphism hoặc chuyển đổi không chuẩn | Kiểm soát đầy đủ nhưng cần tự duy trì logic hai chiều |
| DTO phẳng riêng | Hợp đồng API cần ổn định và khác domain model | Mapping rõ ràng, dễ kiểm soát validation và versioning |

Không nên dùng `@JsonUnwrapped` chỉ để tiết kiệm một cấp object nếu cấu trúc lồng nhau giúp hợp đồng dễ hiểu hơn. Flattening làm tên property của object con trở thành một phần trực tiếp của schema cha, vì vậy thay đổi tên field con có thể trở thành thay đổi API bên ngoài.

## 15. Những lỗi thường gặp

**Đặt `@JsonUnwrapped` lên Map, List hoặc array.** Annotation được thiết kế cho POJO có bean property, không phải cấu trúc map/collection. Dùng `@JsonAnyGetter`/`@JsonAnySetter` cho map động hoặc custom serializer.

**Hai object con tạo cùng tên property.** Dùng prefix/suffix để tạo namespace riêng và kiểm tra tên sau khi áp dụng naming strategy.

**Object con có type metadata polymorphic.** Unwrapping không tương thích với cách ghi type id thông thường của `@JsonTypeInfo`. Giữ wrapper hoặc thiết kế discriminator/custom mapping riêng.

**Chỉ kiểm tra serialize mà không kiểm tra deserialize.** Một JSON phẳng có thể được ghi ra nhưng chưa chắc có thể đọc lại vào model dự kiến. Luôn test cả hai chiều nếu API cần round-trip.

**Dùng constructor/record bất biến mà không xác nhận hỗ trợ.** Creator-based deserialization có những giới hạn riêng khi phân phối field phẳng. Dùng DTO trung gian hoặc custom deserializer nếu cần.

**Custom serializer không hỗ trợ unwrapping.** Serializer tự viết cần hỗ trợ cơ chế unwrapping; nếu không, hãy để serializer của object cha điều khiển token hoặc dùng mapping riêng.

**Mong prefix/suffix thay đổi tên property Java.** Chúng chỉ biến đổi tên trong JSON, không đổi field/getter trong object Java.

**Dùng JsonInclude để giải quyết xung đột tên.** Inclusion chỉ bỏ property theo giá trị, không bảo đảm hai property còn lại có tên khác nhau. Hãy giải quyết bằng prefix/suffix hoặc thiết kế schema.

**Cho rằng field private tự được serialize vì có JsonUnwrapped.** Annotation không tự thay thế quy tắc visibility và introspection của Jackson. Property con và property cha vẫn phải được nhận diện theo cấu hình thông thường.

## 16. Quy trình triển khai JsonUnwrapped

1. Xác định property Java nào là POJO con cần làm phẳng.
2. Xác nhận JSON contract yêu cầu các field con nằm ngang hàng với field cha.
3. Đặt `@JsonUnwrapped` trên property tương ứng.
4. Kiểm tra tên property con có trùng với tên của cha hoặc object con khác không.
5. Nếu có nguy cơ trùng, chọn `prefix` hoặc `suffix` ổn định theo hợp đồng API.
6. Xác nhận kiểu con là POJO được Jackson hỗ trợ; không áp dụng trực tiếp cho Map, Collection hoặc array.
7. Kiểm tra các giới hạn với polymorphic type, creator-based immutable model và custom serializer.
8. Serialize một object đại diện và xác nhận không còn wrapper JSON ngoài ý muốn.
9. Deserialize JSON phẳng và xác nhận object con được khôi phục đúng.
10. Thêm test cho null, property thiếu, prefix/suffix, tên trùng và naming strategy nếu có.

## Kết luận

`@JsonUnwrapped` làm phẳng các bean property của một POJO con bằng cách đưa chúng lên cùng object JSON với property của cha. `prefix` và `suffix` giúp tạo tên duy nhất, tránh xung đột khi nhiều object con có các field giống nhau. Annotation hỗ trợ cả serialize và deserialize trong các trường hợp POJO thông thường, nhưng không phải cơ chế flatten cho Map, Collection hoặc array và cần cân nhắc các giới hạn với polymorphic type handling, creator-based model và custom serializer. Hãy thiết kế tên JSON như một phần của hợp đồng API, kiểm tra cả hai chiều và dùng `@JsonAnyGetter` hoặc custom mapping khi dữ liệu có key động hoặc cấu trúc đặc biệt.
