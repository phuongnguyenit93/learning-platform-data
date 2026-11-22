# GenericConversionService và cơ chế tra cứu converter trong Spring Framework

## 1. Vai trò của GenericConversionService

Spring cung cấp interface ConversionService để kiểm tra và thực hiện chuyển đổi giữa các kiểu Java. Ứng dụng đăng ký converter vào registry rồi yêu cầu service chuyển một giá trị từ source type sang target type.

GenericConversionService trong org.springframework.core.convert.support là implementation tổng quát quản lý converter và tra cứu converter phù hợp. Nó hỗ trợ ConversionService và khả năng đăng ký qua ConverterRegistry. DefaultConversionService bổ sung nhiều converter thông dụng; FormattingConversionService kết hợp conversion với formatting.

```java
ConversionService service = new DefaultConversionService();
Integer age = service.convert("28", Integer.class);
Boolean active = service.convert("true", Boolean.class);
```

GenericConversionService mới tạo là registry tổng quát, không tự cài toàn bộ converter mặc định như DefaultConversionService.

| Thành phần | Trách nhiệm |
| --- | --- |
| ConversionService | canConvert(...) và convert(...) |
| ConverterRegistry | Đăng ký và gỡ converter |
| GenericConversionService | Quản lý registry, lookup, điều kiện và cache |
| DefaultConversionService | Cung cấp bộ converter mặc định |

## 2. Các API chính

ConversionService có nhóm overload dùng Class và nhóm dùng TypeDescriptor:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);

boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(Object source, TypeDescriptor sourceType,
               TypeDescriptor targetType);
```

Class chỉ biểu diễn raw type. TypeDescriptor còn mang generic element type, annotation và property context. Khi conversion phụ thuộc List<Integer>, Map key/value hoặc annotation trên field, TypeDescriptor là metadata quan trọng.

ConverterRegistry có các phương thức đăng ký thường dùng:

```java
<S, T> void addConverter(Converter<S, T> converter);
<S, T> void addConverter(Class<S> sourceType, Class<T> targetType,
                         Converter<? super S, ? extends T> converter);
void addConverter(GenericConverter converter);
void addConverterFactory(ConverterFactory<?, ?> factory);
void removeConvertible(Class<?> sourceType, Class<?> targetType);
```

Đây là các chữ ký rút gọn minh họa SPI. canConvert chỉ kiểm tra cặp kiểu có khả năng chuyển đổi; nó không đảm bảo dữ liệu cụ thể sẽ parse thành công.

## 3. Các loại converter

| SPI | Sử dụng |
| --- | --- |
| Converter<S,T> | Một cặp source/target đơn giản, type-safe |
| ConverterFactory<S,R> | Một source chuyển sang họ target type |
| GenericConverter | Nhiều cặp hoặc cần TypeDescriptor |
| ConditionalConverter | Candidate chỉ hợp lệ trong một context |

### Converter<S,T>

```java
public final class StringToOrderStatus
        implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

OrderStatus là enum của ứng dụng. Spring suy ra cặp String → OrderStatus từ generic signature khi đăng ký instance. Đây thường là lựa chọn tốt cho một cặp chuyển đổi cụ thể.

### ConverterFactory<S,R>

Factory tạo converter theo kiểu đích cụ thể, hữu ích khi source String có thể chuyển sang nhiều enum khác nhau. Factory nhận target class qua getConverter(targetType). Không nên dùng factory nếu mỗi target có logic hoàn toàn riêng; converter cụ thể có thể dễ đọc hơn.

### GenericConverter

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();
    Object convert(Object source, TypeDescriptor sourceType,
                   TypeDescriptor targetType);
}
```

getConvertibleTypes khai báo các cặp class được hỗ trợ. convert nhận descriptor để có thể xét generic metadata và annotation. ConditionalGenericConverter kết hợp GenericConverter với matches(sourceType, targetType).

Không nên dùng GenericConverter cho logic một cặp đơn giản nếu Converter<S,T> đã diễn đạt đủ rõ ràng.

## 4. Registry được tổ chức thế nào?

Ở mức khái niệm, GenericConversionService quản lý registry converters và cache lookup. Registry có một tập converter global và map theo ConvertiblePair. Mỗi ConvertiblePair có thể có một hoặc nhiều candidate; cache ánh xạ cặp TypeDescriptor nguồn/đích sang converter được chọn hoặc marker không tìm thấy.

```text
GenericConversionService
├── converters
│   ├── globalConverters
│   └── Map<ConvertiblePair, ConvertersForPair>
│       ├── (String, Integer)
│       └── (String, OrderStatus)
└── converterCache
    ├── (source descriptor, target descriptor) -> converter
    └── (source descriptor, target descriptor) -> NO_MATCH
```

Đây là mô hình nội bộ để giải thích lookup. Các field và class như converters, ConvertersForPair, ConverterCacheKey, converterCache và NO_MATCH không phải API public để ứng dụng thao tác trực tiếp.

## 5. Luồng tra cứu converter

Khi gọi service.convert("42", Integer.class), quy trình khái quát:

1. Kiểm tra target type và xác định TypeDescriptor nguồn/đích.
2. Xử lý source null theo quy tắc riêng.
3. Tạo cache key từ source và target descriptor.
4. Tra cache. Nếu có converter thì sử dụng; nếu có NO_MATCH thì biết lần trước không tìm thấy.
5. Khi cache miss, registry tìm converter bằng cách duyệt hierarchy class/interface của source và target.
6. Candidate có điều kiện phải vượt qua matches(sourceType, targetType).
7. Nếu không có candidate, xét converter mặc định.
8. Lưu kết quả lookup vào cache.
9. Gọi converter đã chọn hoặc phát sinh exception nếu không có đường chuyển đổi.

```text
convert(source, sourceType, targetType)
             |
             v
       tạo cache key
             |
             v
         cache hit? ---- yes ----> dùng kết quả
             |
             no
             v
     registry.find(source, target)
             |
             v
      duyệt source/target hierarchy
             |
             v
       tìm candidate theo pair
             |
             v
    ConditionalConverter.matches?
             |
       match -> chọn converter
       no match -> candidate tiếp
             |
             v
      không có candidate?
             |
             v
       default converter/no-op
             |
             v
         cache kết quả
             |
             v
        thực hiện conversion
```

Converter mặc định có thể là no-op nếu source assignable sang target. Khi ấy Spring trả lại object nguồn. Nếu không có converter và source không gán được cho target, conversion không khả dụng.

Thứ tự duyệt hierarchy là chi tiết implementation. Không xây business rule dựa trên một thứ tự ưu tiên nội bộ; hãy khai báo converter cụ thể và điều kiện rõ ràng.

## 6. Tra cứu theo hierarchy

Converter đăng ký cho supertype có thể được dùng với source subclass tương thích. Ví dụ converter BaseCode → String có thể làm candidate cho source SpecialCode nếu SpecialCode kế thừa BaseCode. Hierarchy của target cũng tham gia quá trình tìm cặp ứng viên.

```java
class BaseCode {
    private final String value;
    BaseCode(String value) { this.value = value; }
    public String value() { return value; }
}
class SpecialCode extends BaseCode {
    SpecialCode(String value) { super(value); }
}
```

Registry thử các cặp source/target candidate. Generic checks và conditional matches vẫn có thể loại candidate dù raw class có quan hệ kế thừa. Không giả định converter cho Object luôn là lựa chọn ưu tiên.

## 7. ConditionalConverter

ConditionalConverter có phương thức:

```java
boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
```

Nó cho phép cùng một cặp class chỉ áp dụng trong một context, chẳng hạn target field có annotation riêng. Một ConditionalGenericConverter có thể kiểm tra targetType.getAnnotation(MyAnnotation.class) rồi trả true/false.

matches chỉ là bước chọn candidate, không phải conversion. Method này nên nhẹ, ổn định và không có side effect, bởi lookup có thể được cache.

## 8. TypeDescriptor và generic metadata

TypeDescriptor có thể biểu diễn kiểu property, generic element type của array/collection/map, annotation và property context.

Ví dụ List<String> và List<Integer> đều có raw class List.class, nhưng element type khác nhau. Khi metadata đầy đủ và có converter cho từng phần tử, Spring có thể chuyển từng item. Nếu chỉ gọi convert(source, List.class), target generic Integer không được thể hiện. Java generic cast sau conversion không cung cấp metadata runtime cho Spring.

Khi cần generic conversion, dùng overload TypeDescriptor với descriptor lấy từ field, method parameter hoặc property phù hợp. Kiểm tra source và target descriptors trước khi kết luận converter có thể xử lý collection.

## 9. Converter cache và NO_MATCH

Cache key chứa source TypeDescriptor và target TypeDescriptor. Cache value có thể là converter đã chọn hoặc sentinel NO_MATCH khi lookup không tìm được candidate.

- Lần đầu String → OrderStatus: cache miss, tìm converter, lưu converter.
- Lần sau cùng descriptor: cache hit, dùng converter đã lưu.
- Lần đầu Input → Target không hỗ trợ: cache miss, lưu NO_MATCH.
- Lần sau: cache hit NO_MATCH, tránh lặp lookup.

Cache lưu kết quả tra cứu converter, không lưu giá trị đã convert. Mỗi input mới vẫn chạy converter. Khi thêm hoặc gỡ converter, implementation hiện tại invalidates cache để lookup sau phản ánh registry mới. Không dùng reflection để truy cập hoặc xóa cache nội bộ; dùng API add/remove.

## 10. No-op conversion, null và lỗi

Nếu không có converter cụ thể nhưng source assignable sang target, GenericConversionService có thể trả lại source. Ví dụ StringBuilder sang CharSequence có thể giữ nguyên reference.

```java
GenericConversionService service = new GenericConversionService();
StringBuilder source = new StringBuilder("hello");
CharSequence target = service.convert(source, CharSequence.class);
System.out.println(target == source);
```

Stdout:

```text
true
```

Với null, target reference type thường nhận null; target Optional có thể nhận Optional.empty theo hành vi mặc định. Primitive như int không nhận null nên conversion sẽ thất bại. Đừng kết luận mọi converter custom có hành vi null giống nhau.

| Exception | Ý nghĩa |
| --- | --- |
| ConverterNotFoundException | Không tìm thấy converter; source không assignable |
| ConversionFailedException | Converter đã chọn nhưng giá trị cụ thể chuyển đổi thất bại |

Nếu không có converter String → Integer, lỗi có thể là ConverterNotFoundException. Nếu có converter nhưng nó gọi Integer.valueOf("abc"), lookup thành công nhưng parse thất bại và có thể được biểu diễn bằng ConversionFailedException bọc NumberFormatException. Kiểm tra cause để tìm nguyên nhân gốc.

## 11. Java 17+ demo: đăng ký và lookup converter

Ví dụ dùng Spring Framework 6.2.x, Java 17+ và Maven. Tạo pom.xml với dependency spring-core phiên bản 6.2.12:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core</artifactId>
    <version>6.2.12</version>
</dependency>
```

Tạo file src/main/java/demo/GenericConversionDemo.java:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.GenericConversionService;

public class GenericConversionDemo {
    enum OrderStatus { NEW, PAID, SHIPPED }

    public static void main(String[] args) {
        GenericConversionService service =
                new GenericConversionService();

        System.out.println("before=" + service.canConvert(
                String.class, OrderStatus.class));

        service.addConverter(new Converter<String, OrderStatus>() {
            @Override
            public OrderStatus convert(String source) {
                return OrderStatus.valueOf(
                        source.trim().toUpperCase(Locale.ROOT));
            }
        });

        System.out.println("after=" + service.canConvert(
                String.class, OrderStatus.class));

        OrderStatus status =
                service.convert(" paid ", OrderStatus.class);
        System.out.println("status=" + status);

        StringBuilder source = new StringBuilder("hello");
        CharSequence same =
                service.convert(source, CharSequence.class);
        System.out.println("sameReference=" + (source == same));

        try {
            service.convert("10", Integer.class);
        } catch (RuntimeException ex) {
            System.out.println("missing="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.GenericConversionDemo
```

Stdout do main tạo:

```text
before=false
after=true
status=PAID
sameReference=true
missing=ConverterNotFoundException
```

Service trống chưa có String → OrderStatus converter, nên before=false. Sau addConverter, registry có cặp phù hợp. Chuỗi " paid " trở thành enum PAID. StringBuilder assignable sang CharSequence nên no-op giữ cùng reference. Service trống không có String → Integer converter, vì vậy trường hợp cuối minh họa converter not found.

Nếu dùng DefaultConversionService, dòng cuối không còn lỗi thiếu converter vì service mặc định có chuyển đổi String → Integer.

## 12. GenericConverter và collection conversion

GenericConverter có thể khai báo nhiều ConvertiblePair và dùng TypeDescriptor để phân biệt target. Ví dụ converter String → CustomerId và String → InvoiceId có thể khai báo cả hai cặp trong getConvertibleTypes(). Trong convert, xem targetType.getObjectType() để tạo đúng kiểu đích. CustomerId và InvoiceId là class miền nghiệp vụ do ứng dụng định nghĩa.

Với List<String> → List<Integer>, descriptor cung cấp element type để framework chọn converter cho mỗi phần tử. Với Map, metadata có thể mô tả cả key và value type. Nếu descriptor thiếu generic information, conversion có thể không chọn được converter mong muốn hoặc chỉ thấy raw container type.

Không tự cast kết quả thành List<Integer> khi chưa cung cấp target descriptor. Type erasure khiến cast không tự chuyển phần tử.

## 13. Registration và removal

| API | Tác dụng |
| --- | --- |
| addConverter(Converter) | Đăng ký converter theo generic type |
| addConverter(Class, Class, Converter) | Đăng ký cặp rõ ràng |
| addConverter(GenericConverter) | Đăng ký nhiều cặp/context |
| addConverterFactory(ConverterFactory) | Đăng ký factory |
| removeConvertible(source, target) | Gỡ converter theo pair |

Có thể nhiều conditional candidate cùng cặp; registry xét điều kiện phù hợp. Tránh nhiều converter trùng pair nhưng không có rule rõ ràng. Viết test cho từng TypeDescriptor và candidate. Đừng dùng thứ tự đăng ký làm business rule.

Thông thường đăng ký converter khi application khởi động và chia sẻ ConversionService đã cấu hình. Tránh thay đổi registry theo từng request, làm semantics conversion thay đổi giữa các request.

## 14. GenericConversionService, DefaultConversionService và MVC

| Implementation | Mục đích |
| --- | --- |
| GenericConversionService | Registry tổng quát |
| DefaultConversionService | Bộ converter mặc định |
| FormattingConversionService | Conversion kết hợp Formatter |
| DefaultFormattingConversionService | Formatting service có defaults |

Spring MVC cho phép đăng ký converter qua WebMvcConfigurer.addFormatters:

```java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatus());
    }
}
```

Đây là class cấu hình MVC cần các import và converter class tương ứng. Đăng ký converter vào một instance GenericConversionService cục bộ không khiến MVC tự động dùng instance ấy; phải gắn vào đúng FormatterRegistry/ConversionService của application context.

JSON @RequestBody thường được deserialize bằng HttpMessageConverter như Jackson. ConversionService không thay thế toàn bộ Jackson mapping; với định dạng JSON riêng có thể cần cấu hình serializer/deserializer hoặc module Jackson.

## 15. Lỗi thường gặp và cách debug

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ConverterNotFoundException | Thiếu converter và source không assignable | Kiểm tra source/target pair |
| ConversionFailedException | Converter có mặt nhưng parse lỗi | Xem cause và input |
| canConvert=false | Registry thiếu converter hoặc condition không match | Kiểm tra registration/descriptor |
| canConvert=true nhưng convert lỗi | Dữ liệu cụ thể sai định dạng | Kiểm tra converter logic |
| Converter không chạy trong MVC | Đăng ký vào service instance khác | Dùng đúng FormatterRegistry |
| Generic element không chuyển | Thiếu target element descriptor | Cung cấp TypeDescriptor đầy đủ |
| String→Integer fail với service trống | Chưa có default converter | Dùng DefaultConversionService hoặc add converter |
| Null vào primitive | Primitive không thể nhận null | Dùng wrapper hoặc xử lý null |
| Converter mới không được chọn | Candidate khác hoặc conditional mismatch | Debug matches và hierarchy |
| JSON không dùng converter MVC | Jackson HttpMessageConverter xử lý body | Cấu hình Jackson |

Quy trình debug:
1. Xác định source runtime class và target type.
2. Kiểm tra canConvert bằng overload đúng.
3. Xác minh converter vào đúng registry/service instance.
4. Đặt breakpoint tại Converter.convert và ConditionalConverter.matches.
5. Kiểm tra source/target hierarchy, TypeDescriptor và generic info.
6. Phân biệt thiếu converter với conversion failure.
7. Trong MVC, xác minh WebMvcConfigurer/FormatterRegistry của context thật.

Không phụ thuộc vào class nội bộ ConverterAdapter/ConverterCacheKey trong mã ứng dụng; chúng hữu ích khi đọc source framework nhưng không phải API extension.

## 16. Hiệu năng và thread safety

ConversionService được thiết kế để cấu hình và chia sẻ. Converter do ứng dụng viết nên stateless hoặc thread-safe. Cache lookup giảm việc duyệt hierarchy lặp lại, nhưng conversion vẫn chạy cho từng giá trị.

- Không giữ request-specific mutable state trong converter.
- Tránh I/O hoặc query database trong converter.
- Không đăng ký nhiều converter cạnh tranh không có điều kiện rõ.
- Đăng ký cấu hình converter ở startup.
- Test giá trị hợp lệ, sai định dạng, null, generic type và source subclass.
- Không dùng conversion làm validation hoặc authorization nghiệp vụ.

Nếu conversion phụ thuộc locale, cân nhắc Formatter. Nếu phụ thuộc annotation/property context, cân nhắc GenericConverter với ConditionalConverter. Nếu chỉ có một cặp đơn giản, Converter<S,T> dễ bảo trì hơn.

## 17. Checklist và tóm tắt

1. Chọn đúng SPI: Converter, ConverterFactory hoặc GenericConverter.
2. Khai báo source/target pair đủ cụ thể.
3. Dùng TypeDescriptor khi generic/annotation context quan trọng.
4. Dùng ConditionalConverter khi selection phụ thuộc metadata.
5. Đăng ký vào đúng ConversionService mà framework sử dụng.
6. Phân biệt converter not found, conversion failed, null và no-op.
7. Hiểu cache lưu converter/NO_MATCH, không lưu giá trị output.
8. Test hierarchy, collection, null, error path và MVC integration.

GenericConversionService quản lý registry, tra cứu converter theo source/target TypeDescriptor, kiểm tra candidate và cache lookup. Khi cache miss, registry xét hierarchy và conditional matches; nếu không có converter, source assignable sang target có thể dùng no-op. DefaultConversionService cung cấp converter mặc định, còn MVC sử dụng registry được gắn trong application context.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [ConverterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalConverter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [DefaultConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
