# Phân biệt bỏ qua null và ghi đè giá trị hiện có bằng null

Khi cập nhật một object Java từ JSON, cần phân biệt hai trường hợp: property không xuất hiện trong JSON và property xuất hiện với giá trị null. Hai trường hợp này không đồng nghĩa.

- **Missing property**: client không gửi khóa đó. Khi cập nhật object hiện có, property thường không bị thay đổi.
- **Explicit null**: client gửi khóa và giá trị null. Theo chính sách mặc định thông thường của Jackson đối với property reference, giá trị cũ có thể bị ghi đè thành null.
- **Giá trị thực**: client gửi string, number, boolean, array hoặc object. Giá trị này được ánh xạ theo kiểu Java đích.

Jackson cung cấp cơ chế điều khiển null như @JsonSetter với Nulls.SET, Nulls.SKIP, Nulls.FAIL và Nulls.AS_EMPTY. Bài học này tập trung vào cách các lựa chọn đó ảnh hưởng đến việc cập nhật dữ liệu.

## 1. Ba trạng thái JSON khác nhau

Giả sử ứng dụng quản lý hồ sơ với property nickname.

**Không có property:**

~~~json
{
  "displayName": "An"
}
~~~

**Property có giá trị null:**

~~~json
{
  "displayName": "An",
  "nickname": null
}
~~~

**Property có string rỗng:**

~~~json
{
  "displayName": "An",
  "nickname": ""
}
~~~

Ba trạng thái có ý nghĩa khác nhau:

| JSON | Ý nghĩa |
|---|---|
| Không có khóa | Không gửi property |
| nickname là null | Gửi null tường minh |
| nickname là chuỗi rỗng | Gửi một string có độ dài bằng 0 |
| tags là [] | Gửi collection rỗng |
| tags là null | Gửi null cho cả collection |
| tags là ["java"] | Gửi collection có phần tử |

Ứng dụng cần định nghĩa ý nghĩa cập nhật của từng trạng thái trong hợp đồng API.

## 2. Khác biệt khi tạo object mới và cập nhật object hiện có

### 2.1. Tạo object mới

~~~java
public class Profile {
    private String displayName = "Guest";
    private String nickname = "New user";

    public Profile() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Nếu JSON không có nickname:

~~~java
Profile profile = mapper.readValue(
        """
        {"displayName":"An"}
        """,
        Profile.class
);
~~~

Jackson tạo object mới. Vì JSON không có nickname nên property không nhận giá trị từ JSON; giá trị khởi tạo trong class có thể vẫn là "New user".

Nếu JSON gửi nickname null:

~~~java
Profile profile = mapper.readValue(
        """
        {"displayName":"An","nickname":null}
        """,
        Profile.class
);
~~~

Với cách xử lý null mặc định thông thường đối với property reference, Jackson gán null cho nickname. Giá trị khởi tạo "New user" bị thay thế.

### 2.2. Cập nhật object hiện có bằng readerForUpdating

Jackson cung cấp readerForUpdating để đọc JSON và áp dụng dữ liệu lên một instance đã tồn tại:

~~~java
Profile profile = new Profile();
profile.setDisplayName("Old name");
profile.setNickname("Old nickname");

String json = """
        {
          "displayName": "New name"
        }
        """;

mapper.readerForUpdating(profile).readValue(json);
~~~

Sau thao tác này, displayName thành "New name", còn nickname vẫn là "Old nickname" vì property không xuất hiện trong JSON.

Nếu JSON gửi null:

~~~java
String json = """
        {
          "displayName": "New name",
          "nickname": null
        }
        """;

mapper.readerForUpdating(profile).readValue(json);
~~~

Theo null policy mặc định thông thường, nickname cũ bị ghi đè thành null.

| Giá trị ban đầu | JSON đầu vào | Kết quả thông thường |
|---|---|---|
| "Old" | Property không xuất hiện | Giữ "Old" |
| "Old" | Property là null | Thành null |
| "Old" | Property là "New" | Thành "New" |
| "Old" | Property là chuỗi rỗng | Thành chuỗi rỗng |

Đây là khác biệt cốt lõi: missing thường có nghĩa không cập nhật property; explicit null là một giá trị đầu vào và có thể có nghĩa xóa giá trị hiện có.

### 2.3. updateValue

ObjectMapper còn có updateValue cho trường hợp áp dụng dữ liệu từ một object Java khác, chẳng hạn Map, lên target:

~~~java
Profile existing = new Profile();

Map<String, Object> updates = new HashMap<>();
updates.put("displayName", "Updated");

mapper.updateValue(existing, updates);
~~~

Khi cần thể hiện rõ việc đọc một JSON document lên instance hiện có, readerForUpdating thường làm ý định dễ nhận biết hơn. Hành vi chi tiết của updateValue phụ thuộc kiểu nguồn, kiểu đích và phiên bản Jackson; hãy kiểm tra tài liệu API khi dùng cho hợp đồng cập nhật quan trọng.

## 3. Điều khiển null bằng @JsonSetter

Jackson 2.x cung cấp annotation JsonSetter với thuộc tính nulls để chỉ định hành vi khi property nhận JSON null.

| Chính sách | Ý nghĩa |
|---|---|
| Nulls.SET | Gán null theo cơ chế setter/property |
| Nulls.SKIP | Bỏ qua việc gán; giữ giá trị hiện có |
| Nulls.FAIL | Từ chối null bằng exception |
| Nulls.AS_EMPTY | Dùng empty value do deserializer của kiểu đích cung cấp |
| Nulls.DEFAULT | Dùng chính sách mặc định của mapper/property |

### 3.1. Nulls.SET: ghi đè bằng null

SET là cách xử lý thông thường đối với property reference khi nhận null. Có thể khai báo tường minh:

~~~java
public class Profile {
    private String nickname = "Old nickname";

    @JsonSetter(nulls = Nulls.SET)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }
}
~~~

Khi JSON có:

~~~json
{
  "nickname": null
}
~~~

setter nhận null và giá trị cũ được thay bằng null. SET phù hợp khi hợp đồng API quy định null có nghĩa là xóa giá trị.

Với primitive như int, Java không thể lưu null. Hành vi cụ thể phụ thuộc null-handling và feature của Jackson; có thể dùng FAIL_ON_NULL_FOR_PRIMITIVES để từ chối null thay vì nhận giá trị mặc định.

### 3.2. Nulls.SKIP: bỏ qua việc gán null

Nếu muốn giữ giá trị cũ khi JSON gửi null, dùng SKIP:

~~~java
public class Profile {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Giả sử object đã có nickname:

~~~java
Profile profile = new Profile();
profile.setNickname("Old nickname");

String json = """
        {"nickname":null}
        """;

mapper.readerForUpdating(profile).readValue(json);
~~~

Với SKIP, thao tác gán null bị bỏ qua. nickname vẫn là "Old nickname".

SKIP chỉ bỏ qua việc gán property khi nhận null. Nó không bỏ qua string rỗng, số 0, false hoặc collection rỗng vì những giá trị đó không phải JSON null.

### 3.3. Nulls.FAIL: từ chối null

Nếu property không được nhận null ngay trong quá trình ánh xạ:

~~~java
public class Profile {
    private String nickname;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }
}
~~~

Với JSON:

~~~json
{"nickname":null}
~~~

Jackson từ chối null và ném exception trong quá trình deserialization.

FAIL phù hợp khi null không được chấp nhận ngay tại ranh giới ánh xạ. Nếu muốn thu thập nhiều lỗi dữ liệu và trả về danh sách validation violations, Jakarta Bean Validation thường phù hợp hơn. Lựa chọn phụ thuộc việc ứng dụng muốn từ chối ngay lúc mapping hay tạo object rồi kiểm tra constraint.

### 3.4. Nulls.AS_EMPTY: thay null bằng giá trị rỗng

AS_EMPTY yêu cầu deserializer tạo empty value phù hợp với kiểu đích thay vì gán null.

~~~java
public class Profile {
    private List<String> tags;

    @JsonSetter(nulls = Nulls.AS_EMPTY)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
~~~

JSON:

~~~json
{
  "tags": null
}
~~~

Có thể được ánh xạ thành collection rỗng theo empty value mà deserializer của kiểu đó cung cấp. Với String, empty value thường là chuỗi rỗng; với collection, thường là collection rỗng. Với kiểu tùy chỉnh, kết quả phụ thuộc deserializer.

AS_EMPTY không có nghĩa mọi kiểu đều nhận cùng một giá trị mặc định. Hãy kiểm tra empty value của kiểu đích nếu quy tắc này quan trọng.

### 3.5. Nulls.DEFAULT: dùng chính sách mặc định

DEFAULT yêu cầu Jackson dùng null policy mặc định đang áp dụng cho property hoặc mapper. Nếu ứng dụng đặt default setter info ở cấp mapper, hành vi DEFAULT có thể chịu ảnh hưởng từ cấu hình đó.

Với property quan trọng của hợp đồng API, khai báo lựa chọn cụ thể giúp ý định dễ đọc và ít phụ thuộc vào thay đổi cấu hình toàn cục.

## 4. Đặt @JsonSetter trên property

Có thể đặt annotation trên setter:

~~~java
@JsonSetter(nulls = Nulls.SKIP)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
~~~

Hoặc trên field mà Jackson nhận diện:

~~~java
public class Profile {

    @JsonSetter(nulls = Nulls.SKIP)
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Đặt annotation gần property giúp người đọc thấy chính sách null ngay tại nơi khai báo dữ liệu. Nếu annotation xuất hiện trên nhiều accessor của cùng logical property, cần tránh metadata mâu thuẫn và kiểm tra cách Jackson hợp nhất property.

Đối với immutable object hoặc creator property, quy trình khác JavaBean setter thông thường. Hãy xác nhận annotation và null handling được hỗ trợ đúng vị trí trong phiên bản Jackson đang dùng.

## 5. Phân biệt null của collection và null của phần tử

Một property có thể là collection hoặc map. Khi đó có hai lớp null:

1. Bản thân collection là null.
2. Một phần tử bên trong collection là null.

Property null:

~~~json
{
  "tags": null
}
~~~

Collection có phần tử null:

~~~json
{
  "tags": ["java", null, "jackson"]
}
~~~

Jackson cho phép cấu hình riêng bằng nulls và contentNulls.

### 5.1. Null của cả property

~~~java
public class Profile {
    private List<String> tags;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
~~~

Nếu JSON có tags null, Jackson bỏ qua việc gán property. Khi update instance hiện có, collection cũ được giữ lại.

### 5.2. Null của phần tử

~~~java
public class Profile {
    private List<String> tags;

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
~~~

Nếu JSON có array chứa phần tử null, null element có thể bị bỏ qua trong quá trình tạo collection, trong khi property tags vẫn được xử lý như một collection bình thường.

Có thể kết hợp:

~~~java
@JsonSetter(
        nulls = Nulls.SKIP,
        contentNulls = Nulls.SKIP
)
public void setTags(List<String> tags) {
    this.tags = tags;
}
~~~

Khi đó:
- tags là null: bỏ qua việc gán cả property.
- tags là array có phần tử null: bỏ qua các phần tử null.
- tags là array rỗng: gán collection rỗng vì [] là một giá trị thực.

Quy tắc tương tự áp dụng cho Map: null của toàn bộ map khác null của từng value.

## 6. @JsonMerge và cập nhật object lồng nhau

Một trường hợp khác là cập nhật property object lồng nhau.

~~~java
public class UserSettings {
    private String theme;
    private NotificationSettings notifications;

    // Getter, setter và constructor.
}

public class NotificationSettings {
    private boolean emailEnabled;
    private boolean smsEnabled;

    // Getter, setter và constructor.
}
~~~

Khi cập nhật object đã có bằng JSON:

~~~json
{
  "notifications": {
    "emailEnabled": false
  }
}
~~~

Nếu không cấu hình merge, property notifications có thể được thay bằng object mới tạo từ phần JSON gửi lên. Giá trị smsEnabled cũ có thể không được giữ như mong đợi.

Jackson cung cấp @JsonMerge để yêu cầu merge nội dung vào giá trị hiện có đối với những kiểu được hỗ trợ:

~~~java
public class UserSettings {
    private String theme;

    @JsonMerge
    private NotificationSettings notifications;

    // Getter và setter.
}
~~~

Khi dùng update reader, @JsonMerge cho phép Jackson cập nhật object lồng nhau theo ngữ nghĩa merge của kiểu đó thay vì thay toàn bộ property bằng giá trị mới.

Cần phân biệt ba cơ chế:
- @JsonMerge điều khiển cách cập nhật nội dung của property có cấu trúc.
- @JsonSetter(nulls = ...) điều khiển null của property.
- contentNulls điều khiển null trong phần tử collection hoặc value của map.

@JsonMerge không tự động có nghĩa null luôn bị bỏ qua. Nếu JSON gửi notifications null, hãy xác định null policy của property và kiểm thử hành vi cụ thể.

## 7. Phân biệt missing và explicit null bằng JsonNode

Nếu ứng dụng cần tự quyết định property có được gửi hay không, tree model giúp phân biệt hai trạng thái trước khi cập nhật DTO hoặc domain object.

~~~java
JsonNode root = mapper.readTree(json);

if (!root.has("nickname")) {
    System.out.println("Property is missing");
} else if (root.get("nickname").isNull()) {
    System.out.println("Property is explicitly null");
} else {
    System.out.println("Property has a value");
}
~~~

Các method cần nhớ:

| Method | Property thiếu | Property có null | Có giá trị khác null |
|---|---|---|---|
| has(name) | false | true | true |
| hasNonNull(name) | false | false | true |
| get(name) | Java null | NullNode | Node tương ứng |
| path(name) | MissingNode | NullNode | Node tương ứng |

Ví dụ:

~~~java
JsonNode nicknameNode = root.get("nickname");

if (nicknameNode == null) {
    // Không có khóa nickname.
} else if (nicknameNode.isNull()) {
    // Có khóa nickname với JSON null.
} else {
    String nickname = nicknameNode.asText();
    // Có giá trị thực.
}
~~~

Không nên chỉ dùng asText() hoặc asInt() rồi kết luận property có được gửi hay không, vì các method chuyển đổi tiện ích có thể trả về giá trị mặc định khi node thiếu hoặc không phù hợp.

## 8. Áp dụng cho API cập nhật từng phần

### 8.1. Ý nghĩa của missing và null trong PATCH

Một hợp đồng PATCH thường cần phân biệt:

- Missing: giữ nguyên giá trị hiện tại.
- Null: xóa giá trị hiện tại nếu property cho phép xóa.
- Value: thay bằng giá trị mới.

Giả sử hồ sơ hiện tại:

~~~json
{
  "displayName": "An",
  "nickname": "An Nguyen",
  "bio": "Java developer"
}
~~~

Request chỉ đổi displayName:

~~~json
{
  "displayName": "Binh"
}
~~~

Kết quả mong muốn:

~~~json
{
  "displayName": "Binh",
  "nickname": "An Nguyen",
  "bio": "Java developer"
}
~~~

Request khác gửi null để xóa bio:

~~~json
{
  "bio": null
}
~~~

Kết quả mong muốn theo hợp đồng này:

~~~json
{
  "displayName": "Binh",
  "nickname": "An Nguyen",
  "bio": null
}
~~~

Không thể dùng một chính sách SKIP toàn cục cho mọi property nếu một số property cần cho phép null để xóa. Cần xác định chính sách riêng theo property hoặc xử lý patch document bằng logic tường minh.

### 8.2. @JsonSetter(nulls = Nulls.SKIP) không tự giữ giá trị database

Nếu DTO update là object mới, việc Jackson bỏ qua null chỉ có nghĩa setter không được gọi. Property trên DTO mới vẫn có thể là null nếu không có giá trị khởi tạo.

Ví dụ:

~~~java
public class ProfileUpdateRequest {
    @JsonSetter(nulls = Nulls.SKIP)
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Đoạn khai báo này không tự tìm profile hiện có trong database để giữ nickname cũ. Muốn giữ dữ liệu, ứng dụng phải:
- Cập nhật trực tiếp instance hiện có bằng readerForUpdating với null policy phù hợp; hoặc
- Giữ trạng thái presence trong patch model rồi để application service quyết định giữ, xóa hay thay thế property.

Đây là khác biệt quan trọng giữa xử lý null khi mapping và logic cập nhật dữ liệu đang lưu.

### 8.3. Dùng readerForUpdating với null policy

~~~java
public class Profile {
    private String displayName;
    private String nickname;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getNickname() {
        return nickname;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

~~~java
Profile profile = new Profile();
profile.setDisplayName("An");
profile.setNickname("An Nguyen");

String patchJson = """
        {
          "displayName": "Binh",
          "nickname": null
        }
        """;

mapper.readerForUpdating(profile).readValue(patchJson);
~~~

Sau khi đọc:
- displayName thành "Binh".
- nickname vẫn là "An Nguyen" vì việc gán null bị bỏ qua.

Nếu nickname cần được xóa khi nhận null, hãy dùng SET hoặc chính sách mặc định tương ứng. Quy tắc phải xuất phát từ hợp đồng API.

## 9. Jackson update không tự động triển khai JSON Merge Patch

JSON Merge Patch được mô tả trong RFC 7396. Trong định dạng này, null trong object patch có ý nghĩa loại bỏ member tương ứng khỏi target document; object con có thể được merge đệ quy, còn array thường được thay thế như một giá trị.

Jackson có API update object và annotation @JsonMerge, nhưng chỉ dùng readerForUpdating hoặc @JsonMerge không có nghĩa ứng dụng đã triển khai đầy đủ giao thức JSON Merge Patch.

Nếu endpoint nhận media type application/merge-patch+json, ứng dụng cần xử lý đúng semantics của RFC 7396 hoặc dùng thư viện hỗ trợ. JSON Patch theo RFC 6902 lại dùng danh sách operation như add, remove, replace và test; nó có semantics khác với Merge Patch.

## 10. Kiểm thử hành vi null khi cập nhật

Null handling nên được kiểm thử trên object đã có giá trị. Test chỉ deserialize object mới có thể không phát hiện việc ghi đè dữ liệu cũ.

Missing property giữ giá trị:

~~~java
@Test
void missingPropertyKeepsExistingValue() throws Exception {
    Profile profile = new Profile();
    profile.setNickname("Old nickname");

    mapper.readerForUpdating(profile)
            .readValue("{\"displayName\":\"New name\"}");

    assertEquals("Old nickname", profile.getNickname());
}
~~~

Explicit null xóa giá trị với chính sách mặc định SET:

~~~java
@Test
void explicitNullClearsExistingValue() throws Exception {
    Profile profile = new Profile();
    profile.setNickname("Old nickname");

    mapper.readerForUpdating(profile)
            .readValue("{\"nickname\":null}");

    assertNull(profile.getNickname());
}
~~~

Explicit null được bỏ qua với SKIP:

~~~java
@Test
void explicitNullCanBeSkippedForSelectedProperty() throws Exception {
    Profile profile = new Profile();
    profile.setNickname("Old nickname");

    mapper.readerForUpdating(profile)
            .readValue("{\"nickname\":null}");

    assertEquals("Old nickname", profile.getNickname());
}
~~~

Test thứ ba phải dùng class có setter hoặc property đã khai báo @JsonSetter(nulls = Nulls.SKIP). Nếu dùng class mặc định SET, kết quả mong đợi sẽ khác.

Một bộ test nên bao gồm:
- Property bị thiếu.
- Property null tường minh.
- Property có string rỗng.
- Property có giá trị bình thường.
- Collection bị null.
- Collection rỗng.
- Phần tử collection null nếu hợp đồng cho phép hoặc từ chối trường hợp đó.

## 11. Validation sau khi cập nhật

Với cập nhật từng phần, validation trên từng field riêng lẻ chưa chắc đủ. Một patch có thể hợp lệ ở cấp property nhưng khiến object cuối cùng vi phạm invariant khi kết hợp với dữ liệu cũ.

Ví dụ object có startDate và endDate:
- Request chỉ đổi startDate.
- endDate được giữ từ dữ liệu cũ.
- Sau khi merge, startDate có thể lớn hơn endDate.

Vì vậy, quy trình phù hợp thường là:

1. Đọc patch và xác định property được gửi.
2. Áp dụng thay đổi vào trạng thái hiện tại theo null policy.
3. Kiểm tra constraint và invariant trên object sau khi merge.
4. Lưu thay đổi trong transaction nếu cần.

Validation trên DTO patch mới không thể thay thế kiểm tra trạng thái cuối cùng nếu quy tắc phụ thuộc dữ liệu đang lưu.

## 12. Cách chọn chính sách cho từng trường hợp

| Yêu cầu cập nhật | Chính sách phù hợp |
|---|---|
| Missing giữ giá trị cũ | Không có property trong JSON; update reader không gán property đó |
| Null xóa giá trị cũ | Nulls.SET hoặc chính sách mặc định phù hợp cho reference |
| Null không được phép | Nulls.FAIL hoặc Bean Validation tùy thời điểm cần từ chối |
| Null chuyển thành giá trị rỗng | Nulls.AS_EMPTY |
| Null giữ nguyên giá trị cũ | Nulls.SKIP khi cập nhật instance hiện có |
| Bỏ qua null trong phần tử collection | contentNulls = Nulls.SKIP |
| Merge object lồng nhau | @JsonMerge kết hợp update API phù hợp |
| Cần phân biệt missing/null trong logic phức tạp | JsonNode hoặc patch model có trạng thái presence |

Không có một chính sách duy nhất phù hợp cho mọi property. Nickname có thể cho phép null để xóa; danh sách roles có thể yêu cầu không bao giờ nhận null; một field ghi chú có thể chuyển null thành chuỗi rỗng. Hợp đồng API cần mô tả rõ từng trường.

## 13. Trình tự xử lý khi cập nhật một object

Khi nhận JSON dùng để cập nhật object hiện có, hãy xác định:

1. JSON có cú pháp hợp lệ không?
2. Property nào thực sự xuất hiện?
3. Property xuất hiện có giá trị null, rỗng hay một giá trị cụ thể?
4. Jackson sẽ cập nhật object hiện tại hay tạo object mới?
5. Null policy của từng property là SET, SKIP, FAIL, AS_EMPTY hay DEFAULT?
6. Nếu property là collection/map, null policy của container và content có khác nhau không?
7. Object lồng nhau có cần merge bằng @JsonMerge không?
8. Sau khi cập nhật, object có còn thỏa validation và domain invariant không?
9. API có đang triển khai PUT, PATCH, JSON Merge Patch hay JSON Patch đúng semantics đã công bố không?

Phân biệt bỏ qua null và ghi đè giá trị hiện có bằng null giúp tránh vô tình xóa dữ liệu khi cập nhật. Missing property thường biểu thị không có thay đổi cho property đó; explicit null là một đầu vào có ý nghĩa riêng. Jackson cung cấp các công cụ để điều khiển việc gán, còn ứng dụng phải quyết định semantics cập nhật và xác nhận trạng thái cuối cùng có hợp lệ hay không.
