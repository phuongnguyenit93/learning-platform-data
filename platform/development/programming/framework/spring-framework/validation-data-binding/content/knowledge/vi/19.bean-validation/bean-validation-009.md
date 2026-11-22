# @Validated của Spring và lựa chọn nhóm kiểm tra (Validation Groups)

> **Module:** Spring Framework – validation-data-binding  
> **Chủ đề cha:** Bean Validation  
> **Trọng tâm:** Chọn đúng tập Jakarta Validation constraint tại từng điểm nhận dữ liệu bằng `org.springframework.validation.annotation.Validated`, đặc biệt khi CREATE/UPDATE có quy tắc khác nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Phân biệt `@Validated` của Spring với `@Valid` của Jakarta Validation.
2. Khai báo marker interface cho group và gắn `groups = ...` vào các constraint.
3. Hiểu chính xác `Default` group và cách kết hợp `Default.class` với `Create.class` hoặc `Update.class`.
4. Dùng `@Validated(...)` trên tham số `@RequestBody`, `@ModelAttribute` và dùng Jakarta `Validator.validate(bean, groups...)` để tự kiểm thử.
5. Nhận biết `@Validated` ở **tham số controller** với `@Validated` ở **class service** dành cho method validation qua AOP.
6. Phân biệt lỗi Bean Validation khi validate từng tham số với method validation tích hợp Spring MVC 6.1+.
7. Dùng group inheritance, `@GroupSequence`, `@ConvertGroup` khi thật sự cần, đồng thời tránh thiết kế group quá phức tạp.

## 2. Khi nào cần nhóm kiểm tra?

Một DTO có thể được dùng cho nhiều thao tác:

- **Tạo tài khoản:** `id` phải vắng mặt vì server sinh id; `username` bắt buộc.
- **Cập nhật tài khoản:** `id` phải có; `username` vẫn bắt buộc.
- **Quy tắc chung:** `email` phải không trống và đúng định dạng ở cả hai trường hợp.

Nếu đặt mọi constraint trong nhóm mặc định, không thể biểu diễn đầy đủ hai ngữ cảnh với cùng DTO mà không đổi quy tắc. **Validation groups** là cơ chế của Jakarta Validation để gắn mỗi constraint vào một hoặc nhiều nhóm và chỉ đánh giá các nhóm được yêu cầu.

Spring bổ sung `@Validated` để khai báo **nhóm cần chạy** ở các điểm Spring kích hoạt validation. Annotation không định nghĩa constraint mới. Nó truyền nhóm hoặc validation hints tới validator thích hợp.

```text
                 ĐỊNH NGHĨA TRÊN DTO
       @Null(groups = Create.class) Long id
       @NotNull(groups = Update.class) Long id
       @NotBlank(groups = {Create.class, Update.class}) String name
       @Email String email                  [Default]
                           |
                           v
                    TRIGGER VALIDATION
          @Validated(Create.class)      -> chỉ Create
          @Validated(Update.class)      -> chỉ Update
          @Validated({Default.class, Create.class})
                                       -> Default và Create
                           |
                           v
             Tập ConstraintViolation / BindingResult
```

Khai báo group cho **constraint**, chọn group khi **thực thi**; hai bước phải khớp nhau mới có tác dụng.

## 3. `@Valid` và `@Validated`: giống và khác

| Tiêu chí | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| --- | --- | --- |
| Nguồn | Chuẩn Jakarta Validation | Riêng Spring |
| Vai trò nền tảng | Đánh dấu cascade validation; Spring cũng nhận biết để kích hoạt validation trên đối số được hỗ trợ | Đánh dấu validation và chọn nhóm/hint trong các tích hợp Spring |
| Chọn nhóm trực tiếp? | Không có thuộc tính chọn nhóm | Có `value()` chứa các `Class<?>[]` |
| Ví dụ controller | `@Valid @RequestBody Input input` | `@Validated(Create.class) @RequestBody Input input` |
| Object lồng nhau | Thường dùng `@Valid` trên field/property để đi sâu | Dùng `@Valid` cho cascade; `@Validated` trên field không phải cơ chế group conversion chuẩn |
| Method validation ở service | `@Valid` có thể góp phần kiểm tra tham số/return theo cơ chế đã bật | `@Validated` trên class là điểm đánh dấu cho Spring AOP method validation |
| Dùng ngoài Spring | Có, qua Jakarta Validator | Không phải annotation Jakarta tiêu chuẩn |

Imports phải tường minh:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.Default;
import org.springframework.validation.annotation.Validated;
```

`@Validated` nhận một hoặc nhiều class nhóm:

```java
@Validated(Create.class)
@Validated({Default.class, Create.class})
```

Hai dòng này là **hai cách dùng độc lập**, không đặt đồng thời trên cùng một phần tử. Spring sử dụng `Class<?>[] value()` làm validation hints, thông thường các class đó là các group interface của Jakarta Validation. Không nhầm `@Validated` với annotation `@Valid` chỉ vì cùng xuất hiện trước DTO.

**Điểm tinh tế:** `@Valid` ở field lồng nhau là chỉ thị cascade theo ngữ cảnh group đang được validate; nó không có nghĩa “luôn validate mọi group của bean con”. Muốn đổi group khi cascade, sử dụng `@ConvertGroup` theo đặc tả.

## 4. Khai báo nhóm và constraint

### 4.1. Marker interface

Group thường là interface rỗng, dùng như định danh:

```java
public interface Create {}
public interface Update {}
```

Không cần implements các interface này trên DTO; các class nhóm chỉ xuất hiện trong `groups` và trong lệnh gọi validation. Có thể tổ chức thành một lớp chứa nested interfaces (`Checks.Create`, `Checks.Update`) để tránh xung đột tên.

### 4.2. DTO cho Create và Update

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public class AccountCommand {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    @NotBlank(groups = {Create.class, Update.class})
    private String username;

    @NotBlank
    @Email
    private String email;

    // constructor, getter và setter được bỏ qua trong ví dụ khai báo
}
```

Đoạn này minh họa metadata, chưa phải một file chạy độc lập.

- Khi validate **Create**: `id` phải null và `username` không được blank.
- Khi validate **Update**: `id` phải khác null và `username` không được blank.
- `email` có `@NotBlank` và `@Email` nhưng **không ghi `groups`**, nên hai constraint đó thuộc nhóm `jakarta.validation.groups.Default`.
- Một constraint có thể thuộc nhiều nhóm thông qua `groups = {A.class, B.class}`; không cần nhân đôi cùng một annotation ở hai field.

### 4.3. Bẫy quan trọng: `Default` không tự đi kèm group bạn chọn

Đối với `AccountCommand` ở trên:

```java
validator.validate(command);                   // Default
validator.validate(command, Create.class);     // Create
validator.validate(command, Update.class);     // Update
validator.validate(command, Default.class, Create.class);
```

Các lời gọi có ý nghĩa **khác nhau**. Khi bạn chủ động yêu cầu `Create.class`, constraint chỉ thuộc `Default` **không tự động chạy** (trừ khi có group inheritance hoặc sequence được định nghĩa phù hợp). Vậy nếu muốn kiểm tra email khi tạo, cần:

```java
@Validated({Default.class, Create.class})
```

Tương tự cho cập nhật:

```java
@Validated({Default.class, Update.class})
```

Không phải mọi constraint đều phải ghi thêm `Default.class` vào `groups`. Một lựa chọn khác là thiết kế group `Create` kế thừa `Default` hoặc dùng group sequence, nhưng cách chọn tường minh hai group tại endpoint thường dễ đọc và dễ kiểm thử.

### 4.4. Bảng dự đoán

Giả sử DTO có:
- `id == null`
- `username == ""`
- `email == "invalid-email"`

| Nhóm được validate | Constraint thất bại | Lý do |
| --- | --- | --- |
| `Default` | `email` | `@Email` sai, `@NotBlank` trên email vẫn đạt |
| `Create` | `username` | `id == null` đạt `@Null`; email Default không chạy |
| `Update` | `id`, `username` | `@NotNull` trên id sai; tên blank |
| `Default, Create` | `email`, `username` | Gộp hai tập constraint |
| `Default, Update` | `email`, `id`, `username` | Gộp hai tập constraint |

Cần nhớ `Validator.validate(...)` trả về **`Set<ConstraintViolation<T>>`**; thứ tự duyệt `Set` không được bảo đảm. Nếu trình bày nhiều lỗi theo thứ tự cố định, hãy sắp xếp khi hiển thị hoặc kiểm thử.

## 5. Ví dụ Java 17+ độc lập: kiểm chứng lựa chọn group

Để xác minh cơ chế group ngay từ Jakarta Validation mà không cần web server, tạo project Maven sau. Ví dụ có thể biên dịch trên Java 17+ với Hibernate Validator 8 (implementation của Jakarta Validation 3.0).

```text
group-check/
├── pom.xml
└── src/main/java/example/groups/GroupValidationCheck.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>group-check</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/groups/GroupValidationCheck.java`:

```java
package example.groups;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public final class GroupValidationCheck {

    public interface Create {}
    public interface Update {}

    public record Account(
            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @NotBlank(groups = {Create.class, Update.class})
            String username,

            @NotBlank
            @Email
            String email) {}

    private static String failingFields(
            Validator validator, Account account, Class<?>... groups) {
        return validator.validate(account, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Account bad = new Account(null, "", "invalid-email");

            System.out.println("default="
                    + failingFields(validator, bad));
            System.out.println("create="
                    + failingFields(validator, bad, Create.class));
            System.out.println("update="
                    + failingFields(validator, bad, Update.class));
            System.out.println("create+default="
                    + failingFields(validator, bad,
                                    Create.class, Default.class));
            System.out.println("update+default="
                    + failingFields(validator, bad,
                                    Update.class, Default.class));

            Account validUpdate =
                    new Account(12L, "Lan", "lan@example.com");
            System.out.println("valid-update-count="
                    + validator.validate(
                            validUpdate, Update.class, Default.class).size());
        }
    }
}
```

Chạy:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.groups.GroupValidationCheck
```

Các dòng **stdout do chương trình tạo** (không tính log của Maven/provider):

```text
default=email
create=username
update=id,username
create+default=email,username
update+default=email,id,username
valid-update-count=0
```

**Vì sao kết quả này chính xác?**

- Với `Default`, chỉ kiểm tra hai annotation của email; email không blank nhưng không đạt `@Email`.
- Với `Create`, `id == null` đạt `@Null`; `username == ""` thất bại `@NotBlank`.
- Với `Update`, id null thất bại `@NotNull` và tên blank thất bại `@NotBlank`.
- Khi yêu cầu nhiều group, tập vi phạm là tập các constraint tương ứng; sắp xếp chuỗi tên field khiến output có thứ tự ổn định.
- `Account` hợp lệ khi update có id dương/khác null, tên và email đúng; không có constraint nào thất bại.
- Từ khóa `try (ValidatorFactory ...)` đóng factory sau khi sử dụng; trong ứng dụng Spring, factory thường là bean được framework quản lý.

Đây là một chương trình **Jakarta Validation thuần**, chưa dùng `@Validated` của Spring. Nó cho thấy tại sao Spring cần chuyển đúng các class group tới provider.

## 6. `@Validated` ở Spring MVC: chọn nhóm cho HTTP request

Spring MVC thường kích hoạt Jakarta Validation sau khi tạo DTO từ request. Một phương thức có thể dùng một DTO với group Create, còn phương thức khác dùng cùng DTO với group Update.

### 6.1. Ví dụ Spring Boot 3 / Java 17 có thể chạy

Ví dụ cần một dự án Spring Boot 3.x có `spring-boot-starter-web` và `spring-boot-starter-validation`, cùng Java 17+. Mã sau là một file ứng dụng hoàn chỉnh. Bạn có thể dùng dự án Maven Boot đã tạo hoặc dùng cấu hình phụ thuộc sau:

```xml
<!-- Các dependency trong pom.xml của dự án Spring Boot,
     với phiên bản do Spring Boot parent/BOM quản lý -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Đoạn XML chỉ là **dependency fragment** (không phải pom độc lập). Đặt Java ở tệp `src/main/java/example/groupweb/GroupWebApplication.java`:

```java
package example.groupweb;

import java.util.Map;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.groups.Default;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GroupWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(GroupWebApplication.class, args);
    }

    public interface Create {}
    public interface Update {}

    public record AccountRequest(
            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @NotBlank(groups = {Create.class, Update.class})
            String username,

            @NotBlank
            @Email
            String email) {}

    @RestController
    @RequestMapping("/accounts")
    public static class AccountController {

        @PostMapping
        public Map<String, String> create(
                @Validated({Default.class, Create.class})
                @RequestBody AccountRequest request) {
            return Map.of("action", "created",
                          "username", request.username());
        }

        @PutMapping
        public Map<String, String> update(
                @Validated({Default.class, Update.class})
                @RequestBody AccountRequest request) {
            return Map.of("action", "updated",
                          "username", request.username());
        }
    }
}
```

Chạy ứng dụng theo hệ build đang dùng, ví dụ:

```bash
./mvnw spring-boot:run
```

hoặc:

```bash
./gradlew bootRun
```

Những lệnh trên áp dụng khi dự án có Maven/Gradle wrapper tương ứng; chúng không thể chạy từ một thư mục chỉ chứa file Java và dependency fragment.

Sau khi server chạy ở `localhost:8080`:

```bash
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"lan@example.com"}'
curl -i -X PUT http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":12,"username":"Lan","email":"lan@example.com"}'
```

Nếu ứng dụng không có security filter hay cấu hình HTTP đặc biệt, cả hai request hợp lệ trên trả **HTTP 200**. JSON body có cặp key `action`/`username`; thứ tự key không được cam kết.

Thử các request sai:

```bash
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":9,"username":"Lan","email":"lan@example.com"}'
curl -i -X PUT http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"lan@example.com"}'
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"bad-email"}'
```

Theo cấu hình Spring MVC thông thường, chúng bị từ chối với **HTTP 400**: lần lượt vi phạm `@Null` Create, `@NotNull` Update, `@Email` Default. Các request bị từ chối trước khi logic của controller chạy. Payload lỗi phụ thuộc Spring Boot, exception handler và cách cấu hình Problem Details nên **không giả định một JSON lỗi cố định**.

**Điểm đáng chú ý:** Bài này đặt `@Validated` trực tiếp trên **tham số DTO của từng endpoint**, vì hai endpoint chọn group khác nhau. Không đặt `@Validated(Create.class)` lên toàn bộ controller rồi kỳ vọng endpoint Update tự đổi sang group Update.

### 6.2. Vì sao `@RequestBody` vẫn cần provider?

`@RequestBody` được `HttpMessageConverter` (thường Jackson) deserialize JSON thành DTO. Sau đó Spring dùng validator để đánh giá các constraint của group đã chọn. Nếu thiếu `spring-boot-starter-validation` hoặc Bean Validation provider tương thích, annotation có thể không được thực thi như bạn mong đợi.

Trong Spring Framework 6+ / Boot 3+ dùng package `jakarta.validation`. `javax.validation` là namespace của các đời trước; kiểm tra dependency và import khi nâng cấp.

### 6.3. `@ModelAttribute` và `BindingResult`

Đối với request form, ví dụ đoạn **phương thức minh họa trong controller**:

```java
@PostMapping("/account-form")
public String submit(
        @Validated({Default.class, Create.class})
        @ModelAttribute AccountForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "invalid-form";
    }
    return "accepted";
}
```

Đoạn này yêu cầu `AccountForm` và các import đã được định nghĩa trong ứng dụng; không phải chương trình Java độc lập. `BindingResult` phải đứng **ngay sau tham số model** liên quan, để controller có thể xử lý cả lỗi data binding lẫn validation của đối tượng đó. Nếu không có `BindingResult` và validation thất bại, Spring MVC thường ném `MethodArgumentNotValidException`.

Khi chuyển đổi dữ liệu form thất bại trước validation (ví dụ chuỗi không thể chuyển thành số), đó là **lỗi binding**, vẫn có thể được chứa trong `BindingResult`. Đừng mặc định mọi lỗi từ form đều do constraint group.

## 7. Đặt `@Validated` trên service: Method Validation qua Spring AOP

Ngoài validate một DTO đầu vào controller, Spring còn hỗ trợ validate **tham số và return value của method** trên bean Spring.

Ví dụ service, với các class `Update` và dependency validation đã có:

```java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Update.class)
public class AccountService {

    public void changeStatus(
            @NotNull(groups = Update.class)
            @Positive(groups = Update.class)
            Long accountId) {
        // Xử lý nghiệp vụ với accountId hợp lệ.
    }
}
```

Đây là **mảnh code minh họa**; cần khai báo interface `Update` và lắp vào dự án Spring. `@Validated(Update.class)` ở **class** vừa là marker cho hạ tầng method validation của Spring, vừa chọn group Update mặc định cho method trong bean đó. Khi `MethodValidationPostProcessor` và provider được cấu hình, lời gọi `accountService.changeStatus(null)` **qua Spring proxy** có thể bị từ chối do `@NotNull`.

Cơ chế:

```text
Caller -> Spring proxy / MethodValidationInterceptor
       -> xác định method + groups
       -> Jakarta Validator / ExecutableValidator
       -> có violations? báo lỗi
       -> không lỗi? gọi implementation
```

Những giới hạn phải nhớ:

- Phải gọi **qua Spring-managed proxy**. Gọi `this.changeStatus(...)` bên trong cùng bean thường đi thẳng vào object nên có thể bỏ qua AOP validation; gọi `new AccountService()` cũng bỏ qua Spring proxy.
- Cần Bean Validation provider và `MethodValidationPostProcessor`/cấu hình tự động tương ứng. Trong Spring Boot có validation starter, auto-configuration thông thường bật method validation cho bean phù hợp; trong Spring Framework thuần phải kiểm tra cấu hình.
- Mặc định Spring AOP method validation có thể ném `jakarta.validation.ConstraintViolationException`. Khi bật tùy chọn `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, Spring có thể chuyển sang `org.springframework.validation.method.MethodValidationException`.
- Chỉ annotation class-level không làm mọi method bình thường tự được validate: cần constraint hoặc cascade thích hợp trên tham số/giá trị trả về.
- `@Validated` có thể khai báo groups tại method và class; khi thiết kế phức tạp, kiểm tra cách interceptor chọn group và proxy bằng test thực tế thay vì ngầm coi mọi annotation được “gộp” tự động.

Nếu cần một method chạy nhóm khác với class-level default, đặt group thích hợp ở nơi framework hỗ trợ, hoặc tách các service contract theo ngữ cảnh để không tạo mâu thuẫn khó đọc.

## 8. Spring MVC 6.1+: phân biệt validation đối số và method validation

Spring MVC hiện có **hai đường thực thi validation** dễ bị nhầm:

| Tình huống | Đường thực thi điển hình | Lỗi thường gặp |
| --- | --- | --- |
| `@Validated(Create.class) @RequestBody Dto` và không có constraint trực tiếp trên method | Validate DTO như một **method argument** | `MethodArgumentNotValidException` |
| `@Valid/@Validated @ModelAttribute Dto, BindingResult` | Validate/bind DTO, chuyển lỗi tới `BindingResult` để controller xem | Controller có thể tự phản hồi |
| `@RequestParam @Min(1) int page` (constraint trực tiếp trên method parameter, Spring MVC 6.1+) | **Built-in method validation** của MVC | `HandlerMethodValidationException` |
| Bean service `@Validated` với proxy AOP | **Spring AOP method validation** | `ConstraintViolationException` (mặc định), hoặc `MethodValidationException` khi được cấu hình |

**Quy tắc Spring MVC 6.1+ cần nhớ:** Một constraint Jakarta trực tiếp trên tham số hoặc return value của handler có thể khiến toàn bộ handler đi theo đường **method validation**; cách này bao gồm cả các constraint lồng nhau có `@Valid` và thường thay thế đường validate riêng từng `@RequestBody`/model attribute. Vì vậy exception có thể đổi từ `MethodArgumentNotValidException` sang `HandlerMethodValidationException`.

**Với controller đã có `@Validated` ở cấp class:** Spring có thể áp dụng **AOP proxy method validation**. Tài liệu Spring khuyến nghị bỏ `@Validated` class-level khỏi controller khi muốn tận dụng built-in MVC method validation (giới thiệu từ Spring Framework 6.1). Vẫn có thể dùng `@Validated(Group.class)` **trên tham số DTO** để chọn group.

Chẳng hạn:

```java
@GetMapping("/page")
public String page(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

Đây là **method fragment**. Vì `@Min` nằm trực tiếp trên tham số, với Spring MVC 6.1+ built-in method validation có thể xử lý nó. Không suy ra `@Validated` là annotation cần đặt trên mọi controller; còn tùy loại constraint và điểm tích hợp.

## 9. Group inheritance và cách mô hình hóa nhóm

Bạn có thể cho một nhóm kế thừa nhóm khác:

```java
import jakarta.validation.groups.Default;

public interface Create extends Default {}
public interface Update extends Default {}
```

Với mô hình này, khi yêu cầu `Create.class` hoặc `Update.class`, validator cũng xét các constraint thuộc `Default` thông qua **group inheritance**. Đây là lựa chọn khác với việc ghi `@Validated({Default.class, Create.class})` ở từng endpoint.

Nhưng trước khi thay đổi thiết kế, hãy hiểu tác động: inheritance khiến group mặc định luôn đi kèm group con ở mọi nơi có nhóm đó, bao gồm khi một service hoặc nested object được validate. Nếu từng endpoint cần chủ động chọn nhóm chung, cách khai báo tường minh thường dễ theo dõi hơn.

Nhóm cũng có thể mang ý nghĩa `Draft`, `Publish`, `Payment`…; nên đặt tên mô tả **ngữ cảnh validation**, không dùng làm quyền bảo mật. Group không thay thế authentication/authorization; việc một DTO đạt group Admin không chứng minh người gọi có quyền Admin.

## 10. `@GroupSequence`: khi thứ tự kiểm tra quan trọng

Mặc định, với nhiều group được yêu cầu cùng lúc, Jakarta Validation **không bảo đảm thứ tự đánh giá**. Nếu constraint khó hoặc tốn chi phí chỉ nên chạy khi các constraint cơ bản đã đúng, định nghĩa group sequence:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface AdvancedChecks {}

@GroupSequence({Default.class, AdvancedChecks.class})
interface CompleteChecks {}
```

Dùng:

```java
validator.validate(command, CompleteChecks.class);
```

Hoặc trong Spring:

```java
@Validated(CompleteChecks.class)
```

Khi validate sequence, provider chạy `Default` trước. Nếu có violation trong nhóm đó, **bỏ qua `AdvancedChecks`**; nếu đạt mới chạy tiếp. Cơ chế này khác với yêu cầu `@Validated({Default.class, AdvancedChecks.class})`: danh sách nhiều group **không mặc nhiên có thứ tự**.

Lưu ý:
- Một group sequence phải được định nghĩa nhất quán, không có vòng lặp.
- Tránh vừa dùng `@GroupSequence` trên class để **định nghĩa lại Default** vừa dùng sequence interface mà không hiểu sự khác biệt. Khi định nghĩa lại Default ở class, sequence phải bao gồm chính class đó theo đặc tả; ví dụ trên chỉ định nghĩa **sequence interface**.
- Không nên biến mọi workflow nghiệp vụ thành các tầng group phức tạp; kiểm tra phụ thuộc dữ liệu có thể rõ hơn khi làm tại service.

## 11. Cascade nhóm vào bean lồng nhau: `@Valid` và `@ConvertGroup`

Giả sử DTO đơn hàng phải validate địa chỉ giao hàng theo một nhóm riêng. `@Valid` chỉ định **đi sâu vào object**, còn `@ConvertGroup` thay đổi group truyền vào association đó:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.constraints.NotBlank;

interface OrderCreate {}
interface ShippingChecks {}

class ShippingAddress {
    @NotBlank(groups = ShippingChecks.class)
    private String city;
}

class Checkout {
    @Valid
    @ConvertGroup(from = OrderCreate.class, to = ShippingChecks.class)
    private ShippingAddress shippingAddress;
}
```

Các class trên là **mô hình minh họa**, không phải chương trình chạy độc lập. Khi validate `Checkout` theo `OrderCreate.class`, provider cascade tới `ShippingAddress` bằng nhóm `ShippingChecks.class`, vì association có group conversion tương ứng. Nếu không khai báo conversion và `ShippingAddress.city` chỉ thuộc `ShippingChecks`, group `OrderCreate` không tự làm nó chạy.

`@ConvertGroup` là cơ chế của **Jakarta Validation**, khác với `@Validated` ở controller. Chỉ dùng khi sự khác biệt group giữa cha và con là chủ đích; nếu không, `@Valid` đơn giản thường đủ.

## 12. Chọn group theo nghiệp vụ: hai phương án thiết kế

### Phương án A: một DTO với group rõ ràng

```java
public record UserInput(
    @Null(groups = Create.class)
    @NotNull(groups = Update.class) Long id,
    @NotBlank(groups = {Create.class, Update.class}) String name
) {}
```

Thích hợp khi các thuộc tính thực sự giống nhau và chỉ một vài ràng buộc khác theo thao tác. Khi dùng cách này, cần test đủ cả các tổ hợp group và thống nhất quy ước chung cho `Default`.

### Phương án B: DTO riêng cho từng endpoint

```java
public record CreateUserRequest(@NotBlank String name) {}
public record UpdateUserRequest(@NotNull Long id, @NotBlank String name) {}
```

Thích hợp khi shape dữ liệu của Create và Update khác nhau đáng kể, chẳng hạn Update hỗ trợ PATCH với nhiều field tùy chọn hoặc Create không hề có id. Giữ các constraint trong `Default` cho DTO riêng thường đơn giản hơn.

**Cách chọn:** Dùng groups khi muốn tái sử dụng **một mô hình input gần như giống nhau**. Nếu sự khác biệt lớn về dữ liệu, quyền sửa field, optionality hay ý nghĩa API, tách DTO thường rõ hơn. Dù chọn cách nào, không dùng validation group làm biện pháp chống mass assignment; cần kiểm soát field được bind và quyền sửa ở tầng thích hợp.

## 13. Lỗi hay gặp và cách tự kiểm tra

1. **Chỉ viết `@Validated(Create.class)` rồi nghĩ constraint không khai báo group cũng chạy.** Chúng thuộc `Default`. Thêm `Default.class` vào tập yêu cầu hoặc thiết kế inheritance/sequence rõ ràng.
2. **Gắn `groups=...` ở DTO nhưng không kích hoạt validation.** Annotation constraint không tự chạy khi gọi constructor/setter; cần `Validator`, Spring MVC, method validation hoặc tích hợp tương ứng.
3. **Tưởng `@Valid` chọn một nhóm cụ thể.** `@Valid` không có thuộc tính group. Dùng `@Validated` tại điểm Spring kích hoạt validation.
4. **Quên `@Valid` khi model có object con.** Constraint trên bean con thường không chạy khi thiếu cascade.
5. **Dùng `@Validated` trên field lồng nhau để đổi nhóm.** Dùng `@Valid` kết hợp `@ConvertGroup` theo chuẩn Jakarta khi cần đổi group tại cascade.
6. **Kỳ vọng thứ tự nhóm trong `@Validated({A.class, B.class})` là thứ tự chạy.** Nếu cần ưu tiên, dùng `@GroupSequence`.
7. **Gắn `@Validated` ở class controller mà không hiểu MVC 6.1+ method validation.** Có thể dẫn tới đường AOP khác built-in; xem nhóm annotation và loại exception.
8. **Thêm `@Validated` class service rồi gọi qua `this.method()`.** Self-invocation thường bỏ qua proxy, nên validation có thể không xảy ra.
9. **Chỉ có `spring-boot-starter-web` rồi nghĩ chắc chắn có Bean Validation provider.** Kiểm tra `spring-boot-starter-validation` hoặc cấu hình tương đương.
10. **Bắt mỗi `MethodArgumentNotValidException` và bỏ qua `HandlerMethodValidationException`.** Chọn xử lý lỗi phù hợp với cả hai cơ chế nếu handler có constraint trực tiếp.
11. **Cho rằng `@NotBlank` trong Default không quan trọng khi Update.** Nếu request Update không kết hợp Default, bắt buộc chung có thể bị bỏ qua.
12. **Dùng groups như role-based access control.** Constraint hợp lệ không chứng minh quyền thực hiện thao tác.
13. **Test bằng cách so thứ tự `Set<ConstraintViolation>`.** Sắp xếp field/code rồi so nội dung; không giả định iteration order.
14. **Nhầm lỗi chuyển chuỗi thành số với lỗi `@Min`/`@NotNull`.** Data binding/JSON deserialize có thể thất bại trước bước validate.
15. **Ghi group ở annotation không hỗ trợ `groups`.** Xác minh đó là Jakarta Constraint với thuộc tính `groups`, không chỉ là annotation bất kỳ.

## 14. Checklist áp dụng trong dự án

Trước khi viết endpoint sử dụng `@Validated`, hãy tự trả lời:

- Các constraint được khai báo với nhóm nào? Có cái nào đang thuộc `Default`?
- Endpoint này cần kiểm tra những nhóm nào? Có bỏ sót constraint bắt buộc chung không?
- Có object con cần `@Valid` và group conversion không?
- Điểm kích hoạt là request body, form, method service hay lời gọi `Validator` trực tiếp?
- Có validation provider thực sự trên classpath và được framework cấu hình?
- Controller có constraint trực tiếp trên method parameter khiến cơ chế method validation khác đi không?
- Có xử lý thích hợp các lỗi `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `BindingResult`, hoặc AOP `ConstraintViolationException` không?
- Test Create/Update, data null/blank, data hợp lệ, Default-only, group inheritance và một tình huống nested khi phù hợp.

## 15. Câu hỏi tự luyện

**Câu 1.** `@NotBlank String name` không ghi `groups`. Controller dùng `@Validated(Update.class)`. `name=""` chắc chắn bị báo lỗi không?

**Đáp:** Không, nếu `Update` là nhóm độc lập và không có inheritance/sequence; `@NotBlank` thuộc Default. Hãy yêu cầu cả `Default.class` nếu mục đích là kiểm tra tên.

**Câu 2.** `@NotNull(groups = Update.class) Long id` với `id=null` có bị lỗi khi gọi `@Validated(Create.class)` không?

**Đáp:** Không, vì constraint chỉ thuộc Update. Điều đó không chứng minh id phù hợp để Create; nếu cần id phải null khi Create, khai báo `@Null(groups=Create.class)`.

**Câu 3.** Muốn kiểm tra Default trước rồi mới kiểm tra Advanced, viết `@Validated({Default.class, Advanced.class})` có đủ không?

**Đáp:** Không; dùng `@GroupSequence({Default.class, Advanced.class})` trên sequence interface và chọn interface đó.

**Câu 4.** Vì sao service có `@Validated` vẫn không validate khi gọi nội bộ `this.changeStatus(null)`?

**Đáp:** Vì lời gọi self-invocation không đi qua Spring AOP proxy, nên interceptor không chặn được.

**Câu 5.** Spring MVC có `@RequestParam @Min(1) int page` và cùng method có một `@Valid @RequestBody`. Khi validation thất bại, luôn là `MethodArgumentNotValidException`?

**Đáp:** Không. Với cơ chế built-in method validation từ Spring MVC 6.1, constraint trực tiếp trên method parameter có thể kích hoạt `HandlerMethodValidationException` để xử lý cả method constraints và nested constraints.

**Câu 6.** Một object cha validate theo `Create` nhưng object con có constraint chỉ trong `Shipping`. Cần làm gì?

**Đáp:** Đặt `@Valid` trên association và cân nhắc `@ConvertGroup(from=Create.class,to=Shipping.class)`; chỉ `@Valid` sẽ không tự đổi sang group Shipping.

## 16. Tổng kết

- **Constraint `groups`** gắn quy tắc vào nhóm; **`@Validated`** của Spring chỉ định nhóm khi validation được kích hoạt.
- `@Valid` thuộc Jakarta; `@Validated` thuộc Spring. `@Valid` đặc biệt quan trọng cho cascade; `@Validated` cho chọn group trong tích hợp Spring.
- Nếu cần cả quy tắc chung và riêng, dùng `@Validated({Default.class, Create.class})` hoặc cơ chế inheritance/sequence được thiết kế rõ.
- `@Validated` ở **DTO parameter của controller** khác `@Validated` ở **class service** kích hoạt AOP method validation.
- Spring MVC 6.1+ có built-in method validation với hành vi exception riêng; chú ý class-level `@Validated` trên controller.
- Dùng group sequence cho **thứ tự**, group conversion cho **chuyển nhóm khi cascade** và test từng ngữ cảnh để tránh bỏ sót constraint.

### Tài liệu kỹ thuật

- Spring Framework — `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework — Java Bean Validation và method validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Validation trong Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@ModelAttribute` và `BindingResult`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Jakarta Validation 3.1 — Đặc tả về groups, group sequence và group conversion: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `Default` group: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/default
