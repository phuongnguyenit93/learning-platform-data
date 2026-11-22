# ConditionalGenericConverter khi cần kết hợp hai cơ chế trong Spring

Trong Spring Core, có những converter cần đồng thời hai khả năng: **mô tả nhiều cặp kiểu nguồn/đích và nhận metadata kiểu đầy đủ**, đồng thời **chỉ áp dụng khi điều kiện của kiểu hoặc property được thỏa mãn**. Interface **ConditionalGenericConverter** giải quyết trường hợp này bằng cách kết hợp **GenericConverter** với **ConditionalConverter**.

- **GenericConverter** khai báo những cặp kiểu có thể chuyển đổi và nhận **TypeDescriptor** của nguồn/đích khi thực hiện.
- **ConditionalConverter** bổ sung phương thức **matches(sourceType, targetType)** để quyết định converter có phù hợp với descriptor cụ thể hay không.
- **ConditionalGenericConverter** kế thừa cả hai: Spring biết converter xử lý cặp class nào, đồng thời hỏi điều kiện dựa trên metadata trước khi chọn converter.

Ví dụ, ứng dụng có kiểu **Code**, nhưng chỉ muốn chuẩn hóa chuỗi thành slug khi property đích mang annotation **@Slugged**. Hai field cùng có kiểu Java **Code**, song converter chỉ áp dụng cho field có annotation. Đây là lý do cần kết hợp khả năng mô tả cặp kiểu với cơ chế lựa chọn có điều kiện.

## 1. Khi nào cần kết hợp hai cơ chế?

Một **Converter<S, T>** thông thường diễn tả một cặp kiểu rõ ràng, chẳng hạn **String → Code**. Đây là lựa chọn tốt khi một quy tắc áp dụng nhất quán cho mọi property có cặp kiểu đó.

Nhưng trong hệ thống lớn, cùng một cặp kiểu có thể mang nhiều ngữ nghĩa:

- Một field Code cần chuyển chuỗi thành mã slug viết thường.
- Một field Code khác cần giữ nguyên mã do hệ thống ngoài cấp.
- Một property collection cần xử lý theo generic element type hoặc metadata của phần tử.
- Một cặp kiểu chỉ được chuyển khi descriptor có annotation hoặc context nhất định.

Chỉ nhìn **String.class → Code.class** có thể chưa đủ để chọn đúng logic. **TypeDescriptor** mô tả thêm ngữ cảnh; **matches(...)** kiểm tra converter có áp dụng trong ngữ cảnh đó không.

| Interface | Mô tả cặp kiểu | Nhận TypeDescriptor khi convert | Điều kiện matches |
| --- | --- | --- | --- |
| **Converter<S,T>** | Một cặp generic rõ ràng | Không trong chữ ký convert thông thường | Không |
| **GenericConverter** | Một tập ConvertiblePair | Có source/target TypeDescriptor | Không bắt buộc |
| **ConditionalConverter** | Không tự định nghĩa phép convert và cặp kiểu | matches nhận hai descriptor | Có |
| **ConditionalGenericConverter** | Một tập ConvertiblePair | Có qua GenericConverter | Có qua ConditionalConverter |

Hai interface nhỏ có nhiệm vụ khác nhau. Interface kết hợp chỉ hữu ích khi converter thực sự cần cả hai.

## 2. Hợp đồng API của ba interface

Các interface nằm trong package **org.springframework.core.convert.converter**.

### GenericConverter

Hợp đồng rút gọn:

~~~java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

**getConvertibleTypes()** khai báo tập cặp kiểu mà converter có thể xử lý. Mỗi **ConvertiblePair** gồm một class nguồn và một class đích. **convert(...)** nhận giá trị thực cùng descriptor chi tiết để chuyển đổi.

### ConditionalConverter

Hợp đồng điều kiện:

~~~java
public interface ConditionalConverter {
    boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

**matches(...)** trả true nếu converter phù hợp với cặp descriptor đang xét; trả false nếu không.

### ConditionalGenericConverter

Interface kết hợp về bản chất được khai báo:

~~~java
public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
~~~

Nó không thêm phương thức bắt buộc mới ngoài những phương thức kế thừa. Class triển khai cần cung cấp **getConvertibleTypes()**, **convert(...)** và **matches(...)**.

Cần phân biệt hai câu hỏi:

1. **getConvertibleTypes()** trả lời: converter này có thể xử lý những cặp class nào?
2. **matches(...)** trả lời: với cặp TypeDescriptor cụ thể hiện tại, converter có được áp dụng không?

Không đưa mọi điều kiện metadata vào khai báo cặp class. Ngược lại, cũng không dùng matches chỉ để lặp lại những điều mà cặp kiểu đã xác định.

## 3. TypeDescriptor làm cho condition có ý nghĩa

**TypeDescriptor** cung cấp thông tin phong phú hơn **Class<?>**:

- Kiểu object sau khi xử lý primitive/wrapper.
- Annotation gắn trên field hoặc method parameter.
- Component type của array.
- Element type của collection.
- Key/value type của map.
- Generic metadata lấy từ khai báo property hoặc parameter.

Một ConvertiblePair(String.class, Code.class) chỉ mô tả kiểu lớp. Nếu hai property đều có kiểu Code, cặp này không phân biệt được property nào có annotation @Slugged.

Khi Spring truyền target descriptor vào **matches(...)**, converter có thể kiểm tra:

~~~java
boolean slugged = targetType.hasAnnotation(Slugged.class);
~~~

Đoạn minh họa đúng khi Slugged là runtime annotation được gắn trên phần tử mà descriptor mô tả.

Trong code thủ công, tạo descriptor từ field bằng reflection:

~~~java
TypeDescriptor targetDescriptor =
        new TypeDescriptor(ArticleForm.class.getDeclaredField("slugCode"));
~~~

Nhờ vậy, cùng class Code có thể có chính sách chuyển đổi khác nhau theo từng property.

### Generic element metadata

Với field:

~~~java
private List<Code> codes;
~~~

TypeDescriptor tạo từ field giữ được generic element type Code. Trong conversion của collection, Spring dùng descriptor phần tử khi xét converter cho từng item. Nếu condition phụ thuộc generic type, có thể xem **sourceType.getElementTypeDescriptor()** hoặc **targetType.getElementTypeDescriptor()** khi có.

Descriptor phần tử có thể null nếu kiểu khai báo không cung cấp đủ metadata hoặc không phải collection. Hãy kiểm tra null trước khi đọc element type. Với map, có API mô tả key/value; với array, có component type descriptor tương ứng.

**TypeDescriptor.valueOf(Code.class)** chỉ mô tả class Code, không mang annotation của một field cụ thể. Nếu điều kiện phụ thuộc annotation trên property, hãy lấy descriptor từ field/property context.

## 4. Spring chọn converter như thế nào?

Một ConversionService như **GenericConversionService** hoặc **DefaultConversionService** quản lý converter đã đăng ký. Khi gọi **canConvert(...)** hoặc **convert(...)**, registry tìm đường chuyển đổi theo kiểu nguồn/đích và điều kiện của converter.

~~~text
canConvert(sourceType, targetType) hoặc convert(...)
                |
                v
Tìm converter có ConvertiblePair tương thích
                |
                v
Nếu là converter có điều kiện:
matches(sourceDescriptor, targetDescriptor)?
          | true                  | false
          v                       v
Giữ làm ứng viên             Bỏ qua ứng viên này
          |
          v
Chọn converter phù hợp theo registry/specificity
          |
          v
convert(source, sourceDescriptor, targetDescriptor)
~~~

Đây là mô hình khái niệm, không cam kết thứ tự gọi matches cố định cho mọi implementation. Registry có thể cache kết quả tìm converter; điều người viết converter cần bảo đảm là **matches(...) không có side effect và có kết quả ổn định theo descriptor**.

Lưu ý:

1. matches có thể được đánh giá khi kiểm tra khả năng chuyển đổi, không chỉ lúc convert chạy. Nó phải nhanh và thuần.
2. canConvert true chỉ cho biết Spring tìm được converter theo metadata hiện tại; dữ liệu cụ thể vẫn có thể bị từ chối trong convert.
3. matches false loại converter này khỏi context đang xét; converter khác vẫn có thể xử lý nếu registry có đường thay thế.
4. Nếu nhiều converter cùng phù hợp, việc chọn còn phụ thuộc cặp kiểu và registry. Tránh các điều kiện chồng lấn mà cho kết quả khác nhau.
5. Không giả định converter tùy chỉnh sẽ luôn thắng converter built-in. Test trên đúng descriptor của property.

## 5. Ví dụ hoàn chỉnh Java 17: chỉ chuyển Code khi field có @Slugged

Ví dụ dùng **Spring Framework 6.2.10**, JDK 17+ và Maven; không cần Spring Boot hoặc web server. Một ConditionalGenericConverter xử lý String → Code, nhưng chỉ áp dụng nếu field đích có annotation **@Slugged**.

Hai field cùng có kiểu Code:

- **slugCode** mang @Slugged, nên chuỗi được trim, chuyển chữ thường và thay khoảng trắng bằng dấu gạch ngang.
- **externalCode** không có annotation, nên converter này từ chối tham gia.

Cấu trúc:

~~~text
conditional-generic-converter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConditionalGenericConverterDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conditional-generic-converter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ConditionalGenericConverterDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.ConditionalGenericConverter;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConditionalGenericConverterDemo {

    public static void main(String[] args) throws NoSuchFieldException {
        DefaultConversionService service = new DefaultConversionService();
        service.addConverter(new SlugCodeConverter());

        TypeDescriptor source = TypeDescriptor.valueOf(String.class);
        TypeDescriptor slugTarget =
                new TypeDescriptor(ArticleForm.class.getDeclaredField("slugCode"));
        TypeDescriptor plainTarget =
                new TypeDescriptor(ArticleForm.class.getDeclaredField("externalCode"));

        System.out.println("sluggedCanConvert = "
                + service.canConvert(source, slugTarget));
        System.out.println("plainCanConvert = "
                + service.canConvert(source, plainTarget));

        Code converted = (Code) service.convert(
                "  Spring Conversion Rules  ", source, slugTarget);

        System.out.println("converted = " + converted.value());
        System.out.println("targetHasSlugged = "
                + slugTarget.hasAnnotation(Slugged.class));
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface Slugged {
    }

    public record Code(String value) {
    }

    public static final class ArticleForm {
        @Slugged
        private Code slugCode;

        private Code externalCode;

        public Code getSlugCode() {
            return slugCode;
        }

        public void setSlugCode(Code slugCode) {
            this.slugCode = slugCode;
        }

        public Code getExternalCode() {
            return externalCode;
        }

        public void setExternalCode(Code externalCode) {
            this.externalCode = externalCode;
        }
    }

    public static final class SlugCodeConverter
            implements ConditionalGenericConverter {

        @Override
        public Set<GenericConverter.ConvertiblePair> getConvertibleTypes() {
            return Set.of(new GenericConverter.ConvertiblePair(
                    String.class, Code.class));
        }

        @Override
        public boolean matches(
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            return sourceType.getObjectType() == String.class
                    && targetType.getObjectType() == Code.class
                    && targetType.hasAnnotation(Slugged.class);
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            if (source == null) {
                return null;
            }

            String normalized = source.toString()
                    .trim()
                    .toLowerCase(Locale.ROOT)
                    .replaceAll("\\s+", "-");

            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Slug must not be blank");
            }

            return new Code(normalized);
        }
    }
}
~~~

Trong thư mục chứa pom.xml, chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConditionalGenericConverterDemo
~~~

**Stdout của chương trình**:

~~~text
sluggedCanConvert = true
plainCanConvert = false
converted = spring-conversion-rules
targetHasSlugged = true
~~~

Giải thích:

- **getConvertibleTypes()** khai báo cặp String → Code. Đây là phạm vi class-level converter có thể xử lý.
- **matches(...)** kiểm tra source type, target type và annotation @Slugged trên target descriptor. Cặp class đúng nhưng target không có annotation thì bị từ chối.
- **convert(...)** chuẩn hóa giá trị cụ thể sau khi registry chọn converter.
- **DefaultConversionService.addConverter(...)** nhận GenericConverter; do class cũng là ConditionalGenericConverter, registry có thể kiểm tra điều kiện.
- TypeDescriptor tạo từ field thật nên giữ annotation runtime. Nếu chỉ dùng **TypeDescriptor.valueOf(Code.class)**, metadata field bị mất và matches trả false.
- **canConvert(...)** chạy trước phép chuyển đổi; với plain field, converter này không khớp và không có converter thay thế cho String → Code, nên kết quả false.

Ví dụ tập trung vào lựa chọn converter theo metadata field; nó chưa tạo DataBinder hoặc HTTP request. Phần tiếp theo trình bày cách áp dụng cùng nguyên tắc vào property binding.

## 6. Tích hợp với DataBinder và Spring MVC

Trong ứng dụng thật, metadata annotation thường nằm trên property của DTO. Khi DataBinder xử lý property, Spring có thể cung cấp TypeDescriptor tương ứng cho converter. Nếu converter xét annotation, cần bảo đảm annotation được đặt tại vị trí descriptor đích biểu diễn.

Ví dụ DataBinder thủ công:

~~~java
ArticleForm form = new ArticleForm();

DefaultConversionService conversions = new DefaultConversionService();
conversions.addConverter(new SlugCodeConverter());

DataBinder binder = new DataBinder(form, "articleForm");
binder.setConversionService(conversions);
binder.setAllowedFields("slugCode");
binder.bind(new MutablePropertyValues(Map.of(
        "slugCode", " Spring Conversion Rules "
)));

BindingResult result = binder.getBindingResult();
if (!result.hasErrors()) {
    System.out.println(form.getSlugCode().value());
}
~~~

Đây là đoạn minh họa dùng các class ở ví dụ trên; cần import DataBinder, MutablePropertyValues, BindingResult và Map. Property slugCode phải là JavaBean writable property. Annotation được đặt trên field để TypeDescriptor phản ánh. Nếu annotation đặt trên getter/setter hoặc record component, hãy xác nhận nơi Spring introspection lấy metadata.

Trong Spring MVC có thể đăng ký converter với **WebMvcConfigurer.addFormatters(...)**:

~~~java
@Configuration
class ConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new ConditionalGenericConverterDemo.SlugCodeConverter());
    }
}
~~~

Đây là đoạn minh họa trong ứng dụng MVC; cần dependency spring-webmvc, annotation @Configuration, FormatterRegistry và WebMvcConfigurer. Đăng ký trong registry MVC giúp binder thuộc phạm vi MVC sử dụng converter; không tạo một ConversionService độc lập cho từng controller.

Các ranh giới quan trọng:

- **@ModelAttribute form:** DataBinder thực hiện property binding và dùng ConversionService/TypeDescriptor để chuyển kiểu.
- **@RequestBody JSON:** Jackson thường deserialize body. Không mặc nhiên giả định custom Spring ConversionService converter tự chạy cho field JSON; nếu cần, cấu hình Jackson deserializer/module phù hợp.
- **@Valid:** Bean Validation là cơ chế khác; converter không thay thế validation.
- Không truy vấn database, kiểm tra quyền hoặc ghi dữ liệu trong matches/convert.
- Converter được dùng chung có thể chạy đồng thời; giữ implementation stateless và thread-safe.

## 7. Kết hợp điều kiện với generic element metadata

Có ứng dụng cần chuyển **List<String> → List<Code>**, nhưng chỉ khi descriptor phần tử đích có metadata phù hợp. Khi Spring chuyển collection, converter cấu trúc xử lý container ngoài; converter phần tử được xét với TypeDescriptor của từng item.

~~~text
List<String>
    |
    v
CollectionToCollectionConverter
    |
    +-- String[0] -> Code
    +-- String[1] -> Code
    +-- String[2] -> Code
    |
    v
List<Code>
~~~

Một ConditionalGenericConverter có thể khai báo ConvertiblePair(String.class, Code.class) và dùng matches(sourceElementDescriptor, targetElementDescriptor) để kiểm tra element context. Tuy nhiên, điều kiện dựa trên annotation của **container field** và annotation trên **element type** là hai ngữ cảnh khác nhau. Đừng giả định annotation đặt trên field List<Code> luôn xuất hiện trên descriptor của từng phần tử.

Nếu logic nằm trên annotation của container field, converter element có thể không nhìn thấy nó trực tiếp qua element descriptor. Một phương án rõ hơn là annotation gắn trên element type hoặc custom converter ở cấp container có thể đọc metadata field đầy đủ. Chọn theo vị trí metadata và độ phức tạp của quy tắc.

Khi condition cần tham chiếu element type, dùng API descriptor tương ứng:

~~~java
TypeDescriptor element = targetType.getElementTypeDescriptor();
if (element == null) {
    return false;
}
return element.getObjectType() == Code.class;
~~~

Đoạn minh họa cần đặt trong matches(...) phù hợp; bổ sung kiểm tra annotation trên element nếu đó là ngữ nghĩa mong muốn. Phải xử lý null descriptor vì không phải source/target nào cũng là collection.

## 8. Thiết kế matches(...) đúng cách

**matches(...) là phép quyết định converter có được chọn hay không.** Giữ phương thức này nhỏ, xác định, chỉ dựa trên metadata nguồn/đích được truyền vào.

Nên:

- Kiểm tra source/target object type tương thích với cặp kiểu đã khai báo.
- Kiểm tra annotation bằng **hasAnnotation(...)** hoặc metadata trong TypeDescriptor.
- Kiểm tra collection element/key/value descriptor chỉ khi chắc chắn descriptor không null.
- Trả false khi metadata thiếu hoặc không thỏa điều kiện, trừ khi hợp đồng có fallback rõ ràng.
- Giữ kết quả ổn định: cùng cặp descriptor không nên phụ thuộc thời gian, session hoặc trạng thái database.

Không nên:

- Truy vấn database để quyết định converter áp dụng hay không.
- Thay đổi source/target object trong matches.
- Ghi log nhạy cảm hoặc thực hiện side effect nặng.
- Dùng matches để báo lỗi dữ liệu cụ thể. Condition chỉ chọn converter; lỗi giá trị thuộc convert hoặc tầng validation.
- Viết condition luôn true chỉ để triển khai interface; khi không cần điều kiện, dùng GenericConverter hoặc Converter<S,T> đơn giản.

### convert(...) vẫn phải kiểm tra giá trị

matches không thay thế xác thực input. Converter vẫn phải xử lý:

- Null handling theo hợp đồng kiểu đích và ConversionService.
- Blank/whitespace theo quy tắc dữ liệu.
- Ký tự không hợp lệ, độ dài và định dạng.
- Exception rõ ràng nếu nguồn không thể chuyển thành giá trị đích.

Ví dụ matches chấp nhận field có @Slugged, nhưng source là "###"; converter vẫn phải từ chối nếu cú pháp slug không cho ký tự đó. Condition chọn converter nào tham gia; convert quyết định giá trị cụ thể có chuyển được hay không.

## 9. Registration, converter chồng lấn và cache

Một ConversionService có thể đăng ký nhiều converter, bao gồm converter conditional và unconditional. Khi nhiều converter cùng khai báo cặp kiểu tương thích, registry phải tìm converter phù hợp. Điều kiện hẹp có thể loại một converter khỏi context nhưng không đảm bảo nó luôn thắng converter khác có cùng pair.

Nguyên tắc thiết kế:

1. Tránh đăng ký nhiều converter có cùng ConvertiblePair và điều kiện chồng lấn nếu kết quả khác nhau.
2. Viết matches cụ thể và dễ kiểm thử.
3. Xem xét converter mặc định của Spring; không giả định custom converter thay thế mọi built-in.
4. Dùng **canConvert(sourceDescriptor, targetDescriptor)** trong test để xác nhận metadata chọn đúng đường.
5. Gọi **convert(...)** thực tế để xác nhận converter chạy đúng và lỗi được báo phù hợp.
6. Hoàn tất registration lúc khởi tạo ứng dụng, trước khi ConversionService dùng chung.

Nếu không có converter khớp, canConvert có thể trả false hoặc convert phát sinh lỗi chuyển đổi. Nếu nhiều đường chuyển đổi tồn tại, Spring có thuật toán tìm converter và có thể cache kết quả theo cặp descriptor. Do đó, không thay đổi kết quả matches theo trạng thái mutable ngoài descriptor.

## 10. Hiểu lầm và lỗi thường gặp

**Nhầm ConditionalGenericConverter với ConditionalConverter.** ConditionalConverter chỉ cung cấp matches; nó không tự định nghĩa getConvertibleTypes và convert. ConditionalGenericConverter kế thừa cả GenericConverter và ConditionalConverter.

**Nhầm ConvertiblePair với TypeDescriptor.** Pair là cặp class dùng khai báo phạm vi converter; descriptor mang thêm annotation và generic element metadata.

**Dùng target class để kiểm tra annotation field.** TypeDescriptor.valueOf(Code.class) không mang annotation của field cụ thể. Lấy descriptor từ field/property context nếu condition phụ thuộc metadata field.

**matches phụ thuộc dữ liệu request hoặc database.** Điều này khiến lựa chọn converter khó dự đoán và có thể chạy nhiều lần. Condition nên chỉ dựa trên metadata.

**Dùng convert để kiểm tra converter có áp dụng không.** Dùng matches cho lựa chọn; convert cho phép chuyển giá trị.

**Không xử lý element descriptor null.** Nguồn/đích không phải collection hoặc raw generic có thể không có element descriptor. Trả false hoặc xử lý có chủ đích thay vì gây NullPointerException.

**Đặt annotation sai vị trí.** Annotation trên field container không đồng nghĩa annotation trên element type. Xác định điều kiện áp dụng cho container hay phần tử rồi test descriptor nhận được.

**CanConvert true nhưng convert vẫn lỗi.** Bình thường khi source value cụ thể không đáp ứng cú pháp. CanConvert kiểm tra đường chuyển đổi theo metadata, không kiểm tra nội dung của mọi giá trị.

**Bỏ qua converter built-in hoặc cặp kiểu trùng.** Nhiều converter có thể cạnh tranh; test đúng cặp descriptor và tránh dựa vào thứ tự đăng ký một cách tùy tiện.

**Dùng converter để kiểm tra nghiệp vụ.** Chuẩn hóa slug không chứng minh slug chưa được dùng, user có quyền tạo hay entity tồn tại. Những kiểm tra đó thuộc service/domain/database.

## 11. Kiểm thử và chọn interface phù hợp

| Ca kiểm thử | Source descriptor | Target descriptor | Kết quả mong đợi |
| --- | --- | --- | --- |
| Field có annotation | String | Code field có @Slugged | matches true, canConvert true |
| Field không annotation | String | Code field không annotation | matches false, canConvert false nếu không có converter khác |
| Metadata đúng, input hợp lệ | String có whitespace | Code @Slugged | Convert thành slug chuẩn hóa |
| Metadata đúng, input rỗng | String rỗng | Code @Slugged | convert ném lỗi theo hợp đồng |
| Sai source type | Integer | Code @Slugged | Không khớp ConvertiblePair |
| Annotation khác | String | Code field có annotation khác | matches false |
| Descriptor thiếu metadata | String | Code không có annotation | Condition trả false rõ ràng |
| Converter cạnh tranh | Cùng source/target pair | Descriptor khác context | Registry chọn đường mong muốn |
| DataBinder | Property Code có @Slugged | String property input | BindingResult và target đúng |
| MVC form | @ModelAttribute có field annotation | Form parameter | Converter trong MVC registry được sử dụng |

Dùng unit test cho matches(...) với TypeDescriptor tự tạo và test ConversionService cho cả canConvert lẫn convert. Dùng MockMvc riêng để xác nhận registration và metadata thực tế từ property binding; không kết luận từ test direct ConversionService rằng MVC/Jackson chắc chắn dùng cùng registry.

### Chọn interface

| Nhu cầu | Nên chọn |
| --- | --- |
| Một cặp kiểu đơn giản, luôn áp dụng | **Converter<S,T>** |
| Nhiều cặp kiểu và cần TypeDescriptor khi convert | **GenericConverter** |
| Chỉ cần điều kiện áp dụng cho converter | **ConditionalConverter** kết hợp với converter phù hợp |
| Nhiều cặp kiểu và condition theo descriptor | **ConditionalGenericConverter** |
| Một kiểu nguồn sang họ kiểu đích chung gốc | **ConverterFactory<S,R>** |
| Parse/print phụ thuộc locale | **Formatter<T>** |

Không chọn interface phức tạp hơn chỉ vì có thể. Dùng **ConditionalGenericConverter** khi thật sự cần cả phạm vi nhiều pair/TypeDescriptor của GenericConverter và điều kiện lựa chọn của ConditionalConverter.

## Tài liệu chính thức

- [Spring Framework — ConditionalGenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [Spring Framework — ConditionalConverter API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [Spring Framework — TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Spring Framework — GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework — Type Conversion reference](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
