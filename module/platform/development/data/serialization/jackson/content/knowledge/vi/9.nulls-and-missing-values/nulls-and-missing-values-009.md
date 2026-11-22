# Biểu diễn thuộc tính tùy chọn và vai trò của module hỗ trợ Optional

Trong Java, một thuộc tính có thể không có giá trị. Khi biểu diễn dữ liệu đó bằng JSON, cần quyết định rõ trường hợp nào là **property không xuất hiện**, trường hợp nào là **property có giá trị null**, và trường hợp nào là **property có một giá trị cụ thể**.

`java.util.Optional<T>` cung cấp một cách biểu diễn có hoặc không có giá trị trong Java. Tuy nhiên, JSON không có kiểu Optional riêng. Để Jackson ánh xạ `Optional` thành giá trị JSON một cách tự nhiên, ứng dụng Jackson 2.x thường cần module `jackson-datatype-jdk8` với `Jdk8Module`.

Bài học này giải thích cách biểu diễn thuộc tính tùy chọn trong DTO, cách đăng ký module, hành vi serialize/deserialize, cách phân biệt absent và null, và khi nào cần một mô hình dữ liệu khác thay vì chỉ dùng Optional.

## 1. Thuộc tính tùy chọn trong Java và JSON

Một thuộc tính tùy chọn là thuộc tính mà dữ liệu có thể không cung cấp hoặc không có giá trị. Ví dụ hồ sơ người dùng có nickname tùy chọn:

```json
{
  "id": 42,
  "username": "an",
  "nickname": "Annie"
}
```

Một hồ sơ khác không có nickname:

```json
{
  "id": 43,
  "username": "binh"
}
```

Và một payload có nickname được gửi rõ ràng với giá trị null:

```json
{
  "id": 44,
  "username": "chi",
  "nickname": null
}
```

Ba hình dạng trên cần được phân biệt:

| Trạng thái JSON | Ý nghĩa thường gặp |
| --- | --- |
| Property có giá trị, ví dụ `"nickname": "Annie"` | Người gửi cung cấp giá trị |
| Property không xuất hiện | Người gửi không cung cấp property |
| Property xuất hiện với `null` | Người gửi có gửi property và giá trị của nó là null |

JSON không có literal `undefined`. Việc property không xuất hiện được thể hiện bằng cách bỏ hẳn tên property khỏi object.

Ý nghĩa nghiệp vụ của missing và null phụ thuộc hợp đồng API. Với một API cập nhật hồ sơ, missing có thể nghĩa là giữ nguyên nickname hiện tại, còn null có thể nghĩa là xóa nickname. Với API tạo mới, cả hai có thể được xem là không cung cấp nickname. Jackson chỉ thực hiện parsing và mapping; ứng dụng phải định nghĩa ý nghĩa của từng trạng thái.

## 2. Optional trong Java

`Optional<T>` là một container có thể chứa một giá trị không-null hoặc biểu diễn trạng thái không có giá trị.

Ví dụ:

```java
Optional<String> nickname = Optional.of("Annie");

Optional<String> missingNickname = Optional.empty();
```

Các cách tạo Optional thường gặp:

| API | Công dụng |
| --- | --- |
| `Optional.of(value)` | Tạo Optional có giá trị; ném NullPointerException nếu value là null |
| `Optional.ofNullable(value)` | Tạo Optional có giá trị nếu khác null, ngược lại là empty |
| `Optional.empty()` | Tạo Optional không có giá trị |
| `optional.isPresent()` | Kiểm tra có giá trị |
| `optional.isEmpty()` | Kiểm tra không có giá trị (Java 11+) |
| `optional.orElse(defaultValue)` | Lấy giá trị hoặc giá trị mặc định |
| `optional.orElseGet(supplier)` | Lấy giá trị hoặc tính giá trị mặc định khi cần |
| `optional.orElseThrow()` | Lấy giá trị hoặc ném exception |

Ví dụ dùng trong DTO:

```java
public record UserResponse(
    long id,
    String username,
    Optional<String> nickname
) {}
```

Khi có nickname:

```java
UserResponse user = new UserResponse(
    42L,
    "an",
    Optional.of("Annie")
);
```

Khi không có nickname:

```java
UserResponse user = new UserResponse(
    43L,
    "binh",
    Optional.empty()
);
```

Optional không thể chứa một Java null bên trong. `Optional.ofNullable(null)` trả về `Optional.empty()`. Do đó, chỉ riêng Optional không thể biểu diễn đồng thời ba trạng thái độc lập: không cung cấp property, cung cấp null và cung cấp giá trị.

### 2.1. Optional không thay thế validation

Optional biểu diễn sự hiện diện của một giá trị, không xác nhận giá trị đó hợp lệ.

Ví dụ:

```java
Optional<String> email = Optional.of("not-an-email");
```

Optional này có giá trị, nhưng chuỗi đó vẫn có thể không phải email hợp lệ. Ứng dụng vẫn cần validation về định dạng, độ dài, quyền sở hữu hoặc quy tắc nghiệp vụ.

Tương tự, `Optional.empty()` không có nghĩa dữ liệu được phép thiếu trong mọi tình huống. Nếu trường là bắt buộc, validation hoặc constructor/domain rule phải từ chối trạng thái rỗng.

### 2.2. Optional có phù hợp làm field DTO không?

Theo thiết kế Java, Optional thường được dùng làm kiểu trả về khi một method có thể không tìm thấy kết quả. Dùng Optional làm field, tham số hoặc thành phần DTO là một lựa chọn thiết kế cần cân nhắc.

Có thể dùng Optional trong DTO khi:

- Hợp đồng JSON có một thuộc tính thực sự tùy chọn.
- Đội ngũ muốn thể hiện rõ trạng thái có/không có giá trị ở tầng Java.
- Jackson module và các framework liên quan được cấu hình, kiểm thử phù hợp.

Cần cân nhắc kiểu field thông thường nullable khi:

- Dự án dùng bean validation, persistence hoặc framework không xử lý Optional field như mong đợi.
- Cần phân biệt missing, explicit null và giá trị cụ thể.
- DTO cần mô tả patch/update với ngữ nghĩa ba trạng thái.

Không nên dùng Optional chỉ để tránh mọi Java null. Hãy chọn kiểu dựa trên hợp đồng dữ liệu và cách các lớp trong ứng dụng xử lý nó.

## 3. Module hỗ trợ Optional của Jackson

Jackson core/databind không tự định nghĩa JSON token cho Optional. Với Jackson 2.x, module dành cho các kiểu dữ liệu Java 8 là:

- Artifact: `jackson-datatype-jdk8`
- Module class: `com.fasterxml.jackson.datatype.jdk8.Jdk8Module`
- Kiểu được hỗ trợ gồm `Optional<T>` và các biến thể primitive như `OptionalInt`, `OptionalLong`, `OptionalDouble`.

Module đăng ký serializer/deserializer để Jackson chuyển đổi Optional thành giá trị JSON bên trong thay vì coi Optional như một JavaBean thông thường.

### 3.1. Khai báo dependency Gradle

Với Gradle:

```groovy
dependencies {
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jdk8")
}
```

Nếu dự án không dùng BOM hoặc dependency platform để quản lý Jackson, cần khai báo version tương thích với các artifact Jackson còn lại. Không nên để `jackson-databind`, `jackson-core`, `jackson-annotations` và module JDK 8 lệch phiên bản tùy tiện.

### 3.2. Khai báo dependency Maven

Với Maven:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jdk8</artifactId>
</dependency>
```

Nếu dự án dùng Spring Boot parent/BOM hoặc Jackson BOM, hãy để dependency management quản lý version. Nếu không, khai báo version rõ ràng và giữ các artifact Jackson trong cùng một release line phù hợp.

### 3.3. Đăng ký Jdk8Module trong ứng dụng Java độc lập

Có thể đăng ký trực tiếp:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new Jdk8Module());
```

Hoặc dùng JsonMapper builder:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new Jdk8Module())
    .build();
```

Sau khi cấu hình xong, hãy tái sử dụng mapper. Không thay đổi cấu hình module trong lúc các luồng đang dùng mapper.

Một lựa chọn khác là:

```java
ObjectMapper mapper = new ObjectMapper()
    .findAndRegisterModules();
```

`findAndRegisterModules()` tìm các module có thể phát hiện qua cơ chế service loader trên classpath. Cách này thuận tiện khi ứng dụng có nhiều module, nhưng việc đăng ký tường minh giúp cấu hình dễ đọc và dễ dự đoán hơn trong ví dụ hoặc ứng dụng nhỏ.

### 3.4. Sử dụng với Spring Boot

Trong ứng dụng Spring Boot, module Jackson có mặt trên classpath thường được tích hợp vào mapper do framework cấu hình. Tuy nhiên, cần kiểm tra phiên bản Spring Boot và cách dự án tùy chỉnh `ObjectMapper`.

Ưu tiên inject mapper do Spring quản lý:

```java
@Service
public class UserJsonService {

    private final ObjectMapper mapper;

    public UserJsonService(ObjectMapper mapper) {
        this.mapper = mapper;
    }
}
```

Không nên tạo `new ObjectMapper()` riêng trong service rồi kỳ vọng mapper đó có cùng module, naming strategy, inclusion rule và customizer với mapper HTTP của Spring Boot.

Nếu dự án có custom mapper hoặc builder riêng, hãy bảo đảm `Jdk8Module` được đăng ký trên đúng mapper dùng cho request/response. Viết integration test qua Spring context để xác nhận hành vi thực tế.

## 4. Serialize Optional thành JSON

Sau khi đăng ký `Jdk8Module`, Optional được biểu diễn bằng giá trị chứa bên trong.

### 4.1. Optional có giá trị

```java
public record UserResponse(
    long id,
    String username,
    Optional<String> nickname
) {}

UserResponse user = new UserResponse(
    42L,
    "an",
    Optional.of("Annie")
);

String json = mapper.writeValueAsString(user);
```

JSON có dạng:

```json
{
  "id": 42,
  "username": "an",
  "nickname": "Annie"
}
```

Jackson ghi giá trị bên trong Optional. Nó không tạo object kiểu:

```json
{
  "nickname": {
    "present": true,
    "value": "Annie"
  }
}
```

Optional là chi tiết biểu diễn trong Java; JSON vẫn giữ kiểu string của hợp đồng.

### 4.2. Optional.empty()

Khi Optional không có giá trị:

```java
UserResponse user = new UserResponse(
    43L,
    "binh",
    Optional.empty()
);

String json = mapper.writeValueAsString(user);
```

Theo cấu hình mặc định, Optional.empty thường được serialize thành JSON null:

```json
{
  "id": 43,
  "username": "binh",
  "nickname": null
}
```

Nếu hợp đồng yêu cầu bỏ hẳn property không có giá trị, cần cấu hình inclusion. Việc Optional.empty được ghi thành null hay bị loại khỏi object là hai hành vi khác nhau.

### 4.3. Bỏ qua Optional.empty bằng NON_ABSENT

Dùng `JsonInclude.Include.NON_ABSENT` để loại các giá trị absent, bao gồm Optional.empty:

```java
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record UserResponse(
    long id,
    String username,
    Optional<String> nickname
) {}
```

Với `Optional.empty()`, JSON có thể được ghi như sau:

```json
{
  "id": 43,
  "username": "binh"
}
```

Có thể áp dụng ở cấp property:

```java
public record UserResponse(
    long id,
    String username,
    @JsonInclude(JsonInclude.Include.NON_ABSENT)
    Optional<String> nickname
) {}
```

Hoặc cấu hình inclusion ở cấp mapper nếu chính sách đó áp dụng cho nhiều DTO:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new Jdk8Module())
    .build();

mapper.setDefaultPropertyInclusion(
    JsonInclude.Value.construct(
        JsonInclude.Include.NON_ABSENT,
        JsonInclude.Include.ALWAYS
    )
);
```

Hãy cân nhắc phạm vi cấu hình. Inclusion toàn cục ảnh hưởng đến nhiều kiểu property khác, nên annotation ở property/DTO có thể phù hợp hơn khi hợp đồng chỉ yêu cầu bỏ qua một số Optional.

### 4.4. NON_NULL khác NON_ABSENT như thế nào?

| Inclusion | Hành vi với Optional.empty | Hành vi với Java null |
| --- | --- | --- |
| `ALWAYS` | Ghi property; serializer Optional thường ghi JSON null | Ghi null |
| `NON_NULL` | Optional object không phải Java null nên thường vẫn được xét để ghi; kết quả thường là JSON null | Bỏ property |
| `NON_ABSENT` | Bỏ property Optional.empty | Bỏ property null |
| `NON_EMPTY` | Có thể bỏ giá trị được xem là empty theo serializer | Bỏ property null |

Với mục tiêu cụ thể là không xuất Optional.empty, `NON_ABSENT` diễn đạt đúng ý định hơn `NON_NULL`.

Không nên dựa vào việc Optional là object non-null để suy ra JSON sẽ luôn có string. Serializer của module xử lý Optional.empty như giá trị absent và có thể ghi null hoặc loại bỏ tùy inclusion.

## 5. Deserialize JSON thành Optional

Khi có `Jdk8Module`, Jackson có thể đọc giá trị JSON bên trong thành kiểu Optional tương ứng.

### 5.1. JSON có giá trị

Ví dụ:

```json
{
  "id": 42,
  "username": "an",
  "nickname": "Annie"
}
```

Deserialize:

```java
UserResponse user = mapper.readValue(json, UserResponse.class);

String nickname = user.nickname().orElse("No nickname");
```

Property string được ánh xạ thành `Optional.of("Annie")`.

### 5.2. JSON có explicit null

Payload:

```json
{
  "id": 43,
  "username": "binh",
  "nickname": null
}
```

Với Jdk8Module, giá trị null của property Optional thông thường được biểu diễn thành Optional.empty, theo null handling của module và mapper.

```java
if (user.nickname().isEmpty()) {
    // Không có nickname khả dụng.
}
```

Điều này có nghĩa Optional thông thường không giữ được thông tin rằng property đã xuất hiện rõ ràng với null hay không xuất hiện. Nếu nghiệp vụ cần phân biệt hai trạng thái đó, phải giữ thông tin presence ở một lớp khác.

### 5.3. JSON không có property

Payload:

```json
{
  "id": 44,
  "username": "chi"
}
```

Với JavaBean mutable, khi property không xuất hiện, Jackson thường không gọi setter tương ứng. Giá trị cuối cùng vì thế có thể là giá trị khởi tạo của field, hoặc null nếu không khởi tạo.

Với constructor-based DTO hoặc record, giá trị property bị thiếu được xử lý theo cơ chế creator parameter và cấu hình absent/null của Jackson. Không nên giả định mọi kiểu DTO đều tự nhận Optional.empty khi field vắng mặt. Hãy khởi tạo mặc định hoặc kiểm thử đúng kiểu DTO và phiên bản Jackson đang sử dụng.

Ví dụ JavaBean có giá trị mặc định rõ ràng:

```java
public class UserRequest {
    private Optional<String> nickname = Optional.empty();

    public Optional<String> getNickname() {
        return nickname;
    }

    public void setNickname(Optional<String> nickname) {
        this.nickname = nickname;
    }
}
```

Nếu field không xuất hiện và setter không được gọi, field vẫn giữ `Optional.empty()` đã khởi tạo.

### 5.4. Bật cấu hình đọc absent như null

`Jdk8Module` có tùy chọn liên quan đến cách xử lý absent value khi deserialize, tùy phiên bản module. Một số phiên bản cung cấp cấu hình `configureReadAbsentAsNull` để yêu cầu absent value được xử lý như null thay vì giá trị absent mặc định.

Ví dụ với API module hỗ trợ tùy chọn này:

```java
Jdk8Module module = new Jdk8Module()
    .configureReadAbsentAsNull(true);

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Hãy xem Javadoc đúng phiên bản Jackson đang dùng trước khi bật tùy chọn này, vì nó ảnh hưởng tới ý nghĩa của property bị thiếu. Với DTO patch, thay đổi absent thành null có thể làm mất khả năng phân biệt “không gửi field” và “gửi null”.

## 6. Optional và ba trạng thái của thuộc tính

Đây là phần quan trọng khi thiết kế API cập nhật.

Giả sử một endpoint cập nhật nickname:

- Client gửi `{"nickname":"Annie"}`: đặt nickname thành Annie.
- Client gửi `{"nickname":null}`: xóa nickname.
- Client bỏ hẳn property nickname: giữ nguyên nickname hiện tại.

Một `Optional<String>` thông thường chỉ biểu diễn hai trạng thái:

- Có giá trị: `Optional.of("Annie")`.
- Không có giá trị: `Optional.empty()`.

Nó không giữ riêng thông tin presence của JSON property. Explicit null và missing có thể cùng trở thành Optional.empty tùy cách deserialize. Vì vậy, không nên dùng Optional đơn lẻ khi logic patch cần ba trạng thái.

### 6.1. Kiểm tra presence bằng JsonNode

Có thể đọc request thành tree trước:

```java
JsonNode root = mapper.readTree(json);

if (!root.has("nickname")) {
    // Không gửi nickname: giữ nguyên.
} else if (root.get("nickname").isNull()) {
    // Gửi null: xóa nickname.
} else {
    String nickname = root.get("nickname").asText();
    // Gán nickname mới.
}
```

`has("nickname")` kiểm tra property có xuất hiện hay không. Nếu property tồn tại với JSON null, `has` vẫn trả true; kiểm tra tiếp `isNull()` để phân biệt.

Có thể đóng gói thành helper để tránh lặp logic trong nhiều endpoint.

### 6.2. Dùng kiểu biểu diễn ba trạng thái

Với API patch phức tạp, có thể tạo một kiểu riêng biểu diễn:

```java
public sealed interface FieldUpdate<T> {

    record Unspecified<T>() implements FieldUpdate<T> {}

    record Clear<T>() implements FieldUpdate<T> {}

    record SetValue<T>(T value) implements FieldUpdate<T> {}
}
```

Ý nghĩa:

| Trạng thái | Hành động |
| --- | --- |
| `Unspecified` | Giữ giá trị hiện tại |
| `Clear` | Xóa giá trị |
| `SetValue(value)` | Đặt giá trị mới |

Jackson không tự biết quy ước của kiểu custom này nếu chưa có deserializer hoặc lớp chuyển đổi phù hợp. Có thể viết custom deserializer, dùng JsonNode để chuyển đổi ở service boundary, hoặc sử dụng một thư viện wrapper nullable có module Jackson tương ứng.

Điểm quan trọng là mô hình Java phải giữ được thông tin presence nếu nghiệp vụ cần nó.

### 6.3. So sánh Optional, nullable và JsonNode

| Mô hình | Có giá trị | Null rõ ràng | Missing rõ ràng |
| --- | --- | --- | --- |
| Kiểu Java nullable như String | Có | Có thể là Java null | Không tự phân biệt sau mapping thông thường |
| Optional<T> | Có | Thường được gộp vào empty khi deserialize | Không tự phân biệt với empty/null |
| JsonNode | Có node giá trị | Có NullNode | Có thể nhận diện MissingNode/không có property |
| Kiểu FieldUpdate<T> tùy chỉnh | Có | Có thể biểu diễn Clear riêng | Có thể biểu diễn Unspecified riêng |

Chọn mô hình theo ngữ nghĩa API. Optional phù hợp khi chỉ cần có/không có giá trị. JsonNode hoặc wrapper ba trạng thái phù hợp khi presence là thông tin nghiệp vụ.

## 7. Optional lồng với generic và collection

Optional có thể xuất hiện bên trong kiểu generic phức tạp. Jdk8Module cung cấp serializer/deserializer cho Optional; Jackson Databind tiếp tục xử lý các kiểu lồng bên trong theo kiểu được khai báo.

### 7.1. Optional chứa object

```java
public record UserSummary(
    long id,
    String username
) {}

public record SearchResult(
    Optional<UserSummary> featuredUser
) {}
```

JSON khi có object:

```json
{
  "featuredUser": {
    "id": 42,
    "username": "an"
  }
}
```

Jackson đọc object thành `UserSummary` rồi bọc vào Optional.

### 7.2. Optional chứa List

```java
public record SearchResult(
    Optional<List<UserSummary>> users
) {}
```

Giá trị có dữ liệu:

```json
{
  "users": [
    {"id": 42, "username": "an"},
    {"id": 43, "username": "binh"}
  ]
}
```

`Optional<List<UserSummary>>` phân biệt một danh sách có mặt với một Optional không có danh sách. Tuy nhiên, khi danh sách rỗng, đó vẫn là một giá trị có mặt: `Optional.of(List.of())`. Nó khác `Optional.empty()`.

| Giá trị Java | Ý nghĩa |
| --- | --- |
| `Optional.empty()` | Không có danh sách |
| `Optional.of(List.of())` | Có danh sách, nhưng danh sách rỗng |
| `Optional.of(List.of(user))` | Có danh sách với phần tử |

### 7.3. List chứa Optional

Cũng có thể khai báo:

```java
List<Optional<String>> aliases;
```

Kiểu này biểu diễn mỗi vị trí có thể có hoặc không có giá trị. Nhưng JSON array có thể chứa null trực tiếp, và cách mô hình này thường làm code phức tạp hơn. Hãy chỉ dùng khi mỗi phần tử thực sự có ngữ nghĩa presence riêng.

### 7.4. Optional primitive

Module JDK 8 hỗ trợ các kiểu:

- `OptionalInt`
- `OptionalLong`
- `OptionalDouble`

Ví dụ:

```java
public record Metrics(
    OptionalInt retryCount,
    OptionalLong elapsedMillis,
    OptionalDouble confidence
) {}
```

Các kiểu này tránh boxing thành `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>` trong Java API. Khi dùng với Jackson, vẫn cần đăng ký `Jdk8Module` và kiểm tra hình dạng JSON trong test.

Không dùng OptionalDouble cho dữ liệu tài chính cần chính xác thập phân; hãy dùng Optional<BigDecimal> nếu cần giữ precision.

## 8. Kiểm soát inclusion cho Optional

Inclusion rule quyết định property nào được ghi ra JSON. Với Optional, cần hiểu khác biệt giữa Optional.empty, Java null và Optional có giá trị.

### 8.1. Inclusion theo property

```java
public record UserResponse(
    long id,
    @JsonInclude(JsonInclude.Include.NON_ABSENT)
    Optional<String> nickname
) {}
```

Khi nickname là Optional.empty, property bị loại khỏi JSON. Khi nickname có giá trị, property được ghi. Khi component Java là null thay vì một Optional, NON_ABSENT cũng loại giá trị đó.

### 8.2. Inclusion cho nội dung bên trong

`JsonInclude` còn có thuộc tính `content` để điều khiển inclusion của nội dung container/map. Với Optional, hành vi cụ thể phụ thuộc serializer/module và phiên bản. Nếu cần kiểm soát một quy tắc phức tạp, hãy kiểm thử JSON output thay vì suy luận chỉ từ tên inclusion.

### 8.3. Tránh tạo Optional null

Một field khai báo kiểu Optional nhưng bản thân field lại là Java null sẽ làm mất mục tiêu biểu diễn rõ ràng của Optional:

```java
Optional<String> nickname = null; // Không nên
```

Hãy giữ invariant rằng Optional reference luôn là một object Optional, có thể empty hoặc chứa giá trị:

```java
Optional<String> nickname = Optional.empty();
```

Với constructor/record, bảo đảm nơi tạo object không truyền Java null vào component Optional nếu hợp đồng yêu cầu Optional.empty. Có thể kiểm tra trong compact constructor:

```java
public record UserResponse(
    long id,
    Optional<String> nickname
) {
    public UserResponse {
        nickname = Objects.requireNonNull(nickname);
    }
}
```

Nếu muốn chuẩn hóa Java null thành empty, có thể dùng `Optional.ofNullable` ở ranh giới tạo DTO, nhưng không nên âm thầm thay đổi dữ liệu nếu null mang ý nghĩa riêng.

## 9. Lỗi thường gặp khi dùng Optional với Jackson

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Jackson serialize Optional như object hoặc báo lỗi | Chưa đăng ký Jdk8Module hoặc mapper đang dùng thiếu module | Thêm jackson-datatype-jdk8 và đăng ký module trên đúng mapper |
| Optional.empty xuất hiện thành null dù muốn bỏ field | Inclusion đang là ALWAYS hoặc rule không phù hợp | Dùng NON_ABSENT ở property/type |
| Dùng NON_NULL nhưng Optional.empty vẫn được ghi | Optional.empty là object Optional không phải Java null | Dùng NON_ABSENT |
| Field không xuất hiện nhưng component Optional không như mong đợi | Creator/record/mutable bean xử lý absent khác nhau | Kiểm tra constructor, giá trị khởi tạo và module version |
| Không phân biệt explicit null với missing | Optional gộp các trạng thái không có giá trị | Dùng JsonNode hoặc wrapper ba trạng thái |
| Spring Boot endpoint không giống test mapper | Hai mapper có module/configuration khác nhau | Test bằng mapper bean và HTTP converter thực tế |
| Optional có giá trị nhưng JSON sai kiểu | Kiểu generic hoặc DTO bên trong không phù hợp | Kiểm tra type signature và JSON payload |
| Optional field Java bị null | Code khởi tạo/truyền null thay vì Optional.empty | Chuẩn hóa invariant ở constructor/factory |

Khi debug, hãy kiểm tra theo thứ tự:

1. Mapper thực tế đã đăng ký `Jdk8Module` chưa?
2. Runtime classpath có đúng artifact/version không?
3. Property đang serialize hay deserialize?
4. JSON gửi giá trị, null hay không gửi property?
5. Inclusion rule có phải `NON_ABSENT` không?
6. DTO là mutable bean, constructor-based class hay record?
7. Nghiệp vụ có cần phân biệt missing với explicit null không?

## 10. Kiểm thử Optional với Jackson

Một test nên xác nhận module đã unwrap Optional và round-trip đúng.

### 10.1. Test Optional có giá trị

```java
class OptionalMappingTest {

    private final ObjectMapper mapper = new ObjectMapper()
        .registerModule(new Jdk8Module());

    @Test
    void serializesPresentOptionalAsItsValue() throws Exception {
        UserResponse user = new UserResponse(
            42L,
            "an",
            Optional.of("Annie")
        );

        String json = mapper.writeValueAsString(user);

        assertTrue(json.contains("\"nickname\":\"Annie\""));
    }
}
```

### 10.2. Test Optional.empty mặc định

```java
@Test
void serializesEmptyOptionalAsJsonNullByDefault() throws Exception {
    UserResponse user = new UserResponse(
        43L,
        "binh",
        Optional.empty()
    );

    String json = mapper.writeValueAsString(user);

    JsonNode root = mapper.readTree(json);
    assertTrue(root.has("nickname"));
    assertTrue(root.get("nickname").isNull());
}
```

Test này minh họa hành vi mặc định khi không áp dụng NON_ABSENT. Nếu DTO có inclusion annotation, kết quả cần được kiểm tra theo annotation đó.

### 10.3. Test NON_ABSENT

```java
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record CompactUserResponse(
    long id,
    Optional<String> nickname
) {}

@Test
void omitsEmptyOptionalWithNonAbsent() throws Exception {
    CompactUserResponse user = new CompactUserResponse(
        43L,
        Optional.empty()
    );

    String json = mapper.writeValueAsString(user);
    JsonNode root = mapper.readTree(json);

    assertFalse(root.has("nickname"));
}
```

### 10.4. Test deserialize giá trị và null

```java
@Test
void readsPresentOptional() throws Exception {
    UserResponse user = mapper.readValue(
        """
        {"id": 42, "username": "an", "nickname": "Annie"}
        """,
        UserResponse.class
    );

    assertEquals(Optional.of("Annie"), user.nickname());
}

@Test
void readsExplicitNullAsEmptyOptional() throws Exception {
    UserResponse user = mapper.readValue(
        """
        {"id": 43, "username": "binh", "nickname": null}
        """,
        UserResponse.class
    );

    assertTrue(user.nickname().isEmpty());
}
```

Hãy bổ sung test riêng cho property bị thiếu trên đúng loại DTO mà ứng dụng dùng. Với record, JavaBean có initializer và constructor thông thường, hành vi absent có thể khác nhau; test cần phản ánh cấu hình thực tế chứ không dựa trên giả định chung.

## 11. Thiết kế API cập nhật với Optional

Với endpoint tạo mới, một Optional có thể phù hợp để biểu diễn field không bắt buộc:

```java
public record CreateProfileRequest(
    String username,
    Optional<String> nickname
) {}
```

Tuy nhiên, với endpoint patch, cần xác định rõ missing và null có hành vi khác nhau không.

Một bảng hợp đồng ví dụ:

| Request JSON | Hành động |
| --- | --- |
| `{}` | Không thay đổi nickname |
| `{"nickname": null}` | Xóa nickname |
| `{"nickname": "Annie"}` | Đặt nickname thành Annie |

Nếu chỉ deserialize vào Optional, hai trường hợp đầu có thể cùng trở thành empty. Vì vậy, hãy đọc JsonNode hoặc dùng wrapper có trạng thái presence rõ ràng trước khi cập nhật entity.

Đừng để service suy luận ý nghĩa patch từ một Optional.empty duy nhất nếu API cần ba trạng thái. Điều đó dễ dẫn đến việc vô tình xóa dữ liệu hoặc không áp dụng thay đổi mà client đã yêu cầu.

## 12. Bài thực hành tổng hợp

Xây dựng một API hồ sơ người dùng với field nickname tùy chọn:

1. Khai báo dependency `jackson-datatype-jdk8` theo build tool của dự án.
2. Đăng ký `Jdk8Module` trong mapper Java độc lập.
3. Tạo record `UserResponse` có component `Optional<String> nickname`.
4. Serialize Optional.of("Annie") và quan sát JSON string.
5. Serialize Optional.empty và quan sát JSON null mặc định.
6. Thêm `@JsonInclude(NON_ABSENT)` và xác nhận property bị bỏ khỏi output.
7. Deserialize JSON có nickname string và kiểm tra Optional.of.
8. Deserialize JSON có nickname null và kiểm tra Optional.empty.
9. Thử payload không có nickname với record và JavaBean có initializer; ghi nhận hành vi trên phiên bản Jackson thực tế.
10. Viết test Spring Boot dùng mapper bean thật để xác nhận module được đăng ký.
11. Thiết kế PATCH payload cần phân biệt missing, null và giá trị cụ thể; dùng JsonNode hoặc wrapper ba trạng thái.
12. Kiểm tra validation để bảo đảm field bắt buộc không bị xem là hợp lệ chỉ vì được bọc trong Optional.

Bài thực hành hoàn thành khi có thể giải thích Optional được biểu diễn thành JSON ra sao, module nào chịu trách nhiệm mapping, inclusion ảnh hưởng output thế nào và khi nào Optional không đủ để giữ ý nghĩa của payload.

## 13. Nguyên tắc ghi nhớ

- Optional biểu diễn có hoặc không có một giá trị trong Java; JSON không có kiểu Optional riêng.
- Jackson 2.x dùng artifact `jackson-datatype-jdk8` và `Jdk8Module` để hỗ trợ Optional.
- Đăng ký module trên đúng ObjectMapper mà ứng dụng thực sự dùng.
- Optional có giá trị thường được serialize thành giá trị bên trong; Optional.empty mặc định thường thành JSON null.
- Dùng `JsonInclude.Include.NON_ABSENT` khi muốn bỏ qua Optional.empty trong output.
- `NON_NULL` và `NON_ABSENT` có ý nghĩa khác nhau; Optional.empty không phải Java null.
- JSON property missing khác explicit null, nhưng Optional thông thường không giữ riêng hai trạng thái này sau mapping.
- Với PATCH cần ba trạng thái, dùng JsonNode hoặc wrapper presence-aware.
- Kiểm tra absent property riêng cho record, constructor-based DTO và JavaBean có initializer.
- Optional không thay thế validation và không nên được dùng để che giấu quy tắc null/missing chưa được định nghĩa.

Khi biểu diễn thuộc tính tùy chọn, hãy xác định rõ hợp đồng cần có/không có giá trị hay cần phân biệt missing với null. Sau đó cấu hình Jdk8Module, inclusion rule và kiểu DTO phù hợp, rồi xác nhận hành vi bằng test trên mapper thực tế.
