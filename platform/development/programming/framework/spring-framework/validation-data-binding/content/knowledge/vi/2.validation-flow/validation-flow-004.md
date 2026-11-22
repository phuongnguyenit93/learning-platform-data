# Chuyển từ chuỗi sang kiểu dữ liệu đích trong Spring Framework

## 1. Vì sao cần chuyển đổi kiểu?

Khi Spring nhận dữ liệu từ HTTP request, nhiều giá trị ban đầu là chuỗi: query parameter, path variable, form field hoặc từng phần tử của dữ liệu biểu mẫu. Tuy nhiên, tham số controller và thuộc tính object có thể khai báo là `int`, `long`, `BigDecimal`, `LocalDate`, `Enum` hoặc kiểu miền nghiệp vụ. Spring cần **chuyển đổi chuỗi nguồn thành kiểu Java đích** trước khi gán giá trị (data binding) hay gọi phương thức.

Ví dụ, `GET /orders?quantity=3&date=2026-11-02` có thể được ánh xạ thành `Integer quantity` và `LocalDate date`. Hai giá trị `"3"` và `"2026-11-02"` là chuỗi ở request nhưng được Spring chuyển thành object phù hợp.

Cần phân biệt:
- **Conversion**: biến `"3"` thành `Integer.valueOf(3)`, `"ACTIVE"` thành enum, hoặc `"2026-11-02"` thành ngày.
- **Binding**: gán giá trị đã chuyển đổi vào tham số hoặc thuộc tính object; có thể bao gồm nested property và collection.
- **Validation**: kiểm tra ràng buộc *sau* khi dữ liệu đã được chuyển đổi/bind, ví dụ số lượng phải lớn hơn 0. Conversion failure không giống validation failure.

## 2. Luồng xử lý tổng quát

```text
HTTP request (chuỗi / tập giá trị nguồn)
        |
        v
HandlerMethodArgumentResolver hoặc WebDataBinder
        |
        v
Tra cứu bộ chuyển đổi theo source type -> target type
        |
        +-- Converter / ConverterFactory / GenericConverter
        |   (và Formatter/Parser cho biểu diễn phụ thuộc locale)
        v
Giá trị Java đã chuyển đổi
        |
        v
Gán vào tham số @RequestParam, @PathVariable,
@ModelAttribute hoặc property của object
        |
        v
Validation (khi được kích hoạt) -> controller nếu thành công
```

Spring cung cấp hệ thống `ConversionService` (trong `org.springframework.core.convert`) để chuyển đổi kiểu độc lập với web layer. `GenericConversionService` quản lý các converter; `DefaultConversionService` đăng ký nhiều bộ chuyển đổi phổ biến; `DefaultFormattingConversionService` bổ sung các formatter cho số, ngày và các kiểu có biểu diễn phụ thuộc locale. Trong Spring MVC, việc chuyển đổi cho binding thường được thực hiện thông qua `WebDataBinder` và cơ chế cấu hình MVC.

Khả năng chuyển đổi thực tế phụ thuộc vào `ConversionService` được cấu hình. Không nên mặc định mọi chuỗi hay mọi định dạng ngày đều được chấp nhận.

## 3. Các kiểu chuyển đổi thường gặp

| Chuỗi nguồn | Kiểu đích | Ví dụ kết quả | Điều cần chú ý |
| --- | --- | --- | --- |
| `"42"` | `Integer` / `int` | `42` | Chuỗi không hợp lệ hoặc tràn phạm vi gây lỗi chuyển đổi |
| `"true"` | `Boolean` / `boolean` | `true` | Các biểu diễn được chấp nhận tùy converter đã đăng ký |
| `"19.95"` | `BigDecimal` | `19.95` | Chú ý dấu thập phân và locale khi dùng formatter |
| `"2026-11-02"` | `LocalDate` | ngày 02/11/2026 | Nên khai báo rõ định dạng bằng `@DateTimeFormat` |
| `"ACTIVE"` | `Status` enum | `Status.ACTIVE` | Converter enum mặc định dùng tên hằng, phân biệt hoa/thường |
| `"a,b,c"` | `List<String>` | `[a,b,c]` | ConversionService có converter liên quan, nhưng quy tắc binding request có thể khác theo nguồn và cấu hình |

Các trường hợp như chuỗi trống, `null`, giá trị primitive, hoặc giá trị có khoảng trắng cần được kiểm tra với cấu hình thật. Đặc biệt, một chuyển đổi trả về `null` không thể đáp ứng tham số primitive.

## 4. Ví dụ với tham số Spring MVC

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders")
    String query(
            @RequestParam int quantity,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate date) {
        return "quantity=" + quantity + ", date=" + date;
    }
}
```

Request:

```http
GET /orders?quantity=3&date=2026-11-02
```

Response body khi request hợp lệ:

```text
quantity=3, date=2026-11-02
```

`@RequestParam` lấy giá trị từ request, Spring chuyển `"3"` sang `int`, `@DateTimeFormat` hướng dẫn parser đọc ngày theo ISO. Nếu `quantity=abc`, lỗi xảy ra **trước khi phương thức `query` chạy**. Nếu thiếu `quantity` bắt buộc, lỗi missing parameter khác với lỗi không chuyển được `"abc"`.

Ví dụ ở trên là controller dùng trong ứng dụng Spring MVC đã cấu hình; nó không phải một chương trình Java độc lập chạy bằng `java OrderController`.

## 5. Chuyển đổi trên `@ModelAttribute` và form binding

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class RegistrationForm {
    private Integer age;
    private BigDecimal budget;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public BigDecimal getBudget() { return budget; }
    public void setBudget(BigDecimal budget) { this.budget = budget; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) { this.startDate = startDate; }
}
```

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
class RegistrationController {

    @PostMapping("/register")
    @ResponseBody
    String register(@ModelAttribute RegistrationForm form,
                    BindingResult bindingResult) {
        if (bindingResult.hasErrors()) {
            return "Invalid input";
        }
        return "age=" + form.getAge()
                + ", budget=" + form.getBudget()
                + ", startDate=" + form.getStartDate();
    }
}
```

Khi gửi form fields `age=28`, `budget=150.50`, `startDate=2026-11-02`, binder cố chuyển từng giá trị và gán vào property tương ứng. `BindingResult` phải nằm **ngay sau** tham số model được bind mà nó mô tả; binder có thể lưu field error (ví dụ `typeMismatch`) để controller xử lý. Đừng suy luận rằng một field chuyển đổi thất bại chắc chắn có giá trị mặc định hợp lệ; cần kiểm tra lỗi trước khi sử dụng.

Trong các API JSON với `@RequestBody`, JSON deserialization do `HttpMessageConverter` (thường là Jackson) thực hiện; không đồng nhất nó với luồng string-to-type của `WebDataBinder` cho query/form/path variables. Annotation `@DateTimeFormat` cũng không thay thế cấu hình JSON date format của Jackson.

## 6. Tự định nghĩa `Converter<S, T>`

Dùng converter khi cần ánh xạ từ một kiểu nguồn xác định tới kiểu đích và **không phụ thuộc locale**. Ví dụ chuyển mã sản phẩm dạng chuỗi sang value object:

```java
public record ProductCode(String value) {
    public ProductCode {
        if (value == null || !value.matches("[A-Z]{2}-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
```

```java
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source.trim());
    }
}
```

Để Spring MVC sử dụng converter trên các tham số và property được bind, đăng ký qua `WebMvcConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
    }
}
```

Sau đó:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {
    @GetMapping("/products/{code}")
    String find(@PathVariable ProductCode code) {
        return code.value();
    }
}
```

Request `GET /products/AB-1234` được chuyển thành `new ProductCode("AB-1234")` rồi trả `AB-1234`. Request `GET /products/bad` gây lỗi chuyển đổi; framework xử lý theo cơ chế lỗi của tham số/binding và cấu hình exception handler. Không nên dựa vào thông điệp ngoại lệ cụ thể trong contract API.

`ConverterFactory<S, R>` phù hợp khi một nguồn cần chuyển thành nhiều subtype thuộc cùng họ, chẳng hạn các enum. `GenericConverter` hỗ trợ chuyển đổi có tính đến `TypeDescriptor` và kiểu lồng nhau, đổi lại phức tạp hơn; chỉ dùng khi `Converter` đơn giản không đáp ứng được.

## 7. `Formatter<T>` và xử lý locale

`Formatter<T>` gồm `parse(String, Locale)` và `print(T, Locale)`. Nó hữu ích cho số tiền, ngày/giờ hay những giá trị có biểu diễn thay đổi theo `Locale`. `Converter` chỉ nhận nguồn và không có tham số locale.

Ví dụ parser/formatter cho một kiểu tiền tệ miền nghiệp vụ có thể quyết định dấu phân cách thập phân dựa trên `Locale`. Khi chỉ cần định dạng ngày chuẩn, ưu tiên annotation có sẵn:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate effectiveDate;
```

Hoặc dùng pattern rõ ràng:

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate effectiveDate;
```

Pattern phải tương thích với dữ liệu thực tế, ví dụ `02/11/2026` cho `dd/MM/yyyy`. Đừng dùng một định dạng nhập ngày không xác định rồi dựa vào locale mặc định của máy chủ. Với Spring Boot, các converter/formatter bổ sung và cấu hình conversion có thể phụ thuộc vào loại context; cần kiểm chứng đúng MVC ConversionService đang hoạt động.

## 8. Gọi `ConversionService` trực tiếp

Có thể tách kiểm thử logic chuyển đổi khỏi web layer. Ví dụ sau là một class Java độc lập về mặt cấu trúc, nhưng cần các JAR của Spring Core trên classpath:

```java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionDemo {
    public static void main(String[] args) {
        ConversionService service = new DefaultConversionService();

        Integer count = service.convert("12", Integer.class);
        Boolean enabled = service.convert("true", Boolean.class);

        System.out.println(count);
        System.out.println(enabled);
    }
}
```

Output:

```text
12
true
```

Với Maven/Gradle, khai báo dependency `org.springframework:spring-core` phù hợp phiên bản Spring của dự án. Sau khi build, chạy `ConversionDemo` với runtime classpath chứa Spring Core và các dependency liên quan. `javac ConversionDemo.java` đơn lẻ không chạy được nếu thiếu JAR Spring. `ConversionService#canConvert(String.class, Integer.class)` có thể kiểm tra sự tồn tại của đường chuyển đổi, nhưng **không bảo đảm** chuỗi cụ thể `"xyz"` hợp lệ.

## 9. Lỗi thường gặp và cách xử lý

- **Không thể parse số hoặc ngày**: dùng kiểu đích và `@DateTimeFormat` phù hợp, trả lỗi 400 với thông tin field có ích; không tự diễn giải chuỗi sai thành `0`.
- **Enum không khớp tên hằng**: mặc định thường cần tên enum chính xác. Nếu API cho phép bí danh hoặc không phân biệt chữ hoa/chữ thường, tạo converter rõ ràng; tránh thay đổi ngữ nghĩa toàn cục vô tình.
- **Sai locale/dấu thập phân**: phân biệt kiểu dữ liệu truyền qua API máy-máy với biểu diễn trong form cho người dùng. Với API, thống nhất định dạng và tài liệu hóa nó.
- **Converter không được gọi**: kiểm tra đã đăng ký với đúng `ConversionService`/MVC context, generic source/target type và có converter khác ưu tiên hơn không.
- **Dùng `@Valid` để xử lý parse failure**: validation constraints không sửa chuỗi không thể chuyển đổi; giải quyết lỗi binding và validation riêng.
- **Nhầm `@RequestBody` với `@ModelAttribute`**: JSON sử dụng deserializer, còn query/path/form thường qua binder/conversion; kiểm thử đường thực tế.
- **Tạo converter quá rộng**: tránh converter `String -> Object` có hành vi bất ngờ với mọi tham số; chọn kiểu đích cụ thể và báo lỗi rõ ràng.
- **Không xử lý `BindingResult`**: trong form, đặt ngay sau model attribute tương ứng để có thể trả thông báo lỗi field; trong REST controller xử lý exceptions phù hợp bằng `@ControllerAdvice` nếu muốn response thống nhất.

## 10. Checklist khi áp dụng

1. Xác định nguồn dữ liệu (query/path/form/JSON), kiểu Java đích và cơ chế Spring sử dụng.
2. Ưu tiên các converter/formatter mặc định, khai báo định dạng chính xác cho ngày và số.
3. Viết converter riêng cho quy tắc miền nghiệp vụ, đăng ký vào đúng registry.
4. Kiểm thử giá trị hợp lệ, rỗng, sai format, vượt phạm vi và locale liên quan.
5. Xử lý lỗi chuyển đổi/binding một cách dự đoán được trước khi dùng object; chạy validation riêng cho các ràng buộc miền nghiệp vụ.
6. Giữ contract HTTP rõ ràng, ví dụ: `quantity` là số nguyên dương và `date` theo ISO `yyyy-MM-dd`.

**Ý chính:** Spring chuyển giá trị chuỗi sang kiểu Java đích thông qua conversion/formatting infrastructure, rồi mới bind và validate. Hiểu đúng nguồn dữ liệu, converter được đăng ký và cách lỗi được báo cáo giúp tránh những lỗi nhập liệu âm thầm hoặc khó chẩn đoán.
