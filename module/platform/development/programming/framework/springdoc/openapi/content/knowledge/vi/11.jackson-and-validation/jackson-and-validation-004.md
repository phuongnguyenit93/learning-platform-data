# `@JsonView` và các hình chiếu dữ liệu theo operation

Một model có thể chứa nhiều thông tin hơn mức một endpoint cần trả về. Ví dụ, màn hình danh sách người dùng chỉ cần mã và tên hiển thị; màn hình chi tiết cần thêm email; endpoint dành cho quản trị viên có thể cần thêm ghi chú nội bộ. Nếu mọi endpoint đều serialize cùng một DTO theo cùng cách, response dễ chứa trường thừa hoặc làm hợp đồng API khó hiểu.

Jackson cung cấp `@JsonView` để chọn một tập thuộc tính khi serialize hoặc deserialize JSON. Spring MVC cho phép kích hoạt view ở controller method đối với response và ở tham số `@RequestBody` đối với request. Springdoc-openapi hỗ trợ annotation `@JsonView` trong API Spring MVC, nhờ đó có thể tạo schema phản ánh hình chiếu được dùng ở từng operation.

Điểm quan trọng là view chỉ điều khiển những thuộc tính Jackson đọc hoặc ghi. Nó không tự quyết định người gọi có quyền truy cập endpoint, không thay thế validation và cũng không tối ưu truy vấn cơ sở dữ liệu.

## 1. JSON View là gì?

Một JSON View là một lớp hoặc interface đánh dấu. Nó thường không chứa method hay trạng thái; tên lớp chỉ đại diện cho một nhóm thuộc tính. Các thuộc tính của DTO được gắn `@JsonView` để chỉ ra chúng thuộc những view nào.

Ví dụ một tài khoản có các thông tin:

| Thuộc tính | Danh sách công khai | Chi tiết | Quản trị |
| --- | --- | --- | --- |
| `id` | Có | Có | Có |
| `displayName` | Có | Có | Có |
| `email` | Không | Có | Có |
| `internalNote` | Không | Không | Có |

Có thể định nghĩa các view bằng interface lồng nhau:

```java
public final class UserViews {

    public interface Public {}

    public interface Detail extends Public {}

    public interface Admin extends Detail {}

    public interface Create {}

    public interface Update {}

    private UserViews() {}
}
```

`Detail extends Public` nghĩa là view chi tiết kế thừa các thuộc tính của view công khai. `Admin extends Detail` tiếp tục bao gồm các thuộc tính của hai view trước. `Create` và `Update` là hai view riêng cho dữ liệu đầu vào.

## 2. Gắn view lên thuộc tính DTO

Đặt `@JsonView` trên field hoặc getter để xác định thuộc tính xuất hiện trong view nào:

```java
public class UserDto {

    @JsonView(UserViews.Public.class)
    private UUID id;

    @JsonView({
        UserViews.Public.class,
        UserViews.Create.class,
        UserViews.Update.class
    })
    private String displayName;

    @JsonView(UserViews.Detail.class)
    private String email;

    @JsonView(UserViews.Admin.class)
    private String internalNote;

    // Constructors, getters and setters omitted.
}
```

Với cấu trúc view kế thừa ở trên:

- `Public` chứa `id` và `displayName`.
- `Detail` chứa các trường của `Public` cùng `email`.
- `Admin` chứa các trường của `Detail` cùng `internalNote`.
- `Create` và `Update` chỉ nhận `displayName` trong ví dụ này.

Một thuộc tính có thể thuộc nhiều view bằng cách truyền một mảng lớp vào `@JsonView`. Điều này hữu ích khi cùng một field được dùng trong response công khai và request tạo/cập nhật.

Không cần tạo một view riêng cho mọi endpoint. Hãy nhóm theo mục đích dữ liệu ổn định, chẳng hạn `Public`, `Detail`, `Admin`, `Create` và `Update`, để tránh số lượng view tăng quá nhanh.

## 3. Chọn view cho response của từng operation

Đối với controller trả dữ liệu qua `@ResponseBody` hoặc `ResponseEntity`, đặt `@JsonView` trên method để chọn view serialize response:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    private final UserService userService;

    UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/{id}")
    @JsonView(UserViews.Public.class)
    UserDto getSummary(@PathVariable UUID id) {
        return userService.getById(id);
    }

    @GetMapping("/{id}/detail")
    @JsonView(UserViews.Detail.class)
    UserDto getDetail(@PathVariable UUID id) {
        return userService.getById(id);
    }

    @GetMapping("/{id}/admin")
    @JsonView(UserViews.Admin.class)
    UserDto getAdminView(@PathVariable UUID id) {
        return userService.getById(id);
    }
}
```

Ba operation trả về cùng kiểu Java `UserDto`, nhưng Jackson serialize theo ba view khác nhau. Ví dụ response công khai chỉ chứa:

```json
{
  "id": "9c1c21b1-2cc0-45c7-86a4-10cde57c6c1b",
  "displayName": "Nguyen An"
}
```

Response chi tiết còn có `email`; response quản trị có thêm `internalNote`. View được chọn cố định theo annotation của method nên client không thể tự gửi tên view để yêu cầu server xuất thêm field.

Spring MVC chỉ hỗ trợ một view class được kích hoạt trên controller method. Mặc dù `@JsonView` cho phép khai báo nhiều class, response advice hỗ trợ một class argument; nếu cần kết hợp nhiều nhóm, hãy tạo interface tổng hợp bằng kế thừa như `Admin extends Detail`.

## 4. Chọn view khi deserialize request body

`@JsonView` cũng có thể đặt trực tiếp trên tham số `@RequestBody`. Spring MVC dùng view đó khi Jackson deserialize JSON thành DTO:

```java
@PostMapping
@JsonView(UserViews.Public.class)
UserDto create(
    @JsonView(UserViews.Create.class)
    @Valid @RequestBody UserDto request
) {
    return userService.create(request);
}

@PutMapping("/{id}")
@JsonView(UserViews.Public.class)
UserDto update(
    @PathVariable UUID id,
    @JsonView(UserViews.Update.class)
    @Valid @RequestBody UserDto request
) {
    return userService.update(id, request);
}
```

Trong ví dụ:

- `@JsonView(UserViews.Create.class)` trên tham số chọn các field được đọc từ JSON đầu vào khi tạo.
- `@JsonView(UserViews.Update.class)` giới hạn field được bind khi cập nhật.
- `@JsonView(UserViews.Public.class)` trên method chọn field được serialize trong response.
- `@Valid` chạy Bean Validation trên object sau khi deserialize thành công.

Hai vị trí annotation có mục đích riêng: annotation trên tham số điều khiển deserialize request; annotation trên method điều khiển serialize response. Có thể dùng hai view khác nhau trong cùng một operation.

Các thuộc tính không thuộc view đầu vào sẽ không được bind theo view đang hoạt động. Tuy nhiên, không nên coi đây là cơ chế từ chối mọi field lạ hoặc kiểm soát quyền ghi tuyệt đối. Hành vi với field không được chọn còn liên quan đến cấu hình Jackson và cách xử lý lỗi của ứng dụng; hãy kiểm thử payload có field ngoài view. Với dữ liệu nhạy cảm hoặc quy tắc ghi phức tạp, DTO request riêng thường dễ kiểm soát hơn.

## 5. View kế thừa và thuộc tính không được gắn annotation

Kế thừa giữa các interface view giúp tái sử dụng nhóm field:

```java
public interface SummaryView {}

public interface DetailView extends SummaryView {}

public interface AdminView extends DetailView {}
```

Một field gắn `@JsonView(SummaryView.class)` sẽ xuất hiện trong `SummaryView`, `DetailView` và `AdminView` vì hai view sau kế thừa view trước. Field gắn `@JsonView(AdminView.class)` chỉ xuất hiện trong view quản trị.

Cần chú ý đến thuộc tính không có `@JsonView`. Jackson có `MapperFeature.DEFAULT_VIEW_INCLUSION` để quyết định các thuộc tính không gắn view có xuất hiện trong mọi view hay không:

- Khi bật, thuộc tính không có annotation được đưa vào tất cả view.
- Khi tắt, thuộc tính không có annotation bị loại khỏi các view đang hoạt động.

Jackson 2.x mặc định bật tính năng này ở cấp thư viện, trong khi cấu hình `ObjectMapper` mặc định do Spring Boot tạo thường tắt nó. Jackson 3 cũng thay đổi mặc định của thư viện theo hướng tắt. Nếu ứng dụng tự tạo hoặc thay thế `ObjectMapper`, hành vi có thể khác. Vì vậy, hãy kiểm tra cấu hình thực tế thay vì dựa vào một mặc định chung.

Trong DTO dùng nhiều view, cách dễ dự đoán nhất là gắn view tường minh cho mọi thuộc tính cần xuất hiện. Đặc biệt, không để một field nhạy cảm không có annotation rồi giả định nó sẽ luôn bị ẩn.

## 6. Springdoc tạo schema theo `@JsonView`

Springdoc-openapi xác nhận hỗ trợ annotation `@JsonView` trong API Spring MVC. Khi một operation sử dụng view, springdoc có thể dùng thông tin view để xây dựng schema tương ứng với phần dữ liệu được Jackson đọc hoặc ghi.

Ví dụ, hai operation cùng trả về `UserDto`:

```java
@GetMapping("/{id}")
@JsonView(UserViews.Public.class)
UserDto getSummary(@PathVariable UUID id) { ... }

@GetMapping("/{id}/detail")
@JsonView(UserViews.Detail.class)
UserDto getDetail(@PathVariable UUID id) { ... }
```

Trong `/v3/api-docs`, schema được tham chiếu bởi hai operation cần phản ánh đúng hình chiếu tương ứng. Springdoc có thể tạo component schema riêng cho từng view hoặc đặt tên component theo quy tắc nội bộ của phiên bản đang dùng. Không nên phụ thuộc vào tên component cụ thể nếu chưa kiểm tra output; điều cần xác nhận là danh sách `properties` của mỗi operation đúng với response thực tế.

Với request body, hãy kiểm tra schema gắn với operation cũng phản ánh view của tham số `@RequestBody`. Springdoc hỗ trợ view trên API MVC, nhưng nếu controller dùng `MappingJacksonValue`, custom `ResponseBodyAdvice`, `ObjectMapper` riêng hoặc chọn view động ở runtime, schema tự động có thể không thể suy ra mọi nhánh dữ liệu. Khi đó cần khai báo schema tường minh bằng `@Schema(implementation = ...)` hoặc tùy chỉnh OpenAPI theo cách phù hợp.

## 7. Kiểm soát view động bằng `MappingJacksonValue`

Trong trường hợp view được quyết định trong code thay vì annotation cố định, Spring MVC cho phép trả về `MappingJacksonValue`:

```java
@GetMapping("/{id}/profile")
MappingJacksonValue getProfile(
    @PathVariable UUID id,
    Authentication authentication
) {
    UserDto user = userService.getById(id);

    Class<?> view = userAccessService.canSeeDetails(authentication, user)
        ? UserViews.Detail.class
        : UserViews.Public.class;

    MappingJacksonValue result = new MappingJacksonValue(user);
    result.setSerializationView(view);
    return result;
}
```

Ở đây, ứng dụng quyết định view sau khi kiểm tra quyền của người dùng. Đây là ví dụ minh họa cách Spring MVC truyền view cho Jackson; trong ứng dụng thực tế, việc phân quyền vẫn phải được thực hiện rõ ràng và kiểm thử riêng.

Một operation có thể trả về nhiều hình dạng JSON tùy danh tính người gọi. OpenAPI thường cần mô tả được tất cả hình dạng hợp lệ; nếu schema tự động chỉ phản ánh một kiểu, hãy công bố một schema chung phù hợp hoặc dùng `oneOf`/các operation riêng để hợp đồng rõ ràng. Đừng giả định springdoc có thể suy ra mọi lựa chọn được thực hiện bên trong service.

## 8. `@JsonView` không thay thế DTO, validation hoặc bảo mật

`@JsonView` hữu ích khi nhiều operation chia sẻ một model nhưng cần các tập field khác nhau. Tuy nhiên, không nên dùng nó như giải pháp duy nhất cho mọi trường hợp:

- **Không phải phân quyền:** view chỉ định field được Jackson đọc/ghi. Spring Security hoặc logic phân quyền phải quyết định người gọi có được truy cập operation và dữ liệu hay không.
- **Không phải validation:** view không kiểm tra field bắt buộc, độ dài, định dạng hoặc quy tắc nghiệp vụ. Dùng Bean Validation như `@NotBlank`, `@Email`, `@Size` và kiểm tra nghiệp vụ.
- **Không phải truy vấn projection:** Jackson lọc JSON sau khi object đã được tạo. Nếu cần giảm dữ liệu đọc từ database, dùng projection ở tầng repository/service.
- **Không thay thế DTO chuyên biệt:** request tạo, cập nhật và response có thể có quy tắc khác nhau đáng kể. DTO riêng giúp giới hạn dữ liệu có thể gửi và làm hợp đồng dễ hiểu hơn.
- **Không tự ẩn field trong mọi cách serialize:** nếu object được serialize ngoài controller có kích hoạt view, hành vi có thể khác. Cần hiểu cấu hình `ObjectMapper` và đường đi dữ liệu.

Một nguyên tắc an toàn là không đưa bí mật như password hash, token hoặc dữ liệu xác thực vào DTO response dùng chung rồi chỉ dựa vào một view để che chúng. Không trả dữ liệu đó ra khỏi service nếu operation không cần đến nó.

## 9. Kiểm thử response, request và OpenAPI schema

Vì view tác động đến cả serialize, deserialize và tài liệu, nên kiểm tra ba lớp riêng:

1. **Kiểm tra serialize:** gọi endpoint công khai và xác nhận JSON không chứa `email` hoặc `internalNote`; gọi endpoint chi tiết và xác nhận có `email` nhưng không có `internalNote`.
2. **Kiểm tra deserialize:** gửi JSON có các field được phép trong `Create` hoặc `Update`, xác nhận chúng được bind; gửi thêm field ngoài view và kiểm tra hành vi thực tế của cấu hình Jackson.
3. **Kiểm tra validation:** gửi dữ liệu thiếu hoặc sai constraint trong view đang hoạt động, xác nhận Bean Validation trả lỗi phù hợp.
4. **Kiểm tra OpenAPI:** mở `/v3/api-docs`, tìm từng operation và xác nhận schema request/response liệt kê đúng thuộc tính.
5. **Kiểm tra quyền truy cập:** xác nhận endpoint quản trị vẫn được bảo vệ bằng Spring Security, kể cả khi response view đã loại bỏ field nhạy cảm.

Ví dụ kiểm thử response với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicViewDoesNotExposeEmailOrInternalNote() throws Exception {
        mockMvc.perform(get("/api/users/{id}", "9c1c21b1-2cc0-45c7-86a4-10cde57c6c1b"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").exists())
            .andExpect(jsonPath("$.email").doesNotExist())
            .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
```

Test trên xác nhận response thực tế của endpoint. Một kiểm thử khác nên gọi `/v3/api-docs` hoặc dùng `MockMvc` để xác nhận schema công bố khớp response.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field không có annotation vẫn xuất hiện | `DEFAULT_VIEW_INCLUSION` đang bật | Kiểm tra `ObjectMapper` và gắn view tường minh cho các field. |
| Field có annotation không xuất hiện | View đang kích hoạt không khớp hoặc không kế thừa view của field | Kiểm tra interface kế thừa và `@JsonView` trên field/getter. |
| Request nhận field ngoài view | Cấu hình deserialize và xử lý field ngoài view chưa như mong đợi | Kiểm tra `JsonViewRequestBodyAdvice`, Jackson config và viết test payload ngoài view. |
| Schema trong Swagger UI có field thừa/thiếu | Schema không được tạo theo view mong đợi hoặc có custom converter | Kiểm tra `/v3/api-docs`, view ở method/parameter và schema override. |
| View động trả nhiều hình dạng nhưng OpenAPI chỉ có một schema | Springdoc không suy ra lựa chọn runtime trong code | Khai báo schema chung, `oneOf` hoặc tách operation theo hợp đồng. |
| Field nhạy cảm lộ ra ở endpoint khác | DTO được serialize không có view hoặc có đường serialize khác | Dùng response DTO riêng và kiểm thử mọi endpoint trả dữ liệu. |

## 10. Nguyên tắc áp dụng

- Tạo các interface view nhỏ theo mục đích dữ liệu, dùng kế thừa để mở rộng nhóm field.
- Gắn `@JsonView` tường minh lên các thuộc tính cần kiểm soát.
- Đặt view trên controller method cho response và trên tham số `@RequestBody` cho request.
- Có thể dùng view request và response khác nhau trong cùng operation.
- Kiểm tra `MapperFeature.DEFAULT_VIEW_INCLUSION` trong `ObjectMapper` thực tế.
- Dùng springdoc để sinh schema theo view, sau đó xác minh `/v3/api-docs` cho từng operation.
- Dùng DTO riêng khi quy tắc request/response khác biệt nhiều hoặc dữ liệu nhạy cảm cần được tách khỏi model chung.
- Luôn kiểm thử serialize, deserialize, validation và quyền truy cập độc lập.

`@JsonView` cho phép nhiều operation dùng chung một kiểu Java nhưng công bố những hình chiếu JSON khác nhau. Khi view được chọn rõ ở controller, Jackson được cấu hình nhất quán và springdoc sinh schema đúng theo view, tài liệu OpenAPI sẽ phản ánh gần hơn dữ liệu mà client thực sự nhận hoặc gửi. View là công cụ định hình JSON; validation, truy vấn dữ liệu và phân quyền vẫn cần được thiết kế ở đúng tầng của ứng dụng.

## Tài liệu tham khảo

- [Spring Framework – Jackson JSON Views trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html)
- [Spring Framework – `JsonViewRequestBodyAdvice`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/JsonViewRequestBodyAdvice.html)
- [springdoc-openapi FAQ – hỗ trợ `@JsonView` trong Spring MVC](https://springdoc.org/faq.html)
- [Jackson Databind – `MapperFeature.DEFAULT_VIEW_INCLUSION`](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/MapperFeature.html)
