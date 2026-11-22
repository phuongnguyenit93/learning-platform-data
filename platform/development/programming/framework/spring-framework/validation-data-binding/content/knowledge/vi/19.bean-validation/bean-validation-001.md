# Jakarta Validation và mô hình khai báo constraint trong Spring Framework

> **Module:** Spring Framework – validation-data-binding  
> **Chủ đề cha:** Bean Validation  
> **Trọng tâm:** Cách khai báo, tổ chức và thực thi các *constraint* với `jakarta.validation`; quan hệ giữa Jakarta Validation, provider như Hibernate Validator và quá trình data binding của Spring.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Jakarta Validation (tên trước đây là Bean Validation) và ý nghĩa của cách kiểm tra dữ liệu bằng **annotation khai báo**.
2. Phân biệt **constraint**, **constraint validator**, **validation provider**, **Validator** và **ConstraintViolation**.
3. Đặt các constraint có sẵn trên field, getter, tham số, kiểu, phần tử collection và đối tượng lồng nhau.
4. Phối hợp `@NotNull`, `@NotBlank`, `@Size`, `@Pattern`, `@Email`, `@Positive`, `@Past`… đúng ngữ nghĩa, nhất là với giá trị `null`.
5. Dùng `@Valid`, validation groups, container element constraints và tự định nghĩa `@Constraint`.
6. Chủ động gọi `jakarta.validation.Validator` để kiểm thử, rồi tích hợp `@Valid`/`@Validated` vào Spring MVC.
7. Nhận biết ranh giới giữa **binding**, **Bean Validation**, ràng buộc nghiệp vụ và ràng buộc cơ sở dữ liệu.

## 2. Jakarta Validation là gì?

**Jakarta Validation** là đặc tả chuẩn của hệ sinh thái Jakarta EE cho việc khai báo và kiểm tra tính hợp lệ của dữ liệu Java. Thay vì đặt nhiều câu lệnh `if` lặp lại ở controller, ta gắn annotation ngay nơi định nghĩa dữ liệu:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationForm {
    @NotBlank
    @Size(max = 80)
    private String fullName;

    @NotBlank
    @Email
    private String email;
}
```

Đoạn trên là **mô hình minh họa**, chưa phải chương trình chạy độc lập. Annotation nói rằng tên không được trống, dài tối đa 80 ký tự; email không được trống và phải thỏa quy tắc email của validator. Đoạn khai báo **chưa tự chạy validation**: phải có một lời gọi `Validator.validate(...)` hoặc framework kích hoạt validation tại điểm tích hợp.

Từ Spring Framework 6 / Spring Boot 3, sử dụng package **`jakarta.validation.*`**. Mã cũ dùng `javax.validation.*` thuộc thế hệ thư viện trước; không trộn hai namespace trong cùng ứng dụng khi nâng cấp.

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Constraint annotation** | Khai báo quy tắc trên đối tượng | `@NotBlank`, `@Min(1)`, `@ValidOrderCode` |
| **ConstraintValidator** | Mã thực thi quy tắc với kiểu được hỗ trợ | `ConstraintValidator<OrderCode, String>` |
| **Validation provider** | Triển khai đặc tả, tìm metadata và chạy validation | Hibernate Validator |
| **ValidatorFactory** | Tạo và quản lý các `Validator` | `Validation.buildDefaultValidatorFactory()` |
| **Validator** | Kiểm tra bean và trả về tập lỗi | `validator.validate(order)` |
| **ConstraintViolation** | Kết quả của mỗi quy tắc không đạt | Đường dẫn property, message, giá trị vi phạm, metadata |

Jakarta Validation là **API và hợp đồng hành vi**; Hibernate Validator là một **implementation** phổ biến. Spring cung cấp các điểm tích hợp như `LocalValidatorFactoryBean`, `@Valid` trên tham số controller và `@Validated` để dùng groups. Spring và Jakarta Validation có nhiệm vụ riêng, không phải hai tên của cùng một thành phần.

## 3. Mô hình khai báo một constraint

Một constraint có ba lớp khái niệm:

```text
[Đối tượng cần kiểm tra]
        |
        |  @NotBlank(message = "Không được để trống")
        v
[Constraint metadata]
        |
        v
[Validation provider] -- tìm các ConstraintValidator tương thích
        |
        v
[isValid(value, context)]
        |
        +-- true  -> không tạo lỗi cho quy tắc đó
        |
        +-- false -> ConstraintViolation
                     propertyPath, message, invalidValue, descriptor...
```

Một constraint tiêu chuẩn hoặc tự viết có thể đặt tại các nơi mà annotation cho phép:

- **Field:** `@NotNull private String name;` — provider đọc trực tiếp field, kể cả khi field private.
- **JavaBean getter:** `@NotNull public String getName()` — provider dùng property getter.
- **Class/type:** constraint tùy chỉnh kiểm tra quan hệ giữa nhiều field, ví dụ `startDate <= endDate`.
- **Method/constructor parameter và return value:** kiểm tra hợp đồng phương thức thông qua executable validation hoặc tích hợp của framework.
- **Container element:** `List<@NotBlank String>` hoặc `Map<@NotBlank String, @Valid Address>`.
- **Record component:** với Java hiện đại và provider tương thích, có thể đặt constraint trên thành phần record.

**Không đặt cùng một constraint vô tình ở cả field và getter** của cùng thuộc tính nếu không muốn quy tắc có thể được đánh giá hai lần. Chọn chiến lược khai báo nhất quán.

### 3.1. Một annotation không tự bắt lỗi khi gán giá trị

Ví dụ:

```java
User user = new User();
user.setName("");
```

Nếu `User.name` có `@NotBlank`, lời gọi setter thông thường vẫn gán chuỗi trống. Việc tạo bean hoặc gọi setter không tự ném `ConstraintViolationException`. Lỗi xuất hiện khi gọi `Validator` hoặc khi Spring, JPA, method interceptor… thật sự kích hoạt validation. Ràng buộc chỉ nằm trong metadata nếu không được thực thi.

### 3.2. Mỗi lần validate có thể sinh nhiều lỗi

`Validator.validate(bean)` trả về `Set<ConstraintViolation<T>>`. Tập hợp này **không cam kết thứ tự lỗi**. Nếu cần kết quả kiểm thử cố định, sắp xếp theo `getPropertyPath()` rồi theo message. Không xây dựng logic phụ thuộc “constraint nào chạy trước” khi các constraint nằm trong cùng group, trừ khi có group sequence được khai báo rõ.

## 4. Những constraint có sẵn và cách chọn

Các annotation tiêu biểu thuộc `jakarta.validation.constraints`:

| Annotation | Ràng buộc | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| `@NotNull` | Giá trị khác `null` | `@NotNull Long id` | Chuỗi `""` và `" "` vẫn khác null |
| `@Null` | Giá trị phải là `null` | `@Null Long generatedId` | Hữu ích với field chỉ do server tạo |
| `@NotEmpty` | Không null và không rỗng | `@NotEmpty List<String> tags` | Với chuỗi `" "` vẫn được coi là không rỗng |
| `@NotBlank` | Chuỗi có ít nhất một ký tự không phải whitespace | `@NotBlank String name` | Dành cho `CharSequence` |
| `@Size(min=..., max=...)` | Kích thước chuỗi, collection, map hoặc array | `@Size(min=2,max=50)` | `null` được coi là hợp lệ; ghép `@NotNull` nếu cần |
| `@Min`, `@Max` | Cận giá trị số nguyên | `@Min(1) int count` | `@Min`/`@Max` nhận ngưỡng kiểu `long` |
| `@DecimalMin`, `@DecimalMax` | Cận thập phân, có thể đặt `inclusive=false` | `@DecimalMin("0.01")` | Dùng chuỗi cho giá trị cận |
| `@Positive`, `@PositiveOrZero` | Số dương / không âm | `@Positive Integer quantity` | `null` thường hợp lệ |
| `@Negative`, `@NegativeOrZero` | Số âm / không dương | `@Negative BigDecimal balance` | Chọn theo ý nghĩa miền dữ liệu |
| `@Digits(integer=..., fraction=...)` | Số chữ số phần nguyên/phần thập phân | `@Digits(integer=8,fraction=2)` | Không thay thế cận min/max nghiệp vụ |
| `@Pattern(regexp=...)` | Chuỗi thỏa regex | `@Pattern(regexp="[A-Z]{2}[0-9]{3}")` | `null` hợp lệ; áp dụng cho `CharSequence` |
| `@Email` | Cú pháp email theo validator | `@Email String email` | Không chứng minh email tồn tại; ghép `@NotBlank` nếu bắt buộc |
| `@Past`, `@PastOrPresent` | Thời gian quá khứ / không vượt hiện tại | `@Past LocalDate birthday` | Dùng clock của `ClockProvider` |
| `@Future`, `@FutureOrPresent` | Thời gian tương lai / không trước hiện tại | `@Future LocalDate expiry` | Tránh phụ thuộc thời điểm kiểm thử |
| `@AssertTrue`, `@AssertFalse` | Giá trị boolean theo mong đợi | `@AssertTrue Boolean accepted` | `null` hợp lệ; ghép `@NotNull` nếu bắt buộc |

Hai nhầm lẫn rất thường gặp:

```java
@NotNull
private String description; // "" vẫn hợp lệ đối với riêng @NotNull

@NotBlank
private String displayName; // null, "", "   " đều không hợp lệ
```

Các constraint như `@Size`, `@Pattern`, `@Positive`, `@Email`, `@Past` nhìn chung cho phép `null`; chúng kiểm tra **giá trị có mặt**, còn việc giá trị có được phép thiếu hay không do `@NotNull`/`@NotBlank`/`@NotEmpty` quyết định. Đừng suy ra `@Email` tự yêu cầu email bắt buộc.

`@Size(min=1)` và `@NotBlank` cũng khác nhau: chuỗi chỉ chứa một dấu cách đủ ký tự cho `@Size(min=1)`, nhưng không đạt `@NotBlank`.

## 5. Khai báo trên field, object lồng nhau và collection

### 5.1. Kiểm tra các thuộc tính của một bean

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ProductRequest {
    @NotBlank(message = "Tên sản phẩm bắt buộc")
    @Size(max = 120)
    private String name;

    @NotNull
    @Positive
    private Integer quantity;

    // Constructor, getter, setter tùy kiến trúc DTO
}
```

Đây là **mảnh minh họa DTO**, không phải một class có `main`. Với `quantity`, `@NotNull` từ chối trường hợp thiếu và `@Positive` từ chối 0/số âm; hai constraint bổ sung, không thay thế nhau.

### 5.2. `@Valid` cho đối tượng liên kết

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CheckoutRequest {
    @NotNull
    @Valid
    private Address shippingAddress;
}

public class Address {
    @NotBlank
    private String city;
}
```

**Ý nghĩa:** `@NotNull` yêu cầu có địa chỉ; `@Valid` yêu cầu validator đi sâu vào object `Address` và kiểm tra `city`. Nếu bỏ `@Valid`, chỉ constraint trên trường `shippingAddress` của lớp cha được xét, còn constraint thuộc lớp con không tự được quét. Nếu địa chỉ là `null`, cascade không chạy; `@NotNull` bắt lỗi đó.

Ở mô hình hoàn chỉnh có nhiều lớp, cùng một ý tưởng dùng cho `Order -> Customer -> Address`, nhưng cần tránh vòng lặp object phức tạp và tránh chạy validate trên đồ thị không cần thiết.

### 5.3. Constraint trên phần tử container

Từ các phiên bản Jakarta Validation hiện đại, annotation có thể áp dụng trực tiếp lên kiểu phần tử:

```java
import java.util.List;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class BatchRequest {
    @NotEmpty
    private List<@NotBlank String> codes;

    private Map<@NotBlank String, @Valid Address> addressByLabel;

    private List<@NotNull Integer> positions;
}
```

- `@NotEmpty` bên ngoài kiểm tra **danh sách có phần tử**.
- `@NotBlank` bên trong kiểm tra **từng chuỗi**.
- `@Valid` trên giá trị `Map` yêu cầu validate từng `Address`.
- `@NotNull` trên `Integer` kiểm tra từng vị trí không phải null.

`@Valid` và container element constraints là hai điều khác nhau: một cái kích hoạt **cascade vào bean con**, cái còn lại kiểm tra **mỗi phần tử**. Với các container tùy chỉnh, provider cần `ValueExtractor` thích hợp; không phải kiểu generic bất kỳ cũng được hỗ trợ tự động.

## 6. Validation group: một DTO, nhiều bối cảnh

Có những thuộc tính bắt buộc khi tạo mới nhưng không bắt buộc khi cập nhật, hoặc ngược lại. Group phân chia tập constraint cần đánh giá:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

interface OnCreate {}
interface OnUpdate {}

class DocumentCommand {
    @NotNull(groups = OnUpdate.class)
    private Long id;

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    private String title;
}
```

Các khai báo `OnCreate` và `OnUpdate` là **marker interface**, không cần phương thức. Ví dụ:

```java
validator.validate(command, OnCreate.class);
validator.validate(command, OnUpdate.class);
```

- Khi validate `OnCreate`: kiểm tra `title` theo group Create; constraint `id` trong Update không thuộc lần này.
- Khi validate `OnUpdate`: kiểm tra cả `id` và `title`.
- Constraint không ghi `groups` mặc định thuộc `jakarta.validation.groups.Default`.
- Gọi `validate(bean, OnCreate.class)` **không tự ghép group `Default`** trừ khi group có cấu trúc kế thừa/trình tự được khai báo phù hợp.

Có thể dùng `@GroupSequence` để chỉ định thứ tự group và ngăn đánh giá các nhóm sau nếu nhóm trước có lỗi. Không mặc nhiên cho rằng các constraint trong cùng group được chạy theo thứ tự viết trên field.

Trong Spring, `@Validated(OnCreate.class)` (thuộc `org.springframework.validation.annotation.Validated`) cho phép chọn group tại điểm tích hợp; `@Valid` (thuộc `jakarta.validation.Valid`) chủ yếu yêu cầu validation/cascade theo nhóm mặc định của bối cảnh hiện tại. **Không nhầm hai annotation vì chúng nằm ở các package khác nhau.**

## 7. Tự định nghĩa một constraint

Các annotation built-in không diễn đạt được mọi quy tắc. Ví dụ mã đơn hàng phải có mẫu `ORD-` theo sau bởi đúng ba chữ số.

Một **constraint annotation tùy chỉnh** cần:

1. `@Constraint(validatedBy = ...)`: kết nối với implementation.
2. `@Retention(RUNTIME)`: metadata phải hiện diện khi chạy.
3. `@Target(...)`: giới hạn vị trí được gắn.
4. Ba thuộc tính bắt buộc: `String message()`, `Class<?>[] groups()`, `Class<? extends Payload>[] payload()`.
5. Một `ConstraintValidator<AnnotationType, ValueType>` triển khai logic trong `isValid(...)`.

Các thuộc tính khác như `min`, `max` hoặc `prefix` có thể thêm để cấu hình từng cách dùng annotation. `payload` là nơi đính kèm metadata cho ứng dụng; Jakarta Validation không tự hiểu nó là HTTP status, mức độ lỗi hay UI severity.

### 7.1. Chọn quy ước cho null

Với các custom constraint kiểm tra **định dạng**, thường cho `null` hợp lệ:

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.matches("ORD-[0-9]{3}");
}
```

Sau đó đặt `@NotNull` hoặc `@NotBlank` nếu field bắt buộc. Cách này tách lỗi “thiếu giá trị” và lỗi “sai định dạng”. Không phải mọi constraint đều phải cho null hợp lệ; một custom constraint có thể được thiết kế khác, nhưng phải được định nghĩa và kiểm thử rõ.

**`ConstraintValidator` có thể được provider tái sử dụng và gọi đồng thời**; không giữ giá trị đang validate trong trường mutable dùng chung. `initialize(annotation)` nếu cần chỉ nên đọc cấu hình annotation để chuẩn bị logic; `isValid` không sửa object đầu vào.

### 7.2. Constraint cấp class

Nếu yêu cầu `start <= end`, một `@ValidDateRange` có `@Target(TYPE)` và `ConstraintValidator<ValidDateRange, Booking>` phù hợp hơn việc áp một `@Future` lên từng field. Lớp validator đọc cả `start` và `end` rồi trả về kết quả của quan hệ. Có thể dùng `ConstraintValidatorContext` để gắn lỗi vào đường dẫn property cụ thể thay vì chỉ ở root bean.

Đừng truy cập DB hay gọi API mạng từ `isValid` cho mọi validation request nếu không có lý do nghiệp vụ rõ ràng; trường hợp cần dữ liệu bên ngoài nên được thiết kế và kiểm soát ở tầng service.

### 7.3. Constraint composition

Một annotation mới cũng có thể **kết hợp nhiều constraint có sẵn**, ví dụ `@NotBlank` và `@Size`, bằng cách gắn các annotation đó trên định nghĩa annotation tự tạo. `@ReportAsSingleViolation` dùng khi muốn báo một lỗi tổng hợp thay vì từng lỗi con. Đây là cơ chế khai báo, khác với viết một `ConstraintValidator` kiểm tra tùy ý.

## 8. Ví dụ Java 17+ hoàn chỉnh: gọi Jakarta Validator trực tiếp

Ví dụ sau kiểm chứng cả built-in constraints, custom constraint và `@Valid` cascade. Không cần Spring Web, nhưng cần **Jakarta Validation API và implementation**.

Cấu trúc:

```text
validation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── validation/
                    └── ValidationDemo.java
```

Tệp `pom.xml` (Maven với Java 17; Hibernate Validator 8 là provider cho Jakarta Validation 3.0 API):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validation-demo</artifactId>
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

Hibernate Validator mang API `jakarta.validation` thông qua dependency; dependency EL cung cấp expression-language implementation cho message interpolation mặc định. Dự án thật nên dùng các phiên bản tương thích được quản lý bằng dependency management; các version trên chỉ phục vụ bài thực hành tái lập.

Tệp `src/main/java/example/validation/ValidationDemo.java`:

```java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Comparator;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public class ValidationDemo {

    @Documented
    @Constraint(validatedBy = OrderCodeValidator.class)
    @Target({ElementType.FIELD, ElementType.PARAMETER})
    @Retention(RetentionPolicy.RUNTIME)
    public @interface OrderCode {
        String message() default "code format invalid";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static class OrderCodeValidator
            implements ConstraintValidator<OrderCode, String> {

        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            return value == null || value.matches("ORD-[0-9]{3}");
        }
    }

    public static class Address {
        @NotBlank(message = "city is required")
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static class OrderRequest {
        @NotBlank(message = "code is required")
        @OrderCode
        private final String code;

        @NotNull(message = "quantity is required")
        @Positive(message = "quantity must be positive")
        private final Integer quantity;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        public OrderRequest(String code, Integer quantity, Address address) {
            this.code = code;
            this.quantity = quantity;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            OrderRequest bad =
                    new OrderRequest("BAD", 0, new Address(" "));

            validator.validate(bad).stream()
                    .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                    .sorted(Comparator.naturalOrder())
                    .forEach(System.out::println);

            OrderRequest good =
                    new OrderRequest("ORD-123", 2, new Address("Ha Noi"));
            System.out.println("valid-count="
                    + validator.validate(good).size());
        }
    }
}
```

Chạy trong thư mục `validation-demo`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.validation.ValidationDemo
```

Các dòng chương trình ghi ra **stdout** (không tính thông báo/nhật ký từ Maven hoặc thư viện):

```text
address.city: city is required
code: code format invalid
quantity: quantity must be positive
valid-count=0
```

Giải thích:

- `code="BAD"` không rỗng, nên `@NotBlank` đạt; `@OrderCode` thất bại.
- `quantity=0` không null, nên `@NotNull` đạt; `@Positive` thất bại.
- `address` không null, nhưng `@Valid` đi sâu vào `address.city=" "`, làm `@NotBlank` thất bại.
- Trên `good`, mọi constraint đều đạt, `validate(good).size()` bằng 0.
- `sorted(...)` làm cho thứ tự in ổn định; nếu bỏ sắp xếp, thứ tự của `Set<ConstraintViolation>` không được bảo đảm.
- `ValidatorFactory` được đóng bằng `try-with-resources` sau khi dùng.

Ví dụ có thể kiểm thử riêng từng trường hợp `null`: `@OrderCode` của bài cho `null` hợp lệ, còn `@NotBlank` hoặc `@NotNull` mới từ chối giá trị thiếu.

## 9. Tích hợp vào Spring MVC / Spring Boot

Trong Spring Boot 3+, dependency thường cần:

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

Các dependency trên thuộc dự án Spring Boot đã có parent/BOM quản lý phiên bản. **Thêm starter-web không bảo đảm đã có validation provider trong mọi cấu hình**; starter-validation cung cấp tích hợp phổ biến với Hibernate Validator.

Ví dụ sau là một file ứng dụng Spring Boot Java 17+, dùng `@Valid @RequestBody` để validate request JSON trước khi chạy business logic.

Tệp `src/main/java/example/webvalidation/ValidationWebApplication.java`:

```java
package example.webvalidation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ValidationWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationWebApplication.class, args);
    }

    public record AddressRequest(
            @NotBlank String city) {}

    public record CreateCustomerRequest(
            @NotBlank String name,
            @NotBlank @Email String email,
            @NotNull @Valid AddressRequest address) {}

    @RestController
    @RequestMapping("/customers")
    public static class CustomerController {

        @PostMapping
        public Map<String, String> create(
                @Valid @RequestBody CreateCustomerRequest request) {
            return Map.of(
                    "name", request.name(),
                    "city", request.address().city());
        }
    }
}
```

Giả sử ứng dụng dùng cổng `8080`. Request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","address":{"city":"Ha Noi"}}'
```

Controller trả JSON chứa `name` và `city`; thứ tự các key JSON không được bảo đảm.

Request không hợp lệ:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"invalid","address":{"city":""}}'
```

Với tích hợp mặc định, các constraint thất bại khiến Spring MVC trả lỗi HTTP **400** trước khi vào phần thân `create(...)`; hình dạng JSON error response còn tùy cấu hình xử lý lỗi của ứng dụng. Dữ liệu JSON được **Jackson deserialize** thành `CreateCustomerRequest`; sau đó Jakarta Validation kiểm tra các annotation. Parse JSON không hợp lệ có thể bị từ chối ở bước chuyển đổi trước khi validation diễn ra.

### 9.1. Data binding khác Bean Validation như thế nào?

```text
HTTP request
   |
   v
[Đọc và chuyển đổi] -- Jackson / HttpMessageConverter / WebDataBinder
   |                 -- sai cú pháp JSON, sai kiểu, sai định dạng ngày... -> lỗi binding
   v
[DTO đã được tạo]
   |
   v
[Jakarta Validation] -- @NotNull / @Size / @Valid / custom constraint
   |                 -- ConstraintViolation / errors
   v
[Controller xử lý nghiệp vụ] -- kiểm tra tồn tại, quyền truy cập,
                              tính nhất quán trạng thái, giao dịch...
```

Validation không thay thế bước conversion, và thành công ở cả hai bước chưa chứng minh toàn bộ nghiệp vụ hợp lệ.

### 9.2. `@Valid` và `@Validated` trong Spring

- `@Valid` là annotation chuẩn Jakarta, thường dùng trên `@RequestBody`, `@ModelAttribute` và property lồng nhau để kích hoạt validation/cascade.
- `@Validated` là annotation của Spring, dùng khi cần **validation groups** và trong một số cơ chế method validation qua Spring.
- Với `@ModelAttribute`, có thể đặt `BindingResult` ngay sau tham số cần validate để xử lý lỗi ngay trong controller.
- Với `@RequestBody` thông thường, `@Valid` có thể gây `MethodArgumentNotValidException`; Spring MVC mặc định chuyển thành HTTP 400.
- Từ Spring Framework 6.1, nếu method có constraint trực tiếp trên tham số/giá trị trả về, cơ chế method validation tích hợp có thể sinh `HandlerMethodValidationException`. Nếu ứng dụng đặt `@Validated` ở class controller, cơ chế AOP method validation có thể được dùng; cần phân biệt với cơ chế tích hợp MVC khi cấu hình.

**Ví dụ chọn group** (đoạn minh họa đặt trong controller có DTO/group đã định nghĩa):

```java
@PostMapping("/drafts")
public void create(
        @Validated(OnCreate.class) @RequestBody DocumentCommand request) {
    // Xử lý khi constraints của nhóm OnCreate hợp lệ.
}
```

Việc viết `@Validated(OnCreate.class)` không làm cho constraint thuộc nhóm `Default` tự được chạy, trừ khi có quy tắc nhóm tương ứng.

## 10. Constraint trên method và constructor

Jakarta Validation có thể khai báo hợp đồng đầu vào/đầu ra phương thức:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public interface PricingService {
    @Positive
    long calculatePrice(@NotBlank String productCode);
}
```

Đoạn trên là **interface minh họa**. Annotation không chạy chỉ vì có một lời gọi Java bình thường tới `calculatePrice`. Cần cơ chế gọi `ExecutableValidator` hoặc tích hợp Spring method validation/AOP (tùy phiên bản và vị trí). Constraint trên return value và parameter kiểm tra hai thời điểm khác nhau. Không dùng cùng một class-level `@Validated` một cách máy móc khi dự án đã dùng Spring MVC 6.1+ built-in method validation.

Đối với cross-parameter constraint (ví dụ `start` không được sau `end` ở hai tham số), cần validator hỗ trợ target `PARAMETERS`; khác với class-level constraint kiểm tra hai field trên một DTO. Đây là phần mở rộng khi mô hình phương thức thật sự cần.

## 11. Thông báo lỗi, metadata và i18n

Mỗi constraint có `message`:

```java
@NotBlank(message = "{user.name.required}")
private String name;
```

Provider có thể nội suy message key từ resource bundle `ValidationMessages.properties`. Thông báo `message` có thể chứa placeholder như `{min}`, `{max}` đối với constraint có các thuộc tính tương ứng. Ở Spring, cấu hình `MessageSource` và `LocalValidatorFactoryBean` có thể giúp thống nhất bản địa hóa; chi tiết phụ thuộc cấu hình ứng dụng.

Kết quả `ConstraintViolation` thường cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `getPropertyPath()` | Đường dẫn field hoặc node vi phạm, có thể bao gồm phần tử container |
| `getMessage()` | Thông báo đã nội suy |
| `getMessageTemplate()` | Mẫu thông báo ban đầu, ví dụ một message key |
| `getInvalidValue()` | Giá trị gây lỗi (cẩn trọng khi log dữ liệu người dùng) |
| `getRootBean()` | Đối tượng gốc đang validate |
| `getConstraintDescriptor()` | Metadata của annotation, thuộc tính, groups, validator… |

Ứng dụng có thể chuyển lỗi thành cấu trúc ổn định như `field`, `code`, `message`, nhưng đây là quyết định API. Không phụ thuộc message tiếng Anh mặc định của provider để xây dựng mã lỗi nghiệp vụ.

## 12. Những lỗi thiết kế và suy luận thường gặp

1. **Gọi `new Dto(...)` rồi tưởng annotation tự chạy.** Cần kích hoạt `Validator` hoặc để framework tích hợp thực thi.
2. **Chỉ dùng `@Size` cho field bắt buộc.** `null` có thể vượt qua; thêm `@NotNull` hoặc `@NotBlank` theo kiểu dữ liệu.
3. **Cho rằng `@Email` xác nhận địa chỉ có thể nhận thư.** Nó chỉ kiểm tra hình thức theo validator.
4. **Dùng `@NotBlank` cho số hoặc collection.** `@NotBlank` dành cho chuỗi; với collection chọn `@NotEmpty`, `@Size`.
5. **Đặt constraint trên bean con nhưng quên `@Valid` ở quan hệ cha.** Validation không đi sâu vào object con.
6. **Đặt `@NotEmpty` trên danh sách rồi tưởng từng item cũng hợp lệ.** Cần constraint ở generic type argument.
7. **Dùng nhóm Create khi mong cả `Default` được kiểm tra.** Phải thiết kế groups/sequence rõ ràng.
8. **Trộn `javax.validation` với `jakarta.validation` khi nâng cấp Spring 6/Boot 3.** Dùng namespace/API tương thích phiên bản.
9. **Viết custom validator luôn trả false khi null mà không xét thiết kế.** Phân tách “missing” và “invalid format” giúp tránh báo lỗi không rõ ràng.
10. **Dùng field constraint cho điều kiện liên quan hai field.** Cân nhắc class-level constraint hoặc validation nghiệp vụ ở service.
11. **Dựa vào thứ tự `ConstraintViolation` được trả về.** Kết quả là `Set`; sắp xếp nếu cần order cố định.
12. **Coi Jakarta Validation là thay thế cho DB constraint.** Quy tắc unique, foreign key, race condition và tính nhất quán giao dịch vẫn cần kiểm soát ở database/service.
13. **Chạy validate dữ liệu quá rộng không cần thiết.** Chọn boundary/DTO, cascade và group có chủ đích; không validate nhầm toàn bộ entity graph.
14. **Gộp lỗi binding với lỗi Bean Validation thành một nguyên nhân.** Sai kiểu dữ liệu có thể lỗi ngay trước khi constraint được kiểm tra.

## 13. Bài tập tự đánh giá

**Bài 1.** Một form có `String username` bắt buộc, không nhận chỉ toàn khoảng trắng và tối đa 32 ký tự. Khai báo gì?

```java
@NotBlank
@Size(max = 32)
private String username;
```

**Bài 2.** `List<String> tags` phải có ít nhất một phần tử, và mỗi phần tử không rỗng/không chỉ có khoảng trắng.

```java
@NotEmpty
private List<@NotBlank String> tags;
```

**Bài 3.** Vì sao chỉ dùng `@Positive Integer quantity` chưa đủ nếu `quantity` bắt buộc? Vì `@Positive` không làm `null` sai; cần `@NotNull` bổ sung.

**Bài 4.** Một DTO chứa `Address address`, lớp `Address` có `@NotBlank city`. Field `address` chỉ có `@NotNull`. Liệu `city=""` bị phát hiện không? Không, vì chưa có `@Valid` để cascade vào `Address`.

**Bài 5.** Khi gọi `validator.validate(dto, OnUpdate.class)`, constraint chỉ khai báo `Default` có tự chạy không? Không tự động, trừ khi có quan hệ groups/sequence đã định nghĩa tương ứng.

**Bài 6.** Tự thiết kế `@ValidPeriod` kiểm tra `startDate <= endDate`. Nêu vị trí khai báo hợp lý: `TYPE`, validator nhận DTO chứa cả hai ngày; cho phép hoặc từ chối null theo quy ước riêng, và kết hợp `@NotNull` cho trường bắt buộc.

**Bài 7.** Vì sao `@Valid @RequestBody` có thể trả 400 trước khi vào controller? Spring MVC dùng validation provider sau bước deserialize DTO; lỗi constraint dẫn tới lỗi tham số request và cơ chế HTTP error mặc định.

## 14. Ghi nhớ khi áp dụng

- Jakarta Validation cung cấp **mô hình khai báo constraint bằng annotation**, còn provider thực thi các quy tắc.
- Constraint không tự chạy; phải có điểm kích hoạt `Validator` hoặc tích hợp framework.
- Tách rõ: **có dữ liệu** (`@NotNull`/`@NotBlank`), **giá trị hợp lệ** (`@Size`/`@Pattern`/`@Positive`) và **quan hệ nghiệp vụ**.
- `@Valid` cascade vào bean con; constraint trên generic type argument kiểm tra từng phần tử.
- `groups` điều khiển tập constraint được chạy; `Default` không tự đi kèm mọi group khác.
- Custom constraint phải có `@Constraint`, `message`, `groups`, `payload` và validator tương thích khi cần mã kiểm tra riêng.
- Với Spring Boot 3+, dùng `jakarta.validation` và dependency provider thích hợp; phân biệt lỗi JSON/binding, lỗi Jakarta Validation và lỗi nghiệp vụ.

### Tài liệu tham khảo

- Jakarta Validation 3.1 Specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API, `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint
- Hibernate Validator 8 Reference Guide: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Validation in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
