
# `@Digits`: giới hạn số chữ số phần nguyên và phần thập phân trong Bean Validation

## 1. Bài toán và ý nghĩa của `@Digits`

Giả sử hệ thống có trường `amount` cho số tiền với quy ước **tối đa 4 chữ số phần nguyên** và **tối đa 2 chữ số phần thập phân**. Các giá trị `1234.56`, `0.5`, `-12.34` có thể hợp lệ về số chữ số, trong khi `12345.67` có quá nhiều chữ số phần nguyên và `12.345` có quá nhiều chữ số thập phân.

Jakarta Bean Validation cung cấp constraint chuẩn:

```java
import jakarta.validation.constraints.Digits;

@Digits(integer = 4, fraction = 2)
private BigDecimal amount;
```

Nó yêu cầu giá trị là một số có **không quá** `integer` chữ số ở phần nguyên và **không quá** `fraction` chữ số ở phần thập phân. Cả hai thuộc tính đều bắt buộc khi khai báo annotation và phải là giá trị không âm. Constraint này có trong `jakarta.validation.constraints.Digits`; Spring Framework 6+/Spring Boot 3+ sử dụng namespace `jakarta.validation.*`.

Điểm cần phân biệt ngay từ đầu:

- `@Digits(integer = 4, fraction = 2)` xác định **giới hạn chữ số**, không yêu cầu giá trị phải có đúng 4 chữ số phần nguyên hoặc đúng 2 chữ số thập phân.
- Nó **không tự làm tròn**, không cắt bớt phần thập phân, không chuyển chuỗi thành số và không bắt buộc giá trị dương.
- Giá trị `null` được coi là **hợp lệ với riêng `@Digits`**. Muốn bắt buộc nhập, kết hợp `@NotNull`.
- Nó không giới hạn miền giá trị nghiệp vụ một cách độc lập. Muốn “không âm”, “từ 0 đến 500” hoặc “phải lớn hơn 0”, kết hợp `@PositiveOrZero`, `@DecimalMin`, `@DecimalMax` hoặc rule tương ứng.

`@Digits` đặc biệt hữu ích cho giá, tỷ lệ, trọng lượng, số lượng có phần lẻ và các giá trị thập phân được lưu vào cột dữ liệu có precision/scale xác định.

## 2. Hiểu chính xác `integer` và `fraction`

### 2.1. Hai số đếm là mức tối đa

```java
@Digits(integer = 4, fraction = 2)
BigDecimal amount;
```

Mẫu trên chấp nhận tối đa 4 chữ số phần nguyên và 2 chữ số sau dấu thập phân. Bảng minh họa dùng kiểu `BigDecimal` được tạo từ chuỗi với đúng biểu diễn đã ghi:

| Giá trị đầu vào | Chữ số phần nguyên | Chữ số thập phân | Kết quả |
| --- | ---: | ---: | --- |
| `1234.56` | 4 | 2 | Hợp lệ |
| `1234` | 4 | 0 | Hợp lệ |
| `0.5` | Không vượt giới hạn | 1 | Hợp lệ |
| `-9999.99` | 4 | 2 | Hợp lệ: dấu âm không tính là chữ số |
| `12345.67` | 5 | 2 | **Không hợp lệ**: quá `integer` |
| `12.345` | 2 | 3 | **Không hợp lệ**: quá `fraction` |
| `10000.00` | 5 | 2 | **Không hợp lệ**: quá `integer` |
| `1.230` | 1 | 3 | **Không hợp lệ**: `BigDecimal` có `scale = 3` |
| `1.23` | 1 | 2 | Hợp lệ |
| `null` | Không áp dụng | Không áp dụng | Hợp lệ với riêng `@Digits` |

Bảng dùng dấu chấm theo cú pháp thập phân trong Java; dấu phân tách hàng nghìn không xuất hiện. Với giá trị `0.x`, cách provider tính số chữ số phần nguyên có thể dùng `BigDecimal.precision() - scale()` và cho kết quả không dương ở một số biểu diễn rất nhỏ. Quy tắc quan trọng đối với `integer = 4` là **không vượt quá 4 chữ số phần nguyên**; đừng nhầm số ký tự hiển thị với thuật toán của provider.

### 2.2. Khác với “đúng hai chữ số sau dấu thập phân”

`@Digits(integer = 4, fraction = 2)` vẫn chấp nhận `5`, `5.1`, `5.12`. Nó **không bắt buộc** `5` phải được viết thành `5.00`. Nếu giao diện muốn luôn hiển thị hai chữ số, đó là việc của formatter; nếu dữ liệu cần được lưu với scale cố định, đó là quyết định chuẩn hóa trong tầng nghiệp vụ/lưu trữ.

Trường hợp `@Digits(integer = 6, fraction = 0)` cho phép số **không có chữ số thập phân** theo biểu diễn được kiểm tra. Nó không có nghĩa là “số nguyên dương”, vì giá trị âm như `-123` vẫn được chấp nhận.

### 2.3. `null` và điều kiện bắt buộc nhập

```java
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class PaymentInput {

    @NotNull
    @Digits(integer = 4, fraction = 2)
    private BigDecimal amount;
}
```

Đoạn này minh họa field trong bean, chưa phải ứng dụng Java chạy độc lập. Nếu `amount == null`, `@Digits` bỏ qua và `@NotNull` tạo violation. Đây là nguyên tắc thiết kế của nhiều constraint Jakarta: kiểm tra *không có giá trị* thường tách khỏi kiểm tra *giá trị có định dạng/giới hạn hợp lệ*.

Nếu `amount` phải dương và không vượt quá 5000, cần bổ sung điều kiện miền giá trị. Dù `@Digits(integer = 4, fraction = 2)` chặn `10000.00`, nó vẫn chấp nhận `9999.99` và `-9999.99`, nên không đủ diễn đạt “0 ≤ amount ≤ 5000”.

## 3. `BigDecimal`: precision, scale và số 0 cuối

Với số thập phân cần độ chính xác, hãy ưu tiên `BigDecimal`. Tránh tạo bằng `new BigDecimal(0.1)` vì `double` có biểu diễn nhị phân xấp xỉ; hãy dùng chuỗi hoặc `BigDecimal.valueOf(...)` phù hợp.

`BigDecimal` có hai thuộc tính dễ liên hệ tới `@Digits`:

- `precision()`: số chữ số của **hệ số không chia tỷ lệ** (*unscaled value*) theo quy tắc của `BigDecimal`.
- `scale()`: số chữ số sau dấu thập phân trong cách biểu diễn thông thường nếu scale dương; scale âm biểu thị lũy thừa 10 trong dạng số.

Trong Hibernate Validator, khi kiểm tra `BigDecimal`, cách xác định thường dựa trên:

```text
integerPartLength  = precision - scale
fractionPartLength = max(scale, 0)
```

Cần hiểu đây là **chi tiết của provider**, không phải cách triển khai bắt buộc được viết trong chữ ký annotation của Jakarta. Với số có scale âm như `1E+4`, độ dài phần nguyên được tính theo giá trị số đầy đủ (`10000` có 5 chữ số phần nguyên). Không nên tự thay bằng việc đếm ký tự của `toString()`.

Ví dụ Java 17 thuần JDK:

```java
import java.math.BigDecimal;

public class BigDecimalMetadata {
    public static void main(String[] args) {
        for (String raw : new String[]{"1.23", "1.230", "1234.56"}) {
            BigDecimal value = new BigDecimal(raw);
            System.out.printf("%s: precision=%d, scale=%d%n",
                    raw, value.precision(), value.scale());
        }
    }
}
```

Chạy bằng:

```bash
javac BigDecimalMetadata.java
java BigDecimalMetadata
```

**Standard output chính xác:**

```text
1.23: precision=3, scale=2
1.230: precision=4, scale=3
1234.56: precision=6, scale=2
```

Hai đối tượng sau có cùng **giá trị số** theo `compareTo`, nhưng không có cùng scale:

```java
new BigDecimal("1.230").compareTo(new BigDecimal("1.23")) == 0
```

Với `fraction = 2`, Hibernate Validator sẽ từ chối `new BigDecimal("1.230")` vì **scale bằng 3**. Đây là khác biệt quan trọng giữa việc kiểm tra một giá trị thập phân được biểu diễn bằng `BigDecimal` và việc muốn biết giá trị số có thể rút gọn về bao nhiêu chữ số.

Nếu yêu cầu nghiệp vụ cho phép bỏ các số 0 không có ý nghĩa ở cuối, có thể **quyết định chuẩn hóa tường minh** bằng:

```java
BigDecimal normalized =
        new BigDecimal("1.230").stripTrailingZeros();
// normalized có giá trị 1.23 và scale = 2
```

Đừng âm thầm chuẩn hóa nếu dữ liệu ghi nhận mức độ chính xác có chủ đích, chẳng hạn số đo `1.230` và `1.23` có thể mang ý nghĩa khác nhau. Cũng đừng gọi `setScale(2, RoundingMode.HALF_UP)` chỉ để cho qua validation: hành vi đó **làm tròn dữ liệu**. Nếu nghiệp vụ yêu cầu làm tròn, quy định rõ chính sách và thời điểm thực hiện trước khi validate/lưu.

## 4. Các kiểu dữ liệu được hỗ trợ

Theo Jakarta Validation API, `@Digits` hỗ trợ các kiểu chuẩn sau:

- `BigDecimal`
- `BigInteger`
- `CharSequence` (thường là `String`)
- `byte`, `short`, `int`, `long` và các wrapper tương ứng (`Byte`, `Short`, `Integer`, `Long`)

Hibernate Validator còn hỗ trợ một số kiểu Number khác theo **phần mở rộng riêng của provider**. Không mặc định rằng mọi implementation Jakarta đều hỗ trợ `float`/`double` theo cùng cách; số thực nhị phân còn có vấn đề sai số khi đổi về dạng thập phân.

### `BigInteger` và các kiểu nguyên

```java
@Digits(integer = 6, fraction = 0)
private Long accountSequence;
```

Đối với số nguyên, phần lẻ không xuất hiện. `fraction = 0` cho thấy ý định rõ ràng; giới hạn `integer = 6` chặn một giá trị nguyên có hơn 6 chữ số. Việc sử dụng `@Digits` không thay cho kiểm tra dải số như `@Min`/`@Max` hoặc giới hạn kiểu dữ liệu Java.

### Với `String`, đừng nhầm kiểm tra số và chiều dài chuỗi

```java
@Digits(integer = 4, fraction = 2)
private String enteredAmount;
```

Với provider như Hibernate Validator, chuỗi phải phân tích được thành giá trị số phù hợp rồi mới kiểm tra phần nguyên/phần lẻ. Ví dụ `"abc"` không hợp lệ. Tuy nhiên, `@Digits` **không đơn thuần đếm độ dài ký tự**, không phải một regex bắt buộc cách nhập duy nhất, và không bảo đảm bảo toàn số 0 ở đầu. `"000123.45"` có thể được diễn giải thành số `123.45` tùy cách provider chuyển chuỗi, thay vì bị đánh giá theo 6 ký tự ở phần nguyên.

Nếu cần kiểm tra đúng hình dạng văn bản như “tối đa bốn chữ số trước dấu chấm, tối đa hai sau dấu chấm, không có số 0 đầu, không có ký hiệu mũ”, hãy cân nhắc `@Pattern` cho trường `String` **cùng với** kiểm tra số/nghiệp vụ khi phù hợp. Không sử dụng `@Size` để thay `@Digits`: `@Size(max = 6)` kiểm tra độ dài chuỗi/collection, bao gồm cả dấu âm, dấu phân cách, ký tự khác, chứ không kiểm tra hai phần của một số.

### `Locale` và định dạng người dùng

`@Digits` không phải formatter theo `Locale`. Trong Spring MVC, nếu người dùng nhập `"1.234,56"` ở một giao diện dùng dấu phẩy thập phân, dữ liệu cần được parse đúng thông qua cơ chế **data binding/formatting** trước khi `@Digits` đánh giá đối tượng `BigDecimal`. Một lỗi chuyển kiểu từ chuỗi sang số có thể xảy ra trước validation. Với payload JSON số, client nên gửi số đúng cú pháp JSON và hợp đồng API rõ ràng; không coi dấu phẩy thập phân của giao diện là cú pháp JSON số.

## 5. So sánh với các constraint thường dùng

| Constraint | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| `@Digits(integer=4,fraction=2)` | Tối đa bao nhiêu chữ số ở phần nguyên/phần thập phân? | `1234.56` đạt, `12345.67` không đạt |
| `@NotNull` | Có bắt buộc phải có giá trị? | `null` bị từ chối |
| `@Positive`, `@PositiveOrZero` | Giá trị có phải dương/không âm? | `-1.00` bị từ chối |
| `@DecimalMin("0.00")` | Có lớn hơn hoặc bằng một ngưỡng? | Chặn số âm theo giá trị |
| `@DecimalMax("5000.00")` | Có nhỏ hơn hoặc bằng một ngưỡng? | Chặn `5000.01` |
| `@Size(min=,max=)` | Chuỗi/collection/array có độ dài hoặc kích thước bao nhiêu? | Không thay thế số chữ số thập phân |
| `@Pattern(regexp=...)` | Chuỗi có khớp mẫu ký tự cụ thể? | Ép dấu chấm và độ dài cách viết |
| `@Column(precision=6,scale=2)` | Gợi ý schema số thập phân cho JPA/DB | Liên quan lưu trữ, không thay thế Bean Validation |

Một quy tắc thực tế có thể ghép như sau:

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class PriceInput {

    @NotNull(message = "amount.required")
    @Digits(integer = 4, fraction = 2, message = "amount.digits")
    @DecimalMin(value = "0.00", message = "amount.nonNegative")
    @DecimalMax(value = "5000.00", message = "amount.tooLarge")
    private BigDecimal amount;
}
```

Đây là một field minh họa; cần constructor/getter/setter hoặc binding phù hợp khi đưa vào ứng dụng MVC. Các constraint này mang trách nhiệm khác nhau. Một giá trị như `5000.001` có thể vi phạm cả `@Digits` lẫn `@DecimalMax`; Bean Validation **không đảm bảo chỉ trả một lỗi hoặc thứ tự các lỗi**. Ứng dụng phải có chiến lược hiển thị nếu không muốn nhiều thông báo trên cùng một field.

## 6. Ví dụ chạy được trên Java 17: kiểm tra các trường hợp biên

Ví dụ sau tạo một Bean Validation provider và chạy `@Digits` trên object `AmountForm`. Nó in rõ trường hợp **đạt** hoặc tên constraint **vi phạm**; tên constraint được sắp xếp để stdout không phụ thuộc thứ tự `Set<ConstraintViolation<?>>`.

Sử dụng dự án Gradle độc lập:

```text
digits-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DigitsDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'digits-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DigitsDemo'
}
```

Hibernate Validator 8 là provider Jakarta Bean Validation dùng namespace `jakarta.validation.*`. `expressly` cung cấp Jakarta Expression Language implementation cần cho message interpolation đầy đủ của provider. Nếu dự án là Spring Boot, thường thêm `spring-boot-starter-validation` và để BOM của Spring Boot quản lý phiên bản thay vì cố định hai dependency độc lập như ví dụ.

**`src/main/java/DigitsDemo.java`:**

```java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class DigitsDemo {

    public static final class AmountForm {

        @NotNull
        @Digits(integer = 4, fraction = 2)
        private final BigDecimal amount;

        public AmountForm(BigDecimal amount) {
            this.amount = amount;
        }

        public BigDecimal getAmount() {
            return amount;
        }
    }

    private static String describe(
            Set<ConstraintViolation<AmountForm>> violations) {

        if (violations.isEmpty()) {
            return "PASS";
        }

        return violations.stream()
                .map(v -> v.getPropertyPath() + ":"
                        + v.getConstraintDescriptor()
                            .getAnnotation()
                            .annotationType()
                            .getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        String[] inputs = {
            "1234.56",
            "1234",
            "-9999.99",
            "12345.67",
            "12.345",
            "1.230",
            "1.23",
            null
        };

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            for (String raw : inputs) {
                BigDecimal amount =
                        raw == null ? null : new BigDecimal(raw);

                AmountForm form = new AmountForm(amount);

                Set<ConstraintViolation<AmountForm>> violations =
                        validator.validate(form);

                String label = raw == null ? "<null>" : raw;
                System.out.println(label + " -> " + describe(violations));
            }
        }
    }
}
```

Dùng Gradle cài sẵn:

```bash
gradle run --quiet
```

Hoặc `./gradlew run --quiet` nếu có Gradle Wrapper trên Linux/macOS; trên Windows dùng `gradlew.bat run --quiet`.

**Standard output mong đợi:**

```text
1234.56 -> PASS
1234 -> PASS
-9999.99 -> PASS
12345.67 -> amount:Digits
12.345 -> amount:Digits
1.230 -> amount:Digits
1.23 -> PASS
<null> -> amount:NotNull
```

Tại sao các dòng trên đúng?

1. `1234.56` vừa đủ 4 chữ số phần nguyên và 2 chữ số thập phân.
2. `1234` không có phần lẻ, vẫn đạt vì `fraction` là *tối đa* 2.
3. `-9999.99` đạt: dấu âm không được tính vào số chữ số; muốn cấm âm thì thêm `@DecimalMin("0")` hoặc `@PositiveOrZero`.
4. `12345.67` có 5 chữ số phần nguyên, vượt `integer = 4`.
5. `12.345` có 3 chữ số thập phân, vượt `fraction = 2`.
6. `1.230` được tạo bằng `new BigDecimal("1.230")`, có `scale = 3` và bị từ chối dù số cuối là 0.
7. `null` **được @Digits chấp nhận** nhưng bị `@NotNull` từ chối, nên chỉ hiển thị `amount:NotNull`.
8. Tập violations không đảm bảo thứ tự; ví dụ sắp xếp chuỗi trước khi in để kết quả lặp lại được.

Chương trình kiểm tra object được tạo từ các chuỗi số hợp lệ. Nó **không** minh họa input sai cú pháp như `"12,34"` hoặc `"abc"` khi trường đích là `BigDecimal`, bởi `new BigDecimal(raw)` sẽ ném `NumberFormatException` *trước khi* Bean Validation chạy. Đó chính là lý do cần tách conversion/parsing khỏi validation.

## 7. Áp dụng trong Spring MVC và Spring Boot

### 7.1. Định nghĩa DTO

Với Spring Boot 3+/Spring Framework 6+, DTO minh họa cho request JSON:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public record AmountRequest(
        @NotNull
        @Digits(integer = 4, fraction = 2)
        BigDecimal amount
) {}
```

`@Digits` được đặt trên record component, qua đó constraint có thể được provider dùng trên field/accessor theo các target mà annotation hỗ trợ. Ví dụ này dùng JSON số với `BigDecimal`; không có bước parse chuỗi dùng Locale của người dùng.

### 7.2. Controller dùng `@Valid`

Đoạn sau là **minh họa tích hợp**, cần có ứng dụng Spring MVC và các import tương ứng:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AmountController {

    @PostMapping("/amounts")
    public ResponseEntity<String> create(
            @Valid @RequestBody AmountRequest input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body("amount không hợp lệ");
        }

        return ResponseEntity.ok("accepted");
    }
}
```

`BindingResult` đứng ngay sau tham số được kiểm tra để controller có thể xử lý lỗi Bean Validation theo cơ chế Spring MVC. Nếu không nhận `BindingResult`, lỗi validation của request object thường đi vào cơ chế exception (`MethodArgumentNotValidException` trong tình huống object validation thông thường), còn constraint method-level hoặc cấu hình validation khác có thể dẫn tới loại exception khác.

Ví dụ body JSON:

```json
{"amount": 1234.56}
```

vượt qua `@Digits(integer=4,fraction=2)` và có thể nhận `"accepted"` trong controller minh họa. Body:

```json
{"amount": 12345.67}
```

vi phạm `@Digits` và controller trả HTTP 400 với chuỗi `"amount không hợp lệ"`. Payload sai cú pháp JSON hoặc không chuyển đổi được sang `BigDecimal` có thể bị từ chối **trước validation** qua Jackson/`HttpMessageConverter` và không nhất thiết đi vào `BindingResult` như một violation của `@Digits`.

Trong API production, nên trả cấu trúc lỗi rõ ràng gồm field, error code và message được nội suy phù hợp; không phơi bày giá trị nhạy cảm trong log/response.

### 7.3. Form nhập liệu và `Locale`

Với `@ModelAttribute`, Spring bind chuỗi text từ biểu mẫu thành kiểu số; formatter/conversion service quyết định cách hiểu dấu phân cách của request. Nếu form chọn locale Đức và nhập `"1.234,56"`, lớp parsing phải hiểu đúng dấu chấm nhóm và dấu phẩy thập phân để tạo `BigDecimal("1234.56")` trước khi `@Digits` chạy.

Không nên dựa vào `@Digits` để tự hiểu `Locale`; nó **không** thay thế `@NumberFormat`, `Formatter<BigDecimal>` hoặc cách cấu hình locale resolver. Khi nhập liệu được coi là **String** và validate trực tiếp bằng `@Digits`, provider có thể yêu cầu cú pháp số theo `BigDecimal`, không đồng nghĩa chấp nhận mọi cách viết địa phương.

## 8. Quan hệ với cơ sở dữ liệu: precision và scale

Trong schema SQL, cột kiểu `DECIMAL(p, s)` thường có:

- `p` (*precision*): tổng số chữ số tối đa.
- `s` (*scale*): số chữ số ở phần thập phân.

Từ yêu cầu **tối đa 4 chữ số phần nguyên + 2 chữ số thập phân**, cách ánh xạ thường gặp là:

```java
@Digits(integer = 4, fraction = 2)
@Column(precision = 6, scale = 2)
private BigDecimal amount;
```

Đây là đoạn minh họa JPA (`jakarta.persistence.Column`), không phải Entity đầy đủ. Trong trường hợp thông thường, `DECIMAL(6,2)` chứa tối đa 6 chữ số trong đó 2 sau dấu thập phân, tương ứng tối đa 4 chữ số phần nguyên. Tuy nhiên:

1. `@Digits` là **kiểm tra ứng dụng**; `@Column` là metadata ánh xạ schema của ORM. Chúng không thay thế nhau.
2. Hibernate ORM có thể dùng `@Digits` khi sinh DDL/schema metadata trong một số chế độ, nhưng kết quả phụ thuộc provider/cấu hình; **không nên mặc định annotation là đủ để tạo đúng cột**. Hãy kiểm tra migration SQL thực tế.
3. Từng hệ quản trị CSDL có quy tắc làm tròn, từ chối hoặc chuyển đổi khác nhau khi ghi số vượt scale. Database phải bảo vệ tính nhất quán dù request bỏ qua tầng web.
4. Với dữ liệu tài chính, còn phải quyết định đơn vị tiền, giới hạn âm/dương, rounding mode, chính sách chuyển đổi và transaction. `@Digits` chỉ xác định số chữ số được phép.

Đừng nhầm công thức đơn giản `p = integer + fraction` với việc `@Digits` tự lưu số hay tự xử lý overflow. Constraint giữ vai trò tiền kiểm; schema và nghiệp vụ vẫn cần được thiết kế nhất quán.

## 9. Các lỗi thường gặp

1. **Nghĩ `fraction=2` bắt buộc hai chữ số.** Đây là giới hạn tối đa; `12` và `12.3` vẫn đạt.
2. **Nghĩ `@Digits` làm tròn.** Nó chỉ báo violation; muốn làm tròn phải có quy tắc nghiệp vụ rõ.
3. **Dùng `double` cho tiền rồi kỳ vọng số lẻ luôn chính xác.** Nên dùng `BigDecimal` tạo từ chuỗi hoặc nguồn decimal đáng tin.
4. **Không để ý `BigDecimal.scale()`.** `1.230` có scale 3 và có thể bị từ chối với `fraction = 2`; `1.23` có scale 2.
5. **Nghĩ `@Digits` cấm số âm.** Dấu âm không làm tăng số chữ số; thêm `@DecimalMin` hoặc `@PositiveOrZero` nếu cần.
6. **Nghĩ `null` không hợp lệ.** Riêng `@Digits` cho phép `null`; thêm `@NotNull` cho trường bắt buộc.
7. **Dùng `@Size(max = 6)` cho số decimal.** `@Size` đo kích thước dữ liệu/chuỗi, không tách phần nguyên và phần thập phân.
8. **Đếm ký tự raw input thay số có ý nghĩa.** Số 0 đầu, dấu cộng/trừ, dấu thập phân và biểu diễn mũ có thể làm độ dài văn bản khác độ dài số; muốn kiểm soát cách gõ thì cần validation định dạng riêng.
9. **Không tách conversion và validation.** Chuỗi `"1,23"` có thể sai ngay khi parse `BigDecimal`; `@Digits` không trực tiếp xử lý locale.
10. **Chỉ kiểm tra API mà bỏ qua DB.** Ứng dụng khác có thể ghi dữ liệu trực tiếp; schema vẫn phải có precision/scale và constraint phù hợp.
11. **Nghĩ provider có kiểu hỗ trợ đồng nhất.** Jakarta quy định tập kiểu chuẩn; Hibernate Validator có thêm kiểu tùy implementation. Nếu phụ thuộc phần mở rộng, tài liệu hóa và test provider cụ thể.
12. **Bỏ qua test số 0 và số âm.** Những giá trị `0.00`, `-0.01`, `10000.00` cần được bao phủ theo chính sách nghiệp vụ.
13. **Cho rằng lỗi validation luôn có một phần tử đầu tiên.** `Set<ConstraintViolation<?>>` không có thứ tự; hiển thị lỗi có thứ tự riêng.
14. **Nhầm `javax.validation.*` với `jakarta.validation.*`.** Trong Spring Framework 6+/Boot 3+ dùng namespace Jakarta; migration từ phiên bản cũ phải cập nhật import và provider.

## 10. Checklist và câu hỏi thực hành

### Bảng test tối thiểu cho `@Digits(integer = 4, fraction = 2)`

| Test | Kỳ vọng |
| --- | --- |
| `new BigDecimal("0")` | Đạt |
| `new BigDecimal("0.00")` | Đạt |
| `new BigDecimal("1234.56")` | Đạt |
| `new BigDecimal("12345.67")` | Vi phạm `integer` |
| `new BigDecimal("1234.567")` | Vi phạm `fraction` |
| `new BigDecimal("-9999.99")` | Đạt theo `@Digits`; có thể vi phạm rule không âm riêng |
| `new BigDecimal("1.230")` | Vi phạm `fraction=2` trong Hibernate Validator |
| `null` và chỉ có `@Digits` | Đạt |
| `null` và thêm `@NotNull` | Vi phạm `@NotNull` |

Nên kiểm thử cả ba đường: **Bean Validation thuần Java**, **Spring MVC form binding** và **JSON deserialization** nếu hệ thống sử dụng chúng. Test JSON khác test chuỗi từ form vì cách convert dữ liệu đầu vào khác nhau.

### Tự trả lời

- `@Digits(integer=5, fraction=2)` có nghĩa gì? **Tối đa 5 chữ số ở phần nguyên và 2 ở phần thập phân; không yêu cầu đúng số lượng đó.**
- `@Digits(integer=4, fraction=2)` có ngăn `-9999.99` không? **Không**; cần constraint miền giá trị riêng.
- Vì sao `BigDecimal("1.230")` có thể fail trong khi `BigDecimal("1.23")` pass? **Scale lần lượt là 3 và 2**.
- Tại sao kết hợp `@NotNull`? **Vì `@Digits` coi null là hợp lệ**.
- Nếu muốn 2 chữ số sau dấu thập phân trong UI, bạn chọn gì? **Formatter/`@NumberFormat` hoặc logic hiển thị**, không dùng `@Digits` để thêm số 0.
- Nếu muốn DB chỉ lưu hai chữ số thập phân, có cần schema không? **Có**: dùng kiểu/cột decimal và migration thích hợp, cùng chính sách xử lý scale.
- Nếu user nhập `1.234,56` theo locale Đức thì `@Digits` có tự chuyển thành `1234.56` không? **Không**; Spring binding/conversion phải parse trước.

## 11. Tài liệu tham khảo

- [Jakarta Validation 3.1 — `@Digits` Javadoc](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Digits.html): hai tham số `integer`/`fraction`, kiểu hỗ trợ, null hợp lệ.
- [Jakarta Bean Validation 3.0 specification — `@Digits`](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): định nghĩa constraint chuẩn.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): kiểu mở rộng, mô tả `@Digits` và tác động tới metadata schema.
- [Java SE 17 — `BigDecimal` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `stripTrailingZeros`, `compareTo`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): provider/adapter, Spring `DataBinder`, lỗi validation.
- [Spring Framework — MVC Controller Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `BindingResult` và các đường xử lý lỗi.

**Điểm cần nhớ:** `@Digits` kiểm tra giới hạn **số chữ số phần nguyên** và **phần thập phân** của giá trị, dựa trên kiểu Java và provider; không làm tròn, không ràng buộc dấu hoặc null. Hãy kết hợp nó với `BigDecimal`, constraints miền giá trị và schema dữ liệu khi xây ứng dụng Spring.
