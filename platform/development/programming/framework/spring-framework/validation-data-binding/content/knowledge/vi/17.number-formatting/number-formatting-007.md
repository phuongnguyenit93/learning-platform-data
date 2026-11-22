# Xử lý chuỗi rỗng, dấu âm và số vượt phạm vi khi chuyển đổi số trong Spring

Dữ liệu số từ form hoặc API thường đến dưới dạng chuỗi. Người dùng có thể gửi `"125"`, `"+125"`, `"-8"`, `""`, `"   "` hoặc một chuỗi rất lớn như `"999999999999999999999"`. Những trường hợp này khác nhau: số hợp lệ, không cung cấp giá trị, sai cú pháp, vượt miền kiểu Java hoặc hợp cú pháp nhưng vi phạm quy tắc nghiệp vụ.

Khi Spring bind chuỗi vào property số, **converter thực hiện chuyển đổi kiểu**, còn validation kiểm tra ràng buộc như giá trị phải dương hoặc nằm trong một khoảng cho phép. Cần tách biệt blank/null, cú pháp dấu, giới hạn kiểu đích và giới hạn nghiệp vụ.

## 1. Phân loại đầu vào

| Input | Phân loại | Hướng xử lý |
| --- | --- | --- |
| `"125"` | Số nguyên hợp lệ | `Integer 125` nếu nằm trong miền |
| `"0"` | Số 0 | Cho phép hay cấm tùy nghiệp vụ |
| `"+125"` | Dấu cộng ở đầu | `Integer.parseInt` chấp nhận |
| `"-8"` | Số âm hợp cú pháp | Kiểu int biểu diễn được; nghiệp vụ quyết định |
| `""` | Chuỗi rỗng | Null hoặc lỗi tùy contract |
| `"   "` | Chỉ khoảng trắng | Chuẩn hóa rồi quyết định |
| `" 125 "` | Khoảng trắng hai đầu | `parseInt` trực tiếp không trim |
| `"12.5"` | Số thập phân | Không phải số nguyên cho `parseInt` |
| `"1,250"` | Dấu phân nhóm | Cần locale/formatter rõ |
| `"--5"` hoặc `"+"` | Sai cú pháp | Từ chối |
| `"2147483648"` | Vượt miền int | `NumberFormatException` |
| `"-2147483649"` | Dưới Integer.MIN_VALUE | `NumberFormatException` |

Số âm không phải lỗi parse chỉ vì nó âm. `Integer.parseInt("-8")` trả `-8`. Nếu số lượng không được âm, đó là quy tắc nghiệp vụ, không phải giới hạn của `int`.

## 2. Cú pháp Integer.parseInt và giới hạn kiểu

`Integer.parseInt(String)` phân tích chuỗi thập phân thành số nguyên có dấu. Một dấu ASCII `+` hoặc `-` được phép ở vị trí đầu tiên.

| Chuỗi | Kết quả |
| --- | --- |
| `"42"` | `42` |
| `"+42"` | `42` |
| `"-42"` | `-42` |
| `"-0"` | `0` |
| `" 42"` / `"42 "` | `NumberFormatException` |
| `"+ 42"` / `"++42"` | `NumberFormatException` |
| `""` | `NumberFormatException` |
| `"42.0"` / `"4_200"` | `NumberFormatException` |

`parseInt` **không tự trim khoảng trắng**. Nếu contract cho phép khoảng trắng đầu/cuối, code cần chuẩn hóa trước khi parse. Đừng trim âm thầm nếu khoảng trắng có ý nghĩa trong dữ liệu.

Miền `int`:

```java
Integer.MIN_VALUE == -2_147_483_648
Integer.MAX_VALUE ==  2_147_483_647
```

Hai biên này hợp lệ. Giá trị ngoài miền gây overflow:

```java
Integer.parseInt("2147483647");  // Hợp lệ
Integer.parseInt("-2147483648"); // Hợp lệ
Integer.parseInt("2147483648");  // NumberFormatException
Integer.parseInt("-2147483649"); // NumberFormatException
```

Không dùng cast `(int)` để xử lý overflow. Nếu parse thành `long` rồi ép kiểu, giá trị ngoài miền có thể wrap thành số khác. Hãy kiểm tra bounds hoặc dùng `Math.toIntExact(longValue)`.

## 3. Sai cú pháp, overflow và giới hạn nghiệp vụ

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Sai cú pháp | `"12x"`, `"--3"` | Chuỗi không biểu diễn số nguyên |
| Vượt kiểu | `"2147483648"` cho Integer | Không biểu diễn được trong kiểu đích |
| Vi phạm nghiệp vụ | `"-3"` khi quantity phải không âm; `"5001"` khi max là 5000 | Parse được nhưng không được chấp nhận |

`-3` là số nguyên hợp lệ trong Java. Tuy nhiên, property `quantity` có thể không cho phép âm. Kiểm tra điều này bằng custom converter, Bean Validation như `@PositiveOrZero` hoặc application service tùy loại quy tắc.

Converter đảm bảo representation/kiểu đích hợp lệ. Validator kiểm tra ràng buộc dữ liệu. Service kiểm tra điều kiện phụ thuộc trạng thái hệ thống như tồn kho, quyền hoặc hạn mức.

## 4. Chính sách cho chuỗi rỗng

Với wrapper `Integer`, ứng dụng có thể biểu diễn giá trị chưa nhập bằng `null`. Với primitive `int`, không thể gán `null`; giá trị mặc định là `0` nhưng không nên suy ra input rỗng có nghĩa là 0.

| Chính sách | `""` / `"   "` | Field không xuất hiện |
| --- | --- | --- |
| Optional → null | Trim rồi blank thành `null` | Setter không chạy; giá trị hiện tại có thể giữ nguyên |
| Required → error | Blank bị từ chối hoặc validation fail | Kiểm tra theo contract bắt buộc |
| Default value | Thay blank bằng default đã định nghĩa | Quy định riêng khi key thiếu |

**Không đồng nhất chuỗi rỗng với 0.** `""` không có chữ số; `"0"` là số nguyên hợp lệ. Nếu muốn input trống thành 0, hãy định nghĩa rõ default policy.

Cũng phân biệt **field không được gửi** và **field được gửi nhưng blank**. Khi key không xuất hiện, binder có thể không gọi setter. Khi key xuất hiện và converter trả null, setter có thể nhận null. Trong PATCH, “không đổi” khác “xóa giá trị”.

## 5. Converter với policy blank, dấu âm và range

Converter dưới đây: blank thành null cho field optional; trim đầu/cuối; cho phép dấu cộng theo parser Java; từ chối âm nếu cấu hình; parse theo miền int; kiểm tra range nghiệp vụ sau parse.

```java
public final class BoundedIntegerConverter
        implements Converter<String, Integer> {

    private final int minimum;
    private final int maximum;
    private final boolean allowNegative;

    public BoundedIntegerConverter(
            int minimum, int maximum, boolean allowNegative) {
        if (minimum > maximum) {
            throw new IllegalArgumentException("minimum > maximum");
        }
        this.minimum = minimum;
        this.maximum = maximum;
        this.allowNegative = allowNegative;
    }

    @Override
    public Integer convert(String source) {
        if (source == null) {
            return null;
        }

        String text = source.trim();
        if (text.isEmpty()) {
            return null;
        }

        final int value;
        try {
            value = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Value is not a valid 32-bit decimal integer", ex);
        }

        if (!allowNegative && value < 0) {
            throw new IllegalArgumentException(
                    "Negative values are not allowed");
        }

        if (value < minimum || value > maximum) {
            throw new IllegalArgumentException(
                    "Value is outside the permitted range");
        }

        return value;
    }
}
```

Đây là converter cho một policy cụ thể, không phải quy tắc chung cho mọi `String → Integer`. Số lượng có thể đặt min bằng 0; nhiệt độ có thể cho phép âm. Nếu field bắt buộc, đừng dựa vào converter trả null; thêm `@NotNull` hoặc contract bắt buộc phù hợp.

Kiểm tra range sau parse để phân biệt overflow kiểu đích với giới hạn nghiệp vụ: `"5001"` có thể là int hợp lệ nhưng vượt quota 5000; `"2147483648"` đã vượt miền int nên parse thất bại trước khi xét quota.

## 6. Ví dụ Java 17+ chạy với Spring DataBinder

Ví dụ dùng Spring Framework Core, không cần Spring Boot hoặc HTTP server. Ta đăng ký custom `Converter<String, Integer>` vào `DefaultFormattingConversionService`, rồi bind vào DTO có property `Integer`.

### Cấu trúc dự án

```text
number-input-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/NumberInputDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'number-input-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.NumberInputDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dùng JDK 17+ và Gradle tương thích, có Maven Central để tải dependency lần đầu.

### Mã Java đầy đủ

**`src/main/java/example/NumberInputDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class NumberInputDemo {

    public static final class BoundedIntegerConverter
            implements Converter<String, Integer> {

        private final int minimum;
        private final int maximum;
        private final boolean allowNegative;

        public BoundedIntegerConverter(
                int minimum, int maximum, boolean allowNegative) {
            if (minimum > maximum) {
                throw new IllegalArgumentException("minimum > maximum");
            }
            this.minimum = minimum;
            this.maximum = maximum;
            this.allowNegative = allowNegative;
        }

        @Override
        public Integer convert(String source) {
            if (source == null) {
                return null;
            }
            String text = source.trim();
            if (text.isEmpty()) {
                return null;
            }

            final int value;
            try {
                value = Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Value is not a valid 32-bit decimal integer", ex);
            }

            if (!allowNegative && value < 0) {
                throw new IllegalArgumentException(
                        "Negative values are not allowed");
            }
            if (value < minimum || value > maximum) {
                throw new IllegalArgumentException(
                        "Value is outside the permitted range");
            }
            return value;
        }
    }

    public static final class QuantityForm {
        private Integer quantity;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    private static String label(String input) {
        return input == null ? "<null>" : "[" + input + "]";
    }

    private static void printDirect(
            BoundedIntegerConverter converter, String input) {
        try {
            System.out.println(label(input) + " -> " + converter.convert(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(label(input) + " -> ERROR: " + ex.getMessage());
        }
    }

    private static void bindAndPrint(
            ConfigurableConversionService service, String input) {
        QuantityForm form = new QuantityForm();
        DataBinder binder = new DataBinder(form, "quantityForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", input);
        binder.bind(values);

        FieldError error =
                binder.getBindingResult().getFieldError("quantity");
        System.out.println("binding " + label(input)
                + " -> value=" + form.getQuantity()
                + "; error=" + (error != null)
                + (error == null ? "" : "; code=" + error.getCode()));
    }

    public static void main(String[] args) {
        BoundedIntegerConverter converter =
                new BoundedIntegerConverter(0, 1000, false);

        printDirect(converter, " 42 ");
        printDirect(converter, "+42");
        printDirect(converter, "");
        printDirect(converter, "   ");
        printDirect(converter, "-5");
        printDirect(converter, "1001");
        printDirect(converter, "2147483648");
        printDirect(converter, "12x");

        ConfigurableConversionService service =
                new DefaultFormattingConversionService();
        service.addConverter(converter);

        bindAndPrint(service, "18");
        bindAndPrint(service, "-5");
    }
}
```

### Chạy và stdout dự kiến

```bash
gradle -q run
```

Nếu có Gradle wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

```text
[ 42 ] -> 42
[+42] -> 42
[] -> null
[   ] -> null
[-5] -> ERROR: Negative values are not allowed
[1001] -> ERROR: Value is outside the permitted range
[2147483648] -> ERROR: Value is not a valid 32-bit decimal integer
[12x] -> ERROR: Value is not a valid 32-bit decimal integer
binding [18] -> value=18; error=false
binding [-5] -> value=null; error=true; code=typeMismatch
```

Giải thích: `" 42 "` được trim tường minh; `"+42"` hợp cú pháp; blank thành `null`; `-5` bị policy từ chối; `1001` vượt range nghiệp vụ; `2147483648` overflow kiểu int; `12x` sai cú pháp. Khi đi qua `DataBinder`, lỗi conversion của `quantity` được ghi vào `BindingResult`/`FieldError` với mã thường gặp `typeMismatch`.

Nếu DTO yêu cầu bắt buộc, thêm `@NotNull` và kích hoạt Bean Validation. Không in raw input hoặc exception chứa dữ liệu nhạy cảm trong production.

## 7. Dùng Long, BigInteger hoặc BigDecimal khi cần

| Kiểu | Đặc điểm | Khi dùng |
| --- | --- | --- |
| `Integer` | 32-bit signed | Số đếm nhỏ có bounds rõ |
| `Long` | 64-bit signed | Lớn hơn miền int nhưng vẫn hữu hạn |
| `BigInteger` | Số nguyên chính xác tùy bộ nhớ | Số nguyên rất lớn |
| `BigDecimal` | Số thập phân chính xác theo decimal | Tiền và decimal cần kiểm soát scale |

`Long.parseLong` mở rộng miền nhưng vẫn có `Long.MIN_VALUE`/`Long.MAX_VALUE`. `BigInteger` biểu diễn số nguyên lớn:

```java
BigInteger value = new BigInteger("999999999999999999999999");
```

Số càng dài càng tốn CPU và bộ nhớ. Giới hạn chiều dài input trước khi tạo `BigInteger` để tránh lạm dụng tài nguyên. Sau parse vẫn cần kiểm tra range nghiệp vụ.

Không ép `long` sang `int` bằng cast khi chưa kiểm tra. Dùng `Math.toIntExact(longValue)` để phát hiện giá trị không thể biểu diễn chính xác.

## 8. Số âm là policy theo domain

| Trường hợp | Số âm có thể hợp lệ? |
| --- | --- |
| Số lượng đặt mua | Thường không |
| Khoản điều chỉnh/hoàn tiền | Có thể |
| Nhiệt độ/độ cao | Có |
| Số dư tài khoản | Tùy quy tắc |
| Biên độ thay đổi | Có thể biểu diễn tăng/giảm |

Không nên dùng một converter `String → Integer` chung để cấm số âm toàn ứng dụng nếu các field khác ý nghĩa. Hãy dùng converter theo target domain type, validation theo field hoặc business service khi quy tắc phụ thuộc trạng thái hệ thống.

## 9. Locale, grouping và decimal separator

`Integer.parseInt("1,000")` không coi dấu phẩy là grouping separator; `"1.000"` cũng không phải số nguyên hợp lệ. Với dữ liệu hiển thị theo locale, dùng `NumberFormat`/`DecimalFormat` hoặc Spring `Formatter` với locale xác định rõ.

`1,25` có thể là decimal ở locale này nhưng dấu phẩy là grouping ở locale khác. Không tự bỏ mọi dấu phẩy rồi parse vì `"1,2"` có thể bị diễn giải sai thành `12`. Với tiền hoặc decimal chính xác, ưu tiên `BigDecimal` thay vì `double`.

## 10. Primitive, wrapper và field bị thiếu

```java
public class QuantityForm {
    private Integer optionalQuantity;
    private int primitiveQuantity;
}
```

`Integer` có thể biểu diễn `null`, còn `int` không thể. Chọn `Integer` khi cần phân biệt chưa nhập với 0. Chọn `int` khi giá trị phải tồn tại và mặc định 0 có ý nghĩa. Không dùng 0 làm sentinel nếu 0 là giá trị nghiệp vụ hợp lệ.

Khi field không xuất hiện trong request, binder có thể không gọi setter; giá trị hiện tại/default có thể giữ nguyên. Khi key xuất hiện nhưng blank được convert thành null, setter có thể nhận null. Đây là khác biệt quan trọng trong update/PATCH.

## 11. BindingResult và validation sau conversion

Với `@ModelAttribute` trong Spring MVC, luồng phổ biến là binding/conversion rồi validation khi tham số có `@Valid`/`@Validated` và validator phù hợp.

| Tình huống | Bước lỗi | Kết quả thường gặp |
| --- | --- | --- |
| `quantity=abc` | Conversion | `FieldError` mã `typeMismatch` |
| `quantity=2147483648` vào Integer | Conversion/overflow | `FieldError` mã `typeMismatch` |
| `quantity=-5` bị converter cấm | Custom conversion policy | Binding error |
| `quantity=-5` parse được, có `@PositiveOrZero` | Validation | Constraint violation |
| Blank thành null, có `@NotNull` | Validation | Constraint violation |
| Field không xuất hiện | Không có lần convert | Giá trị hiện tại/default có thể giữ nguyên |

`BindingResult` phải đứng ngay sau tham số `@ModelAttribute` tương ứng:

```java
@PostMapping("/quantities")
String submit(
        @Valid @ModelAttribute("form") QuantityForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "quantities/form";
    }
    quantityService.apply(form);
    return "quantities/success";
}
```

Đây là đoạn minh họa MVC cần controller, DTO, validator và view phù hợp. Không gọi service nghiệp vụ nếu có lỗi binding/validation. `@RequestBody` JSON đi qua `HttpMessageConverter` (ví dụ Jackson), không nhất thiết giống `@ModelAttribute`.

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `" 42 "` bị từ chối | `parseInt` không trim | Chuẩn hóa theo contract |
| Blank thành 0 | Default policy không rõ | Phân biệt null, empty và "0" |
| Số âm bị từ chối toàn app | Policy converter quá rộng | Quy định theo domain/field |
| Giá trị lớn bị wrap sau cast | Ép long sang int không kiểm tra | `Math.toIntExact` hoặc kiểm tra bounds |
| `2147483648` thành lỗi chung | Overflow không phân loại | Hiển thị type mismatch phù hợp |
| `1,000` parse sai | Locale không rõ | Dùng Formatter/NumberFormat |
| Blank thành null nhưng không lỗi | Field optional/thiếu constraint | Dùng `@NotNull` phù hợp |
| Số rất dài tốn tài nguyên | Không giới hạn input | Giới hạn chiều dài trước parse |
| Lỗi conversion bị hiểu là validation | Nhầm `typeMismatch` với constraint | Xử lý binding trước service |

## 13. Kiểm thử giá trị biên

Với converter giới hạn `0..1000` và optional blank:

| Case | Input | Kỳ vọng |
| --- | --- | --- |
| Min/max | `"0"` / `"1000"` | Thành công |
| Dưới min/trên max | `"-1"` / `"1001"` | Từ chối theo policy |
| Dấu cộng | `"+1"` | `1` |
| Whitespace | `" 1 "` | `1` nếu trim |
| Blank | `""` / `"   "` | `null` |
| Sai ký tự | `"1x"` | Từ chối parse |
| Chỉ có dấu | `"+"` / `"-"` | Từ chối parse |
| Biên Integer | `"2147483647"` / `"-2147483648"` | Parse được; policy quyết định |
| Overflow | `"2147483648"` / `"-2147483649"` | Từ chối parse |
| Chuỗi rất dài | Hàng nghìn chữ số | Từ chối theo giới hạn input |

JUnit test minh họa:

```java
@Test
void acceptsTrimmedPositiveNumber() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertEquals(42, converter.convert(" 42 "));
}

@Test
void treatsBlankAsNull() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertNull(converter.convert("   "));
}

@Test
void rejectsNegativeValue() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("-1"));
}

@Test
void rejectsIntegerOverflow() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("2147483648"));
}
```

Đoạn test cần JUnit 5 và import assertions phù hợp. Unit test converter kiểm tra policy; test binder xác nhận lỗi đúng field; integration test MVC xác nhận binder thực tế đăng ký.

## 14. Checklist thiết kế converter số

- Blank có nghĩa là null, lỗi hay default?
- Dấu cộng có được chấp nhận? Số âm hợp lệ với field này không?
- Có trim khoảng trắng hay contract yêu cầu strict?
- Kiểu đích là Integer, Long, BigInteger hay BigDecimal?
- Min/max kiểu và min/max nghiệp vụ có khác nhau?
- Input có giới hạn chiều dài trước parse?
- `BindingResult` được xử lý trước business service?
- Missing và blank có hành vi khác nhau?
- Có log raw input nhạy cảm hoặc bỏ sót test overflow?

## 15. Ghi nhớ và tài liệu chính thức

- `Integer.parseInt` nhận dấu `+`/`-` tùy chọn ở đầu; chuỗi rỗng, ký tự sai và overflow có thể gây `NumberFormatException`.
- `parseInt` không tự trim khoảng trắng.
- `Integer.MIN_VALUE` và `Integer.MAX_VALUE` là hai biên hợp lệ; giá trị ngoài miền phải bị từ chối.
- Số âm hợp cú pháp signed integer; cấm âm là policy nghiệp vụ riêng.
- `Integer` biểu diễn được null; primitive `int` thì không.
- Custom converter cần quy định blank, dấu, parse, overflow và range. Validator/service xử lý các ràng buộc tương ứng.
- Lỗi chuyển đổi trong Spring binding thường được thể hiện qua `BindingResult`/`FieldError` với mã `typeMismatch`.

Tài liệu tham khảo:

- [Oracle Java — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): cú pháp dấu, miền int và `NumberFormatException`.
- [Oracle Java — Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): miền số nguyên 64-bit.
- [Oracle Java — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên lớn.
- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConversionService` và registry.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, conversion và `BindingResult`.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): phối hợp conversion và validation.
