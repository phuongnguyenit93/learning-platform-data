# Nguy cơ mass assignment khi binding trực tiếp vào entity trong Spring MVC

## 1. Vấn đề bảo mật: request được quyền thay đổi những thuộc tính nào?

Khi người dùng cập nhật hồ sơ, giao diện có thể chỉ hiển thị hai trường: `displayName` và `email`. Tuy nhiên entity Java lưu trong database còn có những trường nhạy cảm như `role`, `verified`, `tenantId`, `accountBalance` hoặc `ownerId`.

Nếu controller bind thẳng dữ liệu HTTP vào entity đó, kẻ gửi request có thể **tự thêm tham số không xuất hiện trên giao diện**:

```text
POST /accounts/1
Content-Type: application/x-www-form-urlencoded

displayName=Alice&email=alice@example.test&role=ADMIN&verified=true
```

Nếu entity có các writable properties tương ứng, cơ chế binding có thể ghi `role=ADMIN` và `verified=true` vào entity, dù hai trường này không được người dùng bình thường phép sửa.

Đó là **mass assignment** (còn được gọi là *over-posting* hoặc *autobinding vulnerability*): dữ liệu do client kiểm soát được ánh xạ vào nhiều thuộc tính object hơn phạm vi thực sự được ủy quyền. OWASP phân loại nhóm lỗi này liên quan đến CWE-915 — *Improperly Controlled Modification of Dynamically-Determined Object Attributes*.

**Nguyên tắc căn bản:** Có khả năng *bind được* một field không đồng nghĩa người gọi *có quyền sửa* field đó. Model/domain entity không nên trở thành hợp đồng input của HTTP API chỉ vì framework có thể tự động gán property.

Bài học tập trung vào **Spring MVC data binding**, đặc biệt khi form/query parameter được gán qua `@ModelAttribute` tới **JPA entity**. Các điểm khác biệt với `@RequestBody` JSON, constructor binding, validation, authorization và dirty checking cũng được trình bày để tránh bảo vệ sai tầng.

## 2. Mass assignment xảy ra thế nào trong Spring MVC?

### 2.1. @ModelAttribute và property binding

Một controller có thể viết rất ngắn:

```java
@PostMapping("/accounts/{id}")
public String update(@ModelAttribute Account account) {
    repository.save(account);
    return "ok";
}
```

Đây là **đoạn minh họa nguy hiểm**, không phải phương án khuyến nghị và không phải file Java độc lập. Nếu `Account` là JPA entity chứa các setter cho role, verified, số dư hoặc owner, API đang nhận input dưới hình dạng của toàn entity thay vì chỉ các trường được phép cập nhật.

Theo cơ chế thông thường, `@ModelAttribute` dùng `WebDataBinder` để lấy dữ liệu từ request và áp dụng constructor binding hoặc property binding. Với property binding, tên tham số request có thể khớp với tên thuộc tính Java.

Ví dụ:

```text
request parameter       Java bean property
--------------------    ---------------------------
displayName=Alice    -> account.setDisplayName("Alice")
email=a@example.org  -> account.setEmail("a@example.org")
role=ADMIN           -> account.setRole(Role.ADMIN)
verified=true        -> account.setVerified(true)
```

Dữ liệu không cần có mặt trong HTML form. Client có thể tự gửi request qua curl, trình duyệt tùy chỉnh hoặc API client.

### 2.2. Entity đã có sẵn trong Model còn nguy hiểm hơn

Spring hỗ trợ nạp model object trước khi controller handler chạy:

```java
@ModelAttribute("account")
public Account load(@PathVariable("id") long id) {
    return repository.findById(id).orElseThrow();
}

@PostMapping("/accounts/{id}")
public String update(
        @ModelAttribute("account") Account account) {

    repository.save(account);
    return "saved";
}
```

Đây là đoạn minh họa, cần imports, class và repository. Method `@ModelAttribute("account")` đầu tiên đặt entity vào Model, sau đó argument `@ModelAttribute("account")` của handler có thể lấy chính object đó và bind request lên nó.

Vì entity vốn đã chứa giá trị từ database, những setter nhạy cảm có thể bị gọi trước khi code cập nhật nghiệp vụ thực sự bắt đầu. Nếu entity còn **managed** trong JPA persistence context của một transaction, dirty checking còn có thể phát hiện và flush các thay đổi mà code không chủ đích tạo ra.

Trong một tình huống khác, entity đã detached, nhưng `repository.save(entity)` có thể merge và lưu các giá trị do binding sửa. **Không khẳng định mọi form binding tự động persist**: phải xét entity lifecycle, transaction và các lần `save`/flush thực tế.

### 2.3. Nested property paths làm phạm vi rộng hơn

Nếu form object có property lồng nhau và các accessor/collection hỗ trợ binding, tên tham số có thể là:

```text
shippingAddress.city=Hanoi
owner.id=99
items[0].unitPrice=0
permissions[0].enabled=true
```

Đây là **các đường dẫn giả định**, không có nghĩa entity nào cũng bind được chúng. Tính khả thi phụ thuộc object graph, writable properties, auto-grow, converter, collection và cấu hình binder.

Tuy nhiên nó cho thấy rủi ro không chỉ là một cột đơn lẻ. Khi bind entity có quan hệ JPA, những dữ liệu về owner, tenant, quyền hoặc giá tiền có thể nằm sâu trong object graph. Dùng DTO nông, đúng yêu cầu và chỉ mapping các field đã phê duyệt là cách giảm bề mặt tấn công hiệu quả.

## 3. Vì sao Spring không thể tự biết field nào được quyền sửa?

Spring có thể biết:

- Property `role` tồn tại, kiểu của nó là `Role`.
- String `ADMIN` có thể convert sang enum `Role.ADMIN`.
- Setter `setRole(Role)` cho phép ghi.
- Bean Validation có thể đánh giá constraint của property.

Nhưng chỉ từ những thông tin đó, framework **không biết** người gọi đang là khách, chủ tài khoản, nhân viên hỗ trợ hay quản trị viên; cũng không biết request này chỉ được đổi email hay được phép đổi role.

Đây là ranh giới giữa **binding capability** và **authorization policy**.

| Cơ chế | Nó quyết định điều gì? | Có tự chặn mass assignment không? |
| --- | --- | --- |
| Java setter | Property có thể thay đổi từ code Java | Không |
| `@ModelAttribute` | Chuyển request values sang object | Không, nếu object quá rộng |
| `@Valid` / `@Validated` | Giá trị có đạt constraints không | Không quyết định caller được quyền sửa |
| `@NotNull`, `@Email` | Cấu trúc hoặc điều kiện của giá trị | Không |
| `@Column(updatable=false)` | Ảnh hưởng SQL update của JPA cho một column | Không phải boundary authorization đầy đủ |
| `@JsonIgnore` | Hành vi Jackson JSON serialization/deserialization | Không bảo vệ property binding của `@ModelAttribute` |
| DTO input riêng | Thu hẹp property có thể nhận từ HTTP | Có ích mạnh, nhưng vẫn cần authorization |
| `WebDataBinder#setAllowedFields` | Giới hạn các property names ở property binding | Có ích cho binder được cấu hình |
| Service authorization | Người gọi có quyền sửa resource và field cụ thể không | Cần thiết |
| Database constraints | Bảo đảm một số invariants persisted | Bổ sung, không thay authorization |

Một role `ADMIN` hợp lệ về kiểu và enum nhưng hoàn toàn **không hợp lệ về quyền** nếu do người dùng tự đặt. Validation chỉ phát hiện cấu trúc sai hoặc điều kiện đã khai báo; không tự giải quyết tính chính danh của một thao tác.

## 4. Bốn biện pháp chính theo thứ tự ưu tiên

### 4.1. Ưu tiên input DTO, không dùng JPA entity làm form object

Nếu request chỉ được sửa `displayName` và `email`, hãy tạo DTO chỉ có đúng hai trường đó:

```java
public class ProfileUpdateForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    // Constructor mặc định và getters/setters của hai property này.
}
```

DTO **không có** `role`, `verified`, `tenantId`, `accountBalance`, `ownerId`. Tên role do client tự gửi không có property tương ứng trong DTO để bị ánh xạ.

Service nạp entity bằng ID và chỉ cập nhật những thuộc tính được phép:

```java
@Transactional
public void updateProfile(long accountId, ProfileUpdateForm form) {
    Account account = repository.findById(accountId)
        .orElseThrow();

    // Kiểm tra caller có quyền cập nhật accountId ở đây.
    account.setDisplayName(form.getDisplayName());
    account.setEmail(form.getEmail());
}
```

Đây là fragment tích hợp, cần dependency và quyền truy cập context phù hợp. Không dùng `BeanUtils.copyProperties(form, account)` như một bảo đảm bảo mật nếu nguồn/đích có thể mở rộng không được kiểm soát; **explicit assignment** làm danh sách field được phép rõ ràng khi review.

### 4.2. Dùng allowedFields khi property binding vẫn cần thiết

Đăng ký local `@InitBinder`:

```java
@InitBinder("profile")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
```

Và model attribute tương ứng:

```java
@PostMapping("/accounts/{id}")
public String update(
        @Valid @ModelAttribute("profile") ProfileUpdateForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

Đây là hai fragments của một controller. `@InitBinder("profile")` giới hạn binder của attribute có tên `profile`. `setAllowedFields` cung cấp một **allowlist** cho property binding; các input fields không được phép có thể được ghi vào `BindingResult#getSuppressedFields()`.

Ví dụ:

```java
if (errors.getSuppressedFields().length > 0) {
    // Chủ động từ chối request với property không cho phép.
}
```

**Cần chủ động trả lỗi** khi có suppressed fields nếu API muốn từ chối over-posting. Spring có thể lặng lẽ bỏ qua field ngoài allowlist; không nên mặc nhiên cho rằng mọi field bị suppress đều tạo `FieldError` hoặc HTTP 400.

Allowlist tốt hơn denylist bởi thêm một property nhạy cảm mới lên entity sẽ **không tự mở quyền bind** cho property đó. Ngược lại, nếu chỉ chặn `role` bằng `setDisallowedFields("role")`, lần bổ sung property `verified` hoặc `adminComment` sau này có thể bị bỏ sót.

### 4.3. Chỉ constructor binding khi phù hợp

Spring Framework 6.1+ hỗ trợ chế độ declarative binding:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Theo tài liệu MVC, khi bật flag này:

- Constructor binding vẫn được dùng theo thiết kế model object.
- Property binding không thực hiện trừ khi cấu hình explicit `allowedFields`.
- Với DTO immutable/record có constructor chỉ nhận các field hợp lệ, đây là một lớp phòng vệ hữu ích.

Một record input:

```java
public record ProfileInput(
    @NotBlank String displayName,
    @NotBlank @Email String email
) {}
```

Không mang theo `role` hoặc `verified` trong constructor. Tuy nhiên **constructor binding không tự cho phép dùng entity làm DTO**: nếu constructor của entity nhận thêm field nhạy cảm, field ấy vẫn có thể được lấy từ request. Chính thiết kế của **input type** quyết định an toàn.

`setAllowedFields` chủ yếu giới hạn **property binding**, không phải mọi argument được đưa vào primary constructor. Đừng áp dụng allowlist như một màn chắn vạn năng cho một entity có constructor nhận dữ liệu đặc quyền.

### 4.4. Authorization và mapping an toàn tại service

Sau binding, server cần:

- Xác định **identity thật** từ authentication context, không phải từ tham số `userId` hay `tenantId` do client tự gửi.
- Kiểm tra caller được phép cập nhật **đúng entity ID**.
- Kiểm tra quyền sửa **từng nhóm thuộc tính** nếu có roles khác nhau.
- Chỉ cập nhật các thuộc tính đã được chấp thuận và dùng transaction thích hợp.
- Có database constraints, optimistic locking, audit log hoặc policies khác khi hệ thống yêu cầu.

**DTO và allowlist không thay thế kiểm tra quyền truy cập object** (IDOR/BOLA). Một user có thể gửi DTO hoàn toàn hợp lệ nhưng chọn `/accounts/2` của người khác. Đây là lỗi authorization khác và phải được chặn độc lập.

## 5. Phân biệt @ModelAttribute form binding với @RequestBody JSON

Một sai lầm phổ biến: đặt `setAllowedFields(...)` trong `@InitBinder` rồi cho rằng nó cấm mọi JSON property. Thực tế:

| Hình thức request | Cơ chế chính | Biện pháp cốt lõi |
| --- | --- | --- |
| `application/x-www-form-urlencoded` với `@ModelAttribute` | `WebDataBinder` và conversion service | DTO + allowedFields/declarativeBinding |
| Query parameters vào `@ModelAttribute` | `WebDataBinder` | DTO + allowedFields |
| `@RequestBody SomeEntity` với JSON | `HttpMessageConverter`/Jackson deserialize | Input DTO/Jackson rules + service mapping |
| `@RequestPart` JSON | HTTP message converter cho body part | DTO riêng và validation |
| Direct `@RequestParam Long id` | Argument resolver | Chuyển kiểu + validation + authorization |
| Server lấy entity từ repository | JPA/repository | Kiểm tra quyền trước khi update, không bind tuỳ ý |

Với JSON:

```java
@PostMapping("/accounts/{id}")
public ResponseEntity<?> update(
        @PathVariable long id,
        @Valid @RequestBody ProfileUpdateRequest body) {
    // Chỉ map các field của body được phép.
    return ResponseEntity.noContent().build();
}
```

Đây là fragment, cần DTO và imports. Khi Jackson deserializes JSON thẳng vào entity có setter `setRole`, mass assignment **vẫn có thể xảy ra**, nhưng đó là đường **JSON deserialization**, không phải property binder của `@ModelAttribute`.

### Các annotation bảo vệ nhầm tầng

- `@JsonIgnore` hoặc `@JsonProperty(access = READ_ONLY)` tác động tới Jackson, không phải cơ chế property binder của `@ModelAttribute`.
- `@Column(updatable = false)` có thể hạn chế một cột khi JPA tạo SQL UPDATE, nhưng không chặn object mutation trong bộ nhớ, các side effects khác hoặc những cột nhạy cảm khác.
- `@Transient` là một khái niệm persistence mapping, không phải danh sách field mà HTTP được phép cập nhật.
- `@Valid` kiểm tra constraints; `role=ADMIN` vẫn có thể là enum value hợp lệ.
- Chỉ bỏ field khỏi HTML form hoặc ẩn một input không phải là phòng vệ. Client không bị buộc tuân theo UI.

Để nhận JSON an toàn, dùng DTO/record đầu vào với danh sách fields tối thiểu, validation và explicit service mapping. Nếu muốn từ chối JSON có unknown fields, cấu hình Jackson để fail on unknown properties theo contract riêng; đây là hành vi khác với `BindingResult#getSuppressedFields()` của MVC form binder.

## 6. JPA: vì sao sai lầm còn dẫn tới persisted changes?

### 6.1. Persistence context và dirty checking

Khi một entity đang **managed** trong một JPA persistence context, việc gọi setter khiến state thay đổi. Khi transaction commit hoặc flush, JPA provider có thể phát hiện thay đổi và ghi SQL UPDATE.

Vì thế rủi ro không chỉ là một method `repository.save(...)` rõ ràng. Nếu một managed entity bị bind trước đó trong một luồng request/transaction, việc kiểm soát cập nhật có thể trở nên khó quan sát. Không nên dựa vào “đoạn code này không gọi save” để kết luận entity không bao giờ được persist.

**Tuy nhiên:** trạng thái managed/detached tùy vào transaction boundary, OpenEntityManagerInView, repository method và cách entity được load. Một request không tự động flush mọi object đã bị sửa. Phân tích chính xác luồng persistence trước khi khẳng định impact.

### 6.2. Association và tenant boundary

Entity có thể chứa:

```java
@ManyToOne
private Organization owner;

@Enumerated(EnumType.STRING)
private Role role;

private boolean approved;
```

Đây là fragment JPA. Nếu cho client bind trực tiếp các property của object graph, có thể có nguy cơ thay quan hệ sở hữu hoặc trạng thái phê duyệt tùy mapping và binder configuration.

Không lấy `ownerId`/`tenantId` từ request rồi tin đó là ngữ cảnh phân quyền. Xác định tenant từ principal/server-side context, kiểm tra mọi lookup có scope theo tenant và chỉ cho phép liên kết phù hợp.

### 6.3. Invariants và concurrency

Ngay cả một DTO đúng fields vẫn cần bảo vệ các invariants như tổng tiền tính từ server, unique constraints, giới hạn tồn kho và state transitions. Các kiểm tra kiểu `@Min(0)` chỉ đánh giá một giá trị, không chống double-spend hay stale writes. Dùng transaction, optimistic locking, ràng buộc database hoặc domain methods theo yêu cầu.

## 7. Bài thực hành Java 17 + Spring Boot 3.5.6 + JPA/H2

Mục tiêu là quan sát **trực tiếp** sự khác biệt giữa bind entity nguy hiểm và DTO được kiểm soát. Ứng dụng dùng database H2 in-memory và khởi tạo một tài khoản demo:

```text
id=1
displayName=Alice
email=alice@example.test
role=USER
verified=false
```

Có ba endpoint:

1. `GET /lab/accounts/1` — đọc trạng thái account qua response DTO, để thấy tác động.
2. `POST /lab/accounts/1` — **cách an toàn hơn**, nhận `ProfileUpdateForm` và chỉ cập nhật `displayName`/`email`; extra properties bị từ chối.
3. `POST /lab/unsafe/accounts/1` — **đường lab cố tình không an toàn**, bind thẳng request vào entity đã load để tái hiện nguy cơ. Không được triển khai endpoint này trong ứng dụng thật.

Để giảm khả năng bị triển khai nhầm, các controllers được đánh dấu `@Profile("lab")`, server chỉ bind loopback `127.0.0.1` và dữ liệu dùng H2 memory. Không có authentication/authorization trong bài thực hành, nên **kể cả endpoint DTO demo cũng chưa phải ứng dụng production hoàn chỉnh**.

### 7.1. Cấu trúc file

```text
mass-assignment-lab/
├── pom.xml
└── src/main/
    ├── java/demo/massassign/
    │   ├── MassAssignmentApplication.java
    │   ├── Account.java
    │   ├── AccountRepository.java
    │   ├── ProfileUpdateForm.java
    │   ├── AccountView.java
    │   ├── ProfileService.java
    │   ├── SafeAccountController.java
    │   └── UnsafeAccountController.java
    └── resources/
        └── application.properties
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>mass-assignment-lab</artifactId>
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
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

Mỗi starter phục vụ một vai trò: MVC/web, Bean Validation và JPA. H2 là database thử nghiệm, không tạo yêu cầu cài database ngoài.

### 7.3. application.properties

```properties
# Chỉ chạy lab ở loopback, không public ra mạng.
server.address=127.0.0.1
server.port=8080

spring.datasource.url=jdbc:h2:mem:massassignment;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`ddl-auto=create-drop` chỉ phù hợp demo/test. Nó sẽ xóa dữ liệu khi context đóng; tuyệt đối không copy config này cho database production. `open-in-view=false` giúp tránh tự giữ persistence context qua toàn HTTP request, nhưng không thay thế DTO hay authorization.

### 7.4. MassAssignmentApplication.java

```java
package demo.massassign;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MassAssignmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(MassAssignmentApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(AccountRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.save(new Account(
                    "Alice",
                    "alice@example.test",
                    Account.Role.USER,
                    false
                ));
            }
        };
    }
}
```

Với H2 database mới và không có các bản ghi khác, record đầu tiên thường nhận ID `1`. Nếu project thật đã có dữ liệu khác, phải dùng ID thực tế; các lệnh dưới đây giả định môi trường lab sạch.

### 7.5. Account.java — entity có fields nhạy cảm

```java
package demo.massassign;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {

    public enum Role {
        USER, ADMIN
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    private String email;

    @Enumerated(EnumType.STRING)
    @Column(name = "access_role", nullable = false)
    private Role role;

    private boolean verified;

    protected Account() {
    }

    public Account(
            String displayName,
            String email,
            Role role,
            boolean verified) {

        this.displayName = displayName;
        this.email = email;
        this.role = role;
        this.verified = verified;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Role getRole() {
        return role;
    }

    // Setter này có thể cần cho admin workflow, nhưng không có nghĩa
    // profile update request của user được phép gọi nó.
    public void setRole(Role role) {
        this.role = role;
    }

    public boolean isVerified() {
        return verified;
    }

    public void setVerified(boolean verified) {
        this.verified = verified;
    }
}
```

Entity cố ý có setters cho `role` và `verified` để tái hiện mass assignment. Trong hệ thống thật có thể hạn chế public setters, dùng domain methods kiểm tra quyền và bảo đảm các thay đổi đặc quyền đi qua service riêng. Tuy vậy **bỏ setter không phải kế hoạch bảo vệ duy nhất**: có thể còn constructor binding, field access hoặc JSON paths khác. Vẫn phải kiểm soát input boundary.

### 7.6. AccountRepository.java

```java
package demo.massassign;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
```

Spring Data JPA tạo implementation cho repository này khi chạy application context.

### 7.7. ProfileUpdateForm.java — input DTO chỉ có hai field

```java
package demo.massassign;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class ProfileUpdateForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    public ProfileUpdateForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

**Điểm quan trọng nhất của demo:** DTO này **không chứa** `role` hoặc `verified`. Những fields đó không có đường hợp lệ qua form update profile.

`@NotBlank` và `@Email` bảo đảm cấu trúc cơ bản của input. Chúng không thay nhiệm vụ kiểm tra người gọi có quyền update account này hay không.

### 7.8. AccountView.java — response DTO

```java
package demo.massassign;

public record AccountView(
        long id,
        String displayName,
        String email,
        String role,
        boolean verified) {

    public static AccountView from(Account account) {
        return new AccountView(
            account.getId(),
            account.getDisplayName(),
            account.getEmail(),
            account.getRole().name(),
            account.isVerified()
        );
    }
}
```

Response DTO riêng giúp ứng dụng kiểm soát các fields được công bố. Bài lab chủ động cho hiện `role`/`verified` để quan sát thử nghiệm; API public thật nên quyết định riêng những thông tin nào được phép tiết lộ.

### 7.9. ProfileService.java — cập nhật thuộc tính có chủ đích

```java
package demo.massassign;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProfileService {

    private final AccountRepository repository;

    public ProfileService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AccountView read(long id) {
        return AccountView.from(load(id));
    }

    @Transactional
    public AccountView update(long id, ProfileUpdateForm form) {
        Account account = load(id);

        // Trong production, kiểm tra principal/tenant/owner ở đây,
        // trước khi sửa các thuộc tính.
        account.setDisplayName(form.getDisplayName());
        account.setEmail(form.getEmail());

        // Managed entity được JPA dirty-check khi transaction commit.
        return AccountView.from(account);
    }

    private Account load(long id) {
        return repository.findById(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
    }
}
```

Service chỉ có hai setter dành cho profile update. Vì nó có transaction, entity nạp qua repository là managed trong transaction đó; JPA sẽ flush thay đổi khi commit. Không copy nguyên DTO/entity bằng reflection, không cập nhật role/verified từ form.

**Giới hạn của demo:** comment về principal không phải một bước authorization đã chạy. Ứng dụng chỉ chạy local để minh họa mass assignment; production phải bổ sung Spring Security và kiểm tra ownership/tenant trước khi cập nhật.

### 7.10. SafeAccountController.java — form DTO + allowlist

```java
package demo.massassign;

import jakarta.validation.Valid;

import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("lab")
@RestController
@RequestMapping("/lab/accounts")
public class SafeAccountController {

    private final ProfileService service;

    public SafeAccountController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("form")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @GetMapping("/{id}")
    public AccountView read(@PathVariable("id") long id) {
        return service.read(id);
    }

    @PostMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> update(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("form") ProfileUpdateForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("REJECTED_FIELDS");
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("INVALID_PROFILE");
        }

        return ResponseEntity.ok(service.update(id, form));
    }
}
```

**Ba lớp bảo vệ khác nhau:**

1. `ProfileUpdateForm` chỉ có những property được phép sửa; không có role/verified.
2. `binder.setAllowedFields("displayName","email")` chủ động giới hạn property binding. Extra HTTP parameter sẽ được suppress và handler từ chối request bằng status 400.
3. Service chỉ copy hai fields từ DTO vào entity; đó là nơi cần thêm authorization và kiểm tra tenant theo người dùng thật.

`BindingResult` phải đứng **ngay sau** `@ModelAttribute("form") ProfileUpdateForm form`. Nếu chuyển một tham số khác vào giữa, quy tắc bắt lỗi của form không còn đúng. Một `@Valid` được dùng để chạy Jakarta Bean Validation; riêng `getSuppressedFields()` phục vụ kiểm tra những field binder không cho phép.

**Không bao giờ dùng một DTO “có đủ mọi fields rồi @Valid” thay cho allowlist.** Một property như `role` có thể hoàn toàn hợp lệ về kiểu nhưng vẫn không được caller thay đổi.

### 7.11. UnsafeAccountController.java — endpoint cố tình mắc lỗi

```java
package demo.massassign;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@Profile("lab")
@RestController
@RequestMapping("/lab/unsafe/accounts")
public class UnsafeAccountController {

    private final AccountRepository repository;

    public UnsafeAccountController(AccountRepository repository) {
        this.repository = repository;
    }

    @ModelAttribute("account")
    public Account load(@PathVariable("id") long id) {
        return repository.findById(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
    }

    @PostMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public AccountView update(
            @ModelAttribute("account") Account account) {

        // KHÔNG AN TOÀN: entity đã được property-bind trực tiếp.
        // User có thể đã ghi role / verified trước khi vào đây.
        Account saved = repository.save(account);
        return AccountView.from(saved);
    }
}
```

Đây là **một test fixture intentionally vulnerable**: chỉ có mặt khi chạy profile `lab`, không có policy/allowlist và không dùng input DTO. `@ModelAttribute("account")` tạo/nạp model attribute từ repository; Spring MVC có thể bind các request parameters lên object đó trước khi handler `update` gọi `save`.

Nếu request gửi `role=ADMIN`, Spring có conversion sẵn cho enum và setter `setRole` làm thay đổi giá trị. `verified=true` được convert thành boolean. `repository.save(account)` có thể lưu các giá trị không được phép đó.

**Không triển khai hoặc mở truy cập mạng cho endpoint này.** Mục đích duy nhất là minh họa vì sao không được bind HTTP trực tiếp lên domain entity.

### 7.12. Chạy lab

Cần Java 17+, Maven 3.x. Trong thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run -Dspring-boot.run.profiles=lab
```

Ứng dụng nghe tại `127.0.0.1:8080` theo `application.properties`. Với H2 mới, seed tạo account ID 1 có role `USER` và `verified=false`.

**Chạy các bước theo thứ tự dưới đây** để kết quả minh họa không bị ảnh hưởng bởi thao tác cố tình không an toàn ở cuối.

#### Bước A — kiểm tra trạng thái ban đầu

```bash
curl -s 'http://127.0.0.1:8080/lab/accounts/1'
```

Body có những giá trị quan trọng:

```json
{
  "id": 1,
  "displayName": "Alice",
  "email": "alice@example.test",
  "role": "USER",
  "verified": false
}
```

Các trường trên là dữ liệu logic của JSON response; thứ tự property và whitespace có thể khác do Jackson serializer.

#### Bước B — gửi role/verified vào endpoint an toàn

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'verified=true'
```

HTTP status **400 Bad Request**. Body chính xác do handler chủ động trả:

```text
REJECTED_FIELDS
```

Vì `role` và `verified` không có trong allowlist của binder, chúng bị suppress; handler kiểm tra `getSuppressedFields()` và từ chối toàn request. Nó **không** gọi service.update.

Chạy lại `GET /lab/accounts/1`: role vẫn `USER` và verified vẫn `false`. Đây là điểm chứng minh của cách xử lý an toàn.

#### Bước C — cập nhật profile đúng hợp đồng

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice Nguyen' \
  --data-urlencode 'email=alice.nguyen@example.test'
```

HTTP **200 OK**. Response JSON có:

```json
{
  "id": 1,
  "displayName": "Alice Nguyen",
  "email": "alice.nguyen@example.test",
  "role": "USER",
  "verified": false
}
```

Service đã sửa hai property được phép, nhưng role và verified vẫn giữ từ database. Các properties JSON có thể được sắp xếp khác tùy serializer.

#### Bước D — cố tình minh họa đường entity-binding không an toàn

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/unsafe/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice Nguyen' \
  --data-urlencode 'email=alice.nguyen@example.test' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'verified=true'
```

HTTP **200 OK**, nhưng đây là kết quả **nguy hiểm**, không phải thành công bảo mật. Response thể hiện:

```json
{
  "id": 1,
  "displayName": "Alice Nguyen",
  "email": "alice.nguyen@example.test",
  "role": "ADMIN",
  "verified": true
}
```

Vì dữ liệu đã được bind lên chính entity trước khi gọi `repository.save`, role và verified thay đổi. Đây là over-posting đúng nghĩa.

#### Bước E — kiểm tra persisted state

```bash
curl -s 'http://127.0.0.1:8080/lab/accounts/1'
```

Response lúc này phản ánh role `ADMIN` và `verified=true`. Điều đó chứng minh dữ liệu không chỉ bị sửa tạm trong object response; `repository.save` của unsafe handler đã persist thay đổi.

**Dừng ứng dụng và khởi động lại** sẽ reset H2 memory schema ở lab theo `create-drop`, cho phép thử lại từ account ban đầu.

#### Bước F — validation dữ liệu sai

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=' \
  --data-urlencode 'email=not-an-email'
```

HTTP **400 Bad Request**, body:

```text
INVALID_PROFILE
```

Đây là lỗi từ `@NotBlank`/`@Email` trên DTO. Nó khác với case có fields bị suppress, và cả hai khác với kiểm tra quyền sở hữu account.

Các lệnh `curl -i` hiển thị headers và body; các khối JSON mô tả các field quan trọng, không khẳng định thứ tự/whitespace chính xác. Khi chưa thử nghiệm runtime, bạn nên chạy tuần tự và kiểm tra HTTP status cùng database state theo các kỳ vọng này.

## 8. So sánh hai API sau bài thực hành

| Tiêu chí | `POST /lab/unsafe/accounts/{id}` | `POST /lab/accounts/{id}` |
| --- | --- | --- |
| Đối tượng nhận request | JPA `Account` | `ProfileUpdateForm` |
| Nạp entity trước binding | Có, qua `@ModelAttribute` method | Không; entity được nạp sau validation ở service |
| Có `role`/`verified` trên input type | Có setter trên entity | DTO không có |
| Allowed fields | Không | `displayName`, `email` |
| Xử lý over-posting | Không phát hiện | Kiểm tra suppressed fields và trả 400 |
| Validation | Không có explicit DTO validation | `@Valid` trên DTO |
| Mapping trước persistence | Save entity đã bị bind | Explicit setters trong service |
| Authorization demo | Không | Không, phải bổ sung trước production |
| Kết quả khi client gửi `role=ADMIN` | Có thể persist role ADMIN | Bị từ chối, không update |
| Phù hợp triển khai thật | **Không** | Là nền tảng tốt hơn, nhưng chưa đủ authentication/authorization |

Bài học không phải rằng mọi `@ModelAttribute` đều nguy hiểm. Nó nguy hiểm khi **đích binding có nhiều writable fields hơn quyền update của request**. Một DTO chuyên biệt có phạm vi rõ ràng và được validate/authorize đúng cách là lựa chọn phù hợp.

## 9. Khi thực sự bắt buộc phải bind một entity

Có hệ thống legacy dùng entity trực tiếp trong server-side form. Nếu không thể refactor ngay, tối thiểu phải:

1. Tạo `@InitBinder("account")` với `setAllowedFields(...)` **chỉ những field đã duyệt**.
2. Sử dụng `setDeclarativeBinding(true)` khi phù hợp; xét riêng constructor properties.
3. Kiểm tra `BindingResult#getSuppressedFields()` và từ chối request không hợp lệ.
4. Giữ `BindingResult` ngay sau form object để xử lý binding/type conversion errors.
5. Kiểm tra quyền với ID/tenant từ server-side context.
6. Không lưu/flush entity nếu validation hoặc authorization thất bại.
7. Có integration tests over-posting ở từng endpoint.
8. Lập kế hoạch chuyển sang DTO, vì binder field allowlist không giải quyết mọi đường tương tác với entity.

Ví dụ legacy safeguard:

```java
@InitBinder("account")
void restrict(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}

@PostMapping("/accounts/{id}")
public ResponseEntity<?> update(
        @Valid @ModelAttribute("account") Account account,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().build();
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    // Còn cần authorization và persistence mapping an toàn.
    return ResponseEntity.noContent().build();
}
```

Đây là **fragment phòng vệ có điều kiện** cho code legacy, không là phần của lab chạy đầy đủ. Nếu một method `@ModelAttribute("account")` nạp entity trước handler, hãy chú ý entity có thể bị mutate **ngay trong binding**, trước khi code kiểm tra suppressed fields. Tốt hơn không cho binder nhận entity ngay từ đầu.

Nếu cần reference entity cho view hoặc domain operation mà **không muốn bind**:

```java
@ModelAttribute(binding = false) Account account
```

Trong một handler có thể dùng DTO form riêng và entity được nạp từ model, với `binding=false` để tránh bind request vào entity đó. Tuy nhiên phải bảo đảm model attribute có sẵn, nguồn ID đáng tin và quyền truy cập resource đã được kiểm tra.

## 10. @InitBinder, phạm vi và nguy cơ cấu hình ghi đè

`@InitBinder` trong controller thường có phạm vi local. `@ControllerAdvice` có thể áp dụng binder rules cho nhiều controller. Tuy vậy:

- `@InitBinder("profile")` chỉ chạy cho binder model attribute tên `profile`.
- `@InitBinder` không có tên có thể áp dụng rộng hơn, dễ chạm những DTO không mong muốn.
- Cấu hình global từ `@ControllerAdvice` thường được áp dụng trước local `@InitBinder`.
- `setAllowedFields(...)` là **setter**, không tự intersect với danh sách allowlist được đặt trước.
- Một local setter chạy sau có thể mở rộng allowed fields và phá vỡ kỳ vọng của global security policy.

Ví dụ nguy hiểm:

```java
// Global advice đã giới hạn:
binder.setAllowedFields("displayName", "email");

// Local controller chạy sau, vô tình mở rộng:
binder.setAllowedFields("displayName", "email", "role");
```

Đây là fragment minh họa. Đừng xem allowlist của global advice là một chính sách bất biến nếu các binder customizations phía sau còn có quyền thay đổi nó.

Tốt nhất là đưa chính sách binding quan trọng vào cấu hình có chủ sở hữu rõ, giới hạn từng DTO và có regression test đảm bảo field nhạy cảm không bao giờ được bind.

## 11. Những giải pháp dễ gây cảm giác an toàn giả

### 11.1. “Chỉ cần @Valid”

Không đúng. `@Valid` đánh giá constraints đang được khai báo; nó không biết user có quyền nâng role hay không. Ví dụ một enum `Role.ADMIN` hoàn toàn hợp lệ về kiểu dù người gửi request không được sửa.

Một DTO có field `role`, `@NotNull` và `@Valid` vẫn có thể bị over-posting nếu server tin role đó mà không authorization.

### 11.2. “Cấm role bằng disallowedFields là đủ”

Không nên. Khi team thêm property `approved`, `verified` hoặc `tenantId`, denylist cũ không tự cập nhật. OWASP và Spring đều khuyến nghị ưu tiên **allowlist** khi phải property-bind.

### 11.3. “Không có input trong HTML thì không ai gửi được”

Không đúng. Server không nhận một bản copy bất biến của form UI. Client tự xây HTTP request được, kể cả hidden/readonly/disabled HTML controls có bị thay đổi hay không.

### 11.4. “Chỉ dùng @JsonIgnore là an toàn”

Không đủ. `@JsonIgnore` làm việc với Jackson; form binding bằng `@ModelAttribute` không tự dùng Jackson cho property resolution. Với JSON cũng phải kiểm tra cả serialization lẫn deserialization settings và business authorization.

### 11.5. “Có @Column(updatable=false) nên không sao”

Không đúng. Annotation JPA này chỉ tác động tới persistence SQL cho column được cấu hình. Object trong memory vẫn có thể thay đổi; code khác có thể dựa vào giá trị đó, và các thuộc tính nhạy cảm khác vẫn cập nhật.

### 11.6. “Bỏ setter là đã giải quyết mọi thứ”

Hạn chế setter giúp giảm property binding surface, nhưng Java object vẫn có thể nhận dữ liệu qua constructor, reflection/field access của serializer, mapper hoặc paths khác. Hãy dùng input DTO/authorization và kiểm thử boundary.

### 11.7. “DTO an toàn thì không cần kiểm tra owner”

Sai. DTO ngăn client tự thêm field; nó không ngăn đổi ID trong URL để sửa tài khoản của người khác. Ownership/tenant authorization là cơ chế riêng bắt buộc.

### 11.8. “Repo.save() là nơi đầu tiên entity thay đổi”

Không nhất thiết. Nếu bind được thực hiện trên một entity đã có trong Model, các setter đã chạy trước khi handler bắt đầu. Khi managed, dirty checking còn có thể persist thay đổi tại transaction flush.

## 12. Kiểm thử phòng ngừa mass assignment

Một hệ thống nên có **negative tests** cho các trường hợp cố tình gửi thêm property.

| Tình huống | Kỳ vọng |
| --- | --- |
| Gửi chỉ `displayName`/`email` hợp lệ | Update thành công, field nhạy cảm không đổi |
| Gửi thêm `role=ADMIN` | 4xx hoặc bỏ qua có chủ đích, **không update role** |
| Gửi thêm `verified=true` | Không update verified |
| Gửi `ownerId` hoặc `tenantId` | Không thay tenant/owner |
| Gửi nested `owner.id` | Không đổi quan hệ sở hữu |
| Gửi `status=APPROVED` hoặc `balance=0` | Không đổi trạng thái/tài chính |
| Gửi số không parse được vào property | Trả lỗi type conversion, không persist một phần |
| DTO invalid theo `@NotBlank`/`@Email` | 4xx, không cập nhật |
| Dùng user A gửi update ID của user B | 403/404 theo contract, không cập nhật B |
| Sửa fields không thuộc role hiện hành | Bị từ chối kể cả DTO có chứa field |
| Cùng API nhận JSON `@RequestBody` | DTO và Jackson mapping chỉ nhận fields đã duyệt |
| Refactor entity thêm setter mới | Input binding không tự mở quyền cập nhật field mới |

### 12.1. Unit test chưa đủ

Một unit test gọi trực tiếp:

```java
new SafeAccountController(service).update(id, form, errors);
```

không kích hoạt `WebDataBinder`, `@InitBinder`, conversion/validation của MVC. Nó có thể kiểm tra logic service/controller đã viết nhưng **không** chứng minh over-posting bị ngăn.

Dùng `MockMvc` hoặc HTTP integration tests qua Spring context để xác nhận:

- `getSuppressedFields()` được ghi cho input ngoài allowlist.
- `@Valid` được chạy và `BindingResult` đứng đúng chỗ.
- Entity trong database giữ nguyên role/verified sau request bị từ chối.
- Không có endpoint nào bind trực tiếp input không tin cậy vào entity.
- Mọi update có kiểm tra ownership/tenant từ identity đáng tin.

### 12.2. Ví dụ kiểm thử MockMvc (fragment tùy chọn)

Nếu thêm test dependency `spring-boot-starter-test` và class test thích hợp, có thể kiểm tra:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProfileBindingSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void overPostingIsRejected() throws Exception {
        mvc.perform(post("/lab/accounts/1")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Alice")
                .param("email", "alice@example.test")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("REJECTED_FIELDS"));
    }
}
```

Đây là **fragment kiểm thử**, cần imports, profile lab được bật, application context và test dependency; nó không thuộc 8 Java source files của ví dụ chính. Trong production tests, ngoài HTTP status phải assert lại database state, tránh một bug đã mutate/persist entity mà controller vẫn trả 400.

### 12.3. Test cho JSON cũng cần riêng

Đừng dùng một test form-binding rồi kết luận `@RequestBody Account` cũng đã an toàn. Hãy gửi JSON chứa thêm `role`, `verified` hoặc nested fields vào endpoint JSON thực tế, xem DTO/Jackson deserialization xử lý ra sao và xác nhận giá trị persisted không đổi.

Nếu cấu hình strict unknown fields, hãy kiểm tra response 400 và thông báo an toàn. Nếu API cố ý bỏ qua unknown fields, phải có test chứng minh server không map chúng vào entity.

## 13. Phòng vệ bổ sung trong kiến trúc thực tế

### 13.1. Tách use cases thay vì một entity update chung

Thay vì một endpoint `PATCH /accounts/{id}` nhận mọi fields, cân nhắc phân tách:

- `PUT /accounts/{id}/profile` cho tên hiển thị/email.
- `POST /accounts/{id}/verify` cho luồng xác thực có kiểm chứng riêng.
- `POST /admin/accounts/{id}/role` cho thay đổi role sau khi xác thực admin.
- `POST /accounts/{id}/transfer-owner` nếu domain cho phép và có authorization đặc thù.

Mỗi endpoint có input DTO và service method riêng, giúp chính sách rõ hơn. Những đường dẫn trên chỉ là mô hình thiết kế, không có trong demo.

### 13.2. Service methods theo ý nghĩa domain

Một service tốt có các operation như `changeEmail(...)`, `verifyIdentity(...)`, `grantRole(...)` thay vì một `updateEntity(Map<String,Object> changes)` tổng quát. Như vậy code review nhìn được field và quyền cần thiết theo từng use case.

### 13.3. Bảo vệ database

Database constraints và optimistic locking giúp ngăn data corruption, trùng lặp và lost updates. Nhưng chúng không hiểu “user này không được tự tăng role” nếu update hợp lệ về schema. Authorization và input mapping vẫn phải nằm trong ứng dụng hoặc policy layer thích hợp.

### 13.4. Audit và observability

Log việc thử gửi field không được phép ở mức đủ để phát hiện abuse, nhưng tránh log toàn bộ request body hoặc rejected values nhạy cảm. Với cập nhật role/verified do admin thực hiện, ghi audit event gồm identity, resource, hành động, thời điểm và lý do theo chính sách hệ thống.

### 13.5. Mapping libraries và code generation

Các mapper như MapStruct có thể giúp chuyển DTO sang entity, nhưng vẫn phải review mappings. Nếu có “update entity from DTO” dùng null/unmapped policy tự động, một field mới thêm vào DTO/entity có thể vô ý được copy. Explicit mapping config hoặc domain methods tốt hơn implicit copy mọi property.

### 13.6. Tương tác với frontend

Frontend form validation và disabled controls chỉ cải thiện UX. Backend vẫn phải xác thực/ủy quyền mọi field. Không lấy hidden input như `role=USER` hoặc `price=100` làm nguồn tin cậy; giá tiền, tenant và permissions phải được tính/quyết định ở server.

## 14. Nhận diện rủi ro khi review code

Khi đọc controller Spring MVC, cần chú ý những pattern:

```java
public void update(@ModelAttribute UserEntity user) { ... }
```

```java
public void save(@RequestBody AccountEntity account) { ... }
```

```java
repository.save(entityBoundFromClient);
```

```java
BeanUtils.copyProperties(request, entity);
```

Đây là **các dấu hiệu cần review**, không phải khẳng định chắc chắn lỗ hổng. Phải xét setters, input mapping, validation, allowlists, authorization, serialization và persistence. Nếu request DTO chỉ có fields được phép, có quyền truy cập rõ ràng và mapper chính xác, tự động hóa mapping có thể hợp lý; ngược lại, sự tiện lợi của bind/copy có thể làm thay đổi trạng thái đặc quyền ngoài ý định.

Checklist khi code review:

1. Entity nào đang được expose làm request model?
2. Các writable properties có field nhạy cảm không?
3. Model attribute có được nạp từ database trước binding không?
4. Binder nào có `setAllowedFields` / `setDeclarativeBinding`?
5. Cấu hình global/local binder có thể ghi đè nhau không?
6. DTO có property đặc quyền mà user thường không được sửa không?
7. Mapping ở service có explicit assignment không?
8. ID, owner, tenant lấy từ đâu và được kiểm tra với principal thế nào?
9. Có JSON endpoint riêng mở cùng object không?
10. Sau lỗi validation/authorization, database state có chắc chắn không đổi?
11. Regression tests có gửi field thừa/nested fields không?
12. Code có lộ rejected values/PII qua error messages hoặc logs không?

## 15. Tóm tắt

**Mass assignment xảy ra khi request có thể thay đổi nhiều thuộc tính của object hơn những gì người dùng được phép thao tác.** Trong Spring MVC, bind trực tiếp `@ModelAttribute` lên JPA entity có các writable properties như `role`, `verified`, `owner` hay `balance` dễ tạo rủi ro over-posting. Khi entity được persist bằng `save`/dirty checking, các thay đổi không được cho phép có thể đi vào database.

Phòng vệ ưu tiên là **input DTO riêng cho từng use case**, **explicit mapping** vào entity sau khi **authorization** thành công, và **allowlist property binding** bằng `WebDataBinder#setAllowedFields` nếu còn dùng property binding. Khi phù hợp, `setDeclarativeBinding(true)` và immutable DTO giảm phạm vi property mutation; không nhầm chúng với authorization. Với JSON, dùng DTO và Jackson configuration vì `@RequestBody` không bị giới hạn chỉ bởi `setAllowedFields` của form binder.

Hãy kiểm thử HTTP thực tế với các field cố tình thêm như `role=ADMIN` và xác nhận **persistent state không đổi**. Đây mới là bằng chứng hữu ích hơn việc chỉ thấy request bị từ chối.

## Tài liệu tham khảo

- Spring Framework 6.2 — `@ModelAttribute` controller arguments và security considerations: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@InitBinder`, allowlist, constructor binding và `setDeclarativeBinding`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — `@ModelAttribute` methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html
- Spring Framework 6.2 — `@RequestBody` and message converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — `DataBinder` Javadoc (allowed fields, suppressed fields, declarative binding): https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/validation/DataBinder.html
- OWASP Cheat Sheet Series — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- CWE-915 — Improperly Controlled Modification of Dynamically-Determined Object Attributes: https://cwe.mitre.org/data/definitions/915.html
- OWASP API Security Top 10 — Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/