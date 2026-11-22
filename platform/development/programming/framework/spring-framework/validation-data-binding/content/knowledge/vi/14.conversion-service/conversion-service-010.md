# ConverterNotFoundException, ConversionFailedException và TypeMismatchException trong Spring

Khi Spring chuyển một giá trị từ kiểu nguồn sang kiểu đích, lỗi có thể xuất hiện ở nhiều giai đoạn khác nhau. Ba exception thường gặp là:

- **`ConverterNotFoundException`**: `ConversionService` không tìm được converter phù hợp cho cặp kiểu nguồn → kiểu đích.
- **`ConversionFailedException`**: Spring đã tìm thấy và gọi được conversion path, nhưng lần chuyển đổi **thực tế thất bại**.
- **`TypeMismatchException`**: thao tác **gán giá trị vào một bean property** thất bại do kiểu dữ liệu không phù hợp. Đây là exception ở tầng property access; trong một số trường hợp nó bao bọc lỗi chuyển đổi bên dưới.

Điểm quan trọng: ba tên này **không nằm trong cùng một nhánh kế thừa**. Hai exception đầu thuộc package `org.springframework.core.convert`; exception thứ ba thuộc `org.springframework.beans` và là một loại `PropertyAccessException`. Trong các luồng binding, lỗi tầng conversion có thể được bao bọc hoặc chuyển thành lỗi property access/field error để ứng dụng xử lý.

Bài này hướng dẫn phân biệt đúng nguyên nhân, đọc exception chain, tái hiện lỗi bằng Java 17+ và `ConversionService`/`BeanWrapper`/`DataBinder`, sau đó chọn cách khắc phục tương ứng.

## 1. Vị trí của ba exception trong kiến trúc Spring

Có thể phân lớp như sau:

~~~text
org.springframework.core.convert
          |
          v
   ConversionException
       /          \
      v            v
ConverterNotFoundException   ConversionFailedException


org.springframework.beans
          |
          v
      BeansException
          |
          v
  PropertyAccessException
          |
          v
   TypeMismatchException
          |
          v
 ConversionNotSupportedException (một subclass cụ thể)
~~~

Đây là sơ đồ rút gọn để thể hiện các quan hệ liên quan:

| Exception | Package | Superclass trực tiếp | Ý nghĩa chính |
| --- | --- | --- | --- |
| `ConverterNotFoundException` | `org.springframework.core.convert` | `ConversionException` | Không có converter phù hợp để thực hiện yêu cầu |
| `ConversionFailedException` | `org.springframework.core.convert` | `ConversionException` | Có conversion path nhưng converter/cách chuyển đổi thất bại |
| `TypeMismatchException` | `org.springframework.beans` | `PropertyAccessException` | Không thể gán giá trị theo kiểu mà bean property yêu cầu |

**Đừng suy luận rằng `TypeMismatchException` kế thừa `ConversionException`.** Hai nhánh tách biệt. Trong một thao tác gán bean, Spring có thể chuyển lỗi conversion thành lỗi property access, nhưng điều đó là quan hệ **bọc/chuyển tiếp khi xử lý lỗi**, không phải quan hệ kế thừa giữa hai lớp.

Một subclass quan trọng là `ConversionNotSupportedException`: nó kế thừa `TypeMismatchException` và mô tả tình huống không có editor/converter phù hợp cho bean property. Trong khi đó, `ConverterNotFoundException` là lỗi của `ConversionService` khi tra cứu converter. Hai tên gần giống nhau nhưng khác package và tầng xử lý.

## 2. ConverterNotFoundException — không tìm thấy đường chuyển đổi

### 2.1. Khi nào xảy ra?

`ConverterNotFoundException` được ném khi `ConversionService` được yêu cầu chuyển đổi một cặp kiểu, nhưng không tìm thấy converter phù hợp để xử lý:

~~~java
conversionService.convert(source, TargetType.class);
~~~

Ví dụ có một kiểu domain:

~~~java
public record CustomerReference(String value) {
}
~~~

Nếu ứng dụng yêu cầu chuyển `String` sang `CustomerReference` nhưng `ConversionService` hiện tại không có converter, editor hay convention conversion tương ứng, Spring không biết phải tạo object đích như thế nào.

Ví dụ này giả định `CustomerReference` không có constructor/factory phù hợp mà cơ chế chuyển đổi mặc định có thể tự sử dụng. Nếu kiểu có `valueOf(String)`, `of(String)` hoặc constructor nhận `String`, converter mặc định/convention converter có thể xử lý được và exception sẽ không xuất hiện.

### 2.2. Đọc thông tin exception

`ConverterNotFoundException` cung cấp:

- `getSourceType()`: `TypeDescriptor` của kiểu nguồn được yêu cầu.
- `getTargetType()`: `TypeDescriptor` của kiểu đích.
- `getMessage()`: mô tả lỗi phục vụ chẩn đoán.

Các thông tin này cho biết **cặp kiểu nào chưa có đường chuyển đổi**, giúp kiểm tra registry nhanh hơn so với chỉ đọc một dòng stack trace.

Ví dụ thông điệp có thể mang ý nghĩa “không tìm thấy converter từ `java.lang.String` sang `CustomerReference`”. Nội dung chính xác có thể thay đổi theo phiên bản, không nên so sánh chuỗi message trong test nếu không có lý do.

### 2.3. Cách khắc phục

**Bổ sung Converter phù hợp** là cách thường dùng:

~~~java
public final class StringToCustomerReferenceConverter
        implements Converter<String, CustomerReference> {

    @Override
    public CustomerReference convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Reference is required");
        }
        return new CustomerReference(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Đây là **đoạn class minh họa**, cần import `org.springframework.core.convert.converter.Converter`, `java.util.Locale` và domain record. Converter chỉ nhận giá trị non-null theo hợp đồng `ConversionService`; việc kiểm tra `source == null` trong ví dụ là phòng vệ dư thừa, còn chính sách giá trị rỗng là lựa chọn nghiệp vụ.

Sau đó đăng ký vào registry:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCustomerReferenceConverter());

CustomerReference reference =
        service.convert(" ab-123 ", CustomerReference.class);
~~~

Đoạn trên là phần code minh họa cần các import Spring và converter đã khai báo. `DefaultConversionService` vừa giữ các converter chuẩn, vừa cho phép thêm converter tùy chỉnh.

**Kiểm tra đúng source/target type:** đôi khi ứng dụng đã đăng ký converter nhưng chữ ký kiểu không khớp, ví dụ chỉ có `Converter<String, Long>` nhưng dữ liệu cần `String -> CustomerReference`. Một converter cho `List<String>` cũng không tự động xử lý mọi trường hợp `String -> List<CustomerReference>` nếu generic element/type descriptor không được mô tả phù hợp.

Các hướng kiểm tra:

1. Cặp kiểu nguồn/đích thực tế là gì? Đọc `getSourceType()` và `getTargetType()`.
2. Converter có được thêm vào đúng `ConversionService` đang được dùng không?
3. Converter có được cấu hình vào đúng Spring `ApplicationContext` hoặc binder không?
4. Chữ ký generic/`TypeDescriptor` có mô tả đúng kiểu collection, map, annotation và nested type không?
5. Có một conversion path khác bị thiếu ở giữa nhiều bước chuyển đổi không?

## 3. ConversionFailedException — converter tồn tại nhưng chuyển đổi thất bại

### 3.1. Khác với ConverterNotFoundException

Khi Spring tìm được converter nhưng lúc gọi conversion gặp giá trị không hợp lệ hoặc lỗi trong logic converter, `ConversionFailedException` có thể được ném.

Ví dụ:

~~~java
Integer quantity = conversionService.convert("abc", Integer.class);
~~~

Một `ConversionService` mặc định có thể chuyển `String` sang `Integer`. Vì vậy đây **không phải** lỗi thiếu converter. Lỗi xảy ra khi converter số cố parse `"abc"` và thất bại (thường do `NumberFormatException` ở cause chain).

Ví dụ khác là converter tùy chỉnh ném `IllegalArgumentException` khi mã không thỏa quy tắc định dạng.

### 3.2. Thông tin có thể đọc

`ConversionFailedException` kế thừa `ConversionException` và cung cấp:

- `getSourceType()`: kiểu nguồn.
- `getTargetType()`: kiểu đích.
- `getValue()`: giá trị đầu vào gây lỗi.
- `getCause()`: nguyên nhân gốc hoặc exception mà converter ném ra.

Khi debug, hãy xem **source type, target type, giá trị và cause**. Giá trị trong log cần được cân nhắc che bớt nếu có thể chứa dữ liệu cá nhân, token, mật khẩu hoặc thông tin nhạy cảm.

### 3.3. Tình huống thường gặp

| Giá trị nguồn | Kiểu đích | Lý do có thể thất bại |
| --- | --- | --- |
| `"abc"` | `Integer` | Không phải biểu diễn số nguyên |
| `"2026-19-45"` | `LocalDate` | Thành phần ngày/tháng không hợp lệ |
| `"maybe"` | `Boolean` | Không theo quy tắc parse boolean đang dùng |
| `"AB-12"` | `CustomerReference` | Converter custom yêu cầu dạng `AA-999` |
| Collection có phần tử sai kiểu | `List<Integer>` | Một phần tử không convert được sang kiểu đích |

Không phải mọi giá trị sai đều nhất thiết xuất hiện dưới đúng cùng một lớp exception tại mọi API. `ConversionService` trực tiếp thường đưa ra `ConversionFailedException` khi conversion execution thất bại; bean binding có thể bọc lỗi trong exception khác hoặc lưu vào `BindingResult`.

### 3.4. Cách khắc phục

- **Sửa dữ liệu nguồn:** kiểm tra input, định dạng, miền giá trị và locale.
- **Sửa converter:** xử lý quy tắc parse, validation cơ bản của biểu diễn và exception có ý nghĩa.
- **Bổ sung message lỗi:** giữ thông tin type mismatch để UI chỉ rõ field không hợp lệ.
- **Không nuốt lỗi:** không trả một giá trị mặc định âm thầm nếu việc mất dữ liệu làm sai nghiệp vụ.
- **Phân biệt conversion với validation:** chuỗi `"15"` có thể chuyển thành số 15 thành công nhưng vẫn không đạt điều kiện nghiệp vụ `quantity >= 20`.

Một `Converter` thường nên ném `IllegalArgumentException` để báo nguồn không hợp lệ; `ConversionService` bao quanh lỗi chuyển đổi bằng `ConversionFailedException` và giữ cause. Trong converter không nên thực hiện truy vấn database hoặc kiểm tra quyền phức tạp; các việc ấy phù hợp hơn ở service/validator.

## 4. TypeMismatchException — lỗi gán giá trị vào bean property

### 4.1. Khác với lỗi ConversionService độc lập

`TypeMismatchException` thuộc package `org.springframework.beans`, kế thừa `PropertyAccessException`. Nó được dùng khi thao tác gán một giá trị vào bean property không phù hợp với kiểu mà property yêu cầu.

Ví dụ JavaBean:

~~~java
public class ProductForm {
    private int quantity;

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Nếu dùng `BeanWrapper`:

~~~java
ProductForm form = new ProductForm();
BeanWrapper wrapper = new BeanWrapperImpl(form);

wrapper.setPropertyValue("quantity", "ten");
~~~

`quantity` yêu cầu `int`, còn `"ten"` không thể chuyển thành số nguyên. Trong thao tác property access, lỗi có thể được thể hiện dưới dạng `TypeMismatchException` hoặc subclass phù hợp.

Điểm phân biệt: ở đây ứng dụng không chỉ hỏi `ConversionService` “hãy chuyển String sang Integer”. Ứng dụng đang **thực hiện một thao tác gán bean property**, do đó Spring cần báo lỗi theo ngữ cảnh property access.

### 4.2. Những getter hữu ích

`TypeMismatchException` và superclass `PropertyAccessException` cung cấp dữ liệu giúp xác định:

- Giá trị không thể gán.
- Kiểu bắt buộc.
- Property/event liên quan (tùy constructor/nguồn exception).
- Cause chain nếu conversion hoặc setter ném lỗi.

Trong một exception cụ thể, API getter sẵn có phụ thuộc lớp con và overload được sử dụng. Không giả định mọi subclass đều giữ cùng một bộ metadata.

### 4.3. ConversionNotSupportedException là subclass khác

Một lớp thường cần nhận biết:

`org.springframework.beans.ConversionNotSupportedException` **extends `TypeMismatchException`** và mô tả tình huống không có suitable editor/converter cho bean property. Nó khác với `org.springframework.core.convert.ConverterNotFoundException`:

| Lớp exception | Tầng | Ý nghĩa |
| --- | --- | --- |
| `ConverterNotFoundException` | `ConversionService` | Không tìm thấy converter cho cặp kiểu |
| `ConversionNotSupportedException` | Bean property access | Không có editor/converter phù hợp khi gán bean property |
| `ConversionFailedException` | `ConversionService` | Đã thực hiện conversion nhưng thất bại |
| `TypeMismatchException` | Bean property access | Giá trị không phù hợp kiểu property; có thể là superclass của lỗi chuyên biệt |

Vì vậy, khi log chỉ ghi “conversion not supported”, hãy xem **package đầy đủ** và exception chain thay vì chỉ dựa vào phần tên lớp.

## 5. So sánh nhanh bằng câu hỏi chẩn đoán

| Câu hỏi | Exception thường hướng tới |
| --- | --- |
| Spring không biết chuyển kiểu nguồn sang kiểu đích bằng cách nào? | `ConverterNotFoundException` |
| Spring biết cách chuyển nhưng giá trị cụ thể làm converter thất bại? | `ConversionFailedException` |
| Spring đang gán một giá trị vào property bean và kiểu không phù hợp? | `TypeMismatchException` hoặc subclass |
| Bean property không có editor/converter phù hợp? | Có thể là `ConversionNotSupportedException` |

Câu hỏi quyết định là: **lỗi xảy ra ở bước nào?**

~~~text
Source value + target type
           |
           v
Find conversion path?
   | No                  | Yes
   v                     v
ConverterNotFound     Execute conversion
                          |
                     success?
                     |      |
                    No     Yes
                     |      |
                     v      v
             ConversionFailed  converted value
                                   |
                                   v
                         assign bean property
                                   |
                              type/access OK?
                                |      |
                               No     Yes
                                |      |
                                v      v
                        TypeMismatch  property updated
~~~

Đây là sơ đồ khái niệm. Trong Spring thực tế, binder/accessor có thể sử dụng `PropertyEditor`, `ConversionService`, type descriptor và các adapter. Sơ đồ giúp phân biệt trách nhiệm chứ không phải mô tả toàn bộ nội bộ cho mọi overload.

## 6. Ví dụ Java 17+: tái hiện cả ba loại lỗi

Ví dụ sau chạy bằng Java 17+ và Spring Framework. Nó dùng:

1. `DefaultConversionService` để tái hiện thiếu converter.
2. `DefaultConversionService` để tái hiện converter có nhưng parse thất bại.
3. `BeanWrapperImpl` để gán chuỗi sai vào property kiểu `int`.
4. `DataBinder` để xem lỗi được lưu trong `BindingResult`.

### 6.1. Maven dependency

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-conversion-exceptions-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

`spring-context` kéo theo các module Spring cần thiết như `spring-beans` và `spring-core`. Trong ứng dụng Spring Boot, nên dùng parent/BOM của Boot để quản lý các phiên bản module Spring cùng nhau. Bản `6.2.19` được ghim để ví dụ tái hiện; không phải chỉ dẫn nâng riêng một module trong Boot.

### 6.2. Mã nguồn hoàn chỉnh

Lưu tại `src/main/java/example/ConversionExceptionDemo.java`:

~~~java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.TypeMismatchException;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

public class ConversionExceptionDemo {

    // Kiểu đích không có String constructor, valueOf/of/from.
    public record CustomerReference(String value) {
    }

    public static class ProductForm {
        private int quantity;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    private static void converterNotFound(
            DefaultConversionService service) {
        try {
            service.convert("ABC-123", CustomerReference.class);
        } catch (ConverterNotFoundException ex) {
            System.out.println(
                    "missing=" + ex.getClass().getSimpleName());
            System.out.println(
                    "missing.source=" + ex.getSourceType().getType().getSimpleName());
            System.out.println(
                    "missing.target=" + ex.getTargetType().getType().getSimpleName());
        }
    }

    private static void conversionFailed(
            DefaultConversionService service) {
        try {
            service.convert("not-a-number", Integer.class);
        } catch (ConversionFailedException ex) {
            System.out.println(
                    "failed=" + ex.getClass().getSimpleName());
            System.out.println(
                    "failed.source=" + ex.getSourceType().getType().getSimpleName());
            System.out.println(
                    "failed.target=" + ex.getTargetType().getType().getSimpleName());
            System.out.println(
                    "failed.cause=" + ex.getCause().getClass().getSimpleName());
        }
    }

    private static void propertyMismatch() {
        ProductForm form = new ProductForm();
        BeanWrapper wrapper = new BeanWrapperImpl(form);

        try {
            wrapper.setPropertyValue("quantity", "ten");
        } catch (TypeMismatchException ex) {
            System.out.println(
                    "beanProperty=" + ex.getClass().getSimpleName());
            System.out.println(
                    "beanProperty.required=" +
                    ex.getRequiredType().getSimpleName());
        }
    }

    private static void dataBinderResult() {
        ProductForm form = new ProductForm();
        DataBinder binder = new DataBinder(form, "productForm");

        binder.setAllowedFields("quantity");
        binder.bind(
                new org.springframework.beans.MutablePropertyValues()
                        .add("quantity", "ten"));

        BindingResult result = binder.getBindingResult();

        System.out.println("binder.hasErrors=" + result.hasErrors());
        System.out.println(
                "binder.field=" + result.getFieldError("quantity").getField());
        System.out.println(
                "binder.errorCode=" + result.getFieldError("quantity").getCode());
    }

    public static void main(String[] args) {
        DefaultConversionService service = new DefaultConversionService();

        converterNotFound(service);
        conversionFailed(service);
        propertyMismatch();
        dataBinderResult();
    }
}
~~~

Các class được dùng với mục đích cụ thể:

- `CustomerReference` không có cơ chế tạo từ `String` trong ví dụ, nên conversion service mặc định không có đường chuyển đổi phù hợp.
- `Integer` có conversion path mặc định; chuỗi `"not-a-number"` khiến thực thi parse thất bại.
- `BeanWrapperImpl` nhận chuỗi `"ten"` để gán vào property `int quantity`; exception được bắt ở lớp `TypeMismatchException`.
- `DataBinder` nhận cùng giá trị nhưng ghi lỗi vào `BindingResult`, nên caller có thể đọc field error thay vì phụ thuộc exception được ném ra khỏi controller.

### 6.3. Lệnh biên dịch và chạy

Cấu trúc:

~~~text
spring-conversion-exceptions-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ConversionExceptionDemo.java
~~~

Tại thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.ConversionExceptionDemo
~~~

Đầu ra dự kiến do chương trình in (không tính log Maven):

~~~text
missing=ConverterNotFoundException
missing.source=String
missing.target=CustomerReference
failed=ConversionFailedException
failed.source=String
failed.target=Integer
failed.cause=NumberFormatException
beanProperty=TypeMismatchException
beanProperty.required=int
binder.hasErrors=true
binder.field=quantity
binder.errorCode=typeMismatch
~~~

Các giá trị trên phản ánh API/luồng của ví dụ ở Spring Framework 6.2; message chi tiết hoặc tên cause trong ứng dụng khác có thể khác vì converter, editor và cấu hình có thể khác. Nếu triển khai lại với một phiên bản hoặc converter custom khác, hãy chạy test trên đúng dependency thực tế.

## 7. Vì sao DataBinder có thể không ném exception ra ngoài?

Một nhầm lẫn thường gặp là: “Nếu conversion thất bại, chắc chắn controller sẽ nhận exception `ConversionFailedException`”. Điều đó không luôn đúng.

`DataBinder` được thiết kế để ghi lỗi binding vào `BindingResult`. Khi gán từng property thất bại, binder có thể chuyển lỗi thành `FieldError` (thường mang code `typeMismatch`) để controller hoặc tầng trình bày hiển thị lỗi ngay trên trường tương ứng.

Ví dụ:

~~~java
DataBinder binder = new DataBinder(form, "productForm");
binder.bind(propertyValues);

BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("quantity")) {
    // Hiển thị/định dạng lỗi cho field quantity.
}
~~~

Đây là **đoạn trích** sử dụng biến `form` và `propertyValues` đã có. Để kiểm tra chẩn đoán, dùng:

~~~java
result.getFieldErrors("quantity");
result.getFieldError("quantity").getCode();
result.getFieldError("quantity").getRejectedValue();
result.getFieldError("quantity").getDefaultMessage();
~~~

Không phải mọi lỗi binding đều là `typeMismatch`. Có thể gặp field không tồn tại, field bị suppressed do allowed/disallowed fields, lỗi nested path hoặc lỗi trong setter. Hãy đọc `FieldError`, `ObjectError` và rejected value một cách có chọn lọc.

Trong Spring MVC, nếu một `@ModelAttribute` có lỗi và không có `BindingResult` liền sau để controller xử lý, framework có thể ném exception ở tầng web theo trường hợp cụ thể. Với REST API, ứng dụng có thể ánh xạ lỗi sang HTTP 400. Nhưng không nên để client thấy stack trace hoặc message nội bộ.

## 8. Phân biệt theo cách sử dụng ConversionService, BeanWrapper và DataBinder

| API đang gọi | Mục tiêu | Dạng lỗi thường cần nhận diện |
| --- | --- | --- |
| `ConversionService.convert(source, targetType)` | Chuyển đổi một giá trị theo cặp kiểu | `ConverterNotFoundException` hoặc `ConversionFailedException` |
| `BeanWrapper.setPropertyValue(name, value)` | Chuyển kiểu và gán một bean property | `TypeMismatchException`, `NotWritablePropertyException`, lỗi accessor khác |
| `DataBinder.bind(PropertyValues)` | Gắn tập input vào target và ghi lỗi binding | `BindingResult` với `FieldError`/`ObjectError` |
| Spring MVC `@ModelAttribute` | Bind request parameters vào model object | `BindingResult` hoặc exception web tùy chữ ký/controller/config |
| Spring MVC `@RequestParam` | Chuyển một request parameter vào method argument | `MethodArgumentTypeMismatchException` hoặc lỗi web liên quan |
| JSON `@RequestBody` | Deserialize body qua message converter/Jackson | Lỗi đọc/deserialize message; không mặc định là `ConverterNotFoundException` |

**Đọc đúng API trước khi viết catch block.** Không nên bắt `ConversionException` quanh toàn bộ request rồi bỏ qua `BindingResult`, vì binder có thể đã xử lý lỗi và cho phép ứng dụng trả lại form. Ngược lại, nếu gọi `ConversionService` trực tiếp, bạn phải quyết định bắt exception hay để tầng trên xử lý.

## 9. Xử lý lỗi theo từng mục đích

### 9.1. Khi thiếu converter

Kiểm tra cấu hình `ConversionService` và đăng ký converter:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToCustomerReferenceConverter());
~~~

Nếu app dùng Spring Boot, đăng ký converter theo cơ chế cấu hình web/conversion phù hợp (ví dụ bean `Converter`, `Formatter` hoặc `WebMvcConfigurer#addFormatters`). Đừng tạo một `DefaultConversionService` riêng trong controller rồi kỳ vọng Spring MVC tự sử dụng instance đó.

### 9.2. Khi converter thất bại với một giá trị

Kiểm tra dữ liệu đầu vào và cause chain. Nếu đầu vào sai định dạng, trả lỗi field có message dễ hiểu. Nếu converter có bug hoặc exception kỹ thuật, ghi log nội bộ kèm request correlation ID nhưng không đưa stack trace ra client.

### 9.3. Khi bean property type mismatch

Kiểm tra:

- Java property đích khai báo kiểu gì?
- Giá trị nguồn có kiểu gì và có đúng format không?
- Có editor/converter phù hợp ở đúng binder/accessor chưa?
- Setter có ném lỗi hoặc tự thực hiện kiểm tra không?
- Nested path có hợp lệ và object con đã tồn tại chưa?

Nếu dữ liệu tới qua `DataBinder`, đọc `BindingResult` để phản hồi theo từng field. Nếu sử dụng `BeanWrapper` trực tiếp, bắt `PropertyAccessException`/subclass cụ thể ở lớp gọi có khả năng quyết định hành động tiếp theo.

### 9.4. Không biến mọi lỗi thành cùng một thông điệp

Ví dụ “Dữ liệu không hợp lệ” có thể đủ cho client, nhưng khi chẩn đoán nội bộ nên giữ được:

- source/target type;
- field hoặc property path;
- giá trị bị từ chối (đã redact nếu nhạy cảm);
- exception class/cause;
- request ID hoặc correlation ID;
- phiên bản converter/configuration khi thích hợp.

Không nên log secret hoặc toàn bộ payload nhạy cảm chỉ để thấy rejected value.

## 10. Lỗi hay gặp và các tình huống biên

### Nhầm ConverterNotFound với ConversionFailed

- `ConverterNotFound`: chưa có đường conversion tương ứng.
- `ConversionFailed`: đã có đường xử lý nhưng dữ liệu/logic làm nó thất bại.

Nếu thêm một converter rỗng hoặc converter nhận mọi kiểu nhưng luôn ném exception, hệ thống có thể chuyển từ lỗi “not found” thành “failed” mà dữ liệu vẫn không xử lý được. Hãy tạo converter có source/target rõ ràng và test cả dữ liệu hợp lệ lẫn bất hợp lệ.

### Nhầm ConversionFailed với TypeMismatch

Khi gọi `ConversionService` trực tiếp, lỗi thuộc conversion layer. Khi gán vào property, lỗi có thể được biểu diễn bằng `TypeMismatchException`. Nếu thấy một exception bao bọc exception khác, đọc cả outer exception lẫn cause để biết thao tác bên ngoài là gì và lỗi chuyển đổi bên trong là gì.

### Dùng converter không đúng kiểu generic

`Converter<String, Long>` không phải converter cho `String -> Integer`. Đăng ký vào đúng registry và xác định đúng kiểu đích; với collection, map và generic DTO, cần xem `TypeDescriptor` để biết generic element/key/value.

### Giá trị null và primitive

Một giá trị `null` có thể không chuyển được sang primitive như `int` hoặc `boolean` vì primitive không chứa null. Cân nhắc dùng wrapper `Integer`/`Boolean` khi field có thể bỏ trống, sau đó validation sẽ quyết định có bắt buộc hay không.

### Locale và định dạng ngày/số

`"1,25"` có thể biểu diễn số thập phân theo một locale nhưng lại có ý nghĩa khác theo locale khác. Dùng `Formatter`/locale được cấu hình rõ, tránh converter tự suy đoán định dạng toàn cầu.

### Setter tự ném exception

Ngay cả khi conversion thành công, setter vẫn có thể ném exception do invariant của object. Lúc đó không thể kết luận lỗi là `ConverterNotFoundException`; cần xem `MethodInvocationException`, `PropertyAccessException` hoặc cause chain tương ứng.

### Không có converter nhưng có PropertyEditor

Bean property access có thể dùng `PropertyEditor` đã đăng ký dù `ConversionService` trực tiếp không biết chuyển đổi. Vì vậy, một lời gọi `conversionService.convert(...)` thất bại không chứng minh `BeanWrapper` ở nơi khác chắc chắn thất bại; hai registry/cơ chế có thể khác nhau.

### Không có Spring converter nhưng Jackson có thể deserialize

`@RequestBody` JSON thường sử dụng Jackson/HTTP message converter. Cấu hình Jackson module/deserializer và `ConversionService` không phải cùng một registry. Đừng sửa `ConverterNotFoundException` trong MVC chỉ bằng cách thêm một Jackson deserializer nếu endpoint thật đang dùng `@ModelAttribute`.

## 11. Câu hỏi tự kiểm tra

1. `ConverterNotFoundException` và `ConversionFailedException` có chung superclass nào?
2. Vì sao `TypeMismatchException` không phải subclass của `ConversionException`?
3. Nếu `DefaultConversionService.convert("abc", Integer.class)` thất bại, lý do nghiêng về “không tìm thấy converter” hay “converter thực thi thất bại”?
4. Khi `BeanWrapper.setPropertyValue("quantity", "ten")`, vì sao lỗi có thể xuất hiện ở tầng `PropertyAccessException`?
5. Tại sao `DataBinder.bind(...)` có thể lưu lỗi vào `BindingResult` thay vì ném exception ra ngoài?
6. Khi nhìn thấy `ConversionNotSupportedException`, package của nó giúp phân biệt với `ConverterNotFoundException` như thế nào?
7. Nếu chuỗi số hợp lệ về cú pháp nhưng vượt giới hạn nghiệp vụ, đó là conversion failure hay validation failure?
8. Vì sao cần đọc cả exception cause và rejected field khi xử lý lỗi trong production?

**Ghi nhớ:** `ConverterNotFoundException` = không tìm thấy conversion path; `ConversionFailedException` = conversion path tồn tại nhưng chạy thất bại; `TypeMismatchException` = việc gán bean property không phù hợp kiểu. Hãy xác định **API đang được gọi và tầng phát sinh lỗi**, đọc type/field/cause rồi mới quyết định đăng ký converter, sửa dữ liệu, xử lý property access hay trả lỗi validation.

## Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — ConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionException.html)
- [Spring Framework Javadoc — ConverterNotFoundException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConverterNotFoundException.html)
- [Spring Framework Javadoc — ConversionFailedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionFailedException.html)
- [Spring Framework Javadoc — TypeMismatchException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/TypeMismatchException.html)
- [Spring Framework Javadoc — PropertyAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyAccessException.html)
- [Spring Framework Javadoc — ConversionNotSupportedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/ConversionNotSupportedException.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)