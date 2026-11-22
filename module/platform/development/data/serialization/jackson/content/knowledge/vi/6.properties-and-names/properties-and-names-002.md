# Cấu hình mức hiển thị và phạm vi thuộc tính được ánh xạ

Khi Jackson chuyển một object Java thành JSON hoặc đọc JSON để tạo object, nó phải quyết định **thuộc tính nào của kiểu Java được nhận diện** và **thuộc tính đó được dùng ở chiều đọc, chiều ghi hay cả hai**. Hai quyết định này có liên quan nhưng không giống nhau.

- **Mức hiển thị (visibility)** điều khiển Jackson tự động phát hiện field, getter, setter và constructor/factory method nào.
- **Phạm vi truy cập (property access)** điều khiển một thuộc tính đã được nhận diện có được serialize ra JSON, deserialize từ JSON hay thực hiện cả hai chiều.

Hiểu sự khác biệt này giúp bạn thiết kế JSON đúng hợp đồng, kiểm soát dữ liệu nhạy cảm và tránh thay đổi cấu hình quá rộng khiến những class khác trong ứng dụng bị ảnh hưởng.

## 1. Jackson nhận diện thuộc tính Java như thế nào?

Jackson Databind không đơn giản lấy tất cả field trong một class rồi biến chúng thành JSON. Nó thực hiện quá trình introspection để tìm các thành phần có thể đại diện cho thuộc tính dữ liệu.

Các thành phần thường được xem xét gồm:

- **Field:** biến thành viên của class, ví dụ `private String email`.
- **Getter:** method đọc giá trị, ví dụ `getEmail()`.
- **Is-getter:** method đọc giá trị boolean theo quy ước, ví dụ `isActive()`.
- **Setter:** method nhận giá trị, ví dụ `setEmail(String email)`.
- **Creator property:** tham số constructor hoặc factory method được dùng để tạo object, ví dụ tham số của constructor có `@JsonCreator`.

Ví dụ:

```java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Jackson có thể nhận diện `name` thông qua getter và setter. Getter hỗ trợ chiều serialize vì nó cung cấp giá trị từ object Java. Setter hỗ trợ chiều deserialize vì nó cho phép gán giá trị đọc từ JSON vào object.

Một field, getter và setter có cùng tên logic thường được hợp nhất thành **một property** trong mô hình của Jackson. Vì vậy, class trên thường tạo ra một trường JSON `name`, chứ không phải ba trường riêng biệt mang tên field, getter và setter.

```json
{
  "name": "An"
}
```

Quy tắc phát hiện mặc định phụ thuộc loại thành phần và phiên bản/cấu hình mapper. Trong cấu hình thông thường, getter công khai được nhận diện cho chiều ghi, setter phù hợp được nhận diện cho chiều đọc, còn field được xét theo quy tắc visibility của mapper. Nếu cần dựa trực tiếp vào field private hoặc thay đổi quy tắc này, bạn có thể cấu hình visibility.

## 2. Visibility: điều khiển tự động phát hiện thành phần nào

Jackson cung cấp `JsonAutoDetect.Visibility` để mô tả mức hiển thị được chấp nhận khi tự động phát hiện từng loại thành phần.

Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `ANY` | Chấp nhận mọi mức truy cập, bao gồm private, protected và public. |
| `NON_PRIVATE` | Chấp nhận mọi mức trừ private. |
| `PROTECTED_AND_PUBLIC` | Chỉ chấp nhận protected và public. |
| `PUBLIC_ONLY` | Chỉ chấp nhận thành phần public. |
| `NONE` | Không tự động phát hiện thành phần thuộc loại đang cấu hình. |
| `DEFAULT` | Dùng quy tắc mặc định của Jackson cho loại thành phần đó. |

Bạn có thể cấu hình riêng cho field, getter, is-getter, setter và creator. Điều này quan trọng vì một class có thể muốn đọc dữ liệu qua setter nhưng ghi dữ liệu qua getter, hoặc muốn dùng trực tiếp field cho cả hai chiều.

### 2.1. Cấu hình visibility trên một class bằng JsonAutoDetect

Nếu một kiểu Java cần quy tắc riêng, có thể khai báo `@JsonAutoDetect` trên class:

```java
import com.fasterxml.jackson.annotation.JsonAutoDetect;

@JsonAutoDetect(
        fieldVisibility = JsonAutoDetect.Visibility.ANY,
        getterVisibility = JsonAutoDetect.Visibility.NONE,
        isGetterVisibility = JsonAutoDetect.Visibility.NONE,
        setterVisibility = JsonAutoDetect.Visibility.NONE
)
public class InternalCustomer {
    private String name;
    private boolean active;
}
```

Với cấu hình này, Jackson tự động phát hiện field ở mọi mức truy cập, kể cả `private`, đồng thời không tự động phát hiện getter, is-getter hoặc setter. Các field được nhận diện có thể được dùng để đọc/ghi theo khả năng truy cập mà Jackson thiết lập.

Cách làm này hữu ích khi làm việc với kiểu dữ liệu không có getter/setter hoặc khi muốn mô hình hóa dữ liệu bằng field. Tuy nhiên, cần cân nhắc phạm vi áp dụng vì việc cho phép truy cập mọi field có thể đưa cả dữ liệu nội bộ vào quá trình ánh xạ.

### 2.2. Cấu hình visibility trên ObjectMapper

Nếu muốn áp dụng quy tắc cho tất cả kiểu được một mapper xử lý, có thể cấu hình trên `ObjectMapper`:

```java
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

mapper.setVisibility(
        PropertyAccessor.FIELD,
        JsonAutoDetect.Visibility.ANY
);
```

Thiết lập trên làm thay đổi quy tắc tự động phát hiện field của mapper. Các quy tắc getter, setter và creator vẫn theo cấu hình tương ứng hiện có.

Nếu muốn tắt tự động phát hiện các accessor rồi chỉ dựa vào field, có thể đặt rõ từng nhóm:

```java
mapper.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.NONE);
mapper.setVisibility(PropertyAccessor.FIELD, JsonAutoDetect.Visibility.ANY);
```

Khi đặt `ALL` thành `NONE`, mapper ngừng tự động phát hiện các nhóm accessor theo quy tắc visibility; sau đó field được bật lại với `ANY`. Các annotation tường minh như `@JsonProperty` vẫn có thể tham gia mô hình property theo quy tắc introspection của Jackson.

Không nên đặt cấu hình field `ANY` trên mapper toàn cục chỉ vì một DTO cần đọc field private. Nó có thể khiến nhiều class khác bắt đầu đưa field nội bộ vào JSON. Nếu quy tắc chỉ dành cho một kiểu, cân nhắc `@JsonAutoDetect` trên kiểu đó hoặc một mapper riêng có phạm vi rõ ràng.

## 3. Property access: xác định chiều đọc và chiều ghi

Sau khi Jackson nhận diện một property, ứng dụng còn cần quyết định property đó có được sử dụng ở chiều nào.

Trong annotation `@JsonProperty`, thuộc tính `access` nhận các giá trị của `JsonProperty.Access`:

| Giá trị | Khi serialize Java → JSON | Khi deserialize JSON → Java |
| --- | --- | --- |
| `AUTO` | Theo quy tắc phát hiện và cấu hình thông thường | Theo quy tắc phát hiện và cấu hình thông thường |
| `READ_ONLY` | Có thể đưa giá trị từ object Java ra JSON | Không nhận giá trị từ JSON để gán vào property |
| `WRITE_ONLY` | Không đưa property ra JSON | Có thể nhận giá trị từ JSON để gán vào property |
| `READ_WRITE` | Cho phép cả hai chiều | Cho phép cả hai chiều |

Tên `READ_ONLY` và `WRITE_ONLY` cần được hiểu theo hướng dữ liệu của Jackson: `READ_ONLY` là Jackson chỉ đọc giá trị từ object để ghi JSON; `WRITE_ONLY` là Jackson chỉ ghi giá trị từ JSON vào object.

### 3.1. READ_ONLY: dữ liệu chỉ xuất ra

Ví dụ, mã định danh được server sinh ra và trả về cho client. Client không được dùng JSON request để ghi đè mã này:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class AccountResponse {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String id;

    private String displayName;

    public AccountResponse(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Khi serialize `AccountResponse`, `id` có thể xuất hiện trong response JSON. Khi deserialize JSON thành kiểu này, giá trị `id` trong input không được dùng để gán vào property đó. Server vẫn kiểm soát giá trị định danh thông qua constructor hoặc logic nội bộ.

### 3.2. WRITE_ONLY: dữ liệu chỉ nhận vào

Ví dụ, request đăng ký tài khoản cần nhận mật khẩu từ client nhưng response không được trả mật khẩu:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class RegistrationRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
```

Khi đọc request JSON, Jackson có thể gán `password` vào object. Khi serialize object này, property `password` không được đưa ra JSON. Trong ứng dụng thực tế, mật khẩu vẫn phải được xử lý an toàn ở tầng nghiệp vụ, chẳng hạn băm mật khẩu trước khi lưu; `WRITE_ONLY` chỉ kiểm soát hướng ánh xạ JSON, không tự bảo vệ dữ liệu trong bộ nhớ hoặc database.

### 3.3. READ_WRITE và AUTO

`READ_WRITE` cho phép property tham gia cả serialization và deserialization. Đây là hành vi phù hợp với phần lớn thuộc tính dữ liệu thông thường.

`AUTO` là chế độ mặc định, để Jackson quyết định dựa trên visibility, accessor được nhận diện, annotation khác và cấu hình mapper. Nếu không có yêu cầu đặc biệt, bạn thường không cần ghi rõ `access = AUTO`.

## 4. Visibility và property access không thay thế nhau

Hai khái niệm này giải quyết hai bước khác nhau:

1. Visibility quyết định Jackson có tự động phát hiện field/getter/setter/creator hay không.
2. Property access quyết định property được ánh xạ theo chiều nào sau khi đã được nhận diện.

Ví dụ, một field private có thể không được tự động phát hiện theo visibility hiện tại. Việc gắn `@JsonProperty(access = WRITE_ONLY)` mô tả chiều truy cập của property, nhưng không nên hiểu rằng mọi field private đều tự động trở nên nhìn thấy trong mọi cấu hình. Muốn bảo đảm property được nhận diện, hãy dùng accessor phù hợp, `@JsonProperty` tường minh hoặc cấu hình visibility tương ứng.

Ngược lại, đặt field visibility thành `ANY` chỉ giúp Jackson tự động phát hiện field. Điều đó không tự biến tất cả field thành `READ_ONLY` hay `WRITE_ONLY`; chiều ánh xạ vẫn theo quy tắc property access và các metadata liên quan.

Có thể tóm tắt bằng ma trận:

| Câu hỏi | Cơ chế trả lời |
| --- | --- |
| Jackson có tự động tìm thấy field private không? | `JsonAutoDetect` / visibility của `ObjectMapper` |
| Property có được ghi ra JSON không? | Quy tắc serialization, `JsonProperty.Access`, ignore và cấu hình liên quan |
| Property có được nhận từ JSON không? | Quy tắc deserialization, `JsonProperty.Access`, creator/setter/field và cấu hình liên quan |
| Property được đặt tên gì trong JSON? | `@JsonProperty`, naming strategy và metadata liên quan |

## 5. @JsonIgnore, @JsonInclude và JsonView có vai trò khác nhau

Khi điều khiển phạm vi property, bạn có thể gặp nhiều annotation gần nghĩa nhưng mục tiêu khác nhau:

- `@JsonIgnore` đánh dấu property cần bị bỏ qua trong quá trình ánh xạ theo quy tắc ignore.
- `@JsonProperty(access = ...)` chỉ định hướng đọc/ghi của property.
- `@JsonInclude` điều khiển điều kiện đưa giá trị vào JSON khi serialize, ví dụ chỉ ghi property khác null. Nó không quyết định field có được nhận diện hay có được deserialize hay không.
- `@JsonView` chọn nhóm property được đưa vào hoặc đọc theo view tương ứng, khi thao tác sử dụng view đó.
- `@JsonAutoDetect` điều khiển tự động phát hiện thành phần của class.

Ví dụ, `@JsonInclude(Include.NON_NULL)` có thể khiến một property đã được nhận diện nhưng đang có giá trị null bị bỏ khỏi JSON. Điều này khác với `@JsonIgnore`, vốn đánh dấu property bị bỏ qua theo quy tắc ignore. Không nên dùng `@JsonInclude` như một cơ chế bảo vệ trường nhạy cảm.

## 6. Chọn phạm vi cấu hình phù hợp

Hãy ưu tiên phạm vi hẹp nhất đáp ứng đúng yêu cầu:

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Một DTO cần đọc field private | `@JsonAutoDetect` trên DTO hoặc `@JsonProperty` tường minh |
| Toàn bộ kiểu dùng chung một quy tắc field | Cấu hình visibility trên mapper chuyên biệt hoặc mapper toàn cục nếu đó thật sự là chính sách ứng dụng |
| Một thuộc tính chỉ được xuất ra response | `@JsonProperty(access = READ_ONLY)` |
| Một thuộc tính chỉ được nhận từ request | `@JsonProperty(access = WRITE_ONLY)` |
| Một thuộc tính cần bỏ qua hoàn toàn | `@JsonIgnore` hoặc cơ chế ignore phù hợp |
| Chỉ bỏ các giá trị null khi ghi JSON | `@JsonInclude` |
| Các response có tập trường khác nhau | DTO riêng hoặc `@JsonView` với view được cấu hình rõ ràng |

Đối với API công khai, DTO riêng cho request và response thường giúp hợp đồng dữ liệu rõ ràng hơn việc dùng một entity có nhiều quy tắc truy cập. `READ_ONLY` và `WRITE_ONLY` rất hữu ích, nhưng không nên thay thế thiết kế mô hình phù hợp hoặc validation nghiệp vụ.

## 7. Những điểm cần kiểm tra khi cấu hình

Khi một property không xuất hiện hoặc không được gán như mong đợi, hãy kiểm tra theo thứ tự:

1. Jackson có nhận diện property đó không? Kiểm tra field, getter, setter, creator và visibility.
2. Property có bị ignore hoặc bị giới hạn bởi `JsonProperty.Access` không?
3. Tên JSON có khớp với tên property sau khi áp dụng `@JsonProperty` hoặc naming strategy không?
4. Giá trị có bị loại khỏi output do `@JsonInclude` hoặc filter không?
5. Lần đọc/ghi có sử dụng JSON View hoặc reader/writer với cấu hình riêng không?
6. Mapper thực tế của ứng dụng có cấu hình khác mapper trong ví dụ thử nghiệm không?

Đặc biệt trong Spring Boot, controller thường dùng mapper do framework cấu hình. Một đoạn code thử nghiệm tạo `new ObjectMapper()` có thể không phản ánh chính xác mapper được HTTP message converter sử dụng. Khi điều tra lỗi API, hãy xem cấu hình mapper và converter thực tế.

## 8. Ghi nhớ

- Visibility điều khiển việc tự động phát hiện field, getter, setter và creator.
- Property access điều khiển property được dùng ở chiều serialize, deserialize hay cả hai.
- `@JsonAutoDetect` và cấu hình visibility của mapper trả lời câu hỏi Jackson có nhìn thấy thành phần Java hay không.
- `@JsonProperty(access = READ_ONLY/WRITE_ONLY)` điều khiển hướng ánh xạ của một property đã được nhận diện.
- `@JsonIgnore`, `@JsonInclude` và `@JsonView` có mục đích khác nhau; cần chọn đúng annotation thay vì xem chúng là các cách thay thế lẫn nhau.
- Với dữ liệu nhạy cảm, hãy thiết kế DTO và hợp đồng API rõ ràng. Annotation kiểm soát quá trình ánh xạ JSON, không thay thế bảo mật và logic nghiệp vụ.

Khi cấu hình một thuộc tính, hãy xác định riêng ba điều: Jackson tìm thấy property bằng cách nào, property được phép đi theo chiều nào và property được biểu diễn dưới tên nào. Tách ba câu hỏi đó sẽ giúp cấu hình Jackson dễ dự đoán và dễ bảo trì hơn.
