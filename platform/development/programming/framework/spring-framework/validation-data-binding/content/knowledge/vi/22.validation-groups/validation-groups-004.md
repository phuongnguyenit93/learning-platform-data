# Nhóm tạo mới, cập nhật và tác vụ chuyên biệt trong Jakarta Validation và Spring

> **Module:** Spring Framework – validation-data-binding  
> **Nhóm kiến thức:** Nhóm kiểm tra (validation groups)  
> **Trọng tâm:** Thiết kế nhóm `Create`, `Update` và các nhóm tác vụ như `Publish`, `Approve`, `Dispatch`; chọn đúng các constraint ở từng điểm kích hoạt bằng Spring `@Validated`, đồng thời bảo đảm các quy tắc chung không bị bỏ sót.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một kiểu DTO cần những tập quy tắc khác nhau cho tạo mới, cập nhật và các bước nghiệp vụ chuyên biệt.
2. Định nghĩa nhóm bằng **marker interface** và khai báo `groups` trên các Jakarta Validation constraint.
3. Phân biệt nhóm `Default` với `Create`, `Update`, `Publish`; hiểu rằng chọn nhóm riêng **không mặc nhiên chạy** `Default`.
4. Sử dụng `@Validated({Default.class, Create.class})` trong Spring MVC và `Validator.validate(bean, groups...)` khi kiểm thử.
5. Thiết kế group inheritance, group sequence, group conversion cho trường hợp cần thiết; nhận ra khi nào nên tách DTO thay vì chồng thêm nhiều group.
6. Áp dụng kiểm tra cho form và JSON request, đồng thời phân biệt validation ở controller với method validation trên service.
7. Viết và chạy ví dụ Java 17+ có output xác định cho mọi nhóm và tình huống phối hợp nhóm.
8. Tránh nhầm lẫn validation groups với phân quyền, trạng thái quy trình, quy tắc transaction hoặc ràng buộc dữ liệu.

## 2. Bài toán: một đối tượng, nhiều ngữ cảnh

Giả sử hệ thống quản lý tài liệu có quy trình:

~~~text
Tạo nháp (Create) --> Chỉnh sửa (Update) --> Xuất bản (Publish)
                                           \
                                            --> Phê duyệt (Approve)
~~~

Mỗi tác vụ có yêu cầu khác nhau:

| Trường | Create | Update | Publish | Approve |
| --- | --- | --- | --- | --- |
| `id` | Phải `null` (server tự cấp) | Bắt buộc có | Bắt buộc có | Tùy hợp đồng tác vụ |
| `title` | Không được blank | Không được blank | Không được blank | Có thể không cần gửi |
| `ownerEmail` | Cú pháp email hợp lệ | Cú pháp email hợp lệ | Cú pháp email hợp lệ | Tùy hợp đồng |
| `reviewed` | Chưa cần kiểm tra | Chưa cần kiểm tra | Phải `true` | Có thể không liên quan |
| `approver` | Chưa cần | Chưa cần | Chưa cần | Không được blank |

Nếu một DTO mang tất cả constraint ở nhóm mặc định, việc tạo mới có thể bị chặn vì `id` chưa được sinh, hoặc việc cập nhật bị chặn vì `reviewed` chưa đúng mặc dù chưa tới bước publish.

**Validation groups** cho phép cùng một constraint chỉ có hiệu lực khi **nhóm tương ứng được yêu cầu**. Đây là cơ chế của **Jakarta Validation**, không phải một tính năng giới hạn ở Spring.

Có ba tầng phải tách rõ:

~~~text
1. Constraint metadata trên DTO
   @NotNull(groups = Update.class)
   @AssertTrue(groups = Publish.class)

2. Ngữ cảnh thực thi
   @Validated({Default.class, Update.class})
   hoặc validator.validate(dto, Update.class, Default.class)

3. Kết quả
   Set<ConstraintViolation<T>> / BindingResult / lỗi HTTP
~~~

Viết `groups` mới chỉ là **khai báo quy tắc**. Nếu không có `Validator` hoặc tích hợp Spring kích hoạt validation, annotation không tự chạy khi tạo bean, gọi constructor hay setter.

## 3. Cách định nghĩa một group

Một group thường là interface rỗng:

~~~java
public interface Create {}
public interface Update {}
public interface Publish {}
public interface Approve {}
~~~

Các interface này chỉ đóng vai trò **tên nhóm**; DTO không cần `implements` chúng, cũng không cần viết phương thức.

Một cách tổ chức dễ quản lý trong dự án thực:

~~~java
package example.validation;

public final class ValidationGroups {
    private ValidationGroups() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
    public interface Approve {}
    public interface Dispatch {}
}
~~~

Tệp `ValidationGroups.java` ở trên là class Java biên dịch được với Java 17 thuần. Sau đó tham chiếu, ví dụ:

~~~java
import static example.validation.ValidationGroups.Create;
import static example.validation.ValidationGroups.Update;
~~~

Đây là **import fragment** dùng trong một source file khác. Có thể đặt tên nhóm theo hành động nghiệp vụ, chẳng hạn `Submit`, `ConfirmPayment`, `CloseBooking`, `Archive`. Tuy nhiên, cần thống nhất quy tắc đặt tên và tránh tạo hàng chục nhóm gần như trùng nhau.

## 4. Khai báo constraint theo nhóm trên DTO

Ví dụ định nghĩa một DTO Java 17 bằng record:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public record DocumentCommand(
        @Null(groups = Create.class)
        @NotNull(groups = {Update.class, Publish.class})
        Long id,

        @NotBlank(groups = {Create.class, Update.class, Publish.class})
        String title,

        @NotBlank
        @Email
        String ownerEmail,

        @NotNull(groups = Publish.class)
        @AssertTrue(groups = Publish.class)
        Boolean reviewed,

        @NotBlank(groups = Approve.class)
        String approver) {
}
~~~

Đoạn này là **mảnh mô hình**, giả định đã import các marker interface `Create`, `Update`, `Publish`, `Approve`.

Ý nghĩa:

- `id`: khi Create, `@Null` yêu cầu chưa có ID; khi Update/Publish, `@NotNull` yêu cầu đã có ID.
- `title`: phải không blank ở cả Create, Update và Publish. Không nằm trong nhóm Approve vì giả sử tác vụ phê duyệt riêng không thay nội dung.
- `ownerEmail`: `@NotBlank` và `@Email` **không ghi `groups`** nên thuộc nhóm chuẩn `jakarta.validation.groups.Default`.
- `reviewed`: bắt buộc khác null và phải `true` khi Publish. `@AssertTrue` tự nó cho phép null, vì vậy phải có `@NotNull` nếu field bắt buộc ở bước này.
- `approver`: chỉ được yêu cầu không blank khi Approve.

Để tạo một quy tắc cho nhiều nhóm:

~~~java
@NotBlank(groups = {Create.class, Update.class, Publish.class})
String title
~~~

Không cần nhân bản ba property hoặc tự viết ba validator giống hệt nhau.

**Điều cần tránh:** `groups` kiểm soát **những constraint nào được đánh giá**, không tự thay đổi dữ liệu DTO, không sinh `id`, không ẩn field trong JSON, không ngăn người dùng gửi field ngoài quyền sửa.

## 5. `Default` là nhóm đặc biệt quan trọng

Một constraint **không khai báo `groups`** được gán vào `Default`:

~~~java
@NotBlank              // thuộc Default
private String email;

@NotBlank(groups = Create.class)
private String title;  // thuộc Create, không tự thuộc Default
~~~

Nếu `Create` là interface độc lập, các lệnh gọi sau khác nhau:

~~~java
validator.validate(command);
validator.validate(command, Create.class);
validator.validate(command, Update.class);
validator.validate(command, Default.class, Create.class);
~~~

- `validate(command)`: đánh giá `Default`.
- `validate(command, Create.class)`: đánh giá `Create`, **không tự kèm Default**.
- `validate(command, Update.class)`: đánh giá `Update`.
- `validate(command, Default.class, Create.class)`: đánh giá cả hai nhóm.

Trong Spring, quy tắc tương ứng:

~~~java
@Validated(Create.class)
@Validated({Default.class, Create.class})
~~~

Đây là **hai lựa chọn độc lập**, không đặt cả hai annotation lặp lại trên cùng tham số.

| Khi chọn | Rủi ro nếu quên `Default` |
| --- | --- |
| `@Validated(Create.class)` | Có thể bỏ qua `@Email` / `@NotBlank` khai báo không groups |
| `@Validated(Update.class)` | Có thể bỏ qua ràng buộc chung trên tất cả thao tác |
| `@Validated({Default.class, Create.class})` | Kiểm tra cả quy tắc chung lẫn Create |
| `@Validated({Default.class, Update.class})` | Kiểm tra cả quy tắc chung lẫn Update |

**Không có gì sai** khi cố ý chọn duy nhất một nhóm. Sai là khi lập trình viên tưởng rằng `Default` luôn tự chạy và vô tình bỏ sót các constraint bắt buộc. Nếu nhóm được thiết kế kế thừa `Default` hoặc dùng group sequence, hành vi có thể khác; cần hiểu rõ cấu trúc của chính dự án.

## 6. Chọn nhóm theo từng tác vụ chuyên biệt

### 6.1. Tạo mới (Create)

Những điều thường cần kiểm tra:

- ID do server sinh phải vắng mặt: `@Null(groups=Create.class)`.
- Các field bắt buộc khi tạo: `@NotBlank(groups=Create.class)` / `@NotNull(groups=Create.class)`.
- Các ràng buộc chung như email, định dạng mã: chạy `Default` nếu chúng nằm ở nhóm đó.

Ví dụ:

~~~java
@Validated({Default.class, Create.class})
@RequestBody DocumentCommand request
~~~

Fragment trên là một **tham số controller**, chưa phải phương thức hoàn chỉnh. Trong API thật, `id` có thể hoàn toàn bị loại khỏi Create DTO để tránh client gửi một ID bất kỳ; không nhất thiết phải dùng `@Null` trên một model dùng chung.

### 6.2. Cập nhật (Update)

Những điều thường cần kiểm tra:

- ID bắt buộc: `@NotNull(groups=Update.class)`.
- Tên hoặc trường có ý nghĩa khi cập nhật: `@NotBlank(groups=Update.class)`.
- Có thể yêu cầu mã phiên bản/`ETag` khi cần optimistic locking; validation group không tự giải quyết xung đột cập nhật đồng thời.

~~~java
@Validated({Default.class, Update.class})
@RequestBody DocumentCommand request
~~~

Nếu Update API sử dụng **PUT** với toàn bộ dữ liệu, `@NotBlank` có thể hợp lý. Nếu Update API sử dụng **PATCH**, field không gửi có thể mang ý nghĩa "giữ nguyên"; dùng cùng `@NotBlank` cho mọi field thường không thích hợp. Phần PATCH sẽ được phân tích ở mục 14.

### 6.3. Xuất bản (Publish)

Publish có thể yêu cầu:

- Đối tượng đã tồn tại (ID khác null).
- Nội dung đã có tiêu đề.
- `reviewed == true`.
- Email chủ sở hữu hợp lệ theo nhóm chung.

~~~java
@Validated({Default.class, Publish.class})
@RequestBody DocumentCommand request
~~~

`@AssertTrue` kiểm tra một giá trị Boolean ở thời điểm validate. Nó không tự xác minh rằng quá trình review thật sự được một người có quyền hoàn tất; điều đó cần nghiệp vụ, audit log và phân quyền ở tầng service.

### 6.4. Phê duyệt (Approve)

Tác vụ Approve có thể dùng DTO chuyên biệt:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ApprovalCommand(
        @NotNull Long documentId,
        @NotBlank String approver,
        @NotBlank String comment) {}
~~~

Đây là **mô hình DTO minh họa**. Vì shape của approve khác hẳn Create/Update, ở đây **tách DTO** thường đơn giản hơn đặt thêm group Approve trên mọi field của DTO lớn. Khi chỉ một vài constraint khác nhau và muốn tái sử dụng DTO, nhóm `Approve` mới thực sự có lợi.

### 6.5. Các tác vụ chuyên biệt khác

| Tác vụ | Tên group gợi ý | Ví dụ constraint khai báo theo group |
| --- | --- | --- |
| Hoàn tất hồ sơ | `Submit` | `@NotBlank(groups=Submit.class)` trên số giấy tờ |
| Gửi hàng | `Dispatch` | `@NotNull(groups=Dispatch.class)` trên địa chỉ |
| Thanh toán | `Checkout` | `@NotNull(groups=Checkout.class)` trên phương thức thanh toán |
| Khóa sổ | `ClosePeriod` | `@NotNull(groups=ClosePeriod.class)` trên ngày khóa |
| Xuất bản | `Publish` | `@AssertTrue(groups=Publish.class)` trên cờ đã review |
| Đóng yêu cầu | `Resolve` | `@NotBlank(groups=Resolve.class)` trên kết quả giải quyết |

**Cảnh báo:** Dù một request vượt qua constraint của nhóm `Checkout`, đó **không đồng nghĩa** giao dịch đã được thanh toán hay người gọi được phép thanh toán. Groups phân nhóm **validation**, không thực hiện hành động và không cấp quyền.

## 7. Bảng dự đoán nhóm và số lỗi

Với `DocumentCommand` ở mục 4, giả sử:

~~~text
id         = 7
title      = ""
ownerEmail = "not-mail"
reviewed   = false
approver   = ""
~~~

| Group được chạy | Property vi phạm | Tổng lỗi |
| --- | --- | ---: |
| `Default` | `ownerEmail` do `@Email` | 1 |
| `Create` | `id` do `@Null`, `title` do `@NotBlank` | 2 |
| `Update` | `title` do `@NotBlank` | 1 |
| `Publish` | `title` do `@NotBlank`, `reviewed` do `@AssertTrue` | 2 |
| `Approve` | `approver` do `@NotBlank` | 1 |
| `Default + Create` | `ownerEmail`, `id`, `title` | 3 |
| `Default + Publish` | `ownerEmail`, `title`, `reviewed` | 3 |

Ở `Publish`, `reviewed=false` **đạt `@NotNull`** nhưng **không đạt `@AssertTrue`**. Nếu `reviewed=null`, theo ngữ nghĩa constraint, `@AssertTrue` cho null hợp lệ và `@NotNull` báo lỗi: vẫn một violation ở `reviewed` theo hai tình huống khác nhau.

Thứ tự một `Set<ConstraintViolation<?>>` không được bảo đảm. Bảng liệt kê theo ý nghĩa, không phải thứ tự callback của provider.

## 8. Chương trình Java 17+ chạy được: kiểm chứng các nhóm

Một ví dụ Jakarta Validation thuần giúp kiểm chứng group mà không cần chạy HTTP server. Sau khi hiểu kết quả, bạn có thể áp dụng cùng cách chọn group bằng `@Validated` trong Spring.

### 8.1. Cấu trúc project Maven

~~~text
validation-groups-demo/
├── pom.xml
└── src/main/java/example/groupdemo/ValidationGroupsDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validation-groups-demo</artifactId>
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
~~~

Hibernate Validator 8 là provider phù hợp với Jakarta Validation 3.0. Dependency Jakarta EL phục vụ nội suy thông báo mặc định. Các version trên dành cho ví dụ tái lập; dự án Spring Boot thực tế nên để BOM/parent quản lý version tương thích.

### 8.2. Mã Java hoàn chỉnh

Lưu tệp `src/main/java/example/groupdemo/ValidationGroupsDemo.java`:

~~~java
package example.groupdemo;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public final class ValidationGroupsDemo {

    public interface Create {}
    public interface Update {}
    public interface Publish {}
    public interface Approve {}

    public record Document(
            @Null(groups = Create.class)
            @NotNull(groups = {Update.class, Publish.class})
            Long id,

            @NotBlank(groups = {
                    Create.class, Update.class, Publish.class
            })
            String title,

            @NotBlank
            @Email
            String ownerEmail,

            @NotNull(groups = Publish.class)
            @AssertTrue(groups = Publish.class)
            Boolean reviewed,

            @NotBlank(groups = Approve.class)
            String approver) {}

    private static String invalidFields(
            Validator validator, Document document, Class<?>... groups) {
        return validator.validate(document, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Document invalid =
                    new Document(7L, "", "not-mail", false, "");

            System.out.println("default="
                    + invalidFields(validator, invalid));
            System.out.println("create="
                    + invalidFields(validator, invalid, Create.class));
            System.out.println("update="
                    + invalidFields(validator, invalid, Update.class));
            System.out.println("publish="
                    + invalidFields(validator, invalid, Publish.class));
            System.out.println("approve="
                    + invalidFields(validator, invalid, Approve.class));
            System.out.println("default+create="
                    + invalidFields(validator, invalid,
                                    Default.class, Create.class));
            System.out.println("default+publish="
                    + invalidFields(validator, invalid,
                                    Default.class, Publish.class));

            Document validCreate =
                    new Document(null, "Guide", "a@example.com",
                                 null, null);
            Document validPublish =
                    new Document(8L, "Guide", "a@example.com",
                                 true, "reviewer");

            System.out.println("valid-create-count="
                    + validator.validate(
                            validCreate, Default.class,
                            Create.class).size());
            System.out.println("valid-publish-approve-count="
                    + validator.validate(
                            validPublish, Default.class,
                            Publish.class, Approve.class).size());
        }
    }
}
~~~

Chạy trong thư mục project:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.groupdemo.ValidationGroupsDemo
~~~

**Stdout do chương trình in**, không tính log Maven/provider:

~~~text
default=ownerEmail
create=id,title
update=title
publish=reviewed,title
approve=approver
default+create=id,ownerEmail,title
default+publish=ownerEmail,reviewed,title
valid-create-count=0
valid-publish-approve-count=0
~~~

Giải thích cụ thể:

- `Default`: `ownerEmail="not-mail"` đạt `@NotBlank` nhưng không đạt `@Email`.
- `Create`: `id` phải null và `title` phải khác blank; các constraint Publish/Approve không chạy.
- `Update`: `id=7L` đạt `@NotNull`, `title=""` thất bại.
- `Publish`: `id=7L` đạt; `title=""` và `reviewed=false` thất bại.
- `Approve`: `approver=""` thất bại.
- `Default+Create`: kết hợp đúng tập constraint chung và riêng.
- `validCreate`: ID null là đúng trong Create; `reviewed` và `approver` chưa bắt buộc khi tạo.
- `validPublish`: mọi điều kiện của ba nhóm yêu cầu đều đạt.

Hàm `invalidFields` có `distinct()` và `sorted()` để tạo output ổn định, không phụ thuộc thứ tự của `Set<ConstraintViolation<Document>>`. Trong ứng dụng thực, không chỉ so tên field: nếu cùng một property vi phạm nhiều constraint, cần giữ mã lỗi và thông báo riêng; ở đây `distinct()` chỉ phục vụ minh họa tập field.

**Biên dịch bằng `javac` thuần:** Source Java đầy đủ nhưng sử dụng Jakarta Validation/Hibernate Validator; `javac ValidationGroupsDemo.java` trong thư mục không có classpath sẽ thiếu thư viện. Maven tự nạp các dependency; nếu dùng `javac`/`java -cp` phải cấp **tất cả JAR liên quan**. Không nhầm lỗi thiếu classpath với lỗi group.

## 9. Spring MVC: chọn nhóm cho Create, Update và Publish

Trong Spring Boot 3.x / Spring Framework 6.x, dự án thông thường dùng:

~~~xml
<!-- Hai dependency trong pom.xml đã có Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là **dependency fragment**, không phải một `pom.xml` độc lập. Starter validation thường cung cấp Hibernate Validator và tích hợp cần thiết; không được giả định chỉ có starter web là chắc chắn chạy các annotation.

### 9.1. Ứng dụng Spring Boot Java 17+

Trong một project Spring Boot đã cấu hình các starter ở trên, tạo tệp `src/main/java/example/groupweb/GroupWebApplication.java`:

~~~java
package example.groupweb;

import java.util.Map;

import jakarta.validation.constraints.AssertTrue;
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
    public interface Publish {}

    public record ArticleRequest(
            @Null(groups = Create.class)
            @NotNull(groups = {Update.class, Publish.class})
            Long id,

            @NotBlank(groups = {
                    Create.class, Update.class, Publish.class
            })
            String title,

            @NotBlank
            @Email
            String contactEmail,

            @NotNull(groups = Publish.class)
            @AssertTrue(groups = Publish.class)
            Boolean reviewed) {}

    @RestController
    @RequestMapping("/documents")
    public static class DocumentController {

        @PostMapping
        public Map<String, String> create(
                @Validated({Default.class, Create.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "create",
                          "title", request.title());
        }

        @PutMapping
        public Map<String, String> update(
                @Validated({Default.class, Update.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "update",
                          "id", request.id().toString());
        }

        @PostMapping("/publish")
        public Map<String, String> publish(
                @Validated({Default.class, Publish.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "publish",
                          "id", request.id().toString());
        }
    }
}
~~~

Đây là **file ứng dụng hoàn chỉnh** nếu được đặt vào project Spring Boot có dependency/version và build wrapper phù hợp. Không cần ghi `@Valid` thêm trên cùng tham số `@Validated` để chọn nhóm: `@Validated` được Spring MVC nhận biết và chuyển nhóm tới validator.

Chạy theo build tool sẵn có:

~~~bash
./mvnw spring-boot:run
~~~

hoặc:

~~~bash
./gradlew bootRun
~~~

Các lệnh wrapper này chỉ tồn tại nếu project thực sự chứa `mvnw` hoặc `gradlew` tương ứng.

### 9.2. Thử các endpoint

Giả sử ứng dụng chạy cổng `8080`:

~~~bash
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"First draft","contactEmail":"a@example.com","reviewed":null}'

curl -i -X PUT http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Revised draft","contactEmail":"a@example.com","reviewed":false}'

curl -i -X POST http://localhost:8080/documents/publish \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Ready article","contactEmail":"a@example.com","reviewed":true}'
~~~

Với cấu hình Spring MVC thông thường và không có security/filter đặc biệt, các request hợp lệ trên trả **HTTP 200**, lần lượt mang `operation=create`, `operation=update`, `operation=publish` trong JSON response. Thứ tự key trong JSON không được cam kết.

Thử các request không hợp lệ:

~~~bash
# Create mà client tự đặt ID -> @Null(Create) không đạt
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":99,"title":"Draft","contactEmail":"a@example.com","reviewed":null}'

# Update thiếu ID -> @NotNull(Update) không đạt
curl -i -X PUT http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"Draft","contactEmail":"a@example.com","reviewed":false}'

# Publish chưa review -> @AssertTrue(Publish) không đạt
curl -i -X POST http://localhost:8080/documents/publish \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Draft","contactEmail":"a@example.com","reviewed":false}'

# Email sai dù Create fields hợp lệ -> @Email(Default) không đạt
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"Draft","contactEmail":"invalid","reviewed":null}'
~~~

Trong đường kiểm tra `@RequestBody` thông thường, các constraint thất bại thường dẫn tới **HTTP 400**, ví dụ `MethodArgumentNotValidException`. Cấu trúc JSON lỗi phụ thuộc `@ControllerAdvice`, Problem Details và cấu hình Spring Boot; không dự đoán một payload cố định.

**Cần phân biệt:** Jackson deserialize JSON trước, Jakarta Validation chạy sau. Chuỗi `"id":"not-a-long"` có thể lỗi **chuyển kiểu dữ liệu** trước khi group constraint được kiểm tra. Còn `id=null` chuyển được sang `Long` và có thể bị `@NotNull` của nhóm Update từ chối.

### 9.3. `@ModelAttribute` và `BindingResult`

Với form data, chọn nhóm tương tự:

~~~java
@PostMapping("/draft-form")
public String submitForm(
        @Validated({Default.class, Create.class})
        @ModelAttribute DraftForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "invalid-form";
    }
    return "accepted";
}
~~~

Đây là **method fragment**, cần khai báo `DraftForm` và import trong controller thực. `BindingResult` phải đặt **ngay sau** tham số model cần xử lý, để nhận lỗi binding và validation của chính model đó.

Trong Spring MVC 6.1+, nếu handler còn có constraint trực tiếp trên method parameter (ví dụ `@Min` trên `@RequestParam`), built-in method validation có thể thay đổi đường thực thi và exception thành `HandlerMethodValidationException`. Đừng thiết kế error handler giả định mọi trường hợp đều là `MethodArgumentNotValidException`.

## 10. Phân biệt hai nơi dùng `@Validated` trong Spring

`org.springframework.validation.annotation.Validated` có những tình huống sử dụng liên quan nhưng **không giống hệt nhau**:

| Nơi đặt `@Validated` | Mục đích chính | Điều kiện |
| --- | --- | --- |
| Trên tham số DTO của Spring MVC, ví dụ `@Validated(Create.class) @RequestBody` | Chọn group để validate **đối tượng request** | Spring MVC + Bean Validation provider |
| Trên class service Spring `@Validated` | Đánh dấu bean cho **AOP method validation** | MethodValidationPostProcessor/proxy, provider, constraints ở method |
| Trên method service trong bean có cơ chế method validation | Có thể chỉ định validation hints/group tại method | Cần kiểm tra wiring, proxy và group selection của Spring |
| Trên class controller Spring MVC 6.1+ | Có thể đưa handler vào đường AOP method validation | Không tự khuyến nghị khi muốn dùng built-in MVC method validation |

### 10.1. Method validation ở service

Fragment triển khai:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class DocumentService {

    public interface Publish {}

    public void publish(
            @NotNull(groups = Publish.class) Long documentId) {
        // Gọi repository, kiểm tra quyền, thực hiện publish...
    }
}
~~~

**Cảnh báo của ví dụ:** Class-level `@Validated` ở trên **không chọn nhóm Publish**; nó dùng group mặc định khi không có phương thức khai báo group/hint khác. Do vậy riêng constraint `@NotNull(groups=Publish.class)` sẽ **không chạy** với nhóm Default! Muốn bảo đảm kiểm tra Publish cho method này, có thể thiết kế rõ:

~~~java
@Service
@Validated(DocumentService.Publish.class)
public class DocumentService {
    public interface Publish {}

    public void publish(
            @NotNull(groups = Publish.class) Long documentId) {
        // ...
    }
}
~~~

Đây là **phương án thay thế**, không phải hai khai báo class đặt trong cùng source file. Khi hạ tầng Spring method validation hoạt động, lời gọi qua Spring proxy tới `publish(null)` có thể bị từ chối.

Lưu ý quan trọng:
- Phải có Bean Validation provider và một `MethodValidationPostProcessor` hoặc auto-configuration thích hợp.
- **Proxy** phải chặn được lời gọi. Gọi `this.publish(null)` từ chính bean thường bỏ qua proxy do self-invocation.
- `new DocumentService()` không có proxy Spring.
- Mặc định AOP method validation thường ném `ConstraintViolationException`. Tùy Spring configuration, nó có thể chuyển sang `MethodValidationException` khi bật chế độ adapt violations.
- Constraint không thay thế kiểm tra người gọi có quyền publish, dữ liệu có tồn tại, trạng thái có chuyển được hay không.

### 10.2. Đường validation của Spring MVC mới

Từ Spring Framework 6.1, Spring MVC có built-in method validation cho handler có constraint trực tiếp ở tham số/return value. Nếu controller còn mang `@Validated` ở class-level, có thể kích hoạt đường AOP method validation thay vì cơ chế MVC built-in. Hướng dẫn Spring cho trường hợp muốn built-in method validation là **gỡ `@Validated` class-level khỏi controller**, sau đó dùng annotation phù hợp ở tham số.

Bởi vậy, khi học groups, nên ưu tiên ví dụ `@Validated(Group.class)` **trực tiếp trên DTO parameter** của endpoint nếu mục đích đơn giản là chọn group cho request object.

## 11. Nhóm Default, nhóm kế thừa và cấu trúc nhóm

Có hai cách chính để kết hợp quy tắc chung và riêng.

### Cách A: yêu cầu tường minh hai nhóm ở endpoint

~~~java
@Validated({Default.class, Create.class})
~~~

Ưu điểm:
- Dễ quan sát endpoint nào chạy những rule nào.
- Không kéo theo các constraint không mong muốn ở nơi khác.
- Dễ dùng cho một vài endpoint có chính sách rõ ràng.

Nhược điểm:
- Mọi điểm kích hoạt phải chọn đúng; có thể bỏ quên `Default.class` khi copy code.

### Cách B: group interface kế thừa nhóm chung

~~~java
import jakarta.validation.groups.Default;

public interface Create extends Default {}
public interface Update extends Default {}
~~~

Trong thiết kế này, yêu cầu `Create.class` cũng bao hàm các constraint thuộc group kế thừa `Default`, theo cơ chế **group inheritance** của Jakarta Validation. Vì vậy `@Validated(Create.class)` cũng xét constraint Default. Để so sánh công bằng với cách A, hãy lưu ý là chúng là **hai thiết kế thay thế**; nếu đã định nghĩa `Create extends Default`, bảng ở mục 5 (giả sử các group độc lập) không còn áp dụng nguyên xi.

Ưu điểm:
- Giảm nguy cơ quên nhóm chung.
- Phù hợp khi **mọi** lần kiểm tra Create/Update phải bao gồm Default.

Nhược điểm:
- Có thể kéo theo ràng buộc chung ở cả những luồng mà bạn muốn kiểm tra một phần dữ liệu.
- Cần hiểu inheritance khi kết hợp group sequence và cascade.
- Khi mô hình nhóm phức tạp, người đọc phải tra quan hệ interface để biết chính xác constraint nào chạy.

**Khuyến nghị thiết kế:** Chọn **một** quy ước cho module và ghi lại trong tài liệu kỹ thuật. Đừng pha trộn ngầm hai kiểu khiến người sửa endpoint không thể dự đoán rule được thực thi.

## 12. `@GroupSequence`: khi cần thứ tự nhóm

Nếu validation cần hai pha:

1. Kiểm tra những rule cơ bản như bắt buộc/cú pháp.
2. Chỉ khi pha 1 thành công mới kiểm tra rule đắt hoặc chuyên biệt.

Hãy dùng một **group sequence**:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

public interface Publish {}

@GroupSequence({Default.class, Publish.class})
public interface PublishChecks {}
~~~

Trong một chương trình hoàn chỉnh, đặt các interface này ở file và package tương ứng; đây là **fragment thiết kế**.

Dùng:

~~~java
validator.validate(bean, PublishChecks.class);
~~~

hoặc:

~~~java
@Validated(PublishChecks.class)
~~~

Khi kiểm tra sequence `PublishChecks`, provider đánh giá `Default` trước. Nếu có violation ở bước này, các constraint của `Publish` **không được đánh giá**. Nếu bước 1 đạt, mới tiếp tục Publish. Vì vậy một request có email sai có thể chỉ nhận lỗi email, mặc dù `reviewed=false` cũng sai theo Publish.

**Không giống với**:

~~~java
@Validated({Default.class, Publish.class})
~~~

Cú pháp nhiều group ở trên **không cam kết thứ tự** và không tự dừng nhóm sau khi nhóm trước thất bại; chỉ group sequence có thứ tự và hành vi short-circuit theo các nhóm đã khai báo.

Chú ý:
- Không định nghĩa group sequence có vòng lặp.
- Nếu đang **định nghĩa lại Default của một class bằng `@GroupSequence` trên chính class đó**, quy tắc của đặc tả khác với sequence interface ở ví dụ; sequence phải bao gồm chính bean class theo quy định.
- Group sequence hữu ích cho hiệu năng và thông báo lỗi theo pha, không phải thay thế toàn bộ state machine nghiệp vụ.

## 13. Cascade và chuyển nhóm cho đối tượng con

Một request Create có thể chứa địa chỉ, còn khi Publish cần kiểm tra địa chỉ theo quy tắc chặt hơn.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;

interface Publish {}
interface VerifyAddress {}

class DeliveryAddress {
    @NotBlank(groups = VerifyAddress.class)
    private String city;
}

class DocumentWithDelivery {
    @NotNull(groups = Publish.class)
    @Valid
    @ConvertGroup(from = Publish.class, to = VerifyAddress.class)
    private DeliveryAddress address;
}
~~~

Đây là **mô hình minh họa**, không phải ứng dụng chạy độc lập.

Khi validate `DocumentWithDelivery` với nhóm `Publish`:
- `address == null`: vi phạm `@NotNull(Publish)`; `@Valid` bỏ qua cascade tới null.
- `address != null`: `@NotNull` đạt và `@Valid` cascade.
- `@ConvertGroup` yêu cầu nhóm Publish tại association được đổi thành `VerifyAddress` để kiểm tra `city` của bean con.

Nếu bỏ `@ConvertGroup`, cascade mặc định mang group đang được dùng xuống đối tượng con; constraint của `city` chỉ nằm ở `VerifyAddress` sẽ không tự chạy khi group đầu vào là Publish. Nếu bỏ `@Valid`, conversion group không có điểm cascade thích hợp.

Với list/map, có thể dùng container element constraints:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

private List<@NotNull(groups = Publish.class) @Valid DeliveryAddress> stops;
~~~

Chú ý:
- `@NotNull` trên **element** cấm phần tử null, **không cấm chính list null**.
- `@Valid` trên element cascade vào bean con khi element khác null.
- Để cấm list null/rỗng, thêm constraint ở **container**, ví dụ `@NotEmpty(groups=Publish.class)`.
- Chọn group còn quyết định `@NotNull` có chạy hay không: chỉ validate `Create` không tự kiểm tra constraint được đánh dấu `Publish`.

## 14. Với PATCH, không nên dùng group một cách máy móc

Nhóm Update thường thích hợp với **PUT** hoặc một form cập nhật đầy đủ. Đối với **PATCH** thay đổi từng field, hai request có ý nghĩa khác nhau:

~~~json
{"title":"New title"}
~~~

và:

~~~json
{"title":null}
~~~

Request thứ nhất có thể có nghĩa: cập nhật title, **giữ nguyên email**. Request thứ hai có thể có nghĩa: **xóa title** hoặc gửi giá trị không hợp lệ. Nếu deserialize cả hai vào cùng DTO với field nullable, nhiều trường hợp không phân biệt được “không gửi” và “gửi null”.

Dùng `@NotBlank(groups=Update.class)` trên tất cả field của một PATCH DTO có thể làm request chỉ sửa một field bị từ chối vì các field khác null. Có thể thiết kế:

- Một `CreateRequest` với dữ liệu bắt buộc đầy đủ.
- Một `ReplaceRequest` cho PUT, có ràng buộc đầy đủ.
- Một `PatchRequest` lưu thông tin **presence** của các field, ví dụ qua patch command, JsonNode hoặc một cơ chế có thể phân biệt absent/explicit null.
- Validate riêng **giá trị có mặt**, áp dụng thay đổi lên đối tượng hiện tại, rồi kiểm tra toàn trạng thái nghiệp vụ.

Groups không tự phát hiện property nào xuất hiện trong JSON. Đừng tạo `Patch` group rồi mặc định nó giải quyết toàn bộ khác biệt giữa missing và null.

## 15. Chọn groups hay tách DTO?

| Tiêu chí | DTO dùng nhóm Create/Update | DTO riêng theo thao tác |
| --- | --- | --- |
| Shape dữ liệu rất giống nhau | Thường phù hợp | Có thể trùng lặp |
| Chỉ vài constraint khác nhau | Gọn và minh bạch | Có thể dư mã |
| Cấu trúc request khác nhiều | Dễ trở nên khó hiểu | Thường rõ ràng hơn |
| PATCH với dữ liệu sparse | Không tự giải quyết absent/null | Thường phù hợp khi kết hợp presence model |
| Kiểm soát field được phép ghi | Cần cơ chế khác ngoài groups | DTO riêng giới hạn field tốt hơn |
| Dùng nhiều bước Publish/Approve/Dispatch | Hữu ích khi bước nào cũng gần cùng model | Phù hợp nếu từng command có cấu trúc khác |
| Tái sử dụng nhóm cho service validation | Có thể thuận tiện | Tùy contract service |

Một kiến trúc kết hợp thường tốt:

~~~text
HTTP API
  |
  +-- CreateDocumentRequest -> nhóm Default/Create (hoặc Default)
  |
  +-- UpdateDocumentRequest -> nhóm Default/Update (hoặc Default)
  |
  +-- PublishDocumentCommand -> nhóm Publish
  |
  +-- ApproveDocumentCommand -> nhóm Approve
  |
  v
Service: kiểm tra quyền, trạng thái, idempotency, transaction
  |
  v
Database: unique, foreign key, concurrent consistency
~~~

**Tách DTO không có nghĩa loại bỏ group**, và dùng group không phải lý do để tạo một “God DTO” chứa mọi field của hệ thống.

## 16. Validation groups không phải state machine hay authorization

Giả sử client gửi:

~~~json
{"id":12,"title":"Ready","contactEmail":"a@example.com","reviewed":true}
~~~

Nếu request đạt `@Validated({Default.class, Publish.class})`, kết quả chỉ chứng minh:
- Các constraint thuộc nhóm được chọn đã đạt.
- Những quy tắc khác, không được khai báo hoặc thuộc group khác, có thể chưa được kiểm tra.

Nó **không chứng minh**:
- Client là reviewer hợp lệ.
- Document ID 12 thực sự tồn tại.
- Document đang ở trạng thái được phép publish.
- Không có yêu cầu phê duyệt còn thiếu.
- Transaction đã commit hoặc DB không có race condition.
- Một dữ liệu đầu vào vẫn hợp lệ sau khi trạng thái server thay đổi.

Phân biệt các tầng:

| Tầng | Nhiệm vụ |
| --- | --- |
| JSON parse/data binding | Tạo kiểu Java phù hợp từ input |
| Jakarta Validation | Kiểm tra constraint đã khai báo và group được yêu cầu |
| Spring Security/authorization | Người dùng có quyền thực hiện thao tác? |
| Service/domain policy | Đối tượng có tồn tại, trạng thái chuyển được, dữ liệu nhất quán? |
| Transaction/database | Tính duy nhất, khóa, khóa ngoại, transaction và xung đột đồng thời |

Không gắn `groups = Admin.class` rồi dùng việc validate đạt để xác nhận user có quyền admin; bất kỳ caller nào có thể gửi dữ liệu đạt constraint đó. Phân quyền phải được đánh giá từ identity và chính sách truy cập.

## 17. Lỗi thường gặp khi lựa chọn nhóm

1. **Quên `Default`:** `@Validated(Update.class)` làm các `@Email` chỉ thuộc Default không chạy, nếu Update không kế thừa Default.
2. **Đặt `@NotNull` không ghi groups trên ID:** Tạo mới cần ID null nhưng lại thất bại ở Default. Chuyển constraint sang Update hoặc dùng DTO tách biệt.
3. **Chỉ gọi constructor rồi kỳ vọng annotation hoạt động:** Cần `Validator.validate` hoặc framework kích hoạt validation.
4. **Đổi từ `@Valid` sang `@Validated` rồi quên cascade:** Spring `@Validated` chọn group; với bean con cần `@Valid` trên association và có thể cần `@ConvertGroup`.
5. **Giả định `@Validated({A.class, B.class})` kiểm tra A trước B:** Nếu cần thứ tự, dùng `@GroupSequence`.
6. **Dùng group nhưng vẫn cho client cập nhật field không được phép:** Groups không phải mass-assignment protection.
7. **Tưởng `@NotBlank(groups=Publish.class)` trên một property sẽ chạy ở mọi endpoint:** Chỉ chạy khi Publish hoặc group liên quan được yêu cầu.
8. **Không có Bean Validation provider:** Các annotation có thể không tạo hiệu ứng như mong muốn trong Spring.
9. **Trộn `javax.validation` và `jakarta.validation`:** Spring 6/Boot 3 sử dụng Jakarta namespace; cần dependency tương thích.
10. **Giả định tất cả lỗi HTTP là `MethodArgumentNotValidException`:** Method constraints trong MVC 6.1+ có thể đi theo built-in method validation và sinh `HandlerMethodValidationException`.
11. **Cho rằng AOP method validation chạy khi gọi `this.method()`:** Self-invocation thường bỏ qua proxy.
12. **Tạo quá nhiều nhóm chuyên biệt trùng chức năng:** Gây khó đọc và rất dễ thiếu constraint khi thêm endpoint mới.
13. **Dùng nhóm Update cho PATCH mà không phân biệt field vắng mặt:** Dễ chặn request hợp lệ hoặc cho phép xóa trường quan trọng.
14. **So thứ tự của `Set<ConstraintViolation>`:** Không bảo đảm; sort khi test.
15. **Lưu constraint định dạng nhưng quên kiểm tra nghiệp vụ:** Email đúng cú pháp không có nghĩa email tồn tại; `reviewed=true` do client gửi không xác nhận đã review.
16. **Đặt `@AssertTrue` và tưởng nó cấm null:** Nếu Boolean bắt buộc, kết hợp `@NotNull`.
17. **Tưởng `@Valid` bắt buộc object con khác null:** Cascade bỏ qua reference null; dùng `@NotNull` với group thích hợp nếu bắt buộc.

## 18. Bộ test tối thiểu cho Create, Update và tác vụ riêng

Trong một ứng dụng thực, nên kiểm thử cả **Jakarta Validator** và **Spring MVC boundary**.

| Trường hợp | Nhóm | Kết quả mong đợi |
| --- | --- | --- |
| Create có `id=null`, title/email hợp lệ | Default+Create | Đạt |
| Create có `id != null` | Default+Create | Lỗi ID |
| Create có email sai | Default+Create | Lỗi email Default |
| Create chỉ chọn Create, email sai | Create độc lập | Email **không bị kiểm tra** (thể hiện lý do cần Default) |
| Update không có ID | Default+Update | Lỗi ID |
| Update title blank | Default+Update | Lỗi title |
| Publish `reviewed=false` | Default+Publish | Lỗi reviewed |
| Publish `reviewed=null` | Default+Publish | Lỗi reviewed do NotNull |
| Publish `reviewed=true` và ID hợp lệ | Default+Publish | Đạt nếu các field khác hợp lệ |
| Approve không có approver | Approve | Lỗi approver |
| Một DTO có nested bean cần group riêng | Publish với ConvertGroup | Group được truyền đúng vào child |
| JSON sai kiểu `id` | Bất kỳ | Lỗi deserialize/binding **trước** validation |
| Gọi service thông qua proxy | Nhóm method validation | Constraint được thực thi nếu cấu hình đầy đủ |
| Self-invocation trong cùng bean | Nhóm method validation | Có thể **bỏ qua** AOP interceptor |
| Group sequence Default rồi Publish | PublishChecks | Publish không chạy nếu Default đã lỗi |

**Thiết kế assertion:** So sánh property path, code/violation count hoặc loại exception phù hợp. Tránh phụ thuộc thứ tự lỗi, ngôn ngữ mặc định, hoặc thứ tự key JSON không được API cam kết.

### 18.1. Test MVC bằng MockMvc

Trong Spring Boot, một integration test thường thực hiện:
- POST Create hợp lệ và khẳng định HTTP 200 hoặc 201 **theo controller bạn định nghĩa**.
- POST Create có ID khác null và khẳng định HTTP 400.
- PUT Update thiếu ID và khẳng định HTTP 400.
- POST Publish chưa review và khẳng định HTTP 400.
- POST Create có email sai để kiểm tra nhóm Default không bị bỏ qua.
- Thử request thiếu body hoặc JSON không đúng kiểu để kiểm tra lỗi binding.
- Nếu có `@ControllerAdvice`, khẳng định error schema của ứng dụng (không so message tùy locale khi không cần).

Không nên coi thử HTTP 400 là đủ để chứng minh đúng **group**: cần ít nhất một test chứng minh một rule **được chọn** và một rule **không được chọn** trong cùng tình huống.

## 19. Câu hỏi ôn tập

**Câu 1.** Một DTO có `@NotNull(groups=Update.class) Long id`. Khi Create, `id=null` có lỗi không?

**Đáp:** Không, nếu chỉ kiểm tra Create/Default và không có constraint khác cấm null; `@NotNull` ở Update không được chọn.

**Câu 2.** `@Email String email` không có `groups`. Endpoint chỉ dùng `@Validated(Create.class)`, với Create là marker interface độc lập. `email="invalid"` có bị lỗi không?

**Đáp:** Không từ `@Email` Default trong lượt chỉ kiểm tra Create. Dùng `@Validated({Default.class, Create.class})` hoặc thiết kế Create kế thừa Default.

**Câu 3.** Muốn kiểm tra `id == null` ở Create và `id != null` ở Update thì khai báo gì?

**Đáp:**

~~~java
@Null(groups = Create.class)
@NotNull(groups = Update.class)
Long id;
~~~

**Câu 4.** Muốn Publish chỉ được chạy sau khi Default không có lỗi, dùng `@Validated({Default.class, Publish.class})` đủ chưa?

**Đáp:** Chưa; nhiều group trong một danh sách không bắt buộc có thứ tự. Dùng `@GroupSequence({Default.class, Publish.class})` trên một sequence interface rồi chọn sequence đó.

**Câu 5.** Một đơn hàng có address child. Validate parent bằng Publish, trong child constraint chỉ thuộc StrictAddress. Cần gì?

**Đáp:** Đặt `@Valid` trên association và `@ConvertGroup(from=Publish.class, to=StrictAddress.class)` nếu cần đổi group khi cascade; nếu child bắt buộc, thêm `@NotNull(groups=Publish.class)`.

**Câu 6.** Một controller Create dùng chung DTO chứa cả trường chỉ dành cho approval. Có nhất thiết phải thêm Approval group không?

**Đáp:** Không. Nếu approval có cấu trúc dữ liệu khác, tách DTO/command chuyên biệt có thể rõ ràng hơn. Group phù hợp khi nhiều ngữ cảnh dùng gần như cùng một mô hình.

**Câu 7.** Khi controller có `@Validated` trên class và dự án Spring MVC 6.1+, có thể ảnh hưởng đến built-in method validation không?

**Đáp:** Có. Spring khuyến nghị bỏ class-level `@Validated` trên controller nếu muốn dùng built-in MVC method validation, đồng thời chọn nhóm trên DTO parameter nếu cần.

**Câu 8.** Khi PATCH chỉ gửi một trường và DTO không phân biệt absent/null, group Update có bảo đảm sửa đúng không?

**Đáp:** Không. Cần mô hình PATCH biểu diễn trường có mặt, chọn ràng buộc phù hợp và merge/validate trạng thái ở service.

**Câu 9.** Nếu request vượt qua `@Validated(Approve.class)`, có thể bỏ qua authorization ở service không?

**Đáp:** Không. Validation groups kiểm tra nội dung dữ liệu, không xác minh danh tính hay quyền phê duyệt.

**Câu 10.** Trong ví dụ Java ở mục 8, vì sao `validCreate` có `reviewed=null` và `approver=null` vẫn hợp lệ?

**Đáp:** Vì trong lượt `Default+Create`, constraint `@NotNull`/`@AssertTrue` trên reviewed thuộc Publish và `@NotBlank` trên approver thuộc Approve; chúng không được chọn.

## 20. Checklist trước khi đưa lên production

- [ ] Mỗi constraint có group phù hợp với mục đích nghiệp vụ.
- [ ] Nhóm `Default` được xử lý nhất quán: chọn tường minh hoặc inheritance.
- [ ] Mỗi endpoint Create, Update, Publish/Approve chọn đúng group.
- [ ] DTO request không cho ghi các field mà caller không được phép chỉnh.
- [ ] Dữ liệu lồng nhau có `@Valid` và group conversion khi thực sự cần.
- [ ] Không nhầm nhóm chuyên biệt với permission/state transition.
- [ ] Có provider Jakarta Validation và Spring tích hợp đúng.
- [ ] Hiểu proxy AOP hoặc built-in MVC method validation đang được dùng.
- [ ] Error handler bao quát lỗi binding, argument validation, method validation.
- [ ] Có test hợp lệ, không hợp lệ, các group kết hợp và các rule Default.
- [ ] PATCH xử lý missing/explicit null rõ ràng; service và DB kiểm soát tính nhất quán.

## 21. Tổng kết

- **Group là nhãn cho constraint**, do Jakarta Validation định nghĩa. Spring `@Validated` là một cách chọn group khi framework kích hoạt validation.
- **Create** thường cấm client tự gửi ID, **Update** thường yêu cầu ID, còn tác vụ như **Publish/Approve** có các quy tắc riêng.
- Nếu group `Create`, `Update` độc lập, chọn chúng **không tự kiểm tra Default**. Đây là nguồn lỗi thiết kế phổ biến nhất.
- Dùng `@Validated({Default.class, Create.class})` hoặc inheritance theo quy ước thống nhất; dùng `@GroupSequence` khi thực sự cần thứ tự kiểm tra.
- Dùng `@Valid` cho cascade và `@ConvertGroup` khi cần đổi group trên đối tượng con.
- Chọn **DTO riêng** khi shape Create/Update/Patch/Publish khác nhau lớn.
- Groups không thay thế business validation, authorization hay kiểm soát transaction.
- Trước khi kết thúc, luôn chạy test qua `Validator` và qua Spring MVC/service tại đúng điểm kích hoạt.

### Tài liệu tham khảo

- Jakarta Validation 3.1 Specification – Group definitions, group inheritance, group sequences và group conversion: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation – `Default` group: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/default
- Jakarta Validation – `@GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groupsequence
- Jakarta Validation – `@ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/convertgroup
- Hibernate Validator 8 Reference Guide – Grouping constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework – Java Bean Validation và method validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC – Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
