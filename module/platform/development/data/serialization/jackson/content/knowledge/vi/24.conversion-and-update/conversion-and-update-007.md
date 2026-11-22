# Xử lý cập nhật thuộc tính vắng mặt, null và đối tượng lồng

Khi API nhận một JSON dùng để cập nhật object Java đã tồn tại, cần phân biệt rõ ba trạng thái: property không xuất hiện trong JSON, property xuất hiện với giá trị `null`, và property xuất hiện với một object lồng có thể chỉ chứa một vài field. Ba trường hợp này có ý nghĩa khác nhau đối với dữ liệu hiện tại.

Ví dụ một hồ sơ đang có:

```json
{
  "name": "An",
  "phone": "0900000000",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Nguyen Hue"
  }
}
```

Request cập nhật:

```json
{
  "address": {
    "city": "Da Nang"
  },
  "phone": null
}
```

Ứng dụng cần quyết định:

- `name` không xuất hiện: giữ tên cũ hay đặt về null?
- `phone` xuất hiện với null: xóa số điện thoại, bỏ qua cập nhật hay báo lỗi?
- `address` chỉ có `city`: giữ `street` cũ hay thay toàn bộ address bằng object mới chỉ có city?

Jackson cung cấp `ObjectReader.readerForUpdating()`, annotation `@JsonMerge` và cấu hình null handling qua `@JsonSetter` để kiểm soát nhiều trường hợp này. Tuy nhiên, cần hiểu rõ mỗi cơ chế giải quyết phần nào và không đồng nhất chúng với một chuẩn HTTP PATCH cụ thể.

## 1. Phân biệt property vắng mặt, explicit null và giá trị mới

Khi deserialize một JSON vào object mới, property bị thiếu thường giữ giá trị mặc định của Java hoặc giá trị khởi tạo trong class. Khi cập nhật object đã tồn tại, property bị thiếu thường không được gán lại nên giá trị hiện tại được giữ nguyên.

Property có mặt với JSON `null` là trường hợp khác. Jackson đã nhận được chỉ dẫn rõ ràng rằng giá trị của property là null. Theo cấu hình mặc định đối với reference type, giá trị hiện tại có thể bị thay bằng null.

Property có mặt với một giá trị khác, chẳng hạn string, number hoặc object, sẽ được deserialize và gán theo cơ chế của kiểu đó.

| Trạng thái trong JSON | Ý nghĩa khi cập nhật object hiện có | Hành vi thường gặp |
| --- | --- | --- |
| Property không xuất hiện | Không gửi chỉ dẫn cập nhật property đó | Giữ nguyên giá trị hiện tại |
| `"phone": null` | Client gửi explicit null | Gán null theo mặc định, trừ khi cấu hình null handling khác |
| `"phone": "0912..."` | Client gửi giá trị mới | Deserialize rồi gán giá trị mới |
| `"address": {}` | Client gửi object rỗng | Mặc định có thể thay bằng object rỗng; với merge có thể không đổi field con nào |
| `"address": {"city":"Da Nang"}` | Client gửi một phần object con | Mặc định có thể thay object con; với `@JsonMerge` có thể cập nhật field city và giữ field khác |

Đừng gộp property thiếu và explicit null thành một trạng thái. Trong API cập nhật, chúng thường biểu đạt hai ý định khác nhau: “không thay đổi” và “xóa giá trị”.

## 2. Cập nhật object hiện có bằng readerForUpdating()

`ObjectMapper.readerForUpdating(existingValue)` tạo một `ObjectReader` được cấu hình để deserialize input vào object đã tồn tại. Jackson cập nhật các property có trong JSON và thường giữ nguyên property không có trong JSON.

Ví dụ DTO mutable:

```java
public class Profile {
    private String name;
    private String phone;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getPhone() {
        return phone;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }
}
```

Tạo object ban đầu và cập nhật:

```java
ObjectMapper mapper = new ObjectMapper();

Profile profile = new Profile();
profile.setName("An");
profile.setPhone("0900000000");

String updateJson = "{\"name\":\"An Nguyen\"}";

mapper.readerForUpdating(profile).readValue(updateJson);

System.out.println(profile.getName());  // An Nguyen
System.out.println(profile.getPhone()); // 0900000000
```

JSON không có property `phone`, vì vậy Jackson không cần gán lại property đó. Giá trị hiện có được giữ nguyên.

`readerForUpdating()` làm thay đổi object được truyền vào. Nó không tạo ra một bản sao độc lập để caller nhận về. Vì vậy, hãy truyền đúng object mà request được phép cập nhật và không chia sẻ cùng instance mutable cho nhiều request đồng thời.

## 3. Explicit null theo mặc định có thể xóa giá trị hiện tại

Với reference property, JSON null thường được gán thành Java null nếu không có cấu hình khác:

```java
String updateJson = "{\"phone\":null}";
mapper.readerForUpdating(profile).readValue(updateJson);

System.out.println(profile.getPhone()); // null
```

Đây có thể là hành vi đúng nếu API dùng null để yêu cầu xóa số điện thoại. Nhưng nếu null chỉ có nghĩa “không gửi giá trị”, cần cấu hình `Nulls.SKIP` hoặc xử lý patch theo quy tắc riêng.

Đối với primitive như `int` hoặc `boolean`, Java không có giá trị null. Jackson có thể coercion explicit null về giá trị mặc định của primitive nếu `FAIL_ON_NULL_FOR_PRIMITIVES` không bật. Nếu muốn từ chối null cho primitive, có thể bật feature:

```java
mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Trong DTO nhận request cập nhật, wrapper type như `Integer` và `Boolean` thường dễ biểu diễn trạng thái null hơn primitive. Dù vậy, wrapper vẫn cần quy tắc rõ ràng cho missing và explicit null.

## 4. Bỏ qua explicit null bằng @JsonSetter(nulls = Nulls.SKIP)

`@JsonSetter` cho phép định nghĩa cách Jackson xử lý JSON null khi gán một property. Với `Nulls.SKIP`, Jackson bỏ qua việc gán khi property xuất hiện với giá trị null.

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class Profile {
    private String name;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phone;

    // Getter và setter...
}
```

Khi cập nhật:

```json
{"phone":null}
```

Jackson không gán null vào `phone`, vì vậy giá trị cũ được giữ lại.

Điểm cần nhớ: `Nulls.SKIP` chỉ xử lý explicit null khi property được cung cấp. Property bị thiếu vốn đã không tạo một lần gán, nên giá trị cũ cũng được giữ nguyên trong quá trình update.

Với object mới, nếu field được khởi tạo trước bằng giá trị mặc định trong class, `Nulls.SKIP` có thể giữ giá trị khởi tạo đó. Nếu field chưa có giá trị, nó vẫn có thể là null. `SKIP` không tự tạo một giá trị mặc định có ý nghĩa nghiệp vụ.

## 5. Các lựa chọn null handling của Jackson

`Nulls` định nghĩa cách xử lý explicit JSON null cho property hoặc nội dung container:

| Giá trị | Hành vi tổng quát | Trường hợp sử dụng |
| --- | --- | --- |
| `SET` | Gán null theo hành vi thông thường | Null là một giá trị được chấp nhận |
| `SKIP` | Bỏ qua việc gán | Null có nghĩa không thay đổi giá trị hiện tại |
| `FAIL` | Ném lỗi khi gặp explicit null | Property không được phép nhận null |
| `AS_EMPTY` | Dùng empty value do deserializer cung cấp | Null được chuẩn hóa thành giá trị rỗng phù hợp kiểu |
| `DEFAULT` | Dùng chính sách mặc định của Jackson/property | Không chỉ định hành vi riêng |

Ví dụ từ chối explicit null:

```java
@JsonSetter(nulls = Nulls.FAIL)
private String accountId;
```

Ví dụ dùng empty value:

```java
@JsonSetter(nulls = Nulls.AS_EMPTY)
private List<String> tags = new ArrayList<>();
```

Với collection, empty value thường là collection rỗng theo khả năng của deserializer. Với kiểu khác, empty value phụ thuộc deserializer tương ứng; không nên giả định mọi kiểu đều có cùng một giá trị rỗng.

## 6. contentNulls xử lý null bên trong collection hoặc map

`nulls` điều khiển null của toàn bộ property. `contentNulls` điều khiển null của từng phần tử/value bên trong container.

Ví dụ:

```java
public class Profile {
    @JsonSetter(contentNulls = Nulls.SKIP)
    private List<String> tags = new ArrayList<>();
}
```

Với JSON:

```json
{"tags":["java",null,"jackson"]}
```

Jackson bỏ qua phần tử null khi deserialize nội dung list. List nhận được chứa `java` và `jackson`.

So sánh:

```java
@JsonSetter(nulls = Nulls.SKIP)
private List<String> tags;
```

Cấu hình này bỏ qua khi **cả property `tags`** có giá trị null:

```json
{"tags":null}
```

Trong khi:

```java
@JsonSetter(contentNulls = Nulls.SKIP)
private List<String> tags;
```

bỏ qua null ở từng phần tử bên trong array/list. Hai cấu hình có phạm vi khác nhau và có thể kết hợp:

```java
@JsonSetter(nulls = Nulls.SKIP, contentNulls = Nulls.FAIL)
private List<String> tags;
```

Ví dụ này giữ nguyên list hiện tại nếu toàn bộ property là null, nhưng từ chối nếu một phần tử bên trong list là null.

## 7. Cập nhật object lồng mặc định có thể thay thế object cũ

Xét model:

```java
public class Address {
    private String city;
    private String street;

    // Getter và setter...
}

public class Profile {
    private String name;
    private Address address;

    // Getter và setter...
}
```

Object hiện tại:

```java
Address address = new Address();
address.setCity("Ho Chi Minh City");
address.setStreet("Nguyen Hue");

Profile profile = new Profile();
profile.setName("An");
profile.setAddress(address);
```

Request chỉ gửi:

```json
{
  "address": {
    "city": "Da Nang"
  }
}
```

Nếu property `address` không được cấu hình merge, Jackson thường deserialize một `Address` mới từ object JSON rồi gán vào `profile.address`. Kết quả có thể là:

```json
{
  "city": "Da Nang",
  "street": null
}
```

Giá trị `street` cũ bị mất vì object con đã được thay bằng object mới. Đây là hành vi thay thế property, không phải cập nhật từng field bên trong object con hiện tại.

Nếu muốn giữ `street` và chỉ cập nhật `city`, cần khai báo merge cho property `address`.

## 8. Dùng @JsonMerge để cập nhật object lồng

`@JsonMerge` đánh dấu property có giá trị cấu trúc nên được merge vào giá trị hiện có thay vì thay thế toàn bộ property.

```java
import com.fasterxml.jackson.annotation.JsonMerge;

public class Profile {
    private String name;

    @JsonMerge
    private Address address;

    // Getter và setter...
}
```

Khi cập nhật bằng:

```java
String updateJson = """
        {
          "address": {
            "city": "Da Nang"
          }
        }
        """;

mapper.readerForUpdating(profile).readValue(updateJson);
```

Jackson dùng `Address` hiện có làm giá trị cần cập nhật. Field `city` nhận giá trị mới; field `street` không có trong JSON nên giữ giá trị cũ.

Kết quả logic:

```json
{
  "city": "Da Nang",
  "street": "Nguyen Hue"
}
```

`@JsonMerge` áp dụng cho property cụ thể. Nếu một class có nhiều object lồng, chỉ property được đánh dấu merge mới nhận hành vi này. Không nên cho rằng toàn bộ object graph sẽ tự động merge đệ quy chỉ vì root object được cập nhật.

## 9. Ví dụ tổng hợp: missing, null và nested merge

DTO:

```java
public class Profile {
    private String name;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phone;

    @JsonMerge
    private Address address;

    // Getter và setter...
}
```

Trạng thái ban đầu:

```java
Profile profile = new Profile();
profile.setName("An");
profile.setPhone("0900000000");

Address address = new Address();
address.setCity("Ho Chi Minh City");
address.setStreet("Nguyen Hue");
profile.setAddress(address);
```

Request cập nhật:

```json
{
  "address": {
    "city": "Da Nang"
  },
  "phone": null
}
```

Áp dụng:

```java
mapper.readerForUpdating(profile).readValue(updateJson);
```

Kết quả:

| Property | Trong JSON | Cấu hình | Kết quả |
| --- | --- | --- | --- |
| `name` | Vắng mặt | Không cần cấu hình đặc biệt | Giữ `An` |
| `phone` | Explicit null | `Nulls.SKIP` | Giữ `0900000000` |
| `address.city` | `Da Nang` | `@JsonMerge` trên `address` | Cập nhật thành `Da Nang` |
| `address.street` | Vắng mặt trong object con | `@JsonMerge` trên `address` | Giữ `Nguyen Hue` |

Ví dụ này minh họa cách dùng các cơ chế khác nhau cho từng ý định. Nếu API cần null để xóa phone, hãy bỏ `Nulls.SKIP` hoặc dùng một quy tắc cập nhật khác.

## 10. @JsonMerge với Map

Với map, merge thường hữu ích khi request chỉ gửi một số key cần thêm hoặc cập nhật:

```java
public class Profile {
    @JsonMerge
    private Map<String, String> preferences = new LinkedHashMap<>();

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void setPreferences(Map<String, String> preferences) {
        this.preferences = preferences;
    }
}
```

Giá trị ban đầu:

```json
{
  "theme": "dark",
  "language": "vi",
  "timezone": "Asia/Ho_Chi_Minh"
}
```

JSON cập nhật:

```json
{
  "preferences": {
    "theme": "light",
    "language": null
  }
}
```

Với merge map, entry `theme` được cập nhật; key không được gửi như `timezone` được giữ nguyên. Entry `language` được xử lý theo null policy của value/map content. Nếu không cấu hình content null handling khác, null có thể thay value hiện tại bằng null.

Có thể bỏ qua null value trong map:

```java
@JsonMerge
@JsonSetter(contentNulls = Nulls.SKIP)
private Map<String, String> preferences = new LinkedHashMap<>();
```

Khi đó, explicit null cho một entry không thay đổi value cũ. Cần kiểm thử đúng kiểu map và phiên bản Jackson đang dùng nếu map value là object lồng, vì việc merge value phức tạp có thể phụ thuộc deserializer của kiểu value.

## 11. @JsonMerge với Collection

Với collection, merge thường cập nhật collection hiện có bằng các phần tử nhận được. Với `List`, các phần tử mới thường được thêm vào cuối list hiện tại; không nên giả định Jackson tự tìm phần tử cùng id để cập nhật một item cụ thể.

```java
public class Profile {
    @JsonMerge
    private List<String> tags = new ArrayList<>();

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Ban đầu:

```json
["java", "backend"]
```

Request:

```json
{"tags":["jackson"]}
```

Với merge collection, list có thể trở thành:

```json
["java", "backend", "jackson"]
```

Nếu muốn thay toàn bộ list thành `[“jackson”]`, không dùng merge cho property đó hoặc triển khai semantics thay thế riêng.

Với `Set`, phần tử mới được thêm theo quy tắc `equals()`/`hashCode()` của kiểu phần tử. Với `List`, phần tử trùng vẫn có thể được thêm vì list không tự loại trùng. Merge collection không phải thao tác “upsert phần tử theo id”. Nếu cần cập nhật từng item theo khóa, hãy viết logic domain/custom deserializer rõ ràng.

Array Java có giới hạn thay đổi kích thước và không phải lựa chọn phù hợp cho merge collection theo kiểu append. Với dữ liệu cập nhật, ưu tiên `List`/`Set` hoặc tự xác định hành vi array thay thế.

## 12. Null handling và @JsonMerge là hai quyết định riêng

`@JsonMerge` trả lời câu hỏi: khi property có một object/map/collection, có cập nhật giá trị hiện tại hay thay property bằng giá trị mới?

`@JsonSetter(nulls = ...)` trả lời câu hỏi: nếu property được gửi explicit null, Jackson xử lý null thế nào?

Ví dụ:

```java
@JsonMerge
@JsonSetter(nulls = Nulls.SKIP)
private Address address;
```

Kết quả tổng quát:

| JSON input | Hành vi |
| --- | --- |
| Không có `address` | Không có lần gán; address hiện tại được giữ |
| `"address": null` | Null bị skip; address hiện tại được giữ |
| `"address": {}` | Merge object rỗng; không có field con nào thay đổi |
| `"address": {"city":"Da Nang"}` | Cập nhật city vào address hiện tại; field con khác được giữ |

Nếu thay `Nulls.SKIP` bằng `Nulls.SET`, explicit null có thể đặt toàn bộ `address` thành null dù property có `@JsonMerge`. Nếu dùng `Nulls.FAIL`, explicit null bị từ chối. Không nên giả định `@JsonMerge` tự quyết định ý nghĩa của null.

## 13. Property thiếu khác với object rỗng

Hai request sau không tương đương:

```json
{}
```

và:

```json
{"address":{}}
```

Request đầu không nhắc đến `address`; khi update, Jackson không xử lý property đó.

Request thứ hai có property `address` với một object rỗng. Nếu không có merge, Jackson có thể tạo object `Address` mới rỗng và thay object hiện tại. Nếu có `@JsonMerge`, object rỗng được merge vào object hiện tại và không có field con nào thay đổi.

Sự khác biệt này hữu ích khi API cần phân biệt “không cập nhật địa chỉ” với “gửi một object địa chỉ nhưng không thay đổi field nào”. Nếu muốn object rỗng mang nghĩa xóa địa chỉ, hãy định nghĩa rõ trong hợp đồng và xử lý riêng; đừng dựa vào hành vi ngẫu nhiên của setter.

## 14. Cập nhật object lồng khi giá trị hiện tại là null

`@JsonMerge` chỉ có thể merge vào giá trị hiện tại nếu đã có một instance phù hợp. Nếu property hiện tại là null nhưng JSON gửi một object:

```json
{"address":{"city":"Da Nang"}}
```

Jackson cần tạo một `Address` mới rồi bind nội dung vào đó. Kết quả là property nhận object mới.

Nếu property hiện tại là null và JSON gửi null, hành vi phụ thuộc null policy:

- `SET` hoặc mặc định: property vẫn null.
- `SKIP`: không gán, property giữ null.
- `FAIL`: báo lỗi.
- `AS_EMPTY`: yêu cầu deserializer cung cấp empty value phù hợp.

Merge không thể khôi phục các field cũ nếu không có object cũ. Nếu ứng dụng cần tạo giá trị mặc định khi object lồng thiếu, hãy khởi tạo field hoặc xử lý trong service/domain.

## 15. Cập nhật Map và Collection mà không đánh mất dữ liệu

Khi dùng `@JsonMerge`, cần quyết định semantics cho từng container:

| Kiểu | Hành vi merge thường gặp | Điều cần chú ý |
| --- | --- | --- |
| `Map<K,V>` | Thêm key mới và cập nhật entry có key trùng | Entry không gửi được giữ; null value tuân theo content null policy |
| `List<E>` | Thêm phần tử đầu vào vào collection hiện tại | Không tự upsert theo id; phần tử trùng có thể lặp lại |
| `Set<E>` | Thêm phần tử theo quy tắc Set | Kết quả phụ thuộc `equals()`/`hashCode()` |
| POJO lồng | Bind field input vào instance hiện có | Chỉ property được cấu hình merge mới dùng semantics này |
| Array Java | Không phù hợp với merge thay đổi kích thước | Thường dùng thay thế hoặc logic riêng |

Đối với collection chứa object, đừng giả định Jackson biết item nào trong list cũ tương ứng với item mới. Ví dụ:

```json
{"items":[{"id":"A","name":"New name"}]}
```

Nếu list cũ có item `A` và `B`, merge list có thể thêm một object `A` mới vào cuối thay vì tìm item `A` rồi cập nhật. Muốn upsert theo `id`, hãy viết service logic:

1. Đọc danh sách item cập nhật.
2. Tìm item hiện tại theo khóa.
3. Kiểm tra quyền cập nhật.
4. Cập nhật các field được phép.
5. Thêm item mới hoặc xóa item theo quy tắc API.

Đó là logic nghiệp vụ, không phải semantics mặc định của collection merge.

## 16. updateValue() và readerForUpdating()

`ObjectMapper.updateValue()` là tiện ích để cập nhật object hiện có bằng một object chứa các giá trị override:

```java
Profile updated = mapper.updateValue(profile, overrides);
```

Về bản chất, thao tác này dùng cơ chế reader-for-updating để áp dụng các property của `overrides` lên target. Nó thường được mô tả là shallow merge: các property được cung cấp thay thế giá trị tương ứng; cách xử lý nested object phụ thuộc cấu hình merge như `@JsonMerge`.

So sánh:

| API | Input | Mục đích |
| --- | --- | --- |
| `readerForUpdating(existing).readValue(json)` | JSON string/stream/parser | Đọc JSON trực tiếp vào object hiện có |
| `mapper.updateValue(existing, overrides)` | Một object Java chứa giá trị override | Cập nhật target từ các property của object override |
| `mapper.readValue(json, Type.class)` | JSON | Tạo object mới |

`updateValue()` không phải một triển khai đầy đủ của JSON Merge Patch. Nó không tự định nghĩa semantics HTTP PATCH cho missing/null/array. Nếu cần điều khiển chính xác, đặc biệt với object lồng, hãy cấu hình `@JsonMerge` và null handling hoặc dùng một patch model riêng.

## 17. Phân biệt @JsonMerge với JSON Merge Patch (RFC 7396)

Tên gọi dễ gây nhầm lẫn, nhưng `@JsonMerge` là annotation của Jackson Databind để điều khiển cập nhật property khi deserialize vào object hiện có. JSON Merge Patch là một chuẩn định dạng patch ở tầng giao thức, được định nghĩa trong RFC 7396.

Các semantics quan trọng của JSON Merge Patch:

- Property không có trong patch: giữ nguyên target.
- Property có giá trị null: xóa member tương ứng khỏi target JSON object.
- Property có object: merge đệ quy vào object target.
- Property có array: thay thế toàn bộ array target bằng array mới.

Trong khi đó, `@JsonMerge` trên `List` có thể thêm phần tử mới vào collection hiện tại. Vì vậy, không thể dùng `@JsonMerge` rồi mặc định tuyên bố API đã tuân theo RFC 7396.

Ví dụ RFC 7396:

Target:

```json
{
  "name": "An",
  "phone": "0900000000",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Nguyen Hue"
  },
  "tags": ["java", "backend"]
}
```

Patch:

```json
{
  "phone": null,
  "address": {
    "city": "Da Nang"
  },
  "tags": ["jackson"]
}
```

Kết quả theo JSON Merge Patch:

```json
{
  "name": "An",
  "address": {
    "city": "Da Nang",
    "street": "Nguyen Hue"
  },
  "tags": ["jackson"]
}
```

`phone` bị xóa; `address.city` thay đổi nhưng `address.street` giữ nguyên; array `tags` được thay toàn bộ. Đây là semantics khác với null skip và list append thường gặp khi dùng `@JsonSetter`/`@JsonMerge`.

Nếu API công bố `application/merge-patch+json`, hãy triển khai đúng RFC 7396 hoặc dùng thư viện chuyên biệt. Nếu chỉ dùng Jackson update để cập nhật DTO, hãy mô tả semantics riêng trong API contract.

## 18. Phân biệt với JSON Patch (RFC 6902)

JSON Patch dùng một danh sách thao tác tường minh, ví dụ:

```json
[
  {"op":"replace","path":"/address/city","value":"Da Nang"},
  {"op":"remove","path":"/phone"},
  {"op":"add","path":"/tags/-","value":"jackson"}
]
```

Các operation có thể gồm `add`, `remove`, `replace`, `move`, `copy` và `test`. Cách này cho phép client chỉ rõ thao tác trên path cụ thể. Jackson `readerForUpdating()` không tự hiểu array operation hoặc path syntax của JSON Patch.

Chọn định dạng patch theo nhu cầu:

- JSON Merge Patch phù hợp với patch dạng object đơn giản, trong đó null có nghĩa xóa và array được thay toàn bộ.
- JSON Patch phù hợp khi cần thao tác tường minh trên path, đặc biệt với array.
- Jackson update/`@JsonMerge` phù hợp khi ứng dụng muốn điều khiển merge trực tiếp vào object Java theo quy tắc riêng.

## 19. Immutable object và constructor-based DTO

`readerForUpdating()` phù hợp nhất với object có thể thay đổi qua setter, field hoặc cơ chế update mà Jackson hỗ trợ. Với immutable object, record hoặc class chỉ có final field, không thể giả định Jackson sẽ cập nhật instance hiện có theo cách tương tự bean mutable.

Ví dụ record:

```java
public record Profile(String name, String phone, Address address) {
}
```

Một record không có setter và các component là bất biến. Đối với partial update, cách rõ ràng hơn thường là:

1. Deserialize patch thành DTO riêng có các field nullable/optional.
2. Lấy object hiện tại.
3. Áp dụng quy tắc missing/null/value trong service.
4. Tạo record mới với các giá trị sau cập nhật.

Ví dụ:

```java
Profile updated = new Profile(
        patch.name() != null ? patch.name() : current.name(),
        patch.phone() != null ? patch.phone() : current.phone(),
        mergeAddress(current.address(), patch.address())
);
```

Đoạn ví dụ cần thêm trạng thái presence nếu muốn phân biệt “field thiếu” với “field explicit null”; chỉ dùng nullable component không đủ biểu diễn cả hai trạng thái. Có thể dùng wrapper `Optional` theo thiết kế riêng, kiểu `FieldUpdate<T>` gồm `present` và `value`, hoặc đọc patch thành `JsonNode` để kiểm tra `has()` và `isNull()`.

## 20. Dùng JsonNode khi cần phân biệt presence chính xác

Nếu API cần phân biệt ba trạng thái cho nhiều property — missing, null và value — một patch DTO với field nullable có thể không đủ. Tree Model cho phép kiểm tra sự hiện diện của field:

```java
JsonNode patch = mapper.readTree(json);

if (!patch.has("phone")) {
    // Không có chỉ dẫn cập nhật phone.
} else if (patch.get("phone").isNull()) {
    // Client gửi explicit null: áp dụng chính sách xóa hoặc từ chối.
} else {
    String phone = patch.get("phone").asText();
    // Cập nhật bằng giá trị mới.
}
```

Lưu ý:

- `has("phone")` trả true nếu property có mặt, kể cả giá trị là JSON null.
- `hasNonNull("phone")` trả false nếu thiếu hoặc null; không dùng nó nếu cần phân biệt hai trạng thái.
- `get("phone")` trả Java null nếu property không tồn tại; trả `NullNode` nếu property có JSON null.
- `path("phone")` trả `MissingNode` nếu property không tồn tại.

Tree Model giúp xử lý presence rõ ràng nhưng tạo cây trong bộ nhớ. Với patch nhỏ, điều này thường dễ quản lý; với payload lớn, cân nhắc streaming hoặc patch representation chuyên biệt.

## 21. Cập nhật có chọn lọc và bảo vệ field nhạy cảm

Không nên deserialize trực tiếp một request cập nhật vào entity/database object có nhiều field nhạy cảm. Nếu client có thể gửi `role`, `ownerId`, `balance`, `status` hoặc cờ nội bộ, `readerForUpdating()` có thể cập nhật những property được Jackson cho phép ánh xạ.

Nên dùng DTO patch chỉ chứa các field client được phép thay đổi:

```java
public class UpdateProfileRequest {
    private String displayName;
    private String phone;
    private AddressPatch address;
}
```

Sau đó service áp dụng từng field theo allowlist và kiểm tra quyền:

```java
if (patch.hasDisplayName()) {
    profile.setDisplayName(patch.displayName());
}

if (patch.hasPhone()) {
    profile.setPhone(patch.phone()); // Có thể null nếu API định nghĩa null là xóa.
}
```

Trong ví dụ, `hasDisplayName()`/`hasPhone()` là presence flag do patch model cung cấp. Đây là cách biểu diễn tốt khi cần phân biệt missing và explicit null trong Java.

`@JsonIgnore` hoặc `@JsonProperty(access = READ_ONLY)` có thể hỗ trợ bảo vệ mapping, nhưng authorization và allowlist ở service vẫn cần thiết. Annotation không thay thế kiểm tra quyền của người dùng hiện tại.

## 22. Validation khi cập nhật một phần

DTO tạo mới và DTO cập nhật thường có yêu cầu khác nhau. Ví dụ, khi tạo profile, `name` có thể bắt buộc; khi cập nhật phone, request không cần gửi name.

Nếu dùng cùng DTO có `@NotBlank` cho mọi field, validation có thể từ chối patch chỉ vì các field không được gửi. Một số hướng xử lý:

- Dùng DTO riêng cho create và update.
- Dùng validation groups nếu quy tắc khác nhau nhưng cấu trúc DTO vẫn phù hợp.
- Dùng patch model có presence flag và validation theo field được gửi.
- Validate object sau khi merge nếu cần bảo đảm trạng thái cuối cùng vẫn hợp lệ.

Đặc biệt, validation sau merge kiểm tra trạng thái object cuối cùng; validation patch kiểm tra các giá trị mà client gửi. Hai loại kiểm tra có thể cần cùng tồn tại.

Ví dụ: `address.city` bị bỏ qua trong patch nhưng object hiện tại có city không hợp lệ do dữ liệu cũ. Nếu chỉ validate patch, lỗi có thể không được phát hiện; nếu chỉ validate object cuối, có thể phát hiện trạng thái cuối cùng nhưng không xác định được field nào của request gây ra lỗi. Hãy chọn validation boundary phù hợp.

## 23. Xử lý lỗi khi update

Khi dùng `readerForUpdating()`, các lỗi thường gặp gồm:

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Field cũ bị mất dù không gửi | Property lồng được thay bằng object mới, không có `@JsonMerge` | Đánh dấu property cần merge hoặc merge trong service |
| Explicit null xóa dữ liệu ngoài ý muốn | Null handling mặc định gán null | Dùng `Nulls.SKIP`, `FAIL` hoặc semantics patch rõ ràng |
| Null không xóa được giá trị | Property dùng `Nulls.SKIP` | Xem lại hợp đồng; cho phép `SET` hoặc xử lý lệnh xóa riêng |
| Null trong list/map bị giữ | Chưa cấu hình `contentNulls` | Cấu hình content null policy |
| List có phần tử trùng sau update | Merge collection thêm phần tử, không upsert theo id | Viết logic cập nhật theo khóa |
| Object con không được merge | Thiếu `@JsonMerge` hoặc property hiện tại null | Kiểm tra annotation và instance hiện có |
| Record/immutable object không update như mong muốn | Không có mutable property để ghi | Dùng patch DTO rồi tạo instance mới |
| Field nhạy cảm bị cập nhật | DTO/entity cho phép bind property đó | Dùng allowlist DTO và kiểm tra authorization |

Khi debug, hãy ghi lại JSON patch, trạng thái object trước update, annotation trên property và trạng thái sau update. Test chỉ kiểm tra object mới được deserialize không đủ để xác nhận update semantics.

## 24. Kiểm thử missing, null và merge

Nên kiểm thử riêng từng trạng thái:

| Trường hợp | Input | Kết quả cần xác nhận |
| --- | --- | --- |
| Property thiếu | `{}` | Giá trị hiện tại được giữ |
| Explicit null mặc định | `{"phone":null}` | Reference property được đặt null nếu không có null override |
| Explicit null với SKIP | `{"phone":null}` | Giá trị hiện tại được giữ |
| Explicit null với FAIL | `{"phone":null}` | Deserialize báo lỗi |
| Nested object không merge | `{"address":{"city":"Da Nang"}}` | Object con có thể bị thay thế; field không gửi mất giá trị cũ |
| Nested object có merge | `{"address":{"city":"Da Nang"}}` | Field city đổi; field street giữ nguyên |
| Nested object rỗng có merge | `{"address":{}}` | Object hiện tại không đổi field con |
| Map có merge | `{"preferences":{"theme":"light"}}` | Key khác được giữ; theme được cập nhật |
| List có merge | `{"tags":["jackson"]}` | Phần tử được thêm theo semantics collection |
| Null item trong list | `{"tags":[null]}` | Kết quả theo `contentNulls` |

Ví dụ test update:

```java
@Test
void keepsMissingAndSkippedNullButMergesNestedAddress() throws Exception {
    Profile profile = existingProfile();

    String patch = """
            {
              "address": {"city": "Da Nang"},
              "phone": null
            }
            """;

    mapper.readerForUpdating(profile).readValue(patch);

    assertEquals("An", profile.getName());
    assertEquals("0900000000", profile.getPhone());
    assertEquals("Da Nang", profile.getAddress().getCity());
    assertEquals("Nguyen Hue", profile.getAddress().getStreet());
}
```

Test cần dùng mapper đã cấu hình annotation và module giống ứng dụng thực tế. Nếu dùng custom `ObjectMapper` trong test, hãy bảo đảm `@JsonMerge` và null handling được đọc thông qua annotation introspector mặc định.

## 25. Quy trình thiết kế semantics cập nhật

Trước khi triển khai endpoint update, hãy trả lời rõ các câu hỏi:

1. **Property thiếu có nghĩa gì?** Thường là giữ nguyên.
2. **Explicit null có nghĩa gì?** Xóa giá trị, bỏ qua hay từ chối?
3. **Object lồng một phần có nghĩa gì?** Thay toàn bộ hay merge field con?
4. **Map có merge theo key không?** Entry không gửi có được giữ không?
5. **List có append hay replace?** Có cần upsert theo id không?
6. **Null bên trong container có ý nghĩa gì?** Giữ null, bỏ phần tử hay báo lỗi?
7. **Field nào client được phép cập nhật?** Có field nội bộ hoặc nhạy cảm không?
8. **Object là mutable hay immutable?** Có thể cập nhật tại chỗ hay phải tạo instance mới?
9. **Định dạng patch có phải RFC 7396/6902 không?** Nếu có, cần triển khai đúng chuẩn thay vì tự suy diễn từ Jackson update.
10. **Validation chạy khi nào?** Kiểm tra patch, trạng thái sau merge hay cả hai?

Sau khi thống nhất hợp đồng, chọn cơ chế tương ứng:

- `readerForUpdating()` cho việc bind JSON vào object mutable hiện có.
- `@JsonMerge` cho property POJO/map/collection cần merge vào giá trị hiện tại.
- `@JsonSetter(nulls = ...)` cho explicit null ở property.
- `contentNulls` cho null bên trong container.
- `JsonNode` hoặc patch DTO có presence flag khi cần phân biệt missing/null/value rõ ràng.
- Service/domain logic cho upsert collection theo id, xóa quan hệ hoặc quy tắc nghiệp vụ.
- Thư viện/implementation chuẩn cho JSON Merge Patch hoặc JSON Patch nếu API cam kết theo RFC.

## 26. Ghi nhớ

- Property không xuất hiện trong JSON update thường không được gán lại, nên giá trị hiện tại được giữ.
- Explicit JSON null khác với property thiếu; với reference type, mặc định null có thể thay giá trị hiện tại.
- `readerForUpdating(existing)` cập nhật object đã tồn tại và làm thay đổi instance đó.
- `@JsonSetter(nulls = Nulls.SKIP)` bỏ qua explicit null; `FAIL` từ chối; `SET` gán null; `AS_EMPTY` dùng empty value.
- `contentNulls` áp dụng cho phần tử/value bên trong collection hoặc map, còn `nulls` áp dụng cho toàn bộ property.
- Object lồng mặc định có thể bị thay thế bằng instance mới; `@JsonMerge` yêu cầu Jackson merge vào giá trị hiện có.
- `@JsonMerge` có thể dùng với POJO, Map và Collection; Map thường cập nhật entry theo key, List thường thêm phần tử, không tự upsert theo id.
- `@JsonMerge` và null handling là hai quyết định riêng; explicit null vẫn tuân theo null policy.
- `@JsonMerge` không phải JSON Merge Patch RFC 7396; đặc biệt null và array có semantics khác nhau.
- `readerForUpdating()` phù hợp với object mutable; immutable/record thường nên dùng patch DTO rồi tạo instance mới.
- Dùng `JsonNode.has()` và `get()` khi cần phân biệt field thiếu với explicit null.
- Chỉ cho phép cập nhật field theo allowlist; không deserialize request trực tiếp vào entity nhạy cảm mà bỏ qua authorization.
- Kiểm thử riêng missing, null, object rỗng, nested partial object, map/list merge và content nulls.

Khi xử lý cập nhật một phần, hãy định nghĩa ý nghĩa của missing, null và object lồng trước khi chọn annotation. Jackson cung cấp các cơ chế để thực hiện nhiều chính sách khác nhau, nhưng hợp đồng API và logic domain phải quyết định khi nào giữ, xóa, thay thế hoặc merge dữ liệu hiện có.
