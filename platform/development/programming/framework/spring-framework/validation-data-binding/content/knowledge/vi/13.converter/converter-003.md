# Báo đầu vào không hợp lệ bằng ngoại lệ thích hợp trong Spring Converter

## 1. Vì sao converter cần báo lỗi rõ ràng?

Spring Converter nhận một giá trị nguồn và chuyển nó sang kiểu đích. Ví dụ ứng dụng nhận chuỗi mã trạng thái `"ACTIVE"` và chuyển sang enum `AccountStatus`. Một giá trị hợp lệ có thể chuyển thành object; nhưng nếu người dùng gửi `"UNKNOWN_STATUS"`, converter phải thông báo rằng **giá trị nguồn không thể chuyển đổi theo quy tắc được định nghĩa**.

Trong Spring Core, hợp đồng `org.springframework.core.convert.converter.Converter<S, T>` là:

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

Với một giá trị nguồn không hợp lệ, tài liệu Spring hướng dẫn converter ném một unchecked exception, cụ thể nên dùng **`IllegalArgumentException`** để báo nguồn không hợp lệ. `ConversionService` hoặc tầng binding phía trên sẽ xử lý exception đó và biểu diễn thất bại theo ngữ cảnh.

Điều cần phân biệt:

- **`IllegalArgumentException` trong converter:** implementation nói rằng giá trị đầu vào không thỏa điều kiện chuyển đổi.
- **`ConversionFailedException`:** Spring ConversionService báo một lần chuyển đổi thực tế đã thất bại; exception này có thể giữ nguyên nguyên nhân bên dưới.
- **`TypeMismatchException` / `BindException` / exception của Spring MVC:** lỗi có thể được biểu diễn ở tầng bean property binding hoặc web request binding, tùy đường dữ liệu.
- **Business validation:** dữ liệu đã chuyển đổi thành công về kiểu Java nhưng không thỏa nghiệp vụ; cần validation hoặc exception nghiệp vụ phù hợp, không ép tất cả vào lỗi chuyển đổi.

Converter không nên nuốt lỗi rồi trả một giá trị giả, vì tầng gọi sẽ hiểu nhầm rằng dữ liệu đã được chuyển đổi thành công.

## 2. Quy tắc của Converter: ném IllegalArgumentException

Ví dụ converter chuyển chuỗi sang mã vùng gồm đúng 5 chữ số:

```java
public final class PostalCodeConverter
        implements Converter<String, PostalCode> {

    @Override
    public PostalCode convert(String source) {
        if (source == null || !source.matches("\\d{5}")) {
            throw new IllegalArgumentException(
                "Postal code must contain exactly 5 digits"
            );
        }
        return new PostalCode(source);
    }
}
```

Đây là ví dụ rút gọn, giả định có kiểu `PostalCode` phù hợp. Với `Converter.convert(S)`, Spring bảo đảm source đưa vào không null theo hợp đồng; việc kiểm tra null trong ví dụ chỉ để làm rõ quy tắc nếu phương thức được gọi thủ công hoặc logic bị tái sử dụng. Trong một converter thông thường, có thể tập trung xác thực định dạng nguồn mà hợp đồng thực tế cung cấp.

Vì sao chọn `IllegalArgumentException`?

1. Nó biểu đạt lỗi do **giá trị argument** không hợp lệ đối với thao tác chuyển đổi.
2. Đây là exception unchecked, phù hợp với chữ ký `T convert(S source)` không khai báo checked exception.
3. Spring ConversionService biết cách nhận exception này trong quy trình chuyển đổi và báo một `ConversionException` phù hợp.
4. Lớp gọi có thể dùng nguyên nhân để chẩn đoán hoặc ánh xạ sang phản hồi phù hợp.

**Không nên ném `IllegalStateException`** cho một chuỗi người dùng nhập sai định dạng. `IllegalStateException` thường biểu đạt trạng thái chương trình/đối tượng không thích hợp để thực hiện thao tác. Dữ liệu đầu vào không hợp lệ là vấn đề argument.

Cũng không nên trả `null` để báo conversion failure. `null` có thể mang ý nghĩa hợp lệ trong hệ thống chuyển đổi (ví dụ nguồn null, converter có quy ước riêng, hoặc nullable target); nó không nói rõ rằng người dùng đã gửi dữ liệu sai. Hãy báo lỗi bằng exception.

## 3. Spring bọc lỗi như thế nào?

Một converter tự viết ném `IllegalArgumentException`. Khi được gọi thông qua `GenericConversionService` hoặc `DefaultConversionService`, Spring có thể bọc exception này trong **`org.springframework.core.convert.ConversionFailedException`**, lớp con của `ConversionException`.

Luồng khái quát:

```text
ConversionService.convert(source, TargetType)
                 |
                 v
        tìm Converter phù hợp
                 |
                 v
     Converter.convert(source) 
                 |
         +-------+-------+
         |               |
    chuyển thành công   ném IllegalArgumentException
         |               |
         v               v
    giá trị Target   ConversionFailedException
                         |
                         v
             tầng gọi quyết định cách báo lỗi
```

`ConversionFailedException` mô tả một lần chuyển đổi thực tế đã thất bại. Nó có thể cung cấp:

- `getSourceType()`: kiểu nguồn được chuyển đổi.
- `getTargetType()`: kiểu đích mong muốn.
- `getValue()`: giá trị gây thất bại (cần thận trọng khi log).
- `getCause()`: nguyên nhân, thường là exception mà converter ném ra.

Không phải mọi lỗi dùng ConversionService đều có nguyên nhân là `IllegalArgumentException`. Ví dụ không tìm được converter có thể dẫn tới `ConverterNotFoundException`; một số đường chuyển đổi có thể tạo exception phù hợp khác. Do đó đừng bắt `IllegalArgumentException` bên ngoài rồi mặc định mọi vấn đề đều là giá trị đầu vào sai.

### Phân biệt hai nơi ném exception

| Nơi | Exception nên gặp | Ý nghĩa |
| --- | --- | --- |
| Mã trong converter tự viết | `IllegalArgumentException` | Source không thể được chuyển đổi theo quy tắc converter |
| Spring ConversionService thực thi converter | `ConversionFailedException` hoặc `ConversionException` tương ứng | Chuyển đổi thực tế thất bại |
| Không tìm thấy converter phù hợp | `ConverterNotFoundException` | Thiếu khả năng chuyển đổi, có thể là vấn đề cấu hình |
| JavaBean/property binding | Có thể được chuyển thành `TypeMismatchException` và binding error | Không gán được input sang property đích |
| Spring MVC request parameter/path variable | Exception chuyên biệt như `MethodArgumentTypeMismatchException` | Không chuyển được giá trị request sang kiểu tham số controller |

**Quy tắc:** trong converter viết theo SPI của Spring, hãy ném `IllegalArgumentException`; để ConversionService và tầng tích hợp xử lý việc bọc/ánh xạ lỗi. Tránh tự ném `ConversionFailedException` chỉ để tái hiện việc Spring bọc lỗi, trừ khi bạn đang tự xây một lớp hạ tầng gọi trực tiếp API đó và thực sự có đủ metadata nguồn/đích.

## 4. Ví dụ Java 17 chạy được: Converter sai đầu vào

Chương trình sau dùng `DefaultConversionService` của Spring Framework 6.1.14. Converter nhận chuỗi mã vận đơn có cấu trúc `AB-123456`. Nếu sai định dạng, converter ném `IllegalArgumentException`. Khi chạy qua ConversionService, chương trình bắt `ConversionFailedException` và in loại exception, kiểu nguồn/đích cùng nguyên nhân.

Cấu trúc:

```text
converter-invalid-input/
├── pom.xml
└── src/main/java/demo/ConverterInvalidInputDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-invalid-input</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ConverterInvalidInputDemo.java`:

```java
package demo;

import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterInvalidInputDemo {

    public record TrackingCode(String value) {}

    public static final class StringToTrackingCode
            implements Converter<String, TrackingCode> {

        @Override
        public TrackingCode convert(String source) {
            if (source == null || !source.matches("[A-Z]{2}-\\d{6}")) {
                throw new IllegalArgumentException(
                    "Expected format LL-123456"
                );
            }
            return new TrackingCode(source);
        }
    }

    public static void main(String[] args) {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(new StringToTrackingCode());

        TrackingCode valid =
            service.convert("AB-123456", TrackingCode.class);
        System.out.println("valid=" + valid.value());

        try {
            service.convert("bad-code", TrackingCode.class);
        } catch (ConversionFailedException ex) {
            System.out.println("exception="
                + ex.getClass().getSimpleName());
            System.out.println("source="
                + ex.getSourceType().getType().getSimpleName());
            System.out.println("target="
                + ex.getTargetType().getType().getSimpleName());
            System.out.println("cause="
                + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy từ thư mục có `pom.xml` bằng JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterInvalidInputDemo
```

Các dòng chương trình in ra (không tính log Maven/Spring nếu có):

```text
valid=AB-123456
exception=ConversionFailedException
source=String
target=TrackingCode
cause=IllegalArgumentException
```

Giải thích:

1. `service.addConverter(...)` đăng ký converter cho cặp `String → TrackingCode`.
2. Giá trị `"AB-123456"` khớp biểu thức định dạng, nên converter tạo record `TrackingCode`.
3. Giá trị `"bad-code"` không khớp, nên converter ném `IllegalArgumentException`.
4. ConversionService bắt lỗi chuyển đổi bên trong và ném `ConversionFailedException` chứa thông tin nguồn, đích và nguyên nhân.
5. Mã gọi bắt exception ở **ranh giới phù hợp** để xử lý hoặc chuyển thành phản hồi; converter không tự quyết định HTTP status.

## 5. Trường hợp nào nên dùng exception nào?

Chọn exception theo **tầng đang xử lý** và **loại lỗi**.

### A. Trong Converter: IllegalArgumentException

Khi đầu vào có kiểu nguồn hợp lệ nhưng giá trị không nằm trong miền mà converter có thể chuyển:

```java
@Override
public CurrencyCode convert(String source) {
    if (!source.matches("[A-Z]{3}")) {
        throw new IllegalArgumentException(
            "Currency code must contain 3 uppercase letters"
        );
    }
    return new CurrencyCode(source);
}
```

Đây là snippet minh họa, giả định kiểu `CurrencyCode`. Converter chỉ biết chuyển đổi; nó không nên phụ thuộc `HttpServletResponse`, `ResponseEntity` hoặc tầng controller.

### B. Khi gọi ConversionService trực tiếp: ConversionException

Nếu ứng dụng tự gọi `conversionService.convert(...)`, có thể xử lý `ConversionException` ở ranh giới phù hợp:

```java
try {
    TrackingCode code = conversionService.convert(
        rawValue, TrackingCode.class
    );
} catch (ConversionException ex) {
    // Chuyển thành lỗi input theo hợp đồng của use case.
}
```

`ConversionFailedException` là một dạng cụ thể của `ConversionException`. Có thể bắt lớp cha nếu muốn xử lý cả các thất bại chuyển đổi khác; bắt lớp cụ thể nếu cần metadata của source/target. Không bắt toàn bộ `RuntimeException` chỉ để trả về "input invalid", vì sẽ che lỗi lập trình hoặc lỗi hạ tầng.

### C. Khi bind vào JavaBean: TypeMismatchException và BindingResult

Trong property binding, Spring có thể chuyển lỗi chuyển đổi thành `TypeMismatchException` và ghi thành `FieldError` trong `BindingResult`. Với `DataBinder`, hãy kiểm tra:

```java
BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("quantity")) {
    // Input cho quantity không bind được hoặc không hợp lệ ở field.
}
```

Khi dùng `DataBinder`/`WebDataBinder`, không nhất thiết phải bắt exception quanh từng lời gọi converter; cơ chế binding thường quản lý lỗi theo mô hình `BindingResult`. Nếu muốn fail-fast, cấu hình và gọi API phù hợp; đừng giả định mọi lỗi đều thoát ra dưới dạng exception không được xử lý.

### D. Trong Spring MVC: exception theo loại tham số

Các tình huống thường gặp:

| Kiểu dữ liệu đầu vào | Ví dụ | Exception/đường lỗi thường gặp |
| --- | --- | --- |
| `@RequestParam int page` | `?page=abc` | `MethodArgumentTypeMismatchException` |
| `@PathVariable UUID id` | `/orders/not-a-uuid` | `MethodArgumentTypeMismatchException` trong handler mapping tương ứng |
| `@ModelAttribute` có property kiểu số | field `quantity` là `"abc"` | `BindingResult` có field error; nếu lỗi được ném ra, có thể là `BindException` |
| `@RequestBody` JSON không đọc/không chuyển được | JSON sai cú pháp/không phù hợp target | Exception converter/deserialization như `HttpMessageNotReadableException` |
| `@Valid @RequestBody` có constraint violation | `quantity < 1` sau khi parse được | `MethodArgumentNotValidException` theo luồng MVC thông dụng |

Đừng ném `MethodArgumentTypeMismatchException` bên trong converter. Exception đó cần metadata của method parameter, tên tham số, giá trị nhận được và kiểu cần thiết, thuộc tầng Spring MVC. Converter không nên biết controller nào đang gọi.

### E. Khi dữ liệu đã đúng kiểu nhưng sai nghiệp vụ

Ví dụ `quantity=0` parse thành công sang `Integer`, nhưng quy tắc đặt hàng yêu cầu lớn hơn 0. Đây không phải conversion failure. Hãy dùng Bean Validation (`@Min(1)`), Spring `Validator` hoặc rule nghiệp vụ phù hợp. Khi đó Spring MVC có thể trả `MethodArgumentNotValidException` hoặc ghi vào `BindingResult` tùy controller signature/điểm kích hoạt.

Không dùng `IllegalArgumentException` trong converter cho mọi quy tắc nghiệp vụ; converter nên tập trung vào việc tạo kiểu đích từ nguồn.

## 6. Ánh xạ sang HTTP response ở ranh giới web

Converter thường được dùng ở nhiều nơi: cấu hình bean, DataBinder, MVC, WebFlux, service hoặc code Java thuần. Nếu converter tự ném `ResponseStatusException` hoặc phụ thuộc Servlet API, nó không còn là converter reusable của Spring Core.

Ở Spring MVC, hãy ánh xạ lỗi tại controller advice hoặc handler. Ví dụ **minh họa** cho lỗi type mismatch ở request parameter:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.ResponseEntity;

@RestControllerAdvice
class ApiInputExceptionHandler {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<String> handleTypeMismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body("Invalid value for parameter: " + ex.getName());
    }
}
```

Đoạn code là ví dụ cho Spring MVC REST application đã có Spring Web. Nó không thay thế chương trình Java SE ở mục 4. Khi muốn bắt lỗi do custom converter được gọi trực tiếp từ service, có thể xử lý `ConversionException` tại service boundary hoặc chuyển thành exception ứng dụng; không nên ánh xạ tất cả conversion failures toàn cục nếu một số lỗi là lỗi cấu hình nội bộ.

Response thực tế nên có cấu trúc lỗi thống nhất, không gửi stack trace, tên class nội bộ hoặc raw input nhạy cảm cho client. Ví dụ JSON có thể là:

```json
{
  "error": "INVALID_INPUT",
  "field": "trackingCode",
  "message": "Tracking code must match LL-123456"
}
```

Đây là response schema do ứng dụng tự thiết kế; Spring không tự trả đúng JSON này nếu không có handler/exception mapping tương ứng.

## 7. Những lỗi thiết kế trong custom Converter

### 7.1. Trả null khi dữ liệu sai

```java
if (!valid(source)) {
    return null;
}
```

Cách này nguy hiểm vì caller không phân biệt được "không có giá trị" với "người dùng gửi giá trị không thể chuyển". Có thể gây lỗi ở một bước xa hơn, khó truy ra nguyên nhân. Nên ném `IllegalArgumentException` cho input không hợp lệ.

### 7.2. Nuốt exception rồi trả object mặc định

```java
try {
    return parse(source);
} catch (RuntimeException ex) {
    return DEFAULT_VALUE;
}
```

Đây là silent fallback. Ví dụ mã tiền tệ sai nhưng được chuyển thành VND mặc định có thể gây sai dữ liệu. Chỉ dùng fallback nếu đó là chính sách nghiệp vụ tường minh và được đặt ở tầng thích hợp, không che giấu lỗi parse.

### 7.3. Ném checked exception từ Converter

`Converter.convert` không khai báo checked exception. Không nên bọc checked exception tùy tiện trong exception nghiệp vụ phức tạp nếu lỗi thực chất chỉ là input không thể chuyển. Chọn `IllegalArgumentException` cho invalid source; nếu xảy ra lỗi hạ tầng nghiêm trọng hoặc không phải lỗi input, hãy để exception thích hợp nổi lên và xử lý ở lớp bao quanh.

### 7.4. Gắn HTTP status vào converter

Ném `ResponseStatusException` ngay trong converter trói Spring Core vào web. Converter có thể được gọi từ batch job hoặc service, nơi HTTP status không có ý nghĩa. Hãy để web adapter quyết định status tương ứng.

### 7.5. Bắt mọi exception và biến thành 400

Một lỗi database, null pointer do code sai hoặc converter bị cấu hình thiếu có thể là lỗi server, không phải lỗi input. Chỉ ánh xạ các loại lỗi đã xác định là client-caused; log đủ thông tin kỹ thuật ở server với dữ liệu nhạy cảm được lọc.

### 7.6. Dùng exception thay validation

Giá trị `"16"` chuyển thành Integer thành công, nhưng tuổi tối thiểu là 18. Đây là constraint, không phải lỗi chuyển đổi. Dùng `@Min(18)` hoặc validator phù hợp.

## 8. Kiểm thử converter và exception

Với converter thuần, cần ít nhất các ca:

| Test | Input | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | `AB-123456` | Trả `TrackingCode` đúng giá trị |
| Sai cấu trúc | `bad-code` | Converter ném `IllegalArgumentException` nếu gọi trực tiếp |
| Gọi qua ConversionService | `bad-code` | `ConversionFailedException` và cause là `IllegalArgumentException` |
| Kiểu target không hỗ trợ | một target type không có converter | Có thể là `ConverterNotFoundException`, không phải invalid source |
| Nguồn null | phụ thuộc hợp đồng nullable/caller | Không mặc định coi như chuỗi sai định dạng; kiểm tra API path |
| Collection chứa phần tử sai | danh sách có một item sai | Conversion có thể thất bại ở phần tử; kiểm tra exception cause |

Ví dụ test JUnit 5 cho việc converter từ chối source:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class TrackingCodeConverterTest {

    private final ConverterInvalidInputDemo.StringToTrackingCode converter =
        new ConverterInvalidInputDemo.StringToTrackingCode();

    @Test
    void rejectsInvalidSource() {
        assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("bad-code")
        );
    }
}
```

Đây là snippet test phụ thuộc JUnit 5 và class từ ví dụ mục 4. Một test ở cấp ConversionService nên xác nhận exception bọc và nguyên nhân:

```java
assertThrows(
    ConversionFailedException.class,
    () -> service.convert("bad-code", TrackingCode.class)
);
```

Ngoài kiểm tra exception type, nên khẳng định `getCause()` là `IllegalArgumentException`. Không nên khóa test vào toàn bộ câu chữ message nếu message có thể được hiệu chỉnh; kiểm tra error code/field và nội dung cần thiết theo hợp đồng public.

## 9. Quy trình lựa chọn ngoại lệ

Khi xử lý một đầu vào không hợp lệ, hãy lần lượt đặt câu hỏi:

1. **Đầu vào có chuyển được sang target type không?** Nếu không, custom `Converter` ném `IllegalArgumentException`; ConversionService xử lý thành conversion failure.
2. **Không có converter cho cặp source/target?** Đây thường là vấn đề khả năng/cấu hình chuyển đổi, như `ConverterNotFoundException`; không nên báo người dùng sai định dạng nếu thực ra ứng dụng thiếu converter.
3. **Chuyển kiểu thành công nhưng vi phạm constraint?** Dùng Bean Validation hoặc Spring Validator; không giả lập conversion error.
4. **Lỗi xuất hiện trong bean property binding?** Đọc `BindingResult`/`FieldError` hoặc xử lý exception binding phù hợp.
5. **Lỗi ở request parameter/path variable?** Dùng exception do Spring MVC cung cấp ở tầng method argument, ví dụ `MethodArgumentTypeMismatchException`.
6. **Lỗi khi đọc JSON body?** Xem exception của `HttpMessageConverter`/Jackson, thường `HttpMessageNotReadableException`.
7. **Chọn HTTP status ở đâu?** Ở controller advice hoặc web boundary, theo hợp đồng API; converter reusable không tự quyết định HTTP.

## 10. Câu hỏi tự kiểm tra

1. Vì sao custom `Converter<String, T>` nên ném `IllegalArgumentException` khi source không thể chuyển?
2. Khi converter ném lỗi qua `DefaultConversionService`, exception nào thường bọc nguyên nhân? Làm sao lấy cause?
3. `ConverterNotFoundException` khác `ConversionFailedException` thế nào?
4. Vì sao converter không nên ném `ResponseStatusException`?
5. Khi `@RequestParam int page` nhận `abc`, tầng MVC có thể báo exception nào?
6. Một số nguyên chuyển kiểu thành công nhưng nhỏ hơn giới hạn nghiệp vụ là conversion error hay validation error?
7. Vì sao trả `null` hoặc giá trị mặc định cho invalid source có thể làm lỗi khó phát hiện?
8. Khi dùng `DataBinder`/`BindingResult`, tại sao không nhất thiết phải bắt exception converter quanh từng property?
9. Vì sao không nên ánh xạ mọi `RuntimeException` thành HTTP 400?

**Ghi nhớ:** Custom Spring `Converter` dùng `IllegalArgumentException` để báo giá trị nguồn không hợp lệ. Khi chạy qua `ConversionService`, Spring có thể bọc thành `ConversionFailedException`. Property binding và Spring MVC có các loại lỗi chuyên biệt ở tầng trên. Hãy để converter báo lỗi chuyển đổi, validator báo lỗi constraint và web boundary quyết định HTTP response.

## Tài liệu tham khảo

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework 6.1 — `Converter<S,T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Spring Framework 6.1 — `ConversionFailedException` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionFailedException.html
- Spring Framework 6.1 — `ConversionService` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework — Spring MVC Exceptions: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-exceptions.html
