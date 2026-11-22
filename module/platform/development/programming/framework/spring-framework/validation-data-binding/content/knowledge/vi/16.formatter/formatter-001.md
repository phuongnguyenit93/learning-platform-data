# `Formatter<T>` và nhập/xuất dữ liệu theo `Locale` trong Spring Framework

## 1. Bài toán: cùng một giá trị, nhiều cách biểu diễn

Một giá trị miền nghiệp vụ có thể được viết khác nhau tùy ngôn ngữ và vùng địa lý của người dùng:

| Giá trị | `Locale.US` (`en-US`) | `Locale.GERMANY` (`de-DE`) |
| --- | --- | --- |
| Số thập phân 1234,5 | `1,234.50` | `1.234,50` |
| Ý nghĩa dấu phân cách | Dấu phẩy phân nhóm, dấu chấm thập phân | Dấu chấm phân nhóm, dấu phẩy thập phân |

Nếu luôn dùng một quy tắc cố định, ứng dụng có thể đọc sai dữ liệu: chuỗi `1.234,50` trong giao diện tiếng Đức không thể được hiểu đơn giản bằng quy tắc số kiểu Mỹ. Khi xuất dữ liệu để hiển thị, ứng dụng cũng cần trình bày theo cách người dùng quen đọc.

Trong Spring, `Formatter<T>` là cơ chế chuyển đổi **hai chiều** giữa chuỗi dùng ở giao diện và một kiểu `T` của chương trình, đồng thời nhận `Locale`. Nó đặc biệt phù hợp với dữ liệu form, query parameter và các trường được biểu diễn cho người dùng. Mục tiêu của bài:

- Hiểu vai trò của `parse`, `print`, `Locale` và `FormattingConversionService`.
- Tự cài một `Formatter<T>` và đăng ký để Spring MVC dùng khi binding.
- Biết ranh giới giữa định dạng giao diện, kiểm tra nghiệp vụ và dữ liệu JSON/API.

`Locale` cho biết quy ước ngôn ngữ/vùng (chẳng hạn `en-US`, `de-DE`, `vi-VN`); nó **không tự xác định múi giờ**, tiền tệ của giao dịch hay tất cả quy tắc nghiệp vụ. Hai người có cùng `Locale` vẫn có thể sử dụng múi giờ hoặc đơn vị tiền khác nhau.

## 2. Hợp đồng của `Formatter<T>`

Các interface cốt lõi thuộc package `org.springframework.format`:

```java
public interface Printer<T> {
    String print(T object, java.util.Locale locale);
}

public interface Parser<T> {
    T parse(String text, java.util.Locale locale)
            throws java.text.ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

Đây là chữ ký API được rút gọn để học; khi viết mã thực tế hãy `implements Formatter<T>` từ Spring, không khai báo lại các interface.

- `parse(String, Locale)`: biến văn bản nhập vào thành đối tượng kiểu `T`; ví dụ `"1.234,50"` với `de-DE` thành một giá trị số `1234.50`.
- `print(T, Locale)`: biến đối tượng thành chuỗi trình bày; ví dụ cùng đối tượng `1234.50` thành `"1,234.50"` ở `en-US`.
- `T` là **kiểu đích** cần chuyển đổi, chẳng hạn `LocalDate`, `Price`, `PhoneNumber`. Nó không phải kiểu của chuỗi đầu vào.
- Nếu không phân tích được đầu vào, `parse` nên ném `ParseException` hoặc `IllegalArgumentException` rõ nghĩa. Không âm thầm đổi một chuỗi sai thành `0` hoặc một giá trị mặc định giả.

Hai thao tác bổ sung cho nhau, nhưng không nhất thiết thỏa `print(parse(text)) == text` vì cách nhập có thể được chuẩn hóa. Tiêu chí hữu ích hơn là giá trị miền nghiệp vụ được bảo toàn trong độ chính xác đã quy định. Chẳng hạn, số `1,234.5` có thể được in lại thành `1,234.50`.

### `Formatter` khác `Converter` ở đâu?

| Cơ chế | Trách nhiệm điển hình | Có tham số `Locale` trực tiếp? |
| --- | --- | --- |
| `Converter<S,T>` | Đổi kiểu dữ liệu tổng quát, ví dụ mã định danh → đối tượng miền | Không |
| `Formatter<T>` | Đọc/ghi văn bản dành cho người dùng, nhạy với cách biểu diễn theo vùng | Có, ở cả `parse` và `print` |
| `PropertyEditor` | Cơ chế binding cũ của JavaBeans | Không phải lựa chọn ưu tiên cho thiết kế mới có nhiều `Locale` |

`Formatter` cũng có thể dùng cùng các converter khác: Spring gom chúng trong một hệ thống `ConversionService`. Một phép chuyển đổi thuần kỹ thuật, không phụ thuộc cách người dùng viết/đọc chuỗi, thường phù hợp với `Converter` hơn.

## 3. Luồng xử lý trong Spring MVC

Luồng nhập điển hình:

```text
HTTP request (text) + Locale của request
          |
          v
@RequestParam / @ModelAttribute + WebDataBinder
          |
          v
FormattingConversionService
          |
          v
Formatter<Price>.parse(text, locale)
          |
          v
Đối tượng Price trong controller hoặc form model
```

Luồng trình bày dùng chiều ngược lại: khi thành phần view/binding cần một **chuỗi hiển thị**, `FormattingConversionService` có thể gọi `Formatter<Price>.print(price, locale)`.

`WebDataBinder` xử lý binding và chuyển đổi kiểu; khi giá trị không hợp lệ, Spring có thể ghi lỗi chuyển đổi vào `BindingResult` cho form model. Đối với `@RequestParam` bắt buộc, lỗi chuyển kiểu thường dẫn đến lỗi xử lý tham số/bad request. Thông báo thân thiện cho người dùng nên được xây dựng ở tầng controller/view và cơ chế xử lý lỗi, không nhét mọi logic giao diện vào formatter.

`Locale` được xác định từ ngữ cảnh request theo cấu hình giải quyết locale của Spring MVC (ví dụ dựa trên header `Accept-Language`). Ở những nơi không có HTTP request, Spring có thể lấy `Locale` từ `LocaleContextHolder`. Tránh giả định rằng `Locale.getDefault()` của máy chủ chính là locale của từng người dùng.

Một giới hạn quan trọng: `@RequestBody` đọc JSON thường đi qua `HttpMessageConverter` và Jackson. Một `Formatter<T>` đăng ký với MVC **không mặc nhiên đổi cách Jackson đọc/ghi mọi trường JSON**. API trao đổi dữ liệu giữa máy với máy nên dùng quy ước ổn định, chẳng hạn số JSON và ngày ISO 8601.

## 4. Ví dụ Java 17 chạy được: định dạng `Price`

Ta tạo kiểu `Price` bao một `BigDecimal`, chỉ để minh họa **giá trị số có hai chữ số thập phân khi hiển thị**; ví dụ chưa biểu diễn đơn vị tiền tệ. Dùng `BigDecimal` tránh sai số nhị phân của `double` cho dữ liệu cần độ chính xác thập phân.

Tạo dự án Gradle nhỏ với hai tệp sau. Đây là ví dụ độc lập dùng Spring Framework 6.2.8; trong ứng dụng Spring Boot thật nên để BOM/Boot quản lý phiên bản dependency thay vì tự cố định phiên bản Spring Framework.

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FormatterDemo'
}
```

**`src/main/java/FormatterDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Objects;

import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.context.i18n.LocaleContextHolder;

public class FormatterDemo {

    public record Price(BigDecimal amount) {
        public Price {
            Objects.requireNonNull(amount, "amount");
        }
    }

    public static final class PriceFormatter implements Formatter<Price> {

        private DecimalFormat numberFormat(Locale locale) {
            NumberFormat base = NumberFormat.getNumberInstance(locale);
            if (!(base instanceof DecimalFormat format)) {
                throw new IllegalStateException(
                        "JDK không cung cấp DecimalFormat cho " + locale);
            }
            format.setParseBigDecimal(true);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            format.setRoundingMode(RoundingMode.HALF_UP);
            return format;
        }

        @Override
        public Price parse(String text, Locale locale) throws ParseException {
            if (text == null || text.isBlank()) {
                throw new ParseException("Giá trị không được để trống", 0);
            }
            DecimalFormat format = numberFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            // Không cho phép phần đuôi chưa được phân tích.
            if (!(parsed instanceof BigDecimal amount)
                    || position.getIndex() != text.length()) {
                int index = position.getErrorIndex() >= 0
                        ? position.getErrorIndex() : position.getIndex();
                throw new ParseException("Sai định dạng số: " + text, index);
            }
            return new Price(amount);
        }

        @Override
        public String print(Price value, Locale locale) {
            return numberFormat(locale).format(value.amount());
        }
    }

    public static void main(String[] args) {
        var service = new DefaultFormattingConversionService();
        service.addFormatter(new PriceFormatter());

        try {
            LocaleContextHolder.setLocale(Locale.US);
            Price us = service.convert("1,234.50", Price.class);
            System.out.println(us.amount().toPlainString());
            System.out.println(service.convert(us, String.class));

            LocaleContextHolder.setLocale(Locale.GERMANY);
            System.out.println(service.convert(us, String.class));
            Price de = service.convert("1.234,50", Price.class);
            System.out.println(de.amount().toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Chạy bằng `gradle run --quiet` (hoặc `./gradlew run --quiet` nếu dự án có Gradle Wrapper). Với JDK 17 sử dụng quy tắc số chuẩn của hai locale trên, **stdout**:

```text
1234.50
1,234.50
1.234,50
1234.50
```

Giải thích theo từng bước:

1. `service.addFormatter(...)` đăng ký cả chiều `String → Price` và `Price → String` với conversion service.
2. `LocaleContextHolder.setLocale(Locale.US)` đặt locale cho lượt chuyển đổi hiện tại trong ví dụ không có HTTP request; parser diễn giải dấu phẩy là phân nhóm, dấu chấm là thập phân.
3. Đổi sang `Locale.GERMANY` nhưng giữ **cùng đối tượng** `Price`: `print` xuất `1.234,50`.
4. Nhập chuỗi Đức vào parser cho ra cùng `BigDecimal("1234.50")`.
5. `finally` xóa locale của luồng hiện tại để tránh ảnh hưởng thao tác kế tiếp.

Trong mã production, tách `Price` và `PriceFormatter` thành các lớp ở package nghiệp vụ phù hợp. Ví dụ dùng class lồng nhau chỉ để có thể chạy và quan sát toàn bộ cơ chế trong một tệp Java.

### Vì sao không giữ một `DecimalFormat` dùng chung?

`DecimalFormat` là đối tượng **có trạng thái và không bảo đảm thread-safe**. Bean `Formatter` có thể được chia sẻ giữa nhiều request và locale. Ví dụ tạo một `DecimalFormat` mới cho mỗi lần `parse`/`print`, nên không có biến định dạng mutable dùng chung giữa các luồng. Không cache formatter theo cách bỏ qua locale.

Ví dụ cũng kiểm tra `ParsePosition` để từ chối chuỗi có phần đuôi chưa được đọc như `1,234.50abc`. Tuy vậy, `NumberFormat` có thể khoan dung với một số cách nhóm chữ số. Kiểm tra đã tiêu thụ hết chuỗi **không đồng nghĩa** với kiểm tra mọi quy tắc nghiệp vụ. Nếu miền nghiệp vụ chỉ cho tối đa hai chữ số thập phân hoặc giới hạn giá trị, hãy kiểm tra thêm bằng validation/domain rule thích hợp. Quy tắc làm tròn khi `print` cũng cần được quyết định rõ; nó không tự thay đổi số đang lưu trong đối tượng.

## 5. Tích hợp với Spring MVC

Trong một dự án Spring MVC/Spring Boot có dependency Web MVC, triển khai `WebMvcConfigurer` để đăng ký formatter:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class PriceWebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
    }
}
```

Đoạn tích hợp này **giả định** đã tách `PriceFormatter` của mục 4 thành lớp riêng cùng package/import tương ứng. Đây là minh họa tích hợp, không phải một tệp chạy độc lập. `addFormatters` đăng ký formatter trong conversion service dành cho binding ở Spring MVC; không cần tự gọi `parse` trong mỗi controller.

Ví dụ controller (giả định đã có kiểu `Price` độc lập):

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    @GetMapping("/price")
    public String readPrice(@RequestParam Price price) {
        return price.amount().toPlainString();
    }
}
```

Request minh họa:

```bash
curl -G 'http://localhost:8080/price' \
  -H 'Accept-Language: de-DE' \
  --data-urlencode 'price=1.234,50'
```

Nếu ứng dụng dùng locale request từ `Accept-Language` và đã đăng ký formatter như trên, response body là:

```text
1234.50
```

Phản hồi này trả chuỗi kỹ thuật để kiểm chứng **chiều nhập**. Nó không chứng minh `Formatter.print` tự được gọi khi trả `@ResponseBody`. Muốn in số theo locale trong giao diện, hãy dùng cơ chế render/form binding có hỗ trợ formatting hoặc gọi một dịch vụ định dạng tường minh. Muốn trả dữ liệu JSON/API có cấu trúc, hãy thiết kế DTO và serialization phù hợp.

Với form có `@ModelAttribute`, formatter còn có thể được dùng để chuyển giá trị text field sang `Price`; lỗi binding có thể được xử lý bằng `BindingResult`. Không biến formatter thành nơi truy vấn cơ sở dữ liệu, kiểm tra quyền, hay quyết định dữ liệu có hợp lệ theo mọi luật nghiệp vụ hay không.

## 6. Formatter theo annotation và formatter có sẵn

Spring đã có nhiều bộ định dạng cho số và ngày, nên **không phải lúc nào cũng cần tự viết `Formatter<T>`**.

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class OrderForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate orderDate;

    // getter/setter cho binding của form
}
```

Đây là **đoạn minh họa trường dữ liệu**, chưa phải ứng dụng độc lập: cần getter/setter hoặc cơ chế binding phù hợp. Khi dùng `@NumberFormat`, các ký hiệu phân cách số chịu ảnh hưởng locale, dù pattern mô tả hình dạng định dạng. `@DateTimeFormat(iso = ISO.DATE)` chủ đích sử dụng định dạng ISO (`yyyy-MM-dd`) cho ngày và giảm mơ hồ kiểu `03/04/2026`.

Cách chọn:

- Với số, phần trăm, tiền tệ và ngày đơn giản: xem `@NumberFormat`, `@DateTimeFormat` và formatter tích hợp trước.
- Với **kiểu miền nghiệp vụ tùy chỉnh** có cú pháp nhập/xuất rõ ràng (như `Price`): tự viết `Formatter<Price>`, đăng ký theo field type.
- Khi cách định dạng phụ thuộc annotation riêng gắn trên từng field: cân nhắc `AnnotationFormatterFactory`.
- Khi cần đăng ký một nhóm formatter/converter liên quan: cân nhắc `FormatterRegistrar`.
- Với dữ liệu trao đổi chuẩn giữa hệ thống: ưu tiên định dạng API ổn định; dùng localize tại ranh giới giao diện.

Lưu ý các ô HTML `input type="date"` và `input type="time"` gửi định dạng theo chuẩn HTML, dù nội dung hiển thị trong browser có thể khác theo ngôn ngữ. Không nên ép formatter ngày hiển thị theo locale cho dữ liệu mà browser gửi ở định dạng ISO. Tương tự, việc parse ngày giờ còn cần phân biệt `LocalDate`, thời điểm (`Instant`) và múi giờ (`ZoneId`).

## 7. Kiểm thử và những lỗi thường gặp

Một ma trận kiểm thử tối thiểu cho formatter ví dụ:

| Tình huống | Kỳ vọng |
| --- | --- |
| `parse("1,234.50", Locale.US)` | `Price.amount = 1234.50` |
| `parse("1.234,50", Locale.GERMANY)` | `Price.amount = 1234.50` |
| `print(Price(1234.50), Locale.US)` | `"1,234.50"` |
| `print(Price(1234.50), Locale.GERMANY)` | `"1.234,50"` |
| `parse("1,234.50abc", Locale.US)` | Báo lỗi parse; không âm thầm bỏ `abc` |
| `parse("", Locale.US)` | Báo lỗi parse |
| Nhiều request đồng thời ở các locale khác nhau | Không làm nhiễm định dạng của nhau |

Khi kiểm thử `FormattingConversionService` ngoài web, đặt và khôi phục `LocaleContextHolder` trong từng trường hợp, giống `try/finally` ở ví dụ. Với MVC, kiểm thử tham số HTTP và `Accept-Language` cùng cấu hình locale resolver thực tế.

Những lỗi nên tránh:

1. **Dùng `Double.parseDouble` cho mọi người dùng.** Cách này chỉ hiểu dấu thập phân cố định, không xử lý quy ước locale. Với số tiền, dùng `BigDecimal` theo quy tắc miền nghiệp vụ.
2. **Dùng `Locale.getDefault()` trong formatter** khi request đã có locale riêng. Hãy sử dụng tham số `locale` Spring truyền vào.
3. **Dùng chung `SimpleDateFormat`/`DecimalFormat` mutable** trong bean singleton. Tạo đối tượng mới mỗi lần, hoặc dùng loại formatter immutable/thread-safe khi phù hợp.
4. **Nhầm định dạng với validation.** `Formatter.parse` chỉ đảm nhiệm đọc chuỗi thành kiểu phù hợp; giới hạn âm/dương, khoảng giá trị, số chữ số, quyền thao tác... cần kiểm tra bằng domain validation/Bean Validation hoặc quy tắc bổ sung.
5. **Đổi quy tắc theo locale trong payload JSON công khai.** Các ứng dụng tiêu thụ API có thể không biết locale và không phân tích được chuỗi. Dùng kiểu dữ liệu và chuẩn biểu diễn ổn định.
6. **Bỏ qua các biến thể JDK/CLDR.** Format theo style có thể thay đổi giữa phiên bản JDK hoặc dữ liệu locale. Với giao thức, file trao đổi hoặc dữ liệu lưu trữ, dùng ISO hay pattern được kiểm soát và test rõ ràng.

### Tự kiểm tra kiến thức

- Nếu cùng `Price(1234.50)` được hiển thị cho người dùng Mỹ và Đức, **giá trị trong bộ nhớ** có cần đổi không? Không: chỉ chuỗi tạo ra bởi `print` đổi theo locale.
- Nếu server nhận `"1.234,50"` nhưng parser chạy với `Locale.US`, lỗi nằm ở đâu? Cần kiểm tra cơ chế chọn locale của request, formatter đăng ký và quy ước đầu vào; không sửa bằng cách thay chuỗi tùy tiện.
- Nếu controller nhận JSON `{ "amount": 1234.50 }`, liệu MVC `Formatter<Price>` tự quyết định JSON serializer không? Không: đó là pipeline message conversion/Jackson riêng.
- Khi nào `Converter` phù hợp hơn? Khi chuyển kiểu không có quy tắc trình bày phụ thuộc locale, ví dụ chuyển mã enum hoặc định danh nội bộ.

## 8. Tài liệu tham khảo

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `Printer`, `Parser`, đăng ký và annotation.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): cấu hình formatter trong Spring MVC và lưu ý các trường HTML date/time.
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): ngữ cảnh chung của binding và chuyển đổi kiểu.

Điểm cần ghi nhớ khi áp dụng: `Formatter<T>` giữ nguyên ý nghĩa của đối tượng miền nghiệp vụ trong khi diễn giải hoặc trình bày văn bản theo `Locale`; nó vận hành qua `ConversionService` trong các ngữ cảnh binding phù hợp.