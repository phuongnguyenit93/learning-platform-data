# Phân biệt MissingNode và NullNode

Khi làm việc với Jackson Tree Model, hai trạng thái rất dễ bị nhầm là **MissingNode** và **NullNode**. Cả hai đều không chứa một giá trị nghiệp vụ thông thường, nhưng ý nghĩa hoàn toàn khác nhau:

- **MissingNode** biểu diễn một vị trí không tồn tại trong cây JSON. Nó thường được trả về khi truy cập một property hoặc array index không có bằng path() hoặc at().
- **NullNode** biểu diễn giá trị JSON null thực sự. Nó xuất hiện khi payload có field với giá trị null hoặc có phần tử null trong array.

Phân biệt hai node này rất quan trọng khi xử lý request PATCH, kiểm tra field bắt buộc, đọc webhook có cấu trúc thay đổi hoặc cần giữ nguyên sự khác biệt giữa "không gửi thuộc tính" và "gửi thuộc tính với null".

Quy tắc cần nhớ: **MissingNode là dấu hiệu không tìm thấy vị trí; NullNode là một giá trị có mặt trong JSON nhưng giá trị của nó là null.** Java null do get() trả về lại là trạng thái thứ ba, biểu diễn việc không tìm thấy node qua API đó.

## 1. Ba trạng thái cần phân biệt

Giả sử payload:

~~~json
{
  "name": "An",
  "nickname": null,
  "roles": []
}
~~~

Có ba tình huống khác nhau khi đọc field:

| Input | Kết quả truy cập | Ý nghĩa |
|---|---|---|
| Field name có giá trị | TextNode | Property có mặt và có value |
| Field nickname là null | NullNode | Property có mặt, value là JSON null |
| Field email không xuất hiện | MissingNode với path(), Java null với get() | Property không tồn tại |
| Field roles là [] | ArrayNode rỗng | Property có mặt, collection rỗng |

Cần phân biệt cả Java null và hai loại JsonNode:

1. Java null: một tham chiếu Java không trỏ tới đối tượng node.
2. MissingNode: một node sentinel do Jackson trả về để biểu diễn vị trí không tồn tại.
3. NullNode: một node thực sự đại diện cho JSON null.

Java null không phải một kiểu JsonNode. MissingNode và NullNode đều là object thuộc cây kiểu JsonNode.

## 2. NullNode là gì?

NullNode biểu diễn token JSON null. Khi JSON chứa:

~~~json
{
  "middleName": null
}
~~~

Jackson tạo một node null cho property middleName.

Có thể kiểm tra:

~~~java
JsonNode root = mapper.readTree("""
    {
      "middleName": null
    }
    """);

JsonNode node = root.get("middleName");

System.out.println(node == null); // false
System.out.println(node.isNull()); // true
System.out.println(node.isMissingNode()); // false
~~~

NullNode có mặt trong cây JSON. Nó có thể được tìm thấy khi duyệt object fields, kiểm tra property và xử lý dữ liệu.

### 2.1. NullNode không phải Java null

Hai biểu thức sau không tương đương:

~~~java
node == null
node.isNull()
~~~

- node == null kiểm tra tham chiếu Java có null hay không.
- node.isNull() kiểm tra node có phải đại diện cho JSON null hay không.

Nếu dùng get() và field tồn tại với JSON null, node khác Java null nhưng isNull() trả true.

Nếu dùng path() và field tồn tại với JSON null, kết quả cũng là NullNode.

### 2.2. NullNode có kiểu node riêng

Có thể kiểm tra bằng JsonNodeType:

~~~java
JsonNode node = root.path("middleName");

if (node.getNodeType() == JsonNodeType.NULL) {
    // JSON property có mặt với giá trị null.
}
~~~

Thông thường isNull() dễ đọc hơn. JsonNodeType hữu ích khi code cần phân nhánh theo nhiều loại node.

## 3. MissingNode là gì?

MissingNode là node đặc biệt mà Jackson dùng để biểu diễn một vị trí không tìm thấy trong cây. Nó không phải một token JSON có thể xuất hiện trong payload như null.

Ví dụ:

~~~java
JsonNode root = mapper.readTree("""
    {
      "name": "An"
    }
    """);

JsonNode email = root.path("email");

System.out.println(email.isMissingNode()); // true
System.out.println(email.isNull()); // false
~~~

Property email không có trong JSON. path() trả về MissingNode thay vì Java null.

### 3.1. MissingNode thường xuất hiện từ path() và at()

Hai thao tác truy cập an toàn thường trả MissingNode khi không tìm thấy:

~~~java
JsonNode missingByPath = root.path("email");
JsonNode missingByPointer = root.at("/profile/email");
~~~

Cả hai có thể kiểm tra bằng isMissingNode().

get() hoạt động khác: khi property không tồn tại, get() trả Java null.

### 3.2. MissingNode là sentinel, không phải dữ liệu người gửi

Người gửi JSON không thể gửi một token tên MissingNode. Đây là biểu diễn nội bộ của Jackson để giúp API truy cập cây có thể trả về một JsonNode ngay cả khi vị trí không tồn tại.

Vì vậy, đừng diễn giải MissingNode thành một giá trị JSON mà client đã gửi. Nó chỉ cho biết đường dẫn mà code hỏi không tìm thấy node.

## 4. get() và path(): nguồn gốc của khác biệt

Sự khác biệt dễ thấy nhất giữa MissingNode và NullNode xuất hiện khi dùng get() và path().

Giả sử JSON:

~~~json
{
  "nickname": null
}
~~~

Truy cập:

~~~java
JsonNode nicknameWithGet = root.get("nickname");
JsonNode emailWithGet = root.get("email");

JsonNode nicknameWithPath = root.path("nickname");
JsonNode emailWithPath = root.path("email");
~~~

Kết quả:

| Biểu thức | Kết quả | Kiểm tra |
|---|---|---|
| get("nickname") | NullNode | isNull() = true |
| get("email") | Java null | Tham chiếu == null |
| path("nickname") | NullNode | isNull() = true |
| path("email") | MissingNode | isMissingNode() = true |

Code kiểm tra:

~~~java
assertNotNull(root.get("nickname"));
assertTrue(root.get("nickname").isNull());

assertNull(root.get("email"));

assertTrue(root.path("nickname").isNull());
assertTrue(root.path("email").isMissingNode());
~~~

Cả get() và path() đều giữ được sự phân biệt giữa explicit null và missing, nhưng biểu diễn missing khác nhau.

## 5. has() và hasNonNull() có phân biệt được không?

ObjectNode/JsonNode cung cấp has() và hasNonNull() để kiểm tra property.

Với payload:

~~~json
{
  "name": "An",
  "nickname": null
}
~~~

Kết quả:

~~~java
root.has("name");           // true
root.hasNonNull("name");    // true

root.has("nickname");       // true
root.hasNonNull("nickname");// false

root.has("email");          // false
root.hasNonNull("email");   // false
~~~

| Trạng thái | has() | hasNonNull() |
|---|---:|---:|
| Có value khác null | true | true |
| Explicit JSON null | true | false |
| Missing | false | false |

has() phân biệt property có mặt với property không có. hasNonNull() chỉ trả true khi property có mặt và không phải NullNode.

Lưu ý: hasNonNull() gộp explicit null và missing thành cùng kết quả false. Nếu cần biết chính xác client đã gửi null hay không gửi field, hãy dùng has() rồi kiểm tra node.

## 6. Cách kiểm tra đầy đủ ba trạng thái

Một helper đơn giản có thể phân loại field:

~~~java
public enum FieldPresence {
    MISSING,
    NULL,
    VALUE
}

public static FieldPresence presence(
    JsonNode object,
    String fieldName
) {
    JsonNode node = object.get(fieldName);

    if (node == null) {
        return FieldPresence.MISSING;
    }

    if (node.isNull()) {
        return FieldPresence.NULL;
    }

    return FieldPresence.VALUE;
}
~~~

Sử dụng:

~~~java
switch (presence(root, "nickname")) {
    case MISSING -> System.out.println("Field was not sent");
    case NULL -> System.out.println("Field was sent as null");
    case VALUE -> System.out.println("Field has a value");
}
~~~

Helper này giả định node gốc là object. Nếu root có thể là array, scalar hoặc null, cần kiểm tra root.isObject() trước khi gọi logic xử lý property.

Một cách khác dùng path():

~~~java
JsonNode node = root.path("nickname");

if (node.isMissingNode()) {
    // Không có property.
} else if (node.isNull()) {
    // Property có mặt với null.
} else {
    // Property có value.
}
~~~

Dùng path() phù hợp khi muốn tránh Java null. Dùng get() phù hợp khi muốn biểu diễn missing bằng tham chiếu Java null và kiểm tra rõ ràng.

## 7. MissingNode và NullNode trong truy cập lồng nhau

Giả sử JSON:

~~~json
{
  "customer": {
    "profile": {
      "nickname": null
    }
  }
}
~~~

Có thể có các tình huống:

- customer không có: đường dẫn customer/profile/nickname là missing.
- customer có nhưng null: không thể đi tiếp vào object customer; kết quả truy cập cấp sâu hơn là missing.
- profile không có: nickname là missing.
- nickname có và null: kết quả là NullNode.

Ví dụ:

~~~java
JsonNode nickname = root
    .path("customer")
    .path("profile")
    .path("nickname");

if (nickname.isMissingNode()) {
    // Một cấp trong đường dẫn không tồn tại.
} else if (nickname.isNull()) {
    // nickname tồn tại nhưng có giá trị null.
} else {
    String value = nickname.asText();
}
~~~

Một giới hạn quan trọng: khi dùng chain path(), nếu một cấp trung gian bị thiếu, kết quả cuối cùng chỉ cho biết đường dẫn không tìm thấy. Nó không cho biết chính xác cấp nào bị thiếu. Nếu cần thông báo lỗi chi tiết cho từng cấp, hãy kiểm tra từng node riêng.

Ví dụ:

~~~java
JsonNode customer = root.path("customer");

if (customer.isMissingNode()) {
    throw new IllegalArgumentException("customer is required");
}
if (customer.isNull()) {
    throw new IllegalArgumentException("customer cannot be null");
}
if (!customer.isObject()) {
    throw new IllegalArgumentException("customer must be an object");
}

JsonNode profile = customer.path("profile");

if (profile.isMissingNode()) {
    throw new IllegalArgumentException("profile is required");
}
if (profile.isNull()) {
    throw new IllegalArgumentException("profile cannot be null");
}
~~~

## 8. MissingNode và NullNode trong array

JSON array có thể chứa explicit null:

~~~json
{
  "items": [
    "A",
    null,
    "C"
  ]
}
~~~

Phần tử ở index 1 là NullNode:

~~~java
JsonNode items = root.path("items");

JsonNode second = items.get(1);

assertNotNull(second);
assertTrue(second.isNull());
~~~

Nếu truy cập index ngoài phạm vi:

~~~java
JsonNode outOfRangeByGet = items.get(3);
JsonNode outOfRangeByPath = items.path(3);
~~~

- get(3) trả Java null.
- path(3) trả MissingNode.

Bảng phân biệt:

| Array situation | get(index) | path(index) |
|---|---|---|
| Index có value | Node value | Node value |
| Index có explicit null | NullNode | NullNode |
| Index ngoài phạm vi | Java null | MissingNode |

Đừng nhầm phần tử null với phần tử không tồn tại. Array có null vẫn có size() bao gồm vị trí đó. Index ngoài phạm vi không thuộc array.

## 9. at() và JsonPointer

at() nhận JSON Pointer và trả node ở vị trí tương ứng. Nếu đường dẫn không tồn tại, nó trả MissingNode.

Ví dụ:

~~~java
JsonNode status = root.at("/order/status");
~~~

Nếu JSON có:

~~~json
{
  "order": {
    "status": null
  }
}
~~~

status là NullNode.

Nếu JSON không có order hoặc status, status là MissingNode.

Kiểm tra:

~~~java
if (status.isMissingNode()) {
    // JSON Pointer không tìm thấy vị trí.
} else if (status.isNull()) {
    // Vị trí tồn tại và có JSON null.
}
~~~

at() giúp tránh phải chain nhiều lần path(). Tuy nhiên, khi cần biết cấp nào trong đường dẫn bị thiếu, hãy kiểm tra từng cấp hoặc dùng JsonPointer từng bước.

## 10. Truy cập value có thể làm mất khác biệt

Các phương thức chuyển đổi value như asText(), asInt(), asBoolean() có thể trả fallback. Nếu gọi ngay mà không kiểm tra node, code có thể làm mất sự khác biệt giữa MissingNode, NullNode và node có value.

Ví dụ:

~~~java
String name = root.path("name").asText("");
~~~

Nếu name missing, fallback rỗng được trả về. Nếu name explicit null, hành vi accessor cũng có thể cho kết quả fallback theo API node. Sau phép chuyển đổi, code chỉ còn một chuỗi rỗng và không còn biết trạng thái đầu vào ban đầu.

Với số:

~~~java
int quantity = root.path("quantity").asInt(0);
~~~

quantity missing, null hoặc sai kiểu có thể bị nhập vào cùng giá trị fallback tùy phương thức chuyển đổi. Nếu 0 là giá trị hợp lệ, điều này có thể che giấu lỗi.

Cách an toàn:

~~~java
JsonNode quantityNode = root.path("quantity");

if (quantityNode.isMissingNode()) {
    throw new IllegalArgumentException("quantity is missing");
}
if (quantityNode.isNull()) {
    throw new IllegalArgumentException("quantity cannot be null");
}
if (!quantityNode.isIntegralNumber()
        || !quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("quantity must be an integer");
}

int quantity = quantityNode.intValue();
~~~

Nguyên tắc: kiểm tra presence và null trước, kiểm tra kiểu tiếp theo, rồi mới chuyển value.

## 11. Ảnh hưởng khi chuyển JsonNode thành POJO

Khi dùng Tree Model, Jackson giữ được MissingNode/NullNode ở cấp truy cập cây. Nhưng khi chuyển sang POJO, sự khác biệt có thể bị mất tùy kiểu field và cơ chế khởi tạo.

Ví dụ:

~~~java
public class UserPatch {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Nếu deserialize trực tiếp JSON thành UserPatch:

- JSON không có nickname: field có thể giữ giá trị khởi tạo hoặc null tùy cách tạo object.
- JSON có nickname: null: setter có thể nhận null.
- Nếu field ban đầu đã null, cả missing và explicit null đều có thể cho kết quả Java null.

Vì vậy, nếu API cần phân biệt missing và null, DTO thông thường chỉ có String có thể không đủ. Cần một kiểu presence wrapper hoặc xử lý bằng JsonNode trước khi mapping.

### 11.1. Đọc JsonNode rồi chuyển phần value

Có thể kiểm tra trạng thái trước:

~~~java
JsonNode root = mapper.readTree(json);
JsonNode nickname = root.get("nickname");

if (nickname == null) {
    // Không cập nhật nickname.
} else if (nickname.isNull()) {
    // Xóa nickname.
} else if (nickname.isTextual()) {
    String value = nickname.textValue();
    // Gán nickname mới.
} else {
    throw new IllegalArgumentException("nickname must be a string or null");
}
~~~

Đây là cách đơn giản để giữ presence semantics cho một field.

### 11.2. Dùng wrapper presence

Với ứng dụng có nhiều PATCH DTO, có thể tạo một kiểu biểu diễn ba trạng thái:

~~~java
public sealed interface FieldValue<T>
        permits FieldValue.Missing, FieldValue.NullValue, FieldValue.Present {

    record Missing<T>() implements FieldValue<T> {}
    record NullValue<T>() implements FieldValue<T> {}
    record Present<T>(T value) implements FieldValue<T> {}
}
~~~

Adapter đọc JsonNode có thể trả về:

- Missing khi get() trả Java null.
- NullValue khi node.isNull().
- Present(value) khi node hợp lệ và đã được chuyển đổi.

Wrapper giúp tầng service không phải xử lý JsonNode trực tiếp. Đây là một thiết kế ứng dụng, không phải kiểu Jackson cung cấp sẵn.

## 12. PATCH semantics: vì sao phân biệt rất quan trọng?

Trong API PATCH, ba trạng thái thường có ý nghĩa khác nhau:

| JSON input | Ý nghĩa cập nhật |
|---|---|
| Field không xuất hiện | Giữ nguyên giá trị hiện tại |
| Field có mặt với null | Xóa giá trị hiện tại hoặc đặt null |
| Field có mặt với value | Thay bằng giá trị mới |

Ví dụ dữ liệu hiện tại:

~~~json
{
  "displayName": "An",
  "phone": "0900000000"
}
~~~

Request PATCH:

~~~json
{
  "displayName": null
}
~~~

Theo semantics trên:

- displayName được xóa.
- phone được giữ nguyên vì field không xuất hiện.

Nếu code deserialize thẳng vào DTO mà cả missing và null đều trở thành Java null, service không biết nên giữ hay xóa displayName/phone. Đây là lỗi phổ biến khi dùng DTO update thông thường cho PATCH.

Cách xử lý bằng JsonNode:

~~~java
JsonNode patch = mapper.readTree(json);

if (patch.has("displayName")) {
    JsonNode value = patch.get("displayName");

    if (value.isNull()) {
        user.clearDisplayName();
    } else if (value.isTextual()) {
        user.rename(value.textValue());
    } else {
        throw new IllegalArgumentException(
            "displayName must be a string or null"
        );
    }
}
~~~

Điều kiện patch.has("displayName") chỉ true khi property có mặt, kể cả explicit null. Nếu field missing, khối cập nhật không chạy.

Nếu API tuân theo JSON Merge Patch (RFC 7396), null trong object patch có semantics xóa property đích. Cần xác định rõ media type và quy tắc áp dụng, vì một API PATCH tùy chỉnh có thể định nghĩa khác. Đừng tự động giả định mọi endpoint PATCH đều là JSON Merge Patch.

## 13. Kiểm tra field bắt buộc và field tùy chọn

Đối với field bắt buộc, nên phân biệt:

- Missing: client không cung cấp field.
- Null: client cung cấp nhưng không có giá trị.
- Sai kiểu: client cung cấp giá trị nhưng không đúng schema.
- Empty: có giá trị đúng kiểu nhưng rỗng, ví dụ chuỗi "" hoặc array [].

Ví dụ kiểm tra email:

~~~java
JsonNode email = root.path("email");

if (email.isMissingNode()) {
    throw new IllegalArgumentException("email is required");
}
if (email.isNull()) {
    throw new IllegalArgumentException("email cannot be null");
}
if (!email.isTextual() || email.textValue().isBlank()) {
    throw new IllegalArgumentException("email must be a non-empty string");
}
~~~

Với field tùy chọn, hợp đồng có thể cho phép missing và null, nhưng vẫn cần quyết định hai trường hợp có cùng ý nghĩa không.

Đừng dùng hasNonNull() cho field bắt buộc nếu muốn phân biệt lỗi missing và explicit null; nó chỉ trả false cho cả hai.

## 14. MissingNode không giống EmptyNode hoặc empty value

Một số trạng thái khác cũng dễ nhầm:

| Node/value | Ý nghĩa |
|---|---|
| MissingNode | Vị trí không tồn tại trong cây |
| NullNode | JSON null |
| TextNode("") | String có mặt nhưng rỗng |
| ArrayNode rỗng | Array có mặt nhưng không có phần tử |
| ObjectNode rỗng | Object có mặt nhưng không có property |
| BooleanNode(false) | Giá trị boolean false |
| IntNode(0) | Giá trị số 0 |

Ví dụ:

~~~json
{
  "missingExample": null,
  "emptyText": "",
  "emptyArray": [],
  "emptyObject": {},
  "enabled": false,
  "count": 0
}
~~~

Trong JSON trên, missingExample không phải MissingNode; nó là NullNode vì field có mặt với null. Một field hoàn toàn không được khai báo mới là missing.

Không nên dùng isEmpty() để kiểm tra missing hoặc null. isEmpty() chủ yếu liên quan đến container không có phần tử/property; hãy dùng isMissingNode() và isNull() cho đúng semantics.

## 15. Test phân biệt MissingNode và NullNode

Nên viết test trực tiếp cho các trạng thái:

~~~java
@Test
void distinguishesMissingAndNullNodes() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "nickname": null,
          "name": "An",
          "roles": []
        }
        """);

    assertTrue(root.path("email").isMissingNode());
    assertFalse(root.path("email").isNull());

    assertTrue(root.path("nickname").isNull());
    assertFalse(root.path("nickname").isMissingNode());

    assertTrue(root.path("name").isTextual());
    assertTrue(root.path("roles").isArray());
    assertEquals(0, root.path("roles").size());
}
~~~

Test get():

~~~java
@Test
void getUsesJavaNullForMissingProperty() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "nickname": null
        }
        """);

    assertNull(root.get("email"));
    assertNotNull(root.get("nickname"));
    assertTrue(root.get("nickname").isNull());
}
~~~

Test has():

~~~java
@Test
void hasDistinguishesPresenceFromNonNull() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "nickname": null
        }
        """);

    assertTrue(root.has("nickname"));
    assertFalse(root.hasNonNull("nickname"));

    assertFalse(root.has("email"));
    assertFalse(root.hasNonNull("email"));
}
~~~

Test nested path:

~~~java
@Test
void pathReturnsMissingNodeForMissingNestedPath() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "customer": {
            "profile": {
              "nickname": null
            }
          }
        }
        """);

    assertTrue(
        root.path("customer").path("profile")
            .path("email").isMissingNode()
    );

    assertTrue(
        root.path("customer").path("profile")
            .path("nickname").isNull()
    );
}
~~~

Test array:

~~~java
@Test
void distinguishesNullArrayElementAndOutOfRangeIndex() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "items": ["A", null]
        }
        """);

    JsonNode items = root.path("items");

    assertTrue(items.path(1).isNull());
    assertTrue(items.path(2).isMissingNode());
}
~~~

Các test này bảo vệ semantics của payload. Nếu code chuyển sang dùng asText() hoặc asInt() với fallback mà không kiểm tra node, test có thể giúp phát hiện việc missing/null bị nhập làm một.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| So sánh node với null rồi coi đó là JSON null | Nhầm Java null với NullNode | Dùng isNull() cho JSON null |
| Dùng isNull() để phát hiện field không tồn tại | MissingNode không phải NullNode | Dùng isMissingNode() hoặc get()==null |
| Dùng hasNonNull() để kiểm tra field có gửi không | hasNonNull() false cho cả missing và null | Dùng has() |
| Chain get() gây NullPointerException | get() trả Java null khi thiếu cấp trung gian | Dùng path() hoặc kiểm tra từng cấp |
| Chain path() nhưng bỏ qua kiểm tra kiểu | path() chỉ an toàn với missing, không bảo đảm schema | Dùng isObject(), isTextual(), isArray() |
| Dùng fallback asText/asInt quá sớm | Làm mất khác biệt input | Kiểm tra missing/null/type trước khi chuyển |
| Deserialize PATCH vào DTO thường | Missing và null có thể cùng thành null | Dùng JsonNode hoặc presence wrapper |
| Coi [] hoặc {} là missing | Nhầm empty container với vị trí không tồn tại | Kiểm tra isArray/isObject và size() |
| Giả định MissingNode là token JSON | Nhầm sentinel truy cập với dữ liệu nguồn | Xem MissingNode là kết quả lookup |

## 17. Quy trình xử lý một property trong Tree Model

~~~text
Truy cập property bằng get() hoặc path()
                  |
                  v
         Node có tồn tại?
             /       \
           Không      Có
            |         |
            v         v
         MISSING   Node là NullNode?
                       /      \
                     Có        Không
                     |          |
                     v          v
                   NULL     Kiểm tra kiểu
                                |
                                v
                         Chuyển value và
                         validate nghiệp vụ
~~~

Nếu dùng get(), nhánh "Không" là Java null. Nếu dùng path(), nhánh "Không" là MissingNode. Khi property có mặt với JSON null, cả hai đều cho NullNode.

Đối với field lồng nhau, thực hiện kiểm tra theo từng cấp nếu cần thông báo chính xác cấp nào bị thiếu hoặc null.

## 18. Nguyên tắc thiết kế

1. **Phân biệt ba trạng thái:** Java null, MissingNode và NullNode có ý nghĩa khác nhau.
2. **Dùng đúng API:** get() trả Java null khi missing; path()/at() trả MissingNode.
3. **Kiểm tra presence riêng:** has() phân biệt property có mặt; hasNonNull() gộp missing và null.
4. **Kiểm tra kiểu trước khi đọc:** MissingNode và NullNode không phải object, array hoặc scalar hợp lệ cho mọi field.
5. **Không dùng fallback quá sớm:** asText/asInt có thể làm mất thông tin về trạng thái input.
6. **Giữ semantics PATCH:** missing thường có nghĩa không cập nhật; null có thể có nghĩa xóa.
7. **Không nhầm empty với missing:** "", [], {}, 0 và false đều là những giá trị có mặt.
8. **Kiểm thử hợp đồng:** test riêng missing, explicit null, value, empty và sai kiểu.
9. **Chuyển sang DTO khi schema ổn định:** Tree Model phù hợp cho dữ liệu động, DTO phù hợp cho nghiệp vụ có cấu trúc.

MissingNode và NullNode là hai công cụ giúp Jackson Tree Model thể hiện chính xác sự khác biệt giữa vị trí không tồn tại và giá trị JSON null. Khi xử lý dữ liệu động, hãy giữ nguyên sự khác biệt này cho đến khi tầng nghiệp vụ quyết định cách hiểu. Nhờ vậy, API có thể thực hiện đúng semantics của field bắt buộc, field tùy chọn và PATCH mà không vô tình biến dữ liệu thiếu thành null hoặc ngược lại.

