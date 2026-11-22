# Kiểm tra thuộc tính không khai báo view và cấu hình liên quan

Jackson hỗ trợ JSON Views để tạo những cách biểu diễn khác nhau của cùng một đối tượng. Ví dụ, API công khai có thể trả về tên và mã người dùng, trong khi API quản trị cần thêm email hoặc trạng thái nội bộ. Annotation `@JsonView` đánh dấu thuộc tính thuộc view nào; `ObjectWriter.withView(...)` hoặc tích hợp của Spring MVC chọn view cần dùng khi serialize.

Một chi tiết dễ gây rò rỉ dữ liệu là **thuộc tính không khai báo `@JsonView` vẫn có thể xuất hiện khi một view đang hoạt động**. Hành vi này được điều khiển bởi `MapperFeature.DEFAULT_VIEW_INCLUSION`. Feature này được bật mặc định trong Jackson Databind: property không có view annotation được xem là thuộc mọi view. Nếu tắt feature, property không khai báo view sẽ bị loại khỏi quá trình ánh xạ khi một view cụ thể đang được kích hoạt.

Vì vậy, khi dùng JSON Views để kiểm soát đầu ra, cần hiểu rõ ba điều: view nào đang hoạt động, property nào được gắn view, và chính sách dành cho property không có annotation. Nếu chỉ thêm `@JsonView` vào một vài field mà không kiểm tra cấu hình mặc định, các field còn lại vẫn có thể được serialize.

## 1. JSON View dùng để làm gì?

Một lớp Java có thể được sử dụng ở nhiều endpoint nhưng mỗi endpoint cần một tập thuộc tính khác nhau. Ví dụ, thông tin tài khoản:

```java
public class UserResponse {
    private long id;
    private String username;
    private String email;
    private String role;
    private String passwordHash;
}
```

API công khai chỉ cần `id` và `username`. API nội bộ có thể cần thêm `email` và `role`. Nếu serialize toàn bộ object, những field không nên xuất hiện có thể bị trả ra ngoài.

Jackson cung cấp `@JsonView` để gắn một property với một hoặc nhiều view marker. View marker thường là interface hoặc class rỗng, chỉ dùng để định danh nhóm thuộc tính.

```java
public final class UserViews {
    private UserViews() {
    }

    public interface Public {
    }

    public interface Internal extends Public {
    }
}
```

DTO khai báo view:

```java
import com.fasterxml.jackson.annotation.JsonView;

public class UserResponse {
    @JsonView(UserViews.Public.class)
    private long id;

    @JsonView(UserViews.Public.class)
    private String username;

    @JsonView(UserViews.Internal.class)
    private String email;

    @JsonView(UserViews.Internal.class)
    private String role;

    // Không có @JsonView.
    private String displayLabel;

    // Không nên đưa passwordHash vào response DTO.
    private String passwordHash;

    // Getter và setter.
}
```

Khi serialize với view `Public`, Jackson chọn các property phù hợp với view đang hoạt động và chính sách inclusion. Khi serialize với `Internal`, các thuộc tính của view `Internal` được xét; do `Internal` kế thừa `Public`, những thuộc tính được gắn `Public` cũng được xem là thuộc view `Internal`.

## 2. Kích hoạt view khi serialize

Đánh dấu `@JsonView` trên DTO chưa đủ để lọc đầu ra. Ứng dụng phải chọn view khi ghi JSON.

Với `ObjectMapper`, có thể tạo `ObjectWriter`:

```java
ObjectMapper mapper = new ObjectMapper();

String publicJson = mapper
    .writerWithView(UserViews.Public.class)
    .writeValueAsString(user);

String internalJson = mapper
    .writerWithView(UserViews.Internal.class)
    .writeValueAsString(user);
```

`writerWithView(...)` tạo writer áp dụng view cho lần serialize. Cách này hữu ích khi adapter cần chọn một trong vài dạng đầu ra cho cùng DTO.

Nếu không kích hoạt view, Jackson thực hiện serialization theo các quy tắc thông thường của mapper. Chỉ khai báo `@JsonView` trên field không tự động làm field biến mất khỏi mọi output không có view. Các quy tắc khác như `@JsonIgnore`, visibility, inclusion và serializer vẫn có hiệu lực độc lập.

## 3. Thuộc tính không khai báo view có thể được đưa vào mọi view

Đây là hành vi cần đặc biệt chú ý. Feature điều khiển nó là:

```java
MapperFeature.DEFAULT_VIEW_INCLUSION
```

Theo mặc định, feature này được bật. Khi một view đang hoạt động:

- Property có `@JsonView` được xét theo view đã chọn.
- Property không có `@JsonView` vẫn được bao gồm trong view, nếu `DEFAULT_VIEW_INCLUSION` đang bật.

Ví dụ:

```java
public class ProfileResponse {
    @JsonView(UserViews.Public.class)
    private String username = "lan";

    @JsonView(UserViews.Internal.class)
    private String email = "lan@example.com";

    // Không khai báo view.
    private String internalComment = "Imported from legacy system";
}
```

Với cấu hình mặc định và active view `Public`, output có thể chứa:

```json
{
  "username": "lan",
  "internalComment": "Imported from legacy system"
}
```

`email` không thuộc view `Public`, nhưng `internalComment` không có annotation nên được bao gồm theo `DEFAULT_VIEW_INCLUSION` mặc định.

Đây là lý do một DTO có một vài field được đánh dấu `@JsonView` vẫn có thể trả ra các thuộc tính ngoài dự kiến. Khi cần chính sách allowlist, phải cấu hình rõ cách xử lý các field không khai báo view.

## 4. Tắt DEFAULT_VIEW_INCLUSION

Để loại bỏ các property không có view annotation khi một view đang hoạt động, tắt `MapperFeature.DEFAULT_VIEW_INCLUSION`.

Với `ObjectMapper`:

```java
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.configure(MapperFeature.DEFAULT_VIEW_INCLUSION, false);
```

Hoặc dùng `JsonMapper` builder trong các phiên bản Jackson hỗ trợ:

```java
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
    .build();
```

Sau khi tắt feature, với active view `Public`, output của ví dụ trên chỉ còn property được khai báo cho view phù hợp:

```json
{
  "username": "lan"
}
```

`email` thuộc `Internal`, còn `internalComment` không khai báo view nên cả hai đều bị loại khỏi view `Public`.

### 4.1. Cấu hình trước khi mapper được sử dụng

`ObjectMapper` được thiết kế để tái sử dụng an toàn giữa nhiều thread khi cấu hình đã hoàn tất trước lần đọc/ghi đầu tiên. Hãy thiết lập `DEFAULT_VIEW_INCLUSION` trong giai đoạn khởi tạo ứng dụng, trước khi mapper được dùng.

Không nên bật/tắt feature này theo từng request trên một mapper dùng chung:

```java
// Không nên thay đổi mapper singleton theo request.
mapper.configure(MapperFeature.DEFAULT_VIEW_INCLUSION, requestNeedsDefaults);
```

Hai request chạy đồng thời có thể cần các chính sách khác nhau. Thay đổi cấu hình chung khi mapper đang được sử dụng khiến hành vi khó dự đoán và có thể tạo lỗ hổng đầu ra.

Nếu các nhóm endpoint thật sự cần chính sách mapper khác nhau, hãy tạo mapper riêng tại composition root hoặc cấu hình rõ DTO/view cho từng hợp đồng. Đối với việc chỉ chọn view khác nhau, `ObjectWriter.withView(...)` là lựa chọn phù hợp; feature default inclusion vẫn là chính sách cấu hình của mapper.

## 5. Bảng hành vi của thuộc tính không khai báo view

Giả sử một lớp có ba property:

```java
public class ReportResponse {
    @JsonView(UserViews.Public.class)
    private String title = "Monthly report";

    @JsonView(UserViews.Internal.class)
    private String costBreakdown = "Internal figures";

    private String generatedBy = "report-job";
}
```

Kết quả khi có active view:

| Active view | `DEFAULT_VIEW_INCLUSION` | `title` | `costBreakdown` | `generatedBy` không annotation |
|---|---|---|---|---|
| `Public` | `true` | Có | Không | Có |
| `Public` | `false` | Có | Không | Không |
| `Internal` kế thừa `Public` | `true` | Có | Có | Có |
| `Internal` kế thừa `Public` | `false` | Có | Có | Không |

Khi không kích hoạt view, việc lọc theo `@JsonView` không được áp dụng như một allowlist; các property vẫn được xem xét theo quy tắc serialization thông thường. Vì vậy, tắt `DEFAULT_VIEW_INCLUSION` không có nghĩa mọi property không annotation luôn bị ẩn trong mọi response. Nó điều chỉnh hành vi **khi một view cụ thể đang hoạt động**.

## 6. Quan hệ kế thừa giữa các view

View thường được tổ chức theo quan hệ kế thừa để view chi tiết bao gồm các thuộc tính của view cơ sở:

```java
public final class Views {
    private Views() {
    }

    public interface Summary {
    }

    public interface Public extends Summary {
    }

    public interface Admin extends Public {
    }
}
```

Ví dụ DTO:

```java
public class AccountResponse {
    @JsonView(Views.Summary.class)
    private long id;

    @JsonView(Views.Public.class)
    private String username;

    @JsonView(Views.Admin.class)
    private String email;
}
```

Khi chọn view `Admin`, các thuộc tính được đánh dấu `Summary`, `Public` và `Admin` được đưa vào do quan hệ kế thừa. Khi chọn `Public`, property `Admin` không được đưa vào.

Quan hệ kế thừa giúp tránh lặp annotation trên từng field. Tuy nhiên, cần thiết kế cây view đơn giản và dễ hiểu. Nếu view có nhiều nhánh không liên quan, một class kế thừa có thể vô tình kéo theo nhiều property hơn dự kiến.

Một property có thể thuộc nhiều view:

```java
@JsonView({Views.Public.class, ExportView.class})
private String reference;
```

Khi dùng nhiều view marker, hãy kiểm tra output thực tế cho từng view và tránh tạo quá nhiều tổ hợp khó theo dõi.

## 7. Cấu hình trong Spring Boot

Spring Boot thường tự tạo `ObjectMapper` và dùng nó trong HTTP message converter. Có thể cấu hình mapper feature qua `application.yml`:

```yaml
spring:
  jackson:
    mapper:
      default-view-inclusion: false
```

Hoặc trong `application.properties`:

```properties
spring.jackson.mapper.default-view-inclusion=false
```

Tên property tương ứng với `MapperFeature.DEFAULT_VIEW_INCLUSION`. Hãy kiểm tra phiên bản Spring Boot và cấu hình thực tế của ứng dụng; nếu đã tự cung cấp `ObjectMapper` bean hoặc customizer khác, cấu hình riêng có thể thay đổi cách auto-configuration hoạt động.

Không nên tạo `new ObjectMapper()` trong controller hoặc service chỉ để dùng `@JsonView`, vì mapper đó có thể không mang các module, naming strategy, date format, mix-in và chính sách đã cấu hình cho HTTP converter của Spring Boot.

### 7.1. Chọn view trên controller method

Spring MVC hỗ trợ annotation `@JsonView` trên handler method để chọn view cho response:

```java
import com.fasterxml.jackson.annotation.JsonView;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users/public")
    @JsonView(UserViews.Public.class)
    public UserResponse getPublicUser() {
        return userService.getUser();
    }

    @GetMapping("/users/internal")
    @JsonView(UserViews.Internal.class)
    public UserResponse getInternalUser() {
        return userService.getUser();
    }
}
```

Spring sử dụng view đã chọn khi serialize giá trị trả về. Hãy xác nhận endpoint nào thực sự bật view và DTO nào được trả về. Một method không có `@JsonView` không tự động bị giới hạn bởi view được khai báo ở method khác.

Nếu cần chọn view động, Spring có `MappingJacksonValue`:

```java
MappingJacksonValue wrapper = new MappingJacksonValue(userResponse);
wrapper.setSerializationView(UserViews.Public.class);
return wrapper;
```

Chọn view động phải dựa trên chính sách endpoint và quyền đã được xác thực ở tầng ứng dụng. Không để client tự gửi tên class view tùy ý rồi phản chiếu thành kiểu Java.

## 8. DEFAULT_VIEW_INCLUSION ảnh hưởng đến deserialize

`MapperFeature.DEFAULT_VIEW_INCLUSION` là mapper feature, không chỉ là tùy chọn định dạng output. Nó cũng ảnh hưởng tới cách xử lý property không khai báo view khi một view được kích hoạt trong quá trình deserialization.

Có thể tạo reader với view:

```java
ObjectReader publicReader = mapper
    .readerWithView(UserViews.Public.class)
    .forType(UserRequest.class);

UserRequest request = publicReader.readValue(json);
```

Nếu feature mặc định đang bật, property không có view annotation có thể vẫn được nhận trong view. Nếu tắt, property không có view annotation bị loại khỏi view đang hoạt động.

Với API nhận dữ liệu, cần xác định rõ mục đích: view có thể giới hạn những thuộc tính Jackson gán từ JSON, nhưng không thay thế validation hoặc authorization. Một client gửi field bị bỏ qua không có nghĩa request hợp lệ về nghiệp vụ; ứng dụng vẫn cần kiểm tra quyền và trạng thái.

Nếu cần kiểm soát chặt request và response, DTO riêng cho từng mục đích thường dễ hiểu hơn việc dùng một model và dựa vào nhiều view cho cả hai chiều.

## 9. Phân biệt view với các cơ chế lọc property khác

JSON View chỉ là một trong nhiều cách kiểm soát property khi serialize.

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| `@JsonView` | Chọn nhóm property theo view đang hoạt động | Có thể áp dụng ở nhiều endpoint với cùng DTO |
| `MapperFeature.DEFAULT_VIEW_INCLUSION` | Quyết định property không có view annotation có được đưa vào view hay không | Chính sách mapper khi view đang hoạt động |
| `@JsonIgnore` | Bỏ property khỏi quá trình Jackson xử lý theo annotation | Property cụ thể |
| `@JsonProperty(access = WRITE_ONLY)` | Cho phép đọc từ JSON nhưng không ghi ra JSON | Property cụ thể |
| `@JsonInclude` | Quyết định property có giá trị nào được đưa vào output | Chính sách inclusion khi serialize |
| DTO riêng | Mô tả rõ tập dữ liệu của từng hợp đồng | Từng request/response hoặc use case |
| Filter (`@JsonFilter`, `FilterProvider`) | Lọc property động theo filter id | Khi cần lựa chọn property linh hoạt lúc chạy |

Không nhầm `DEFAULT_VIEW_INCLUSION` với `JsonInclude.Include.NON_NULL`. Một feature quyết định property không gắn view có thuộc active view hay không; `@JsonInclude` quyết định property có được ghi dựa trên giá trị của nó hay không. Một property có thể thuộc view nhưng vẫn bị bỏ qua vì giá trị null và inclusion policy, hoặc không thuộc view nên bị loại trước khi giá trị được ghi.

## 10. Không dùng JSON View làm ranh giới bảo mật duy nhất

JSON View giúp định hình response nhưng không phải cơ chế authorization. Một số rủi ro thường gặp:

- Endpoint quên kích hoạt view và serialize DTO theo quy tắc thông thường.
- Mapper khác được tạo riêng với cấu hình `DEFAULT_VIEW_INCLUSION` khác.
- Một property nhạy cảm không khai báo view nhưng được bao gồm do default inclusion bật.
- View kế thừa một view cơ sở có thêm field ngoài dự kiến.
- Entity persistence có quan hệ hoặc field nội bộ không nên xuất hiện trong response.
- Một serializer tùy chỉnh hoặc wrapper trả dữ liệu theo đường khác với view dự kiến.

Đối với dữ liệu nhạy cảm như mật khẩu, token, secret, thông tin thanh toán hoặc dữ liệu nội bộ, cách an toàn hơn là không đưa chúng vào response DTO. Nếu một field tuyệt đối không được trả ra, dùng response model chỉ chứa dữ liệu được phép hoặc annotation loại trừ rõ ràng như `@JsonIgnore` theo thiết kế phù hợp.

Quyền xem dữ liệu phải được kiểm tra ở application/service layer. Ví dụ, chỉ người có quyền quản trị mới được gọi use case trả về `AdminUserResponse`. Việc chọn `Admin` view không tự xác minh người gọi là admin.

## 11. Kiểm tra cấu hình hiện tại

Khi điều tra vì sao một field không có `@JsonView` vẫn xuất hiện, kiểm tra mapper đang thực sự được sử dụng:

```java
boolean defaultViewInclusion = mapper.isEnabled(
    MapperFeature.DEFAULT_VIEW_INCLUSION
);

System.out.println("DEFAULT_VIEW_INCLUSION = " + defaultViewInclusion);
```

Nếu kết quả là `true`, property không khai báo view được bao gồm trong active view. Nếu là `false`, property không khai báo view bị loại khi active view được chọn.

Trong ứng dụng Spring Boot, cần kiểm tra mapper do framework sử dụng trong HTTP message converter, không chỉ một mapper tự tạo trong unit test. Có thể kiểm tra cấu hình qua context hoặc kiểm thử endpoint thực tế. Nếu ứng dụng có nhiều mapper/converter, mỗi mapper có thể có chính sách khác nhau.

Khi kiểm tra response, nên xác nhận:

1. Controller method hoặc writer có kích hoạt đúng view không.
2. View class có quan hệ kế thừa nào không.
3. Property được Jackson nhận diện từ field, getter, setter hay record component nào.
4. Property có `@JsonView` hay không và annotation có được đặt nhất quán không.
5. `DEFAULT_VIEW_INCLUSION` trên mapper đang serialize là `true` hay `false`.
6. Có mapper bean, converter, mix-in, serializer hoặc filter nào khác thay đổi kết quả không.
7. Có annotation `@JsonIgnore`, `@JsonInclude` hoặc access mode nào tác động thêm không.

## 12. Kiểm thử thuộc tính không khai báo view

Nên viết test rõ ràng cho cả hai chính sách. Ví dụ DTO:

```java
public final class Views {
    private Views() {
    }

    public interface Public {
    }

    public interface Admin extends Public {
    }
}

public class UserViewDto {
    @JsonView(Views.Public.class)
    private String username = "lan";

    @JsonView(Views.Admin.class)
    private String email = "lan@example.com";

    private String internalNote = "private note";

    // Getter và setter.
}
```

Kiểm thử khi default inclusion bật:

```java
@Test
void unannotatedPropertyIsIncludedByDefault() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    UserViewDto dto = new UserViewDto();

    JsonNode json = mapper.readTree(
        mapper.writerWithView(Views.Public.class)
            .writeValueAsString(dto)
    );

    assertTrue(json.has("username"));
    assertFalse(json.has("email"));
    assertTrue(json.has("internalNote"));
}
```

Kiểm thử khi default inclusion tắt:

```java
@Test
void unannotatedPropertyIsExcludedWhenDefaultInclusionIsDisabled()
        throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
        .build();

    UserViewDto dto = new UserViewDto();

    JsonNode json = mapper.readTree(
        mapper.writerWithView(Views.Public.class)
            .writeValueAsString(dto)
    );

    assertTrue(json.has("username"));
    assertFalse(json.has("email"));
    assertFalse(json.has("internalNote"));
}
```

Kiểm thử kế thừa view:

```java
@Test
void adminViewIncludesPropertiesFromParentView() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
        .build();

    UserViewDto dto = new UserViewDto();

    JsonNode json = mapper.readTree(
        mapper.writerWithView(Views.Admin.class)
            .writeValueAsString(dto)
    );

    assertTrue(json.has("username"));
    assertTrue(json.has("email"));
    assertFalse(json.has("internalNote"));
}
```

So sánh JSON dưới dạng `JsonNode` giúp test tập trung vào các property có mặt thay vì phụ thuộc thứ tự field hoặc khoảng trắng. Với Spring Boot, nên bổ sung kiểm thử MVC cho endpoint thực tế để xác nhận annotation ở controller và mapper auto-configured phối hợp đúng.

## 13. Những lỗi thường gặp

### Thêm @JsonView nhưng field không annotation vẫn xuất hiện

Nguyên nhân thường là `MapperFeature.DEFAULT_VIEW_INCLUSION` vẫn bật. Tắt feature trong cấu hình mapper nếu muốn chỉ property được gắn view mới xuất hiện khi active view.

### Tắt DEFAULT_VIEW_INCLUSION nhưng endpoint không kích hoạt view

Feature chỉ ảnh hưởng khi một view đang hoạt động. Nếu controller không có `@JsonView` và writer không gọi `withView`, Jackson không áp dụng view filtering như một allowlist.

### Nghĩ rằng @JsonView là phân quyền

View chỉ điều khiển hình dạng JSON. Authorization phải được kiểm tra trước khi use case trả dữ liệu. Không để client chọn view tùy ý.

### Dùng chung entity cho mọi response

Entity có thể chứa field nội bộ hoặc quan hệ persistence. Dùng DTO theo hợp đồng giúp tránh vô tình lộ dữ liệu và giảm phụ thuộc vào cấu trúc database.

### Bật/tắt mapper feature theo request

Mapper dùng chung không nên bị thay đổi trong lúc xử lý request. Cấu hình feature lúc khởi động; chọn view bằng writer hoặc annotation ở endpoint.

### Nhầm DEFAULT_VIEW_INCLUSION với NON_NULL

Hai cấu hình giải quyết hai câu hỏi khác nhau. Một cái xét property có thuộc active view hay không; cái còn lại xét giá trị có được ghi ra theo inclusion policy hay không.

### Kỳ vọng field có view tự bị ẩn khi không kích hoạt view

Không nên dùng annotation như một cơ chế ẩn mặc định. Nếu field không được phép xuất hiện ở mọi output, thiết kế DTO hoặc quy tắc ignore rõ ràng.

## 14. Quy trình thiết kế JSON View an toàn

Khi dùng JSON Views cho một nhóm endpoint:

1. Xác định các hợp đồng đầu ra thực tế, chẳng hạn public, internal và admin.
2. Tạo view marker đơn giản; chỉ dùng kế thừa khi view con thực sự bao gồm toàn bộ view cha.
3. Đánh dấu rõ những property được phép xuất hiện trong từng view.
4. Quyết định rõ property không khai báo view có được bao gồm hay không.
5. Nếu cần allowlist, cấu hình `MapperFeature.DEFAULT_VIEW_INCLUSION` thành `false` trước khi mapper được sử dụng.
6. Chọn view tại `ObjectWriter` hoặc endpoint Spring MVC; không cho client tùy ý chọn class view.
7. Giữ dữ liệu nhạy cảm ngoài response DTO; kiểm tra quyền ở application layer.
8. Kiểm thử cả view cha, view con, property không annotation và endpoint không bật view.
9. Xác nhận cấu hình trên mapper/converter thực tế trong môi trường ứng dụng.
10. Khi thêm property mới, yêu cầu người phát triển quyết định rõ property đó thuộc view nào.

## 15. Bảng ghi nhớ

| Câu hỏi | Câu trả lời |
|---|---|
| Feature nào điều khiển property không có `@JsonView`? | `MapperFeature.DEFAULT_VIEW_INCLUSION` |
| Mặc định feature này thế nào? | Được bật trong Jackson Databind mặc định |
| Khi bật và active view? | Property không annotation được bao gồm trong mọi view |
| Khi tắt và active view? | Property không annotation bị loại khỏi view |
| Tắt feature có ẩn property khi không active view không? | Không; view filtering chỉ có tác dụng khi view được kích hoạt |
| Chọn view cho một lần serialize bằng gì? | `ObjectWriter.withView(...)` hoặc `writerWithView(...)` |
| Cấu hình trong Spring Boot? | `spring.jackson.mapper.default-view-inclusion=false` |
| Feature có ảnh hưởng deserialize không? | Có, khi một view được kích hoạt cho quá trình đọc |
| JSON View có thay thế authorization không? | Không |
| Cách bảo vệ field nhạy cảm tốt nhất? | Không đưa field đó vào response DTO; kiểm tra quyền ở tầng ứng dụng |

## 16. Kết luận

Khi Jackson serialize với một JSON View đang hoạt động, property không khai báo `@JsonView` vẫn được bao gồm theo mặc định vì `MapperFeature.DEFAULT_VIEW_INCLUSION` được bật. Nếu mục tiêu là chỉ trả những field được đánh dấu cho view, hãy tắt feature này trong cấu hình mapper trước khi mapper được sử dụng. Sau đó, chọn view tường minh bằng `ObjectWriter` hoặc tích hợp controller của Spring MVC.

Hãy kiểm thử riêng property có view, property không có view, quan hệ kế thừa và endpoint không kích hoạt view. Trong ứng dụng web, xác nhận chính mapper do framework sử dụng có cấu hình đúng. JSON Views giúp định hình response nhưng không phải ranh giới phân quyền; dữ liệu nhạy cảm nên được loại khỏi response DTO và quyền truy cập phải được kiểm tra ở tầng ứng dụng.
