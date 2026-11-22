# @Positive, @PositiveOrZero, @Negative và @NegativeOrZero trong Bean Validation

## 1. Mục tiêu và tình huống ứng dụng

Trong các hệ thống Spring, một giá trị có kiểu `Integer`, `Long` hoặc `BigDecimal` vẫn có thể sai về ý nghĩa nghiệp vụ: số lượng đặt hàng phải lớn hơn 0, số sản phẩm tồn kho không thể âm, số tiền điều chỉnh giảm phải nhỏ hơn 0, hoặc khoản thay đổi số dư có thể âm hay bằng 0. Jakarta Bean Validation cung cấp bốn annotation chuẩn mô tả chính xác bốn miền giá trị đó.

Ví dụ:
- `quantity = 3`: hợp lệ nếu yêu cầu số lượng lớn hơn 0.
- `quantity = 0`: không hợp lệ với `@Positive` nhưng hợp lệ với `@PositiveOrZero`.
- `stock = -1`: không hợp lệ nếu số tồn phải lớn hơn hoặc bằng 0.
- `outflow = -50`: hợp lệ với `@Negative`, còn `outflow = 0` không hợp lệ với ràng buộc này.
- `balanceAdjustment = 0`: hợp lệ với `@NegativeOrZero`.

Sau bài học, cần phân biệt được chính xác dấu và ranh giới 0; biết các kiểu số được hỗ trợ, ý nghĩa của `null`, cách kết hợp `@NotNull` và các constraint khác; cách kích hoạt validation trong Spring MVC; và cách kiểm tra hành vi thực tế bằng ví dụ Java 17+, JUnit và MockMvc.

> Các ví dụ dùng `jakarta.validation.constraints.*` của Jakarta Bean Validation 3.x và Spring Framework 6+/Spring Boot 3.x. Với ứng dụng cũ dùng Bean Validation 2.x/Spring Boot 2.x, package thường là `javax.validation.constraints.*`; không trộn hai namespace trong cùng dependency graph.

## 2. So sánh bốn ràng buộc bằng bất đẳng thức

| Annotation | Miền giá trị được chấp nhận | Diễn giải | Giá trị 0 |
| --- | --- | --- | --- |
| `@Positive` | `x > 0` | Dương nghiêm ngặt | **Bị từ chối** |
| `@PositiveOrZero` | `x >= 0` | Không âm | **Hợp lệ** |
| `@Negative` | `x < 0` | Âm nghiêm ngặt | **Bị từ chối** |
| `@NegativeOrZero` | `x <= 0` | Không dương | **Hợp lệ** |

Bảng chân trị cho một số hữu hạn thông thường:

| Giá trị | `@Positive` | `@PositiveOrZero` | `@Negative` | `@NegativeOrZero` |
| --- | --- | --- | --- | --- |
| `-12` | Sai | Sai | Đúng | Đúng |
| `-0.01` | Sai | Sai | Đúng | Đúng |
| `0` | Sai | Đúng | Sai | Đúng |
| `0.0001` | Đúng | Đúng | Sai | Sai |
| `25` | Đúng | Đúng | Sai | Sai |

Các cặp dễ nhầm:
- **Positive khác PositiveOrZero chỉ ở ranh giới 0**. Không dùng `@Positive` cho trường hợp cho phép số 0.
- **Negative khác NegativeOrZero chỉ ở ranh giới 0**. Không dùng `@Negative` cho trường hợp 0 có nghĩa là không có biến động.
- `@PositiveOrZero` và `@NegativeOrZero` đều chấp nhận số 0. Kết hợp cả hai trên cùng giá trị thực chất chỉ chấp nhận 0, nhưng không phải cách rõ ràng nhất để mô tả ràng buộc bằng 0.
- `@Positive` và `@Negative` trên cùng một field là ràng buộc mâu thuẫn với mọi giá trị số hữu hạn. Không dùng sự kết hợp đó để thay cho một constraint nghiệp vụ.

Bốn annotation này là các **constraint chuẩn có từ Bean Validation 2.0**. Chúng kiểm tra dấu, không tự giới hạn độ lớn, đơn vị đo, số chữ số thập phân, tính liên quan giữa hai trường hay tính hợp lệ của giá trị trong một trạng thái nghiệp vụ.

## 3. Đặt annotation trên field, property hoặc record component

Một DTO đơn giản:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record InventoryPolicy(
        @NotNull @Positive Integer minimumOrderQuantity,
        @NotNull @PositiveOrZero BigDecimal availableQuantity,
        @NotNull @Negative BigDecimal mandatoryDecrease,
        @NotNull @NegativeOrZero BigDecimal permittedAdjustment) {
}
```

Đây là một fragment Java 17+: tệp hoàn chỉnh sẽ cần tên `InventoryPolicy.java` và nằm trong package phù hợp. Constraint trên các thành phần `record` được provider Bean Validation hỗ trợ qua metadata tương ứng; tương tự có thể đặt trên field/getter của Java bean.

Giải thích:
1. `minimumOrderQuantity` phải có giá trị và lớn hơn 0; một đơn hàng tối thiểu bằng 0 thường không có ý nghĩa.
2. `availableQuantity` phải có giá trị và không âm; kho có thể hết hàng, nên 0 vẫn hợp lệ.
3. `mandatoryDecrease` phải có giá trị và âm nghiêm ngặt, ví dụ `-3.5`; 0 không biểu thị một lần giảm thực sự.
4. `permittedAdjustment` có thể âm hoặc bằng 0, ví dụ áp dụng cho một loại điều chỉnh chỉ được trừ, nhưng không cộng.

`@NotNull` không bắt buộc cho cơ chế dấu nhưng quan trọng với hợp đồng đầu vào. Nếu không khai báo, cả bốn constraint đều xem `null` là hợp lệ theo Jakarta Bean Validation specification.

### 3.1. Null có hợp lệ không?

**Có, đối với cả bốn annotation**, và đây là đặc điểm dễ bị bỏ sót:

```java
import jakarta.validation.constraints.Positive;

class Product {
    @Positive
    Integer reorderLevel;
}
```

Nếu `reorderLevel == null`, không có lỗi `@Positive`. Muốn bắt buộc trường này vừa tồn tại vừa dương:

```java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

class Product {
    @NotNull
    @Positive
    Integer reorderLevel;
}
```

Hai constraint trả lời hai câu hỏi độc lập: `@NotNull` hỏi "có giá trị không?"; `@Positive` hỏi "nếu có giá trị thì có lớn hơn 0 không?". Việc cho phép null giúp dùng ràng buộc dấu trên những trường **tùy chọn**, nhưng không có nghĩa dữ liệu nghiệp vụ rỗng luôn được chấp nhận.

Một field kiểu primitive `int`/`long` không nhận `null`. Khi deserialize JSON vào primitive bị thiếu, giá trị có thể thành 0 theo cách tạo object/Jackson configuration, khiến lỗi không phân biệt được giữa "không gửi" và "gửi 0". Với dữ liệu request cần phân biệt hai trường hợp, nên dùng wrapper `Integer`/`Long` cùng `@NotNull` khi phù hợp.

### 3.2. Constraint không tự chạy khi tạo object

Khai báo:

```java
InventoryPolicy policy = new InventoryPolicy(
        0,
        new BigDecimal("-2"),
        BigDecimal.ZERO,
        new BigDecimal("1"));
```

chỉ tạo một object Java. Không có exception do `@Positive` hoặc `@Negative` tự phát sinh ngay tại lệnh `new`. Phải có một **điểm kích hoạt validation** như `jakarta.validation.Validator.validate(policy)`, `@Valid @RequestBody` trong Spring MVC hoặc method validation đã được cấu hình.

Tương tự, `@Positive` không biến số âm thành số dương và không clamp `-1` thành `0`. Nó chỉ mô tả điều kiện cần kiểm tra và có thể tạo `ConstraintViolation` khi điều kiện không thỏa.

## 4. Những kiểu dữ liệu được hỗ trợ theo Jakarta Bean Validation

Bốn constraint áp dụng cho **các kiểu số**; danh sách portable do specification quy định gồm:

- `BigDecimal` và `BigInteger`.
- Các primitive `byte`, `short`, `int`, `long`, `float`, `double`.
- Các wrapper tương ứng `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`.

Ví dụ hợp lệ về mặt vị trí annotation:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.NegativeOrZero;

class Measurements {
    @Positive long itemCount;
    @Positive BigInteger sequence;
    @Positive BigDecimal unitPrice;

    @NegativeOrZero int signedAdjustment;
    @NegativeOrZero Double correction;
}
```

**Không áp dụng cho `String` như một đảm bảo portable.** Hibernate Validator có thể hỗ trợ bổ sung một số kiểu như `CharSequence` hoặc `Number` khác tùy provider/version, nhưng specification không bắt buộc hỗ trợ các mở rộng ấy. Nếu request có `"quantity": "5"`, nên để bước conversion/deserialization chuyển về kiểu số phù hợp và kiểm tra constraint trên kiểu số, thay vì phụ thuộc vào một extension.

Nếu dùng annotation cho một kiểu không có validator tương thích, provider có thể báo `UnexpectedTypeException` khi bắt đầu validate. Đây là lỗi cấu hình/kiểu dữ liệu, **không phải** một vi phạm dấu thông thường của client.

### 4.1. Nên dùng BigDecimal hay float/double?

Đối với tiền tệ và những miền yêu cầu độ chính xác thập phân, `BigDecimal` thường phù hợp hơn `double` vì lưu số thập phân với độ chính xác mà ứng dụng kiểm soát. Ví dụ:

```java
new BigDecimal("0.01");  // giá trị thập phân xác định
new BigDecimal("-0.01"); // số âm xác định
```

Còn `float`/`double` là dấu phẩy động nhị phân; khi thực hiện phép toán có thể sinh sai lệch nhỏ quanh 0. Không lấy kết quả dấu từ một phép tính floating-point mà không xét sai số chấp nhận được của nghiệp vụ.

Các giá trị đặc biệt `Double.NaN`, `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` và signed zero như `-0.0d` có thể gây bất ngờ trong logic so sánh hoặc thực thi validator; không sử dụng bảng dấu của **số hữu hạn thông thường** để khẳng định mọi giá trị đặc biệt đều được xử lý giống nhau trên mọi provider. Nếu API cho phép `Float`/`Double`, hãy thiết kế riêng chính sách chấp nhận tính hữu hạn (ví dụ `Double.isFinite(...)`) và kiểm thử trên chính provider/version đang dùng.

Với `BigDecimal`, `new BigDecimal("-0.00").signum()` bằng 0; giá trị này có thể hiển thị khác `0.00` nhưng về mặt so sánh số học không phải một số âm nghiêm ngặt. Không dùng `equals` để so sánh số học của BigDecimal có scale khác nhau; `compareTo(BigDecimal.ZERO)` hoặc `signum()` thích hợp hơn cho kiểm tra dấu.

## 5. Phân biệt kiểm tra dấu với Min, DecimalMin và giới hạn độ lớn

`@Positive` tương đương ý tưởng "lớn hơn 0", nhưng không tương đương mọi ràng buộc có ngưỡng dương.

| Yêu cầu | Annotation phù hợp | Ghi chú |
| --- | --- | --- |
| Số nguyên ít nhất 1 | `@Min(1)` hoặc `@Positive` trên kiểu số nguyên | Hai lựa chọn cùng đạt ngưỡng với các số nguyên |
| Số thập phân lớn hơn 0 | `@Positive` hoặc `@DecimalMin(value = "0", inclusive = false)` | Cho phép `0.00001` |
| Tiền ít nhất 0.01 | `@DecimalMin("0.01")` | `@Positive` riêng lẻ **không** bảo đảm mức tối thiểu 0.01 |
| Số không âm | `@PositiveOrZero` hoặc `@DecimalMin("0")` | Bao gồm 0 |
| Số âm | `@Negative` hoặc `@DecimalMax(value = "0", inclusive = false)` | Không cho 0 |
| Giá trị âm hoặc 0 | `@NegativeOrZero` hoặc `@DecimalMax("0")` | Bao gồm 0 |
| Phần trăm giảm từ 0 đến 100 | `@PositiveOrZero` kết hợp `@Max(100)` hoặc constraint tương đương | Cần cả hai đầu mút |
| Số lượng tối đa trong kho | `@PositiveOrZero` + `@Max(...)` | Dấu không đủ biểu thị giới hạn |

Ví dụ:

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

class MoneyRequest {
    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 10, fraction = 2)
    BigDecimal unitPrice;

    @NotNull
    @Positive
    Integer quantity;
}
```

Ở đây:
- `@DecimalMin("0.01")` từ chối `0.001` dù đó là số dương; `@Positive` sẽ **không** từ chối giá trị này.
- `@Digits(integer = 10, fraction = 2)` đặt giới hạn chữ số theo định dạng số học. Nó không tự làm tròn giá trị không hợp lệ.
- `@Positive` trên quantity buộc số lượng lớn hơn 0, nhưng không đặt giới hạn trên.

`@Min`/`@Max` không có hợp đồng portable cho `float`/`double` theo Bean Validation specification (một số provider mở rộng); khi cần ngưỡng thập phân, ưu tiên `BigDecimal` và `@DecimalMin`/`@DecimalMax`.

## 6. Ví dụ Maven + Java 17 chạy độc lập ngoài Spring

Ví dụ này dùng Jakarta Validation API và Hibernate Validator 8 để tạo report ổn định cho cả bốn constraint. Vì đây là Bean Validation, chương trình **cần các dependency và provider**, không chạy chỉ bằng `javac` không có classpath.

Cấu trúc:

```text
sign-validation-demo/
├── pom.xml
└── src/main/java/example/SignValidationDemo.java
```

### 6.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sign-validation-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

`expressly` cung cấp Jakarta EL implementation cho thông điệp validation; Hibernate Validator là provider. Trong ứng dụng Spring Boot 3.x có BOM quản lý dependency, nên dùng `spring-boot-starter-validation` thay vì copy nguyên phiên bản được pin ở ví dụ này.

### 6.2. File src/main/java/example/SignValidationDemo.java

```java
package example;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public final class SignValidationDemo {

    public record Signs(
            @NotNull @Positive Integer requiredPositive,
            @PositiveOrZero BigDecimal nonNegative,
            @Negative BigDecimal strictlyNegative,
            @NegativeOrZero BigDecimal nonPositive) {
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Signs valid = new Signs(
                    5,
                    BigDecimal.ZERO,
                    new BigDecimal("-0.01"),
                    BigDecimal.ZERO);

            Signs invalid = new Signs(
                    0,
                    new BigDecimal("-0.01"),
                    BigDecimal.ZERO,
                    new BigDecimal("0.01"));

            Signs missing = new Signs(
                    null,
                    BigDecimal.ZERO,
                    new BigDecimal("-1"),
                    BigDecimal.ZERO);

            System.out.println("validViolations="
                    + validator.validate(valid).size());

            Set<ConstraintViolation<Signs>> invalids =
                    validator.validate(invalid);

            System.out.println("invalidViolations="
                    + invalids.size());

            String invalidFields = invalids.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .sorted()
                    .collect(Collectors.joining(","));

            System.out.println("invalidFields=" + invalidFields);

            Set<ConstraintViolation<Signs>> missingErrors =
                    validator.validate(missing);

            System.out.println("missingViolations="
                    + missingErrors.size());
            System.out.println("missingField="
                    + missingErrors.iterator().next()
                            .getPropertyPath().toString());
        }
    }
}
```

Lệnh chạy ở thư mục `sign-validation-demo` với Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SignValidationDemo
```

Stdout **của các lệnh println trong chương trình** (Maven/provider có thể hiển thị log riêng):

```text
validViolations=0
invalidViolations=4
invalidFields=nonNegative,nonPositive,requiredPositive,strictlyNegative
missingViolations=1
missingField=requiredPositive
```

Vì sao có bốn lỗi? `requiredPositive = 0` vi phạm `@Positive`; `nonNegative = -0.01` vi phạm `@PositiveOrZero`; `strictlyNegative = 0` vi phạm `@Negative`; `nonPositive = 0.01` vi phạm `@NegativeOrZero`.

Vì sao `missingViolations=1`? Giá trị `requiredPositive = null` hợp lệ đối với riêng `@Positive`, nhưng vi phạm `@NotNull`. Các trường còn lại hợp lệ. Đoạn code sắp xếp tên field khi in để không phụ thuộc thứ tự duyệt `Set<ConstraintViolation>`, vốn không nên coi là ổn định.

## 7. Unit test biên 0 và giá trị thập phân

Chỉ test số dương lớn không chứng minh được ranh giới giữa bốn constraint. Ta cần ít nhất số âm, 0 và số dương, thêm `null` và số thập phân sát 0.

Ví dụ JUnit Jupiter sau nằm trong dự án có Hibernate Validator 8/JUnit 5. Tạo file `src/test/java/example/SignConstraintsTest.java` và bảo đảm test classpath có JUnit Jupiter (chẳng hạn `spring-boot-starter-test` trong dự án Boot).

```java
package example;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SignConstraintsTest {

    record FourSigns(
            @Positive BigDecimal positive,
            @PositiveOrZero BigDecimal positiveOrZero,
            @Negative BigDecimal negative,
            @NegativeOrZero BigDecimal negativeOrZero) {
    }

    private static Set<String> badFields(
            Validator validator, BigDecimal value) {

        return validator.validate(new FourSigns(
                        value, value, value, value))
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void verifiesZeroAndBothSides() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(
                    Set.of("positive", "positiveOrZero"),
                    badFields(validator, new BigDecimal("-0.01")));

            assertEquals(
                    Set.of("positive", "negative"),
                    badFields(validator, BigDecimal.ZERO));

            assertEquals(
                    Set.of("negative", "negativeOrZero"),
                    badFields(validator, new BigDecimal("0.01")));
        }
    }

    @Test
    void nullIsValidForAllFourConstraints() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(0,
                    validator.validate(
                            new FourSigns(null, null, null, null)).size());
        }
    }
}
```

Test cho số 0 cho thấy `@Positive` và `@Negative` thất bại; hai constraint có hậu tố `OrZero` chấp nhận. Test null khẳng định cả bốn đều mặc định bỏ qua null.

Muốn test cấp độ tích hợp trong ứng dụng Boot, nên bổ sung test `@Valid @RequestBody` với input 0, âm, dương, null, dấu nhỏ (ví dụ 0.0001) và giá trị sai kiểu. Test Bean Validation qua `Validator` chứng minh constraint, còn test HTTP chứng minh Spring đã **thực sự kích hoạt** nó.

## 8. Spring MVC: validation chỉ hoạt động sau bước chuyển kiểu

Một JSON request có thể chứa các trường số. Jackson đọc JSON thành DTO trước, sau đó Spring MVC có thể gọi Bean Validation provider khi tham số method dùng `@Valid` hoặc `@Validated` đúng ngữ cảnh.

Ví dụ Spring Boot 3.x có dependency:

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

Đây là **fragment dependency** trong một dự án Boot có sẵn BOM/parent và application entrypoint, không phải file Maven độc lập. DTO và controller có thể nằm trong package `com.example.pricing`.

**File `src/main/java/com/example/pricing/PricePreviewRequest.java`:**

```java
package com.example.pricing;

import java.math.BigDecimal;

import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record PricePreviewRequest(
        @NotNull @Positive Integer quantity,
        @NotNull @Positive BigDecimal unitPrice,
        @NotNull @PositiveOrZero BigDecimal discount,
        @NotNull @NegativeOrZero BigDecimal adjustment) {
}
```

**File `src/main/java/com/example/pricing/PriceController.java`:**

```java
package com.example.pricing;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {

    @PostMapping("/prices/preview")
    public ResponseEntity<Void> preview(
            @Valid @RequestBody PricePreviewRequest request) {
        // Chỉ minh họa validation; không thực hiện phép tính giá.
        return ResponseEntity.noContent().build();
    }
}
```

Request hợp lệ:

```http
POST /prices/preview
Content-Type: application/json

{
  "quantity": 2,
  "unitPrice": 19.99,
  "discount": 0,
  "adjustment": -1.25
}
```

Khi Bean Validation provider đã được cấu hình, controller trả **HTTP 204 No Content** theo code ở trên.

Request sai:

```http
POST /prices/preview
Content-Type: application/json

{
  "quantity": 0,
  "unitPrice": 19.99,
  "discount": -0.01,
  "adjustment": 0.10
}
```

Bước deserialize tạo được DTO; bước Bean Validation phát hiện ba trường: `quantity` vi phạm `@Positive`; `discount` vi phạm `@PositiveOrZero`; `adjustment` vi phạm `@NegativeOrZero`. Với `@Valid @RequestBody` trong Spring MVC chuẩn, tình huống này thông thường được trả về **HTTP 400 Bad Request**, controller không chạy tới phần body.

**Không suy ra cấu trúc JSON lỗi mặc định.** Nó phụ thuộc vào Spring Boot version, cấu hình Problem Details, exception handler và `MessageSource`. Lớp exception thường thấy ở dạng validation đối tượng `@RequestBody` là `MethodArgumentNotValidException`. Nếu method có constraint đặt trực tiếp trên tham số/giá trị trả về và cần method validation (Spring MVC 6.1+), ngoại lệ có thể là `HandlerMethodValidationException`.

### 8.1. MockMvc test cho ba trường sai

**File `src/test/java/com/example/pricing/PriceControllerTest.java`:**

```java
package com.example.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PriceController.class)
class PriceControllerTest {

    @Autowired MockMvc mvc;

    @Test
    void acceptsValidSigns() throws Exception {
        mvc.perform(post("/prices/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "quantity": 2,
                          "unitPrice": 19.99,
                          "discount": 0,
                          "adjustment": -1.25
                        }
                        """))
                .andExpect(status().isNoContent());
    }

    @Test
    void rejectsWrongSigns() throws Exception {
        mvc.perform(post("/prices/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "quantity": 0,
                          "unitPrice": 19.99,
                          "discount": -0.01,
                          "adjustment": 0.10
                        }
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(result.getResolvedException()
                            instanceof MethodArgumentNotValidException);
                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();

                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("quantity"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("discount"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("adjustment"));
                });
    }
}
```

`@WebMvcTest` cần dependency test của Boot (thường `spring-boot-starter-test`), và Bean Validation provider phải hiện diện trong test runtime. Test kiểm tra field errors thay vì phụ thuộc nội dung message được locale hóa.

### 8.2. Validation cho @RequestParam khác gì?

Với constraint trực tiếp trên tham số method:

```java
import jakarta.validation.constraints.Positive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/stock")
public String stock(@RequestParam @Positive Integer count) {
    return "count=" + count;
}
```

Đây chỉ là **fragment trong controller**, và `@Positive` nằm **trực tiếp trên method parameter**. Spring MVC 6.1+ có built-in method validation cho loại constraint này, với lỗi có thể đi qua `HandlerMethodValidationException`. Trong ứng dụng cũ hơn, hoặc service layer, cần kiểm tra cơ chế method validation/AOP đã cấu hình. Không coi `@Valid` đơn độc trên một `Integer` là thay thế cho `@Positive`.

Nếu request gửi `count=abc` thì Spring không chuyển `String` thành `Integer` được; đây là lỗi **type conversion/binding**, khác với việc đã có số 0 nhưng không thỏa constraint dấu. Trong test thực tế nên phân biệt rõ hai nhóm lỗi này.

## 9. Dùng với collection và object lồng nhau

Các constraint về dấu có thể đặt ngay trên **type argument** của collection, ví dụ:

```java
import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record BatchOrderRequest(
        @NotEmpty List<@NotNull @Positive Integer> quantities,
        @NotNull @Valid WarehousePolicy policy) {
}

public record WarehousePolicy(
        @PositiveOrZero BigDecimal availableStock) {
}
```

Các `record` ở trên thuộc **hai file Java tách biệt** nếu đều để modifier `public`; hoặc đặt dạng package-private trong một file thực hành phù hợp. Đây là fragment minh họa Bean Validation, không phải ứng dụng có thể chạy chỉ bằng đoạn code này.

Giải thích:
- `@NotEmpty` đòi hỏi danh sách `quantities` có phần tử; nó không tự kiểm tra dấu từng phần tử.
- `List<@NotNull @Positive Integer>` yêu cầu mọi phần tử không null và lớn hơn 0. Phần tử `0` hoặc `-2` bị lỗi.
- `@NotNull @Valid WarehousePolicy policy` yêu cầu có đối tượng policy và **cascade** vào `availableStock` để chạy `@PositiveOrZero`.
- Nếu bỏ `@Valid` ở `policy`, việc validate root chỉ thấy `@NotNull` của policy; constraint bên trong policy có thể không được kiểm tra theo đường này.
- Nếu `availableStock == null`, `@PositiveOrZero` một mình cho phép null; thêm `@NotNull` nếu stock luôn phải được xác định.

Khi cần xử lý response có field path như `quantities[0]` hoặc `policy.availableStock`, kiểm tra với provider thực tế. Đừng phụ thuộc thứ tự của danh sách `ConstraintViolation` khi tạo response.

## 10. Khi nào cần @Valid, @Validated và validation groups?

`@Positive`/`@Negative` là **constraint annotations**. `@Valid` là annotation để kích hoạt cascade ở object graph và thường kích hoạt validation DTO tại điểm vào Spring MVC. `@Validated` là annotation của Spring hỗ trợ chọn validation groups và có vai trò trong method validation.

Ví dụ controller:

```java
@PostMapping("/prices/preview")
public ResponseEntity<Void> preview(
        @Valid @RequestBody PricePreviewRequest request) {
    return ResponseEntity.noContent().build();
}
```

`@Valid` trên request có nhiệm vụ yêu cầu validate DTO ở điểm vào. Các dấu `@Positive`/`@PositiveOrZero`... nằm trên record component mới thực sự biểu diễn điều kiện số.

Khi cần áp dụng những nhóm ràng buộc khác nhau theo ngữ cảnh tạo mới/cập nhật, có thể đặt `groups = ...` trên constraint và chọn nhóm tại điểm validate. Không lạm dụng groups nếu hợp đồng dấu giống nhau ở mọi thao tác.

Ví dụ cấu hình nhóm (fragment):

```java
import jakarta.validation.constraints.Positive;
import org.springframework.validation.annotation.Validated;

interface CreateGroup {}

class Draft {
    @Positive(groups = CreateGroup.class)
    Integer requestedQuantity;
}

void handle(@Validated(CreateGroup.class) Draft request) {
    // Dùng trong điểm tích hợp Spring phù hợp;
    // đây chỉ là chữ ký minh họa, không phải endpoint hoàn chỉnh.
}
```

Chú ý `@Positive(groups = CreateGroup.class)` chỉ chạy khi provider validate nhóm `CreateGroup` (hoặc nhóm kế thừa/chuyển nhóm phù hợp); một lời gọi chỉ validate nhóm `Default` không mặc nhiên kích hoạt constraint khai báo riêng cho `CreateGroup`.

Với service bean, method validation thường cần cấu hình hỗ trợ và gọi qua Spring proxy. Tạo đối tượng bằng `new` hoặc self-invocation có thể đi vòng qua proxy. Spring MVC 6.1+ có cơ chế method validation built-in cho controller; không suy ra service bean cũng hoạt động giống handler method.

## 11. Những trường hợp đặc biệt cần test

### 11.1. Số 0, số âm rất nhỏ và số dương rất nhỏ

Nếu policy là `@Positive` thì mọi giá trị **lớn hơn 0** đều thỏa bất đẳng thức, kể cả `0.000001`. Nếu doanh nghiệp yêu cầu tối thiểu 0.01, `@Positive` là **chưa đủ**.

Với `BigDecimal`, test các giá trị:
- `new BigDecimal("-0.0001")`: âm.
- `BigDecimal.ZERO`: bằng 0.
- `new BigDecimal("0.0001")`: dương.
- `new BigDecimal("0.00")`: bằng 0 về mặt số học, dù scale khác.
- `new BigDecimal("-0.00")`: `signum() == 0`, không phải âm nghiêm ngặt.

### 11.2. Dữ liệu số âm nhưng được biểu diễn thành chuỗi

JSON `"amount": -1` và `"amount": "-1"` không có cùng type. Jackson có thể coercion hoặc từ chối chuỗi số tùy cấu hình. Bean Validation chỉ đánh giá giá trị sau khi đã deserialize. Không dùng sự thành công của một request kiểu chuỗi để khẳng định mọi client có thể gửi số dưới dạng string.

### 11.3. Null và trường bị thiếu

Với wrapper `Integer`/`BigDecimal`, thiếu trường có thể cho giá trị null. Bốn constraint dấu không tự báo thiếu; thêm `@NotNull` nếu đó là lỗi. Đừng dựa vào `@Positive` để thay thế kiểm tra sự hiện diện.

### 11.4. Số vượt kiểu dữ liệu

JSON gửi số nguyên vượt `Integer.MAX_VALUE` có thể gây lỗi deserialize trước validation. `@Positive` không sửa overflow và không phải ràng buộc giới hạn kiểu. Nếu miền giá trị có thể lớn, chọn kiểu lớn hơn như `Long`/`BigInteger` và đặt ngưỡng trên thực sự cần thiết.

### 11.5. Giá trị tính toán khác giá trị request

Constraint trên input không bảo đảm mọi kết quả tính toán đều hợp lệ. Ví dụ `@Positive price` và `@Positive quantity` vẫn có thể cho kết quả tiền vượt ngưỡng, hoặc discount lớn hơn tổng giá nếu thiếu ràng buộc liên trường. Xác minh ở tầng nghiệp vụ và đặt các invariant bổ sung.

### 11.6. Primitive, wrapper và ký hiệu âm của zero

`int` không thể null; `Integer` có thể null. Với floating-point, `-0.0` có bit dấu âm nhưng so sánh toán học bằng 0 theo `==`. Các thuật toán/provider có thể biểu diễn hoặc phân loại giá trị này khác cách con người đọc chuỗi `"-0.0"`. Nếu dữ liệu liên quan tiền, ưu tiên `BigDecimal` và policy rõ về số 0; kiểm tra NaN/Infinity nếu hệ thống có đường nhận floating-point.

### 11.7. Cần số nguyên không âm, không phải số thực không âm

`@PositiveOrZero BigDecimal` chấp nhận `0.5`; nếu yêu cầu số đếm, hãy chọn kiểu `Integer`/`Long` hoặc kết hợp thêm ràng buộc phù hợp. Dấu không quyết định tính nguyên.

## 12. Ma trận kiểm thử đề xuất

| Ca | Input | Mong đợi |
| --- | --- | --- |
| Positive âm | `-1` | Sai |
| Positive 0 | `0` | Sai |
| Positive dương | `1` | Đúng |
| PositiveOrZero âm | `-0.01` | Sai |
| PositiveOrZero 0 | `0` | Đúng |
| PositiveOrZero dương | `0.01` | Đúng |
| Negative âm | `-1` | Đúng |
| Negative 0 | `0` | Sai |
| Negative dương | `1` | Sai |
| NegativeOrZero âm | `-1` | Đúng |
| NegativeOrZero 0 | `0` | Đúng |
| NegativeOrZero dương | `1` | Sai |
| Bốn constraint và null | `null` | Đều hợp lệ khi đứng một mình |
| `@NotNull @Positive` với null | `null` | Sai vì NotNull |
| Decimal rất nhỏ | `0.000001` | Positive chấp nhận, không bảo đảm min tiền |
| BigDecimal scale khác | `0.00` và `-0.00` | Zero về mặt số học |
| Kiểu không được hỗ trợ | Gắn constraint số vào object không phải số | Lỗi cấu hình/type validator, không phải dấu sai |
| JSON sai kiểu | `"quantity":"abc"` | Lỗi deserialize/binding trước constraint |
| DTO có field sai | JSON hợp lệ, `quantity=0` | HTTP 400 khi `@Valid` và provider hoạt động |
| Collection | `quantities=[1,0,2]` với List<@Positive Integer> | Lỗi phần tử bằng 0 |
| Bean con | Field bên trong policy bằng `-2` | Cần đường `@Valid` từ root |
| Không có provider | Chỉ có annotations, không có Bean Validation runtime | Không thể khẳng định đã thực thi validation |

Một bộ test tốt nên kiểm tra cả **cấp provider** (số lượng, property path) và **cấp HTTP** (status/field error), đồng thời giữ assertion độc lập thông điệp có thể được dịch theo locale.

## 13. Lỗi thường gặp và cách khắc phục

1. **Chọn `@Positive` nhưng muốn chấp nhận 0:** đổi sang `@PositiveOrZero`.
2. **Chọn `@Negative` nhưng yêu cầu "không tăng":** nếu 0 hợp lệ, dùng `@NegativeOrZero`.
3. **Bỏ `@NotNull` trên giá trị bắt buộc:** bốn constraint dấu xem null là hợp lệ, cần ràng buộc riêng.
4. **Đặt constraint trên `String` theo giả định portable:** specification yêu cầu các kiểu số cụ thể; phụ thuộc extension của provider có thể làm hệ thống khó chuyển đổi.
5. **Dùng `@Positive` cho giá tối thiểu 0.01:** dùng `@DecimalMin("0.01")` và quy tắc số chữ số nếu cần.
6. **Dùng `double` cho tiền và dựa vào sai số dấu:** ưu tiên `BigDecimal`; xử lý đặc biệt các giá trị không hữu hạn nếu tồn tại.
7. **Cho rằng annotation chạy khi `new DTO(...)`:** cần Validator hoặc integration của Spring thực sự gọi nó.
8. **Quên `@Valid` trên tham số `@RequestBody`:** trong MVC thông thường constraint của DTO không tự chạy tại entrypoint nếu thiếu cơ chế kích hoạt phù hợp.
9. **Quên cascade `@Valid` cho object con:** các constraint sâu trong object graph không được duyệt từ root.
10. **Nhầm lỗi conversion với constraint violation:** dữ liệu `"abc"` cho `Integer` có thể thất bại ngay khi bind.
11. **Nhầm method validation với object validation:** trực tiếp `@Positive` trên `@RequestParam` có cơ chế exception khác `@Valid @RequestBody` trong Spring MVC.
12. **Chỉ test một số dương:** không phát hiện được khác biệt `Positive`/`PositiveOrZero` hoặc `Negative`/`NegativeOrZero` ở ranh giới 0.
13. **Quên giới hạn trên hoặc quan hệ giữa nhiều trường:** một số dương có thể vẫn vô nghĩa trong bối cảnh nghiệp vụ.
14. **Khẳng định thứ tự violation ổn định:** `Set<ConstraintViolation>` không yêu cầu thứ tự; nên sort khi cần hiển thị/debug ổn định.

## 14. Checklist triển khai thực tế

1. Viết yêu cầu dưới dạng bất đẳng thức: `>0`, `>=0`, `<0`, `<=0`; xác định rõ 0 có ý nghĩa gì.
2. Chọn kiểu số thích hợp, ưu tiên `BigDecimal` cho tiền; không dùng String để biểu diễn số nếu không cần.
3. Nếu không cho phép thiếu trường, thêm `@NotNull` (và dùng wrapper khi cần phân biệt missing/null).
4. Nếu cần ngưỡng ngoài 0, kết hợp `@DecimalMin`/`@DecimalMax`/`@Min`/`@Max` hoặc custom constraint theo nghiệp vụ.
5. Bảo đảm Bean Validation provider được cài và validation được gọi ở đúng điểm vào; đối với Spring MVC request DTO, thường dùng `@Valid @RequestBody`.
6. Với danh sách và object con, đặt constraint trên type argument và `@Valid` trên đường cần cascade.
7. Test ít nhất giá trị âm, 0, dương, null; bổ sung thập phân rất nhỏ, giới hạn kiểu, JSON sai kiểu, overflow và liên trường khi cần.
8. Khi xử lý phản hồi, phân biệt binding error, Bean Validation constraint violation và lỗi cấu hình provider; không công bố nội bộ stack trace cho client.

### Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 Specification — các constraint @Positive/@PositiveOrZero/@Negative/@NegativeOrZero](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Validation — @Positive API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/positive).
- [Jakarta Validation — @PositiveOrZero API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/positiveorzero).
- [Jakarta Validation — @Negative API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/negative).
- [Jakarta Validation — @NegativeOrZero API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/negativeorzero).
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody kết hợp @Valid](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
