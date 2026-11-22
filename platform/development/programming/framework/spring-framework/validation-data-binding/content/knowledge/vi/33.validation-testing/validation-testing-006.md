# Kiểm thử Converter, ConverterFactory và converter có điều kiện trong Spring Framework

## 1. Mục tiêu và bài toán

Spring Framework có hệ thống **type conversion** trong package `org.springframework.core.convert`. Một request gửi giá trị ở dạng chuỗi, nhưng controller và domain model thường dùng kiểu mạnh: mã đơn hàng, trạng thái enum, định danh được gắn annotation hoặc cấu trúc tập hợp.

Ví dụ:

```http
GET /api/orders?id=ord-0042
GET /api/levels?state=shipped&level=high
GET /api/code?value=VIP-A7
```

Ta muốn:
- `ord-0042` → `OrderNumber("ORD-0042")`; chuỗi thiếu prefix, sai độ dài hay ký tự không phải số phải bị từ chối.
- `shipped` → `OrderState.SHIPPED`, `high` → `ReviewLevel.HIGH` bằng **một ConverterFactory** dùng chung cho nhiều enum.
- `VIP-A7` → `PrefixedCode` **chỉ** khi nơi nhận giá trị có `@RequiredPrefix("VIP")`; nếu không có annotation, converter có điều kiện không nên match.
- Khi converter được đăng ký với Spring MVC, valid query/form parameters được bind đúng và invalid parameters trả lỗi 400 ở đường MVC thích hợp.

Điều này đòi hỏi ba cấp độ test khác nhau:

1. **Unit test cho từng converter**: kiểm tra thuật toán, boundary và exception khi gọi trực tiếp.
2. **Integration test nhẹ với `ConversionService`**: kiểm tra đăng ký, source/target pair, `TypeDescriptor`, `matches` và wrapping exception. Converter đúng nhưng **không được chọn** vẫn là bug.
3. **Web-layer test với `MockMvc`**: kiểm tra conversion có thật sự được Spring MVC áp dụng cho `@RequestParam` và `@ModelAttribute` hay không.

**Bài này thuộc nhóm “Kiểm thử”** của module **Spring Framework - validation-data-binding**. Trọng tâm là chiến lược kiểm thử tin cậy cho `Converter<S,T>`, `ConverterFactory<S,R>` và `ConditionalGenericConverter`, không phải chỉ hướng dẫn tạo converter.

Phạm vi ví dụ hoàn chỉnh: **Java 17+**, **Spring Boot 3.5.6**, **Spring Framework 6.2.x**, JUnit Jupiter và MockMvc. Các ví dụ nhỏ không đủ imports được ghi rõ là minh họa; toàn bộ project ở phần 10 được trình bày theo từng tệp để học viên có thể tạo và chạy.

## 2. Ba SPI conversion khác nhau như thế nào?

| SPI | Phương thức chính | Đủ thông tin nào? | Nên kiểm thử gì? |
| --- | --- | --- | --- |
| `Converter<S,T>` | `T convert(S source)` | Chỉ biết kiểu S và T khai báo, giá trị source | Normalization, dữ liệu tốt/xấu, domain invariant, exception |
| `ConverterFactory<S,R>` | `<T extends R> Converter<S,T> getConverter(Class<T>)` | Nhiều target type trong một họ R | Tạo converter đúng cho từng subclass/enum, không nhầm target class |
| `GenericConverter` | `getConvertibleTypes()` và `convert(Object, TypeDescriptor, TypeDescriptor)` | Source/target descriptors, annotations, generics | ConvertiblePair và ngữ cảnh field/method |
| `ConditionalGenericConverter` | GenericConverter + `matches(TypeDescriptor,TypeDescriptor)` | Ngữ cảnh đủ để quyết định **có được chọn không** | `matches=true/false`, context-aware selection, conversion khi selected |

### 2.1. `Converter<S,T>`

Hợp đồng cơ bản:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

Spring reference nêu rằng khi `ConversionService` gọi converter, tham số `source` được bảo đảm **không null**; converter được thiết kế thread-safe và có thể ném `IllegalArgumentException` cho input sai.

**Hai kiểu test khác nhau:**

```java
// Unit test trực tiếp: thấy exception do converter ném.
assertThrows(IllegalArgumentException.class,
        () -> converter.convert("BAD"));

// Integration với ConversionService: wrapper có thể là
// ConversionFailedException với IllegalArgumentException ở cause.
assertThrows(ConversionFailedException.class,
        () -> conversionService.convert("BAD", OrderNumber.class));
```

Đây là đoạn **minh họa**, giả định `converter` và `conversionService` đã được khởi tạo. Hai assertion cùng đúng mà không mâu thuẫn: tầng service bổ sung thông tin source/target và chuyển thất bại thành một exception có ngữ cảnh.

### 2.2. `ConverterFactory<S,R>`

Hợp đồng:

```java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
```

Một factory `ConverterFactory<String, Enum>` có thể phục vụ nhiều enum class. Không chỉ test một enum vì lỗi generic/target type có thể bị giấu nếu factory hard-code một target.

### 2.3. `ConditionalGenericConverter`

Spring định nghĩa:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}

public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

Bản thân `ConditionalGenericConverter` không bắt buộc thêm method `convert` mới: nó kế thừa `getConvertibleTypes`/`convert` từ `GenericConverter` và `matches` từ `ConditionalConverter`.

Tham số `TypeDescriptor` mang **ngữ cảnh**: field, method parameter, annotations hoặc generic element type. Khi `matches` trả false, converter không phải ứng viên cho vị trí đó; điều này **không đồng nghĩa** rằng mọi conversion giữa hai Java classes đều phải thất bại nếu service có converter khác đủ điều kiện.

## 3. Vì sao phải test cả trực tiếp lẫn đăng ký?

Một unit test:

```java
assertEquals(new OrderNumber("ORD-0042"),
        new StringToOrderNumberConverter().convert("ord-0042"));
```

chỉ chứng minh thuật toán đúng khi bạn **tự gọi** converter. Nó **không** chứng minh:
- Converter đã được đăng ký trong Spring `ConversionService`.
- Source/target types đúng với MVC binder.
- Có converter mặc định khác được chọn trước.
- `ConditionalGenericConverter.matches` được gọi với annotation của target thật.
- Query/form binding qua Spring MVC dùng conversion service đó.
- Khi input lỗi, MVC trả 400 hay controller tự xử lý theo cách nào.

Ngược lại, chỉ có một MockMvc test HTTP 200 cũng không bao phủ đầy đủ edge cases của converter. Chiến lược tốt là **kim tự tháp test**:

```text
             MockMvc
       MVC request binding
       -------------------
       ConversionService
     registration + selection
     -----------------------
         Unit tests
    algorithm + bad inputs
```

**Không cần khởi động toàn bộ ApplicationContext** cho mỗi case boundary nhỏ. Mỗi tầng kiểm tra một trách nhiệm, tránh duplicate vô ích.

## 4. Một ma trận test trước khi viết code

| Loại | Positive | Negative | Integration |
| --- | --- | --- | --- |
| `Converter<String,OrderNumber>` | Trim, uppercase, chuỗi 4 chữ số | Thiếu prefix, sai chữ số, quá dài, blank | `canConvert`, `convert`, cause/error class |
| `ConverterFactory<String,Enum>` | Ít nhất 2 enum types, case-insensitive, trim | Unknown constant, empty | Factory được registry chọn thay vì converter mặc định |
| `ConditionalGenericConverter` | Target field/parameter có annotation phù hợp | Không annotation, prefix khác, input rỗng | `TypeDescriptor` chính xác, `matches`, `canConvert` và MVC annotated parameter |
| Spring MVC | Query/form hợp lệ | Invalid query, invalid form, missing required argument | HTTP status và response field value |
| Cross-cutting | Nhiều lần gọi cùng input cho cùng output | Không lưu request state, không phụ thuộc locale ngầm | Test không bị ảnh hưởng global ConversionService |

Mỗi test nên **đặt tên theo hành vi**, ví dụ `missingAnnotationIsNotMatched` tốt hơn `testConverter1`.

## 5. Kiểm thử `Converter`: không chỉ input hợp lệ

Giả sử giá trị công khai mã đơn hàng phải là `ORD-0000` đến `ORD-9999`, đúng 4 chữ số ASCII. Converter cần chuẩn hóa input bằng trim và uppercase cố định:

```java
String normalized = source.trim().toUpperCase(Locale.ROOT);
if (!normalized.matches("ORD-[0-9]{4}")) {
    throw new IllegalArgumentException("Expected ORD-0000");
}
return new OrderNumber(normalized);
```

Đây là fragment từ tệp hoàn chỉnh sau.

### 5.1. Test cần thiết

1. `ord-0042` thành `ORD-0042`.
2. `  ORD-0001  ` thành `ORD-0001`.
3. `ORD-1234` được giữ nguyên.
4. `REF-0042` sai prefix.
5. `ORD-42` không đủ bốn số.
6. `ORD-12345` dư một số.
7. `"   "` không hợp lệ.
8. `ORD-１２３４` chứa chữ số full-width Unicode, không thỏa `[0-9]`.

Nếu nghiệp vụ muốn Unicode digits, chính regex và yêu cầu phải đổi, không chỉ sửa test. Trong demo, ASCII-only là hợp đồng rõ ràng.

### 5.2. Có nên test null trực tiếp?

Spring `Converter` contract nói `ConversionService` không truyền null vào `convert(S)`. Khi gọi `conversionService.convert(null, SomeType.class)`, framework có thể xử lý null ở tầng service mà không gọi converter.

Vì vậy:
- Test null qua **ConversionService** nếu hợp đồng ứng dụng quan tâm.
- Không mặc định ép mọi `Converter` hỗ trợ null trực tiếp; test trực tiếp nên bám hợp đồng do converter tự công bố.
- Nếu converter là API public dùng ở nơi khác ngoài Spring, bạn có thể chủ động đặt `Objects.requireNonNull(source)` hoặc policy null rõ ràng.

### 5.3. Chú ý locale và thread safety

`toUpperCase()` không chỉ định locale có thể cho hành vi khác theo JVM locale. Dùng `toUpperCase(Locale.ROOT)` khi chuẩn hóa identifier. Converter không nên giữ bộ đếm hoặc mutable request state không đồng bộ.

Test một lần với locale mặc định khác nhau có thể phát hiện bug khó thấy; song không nên thay `Locale.setDefault(...)` tùy tiện trong test chạy song song vì đó là global process state.

## 6. Kiểm thử `ConverterFactory`: nhắm đúng target type

Factory mẫu sẽ tạo converter cho nhiều enum:

```java
public enum OrderState { NEW, SHIPPED }
public enum ReviewLevel { LOW, HIGH }
```

Một implementation dễ test duyệt `targetType.getEnumConstants()`:

```java
for (T constant : targetType.getEnumConstants()) {
    if (constant.name().equalsIgnoreCase(source.trim())) {
        return constant;
    }
}
throw new IllegalArgumentException("Unknown enum value");
```

Điểm mạnh là không cần cast raw `Class` hoặc phụ thuộc một enum được hard-code. Với một `ConverterFactory<String, Enum>`, hãy test:
- `getConverter(OrderState.class)` nhận `"shipped"` → `SHIPPED`.
- `getConverter(ReviewLevel.class)` nhận `"high"` → `HIGH`.
- Whitespace được loại bỏ.
- Unknown value bị từ chối bằng exception rõ ràng.
- Converter cho enum này không tạo giá trị enum kia.

### 6.1. Cạm bẫy converter mặc định

`DefaultConversionService` đã có converter từ String sang Enum. Converter mặc định thường yêu cầu tên enum đúng chính tả/case theo cách riêng của Spring. Vì muốn custom **case-insensitive**, bài test chỉ gọi trực tiếp `factory.getConverter(...)` chưa đủ.

Cần thêm một test:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverterFactory(new CaseInsensitiveEnumFactory());

assertEquals(OrderState.SHIPPED,
        service.convert("shipped", OrderState.class));
```

Test này chứng minh **registry thực sự chọn factory tùy chỉnh** cho String→Enum. Khi đăng ký converter/factory trên service đã có defaults, thứ tự/override registration có ảnh hưởng; đừng chỉ nhìn `canConvert(String.class, OrderState.class)` vì default cũng có thể trả true.

### 6.2. Không giả định factory xử lý null hoặc mọi Enum subtype

`ConverterFactory<String, Enum>` khai báo range type `Enum`. Tham số `getConverter(Class<T>)` có bound `T extends Enum`. Test phải truyền **enum class hợp lệ**. Nếu một ứng dụng chuyển String thành một interface không phải enum, đây không phải factory phù hợp; có thể dùng ConverterFactory khác, Converter đơn hoặc GenericConverter.

## 7. Kiểm thử converter có điều kiện: đặc biệt chú ý `TypeDescriptor`

Một converter có điều kiện không chỉ hỏi `source.getClass()` và `targetClass`. Nó có thể hỏi **target field/parameter có annotation cụ thể hay không**.

Ta thiết kế một custom annotation:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiredPrefix {
    String value();
}
```

Và một value object:

```java
public record PrefixedCode(String value, boolean verified) {}
```

Converter chỉ hỗ trợ `String→PrefixedCode` khi `targetType` có `@RequiredPrefix`. Trong `convert`, annotation quy định prefix phải là `VIP-`, `STAFF-`… Đây là ví dụ **có thể test chính xác context**, không dựa vào bên ngoài như database.

### 7.1. `getConvertibleTypes()`: điều kiện cần, chưa đủ

```java
@Override
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(new ConvertiblePair(
            String.class, PrefixedCode.class));
}
```

Pair tuyên bố converter **có khả năng** xử lý String→PrefixedCode. Nhưng `matches` mới quyết định việc nó có phù hợp **với một vị trí cụ thể** hay không.

### 7.2. `matches` kiểm tra metadata

```java
@Override
public boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType) {

    return sourceType.getType() == String.class
            && targetType.hasAnnotation(RequiredPrefix.class);
}
```

Điều kiện này dựa trên **annotation target**. Với target field không có `@RequiredPrefix`, converter phải không match ngay cả khi Java class đích vẫn là `PrefixedCode`.

### 7.3. Tạo `TypeDescriptor` từ field thật trong test

Thay vì:

```java
TypeDescriptor target = TypeDescriptor.valueOf(PrefixedCode.class);
```

(bị mất thông tin field annotation), tạo descriptor từ reflection field đã được annotate:

```java
TypeDescriptor target = new TypeDescriptor(
        ExampleFields.class.getDeclaredField("vipCode"));
```

Đây là fragment giả định `ExampleFields` có trường `@RequiredPrefix("VIP") PrefixedCode vipCode;`. `TypeDescriptor` giữ annotation gắn với field, nên `matches` có đủ ngữ cảnh. Trong bài thực tế, field/parameter annotations chính là lý do dùng ConditionalGenericConverter.

### 7.4. Tại sao test `canConvert(Class,Class)` chưa đủ?

`service.canConvert(String.class, PrefixedCode.class)` chỉ sử dụng **class descriptors**, không có annotation của field cụ thể. Nó có thể trả false trong khi:

```java
service.canConvert(
    TypeDescriptor.valueOf(String.class),
    new TypeDescriptor(
        ExampleFields.class.getDeclaredField("vipCode")));
```

trả true. Đây là hành vi **đúng** cho converter có điều kiện dựa trên metadata.

Mặt khác, một service còn đăng ký converter khác String→PrefixedCode có thể trả true ngay cả khi conditional converter không match; do đó test unit của `matches` vẫn cần thiết.

### 7.5. Condition không đồng nghĩa validate từng giá trị

`matches` nên được dùng để xét điều kiện trên **types/metadata**; nó không nhận giá trị String cụ thể. Rule như “prefix phải bằng VIP-” có thể cần lấy annotation ở `convert` rồi so với **giá trị input**.

Tách hai trách nhiệm:
- `matches`: field/parameter có yêu cầu đặc biệt này không?
- `convert`: dữ liệu runtime có đáp ứng prefix, cấu trúc, miền giá trị không?

Nếu một vị trí không match, conversion service có thể tìm converter khác; nếu không có, nó báo `ConverterNotFoundException`. Nếu match nhưng text không hợp lệ, `convert` ném exception như `IllegalArgumentException` và service có thể bọc bằng `ConversionFailedException`.

## 8. Chọn `GenericConversionService` hay `DefaultConversionService` khi test?

| Lớp | Đặc tính | Mục tiêu |
| --- | --- | --- |
| `GenericConversionService` | Registry/conversion engine cơ bản, không có bộ mặc định phong phú | Test độc lập: chỉ converter bạn tự add |
| `DefaultConversionService` | Đăng ký sẵn converters cho số, enum, collections, v.v. | Test hành vi thực tế có defaults và precedence |
| `DefaultFormattingConversionService` | Conversion + formatter hạ tầng phổ biến của Spring MVC | Test formatter/annotation-driven formatting |
| MVC-configured conversion service | Hệ thống web với `WebMvcConfigurer#addFormatters` | Kiểm tra end-to-end request binding |
| Unit call `new MyConverter().convert(...)` | Không có registry | Test đúng logic converter và lỗi trực tiếp |

Không tự đồng nhất kết quả của một `GenericConversionService` rỗng với hạ tầng Spring Boot MVC. Ví dụ một class có constructor nhận String hoặc static factory phù hợp có thể được một default converter chọn, dù conditional converter không match. Trong unit test, dùng service rỗng để chứng minh selection của riêng converter, không suy luận toàn hệ thống không còn phương án khác.

### 8.1. `canConvert` không có nghĩa mọi giá trị đều hợp lệ

`canConvert(String.class, OrderNumber.class)` chỉ nói conversion có đường thực hiện về **kiểu**. Nó không kiểm tra nội dung `"WRONG"` có hợp lệ hay không.

Ví dụ:

```java
assertTrue(service.canConvert(String.class, OrderNumber.class));

assertThrows(ConversionFailedException.class,
        () -> service.convert("WRONG", OrderNumber.class));
```

Đây không phải lỗi bất nhất của Spring: lookup converter và kiểm tra runtime value là hai pha khác nhau.

Đối với List/Map, tài liệu `ConversionService` còn lưu ý `canConvert` có thể true dù conversion phần tử sau đó thất bại. Test phải đưa vào dữ liệu thật, không chỉ kiểm tra metadata.

### 8.2. Tránh coupling với global state

Không viết test unit dùng thẳng ApplicationContext toàn bộ chỉ để chuyển một String. Thay vào đó:

```java
GenericConversionService service = new GenericConversionService();
service.addConverter(new StringToOrderNumberConverter());
```

Không gọi `removeConvertible(...)` trên một ConversionService singleton dùng chung giữa các tests, vì có thể khiến case khác fail tùy thứ tự chạy. Mỗi test dùng instance riêng hoặc dùng @BeforeEach để cấu hình độc lập.

## 9. Cách tổ chức code/test theo đường đi thật

Dự án sẽ gồm:
- `StringToOrderNumberConverter` — `Converter<String,OrderNumber>`.
- `CaseInsensitiveEnumFactory` — `ConverterFactory<String,Enum>` cho 2 enum classes.
- `PrefixedCodeConverter` — `ConditionalGenericConverter` dựa trên `@RequiredPrefix` của field/parameter.
- `WebConversionConfig` — đăng ký cả 3 với `WebMvcConfigurer#addFormatters(FormatterRegistry)`.
- `ConversionController` — endpoint query và form để chứng minh Spring MVC binding.
- Nhiều lớp JUnit test: unit từng converter, ConversionService selection và MockMvc.

**Về code Java 17:** dùng `record` cho immutable value types; exception policy dùng `IllegalArgumentException` khi input không hợp lệ; không dùng database hoặc network trong converter. MVC tests dùng `@WebMvcTest` và `@Import` thay vì khởi động mọi service.

### 9.1. Project tree

```text
conversion-tests-demo/
├── pom.xml
├── src/main/java/demo/converters/
│   ├── ConversionDemoApplication.java
│   ├── OrderNumber.java
│   ├── StringToOrderNumberConverter.java
│   ├── OrderState.java
│   ├── ReviewLevel.java
│   ├── CaseInsensitiveEnumFactory.java
│   ├── RequiredPrefix.java
│   ├── PrefixedCode.java
│   ├── PrefixedCodeConverter.java
│   ├── WebConversionConfig.java
│   └── ConversionController.java
└── src/test/java/demo/converters/
    ├── StringToOrderNumberConverterTest.java
    ├── CaseInsensitiveEnumFactoryTest.java
    ├── PrefixedCodeConverterTest.java
    ├── ConversionServiceTest.java
    └── ConversionControllerTest.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>conversion-tests-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Với mục tiêu kiểm thử **type conversion**, project không cần `spring-boot-starter-validation`; việc Spring bind một parameter có thể lỗi vì conversion, không cần có Bean Validation provider. Nếu thêm `@Valid`/`@Min` để kiểm thử constraint, đó là **lớp test khác** và cần cấu hình Jakarta Validation đúng.

### 9.3. `ConversionDemoApplication.java`

```java
package demo.converters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
```

### 9.4. `OrderNumber.java`

```java
package demo.converters;

public record OrderNumber(String value) {
}
```

`OrderNumber` lưu canonical identifier. Nó là value object đơn giản cho bài conversion, chưa đại diện cho toàn bộ aggregate ID của một hệ thống có database.

### 9.5. `StringToOrderNumberConverter.java`

```java
package demo.converters;

import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public final class StringToOrderNumberConverter
        implements Converter<String, OrderNumber> {

    @Override
    public OrderNumber convert(String source) {
        String text = source.trim().toUpperCase(Locale.ROOT);

        if (!text.matches("ORD-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Expected an order number like ORD-0001");
        }

        return new OrderNumber(text);
    }
}
```

Nó là một converter **stateless**. Spring ConversionService bảo đảm khi gọi method `convert`, `source` không null; unit tests của class này tập trung vào giá trị hợp lệ/sai định dạng. Nếu class được gọi ngoài framework và cần một null policy riêng, có thể bổ sung `Objects.requireNonNull` theo hợp đồng ứng dụng.

### 9.6. `OrderState.java`

```java
package demo.converters;

public enum OrderState {
    NEW, SHIPPED
}
```

### 9.7. `ReviewLevel.java`

```java
package demo.converters;

public enum ReviewLevel {
    LOW, HIGH
}
```

### 9.8. `CaseInsensitiveEnumFactory.java`

```java
package demo.converters;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.ConverterFactory;

public final class CaseInsensitiveEnumFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> {
            String requested = source.trim();

            for (T constant : targetType.getEnumConstants()) {
                if (constant.name().equalsIgnoreCase(requested)) {
                    return constant;
                }
            }

            throw new IllegalArgumentException(
                    "Unknown " + targetType.getSimpleName()
                            + " constant");
        };
    }
}
```

**Vì sao không cast raw Enum?** Duyệt các constants của `targetType` cho phép trả đúng `T` mà không cần ép từ `Class` raw. Đây là ví dụ cố tình đơn giản, có thể yêu cầu policy nghiêm ngặt hơn với alias hoặc khoảng trắng Unicode trong sản phẩm thật.

Factory này không nên dùng cho một enum có phân biệt tên key được locale hóa phức tạp; khi cần localization, dùng explicit mapping, formatter hoặc dictionary phù hợp.

### 9.9. `RequiredPrefix.java`

```java
package demo.converters;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface RequiredPrefix {
    String value();
}
```

Target bao gồm `FIELD` và `PARAMETER` để unit test có thể lấy descriptor từ field, còn Spring MVC có thể xem annotation trên một `@RequestParam` handler method parameter.

### 9.10. `PrefixedCode.java`

```java
package demo.converters;

public record PrefixedCode(String value, boolean verified) {
}
```

Record này cố ý **không** có constructor một tham số `String` hay static `valueOf(String)` để không đưa ra một tuyến conversion đơn giản khác trong các tests chọn converter. `verified` chỉ biểu thị converter đã xác nhận prefix ở ví dụ, **không phải** bằng chứng authorization hay chữ ký bảo mật trong hệ thống thật.

### 9.11. `PrefixedCodeConverter.java`

```java
package demo.converters;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

import java.util.Set;

public final class PrefixedCodeConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(
                String.class, PrefixedCode.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        return sourceType.getType() == String.class
                && targetType.hasAnnotation(RequiredPrefix.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        RequiredPrefix annotation =
                targetType.getAnnotation(RequiredPrefix.class);

        if (annotation == null) {
            throw new IllegalArgumentException(
                    "RequiredPrefix annotation is missing");
        }

        String text = ((String) source).trim();
        String prefix = annotation.value() + "-";

        if (!text.startsWith(prefix)
                || text.length() == prefix.length()) {
            throw new IllegalArgumentException(
                    "Expected a nonempty code starting with " + prefix);
        }

        return new PrefixedCode(text, true);
    }
}
```

Hành vi:
- `getConvertibleTypes()` đăng ký cặp String→PrefixedCode.
- `matches` true **chỉ** khi target descriptor có `@RequiredPrefix`.
- `convert` đọc giá trị prefix của annotation cụ thể, nên `VIP-A7` và `STAFF-B9` có thể có policy khác nhau.
- String chỉ có `"VIP-"` không hợp lệ, vì thiếu phần sau prefix.
- String `"STAFF-B9"` bị từ chối ở target `@RequiredPrefix("VIP")`.

Trong production, nên bổ sung **giới hạn length/allowed characters** của suffix nếu prefix alone chưa đủ. Chỉ có `verified=true` từ converter **không thay việc kiểm tra quyền người dùng**.

### 9.12. `WebConversionConfig.java`

```java
package demo.converters;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {

        registry.addConverter(new StringToOrderNumberConverter());
        registry.addConverterFactory(new CaseInsensitiveEnumFactory());
        registry.addConverter(new PrefixedCodeConverter());
    }
}
```

`FormatterRegistry` cũng có các phương thức đăng ký converter/factory. Khi Spring MVC xây dựng conversion infrastructure, các converter được bổ sung vào MVC conversion service.

**Không nhầm với Jackson:** Cấu hình này phục vụ conversion của query/form/path parameters và các đường Spring MVC binder phù hợp. JSON body qua Jackson/`HttpMessageConverter` có cơ chế deserialization riêng. Đừng dùng kết quả `@RequestBody` JSON làm bằng chứng rằng `Converter<String,OrderNumber>` được chọn.

### 9.13. `ConversionController.java`

```java
package demo.converters;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class ConversionController {

    @GetMapping("/orders")
    public Map<String, String> order(
            @RequestParam("id") OrderNumber id) {

        return Map.of("id", id.value());
    }

    @GetMapping("/levels")
    public Map<String, String> enums(
            @RequestParam("state") OrderState state,
            @RequestParam("level") ReviewLevel level) {

        return Map.of(
                "state", state.name(),
                "level", level.name());
    }

    @GetMapping("/code")
    public Map<String, Object> code(
            @RequestParam("value")
            @RequiredPrefix("VIP") PrefixedCode code) {

        return Map.of(
                "value", code.value(),
                "verified", code.verified());
    }

    public static class Form {
        private OrderNumber order;
        private OrderState state;

        public OrderNumber getOrder() {
            return order;
        }

        public void setOrder(OrderNumber order) {
            this.order = order;
        }

        public OrderState getState() {
            return state;
        }

        public void setState(OrderState state) {
            this.state = state;
        }
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> form(
            @ModelAttribute("form") Form form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "BINDING_ERROR",
                    "fields", fields));
        }

        if (form.getOrder() == null || form.getState() == null) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "MISSING_FORM_FIELD",
                    "fields", java.util.List.of()));
        }

        return ResponseEntity.ok(Map.of(
                "order", form.getOrder().value(),
                "state", form.getState().name()));
    }
}
```

**Những điểm test quan trọng:**
- `@RequestParam OrderNumber` kiểm tra cách MVC dùng converter đơn.
- Hai `@RequestParam` enum types chứng minh factory hoạt động trên nhiều targets.
- `@RequiredPrefix("VIP")` nằm trên method parameter, để `TypeDescriptor` có annotation khi converter được xét.
- `@ModelAttribute Form` dùng `WebDataBinder` với hai properties để test form binding.
- `BindingResult` đứng ngay sau form: khi conversion của form field thất bại, controller có thể trả mã `BINDING_ERROR`.
- Trong demo không đặt Bean Validation constraints trên Form, nên `BINDING_ERROR` thực sự biểu thị conversion/binding failure, không bị trộn vào Jakarta constraint errors.

Endpoint `/code` chỉ minh họa context-driven conversion. Nếu một cấu hình MVC khác không chuyển annotation metadata xuống ConversionService đúng cách, MockMvc test sẽ phát hiện vấn đề tích hợp; unit test `TypeDescriptor` là lớp chẩn đoán đầu tiên.

## 10. Unit tests cho converter đơn

### 10.1. `StringToOrderNumberConverterTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StringToOrderNumberConverterTest {

    private final StringToOrderNumberConverter converter =
            new StringToOrderNumberConverter();

    @Test
    void lowercaseInputIsCanonicalized() {
        assertEquals(new OrderNumber("ORD-0042"),
                converter.convert("ord-0042"));
    }

    @Test
    void surroundingWhitespaceIsTrimmed() {
        assertEquals(new OrderNumber("ORD-0001"),
                converter.convert("  ORD-0001  "));
    }

    @Test
    void canonicalInputIsPreserved() {
        assertEquals(new OrderNumber("ORD-9876"),
                converter.convert("ORD-9876"));
    }

    @Test
    void incorrectPrefixIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("REF-0042"));
    }

    @Test
    void tooFewDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-42"));
    }

    @Test
    void tooManyDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-12345"));
    }

    @Test
    void blankInputIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("   "));
    }

    @Test
    void nonAsciiDigitsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ORD-１２３４"));
    }
}
```

Test này cố tình **không** gọi Spring Test Context. Phụ thuộc duy nhất ở test là JUnit, còn Spring Converter SPI ở class sản xuất. Các trường hợp malformed text bị converter ném `IllegalArgumentException` trực tiếp.

**Chú ý về test encoding:** Tệp Java lưu UTF-8 nếu có full-width Unicode digits; Maven/JDK 17 trong môi trường thông thường hỗ trợ UTF-8 theo cấu hình. Nếu build tool/IDE khác encoding, chỉ định cấu hình source encoding rõ ràng.

## 11. Unit tests cho `ConverterFactory`

### 11.1. `CaseInsensitiveEnumFactoryTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CaseInsensitiveEnumFactoryTest {

    private final CaseInsensitiveEnumFactory factory =
            new CaseInsensitiveEnumFactory();

    @Test
    void convertsFirstEnumCaseInsensitively() {
        assertEquals(OrderState.SHIPPED,
                factory.getConverter(OrderState.class)
                       .convert("shipped"));
    }

    @Test
    void convertsSecondEnumIndependently() {
        assertEquals(ReviewLevel.HIGH,
                factory.getConverter(ReviewLevel.class)
                       .convert("high"));
    }

    @Test
    void trimsWhitespaceForAnyEnum() {
        assertEquals(OrderState.NEW,
                factory.getConverter(OrderState.class)
                       .convert("  new  "));
    }

    @Test
    void unknownConstantIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> factory.getConverter(OrderState.class)
                             .convert("deleted"));
    }

    @Test
    void emptyEnumNameIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> factory.getConverter(ReviewLevel.class)
                             .convert(""));
    }
}
```

Nếu chỉ test `getConverter(OrderState.class)`, một implementation hard-code OrderState vẫn có thể pass. Hai target types giúp bắt lỗi lựa chọn target; test integration ở phần 13 còn chứng minh registry dùng factory này khi có default String→Enum converter.

## 12. Unit tests cho `ConditionalGenericConverter`

### 12.1. `PrefixedCodeConverterTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PrefixedCodeConverterTest {

    private final PrefixedCodeConverter converter =
            new PrefixedCodeConverter();

    // Các field này chỉ dùng để tạo TypeDescriptor thật.
    private static class Targets {
        @RequiredPrefix("VIP")
        private PrefixedCode vip;

        @RequiredPrefix("STAFF")
        private PrefixedCode staff;

        private PrefixedCode plain;
    }

    private static TypeDescriptor target(String field) throws Exception {
        return new TypeDescriptor(
                Targets.class.getDeclaredField(field));
    }

    private static TypeDescriptor source() {
        return TypeDescriptor.valueOf(String.class);
    }

    @Test
    void declaresExactlyOneConvertiblePair() {
        assertEquals(
                Set.of(new GenericConverter.ConvertiblePair(
                        String.class, PrefixedCode.class)),
                converter.getConvertibleTypes());
    }

    @Test
    void matchesAnnotatedVipField() throws Exception {
        assertTrue(converter.matches(source(), target("vip")));
    }

    @Test
    void matchesAnotherAnnotatedField() throws Exception {
        assertTrue(converter.matches(source(), target("staff")));
    }

    @Test
    void doesNotMatchUnannotatedField() throws Exception {
        assertFalse(converter.matches(source(), target("plain")));
    }

    @Test
    void annotatedFieldControlsAcceptedPrefix() throws Exception {
        assertEquals(new PrefixedCode("VIP-A7", true),
                converter.convert("  VIP-A7  ",
                        source(), target("vip")));

        assertEquals(new PrefixedCode("STAFF-X2", true),
                converter.convert("STAFF-X2",
                        source(), target("staff")));
    }

    @Test
    void wrongPrefixAndEmptySuffixAreRejected() throws Exception {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("STAFF-X2",
                        source(), target("vip")));

        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("VIP-",
                        source(), target("vip")));
    }

    @Test
    void directCallWithoutAnnotationHasExplicitFailure()
            throws Exception {

        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("VIP-A7",
                        source(), target("plain")));
    }
}
```

Các field `vip`, `staff`, `plain` không cần khởi tạo object; test chỉ lấy `java.lang.reflect.Field` để xây `TypeDescriptor`. Do đó test không phụ thuộc bean property access hay MVC. Nó chứng minh:
1. Source→target pair được khai báo đúng.
2. Annotation làm `matches` thay đổi từ false sang true.
3. Thuộc tính `value()` của annotation ảnh hưởng conversion.
4. Input có prefix sai vẫn bị từ chối **sau khi** converter được chọn.
5. Gọi thẳng `convert` với target không annotated là **bypass bước selection**, nên implementation tự kiểm tra để fail rõ ràng.

## 13. Integration tests với `ConversionService`

### 13.1. `ConversionServiceTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.core.convert.support.GenericConversionService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConversionServiceTest {

    private static class Fields {
        @RequiredPrefix("VIP")
        private PrefixedCode vip;

        private PrefixedCode unannotated;
    }

    private static TypeDescriptor field(String name) throws Exception {
        return new TypeDescriptor(
                Fields.class.getDeclaredField(name));
    }

    @Test
    void registeredPlainConverterIsUsed() {
        GenericConversionService service =
                new GenericConversionService();

        service.addConverter(new StringToOrderNumberConverter());

        assertTrue(service.canConvert(
                String.class, OrderNumber.class));
        assertEquals(new OrderNumber("ORD-0007"),
                service.convert("ord-0007", OrderNumber.class));
    }

    @Test
    void invalidValueBecomesConversionFailedException() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertThrows(ConversionFailedException.class,
                () -> service.convert(
                        "wrong", OrderNumber.class));
    }

    @Test
    void factoryOverridesDefaultEnumConversion() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverterFactory(new CaseInsensitiveEnumFactory());

        // Lowercase chỉ đúng theo factory case-insensitive.
        assertEquals(OrderState.SHIPPED,
                service.convert("shipped", OrderState.class));
        assertEquals(ReviewLevel.HIGH,
                service.convert("high", ReviewLevel.class));
    }

    @Test
    void annotatedTargetCanBeConverted() throws Exception {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new PrefixedCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor target = field("vip");

        assertTrue(service.canConvert(source, target));

        Object actual = service.convert(
                "VIP-Z9", source, target);

        assertEquals(new PrefixedCode("VIP-Z9", true), actual);
    }

    @Test
    void unannotatedTargetIsNotConvertibleInIsolatedRegistry()
            throws Exception {

        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new PrefixedCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor target = field("unannotated");

        assertFalse(service.canConvert(source, target));
        assertThrows(ConverterNotFoundException.class,
                () -> service.convert("VIP-Z9", source, target));
    }

    @Test
    void typeLevelCanConvertDoesNotValidateInputValues() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertTrue(service.canConvert(
                String.class, OrderNumber.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert(
                        "ORD-NaN", OrderNumber.class));
    }

    @Test
    void nullInputMayBeHandledAtServiceBoundary() {
        GenericConversionService service =
                new GenericConversionService();
        service.addConverter(new StringToOrderNumberConverter());

        assertNull(service.convert(null, OrderNumber.class));
    }
}
```

**Vì sao dùng `GenericConversionService` cho conditional test?** Nó là một registry cô lập với đúng converter đã đăng ký. Khi unannotated target không match, test có cơ sở kỳ vọng `canConvert==false` và `ConverterNotFoundException`. Nếu dùng `DefaultConversionService`, các converter mặc định khác có thể tạo tuyến chuyển đổi thay thế, làm suy luận sai.

**Vì sao dùng `DefaultConversionService` cho enum factory?** Nó có sẵn String→Enum conversion. Sau khi đăng ký factory mới, lowercase enum test chứng minh **factory mới thực sự thắng trong lựa chọn**.

**Quan trọng về exception:** khi gọi `service.convert("wrong", OrderNumber.class)`, Spring có thể bọc `IllegalArgumentException` của converter trong `ConversionFailedException`. Unit test `converter.convert("wrong")` thì kiểm tra exception gốc. Trong môi trường test nâng cao, có thể assert cause class và sanitized message; tránh cố định toàn bộ stack trace hay exception text của Spring.

## 14. MockMvc: chứng minh MVC thực sự sử dụng converter

### 14.1. `ConversionControllerTest.java`

```java
package demo.converters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ConversionController.class)
@Import(WebConversionConfig.class)
class ConversionControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryParameterUsesPlainConverter() throws Exception {
        mvc.perform(get("/api/orders").param("id", "ord-0042"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-0042"));
    }

    @Test
    void invalidOrderNumberFailsBeforeController() throws Exception {
        mvc.perform(get("/api/orders").param("id", "bad"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredOrderIdIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void bothEnumTypesUseCustomFactory() throws Exception {
        mvc.perform(get("/api/levels")
                        .param("state", "shipped")
                        .param("level", "high"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("SHIPPED"))
                .andExpect(jsonPath("$.level").value("HIGH"));
    }

    @Test
    void unknownEnumConstantIsRejected() throws Exception {
        mvc.perform(get("/api/levels")
                        .param("state", "retired")
                        .param("level", "low"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void annotatedRequestParameterUsesConditionalConverter()
            throws Exception {

        mvc.perform(get("/api/code").param("value", "VIP-A7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.value").value("VIP-A7"))
                .andExpect(jsonPath("$.verified").value(true));
    }

    @Test
    void wrongPrefixIsRejectedAfterConditionalSelection()
            throws Exception {

        mvc.perform(get("/api/code").param("value", "STAFF-A7"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void formObjectPropertiesUseRegisteredConverters()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "ord-0008")
                        .param("state", "new"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.order").value("ORD-0008"))
                .andExpect(jsonPath("$.state").value("NEW"));
    }

    @Test
    void invalidFormFieldBecomesBindingResultError()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "wrong")
                        .param("state", "new"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[0]").value("order"));
    }

    @Test
    void missingFormFieldHasDifferentApplicationCode()
            throws Exception {

        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("order", "ord-0008"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_FORM_FIELD"));
    }
}
```

**Lợi ích của `@WebMvcTest`:** chỉ tạo web slice phục vụ MVC, không cần database/server TCP. `@Import(WebConversionConfig.class)` đảm bảo ba converter/factory có mặt trong test context ngay cả khi một phiên bản cấu hình test không tự quét class `@Configuration` ngoài web slice.

Với `@RequestParam` invalid, Spring MVC có thể tạo `MethodArgumentTypeMismatchException` rồi trả HTTP 400 mặc định. Với `@ModelAttribute` form invalid, `BindingResult` đặt ngay sau DTO cho phép controller tự phản hồi `BINDING_ERROR`.

**Bài test quan trọng nhất cho converter có điều kiện:** `annotatedRequestParameterUsesConditionalConverter`. Chỉ cần cấu hình sai cách truyền MethodParameter annotation vào TypeDescriptor là test này có thể fail dù `converter.matches` unit test vẫn pass. Đó chính là lý do cần tầng MVC bên cạnh unit tests.

## 15. Kết quả mong đợi và cách chạy

Tổng các `@Test` trong năm tệp:
- `StringToOrderNumberConverterTest`: 8 test.
- `CaseInsensitiveEnumFactoryTest`: 5 test.
- `PrefixedCodeConverterTest`: 7 test.
- `ConversionServiceTest`: 7 test.
- `ConversionControllerTest`: 10 test.

**Tổng cộng 37 test cases.** Đây là kỳ vọng theo đoạn mã trên, không phải kết quả đã chạy Maven trong lúc soạn bài.

Tại thư mục `conversion-tests-demo`, dùng JDK 17+ và Maven:

```bash
mvn test
```

Có thể chạy một nhóm test:

```bash
mvn -Dtest=StringToOrderNumberConverterTest test
mvn -Dtest=CaseInsensitiveEnumFactoryTest test
mvn -Dtest=PrefixedCodeConverterTest test
mvn -Dtest=ConversionServiceTest test
mvn -Dtest=ConversionControllerTest test
```

Các lớp test không được gắn `@Disabled`, không dựa vào database hay credentials. Nếu tests không pass, xem stack trace và framework version trước khi thay đổi assertion một cách tùy tiện.

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

### 15.1. Thử endpoint `Converter`

```bash
curl -i 'http://localhost:8080/api/orders?id=ord-0042'
```

Kỳ vọng HTTP **200**:

```json
{"id":"ORD-0042"}
```

### 15.2. Thử factory hai enum types

```bash
curl -i 'http://localhost:8080/api/levels?state=shipped&level=high'
```

Kỳ vọng HTTP **200**:

```json
{"state":"SHIPPED","level":"HIGH"}
```

### 15.3. Thử conditional converter

```bash
curl -i 'http://localhost:8080/api/code?value=VIP-A7'
```

Kỳ vọng HTTP **200**:

```json
{"value":"VIP-A7","verified":true}
```

Với `value=STAFF-A7`, converter đã được chọn theo annotation nhưng **kiểm tra giá trị** thất bại, nên request thông thường trả HTTP **400**. Phân biệt điều này với việc một unannotated target **không match**: kết quả có thể là `ConverterNotFoundException`/conversion not supported nếu không có converter khác.

### 15.4. Thử form binding

```bash
curl -i -X POST \
  'http://localhost:8080/api/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'order=ord-0008' \
  --data-urlencode 'state=new'
```

Kỳ vọng HTTP **200**:

```json
{"order":"ORD-0008","state":"NEW"}
```

Gửi `order=bad`:
- `WebDataBinder` thử convert field `order`.
- Converter ném `IllegalArgumentException`.
- Binder ghi lỗi type conversion vào `BindingResult`.
- Controller nhận `errors.hasErrors()==true` và trả `BINDING_ERROR` cùng `fields:["order"]`.

Đây là khác biệt giữa **conversion exception** trong service và **binding error** trong Spring MVC.

## 16. Tại sao không dùng một bài test duy nhất kiểm tra `canConvert`?

`canConvert(Class,Class)` chỉ mô tả **khả năng chuyển kiểu** theo cấu hình hiện tại, không xác thực:
- Input text có hợp lệ không.
- Annotation của target có được xét không.
- Converter của bạn hay default converter được chọn.
- Output có đúng canonical representation không.
- MVC binder/formatter dùng cùng registry không.
- Request HTTP failure xử lý ra sao.

Một test đầy đủ nên kiểm tra ít nhất:

```java
assertTrue(service.canConvert(String.class, OrderNumber.class));
assertEquals(new OrderNumber("ORD-0009"),
        service.convert("ord-0009", OrderNumber.class));
assertThrows(ConversionFailedException.class,
        () -> service.convert("invalid", OrderNumber.class));
```

Với conditional converter, nên dùng `TypeDescriptor` từ annotated field/parameter. Không suy luận rằng `canConvert(String.class, PrefixedCode.class)==false` là converter hỏng; với target không annotation, điều đó có thể đúng theo yêu cầu.

## 17. Phân biệt errors ở 3 tầng

| Tầng | Test input | Kết quả thường kiểm |
| --- | --- | --- |
| Gọi thẳng `Converter.convert` | `"bad"` | `IllegalArgumentException` |
| `ConversionService.convert` | `"bad"` | `ConversionFailedException` khi converter được chọn |
| `ConversionService` không có route | String→PrefixedCode target không annotated | `ConverterNotFoundException` |
| Spring MVC `@RequestParam` | `?id=bad` | HTTP 400 qua type mismatch |
| Spring MVC `@ModelAttribute` | `order=bad` | `FieldError` trong `BindingResult`; controller có thể trả 400 |
| Jackson JSON `@RequestBody` | JSON field string→value object | Jackson deserialization path, không mặc định dùng ConverterRegistry |
| Jakarta Validation `@Valid` | Dữ liệu convert được nhưng vi phạm annotation constraint | Một validation path khác, thường `MethodArgumentNotValidException` |

### 17.1. Không test toàn bộ exception message

Message Spring bao gồm source/target type và có thể thay đổi khi nâng Spring. Unit test nên assert exception **type**, root cause khi cần, và lỗi HTTP có machine-readable code nếu ứng dụng đã định nghĩa. Đừng hard-code toàn bộ `ex.getMessage()` trừ khi đó là hợp đồng do bạn chủ động tạo và quản lý.

### 17.2. Negative test phát hiện sai registration

Một tình huống kinh điển: bạn có unit test converter đơn pass, nhưng quên đăng ký converter vào `WebMvcConfigurer#addFormatters`. MockMvc request `?id=ord-0042` có thể:
- Đi qua một built-in converter khác nếu target class có cách khởi tạo đặc biệt.
- Không tìm thấy tuyến chuyển kiểu, dẫn đến lỗi.
- Trả một giá trị khác với canonical form mong đợi.

Vì vậy assert **output value** như `ORD-0042`, không chỉ assert `200`. Điều này giúp phát hiện converter bạn viết thực sự được dùng, chứ không phải một fallback khác vô tình làm test pass.

## 18. Test theo bảng dữ liệu với `@ParameterizedTest`

Khi số lượng edge cases tăng, có thể dùng JUnit Jupiter parameterized tests.

```java
@ParameterizedTest
@ValueSource(strings = {
        "BAD", "ORD-1", "ORD-12345", "", "ORD-12AB"
})
void invalidOrderIdentifiersAreRejected(String input) {
    assertThrows(IllegalArgumentException.class,
            () -> converter.convert(input));
}
```

Đây là fragment minh họa, cần imports:
`org.junit.jupiter.params.ParameterizedTest`,
`org.junit.jupiter.params.provider.ValueSource`,
`org.junit.jupiter.api.Assertions.assertThrows` và một `converter` được tạo. Nó có thể thay nhiều tests cùng cấu trúc; trong project hoàn chỉnh, ta giữ các method riêng để bài học dễ truy vết từng failure.

Đối với nhiều enum targets, có thể dùng `@MethodSource` với stream của target class, input và expected. Nhưng generics của `ConverterFactory<String,Enum>` có thể phức tạp hơn: giữ unit test tách rời đôi khi rõ ràng hơn một parameterized test phải dùng raw types.

## 19. MockMvc test slice và whole-context test

### 19.1. `@WebMvcTest` phù hợp khi nào?

Dùng cho:
- Query/path/form binding.
- Controller handler selection.
- MVC conversion/formatting/argument resolution.
- Error response do MVC và controller tạo.

`@WebMvcTest(ConversionController.class)` thường không khởi tạo toàn bộ service/repository. Nếu controller inject dependencies, bạn cần mock/bean test phù hợp. Ví dụ này có controller không có external dependencies nên web slice gọn.

### 19.2. `@SpringBootTest` cần khi nào?

Dùng thêm một số test `@SpringBootTest` khi phải chứng minh:
- Component scan, configuration của ứng dụng thật.
- Có nhiều `WebMvcConfigurer` tác động lẫn nhau.
- Security filters, custom conversion services, MVC advice/other auto-config ảnh hưởng.
- Registration phụ thuộc bean tự động hoặc profile.

Không cần thay mọi unit test bằng `@SpringBootTest`. Mỗi test nên bao phủ trách nhiệm với chi phí nhỏ nhất đủ tin cậy.

### 19.3. `@AutoConfigureMockMvc` khác `@WebMvcTest`

Trong whole-context test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class IntegrationTest {
    @Autowired MockMvc mvc;
}
```

Đây là snippet minh họa; cần imports. Với `@WebMvcTest`, Boot đã cung cấp MockMvc web-slice support tương ứng, không cần tự dựng `MockMvcBuilders.standaloneSetup(...)` trong ví dụ. Khi dùng standalone setup, bạn phải **tự cấu hình** conversion service/resolvers tương ứng; nếu không, test có thể khác production MVC.

## 20. Các tình huống khó dễ bị bỏ sót

### 20.1. Converter bị chọn sai do metadata mất mát

`TypeDescriptor.valueOf(PrefixedCode.class)` không mang field annotation. Nếu test cần xét `@RequiredPrefix`, hãy dùng:
- `new TypeDescriptor(Field)` cho annotated field.
- `new TypeDescriptor(MethodParameter)` cho annotated method parameter khi phù hợp.
- Hoặc Spring MVC test với một annotated handler parameter thật.

Không tạo một fake boolean `hasAnnotation=true` trong test nếu có thể sử dụng reflection metadata thực tế. Real TypeDescriptor giúp phát hiện lỗi retention/target của annotation.

### 20.2. Multiple candidate converters

Nếu cùng cặp String→Target có nhiều converter, việc lựa chọn có thể phụ thuộc đăng ký/độ cụ thể/condition. Tránh assertion dựa vào thứ tự không được đặc tả rõ trong contract của ứng dụng. Cô lập conditional converter bằng `GenericConversionService` cho unit selection; dùng `DefaultConversionService` để test giao thoa với defaults có chủ đích.

### 20.3. Empty string và null

`source.trim()` có thể thành `""`; converter ở project sẽ từ chối vì regex/prefix check. Từ chối chuỗi trống khác với `null` do framework truyền tới controller cho optional arguments.

Nếu mục tiêu là “thiếu bắt buộc”, đó là vấn đề argument presence/Bean Validation, không phải converter tự đoán `null` là hợp lệ ở mọi ngữ cảnh.

### 20.4. Whitespace Unicode

`String.trim()` chỉ loại bỏ một số ký tự whitespace truyền thống; `strip()` dùng `Character.isWhitespace` và có semantics khác. Chọn đúng theo contract API và viết tests cho `\u00A0`, `\u2003`, tab, xuống dòng nếu việc canonicalize ảnh hưởng bảo mật.

### 20.5. Locale

`toUpperCase(Locale.ROOT)` giúp tránh thay đổi theo locale của JVM. Nếu converter liên quan user-visible currency/dates, `Formatter<T>` với `Locale` có thể phù hợp hơn `Converter<S,T>`, nhưng đó là một tập test riêng.

### 20.6. Converter thread safety

Spring có thể dùng cùng converter instance trong nhiều requests. Unit test không thay cho concurrency tests khi converter chứa cache mutable hoặc I/O. Với converter stateless của project, không có state request để race; nếu thêm cache, hãy dùng cấu trúc thread-safe hoặc immutable và test dưới tải hợp lý.

### 20.7. Value object invariant

Dù có converter, domain object vẫn nên tự giữ invariant khi các code paths khác có thể tạo object trực tiếp. Trong project mẫu, `OrderNumber` chỉ là record chứa String và validator nằm trong converter; sản phẩm thật có thể chuyển rule vào constructor/factory domain để không cho tạo `OrderNumber("BAD")` từ nguồn khác. Khi đó test phải bổ sung direct domain constructor tests để giữ single source of truth.

### 20.8. Không gộp type conversion với business authorization

`@RequiredPrefix("VIP")` chứng minh metadata-driven conversion, không có nghĩa người gửi chuỗi VIP- được cấp quyền VIP. Quyền thực tế dựa vào authenticated identity và service authorization, không phụ thuộc chuỗi user tự cung cấp.

### 20.9. ConversionService là capability không phải validator

Một converter nên chuyển dữ liệu và từ chối input không đúng cú pháp. Các constraint như `@Min`, `@NotBlank`, `@Valid` kiểm tra domain validity sau đó. Dùng converter để gọi database tìm quyền mỗi request có thể tạo dependency không rõ ràng; cần phân biệt syntactic conversion, validation và authorization.

### 20.10. Collection/Map conversion

Một `Converter<String,OrderNumber>` có thể được dùng gián tiếp để chuyển các phần tử collection khi DefaultConversionService có converter tập hợp. Nhưng `canConvert(List.class,List.class)` không đủ để chứng minh từng element hợp lệ: dùng `TypeDescriptor.collection(...)` với generic element type và test values.

Ví dụ minh họa:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToOrderNumberConverter());

Object result = service.convert(
        java.util.List.of("ord-0001", "ord-0002"),
        TypeDescriptor.collection(
                java.util.List.class,
                TypeDescriptor.valueOf(String.class)),
        TypeDescriptor.collection(
                java.util.List.class,
                TypeDescriptor.valueOf(OrderNumber.class)));
```

Với các converter collection mặc định, kết quả có thể là List các `OrderNumber` tương ứng. Đây là fragment minh họa **không nằm trong test suite chính**; nếu dùng trong sản phẩm, assert size, element types, values và behavior khi có một phần tử sai định dạng.

## 21. Checklist QA khi review converter tests

1. Có nêu **source type** và **target type** đúng của converter/factory?
2. Unit test converter có assert canonical output thay vì chỉ non-null?
3. Có test dữ liệu biên, whitespace, case, prefix/regex, invalid text?
4. Có phân biệt exception trực tiếp `IllegalArgumentException` với service `ConversionFailedException`?
5. Test factory có dùng **ít nhất hai target subclasses** thay vì một enum?
6. Có test factory được đăng ký trong `DefaultConversionService` với defaults?
7. Có đọc `getConvertibleTypes()` của GenericConverter và assert cặp khai báo?
8. Có test `matches` cả true và false?
9. Với condition dựa annotation, `TypeDescriptor` có thật sự chứa annotation?
10. Có test giá trị runtime sau khi condition đã match?
11. Có test source/target Class descriptor **không** tương đương annotated field descriptor?
12. Có kiểm tra `canConvert` nhưng không xem đó là validation của input?
13. Có dùng registry mới cho từng test thay vì thay shared singleton?
14. Có một MockMvc test chứng minh Spring MVC **thật sự** gọi converter?
15. Có test invalid query và invalid form binding riêng?
16. Có phân biệt `@RequestBody`/Jackson với binder conversion?
17. Có tránh khẳng định mọi conversion error đều là Jakarta Bean Validation failure?
18. Có tránh assert toàn bộ nội dung Spring exception message?
19. Có test normalization với `Locale.ROOT` nếu cần stable identifiers?
20. Nếu converter có mutable state, có kiểm thử thread safety/invariants?
21. Có lệnh build `mvn test` và tệp/class/path khớp package?
22. Kết quả dự kiến có được ghi là **kỳ vọng**, không mạo nhận đã chạy?
23. Nếu thay framework version, có test lại method annotation metadata và converter selection?
24. Có tách authorization khỏi conversion của những chuỗi nhìn như role/token?

## 22. Sai lầm thường gặp

| Sai lầm | Kết quả | Cách sửa |
| --- | --- | --- |
| Chỉ test `convert()` và nghĩ Spring sẽ tự dùng nó | Quên đăng ký hoặc registry chọn converter khác | Thêm `ConversionService` + MockMvc test |
| Chỉ test `canConvert` | Không phát hiện input sai, output sai | Assert `convert` với giá trị thật và negative inputs |
| Test `ConverterFactory` bằng một enum | Không bắt lỗi hard-code target class | Test nhiều target enum classes |
| Dùng `TypeDescriptor.valueOf(Target.class)` cho conditional annotation | Mất field/parameter metadata | Dùng `new TypeDescriptor(Field/MethodParameter)` |
| `matches()` luôn true | Converter ảnh hưởng những nơi không có annotation | Kiểm tra đúng target context |
| `matches()` kiểm tra runtime source value | Interface không có value | Dùng `convert` kiểm tra nội dung, `matches` kiểm tra metadata |
| Không kiểm tra getConvertibleTypes | Converter không được registry xem là ứng viên | Test pair String→target |
| Expect `IllegalArgumentException` từ `ConversionService.convert` | Thường nhận wrapper `ConversionFailedException` | Assert phù hợp tầng đang test |
| Expect `ConverterNotFoundException` khi converter đã match nhưng text sai | Tìm thấy converter, chỉ conversion thất bại | Assert `ConversionFailedException` |
| Dùng `DefaultConversionService` để khẳng định “conditional không match thì không thể convert” | Có thể có fallback khác | Dùng registry cô lập và assert `matches` |
| Hard-code JVM locale trong test | CI locale khác gây fail | Chuẩn hóa với `Locale.ROOT` |
| Dùng `@WebMvcTest` mà thiếu converter config | MockMvc không có expected registry | `@Import(WebConversionConfig.class)` |
| Dùng standalone MockMvc không khai báo conversion service | Hành vi khác production | Tự cấu hình MVC service hoặc dùng web slice |
| Test JSON `@RequestBody` để chứng minh String→value converter | Jackson có pipeline riêng | Dùng query/form/path binding |
| Trả “invalid code” mà log raw input secrets | Rò rỉ data | Sanitize messages/logging |
| Nhầm `@Min`/`@NotBlank` với conversion | Validation là pha khác | Test riêng binding vs constraints |
| Tạo converter stateful trong singleton | Race giữa requests | Stateless/immutable hoặc đồng bộ đúng |
| Bỏ business authorization vì value đã convert được | Chuỗi hợp cú pháp không chứng minh quyền | Kiểm tra principal/permissions tại service |

## 23. Bài tập tự luyện

1. Bổ sung test `ORD-0000` và `ORD-9999` cho hai giá trị biên của mã đơn.
2. Thêm quy tắc từ chối `ORD-9999` vì đây là ID dự trữ; phân biệt syntax conversion với domain policy.
3. Thay `trim()` bằng `strip()` và kiểm tra Unicode whitespace như `\u2003`, giải thích contract thay đổi.
4. Thêm enum `PaymentMethod { CARD, CASH }`; không sửa factory và viết test xác nhận target thứ ba vẫn hoạt động.
5. Thử input enum `"ShIpPeD"` và whitespace khác nhau, xác nhận case-insensitive.
6. Viết test `DefaultConversionService` **không** đăng ký custom factory và so sánh `"shipped"` với khi đã đăng ký.
7. Chuyển annotation `@RequiredPrefix` sang một value khác như `"PARTNER"`; dùng TypeDescriptor field để test dynamic annotation attribute.
8. Bỏ annotation trên field `vip`; xác nhận `matches=false` và `canConvert` cho contextual target thay đổi.
9. Đăng ký thêm một plain `Converter<String,PrefixedCode>` và quan sát fallback khi conditional converter không match; không khẳng định thứ tự nếu chưa kiểm chứng framework version.
10. Thêm `@RequestParam @RequiredPrefix("STAFF")` endpoint, test prefix VIP bị từ chối.
11. Viết test conversion collection `List<String> -> List<OrderNumber>` với hai elements hợp lệ và một invalid element.
12. Tạo DTO Form có field annotated `@RequiredPrefix` rồi kiểm thử WebDataBinder có giữ field annotations khi property binding không.
13. Thử gửi nhiều query parameters với cùng tên và xem argument resolver truyền loại dữ liệu nào vào converter.
14. Thêm error response JSON có machine-readable code cho `MethodArgumentTypeMismatchException` nhưng không trả raw value.
15. Thêm `@NotBlank`, `@Valid` và provider Jakarta Validation để test rằng syntax conversion thành công nhưng constraint vẫn có thể thất bại.
16. Dùng `@SpringBootTest + @AutoConfigureMockMvc` cho một test để chứng minh component scan/auto-configuration trong ứng dụng thật.
17. Refactor `OrderNumber` để constructor tự kiểm tra invariant, rồi test direct construction và converter.
18. Viết parameterized tests cho mười invalid code strings, phân tích khi nào một test method với nhiều cases tốt hơn nhiều test methods.
19. So sánh converter có điều kiện dựa trên target annotations với một `Formatter` cần locale: bài toán nào hợp hơn?
20. Viết checklist review converter được đưa vào global ConversionService, đặc biệt chỗ có thể vô tình override built-in types.

**Kết luận:** Kiểm thử type conversion trong Spring không dừng ở lời gọi `convert()`. Với `Converter`, kiểm chứng **giá trị và lỗi**; với `ConverterFactory`, kiểm chứng **nhiều target types**; với `ConditionalGenericConverter`, kiểm chứng **selection theo TypeDescriptor và annotation**. Cuối cùng, test `ConversionService` và `MockMvc` để chứng minh các converter được **đăng ký và sử dụng thật**. Đây là cách bắt những lỗi mà unit test đơn lẻ không thể phát hiện.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Converter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConverterFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConverterFactory.html)
- [Spring Framework 6.2 — ConditionalGenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework 6.2 — GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework 6.2 — TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework 6.2 — GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework 6.2 — ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — Spring MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Boot 3.5 — Testing Web Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit 5 — User Guide / Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)