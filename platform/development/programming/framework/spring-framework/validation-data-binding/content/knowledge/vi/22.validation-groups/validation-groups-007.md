# Dừng chuỗi nhóm khi một giai đoạn có vi phạm: @GroupSequence trong Bean Validation

## 1. Bài toán: kiểm tra theo giai đoạn và dừng đúng lúc

Giả sử một API tiếp nhận thông tin đăng ký. Có ba tầng kiểm tra hợp lý:

1. **Đầu vào cơ bản**: tên không trắng, email có hình thức phù hợp, mật khẩu không rỗng.
2. **Quy tắc nghiệp vụ**: độ dài mật khẩu đạt yêu cầu hoặc các thuộc tính có mối quan hệ hợp lý.
3. **Xác nhận cuối**: người dùng đã chấp nhận điều khoản hoặc một điều kiện hoàn tất khác.

Nếu dữ liệu đầu vào cơ bản đã sai, việc tiếp tục kiểm tra nghiệp vụ có thể tạo thông báo gây nhiễu, thực hiện công việc không cần thiết hoặc yêu cầu dữ liệu mà giai đoạn trước chưa bảo đảm.

**Jakarta Bean Validation hỗ trợ chuỗi nhóm (group sequence)** bằng annotation `@GroupSequence`. Khi một nhóm trong chuỗi sinh **ít nhất một `ConstraintViolation`**, các nhóm **đứng sau nhóm đó trong chuỗi không được xử lý**.

Bài học này phân biệt rõ:
- Chọn **nhiều validation group** nhưng không yêu cầu thứ tự.
- Chọn **một group sequence** để kiểm tra tuần tự và dừng ở giai đoạn đầu tiên thất bại.
- **Dừng giữa các nhóm** và chế độ provider **fail-fast ở mức vi phạm đầu tiên**: hai cơ chế khác nhau.
- Cách kiểm chứng bằng Java 17+, Hibernate Validator/JUnit và Spring MVC `@Validated`.
- Những ngoại lệ cần hiểu: nhóm `Default`, validation lồng nhau, group conversion, nhóm được yêu cầu ngoài chuỗi, cấu hình sequence sai.

Ngữ cảnh ví dụ: Java 17+, `jakarta.validation.*` (Jakarta Bean Validation 3.x), Hibernate Validator 8 và Spring Framework 6+/Spring Boot 3.x. Với dự án cũ Spring Boot 2.x thường là `javax.validation.*`.

## 2. Quy tắc cốt lõi của group sequence

Một sequence mô tả **thứ tự các nhóm**, không mô tả trực tiếp thứ tự từng annotation:

```text
                  @GroupSequence({Basic, Policy, Confirm})
                                  |
                                  v
                        [Basic: kiểm tra]
                            /         \
                      Có lỗi?         Không lỗi
                         |                |
                         v                v
                    DỪNG CHUỖI       [Policy: kiểm tra]
                                       /           \
                                  Có lỗi?           Không lỗi
                                     |                  |
                                     v                  v
                                DỪNG CHUỖI        [Confirm: kiểm tra]
                                                        |
                                                   Kết thúc
```

Các quy tắc bắt buộc:

- **Giai đoạn đầu chạy trước giai đoạn sau** theo thứ tự trong mảng của `@GroupSequence`.
- **Nếu một giai đoạn có một hoặc nhiều vi phạm**, mọi nhóm nằm phía sau nó **trong chuỗi** bị bỏ qua.
- **Nếu giai đoạn hiện tại không có vi phạm**, engine được tiếp tục đến giai đoạn kế tiếp.
- **Nếu mọi giai đoạn đều hợp lệ**, tập vi phạm của lời gọi validate rỗng.
- **Trong một giai đoạn**, specification không đặt thứ tự cụ thể cho từng constraint, field hoặc property getter; mặc định không dừng ngay ở constraint đầu tiên sai.
- Mỗi constraint có thể nằm trong nhiều group. Khi một constraint đã được xử lý cho cùng đường đi trong cùng validation routine, không cần xử lý lặp chỉ vì group xuất hiện tiếp sau.

Hãy nhớ công thức:

**Có vi phạm ở nhóm thứ k → nhóm thứ k+1, k+2, ... của sequence không được kiểm tra.**

Đây là tính chất bảo đảm bởi Jakarta Bean Validation, không chỉ là cách Hibernate Validator tự tối ưu.

### 2.1. Ví dụ ba giai đoạn

| Giai đoạn | Group | Các quy tắc minh họa |
| --- | --- | --- |
| 1 | `InputChecks` | `@NotBlank username`, `@Email email`, `@NotBlank password` |
| 2 | `PolicyChecks` | `@Size(min = 8) password` |
| 3 | `ConsentChecks` | `@AssertTrue accepted` |

Tình huống có cả tên sai, mật khẩu quá ngắn và chưa chấp nhận điều khoản: chuỗi chỉ báo các lỗi ở **InputChecks**. Lỗi mật khẩu quá ngắn và điều khoản chưa chấp nhận vẫn **tồn tại trong dữ liệu**, nhưng provider chưa được yêu cầu đánh giá chúng ở giai đoạn sau.

Đây là lý do không nên diễn đạt group sequence là "đã kiểm tra toàn bộ object và chỉ giữ lỗi đầu". Nó thực sự **không thực hiện** các nhóm còn lại trong tuyến sequence.

## 3. Cách khai báo @GroupSequence trên interface

Nhóm validation được biểu diễn bằng Java interface. Một interface khác mang annotation `@GroupSequence` dùng làm **tên của quy trình có thứ tự**:

```java
import jakarta.validation.GroupSequence;

public final class Checks {
    private Checks() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}
}
```

Đây là một fragment minh họa. Khi gọi:

```java
validator.validate(request, Checks.Ordered.class);
```

provider mở rộng `Checks.Ordered` thành ba giai đoạn được khai báo, lần lượt `Input` → `Policy` → `Consent`. Ta **không** gắn constraint vào group `Ordered`; ta gắn vào các group thành phần.

**Lưu ý quan trọng về định nghĩa:** interface chứa `@GroupSequence` không nên trực tiếp kế thừa interface group khác và không nên được dùng trực tiếp làm group trên constraint. Tránh vòng phụ thuộc trực tiếp/gián tiếp giữa các sequence hoặc group inheritance; cấu hình vòng có thể gây `GroupDefinitionException` khi sử dụng.

Mảng bên trong `@GroupSequence` là **thứ tự xử lý**. Điều đó khác với mảng ở `groups` của constraint:

```java
@NotBlank(groups = {Checks.Input.class, Checks.Policy.class})
String field;
```

Ở đây một constraint thuộc **hai tập nhóm**, chứ không có quy định Input phải chạy trước Policy. Để có thứ tự và dừng, yêu cầu validate group `Checks.Ordered.class`.

### 3.1. Không truyền nhiều nhóm và kỳ vọng có cùng tác dụng

Hai lời gọi này **không tương đương**:

```java
// Không cam kết thứ tự, không yêu cầu dừng sau nhóm đầu lỗi:
validator.validate(request,
        Checks.Input.class,
        Checks.Policy.class,
        Checks.Consent.class);

// Có thứ tự và dừng khi nhóm hiện tại bị lỗi:
validator.validate(request, Checks.Ordered.class);
```

Trong lời gọi thứ nhất, các constraints ở cả ba nhóm được yêu cầu và thứ tự không được xác định bởi thứ tự tham số. Lời gọi thứ hai đặt một quy trình tuần tự: nếu Input có lỗi, Policy và Consent sẽ không chạy trong chuỗi.

Thêm `@Validated({Input.class, Policy.class})` trong Spring cũng chỉ chọn nhiều group; nó **không tự biến** hai group thành sequence.

## 4. Dừng theo giai đoạn không đồng nghĩa fail-fast theo constraint

Đây là hai cơ chế dễ bị nhầm nhất.

| Thuộc tính | Group sequence chuẩn | Fail-fast kiểu provider (ví dụ Hibernate Validator) |
| --- | --- | --- |
| Phạm vi dừng | Khi một **group/giai đoạn** thất bại, không chạy các group sau | Có thể dừng sau **vi phạm đầu tiên** |
| Có thứ tự giữa các giai đoạn? | Có: theo `@GroupSequence` | Không tự bảo đảm; phụ thuộc cách cấu hình |
| Nhiều lỗi trong giai đoạn hiện tại? | Có thể trả về nhiều lỗi | Thường chỉ trả một lỗi |
| Có thuộc chuẩn Jakarta Bean Validation? | **Có** | Cấu hình cụ thể của provider |
| Dùng khi nào? | Quy trình xác thực nhiều tầng, phụ thuộc điều kiện nền | Muốn giảm chi phí/ít lỗi trả về |
| Chứng minh bằng test | Giai đoạn sau không có lỗi khi giai đoạn trước sai | Lời gọi trả lỗi đầu tiên theo provider đang cấu hình |

Ví dụ `Input` có `username=" "` và `email="wrong"`. Với group sequence và provider ở cấu hình chuẩn, có thể nhận **hai vi phạm** ở Input. Provider không phải bỏ toàn bộ lỗi sau vi phạm đầu tiên **trong cùng một nhóm**. Nếu bật fail-fast của Hibernate Validator, kết quả có thể chỉ là **một** vi phạm, và không nên dự đoán nó thuộc username hay email khi chưa có quy tắc thứ tự khác.

Nếu ứng dụng cần hiển thị **tất cả lỗi cơ bản**, nhưng không hiển thị lỗi nâng cao cho đến khi cơ bản hợp lệ, dùng group sequence là cách phù hợp hơn bật fail-fast toàn cục.

## 5. Chọn nhóm Default ở đâu?

Jakarta có nhóm `jakarta.validation.groups.Default`. Constraint không khai báo `groups` sẽ thuộc `Default`.

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;

class BasicProfile {
    @NotBlank
    String name; // Tương đương groups = Default.class
}
```

Nếu gọi:

```java
validator.validate(profile);
```

provider yêu cầu nhóm Default. Nhưng nếu gọi `validator.validate(profile, Checks.Ordered.class)` và sequence **không chứa Default**, constraint chỉ thuộc Default có thể **không được chạy**.

Khi muốn kiểm tra constraint mặc định trước các nhóm nâng cao, một sequence trên interface có thể khai báo:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface BusinessChecks {}
interface ApprovalChecks {}

@GroupSequence({
    Default.class,
    BusinessChecks.class,
    ApprovalChecks.class
})
interface FullCheck {}
```

Nếu Default sai, BusinessChecks và ApprovalChecks không chạy. Nếu Default đạt, provider chuyển qua BusinessChecks và sau đó ApprovalChecks nếu cần.

**Không nhầm cách dùng interface và class:**
- `@GroupSequence` trên **interface** định nghĩa một group sequence để gọi tường minh (ví dụ `FullCheck.class`).
- `@GroupSequence` trực tiếp trên **bean class** có nghĩa **định nghĩa lại Default group sequence cho chính class đó**, với quy tắc khai báo khác; xem mục 11.

## 6. Ma trận đầu vào: lỗi ở đâu thì dừng ở đó

Xét object `Signup` có hai constraint ở nhóm Input, một constraint ở nhóm Policy và một ở Consent:

| Tình huống | Input | Policy | Consent | Kết quả với Ordered |
| --- | --- | --- | --- | --- |
| Username trắng; email sai; password ngắn; chưa đồng ý | **Sai** | Chưa kiểm tra | Chưa kiểm tra | Lỗi username, email |
| Input hợp lệ; password ngắn; chưa đồng ý | Đúng | **Sai** | Chưa kiểm tra | Lỗi password |
| Input và password hợp lệ; chưa đồng ý | Đúng | Đúng | **Sai** | Lỗi accepted |
| Mọi trường hợp lệ | Đúng | Đúng | Đúng | Không lỗi |

Các nhóm nằm sau **chưa được kiểm tra**, không phải được xem là "đúng". Nếu trả lại trạng thái từ API, có thể dùng từ "chưa kiểm tra" thay vì "đã đạt" để tránh hiểu sai.

### 6.1. Một nhóm có nhiều constraint: phải hiểu "giai đoạn"

Ví dụ Input gồm `@NotBlank username`, `@NotBlank password` và `@Email email`. Cả ba constraint thuộc cùng group, không có thứ tự xác định. Nếu username và email sai, provider có thể báo cả hai; không thể dùng `@GroupSequence` để ép "username phải kiểm tra trước email" khi chúng nằm **trong cùng group**.

Muốn tách hai bước thật sự, dùng hai group khác nhau (`RequiredFields` rồi `SyntaxFields`) và thêm vào sequence. Tuy nhiên cần tránh chia nhỏ quá mức: sẽ tạo nhiều nhóm, khó bảo trì và khó giải thích vì sao API mỗi lần chỉ báo một lỗi.

### 6.2. Group có dependency và kế thừa

Một group có thể kế thừa group khác:

```java
interface SimpleChecks {}
interface ExtendedChecks extends SimpleChecks {}
```

Khi yêu cầu `ExtendedChecks`, các constraint thuộc `SimpleChecks` cũng có thể được áp dụng theo quy tắc group inheritance. Do vậy mỗi **bước** của sequence có thể bao gồm nhiều constraint/group được mở rộng. Cần dựa trên group definition thực tế, không chỉ đếm số interface xuất hiện trong annotation.

Nếu định nghĩa chuỗi chứa quan hệ kế thừa tạo thứ tự vòng, provider có thể phát sinh `GroupDefinitionException`. Đừng định nghĩa các sequence vòng hoặc sử dụng interface sequence như group thông thường.

## 7. Ví dụ hoàn chỉnh Java 17+ với Maven và Hibernate Validator

Ví dụ này chạy **không cần Spring, không cần HTTP server**. Nó chứng minh group sequence dừng từng bước và chứng minh rõ sự khác biệt khi yêu cầu ba group độc lập.

Cần Java 17+, Maven, Jakarta Validation provider. Cấu trúc:

```text
ordered-validation-demo/
├── pom.xml
└── src/
    ├── main/java/example/StagedValidationDemo.java
    └── test/java/example/StagedValidationDemoTest.java
```

### 7.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>ordered-validation-demo</artifactId>
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

Các phiên bản được pin để ví dụ tái hiện ổn định; ở ứng dụng Spring Boot thực tế nên dùng BOM và `spring-boot-starter-validation`. Cần provider runtime; chỉ có API annotation thì không đủ để thực thi kiểm tra.

### 7.2. File src/main/java/example/StagedValidationDemo.java

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class StagedValidationDemo {
    private StagedValidationDemo() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}

    public record Signup(
            @NotBlank(groups = Input.class)
            String username,

            @Email(groups = Input.class)
            String email,

            @NotBlank(groups = Input.class)
            @Size(min = 8, groups = Policy.class)
            String password,

            @AssertTrue(groups = Consent.class)
            boolean accepted) {
    }

    public static Set<String> invalidFields(
            Validator validator,
            Signup signup,
            Class<?>... groups) {

        Set<ConstraintViolation<Signup>> violations =
                validator.validate(signup, groups);

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    private static void show(
            String label,
            Validator validator,
            Signup signup,
            Class<?>... groups) {

        String fields = invalidFields(validator, signup, groups)
                .stream()
                .sorted()
                .collect(Collectors.joining(","));

        System.out.println(label + "="
                + (fields.isEmpty() ? "OK" : fields));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Signup badInput = new Signup(
                    " ", "bad-email", "123", false);

            Signup badPolicy = new Signup(
                    "linh", "linh@example.com", "123", false);

            Signup badConsent = new Signup(
                    "linh", "linh@example.com", "strong123", false);

            Signup valid = new Signup(
                    "linh", "linh@example.com", "strong123", true);

            show("input-error", validator, badInput, Ordered.class);
            show("policy-error", validator, badPolicy, Ordered.class);
            show("consent-error", validator, badConsent, Ordered.class);
            show("all-valid", validator, valid, Ordered.class);

            // Không có sequence: ba nhóm được yêu cầu độc lập.
            show("unordered", validator, badInput,
                    Input.class, Policy.class, Consent.class);

            // Không constraint nào trong demo thuộc Default.
            show("default-only", validator, badInput);
        }
    }
}
```

Biên dịch/test và chạy trong thư mục `ordered-validation-demo`:

```bash
mvn -q test
mvn -q exec:java -Dexec.mainClass=example.StagedValidationDemo
```

Stdout từ các lời gọi `System.out.println` (không tính log tùy môi trường của Maven/provider):

```text
input-error=email,username
policy-error=password
consent-error=accepted
all-valid=OK
unordered=accepted,email,password,username
default-only=OK
```

Tại sao các dòng này đúng?

- `input-error=email,username`: tên trắng và email sai nên Input thất bại. Mật khẩu ngắn và `accepted=false` ở giai đoạn **sau** không được xử lý trong group sequence.
- `policy-error=password`: Input hợp lệ; Policy kiểm tra mật khẩu `"123"` dài chưa đủ 8. Consent tiếp tục bị bỏ qua dù `accepted=false`.
- `consent-error=accepted`: Input và Policy đều pass; Consent là bước đầu tiên có lỗi.
- `all-valid=OK`: cả ba nhóm vượt qua.
- `unordered=accepted,email,password,username`: khi gọi trực tiếp Input, Policy và Consent **không qua sequence**, tất cả bốn lỗi có thể xuất hiện.
- `default-only=OK`: demo không khai báo constraint nào thuộc Default; chỉ yêu cầu `Default` không tự kiểm tra các constraint thuộc ba nhóm khác.

Hàm `invalidFields` đưa về tên property dưới dạng `Set`; `show` sắp xếp tên trước khi in để output ổn định. Không được suy diễn thứ tự xử lý constraint từ thứ tự tên in trên màn hình.

**Điểm quan trọng:** bằng việc cho dữ liệu ở các nhóm sau cũng sai nhưng `Ordered` chỉ trả lỗi tại nhóm đầu tiên không đạt, ví dụ chứng minh hành vi dừng sequence — không chỉ che thông báo của nhóm sau.

## 8. Kiểm thử JUnit 5: chứng minh ba điểm dừng

Tạo file **src/test/java/example/StagedValidationDemoTest.java**:

```java
package example;

import java.util.Set;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StagedValidationDemoTest {

    private static Set<String> errors(
            Validator validator,
            StagedValidationDemo.Signup form,
            Class<?>... groups) {

        return StagedValidationDemo.invalidFields(
                validator, form, groups);
    }

    @Test
    void firstStageStopsBusinessAndConsentStages() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var form = new StagedValidationDemo.Signup(
                    " ", "bad-email", "123", false);

            assertEquals(Set.of("username", "email"),
                    errors(validator, form,
                            StagedValidationDemo.Ordered.class));

            // Gọi nhóm rời rạc: các lỗi nhóm sau vẫn xuất hiện.
            assertEquals(
                    Set.of("username", "email",
                            "password", "accepted"),
                    errors(validator, form,
                            StagedValidationDemo.Input.class,
                            StagedValidationDemo.Policy.class,
                            StagedValidationDemo.Consent.class));
        }
    }

    @Test
    void secondStageStopsConsentStage() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var form = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "123", false);

            assertEquals(Set.of("password"),
                    errors(validator, form,
                            StagedValidationDemo.Ordered.class));
        }
    }

    @Test
    void thirdStageRunsOnlyAfterEarlierStagesPass() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var needsConsent = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "strong123", false);
            assertEquals(Set.of("accepted"),
                    errors(validator, needsConsent,
                            StagedValidationDemo.Ordered.class));

            var complete = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "strong123", true);
            assertEquals(Set.of(),
                    errors(validator, complete,
                            StagedValidationDemo.Ordered.class));
        }
    }
}
```

Bộ test dùng `pom.xml` ở mục 7; JUnit Jupiter và Surefire đã được khai báo. Các assertion kiểm tra **tập property path** chứ không dựa vào thứ tự của `Set<ConstraintViolation<?>>` hoặc câu tiếng Anh có thể thay đổi theo locale.

Nếu muốn chứng minh ràng buộc sau **thực sự chưa được gọi**, không chỉ dựa vào tập lỗi trả về, có thể bổ sung một custom `ConstraintValidator` đếm số lần `isValid(...)` được gọi trong fixture kiểm thử. Tuy nhiên test dạng này cần xử lý state/thread-safety cẩn thận. Với hành vi chuẩn, việc nhóm sau bị bỏ qua đã được specification bảo đảm.

## 9. Tích hợp Spring MVC: dùng @Validated với sequence

Trong Spring MVC, một request có thể được validate bằng `@Validated` trên tham số DTO. Nếu muốn thứ tự/dừng, truyền **interface sequence**, không truyền ba group độc lập.

Giả sử Spring Boot 3.x đã có các dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Đây là **fragment trong pom.xml của ứng dụng Boot đã có parent/BOM**, không phải file Maven độc lập. Những Java file tiếp theo thuộc cùng ứng dụng và package được component scan.

### 9.1. Các nhóm và sequence

File **src/main/java/com/example/signup/SignupChecks.java**:

```java
package com.example.signup;

import jakarta.validation.GroupSequence;

public final class SignupChecks {
    private SignupChecks() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}
}
```

### 9.2. Request DTO có constraint ở từng giai đoạn

File **src/main/java/com/example/signup/SignupRequest.java**:

```java
package com.example.signup;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(groups = SignupChecks.Input.class)
        String username,

        @Email(groups = SignupChecks.Input.class)
        String email,

        @NotBlank(groups = SignupChecks.Input.class)
        @Size(min = 8, groups = SignupChecks.Policy.class)
        String password,

        @AssertTrue(groups = SignupChecks.Consent.class)
        boolean accepted) {
}
```

Trong ví dụ này, `@Email` được dùng ở giai đoạn Input. `@Email` đứng một mình không thay thế `@NotBlank` nếu email là trường bắt buộc; với hệ thống thật, thêm `@NotBlank(groups = Input.class)` cho email khi yêu cầu phải nhập email. Dữ liệu mẫu bên dưới luôn gửi một chuỗi email nên ví dụ tập trung vào cơ chế dừng chuỗi.

### 9.3. Controller chọn sequence

File **src/main/java/com/example/signup/SignupController.java**:

```java
package com.example.signup;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    @PostMapping("/signup")
    public ResponseEntity<Void> signup(
            @Validated(SignupChecks.Ordered.class)
            @RequestBody SignupRequest request) {

        // Chỉ đi tới đây khi các constraint được yêu cầu đều pass.
        return ResponseEntity.noContent().build();
    }
}
```

Dấu quan trọng nằm ở:

```java
@Validated(SignupChecks.Ordered.class)
@RequestBody SignupRequest request
```

Spring yêu cầu Bean Validation với group `Ordered`. Provider mở rộng sequence và áp dụng quy tắc dừng ở nhóm đầu tiên có lỗi. Nếu thay bằng:

```java
@Validated({
    SignupChecks.Input.class,
    SignupChecks.Policy.class,
    SignupChecks.Consent.class
})
@RequestBody SignupRequest request
```

thì đó là **ba nhóm được chọn mà không có trình tự dừng**. Đừng viết `@Valid @RequestBody` rồi kỳ vọng nó tự dùng `SignupChecks.Ordered`: `@Valid` thông thường yêu cầu `Default`, trừ khi cấu hình Default được định nghĩa lại theo cách khác.

### 9.4. Các phản hồi mong đợi

Với controller ở trên và Bean Validation provider đã cấu hình:

| JSON request | Giai đoạn đầu lỗi | Hành vi |
| --- | --- | --- |
| `{"username":" ","email":"bad-email","password":"123","accepted":false}` | Input | Thông thường 400, lỗi username và email |
| `{"username":"linh","email":"linh@example.com","password":"123","accepted":false}` | Policy | Thông thường 400, lỗi password; chưa kiểm tra Consent |
| `{"username":"linh","email":"linh@example.com","password":"strong123","accepted":false}` | Consent | Thông thường 400, lỗi accepted |
| `{"username":"linh","email":"linh@example.com","password":"strong123","accepted":true}` | Không có | 204 No Content |

**Không mặc định rằng response JSON chỉ chứa một lỗi.** Nếu nhóm Input có hai constraint sai, Spring có thể nhận hai `FieldError`. Tập lỗi trả về thể hiện **giai đoạn đầu tiên không đạt**, không nhất thiết một thông báo duy nhất.

Với `@RequestBody`, Jackson deserialize JSON **trước khi** Bean Validation kiểm tra. Nếu JSON không parse được hoặc field có kiểu không hợp lệ, có thể phát sinh `HttpMessageNotReadableException` trước khi sequence được xét. Khi validation đối tượng request thông thường thất bại và không có `BindingResult`/`Errors` ngay sau argument, Spring MVC thường ném `MethodArgumentNotValidException` và trả 400. Nếu controller method cần **method validation** vì có constraint trực tiếp trên tham số hoặc return value, Spring MVC 6.1+ có thể dùng `HandlerMethodValidationException`. Không gộp mọi exception thành một loại.

### 9.5. MockMvc integration test

File **src/test/java/com/example/signup/SignupControllerTest.java** trong ứng dụng Boot có `spring-boot-starter-test`:

```java
package com.example.signup;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SignupController.class)
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private static Set<String> fields(
            MethodArgumentNotValidException ex) {
        return ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .collect(Collectors.toSet());
    }

    @Test
    void stopsAfterInputHasViolations() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": " ",
                      "email": "bad-email",
                      "password": "123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                assertTrue(result.getResolvedException()
                        instanceof MethodArgumentNotValidException);
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("username", "email"), fields(ex));
            });
    }

    @Test
    void stopsAfterPolicyHasViolation() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("password"), fields(ex));
            });
    }

    @Test
    void reachesConsentAfterPriorGroupsPass() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "strong123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("accepted"), fields(ex));
            });
    }

    @Test
    void acceptsRequestThatPassesEveryStage() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "strong123",
                      "accepted": true
                    }
                    """))
            .andExpect(status().isNoContent());
    }
}
```

`@WebMvcTest` cần một ứng dụng Boot có cấu hình test hợp lệ, validation provider và component scan phù hợp. Khi có `@ControllerAdvice` tùy chỉnh hoặc method validation bổ sung, exception/status mapping có thể thay đổi; cần điều chỉnh test theo hợp đồng thật.

Hai điểm test quan trọng:
- Ở case Input sai, **không có** field error của password/accepted, dù dữ liệu của chúng cũng không đạt constraints nhóm sau.
- Ở case Policy sai, field error accepted chưa xuất hiện. Nếu lập trình viên vô tình thay `Ordered.class` bằng danh sách nhóm rời rạc, test sẽ phát hiện vì lỗi các nhóm sau cũng xuất hiện.

## 10. Định nghĩa lại Default group sequence trên bean class

Đôi khi không muốn controller phải biết interface `Ordered`, mà muốn **mỗi lần validate Default đối với class đó** luôn theo quy trình có thứ tự. Jakarta cho phép gắn `@GroupSequence` trực tiếp lên class.

Ví dụ fragment:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface ExtendedChecks {}

@GroupSequence({
    Profile.class,
    ExtendedChecks.class
})
class Profile {

    @NotBlank
    String displayName;

    @Size(min = 20, groups = ExtendedChecks.class)
    String biography;
}
```

Khi gọi `validator.validate(profile)` theo Default:
1. Constraints Default khai báo trên `Profile` được kiểm tra qua nhóm `Profile.class`.
2. Nếu `displayName` sai, giai đoạn `ExtendedChecks` không được chạy.
3. Nếu Default đạt, constraint độ dài biography thuộc ExtendedChecks được kiểm tra.

**Quy tắc đặc biệt rất quan trọng:** trên một **class** dùng để định nghĩa lại Default, sequence **phải chứa chính class đó** (ví dụ `Profile.class`). Không viết `@GroupSequence({Default.class, ExtendedChecks.class})` trực tiếp trên class `Profile` vì đó không phải cú pháp hợp lệ để redefinition và có thể gây `GroupDefinitionException`. Ngược lại, với **interface** định nghĩa sequence tường minh, `@GroupSequence({Default.class, ExtendedChecks.class})` là hợp lệ.

Định nghĩa lại Default của một class chỉ có hiệu lực **cục bộ** cho class đó: không tự áp sequence Default ấy lên mọi bean con qua `@Valid`. Vì vậy cần kiểm thử object graph thay vì suy đoán "toàn bộ cây đều theo đúng sequence của cha".

### 10.1. Có nên dùng class-level redefinition mọi nơi?

Không nhất thiết. Ưu điểm là mọi lượt validate Default của class có quy trình thống nhất. Nhược điểm là Default không còn đơn giản; người đọc cần tìm annotation ở class để hiểu tại sao một số constraint không được thực hiện. Với endpoint có ngữ cảnh rõ ràng, định nghĩa sequence bằng interface và chọn bằng `@Validated(Ordered.class)` thường dễ hiểu.

Nếu sequence phụ thuộc động vào trạng thái bean, Hibernate Validator có extension `@GroupSequenceProvider` để cung cấp default group sequence động. Đây là tính năng **provider-specific**, không phải API chuẩn portable của Jakarta; chỉ dùng khi thực sự cần và test theo provider đang dùng.

## 11. Dừng chuỗi khi validation lan sang bean con

Một giai đoạn không chỉ bao gồm constraint trên root. Khi một field được đánh dấu `@Valid`, provider có thể cascade tới bean con với group đang được yêu cầu.

```java
import jakarta.validation.Valid;
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface Basic {}
interface Advanced {}

@GroupSequence({Basic.class, Advanced.class})
interface RegistrationFlow {}

class Address {
    @NotBlank(groups = Basic.class)
    String city;
}

class Registration {
    @Valid Address address;

    @Size(min = 8, groups = Advanced.class)
    String password;
}
```

Nếu `address.city = " "` và `password = "123"`, gọi:

```java
validator.validate(registration, RegistrationFlow.class);
```

sẽ gặp lỗi ở **Basic của Address**, nên **Advanced trên Registration** không chạy trong sequence. Nói cách khác, điều kiện "nhóm Basic pass" có thể bao gồm cả object graph được cascade, không chỉ trường của root.

Tuy nhiên:
- `@Valid` không tự làm bean con khác null; `address=null` khiến cascade bỏ qua. Dùng `@NotNull(groups = Basic.class)` nếu cần.
- Nếu thiếu `@Valid` ở `Registration.address`, Basic của Address có thể không được kiểm tra theo đường đi từ Registration, khiến sequence đi tiếp khác mong đợi.
- Mỗi giai đoạn có thể chứa nhiều object và nhiều vi phạm; provider không bảo đảm thứ tự kiểm tra giữa các thuộc tính trong cùng nhóm.

### 11.1. @ConvertGroup và thứ tự

Jakarta hỗ trợ `@ConvertGroup` trên một đường `@Valid` để ánh xạ group khi đi vào bean con. Sequence được **mở rộng thành các group thành phần trước khi chuyển group**, do đó không nên giả định `@ConvertGroup(from = RegistrationFlow.class, ...)` hoạt động giống việc chuyển cả một sequence: thuộc tính `from` phải trỏ tới group phù hợp sau khi sequence đã được mở rộng.

Ví dụ (fragment):

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Container {
    @Valid
    @ConvertGroup(from = Default.class, to = AddressChecks.class)
    Address address;
}

interface AddressChecks {}
```

Điều này chuyển nhóm Default khi cascade qua `address` sang AddressChecks; nó không thay đổi thứ tự các nhóm trên root, và cũng không tự tạo thêm constraint trên bean con.

Nếu kết hợp sequence, inheritance và conversion ở nhiều cấp, cần unit test với dữ liệu cố tình sai ở các nhóm khác nhau để biết chính xác nhóm nào được thực hiện.

## 12. Ngoại lệ quan trọng: nhóm được yêu cầu cả ngoài sequence

Đây là trường hợp dễ làm kết quả khác ý định "dừng ở lỗi nhóm đầu".

Giả sử `Flow` gồm `Input` rồi `Policy`:

```java
@GroupSequence({Input.class, Policy.class})
interface Flow {}
```

Thông thường:

```java
validator.validate(request, Flow.class);
```

Nếu Input sai, Policy bị bỏ qua **trong Flow**. Nhưng nếu gọi:

```java
validator.validate(
        request,
        Flow.class,
        Policy.class);
```

`Policy` đồng thời được yêu cầu như **một group độc lập ngoài Flow**. Khi ấy các constraint của Policy có thể vẫn được kiểm tra dù Input không đạt. Specification không hứa rằng yêu cầu group bên ngoài sẽ bị cơ chế stop của sequence khác vô hiệu hóa.

**Quy tắc thực hành:** nếu muốn một pipeline dừng rõ ràng, **chỉ yêu cầu group sequence như một đầu vào validation**, thay vì vừa yêu cầu sequence vừa yêu cầu một hoặc nhiều group thành phần một cách độc lập.

Tương tự, khi một group được yêu cầu nhiều lần qua inheritance hoặc sequence, provider dùng quy tắc tránh kiểm tra lặp một constraint trên cùng đường đi; đừng suy diễn số lần thực thi đơn giản từ số lần tên group xuất hiện.

## 13. Vì sao không nên dùng group sequence thay service workflow?

Group sequence hữu ích khi các ràng buộc có tính **đồng bộ, kiểm tra dữ liệu sẵn có**. Nó không thay thế quy trình nghiệp vụ nhiều bước thực sự:

- Không tự mở transaction, lưu dữ liệu, khóa bản ghi hoặc cấp quyền.
- Không biến Bean Validation thành hệ thống thực thi command/side effect theo thứ tự.
- Không bảo đảm lỗi từ database/network xảy ra dưới dạng `ConstraintViolation` và sẽ được xử lý như lỗi dữ liệu.
- Không có hợp đồng trả trạng thái chi tiết "stage 2 đang chờ" nếu ứng dụng không tự xây dựng response.
- Không phải cách bảo mật thông tin: dù chưa chạy một số ràng buộc, API vẫn phải tránh để lộ dữ liệu nhạy cảm và xác thực quyền truy cập riêng.

Custom `ConstraintValidator` nên có hành vi ổn định, tránh side effect. Nếu một kiểm tra "nâng cao" cần truy vấn dữ liệu ngoài hoặc tiêu tốn tài nguyên lớn, group sequence giúp giảm số lần gọi khi giai đoạn cơ bản thất bại, nhưng thời gian, tính nhất quán dữ liệu và retry vẫn là trách nhiệm của service/application.

## 14. Kiểm thử đầy đủ: ngăn false positive

Bộ test tốt cần các ca sau:

| Ca | Input | Assertion |
| --- | --- | --- |
| Lỗi nhóm đầu | Input sai, Policy sai, Consent sai | Chỉ lỗi Input trong group sequence |
| Nhiều lỗi cùng nhóm đầu | Username và email sai | Nhận lỗi của cả hai (khi không bật fail-fast) |
| Nhóm đầu đạt, nhóm hai sai | Password ngắn | Chỉ lỗi Policy; Consent chưa xét |
| Hai nhóm đầu đạt, nhóm ba sai | Accepted=false | Chỉ lỗi Consent |
| Mọi nhóm đạt | Dữ liệu đúng | Không vi phạm |
| Nhóm rời rạc | Yêu cầu Input, Policy, Consent riêng | Các lỗi thuộc cả ba nhóm có thể xuất hiện |
| Chỉ validate Default | Constraints chỉ thuộc nhóm tùy biến | Không tự chạy nhóm tùy biến |
| Sequence chứa Default | Default sai, Advanced sai | Advanced bị bỏ qua |
| Re-defined Default trên class | @GroupSequence chứa chính class | Mặc định dùng thứ tự mới |
| Class default sequence không chứa class | Cấu hình sai | Có thể báo GroupDefinitionException |
| Nested @Valid sai trong giai đoạn đầu | Address.city trắng | Dừng trước giai đoạn sau trên root |
| Nested bean null | Thiếu @NotNull | Cascade có thể bỏ qua, cần test hiện diện |
| Nhóm được yêu cầu ngoài sequence | Flow cùng Policy | Không được giả định Policy luôn bị bỏ qua |
| Provider fail-fast | Nhiều lỗi cùng giai đoạn | Có thể chỉ một violation, không đoán field nào |
| JSON sai kiểu | Body không deserialize được | Lỗi trước Bean Validation; sequence chưa xử lý |
| Spring thiếu validation provider | Chỉ có annotations | Không kết luận đã validate thành công |

Nên assert **property path, số vi phạm/nhóm xuất hiện, HTTP status** và mốc nào được chấp nhận; không assert toàn bộ message theo một locale cố định. Để kiểm tra thứ tự nội bộ thật sự hoặc số lần gọi custom constraint, có thể dùng test validator instrumentation trong phạm vi controlled test.

## 15. Các lỗi phổ biến và cách khắc phục

1. **Nhầm `@GroupSequence` với `groups = {A,B}`:** mảng `groups` là membership, `@GroupSequence` mới xác định thứ tự và stop.
2. **Truyền `validator.validate(bean, A.class, B.class)` rồi nghĩ A trước B:** không có bảo đảm. Gọi sequence interface.
3. **Nghĩ dừng ngay ở constraint đầu tiên:** group sequence dừng **sau giai đoạn có lỗi**, có thể có nhiều lỗi trong giai đoạn ấy.
4. **Dùng `@Valid` mà mong provider chọn Ordered:** `@Valid` mặc định kiểm tra Default ở điểm tích hợp; dùng `@Validated(Ordered.class)` hoặc cấu hình Default phù hợp.
5. **Sequence không chứa Default nhưng có nhiều constraint Default:** các constraint ấy có thể bị bỏ qua; thêm Default vào interface sequence khi cần.
6. **Đặt `@GroupSequence({Default.class, Advanced.class})` lên bean class:** khi định nghĩa lại Default trên class phải chứa **chính class**, không phải Default.class.
7. **Tạo group sequence vòng:** có thể gây `GroupDefinitionException`. Rà soát inheritance và sequence lồng nhau.
8. **Gắn constraint trực tiếp vào interface sequence:** nên gắn vào group thành phần, không dùng sequence interface như một group thông thường.
9. **Vừa yêu cầu Flow vừa yêu cầu một nhóm thành phần ngoài Flow:** stop của Flow không loại bỏ yêu cầu kiểm tra độc lập.
10. **Quên `@Valid` trên bean con:** lỗi của object sâu không được kiểm tra, khiến sequence đi tiếp dù dữ liệu thực tế sai.
11. **Lạm dụng fail-fast thay group sequence:** có thể mất các lỗi hữu ích cùng giai đoạn và không bảo đảm thứ tự field.
12. **Nhầm JSON binding exception với constraint violation:** deserialization có thể lỗi trước khi gọi provider.
13. **Tin rằng group sequence là kiểm tra phân quyền:** validation không thay thế authorization.
14. **Chọn các giai đoạn có side effect:** validation nên chủ yếu kiểm tra, không ghi dữ liệu hay gọi workflow có thay đổi trạng thái.
15. **Không test trường hợp nhóm 2 sai:** chỉ test nhóm 1 thất bại không chứng minh được cơ chế chuyển bước và dừng ở bước kế tiếp.
16. **Nhầm class-level Default redefinition với cascade toàn cây:** sequence Default của class là cục bộ; xem quy tắc propagation và conversion.
17. **Coi một violation luôn tương ứng một field:** custom class-level constraints và container element constraints có property path khác, cần xem API metadata.
18. **Thiếu provider runtime hoặc sai namespace Jakarta/javax:** annotation tồn tại không có nghĩa engine đã thực thi.

## 16. Checklist đưa vào dự án

1. Chia constraint thành các giai đoạn thật sự có quan hệ phụ thuộc, ví dụ Input → Policy → Consent.
2. Tạo marker interfaces, rồi tạo **một interface sequence** với `@GroupSequence({A.class, B.class, C.class})`.
3. Đặt `groups = A.class`/`B.class`/`C.class` lên đúng constraint; tránh thêm nhóm nhầm ngữ cảnh.
4. Quyết định có cần nhóm `Default` không; nếu có, đưa nó vào **interface sequence** ở vị trí thích hợp.
5. Kích hoạt bằng `validator.validate(bean, Flow.class)` hoặc `@Validated(Flow.class)` trên request DTO trong Spring MVC.
6. Test input sai ở giai đoạn 1, 2 và 3 cùng dữ liệu sai ở giai đoạn sau để chứng minh quy tắc dừng.
7. Test cả số lỗi **trong giai đoạn đầu**; không nhầm với fail-fast provider.
8. Nếu dùng `@Valid` và group conversion, kiểm tra cả object graph, null, inheritance và nhóm được chọn.
9. Tránh yêu cầu nhóm thành phần độc lập khi muốn stop theo sequence.
10. Giữ thứ tự service workflow, authorization, transaction và side effect ở các lớp nghiệp vụ thích hợp, không ép vào constraint sequence.
11. Dùng assertion về property path và HTTP status; không dựa vào thứ tự `Set`, thứ tự thông báo hoặc locale.
12. Xem specification/provider docs khi định nghĩa lại Default trên class để tránh thiếu chính class trong sequence.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 Specification — Group sequence và Validation routine](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Bean Validation API 3.0 — @GroupSequence](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html).
- [Hibernate Validator 8 Reference Guide — Defining group sequences, redefining Default, fail fast](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody kết hợp @Validated](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
