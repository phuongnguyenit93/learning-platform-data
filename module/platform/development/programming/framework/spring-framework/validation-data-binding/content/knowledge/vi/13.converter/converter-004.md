# Viết Converter từ chuỗi sang kiểu giá trị nghiệp vụ trong Spring Framework

> **Chủ đề:** Spring Framework – validation-data-binding. **Nhóm:** Converter. Ví dụ sử dụng Java 17 và Spring Framework 6.2.x.

## 1. Bài toán và mục tiêu

Dữ liệu đến từ HTTP query, form, header hoặc cấu hình thường là văn bản. Trong ứng dụng, ta muốn dùng kiểu có ý nghĩa nghiệp vụ thay vì truyền chuỗi rời rạc. Ví dụ client gửi mã `prd-a123`, còn controller muốn nhận một value object `ProductCode`.

Nếu mỗi controller hoặc service tự trim, uppercase, parse và kiểm tra định dạng, quy tắc chuyển đổi sẽ bị lặp lại và có thể khác nhau. Spring `Converter` cho phép đóng gói phép chuyển đổi giữa hai kiểu, đăng ký một lần và tái sử dụng trong `ConversionService`, `DataBinder` và Spring MVC.

Mục tiêu:
- Hiểu `Converter<S,T>` và cách triển khai converter có kiểu rõ ràng.
- Tạo value object đại diện một khái niệm domain.
- Chuẩn hóa chuỗi, từ chối dữ liệu sai và giữ invariant.
- Đăng ký converter vào `ConverterRegistry`/`FormatterRegistry`.
- Dùng conversion trong JavaBeans, `DataBinder` và tham số MVC.
- Phân biệt conversion với validation, lookup database và Jackson JSON deserialization.

**Ranh giới quan trọng:** converter biến một biểu diễn thành kiểu đích. Nó không chứng minh đối tượng tồn tại, người gọi có quyền truy cập hoặc hành động được phép theo nghiệp vụ.

## 2. Converter SPI

Spring định nghĩa interface:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

`S` là kiểu nguồn, `T` là kiểu đích. Với bài này, phép chuyển đổi là `String -> ProductCode`.

```java
public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        // Parse và chuẩn hóa source.
    }
}
```

Spring sử dụng generic type để nhận diện converter thích hợp trong registry. Converter nên nhỏ, tập trung vào một phép chuyển đổi, stateless và không phụ thuộc controller hoặc repository.

Nếu không thể chuyển đổi, implementation có thể ném exception để báo conversion failure. Tránh catch mọi lỗi rồi trả `null`: cách đó biến “giá trị client gửi sai” thành “không có giá trị” và khiến lỗi bị phát hiện muộn ở tầng khác.

## 3. Tạo value object ProductCode

Quy ước ví dụ: mã sản phẩm chuẩn hóa có dạng `PRD-XXXX`, trong đó `XXXX` gồm bốn chữ cái in hoa hoặc chữ số. Input được trim và chuyển về uppercase theo locale trung tính.

| Input | Kết quả |
| --- | --- |
| `"prd-a123"` | `ProductCode("PRD-A123")` |
| `" PRD-b9x2 "` | `ProductCode("PRD-B9X2")` |
| `"PRD-12"` | Từ chối vì sai độ dài |
| `"ABC-A123"` | Từ chối vì sai prefix |
| Chuỗi rỗng | Từ chối |

```java
package demo;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null || !value.matches("PRD-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Invalid product code: " + value);
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

Record cung cấp accessor `value()`, equality và hash code dựa trên giá trị. Compact constructor bảo vệ invariant nội tại, kể cả khi một đoạn code khác gọi constructor trực tiếp mà không qua converter.

**Tách trách nhiệm:** converter diễn giải representation bên ngoài (trim, uppercase, parse); value object đảm bảo mọi instance đều hợp lệ. Quy tắc chuẩn hóa phải là quyết định rõ ràng của domain. Nếu mã phân biệt hoa/thường thì không được tự tiện uppercase.

## 4. Viết StringToProductCodeConverter

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "Product code must not be null");
        }

        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "Product code must not be blank");
        }

        return new ProductCode(normalized);
    }
}
```

Giải thích:
1. Generic khai báo rõ nguồn và đích; không cần tự kiểm tra `instanceof`.
2. `trim()` bỏ khoảng trắng đầu/cuối.
3. `toUpperCase(Locale.ROOT)` tránh phụ thuộc locale mặc định của máy chạy.
4. Chuỗi rỗng bị từ chối.
5. Tạo `ProductCode` để invariant được kiểm tra lần cuối.

Trong conversion flow thông thường, `ConversionService` xử lý giá trị `null` riêng và converter không nhất thiết nhận null. Kiểm tra null ở đây làm implementation an toàn hơn khi được gọi trực tiếp. Không dùng converter để tra cứu sản phẩm trong database: converter nên chuyển đổi representation, còn lookup là trách nhiệm của application service/domain layer.

## 5. ConversionService và ConverterRegistry

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| `Converter<S,T>` | SPI triển khai phép chuyển đổi có kiểu |
| `ConversionService` | API kiểm tra và thực hiện chuyển đổi lúc runtime |
| `ConverterRegistry` | Đăng ký converter vào hệ thống |
| `GenericConversionService` | Implementation registry tổng quát |
| `DefaultConversionService` | Conversion service với nhiều converter mặc định |
| `FormatterRegistry` | Registry hỗ trợ cả converter và formatter |

Đăng ký thủ công:

```java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToProductCodeConverter());

ProductCode code = service.convert("prd-a123", ProductCode.class);
System.out.println(code);
```

Output:

```text
PRD-A123
```

Có thể kiểm tra khả năng chuyển đổi:

```java
boolean supported =
        service.canConvert(String.class, ProductCode.class);
```

`canConvert` trả lời registry có đường chuyển giữa cặp kiểu hay không. Nó không chứng minh một chuỗi cụ thể hợp lệ: converter có thể tồn tại nhưng `convert("invalid", ProductCode.class)` vẫn thất bại.

Conversion service thường được cấu hình lúc khởi tạo application context và tái sử dụng. Các converter nên stateless để dùng an toàn giữa nhiều request.

## 6. Ví dụ Java 17 chạy được với Maven

Cấu trúc project:

```text
product-code-converter/
  pom.xml
  src/main/java/demo/ProductCode.java
  src/main/java/demo/StringToProductCodeConverter.java
  src/main/java/demo/ConverterDemo.java
```

### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>product-code-converter</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### ConverterDemo.java

Lưu lớp `ProductCode` và `StringToProductCodeConverter` theo các file ở cấu trúc trên. File main:

```java
package demo;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterDemo {

    public static void main(String[] args) {
        DefaultConversionService registry =
                new DefaultConversionService();
        registry.addConverter(new StringToProductCodeConverter());

        ConversionService service = registry;

        System.out.println("canConvert="
                + service.canConvert(String.class, ProductCode.class));

        ProductCode first =
                service.convert("prd-a123", ProductCode.class);
        ProductCode second =
                service.convert(" PRD-b9x2 ", ProductCode.class);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

Chạy trong thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterDemo
```

Stdout:

```text
canConvert=true
first=PRD-A123
second=PRD-B9X2
```

Đây là chương trình Java hoàn chỉnh có dependency Maven; chỉ dùng `javac ConverterDemo.java` không có Spring trong classpath sẽ không biên dịch. Ví dụ không cần Spring MVC, servlet container hay database.

## 7. Dùng converter trong BeanWrapper

Spring dùng conversion service khi bind property. DTO:

```java
package demo;

public class ProductSearch {
    private ProductCode code;

    public ProductCode getCode() {
        return code;
    }

    public void setCode(ProductCode code) {
        this.code = code;
    }
}
```

Dùng BeanWrapper:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

ProductSearch target = new ProductSearch();
BeanWrapper wrapper = new BeanWrapperImpl(target);
wrapper.setConversionService(conversionService);

wrapper.setPropertyValue("code", "prd-a123");
System.out.println(target.getCode());
```

Output:

```text
PRD-A123
```

Luồng xử lý: wrapper nhận property path `code` và chuỗi đầu vào; chuyển đổi service tìm `Converter<String, ProductCode>`; converter tạo object chuẩn hóa; setter nhận kiểu đích. Snippet giả định `conversionService` đã được tạo và đăng ký ở phần 6.

Nếu conversion thất bại, BeanWrapper báo lỗi property access/type mismatch; không được coi field đã được gán thành công. Việc conversion thành công cũng chưa chứng minh mã sản phẩm tồn tại hay được phép bán.

## 8. Dùng converter qua DataBinder

`DataBinder` cũng sử dụng hệ thống property access và conversion:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

ProductSearch target = new ProductSearch();
DataBinder binder = new DataBinder(target, "productSearch");
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "prd-a123");

binder.bind(values);

if (binder.getBindingResult().hasErrors()) {
    // Xử lý lỗi binding.
} else {
    System.out.println(target.getCode());
}
```

Đây là ví dụ binding thủ công; các import và biến phụ thuộc cần có trong cùng context. `bind` dùng conversion service rồi gán property. `BindingResult` lưu các lỗi binding.

`bind` không tự kích hoạt mọi annotation validation. Với `DataBinder` thủ công, nếu muốn chạy Bean Validation thì phải cấu hình validator và gọi `validate`; trong Spring MVC, `@Valid`/`@Validated` có thể kích hoạt validation qua lifecycle framework.

## 9. Đăng ký converter trong Spring MVC

Cách phổ biến là triển khai `WebMvcConfigurer` và thêm converter vào `FormatterRegistry`:

```java
package demo.web;

import demo.StringToProductCodeConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
    }
}
```

Controller có thể nhận trực tiếp value object:

```java
package demo.web;

import demo.ProductCode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    @GetMapping("/products")
    public String find(@RequestParam ProductCode code) {
        return "Selected product: " + code;
    }
}
```

Request:

```http
GET /products?code=prd-a123
```

Response body:

```text
Selected product: PRD-A123
```

Khi converter được đăng ký vào MVC registry, Spring thực hiện conversion cho những argument/binding flow sử dụng conversion service, chẳng hạn query parameter, path variable và form property phù hợp. Controller không cần gọi converter thủ công trong từng method.

**Không nhầm với `@RequestBody` JSON:** JSON thường đi qua `HttpMessageConverter` (ví dụ Jackson), dùng pipeline deserialize riêng. Converter đăng ký qua `FormatterRegistry` không tự động trở thành Jackson deserializer cho mọi JSON property. Với JSON, có thể cần Jackson creator, custom deserializer hoặc module phù hợp; hãy test endpoint JSON riêng.

## 10. Converter và Formatter

| Tiêu chí | Converter | Formatter |
| --- | --- | --- |
| Interface | `Converter<S,T>` | `Formatter<T>` |
| Hướng | Một chiều từ source sang target | Parse từ String và print ra String |
| Mục đích | Chuyển kiểu tổng quát | Định dạng dữ liệu cho giao diện, có thể phụ thuộc locale |
| Ví dụ | `String -> ProductCode` | Ngày giờ hoặc số thập phân hiển thị theo locale |
| Khi phù hợp | Quy tắc parse/convert ổn định | Cần parse và hiển thị giá trị theo định dạng |

`Formatter<T>` kết hợp `Parser<T>` và `Printer<T>`. Nếu chỉ cần biến chuỗi thành value object và không có yêu cầu in lại theo locale, `Converter` thường trực tiếp hơn. Với tiền tệ hoặc ngày giờ theo locale, `Formatter` có thể phù hợp.

Cả converter và formatter đều có thể đăng ký qua `FormatterRegistry`. Đừng triển khai formatter chỉ để thay một converter đơn giản khi không cần chức năng print/parse tương ứng.

## 11. Conversion khác validation và business rule

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Converter | Chuỗi được diễn giải thành kiểu đích nào? | `"prd-a123"` → `ProductCode("PRD-A123")` |
| Value object | Instance có invariant nội tại không? | Prefix và độ dài mã đúng |
| Bean Validation | DTO có đạt constraint khai báo không? | `@NotNull`, `@Valid`, custom constraint |
| Service/domain | Giá trị có được phép sử dụng trong use case? | Sản phẩm tồn tại, đang hoạt động |
| Repository/database | Trạng thái lưu trữ có hợp lệ không? | FK, unique, transaction |

Không đưa repository lookup vào converter. Mã có thể chuyển đổi hợp lệ nhưng chưa tồn tại. Việc kiểm tra tồn tại cần repository/service; việc kiểm tra quyền hoặc chính sách bán hàng cần domain/application service.

Tương tự, converter không thay thế Bean Validation. `"PRD-A123"` có thể chuyển đổi thành công nhưng giá trị khác vẫn có thể vi phạm ràng buộc trên DTO hoặc nghiệp vụ.

## 12. Xử lý lỗi conversion

Converter có thể ném exception nếu nguồn không hợp lệ. Qua ConversionService, lỗi có thể được bọc thành loại exception conversion; trong property binding/MVC, lỗi có thể được biểu diễn như binding/type mismatch tùy pipeline.

Nguyên tắc:
1. Không trả `null` để che lỗi.
2. Message lỗi nêu điều kiện đầu vào, không tiết lộ thông tin nội bộ.
3. Phân biệt sai định dạng với “không tìm thấy sản phẩm”.
4. Với MVC, chuẩn hóa response qua `BindingResult` hoặc `@ControllerAdvice` theo API contract.
5. Không catch `RuntimeException` chung rồi gắn nhãn mọi lỗi là “mã không hợp lệ”; có thể che bug/hạ tầng.

Unit test minh họa:

```java
assertEquals(
        new ProductCode("PRD-A123"),
        converter.convert("prd-a123"));

assertThrows(
        IllegalArgumentException.class,
        () -> converter.convert("bad"));
```

Đây là snippet dùng JUnit với biến `converter` đã khởi tạo. Bên cạnh unit test, nên test cả việc converter đã đăng ký vào service và request MVC thực tế.

## 13. Các cách đăng ký và tổ chức nhiều converter

Trong MVC, dùng `WebMvcConfigurer#addFormatters`:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToProductCodeConverter());
}
```

Đây là phần thân method trong class triển khai `WebMvcConfigurer`. Với ứng dụng thuần, thêm converter vào `DefaultConversionService` hoặc một registry được quản lý.

Nếu có nhiều value object, có thể đăng ký nhiều converter:

```java
@Configuration
class ConversionConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
        registry.addConverter(new StringToOrderIdConverter());
        registry.addConverter(new StringToCustomerCodeConverter());
    }
}
```

Hai converter bổ sung trong ví dụ cần implementation riêng. Có thể tách config theo domain khi danh sách lớn; tránh đặt logic parse phức tạp vào configuration class.

ConversionService thường được dùng lại trong application context; converter nên stateless và không giữ state mutable theo request. Không tạo mới registry cho mỗi request.

## 14. Khi nào cần GenericConverter, ConverterFactory hoặc PropertyEditor?

| Thành phần | Khi phù hợp |
| --- | --- |
| `Converter<S,T>` | Một cặp source/target rõ ràng |
| `ConverterFactory<S,R>` | Một source type chuyển sang nhiều target subtype cùng họ |
| `GenericConverter` | Nhiều source/target type, metadata hoặc điều kiện matching phức tạp |
| `PropertyEditor` | Cơ chế cũ gắn với JavaBeans/property binding; thường stateful |
| `ConversionService` | API thực thi các converter đã đăng ký |
| Custom validator | Kiểm tra constraint trên đối tượng, không nhằm chuyển kiểu |

Bắt đầu với `Converter` cho trường hợp đơn giản. Chỉ chọn `GenericConverter` hoặc `ConverterFactory` nếu yêu cầu thật sự cần khả năng mở rộng; abstraction phức tạp hơn không tự làm quy tắc chính xác hơn.

## 15. Mở rộng sang tiền tệ, ngày giờ và mã định danh

### Mã định danh

Với `ProductCode`, cần định nghĩa:
- Có trim không?
- Chữ hoa/thường có phân biệt không?
- Prefix, separator và độ dài nào được chấp nhận?
- Có cho ký tự Unicode không?
- Giá trị chuẩn hóa có dùng trong equality/index không?

Mọi adapter tạo kiểu này phải theo cùng invariant.

### Tiền tệ

Không parse chuỗi tiền tệ mà không định nghĩa locale và currency. `"1,234.50"` có thể mang nghĩa khác `"1.234,50"`. Nếu cần parse/in theo locale, cân nhắc `Formatter`; dùng `BigDecimal` thay cho `double` để giữ độ chính xác thập phân. Kiểu tiền nên mang currency tường minh nếu nghiệp vụ cần phân biệt.

### Ngày giờ

Chuỗi ISO có thể được parse bằng converter nếu contract cố định. Nếu cần in/parse theo locale, timezone hay định dạng giao diện, formatter thường phù hợp. Đừng tự giả định chuỗi ngày giờ không có offset luôn đại diện cùng một thời điểm trên mọi hệ thống.

## 16. Lỗi phổ biến

**1. Trả sai kiểu đích.** Generic `Converter<String, ProductCode>` cần trả `ProductCode`, không phải chuỗi.

**2. Chuẩn hóa thiếu nhất quán.** Khoảng trắng và hoa/thường có thể khiến cùng mã trở thành hai key khác nhau.

**3. Catch lỗi và trả null.** Làm dữ liệu sai bị hiểu thành không có dữ liệu.

**4. Truy vấn database trong converter.** Khiến phép chuyển đổi phụ thuộc hạ tầng và business context.

**5. Dùng locale mặc định.** Chuẩn hóa mã kỹ thuật nên dùng `Locale.ROOT` khi phù hợp.

**6. Coi conversion thành công là validation thành công.** Mã đúng định dạng chưa chắc tồn tại hoặc được phép dùng.

**7. Nghĩ converter MVC sẽ tự xử lý JSON.** `@RequestBody` thường qua Jackson/message converter; cấu hình riêng nếu cần.

**8. Tạo ConversionService cho từng request.** Cấu hình một lần và tái sử dụng.

**9. Converter giữ mutable request state.** Có thể gây lỗi khi nhiều luồng dùng chung; giữ implementation stateless.

**10. Chỉ test converter trực tiếp.** Cần kiểm tra registry, DataBinder và MVC endpoint nữa.

## 17. Ma trận kiểm thử

| Test case | Kết quả mong đợi |
| --- | --- |
| `"prd-a123"` | `PRD-A123` |
| `" PRD-b9x2 "` | `PRD-B9X2` |
| Chuỗi rỗng hoặc chỉ khoảng trắng | Conversion failure |
| `"PRD-12"` | Bị từ chối vì sai độ dài |
| `"ABC-A123"` | Bị từ chối vì sai prefix |
| `canConvert(String, ProductCode)` sau đăng ký | true |
| `convert` mã hợp lệ | Value object chuẩn hóa |
| BeanWrapper ghi chuỗi vào property `ProductCode` | Setter nhận object đúng kiểu |
| MVC `@RequestParam ProductCode` | Request hợp lệ được chuyển đổi |
| MVC input sai | Binding/conversion error theo API contract |
| `@RequestBody` JSON | Test Jackson/deserializer riêng |

Chia test thành ba tầng:
1. **Unit test:** quy tắc parse/normalize và invariant.
2. **ConversionService/DataBinder test:** xác minh registry và property binding dùng converter.
3. **MVC integration test:** kiểm tra query/form/path argument, response khi sai và exception handling.

## 18. Checklist áp dụng

1. Xác định source type và target type; ưu tiên value object có tên nghiệp vụ.
2. Bảo vệ invariant trong constructor/factory của value object.
3. Quyết định normalization và lỗi conversion một cách tường minh.
4. Implement `Converter<S,T>` nhỏ, stateless.
5. Đăng ký vào `ConverterRegistry` hoặc `FormatterRegistry` thích hợp.
6. Kiểm tra qua `ConversionService` và DataBinder/MVC.
7. Tách conversion khỏi validation, business rule và persistence.
8. Test cả input hợp lệ, sai format, rỗng, whitespace và null.
9. Kiểm tra riêng JSON deserialization nếu endpoint dùng `@RequestBody`.
10. Giữ converter nhẹ, không truy vấn database và không kiểm tra quyền.

**Ghi nhớ:** `Converter<String, ProductCode>` chuyển representation thành kiểu giá trị nghiệp vụ. `ConversionService` tìm và thực thi converter; `FormatterRegistry`/`WebMvcConfigurer` tích hợp nó với web binding. Conversion trả lời “chuỗi này biểu diễn kiểu gì?”, còn validation và service/domain trả lời “giá trị đó có hợp lệ và được phép sử dụng không?”.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference – Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter SPI và ConverterRegistry.
- [Spring Framework Reference – Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Converter, Formatter, locale và FormatterRegistry.
- [Spring Framework Reference – Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký converter/formatter qua WebMvcConfigurer.
- [Spring Framework 6.2.14 Javadoc – Converter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html): interface chuyển đổi có kiểu.
- [Spring Framework 6.2.14 Javadoc – ConverterRegistry](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): API đăng ký converter.
