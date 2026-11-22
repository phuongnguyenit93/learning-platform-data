# Thiết kế DTO hoặc form object theo một tác vụ cụ thể trong Spring Framework

## 1. Vì sao đối tượng đầu vào phải bám theo tác vụ?

Giả sử ứng dụng có tác vụ **đăng ký tham dự một buổi workshop**. Người dùng chỉ cần nhập tên, email và số ghế. Hệ thống tự xác định mã đăng ký, đơn giá, tổng tiền và trạng thái. Nếu controller nhận thẳng một entity có cả `id`, `totalVnd`, `status` và các trường quản trị, dữ liệu HTTP có thể vô tình hoặc cố ý ghi vào thuộc tính không dành cho người dùng.

**DTO đầu vào (request DTO) hoặc form object nên mô tả chính xác những thông tin mà một tác vụ được phép tiếp nhận**, không mô tả toàn bộ cấu trúc database.

- **DTO (Data Transfer Object)**: cấu trúc dữ liệu truyền qua ranh giới, ví dụ JSON request, form submission hoặc lời gọi service. Tên gọi DTO không bắt buộc dùng class có setter; Java `record` cũng là một DTO phù hợp.
- **Form object / command object**: đối tượng đại diện các trường của một biểu mẫu/nghiệp vụ người dùng thực hiện, thường dùng với Spring MVC `@ModelAttribute`. Một form object có thể là JavaBean với constructor rỗng và getter/setter hoặc kiểu bất biến dùng constructor binding.
- **Domain entity / persistence entity**: biểu diễn dữ liệu và vòng đời nghiệp vụ của hệ thống. Entity thường có thêm ID, trạng thái, thông tin kiểm toán, quan hệ JPA và bất biến nội bộ.
- **Response DTO**: hợp đồng trả dữ liệu cho client; có thể khác cả request DTO lẫn entity.

Một tác vụ khác nhau cần một hợp đồng khác nhau, kể cả khi cùng thao tác trên một entity. Ví dụ `CreateRegistrationForm`, `ChangeRegistrationEmailRequest` và `CancelRegistrationRequest` không nên dùng chung một `RegistrationDto` chứa mọi trường với nhiều giá trị nullable và quyền ghi mơ hồ.

## 2. Bắt đầu từ hợp đồng của một tác vụ cụ thể

**User story:** Người tham dự gửi biểu mẫu đăng ký workshop, chọn từ 1 đến 5 ghế. Hệ thống ghi nhận đăng ký ở trạng thái `PENDING` và tính tiền với đơn giá minh họa 250.000 VND/ghế.

| Trường | Nguồn | Kiểu Java gợi ý | Quy tắc |
| --- | --- | --- | --- |
| `attendeeName` | Người dùng | `String` | Bắt buộc, không chỉ chứa khoảng trắng, tối đa 80 ký tự |
| `email` | Người dùng | `String` | Bắt buộc, đúng cú pháp email, tối đa 120 ký tự |
| `seats` | Người dùng | `Integer` | Bắt buộc, từ 1 đến 5 |
| `registrationId` | Máy chủ | Không có trong input form | Tạo khi lưu vào hệ thống thực |
| `pricePerSeatVnd` | Máy chủ | Không có trong input form | Tính/tra giá theo chính sách máy chủ |
| `totalVnd` | Máy chủ | Không có trong input form | Tính từ số ghế và đơn giá tin cậy |
| `status` | Máy chủ | Không có trong input form | Trạng thái ban đầu do nghiệp vụ quy định |
| `createdAt`, `createdBy` | Máy chủ | Không có trong input form | Lấy từ đồng hồ hệ thống và danh tính đã xác thực |

Một request form hợp lệ có nội dung logic tương đương:

```text
attendeeName=Lan Nguyen
email=lan@example.com
seats=2
```

Những trường như `status=APPROVED` hoặc `totalVnd=0` **không thuộc hợp đồng đầu vào**, dù client vẫn có thể tự gửi chúng qua HTTP. Việc ẩn một ô HTML không tạo ra ranh giới bảo mật; server phải chủ động giới hạn những thuộc tính có thể được bind và luôn tính/tra các dữ liệu nhạy cảm ở phía server.

**Kết quả mong đợi** của ứng dụng minh họa là xác nhận tên, số ghế, số tiền và trạng thái. Ví dụ không trả email để tránh lộ thêm dữ liệu cá nhân không cần thiết cho response.

## 3. Từ request đến nghiệp vụ: các lớp chịu trách nhiệm gì?

```text
POST /registrations (application/x-www-form-urlencoded)
          |
          v
CreateRegistrationForm
  - Chỉ có attendeeName, email, seats
  - @NotBlank, @Email, @NotNull, @Min, @Max, @Size
          |
          v
Spring MVC @ModelAttribute + WebDataBinder
  - Bind và convert kiểu dữ liệu
  - Chỉ chấp nhận allowedFields
          |
          v
@Valid + BindingResult
  - Bắt lỗi cấu trúc/định dạng của input
          |
          v
Controller ánh xạ rõ ràng từng trường
          |
          v
CreateRegistrationCommand
          |
          v
RegistrationService
  - Kiểm tra bất biến nghiệp vụ
  - Tự tính tổng tiền, trạng thái
          |
          v
RegistrationReceipt (response DTO)
```

Tách đối tượng theo ranh giới giúp thay đổi biểu mẫu mà không làm vỡ mô hình lưu trữ, tránh gửi dữ liệu nội bộ ra ngoài, và giảm nguy cơ **overposting / mass assignment**: client cố ghi các thuộc tính mà chức năng không cho phép chỉnh sửa.

Không phải mọi dự án đều cần thêm một class `Command` trung gian. Với tác vụ nhỏ, controller có thể ánh xạ trực tiếp các giá trị đã kiểm tra vào một phương thức service có tham số rõ ràng. Điều quan trọng là **không truyền một entity vừa bị bind trực tiếp vào thao tác lưu** và phải xác định dữ liệu nào do client quyết định, dữ liệu nào do server quyết định.

## 4. Ví dụ Spring Boot MVC chạy được: tạo đăng ký workshop

Ví dụ dùng **Java 17**, **Spring Boot 3.4.3** (Spring Framework 6), Maven, Bean Validation và endpoint nhận HTML form URL-encoded. Để tập trung vào DTO và binding, service trả về bản xác nhận tính toán tại chỗ, **chưa lưu database, chưa triển khai xác thực hay thanh toán**. Việc sinh ID và persist entity sẽ được bổ sung ở hệ thống thực.

Cấu trúc tệp:

```text
registration-demo/
├── pom.xml
└── src/main/java/demo/registration/
    ├── RegistrationDemoApplication.java
    ├── CreateRegistrationForm.java
    ├── CreateRegistrationCommand.java
    ├── RegistrationReceipt.java
    ├── RegistrationService.java
    └── RegistrationController.java
```

### 4.1. Khai báo dependency

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.3</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>registration-demo</artifactId>
    <version>1.0.0</version>

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
```

`spring-boot-starter-web` cung cấp Spring MVC và server nhúng; `spring-boot-starter-validation` cung cấp Bean Validation provider để các annotation như `@NotBlank`, `@Email` và `@Min` thực sự được kiểm tra. Với Spring Framework 6, dùng namespace `jakarta.validation` thay vì `javax.validation` của phiên bản cũ.

### 4.2. Điểm khởi động

**`src/main/java/demo/registration/RegistrationDemoApplication.java`**

```java
package demo.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationDemoApplication.class, args);
    }
}
```

### 4.3. Form object chỉ có ba trường được nhập

**`src/main/java/demo/registration/CreateRegistrationForm.java`**

```java
package demo.registration;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class CreateRegistrationForm {
    @NotBlank
    @Size(max = 80)
    private String attendeeName;

    @NotBlank
    @Email
    @Size(max = 120)
    private String email;

    @NotNull
    @Min(1)
    @Max(5)
    private Integer seats;

    public String getAttendeeName() {
        return attendeeName;
    }

    public void setAttendeeName(String attendeeName) {
        this.attendeeName = attendeeName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }
}
```

Đây là một JavaBean có constructor rỗng mặc định. Spring MVC có thể dùng setter để bind tham số form với tên trùng property: `attendeeName`, `email`, `seats`. `Integer` thay cho `int` để phân biệt **không gửi trường** (`null`, được `@NotNull` bắt) với **gửi giá trị 0** (được `@Min(1)` bắt). Với `seats=abc`, Spring không thể chuyển chuỗi thành `Integer` và ghi nhận lỗi chuyển kiểu trong quá trình binding.

Các annotation chỉ giải quyết lỗi cấu trúc/định dạng đầu vào. Chúng không xác minh workshop còn ghế, người dùng có quyền đặt hộ, hay giá hiện tại; các điều kiện đó thuộc service/domain và cần nguồn dữ liệu tin cậy.

### 4.4. Command và response tách khỏi form

**`src/main/java/demo/registration/CreateRegistrationCommand.java`**

```java
package demo.registration;

public record CreateRegistrationCommand(
        String attendeeName,
        String email,
        int seats) {
}
```

**`src/main/java/demo/registration/RegistrationReceipt.java`**

```java
package demo.registration;

public record RegistrationReceipt(
        String attendeeName,
        int seats,
        int totalVnd,
        String status) {
}
```

Java `record` phù hợp cho dữ liệu bất biến theo nghĩa các thành phần không thể gán lại sau khi khởi tạo. Đây không phải đối tượng JPA entity và không cần setters. `CreateRegistrationCommand` mô tả đầu vào service đã được ánh xạ từ biểu mẫu; `RegistrationReceipt` mô tả đúng những trường trả cho client.

### 4.5. Service giữ quyền quyết định giá và trạng thái

**`src/main/java/demo/registration/RegistrationService.java`**

```java
package demo.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private static final int PRICE_PER_SEAT_VND = 250_000;

    public RegistrationReceipt create(CreateRegistrationCommand command) {
        if (command.seats() < 1 || command.seats() > 5) {
            throw new IllegalArgumentException("seats must be between 1 and 5");
        }

        int total = command.seats() * PRICE_PER_SEAT_VND;
        return new RegistrationReceipt(
                command.attendeeName(),
                command.seats(),
                total,
                "PENDING");
    }
}
```

Giá và trạng thái không được đọc từ HTTP request; vì vậy client không thể thay chúng bằng cách tự thêm trường vào form. Kiểm tra số ghế trong service thể hiện một bất biến nghiệp vụ tối thiểu ngay cả khi service được gọi từ một nguồn khác không đi qua controller. Trong hệ thống thật, giá có thể là `BigDecimal` theo tiền tệ và được tra từ cấu hình hoặc database; demo dùng VND nguyên và `int` vì miền giá trị đang rất nhỏ.

### 4.6. Controller: binding, validation, allowlist và ánh xạ rõ ràng

**`src/main/java/demo/registration/RegistrationController.java`**

```java
package demo.registration;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {
    private final RegistrationService service;

    public RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @InitBinder("registrationForm")
    void restrictFormFields(WebDataBinder binder) {
        binder.setAllowedFields("attendeeName", "email", "seats");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("registrationForm") CreateRegistrationForm form,
            BindingResult bindingResult) {

        if (bindingResult.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "Unexpected form fields"));
        }

        if (bindingResult.hasErrors()) {
            List<Map<String, String>> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "Invalid value")))
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("errors", errors));
        }

        CreateRegistrationCommand command = new CreateRegistrationCommand(
                form.getAttendeeName().strip(),
                form.getEmail().strip(),
                form.getSeats());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(command));
    }
}
```

Các quyết định quan trọng trong controller:

1. `@ModelAttribute("registrationForm")` yêu cầu Spring tạo/bind đối tượng từ request parameters, phù hợp với `application/x-www-form-urlencoded`; tên `registrationForm` cũng được dùng bởi `@InitBinder`.
2. `@InitBinder("registrationForm")` giới hạn **setter/property binding** vào đúng ba trường. `getSuppressedFields()` cho biết có tên field nào bị loại khỏi binding; endpoint minh họa chủ động trả `400` nếu client gửi thêm field ngoài hợp đồng.
3. `@Valid` chạy Bean Validation sau binding. `BindingResult` **phải đứng ngay sau** tham số form để controller xử lý lỗi bind và lỗi validation. Nếu bỏ `BindingResult`, Spring MVC thường báo lỗi qua ngoại lệ xử lý request.
4. Controller tự ánh xạ từng trường vào `CreateRegistrationCommand`. Tránh cơ chế copy toàn bộ thuộc tính giữa request object và entity nếu việc đó có thể làm lọt thuộc tính không được phép.
5. `.strip()` loại bỏ khoảng trắng ở hai đầu sau khi dữ liệu đã qua validation; không tự động biến dữ liệu không hợp lệ thành hợp lệ. Trên hệ thống thực có thể chuẩn hóa trước validation theo một chính sách rõ ràng, đồng thời tránh âm thầm thay đổi ý nghĩa email của người dùng.
6. Response là một DTO riêng. Không trả trực tiếp entity chứa dữ liệu nội bộ hay quan hệ lazy-loaded.

**Lưu ý:** Nếu request có khóa thừa mà không có allowlist, đối tượng form ở ví dụ này vẫn không có setter cho `status`/`totalVnd`, nhưng việc khai báo allowed fields giúp ý định thiết kế minh bạch và tránh phát sinh quyền ghi ngoài ý muốn khi class được mở rộng. Với các dạng constructor binding, phải đánh giá riêng các tham số constructor; `setAllowedFields` chủ yếu bảo vệ property binding.

## 5. Chạy và đối chiếu đầu ra

Trong thư mục `registration-demo`, có JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Ứng dụng lắng nghe cổng `8080` theo cấu hình mặc định, nếu cổng này chưa bị ứng dụng khác sử dụng. Trong terminal khác (dùng `curl.exe` trên Windows PowerShell hoặc `curl` trên Bash), gửi dữ liệu form hợp lệ:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=2"
```

**HTTP status:** `201 Created`. **JSON body:**

```json
{
  "attendeeName": "Lan Nguyen",
  "seats": 2,
  "totalVnd": 500000,
  "status": "PENDING"
}
```

Đây là kết quả xác định từ `2 × 250000 = 500000`, không phụ thuộc giá do client gửi. Thứ tự thuộc tính JSON/headers thực tế có thể khác tùy bộ serializer, nhưng nội dung giá trị trên là điều cần đối chiếu.

Thử gửi số ghế quá giới hạn:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=9"
```

Kết quả là **HTTP 400** với `errors` chứa lỗi trường `seats` (ràng buộc `@Max(5)`); nội dung thông báo chi tiết có thể thay đổi theo locale và Bean Validation provider.

Thử *overposting*:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=2" --data-urlencode "status=APPROVED"
```

Kết quả là **HTTP 400** do `status` không nằm trong `allowedFields`, body:

```json
{"error":"Unexpected form fields"}
```

Thử `seats=abc` sẽ tạo lỗi *type mismatch*; thử thiếu `email` sẽ tạo lỗi `@NotBlank`. Cả hai trường hợp phải trả `400` và không gọi service để tạo xác nhận.

Chú ý: demo trả xác nhận trong bộ nhớ, không lưu đăng ký. Khi nối database, service cần kiểm tra số ghế còn lại và ghi nhận dữ liệu theo transaction phù hợp; không suy ra từ JSON `201` ở demo rằng đã có bản ghi bền vững.

## 6. Nếu đầu vào là JSON thì thiết kế khác ở điểm nào?

Tác vụ vẫn là **tạo đăng ký**, nhưng transport khác:

| HTML form | JSON API |
| --- | --- |
| `Content-Type: application/x-www-form-urlencoded` | `Content-Type: application/json` |
| `@ModelAttribute` + `WebDataBinder` | `@RequestBody` + `HttpMessageConverter` (thường Jackson) |
| JavaBean có setters hoặc constructor-bound object | `record`/class được JSON deserializer hỗ trợ |
| `BindingResult` có thể đứng ngay sau tham số form | `@Valid` cũng dùng được trên `@RequestBody`; xử lý lỗi bằng exception handler hoặc `Errors` phù hợp |
| `@InitBinder.setAllowedFields` giới hạn property binding | Không tự động giới hạn JSON deserialization; dùng request DTO chặt chẽ và chính sách Jackson |

Ví dụ **chữ ký minh họa, không phải một controller độc lập**:

```java
public record CreateRegistrationJson(
        @jakarta.validation.constraints.NotBlank String attendeeName,
        @jakarta.validation.constraints.Email
        @jakarta.validation.constraints.NotBlank String email,
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Min(1)
        @jakarta.validation.constraints.Max(5) Integer seats) {
}

@PostMapping(path = "/registrations-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<RegistrationReceipt> createJson(
        @Valid @RequestBody CreateRegistrationJson request) {
    var command = new CreateRegistrationCommand(
            request.attendeeName(),
            request.email(),
            request.seats());
    return ResponseEntity.status(HttpStatus.CREATED)
            .body(service.create(command));
}
```

Đoạn này được chèn vào một controller có `service` và import phù hợp. Nó minh họa record bất biến cho request JSON. Nếu có lỗi validation mà không có `Errors`/`BindingResult` đi kèm, Spring MVC có thể trả `400` qua cơ chế xử lý ngoại lệ mặc định. Tên ngoại lệ có thể khác nếu endpoint còn có ràng buộc yêu cầu method validation.

Nếu muốn **từ chối khóa JSON không có trong DTO**, cần cấu hình rõ chính sách cho unknown properties (ví dụ Jackson `FAIL_ON_UNKNOWN_PROPERTIES` tại phạm vi thích hợp). Chỉ việc DTO thiếu trường `status` chưa bảo đảm server sẽ trả `400` khi client gửi trường đó: một JSON deserializer có thể bỏ qua thuộc tính lạ theo cấu hình. Điều bất biến là không chuyển các trường bị bỏ qua vào entity hoặc lệnh nghiệp vụ.

## 7. Nguyên tắc quyết định kiểu dữ liệu và ranh giới validation

### 7.1. Kiểu Java phù hợp với giá trị đầu vào

- Dùng `Integer` khi cần biểu diễn “chưa được gửi” bằng `null`; kết hợp `@NotNull` với `@Min`/`@Max`. Dùng `int` khi đầu vào chắc chắn có giá trị sau một bước khởi tạo có kiểm soát.
- Dùng `String` cho email, tên, mã có số 0 đầu hoặc định dạng cần giữ nguyên. Tránh xem email hoặc số điện thoại là một `long`.
- Dùng `LocalDate` cho ngày chỉ có ngày-tháng-năm, `Instant`/`OffsetDateTime` khi cần thời điểm; cấu hình `@DateTimeFormat`/`Formatter` cho HTML form nếu định dạng nhập không mặc định.
- Dùng `BigDecimal` cho tiền có đơn vị nhỏ lẻ và quy tắc làm tròn rõ ràng. Các số tiền, chiết khấu, quyền và trạng thái do server kiểm soát thường **không nên là input có thể ghi** của client.
- Với giá trị hữu hạn, có thể dùng `enum` nhưng cần xét phản hồi khi client gửi giá trị không được hỗ trợ và cơ chế tương thích API khi thêm trạng thái.

### 7.2. Phân biệt ba loại kiểm tra

1. **Binding/conversion:** có thể biến `"2"` thành `Integer` không? `"abc"` gây type mismatch trước khi có đối tượng kiểu số hợp lệ.
2. **Validation đầu vào:** `@NotBlank`, `@Size`, `@Email`, `@Min`, `@Max` xác định một đối tượng đầu vào có đạt hợp đồng cú pháp/cấu trúc không.
3. **Business validation/authorization:** workshop còn chỗ không, người gọi có quyền thay đổi đăng ký nào, giá hiện tại là bao nhiêu? Những kiểm tra này dùng trạng thái server và danh tính tin cậy, thường nằm ở service/domain.

Không nên dồn cả ba loại vào một DTO, và cũng không được coi `@Valid` là cơ chế phân quyền hoặc bảo đảm dữ liệu đã an toàn cho mọi nghiệp vụ.

### 7.3. DTO chứa cấu trúc lồng nhau

Nếu form có danh sách người tham dự, một thiết kế có thể dùng `List<AttendeeForm> attendees`, trong đó mỗi phần tử có ràng buộc riêng. Dùng `@Valid` trên trường lồng nhau để kích hoạt cascade validation và `@Size(max=...)` để giới hạn số phần tử. Với binding theo property path như `attendees[0].name`, phải giới hạn kích thước/cấp độ cấu trúc và cân nhắc `autoGrowCollectionLimit` để không tạo đồ thị đối tượng quá lớn từ dữ liệu người dùng gửi.

Chỉ thêm cấu trúc lồng nhau khi tác vụ thực sự yêu cầu; với ví dụ workshop chỉ nhập số ghế thì `int seats` đơn giản hơn nhiều so với tạo ra danh sách attendee giả định.

## 8. Thiết kế khác nhau cho Create, Update, PATCH và Cancel

| Tác vụ | Đối tượng đầu vào gợi ý | Ý nghĩa các trường |
| --- | --- | --- |
| Tạo đăng ký | `CreateRegistrationForm` | Tên, email, số ghế bắt buộc; không có ID/trạng thái |
| Đổi email liên hệ | `ChangeRegistrationEmailRequest` | Chỉ email mới; ID lấy từ đường dẫn hoặc ngữ cảnh và xác minh quyền |
| Điều chỉnh số ghế | `ChangeSeatCountRequest` | Chỉ số ghế mới, kiểm tra chỗ còn trống và điều kiện thay đổi |
| Hủy đăng ký | `CancelRegistrationRequest` | Lý do hủy (nếu cần); trạng thái hủy do service xác định |
| Cập nhật một phần | `PatchRegistrationRequest` hoặc mô hình patch chuyên biệt | Phải phân biệt trường vắng mặt với yêu cầu xóa trường |

**Không nên tái sử dụng DTO tạo mới cho PATCH.** Với nhiều deserializer, cả JSON thiếu trường và JSON gán `null` có thể cùng dẫn tới giá trị Java `null`. Nếu nghiệp vụ cần phân biệt “giữ nguyên” với “xóa”, thiết kế phải mang **thông tin trường có xuất hiện hay không**: cấu trúc patch có flag, wrapper phù hợp, hoặc JSON Patch/Merge Patch với quy ước được định nghĩa rõ.

Đối với chỉnh sửa entity đang có, thường làm theo thứ tự: lấy ID từ route, xác thực người dùng, load entity, kiểm tra quyền, kiểm tra hợp đồng update, rồi áp dụng **các thuộc tính được phép chỉnh**. Không bind mọi request parameter vào entity JPA managed đang có và lập tức gọi `save`.

## 9. Khi nào nên dùng JavaBean, constructor binding hoặc record?

- **JavaBean có setter:** đơn giản cho HTML form truyền thống với `@ModelAttribute` và form validation. Nếu dùng property binding, khai báo tập `allowedFields` và không thêm setter cho trường bảo vệ.
- **Constructor binding / immutable DTO:** phù hợp khi các field được xác định rõ tại thời điểm tạo đối tượng, tránh setter công khai. Spring MVC hỗ trợ binding qua constructor, kể cả với nhiều kiểu dạng record, nhưng cần bảo đảm tên tham số được giữ trong bytecode và quy tắc chuyển kiểu phù hợp.
- **Record cho JSON request/response:** súc tích, bất biến ở mức tham chiếu field, phù hợp dữ liệu truyền nhận. Tuy nhiên record không tự ngăn các đối tượng thành phần có thể bị mutate và không phải lựa chọn bắt buộc cho mọi form.
- **Entity:** chứa logic và vòng đời nghiệp vụ; tránh dùng làm một request DTO có thể bị dữ liệu HTTP bind trực tiếp.

Spring MVC có hỗ trợ cấu hình **declarative binding** và constructor binding để giảm diện setter binding. Với các phiên bản/cấu hình còn dùng property binding, nên giới hạn trường được phép và kiểm tra request bất thường. Đừng dựa vào việc chỉ hiện vài input trên giao diện HTML: người gửi request có thể thêm bất kỳ parameter nào.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Dùng trực tiếp `RegistrationEntity` làm tham số `@ModelAttribute` | Dễ bind nhầm ID, status, price hoặc quan hệ JPA | Tạo form/DTO đúng tác vụ và ánh xạ field cụ thể |
| Dùng một DTO khổng lồ cho create/update/cancel | Nhiều trường nullable, quyền ghi không rõ | Tạo input riêng theo use case |
| Tin giá và trạng thái mà client gửi | Client có thể thao túng tiền/trạng thái | Server tự xác định, không đưa vào writable input |
| Chỉ dùng HTML `readonly`/`hidden` để bảo vệ trường | Request giả mạo vẫn gửi giá trị tùy ý | Kiểm soát ở server bằng DTO và binding whitelist |
| Dùng `int` cho field bắt buộc mà cần biết có được gửi không | Không phân biệt thiếu input với giá trị mặc định | `Integer` + `@NotNull` |
| Quên `@Valid` hoặc dependency validation provider | Annotation có thể không được kích hoạt | Bổ sung Bean Validation provider và kích hoạt validation |
| Đặt `BindingResult` xa khỏi tham số form | Controller không nhận lỗi theo đường dự kiến | Đặt ngay sau `@Valid @ModelAttribute` |
| Cho rằng `@InitBinder.setAllowedFields` xử lý luôn JSON | Sai cơ chế: JSON thường qua `HttpMessageConverter` | Dùng request DTO và cấu hình Jackson riêng |
| Copy mọi thuộc tính request vào entity bằng reflection | Ghi đè trường ngoài hợp đồng, khó kiểm soát | Map tường minh hoặc mapper giới hạn danh sách field |
| Xem validation đầu vào là kiểm tra quyền | Người dùng vẫn có thể sửa tài nguyên của người khác | Xác thực và kiểm tra quyền trong service |
| Đánh đồng thiếu trường trong PATCH với null | Xóa/ghi đè dữ liệu ngoài ý muốn | Thiết kế hợp đồng patch có presence semantics |
| Trả entity trực tiếp ra response | Lộ dữ liệu, mắc lỗi lazy loading và thay đổi API ngoài ý muốn | Sử dụng response DTO chuyên biệt |

## 11. Checklist khi thiết kế input object cho một tác vụ mới

1. Viết một câu mô tả **ai thực hiện hành động gì**, trên đối tượng nào; xác định tác vụ là tạo, sửa, hủy hay tìm kiếm.
2. Liệt kê từng trường client **được phép cung cấp**; tách các trường do server sinh/tính.
3. Chọn tên field, kiểu, giới hạn độ dài/miền giá trị, quy tắc bắt buộc và ý nghĩa khi vắng mặt.
4. Chọn cơ chế nhận phù hợp: HTML form qua `@ModelAttribute` hay JSON qua `@RequestBody`. Thiết kế allowlist hoặc constructor binding khi cần.
5. Dùng `@Valid` và xử lý lỗi chuyển kiểu, lỗi validation; không gọi service khi đầu vào sai.
6. Map tường minh sang command/domain operation; service xác minh quyền, trạng thái, tồn kho/số chỗ, giá và bất biến nghiệp vụ.
7. Trả response DTO chỉ chứa dữ liệu cần công bố; không tuần tự hóa entity một cách vô thức.
8. Thử request hợp lệ, thiếu trường, kiểu sai, vượt giới hạn, field không được phép, ID của người khác, request lặp, concurrency và sự khác nhau giữa missing/null của update.
9. Xem lại hợp đồng khi tác vụ đổi yêu cầu; không tự thêm field nhạy cảm vào một form object vốn được bind tự động.

**Ghi nhớ:** Một input DTO tốt trả lời được ba câu hỏi: *tác vụ là gì*, *client được phép gửi gì*, và *server sẽ kiểm soát những gì*. Form object là hợp đồng nhận dữ liệu; entity là mô hình nghiệp vụ; response DTO là hợp đồng trả dữ liệu. Tách rõ ba vai trò này giúp Spring Data Binding dễ kiểm soát, validation đúng lớp và giảm lỗi overposting.

## 12. Tài liệu chính thức

- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): cách bind model attribute, constructor/property binding, `BindingResult` và `@Valid`.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): các dạng binding, `allowedFields`, declarative binding và model design.
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình binder theo controller và model attribute.
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): JSON qua `HttpMessageConverter`.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): constraints, `jakarta.validation` và tích hợp validator.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validation của tham số controller và trường hợp method validation.