# DefaultConversionService và các converter có sẵn trong Spring Framework

Trong Spring Framework, **`ConversionService`** là giao diện thống nhất để kiểm tra và thực hiện chuyển đổi giữa các kiểu Java tại runtime. Thay vì tự viết logic chuyển chuỗi sang số, enum, ngày tháng hay collection tại từng nơi, ứng dụng có thể dùng một conversion service đã đăng ký sẵn nhiều converter phổ biến.

Implementation quan trọng là **`org.springframework.core.convert.support.DefaultConversionService`**. Lớp này mở rộng `GenericConversionService` và tự đăng ký một tập converter phù hợp với phần lớn ứng dụng. Các nhóm chính gồm **scalar converters**, **collection/array converters**, converter cho một số kiểu ngày giờ, buffer và các chuyển đổi object thông dụng. Khi cần kiểu nghiệp vụ riêng, ứng dụng bổ sung converter của mình vào registry.

**Điểm cần nhớ:** `DefaultConversionService` có nhiều converter hữu ích ngay sau khi khởi tạo, nhưng nó không đoán được mọi quy tắc nghiệp vụ, không tự validate, không biến mọi chuỗi thành mọi object, và không đảm bảo mọi subsystem Spring đều dùng chung một instance.

## 1. ConversionService và GenericConversionService

`ConversionService` là API để thực thi conversion. Các phương thức thường dùng:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);

boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

- `canConvert(...)` hỏi xem service có đường chuyển đổi phù hợp theo kiểu nguồn và đích hay không.
- `convert(...)` thực hiện chuyển đổi; nếu không có converter phù hợp hoặc dữ liệu không parse được, có thể phát sinh `ConversionException`, thường thấy là `ConverterNotFoundException` hoặc `ConversionFailedException`.
- Overload nhận `TypeDescriptor` còn giữ metadata về kiểu generic, annotation và đặc điểm field/property; hữu ích khi chuyển collection có kiểu phần tử hoặc conversion phụ thuộc ngữ cảnh.

Các vai trò trong package `org.springframework.core.convert`:

| Thành phần | Vai trò |
| --- | --- |
| `ConversionService` | API sử dụng để kiểm tra và thực hiện conversion |
| `ConverterRegistry` | SPI để đăng ký converter, converter factory hoặc generic converter |
| `ConfigurableConversionService` | Kết hợp khả năng sử dụng và đăng ký converter |
| `GenericConversionService` | Implementation tổng quát, quản lý registry và phân giải converter |
| `DefaultConversionService` | `GenericConversionService` được đăng ký sẵn converter phổ biến |
| `ConversionServiceFactory` | Hỗ trợ tạo service từ tập converter cấu hình |
| `TypeDescriptor` | Mô tả kiểu nguồn/đích cùng metadata ở mức field/property/generic |

Một `GenericConversionService` mới tạo là bộ máy phân giải và quản lý converter, nhưng **không đồng nghĩa đã có đầy đủ converter chuẩn**. Khi cần bộ mặc định, hãy tạo `DefaultConversionService` hoặc gọi helper `DefaultConversionService.addDefaultConverters(registry)` trên một registry phù hợp.

## 2. DefaultConversionService đăng ký gì?

Dùng trực tiếp:

~~~java
ConversionService service = new DefaultConversionService();
~~~

Constructor của `DefaultConversionService` gọi `addDefaultConverters(this)`. Bộ mặc định được thiết kế cho nhiều tình huống thường gặp. Tài liệu Spring phân loại các converter đáng chú ý thành scalar, collection và các converter cơ bản từ `Object` sang `String`. Source của Spring còn cho thấy các nhóm bổ sung như byte buffer, ngày/giờ, timezone, object-to-object và Optional. Danh sách cụ thể phụ thuộc phiên bản Spring Framework; khi phụ thuộc một cặp conversion cụ thể, hãy xem Javadoc/source đúng version ứng dụng đang chạy.

### 2.1. Scalar converters: chuyển đổi một giá trị

Scalar là các giá trị đơn như chuỗi, số, boolean, enum, locale, thời gian và các kiểu tương tự. Các ví dụ phổ biến:

| Nhóm | Ví dụ | Ghi chú |
| --- | --- | --- |
| String → Number | `String -> Integer`, `String -> Long`, `String -> BigDecimal` | Chuỗi sai cú pháp số sẽ lỗi |
| Number → Number | `Integer -> Long`, `Integer -> Double` | Cân nhắc overflow và mất độ chính xác |
| String → Boolean | `"true" -> Boolean` | Không thay thế validation nghiệp vụ |
| String → Character | `"A" -> Character` | Chuỗi không phù hợp có thể bị từ chối |
| String → Enum | `"ACTIVE" -> Status.ACTIVE` | Thường dùng tên enum constant |
| String → UUID | `"..." -> UUID` | Cần đúng cú pháp UUID |
| String → Locale/Currency | `"en-US" -> Locale`, `"USD" -> Currency` | Không đồng nghĩa format tiền theo locale |
| String → URI/URL/Charset/Path/Pattern | Text → kiểu Java tương ứng | Mỗi kiểu có quy tắc parse riêng |
| Date/time | Một số chuyển đổi giữa kiểu ngày giờ | Xét timezone, format và version |

Bảng là nhóm ví dụ, không phải cam kết mọi cặp đều có converter hai chiều hoặc mọi giá trị đều chuyển được. `canConvert(true)` theo kiểu không bảo đảm chuỗi cụ thể có thể parse.

Ví dụ:

~~~java
DefaultConversionService service = new DefaultConversionService();

Integer age = service.convert("21", Integer.class);
Long count = service.convert(12, Long.class);
Status status = service.convert("ACTIVE", Status.class);
UUID id = service.convert(
        "123e4567-e89b-12d3-a456-426614174000", UUID.class);
~~~

Đoạn này giả định có enum `Status` và import `java.util.UUID`. `age` nhận 21, `count` nhận 12L, `status` nhận enum constant `ACTIVE`, còn `id` nhận UUID tương ứng. Đây là snippet minh họa, không phải một file độc lập.

### 2.2. Collection và array converters

DefaultConversionService đăng ký converter để chuyển đổi container dựa trên converter của phần tử. Nếu Spring biết chuyển `String -> Integer`, cơ chế collection/array có thể tái sử dụng quy tắc ấy. Ví dụ thường gặp:

- `String[] -> List<Integer>`.
- `List<String> -> Set<Integer>`.
- `List<Integer> -> String[]` nếu có converter phần tử phù hợp.
- Chuyển giữa các dạng array/collection thông dụng.

Không phải tạo một converter riêng cho từng tổ hợp collection khi conversion phần tử đã có và cấu trúc container được hỗ trợ. Spring có các converter như `ArrayToCollectionConverter`, `CollectionToArrayConverter`, `CollectionToCollectionConverter` và `ArrayToArrayConverter`.

Java type erasure làm cho kiểu generic phần tử không luôn có sẵn từ raw class. Chỉ nhìn `List.class` sẽ không biết danh sách đích cần chứa Integer hay String. Khi cần, truyền `TypeDescriptor` để mô tả kiểu phần tử.

Ví dụ chuyển list chuỗi sang list số nguyên:

~~~java
DefaultConversionService service = new DefaultConversionService();

List<String> input = List.of("10", "20", "30");
TypeDescriptor sourceType = TypeDescriptor.forObject(input);
TypeDescriptor targetType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

@SuppressWarnings("unchecked")
List<Integer> result = (List<Integer>) service.convert(
        input, sourceType, targetType);

System.out.println(result);
~~~

Imports:

~~~java
import java.util.List;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
~~~

Stdout:

~~~text
[10, 20, 30]
~~~

Nếu chỉ gọi `service.convert(input, List.class)`, target type được mô tả quá tổng quát; không có thông tin để yêu cầu chuyển từng phần tử thành `Integer`. `TypeDescriptor.collection(...)` làm rõ kiểu phần tử đích.

### 2.3. Map và object lồng nhau

DefaultConversionService có converter cho các tình huống Map/container phổ biến, tùy cặp kiểu và version. Ví dụ chuyển map-to-map có thể sử dụng converter phần tử cho key/value khi đường chuyển đổi đó tồn tại. Nhưng chuyển một Map tùy ý thành DTO/entity với thuộc tính lồng nhau **không phải** cam kết mapping object tổng quát.

Nếu cần map key/value sang DTO hoặc biến đổi cấu trúc dữ liệu nghiệp vụ, hãy dùng data binding có schema, mapper chuyên dụng hoặc code mapping tường minh. Không xem `DefaultConversionService` là thay thế cho MapStruct, BeanUtils hay Jackson.

### 2.4. Một số converter bổ sung

Tùy version Spring, bộ mặc định còn có thể đăng ký:

- Byte buffer và byte array/kiểu buffer liên quan.
- `Date -> Instant` và `Instant -> Date`.
- `String -> TimeZone`, `ZoneId -> TimeZone`.
- `ZonedDateTime -> Calendar`.
- `ObjectToObjectConverter` cho một số kiểu đích có factory/constructor phù hợp theo quy ước của Spring.
- `Object -> Optional` và `Optional -> Object`.
- `IdToEntityConverter` trong trường hợp entity có API nhận diện ID phù hợp.
- Fallback `Object -> String` cho biểu diễn chuỗi thông dụng.

Đừng coi các class trên là API whitelist bất biến. Một số converter là implementation nội bộ, có điều kiện lựa chọn và có thể thay đổi giữa các version. Hãy xem Javadoc/source đúng version khi phụ thuộc một chuyển đổi cụ thể.

## 3. Chương trình Java 17+ chạy độc lập

Ví dụ sau dùng Spring Framework `spring-core`, không cần Spring Boot hoặc HTTP server. Nó chứng minh conversion mặc định cho số, enum và collection.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'default-conversion-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-core:6.2.0'
}

application {
    mainClass = 'example.DefaultConversionDemo'
}
~~~

Tạo `src/main/java/example/DefaultConversionDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.UUID;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public class DefaultConversionDemo {

    enum Status {
        ACTIVE, DISABLED
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        Integer age = service.convert("21", Integer.class);
        Long count = service.convert(12, Long.class);
        Status status = service.convert("ACTIVE", Status.class);
        UUID id = service.convert(
                "123e4567-e89b-12d3-a456-426614174000", UUID.class);

        List<String> source = List.of("10", "20", "30");
        TypeDescriptor sourceType = TypeDescriptor.forObject(source);
        TypeDescriptor targetType = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Integer.class));

        @SuppressWarnings("unchecked")
        List<Integer> numbers = (List<Integer>) service.convert(
                source, sourceType, targetType);

        System.out.println("age: " + age);
        System.out.println("count: " + count);
        System.out.println("status: " + status);
        System.out.println("uuid: " + id);
        System.out.println("numbers: " + numbers);
        System.out.println("string-to-integer: "
                + service.canConvert(String.class, Integer.class));
        System.out.println("string-to-status: "
                + service.canConvert(String.class, Status.class));
    }
}
~~~

Chạy từ thư mục gốc với Gradle Wrapper:

~~~bash
./gradlew run
~~~

Nếu đã cài Gradle tương thích nhưng chưa có wrapper, dùng `gradle run`. Trên Windows có thể dùng `.\gradlew.bat run`.

Stdout dự kiến:

~~~text
age: 21
count: 12
status: ACTIVE
uuid: 123e4567-e89b-12d3-a456-426614174000
numbers: [10, 20, 30]
string-to-integer: true
string-to-status: true
~~~

Ví dụ thể hiện:

1. Constructor của `DefaultConversionService` đăng ký bộ converter mặc định, không cần tự thêm converter String sang Integer.
2. Có converter `Integer -> Long` nên giá trị số được chuyển theo kiểu đích.
3. Chuỗi tên constant có thể được chuyển sang enum.
4. Collection conversion tái sử dụng converter phần tử; `TypeDescriptor` cung cấp kiểu phần tử đích.
5. `canConvert(...)` kiểm tra khả năng theo kiểu, không parse trước giá trị cụ thể.

Dependency được cố định để ví dụ có version cụ thể. Dự án thực tế nên dùng BOM/Spring Boot dependency management và version do dự án quản lý; khi đổi version, hãy chạy lại test để xác minh hành vi.

## 4. Helper đăng ký bộ converter mặc định

### 4.1. `addDefaultConverters(ConverterRegistry)`

Không cần tạo một `DefaultConversionService` mới nếu đã có registry phù hợp. Có thể thêm bộ converter chuẩn bằng:

~~~java
DefaultConversionService.addDefaultConverters(registry);
~~~

`registry` phải đáp ứng yêu cầu API: không chỉ implement `ConverterRegistry` mà còn phải dùng được như một `ConversionService` (ví dụ `ConfigurableConversionService`). Vì vậy không truyền một registry bất kỳ mà thiếu khả năng thực hiện conversion.

Đối với ví dụ thông dụng, không cần gọi helper sau khi đã tạo `new DefaultConversionService()`: constructor mặc định đã đăng ký các converter ấy. Gọi lặp lại không cần thiết và có thể làm registry khó hiểu.

### 4.2. `addCollectionConverters(ConverterRegistry)`

Có method tĩnh `addCollectionConverters(...)` để thêm nhóm converter collection/array. Thường nên khởi tạo `DefaultConversionService` hoặc gọi `addDefaultConverters(...)` để có cả scalar converters và các nhóm mặc định khác. Chỉ dùng helper chuyên collection nếu thực sự hiểu registry hiện có và phần converter phần tử đã được đăng ký ra sao.

### 4.3. `getSharedInstance()`

`DefaultConversionService.getSharedInstance()` trả về shared default instance được khởi tạo lười. API mô tả đây là fallback cho code path không thể truy cập một service sống lâu hơn. Khi ứng dụng cần tùy chỉnh, tài liệu khuyến nghị tạo instance riêng thay vì chỉnh shared instance. Điều đó giúp cấu hình của test hoặc thành phần riêng không làm thay đổi hành vi của code khác dùng chung process.

## 5. Dùng DefaultConversionService trong Spring ApplicationContext

Nếu muốn Spring container sử dụng một conversion service chung, có thể đăng ký bean tên `conversionService`:

~~~java
@Configuration
public class ConversionConfig {

    @Bean("conversionService")
    public ConversionService conversionService() {
        return new DefaultConversionService();
    }
}
~~~

Imports cần có `org.springframework.context.annotation.Configuration`, `Bean` và `org.springframework.core.convert.ConversionService`. Đây là class cấu hình trong ứng dụng Spring, không phải chương trình chạy độc lập.

Spring core container nhận diện bean tên đặc biệt `conversionService` khi cần chuyển đổi giá trị cấu hình/bean. Một số subsystem khác có registry hoặc vòng đời cấu hình riêng; không suy luận rằng một bean này tự cấu hình được mọi loại HTTP input, Jackson hoặc mọi PropertyEditor.

Ví dụ XML tương ứng:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

`ConversionServiceFactoryBean` tạo service được cấu hình với converter mặc định. Tập converter ứng dụng có thể được bổ sung qua cấu hình bean phù hợp.

### 5.1. Spring MVC

Trong Spring MVC, conversion và formatting cho các điểm binding có thể cấu hình qua `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

~~~java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToTicketCodeConverter());
    }
}
~~~

Đoạn này giả định đã có `StringToTicketCodeConverter`, cùng imports `Configuration`, `WebMvcConfigurer` và `FormatterRegistry`. MVC cũng có các converter/formatter mặc định; cấu hình ứng dụng bổ sung quy tắc riêng vào registry phù hợp.

Cần phân biệt:
- Query parameter, path variable và form data thường đi qua các argument resolver/data binder, nơi conversion service và formatter có vai trò.
- `@RequestBody` JSON thường được đọc bởi `HttpMessageConverter` và Jackson. Đăng ký converter trong MVC FormatterRegistry không tự cấu hình Jackson đọc mọi field JSON.
- `@ConfigurationProperties` trong Spring Boot có đường bind cấu hình riêng và có thể cần converter được đăng ký cho property binding.

## 6. Bổ sung converter nghiệp vụ

Giả sử ứng dụng có kiểu `TicketCode` với format `TKT-123`. Đây không phải kiểu phổ biến mà Spring tự hiểu. Ta tạo converter:

~~~java
package example;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToTicketCodeConverter
        implements Converter<String, TicketCode> {

    @Override
    public TicketCode convert(String source) {
        return new TicketCode(
                source.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

Đoạn trên là class minh họa, cần kiểu `TicketCode` có constructor kiểm tra định dạng. Dùng `Locale.ROOT` cho mã kỹ thuật để chuẩn hóa không phụ thuộc locale của máy. Cũng cần quyết định chính sách với null/chuỗi rỗng trước khi converter được gọi; validator riêng xử lý trường bắt buộc.

Đăng ký converter:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

service.addConverter(new StringToTicketCodeConverter());
~~~

Service giữ tất cả converter mặc định và thêm quy tắc domain. Nếu cần chiều ngược `TicketCode -> String`, tạo converter khác; Spring không tự sinh nghịch đảo cho converter một chiều.

### 6.1. Converter, ConverterFactory và GenericConverter

| Loại | Dùng khi | Ví dụ |
| --- | --- | --- |
| `Converter<S,T>` | Một cặp kiểu nguồn/đích rõ ràng | `String -> TicketCode` |
| `ConverterFactory<S,R>` | Nhiều kiểu đích có chung base type | Họ enum |
| `GenericConverter` | Nhiều cặp kiểu, cần metadata `TypeDescriptor` | Quy tắc phụ thuộc generic/annotation |
| `ConditionalGenericConverter` | Chỉ áp dụng khi descriptor thỏa điều kiện | Conversion có điều kiện theo field metadata |

Một converter nhỏ thường dễ đọc và test nhất. Chỉ dùng generic/conditional converter khi thật sự cần nhiều cặp kiểu hoặc metadata.

### 6.2. Đừng vô tình làm mất converter mặc định

Một lỗi phổ biến là khởi tạo `new GenericConversionService()` rồi chỉ đăng ký converter domain, nhưng ứng dụng lại kỳ vọng `String -> Integer` hoạt động. `GenericConversionService` không tự có toàn bộ bộ mặc định như `DefaultConversionService`.

Cách đơn giản:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToTicketCodeConverter());
~~~

Nếu vì lý do kiến trúc phải dùng registry khác, đăng ký default converters trước rồi thêm converter riêng. Đừng tự viết lại các converter số/collection phổ biến nếu bộ mặc định đã đáp ứng.

## 7. TypeDescriptor và kiểu generic

Java type erasure khiến runtime không thể luôn suy ra generic element type chỉ từ raw class. Ví dụ `List<String>` và `List<Integer>` cùng có raw class `List.class`. Conversion service cần metadata kiểu phần tử để chuyển đổi chính xác.

Ví dụ:

~~~java
List<String> source = List.of("1", "2");
TypeDescriptor sourceDesc = TypeDescriptor.forObject(source);
TypeDescriptor targetDesc = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object result = service.convert(source, sourceDesc, targetDesc);
~~~

Nếu converter collection và converter phần tử phù hợp được đăng ký, `result` là list integer. Khi làm việc với JavaBean property, Spring có thể đọc metadata generic từ property descriptor; `TypeDescriptor` cũng mang annotation metadata cho converter/formatter có điều kiện.

Khi viết code generic, tránh cast mù. Nên truyền target descriptor hoặc dùng helper nhận descriptor thay vì chỉ gọi `convert(value, List.class)` khi cần list có kiểu phần tử cụ thể.

## 8. Null, conversion errors và giới hạn

### 8.1. Null source

Contract của converter kiểu `Converter<S,T>` đảm bảo source truyền vào `convert(S)` không null; xử lý null thuộc cơ chế của `ConversionService`. Nhiều target reference type có thể giữ null mà không gọi converter. Vì vậy đừng dùng converter để thay thế kiểm tra trường bắt buộc.

Nếu API yêu cầu age, hãy dùng validation như `@NotNull` hoặc kiểm tra DTO. Kết quả chuyển đổi null không chứng minh request hợp lệ.

### 8.2. Khả năng chuyển đổi không đồng nghĩa giá trị hợp lệ

~~~java
service.canConvert(String.class, Integer.class); // true
service.convert("not-a-number", Integer.class);  // conversion fails
~~~

`canConvert(...)` kiểm tra cặp kiểu, không parse trước nội dung. Khi chuỗi sai định dạng, conversion thất bại và có thể được bọc trong `ConversionFailedException`. Ứng dụng cần xử lý phù hợp với điểm gọi: form binding có thể ghi lỗi vào `BindingResult`, còn gọi service trực tiếp cần xử lý exception.

### 8.3. Parse thành công không đồng nghĩa business rule đúng

Chuỗi `"0"` chuyển thành Integer 0 thành công, nhưng số lượng có thể phải lớn hơn 0. `"TKT-123"` có thể tạo được TicketCode nhưng không chứng minh ticket tồn tại hoặc caller có quyền truy cập.

Phân biệt:
- **Conversion:** input có thể chuyển sang kiểu Java đích không?
- **Validation:** dữ liệu có thỏa constraint khai báo không?
- **Domain/service:** giá trị có thỏa trạng thái và bất biến nghiệp vụ không?
- **Authorization:** chủ thể có quyền thao tác tài nguyên không?
- **Database:** transaction và constraint có giữ toàn vẹn dữ liệu khi ghi không?

### 8.4. Precision, locale và timezone

Đừng dùng scalar conversion như công cụ format tiền theo locale. `BigDecimal` phù hợp cho số thập phân nhưng input và scale vẫn cần quy tắc. Khi parse/print theo `Locale`, dùng `Formatter<T>` hoặc formatting service. Khi xử lý date/time, phải xác định timezone và format của hợp đồng; không giả định chuyển đổi giữa `LocalDate`, `Instant` và `Date` có ngữ nghĩa duy nhất trong mọi ngữ cảnh.

## 9. Thread-safety và vòng đời

Spring mô tả `ConversionService` là object stateless, thường khởi tạo lúc startup rồi chia sẻ giữa nhiều thread. Vì vậy custom converter đăng ký vào service nên stateless và thread-safe.

Converter không nên:
- Lưu request-specific data trong mutable field.
- Dùng formatter mutable thiếu bảo vệ giữa các thread.
- Gọi database/network trong lúc parse một query parameter.
- Phụ thuộc SecurityContext để quyết định có chuyển kiểu được không.
- Thay đổi hành vi theo request trước đó.

Nếu quy tắc cần locale, dùng `Formatter<T>` có tham số locale trong `parse/print`. Nếu cần database hoặc trạng thái nghiệp vụ, đưa vào service/domain. Không mutate registry liên tục sau khi ứng dụng đã phục vụ request.

## 10. Kiểm thử converter và service

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| String → Integer hợp lệ | Nhận số đúng |
| Integer → Long | Nhận kiểu đích tương ứng |
| String → enum đúng tên | Nhận enum constant |
| String → enum sai tên | Conversion fail có kiểm soát |
| List<String> → List<Integer> | Các phần tử được chuyển với TypeDescriptor |
| Kiểu nghiệp vụ có custom converter | Chỉ chuyển sau khi đăng ký |
| `canConvert` | Đúng theo cặp kiểu, không phụ thuộc giá trị cụ thể |
| Null | Tuân theo null semantics; validation bắt buộc vẫn chạy riêng |
| Locale/timezone | Kết quả đúng theo hợp đồng |
| Converter đa luồng | Không rò trạng thái giữa các lần chuyển |

Một unit test JUnit đơn giản:

~~~java
@Test
void convertsStringToInteger() {
    DefaultConversionService service = new DefaultConversionService();

    assertTrue(service.canConvert(String.class, Integer.class));
    assertEquals(Integer.valueOf(21),
            service.convert("21", Integer.class));
}
~~~

Đây là method test minh họa, cần import JUnit 5, `DefaultConversionService` và các assertion tĩnh. Với custom converter, test cả dữ liệu hợp lệ, dữ liệu sai và trường hợp converter chưa được đăng ký.

Với MVC/Boot, hãy integration test qua đúng `MockMvc`, binder hoặc configuration binding nếu service được đăng ký ở subsystem đó. Unit test tạo `new DefaultConversionService()` không chứng minh MVC hay Jackson đang sử dụng cùng instance.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ConverterNotFoundException` | Không có converter cho cặp kiểu hoặc inject nhầm service | Kiểm tra registry, bean và `canConvert` |
| `ConversionFailedException` | Có đường chuyển kiểu nhưng input không parse được | Kiểm tra format và exception gốc |
| `List.class` không thành `List<Integer>` | Target descriptor thiếu metadata phần tử | Dùng `TypeDescriptor.collection(...)` |
| Unit test chuyển được, MVC không thấy converter | Test dùng instance riêng; MVC dùng registry khác | Đăng ký vào đúng `FormatterRegistry`/MVC config |
| `@RequestBody` không dùng custom converter | Jackson là luồng deserialize khác | Cấu hình Jackson/deserializer tương ứng |
| Converter mặc định biến mất | Dùng `GenericConversionService` trống hoặc override registry | Dùng `DefaultConversionService` hoặc thêm default converters |
| `canConvert` true nhưng request vẫn lỗi | Giá trị đầu vào cụ thể không parse được | Test dữ liệu thật, không chỉ cặp kiểu |
| Kết quả phụ thuộc request trước | Converter mutable hoặc không thread-safe | Viết converter stateless |
| Ngày giờ lệch | Chưa định nghĩa timezone/locale | Dùng formatter và chính sách thời gian rõ ràng |
| Muốn tự map JSON/map sang entity | Conversion service không phải object mapper tổng quát | Dùng Jackson/DTO mapper hoặc mapping explicit |

## 12. Checklist áp dụng

1. Dùng `DefaultConversionService` khi cần chuyển đổi Java phổ biến và không muốn đăng ký thủ công từng converter.
2. Dùng `GenericConversionService` khi chủ đích quản lý registry trống; đăng ký những converter mà ứng dụng cần.
3. Dùng `ConversionService` để tiêu thụ, `ConverterRegistry`/`ConfigurableConversionService` khi cần đăng ký.
4. Dùng `TypeDescriptor` khi generic collection hoặc metadata field ảnh hưởng conversion.
5. Thêm converter nghiệp vụ cho cặp kiểu rõ ràng; định nghĩa chiều ngược riêng khi cần.
6. Đăng ký vào đúng scope: ApplicationContext, Spring MVC, configuration binding hoặc subsystem khác.
7. Giữ converter stateless, thread-safe và tránh I/O.
8. Tách conversion khỏi validation, authorization và domain rules.
9. Test cả cặp kiểu và giá trị thực, gồm invalid input, null và collection.
10. Đối chiếu Javadoc/source đúng version trước khi phụ thuộc vào converter ít phổ biến hoặc class implementation nội bộ.

**Ghi nhớ:** `DefaultConversionService` là `GenericConversionService` đã cài sẵn các converter phổ biến. Scalar converters xử lý kiểu đơn, collection/array converters tái sử dụng converter phần tử, và các converter bổ sung xử lý một số kiểu thời gian, buffer, Optional và object thông dụng. Khởi tạo service mặc định rồi bổ sung converter domain là cách đơn giản cho phần lớn ứng dụng; cần cấu hình và kiểm thử đúng subsystem sử dụng nó.

### Tài liệu tham khảo

- Spring Framework Reference — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.2 Reference — Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 Javadoc — DefaultConversionService: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.2 Source — DefaultConversionService.java: https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-core/src/main/java/org/springframework/core/convert/support/DefaultConversionService.java
- Spring Framework Reference — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — Spring MVC Conversion and Formatting: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
