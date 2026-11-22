# Cấu hình FormattingConversionService cho nhu cầu nhập và hiển thị

Khi một người dùng nhập `"12,50"` hoặc `"31/12/2026"`, ứng dụng cần **đọc** chuỗi theo quy ước người dùng, chuyển thành kiểu Java phù hợp và có thể **hiển thị lại** dữ liệu theo định dạng mong muốn. Spring Framework cung cấp `FormattingConversionService` để thống nhất hai chiều đó cùng với chuyển đổi kiểu thông thường.

Bài này tập trung vào **cách cấu hình** dịch vụ định dạng cho form, model object và Spring MVC: chọn loại formatter/converter, đăng ký đúng phạm vi, xử lý `Locale`, hỗ trợ annotation trên field, kiểm chứng chiều parse/print và nhận diện lỗi. Các ví dụ dùng Java 17+ và API Spring Framework 6.x.

## 1. Đặt đúng yêu cầu: nhập và hiển thị là hai chiều

Giả sử ứng dụng có thuộc tính số lượng/giá trị thập phân trong model. Người dùng chọn tiếng Đức và nhập `12,50`; đối tượng Java lưu `BigDecimal("12.50")`. Khi hiển thị lại cho người dùng tiếng Anh (Mỹ), giao diện có thể in `12.50`.

```text
NHẬP (client -> model)
"12,50" + Locale.GERMANY
          |
          | Formatter.parse(...) hoặc converter liên quan
          v
        Java object: BigDecimal("12.50")
          |
          | xử lý/validation nghiệp vụ (nếu có)
          v
HIỂN THỊ (model -> client)
Java object + Locale.US
          |
          | Formatter.print(...)
          v
        "12.50"
```

Không nên coi định dạng chuỗi như việc thay đổi giá trị nghiệp vụ. `12,50` và `12.50` là hai cách biểu diễn số 12.5 trong các locale khác nhau. Trong lưu trữ và tính toán, nên dùng kiểu dữ liệu phù hợp (`BigDecimal` cho nhiều bài toán số thập phân chính xác, `LocalDate` cho ngày không có múi giờ, v.v.); format ở ranh giới UI.

Với các field trong Spring MVC, luồng thường là:

1. Request chứa tên field và giá trị văn bản.
2. `WebDataBinder` xác định property/type đích.
3. `ConversionService`/`Formatter` parse giá trị theo kiểu và `Locale`.
4. Binder gán giá trị hoặc ghi lỗi chuyển kiểu vào `BindingResult`.
5. Validation được kích hoạt khi có cấu hình/yêu cầu tương ứng.
6. Form view dùng cơ chế field binding của Spring để hiển thị lại giá trị với formatter thích hợp.

**Hai chiều không có nghĩa hoàn toàn đối xứng với mọi đầu vào.** Formatter có thể chuẩn hóa cách in (ví dụ nhập `12,5` nhưng in `12,50`). Quy tắc làm tròn, độ chính xác và các dạng đầu vào được chấp nhận phải được xác định rõ.

## 2. Những thành phần tham gia

| Thành phần | Vai trò | Khi dùng |
| --- | --- | --- |
| `Converter<S,T>` | Chuyển đổi một kiểu sang kiểu khác, không trực tiếp nhận `Locale` | `String -> Enum`, `String -> ID`, `Long -> Instant` với quy ước rõ |
| `Printer<T>` | Chuyển giá trị có kiểu thành `String` cho UI | In ngày, số, mã trình bày |
| `Parser<T>` | Parse `String` thành giá trị có kiểu | Đọc văn bản nhập của người dùng |
| `Formatter<T>` | Kết hợp `Printer<T>` và `Parser<T>`, cả hai nhận `Locale` | Số, ngày và giá trị hiển thị phụ thuộc vùng/ngôn ngữ |
| `ConversionService` | API chuyển đổi chung (`convert`, `canConvert`) | Được binder/SpEL hoặc mã ứng dụng sử dụng |
| `FormatterRegistry` | API đăng ký `Converter`, `Formatter`, `Printer`, `Parser`, annotation formatter | Cấu hình tập trung |
| `FormattingConversionService` | `ConversionService` đồng thời là `FormatterRegistry` | Trung tâm cấu hình hai chiều |
| `DefaultFormattingConversionService` | Bản triển khai có sẵn nhiều converter/formatter mặc định | Điểm khởi đầu thông dụng |
| `FormatterRegistrar` | Gói đăng ký một nhóm formatter/converter | Cấu hình ngày/giờ hoặc nhóm định dạng liên quan |

`FormattingConversionService` mở rộng `GenericConversionService` và hiện thực `FormatterRegistry`. Nó cho phép đăng ký cả chuyển kiểu tổng quát lẫn formatter cần `Locale`. Lệnh thường gặp:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new MyConverter());       // Converter<S,T>
service.addFormatter(new MyTypeFormatter());   // Formatter<T>
```

Đây là **mã minh họa API**: `MyConverter` và `MyTypeFormatter` phải có implementation thực. `new DefaultFormattingConversionService()` đã đăng ký nhiều converter, formatter số/ngày và hỗ trợ annotation định dạng thông dụng. Khi chỉ cần thêm một kiểu riêng, **giữ mặc định và thêm formatter của mình** thường là lựa chọn đơn giản, ít gây mất hành vi có sẵn.

Cần phân biệt hai constructor:

- `new DefaultFormattingConversionService()`: đăng ký các converter và formatter mặc định.
- `new DefaultFormattingConversionService(false)`: vẫn đăng ký converter mặc định nhưng **không đăng ký formatter mặc định**; dành cho cấu hình thay thế chủ động. Khi dùng cách này, phải đăng ký lại đúng những formatter/annotation formatter mà ứng dụng cần.

`new FormattingConversionService()` là registry nền để cấu hình thủ công; không nên mặc định nó đã có toàn bộ bộ quy tắc giống `DefaultFormattingConversionService`.

## 3. Đăng ký formatter theo kiểu hoặc theo annotation

`FormatterRegistry` hỗ trợ các hình thức sau:

```java
registry.addFormatter(new QuantityFormatter());
registry.addFormatterForFieldType(Quantity.class, new QuantityFormatter());
registry.addFormatterForFieldAnnotation(new MyAnnotationFormatterFactory());
```

Các class ví dụ là tên minh họa; `QuantityFormatter` được hiện thực đầy đủ ở phần sau.

- **Theo kiểu:** mọi property có kiểu `Quantity` trong phạm vi registry sẽ dùng formatter đăng ký cho kiểu đó khi cần parse/print. `addFormatter(...)` có thể suy ra kiểu `T` từ generic của implementation; `addFormatterForFieldType(...)` ghi rõ kiểu.
- **Theo annotation:** chỉ field/parameter có annotation tương ứng mới nhận quy tắc. Phù hợp khi cùng một kiểu cần nhiều cách định dạng, ví dụ số tiền và số lượng cùng dùng `BigDecimal` nhưng hiển thị khác nhau.
- **Theo nhóm:** `FormatterRegistrar.registerFormatters(FormatterRegistry)` đặt nhiều converter/formatter cùng nhau, giúp cấu hình nhất quán.
- **Tách hai chiều:** `addPrinter(...)` và `addParser(...)` hữu ích khi chỉ cần một hướng; với form nhập và hiển thị đầy đủ, `Formatter<T>` thường rõ ràng hơn.

Tránh đăng ký một formatter áp dụng toàn bộ `String` hoặc `BigDecimal` chỉ để xử lý một field cá biệt, nếu các phần khác trong ứng dụng dùng định dạng khác. Khi cần quy tắc riêng, ưu tiên field annotation, kiểu value object chuyên biệt hoặc phạm vi binder thích hợp.

## 4. Ví dụ Java 17+ chạy độc lập với Spring: locale cho parse và print

Ví dụ dùng một value object `Quantity` để thấy rõ cách một `Formatter<Quantity>` hoạt động qua `DefaultFormattingConversionService`. Với `Locale.GERMANY`, dấu phẩy là dấu thập phân; với `Locale.US`, dấu chấm là dấu thập phân.

Tạo cấu trúc Maven:

```text
formatting-demo/
├── pom.xml
└── src/main/java/FormattingServiceDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>formatting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

Nội dung `src/main/java/FormattingServiceDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormattingServiceDemo {
    // Kiểu đích chứa dữ liệu đã parse; không giữ nguyên dấu phẩy/dấu chấm của UI.
    public record Quantity(BigDecimal value) {}

    public static final class QuantityFormatter implements Formatter<Quantity> {
        private DecimalFormat decimalFormat(Locale locale) {
            // Mỗi lần gọi dùng instance mới vì DecimalFormat không thread-safe.
            DecimalFormat format =
                    (DecimalFormat) NumberFormat.getNumberInstance(locale);
            format.setParseBigDecimal(true);
            format.setGroupingUsed(false);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            return format;
        }

        @Override
        public Quantity parse(String text, Locale locale) throws ParseException {
            DecimalFormat format = decimalFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            // Parse phải tiêu thụ toàn chuỗi để tránh chấp nhận phần dư.
            if (!(parsed instanceof BigDecimal number)
                    || position.getIndex() != text.length()) {
                throw new ParseException("Invalid quantity: " + text, 0);
            }
            // Quy ước của ví dụ: tối đa hai chữ số thập phân.
            if (number.scale() > 2) {
                throw new ParseException("Too many decimal places: " + text, 0);
            }
            return new Quantity(number);
        }

        @Override
        public String print(Quantity quantity, Locale locale) {
            return decimalFormat(locale).format(quantity.value());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(new QuantityFormatter());

        try {
            LocaleContextHolder.setLocale(Locale.GERMANY);
            Quantity quantity = service.convert("12,50", Quantity.class);

            System.out.println("internal=" + quantity.value().toPlainString());
            System.out.println("display.de=" + service.convert(quantity, String.class));

            LocaleContextHolder.setLocale(Locale.US);
            System.out.println("display.us=" + service.convert(quantity, String.class));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Chạy trong thư mục `formatting-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=FormattingServiceDemo
```

Các dòng do chương trình in ra:

```text
internal=12.50
display.de=12,50
display.us=12.50
```

Đọc ví dụ theo từng trách nhiệm:

1. `Quantity` là kiểu model; `BigDecimal` giữ phần số thập phân độc lập cách hiển thị.
2. `QuantityFormatter.parse` chuyển chuỗi của locale hiện tại thành `Quantity`.
3. `QuantityFormatter.print` xuất chuỗi của locale hiện tại từ `Quantity`.
4. `service.addFormatter(...)` đăng ký hai chiều cho kiểu `Quantity`.
5. `service.convert(...)` sử dụng adapter formatter thích hợp khi chuyển giữa `String` và `Quantity`.
6. `LocaleContextHolder.setLocale(...)` mô phỏng locale đang hoạt động để ví dụ cho kết quả xác định. Trong request MVC bình thường, Spring tích hợp locale của request vào ngữ cảnh xử lý; trong test hoặc mã tự vận hành nên thiết lập/khôi phục ngữ cảnh cẩn thận.

**Phạm vi của demo:** `setGroupingUsed(false)` nhằm loại bỏ dấu phân nhóm hàng nghìn và giúp output rõ ràng; nó không đại diện cho mọi quy tắc nhập số quốc tế. Quy tắc “tối đa hai chữ số thập phân” thuộc thiết kế ví dụ; ứng dụng thực tế cần xác định thêm min/max, dấu âm, làm tròn, đơn vị và chính sách sai dữ liệu. `DecimalFormat` không an toàn để dùng chung giữa các thread; ví dụ luôn tạo instance mới.

Nếu sửa `"12,50"` thành `"abc"` khi dùng `Locale.GERMANY`, `parse` không thành công; khi sử dụng `ConversionService.convert` trực tiếp, lỗi sẽ được phát sinh tới caller dưới dạng exception chuyển đổi (với nguyên nhân parse liên quan). Nếu thao tác diễn ra qua `DataBinder`, lỗi thường được biểu diễn trong `BindingResult`.

## 5. Đăng ký trong ứng dụng Spring MVC

Trong một ứng dụng Spring MVC hoặc Spring Boot sử dụng Spring MVC, nơi cấu hình tự nhiên cho formatter phục vụ form là `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Tách Quantity và QuantityFormatter từ ví dụ trước thành class
        // có thể truy cập trong ứng dụng.
        registry.addFormatter(new QuantityFormatter());

        // Ví dụ riêng: định dạng ISO cho nhóm java.time của MVC.
        DateTimeFormatterRegistrar dates = new DateTimeFormatterRegistrar();
        dates.setUseIsoFormat(true);
        dates.registerFormatters(registry);
    }
}
```

Đây là **đoạn cấu hình cho dự án Spring MVC**, không phải file standalone; cần có class `QuantityFormatter` từ phần 4 và dependency `spring-webmvc` (hoặc starter web tương ứng). Đặt `WebFormattingConfig` trong phạm vi component scan của ứng dụng. `addFormatters` cho phép bổ sung converter/formatter vào registry của MVC mà không tự tạo và thay thế toàn bộ dịch vụ mặc định.

Khi chỉ cần custom `Quantity`, bỏ phần `DateTimeFormatterRegistrar` để giữ hành vi ngày/giờ hiện có. `dates.setUseIsoFormat(true)` là một **lựa chọn cấu hình chung cho nhóm ngày/giờ**; hãy áp dụng nếu UI/API mong muốn ISO, không thêm một cách máy móc nếu hệ thống có quy ước khác.

Mã khai báo `@Configuration` thường phù hợp hơn so với mỗi controller tự chuyển chuỗi bằng `replace(",", ".")`, bởi cùng một đăng ký có thể phục vụ nhiều form, giảm lỗi không nhất quán giữa nhập và hiển thị.

### Bean conversionService ở Spring container có giống MVC registry không?

Không hoàn toàn. `ConversionService` của **BeanFactory** dùng cho chuyển đổi khi cấu hình bean/property và các luồng có hỗ trợ; `ConversionService` của **Spring MVC** dùng cho dữ liệu request/model binding. Hai phạm vi có thể được cấu hình khác nhau.

Đối với Spring container, một ví dụ đăng ký bean là:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

@Configuration
class CoreConversionConfig {
    @Bean("conversionService")
    static ConversionService conversionService() {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(new QuantityFormatter());
        return service;
    }
}
```

Đây là đoạn cấu hình phụ thuộc `QuantityFormatter` từ phần 4. Bean có tên `conversionService` là một cách cấu hình `ConversionService` cho Spring container. **Không tự suy ra chỉ khai báo bean đó đã thay registry formatter của Spring MVC trong mọi cấu hình**, đặc biệt khi ứng dụng dùng Spring Boot auto-configuration. Muốn custom form MVC, lựa chọn rõ mục tiêu là `WebMvcConfigurer.addFormatters`.

Nếu ứng dụng dùng cấu hình Spring XML, Spring còn cung cấp `FormattingConversionServiceFactoryBean` với các tập `converters`, `formatters` và `formatterRegistrars`; dùng khi dự án thật sự cần cấu hình declarative.

## 6. Dùng @NumberFormat và @DateTimeFormat thay vì viết formatter riêng

Các kiểu số/ngày thông dụng thường **đã được hỗ trợ**, nên chỉ cần khai báo quy tắc ngay trên field/parameter khi không muốn ảnh hưởng mọi nơi.

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate checkIn;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal budget;

    public LocalDate getCheckIn() { return checkIn; }
    public void setCheckIn(LocalDate checkIn) { this.checkIn = checkIn; }

    public BigDecimal getBudget() { return budget; }
    public void setBudget(BigDecimal budget) { this.budget = budget; }
}
```

Đây là **lớp model** để dùng cùng binder/MVC, không có `main`. Ý nghĩa:

- `@DateTimeFormat(iso = ISO.DATE)`: ngày ở dạng ISO như `2026-12-31`, thích hợp khi input cần biểu diễn nhất quán.
- `@NumberFormat(pattern = "#,##0.00")`: mô tả định dạng số với phần nguyên nhóm và hai chữ số thập phân; dấu thực tế trên giao diện được diễn giải theo `Locale`. Với `Locale.GERMANY`, ví dụ hiển thị có thể là `1.234,50`; với `Locale.US` là `1,234.50`.
- `@NumberFormat(style = NumberFormat.Style.CURRENCY)`: quy tắc in số theo phong cách tiền tệ của locale. Đây là **định dạng hiển thị**, chưa quy định loại tiền, tỷ giá, độ chính xác tài chính hoặc đơn vị nghiệp vụ.
- `@DateTimeFormat(pattern = "dd/MM/yyyy")`: cố định mẫu nhập/in dạng ngày. Nếu dùng cho API công khai hoặc dữ liệu trao đổi giữa hệ thống, ISO thường dễ thống nhất hơn.

**Điểm then chốt:** annotation được xét khi hệ thống có **ngữ cảnh field/parameter và metadata của nó**, như Spring MVC binding. Một lời gọi `service.convert("...", LocalDate.class)` chỉ nhận kiểu nguồn/đích; không cung cấp metadata của field `checkIn` để áp dụng riêng annotation từ `BookingForm`.

Khi cùng một kiểu cần nhiều cách format, annotation trên field phù hợp hơn so với thay formatter toàn cục cho mọi field. Với kiểu value object riêng (`Quantity`), một `Formatter<Quantity>` đăng ký theo kiểu thường tiện lợi.

## 7. Locale: lấy ở đâu, dùng lúc nào, kiểm tra thế nào?

`Formatter<T>` nhận tham số `Locale` ở cả `parse(String, Locale)` và `print(T, Locale)`. Đây là yếu tố khác biệt lớn so với `Converter<S,T>` cơ bản.

Trong Spring MVC, locale thường đến từ cấu hình cơ chế locale của request (ví dụ header `Accept-Language` nếu ứng dụng dùng resolver tương ứng). Trong mã trực tiếp, `FormattingConversionService` thường sử dụng `LocaleContextHolder` để cấp locale cho adapter formatter. Khi viết test, nên **cố định locale** thay vì dựa vào locale của máy chạy CI.

Ví dụ các ca cần kiểm tra:

| Locale | Chuỗi đầu vào | Model kỳ vọng | Chuỗi in lại với hai chữ số |
| --- | --- | --- | --- |
| `Locale.GERMANY` | `12,50` | `BigDecimal("12.50")` | `12,50` |
| `Locale.US` | `12.50` | `BigDecimal("12.50")` | `12.50` |
| `Locale.GERMANY` | `abc` | Parse thất bại | Không thực hiện print |
| `Locale.GERMANY` | `12,345` | Bị ví dụ `QuantityFormatter` từ chối vì >2 chữ số thập phân | Không thực hiện print |

Các dòng này mô tả formatter **của ví dụ phần 4**, không phải lời cam kết rằng mọi formatter mặc định của Spring chấp nhận/từ chối cùng những chuỗi đó.

Các bẫy phổ biến:

- **Dùng dấu phân cách cố định:** tự `replace(",", ".")` phá các trường hợp có dấu nhóm nghìn hoặc locale khác.
- **Không chọn locale rõ ràng trong test:** cùng input có thể cho kết quả khác nhau theo locale mặc định.
- **Giữ trạng thái locale ở ThreadLocal:** khi tự gọi `LocaleContextHolder.setLocale(...)`, dùng `try/finally` để khôi phục, tránh ảnh hưởng lần xử lý/test sau.
- **Chia sẻ `SimpleDateFormat` hoặc `DecimalFormat` mutable:** chúng không an toàn dùng chung giữa thread; dùng instance theo lời gọi hoặc API immutable phù hợp như `java.time.format.DateTimeFormatter`.
- **Không tính đến khác biệt JDK:** các kiểu format theo `FormatStyle`/locale có thể thay đổi theo dữ liệu locale của JDK; định dạng ISO hoặc pattern được kiểm soát cho dữ liệu cần tính ổn định cao.

### HTML date/time input và text input

Với `<input type="text">`, trình duyệt gửi chuỗi mà người dùng nhập, nên parse theo locale/pattern của app rất quan trọng. Nhưng HTML `<input type="date">` gửi giá trị chuẩn dạng `yyyy-MM-dd`, độc lập cách lịch hiển thị theo vùng; `<input type="time">` cũng có quy ước máy đọc riêng của HTML.

Vì vậy, tránh áp một formatter ngày địa phương như `dd/MM/yyyy` cho một field HTML `type="date"` rồi giả định browser sẽ gửi đúng định dạng đó. Có thể cấu hình ISO cho loại field này bằng `@DateTimeFormat(iso = ISO.DATE)` hoặc đăng ký date/time formatter ISO thích hợp. Phân biệt **giá trị giao thức của control** với **cách browser hiển thị control**.

## 8. Gắn với DataBinder và xử lý lỗi nhập

Để mô phỏng binding ngoài web, có thể cấu hình `DataBinder` dùng cùng `FormattingConversionService`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

// QuantityForm là JavaBean có property quantity kiểu Quantity,
// kèm getter/setter; QuantityFormatter từ phần 4.
QuantityForm form = new QuantityForm();
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();
service.addFormatter(new QuantityFormatter());

DataBinder binder = new DataBinder(form, "quantityForm");
binder.setConversionService(service);

MutablePropertyValues values = new MutablePropertyValues();
values.add("quantity", "12,50");

// Cần Locale.GERMANY trong ngữ cảnh đang chạy.
binder.bind(values);
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Dùng fieldErrors/rejectedValue để trả thông báo phù hợp.
}
```

Đây là **đoạn minh họa cách tích hợp**, không phải chương trình chạy độc lập: `QuantityForm` và ngữ cảnh locale cần được khai báo/thiết lập theo ứng dụng. `DataBinder` làm nhiệm vụ gán, `FormattingConversionService` chuyển chuỗi thành `Quantity`, còn `BindingResult` giữ lỗi nếu thất bại.

Nếu người dùng nhập `"abc"`, lỗi parse có thể trở thành lỗi binding của field, thường gắn mã `typeMismatch`; kiểm tra `result.getFieldError("quantity")`. Khi code gọi `ConversionService.convert` trực tiếp thì phải xử lý exception theo cách caller cần; API không tự có `BindingResult`.

**Formatting khác validation:** chuyển được `"0,00"` thành kiểu `Quantity` chưa chứng minh giá trị hợp lệ cho nghiệp vụ. Nếu yêu cầu số lượng >0, kiểm tra qua Spring `Validator`, Jakarta Bean Validation (ví dụ `@DecimalMin` trên field số thích hợp) hoặc service/domain. Việc gọi `DataBinder.bind` trực tiếp không đồng nghĩa `binder.validate()` đã chạy.

**Formatting khác security:** định dạng thành công không cấp quyền ghi property. Form binding từ dữ liệu không tin cậy cần DTO/constructor có danh sách trường phù hợp và, khi áp dụng, cấu hình allowed fields. Không dùng formatter để thay kiểm soát quyền hoặc chống mass assignment.

## 9. Ba mức cấu hình: chọn đúng nơi và tránh tác dụng ngoài ý muốn

| Nhu cầu | Cách cấu hình phù hợp | Lưu ý |
| --- | --- | --- |
| Một đoạn mã hoặc một binder độc lập | Tạo `DefaultFormattingConversionService`, `addFormatter` rồi `binder.setConversionService(...)` | Kiểm soát rõ phạm vi, nên tái sử dụng service sau khi cấu hình |
| Tất cả form Spring MVC cần formatter custom | `WebMvcConfigurer.addFormatters` | Dùng registry của MVC; không tự thay toàn bộ converter mặc định |
| Một field cần pattern riêng | `@NumberFormat` / `@DateTimeFormat` | Ít ảnh hưởng các field cùng kiểu |
| Toàn ứng dụng cần quy tắc ngày/giờ chung | `DateTimeFormatterRegistrar` / `DateFormatterRegistrar` | Phân biệt `java.time` với `java.util.Date`; kiểm tra cả hai chiều |
| Một nhóm formatter tự phát triển | `FormatterRegistrar` | Giảm cấu hình rải rác, giữ nhất quán |
| Dự án Spring XML | `FormattingConversionServiceFactoryBean` | Khai báo converters, formatters và registrars |
| Cần ảnh hưởng chuyển đổi cấu hình bean trong container | Bean có tên `conversionService` | Đối chiếu phạm vi thực tế với registry MVC/Boot |

Với Spring Boot dùng MVC, nên đọc cấu hình MVC hiện có trước khi thêm bean. Boot có các thiết lập `spring.mvc.format.*` cho một số định dạng ngày/giờ thông thường; chúng có phạm vi và quy tắc riêng. Khi chỉ thêm formatter custom, đăng ký qua `WebMvcConfigurer` là cách rõ ràng. Tránh dùng `@EnableWebMvc` chỉ để thêm formatter trong ứng dụng Boot đang dựa vào MVC auto-configuration; annotation này có thể thay đổi cách ứng dụng nhận các cấu hình tự động khác.

### Khi cần thay format ngày/giờ mặc định trên diện rộng

Spring cung cấp cách cấu hình có chủ ý, ví dụ:

```java
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

DefaultFormattingConversionService custom =
        new DefaultFormattingConversionService(false);

DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
registrar.setUseIsoFormat(true);
registrar.registerFormatters(custom);
```

Đây là đoạn cấu hình **chỉ nhằm minh họa cấu trúc API**. Với `false`, các formatter mặc định không được đăng ký: các annotation formatter khác, như `@NumberFormat`, có thể cần bổ sung đăng ký tương ứng. Nếu không có yêu cầu thay thế toàn bộ default, sử dụng `new DefaultFormattingConversionService()` rồi bổ sung quy tắc cụ thể thường an toàn hơn.

Theo tài liệu Spring, khi cần chỉ định format ngày/giờ chung cho `java.time` có `DateTimeFormatterRegistrar`; các kiểu cũ `Date`/`Calendar` có `DateFormatterRegistrar`. Đừng giả định một registrar bao phủ mọi kiểu ngày/giờ.

## 10. Chẩn đoán khi nhập/hiển thị không đúng

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xác minh/sửa |
| --- | --- | --- |
| Nhập `12,50` nhưng lỗi `typeMismatch` | Locale, formatter không đăng ký hoặc không áp dụng đúng field | Kiểm tra locale đang hoạt động, `addFormatters` và `FieldError` |
| Nhập đúng nhưng hiển thị dấu thập phân khác | Locale ở thời điểm print khác parse | Ghi nhận locale của request khi render, test parse/print theo từng locale |
| Có custom formatter nhưng Spring MVC không dùng | Đăng ký trong một `ConversionService` khác registry MVC | Đưa cấu hình vào `WebMvcConfigurer.addFormatters` hoặc nối đúng service |
| Annotation `@DateTimeFormat` dường như vô hiệu | Chuyển trực tiếp không có metadata field, hoặc không dùng binder có annotation support | Kiểm tra đường binding và `TypeDescriptor` của property |
| Ngày form `type="date"` bị báo sai format | Dùng pattern locale cho input yêu cầu ISO | Dùng ISO cho dữ liệu HTML date |
| Đổi format toàn cục làm các form khác hỏng | Formatter đăng ký theo kiểu quá rộng hoặc tắt default | Thu hẹp bằng field annotation/value object; bổ sung lại default cần thiết |
| Dấu nghìn, phần thập phân bị sai | Dùng `replace`/`parseDouble` bất chấp locale | Dùng formatter số và xác định quy tắc grouping/precision |
| Cùng test cho kết quả khác trên CI | Phụ thuộc locale/JDK môi trường | Cố định locale, timezone khi liên quan, mẫu đầu vào và JDK |
| Người dùng nhập sai nhưng trang không hiển thị thông báo | Không dùng `BindingResult` đúng cách hoặc view không render lỗi | Kiểm tra vị trí argument và cơ chế view field errors |
| JSON format khác HTML form | `@RequestBody` đi qua HTTP message converter (thường Jackson) | Cấu hình serializer/deserializer của JSON riêng nếu API cần format đó |

Một quy trình gỡ lỗi ngắn:

1. Xác định **kiểu request**: HTML form/`@ModelAttribute` hay JSON/`@RequestBody`.
2. Ghi nhận **tên field, chuỗi gốc, kiểu đích và `Locale`**.
3. Kiểm tra formatter/converter đã được đăng ký **đúng service/binder** chưa.
4. Thử riêng `String -> T` và `T -> String` trên locale cố định.
5. Kiểm tra `BindingResult` của form để phân biệt lỗi parse với lỗi validation.
6. Kiểm tra form rendering có dùng Spring field binding (ví dụ Thymeleaf `th:field` hoặc Spring form tag) hay chỉ in raw property.
7. Chạy test với các locale cần hỗ trợ, giá trị biên, input rỗng, giá trị sai cú pháp và số có dấu nhóm thập phân.

**Lưu ý về JSON:** `FormattingConversionService` gắn với Spring binding/form; Jackson serialize/deserialize JSON theo cơ chế và cấu hình riêng. Đừng kỳ vọng `@NumberFormat` hoặc một `Formatter<T>` trong MVC tự thay đổi cách JSON được viết ra bởi `@ResponseBody`.

## 11. Câu hỏi tự kiểm tra

**1. Vì sao `Converter<String, BigDecimal>` chưa chắc là giải pháp tốt nhất cho input quốc tế hóa?** Vì converter cơ bản không nhận tham số `Locale`; `Formatter<BigDecimal>` có `parse` và `print` theo locale, phù hợp UI hơn. Nếu đầu vào luôn dùng một chuẩn máy đọc cố định, converter vẫn có thể hợp lý.

**2. Một property `LocalDate` cần nhận `yyyy-MM-dd` từ HTML `type="date"`, chọn gì?** Có thể khai báo `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`; với nhiều field cùng yêu cầu, cấu hình ISO date/time qua registrar thích hợp.

**3. Có `QuantityFormatter` nhưng `controller` vẫn không dùng khi submit. Kiểm tra ở đâu?** Trước hết xem formatter đã đăng ký vào **MVC FormatterRegistry** hay chỉ một bean/service khác; tiếp theo xác minh loại request và kiểu property.

**4. `new DefaultFormattingConversionService(false)` giúp làm gì, cần lưu ý gì?** Tắt đăng ký formatter mặc định để tự quyết quy tắc; phải đăng ký bù formatter/annotation formatter cần dùng và kiểm thử những kiểu bị ảnh hưởng.

**5. Parse thành công `"0,00"` có nghĩa nghiệp vụ chấp nhận không?** Không. Parse xác nhận khả năng biểu diễn và kiểu dữ liệu; validator/domain kiểm tra điều kiện như số lượng dương.

**6. Dùng `@NumberFormat` ở property, rồi gọi trực tiếp `conversionService.convert(text, BigDecimal.class)` có chắc đọc annotation đó không?** Không. Lời gọi này không chỉ ra property mang annotation; binding với metadata field mới tạo điều kiện cho formatter dựa trên annotation hoạt động.

## Tài liệu tham khảo

- [Spring Framework — Field Formatting, Formatter SPI, FormatterRegistry, AnnotationFormatterFactory](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework — Configuring a Global Date and Time Format](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format-configuring-formatting-globaldatetimeformat.html)
- [Spring MVC — Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — DefaultFormattingConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
- [Spring Boot — Servlet Web Applications: Type Conversion and Formatting](https://docs.spring.io/spring-boot/reference/web/servlet.html)
