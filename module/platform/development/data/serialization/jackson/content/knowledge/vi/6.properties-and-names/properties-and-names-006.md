# Chấp nhận tên cũ bằng @JsonAlias

Khi một API hoặc file JSON thay đổi tên thuộc tính, ứng dụng có thể cần tiếp tục đọc dữ liệu từ các client cũ trong một khoảng thời gian. Jackson cung cấp annotation `@JsonAlias` để một thuộc tính Java chấp nhận nhiều tên JSON khi **deserialization**.

Alias giúp quá trình chuyển đổi hợp đồng dữ liệu diễn ra từng bước: ứng dụng nhận cả tên mới và tên cũ, trong khi vẫn có thể phát ra một tên chuẩn duy nhất khi serialize. Đây là cách hữu ích để duy trì tương thích ngược mà không phải tạo nhiều thuộc tính Java trùng ý nghĩa.

## 1. Vấn đề khi tên thuộc tính JSON thay đổi

Giả sử API ban đầu nhận JSON có thuộc tính `name`:

```json
{
  "name": "An"
}
```

Sau này, hợp đồng API được chuẩn hóa thành `display_name` để thống nhất cách đặt tên giữa các dịch vụ:

```json
{
  "display_name": "An"
}
```

Nếu ứng dụng chỉ ánh xạ tên mới, client cũ gửi `name` có thể không còn cập nhật được thuộc tính Java như mong đợi. Nếu đổi hẳn tên thuộc tính trong DTO mà không có quy tắc tương thích, những payload đã phát hành trước đó sẽ gặp vấn đề.

Ta muốn đạt được hai điều:

- Khi đọc JSON, chấp nhận cả `display_name` và tên cũ `name`.
- Khi ghi JSON, luôn phát ra tên chuẩn `display_name`.

`@JsonAlias` được thiết kế cho tình huống này.

## 2. @JsonAlias hoạt động như thế nào?

`@JsonAlias` khai báo một hoặc nhiều tên thay thế mà Jackson chấp nhận khi đọc JSON. Annotation thuộc package `com.fasterxml.jackson.annotation` trong Jackson 2.x và được giới thiệu từ phiên bản 2.9.

Cú pháp cơ bản:

```java
@JsonAlias("old_name")
private String newName;
```

Có thể khai báo nhiều alias:

```java
@JsonAlias({"old_name", "legacyName", "previous_name"})
private String newName;
```

Các tên trong alias được ánh xạ vào cùng một logical property của Java. Alias là tên đầu vào bổ sung; nó không tạo thêm field Java và không làm xuất hiện nhiều thuộc tính khác nhau trong object.

### 2.1. Ví dụ đầy đủ với tên chuẩn và tên cũ

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class UserRequest {
    @JsonProperty("display_name")
    @JsonAlias({"name", "displayName", "full_name"})
    private String displayName;

    public UserRequest() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Trong ví dụ:

- `displayName` là tên thuộc tính trong Java.
- `@JsonProperty("display_name")` xác định tên JSON chuẩn.
- `@JsonAlias({"name", "displayName", "full_name"})` cho phép đọc thêm ba tên cũ.

Jackson có thể ánh xạ từng payload sau vào cùng một thuộc tính `displayName`:

```json
{"display_name": "An"}
```

```json
{"name": "An"}
```

```json
{"displayName": "An"}
```

```json
{"full_name": "An"}
```

Mã Java sử dụng cùng một cách đọc:

```java
ObjectMapper mapper = new ObjectMapper();

UserRequest request = mapper.readValue(
    """
    {"name": "An"}
    """,
    UserRequest.class
);

System.out.println(request.getDisplayName());
```

Kết quả:

```text
An
```

Không cần viết nhánh `if/else` để kiểm tra từng tên JSON trước khi gán vào object. Quy tắc tên thay thế được khai báo ngay tại thuộc tính cần ánh xạ.

## 3. Alias chỉ ảnh hưởng đến deserialization

Đây là đặc điểm quan trọng nhất cần nhớ: **`@JsonAlias` chỉ bổ sung tên được chấp nhận khi đọc JSON; nó không thay đổi tên được phát ra khi serialize.**

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

UserRequest request = mapper.readValue(
    """
    {"name": "An"}
    """,
    UserRequest.class
);

String output = mapper.writeValueAsString(request);

System.out.println(output);
```

Kết quả:

```json
{"display_name":"An"}
```

Mặc dù đầu vào dùng tên cũ `name`, đầu ra vẫn dùng tên chuẩn `display_name` do `@JsonProperty` xác định.

Có thể mô tả luồng ánh xạ như sau:

```text
JSON đầu vào
   |
   +-- "display_name" --+
   +-- "name" ----------+--> Java property: displayName
   +-- "displayName" ---+
   +-- "full_name" -----+
                              |
                              v
                         Java object
                              |
                              v
                       JSON đầu ra
                              |
                              +--> "display_name"
```

Cơ chế này giúp API tiếp tục tiếp nhận client cũ nhưng dần thống nhất dữ liệu phát ra theo hợp đồng mới.

Nếu yêu cầu là **serialize ra nhiều tên khác nhau cho những client khác nhau**, `@JsonAlias` không giải quyết được chiều đó. Khi ấy cần thiết kế DTO response riêng, custom serializer hoặc một lớp chuyển đổi response theo phiên bản API.

## 4. Dùng @JsonAlias khi không cần đổi tên chuẩn

Không bắt buộc phải kết hợp `@JsonAlias` với `@JsonProperty`. Nếu tên chuẩn chính là tên Java theo quy tắc Jackson hiện hành, có thể chỉ khai báo alias:

```java
import com.fasterxml.jackson.annotation.JsonAlias;

public class CustomerRequest {
    @JsonAlias({"customer_name", "full_name"})
    private String name;

    public CustomerRequest() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Trong trường hợp này, Jackson đọc được các tên:

- `name` — tên property thông thường.
- `customer_name` — alias.
- `full_name` — alias.

Khi serialize, tên phát ra vẫn là tên chuẩn mà Jackson xác định cho property, ở ví dụ đơn giản này là `name`.

Nếu hợp đồng JSON có tên chuẩn rõ ràng và khác tên Java, nên khai báo `@JsonProperty` để người đọc code thấy ngay tên đầu ra dự kiến. Alias chỉ mô tả các tên tương thích ở chiều vào.

## 5. Đặt @JsonAlias ở đâu?

`@JsonAlias` có thể được đặt trên field, setter hoặc tham số creator/constructor được Jackson sử dụng để tạo object. Nên chọn một vị trí nhất quán với cách lớp đang khai báo property.

### 5.1. Đặt trên field

```java
public class ProductRequest {
    @JsonProperty("product_code")
    @JsonAlias({"code", "sku"})
    private String productCode;

    public ProductRequest() {
    }

    public String getProductCode() {
        return productCode;
    }

    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }
}
```

Cách này dễ đọc khi annotation mô tả trực tiếp một thuộc tính. Jackson cần nhận diện field theo metadata và quy tắc visibility tương ứng; annotation trên field có thể làm field tham gia quá trình introspection ngay cả khi field không public.

### 5.2. Đặt trên setter

Nếu dự án tổ chức annotation tại setter, có thể viết:

```java
public class ProductRequest {
    private String productCode;

    public String getProductCode() {
        return productCode;
    }

    @JsonProperty("product_code")
    @JsonAlias({"code", "sku"})
    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }
}
```

Setter là điểm nhận giá trị trong quá trình data binding kiểu JavaBean. Khi một property có annotation ở nhiều thành phần như field, getter và setter, Jackson hợp nhất metadata theo quy tắc property introspection. Tránh khai báo những tên chuẩn hoặc alias mâu thuẫn ở nhiều vị trí khác nhau vì cấu hình sẽ khó hiểu và khó bảo trì.

### 5.3. Đặt trên constructor parameter

Với lớp bất biến, constructor có thể là điểm tạo object. Khi đó, khai báo tên chuẩn và alias tại tham số:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ImmutableUserRequest {
    private final String displayName;

    @JsonCreator
    public ImmutableUserRequest(
            @JsonProperty("display_name")
            @JsonAlias({"name", "fullName"})
            String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Ở đây, `@JsonProperty` xác định tên property để creator nhận giá trị; `@JsonAlias` thêm các tên đầu vào thay thế. Với constructor nhiều tham số, cần khai báo metadata cho từng tham số theo đúng property tương ứng.

Đối với Java record, có thể đặt annotation trên record component khi phiên bản Jackson đang dùng hỗ trợ record và annotation được truyền tới phần tử mà Jackson introspect:

```java
public record UserRecord(
    @JsonProperty("display_name")
    @JsonAlias({"name", "fullName"})
    String displayName
) {
}
```

Record support phụ thuộc major/minor version Jackson và JDK; nếu dự án dùng phiên bản cũ, hãy kiểm tra khả năng hỗ trợ record trước khi áp dụng mẫu này.

## 6. Chấp nhận nhiều thế hệ tên trong quá trình đổi hợp đồng

Một API có thể đã trải qua nhiều lần đổi tên:

| Thế hệ client | Tên JSON |
|---|---|
| Client cũ nhất | `full_name` |
| Client trung gian | `name` |
| Client hiện tại | `displayName` |
| Hợp đồng chuẩn mới | `display_name` |

Có thể khai báo tất cả tên đầu vào tại một property:

```java
public class ProfileRequest {
    @JsonProperty("display_name")
    @JsonAlias({"full_name", "name", "displayName"})
    private String displayName;

    public ProfileRequest() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Cách này đặc biệt hữu ích khi:

- Có nhiều phiên bản client đang được sử dụng ngoài thực tế.
- Hệ thống nhận dữ liệu từ nhiều nguồn có quy ước đặt tên khác nhau.
- Cần di chuyển dần từ tên snake_case sang camelCase hoặc ngược lại.
- Có dữ liệu lịch sử cần đọc lại sau khi mô hình Java được chuẩn hóa.

Dù có thể khai báo nhiều alias, không nên giữ vô hạn các tên cũ. Mỗi alias là một phần của hợp đồng đầu vào mà ứng dụng phải tiếp tục hỗ trợ và kiểm thử. Hãy ghi nhận nguồn dữ liệu nào còn gửi tên cũ, đặt kế hoạch loại bỏ và xóa alias khi không còn client hoặc dữ liệu cần tương thích.

## 7. @JsonAlias không thay thế các annotation khác

Một số annotation có tên hoặc mục tiêu gần nhau nhưng giải quyết vấn đề khác nhau:

| Annotation | Mục đích |
|---|---|
| `@JsonAlias` | Chấp nhận thêm tên property khi deserialize |
| `@JsonProperty` | Xác định tên property JSON chuẩn và các metadata liên quan |
| `@JsonNaming` | Áp dụng chiến lược đặt tên property cho một lớp |
| `@JsonIgnore` | Bỏ qua property theo quy tắc annotation |
| `@JsonIgnoreProperties` | Bỏ qua các property được liệt kê hoặc property không biết theo cấu hình annotation |
| `@JsonCreator` | Chỉ định constructor/factory dùng để tạo object khi deserialize |

Ví dụ, `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)` có thể đổi quy tắc tên từ `displayName` thành `display_name` cho toàn lớp. Nếu chỉ một property cần nhận tên lịch sử, `@JsonAlias` thường diễn đạt ý định cụ thể hơn.

Không nên dùng `@JsonIgnoreProperties(ignoreUnknown = true)` để thay cho alias. Cấu hình bỏ qua unknown property làm Jackson bỏ qua mọi tên không nhận diện được theo phạm vi cấu hình; nó không ánh xạ tên cũ vào property cần thiết. Nếu client gửi `name` và ứng dụng chỉ bỏ qua unknown property, giá trị đó có thể không được gán vào `displayName`.

## 8. Alias là tên thuộc tính, không phải bí danh của giá trị

`@JsonAlias` tác động lên **key của object JSON**, không tác động lên value.

Ví dụ, alias sau cho phép hai tên key:

```java
@JsonAlias({"state", "current_state"})
private String status;
```

Nó có thể đọc:

```json
{"state": "ACTIVE"}
```

hoặc:

```json
{"current_state": "ACTIVE"}
```

Nhưng nếu hệ thống cũ gửi giá trị `"enabled"` thay cho `"ACTIVE"`, `@JsonAlias` không tự chuyển đổi giá trị đó. Đó là bài toán ánh xạ giá trị, có thể xử lý bằng enum, `@JsonCreator`, custom deserializer hoặc tầng chuyển đổi dữ liệu.

Ví dụ enum nhận các giá trị lịch sử:

```java
import com.fasterxml.jackson.annotation.JsonCreator;

public enum AccountStatus {
    ACTIVE,
    DISABLED;

    @JsonCreator
    public static AccountStatus fromJson(String value) {
        return switch (value.toLowerCase()) {
            case "active", "enabled" -> ACTIVE;
            case "disabled", "inactive" -> DISABLED;
            default -> throw new IllegalArgumentException(
                "Unknown account status: " + value
            );
        };
    }
}
```

Trong ví dụ này, `@JsonCreator` xử lý các cách viết của value. Nó độc lập với việc `@JsonAlias` xử lý tên property.

## 9. Alias có phân biệt chữ hoa/chữ thường không?

Mặc định, tên property JSON được so khớp theo quy tắc phân biệt chữ hoa/chữ thường. Ví dụ alias `user_name` không mặc nhiên có nghĩa là `USER_NAME` hoặc `User_Name` cũng được chấp nhận.

Nếu hệ thống thực sự cần so khớp không phân biệt chữ hoa/chữ thường, Jackson có tính năng cấu hình:

```java
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES)
    .build();
```

Tính năng này ảnh hưởng đến việc nhận diện property nói chung, không chỉ riêng alias. Vì vậy, chỉ bật khi hợp đồng đầu vào cho phép sự khác biệt về chữ hoa/chữ thường; tránh bật toàn cục chỉ để sửa một tên cũ đơn lẻ.

## 10. Xử lý payload chứa đồng thời tên chuẩn và alias

Một payload không nên gửi nhiều key cùng đại diện cho một property:

```json
{
  "display_name": "An",
  "name": "Bình"
}
```

Cả `display_name` và `name` đều trỏ đến `displayName`. Trong quá trình binding, giá trị được gán có thể bị ghi đè theo thứ tự các thuộc tính được xử lý và cơ chế tạo object đang dùng. Với creator property hoặc cấu hình đặc biệt, kết quả cũng cần được kiểm tra theo trường hợp cụ thể.

Không nên dựa vào thứ tự key để quyết định giá trị nghiệp vụ. Cách an toàn hơn là quy định client chỉ gửi một trong các tên được chấp nhận. Nếu cần phát hiện payload mơ hồ, hãy xác thực JSON trước khi bind hoặc dùng custom deserializer để từ chối khi có nhiều tên cùng xuất hiện.

Tương tự, nếu payload chứa một alias nhiều lần hoặc lặp lại key JSON, không nên xem hành vi ghi đè mặc định là một quy tắc nghiệp vụ. Dữ liệu đầu vào cần có một biểu diễn duy nhất cho mỗi giá trị logic.

## 11. Kiểm thử @JsonAlias

Nên kiểm thử cả hai chiều: mọi tên cũ được đọc đúng và tên chuẩn được phát ra khi serialize.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class UserRequestTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsLegacyPropertyNames() throws Exception {
        UserRequest fromOldName = mapper.readValue(
            """
            {"name": "An"}
            """,
            UserRequest.class
        );

        UserRequest fromNewName = mapper.readValue(
            """
            {"display_name": "An"}
            """,
            UserRequest.class
        );

        assertEquals("An", fromOldName.getDisplayName());
        assertEquals("An", fromNewName.getDisplayName());
    }

    @Test
    void serializesUsingCanonicalName() throws Exception {
        UserRequest request = new UserRequest();
        request.setDisplayName("An");

        String json = mapper.writeValueAsString(request);

        assertEquals(
            """
            {"display_name":"An"}
            """.trim(),
            json
        );
    }
}
```

Các test nên được mở rộng theo hợp đồng thực tế:

- Một test cho mỗi alias còn được hỗ trợ.
- Một test cho tên chuẩn.
- Một test xác nhận đầu ra chỉ dùng tên chuẩn.
- Một test cho giá trị null hoặc thiếu trường nếu hai trường hợp có ý nghĩa khác nhau.
- Một test cho payload chứa đồng thời alias và tên chuẩn nếu ứng dụng cần từ chối hoặc xác định chính sách rõ ràng.
- Một test cho phiên bản DTO/record/creator thực tế đang dùng.

## 12. Những giới hạn cần nhớ

`@JsonAlias` là công cụ tương thích tên property đơn giản, không phải cơ chế chuyển đổi schema tổng quát.

- Alias không đổi tên thuộc tính trong Java.
- Alias không làm thay đổi tên được serialize.
- Alias không chuyển đổi value, kiểu dữ liệu hoặc cấu trúc JSON lồng nhau.
- Alias không tự động chấp nhận mọi tên gần giống hoặc khác chữ hoa/chữ thường.
- Alias không thay thế xác thực payload hoặc quản lý phiên bản API.
- Alias không giải quyết trường hợp hai key cùng xuất hiện nhưng mang giá trị mâu thuẫn.

Nếu cần đổi cấu trúc sâu hơn, ví dụ một trường cũ dạng chuỗi được thay bằng object lồng nhau, nên dùng DTO tương thích riêng hoặc custom deserializer để kiểm soát việc chuyển đổi. Không nên cố ép một danh sách alias xử lý một thay đổi schema lớn.

## 13. Quy trình loại bỏ tên cũ

Một quy trình chuyển đổi có thể triển khai theo các bước:

1. Xác định tên chuẩn mới và các tên lịch sử đang xuất hiện trong dữ liệu.
2. Thêm `@JsonAlias` cho những tên cũ cần tiếp tục hỗ trợ.
3. Giữ tên chuẩn bằng `@JsonProperty` khi hợp đồng cần quy định rõ.
4. Kiểm thử đọc dữ liệu của từng thế hệ client và kiểm thử JSON đầu ra.
5. Theo dõi nguồn hoặc phiên bản client còn gửi alias cũ bằng log/metric phù hợp, tránh ghi log dữ liệu nhạy cảm.
6. Thông báo thời hạn ngừng hỗ trợ tên cũ theo chính sách API.
7. Sau khi dữ liệu và client cũ đã được di chuyển, xóa alias không còn cần thiết và cập nhật test.

Alias là một cầu nối trong giai đoạn chuyển đổi. Nó hữu ích nhất khi có kế hoạch kết thúc rõ ràng, thay vì tích lũy mãi các tên cũ trong DTO.

## 14. Ghi nhớ

- `@JsonAlias` cho phép một property nhận nhiều tên JSON khi deserialize.
- Kết hợp `@JsonProperty("canonical_name")` với `@JsonAlias({"oldName", "older_name"})` để tách tên chuẩn và tên tương thích.
- Serialize vẫn dùng tên chuẩn; alias không tạo nhiều key trong JSON đầu ra.
- Alias áp dụng cho key/property, không đổi value; dùng enum creator hoặc custom deserializer nếu cần ánh xạ giá trị.
- Tránh payload chứa đồng thời nhiều tên cho cùng một property và kiểm thử chính sách khi có xung đột.
- Giữ danh sách alias ngắn gọn, theo dõi client cũ và loại bỏ alias khi hết nhu cầu tương thích.

