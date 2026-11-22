# Thiết kế converter thuần và an toàn khi chạy đồng thời trong Spring

## 1. Vì sao converter cần thuần và an toàn đa luồng?

Trong Spring, một **converter** chuyển dữ liệu từ kiểu nguồn sang kiểu đích. Ví dụ, một chuỗi mã sản phẩm thành value object `ProductCode`, một chuỗi số thành `Integer` hoặc một chuỗi ngày theo hợp đồng đầu vào thành `LocalDate`. Converter thường được đăng ký vào `ConversionService` để nhiều thành phần trong ứng dụng dùng lại.

Khi ứng dụng Spring chạy web, cùng một converter đã đăng ký có thể được gọi từ nhiều request gần như đồng thời. Nếu converter lưu trạng thái của lần gọi trước trong field mutable, hoặc dùng một đối tượng không an toàn đa luồng, các request có thể làm nhiễu dữ liệu của nhau.

Ví dụ nguy hiểm:

~~~java
public class UnsafeConverter implements Converter<String, String> {
    private String lastValue;

    @Override
    public String convert(String source) {
        lastValue = source;
        return lastValue.trim();
    }
}
~~~

Trong ví dụ này, hai thread có thể đồng thời ghi `lastValue`. Thread A ghi dữ liệu của request A, thread B ghi đè bằng dữ liệu request B, rồi A đọc phải giá trị B. Kết quả phụ thuộc lịch thực thi; lỗi có thể hiếm gặp và khó tái hiện.

Một converter tốt thường có các đặc điểm:

- **Stateless:** không giữ dữ liệu riêng của từng lần chuyển đổi trong field có thể thay đổi.
- **Pure theo nghĩa thực hành:** kết quả phụ thuộc vào đầu vào và quy tắc rõ ràng; không gây side effect như ghi database, gọi HTTP hoặc cập nhật trạng thái dùng chung.
- **Deterministic:** cùng một input và cùng cấu hình trả cùng kết quả.
- **Thread-safe:** nhiều thread có thể gọi đồng thời mà không làm sai kết quả hoặc phá hỏng trạng thái chung.
- **Có hợp đồng lỗi rõ:** định nghĩa cách xử lý null, chuỗi rỗng, whitespace, format sai và giá trị ngoài miền.
- **Nhẹ:** tránh I/O, lock kéo dài hoặc công việc đắt đỏ trong một phép chuyển đổi đơn giản.

Các thuộc tính này liên quan nhưng không đồng nhất. Một converter không giữ state có thể vẫn không an toàn nếu nó sử dụng singleton mutable bên ngoài. Một converter thread-safe cũng có thể không pure nếu nó gửi event hoặc ghi log. Mục tiêu là thiết kế phép chuyển đổi ngắn, dễ dự đoán và độc lập với vòng đời request.

## 2. Hợp đồng Converter của Spring

SPI thông dụng trong Spring Core:

~~~java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
~~~

`S` là kiểu nguồn, `T` là kiểu đích. Converter được đăng ký trong `ConverterRegistry` hoặc một `ConversionService` thích hợp. Ví dụ:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToProductCode());

ProductCode code = service.convert("sku-a123", ProductCode.class);
~~~

Đây là snippet tích hợp với Spring Core, cần dependency `spring-core` và import tương ứng. Với conversion service đã được cấu hình và chia sẻ trong ứng dụng, nhiều luồng xử lý có thể cùng yêu cầu chuyển đổi.

### 2.1. Converter không phải nơi lưu dữ liệu của request

Không đưa các thông tin sau vào instance field mutable của converter:

| Trạng thái không nên lưu | Vì sao |
| --- | --- |
| Giá trị input gần nhất | Request khác có thể ghi đè |
| `Locale` của request hiện tại | Locale thuộc ngữ cảnh từng request |
| User hiện tại / tenant hiện tại | Không được giữ identity của request trước |
| `BindingResult` / `WebDataBinder` | Các đối tượng này gắn với một lần binding |
| Buffer dùng chung có thể thay đổi | Nhiều thread có thể cùng sửa |
| Bộ đếm hoặc cache mutable tự viết | Cần đồng bộ/chiến lược thread-safe riêng, thường nằm ngoài converter |

Dữ liệu bất biến, hằng số và cấu trúc lookup bất biến thường phù hợp hơn:

~~~java
private static final Set<String> ALLOWED =
        Set.of("NEW", "PAID", "CANCELLED");
~~~

`Set.of` tạo tập không thể thay đổi. Tuy nhiên, nếu các phần tử bên trong là object mutable thì toàn bộ cấu trúc chưa chắc bất biến sâu. Ưu tiên kiểu value object immutable và không chia sẻ object có thể bị thay đổi sau khi đưa vào lookup.

### 2.2. Pure conversion: input → output hoặc lỗi

Một converter có thể được xem là pure theo nghĩa thực hành khi:

- Đọc input, kiểm tra, chuẩn hóa theo quy tắc đã xác định.
- Tạo ra value object mới hoặc trả kiểu immutable.
- Không thay đổi input.
- Không phụ thuộc thời gian, mạng, database, random hay state dùng chung.
- Không sửa cấu hình dùng chung trong lúc convert.
- Không có kết quả phụ thuộc vào request đến trước đó.

Ví dụ:

~~~java
public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}
~~~

Với cùng chuỗi đầu vào, kết quả luôn là cùng mã chuẩn hóa. `Locale.ROOT` làm quy tắc uppercase không phụ thuộc locale của người dùng hoặc thiết lập máy chủ.

Tuy nhiên, pure không có nghĩa mọi đầu vào phải được chấp nhận. Input sai có thể ném một exception có ý nghĩa. Một phép chuyển đổi thuần vẫn có thể thất bại theo hợp đồng đã định trước.

## 3. Vì sao converter Spring có thể được gọi đồng thời?

Trong ứng dụng Spring, conversion service hoặc registry thường được cấu hình lúc khởi động rồi được nhiều thành phần sử dụng. Một converter đã đăng ký có thể được gọi từ:

- Spring MVC khi bind query parameter, path variable hoặc form field.
- `DataBinder` / `WebDataBinder` khi gán property.
- Thành phần Spring khác có dùng `ConversionService`.
- Code ứng dụng gọi trực tiếp `conversionService.convert(...)`.
- Nhiều request xử lý trên các thread khác nhau.

Không nên phụ thuộc vào giả định “một request gọi converter tại một thời điểm”. Servlet container thường xử lý nhiều request song song, và cùng một singleton bean có thể được gọi từ nhiều thread.

Ví dụ một converter được đăng ký bằng bean:

~~~java
@Configuration
public class ConversionConfig {

    @Bean
    Converter<String, ProductCode> productCodeConverter() {
        return new StringToProductCode();
    }
}
~~~

Snippet này minh họa bean trong Spring container. Nếu converter là singleton (mặc định của bean scope thông thường), cùng một instance được tái sử dụng. Điều đó **không tự làm converter thread-safe**; chính cách triển khai mới quyết định.

Không cần tạo một converter mới cho mỗi request chỉ để tránh race condition. Hãy loại bỏ mutable shared state và dùng các collaborator an toàn đa luồng.

## 4. Ví dụ hoàn chỉnh: converter immutable và chạy đồng thời

Ví dụ dưới đây dùng Java 17+, Spring Core 6.2.12 và Gradle. Chương trình tạo một converter stateless, đăng ký một lần vào `DefaultConversionService`, rồi nhiều thread đồng thời chuyển các mã sản phẩm. Chương trình xác minh rằng mỗi đầu ra vẫn tương ứng chính xác với input của task đó.

### 4.1. Định nghĩa value object

File `src/main/java/ProductCode.java`:

~~~java
import java.util.Locale;
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        Objects.requireNonNull(value, "value must not be null");

        if (!value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-[A-Z0-9]{4}");
        }
    }

    public static ProductCode fromInput(String raw) {
        Objects.requireNonNull(raw, "raw must not be null");
        return new ProductCode(
                raw.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Record tạo accessor và equality dựa trên component. Field `value` là final; không có setter. Factory method chuẩn hóa chuỗi theo một quy tắc rõ ràng trước khi tạo mã.

Lớp vẫn xác thực định dạng trong compact constructor. Điều này bảo vệ invariant ngay cả khi ai đó tạo `new ProductCode("bad")` mà không thông qua converter.

### 4.2. Viết converter không giữ state

File `src/main/java/StringToProductCode.java`:

~~~java
import java.util.Objects;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        Objects.requireNonNull(source, "source must not be null");
        return ProductCode.fromInput(source);
    }
}
~~~

Converter không có instance field. Mỗi lần gọi chỉ đọc đối số `source` và trả value object mới. `Objects.requireNonNull` làm rõ lỗi null; trong các luồng Spring thông thường, `ConversionService` có quy tắc xử lý null riêng, nhưng code gọi trực tiếp converter vẫn cần một hợp đồng rõ ràng.

Không cần `synchronized` vì không có mutable shared state. Thêm khóa vào converter stateless chỉ gây overhead mà không giải quyết vấn đề nào.

### 4.3. Chạy nhiều task đồng thời

File `src/main/java/ConcurrentConversionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.core.convert.support.DefaultConversionService;

public final class ConcurrentConversionDemo {

    public static void main(String[] args) throws Exception {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new StringToProductCode());

        int taskCount = 1_000;
        ExecutorService executor =
                Executors.newFixedThreadPool(8);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < taskCount; i++) {
                final int number = i;

                tasks.add(() -> {
                    String input = String.format(" sku-%04d ", number);
                    ProductCode converted =
                            service.convert(input, ProductCode.class);

                    String expected =
                            String.format("SKU-%04d", number);

                    if (!expected.equals(converted.value())) {
                        throw new IllegalStateException(
                                "Expected " + expected
                                        + " but got " + converted.value());
                    }

                    return converted.value();
                });
            }

            List<Future<String>> results =
                    executor.invokeAll(tasks);

            for (Future<String> result : results) {
                result.get();
            }

            System.out.println("tasks=" + results.size());
            System.out.println("allConversionsCorrect=true");
            System.out.println("first=" + results.get(0).get());
            System.out.println("last="
                    + results.get(results.size() - 1).get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'concurrent-converter-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.12'
}

application {
    mainClass = 'ConcurrentConversionDemo'
}
~~~

Chạy bằng JDK 17+:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Khi cần tải dependency, máy phải truy cập Maven Central.

Stdout chính xác từ chương trình:

~~~text
tasks=1000
allConversionsCorrect=true
first=SKU-0000
last=SKU-0999
~~~

`invokeAll` trả danh sách Future theo thứ tự danh sách task được truyền vào, không phải thứ tự thread hoàn tất. Vì vậy `first` và `last` vẫn lần lượt là task số 0 và 999 dù các task có thể chạy đồng thời hoặc hoàn tất theo thứ tự khác.

Ví dụ là một stress check nhỏ hữu ích để phát hiện kiểu lỗi lưu trạng thái dùng chung; nó **không phải bằng chứng hình thức** rằng mọi hệ thống đều không có race condition. Để tin cậy hơn, cần test với nhiều input, nhiều thread, vòng lặp dài hơn, các edge case và mọi collaborator mà converter thật sự sử dụng.

## 5. Mẫu converter không an toàn và cách sửa

### 5.1. Lỗi 1: giữ giá trị gần nhất trong field

Không an toàn:

~~~java
public class LastValueConverter
        implements Converter<String, ProductCode> {

    private String normalized;

    @Override
    public ProductCode convert(String source) {
        normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}
~~~

Hai thread có thể ghi `normalized` đồng thời. Một thread có thể trả mã được tạo từ input của thread còn lại. Đây là race condition và lỗi data leakage giữa request.

Sửa bằng biến local:

~~~java
@Override
public ProductCode convert(String source) {
    String normalized =
            source.trim().toUpperCase(Locale.ROOT);
    return new ProductCode(normalized);
}
~~~

Biến local thuộc stack frame của từng lần gọi, do đó không được chia sẻ giữa các lần convert. Điều này không làm mọi object mà biến local tham chiếu tới tự động thread-safe; nếu tham chiếu đến shared mutable object bên ngoài, vẫn cần đánh giá.

### 5.2. Lỗi 2: dùng SimpleDateFormat dùng chung

`SimpleDateFormat` là mutable và không an toàn khi nhiều thread cùng sử dụng một instance. Mẫu sau nguy hiểm:

~~~java
public class UnsafeDateConverter {
    private final SimpleDateFormat format =
            new SimpleDateFormat("yyyy-MM-dd");

    public Date parse(String value) throws ParseException {
        return format.parse(value);
    }
}
~~~

Một thread có thể thay đổi trạng thái nội bộ trong khi thread khác parse. Kết quả có thể lỗi, sai ngày hoặc không ổn định.

Ưu tiên `java.time.format.DateTimeFormatter`, vốn immutable và thread-safe:

~~~java
private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ISO_LOCAL_DATE;

public LocalDate parse(String value) {
    return LocalDate.parse(value, FORMAT);
}
~~~

Đây là snippet sử dụng Java Time API. `DateTimeFormatter` có thể được chia sẻ giữa các thread. Với pattern tùy biến, tạo formatter một lần bằng factory và giữ immutable; không sửa formatter trong mỗi request.

### 5.3. Lỗi 3: giữ Locale của request trong singleton

Không an toàn:

~~~java
public class LocaleAwareConverter
        implements Converter<String, BigDecimal> {

    private Locale currentLocale;

    public void setCurrentLocale(Locale locale) {
        this.currentLocale = locale;
    }

    @Override
    public BigDecimal convert(String source) {
        NumberFormat format =
                NumberFormat.getNumberInstance(currentLocale);
        try {
            return new BigDecimal(
                    format.parse(source).toString());
        } catch (ParseException ex) {
            throw new IllegalArgumentException(ex);
        }
    }
}
~~~

`currentLocale` có thể bị request khác thay đổi. Việc người dùng A dùng `vi_VN` và người dùng B dùng `en_US` cùng lúc có thể khiến A parse theo locale của B.

Nếu quy tắc chuyển đổi **phụ thuộc locale**, `Formatter<T>` thường phù hợp hơn `Converter<S,T>` vì `Formatter` nhận `Locale` trực tiếp trong `parse(String, Locale)` và `print(T, Locale)`. Không đưa locale vào singleton converter bằng setter theo từng request.

Nếu format của API là cố định, hãy khai báo hợp đồng cố định (ví dụ ISO date hoặc số dùng dấu chấm thập phân) và dùng parser phù hợp. Không đọc default locale hệ thống mỗi lần convert nếu cùng input cần có kết quả ổn định giữa môi trường.

### 5.4. Lỗi 4: dùng shared mutable cache không có đồng bộ

Ví dụ:

~~~java
private final Map<String, ProductCode> cache = new HashMap<>();
~~~

`HashMap` mutable không được thiết kế cho nhiều thread đọc/ghi đồng thời. Nếu thực sự cần cache, hãy chọn giải pháp cache thread-safe phù hợp và xác định:

- Key có bao hàm mọi yếu tố làm thay đổi kết quả không?
- Có cần giới hạn kích thước/TTL không?
- Có cho phép nhiều thread cùng tính lại một key không?
- Cache có thể giữ dữ liệu nhạy cảm không?
- Cách cập nhật, eviction và quan sát hiệu năng?
- Cache failure có làm đổi semantics của phép conversion không?

Tuy vậy, converter thường là nơi không phù hợp để thêm cache. Phép chuyển chuỗi sang value object nhỏ thường rẻ; cache tăng độ phức tạp, bộ nhớ và trạng thái dùng chung. Chỉ thêm cache sau khi profiling chứng minh cần thiết.

### 5.5. Lỗi 5: gọi repository hoặc HTTP client trong convert

Một converter như:

~~~java
Product product = productRepository.findByCode(source);
~~~

đã biến phép chuyển kiểu thành thao tác truy cập hệ thống bên ngoài. Điều này dẫn tới:

- Độ trễ database/network trong quá trình bind request.
- Khó phân biệt lỗi parsing với lỗi hạ tầng.
- Lặp truy vấn khi một form có nhiều field/validation path.
- Khó kiểm soát transaction, authorization và tenant.
- Kết quả conversion phụ thuộc trạng thái hệ thống tại thời điểm gọi.
- Khó test đồng thời và khó tái hiện.

Converter phù hợp để parse/normalize **giá trị biểu diễn** thành kiểu Java. Tra cứu entity theo ID/code thuộc service hoặc application layer. Sau khi convert ra một key/value object, controller/service gọi repository trong bước rõ ràng và xử lý not-found theo nghiệp vụ.

## 6. Phân biệt Converter, Formatter và PropertyEditor

| Thành phần | Đặc điểm | Lựa chọn khi |
| --- | --- | --- |
| `Converter<S,T>` | Một chiều, kiểu nguồn và đích rõ | Chuyển kiểu domain/pure parsing không phụ thuộc locale |
| `ConverterFactory<S,R>` | Tạo converter cho một họ kiểu đích | Nhiều kiểu đích liên quan cùng một nguồn |
| `GenericConverter` | Chuyển đổi dựa trên cặp kiểu và TypeDescriptor | Quy tắc phụ thuộc generic hoặc annotation |
| `Formatter<T>` | Parse và print, có Locale | Dữ liệu hiển thị theo ngôn ngữ/định dạng |
| `PropertyEditor` | API JavaBeans cũ, có trạng thái và text representation | Chỉ khi cần tương thích cơ chế cũ; hạn chế chia sẻ instance |

`Converter` thường đơn giản và không giữ locale. `Formatter` truyền locale vào từng lần parse/print nên tránh phải lưu locale của request trong instance. `PropertyEditor` thường có state nội bộ (ví dụ text value), vì vậy không nên tự tạo singleton editor dùng chung giữa các request; binder tạo/quản lý editor theo phạm vi thích hợp.

Chọn SPI theo ngữ nghĩa thay vì cố dùng một `Converter` cho mọi nhu cầu. Ví dụ parse mã hàng có quy tắc cố định là converter hợp lý; parse ngày theo locale người dùng thường là formatter tốt hơn.

## 7. Nguyên tắc về null, rỗng, whitespace và lỗi

Một converter thuần phải có hợp đồng đầu vào rõ. Không nên tùy tiện coi tất cả trường hợp là giống nhau.

| Input | Câu hỏi cần quyết định |
| --- | --- |
| `null` | Caller/conversion service có xử lý null trước không? Converter trực tiếp có ném NPE hay cho phép null? |
| `""` | Rỗng có phải thiếu giá trị, hay là một giá trị không hợp lệ? |
| `"   "` | Có trim không? Sau trim có xem như rỗng không? |
| Chữ hoa/thường | Có canonicalize không? Quy tắc có phụ thuộc locale không? |
| Ký tự Unicode | Có chuẩn hóa Unicode hay chỉ giới hạn ASCII? |
| Giá trị vượt miền | Ném lỗi parse/validation nào? |
| Leading zero | Có giữ nguyên không? Ví dụ mã định danh "0007" có khác "7"? |

Đừng trim mọi chuỗi một cách máy móc. Với mã sản phẩm, trim có thể là quy tắc mong muốn. Với mật khẩu, token hoặc giá trị ký số, trim có thể thay đổi dữ liệu hợp lệ. Với mã có leading zero, đừng chuyển qua integer vì sẽ làm mất thông tin.

### 7.1. Exception có ý nghĩa

Một converter có thể ném `IllegalArgumentException` hoặc exception phù hợp khi input không hợp lệ; `ConversionService`/binder sẽ xử lý tùy đường gọi. Với Spring MVC, lỗi conversion khi bind thường được biểu diễn dưới dạng binding error; controller có thể nhận `BindingResult` cho một `@ModelAttribute` phù hợp.

Nên tạo thông báo lỗi đủ rõ cho developer nhưng không đưa dữ liệu bí mật vào message. Không bắt mọi exception rồi trả null:

~~~java
// Tránh: che lỗi đầu vào sai và tạo trạng thái không rõ ràng
try {
    return parse(source);
} catch (RuntimeException ex) {
    return null;
}
~~~

Trả null có thể khiến hệ thống hiểu nhầm input lỗi là field bị bỏ trống. Hãy giữ sự khác biệt giữa “không có giá trị” và “giá trị không parse được”.

## 8. Registration trong Spring MVC và Spring Boot

### 8.1. Đăng ký thông qua WebMvcConfigurer

Ví dụ tích hợp trong ứng dụng MVC:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCode());
    }
}
~~~

`addFormatters` được Spring MVC dùng để đăng ký converter/formatter vào conversion service của MVC. Converter nên đã được khởi tạo hoàn chỉnh trước khi đăng ký. Không sửa cấu hình registry trong lúc request đang dùng conversion service.

Trong một ứng dụng Spring Boot MVC, có thể cấu hình thông qua `WebMvcConfigurer` mà không cần tự thay thế toàn bộ MVC auto-configuration. Nếu tự khai báo `ConversionService` hoặc mở rộng MVC quá mức, cần kiểm tra xem có làm mất các formatter/converter mặc định hay cấu hình Boot khác không.

### 8.2. Đăng ký Converter như bean

Trong một số cấu hình, converter có thể được khai báo là Spring bean và được phát hiện/đăng ký theo cơ chế cấu hình tương ứng. Không nên dựa vào việc chỉ có bean type `Converter` thì mọi loại Spring conversion path sẽ tự động nhận, nếu tài liệu cấu hình ứng dụng không xác nhận điều đó. Với MVC, cách rõ ràng là đăng ký qua `FormatterRegistry` của `WebMvcConfigurer`.

Nếu cần inject dependency vào converter, có thể tạo bean qua cấu hình:

~~~java
@Bean
StringToProductCode stringToProductCode() {
    return new StringToProductCode();
}
~~~

Ví dụ converter thuần ở trên không cần dependency. Nếu converter cần một cấu hình bất biến, inject cấu hình ở constructor và giữ final; không dùng setter thay đổi sau khi bean đã được chia sẻ.

### 8.3. Scope không phải cách chữa stateful design

Thay singleton converter bằng prototype/request scope chỉ để tránh race condition thường không phải giải pháp tốt:

- Có thể làm integration phức tạp và không đúng vòng đời mà conversion service cần.
- Scope mới không loại bỏ mutable state ở các collaborator được chia sẻ.
- Tạo instance liên tục không giải quyết side effects hoặc logic phụ thuộc request.
- Converter stateless có thể dùng chung hiệu quả và dễ test hơn.

Hãy dùng scope theo yêu cầu thật của object. Với converter chuyển đổi giá trị, thiết kế stateless gần như luôn là điểm khởi đầu phù hợp.

## 9. Những điều không nên làm bên trong convert()

**Không đọc SecurityContext rồi ghi user vào field.** Nếu conversion phụ thuộc principal/tenant, đưa ngữ cảnh một cách tường minh vào tầng nghiệp vụ phù hợp. ThreadLocal context cũng cần được quản lý đúng vòng đời; không lưu nó trên instance converter.

**Không cập nhật database.** Chuyển một chuỗi ID thành typed ID là conversion; tìm entity và kiểm tra quyền là nghiệp vụ.

**Không gọi API bên ngoài.** Network timeout không nên được ngụy trang thành lỗi parse.

**Không phát event hoặc sửa global state.** Những side effects làm retry/test khó dự đoán; thực hiện trong application service.

**Không nuốt lỗi rồi trả giá trị mặc định.** Ví dụ parse chuỗi sai thành 0 có thể làm dữ liệu có vẻ hợp lệ nhưng sai ý nghĩa.

**Không dùng mutable singleton helper.** Kiểm tra cả các object mà converter gọi: parser, formatter, collection, cache và thư viện bên thứ ba.

**Không ghi log toàn bộ raw input không kiểm soát.** Input có thể chứa password, token, PII hoặc chuỗi cực dài. Nếu cần quan sát, log loại lỗi và metadata an toàn, có giới hạn.

## 10. Test converter theo nhiều lớp

### 10.1. Unit test về ngữ nghĩa

Kiểm tra:

- Chuỗi hợp lệ tạo đúng value object.
- Chuẩn hóa whitespace và case theo contract.
- Input sai format gây lỗi như kỳ vọng.
- Null/empty được xử lý theo hợp đồng.
- Cùng input nhiều lần cho kết quả bằng nhau.
- Không có side effect hoặc mutation ở input.

Ví dụ JUnit Jupiter (đặt trong `src/test/java/StringToProductCodeTest.java`):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToProductCodeTest {

    private final StringToProductCode converter =
            new StringToProductCode();

    @Test
    void normalizesValidCode() {
        ProductCode actual = converter.convert(" sku-a123 ");
        assertEquals(new ProductCode("SKU-A123"), actual);
    }

    @Test
    void rejectsInvalidCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("not-a-sku"));
    }

    @Test
    void isDeterministicForSameInput() {
        ProductCode first = converter.convert("sku-b456");
        ProductCode second = converter.convert("sku-b456");
        assertEquals(first, second);
    }
}
~~~

File Gradle thêm dependency JUnit Jupiter và plugin test platform nếu muốn chạy các unit test. Ví dụ trên minh họa assertion; cần cùng package hoặc import class thực tế trong dự án.

### 10.2. Test tính an toàn đồng thời

Không chỉ test converter một lần. Chia sẻ **cùng một instance** qua nhiều task, dùng nhiều input khác nhau và xác minh output tương ứng. Điều này giúp lộ các lỗi kiểu field dùng chung, mutable parser hoặc cache không an toàn.

Có thể mở rộng bài test demo:

- Tăng số task và số vòng lặp.
- Dùng input với các ký tự/biên khác nhau.
- Chạy lặp test nhiều lần trên CI.
- Kiểm tra exception được truyền về caller qua Future.
- Đảm bảo executor được shutdown trong finally.
- Không assert thứ tự hoàn tất task nếu chương trình không kiểm soát scheduler.

Concurrency test vẫn có thể bỏ sót race condition hiếm; kết hợp đọc code, loại bỏ mutable state, và stress test.

### 10.3. Test tích hợp với ConversionService

Tạo conversion service giống cấu hình ứng dụng, đăng ký converter đúng một lần, rồi xác minh:

~~~java
DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new StringToProductCode());

ProductCode result =
        conversions.convert("sku-c789", ProductCode.class);
~~~

Kiểm tra cả code trực tiếp lẫn đi qua conversion service, vì wrapper có thể xử lý null hoặc chọn converter theo type descriptor.

### 10.4. Test Spring MVC

Dùng MockMvc hoặc request thực để test:

- Query/form parameter hợp lệ.
- Parameter không hợp lệ và BindingResult.
- Locale/format nếu dùng Formatter.
- Nhiều request đồng thời gọi cùng endpoint.
- Converter có bị tác động bởi thứ tự request không.
- Exception handler có phản hồi đúng hợp đồng không.

Test MVC giúp phát hiện converter đăng ký nhầm registry, converter bị ghi đè hoặc behavior khác với khi gọi trực tiếp. Không thay integration test bằng unit test thuần khi thay đổi cấu hình framework.

## 11. Thiết kế cho giá trị có locale hoặc tenant

Một converter thuần nên có kết quả ổn định nếu contract là cố định. Nhưng có loại biểu diễn thật sự cần ngữ cảnh, ví dụ tiền tệ hoặc ngày hiển thị:

- Dữ liệu hiển thị theo locale: dùng `Formatter<T>` nhận `Locale` làm tham số, hoặc thực hiện format ở presentation layer.
- Dữ liệu tiền tệ: giữ amount và currency thành kiểu rõ ràng; đừng giả định một số `BigDecimal` tự mang currency.
- Tenant: nếu cùng chuỗi có ý nghĩa khác nhau theo tenant, conversion ở tầng request có thể cần metadata rõ ràng. Tránh đọc tenant vào mutable field của converter.
- Time zone: dùng `ZoneId`/`OffsetDateTime` theo contract; không để timezone máy chủ quyết định parse một cách ngầm định.

Ví dụ formatter immutable có thể dùng `DateTimeFormatter`:

~~~java
public final class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return DateTimeFormatter.ISO_LOCAL_DATE.format(value);
    }
}
~~~

Ví dụ trên chủ ý dùng format ISO nên không phụ thuộc locale, dù SPI vẫn nhận locale. Nếu muốn dùng localized pattern, hãy xây formatter từ locale truyền vào mỗi lần gọi; đừng lưu locale hiện tại trong field. `DateTimeFormatter` là immutable và thread-safe.

## 12. Lựa chọn giữa stateful và stateless

| Tình huống | Khuyến nghị |
| --- | --- |
| Parse mã ID theo regex cố định | Converter stateless |
| Map enum string sang enum | Converter stateless hoặc built-in conversion |
| Parse ngày ISO | Built-in formatter/conversion hoặc formatter immutable |
| Parse ngày theo locale request | Formatter dùng locale parameter |
| Cần DB lookup | Chuyển sang service layer sau khi parse key |
| Cache lookup đắt | Cache ở service/repository layer với policy rõ |
| Cần tenant/user context | Truyền context rõ ở tầng phù hợp; không lưu trên converter |
| Cần per-request mutable state | Gắn với request/binder, không với singleton converter |

Không phải converter nào cũng pure tuyệt đối trong nghĩa toán học. Nhưng phần lớn phép chuyển đổi dữ liệu đầu vào có thể được viết như hàm không trạng thái. Càng ít phụ thuộc bên ngoài, càng dễ kiểm thử, dễ tái sử dụng và ít có khả năng tạo race condition.

## 13. Checklist review một converter trước khi merge

1. Instance field có mutable không? Nếu có, tại sao cần và ai đồng bộ?
2. Kết quả có phụ thuộc input hiện tại hay giá trị của request trước?
3. Có dùng `SimpleDateFormat`, `HashMap` hoặc mutable helper chia sẻ không?
4. Có lưu Locale, user, tenant, request, binder hay BindingResult không?
5. Có gọi database, HTTP, filesystem hoặc phát event không?
6. Có trả kiểu immutable hoặc object không chia sẻ mutable state không?
7. Null, empty, whitespace, invalid format và overflow có contract rõ không?
8. Exception có giữ đúng ngữ nghĩa hay bị nuốt thành null/default?
9. Có test nhiều input và cùng một instance ở nhiều thread không?
10. Converter đã được đăng ký đúng conversion service/formatter registry chưa?
11. Có dùng Formatter thay Converter khi locale là một phần của contract không?
12. Có thể thay conversion bằng service lookup vì logic đã vượt khỏi parse/normalize không?
13. Có log raw input hoặc thông tin nhạy cảm không?
14. Có kiểm tra performance bằng profiling trước khi thêm cache/lock không?

Nếu không thể trả lời rõ một trong các câu về shared state hoặc side effect, hãy xem lại thiết kế trước khi đưa converter vào registry dùng chung.

## 14. Lỗi thường gặp và cách khắc phục

**Kết quả lúc đúng lúc sai khi có traffic cao.** Tìm instance field mutable, buffer, parser hoặc cache dùng chung; viết lại bằng local variable hoặc helper immutable, rồi thêm concurrency test.

**Dùng synchronized nhưng hiệu năng giảm.** Lock có thể che race condition nhưng vẫn giữ thiết kế stateful không cần thiết. Nếu converter chỉ parse input, loại bỏ shared state để không cần lock.

**Converter trực tiếp pass, MVC test fail.** Xác minh converter đã đăng ký trong đúng `FormatterRegistry`/`ConversionService`; request có đi qua MVC binder hay JSON message converter không?

**Locale của user A bị dùng cho user B.** Không giữ locale trong field; dùng `Formatter` với tham số locale hoặc truyền format contract rõ ràng.

**Input sai bị biến thành null.** Không nuốt exception. Phân biệt input absent với input malformed; trả lỗi binding thích hợp.

**Converter gọi database và đôi lúc timeout.** Chỉ parse ID trong converter; tra cứu entity ở service và xử lý not-found/authorization riêng.

**Cache làm dữ liệu cũ.** Xem cache policy, invalidation và consistency; cân nhắc bỏ cache nếu conversion vốn rất rẻ.

**Concurrency test pass nhưng production vẫn lỗi.** Test không chứng minh tuyệt đối. Đọc tất cả collaborator và đảm bảo không có mutable shared state, đồng thời kiểm tra đúng đường tích hợp và version.

## 15. Tài liệu chính thức

- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework – Core Conversion SPI Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework – ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework – ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring Framework – Formatter SPI](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Java – DateTimeFormatter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java – SimpleDateFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html)
- [Java Concurrency Utilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

**Nguyên tắc thiết kế:** hãy coi converter được chia sẻ là một thành phần có thể nhận nhiều lời gọi đồng thời. Giữ instance stateless, dùng biến local và cấu trúc immutable, nhận ngữ cảnh như Locale qua tham số khi phù hợp, và chuyển I/O/tra cứu nghiệp vụ sang service layer. Đó là cách đơn giản nhất để converter có kết quả ổn định, dễ test và an toàn khi ứng dụng xử lý nhiều request cùng lúc.
