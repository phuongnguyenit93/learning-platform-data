# ConvertiblePair và khai báo phạm vi chuyển đổi trong Spring Framework

Trong hệ thống chuyển đổi kiểu của Spring, một converter cần công bố **kiểu nguồn nào có thể chuyển sang kiểu đích nào**. Với `GenericConverter`, thông tin này được mô tả bởi `GenericConverter.ConvertiblePair` và trả về từ `getConvertibleTypes()`.

Một `ConvertiblePair` là cặp có hướng:

\[
(\text{sourceType},\ \text{targetType})
\]

Ví dụ `String → Money` khác `Money → String`. Đăng ký chiều đầu tiên không tự tạo quy tắc cho chiều ngược lại.

Bài học này trình bày cấu trúc `ConvertiblePair`, cách khai báo một hoặc nhiều cặp, cơ chế registry tra cứu, vai trò của `TypeDescriptor`, `ConditionalGenericConverter`, cách đăng ký trong Spring MVC và một chương trình Java 17/Spring 6.2 chạy được.

## 1. ConvertiblePair là gì?

`ConvertiblePair` là lớp lồng tĩnh trong `GenericConverter`, thuộc package `org.springframework.core.convert.converter`. Nó giữ hai lớp Java: kiểu nguồn và kiểu đích. Nó không thực hiện parse dữ liệu, không giữ giá trị đầu vào và không phải converter độc lập.

Chữ ký quan trọng của `GenericConverter`:

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
```

`getConvertibleTypes()` trả tập các cặp kiểu mà converter hỗ trợ. `convert(...)` nhận object nguồn, metadata mô tả trường nguồn/đích và tạo object đích.

Cách tạo cặp:

```java
new GenericConverter.ConvertiblePair(
        String.class, Money.class);
```

Đọc theo đúng thứ tự: `String.class` là source, `Money.class` là target. Đảo hai đối số sẽ khai báo một conversion khác.

Một converter có điều kiện có thể trả `null` từ `getConvertibleTypes()` để cho biết mọi cặp kiểu cần được xem xét có điều kiện. Trường hợp này chỉ phù hợp với converter triển khai `ConditionalConverter`; trong ứng dụng thông thường, hãy công bố các cặp cụ thể.

## 2. Phạm vi chuyển đổi là cặp có hướng

| Cặp kiểu | Ý nghĩa |
| --- | --- |
| `String → CurrencyCode` | Parse chuỗi thành mã tiền tệ |
| `CurrencyCode → String` | In mã tiền tệ thành chuỗi |
| `String → Money` | Parse văn bản tiền thành kiểu miền |
| `BigDecimal → Money` | Chuyển số thập phân thành kiểu miền |
| `String → LocalDate` | Parse chuỗi thành ngày theo quy tắc định dạng |

Hai chiều chuyển đổi là hai cặp độc lập. Nếu giao diện cần vừa nhận vừa hiển thị dữ liệu, hãy đăng ký converter ngược hoặc cân nhắc `Formatter<T>` có cả `parse` và `print`.

Một converter chỉ nên khai báo những cặp mà nó thật sự có thể xử lý. Công bố `Object → Money` trong khi mã chỉ biết xử lý `String` và `BigDecimal` là hợp đồng sai; registry có thể chọn converter cho một source không phù hợp.

## 3. Khai báo một cặp hay nhiều cặp?

### 3.1. Converter cho một cặp

Nếu chỉ có một cặp cố định, ưu tiên `Converter<S,T>`:

```java
public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        return new CurrencyCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Spring có thể suy ra cặp kiểu từ generic của lớp. Cách này type-safe và ngắn gọn hơn `GenericConverter` khi không cần metadata.

### 3.2. GenericConverter cho nhiều cặp

Khi một thành phần thực sự nhận nhiều kiểu nguồn hoặc đích, khai báo tập `ConvertiblePair`:

```java
private static final Set<ConvertiblePair> PAIRS = Set.of(
    new ConvertiblePair(String.class, Money.class),
    new ConvertiblePair(BigDecimal.class, Money.class)
);

@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return PAIRS;
}
```

Ví dụ này công bố hai đường chuyển đổi khác nhau nhưng tạo cùng kiểu đích `Money`. Bên trong `convert(...)` cần nhận diện kiểu nguồn và xử lý tương ứng.

`ConvertiblePair` là metadata tìm kiếm, không bảo đảm mọi giá trị thuộc kiểu nguồn đều hợp lệ. Chuỗi `"12.50"` có thể parse được, còn `"twelve"` vẫn có thể bị converter từ chối.

## 4. Registry dùng ConvertiblePair như thế nào?

`ConverterRegistry` là SPI đăng ký converter, factory và gỡ quy tắc theo cặp. Các phương thức quan trọng gồm:

- `addConverter(Converter<?, ?> converter)`: đăng ký converter generic đơn giản.
- `addConverter(sourceType, targetType, converter)`: đăng ký một cặp kiểu tường minh.
- `addConverter(GenericConverter converter)`: đăng ký converter công bố một hoặc nhiều `ConvertiblePair`.
- `addConverterFactory(ConverterFactory<?, ?> factory)`: đăng ký factory tạo converter cho một họ kiểu đích.
- `removeConvertible(sourceType, targetType)`: gỡ quy tắc theo cặp.

Luồng tổng quát:

```text
GenericConverter
      |
      v
getConvertibleTypes()
      |
      +-- (String, Money)
      +-- (BigDecimal, Money)
      |
      v
ConverterRegistry.addConverter(...)
      |
      v
Registry lưu converter theo các cặp được công bố
      |
      v
ConversionService.canConvert(...) / convert(...)
      |
      v
Tìm converter phù hợp với kiểu nguồn và kiểu đích thực tế
```

Các cặp được dùng để xác định ứng viên. Khi chuyển đổi thật, `ConversionService` tìm converter rồi gọi `convert(...)` với source và target descriptor.

### 4.1. Tìm kiếm theo phân cấp kiểu

`GenericConversionService` có thể xét phân cấp lớp và interface của kiểu nguồn và kiểu đích. Vì vậy, đăng ký cặp với kiểu cha hoặc interface có thể mở rộng phạm vi áp dụng sang kiểu con tương ứng.

Ví dụ `CharSequence → Money` rộng hơn `String → Money` vì nhiều loại dữ liệu có thể triển khai `CharSequence`. Chỉ chọn kiểu nguồn rộng khi thuật toán thật sự xử lý được toàn bộ phạm vi đó.

Không nên giả định registry chỉ so sánh hai lớp bằng phép bằng tuyệt đối. Hành vi tra cứu của `GenericConversionService` còn xét quan hệ kế thừa và các converter có điều kiện.

### 4.2. Nhiều converter cho cùng cặp

Nếu cùng source/target được đăng ký nhiều lần, việc chọn converter chịu ảnh hưởng của registry, điều kiện và thứ tự đăng ký. Hãy gom đăng ký vào một cấu hình có chủ đích, tránh việc nhiều module cùng thay thế một cặp kiểu mà không có hợp đồng rõ ràng.

Nếu một cặp chỉ nên dùng trong một số ngữ cảnh, xem xét `ConditionalGenericConverter`. Nếu hai ngữ cảnh cần quy tắc hoàn toàn khác nhau, cân nhắc các `ConversionService` riêng.

## 5. TypeDescriptor bổ sung metadata gì?

Khác `Converter<S,T>` đơn giản, `GenericConverter` nhận:

- `source`: giá trị cần chuyển.
- `sourceType`: `TypeDescriptor` mô tả trường nguồn.
- `targetType`: `TypeDescriptor` mô tả trường đích.

`TypeDescriptor` có thể mang kiểu Java, metadata generic của collection/map/array và annotation trên field hoặc method. Nhờ đó converter có thể đưa ra quyết định dựa trên ngữ cảnh khai báo.

Ví dụ, hai trường đều có kiểu collection nhưng generic element type khác nhau; chỉ nhìn `List.class` là chưa đủ để biết phần tử bên trong là `String` hay `Integer`. Với metadata phù hợp, converter có thể xử lý chính xác hơn.

Nếu logic chỉ cần xem source có phải `String` hay không và target là một lớp cụ thể, `Converter<S,T>` dễ đọc hơn. Dùng `TypeDescriptor` khi metadata thật sự ảnh hưởng quyết định chuyển đổi.

## 6. ConditionalGenericConverter

`ConditionalGenericConverter` kết hợp `GenericConverter` với điều kiện `matches(...)`:

```java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
```

Registry chỉ chọn converter có điều kiện khi `matches(...)` trả `true`. Chẳng hạn cùng cặp `String → Money` nhưng converter chỉ áp dụng cho trường đích được đánh dấu bằng annotation riêng.

```java
public final class AccountingMoneyConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(AccountingCurrency.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return Money.parse((String) source);
    }
}
```

Đây là ví dụ cấu trúc; muốn biên dịch cần định nghĩa annotation `AccountingCurrency`, kiểu `Money` và imports. `matches` quyết định converter có phù hợp metadata hay không; `convert` vẫn cần xác thực nội dung giá trị.

Không dùng điều kiện metadata để thay thế kiểm tra cú pháp chuỗi. Một converter phù hợp với field vẫn có thể từ chối một giá trị sai định dạng khi thực thi.

## 7. Ví dụ hoàn chỉnh: hai ConvertiblePair cùng tạo một kiểu Money

Ví dụ Java 17/Spring Framework 6.2 dưới đây chạy từ console, không cần Spring Boot hoặc HTTP server. Nó đăng ký một `GenericConverter` nhận `String` và `BigDecimal` để tạo cùng kiểu miền `Money`.

Cấu trúc dự án:

```text
convertible-pair-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/convert/ConvertiblePairDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'convertible-pair-demo'
```

`build.gradle`:

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
    mainClass = 'demo.convert.ConvertiblePairDemo'
}
```

`spring-context` kéo theo các module Spring cần cho conversion service và registry. Trong dự án Spring Boot, nên để Boot quản lý phiên bản module Spring thay vì tự ghim một phiên bản khác với các starter.

Tạo `src/main/java/demo/convert/ConvertiblePairDemo.java`:

```java
package demo.convert;

import java.math.BigDecimal;
import java.util.Set;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConvertiblePairDemo {

    public record Money(BigDecimal amount) {
        public Money {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Money amount must be non-negative");
            }
        }
    }

    public static final class MoneyConverter implements GenericConverter {

        private static final Set<ConvertiblePair> PAIRS = Set.of(
                new ConvertiblePair(String.class, Money.class),
                new ConvertiblePair(BigDecimal.class, Money.class)
        );

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return PAIRS;
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            BigDecimal amount;
            if (sourceType.getObjectType() == String.class) {
                amount = new BigDecimal(((String) source).trim());
            } else if (sourceType.getObjectType() == BigDecimal.class) {
                amount = (BigDecimal) source;
            } else {
                throw new IllegalArgumentException(
                        "Unsupported source type: " + sourceType);
            }

            return new Money(amount);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(new MoneyConverter());

        System.out.println("stringPair="
                + service.canConvert(String.class, Money.class));
        System.out.println("decimalPair="
                + service.canConvert(BigDecimal.class, Money.class));

        Money fromText = service.convert("125.50", Money.class);
        Money fromNumber = service.convert(
                new BigDecimal("80.25"), Money.class);

        System.out.println("fromText=" + fromText.amount().toPlainString());
        System.out.println("fromNumber="
                + fromNumber.amount().toPlainString());

        try {
            service.convert("-1.00", Money.class);
        } catch (ConversionFailedException exception) {
            System.out.println("negative=rejected");
        }
    }
}
```

Chạy từ thư mục dự án với Gradle đã cài:

```bash
gradle -q run
```

Nếu có Gradle Wrapper, dùng `./gradlew -q run` trên Unix/macOS hoặc `gradlew.bat -q run` trên Windows.

Stdout do chương trình Java in ra:

```text
stringPair=true
decimalPair=true
fromText=125.50
fromNumber=80.25
negative=rejected
```

### Phân tích kết quả

- `getConvertibleTypes()` công bố hai cặp: `String → Money` và `BigDecimal → Money`.
- `addConverter(new MoneyConverter())` đăng ký converter và để registry lấy các cặp từ `getConvertibleTypes()`.
- `canConvert(...)` kiểm tra registry có khả năng chuyển đổi cặp kiểu hay không.
- Khi source là String, converter parse thành `BigDecimal`; khi source đã là `BigDecimal`, dùng trực tiếp.
- Constructor `Money` từ chối số âm. Converter được tìm thấy nhưng giá trị cụ thể bị từ chối; lỗi được Spring thể hiện qua `ConversionFailedException`.

Do đó, `ConvertiblePair` xác định **phạm vi kiểu**; `convert(...)` xử lý **giá trị cụ thể**. Hai bước này không thể thay thế cho nhau.

## 8. Đăng ký trong Spring Configuration và Spring MVC

### 8.1. ConversionService bean

Có thể đăng ký converter vào một conversion service do Spring quản lý:

```java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConfigurableConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new MoneyConverter());
        return service;
    }
}
```

Đây là lớp cấu hình Spring cần imports và lớp `MoneyConverter` ở package phù hợp. `DefaultConversionService` vừa cung cấp conversion mặc định, vừa triển khai registry để thêm các cặp kiểu.

Spring có quy ước bean conversion service toàn cục tên `conversionService` trong những cơ chế cần nhận diện bean này. Tránh khai báo nhiều bean cùng vai trò mà không có lý do, và kiểm tra context thực tế đang dùng bean nào.

### 8.2. Đăng ký cho Spring MVC

Khi muốn converter phục vụ binding của Spring MVC, triển khai `WebMvcConfigurer.addFormatters(FormatterRegistry registry)`:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MoneyConverter());
    }
}
```

Converter được đăng ký vào formatter registry mà MVC sử dụng. Các tham số query hoặc thuộc tính form có kiểu `Money` có thể được chuyển từ chuỗi khi dùng đường binding hỗ trợ conversion service đó.

Trong Spring Boot, thường chỉ cần bổ sung `WebMvcConfigurer` để mở rộng MVC; không thêm `@EnableWebMvc` chỉ để đăng ký converter vì có thể thay đổi cơ chế auto-configuration của Boot.

Tạo bean `GenericConverter` đơn lẻ không bảo đảm mọi registry trong mọi application context tự động nhận nó. Hãy đăng ký vào đúng conversion service hoặc registry mà tầng sử dụng cần.

### 8.3. DataBinder và JSON

`DataBinder` có thể dùng conversion service để chuyển đổi property khi bind. Có thể cấu hình thủ công trước khi gọi `bind(...)`:

```java
DataBinder binder = new DataBinder(form, "payment");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

Đây là đoạn trích, cần có đối tượng `form`, `PropertyValues` và `ConversionService` tương ứng. Converter phải có mặt trong service được gắn vào binder.

Với `@RequestBody` JSON, Spring thường dùng `HttpMessageConverter` như Jackson để deserialize. Converter đã đăng ký trong MVC `FormatterRegistry` không mặc nhiên trở thành Jackson deserializer. Cần cấu hình Jackson module/serializer/deserializer nếu kiểu JSON cần xử lý riêng.

## 9. Phân biệt GenericConverter với ConverterFactory

`ConverterFactory<S,R>` phù hợp khi một source type chuyển tới nhiều target type cùng họ. Ví dụ `String → nhiều enum cụ thể`: factory nhận target class rồi tạo converter đúng cho enum đó.

`GenericConverter` phù hợp khi converter cần công bố nhiều cặp nguồn/đích cụ thể, có thể khác họ, hoặc cần metadata `TypeDescriptor`.

| Yêu cầu | SPI phù hợp |
| --- | --- |
| Một cặp `String → CurrencyCode` | `Converter<S,T>` |
| Một source chuyển đến nhiều enum | `ConverterFactory<S,R>` |
| Nhiều cặp như `String → Money`, `BigDecimal → Money` | `GenericConverter` |
| Phụ thuộc annotation/generic metadata | `ConditionalGenericConverter` |
| Parse và in văn bản theo locale | `Formatter<T>` |

Hãy chọn SPI đơn giản nhất đáp ứng yêu cầu. `GenericConverter` linh hoạt nhưng ít type-safe hơn `Converter<S,T>` và đòi hỏi tự kiểm soát việc ép kiểu.

## 10. Những lưu ý khi khai báo tập ConvertiblePair

### 10.1. Không công bố cặp mà converter không thực hiện được

Nếu công bố `String → Money`, converter phải xử lý mọi String thuộc hợp đồng đó hoặc từ chối giá trị sai theo cách rõ ràng. Nếu source quá rộng như `Object`, phải bảo đảm thuật toán thực sự hỗ trợ toàn bộ phạm vi.

### 10.2. Không nhầm hai chiều chuyển đổi

`String → Money` không tự cung cấp `Money → String`. Nếu cần hiển thị lại, đăng ký chiều ngược riêng hoặc dùng `Formatter`.

### 10.3. Không nhầm ConvertiblePair và TypeDescriptor

`ConvertiblePair` khai báo cặp lớp. `TypeDescriptor` cung cấp metadata chi tiết cho một lần chuyển đổi. Khi cần generic type hoặc annotation, hãy xem descriptor thay vì chỉ nhìn `source.getClass()`.

### 10.4. Null khác chuỗi rỗng

`null` là không có object nguồn; `""` là String có độ dài bằng 0. Conversion service có quy tắc null riêng. Converter vẫn cần xác định cách xử lý chuỗi rỗng, khoảng trắng, định dạng sai và giá trị biên; không tạo giá trị giả để che lỗi.

### 10.5. Tránh converter mutable dùng chung

Conversion service thường được tạo lúc khởi tạo ứng dụng và dùng chung giữa nhiều luồng. Converter nên stateless hoặc có trạng thái bất biến. Không lưu dữ liệu request hay user hiện tại trong field.

## 11. Kiểm thử cặp kiểu và converter

| Test | Điều cần xác minh |
| --- | --- |
| Cặp nguồn String | `canConvert(String.class, Money.class)` là true |
| Cặp nguồn BigDecimal | `canConvert(BigDecimal.class, Money.class)` là true |
| Chuỗi hợp lệ | Parse đúng số và tạo Money |
| BigDecimal | Giữ chính xác giá trị thập phân |
| Số âm | Converter/constructor từ chối với lỗi có nguyên nhân |
| Cặp không hỗ trợ | Không báo hỗ trợ ngoài ý muốn |
| Kiểu cha/interface | Chỉ áp dụng nếu converter được thiết kế cho phạm vi đó |
| Metadata | Conditional converter chỉ khớp field đúng annotation/generic |
| MVC | Converter đăng ký trong đúng registry MVC |
| JSON | Kiểm thử riêng cấu hình Jackson |

Đừng chỉ kiểm tra `canConvert(...)`. Nó cho biết có đường chuyển đổi theo kiểu; không xác minh mọi giá trị cụ thể đều được chấp nhận. Cần gọi `convert(...)` với cả dữ liệu hợp lệ và không hợp lệ.

## 12. Lỗi thường gặp

1. **Đảo source và target:** `(Money, String)` khác `(String, Money)`.
2. **Quên khai báo một cặp:** code có nhánh BigDecimal nhưng `getConvertibleTypes()` không công bố cặp đó, khiến registry không tìm được converter cho source này.
3. **Công bố cặp nhưng không xử lý:** registry tìm thấy converter nhưng `convert(...)` không biết xử lý source.
4. **Dùng GenericConverter cho một cặp đơn giản:** `Converter<S,T>` rõ ràng và type-safe hơn.
5. **Bỏ qua TypeDescriptor:** logic phụ thuộc annotation/generic nhưng chỉ nhìn class runtime.
6. **Dùng matches() để kiểm tra nội dung:** matches phù hợp với metadata; convert kiểm tra giá trị cụ thể.
7. **Công bố cặp Object quá rộng:** có thể khiến converter được chọn cho kiểu ngoài dự kiến.
8. **Cho rằng cặp có hai chiều:** chiều ngược phải đăng ký riêng.
9. **Chỉ tạo bean mà quên registry:** converter chưa được conversion service sử dụng thì không có tác dụng.
10. **Đăng ký trùng lặp ở nhiều nơi:** thứ tự và điều kiện có thể làm lựa chọn converter khó đoán.
11. **Không phân biệt không có converter và converter từ chối giá trị:** đây là hai loại lỗi khác nhau.
12. **Cho rằng MVC converter tự áp dụng cho Jackson:** JSON deserialization có cơ chế riêng.

## 13. Bài tập tự luyện

1. Thêm cặp `Long → Money` và một nhánh xử lý tương ứng trong `convert(...)`. Kiểm tra `canConvert(Long.class, Money.class)`.
2. Gọi chuyển đổi `Money → String` trước khi đăng ký cặp ngược. Sau đó bổ sung converter ngược và so sánh.
3. Thử cặp nguồn `CharSequence → Money`. Giải thích vì sao nó rộng hơn `String → Money`.
4. Viết `ConditionalGenericConverter` chỉ áp dụng khi field đích có annotation riêng.
5. Thử null, chuỗi rỗng, khoảng trắng, số âm và số quá lớn; xác định chính sách của converter.
6. Đăng ký converter qua `WebMvcConfigurer.addFormatters(...)` rồi kiểm thử endpoint nhận Money từ query parameter.

Bạn nắm vững bài khi giải thích được: **ConvertiblePair công bố phạm vi; registry dùng cặp để tìm converter; TypeDescriptor mô tả ngữ cảnh; convert xử lý giá trị thực.**

## Tài liệu tham khảo

- [Spring Framework 6.2 — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework — GenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework — GenericConverter.ConvertiblePair Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.ConvertiblePair.html)
- [Spring Framework — ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
