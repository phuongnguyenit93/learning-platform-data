# Thiết kế mô hình JSON riêng cho từng trường hợp sử dụng

Một đối tượng Java trong hệ thống có thể phục vụ nhiều mục đích: lưu trong cơ sở dữ liệu, trả về REST API, gửi qua message broker, ghi audit log hoặc xuất thành tệp báo cáo. Những mục đích này thường cần các cấu trúc JSON khác nhau. Nếu dùng cùng một entity hoặc một DTO lớn cho tất cả trường hợp, ứng dụng dễ công bố dữ liệu nội bộ, tạo hợp đồng khó thay đổi và buộc các hệ thống tiêu thụ phụ thuộc vào chi tiết triển khai.

Với Jackson, có thể dùng annotation, serializer, filter và cấu hình mapper để thay đổi cách một lớp được tuần tự hóa. Tuy nhiên, nền tảng của một chính sách đầu ra tốt là **thiết kế kiểu dữ liệu JSON theo từng trường hợp sử dụng**. Mỗi API hoặc luồng tích hợp nên có một mô hình đầu ra thể hiện rõ dữ liệu được phép công bố, tên field, kiểu dữ liệu, null policy và quy tắc tương thích.

Ví dụ, cùng một người dùng có thể cần các biểu diễn khác nhau:

- Trang hồ sơ công khai chỉ cần tên hiển thị và ảnh đại diện.
- Màn hình quản trị cần thêm trạng thái khóa và vai trò.
- Sự kiện `UserCreated` cần mã người dùng, thời điểm và phiên bản schema.
- Báo cáo xuất tệp cần các cột phẳng, ổn định.
- Audit log cần mô tả hành động và trường đã thay đổi, nhưng không được ghi mật khẩu hoặc token.

Jackson đảm nhiệm việc chuyển các mô hình đầu ra này thành JSON. Quyết định mô hình nào được dùng phải được đưa ra ở tầng ứng dụng, nơi hiểu mục đích và quyền truy cập của người gọi.

## 1. Tách mô hình domain, persistence và JSON

Ba mô hình thường có trách nhiệm khác nhau:

| Mô hình | Trách nhiệm | Ví dụ nội dung |
|---|---|---|
| Domain model | Biểu diễn trạng thái và quy tắc nghiệp vụ | `User`, trạng thái tài khoản, phương thức khóa/mở khóa. |
| Persistence model/entity | Ánh xạ dữ liệu lưu trữ và quan hệ cơ sở dữ liệu | ID nội bộ, quan hệ JPA, cột hash, thời điểm tạo/cập nhật. |
| JSON DTO/contract | Mô tả dữ liệu trao đổi với một client hoặc hệ thống cụ thể | `PublicUserResponse`, `AdminUserResponse`, `UserCreatedEvent`. |

Một entity có thể chứa thông tin mà client không được biết, quan hệ lazy, dữ liệu phục vụ kiểm toán hoặc thuộc tính chỉ có ý nghĩa trong cơ sở dữ liệu. Khi trả entity trực tiếp, Jackson có thể phát hiện getter và đưa các property đó vào JSON. Điều này khiến việc thêm getter hoặc field mới vô tình làm thay đổi API.

Hãy xem JSON DTO là một hợp đồng độc lập. DTO chỉ chứa các field cần thiết cho trường hợp sử dụng tương ứng. Domain/entity có thể thay đổi nội bộ mà không nhất thiết làm thay đổi JSON.

## 2. Bắt đầu từ người nhận và mục đích sử dụng

Trước khi tạo lớp DTO, hãy trả lời các câu hỏi thiết kế:

1. Ai nhận JSON: trình duyệt công khai, ứng dụng di động, quản trị viên, service nội bộ, message consumer hay hệ thống báo cáo?
2. Người nhận cần thực hiện hành động hoặc quyết định nào với dữ liệu?
3. Những field nào được phép công bố theo quyền của người nhận?
4. Dữ liệu nào phải ổn định qua nhiều phiên bản triển khai?
5. Field nào có thể thiếu, null, rỗng hoặc được bổ sung trong tương lai?
6. Kiểu ngày giờ, số thập phân, enum và collection được biểu diễn theo quy ước nào?

Không nên bắt đầu bằng cách sao chép toàn bộ field của entity rồi đánh dấu một số field là `@JsonIgnore`. Cách đó là denylist: field mới có thể bị lộ nếu người viết quên thêm vào danh sách loại trừ. Mô hình DTO theo allowlist chỉ khai báo các field được phép xuất, nên phạm vi công bố rõ ràng hơn.

## 3. Một domain object, nhiều JSON DTO

Giả sử domain model có thông tin tài khoản:

```java
import java.time.Instant;
import java.util.List;

public class User {
    private final long id;
    private final String username;
    private final String displayName;
    private final String passwordHash;
    private final String internalNote;
    private final boolean locked;
    private final List<String> roles;
    private final Instant createdAt;

    public User(
            long id,
            String username,
            String displayName,
            String passwordHash,
            String internalNote,
            boolean locked,
            List<String> roles,
            Instant createdAt
    ) {
        this.id = id;
        this.username = username;
        this.displayName = displayName;
        this.passwordHash = passwordHash;
        this.internalNote = internalNote;
        this.locked = locked;
        this.roles = List.copyOf(roles);
        this.createdAt = createdAt;
    }

    public long getId() { return id; }
    public String getUsername() { return username; }
    public String getDisplayName() { return displayName; }
    public String getPasswordHash() { return passwordHash; }
    public String getInternalNote() { return internalNote; }
    public boolean isLocked() { return locked; }
    public List<String> getRoles() { return roles; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Không nên trả trực tiếp `User` cho mọi endpoint. Thay vào đó, tạo các kiểu đầu ra có mục đích riêng.

### 3.1. DTO cho hồ sơ công khai

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public record PublicUserResponse(
        long id,
        String username,
        @JsonProperty("display_name") String displayName,
        Instant createdAt
) {
    public static PublicUserResponse from(User user) {
        return new PublicUserResponse(
                user.getId(),
                user.getUsername(),
                user.getDisplayName(),
                user.getCreatedAt()
        );
    }
}
```

JSON đầu ra có dạng:

```json
{
  "id": 42,
  "username": "an",
  "display_name": "An Nguyen",
  "createdAt": "2026-11-12T09:00:00Z"
}
```

DTO này không có `passwordHash`, `internalNote`, `locked` hoặc `roles`. Các field đó không thể tự xuất hiện chỉ vì domain object có getter tương ứng.

### 3.2. DTO cho màn hình quản trị

Quản trị viên có thể cần thêm trạng thái và vai trò:

```java
import java.time.Instant;
import java.util.List;

public record AdminUserResponse(
        long id,
        String username,
        String displayName,
        boolean locked,
        List<String> roles,
        Instant createdAt
) {
    public static AdminUserResponse from(User user) {
        return new AdminUserResponse(
                user.getId(),
                user.getUsername(),
                user.getDisplayName(),
                user.isLocked(),
                user.getRoles(),
                user.getCreatedAt()
        );
    }
}
```

Ngay cả DTO quản trị cũng không cần chứa password hash hoặc ghi chú nội bộ nếu màn hình không có nhu cầu đó. Quyền quản trị không có nghĩa mọi field trong domain đều được phép gửi.

### 3.3. DTO cho sự kiện tích hợp

Một message event cần hợp đồng ổn định và đủ thông tin để consumer xử lý độc lập:

```java
import java.time.Instant;

public record UserCreatedEvent(
        int schemaVersion,
        String eventId,
        long userId,
        String username,
        Instant occurredAt
) {
    public static UserCreatedEvent from(User user, String eventId) {
        return new UserCreatedEvent(
                1,
                eventId,
                user.getId(),
                user.getUsername(),
                Instant.now()
        );
    }
}
```

JSON event có thể được gửi đến message broker:

```json
{
  "schemaVersion": 1,
  "eventId": "evt-8f4a",
  "userId": 42,
  "username": "an",
  "occurredAt": "2026-11-12T09:00:00Z"
}
```

Event là một hợp đồng tích hợp. Không nên dùng trực tiếp `AdminUserResponse` hoặc entity làm message chỉ vì chúng đang có sẵn các field tương tự. Consumer có vòng đời triển khai riêng và cần cấu trúc ổn định theo phiên bản.

### 3.4. DTO cho báo cáo hoặc export

Một tệp CSV/JSON phục vụ báo cáo có thể cần cấu trúc phẳng và tên field ổn định:

```java
public record UserExportRow(
        long user_id,
        String username,
        String display_name,
        String account_status,
        String created_date
) {
}
```

Mô hình export nên phản ánh định dạng và quy tắc của báo cáo, ví dụ cách chuẩn hóa ngày, cách hiển thị trạng thái hoặc mã tham chiếu. Không nên tái sử dụng response REST nếu báo cáo có yêu cầu khác về thứ tự cột, giá trị mặc định hoặc phạm vi dữ liệu.

## 4. Đặt logic ánh xạ ở một nơi có chủ đích

Việc chuyển domain object sang DTO nên được thực hiện bằng factory method, mapper class hoặc thư viện mapping đã được dự án lựa chọn. Với ứng dụng nhỏ, static factory trong DTO có thể đủ rõ ràng. Với nhiều trường hợp sử dụng, một mapper riêng giúp tập trung quy tắc.

```java
public final class UserResponseMapper {
    private UserResponseMapper() {
    }

    public static PublicUserResponse toPublic(User user) {
        return new PublicUserResponse(
                user.getId(),
                user.getUsername(),
                user.getDisplayName(),
                user.getCreatedAt()
        );
    }

    public static AdminUserResponse toAdmin(User user) {
        return new AdminUserResponse(
                user.getId(),
                user.getUsername(),
                user.getDisplayName(),
                user.isLocked(),
                user.getRoles(),
                user.getCreatedAt()
        );
    }
}
```

Mapper class làm rõ rằng hai biểu diễn được tạo có chủ đích. Khi logic ánh xạ phức tạp, có thể dùng MapStruct hoặc công cụ tương tự, nhưng cần giữ mapping allowlist và xem xét các field nhạy cảm trong code được sinh.

Không đặt quyết định quyền truy cập chỉ trong mapper. Controller/service phải xác thực người gọi và kiểm tra quyền trước khi chọn DTO. Ví dụ, chỉ gọi `toAdmin()` sau khi service xác nhận người dùng có quyền quản trị.

## 5. Chọn DTO theo use case ở tầng ứng dụng

Controller nên trả đúng loại response mà endpoint công bố:

```java
@RestController
@RequestMapping("/users")
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/{id}")
    public PublicUserResponse getPublicProfile(@PathVariable long id) {
        User user = userService.findById(id);
        return UserResponseMapper.toPublic(user);
    }
}
```

Endpoint quản trị nên có route, authorization và response type rõ ràng:

```java
@GetMapping("/admin/{id}")
public AdminUserResponse getAdminView(@PathVariable long id) {
    authorizationService.requireUserAdministration();
    User user = userService.findById(id);
    return UserResponseMapper.toAdmin(user);
}
```

Đây là ví dụ minh họa; trong ứng dụng thực tế có thể dùng method security như `@PreAuthorize` hoặc cơ chế phân quyền hiện hành. Điều quan trọng là quyền được kiểm tra trước khi dữ liệu nhạy cảm được đưa vào DTO.

## 6. Request model và response model nên tách biệt

JSON client gửi lên và JSON server trả về thường có quyền ghi/đọc khác nhau. Một request tạo tài khoản có thể nhận mật khẩu, trong khi response không bao giờ được gửi lại mật khẩu.

```java
public record CreateUserRequest(
        String username,
        String password,
        String displayName
) {
}

public record UserCreatedResponse(
        long id,
        String username,
        String displayName,
        Instant createdAt
) {
}
```

Service nhận `CreateUserRequest`, băm mật khẩu và tạo domain object. Controller trả `UserCreatedResponse`. Không dùng lại request object làm response chỉ vì nó có sẵn các field cần thiết.

Nếu có field chỉ nhận đầu vào nhưng không xuất ra, Jackson cung cấp `@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)`. Tương tự, `READ_ONLY` có thể dùng cho field chỉ do server xuất. Những annotation này hữu ích trong một số hợp đồng hai chiều, nhưng request/response DTO riêng thường dễ hiểu và dễ kiểm soát hơn.

## 7. Chọn hình dạng JSON phù hợp

Một DTO không chỉ quyết định tên field mà còn quyết định cấu trúc lồng nhau, cách phân trang, collection, null và giá trị đặc biệt.

### 7.1. Nested object hay cấu trúc phẳng

Nếu dữ liệu có ý nghĩa độc lập và được tái sử dụng, nested object có thể phản ánh quan hệ rõ ràng:

```json
{
  "id": 42,
  "name": "An",
  "address": {
    "city": "Da Nang",
    "countryCode": "VN"
  }
}
```

Với báo cáo hoặc tích hợp yêu cầu cột phẳng, có thể chọn:

```json
{
  "user_id": 42,
  "user_name": "An",
  "address_city": "Da Nang",
  "address_country_code": "VN"
}
```

Không có hình dạng đúng cho mọi tình huống. Hãy chọn theo cách consumer truy cập dữ liệu và mức độ ổn định cần thiết. Tránh lồng sâu không cần thiết hoặc trả toàn bộ graph entity chỉ vì Jackson có thể tuần tự hóa nó.

### 7.2. Envelope và phân trang

Danh sách lớn thường cần metadata phân trang:

```java
public record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
```

JSON:

```json
{
  "items": [
    {"id": 42, "username": "an"},
    {"id": 43, "username": "binh"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 125,
  "totalPages": 7
}
```

Envelope giúp client hiểu dữ liệu và trạng thái phân trang. Nếu nhiều endpoint dùng chung một envelope và semantics giống nhau, có thể tái sử dụng generic DTO. Không nên dùng cùng envelope nếu một luồng có pagination cursor, một luồng khác có offset/page number hoặc metadata khác về ý nghĩa.

### 7.3. Null, field thiếu và collection rỗng

Hãy quyết định rõ:

- Field luôn có mặt nhưng có thể là `null`.
- Field null bị bỏ qua khi ghi.
- Field không có dữ liệu được ghi thành array rỗng `[]`.
- Field không áp dụng bị bỏ qua hoàn toàn.

Jackson hỗ trợ `@JsonInclude` hoặc cấu hình inclusion ở mapper:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record PublicProfileResponse(
        long id,
        String displayName,
        String avatarUrl
) {
}
```

`NON_NULL` bỏ qua field có giá trị null. Nó không biến null thành chuỗi rỗng hoặc collection rỗng. Client cần biết sự khác nhau giữa “không có thông tin”, “chưa đặt giá trị” và “danh sách hiện không có phần tử”. Đối với API cập nhật, sự khác biệt giữa field thiếu và field null có thể quyết định giữ nguyên hay xóa giá trị.

### 7.4. Kiểu số, ngày giờ và enum

DTO nên dùng kiểu Java phù hợp với semantics của dữ liệu:

- Tiền và số thập phân cần độ chính xác: `BigDecimal`, không chuyển qua `double`.
- Thời điểm sự kiện: thường dùng `Instant` hoặc kiểu có offset theo hợp đồng.
- Ngày trên lịch: `LocalDate`.
- Trạng thái có tập giá trị cố định: enum, với quy ước JSON string ổn định.

Không để định dạng mặc định vô tình trở thành hợp đồng. Đăng ký module ngày giờ cần thiết, xác định format và timezone, và dùng `@JsonProperty` nếu tên field JSON phải khác tên Java. Khi thay đổi tên enum hoặc format, hãy xem đó là thay đổi hợp đồng có thể ảnh hưởng consumer.

## 8. Dùng annotation Jackson ở đúng phạm vi

Annotation giúp diễn đạt quy tắc của một DTO, nhưng không nên dùng annotation để che giấu một mô hình đầu ra quá rộng.

| Annotation/cơ chế | Mục đích phù hợp |
|---|---|
| `@JsonProperty` | Đặt tên JSON hoặc chỉ định property rõ ràng. |
| `@JsonPropertyOrder` | Ổn định thứ tự field khi định dạng đầu ra cần thứ tự dễ đọc hoặc snapshot. |
| `@JsonInclude` | Chọn điều kiện đưa giá trị vào JSON, ví dụ bỏ qua null. |
| `@JsonFormat` | Định dạng một property ngày giờ hoặc kiểu được hỗ trợ. |
| `@JsonIgnore` | Loại một property cụ thể khỏi ánh xạ JSON. |
| `@JsonProperty(access = ...)` | Quy định hướng đọc/ghi của property. |
| `@JsonView` | Chọn nhóm property cho một số biểu diễn đã định nghĩa. |
| `@JsonFilter` | Lọc property động theo filter được cấu hình. |
| Mix-in annotation | Áp dụng annotation cho kiểu không thể sửa mã nguồn. |

### 8.1. `@JsonView` không thay thế authorization

Có thể dùng `@JsonView` để tạo nhiều góc nhìn từ cùng một lớp, ví dụ view cơ bản và view quản trị. Cách này giảm số DTO trong trường hợp các biểu diễn thực sự gần nhau. Tuy nhiên, nếu endpoint chọn nhầm view hoặc không kiểm tra quyền trước khi serialize, dữ liệu vẫn có thể bị lộ.

View là cơ chế chọn property khi tuần tự hóa; nó không xác thực người dùng và không quyết định người dùng có quyền xem field hay không. Với dữ liệu nhạy cảm hoặc các hợp đồng khác biệt lớn, DTO riêng thường rõ ràng hơn.

### 8.2. Filter động cần allowlist và kiểm soát quyền

`@JsonFilter` hữu ích khi tập field được chọn động theo một yêu cầu hợp lệ. Tuy nhiên, nếu filter dựa trên danh sách denylist, field mới có thể bị xuất khi chưa được thêm vào danh sách loại trừ. Hãy dùng allowlist và xác thực quyền trước khi tạo filter. Không nhận tên field tùy ý từ client rồi dùng trực tiếp để quyết định dữ liệu được công bố.

### 8.3. Custom serializer không nên chứa logic phân quyền

Serializer phù hợp để biểu diễn một kiểu giá trị theo định dạng đặc biệt, ví dụ tiền tệ hoặc value object. Không nên để serializer tự truy vấn người dùng hiện tại, gọi dịch vụ phân quyền hoặc quyết định một người có được xem dữ liệu hay không. Những quyết định đó thuộc tầng ứng dụng; serializer nên nhận một DTO đã được chuẩn bị đúng.

## 9. Một mapper chung hay nhiều mapper?

Phần lớn ứng dụng có thể dùng một `ObjectMapper` đã cấu hình chung cho các quy tắc nền tảng: module ngày giờ, naming strategy, serializer phổ biến và các feature chung. Những khác biệt về nội dung nên được thể hiện qua DTO.

Nếu hai tích hợp có yêu cầu serialization thật sự khác nhau, ví dụ một bên cần format timestamp legacy còn một bên dùng ISO-8601, có thể tạo mapper riêng cho từng boundary. Mỗi mapper cần được cấu hình hoàn chỉnh trước khi dùng và không thay đổi cấu hình trong khi xử lý request.

Với khác biệt nhỏ ở một thao tác, `ObjectWriter` hoặc `ObjectReader` có thể tạo biến thể bất biến:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
String prettyJson = prettyWriter.writeValueAsString(response);
```

Không đổi `ObjectMapper` singleton theo từng request để chuyển giữa chính sách public/admin. Chọn DTO đúng và kiểm tra authorization trước; mapper chỉ thực hiện việc tuần tự hóa.

## 10. Thiết kế phiên bản và khả năng tương thích của JSON contract

JSON DTO được client hoặc service khác tiêu thụ sẽ trở thành hợp đồng. Thay đổi một field có thể ảnh hưởng tới code đã triển khai ở nơi khác.

Các nguyên tắc thường hữu ích:

- Thêm field tùy chọn thường dễ tương thích hơn xóa hoặc đổi tên field đang dùng.
- Không đổi kiểu field, ví dụ từ number sang string, nếu chưa có kế hoạch chuyển đổi consumer.
- Không đổi ý nghĩa của field trong khi giữ nguyên tên.
- Giữ enum string ổn định; cần chiến lược cho giá trị mới mà consumer cũ chưa biết.
- Xác định rõ null, missing và default value.
- Với event, lưu schema version hoặc quản lý version bằng topic/subject/schema registry theo nền tảng tích hợp.
- Tài liệu hóa format ngày giờ, timezone, precision số và quy tắc pagination.

Ví dụ event có phiên bản:

```java
public record UserCreatedEventV1(
        int schemaVersion,
        String eventId,
        long userId,
        String username,
        Instant occurredAt
) {
}
```

Nếu phiên bản sau cần thêm nguồn tạo tài khoản, có thể bổ sung field tùy chọn hoặc phát hành một schema/event version mới tùy yêu cầu tương thích. Không nên đổi cấu trúc event cũ mà không kiểm tra consumer đang sử dụng.

Đối với REST API, version có thể được quản lý bằng URL, header hoặc chính sách tương thích của tổ chức. Không phải mọi API đều cần version trong từng JSON object; điều quan trọng là cách version hóa phải nhất quán và được công bố.

## 11. DTO lỗi cũng là một hợp đồng đầu ra riêng

Không nên trả exception Java hoặc entity nội bộ thành JSON lỗi. Hãy định nghĩa một error response ổn định:

```java
import java.time.Instant;
import java.util.Map;

public record ApiErrorResponse(
        String code,
        String message,
        Instant timestamp,
        String requestId,
        Map<String, String> fieldErrors
) {
}
```

Ví dụ:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "timestamp": "2026-11-12T09:00:00Z",
  "requestId": "req-100",
  "fieldErrors": {
    "email": "must be a valid email address"
  }
}
```

Không đưa stack trace, SQL, đường dẫn nội bộ, secret, token hoặc nội dung exception không được lọc vào response. Log nội bộ có thể giữ thêm chi tiết phù hợp để điều tra. Error DTO giúp client xử lý lỗi bằng mã ổn định thay vì phân tích thông báo tự do.

## 12. Bảo mật đầu ra: allowlist, authorization và dữ liệu nhạy cảm

Thiết kế DTO riêng giúp giảm nguy cơ công bố nhầm field, nhưng vẫn cần kiểm soát ở tầng ứng dụng.

- Chỉ ánh xạ field cần thiết cho trường hợp sử dụng.
- Kiểm tra quyền trước khi truy xuất hoặc đưa dữ liệu nhạy cảm vào DTO.
- Không đưa password, password hash, API key, access token, refresh token hoặc secret vào response thông thường.
- Không ghi dữ liệu nhạy cảm vào event, export hoặc audit log nếu không có yêu cầu và kiểm soát rõ ràng.
- Xử lý dữ liệu cá nhân theo mục đích, phạm vi truy cập và thời hạn lưu trữ phù hợp.
- Không dựa vào việc field đang là `private`, `transient` hoặc null để bảo vệ JSON.
- Không dùng serializer để che giấu dữ liệu sau khi toàn bộ domain object đã được chọn làm response.

Ví dụ, một audit event nên mô tả thay đổi mà không ghi giá trị bí mật:

```java
public record UserSecurityAuditEvent(
        String eventId,
        long actorId,
        long targetUserId,
        String action,
        List<String> changedFields,
        Instant occurredAt
) {
}
```

Nếu người dùng đổi mật khẩu, `changedFields` có thể chứa `password`, nhưng event không chứa mật khẩu cũ, mật khẩu mới hoặc hash. Cách mô hình hóa này vẫn cung cấp thông tin kiểm toán cần thiết mà không sao chép secret vào log.

## 13. Kiểm thử hợp đồng JSON theo từng trường hợp sử dụng

Mỗi DTO đầu ra quan trọng nên có kiểm thử xác nhận field được công bố. Kiểm thử không chỉ xác nhận field cần có mà còn khẳng định field nhạy cảm không xuất hiện.

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PublicUserResponseTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void publicResponseContainsOnlyPublicFields() throws Exception {
        User user = new User(
                42L,
                "an",
                "An Nguyen",
                "password-hash",
                "internal note",
                false,
                List.of("USER", "ADMIN"),
                Instant.parse("2026-11-12T09:00:00Z")
        );

        PublicUserResponse response = PublicUserResponse.from(user);
        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

        assertEquals(42L, json.path("id").asLong());
        assertEquals("an", json.path("username").asText());
        assertEquals("An Nguyen", json.path("display_name").asText());
        assertFalse(json.has("passwordHash"));
        assertFalse(json.has("internalNote"));
        assertFalse(json.has("roles"));
        assertFalse(json.has("locked"));
    }
}
```

Với hệ thống có nhiều client, nên kiểm thử schema hoặc snapshot theo hợp đồng. Snapshot test hữu ích để phát hiện thay đổi cấu trúc không chủ ý, nhưng cần cập nhật có chủ đích khi hợp đồng thay đổi. Ngoài kiểm thử serialization, cần kiểm thử authorization để chắc chắn endpoint không trả DTO quản trị cho người dùng không đủ quyền.

## 14. Những lỗi thiết kế thường gặp

### 14.1. Trả trực tiếp entity JPA

Entity có thể chứa getter cho field nội bộ, quan hệ lazy hoặc cấu trúc không phù hợp với API. Tuần tự hóa trực tiếp làm persistence model trở thành public contract. Hãy map sang DTO.

### 14.2. Một DTO khổng lồ cho mọi endpoint

DTO có hàng chục field nullable và nhiều cờ để bật/tắt field khiến hợp đồng khó hiểu. Hãy chia theo trường hợp sử dụng hoặc nhóm biểu diễn có ý nghĩa ổn định.

### 14.3. Dùng `Map<String, Object>` cho schema đã biết

Map linh hoạt nhưng mất kiểm tra kiểu ở compile time, dễ sai tên field và khó version hóa. Dùng DTO có kiểu khi cấu trúc đã biết; chỉ dùng map khi dữ liệu thực sự động.

### 14.4. Dựa vào `@JsonIgnore` như lớp bảo mật duy nhất

Annotation có thể bị thay đổi, mix-in hoặc cấu hình khác ảnh hưởng. DTO allowlist cùng authorization rõ ràng tạo ranh giới an toàn hơn.

### 14.5. Chọn `@JsonView` theo tham số client mà không kiểm tra quyền

View chỉ chọn property. Người gọi không được tự quyết định view có thể tiết lộ dữ liệu quản trị. Việc chọn view phải gắn với quyền đã xác thực.

### 14.6. Thay đổi mapper dùng chung trong lúc xử lý request

Thay naming strategy, timezone hoặc feature theo từng request trên singleton có thể gây hành vi không nhất quán. Cấu hình mapper trước khi sử dụng; dùng DTO, `ObjectWriter` hoặc mapper riêng cho hợp đồng độc lập.

### 14.7. Tái sử dụng event DTO làm response DTO

Event và HTTP response có người nhận, vòng đời, yêu cầu tương thích và ngữ nghĩa khác nhau. Chỉ dùng chung một kiểu khi hai hợp đồng thực sự giống nhau và được quản lý cùng vòng đời; không tái sử dụng chỉ để giảm số lớp.

## 15. Quy trình thiết kế một JSON model mới

Khi thêm endpoint hoặc tích hợp mới, có thể đi theo trình tự sau:

1. **Xác định consumer và mục đích:** ai đọc dữ liệu và họ cần làm gì?
2. **Chốt allowlist:** liệt kê field được phép công bố và lý do cần từng field.
3. **Chọn kiểu Java:** `BigDecimal` cho số thập phân chính xác, kiểu ngày giờ theo semantics, enum hoặc value object có hợp đồng rõ.
4. **Thiết kế cấu trúc:** nested object, array, envelope, pagination và null policy.
5. **Tạo DTO riêng:** đặt tên phản ánh use case, không dùng entity làm response.
6. **Viết mapping:** chuyển domain data sang DTO sau khi kiểm tra quyền.
7. **Cấu hình Jackson:** dùng naming, module, format và feature chung; tránh thay đổi mapper dùng chung theo request.
8. **Tài liệu hóa version:** xác định quy tắc thêm/xóa/đổi field và enum.
9. **Kiểm thử hợp đồng và quyền:** kiểm tra field có/không có, format và authorization.

## 16. Chọn cách biểu diễn theo trường hợp sử dụng

| Trường hợp | Mô hình nên cân nhắc | Lưu ý chính |
|---|---|---|
| Hồ sơ công khai | `PublicUserResponse` | Chỉ chứa dữ liệu công khai, allowlist nhỏ. |
| Màn hình quản trị | `AdminUserResponse` | Kiểm tra quyền trước khi tạo DTO; chỉ thêm field quản trị cần dùng. |
| Request tạo/cập nhật | `CreateUserRequest`, `UpdateUserRequest` | Tách khỏi response; xác định rõ missing/null và validation. |
| Message event | `UserCreatedEvent` | Schema ổn định, event ID, thời điểm, version và idempotency. |
| Báo cáo/export | `UserExportRow` | Cấu trúc phẳng, tên cột và format cố định. |
| Audit log | `UserSecurityAuditEvent` | Ghi hành động và field thay đổi; không ghi secret. |
| Lỗi REST API | `ApiErrorResponse` | Mã lỗi ổn định, thông tin an toàn, không lộ stack trace. |
| Dữ liệu thực sự động | `JsonNode` hoặc map có kiểm soát | Xác thực cấu trúc và giới hạn input; không dùng thay DTO khi schema đã biết. |

Jackson cung cấp nhiều cách tùy chỉnh JSON, nhưng chính sách đầu ra bền vững bắt đầu từ việc chọn đúng mô hình dữ liệu cho đúng consumer. Domain model và entity phục vụ nghiệp vụ/lưu trữ; DTO công khai, DTO quản trị, request, event, export và audit có thể cần các hợp đồng riêng. Hãy ưu tiên allowlist, mapping có chủ đích và authorization ở tầng ứng dụng. Dùng annotation và serializer để thể hiện quy tắc định dạng, dùng mapper đã cấu hình ổn định, và kiểm thử JSON theo từng hợp đồng. Khi đó, thay đổi nội bộ của Java ít làm ảnh hưởng consumer, còn dữ liệu được công bố đúng mục đích và quyền truy cập.
