# Giải tuần tự hóa qua constructor không tham số và setter

Trong Jackson, một cách phổ biến để tạo object khi đọc JSON là **gọi constructor không tham số trước, sau đó gán từng property thông qua setter**. Đây là mô hình JavaBean quen thuộc: class cung cấp constructor để tạo instance và các method `setXxx(...)` để nhận dữ liệu.

Cơ chế này phù hợp với DTO mutable, request/response model và nhiều class Java truyền thống. Để sử dụng đúng, cần hiểu thứ tự Jackson tạo object, nhận diện setter, chuyển kiểu giá trị JSON và xử lý những property bị thiếu hoặc có giá trị null. Những chi tiết này quyết định vì sao một object được tạo thành công, vì sao một setter không được gọi hoặc vì sao dữ liệu sau deserialize khác với giá trị ban đầu của constructor.

## 1. Luồng giải tuần tự hóa của JavaBean

Giả sử JSON cần đọc thành một object `Customer`:

```json
{
  "name": "An",
  "email": "an@example.test"
}
```

Class Java có constructor không tham số và setter tương ứng:

```java
public class Customer {
    private String name;
    private String email;

    public Customer() {
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

Khi gọi:

```java
ObjectMapper mapper = new ObjectMapper();
Customer customer = mapper.readValue(json, Customer.class);
```

Về mặt khái niệm, Jackson thực hiện các bước:

1. Xác định kiểu đích là `Customer`.
2. Tìm cách tạo instance. Trong trường hợp này, mapper chọn constructor không tham số.
3. Gọi constructor để tạo object ban đầu.
4. Đọc từng property từ JSON.
5. Tìm mutator tương ứng, ở đây là setter `setName(...)` hoặc `setEmail(...)`.
6. Chuyển giá trị JSON sang kiểu Java của tham số setter.
7. Gọi setter để gán giá trị vào instance.
8. Trả về object đã được populate.

```text
JSON input
   |
   v
Chọn deserializer cho Customer
   |
   v
Gọi Customer()
   |
   v
Tạo instance ban đầu
   |
   +-------------------------------+
   | Đọc property "name"           |
   | Chuyển JSON string -> String  |
   | Gọi setName("An")             |
   +-------------------------------+
   |
   +-------------------------------+
   | Đọc property "email"          |
   | Chuyển JSON string -> String  |
   | Gọi setEmail(...)             |
   +-------------------------------+
   |
   v
Customer đã được gán dữ liệu
```

Constructor chạy trước các setter trong đường giải tuần tự hóa mặc định này. Vì vậy, giá trị khởi tạo trong constructor hoặc field initializer có thể tồn tại nếu JSON không cung cấp property tương ứng; nếu JSON có property đó, setter thường ghi đè giá trị ban đầu.

## 2. Constructor không tham số có vai trò gì?

Constructor không tham số (no-argument constructor hoặc no-arg constructor) là constructor không nhận tham số:

```java
public Customer() {
}
```

Jackson cần một cách tạo instance trước khi gán các property. Với JavaBean mutable, no-arg constructor cung cấp điểm khởi tạo đơn giản: tạo object trước, rồi điền dữ liệu sau.

### 2.1. Constructor tường minh và constructor mặc định do Java sinh

Nếu class không khai báo bất kỳ constructor nào, compiler Java tự sinh constructor không tham số với visibility giống class:

```java
public class Customer {
    private String name;

    // Java tự cung cấp public Customer() nếu class public
}
```

Nhưng nếu class đã khai báo một constructor có tham số, Java không còn tự sinh no-arg constructor:

```java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }
}
```

Class trên không có constructor không tham số. Nếu không cung cấp creator phù hợp, Jackson không thể dùng đường tạo object JavaBean mặc định. Lỗi thường gặp có dạng:

```text
Cannot construct instance of Customer:
(no Creators, like default constructor, exist)
```

Nếu muốn dùng constructor + setter, hãy khai báo no-arg constructor và bảo đảm class có các mutator cần thiết:

```java
public class Customer {
    private String name;

    public Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Việc có thêm constructor tham số không làm Jackson tự chọn constructor đó. Nếu muốn Jackson truyền dữ liệu vào constructor tham số, đó là một cơ chế creator khác, được trình bày ở phần 9.

### 2.2. Visibility và khả năng truy cập constructor

Constructor public là lựa chọn ít gây bất ngờ nhất:

```java
public class Customer {
    public Customer() {
    }
}
```

Jackson cũng có thể sử dụng một số constructor không public khi cơ chế phát hiện creator và khả năng truy cập reflection cho phép. Kết quả phụ thuộc visibility configuration, `MapperFeature.CAN_OVERRIDE_ACCESS_MODIFIERS`, môi trường security và giới hạn truy cập của Java module system.

Không nên thiết kế class dựa trên giả định rằng một private constructor luôn được Jackson truy cập thành công. Nếu constructor không public là chủ ý, cần cấu hình và kiểm thử trên đúng runtime. Nếu class cần deserialize như DTO thông thường, constructor public hoặc package/protected constructor có thể truy cập là cách dễ vận hành hơn.

### 2.3. Constructor nên làm gì?

Vì constructor được chạy trước khi Jackson gán property, nó nên thiết lập trạng thái ban đầu an toàn:

```java
public class ImportJob {
    private String source;
    private String status;
    private List<String> warnings = new ArrayList<>();

    public ImportJob() {
        this.status = "NEW";
    }

    public void setSource(String source) {
        this.source = source;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public void setWarnings(List<String> warnings) {
        this.warnings = warnings;
    }
}
```

Trong ví dụ, constructor đặt trạng thái mặc định là `NEW`. Nếu JSON không có property `status`, giá trị này được giữ lại. Nếu JSON có `"status": "QUEUED"`, setter thay thế giá trị ban đầu bằng `QUEUED`.

Constructor không nên giả định rằng các property JSON đã có giá trị. Nó cũng không nên thực hiện nghiệp vụ phụ thuộc vào dữ liệu sẽ được gán sau đó, vì tại thời điểm constructor chạy, các setter chưa được gọi.

## 3. Jackson nhận diện setter như thế nào?

Setter JavaBean thường có tên `set` theo sau bởi tên property và nhận một tham số:

```java
public void setEmail(String email) {
    this.email = email;
}
```

Tên method được chuyển thành tên property theo quy tắc JavaBean. Ví dụ:

| Setter | Tên property mặc định |
|---|---|
| `setName(String)` | `name` |
| `setEmail(String)` | `email` |
| `setCreatedAt(Instant)` | `createdAt` |
| `setURL(String)` | Phụ thuộc quy tắc Bean naming đang bật |

Jackson cần xác định method có phải mutator phù hợp không, sau đó ghép nó với các thành viên cùng logical property nếu có.

### 3.1. Setter không bắt buộc phải có getter

Một class có thể chỉ cung cấp setter:

```java
public class SearchRequest {
    private String keyword;

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
```

Khi đọc JSON:

```json
{
  "keyword": "jackson"
}
```

Jackson có thể gọi `setKeyword("jackson")`. Nhưng nếu class không có getter hoặc field đọc được, property có thể không được xuất ra khi serialize.

Điều này thường phù hợp với request model chỉ nhận input. Nếu muốn thể hiện hợp đồng rõ ràng hơn, có thể dùng `@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)`.

### 3.2. Setter có thể có visibility khác public

Trong Jackson 2.x, quy tắc visibility cho setter mặc định rộng hơn getter và field; setter theo JavaBean có thể được phát hiện kể cả khi không public. Tuy vậy, khả năng gọi method vẫn phụ thuộc cấu hình truy cập reflection và môi trường chạy.

Có thể điều chỉnh visibility bằng `@JsonAutoDetect` hoặc cấu hình mapper. Nếu setter là private/protected và cần dùng trong module Java có encapsulation nghiêm ngặt, hãy kiểm tra runtime thực tế thay vì dựa vào hành vi IDE hoặc unit test trên classpath không module.

### 3.3. Setter có thể trả về chính object

Theo phong cách JavaBean cổ điển, setter thường trả về `void`. Tuy nhiên, Jackson nhận diện mutator dựa chủ yếu vào quy ước tên và chữ ký tham số; một số fluent setter trả về object vẫn có thể được nhận diện:

```java
public Customer setName(String name) {
    this.name = name;
    return this;
}
```

Dù vậy, để code dễ hiểu và tương thích với thư viện bean-introspection khác, setter trả về `void` vẫn là lựa chọn thông dụng.

### 3.4. Overloaded setter có thể gây mơ hồ

Tránh khai báo nhiều setter cùng tên chỉ khác kiểu tham số:

```java
public void setAmount(BigDecimal amount) {
    this.amount = amount;
}

public void setAmount(String amount) {
    this.amount = new BigDecimal(amount);
}
```

Jackson có thể phải chọn một mutator trong các ứng viên cùng property. Kết quả lựa chọn có thể phụ thuộc kiểu tham số và quy tắc giải quyết xung đột; nếu các ứng viên không thể phân giải, mapper có thể báo lỗi định nghĩa.

Nên giữ một setter có kiểu rõ ràng. Nếu JSON cần chấp nhận nhiều biểu diễn đầu vào, hãy viết custom deserializer hoặc dùng một kiểu trung gian có quy tắc chuyển đổi tường minh.

## 4. Ánh xạ tên JSON tới setter

Jackson dùng tên property logic để tìm mutator tương ứng. Ví dụ:

```java
public class Employee {
    private String department;

    public void setDepartment(String department) {
        this.department = department;
    }
}
```

JSON sau ánh xạ tới setter `setDepartment(...)`:

```json
{
  "department": "Engineering"
}
```

Tên JSON không nhất thiết phải giống tên method. Có thể đặt tên external property bằng `@JsonSetter` hoặc `@JsonProperty`:

```java
public class Employee {
    private String department;

    @JsonSetter("department_name")
    public void setDepartment(String department) {
        this.department = department;
    }
}
```

Khi đó Jackson đọc key `department_name` và gọi `setDepartment(...)`.

### 4.1. Alias cho tên cũ và tên mới

Nếu API phải chấp nhận nhiều tên đầu vào trong giai đoạn chuyển đổi, có thể dùng `@JsonAlias`:

```java
public class Employee {
    private String department;

    @JsonSetter("department_name")
    @JsonAlias({"department", "dept"})
    public void setDepartment(String department) {
        this.department = department;
    }
}
```

Các tên alias được chấp nhận khi deserialize. Khi serialize, Jackson vẫn dùng tên property chính là `department_name`. `@JsonAlias` không tạo nhiều key output.

Điều này hữu ích khi đổi tên API nhưng cần tương thích payload cũ. Nên đặt kế hoạch loại bỏ alias sau khi các producer đã chuyển sang tên mới.

### 4.2. Naming strategy và tên tường minh

Mapper có thể áp dụng naming strategy toàn cục, ví dụ camelCase sang snake_case:

```java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
```

Setter `setCreatedAt(...)` khi đó thường tương ứng với key JSON `created_at`. Nếu dùng `@JsonSetter("created_time")`, tên tường minh xác định tên đầu vào của property. Khi đặt annotation ở nhiều accessor của cùng property, cần giữ tên nhất quán để tránh vô tình tạo property khác nhau hoặc xung đột.

## 5. Giá trị được gán vào setter như thế nào?

Jackson không truyền nguyên token JSON cho setter. Nó trước tiên chọn deserializer cho kiểu tham số, chuyển giá trị đầu vào thành kiểu Java rồi mới gọi setter.

Ví dụ:

```java
public class Invoice {
    private BigDecimal total;
    private LocalDate dueDate;
    private List<String> tags;

    public void setTotal(BigDecimal total) {
        this.total = total;
    }

    public void setDueDate(LocalDate dueDate) {
        this.dueDate = dueDate;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

JSON:

```json
{
  "total": 1250.50,
  "dueDate": "2026-12-31",
  "tags": ["urgent", "online"]
}
```

Đối với từng property, Jackson cần chuyển:

| JSON | Kiểu tham số setter | Giá trị Java |
|---|---|---|
| `1250.50` | `BigDecimal` | `BigDecimal` |
| `"2026-12-31"` | `LocalDate` | `LocalDate` |
| Mảng string | `List<String>` | List chứa các String |

Với Jackson 2.x, kiểu `java.time` thường cần module `jackson-datatype-jsr310` được thêm vào classpath và đăng ký với mapper. Ví dụ:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
```

Jackson 3 đã tích hợp hỗ trợ Java Time cơ bản vào databind. Cần cấu hình theo API và dependency của major version đang dùng.

Đối với collection hoặc object lồng nhau, Jackson tiếp tục dùng deserializer tương ứng cho từng phần tử/thuộc tính trước khi truyền giá trị đã tạo vào setter. Nếu một phần tử không chuyển đổi được, quá trình deserialize có thể dừng trước khi setter hoàn tất.

## 6. Constructor, field initializer và property bị thiếu

No-arg constructor và field initializer chạy trước khi Jackson gán các property JSON. Do đó, một property không xuất hiện trong input thường giữ nguyên giá trị ban đầu.

```java
public class JobRequest {
    private String name = "untitled";
    private int retryCount = 3;

    public JobRequest() {
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public String getName() {
        return name;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
```

Nếu JSON là:

```json
{
  "name": "daily-import"
}
```

Kết quả:

- `name` thành `daily-import` vì Jackson gọi `setName(...)`.
- `retryCount` vẫn là `3` vì JSON không có property này và setter không được gọi cho property bị thiếu.

Cần phân biệt **property bị thiếu** với **property có mặt nhưng mang null**. Hai trường hợp có thể tạo kết quả khác nhau.

## 7. Xử lý null và property có mặt

### 7.1. Reference type nhận null

Với property có kiểu tham chiếu như `String`, `BigDecimal`, `List` hoặc một class DTO, JSON null thường được chuyển thành Java null và setter được gọi với null:

```json
{
  "name": null
}
```

Nếu setter chỉ gán trực tiếp:

```java
public void setName(String name) {
    this.name = name;
}
```

giá trị trước đó của `name` sẽ bị thay bằng null.

Nếu muốn bỏ qua giá trị null và giữ giá trị khởi tạo, có thể dùng `@JsonSetter(nulls = Nulls.SKIP)`:

```java
public class JobRequest {
    private String name = "untitled";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setName(String name) {
        this.name = name;
    }
}
```

Khi JSON có `"name": null`, setter bị bỏ qua và giá trị `untitled` được giữ lại. Cơ chế này hữu ích với patch-like input, nhưng phải phân biệt rõ ý nghĩa null trong hợp đồng API.

### 7.2. Primitive và null

Primitive Java như `int`, `long`, `boolean` không thể lưu null. Trong Jackson 2.x, null đầu vào cho primitive thường được chuyển thành giá trị mặc định của primitive nếu không bật kiểm tra nghiêm ngặt:

- `int`: 0
- `long`: 0L
- `boolean`: false

Nếu muốn từ chối null cho primitive, bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

Khi bật feature này, input chứa null cho primitive sẽ gây lỗi mapping thay vì âm thầm thành 0/false. Với API cần phân biệt “không gửi”, “gửi null” và “gửi giá trị 0”, dùng wrapper type như `Integer` hoặc một mô hình patch riêng thường rõ ràng hơn.

### 7.3. Nulls.SKIP, Nulls.FAIL và Nulls.AS_EMPTY

Jackson 2.x hỗ trợ chính sách null theo property thông qua `@JsonSetter`:

```java
public class Preferences {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Một số lựa chọn:

| Chính sách | Ý nghĩa |
|---|---|
| `Nulls.SET` | Gán null như giá trị bình thường (mặc định phổ biến) |
| `Nulls.SKIP` | Không gọi setter khi input null |
| `Nulls.FAIL` | Từ chối input null |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng theo deserializer của kiểu |
| `Nulls.DEFAULT` | Dùng chính sách mặc định của property/mapper |

Đối với collection, `contentNulls` có thể điều khiển phần tử null bên trong collection. Chính sách này khác với null của chính collection.

## 8. Property không có trong JSON và property không được nhận diện

Nếu JSON không chứa một property đã được nhận diện, setter của property đó không được gọi. Giá trị sau deserialize phụ thuộc constructor và field initializer.

Nếu JSON chứa key không có property tương ứng, đó là **unknown property**. Hai tình huống này khác nhau:

- Thiếu property đã biết: Jackson không có giá trị mới để gán.
- Có key lạ: Jackson cần quyết định từ chối, bỏ qua hoặc xử lý bằng cơ chế mở rộng.

Trong Jackson 2.x, `FAIL_ON_UNKNOWN_PROPERTIES` mặc định bật. Có thể tắt ở mapper hoặc reader nếu hợp đồng yêu cầu bỏ qua field lạ:

```java
ObjectMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
```

Nếu muốn xử lý property không biết trước, có thể dùng `@JsonAnySetter`:

```java
public class Metadata {
    private final Map<String, JsonNode> attributes = new LinkedHashMap<>();

    @JsonAnySetter
    public void addAttribute(String name, JsonNode value) {
        attributes.put(name, value);
    }
}
```

Các key chưa có setter riêng sẽ được chuyển vào method `addAttribute`. Cách này phù hợp với metadata mở rộng hoặc payload có các thuộc tính động. Cần giới hạn và xác thực dữ liệu nếu map này chứa thông tin đến từ bên ngoài.

## 9. Setter có thể gây lỗi ở thời điểm nào?

Lỗi deserialize không nhất thiết xảy ra ở bước tìm constructor. Có thể phân biệt các nhóm lỗi:

| Giai đoạn | Ví dụ nguyên nhân | Kết quả thường gặp |
|---|---|---|
| Tạo instance | Không có constructor phù hợp, class abstract/interface | Không thể construct instance |
| Nhận diện property | Visibility không phù hợp, annotation xung đột | Property không được nhận diện hoặc lỗi định nghĩa |
| Đọc giá trị | JSON sai cú pháp, token không đúng kiểu | Parse/mapping exception |
| Chuyển kiểu | Chuỗi không phải số, ngày giờ sai format | Lỗi từ deserializer |
| Gọi setter | Setter ném exception, tham số không phù hợp | Lỗi mapping kèm đường dẫn property |
| Hoàn tất object | Invariant chỉ được kiểm tra sau khi gán | Object có thể ở trạng thái không hợp lệ nếu không có validation |

Ví dụ setter có thể tự kiểm tra dữ liệu:

```java
public void setQuantity(int quantity) {
    if (quantity < 0) {
        throw new IllegalArgumentException("quantity must not be negative");
    }
    this.quantity = quantity;
}
```

Nếu JSON chứa `"quantity": -1`, setter ném exception và Jackson bọc lỗi trong exception mapping. Khi đọc stack trace, hãy tìm property path để xác định setter hoặc trường dữ liệu gây lỗi.

Không nên đặt side effect như gọi HTTP, ghi database hoặc gửi message trong setter của DTO. Jackson có thể gọi setter trong quá trình parse; side effect khiến việc deserialize trở nên khó dự đoán, khó kiểm thử và có thể thực hiện một phần trước khi một property khác thất bại.

## 10. Thứ tự setter và tính nhất quán của object

Với default bean deserializer, Jackson tạo instance rồi xử lý các property trong luồng input. Vì vậy, setter thường được gọi khi property tương ứng được đọc; không nên dựa vào thứ tự key JSON để đảm bảo một setter luôn chạy trước setter khác.

Ví dụ không nên viết:

```java
public void setTotal(BigDecimal total) {
    this.total = total;
    recalculateTax(); // Có thể countryCode chưa được gán.
}

public void setCountryCode(String countryCode) {
    this.countryCode = countryCode;
}
```

Nếu logic phụ thuộc nhiều property, hãy thực hiện sau khi object được deserialize đầy đủ ở tầng service/factory/validation. Nếu cần bất biến mạnh và dữ liệu phải hợp lệ ngay khi tạo, hãy cân nhắc creator constructor hoặc một factory có xác thực rõ ràng.

Constructor + setter phù hợp với object mutable, nhưng trong quá trình binding, object có thể tạm thời chỉ được gán một phần. Không đưa instance đó vào luồng xử lý khác trước khi `readValue()` hoàn tất.

## 11. Phân biệt constructor không tham số + setter với creator constructor

Hai cách này đều có thể tạo object từ JSON, nhưng vòng đời khác nhau.

| Tiêu chí | No-arg constructor + setter | Creator/property-based constructor |
|---|---|---|
| Tạo object | Tạo instance rỗng hoặc có giá trị mặc định | Đọc tham số rồi gọi constructor/factory |
| Gán property | Sau khi tạo object | Tham số được truyền ngay khi tạo |
| Setter | Thường cần cho property muốn gán | Không cần nếu constructor nhận đủ dữ liệu |
| Phù hợp | DTO mutable, JavaBean | Immutable object, value object |
| Trạng thái trung gian | Có thể tồn tại object chưa đủ dữ liệu trong lúc deserialize | Object chỉ được tạo khi đã có tham số creator |
| Giá trị bị thiếu | Thường giữ initializer/default nếu không có setter call | Phụ thuộc default/optional parameter và creator configuration |

Ví dụ creator constructor:

```java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    @JsonCreator
    public Money(
            @JsonProperty("amount") BigDecimal amount,
            @JsonProperty("currency") String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Với class này, Jackson truyền các giá trị vào constructor thay vì tạo object rỗng rồi gọi setter. Đây là một lựa chọn khác khi thiết kế object bất biến; không nên cố ép class immutable vào mô hình setter-based.

## 12. Ví dụ hoàn chỉnh và kiểm thử

Ví dụ dưới đây minh họa constructor đặt default value, setter nhận property JSON, và getter cho phép kiểm tra kết quả:

```java
public class ImportRequest {
    private String source = "manual";
    private int retryCount = 2;

    public ImportRequest() {
        // Constructor không tham số được Jackson sử dụng.
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
```

Deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

ImportRequest request = mapper.readValue(
        """
        {
          "source": "s3",
          "retryCount": 5
        }
        """,
        ImportRequest.class
);

System.out.println(request.getSource());      // s3
System.out.println(request.getRetryCount());  // 5
```

Nếu input chỉ có `source`:

```json
{
  "source": "s3"
}
```

thì `retryCount` giữ giá trị `2` do field initializer đặt ra. Không có key `retryCount`, Jackson không cần gọi `setRetryCount(...)`.

Một unit test có thể kiểm tra cả trường hợp property có mặt và bị thiếu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class ImportRequestTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void shouldCreateObjectAndPopulatePropertiesThroughSetters() throws Exception {
        ImportRequest request = mapper.readValue(
                """
                {
                  "source": "s3",
                  "retryCount": 5
                }
                """,
                ImportRequest.class
        );

        assertEquals("s3", request.getSource());
        assertEquals(5, request.getRetryCount());
    }

    @Test
    void shouldKeepInitializerWhenPropertyIsMissing() throws Exception {
        ImportRequest request = mapper.readValue(
                """
                {
                  "source": "s3"
                }
                """,
                ImportRequest.class
        );

        assertEquals("s3", request.getSource());
        assertEquals(2, request.getRetryCount());
    }
}
```

Test đầu xác nhận các property có trong JSON được gán. Test thứ hai xác nhận property bị thiếu giữ giá trị initializer. Khi cần kiểm tra null, unknown property hoặc lỗi setter, nên bổ sung test riêng cho đúng hợp đồng dữ liệu.

## 13. Checklist thiết kế JavaBean cho Jackson

Khi muốn dùng constructor không tham số và setter để deserialize ổn định:

- Cung cấp no-arg constructor có thể được Jackson sử dụng.
- Nếu đã khai báo constructor tham số, nhớ rằng Java không tự sinh thêm no-arg constructor.
- Đặt tên setter theo quy ước `setXxx(...)` và tránh overload không cần thiết.
- Chọn visibility có chủ đích; không mở private field toàn cục nếu không muốn mọi field trở thành hợp đồng JSON.
- Dùng `@JsonSetter` hoặc `@JsonProperty` khi tên JSON khác tên Java.
- Xác định rõ ý nghĩa của property thiếu và property null.
- Không đặt nghiệp vụ phụ thuộc thứ tự setter trong setter.
- Không thực hiện side effect bên ngoài trong constructor hoặc setter của DTO.
- Hoàn tất cấu hình mapper trước khi chia sẻ mapper trong ứng dụng.
- Kiểm thử cả trường hợp property có mặt, thiếu, null, sai kiểu và key không nhận diện.

## 14. Kết luận

Trong mô hình JavaBean, Jackson thường gọi constructor không tham số để tạo instance, sau đó ánh xạ từng JSON property tới setter hoặc mutator phù hợp. Constructor và field initializer thiết lập trạng thái ban đầu; setter cập nhật những property có trong input. Do đó, property thiếu thường giữ giá trị mặc định đã khởi tạo, trong khi property có mặt nhưng null có thể ghi đè giá trị đó.

Để cơ chế hoạt động dễ dự đoán, class cần constructor truy cập được, setter có tên và kiểu rõ ràng, cùng quy tắc visibility/annotation phù hợp. Khi object cần bất biến hoặc phải bảo đảm invariant ngay lúc tạo, creator constructor thường là mô hình phù hợp hơn. Việc chọn đúng cách tạo object giúp quá trình deserialize rõ ràng, kiểm thử được và giữ hợp đồng JSON ổn định.

## Tài liệu tham khảo

- [Jackson Databind — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)
- [Jackson Annotations — @JsonCreator, @JsonProperty và @JsonSetter](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations)
- [Jackson 2.17 — ObjectMapper API](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.17.0/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — POJOPropertiesCollector source](https://github.com/FasterXML/jackson-databind/blob/2.17/src/main/java/com/fasterxml/jackson/databind/introspect/POJOPropertiesCollector.java)

