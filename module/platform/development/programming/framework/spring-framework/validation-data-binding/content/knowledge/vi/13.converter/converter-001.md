# Converter<S, T> và hợp đồng chuyển đổi một cặp kiểu trong Spring Framework

## 1. Vai trò và contract

Spring Core định nghĩa functional interface org.springframework.core.convert.converter.Converter<S, T> với một phương thức:

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

S là kiểu nguồn (*source*), T là kiểu đích (*target*). Một implementation mô tả một quy tắc chuyển đổi có hướng từ S sang T. Ví dụ: String → Integer, String → OrderCode, UUID → CustomerId hoặc LegacyStatus → OrderStatus.

Nếu viết Converter<String, OrderCode>, contract nói rằng convert nhận String và trả OrderCode khi thành công. Nó không tự động tạo chiều OrderCode → String. Nếu ứng dụng cần chiều ngược, phải đăng ký một quy tắc riêng, ví dụ Converter<OrderCode, String>, hoặc dùng một abstraction phù hợp hơn như Formatter khi bài toán là parse/print chuỗi.

**Converter không phải ConversionService.** Converter là một luật chuyển đổi cụ thể. ConversionService là cổng gọi thống nhất để kiểm tra khả năng chuyển đổi và yêu cầu chuyển đổi mà không cần caller tự tìm implementation.

## 2. “Một cặp kiểu” có nghĩa gì?

```text
S (source type) --[Converter<S, T>]--> T (target type)

String           --[StringToOrderCode]--> OrderCode
UUID             --[UUIDToCustomerId]----> CustomerId
LegacyStatus     --[LegacyToStatus]------> OrderStatus
```

Contract có bốn điểm:

1. Kiểu đầu vào được xác định là S.
2. Kết quả thành công có kiểu T.
3. Chiều chuyển đổi là S → T; không mặc định có T → S.
4. Implementation tự định nghĩa quy tắc parse, chuẩn hóa, ánh xạ hoặc từ chối giá trị.

Generic giúp compiler kiểm tra tương thích ở compile time. Một Converter<String, OrderCode> không thể được truyền nhầm vào vị trí cần converter nhận UUID nếu generic được giữ đúng. Nhưng generic chỉ kiểm tra kiểu Java, không thể chứng minh giá trị cụ thể hợp lệ về nghiệp vụ: một chuỗi "??" vẫn là String đúng kiểu nhưng chưa chắc là mã đơn hàng hợp lệ.

### 2.1. Converter chỉ có một chiều

Converter<String, OrderCode> trả lời câu hỏi “tạo OrderCode từ String như thế nào?”. Các thao tác sau là quy tắc riêng:

- In OrderCode thành chuỗi hiển thị.
- Parse ngày hoặc số theo locale.
- Chuyển domain code sang legacy code.
- Chuyển legacy code sang domain code.
- Chuyển qua một kiểu trung gian.

Không nên giả định một converter hai chiều chỉ vì dữ liệu vừa đi vào vừa đi ra ứng dụng. Parse đầu vào và biểu diễn đầu ra có thể có quy tắc khác nhau.

### 2.2. Converter và Formatter

| Tiêu chí | Converter<S, T> | Formatter<T> |
| --- | --- | --- |
| API | Một phương thức convert | parse và print |
| Đầu vào | Bất kỳ kiểu S | String khi parse |
| Đầu ra | T | T khi parse; String khi print |
| Locale | Không truyền vào convert | Có Locale |
| Bài toán | Chuyển một cặp kiểu | Nhập/hiển thị theo locale |
| Ví dụ | String → OrderCode | String ↔ LocalDate |

Mã kỹ thuật có cú pháp cố định thường phù hợp Converter. Ngày tháng, số thập phân hoặc tiền tệ nhập/hiển thị cho nhiều locale thường phù hợp Formatter.

## 3. Nguyên tắc implementation

Một converter tốt cần:

- **Kiểm tra miền giá trị:** từ chối nội dung không thể đại diện bằng kiểu đích.
- **Chuẩn hóa có chủ đích:** trim khoảng trắng hoặc chuẩn hóa chữ hoa/thường khi domain quy định.
- **Không làm mất thông tin:** không xóa ký tự/đổi định dạng ngoài contract.
- **Báo lỗi rõ ràng:** input không hợp lệ phải tạo lỗi có thể chẩn đoán.
- **Stateless và thread-safe:** converter thường được tái sử dụng đồng thời giữa nhiều request.
- **Hạn chế side effect:** parse mã không nên tự ghi database, gửi email hoặc đổi trạng thái nghiệp vụ.

Null và chuỗi rỗng cần được phân biệt. DataBinder/ConversionService/MVC có chính sách riêng khi xử lý giá trị vắng mặt; không nên biến mọi input rỗng thành một object mặc định để che dữ liệu sai. Nếu use case cần optional input, xác định ở boundary bằng kiểu và validation phù hợp.

### 3.1. Trả null hay ném exception?

Chính sách thường dễ hiểu nhất là trả T khi hợp lệ và ném IllegalArgumentException khi giá trị không thuộc miền converter chấp nhận. Khi gọi qua ConversionService, lỗi từ converter thường được bọc trong ConversionFailedException.

Chỉ trả null nếu null mang ý nghĩa đã được quy định và tầng gọi có thể hiểu rõ ý nghĩa đó. Không bắt mọi parse error rồi trả null, vì caller khó phân biệt “không có dữ liệu” và “dữ liệu sai”.

## 4. Ví dụ: String sang OrderCode

Giả sử mã đơn hàng có định dạng:

```text
ORD-000123
```

Converter sẽ trim khoảng trắng hai đầu, chuyển prefix sang chữ hoa bằng Locale.ROOT, kiểm tra prefix ORD- và đúng sáu chữ số, sau đó tạo value object bất biến.

### 4.1. Cấu trúc project và dependency

Ví dụ dùng Java 17, Spring Framework 6.2.6, không cần web server hay database:

```text
converter-demo/
├── pom.xml
└── src/main/java/demo/
    ├── OrderCode.java
    ├── StringToOrderCode.java
    └── ConverterDemo.java
```

pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency spring-context cung cấp các module Spring cần thiết cho ví dụ conversion.

### 4.2. Value object

Tệp src/main/java/demo/OrderCode.java:

```java
package demo;

import java.util.Objects;

public record OrderCode(String value) {
    public OrderCode {
        Objects.requireNonNull(value, "value must not be null");
        if (!value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid OrderCode");
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

Record giúp dữ liệu gọn và bất biến. Compact constructor bảo vệ invariant ngay cả khi object được tạo từ một đường khác ngoài converter.

### 4.3. Converter implementation

Tệp src/main/java/demo/StringToOrderCode.java:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToOrderCode
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException("Order code is required");
        }

        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }

        return new OrderCode(normalized);
    }
}
```

Locale.ROOT phù hợp khi chuẩn hóa mã kỹ thuật không phụ thuộc ngôn ngữ người dùng. Converter chỉ nhận String do caller cung cấp; nó không tự đọc HTTP request.

### 4.4. Đăng ký và sử dụng ConversionService

Tệp src/main/java/demo/ConverterDemo.java:

```java
package demo;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.GenericConversionService;

public final class ConverterDemo {

    public static void main(String[] args) {
        GenericConversionService registry =
                new GenericConversionService();

        registry.addConverter(new StringToOrderCode());

        ConversionService service = registry;

        System.out.println("can String -> OrderCode: " +
                service.canConvert(String.class, OrderCode.class));

        OrderCode code = service.convert(
                " ord-000123 ", OrderCode.class);

        System.out.println("converted: " + code);
        System.out.println("can OrderCode -> String: " +
                service.canConvert(OrderCode.class, String.class));
    }
}
```

Chạy tại thư mục converter-demo:

```bash
mvn -q clean compile exec:java
```

Stdout do chương trình in:

```text
can String -> OrderCode: true
converted: ORD-000123
can OrderCode -> String: false
```

Giải thích:

1. addConverter đăng ký một đường String → OrderCode.
2. canConvert kiểm tra registry có đường chuyển đổi theo cặp kiểu.
3. convert tìm converter phù hợp, chuẩn hóa chuỗi và tạo value object.
4. OrderCode → String trả false vì chưa đăng ký quy tắc chiều ngược.

canConvert chỉ xác nhận có đường chuyển đổi theo kiểu. Nó **không thử mọi giá trị**. Một chuỗi sai định dạng vẫn có thể làm convert thất bại dù canConvert trả true.

## 5. Khi input không hợp lệ

Gọi:

```java
service.convert("ORD-12", OrderCode.class);
```

converter từ chối vì mã không có đủ sáu chữ số. Khi đi qua GenericConversionService, lỗi thường được bọc bởi ConversionFailedException.

Có thể xử lý:

```java
try {
    service.convert("ORD-12", OrderCode.class);
} catch (org.springframework.core.convert.ConversionFailedException ex) {
    System.out.println("conversion failed");
}
```

Nếu chỉ chạy snippet trên, chương trình tự in:

```text
conversion failed
```

Trong MVC, conversion error có thể được đưa vào lỗi binding/type mismatch. Controller hoặc exception handler chọn HTTP status và thông báo ổn định. Không gửi stack trace cho client và không tạo OrderCode mặc định để che dữ liệu sai.

## 6. Generic S và T giúp gì?

Khai báo:

```java
Converter<String, OrderCode> parser = new StringToOrderCode();
```

giúp compiler biết parser nhận String và trả OrderCode. Truyền Integer vào convert là lỗi compile time; caller dùng trực tiếp OrderCode mà không phải cast. Nếu API chỉ có Object convert(Object), caller phải cast và nhiều lỗi kiểu chỉ xuất hiện lúc chạy.

Generic Java bị type erasure ở runtime. Với cấu trúc như List<String> → List<OrderCode>, raw type List.class không đủ mô tả kiểu phần tử. Spring cung cấp metadata giàu hơn như TypeDescriptor và SPI GenericConverter cho những trường hợp đó.

### 6.1. Khi nào Converter là đủ?

Dùng Converter<S,T> khi có một cặp kiểu cụ thể, quy tắc không cần locale và không cần metadata field/generic phức tạp. Ví dụ String → OrderCode, UUID → CustomerId hoặc Long → InvoiceNumber.

### 6.2. SPI tổng quát hơn

| SPI | Mục đích | Ví dụ |
| --- | --- | --- |
| Converter<S,T> | Một cặp source/target | String → OrderCode |
| ConverterFactory<S,R> | Một nguồn sang họ kiểu đích có chung base type | String → enum subtype |
| GenericConverter | Nhiều cặp kiểu, có thể dùng TypeDescriptor | Collection/map |
| ConditionalGenericConverter | Generic converter có điều kiện | Theo kiểu/annotation |

Không nên dùng SPI phức tạp nếu một Converter diễn đạt đủ contract. Chọn API theo lượng thông tin thực sự cần.

## 7. Phân biệt các thành phần

| Thành phần | Vai trò | API tiêu biểu |
| --- | --- | --- |
| Converter<S,T> | Một luật chuyển kiểu | T convert(S source) |
| ConversionService | Hỏi và thực hiện chuyển đổi | canConvert, convert |
| ConverterRegistry | Đăng ký/quản lý converter | addConverter |
| GenericConversionService | Implementation conversion và registry | Cài đặt các interface trên |
| DefaultConversionService | Service có sẵn converter mặc định | Dùng ngay và bổ sung converter |

Flow runtime:

```text
Cấu hình:
  ConverterRegistry.addConverter(StringToOrderCode)

Khi chạy:
  ConversionService.convert("ORD-000123", OrderCode.class)
                  |
                  v
          tìm converter phù hợp
                  |
                  v
          StringToOrderCode.convert(source)
                  |
                  v
                OrderCode
```

Caller chỉ phụ thuộc ConversionService; không cần biết class converter cụ thể. Nếu biến có kiểu tĩnh ConversionService, nó không có phương thức addConverter. Hãy đăng ký qua registry trước khi đưa service cho caller.

### 7.1. GenericConversionService

Dùng khi muốn registry rỗng và tự đăng ký:

```java
GenericConversionService service = new GenericConversionService();
service.addConverter(new StringToOrderCode());
```

Phù hợp với ví dụ độc lập, test hoặc registry tùy chỉnh.

### 7.2. DefaultConversionService

Dùng khi muốn có sẵn converter phổ biến:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToOrderCode());
```

Các converter mặc định không thể biết mọi kiểu domain của ứng dụng; converter riêng vẫn phải đăng ký.

### 7.3. Đăng ký trong Spring MVC

Dùng WebMvcConfigurer.addFormatters(FormatterRegistry):

```java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCode());
    }
}
```

Đây là snippet cấu hình cần các import Configuration, WebMvcConfigurer, FormatterRegistry và class converter. MVC có thể dùng quy tắc này khi bind query/path/form value sang OrderCode trong các ngữ cảnh dùng ConversionService.

Đừng mặc định một converter được đăng ký cho MVC cũng thay toàn bộ JSON deserialization:
- @ModelAttribute dùng cơ chế data binding của MVC.
- @RequestBody JSON thường đi qua HttpMessageConverter như Jackson.
- Spring Boot configuration/property binding có đường tích hợp riêng; cần cấu hình đúng subsystem.

## 8. Thread safety, null và side effect

### 8.1. Thread safety

Converter thường đăng ký một lần rồi dùng bởi nhiều request đồng thời. Hãy giữ implementation stateless hoặc chỉ dùng state bất biến. Không lưu dữ liệu request trong field và không chia sẻ mutable formatter như SimpleDateFormat.

### 8.2. Null và chuỗi rỗng

Phân biệt null/vắng mặt, chuỗi rỗng, chỉ khoảng trắng và chuỗi sai cú pháp. DataBinder/ConversionService/MVC có thể xử lý null/empty trước khi gọi converter. Không gộp tất cả thành một code mặc định; điều đó che input thiếu. Quy tắc null cần rõ ở boundary và nhất quán với validation.

### 8.3. Side effect

Converter nên là thao tác nhẹ, xác định và có thể kiểm thử lại. Nếu String → Customer cần truy vấn database, kiểm tra quyền hoặc gọi mạng, đó thường là bước application service/use case thay vì converter thuần vì phát sinh transaction, latency và lỗi hạ tầng.

## 9. Kiểm thử Converter

Có thể test trực tiếp không cần Spring context:

```java
@Test
void convertsNormalizedOrderCode() {
    OrderCode code = new StringToOrderCode().convert(" ord-000123 ");
    assertEquals("ORD-000123", code.value());
}

@Test
void rejectsInvalidOrderCode() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new StringToOrderCode().convert("ORD-12")
    );
}
```

Đây là snippet JUnit 5, cần import và dependency test. Nên test converter trực tiếp rồi test integration để xác nhận converter được đăng ký trong registry đúng.

Các case cần có:
1. Chuỗi canonical hợp lệ.
2. Khoảng trắng hai đầu.
3. Prefix chữ thường nếu policy cho phép.
4. Prefix sai hoặc thiếu.
5. Số chữ số quá ít/quá nhiều.
6. Ký tự ngoài chữ số.
7. Chuỗi rỗng/blank.
8. Không có chiều ngược khi chưa đăng ký.
9. Đăng ký MVC rồi bind một request.
10. Gọi đồng thời để xác nhận converter không giữ state.

Test riêng canConvert và convert: đường kiểu tồn tại nhưng giá trị cụ thể vẫn có thể sai.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ Converter tự có chiều ngược | Registry không có T → S | Đăng ký converter ngược |
| Dùng Converter cho format phụ thuộc locale | Parse sai định dạng vùng | Dùng Formatter |
| Tin canConvert=true nghĩa là input hợp lệ | convert vẫn ném lỗi | Kiểm tra giá trị thực |
| Trả null cho mọi lỗi | Không phân biệt thiếu và sai | Xác định null semantics |
| Converter có mutable state | Race condition | Stateless/thread-safe |
| Truy vấn DB trong parse | Gắn conversion với hạ tầng | Tách lookup sang service |
| Đăng ký nhầm registry | Subsystem không thấy converter | Đăng ký đúng extension point |
| Nghĩ converter MVC xử lý JSON | Jackson vẫn có cấu hình riêng | Cấu hình HttpMessageConverter |
| Generic converter quá rộng | Bắt nhầm cặp kiểu | Thu hẹp hoặc dùng điều kiện |
| Lẫn conversion với validation | Khó xử lý đúng lớp | Converter chuyển kiểu; validator/service kiểm tra rule |
| Dùng Object → String cho mọi thứ | Biểu diễn khó kiểm soát | Converter theo cặp kiểu cụ thể |

## 11. Chọn SPI theo nhu cầu

- Converter<S,T>: một source type sang một target type.
- Formatter<T>: parse/print chuỗi có locale.
- ConverterFactory<S,R>: một nguồn sang họ kiểu đích có chung base type.
- GenericConverter: nhiều cặp kiểu hoặc cần TypeDescriptor.
- ConditionalGenericConverter: áp dụng theo điều kiện metadata.

Chọn theo thông tin quy tắc cần biết, không theo số lượng method.

## 12. Tự kiểm tra

**1.** Converter<String, OrderCode> nhận và trả gì?  
Nhận String, trả OrderCode khi thành công.

**2.** Contract trên có tự chuyển OrderCode thành String không?  
Không. Đó là chiều khác, cần quy tắc riêng.

**3.** canConvert(String.class, OrderCode.class) == true có đảm bảo chuỗi "bad" chuyển được không?  
Không. Nó chỉ kiểm tra đường chuyển đổi theo kiểu, không kiểm tra từng giá trị.

**4.** Mã kỹ thuật có cú pháp cố định nên dùng Converter hay Formatter?  
Thường là Converter. Dữ liệu phụ thuộc locale nên xem Formatter.

**5.** Converter có nên truy cập database để tìm entity không?  
Thông thường không; lookup và authorization thuộc service/use case.

**6.** Converter MVC có tự xử lý JSON @RequestBody không?  
Không mặc định. JSON thường qua HttpMessageConverter/Jackson.

**7.** Generic giúp gì dù Java có type erasure?  
Compiler kiểm tra kiểu ở compile time. Khi cần generic runtime metadata, dùng TypeDescriptor và SPI tổng quát hơn.

## 13. Checklist đưa converter vào dự án

1. Xác định source type và target type; đặt tên theo hướng, ví dụ StringToOrderCode.
2. Quy định parse, normalize và dữ liệu bị từ chối.
3. Bảo vệ invariant ở value object khi cần.
4. Giữ converter stateless, thread-safe và không side effect.
5. Đăng ký đúng ConverterRegistry/FormatterRegistry hoặc extension point MVC.
6. Gọi qua ConversionService khi cần abstraction.
7. Không giả định chiều ngược; đăng ký riêng nếu cần.
8. Test valid, invalid, boundary, blank và registry integration.
9. Xử lý conversion error ở web/use case mà không lộ stack trace.
10. Chuyển sang SPI khác khi cần locale, generic metadata, họ kiểu đích hoặc lookup nghiệp vụ.

**Ghi nhớ:** Converter<S,T> là hợp đồng **một chiều cho một cặp kiểu nguồn–đích**. Generic mô tả kiểu input/output; implementation xử lý giá trị cụ thể; registry và ConversionService giúp Spring tìm và gọi đúng quy tắc. Conversion, formatting, validation và nghiệp vụ là những trách nhiệm khác nhau.

## 14. Tài liệu chính thức

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter, ConverterFactory và registry.
- [Spring Javadoc — Converter (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/converter/Converter.html): contract convert(S source).
- [Spring Javadoc — ConversionService (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/ConversionService.html): canConvert và convert.
- [Spring Javadoc — GenericConversionService (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html): registry và dispatch.
- [Spring Javadoc — ConverterRegistry (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): đăng ký converter và factory.
- [Spring MVC — Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký qua WebMvcConfigurer.addFormatters.
