# Xử lý mảng một phần tử và giá trị đơn theo chính sách

Trong JSON, một giá trị đơn và một mảng chứa đúng một phần tử là hai cấu trúc khác nhau:

```json
"urgent"
```

```json
["urgent"]
```

Tương tự, object đơn và mảng chứa một object cũng khác nhau:

```json
{"id": 10, "name": "An"}
```

```json
[{"id": 10, "name": "An"}]
```

Một số API hoặc nguồn dữ liệu không nhất quán: lúc gửi giá trị đơn, lúc gửi mảng một phần tử. Jackson có các chính sách để chấp nhận hoặc tạo ra những dạng này. Cần chọn chính sách theo hợp đồng dữ liệu, xác định phạm vi áp dụng và hiểu rõ tác động khi mảng rỗng hoặc có nhiều phần tử.

Các ví dụ trong bài sử dụng Jackson 2.x với package `com.fasterxml.jackson`. Những feature được trình bày là cấu hình Databind phổ biến; nếu dự án dùng version khác, hãy kiểm tra Javadoc đúng version trước khi áp dụng.

## 1. Phân biệt bốn cấu trúc đầu vào

Trước khi cấu hình mapper, cần xác định JSON nào thực sự được gửi:

| JSON | Cấu trúc | Ví dụ target Java |
|---|---|---|
| `"urgent"` | Giá trị chuỗi đơn | `String` |
| `["urgent"]` | Mảng có một phần tử | `List<String>` hoặc `String[]` |
| `[]` | Mảng rỗng | Collection rỗng |
| `null` | Giá trị JSON null | Tham chiếu Java null, nếu được phép |

Một mảng có một phần tử không phải là một scalar. Số lượng phần tử bằng một không làm thay đổi kiểu JSON của nó. Tương tự, `[]` không phải `null`, và chuỗi rỗng `""` không phải mảng rỗng.

Mặc định, Jackson giữ ranh giới kiểu này:

- Collection/array Java được đọc từ JSON array.
- Property scalar được đọc từ JSON scalar.
- JSON array không tự động trở thành một object scalar chỉ vì mảng chỉ có một phần tử.
- JSON scalar không tự động trở thành collection một phần tử.

Nếu API quy định một shape cố định, hãy giữ đúng shape đó. Các feature linh hoạt chỉ nên bật khi hệ thống cần tương thích với nguồn dữ liệu thực tế.

## 2. Nhận giá trị đơn thành collection một phần tử

Trường hợp thường gặp là API khai báo một danh sách nhưng đôi khi gửi một giá trị đơn khi danh sách chỉ có một phần tử.

Ví dụ DTO:

```java
public class SearchRequest {
    private List<String> tags;

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

JSON theo hợp đồng thông thường:

```json
{
  "tags": ["urgent"]
}
```

Nhưng một client có thể gửi:

```json
{
  "tags": "urgent"
}
```

Nếu không cấu hình, Jackson thường báo lỗi vì đang cố gắng ánh xạ một chuỗi thành `List<String>`. Có thể cho phép scalar trở thành collection một phần tử bằng `ACCEPT_SINGLE_VALUE_AS_ARRAY`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);

SearchRequest request = mapper.readValue(json, SearchRequest.class);
System.out.println(request.getTags()); // [urgent]
```

Feature này áp dụng cho quá trình deserialize collection hoặc array: khi gặp một giá trị đơn ở vị trí cần collection, Jackson xử lý nó như collection có đúng một phần tử.

### 2.1. Áp dụng chỉ cho một property bằng `@JsonFormat`

Nếu chỉ một vài field cần tương thích với scalar input, không nhất thiết bật feature cho toàn mapper. Có thể dùng `@JsonFormat` ngay trên property:

```java
import com.fasterxml.jackson.annotation.JsonFormat;

public class SearchRequest {
    @JsonFormat(with = JsonFormat.Feature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    private List<String> tags;

    private List<String> categories;

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getCategories() {
        return categories;
    }

    public void setCategories(List<String> categories) {
        this.categories = categories;
    }
}
```

Trong ví dụ này, `tags` chấp nhận cả chuỗi đơn và mảng; `categories` vẫn tuân theo cấu trúc collection thông thường. Đây là cách phù hợp khi một đối tác cụ thể gửi dữ liệu không nhất quán nhưng những field khác phải giữ hợp đồng chặt chẽ.

### 2.2. Collection có kiểu phần tử vẫn phải được khai báo đầy đủ

`ACCEPT_SINGLE_VALUE_AS_ARRAY` giải quyết sự khác nhau giữa scalar và collection. Nó không thay thế thông tin generic của phần tử.

Khi đọc trực tiếp một list:

```java
import com.fasterxml.jackson.core.type.TypeReference;

List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
);
```

Nếu JSON là một object đơn thay vì array, `ACCEPT_SINGLE_VALUE_AS_ARRAY` có thể cho phép object đó trở thành list một phần tử, với phần tử được deserialize thành `User`. Nếu truyền `List.class`, Jackson không có đủ thông tin để biết phần tử cần là `User`.

## 3. Nhận mảng một phần tử thành giá trị scalar

Chiều ngược lại cũng có thể xảy ra: API trả về một field scalar, nhưng một nguồn dữ liệu lại bọc giá trị trong array có đúng một phần tử.

Ví dụ target Java:

```java
public class UserResponse {
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

JSON theo hợp đồng:

```json
{
  "displayName": "An"
}
```

Nguồn dữ liệu không nhất quán có thể gửi:

```json
{
  "displayName": ["An"]
}
```

Để cho phép một array có đúng một phần tử được đọc thành scalar, Jackson có `UNWRAP_SINGLE_VALUE_ARRAYS`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS);

UserResponse response = mapper.readValue(json, UserResponse.class);
System.out.println(response.getDisplayName()); // An
```

Feature này khác với `ACCEPT_SINGLE_VALUE_AS_ARRAY`:

| Feature | JSON đầu vào | Kiểu Java đích | Kết quả |
|---|---|---|---|
| `ACCEPT_SINGLE_VALUE_AS_ARRAY` | `"An"` | `List<String>` | List chứa `"An"` |
| `UNWRAP_SINGLE_VALUE_ARRAYS` | `["An"]` | `String` | Scalar `"An"` |

Tên feature mô tả hai hướng khác nhau. Không bật một feature rồi kỳ vọng nó xử lý cả hai dạng.

### 3.1. Mảng có nhiều hơn một phần tử không được tự chọn phần tử đầu

`UNWRAP_SINGLE_VALUE_ARRAYS` chỉ dành cho array có đúng một giá trị. Ví dụ sau không phải input hợp lệ cho scalar target:

```json
{
  "displayName": ["An", "Binh"]
}
```

Jackson báo lỗi mapping thay vì âm thầm lấy phần tử đầu hoặc cuối. Đây là hành vi quan trọng: tự bỏ phần tử có thể làm mất dữ liệu và che giấu lỗi hợp đồng.

Mảng rỗng cũng không phải mảng một phần tử. Không nên giả định `[]` sẽ tự biến thành `null` hoặc giá trị mặc định khi bật `UNWRAP_SINGLE_VALUE_ARRAYS`.

## 4. Ghi collection một phần tử thành scalar

Khi serialize, Jackson mặc định giữ kiểu collection. Một list có một phần tử vẫn được ghi thành JSON array:

```java
List<String> tags = List.of("urgent");
String json = mapper.writeValueAsString(tags);
// ["urgent"]
```

Nếu hợp đồng của một hệ thống cũ yêu cầu ghi collection có đúng một phần tử thành scalar, có thể bật `WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED`:

```java
import com.fasterxml.jackson.databind.SerializationFeature;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(SerializationFeature.WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED);

String one = mapper.writeValueAsString(List.of("urgent"));
// "urgent"

String two = mapper.writeValueAsString(List.of("urgent", "review"));
// ["urgent","review"]

String empty = mapper.writeValueAsString(List.of());
// []
```

Feature này chỉ unwrap khi collection/array có đúng một phần tử. Collection rỗng vẫn là array rỗng; collection có từ hai phần tử trở lên vẫn là array.

### 4.1. Áp dụng theo property

Có thể cấu hình output riêng cho một property bằng `@JsonFormat`:

```java
import com.fasterxml.jackson.annotation.JsonFormat;

public class LegacyResponse {
    @JsonFormat(with = JsonFormat.Feature.WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED)
    private List<String> warnings;

    private List<String> permissions;

    // getters và setters
}
```

`warnings` có thể được ghi thành scalar khi có đúng một phần tử; `permissions` tiếp tục được ghi thành array. Cách cấu hình cục bộ giúp hạn chế ảnh hưởng đến những payload không liên quan.

## 5. Đừng nhầm ba chính sách với nhau

Jackson có ba feature quan trọng cho tình huống này:

| Feature | Chiều xử lý | Khi nào tác động |
|---|---|---|
| `DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY` | Đọc | Scalar JSON vào collection/array Java |
| `DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS` | Đọc | JSON array đúng một phần tử vào scalar Java |
| `SerializationFeature.WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED` | Ghi | Collection/array Java đúng một phần tử thành scalar JSON |

Ví dụ luồng dữ liệu:

```text
JSON scalar "urgent"
        |
        | ACCEPT_SINGLE_VALUE_AS_ARRAY
        v
Java List<String> ["urgent"]

JSON array ["urgent"]
        |
        | UNWRAP_SINGLE_VALUE_ARRAYS
        v
Java String "urgent"

Java List<String> ["urgent"]
        |
        | WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED
        v
JSON scalar "urgent"
```

Ba chính sách có thể dùng riêng hoặc phối hợp tùy hợp đồng. Không nên bật tất cả theo thói quen vì việc chấp nhận nhiều hình dạng hơn có thể làm ứng dụng khó phát hiện client gửi sai schema.

## 6. Mảng rỗng, `null` và chuỗi rỗng là các trường hợp riêng

Các feature single-value không nên được dùng để suy luận cách xử lý empty input. Hãy quyết định rõ chính sách cho từng trường hợp:

| JSON | Ý nghĩa | Collection target thường nhận |
|---|---|---|
| `[]` | Không có phần tử | Collection rỗng |
| `["urgent"]` | Một phần tử | Collection có một phần tử |
| `"urgent"` | Một giá trị scalar | Lỗi mặc định; thành list một phần tử nếu bật `ACCEPT_SINGLE_VALUE_AS_ARRAY` |
| `null` | Giá trị null | `null` nếu cho phép; nếu không thì validation/configuration xử lý |
| `""` | Chuỗi rỗng | Một chuỗi rỗng nếu target là String; không đồng nghĩa với list rỗng |

Jackson còn có `ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT` trong `DeserializationFeature`. Feature này có thể cho phép một JSON array rỗng được xem như `null` khi target là một POJO/object phù hợp. Nó không phải cách tổng quát để biến mọi collection rỗng thành null và không thay thế `UNWRAP_SINGLE_VALUE_ARRAYS`.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT);

User user = mapper.readValue("[]", User.class);
```

Nếu bật chính sách này, một mảng rỗng ở vị trí object target có thể được đọc thành null. Chỉ bật khi hợp đồng cũ yêu cầu chính xác hành vi đó. Với field collection, thông thường `[]` nên tiếp tục có nghĩa collection rỗng.

Tương tự, `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` liên quan đến chuỗi rỗng và một số object target; nó không phải chính sách array. Không gộp các trường hợp `[]`, `null` và `""` thành một khái niệm “không có dữ liệu” nếu nghiệp vụ cần phân biệt chúng.

## 7. Cấu hình toàn mapper hay từng property?

Có hai mức cấu hình chính.

### 7.1. Cấu hình toàn mapper

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
        .enable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS)
        .enable(SerializationFeature.WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED);
```

Ưu điểm là cấu hình đơn giản và nhất quán cho một nhóm dữ liệu. Nhược điểm là tất cả property phù hợp đều chịu ảnh hưởng, kể cả DTO của những API có schema nghiêm ngặt.

### 7.2. Cấu hình theo property

```java
public class PartnerPayload {
    @JsonFormat(with = JsonFormat.Feature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    private List<String> labels;

    @JsonFormat(with = JsonFormat.Feature.WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED)
    private List<String> legacyCodes;

    // getters và setters
}
```

Cấu hình theo property phù hợp khi chỉ một field hoặc một đối tác có quy ước đặc biệt. Riêng việc unwrap một JSON array thành scalar khi deserialize thường được điều khiển bằng `UNWRAP_SINGLE_VALUE_ARRAYS` ở mức `DeserializationFeature`; `@JsonFormat` có feature `ACCEPT_SINGLE_VALUE_AS_ARRAY` cho chiều scalar thành collection và `WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED` cho chiều ghi.

Nếu các DTO của nhiều đối tác có chính sách khác nhau, có thể tạo `ObjectReader`/`ObjectWriter` hoặc mapper riêng theo ranh giới tích hợp. Hãy hoàn tất cấu hình trước khi chia sẻ các object này giữa nhiều luồng.

## 8. Ví dụ tổng hợp với DTO và hai nguồn JSON

Giả sử một đối tác gửi danh sách `roles`, nhưng đôi lúc gửi một role dạng scalar:

```json
{
  "user_id": 10,
  "roles": "editor"
}
```

hoặc:

```json
{
  "user_id": 10,
  "roles": ["editor", "reviewer"]
}
```

DTO:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public class PartnerUser {
    @JsonProperty("user_id")
    private long userId;

    @JsonFormat(with = JsonFormat.Feature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    private List<String> roles;

    public long getUserId() {
        return userId;
    }

    public void setUserId(long userId) {
        this.userId = userId;
    }

    public List<String> getRoles() {
        return roles;
    }

    public void setRoles(List<String> roles) {
        this.roles = roles;
    }
}
```

Deserialize cả hai payload:

```java
ObjectMapper mapper = new ObjectMapper();

PartnerUser first = mapper.readValue(singleRoleJson, PartnerUser.class);
PartnerUser second = mapper.readValue(multipleRolesJson, PartnerUser.class);

System.out.println(first.getRoles());  // [editor]
System.out.println(second.getRoles()); // [editor, reviewer]
```

Code nghiệp vụ phía sau luôn làm việc với `List<String>`, bất kể đối tác gửi scalar hay array. Tuy vậy, ứng dụng vẫn nên ghi nhận nguồn nào đang gửi sai shape để có thể thống nhất hợp đồng về sau.

## 9. Ví dụ kiểm tra array một phần tử vào scalar

Giả sử một hệ thống cũ trả về `id` dưới dạng array dù domain chỉ có một ID:

```json
{
  "id": [42]
}
```

DTO:

```java
public class LegacyRecord {
    private long id;

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }
}
```

Đọc với chính sách unwrap:

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS);

LegacyRecord record = mapper.readValue(json, LegacyRecord.class);
System.out.println(record.getId()); // 42
```

Nếu đối tác gửi `"id": [42, 43]`, Jackson báo lỗi vì không thể chọn một giá trị scalar duy nhất. Nếu nghiệp vụ thực sự cho phép nhiều ID, kiểu Java đích phải là collection và cần xử lý như danh sách.

## 10. Ảnh hưởng đến tính ổn định của JSON output

`WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED` có thể khiến cùng một property thay đổi kiểu JSON tùy số lượng phần tử:

| Số phần tử trong Java list | JSON khi bật unwrapped |
|---:|---|
| 0 | `[]` |
| 1 | `"urgent"` |
| 2 | `["urgent", "review"]` |

Đây là một hợp đồng không ổn định về kiểu: client phải xử lý cả scalar lẫn array cho cùng một field. Nếu API được thiết kế mới, thông thường nên giữ collection luôn là JSON array, kể cả khi có một phần tử. Điều này làm schema rõ ràng và client đơn giản hơn.

Chỉ dùng unwrapped output khi cần tương thích với một hợp đồng đã tồn tại và client yêu cầu đúng định dạng đó. Khi đã bật, hãy kiểm tra chiều đọc của phía nhận: nó cần chấp nhận scalar vào collection, thường bằng `ACCEPT_SINGLE_VALUE_AS_ARRAY`.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Cannot deserialize String from Array | JSON gửi `[...]` nhưng target là `String` | Nếu hợp đồng cho phép đúng một phần tử, bật `UNWRAP_SINGLE_VALUE_ARRAYS` |
| Cannot deserialize ArrayList from String | JSON gửi scalar nhưng target là `List` | Bật `ACCEPT_SINGLE_VALUE_AS_ARRAY` hoặc sửa nguồn gửi đúng array |
| Array có hai phần tử không đọc được vào scalar | `UNWRAP_SINGLE_VALUE_ARRAYS` chỉ cho phép đúng một phần tử | Đổi target thành collection nếu nghiệp vụ cho phép nhiều giá trị |
| Một field được chấp nhận scalar ngoài dự kiến | Feature được bật toàn mapper | Chuyển sang `@JsonFormat` ở property cần thiết hoặc mapper riêng |
| Output lúc là scalar, lúc là array | Bật `WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED` | Giữ array ổn định hoặc xác nhận client chấp nhận cả hai dạng |
| Array rỗng biến thành null | Bật `ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT` cho object target | Xác định lại chính sách empty và null; tắt feature nếu không cần |
| List phần tử sai kiểu | Dùng raw `List.class` hoặc target generic không đầy đủ | Truyền `TypeReference<List<T>>` hoặc `JavaType` |

Không nên bắt mọi `JsonMappingException` rồi mặc định dùng phần tử đầu. Cách đó che giấu input sai shape và có thể làm mất dữ liệu mà không có dấu hiệu.

## 12. Kiểm thử chính sách với các trường hợp biên

Khi bật một trong các feature trên, cần kiểm tra ít nhất các hình dạng liên quan đến hợp đồng:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SingleValueArrayTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
            .enable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS);

    @Test
    void acceptsScalarAsOneElementList() throws Exception {
        List<String> values = mapper.readValue(
                "\"urgent\"",
                new com.fasterxml.jackson.core.type.TypeReference<List<String>>() {}
        );
        assertEquals(List.of("urgent"), values);
    }

    @Test
    void unwrapsOneElementArrayToScalar() throws Exception {
        String value = mapper.readValue("[\"urgent\"]", String.class);
        assertEquals("urgent", value);
    }

    @Test
    void rejectsArrayWithMultipleElementsForScalarTarget() {
        assertThrows(Exception.class,
                () -> mapper.readValue("[\"urgent\",\"review\"]", String.class));
    }
}
```

Trong test thực tế, nên thay `assertThrows(Exception.class, ...)` bằng exception mapping cụ thể phù hợp với Jackson version đang dùng, chẳng hạn `JsonMappingException` hoặc subtype cụ thể. Có thể bổ sung test cho `[]`, `null`, chuỗi rỗng, collection có nhiều phần tử và serialization một phần tử để xác nhận đầy đủ hợp đồng.

## 13. Chọn chính sách theo hợp đồng dữ liệu

| Nhu cầu | Chính sách nên cân nhắc |
|---|---|
| Một property `List<T>` đôi khi nhận scalar | `@JsonFormat(with = ACCEPT_SINGLE_VALUE_AS_ARRAY)` |
| Nhiều collection trong một nguồn cũ đều nhận scalar | `DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY` trên mapper dành riêng cho nguồn đó |
| Một property scalar đôi khi nhận array đúng một phần tử | `DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS` trên reader/mapper phù hợp |
| Output legacy yêu cầu list một phần tử thành scalar | `WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED`, tốt nhất giới hạn theo property |
| Object target cần xem `[]` là null | Cân nhắc `ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT` sau khi xác nhận hợp đồng |
| API mới cần kiểu dữ liệu rõ ràng | Giữ scalar là scalar và collection luôn là array |

Nếu nguồn dữ liệu không nhất quán, hãy coi chính sách linh hoạt là lớp tương thích tại biên tích hợp. Phần nghiệp vụ bên trong nên nhận một kiểu Java ổn định: field danh sách luôn là `List<T>`, field đơn luôn là kiểu scalar. Ghi log/metric về các payload sai shape khi phù hợp để có thể loại bỏ dần tương thích cũ.

## 14. Kết luận

Jackson cho phép kiểm soát riêng ba tình huống: scalar JSON thành collection bằng `ACCEPT_SINGLE_VALUE_AS_ARRAY`, array đúng một phần tử thành scalar bằng `UNWRAP_SINGLE_VALUE_ARRAYS`, và collection một phần tử thành scalar JSON khi ghi bằng `WRITE_SINGLE_ELEM_ARRAYS_UNWRAPPED`. Các feature này có hướng tác động khác nhau; array rỗng, `null` và chuỗi rỗng vẫn cần chính sách riêng. Hãy áp dụng ở phạm vi nhỏ nhất phù hợp với hợp đồng, giữ kiểu dữ liệu ổn định trong phần nghiệp vụ và kiểm thử cả trường hợp một phần tử lẫn mảng rỗng/nhiều phần tử.
