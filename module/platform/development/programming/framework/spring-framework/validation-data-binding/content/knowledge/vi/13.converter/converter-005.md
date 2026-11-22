# ConverterFactory cho một họ kiểu đích trong Spring

Trong Spring Core, `ConverterFactory<S, R>` là SPI dùng khi **một kiểu nguồn cần chuyển đổi thành nhiều kiểu đích có chung một kiểu cơ sở**. Thay vì viết một `Converter<S, T>` riêng cho từng kiểu đích, ta viết một factory nhận `Class<T>` và tạo converter thích hợp cho kiểu đích cụ thể đó.

Một ví dụ kinh điển là chuyển `String` thành nhiều enum: `Priority`, `OrderState`, `PaymentStatus`. Các enum đều có thể cùng triển khai một interface nghiệp vụ, chẳng hạn `CodeValue`. Factory nhận lớp enum cần tạo và trả converter chuyên xử lý lớp đó.

~~~text
                 ConverterFactory<String, CodeValue>
                              |
               +--------------+---------------+
               |              |               |
        getConverter(     getConverter(   getConverter(
          Priority)       OrderState)    PaymentStatus)
               |              |               |
        Converter<String, Priority>  ...  Converter<String, PaymentStatus>
~~~

Đề bài tập trung vào **họ kiểu đích**. Điểm cốt lõi không phải chỉ chuyển một chuỗi sang một enum, mà là giữ chung quy tắc chuyển đổi cho nhiều kiểu đích trong cùng một nhóm, đồng thời vẫn sử dụng được thông tin cụ thể của kiểu đích tại thời điểm tạo converter.

## 1. Hợp đồng của ConverterFactory

Spring định nghĩa interface trong package `org.springframework.core.convert.converter`:

~~~java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
~~~

Ý nghĩa các tham số generic:

| Thành phần | Ý nghĩa |
| --- | --- |
| `S` | Kiểu dữ liệu nguồn mà các converter của factory đọc vào. |
| `R` | Kiểu cơ sở hoặc kiểu giới hạn của **họ kiểu đích**. |
| `T extends R` | Kiểu đích cụ thể mà lần gọi `getConverter(...)` muốn chuyển đổi sang. |
| `targetType` | Đối tượng `Class<T>` mô tả kiểu đích cụ thể. |
| Giá trị trả về | Một `Converter<S, T>` chuyên chuyển từ `S` sang đúng `T` đó. |

Ví dụ:

~~~java
ConverterFactory<String, Enum> factory = ...;

Converter<String, Priority> priorityConverter =
        factory.getConverter(Priority.class);

Converter<String, OrderState> stateConverter =
        factory.getConverter(OrderState.class);
~~~

Hai converter có cùng kiểu nguồn `String` nhưng kiểu đích khác nhau. Factory biết cần xử lý enum nào nhờ `targetType`, vì vậy có thể sử dụng metadata hoặc hằng số của đúng enum đích.

Trong ứng dụng thực tế, không nhất thiết phải dùng `Enum` làm `R`. Có thể dùng một interface do ứng dụng định nghĩa như `CodeValue`, một lớp cơ sở như `Number`, hoặc một kiểu cha khác mà các kiểu đích cùng mở rộng/triển khai.

## 2. Khi nào nên dùng ConverterFactory?

Hãy xem ba nhu cầu chuyển đổi:

**Trường hợp A — một cặp kiểu nguồn/đích duy nhất**

Chuyển `String` sang `UUID`:

~~~java
Converter<String, UUID>
~~~

Một `Converter` đơn giản thường là đủ.

**Trường hợp B — nhiều kiểu đích cùng họ**

Chuyển `String` sang nhiều enum:

~~~java
ConverterFactory<String, Enum>
~~~

Một factory cung cấp converter tương ứng cho từng enum. Đây là trường hợp `ConverterFactory` phù hợp.

**Trường hợp C — nhiều cặp kiểu và cần metadata phong phú**

Ví dụ chuyển array thành collection, cần biết kiểu phần tử của collection đích, hoặc chuyển đổi phụ thuộc annotation/field context:

~~~java
GenericConverter
~~~

`GenericConverter` cung cấp cả `TypeDescriptor` nguồn và đích, cũng như tập các cặp kiểu mà nó hỗ trợ. Khi cần nhiều kiểu nguồn/đích hoặc thông tin về field/generic type, đây thường là lựa chọn phù hợp hơn.

Bảng quyết định:

| Nhu cầu | SPI nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ một kiểu nguồn và một kiểu đích | `Converter<S, T>` | Hợp đồng đơn giản, mạnh về kiểu. |
| Một kiểu nguồn chuyển sang nhiều kiểu đích có chung kiểu cơ sở | `ConverterFactory<S, R>` | `getConverter(Class<T>)` nhận kiểu đích cụ thể. |
| Nhiều cặp nguồn/đích, cần descriptor hoặc metadata | `GenericConverter` | Có `TypeDescriptor` và tập `ConvertiblePair`. |
| Chỉ áp dụng khi một điều kiện về metadata được thỏa mãn | `ConditionalConverter` hoặc `ConditionalGenericConverter` | Cho phép kiểm tra điều kiện trước khi converter được chọn. |

Không cần dùng `ConverterFactory` chỉ vì có nhiều dòng code. Nếu mỗi kiểu đích có quy tắc độc lập và không chia sẻ cùng họ, các `Converter` riêng có thể rõ ràng hơn.

## 3. Ví dụ nghiệp vụ: một họ enum có mã riêng

Giả sử hệ thống nhận mã viết tắt từ form hoặc cấu hình:

- `Priority.HIGH` có mã `H`.
- `Priority.LOW` có mã `L`.
- `OrderState.OPEN` có mã `O`.
- `OrderState.CLOSED` có mã `C`.

Cả hai enum đều triển khai interface `CodeValue`:

~~~java
public interface CodeValue {
    String code();
}
~~~

Factory có thể khai báo:

~~~java
public class StringToCodeValueConverterFactory
        implements ConverterFactory<String, CodeValue> {
    // ...
}
~~~

Khi `getConverter(Priority.class)` được gọi, factory tạo converter chỉ biết về `Priority`. Khi `getConverter(OrderState.class)` được gọi, factory tạo converter chỉ biết về `OrderState`. Quy tắc chung như trim input, so sánh không phân biệt hoa/thường, và báo lỗi khi không tìm thấy mã có thể được triển khai một lần.

Điểm quan trọng: `R` là **giới hạn kiểu đích**, không phải kiểu nguồn. Trong ví dụ này, nguồn là `String`, còn họ đích là các kiểu triển khai `CodeValue`.

## 4. Chương trình Java 17+ hoàn chỉnh với Spring

Ví dụ dưới đây sử dụng Spring Framework `6.2.0`. Nó đăng ký một `ConverterFactory<String, CodeValue>` vào `DefaultConversionService` rồi chuyển đổi sang hai enum khác nhau.

Cấu trúc dự án:

~~~text
converter-factory-demo/
├── pom.xml
└── src/main/java/example/ConverterFactoryDemo.java
~~~

### 4.1. Tạo pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>converter-factory-demo</artifactId>
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
        </plugins>
    </build>
</project>
~~~

### 4.2. Tạo ConverterFactoryDemo.java

~~~java
package example;

import java.util.Locale;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.converter.ConverterFactory;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConverterFactoryDemo {

    public interface CodeValue {
        String code();
    }

    public enum Priority implements CodeValue {
        HIGH("H"),
        LOW("L");

        private final String code;

        Priority(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public enum OrderState implements CodeValue {
        OPEN("O"),
        CLOSED("C");

        private final String code;

        OrderState(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public static final class StringToCodeValueConverterFactory
            implements ConverterFactory<String, CodeValue> {

        @Override
        public <T extends CodeValue> Converter<String, T> getConverter(
                Class<T> targetType) {

            if (!targetType.isEnum()) {
                throw new IllegalArgumentException(
                        "Target type must be an enum: " + targetType.getName());
            }

            return source -> {
                String normalized = source.trim()
                        .toUpperCase(Locale.ROOT);

                for (Object constant : targetType.getEnumConstants()) {
                    CodeValue candidate = (CodeValue) constant;

                    if (candidate.code().equalsIgnoreCase(normalized)) {
                        return targetType.cast(candidate);
                    }
                }

                throw new IllegalArgumentException(
                        "Unknown code '" + source
                                + "' for " + targetType.getSimpleName());
            };
        }
    }

    public static void main(String[] args) {
        DefaultConversionService registry =
                new DefaultConversionService();

        registry.addConverterFactory(
                new StringToCodeValueConverterFactory());

        ConversionService conversionService = registry;

        Priority priority =
                conversionService.convert(" h ", Priority.class);

        OrderState state =
                conversionService.convert("o", OrderState.class);

        System.out.println("priority=" + priority);
        System.out.println("state=" + state);
        System.out.println("canConvertToPriority="
                + conversionService.canConvert(
                        String.class, Priority.class));
        System.out.println("canConvertToState="
                + conversionService.canConvert(
                        String.class, OrderState.class));
    }
}
~~~

### 4.3. Biên dịch và chạy

Cần JDK 17+ và Maven. Mở terminal tại thư mục `converter-factory-demo`:

~~~bash
mvn -q package
java -cp target/classes;... example.ConverterFactoryDemo
~~~

Lệnh `java -cp` trong ví dụ cần classpath chứa các dependency Maven; cách chạy ngắn và đúng cho dự án trên là thêm `exec-maven-plugin` vào `pom.xml`, rồi dùng:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ConverterFactoryDemo
~~~

Để chạy được lệnh trên, bổ sung plugin vào phần `build/plugins` của pom:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
~~~

Kết quả stdout:

~~~text
priority=HIGH
state=OPEN
canConvertToPriority=true
canConvertToState=true
~~~

Giải thích:

1. `DefaultConversionService` là một implementation có sẵn của `ConversionService` và registry; ta đăng ký factory bằng `addConverterFactory(...)`.
2. Khi chuyển `" h "` sang `Priority`, conversion service chọn converter factory đã đăng ký và yêu cầu converter dành riêng cho `Priority.class`. Converter trim chuỗi, chuẩn hóa và tìm mã `H`.
3. Khi chuyển `"o"` sang `OrderState`, cùng factory được dùng nhưng `targetType` là `OrderState.class`; converter tìm mã `O`.
4. Hai kiểu đích không cần hai lớp `Converter` được đăng ký thủ công. Factory tạo converter phù hợp dựa trên `targetType`.
5. `canConvert(...)` chỉ cho biết có converter phù hợp theo metadata kiểu; nó **không kiểm tra trước giá trị cụ thể**. Ví dụ `canConvert(String.class, Priority.class)` có thể là `true` dù chuỗi `"X"` không phải mã Priority hợp lệ.

Lưu ý về lệnh chạy: nếu dùng `exec-maven-plugin` như phần bổ sung trên, hãy đặt `mainClass` trong cấu hình plugin hoặc truyền `-Dexec.mainClass` như lệnh ở trên. Không dùng classpath chỉ có `target/classes` vì Spring dependency chưa nằm trong classpath.

## 5. Đọc kỹ generic type: vì sao R là kiểu cơ sở?

Một khai báo:

~~~java
ConverterFactory<String, Number>
~~~

có nghĩa factory chuyển từ `String` sang nhiều kiểu con của `Number`, ví dụ `Integer`, `Long`, `Double`. Nó **không có nghĩa** factory chuyển sang đúng kiểu `Number` trong mọi lời gọi.

Khi gọi:

~~~java
Converter<String, Integer> toInteger =
        factory.getConverter(Integer.class);

Converter<String, Long> toLong =
        factory.getConverter(Long.class);
~~~

`T` lần lượt được suy luận là `Integer` và `Long`, đều thỏa `T extends Number`.

Nếu viết:

~~~java
ConverterFactory<String, Integer>
~~~

thì kiểu đích được giới hạn hẹp hơn nhiều; không thể dùng factory đó để trả `Converter<String, Long>` vì `Long` không phải kiểu con của `Integer`.

### Factory phải sử dụng targetType

Trong `getConverter(Class<T> targetType)`, tham số đích cho phép factory:

- Tra cứu enum constant hoặc metadata của lớp đích.
- Chọn thuật toán chuyển đổi phù hợp.
- Tạo converter chuyên biệt cho đúng target.
- Từ chối kiểu đích không thuộc nhóm được hỗ trợ.

Nếu factory bỏ qua `targetType` và luôn tạo converter cho một enum cố định, nó sẽ không còn đáp ứng mục đích “một họ kiểu đích”.

### Vì sao không tự cast tùy tiện?

Generic signature bảo đảm ở mức compile-time rằng `T extends R`, nhưng **không tự chứng minh mọi subclass đều thuộc cùng cấu trúc nội bộ**. Nếu factory dựa vào giả định enum, cần kiểm tra `targetType.isEnum()` trước khi gọi `getEnumConstants()`. Nếu một interface có thể được implement bởi class không phải enum, phải xử lý trường hợp đó rõ ràng như ví dụ.

## 6. Đăng ký factory vào ConversionService

`ConverterFactory` không tự chạy khi một method Java được gọi. Nó phải được đăng ký vào một registry hoặc được cấu hình vào Spring container theo cách phù hợp.

### 6.1. Sử dụng ConversionService trực tiếp

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverterFactory(
        new StringToCodeValueConverterFactory());

Priority priority =
        conversionService.convert("H", Priority.class);
~~~

Đây là cách đơn giản để dùng converter trong code bất kỳ, không cần Spring MVC.

### 6.2. Dùng trong DataBinder

`DataBinder` có thể nhận `ConversionService` để chuyển các property value từ nguồn sang kiểu thuộc tính:

~~~java
ProductForm form = new ProductForm();

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverterFactory(
        new StringToCodeValueConverterFactory());

DataBinder binder = new DataBinder(form, "product");
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("priority", "H");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Không sử dụng dữ liệu để thực hiện nghiệp vụ.
}
~~~

Đây là **đoạn trích minh họa**; `ProductForm` cần có property `priority` thuộc kiểu enum phù hợp, cùng getter/setter. Những kiểu import liên quan gồm `DataBinder`, `MutablePropertyValues` và `BindingResult`.

Nếu converter không chuyển được mã, binder ghi nhận lỗi binding/conversion trong `BindingResult`. Sau khi bind, ứng dụng cần kiểm tra `hasErrors()` trước khi tiếp tục. Converter chỉ đảm nhiệm chuyển đổi kiểu, không thay thế validation của giá trị hay kiểm tra nghiệp vụ.

### 6.3. Đăng ký trong Spring MVC

Trong ứng dụng Spring MVC, có thể thêm converter vào registry của MVC:

~~~java
// Đoạn trích trong @Configuration.
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverterFactory(
            new StringToCodeValueConverterFactory());
}
~~~

`FormatterRegistry` có khả năng đăng ký `Converter`, `ConverterFactory` và `GenericConverter`. MVC sử dụng hệ thống conversion/formatting trong các tình huống bind request parameter hoặc model attribute có cấu hình thích hợp. Đây là cấu hình dành cho **property binding của MVC**; không nên giả định nó tự biến JSON deserialization qua Jackson thành cùng một pipeline.

Với một ứng dụng Spring Boot, hãy đăng ký factory tại nơi cấu hình conversion phù hợp với phiên bản và loại ứng dụng. Tránh tạo một `DefaultConversionService` riêng cho từng request; service được thiết kế để chia sẻ và sử dụng lại.

## 7. Xử lý giá trị không hợp lệ và null

Hợp đồng `Converter` yêu cầu phương thức `convert(S source)` nhận một source không null trong luồng thông thường của Spring ConversionService. Khi dữ liệu nguồn không hợp lệ, converter nên ném unchecked exception; thông thường là `IllegalArgumentException` để biểu thị không thể chuyển đổi.

Ví dụ:

~~~java
throw new IllegalArgumentException(
        "Unknown code '" + source + "'");
~~~

Khi được gọi qua `ConversionService`, ngoại lệ chuyển đổi có thể được bọc trong một `ConversionFailedException` hoặc dạng `ConversionException` phù hợp với ngữ cảnh. Khi dùng qua `DataBinder`, lỗi conversion có thể được ghi thành `FieldError` với mã như `typeMismatch`.

Không trả về `null` để âm thầm biểu thị mọi mã không hợp lệ trừ khi contract của ứng dụng quy định rõ điều đó. Giá trị sai nên tạo lỗi có thể quan sát và xử lý.

### Null source khác với empty string

Cần phân biệt:

| Input | Ý nghĩa thường gặp |
| --- | --- |
| `null` | Không có đối tượng nguồn để chuyển đổi; `ConversionService` có cơ chế xử lý null riêng. |
| `""` | Chuỗi rỗng; converter nhận chuỗi rỗng và phải xác định đây là mã không hợp lệ, giá trị mặc định hay trạng thái đặc biệt theo contract. |
| `"  "` | Chuỗi chứa khoảng trắng; converter có thể trim, rồi xử lý như rỗng nếu quy tắc cho phép. |
| `"H"` | Mã cụ thể hợp lệ nếu kiểu đích có mã tương ứng. |
| `"UNKNOWN"` | Chuỗi không tìm thấy mã; converter nên báo lỗi chuyển đổi. |

Không dùng `source.trim()` trước khi xử lý null nếu converter có thể được gọi trực tiếp bên ngoài ConversionService. Trong hợp đồng chuẩn, converter không nhận null, nhưng nên ghi rõ giả định và nếu method public được dùng trực tiếp thì có thể kiểm tra đầu vào phù hợp.

### Không sử dụng Locale mặc định cho mã kỹ thuật

Nếu chuẩn hóa ký tự, tránh phụ thuộc locale của máy chạy. Dùng:

~~~java
source.toUpperCase(Locale.ROOT)
~~~

thay vì `toUpperCase()` không có tham số. Điều này đặc biệt quan trọng với mã kỹ thuật không phụ thuộc ngôn ngữ người dùng. Nếu quy tắc mã có ngữ nghĩa locale thật, hãy truyền locale như một phần của contract thay vì phụ thuộc cấu hình toàn JVM.

## 8. Vòng đời và thread safety

Một `ConversionService` thường được tạo khi ứng dụng khởi động và được chia sẻ giữa nhiều thread. Spring mô tả `ConversionService` là một đối tượng stateless theo thiết kế, phù hợp để chia sẻ. Factory cũng nên được triển khai như một thành phần **không giữ mutable state theo request**.

Thực hành tốt:

- Factory không giữ dữ liệu thay đổi theo lần convert.
- Converter trả về từ factory nên bất biến hoặc an toàn khi dùng đồng thời.
- Không cache kết quả theo input mutable mà không có chiến lược đồng bộ và giới hạn bộ nhớ.
- Metadata phụ thuộc `targetType` nên được tính khi gọi `getConverter` rồi giữ trong converter bất biến nếu điều đó hữu ích.
- Tránh thay đổi registry sau khi service đã được sử dụng trong ứng dụng, trừ khi API/cấu hình được thiết kế rõ cho việc đó.

Ví dụ trong chương trình, converter được trả về đóng trên `targetType`. `targetType` là đối tượng `Class` bất biến, nên việc tham chiếu nó không tạo trạng thái thay đổi theo request.

## 9. So sánh Converter, ConverterFactory và GenericConverter sâu hơn

| Đặc điểm | Converter | ConverterFactory | GenericConverter |
| --- | --- | --- | --- |
| Kiểu nguồn | Một `S` | Một `S` | Nhiều kiểu nguồn qua cặp type |
| Kiểu đích | Một `T` | Một họ `T extends R` | Nhiều kiểu đích qua cặp type |
| Nhận target Class | Không trong method convert | Có trong `getConverter(Class<T>)` | Có `TypeDescriptor` khi convert |
| Có metadata field/generic | Không trực tiếp | Không trực tiếp | Có qua `TypeDescriptor` |
| Độ phức tạp | Thấp | Trung bình | Cao hơn |
| Ví dụ phù hợp | String -> UUID | String -> mọi enum trong một họ | Array -> nhiều kiểu collection |

Một nguyên tắc hữu ích: **hãy chọn SPI đơn giản nhất đáp ứng được mô hình chuyển đổi**. Dùng `ConverterFactory` khi sự khác nhau giữa các converter chủ yếu phụ thuộc vào kiểu đích trong cùng một họ. Dùng `GenericConverter` khi logic phải đọc metadata phong phú hơn hoặc hỗ trợ nhiều cặp nguồn/đích không thể biểu diễn gọn bằng một `S` và một `R`.

## 10. Lỗi thường gặp

**Lỗi 1 — Đảo S và R.**

~~~java
ConverterFactory<CodeValue, String>
~~~

Khai báo này có nghĩa nguồn là `CodeValue`, kiểu đích là `String`. Nếu mục tiêu là đọc mã `String` để tạo enum, phải là `ConverterFactory<String, CodeValue>`.

**Lỗi 2 — Không dùng targetType.**

Nếu converter luôn trả `Priority` dù caller yêu cầu `OrderState`, factory không đáp ứng generic contract và có thể gây lỗi kiểu lúc chạy. Hãy dùng `targetType` để tìm metadata đích và trả converter đúng `T`.

**Lỗi 3 — Trả converter có generic không khớp.**

Không ép `Converter<String, Priority>` thành `Converter<String, OrderState>`. Để compiler kiểm tra quan hệ generic và tránh raw type/cast không cần thiết.

**Lỗi 4 — Giả định enum luôn dùng name().**

`Enum.valueOf(...)` chỉ tìm theo tên constant, ví dụ `HIGH`. Nếu wire format dùng mã `H`, cần tra cứu metadata code như ví dụ `CodeValue`.

**Lỗi 5 — Không xử lý code lạ.**

Không tìm thấy code phải có hành vi rõ ràng: ném exception conversion, trả lỗi validation thích hợp hoặc áp dụng default được contract cho phép. Đừng âm thầm trả enum đầu tiên.

**Lỗi 6 — Dùng locale mặc định.**

Mã kỹ thuật dùng để trao đổi giữa hệ thống không nên thay đổi kết quả theo locale mặc định của máy. Dùng `Locale.ROOT` khi chuẩn hóa mã ASCII không phụ thuộc ngôn ngữ.

**Lỗi 7 — Tạo ConversionService trên mỗi lần gọi.**

Làm như vậy tốn chi phí khởi tạo và đăng ký converter, đồng thời phân tán cấu hình. Hãy cấu hình service dùng chung trong application context hoặc một nơi khởi tạo phù hợp.

**Lỗi 8 — Coi canConvert là kiểm tra giá trị.**

`canConvert(String.class, Priority.class)` trả lời về khả năng có converter theo kiểu; nó không chứng minh mọi chuỗi đều là mã hợp lệ. Chỉ lần `convert(...)` với giá trị cụ thể mới thực thi quy tắc dữ liệu.

**Lỗi 9 — Cho rằng ConverterFactory tự đăng ký.**

Việc implement interface không làm Spring tự phát hiện mọi class. Phải đăng ký vào `ConverterRegistry`/`ConversionService` hoặc cấu hình trong formatter registry phù hợp.

**Lỗi 10 — Đưa logic nghiệp vụ quá lớn vào converter.**

Converter nên chuyển biểu diễn dữ liệu giữa các kiểu. Không nên truy vấn DB, kiểm tra quyền hoặc thay đổi trạng thái domain trong `convert(...)`. Những việc này thuộc service/application layer.

## 11. Cách kiểm thử một ConverterFactory

Kiểm thử nên xác minh cả **nhiều kiểu đích** và **dữ liệu sai**.

Ví dụ với JUnit 5:

~~~java
// Đoạn trích trong test đã import JUnit 5 assertions.
DefaultConversionService service = new DefaultConversionService();
service.addConverterFactory(new StringToCodeValueConverterFactory());

assertEquals(Priority.HIGH,
        service.convert("H", Priority.class));

assertEquals(OrderState.OPEN,
        service.convert("O", OrderState.class));

assertThrows(ConversionException.class,
        () -> service.convert("unknown", Priority.class));
~~~

`ConversionException` là lớp cơ sở trong hệ thống conversion của Spring; kiểm thử chính xác subtype có thể gắn với implementation/đường gọi đang dùng, nên assertion trên dùng kiểu cha để không phụ thuộc wrapper cụ thể. Đoạn test là minh họa, cần thêm dependency JUnit và import phù hợp.

Một bộ test thực tế nên gồm:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Một mã hợp lệ cho enum thứ nhất | Trả đúng constant của enum thứ nhất. |
| Một mã hợp lệ cho enum thứ hai | Cùng factory vẫn trả đúng constant của enum thứ hai. |
| Mã viết thường | Xử lý theo chính sách case-insensitive nếu factory đã quy định. |
| Có khoảng trắng đầu/cuối | Trim theo contract, hoặc từ chối nếu contract không cho phép. |
| Mã không tồn tại | Ném lỗi conversion. |
| target type không thuộc họ | Factory từ chối rõ ràng. |
| Kiểu nguồn khác `String` | Chỉ convert nếu có một converter khác đăng ký; factory này không nhận nó. |
| Gọi đồng thời nhiều thread | Kết quả ổn định, không phụ thuộc state mutable dùng chung. |

Ngoài unit test trực tiếp converter, cần integration test cho nơi sử dụng nó: `DataBinder`, Spring MVC form binding hoặc service dùng `ConversionService`. Nếu converter dùng trong form, kiểm tra `BindingResult` có lỗi khi giá trị không hợp lệ và xác minh service không được gọi khi bind thất bại.

## 12. Quy trình triển khai trong ứng dụng

1. Xác định **kiểu nguồn S** và họ kiểu đích có **kiểu cơ sở R** chung.
2. Viết `ConverterFactory<S, R>`, triển khai `getConverter(Class<T>)` để tạo converter đúng target.
3. Định nghĩa quy tắc rõ cho chuẩn hóa input, dữ liệu thiếu, mã không hợp lệ và kiểu đích không hỗ trợ.
4. Đảm bảo converter/factory an toàn khi được chia sẻ giữa nhiều thread.
5. Đăng ký factory vào `ConversionService` hoặc `FormatterRegistry` đúng nơi ứng dụng dùng.
6. Dùng `ConversionService.convert(...)` hoặc để `DataBinder` sử dụng conversion service khi bind thuộc tính.
7. Kiểm tra lỗi conversion và validation trước khi chuyển object sang nghiệp vụ ghi dữ liệu.
8. Test ít nhất hai kiểu đích trong cùng họ và cả nhánh dữ liệu không hợp lệ.

### Tài liệu Spring chính thức

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework 6.2 — `ConverterFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/converter/ConverterFactory.html)
- [Spring Framework 6.2 — `ConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — `DefaultConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Framework 6.2 — `GenericConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
