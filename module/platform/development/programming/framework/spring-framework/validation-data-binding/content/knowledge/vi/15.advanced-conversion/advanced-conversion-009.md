# Độ ưu tiên giữa converter cụ thể và converter tổng quát trong Spring

Khi Spring có nhiều converter cùng có khả năng xử lý một phép chuyển đổi, `ConversionService` phải chọn một converter phù hợp. Ví dụ, ứng dụng có thể đồng thời đăng ký:

- Một converter cụ thể từ `String` sang `CustomerCode`.
- Một `GenericConverter` tổng quát từ `String` sang `Object`, có khả năng tạo nhiều loại mã khác nhau dựa trên kiểu đích.

Khi chuyển `"C-42"` sang `CustomerCode`, converter cụ thể nên được xét trước cặp tổng quát `String -> Object`. Nhưng không nên rút gọn thành quy tắc “`Converter` luôn thắng `GenericConverter`”. **Spring chọn theo các cặp kiểu và thứ tự duyệt hệ phân cấp kiểu; nếu nhiều converter cùng đăng ký một cặp, điều kiện và thứ tự đăng ký cũng có thể ảnh hưởng.**

Bài này giải thích cơ chế lựa chọn trong `GenericConversionService`, phân biệt độ cụ thể của cặp kiểu với loại SPI, làm rõ `ConditionalConverter`/`ConditionalGenericConverter`, minh họa trường hợp cụ thể và tổng quát bằng chương trình Java 17+, và đưa ra cách thiết kế để tránh kết quả phụ thuộc cấu hình ngẫu nhiên.

## 1. Trước hết phải hiểu “cụ thể” và “tổng quát” là gì

Có hai khái niệm khác nhau thường bị gộp làm một:

**Mức độ cụ thể của cặp kiểu** nói về kiểu nguồn và kiểu đích được đăng ký.

~~~java
Converter<String, CustomerCode>
~~~

là cặp cụ thể `String -> CustomerCode`.

~~~java
GenericConverter // ConvertiblePair(String.class, Object.class)
~~~

là cặp rộng hơn `String -> Object`. Nó có thể được xét khi target là `CustomerCode`, bởi vì `CustomerCode` là kiểu con của `Object`.

**Loại SPI** nói về giao diện được triển khai:

- `Converter<S,T>`: một cặp source/target xác định bằng generic.
- `ConverterFactory<S,R>`: một kiểu nguồn sang họ kiểu đích có chung kiểu giới hạn.
- `GenericConverter`: có thể khai báo nhiều `ConvertiblePair` và nhận `TypeDescriptor` của nguồn/đích.
- `ConditionalConverter`: bổ sung điều kiện để một converter được chọn.
- `ConditionalGenericConverter`: kết hợp khả năng khai báo pair của `GenericConverter` với điều kiện `matches(...)`.

Đây là hai trục độc lập. Một `GenericConverter` có thể đăng ký đúng cặp `String -> CustomerCode` và rất cụ thể; một `Converter` khác cũng có thể rất tổng quát nếu kiểu đích là một lớp cha. Không thể xác định ưu tiên chỉ bằng cách nhìn tên interface.

| So sánh | Converter cụ thể | Converter tổng quát |
| --- | --- | --- |
| Ví dụ cặp kiểu | `String -> CustomerCode` | `String -> Object` |
| Phạm vi | Một kiểu đích rõ ràng | Nhiều kiểu đích có thể nằm dưới Object |
| Metadata khi convert | Chỉ nhận source value trong `convert(S)` | Nhận `TypeDescriptor` nguồn và đích |
| Có thể cùng tồn tại? | Có | Có |
| Câu hỏi quyết định | Cặp kiểu này có được xét trước không? | Cặp tổng quát có còn là ứng viên sau các cặp cụ thể không? |

## 2. ConversionService tìm converter như thế nào?

Các implementation phổ biến như `GenericConversionService` duy trì registry các converter đã đăng ký và tra cứu theo cặp kiểu. Khi cần chuyển đổi một giá trị, service nhận dạng kiểu nguồn/đích, tìm converter phù hợp, rồi thực thi converter đã chọn.

Ở mức khái niệm:

~~~text
convert(source, targetType)
            |
            v
   Tạo TypeDescriptor nguồn/đích
            |
            v
  Tra cache theo source + target
            |
       cache miss
            |
            v
  Duyệt hệ phân cấp kiểu nguồn
            |
            v
  Với từng kiểu nguồn, duyệt
  hệ phân cấp kiểu đích
            |
            v
  Tìm ConvertiblePair tương ứng
            |
            v
  Kiểm tra ConditionalConverter.matches(...)
            |
      +-----+------+
      |            |
   Có ứng viên    Chưa có
      |            |
  Chọn converter  Xét cặp tiếp theo
      |
      v
  Thực thi convert(...)
~~~

Mã nguồn `GenericConversionService` mô tả rõ việc tìm kiếm trên **toàn bộ class/interface hierarchy** của source và target. Cách duyệt là:

1. Tạo danh sách kiểu nguồn theo thứ tự phân cấp.
2. Tạo danh sách kiểu đích theo thứ tự phân cấp.
3. Duyệt từng kiểu nguồn; với mỗi kiểu nguồn, duyệt các kiểu đích.
4. Với cặp tương ứng, tìm converter đã đăng ký và kiểm tra điều kiện nếu converter là conditional.
5. Dừng ở converter phù hợp đầu tiên; nếu không có cặp nào phù hợp thì dùng fallback hoặc báo không tìm thấy converter.

Vì source hierarchy là vòng lặp bên ngoài, **không phải mọi trường hợp đều có một quy tắc tuyến tính “target exact luôn thắng source exact”**. Ví dụ, cặp `String -> CodeValue` có thể được xét trước `Object -> CustomerCode` do Spring duyệt `String` trước `Object`, dù target thứ nhất là interface chung.

### Ví dụ thứ tự phân cấp

Giả sử:

~~~java
interface CodeValue {}
final class CustomerCode implements CodeValue {}
~~~

Với yêu cầu `String -> CustomerCode`, danh sách kiểu đích có thể chứa `CustomerCode` trước, sau đó các interface mà nó triển khai, và cuối cùng là các kiểu cha như `Object`.

Các ứng viên có thể được xét theo dạng:

~~~text
(String, CustomerCode)    // cặp target cụ thể
(String, CodeValue)       // target interface
(String, Object)          // target tổng quát
...
~~~

Trong trường hợp cùng source là `String`, cặp `String -> CustomerCode` có vị trí trước `String -> Object`. Đây là lý do converter được đăng ký cho target cụ thể thường được chọn trước converter có target rộng hơn.

Nhưng nếu source pair cũng khác nhau, thứ tự nguồn tham gia vào quyết định. Do đó, nên đọc cặp kiểu thực sự được khai báo trong converter và test theo target cần dùng, thay vì suy luận từ nhãn “specific” hoặc “generic”.

## 3. Ví dụ trực quan: String -> CustomerCode so với String -> Object

Giả sử có hai kiểu mã:

~~~java
public interface CodeValue {
    String value();
}

public record CustomerCode(String value) implements CodeValue {}

public record OrderCode(String value) implements CodeValue {}
~~~

Một converter cụ thể:

~~~java
public final class StringToCustomerCode
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Một converter tổng quát:

~~~java
public final class StringToCodeValue
        implements GenericConverter {

    // Pair tổng quát, có thể được xét cho target cụ thể dưới Object.
    // convert(...) phải tự nhìn TypeDescriptor của target.
}
~~~

Nếu yêu cầu `String -> CustomerCode`, Spring có thể tìm thấy pair trực tiếp `String -> CustomerCode` trước pair `String -> Object`. Converter cụ thể được dùng.

Nếu yêu cầu `String -> OrderCode` và không có converter riêng cho OrderCode, pair `String -> Object` có thể là ứng viên tổng quát. `GenericConverter` có thể nhìn `targetType` và trả đúng kiểu đối tượng cần tạo.

Điều này minh họa nguyên tắc thiết kế hữu ích: **đăng ký converter rõ ràng cho những cặp có quy tắc riêng, chỉ dùng converter tổng quát cho phần thực sự chia sẻ được một thuật toán.**

## 4. Chương trình Java 17+ chạy được: cặp cụ thể và cặp tổng quát

Ví dụ sau dùng Spring Framework `6.2.0` và `DefaultConversionService`. Một `Converter<String, CustomerCode>` cụ thể được đăng ký cùng một `GenericConverter` có pair `String -> Object`.

Kết quả kỳ vọng:

- `CustomerCode` dùng converter cụ thể.
- `OrderCode` dùng converter tổng quát, vì không có pair riêng `String -> OrderCode`.
- `canConvert(...)` trả lời khả năng theo kiểu; nó không thực thi giá trị cụ thể.

Cấu trúc thư mục:

~~~text
converter-priority-demo/
├── pom.xml
└── src/main/java/example/ConverterPriorityDemo.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>converter-priority-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>example.ConverterPriorityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. ConverterPriorityDemo.java

~~~java
package example;

import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterPriorityDemo {

    public interface CodeValue {
        String value();
    }

    public record CustomerCode(String value) implements CodeValue {
    }

    public record OrderCode(String value) implements CodeValue {
    }

    public static final class StringToCustomerCode
            implements Converter<String, CustomerCode> {

        @Override
        public CustomerCode convert(String source) {
            return new CustomerCode(
                    "specific:" + source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static final class StringToCodeValue
            implements GenericConverter {

        private static final Set<ConvertiblePair> PAIRS =
                Set.of(new ConvertiblePair(String.class, Object.class));

        @Override
        public Set<ConvertiblePair> getConvertibleTypes() {
            return PAIRS;
        }

        @Override
        public Object convert(
                Object source,
                TypeDescriptor sourceType,
                TypeDescriptor targetType) {

            String normalized = source.toString()
                    .trim().toUpperCase(Locale.ROOT);

            Class<?> target = targetType.getObjectType();

            if (target == OrderCode.class) {
                return new OrderCode("generic:" + normalized);
            }

            if (target == CustomerCode.class) {
                return new CustomerCode("generic:" + normalized);
            }

            throw new IllegalArgumentException(
                    "Unsupported code type: " + target.getName());
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        // Đăng ký converter tổng quát và converter cụ thể.
        service.addConverter(new StringToCodeValue());
        service.addConverter(new StringToCustomerCode());

        CustomerCode customer =
                service.convert(" c-42 ", CustomerCode.class);

        OrderCode order =
                service.convert(" ord-9 ", OrderCode.class);

        System.out.println("customer=" + customer.value());
        System.out.println("order=" + order.value());
        System.out.println("canConvertCustomer="
                + service.canConvert(String.class, CustomerCode.class));
        System.out.println("canConvertOrder="
                + service.canConvert(String.class, OrderCode.class));
    }
}
~~~

### 4.3. Chạy chương trình

Với JDK 17+ và Maven, chạy trong thư mục `converter-priority-demo`:

~~~bash
mvn -q compile exec:java
~~~

Stdout dự kiến:

~~~text
customer=specific:C-42
order=generic:ORD-9
canConvertCustomer=true
canConvertOrder=true
~~~

Giải thích:

1. `StringToCustomerCode` đăng ký pair `String -> CustomerCode`.
2. `StringToCodeValue` đăng ký pair rộng hơn `String -> Object`. Khi convert sang `OrderCode`, target nằm dưới `Object` nên converter tổng quát là một ứng viên.
3. Khi convert sang `CustomerCode`, lookup gặp pair target cụ thể trước pair `String -> Object`; vì vậy giá trị có tiền tố `specific:`.
4. Khi convert sang `OrderCode`, không có converter cụ thể hơn; `GenericConverter` nhìn `targetType` và tạo `OrderCode`.
5. `canConvert(...)` trả `true` cho cả hai cặp vì có một đường converter phù hợp về kiểu; nó không chứng minh mọi chuỗi đều hợp lệ hoặc converter sẽ không ném exception.

Đây là chương trình hoàn chỉnh, không cần Spring Boot hay web server. Kết quả nêu trên là kết quả dự kiến theo các cặp kiểu và logic converter đã viết; nên chạy Maven trên đúng môi trường dự án khi áp dụng.

## 5. Độ ưu tiên không phải bảng “Converter thắng GenericConverter”

Một ngộ nhận thường gặp là:

> Converter luôn có độ ưu tiên cao hơn GenericConverter.

Đây không phải hợp đồng chung của SPI. Một `Converter<S,T>` khi đăng ký được Spring adapter thành converter nội bộ với pair xác định; một `GenericConverter` cũng có thể đăng ký đúng cùng pair. Khi đó hai ứng viên đang cạnh tranh **trên cùng một ConvertiblePair**, và kết quả phụ thuộc thứ tự nội bộ của registry cùng điều kiện match, không phải tên interface nào “cao cấp” hơn.

Cần phân biệt ba tình huống:

| Tình huống | Cơ chế đáng quan tâm | Kết quả thường gặp |
| --- | --- | --- |
| Pair cụ thể và pair tổng quát khác nhau, ví dụ `String -> CustomerCode` và `String -> Object` | Thứ tự duyệt source/target hierarchy | Pair cụ thể có thể được xét trước pair tổng quát. |
| Hai converter cùng đăng ký `String -> CustomerCode` | Thứ tự ứng viên của cùng pair; conditional matching | Ứng viên phù hợp đầu tiên trong danh sách được chọn. |
| Converter có `matches(...)` trả false | Điều kiện của `ConditionalConverter` hoặc `ConditionalGenericConverter` | Converter bị bỏ qua; Spring tiếp tục tìm ứng viên khác. |

### 5.1. Cùng một pair: thứ tự đăng ký cần được hiểu đúng

Trong implementation `GenericConversionService` hiện hành, registry cho một pair lưu các converter trong cấu trúc deque; khi thêm converter, implementation đưa converter mới vào đầu danh sách. Việc tìm kiếm duyệt các ứng viên trong danh sách và lấy converter phù hợp đầu tiên.

Điều đó có nghĩa nếu nhiều converter cùng đăng ký pair `String -> CustomerCode`, converter đăng ký sau có thể đứng trước converter đăng ký trước trong implementation này. Nếu converter là conditional, Spring phải kiểm tra `matches(sourceType, targetType)`; ứng viên không thỏa điều kiện sẽ không được chọn.

**Không nên xây contract nghiệp vụ dựa vào thứ tự đăng ký ngẫu nhiên.** Thứ tự bên trong registry là chi tiết implementation; cấu hình bean hoặc component scan có thể làm thứ tự khởi tạo khó nhìn thấy. Nếu hai converter cùng pair có logic xung đột, hãy hợp nhất thành một converter có điều kiện rõ ràng hoặc thu hẹp cặp kiểu của từng converter.

### 5.2. Khác pair: thứ tự source hierarchy và target hierarchy mới là điểm chính

Xét hai cặp:

~~~text
Converter A: String -> CodeValue
Converter B: Object -> CustomerCode
Yêu cầu:     String -> CustomerCode
~~~

Không thể nhìn target và tuyên bố B luôn thắng vì target của B rất cụ thể. GenericConversionService duyệt hệ phân cấp **source trước**. Với source chính xác là `String`, converter A có thể được xét trước khi lookup chuyển sang source cha `Object`. Vì vậy, ưu tiên giữa các cặp không chỉ dựa vào target mà phụ thuộc thứ tự của cả hai hệ phân cấp.

Đây là lý do bài kiểm thử quan trọng hơn suy luận theo tên “specific” hay “generic”.

## 6. ConditionalConverter: quyết định theo metadata

`ConditionalConverter` cho phép một converter tự trả lời liệu nó có phù hợp với cặp kiểu hiện tại thông qua:

~~~java
boolean matches(
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Ví dụ, cùng chuyển từ `String` sang `LocalDate` nhưng chỉ muốn custom converter được dùng cho field có annotation đặc biệt. Converter có thể kiểm tra metadata đích trong `TypeDescriptor` rồi chỉ nhận trường hợp đúng.

Một `ConditionalGenericConverter` vừa khai báo cặp kiểu qua `getConvertibleTypes()`, vừa triển khai `matches(...)`. Đây là cách hữu ích khi:

- Cùng cặp kiểu nhưng quy tắc phụ thuộc annotation của field.
- Cần phân biệt loại dữ liệu hoặc metadata trên target.
- Converter tổng quát chỉ nên hoạt động với một nhóm domain cụ thể.
- Muốn custom converter nhường quyền cho ứng viên khác khi điều kiện không phù hợp.

Ví dụ minh họa:

~~~java
public final class ConditionalStringToCode
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(new ConvertiblePair(String.class, CodeValue.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        // Chỉ chạy khi matches(...) trả true.
        return createCode(source.toString(), targetType.getObjectType());
    }
}
~~~

Đây là đoạn minh họa về cấu trúc, không phải chương trình độc lập: `SpecialCode` và `createCode(...)` do ứng dụng định nghĩa. Nếu một converter conditional trả `false`, service có thể tiếp tục xét converter phù hợp khác trong quá trình lookup.

**Đừng dùng conditional để che giấu sự cạnh tranh không rõ ràng**. Điều kiện phải diễn đạt một quy tắc domain/metadata dễ hiểu và có test cho cả nhánh true lẫn false.

## 7. ConverterFactory và GenericConverter trong cuộc cạnh tranh

`ConverterFactory<S,R>` cũng được đăng ký thành adapter nội bộ và có một pair nguồn/kiểu giới hạn đích. Khi lookup, adapter factory có thể gọi `getConverter(targetType)` để lấy converter cụ thể cho target hiện tại; nếu factory hoặc converter sinh ra là conditional, điều kiện của nó cũng được xem xét.

Ví dụ:

~~~java
ConverterFactory<String, CodeValue> factory = ...;
Converter<String, CustomerCode> customer =
        factory.getConverter(CustomerCode.class);
~~~

Nếu target là `CustomerCode`, factory tạo converter phù hợp. Pair đăng ký của factory thường đại diện kiểu giới hạn `CodeValue`, vì vậy nó có thể được xét theo hệ phân cấp target khi yêu cầu một kiểu triển khai cụ thể.

`GenericConverter` có thể hỗ trợ nhiều pair và dùng `TypeDescriptor` trực tiếp, nên phù hợp khi thuật toán phụ thuộc metadata hoặc nhiều kiểu nguồn/đích. Nhưng **GenericConverter không mặc định có ưu tiên cao hơn hoặc thấp hơn ConverterFactory**. Cần xem pair nào khớp trước, điều kiện match và các ứng viên cùng pair.

## 8. Generic type: raw pair chưa phải toàn bộ câu chuyện

Hai collection có cùng raw class nhưng kiểu phần tử khác nhau:

~~~java
List<String>
List<Integer>
~~~

Nếu converter chỉ nhìn `Class` thô `List.class`, nó không thể phân biệt hai kiểu tham số hóa này. `TypeDescriptor` cung cấp metadata generic của property để converter có thể kiểm tra kiểu phần tử, annotation và thuộc tính khác.

Trong Spring `GenericConversionService`, converter có thể cần so khớp đầy đủ generic type. Các adapter cho `Converter`/`ConverterFactory` dựa trên generic signature; `GenericConverter` có thể kiểm tra `TypeDescriptor` trực tiếp. Với một số kiểu generic không thể phân giải đầy đủ, Spring có logic fallback riêng và hành vi đã được điều chỉnh theo phiên bản.

### Lưu ý thay đổi từ Spring 6.2.3

Mã nguồn Spring 6.2.x có nhánh fallback tương thích cho một số `ConverterAdapter` với generic type không thể phân giải, được ghi chú là fallback về hành vi trước 6.2.3. Vì vậy, khi converter của bạn dựa vào `List<?>`, raw type hoặc generic type không đầy đủ, hãy test trên đúng patch version đang sử dụng.

Đừng suy luận rằng hai converter đều đăng ký pair `Collection -> Collection` thì chắc chắn có thể phân biệt phần tử chỉ dựa vào raw pair. Dùng `TypeDescriptor` và test cụ thể với `List<String>`/`List<Integer>` nếu metadata generic quan trọng.

## 9. Cache và vòng đời của lookup

`GenericConversionService` cache kết quả tra cứu theo cặp descriptor source/target. Mục đích là không phải duyệt lại toàn bộ hệ phân cấp kiểu cho mọi lần convert giống nhau. Registry cũng quản lý việc invalidation cache khi converter được thêm hoặc loại bỏ.

Trong ứng dụng, nên:

- Đăng ký converter lúc khởi động hoặc ở giai đoạn cấu hình rõ ràng.
- Giữ ConversionService stateless và chia sẻ giữa các thread.
- Tránh thay đổi registry tùy tiện trong khi request đang chạy.
- Không giả định thứ tự đăng ký do component scan luôn ổn định nếu có nhiều converter cùng pair.
- Kiểm thử output thực tế của một cặp source/target sau khi toàn bộ configuration đã được nạp.

Việc cache không làm thay đổi nguyên tắc lookup: service vẫn cần chọn converter tương ứng với source/target và metadata. Nó chỉ giúp tái sử dụng kết quả phù hợp cho lần gọi sau.

## 10. Cách thiết kế để tránh xung đột converter

Khi có nhiều converter cho cùng vùng dữ liệu, hãy làm rõ ownership:

**Ưu tiên pair cụ thể** cho quy tắc riêng:

~~~java
Converter<String, CustomerCode>
Converter<String, OrderCode>
~~~

**Dùng converter tổng quát** khi thuật toán thực sự dùng chung và có thể xác định target chính xác:

~~~java
GenericConverter // String -> Object, có targetType kiểm soát
~~~

**Dùng ConditionalGenericConverter** khi việc chọn còn phụ thuộc annotation hoặc metadata:

~~~java
matches(sourceType, targetType)
~~~

Một số quy tắc thực hành:

1. Tránh đăng ký hai converter không tương thích cho cùng một pair.
2. Nếu phải có hai implementation cùng pair, dùng điều kiện rõ ràng và bảo đảm không có hai converter cùng trả true cho cùng metadata.
3. Không dựa vào thứ tự khởi tạo bean để chọn logic domain.
4. Đừng khai báo pair quá rộng như `Object -> Object` nếu converter không có khả năng xử lý mọi target.
5. Thu hẹp cặp kiểu của GenericConverter đến mức đủ cần thiết; đừng dùng wildcard pair để “bắt tất cả” rồi phải đoán target trong một đoạn code lớn.
6. Khi có nhiều context hoặc registry, kiểm tra converter đã được đăng ký vào đúng ConversionService đang được dùng.
7. Với generic collections, dùng TypeDescriptor thay vì chỉ so sánh raw Class.
8. Sau khi thay đổi dependency Spring, chạy lại test lựa chọn converter trên các source/target quan trọng.

## 11. Kiểm tra converter nào đang được chọn

`ConversionService` công khai các API như:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
~~~

`canConvert` không trả về tên converter được chọn. Nó trả lời liệu service có đường chuyển đổi cho cặp kiểu hay không.

Muốn biết converter cụ thể nào được gọi:

- Tạo output có dấu hiệu phân biệt trong test (như tiền tố `specific:` và `generic:` trong ví dụ).
- Dùng breakpoint trong `convert(...)` của từng converter.
- Với `GenericConverter`, log một mã định danh hoặc thông tin target descriptor ở mức debug nếu log không chứa dữ liệu nhạy cảm.
- Kiểm tra danh sách converter đã đăng ký qua cấu hình/implementation phù hợp; đừng parse chuỗi `toString()` làm API ổn định.

Không nên expose tên class converter như một phần API business response. Đây là thông tin để debug cấu hình nội bộ.

## 12. Bộ kiểm thử nên có

| Ca kiểm thử | Cấu hình | Điều phải xác minh |
| --- | --- | --- |
| Pair cụ thể so với pair tổng quát | `String -> CustomerCode` và `String -> Object` | Target CustomerCode dùng converter cụ thể. |
| Chỉ có converter tổng quát | `String -> Object` | Target con được xử lý đúng bởi GenericConverter. |
| Không hỗ trợ target | GenericConverter từ chối target | ConversionService báo không tìm được converter phù hợp. |
| Conditional true | `matches(...)` trả true | Converter conditional được chọn khi pair hợp lệ. |
| Conditional false | `matches(...)` trả false | Service xét ứng viên khác hoặc không tìm được. |
| Hai converter cùng pair | Hai implementation cùng `String -> CustomerCode` | Test hành vi theo cấu hình; loại bỏ phụ thuộc thứ tự nếu có thể. |
| Source subclass | Source là class triển khai/extends kiểu đăng ký | Kiểm tra quy tắc source hierarchy. |
| Target subclass/interface | Target nằm dưới class/interface được đăng ký | Kiểm tra target hierarchy. |
| Generic collections | `List<String>` và `List<Integer>` | Kiểm tra TypeDescriptor và generic matching. |
| Cache sau cấu hình | Đăng ký hoàn chỉnh trước khi convert | Kết quả không phụ thuộc thứ tự khởi tạo bất định. |

Với JUnit 5, một test output có thể xác minh converter được chọn:

~~~java
@Test
void concretePairIsChosenBeforeBroadTargetPair() {
    DefaultConversionService service = createService();

    CustomerCode result =
            service.convert("c-42", CustomerCode.class);

    assertEquals("specific:C-42", result.value());
}
~~~

Đây là đoạn trích test; `createService()` cần khởi tạo registry như ví dụ ở mục 4. Đối với trường hợp cùng pair, không chỉ assert converter “đăng ký sau” thắng rồi xem đó là contract. Nếu business cần một logic duy nhất, hãy chỉ đăng ký một ứng viên hoặc dùng conditional matching không chồng lấn.

## 13. Lỗi phổ biến

**Lỗi 1 — Nghĩ Converter luôn thắng GenericConverter.** Loại SPI không phải bảng ưu tiên. Phải kiểm tra ConvertiblePair, class hierarchy và điều kiện.

**Lỗi 2 — Chỉ nhìn kiểu đích.** Lookup duyệt hệ phân cấp source trước, rồi target; source specificity cũng ảnh hưởng thứ tự.

**Lỗi 3 — Đăng ký nhiều converter cùng pair và dựa vào XML order.** Implementation có thể có quy tắc thứ tự riêng; component scan còn làm thứ tự khởi tạo khó đoán. Hợp nhất logic hoặc dùng conditional criteria.

**Lỗi 4 — GenericConverter khai báo pair quá rộng.** Một converter `String -> Object` có thể được xét cho nhiều target. Nếu không kiểm tra `targetType` cẩn thận, nó có thể trả sai object hoặc ném exception ở target không hỗ trợ.

**Lỗi 5 — ConditionalConverter trả true quá rộng.** Điều kiện không đủ cụ thể có thể khiến converter cạnh tranh với các converter khác ở cùng pair. Test cả nhánh true/false.

**Lỗi 6 — Chỉ test canConvert.** `canConvert` không chứng minh converter cụ thể nào được chạy và không xác thực input value.

**Lỗi 7 — Bỏ qua TypeDescriptor.** Với generic collection hoặc annotation, so sánh raw Class có thể mất thông tin cần thiết.

**Lỗi 8 — Sửa registry trong lúc ứng dụng đang xử lý request.** Cache và registry phải được quản lý có chủ đích; đăng ký converter nên hoàn tất ở startup.

**Lỗi 9 — Cho rằng addConverter của DefaultConversionService thay thế mọi converter mặc định.** Nó bổ sung một converter vào registry; việc lựa chọn sau đó vẫn theo lookup rules và các converter sẵn có.

## 14. Checklist khi cần phân tích độ ưu tiên

1. Ghi rõ source type và target type thực tế, bao gồm generic/TypeDescriptor nếu có.
2. Liệt kê mọi `ConvertiblePair` có thể match, kể cả pair từ converter factory.
3. Vẽ source hierarchy và target hierarchy; nhớ lookup duyệt source candidate trước rồi target candidate.
4. Với các converter cùng pair, kiểm tra `ConditionalConverter.matches(...)` và thứ tự ứng viên của implementation đang dùng.
5. Không dùng loại SPI làm tiêu chí ưu tiên duy nhất.
6. Viết test thể hiện converter được chọn bằng kết quả có thể nhận biết.
7. Kiểm tra đúng Spring patch version của ứng dụng, đặc biệt nếu logic phụ thuộc generic matching hoặc fallback.
8. Thu hẹp converter tổng quát, loại bỏ các pair chồng lấn không có lý do.
9. Đảm bảo conversion error được xử lý trước khi gọi business service.
10. Chỉ khi quy tắc lựa chọn đã rõ và test ổn định mới dùng registry trong DataBinder/MVC hoặc application service.

### Kết luận

Spring không có một luật đơn giản rằng `Converter` luôn có độ ưu tiên cao hơn `GenericConverter`. Với `GenericConversionService`, lựa chọn dựa trên cặp source/target và thứ tự duyệt hệ phân cấp kiểu; pair cụ thể thường được xét trước pair tổng quát khi các source type giống nhau. Nếu nhiều converter cùng đăng ký một pair, conditional matching và thứ tự ứng viên cũng tham gia quyết định.

Muốn cấu hình dễ bảo trì, hãy đăng ký cặp cụ thể cho logic đặc thù, dùng converter tổng quát khi thực sự có thuật toán chung, và sử dụng conditional converter khi metadata làm thay đổi quy tắc. Quan trọng nhất là test converter được chọn trên đúng dependency version của ứng dụng, thay vì suy luận từ tên interface hoặc thứ tự file cấu hình.

### Tài liệu tham khảo chính thức

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — GenericConversionService source code](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java)
- [Spring Framework 6.2 — GenericConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [Spring Framework — ConditionalConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [Spring Framework — ConditionalGenericConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConditionalGenericConverter.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
