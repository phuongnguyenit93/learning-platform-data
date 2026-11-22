# Xử lý nguồn không null theo hợp đồng Converter trong Spring Framework

## 1. Vấn đề cần hiểu

Trong Spring Framework, `org.springframework.core.convert.converter.Converter<S, T>` biểu diễn phép biến đổi **một giá trị nguồn kiểu S** thành **một giá trị đích kiểu T**. Điểm cốt lõi của hợp đồng: **mỗi lần Spring gọi `Converter.convert(S source)`, đối số `source` được bảo đảm khác `null`**. Vì thế, một converter được đăng ký và được gọi đúng qua hạ tầng chuyển đổi của Spring có thể tập trung xử lý giá trị nguồn hợp lệ về mặt hiện diện, thay vì tự viết nhánh `if (source == null)` ở đầu phương thức.

Tuy nhiên, hãy phân biệt ba khái niệm:

1. **Nguồn không null**: `source` là một đối tượng đang tồn tại; đây là bảo đảm của hợp đồng `Converter`.
2. **Giá trị nguồn hợp lệ**: nội dung của đối tượng phải đáp ứng quy tắc của phép chuyển đổi; chuỗi rỗng, chuỗi chỉ có khoảng trắng hoặc mã sai định dạng đều **không null nhưng có thể không hợp lệ**.
3. **Kết quả không null**: hợp đồng `Converter` **không** bảo đảm điều này; API cho phép `convert` trả `null` khi phép chuyển đổi được thiết kế như vậy.

Ví dụ: `"12"`, `""` và `"abc"` là ba nguồn `String` không null. Converter chuyển chuỗi thành số có thể chuyển `"12"` thành `12`; với `""` hoặc `"abc"`, nó phải áp dụng chính sách nghiệp vụ đã định (chẳng hạn báo lỗi hoặc cho kết quả null). Việc nguồn không null tự nó không làm nội dung đúng.

## 2. Hợp đồng ở đúng lớp API

~~~java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Đây là hình thức rút gọn để minh họa phương thức quan trọng; khai báo thực tế trong Spring còn có annotation nullability và phương thức mặc định `andThen`. Từ Javadoc của `convert`:

- `source` phải là một thể hiện của kiểu `S` và **không được null**.
- Giá trị trả về là thể hiện của kiểu `T` và **có thể null**.
- Khi không thể chuyển đổi nguồn sang đích, converter nên ném `IllegalArgumentException` để biểu thị nguồn không hợp lệ.
- Converter nên **thread-safe** vì có thể được tái sử dụng và gọi từ nhiều luồng.

Dấu phân biệt quan trọng:

| Cách gọi | Nguồn null có thể truyền vào? | Ai chịu trách nhiệm xử lý? |
| --- | --- | --- |
| `converter.convert(source)` gọi trực tiếp | Không theo hợp đồng `Converter` | Người gọi phải bảo đảm `source != null`. |
| `conversionService.convert(source, Target.class)` | Có thể; `ConversionService` chấp nhận nguồn null | Hạ tầng conversion xử lý null trước khi gọi converter ứng dụng. |
| `converter.convert("")` | Có: chuỗi rỗng vẫn là đối tượng không null | Converter xử lý theo quy tắc đầu vào, không phải quy tắc null. |
| `converter.convert("sai định dạng")` | Có | Converter xác thực và báo lỗi nếu không chuyển đổi được. |

**Không nên suy ngược** rằng vì `ConversionService` nhận `null` nên mọi `Converter` cũng phải xử lý `null`. Hai API có hợp đồng khác nhau.

## 3. Luồng xử lý null khi dùng ConversionService

Trong trường hợp thông thường với `GenericConversionService` hoặc `DefaultConversionService`:

~~~text
Ứng dụng / Spring Data Binder / Spring MVC
                 |
                 v
      ConversionService.convert(...)
                 |
         source == null ?
           /           \
         Có            Không
          |               |
  Xử lý null tại      Chọn converter
  tầng conversion          |
          |                v
          |       Converter<S,T>.convert(source)
          |                |
          +--------+-------+
                   |
             Kết quả / lỗi
~~~

- Nếu nguồn **khác null** và cần chuyển đổi, Spring tìm converter thích hợp và gọi `convert` với nguồn không null.
- Nếu nguồn **null**, `GenericConversionService` dùng đường xử lý nguồn null thay vì giao null cho converter thông thường. Với kiểu đích tham chiếu như `Integer` hoặc một record tùy biến, kết quả mặc định thường là `null`. Một số kiểu đích có xử lý riêng (ví dụ `Optional` có thể nhận `Optional.empty()`).
- Đích là kiểu nguyên thủy như `int` không chứa được `null`; không được mặc định rằng chuyển `null` sang `int.class` trả về 0. `GenericConversionService` báo `ConversionFailedException` trong trường hợp không thể gán null cho kiểu nguyên thủy.
- Bộ chuyển đổi chỉ được gọi khi hệ thống cần phép chuyển đổi phù hợp; nếu loại nguồn đã gán được trực tiếp cho loại đích, conversion service có thể trả nguồn như cũ. Đừng dựa vào việc converter tùy biến chắc chắn được gọi trong mọi phép gán kiểu.

Điều này giải thích vì sao `service.convert(null, SomeType.class)` có thể hoàn thành mà phương thức `SomeConverter.convert` không hề chạy. Trong luồng data binding, cơ chế xử lý giá trị vắng mặt còn có thể có các quy tắc riêng của binder hoặc controller; không đồng nhất tất cả với converter.

## 4. Ví dụ đầy đủ: String → TicketCode

Giả sử hệ thống nhận mã vé gồm **hai chữ cái, dấu gạch ngang và ba chữ số**, ví dụ `AB-123`. Nguồn có thể có khoảng trắng đầu/cuối và chữ thường; quy tắc chuyển đổi là chuẩn hóa rồi kiểm tra định dạng. Chuỗi rỗng, chỉ có khoảng trắng hoặc sai định dạng phải bị từ chối.

Ví dụ dùng **Java 17** và **Spring Framework 6.2.14**. Cấu trúc dự án:

~~~text
converter-contract/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConverterContractDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/ConverterContractDemo.java`:

~~~java
package demo;

import java.util.Locale;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterContractDemo {

    record TicketCode(String value) {}

    static final class StringToTicketCode implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            // Spring chỉ gọi phương thức này với source khác null.
            String normalized = source.strip().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                    "Ticket code must match AA-999");
            }

            return new TicketCode(normalized);
        }
    }

    public static void main(String[] args) {
        var service = new DefaultConversionService();
        service.addConverter(new StringToTicketCode());

        TicketCode code = service.convert("  ab-123  ", TicketCode.class);
        System.out.println(code.value());

        // ConversionService nhận null và xử lý trước converter.
        System.out.println(service.convert(null, TicketCode.class));

        try {
            service.convert("abc", TicketCode.class);
        } catch (ConversionFailedException ex) {
            System.out.println(ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Chạy từ thư mục có `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterContractDemo
~~~

Stdout của chương trình:

~~~text
AB-123
null
IllegalArgumentException
~~~

Giải thích từng đường đi:

1. `"  ab-123  "` là nguồn không null. Converter được gọi, `strip()` bỏ khoảng trắng biên, `toUpperCase(Locale.ROOT)` chuẩn hóa thành `AB-123`, regex cho phép nên trả `TicketCode("AB-123")`.
2. `service.convert(null, TicketCode.class)` do **conversion service** xử lý, trả `null` cho kiểu tham chiếu này. `StringToTicketCode.convert` không được gọi, nên việc dùng `source.strip()` bên trong converter vẫn tuân hợp đồng.
3. `"abc"` là nguồn không null nhưng không hợp lệ. Converter ném `IllegalArgumentException`; khi đi qua `ConversionService`, lỗi chuyển đổi được bọc thành `ConversionFailedException` với nguyên nhân gốc là `IllegalArgumentException`. Vì vậy dòng cuối in tên loại nguyên nhân gốc.
4. Nếu ứng dụng **tự gọi** `new StringToTicketCode().convert(null)`, nó đã vi phạm tiền điều kiện của API. Đừng dùng phép gọi đó làm tiêu chuẩn đánh giá converter được đăng ký qua Spring.

Không có trường trạng thái thay đổi theo mỗi lần gọi trong `StringToTicketCode`, nên ví dụ này còn phù hợp với yêu cầu thread-safe.

## 5. Thiết kế xử lý dữ liệu: thiếu, rỗng, trắng, sai định dạng

Nguồn không null chỉ cho phép bỏ nhánh kiểm tra **tham chiếu null** bên trong converter. Nó không thay thế việc thiết kế chính sách cho từng dạng đầu vào.

| Dữ liệu | Thuộc loại nào? | Xử lý đề xuất đối với mã vé |
| --- | --- | --- |
| `null` | Không có đối tượng nguồn | Tầng `ConversionService`/binding xử lý; có thể cần validation đánh dấu bắt buộc. |
| `""` | String không null, độ dài 0 | Báo `IllegalArgumentException` do thiếu mã hợp lệ. |
| `"   "` | String không null, chỉ chứa khoảng trắng | Sau `strip()` thành rỗng; báo lỗi. |
| `"  ab-123  "` | String không null, có thể chuẩn hóa | Trả `TicketCode("AB-123")`. |
| `"ab123"` | String không null, thiếu dấu gạch | Báo lỗi định dạng. |
| `"AB-123"` | String không null, hợp lệ | Trả `TicketCode("AB-123")`. |

Một số nghiệp vụ lại quy định chuỗi trắng là “không nhập” và muốn chuyển thành `null`. Khi ấy converter có thể viết:

~~~java
@Override
public TicketCode convert(String source) {
    String value = source.strip();
    if (value.isEmpty()) {
        return null;  // Chính sách nghiệp vụ cụ thể, KHÔNG phải xử lý nguồn null.
    }
    // Kiểm tra định dạng, tạo TicketCode...
}
~~~

Đây là **đoạn minh họa trong thân converter**, không phải chương trình độc lập; chính sách này khác ví dụ đầy đủ ở trên. Chỉ chọn cách trả `null` nếu API phía sau chấp nhận trạng thái vắng mặt. Không dùng `return null` một cách tùy tiện để che dữ liệu sai: nó có thể khiến lỗi đầu vào bị hiểu thành “không có dữ liệu”.

Quy trình quyết định nên là: **nguồn đã có mặt → chuẩn hóa hợp lệ → kiểm tra ràng buộc → tạo giá trị T hoặc báo lỗi rõ ràng**. Nếu thật sự có ý nghĩa “đầu vào trắng = vắng mặt”, phải viết chính sách đó và kiểm thử riêng.

## 6. Conversion khác validation như thế nào?

Hai tầng này giải quyết các câu hỏi khác nhau:

- **Conversion**: “Chuỗi hiện có có chuyển thành đối tượng đích được không?” Ví dụ `"AB-123"` → `TicketCode`, còn `"abc"` → lỗi chuyển đổi.
- **Validation**: “Đối tượng/thuộc tính sau chuyển đổi có thỏa quy tắc dữ liệu không?” Ví dụ mã vé bắt buộc có mặt, độ dài phù hợp, có tồn tại trong hệ thống hay không. Trong Bean Validation, `@NotNull` có thể kiểm tra giá trị vắng mặt; quy tắc nghiệp vụ phức tạp có thể dùng custom constraint.

Vì thế:

1. Không dùng hợp đồng “`source` không null” để kết luận trường dữ liệu đầu vào là bắt buộc. Trường vắng mặt có thể **không đi qua converter** mà vẫn cần `@NotNull` hoặc cơ chế required của tầng giao diện.
2. Không kỳ vọng converter luôn được gọi trước mọi validation. Thứ tự thực tế tùy đường binding, loại đối tượng, cấu hình và lỗi xảy ra; mục tiêu là đặt mỗi trách nhiệm đúng tầng.
3. Không kết luận `@NotNull` sẽ bắt được chuỗi trắng. Một String chứa khoảng trắng vẫn không null; nếu ràng buộc yêu cầu văn bản không trắng, cân nhắc `@NotBlank` trên thuộc tính chuỗi phù hợp.
4. Khi converter ném lỗi, tầng Spring MVC có thể biểu diễn nó bằng lỗi binding/type mismatch; cách biến lỗi đó thành HTTP response hay thông báo giao diện phụ thuộc controller, `BindingResult` và cấu hình exception handling. Không giả định trực tiếp `IllegalArgumentException` của converter sẽ luôn xuất hiện nguyên trạng tới client.

Đặt trách nhiệm rõ ràng giúp dữ liệu lỗi được giải thích đúng: **thiếu giá trị**, **định dạng không chuyển đổi được**, và **giá trị hợp kiểu nhưng vi phạm nghiệp vụ** là ba trường hợp khác nhau.

## 7. Đăng ký để Spring MVC dùng converter

Khi có Spring Web MVC trên classpath, có thể đăng ký converter vào `FormatterRegistry` qua `WebMvcConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ConverterContractDemo.StringToTicketCode());
    }
}
~~~

Đây là **đoạn tích hợp dùng trong một ứng dụng Spring MVC**, không thuộc chương trình Spring Core độc lập ở mục 4; nó cần các dependency ứng dụng web tương ứng. Với converter đã đăng ký, framework có thể dùng nó cho đường binding/chuyển đổi phù hợp (ví dụ một tham số kiểu `TicketCode` nhận từ chuỗi). Quy tắc nguồn không null vẫn nằm ở hợp đồng `Converter`; ý nghĩa của tham số thiếu, chuỗi trống và thông báo lỗi thuộc lớp web/binder.

Nếu dùng Spring Boot, hãy xác định đúng conversion service nào được dùng ở ngữ cảnh cụ thể: bean `ConversionService` tự cấu hình cho ứng dụng không mặc nhiên có nghĩa là mọi cơ chế binding đều dùng chính bean đó. Cách đăng ký qua `addFormatters` ở đây nêu rõ conversion registry của Spring MVC.

## 8. Converter.andThen và giá trị null trung gian

`Converter` hỗ trợ `andThen(after)` để kết hợp hai bước. Hợp đồng đầu vào không null áp dụng cho converter đầu tiên; converter thứ hai chỉ nên nhận một giá trị trung gian **khác null**. Trong hiện thực `andThen` của Spring, nếu bước đầu trả `null` thì kết quả gộp là `null` và bước sau không chạy.

Đoạn minh họa có thể đặt trong một phương thức Java, với import `Converter`:

~~~java
Converter<String, String> normalize = text ->
    text.isBlank() ? null : text.strip();

Converter<String, Integer> measure = text -> text.length();

Converter<String, Integer> chained = normalize.andThen(measure);

System.out.println(chained.convert("  ABC  ")); // 3
System.out.println(chained.convert("   "));     // null
~~~

- Cả hai lần gọi converter đầu tiên đều có `source` là String **khác null**.
- Lần hai, `normalize` trả `null` theo chính sách ứng dụng, `measure` không bị gọi với null; kết quả chuỗi là null.
- Nếu bạn **gọi trực tiếp** `chained.convert(null)`, nguồn đầu vào đã vi phạm tiền điều kiện ban đầu; `andThen` không biến lời gọi trực tiếp ấy thành lời gọi hợp lệ.

Đây là lý do phải tách bạch **null ở đầu vào** và **null do bước trung gian tạo ra**. Cách kết hợp converter không cho phép xem mọi giá trị đều chắc chắn không null sau bước đầu.

## 9. Kiểm thử đúng hợp đồng

Kiểm thử ở **hai mức** để tránh đánh đồng trách nhiệm.

**Mức đơn vị — gọi trực tiếp converter với các nguồn không null**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ConverterContractDemoTest {
    private final ConverterContractDemo.StringToTicketCode converter =
        new ConverterContractDemo.StringToTicketCode();

    @Test
    void convertsValidNonNullSource() {
        var result = converter.convert("  ab-123  ");
        assertEquals("AB-123", result.value());
    }

    @Test
    void rejectsBlankAndMalformedSources() {
        assertThrows(IllegalArgumentException.class,
            () -> converter.convert("   "));
        assertThrows(IllegalArgumentException.class,
            () -> converter.convert("ab123"));
    }
}
~~~

Đoạn test này nằm trong `src/test/java/demo/ConverterContractDemoTest.java` và cần dòng `package demo;` ở đầu tệp, cùng JUnit Jupiter trên test classpath. Đây là code kiểm thử thêm cho dự án mẫu, không được Maven thực thi nếu chưa bổ sung dependency/plugin kiểm thử.

**Mức tích hợp — gọi `ConversionService` để kiểm tra null tại ranh giới**:

~~~java
@Test
void serviceHandlesNullBeforeCallingConverter() {
    var service = new DefaultConversionService();
    service.addConverter(new ConverterContractDemo.StringToTicketCode());

    assertNull(service.convert(null, ConverterContractDemo.TicketCode.class));

    var failure = assertThrows(ConversionFailedException.class,
        () -> service.convert("xxx", ConverterContractDemo.TicketCode.class));

    assertInstanceOf(IllegalArgumentException.class, failure.getCause());
}
~~~

Các import cần bổ sung cho đoạn tích hợp này:

~~~java
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.support.DefaultConversionService;
~~~

Để chạy toàn bộ các test JUnit 5 trong dự án ví dụ, thêm các đoạn sau vào `pom.xml` ở đúng vị trí tương ứng:

~~~xml
<!-- Bên trong <dependencies> -->
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>

<!-- Bên trong <build><plugins> -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
~~~

Sau đó chạy `mvn test`. Khi ghép test thành **một tệp Java hợp lệ**, đặt `package demo;` đầu tệp, đặt tất cả `import` kế tiếp, rồi hợp nhất ba phương thức `@Test` trong một lớp `ConverterContractDemoTest`. Các khối ngắn ở trên minh họa từng phần, nên không được dán nguyên chúng nối tiếp nhau với `import` nằm sau khai báo lớp.

**Không nên viết `assertDoesNotThrow(() -> converter.convert(null))`**: test ấy áp một hợp đồng sai lên converter. Nếu muốn kiểm tra tầng ứng dụng nhận null, hãy gọi `ConversionService` và xác nhận cách nó xử lý. Ngược lại, nếu converter có API gọi trực tiếp riêng do ứng dụng tự quy định, phải tài liệu hóa và kiểm thử tiền điều kiện cho API đó, không suy ra từ Spring.

Các ca cần có khi nghiệp vụ mở rộng: chuỗi có dấu Unicode, khoảng trắng, mã quá dài, ký tự đặc biệt, dữ liệu đúng quy tắc nhưng không còn hợp lệ theo nghiệp vụ, và trường hợp nhiều luồng gọi cùng converter.

## 10. Lỗi thường gặp và cách tránh

| Sai lầm | Vì sao sai? | Cách làm |
| --- | --- | --- |
| Mọi converter đều bắt đầu bằng `if (source == null) return null;` | Dễ làm mờ tiền điều kiện “nguồn khác null”; có thể che việc gọi trực tiếp sai hợp đồng. | Đặt xử lý null tại tầng `ConversionService`/caller; converter tập trung vào giá trị S hiện có. |
| Gọi `converter.convert(null)` rồi kết luận Spring không an toàn | Gọi thẳng vượt qua bước lọc null của hạ tầng. | Kiểm thử `service.convert(null, Target.class)` khi cần xác nhận hành vi Spring. |
| Xem `""` hoặc `"   "` là `null` | Chúng là đối tượng `String` khác null. | Xây dựng chính sách rõ cho chuỗi rỗng/trắng, chuẩn hóa và kiểm tra. |
| Nghĩ converter phải luôn trả T không null | Hợp đồng cho phép kết quả null. | Tài liệu hóa khi nào trả null; xác nhận phía nhận chấp nhận null. |
| Bắt `NullPointerException` để xử lý dữ liệu nguồn sai | Che lỗi lập trình và không thể hiện đúng nguyên nhân. | Kiểm tra nội dung nguồn và ném `IllegalArgumentException` khi không chuyển đổi được. |
| Trả một giá trị mặc định tùy tiện khi parse lỗi | Hệ thống có thể lưu dữ liệu sai mà không báo. | Chỉ dùng giá trị mặc định khi được quy định tường minh. |
| Dựa vào `canConvert` để khẳng định một giá trị luôn hợp lệ | `canConvert` chủ yếu kiểm tra khả năng chuyển đổi theo kiểu, không xác nhận nội dung từng chuỗi. | Thử chuyển đổi giá trị thật và xử lý lỗi. |
| Lưu trạng thái tạm trong field của singleton converter | Nhiều request có thể ảnh hưởng lẫn nhau. | Dùng biến cục bộ; nếu cần cache, thiết kế an toàn luồng. |
| Cho rằng có converter thì đã thay thế validation | Conversion và validation kiểm tra các điều kiện khác nhau. | Kiểm tra tính bắt buộc, ràng buộc nghiệp vụ ở tầng validation phù hợp. |

## 11. Checklist khi tự triển khai

1. Ghi rõ cặp kiểu `S → T` và nơi đăng ký converter.
2. Xác định ý nghĩa của `null` ở **tầng gọi**; không mặc định converter trực tiếp được nhận null.
3. Quy định riêng hành vi của nguồn không null nhưng rỗng, trắng, sai định dạng, ngoài miền giá trị.
4. Chuẩn hóa dữ liệu có chủ đích (ví dụ `strip()`, locale cố định) trước khi kiểm tra; đừng thay đổi ngầm các giá trị mà nghiệp vụ yêu cầu giữ nguyên.
5. Chọn rõ giữa trả `T`, trả `null` theo chính sách có chủ đích, hoặc ném `IllegalArgumentException` khi không thể chuyển đổi.
6. Giữ converter không trạng thái thay đổi theo request hoặc bảo đảm an toàn luồng.
7. Kiểm thử converter bằng nguồn không null; kiểm thử đường null và exception wrapping qua `ConversionService`.
8. Kiểm tra cách Spring MVC/data binder/validation của ứng dụng chuyển lỗi thành thông tin cho người dùng.

**Tự kiểm tra kiến thức:** (a) Vì sao `service.convert(null, TicketCode.class)` có thể trả null dù `StringToTicketCode.convert` dùng `source.strip()` ngay? (b) Chuỗi `"   "` có vi phạm hợp đồng “nguồn không null” không? (c) Khi `Converter.andThen` có kết quả bước đầu là null, có nên gọi converter thứ hai với null không? Câu trả lời lần lượt là: null được xử lý ở conversion service trước; chuỗi trắng không null nên không vi phạm hợp đồng nhưng có thể sai quy tắc; `andThen` bỏ qua bước sau nếu kết quả trung gian là null.

## 12. Tài liệu tra cứu

- Spring Framework Reference, *Spring Type Conversion*: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Javadoc `Converter<S,T>`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Javadoc `GenericConversionService`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html
