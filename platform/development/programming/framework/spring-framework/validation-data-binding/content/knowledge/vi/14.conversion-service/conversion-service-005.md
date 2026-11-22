# Đăng ký, thay thế hoặc loại bỏ Converter trong Spring ConversionService

Spring Framework cung cấp **`ConversionService`** để chuyển một giá trị từ kiểu nguồn sang kiểu đích, ví dụ `String` thành `Integer`, `String` thành enum hoặc một mã văn bản thành value object của ứng dụng. Khi cần mở rộng logic chuyển đổi, ta đăng ký một **`Converter<S, T>`**, `ConverterFactory<S, R>` hoặc `GenericConverter` vào registry mà `ConversionService` sử dụng.

Điểm quan trọng là phân biệt hai vai trò:

- **`ConversionService`** là API sử dụng converter: hỏi có chuyển được không và thực hiện chuyển đổi.
- **`ConverterRegistry`** là SPI cấu hình: đăng ký converter và gỡ converter theo cặp kiểu nguồn/đích.
- **`ConfigurableConversionService`** kết hợp hai vai trò trên, nên có thể vừa convert vừa thay đổi registry.
- Trong Spring MVC, `WebMvcConfigurer.addFormatters(FormatterRegistry)` là điểm mở rộng chuẩn để đăng ký converter/formatter cho binder của ứng dụng.

Không phải mọi object được gọi là `ConversionService` đều có API thêm/xóa converter. Cũng không nên sửa một service dùng chung của framework tùy tiện, vì các controller và binder khác có thể dựa vào những converter đã đăng ký.

## 1. ConversionService làm gì?

Một `ConversionService` cung cấp hai nhóm phương thức:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType, TypeDescriptor targetType);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
```

Hai overload nhận `TypeDescriptor` cho phép Spring xét thêm metadata kiểu như generic element type và annotation của field. Ví dụ, chuyển `List<String>` sang `List<Integer>` cần biết kiểu phần tử của collection, không chỉ biết cả hai giá trị ngoài cùng đều là `List`.

Ví dụ sử dụng:

```java
ConversionService service = ...;

boolean supported =
        service.canConvert(String.class, Integer.class);

Integer quantity = service.convert("42", Integer.class);
```

Nếu không có đường chuyển đổi phù hợp, `convert(...)` có thể ném `ConversionFailedException` hoặc exception chuyển đổi liên quan. `canConvert(...)` giúp kiểm tra khả năng trước, nhưng không bảo đảm một giá trị cụ thể luôn parse được: ví dụ `String` nói chung có thể chuyển thành `Integer`, nhưng `"abc"` không phải số nguyên hợp lệ.

Với `source == null`, `ConversionService` thường trả `null` theo quy tắc chung của API mà không cần gọi custom converter cho một giá trị nguồn null. Nếu cần biểu diễn một giá trị “không có” thành object đặc biệt, hãy thiết kế rõ trong lớp gọi hoặc một converter/formatter phù hợp; đừng mặc định converter sẽ nhận `null`.

## 2. ConversionService và ConverterRegistry là hai vai trò khác nhau

Sơ đồ quan hệ:

```text
             ConverterRegistry
         (đăng ký / gỡ converter)
                    ▲
                    │
       ConfigurableConversionService
                    │
          ┌─────────┴──────────┐
          │                    │
 ConversionService         ConverterRegistry
 (canConvert/convert)   (add/remove converter)
```

Các interface quan trọng:

| API | Chức năng chính |
| --- | --- |
| `ConversionService` | `canConvert(...)` và `convert(...)` |
| `ConverterRegistry` | `addConverter(...)`, `addConverterFactory(...)` và `removeConvertible(...)` |
| `ConfigurableConversionService` | Kết hợp `ConversionService` và `ConverterRegistry` |
| `Converter<S, T>` | Một converter strongly typed từ `S` sang `T` |
| `ConverterFactory<S, R>` | Tạo converter từ một kiểu nguồn đến một họ kiểu đích có chung root type `R` |
| `GenericConverter` | Chuyển đổi linh hoạt dựa trên tập `ConvertiblePair` và `TypeDescriptor` |
| `ConditionalConverter` | Cho phép converter kiểm tra thêm điều kiện về kiểu/mô tả trước khi áp dụng |

`ConversionService` **không khai báo** các thao tác đăng ký/gỡ converter. Nếu biến chỉ có kiểu interface này:

```java
ConversionService service = ...;
// service.addConverter(...); // Không biên dịch.
```

thì không thể gọi phương thức cấu hình qua biến đó. Cần tham chiếu đến kiểu registry phù hợp:

```java
ConfigurableConversionService configurable = ...;
configurable.addConverter(myConverter);
```

Hoặc dùng biến `ConverterRegistry` nếu code chỉ cần thao tác đăng ký, không cần convert trực tiếp.

## 3. Đăng ký converter: các cách phổ biến

`ConverterRegistry` cung cấp các dạng overload thường dùng:

```java
registry.addConverter(new StringToCodeConverter());

registry.addConverter(
        String.class,
        Code.class,
        source -> Code.of(source.trim()));

registry.addConverter(new SomeGenericConverter());

registry.addConverterFactory(new StringToEnumConverterFactory());
```

### 3.1. Converter<S, T>

Dùng khi cặp kiểu nguồn và đích rõ ràng:

```java
public final class StringToCodeConverter
        implements Converter<String, Code> {

    @Override
    public Code convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Code must not be blank");
        }
        return Code.of(source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Đây là converter ví dụ. Với `Converter<S,T>`, Spring suy ra cặp kiểu từ tham số generic; converter phải khai báo generic đủ cụ thể để registry xác định được `S` và `T`. Một class raw kiểu `Converter` hoặc generic type chưa thể giải quyết có thể bị từ chối khi đăng ký.

### 3.2. Đăng ký cặp nguồn/đích tường minh

Có thể đăng ký converter bằng hai class:

```java
registry.addConverter(
        String.class,
        CustomerId.class,
        source -> CustomerId.from(source.trim()));
```

Cách này hữu ích khi muốn tái sử dụng lambda/logic chuyển đổi hoặc khi kiểu generic của converter không thể được suy luận thuận tiện. Hãy bảo đảm hàm chuyển đổi nhận đúng kiểu nguồn và trả đúng kiểu đích đã khai báo.

### 3.3. ConverterFactory

Dùng khi đích thuộc một họ kiểu có chung root. Ví dụ một converter factory tạo converter từ `String` sang từng kiểu enum:

```java
public final class StringToEnumFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {
        return source -> Enum.valueOf(
                targetType, source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Đây là ví dụ rút gọn về ý tưởng; khi xây dựng thực tế, cần xử lý input rỗng, tên enum không hợp lệ và generic type an toàn. Spring cũng đã có converter mặc định cho nhiều kiểu phổ biến, nên không đăng ký thêm chỉ để tái tạo khả năng đã tồn tại.

### 3.4. GenericConverter

Dùng khi cần hỗ trợ nhiều cặp kiểu hoặc đọc `TypeDescriptor` nguồn/đích, chẳng hạn annotation, generic collection element hoặc metadata của field. Một `GenericConverter` khai báo tập `ConvertiblePair` trong `getConvertibleTypes()` và thực hiện logic trong `convert(...)`.

Nếu logic chỉ là `String` sang một value object, `Converter<String, Target>` thường dễ hiểu và dễ kiểm thử hơn. Chỉ dùng `GenericConverter` khi thực sự cần sự linh hoạt về metadata hoặc nhiều cặp kiểu.

## 4. Thay thế converter đang có

`ConverterRegistry` không có một phương thức riêng tên `replaceConverter(...)`. Việc thay converter thường được thực hiện bằng **gỡ cặp nguồn/đích cũ rồi đăng ký converter mới**:

```java
registry.removeConvertible(String.class, CustomerId.class);
registry.addConverter(new StringToCustomerIdConverter());
```

`removeConvertible(sourceType, targetType)` xóa các converter đã đăng ký cho **cặp kiểu nguồn/đích được chỉ định** khỏi registry đó. Sau khi gỡ, đăng ký converter mới cho cùng cặp.

Điều này không phải “tìm một object converter theo tên rồi chỉ xóa đúng object đó”. API gỡ theo cặp kiểu, vì vậy hãy kiểm tra ảnh hưởng đến các chuyển đổi khác đang dùng đúng cặp đó, gồm cả converter được đăng ký bởi cấu hình mặc định nếu cặp tương ứng nằm trong registry.

**Không nên tự động remove rồi add trên một service toàn cục đang được nhiều request sử dụng** trong lúc ứng dụng chạy. Registry có thể được dùng chung; thay đổi runtime cần được quản lý đồng bộ và có chủ đích. An toàn hơn là cấu hình bộ converter hoàn chỉnh khi khởi tạo ứng dụng, hoặc tạo một service riêng cho một phạm vi nghiệp vụ.

### Thay thế có thể làm mất converter mặc định

Một `DefaultFormattingConversionService` có nhiều converter và formatter tích hợp sẵn. Nếu gọi:

```java
registry.removeConvertible(String.class, Integer.class);
```

trên registry đó, bạn có thể loại bỏ đường chuyển đổi mặc định `String → Integer` mà nhiều field form đang sử dụng. Hãy chỉ gỡ cặp bạn sở hữu/được giao quản lý. Khi cần định nghĩa quy tắc riêng cho một field, cân nhắc formatter/annotation hoặc binder có phạm vi hẹp thay vì thay đổi quy tắc chung toàn ứng dụng.

### Thêm converter mới cùng cặp có phải lúc nào cũng là thay thế?

Đừng dựa vào thứ tự đăng ký một cách mơ hồ để thay thế converter của hệ thống. Khi có nhiều converter cho cặp kiểu trùng nhau, kết quả chọn có thể phụ thuộc cách registry quản lý converter cụ thể và các điều kiện khớp kiểu. Nếu cần thay thế có kiểm soát, cách dễ đọc là tạo registry riêng đã được cấu hình rõ ràng, hoặc remove đúng cặp rồi add converter mong muốn trước khi service bắt đầu được dùng.

## 5. Loại bỏ converter

Để loại converter của một cặp:

```java
configurable.removeConvertible(String.class, CustomerId.class);
```

Sau khi remove, hãy kiểm tra lại:

```java
boolean canConvert =
        configurable.canConvert(String.class, CustomerId.class);
```

Tuy nhiên, kết quả `canConvert` có thể vẫn là `true` nếu registry còn converter khác, converter tổng quát hoặc một đường chuyển đổi mặc định có thể xử lý cặp đó. Vì vậy **không dùng duy nhất boolean này để chứng minh chính xác instance converter nào đã bị xóa**. Kiểm thử bằng một input đại diện có thể xác nhận hành vi thực tế; với converter có điều kiện, nên thử cả input thuộc và không thuộc điều kiện.

`removeConvertible` chỉ nhận cặp kiểu, không phải tên bean, qualifier, id hoặc object converter. Nó cũng không tự xóa converter khỏi các registry khác. Nếu cùng một class converter được đăng ký trong nhiều service, mỗi registry có vòng đời/cấu hình riêng.

## 6. Những implementation thường gặp

| Implementation | Vai trò và điểm đáng chú ý |
| --- | --- |
| `GenericConversionService` | Cài đặt nền tảng của `ConfigurableConversionService`; quản lý registry, tra cứu converter và cache kết quả phù hợp |
| `DefaultConversionService` | Mở rộng cấu hình converter thông dụng cho các kiểu Java thường gặp |
| `FormattingConversionService` | Kết hợp ConversionService với `FormatterRegistry` để hỗ trợ converter và formatter |
| `DefaultFormattingConversionService` | FormattingConversionService có các converter/formatter mặc định thường dùng |
| `ConversionServiceFactoryBean` | FactoryBean tạo/expose ConversionService từ các converter đã cấu hình |
| `FormattingConversionServiceFactoryBean` | FactoryBean cấu hình FormattingConversionService với converter/formatter/registrar |

`DefaultConversionService` và `DefaultFormattingConversionService` phù hợp làm nền tảng trong nhiều ứng dụng. Một service có cấu hình mặc định thường cần thiết hơn việc tự tạo `GenericConversionService` rỗng, vì nếu service rỗng thì các chuyển đổi thường dùng như số, enum hay collection có thể không khả dụng cho đến khi tự đăng ký.

Với các static helper tạo mặc định (ví dụ `DefaultConversionService.addDefaultConverters(registry)`), hãy đọc đúng API phiên bản Spring đang dùng. Các helper này có thể thêm một tập converter mặc định vào registry bạn cung cấp, không nên hiểu là tự khởi tạo hoặc quản lý bean Spring cho toàn bộ ứng dụng.

## 7. Ví dụ Java 17+ chạy được: đăng ký, thay thế và remove

Ví dụ này sử dụng Spring Framework 6.2.x, không cần Spring Boot hay HTTP server. Ta tạo một converter từ `String` đến value object `TicketCode`, thử convert, remove converter đã đăng ký, sau đó đăng ký một converter mới cho cùng cặp.

### 7.1. Cấu trúc dự án

```text
conversion-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ConversionRegistryDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'conversion-registry-demo'
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
    mainClass = 'example.ConversionRegistryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dùng JDK 17+ và Gradle tương thích, có kết nối Maven Central để tải dependency lần đầu. `spring-context` kéo theo module cần cho `core.convert` và `format`.

### 7.2. Mã nguồn đầy đủ

**`src/main/java/example/ConversionRegistryDemo.java`**

```java
package example;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

import java.util.Locale;

public class ConversionRegistryDemo {

    public static final class TicketCode {
        private final String value;

        private TicketCode(String value) {
            this.value = value;
        }

        public static TicketCode of(String value) {
            return new TicketCode(value);
        }

        public String value() {
            return value;
        }

        @Override
        public String toString() {
            return "TicketCode[value=" + value + "]";
        }
    }

    public static final class PlainTicketCodeConverter
            implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            return TicketCode.of(
                    source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static final class PrefixedTicketCodeConverter
            implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            return TicketCode.of(
                    "NEW-" + source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        ConfigurableConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new PlainTicketCodeConverter());

        TicketCode first =
                service.convert(" ab-12 ", TicketCode.class);
        System.out.println("registered=" + first);

        service.removeConvertible(String.class, TicketCode.class);
        System.out.println("afterRemove="
                + service.canConvert(String.class, TicketCode.class));

        service.addConverter(new PrefixedTicketCodeConverter());
        TicketCode replaced =
                service.convert(" ab-12 ", TicketCode.class);
        System.out.println("afterRegister=" + replaced);

        service.removeConvertible(String.class, TicketCode.class);
        System.out.println("removedAgain="
                + service.canConvert(String.class, TicketCode.class));
    }
}
```

Điểm thiết kế của `TicketCode`: constructor nhận `String` là private và không có static `valueOf(String)`; do đó ví dụ không vô tình tạo thêm đường chuyển đổi tự động String → TicketCode bằng cơ chế object-to-object. Registry cần custom converter đã đăng ký.

### 7.3. Chạy chương trình

Từ thư mục dự án:

```bash
gradle -q run
```

Nếu dự án có Gradle wrapper, dùng `./gradlew -q run` trên macOS/Linux hoặc `gradlew.bat -q run` trên Windows.

**Stdout mong đợi:**

```text
registered=TicketCode[value=AB-12]
afterRemove=false
afterRegister=TicketCode[value=NEW-AB-12]
removedAgain=false
```

Giải thích:

1. `addConverter(new PlainTicketCodeConverter())` đăng ký converter `String → TicketCode`.
2. `convert(" ab-12 ", TicketCode.class)` chạy converter đầu tiên, trim, viết hoa và tạo `TicketCode[value=AB-12]`.
3. `removeConvertible(String.class, TicketCode.class)` gỡ đường chuyển đổi của cặp này. Vì `TicketCode` không có constructor/static factory nhận String, không còn fallback chuyển đổi mặc định; `canConvert` trả `false`.
4. `addConverter(new PrefixedTicketCodeConverter())` đăng ký lại cặp đó với quy tắc mới, kết quả có tiền tố `NEW-`.
5. Gỡ thêm lần nữa, service không còn converter cho cặp được kiểm thử.

Ví dụ tạo một `DefaultFormattingConversionService` mới trong `main`; không chỉnh service static dùng chung của hệ thống. Đây là vòng đời đơn giản để minh họa cấu hình trước khi dùng.

## 8. Đăng ký converter trong ứng dụng Spring MVC

Trong Spring MVC, điểm mở rộng thông dụng là `WebMvcConfigurer.addFormatters(FormatterRegistry registry)`:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCustomerIdConverter());
    }
}
```

`FormatterRegistry` kế thừa `ConverterRegistry` nên có thể đăng ký converter, đồng thời hỗ trợ `Formatter`, parser/printer và annotation formatter factory. Đây là cách tích hợp converter vào hệ thống formatting/conversion do MVC quản lý; không cần tự tạo một `ConversionService` khác rồi thay thế nếu chỉ muốn bổ sung một converter.

Một converter ví dụ:

```java
public final class StringToCustomerIdConverter
        implements Converter<String, CustomerId> {

    @Override
    public CustomerId convert(String source) {
        return CustomerId.from(source.trim());
    }
}
```

Đây là **đoạn minh họa tích hợp**, cần có class `CustomerId`, package/import, configuration scan và dependency Spring MVC phù hợp. Sau khi đăng ký, Spring có thể sử dụng converter khi bind property hoặc đối số controller có kiểu đích `CustomerId`, miễn là source/target metadata phù hợp.

### Nếu cần nhiều converter/formatter liên quan

Có thể dùng `FormatterRegistrar` để gom cấu hình:

```java
public final class CustomerFormattingRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCustomerIdConverter());
        registry.addFormatterForFieldType(
                CustomerCode.class, new CustomerCodeFormatter());
    }
}
```

Với registrar, nhóm quy tắc của một domain có thể được gắn vào registry tại một điểm cấu hình. Đoạn này giả định `CustomerCodeFormatter` triển khai `Formatter<CustomerCode>` và các kiểu domain đã được khai báo.

**Thay thế hoặc remove trong MVC:** `addFormatters` được gọi trong quá trình cấu hình ứng dụng; đây không phải nơi để mỗi request thay đổi registry dùng chung. Nếu muốn loại một converter, tốt nhất xây dựng registry cuối cùng ngay trong cấu hình, không đăng ký converter rồi tháo ra theo luồng request. Nếu thực sự phải sửa registry, hãy nắm rõ phạm vi service và cặp kiểu bị ảnh hưởng.

## 9. DataBinder sử dụng ConversionService như thế nào?

`DataBinder` có thể dùng một `ConversionService` để chuyển dữ liệu trước khi ghi property. Có thể cấu hình một binder riêng:

```java
DataBinder binder = new DataBinder(target, "form");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

Đoạn này là ví dụ minh họa, cần có `target`, `propertyValues` và imports phù hợp. `setConversionService(...)` đặt ConversionService cho binder; nó không thêm hoặc gỡ converter khỏi registry. Muốn thay đổi converter, hãy cấu hình registry đứng sau service.

Một ví dụ dùng MVC:

```java
@InitBinder("customerForm")
void initCustomerBinder(WebDataBinder binder) {
    binder.setConversionService(applicationConversionService);
}
```

Đây là **một lựa chọn cấu hình theo binder**, không phải mẫu luôn cần thiết. Nếu MVC đã có shared formatting conversion service với converter được đăng ký qua `WebMvcConfigurer`, thông thường không cần tự thay conversion service cho mỗi model attribute. Cấu hình binder riêng có thể vô tình bỏ mất formatter/converter mặc định nếu service được truyền vào thiếu các cấu hình đó.

**`ConversionService` và `PropertyEditor` có thể cùng tồn tại.** Spring có hệ thống conversion hiện đại nhưng vẫn hỗ trợ JavaBeans `PropertyEditor` cho một số nhu cầu binding. Khi cả hai được cấu hình, cần hiểu cách binder ưu tiên cơ chế phù hợp với property/value thay vì mặc định rằng custom converter luôn được gọi.

## 10. Converter, Formatter và PropertyEditor khác nhau thế nào?

| Thành phần | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `Converter<S,T>` | Logic chuyển kiểu tổng quát, strongly typed | `String → CustomerId` |
| `ConverterFactory<S,R>` | Tạo converter cho một họ kiểu đích | `String → Enum subclass` |
| `GenericConverter` | Hỗ trợ nhiều cặp kiểu, đọc TypeDescriptor | `Collection<?> → Collection<?>` |
| `Formatter<T>` | Parse và print giá trị cho môi trường client, có Locale | `String ↔ LocalDate` |
| `PropertyEditor` | API JavaBeans cũ, thường gắn với một property/binder | `StringTrimmerEditor` |

Dùng `Converter` khi chỉ cần chuyển đổi kiểu. Dùng `Formatter` khi cần **parse/print hiển thị**, đặc biệt với ngày, số và locale. Dùng `PropertyEditor` khi tích hợp code cũ hoặc cần editor theo property; đừng tự xây editor mới chỉ để thay thế converter hiện đại nếu SPI phù hợp hơn.

Với ngày tháng/tiền tệ, annotation như `@DateTimeFormat` hoặc `@NumberFormat` có thể giúp chọn quy tắc theo field mà không phải đăng ký một converter chung quá rộng. Với nhiều formatter liên quan, `FormatterRegistrar` giúp gom cấu hình.

## 11. Phạm vi, thread-safety và quản lý vòng đời

Spring thiết kế `ConversionService` để thường được cấu hình khi khởi tạo ứng dụng rồi chia sẻ giữa các luồng. Các converter/formatter được đăng ký vào service dùng chung vì thế cũng phải được thiết kế cẩn thận:

- Hãy làm converter stateless, hoặc bảo đảm mọi trạng thái có thể thay đổi được quản lý an toàn giữa các thread.
- Tránh gọi `addConverter`/`removeConvertible` theo từng request; thay đổi registry dùng chung có thể ảnh hưởng request khác.
- Nếu một controller cần quy tắc đặc biệt, cân nhắc binder/conversion service riêng hoặc converter field-specific thay vì sửa quy tắc toàn ứng dụng.
- Không mutate instance trả về bởi một bean service toàn cục sau khi ứng dụng đã chạy nếu không có kế hoạch đồng bộ và kiểm soát thay đổi.
- Ghi nhận rõ converter nào là mặc định của Spring, converter nào do module nghiệp vụ sở hữu; điều này quan trọng khi remove theo cặp.

Cũng nên bảo đảm converter xử lý input rỗng và sai định dạng theo contract. Một converter ném `IllegalArgumentException` khi đầu vào sai có thể dẫn đến lỗi conversion trong binding; ứng dụng nên hiển thị lỗi theo field, không để exception nội bộ bị trả trực tiếp cho client.

## 12. Lỗi phổ biến khi đăng ký, thay thế hoặc gỡ converter

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gọi `addConverter` không biên dịch | Biến chỉ có kiểu `ConversionService` | Dùng `ConverterRegistry` hoặc `ConfigurableConversionService` |
| `canConvert` trả false sau đăng ký | Sai source/target type hoặc converter generic không suy luận được | Kiểm tra generic type/cặp kiểu đã đăng ký |
| `canConvert` true nhưng `convert` lỗi | Input thực tế không hợp lệ, converter ném exception | Test dữ liệu đại diện và validate input |
| Gỡ converter xong default conversion lỗi | `removeConvertible` gỡ cả cặp mà converter mặc định sử dụng | Chỉ remove cặp do ứng dụng sở hữu hoặc tạo service riêng |
| Converter không chạy trong MVC | Chưa đăng ký vào registry MVC hoặc binder dùng service khác | Dùng `WebMvcConfigurer.addFormatters`, kiểm tra phạm vi |
| Thêm converter thứ hai nhưng kết quả không như mong đợi | Nhiều converter/đường chuyển đổi có thể khớp | Cấu hình registry rõ ràng, test cặp và metadata thực tế |
| Dùng `Converter` cho parse ngày theo locale | Converter không nhận Locale như Formatter | Dùng `Formatter<T>` hoặc `@DateTimeFormat` |
| Chỉnh registry mỗi request gây lỗi không ổn định | Service chia sẻ, mutable registry bị thay đổi trong lúc dùng | Đăng ký khi startup, tránh runtime mutation |
| `removeConvertible` không làm `canConvert` false | Converter khác hoặc fallback vẫn hỗ trợ cặp | Kiểm tra toàn bộ registry/đường chuyển đổi; không chỉ một converter |
| Service custom làm mất String → Number, enum, collection | Thay service mặc định bằng registry rỗng/thiếu converter cơ bản | Dùng `DefaultConversionService`/`DefaultFormattingConversionService` làm nền nếu phù hợp |
| Dữ liệu sai kiểu gây exception chung | Không xử lý conversion error ở binding layer | Đọc `BindingResult`, trả lỗi theo field và input contract |

### Gợi ý debug

Khi converter không được gọi:

1. In/log đúng class nguồn và đích tại điểm bind.
2. Gọi `canConvert(sourceType, targetType)` trên **chính service binder đang dùng**.
3. Xác nhận converter đã đăng ký vào đúng registry và thời điểm cấu hình trước khi binding bắt đầu.
4. Kiểm tra converter có điều kiện (nếu là `ConditionalConverter`) và metadata `TypeDescriptor`.
5. Kiểm tra binder có service khác được set qua `setConversionService(...)` không.
6. Thử một unit test trực tiếp cho converter, một test cho service, rồi một integration test MVC.

Không nên chỉ kiểm tra một bean tên `conversionService` trong context rồi kết luận tất cả binder đều đang dùng đúng instance đó; cấu hình MVC hoặc binder cục bộ có thể chọn một service khác.

## 13. Bài tập tự luyện

Tạo hai converter cho `String → TicketCode`:

- Converter A trim rồi viết hoa.
- Converter B thêm tiền tố `NEW-` sau khi chuẩn hóa.

Trả lời:

1. Vì sao biến có kiểu `ConversionService` không gọi được `addConverter`?
2. `removeConvertible` nhận một instance converter hay cặp kiểu?
3. Vì sao remove converter của `String → Integer` trên service mặc định có thể ảnh hưởng binder khác?
4. Khi nào nên dùng `Formatter` thay vì `Converter`?
5. Vì sao không nên thay đổi registry dùng chung trong mỗi request?
6. Nếu `canConvert` trả true nhưng dữ liệu cụ thể làm `convert` ném exception, điều đó có mâu thuẫn không?

**Đáp án định hướng:** (1) `ConversionService` chỉ khai báo API đọc/convert, còn đăng ký thuộc `ConverterRegistry`. (2) Cặp `sourceType/targetType`. (3) Registry có thể chứa converter mặc định Spring cho cặp đó; remove sẽ tác động đường chuyển đổi chung. (4) Khi cần parse/print hiển thị và Locale. (5) Service thường dùng chung cho nhiều request/thread. (6) Không: khả năng chuyển theo cặp kiểu không đảm bảo mọi giá trị nguồn đều hợp lệ.

## 14. Ghi nhớ và tài liệu chính thức

- **`ConversionService`** dùng để `canConvert` và `convert`.
- **`ConverterRegistry`** dùng để `addConverter`, `addConverterFactory` và `removeConvertible`.
- **`ConfigurableConversionService`** hỗ trợ cả hai vai trò.
- Để thay converter của một cặp, thường remove cặp đó rồi add converter mới; API remove làm việc theo **kiểu nguồn/đích**, không phải tên instance.
- **`DefaultConversionService`** và **`DefaultFormattingConversionService`** cung cấp nền converter/formatter thông dụng; đừng bỏ chúng vô tình khi thay service.
- Trong Spring MVC, **`WebMvcConfigurer.addFormatters(FormatterRegistry)`** là cách chuẩn để cấu hình converter/formatter toàn cục cho MVC.
- `DataBinder.setConversionService` chỉ gắn service cho binder; nó không thêm converter vào service.
- Đăng ký ở giai đoạn cấu hình ứng dụng, ưu tiên converter stateless/thread-safe, và kiểm tra tác động của remove đối với converter mặc định.

Nguồn chính thức:

- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `ConverterRegistry`, converter và các implementation.
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `FormatterRegistry` và `FormatterRegistrar`.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký converter/formatter bằng `WebMvcConfigurer.addFormatters`.
- [Spring Framework — ConfigurableConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/convert/support/ConfigurableConversionService.html): API cấu hình service.
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): `addConverter`, `addConverterFactory` và `removeConvertible`.
