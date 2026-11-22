# Kiểu dữ liệu được hỗ trợ và UnexpectedTypeException trong Jakarta Bean Validation và Spring

## 1. Vấn đề cốt lõi: constraint không áp dụng cho mọi kiểu Java

Các annotation chuẩn như `@NotBlank`, `@Size`, `@Min`, `@Positive`, `@Past` hay `@Email` đều khai báo một quy tắc, nhưng **mỗi quy tắc chỉ hỗ trợ những kiểu dữ liệu nhất định**. Java thường cho phép gắn annotation lên một field dù kiểu Java của field không tương thích: annotation có `@Target(FIELD)` không có nghĩa nó dùng được cho tất cả kiểu field.

Ví dụ:

```java
@NotBlank
private Integer quantity;
```

Đoạn trên có thể **biên dịch thành công**, vì Java kiểm tra vị trí annotation, không tự biết `@NotBlank` chỉ dành cho `CharSequence`. Khi có một lượt Bean Validation xử lý field này, provider không tìm thấy `ConstraintValidator` thích hợp cho tổ hợp `(@NotBlank, Integer)` và ném `jakarta.validation.UnexpectedTypeException`.

Phân biệt:

- **Giá trị không đạt ràng buộc trên kiểu được hỗ trợ:** provider tạo `ConstraintViolation`; ví dụ `@Positive Integer quantity = 0`.
- **Khai báo constraint sai kiểu hoặc mơ hồ:** provider không thể chọn một implementation thích hợp và ném `UnexpectedTypeException`; ví dụ `@NotBlank Integer quantity = 1`.
- **Không có provider/không kích hoạt validation:** là lỗi cấu hình hoặc thiếu trigger khác; không thể kết luận chỉ từ việc field có annotation.

Thông điệp chính: **chọn constraint theo kiểu Java đã khai báo, sau đó mới xét giá trị nào hợp lệ**. Đừng suy rằng một annotation chỉ vì tên nghe hợp lý sẽ có validator cho kiểu dữ liệu đang dùng.

## 2. Bean Validation quyết định hỗ trợ kiểu bằng cách nào?

Một constraint có thể được thực thi bởi một hay nhiều implementation theo giao diện:

```java
ConstraintValidator<ConstraintAnnotation, SupportedType>
```

Ví dụ về mặt khái niệm, một validator của `@NotBlank` nhận `CharSequence`; vì `String` hiện thực `CharSequence` nên phù hợp. `Integer` không phải subtype của `CharSequence` nên không phù hợp.

Trong một lượt validation, provider căn cứ vào:

1. **Constraint annotation** được áp dụng, chẳng hạn `@Size`.
2. **Kiểu đã khai báo** tại vị trí bị kiểm tra, chẳng hạn `String`, `List<String>`, `BigDecimal` hoặc `Integer`.
3. Danh sách `ConstraintValidator` mà provider biết cho constraint đó, gồm implementation chuẩn và các extension được cấu hình.
4. Quy tắc so khớp kiểu và chọn validator **cụ thể nhất, duy nhất** trong các validator phù hợp.

Hai tình huống dẫn đến `UnexpectedTypeException`:

- **Không có validator phù hợp:** ví dụ `@NotBlank` trên `Integer`.
- **Có nhiều validator phù hợp nhưng không chọn được một cái cụ thể nhất:** thường gặp ở custom constraint khi hai validator nhận những interface không liên hệ kế thừa với nhau mà kiểu field triển khai cả hai.

Theo Jakarta Validation, nguyên tắc so khớp dựa trên quan hệ subtype giữa kiểu được validate và kiểu validator hỗ trợ; primitive được xem tương đương wrapper tương ứng khi giải quyết validator. Trong cấu hình thông thường, lỗi được phát hiện khi gọi `validate(...)`, hoặc sớm hơn khi provider cần phân giải metadata. Không phải lỗi cú pháp Java.

```text
Constraint annotation + kiểu field đã khai báo
                      |
                Provider tra cứu
                      |
       +--------------+---------------+
       |              |               |
  Đúng 1 loại      Không có        Nhiều loại
  phù hợp nhất     loại phù hợp    cùng cụ thể nhất
       |              |               |
    isValid(...)    UnexpectedTypeException
       |
       +-- true  -> không có violation
       +-- false -> ConstraintViolation
```

Vì đây là lỗi chọn validator theo kiểu, việc giá trị hiện tại là `null` **không bảo đảm tránh được** `UnexpectedTypeException`. Đừng dựa vào vài test dữ liệu null để chứng minh khai báo annotation hợp lệ.

## 3. Bảng tra nhanh kiểu dữ liệu theo constraint chuẩn

Bảng dưới đây bám theo **Jakarta Validation 3.1, chương “Built-in Constraint definitions”**. Những kiểu hoặc tính năng do một provider bổ sung sẽ được nêu riêng; không xem extension là bảo đảm di động giữa các provider.

| Constraint | Kiểu được chuẩn hỗ trợ | Điều kiện chính | Áp dụng sai hay gặp |
| --- | --- | --- | --- |
| `@Null`, `@NotNull` | Mọi kiểu | Phải null / không được null | Dùng `@NotNull` trên primitive `int` không có ý nghĩa bắt null |
| `@AssertTrue`, `@AssertFalse` | `boolean`, `Boolean` | Đúng / sai | Gắn trên `String` chứa `"true"` |
| `@NotBlank` | `CharSequence` và subtype như `String`, `StringBuilder` | Không null, có ít nhất một ký tự không trắng | Gắn trên `Integer`, `List`, enum |
| `@NotEmpty` | `CharSequence`, `Collection`, `Map`, mảng | Không null, kích thước lớn hơn 0 | Gắn trên số hoặc một JavaBean bất kỳ |
| `@Size(min,max)` | `CharSequence`, `Collection`, `Map`, mảng | Độ dài/số phần tử trong đoạn đóng | Gắn trên `Integer`/`BigDecimal` để kiểm tra số lớn nhỏ |
| `@Pattern(regexp=...)` | `CharSequence` | Chuỗi phù hợp regex | Gắn trên enum hoặc number |
| `@Email` | `CharSequence` | Email có cấu trúc hợp lệ theo provider | Gắn trên `Integer`, `byte[]` |
| `@Min`, `@Max` | `BigDecimal`, `BigInteger`, `byte/short/int/long` và wrapper | Lớn hơn/nhỏ hơn hoặc bằng ngưỡng kiểu `long` | Gắn trên `String`, `LocalDate`, `List` |
| `@DecimalMin`, `@DecimalMax` | Nhóm số nguyên và `BigDecimal/BigInteger` như trên, thêm `CharSequence` | So sánh với ngưỡng số thập phân dạng chuỗi; có `inclusive` | Dùng làm giới hạn độ dài chuỗi |
| `@Positive`, `@PositiveOrZero` | `BigDecimal`, `BigInteger`, các primitive/wrapper số gồm `float/double` | `> 0` / `>= 0` | Gắn trên `String` chứa chữ số |
| `@Negative`, `@NegativeOrZero` | Cùng nhóm kiểu số của `@Positive` | `< 0` / `<= 0` | Gắn trên chuỗi hay enum |
| `@Digits(integer, fraction)` | `BigDecimal`, `BigInteger`, `CharSequence`, nhóm số nguyên và wrapper | Giới hạn số chữ số nguyên và phần thập phân | Dùng để giới hạn trị tuyệt đối hoặc áp lên `LocalDate` |
| `@Past`, `@PastOrPresent` | `Date`, `Calendar` và các kiểu ngày/giờ `java.time` chuẩn hỗ trợ | Trước hiện tại / trước hoặc bằng hiện tại | Gắn lên `String` ISO chưa parse |
| `@Future`, `@FutureOrPresent` | Cùng nhóm kiểu thời gian của `@Past` | Sau hiện tại / sau hoặc bằng hiện tại | Gắn lên `Long` timestamp hoặc `String` |

**Lưu ý chuẩn cho số thực:** `float`/`double` **không thuộc tập kiểu bắt buộc được hỗ trợ bởi `@Min`, `@Max`, `@DecimalMin` và `@DecimalMax`** vì rủi ro làm tròn; một số provider có extension. Ngược lại, `@Positive`/`@Negative` và biến thể “or zero” **có** hỗ trợ `float`/`double` theo chuẩn. Nếu dữ liệu tiền tệ hoặc độ chính xác thập phân quan trọng, ưu tiên `BigDecimal`.

**Chọn theo nghiệp vụ thay vì học thuộc bảng:** một chuỗi email được kiểm tra bằng `@Email`, một tập hàng hóa dùng `@NotEmpty`/`@Size`, một số lượng dùng `@Positive`/`@Min`, một ngày kết thúc dùng `@Future`. Cùng một từ “lớn hơn” có thể là **độ dài**, **giá trị số**, hoặc **thời điểm**: chúng là các loại constraint khác nhau.

## 4. `@NotNull`, `@NotEmpty`, `@NotBlank` và `@Size` không thay thế cho nhau

Chúng cùng có thể xuất hiện trên `String`, nhưng ngữ nghĩa không giống nhau.

| Giá trị `String` | `@NotNull` | `@NotEmpty` | `@NotBlank` | `@Size(min=1)` |
| --- | --- | --- | --- | --- |
| `null` | Lỗi | Lỗi | Lỗi | Hợp lệ |
| `""` | Hợp lệ | Lỗi | Lỗi | Lỗi |
| `"   "` | Hợp lệ | Hợp lệ | Lỗi | Hợp lệ |
| `"abc"` | Hợp lệ | Hợp lệ | Hợp lệ | Hợp lệ |

`@Size` mặc định coi `null` là hợp lệ, nên khi cần bắt buộc nhập tên có độ dài 3–50 ký tự, thường kết hợp `@NotBlank` với `@Size(min=3, max=50)`.

```java
@NotBlank
@Size(min = 3, max = 50)
private String displayName;
```

Đối với danh sách, `@NotBlank` **không có nghĩa** “danh sách không rỗng”:

```java
@NotEmpty
private List<String> tags;

@Size(min = 1, max = 10)
private List<String> categories;
```

Hai đoạn trên là field trong một bean có import `List` và constraint. Chúng kiểm tra **số phần tử** của collection. Nếu muốn kiểm tra **nội dung từng chuỗi bên trong**, phải đặt constraint ở type argument, ví dụ `List<@NotBlank String>`.

`@NotNull` trên `int` luôn đúng về null vì primitive không có giá trị null. Với input có thể vắng mặt, dùng wrapper `Integer` và `@NotNull`; dùng `@Positive` để kiểm tra số dương khi giá trị có mặt.

## 5. Các kiểu số: trị số khác độ dài, precision khác range

Ví dụ sai:

```java
@Size(min = 1, max = 10)
private Integer quantity; // Sai: Integer không có "size" theo @Size
```

Thay bằng:

```java
@NotNull
@Min(1)
@Max(10)
private Integer quantity;
```

Hoặc nếu chỉ cần lớn hơn 0:

```java
@NotNull
@Positive
private Integer quantity;
```

Với tiền:

```java
@NotNull
@DecimalMin(value = "0.00", inclusive = true)
@Digits(integer = 8, fraction = 2)
private BigDecimal price;
```

`@DecimalMin("0.00")` bảo đảm không âm, còn `@Digits(integer=8,fraction=2)` giới hạn số chữ số. `@Digits` **không phải** constraint giới hạn giá trị theo một cận; ví dụ `99999999.99` phù hợp cấu trúc chữ số nhưng có thể vượt giới hạn nghiệp vụ mà ứng dụng chưa diễn đạt.

Đối với `BigDecimal`, dùng số nguyên và số thập phân theo hợp đồng cụ thể; **`@Min` nhận thuộc tính `long`** còn `@DecimalMin` nhận chuỗi để biểu diễn các cận như `"0.01"`. Không áp `@Size(max=8)` lên `BigDecimal` để hạn chế độ lớn.

Dùng `@Positive` với `double` được chuẩn hỗ trợ, nhưng độ chính xác IEEE 754 và trường hợp NaN/infinity (tùy provider) cần được kiểm soát bằng kiểu dữ liệu/quy tắc phù hợp; không xem Bean Validation là thay thế cho lựa chọn kiểu số đúng.

## 6. Ngày giờ và giá trị chữ: phải parse sang kiểu temporal thích hợp

Ví dụ sai:

```java
@Past
private String birthDate; // Sai theo chuẩn: String không phải temporal type
```

Sửa:

```java
@NotNull
@Past
private LocalDate birthDate;
```

Ở API Spring MVC, chuỗi đầu vào `"2000-01-01"` phải được bind/parse thành `LocalDate` trước khi provider kiểm tra `@Past`. Có thể dùng `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` cho query/form binding; JSON body dùng cấu hình Jackson thích hợp. `@DateTimeFormat` **là cơ chế conversion**, không mở rộng `@Past` sang `String`.

Các kiểu thời gian được chuẩn hỗ trợ cho `@Past`/`@Future` và biến thể bao gồm `java.util.Date`, `Calendar`, `Instant`, `LocalDate`, `LocalDateTime`, `LocalTime`, `OffsetDateTime`, `OffsetTime`, `ZonedDateTime`, `MonthDay`, `Year`, `YearMonth` và các chronology types như `HijrahDate`, `JapaneseDate`, `MinguoDate`, `ThaiBuddhistDate`.

“Hiện tại” trong temporal constraints do `ClockProvider` của Jakarta Validation cung cấp. Kiểm thử thời gian nên dùng `ClockProvider` cố định khi cần kết quả bất biến theo thời điểm chạy; đặc biệt lưu ý vùng múi giờ khi dùng `LocalDate`/`LocalTime`.

Gắn `@Future` lên `Long` biểu diễn milliseconds từ epoch **không phải** cách dùng portable. Nếu phải lưu giá trị số epoch, đổi sang `Instant` tại biên của ứng dụng hoặc viết custom constraint đúng kiểu.

## 7. UnexpectedTypeException khác ConstraintViolation thế nào?

`jakarta.validation.UnexpectedTypeException` là lớp con của:

```text
RuntimeException
  └── ValidationException
       └── ConstraintDeclarationException
            └── UnexpectedTypeException
```

Nó biểu thị **không giải quyết được validator cho khai báo constraint/type**. Nó không phải `ConstraintViolation` bình thường và không phải `ConstraintViolationException` (lớp khác, thường được Spring dùng khi tích hợp method validation).

So sánh hai field:

```java
@Positive
private Integer quantity = 0; // Kiểu đúng; giá trị không đạt
```

Gọi `validator.validate(bean)` có thể trả `Set<ConstraintViolation<?>>` với lỗi trên `quantity`. Không phải `UnexpectedTypeException`.

```java
@NotBlank
private Integer quantity = 7; // Kiểu sai; chưa thể chạy constraint
```

Gọi `validator.validate(bean)` có thể ném `UnexpectedTypeException` thay vì trả một tập lỗi cho field. `Integer` không triển khai `CharSequence`, dù giá trị là 7, 0 hoặc null.

Với Hibernate Validator, thông báo thường có dạng tương tự:

```text
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.NotBlank' validating type
'java.lang.Integer'. Check configuration for 'quantity'
```

Đây là **mẫu thông báo**, không phải yêu cầu message tuyệt đối giống nhau giữa phiên bản/provider. `HV000030` là mã thông báo của Hibernate Validator; Jakarta API chuẩn hóa **loại exception**, không chuẩn hóa đoạn chữ hiển thị từ mọi provider.

Không bắt `UnexpectedTypeException` để đổi tất cả thành “người dùng nhập dữ liệu sai”. Constraint/type không tương thích thường là **lỗi lập trình hoặc cấu hình phía máy chủ**; sửa DTO/annotation/custom validator và thêm test để phát hiện sớm.

## 8. Ví dụ chạy được với Java 17 và Spring Boot

Ví dụ đầy đủ sau cố ý đặt một constraint sai kiểu ở **một class riêng**, sau khi đã kiểm tra object hợp lệ và không hợp lệ theo cách bình thường. Nhờ vậy ta phân biệt chính xác:

1. Bean có đủ điều kiện → 0 violation.
2. Bean có 5 giá trị sai nhưng kiểu field hợp lệ → 5 violation.
3. Bean gắn `@NotBlank` lên `Integer` → ném `UnexpectedTypeException`.

Cấu trúc:

```text
constraint-type-demo/
├── pom.xml
└── src/main/java/demo/ConstraintTypeDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>constraint-type-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/ConstraintTypeDemo.java`

```java
package demo;

import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;

import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConstraintTypeDemo {

    public static void main(String[] args) {
        SpringApplication.run(ConstraintTypeDemo.class, args);
    }

    @Bean
    ApplicationRunner run(jakarta.validation.Validator validator) {
        return args -> {
            Order valid = new Order(
                    "Linh",
                    List.of("java"),
                    3,
                    "ABC",
                    LocalDate.of(2100, 1, 1));

            System.out.println("Valid violations: "
                    + validator.validate(valid).size());

            Order invalid = new Order(
                    "   ",
                    List.of(),
                    0,
                    "A",
                    LocalDate.of(2000, 1, 1));

            var violations = validator.validate(invalid);
            String paths = violations.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .sorted()
                    .collect(Collectors.joining(", "));

            System.out.println("Invalid violations: "
                    + violations.size());
            System.out.println("Invalid fields: " + paths);

            try {
                validator.validate(new WrongType());
            } catch (UnexpectedTypeException ex) {
                System.out.println("Mismatched constraint: "
                        + ex.getClass().getSimpleName());
            }
        };
    }

    static final class Order {
        @NotBlank
        private final String name;

        @NotEmpty
        private final List<String> tags;

        @Positive
        private final Integer quantity;

        @Size(min = 3, max = 8)
        private final String code;

        @Future
        private final LocalDate deliveryDate;

        Order(String name, List<String> tags,
              Integer quantity, String code, LocalDate deliveryDate) {
            this.name = name;
            this.tags = tags;
            this.quantity = quantity;
            this.code = code;
            this.deliveryDate = deliveryDate;
        }
    }

    static final class WrongType {
        // Cố ý sai để minh họa UnexpectedTypeException.
        @NotBlank
        private final Integer quantity = 7;
    }
}
```

Chạy với Maven và JDK 17+ tại thư mục `constraint-type-demo`:

```bash
mvn spring-boot:run
```

Ngoài các log khởi động thông thường, các dòng do chương trình in ra là:

```text
Valid violations: 0
Invalid violations: 5
Invalid fields: code, deliveryDate, name, quantity, tags
Mismatched constraint: UnexpectedTypeException
```

**Tại sao 5 lỗi?** `"   "` không đạt `@NotBlank`, `List.of()` rỗng không đạt `@NotEmpty`, 0 không đạt `@Positive`, `"A"` quá ngắn so với `@Size(min=3)`, và năm 2000 nằm trong quá khứ nên không đạt `@Future`. Kiểm tra sắp xếp property paths trước khi in vì `Set<ConstraintViolation<?>>` không bảo đảm thứ tự duyệt.

**Tại sao lỗi thứ ba khác?** `WrongType.quantity` có kiểu khai báo `Integer`, trong khi `@NotBlank` chỉ hỗ trợ `CharSequence`. Provider không thể chọn validator thích hợp, nên không có phép kiểm tra giá trị “đúng/sai” thông thường.

Ví dụ sử dụng `spring-boot-starter-validation` để Boot cung cấp provider và một `jakarta.validation.Validator` do Spring quản lý. Mã Java và output ở trên có thể kiểm tra bằng Maven; khi copy vào một dự án khác phải giữ package, file và dependency tương ứng. Đừng xem việc một demo riêng chạy được là bằng chứng mọi API/controller của ứng dụng tự động kích hoạt validation; hãy kiểm tra entry point riêng.

## 9. Các ví dụ sai kiểu thường gặp và cách sửa

### A. Số nguyên nhưng dùng `@NotBlank`

Sai:

```java
@NotBlank
private Integer age;
```

Đúng, nếu tuổi bắt buộc từ 0 trở lên:

```java
@NotNull
@Min(0)
private Integer age;
```

Nếu yêu cầu tuổi phải lớn hơn 0, dùng `@Positive` thay vì `@Min(0)`.

### B. Collection nhưng dùng `@NotBlank`

Sai:

```java
@NotBlank
private List<String> members;
```

Đúng:

```java
@NotEmpty
private List<@NotBlank String> members;
```

`@NotEmpty` kiểm tra danh sách có ít nhất một phần tử, còn `@NotBlank` trên type argument kiểm tra **từng chuỗi**.

### C. Enum lưu vào cột SQL kiểu VARCHAR

Sai:

```java
@Pattern(regexp = "NEW|DONE")
@Enumerated(EnumType.STRING)
private Status status;
```

Dù JPA lưu enum thành chuỗi trong database, **kiểu Java tại field vẫn là `Status`**, nên `@Pattern` (chỉ nhận `CharSequence`) không phù hợp. Dùng:

```java
@NotNull
@Enumerated(EnumType.STRING)
private Status status;
```

và định nghĩa rõ các hằng của enum. Nếu cần giới hạn tập trạng thái theo nghiệp vụ, dùng custom constraint hỗ trợ `Status` hoặc kiểm tra tại business boundary. Các dòng JPA trên là **field minh họa**, cần import `jakarta.persistence.*` và một enum `Status` hợp lệ.

### D. Độ lớn số nhưng dùng `@Size`

Sai:

```java
@Size(max = 8)
private BigDecimal total;
```

Đúng khi giới hạn trị số:

```java
@DecimalMax("99999999.99")
@DecimalMin("0.00")
private BigDecimal total;
```

Nếu còn muốn tối đa 8 chữ số phần nguyên và 2 phần thập phân, bổ sung `@Digits(integer=8, fraction=2)`.

### E. Ngày được giữ dưới dạng `String` nhưng dùng `@Past`

Sai:

```java
@Past
private String birthday;
```

Đúng: parse sang `LocalDate` rồi validate `@Past`, hoặc nếu nghiệp vụ bắt buộc giữ chuỗi, dùng custom constraint trên `CharSequence` để parse/kiểm tra ngày theo hợp đồng rõ ràng. Đừng tự chuyển một chuỗi ngày thành số để áp dụng `@Min`.

## 10. Kiểm tra từng phần tử của collection và container element constraints

Jakarta Validation hỗ trợ constraint trên **type arguments** và cascade qua **value extractors**. Đây là điểm dễ nhầm giữa kiểu container và kiểu phần tử.

```java
@NotEmpty
private List<@NotBlank String> labels;

@Size(min = 1)
private Map<@NotBlank String, @Positive Integer> stockByCode;
```

Hai field minh họa trên có:

- Constraint **đặt trên `List`**: `@NotEmpty` yêu cầu ít nhất một phần tử.
- Constraint **đặt trên `String` bên trong `List`**: `@NotBlank` kiểm tra từng nhãn.
- Constraint **đặt trên `Map`**: `@Size(min=1)` kiểm tra số entry.
- Constraint **đặt trên key/value**: key phải là chuỗi không trắng; giá trị số lượng phải lớn hơn 0.

Nếu viết `List<@NotBlank Integer>`, annotation nằm tại kiểu phần tử **`Integer`** và vẫn sai kiểu; chuyển annotation từ field ra type argument không thể khiến một `Integer` biến thành `CharSequence`.

Với nested bean:

```java
@NotEmpty
private List<@Valid Address> addresses;
```

`@Valid` kích hoạt **cascade** sang các `Address` khi object cha được validate; nó không phải constraint kiểm tra “không rỗng”. `@NotEmpty` bảo đảm collection có phần tử; muốn chắc chắn từng phần tử không null có thể thêm `@NotNull` tại type argument. Cần chú ý provider/extractor cho custom container như một class wrapper riêng. Không phải mọi container tự viết đều được provider biết cách lấy phần tử: một `ValueExtractor` có thể cần thiết.

**Phân biệt lỗi:** container element có constraint với kiểu không phù hợp có thể gây `UnexpectedTypeException`, còn vấn đề thiếu/không xác định được `ValueExtractor` có thể gây một `ValidationException`/`ConstraintDeclarationException` khác tùy trường hợp. Đọc **loại exception thực sự**, đừng quy mọi vấn đề nested/container thành HV000030.

## 11. Các trường hợp `null`: đúng kiểu vẫn cần chọn ràng buộc phù hợp

Đa số constraint chỉ kiểm tra **nội dung/định dạng** coi `null` là hợp lệ; chúng không thay `@NotNull`.

| Constraint | `null` có hợp lệ? | Lưu ý |
| --- | --- | --- |
| `@NotNull` | Không | Bắt buộc hiện diện, không xét giá trị bên trong |
| `@Null` | Có | Yêu cầu phải null |
| `@NotBlank` | Không | Đồng thời từ chối chuỗi rỗng/toàn khoảng trắng |
| `@NotEmpty` | Không | Đồng thời từ chối chuỗi/collection/map/mảng rỗng |
| `@Size`, `@Pattern`, `@Email` | Có | Kết hợp `@NotNull`/`@NotBlank` nếu bắt buộc |
| `@Min`, `@Max`, `@Positive`, `@Digits` | Có | Giá trị null không được xét; cần `@NotNull` nếu là field bắt buộc |
| `@Past`, `@Future` và biến thể | Có | Dữ liệu không có ngày phải được xử lý riêng |
| `@AssertTrue`/`@AssertFalse` trên `Boolean` | Có | Giá trị null được coi hợp lệ theo chuẩn |

Ví dụ một email bắt buộc:

```java
@NotBlank
@Email
private String email;
```

`@Email` chịu trách nhiệm định dạng và `@NotBlank` yêu cầu có nội dung. Chính xác tiêu chí email “hợp lệ” được Jakarta Validation cho phép provider quyết định một phần; nếu hệ thống có hợp đồng riêng, cần tài liệu hóa và kiểm thử.

Cần hiểu **hai chiều độc lập**: “validator có hỗ trợ kiểu không?” và “giá trị có đạt quy tắc không?”. `null` hợp lệ chỉ là câu trả lời của chiều thứ hai sau khi constraint/type đã phù hợp.

## 12. Provider extension và tính portable của API

Jakarta Validation định nghĩa bộ constraint chuẩn ở `jakarta.validation.constraints`. Hibernate Validator còn cung cấp một số constraint trong namespace `org.hibernate.validator.constraints`, ví dụ `@Length`, `@Range`, `@URL`; đó là **tính năng riêng của provider**, có thể có tập kiểu và hành vi khác chuẩn.

Một provider cũng có thể bổ sung hỗ trợ ngoài bộ kiểu bắt buộc cho constraint chuẩn. Chẳng hạn một version của Hibernate Validator có thể cung cấp validator cho một số kiểu số/chuỗi ngoài bảng chuẩn. Điều này tạo hai yêu cầu khi thiết kế:

1. **Ứng dụng cần di động giữa provider:** chỉ dựa vào tập kiểu được đặc tả Jakarta Validation bảo đảm; ưu tiên annotation chuẩn và model phù hợp.
2. **Ứng dụng cố ý phụ thuộc Hibernate Validator:** kiểm tra đúng tài liệu version và viết integration test. Nêu rõ dependency; đừng diễn giải khả năng mở rộng đó thành một điều bảo đảm cho mọi Jakarta provider.

Tương tự, một dự án Spring Framework 6+ / Boot 3+ dùng namespace `jakarta.validation.*`; mã cũ Spring 5/Boot 2 thường dùng `javax.validation.*`. Nếu trộn annotation của hai thế hệ hoặc provider/API không tương thích, bạn có thể gặp các hành vi khác ngoài `UnexpectedTypeException`. Chẩn đoán dependency và imports trước khi đổi type/constraint.

## 13. Custom constraint: hỗ trợ kiểu cụ thể và nguy cơ trùng khớp mơ hồ

Giả sử có annotation `@ValidCode` và implementation:

```java
public final class ValidCodeValidator
        implements ConstraintValidator<ValidCode, CharSequence> {

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        return value == null || value.toString().startsWith("VN-");
    }
}
```

Đây là **đoạn class minh họa**, cần annotation `ValidCode` có `@Constraint(validatedBy=ValidCodeValidator.class)`, import `jakarta.validation.*` và lớp đặt trong source phù hợp. Khi áp dụng `@ValidCode` lên `String` thì phù hợp vì `String implements CharSequence`. Khi áp dụng lên `Integer` thì không có validator phù hợp và có thể ném `UnexpectedTypeException`.

Nếu phải hỗ trợ thêm kiểu thứ hai, định nghĩa **một `ConstraintValidator<ValidCode, Integer>` riêng** với ngữ nghĩa rõ ràng và liệt kê cả hai implementation trong `validatedBy`. Đừng cast tất cả về một kiểu trong một validator không được khai báo hỗ trợ; cũng đừng dùng `Object` như giải pháp chung nếu quy tắc nghiệp vụ cần phân biệt loại dữ liệu.

Một lỗi phức tạp hơn:

- Validator A nhận `CharSequence`.
- Validator B nhận `Serializable`.
- Field được khai báo kiểu `String`, vốn hiện thực **cả hai interface**.
- `CharSequence` và `Serializable` không kế thừa nhau, nên không có một validator “cụ thể hơn” duy nhất.

Như vậy provider có thể ném `UnexpectedTypeException` vì **nhiều validator cùng phù hợp nhưng mơ hồ**, dù không phải “thiếu validator”. Kiểm tra danh sách `validatedBy`, các kiểu generic và quan hệ kế thừa. Dùng các loại target được chọn cụ thể, không cố đăng ký nhiều overload có quan hệ không rõ.

Jakarta Validation yêu cầu triển khai `ConstraintValidator.isValid(...)` an toàn luồng; provider có thể cache instance. Một lỗi thread safety trong logic custom validator thường là vấn đề khác, không phải bản thân `UnexpectedTypeException`.

## 14. Khi lỗi xuất hiện trong Spring MVC

Trong Spring MVC, các annotation như `@Valid`, `@Validated` hoặc constraint đặt trực tiếp trên tham số method có thể yêu cầu chạy Bean Validation ở các entry point thích hợp.

Ví dụ DTO nhận request:

```java
public class CreateOrderRequest {
    @NotBlank
    private String itemCode;

    @NotNull
    @Positive
    private Integer quantity;

    @NotEmpty
    private List<@NotBlank String> itemTags;

    // Constructor/getter/setter hoặc record binding
    // được định nghĩa theo cách ứng dụng dùng.
}
```

Đoạn trên là **class minh họa**, cần import `java.util.List` và các annotation Jakarta. Controller:

```java
@PostMapping("/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return ResponseEntity.accepted().build();
}
```

Đây là **method minh họa** trong Spring MVC controller, cần các import framework và response policy phù hợp. Khi framework đã deserialise request thành object và kích hoạt validator:

- `quantity = 0` với `@Positive`: **giá trị sai**, sinh Bean Validation violation; thông thường MVC chuyển thành lỗi yêu cầu như HTTP 400 theo cấu hình exception handling.
- `quantity = 5` nhưng code khai báo `@NotBlank Integer quantity`: **metadata constraint sai kiểu**; provider ném `UnexpectedTypeException`, thường biểu hiện lỗi cấu hình phía server. Đây không phải “form input sai” mà có thể chữa bằng thay thông báo validation cho người dùng.
- JSON gửi `"quantity": "abc"` cho `Integer`: Jackson có thể thất bại ngay khi chuyển kiểu, trước cả Bean Validation; đó là lỗi deserialize/HTTP message conversion.
- Nếu thiếu `@Valid`/entry point hỗ trợ, constraint có thể chưa chạy; việc không thấy exception **không chứng minh** khai báo đúng kiểu.

Trong MVC hiện đại, validation object argument có thể phát sinh `MethodArgumentNotValidException`; nếu method-level validation được kích hoạt bởi constraint trực tiếp trên method parameter, Spring có thể dùng `HandlerMethodValidationException`. `UnexpectedTypeException` là ngoại lệ từ **provider resolve constraint**, cần được xử lý như lỗi kỹ thuật và sửa code. Không coi nó là một nhánh của `BindingResult.hasErrors()` thông thường.

## 15. Quy trình chẩn đoán HV000030/UnexpectedTypeException

Khi log xuất hiện thông báo tương tự `HV000030` hoặc tên class `UnexpectedTypeException`, làm tuần tự:

1. **Đọc chính xác annotation, kiểu và property path** trong thông báo. Ví dụ `NotBlank`, `Integer`, `quantity` là đủ để khoanh vùng.
2. **Mở khai báo Java**, không chỉ nhìn dữ liệu SQL hoặc JSON. Kiểu của field/getter/record component quyết định ứng viên validator. Với enum gắn `@Enumerated(EnumType.STRING)`, kiểu Java vẫn là enum.
3. **So với bảng supported types** trong Jakarta Validation spec hoặc Javadoc đúng provider/version. Phân biệt `@Size` với `@Min`, `@NotBlank` với `@NotEmpty`, `@Past` với kiểu String/epoch.
4. **Kiểm tra constraint nằm ở container hay element**: `@NotBlank List<String>` sai; `List<@NotBlank String>` đúng khi muốn kiểm tra từng chuỗi.
5. **Kiểm tra group và đường cascade** nếu lỗi chỉ xuất hiện ở một flow: nhóm được validate và `@Valid` trên object nested quyết định field có được kiểm tra hay không.
6. **Kiểm tra custom `@Constraint(validatedBy=...)`**: validator có generic target type đúng không, có hơn một ứng viên cùng cụ thể nhất không?
7. **Kiểm tra dependency/integration**: `jakarta` hay `javax`, version provider, service được Spring quản lý, XML mapping hay factory cấu hình có override validators không?
8. **Thêm một test gọi `validator.validate(bean)` trực tiếp** cho từng DTO/bộ group liên quan để lỗi được phát hiện sớm và tái hiện được, thay vì chờ request production.
9. **Sửa model hoặc constraint**, không bắt exception rồi bỏ qua. Nếu kiểu dữ liệu thực sự đặc biệt, viết custom constraint rõ hợp đồng và test đúng provider.

Trong Hibernate Validator, thông báo `HV000031` thường liên quan **nhiều validator cùng phù hợp**, còn `HV000030` thường liên quan **không có validator phù hợp**; mã chính xác là chi tiết triển khai, hãy dựa thêm vào Java exception class và stack trace.

## 16. Kiểm thử để tránh tái phát

### Test giá trị sai nhưng kiểu đúng

```java
var violations = validator.validate(
        new Order("   ", List.of(), 0,
                  "A", LocalDate.of(2000, 1, 1)));

assertEquals(5, violations.size());
```

Đây là **đoạn JUnit 5 minh họa**, dựa trên class `Order` trong ví dụ Java trước đó và biến `validator` được inject. Cần import `org.junit.jupiter.api.Assertions.assertEquals` hoặc static import phù hợp. Kiểm tra các property path cụ thể để tránh một thay đổi về message/locale làm test khó ổn định.

### Test kiểu sai phải lộ lỗi kỹ thuật

```java
assertThrows(UnexpectedTypeException.class,
        () -> validator.validate(new WrongType()));
```

Cần JUnit 5 và lớp `WrongType` đã nêu. Test này giúp minh họa nguyên nhân trong code học tập. **Đối với code production, hãy sửa khai báo `WrongType` để test thực tế khẳng định không có `UnexpectedTypeException` nữa**; không giữ một assertion mong đợi lỗi kỹ thuật lâu dài.

### Test tích hợp Spring

- Inject `jakarta.validation.Validator` từ Spring ApplicationContext để kiểm tra đúng provider được ứng dụng sử dụng.
- Với endpoint, dùng `MockMvc` và DTO hợp lệ/không hợp lệ để phân biệt lỗi binding, violation và lỗi cấu hình.
- Với service `@Validated`, kiểm tra qua Spring proxy nếu method validation được sử dụng.
- Với collection/nested model, kiểm tra ít nhất một phần tử sai và sự có mặt của `@Valid`/container element constraint.
- Với custom constraint, thử từng kiểu được hỗ trợ và một kiểu không hỗ trợ trong test chủ đích; chú ý hai validator có thể mơ hồ khi cùng interface.
- Với temporal constraint, kiểm tra cùng `ClockProvider`/timezone nếu case phụ thuộc thời điểm hiện tại.

Để phát hiện lỗi trước khi chạy traffic thật, có thể thêm integration test quét những DTO/entry point quan trọng và gọi validation trên dữ liệu mẫu. Không giả định việc mở ApplicationContext luôn kiểm tra mọi annotation: nhiều provider giải quyết validator **khi một loại constraint được dùng lần đầu**.

## 17. Bộ quy tắc lựa chọn nhanh

| Bạn cần kiểm tra | Loại Java thích hợp | Annotation nên cân nhắc |
| --- | --- | --- |
| Tên người dùng bắt buộc, không được chỉ có space | `String` | `@NotBlank` + `@Size` |
| Email có nội dung và hợp lệ về cấu trúc | `String` | `@NotBlank` + `@Email` |
| Danh sách có ít nhất một phần tử | `List<T>` | `@NotEmpty` |
| Danh sách tên và từng tên đều hợp lệ | `List<String>` | `@NotEmpty List<@NotBlank String>` |
| Số lượng hàng hóa nguyên dương | `Integer` | `@NotNull` + `@Positive` |
| Điểm số từ 0 đến 100 | `Integer` hoặc `BigDecimal` | `@Min(0)` + `@Max(100)` khi kiểu hỗ trợ |
| Giá tiền không âm, tối đa 2 chữ số lẻ | `BigDecimal` | `@DecimalMin("0.00")` + `@Digits` |
| Ngày giao hàng sau hiện tại | `LocalDate` | `@NotNull` + `@Future` |
| Đảm bảo trạng thái enum được cung cấp | `Status` | `@NotNull` |
| Chuỗi khớp biểu thức chính quy | `String`/`CharSequence` | `@Pattern` |
| Có thuộc tính con cần kiểm tra tiếp | JavaBean hoặc collection nested | `@Valid` + constraints trên các field liên quan |

**Tự hỏi trước khi code review:** “Kiểu khai báo tại điểm gắn annotation là gì? Jakarta Validation có validator cho cặp annotation/kiểu này không? Annotation kiểm tra null hay nội dung? Có entry point thực sự chạy validation không?”

## 18. Câu hỏi tự kiểm tra

**1. Vì sao `@NotBlank Integer age` biên dịch được mà runtime lại có thể lỗi?**  
Java cho phép annotation trên field, nhưng Bean Validation phải tìm `ConstraintValidator` có supported type phù hợp; `Integer` không phải `CharSequence`.

**2. `@Size(min=1) List<String> names` có kiểm tra `names.get(0)` không được rỗng không?**  
Không. Nó kiểm tra số phần tử list. Dùng `List<@NotBlank String>` để kiểm tra từng chuỗi, kết hợp `@NotEmpty` nếu danh sách phải có ít nhất một phần tử.

**3. `@Size(max=5) Integer code` có tương đương mã số tối đa 5 chữ số không?**  
Không. `@Size` không áp dụng cho `Integer` theo chuẩn. Thiết kế kiểu, range hoặc định dạng chuỗi mã số phù hợp.

**4. `@Min(1) Double price` có portable không?**  
Không theo tập supported types bắt buộc của `@Min` trong Jakarta Validation; một provider có thể mở rộng. Với số thập phân có độ chính xác nghiệp vụ, dùng `BigDecimal` và `@DecimalMin`.

**5. `@Positive Double percent` có portable không?**  
Có, `@Positive` được chuẩn chỉ rõ hỗ trợ `float`/`double`, nhưng cần hiểu chính xác biểu diễn số thực.

**6. Khi `validator.validate(bean)` trả 3 `ConstraintViolation`, có phải lỗi `UnexpectedTypeException` không?**  
Không. Provider đã chọn validator thích hợp và phát hiện các giá trị không đạt. `UnexpectedTypeException` là không giải quyết được validator.

**7. `@Pattern` trên enum có hoạt động vì JPA lưu enum dưới dạng text không?**  
Không. Bean Validation kiểm tra kiểu Java của field, không dựa vào cách JPA mã hóa xuống database.

**8. Vì sao cùng một DTO có thể chạy bình thường ở một provider nhưng lỗi ở provider khác?**  
Một provider có thể hỗ trợ thêm kiểu ngoài bộ chuẩn. Nếu cần di động, dùng đúng supported types của Jakarta Validation.

**9. Có thể sửa lỗi bằng `catch (UnexpectedTypeException)` rồi trả lỗi người dùng không?**  
Không nên xem đó là giải pháp. Đây thường là sai declaration/configuration cần sửa ở code và bắt bằng test.

**Ghi nhớ:** *Giá trị sai → constraint violation; khai báo constraint sai kiểu hoặc mơ hồ → UnexpectedTypeException*. Hãy lựa chọn **annotation theo kiểu Java** trước khi xác thực dữ liệu thực tế.

## Tài liệu tham khảo

- Jakarta Validation 3.1 specification — Built-in Constraint definitions: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#builtinconstraints
- Jakarta Validation 3.1 specification — ConstraintValidator resolution algorithm: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — UnexpectedTypeException: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/UnexpectedTypeException.html
- Jakarta Validation API — Built-in constraints package: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/package-summary.html
- Hibernate Validator — Reference Guide and documentation: https://hibernate.org/validator/documentation/
- Spring Framework Reference — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
