# Bean Validation với @Valid, @Validated và nhóm ràng buộc trong Spring MVC

## 1. Mục tiêu và phạm vi

Ứng dụng web phải xác minh dữ liệu đầu vào trước khi dùng cho nghiệp vụ. Spring MVC hỗ trợ tích hợp **Jakarta Bean Validation** để khai báo các quy tắc ngay trên đối tượng và kích hoạt kiểm tra khi bind dữ liệu vào tham số controller.

Sau bài này, bạn có thể:

1. Phân biệt **binding**, **validation** và **business validation**.
2. Biết vai trò của `@Valid`, `@Validated`, các annotation ràng buộc như `@NotBlank`, `@NotNull`, `@Size`.
3. Tạo nhóm `Create`, `Update`, chọn nhóm chính xác cho từng endpoint và hiểu vai trò nhóm `Default`.
4. Kiểm tra đối tượng lồng nhau bằng cascade validation và tránh bỏ sót group.
5. Đọc lỗi bằng `BindingResult`, phân biệt `MethodArgumentNotValidException` với `HandlerMethodValidationException` trong Spring MVC 6.1+.
6. Viết integration test với `MockMvc` cho cả dữ liệu hợp lệ và không hợp lệ.

Phạm vi là **Spring MVC trên Servlet stack**, sử dụng Java 17+, Spring Boot 3.x và namespace `jakarta.validation`. Spring WebFlux, validator custom ngoài Bean Validation và nghiệp vụ dữ liệu có thể có quy trình bổ sung; không suy ra cùng hành vi exception cho mọi framework hay mọi phiên bản.

## 2. Spring MVC kiểm tra dữ liệu ở bước nào?

Ví dụ một client gửi JSON:

```http
POST /api/users HTTP/1.1
Content-Type: application/json

{"name":"","email":"khong-phai-email","password":"abc"}
```

Luồng xử lý rút gọn:

```text
HTTP request
     |
DispatcherServlet -> chọn controller/handler
     |
@RequestBody -> HttpMessageConverter (ví dụ Jackson)
     |          chuyển JSON thành đối tượng Java
     v
WebDataBinder / Validator
     |          áp dụng @Valid hoặc @Validated và constraints
     +---- có lỗi -> xử lý validation errors (thường HTTP 400)
     |
     v
Controller method -> xử lý nghiệp vụ -> HTTP response
```

Các khái niệm khác nhau:

| Khâu | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **Binding / conversion** | Đọc body/form/query rồi chuyển kiểu, gán vào Java object | JSON string sang `UserPayload`; `"7"` sang `long` |
| **Bean Validation** | Kiểm tra các constraint đã khai báo | `@NotBlank`, `@Email`, `@Size(min=8)` |
| **Business validation** | Kiểm tra quy tắc phụ thuộc trạng thái hệ thống và transaction | Email đã tồn tại trong DB, user có quyền thay đổi bản ghi không |
| **Persistence constraints** | Ràng buộc của cơ sở dữ liệu, bảo vệ tính nhất quán cuối cùng | `UNIQUE(email)`, `NOT NULL`, foreign key |

**Bean Validation không thay thế ràng buộc DB hoặc authorization**. Trên hai request đồng thời, cả hai có thể vượt qua kiểm tra “email chưa tồn tại”, nên database vẫn cần unique constraint và ứng dụng cần xử lý lỗi tranh chấp.

### Các thành phần liên quan

- `jakarta.validation` định nghĩa annotation, `Validator`, `ConstraintViolation`, group và contract chuẩn.
- **Hibernate Validator** là một implementation phổ biến của Jakarta Bean Validation, thường được Spring Boot chọn qua `spring-boot-starter-validation`. Nó không đồng nghĩa với Hibernate ORM/JPA.
- `org.springframework.validation.Validator` là interface validation của Spring. `LocalValidatorFactoryBean` làm cầu nối Jakarta Bean Validation với Spring `SmartValidator` và `Errors`.
- `@Valid` được định nghĩa bởi **Jakarta Validation**: `jakarta.validation.Valid`.
- `@Validated` được định nghĩa bởi **Spring Framework**: `org.springframework.validation.annotation.Validated`.

Nếu dự án chỉ thêm API annotation mà **thiếu implementation Validator**, việc khai báo constraint không đủ để bảo đảm chúng thực sự được kiểm tra. Trong Spring Boot 3.x, khai báo starter validation tường minh.

## 3. Các constraint cơ bản và ý nghĩa thực tế

| Constraint | Mục đích | Điều cần nhớ |
| --- | --- | --- |
| `@NotNull` | Giá trị khác `null` | Chuỗi `""` và `"   "` vẫn hợp lệ |
| `@NotEmpty` | Không `null` và không rỗng: chuỗi/collection/map/array phù hợp | Chuỗi chỉ chứa khoảng trắng vẫn có thể hợp lệ |
| `@NotBlank` | Chuỗi khác `null` và chứa ít nhất một ký tự không phải whitespace | Dùng cho trường text bắt buộc |
| `@Size(min=…, max=…)` | Độ dài chuỗi hoặc kích thước collection/map/array | `null` thường được xem là hợp lệ; kết hợp `@NotNull`/`@NotBlank` khi bắt buộc |
| `@Email` | Kiểm tra cú pháp email theo validator | Không chứng minh email tồn tại hoặc thuộc về người gửi; thường kết hợp `@NotBlank` |
| `@Min` / `@Max` | Giới hạn giá trị số nguyên/ngữ nghĩa số | Với số thập phân cần xem `@DecimalMin`/`@DecimalMax` |
| `@Positive` / `@PositiveOrZero` | Số dương / không âm | Không buộc khác `null` |
| `@Pattern(regexp="…")` | Kiểm tra regex trên chuỗi | Chỉ phù hợp một định dạng có ranh giới rõ; tránh regex phức tạp dễ sai |
| `@Past` / `@Future` | Ngày/giờ so với hiện tại | Liên quan clock/time zone, cần test với clock phù hợp |
| `@Null` | Yêu cầu giá trị là `null` | Hữu ích cho ID chỉ do server sinh ở request tạo mới |
| `@AssertTrue` | Giá trị Boolean phải đúng | Không thay thế rule nghiệp vụ phụ thuộc database |

Ví dụ:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

record ProductRequest(
        @NotBlank String title,
        @Positive long stockQuantity,
        @NotBlank @Email String contactEmail,
        @Size(max = 200) String description) {
}
```

Đây là **DTO mẫu**, chưa có HTTP endpoint. Có hai điểm cần thận trọng:

- `@Positive long stockQuantity` chặn `0`, trong khi nhiều nghiệp vụ cho phép tồn kho `0`; khi đó hãy dùng `@PositiveOrZero`.
- `@Size(max=200)` không làm `description` bắt buộc. Nếu được phép bỏ trống, `null` là giá trị hợp lệ; nếu bắt buộc, bổ sung constraint riêng.

Các annotation chỉ có hiệu lực ở **điểm kích hoạt validation**: Spring MVC không tự kiểm tra mọi object vừa được tạo bằng `new`, gán bằng setter hay tải từ DB.

## 4. `@Valid` và `@Validated` khác nhau thế nào?

### `@Valid` — đánh dấu cần kiểm tra đối tượng và cascade

`@Valid` là annotation của Jakarta Validation. Trên DTO tham số MVC, nó thông báo Spring kiểm tra object khi thích hợp. Mặc định dùng **nhóm `Default`**. Đặt `@Valid` trên tham chiếu object lồng nhau giúp validation đi tiếp xuống object đó (cascade).

```java
@PostMapping("/users")
public void create(@Valid @RequestBody UserPayload body) {
    // Chỉ vào được method khi validation/binding thành công
    // hoặc khi có BindingResult xử lý lỗi theo cách chủ động.
}
```

Đoạn method là fragment minh họa. Nếu chỉ dùng `@Valid` như trên, constraint khai báo **riêng `groups=Create.class`** sẽ không tự được chọn. Và `@Valid` **không chứa tham số `groups`**: cú pháp `@Valid(Create.class)` không hợp lệ.

`@Valid` bản thân **không phải constraint yêu cầu object khác null**. Để object lồng nhau bắt buộc hiện diện, dùng đồng thời `@NotNull` và `@Valid`.

### `@Validated` — Spring chọn nhóm validation

`@Validated` của Spring mở rộng cơ chế tích hợp bằng cách nhận một hoặc nhiều nhóm:

```java
@PostMapping("/users")
public void create(@Validated(Create.class) @RequestBody UserPayload body) {
    // Kiểm tra các constraint thuộc nhóm Create.
}
```

Nếu chọn `Create.class` riêng, **không mặc nhiên kiểm tra các constraint chỉ thuộc `Default`**. Muốn chạy cả quy tắc chung và quy tắc tạo mới, khai báo:

```java
@Validated({Default.class, Create.class})
```

`Default` ở đây là `jakarta.validation.groups.Default`. Việc chọn nhiều group **không bảo đảm thứ tự đánh giá**; muốn có thứ tự thì dùng `@GroupSequence`.

### Bảng so sánh nhanh

| Khía cạnh | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation` | `org.springframework.validation.annotation` |
| Mục đích phổ biến trên tham số MVC | Kích hoạt validate DTO theo Default; cascade ở thuộc tính lồng nhau | Kích hoạt validate DTO với group được chọn |
| Chọn `Create`, `Update` ngay trên annotation | Không | Có, ví dụ `@Validated(Update.class)` |
| Cascade sang object lồng nhau khi đặt trên field | **Có** | **Không thay thế `@Valid` trên field** |
| Đặt ở class level để kích hoạt AOP method validation cho Spring bean | Không theo nghĩa marker AOP của Spring | Có thể, với cơ chế `MethodValidationPostProcessor` |
| Trên controller Framework 6.1+ | Vẫn dùng cho đối tượng | Dùng ở **tham số để chọn group**; tránh class-level nếu muốn Spring MVC native method validation |

Với DTO HTTP input, bạn thường **chọn một trong hai** annotation trên tham số. Không cần đặt cả `@Valid` và `@Validated` trên cùng một tham số chỉ để chọn group; nested DTO vẫn cần `@Valid` ở vị trí cascade.

## 5. Nhóm ràng buộc (*validation groups*)

Validation group là interface marker để gắn từng constraint vào kịch bản. Một DTO có thể phục vụ nhiều hành động với quy tắc khác nhau.

Ví dụ:

- **Tạo mới**: body chưa được chứa ID; password bắt buộc và đủ độ dài.
- **Cập nhật**: body phải có ID hợp lệ; password không bắt buộc; tên/email vẫn được kiểm tra.
- **Quy tắc chung**: tên không trống, email đúng cú pháp, địa chỉ lồng nhau hợp lệ.

Khai báo nhóm:

```java
public interface Create {}
public interface Update {}
```

Dạng trên là **hai khai báo interface minh họa**, mỗi public interface phải được đặt trong tệp Java riêng nếu viết nguyên dạng. Trong ví dụ ứng dụng đầy đủ ở phần sau, chúng là interface package-private được đặt chung một tệp.

Gắn group vào constraint:

```java
record UserPayload(
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        Long id,

        @NotBlank String name,

        @NotBlank @Email String email,

        @NotBlank(groups = Create.class)
        @Size(min = 8, groups = Create.class)
        String password) {
}
```

Khi constraint không có `groups` hoặc `groups={}`, nó thuộc **`Default`**. Trong đoạn này:

| Constraint | Nhóm |
| --- | --- |
| `id` phải `null` | `Create` |
| `id` không được `null` | `Update` |
| `name` không trống | `Default` |
| `email` không trống, đúng cú pháp | `Default` |
| `password` không trống, ít nhất 8 ký tự | `Create` |

Kết quả:

| Nhóm được kích hoạt | Kiểm tra được chạy |
| --- | --- |
| Chỉ `Default`, ví dụ `@Valid` | Tên và email |
| Chỉ `Create` | ID phải null; password bắt buộc/đủ dài |
| Chỉ `Update` | ID không được null |
| `Default` + `Create` | Tên/email + ID phải null + password |
| `Default` + `Update` | Tên/email + ID bắt buộc |

Cảnh báo: `@Validated(Create.class)` **không tự chạy Default**. Đây là lỗi thiết kế phổ biến khi “thêm group” rồi vô tình vô hiệu hóa ràng buộc chung.

Nếu `@Validated` nhận group interface **kế thừa `Default`**, quy tắc từ group cha có thể được bao gồm theo semantics của Bean Validation. Tuy nhiên, chọn `{Default.class, Create.class}` là cách đọc rõ nhất khi cần cả hai nhóm.

### Group là lựa chọn quy tắc, không phải nhóm field cho JSON serializer

Bean Validation group **không mặc định quyết định field nào được Jackson nhận, trả hoặc cho phép cập nhật**. Các field không gửi vẫn có thể được deserialize thành `null` rồi được kiểm tra theo group. Không sử dụng group validation như cơ chế “ẩn trường nhạy cảm” khỏi response; cần DTO/view/security policy riêng.

## 6. Ứng dụng hoàn chỉnh: tạo và sửa người dùng

Ví dụ sau dùng **Spring Boot 3.2+ với Spring Framework 6.1+**, Java 17+, Spring MVC Servlet, Jakarta Validation. Chọn baseline này để minh họa đồng thời validation DTO và **native method validation** của Spring MVC 6.1+. Nó không giả định bạn có sẵn DB hay repository.

### Dependencies

Với dự án Gradle đã cấu hình Spring Boot plugin, repository và test runtime, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là mảnh `build.gradle`, không phải file build độc lập. Ở Maven, hai dependency runtime tương ứng cũng là `spring-boot-starter-web` và `spring-boot-starter-validation`, cộng starter test với scope `test`.

### Mã nguồn

Tạo file **`src/main/java/demo/validation/ValidationApplication.java`**:

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}

interface Create {}
interface Update {}

record Address(@NotBlank String city) {}

record UserPayload(
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        @Positive(groups = Update.class)
        Long id,

        @NotBlank String name,

        @NotBlank @Email String email,

        @NotBlank(groups = Create.class)
        @Size(min = 8, groups = Create.class)
        String password,

        @Valid @NotNull Address address) {
}

@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<Map<String, String>> create(
            @Validated({Default.class, Create.class})
            @RequestBody UserPayload body) {

        // Minh họa validation; ứng dụng thực cần ghi DB và hash password.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("name", body.name()));
    }

    @PutMapping("/{id}")
    Map<String, Object> update(
            @PathVariable long id,
            @Validated({Default.class, Update.class})
            @RequestBody UserPayload body) {

        // Validation cấu trúc không tự đảm bảo path ID == body ID.
        if (!Long.valueOf(id).equals(body.id())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "path id differs from body id");
        }

        return Map.of("id", id, "name", body.name());
    }

    @GetMapping("/page")
    Map<String, Integer> page(@RequestParam @Min(1) int number) {
        return Map.of("number", number);
    }
}
```

Code là **một tệp Java hợp lệ về cấu trúc**: chỉ `ValidationApplication` là public; những interface, record và controller còn lại là package-private. Đặt trong một project Boot như mô tả và chạy qua Boot plugin; không dùng `javac ValidationApplication.java` mà không cung cấp classpath Spring/Jakarta.

### Phân tích từng endpoint

**`POST /api/users`**

- `@Validated({Default.class, Create.class})` kích hoạt constraint chung và constraint cho lúc tạo mới.
- `id` phải `null` do `@Null(groups=Create.class)`.
- `name` và `email` bắt buộc; `email` còn phải đúng định dạng.
- `password` không blank và ít nhất 8 ký tự.
- `address` bắt buộc (`@NotNull`), và `address.city` được kiểm tra nhờ `@Valid` cascade; vì `Default` đang được chọn, constraint `@NotBlank` của `city` được áp dụng.
- Dữ liệu hợp lệ trả 201 cùng JSON `{"name":"An"}`. Đây là API demo: chưa có DB, chưa lưu password và chưa trả ID mới.

**`PUT /api/users/{id}`**

- `@Validated({Default.class, Update.class})` chạy constraint chung và constraint cập nhật.
- `id` body phải khác `null` và dương (`@NotNull`, `@Positive` thuộc `Update`).
- `password` được phép `null` vì constraint password chỉ nằm trong `Create`.
- Tên, email, address vẫn được kiểm tra do có `Default`.
- Controller **kiểm tra riêng** ID trên URL phải bằng ID trong JSON. Bean Validation field đơn lẻ không thể tự suy ra quan hệ giữa path variable và DTO này.
- Dữ liệu hợp lệ với ID 7 trả 200 cùng JSON chứa `"id":7` và `"name":"An"`.

**`GET /api/users/page?number=…`**

- `@RequestParam @Min(1) int number` kiểm tra **constraint trực tiếp trên tham số controller**, không phải DTO.
- Với Spring Framework 6.1+ và provider Bean Validation, đây là trường hợp **built-in method validation**; vi phạm có thể dẫn tới `HandlerMethodValidationException`.
- Controller ở ví dụ này **không đặt `@Validated` trên class**, để cơ chế MVC native xử lý method constraints. Trên Spring Framework trước 6.1, cơ chế validation cho tham số kiểu này khác và thường dựa vào AOP `@Validated` cấp class.

## 7. Chạy thử và đọc kết quả

Trong dự án Gradle cấu hình chuẩn, chạy:

```bash
./gradlew bootRun
```

Dùng Bash/curl tại terminal khác (ứng dụng được giả định chạy trên `localhost:8080`):

```bash
curl -i -X POST http://localhost:8080/api/users \
  -H 'Content-Type: application/json' \
  -d '{"id":null,"name":"An","email":"an@example.com","password":"secret123","address":{"city":"Ha Noi"}}'

curl -i -X POST http://localhost:8080/api/users \
  -H 'Content-Type: application/json' \
  -d '{"id":10,"name":"","email":"sai-email","password":"abc","address":{"city":""}}'

curl -i -X PUT http://localhost:8080/api/users/7 \
  -H 'Content-Type: application/json' \
  -d '{"id":7,"name":"An","email":"an@example.com","address":{"city":"Ha Noi"}}'

curl -i 'http://localhost:8080/api/users/page?number=0'
```

Các kết quả **mong đợi trong ứng dụng mẫu** (không có security/filter tùy chỉnh):

| Gọi | HTTP status | Tại sao |
| --- | --- | --- |
| POST hợp lệ | 201 Created | Cả `Default` và `Create` đều đạt |
| POST chứa ID, tên trống, email sai, password ngắn, city trống | 400 Bad Request | Vi phạm nhiều constraint thuộc `Create` và `Default` |
| PUT hợp lệ với ID 7, không có password | 200 OK | `Update` không yêu cầu password |
| GET number=0 | 400 Bad Request | `@Min(1)` trên tham số method bị vi phạm |
| GET number=2 | 200 OK | Trả `{"number":2}` |

Body lỗi **không cố định** nếu chưa thiết kế `@ControllerAdvice`: có thể là `ProblemDetail`, cấu trúc lỗi của Boot hoặc output từ custom exception handler; không suy từ status 400 rằng sẽ có JSON liệt kê mọi field. Bean Validation cũng **không cam kết thứ tự các lỗi**.

Mã demo không xử lý password thật. Trong hệ thống production không lưu hoặc log plain-text password; phải hash bằng cơ chế an toàn thích hợp (ví dụ password encoder trong hệ thống xác thực) và áp dụng chính sách bảo mật nhất quán.

## 8. Cascade validation — kiểm tra object lồng nhau

Một DTO lồng nhau có constraint trên field **chỉ được kiểm tra khi validation đi vào object đó**. `@Valid` làm nhiệm vụ cascade:

```java
record Address(@NotBlank String city) {}

record OrderRequest(
        @NotBlank String reference,
        @NotNull @Valid Address shippingAddress) {
}
```

- `@NotNull` kiểm tra `shippingAddress` hiện diện.
- `@Valid` đi tiếp vào `Address` nếu object có giá trị, nhờ đó kiểm tra `city`.
- Nếu bỏ `@Valid` thì kiểm tra `@NotNull` ở cha **không tự kiểm tra** `city` của object con.
- Nếu bỏ `@NotNull` thì `shippingAddress=null` thường được bỏ qua bởi cascade `@Valid`.
- Khi validation group được yêu cầu, các group đó cũng được xét khi cascade; một constraint con chỉ ở `Default` sẽ không tự chạy nếu phía cha chỉ chọn `Create` (trừ khi có group inheritance/conversion/sequence liên quan).

Với container trong Bean Validation 2.0+/Jakarta Validation:

```java
record BulkOrder(
        @NotNull
        @Size(min = 1)
        java.util.List<@Valid OrderRequest> orders) {
}
```

Các phần tử `OrderRequest` không-null được cascade. Nếu **không được phép chứa phần tử null**, đặt constraint thích hợp trên phần tử:

```java
java.util.List<@NotNull @Valid OrderRequest> orders
```

Ở cả hai đoạn trên, đây là **khai báo DTO minh họa**, không kèm endpoint. Hành vi validation container element phụ thuộc provider và metadata hợp lệ; phải có một điểm gọi validator trên `BulkOrder`.

### `@ConvertGroup` khi group ngoài và group trong không tương ứng

Giả sử khi tạo `Order`, bạn cần validate địa chỉ ở nhóm `AddressChecks`, dù bên ngoài đang gọi group `Create`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;

record OrderPayload(
        @Valid
        @ConvertGroup(from = Create.class, to = AddressChecks.class)
        AddressPayload destination) {
}

interface AddressChecks {}

record AddressPayload(
        @NotBlank(groups = AddressChecks.class) String city) {
}
```

Khi request chọn `Create.class`, cascade trên `destination` chuyển nhóm sang `AddressChecks.class`. `@ConvertGroup` **chỉ có ý nghĩa trên cascade có `@Valid`**; nó không có tác dụng tự động cho mọi field của DTO cha và không làm group cha thay đổi.

Phần này có tên interface/record đơn giản để minh họa cơ chế; nếu đặt cùng project với các ví dụ khác có tên type trùng, cần đổi tên hoặc tách package.

## 9. `@GroupSequence` — thứ tự thực hiện nhóm

Khi truyền nhiều nhóm cho `@Validated({A.class, B.class})`, Jakarta Bean Validation **không đảm bảo** `A` được kiểm tra trước `B`. Điều này quan trọng nếu một nhóm kiểm tra điều kiện cơ bản còn nhóm sau kiểm tra logic nặng hơn.

Khai báo sequence:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface OrderedChecks {}
```

Khi yêu cầu `OrderedChecks.class`, validator:

1. Kiểm tra constraints nhóm `Default` trước.
2. Nếu có vi phạm ở `Default`, **không chạy** nhóm `ExpensiveChecks`.
3. Nếu `Default` đạt, mới kiểm tra nhóm `ExpensiveChecks`.

Ví dụ sử dụng ở controller dưới dạng fragment:

```java
@PostMapping("/verify")
public void verify(
        @Validated(OrderedChecks.class) @RequestBody SomeDto body) {
}
```

`SomeDto` phải là DTO do ứng dụng định nghĩa có constraints thuộc các nhóm liên quan; đoạn trên là fragment, không phải một ví dụ chạy riêng. Đừng dùng `@GroupSequence` chỉ để sắp thứ tự **field errors** trả về client; mục đích là thứ tự **đánh giá nhóm** và dừng sớm giữa nhóm.

**Không nhầm hai cách dùng sequence:**

- `@GroupSequence` trên **interface nhóm** (như `OrderedChecks`) tạo nhóm tổng hợp có thứ tự.
- `@GroupSequence` trên **class DTO** có thể **định nghĩa lại `Default` cho class đó**. Khi định nghĩa lại, sequence phải chứa **chính class DTO** thay cho `Default.class` trong danh sách ở cấp class; cấu hình sai có thể ném `GroupDefinitionException`. Việc redefining Default là cục bộ với class, không mặc định truyền nguyên cách định nghĩa lại sang object con.

Để tránh phức tạp không cần thiết, hãy bắt đầu với `Default` và một số group marker rõ ràng. Dùng sequence chỉ khi việc kiểm tra theo giai đoạn có ý nghĩa.

## 10. `BindingResult` và xử lý lỗi ngay trong controller

Không phải endpoint nào cũng nên ném exception ngay khi DTO vi phạm. Với luồng form-render (MVC truyền thống), controller có thể cần giữ input và trả lỗi lên view:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "register-form";
    }

    return "redirect:/registered";
}
```

Trong đó `RegisterForm` là JavaBean đã khai báo constraints và template view `register-form` tồn tại. Đây là **fragment controller sử dụng view rendering**, không phải code độc lập trong ứng dụng REST mẫu ở phần 6.

Các lưu ý chính:

- `BindingResult` hoặc `Errors` phải đặt **ngay sau tham số được validate** mà nó đại diện.
- Có thể đọc `bindingResult.getFieldErrors()`, `getGlobalErrors()`, `hasErrors()` để hiển thị lỗi phù hợp.
- Khi không có `BindingResult`, lỗi validation đầu vào thường được Spring chuyển thành exception và HTTP 400 theo error handling mặc định.
- Với `@RequestBody`, cũng có thể đặt `BindingResult` ngay sau DTO để xử lý theo cách của ứng dụng; tuy nhiên với API REST, nhiều đội chọn central error handler cho response đồng nhất.
- Các lỗi parse JSON hoặc không convert được type thường xảy ra **trước validation**, nên không phải lúc nào cũng nằm trong `BindingResult`. Ví dụ body malformed có thể gây `HttpMessageNotReadableException`.
- Với **method validation** khi có constraint trực tiếp trên tham số controller, Spring MVC 6.1+ có quy tắc phối hợp `Errors`/`BindingResult`: method chỉ được gọi nếu **mọi lỗi validation đều nằm ở các tham số có `Errors` ngay sau chúng**; nếu tham số khác cũng lỗi, `HandlerMethodValidationException` được ném.

## 11. Validation đầu vào DTO và method validation trong Spring MVC 6.1+

Spring MVC có hai đường đi khác nhau, cần nhận biết để cấu hình xử lý lỗi đúng.

### Đường 1 — Kiểm tra argument kiểu DTO

Ví dụ:

```java
@PostMapping("/users")
public void create(@Valid @RequestBody UserPayload body) {
}
```

Nếu chỉ có việc validate object argument theo cơ chế riêng của `@RequestBody`/`@ModelAttribute`, không có constraint trực tiếp đòi hỏi method validation, Spring thường ném **`MethodArgumentNotValidException`** khi input không hợp lệ và không có `BindingResult` ngay sau.

### Đường 2 — Kiểm tra constraint trực tiếp trên tham số/giá trị trả về

Ví dụ:

```java
@GetMapping("/page")
public int page(@RequestParam @Min(1) int number) {
    return number;
}
```

`@Min(1)` là constraint trực tiếp trên tham số method. Từ **Spring Framework 6.1**, Spring MVC có **built-in method validation** để validate những constraint dạng này; khi có lỗi, thường ném **`HandlerMethodValidationException`**. Ràng buộc trực tiếp như `@NotNull` trên tham số method (kể cả tham số có `@Valid`) có thể khiến toàn bộ handler phải đi qua method validation, bao gồm phần validate DTO.

**`@Valid` tự nó không phải constraint** nên chỉ thêm `@Valid` trên DTO không tự ép method validation. Điều này khác với `@NotNull`, `@Min`, `@Size` đặt trực tiếp trên tham số method.

### Tại sao không đặt `@Validated` cấp class trên controller mới?

Spring Framework 6.1 bổ sung built-in method validation cho handler MVC. Nếu controller được đánh dấu **`@Validated` ở cấp class**, method validation có thể diễn ra qua **AOP proxy** thay vì cơ chế native MVC. Để tận dụng API lỗi `HandlerMethodValidationException` và integration được Spring khuyến nghị, **bỏ `@Validated` ở cấp class controller** khi chuyển sang cách mới; vẫn đặt `@Validated(Group.class)` trên tham số DTO để chọn group.

Với **service bean**, `@Validated` cấp class vẫn là cách phổ biến để bật Spring AOP method validation qua `MethodValidationPostProcessor`, miễn ứng dụng có proxy/validator phù hợp. Những cơ chế proxy chịu ảnh hưởng của self-invocation, public method/proxy type và tổ hợp annotation; không suy ra rằng `new Service()` hoặc gọi từ cùng bean luôn đi qua AOP.

### Khác nhau giữa các mốc phiên bản

| Nền tảng | Điều cần nhớ |
| --- | --- |
| Spring 5.x / Boot 2.x | Thường dùng namespace `javax.validation`; MVC có validation object argument, còn method validation thường cần cơ chế AOP riêng. |
| Spring 6.0 / Boot 3.0–3.1 | Chuyển sang `jakarta.validation`; chưa có cơ chế method validation native mới của Spring MVC 6.1. |
| Spring 6.1+ / Boot 3.2+ | Spring MVC hỗ trợ native method validation với `HandlerMethodValidationException`; tránh class-level `@Validated` trên controller nếu muốn hành vi native. |

Bảng nêu **baseline thường gặp**. Luôn kiểm tra phiên bản `spring-webmvc` và provider validation thực tế trong dependency tree, đặc biệt khi dự án override BOM hoặc dùng dependency riêng.

## 12. Xử lý exception và thiết kế lỗi HTTP rõ ràng

Trong API REST, người dùng cần biết field nào vi phạm, nhưng response không nên lộ stack trace hoặc implementation detail.

Một handler mẫu cho lỗi DTO (`MethodArgumentNotValidException`):

```java
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, List<String>>> invalidBody(
            MethodArgumentNotValidException ex) {

        List<String> messages = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error ->
                        error.getField() + ": " + error.getDefaultMessage())
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of("errors", messages));
    }
}
```

Đoạn này là **class đầy đủ nhưng cần được đặt trong project Spring**, và chỉ minh họa một loại exception. Nếu đặt chung package với controller mẫu phần 6, nó sẽ thay đổi cấu trúc body lỗi thành object chứa `errors` (thứ tự danh sách vẫn không bảo đảm).

Với Spring MVC 6.1+, có thể xử lý `HandlerMethodValidationException` bằng `@ExceptionHandler` hoặc override phương thức tương ứng trong `ResponseEntityExceptionHandler`. Ví dụ fragment:

```java
@ExceptionHandler(HandlerMethodValidationException.class)
ResponseEntity<Map<String, Object>> invalidMethod(
        HandlerMethodValidationException ex) {

    List<String> messages = ex.getAllValidationResults().stream()
            .flatMap(result -> result.getResolvableErrors().stream())
            .map(error -> error.getDefaultMessage())
            .toList();

    return ResponseEntity.status(ex.getStatusCode())
            .body(Map.of("errors", messages));
}
```

Fragment này cần imports `org.springframework.web.method.annotation.HandlerMethodValidationException`, `java.util.List`, `java.util.Map`, `org.springframework.http.ResponseEntity` và được đặt **bên trong `@RestControllerAdvice`**. `HandlerMethodValidationException` có thể biểu diễn cả vi phạm tham số và **vi phạm giá trị trả về**; status thường là **400 cho input** và **500 cho lỗi return value**. Không hardcode 400 cho mọi trường hợp rồi vô tình che lỗi chương trình.

Trong hệ thống thực, bổ sung xử lý lỗi JSON sai cú pháp (`HttpMessageNotReadableException`), lỗi type conversion, business errors, lỗi nhóm/metadata validator và response format chuẩn (ví dụ RFC 9457 `ProblemDetail`), cùng correlation ID khi cần.

Thông điệp từ constraint có thể chứa nội dung do developer tạo; tránh đưa giá trị bí mật trong rejected values ra JSON/log. Với i18n, Spring cung cấp `MessageSource`/message codes và Bean Validation message interpolation để địa phương hóa thông báo.

## 13. Integration test có thể đặt vào dự án ví dụ

Tạo **`src/test/java/demo/validation/ValidationApplicationTests.java`**, dùng `spring-boot-starter-test` đã khai báo:

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createAcceptsDefaultAndCreateGroups() throws Exception {
        mvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"An",
                      "email":"an@example.com",
                      "password":"secret123",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("An"));
    }

    @Test
    void createRejectsInvalidDefaultAndCreateConstraints() throws Exception {
        mvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id":10,
                      "name":"",
                      "email":"invalid",
                      "password":"abc",
                      "address":{"city":""}
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void updateDoesNotRequireCreateOnlyPassword() throws Exception {
        mvc.perform(put("/api/users/7")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id":7,
                      "name":"An",
                      "email":"an@example.com",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void updateRequiresId() throws Exception {
        mvc.perform(put("/api/users/7")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"An",
                      "email":"an@example.com",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directMethodConstraintIsValidated() throws Exception {
        mvc.perform(get("/api/users/page").param("number", "0"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/users/page").param("number", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value(2));
    }
}
```

Chạy:

```bash
./gradlew test
```

Bộ test mong đợi **5 method pass** với baseline Boot 3.2+ Spring 6.1+, Jakarta provider đã bật và không có bảo mật/filter tùy chỉnh. Các assertions tập trung HTTP status/body xác định trong ví dụ, **không phụ thuộc thứ tự constraint violations hoặc error format mặc định**.

Để nâng chất lượng kiểm thử, thêm các case:

- Tạo mới thiếu `address`: 400 do `@NotNull`.
- `address.city=""`: 400 nhờ `@Valid` cascade.
- Tạo mới `id=7`: 400 bởi `Create`; cập nhật `id=null`: 400 bởi `Update`.
- Bỏ `@Valid` ở `address` trong một nhánh test minh họa: chứng minh lỗi city không còn được phát hiện bởi cascade (nhưng `@NotNull` ở address vẫn chạy).
- Đặt `@Validated(Create.class)` thay cho `@Validated({Default.class,Create.class})` trong một test độc lập: thấy rõ ràng buộc chỉ thuộc `Default` bị bỏ qua.
- Đưa `@NotNull` trực tiếp lên tham số method cần kiểm tra: xác nhận khi nào lỗi đi qua `HandlerMethodValidationException`.
- Nếu có `@ControllerAdvice` custom, assert schema body, message codes, localization và trạng thái đúng cho lỗi return value.

## 14. Tự validate trong service và không phụ thuộc vào HTTP

Bean Validation không dành riêng cho controller. Bạn có thể gọi `jakarta.validation.Validator` tại ranh giới dữ liệu phù hợp:

```java
package demo.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.util.Set;

public class StandaloneValidation {
    record Invoice(@NotBlank String customer, @Positive int total) {}

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Invoice invoice = new Invoice("", -2);
            Set<ConstraintViolation<Invoice>> errors =
                    validator.validate(invoice);

            System.out.println(errors.size());
        }
    }
}
```

Đây là **một tệp Java 17+ độc lập về Spring MVC**, nhưng để biên dịch/chạy cần classpath có `jakarta.validation-api` và implementation (ví dụ Hibernate Validator) cùng các dependency runtime của provider. Tạo tệp `src/main/java/demo/validation/StandaloneValidation.java` trong dự án Boot ở phần 6 (đã có starter validation); có thể chạy bằng IDE với classpath Gradle hoặc task JavaExec thích hợp.

Trong trường hợp hai constraint `@NotBlank` và `@Positive` của `Invoice("", -2)` cùng được đánh giá bởi provider tương thích, stdout là:

```text
2
```

Không dựa vào thứ tự phần tử của `Set<ConstraintViolation<Invoice>>` để xây response. Nếu cần validate group:

```java
validator.validate(invoice, Default.class, Create.class);
```

Lời gọi này là fragment nằm trong scope có `validator`, `invoice` và hai type `Default`/`Create` phù hợp. `Validator#validate(object)` mặc định chọn `Default`; truyền nhóm chỉ thực hiện những group được nêu và kế thừa/sequence/conversion liên quan.

Đối với **method validation trên service**, có thể sử dụng `@Validated` cấp class và `@NotNull`, `@Min` trực tiếp trên tham số method trong một bean do Spring quản lý. Hãy phân biệt với `Validator#validate(bean)` (kiểm tra constraint trên trạng thái object); validator chuẩn còn có API `ExecutableValidator` để kiểm tra tham số/return value của method nếu cần thao tác chủ động.

## 15. Các lỗi phổ biến cần tránh

1. **Thiếu implementation**: chỉ thêm `jakarta.validation-api` rồi chờ `@Valid` tự chạy; với Boot dùng `spring-boot-starter-validation`.
2. **Import sai namespace**: Boot 3.x sử dụng `jakarta.validation.*`, không phải `javax.validation.*` từ thế hệ Boot 2.x.
3. **Nhầm `@Valid` với constraint bắt buộc**: `@Valid` chỉ trigger/cascade; object con `null` cần `@NotNull` nếu bắt buộc.
4. **Nhầm `@Validated(Create.class)` tự áp dụng `Default`**: group khác không tự kéo `Default` vào.
5. **Gắn annotation constraint vào DTO nhưng quên kích hoạt validation ở boundary**: body đã deserialize không có nghĩa đã được validate.
6. **Dùng `@NotNull` cho chuỗi bắt buộc**: `""` vẫn vượt qua; cân nhắc `@NotBlank`.
7. **Quên `@Valid` trên field lồng nhau / collection elements**: child constraint không chạy như mong đợi.
8. **Đặt `BindingResult` sai vị trí**: Spring yêu cầu theo ngay sau tham số được validate tương ứng.
9. **Xử lý mọi lỗi thành một exception**: Spring MVC 6.1+ có cả `MethodArgumentNotValidException` và `HandlerMethodValidationException`; parse/type error còn có exception khác.
10. **Áp dụng `@Validated` ở class-level controller rồi mong native MVC method validation**: class-level có thể chuyển sang đường AOP, làm exception khác kỳ vọng.
11. **Tưởng group bảo vệ security/business rule**: role, owner, uniqueness, concurrency vẫn phải kiểm tra ở layer đúng.
12. **Tin rằng list lỗi có thứ tự cố định**: mặc định không có cam kết thứ tự và lỗi đầu tiên; nếu thứ tự nhóm cần thiết dùng `@GroupSequence`.
13. **Để DB constraint phụ thuộc vào validation đầu vào**: phải bảo vệ cả phía persistence và xử lý race condition.
14. **Trả giá trị rejectedValue nhạy cảm cho client**: thận trọng với password/token/log.
15. **Dùng chung một DTO cho quá nhiều hành động**: khi groups chằng chịt, DTO riêng theo use case thường rõ và an toàn hơn.

## 16. Chọn `@Valid`, `@Validated` hay DTO riêng?

| Tình huống | Gợi ý |
| --- | --- |
| Một DTO và bộ quy tắc chung duy nhất | `@Valid @RequestBody Dto` |
| Có ràng buộc khác nhau giữa create/update nhưng cấu trúc gần giống | `@Validated({Default.class,Create.class})` hoặc `{Default.class,Update.class}` |
| Object chứa object/list con có constraint | Thêm `@Valid` tại vị trí cascade; `@NotNull` nếu bắt buộc |
| Group phải chạy theo giai đoạn | `@GroupSequence` trên group interface, test tình huống dừng sớm |
| Input có hình dạng, quyền thay đổi, field bắt buộc rất khác nhau | Tạo DTO riêng như `CreateUserRequest` và `UpdateUserRequest` |
| Kiểm tra tham số scalar trực tiếp trên controller, Framework 6.1+ | Constraint `@Min`, `@NotBlank`... + native MVC method validation |
| Kiểm tra method của service bean | `@Validated` cấp class, cấu hình AOP method validation phù hợp |
| Quy tắc phụ thuộc DB, người dùng đã xác thực hoặc trạng thái hệ thống | Validation nghiệp vụ trong service/domain + transaction/database constraints |

Tư duy khi áp dụng: chọn **hợp đồng input của endpoint** trước; đặt constraints ngay tại DTO thích hợp; chọn group có chủ ý; bảo đảm nested validation; xử lý lỗi nhất quán và viết test cho cả đường thành công lẫn thất bại.

## 17. Bài tập tự kiểm tra

1. Tạo `OrderRequest` có `quantity` lớn hơn 0, `email` bắt buộc và `shippingAddress.city` không trống. Gọi `@Valid` trên body: trường hợp thiếu `shippingAddress` có bị chặn nếu chỉ đặt `@Valid` trên field không? Vì sao?
2. Thêm group `Publish` để yêu cầu `description` ít nhất 30 ký tự khi phát hành. Vì sao `@Validated(Publish.class)` có thể bỏ qua `@NotBlank` mặc định trên `title`? Hãy sửa annotation tham số.
3. Xây dựng sequence `Default` rồi `Publish`. Nếu title trống, nhóm `Publish` có chạy không? Viết test chứng minh.
4. Với `GET /products?page=0` và `@Min(1)` trên tham số controller ở Framework 6.1+, exception nào có thể được ném? Nếu đồng thời thêm `@Valid @RequestBody` thì exception handling cần lưu ý gì?
5. Viết test cập nhật user: password không truyền vẫn hợp lệ, email bỏ trống phải lỗi, id body khác path phải lỗi nghiệp vụ. Phân biệt ba loại quy tắc đó.
6. Trong method controller có `BindingResult` ngay sau DTO nhưng còn một tham số `@RequestParam @Min(1)` khác bị lỗi, controller có nhất thiết được gọi không? Hãy giải thích native method validation.
7. Viết một `@RestControllerAdvice` trả mã lỗi ổn định và không làm lộ rejected password cho cả hai exception validation phổ biến.

## 18. Tài liệu chính thức

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): phân biệt argument validation và native method validation, `@Valid`, `@Validated`, `BindingResult`, exception.
- [Spring Framework — Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/annotation/Validated.html): nhóm validation và AOP method validation.
- [Spring Framework — Spring MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): tham số controller được hỗ trợ.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): mốc bổ sung built-in MVC method validation.
- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): ràng buộc chuẩn, `Default`, nhóm, cascade, `@GroupSequence`, `@ConvertGroup`.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): autoconfiguration và method validation cho Spring bean.
