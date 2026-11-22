# Áp dụng JsonInclude cho giá trị null, rỗng và mặc định

Khi serialize một object Java thành JSON, Jackson có thể đưa mọi thuộc tính vào output, kể cả thuộc tính đang có giá trị `null`, chuỗi rỗng, collection rỗng hoặc giá trị mặc định như `0` và `false`. Trong nhiều API, ta muốn bỏ một số giá trị để JSON gọn hơn hoặc để thể hiện đúng hợp đồng dữ liệu.

Jackson cung cấp annotation **`@JsonInclude`** để quy định khi nào một thuộc tính được đưa vào JSON. Annotation này có thể áp dụng ở cấp lớp hoặc từng thuộc tính; cấu hình của `ObjectMapper` cũng có thể đặt chính sách mặc định cho toàn ứng dụng. Ngoài việc quyết định có xuất một property hay không, Jackson còn cho phép quy định cách lọc các phần tử bên trong collection, array hoặc Map.

Điểm quan trọng là phải phân biệt rõ `null`, giá trị rỗng và giá trị mặc định. Chúng không đồng nghĩa với nhau, và mỗi chế độ `JsonInclude.Include` có tiêu chí riêng.

## 1. JsonInclude dùng để làm gì?

`@JsonInclude` thuộc Jackson Annotations. Nó điều khiển việc **serialize**: một property hoặc nội dung bên trong property có được ghi vào JSON hay không.

Ví dụ, một DTO có nhiều thuộc tính tùy chọn:

```java
public class Profile {
    private String name;
    private String nickname;
    private List<String> roles;
    private Integer age;
    private boolean active;

    // Constructor, getter và setter
}
```

Nếu `nickname` là `null`, `roles` là list rỗng, `age` là `null` và `active` là `false`, output mặc định có thể chứa tất cả các thuộc tính đó:

```json
{
  "name": "An",
  "nickname": null,
  "roles": [],
  "age": null,
  "active": false
}
```

Nếu muốn bỏ thuộc tính null, có thể đặt:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Profile {
    // Các thuộc tính và accessor
}
```

Khi đó, `nickname` và `age` không xuất hiện trong JSON. `roles` vẫn là `[]` và `active` vẫn là `false`, vì hai giá trị này không phải null.

### 1.1. JsonInclude chỉ điều khiển output

`@JsonInclude` là quy tắc serialize. Nó không tự quy định cách deserialize khi JSON đầu vào thiếu field hoặc có giá trị `null`.

Ví dụ, nếu `nickname` bị bỏ khỏi JSON do `NON_NULL`, khi đọc JSON đó trở lại, Jackson không tự suy ra rằng `nickname` phải nhận một giá trị mặc định nghiệp vụ. Hành vi khi field bị thiếu còn phụ thuộc constructor, setter, giá trị khởi tạo của field và cấu hình deserialize.

Nếu cần quy định cách xử lý `null` khi đọc JSON, hãy tìm hiểu `@JsonSetter`, `Nulls`, creator properties và các `DeserializationFeature` tương ứng. Không nên dùng `@JsonInclude` như một cơ chế validation hoặc defaulting cho input.

## 2. Các chế độ JsonInclude.Include

`JsonInclude.Include` cung cấp những chế độ thường dùng sau:

| Chế độ | Điều kiện đưa property vào JSON |
|---|---|
| `ALWAYS` | Luôn đưa vào, kể cả khi giá trị là `null` hoặc rỗng. |
| `NON_NULL` | Chỉ đưa vào khi giá trị không phải `null`. |
| `NON_ABSENT` | Bỏ giá trị null hoặc absent, đặc biệt hữu ích với kiểu tham chiếu như `Optional`. |
| `NON_EMPTY` | Bỏ null, absent và giá trị rỗng như chuỗi rỗng, array rỗng, collection rỗng hoặc Map rỗng. |
| `NON_DEFAULT` | Bỏ giá trị được xem là mặc định theo quy tắc của Jackson. |
| `CUSTOM` | Dùng filter tùy chỉnh để quyết định giá trị nào bị loại. |
| `USE_DEFAULTS` | Dùng chính sách mặc định từ cấp cấu hình cao hơn. |

### 2.1. ALWAYS: luôn xuất thuộc tính

`ALWAYS` là chế độ mặc định phổ biến khi không có chính sách inclusion khác. Giá trị null vẫn được biểu diễn thành JSON `null`:

```java
@JsonInclude(JsonInclude.Include.ALWAYS)
private String middleName;
```

Ví dụ output:

```json
{
  "middleName": null
}
```

Chế độ này hữu ích khi hợp đồng API yêu cầu key luôn hiện diện, kể cả khi chưa có dữ liệu. Một số client phân biệt rõ giữa key không xuất hiện và key xuất hiện với giá trị `null`.

### 2.2. NON_NULL: bỏ giá trị null

`NON_NULL` chỉ kiểm tra giá trị property có phải `null` hay không:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String name;
    private String avatarUrl;
    private Integer age;

    // Constructor, getter và setter
}
```

Nếu `avatarUrl` và `age` là null, chúng bị bỏ khỏi output. Nhưng chuỗi `""`, list `[]`, số `0` và boolean `false` vẫn được xuất.

Ví dụ:

```json
{
  "name": "An",
  "avatarUrl": "",
  "age": 0
}
```

Đây là lựa chọn phù hợp khi muốn bỏ các field chưa có dữ liệu nhưng vẫn giữ nguyên giá trị rỗng hoặc giá trị false/zero có ý nghĩa.

### 2.3. NON_ABSENT: bỏ null và giá trị absent

`NON_ABSENT` mở rộng ý nghĩa của `NON_NULL` cho các kiểu tham chiếu có trạng thái absent. Một ví dụ điển hình là `Optional` khi ứng dụng dùng module hỗ trợ kiểu JDK 8:

```java
public class UserResponse {
    @JsonInclude(JsonInclude.Include.NON_ABSENT)
    private Optional<String> nickname;

    // Constructor, getter và setter
}
```

Với module hỗ trợ Optional, `Optional.empty()` được xem là absent và có thể bị bỏ khỏi JSON. `Optional.of("An")` vẫn được serialize thành giá trị tương ứng.

Để Jackson xử lý các kiểu JDK 8 như `Optional`, ứng dụng cần module phù hợp, thường là `jackson-datatype-jdk8`:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new Jdk8Module());
```

Trong ứng dụng framework, hãy dùng mapper đã được framework cấu hình và kiểm tra module đã có trong runtime. `NON_ABSENT` không có nghĩa là mọi giá trị rỗng đều bị bỏ; một chuỗi rỗng hoặc collection rỗng không tự động trở thành absent.

### 2.4. NON_EMPTY: bỏ giá trị rỗng

`NON_EMPTY` bỏ các giá trị được Jackson xem là rỗng. Những trường hợp thường gặp gồm:

- `null`.
- Giá trị absent, chẳng hạn `Optional.empty()` khi có module hỗ trợ.
- Chuỗi có độ dài bằng 0 (`""`).
- Array có độ dài bằng 0.
- Collection không có phần tử.
- Map không có entry.

Ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class SearchResponse {
    private String keyword;
    private List<String> results;
    private Map<String, String> metadata;
    private String description;

    // Constructor, getter và setter
}
```

Nếu `keyword` là `""`, `results` là list rỗng, `metadata` là map rỗng và `description` là null, các thuộc tính này bị loại khỏi output.

`NON_EMPTY` không có nghĩa là bỏ mọi giá trị được xem là “không có ích” theo nghiệp vụ. Ví dụ:

| Giá trị | Có bị loại bởi `NON_EMPTY` không? |
|---|---|
| `null` | Có |
| `""` | Có |
| `"   "` | Không, đây vẫn là chuỗi có ký tự |
| `0` | Không |
| `false` | Không |
| `new int[0]` | Có |
| `List.of()` | Có |
| `Map.of()` | Có |
| List có một phần tử | Không |

Đặc biệt, chuỗi chỉ chứa dấu cách như `"   "` vẫn không rỗng theo nghĩa kỹ thuật. Nếu muốn trim hoặc bỏ chuỗi chỉ có whitespace, hãy chuẩn hóa dữ liệu ở tầng phù hợp hoặc dùng filter tùy chỉnh.

Ở các phiên bản Jackson hiện đại, `NON_EMPTY` tập trung vào null/absent và các container/string rỗng. Không nên dùng nó với kỳ vọng tự loại `0` hoặc `false`; nếu cần bỏ giá trị mặc định, hãy xem `NON_DEFAULT`.

### 2.5. NON_DEFAULT: bỏ giá trị mặc định

`NON_DEFAULT` dùng để loại giá trị được xem là mặc định. Các giá trị mặc định Java thường gặp:

| Kiểu | Giá trị mặc định |
|---|---|
| `boolean` | `false` |
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `char` | `\u0000` |
| Kiểu tham chiếu | `null` |

Ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_DEFAULT)
public class FeatureSettings {
    private boolean enabled;
    private int retryCount;
    private String label;

    // Constructor, getter và setter
}
```

Nếu `enabled` là `false`, `retryCount` là `0` và `label` là null, các thuộc tính này có thể bị bỏ khỏi JSON. Khi `enabled` là true hoặc `retryCount` lớn hơn 0, chúng được đưa vào.

**Lưu ý về phạm vi áp dụng:** `NON_DEFAULT` ở cấp lớp có thể xác định default bằng cách tạo một instance mặc định của POJO rồi so sánh giá trị thuộc tính với instance đó. Nhờ vậy, giá trị khởi tạo riêng trong lớp cũng có thể được xem là mặc định:

```java
@JsonInclude(JsonInclude.Include.NON_DEFAULT)
public class RetryPolicy {
    private int maxAttempts = 3;
    private boolean enabled = true;

    public RetryPolicy() {
    }

    // Getter và setter
}
```

Nếu một instance có `maxAttempts = 3` và `enabled = true`, các giá trị đó có thể bị bỏ vì trùng với giá trị trên instance mặc định. Cách xác định default ở cấp lớp phụ thuộc khả năng tạo instance mặc định và cấu trúc POJO.

Khi `NON_DEFAULT` được đặt ở phạm vi global hoặc trên một property riêng lẻ, Jackson so sánh với default theo kiểu dữ liệu (ví dụ null, zero, false), không nhất thiết dùng giá trị khởi tạo tùy chỉnh của một instance khác. Vì thế, cần phân biệt nơi đặt annotation khi muốn loại một giá trị mặc định do nghiệp vụ định nghĩa.

Nếu lớp không có constructor mặc định hoặc việc tạo instance mặc định có tác dụng phụ, không nên dựa vào cơ chế so sánh default ở cấp lớp mà chưa xác nhận hành vi của phiên bản Jackson đang dùng. Có thể dùng filter tùy chỉnh hoặc biểu diễn default rõ ràng ở tầng model.

### 2.6. CUSTOM: định nghĩa điều kiện loại riêng

Khi các chế độ chuẩn không đáp ứng được quy tắc nghiệp vụ, có thể dùng `CUSTOM` với `valueFilter`. Jackson tạo filter và dùng `equals()` để xác định giá trị nào bị loại.

Ví dụ, ứng dụng muốn bỏ `retryCount` khi giá trị bằng `0`:

```java
public class ZeroFilter {
    @Override
    public boolean equals(Object other) {
        return Integer.valueOf(0).equals(other);
    }
}

public class JobStatus {
    @JsonInclude(
        value = JsonInclude.Include.CUSTOM,
        valueFilter = ZeroFilter.class
    )
    private Integer retryCount;

    // Getter và setter
}
```

Nếu `retryCount` bằng 0, filter trả về true khi so sánh và Jackson loại property. Nếu giá trị khác 0, property được giữ lại. Filter nên không có mutable state và có hành vi `equals()` rõ ràng, ổn định.

`CUSTOM` cũng hỗ trợ `contentFilter` để lọc phần tử hoặc value bên trong container. Cần chọn `valueFilter` hay `contentFilter` tùy muốn loại cả property hay chỉ loại các giá trị con.

### 2.7. USE_DEFAULTS: kế thừa chính sách ở cấp khác

`USE_DEFAULTS` yêu cầu Jackson dùng chính sách inclusion từ cấu hình mặc định hoặc cấp cấu hình bao quanh. Nó hữu ích khi một property hoặc lớp muốn quay lại chính sách đã được cấu hình chung.

Ví dụ, mapper đặt mặc định `NON_NULL`, nhưng một property cần dùng chính sách mặc định kế thừa:

```java
@JsonInclude(JsonInclude.Include.USE_DEFAULTS)
private String optionalNote;
```

`USE_DEFAULTS` không có nghĩa là `ALWAYS`; nó có nghĩa là không tự đặt một chính sách inclusion riêng tại vị trí đó.

## 3. Phân biệt value inclusion và content inclusion

`@JsonInclude` có hai thuộc tính quan trọng:

- `value`: quyết định có đưa chính property vào JSON hay không.
- `content`: quyết định có giữ các giá trị nằm bên trong property hay không, chẳng hạn phần tử của collection/array hoặc value của Map.

Hai chính sách này độc lập. Một list có thể không rỗng nên property được xuất, nhưng vẫn có phần tử null cần loại bỏ.

### 3.1. Loại cả collection khi rỗng

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
private List<String> tags;
```

Nếu `tags` là null hoặc list rỗng, key `tags` bị bỏ. Nếu list có phần tử, property được giữ lại.

### 3.2. Giữ collection nhưng lọc phần tử null

```java
@JsonInclude(
    value = JsonInclude.Include.ALWAYS,
    content = JsonInclude.Include.NON_NULL
)
private List<String> tags;
```

Với dữ liệu:

```java
tags = Arrays.asList("java", null, "jackson");
```

Jackson giữ property và loại phần tử null trong nội dung collection. Output có dạng:

```json
{
  "tags": ["java", "jackson"]
}
```

Nếu list rỗng, key vẫn được xuất thành `"tags": []` vì `value` là `ALWAYS`.

### 3.3. Kết hợp bỏ container rỗng và lọc phần tử null

```java
@JsonInclude(
    value = JsonInclude.Include.NON_EMPTY,
    content = JsonInclude.Include.NON_NULL
)
private List<String> tags;
```

Kết quả:

| Giá trị Java | JSON |
|---|---|
| `null` | Bỏ key `tags` |
| List rỗng | Bỏ key `tags` |
| `Arrays.asList("java", null)` | `"tags": ["java"]` |
| `List.of("java", "jackson")` | `"tags": ["java", "jackson"]` |

Đối với Map, `content` áp dụng lên value của entry, không phải key:

```java
@JsonInclude(
    value = JsonInclude.Include.NON_EMPTY,
    content = JsonInclude.Include.NON_NULL
)
private Map<String, String> metadata;
```

Map rỗng bị bỏ; entry có value null bị lọc; key có value khác null được giữ lại.

## 4. Đặt JsonInclude ở những phạm vi khác nhau

Jackson cho phép đặt chính sách inclusion ở nhiều cấp. Cần chọn phạm vi phù hợp để tránh cấu hình quá rộng.

### 4.1. Cấp thuộc tính

Đặt annotation trực tiếp trên field hoặc accessor khi chỉ một property cần chính sách riêng:

```java
public class UserResponse {
    private String name;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    private String nickname;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String avatarUrl;
}
```

Phạm vi property phù hợp khi mỗi field có ý nghĩa khác nhau. Ví dụ nickname rỗng thì không cần hiển thị, nhưng avatar URL chỉ cần bỏ khi null.

### 4.2. Cấp lớp

Đặt annotation trên class để áp dụng chính sách mặc định cho các property của lớp:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String name;
    private String nickname;
    private String avatarUrl;

    @JsonInclude(JsonInclude.Include.ALWAYS)
    private String statusMessage;
}
```

Các property thông thường tuân theo chính sách cấp lớp. `statusMessage` có chính sách riêng để luôn xuất hiện, kể cả null. Khi có nhiều cấp cấu hình, hãy kiểm tra annotation cụ thể và cấu hình mapper để xác nhận chính sách hiệu lực.

### 4.3. Cấp ObjectMapper cho toàn ứng dụng

Có thể cấu hình inclusion mặc định trên mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.setDefaultPropertyInclusion(
    JsonInclude.Value.construct(
        JsonInclude.Include.NON_NULL,
        JsonInclude.Include.ALWAYS
    )
);
```

Tham số thứ nhất là value inclusion mặc định; tham số thứ hai là content inclusion mặc định. Trong ví dụ, property null bị bỏ, còn nội dung collection/Map không bị lọc theo chính sách content mặc định.

Trong ứng dụng framework, hãy cấu hình mapper ở giai đoạn khởi tạo hoặc dùng cơ chế cấu hình Jackson do framework cung cấp. Tránh thay đổi mapper dùng chung sau khi nó đã bắt đầu serialize/deserialize.

### 4.4. Cấu hình riêng cho một kiểu Java

Nếu muốn áp dụng chính sách cho một kiểu cụ thể mà không gắn annotation vào lớp, có thể dùng `configOverride`:

```java
mapper.configOverride(AuditEvent.class)
    .setInclude(
        JsonInclude.Value.construct(
            JsonInclude.Include.NON_EMPTY,
            JsonInclude.Include.ALWAYS
        )
    );
```

Cách này hữu ích khi không sở hữu source class hoặc muốn giữ model độc lập với cấu hình JSON. Hãy cấu hình override trước khi mapper được sử dụng và tránh tạo các quy tắc mâu thuẫn giữa annotation, type override và default inclusion.

## 5. Ví dụ tổng hợp

Giả sử API trả về thông tin hồ sơ, trong đó:

- Field null không cần xuất.
- Chuỗi rỗng và collection rỗng không cần xuất.
- `false` là một giá trị nghiệp vụ có ý nghĩa nên vẫn phải xuất.
- Các phần tử null trong danh sách tag cần được bỏ.
- Trường `status` phải luôn hiện diện để client biết trạng thái xử lý.

Có thể mô hình hóa như sau:

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class ProfileResponse {
    private String name;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    private String nickname;

    @JsonInclude(
        value = JsonInclude.Include.NON_EMPTY,
        content = JsonInclude.Include.NON_NULL
    )
    private List<String> tags;

    private boolean active;

    @JsonInclude(JsonInclude.Include.ALWAYS)
    private String status;

    // Constructor, getter và setter
}
```

Với dữ liệu:

```java
ProfileResponse response = new ProfileResponse();
response.setName("An");
response.setNickname("");
response.setTags(Arrays.asList("java", null, "jackson"));
response.setActive(false);
response.setStatus(null);
```

JSON dự kiến:

```json
{
  "name": "An",
  "tags": ["java", "jackson"],
  "active": false,
  "status": null
}
```

Ví dụ này thể hiện sự khác nhau giữa ba khái niệm: `nickname` bị bỏ vì chuỗi rỗng; phần tử null trong `tags` bị lọc bởi `content`; `active=false` vẫn xuất hiện vì `NON_EMPTY` không loại boolean mặc định; `status` vẫn có mặt do chính sách property-level `ALWAYS`.

## 6. Null, thiếu và giá trị mặc định khi deserialize

Khi làm việc với API, cần phân biệt:

1. **Property không có trong JSON:** client không gửi key đó.
2. **Property có giá trị null:** client gửi key với giá trị JSON `null`.
3. **Property có giá trị rỗng:** client gửi `""`, `[]` hoặc `{}`.
4. **Property có giá trị mặc định:** client gửi `0`, `false` hoặc một giá trị mà domain xem là mặc định.

`JsonInclude` chỉ quyết định trường hợp nào được ghi ra output. Khi đọc input, các trường hợp trên có thể có ý nghĩa khác nhau.

Ví dụ, `@JsonSetter` có thể quy định cách xử lý null:

```java
public class UpdateProfileRequest {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }
}
```

Với setter được cấu hình `Nulls.SKIP`, giá trị null từ JSON sẽ không gọi việc gán null vào thuộc tính; giá trị khởi tạo hiện có được giữ lại. Nếu property hoàn toàn không xuất hiện, setter cũng không được gọi và giá trị khởi tạo vẫn còn. Đây là chính sách deserialize, độc lập với `@JsonInclude` khi serialize.

Một số giá trị `Nulls` thường gặp:

| Giá trị | Ý nghĩa khi nhận JSON null |
|---|---|
| `SET` | Gán null vào thuộc tính (hành vi thông thường). |
| `SKIP` | Bỏ qua việc gán, giữ giá trị hiện tại/giá trị khởi tạo. |
| `FAIL` | Báo lỗi khi nhận null. |
| `AS_EMPTY` | Chuyển null thành giá trị rỗng theo kiểu đích nếu có thể. |
| `DEFAULT` | Dùng chính sách mặc định của cấu hình. |

Đối với creator-based immutable object, field thiếu hoặc null được xử lý khi Jackson chuẩn bị các tham số creator. Cần xem các feature như `FAIL_ON_MISSING_CREATOR_PROPERTIES`, `FAIL_ON_NULL_CREATOR_PROPERTIES` và `FAIL_ON_NULL_FOR_PRIMITIVES` nếu các giá trị đó bắt buộc.

## 7. Những hiểu lầm thường gặp

**Dùng `NON_NULL` nhưng vẫn thấy `""` hoặc `[]`.** Đây là hành vi đúng: `NON_NULL` chỉ bỏ null. Dùng `NON_EMPTY` nếu muốn bỏ chuỗi, array, collection hoặc Map rỗng.

**Dùng `NON_EMPTY` nhưng vẫn thấy `0` và `false`.** Đây không phải giá trị rỗng theo chính sách hiện đại của Jackson. Nếu muốn bỏ giá trị mặc định, cân nhắc `NON_DEFAULT`.

**Cho rằng chuỗi chỉ có dấu cách là rỗng.** Jackson xem `"   "` là chuỗi có độ dài khác 0. Hãy trim hoặc chuẩn hóa trước khi serialize nếu hợp đồng yêu cầu.

**Cho rằng `NON_EMPTY` loại phần tử null bên trong list.** Inclusion của container và inclusion của content là hai việc khác nhau. Dùng `content = NON_NULL` nếu cần lọc phần tử null.

**Cho rằng `NON_NULL` làm deserializer bỏ qua null.** Annotation này điều khiển output. Muốn xử lý null đầu vào, dùng `@JsonSetter(nulls = ...)` hoặc cấu hình deserialize phù hợp.

**Cho rằng `NON_DEFAULT` luôn so sánh với giá trị khởi tạo của object.** Quy tắc phụ thuộc phạm vi áp dụng. Class-level inclusion có thể so sánh với instance mặc định của POJO; global/property-level inclusion dùng default theo kiểu. Hãy chọn đúng phạm vi và kiểm tra kết quả.

**Đặt inclusion toàn cục mà không xem hợp đồng API.** Bỏ null hoặc giá trị mặc định có thể làm client phân biệt sai giữa “không được cung cấp” và “đã được xác định là null/false/0”. Chính sách cần phù hợp với ý nghĩa của từng field.

## 8. Quy trình chọn chính sách JsonInclude

Khi thiết kế DTO hoặc response JSON, có thể làm theo các bước:

1. **Xác định ý nghĩa của null.** Key null có cần xuất để biểu thị trạng thái chưa có dữ liệu không?
2. **Xác định ý nghĩa của giá trị rỗng.** Chuỗi rỗng, list rỗng và map rỗng có ý nghĩa khác với việc không có key không?
3. **Xác định giá trị mặc định.** `0` hoặc `false` có phải dữ liệu hợp lệ cần giữ không? Có default nghiệp vụ riêng như số lần thử mặc định bằng 3 không?
4. **Chọn chế độ value inclusion.** Dùng `NON_NULL`, `NON_ABSENT`, `NON_EMPTY`, `NON_DEFAULT` hoặc `CUSTOM` theo tiêu chí cụ thể.
5. **Kiểm tra nội dung container.** Nếu cần lọc phần tử null hoặc value null của Map, cấu hình `content` riêng.
6. **Chọn phạm vi.** Đặt ở property nếu chỉ một field cần chính sách riêng; cấp lớp nếu cả DTO dùng chung; mapper/type override nếu đó là quy tắc cấu hình ứng dụng.
7. **Tách serialize và deserialize.** Nếu input có quy tắc null/missing riêng, cấu hình `@JsonSetter`, creator hoặc feature deserialize.
8. **Kiểm tra JSON thực tế.** Dùng đúng mapper của ứng dụng và thử ít nhất null, empty, default, giá trị hợp lệ cùng container có phần tử null.

## Kết luận

`@JsonInclude` giúp kiểm soát property và nội dung nào được xuất trong JSON. `NON_NULL` bỏ null; `NON_ABSENT` xử lý thêm giá trị absent; `NON_EMPTY` bỏ container/string rỗng; `NON_DEFAULT` bỏ giá trị mặc định; còn `CUSTOM` cho phép áp dụng quy tắc nghiệp vụ riêng. Thuộc tính `value` quyết định có xuất cả property hay không, trong khi `content` lọc phần tử hoặc value bên trong container. Khi chọn chính sách, hãy giữ rõ sự khác nhau giữa null, thiếu, rỗng và mặc định, đồng thời nhớ rằng `JsonInclude` điều khiển serialize chứ không quyết định cách deserialize input.
