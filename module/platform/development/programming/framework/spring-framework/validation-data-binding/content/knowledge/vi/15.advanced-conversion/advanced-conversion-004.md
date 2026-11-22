# ConditionalConverter và điều kiện matches trong Spring Framework

## 1. Khái niệm

Spring có thể có nhiều converter cùng hỗ trợ một cặp kiểu nguồn–đích, nhưng chỉ một converter phù hợp với một field hoặc member cụ thể. Ví dụ hai field đều có kiểu đích ReferenceCode và nhận String; một field có annotation chỉ định quy tắc mã tham chiếu, field kia thì không. Nếu chỉ xét Class, registry không phân biệt được metadata đó.

org.springframework.core.convert.converter.ConditionalConverter bổ sung phương thức:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}
```

matches trả true nếu converter đang xét phù hợp với hai TypeDescriptor; trả false nếu converter cần được bỏ qua. Phương thức này **chỉ chọn converter**, không parse hoặc chuyển đổi source value. Logic chuyển đổi nằm trong convert(...) của Converter, GenericConverter hoặc converter do ConverterFactory cung cấp.

## 2. TypeDescriptor quan trọng ở đâu?

TypeDescriptor giàu thông tin hơn Class<?>. Nó có thể mang:
- Kiểu Java nguồn/đích.
- Generic element, key hoặc value type.
- Annotation của field hoặc method.
- Thông tin member mà descriptor được tạo từ đó.
- Ngữ cảnh array, collection, map và nested type.

Hai field cùng kiểu ReferenceCode có thể có annotation khác nhau. Class chỉ nói chúng có cùng kiểu; TypeDescriptor cho phép matches kiểm tra marker như @ReferenceFormat.

```java
TypeDescriptor source = TypeDescriptor.valueOf(String.class);
TypeDescriptor target =
        TypeDescriptor.field(Invoice.class.getField("referenceCode"));
boolean marked = target.hasAnnotation(ReferenceFormat.class);
```

Đây là snippet reflection; Invoice và ReferenceFormat được định nghĩa trong ví dụ. Annotation cần RetentionPolicy.RUNTIME để đọc được lúc chạy.

## 3. Các SPI liên quan

| SPI | Contract | Khả năng |
| --- | --- | --- |
| Converter<S,T> | T convert(S source) | Một cặp kiểu; có thể triển khai thêm ConditionalConverter |
| GenericConverter | ConvertiblePair + convert với TypeDescriptor | Nhiều cặp kiểu và metadata |
| ConverterFactory<S,R> | Một nguồn sang họ target subtype của R | Nhiều target có chung base type |
| ConditionalGenericConverter | GenericConverter + ConditionalConverter | Khai báo pair và matches cùng lúc |

ConditionalGenericConverter là interface kết hợp:

```java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

Implementation phải khai báo getConvertibleTypes(), matches(...) và convert(...). Registry trước hết tìm theo ConvertiblePair; sau đó matches thu hẹp lựa chọn theo descriptor. Nếu matches=false, Spring có thể tìm converter khác cho cùng cặp kiểu.

## 4. Ví dụ Java 17 / Spring 6.2.6

Ví dụ này chỉ chuyển String thành ReferenceCode khi field đích có annotation @ReferenceFormat. Hai field Invoice.referenceCode và Customer.legacyCode có cùng kiểu Java, nhưng chỉ field thứ nhất mang annotation.

Cấu trúc project:

```text
conditional-converter-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ReferenceFormat.java
    ├── ReferenceCode.java
    ├── Invoice.java
    ├── Customer.java
    ├── StringToReferenceCode.java
    └── ConditionalConverterDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conditional-converter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConditionalConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**ReferenceFormat.java**

```java
package demo;
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface ReferenceFormat { }
```

**ReferenceCode.java**

```java
package demo;
public record ReferenceCode(String value) {
    public ReferenceCode {
        if (value == null || !value.matches("REF-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid reference code");
        }
    }
    @Override public String toString() { return value; }
}
```

**Invoice.java**

```java
package demo;
public class Invoice {
    @ReferenceFormat
    public ReferenceCode referenceCode;
}
```

**Customer.java**

```java
package demo;
public class Customer {
    public ReferenceCode legacyCode;
}
```

**StringToReferenceCode.java**

```java
package demo;

import java.util.Set;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;

public final class StringToReferenceCode
        implements ConditionalGenericConverter {
    private static final ConvertiblePair PAIR =
            new ConvertiblePair(String.class, ReferenceCode.class);

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(PAIR);
    }

    @Override
    public boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType) {
        return targetType.hasAnnotation(ReferenceFormat.class);
    }

    @Override
    public Object convert(Object source, TypeDescriptor sourceType,
                          TypeDescriptor targetType) {
        if (source == null) return null;
        String normalized = source.toString().trim().toUpperCase();
        return new ReferenceCode(normalized);
    }
}
```

**ConditionalConverterDemo.java**

```java
package demo;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.GenericConversionService;

public final class ConditionalConverterDemo {
    public static void main(String[] args) throws Exception {
        GenericConversionService service = new GenericConversionService();
        service.addConverter(new StringToReferenceCode());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor invoiceTarget = TypeDescriptor.field(
                Invoice.class.getField("referenceCode"));
        TypeDescriptor customerTarget = TypeDescriptor.field(
                Customer.class.getField("legacyCode"));

        System.out.println("invoice.matches=" +
                service.canConvert(source, invoiceTarget));
        System.out.println("customer.matches=" +
                service.canConvert(source, customerTarget));

        ReferenceCode code = (ReferenceCode) service.convert(
                " ref-0042 ", source, invoiceTarget);
        System.out.println("invoice.code=" + code);
    }
}
```

Chạy ở thư mục project:

```bash
mvn -q clean compile exec:java
```

Stdout:

```text
invoice.matches=true
customer.matches=false
invoice.code=REF-0042
```

Cả hai field đều có cùng pair String → ReferenceCode, nên đều là ứng viên kiểu. matches chỉ chọn field Invoice vì descriptor có annotation. Customer không có annotation nên converter bị bỏ qua. Lệnh convert thực sự chỉ chạy ở descriptor Invoice.

canConvert(TypeDescriptor, TypeDescriptor) kiểm tra có converter phù hợp theo metadata; nó không thử mọi source value. Nếu gửi BAD-CODE, matches vẫn true nhưng convert/constructor ReferenceCode sẽ từ chối nội dung.

## 5. matches khác convert thế nào?

| matches | convert |
| --- | --- |
| Nhận sourceType và targetType | Nhận source value cùng hai descriptor |
| Quyết định chọn converter | Tạo giá trị đích |
| Kiểm tra annotation/generic/member metadata | Parse, normalize và kiểm tra nội dung |
| Trả boolean | Trả object đích hoặc ném lỗi |

Không parse chuỗi hoặc kiểm tra regex input trong matches vì nó không nhận giá trị nguồn. Nếu dữ liệu không đúng định dạng, xử lý trong convert hoặc validation thích hợp. Khi converter được gọi qua ConversionService, IllegalArgumentException thường được bọc trong ConversionFailedException.

## 6. Điều kiện có thể dựa trên dữ liệu nào?

- **Annotation target:** chỉ chạy khi target field/method có marker.
- **Annotation source:** chỉ chạy với các field nguồn được đánh dấu.
- **Generic type:** phân biệt List<String> với List<ReferenceCode>.
- **Class/method characteristic:** chỉ chạy nếu target class có factory/finder method phù hợp.
- **Cặp kiểu:** getConvertibleTypes khai báo pair sơ bộ; matches kiểm tra metadata cụ thể.

Tài liệu Spring đưa ví dụ converter String → Account chỉ được chọn khi target Account định nghĩa public static finder method như findAccount(String). matches kiểm tra sự hiện diện/khả năng phù hợp của method; việc tạo Account thực tế thuộc convert hoặc service được thiết kế riêng.

## 7. Nhiều converter cùng cặp kiểu

Registry có thể giữ nhiều converter cùng ConvertiblePair. Một converter có matches=false có thể bị bỏ qua để thử converter khác. Vì vậy:

- Thiết kế các điều kiện không chồng lấn ngoài ý muốn.
- Không dựa vào thứ tự đăng ký thay cho điều kiện rõ ràng.
- Kiểm thử converter tổng quát và converter chuyên biệt cùng tồn tại.
- Nếu mọi converter đều không match, không có đường chuyển đổi phù hợp.
- Nếu converter match nhưng value sai, đó là lỗi conversion, không phải lỗi matching.

matches có thể được gọi nhiều lần và từ nhiều request. Hãy giữ nó thuần, nhanh, xác định, không truy vấn DB, gọi mạng, ghi log nhạy cảm hoặc sửa state.

## 8. Khi nào dùng ConditionalConverter?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một cặp kiểu, một luật cố định | Converter<S,T> |
| Converter chỉ chạy khi target có annotation | Converter + ConditionalConverter |
| Nhiều pair hoặc cần descriptor trong convert | GenericConverter |
| Vừa khai báo pair vừa điều kiện hóa | ConditionalGenericConverter |
| Một source sang họ target subtype | ConverterFactory |
| Parse/print có locale | Formatter<T> |

Dùng Converter đơn giản nếu metadata không ảnh hưởng lựa chọn. Chỉ thêm conditional logic khi cùng cặp kiểu thật sự cần quy tắc khác theo annotation, generic hoặc member context.

## 9. Những lỗi phổ biến

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Parse input trong matches | Sai vai trò, không có source value | Parse trong convert |
| Chỉ xét Class khi điều kiện phụ thuộc annotation | Chọn converter cho nhầm field | Xét TypeDescriptor |
| Quên ConvertiblePair | Registry không thấy pair ứng viên | Khai báo đúng source/target |
| Nghĩ matches=true nghĩa value hợp lệ | convert vẫn có thể thất bại | Kiểm tra value trong convert |
| Annotation thiếu RUNTIME | Không đọc được ở runtime | RetentionPolicy.RUNTIME |
| Side effect trong matches | Lookup chậm và khó đoán | Điều kiện thuần |
| Nhiều condition overlap | Kết quả chọn converter khó dự đoán | Thiết kế điều kiện loại trừ, test registry |
| Dùng SPI tổng quát quá sớm | Tăng phức tạp | Ưu tiên Converter khi đủ |
| Dùng matches để phân quyền | Bỏ qua authorization thực | Kiểm tra quyền trong service/domain |

## 10. Kiểm thử

Unit test nên tạo TypeDescriptor từ field có và không có annotation, rồi xác nhận matches true/false. Integration test nên đăng ký converter vào GenericConversionService và gọi canConvert(sourceDescriptor, targetDescriptor), sau đó gọi convert với value hợp lệ và sai.

Các tình huống cần thử:
1. Field có annotation.
2. Field không có annotation.
3. Annotation đặt trên method/parameter.
4. Source descriptor có annotation hoặc generic khác nhau.
5. Generic target với element type phù hợp/không phù hợp.
6. matches=false nhưng có converter khác.
7. matches=true nhưng dữ liệu sai.
8. Nhiều lần gọi và đa luồng để xác nhận không có state/side effect.

Không test matches riêng rồi kết luận registry đã cấu hình đúng; cần test qua ConversionService.

## 11. Spring MVC và Data Binding

Spring MVC dùng ConversionService trong các luồng bind query parameter, path variable và form/model attribute. Khi TypeDescriptor của field/method mang annotation, ConditionalConverter có thể chọn quy tắc tương ứng. Cần integration test với binder thật để xác nhận descriptor MVC cung cấp có đúng metadata mong đợi.

Không đồng nhất @ModelAttribute với @RequestBody JSON. JSON thường đi qua HttpMessageConverter như Jackson và có cơ chế deserialization riêng; converter dành cho MVC không tự thay toàn bộ Jackson mapping.

Ba trách nhiệm cần tách:
- matches chọn converter theo metadata.
- convert biến đổi giá trị cụ thể.
- Validator kiểm tra constraint dữ liệu.
- Service/domain kiểm tra quyền, trạng thái và invariant nghiệp vụ.

## 12. Tự kiểm tra

**1.** matches nhận gì?  
TypeDescriptor nguồn và đích.

**2.** matches true có parse chuỗi không?  
Không; chỉ xác nhận converter phù hợp metadata.

**3.** Vì sao Class không đủ?  
Hai field cùng kiểu có thể có annotation/generic/member metadata khác.

**4.** ConditionalGenericConverter kết hợp interface nào?  
GenericConverter và ConditionalConverter.

**5.** matches=false nghĩa là mọi conversion đều không thể?  
Không; registry có thể tìm converter khác.

**6.** Converter match nhưng value sai thì lỗi ở đâu?  
Trong convert hoặc constructor/value object.

**7.** Vì sao matches nên stateless?  
Lookup có thể gọi nhiều lần, từ nhiều luồng; điều kiện phải ổn định và không side effect.

## 13. Checklist thiết kế

1. Xác định chính xác source/target pair.
2. Chọn metadata quyết định điều kiện: annotation, generic, field, method hoặc class characteristic.
3. Chọn SPI phù hợp, tránh Generic SPI nếu Converter đủ.
4. Viết matches nhanh, xác định, không parse value và không side effect.
5. Để convert kiểm tra nội dung và tạo target type.
6. Test true/false và integration qua GenericConversionService.
7. Kiểm tra converter cạnh tranh cùng pair.
8. Xác nhận TypeDescriptor thực tế do binder cung cấp.
9. Không dùng matches như authorization hoặc validation.
10. Giữ đơn giản nếu không có metadata condition cần thiết.

**Ghi nhớ:** ConditionalConverter bổ sung điều kiện lựa chọn qua matches(TypeDescriptor, TypeDescriptor). Điều kiện dựa trên metadata nguồn/đích; logic chuyển đổi nằm trong convert. ConditionalGenericConverter kết hợp khai báo source/target pair với điều kiện chi tiết, phù hợp khi cùng một cặp kiểu cần các quy tắc khác nhau tùy annotation, generic hoặc đặc điểm field/type.

## 14. Tài liệu chính thức

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): GenericConverter, ConditionalGenericConverter và matching metadata.
- [ConditionalConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html): matches(TypeDescriptor, TypeDescriptor).
- [ConditionalGenericConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html): kết hợp GenericConverter và ConditionalConverter.
- [GenericConverter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html): ConvertiblePair và convert.
- [TypeDescriptor Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): kiểu, annotation và generic metadata.
- [GenericConversionService Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html): đăng ký, lookup và dispatch.
