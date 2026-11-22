# GenericConverter và nhiều cặp kiểu nguồn đích trong Spring

## 1. Khi nào cần GenericConverter?

Spring có hệ thống chuyển đổi kiểu (type conversion) để biến một giá trị đầu vào thành kiểu mà property, constructor hoặc API đang yêu cầu. Ví dụ form gửi `"42"` nhưng đối tượng Java cần `Long`; query parameter gửi `"SHIPPED"` nhưng model cần enum `OrderStatus`.

Với một cặp kiểu đơn giản, interface `Converter<S, T>` là lựa chọn tự nhiên:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Nếu một lớp phải xử lý **nhiều cặp kiểu nguồn–đích**, hoặc quyết định conversion cần dựa vào metadata của field/parameter, Spring cung cấp **`GenericConverter`**. Nó linh hoạt hơn `Converter`: khai báo một tập `ConvertiblePair`, nhận giá trị nguồn ở dạng `Object`, và được cung cấp `TypeDescriptor` của cả nguồn lẫn đích.

Ví dụ một converter có thể hỗ trợ đồng thời:

| Kiểu nguồn | Kiểu đích | Ý nghĩa |
| --- | --- | --- |
| `String` | `CustomerId` | Đổi chuỗi số thành định danh khách hàng |
| `Long` | `CustomerId` | Bọc số đã có kiểu thành định danh |
| `String` | `OrderStatus` | Đổi mã trạng thái thành enum |

Một `GenericConverter` có thể thực hiện cả ba cặp trong cùng một class. Spring dùng danh sách cặp kiểu để tìm converter phù hợp, sau đó gọi `convert(source, sourceType, targetType)`.

**`TypeDescriptor` là điểm khác biệt quan trọng.** Nó mang thêm thông tin về kiểu generic và ngữ cảnh khai báo như field, method parameter, annotation. Nhờ đó converter có thể phân biệt trường hợp `List<Integer>` với `List<String>` dù cả hai có raw type là `List.class`.

Bài dùng **Java 17+ và Spring Framework 6.2.x**. Sau khi học xong, bạn có thể:

- Khai báo nhiều `ConvertiblePair` trong `getConvertibleTypes()`.
- Viết logic chuyển đổi bằng `TypeDescriptor` nguồn và đích.
- Đăng ký converter vào `ConversionService`.
- Hiểu khi nào cần `ConditionalGenericConverter` và `matches(...)`.
- Phân biệt `GenericConverter` với `Converter`, `ConverterFactory` và `ConversionService`.
- Kiểm thử cả conversion thành công, thất bại và dữ liệu generic.

## 2. Các interface trong hệ thống conversion

Spring có một số SPI khác nhau, mỗi interface phù hợp một mức độ phức tạp:

| API | Phạm vi | Nên dùng khi |
| --- | --- | --- |
| `Converter<S, T>` | Một cặp kiểu nguồn–đích | Logic đơn giản, kiểu tĩnh rõ ràng |
| `ConverterFactory<S, R>` | Một nguồn sang một họ kiểu đích có chung base type | Nhiều subtype đích có cùng quy tắc |
| `GenericConverter` | Nhiều cặp kiểu nguồn–đích, có metadata `TypeDescriptor` | Nhiều kiểu hoặc cần generic/annotation context |
| `ConditionalGenericConverter` | Như GenericConverter, thêm điều kiện chọn converter | Chỉ áp dụng khi field/parameter thỏa điều kiện |
| `ConversionService` | API runtime để hỏi và thực hiện conversion | Thành phần gọi conversion, không phải SPI bắt buộc để tự viết converter |

Không nên chọn `GenericConverter` chỉ vì nó mạnh hơn. Tài liệu Spring khuyên ưu tiên `Converter` hoặc `ConverterFactory` khi chúng đã đáp ứng yêu cầu, vì chúng dễ đọc và kiểm tra kiểu ở compile time hơn.

### GenericConverter có những method nào?

Chữ ký cốt lõi:

~~~java
public interface GenericConverter {

    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

Đây là chữ ký API để học, không phải class tự định nghĩa thay Spring.

- `getConvertibleTypes()` trả tập những cặp source class → target class mà converter có thể xử lý.
- `convert(...)` thực hiện chuyển đổi. `source` có kiểu `Object`; vì vậy phải kiểm tra/diễn giải dựa trên descriptor hoặc class thực tế.
- `sourceType` mô tả kiểu nguồn và ngữ cảnh khai báo.
- `targetType` mô tả kiểu đích, bao gồm metadata generic hoặc annotation nếu có.
- Nếu không có cặp nào phù hợp, converter không nên được đăng ký như thể nó hỗ trợ kiểu đó.

`GenericConverter.ConvertiblePair` lưu hai class nguồn và đích. Một cặp `String.class → CustomerId.class` không tự động có nghĩa converter hỗ trợ `Long.class → CustomerId.class`; muốn hỗ trợ cả hai phải khai báo cả hai.

## 3. ConvertiblePair: đăng ký nhiều cặp kiểu

Một converter có thể trả về nhiều cặp trong một tập:

~~~java
@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(
            new ConvertiblePair(String.class, CustomerId.class),
            new ConvertiblePair(Long.class, CustomerId.class),
            new ConvertiblePair(String.class, OrderStatus.class)
    );
}
~~~

Đây là fragment trong một class implements `GenericConverter`. Tập cặp phải nhất quán với những nhánh mà `convert(...)` thực sự xử lý.

Khi `ConversionService` tìm conversion:

1. Nhận kiểu nguồn và kiểu đích, có thể kèm `TypeDescriptor`.
2. Tìm converter có `ConvertiblePair` tương thích.
3. Nếu converter có điều kiện, kiểm tra thêm `matches(...)`.
4. Gọi `convert(...)` với source và hai descriptor.
5. Trả object thuộc kiểu đích hoặc ném lỗi conversion nếu dữ liệu không hợp lệ.

**Đăng ký cặp kiểu không đồng nghĩa chuyển đổi luôn thành công.** Ví dụ `"abc"` vẫn có source type `String` và target `CustomerId` phù hợp với cặp đã đăng ký, nhưng logic parse số có thể thất bại. Lỗi dữ liệu phải được biểu diễn bằng exception conversion phù hợp, không trả một object đích giả.

## 4. Ví dụ hoàn chỉnh: một GenericConverter xử lý ba cặp kiểu

Ví dụ dùng định danh khách hàng và trạng thái đơn hàng. Mục tiêu là cho thấy một converter duy nhất có thể xử lý nhiều cặp mà không cần viết ba class `Converter` khác nhau.

### 4.1. Tạo project Gradle

Cấu trúc:

~~~text
generic-converter-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/GenericConverterDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'generic-converter-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.GenericConverterDemo'
}
~~~

`spring-core` chứa hệ thống conversion. Ví dụ cố định Spring Framework 6.2.14 để dễ tái hiện; trong dự án Spring Boot thực tế, để BOM của Boot quản lý phiên bản tương thích.

### 4.2. Tệp Java chạy được

Tệp `src/main/java/demo/GenericConverterDemo.java`:

~~~java
package demo;

import java.util.Set;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.GenericConversionService;

public class GenericConverterDemo {

    public record CustomerId(long value) {}

    public enum OrderStatus {
        CREATED, SHIPPED, CANCELLED
    }

    public static final class CatalogConverter
            implements GenericConverter {

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return Set.of(
                    new ConvertiblePair(
                            String.class, CustomerId.class),
                    new ConvertiblePair(
                            Long.class, CustomerId.class),
                    new ConvertiblePair(
                            String.class, OrderStatus.class)
            );
        }

        @Override
        public Object convert(
                Object source,
                org.springframework.core.convert.TypeDescriptor sourceType,
                org.springframework.core.convert.TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            Class<?> target = targetType.getObjectType();
            Class<?> origin = sourceType.getObjectType();

            if (target == CustomerId.class) {
                if (origin == String.class) {
                    return new CustomerId(
                            Long.parseLong((String) source));
                }
                if (origin == Long.class) {
                    return new CustomerId((Long) source);
                }
            }

            if (target == OrderStatus.class
                    && origin == String.class) {
                return OrderStatus.valueOf(
                        ((String) source).trim().toUpperCase());
            }

            throw new IllegalArgumentException(
                    "Cặp kiểu chưa được hỗ trợ: "
                    + origin.getSimpleName() + " -> "
                    + target.getSimpleName());
        }
    }

    public static void main(String[] args) {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new CatalogConverter());

        CustomerId fromText =
                service.convert("42", CustomerId.class);
        CustomerId fromNumber =
                service.convert(7L, CustomerId.class);
        OrderStatus status =
                service.convert("shipped", OrderStatus.class);

        System.out.println("fromText=" + fromText.value());
        System.out.println("fromNumber=" + fromNumber.value());
        System.out.println("status=" + status);
    }
}
~~~

Các thành phần quan trọng:

- `CatalogConverter` công bố ba cặp trong `getConvertibleTypes()`.
- `GenericConversionService` là registry/service cho phép gọi `addConverter(...)`.
- `convert("42", CustomerId.class)` chọn cặp `String → CustomerId`.
- `convert(7L, CustomerId.class)` chọn cặp `Long → CustomerId`.
- `convert("shipped", OrderStatus.class)` chọn cặp `String → OrderStatus`.
- `getObjectType()` trả class thực tế được boxing cho kiểu primitive nếu có; ví dụ này chỉ dùng kiểu wrapper/record/enum.

Chạy ở thư mục project có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout của chương trình Java:

~~~text
fromText=42
fromNumber=7
status=SHIPPED
~~~

`GenericConversionService` được dùng ở đây để tập trung vào ba cặp tùy chỉnh, tránh lẫn với converter built-in của `DefaultConversionService`. Khi ứng dụng muốn cả các conversion mặc định của Spring (String → number, enum, collection, v.v.), có thể cân nhắc `DefaultConversionService` rồi đăng ký converter bổ sung.

### 4.3. Bổ sung xử lý lỗi conversion

Ví dụ hiện tại dùng `Long.parseLong` và `OrderStatus.valueOf`. Nếu input sai, các hàm JDK có thể ném `NumberFormatException` hoặc `IllegalArgumentException`. Trong hệ thống production, hãy để lỗi được bọc/diễn giải theo contract conversion của Spring.

Có thể chủ động ném `org.springframework.core.convert.ConversionFailedException` khi muốn cung cấp metadata nguồn/đích:

~~~java
throw new ConversionFailedException(
        sourceType,
        targetType,
        source,
        new IllegalArgumentException("Mã định danh không hợp lệ")
);
~~~

Đây là fragment trong `convert(...)`; `sourceType` và `targetType` ở đây là các tham số `TypeDescriptor` của method. Nếu cần thông báo phù hợp, không đưa raw input nhạy cảm vào exception message. Với demo ngắn, các exception JDK vẫn đủ minh họa trường hợp dữ liệu sai; Spring conversion infrastructure có thể bọc chúng thành lỗi conversion ở tầng gọi.

## 5. TypeDescriptor: metadata vượt qua raw Class

`GenericConverter` nhận cả `Class` thô và `TypeDescriptor`. Vì vậy có thể sử dụng thông tin mà `Class<?>` đơn thuần không giữ được.

Ví dụ hai khai báo:

~~~java
List<Integer> quantities;
List<String> labels;
~~~

Cả hai đều có raw type `List.class` ở runtime, do type erasure. Nhưng `TypeDescriptor` có thể biểu diễn element type:

- descriptor của `List<Integer>` biết phần tử mong muốn là `Integer`;
- descriptor của `List<String>` biết phần tử mong muốn là `String`.

Tương tự, descriptor có thể cho biết annotation ở field hoặc method parameter. Điều đó cho phép converter phân biệt cách chuyển đổi dựa trên **nơi kiểu được khai báo**, không chỉ tên class.

### 5.1. Lấy TypeDescriptor cho collection

Trong Spring có API dựng descriptor cho collection:

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String[].class);

TypeDescriptor target = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class));
~~~

Đây là fragment cần import `org.springframework.core.convert.TypeDescriptor` và `java.util.List`. Descriptor đích biểu diễn `List<Integer>` chứ không đơn thuần `List.class`.

### 5.2. Dùng conversion service chuyển String[] thành List<Integer>

Đoạn sau có thể chạy trong một method Java với `DefaultConversionService`:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

TypeDescriptor source = TypeDescriptor.valueOf(String[].class);
TypeDescriptor target = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(
        new String[]{"10", "20"},
        source,
        target);

System.out.println(converted);
~~~

Stdout mong đợi:

~~~text
[10, 20]
~~~

Spring có converter tích hợp cho array → collection và chuyển từng phần tử theo element descriptor. Chính metadata `Integer` giúp kết quả là `List<Integer>`, không phải `List<String>`.

Ví dụ trên sử dụng **built-in converters** của `DefaultConversionService`. Nó không phải converter tự viết ở mục 4; mục đích là thấy lợi ích của descriptor generic khi gọi cùng `ConversionService`.

### 5.3. Field annotation và metadata

`TypeDescriptor` còn cung cấp annotation metadata thông qua nơi khai báo nguồn/đích. Ví dụ, một custom converter có thể chỉ hoạt động nếu field đích mang annotation đánh dấu; một converter có thể đọc annotation từ `targetType` và quyết định cách parse.

Không nên tự viết logic dùng reflection để đoán mọi metadata nếu `TypeDescriptor` đã cung cấp API tương ứng. Khi làm converter có điều kiện theo annotation, thường nên triển khai `ConditionalGenericConverter` và đặt tiêu chí trong `matches(...)`.

## 6. ConditionalGenericConverter: nhiều cặp nhưng chỉ khớp khi đủ điều kiện

Một `GenericConverter` chọn theo cặp class. Đôi khi hai field có cùng source/target class nhưng cần conversion khác nhau tùy ngữ cảnh, chẳng hạn:

- `String → AccountId` chỉ được phép ở field có `@ExternalId`.
- `String → AccountId` ở field khác phải được xử lý bởi converter khác.
- Một quy tắc conversion chỉ áp dụng nếu source/target descriptor chứa annotation cụ thể.

Spring cung cấp `ConditionalGenericConverter`, kết hợp `GenericConverter` và `ConditionalConverter`:

~~~java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
~~~

Trong đó có method:

~~~java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Đây là chữ ký interface dùng để học, không phải code tự định nghĩa lại Spring.

Ví dụ hình thức:

~~~java
@Override
public boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {
    return targetType.hasAnnotation(ExternalCode.class);
}
~~~

Đây là fragment trong implementation `ConditionalGenericConverter`. `ExternalCode` là annotation tự định nghĩa của ứng dụng và cần được khai báo runtime-retained, target phù hợp với field/parameter. Ngoài điều kiện annotation, nên kiểm tra source/target descriptor hoặc `getConvertibleTypes()` để không match quá rộng.

Vai trò của `matches(...)` là **quyết định converter có áp dụng trong ngữ cảnh hiện tại không**, trước khi chạy `convert(...)`. Nó không dùng để thực hiện conversion, không nên thay đổi dữ liệu và nên trả kết quả nhất quán.

### Tránh điều kiện quá rộng

Nếu `matches` chỉ trả `true` cho mọi target có annotation nhưng converter lại không hỗ trợ mọi kiểu nguồn, cần thu hẹp điều kiện bằng `sourceType.getObjectType()` và `targetType.getObjectType()`. Một converter match nhầm có thể khiến conversion service chọn sai chiến lược hoặc ném exception không mong muốn.

Dùng `ConditionalGenericConverter` khi có điều kiện thật sự. Nếu chỉ có ba cặp class cố định, `GenericConverter` thuần ở mục 4 đã đủ.

## 7. Nhiều cặp kiểu hay ConverterFactory?

Cần phân biệt hai cách mở rộng:

### Nhiều cặp rời rạc: GenericConverter

Ví dụ:

~~~text
String -> CustomerId
Long   -> CustomerId
String -> OrderStatus
UUID   -> CustomerId
~~~

Đây là tập các cặp không nhất thiết cùng một họ. `GenericConverter` biểu diễn tự nhiên bằng `Set<ConvertiblePair>`.

### Một nguồn sang một họ kiểu đích: ConverterFactory

Ví dụ một factory chuyển `String` sang các enum subtype khác nhau:

~~~java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
~~~

Đây là **chữ ký rút gọn** của `ConverterFactory`. Nếu tất cả target đều là subtype của cùng một base type `R` và logic có chung cấu trúc, `ConverterFactory` có thể gọn hơn việc khai báo từng cặp.

So sánh:

| Yêu cầu | Lựa chọn |
| --- | --- |
| String → enum bất kỳ trong một họ | ConverterFactory |
| String → CustomerId; Long → CustomerId; String → OrderStatus | GenericConverter |
| Một kiểu nguồn, một kiểu đích cố định | Converter<S,T> |
| Nhiều cặp nhưng chỉ dùng khi field có annotation | ConditionalGenericConverter |

Không chọn `GenericConverter` chỉ vì có từ “generic”. `ConverterFactory` cũng không phải generic collection converter; factory giải quyết một họ kiểu đích theo tham số class.

## 8. Đăng ký GenericConverter trong ứng dụng

### 8.1. Đăng ký trực tiếp bằng registry

Ví dụ ở mục 4:

~~~java
GenericConversionService service =
        new GenericConversionService();
service.addConverter(new CatalogConverter());
~~~

Đây là cách phù hợp trong test, utility hoặc thành phần cần tạo conversion service riêng. Converter phải được đăng ký trước khi dùng.

### 8.2. Dùng DefaultConversionService

`DefaultConversionService` cung cấp tập converter tiêu chuẩn của Spring. Có thể đăng ký converter riêng:

~~~java
DefaultConversionService service =
        new DefaultConversionService();
service.addConverter(new CatalogConverter());
~~~

Khi làm vậy, converter của ứng dụng bổ sung vào khả năng chuyển đổi mặc định. Nếu hai converter cùng hỗ trợ một cặp, thứ tự/độ cụ thể và thuật toán chọn converter cần được xem xét; tránh đăng ký những converter xung đột không có chủ đích.

### 8.3. Spring MVC qua WebMvcConfigurer

Trong Spring MVC, có thể bổ sung converter vào registry:

~~~java
@Configuration
public class WebConversionConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new CatalogConverter());
    }
}
~~~

Đây là **class cấu hình đầy đủ** khi thêm các import `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry` và `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` cùng class `CatalogConverter` phù hợp.

`addFormatters(...)` là điểm đăng ký converter/formatter cho conversion service của MVC. Sau khi đăng ký, conversion có thể tham gia binding request parameters, form fields và các điểm MVC sử dụng conversion service.

**Không tạo một `GenericConversionService` riêng trong controller cho mỗi request.** Conversion service được thiết kế để cấu hình khi khởi tạo và tái sử dụng. Tài liệu Spring mô tả conversion service là stateless và phù hợp chia sẻ giữa nhiều thread; converter tùy chỉnh cũng cần tuân theo nguyên tắc không giữ mutable state theo request.

## 9. Dùng ConversionService để hỏi và thực hiện chuyển đổi

`ConversionService` là facade để hỏi khả năng và thực hiện conversion:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Đây là chữ ký API minh họa.

Ví dụ:

~~~java
if (service.canConvert(String.class, CustomerId.class)) {
    CustomerId id = service.convert("42", CustomerId.class);
}
~~~

Đoạn này dùng service đã đăng ký `CatalogConverter`. `canConvert` kiểm tra **có converter phù hợp về kiểu hay không**; nó không bảo đảm chuỗi cụ thể sẽ parse thành công. `"abc"` vẫn có thể khiến `convert(...)` thất bại dù `canConvert(String.class, CustomerId.class)` là `true`.

Khi nguồn/đích cần metadata generic hoặc annotation, dùng overload nhận `TypeDescriptor` thay vì chỉ class. Đây là cách giữ thông tin `List<Integer>` hoặc annotation trên field.

### Null và primitive

Conversion với `null` cần chú ý kiểu đích. `null` không thể gán vào primitive như `int`; chuyển đổi có thể thất bại. Với wrapper `Integer`, `null` thường có thể giữ nguyên theo quy tắc converter/ConversionService. Converter tùy chỉnh nên quyết định rõ cách xử lý null, không parse hoặc gọi method trên source null.

Trong ví dụ mục 4, `convert` trả `null` nếu source null. Điều đó phù hợp target record wrapper/enum nhưng chưa chắc phù hợp property primitive. Caller cần chọn kiểu đích và chính sách null thích hợp.

## 10. Conversion exception và cách chẩn đoán

Các lỗi thường gặp:

| Lỗi | Nguyên nhân có thể |
| --- | --- |
| `ConverterNotFoundException` | Không có converter cho cặp kiểu nguồn–đích |
| `ConversionFailedException` | Có converter phù hợp nhưng conversion thất bại khi xử lý giá trị |
| `IllegalArgumentException` trong converter | Input không hợp lệ hoặc code của converter tự ném |
| Không gọi được converter mong muốn | Cặp kiểu chưa khai báo hoặc `matches(...)` trả false |
| Kết quả collection sai element type | Dựng `TypeDescriptor` đích thiếu generic element metadata |

Ví dụ trong mục 4, `Long.parseLong("abc")` ném `NumberFormatException`. Khi được gọi qua conversion service, lỗi có thể được bọc thành lỗi conversion tùy đường gọi. Nếu cần tạo `ConversionFailedException` rõ ràng, có thể bọc exception cùng descriptor nguồn/đích như sau:

~~~java
try {
    long value = Long.parseLong((String) source);
    return new CustomerId(value);
} catch (NumberFormatException ex) {
    throw new ConversionFailedException(
            sourceType, targetType, source, ex);
}
~~~

Đây là fragment thay cho nhánh `String → CustomerId`. Thông điệp dành cho client nên được quyết định ở tầng binding/API; đừng để chuỗi exception nội bộ trở thành contract lỗi công khai.

Khi converter được dùng từ Spring MVC, exception conversion có thể được chuyển thành binding error trong `BindingResult`. Khi gọi `ConversionService` trực tiếp, caller cần bắt/xử lý exception theo hợp đồng riêng của mình.

## 11. Kiểm thử GenericConverter

Cần kiểm tra mọi cặp đã khai báo, không chỉ một cặp đại diện.

Ví dụ JUnit 5:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.GenericConversionService;

import static org.junit.jupiter.api.Assertions.*;

class CatalogConverterTest {

    private final GenericConversionService service =
            new GenericConversionService();

    CatalogConverterTest() {
        service.addConverter(
                new GenericConverterDemo.CatalogConverter());
    }

    @Test
    void convertsAllDeclaredPairs() {
        var fromText = service.convert(
                "42", GenericConverterDemo.CustomerId.class);
        var fromLong = service.convert(
                7L, GenericConverterDemo.CustomerId.class);
        var status = service.convert(
                "shipped", GenericConverterDemo.OrderStatus.class);

        assertEquals(42L, fromText.value());
        assertEquals(7L, fromLong.value());
        assertEquals(
                GenericConverterDemo.OrderStatus.SHIPPED,
                status);
    }

    @Test
    void rejectsInvalidIdentifier() {
        assertThrows(RuntimeException.class, () ->
                service.convert(
                        "not-a-number",
                        GenericConverterDemo.CustomerId.class));
    }
}
~~~

Đây là tệp test độc lập khi class demo và JUnit 5 cùng package. Trong `build.gradle`, bổ sung:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Test cần JUnit dependency trên test classpath. Assertion `RuntimeException` trong ví dụ chỉ nhằm chứng minh conversion sai bị từ chối; với hợp đồng production, nên kiểm tra cụ thể `ConversionFailedException` nếu converter đã chủ động bọc lỗi như mục 10.

Các ca nên có thêm:

1. Mỗi `ConvertiblePair` đã khai báo đều chuyển được dữ liệu hợp lệ.
2. Input không hợp lệ cho từng cặp.
3. Kiểu nguồn/đích chưa đăng ký: `canConvert` và `convert`.
4. `null` và primitive target.
5. Generic element descriptor của collection.
6. `matches` true/false với annotation hoặc field context.
7. Converter không giữ state và dùng ổn định khi nhiều request cùng gọi.

## 12. Thread safety và nguyên tắc thiết kế converter

Spring mô tả `ConversionService` là stateless và được thiết kế để khởi tạo khi application startup rồi chia sẻ giữa các thread. Tuy nhiên, điều đó không tự biến **custom converter có mutable state** thành thread-safe.

Một converter tốt:

- Không ghi giá trị input hiện tại vào field.
- Không lưu target descriptor/rejected value của request gần nhất trong field.
- Dùng biến cục bộ trong `convert`.
- Chỉ giữ cấu hình bất biến hoặc dependency được thiết kế thread-safe.
- Không biến conversion thành thao tác cập nhật dữ liệu nghiệp vụ có side effect.
- Thực hiện kiểm tra null, kiểu và giới hạn input cần thiết.

Ví dụ converter stateless ở mục 4 chỉ đọc source/descriptor rồi trả một object mới; nó có thể được đăng ký một lần và dùng lại.

Nếu converter cần gọi database để đổi ID thành entity, hãy cân nhắc ranh giới service và transaction. Chuyển đổi kiểu cơ bản thường nên là phép ánh xạ giá trị thuần; việc tải entity/phân quyền có thể thuộc service riêng để tránh ẩn I/O và lỗi nghiệp vụ trong conversion.

## 13. Lỗi thường gặp và cách khắc phục

**Khai báo ConvertiblePair thiếu một cặp.** Dù `convert` có nhánh `Long → CustomerId`, nếu `getConvertibleTypes` không khai báo cặp đó, registry có thể không chọn converter. Luôn đối chiếu hai nơi.

**Nhầm nhiều cặp với nhiều overload method.** `GenericConverter` dùng một `convert(Object, TypeDescriptor, TypeDescriptor)`; việc phân nhánh dựa trên descriptor và source. Không khai báo một method convert cho mỗi cặp như `Converter`.

**Bỏ qua TypeDescriptor.** Chỉ dùng `source.getClass()` và `targetType.getType()` khiến logic không tận dụng generic, annotation và field context. Khi có metadata quan trọng, dùng descriptor.

**Dùng GenericConverter cho logic đơn giản.** Một cặp `String → Money` tĩnh có thể dễ hiểu hơn với `Converter<String, Money>`.

**Viết matches quá rộng.** Conditional converter có thể nhận cặp không phù hợp và làm hỏng đường conversion. Kiểm tra cả source type, target type và điều kiện annotation.

**Cho rằng canConvert đảm bảo giá trị hợp lệ.** Nó xác nhận có converter hỗ trợ cặp kiểu, không thử parse mọi dữ liệu thực tế.

**Trả null không có chính sách.** Null vào primitive target không hợp lệ; cần quy định rõ null behavior.

**Dùng chung formatter/parser mutable.** `SimpleDateFormat` và các parser có state có thể gây race nếu giữ làm field dùng chung. Ưu tiên API immutable như `DateTimeFormatter` hoặc tạo đối tượng theo lần gọi.

**Converter có side effect.** Việc conversion có thể được thực hiện ở nhiều tầng/framework callback; không dùng converter để ghi database, gửi message hoặc cập nhật aggregate.

**Không kiểm thử generic target descriptor.** Chuyển `String[] → List.class` mà không cung cấp element type có thể cho kết quả không như mong muốn. Với kiểu generic, tạo `TypeDescriptor` có element/key/value metadata.

## 14. Checklist áp dụng

- Chọn `Converter`/`ConverterFactory` trước nếu chỉ cần một cặp hoặc một họ kiểu đích đơn giản.
- Khai báo đầy đủ tất cả `ConvertiblePair` mà converter hỗ trợ.
- Đảm bảo mỗi nhánh trong `convert` tương ứng với một cặp đã công bố.
- Dùng `sourceType`/`targetType` khi generic metadata hoặc annotation có ý nghĩa.
- Dùng `ConditionalGenericConverter` chỉ khi cần điều kiện `matches`.
- Đăng ký converter vào `ConversionService`/`FormatterRegistry` ở startup.
- Thiết kế null, lỗi parse và exception mapping rõ ràng.
- Không lưu request-specific mutable state trong converter singleton.
- Test tất cả cặp kiểu, input sai, null, generic metadata và điều kiện matches.

## 15. Ghi nhớ

`GenericConverter` là SPI linh hoạt của Spring cho conversion giữa **nhiều cặp kiểu nguồn–đích**. `getConvertibleTypes()` công bố các cặp hỗ trợ; `convert(...)` thực hiện logic dựa trên giá trị và `TypeDescriptor`; `ConditionalGenericConverter` thêm điều kiện qua `matches(...)`. `ConversionService` là facade đăng ký, hỏi và thực hiện conversion.

Hãy chọn abstraction đơn giản nhất đáp ứng yêu cầu: `Converter` cho một cặp, `ConverterFactory` cho một họ target, và `GenericConverter` khi thực sự cần nhiều cặp/metadata. Đăng ký một lần, giữ converter stateless, và kiểm thử từng cặp để conversion nhất quán trong toàn ứng dụng.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [GenericConverter API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalGenericConverter API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [ConversionService API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [TypeDescriptor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
