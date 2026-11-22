# @Pattern và @Email: kiểm tra cú pháp dữ liệu trong Jakarta Bean Validation và Spring Framework

## 1. Mục tiêu: kiểm tra chuỗi đúng khuôn dạng, không suy diễn tính xác thực

Trong một API Spring, hai trường nhập liệu có vẻ giống nhau nhưng bản chất quy tắc khác nhau:

- Mã ưu đãi phải có dạng `ABC-1234`, tức ba chữ cái Latin in hoa, dấu gạch nối và bốn chữ số. Đây là **quy tắc cú pháp do ứng dụng tự định nghĩa**, phù hợp với `@Pattern`.
- Email đăng ký phải có cấu trúc địa chỉ email hợp lệ theo bộ kiểm tra của Bean Validation provider. Đây là **quy tắc cú pháp email thông dụng**, phù hợp với `@Email`.

Hai annotation chuẩn nằm trong package `jakarta.validation.constraints`:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Pattern;

class ContactRequest {
    @Email
    String email;

    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    String inviteCode;
}
```

Cả hai kiểm tra **biểu diễn văn bản (`CharSequence`)** sau khi Java đã nhận được giá trị. Chúng **không xác thực danh tính**, không tự truy cập DNS/database, không kiểm tra email có thể nhận thư, không tạo bảo đảm mã ưu đãi tồn tại hoặc người gửi sở hữu nó.

Mấu chốt của bài là phân biệt ba câu hỏi:

1. **Chuỗi có đúng cú pháp không?** → `@Pattern` hoặc `@Email`.
2. **Người dùng có bắt buộc nhập trường này không?** → kết hợp `@NotNull`, `@NotBlank` hoặc `@NotEmpty` theo kiểu dữ liệu.
3. **Giá trị có thật, được phép dùng, và thuộc về người dùng không?** → kiểm tra nghiệp vụ, database và quy trình xác minh riêng.

Lưu ý về hệ thư viện: Spring Framework 6 / Spring Boot 3 dùng namespace **`jakarta.validation.*`**. Các dự án Spring cũ có thể dùng `javax.validation.*`; tránh trộn annotation từ hai namespace với provider không tương thích.

## 2. @Pattern: ràng buộc bằng Java regular expression

`@Pattern` có một tham số bắt buộc `regexp`. Giá trị `CharSequence` phải khớp biểu thức chính quy theo quy ước của `java.util.regex.Pattern`. Theo đặc tả Jakarta Validation, **giá trị `null` được xem là hợp lệ** đối với `@Pattern`; phải thêm constraint khác khi trường bắt buộc nhập.

Ví dụ:

```java
@Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
private String inviteCode;
```

Ở đây:

- `[A-Z]`: một chữ cái Latin viết hoa A–Z.
- `{3}`: đúng ba lần.
- `-`: dấu gạch nối ký tự.
- `[0-9]`: một chữ số ASCII từ 0 đến 9.
- `{4}`: đúng bốn lần.

Một constraint `@Pattern` dùng việc khớp **toàn bộ chuỗi** theo hợp đồng validator, nên `ABC-1234` đạt; `xABC-1234`, `ABC-1234x`, `abc-1234` và `ABC-123` đều không đạt. Không dùng logic `find()` (tìm chuỗi con) để suy ra hành vi mặc định của `@Pattern`.

### 2.1. Bảng kiểm tra cú pháp

| Giá trị `inviteCode` | `@Pattern(regexp="[A-Z]{3}-[0-9]{4}")` | Lý do |
| --- | --- | --- |
| `"ABC-1234"` | Đạt | Đúng số ký tự và thứ tự |
| `"XYZ-0000"` | Đạt | `0000` là bốn chữ số hợp lệ về cú pháp |
| `"abc-1234"` | Vi phạm | Mẫu yêu cầu chữ hoa |
| `"AB-1234"` | Vi phạm | Thiếu một chữ cái |
| `"ABCD-1234"` | Vi phạm | Thừa một chữ cái |
| `"ABC_1234"` | Vi phạm | Sai ký tự phân cách |
| `"ABC-123"` | Vi phạm | Thiếu một chữ số |
| `" ABC-1234 "` | Vi phạm | Có khoảng trắng thừa |
| `""` | Vi phạm | Mẫu không cho phép chuỗi rỗng |
| `null` | Đạt | `@Pattern` không áp đặt tính bắt buộc |

**Kết luận quan trọng:** nếu mã ưu đãi là tùy chọn, `null` được phép nhưng chuỗi rỗng `""` sẽ bị từ chối với pattern này. Nếu giao diện muốn coi ô trống như không nhập, quy định bước chuẩn hóa đầu vào cho nhất quán; đừng vô tình dựa vào việc form binder có trim hay không.

### 2.2. Các thuộc tính của @Pattern

`@Pattern` cung cấp các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `regexp` | Regex bắt buộc, tuân theo cú pháp Java regex |
| `flags` | Cờ điều khiển regex, mặc định tập rỗng |
| `message` | Mẫu thông báo khi vi phạm |
| `groups` | Nhóm validation được áp dụng |
| `payload` | Metadata mở rộng; không thay đổi điều kiện khớp |

Ví dụ muốn chấp nhận chữ thường và chữ hoa:

```java
import jakarta.validation.constraints.Pattern;

class CouponRequest {
    @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}",
        flags = Pattern.Flag.CASE_INSENSITIVE,
        message = "Mã phải có dạng ABC-1234"
    )
    String code;
}
```

`Pattern.Flag` ở đây là **enum bên trong annotation `jakarta.validation.constraints.Pattern`**, không phải `java.util.regex.Pattern`. Các cờ khác có thể gặp: `MULTILINE`, `DOTALL`, `COMMENTS`, `UNICODE_CASE`. Chỉ thêm cờ khi có chủ đích; nhất là `CASE_INSENSITIVE` và `UNICODE_CASE` có thể mở rộng tập ký tự được chấp nhận. Đối với định danh ASCII cần chính xác, dùng lớp ký tự rõ ràng và kiểm thử trường hợp Unicode.

### 2.3. Regex trong source Java phải escape đúng hai tầng

Nếu muốn chuỗi dạng `ABC-1234` nhưng dùng `\\d` để chỉ một chữ số theo Java regex, trong **literal Java** cần ghi:

```java
@Pattern(regexp = "[A-Z]{3}-\\d{4}")
String code;
```

Trong literal Java, hai dấu `\\` tạo một dấu `\` đưa vào regex; sau đó engine regex hiểu `\\d` theo cú pháp của nó. Nếu gõ `"[A-Z]{3}-\d{4}"` trong source Java, compiler báo `illegal escape character`.

Có thể tránh nhầm bằng cách dùng `[0-9]`. Với dấu chấm thật trong email domain, nguồn Java cần `"\\."` để regex hiểu literal `.`, thay vì ký tự wildcard `.`.

Với regex đang yêu cầu khớp toàn bộ input, không bắt buộc thêm `^` và `$`. Nếu chủ động dùng anchor khi viết regex khác, hãy hiểu khác biệt giữa `^`/`$`, multiline mode và `\\A`/`\\z`; đừng kỳ vọng anchor tự bảo vệ mọi đoạn mã sử dụng `find()`.

### 2.4. Regex thực tế nên hẹp và có giới hạn

Ví dụ handle chỉ cho phép 3–12 ký tự gồm chữ thường, chữ số và dấu gạch dưới, chữ đầu là chữ thường:

```java
@Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
String handle;
```

Regex trên đã giới hạn **tập ký tự và chiều dài**. Với trường chỉ cần ràng buộc độ dài mà không có bộ ký tự đặc thù, dùng `@Size`; với chuỗi bắt buộc có chữ, dùng `@NotBlank`. Đừng tạo regex quá dài để làm thay toàn bộ parser dữ liệu phức tạp.

Regex có thể gây tốn CPU với mẫu có lặp lồng nhau trên input dài (catastrophic backtracking). Ví dụ mẫu có nhiều nhóm lặp chồng chéo trên chuỗi không khớp có thể làm thời gian xử lý tăng mạnh. Giới hạn kích thước request, thiết kế regex tuyến tính khi có thể, kiểm thử đầu vào dài/xấu, và cân nhắc parser chuyên dụng với định dạng phức tạp.

## 3. @Email: kiểm tra địa chỉ email theo provider

`@Email` được chuẩn hóa trong Jakarta Bean Validation:

```java
import jakarta.validation.constraints.Email;

class SignupRequest {
    @Email
    String contactEmail;
}
```

Theo hợp đồng chuẩn:

- Giá trị được kiểm tra là **`CharSequence`**, ví dụ `String`.
- `null` **hợp lệ**. Muốn bắt buộc nhập, phải kết hợp một constraint khác.
- Địa chỉ phải có dạng email được coi là well-formed theo provider.
- **Định nghĩa chính xác thế nào là email hợp lệ được để cho Bean Validation provider quyết định.** Vì thế không nên coi `@Email` là triển khai đầy đủ và thống nhất tuyệt đối của mọi tình huống RFC email.
- `regexp` mặc định là `".*"`, tức không thêm ràng buộc regex riêng ngoài tiêu chí email do provider áp dụng.

Điều này giải thích vì sao các địa chỉ khác thường như local part có dấu đặc biệt, địa chỉ quốc tế hóa, domain không thông dụng, hoặc cú pháp có trích dẫn có thể được chấp nhận/từ chối khác nhau giữa provider/phiên bản.

**`@Email` chỉ kiểm tra cú pháp, không xác nhận hộp thư hoạt động.** Một chuỗi có cấu trúc hợp lệ như `unknown@example.com` vẫn có thể không đại diện cho một tài khoản có thể nhận email; hơn nữa `example.com` là tên miền dùng cho ví dụ tài liệu. Không dùng kết quả `@Email` làm bằng chứng người gửi sở hữu địa chỉ.

### 3.1. @Email không thay @NotBlank

Để email là một trường **bắt buộc và cần có nội dung**, viết:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

class AccountRequest {
    @NotBlank(message = "Vui lòng nhập email")
    @Email(message = "Địa chỉ email không đúng định dạng")
    String email;
}
```

`@NotBlank` từ chối `null`, `""` và chuỗi chỉ có khoảng trắng, trong khi `@Email` chịu trách nhiệm kiểm tra cú pháp email. Với email tùy chọn, chỉ `@Email` cho phép `null`; chính sách ứng dụng cần nói rõ chuỗi rỗng được diễn giải thế nào.

Một số provider, bao gồm những cấu hình Hibernate Validator phổ biến, chấp nhận `""` đối với `@Email`; đặc tả chỉ cam kết chắc chắn rằng `null` được phép và để tiêu chí cú pháp chi tiết cho provider. Vì vậy không dựa vào `@Email` một mình để bắt buộc email, và viết test thực tế cho `""` theo provider đang chạy.

### 3.2. Email có thể thêm regex bổ sung

`@Email` cũng có `regexp` và `flags`. Mẫu này sẽ áp dụng **thêm** điều kiện regex bên cạnh việc kiểm tra cú pháp email của provider.

Ví dụ ứng dụng nội bộ chỉ cho địa chỉ trong một domain cụ thể:

```java
@Email(
    regexp = "[^@]+@example\\.com",
    message = "Phải dùng email thuộc example.com"
)
String workEmail;
```

Giải thích:

- `@Email` vẫn đánh giá địa chỉ có cú pháp email theo provider.
- `regexp` chỉ cho chuỗi có dạng một phần trước `@` và domain `example.com`.
- Regex phân biệt hoa/thường nếu không chỉ định cờ. Nếu chính sách coi domain không phân biệt hoa/thường, cần chuẩn hóa hoặc cấu hình phù hợp.
- Ví dụ `example.com` chỉ là tên miền minh họa; ứng dụng thật cần quy tắc domain tổ chức chính thức.
- **Regex domain chưa chứng minh người dùng thuộc tổ chức** và có thể không xử lý alias, subdomain, internationalized domain, địa chỉ nội bộ theo chính sách thực tế. Xác thực domain và chứng minh sở hữu địa chỉ nên thực hiện bằng quy trình ứng dụng riêng.

Không viết một regex RFC email đồ sộ chỉ vì muốn “nghiêm ngặt nhất”. `@Email` cộng một vài điều kiện nghiệp vụ hẹp thường dễ hiểu, dễ kiểm thử hơn. Nếu chính sách phức tạp (quản lý allowlist domain, alias, tenant, xác minh mã OTP), tách khỏi annotation regex hoặc viết custom constraint có ngữ nghĩa rõ.

### 3.3. Những gì @Email không đảm bảo

| Yêu cầu | `@Email` hỗ trợ? | Cách xử lý khi cần |
| --- | --- | --- |
| Có cấu trúc email phù hợp provider | Có | `@Email` |
| Không được bỏ trống | Không tự bảo đảm | `@NotBlank` |
| Chiều dài theo policy ứng dụng | Không tự bảo đảm mọi giới hạn | `@Size`/kiểm tra kích thước phù hợp |
| Domain đang có DNS/MX | Không | Kiểm tra mạng khi thật sự cần, xử lý DNS có MX/SMTP fallback |
| Hộp thư tồn tại | Không | Không thể suy ra chắc chỉ từ cú pháp/DNS |
| Người dùng sở hữu địa chỉ | Không | Gửi link/mã xác minh |
| Địa chỉ chưa được đăng ký | Không | Unique constraint ở database và xử lý race condition |
| Không thuộc domain bị chặn | Không | Quy tắc domain/allowlist/blocklist riêng |
| Không dùng địa chỉ tạm thời | Không | Dịch vụ/chính sách đánh giá rủi ro, có thể không hoàn hảo |
| Không có nguy cơ abuse | Không | Rate limiting, phát hiện bất thường và chính sách gửi thư |

Kiểm tra DNS/SMTP đồng bộ trong `ConstraintValidator` của mỗi request thường gây latency, side effect và khả năng phụ thuộc mạng; cần cân nhắc thật kỹ. Hầu hết quy trình đăng ký dùng syntax validation trước, tạo trạng thái **unverified**, gửi thư xác minh và chỉ chuyển sang **verified** sau khi người dùng chứng minh quyền nhận.

## 4. Bảng so sánh @Pattern và @Email

| Tiêu chí | `@Pattern` | `@Email` |
| --- | --- | --- |
| Mục đích | Đúng một biểu thức regex do ứng dụng khai báo | Đúng cú pháp email theo provider |
| Đầu vào | `CharSequence` | `CharSequence` |
| Giá trị `null` | Hợp lệ | Hợp lệ |
| Ràng buộc bắt buộc | `regexp` | Không; `regexp` mặc định `".*"` |
| `flags` | Cờ cho regex chính | Cờ cho regex bổ sung |
| Quy tắc phụ thuộc provider | Engine regex theo Java; tích hợp provider kiểm tra | Định nghĩa email well-formed do provider quyết định |
| Dữ liệu điển hình | Mã định danh, mã bưu chính theo chính sách, username | Địa chỉ email |
| Thay thế `@NotBlank` | Không | Không |
| Kiểm tra dữ liệu có thật | Không | Không |
| Kiểm tra quyền sở hữu | Không | Không |

Có thể sử dụng `@Pattern` trực tiếp để ràng buộc một format email chuyên biệt nhưng **không nên coi regex tùy ý là thay thế hoàn toàn cho `@Email`**. Ngược lại, không dùng `@Email` để xác nhận mã khách hàng hay định dạng bất kỳ chỉ vì nó có tham số `regexp`.

## 5. Thiết kế DTO: phối hợp nhiều constraint đúng ngữ nghĩa

### 5.1. Trường bắt buộc và trường tùy chọn

Ví dụ DTO nhận yêu cầu:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class SignupForm {
    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    // Mã mời tùy chọn: null hợp lệ; nếu có phải đúng khuôn dạng.
    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    private String inviteCode;

    @NotBlank
    @Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
    private String handle;

    // Getter/setter hoặc constructor binding phù hợp.
}
```

`@Size(max=254)` trong ví dụ là **quy định chiều dài ứng dụng** thường gặp, không phải bằng chứng tổng quát rằng mọi địa chỉ email phù hợp RFC chắc chắn được xử lý chính xác. Với Unicode, số ký tự, UTF-16 code unit và số byte UTF-8 không luôn bằng nhau; xác định rõ hệ thống dùng chuẩn đo độ dài nào và test giá trị biên.

Ý nghĩa các field:

- `email`: không rỗng/toàn blank, hợp cú pháp theo provider, không vượt giới hạn length do ứng dụng đặt.
- `inviteCode`: có thể null; nếu có giá trị, phải khớp chuỗi mã mời. Chuỗi `""` không khớp pattern.
- `handle`: bắt buộc có nội dung và hợp đúng tập ký tự/độ dài đã đặt.

Một trường hợp “có mã mời nhưng muốn coi chuỗi trắng như không nhập” cần **định nghĩa bước normalization** rõ trước validation, ví dụ trim rồi chuyển chuỗi rỗng thành null ở binder/mapper. Không giả định JSON deserializer, form binder và method validation đều tự làm việc đó.

### 5.2. @NotNull, @NotEmpty, @NotBlank và @Size khác gì?

| Constraint | `null` | `""` | `"   "` | Mục tiêu |
| --- | --- | --- | --- | --- |
| `@NotNull` | Vi phạm | Đạt | Đạt | Không cho `null` |
| `@NotEmpty` | Vi phạm | Vi phạm | Đạt | Không cho rỗng |
| `@NotBlank` | Vi phạm | Vi phạm | Vi phạm | Không cho trắng |
| `@Size(min=1)` | Đạt | Vi phạm | Đạt | Độ dài tối thiểu, không tự cấm null |
| `@Pattern(regexp="[A-Z]+")` | Đạt | Vi phạm | Vi phạm | Cú pháp theo regex |
| `@Email` | Đạt | Tùy chi tiết provider | Thường bị từ chối; theo provider | Cú pháp email |

Không áp dụng `@NotBlank` lên `Integer` hoặc collection; nó dành cho `CharSequence`. Với collection, dùng `@NotEmpty` hoặc `@Size(min=1)`. Nhiều constraint cùng thất bại có thể sinh nhiều violation cho **cùng một field**, vì vậy UI không nên đếm số violation rồi giả định đó là số field lỗi.

### 5.3. Phải chọn đúng kiểu dữ liệu

`@Pattern` và `@Email` đều thiết kế cho `CharSequence`. Không gắn chúng trực tiếp lên `Long phone`, `UUID id`, `LocalDate` hoặc kiểu domain object tùy ý rồi giả định validator sẽ tự chuyển về `String`. Ràng buộc áp dụng sai kiểu có thể gây `UnexpectedTypeException` hoặc exception cấu hình lúc validation.

Với số điện thoại, mã định danh có số 0 ở đầu hoặc chuỗi có dấu `+`, nên dùng `String` nếu cần giữ đúng biểu diễn. Sau khi kiểm tra cú pháp, áp dụng phân tích riêng theo quốc gia/định dạng nếu nghiệp vụ cần; đừng tưởng `@Pattern(regexp="[0-9]{10}")` là quy tắc số điện thoại quốc tế.

## 6. Java 17+ chạy độc lập: quan sát @Pattern, @Email và kết quả violation

Ví dụ dưới sử dụng **Jakarta Validation 3.x** và provider **Hibernate Validator 8.x**, không cần khởi động Spring MVC để quan sát cốt lõi của constraint. Lệnh chạy dùng Maven tạo classpath, sau đó dùng `javac` và `java` như một chương trình Java thông thường.

### 6.1. Tạo pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>pattern-email-demo</artifactId>
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
    </dependencies>
</project>
```

`hibernate-validator` kéo theo Jakarta Validation API và các dependency transitive. Trong ứng dụng thông thường, Hibernate Validator có thể dùng Jakarta Expression Language để nội suy một số message template. Ở chương trình CLI nhỏ này, ta chủ động dùng `ParameterMessageInterpolator` của Hibernate Validator để tránh phụ thuộc EL. Đây là thành phần của provider, không phải API portable của Jakarta Validation; với message template cần biểu thức EL, phải cấu hình thích hợp.

### 6.2. Tạo tệp PatternEmailDemo.java

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class PatternEmailDemo {

    public static final class Signup {
        @NotBlank
        @Email
        private final String email;

        // Mã mời tùy chọn; null không vi phạm Pattern.
        @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
        private final String inviteCode;

        @Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
        private final String handle;

        public Signup(String email, String inviteCode, String handle) {
            this.email = email;
            this.inviteCode = inviteCode;
            this.handle = handle;
        }
    }

    private static void show(
            String label, Set<? extends ConstraintViolation<?>> violations) {
        List<String> failures = violations.stream()
                .map(v -> v.getPropertyPath() + ":"
                        + v.getConstraintDescriptor()
                           .getAnnotation()
                           .annotationType()
                           .getSimpleName())
                .sorted()
                .toList();
        System.out.println(label + " -> " + failures);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Signup valid = new Signup(
                    "alice@example.com", "ABC-1234", "alice_1");
            Signup optional = new Signup(
                    "alice@example.com", null, null);
            Signup missing = new Signup(
                    null, null, null);
            Signup invalid = new Signup(
                    "wrong-address", "ab-12", "A");

            show("valid", validator.validate(valid));
            show("optional", validator.validate(optional));
            show("missing", validator.validate(missing));
            show("invalid", validator.validate(invalid));

            show("property inviteCode",
                    validator.validateProperty(invalid, "inviteCode"));
            show("candidate good",
                    validator.validateValue(
                            Signup.class, "inviteCode", "XYZ-0034"));
            show("candidate bad",
                    validator.validateValue(
                            Signup.class, "inviteCode", "XYZ-34"));
        }
    }
}
```

Các chuỗi input đều cố ý đơn giản, tránh trường hợp email lạ mà từng provider có thể phân tích khác nhau. Hàm `show` in **property path + tên annotation** đã sắp xếp, để không dựa vào thứ tự của `Set<ConstraintViolation<?>>` hoặc bản dịch message theo locale.

### 6.3. Biên dịch, chạy và đối chiếu

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" PatternEmailDemo.java
java -cp ".:$CP" PatternEmailDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content classpath.txt -Raw).Trim()
javac -encoding UTF-8 -cp $cp PatternEmailDemo.java
java -cp ".;$cp" PatternEmailDemo
```

**Stdout kỳ vọng** (bỏ qua log provider/Maven nếu môi trường có in thêm):

```text
valid -> []
optional -> []
missing -> [email:NotBlank]
invalid -> [email:Email, handle:Pattern, inviteCode:Pattern]
property inviteCode -> [inviteCode:Pattern]
candidate good -> []
candidate bad -> [inviteCode:Pattern]
```

Phân tích:

- `valid`: email có dạng cơ bản; mã mời và handle đều đúng regex.
- `optional`: hai trường `inviteCode` và `handle` được phép `null` vì `@Pattern` không đặt yêu cầu bắt buộc.
- `missing`: email null vi phạm `@NotBlank`; `@Email` cho phép null. Hai field khác vẫn hợp lệ.
- `invalid`: email không có cấu trúc email, invite code và handle không khớp regex; sắp xếp đường dẫn giúp stdout rõ ràng.
- `validateProperty(invalid, "inviteCode")` chỉ kiểm tra constraint trên giá trị hiện tại của property.
- `validateValue(Signup.class, "inviteCode", "XYZ-0034")` kiểm tra candidate mà không cần một bean mới; `XYZ-34` không đủ bốn chữ số.
- Bản thân `Validator` không trim, lowercase, sửa email hoặc cập nhật object; nếu cần chuẩn hóa, làm một bước rõ ràng trước validation.

**Giới hạn kết quả ví dụ:** đây là kết quả suy ra theo constraint và provider Hibernate Validator 8.x đã chọn, không phải cam kết mọi provider có cùng chi tiết phân tích email/format thông báo. Với CI, chạy mã trên JDK và bản dependency thật của dự án.

## 7. Kết hợp @Pattern và @Email với Spring MVC

Trong Spring MVC, `@Pattern` và `@Email` thường được gắn lên DTO/form rồi chạy khi controller dùng `@Valid` hoặc `@Validated`. Việc đặt annotation trên field **không tự động kiểm tra mỗi lần Java setter được gọi**; phải có bước validation được kích hoạt.

Ví dụ DTO dùng được với JSON deserializer thông dụng:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public class CreateAccountRequest {
    @NotBlank
    @Email
    private String email;

    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    private String inviteCode;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getInviteCode() { return inviteCode; }
    public void setInviteCode(String inviteCode) {
        this.inviteCode = inviteCode;
    }
}
```

Controller minh họa (nằm trong `@RestController`; cần các import Spring/Jakarta tương ứng):

```java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        var fields = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .toList();
        return ResponseEntity.badRequest().body(fields);
    }

    // Service tiếp tục kiểm tra business rules và phát email xác minh.
    return ResponseEntity.ok().build();
}
```

Ý nghĩa luồng:

1. JSON body được đọc và chuyển thành `CreateAccountRequest` bởi `HttpMessageConverter` (thường Jackson) trước.
2. Bean Validation kiểm tra các field phù hợp khi có provider và validator được cấu hình.
3. Với chữ ký controller dùng `BindingResult` ngay sau tham số DTO trong trường hợp Spring hỗ trợ, code có thể đọc `FieldError` và trả phản hồi lỗi.
4. Khi hợp lệ về cú pháp, service vẫn phải xác nhận quy tắc nghiệp vụ, lưu dữ liệu, kiểm tra unique trong database và xác minh địa chỉ email.

Spring MVC có hai đường validation cần phân biệt: validation trên `@ModelAttribute`/`@RequestBody`/`@RequestPart` và method validation trên tham số/giá trị trả về. Tùy chữ ký method, Spring có thể phát sinh `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException`; vì vậy không nên khẳng định mọi vi phạm sẽ luôn đi qua duy nhất một kiểu exception.

### 7.1. Form và JSON có thể khác nhau ở bước binding

Với form, input ban đầu có thể là `String`; converter/binder có thể trim, parse hoặc chuyển blank thành null nếu được cấu hình. Với JSON, Jackson và chiến lược deserialize quyết định biểu diễn Java nhận được. Khi bước chuẩn hóa làm dữ liệu thay đổi trước validation, cùng một chuỗi người dùng gõ có thể cho kết quả khác giữa form/JSON.

Chẳng hạn:

- `inviteCode=null` → `@Pattern` đạt.
- `inviteCode=""` → pattern mã trên vi phạm.
- `inviteCode=" ABC-1234 "` → vi phạm nếu giữ nguyên; có thể đạt sau khi chuẩn hóa `strip()`, nếu nghiệp vụ cho phép trim.
- `email=null` → `@Email` đạt, `@NotBlank` vi phạm nếu có.
- `email=""` → `@NotBlank` vi phạm; `@Email` phụ thuộc provider ở trường hợp empty.

Hãy quyết định rõ chuỗi nào được chấp nhận, chuẩn hóa theo quy định và test cả hai đường nhập liệu. Cẩn thận với việc tự động lowercase **toàn bộ** email: phần domain không phân biệt chữ hoa/thường trong DNS, nhưng tính tương đương phần local-part và Unicode có quy tắc tinh vi; không áp đặt “mọi email giống nhau sau lowercase” chỉ dựa trên `@Email`.

### 7.2. Validation groups theo thao tác

Mỗi annotation có thuộc tính `groups`. Ví dụ mã ưu đãi chỉ bắt buộc có định dạng khi tạo account, nhưng một loại update khác không kiểm tra trường đó:

```java
interface OnCreate {}

class AccountCommand {
    @NotBlank(groups = OnCreate.class)
    @Email(groups = OnCreate.class)
    String email;

    @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}",
        groups = OnCreate.class
    )
    String inviteCode;
}
```

Gọi `validator.validate(command, OnCreate.class)` để áp dụng các constraint trong group này. Nếu controller dùng Spring `@Validated(OnCreate.class)`, Spring sẽ chọn group tương ứng trong ngữ cảnh validation hỗ trợ.

**Lưu ý:** khi đã yêu cầu một group custom, các constraint chỉ thuộc `Default` không mặc nhiên chạy kèm, trừ khi có group inheritance/sequence/conversion được khai báo phù hợp. Với update kiểu PATCH, phân biệt field vắng mặt, field null và field có chuỗi mới; `@Pattern` một mình không đủ để xác định ý nghĩa “xóa giá trị”.

### 7.3. Kiểm tra thủ công và hiển thị lỗi

Có thể inject `jakarta.validation.Validator` vào service:

```java
@Service
public class ContactValidationService {
    private final jakarta.validation.Validator validator;

    public ContactValidationService(
            jakarta.validation.Validator validator) {
        this.validator = validator;
    }

    public boolean validCandidateCode(String code) {
        return validator.validateValue(
                CreateAccountRequest.class, "inviteCode", code
        ).isEmpty();
    }
}
```

Đoạn trên là **mã tích hợp**, không phải chương trình Java độc lập; cần import `@Service` và class DTO từ project. `validateValue` kiểm tra candidate theo constraint field, không kiểm tra toàn bộ bean/cross-field hoặc gửi email.

Với UI, dùng property path, mã lỗi và thông điệp phù hợp locale; hạn chế log giá trị người dùng nhập, nhất là khi có token hoặc thông tin cá nhân. `BindingResult.getFieldErrors()` phân loại lỗi gắn với field; đồng thời xử lý `getGlobalErrors()` nếu có constraint cấp object. Thông báo message có thể thay đổi theo locale, nên không dùng chuỗi đã dịch làm khóa logic của hệ thống.

## 8. Phạm vi kiểm tra cú pháp so với kiểm tra nghiệp vụ

### 8.1. Mã ưu đãi đúng regex vẫn có thể vô hiệu

Chuỗi `ABC-1234` có thể vượt qua `@Pattern` nhưng vẫn không được phép sử dụng nếu:

- Mã không tồn tại trong database.
- Mã hết hạn hoặc hết lượt.
- Mã không thuộc tài khoản/nhóm người dùng hiện tại.
- Mã từng được sử dụng hoặc đã bị vô hiệu.
- Mã thuộc tenant khác và việc lộ thông tin làm ảnh hưởng phân quyền.

Hướng xử lý là: validate cú pháp ở DTO, sau đó service kiểm tra tồn tại/trạng thái/ownership bằng transaction và concurrency control thích hợp. Không tự coi `@Pattern` là validation business.

### 8.2. Email đúng cú pháp vẫn cần xác minh

Một quy trình đăng ký hợp lý:

1. Bind JSON/form vào DTO.
2. Validate email bắt buộc và cú pháp.
3. Chuẩn hóa theo chính sách rõ ràng, kiểm tra giới hạn chiều dài hợp đồng.
4. Tạo tài khoản ở trạng thái email chưa xác minh.
5. Gửi token/link xác minh ngắn hạn có giới hạn lần thử và bảo vệ chống lạm dụng.
6. Chỉ đánh dấu verified sau khi xác nhận đúng quyền nhận.
7. Xử lý email đổi địa chỉ, hết hạn token, gửi lại và tranh chấp uniqueness trong database.

Không bắt buộc kiểm tra trực tiếp SMTP mỗi lần người dùng nhập email; nhiều server từ chối probing và kết quả dễ gây false positive/false negative. Rà soát quyền riêng tư khi log email và thao tác xác minh.

### 8.3. Xử lý Unicode và tính nhất quán

Regex ASCII như `[A-Z]` và `[0-9]` có mục đích giới hạn rõ. Nếu sản phẩm hỗ trợ tên có dấu, domain quốc tế hoặc mã chứa Unicode, xác định quy tắc Unicode normalize, case folding và equivalence trước khi chọn regex; kiểm tra cùng quy tắc ở backend và UI, tránh chỉ dựa vào HTML `pattern`.

HTML `input type="email"` và `pattern` của trình duyệt giúp phản hồi sớm nhưng **không bảo vệ server**: client có thể bỏ qua JavaScript, gửi HTTP trực tiếp hoặc dùng client khác. Constraint backend vẫn cần được thực thi. Khi một giá trị đi qua URL, JSON hoặc form encoding, kiểm tra đúng biểu diễn Java sau decode, không regex trực tiếp lên bytes ở sai tầng.

## 9. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `@Email` cho phép `null` | Đặc tả coi null là hợp lệ | Kết hợp `@NotBlank` nếu bắt buộc |
| `@Pattern` cho phép `null` nhưng từ chối `""` | Regex chỉ chạy trên giá trị không null | Xác định optional semantics và bước chuẩn hóa |
| `@Email` trả “hợp lệ” cho địa chỉ không tồn tại | Chỉ kiểm tra well-formed syntax | Dùng email verification |
| Email hợp lệ ở môi trường này, môi trường khác bị từ chối | Provider có ngữ nghĩa email không hoàn toàn giống nhau | Pin/test provider version và policy input |
| Java báo `illegal escape character` | Quên escape dấu gạch chéo trong Java literal | Viết `"\\d"` hoặc dùng `[0-9]` |
| Regex mã ưu đãi chấp nhận chuỗi ngoài ý muốn | Regex quá rộng, `.*`, cờ không phù hợp | Định nghĩa tập ký tự và số lượng cụ thể |
| Regex chậm trên input dài | Backtracking nhiều hoặc không giới hạn length | Ràng buộc kích thước request, đơn giản hóa regex, benchmark case xấu |
| `@Pattern` trên kiểu số nguyên ném exception | Constraint chỉ hỗ trợ `CharSequence` | Chọn `String` cho dữ liệu cú pháp hoặc custom constraint |
| Form hợp lệ nhưng service từ chối | Chuỗi đúng format nhưng mã không tồn tại/hết hạn | Tách syntax và business validation |
| API bỏ qua annotation | Chưa kích hoạt validator/provider hay dùng sai namespace | Cấu hình Jakarta provider và `@Valid`/`@Validated` |
| Spring trả lỗi 400 trước khi chạy Bean Validation | Body JSON sai cú pháp hoặc deserialize thất bại | Phân biệt parse error và constraint error |
| `@Email(regexp=...)` chặn domain hợp lệ | Regex policy quá hẹp/không hỗ trợ alias | Thống nhất domain policy, viết kiểm thử đại diện |
| `@Pattern` uppercase không chấp nhận lowercase | Cờ và quy tắc chuẩn hóa chưa rõ | Quy định canonical case, thêm flag hoặc normalize trước |
| UI regex đạt nhưng backend regex trượt | Khác engine regex, Unicode/flags/normalization | Coi server là nguồn quyết định, test mẫu trên Java |
| Email bị ghi log cùng form lỗi | Log toàn DTO/`getInvalidValue()` | Log mã lỗi/path, che dữ liệu nhạy cảm |
| Regex kiểm tra email “chuẩn RFC 100%” khó bảo trì | Format email có nhiều trường hợp hợp lệ/khác provider | Dùng `@Email` + policy hẹp và xác minh thực tế |

## 10. Bộ kiểm thử nên có

Để bảo đảm cả cú pháp và contract đầu vào, viết test theo các lớp:

**A. Unit test riêng cho @Pattern**

- Case hợp lệ, sai độ dài, sai ký tự, sai case, leading/trailing whitespace.
- Giá trị `null`, `""` và giá trị rất dài.
- Cờ `CASE_INSENSITIVE`/Unicode nếu đã bật.
- Test trường hợp regex xấu có thể khiến CPU tăng, nhất là khi input do client kiểm soát.

**B. Unit test riêng cho @Email**

- Email phổ biến như `alice@example.com`.
- Không có `@`, thiếu phần trước/sau `@`, chứa khoảng trắng không được phép.
- `null` và `""` theo chính provider.
- Địa chỉ quốc tế, subdomain, dấu `+` hoặc trích dẫn nếu hệ thống muốn hỗ trợ chúng.
- Khi đổi provider/version, chạy regression tests để phát hiện thay đổi phạm vi cú pháp.

**C. Integration test Spring MVC**

- `@Valid`/`@Validated` thực sự được kích hoạt.
- Body sai kiểu/JSON không parse được khác với violation email/regex.
- Cả `BindingResult`, exception handler và response status/message đáp ứng hợp đồng API.
- Chính sách normalize từ form và JSON nhất quán.
- Không trả raw email, token/mật khẩu hoặc stack trace trong body/log.
- Sau syntax validation, service vẫn kiểm tra state, uniqueness và verification đúng flow.

Một cách kiểm thử Jakarta Validator trực tiếp là gọi `validator.validateValue(Request.class,"inviteCode", candidate)` cho bộ giá trị biên, rồi assert số violation hoặc annotation type thay vì assert message dịch theo locale. Nhưng trong bước submit, phải chạy `validate(request)`/`@Valid` toàn DTO để không bỏ sót constraint khác.

## 11. Quy tắc chọn và ghi nhớ

- **Muốn chuỗi tuân theo cấu trúc tự định nghĩa** (mã, handle, phiên bản, số hiệu): bắt đầu với `@Pattern(regexp=...)`, giới hạn phạm vi rõ ràng.
- **Muốn địa chỉ có cú pháp email**: dùng `@Email`; nhớ rằng chi tiết email hợp lệ thuộc provider và null được phép.
- **Muốn field bắt buộc có nội dung**: thêm `@NotBlank`; `@Email`/`@Pattern` không tự thay thế yêu cầu bắt buộc.
- **Muốn giới hạn độ dài**: dùng `@Size` và quy định rõ độ dài xét theo biểu diễn nào nếu có Unicode.
- **Muốn kiểm tra mã có tồn tại, email được sở hữu, mã chưa hết hạn**: thực hiện kiểm tra nghiệp vụ, persistence và verification riêng.
- **Muốn vận hành đúng trong Spring**: cấu hình Bean Validation provider, dùng `@Valid`/`@Validated` đúng ngữ cảnh, tách binding/deserialization errors và constraint errors.
- **Muốn tránh sai khác môi trường**: kiểm thử input biên và pin version provider; giới hạn regex tránh backtracking nặng.

Chọn `@Pattern` khi bạn **sở hữu quy tắc cú pháp**; chọn `@Email` khi bạn cần **quy tắc địa chỉ email do provider triển khai**. Trong cả hai trường hợp, syntax validation là một lớp kiểm tra đầu vào, không phải bằng chứng dữ liệu đúng nghiệp vụ hoặc người dùng có quyền sử dụng dữ liệu đó.

### Tài liệu đối chiếu

- Jakarta Validation 3.1 API — `@Pattern`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Pattern.html
- Jakarta Validation 3.1 API — `@Email`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Email.html
- Jakarta Bean Validation specification, built-in constraints: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Java 17 regex `Pattern`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- Hibernate Validator 8 Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
