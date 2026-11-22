# Vai trò chuyển kiểu trong Spring Expression Language (SpEL)

Spring Expression Language (SpEL) không chỉ đọc thuộc tính hoặc gọi phương thức. Khi một biểu thức ghi giá trị vào object, phần tử collection hay thuộc tính lồng nhau, giá trị nguồn có thể có kiểu khác với kiểu mà đích yêu cầu. **Bộ chuyển kiểu của evaluation context** giúp SpEL chuyển giá trị để phép gán phù hợp với kiểu của đích.

Ví dụ object có thuộc tính `Boolean enabled`. Biểu thức `parser.parseExpression("enabled").setValue(context, settings, "true")` nhận chuỗi "true" nhưng có thể gán Boolean true vào thuộc tính. Cơ chế chuyển kiểu được gọi trong quá trình thực thi biểu thức, dựa trên `TypeConverter` mà `EvaluationContext` cung cấp.

Trong Spring, SpEL sử dụng `ConversionService` của Spring Core theo mặc định thông qua bộ chuyển đổi của evaluation context. ConversionService có các converter phổ biến cho chuỗi, số, enum, collection và nhiều kiểu khác; ứng dụng cũng có thể đăng ký converter riêng. Hệ thống có hiểu biết về generic type khi chuyển đổi giá trị trong các thuộc tính collection. 

## 1. Vì sao SpEL cần chuyển kiểu?

Một biểu thức SpEL được phân tích thành cấu trúc thực thi. Khi đánh giá, SpEL cần biết object gốc là gì, có thể đọc/ghi thuộc tính nào, giá trị đang có kiểu gì và kiểu đích là gì khi cần gán.

Xét object:

~~~java
public class FeatureSettings {
    private Boolean enabled;
    private Integer retryCount;
}
~~~

Nếu expression nhận một giá trị chuỗi để gán:

~~~java
parser.parseExpression("retryCount")
      .setValue(context, settings, "5");
~~~

SpEL cần chuyển String "5" thành Integer trước khi gán vào retryCount. Nếu không có converter phù hợp hoặc nội dung không hợp lệ, quá trình đánh giá thất bại bằng ngoại lệ SpEL tương ứng.

Với danh sách:

~~~java
public class FeatureSettings {
    private List<Boolean> flags = new ArrayList<>();
}
~~~

biểu thức `flags[0]` trỏ tới phần tử Boolean đầu tiên. Gán chuỗi `"false"` vào vị trí đó yêu cầu chuyển đổi thành Boolean. SpEL có thể dùng metadata generic của property để biết phần tử mong đợi là Boolean.

**Chuyển kiểu không phải validation nghiệp vụ.** Chuyển được "5" thành số nguyên không chứng minh số lần retry được phép; ứng dụng vẫn cần ràng buộc như `retryCount >= 0` và giới hạn phù hợp.

## 2. EvaluationContext và TypeConverter

`EvaluationContext` là đối tượng cung cấp ngữ cảnh để SpEL đọc và ghi dữ liệu khi chạy expression. Nó cung cấp nhiều chiến lược, trong đó có `TypeConverter`.

| Thành phần | Vai trò |
|---|---|
| `ExpressionParser` | Phân tích chuỗi expression thành đối tượng `Expression` |
| `Expression` | Đại diện biểu thức đã phân tích; có thể đọc hoặc gán giá trị |
| `EvaluationContext` | Cung cấp root object, property/method resolver, type locator, type converter và chiến lược đánh giá |
| `StandardEvaluationContext` | Evaluation context đầy đủ tính năng, có thể cấu hình nhiều chiến lược |
| `SimpleEvaluationContext` | Context giới hạn tính năng SpEL cho data binding hoặc use case cần hạn chế |
| `TypeConverter` | Giao diện SpEL dùng để chuyển giá trị trong quá trình đánh giá |
| `StandardTypeConverter` | Adapter kết nối SpEL với cơ chế chuyển kiểu Spring Core |
| `ConversionService` | API Spring Core thực hiện chuyển đổi giữa các kiểu; có thể đăng ký converter |

Luồng gán có thể hình dung như sau:

~~~text
ExpressionParser
      |
      v
parseExpression("retryCount")
      |
      v
Expression.setValue(context, target, "5")
      |
      v
EvaluationContext.getTypeConverter()
      |
      v
TypeConverter / StandardTypeConverter
      |
      v
Spring ConversionService
      |
      v
Converter phù hợp: String -> Integer
      |
      v
Gán Integer(5) vào target.retryCount
~~~

Đây là luồng khái niệm. Chi tiết lựa chọn property accessor, xác định descriptor của đích và chọn converter do hạ tầng SpEL/Spring thực hiện.

### StandardEvaluationContext

`StandardEvaluationContext` cung cấp triển khai đầy đủ cho việc phân giải property, method, constructor, type và các chiến lược đánh giá. Nó cho phép thay đổi `TypeConverter`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeConverter(new StandardTypeConverter());
~~~

Khi cần chuyển đổi tùy chỉnh, có thể truyền một `ConversionService` cụ thể vào `StandardTypeConverter`.

### SimpleEvaluationContext

`SimpleEvaluationContext` dành cho tình huống chỉ cần một tập con tính năng SpEL, chẳng hạn data binding và lọc dựa trên property. Ứng dụng chọn rõ quyền truy cập property read-only hoặc read-write:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Context này không cung cấp toàn bộ chức năng của `StandardEvaluationContext`: ví dụ type references, constructor references và bean references bị loại khỏi tập tính năng mặc định. Nó hữu ích khi expression đến từ người dùng hoặc cấu hình bên ngoài và ứng dụng chỉ cần thao tác trên property được kiểm soát. Tuy vậy, vẫn phải cấu hình đúng property accessor và quyền đọc/ghi.

## 3. ConversionService và mối quan hệ với SpEL

`org.springframework.core.convert.ConversionService` định nghĩa API chuyển đổi ở runtime. Hai dạng gọi chính:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

Ngoài overload dùng `Class`, API còn hỗ trợ `TypeDescriptor` để mô tả generic type và metadata của property. Điều này quan trọng khi đích là collection, map hoặc phần tử collection.

Các implementation phổ biến:

- `DefaultConversionService`: implementation tiện dụng với converter mặc định.
- `GenericConversionService`: implementation tổng quát cho việc đăng ký và thực thi converter.
- `ConversionServiceFactory`: hỗ trợ tạo conversion service từ danh sách converter.

`ConversionService` được thiết kế stateless và có thể chia sẻ giữa các thread nếu converter do ứng dụng đăng ký cũng tuân thủ đặc tính đó. Thông thường, cấu hình converter khi ứng dụng khởi động thay vì đăng ký thay đổi trong lúc xử lý từng request.

### Converter SPI

Để tạo chuyển đổi từ kiểu nguồn `S` sang kiểu đích `T`, triển khai interface:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Ví dụ converter nhận chuỗi và chuyển thành enum `Priority`:

~~~java
public final class PriorityConverter
        implements Converter<String, Priority> {

    @Override
    public Priority convert(String source) {
        return Priority.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Converter nên xử lý rõ input rỗng, null nếu hợp đồng yêu cầu, chữ hoa/thường, locale, định dạng và lỗi. Không biến mọi lỗi thành giá trị mặc định một cách âm thầm vì điều đó che giấu input sai.

### TypeDescriptor và generic type

Hai kiểu sau khác nhau:

~~~java
List<String> names;
List<Boolean> flags;
~~~

Cả hai có raw type là `List`, nhưng kiểu phần tử đích khác nhau. Khi SpEL thực hiện ghi vào `flags[0]`, hạ tầng có thể sử dụng descriptor của property/element để chuyển chuỗi thành Boolean. Nếu chỉ gọi `ConversionService.convert(source, List.class)`, thông tin generic của phần tử không được thể hiện đầy đủ.

Đối với chuyển đổi collection generic một cách tường minh, có thể tạo `TypeDescriptor` cho property/field nguồn và đích rồi gọi overload nhận descriptor:

~~~java
Object converted = conversionService.convert(
        sourceValue,
        sourceTypeDescriptor,
        targetTypeDescriptor);
~~~

Các descriptor phải mô tả đúng kiểu nguồn/đích và generic type. Không tự giả định raw `List.class` đủ để xác định kiểu từng phần tử.

## 4. Ví dụ Java 17+ chạy được: chuyển kiểu mặc định và converter tùy chỉnh

Chương trình dưới đây minh họa ba trường hợp:

1. Gán chuỗi "true" vào property kiểu Boolean.
2. Gán chuỗi "false" vào phần tử `List<Boolean>` để thấy SpEL dùng kiểu generic.
3. Đăng ký converter riêng từ `String` sang enum `Priority` rồi gán "high" vào property.

Ví dụ dùng Spring Framework 6.2.12, Java 17+ và Maven. Không cần Spring Boot, web server hoặc database.

Cấu trúc thư mục:

~~~text
spel-conversion-demo/
├── pom.xml
└── src/main/java/demo/SpelConversionDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spel-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-expression</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SpelConversionDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.spel.support.StandardTypeConverter;

public final class SpelConversionDemo {

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    public static final class Settings {
        private Boolean enabled = false;
        private List<Boolean> flags = new ArrayList<>(List.of(true));
        private Priority priority = Priority.LOW;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public List<Boolean> getFlags() {
            return flags;
        }

        public void setFlags(List<Boolean> flags) {
            this.flags = flags;
        }

        public Priority getPriority() {
            return priority;
        }

        public void setPriority(Priority priority) {
            this.priority = priority;
        }
    }

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();
        Settings settings = new Settings();

        // ConversionService có sẵn converter thông dụng.
        StandardEvaluationContext defaultContext =
                new StandardEvaluationContext(settings);

        parser.parseExpression("enabled")
                .setValue(defaultContext, "true");

        parser.parseExpression("flags[0]")
                .setValue(defaultContext, "false");

        System.out.println("enabled=" + settings.getEnabled());
        System.out.println("flags[0]=" + settings.getFlags().get(0));
        System.out.println("flags.elementType="
                + settings.getFlags().get(0).getClass().getName());

        // Đăng ký converter riêng cho String -> Priority.
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                Priority.class,
                source -> Priority.valueOf(
                        source.trim().toUpperCase(Locale.ROOT)));

        StandardEvaluationContext customContext =
                new StandardEvaluationContext(settings);

        customContext.setTypeConverter(
                new StandardTypeConverter(conversionService));

        parser.parseExpression("priority")
                .setValue(customContext, "high");

        System.out.println("priority=" + settings.getPriority());
        System.out.println("priority.type="
                + settings.getPriority().getClass().getName());
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpelConversionDemo
~~~

Các dòng stdout do chương trình in ra:

~~~text
enabled=true
flags[0]=false
flags.elementType=java.lang.Boolean
priority=HIGH
priority.type=demo.SpelConversionDemo$Priority
~~~

Maven có thể in log riêng tùy môi trường; phần trên là output từ các lệnh `System.out.println`.

**Giải thích kết quả:**

- `enabled` khai báo kiểu Boolean; chuỗi "true" được chuyển thành `Boolean.TRUE` trước khi gán.
- `flags[0]` là phần tử của `List<Boolean>`. SpEL dùng thông tin kiểu phần tử để chuyển chuỗi "false" thành Boolean, không lưu chuỗi vào danh sách.
- `priority` khai báo kiểu enum `Priority`. Converter riêng chuẩn hóa chuỗi rồi gọi `Priority.valueOf(...)`.
- `StandardTypeConverter(conversionService)` kết nối evaluation context với conversion service vừa cấu hình. SpEL dùng `TypeConverter` để thực thi phép gán.

Nếu converter riêng nhận một giá trị không phải tên enum hợp lệ, `Priority.valueOf(...)` ném `IllegalArgumentException`; Spring/SpEL thể hiện thất bại dưới dạng lỗi chuyển đổi/đánh giá. Ứng dụng nên chuyển lỗi sang thông báo có thể hiểu được mà không để lộ stack trace.

## 5. Cấu hình TypeConverter riêng cho EvaluationContext

`EvaluationContext` cho phép thay `TypeConverter` trực tiếp. Có hai hướng thường gặp.

Dùng `StandardTypeConverter` mặc định:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(new StandardTypeConverter());
~~~

Dùng `ConversionService` đã đăng ký converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new PriorityConverter());

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

Hướng thứ hai tách phần đăng ký/quản lý converter khỏi việc thực thi biểu thức. Có thể chia sẻ cùng conversion service giữa nhiều expression context nếu converter stateless và thread-safe.

Lưu ý:

- Cấu hình context trước khi dùng expression.
- Không tạo converter phụ thuộc state của một request nếu conversion service sẽ được chia sẻ giữa nhiều thread.
- Với converter tùy chỉnh, định nghĩa rõ input null, blank, locale, đơn vị, precision và ngoại lệ.
- Không dùng converter để cấp quyền hoặc xác nhận nghiệp vụ.
- `TypeConverter` là chiến lược của SpEL. Các API trực tiếp khác có thể gọi `ConversionService.convert(...)` mà không cần evaluation context.

## 6. SimpleEvaluationContext và giới hạn tính năng SpEL

Nếu ứng dụng cho phép người dùng hoặc quản trị viên nhập expression, cần cân nhắc quyền biểu thức. `StandardEvaluationContext` mạnh và có thể mở nhiều tính năng: property, method, type references, constructor, bean resolution và function tùy cấu hình.

`SimpleEvaluationContext` dành cho những trường hợp cần tập tính năng hẹp hơn, đặc biệt là data binding và lọc dựa trên property. Ví dụ chỉ cần đọc property:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Nếu cần ghi property:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Builder có thể cấu hình accessor, method resolution hoặc type converter trong phạm vi được hỗ trợ. Context này loại bỏ một số tính năng có rủi ro cao hơn như type references, constructors và bean references trong mô hình mặc định. Điều đó giúp giảm bề mặt biểu thức mà người dùng có thể khai thác.

**Giới hạn cần nhớ:** SimpleEvaluationContext không phải bộ lọc tự động cho toàn bộ logic nghiệp vụ, cũng không thay thế authorization. Nếu bật ghi property, người dùng vẫn có thể sửa property mà accessor cho phép. Hãy cấu hình root object và accessor chỉ phơi bày dữ liệu cần thiết.

## 7. Phân biệt chuyển kiểu của SpEL với DataBinder và Spring MVC

Cả SpEL, `DataBinder` và Spring MVC đều có thể dùng hạ tầng chuyển đổi kiểu Spring, nhưng chúng giải quyết bài toán khác nhau:

| Cơ chế | Vai trò chính | Ví dụ |
|---|---|---|
| `ConversionService` | API chuyển kiểu dùng chung | String sang Integer, enum hoặc kiểu domain |
| `TypeConverter` của SpEL | Chuyển giá trị khi đánh giá expression | Gán "false" vào `flags[0]` kiểu Boolean |
| `DataBinder` | Bind tập property values vào object và thu thập lỗi | `age=abc` vào form có `Integer age` |
| `WebDataBinder` | Biến thể phục vụ web binding trong Spring MVC | Bind form/query của `@ModelAttribute` |
| `HttpMessageConverter` | Đọc/ghi HTTP body như JSON | Jackson deserialize body thành request DTO |
| Bean Validation | Kiểm tra ràng buộc dữ liệu | `@Min(1)`, `@NotBlank`, custom constraint |

`DataBinder` có thể nhận chuỗi "abc" cho thuộc tính Integer age, tạo `FieldError` nếu không chuyển kiểu được. Còn SpEL dùng `Expression.setValue(...)` và `EvaluationContext.getTypeConverter()` để chuyển giá trị cần gán trong expression. Cùng dùng converter Spring không có nghĩa `BindingResult` tự xuất hiện khi SpEL thất bại.

Trong Spring MVC, `@RequestBody` thường được đọc bởi HTTP message converter (ví dụ Jackson), còn `@ModelAttribute` đi qua cơ chế data binding. Đừng áp dụng mọi quy tắc của `WebDataBinder` cho JSON body hoặc cho SpEL expression.

## 8. Giá trị nguồn, kiểu đích và generic-aware conversion

Một điểm quan trọng của chuyển kiểu trong SpEL là hệ thống không chỉ nhìn vào raw type của object. Khi đích là property có generic type, Spring có thể dùng `TypeDescriptor` để mô tả đầy đủ kiểu.

Ví dụ:

~~~java
public class Example {
    private List<Boolean> flags = new ArrayList<>();

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

Với expression `flags[0]`, descriptor của property/phần tử giúp xác định đích là Boolean. Chuỗi "false" được chuyển thành Boolean khi gán.

Điều này hữu ích với `List<Boolean>`, `List<Integer>`, `Map<String, LocalDate>` và các property lồng nhau có kiểu khác nguồn. Tuy nhiên, `TypeDescriptor` không thể suy ra mọi kiểu trong mọi tình huống. Nếu raw collection không khai báo generic hoặc metadata bị mất, converter có thể không biết phần tử cần chuyển sang loại nào. Khi đó cần cung cấp descriptor đầy đủ hoặc thiết kế object có kiểu tĩnh rõ ràng.

## 9. Lỗi chuyển đổi và cách xử lý

**Không có converter phù hợp.** Đích là kiểu domain riêng nhưng conversion service chưa đăng ký converter. Kiểm tra source type, target type và đăng ký `Converter`, `ConverterFactory` hoặc `GenericConverter`.

**Dữ liệu không hợp lệ theo converter.** Ví dụ "very-high" không phải tên enum `Priority`. Converter cần báo lỗi nhất quán; không nên âm thầm chọn LOW.

**Nhầm lỗi chuyển kiểu với lỗi biểu thức.** Expression có thể lỗi vì property không tồn tại, index ngoài giới hạn, method không phân giải được hoặc converter thất bại. Phải đọc loại exception và ngữ cảnh thay vì chỉ bắt một exception tổng quát rồi bỏ qua.

**Mất thông tin generic.** Chuyển raw `List` không cho biết kiểu từng phần tử. Sử dụng `TypeDescriptor` khi cần chuyển collection/map parameterized.

**Dùng converter có tác dụng phụ.** Converter thường nên thuần, ngắn gọn và không gọi database/HTTP. Nếu converter thay đổi state hoặc phụ thuộc request, kết quả có thể khó lường và gây vấn đề khi conversion service được chia sẻ.

**Dùng StandardEvaluationContext cho expression không đáng tin.** Context đầy đủ tính năng có thể mở rộng quyền đọc/ghi và gọi method. Chọn SimpleEvaluationContext hoặc thiết kế expression/API hạn chế; không chỉ dựa vào converter riêng.

**Nhầm conversion với validation.** "0" chuyển thành Integer thành công nhưng vẫn có thể vi phạm `@Min(1)`. Thực hiện validation sau conversion theo đúng quy tắc nghiệp vụ.

## 10. Kiểm thử nên có

| Trường hợp | Kết quả mong đợi |
|---|---|
| Gán "true" vào `Boolean enabled` | `enabled == Boolean.TRUE` |
| Gán "false" vào `List<Boolean>` | Phần tử là Boolean false, không phải String |
| Gán "high" khi đã đăng ký `String -> Priority` | `Priority.HIGH` |
| Gán chuỗi không phải enum hợp lệ | Expression thất bại; không âm thầm gán mặc định |
| Đích không có converter phù hợp | Lỗi chuyển đổi được báo rõ |
| Context dùng read-only property access | Ghi property không được phép |
| Simple context được dùng cho expression cần type reference | Tính năng bị giới hạn theo thiết kế |
| Collection không khai báo generic | Không giả định Spring luôn suy ra kiểu phần tử |

Khi kiểm tra kết quả, so sánh **kiểu runtime** của giá trị được gán bên cạnh giá trị hiển thị. Ví dụ `flags.get(0).getClass()` giúp phát hiện trường hợp code vô tình giữ chuỗi thay vì Boolean.

## 11. Nguyên tắc thiết kế khi sử dụng chuyển kiểu trong SpEL

1. Dùng `EvaluationContext` đúng mức cần thiết; ưu tiên `SimpleEvaluationContext` khi chỉ cần data binding/property access hạn chế.
2. Định nghĩa root object có kiểu rõ ràng và chỉ phơi bày property cần thiết.
3. Chỉ đăng ký converter có input/output rõ ràng; xử lý rỗng, locale và lỗi nhất quán.
4. Tận dụng `ConversionService` dùng chung nếu converter stateless; tránh cấu hình converter theo request.
5. Với collection/map generic, giữ metadata kiểu rõ ràng để chuyển đúng phần tử.
6. Phân biệt chuyển kiểu, lỗi đánh giá expression và validation nghiệp vụ.
7. Không để expression không đáng tin truy cập rộng vào object nội bộ, method hoặc bean của ứng dụng.
8. Kiểm thử trường hợp thành công, không có converter, giá trị sai và quyền ghi bị giới hạn.

**Ghi nhớ:** SpEL không tự biến mọi giá trị thành mọi kiểu. Khi một expression đọc/ghi property cần chuyển kiểu, SpEL nhờ `TypeConverter` trong `EvaluationContext`; `StandardTypeConverter` nối tới Spring Core `ConversionService`, nơi chứa converter mặc định và converter do ứng dụng đăng ký. Việc lựa chọn context, quyền property access, converter và validation quyết định phép gán có an toàn và đúng nghiệp vụ hay không.

### Tài liệu tham khảo

- Spring Framework Reference 6.2 — Evaluation: `EvaluationContext`, `StandardEvaluationContext`, `SimpleEvaluationContext` và type conversion.
- Spring Framework Reference 6.2 — Spring Type Conversion: `ConversionService`, `Converter` SPI và `TypeDescriptor`.
- Spring Framework Javadoc — `EvaluationContext#getTypeConverter()`, `StandardEvaluationContext#setTypeConverter(...)`, `StandardTypeConverter`.
- Spring Framework Javadoc — `DefaultConversionService` và `ConversionService`.
