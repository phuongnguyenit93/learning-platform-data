# Phân biệt cập nhật đối tượng và giao thức JSON Patch hoặc Merge Patch

Khi API nhận một payload chỉ chứa một phần dữ liệu, ứng dụng cần quyết định cách áp dụng phần dữ liệu đó lên trạng thái hiện có. Jackson có thể đọc JSON vào một object đã tồn tại, nhưng thao tác này chỉ là cơ chế data binding. Nó không tự định nghĩa một giao thức cập nhật chuẩn, không mô tả đầy đủ thao tác thêm/xóa/thay thế và không tự giải quyết mọi quy tắc về null, mảng hoặc tính nguyên tử.

JSON Patch và JSON Merge Patch là hai định dạng patch được chuẩn hóa bằng RFC. Chúng mô tả rõ cách thay đổi một JSON document. Jackson có thể làm việc với chúng thông qua `JsonNode` và thư viện hỗ trợ, sau đó ánh xạ kết quả về DTO.

Cần phân biệt ba lớp:

- **Cập nhật object bằng Jackson:** áp dụng các property JSON lên một Java object hiện có.
- **JSON Patch (RFC 6902):** mô tả một chuỗi thao tác cụ thể như add, remove, replace, move, copy và test.
- **JSON Merge Patch (RFC 7396):** mô tả một phần object cần hợp nhất; null có nghĩa xóa property và array được thay thế toàn bộ.

## 1. Cập nhật object hiện có bằng Jackson

Jackson Databind có thể đọc JSON vào một instance đã tồn tại bằng `ObjectReader.readerForUpdating(...)`.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

User user = new User();
user.setName("An");
user.setEmail("an@example.com");
user.setActive(true);

String updateJson = """
    {
      "name": "Bình"
    }
    """;

mapper.readerForUpdating(user).readValue(updateJson);
~~~

Sau khi cập nhật, object giữ trạng thái:

~~~text
name   = "Bình"
email  = "an@example.com"
active = true
~~~

Property không xuất hiện trong JSON thường không được gán lại, nên giá trị hiện có vẫn còn. Property có mặt sẽ được Jackson xử lý theo deserializer, setter/field và các cấu hình liên quan.

Đây là cách thuận tiện cho một số trường hợp cập nhật DTO hoặc bean. Tuy nhiên, nó không phải JSON Patch hay Merge Patch. Payload chỉ là JSON object thông thường; nó không thể biểu diễn tường minh thao tác move, copy, test hoặc xóa một property theo chuẩn patch.

### 1.1. ObjectReader và updateValue

Có hai API thường gặp:

~~~java
mapper.readerForUpdating(existing).readValue(json);
~~~

và:

~~~java
mapper.updateValue(existing, overrides);
~~~

`readerForUpdating` đọc JSON text vào instance đích. `updateValue` áp dụng dữ liệu từ một object khác lên instance đích thông qua cơ chế databind. Cả hai đều dựa vào quy tắc cập nhật của Jackson và kiểu dữ liệu cụ thể.

Ví dụ `updateValue` với Map:

~~~java
Map<String, Object> changes = Map.of("name", "Bình");

User updated = mapper.updateValue(user, changes);
~~~

Các API này không cung cấp ngữ nghĩa patch độc lập với model. Hành vi cập nhật nested POJO, Map và Collection còn phụ thuộc cấu hình merge của property.

### 1.2. Jackson update không phải giao thức HTTP PATCH

HTTP PATCH chỉ định phương thức HTTP dùng để áp dụng một tập thay đổi lên resource. Bản thân HTTP không bắt buộc body phải là JSON Patch hay JSON Merge Patch; media type và hợp đồng API xác định định dạng patch.

Ví dụ:

~~~http
PATCH /users/42
Content-Type: application/merge-patch+json
~~~

Body có thể là Merge Patch. Nếu dùng JSON Patch, Content-Type thường là:

~~~http
Content-Type: application/json-patch+json
~~~

Một API cũng có thể nhận một DTO update riêng dưới dạng JSON thông thường. Khi đó, đó là hợp đồng update do ứng dụng định nghĩa, không tự động trở thành RFC 6902 hoặc RFC 7396.

## 2. @JsonMerge điều khiển việc hợp nhất property

Mặc định, khi cập nhật object, một property lồng nhau có thể được thay thế theo cách deserialize thông thường. Annotation `@JsonMerge` cho phép yêu cầu Jackson hợp nhất nội dung mới vào giá trị hiện có đối với property được đánh dấu.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonMerge;

public class User {
    private String name;

    @JsonMerge
    private Address address;

    // Getter/setter
}
~~~

Giả sử object hiện tại có:

~~~json
{
  "name": "An",
  "address": {
    "city": "Hanoi",
    "street": "Le Loi"
  }
}
~~~

Payload update:

~~~json
{
  "address": {
    "city": "Da Nang"
  }
}
~~~

Khi property `address` được cấu hình merge, Jackson có thể cập nhật city trong Address hiện có và giữ street. Nếu không có merge behavior phù hợp, property nested có thể được tạo/thay thế theo deserializer thay vì cập nhật sâu như mong đợi.

`@JsonMerge` là quy tắc data binding ở cấp property. Nó không biến JSON body thành một giao thức patch chuẩn và không bổ sung các thao tác như move/copy/test.

### 2.1. Merge Map và Collection không giống merge object

Với Map, merge thường cập nhật hoặc thêm các entry theo key; entry cũ không xuất hiện trong payload vẫn được giữ.

Với Collection như List, merge behavior thường nối thêm các phần tử đầu vào vào collection hiện tại. Nó không hiểu rằng phần tử thứ hai trong JSON là lệnh thay thế phần tử index 1. Cách xử lý cụ thể còn phụ thuộc loại collection và deserializer.

Ví dụ minh họa:

~~~java
public class Preferences {
    @JsonMerge
    private Map<String, String> labels;

    @JsonMerge
    private List<String> tags;

    // Getter/setter
}
~~~

Nếu cần thay toàn bộ List, dùng semantics thay thế phù hợp hoặc gán collection mới. Nếu cần thay đổi chính xác một phần tử theo index, JSON Patch có thao tác `replace` với path đến index đó.

## 3. Ba khái niệm null, thiếu property và xóa property

Đây là khác biệt quan trọng nhất giữa cập nhật object thông thường và Merge Patch.

Giả sử object có property `nickname`.

| Payload | Cập nhật object thông thường | JSON Merge Patch |
|---|---|---|
| Không có key `nickname` | Thường giữ giá trị hiện tại | Giữ giá trị hiện tại |
| `"nickname": null` | Thường gán null, tùy null policy | Xóa property `nickname` |
| `"nickname": "An"` | Gán chuỗi "An" | Gán chuỗi "An" |

Trong Jackson, null đầu vào có thể được điều khiển bằng `@JsonSetter(nulls = ...)` hoặc cấu hình null handling. Ví dụ:

~~~java
@JsonSetter(nulls = Nulls.SKIP)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
~~~

Với `Nulls.SKIP`, Jackson bỏ qua thao tác gán khi property xuất hiện với giá trị null. Đây là lựa chọn cho update bean nếu muốn null có nghĩa "không thay đổi". Nó vẫn không tương đương với Merge Patch, nơi null trong object patch có nghĩa xóa member.

Một Java field kiểu String chỉ có thể lưu null hoặc một chuỗi; nó không tự ghi nhớ property đã bị bỏ qua hay đã được gửi với null. Nếu cần phân biệt ba trạng thái trong một DTO update tùy biến, cần một wrapper/presence model hoặc xử lý JSON tree trước khi bind.

## 4. JSON Patch (RFC 6902) là gì?

JSON Patch biểu diễn thay đổi dưới dạng một JSON array gồm các operation có thứ tự. Mỗi operation chỉ rõ thao tác và vị trí trong JSON document.

Media type chuẩn:

~~~text
application/json-patch+json
~~~

Ví dụ resource ban đầu:

~~~json
{
  "name": "An",
  "tags": ["java", "jackson"],
  "active": true
}
~~~

Patch:

~~~json
[
  { "op": "replace", "path": "/name", "value": "Bình" },
  { "op": "add", "path": "/tags/-", "value": "json" },
  { "op": "remove", "path": "/active" }
]
~~~

Kết quả:

~~~json
{
  "name": "Bình",
  "tags": ["java", "jackson", "json"]
}
~~~

Mỗi operation được áp dụng tuần tự lên kết quả của operation trước đó. `path` sử dụng JSON Pointer để xác định vị trí trong document.

### 4.1. Sáu operation của JSON Patch

| Operation | Tác dụng | Field thường dùng |
|---|---|---|
| `add` | Thêm member hoặc chèn phần tử array | `op`, `path`, `value` |
| `remove` | Xóa member hoặc phần tử array | `op`, `path` |
| `replace` | Thay giá trị tại path đã tồn tại | `op`, `path`, `value` |
| `move` | Di chuyển giá trị từ path nguồn sang path đích | `op`, `from`, `path` |
| `copy` | Sao chép giá trị từ path nguồn sang path đích | `op`, `from`, `path` |
| `test` | Kiểm tra giá trị tại path có bằng giá trị kỳ vọng không | `op`, `path`, `value` |

### 4.2. add

Thêm property vào object:

~~~json
[
  {
    "op": "add",
    "path": "/email",
    "value": "an@example.com"
  }
]
~~~

Với object, nếu member đã tồn tại, `add` thay giá trị member đó. Với array, `add` chèn phần tử tại index chỉ định và dịch các phần tử sau sang phải. Dùng `-` ở cuối path để thêm vào cuối array.

### 4.3. remove

Xóa một member:

~~~json
[
  {
    "op": "remove",
    "path": "/email"
  }
]
~~~

Path phải trỏ đến một giá trị tồn tại. Với array, xóa phần tử tại index và dịch các phần tử sau sang trái.

### 4.4. replace

Thay giá trị đã tồn tại:

~~~json
[
  {
    "op": "replace",
    "path": "/profile/city",
    "value": "Da Nang"
  }
]
~~~

Khác với add, replace yêu cầu path đích đã tồn tại. Điều này giúp phát hiện trường hợp client định sửa một property nhưng resource không có property đó.

### 4.5. move

Di chuyển giá trị từ vị trí nguồn sang vị trí đích:

~~~json
[
  {
    "op": "move",
    "from": "/profile/oldName",
    "path": "/profile/name"
  }
]
~~~

Về ý nghĩa, move tương đương xóa tại `from` rồi thêm vào `path`. Path nguồn phải tồn tại. Theo RFC, không được di chuyển một giá trị vào bên trong chính descendant của nó.

### 4.6. copy

Sao chép giá trị từ vị trí nguồn:

~~~json
[
  {
    "op": "copy",
    "from": "/profile/name",
    "path": "/displayName"
  }
]
~~~

Giá trị tại `from` được sao chép sang `path`; nguồn vẫn còn nguyên.

### 4.7. test

Kiểm tra điều kiện trước khi tiếp tục:

~~~json
[
  {
    "op": "test",
    "path": "/status",
    "value": "DRAFT"
  },
  {
    "op": "replace",
    "path": "/status",
    "value": "SUBMITTED"
  }
]
~~~

Nếu test thất bại, patch không được xem là áp dụng thành công. Operation test hữu ích để kiểm tra một trạng thái kỳ vọng, nhưng không thay thế cơ chế kiểm soát concurrency ở tầng HTTP/database.

## 5. JSON Pointer và path trong JSON Patch

Path trong JSON Patch tuân theo JSON Pointer (RFC 6901). Nó bắt đầu bằng dấu `/` cho mỗi segment.

Ví dụ:

| Path | Ý nghĩa |
|---|---|
| `/name` | Property name ở root |
| `/profile/city` | Property city bên trong profile |
| `/items/0` | Phần tử đầu tiên của array items |
| `/items/-` | Vị trí cuối array khi dùng add |
| `/a~1b` | Property có tên `a/b` |
| `/m~0n` | Property có tên `m~n` |

Trong một segment, ký tự `~` phải được escape thành `~0`, còn `/` phải được escape thành `~1`. Khi tạo path từ tên property động, không tự nối chuỗi mà bỏ qua quy tắc escape.

Path cũng cần được kiểm tra theo quyền nghiệp vụ. Ví dụ, client có thể được phép cập nhật `/profile/displayName` nhưng không được sửa `/role`, `/ownerId` hoặc `/billing/status`.

## 6. JSON Merge Patch (RFC 7396) là gì?

JSON Merge Patch biểu diễn phần dữ liệu muốn hợp nhất vào resource. Nó thường có hình dạng gần giống object đích, thay vì một array operation.

Media type chuẩn:

~~~text
application/merge-patch+json
~~~

Resource ban đầu:

~~~json
{
  "name": "An",
  "email": "an@example.com",
  "profile": {
    "city": "Hanoi",
    "language": "vi"
  },
  "tags": ["java", "jackson"]
}
~~~

Merge Patch:

~~~json
{
  "name": "Bình",
  "email": null,
  "profile": {
    "city": "Da Nang"
  },
  "tags": ["json"]
}
~~~

Kết quả:

~~~json
{
  "name": "Bình",
  "profile": {
    "city": "Da Nang",
    "language": "vi"
  },
  "tags": ["json"]
}
~~~

Quy tắc:

- Property không có trong patch được giữ nguyên.
- Property có giá trị khác null được thêm mới hoặc thay thế.
- Property có giá trị null bị xóa khỏi object đích.
- Nếu patch member là object, merge đệ quy vào object đích.
- Array được thay thế toàn bộ, không merge từng index.
- Nếu patch ở root là scalar, array hoặc null, toàn bộ target được thay bằng giá trị đó.

### 6.1. Null trong Merge Patch có nghĩa xóa

Đây là điểm dễ nhầm: trong object Merge Patch, null được dành cho thao tác xóa member.

Ví dụ:

~~~json
{
  "middleName": null
}
~~~

có nghĩa xóa member `middleName`, không phải đặt giá trị member thành JSON null.

Nếu nghiệp vụ cần phân biệt "xóa field" với "đặt field thành null", Merge Patch không biểu diễn được cả hai ý nghĩa trong cùng một object patch theo cách trực tiếp. Có thể dùng JSON Patch `replace` với value null để đặt null, và `remove` để xóa; hoặc thiết kế một DTO update có presence/operation rõ ràng.

### 6.2. Array trong Merge Patch bị thay thế toàn bộ

Giả sử resource có:

~~~json
{
  "tags": ["java", "jackson", "spring"]
}
~~~

Patch:

~~~json
{
  "tags": ["json"]
}
~~~

Kết quả:

~~~json
{
  "tags": ["json"]
}
~~~

Merge Patch không nối thêm `json` và không thay riêng phần tử index 0. Toàn bộ array được thay thế.

Nếu cần sửa chính xác một phần tử array, thêm/xóa theo index hoặc kiểm tra giá trị trước khi sửa, JSON Patch phù hợp hơn.

## 7. Bảng so sánh ba cách cập nhật

| Tiêu chí | Jackson update object | JSON Patch | JSON Merge Patch |
|---|---|---|---|
| Định dạng đầu vào | JSON object thông thường hoặc Java overrides | Array operation | Object patch hoặc giá trị JSON bất kỳ |
| Chuẩn hóa giao thức | Theo model và cấu hình Jackson | RFC 6902 | RFC 7396 |
| Chỉ rõ vị trí thay đổi | Qua property của DTO | JSON Pointer path | Cấu trúc object lồng nhau |
| Xóa property | Cần quy tắc riêng/logic ứng dụng | Operation remove | Member có giá trị null |
| Đặt property thành JSON null | Có thể qua null handling | replace/add với value null | Không thể biểu diễn trực tiếp trong object patch vì null nghĩa xóa |
| Thao tác array | Theo deserializer/merge config | add/remove/replace/move/copy theo index | Thay toàn bộ array |
| Kiểm tra điều kiện | Tự viết validation | Có operation test | Không có operation test |
| Di chuyển/sao chép member | Tự viết logic | Có move/copy | Không có |
| Phù hợp | DTO update đơn giản | Thay đổi chính xác, nhiều thao tác | Cập nhật object từng phần đơn giản |

Không có một định dạng phù hợp cho mọi API. Hãy chọn dựa trên ngữ nghĩa mà client cần biểu đạt.

## 8. Áp dụng JSON Patch với Jackson JsonNode

Jackson Core/Databind cung cấp `JsonParser`, `JsonGenerator` và `JsonNode`, nhưng API databind thông thường không tự biến một JSON array thành giao thức RFC 6902. Có thể dùng thư viện JSON Patch tương thích Jackson hoặc một implementation chuẩn khác.

Ví dụ với thư viện `json-patch` thuộc hệ sinh thái java-json-tools, API thường có dạng:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.fge.jsonpatch.JsonPatch;

ObjectMapper mapper = new ObjectMapper();

JsonNode target = mapper.readTree("""
    {
      "name": "An",
      "active": true
    }
    """);

JsonNode patchDocument = mapper.readTree("""
    [
      { "op": "replace", "path": "/name", "value": "Bình" },
      { "op": "remove", "path": "/active" }
    ]
    """);

JsonPatch patch = JsonPatch.fromJson(patchDocument);

// Làm việc trên bản sao để chỉ commit sau khi patch áp dụng thành công.
JsonNode candidate = target.deepCopy();
JsonNode patched = patch.apply(candidate);
~~~

Tên package và API có thể khác giữa các implementation/version. Cần chọn thư viện hỗ trợ RFC 6902, kiểm tra khả năng tương thích với Jackson đang dùng và xác nhận các operation được hỗ trợ đúng theo hợp đồng.

Sau khi patch tree thành công, có thể bind về DTO:

~~~java
User updated = mapper.treeToValue(patched, User.class);
~~~

Với DTO bất biến, bước này tạo instance mới thông qua creator. Với entity đang được quản lý bởi ORM, nên xác thực kết quả và cập nhật entity theo transaction của ứng dụng thay vì để client sửa trực tiếp mọi field của entity.

### 8.1. Không sửa trạng thái đang lưu trước khi patch hợp lệ

Một patch có nhiều operation có thể thành công ở operation đầu rồi thất bại ở operation sau. Vì vậy, nên áp dụng patch lên một bản sao của JSON tree, kiểm tra kết quả, bind/validate và chỉ sau đó mới ghi trạng thái vào database.

~~~text
JSON hiện tại
     |
     v
Tạo bản sao candidate
     |
     v
Áp dụng tuần tự các operation
     |
     +---- lỗi ----> Bỏ candidate, giữ nguyên resource
     |
     v
Bind thành DTO/domain model
     |
     v
Validate nghiệp vụ và quyền
     |
     +---- lỗi ----> Không commit
     |
     v
Lưu trong transaction
~~~

Cách này tránh để resource đang lưu bị cập nhật một phần khi patch thất bại giữa chừng.

## 9. Áp dụng JSON Merge Patch bằng JsonNode

Có thể dùng implementation RFC 7396 đã được kiểm chứng. Nếu tự triển khai, phải tuân thủ đúng quy tắc đệ quy, null và array của RFC.

Một hàm minh họa cho merge semantics:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.Iterator;
import java.util.Map;

public static JsonNode applyMergePatch(
        JsonNode target,
        JsonNode patch) {

    // Patch không phải object: thay toàn bộ target.
    if (!patch.isObject()) {
        return patch.deepCopy();
    }

    // Khi patch là object nhưng target không phải object,
    // bắt đầu từ object rỗng.
    ObjectNode result = target != null && target.isObject()
        ? ((ObjectNode) target).deepCopy()
        : JsonNodeFactory.instance.objectNode();

    Iterator<Map.Entry<String, JsonNode>> fields = patch.fields();

    while (fields.hasNext()) {
        Map.Entry<String, JsonNode> field = fields.next();
        String name = field.getKey();
        JsonNode patchValue = field.getValue();

        if (patchValue.isNull()) {
            result.remove(name);
        } else {
            JsonNode currentValue = result.get(name);
            result.set(
                name,
                applyMergePatch(currentValue, patchValue)
            );
        }
    }

    return result;
}
~~~

Ví dụ sử dụng:

~~~java
JsonNode target = mapper.readTree("""
    {
      "name": "An",
      "profile": {
        "city": "Hanoi",
        "language": "vi"
      }
    }
    """);

JsonNode patch = mapper.readTree("""
    {
      "name": "Bình",
      "profile": {
        "city": "Da Nang"
      }
    }
    """);

JsonNode result = applyMergePatch(target, patch);
~~~

Kết quả giữ lại `profile.language` vì patch không đề cập đến nó.

Đây là mã minh họa semantics cốt lõi, không phải thư viện production hoàn chỉnh. Trong ứng dụng thật, cần kiểm thử toàn bộ trường hợp RFC, giới hạn kích thước/depth, xử lý lỗi, media type và transaction. Nếu có thể, ưu tiên implementation RFC 7396 đã được duy trì và kiểm thử.

## 10. Chuyển kết quả patch về DTO và validate

Patch nên được áp dụng lên JSON representation của resource, sau đó mới chuyển về kiểu Java mà ứng dụng sử dụng.

Ví dụ:

~~~java
JsonNode currentTree = mapper.valueToTree(existingUser);
JsonNode candidateTree = applyMergePatch(currentTree, mergePatchTree);

User candidate = mapper.treeToValue(candidateTree, User.class);

validate(candidate);
repository.save(candidate);
~~~

Luồng này phù hợp khi DTO có thể được tạo lại từ JSON tree. Với entity có quan hệ ORM, proxy, lazy field hoặc logic domain phức tạp, không nên serialize toàn bộ entity rồi deserialize lại như một cách cập nhật mặc định. Thay vào đó, map các thay đổi được phép vào aggregate/domain object bằng logic nghiệp vụ.

Các bước nên tách riêng:

1. Xác định resource hiện tại và quyền truy cập.
2. Chuyển resource sang representation phù hợp.
3. Áp dụng patch trên candidate.
4. Kiểm tra path/field được phép sửa.
5. Bind hoặc map candidate về kiểu đích.
6. Chạy validation nghiệp vụ.
7. Lưu trong transaction nếu mọi bước hợp lệ.

## 11. Kiểm soát quyền và path được phép sửa

JSON Patch cho client chỉ định path trực tiếp. Điều này mạnh nhưng có thể tạo lỗ hổng nếu API cho phép sửa mọi path.

Ví dụ, client có thể thử:

~~~json
[
  {
    "op": "replace",
    "path": "/role",
    "value": "ADMIN"
  }
]
~~~

Nếu `role` là field chỉ quản trị viên được thay đổi, không được áp dụng patch chỉ vì cú pháp hợp lệ.

Cần xác định allowlist path theo user/role và nghiệp vụ. Đặc biệt kiểm tra:

- ID, owner ID và tenant ID.
- Role, permission và trạng thái phê duyệt.
- Trường audit như createdAt/createdBy.
- Trường tính toán từ server.
- Quan hệ object mà client không được phép gán tùy ý.

Với `move` và `copy`, phải kiểm tra cả `from` lẫn `path`. Với `test`, cân nhắc tránh tiết lộ giá trị nhạy cảm qua kết quả thành công/thất bại.

JSON Merge Patch không có path operation riêng, nhưng vẫn cần allowlist field và kiểm tra sâu object. Không cho phép client ghi đè field nhạy cảm chỉ vì field đó có mặt trong JSON.

## 12. Concurrency và điều kiện cập nhật

Một patch có thể được tạo dựa trên trạng thái resource mà client đã đọc trước đó. Nếu một client khác cập nhật resource trong lúc đó, patch cũ có thể ghi đè hoặc làm mất thay đổi mới.

HTTP API thường dùng ETag và điều kiện `If-Match`:

~~~http
GET /users/42
~~~

Response:

~~~http
ETag: "v17"
~~~

Khi gửi patch:

~~~http
PATCH /users/42
If-Match: "v17"
Content-Type: application/json-patch+json
~~~

Server chỉ áp dụng nếu resource vẫn ở version tương ứng. Nếu đã thay đổi, trả lỗi precondition phù hợp, thường là `412 Precondition Failed`.

JSON Patch operation `test` có thể kiểm tra một giá trị cụ thể, nhưng không thay thế kiểm soát phiên bản toàn resource. ETag/version column giúp phát hiện cập nhật cạnh tranh ở phạm vi resource hoặc transaction.

## 13. Chọn JSON Patch hay Merge Patch?

Dùng **JSON Patch** khi:

- Cần thêm, xóa, thay thế chính xác từng property.
- Cần sửa phần tử array theo index.
- Cần move/copy dữ liệu giữa các path.
- Cần test điều kiện trước khi thay đổi.
- Client cần mô tả nhiều thao tác tuần tự trong một request.

Dùng **JSON Merge Patch** khi:

- Payload update có hình dạng gần giống object resource.
- Chỉ cần thay một số property và giữ các property không gửi.
- Xóa field bằng cách gửi null là phù hợp.
- Array được thay thế toàn bộ mỗi khi gửi.
- Không cần operation move, copy hoặc test.

Dùng **Jackson object update** khi:

- API có DTO update đơn giản do ứng dụng tự định nghĩa.
- Không cần một patch format interoperable theo RFC.
- Có thể kiểm soát rõ absent/null và merge behavior bằng DTO, setter và `@JsonMerge`.
- Logic cập nhật được xử lý ở tầng service/domain.

## 14. Các lỗi thường gặp

**Cho rằng readerForUpdating là JSON Patch.** Nó chỉ cập nhật object theo quy tắc databind. Nó không hiểu operation array hoặc JSON Pointer.

**Cho rằng null luôn có nghĩa xóa.** Với Jackson object update, null thường được gán theo null policy. Chỉ Merge Patch quy định null member trong object patch có nghĩa xóa.

**Cho rằng @JsonMerge tự tạo semantics RFC.** Annotation điều khiển merge property của Jackson; nó không cung cấp operation add/remove/test hay media type patch.

**Cho rằng Merge Patch cập nhật từng phần tử array.** RFC 7396 thay thế toàn bộ array.

**Dùng JSON Patch mà không kiểm soát path.** Một patch hợp lệ về cú pháp vẫn có thể sửa field mà client không được phép.

**Áp dụng patch trực tiếp lên entity đang lưu.** Nếu operation giữa chừng lỗi hoặc validation thất bại, có thể để lại trạng thái dở dang. Áp dụng lên candidate rồi commit trong transaction.

**Không phân biệt absent và null trong DTO update.** Java field null không tự cho biết client bỏ field hay gửi null; cần presence model nếu nghiệp vụ cần phân biệt.

**Không kiểm soát concurrency.** Patch được tạo trên bản cũ có thể ghi đè thay đổi mới. Dùng ETag/If-Match hoặc version kiểm soát optimistic locking.

## 15. Ghi nhớ

- Jackson `readerForUpdating` và `updateValue` là cơ chế cập nhật object theo databind, không phải giao thức patch chuẩn.
- `@JsonMerge` điều khiển cách hợp nhất property lồng nhau; hành vi Map, Collection và POJO không giống nhau.
- JSON Patch (RFC 6902) là array operation gồm add, remove, replace, move, copy và test; path dùng JSON Pointer.
- JSON Merge Patch (RFC 7396) là một phần JSON được hợp nhất đệ quy; null trong object patch xóa member và array được thay thế toàn bộ.
- Merge Patch không biểu diễn trực tiếp việc đặt một object member thành JSON null; JSON Patch có thể dùng add/replace với value null.
- Jackson tree model có thể làm representation trung gian; dùng implementation RFC phù hợp hoặc tự triển khai Merge Patch với test đầy đủ.
- Áp dụng patch trên candidate, kiểm tra path, bind, validate rồi mới commit.
- Kiểm soát quyền sửa field và concurrency bằng allowlist, ETag/If-Match hoặc optimistic locking.

