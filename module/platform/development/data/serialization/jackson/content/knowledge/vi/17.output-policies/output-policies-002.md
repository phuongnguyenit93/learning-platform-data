# Kiểm soát thuộc tính đầu ra bằng JsonInclude

Khi serialize một object Java thành JSON, Jackson cần quyết định thuộc tính nào sẽ xuất hiện trong kết quả. Có API yêu cầu giữ mọi key, kể cả khi giá trị là `null`; API khác muốn bỏ các giá trị chưa có dữ liệu, chuỗi rỗng hoặc collection rỗng. Một số trường hợp còn cần bỏ giá trị mặc định như `0` và `false`, hoặc áp dụng quy tắc riêng cho một kiểu dữ liệu.

Jackson cung cấp annotation **`@JsonInclude`** và các API cấu hình inclusion để điều khiển việc một property có được ghi vào JSON hay không. Chính sách có thể đặt trên từng property, cả lớp, một kiểu Java cụ thể hoặc làm mặc định cho `ObjectMapper`. Với container và kiểu tham chiếu, còn có thể cấu hình riêng cách lọc nội dung bên trong property.

Muốn dùng `JsonInclude` đúng, trước hết cần xác định hợp đồng JSON: key null có cần xuất hiện không, giá trị rỗng có ý nghĩa gì, `0`/`false` có phải dữ liệu hợp lệ không và các phần tử null bên trong collection có được giữ lại không.

## 1. JsonInclude điều khiển điều gì?

`@JsonInclude` thuộc Jackson Annotations. Nó quyết định **điều kiện một thuộc tính được đưa vào JSON khi serialize**.

Ví dụ DTO:

```java
public class UserResponse {
    private String name;
    private String nickname;
    private String avatarUrl;
    private List<String> roles;
    private Integer age;
    private boolean active;

    // Constructor, getter và setter
}
```

Nếu một instance có `nickname = null`, `avatarUrl = ""`, `roles = []`, `age = null` và `active = false`, JSON mặc định có thể chứa:

```json
{
  "name": "An",
  "nickname": null,
  "avatarUrl": "",
  "roles": [],
  "age": null,
  "active": false
}
```

Nếu đặt `NON_NULL`, các property có giá trị null bị bỏ, nhưng chuỗi rỗng, list rỗng và `false` vẫn được xuất. Nếu đặt `NON_EMPTY`, chuỗi/list rỗng cũng có thể bị bỏ. Nếu muốn bỏ `false` hoặc `0`, cần xem `NON_DEFAULT` hoặc một filter riêng.

`JsonInclude` không thay đổi giá trị trong object Java. Nó chỉ ảnh hưởng JSON được tạo ra. Property bị bỏ khỏi output vẫn tồn tại trong object và có thể được dùng trong logic ứng dụng.

## 2. Các chế độ JsonInclude.Include

`JsonInclude.Include` xác định tiêu chí inclusion. Những giá trị thường dùng:

| Chế độ | Khi nào property được xuất? |
|---|---|
| `ALWAYS` | Luôn xuất, kể cả khi null hoặc rỗng. |
| `NON_NULL` | Xuất khi giá trị khác null. |
| `NON_ABSENT` | Bỏ null và giá trị absent của kiểu tham chiếu như `Optional.empty()` khi có module hỗ trợ. |
| `NON_EMPTY` | Bỏ null/absent và giá trị rỗng theo định nghĩa của Jackson/deserializer. |
| `NON_DEFAULT` | Bỏ giá trị được xem là mặc định theo phạm vi cấu hình. |
| `CUSTOM` | Dùng filter tùy chỉnh để xác định giá trị cần bỏ. |
| `USE_DEFAULTS` | Kế thừa chính sách mặc định từ cấu hình áp dụng ở cấp khác. |

### 2.1. ALWAYS: giữ key trong mọi trường hợp

`ALWAYS` là lựa chọn khi hợp đồng API yêu cầu key luôn có mặt, kể cả giá trị null:

```java
public class UserResponse {
    @JsonInclude(JsonInclude.Include.ALWAYS)
    private String middleName;
}
```

Khi `middleName` là null, output vẫn có:

```json
{
  "middleName": null
}
```

Điều này hữu ích khi client cần phân biệt một key được trả về với giá trị null và một key hoàn toàn không xuất hiện.

### 2.2. NON_NULL: chỉ bỏ null

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String name;
    private String nickname;
    private Integer age;
    private boolean active;
}
```

Nếu `nickname` và `age` null, hai key đó không xuất hiện. Nhưng `""`, `0` và `false` vẫn là giá trị khác null nên được ghi.

Ví dụ:

```json
{
  "name": "An",
  "active": false
}
```

`NON_NULL` phù hợp khi chỉ muốn bỏ field không có giá trị mà vẫn giữ nguyên dữ liệu rỗng hoặc giá trị boolean/số có ý nghĩa.

### 2.3. NON_ABSENT: bỏ cả giá trị absent

`NON_ABSENT` bao gồm null và các giá trị absent của kiểu tham chiếu. Trường hợp điển hình là `Optional.empty()` khi ứng dụng đăng ký module JDK 8:

```java
public class UserResponse {
    @JsonInclude(JsonInclude.Include.NON_ABSENT)
    private Optional<String> nickname;

    public Optional<String> getNickname() {
        return nickname;
    }
}
```

Để Jackson xử lý `Optional`, ứng dụng cần module `jackson-datatype-jdk8`:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new Jdk8Module());
```

Với module này, `Optional.empty()` được xem là absent và có thể bị bỏ; `Optional.of("An")` được serialize thành giá trị tương ứng. `NON_ABSENT` không đồng nghĩa với bỏ mọi giá trị rỗng: chuỗi `""` và collection rỗng không tự động trở thành absent.

Trong ứng dụng framework, nên sử dụng mapper đã được framework cấu hình và xác nhận module cần thiết có trong runtime. Tránh tạo mapper mặc định mới chỉ để serialize một DTO vì mapper đó có thể thiếu module đã được đăng ký trong ứng dụng.

### 2.4. NON_EMPTY: bỏ giá trị rỗng

`NON_EMPTY` bỏ null, absent và những giá trị mà Jackson xem là rỗng. Các trường hợp phổ biến:

- Chuỗi có độ dài bằng 0 (`""`).
- Array không có phần tử.
- Collection rỗng.
- Map rỗng.
- Giá trị null hoặc absent.

Ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class SearchResponse {
    private String keyword;
    private List<String> results;
    private Map<String, String> metadata;
    private String description;
}
```

Nếu `keyword = ""`, `results = []`, `metadata = {}` và `description = null`, các property đó bị bỏ khỏi JSON.

`NON_EMPTY` không có nghĩa là bỏ mọi giá trị “không đáng kể” theo nghiệp vụ:

| Giá trị Java | Có bị bỏ bởi NON_EMPTY? |
|---|---|
| `null` | Có |
| `""` | Có |
| `"   "` | Không; đây vẫn là chuỗi có ký tự |
| `0` | Không |
| `false` | Không |
| Array rỗng | Có |
| Collection rỗng | Có |
| Map rỗng | Có |
| Collection có phần tử | Không |

Chuỗi chỉ chứa khoảng trắng vẫn có độ dài lớn hơn 0. Nếu API muốn bỏ cả whitespace-only string, hãy trim hoặc chuẩn hóa dữ liệu trước khi serialize, hoặc định nghĩa filter tùy chỉnh.

`NON_EMPTY` cũng không thay thế validation. Nó không kiểm tra một chuỗi có hợp lệ theo nghiệp vụ hay không; nó chỉ áp dụng tiêu chí rỗng do Jackson nhận diện.

### 2.5. NON_DEFAULT: bỏ giá trị mặc định

`NON_DEFAULT` bỏ các giá trị được xem là mặc định. Với kiểu Java nguyên thủy, default thường là:

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
}
```

Nếu `enabled = false`, `retryCount = 0` và `label = null`, các property này có thể bị bỏ. Nếu `enabled = true` hoặc `retryCount = 3`, chúng được giữ lại.

**Phạm vi đặt annotation ảnh hưởng cách xác định default.** Khi đặt `NON_DEFAULT` ở cấp class, Jackson có thể tạo một instance mặc định của POJO rồi so sánh property của object đang serialize với giá trị tương ứng trên instance mặc định. Nhờ đó, giá trị khởi tạo riêng trong class cũng có thể được xem là default:

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

Với instance mặc định, `maxAttempts = 3` và `enabled = true`. Các giá trị đó có thể bị bỏ khi serialize một instance khác có cùng giá trị.

Khi dùng `NON_DEFAULT` ở cấp global hoặc property, việc so sánh thường dựa trên default theo kiểu dữ liệu, ví dụ null, zero hoặc false, chứ không nhất thiết dựa vào giá trị khởi tạo nghiệp vụ của một POJO. Vì vậy, nếu default riêng là `3` hoặc `true`, cần chọn đúng phạm vi áp dụng hoặc dùng filter tùy chỉnh.

Class-level `NON_DEFAULT` cần khả năng tạo instance mặc định phù hợp. Nếu constructor mặc định không tồn tại, không thể tạo object an toàn hoặc có tác dụng phụ, hãy cân nhắc chính sách khác và xác nhận hành vi với phiên bản Jackson của dự án.

### 2.6. CUSTOM: tiêu chí do ứng dụng định nghĩa

Khi các chế độ chuẩn không đủ, `CUSTOM` cho phép dùng filter. Jackson dùng `equals()` của filter để xác định giá trị có cần bị loại hay không: nếu filter xem giá trị là bằng giá trị sentinel, property bị suppress.

Ví dụ, bỏ `retryCount` khi bằng `0`:

```java
public class ZeroFilter {
    @Override
    public boolean equals(Object value) {
        return Integer.valueOf(0).equals(value);
    }
}

public class JobStatus {
    @JsonInclude(
        value = JsonInclude.Include.CUSTOM,
        valueFilter = ZeroFilter.class
    )
    private Integer retryCount;
}
```

Nếu `retryCount` là 0, filter trả về true và property bị bỏ. Nếu giá trị khác 0, property được xuất. Filter nên có hành vi `equals()` ổn định, không phụ thuộc mutable state và có constructor phù hợp để Jackson khởi tạo.

`CUSTOM` cũng có thể dùng cho `contentFilter` để lọc nội dung bên trong container hoặc kiểu tham chiếu. Phần value filter và content filter được giải thích ở phần tiếp theo.

### 2.7. USE_DEFAULTS: dùng chính sách kế thừa

`USE_DEFAULTS` không có nghĩa là luôn xuất property. Nó yêu cầu Jackson dùng chính sách inclusion được cung cấp ở cấp cấu hình khác:

```java
@JsonInclude(JsonInclude.Include.USE_DEFAULTS)
private String note;
```

Ví dụ mapper có default `NON_NULL`; property dùng `USE_DEFAULTS` sẽ theo chính sách mặc định đó thay vì tự đặt `ALWAYS` hoặc `NON_EMPTY`.

## 3. Phân biệt value inclusion và content inclusion

`@JsonInclude` có hai thuộc tính cấu hình độc lập:

- `value`: quyết định có xuất chính property hay không.
- `content`: quyết định có giữ các giá trị nằm bên trong property hay không, chẳng hạn phần tử collection/array hoặc value của Map và kiểu tham chiếu.

### 3.1. Bỏ cả collection khi rỗng

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
private List<String> tags;
```

Nếu `tags` là null hoặc list rỗng, key `tags` bị bỏ. Nếu list có phần tử, property được xuất.

### 3.2. Giữ property nhưng lọc nội dung null

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

Jackson giữ property và lọc phần tử null trong nội dung collection. Output có dạng:

```json
{
  "tags": ["java", "jackson"]
}
```

Nếu list rỗng, key vẫn được xuất thành `"tags": []` vì `value` là `ALWAYS`.

### 3.3. Bỏ container rỗng và lọc phần tử null

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

Đối với Map, `content` áp dụng lên value của entry:

```java
@JsonInclude(
    value = JsonInclude.Include.NON_EMPTY,
    content = JsonInclude.Include.NON_NULL
)
private Map<String, String> metadata;
```

Map rỗng bị bỏ; entry có value null bị lọc; entry có value khác null được giữ. Inclusion của content không phải cách lọc key của Map.

## 4. Áp dụng JsonInclude trên property

Đặt annotation trực tiếp lên field hoặc accessor khi chỉ một thuộc tính cần chính sách riêng:

```java
public class UserResponse {
    private String name;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    private String nickname;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String avatarUrl;

    @JsonInclude(JsonInclude.Include.ALWAYS)
    private String status;
}
```

Trong ví dụ:

- `nickname` bị bỏ nếu null hoặc chuỗi rỗng.
- `avatarUrl` chỉ bị bỏ nếu null; chuỗi rỗng vẫn được xuất.
- `status` luôn được xuất, kể cả null.
- `name` theo chính sách mặc định của mapper/lớp.

Annotation cũng có thể đặt trên getter:

```java
public class UserResponse {
    private String nickname;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    public String getNickname() {
        return nickname;
    }
}
```

Jackson hợp nhất field và accessor thành logical property theo quy tắc introspection. Để tránh cấu hình khó hiểu, nên đặt annotation nhất quán ở một vị trí có chủ đích, nhất là khi field, getter và setter cùng được annotation.

### 4.1. Property bị bỏ không có nghĩa là bị bỏ qua khi đọc JSON

`@JsonInclude` điều khiển serialize. Nó không tự thay đổi cách deserialize khi JSON đầu vào thiếu key hoặc chứa null.

Ví dụ, nếu `nickname` bị bỏ khỏi response do `NON_EMPTY`, điều đó không có nghĩa Jackson sẽ bỏ qua một `nickname` được gửi trong request. Muốn điều khiển đầu vào, hãy xem `@JsonProperty(access = ...)`, `@JsonSetter`, `Nulls` hoặc cấu hình deserialize phù hợp.

### 4.2. JsonInclude không thay thế JsonIgnore

Hai annotation có mục đích khác nhau:

- `@JsonInclude` giữ property khi thỏa điều kiện giá trị.
- `@JsonIgnore` loại property khỏi quá trình ánh xạ theo chính sách ignore, bất kể giá trị của nó.

Nếu một field không bao giờ được xuất, dùng `@JsonIgnore` hoặc access mode phù hợp. Nếu chỉ muốn bỏ field khi null/rỗng, dùng `@JsonInclude`.

## 5. Áp dụng chính sách ở cấp class

Đặt `@JsonInclude` trên class để áp dụng một chính sách mặc định cho các property của kiểu đó:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String name;
    private String nickname;
    private String avatarUrl;

    @JsonInclude(JsonInclude.Include.ALWAYS)
    private String status;
}
```

Các property thông thường theo chính sách cấp lớp; `status` có cấu hình riêng để luôn xuất hiện. Cách này phù hợp khi phần lớn field trong một DTO dùng chung tiêu chí.

Class-level annotation cũng hữu ích khi muốn giữ chính sách serialize gần model. Tuy nhiên, nếu cùng một model được dùng cho nhiều API có hợp đồng khác nhau, annotation trên class có thể không đủ linh hoạt. Khi đó, cân nhắc mapper/view hoặc DTO response riêng theo từng hợp đồng.

## 6. Cấu hình inclusion mặc định trên ObjectMapper

Nếu nhiều DTO trong ứng dụng có cùng chính sách, có thể đặt default inclusion trên mapper thay vì lặp annotation.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.setDefaultPropertyInclusion(
    JsonInclude.Value.construct(
        JsonInclude.Include.NON_NULL,
        JsonInclude.Include.ALWAYS
    )
);
```

Đối số thứ nhất là inclusion mặc định của property value; đối số thứ hai là inclusion mặc định của content. Trong ví dụ, property null bị bỏ, còn nội dung collection/Map không bị lọc theo một chính sách content riêng.

Có thể viết theo cách builder của `JsonInclude.Value`:

```java
JsonInclude.Value inclusion = JsonInclude.Value.empty()
    .withValueInclusion(JsonInclude.Include.NON_NULL)
    .withContentInclusion(JsonInclude.Include.NON_NULL);

mapper.setDefaultPropertyInclusion(inclusion);
```

Đây là cấu hình mặc định. Annotation trên class/property và type override có thể cung cấp chính sách cụ thể hơn. Khi nhiều lớp cấu hình cùng áp dụng, hãy xác nhận kết quả với mapper và phiên bản Jackson thực tế thay vì chỉ nhìn một dòng cấu hình.

Trong ứng dụng framework, nên cấu hình mapper ở giai đoạn khởi tạo thông qua cơ chế framework hỗ trợ. Không thay đổi inclusion của mapper singleton theo từng request sau khi mapper đã bắt đầu serialize.

## 7. Cấu hình theo kiểu Java bằng configOverride

Đôi khi không thể hoặc không muốn sửa source class để thêm annotation. `ObjectMapper.configOverride()` cho phép đặt cấu hình inclusion cho một kiểu Java cụ thể:

```java
mapper.configOverride(AuditEvent.class)
    .setInclude(
        JsonInclude.Value.construct(
            JsonInclude.Include.NON_EMPTY,
            JsonInclude.Include.ALWAYS
        )
    );
```

Trong ví dụ, các property của `AuditEvent` dùng `NON_EMPTY` làm inclusion mặc định cho value; content vẫn theo `ALWAYS` nếu không có cấu hình cụ thể khác.

Cách này hữu ích khi:

- Class đến từ thư viện bên ngoài và không thể chỉnh sửa annotation.
- Một ứng dụng muốn tách chính sách JSON khỏi model domain.
- Một kiểu có chính sách đầu ra riêng so với default toàn mapper.

Hãy thực hiện override trước khi mapper được sử dụng và giữ các rule tập trung trong cấu hình. Tránh rải nhiều override rời rạc mà không có tài liệu về hợp đồng JSON.

## 8. Hiểu cách các phạm vi cấu hình kết hợp

Một ứng dụng có thể đồng thời có:

1. Default inclusion trên `ObjectMapper`.
2. Type override cho một class bằng `configOverride()`.
3. Annotation ở cấp class.
4. Annotation riêng trên property.

Các lớp cấu hình được Jackson hợp nhất khi introspect property. Chính sách cụ thể của annotation thường có tính ưu tiên cao hơn default rộng hơn; property annotation là nơi diễn đạt ngoại lệ sát nhất với thuộc tính. Tuy nhiên, khi có nhiều nguồn cấu hình, kết quả còn phụ thuộc cách `JsonInclude.Value` được merge và phiên bản Jackson.

Để tránh xung đột:

- Dùng mapper default cho quy tắc chung.
- Dùng class annotation hoặc type override cho quy tắc của một kiểu.
- Dùng property annotation cho ngoại lệ của một field.
- Dùng `USE_DEFAULTS` khi muốn property/class quay về chính sách bao quanh.
- Tránh đặt những rule mâu thuẫn trên field và getter cùng logical property.
- Viết test serialize cho từng trường hợp quan trọng bằng mapper production.

Không nên suy ra output chỉ từ annotation nhìn thấy trên field. Jackson có thể nhận diện property từ getter, field, constructor hoặc mix-in; cấu hình mapper cũng tham gia quyết định cuối cùng.

## 9. Dùng filter tùy chỉnh cho quy tắc nghiệp vụ

Nếu một giá trị chỉ được xem là rỗng theo nghiệp vụ, filter có thể diễn đạt quy tắc đó.

### 9.1. valueFilter: bỏ cả property theo giá trị

Ví dụ, bỏ chuỗi `"N/A"` khỏi output:

```java
public class NotAvailableFilter {
    @Override
    public boolean equals(Object value) {
        return "N/A".equals(value);
    }
}

public class ReportResponse {
    @JsonInclude(
        value = JsonInclude.Include.CUSTOM,
        valueFilter = NotAvailableFilter.class
    )
    private String department;
}
```

Nếu `department` là `"N/A"`, filter trả về true và property bị bỏ. Nếu là `"Finance"`, property được xuất.

Filter so sánh giá trị qua `equals()`. Hãy viết filter không phụ thuộc state thay đổi, xử lý null theo ý định rõ ràng và tránh gọi service hoặc thực hiện I/O trong `equals()`.

### 9.2. contentFilter: lọc giá trị bên trong container

Nếu muốn giữ property nhưng loại các phần tử có giá trị sentinel, dùng `content = CUSTOM`:

```java
public class UnknownValueFilter {
    @Override
    public boolean equals(Object value) {
        return "UNKNOWN".equals(value);
    }
}

public class ReportResponse {
    @JsonInclude(
        value = JsonInclude.Include.ALWAYS,
        content = JsonInclude.Include.CUSTOM,
        contentFilter = UnknownValueFilter.class
    )
    private List<String> labels;
}
```

Với list `List.of("READY", "UNKNOWN", "DONE")`, nội dung được lọc theo content filter trong khi property `labels` vẫn được giữ. Hãy kiểm tra serializer của kiểu container và phiên bản Jackson vì các kiểu tùy chỉnh có thể cần serializer riêng để hỗ trợ content suppression.

### 9.3. Chọn filter hay chuẩn hóa dữ liệu?

Filter phù hợp khi quy tắc chỉ dành cho output. Nếu `"N/A"` thực chất biểu diễn một trạng thái nghiệp vụ, nên cân nhắc chuẩn hóa thành enum hoặc giá trị domain rõ ràng trước khi serialize. Không để filter che giấu dữ liệu sai hoặc thay thế validation.

## 10. JsonInclude với Optional và các kiểu tham chiếu

`Optional<T>` biểu diễn có/không có giá trị. Khi dùng module `jackson-datatype-jdk8`, có thể phối hợp inclusion:

```java
public class UserResponse {
    @JsonInclude(JsonInclude.Include.NON_ABSENT)
    private Optional<String> nickname;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    private Optional<String> note;
}
```

`NON_ABSENT` tập trung vào absent/null. `NON_EMPTY` có thể loại thêm nội dung rỗng, ví dụ `Optional.of("")` nếu serializer của kiểu tham chiếu báo giá trị nội dung là empty. Hãy kiểm tra behavior của module và serializer đang dùng.

Với các kiểu tham chiếu khác, serializer có thể định nghĩa thế nào là empty hoặc absent. `JsonInclude` dựa vào khả năng của serializer/type handler; không phải mọi wrapper tùy chỉnh đều có cùng semantics.

## 11. JsonInclude và naming/visibility của property

`JsonInclude` chỉ tác động lên property mà Jackson đã nhận diện. Nếu property không xuất hiện do visibility hoặc ignore, inclusion policy không làm nó tự xuất hiện.

Ví dụ, field private không có getter và không có annotation/visibility phù hợp có thể không được Jackson nhận diện theo cấu hình mặc định. Thêm `@JsonInclude(NON_NULL)` vào field đó không tự động bật field visibility.

Tương tự, nếu getter tạo tên property khác với field, annotation trên hai vị trí không nhất quán có thể dẫn tới cấu hình không như mong muốn. Hãy xác định logical property thực tế qua accessor và annotation trước khi điều tra inclusion.

`@JsonInclude` cũng không phải allowlist cho toàn bộ field. Nếu yêu cầu là chỉ cho phép một tập tên property được serialize, hãy xem `@JsonIncludeProperties` hoặc cơ chế filter property phù hợp; đó là bài toán lựa chọn property, khác với điều kiện bỏ property theo giá trị.

## 12. Ví dụ tổng hợp: response API với nhiều chính sách

Giả sử API trả hồ sơ với các yêu cầu:

- Bỏ property null.
- Bỏ chuỗi rỗng và collection rỗng ở một số field tùy chọn.
- Giữ `active = false` vì đây là trạng thái có ý nghĩa.
- Giữ `status` kể cả null vì client luôn cần key này.
- Lọc phần tử null trong `roles`.

Có thể viết:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProfileResponse {
    private String name;

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    private String nickname;

    @JsonInclude(
        value = JsonInclude.Include.NON_EMPTY,
        content = JsonInclude.Include.NON_NULL
    )
    private List<String> roles;

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
response.setRoles(Arrays.asList("ADMIN", null, "USER"));
response.setActive(false);
response.setStatus(null);
```

Output dự kiến:

```json
{
  "name": "An",
  "roles": ["ADMIN", "USER"],
  "active": false,
  "status": null
}
```

`nickname` bị bỏ do empty string. `roles` vẫn được xuất vì list không rỗng, nhưng phần tử null bị lọc. `active` vẫn được xuất vì `NON_NULL` không loại false. `status` được xuất do annotation `ALWAYS` cụ thể hơn chính sách class.

## 13. Kiểm thử JsonInclude bằng ObjectMapper

Inclusion là hành vi của serializer, vì vậy nên kiểm tra JSON thực tế thay vì chỉ kiểm tra annotation tồn tại.

Ví dụ JUnit:

```java
class ProfileResponseTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void omitsEmptyAndNullButKeepsFalseAndExplicitStatus() throws Exception {
        ProfileResponse response = new ProfileResponse();
        response.setName("An");
        response.setNickname("");
        response.setRoles(Arrays.asList("ADMIN", null, "USER"));
        response.setActive(false);
        response.setStatus(null);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

        assertEquals("An", json.get("name").asText());
        assertFalse(json.has("nickname"));
        assertEquals(2, json.get("roles").size());
        assertFalse(json.get("active").asBoolean());
        assertTrue(json.has("status"));
        assertTrue(json.get("status").isNull());
    }
}
```

Các assertion nên phân biệt:

- `json.has("field")`: key có xuất hiện hay không.
- `json.get("field").isNull()`: key có mặt với giá trị JSON null hay không.
- Giá trị rỗng như `""`, `[]`, `{}`.
- Giá trị default như `0` hoặc `false`.
- Nội dung container sau khi content inclusion được áp dụng.

Không dùng `get("field") == null` để phân biệt key bị thiếu với key có JSON null một cách tùy tiện; trong Jackson tree model, `get()` trả null khi field không tồn tại và trả `NullNode` khi field có giá trị JSON null. Viết assertion rõ ràng giúp test bắt đúng hợp đồng output.

## 14. Những lỗi thường gặp

**Dùng `NON_NULL` nhưng vẫn thấy chuỗi rỗng hoặc list rỗng.** Đây là đúng theo định nghĩa: `NON_NULL` chỉ bỏ null. Dùng `NON_EMPTY` nếu muốn bỏ các giá trị rỗng.

**Dùng `NON_EMPTY` nhưng vẫn thấy `0` hoặc `false`.** Các giá trị này không phải empty. Nếu muốn bỏ default, xem `NON_DEFAULT` hoặc filter tùy chỉnh.

**Cho rằng whitespace-only string là empty.** `"   "` vẫn là chuỗi có ký tự. Hãy trim/normalize hoặc viết filter riêng.

**Cho rằng bỏ container đồng nghĩa lọc phần tử.** `value` và `content` có phạm vi khác nhau. Dùng `content` khi cần lọc phần tử hoặc value bên trong container.

**Cho rằng JsonInclude điều khiển deserialize.** Nó là chính sách serialize. Muốn xử lý null/missing khi đọc, dùng cấu hình deserialize tương ứng.

**Cho rằng `NON_DEFAULT` luôn dùng giá trị khởi tạo của object.** Cách xác định default phụ thuộc phạm vi annotation/cấu hình. Class-level và global/property-level có semantics khác nhau.

**Đặt annotation trên field nhưng property được nhận diện từ accessor khác.** Kiểm tra logical property, visibility và annotation merge; đặt rule nhất quán.

**Thay đổi mapper singleton sau khi đã dùng.** Inclusion là cấu hình serializer. Hãy cấu hình mapper trước khi chia sẻ, không thay đổi theo request.

**Dùng JsonInclude như allowlist.** Inclusion quyết định bỏ theo giá trị; allowlist tên property là một yêu cầu khác.

## 15. Quy trình chọn chính sách output

1. Xác định key nào bắt buộc luôn xuất hiện, kể cả khi null.
2. Xác định field nào có thể bỏ khi null.
3. Phân biệt null với chuỗi rỗng, collection rỗng và absent value.
4. Xác định `0` và `false` có phải giá trị hợp lệ cần giữ hay default cần bỏ.
5. Chọn `value` inclusion cho toàn property.
6. Nếu cần lọc nội dung collection/Map, cấu hình `content` riêng.
7. Chọn phạm vi: property, class, type override hoặc mapper default.
8. Dùng `CUSTOM` khi quy tắc nghiệp vụ không thể diễn đạt bằng mode chuẩn.
9. Kiểm tra logical property và annotation merge khi field/getter cùng tồn tại.
10. Viết test JSON để xác nhận key thiếu, key null, empty, default và content sau lọc.

## Kết luận

`@JsonInclude` kiểm soát điều kiện một property và nội dung bên trong nó được xuất ra JSON. `ALWAYS`, `NON_NULL`, `NON_ABSENT`, `NON_EMPTY`, `NON_DEFAULT` và `CUSTOM` diễn đạt những tiêu chí khác nhau; `value` áp dụng cho cả property, còn `content` áp dụng cho phần tử hoặc value bên trong kiểu chứa. Có thể đặt chính sách trên property, class, kiểu Java hoặc làm default cho `ObjectMapper`. Hãy chọn phạm vi theo hợp đồng API, giữ riêng logic serialize với deserialize và kiểm tra output thực tế để bảo đảm client nhận đúng những key cần thiết.
