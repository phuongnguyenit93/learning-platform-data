# ConversionService và API convert trong Spring Framework

## 1. ConversionService giải quyết vấn đề gì?

Ứng dụng Spring thường nhận dữ liệu ở dạng chuỗi, nhưng đối tượng Java cần các kiểu dữ liệu cụ thể. Ví dụ:

- Query parameter `?page=3` cần thành `Integer`.
- Chuỗi `"2026-12-31"` cần thành `LocalDate`.
- Mã `"PENDING"` cần thành enum `OrderStatus`.
- Một danh sách chuỗi cần thành `List<Long>`.
- Một mã khách hàng cần thành kiểu miền `CustomerCode`.

Nếu mỗi controller, service hoặc DataBinder tự viết logic parse, hệ thống sẽ có nhiều cách chuyển đổi, khó tái sử dụng và khó kiểm soát lỗi. **`org.springframework.core.convert.ConversionService`** cung cấp một API thống nhất để hỏi khả năng chuyển đổi và thực hiện chuyển đổi từ kiểu nguồn sang kiểu đích.

Các ý chính:

- `ConversionService` là **API sử dụng** converter: `canConvert(...)` và `convert(...)`.
- `Converter<S,T>`, `ConverterFactory<S,R>`, `GenericConverter` và `ConditionalGenericConverter` là các **SPI triển khai logic chuyển đổi**.
- `ConverterRegistry` là API đăng ký các converter vào một implementation có khả năng cấu hình.
- `GenericConversionService` là implementation tổng quát, cung cấp cơ chế đăng ký, tra cứu và thực thi converter.
- `DefaultConversionService` là implementation có sẵn các converter phổ biến của Spring.
- `TypeDescriptor` mang theo thông tin kiểu và metadata vị trí khai báo, bao gồm generic types và annotation.

ConversionService thường được dùng trong Spring Core, DataBinder, Spring MVC và các thành phần cần chuyển dữ liệu từ một kiểu sang kiểu khác.

## 2. Hợp đồng API của ConversionService

Các overload cốt lõi của interface có thể nhìn như sau:

```java
public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);

    <T> T convert(Object source, Class<T> targetType);

    boolean canConvert(
        TypeDescriptor sourceType, TypeDescriptor targetType
    );

    Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    );
}
```

Đây là phần API trọng tâm; tùy phiên bản Spring có thêm default method và nullable annotations.

### canConvert(sourceType, targetType)

Hỏi xem implementation có khả năng thực hiện conversion từ kiểu nguồn sang kiểu đích không:

```java
boolean supported =
    conversionService.canConvert(String.class, Integer.class);
```

Phương thức này hữu ích khi muốn kiểm tra khả năng trước khi gọi convert. Nhưng **`true` không đảm bảo mọi giá trị đầu vào đều chuyển đổi được**. Ví dụ `String → Integer` là một cặp kiểu được hỗ trợ, song `"abc"` vẫn không parse thành số nguyên. Với array, collection và map, Spring còn có thể trả `true` vì có khả năng chuyển đổi phần tử theo kiểu, dù một phần tử cụ thể gây lỗi trong lúc chạy.

Nếu `sourceType` là `null`, API cho phép kiểm tra khả năng chuyển đổi từ giá trị null tùy implementation/target. `targetType` bắt buộc phải có; truyền target type null là lỗi argument.

### convert(source, targetType)

Đây là overload phổ biến nhất khi biết kiểu đích ở compile time:

```java
Integer page = conversionService.convert("3", Integer.class);
LocalDate date =
    conversionService.convert("2026-12-31", LocalDate.class);
```

- `source` là object cần chuyển đổi.
- `targetType` là class đích cần nhận.
- Kết quả có kiểu `T` tương ứng với target class.
- Nếu một conversion exception xảy ra, method có thể ném `ConversionException`.
- Nếu cặp source/target không có converter phù hợp, có thể gặp `ConverterNotFoundException`.
- Nếu converter đã tìm thấy nhưng dữ liệu cụ thể không hợp lệ, thường gặp `ConversionFailedException` chứa nguyên nhân.

### convert(source, sourceType, targetType)

Overload sử dụng `TypeDescriptor` khi cần metadata chính xác hơn:

```java
Object converted = conversionService.convert(
    rawValue,
    sourceDescriptor,
    targetDescriptor
);
```

`TypeDescriptor` cho phép Spring biết không chỉ lớp Java mà còn **generic element type**, annotation và vị trí field/method nơi conversion xảy ra. Điều đó đặc biệt hữu ích khi chuyển `String[]` sang `List<Integer>` hoặc khi converter cần đọc annotation trên field đích để quyết định logic.

Từ Spring Framework 6.1 còn có overload `convert(Object source, TypeDescriptor targetType)` giúp chỉ cung cấp target descriptor; Spring tự suy ra descriptor nguồn từ object thực tế bằng `TypeDescriptor.forObject(source)`. Khi source là null và caller cần mô tả kiểu nguồn cụ thể, overload có đủ cả source descriptor có thể cung cấp thêm ngữ cảnh.

## 3. TypeDescriptor: nhiều hơn một Class

Nếu chỉ dùng `Class<?>`, `List.class` không nói được danh sách đó chứa `String`, `Integer` hay kiểu khác. `TypeDescriptor` giữ thêm thông tin generic và annotation của vị trí khai báo.

Ví dụ:

```java
final class SearchRequest {
    private List<Integer> pageNumbers;

    public List<Integer> getPageNumbers() {
        return pageNumbers;
    }
}
```

Với field `pageNumbers`, ta có thể lấy descriptor:

```java
Field field = SearchRequest.class.getDeclaredField("pageNumbers");
TypeDescriptor descriptor = new TypeDescriptor(
    new Property(field)
);
```

Đoạn code trên cần import `java.lang.reflect.Field` và `org.springframework.core.convert.TypeDescriptor`; có thể dùng `Property` từ `org.springframework.core.convert.Property`. Descriptor có thể giữ thông tin `List<Integer>` mà `List.class` đơn thuần không biểu đạt được.

Trong thực tế, việc chuyển đổi collection/map thường cần biết **kiểu phần tử hoặc kiểu key/value**. Ví dụ khi chuyển `String[]` sang `List<Integer>`, Spring chuyển từng phần tử sang `Integer`. TypeDescriptor của field đích cho phép tìm element type là `Integer`.

### Lấy descriptor trực tiếp

Một số cách tạo descriptor hữu ích:

```java
TypeDescriptor.valueOf(String.class);
TypeDescriptor.forObject("hello");
TypeDescriptor.collection(List.class, TypeDescriptor.valueOf(Integer.class));
TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(String.class),
    TypeDescriptor.valueOf(Long.class)
);
```

Các factory method trên tạo descriptor cho kiểu thường, kiểu lấy từ object, collection element và map key/value. Đối với object có generic phức tạp hoặc annotation cụ thể, nên lấy descriptor từ field, constructor parameter hoặc method parameter thay vì tự suy đoán metadata.

TypeDescriptor cũng có API đọc annotation và mô tả kiểu object/generic, hỗ trợ converter dựa vào metadata. Nếu hai field đều có kiểu Java `String` nhưng một field gắn annotation riêng, converter có thể phân biệt chúng khi được gọi qua overload TypeDescriptor.

## 4. Các implementation thường gặp

### GenericConversionService

`org.springframework.core.convert.support.GenericConversionService` là implementation tổng quát của ConversionService/ConverterRegistry. Nó có các khả năng:

- Đăng ký và gỡ converter.
- Lưu mapping giữa kiểu nguồn/đích và converter.
- Tra cứu converter phù hợp dựa vào `TypeDescriptor`.
- Cache kết quả tra cứu để giảm chi phí lặp lại.
- Cho phép converter cung cấp nhiều cặp source/target hoặc điều kiện matching.

Nó là nền tảng phù hợp khi bạn muốn tự cấu hình registry converter.

### DefaultConversionService

`org.springframework.core.convert.support.DefaultConversionService` mở rộng chức năng của GenericConversionService và đăng ký nhiều converter chuẩn dùng trong ứng dụng thông thường. Ví dụ có thể chuyển các chuỗi số, enum, boolean, collection/map và các kiểu phổ biến. Để sử dụng nhanh:

```java
ConversionService service = new DefaultConversionService();
```

Một instance `DefaultConversionService` được cấu hình sẵn hữu ích cho chương trình Java thuần hoặc test mà không cần tạo Spring ApplicationContext.

### DefaultFormattingConversionService

`org.springframework.format.support.DefaultFormattingConversionService` mở rộng conversion với hỗ trợ formatting/annotation formatting. Trong ứng dụng web/form, formatters giúp chuyển dữ liệu có quy tắc hiển thị như số và ngày tháng theo locale. Không nên nhầm formatter với mọi converter; formatter tập trung vào chuyển đổi giữa text và object theo ngữ cảnh hiển thị.

### Không phải mọi ConversionService đều tự có converter custom

Một interface `ConversionService` không tự động biết mọi kiểu miền do ứng dụng định nghĩa. Nếu muốn chuyển `String → CustomerId`, bạn cần đăng ký một converter thích hợp vào registry được dùng thực tế. Đăng ký converter vào một instance độc lập nhưng controller hoặc binder lại dùng instance khác sẽ khiến conversion không xuất hiện ở luồng request.

## 5. Các cách định nghĩa converter và khi nào chọn

Spring cung cấp một số SPI với độ linh hoạt tăng dần.

| SPI | Dùng khi | Ví dụ |
| --- | --- | --- |
| `Converter<S,T>` | Một cặp kiểu nguồn → đích đơn giản | `String → CurrencyCode` |
| `ConverterFactory<S,R>` | Một nguồn chuyển sang nhiều kiểu con của một target base | `String → Enum subclasses` |
| `GenericConverter` | Cần hỗ trợ nhiều cặp kiểu, generic hoặc metadata source/target | `String[] → Collection<E>` |
| `ConditionalGenericConverter` | Cần điều kiện để converter được chọn dựa trên descriptor | Chỉ chuyển khi field target có annotation cụ thể |

Ưu tiên SPI đơn giản nhất đáp ứng yêu cầu. Không nên chọn `GenericConverter` chỉ vì nó linh hoạt hơn; logic matching và descriptor phức tạp hơn, khó đọc và bảo trì hơn.

### Converter<S,T>

Ví dụ:

```java
public record CurrencyCode(String value) {}

public final class StringToCurrencyCode
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        if (source == null || !source.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain 3 uppercase letters"
            );
        }
        return new CurrencyCode(source);
    }
}
```

Đây là converter một cặp kiểu. Khi source không hợp lệ, ném `IllegalArgumentException` để báo giá trị không chuyển đổi được. Không trả `null` hoặc một giá trị mặc định để che lỗi parse.

### ConverterFactory<S,R>

Dùng khi một kiểu nguồn chuyển thành nhiều kiểu có quan hệ cùng một base type. Enum là ví dụ kinh điển:

```java
public final class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> Enum.valueOf(targetType, source.trim());
    }
}
```

Đây là snippet minh họa ý tưởng; code sản phẩm cần quyết định rõ xử lý chuỗi rỗng, chữ hoa/thường và exception cho giá trị không tồn tại. Factory trả converter cụ thể theo enum target được yêu cầu.

### GenericConverter

`GenericConverter` khai báo các cặp kiểu mà implementation hỗ trợ thông qua `getConvertibleTypes()` và phương thức chuyển đổi dùng descriptor. Nó hữu ích khi logic cần biết generic element type hoặc metadata vị trí nguồn/đích.

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    );
}
```

Đây là chữ ký rút gọn cho những phần quan trọng. Ví dụ một converter array → collection cần biết element type của collection đích rồi yêu cầu ConversionService chuyển từng phần tử. Với use case đơn giản, `Converter<S,T>` ít phức tạp và nên được ưu tiên.

### ConditionalGenericConverter

Một số converter chỉ nên được chọn khi điều kiện thỏa mãn. `ConditionalGenericConverter` kết hợp GenericConverter và ConditionalConverter, cho phép implement `matches(sourceType, targetType)`.

Ví dụ ý tưởng: chỉ convert `String → CustomerId` khi field đích gắn annotation `@ExternalId`. Điều kiện này dựa vào metadata của `TypeDescriptor`, nhờ đó cùng cặp kiểu Java có thể có hành vi khác nhau tại các vị trí khai báo khác nhau. Không dùng conditional matching nếu một converter đơn giản là đủ.

## 6. Đăng ký converter vào registry

`GenericConversionService` và các implementation có thể cấu hình cung cấp phương thức đăng ký, ví dụ `addConverter`, `addConverterFactory` và `addGenericConverter`.

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCurrencyCode());

CurrencyCode code =
    service.convert("USD", CurrencyCode.class);
```

Đây là minh họa registration và sử dụng trên cùng instance. Nếu tạo converter xong nhưng không đăng ký vào service đang được sử dụng, lời gọi convert sẽ không tìm thấy logic custom đó.

### Trong Spring ApplicationContext

Trong ứng dụng Spring, ConversionService thường được cấu hình và chia sẻ ở phạm vi container. Có thể đăng ký một bean mang tên `conversionService` hoặc cấu hình theo cơ chế của Spring MVC/WebFlux tùy loại ứng dụng.

Ví dụ cấu hình Java:

```java
@Configuration
public class ConversionConfig {

    @Bean
    public FormattingConversionService conversionService() {
        DefaultFormattingConversionService service =
            new DefaultFormattingConversionService();

        service.addConverter(new StringToCurrencyCode());
        return service;
    }
}
```

Đoạn code là ví dụ cấu hình Spring với `@Configuration` và `@Bean`; cần import các kiểu tương ứng. Trong Spring MVC, có cơ chế đăng ký formatter/converter ở cấu hình MVC như `WebMvcConfigurer#addFormatters(FormatterRegistry)`. Tùy cấu hình ApplicationContext, không nên đăng ký hai bean service cạnh tranh hoặc vô tình dùng instance khác với service framework đang chọn.

### WebMvcConfigurer

Một cách phổ biến để thêm converter cho Spring MVC:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

Đoạn minh họa trong Spring MVC application đã có Spring Web. `FormatterRegistry` cho phép thêm converter/formatter vào hệ thống format/conversion MVC. Các controller có thể dùng custom type trong `@RequestParam`, `@PathVariable` hoặc model binding nếu đường chuyển đổi tương ứng được sử dụng.

**Lưu ý:** đăng ký qua `WebMvcConfigurer` là cách cấu hình MVC; nó không mặc nhiên đăng ký converter vào một `DefaultConversionService` riêng mà bạn tạo trong code Java.

## 7. Ví dụ Java 17 hoàn chỉnh với DefaultConversionService

Ví dụ sau chạy độc lập trên Java 17, dùng Spring Framework 6.1.14. Converter parse chuỗi mã đơn hàng dạng `ORD-12345` thành record `OrderCode`; chương trình hỏi `canConvert`, chuyển dữ liệu hợp lệ, rồi minh họa lỗi khi giá trị sai.

Cấu trúc:

```text
conversion-service-demo/
├── pom.xml
└── src/main/java/demo/ConversionServiceDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-service-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ConversionServiceDemo.java`:

```java
package demo;

import org.springframework.core.convert.ConversionException;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConversionServiceDemo {

    public record OrderCode(String value) {}

    public static final class StringToOrderCode
            implements Converter<String, OrderCode> {

        @Override
        public OrderCode convert(String source) {
            if (source == null || !source.matches("ORD-\\d{5}")) {
                throw new IllegalArgumentException(
                    "Expected order code format ORD-12345"
                );
            }
            return new OrderCode(source);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(new StringToOrderCode());

        System.out.println("canConvert="
            + service.canConvert(String.class, OrderCode.class));

        OrderCode code =
            service.convert("ORD-12345", OrderCode.class);
        System.out.println("converted=" + code.value());

        try {
            service.convert("BAD", OrderCode.class);
        } catch (ConversionException ex) {
            System.out.println("failure="
                + ex.getClass().getSimpleName());
            System.out.println("cause="
                + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Từ thư mục có `pom.xml`, chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConversionServiceDemo
```

Các dòng do chương trình in ra (không tính logging của Maven nếu có):

```text
canConvert=true
converted=ORD-12345
failure=ConversionFailedException
cause=IllegalArgumentException
```

Giải thích:

1. `DefaultConversionService` đã có các converter chuẩn; ta bổ sung cặp custom `String → OrderCode` bằng `addConverter`.
2. `canConvert(String.class, OrderCode.class)` trả `true` vì registry có converter tương ứng. Đây là kiểm tra cặp kiểu, không kiểm tra trước nội dung chuỗi `"BAD"`.
3. `convert("ORD-12345", OrderCode.class)` gọi converter, chuỗi khớp biểu thức và được bọc trong `OrderCode`.
4. `convert("BAD", OrderCode.class)` vẫn tìm được converter nhưng converter ném `IllegalArgumentException`.
5. ConversionService chuyển lỗi thành `ConversionFailedException`; cause giữ nguyên `IllegalArgumentException` để caller có thể chẩn đoán.
6. Mã gọi bắt `ConversionException`, cho phép xử lý thất bại chuyển đổi theo hợp đồng của use case.

## 8. canConvert không phải bảo đảm dữ liệu luôn hợp lệ

Điểm này đặc biệt quan trọng với collection, array và map.

Ví dụ một service có khả năng chuyển `String[] → List<Integer>`. Kiểu nguồn và đích là cặp có thể hỗ trợ; tuy nhiên input:

```text
["10", "20", "not-a-number"]
```

không thể hoàn tất vì phần tử thứ ba không chuyển được sang `Integer`. Do đó `canConvert(...)` có thể trả `true` nhưng `convert(...)` vẫn ném `ConversionException`.

Cách tư duy đúng:

- `canConvert` trả lời câu hỏi **có đường conversion cho cặp descriptor này không?**
- `convert` thực hiện conversion trên **giá trị cụ thể**, nên vẫn có thể thất bại do nội dung.
- Với generic/container types, việc convert có thể thực hiện từng phần tử, và exception có thể bắt nguồn từ một converter con.
- Không dùng `canConvert` thay cho validation input; cũng không gọi `convert` chỉ để “thử” rồi bỏ qua exception mà không xử lý.

Nếu kết quả `canConvert` là false, có thể thiếu converter phù hợp. Nếu true nhưng convert thất bại, cần xem giá trị cụ thể, converter implementation và nested element conversion.

## 9. Null, primitive và kiểu đích

`ConversionService` cho phép source nullable; xử lý null phụ thuộc vào API overload và implementation. Một số nguyên tắc:

- Target type phải được cung cấp; không thể gọi convert với target class null.
- `TypeDescriptor` nguồn có thể null khi source object null; nếu source không null nhưng descriptor nguồn null trong overload đầy đủ, đó là trường hợp không hợp lệ.
- Đừng giả định `null` luôn tương đương chuỗi rỗng `""`. Hai giá trị có ngữ nghĩa khác nhau và converter có thể xử lý chúng khác nhau.
- Với kiểu primitive như `int.class`, target thực tế không thể chứa null theo ngữ nghĩa Java; khi làm việc với dữ liệu tùy chọn, wrapper `Integer` hoặc kiểu dữ liệu có thể nullable thường phù hợp hơn.
- `DefaultConversionService` có quy tắc chuyển đổi null cụ thể, nhưng logic nghiệp vụ về field bắt buộc nên được xử lý ở validation layer.

Khi dùng `convert(source, targetType)` và source là null, descriptor nguồn được suy ra theo quy tắc API; khi target descriptor được lấy từ field generic/annotation, có thể dùng overload TypeDescriptor để giữ ngữ cảnh cần thiết. Nếu có yêu cầu nullable đặc biệt, hãy kiểm tra Javadoc của implementation đang chạy và viết test rõ ràng.

## 10. Exception trong conversion

Spring dùng hệ exception thuộc `org.springframework.core.convert`:

| Exception | Ý nghĩa |
| --- | --- |
| `ConversionException` | Lớp exception nền cho lỗi chuyển đổi |
| `ConversionFailedException` | Converter tìm được nhưng conversion cụ thể thất bại |
| `ConverterNotFoundException` | Không tìm được converter cho cặp kiểu yêu cầu |
| `ConversionService` exception contract | Các method convert có thể ném `ConversionException`; target type null là `IllegalArgumentException` |

Khi tự viết `Converter<S,T>`, quy tắc phù hợp cho dữ liệu nguồn không thể chuyển đổi là ném `IllegalArgumentException`. ConversionService thường bọc nó thành `ConversionFailedException` với source/target type và value metadata.

Không nên:
- Trả `null` để che lỗi dữ liệu sai.
- Trả một object mặc định khi parse thất bại mà không có chính sách explicit.
- Ném exception HTTP trong converter của Spring Core.
- Bắt mọi `RuntimeException` rồi báo "input invalid", vì lỗi có thể là bug hoặc cấu hình sai.
- Nhầm conversion error với constraint violation: số `0` convert thành `Integer` thành công nhưng có thể vi phạm `@Min(1)`.

Ở tầng web, MVC có thể biến lỗi thành `MethodArgumentTypeMismatchException`, binding errors hoặc exception đọc request body tùy điểm nhận dữ liệu. Converter không cần phụ thuộc HTTP; controller advice hoặc boundary của API quyết định status và response body.

## 11. Performance, vòng đời và thread safety

Tài liệu Spring mô tả ConversionService là object **stateless** theo thiết kế, thường được khởi tạo khi ứng dụng khởi động và dùng chung giữa nhiều thread. Điều này giúp tránh tạo registry mới cho mỗi request và giữ nhất quán cách chuyển đổi trong application.

Một số nguyên tắc:

- Đăng ký converter trong cấu hình khởi động, trước khi có nhiều luồng sử dụng.
- Sau khi đăng ký xong, chia sẻ service đã cấu hình; đừng thay đổi registry tùy tiện trong từng request.
- Converter nên giữ trạng thái bất biến hoặc thread-safe; tránh lưu request-specific data vào field của converter singleton.
- Logic chuyển đổi nên deterministic: cùng source và descriptor phải có kết quả giống nhau, trừ khi chính sách được thiết kế rõ có phụ thuộc locale/time zone.
- Không đưa database lookup hoặc remote network call vào converter một cách tùy tiện. Converter thường là bước chuyển kiểu nhẹ; lookup entity có thể cần repository/service và cơ chế lỗi khác.
- GenericConversionService có cache tra cứu converter; điều này giúp tái sử dụng kết quả matching nhưng không làm cho dữ liệu đầu vào luôn hợp lệ.

Nếu cần thay đổi converter theo user/session, không nhồi state vào shared ConversionService. Tạo abstraction theo use case hoặc cấu hình rõ service scope; đừng làm conversion phụ thuộc thread-local không được kiểm soát.

## 12. Khi nào dùng ConversionService, khi nào dùng Formatter?

**ConversionService** tập trung vào chuyển đổi kiểu tổng quát, ví dụ `String → LocalDate` hoặc `String → CustomerId`.

**Formatter<T>** có hai hướng:
- `parse(String text, Locale locale)`: text thành object.
- `print(T object, Locale locale)`: object thành text.

Formatter phù hợp với dữ liệu trình bày theo locale như ngày, số thập phân hoặc tiền tệ. Spring formatting infrastructure có thể đăng ký formatter với `FormattingConversionService` và tích hợp với MVC. Nếu bạn chỉ cần chuyển kiểu miền một chiều, Converter thường đơn giản hơn.

Một converter không có thông tin Locale trong chữ ký `convert(S source)`. Khi logic phụ thuộc locale, formatter là lựa chọn tự nhiên hơn. Cần tránh parse ngày tháng bằng format cứng trong converter nếu người dùng nhập theo nhiều locale.

## 13. Các lỗi phổ biến và cách gỡ lỗi

| Triệu chứng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| `ConverterNotFoundException` | Chưa đăng ký converter hoặc đăng ký sai instance | Kiểm tra registry thực tế mà framework sử dụng |
| `canConvert` trả true nhưng convert thất bại | Giá trị cụ thể sai định dạng hoặc element collection lỗi | Đọc `ConversionFailedException` và `getCause()` |
| Custom converter không chạy trong MVC | Converter đăng ký vào một service khác với service MVC | Dùng `WebMvcConfigurer.addFormatters` hoặc cấu hình MVC chính thức |
| `List<Integer>` nhận phần tử không đúng | Generic target descriptor không được cung cấp/không suy ra được | Kiểm tra `TypeDescriptor` và nested conversion |
| Enum parse thất bại do chữ hoa/thường | Quy tắc enum conversion không khớp dữ liệu | Chuẩn hóa ở converter và xác định rõ case policy |
| `null` gây kết quả bất ngờ | Nhầm null với chuỗi rỗng hoặc primitive target | Kiểm tra nullable semantics và test riêng |
| Converter dùng dữ liệu người dùng hiện tại bị sai giữa request | Converter singleton lưu mutable state | Giữ converter stateless/thread-safe |
| Hai converter cùng cặp kiểu cạnh tranh | Registry có nhiều ứng viên hoặc điều kiện matching chồng lấn | Thu hẹp source/target pair hoặc điều kiện |
| Thông báo lỗi trả raw input | Exception handler để lộ dữ liệu | Trả message ổn định, lọc rejected value và log nội bộ an toàn |
| Dùng ConversionService để kiểm tra nghiệp vụ | Trộn type conversion với validation | Chuyển rule nghiệp vụ sang Spring Validator/Bean Validation |

Khi debug một lỗi conversion, đi theo trình tự:

1. Ghi lại **source type** và **target type** dự kiến.
2. Xác nhận converter tương ứng đã đăng ký đúng registry.
3. Gọi `canConvert` để xem cặp kiểu có được hỗ trợ hay không.
4. Gọi `convert` với một giá trị mẫu hợp lệ và không hợp lệ.
5. Nếu lỗi, kiểm tra loại `ConversionException` và `getCause()`.
6. Nếu là collection/map, kiểm tra descriptor element/key/value và từng phần tử.
7. Nếu chỉ xảy ra ở MVC, xác minh service được sử dụng bởi MVC và đường đi binding/argument conversion thực tế.

## 14. Câu hỏi tự kiểm tra

1. `ConversionService` là API sử dụng hay SPI triển khai converter? `Converter<S,T>` đóng vai trò nào?
2. `canConvert(String.class, Integer.class)` trả true có bảo đảm chuỗi `"abc"` chuyển được không?
3. Khi nào dùng overload `convert(Object, Class<T>)`, khi nào cần overload có `TypeDescriptor`?
4. Vì sao `TypeDescriptor` hữu ích khi chuyển `String[]` sang `List<Integer>`?
5. `DefaultConversionService` khác `GenericConversionService` ở mục đích cấu hình sẵn như thế nào?
6. Khi nào nên dùng `ConverterFactory` thay vì một `Converter`?
7. Sự khác nhau giữa `GenericConverter` và `ConditionalGenericConverter` là gì?
8. Vì sao converter custom đăng ký ở một service độc lập có thể không chạy trong Spring MVC?
9. `ConversionFailedException` khác `ConverterNotFoundException` ra sao?
10. Vì sao ConversionService nên được cấu hình khi startup và dùng như một service stateless?
11. Một giá trị đã parse thành kiểu Java nhưng vi phạm `@Min` thuộc conversion error hay validation error?
12. Vì sao không nên giữ mutable request-specific state trong converter singleton?

**Ghi nhớ:** `ConversionService` là facade dùng để hỏi khả năng và thực hiện chuyển đổi. `convert` điều phối đến converter đã đăng ký; `TypeDescriptor` mang thêm metadata generic/annotation. `canConvert` chỉ cho biết cặp kiểu có đường chuyển đổi, không bảo đảm mọi giá trị cụ thể hợp lệ. Chọn đúng SPI, đăng ký đúng service mà framework dùng, và để conversion errors tách biệt với validation errors.

## Tài liệu tham khảo

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1.14 — ConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.1.14 — GenericConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
- Spring Framework 6.1.14 — DefaultConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework — Formatting Conversion Service: https://docs.spring.io/spring-framework/reference/core/validation/format.html
