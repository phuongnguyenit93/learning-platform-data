# Giữ khác biệt giữa không cung cấp và yêu cầu xóa giá trị

Khi một API nhận yêu cầu cập nhật dữ liệu, một thuộc tính có thể xuất hiện theo ba trạng thái khác nhau:

1. **Không được gửi trong JSON:** client không đề cập thuộc tính đó; thông thường server giữ nguyên giá trị hiện tại.
2. **Được gửi với giá trị `null`:** client gửi tường minh rằng thuộc tính không có giá trị; tùy hợp đồng, server có thể phải xóa hoặc đặt giá trị hiện tại thành `null`.
3. **Được gửi với một giá trị cụ thể:** server thay giá trị hiện tại bằng giá trị mới.

Ba trạng thái này rất quan trọng với API cập nhật từng phần (partial update), đặc biệt là `PATCH`. Nếu mô hình Java chỉ có một field thông thường, hai trường hợp “không gửi” và “gửi `null`” thường bị nhập làm một. Khi đó, server không thể biết client muốn giữ nguyên dữ liệu hay chủ động xóa dữ liệu.

Trong Jackson, cần thiết kế DTO và cách đọc JSON để bảo toàn sự khác biệt này. Có thể dùng setter theo dõi sự hiện diện, `JsonNode` để kiểm tra cấu trúc đầu vào, hoặc kiểu bao ba trạng thái như `JsonNullable<T>`. Với API cần mô tả thao tác cập nhật tường minh, cũng có thể dùng JSON Merge Patch hoặc JSON Patch theo đúng hợp đồng.

## 1. Vì sao null và thiếu trường không giống nhau?

Giả sử hồ sơ người dùng hiện tại có:

```json
{
  "displayName": "Lan",
  "phoneNumber": "0900000000",
  "bio": "Yêu thích Java"
}
```

Client muốn đổi tên hiển thị nhưng giữ nguyên số điện thoại và phần giới thiệu. Nó có thể gửi:

```json
{
  "displayName": "Lan Nguyen"
}
```

Trường `phoneNumber` và `bio` không xuất hiện. Với cập nhật từng phần, ý nghĩa thường là không thay đổi hai trường đó.

Nếu client muốn xóa phần giới thiệu, nó có thể gửi:

```json
{
  "bio": null
}
```

Nếu client muốn thay số điện thoại:

```json
{
  "phoneNumber": "0912345678"
}
```

Như vậy, server cần hiểu:

| JSON | Ý nghĩa cập nhật thường gặp |
|---|---|
| Không có khóa `bio` | Giữ nguyên bio hiện tại |
| `"bio": null` | Xóa bio hoặc đặt bio thành null |
| `"bio": "Nội dung mới"` | Thay bio bằng nội dung mới |
| `"bio": ""` | Đặt bio thành chuỗi rỗng, nếu hợp đồng cho phép |

Giá trị chuỗi rỗng `""` không đồng nghĩa với `null`. Nó là một giá trị chuỗi có độ dài bằng 0. Tương tự, array rỗng `[]`, object rỗng `{}`, số `0` và boolean `false` đều là các giá trị cụ thể, không phải trường bị thiếu.

## 2. Vì sao DTO thông thường làm mất thông tin?

Một request DTO đơn giản có thể được khai báo như sau:

```java
public class UpdateProfileRequest {
    private String displayName;
    private String bio;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }
}
```

Nếu Jackson đọc JSON:

```json
{}
```

thì setter không được gọi cho `bio`; field giữ giá trị mặc định `null`.

Nếu Jackson đọc:

```json
{"bio": null}
```

thì theo cách xử lý null thông thường, setter được gọi với tham số `null`; field cũng có giá trị `null`.

Sau khi deserialize, cả hai trường hợp đều có thể cho kết quả:

```java
request.getBio() == null
```

DTO không còn đủ thông tin để biết client đã bỏ qua khóa hay gửi khóa với giá trị null. Nếu code cập nhật dùng điều kiện:

```java
if (request.getBio() != null) {
    profile.setBio(request.getBio());
}
```

thì chuỗi mới được cập nhật, nhưng client không thể yêu cầu xóa bio bằng `null`. Nếu thay bằng:

```java
profile.setBio(request.getBio());
```

thì trường bị thiếu cũng có thể xóa bio ngoài ý muốn. Cả hai cách đều không thể biểu diễn đầy đủ ba trạng thái.

## 3. Cách 1: Theo dõi sự hiện diện bằng setter

Một cách đơn giản là thêm cờ cho biết thuộc tính có xuất hiện trong JSON hay không. Jackson chỉ gọi setter khi property được cung cấp; vì vậy setter có thể đánh dấu `provided = true` ngay cả khi giá trị nhận được là `null`.

```java
import com.fasterxml.jackson.annotation.JsonSetter;

public class UpdateProfileRequest {
    private boolean bioProvided;
    private String bio;

    @JsonSetter("bio")
    public void setBio(String bio) {
        this.bioProvided = true;
        this.bio = bio;
    }

    public boolean isBioProvided() {
        return bioProvided;
    }

    public String getBio() {
        return bio;
    }
}
```

Kết quả:

| JSON đầu vào | `isBioProvided()` | `getBio()` | Diễn giải |
|---|---:|---|---|
| `{}` | `false` | `null` | Không cập nhật |
| `{"bio": null}` | `true` | `null` | Yêu cầu xóa hoặc đặt null |
| `{"bio": "Java"}` | `true` | `"Java"` | Thay bằng giá trị mới |
| `{"bio": ""}` | `true` | `""` | Thay bằng chuỗi rỗng |

Trong cách này, `bioProvided` mặc định là `false`. Nếu khóa `bio` không có trong JSON, Jackson không gọi setter nên cờ vẫn là `false`. Nếu khóa có mặt với `null`, setter được gọi và cờ thành `true`.

### 3.1. Áp dụng ba trạng thái vào logic cập nhật

Application service có thể phân biệt ba trường hợp:

```java
public void updateProfile(
        UserProfile profile,
        UpdateProfileRequest request) {

    if (request.isBioProvided()) {
        if (request.getBio() == null) {
            profile.clearBio();
        } else {
            profile.changeBio(request.getBio());
        }
    }
}
```

Ở đây:

- Không gửi `bio`: không gọi `clearBio()` hoặc `changeBio()`.
- Gửi `bio: null`: gọi `clearBio()`.
- Gửi chuỗi: gọi `changeBio()` với giá trị mới.

`clearBio()` và `changeBio()` là hành vi của domain model. DTO chỉ giữ thông tin client đã gửi gì; service điều phối yêu cầu; domain model thực hiện thay đổi theo quy tắc của ứng dụng.

Nếu có nhiều thuộc tính cần cập nhật, mỗi thuộc tính có thể có một cờ tương ứng. Tuy nhiên, DTO có quá nhiều cờ sẽ dài và dễ quên. Khi số trường lớn, hãy cân nhắc một kiểu bao dùng chung hoặc thư viện chuyên hỗ trợ trạng thái undefined.

### 3.2. Những điều cần chú ý với setter tracking

- Dùng kiểu bao như `Integer`, `Boolean` cho dữ liệu có thể null; không dùng `int` hoặc `boolean` nếu cần phân biệt thiếu và giá trị mặc định.
- Đảm bảo Jackson thực sự sử dụng setter được đánh dấu. Nếu field visibility, creator hoặc cấu hình access thay đổi, cần kiểm tra cách property được phát hiện.
- Không cấu hình `Nulls.SKIP` cho property này nếu cần nhận biết null tường minh, vì setter có thể không được gọi khi giá trị JSON là null.
- Nếu dùng constructor hoặc builder để tạo DTO, cần một cách theo dõi presence tương ứng; cờ trong setter chỉ hoạt động khi setter thực sự được gọi.
- Không tái sử dụng cùng một request DTO cho nhiều lần deserialize nếu trạng thái presence không được khởi tạo lại.

## 4. Cách 2: Kiểm tra trực tiếp bằng JsonNode

Nếu cấu trúc request động hoặc chỉ cần kiểm tra một số trường, có thể đọc JSON thành `JsonNode` rồi kiểm tra sự hiện diện của từng khóa.

```java
JsonNode root = mapper.readTree(json);

if (!root.has("bio")) {
    // Không cung cấp: giữ nguyên bio.
} else {
    JsonNode bioNode = root.get("bio");

    if (bioNode.isNull()) {
        // Có cung cấp null: xóa bio.
    } else if (bioNode.isTextual()) {
        // Có chuỗi: thay bio bằng bioNode.asText().
    } else {
        throw new IllegalArgumentException("bio must be a string or null");
    }
}
```

Hai phương thức `has` và `hasNonNull` có ý nghĩa khác nhau:

| Phương thức | Khóa không tồn tại | Khóa tồn tại với JSON null | Khóa tồn tại với giá trị khác null |
|---|---|---|---|
| `has("bio")` | `false` | `true` | `true` |
| `hasNonNull("bio")` | `false` | `false` | `true` |

Do đó, nếu cần phân biệt “không gửi” với “gửi null”, hãy dùng `has()` rồi kiểm tra `isNull()`. Nếu chỉ dùng `hasNonNull()`, hai trạng thái thiếu và null sẽ lại bị gộp thành một.

`path("bio")` trả về `MissingNode` khi khóa không tồn tại, trong khi `get("bio")` trả về `null` Java khi không có khóa. Cả hai cách đều có thể dùng nếu kiểm tra đúng trạng thái, nhưng `has()` thường thể hiện ý định rõ ràng khi xử lý partial update.

Tree Model phù hợp khi request có cấu trúc động, cần kiểm tra nhiều khóa có điều kiện hoặc cần giữ lại những phần JSON chưa biết trước. Nếu DTO đã có cấu trúc ổn định và chỉ cần phân biệt presence cho vài trường, setter tracking thường dễ tích hợp hơn.

## 5. Cách 3: Dùng JsonNullable để biểu diễn undefined, null và value

Khi nhiều DTO cần biểu diễn trạng thái cập nhật ba giá trị, một kiểu bao như `JsonNullable<T>` có thể giúp code rõ ràng hơn. Kiểu này thường được dùng cùng thư viện `jackson-databind-nullable` của OpenAPI Tools.

Ba trạng thái chính:

| Trạng thái | Ý nghĩa |
|---|---|
| `JsonNullable.undefined()` | Thuộc tính không được cung cấp |
| `JsonNullable.of(null)` | Thuộc tính được cung cấp tường minh với null |
| `JsonNullable.of(value)` | Thuộc tính được cung cấp với giá trị cụ thể |

Ví dụ DTO:

```java
import org.openapitools.jackson.nullable.JsonNullable;

public class UpdateProfileRequest {
    private JsonNullable<String> bio = JsonNullable.undefined();

    public JsonNullable<String> getBio() {
        return bio;
    }

    public void setBio(JsonNullable<String> bio) {
        this.bio = bio;
    }
}
```

Để Jackson xử lý kiểu này, cần thêm dependency tương ứng và đăng ký `JsonNullableModule`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.openapitools.jackson.nullable.JsonNullableModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JsonNullableModule());
```

Dependency Maven thường có dạng:

```xml
<dependency>
    <groupId>org.openapitools</groupId>
    <artifactId>jackson-databind-nullable</artifactId>
    <version>${jackson-databind-nullable.version}</version>
</dependency>
```

Hãy quản lý version bằng dependency management phù hợp với dự án, thay vì sao chép một version tùy ý. Module cần tương thích với phiên bản Jackson đang sử dụng.

Khi cập nhật:

```java
JsonNullable<String> bio = request.getBio();

if (bio != null && bio.isPresent()) {
    String value = bio.orElse(null);
    if (value == null) {
        profile.clearBio();
    } else {
        profile.changeBio(value);
    }
}
```

`isPresent()` cho biết wrapper có giá trị được cung cấp hay không. `orElse(null)` có thể trả về null nếu trạng thái là `JsonNullable.of(null)`. Cần kiểm tra wrapper không phải null trong trường hợp DTO được tạo thủ công hoặc cấu hình deserialization không như mong đợi.

Với module được đăng ký đúng, property bị thiếu có thể giữ trạng thái `undefined`, JSON null trở thành trạng thái present với null, còn giá trị cụ thể trở thành present với value. Hãy viết test trên đúng phiên bản thư viện và cấu hình ứng dụng để xác nhận hành vi này.

## 6. Vì sao Optional thường không giải quyết đủ ba trạng thái?

`Optional<T>` hữu ích để biểu diễn một kết quả có thể có hoặc không có giá trị trong code Java, nhưng không tự động là mô hình ba trạng thái cho partial update.

Nếu một property `Optional<String>` được đọc từ JSON, cách xử lý còn phụ thuộc module Jackson và cấu hình. Trong nhiều cách ánh xạ thông thường, trường bị thiếu và trường có giá trị null đều có thể trở thành `Optional.empty()`. Khi đó, ứng dụng vẫn không biết client có chủ động yêu cầu xóa hay không.

Nếu hợp đồng cần ba trạng thái, hãy chọn một mô hình có trạng thái presence tường minh như:

- Cờ `provided` cùng giá trị trong DTO.
- `JsonNode` và kiểm tra `has()`/`isNull()`.
- `JsonNullable<T>` với module tương ứng.
- Một kiểu `FieldUpdate<T>` do ứng dụng định nghĩa.

Đừng chọn `Optional` chỉ vì tên gọi có vẻ thể hiện trường không bắt buộc. Cần kiểm thử chính xác cách Jackson ánh xạ trường thiếu và null trong phiên bản đang dùng.

## 7. Phân biệt null với các quy tắc Nulls của Jackson

Jackson có `@JsonSetter` và `Nulls` để quy định cách xử lý giá trị null khi deserialize:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class SettingsRequest {
    @JsonSetter(nulls = Nulls.SKIP)
    private String language;
}
```

Một số lựa chọn:

| Giá trị | Hành vi khi JSON có null |
|---|---|
| `Nulls.SET` | Gán null cho property (hành vi thường gặp mặc định) |
| `Nulls.SKIP` | Bỏ qua việc gán null; giữ giá trị hiện tại/default |
| `Nulls.FAIL` | Báo lỗi khi gặp null |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng do kiểu đích định nghĩa nếu hỗ trợ |
| `Nulls.DEFAULT` | Dùng chính sách mặc định áp dụng cho property/context |

Các lựa chọn này xử lý **giá trị null có mặt trong JSON**. Chúng không tự tạo thông tin cho biết một property bị thiếu. Ví dụ, `Nulls.SKIP` có thể hữu ích khi muốn null không ghi đè giá trị khởi tạo, nhưng nó cũng làm mất tín hiệu “client gửi null” nếu ứng dụng cần coi null là yêu cầu xóa.

Đặc biệt với partial update, đừng bật `Nulls.SKIP` trên mọi trường rồi kỳ vọng vẫn phân biệt được ba trạng thái. Hãy xác định ý nghĩa của null trong hợp đồng trước khi chọn chính sách.

`@JsonInclude` cũng không giải quyết vấn đề presence ở chiều đọc. `NON_NULL` hoặc `NON_EMPTY` chủ yếu quyết định thuộc tính nào được ghi ra JSON khi serialize; chúng không cho biết client đã gửi trường nào trong request.

## 8. JSON Merge Patch và ý nghĩa của null

Một cách chuẩn hóa partial update ở tầng HTTP là JSON Merge Patch theo RFC 7396. Request dùng media type:

```text
application/merge-patch+json
```

Trong JSON Merge Patch:

- Thành viên không xuất hiện trong patch giữ nguyên giá trị tương ứng của tài liệu đích.
- Thành viên có giá trị null yêu cầu loại bỏ thành viên đó khỏi tài liệu đích.
- Object được merge đệ quy.
- Array được thay thế như một giá trị hoàn chỉnh, không merge từng phần tử theo index.
- Patch là object ở cấp cao nhất trong mô hình merge patch thông thường; một giá trị không phải object có thể thay thế toàn bộ tài liệu đích.

Ví dụ tài liệu hiện tại:

```json
{
  "displayName": "Lan",
  "bio": "Yêu thích Java",
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 3"
  },
  "tags": ["java", "backend"]
}
```

Patch:

```json
{
  "bio": null,
  "address": {
    "district": "District 1"
  },
  "tags": ["java", "cloud"]
}
```

Sau khi áp dụng merge patch:

```json
{
  "displayName": "Lan",
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  },
  "tags": ["java", "cloud"]
}
```

`displayName` được giữ nguyên vì patch không nhắc tới nó. `bio` bị loại khỏi tài liệu vì patch đặt null. `address.district` được cập nhật, còn `address.city` được giữ nguyên do merge đệ quy. `tags` bị thay thế toàn bộ bằng array mới.

Lưu ý quan trọng: trong Merge Patch, null mang nghĩa xóa thành viên. Nếu API cần phân biệt “lưu giá trị JSON null” với “xóa thành viên”, Merge Patch không đủ để biểu diễn cả hai ý nghĩa một cách độc lập. Hãy chọn định dạng patch khác hoặc thiết kế command cập nhật riêng.

Jackson cung cấp công cụ parse và thao tác JSON, nhưng không tự biến mọi request `application/merge-patch+json` thành cập nhật đúng nghiệp vụ. Ứng dụng phải áp dụng đúng thuật toán merge patch hoặc dùng thư viện chuyên biệt, rồi ánh xạ kết quả sang mô hình domain với chính sách rõ ràng.

## 9. JSON Patch: mô tả thao tác cập nhật tường minh

JSON Patch theo RFC 6902 biểu diễn cập nhật dưới dạng một mảng thao tác. Media type là:

```text
application/json-patch+json
```

Các thao tác thường gặp:

| Operation | Ý nghĩa |
|---|---|
| `add` | Thêm giá trị tại path; với object có thể thêm hoặc thay thế thành viên |
| `remove` | Xóa giá trị tại path |
| `replace` | Thay giá trị tại path đã tồn tại |
| `move` | Di chuyển giá trị từ path này sang path khác |
| `copy` | Sao chép giá trị từ path này sang path khác |
| `test` | Kiểm tra giá trị tại path có bằng giá trị mong đợi hay không |

Ví dụ:

```json
[
  {"op": "replace", "path": "/displayName", "value": "Lan Nguyen"},
  {"op": "remove", "path": "/bio"},
  {"op": "add", "path": "/tags/-", "value": "jackson"}
]
```

Mỗi thao tác chỉ rõ hành động. `remove` biểu diễn yêu cầu xóa rõ ràng, trong khi `replace` cung cấp giá trị mới. Cách này tránh việc phải suy luận hành động chỉ từ sự có mặt hay vắng mặt của field.

Tuy nhiên, JSON Patch có thể tác động vào đường dẫn lồng nhau hoặc vị trí trong array. Server cần giới hạn các path và operation được phép. Không nên cho client tùy ý sửa các thuộc tính nội bộ như `role`, `balance`, `ownerId` hoặc trạng thái quản trị chỉ vì JSON Patch cho phép biểu diễn chúng.

Khi áp dụng patch, nên:

1. Xác thực người gọi có quyền cập nhật tài nguyên.
2. Chỉ cho phép các path/operation nằm trong whitelist của API.
3. Kiểm tra điều kiện `test` hoặc version/ETag nếu cần chống cập nhật cạnh tranh.
4. Áp dụng patch trên bản biểu diễn phù hợp hoặc chuyển thành command có kiểu.
5. Chạy validation và domain rules trước khi lưu.
6. Ghi nhận kết quả theo transaction và xử lý lỗi patch một cách nguyên tử theo hợp đồng.

## 10. Áp dụng ba trạng thái vào cập nhật database

Giả sử một bảng `user_profile` có cột `bio`. API nhận `UpdateProfileRequest` với `bioProvided` và `bio`.

Quy tắc cập nhật có thể được biểu diễn:

```text
bioProvided = false
    -> không đưa cột bio vào lệnh UPDATE

bioProvided = true, bio = null
    -> cập nhật cột bio = NULL

bioProvided = true, bio = "nội dung"
    -> cập nhật cột bio = "nội dung"
```

Điều này khác với câu SQL luôn ghi `bio = :bio` khi `:bio` null, vì câu SQL đó có thể xóa dữ liệu ngay cả khi client không gửi trường `bio`.

Ví dụ ở tầng ứng dụng:

```java
if (request.isBioProvided()) {
    profile.setBio(request.getBio());
}
```

Nếu `setBio(null)` được phép xóa, hai trạng thái được giữ đúng. Nếu cần domain method phân biệt rõ hơn:

```java
if (request.isBioProvided()) {
    if (request.getBio() == null) {
        profile.clearBio();
    } else {
        profile.changeBio(request.getBio());
    }
}
```

Khi dùng JPA, chỉ thay đổi entity nếu field được cung cấp. Khi dùng SQL động, chỉ thêm cột vào `SET` nếu cờ presence là true. Khi dùng câu lệnh cập nhật tĩnh, cần truyền một cờ bổ sung hoặc biểu thức điều kiện để phân biệt giữ nguyên với đặt null. Cách lưu trữ không được làm mất ý nghĩa ba trạng thái của request.

## 11. Cập nhật collection và object lồng nhau

Các kiểu dữ liệu phức tạp cần quy định semantics rõ hơn.

Ví dụ request:

```json
{
  "tags": []
}
```

Array rỗng thường có nghĩa là thay danh sách tags bằng danh sách rỗng. Nó khác với:

```json
{}
```

Trong partial update, trường `tags` bị thiếu thường có nghĩa giữ nguyên danh sách hiện tại.

Và:

```json
{"tags": null}
```

có thể mang nghĩa xóa toàn bộ danh sách, đặt danh sách thành null hoặc không hợp lệ; API phải quy định rõ. Không nên tự suy ra ý nghĩa chỉ từ kiểu Java `List<T>`.

Object lồng nhau cũng có thể có hai chính sách phổ biến:

- **Thay thế toàn bộ object:** nếu gửi `address`, toàn bộ địa chỉ được thay bằng object mới.
- **Cập nhật đệ quy:** chỉ những trường xuất hiện trong `address` mới thay đổi.

Hai chính sách này cho kết quả khác nhau. Nếu cần merge đệ quy, có thể áp dụng JSON Merge Patch. Nếu dùng DTO setter tracking, cần theo dõi presence ở cả object cha và các trường con, đồng thời xác định rõ khi `address: null` thì xóa toàn bộ địa chỉ hay giữ nguyên.

## 12. Validation và bảo vệ dữ liệu

Phân biệt thiếu và null không có nghĩa là chấp nhận mọi giá trị. Sau khi xác định trạng thái cập nhật, ứng dụng vẫn cần kiểm tra:

- Thuộc tính có được phép cập nhật bởi người gọi hay không.
- Giá trị mới có đúng kiểu và nằm trong miền hợp lệ hay không.
- Null có được phép theo nghiệp vụ hay không.
- Chuỗi rỗng có hợp lệ hay phải từ chối.
- Collection có số lượng phần tử tối đa hay không.
- Object lồng nhau có hợp lệ và có thuộc tài nguyên đang cập nhật hay không.
- Người gọi có quyền xóa hoặc thay đổi thuộc tính đó hay không.

Không để Jackson quyết định quyền truy cập. Annotation như `@JsonProperty(access = WRITE_ONLY)` chỉ kiểm soát chiều ánh xạ JSON, không phải cơ chế phân quyền. Một client không có quyền sửa `role` vẫn phải bị từ chối ở tầng ứng dụng dù JSON parser có thể đọc trường đó.

## 13. Kiểm thử các trạng thái của property

Với setter tracking, nên kiểm thử ít nhất ba trường hợp:

```java
class UpdateProfileRequestTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void missingBioMeansNotProvided() throws Exception {
        UpdateProfileRequest request = mapper.readValue(
            "{}", UpdateProfileRequest.class);

        assertFalse(request.isBioProvided());
        assertNull(request.getBio());
    }

    @Test
    void explicitNullMeansProvidedAndNull() throws Exception {
        UpdateProfileRequest request = mapper.readValue(
            "{\"bio\":null}", UpdateProfileRequest.class);

        assertTrue(request.isBioProvided());
        assertNull(request.getBio());
    }

    @Test
    void concreteValueMeansProvidedAndHasValue() throws Exception {
        UpdateProfileRequest request = mapper.readValue(
            "{\"bio\":\"Java\"}", UpdateProfileRequest.class);

        assertTrue(request.isBioProvided());
        assertEquals("Java", request.getBio());
    }
}
```

Các test này giả định property được Jackson ánh xạ qua setter và chính sách null mặc định cho phép gọi setter với null. Nếu cấu hình `@JsonSetter(nulls = Nulls.SKIP)` hoặc cấu hình null khác, kết quả sẽ thay đổi. Hãy kiểm thử trên mapper thực tế mà ứng dụng sử dụng.

Với `JsonNode`, cần kiểm thử `has("bio")` cho trường hợp null tường minh và trường hợp thiếu. Với `JsonNullable`, kiểm thử riêng undefined, present-null và present-value sau khi đăng ký `JsonNullableModule`.

## 14. Chọn cách biểu diễn phù hợp

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Chỉ cần đổi tên khóa JSON so với field Java | `@JsonProperty` |
| Chấp nhận tên cũ khi đọc nhưng chỉ phát tên mới | `@JsonProperty` kết hợp `@JsonAlias` |
| Cập nhật một vài trường, chỉ có ít property cần phân biệt thiếu/null | Setter tracking bằng cờ presence |
| Payload động, cần kiểm tra nhiều khóa có điều kiện | `JsonNode` và `has()`/`isNull()` |
| Nhiều DTO cần biểu diễn undefined/null/value | `JsonNullable<T>` và module tương ứng |
| API cần thao tác cập nhật rõ ràng theo đường dẫn | JSON Patch |
| API muốn semantics merge object theo RFC 7396 | JSON Merge Patch |

Không nên dùng `@JsonProperty` như giải pháp cho mọi vấn đề cập nhật từng phần. Annotation này chủ yếu xác định tên và metadata của property. Nó không tự ghi nhớ một trường đã bị thiếu trong JSON. Khi cần phân biệt ba trạng thái, phải chọn một mô hình dữ liệu giữ được thông tin presence.

## 15. Kết luận

Trong API cập nhật từng phần, “không cung cấp”, “cung cấp null” và “cung cấp giá trị” là ba ý nghĩa khác nhau. DTO thông thường có field nullable thường làm hai trạng thái đầu cùng trở thành `null`, khiến server không thể biết nên giữ nguyên hay xóa dữ liệu.

Hãy chọn cách biểu diễn phù hợp với hợp đồng: setter tracking cho DTO đơn giản, `JsonNode` cho payload động, `JsonNullable<T>` khi cần kiểu ba trạng thái dùng lại, hoặc JSON Merge Patch/JSON Patch khi muốn chuẩn hóa giao thức cập nhật. Sau khi ánh xạ, chuyển trạng thái thành hành động ứng dụng rõ ràng: bỏ qua, xóa hoặc thay thế. Cuối cùng, validation và phân quyền vẫn phải được thực hiện ở tầng ứng dụng/domain trước khi lưu dữ liệu.
