# `@GroupSequence` và thứ tự các giai đoạn trong Bean Validation

## 1. Vì sao cần thứ tự kiểm tra?

Trong Spring Framework, Jakarta Bean Validation có thể kiểm tra một đối tượng bằng nhiều ràng buộc: dữ liệu bắt buộc, định dạng, quan hệ giữa các trường và các quy tắc nghiệp vụ phức tạp. Không phải lúc nào tất cả các kiểm tra cũng nên chạy cùng lúc.

Ví dụ form đăng ký có ba giai đoạn:

1. **Required:** tên và email không được trống.
2. **Syntax:** email phải đúng định dạng.
3. **Business:** mã đăng ký phải theo quy tắc nghiệp vụ.

Nếu tên vẫn trống, ta có thể muốn **dừng sau giai đoạn Required** thay vì hiển thị thêm lỗi từ những bước sau. Nếu email đã có nhưng sai cú pháp, ta có thể muốn trả lỗi định dạng và **không chạy** các ràng buộc nghiệp vụ phụ thuộc vào dữ liệu hợp lệ.

Jakarta Bean Validation hỗ trợ điều này qua **validation groups** và annotation **`@GroupSequence`**:

```text
Yêu cầu validate nhóm OrderedChecks
                  |
                  v
           [Required]
           lỗi? -- có --> kết thúc; trả các vi phạm Required
                  |
                không
                  v
            [Syntax]
           lỗi? -- có --> kết thúc; trả các vi phạm Syntax
                  |
                không
                  v
           [Business]
                  |
                  v
             trả kết quả
```

**Ý chính:** `@GroupSequence` thiết lập **thứ tự giữa các nhóm (giai đoạn)**. Nếu một giai đoạn tạo ít nhất một `ConstraintViolation`, những giai đoạn **đứng sau** bị bỏ qua trong lần validation đó. Nó **không đảm bảo** thứ tự thực hiện từng annotation bên trong cùng một nhóm và cũng **không phải** cơ chế “gặp lỗi đầu tiên trên toàn hệ thống thì dừng”.

Sau bài học, bạn sẽ hiểu và sử dụng được:

- `groups` trên annotation như `@NotBlank`, `@Pattern`, `@Min`, `@AssertTrue`.
- `@GroupSequence` đặt trên **interface đại diện cho một chuỗi nhóm**.
- `@GroupSequence` đặt trực tiếp trên **bean class để định nghĩa lại nhóm `Default` của class đó**.
- Khác biệt giữa `validator.validate(bean, Ordered.class)`, `validator.validate(bean, A.class, B.class)` và `validator.validate(bean)` mặc định.
- Quy tắc dừng sớm giữa giai đoạn, cascaded validation (`@Valid`), group conversion và các lỗi cấu hình phổ biến.
- Cách tích hợp vào Spring MVC bằng `@Validated(Ordered.class)` và kiểm tra `BindingResult`.

## 2. Ôn lại validation group

Một **group** đại diện cho một tập constraint được kiểm tra cùng nhau. Theo Jakarta Validation, group thường được biểu diễn bằng một interface rỗng:

```java
public interface Required {}
public interface Syntax {}
public interface Business {}
```

Khi khai báo constraint, ta gắn nó vào một hoặc nhiều group:

```java
@NotBlank(groups = Required.class)
private String name;

@Pattern(regexp = ".+@.+\\..+", groups = Syntax.class)
private String email;

@Pattern(regexp = "REG-[0-9]{3}", groups = Business.class)
private String registrationCode;
```

Đây là **đoạn code minh họa**, cần import các annotation từ `jakarta.validation.constraints` và khai báo các group interface trong class/package tương ứng.

Một constraint có thể thuộc **nhiều group**:

```java
@NotBlank(groups = {Required.class, Business.class})
private String displayName;
```

Tuy nhiên, việc một constraint thuộc nhiều group không tạo một thứ tự xử lý. Nếu muốn group `Required` chạy trước `Business`, cần một group sequence.

### 2.1. Group `Default`

Nếu không viết thuộc tính `groups`:

```java
@NotBlank
private String name;
```

constraint thuộc **`jakarta.validation.groups.Default`**. Khi gọi:

```java
validator.validate(object);
```

Jakarta Validation mặc định yêu cầu group `Default` (trừ những thay đổi được khai báo theo chuẩn, chẳng hạn định nghĩa lại Default trên class). Điều này **khác** với việc “chạy mọi group”.

Nếu các constraint của một DTO chỉ có `groups = Required.class`, `groups = Syntax.class` và `groups = Business.class`, gọi `validate(dto)` mà không chỉ định group sẽ **không tự chạy ba nhóm đó**. Phải yêu cầu các group thích hợp hoặc đặt sequence theo chủ đích.

### 2.2. Gọi nhiều group không có nghĩa là có thứ tự

Hai cách sau có ngữ nghĩa khác nhau:

```java
// Yêu cầu nhiều group; KHÔNG cam kết thứ tự A -> B -> C.
validator.validate(form, Required.class, Syntax.class, Business.class);

// Yêu cầu một group sequence định nghĩa rõ thứ tự.
validator.validate(form, OrderedChecks.class);
```

Khi truyền nhiều group trực tiếp vào `validate(...)`, chuẩn không quy định thứ tự thực hiện giữa chúng. Không dựa vào thứ tự các đối số varargs để suy ra “Required thất bại nên Syntax không chạy”.

**Một group chỉ chọn tập constraint. Một group sequence mới mang theo luật thứ tự giữa các tập đó.**

## 3. Khai báo `@GroupSequence` trên interface

Giả sử ba nhóm:

```java
public interface Required {}
public interface Syntax {}
public interface Business {}
```

Ta khai báo một interface **đại diện cho chuỗi**:

```java
import jakarta.validation.GroupSequence;

@GroupSequence({
    Required.class,
    Syntax.class,
    Business.class
})
public interface OrderedChecks {}
```

`OrderedChecks` là **group sequence**. Khi gọi:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration, OrderedChecks.class);
```

việc kiểm tra được yêu cầu theo thứ tự:

```text
Required -> Syntax -> Business
```

Cơ chế:

1. Đánh giá các constraint thuộc `Required` trên phạm vi object graph áp dụng.
2. Nếu `Required` có vi phạm, trả những vi phạm tương ứng, **không chuyển sang `Syntax` và `Business`**.
3. Nếu `Required` đạt, chuyển sang `Syntax`.
4. Nếu `Syntax` có vi phạm, **bỏ qua `Business`**.
5. Nếu `Syntax` đạt, kiểm tra `Business`.
6. Tập vi phạm trả về phản ánh những constraint đã được thực thi; không nhất thiết chứa toàn bộ lỗi tiềm ẩn của các giai đoạn chưa chạy.

Đừng gắn constraint trực tiếp vào `groups = OrderedChecks.class`. Hãy gắn constraint vào các **group thành phần** như `Required`, `Syntax`, `Business`, rồi yêu cầu `OrderedChecks` tại điểm bắt đầu validation.

Interface chứa `@GroupSequence` cũng không nên `extends` các group khác. Theo đặc tả, nó là interface **khai báo sequence**, không phải một group kế thừa được dùng làm nơi đính constraint.

### 3.1. Trong một giai đoạn có nhiều lỗi thì sao?

Giả sử `Required` có:

```java
@NotBlank(groups = Required.class)
private String name;

@NotBlank(groups = Required.class)
private String email;
```

Nếu cả hai trường đều trống, validator **có thể trả hai vi phạm trong giai đoạn `Required`**. `@GroupSequence` chỉ đảm bảo không chạy giai đoạn **sau**, không cam kết chỉ nhận **một** lỗi.

Cũng không thể dựa vào thứ tự thực thi của `name` trước `email`, hay thứ tự phần tử trong `Set<ConstraintViolation<?>>`. Với test hoặc log cần ổn định, nên so sánh **tập lỗi theo path/constraint** hoặc sort trước khi hiển thị.

### 3.2. Ví dụ ba lần thử

| Input | `Required` | `Syntax` | `Business` | Kết quả |
| --- | --- | --- | --- | --- |
| Tên rỗng, email sai, code sai | **Fail** | Bỏ qua | Bỏ qua | Chỉ lỗi giai đoạn Required |
| Tên hợp lệ, email sai, code sai | Pass | **Fail** | Bỏ qua | Lỗi giai đoạn Syntax |
| Tên/email hợp lệ, code sai | Pass | Pass | **Fail** | Lỗi giai đoạn Business |
| Mọi dữ liệu hợp lệ | Pass | Pass | Pass | Không có vi phạm |

Chuỗi này phù hợp với quy trình **kiểm tra điều kiện nền tảng trước khi kiểm tra điều kiện phức tạp**. Nó không làm các ràng buộc về cú pháp/nghiệp vụ biến mất; những ràng buộc đó vẫn được chạy khi dữ liệu đã vượt qua giai đoạn trước.

## 4. `@GroupSequence` không tự kích hoạt

Việc chỉ định nghĩa interface:

```java
@GroupSequence({Required.class, Syntax.class})
interface OrderedChecks {}
```

không có nghĩa mọi lần validate đều tự động dùng sequence này.

Cần chỉ định `OrderedChecks.class` tại **điểm yêu cầu validation**:

```java
validator.validate(form, OrderedChecks.class);
```

hoặc trong Spring MVC, tại đối số cần validate theo group:

```java
@Validated(OrderedChecks.class) @ModelAttribute("form") Registration form
```

`@Validated` của Spring cho phép chỉ định validation hints/groups. Ngược lại, `@Valid` trên một tham số controller thông thường yêu cầu validation nhưng **không mang thuộc tính `groups` để chọn interface sequence**; nếu không có cấu hình khác, nhóm được dùng là `Default`.

Các trường hợp có thể chọn phương án khác:
- Cần nhiều endpoint kiểm tra khác nhau: dùng group/sequence riêng theo từng endpoint.
- Cần mọi lần `Default` validation của **một class cụ thể** tuân theo chuỗi: đặt `@GroupSequence` trên **class**, xem mục 6.
- Cần vừa bắt buộc nhóm nền tảng vừa kiểm tra quy tắc tốn kém: dùng `Default` trong sequence interface, sau đó group cho bước nâng cao.

## 5. Dùng `Default` làm giai đoạn đầu của một sequence interface

Với code hiện có, các constraint thường không khai báo group và vì thế thuộc `Default`:

```java
public class ProductForm {
    @NotBlank
    private String name;

    @Min(1)
    private Integer quantity;

    @SomeComplexRule(groups = Advanced.class)
    private String extra;
}
```

`@SomeComplexRule` ở đây **là tên minh họa**, không phải annotation chuẩn và không phải chương trình Java chạy độc lập. Các annotation chuẩn như `@NotBlank`, `@Min` thuộc Jakarta Validation.

Có thể định nghĩa:

```java
public interface Advanced {}

@GroupSequence({Default.class, Advanced.class})
public interface FullCheck {}
```

Import `jakarta.validation.GroupSequence` và `jakarta.validation.groups.Default`.

Khi `validator.validate(product, FullCheck.class)`:

1. Các ràng buộc thuộc `Default` chạy trước.
2. Nếu có lỗi `name` hoặc `quantity`, **không kiểm tra** `Advanced`.
3. Nếu `Default` đạt, mới kiểm tra `Advanced`.

Đây là cách hữu ích để bổ sung một giai đoạn đắt đỏ cho DTO đang dùng nhiều constraint mặc định **mà không sửa tất cả các annotation cũ**.

**Chú ý:** đoạn này nói về `@GroupSequence` trên **interface**. Khi đặt annotation trên **bean class để định nghĩa lại `Default`**, cú pháp khác và có một quy tắc bắt buộc: phải đưa chính class vào sequence, không đưa `Default.class` vào thay thế. Xem mục kế tiếp.

## 6. Định nghĩa lại nhóm `Default` trên chính bean class

Jakarta Validation còn cho phép đặt `@GroupSequence` **trực tiếp trên class**. Khi đó, nó không định nghĩa một interface sequence được gọi bằng tên riêng, mà thay đổi **ngữ nghĩa `Default` dành cho class ấy**.

Ví dụ:

```java
public interface ComplexChecks {}

@GroupSequence({Invoice.class, ComplexChecks.class})
public class Invoice {

    @NotBlank
    private String invoiceNumber;

    @AssertTrue(groups = ComplexChecks.class)
    private boolean totalIsConsistent;

    // Constructor/getters/setters.
}
```

Đây là **đoạn minh họa**, cần import `jakarta.validation.GroupSequence`, `jakarta.validation.constraints.NotBlank` và `AssertTrue`.

Khi gọi:

```java
validator.validate(invoice); // Không cần chỉ định interface sequence.
```

đối với instance `Invoice`, validation theo Default được thay bằng:

```text
Invoice.class -> ComplexChecks.class
```

Ý nghĩa:
- Các constraint `Default` khai báo trên `Invoice` được bao gồm thông qua group **`Invoice.class`** ở giai đoạn đầu.
- Nếu `invoiceNumber` trống, chưa đến `ComplexChecks`.
- Nếu `invoiceNumber` hợp lệ mà `totalIsConsistent` là false, constraint `@AssertTrue` thuộc `ComplexChecks` chạy và có thể báo lỗi.
- Nếu cả hai đều hợp lệ, không có vi phạm.

### 6.1. Tại sao phải có `Invoice.class`?

Đối với định nghĩa lại Default trên class `Invoice`, chuẩn **yêu cầu** sequence chứa **chính `Invoice.class`**:

```java
// ĐÚNG: đặt trên class Invoice.
@GroupSequence({Invoice.class, ComplexChecks.class})
public class Invoice { ... }
```

Không thay bằng:

```java
// SAI khi đặt trên class Invoice.
@GroupSequence({Default.class, ComplexChecks.class})
public class Invoice { ... }
```

Trường hợp thứ hai sử dụng `Default.class` để định nghĩa lại chính `Default` và dẫn tới vấn đề cấu hình. Nếu sequence ở class không chứa **class đó**, provider phải báo **`GroupDefinitionException`** khi validate/đọc metadata thích hợp.

**Cần nhớ hai công thức:**

| Vị trí annotation | Cấu hình đúng | Cách gọi |
| --- | --- | --- |
| Trên **interface sequence** `FullCheck` | `@GroupSequence({Default.class, ComplexChecks.class})` | `validator.validate(bean, FullCheck.class)` |
| Trên **bean class** `Invoice` | `@GroupSequence({Invoice.class, ComplexChecks.class})` | `validator.validate(invoice)` dùng Default đã định nghĩa lại |

Đây là một trong những khác biệt quan trọng nhất của `@GroupSequence`.

### 6.2. Phạm vi của Default redefinition

Định nghĩa lại Default trên class là **cục bộ cho class đó**. Nó **không tự động truyền một sequence mới nguyên vẹn sang mọi object con** được gắn `@Valid`.

Nếu `Invoice` chứa `@Valid Customer customer`:
- Khi truyền nhóm `Default` qua quan hệ cascade, `Customer` thông thường nhận ngữ nghĩa Default của **Customer**.
- Sequence Default định nghĩa riêng trên `Invoice` không được hiểu như một chuỗi group toàn cục áp dụng y hệt cho `Customer`.
- Nếu `Customer` cũng có Default sequence riêng, nó có thể áp dụng luật riêng khi được validate trong nhóm Default.
- Nếu cần đổi group khi đi qua một cạnh `@Valid`, cân nhắc `@ConvertGroup` có chủ đích.

Vì vậy, đừng dùng định nghĩa lại `Default` trên một root DTO như một “nút bật group sequence toàn bộ application”. Test cả root và child khi có nested validation.

## 7. Ví dụ Maven Java 17+ đầy đủ: ba giai đoạn và Default redefinition

Ví dụ sau dùng **Jakarta Bean Validation 3.0, Hibernate Validator 8.0.2.Final** và **Spring Framework 6.2.14**. Chương trình chạy độc lập, không cần Spring Boot hay web server, và kiểm tra:
- Ba giai đoạn Required → Syntax → Business.
- Việc bỏ qua giai đoạn sau khi giai đoạn trước có lỗi.
- `Default` **không tự chạy** các group custom khi chỉ có constraint gắn group custom.
- Spring `SpringValidatorAdapter` nhận sequence làm validation hint.
- `@GroupSequence` ở **class** đổi Default sequence đúng cách.

### 7.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-group-sequence</artifactId>
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
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
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

`hibernate-validator` là provider cho Jakarta Bean Validation; `jakarta.el` hỗ trợ message interpolation; `spring-context` cung cấp `SpringValidatorAdapter` và `BeanPropertyBindingResult`. Trong Spring Boot, thường dùng dependency management/starter validation phù hợp phiên bản Boot thay vì tự chốt từng version như ví dụ học tập.

### 7.2. Tạo `src/main/java/demo/GroupSequenceDemo.java`

```java
package demo;

import java.util.List;

import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class GroupSequenceDemo {

    public interface Required {}
    public interface Syntax {}
    public interface Business {}

    // Sequence interface được yêu cầu tường minh.
    @GroupSequence({Required.class, Syntax.class, Business.class})
    public interface OrderedChecks {}

    public static final class Registration {
        @NotBlank(groups = Required.class, message = "name required")
        private String name;

        @NotBlank(groups = Required.class, message = "email required")
        @Pattern(
            regexp = "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
            groups = Syntax.class,
            message = "email syntax invalid"
        )
        private String email;

        @Pattern(
            regexp = "REG-[0-9]{3}",
            groups = Business.class,
            message = "registration code invalid"
        )
        private String registrationCode;

        public Registration(String name, String email, String code) {
            this.name = name;
            this.email = email;
            this.registrationCode = code;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getRegistrationCode() {
            return registrationCode;
        }

        public void setRegistrationCode(String code) {
            this.registrationCode = code;
        }
    }

    public interface DeepCheck {}

    // Khi ở CLASS, @GroupSequence định nghĩa lại Default cho class này.
    @GroupSequence({Profile.class, DeepCheck.class})
    public static final class Profile {
        @NotBlank(message = "title required")
        private String title;

        @AssertTrue(
            groups = DeepCheck.class,
            message = "approval required"
        )
        private boolean approved;

        public Profile(String title, boolean approved) {
            this.title = title;
            this.approved = approved;
        }

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public boolean isApproved() {
            return approved;
        }

        public void setApproved(boolean approved) {
            this.approved = approved;
        }
    }

    private static <T> List<String> paths(
            Validator validator, T bean, Class<?>... groups) {
        return validator.validate(bean, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
    }

    private static void check(
            List<String> actual,
            List<String> expected,
            String caseName) {
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    caseName + ": expected " + expected
                    + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Registration first = new Registration(
                    " ", "not-an-email", "BAD");

            Registration second = new Registration(
                    "Ada", "not-an-email", "BAD");

            Registration third = new Registration(
                    "Ada", "ada@example.com", "BAD");

            Registration valid = new Registration(
                    "Ada", "ada@example.com", "REG-123");

            // Mỗi lần chỉ chạy các giai đoạn tới giai đoạn bị lỗi.
            List<String> required =
                    paths(validator, first, OrderedChecks.class);
            List<String> syntax =
                    paths(validator, second, OrderedChecks.class);
            List<String> business =
                    paths(validator, third, OrderedChecks.class);
            List<String> success =
                    paths(validator, valid, OrderedChecks.class);

            check(required, List.of("name"), "required");
            check(syntax, List.of("email"), "syntax");
            check(business, List.of("registrationCode"), "business");
            check(success, List.of(), "success");

            System.out.println("required=" + required);
            System.out.println("syntax=" + syntax);
            System.out.println("business=" + business);
            System.out.println("success=" + success);

            // Registration chỉ dùng group custom, không có Default constraint.
            List<String> defaultOnly = paths(validator, first);
            check(defaultOnly, List.of(), "default");
            System.out.println("defaultOnly=" + defaultOnly);

            // Spring SmartValidator nhận group sequence làm hint.
            SpringValidatorAdapter adapter =
                    new SpringValidatorAdapter(validator);
            BeanPropertyBindingResult springErrors =
                    new BeanPropertyBindingResult(second, "registration");

            adapter.validate(second, springErrors, OrderedChecks.class);
            List<String> springFields =
                    springErrors.getFieldErrors().stream()
                            .map(FieldError::getField)
                            .sorted()
                            .toList();

            check(springFields, List.of("email"), "spring");
            System.out.println("springFields=" + springFields);

            // @GroupSequence đặt trên class Profile:
            // validator.validate(profile) tự dùng Default đã được thay thế.
            List<String> profile1 =
                    paths(validator, new Profile("", false));
            List<String> profile2 =
                    paths(validator, new Profile("Ready", false));
            List<String> profile3 =
                    paths(validator, new Profile("Ready", true));

            check(profile1, List.of("title"), "profile1");
            check(profile2, List.of("approved"), "profile2");
            check(profile3, List.of(), "profile3");

            System.out.println("classDefault1=" + profile1);
            System.out.println("classDefault2=" + profile2);
            System.out.println("classDefault3=" + profile3);

            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 7.3. Chạy bằng Maven

Từ thư mục chứa `pom.xml`, dùng **JDK 17+ và Maven 3.9+**:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.GroupSequenceDemo
```

Những dòng do chính chương trình in, không tính log khởi tạo Hibernate Validator hoặc Maven có thể xuất hiện trên console:

```text
required=[name]
syntax=[email]
business=[registrationCode]
success=[]
defaultOnly=[]
springFields=[email]
classDefault1=[title]
classDefault2=[approved]
classDefault3=[]
CHECKS: PASS
```

Giải thích:
- `required=[name]`: tên trống gây vi phạm ở `Required`. Dù email và code cũng sai, hai giai đoạn sau **chưa chạy**.
- `syntax=[email]`: `Required` đạt, regex email ở `Syntax` thất bại. Constraint `registrationCode` ở Business chưa chạy.
- `business=[registrationCode]`: dữ liệu qua hai giai đoạn đầu, tới Business mới có lỗi.
- `success=[]`: tất cả giai đoạn đều đạt.
- `defaultOnly=[]`: không yêu cầu sequence, bean `Registration` chỉ có constraints gắn group custom nên Default không kiểm tra chúng.
- `springFields=[email]`: Spring adapter nhận `OrderedChecks.class` dưới dạng validation hint và tạo `FieldError` tương ứng.
- `classDefault1=[title]`: trên class `Profile`, Default đầu tiên đánh giá constraint `title`, lỗi nên dừng.
- `classDefault2=[approved]`: `title` đạt, mới tới group `DeepCheck`.
- `classDefault3=[]`: hai giai đoạn của Default class đều đạt.

**Chú ý về cú pháp:** regex email trong ví dụ chỉ phục vụ minh họa giai đoạn kiểm tra cú pháp, **không phải giải pháp kiểm tra email đầy đủ cho môi trường sản xuất**. Có thể thay bằng `@Email(groups=Syntax.class)` từ Jakarta Validation, kèm quy tắc ứng dụng phù hợp và test provider thực tế.

**Chú ý về runnable:** mã `GroupSequenceDemo.java` đã hoàn thiện class, import, POM, lệnh Maven và các phép kiểm tra kết quả. Khi dùng trong dự án hiện hữu, hãy chạy với đúng JDK và dependency của dự án, đặc biệt nếu Spring/Jakarta namespace khác phiên bản minh họa.

## 8. Dùng group sequence trong Spring MVC

Trong một Spring MVC controller, tham số `@ModelAttribute` có thể kích hoạt nhóm kiểm tra có thứ tự qua `@Validated`:

```java
@PostMapping("/registrations")
public String submit(
        @Validated(GroupSequenceDemo.OrderedChecks.class)
        @ModelAttribute("registration")
        GroupSequenceDemo.Registration form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration/form";
    }
    return "registration/success";
}
```

**Đây là đoạn minh họa đặt trong controller**, không phải chương trình độc lập. Nó giả định DTO `GroupSequenceDemo.Registration` được dùng làm form model và có đủ cơ chế khởi tạo/binding phù hợp; trong ứng dụng MVC thực tế DTO thường có no-arg constructor hoặc cơ chế constructor binding phù hợp. Import cần thiết:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.validation.BindingResult;
```

Khi người dùng gửi dữ liệu:

1. Spring MVC bind request thành `Registration` (chuyển kiểu và điền giá trị).
2. `@Validated(OrderedChecks.class)` yêu cầu Bean Validation chạy với **sequence**.
3. Nếu Required sai, `BindingResult` chứa lỗi Required; Syntax và Business không được chạy trong lần validate theo sequence.
4. Nếu Required đạt mà Syntax sai, chỉ lỗi thuộc giai đoạn Syntax được ghi thêm.
5. Nếu cả ba nhóm đạt, phần xử lý có thể tiếp tục.

**`BindingResult` phải đứng ngay sau argument đang được validate** khi muốn tự xử lý lỗi của argument đó trong flow MVC thông thường. Nếu thay bằng `@Valid` đơn thuần, nhóm được yêu cầu thường là `Default`, không mặc nhiên kích hoạt `OrderedChecks`.

### 8.1. Dùng `@Validated` ở đâu?

`@Validated` là annotation của **Spring** (`org.springframework.validation.annotation.Validated`), có thể mang các group class làm validation hints:

```java
@Validated(OrderedChecks.class)
```

`@GroupSequence` và `groups=...` là cơ chế của **Jakarta Bean Validation**. Spring truyền hint tới provider phù hợp thông qua adapter. Khi các annotation hoặc hạ tầng cấu hình khác yêu cầu **method validation** (ví dụ constraint đặt trực tiếp lên method parameter), hành vi exception/đường validation có thể khác cách validate command object thông thường; cần test endpoint thực tế.

Đừng cho rằng đặt `@Validated` trên toàn bộ controller class có nghĩa mọi `@ModelAttribute` tự chạy một sequence cụ thể theo cách bạn dự định. Để dễ đọc và kiểm soát, đặt group phù hợp trên parameter đang nhận DTO và xác nhận kết quả bằng integration test.

### 8.2. `@RequestBody` JSON cũng có thể được validate theo group

Có thể khai báo:

```java
@PostMapping("/api/registrations")
public ResponseEntity<Void> submitJson(
        @RequestBody
        @Validated(OrderedChecks.class)
        RegistrationDto request) {
    // Xử lý khi DTO hợp lệ.
    return ResponseEntity.noContent().build();
}
```

Đây là **đoạn minh họa controller** cần Spring Web MVC, các import `PostMapping`, `RequestBody`, `ResponseEntity`, `Validated` và `RegistrationDto` có thật. JSON được deserialize trước khi Bean Validation kiểm tra; một lỗi JSON không đọc được **không** trở thành vi phạm của giai đoạn Required/Syntax/Business. Khi không có `BindingResult` tương ứng, lỗi validation của argument có thể được ném thành exception để exception handler xử lý tùy phiên bản/cấu hình MVC.

Phân biệt:
- **Binding/deserialization error**: không chuyển dữ liệu vào kiểu Java đích.
- **Validation error**: có object Java nhưng vi phạm constraint trong một group được yêu cầu.
- **Business processing error**: nghiệp vụ hoặc database từ chối ngay cả khi DTO hợp lệ.

`@GroupSequence` điều khiển **validation constraints**, không sửa lỗi parse JSON và không thay thế transaction hay kiểm tra nhất quán dữ liệu ở tầng service/database.

## 9. `@Valid`, đối tượng con và thứ tự giữa các giai đoạn

Một form có thể có cấu trúc:

```java
public class OrderForm {
    @Valid
    private Customer customer;

    @Valid
    private List<LineItem> items;
}
```

Đây là mã minh họa; cần import `jakarta.validation.Valid`, `java.util.List`, cùng các class con. Với `@Valid`, Bean Validation có thể kiểm tra constraints ở object con. Khi gọi `validator.validate(order, OrderedChecks.class)`, sequence có thể được áp dụng **trên object graph đang được validate**, chứ không chỉ object root.

**Điều đáng nhớ:** đối với một group có thứ tự theo sequence, validator phải xem xét **các ràng buộc thuộc giai đoạn đó trên các đối tượng con có thể cascade được** trước khi quyết định có chuyển sang giai đoạn tiếp theo không. Nếu một constraint thuộc Required ở child thất bại, giai đoạn Syntax sau đó có thể bị bỏ qua đối với toàn bộ lượt validate theo sequence.

Điều này phù hợp với yêu cầu như:
- Kiểm tra trường bắt buộc ở `OrderForm`, `Customer`, `LineItem` trước.
- Chỉ khi tất cả trường bắt buộc đạt mới kiểm tra định dạng.
- Chỉ khi dữ liệu có cấu trúc hợp lệ mới chạy constraint nghiệp vụ tốn kém.

Nhưng có một ngoại lệ ngữ nghĩa quan trọng: **Default group sequence được định nghĩa lại trên một class là cục bộ cho class đó và không được truyền y nguyên qua các tham chiếu `@Valid`**. Ví dụ `@GroupSequence({OrderForm.class, Advanced.class})` trên `OrderForm` không có nghĩa `Customer` tự động nhận `OrderForm.class` rồi `Advanced.class` thay cho Default riêng của mình.

Nếu muốn đổi group khi cascade từ parent sang child, dùng `@ConvertGroup` tại cạnh có `@Valid`:

```java
@Valid
@ConvertGroup(from = Default.class, to = ChildChecks.class)
private ChildDto child;
```

Các import là `jakarta.validation.Valid`, `jakarta.validation.groups.ConvertGroup`, `jakarta.validation.groups.Default`. `ChildChecks` là interface group đã khai báo; đoạn trên là **mã cấu trúc minh họa**, không phải class đầy đủ.

`@ConvertGroup` không thay đổi thứ tự một cách tùy ý và không tự định nghĩa group sequence mới: nó **đổi group truyền qua một cạnh cascade**. Khi dùng chung với `@GroupSequence`, phải kiểm thử cả root lẫn child trong những tình huống đầu vào lỗi để tránh nghĩ rằng group conversion là một cách “gắn `@GroupSequence` trên mọi object”.

### 9.1. `@Valid` không có `groups=...`

Cú pháp sau **không hợp lệ**:

```java
@Valid(groups = Required.class)  // Sai: @Valid không có thuộc tính groups.
private Customer customer;
```

Đúng là:

```java
@Valid
private Customer customer;
```

Rồi sử dụng `Validator.validate(root, Required.class)`, `@Validated(Required.class)` ở entry point hoặc `@ConvertGroup` khi cần đổi group lúc cascade. Đừng đặt nhầm tham số của một constraint vào annotation `@Valid`.

## 10. Group inheritance, nhóm lồng và constraint nằm ở nhiều nhóm

Một group có thể kế thừa từ group khác bằng interface:

```java
public interface Required {}
public interface Premium extends Required {}
```

Nếu validate `Premium`, các constraint thuộc Required cũng có thể được bao gồm qua group inheritance. Nhưng **kế thừa interface không tạo ra thứ tự chạy**:

```text
Premium extends Required
    = nhóm bao gồm constraints kế thừa
    ≠ chạy Required trước Premium rồi dừng nếu Required lỗi
```

Muốn thứ tự, tạo một **interface sequence riêng**, không `extends` group khác:

```java
@GroupSequence({Required.class, PremiumChecks.class})
public interface PremiumPipeline {}
```

Tương tự, một group trong sequence có thể là một sequence/group phức hợp khác. Chuẩn yêu cầu quan hệ thứ tự của các group thành phần phải được tôn trọng; các định nghĩa gây ra **vòng thứ tự không hợp lệ** có thể dẫn tới `GroupDefinitionException`.

Nếu một constraint thuộc **nhiều group** xuất hiện trong cùng một chuỗi, Jakarta Validation không yêu cầu chạy lặp cùng constraint trên cùng navigation path mỗi khi gặp group đó; constraint đã được đánh giá ở group đầu phù hợp không bị thực thi lại chỉ vì xuất hiện trong group đứng sau.

Vì thế, không nên dựa vào một `ConstraintValidator` có tác dụng phụ hoặc đếm lần gọi `isValid()` như một cơ chế nghiệp vụ. Constraint validator nên tập trung xác định tính hợp lệ, không cập nhật dữ liệu hay gửi thông báo bên ngoài.

## 11. `@GroupSequence` có phải “fail fast” không?

**Không.** Hai cơ chế này khác nhau:

| Cơ chế | Quy tắc dừng | Có chuẩn Jakarta không? |
| --- | --- | --- |
| `@GroupSequence` | Khi **một group/giai đoạn** có vi phạm, bỏ qua những group sau | Có, thuộc Jakarta Validation |
| Provider-specific fail-fast | Có thể dừng ngay sau vi phạm đầu tiên mà provider phát hiện | Hành vi/cấu hình do provider quyết định, không phải ý nghĩa của `@GroupSequence` |
| `if (errors.hasErrors()) return ...` trong controller | Ứng dụng không xử lý tiếp khi đã có lỗi | Logic ứng dụng; không tự thay đổi thứ tự constraint trong validator |

Ví dụ `Required` có 5 field sai. `@GroupSequence` không bảo đảm chỉ trả đúng một lỗi; có thể thu được nhiều violation cùng giai đoạn. Nếu bật một cấu hình fail-fast đặc thù của Hibernate Validator, số violation và thứ tự phát hiện có thể khác, nhưng đó là **chính sách provider** và cần test riêng.

Đừng phụ thuộc vào thứ tự từng constraint bên trong một giai đoạn, cũng đừng giả định group sequence giúp điều phối **các tác vụ dịch vụ thật** như kiểm tra tồn kho bằng transaction hoặc gọi API ngoài. Bean Validation nên xử lý các quy tắc nhất quán, không có side effect; dịch vụ vẫn phải kiểm tra invariant nghiệp vụ khi ghi dữ liệu.

## 12. Những lỗi thiết kế và cấu hình phổ biến

### 12.1. Nhầm `@GroupSequence` với `@Validated`

`@GroupSequence` là annotation Jakarta dùng để **mô tả thứ tự giữa group**. `@Validated` là annotation Spring để **yêu cầu validate theo một hoặc nhiều group** tại điểm gọi phù hợp. Chỉ viết `@GroupSequence` trên một interface mà không yêu cầu group đó thì nó không tự có tác dụng với `validator.validate(bean)`.

### 12.2. Gọi nhiều group và mong short-circuit

```java
validator.validate(form, Required.class, Business.class);
```

Đây **không phải** một sequence. Hai group được yêu cầu mà không có thứ tự chuẩn. Sửa bằng:

```java
validator.validate(form, OrderedChecks.class);
```

trong đó `@GroupSequence` đã khai báo thứ tự cần thiết.

### 12.3. Đặt `@GroupSequence` trên class mà không có chính class

```java
@GroupSequence({Default.class, Business.class})
public class Order { ... } // Sai định nghĩa lại Default của Order.
```

Với class, phải chứa `Order.class`:

```java
@GroupSequence({Order.class, Business.class})
public class Order { ... }
```

Ngược lại, với **interface sequence**, `Default.class` là thành phần hoàn toàn hợp lệ.

### 12.4. Dùng interface sequence làm `groups` của constraint

```java
@NotBlank(groups = OrderedChecks.class)
private String name;
```

Điều này không phải cách chuẩn để định nghĩa ràng buộc của từng giai đoạn. Đặt `groups = Required.class` và đưa `Required.class` vào sequence. Theo hướng dẫn đặc tả, interface chứa sequence không nên được dùng trực tiếp trong constraint declaration.

### 12.5. Định nghĩa vòng giữa các sequence

```java
@GroupSequence({Second.class})
interface First {}

@GroupSequence({First.class})
interface Second {}
```

Cấu trúc minh họa này dẫn tới vòng phụ thuộc sequence. Provider có thể ném `GroupDefinitionException` khi cần xử lý nhóm đó. Không tự động “sửa” thứ tự bằng cách dựa vào provider; hãy thiết kế các giai đoạn theo hướng một chiều.

### 12.6. Cho rằng `Default` là tổng tất cả group

Một constraint chỉ gắn `groups = Business.class` **không** tự thuộc Default. Nếu dùng `@Valid` không có lựa chọn group, nó có thể không được chạy. Thêm group thích hợp vào sequence hoặc chỉ định `@Validated` đúng ở entry point.

### 12.7. Chạy validation mà không có provider

Annotation không tự thực thi. Jakarta Bean Validation cần implementation như Hibernate Validator và cấu hình tích hợp với Spring. Nếu chỉ có API mà không có provider, việc tạo `ValidatorFactory`/thực thi validation có thể thất bại; trong Spring Boot, cần dependency validation starter phù hợp phiên bản.

### 12.8. Bỏ qua lỗi binding

Một field `Integer` nhận chuỗi `"abc"` có thể không convert được trước khi tới `@Min`. Đừng chờ sequence Syntax/Business xử lý mọi lỗi parse: đó là **data binding**, cần phân loại `typeMismatch` và cung cấp thông báo riêng.

### 12.9. Trông chờ một lỗi duy nhất

Trong cùng giai đoạn Required, nhiều field có thể cùng lỗi. `Set<ConstraintViolation<?>>` không bảo đảm thứ tự, vì vậy test nên kiểm tra **tập field lỗi và group**, không kiểm tra “lỗi đầu tiên là field X” trừ khi ứng dụng đã chủ động sort/ưu tiên.

### 12.10. Dùng sequence để che lỗi nghiệp vụ quan trọng

Sequence tối ưu việc hiển thị và tránh chạy constraint tốn kém khi dữ liệu nền tảng sai. Nhưng không có nghĩa lỗi ở các giai đoạn chưa chạy đã được chứng minh là không tồn tại. Sau khi người dùng sửa giai đoạn trước, có thể xuất hiện lỗi của giai đoạn tiếp theo; UX cần giải thích điều đó.

### 12.11. Định nghĩa lại Default của root rồi mong child dùng y hệt

Class-level Default redefinition có phạm vi cục bộ. Với object graph có `@Valid`, group đi qua quan hệ theo quy tắc cascade; nếu cần chính sách khác cho child, dùng group conversion/sequence của child một cách tường minh và kiểm thử hành vi thực tế.

### 12.12. Trộn namespace Java Validation

Spring Framework 6+ sử dụng `jakarta.validation.*` trong hệ sinh thái Jakarta; dự án Spring 5.x cũ thường sử dụng `javax.validation.*`. API, provider và imports phải tương thích, không đổi riêng tên package trên một vài annotation rồi kỳ vọng build chạy.

## 13. Ma trận test quan trọng

| Trường hợp | Đầu vào/cấu hình | Kỳ vọng |
| --- | --- | --- |
| Required sai | name trống, email sai, code sai | Chỉ violation thuộc giai đoạn Required trong sequence |
| Required đạt, Syntax sai | name có giá trị, email sai, code sai | Syntax báo lỗi; Business chưa được chạy |
| Required/Syntax đạt, Business sai | email đúng pattern, code sai | Business báo lỗi |
| Mọi giai đoạn đạt | Dữ liệu hợp lệ | Không có violation |
| Nhiều lỗi cùng giai đoạn | name và email cùng rỗng | Có thể có nhiều violation Required |
| Gọi các group trực tiếp | `validate(bean, Required.class, Business.class)` | Không bảo đảm thứ tự hoặc short-circuit |
| Không chỉ định group | `validate(bean)` với constraints chỉ ở custom groups | Chỉ Default được yêu cầu; custom groups không tự chạy |
| Interface sequence có Default | `@GroupSequence({Default.class, Advanced.class})` | Default chạy trước Advanced khi yêu cầu interface |
| Class-level Default redefinition | `@GroupSequence({Bean.class, Advanced.class})` trên Bean | Validate Default của Bean theo sequence |
| Class-level thiếu bean class | Class annotation không chứa `Bean.class` | `GroupDefinitionException` |
| Sequence có cycle | A → B → A không hợp lệ | `GroupDefinitionException` |
| Constraint trong nhiều group | Một constraint khai báo ở cả hai group | Không phải chạy lặp vô điều kiện trong cùng một validation path |
| Group inheritance | `Premium extends Required` | Kế thừa tập constraint, **không** tạo thứ tự |
| Child có `@Valid` | Required sai ở object con | Group sau không chạy theo ordered sequence phù hợp |
| Class default của root | Root định nghĩa lại Default, có child | Sequence cục bộ không tự truyền y nguyên sang child |
| Group conversion | `@ConvertGroup(from=Default.class,to=ChildChecks.class)` | Dùng group chỉ định khi cascade tại cạnh đó |
| Lỗi conversion form | String không đổi được thành Integer | Spring báo binding error; không phải chứng minh @Min ở group nào chạy |
| JSON body lỗi | JSON deserialization thất bại | Báo lỗi đọc request, trước khi có object được validate |
| Spring MVC `@Validated` | `@Validated(OrderedChecks.class)` và BindingResult ngay sau | Sử dụng sequence của DTO, nhận field errors |
| Provider fail-fast | Cấu hình riêng Hibernate Validator | Có thể trả ít lỗi hơn; không đồng nhất `@GroupSequence` |
| Test thứ tự | Nhiều violations trong một group | Không dựa vào thứ tự Set; sắp xếp/so tập |

### 13.1. Cách test không phụ thuộc text của thông báo

Với một validator có sẵn, có thể kiểm tra tập path:

```java
Set<String> paths = validator.validate(form, OrderedChecks.class)
        .stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(Collectors.toSet());

if (!paths.equals(Set.of("email"))) {
    throw new AssertionError("Unexpected validation phase: " + paths);
}
```

Đây là **trích đoạn** trong method/test có sẵn biến `validator`, `form`, import `java.util.Set` và `java.util.stream.Collectors`. Cách này không phụ thuộc locale của `message`, cũng không phụ thuộc thứ tự `Set` được provider trả về.

Với logic quan trọng, nên test thêm:
- **Sự có mặt/không có mặt** của violation thuộc các group được mong đợi.
- **Một constraint phức tạp** được chạy chỉ sau khi giai đoạn điều kiện tiên quyết đã đạt, bằng một validator test có theo dõi nhưng không đưa side effect vào production.
- `BindingResult` của endpoint Spring MVC thực tế, không chỉ gọi Jakarta Validator độc lập.
- Mối quan hệ giữa Default redefinition của root và nested child, nhất là khi có `@ConvertGroup`.

## 14. Checklist thiết kế và triển khai

- [ ] Tách constraint thành các group **theo phụ thuộc dữ liệu**, không chỉ dựa theo tên dễ nhớ.
- [ ] Khai báo `@GroupSequence` trên interface có thứ tự từ điều kiện nền tảng đến điều kiện nâng cao.
- [ ] Yêu cầu **sequence interface** tại điểm validate: `validator.validate(bean, Sequence.class)` hoặc Spring `@Validated(Sequence.class)`.
- [ ] Nếu đặt `@GroupSequence` trên **class**, nhớ đưa **chính class đó** vào danh sách để định nghĩa lại Default; không thay bằng `Default.class`.
- [ ] Không gắn constraint vào interface chứa sequence; gắn vào các group thành phần.
- [ ] Không kỳ vọng thứ tự giữa constraint trong cùng một group hoặc giữa nhiều group truyền trực tiếp không có sequence.
- [ ] Test giai đoạn đầu thất bại, giữa thất bại, cuối thất bại và tất cả thành công.
- [ ] Xác định rõ validation groups truyền qua `@Valid`, group conversion và phạm vi Default redefinition của từng bean.
- [ ] Không dùng sequence thay thế bảo vệ lỗi binding, JSON, transaction, phân quyền và invariant nghiệp vụ ở service.
- [ ] Kiểm tra khả năng chạy với cùng Jakarta Validation provider/Spring dependency của dự án.
- [ ] Đừng dùng `ConstraintValidator` có side effect; không giả định một constraint được gọi đúng một lần trên toàn object graph.
- [ ] Với Spring MVC, xác nhận `BindingResult` ngay sau parameter được validate hoặc cơ chế exception handler khi không nhận BindingResult.

## Tài liệu chính thức

- Jakarta Bean Validation 3.0 Specification, mục 5.4 **Group and group sequence**, 5.4.2 **Group sequence**, 5.4.3 **Redefining the Default group for a class**: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 — `@GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html
- Jakarta Validation 3.0 — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Validation 3.0 — `@ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/ConvertGroup.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `@Validated`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Hibernate Validator 8 — Reference Guide, Group sequences: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
