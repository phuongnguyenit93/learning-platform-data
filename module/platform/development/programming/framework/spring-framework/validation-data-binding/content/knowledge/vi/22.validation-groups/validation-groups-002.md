# Áp dụng constraint cho một hoặc nhiều nhóm trong Jakarta Bean Validation và Spring

## 1. Tại sao cần validation groups?

Một đối tượng Java có thể được dùng trong nhiều ngữ cảnh: tạo mới, cập nhật, xuất bản, thanh toán hoặc phê duyệt. Các trường bắt buộc ở ngữ cảnh này chưa chắc bắt buộc ở ngữ cảnh khác. Ví dụ:

- **Tạo tài khoản**: mã định danh do hệ thống cấp, client không được gửi `id`; email phải hợp lệ.
- **Cập nhật tài khoản**: `id` phải có; email tiếp tục phải hợp lệ.
- **Xuất bản hồ sơ**: phần giới thiệu phải đạt độ dài tối thiểu.
- **Mọi trường hợp**: tên hiển thị không được trống.

Nếu tách một DTO cho mỗi thao tác thì đôi khi dễ kiểm soát nhất. Nhưng khi một bean dùng chung có thật sự nhiều bộ quy tắc, **validation groups** cho phép chọn một **tập con constraint** tùy ngữ cảnh, thay vì chạy tất cả constraint vô điều kiện.

Hai việc cần phân biệt:

1. **Gán một constraint cho nhóm nào?** — dùng thuộc tính `groups` trên annotation như `@NotBlank(groups = Create.class)`.
2. **Chạy kiểm tra nhóm nào?** — gọi `Validator.validate(bean, Create.class)`, hoặc dùng `@Validated(Create.class)` tại điểm tích hợp Spring.

Chỉ khai báo nhóm **không tự chạy validation**. Cần provider Jakarta Bean Validation (ví dụ Hibernate Validator), và một điểm gọi validation thực sự.

Bài này tập trung vào cách một constraint thuộc **một hoặc nhiều nhóm**, quan hệ với nhóm `Default`, cách chỉ định nhiều nhóm khi kiểm tra, Spring MVC, nhóm trên object con, thứ tự với `@GroupSequence` và cách kiểm thử.

> Ví dụ dựa trên `jakarta.validation.*` (Jakarta Bean Validation 3.x), Java 17+, Spring Framework 6+/Spring Boot 3.x. Dự án Spring Boot 2.x thường dùng `javax.validation.*`; không trộn namespace cũ và mới trong cùng chương trình.

## 2. Group là gì? Cách định nghĩa marker interface

Trong Jakarta Bean Validation, group thường được biểu diễn bằng **Java interface** không có phương thức:

```java
package example;

public final class Groups {
    private Groups() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
}
```

Các interface này là **marker**: chúng không thực thi thuật toán kiểm tra. Chúng là tên ngữ cảnh để provider quyết định constraint nào được áp dụng.

Có thể định nghĩa group ở top-level hoặc lồng trong một class chứa các constant/nhóm, như `Groups.Create.class`. Dùng những tên nghiệp vụ rõ nghĩa (`Create`, `Update`, `Publish`) thay vì tên phụ thuộc UI hoặc endpoint không ổn định.

Không dùng chuỗi `"Create"` để định nghĩa nhóm. Kiểu đầu vào của `groups` là một mảng class, thường là `Class<?>[]`, vì vậy cách gọi là:

```java
@NotNull(groups = Groups.Create.class)
@NotBlank(groups = {Groups.Create.class, Groups.Update.class})
```

Ở dòng thứ hai, một **constraint declaration** duy nhất được gắn với **hai nhóm**. Không có quy tắc "chỉ được một nhóm" hoặc yêu cầu viết cùng annotation hai lần. Nhóm chỉ xác định constraint được **chọn** khi validate; nội dung kiểm tra của `@NotBlank` không đổi.

### 2.1. Nhóm Default không phải "tất cả"

Jakarta cung cấp `jakarta.validation.groups.Default`.

- Khi khai báo constraint **không có thuộc tính `groups`**, constraint thuộc nhóm `Default`.
- `@NotBlank String name;` tương đương về nhóm với `@NotBlank(groups = Default.class) String name;`.
- Khi gọi `validator.validate(bean)` **không truyền nhóm**, mặc định kiểm tra `Default`.
- Khi gọi `validator.validate(bean, Create.class)`, các constraint **chỉ thuộc Default** thông thường **không tự chạy**.
- Khi gọi `validator.validate(bean, Default.class, Create.class)`, chạy tập constraint thuộc cả hai nhóm (với quy tắc group inheritance/sequence liên quan).

Điểm quan trọng nhất: `Default` **không đồng nghĩa "áp dụng trong mọi ngữ cảnh"**. Nếu logic Create/Update luôn phải áp dụng một quy tắc chung, ta phải truyền cả Default lúc validate, hoặc đưa quy tắc đó vào nhóm dùng chung/nhóm nghiệp vụ tương ứng.

## 3. Áp dụng constraint cho một nhóm hoặc nhiều nhóm

Ví dụ một DTO có bốn quy tắc khác nhau:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;

record AccountRequest(
    // Chỉ thuộc Default vì không ghi groups:
    @NotBlank String displayName,

    // Tạo mới không được gửi id; cập nhật phải có id:
    @Null(groups = Groups.Create.class)
    @NotNull(groups = Groups.Update.class)
    Long id,

    // Hai constraint, mỗi constraint thuộc cả hai nhóm:
    @NotBlank(groups = {
        Groups.Create.class, Groups.Update.class
    })
    @Email(groups = {
        Groups.Create.class, Groups.Update.class
    })
    String email,

    // Chỉ dùng khi xuất bản:
    @Size(min = 10, groups = Groups.Publish.class)
    String about
) {}
```

Đây là fragment minh họa Java 17+ với `Groups` đã định nghĩa. Đọc từng phần:

- `displayName`: `@NotBlank` thuộc **Default**; một lượt validate chỉ nhóm `Create` sẽ không kiểm tra constraint này.
- `id`: trong nhóm `Create` thì phải **null** do `@Null`; trong nhóm `Update` thì phải **khác null** do `@NotNull`. Đây là hai constraint độc lập trên cùng field với các nhóm khác nhau.
- `email`: cả `@NotBlank` lẫn `@Email` thuộc `Create` **và** `Update`. Mỗi constraint có thể được áp dụng khi một trong hai nhóm được yêu cầu.
- `about`: `@Size(min = 10)` chỉ thuộc `Publish`. Khi kiểm tra tạo mới, mô tả ngắn chưa gây lỗi từ constraint này.

Không hiểu nhầm rằng viết `groups = {Create.class, Update.class}` có nghĩa "chỉ kiểm tra khi cả hai nhóm cùng được yêu cầu". Nó có nghĩa constraint nằm trong **mỗi nhóm được liệt kê**.

### 3.1. Bảng chọn constraint theo nhóm

| Constraint | Default | Create | Update | Publish |
| --- | :---: | :---: | :---: | :---: |
| `displayName: @NotBlank` | ✓ | — | — | — |
| `id: @Null` | — | ✓ | — | — |
| `id: @NotNull` | — | — | ✓ | — |
| `email: @NotBlank` | — | ✓ | ✓ | — |
| `email: @Email` | — | ✓ | ✓ | — |
| `about: @Size(min=10)` | — | — | — | ✓ |

Bảng này giả sử các marker interface không có quan hệ kế thừa, chưa có `@GroupSequence` hoặc chuyển nhóm (`@ConvertGroup`). Các cơ chế đó có thể ảnh hưởng tập constraint thực sự được chạy và sẽ được giải thích bên dưới.

### 3.2. Một giá trị, nhiều nhóm hợp lệ

Cho đối tượng có dữ liệu:

```java
var account = new AccountRequest(
    " ",            // displayName sai Default
    -5L,            // id sai Create, đúng Update
    "not-an-email", // email sai Create và Update
    "short"         // about sai Publish
);
```

Kỳ vọng theo từng lượt:

| Nhóm được yêu cầu | Property path bị lỗi |
| --- | --- |
| Không truyền nhóm / `Default.class` | `displayName` |
| `Create.class` | `id`, `email` |
| `Update.class` | `email` |
| `Publish.class` | `about` |
| `Create.class, Publish.class` | `id`, `email`, `about` |
| `Default.class, Create.class` | `displayName`, `id`, `email` |

Một constraint có thể được đánh dấu thuộc nhiều nhóm, nhưng trong cùng một lượt validate của cùng đường đi, provider không được trả lại cùng một violation chỉ vì nhóm đó được yêu cầu lặp ở nhiều nhánh. Không xây dựng UI phụ thuộc vào thứ tự duyệt của `Set<ConstraintViolation<?>>`.

## 4. Sự khác nhau giữa gán groups và gọi validate()

Mọi constraint chuẩn có thuộc tính `groups`. Cú pháp truyền nhóm khi dùng Jakarta Validator:

```java
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

void check(Validator validator, AccountRequest account) {
    validator.validate(account); // tương đương Default

    validator.validate(account, Groups.Create.class);

    validator.validate(
            account,
            Groups.Create.class,
            Groups.Update.class);

    validator.validate(
            account,
            Default.class,
            Groups.Create.class);
}
```

Đây là **fragment** minh họa lời gọi API. Các `validate(...)` trả về `Set<ConstraintViolation<AccountRequest>>`, không tự ném exception vì dữ liệu sai theo mặc định.

Cần nhớ ba điều:

1. `validate(object, A.class, B.class)` lựa chọn hợp các constraint áp dụng cho các nhóm được yêu cầu; nó không yêu cầu từng constraint phải thuộc **đồng thời A và B**.
2. `validate(object, A.class, B.class)` **không bảo đảm kiểm tra A trước B**. Muốn thứ tự và chỉ sang B khi A pass thì dùng `@GroupSequence`.
3. Nếu chỉ yêu cầu `A.class` thì `Default` không tự được thêm, trừ khi A kế thừa Default, một group sequence liên quan hoặc quy tắc đặc biệt khác được định nghĩa rõ.

Có thể gọi `validator.validateProperty(bean, "email", Groups.Create.class)` để kiểm tra một thuộc tính, hoặc `validateValue(AccountRequest.class, "email", value, Groups.Create.class)` để kiểm tra giá trị giả định mà chưa tạo bean. Những API này không thay thế việc validate toàn bộ đồ thị khi ràng buộc cần nhiều trường hoặc cascade.

## 5. Ví dụ Java 17+ chạy được bằng Maven và Hibernate Validator

Ví dụ độc lập này sử dụng đúng các nhóm ở phần trên, in **đường dẫn vi phạm đã sắp xếp** để kết quả không phụ thuộc thứ tự của `Set` do provider trả về.

Thư mục:

```text
groups-demo/
├── pom.xml
└── src/
    ├── main/java/example/GroupValidationDemo.java
    └── test/java/example/GroupValidationDemoTest.java
```

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>groups-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` là provider, còn `expressly` cung cấp Jakarta EL implementation thường dùng cho nội suy thông điệp. Trong ứng dụng Spring Boot, nên dùng `spring-boot-starter-validation` và BOM của Boot thay vì tùy tiện pin các phiên bản thư viện như ví dụ standalone này.

### 5.2. File src/main/java/example/GroupValidationDemo.java

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;
import jakarta.validation.GroupSequence;

public final class GroupValidationDemo {
    private GroupValidationDemo() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}

    // Default được kiểm tra trước Publish nếu yêu cầu OrderedPublish.
    @GroupSequence({Default.class, Publish.class})
    public interface OrderedPublish {}

    public record Account(
            @NotBlank String displayName,

            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @Email(groups = {Create.class, Update.class})
            String email,

            @Size(min = 10, groups = Publish.class)
            String about) {
    }

    public static Account invalidExample() {
        return new Account(
                " ", -5L, "not-an-email", "short");
    }

    public static Set<String> invalidFields(
            Validator validator,
            Account account,
            Class<?>... groups) {

        Set<ConstraintViolation<Account>> violations =
                validator.validate(account, groups);

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    private static void print(
            String label,
            Validator validator,
            Account account,
            Class<?>... groups) {

        String names = invalidFields(validator, account, groups)
                .stream()
                .sorted()
                .collect(Collectors.joining(","));

        System.out.println(label + "=" + names);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            Account account = invalidExample();

            print("default", validator, account);
            print("create", validator, account, Create.class);
            print("update", validator, account, Update.class);
            print("publish", validator, account, Publish.class);
            print("create+publish", validator, account,
                    Create.class, Publish.class);
            print("default+create", validator, account,
                    Default.class, Create.class);
            print("ordered-publish", validator, account,
                    OrderedPublish.class);
        }
    }
}
```

Chạy ở thư mục `groups-demo` (Java 17+, Maven có kết nối để lấy dependency hoặc dependency đã cache):

```bash
mvn -q test
mvn -q exec:java -Dexec.mainClass=example.GroupValidationDemo
```

Kết quả **từ các lời gọi println**, không tính log Maven/provider:

```text
default=displayName
create=email,id
update=email
publish=about
create+publish=about,email,id
default+create=displayName,email,id
ordered-publish=displayName
```

Dòng cuối phản ánh `@GroupSequence`: `Default` có lỗi `displayName`, vì thế `Publish` chưa được xét khi validate nhóm `OrderedPublish`. Nếu chỉ validate hai nhóm tách rời bằng `Default.class, Publish.class` thì cả hai constraint sẽ được xét mà **không bảo đảm thứ tự**.

Trong demo, email chỉ có `@Email`. Đối với ứng dụng thật, `@Email` không tự bảo đảm chuỗi khác null hoặc khác rỗng: nếu email bắt buộc thì thêm `@NotBlank(groups={Create.class,Update.class})`.

## 6. Unit test JUnit 5 chứng minh nhóm nào chạy

**File `src/test/java/example/GroupValidationDemoTest.java`:**

```java
package example;

import java.util.Set;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GroupValidationDemoTest {

    private static Set<String> fields(
            Validator validator, Class<?>... groups) {
        return GroupValidationDemo.invalidFields(
                validator, GroupValidationDemo.invalidExample(), groups);
    }

    @Test
    void picksOneGroupAtATime() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("displayName"),
                    fields(validator));
            assertEquals(Set.of("email", "id"),
                    fields(validator, GroupValidationDemo.Create.class));
            assertEquals(Set.of("email"),
                    fields(validator, GroupValidationDemo.Update.class));
            assertEquals(Set.of("about"),
                    fields(validator, GroupValidationDemo.Publish.class));
        }
    }

    @Test
    void includesAllRequestedGroupsWithoutOrdering() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("email", "id", "about"),
                    fields(validator,
                            GroupValidationDemo.Create.class,
                            GroupValidationDemo.Publish.class));

            assertEquals(Set.of("displayName", "email", "id"),
                    fields(validator,
                            Default.class,
                            GroupValidationDemo.Create.class));
        }
    }

    @Test
    void orderedGroupSkipsNextGroupOnFailure() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("displayName"),
                    fields(validator,
                            GroupValidationDemo.OrderedPublish.class));
        }
    }
}
```

Test này dùng chính `pom.xml` ở mục 5, gồm JUnit Jupiter và Maven Surefire. Các assertion so sánh **tập tên thuộc tính**, không so sánh thứ tự `ConstraintViolation` hoặc chuỗi tiếng Anh có thể thay đổi theo locale.

Trong thực tế hãy bổ sung thêm test cho đối tượng tạo mới hợp lệ, cập nhật hợp lệ và dữ liệu thiếu. Một test chỉ chứng minh nhóm được **chọn** không thay thế kiểm thử nghiệp vụ của các constraint cụ thể.

## 7. Khi constraint thuộc hai nhóm, có bị chạy hai lần?

Khái niệm **membership** của nhóm khác khái niệm **số lượt thực thi**. Với:

```java
@NotBlank(groups = {Create.class, Update.class})
String email;
```

Khi `validate(bean, Create.class)`, constraint thuộc nhóm được yêu cầu nên được kiểm tra. Khi `validate(bean, Update.class)` ở một lời gọi **khác**, nó cũng được kiểm tra.

Nhưng với **một lời gọi** `validate(bean, Create.class, Update.class)`, nhà cung cấp Bean Validation không phải trả hai bản sao của cùng một violation trên cùng đường dữ liệu. Specification có quy tắc tránh kiểm tra lặp constraint trong cùng validation routine cho một đường đi. Trường hợp có nhiều **constraint declaration khác nhau** trên một field (ví dụ `@NotBlank` và `@Email`) là hai điều kiện riêng, có thể phát sinh hai violation khác nhau nếu đều thất bại.

Không dùng `groups = {Create.class, Update.class}` để diễn đạt "chỉ khi cả Create và Update cùng được chọn". Nếu cần điều kiện kết hợp phức tạp, đó là một **quy tắc nghiệp vụ mới**, không phải cú pháp groups mặc định.

## 8. Spring MVC: chọn một hoặc nhiều group bằng @Validated

Trong Spring, `@Valid` thuộc Jakarta Validation còn `@Validated` thuộc `org.springframework.validation.annotation`. `@Validated` hỗ trợ chọn **validation hints**, phổ biến là các group class.

Trước hết, xác định các interface dùng chung.

**File `src/main/java/com/example/accounts/Checks.java`:**

```java
package com.example.accounts;

public final class Checks {
    private Checks() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
}
```

**File `src/main/java/com/example/accounts/AccountPayload.java`:**

```java
package com.example.accounts;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;

public record AccountPayload(
        @NotBlank String displayName,

        @Null(groups = Checks.Create.class)
        @NotNull(groups = Checks.Update.class)
        Long id,

        @NotBlank(groups = {
                Checks.Create.class, Checks.Update.class
        })
        @Email(groups = {
                Checks.Create.class, Checks.Update.class
        })
        String email,

        @Size(min = 10, groups = Checks.Publish.class)
        String about) {
}
```

Trong DTO này, `displayName` thuộc nhóm `Default`; email thuộc **cả Create và Update**; id có điều kiện khác giữa hai thao tác; about thuộc Publish.

**File `src/main/java/com/example/accounts/AccountController.java`:**

```java
package com.example.accounts;

import jakarta.validation.groups.Default;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @PostMapping("/accounts")
    public ResponseEntity<Void> create(
            @Validated({Default.class, Checks.Create.class})
            @RequestBody AccountPayload payload) {

        // Mô phỏng thành công khi validation đã vượt qua.
        return ResponseEntity.status(201).build();
    }

    @PutMapping("/accounts")
    public ResponseEntity<Void> update(
            @Validated({Default.class, Checks.Update.class})
            @RequestBody AccountPayload payload) {

        return ResponseEntity.noContent().build();
    }
}
```

Đây là **các file trong một ứng dụng Spring MVC hoặc Spring Boot 3.x đang có dependency Web và Validation**, không phải chương trình standalone. Hai endpoint dùng `@Validated` để truyền **hai nhóm mỗi lần** cho Spring Bean Validation integration:

- `POST /accounts` kiểm tra `Default` và `Create`.
- `PUT /accounts` kiểm tra `Default` và `Update`.
- Vì đã truyền `Default.class` một cách tường minh, `@NotBlank displayName` vẫn được kiểm tra cho cả hai request.
- Không có `Publish` trong hai nhóm đó, vì thế `about` ngắn chưa làm request lỗi ở hai endpoint.
- Cần provider (thường qua `spring-boot-starter-validation`) để annotations thực sự được xử lý.

**Dùng `@Validated(Create.class)` một mình có thể bỏ qua các constraint chỉ thuộc Default.** Đây là lỗi khá phổ biến khi chuyển từ `@Valid` sang `@Validated` mà chưa điều chỉnh nhóm.

### 8.1. Request nào hợp lệ?

Tạo mới hợp lệ:

```http
POST /accounts
Content-Type: application/json

{
  "displayName": "An",
  "id": null,
  "email": "an@example.com",
  "about": "short"
}
```

Controller trên trả **201 Created**; `about` chưa đủ 10 ký tự nhưng constraint Publish **không được chọn**, nên không làm request Create bị lỗi.

Tạo mới sai:

```http
POST /accounts
Content-Type: application/json

{
  "displayName": " ",
  "id": 7,
  "email": "invalid-email",
  "about": "short"
}
```

Với validation provider/configuration chuẩn, thường trả **400 Bad Request** vì:
- `displayName` vi phạm `@NotBlank` trong Default.
- `id` vi phạm `@Null` trong Create.
- `email` vi phạm `@Email` trong Create.
- `about` chưa được kiểm tra vì chỉ thuộc Publish.

Cập nhật hợp lệ:

```http
PUT /accounts
Content-Type: application/json

{
  "displayName": "An",
  "id": 7,
  "email": "an@example.com",
  "about": "short"
}
```

Endpoint trả **204 No Content**. Với Update, `id` phải khác null; đây là một ví dụ minh họa **kiểm tra dữ liệu**, chưa xử lý việc ID có tồn tại hoặc có thuộc người dùng hay không.

Cần lưu ý: `@Validated` chỉ áp dụng điều kiện dữ liệu. Nó **không** tự cung cấp phân quyền, xác minh bản ghi thuộc người gọi, kiểm tra chuyển trạng thái hoặc ngăn client ghi lên các trường mà API không cho phép. Với endpoint production, vẫn nên cân nhắc DTO tách biệt cho Create/Update nếu hợp đồng và quyền sửa khác biệt lớn.

### 8.2. Spring xử lý lỗi nhóm ra sao?

Với `@Validated @RequestBody` dạng command object trong MVC:
- Jackson hoặc HttpMessageConverter chuyển JSON thành `AccountPayload`.
- Spring khởi tạo validation với các group/hint đã chọn.
- Bean Validation provider kiểm tra constraint thuộc các nhóm được yêu cầu.
- Nếu có lỗi và không có `BindingResult`/`Errors` xử lý tại chỗ, Spring MVC thường ném `MethodArgumentNotValidException` và trả **HTTP 400**.
- Nếu handler method cần **method validation** do constraint trực tiếp trên tham số hoặc return value, cơ chế Spring MVC 6.1+ có thể dùng `HandlerMethodValidationException`.

Một JSON không thể deserialize thành object (ví dụ giá trị số không chuyển được thành `Long`) có thể lỗi **trước khi** Bean Validation chạy. Không gộp type conversion/binding error với constraint violation.

### 8.3. MockMvc test đúng các nhóm

**File `src/test/java/com/example/accounts/AccountControllerTest.java`** trong ứng dụng Spring Boot có `spring-boot-starter-test`:

```java
package com.example.accounts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void createRunsDefaultAndCreateGroups() throws Exception {
        mvc.perform(post("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": " ",
                      "id": 7,
                      "email": "invalid-email",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                assertTrue(result.getResolvedException()
                        instanceof MethodArgumentNotValidException);
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("displayName"));
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("id"));
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("email"));
                // Nhóm Publish không được chọn; không có lỗi about.
                assertTrue(!ex.getBindingResult()
                        .hasFieldErrors("about"));
            });
    }

    @Test
    void createAllowsShortAboutWhenPublishNotSelected()
            throws Exception {
        mvc.perform(post("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An",
                      "id": null,
                      "email": "an@example.com",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isCreated());
    }

    @Test
    void updateRequiresId() throws Exception {
        mvc.perform(put("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An",
                      "id": null,
                      "email": "an@example.com",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

Các test minh họa API của Spring Boot 3.x với `@WebMvcTest`, Bean Validation provider và application scan phù hợp. Nếu cấu hình có `@ControllerAdvice` riêng, cách ném exception/response có thể khác; điều quan trọng là chứng minh nhóm nào thật sự kiểm tra trường nào.

## 9. @Valid, @Validated và chuyển nhóm khi validate lồng nhau

`@Valid` là metadata **cascaded validation** trong Jakarta. Khi một object cha được validate theo một nhóm, provider thông thường truyền nhóm đang kiểm tra xuống object con qua thuộc tính có `@Valid`.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

interface Create {}

class Address {
    @NotBlank(groups = Create.class)
    String city;
}

class Customer {
    @Valid
    Address address;
}
```

Khi gọi `validator.validate(customer, Create.class)`, constraint `Address.city` thuộc `Create` có thể được xét **nếu address khác null**. Khi gọi chỉ `validator.validate(customer)` (Default), constraint ở Address thuộc riêng Create không được chạy.

Nếu cần chuyển tên nhóm giữa hai miền nghiệp vụ, Jakarta có `@ConvertGroup`, chỉ có ý nghĩa trên đường cascade `@Valid`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.NotBlank;

interface ChildChecks {}

class ShippingAddress {
    @NotBlank(groups = ChildChecks.class)
    String street;
}

class Order {
    @Valid
    @ConvertGroup(from = Default.class, to = ChildChecks.class)
    ShippingAddress shippingAddress;
}
```

Khi validate `Order` theo nhóm Default, ở **đường đi shippingAddress**, group được chuyển sang ChildChecks trước khi validate bean con; constraint trên `ShippingAddress.street` thuộc ChildChecks sẽ được kiểm tra nếu bean tồn tại. Điều này **không thay đổi** nhóm của các constraint khác trên chính Order.

Nên dùng `@ConvertGroup` khi thật sự cần ánh xạ ngữ cảnh giữa các mô hình; không thay thế bằng việc gán mọi constraint vào tất cả nhóm. Với container `List<@Valid Address>`, cũng có thể áp dụng group conversion tại nơi cascade phù hợp theo specification.

**Điều nhóm không làm:** nó không tự bật `@Valid` khi thiếu đường cascade, không tự thêm `@NotNull` khi bean con null, và không biến DTO Java thành lời gọi validation. Cả ba việc đó vẫn có điều kiện riêng.

## 10. Nhóm kế thừa và tập ràng buộc dùng chung

Một nhóm có thể mở rộng nhóm khác qua kế thừa Java interface.

```java
interface BasicChecks {}
interface FullChecks extends BasicChecks {}
```

Nếu một constraint được gán vào `BasicChecks`, yêu cầu validate `FullChecks.class` cũng bao gồm các constraint của `BasicChecks` theo quy tắc kế thừa nhóm. Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

class Profile {
    @NotBlank(groups = BasicChecks.class)
    String name;

    @Size(min = 50, groups = FullChecks.class)
    String biography;
}
```

- `validate(profile, BasicChecks.class)` kiểm tra `name`.
- `validate(profile, FullChecks.class)` kiểm tra `name` **và** `biography`.
- `validate(profile)` theo Default không tự chọn hai nhóm này nếu không có constraint thuộc Default/kế thừa đặc biệt.

Group inheritance là **quan hệ tập hợp**, không đồng nghĩa "Basic chạy trước Full". Nếu cần một thứ tự với quy tắc dừng khi thất bại, dùng group sequence.

**Một lựa chọn thiết kế khác:** đặt constraint chung vào nhóm riêng `Common.class`, rồi truyền `@Validated({Common.class, Create.class})`. Cách này thường dễ đọc và tránh hiểu nhầm rằng nhóm Default được chạy cho mọi endpoint.

## 11. Áp dụng nhiều nhóm có bảo đảm thứ tự kiểm tra không?

**Không.** Với:

```java
validator.validate(bean, Default.class, Publish.class);
```

Jakarta Bean Validation cho phép xử lý các constraint thuộc hai nhóm theo thứ tự bất kỳ, miễn bảo đảm hành vi validation theo specification. Không được suy diễn rằng tham số group đầu tiên luôn được xử lý trước hoặc nhóm thứ hai sẽ bị bỏ qua nếu nhóm đầu thất bại.

Muốn kiểm tra tuần tự, khai báo **group sequence** trên một interface:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface PublishChecks {}

@GroupSequence({Default.class, PublishChecks.class})
interface PublishFlow {}
```

Sau đó:

```java
validator.validate(bean, PublishFlow.class);
```

Theo sequence, Default được kiểm tra trước. Nếu Default có vi phạm, `PublishChecks` **không được chạy trong lượt này**. Nếu Default pass, bước PublishChecks được thực hiện. Một constraint thuộc nhiều nhóm trong sequence không được đánh giá lặp cho cùng đường đi.

Đây là **cơ chế thứ tự và dừng sớm giữa nhóm**, không phải cách áp dụng đơn thuần một constraint cho nhiều nhóm. Không dùng `@GroupSequence` nếu chỉ cần validate hợp hai nhóm mà không quan tâm thứ tự.

Các nhóm trong sequence không được tạo vòng phụ thuộc. Việc gắn constraint trực tiếp vào chính interface đã định nghĩa sequence cũng không phải mô hình được khuyến nghị. Khi định nghĩa lại nhóm Default trên **class** bằng `@GroupSequence`, specification có các quy tắc riêng (phải đưa chính class vào sequence, không chỉ viết `Default.class`); hãy xem tài liệu chính thức trước khi dùng cấu hình nâng cao đó.

## 12. Dùng validation groups cho service và method validation

Nhóm cũng áp dụng cho kiểm tra các tham số và giá trị trả về của method khi **method validation** được bật. Tuy nhiên:

- `@Valid` trên tham số method Java bình thường **không tự kích hoạt** validation.
- Trong Spring service bean, method validation truyền thống hoạt động thông qua infrastructure/proxy (thường dùng `@Validated` trên bean), nên phải gọi **qua Spring bean proxy** và có provider.
- Gọi `new MyService()` hoặc tự gọi `this.someMethod()` trong chính bean có thể bỏ qua interception của Spring AOP.
- Spring MVC 6.1+ có built-in method validation cho handler method, khác với cơ chế proxy service; controller-level `@Validated` có thể ảnh hưởng lựa chọn cơ chế.

Một fragment minh họa:

```java
import jakarta.validation.Valid;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Groups.Update.class)
class AccountService {

    public void save(@Valid AccountPayload payload) {
        // Logic sau khi qua method validation nếu infrastructure bật.
    }
}
```

Trong fragment, `Groups.Update` là group mặc định cho cơ chế method validation của bean theo cấu hình Spring, còn `@Valid` yêu cầu cascade vào `AccountPayload`. Nếu dùng `Groups.Update` mà muốn thêm các constraint Default, cần thiết kế/lựa chọn group phù hợp; không tự cho rằng Default luôn được bổ sung.

**Giới hạn quan trọng:** group validation không thay thế authorization hoặc transaction invariants. Một user có quyền Update vẫn cần được kiểm tra quyền thao tác lên đúng đối tượng, kể cả khi DTO hợp lệ.

## 13. Container element constraint và nhóm

Group metadata được khai báo cho constraint ngay tại vị trí type argument:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

record Labels(
        @NotEmpty
        List<@NotBlank(groups = Groups.Create.class) String> values) {
}
```

- `@NotEmpty` trên danh sách thuộc Default.
- `@NotBlank` trên từng String thuộc Create.
- `validate(labels)` chỉ kiểm tra `@NotEmpty`; nếu list không rỗng nhưng chứa `" "`, lượt Default này không tự chạy `@NotBlank`.
- `validate(labels, Create.class)` kiểm tra các phần tử String theo nhóm Create nhưng không tự chạy `@NotEmpty` của Default.
- `validate(labels, Default.class, Create.class)` yêu cầu cả hai.

Với bean con:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Line(@NotBlank(groups = Groups.Update.class) String sku) {}

record Batch(List<@Valid Line> lines) {}
```

Khi Bean Validation xác thực Batch theo Update, nó cascade vào từng `Line` và kiểm tra `sku` theo nhóm Update; khi chỉ xác thực Default, constraint chỉ thuộc Update không được chọn. `@Valid` không tự chọn lại Default, và phần tử Line null sẽ bị bỏ qua khi cascade trừ khi có `@NotNull` trên element.

## 14. Khi nào dùng groups, khi nào nên tách DTO?

**Groups phù hợp** khi:
- Cấu trúc DTO thực sự là một, nhưng quy tắc đơn giản thay đổi theo thao tác Create/Update.
- Một constraint cần xuất hiện trong nhiều ngữ cảnh và khai báo chung giúp giảm trùng lặp.
- Hệ thống cần phân tầng kiểm tra rõ ràng, ví dụ kiểm tra cơ bản rồi mới kiểm tra nặng qua group sequence.
- Tổ chức cần truyền cùng logic nhóm qua cascade vào object con.

**Tách DTO thường rõ ràng hơn** khi:
- JSON schema Create và Update khác nhiều trường hoặc kiểu dữ liệu.
- Quyền ghi field khác nhau; ví dụ admin được sửa trường mà user không được sửa.
- Những ràng buộc chéo và invariant nghiệp vụ quá phức tạp.
- Một DTO dùng chung tạo nhiều nhóm, group conversion và sequence khiến khó đọc, khó test.
- Hợp đồng public API cần tài liệu, OpenAPI schema và backward compatibility độc lập.

Dù chọn groups hay tách DTO, cần kiểm thử **đúng điểm vào** (MVC, service, message consumer) và không cho rằng một annotation luôn được thực thi trong mọi luồng.

## 15. Ma trận kiểm thử các trường hợp dễ bỏ sót

| Tình huống | Đề xuất assertion |
| --- | --- |
| Constraint không khai báo groups | Chỉ xác nhận nó thuộc Default trong ví dụ đơn giản |
| Constraint chỉ thuộc Create | `validate(bean, Create.class)` chạy; `validate(bean)` không tự chạy |
| Constraint thuộc Create và Update | Cả hai lời gọi nhóm riêng đều kiểm tra |
| `validate(bean, Create.class, Update.class)` | Hợp constraint hai nhóm, không yêu cầu theo thứ tự |
| Default + Create | Constraint chung Default và riêng Create cùng chạy |
| Group inheritance | Nhóm con lấy thêm constraint từ nhóm cha |
| Group sequence | Nhóm sau bị bỏ qua nếu nhóm trước có violation |
| Bean con có `@Valid` | Group đang validate được truyền xuống theo quy tắc cascade |
| Bean con có `@ConvertGroup` | Kiểm tra nhánh con theo group đã chuyển |
| Bean con null | Cascade bỏ qua; thêm `@NotNull` nếu phải tồn tại |
| List type argument có groups | Chỉ constraint thuộc nhóm được chọn mới chạy trên phần tử |
| `@Validated` chỉ Create trong MVC | Không ngầm chạy Default; test field chung |
| `@Validated({Default, Create})` | Cả Default và Create được áp dụng |
| JSON sai kiểu | Lỗi deserialize/binding có thể xảy ra trước validation |
| Dự án thiếu provider | Không nên khẳng định Bean Validation đã được kích hoạt |
| Service self-invocation | Không giả định AOP method validation được chạy |
| DTO hợp lệ nhưng sai quyền | Authorization/nghiệp vụ vẫn cần kiểm tra riêng |

Khi assertion đường dẫn lỗi, đừng phụ thuộc thứ tự các violation hay thông điệp tiếng Anh; dùng `ConstraintViolation.getPropertyPath()` và field errors đã được chuẩn hóa.

## 16. Lỗi phổ biến khi khai báo nhóm

1. **Cho rằng Default luôn chạy:** khi chọn `Create.class` riêng thì Default không tự được thêm. Truyền rõ `Default.class` nếu muốn.
2. **Nhầm `groups={A,B}` với phép giao:** constraint thuộc **cả hai tập**, chạy nếu được yêu cầu A hoặc B.
3. **Chỉ gán nhóm, không kích hoạt validation:** cần `Validator.validate` hoặc Spring integration.
4. **Cho rằng thứ tự trong `validate(bean, A.class, B.class)` là thứ tự thực thi:** không bảo đảm; dùng `@GroupSequence` nếu cần.
5. **Thêm tất cả constraint vào mọi nhóm:** dẫn đến khó bảo trì; dùng nhóm Common/kế thừa hoặc tách DTO.
6. **Quên `@Valid` trên association:** nhóm có được chọn vẫn không đến bean con nếu thiếu đường cascade.
7. **Sai cách dùng `@ConvertGroup`:** chỉ có ý nghĩa khi đi cùng cascaded validation; không dùng để đổi nhóm tùy tiện trên field scalar.
8. **Quên chọn group trong Spring MVC:** `@Valid @RequestBody` thông thường chỉ yêu cầu Default, không tự chọn Create/Update.
9. **Nhầm `@Validated` và `@Valid` hoàn toàn giống nhau:** `@Validated` của Spring có khả năng chọn group, còn `@Valid` của Jakarta là chỉ dẫn cascade và dấu validation root trong integration.
10. **Dùng chung DTO để giải quyết authorization:** groups kiểm tra dữ liệu, không cấp quyền.
11. **Kiểm thử chỉ status 400:** thiếu assertion field/path nên không biết constraint group nào thực sự chạy.
12. **Cấu hình provider và namespace sai:** Spring Boot 3.x dùng Jakarta, cần thư viện Bean Validation tương thích.
13. **Xem group sequence là điều kiện OR:** sequence là xử lý **theo thứ tự với dừng sớm**, không phải phép chọn tùy ý.
14. **Không phân biệt validation nhóm với các bước nghiệp vụ:** một request đã pass Create không đồng nghĩa được phép lưu/xuất bản.
15. **Bỏ qua null và group constraint chỉ hoạt động trên giá trị khác null:** nhiều constraint chấp nhận null, cần `@NotNull` đúng nhóm nếu bắt buộc.
16. **Giả định group là runtime state của object:** group được **truyền khi validate**, không tự "gắn trạng thái Create" vào bean.

## 17. Checklist áp dụng vào dự án

1. Viết bảng quy tắc theo **hành động** (Create, Update, Publish) và **thuộc tính** trước khi chọn annotation.
2. Đặt nhóm bằng marker interfaces; dùng `groups = A.class` cho một nhóm và `groups = {A.class, B.class}` cho nhiều nhóm.
3. Ghi nhớ constraint không có `groups` mặc định thuộc `Default`; quyết định có luôn kiểm tra nhóm đó hay không.
4. Tại điểm validate, chọn đúng nhóm bằng `Validator.validate(bean, ...)` hoặc `@Validated(...)` trong Spring.
5. Khi cần chạy **cả** constraint chung và riêng, truyền `Default.class` cùng nhóm nghiệp vụ hoặc thiết kế group inheritance rõ ràng.
6. Dùng `@GroupSequence` **chỉ khi** cần thứ tự/dừng sớm; không phụ thuộc thứ tự truyền nhóm thông thường.
7. Với bean con và collection, kiểm tra `@Valid`, group propagation, `@ConvertGroup` nếu có và behavior khi null.
8. Xác minh provider, classpath, cơ chế method validation và phân biệt lỗi binding so với vi phạm constraint.
9. Tạo test provider-level (JUnit) và integration test (MockMvc) cho mỗi hành động; assertion tên field được kiểm tra/không kiểm tra.
10. Giữ trách nhiệm phân quyền, kiểm soát transaction và invariant nghiệp vụ **ngoài** validation groups.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 — Group and group sequence, group inheritance, group conversion](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Bean Validation API — Default group](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/Default.html).
- [Spring Framework Javadoc — @Validated](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/annotation/Validated.html).
- [Spring Framework — @RequestBody và validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Hibernate Validator 8 Reference Guide — Grouping constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
