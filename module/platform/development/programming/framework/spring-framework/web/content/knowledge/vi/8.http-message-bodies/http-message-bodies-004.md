# Spring MVC: Tuần tự hóa JSON, DTO, kiểu generic và tham chiếu vòng

## 1. Mục tiêu bài học

Trong REST API với Spring MVC, controller nhận dữ liệu JSON từ client và trả JSON trở lại. Đây không chỉ là thao tác chuyển chuỗi: hệ thống cần biết Java type, hợp đồng DTO, quy tắc validation và cách biểu diễn một object graph mà không lặp vô hạn.

Sau bài này, bạn sẽ:

- Giải thích **serialization** (Java object → JSON) và **deserialization** (JSON → Java object) bằng Jackson thông qua Spring MVC.
- Phân biệt `@RequestBody`, `@ResponseBody`, `@RestController`, `ResponseEntity` và `HttpMessageConverter`.
- Thiết kế request DTO, response DTO để tránh lộ dữ liệu nội bộ hay vô tình serialize JPA entity.
- Sử dụng các container generic như `List<BookResponse>` và `ApiResponse<List<BookResponse>>`; dùng `TypeReference`/`JavaType` khi tự đọc JSON.
- Nhận ra vòng tham chiếu hai chiều, lựa chọn DTO hữu hạn, `@JsonIgnore`, `@JsonManagedReference`/`@JsonBackReference` hoặc `@JsonIdentityInfo`.
- Kiểm thử chính xác status, JSON structure, validation và xử lý lỗi.

Ví dụ thực hành dùng **Java 17+, Spring Boot 3.5.0, Spring Framework 6.2 và Jackson 2** (các import `com.fasterxml.jackson.*`). Các đoạn code được ghi rõ khi chỉ minh họa; dự án hoàn chỉnh nằm ở mục 9.

## 2. Luồng dữ liệu JSON trong Spring MVC

Một request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
~~~

Một handler tối giản:

~~~java
@PostMapping("/books")
public BookResponse create(@RequestBody CreateBookRequest input) {
    return new BookResponse(1, input.title(), input.pages());
}
~~~

Handler này là một phần minh họa, giả định các record đã được khai báo và controller có `@RestController`.

**Luồng nhận dữ liệu**:

1. MVC chọn handler theo path, HTTP method và điều kiện mapping.
2. `@RequestBody` yêu cầu đọc request body; `HttpMessageConverter` thích hợp được chọn dựa vào Content-Type và Java target type.
3. Với JSON và Spring Framework 6.2/Jackson 2, converter thông thường là `MappingJackson2HttpMessageConverter` sử dụng `ObjectMapper` để parse và tạo `CreateBookRequest`.
4. Nếu controller khai báo `@Valid` thì Bean Validation chạy sau khi deserialize thành công.
5. Handler xử lý nghiệp vụ và tạo giá trị trả về.
6. `@ResponseBody` (trực tiếp hoặc từ `@RestController`) làm Spring dùng converter ghi object thành JSON trong HTTP response.

**Những phân biệt cần nhớ**:

| Khái niệm | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| Serialization | Object Java → JSON bytes | `BookResponse` trả cho browser |
| Deserialization | JSON bytes → Object Java | `@RequestBody CreateBookRequest` |
| DTO mapping | Domain/entity → contract của API | `BookEntity` → `BookResponse` |
| Bean Validation | Kiểm tra quy tắc của object sau parse | `@NotBlank`, `@Min` |
| `ResponseEntity<T>` | Điều khiển status, headers và body | `201 Created` + `BookResponse` |
| `HttpMessageConverter` | Đọc/ghi HTTP body theo media type | Jackson JSON converter |
| `ObjectMapper` | Jackson API để map JSON ↔ Java object | `readValue`, `writeValueAsString` |

`@RestController` tương đương dùng `@Controller` cùng `@ResponseBody` ở class. Với `@Controller` thuần, một giá trị trả về dạng `String` có thể được hiểu là tên **view** chứ không phải chuỗi JSON. `ResponseEntity` bọc status và headers ở lớp HTTP, không mặc nhiên serialize bản thân nó thành JSON body.

### 2.1. Content-Type và Accept

- `Content-Type: application/json` nói rằng body client gửi là JSON.
- `Accept: application/json` đề nghị server trả JSON.
- Handler có `consumes = "application/json"` có thể trả **415 Unsupported Media Type** nếu client gửi Content-Type khác.
- Nếu client chỉ chấp nhận media type mà server không thể tạo theo `produces`/converter, có thể trả **406 Not Acceptable**.
- JSON hỏng cú pháp hoặc value không thể chuyển sang Java type phù hợp thường dẫn tới **400 Bad Request** trước khi handler chạy.
- Một lỗi **serialization** khi ghi response (ví dụ vòng graph) là lỗi phía server, không phải mặc nhiên là lỗi JSON input của client.

Spring Boot 3.x với `spring-boot-starter-web` thông thường đã có Jackson và cấu hình JSON message converter. Không cần tự tạo `ObjectMapper` mới trong mọi controller.

## 3. Java object được biểu diễn thành JSON như thế nào?

JSON có object, array, string, number, boolean và `null`. Nó không mang Java class, package, setter, constructor, generic parameter hoặc kiểu JPA. Jackson dùng metadata từ Java type, accessor và annotation để xác định field JSON.

JavaBean:

~~~java
public class BookBean {
    private long id;
    private String title;

    public BookBean() {}
    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
}
~~~

Record trong Java 17:

~~~java
public record BookResponse(long id, String title, int pages) {}
~~~

Jackson 2 trong Spring Boot 3.x hỗ trợ Java records. Giá trị `new BookResponse(1, "Java", 300)` tương đương JSON:

~~~json
{"id":1,"title":"Java","pages":300}
~~~

Để deserialize một DTO, Jackson cần cách xây dựng object phù hợp: canonical constructor cho record, hoặc constructor/factory/getter-setter/field theo cấu hình cho class. Không phải mọi class immutable đều được hỗ trợ tự động nếu thiếu creator và metadata tương ứng.

**Object property order trong JSON không được bảo đảm là contract.** Khi test, so sánh field bằng JSONPath hoặc parse tree thay vì đòi raw JSON string trùng từng ký tự.

### 3.1. Jackson annotations thiết yếu

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

public record PublicUser(
        @JsonProperty("user_id") long id,
        String username,
        @JsonInclude(JsonInclude.Include.NON_NULL) String nickname) {}
~~~

Với `new PublicUser(5, "lan", null)`, Jackson tạo JSON tương đương:

~~~json
{"user_id":5,"username":"lan"}
~~~

| Annotation | Tác động điển hình | Chú ý |
| --- | --- | --- |
| `@JsonProperty("name")` | Đổi tên property trong JSON | Là thay đổi API contract |
| `@JsonIgnore` | Bỏ property khỏi JSON binding | Cần xem ảnh hưởng cả chiều đọc/ghi |
| `@JsonIgnoreProperties({...})` | Bỏ các property được chỉ ra | Không thay authorization |
| `@JsonInclude(NON_NULL)` | Không serialize các field null | Không bắt buộc giá trị tồn tại |
| `@JsonFormat` | Format JSON cho ngày/giờ, số, enum… | Do Jackson xử lý |
| `@JsonCreator` | Chỉ rõ constructor/factory deserialize | Hay đi cùng `@JsonProperty` |
| `@JsonView` | Chọn tập property theo view | Phải kiểm thử các view và bảo vệ dữ liệu |

Ví dụ JSON chứa ngày:

~~~java
import java.time.LocalDate;
import com.fasterxml.jackson.annotation.JsonFormat;

public record EventResponse(
        @JsonFormat(pattern = "yyyy-MM-dd")
        LocalDate eventDate) {}
~~~

Với Spring Boot 3.x, Jackson Java Time module thường có sẵn qua dependency được quản lý. `@JsonFormat` tác động vào **Jackson JSON mapping**. `@DateTimeFormat` chủ yếu dùng trong **Spring MVC request parameter / form binding**: không nên dùng lẫn hai annotation rồi giả định JSON được xử lý như form.

### 3.2. JSON field vắng mặt, null và field không mong đợi

Giả sử:

~~~java
public record CreateBookRequest(String title, Integer pages) {}
~~~

Body `{"title":"A"}` và `{"title":"A","pages":null}` thường đều cho `pages == null` trong cấu hình quen thuộc. Nếu field bắt buộc, dùng `@NotNull` kết hợp `@Valid`. Với PATCH cần phân biệt "không cung cấp field", "cung cấp null" và "cung cấp value", dùng contract thích hợp (JSON Merge Patch, presence wrapper hoặc JsonNode), thay vì coi null và vắng mặt là như nhau.

Jackson có thể bỏ qua unknown fields trong cấu hình Spring Boot thông thường, nhưng chính sách này cấu hình được. Unknown-field behavior cần được định nghĩa và kiểm thử. Dù có từ chối field lạ, authorization vẫn phải được kiểm tra riêng.

## 4. DTO — hợp đồng rõ ràng giữa client và server

**DTO (Data Transfer Object)** chứa dữ liệu API được phép nhận/gửi. Entity/domain model có thể chứa quan hệ và trạng thái mà client không nên thấy.

Ví dụ entity nội bộ (minh họa):

~~~java
class AccountEntity {
    long id;
    String displayName;
    String passwordHash;
    boolean administrator;
    TeamEntity team;
}
~~~

Nếu controller trả entity trực tiếp, serializer có thể thấy hash, trạng thái quản trị hoặc đi theo liên kết `team`. Với JPA/Hibernate còn có thể phát sinh lazy loading, N+1 query và vòng tham chiếu.

Response DTO:

~~~java
public record AccountResponse(long id, String displayName) {}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.NotBlank;

public record UpdateAccountRequest(@NotBlank String displayName) {}
~~~

Mapping trong service:

~~~java
AccountResponse toResponse(AccountEntity account) {
    return new AccountResponse(account.id, account.displayName);
}
~~~

Các đoạn trên minh họa thiết kế, chưa phải file chạy độc lập vì chưa định nghĩa `TeamEntity` và các thành phần cần thiết khác.

**Vì sao tách request và response DTO?**

- Client không được tự đặt `id`, `role`, `balance` hoặc `passwordHash` chỉ bằng cách thêm property vào JSON.
- Service quyết định trường nào sửa được và thực hiện kiểm tra authorization.
- Response chỉ có field được công bố; không lộ object graph hay property nội bộ.
- DB schema và entity có thể thay đổi mà không phải đổi JSON contract.
- API versioning, validation và tài liệu OpenAPI dễ mô tả hơn.

DTO record gọn và immutable, phù hợp snapshot thông tin. DTO class vẫn hữu ích khi có yêu cầu construction/mapping đặc biệt. **Không bind `@RequestBody` trực tiếp vào JPA entity** nếu nó có nhiều field ngoài quyền sửa của người dùng. DTO hạn chế field không tự thay thế kiểm tra quyền xem/sửa resource trong service.

## 5. Generic response và type erasure

### 5.1. Generic DTO đơn và lồng nhau

~~~java
public record ApiResponse<T>(String status, T data) {}
~~~

Dùng cho một giá trị:

~~~java
ApiResponse<BookResponse> one =
        new ApiResponse<>("ok", new BookResponse(1, "Java", 300));
~~~

Dùng cho nhiều giá trị:

~~~java
ApiResponse<List<BookResponse>> many = new ApiResponse<>(
        "ok",
        List.of(
                new BookResponse(1, "Java", 300),
                new BookResponse(2, "Spring", 240)));
~~~

JSON của `many`:

~~~json
{
  "status": "ok",
  "data": [
    {"id":1,"title":"Java","pages":300},
    {"id":2,"title":"Spring","pages":240}
  ]
}
~~~

**JSON không ghi "ApiResponse<List<BookResponse>>" vào body.** Nó chỉ có object và array. Java generics ở runtime chịu **type erasure**, vì vậy lúc tự đọc JSON phải cung cấp đủ kiểu phần tử.

Spring MVC thường có thể xác định generic target từ **chữ ký handler**:

~~~java
@PostMapping("/batch")
public void receive(@RequestBody List<BookResponse> books) {
    // Spring biết element type BookResponse từ method signature.
}
~~~

Đây chỉ là chữ ký minh họa. Để validate từng item list còn phải xét container element validation/cấu hình tương ứng; không tự suy ra `@Valid` trên collection nào cũng xử lý giống một request DTO thuần.

### 5.2. Sai lầm khi dùng raw List.class

~~~java
ObjectMapper mapper = new ObjectMapper();
List<?> rawBooks = mapper.readValue(
        "[{\"id\":1,\"title\":\"Java\",\"pages\":300}]",
        List.class);
System.out.println(rawBooks.get(0).getClass().getName());
~~~

Stdout với Jackson 2 mặc định:

~~~text
java.util.LinkedHashMap
~~~

Vì `List.class` thiếu thông tin phần tử, một object JSON mặc định được chuyển thành `LinkedHashMap`. Ép trực tiếp `(BookResponse) rawBooks.get(0)` có thể ném `ClassCastException`.

### 5.3. Đúng: TypeReference<T>

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

ObjectMapper mapper = new ObjectMapper();
String json = """
    [{"id":1,"title":"Java","pages":300}]
    """;

List<BookResponse> books =
        mapper.readValue(json, new TypeReference<List<BookResponse>>() {});
System.out.println(books.get(0).title());
~~~

Stdout:

~~~text
Java
~~~

Đoạn này giả định `BookResponse` record đã được khai báo. Với generic wrapper:

~~~java
ApiResponse<List<BookResponse>> result = mapper.readValue(
        """
        {"status":"ok","data":[{"id":1,"title":"Java","pages":300}]}
        """,
        new TypeReference<ApiResponse<List<BookResponse>>>() {});
~~~

Anonymous subclass của `TypeReference` nắm giữ signature generic cụ thể. Nếu tạo `new TypeReference<List<T>>() {}` bên trong một generic method mà `T` vẫn chưa được ràng buộc thành class cụ thể, runtime không tự biết `T` thật.

### 5.4. Đúng: JavaType khi dựng kiểu ở runtime

~~~java
import com.fasterxml.jackson.databind.JavaType;

JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, BookResponse.class);
JavaType nestedType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, listType);

ApiResponse<List<BookResponse>> parsed =
        mapper.readValue(json, nestedType);
~~~

Biến `json` ở đây cần chứa một object `ApiResponse` như ví dụ trước. `JavaType` thích hợp khi loại phần tử là một giá trị `Class<?>` chỉ biết lúc chạy. Với Spring clients có API nhận `ParameterizedTypeReference<T>`, có thể viết:

~~~java
ParameterizedTypeReference<ApiResponse<List<BookResponse>>> responseType =
        new ParameterizedTypeReference<>() {};
~~~

Import `org.springframework.core.ParameterizedTypeReference`. Đây là type token của **Spring**, khác với `com.fasterxml.jackson.core.type.TypeReference` của **Jackson**; không truyền trực tiếp cái này vào `ObjectMapper.readValue`.

| Bối cảnh | Cách xác định kiểu |
| --- | --- |
| Spring MVC handler `@RequestBody List<BookDto>` | Chữ ký tham số controller |
| Controller trả `ResponseEntity<ApiResponse<List<BookDto>>>` | Chữ ký return type cùng object thật |
| Jackson `readValue(json, List.class)` | Mất element type, thường có Map |
| Jackson `readValue(json, new TypeReference<List<BookDto>>() {})` | Giữ element type |
| Jackson với kiểu dựng động | Dùng `JavaType`/`TypeFactory` |
| Spring HTTP client có generic API | Dùng `ParameterizedTypeReference<T>` khi overload hỗ trợ |

`ResponseEntity<T>` bọc response HTTP, không phải field tự động trong JSON. Nếu muốn status ở body, phải khai báo trong `ApiResponse<T>`; status HTTP 201 và `"status":"ok"` là hai thành phần khác nhau.

## 6. Vòng tham chiếu trong object graph

Giả sử quan hệ hai chiều:

~~~java
class Team {
    public long id;
    public String name;
    public List<User> users = new ArrayList<>();
}

class User {
    public long id;
    public String username;
    public Team team;
}
~~~

Các import `java.util.List` và `java.util.ArrayList` cần có. Sau khi tạo `team.users.add(user)` và `user.team = team`, graph trở thành:

~~~text
Team
 └─ users[0] → User
                  └─ team → Team
                                └─ users[0] → User
                                                  └─ ...
~~~

Jackson tự duyệt property mà không có cấu trúc chặn vòng có thể đi qua `team.users[0].team.users[0]...`, gây lỗi recursion/serialization hoặc giới hạn độ sâu, tùy phiên bản. Trong HTTP response có thể gây lỗi server. Một object graph Java có thể tham chiếu lại cùng một instance; JSON object/array thông thường không có cơ chế Java pointer identity riêng.

### 6.1. Giải pháp ưu tiên: DTO có độ sâu hữu hạn

Thay vì trả entity graph đầy đủ:

~~~java
record TeamSummary(long id, String name) {}
record UserResponse(long id, String username, TeamSummary team) {}
~~~

JSON:

~~~json
{
  "id":10,
  "username":"lan",
  "team":{"id":3,"name":"Platform"}
}
~~~

TeamSummary không chứa users. Với endpoint GET team, dùng DTO riêng:

~~~java
record UserSummary(long id, String username) {}
record TeamResponse(long id, String name, List<UserSummary> members) {}
~~~

Do đó response có chỗ dừng. Service chọn đúng dữ liệu cần truy vấn; nếu dùng JPA, có thể dùng projection/fetch phù hợp để tránh N+1. Tạo DTO không tự đảm bảo SQL hiệu quả nhưng cho phép kiểm soát chính xác contract.

### 6.2. @JsonIgnore: bỏ chiều không cần thiết

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

class User {
    public long id;
    public String username;

    @JsonIgnore
    public Team team;
}
~~~

Khi serialize Team với list Users, thuộc tính User.team bị bỏ, làm đứt vòng. Tuy nhiên User cũng mất thông tin team khi serialize riêng theo mapping này. Nếu các endpoint cần JSON khác nhau, response DTO vẫn rõ ràng hơn việc đổi annotation entity tùy trường hợp.

### 6.3. @JsonManagedReference và @JsonBackReference

~~~java
import com.fasterxml.jackson.annotation.JsonManagedReference;
import com.fasterxml.jackson.annotation.JsonBackReference;

class Team {
    public long id;
    public String name;

    @JsonManagedReference
    public List<User> users = new ArrayList<>();
}

class User {
    public long id;
    public String username;

    @JsonBackReference
    public Team team;
}
~~~

Khi serialize Team, chiều `Team → users` được ghi, còn reference ngược `User → team` không được ghi:

~~~json
{
  "id":3,
  "name":"Platform",
  "users":[{"id":10,"username":"lan"}]
}
~~~

Với parent-child phù hợp, Jackson còn có thể khôi phục backlink trong deserialization. Các cặp managed/back cần đúng hướng và tên; nếu có nhiều quan hệ độc lập, có thể đặt tên cặp rõ ràng, ví dụ `@JsonManagedReference("members")` và `@JsonBackReference("members")`.

**Giới hạn:** đây là quy tắc có hướng. Serialize User riêng thì Team có thể bị loại bỏ; không thích hợp máy móc cho many-to-many hoặc quan hệ hai list đối xứng. Phải xác định JSON contract trước khi dùng.

### 6.4. @JsonIdentityInfo: biểu diễn object bằng identity

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class Team {
    public long id;
    public String name;
    public List<User> users = new ArrayList<>();
}

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class User {
    public long id;
    public String username;
    public Team team;
}
~~~

Một dạng JSON có thể được tạo khi serialize Team làm root (thứ tự duyệt và identity scope ảnh hưởng chi tiết):

~~~json
{
  "id":3,
  "name":"Platform",
  "users":[{"id":10,"username":"lan","team":3}]
}
~~~

Lần đầu object xuất hiện có thể được ghi đầy đủ, lần sau ghi id thay vì đệ quy tiếp. Điều này **thay đổi contract**: client phải hiểu chỗ nào là object, chỗ nào là id. Object id cần tồn tại và nhất quán. Deserialization một reference id không có định nghĩa object tương ứng có thể đòi resolver riêng, không tự truy vấn database.

Nếu dùng `@JsonIdentityReference(alwaysAsId = true)` thì cần đặc biệt kiểm tra phía client có đủ dữ liệu và có thể khôi phục reference hay không. Đừng chọn identity annotation chỉ vì muốn hết exception mà chưa biết dạng JSON đích.

### 6.5. Chọn cách nào?

| Cách | Hiệu ứng | Phù hợp khi | Điểm cần tránh |
| --- | --- | --- | --- |
| DTO hữu hạn | Chỉ xuất dữ liệu đã chọn | API public, hợp đồng ổn định | Mapper vẫn phải truy vấn hiệu quả |
| `@JsonIgnore` | Loại một property | Field thực sự không cần xuất | Có thể làm mất field ở endpoint khác |
| Managed/back | Serialize một chiều parent → child | Quan hệ cha-con rõ | Không phù hợp mọi graph |
| `@JsonIdentityInfo` | Thay object lặp bằng id | Client hiểu identity references | Contract phức tạp, cần id resolver |
| Đổi hết sang EAGER | Không cắt vòng | Không phải giải pháp | N+1/payload phình to |

**Lưu ý JPA/Hibernate:** vòng quan hệ, lỗi lazy initialization và truy vấn N+1 là các vấn đề riêng nhưng thường xuất hiện cùng khi trả entity trực tiếp. Đừng chữa tất cả bằng cách tăng fetch eager, bật Open Session in View hoặc nâng giới hạn JSON nesting. Thiết kế service load đúng dữ liệu và map sang DTO.

## 7. Validation và lỗi JSON cần phân biệt

Ví dụ request DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;

public record CreateBookRequest(
        @NotBlank String title,
        @NotNull @Min(1) Integer pages) {}
~~~

Handler có `@Valid`:

~~~java
@PostMapping("/books")
public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    // Service xử lý và tạo response...
}
~~~

Đoạn handler minh họa chữ ký; tham khảo mục 9 để có code chạy đầy đủ.

| Input | Loại lỗi/kết quả thường gặp |
| --- | --- |
| `{"title":"Java","pages":200}` | JSON parse và validation OK |
| `{"title":"","pages":200}` | `@NotBlank` không đạt → HTTP 400 |
| `{"title":"Java","pages":0}` | `@Min(1)` không đạt → HTTP 400 |
| `{"title":"Java","pages":null}` | `@NotNull` không đạt → HTTP 400 |
| `{"title":"Java","pages":"abc"}` | Lỗi Jackson mapping String → Integer → HTTP 400 |
| `{"title":` | JSON cú pháp hỏng → HTTP 400 |
| Body không phải JSON, handler `consumes=application/json` | HTTP 415 |
| Accept không phù hợp converter/produces | HTTP 406 |

Bean Validation cần provider, trong Spring Boot dùng `spring-boot-starter-validation`. JSON parse lỗi thường được Spring MVC bọc qua `HttpMessageNotReadableException`, còn validation failure cho `@Valid @RequestBody` trong cấu hình phổ biến qua `MethodArgumentNotValidException`. Loại exception còn tùy cấu hình method validation; không hardcode nội dung lỗi framework như contract.

Nếu muốn response lỗi thống nhất, dùng `@RestControllerAdvice` với `@ExceptionHandler` và DTO lỗi đã định nghĩa. Validation không thay thế authorization, giới hạn request size, giới hạn collection length hoặc bảo vệ tài nguyên.

## 8. Phân biệt Jackson JSON với form binding

| Client gửi | Annotation thường chọn | Công cụ |
| --- | --- | --- |
| JSON body `{"title":"Java"}` | `@RequestBody CreateBookRequest` | Jackson HTTP converter |
| Query string `?page=2` | `@RequestParam int page` | ConversionService/Formatter |
| HTML form `title=Java&pages=200` | `@ModelAttribute CreateBookForm` | WebDataBinder + Spring conversion |
| URL `/books/7` | `@PathVariable long id` | Spring conversion |
| Response Java DTO → JSON | `@ResponseBody` hoặc `@RestController` | JSON message converter |

`@DateTimeFormat` chủ yếu cấu hình Spring formatting với parameters/form; `@JsonFormat` điều chỉnh Jackson JSON. Cùng một `LocalDate` nhưng hai đường binding có thể được cấu hình riêng. Không giả định multipart/form hoặc form-url-encoded được parse như JSON chỉ vì controller có DTO.

## 9. Ví dụ thực hành hoàn chỉnh: Book REST API

Dự án Maven, Java 17, Spring Boot 3.5.0. Dữ liệu lưu trong memory để tập trung vào JSON. Controller có request DTO riêng, response DTO riêng và generic response wrapper. Domain entity có `internalNote` nhưng client không bao giờ thấy nó.

Cấu trúc:

~~~text
json-dto-demo/
├── pom.xml
└── src/
    ├── main/java/demo/JsonDtoApplication.java
    └── test/java/demo/BookControllerTest.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>json-dto-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. JsonDtoApplication.java

Đặt toàn bộ mã dưới đây trong file `src/main/java/demo/JsonDtoApplication.java`. Java cho phép nhiều package-private class/record trong cùng một file nhưng chỉ có một top-level public class trùng tên file.

~~~java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDtoApplication.class, args);
    }
}

// Client chỉ được truyền title và pages; id do server tạo.
record CreateBookRequest(
        @NotBlank String title,
        @NotNull @Min(1) Integer pages) {
}

// API response không có thông tin nội bộ.
record BookResponse(long id, String title, int pages) {
    static BookResponse from(BookEntity book) {
        return new BookResponse(book.id(), book.title(), book.pages());
    }
}

// Wrapper generic: T có thể là BookResponse hoặc List<BookResponse>.
record ApiResponse<T>(String status, T data) {
}

// Domain object không được trả trực tiếp qua HTTP.
record BookEntity(long id, String title, int pages, String internalNote) {
}

@RestController
@RequestMapping(path = "/api", produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final Map<Long, BookEntity> books = new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(2);

    BookController() {
        books.put(1L, new BookEntity(1, "Java Basics", 200, "private-a"));
        books.put(2L, new BookEntity(2, "Spring MVC", 240, "private-b"));
    }

    @GetMapping("/books")
    public ResponseEntity<ApiResponse<List<BookResponse>>> list() {
        List<BookResponse> data = books.values().stream()
                .sorted(Comparator.comparingLong(BookEntity::id))
                .map(BookResponse::from)
                .toList();
        return ResponseEntity.ok(new ApiResponse<>("ok", data));
    }

    @GetMapping("/books/{id}")
    public ResponseEntity<ApiResponse<BookResponse>> one(
            @PathVariable long id) {
        BookEntity book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
                new ApiResponse<>("ok", BookResponse.from(book)));
    }

    @PostMapping(path = "/books",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ApiResponse<BookResponse>> create(
            @Valid @RequestBody CreateBookRequest request) {
        long id = ids.incrementAndGet();
        BookEntity book = new BookEntity(
                id, request.title(), request.pages(), "server-only");
        books.put(id, book);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new ApiResponse<>("ok", BookResponse.from(book)));
    }
}
~~~

Điểm chính của code:

- `@RestController` kích hoạt serialization cho response.
- `@RequestBody` dùng Jackson để tạo `CreateBookRequest`; `@Valid` yêu cầu Bean Validation.
- Response method trả `ResponseEntity<ApiResponse<List<BookResponse>>>` hoặc `ResponseEntity<ApiResponse<BookResponse>>` với generic type rõ ràng.
- Chỉ `BookResponse` được chuyển thành JSON; `internalNote` trong `BookEntity` không có trong API payload.
- `ConcurrentHashMap` và `AtomicLong` giúp demo hoạt động khi có request đồng thời. Data chỉ tồn tại trong memory, mất sau restart; đây không phải ví dụ persistence production.
- GET list sắp xếp theo id để ví dụ và test có thứ tự mảng xác định.

### 9.3. Chạy và kiểm tra HTTP

Tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

GET list:

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'
~~~

HTTP **200 OK**, body tương đương:

~~~json
{
  "status": "ok",
  "data": [
    {"id":1,"title":"Java Basics","pages":200},
    {"id":2,"title":"Spring MVC","pages":240}
  ]
}
~~~

POST tạo book:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Modern Java","pages":310}'
~~~

Với POST đầu tiên trên instance vừa khởi động, trả **201 Created**, body tương đương:

~~~json
{
  "status": "ok",
  "data": {"id":3,"title":"Modern Java","pages":310}
}
~~~

Lần POST tiếp theo có id lớn hơn. Không có `internalNote` trong body. GET `/api/books/1` trả DTO với id 1, còn `/api/books/999` (khi chưa có id này) trả 404 với body trống theo handler.

Thử sai validation:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data '{"title":"","pages":0}'
~~~

HTTP thường là **400 Bad Request** do `@NotBlank` và `@Min(1)`. Body thông báo lỗi mặc định không cố định, nên không dự đoán nguyên văn. Nếu gửi `{"title":"X","pages":"abc"}`, lỗi xảy ra trước validation ở bước deserialize Integer.

Ví dụ shell trên dùng cách nối dòng `\` của Bash. Trên Windows PowerShell, có thể dùng `curl.exe` trên một dòng hoặc ký tự nối dòng PowerShell phù hợp; alias `curl` có thể không phải chương trình curl thực.

### 9.4. Test HTTP contract và nested generic

Tạo file `src/test/java/demo/BookControllerTest.java`:

~~~java
package demo;

import java.util.List;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void getListHasOnlyDtoFields() throws Exception {
        mvc.perform(get("/api/books").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.data[0].title").value("Java Basics"))
            .andExpect(jsonPath("$.data[0].internalNote").doesNotExist());
    }

    @Test
    void createReturns201AndHidesInternalData() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Modern Java","pages":310}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.data.title").value("Modern Java"))
            .andExpect(jsonPath("$.data.pages").value(310))
            .andExpect(jsonPath("$.data.internalNote").doesNotExist());
    }

    @Test
    void invalidDtoReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"","pages":0}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void readNestedGenericWithoutRawMap() throws Exception {
        String json = """
                {"status":"ok",
                 "data":[{"id":1,"title":"Java Basics","pages":200}]}
                """;
        ApiResponse<List<BookResponse>> decoded = mapper.readValue(
                json, new TypeReference<ApiResponse<List<BookResponse>>>() {});
        assertEquals("ok", decoded.status());
        assertEquals(BookResponse.class, decoded.data().get(0).getClass());
        assertEquals("Java Basics", decoded.data().get(0).title());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test HTTP kiểm tra status và JSONPath thay vì thứ tự property. Test generic khẳng định Jackson tạo được `BookResponse` thay vì Map. Các test dùng context chung nên test POST có thể thêm book mới; GET list vẫn luôn có hai book seeded với id 1 và id 2 ở đầu khi sắp xếp theo id.

## 10. JSON cycle với JPA/Hibernate: xử lý ở tầng nào?

Mối quan hệ JPA:

~~~java
// Minh họa hình dạng relationship, chưa phải entity chạy độc lập.
@Entity
class Department {
    @OneToMany(mappedBy = "department")
    List<Employee> employees;
}

@Entity
class Employee {
    @ManyToOne(fetch = FetchType.LAZY)
    Department department;
}
~~~

Cần chú ý bốn rủi ro riêng:

1. **Graph cycle:** Department → employees → department → … nếu serialize quan hệ hai chiều.
2. **LazyInitializationException:** Jackson truy cập association khi persistence context đã đóng.
3. **N+1 queries:** mỗi nested getter có thể kéo thêm truy vấn.
4. **Data exposure:** entity lộ field nội bộ.

Đổi tất cả sang `FetchType.EAGER` không giải quyết cycle và có thể tăng tải. Đặt `@JsonIgnore` bừa trên entity có thể làm thay đổi API của nhiều endpoint. Thiết kế query/projection lấy đúng field, chuyển sang DTO trong phạm vi dữ liệu còn dùng được và trả DTO. Cấu hình Hibernate module cho Jackson (nếu có) không thay thế thiết kế JSON contract.

## 11. Lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| `LinkedHashMap cannot be cast to BookResponse` | Đọc JSON generic bằng raw `List.class` | `TypeReference`/`JavaType` |
| 400 do JSON parse | JSON không hợp lệ/field sai kiểu | Kiểm tra body, Content-Type và root cause |
| 400 do validation | Parse xong nhưng constraint sai | `@Valid`, constraint, handler errors |
| 415 | Sai Content-Type | Kiểm tra `consumes` |
| 406 | Sai Accept/produces/converter | Kiểm tra `Accept` và `produces` |
| 500 khi serialize graph | Vòng object hoặc getter lỗi | Response DTO hữu hạn, xem stacktrace |
| LazyInitializationException | Đụng JPA lazy relation ngoài context | Mapping/projection trong service |
| JSON lộ private field | Trả entity hoặc DTO chứa field ngoài ý muốn | Dùng response DTO allowlist |
| JSON ngày sai format | Jackson date config | `@JsonFormat` / JavaTimeModule |
| Test JSON thất bại vì key order | So sánh chuỗi JSON trực tiếp | JSONPath/parse tree |

Nhiều lỗi có cùng HTTP status nhưng xuất phát từ bước khác nhau. Khi chẩn đoán, xác định request có vào handler chưa, lỗi nằm ở parse/validation/service/serialization, rồi mới sửa đúng tầng.

Một số anti-pattern khác:

- Không dùng `Map<String,Object>` cho mọi request nếu cấu trúc đã biết; khó validate và mất type safety.
- Không coi `@JsonIgnore` hay DTO là giải pháp thay cho phân quyền resource.
- Không tăng max JSON depth để che vòng object do API serialize trực tiếp entity.
- Không dùng cách deserialize polymorphic class name từ JSON không tin cậy bằng default typing mở rộng; cần allowlist/discriminator rõ.
- Không nhét `ResponseEntity` vào property DTO rồi hy vọng Jackson tự hiểu HTTP headers.
- Không tự đoán unknown-field handling; ghi rõ policy và kiểm thử.
- Không ép `LocalDateTime` thành một UTC instant khi JSON không có offset/zone.
- Không tự giả định field null bị lược bỏ trừ khi có cấu hình/annotation tương ứng.

## 12. Bài tập tự luyện

**Bài 1 — DTO và bảo mật:** Entity `Customer` có `id, displayName, email, passwordHash, role`. Tạo `CustomerCreateRequest` chỉ nhận `displayName,email` và `CustomerResponse` chỉ trả `id,displayName`. Nêu nơi kiểm tra quyền role.

**Bài 2 — Generic:** Cho `{"status":"ok","data":[{"id":1,"title":"Java","pages":200}]}`. Viết `TypeReference<ApiResponse<List<BookResponse>>>` và dự đoán kiểu `data.get(0)` nếu chỉ dùng `ApiResponse.class`.

**Bài 3 — Cycle:** Dựng sơ đồ `Department ↔ Employee`. Thiết kế `DepartmentResponse` chứa `List<EmployeeSummary>`, trong `EmployeeSummary` không còn `department.employees`. Vì sao chặn được recursion?

**Bài 4 — Annotation:** So sánh `@JsonIgnore`, managed/back references và identity. Với endpoint GET Team có users nhưng user không cần chứa Team, chọn cách hợp lý; với API công khai lâu dài, cân nhắc DTO.

**Bài 5 — Validation:** Dự đoán bước thất bại cho `pages=0`, `pages=null` và `pages="abc"`. Vì sao validator không được gọi cho tất cả trường hợp?

**Bài 6 — HTTP:** Phân biệt 400 parse, 400 validation, 415, 406 và server-side serialization error. Thêm test vào dự án mục 9.

**Bài 7 — Compatibility:** Client cũ chỉ biết `id,title`; client mới muốn thêm `pages,language`. Đề xuất cách mở rộng response DTO, versioning và unknown-field policy.

## 13. Tài liệu tham khảo

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html).
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework 6.2 — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html).
- [Jackson 2 — ObjectMapper Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.18.4/com/fasterxml/jackson/databind/ObjectMapper.html).
- [Jackson 2 — TypeReference Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.18.4/com/fasterxml/jackson/core/type/TypeReference.html).
- [Jackson 2 — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonManagedReference.html), [JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonBackReference.html), [JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonIdentityInfo.html).

