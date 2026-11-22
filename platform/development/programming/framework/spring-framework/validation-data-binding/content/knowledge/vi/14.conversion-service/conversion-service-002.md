# canConvert và giới hạn khi dự đoán khả năng chuyển đổi trong Spring

## 1. canConvert trả lời câu hỏi gì?

Trong Spring Framework, **ConversionService** cung cấp API thống nhất để chuyển đổi giữa các kiểu Java. Trước khi gọi **convert(...)**, ứng dụng có thể gọi **canConvert(...)** để hỏi liệu service hiện tại có hỗ trợ chuyển từ kiểu nguồn sang kiểu đích hay không.

Ví dụ:

~~~java
ConversionService service = DefaultConversionService.getSharedInstance();
boolean supported = service.canConvert(String.class, Integer.class);
Integer value = service.convert("42", Integer.class);
~~~

Với cấu hình conversion mặc định, Spring có converter từ **String** sang **Integer**. Vì vậy phép kiểm tra theo cặp kiểu trả về **true** và giá trị **"42"** chuyển thành **42**.

Điểm quan trọng: **canConvert dự đoán khả năng theo kiểu và converter đã đăng ký; nó không kiểm tra trước nội dung của một giá trị cụ thể**. Do đó:

- **canConvert(String.class, Integer.class) == true** không có nghĩa mọi chuỗi đều là số nguyên hợp lệ.
- **convert("42", Integer.class)** có thể thành công.
- **convert("forty-two", Integer.class)** vẫn có thể thất bại lúc chạy.

canConvert là phép kiểm tra về **đường chuyển đổi**, không phải bộ xác thực dữ liệu đầu vào, không thay thế xử lý exception, và không chứng minh dữ liệu đáp ứng nghiệp vụ.

## 2. Hai dạng canConvert và vai trò của TypeDescriptor

ConversionService cung cấp hai nhóm overload chính:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
~~~

Các phương thức thực hiện chuyển đổi tương ứng:

~~~java
<T> T convert(Object source, Class<T> targetType);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

### 2.1. Kiểm tra theo Class

**canConvert(Class, Class)** nhìn vào kiểu Java nguồn và đích. Cách này phù hợp với câu hỏi đơn giản:

- Có converter từ String sang Integer không?
- Có thể chuyển LocalDate sang kiểu đích cụ thể không?
- Ứng dụng có hỗ trợ cặp kiểu String sang OrderStatus không?

Overload này không biết field cụ thể, annotation của field, generic type của collection hoặc ngữ cảnh property nơi dữ liệu được chuyển.

### 2.2. Kiểm tra theo TypeDescriptor

**TypeDescriptor** mang nhiều thông tin hơn Class: kiểu khai báo, generic element/key/value type, annotation trên field hoặc method parameter và ngữ cảnh nơi kiểu được khai báo.

Ví dụ hai property đều là String, nhưng một property có annotation định dạng ngày và property còn lại không có. Một converter có thể dùng metadata của descriptor để xử lý khác nhau.

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String.class);
TypeDescriptor target = TypeDescriptor.valueOf(Integer.class);

boolean supported = service.canConvert(source, target);
Object converted = service.convert("42", source, target);
~~~

Overload theo TypeDescriptor thích hợp khi cần chuyển đổi theo **ngữ cảnh property hoặc generic container**. Nó vẫn không biết trước giá trị thực tế có hợp lệ hay không. Descriptor bổ sung ngữ cảnh kiểu; nó không chứa bằng chứng rằng chuỗi "abc" có thể trở thành số nguyên.

## 3. Phân biệt khả năng theo kiểu và khả năng theo giá trị

Hãy xét cùng một cặp String → Integer:

| Giá trị nguồn | canConvert(String, Integer) | convert thực tế | Kết luận |
| --- | --- | --- | --- |
| "42" | true | Thành công, 42 | Giá trị phù hợp converter |
| "0" | true | Thành công, 0 | Chuyển kiểu được; nghiệp vụ có thể vẫn từ chối |
| "-5" | true | Thành công, -5 | Chuyển kiểu được; miền giá trị cần validation |
| "forty-two" | true | Lỗi parse/chuyển đổi | Cặp kiểu được hỗ trợ nhưng giá trị không hợp lệ |
| Chuỗi rỗng | true ở cấp cặp kiểu | Phụ thuộc converter và ngữ cảnh | Không suy ra chính sách empty từ canConvert |

Hai trường hợp 0 và -5 đặc biệt hữu ích: chuyển đổi kỹ thuật có thể thành công, nhưng nếu field là **quantity** thì quy tắc nghiệp vụ có thể yêu cầu số dương. **Conversion và validation trả lời hai câu hỏi khác nhau.**

Một converter tự viết có thể tồn tại cho cặp kiểu nhưng vẫn ném lỗi khi giá trị vi phạm tiền điều kiện. Vì thế canConvert không thực thi trước converter trên mọi giá trị để thử nghiệm nội dung.

## 4. Những giới hạn quan trọng của canConvert

### 4.1. Collection, array và map có thể trả true dù phần tử bên trong lỗi

Đây là giới hạn được tài liệu Javadoc của Spring nêu rõ. Với conversion giữa **Collection**, **Array** và **Map**, canConvert có thể trả về **true** dù convert vẫn phát sinh **ConversionException** nếu phần tử bên trong không chuyển đổi được. Caller phải tự xử lý ngoại lệ này.

Ví dụ từ List<String> sang List<Integer>:

~~~text
["1", "2", "3"]  -> [1, 2, 3]
["1", "x", "3"]  -> lỗi ở phần tử "x"
~~~

Ở cấp container, Spring biết có chiến lược chuyển String sang Integer, vì vậy phép kiểm tra generic container có thể báo hỗ trợ. Nhưng nội dung "x" không thể trở thành số nguyên. Một lần canConvert không duyệt và xác nhận mọi phần tử của collection đầu vào.

Với map, kiểu key và value đều có thể tham gia conversion. Có converter cho key/value không chứng minh từng key/value thực tế đều hợp lệ; conversion có thể lỗi giữa chừng.

### 4.2. Null source và kiểu nguồn không rõ ràng

canConvert(Class, Class) cho phép kiểu nguồn null theo hợp đồng API; targetType vẫn bắt buộc. Trong overload TypeDescriptor, source descriptor cũng có thể null. Null biểu diễn không biết hoặc không có thông tin kiểu nguồn tùy điểm gọi; không suy ra mọi null sẽ tạo ra một giá trị đích không-null hay conversion thành công.

Đặc biệt, giá trị null không giống chuỗi rỗng. Converter, DataBinder, primitive/wrapper và validation có chính sách khác nhau:

- Với wrapper Integer hoặc Boolean, null có thể biểu diễn được.
- Với primitive int hoặc boolean, không thể gán null trực tiếp.
- Binder/editor có thể biến chuỗi rỗng thành null theo cấu hình riêng.
- @NotNull có thể từ chối null khi validation chạy.

**canConvert không xác định hợp đồng empty/null của endpoint.**

### 4.3. canConvert chỉ phản ánh ConversionService hiện tại

Kết quả phụ thuộc converter và formatter đã đăng ký trong đúng service:

- Converter mặc định của DefaultConversionService.
- Converter ứng dụng thêm vào ConverterRegistry.
- ConverterFactory hỗ trợ cả một họ kiểu.
- Converter theo generic type hoặc ngữ cảnh TypeDescriptor.
- Cấu hình định dạng trong môi trường Spring cụ thể.

Nếu converter chưa được đăng ký vào đúng ConversionService, canConvert có thể trả false dù ở module khác của ứng dụng có converter cùng mục đích. Ngược lại, converter đã đăng ký có thể khiến kết quả true nhưng chỉ xử lý được một tập giá trị con.

Đừng dùng kết quả từ một ConversionService độc lập để kết luận cấu hình của WebDataBinder hoặc ApplicationContext khác hoàn toàn giống nhau. Hãy kiểm tra đúng instance ứng dụng thực sự sử dụng.

### 4.4. TypeDescriptor cung cấp metadata, không xác thực toàn bộ dữ liệu

TypeDescriptor hữu ích cho property annotation, generic element type, array component type, map key/value và nested context. Tuy nhiên, metadata đó vẫn là metadata khai báo.

Descriptor của List<Integer> cho biết phần tử đích là Integer. Nó không chứng minh list đầu vào không có "bad", không quá dài, không lặp, hoặc thỏa quy tắc nghiệp vụ.

### 4.5. Converter có thể phụ thuộc giá trị hoặc ngữ cảnh

Một Converter<String, T> có thể kiểm tra cú pháp và ném IllegalArgumentException khi chuỗi không hợp lệ. canConvert(String.class, T.class) vẫn có thể true bởi converter có mặt và nhận kiểu String; convert("invalid", T.class) mới phát hiện giá trị không dùng được.

Conversion cũng có thể thất bại vì:

- Chuỗi số vượt giới hạn kiểu đích.
- Ngày không tồn tại hoặc sai định dạng.
- Enum không có hằng số tương ứng.
- Mã định danh sai checksum.
- Phần tử con trong container không chuyển được.
- Converter kiểm tra trạng thái hoặc dữ liệu miền không hợp lệ.

canConvert không thực thi trước mọi converter trên mọi dữ liệu để thử nghiệm giá trị. Dùng convert thật và xử lý exception là kiểm tra runtime cuối cùng.

## 5. DefaultConversionService và converter tùy chỉnh

**DefaultConversionService** là triển khai có sẵn với nhiều converter phổ biến. **GenericConversionService** là triển khai chung có thể đăng ký converter; nhiều triển khai ConversionService cũng có giao diện ConverterRegistry để thêm hoặc gỡ converter.

Ví dụ:

~~~java
ConversionService service = new DefaultConversionService();

service.canConvert(String.class, Integer.class); // true
service.convert("42", Integer.class);             // 42
~~~

Nếu ứng dụng bổ sung converter cho kiểu miền:

~~~java
public record OrderCode(String value) {}

public final class OrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        if (source == null || !source.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(source);
    }
}
~~~

Đây là trích đoạn cần đặt trong project và import Converter. Khi đăng ký vào registry:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new OrderCodeConverter());
~~~

canConvert(String.class, OrderCode.class) có thể trả true cho cặp kiểu đó. Nhưng "hello" vẫn bị từ chối bởi converter.

Không dùng converter để kiểm tra mọi quy tắc nghiệp vụ. Nếu OrderCode đúng cú pháp nhưng không tồn tại trong hệ thống, đó thuộc bước tra cứu/nghiệp vụ, không phải conversion thuần túy.

## 6. Ví dụ Java 17+ có thể chạy: canConvert true nhưng convert vẫn lỗi

Chương trình sau dùng **Java 17** và **Spring Framework 6.2.15**. Nó minh họa:
1. Cặp String → Integer được hỗ trợ.
2. Giá trị hợp lệ chuyển đổi được.
3. Chuỗi sai định dạng vẫn làm convert thất bại dù canConvert true.
4. List<String> → List<Integer> được nhận diện ở cấp generic container, nhưng phần tử sai làm thao tác conversion lỗi.

Cấu trúc:

~~~text
can-convert-demo/
├── pom.xml
└── src/main/java/demo/CanConvertDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>can-convert-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.15</version>
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
                <configuration>
                    <mainClass>demo.CanConvertDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/CanConvertDemo.java**:

~~~java
package demo;

import java.util.List;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

public final class CanConvertDemo {

    public static void main(String[] args) {
        ConversionService service = new DefaultConversionService();

        System.out.println("STRING_TO_INTEGER="
                + service.canConvert(String.class, Integer.class));

        Integer number = service.convert("42", Integer.class);
        System.out.println("CONVERT_42=" + number);

        try {
            service.convert("forty-two", Integer.class);
            System.out.println("CONVERT_BAD=unexpected-success");
        } catch (ConversionFailedException ex) {
            System.out.println("CONVERT_BAD="
                    + ex.getClass().getSimpleName());
        }

        TypeDescriptor sourceList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(String.class));
        TypeDescriptor targetList = TypeDescriptor.collection(
                List.class, TypeDescriptor.valueOf(Integer.class));

        System.out.println("LIST_CONVERTIBLE="
                + service.canConvert(sourceList, targetList));

        Object converted = service.convert(
                List.of("1", "2", "3"), sourceList, targetList);
        System.out.println("LIST_VALUES=" + converted);

        try {
            service.convert(
                    List.of("1", "x", "3"), sourceList, targetList);
            System.out.println("LIST_BAD=unexpected-success");
        } catch (ConversionFailedException ex) {
            System.out.println("LIST_BAD="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Trong thư mục chứa pom.xml, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả đầu ra dự kiến:

~~~text
STRING_TO_INTEGER=true
CONVERT_42=42
CONVERT_BAD=ConversionFailedException
LIST_CONVERTIBLE=true
LIST_VALUES=[1, 2, 3]
LIST_BAD=ConversionFailedException
~~~

ConversionFailedException là một loại ConversionException. Lỗi của list có thể bao bọc lỗi conversion phần tử. Không phụ thuộc vào toàn bộ thông điệp exception vì nội dung chi tiết có thể gồm giá trị đầu vào và thay đổi theo phiên bản; chương trình chỉ in tên class exception để đầu ra ổn định.

### Điều chương trình chứng minh

- STRING_TO_INTEGER=true xác nhận converter String → Integer tồn tại trong service.
- CONVERT_42=42 chứng minh một giá trị cụ thể chạy được.
- CONVERT_BAD=ConversionFailedException chứng minh giá trị khác có thể thất bại trên cùng cặp kiểu.
- LIST_CONVERTIBLE=true thể hiện Spring nhận diện được đường chuyển đổi theo kiểu container và element type.
- LIST_BAD=ConversionFailedException chứng minh các phần tử vẫn phải được parse ở runtime.

Ví dụ là ứng dụng Java hoàn chỉnh, không phải đoạn trong controller. Khi dùng Spring MVC, cấu hình và exception mapping có thể thay đổi cách lỗi được đưa vào BindingResult hay HTTP response.

## 7. canConvert trong DataBinder và Spring MVC

Trong DataBinder, ConversionService được dùng để chuyển giá trị đầu vào sang kiểu của property hoặc constructor parameter khi cần. Ứng dụng có thể gắn ConversionService vào binder:

~~~java
DataBinder binder = new DataBinder(target, "form");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
~~~

Đây là đoạn cấu hình minh họa; cần target, propertyValues và import phù hợp. canConvert có thể hữu ích để hiển thị khả năng của cấu hình conversion hoặc kiểm tra một cặp kiểu trước workflow. Nhưng khi bind(...) thực hiện thật, giá trị thô vẫn phải chuyển thành công. Nếu không, binder ghi lỗi binding (thường có mã typeMismatch) trong BindingResult.

Với controller dùng @ModelAttribute, Spring MVC thường cấu hình WebDataBinder và xử lý lỗi theo cơ chế binding:

~~~java
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "order-form";
    }
    return "order-success";
}
~~~

Đây là mã tích hợp, cần DTO, view, import và validation provider. BindingResult phải đứng ngay sau model attribute tương ứng. Không dùng canConvert(...) == true để bỏ qua kiểm tra result.hasErrors().

@RequestBody JSON thường được Jackson đọc qua HttpMessageConverter; dữ liệu JSON không chuyển được kiểu có thể gây lỗi deserialize trước khi controller nhận DTO. Không giả định @InitBinder hay canConvert của một service riêng dự báo mọi hành vi serializer JSON.

## 8. Vì sao canConvert không phải validator?

Một validator đánh giá **giá trị đã được chuyển thành kiểu phù hợp** theo điều kiện ứng dụng:

- @Min(1) kiểm tra số lượng.
- @NotNull kiểm tra giá trị không null.
- Validator ngày kiểm tra khoảng thời gian.
- Validator mã đơn hàng có thể kiểm tra trạng thái hoặc quy tắc domain.

ConversionService trả lời: **"Có thể chuyển từ kiểu này sang kiểu kia không?"**. Bean Validation trả lời: **"Giá trị sau khi biểu diễn có thỏa các ràng buộc không?"**. Tầng nghiệp vụ tiếp tục trả lời: **"Giá trị này có hợp lệ trong trạng thái hệ thống hiện tại không?"**

Ví dụ "-5" chuyển được sang Integer; converter không nhất thiết biết quantity phải dương. Nếu domain yêu cầu quantity từ 1 trở lên, validation hoặc logic domain phải từ chối.

~~~text
Dữ liệu thô
   |
   v
Conversion (kiểu Java)
   | thất bại -> binding/conversion error
   v
Bean Validation
   | thất bại -> constraint violation
   v
Business rules
   | thất bại -> domain/business error
   v
Tiếp tục xử lý
~~~

Không gộp ba giai đoạn thành một boolean canConvert, và không trả lỗi "không hỗ trợ kiểu" khi thực tế là chuỗi nhập sai.

## 9. Cách dùng canConvert an toàn trong code ứng dụng

Một mẫu sử dụng có kiểm soát:

~~~java
if (!service.canConvert(sourceType, targetType)) {
    throw new IllegalArgumentException("Conversion pair is not supported");
}

try {
    Object value = service.convert(sourceValue, sourceDescriptor, targetDescriptor);
    // Tiếp tục validation trên giá trị đã chuyển thành kiểu đích.
} catch (ConversionException ex) {
    // Xử lý giá trị thực tế không chuyển đổi được.
}
~~~

Đây là pseudocode minh họa, cần biến và descriptor thật. Trước khi gọi convert, hãy hỏi:

1. Đây có đúng ConversionService ứng dụng sẽ dùng lúc thực thi không?
2. Kiểm tra bằng Class có đủ hay cần TypeDescriptor để giữ generic type/annotation context?
3. Giá trị thực tế có thể sai cú pháp, null, rỗng, vượt giới hạn hoặc có phần tử con lỗi không?
4. Nếu convert ném ConversionException, nó được biến thành lỗi field hay lỗi API như thế nào?
5. Sau khi chuyển đổi thành công, có cần Bean Validation hoặc business validation không?

Không nên convert thử nhiều giá trị tùy ý chỉ để suy ra converter có hỗ trợ. canConvert là cách kiểm tra route theo kiểu; convert mới là thao tác thực tế. Nếu xác thực hàng loạt dữ liệu, hãy chạy conversion có giới hạn và thu thập kết quả từng phần tử, kèm chính sách lỗi phù hợp.

### Đăng ký converter và ảnh hưởng tới kết quả

Ví dụ converter tự viết:

~~~java
public record OrderCode(String value) {}

public final class OrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        if (source == null || !source.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(source);
    }
}
~~~

Đây là trích đoạn cần đặt trong project và import Converter. Khi đăng ký:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new OrderCodeConverter());
~~~

Có thể kiểm tra:

~~~java
service.canConvert(String.class, OrderCode.class); // true
service.convert("ORD-123456", OrderCode.class);    // thành công
service.convert("ORD-12", OrderCode.class);        // thất bại
~~~

Cặp kiểu có converter không đồng nghĩa mọi chuỗi đều đúng cú pháp. Nếu việc kiểm tra mã còn cần tra database, không nên nhét tác vụ IO vào converter; hãy phân chia conversion và nghiệp vụ lookup.

## 10. Lỗi thường gặp

1. **"canConvert true nghĩa là chuỗi sẽ chuyển được".** Sai: nó kiểm tra kiểu, không xác nhận nội dung.
2. **"canConvert false nghĩa là hệ thống không thể làm điều đó ở bất kỳ đâu".** Chỉ phản ánh service và registry hiện tại; service khác hoặc converter chưa đăng ký có thể thay đổi kết quả.
3. **"List<String> sang List<Integer> canConvert true thì mọi phần tử hợp lệ".** Sai: phần tử sai vẫn làm convert thất bại.
4. **"TypeDescriptor sẽ kiểm tra dữ liệu thực".** Sai: nó mang metadata kiểu/generic/annotation, không duyệt và xác nhận raw value.
5. **"canConvert là Bean Validation".** Sai: validation đánh giá ràng buộc trên giá trị sau chuyển đổi.
6. **"canConvert true nghĩa là null và chuỗi rỗng đều được chấp nhận".** Sai: cần hiểu riêng semantics null, empty, primitive/wrapper và converter.
7. **"Một service tự tạo có kết quả giống Spring MVC".** Không nhất thiết: binder/web config có thể đăng ký converter hoặc formatter riêng.
8. **"Nếu canConvert false thì cứ thử convert để xem".** Không phù hợp cho flow cần dự đoán an toàn; convert thực tế có thể ném exception. Hãy cấu hình đúng service và xử lý unsupported pair rõ ràng.
9. **"Chuyển kiểu thành công là dữ liệu hợp lệ".** Sai: -5 có thể là Integer nhưng quantity không được âm.
10. **"Bắt RuntimeException rộng là đủ".** Nên bắt exception conversion phù hợp ở đúng ranh giới, giữ nguyên nguyên nhân, tránh che lỗi lập trình hoặc lỗi hệ thống khác.

## 11. Bài tập thực hành

**Bài tập 1 — Giá trị String → Integer.** Chạy ví dụ với "7", "0", "-1", "007" và "7x". Ghi riêng canConvert và kết quả convert. Với quantity, thêm quy tắc miền yêu cầu số dương.

**Bài tập 2 — Collection conversion.** Thay List.of("1", "2", "3") bằng List.of("1", "bad", "3"). Xác nhận canConvert vẫn mô tả kiểu container và lỗi chỉ xuất hiện khi convert từng phần tử.

**Bài tập 3 — Converter tùy chỉnh.** Đăng ký converter String → OrderCode, gọi canConvert rồi thử "ORD-123456", "ORD-12" và "abc". Phân biệt cặp kiểu có converter với giá trị pass regex.

**Bài tập 4 — Class và TypeDescriptor.** Dùng hai overload canConvert cho String/Integer và descriptor tương ứng. Nêu thông tin nào TypeDescriptor giữ mà Class không giữ.

**Bài tập 5 — DataBinder.** Tạo DTO có Integer quantity, bind "abc" bằng DataBinder đã cấu hình ConversionService. Xem BindingResult.getFieldErrors("quantity"), mã lỗi và isBindingFailure(). Sau đó bind "0" và xác nhận conversion có thể thành công trước khi validation từ chối giá trị.

## 12. Tài liệu chính thức

- [ConversionService Javadoc – Spring Framework](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html): hợp đồng canConvert, convert, overload Class/TypeDescriptor và lưu ý collection, array, map.
- [Spring Type Conversion Reference](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService API, ConverterRegistry và cấu hình chuyển đổi.
- [GenericConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html): triển khai chung và quản lý converter.
- [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): mô tả kiểu, generic, annotation và context của source/target.
- [DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): gắn ConversionService và thu thập BindingResult.
- [Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding dữ liệu vào model attribute.

**Nguyên tắc cần nhớ:** canConvert trả lời câu hỏi "ConversionService này có đường chuyển đổi cho cặp kiểu nguồn/đích không?". Nó không bảo đảm mọi giá trị nguồn đều hợp lệ, đặc biệt với collection/array/map và converter kiểm tra nội dung. Hãy thực hiện convert trong ranh giới xử lý lỗi rõ ràng, rồi chạy validation và business rules riêng.