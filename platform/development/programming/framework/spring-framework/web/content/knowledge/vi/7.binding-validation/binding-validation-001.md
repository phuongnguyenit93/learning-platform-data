# WebDataBinder và quá trình chuyển dữ liệu chuỗi thành đối tượng trong Spring MVC

## 1. Học được gì sau bài này?

Khi trình duyệt gửi biểu mẫu `quantity=3&deliveryDate=2026-12-24&code=sku-007`, mọi giá trị đầu vào đều có thể xuất phát dưới dạng chuỗi, nhưng controller lại cần `Integer`, `LocalDate` và một kiểu miền nghiệp vụ như `ProductCode`. **Data binding** là quá trình kết nối tên tham số với thuộc tính hoặc tham số constructor của đối tượng Java, đồng thời thực hiện **type conversion** cần thiết. `WebDataBinder` là thành phần chuyên biệt cho tình huống web của Spring MVC.

Sau bài học, bạn sẽ biết:

- `WebDataBinder` tham gia luồng xử lý `@ModelAttribute` thế nào; đâu là nhiệm vụ của `DataBinder`, `ConversionService`, `Formatter` và `PropertyEditor`.
- Từ `String` đầu vào đến object Java: ánh xạ tên, tạo đối tượng, gán thuộc tính hoặc gọi constructor, chuyển kiểu, ghi nhận lỗi.
- Phân biệt cấu hình conversion **toàn cục** và cấu hình binder **theo controller/model attribute** bằng `WebMvcConfigurer` và `@InitBinder`.
- Đọc lỗi qua `BindingResult`; phân biệt lỗi chuyển kiểu, trường không được bind và kiểm tra hợp lệ nghiệp vụ.
- Bảo vệ object khỏi việc client gán vào thuộc tính không được phép (`mass assignment`) bằng DTO và `allowedFields`.
- Tự chạy và kiểm thử một ứng dụng Spring Boot 3.x / Spring MVC với Java 17+.

**Phạm vi:** Spring MVC chạy trên Servlet stack (Spring Framework 6.x). `WebFlux` có luồng HTTP khác; `@RequestBody` đọc JSON qua `HttpMessageConverter`, không tương đương với việc bind tham số form bằng `WebDataBinder`.

## 2. WebDataBinder nằm ở đâu trong chuỗi xử lý?

Để hiểu đúng cơ chế, cần phân biệt ba khái niệm:

1. **Binding:** tìm giá trị nguồn theo tên `customer`, `quantity` hoặc đường dẫn `address.city`, rồi đưa chúng vào đích tương ứng.
2. **Conversion/formatting:** biến `"3"` thành `Integer(3)`, `"2026-12-24"` thành `LocalDate`, `"sku-007"` thành `ProductCode`; khi hiển thị form có thể định dạng ngược đối tượng thành văn bản.
3. **Validation:** sau binding, đánh giá quy tắc như `quantity > 0` hoặc `customer` không rỗng. Giá trị chuyển kiểu thành công chưa chắc hợp lệ về nghiệp vụ.

Sơ đồ khái quát với `@ModelAttribute`:

```text
POST /orders/form
Content-Type: application/x-www-form-urlencoded

customer=Ada&quantity=3&deliveryDate=2026-12-24&code=sku-007
       │
       ▼
DispatcherServlet → RequestMappingHandlerAdapter
       │
       ▼
Bộ phân giải tham số @ModelAttribute
       │
       ├─ Tìm hoặc tạo object đích (OrderForm)
       ├─ Tạo và khởi tạo WebDataBinder
       │    ├─ Cấu hình ConversionService/Formatter/PropertyEditor
       │    ├─ Chạy @InitBinder phù hợp
       │    └─ Áp dụng allowedFields và các quy tắc binding
       ├─ Bind dữ liệu vào object
       │    └─ Chuyển String → kiểu Java, ghi lỗi nếu thất bại
       ├─ Chạy validation nếu được yêu cầu, ví dụ @Valid
       └─ Cung cấp OrderForm + BindingResult cho controller
       │
       ▼
Controller xử lý object đã bind / lỗi
```

`org.springframework.validation.DataBinder` xử lý binding và validation ở mức tổng quát. `org.springframework.web.bind.WebDataBinder` mở rộng cho ngữ cảnh web, gồm các quy tắc làm việc với tham số request. Spring MVC thường tạo binder cho **từng đối tượng cần bind ở request**, thông qua cơ sở hạ tầng `WebDataBinderFactory`; không lưu một `WebDataBinder` đang thao tác vào singleton service để tái dùng giữa nhiều request.

`BeanWrapper` hoặc cơ chế truy cập property của Spring hỗ trợ tìm thuộc tính JavaBean; `ConversionService`/formatter/editor xử lý bước biến đổi kiểu. `BindingResult` giữ cả lỗi binding và validation. Không coi `WebDataBinder` là JSON parser hoặc cơ chế routing URL.

### Những nguồn dữ liệu nào được bind?

Với `@ModelAttribute` trong Spring MVC, tên trường có thể lấy từ request parameters (query string và form-urlencoded data), URI variables và request headers ở những tình huống phù hợp. Tham số request có ưu tiên hơn URI variables/header nếu trùng tên. Một object có thể đến từ model/session, được tạo bằng constructor, hoặc được tìm qua converter trong một số trường hợp.

| Controller argument | Input điển hình | Cơ chế chính |
| --- | --- | --- |
| `@RequestParam Integer page` | `?page=3` | Chuyển giá trị tham số sang kiểu method argument |
| `@PathVariable UUID id` | `/orders/{id}` | Chuyển giá trị path variable |
| `@RequestHeader LocalDate date` | HTTP header tương ứng, nếu có converter phù hợp | Chuyển giá trị header |
| `@ModelAttribute OrderForm form` | `customer=Ada&quantity=3` | Tạo/tìm object, bind nhiều property, có thể validate |
| `@RequestBody OrderJson body` | JSON như `{"quantity":3}` | `HttpMessageConverter` (thường là Jackson), rồi có thể validate |

`@RequestParam` và `@PathVariable` cũng tận dụng hệ thống chuyển kiểu và có thể được tùy chỉnh thông qua cấu hình conversion hoặc binder phù hợp; nhưng chúng **không** tạo một object form nhiều thuộc tính như `@ModelAttribute`.

## 3. Từ chuỗi đến object: điều gì thực sự xảy ra?

Xét form:

```text
customer=Ada
quantity=3
deliveryDate=2026-12-24
code=sku-007
```

Và Java bean:

```java
public class OrderForm {
    private String customer;
    private Integer quantity;
    private LocalDate deliveryDate;
    private ProductCode code;

    public OrderForm() { }

    public void setCustomer(String customer) { this.customer = customer; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public void setDeliveryDate(LocalDate deliveryDate) { this.deliveryDate = deliveryDate; }
    public void setCode(ProductCode code) { this.code = code; }

    // Các getter được lược bỏ trong đoạn minh họa này.
}
```

*Đây là đoạn minh họa riêng của model; chương 7 có ví dụ project đầy đủ với import, getter, setter và test.*

Trình tự khái quát:

1. Spring xác định tên model attribute (`orderForm`), tìm object đã có hoặc tạo `OrderForm`.
2. `WebDataBinder` đối chiếu các trường nguồn với property đích cùng tên. Với binding kiểu JavaBean, setter/đường dẫn property phải phù hợp.
3. `customer` vốn là `String` nên gán trực tiếp; `quantity` cần converter sang `Integer`; `deliveryDate` cần quy tắc parse ngày; `code` cần quy tắc tùy biến sang `ProductCode`.
4. Nếu chuyển đổi thất bại, binder ghi `FieldError`, ví dụ field `quantity` với lỗi `typeMismatch`. Không được giả định Spring sẽ âm thầm đổi `"abc"` thành `0`.
5. Nếu method có `@Valid`/`@Validated` phù hợp, validation chạy sau khi có đối tượng đã bind và lỗi có thể được cộng thêm vào `BindingResult`.
6. Controller chỉ nên xử lý nghiệp vụ khi trạng thái binding và validation đã đạt yêu cầu.

Tên property có thể lồng nhau, ví dụ `address.city`, `items[0].sku`. Binding lồng nhau phụ thuộc vào cấu trúc object, setter/constructor, khả năng auto-grow và chính sách giới hạn của binder. Không mở rộng tùy tiện sang bất kỳ property nào client tự gửi: một field nhạy cảm như `role` hoặc `isAdmin` có thể bị gán trái phép nếu thiết kế object thiếu an toàn.

### Constructor binding và property binding

`@ModelAttribute` có thể khởi tạo object qua constructor có tham số; Spring cũng có thể bind các thuộc tính có thể ghi sau đó. Với Java record:

```java
public record SearchFilter(String keyword, Integer page) { }
```

Input `keyword=spring&page=2` có thể dùng để tạo `SearchFilter("spring", 2)` thông qua constructor binding. Với kiểu bất biến, tên tham số phải được framework nhận biết đúng (cấu hình biên dịch/metadata phù hợp), và tên input phải khớp với tham số; `@BindParam` hỗ trợ đổi tên tham số web trong Spring 6.1+.

Với JavaBean có no-args constructor/setters, property binding là con đường tự nhiên. Đó là cách ví dụ chính phía dưới minh họa. Đối với input không tin cậy, object chuyên dùng cho request và constructor binding hạn chế số điểm có thể gán thường an toàn hơn việc đưa thẳng entity persistence ra binder.

## 4. ConversionService, Converter, Formatter và PropertyEditor

`WebDataBinder` không tự hiểu tất cả các kiểu Java do bạn định nghĩa. Nó dựa trên hệ thống chuyển đổi đã cấu hình.

| Thành phần | Trách nhiệm | Khi nên dùng |
| --- | --- | --- |
| `ConversionService` | API trung tâm `canConvert`/`convert`; điều phối converters | Dùng chung cho nhiều nơi cần chuyển kiểu |
| `Converter<S,T>` | Chuyển một kiểu nguồn sang một kiểu đích | Ví dụ `String → ProductCode`, `String → UUID` (nếu cần tùy biến) |
| `ConverterFactory<S,R>` | Tạo converter cho một họ kiểu đích | Nhiều enum/kiểu con theo cùng quy tắc |
| `GenericConverter` | Quy tắc dựa trên `TypeDescriptor`/generic/annotation | Chuyển đổi cần biết kiểu phần tử hay metadata |
| `Formatter<T>` | Parse văn bản thành `T` và print `T` thành văn bản, có `Locale` | Số/tiền tệ/ngày theo ngôn ngữ/vùng |
| `PropertyEditor` | API JavaBeans cũ, có trạng thái và các thao tác `setAsText` | Tích hợp thư viện cũ hoặc custom editor cục bộ |

### Converter: khi quy tắc không phụ thuộc Locale

Ví dụ mã sản phẩm có định dạng `SKU-007`:

```java
record ProductCode(String value) {}

final class ProductCodeConverter
        implements org.springframework.core.convert.converter.Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(java.util.Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{3}")) {
            throw new IllegalArgumentException("Mã sản phẩm phải có dạng SKU-000");
        }
        return new ProductCode(normalized);
    }
}
```

`Converter` nhận `String` và trả về **object miền nghiệp vụ**, không chỉ kiểm tra string. Chuyển `"sku-007"` thành `ProductCode("SKU-007")`; `"abc"` làm quá trình conversion thất bại. `IllegalArgumentException` tại converter là một cách báo đầu vào sai. Converter dùng chung cần an toàn với nhiều thread; tránh cất dữ liệu request trong field mutable của converter.

### Formatter: khi ngày/số phụ thuộc định dạng nhập/xuất

`@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` có thể đặt trên thuộc tính `LocalDate` để biểu diễn ngày ISO `2026-12-24`. `@NumberFormat` hỗ trợ một số trường hợp định dạng số. Khi cần quy tắc phức tạp và phụ thuộc `Locale`, hãy viết `Formatter<T>` với `parse(String, Locale)` và `print(T, Locale)`.

Không lấy `LocalDate.parse(...)` trong từng controller để tự thay thế cơ chế binding chung. Khi viết converter/formatter, cần kiểm tra chuỗi rỗng, khoảng trắng, định dạng không hợp lệ, múi giờ (khi chuyển loại có thông tin thời điểm), và việc parse/print có đối xứng hay không.

### PropertyEditor: hiểu để bảo trì mã cũ

`PropertyEditor` thường được đăng ký trên một binder bằng `registerCustomEditor` trong `@InitBinder`. Một editor có thể giữ giá trị nội bộ, nên không tùy tiện chia sẻ cùng instance mutable giữa requests. Với ứng dụng Spring MVC hiện đại, ưu tiên `Converter`/`Formatter` cho nhu cầu mới.

## 5. Cấu hình conversion toàn cục và @InitBinder theo phạm vi

### Toàn cục qua WebMvcConfigurer

`WebMvcConfigurer#addFormatters(FormatterRegistry)` đăng ký converter hoặc formatter mà cơ chế chuyển kiểu của MVC dùng trên nhiều controller:

```java
@Configuration
class WebBindingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}
```

*Đoạn này là trích từ ứng dụng đầy đủ ở mục 7; thêm đúng import `@Configuration`, `WebMvcConfigurer` và `FormatterRegistry` như trong ví dụ.*

Ưu điểm là một định nghĩa `String → ProductCode` có thể dùng cho `@RequestParam ProductCode`, `@PathVariable ProductCode` hoặc property kiểu `ProductCode` trong `@ModelAttribute`. Không tạo `ConversionService` mới trong từng controller nếu muốn tận dụng cấu hình MVC hiện có.

### Theo controller/model attribute qua @InitBinder

`@InitBinder` được gọi để tùy chỉnh `WebDataBinder` trước quá trình binding. Có thể đặt trong `@Controller`/`@RestController` cho phạm vi controller; hoặc trong `@ControllerAdvice` khi cần áp dụng cho nhiều controller. `@InitBinder("orderForm")` chỉ nhắm vào model attribute có tên `orderForm`.

```java
@InitBinder("orderForm")
void configureOrderForm(WebDataBinder binder) {
    binder.setAllowedFields("customer", "quantity", "deliveryDate", "code");
}
```

`allowedFields` giúp chỉ cho phép các property đã chỉ định được set bằng property binding. Nếu client gửi thêm `admin=true`, Spring đưa `admin` vào danh sách `getSuppressedFields()` thay vì gán property đó (khi không nằm trong danh sách cho phép). `BindingResult#getSuppressedFields()` giúp bạn phát hiện và quyết định trả lỗi. `setDisallowedFields` cũng có, nhưng danh sách được **cho phép** rõ ràng thường dễ kiểm soát hơn danh sách các tên bị cấm.

Một số cấu hình binder cần biết:

- `setRequiredFields("customer")` yêu cầu trường xuất hiện khi bind; đây là quy tắc hiện diện ở tầng binding, **khác** `@NotBlank` hay kiểm tra ý nghĩa của giá trị.
- `setAllowedFields(...)` và `setDisallowedFields(...)` áp dụng cho tên field được bind, có thể nhận các pattern; không xem chúng là firewall thay cho DTO phù hợp.
- `setDeclarativeBinding(true)` (Spring 6.1+) cho phép thiên về constructor binding; property binding bị hạn chế nếu không cấu hình allowed fields. Hữu ích khi DTO bất biến hoặc muốn chặn sửa property ngoài khai báo.
- Có thể đăng ký `Formatter`/`PropertyEditor` và validator theo binder, nhưng chuyển kiểu dùng chung nên đặt trong cấu hình MVC.
- Nếu muốn lấy object sẵn có từ model mà không cho binding dữ liệu request vào, cân nhắc `@ModelAttribute(binding = false)`.

**Quan trọng về bảo mật:** không dùng persistence entity chứa `role`, `isAdmin`, `creditLimit` làm input model tự do nếu client không được quyền chỉnh các trường ấy. Phân quyền và cập nhật entity nên làm tại service sau khi DTO đã được kiểm tra; `allowedFields` là một lớp bảo vệ bổ sung cho property binding.

## 6. BindingResult: theo dõi lỗi chuyển đổi và validation

`BindingResult` giữ lỗi theo **object** và **field**. Khi controller khai báo nó, hãy đặt **ngay sau** tham số `@ModelAttribute` tương ứng:

```java
@PostMapping("/example")
String submit(@ModelAttribute("orderForm") OrderForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "invalid";
    }
    return "ok";
}
```

*Đây là minh họa chữ ký method; mục 7 chứa chương trình chạy đầy đủ.*

Một `FieldError` có thể chứa `field`, `rejectedValue`, `codes` và thông điệp lỗi. Ví dụ `quantity=abc` trong khi đích là `Integer` thường ghi lỗi `typeMismatch` cho `quantity`. Nếu có `@Valid` và Jakarta Bean Validation được cấu hình, lỗi như `NotNull`, `Min`, `NotBlank` cũng được đưa vào kết quả. `@Valid` không phải điều kiện để Spring **chuyển kiểu**; binding và conversion vẫn xảy ra khi không có `@Valid`.

Phân loại:

| Request | Điểm hỏng | Cách đọc |
| --- | --- | --- |
| `quantity=abc` → `Integer` | Chuyển kiểu | `hasFieldErrors("quantity")`, mã `typeMismatch` |
| `deliveryDate=tomorrow` → `LocalDate` theo ISO | Chuyển kiểu | `FieldError` của `deliveryDate` |
| `quantity=-2` và `@Min(1)` | Validation, **không** phải lỗi chuyển kiểu | `FieldError` từ Bean Validation |
| `admin=true` nhưng chỉ cho bind 4 field khác | Bị chặn bởi allowed fields | `getSuppressedFields()` có `admin` |
| Không gửi `customer` | Có thể còn `null` nếu không đặt required/validation | Cần chính sách `setRequiredFields` hoặc `@NotBlank` tương ứng |

Khi không có `BindingResult` đi kèm để xử lý tại controller, một số lỗi binding/validation của `@ModelAttribute` có thể được Spring MVC đẩy thành exception, thường được ánh xạ sang phản hồi lỗi mặc định. Khi bind trong method đã có `BindingResult`, controller chịu trách nhiệm kiểm tra; **không tiếp tục chạy nghiệp vụ khi `result.hasErrors()`**.

Lưu ý: `@Valid` kiểm tra constraint đã khai báo trên object, không tự động đảm bảo nghiệp vụ hay quyền truy cập. Lỗi parser JSON của `@RequestBody` có thể ném exception như `HttpMessageNotReadableException` trước khi tới controller; cách chẩn đoán khác với `FieldError` của form binding.

## 7. Ví dụ Spring Boot 3 + Java 17 chạy được

Đây là ứng dụng hoàn chỉnh minh họa `WebDataBinder`, `@InitBinder`, `Converter<String, ProductCode>`, `@DateTimeFormat` và `BindingResult`. Chúng ta dùng Spring Boot **3.3.13**, Java **17+**, Maven, không cần cơ sở dữ liệu.

Cấu trúc project:

```text
web-data-binder-demo/
├── pom.xml
└── src/
    ├── main/java/example/BindingDemoApplication.java
    └── test/java/example/OrderControllerTest.java
```

### 7.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>web-data-binder-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. BindingDemoApplication.java

Toàn bộ các class sau cùng nằm trong file `src/main/java/example/BindingDemoApplication.java`; chỉ `BindingDemoApplication` là public top-level class, phù hợp quy tắc biên dịch Java.

```java
package example;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}

// Kiểu giá trị thuộc miền nghiệp vụ.
record ProductCode(String value) {}

// Converter dùng chung trong cấu hình MVC.
final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "ProductCode phải có dạng SKU-000");
        }
        return new ProductCode(normalized);
    }
}

@Configuration
class WebBindingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}

// Input DTO cho form; không dùng một entity persistence trực tiếp.
class OrderForm {
    private String customer;
    private Integer quantity;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate deliveryDate;

    private ProductCode code;

    // Thuộc tính mô phỏng field client không được phép chỉnh.
    private boolean admin;

    public OrderForm() {}

    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public LocalDate getDeliveryDate() { return deliveryDate; }
    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public ProductCode getCode() { return code; }
    public void setCode(ProductCode code) { this.code = code; }

    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean admin) { this.admin = admin; }
}

@RestController
@RequestMapping("/orders")
class OrderController {

    // Chỉ áp dụng cho @ModelAttribute("orderForm").
    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "customer", "quantity", "deliveryDate", "code");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> submit(
            @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        // Đầu vào bị chặn bởi allowedFields là sự kiện cần xử lý.
        if (result.getSuppressedFields().length > 0) {
            String names = Arrays.stream(result.getSuppressedFields())
                    .sorted()
                    .collect(Collectors.joining(","));
            return ResponseEntity.badRequest().body("blocked:" + names);
        }

        if (result.hasErrors()) {
            String fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .collect(Collectors.joining(","));
            return ResponseEntity.badRequest().body("invalid:" + fields);
        }

        return ResponseEntity.ok(
                "order:" + form.getCustomer()
                + "|" + form.getQuantity()
                + "|" + form.getDeliveryDate()
                + "|" + form.getCode().value());
    }

    // Chứng minh Converter cũng dùng cho một tham số đơn.
    @GetMapping("/by-code")
    String byCode(@RequestParam ProductCode code) {
        return "found:" + code.value();
    }
}
```

Vì demo chủ động tập trung vào **chuyển kiểu**, nó không khai báo `@NotBlank`/`@NotNull` hay `@Min`. Vì vậy hãy cung cấp đủ bốn giá trị khi gọi endpoint thành công; ứng dụng thực cần validation cho trường bắt buộc trước khi dereference `deliveryDate` hoặc `code`.

### 7.3. Chạy và quan sát kết quả

Tại thư mục `web-data-binder-demo`:

```bash
mvn test
mvn spring-boot:run
```

Ở terminal khác, gọi lần lượt:

```bash
curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Ada" \
  --data-urlencode "quantity=3" \
  --data-urlencode "deliveryDate=2026-12-24" \
  --data-urlencode "code=sku-007"

curl -s "http://localhost:8080/orders/by-code?code=sku-007"

curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "customer=Ada&quantity=abc&deliveryDate=2026-12-24&code=sku-007"

curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "customer=Ada&quantity=3&deliveryDate=2026-12-24&code=sku-007&admin=true"
```

Kết quả **body** kỳ vọng, theo đúng thứ tự bốn lệnh (mỗi lệnh không tự thêm newline):

```text
order:Ada|3|2026-12-24|SKU-007
found:SKU-007
invalid:quantity
blocked:admin
```

Giải thích chính xác theo từng case:

- Form hợp lệ: `quantity` từ `"3"` thành `Integer`; ngày ISO thành `LocalDate`; mã `"sku-007"` thành `ProductCode("SKU-007")`. `OrderForm` chứa object đã được chuyển kiểu.
- Query `code=sku-007` tại `@RequestParam ProductCode` dùng converter đăng ký toàn cục.
- `quantity=abc` không đổi được thành `Integer`: `BindingResult` chứa `FieldError` của `quantity` và controller trả HTTP 400 `invalid:quantity`.
- Client gửi `admin=true` nhưng `@InitBinder` chỉ cho phép bốn property khác; field `admin` bị suppress và controller trả HTTP 400 `blocked:admin`. Đó không phải lỗi type conversion.

Với `curl -i`, HTTP status tương ứng là 200, 200, 400, 400. Với Windows PowerShell, nếu `curl` trỏ tới alias của `Invoke-WebRequest`, hãy dùng `curl.exe` hoặc công cụ HTTP tương đương.

### 7.4. Test MockMvc xác minh từng bước binding

File `src/test/java/example/OrderControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsFormFieldsWithDateAndCustomProductCode() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "3")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "order:Ada|3|2026-12-24|SKU-007"));
    }

    @Test
    void usesGlobalConverterForRequestParam() throws Exception {
        mvc.perform(get("/orders/by-code")
                    .param("code", "sku-007"))
            .andExpect(status().isOk())
            .andExpect(content().string("found:SKU-007"));
    }

    @Test
    void reportsTypeMismatchOnQuantity() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "abc")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:quantity"));
    }

    @Test
    void blocksUnexpectedAdminProperty() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "3")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007")
                    .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("blocked:admin"));
    }
}
```

Chạy `mvn test`. Bốn test kiểm tra kết quả end-to-end qua MVC: bind thành công, dùng converter ngoài form, lỗi chuyển kiểu và phát hiện field bị cấm. Demo không cần chạy Servlet server khi test; `MockMvc` xử lý request giả lập trong test context Spring Boot.

## 8. Lỗi phổ biến khi áp dụng vào dự án thật

| Hiện tượng | Nguyên nhân có thể | Cách sửa phù hợp |
| --- | --- | --- |
| `quantity=abc` gây lỗi | String không parse được thành số | Trả lỗi thân thiện từ `BindingResult`; hiển thị field và nguyên nhân cho người dùng |
| Ngày `24/12/2026` không parse theo ISO | Định dạng mong đợi là `yyyy-MM-dd` | Thống nhất định dạng hoặc dùng `@DateTimeFormat`/`Formatter` thích hợp |
| Field object vẫn `null` | Sai tên field, thiếu setter/constructor, conversion lỗi, field bị chặn | Kiểm tra input, tên property, `BindingResult` và `getSuppressedFields` |
| Converter tự viết không được gọi | Chưa đăng ký vào MVC `ConversionService`, sai source/target types | Đăng ký qua `WebMvcConfigurer#addFormatters`; test `@RequestParam` và form |
| `@InitBinder("orderForm")` không áp dụng | `@ModelAttribute` tên khác | Dùng cùng tên attribute chính xác |
| Hai `BindingResult` lẫn nhau | Đặt sai thứ tự method arguments | Đặt ngay sau tham số model attribute nó mô tả |
| Form trả 415 | `Content-Type` không đúng với `consumes` | Gửi form-urlencoded nếu endpoint khai báo form-urlencoded; JSON dùng endpoint phù hợp |
| JSON binding không theo custom formatter | `@RequestBody` đi qua `HttpMessageConverter`/Jackson | Cấu hình Jackson cho JSON hoặc chuyển đổi ở lớp riêng |
| Client có thể gửi `role=ADMIN` | Bind trực tiếp entity nhiều property ghi được | DTO giới hạn field, allowedFields hoặc constructor binding; phân quyền tại service |
| Converter cất request data trong field | Converter thường dùng chung, có thể có concurrency | Viết converter bất biến, không giữ trạng thái request |

Để debug, có thể đặt breakpoint ở `@InitBinder`, converter `convert()`, controller và kiểm tra `BindingResult`. Với dữ liệu lồng nhau, thử input như `address.city`/`items[0].sku` và kiểm tra cấu trúc DTO. Chỉ bật log chi tiết cần thiết trong môi trường phát triển; tránh in thông tin nhạy cảm từ request trong production.

### Quy trình xử lý lỗi thực tế

1. **Định nghĩa input contract:** field nào được phép nhận, kiểu dữ liệu, định dạng, trường bắt buộc, quy tắc nghiệp vụ.
2. **Chuyển kiểu:** dựa trên converter/formatter nhất quán, xử lý giá trị sai bằng lỗi thay vì default âm thầm.
3. **Chặn field không được phép:** DTO + `allowedFields` hoặc constructor binding; đọc suppressed fields khi cần.
4. **Validate:** dùng Jakarta Bean Validation/validator cho quy tắc ngoài type conversion.
5. **Xử lý lỗi:** phản hồi HTTP 400 rõ field nào sai, nhưng tránh tiết lộ thông tin nội bộ hoặc giá trị nhạy cảm.
6. **Gọi service:** chỉ sau khi DTO hợp lệ; service chịu trách nhiệm nghiệp vụ, phân quyền và thay đổi entity.

## 9. Câu hỏi tự kiểm tra

1. Khi gửi `quantity=7`, nhiệm vụ chuyển `"7"` thành `Integer` thuộc binding hay validation? **Đáp án:** type conversion bên trong quá trình binding; validation kiểm tra tính hợp lệ sau đó.
2. Khi gửi `quantity=abc` tới `Integer`, lỗi sẽ ở đâu nếu controller có `BindingResult`? **Đáp án:** lỗi field của `quantity`, thường mã `typeMismatch`.
3. `@RequestBody ProductInput` đọc JSON bằng thành phần nào? **Đáp án:** `HttpMessageConverter` (thường Jackson cho JSON); không nhầm với property binding từ form.
4. `@InitBinder("orderForm")` có tự áp dụng cho mọi DTO không? **Không.** Nó nhắm attribute `orderForm` trong phạm vi controller hoặc advice thích hợp.
5. Bạn nên đặt converter `String → ProductCode` cần dùng ở nhiều controller ở đâu? **Đáp án:** cấu hình MVC chung, ví dụ `WebMvcConfigurer#addFormatters`.
6. `@Valid` có cần để `String` biến thành `LocalDate` không? **Không.** Format/conversion và validation là hai bước khác nhau.
7. Vì sao `setAllowedFields` hữu ích dù một DTO có field `admin`? **Vì nó hạn chế property binding theo whitelist**; client không được tự gán field ngoài danh sách.
8. Khi dùng `@ModelAttribute("orderForm")` và `BindingResult`, phải đặt chúng thế nào? **Liền nhau** trong chữ ký controller method.

## 10. Tài liệu chính thức

- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): tác dụng `WebDataBinder`, phạm vi `@InitBinder`, `allowedFields` và `declarativeBinding`.
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): quá trình tạo/bind model attribute, constructor/property binding, `BindingResult`.
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): đăng ký formatter/converter qua `WebMvcConfigurer`.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConverterFactory`, `ConversionService`, `TypeDescriptor`.
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, parsing/printing theo locale.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): phân biệt chuyển đổi HTTP body với WebDataBinder.
