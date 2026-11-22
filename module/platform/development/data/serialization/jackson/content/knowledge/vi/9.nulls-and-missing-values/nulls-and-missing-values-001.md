# Phân biệt thuộc tính vắng mặt, null và giá trị rỗng

Trong JSON, một thuộc tính có thể không xuất hiện, xuất hiện với giá trị null, hoặc xuất hiện với một giá trị rỗng như chuỗi rỗng, mảng rỗng hay object rỗng. Những trạng thái này nhìn qua có vẻ gần nhau, nhưng chúng mang ý nghĩa khác nhau đối với hợp đồng API và cách Jackson tạo object Java.

Ví dụ, ba payload sau không tương đương:

~~~json
{}
~~~

~~~json
{ "nickname": null }
~~~

~~~json
{ "nickname": "" }
~~~

- Payload thứ nhất không gửi thuộc tính nickname.
- Payload thứ hai gửi thuộc tính nickname và giá trị của nó là null.
- Payload thứ ba gửi một chuỗi có độ dài bằng không.

Nếu ứng dụng dùng cả ba trạng thái để quyết định cập nhật dữ liệu, việc phân biệt chúng là bắt buộc. Nếu ứng dụng chỉ cần biết nickname có nội dung hay không, có thể chuẩn hóa nhiều trạng thái về cùng một kết quả, nhưng đó phải là quyết định có chủ đích.

Jackson ánh xạ các trạng thái JSON này vào kiểu Java dựa trên kiểu đích, constructor, giá trị khởi tạo, annotation và cấu hình. Hiểu rõ từng lớp giúp tránh vô tình biến dữ liệu bị thiếu thành giá trị mặc định hoặc làm mất ý nghĩa của thao tác cập nhật từng phần.

## 1. Những trạng thái thường bị nhầm lẫn

Xét thuộc tính tags của một request:

| JSON | Ý nghĩa ở cấp dữ liệu |
|---|---|
| Không có thuộc tính tags | Producer không cung cấp thông tin tags. |
| "tags": null | Producer cung cấp tags nhưng giá trị được xác định là null. |
| "tags": "" | Một chuỗi tồn tại nhưng không có ký tự. |
| "tags": [] | Một danh sách tồn tại nhưng không có phần tử. |
| "tags": {} | Một object tồn tại nhưng không có thuộc tính con. |
| "tags": ["java"] | Một danh sách có một phần tử. |

Các giá trị khác cũng cần được phân biệt:

- 0 là một số hợp lệ, không phải giá trị bị thiếu.
- false là một giá trị boolean hợp lệ, không phải giá trị bị thiếu.
- Chuỗi chỉ chứa khoảng trắng không giống chuỗi rỗng.
- Mảng có phần tử null không giống mảng rỗng.
- Object có một thuộc tính mang null không giống object rỗng.

Ví dụ:

~~~json
{
  "enabled": false,
  "retryCount": 0,
  "description": "",
  "tags": [],
  "metadata": {},
  "aliases": [null]
}
~~~

Tất cả thuộc tính trên đều có mặt. Nếu code chỉ kiểm tra truthy/falsy hoặc chỉ kiểm tra giá trị khác null, có thể vô tình loại bỏ dữ liệu hợp lệ như false và 0.

## 2. JSON có ít kiểu dữ liệu hơn Java

JSON phân biệt object, array, string, number, boolean và null. JSON không có một kiểu riêng để biểu diễn trạng thái "không gửi thuộc tính"; sự vắng mặt được thể hiện bằng việc không có cặp tên/giá trị trong object.

Java có thêm kiểu nguyên thủy, kiểu tham chiếu, collection, Optional và các kiểu miền dữ liệu. Khi Jackson deserialize, trạng thái vắng mặt không tự động trở thành một đối tượng Java đặc biệt. Kết quả phụ thuộc vào kiểu đích và cách tạo object.

| Kiểu Java | Khi thuộc tính bị thiếu | Khi JSON gửi null |
|---|---|---|
| String | Thường là null nếu không có giá trị khởi tạo khác. | Thường là null. |
| Integer, Long, Boolean | Thường là null nếu không có giá trị khởi tạo khác. | Thường là null. |
| int, long, boolean | Giá trị mặc định của kiểu nguyên thủy nếu không có creator/default khác: 0 hoặc false. | Có thể được chuyển thành giá trị mặc định tùy cấu hình; có thể từ chối bằng feature phù hợp. |
| List, Map | Thường là null nếu không có giá trị khởi tạo khác. | Thường là null. |
| String với giá trị khởi tạo trong field | Giá trị khởi tạo có thể được giữ nếu property không được gán. | Có thể bị ghi đè thành null khi setter/property được xử lý. |
| Optional<T> | Với module hỗ trợ Optional, thường trở thành Optional.empty(). | Thường cũng trở thành Optional.empty(); không giữ được khác biệt chỉ bằng Optional thông thường. |

Bảng này mô tả hành vi phổ biến với bean binding. Constructor-based binding, creator properties, custom deserializer và cấu hình Jackson có thể thay đổi kết quả. Khi trạng thái thiếu và null có ý nghĩa nghiệp vụ khác nhau, không nên suy đoán từ bảng mặc định; hãy định nghĩa rõ cách binding và kiểm thử.

## 3. Thuộc tính bị thiếu khi deserialize POJO

Với Java bean có constructor không tham số và setter, Jackson thường chỉ gọi setter cho những thuộc tính có trong JSON.

~~~java
public class ProfileRequest {
    private String nickname = "guest";
    private int age = 18;

    public ProfileRequest() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Khi đọc:

~~~json
{}
~~~

Jackson tạo object bằng constructor không tham số. Vì JSON không có nickname và age, các setter tương ứng không được gọi. Giá trị khởi tạo trong field có thể được giữ: nickname là guest và age là 18.

Đây là hành vi hữu ích khi ứng dụng muốn cung cấp default cho property không được gửi. Nhưng nó cũng có thể che giấu việc producer quên gửi một trường bắt buộc.

Nếu field không có giá trị khởi tạo:

~~~java
private String nickname;
private int age;
~~~

thì trạng thái sau khi đọc object rỗng thường là nickname bằng null và age bằng 0.

Vì vậy, giá trị của một thuộc tính bị thiếu không chỉ do JSON quyết định. Nó còn phụ thuộc vào cách class khởi tạo state.

## 4. Thuộc tính có mặt với null

Với cùng bean ở trên, payload:

~~~json
{
  "nickname": null,
  "age": null
}
~~~

khác với object rỗng. Jackson nhìn thấy hai thuộc tính và xử lý giá trị null cho chúng.

Đối với nickname kiểu String, giá trị thường được gán thành null, ghi đè giá trị khởi tạo guest. Đối với age kiểu int, Java không thể lưu null. Jackson có thể chuyển null thành giá trị mặc định của kiểu nguyên thủy trong cấu hình mặc định, hoặc từ chối nếu bật feature phù hợp.

Có thể yêu cầu từ chối null cho kiểu nguyên thủy:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Khi feature này được bật, JSON gửi null vào thuộc tính int hoặc boolean sẽ gây lỗi deserialize thay vì âm thầm chuyển thành 0 hoặc false.

Feature trên xử lý null vào primitive. Nó không có nghĩa mọi primitive bị thiếu đều bị từ chối. Muốn kiểm soát thuộc tính bị thiếu, cần xem xét creator binding, validation hoặc cơ chế riêng.

## 5. Phân biệt null với giá trị rỗng

Một chuỗi rỗng vẫn là một giá trị String:

~~~json
{ "nickname": "" }
~~~

Một danh sách rỗng vẫn là một List:

~~~json
{ "tags": [] }
~~~

Một object rỗng vẫn là một object:

~~~json
{ "preferences": {} }
~~~

Những giá trị này thường deserialize thành String rỗng, collection rỗng hoặc object có các property không được cung cấp. Chúng không tự chuyển thành null.

Quy tắc nghiệp vụ có thể phân biệt:

- nickname null: người dùng chưa xác định nickname hoặc yêu cầu xóa nickname.
- nickname rỗng: người dùng gửi một chuỗi nhưng không nhập ký tự.
- nickname chỉ có khoảng trắng: có ký tự nhưng không có nội dung hữu ích.
- tags rỗng: người dùng muốn danh sách tag hiện tại trở thành danh sách không có phần tử.
- tags null: người dùng không cung cấp giá trị có thể sử dụng hoặc muốn xóa danh sách, tùy hợp đồng.

Không có một ý nghĩa chung cho null hoặc empty trong mọi API. Hợp đồng phải quy định ý nghĩa của chúng.

## 6. Điều khiển null bằng @JsonSetter

Jackson có annotation @JsonSetter để xác định cách xử lý giá trị null khi gán một property. Thuộc tính nulls cho phép chọn chính sách:

| Nulls | Hành vi |
|---|---|
| SET | Gán null theo hành vi thông thường. |
| SKIP | Bỏ qua việc gán khi input là null. |
| FAIL | Ném lỗi khi input là null. |
| AS_EMPTY | Dùng empty value do deserializer của kiểu đó cung cấp. |
| DEFAULT | Dùng chính sách mặc định của cấu hình. |

Ví dụ, nếu null có nghĩa là giữ nguyên giá trị khởi tạo, có thể dùng SKIP trên setter:

~~~java
public class ProfileRequest {
    private String nickname = "guest";

    public String getNickname() {
        return nickname;
    }

    @JsonSetter(value = "nickname", nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Với payload:

~~~json
{ "nickname": null }
~~~

setter bị bỏ qua theo chính sách SKIP, vì vậy nickname vẫn giữ giá trị khởi tạo guest.

Nếu null phải bị từ chối:

~~~java
@JsonSetter(value = "nickname", nulls = Nulls.FAIL)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
~~~

Nếu null của collection cần được chuyển thành empty collection, có thể dùng AS_EMPTY:

~~~java
public class SearchRequest {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(value = "tags", nulls = Nulls.AS_EMPTY)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
~~~

Hành vi AS_EMPTY phụ thuộc empty value do deserializer cung cấp. Với các collection phổ biến, kết quả thường là collection rỗng. Hãy kiểm tra kiểu cụ thể đang dùng nếu empty value có ý nghĩa đặc biệt.

Lưu ý SKIP trên setter/field là cách hữu ích cho mutable bean. Với constructor creator, tham số được thu thập trước khi constructor được gọi; đừng giả định SKIP sẽ giữ nguyên giá trị field initializer như trường hợp setter. Với creator property, hãy dùng các feature kiểm soát missing/null creator và test trực tiếp.

## 7. Null của collection và null bên trong collection

Jackson phân biệt null của cả container với null của từng phần tử.

Ví dụ:

~~~json
{
  "tags": null,
  "aliases": ["linh", null, "minh"]
}
~~~

- tags là null: toàn bộ property collection có giá trị null.
- aliases là một array có ba phần tử, trong đó phần tử thứ hai là null.

@JsonSetter hỗ trợ hai thuộc tính:

- nulls: xử lý null của chính property.
- contentNulls: xử lý null của từng phần tử bên trong collection, map hoặc container phù hợp.

Ví dụ:

~~~java
public class ProfileRequest {
    private List<String> tags;

    @JsonSetter(
        value = "tags",
        nulls = Nulls.AS_EMPTY,
        contentNulls = Nulls.FAIL
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
~~~

Với cấu hình này, tags null có thể được chuyển thành empty collection, nhưng một phần tử null trong array bị từ chối.

Nếu nghiệp vụ cho phép null element, không bật FAIL một cách máy móc. Ví dụ, một danh sách có phần tử null có thể là dữ liệu hợp lệ trong một hợp đồng cũ, dù thiết kế API mới thường nên tránh kiểu dữ liệu khó xử lý này.

## 8. Kiểm soát thuộc tính bắt buộc trong constructor

Với constructor-based binding, Jackson phải thu thập các giá trị trước khi gọi constructor. Trường bị thiếu và trường null cần được kiểm soát riêng.

Có thể đánh dấu creator property bắt buộc:

~~~java
public record CreateUserRequest(
    @JsonProperty(value = "username", required = true)
    String username,
    @JsonProperty(value = "email", required = true)
    String email
) {}
~~~

Cấu hình FAIL_ON_MISSING_CREATOR_PROPERTIES yêu cầu creator property không được thiếu:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .build();
~~~

Để từ chối creator property có giá trị null, có thể bật:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
~~~

Hai feature có ý nghĩa khác nhau:

- FAIL_ON_MISSING_CREATOR_PROPERTIES từ chối creator property không xuất hiện.
- FAIL_ON_NULL_CREATOR_PROPERTIES từ chối creator property được cung cấp với giá trị null.

Khi chỉ cần kiểm soát một tham số hoặc một kiểu, có thể tạo ObjectReader với feature riêng thay vì bật toàn cục. Sau khi deserialize, vẫn cần validation nghiệp vụ cho username, email và các điều kiện khác.

Không nên coi @JsonProperty(required = true) là cơ chế validation tổng quát cho mọi field của mutable bean. Thuộc tính required chủ yếu có ý nghĩa đối với creator properties; với bean có setter, hãy dùng validation hoặc chính sách deserialization phù hợp.

## 9. Kiểm tra trạng thái bằng JsonNode

Khi cần phân biệt chính xác một property không tồn tại với property có giá trị null, tree model của Jackson rất hữu ích.

~~~java
JsonNode root = mapper.readTree(json);

JsonNode nickname = root.get("nickname");

if (nickname == null) {
    // Property không tồn tại.
} else if (nickname.isNull()) {
    // Property có mặt với JSON null.
} else if (nickname.isTextual() && nickname.asText().isEmpty()) {
    // Property có mặt với chuỗi rỗng.
}
~~~

Có thể dùng path:

~~~java
JsonNode nickname = root.path("nickname");

if (nickname.isMissingNode()) {
    // Không có property.
} else if (nickname.isNull()) {
    // Property tồn tại và có giá trị null.
}
~~~

Hai API có khác biệt:

- get("nickname") trả về null của Java khi property không tồn tại; nếu property có mặt với JSON null thì trả về NullNode.
- path("nickname") trả về MissingNode khi property không tồn tại; nếu property có mặt với JSON null thì trả về NullNode.

Các hàm tiện ích:

| API | Ý nghĩa |
|---|---|
| has("nickname") | true nếu property tồn tại, kể cả khi giá trị là JSON null. |
| hasNonNull("nickname") | true nếu property tồn tại và không phải JSON null. |
| get("nickname") | Trả node hoặc Java null nếu property không tồn tại. |
| path("nickname") | Trả node hoặc MissingNode nếu property không tồn tại. |
| isMissingNode() | Kiểm tra node đại diện cho property không tồn tại. |
| isNull() | Kiểm tra node JSON null. |

Không nên dùng asText() một mình để phân biệt các trạng thái. Một số cách chuyển đổi node sang String có thể trả về chuỗi rỗng hoặc giá trị fallback cho node thiếu/null, khiến thông tin trạng thái ban đầu bị mất.

## 10. Phân biệt thiếu và null trong API cập nhật từng phần

Sự khác biệt có ý nghĩa lớn nhất thường xuất hiện ở API PATCH hoặc các thao tác cập nhật từng phần.

Giả sử profile hiện tại là:

~~~json
{
  "displayName": "Linh",
  "nickname": "L"
}
~~~

Client gửi:

~~~json
{
  "displayName": "Linh Nguyen"
}
~~~

Nếu hợp đồng quy định property bị thiếu có nghĩa là không thay đổi, nickname phải giữ nguyên.

Nếu client gửi:

~~~json
{
  "nickname": null
}
~~~

hợp đồng có thể quy định xóa nickname.

Nếu client gửi:

~~~json
{
  "nickname": ""
}
~~~

hợp đồng có thể quy định đặt nickname thành chuỗi rỗng, hoặc từ chối vì không hợp lệ. Không thể tự suy ra ý nghĩa chỉ từ JSON.

Vấn đề là một DTO Java thông thường với field nullable thường không giữ được sự khác biệt giữa property bị thiếu và property explicit null sau khi deserialize. Cả hai có thể trở thành null.

Có một số cách mô hình hóa:

### Dùng tree model để kiểm tra presence

Với request PATCH có số lượng trường nhỏ hoặc cần logic đặc biệt, có thể đọc thành JsonNode, kiểm tra has/hasNonNull rồi áp dụng thay đổi có chủ đích.

~~~java
JsonNode patch = mapper.readTree(requestBody);

if (patch.has("nickname")) {
    JsonNode value = patch.get("nickname");

    if (value.isNull()) {
        profile.clearNickname();
    } else {
        profile.changeNickname(value.asText());
    }
}
~~~

Đoạn code phân biệt property không tồn tại với property có mặt. Nếu value là object hoặc array thay vì string, cần kiểm tra node type trước khi gọi asText và trả lỗi validation phù hợp.

### Dùng wrapper biểu diễn ba trạng thái

Thư viện jackson-databind-nullable của OpenAPI cung cấp JsonNullable để phân biệt undefined với explicit null và một giá trị cụ thể. Mô hình khái niệm:

- JsonNullable.undefined(): property không xuất hiện.
- JsonNullable.of(null): property có mặt với null.
- JsonNullable.of(value): property có mặt với giá trị.

Ví dụ sử dụng cần thêm dependency tương ứng và đăng ký JsonNullableModule theo tài liệu của phiên bản thư viện:

~~~java
public class ProfilePatchRequest {
    private JsonNullable<String> nickname = JsonNullable.undefined();

    public JsonNullable<String> getNickname() {
        return nickname;
    }

    public void setNickname(JsonNullable<String> nickname) {
        this.nickname = nickname;
    }
}
~~~

Khi áp dụng, kiểm tra kỹ cách module xử lý property thiếu, null và serialization. Không nên chỉ thay String bằng Optional<String> rồi kỳ vọng có ba trạng thái; Optional thông thường chỉ có empty hoặc present và thường gộp thiếu với null khi deserialize.

### Dùng quy ước JSON Merge Patch hoặc JSON Patch

Nếu API áp dụng JSON Merge Patch, null trong object patch mang ý nghĩa xóa thuộc tính theo quy tắc của định dạng đó. Điều này khác với một DTO JSON thông thường nơi null chỉ là một giá trị. Nếu API cần biểu diễn rõ thao tác xóa, thay thế và thêm, có thể dùng JSON Patch hoặc một hợp đồng command riêng.

Đừng trộn ngữ nghĩa PATCH vào mọi request DTO. POST/PUT/PATCH có thể có quy tắc presence khác nhau; hãy ghi rõ trong hợp đồng và kiểm tra từng thao tác.

## 11. Điều khiển dữ liệu null và rỗng khi serialize

Các trạng thái cũng cần được xem xét ở chiều ghi JSON.

Jackson có @JsonInclude để quyết định property nào được đưa vào output:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProfileResponse(
    String nickname,
    List<String> tags
) {}
~~~

Với NON_NULL, property có giá trị null bị bỏ qua khi serialize. Ví dụ object Java có nickname null có thể được ghi thành:

~~~json
{
  "tags": []
}
~~~

Để loại cả các giá trị rỗng phổ biến, có thể dùng NON_EMPTY:

~~~java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public record ProfileResponse(
    String nickname,
    List<String> tags,
    Map<String, String> metadata
) {}
~~~

NON_EMPTY có thể loại bỏ chuỗi rỗng, collection rỗng, map rỗng và các giá trị empty theo định nghĩa của kiểu. Vì vậy, nó có phạm vi rộng hơn NON_NULL.

Một số lựa chọn thường gặp:

| Include | Hành vi khái quát |
|---|---|
| ALWAYS | Luôn đưa property vào, kể cả null. |
| NON_NULL | Bỏ property có giá trị null. |
| NON_ABSENT | Bỏ giá trị null và giá trị absent của các kiểu hỗ trợ khái niệm absent như Optional. |
| NON_EMPTY | Bỏ null và các giá trị rỗng theo quy tắc của Jackson. |
| NON_DEFAULT | Bỏ các giá trị được xem là mặc định theo ngữ cảnh cấu hình. |

Cần nhớ rằng @JsonInclude chỉ điều khiển serialize. Nó không làm cho property bắt buộc khi deserialize và cũng không giữ lại trạng thái presence đã mất trong quá trình đọc.

Nếu hợp đồng yêu cầu luôn phát ra tags dưới dạng array rỗng khi không có phần tử, không nên dùng NON_EMPTY cho property đó. Ngược lại, nếu null và empty đều có nghĩa là không có nội dung, NON_EMPTY có thể phù hợp.

## 12. Validation nên được thực hiện sau khi hiểu rõ presence

Jackson chịu trách nhiệm parse và bind. Bean Validation hoặc logic nghiệp vụ chịu trách nhiệm đánh giá giá trị có hợp lệ hay không.

Ví dụ:

~~~java
public record CreateProfileRequest(
    @NotBlank String displayName,
    @NotNull List<@NotBlank String> tags
) {}
~~~

- @NotNull kiểm tra giá trị không phải null.
- @NotBlank kiểm tra chuỗi không null, không rỗng và có ký tự không phải whitespace.
- Với collection, có thể dùng @NotEmpty nếu yêu cầu collection phải có ít nhất một phần tử.
- Constraint trên phần tử collection kiểm tra từng phần tử, không chỉ container.

Tuy nhiên, nếu field có giá trị khởi tạo, property bị thiếu có thể giữ giá trị đó và vượt qua validation. Nếu hợp đồng yêu cầu client phải gửi field, cần kiểm tra presence ở creator binding hoặc tree/wrapper model, không chỉ dựa vào @NotNull.

Với constructor creator, có thể dùng required property và FAIL_ON_MISSING_CREATOR_PROPERTIES. Với explicit null, dùng FAIL_ON_NULL_CREATOR_PROPERTIES hoặc chính sách null phù hợp. Sau đó chạy Bean Validation cho các ràng buộc như độ dài, định dạng và miền giá trị.

## 13. Checklist thiết kế hợp đồng cho từng property

Khi thêm một property vào request hoặc response, hãy xác định rõ:

1. Property có bắt buộc xuất hiện không?
2. Nếu xuất hiện, có cho phép null không?
3. Chuỗi rỗng có hợp lệ không?
4. Collection rỗng có khác với null không?
5. Property bị thiếu mang nghĩa default, không thay đổi hay lỗi?
6. Explicit null mang nghĩa không có giá trị, xóa giá trị hay lỗi?
7. Khi serialize, null và empty có được đưa vào output không?
8. Có cần phân biệt presence để hỗ trợ PATCH hoặc cập nhật từng phần không?

Các câu trả lời này phải nhất quán giữa producer, consumer, DTO, Jackson configuration và validation. Một annotation đơn lẻ không thể định nghĩa toàn bộ hợp đồng.

## Kết luận

Thuộc tính vắng mặt, null và giá trị rỗng là ba trạng thái khác nhau ở cấp JSON. Jackson có thể ánh xạ chúng thành các kết quả Java khác nhau tùy kiểu đích, field initializer, creator, annotation và feature cấu hình.

Hãy quy định rõ ý nghĩa của từng trạng thái trong hợp đồng. Dùng @JsonSetter để kiểm soát explicit null, creator features để kiểm soát property bắt buộc, JsonNode hoặc wrapper ba trạng thái khi cần giữ presence cho PATCH, và @JsonInclude để quyết định cách ghi null/empty ra JSON. Kiểm thử riêng trường hợp thiếu, null, rỗng, 0 và false để tránh làm mất dữ liệu hoặc vô tình thay đổi ý nghĩa thao tác.

