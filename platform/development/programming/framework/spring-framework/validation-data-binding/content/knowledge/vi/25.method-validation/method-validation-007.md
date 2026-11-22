# Lựa chọn nhóm ở cấp lớp hoặc phương thức trong Spring Validation

## 1. Vấn đề: một bean có nhiều quy tắc, nhưng mỗi thao tác cần nhóm khác nhau

Trong Spring Framework, nhiều quy tắc kiểm tra có thể được gắn vào cùng một kiểu dữ liệu hoặc vào tham số/giá trị trả về của cùng một service. Tuy nhiên, quy tắc cần chạy lúc **tạo mới** có thể khác quy tắc lúc **cập nhật**; ngay cả những phương thức của cùng một service cũng có thể cần tập ràng buộc khác nhau.

Jakarta Validation gọi mỗi tập ràng buộc là **validation group**. Spring cung cấp annotation `@Validated` để lựa chọn group tại điểm gọi được Spring quản lý. Với **method validation thông qua AOP**, có hai vị trí rất quan trọng:

- **`@Validated(Create.class)` ở cấp lớp:** đánh dấu bean đủ điều kiện cho Spring method-validation proxy, đồng thời chọn nhóm mặc định cho các phương thức của bean.
- **`@Validated(Update.class)` ở cấp phương thức:** chọn nhóm riêng cho phương thức đó, **ghi đè** lựa chọn ở cấp lớp cho lời gọi này.

Ví dụ ý tưởng:

```java
@Service
@Validated(Create.class)              // Điểm kích hoạt AOP + group mặc định
public class AccountService {

    public void create(
            @NotBlank(groups = Create.class) String name) {
        // ...
    }

    @Validated(Update.class)          // Ghi đè group của class
    public void rename(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

Đoạn trên chỉ minh họa cách đặt annotation; phần sau có dự án hoàn chỉnh với mã nguồn và test. Điều kiện quan trọng: **chỉ gắn `@Validated` lên method của một Spring service thông thường không đủ để tự tạo AOP proxy**. Với cấu hình `MethodValidationPostProcessor` mặc định, cần `@Validated` ở type (hoặc meta-annotation tương đương) để bean được chọn cho method validation.

Bài này phân biệt chính xác ba việc thường bị trộn lẫn:

1. **Khai báo group trên constraint:** `@NotBlank(groups = Create.class)` cho biết constraint thuộc nhóm nào.
2. **Chọn group khi validate:** `@Validated(Create.class)` hoặc `validator.validate(bean, Create.class)` cho biết lần kiểm tra chạy nhóm nào.
3. **Kích hoạt điểm validation:** proxy cho service, argument resolver của MVC hoặc cơ chế method validation tích hợp trong MVC; annotation chọn nhóm không tự bảo đảm mọi lời gọi Java đều được kiểm tra.

Phạm vi phiên bản: Java 17+, Jakarta Validation 3.x, Spring Framework 6.x / Spring Boot 3.x. Đặc biệt lưu ý sự khác biệt từ Spring Framework **6.1** trở đi đối với controller.

## 2. Nền tảng: validation group thuộc Jakarta, @Validated thuộc Spring

### 2.1. Khai báo group bằng interface

Group trong Jakarta Validation là kiểu `Class<?>`, thông dụng nhất là các **marker interface** không có method:

```java
public interface Create {}
public interface Update {}
```

Đây là hai interface độc lập. Bản thân chúng không thực thi validation, không có logic nghiệp vụ, không tạo proxy và không xác định được Spring sẽ dùng group nào.

Gắn group vào constraint:

```java
@NotBlank(groups = Create.class)
private String password;

@NotBlank(groups = Update.class)
private String displayName;
```

Khi chọn `Create.class`, constraint đầu được xét. Khi chọn `Update.class`, constraint thứ hai được xét. Các constraint có thể cùng thuộc nhiều nhóm:

```java
@Size(min = 3, groups = {Create.class, Update.class})
private String username;
```

### 2.2. Nhóm Default là nhóm thực sự, không phải “tất cả”

Constraint không khai báo `groups` thuộc `jakarta.validation.groups.Default`:

```java
@NotNull                   // groups = Default.class
private String id;

@NotBlank(groups = Create.class)
private String password;
```

Khi gọi `validator.validate(bean)`, Jakarta Validation dùng nhóm `Default`. Khi gọi `validator.validate(bean, Create.class)`, **không tự động chạy thêm Default**. Tương tự, `@Validated(Create.class)` ở Spring không mặc nhiên kiểm tra mọi constraint thuộc Default.

Nếu cần cả hai nhóm, chỉ định:

```java
@Validated({Default.class, Create.class})
```

trong đó `Default` được import từ `jakarta.validation.groups.Default`. Khi chuyển sang lựa chọn group ở phương thức, hãy nêu lại **toàn bộ** các nhóm mong muốn; `@Validated` cấp method không tự cộng các nhóm khai báo ở class.

Một cách khác khi đúng ý nghĩa nghiệp vụ là group kế thừa:

```java
public interface Create extends Default {}
```

Lúc này chọn `Create` bao gồm các constraint thuộc group `Default` nhờ **group inheritance của Jakarta Validation**. Chỉ làm vậy nếu mọi trường hợp Create thực sự phải kiểm tra toàn bộ Default; không tạo kế thừa tùy tiện để né việc khai báo nhóm.

### 2.3. Group và group sequence không giống nhau

`@Validated({Default.class, Create.class})` chọn cả hai nhóm nhưng **không bảo đảm** tất cả lỗi Default được xét trước Create hay việc group thứ hai bị bỏ qua khi group thứ nhất có lỗi.

Khi bắt buộc kiểm tra theo **thứ tự giai đoạn** và dừng trước giai đoạn kế tiếp nếu giai đoạn hiện tại đã sai, dùng `@GroupSequence` của Jakarta Validation. Đó là chức năng khác với lựa chọn group cấp lớp/phương thức. Không dùng thứ tự phần tử trong mảng `@Validated` thay cho group sequence.

## 3. Cách Spring chọn nhóm ở cấp lớp và cấp phương thức

Trong **Spring-driven method validation bằng AOP**, quy tắc thông dụng là:

1. Spring xác định bean thuộc diện method validation nhờ `@Validated` ở type và một `MethodValidationPostProcessor` đang hoạt động.
2. Khi một lời gọi đi qua proxy, interceptor tìm `@Validated` trên phương thức đang được gọi.
3. Nếu phương thức có `@Validated`, dùng `value()` của annotation **phương thức**, kể cả mảng rỗng.
4. Nếu không có ở phương thức, tìm `@Validated` trên type/những vị trí hỗ trợ khác của bean.
5. Nếu không chọn nhóm tường minh, provider dùng nhóm `Default`.
6. Áp dụng nhóm được chọn cho ràng buộc trên **tham số**, và khi phương thức trả về, cho các ràng buộc trên **giá trị trả về**.

| Vị trí annotation | Nhóm chọn trong AOP service | Ý nghĩa |
| --- | --- | --- |
| `@Validated(Create.class)` ở lớp, method không có `@Validated` | `Create` | Dùng lựa chọn cấp lớp |
| `@Validated(Create.class)` ở lớp, `@Validated(Update.class)` ở method | `Update` | Method ghi đè class |
| `@Validated(Create.class)` ở lớp, `@Validated` ở method | `Default` | Method ghi đè bằng lựa chọn mặc định |
| `@Validated({Default.class, Create.class})` ở lớp, method không có annotation | `Default` và `Create` | Chọn rõ hai nhóm |
| Chỉ `@Validated(Update.class)` ở method của service, không có type-level `@Validated` | Chưa đủ điều kiện AOP | Annotation method không tự tạo pointcut/proxy |
| Không có `@Validated` trên service được tạo thủ công bằng `new` | Không tự có AOP | Lời gọi Java thuần không bị Spring intercept |

**“Ghi đè” ở đây là ghi đè việc chọn group khi thực thi, không sửa `groups` khai báo trên constraint.** Nếu một constraint thuộc `Create`, nó vẫn thuộc Create dù phương thức đang chạy group Update; chỉ đơn giản là lần validate ấy không chọn constraint đó.

**Cấp lớp không đồng nghĩa với ràng buộc cấp lớp:** `@Validated` đặt trên service là chọn group/kích hoạt method validation. Custom constraint `@Constraint` đặt trên DTO class là kiểm tra trạng thái của DTO. Hai khái niệm dùng từ “class-level” nhưng khác cơ chế.

## 4. Ví dụ Spring Boot chạy được: class default, method override và Default

Chúng ta xây dựng một Spring service có ba thao tác:

- `create` dùng group `Create` mặc định của class;
- `rename` dùng group `Update` ghi đè ở method;
- `check` dùng `@Validated` không có value để chọn lại group `Default`.

Các test gọi **Spring bean đã được proxy** và quan sát `ConstraintViolationException`. Không dùng HTTP ở phần này để tránh trộn cơ chế Spring MVC với method validation AOP.

### 4.1. Cấu trúc dự án

```text
validation-groups-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/com/example/groups/
    │   ├── GroupDemoApplication.java
    │   ├── Create.java
    │   ├── Update.java
    │   └── AccountService.java
    └── test/java/com/example/groups/
        └── AccountServiceValidationTest.java
```

Cài Java 17 trở lên và dùng Gradle wrapper của dự án. Tệp `settings.gradle`:

```groovy
rootProject.name = 'validation-groups-demo'
```

Tệp `build.gradle` (các phiên bản minh họa cụ thể thuộc dòng Spring Boot 3):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` cung cấp Jakarta Validation provider; `spring-boot-starter-aop` làm rõ dependency phục vụ cơ chế proxy. Với cấu hình tự động thông thường của Spring Boot 3, `MethodValidationPostProcessor` được đăng ký khi có Bean Validation provider hợp lệ. Nếu ứng dụng Spring Framework thuần không dùng Boot, cần cấu hình processor này tường minh.

### 4.2. Khởi động ứng dụng

Tệp `src/main/java/com/example/groups/GroupDemoApplication.java`:

```java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GroupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(GroupDemoApplication.class, args);
    }
}
```

Hai marker interface:

Tệp `src/main/java/com/example/groups/Create.java`:

```java
package com.example.groups;

public interface Create {}
```

Tệp `src/main/java/com/example/groups/Update.java`:

```java
package com.example.groups;

public interface Update {}
```

Nhóm của Jakarta Validation **không cần** annotation riêng trên interface. Việc chúng được dùng bởi `@NotBlank(groups = ...)` và `@Validated(...)` là đủ.

### 4.3. Service có lựa chọn group ở hai cấp

Tệp `src/main/java/com/example/groups/AccountService.java`:

```java
package com.example.groups;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Create.class)
public class AccountService {

    // Không có @Validated ở method => dùng Create từ class.
    public String create(
            @NotBlank(groups = Create.class) String username) {
        return "created:" + username;
    }

    // Group Update thay thế Create cho method này.
    @Validated(Update.class)
    public String rename(
            @NotBlank(groups = Update.class) String newName) {
        return "renamed:" + newName;
    }

    // Mảng group rỗng => chọn group Default.
    @Validated
    public String check(
            @NotBlank String token) {
        return "checked:" + token;
    }

    // Constraint @NotBlank ở Default KHÔNG chạy trong lời gọi
    // dùng nhóm Create từ class.
    public String defaultOnly(
            @NotBlank String description) {
        return "description:" + description;
    }
}
```

Những điểm cần quan sát:

- `create(" ")`: `@NotBlank(groups=Create.class)` thất bại.
- `rename(" ")`: method chọn Update, nên `@NotBlank(groups=Update.class)` thất bại.
- `check(" ")`: method `@Validated` không tham số chọn Default, nên `@NotBlank` thất bại.
- `defaultOnly(" ")`: method kế thừa Create từ class, nhưng `@NotBlank` không khai báo groups thuộc Default; ràng buộc này **không được chọn**. Ví dụ cố tình cho thấy một bẫy thiết kế, không khuyến khích bỏ kiểm tra dữ liệu trong ứng dụng thật.
- Khi dữ liệu hợp lệ, method hoàn thành và trả chuỗi thông thường. Khi có violation từ interceptor, thân method không chạy.

Không nên dùng `@Validated(Create.class)` ở lớp rồi nghĩ rằng mọi `@NotNull` hay `@NotBlank` không gắn group đều tự chạy. Phải quy định rõ Default hoặc group inheritance nếu mong muốn điều đó.

### 4.4. Unit/integration test qua Spring proxy

Tệp `src/test/java/com/example/groups/AccountServiceValidationTest.java`:

```java
package com.example.groups;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AccountServiceValidationTest {

    @Autowired
    private AccountService service;

    @Test
    void classLevelCreateGroupAppliesByDefault() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("created:alice", service.create("alice"));
    }

    @Test
    void methodLevelUpdateOverridesCreate() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.rename(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("renamed:anna", service.rename("anna"));
    }

    @Test
    void methodWithEmptyValidatedUsesDefault() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.check(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("checked:ok", service.check("ok"));
    }

    @Test
    void defaultConstraintIsNotImplicitlyAddedToCreateGroup() {
        assertEquals(
                "description: ",
                service.defaultOnly(" ")
        );
    }
}
```

Chạy trên hệ điều hành có shell POSIX:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Kỳ vọng:** bốn test thành công khi cấu hình Boot/AOP thông thường đang hoạt động. Ba test đầu dùng `assertThrows` vì Spring AOP method validation mặc định ném `jakarta.validation.ConstraintViolationException` khi tham số không hợp lệ. Test thứ tư xác nhận nhóm Default **không được cộng tự động** vào group Create. Không cần khẳng định thứ tự lỗi trong `Set<ConstraintViolation<?>>`; nó không được cam kết.

Với dự án bật chế độ `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, lỗi AOP có thể được báo bằng `org.springframework.validation.method.MethodValidationException` thay cho `ConstraintViolationException`. Cần điều chỉnh test/handler theo chính cấu hình ứng dụng, không coi mọi dự án Spring đều ném cùng exception.

### 4.5. Tại sao test phải gọi bean do Spring quản lý?

Nếu tự viết:

```java
AccountService service = new AccountService();
service.create(" ");
```

thì **không có Spring AOP proxy**: không thể suy ra `@Validated` sẽ tự chạy. Đoạn này chỉ tạo object Java thông thường; nó có thể trả `"created: "` vì thân method đơn giản nối chuỗi.

Tương tự, một method trong service gọi `this.rename(...)` thường **bỏ qua proxy** theo mô hình Spring AOP phổ biến, nên không kích hoạt interception của `rename` qua đường gọi nội bộ. Muốn method validation thực thi, hãy gọi qua Spring bean proxy ở boundary phù hợp; không dùng self-invocation làm điều kiện bảo vệ dữ liệu.

## 5. Khi nào dùng @Validated ở lớp, ở method hoặc ở tham số?

Cùng một annotation `@Validated` có thể xuất hiện tại ba vị trí (TYPE, METHOD, PARAMETER), nhưng **ngữ nghĩa phụ thuộc điểm tích hợp**.

### 5.1. Service: TYPE chọn mặc định, METHOD ghi đè

Ví dụ `AccountService` ở phần 4 minh họa cách dùng quen thuộc với `MethodValidationPostProcessor`:

```java
@Validated(Create.class)
@Service
class AccountService {

    public void create(
            @NotBlank(groups = Create.class) String name) {}

    @Validated(Update.class)
    public void update(
            @NotBlank(groups = Update.class) String name) {}
}
```

Đây là code minh họa cấu trúc, không phải một chương trình Java độc lập. Method-level `@Validated(Update.class)` chọn group cho method. **Không phải** cấu hình chỉ kiểm tra một tham số nhất định; nó ảnh hưởng việc kiểm tra các constraint của method được interceptor xử lý, bao gồm tham số và return value.

### 5.2. Controller @RequestBody: PARAMETER chọn nhóm cho object

Trong Spring MVC, `@Validated(Create.class)` trực tiếp trên `@RequestBody` hoặc `@ModelAttribute` là một **validation hint cho đối tượng vừa bind**:

```java
@PostMapping("/accounts")
public ResponseEntity<Void> create(
        @Validated(Create.class) @RequestBody AccountRequest request) {
    return ResponseEntity.noContent().build();
}
```

Đây là đoạn **method controller minh họa**; `AccountRequest` giả định có các constraint gắn group Create. Với tham số command object và không có constraint trực tiếp trên các tham số khác đòi hỏi method validation, Spring MVC sẽ validate object theo Create và có thể báo `MethodArgumentNotValidException` (nếu không có `BindingResult` ngay sau).

Với một endpoint cập nhật:

```java
@PutMapping("/accounts/{id}")
public ResponseEntity<Void> update(
        @PathVariable long id,
        @Validated(Update.class) @RequestBody AccountRequest request) {
    return ResponseEntity.noContent().build();
}
```

Đây cũng là đoạn method của một controller, không phải chương trình độc lập. Mỗi tham số body có thể chọn group khác nhau tại thời điểm bind. **Không cần đặt `@Validated(Create.class)` trên controller class chỉ để chọn group cho `@RequestBody`.**

Phân biệt:

| Cách viết | Vị trí | Ý nghĩa chính |
| --- | --- | --- |
| `@Valid @RequestBody Dto dto` | Tham số controller | Validate DTO theo Default (trong ngữ cảnh điển hình) |
| `@Validated(Create.class) @RequestBody Dto dto` | Tham số controller | Validate DTO theo Create khi MVC bind |
| `@Validated(Create.class)` trên service class | Type | Kích hoạt AOP pointcut và chọn group mặc định cho method validation |
| `@Validated(Update.class)` trên service method | Method | Ghi đè group khi method được proxy validate |
| `@Validated(Create.class)` trên controller class | Type | Có thể chuyển controller sang AOP method validation; cần cân nhắc Spring MVC 6.1+ |

`@Valid` là annotation Jakarta, dùng cho cascaded validation; nó không có tham số chọn groups. `@Validated` là Spring annotation cho validation hint và method validation group selection. Dùng cả hai trên cùng một tham số nếu không cần là thừa và dễ khiến ý định chọn group mơ hồ.

### 5.3. Spring MVC 6.1+: method validation tích hợp khác AOP

**Từ Spring Framework 6.1, Spring MVC hỗ trợ method validation tích hợp cho handler method**, không cần AOP proxy. Nó được kích hoạt khi có constraint trực tiếp trên tham số hoặc return value, ví dụ:

```java
@GetMapping("/quantities")
public String quantities(
        @RequestParam @Min(1) int quantity) {
    return "quantity=" + quantity;
}
```

Đây là đoạn method controller minh họa (import `@GetMapping`, `@RequestParam`, `@Min` tương ứng). `@Min(1)` là constraint trực tiếp lên tham số: MVC dùng built-in method validation, có thể ném `HandlerMethodValidationException`. Nếu chỉ có `@Valid @RequestBody` trên command object (và không có constraint trực tiếp yêu cầu method validation), đường đi thông thường là validation ở argument resolver với `MethodArgumentNotValidException`.

**Cảnh báo quan trọng về cấp lớp:** Khi controller có `@Validated` ở TYPE, Spring MVC có thể để method validation đi qua **AOP proxy**. Tài liệu Spring khuyên **bỏ `@Validated` cấp lớp trên controller** nếu muốn dùng cơ chế built-in MVC 6.1+. Vì vậy **không bê nguyên quy tắc “đặt `@Validated` ở class để bật AOP” của service sang mọi controller** mà không kiểm tra phiên bản và cơ chế mong muốn.

Spring MVC hỗ trợ xác định group cho built-in method validation (xem `MethodValidator#determineValidationGroups` và `MethodValidationAdapter`); annotation trên method có thể cung cấp group. Nhưng annotation ở method controller không tự đồng nghĩa với việc nó sẽ là AOP pointcut của service. Hãy kiểm thử theo **đường validation thực tế**, đặc biệt khi codebase có class-level `@Validated` lâu đời.

## 6. Lựa chọn group ảnh hưởng đến tham số, return value và object lồng nhau

### 6.1. Trực tiếp trên tham số phương thức

```java
@Service
@Validated(Create.class)
public class InventoryService {

    public String reserve(
            @NotBlank(groups = Create.class) String sku,
            @Min(value = 1, groups = Create.class) int quantity) {
        return sku + ":" + quantity;
    }
}
```

Đoạn này minh họa method validation AOP: chọn group Create sẽ áp dụng cho **cả hai** constraint tham số thuộc Create. Nó không có ý nghĩa “mỗi tham số chọn một group riêng” trong một lần validate executable thông thường.

### 6.2. Constraint trên giá trị trả về

Jakarta Validation hỗ trợ constraint trên return value:

```java
@Service
@Validated(Create.class)
public class CodeService {

    @NotBlank(groups = Create.class)
    public String generateCode() {
        return "";
    }
}
```

Đoạn code minh họa này cố ý trả chuỗi rỗng: với proxy và group Create, lỗi được phát hiện **sau khi thân phương thức chạy, trước khi kết quả hợp lệ được trả về cho caller**. Vì vậy các side effect thực hiện trong method có thể đã xảy ra trước khi kiểm tra return value thất bại; không dùng return validation để thay thế bất biến transaction hoặc điều kiện nghiệp vụ ở nơi ghi dữ liệu.

### 6.3. @Valid và group của object lồng nhau

Ví dụ:

```java
public record Profile(
        @NotBlank(groups = Create.class) String displayName
) {}

@Service
@Validated(Create.class)
public class ProfileService {

    public void register(@Valid Profile profile) {
        // ...
    }
}
```

Đây là hai type minh họa, cần import `jakarta.validation.Valid` và các annotation Java/Spring tương ứng. Khi method validation trên service chọn Create, group đó thường được **truyền xuống object Profile** qua `@Valid` (cascading). Nhờ vậy `displayName` thuộc Create cũng được kiểm tra.

Nếu object lồng nhau phải dùng group khác với object cha, Jakarta Validation có `@ConvertGroup` trên vị trí cascade:

```java
public record Registration(
        @Valid
        @ConvertGroup(from = Create.class, to = Detailed.class)
        Profile profile
) {}
```

`@ConvertGroup` ở đây là **tính năng chuẩn Jakarta**, nhưng ví dụ ngắn giả định đã khai báo group `Detailed` và `Profile` có các constraint theo group đó. Không đặt `@ConvertGroup` đơn độc mà thiếu `@Valid` trên association; provider có thể ném `ConstraintDeclarationException`.

### 6.4. @Validated không thay đổi sự thật về loại constraint

Nếu đã gắn `@NotNull(groups=Update.class)` vào một tham số, việc thêm `@Validated(Create.class)` trên method **không chuyển** constraint đó sang Create. Chỉ có các group được yêu cầu và các quy tắc kế thừa/chuyển group theo Jakarta Validation mới xác định nó có được kiểm tra hay không.

Vì thế khi debug “đã thêm @Validated nhưng constraint không chạy”, kiểm tra **cả hai phía**: `groups` trên constraint và `value()` trên điểm lựa chọn group.

## 7. Các bẫy liên quan đến proxy, kế thừa và thiết kế API

### 7.1. Chỉ đánh dấu method mà quên type

```java
@Service
public class WronglyConfiguredService {

    @Validated(Update.class)
    public void rename(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

Đây là đoạn phản ví dụ để chỉ ra lỗ hổng cấu hình. Với **MethodValidationPostProcessor AOP mặc định**, annotation chỉ ở method **không phải pointcut** chọn bean. Vì vậy một lời gọi bên ngoài có thể không được method validation kiểm tra. Cần `@Validated` ở cấp type để chọn bean, rồi method-level annotation để ghi đè nhóm.

### 7.2. Lời gọi nội bộ không đi qua proxy

```java
@Service
@Validated(Create.class)
public class SelfCallService {

    public void outer() {
        inner(" ");            // self-invocation
    }

    @Validated(Update.class)
    public void inner(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

Đây là phản ví dụ: `outer()` gọi thẳng `inner()` trên cùng object, theo Spring proxy AOP thông thường nên không có lần interception riêng cho `inner`. Gọi `inner(" ")` từ một bean khác qua proxy mới là đường mong đợi. Không dựa vào validation AOP để bảo vệ một method có thể được gọi nội bộ qua `this`.

### 7.3. Private/final method và đối tượng tạo bằng new

Spring AOP proxy phải có khả năng can thiệp lời gọi method. Các phương thức `private` không được proxy intercept; CGLIB không thể override `final` method/class. Với JDK dynamic proxy, caller phải đi qua interface method được proxy. Các chi tiết về loại proxy và implementation class có thể ảnh hưởng việc đọc annotation; kiểm thử bằng Spring context thật nếu cấu trúc interface/phân cấp phức tạp.

### 7.4. Method override trong Java inheritance

Jakarta Validation định nghĩa quy tắc nghiêm ngặt cho constraint của tham số phương thức khi override/implement: không được tùy tiện **tăng precondition** (ví dụ thêm constraint tham số vào phương thức triển khai nếu hợp đồng cha không khai báo), nhằm giữ nguyên nguyên tắc thay thế Liskov. Vi phạm có thể dẫn tới `ConstraintDeclarationException` trong provider.

Group selection bằng Spring `@Validated` không xóa các quy định Jakarta về method constraint inheritance. Nếu code đặt constraint trên interface nhưng lựa chọn group trên implementation, hãy xác minh sự kết hợp annotation đúng với Spring/proxy/provider đang dùng và test qua interface/caller thật.

### 7.5. Exception và xử lý lỗi khác theo đường validation

| Điểm validation | Trường hợp phổ biến | Exception thường gặp |
| --- | --- | --- |
| Jakarta API trực tiếp | `validator.validate(bean, groups...)` | Trả `Set<ConstraintViolation<?>>`; không tự ném khi chỉ có violation |
| Spring service AOP | `MethodValidationPostProcessor` mặc định | `ConstraintViolationException` |
| Spring service AOP thích nghi lỗi | `setAdaptConstraintViolations(true)` | `MethodValidationException` |
| MVC validate DTO riêng | `@Validated(Group.class) @RequestBody Dto` | `MethodArgumentNotValidException` |
| MVC 6.1+ built-in method validation | Constraint trực tiếp trên handler params/return | `HandlerMethodValidationException` |
| Binding/deserialize | JSON không hợp lệ hoặc kiểu không chuyển được | Exception binding/HTTP message riêng; có thể xảy ra trước Bean Validation |

Dạng exception không quyết định một constraint thuộc group nào. Đó là biểu hiện của **đường tích hợp** (Spring AOP, Spring MVC hay Jakarta API thuần). Cần chuẩn hóa phản hồi dựa trên API của từng exception thay vì assume mọi group validation đều tạo cùng một `BindingResult`.

## 8. Chọn một hay nhiều nhóm trong thực tế

### 8.1. Create và Update có quy tắc dùng chung

Giả sử:

```java
public interface Create {}
public interface Update {}

public record AccountRequest(
        @NotBlank(groups = {Create.class, Update.class}) String username,
        @NotNull(groups = Create.class) String initialPassword,
        @NotBlank(groups = Update.class) String updateReason
) {}
```

Ở luồng Create, `username` và `initialPassword` được kiểm tra. Ở luồng Update, `username` và `updateReason` được kiểm tra. Vì `username` thuộc cả hai group, không cần duplicate annotation.

Nếu muốn các constraint chuẩn như `@Email` luôn chạy, có thể gắn chúng vào cả hai nhóm hoặc thiết kế `Default` phù hợp. **Không tự động cộng Default** chỉ vì mong muốn “các rule cơ bản luôn chạy”.

### 8.2. Nhiều nhóm cùng một method

```java
@Validated({Default.class, Update.class})
public void update(
        @NotBlank String id,
        @NotBlank(groups = Update.class) String reason) {
    // ...
}
```

Đây là method minh họa trong một bean có `@Validated` cấp type. Lần kiểm tra chọn **hai nhóm** để bao phủ cả `id` thuộc Default và `reason` thuộc Update. Mảng nhiều phần tử không yêu cầu provider đánh giá theo thứ tự mảng.

### 8.3. Tách group theo thao tác hay theo tầng?

Group hợp lý khi **cùng cấu trúc dữ liệu** có nhiều tập ràng buộc độc lập, ví dụ Create/Update/Publish hoặc Draft/Submit. Tuy nhiên nếu DTO của hai nghiệp vụ khác nhau về ý nghĩa, cấu trúc và hợp đồng API, **hai DTO chuyên biệt** có thể rõ ràng hơn một DTO duy nhất với hàng chục annotation `groups`. Cân nhắc:

- Group có giúp biểu đạt được một chính sách kiểm tra tái sử dụng không?
- Mọi đường gọi có chọn đúng group, kể cả job và message consumer?
- Các ràng buộc Default có bị bỏ sót hay không?
- Client có nhận error code nhất quán cho mỗi endpoint?
- Việc mở rộng nhóm có làm method-level `@Validated` hiện tại vô tình bỏ mất constraint mới?

Đừng coi group như cơ chế **ủy quyền**. Validation groups quyết định một tập constraint được chạy; chúng không xác thực người dùng, phân quyền hay bảo vệ resource.

## 9. Cách kiểm thử hành vi chọn nhóm chặt chẽ

Một bộ test nên bao phủ **nhóm chọn, nhóm không chọn, proxy và exception**:

| Kiểm thử | Kết quả muốn chứng minh |
| --- | --- |
| Gọi method không có `@Validated` riêng qua bean có class `@Validated(Create.class)` | Create được chọn |
| Gọi method có `@Validated(Update.class)` | Update được chọn, không ngầm cộng Create |
| Gọi method có `@Validated` rỗng | Default được chọn |
| Constraint Default dưới class Create-only | Không tự chạy |
| Method có `@Validated({Default.class, Update.class})` | Cả hai nhóm được xét |
| Gọi bean do `new` tạo, không đi qua Spring proxy | Không kỳ vọng AOP tự chạy |
| Service tự gọi method qua `this` | Không kỳ vọng interception của method bên trong |
| `@Valid` trên tham số object lồng nhau | Group cascade đúng hoặc được `@ConvertGroup` theo thiết kế |
| Handler MVC có `@RequestBody` và constraint method | Phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException` |
| Dự án bật `setAdaptConstraintViolations(true)` | Handler/test được điều chỉnh đúng exception |

Để tránh test yếu, không chỉ kiểm tra `getConstraintViolations().size()` khi có nhiều constraint: nên xác minh **property path**, annotation type hoặc message template phù hợp. Không dựa vào thứ tự của `Set<ConstraintViolation<?>>` hay chuỗi message đã được bản địa hóa. Khi kiểm tra lựa chọn group trong service, test phải gọi qua bean `@Autowired`; nếu chỉ gọi `new AccountService()`, bài test không kiểm chứng Spring AOP.

Nếu không thấy exception dù đầu vào sai, kiểm tra theo thứ tự:

1. Bean có thật sự do Spring tạo và được gọi qua proxy?
2. `MethodValidationPostProcessor` đã đăng ký, Bean Validation provider đã có?
3. Annotation `@Validated` có ở **type** của service cần AOP không?
4. Method có ghi đè group ở cấp method không? Nó có thuộc Default hay group khác?
5. `groups` khai báo trên constraint có trùng với group được chọn không?
6. Phương thức có `public`, không bị giới hạn bởi proxy/final/private, hay bị self-invocation không?
7. Nếu ở controller, có đang dùng Spring MVC 6.1+ built-in validation, argument validation hay AOP controller?
8. Test có dùng đúng exception type/bean instance/version không?

## 10. Lỗi phổ biến cần tránh

**Lỗi 1: Chỉ đặt `@Validated(Update.class)` trên service method rồi chờ nó tự được AOP kiểm tra.** Trong Spring-driven AOP method validation mặc định, annotation method chỉ **ghi đè nhóm**; type-level `@Validated` là phần quan trọng để bean được chọn.

**Lỗi 2: Nghĩ method-level group cộng với class-level group.** `@Validated(Update.class)` ở method không tương đương `@Validated({Create.class, Update.class})` khi class đang chọn Create. Nó thay thế lựa chọn của type cho method đó.

**Lỗi 3: Nhầm `Default` với “tất cả nhóm”.** Constraint không gắn group thuộc Default. Khi chọn Create, Default không tự được xét; muốn cả hai thì chọn rõ hoặc thiết kế kế thừa phù hợp.

**Lỗi 4: Dùng `@Valid` để chọn nhóm.** `@Valid` kích hoạt cascade và được framework dùng để bắt đầu bean validation ở boundary, nhưng annotation Jakarta này không nhận đối số group. `@Validated(SomeGroup.class)` là Spring-specific selection/hint.

**Lỗi 5: Gắn `@Validated` cấp class cho mọi MVC controller vì service cũng làm vậy.** Spring MVC 6.1+ có method validation tích hợp; class-level `@Validated` có thể chuyển sang AOP và thay đổi exception path. Hãy chọn cơ chế phù hợp thay vì phối trộn không chủ đích.

**Lỗi 6: Nhầm validation cho `@RequestBody` với validation trực tiếp trên tham số method.** `@Validated(Group.class) @RequestBody Dto` được MVC dùng khi bind command object; `@Min` trực tiếp trên `@RequestParam int` dẫn đến method validation tích hợp trên MVC 6.1+.

**Lỗi 7: Tưởng test dùng `new Service()` chứng minh được method validation.** Cần gọi qua Spring-managed bean/proxy.

**Lỗi 8: Thêm constraint lên tham số phương thức override từ interface một cách tùy tiện.** Jakarta Validation có quy tắc method inheritance; một số khai báo làm provider ném `ConstraintDeclarationException`.

**Lỗi 9: Dùng tên nhóm lẫn với bước nghiệp vụ.** `Create`/`Update` là tập ràng buộc, không phải cơ chế bảo vệ transaction, authorization, idempotency hay kiểm tra uniqueness trong database.

**Lỗi 10: Giả định mọi lỗi validation được báo cùng exception.** Dựa vào chính boundary (Jakarta API, Spring AOP, MVC argument resolver, MVC built-in) để chọn cách handle; không đoán từ nhóm đã chọn.

## 11. Checklist khi triển khai

1. Định nghĩa nhóm thành marker interface có tên thể hiện nghiệp vụ.
2. Khai báo rõ `groups` trên từng constraint và quyết định constraint nào thuộc `Default`.
3. Với Spring service AOP, đặt `@Validated(...)` ở type để kích hoạt validation và chọn mặc định.
4. Chỉ đặt `@Validated(...)` ở method khi thực sự cần **ghi đè** nhóm của type; khai báo đầy đủ nhóm muốn chạy.
5. Phân biệt annotation trên method service với annotation trên **tham số command object của Spring MVC**.
6. Với controller Spring MVC 6.1+, cân nhắc cơ chế built-in method validation và tránh dùng type-level `@Validated` chỉ vì thói quen.
7. Gọi service qua Spring proxy, không phụ thuộc self-invocation hoặc method không thể intercept.
8. Kiểm thử ít nhất một violation cho mỗi nhóm, một constraint Default, một method override và cách xử lý exception thực tế.
9. Sử dụng group sequence chỉ khi cần thứ tự; dùng group conversion khi cần thay nhóm trong cascade, không trộn chúng với quy tắc ghi đè giữa class và method.
10. Nếu thay đổi group mặc định của class, rà soát mọi method chưa khai báo `@Validated` riêng vì phạm vi constraint được chọn của chúng có thể thay đổi.

**Điểm cốt lõi:** Trong Spring AOP method validation, `@Validated` ở **lớp** quyết định bean được proxy và nhóm mặc định; `@Validated` ở **phương thức** ghi đè nhóm cho lời gọi đó. Trong Spring MVC, `@Validated` trên **tham số** lại là hint để validate command object, còn method validation tích hợp từ 6.1 có đường kích hoạt và exception riêng. Đọc đúng vị trí annotation, nhóm trên constraint và đường gọi qua framework là cách tránh bỏ sót validation.

## Tài liệu tham khảo

- [Spring Framework — `@Validated` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html): nhóm ở type/method và vai trò pointcut.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html): `MethodValidationPostProcessor`, AOP, ngoại lệ method validation.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): built-in MVC validation 6.1+, lưu ý controller class-level `@Validated`.
- [Jakarta Validation — Groups](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/validation/groups/package-summary): `Default`, `@ConvertGroup` và cơ chế nhóm.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): group inheritance, group sequence, method constraint inheritance.
