# `@Min`, `@Max`, `@DecimalMin` và `@DecimalMax` trong Bean Validation

## 1. Mục tiêu và bối cảnh

Bốn annotation này thuộc nhóm **ràng buộc chuẩn (built-in constraints)** của Jakarta Bean Validation, dùng để kiểm tra một **giá trị số có nằm trong giới hạn tối thiểu hoặc tối đa hay không**. Chúng thường xuất hiện trong model Spring MVC, DTO, form nhập liệu và dữ liệu nghiệp vụ:

- Số lượng sản phẩm phải ít nhất 1: `@Min(1)`.
- Số lượt thử lại không quá 5: `@Max(5)`.
- Đơn giá phải **lớn hơn** `0.00` (loại trừ mốc 0): `@DecimalMin(value = "0.00", inclusive = false)`.
- Tỷ lệ chiết khấu phải **nhỏ hơn** `1.00` (loại trừ 100%): `@DecimalMax(value = "1.00", inclusive = false)`.

Vấn đề cần học không chỉ là nhớ tên annotation: phải chọn đúng **kiểu ngưỡng** (`long` hoặc chuỗi số thập phân), hiểu **biên có được tính hay không**, xử lý `null`, sử dụng kiểu số phù hợp và biết Spring gọi Bean Validation ở giai đoạn nào sau khi bind dữ liệu.

Sau bài này, bạn có thể:
1. Phân biệt đầy đủ bốn annotation theo toán tử so sánh, kiểu `value`, `inclusive` và kiểu Java được hỗ trợ.
2. Viết ràng buộc khoảng `[min, max]`, `(min, max)`, `[min, max)` hoặc `(min, max]` và kiểm tra đúng điểm biên.
3. Kết hợp `@NotNull`, `@Digits`, conversion và validation khi cần, thay vì kỳ vọng một annotation làm mọi việc.
4. Chạy một chương trình Java 17+ dùng Jakarta Validation với Hibernate Validator và đối chiếu `ConstraintViolation` với `FieldError` của Spring.
5. Tránh lỗi độ chính xác số thực, sai kiểu dữ liệu, nhầm `javax.validation` và `jakarta.validation`, hoặc hiểu nhầm `BindingResult` trong Spring.

## 2. So sánh trực tiếp bốn annotation

| Annotation | Điều kiện mặc định | Kiểu thuộc tính `value` | Có `inclusive`? | Ví dụ |
| --- | --- | --- | --- | --- |
| `@Min` | `x >= value` | `long` | Không; luôn bao gồm mốc | `@Min(1)` |
| `@Max` | `x <= value` | `long` | Không; luôn bao gồm mốc | `@Max(100)` |
| `@DecimalMin` | `x >= value` | `String` theo dạng số của `BigDecimal` | Có; mặc định `true` | `@DecimalMin("0.01")` |
| `@DecimalMax` | `x <= value` | `String` theo dạng số của `BigDecimal` | Có; mặc định `true` | `@DecimalMax("999.99")` |

Tất cả đều nằm trong package `jakarta.validation.constraints` khi ứng dụng dùng Jakarta Validation (phổ biến với Spring Framework 6+). Đây là **ràng buộc so sánh giá trị**, không phải annotation dành riêng cho `int`, cũng không phải bộ chuyển chuỗi sang số.

### 2.1. `@Min`: giá trị không nhỏ hơn ngưỡng

```java
@Min(value = 1, message = "Số lượng phải từ {value} trở lên")
private Integer quantity;
```

- `quantity = 1` → **hợp lệ**.
- `quantity = 0` → **vi phạm**.
- `quantity = 100` → hợp lệ đối với riêng `@Min`.
- `quantity = null` → **hợp lệ đối với riêng `@Min`**; cần `@NotNull` nếu bắt buộc nhập.

`@Min(1)` là viết tắt của `@Min(value = 1)`. Thuộc tính `value` có kiểu `long`, nên có thể biểu diễn cả ngưỡng âm và các ngưỡng trong giới hạn của `long`, nhưng **không thể viết** `@Min(0.1)` để đặt ngưỡng thập phân.

### 2.2. `@Max`: giá trị không vượt quá ngưỡng

```java
@Max(value = 100, message = "Giá trị không được vượt quá {value}")
private Long count;
```

- `count = 100L` → hợp lệ.
- `count = 101L` → vi phạm.
- `count = -1L` → hợp lệ đối với riêng `@Max`; nếu không chấp nhận số âm, cần thêm ràng buộc tối thiểu.
- `count = null` → hợp lệ đối với riêng `@Max`.

`@Max(100)` **không** có biến thể `inclusive = false`; muốn biểu diễn `< 100` một cách trực tiếp, có thể dùng `@DecimalMax(value = "100", inclusive = false)` trên kiểu được hỗ trợ.

### 2.3. `@DecimalMin`: ngưỡng thập phân và biên mở

```java
@DecimalMin(value = "0.00", inclusive = false)
private BigDecimal price;
```

- `price = 0.00` → vi phạm vì cần `x > 0.00`.
- `price = 0.01` → hợp lệ.
- `price = -0.01` → vi phạm.
- `price = null` → hợp lệ với riêng `@DecimalMin`.

Nếu bỏ `inclusive = false`, mặc định là `true`, điều kiện trở thành `x >= 0.00`. Khác với `@Min`, `value` của `@DecimalMin` là một **chuỗi biểu diễn số**, ví dụ `"0.10"`, `"1.2345"`, `"-0.005"` hoặc `"100000000000000000000"`.

Cú pháp bên trong dấu nháy phải theo dạng mà `BigDecimal` hiểu; trong annotation viết `"0.01"` với dấu chấm thập phân, **không phải** `"0,01"` theo locale người dùng.

### 2.4. `@DecimalMax`: ngưỡng thập phân và biên mở

```java
@DecimalMax(value = "1.00", inclusive = false)
private BigDecimal discountRate;
```

- `discountRate = 0.99` → hợp lệ.
- `discountRate = 1.00` → vi phạm vì cần `x < 1.00`.
- `discountRate = 1.01` → vi phạm.
- `discountRate = null` → hợp lệ với riêng `@DecimalMax`.

Nếu bỏ `inclusive`, mốc tối đa được bao gồm (`x <= value`). `@DecimalMax` có cùng cách biểu diễn ngưỡng kiểu `String` như `@DecimalMin`.

## 3. Biên đóng và biên mở: chọn đúng annotation

Với `BigDecimal amount`, các khoảng được mô tả như sau:

| Khoảng mong muốn | Annotation |
| --- | --- |
| `[0, 100]` | `@DecimalMin("0")` và `@DecimalMax("100")` |
| `(0, 100)` | `@DecimalMin(value = "0", inclusive = false)` và `@DecimalMax(value = "100", inclusive = false)` |
| `[0, 100)` | `@DecimalMin("0")` và `@DecimalMax(value = "100", inclusive = false)` |
| `(0, 100]` | `@DecimalMin(value = "0", inclusive = false)` và `@DecimalMax("100")` |
| `1 <= x <= 10` với ngưỡng nguyên | `@Min(1)` và `@Max(10)` |

Một field có thể gắn đồng thời ràng buộc tối thiểu và tối đa:

```java
@DecimalMin(value = "0.00", inclusive = false)
@DecimalMax(value = "1.00", inclusive = true)
private BigDecimal share;
```

Với ví dụ này, `0.00` không hợp lệ, `0.01` hợp lệ, `1.00` hợp lệ, `1.01` không hợp lệ. Các constraint là điều kiện **đồng thời**: dữ liệu chỉ hợp lệ nếu tất cả constraint áp dụng đều thỏa.

**Đừng suy diễn biên dựa vào cách hiển thị.** Ví dụ một form hiển thị `1.00` không có nghĩa giá trị được làm tròn từ `0.999`; validator kiểm tra **giá trị Java hiện có sau chuyển đổi**, trừ khi ứng dụng chủ động áp dụng bước chuẩn hóa/làm tròn trước đó.

### 3.1. Hai điểm biên bắt buộc phải test

Nếu yêu cầu `price > 0.10`:

```text
0.09  -> sai
0.10  -> sai vì inclusive=false
0.11  -> đúng
```

Nếu yêu cầu `stock <= 20`:

```text
19 -> đúng
20 -> đúng vì @Max có biên đóng
21 -> sai
```

Cần test **ngay tại mốc**, **nhỏ hơn mốc** và **lớn hơn mốc**. Test một giá trị ở quá xa giới hạn có thể bỏ sót việc đặt nhầm `inclusive`.

## 4. Những kiểu dữ liệu được Jakarta Validation bảo đảm hỗ trợ

Theo Jakarta Bean Validation 3.0, tập kiểu chuẩn được bảo đảm như sau:

| Kiểu giá trị cần validate | `@Min`/`@Max` | `@DecimalMin`/`@DecimalMax` | Ghi chú |
| --- | --- | --- | --- |
| `byte`, `short`, `int`, `long` và wrapper | Có | Có | Nếu dùng wrapper, `null` hợp lệ với riêng constraint này |
| `BigInteger` | Có | Có | Hữu ích cho số nguyên lớn hơn `long` |
| `BigDecimal` | Có | Có | So sánh theo **giá trị số**, không theo chuỗi/scale |
| `CharSequence` (`String`, ...) | **Không được chuẩn bảo đảm** | Có | Giá trị chuỗi phải biểu diễn được số hợp lệ theo provider |
| `float`, `double` và wrapper | **Không được chuẩn bảo đảm** | **Không được chuẩn bảo đảm** | Sai số nhị phân; provider có thể hỗ trợ mở rộng xấp xỉ |
| `Boolean`, `LocalDate`, `Duration`, object bất kỳ | Không | Không | Dùng constraint thích hợp với kiểu đó |

**Lưu ý quan trọng:** Hibernate Validator có thể hỗ trợ **thêm** một số kiểu (ví dụ `@Min` trên chuỗi số hoặc một số subclass `Number`). Đó là phần mở rộng của provider, **không phải hợp đồng di động của Jakarta Validation**. Nếu cần thay provider hoặc yêu cầu portability, dựa vào tập kiểu chuẩn trong bảng.

`@Min(2)` trên `BigDecimal("1.99")` vẫn thất bại; `@Min` không làm tròn số rồi so sánh với `2`. Chỉ có **ngưỡng** là `long`. Nếu cần ranh giới `1.99`, phải dùng `@DecimalMin("1.99")`.

### 4.1. Vì sao nên dùng `BigDecimal` cho tiền và tỷ lệ chính xác?

Số `double`/`float` không biểu diễn chính xác nhiều phân số thập phân trong hệ nhị phân. Với giới hạn như `0.1`, `1.005` hoặc `9999.99`, dùng `BigDecimal` tránh việc độ chính xác phụ thuộc biểu diễn dấu chấm động. Tạo từ chuỗi:

```java
BigDecimal price = new BigDecimal("0.10");
```

Tránh tạo trực tiếp từ `double`:

```java
BigDecimal imprecise = new BigDecimal(0.1);
```

Dòng thứ hai có thể mang sai số của literal `double`. Nếu đã có `double` và bắt buộc chuyển, `BigDecimal.valueOf(...)` thường phù hợp hơn constructor nhận `double`, nhưng với input tiền tệ nên parse trực tiếp thành `BigDecimal`.

`BigDecimal("1.0")` và `BigDecimal("1.00")` có **cùng giá trị số** (`compareTo() == 0`) nhưng `equals()` khác vì scale. Các constraint ranh giới kiểm tra quan hệ số học; chúng **không bảo đảm** số chữ số sau dấu thập phân, rounding mode hoặc biểu diễn canonical. Để giới hạn số chữ số, dùng thêm `@Digits(integer = ..., fraction = ...)` và quy tắc nghiệp vụ phù hợp.

### 4.2. Khi validate `String` bằng `@DecimalMin`

`@DecimalMin("1.5")` có hỗ trợ `CharSequence` theo chuẩn, nhưng phải rõ đó là **chuỗi biểu diễn một số**. Nó không phải bộ parser theo locale hoặc cơ chế chuẩn hóa input cho mọi form:

```java
@DecimalMin("1.5")
private String numericText;
```

Nếu người dùng gửi `"1,5"` theo locale sử dụng dấu phẩy, đừng mặc định Jakarta Validation sẽ hiểu đó là 1,5. Trong Spring MVC, thường phù hợp hơn khi bind field kiểu `BigDecimal` bằng converter/formatter theo locale, rồi chạy `@DecimalMin` **trên giá trị đã chuyển đổi**.

Với chuỗi không biểu diễn được số như `"hello"`, không dùng kết quả Bean Validation như một bộ xử lý chuẩn hóa hoàn chỉnh. Quy tắc parse/format, text error và cơ chế validation phải được xác định riêng, nhất là khi có `@ModelAttribute` hoặc JSON API.

## 5. `null`, khoảng trắng, kiểu nguyên thủy và nhóm lỗi

Bốn constraint ranh giới đều coi `null` là **hợp lệ**. Điều này có chủ đích: ràng buộc số chỉ chịu trách nhiệm so sánh **khi có giá trị**. Nếu người dùng bắt buộc phải điền:

```java
@NotNull(message = "Giá trị bắt buộc")
@DecimalMin("0.00")
private BigDecimal amount;
```

- `null` → vi phạm `@NotNull`, nhưng không vi phạm `@DecimalMin`.
- `BigDecimal.ZERO` → hợp lệ đối với `@DecimalMin("0.00")` vì mặc định `inclusive = true`.
- `new BigDecimal("-0.01")` → vi phạm `@DecimalMin`.
- `""` và `"   "` **không phải** là `null` ở mọi đường binding; ứng dụng phải xác định conversion/trim/blank policy.

Đối với `int`/`long` nguyên thủy, giá trị Java không thể là null. Nếu form không gửi field, giá trị có thể giữ **0 mặc định** trên object mới; `@Min(1)` sẽ bắt lỗi số 0, nhưng đây không phải bằng chứng người dùng đã nhập số 0. Nếu cần phân biệt *không nhập* và *nhập 0*, dùng `Integer`/`Long` và `@NotNull`.

Ngược lại, chuỗi `"abc"` gửi lên field `Integer` có thể gây lỗi conversion `typeMismatch` trong Spring **trước** khi validator nhận một giá trị Integer hợp lệ. Vì vậy cần xử lý cả lỗi binding và lỗi Bean Validation.

### 5.1. Ràng buộc khoảng có thể kết hợp

```java
@NotNull
@Min(1)
@Max(50)
private Integer retryCount;
```

Đây là yêu cầu **giá trị bắt buộc trong `[1, 50]`**. Nếu muốn trường không bắt buộc nhưng, khi có, phải trong khoảng đó, bỏ `@NotNull`.

Thêm `@Positive`/`@PositiveOrZero` là lựa chọn khác khi chỉ cần tính dương/không âm. `@DecimalMin(value="0", inclusive=false)` diễn đạt `x > 0`, nhưng với mục đích đọc code, `@Positive` có thể rõ ý hơn. Chọn một hợp đồng nhất quán, tránh ràng buộc lặp không cần thiết.

## 6. Chương trình Java 17+ đầy đủ: kiểm tra bốn constraint và Spring adapter

Ví dụ dùng **Jakarta Validation 3.0 / Hibernate Validator 8.0.2.Final** và **Spring Framework 6.2.14**, không cần Spring Boot hoặc web server. Chương trình tạo các giá trị **ngay tại hoặc vượt biên** để thấy:
- `@Min(2)` và `@Max(20)` luôn bao gồm mốc.
- `@DecimalMin("0.10", inclusive = false)` và `@DecimalMax("100.00", inclusive = false)` loại trừ mốc.
- `@NotNull` kết hợp `@DecimalMin` để bắt missing value.
- Jakarta `ConstraintViolation` có property path, invalid value, tên constraint và message.
- `SpringValidatorAdapter` chuyển cùng các vi phạm thành `FieldError` trong một `BindingResult`.

### 6.1. Maven POM

Tạo file `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>numeric-bounds-validation</artifactId>
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

### 6.2. Mã Java độc lập

Tạo file `src/main/java/example/NumericBoundsDemo.java`:

```java
package example;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.validation.DirectFieldBindingResult;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class NumericBoundsDemo {

    public static final class Limits {
        @Min(value = 2, message = "quantity must be >= {value}")
        Integer quantity = 1;

        @Max(value = 20, message = "stock must be <= {value}")
        Integer stock = 21;

        @DecimalMin(
                value = "0.10", inclusive = false,
                message = "price must be > {value}")
        BigDecimal price = new BigDecimal("0.10");

        @DecimalMax(
                value = "100.00", inclusive = false,
                message = "discount must be < {value}")
        BigDecimal discount = new BigDecimal("100.00");

        @NotNull(message = "tax is required")
        @DecimalMin(
                value = "0.00", message = "tax must be >= {value}")
        BigDecimal tax = null;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            Limits invalid = new Limits();

            List<ConstraintViolation<Limits>> violations =
                    new ArrayList<>(validator.validate(invalid));

            // Tập kết quả không bảo đảm thứ tự.
            violations.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(violations.size() == 5,
                    "Expected 5 constraint violations");

            for (ConstraintViolation<Limits> violation : violations) {
                String annotation = violation.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName();
                System.out.println(
                        violation.getPropertyPath()
                        + " | value=" + violation.getInvalidValue()
                        + " | annotation=" + annotation
                        + " | template=" + violation.getMessageTemplate()
                        + " | message=" + violation.getMessage());
            }
            System.out.println("violationCount=" + violations.size());

            // Đối chiếu cùng Validator với BindingResult của Spring.
            DirectFieldBindingResult result =
                    new DirectFieldBindingResult(invalid, "limits");
            new SpringValidatorAdapter(validator).validate(invalid, result);
            require(result.getFieldErrorCount() == 5,
                    "Expected 5 Spring field errors");
            System.out.println(
                    "springFieldErrors=" + result.getFieldErrorCount());

            // Giá trị biên đóng được chấp nhận; biên mở cần vượt mốc.
            Limits valid = new Limits();
            valid.quantity = 2;
            valid.stock = 20;
            valid.price = new BigDecimal("0.11");
            valid.discount = new BigDecimal("99.99");
            valid.tax = new BigDecimal("0.00");

            require(validator.validate(valid).isEmpty(),
                    "Expected valid numeric boundaries");
            System.out.println("validBoundaries=true");

            // Bốn constraint số cho phép null, @NotNull không cho phép.
            Limits missing = new Limits();
            missing.quantity = null;
            missing.stock = null;
            missing.price = null;
            missing.discount = null;
            missing.tax = null;

            Set<ConstraintViolation<Limits>> missingErrors =
                    validator.validate(missing);
            require(missingErrors.size() == 1,
                    "Expected only tax's @NotNull violation");
            require(missingErrors.iterator().next()
                            .getPropertyPath().toString().equals("tax"),
                    "Expected tax field violation");
            System.out.println("nullOnlyErrors=" + missingErrors.size());

            System.out.println("CHECKS: PASS");
        }
    }
}
```

**Vì sao ví dụ dùng `DirectFieldBindingResult`?** Model ví dụ cố ý khai báo các trường và khởi tạo trực tiếp, không viết getter/setter; `DirectFieldBindingResult` đọc field trực tiếp. Với bean MVC thông thường có JavaBean getters/setters, `BeanPropertyBindingResult` hoặc binder của Spring MVC là cách phổ biến hơn.

### 6.3. Cách chạy và kết quả kỳ vọng

Chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.NumericBoundsDemo
```

Phần stdout do chương trình in ra sau khi bỏ qua log phụ của thư viện, nếu có:

```text
discount | value=100.00 | annotation=DecimalMax | template=discount must be < {value} | message=discount must be < 100.00
price | value=0.10 | annotation=DecimalMin | template=price must be > {value} | message=price must be > 0.10
quantity | value=1 | annotation=Min | template=quantity must be >= {value} | message=quantity must be >= 2
stock | value=21 | annotation=Max | template=stock must be <= {value} | message=stock must be <= 20
tax | value=null | annotation=NotNull | template=tax is required | message=tax is required
violationCount=5
springFieldErrors=5
validBoundaries=true
nullOnlyErrors=1
CHECKS: PASS
```

Cách hiểu:
1. `quantity = 1` sai vì `< 2`; `stock = 21` sai vì `> 20`.
2. `price = 0.10` và `discount = 100.00` nằm **ngay tại biên** nhưng vẫn sai vì `inclusive = false`.
3. `tax = null` chỉ vi phạm `@NotNull`; `@DecimalMin("0.00")` không tự bắt null.
4. `getMessageTemplate()` giữ `{value}`, còn `getMessage()` nội suy thành `2`, `20`, `0.10` và `100.00`.
5. `SpringValidatorAdapter` biến năm violation thành năm lỗi field trong `BindingResult`.
6. Object `valid` chứa các điểm biên đóng hợp lệ, còn giá trị ở các biên mở được đặt **vượt qua mốc**.
7. Object `missing` xác nhận đúng **một** lỗi required; bốn constraint số còn lại chấp nhận null.

Kết quả được sắp xếp theo property path để dễ so; Jakarta Validation trả `Set<ConstraintViolation<?>>` nên **không bảo đảm thứ tự** nếu không sắp xếp.

### 6.4. Điều gì xảy ra khi dùng giá trị lớn?

Vì tham số `value` của `@Min/@Max` là `long`, không thể viết `@Min` với ngưỡng lớn hơn `Long.MAX_VALUE`. Dù field là `BigInteger`, `@Min` vẫn bị giới hạn **đối với ngưỡng khai báo**. `@DecimalMin(value = "100000000000000000000")` biểu diễn ngưỡng lớn bằng chuỗi, phù hợp khi field là `BigInteger` hoặc `BigDecimal` và provider hỗ trợ theo Jakarta Validation.

## 7. Tích hợp Spring MVC và thứ tự data binding

Trong Spring MVC, quy trình điển hình:

```text
HTTP form / query parameter
         |
         v
Chuyển chuỗi -> Integer, Long, BigDecimal (ConversionService/Formatter)
         |
         v
Bean có dữ liệu đã bind
         |
         v
@Valid / @Validated gọi Jakarta Bean Validation
         |
         v
BindingResult chứa lỗi conversion hoặc constraint
```

Model ví dụ (đoạn minh họa, có getter/setter theo JavaBean để Spring bind):

```java
public class ProductForm {
    @NotNull
    @Min(1)
    @Max(100)
    private Integer quantity;

    @NotNull
    @DecimalMin(value = "0.00", inclusive = false)
    @DecimalMax("999999.99")
    private BigDecimal unitPrice;

    // Getters/setters của quantity và unitPrice.
}
```

Các import dùng `jakarta.validation.constraints.*` và `java.math.BigDecimal`. Đây là trích đoạn model, không phải một chương trình chạy độc lập.

Controller có thể nhận form (đoạn minh họa, cần Spring Web MVC):

```java
@PostMapping("/products")
String submit(@Valid @ModelAttribute("product") ProductForm product,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "products/form";
    }
    return "products/success";
}
```

Các import chính: `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `org.springframework.web.bind.annotation.ModelAttribute` và `org.springframework.validation.BindingResult`.

`BindingResult` phải nằm **ngay sau** argument `@ModelAttribute` cần xử lý lỗi. Khi có Bean Validation provider trên classpath và MVC được cấu hình phù hợp, `@Valid` kích hoạt validation cho object đã bind. Với `DataBinder` thủ công, cần đặt validator (`setValidator`/`addValidators`) rồi gọi `binder.validate()`; chỉ `bind(...)` không tự đảm bảo đã chạy Bean Validation.

### 7.1. Phân biệt lỗi type mismatch và vi phạm constraint

Input `"abc"` gửi vào `quantity: Integer` không phải số. Spring có thể tạo `FieldError` với code dạng `typeMismatch`, vì không thể chuyển chuỗi thành Integer. Trong trường hợp này **chưa có giá trị Integer để so với `@Min(1)`**.

Input `"0"` được chuyển thành `Integer 0`, sau đó không đạt `@Min(1)`, nên có lỗi constraint với code dựa trên `Min`. Để báo lỗi hợp lý, tách:
- **Lỗi cú pháp/chuyển đổi:** “Hãy nhập một số nguyên hợp lệ”.
- **Lỗi ranh giới:** “Số lượng phải từ 1 trở lên”.

Đối với `BigDecimal` nhập `"1,50"` theo locale Việt Nam, thành công hay thất bại phụ thuộc formatter/conversion được cấu hình. Annotation `@DecimalMin("1.00")` so sánh giá trị sau binding; bản thân annotation **không** quyết định cách parse dấu phẩy và dấu chấm.

### 7.2. `@RequestBody` JSON có đường đi khác

Nếu controller nhận `@Valid @RequestBody ProductForm`, JSON được deserialize bởi HTTP message converter (thường là Jackson) trước khi validation, với quy tắc JSON và cấu hình riêng. Một trường JSON numeric `1.50` và chuỗi JSON `"1,50"` không tương đương. Formatter cho form không nhất thiết được dùng cho JSON; test riêng parser, exception handler và validation của API JSON.

## 8. Đọc `ConstraintViolation` và thông báo lỗi

Mỗi vi phạm Jakarta Validation cung cấp:

```java
violation.getPropertyPath();
violation.getInvalidValue();
violation.getMessage();
violation.getMessageTemplate();
violation.getConstraintDescriptor();
```

Với annotation:

```java
@DecimalMin(
    value = "0.10",
    inclusive = false,
    message = "Giá phải lớn hơn {value}"
)
private BigDecimal price;
```

Khi `price = new BigDecimal("0.10")`, `getMessageTemplate()` giữ `"Giá phải lớn hơn {value}"`, còn `getMessage()` được nội suy thành `"Giá phải lớn hơn 0.10"`. Nếu dùng mẫu mặc định, provider có thể tra message trong bundle (thường là thông báo tiếng Anh mặc định, hoặc bản dịch đã cấu hình).

`getPropertyPath()` là đường dẫn có cấu trúc; với form lồng nhau có thể là `product.price`. `getInvalidValue()` trả object đã validate, trong ví dụ là `BigDecimal`. Không trả giá trị này nguyên dạng qua API hoặc log nếu dữ liệu có thể nhạy cảm.

Các thuộc tính `value`, `message`, `groups` và `payload` là thuộc tính phổ biến của constraint. `inclusive` **chỉ có trên** hai annotation decimal trong nhóm đang học. Có thể đặt message cụ thể hoặc resource bundle key (`"{product.price.min}"`) để quốc tế hóa.

Trong Spring, `FieldError.getField()`, `getRejectedValue()` và `getDefaultMessage()` giúp hiển thị lỗi; error codes/arguments hỗ trợ `MessageSource`. Chúng không ánh xạ 1:1 với mọi thuộc tính `ConstraintViolation`: `FieldError` còn chứa lỗi conversion, và `getCodes()` không phải `getMessageTemplate()`.

## 9. Ma trận kiểm thử ranh giới

| Bài test | Giá trị | Annotation | Kỳ vọng |
| --- | --- | --- | --- |
| Ngay tại min | `1` | `@Min(1)` | Pass |
| Dưới min | `0` | `@Min(1)` | Vi phạm |
| Ngay tại max | `5` | `@Max(5)` | Pass |
| Trên max | `6` | `@Max(5)` | Vi phạm |
| Decimal min đóng | `0.10` | `@DecimalMin("0.10")` | Pass |
| Decimal min mở | `0.10` | `@DecimalMin(value="0.10", inclusive=false)` | Vi phạm |
| Decimal min mở | `0.11` | Như trên | Pass |
| Decimal max đóng | `99.99` | `@DecimalMax("99.99")` | Pass |
| Decimal max mở | `99.99` | `@DecimalMax(value="99.99", inclusive=false)` | Vi phạm |
| Decimal max mở | `99.98` | Như trên | Pass |
| So sánh khác scale | `1.00` so với ngưỡng `"1.0"` | Decimal min/max inclusive | Dựa trên giá trị số; scale khác không làm thay đổi kết quả |
| Ngưỡng nguyên trên decimal | `1.99` | `@Min(2)` | Vi phạm; không làm tròn |
| Null với range | `null` | `@Min(1)`, `@DecimalMax("10")` | Pass đối với riêng hai constraint |
| Null bắt buộc | `null` | `@NotNull @Min(1)` | Vi phạm `@NotNull` |
| Kiểu float/double | `double` với `@DecimalMin` | Theo Jakarta Validation portable | Không được chuẩn bảo đảm; tránh giả định |
| Chuỗi sai kiểu | `"abc"` → `Integer` | `@Min(1)` trên target | Conversion error trước validation |
| Số thập phân sai định dạng locale | `"1,20"` → `BigDecimal` | `@DecimalMin("1.00")` | Phụ thuộc formatter/parser, sau đó mới so sánh |
| Giá trị âm | `-1` | `@Max(10)` | Pass đối với riêng `@Max` |
| Giá trị quá lớn | `BigInteger` lớn hơn `long` | `@DecimalMin` với chuỗi lớn | So sánh được theo giá trị khi provider/kiểu đúng |
| Kiểu không hỗ trợ | `LocalDate` với `@Min` | Sai loại constraint | Có thể gây `UnexpectedTypeException` khi validate |

Với test tự động, có thể assert theo loại annotation và property path:

```java
boolean hasMinViolation = validator.validate(form).stream()
    .anyMatch(v ->
        v.getPropertyPath().toString().equals("quantity")
        && v.getConstraintDescriptor().getAnnotation()
                .annotationType() == Min.class);
```

Đây là **đoạn Java minh họa** bên trong test có sẵn `validator`, `form` và import `jakarta.validation.constraints.Min`. Không dựa vào thứ tự Set hay nguyên văn message đã dịch để xác định một violation.

### 9.1. Test `inclusive = false` theo giá trị đúng

Với ngưỡng `"0.10"` và `inclusive=false`, nếu chỉ test giá trị `0.00` (fail) và `1.00` (pass) thì bạn chưa chứng minh điều kiện thật là `>` thay vì `>=`. Phải thêm đúng giá trị biên `"0.10"` và kiểm tra **fail**.

Tương tự, với `@DecimalMax(value="100.00", inclusive=false)`, giá trị `100.00` phải fail. Đây là nơi lỗi cấu hình dễ lọt qua nếu test chỉ bao gồm giá trị ngoài khoảng.

## 10. Lỗi thường gặp và cách khắc phục

**1. Dùng `@Min(0.01)` hoặc `@Max(99.99)`.** `value` của hai annotation này là `long`, không nhận literal phân số. Dùng `@DecimalMin("0.01")` hoặc `@DecimalMax("99.99")`.

**2. Tưởng `@DecimalMin("0.00")` có nghĩa là `x > 0`.** Mặc định `inclusive=true`: `0.00` vẫn hợp lệ. Nếu yêu cầu dương nghiêm ngặt, dùng `inclusive=false` hoặc `@Positive` theo contract.

**3. Quên `@NotNull`.** Cả bốn annotation cho phép `null`; để bắt buộc nhập phải thêm `@NotNull`. Với primitive không null, phân biệt missing input và giá trị mặc định zero khi thiết kế form.

**4. Dùng `double` cho tiền rồi kỳ vọng validation chính xác.** Jakarta spec không bảo đảm hỗ trợ các annotation này trên float/double; thậm chí provider có extension vẫn có vấn đề rounding. Ưu tiên `BigDecimal` với ngưỡng chuỗi.

**5. Dùng `@Min/@Max` trên String và coi là portable.** Chuẩn chỉ bảo đảm `CharSequence` cho hai annotation decimal. Hibernate Validator có một số mở rộng, nhưng đổi provider có thể gây `UnexpectedTypeException`.

**6. Cho rằng `@DecimalMin` kiểm tra số chữ số lẻ.** Nó chỉ so sánh ngưỡng. Nếu cần tối đa 2 chữ số thập phân, xem `@Digits(integer=..., fraction=2)` hoặc logic domain.

**7. Nhầm `@Max` với số phần tử trong collection hoặc độ dài chuỗi.** `@Max` kiểm tra giá trị số, không kiểm tra kích thước. Với `List`, `String`, `Map`, thường dùng `@Size(max = ...)` để giới hạn kích thước/độ dài.

**8. Lỗi nhập chuỗi số không hiển thị đúng.** `@Min` không sửa `typeMismatch`; cần cấu hình formatter, binding, `BindingResult` và thông báo lỗi conversion tách biệt.

**9. Trộn `javax.validation.constraints` với `jakarta.validation.constraints`.** Spring Framework 6+ đi cùng Jakarta Validation (`jakarta.*`). Spring Framework 5.x thường đi với `javax.validation.*`. Không trộn API/provider thuộc hai namespace trên cùng đường validation.

**10. Giả định tất cả violations chỉ có một lỗi.** Nếu đặt nhiều constraint trên một field, cùng một input có thể vi phạm nhiều điều kiện khác nhau; kết quả là Set không có thứ tự. Hãy chọn error ưu tiên trong UI một cách có chủ đích, không dựa vào thứ tự iteration.

**11. Gắn annotation vào kiểu không được hỗ trợ.** Jakarta Validation có thể ném `UnexpectedTypeException`, đây là lỗi cấu hình/constraint mapping, không phải “dữ liệu người dùng sai ngưỡng”. Kiểm tra kiểu Java trước khi triển khai.

**12. Chỉ validate ở frontend.** HTML `min`, `max`, JS input validation hữu ích cho trải nghiệm nhưng có thể bị bỏ qua khi gửi HTTP trực tiếp. Server cần validation theo contract API/domain, và vẫn phải kiểm soát tính đúng đắn khi ghi dữ liệu.

## 11. Quy trình áp dụng cho một field mới

1. **Xác định miền số:** kiểu `Integer`, `Long`, `BigInteger`, `BigDecimal` hoặc chuỗi số; tránh float/double khi yêu cầu ranh giới thập phân chính xác.
2. **Xác định hai biên:** ngưỡng tối thiểu/tối đa và từng biên đóng hay mở; đừng chọn annotation trước khi làm rõ yêu cầu.
3. **Chọn constraint:** `@Min/@Max` cho ngưỡng nguyên có biên đóng; `@DecimalMin/@DecimalMax` khi có ngưỡng phân số, biên mở hoặc giới hạn vượt `long`.
4. **Giải quyết nullable:** nếu bắt buộc giá trị, thêm `@NotNull`, và bảo đảm binder có thể phân biệt missing với số 0 khi cần.
5. **Xác định conversion:** input form/JSON theo locale và kiểu số đã định; tách lỗi chuyển đổi khỏi lỗi giới hạn.
6. **Thiết lập server validation:** `@Valid`/`@Validated` trên đúng đường request hoặc gọi `Validator`/`DataBinder.validate()` bằng tay.
7. **Viết test biên:** đúng mốc, sát dưới/trên mốc, null, số âm, overflow, scale, input sai và typed-error.
8. **Kiểm tra thông báo:** `getMessage()` đã nội suy, message code/locale đúng; không lộ raw value nhạy cảm.
9. **Giữ domain rule nhất quán:** cùng khoảng hợp lệ phải được áp dụng khi xử lý nghiệp vụ, import dữ liệu, API và các đường ghi khác.

## Tài liệu tham khảo

- Jakarta Bean Validation 3.0 — đặc tả các built-in constraints: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 — `@Min`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Min.html
- Jakarta Validation 3.0 — `@Max`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Max.html
- Jakarta Validation 3.0 — `@DecimalMin`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/DecimalMin.html
- Jakarta Validation 3.0 — `@DecimalMax`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/DecimalMax.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `DirectFieldBindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DirectFieldBindingResult.html
- Hibernate Validator 8.0 — Reference Guide: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
