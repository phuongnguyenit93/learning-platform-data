# ConverterRegistry và đăng ký converter theo cặp kiểu trong Spring Framework

Spring thường nhận dữ liệu ở dạng chuỗi từ form, query parameter hoặc cấu hình, trong khi mã Java cần các kiểu rõ ràng như số, ngày tháng, enum hoặc kiểu miền do ứng dụng tự định nghĩa. **Converter** chịu trách nhiệm chuyển một kiểu nguồn sang kiểu đích. **ConverterRegistry** là giao diện đăng ký các converter vào hệ thống chuyển đổi kiểu của Spring.

Khi hiểu cách khai báo converter và đăng ký đúng cặp kiểu, bạn có thể bổ sung chuyển đổi cho toàn ứng dụng hoặc cho Spring MVC mà không rải logic phân tích chuỗi khắp controller và service.

Bài học tập trung vào:

- Phân biệt `ConverterRegistry` và `ConversionService`.
- Đăng ký converter theo cặp `sourceType → targetType` bằng `addConverter(...)`.
- Đăng ký converter thông qua kiểu generic đã khai báo.
- Chọn `Converter`, `ConverterFactory`, `GenericConverter` hoặc `Formatter`.
- Đưa converter vào Spring Container và Spring MVC bằng Java Configuration.
- Kiểm tra khả năng chuyển đổi, xử lý đầu vào sai và kiểm thử.
- Tránh xung đột converter, mất metadata kiểu và các lỗi cấu hình phổ biến.

## 1. ConverterRegistry là gì?

`org.springframework.core.convert.converter.ConverterRegistry` là **SPI (Service Provider Interface)** quy định cách thêm hoặc gỡ converter khỏi một registry chuyển đổi. Nó tập trung vào thao tác cấu hình:

```java
public interface ConverterRegistry {
    void addConverter(Converter<?, ?> converter);

    <S, T> void addConverter(
            Class<S> sourceType,
            Class<T> targetType,
            Converter<? super S, ? extends T> converter);

    void addConverter(GenericConverter converter);

    void addConverterFactory(ConverterFactory<?, ?> factory);

    void removeConvertible(
            Class<?> sourceType,
            Class<?> targetType);
}
```

Đây là các chữ ký tiêu biểu của API Spring; khi dùng trong mã nguồn cần import đúng package `org.springframework.core.convert.converter.ConverterRegistry`. Hai khái niệm thường đi cùng nhau nhưng có trách nhiệm khác nhau:

| API | Trách nhiệm | Thường được gọi ở đâu? |
| --- | --- | --- |
| `ConverterRegistry` | Đăng ký, gỡ converter và converter factory | Java Configuration, MVC config |
| `ConversionService` | Hỏi có chuyển được không và thực hiện chuyển đổi | DataBinder, controller, service |
| `GenericConversionService` | Cài đặt nền tảng cho cả hai API, cung cấp registry và service | Dùng khi cần tự cấu hình hệ thống chuyển đổi |
| `DefaultConversionService` | Bản cài đặt có sẵn nhiều converter tiêu chuẩn | Ứng dụng thông thường cần chuyển đổi phổ biến |
| `DefaultFormattingConversionService` | Mở rộng hệ thống chuyển đổi với các formatter mặc định | Ứng dụng có cả chuyển đổi và định dạng văn bản |
| `FormatterRegistry` | Registry mở rộng cho formatter và converter | Cấu hình chuyển đổi/định dạng trong MVC |

Một đối tượng triển khai `ConversionService` thường đồng thời triển khai `ConverterRegistry`. Ví dụ `GenericConversionService` là nền tảng chung; `DefaultConversionService` và `FormattingConversionService` kế thừa/cung cấp thêm cấu hình mặc định.

**Cách nhớ:** registry là nơi *đăng ký quy tắc chuyển đổi*; service là nơi *sử dụng quy tắc đó*.

## 2. Cặp kiểu nguồn và kiểu đích

Một converter thông thường khai báo hai tham số generic:

```java
Converter<S, T>
```

Trong đó:

- `S` là kiểu nguồn (source type).
- `T` là kiểu đích (target type).
- `convert(S source)` nhận một đối tượng kiểu nguồn và trả về giá trị kiểu đích.

Ví dụ, nếu request cung cấp chuỗi `"USD"` và ứng dụng dùng kiểu miền `CurrencyCode`:

```text
String "USD"
    |
    v
Converter<String, CurrencyCode>
    |
    v
CurrencyCode("USD")
```

Cặp kiểu `String.class → CurrencyCode.class` xác định lúc nào converter có thể được chọn. Registry không cần đoán ý nghĩa chuỗi: bạn khai báo rõ kiểu đầu vào, kiểu đầu ra và cách chuyển đổi.

Một converter có thể được viết thành lớp:

```java
public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        return new CurrencyCode(source.trim().toUpperCase());
    }
}
```

Đây là đoạn trích; định nghĩa đầy đủ của `CurrencyCode` và kiểm tra đầu vào được trình bày trong ví dụ chạy được ở mục 6.

Một converter cũng có thể được đăng ký với cặp kiểu tường minh:

```java
registry.addConverter(
        String.class,
        CurrencyCode.class,
        new StringToCurrencyCode());
```

Cách này hữu ích khi bạn muốn khai báo rõ cặp nguồn/đích tại nơi đăng ký, hoặc khi cùng một converter cần được liên kết với một cặp kiểu cụ thể. Spring còn có overload nhận trực tiếp converter và suy ra cặp kiểu từ generic đã triển khai.

## 3. Hai cách đăng ký converter

### 3.1. Đăng ký với kiểu generic được khai báo trong lớp

Khi một lớp triển khai `Converter<String, CurrencyCode>`, Spring có thể xác định cặp kiểu từ generic:

```java
ConverterRegistry registry = ...;
registry.addConverter(new StringToCurrencyCode());
```

Đây là cách ngắn gọn, dễ đọc và phù hợp khi converter có một cặp kiểu cố định. Thông tin kiểu phải có thể được xác định từ generic của lớp triển khai. Tránh đăng ký một converter raw type đã xóa generic vì registry có thể không suy ra được cặp kiểu mong muốn.

### 3.2. Đăng ký với cặp kiểu tường minh

Overload thứ hai nhận hai lớp kiểu và một converter:

```java
registry.addConverter(
        String.class,
        CurrencyCode.class,
        new StringToCurrencyCode());
```

Lợi ích của cách này là cặp kiểu được nhìn thấy ngay tại nơi cấu hình. Đặc biệt hữu ích khi dùng converter chung cho một số cặp kiểu hoặc khi muốn tránh phụ thuộc vào việc suy luận generic.

Ví dụ cùng một converter chuẩn hóa mã có thể được tái sử dụng cho nhiều wrapper kiểu miền, nhưng chỉ nên làm vậy khi quy tắc chuyển đổi thực sự giống nhau. Nếu mỗi kiểu có định dạng hoặc quy tắc khác nhau, hãy tạo converter riêng để tên kiểu phản ánh đúng ý nghĩa.

### 3.3. Đăng ký factory hoặc generic converter

Không phải mọi yêu cầu đều chỉ có một cặp kiểu cố định:

- `addConverterFactory(...)` đăng ký `ConverterFactory<S, R>`; factory tạo converter cho nhiều kiểu đích con của kiểu cơ sở `R`. Tình huống điển hình là chuyển chuỗi sang một trong nhiều kiểu enum.
- `addConverter(GenericConverter)` đăng ký converter có thể hỗ trợ nhiều cặp kiểu. `GenericConverter` mô tả các cặp chuyển đổi và nhận `TypeDescriptor` để xem metadata của nguồn/đích, hữu ích khi quyết định chuyển đổi dựa trên annotation hoặc metadata collection.
- `ConditionalConverter` có thể được triển khai bổ sung để chỉ nhận một cặp kiểu khi điều kiện cụ thể thỏa mãn.

Không nên chọn `GenericConverter` chỉ vì nó linh hoạt hơn. Với một cặp kiểu đơn giản, `Converter<S,T>` thường rõ ràng và ít mã nhất.

## 4. ConverterRegistry và ConversionService phối hợp ra sao?

Sau khi converter được đăng ký, ứng dụng thường sử dụng `ConversionService`:

```java
ConversionService service = ...;

boolean supported =
        service.canConvert(String.class, CurrencyCode.class);

CurrencyCode code =
        service.convert("USD", CurrencyCode.class);
```

`canConvert(sourceType, targetType)` kiểm tra khả năng chuyển đổi của service. `convert(source, targetType)` thực hiện chuyển đổi và trả về kiểu đích. Có thêm overload dùng `TypeDescriptor` khi cần giữ metadata về field, generic collection hoặc annotation.

Một ví dụ đường đi:

```text
Java Configuration
      |
      v
ConverterRegistry.addConverter(...)
      |
      v
ConversionService giữ converter đã đăng ký
      |
      +--> canConvert(String, CurrencyCode)
      |
      +--> convert("USD", CurrencyCode)
                    |
                    v
             CurrencyCode("USD")
```

`ConversionService` được thiết kế như một service stateless để khởi tạo lúc ứng dụng bắt đầu và chia sẻ giữa các luồng. Những converter được chia sẻ cũng nên stateless/thread-safe. Không lưu giá trị request, người dùng hiện tại hoặc trạng thái mutable theo request vào field của converter singleton.

### 4.1. Kiểm tra trước khi convert

`canConvert(...)` hữu ích khi ứng dụng cần kiểm tra một cặp kiểu có được hỗ trợ. Nhưng kết quả `true` không bảo đảm mọi giá trị nguồn đều hợp lệ. Ví dụ `String → CurrencyCode` có converter, nhưng chuỗi `"US"` vẫn có thể sai định dạng.

Vì thế cần phân biệt:

1. **Không có converter phù hợp:** service không biết chuyển cặp kiểu đó.
2. **Có converter nhưng dữ liệu cụ thể không hợp lệ:** converter được gọi nhưng từ chối giá trị, thường bằng `IllegalArgumentException`.
3. **Chuyển đổi thành công:** có đối tượng đích phù hợp.

Khi chuyển đổi lỗi thông qua `ConversionService`, Spring thường bọc lỗi converter trong `ConversionFailedException`; ở các lớp binding cao hơn có thể xuất hiện lỗi chuyển kiểu khác. Ở ranh giới ứng dụng, nên ánh xạ lỗi về thông báo rõ ràng và không trả stack trace.

## 5. Chọn đúng loại converter

| Loại | Khi nên dùng | Đặc điểm |
| --- | --- | --- |
| `Converter<S,T>` | Một cặp kiểu nguồn/đích cụ thể | Đơn giản, generic rõ ràng |
| `ConverterFactory<S,R>` | Một kiểu nguồn chuyển sang nhiều kiểu đích cùng họ | Factory trả converter cho kiểu đích con của `R` |
| `GenericConverter` | Nhiều cặp kiểu hoặc cần metadata nguồn/đích | Dùng tập `ConvertiblePair` và `TypeDescriptor` |
| `ConditionalConverter` | Chuyển đổi chỉ hợp lệ khi có điều kiện về metadata | Có thể kết hợp với `GenericConverter` |
| `Formatter<T>` | Chuyển văn bản sang kiểu và in kiểu ra văn bản theo locale | Có cả `parse(...)` và `print(...)` |

### 5.1. Khi nào dùng ConverterFactory?

Ví dụ một ứng dụng nhận chuỗi để tạo enum. Thay vì viết một lớp chuyển đổi cho từng enum cụ thể, có thể dùng một `ConverterFactory<String, Enum>` trả về converter tương ứng với kiểu enum được yêu cầu. Mẫu này phù hợp khi các kiểu đích cùng chia sẻ một cơ chế chuyển đổi.

Tuy nhiên, cần xử lý tên enum sai và định dạng đầu vào có chủ đích. Không giả định chuỗi từ client luôn đúng; `Enum.valueOf(...)` có thể ném `IllegalArgumentException` nếu không tìm thấy hằng phù hợp.

### 5.2. Khi nào dùng GenericConverter?

`GenericConverter` thích hợp khi converter cần biết chi tiết kiểu hơn `Class<?>` đơn thuần. Ví dụ chuyển collection phụ thuộc generic element type, hoặc chỉ hoạt động với field có annotation cụ thể. `TypeDescriptor` có thể biểu diễn loại đối tượng, generic, annotation và metadata liên quan.

Với một cặp đơn giản như `String → CurrencyCode`, không cần tự cài `GenericConverter`; dùng `Converter` rồi đăng ký vào registry.

### 5.3. Khi nào dùng Formatter?

`Converter` thường tập trung chuyển một kiểu sang kiểu khác. `Formatter<T>` được thiết kế cho chuyển đổi văn bản hai chiều: `parse(String, Locale)` để đọc và `print(T, Locale)` để hiển thị. Với ngày, số thập phân và nội dung phụ thuộc locale, formatter thường là lựa chọn tự nhiên hơn.

## 6. Ví dụ hoàn chỉnh: đăng ký Converter<String, CurrencyCode>

Ví dụ này dùng Java 17 và Spring Framework 6.2. Nó tạo một kiểu miền `CurrencyCode`, khai báo converter, đăng ký bằng cặp kiểu rõ ràng, sau đó chuyển đổi hợp lệ và kiểm tra chuỗi không hợp lệ. Chương trình console không cần Spring Boot hoặc HTTP server.

Cấu trúc:

```text
converter-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/conversion/ConverterRegistryDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'converter-registry-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.conversion.ConverterRegistryDemo'
}
```

`spring-context` kéo theo các module cần thiết cho hệ thống convert của Spring. Với dự án Spring Boot hiện có, nên dùng phiên bản dependency do Spring Boot quản lý thay vì đặt một phiên bản Spring độc lập có thể không tương thích với các starter khác.

Tệp `src/main/java/demo/conversion/ConverterRegistryDemo.java`:

```java
package demo.conversion;

import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultFormattingConversionService;

public class ConverterRegistryDemo {

    public record CurrencyCode(String value) {
        public CurrencyCode {
            if (value == null || !Pattern.matches("[A-Z]{3}", value)) {
                throw new IllegalArgumentException(
                        "Currency code must contain exactly three uppercase letters");
            }
        }
    }

    public static final class StringToCurrencyCode
            implements Converter<String, CurrencyCode> {

        @Override
        public CurrencyCode convert(String source) {
            if (source == null) {
                throw new IllegalArgumentException("Source is required");
            }

            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new CurrencyCode(normalized);
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        // Đăng ký tường minh cặp kiểu String -> CurrencyCode.
        service.addConverter(
                String.class,
                CurrencyCode.class,
                new StringToCurrencyCode());

        System.out.println("canConvert="
                + service.canConvert(String.class, CurrencyCode.class));

        CurrencyCode valid =
                service.convert(" usd ", CurrencyCode.class);
        System.out.println("converted=" + valid.value());

        try {
            service.convert("US", CurrencyCode.class);
        } catch (ConversionFailedException exception) {
            System.out.println("invalid=rejected");
        }
    }
}
```

Chạy từ thư mục dự án bằng Gradle đã cài đặt:

```bash
gradle -q run
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew -q run` trên Unix/macOS hoặc `gradlew.bat -q run` trên Windows. Đầu ra do chương trình Java in ra:

```text
canConvert=true
converted=USD
invalid=rejected
```

Giải thích:

- `DefaultFormattingConversionService` đã có các converter và formatter phổ biến; ví dụ chỉ bổ sung một cặp kiểu miền mới.
- `addConverter(String.class, CurrencyCode.class, ...)` đăng ký rõ cặp kiểu nguồn/đích.
- `canConvert(...)` trả `true` vì registry có converter cho cặp kiểu này.
- `" usd "` được trim, chuẩn hóa bằng `Locale.ROOT` và tạo ra `CurrencyCode("USD")`.
- `"US"` có độ dài không hợp lệ, constructor record ném `IllegalArgumentException`. Conversion service bọc lỗi chuyển đổi thành `ConversionFailedException`; chương trình bắt lỗi và in một thông báo ổn định.

Lưu ý `source` mà Spring chuyển cho converter thông thường là khác `null` theo hợp đồng của `Converter`. Kiểm tra `null` trong converter ở ví dụ chỉ là phòng vệ cho việc gọi trực tiếp từ mã Java; trường hợp null trong hệ thống conversion thường được xử lý bởi service và các quy tắc null của framework.

## 7. Đăng ký Converter bằng Java Configuration

Trong ứng dụng Spring, converter nên được đăng ký lúc application context khởi tạo. Có hai tình huống thường gặp: dùng một `ConversionService` cho container và dùng registry mà Spring MVC cung cấp.

### 7.1. Đăng ký bean ConversionService trong Spring Container

Tài liệu Spring quy ước bean chuyển đổi toàn cục có tên `conversionService` để container có thể nhận diện. Một cấu hình có thể là:

```java
package demo.conversion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultFormattingConversionService;

@Configuration
public class ConversionConfiguration {

    @Bean("conversionService")
    public ConversionService conversionService() {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(
                new ConverterRegistryDemo.StringToCurrencyCode());

        return service;
    }
}
```

Đoạn cấu hình giả định lớp `StringToCurrencyCode` được đặt ở package riêng và có thể truy cập từ cấu hình. Ví dụ trên tái sử dụng lớp bên trong `ConverterRegistryDemo` để minh họa; trong dự án thực tế nên tách converter thành class top-level hoặc bean riêng.

Spring có thể dùng bean `conversionService` cho các nhu cầu chuyển đổi của container. Vì phương thức khai báo kiểu trả về `ConversionService` (API sử dụng), nhưng đối tượng thực thi là `DefaultFormattingConversionService` (có registry), cấu hình converter được thực hiện trước khi trả bean.

Không tạo nhiều bean `conversionService` không cần thiết. Một hệ thống nên có chiến lược chuyển đổi nhất quán, và các converter nên được đăng ký lúc khởi tạo thay vì sửa registry tùy ý trong từng request.

### 7.2. Đăng ký converter cho Spring MVC

Khi mục tiêu là form, query parameter hoặc dữ liệu binding của controller MVC, cách mở rộng trực tiếp là triển khai `WebMvcConfigurer` và override `addFormatters(FormatterRegistry registry)`:

```java
package demo.conversion;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new ConverterRegistryDemo.StringToCurrencyCode());
    }
}
```

Spring MVC sử dụng registry này trong hệ thống conversion/formatting của nó. Các tham số như `@RequestParam CurrencyCode currency` hoặc thuộc tính `CurrencyCode` trong đối tượng `@ModelAttribute` có thể nhận chuỗi và chuyển qua converter khi đường xử lý MVC phù hợp.

Trong ứng dụng Spring Boot, thường chỉ cần thêm `WebMvcConfigurer` để mở rộng cấu hình MVC hiện có; không thêm `@EnableWebMvc` chỉ vì muốn đăng ký converter, bởi annotation đó thay đổi cách Boot tự cấu hình MVC. Tránh tạo hai bộ registry riêng rồi giả định converter đăng ký ở một nơi tự động xuất hiện ở nơi khác.

### 7.3. Đăng ký bằng bean Converter được Spring quản lý

Một converter có thể được khai báo như bean riêng:

```java
@Bean
public Converter<String, CurrencyCode> currencyCodeConverter() {
    return new StringToCurrencyCode();
}
```

Tuy nhiên, việc tồn tại một bean `Converter` **không đồng nghĩa** mọi `ConversionService` tự động nhận bean đó trong mọi kiểu ứng dụng. Cách tích hợp phụ thuộc vào cấu hình container, Spring Boot hoặc registry MVC. Nếu bạn cần chắc chắn trong MVC, đăng ký nó trong `addFormatters(...)`; nếu cần service dùng chung, đưa nó vào `conversionService` bean hoặc registry được ứng dụng quản lý.

Trong Spring Boot, cơ chế thu thập converter bean có thể được hỗ trợ bởi cấu hình auto-configuration tương ứng với phiên bản Boot. Hãy xác minh đường tích hợp của ứng dụng thay vì dựa vào một quy tắc chung cho mọi Spring context.

## 8. Sử dụng Converter với DataBinder và controller

`DataBinder` dùng cơ chế chuyển đổi của Spring để gắn dữ liệu vào kiểu thuộc tính. Ví dụ DTO có trường:

```java
public class PaymentForm {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
```

Khi binder nhận `currency=usd`, nếu conversion service được cấu hình đúng cho binder/MVC, chuỗi có thể được chuyển thành `CurrencyCode("USD")`. Nếu không có converter thích hợp hoặc chuỗi sai định dạng, quá trình binding có thể ghi lỗi type mismatch vào `BindingResult`.

Đoạn code để gắn conversion service thủ công vào binder là:

```java
DataBinder binder = new DataBinder(paymentForm, "payment");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

Đây là đoạn trích cần có `PaymentForm`, `ConversionService` và `PropertyValues` đã chuẩn bị. `DataBinder#setConversionService(...)` cấu hình service dùng trong quá trình binding; cần thực hiện khi tạo binder, trước khi binding. Không sửa registry của service theo từng binder.

Trong Spring MVC, `WebDataBinder` được tạo và cấu hình theo request. `WebMvcConfigurer.addFormatters(...)` là nơi thích hợp để đăng ký chuyển đổi dùng chung trong MVC. Có thể dùng `@InitBinder` để bổ sung cấu hình cục bộ cho một controller, nhưng đừng nhầm một validator với một converter: converter biến đổi kiểu, validator kiểm tra quy tắc trên giá trị đã có.

## 9. Đăng ký converter factory và generic converter

### 9.1. ConverterFactory

Khi nhiều kiểu đích thuộc cùng một họ, `ConverterFactory<S,R>` cho phép tạo converter cụ thể theo kiểu đích `T extends R`. Ví dụ chuyển chuỗi sang nhiều kiểu enum:

```java
public final class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> {
            String value = source.trim();
            return (T) Enum.valueOf(targetType, value);
        };
    }
}
```

Đoạn minh họa làm rõ cơ chế generic; với mã production cần xem xét cảnh báo unchecked cast, hằng enum có phân biệt hoa/thường và thông báo khi tên không tồn tại. Có thể dùng helper có kiểm tra hoặc chuẩn hóa giá trị theo hợp đồng của API. Đăng ký bằng `registry.addConverterFactory(new StringToEnumConverterFactory())`.

Một factory hữu ích khi cùng một quy tắc áp dụng cho một họ target; không nên dùng nó để chuyển sang các kiểu miền không liên quan chỉ nhằm giảm số lớp.

### 9.2. GenericConverter

`GenericConverter` cho phép khai báo nhiều `ConvertiblePair` và nhận `TypeDescriptor` nguồn/đích:

```java
Set<ConvertiblePair> pairs = Set.of(
        new ConvertiblePair(String.class, CurrencyCode.class));

@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return pairs;
}

@Override
public Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {
    // Chuyển đổi theo metadata và kiểu đã khai báo.
}
```

Đây là cấu trúc trích đoạn: để chạy cần triển khai đầy đủ `GenericConverter`, imports và định nghĩa logic chuyển. `GenericConverter` đặc biệt hữu ích khi việc chọn conversion phụ thuộc generic element type hoặc annotation trên field/parameter. Nếu chỉ cần một cặp đơn giản, giữ `Converter<S,T>`.

### 9.3. removeConvertible

`ConverterRegistry` có `removeConvertible(sourceType, targetType)` để gỡ các converter đã đăng ký cho một cặp kiểu. Chỉ dùng khi đang cấu hình hoặc xây registry có chủ đích; thay đổi registry toàn cục sau khi ứng dụng phục vụ request có thể làm hành vi chuyển đổi thay đổi bất ngờ giữa các thao tác.

Nếu cần converter khác nhau trong các ngữ cảnh khác nhau, tạo registry/service riêng cho từng ngữ cảnh thay vì liên tục add/remove một cặp converter dùng chung.

## 10. Xử lý null, chuỗi rỗng và lỗi chuyển đổi

Một `Converter<S,T>` thông thường nhận `source` khác null theo hợp đồng API. Việc xử lý null thường do `ConversionService` hoặc tầng binding quyết định. Chuỗi rỗng `""` lại là một giá trị String thực, không phải null. Bạn phải xác định rõ quy tắc:

- Chuỗi rỗng có được xem là thiếu không?
- Có loại bỏ khoảng trắng đầu/cuối không?
- Có chuẩn hóa chữ hoa/chữ thường không?
- Mã có phân biệt locale không?
- Nếu sai cú pháp, có ném `IllegalArgumentException` với thông báo đủ rõ không?

Với converter trong ví dụ, `trim()` loại khoảng trắng hai đầu và `Locale.ROOT` chuẩn hóa mã không phụ thuộc locale của máy. Nó chỉ chấp nhận đúng ba ký tự A-Z. Đây là hợp đồng ví dụ cho mã tiền tệ dạng chữ; nó không kiểm tra mã có tồn tại trong danh mục ISO hoặc ứng dụng có hỗ trợ đồng tiền đó hay không. Nếu cần kiểm tra danh mục, cân nhắc lookup service/cache có thiết kế phù hợp; không nhồi truy cập mạng/cơ sở dữ liệu vào một converter dùng chung mà không xét thread safety và hiệu năng.

Khi converter không thể chuyển đổi một giá trị, ném `IllegalArgumentException` là tín hiệu được Spring hỗ trợ. Đừng trả về một giá trị giả như `CurrencyCode("XXX")` chỉ để tránh exception trừ khi đó thực sự là giá trị mặc định hợp lệ theo hợp đồng miền.

## 11. Converter và Formatter trong Spring MVC

Spring MVC sử dụng hệ thống conversion/formatting để xử lý dữ liệu từ request parameters và các thuộc tính cần binding. `FormatterRegistry` mở rộng khả năng đăng ký converter để còn hỗ trợ formatter.

Ví dụ:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToCurrencyCode());
    registry.addFormatter(new CurrencyCodeFormatter());
}
```

Đoạn minh họa cho thấy hai loại có thể cùng nằm trong registry; `CurrencyCodeFormatter` cần triển khai `Formatter<CurrencyCode>` riêng. Converter phù hợp cho việc biến đổi kiểu; formatter phù hợp cho đọc/hiển thị theo locale.

Đối với request JSON qua `@RequestBody`, Spring MVC thường dùng `HttpMessageConverter` (ví dụ Jackson) để deserialize JSON. Việc một converter được đăng ký vào `FormatterRegistry` **không bảo đảm** Jackson tự dùng nó khi đọc JSON. Nếu cần chuyển đổi trong JSON, phải cấu hình serializer/deserializer/module phù hợp cho Jackson hoặc dùng kiểu JSON có cấu trúc rõ ràng. Không suy diễn hành vi JSON từ ví dụ `@RequestParam` hay `@ModelAttribute`.

## 12. Kiểm thử ConverterRegistry

Kiểm thử converter nên bao gồm ít nhất các trường hợp:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Cặp kiểu được đăng ký | `canConvert(String.class, CurrencyCode.class)` trả `true` |
| Chuyển hợp lệ | `"usd"` tạo đúng `CurrencyCode("USD")` |
| Khoảng trắng | Hành vi trim theo hợp đồng |
| Sai độ dài | Từ chối `"US"` bằng exception phù hợp |
| Chuỗi rỗng | Theo chính sách đã định, không tự tạo mã giả |
| Cặp kiểu không được hỗ trợ | `canConvert(...)` trả `false` hoặc conversion thất bại theo API |
| MVC query/form | Converter hoạt động qua registry của MVC |
| JSON body | Kiểm thử riêng Jackson converter/deserializer |
| Dùng nhiều thread | Converter không giữ trạng thái request và dùng an toàn |
| Cấu hình context | Không có nhiều registry hoặc converter xung đột ngoài ý muốn |

Một unit test có thể tạo `DefaultFormattingConversionService`, thêm converter, rồi kiểm tra `convert(...)`. Một integration test Spring MVC nên khởi tạo application context và gửi request thực qua `MockMvc` để chắc rằng converter thực sự được registry MVC sử dụng.

Không chỉ kiểm tra `canConvert` rồi kết luận converter tốt: phương thức đó chủ yếu trả lời cặp kiểu có khả năng chuyển đổi hay không, không kiểm thử mọi giá trị nguồn.

## 13. Những lỗi thường gặp

1. **Nhầm ConverterRegistry với ConversionService:** registry đăng ký, service thực hiện chuyển đổi. Biết cặp kiểu đã đăng ký không đồng nghĩa dữ liệu đầu vào nào cũng hợp lệ.
2. **Đăng ký sai chiều:** `String → CurrencyCode` khác `CurrencyCode → String`. Kiểm tra đúng source và target.
3. **Không khai báo generic rõ ràng:** raw converter khiến việc suy ra cặp kiểu không rõ; dùng `Converter<S,T>` đúng tham số.
4. **Tưởng bean Converter tự động được mọi service sử dụng:** cách thu thập bean phụ thuộc cấu hình/Boot; trong MVC hãy dùng `addFormatters(...)`.
5. **Tạo ConversionService nhưng không đặt đúng bean name hoặc không nối vào context cần dùng:** nếu muốn container nhận diện service toàn cục, tuân theo tên/configuration mà Spring yêu cầu; với MVC, cấu hình registry MVC.
6. **Tạo một service mới cho từng request:** conversion service được thiết kế để khởi tạo và chia sẻ; tạo mới liên tục gây lãng phí và phân tán converter.
7. **Converter có trạng thái mutable:** nhiều request có thể dùng chung converter; không lưu dữ liệu theo request trong field.
8. **Không xử lý đầu vào sai:** converter nên ném exception phù hợp thay vì âm thầm trả giá trị không đúng.
9. **Nhầm converter với validator:** converter tạo giá trị kiểu đích; validator kiểm tra giá trị sau khi đã có.
10. **Dùng Converter thay Formatter cho dữ liệu cần locale:** ngày/số hiển thị theo locale thường cần `Formatter`.
11. **Tưởng ConverterRegistry cấu hình JSON Jackson:** Spring MVC message converter và Jackson có đường tích hợp riêng.
12. **Đăng ký nhiều converter cho cùng cặp không chủ đích:** có thể tạo hành vi khó dự đoán khi context được cấu hình nhiều lần. Gom đăng ký vào một nơi rõ ràng và kiểm thử.
13. **Không tách lỗi “không có converter” và “converter từ chối giá trị”:** một lỗi là thiếu khả năng cho cặp kiểu; lỗi kia là dữ liệu cụ thể không chuyển được.

## 14. Lộ trình thực hành

1. Tạo một `Converter<String, CurrencyCode>` và chạy ví dụ console.
2. Thay đăng ký generic bằng overload `addConverter(String.class, CurrencyCode.class, converter)`; xác nhận kết quả không đổi.
3. Thêm một cặp kiểu miền khác và converter riêng, quan sát `canConvert` theo từng cặp.
4. Đăng ký converter trong `DefaultFormattingConversionService` như ví dụ.
5. Đưa cấu hình sang `WebMvcConfigurer.addFormatters(...)` và kiểm thử `@RequestParam`/`@ModelAttribute`.
6. Viết test cho chuỗi rỗng, khoảng trắng, ký tự sai và exception.
7. Thử `ConverterFactory` cho một nhóm enum, sau đó đánh giá liệu generic có thực sự giúp giảm mã.
8. Chỉ chuyển sang `GenericConverter` khi cần metadata hoặc nhiều cặp chuyển đổi.

**Tự kiểm tra:** Nếu `registry.addConverter(String.class, CurrencyCode.class, converter)` đã được gọi, điều gì làm `canConvert(String.class, CurrencyCode.class)` trả true? Vì sao chuỗi `"US"` vẫn có thể thất bại? Trong MVC, vì sao phải đăng ký converter ở registry phù hợp thay vì chỉ tạo một object `Converter`?

## Tham khảo chính thức

- [Spring Framework 6.2 — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — Converter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring Framework 6.2 — GenericConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework 6.2 — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
