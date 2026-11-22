# Kiểm tra tham số bắt buộc, tham số thiếu và tham số null

Khi Jackson tạo một đối tượng từ JSON, có ba tình huống cần phân biệt rõ:

1. **Tham số/thuộc tính bắt buộc:** hợp đồng dữ liệu yêu cầu client phải cung cấp giá trị.
2. **Thuộc tính bị thiếu:** tên thuộc tính không xuất hiện trong JSON.
3. **Thuộc tính có giá trị `null`:** tên thuộc tính có xuất hiện nhưng giá trị JSON là `null`.

Hai trường hợp cuối không giống nhau. Ví dụ, `{}` không chứa thuộc tính `name`, trong khi `{"name": null}` có thuộc tính `name` với giá trị null. Jackson có thể xử lý chúng khác nhau tùy cách lớp Java được khởi tạo, annotation và feature đang bật.

Trong chương **Khởi tạo đối tượng** của Data Serialization Jackson, việc phân biệt các tình huống này đặc biệt quan trọng khi dùng constructor hoặc factory method có `@JsonCreator`, JavaBean có setter, record, kiểu primitive và DTO nhận dữ liệu từ API. Nếu không xác định rõ chính sách, đối tượng có thể được tạo với giá trị mặc định ngoài ý muốn hoặc chấp nhận dữ liệu không hợp lệ.

## 1. Phân biệt thuộc tính bị thiếu và thuộc tính null

Xét hai JSON:

```json
{}
```

```json
{
  "name": null
}
```

JSON thứ nhất không có property `name`. JSON thứ hai có property đó và giá trị của nó là `null`. Với một lớp JavaBean có setter, Jackson chỉ gọi setter khi property được cung cấp, trừ khi cấu hình hoặc cơ chế tạo đối tượng có quy tắc khác.

| Dữ liệu JSON | Ý nghĩa |
|---|---|
| `{}` | Không gửi thuộc tính; ứng dụng có thể giữ giá trị khởi tạo hoặc giá trị mặc định. |
| `{"name": null}` | Gửi thuộc tính một cách tường minh với giá trị null. |
| `{"name": "An"}` | Gửi thuộc tính với giá trị chuỗi. |
| `{"name": ""}` | Gửi chuỗi rỗng; đây không phải null và cũng không phải thuộc tính bị thiếu. |

Sự khác biệt này thường quan trọng với API cập nhật. Một request có thể muốn giữ nguyên giá trị hiện tại nếu client bỏ qua field, nhưng xóa giá trị nếu client gửi `null`. Nếu ứng dụng gộp hai trường hợp thành một, ý nghĩa cập nhật sẽ bị thay đổi.

## 2. Giá trị mặc định khi thuộc tính bị thiếu

### 2.1. JavaBean có constructor không tham số

Với một lớp JavaBean thông thường, Jackson có thể gọi constructor không tham số rồi gán các property có mặt trong JSON thông qua setter hoặc field được phép truy cập.

```java
public class ProfileRequest {
    private String displayName = "Guest";
    private int retryCount = 3;

    public ProfileRequest() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
```

Khi đọc JSON:

```java
ObjectMapper mapper = new ObjectMapper();

ProfileRequest a = mapper.readValue("{}", ProfileRequest.class);
ProfileRequest b = mapper.readValue(
        "{\"displayName\": null, \"retryCount\": 5}",
        ProfileRequest.class
);
```

Kết quả điển hình:

- Với `{}`, constructor chạy và không có setter nào được gọi. `displayName` giữ giá trị khởi tạo `"Guest"`, `retryCount` giữ `3`.
- Với JSON thứ hai, setter của `displayName` nhận null theo chính sách mặc định, còn `retryCount` được gán thành `5`.

Nếu không có giá trị khởi tạo, thuộc tính bị thiếu thường giữ giá trị mặc định của Java: `null` cho kiểu tham chiếu, `0` cho kiểu số nguyên, `false` cho `boolean` và `\u0000` cho `char`.

### 2.2. Kiểu primitive và kiểu wrapper

`int` và `Integer` có hành vi khác nhau khi nhận JSON null:

```java
public class Counts {
    private int primitiveCount;
    private Integer wrapperCount;

    public int getPrimitiveCount() {
        return primitiveCount;
    }

    public void setPrimitiveCount(int primitiveCount) {
        this.primitiveCount = primitiveCount;
    }

    public Integer getWrapperCount() {
        return wrapperCount;
    }

    public void setWrapperCount(Integer wrapperCount) {
        this.wrapperCount = wrapperCount;
    }
}
```

Với cấu hình Jackson mặc định thường dùng:

- Nếu field bị thiếu, `primitiveCount` giữ `0`; `wrapperCount` giữ `null`.
- Nếu JSON gửi `wrapperCount: null`, giá trị wrapper là `null`.
- Nếu JSON gửi `primitiveCount: null`, Jackson thường dùng giá trị mặc định của primitive (`0`) nếu không bật feature từ chối null cho primitive.

Nếu `null` không hợp lệ đối với primitive, có thể bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` để Jackson báo lỗi thay vì âm thầm chuyển null thành giá trị mặc định.

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Feature này xử lý trường hợp JSON có giá trị null cho kiểu primitive. Nó không biến một thuộc tính primitive bị thiếu thành lỗi trong mọi trường hợp JavaBean. Để kiểm soát property bị thiếu trong creator, xem các feature dành cho creator ở phần sau.

## 3. Kiểm tra tham số bắt buộc trong constructor với `@JsonCreator`

Khi đối tượng được tạo thông qua constructor hoặc factory method, Jackson cần biết tham số nào tương ứng với property JSON nào. `@JsonCreator` cùng `@JsonProperty` giúp khai báo mối liên hệ đó.

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class CreateUserRequest {
    private final String username;
    private final Integer age;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public CreateUserRequest(
            @JsonProperty(value = "username", required = true) String username,
            @JsonProperty("age") Integer age
    ) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
```

Trong ví dụ, `username` được đánh dấu `required = true`, còn `age` là tham số tùy chọn. `@JsonCreator.Mode.PROPERTIES` chỉ rõ Jackson tạo đối tượng bằng cách ánh xạ các property JSON vào tham số constructor.

### 3.1. `required = true` có ý nghĩa gì?

`@JsonProperty(required = true)` khai báo property bắt buộc phải có trong dữ liệu đầu vào khi dùng creator-based deserialization. Đặc biệt, metadata `required` được hỗ trợ cho tham số constructor/factory creator; không nên hiểu rằng gắn `required = true` lên mọi field hoặc setter sẽ tự động kiểm tra tất cả request JavaBean.

Một điểm quan trọng: **property có mặt và có giá trị null vẫn là property đã được gửi**. `required = true` chủ yếu thể hiện yêu cầu property phải hiện diện. Nếu giá trị null cũng không được phép, cần thêm chính sách từ chối null hoặc kiểm tra trong constructor/validation.

### 3.2. Bật kiểm tra thiếu creator property

Jackson cung cấp feature:

```java
DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES
```

Khi bật, Jackson từ chối creator property bị thiếu thay vì truyền giá trị mặc định/null cho tham số tương ứng. Đây là chính sách rộng cho các property tham gia creator; nó có thể khiến những tham số vốn được thiết kế là tùy chọn cũng trở thành bắt buộc. Hãy cân nhắc phạm vi trước khi bật toàn cục.

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
```

Nếu chỉ một vài tham số là bắt buộc, `required = true` trên đúng creator parameter thường thể hiện hợp đồng rõ hơn việc bật feature toàn cục.

## 4. Phân biệt creator property bị thiếu và creator property null

Jackson có hai feature riêng để kiểm soát hai trường hợp:

| Feature | Trường hợp bị từ chối |
|---|---|
| `FAIL_ON_MISSING_CREATOR_PROPERTIES` | Creator property không xuất hiện trong JSON. |
| `FAIL_ON_NULL_CREATOR_PROPERTIES` | Creator property có mặt nhưng giá trị là JSON null. |

Có thể bật cả hai khi mọi creator parameter đều phải có giá trị khác null:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
mapper.enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES);
```

Khi bật cả hai, JSON `{}` sẽ thất bại nếu kiểu đích có creator property cần cung cấp. JSON `{"username": null}` cũng thất bại nếu `username` là creator property. Cấu hình này thích hợp với hợp đồng chặt chẽ, nhưng không phù hợp nếu constructor có tham số tùy chọn.

Nếu muốn một số tham số tùy chọn, có thể:

- Không bật feature toàn cục và đánh dấu `required = true` cho đúng tham số bắt buộc.
- Kiểm tra giá trị bắt buộc ngay trong constructor/factory method.
- Dùng kiểu wrapper để biểu diễn khả năng null một cách rõ ràng.
- Tách request thành các kiểu khác nhau nếu mỗi thao tác có hợp đồng đầu vào khác nhau.

## 5. Kiểm tra null cho property JavaBean bằng `@JsonSetter`

Với lớp dùng setter thay vì creator, `@JsonSetter` cho phép quy định cách xử lý khi property có giá trị JSON null.

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class UpdateProfileRequest {
    private String displayName = "Guest";

    public String getDisplayName() {
        return displayName;
    }

    @JsonSetter(value = "displayName", nulls = Nulls.FAIL)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Với cấu hình này:

- `{}` không gọi setter; giá trị khởi tạo `"Guest"` được giữ lại.
- `{"displayName": null}` bị từ chối vì `Nulls.FAIL`.
- `{"displayName": "An"}` gọi setter với chuỗi `"An"`.

`Nulls` có các chính sách thường dùng:

| Chính sách | Hành vi khi property có giá trị null |
|---|---|
| `Nulls.SET` | Gán giá trị null theo cách xử lý thông thường; đây là mặc định phổ biến. |
| `Nulls.SKIP` | Bỏ qua việc gán; giá trị hiện tại hoặc giá trị khởi tạo được giữ nguyên. |
| `Nulls.FAIL` | Báo lỗi khi nhận null. |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng do deserializer của kiểu đích cung cấp, chẳng hạn chuỗi rỗng hoặc collection rỗng. |
| `Nulls.DEFAULT` | Dùng chính sách mặc định được cấu hình cho property hoặc mapper. |

Ví dụ dùng `Nulls.SKIP` để null không ghi đè giá trị khởi tạo:

```java
@JsonSetter(value = "displayName", nulls = Nulls.SKIP)
public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
```

Khi JSON gửi `displayName: null`, setter không được áp dụng giá trị null; `displayName` vẫn giữ `"Guest"`. Tuy nhiên, nếu property bị thiếu, setter cũng không được gọi. Vì thế, trong ví dụ này cả thiếu và null đều giữ giá trị hiện tại, dù chúng vẫn là hai trạng thái đầu vào khác nhau.

### 5.1. `Nulls` áp dụng cho phần tử collection

`@JsonSetter` còn có thuộc tính `contentNulls` để điều khiển phần tử null bên trong collection hoặc map:

```java
@JsonSetter(value = "tags", contentNulls = Nulls.FAIL)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Với `{"tags": ["java", null]}`, Jackson báo lỗi vì phần tử thứ hai là null. Đây là kiểm soát null của nội dung collection, khác với `nulls`, vốn kiểm soát chính property `tags`.

## 6. Giá trị mặc định và `@JsonProperty(defaultValue)`

Jackson có thuộc tính `defaultValue` trên `@JsonProperty` để cung cấp metadata về giá trị mặc định. Tuy nhiên, trong Jackson Databind thông thường, metadata này không tự động khiến Jackson gán giá trị đó vào property khi JSON thiếu field.

```java
@JsonProperty(value = "retryCount", defaultValue = "3")
private int retryCount;
```

Không nên cho rằng annotation trên chắc chắn làm `retryCount` thành `3`. Để thực sự có giá trị mặc định, có thể dùng field initializer, constructor, factory method hoặc logic khởi tạo rõ ràng.

Ví dụ dùng constructor để gán mặc định cho tham số tùy chọn:

```java
public final class RetryOptions {
    private final Integer retryCount;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public RetryOptions(@JsonProperty("retryCount") Integer retryCount) {
        this.retryCount = retryCount == null ? 3 : retryCount;
    }

    public Integer getRetryCount() {
        return retryCount;
    }
}
```

Với cách viết này, cả trường hợp thiếu `retryCount` và trường hợp gửi `retryCount: null` đều được quy về giá trị `3`, nếu không bật feature từ chối creator property tương ứng. Nếu nghiệp vụ cần phân biệt hai trường hợp, không nên gộp chúng bằng điều kiện `null` như trên; hãy dùng cách đọc có khả năng theo dõi sự hiện diện của property hoặc một mô hình request phù hợp.

## 7. Record và đối tượng bất biến

Java record thường được Jackson hỗ trợ thông qua canonical constructor. Mỗi thành phần record tương ứng với một creator property. Có thể khai báo rõ tên JSON và quy tắc bắt buộc:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record RegisterRequest(
        @JsonProperty(value = "username", required = true) String username,
        @JsonProperty("display_name") String displayName
) {
    public RegisterRequest {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username is required");
        }
    }
}
```

Record là bất biến sau khi tạo, nên Jackson phải cung cấp các giá trị creator trước khi constructor hoàn tất. Các feature dành cho missing/null creator properties có thể được dùng để kiểm soát đầu vào. Kiểm tra trong compact constructor giúp bảo vệ invariant của chính đối tượng, kể cả khi đối tượng được tạo từ code Java chứ không phải JSON.

Khả năng nhận diện record và một số chi tiết constructor phụ thuộc phiên bản Java và Jackson. Với các lớp bất biến thông thường, dùng `@JsonCreator` và `@JsonProperty` tường minh giúp ánh xạ tham số rõ ràng hơn.

## 8. Kiểm tra dữ liệu sau khi Jackson tạo đối tượng

Jackson giải quyết việc phân tích JSON và ánh xạ giá trị vào đối tượng. Điều đó không đồng nghĩa mọi quy tắc nghiệp vụ đã được kiểm tra. Một giá trị có thể đúng kiểu Java nhưng vẫn không hợp lệ, ví dụ:

- Chuỗi `username` có mặt nhưng chỉ chứa dấu cách.
- Số lượng `quantity` có mặt nhưng nhỏ hơn 1.
- Ngày bắt đầu có mặt nhưng nằm sau ngày kết thúc.
- Email đúng kiểu chuỗi nhưng không đúng định dạng mong muốn.

Có thể dùng Jakarta Bean Validation để biểu diễn các ràng buộc:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull @Positive Integer quantity
) {
}
```

Trong Spring MVC, có thể yêu cầu validation cho request body:

```java
@PostMapping("/orders")
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
```

`@NotNull` kiểm tra null sau khi đối tượng đã được tạo; `@NotBlank` còn kiểm tra chuỗi không null, không rỗng và có ít nhất một ký tự không phải khoảng trắng; `@Positive` kiểm tra số lớn hơn 0. Để validation hoạt động, ứng dụng cần dependency/provider Bean Validation phù hợp (ví dụ starter validation trong Spring Boot).

Hãy phân biệt:

- **Ràng buộc cấu trúc/ánh xạ:** JSON có đúng kiểu và có đủ creator property theo chính sách Jackson không?
- **Ràng buộc dữ liệu:** giá trị có null, rỗng hoặc nằm ngoài miền cho phép không?
- **Ràng buộc nghiệp vụ:** người dùng hiện tại có quyền thực hiện thao tác và trạng thái hệ thống có cho phép không?

Ba lớp kiểm tra có thể phối hợp nhưng không thay thế lẫn nhau.

## 9. Xử lý lỗi khi thiếu tham số hoặc gửi null

Khi Jackson không thể tạo đối tượng do thiếu creator property, null không hợp lệ hoặc null cho primitive bị từ chối, thao tác đọc JSON có thể ném ngoại lệ ánh xạ như `MismatchedInputException` hoặc lớp con của `JsonMappingException`.

Ở tầng API, lỗi cú pháp hoặc lỗi ánh xạ request thường được chuyển thành phản hồi `400 Bad Request`. Với Spring MVC, lỗi validation sau khi binding cũng cần được xử lý để trả thông báo dễ hiểu, chẳng hạn tên field và quy tắc bị vi phạm. Tránh trả stack trace, nội dung nội bộ hoặc dữ liệu nhạy cảm trong response lỗi.

Ví dụ về các tình huống cần kiểm tra:

| JSON đầu vào | Chính sách | Kết quả mong đợi |
|---|---|---|
| `{}` | `username` là creator property required | Lỗi thiếu property. |
| `{"username": null}` | Bật `FAIL_ON_NULL_CREATOR_PROPERTIES` hoặc kiểm tra null trong constructor | Lỗi null không hợp lệ. |
| `{"username": "An"}` | `username` bắt buộc, `age` tùy chọn | Tạo đối tượng thành công. |
| `{"displayName": null}` | Setter dùng `Nulls.FAIL` | Lỗi null ở property. |
| `{"retryCount": null}` | Primitive và bật `FAIL_ON_NULL_FOR_PRIMITIVES` | Lỗi null cho primitive. |
| `{"quantity": 0}` | Bean Validation dùng `@Positive` | Binding có thể thành công, validation thất bại. |

## 10. Chọn chính sách phù hợp

| Nhu cầu | Cơ chế nên xem xét |
|---|---|
| Một tham số constructor/factory bắt buộc phải xuất hiện | `@JsonProperty(required = true)` trên creator property |
| Mọi creator property đều phải có mặt | `FAIL_ON_MISSING_CREATOR_PROPERTIES` |
| Mọi creator property đều phải khác null | `FAIL_ON_NULL_CREATOR_PROPERTIES` |
| JSON null cho primitive phải bị từ chối | `FAIL_ON_NULL_FOR_PRIMITIVES` |
| Một JavaBean property không chấp nhận null | `@JsonSetter(nulls = Nulls.FAIL)` |
| Null không được ghi đè giá trị hiện có | `@JsonSetter(nulls = Nulls.SKIP)` |
| Null trong phần tử collection phải bị từ chối | `@JsonSetter(contentNulls = Nulls.FAIL)` |
| Giá trị thiếu cần có mặc định thực sự | Field initializer, constructor hoặc factory method |
| Chuỗi/số phải thỏa quy tắc nghiệp vụ | Jakarta Bean Validation hoặc kiểm tra trong domain constructor |

Khi thiết kế DTO nhận JSON, hãy quyết định riêng cho từng property: có bắt buộc xuất hiện không, có được phép null không, và giá trị có cần kiểm tra thêm sau khi binding không. Đừng đồng nhất thuộc tính bị thiếu với thuộc tính null, cũng đừng dựa vào giá trị mặc định của Java như một cách kiểm tra dữ liệu. Jackson cung cấp creator annotations, deserialization features và null-handling policies để kiểm soát quá trình tạo đối tượng; constructor và Bean Validation giúp bảo vệ các ràng buộc của dữ liệu sau khi ánh xạ.
