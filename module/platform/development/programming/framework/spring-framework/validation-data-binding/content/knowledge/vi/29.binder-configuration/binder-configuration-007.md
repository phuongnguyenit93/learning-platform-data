# Thêm formatter theo trường bằng addCustomFormatter trong Spring DataBinder

## 1. Tình huống: hai trường cùng kiểu nhưng dùng hai định dạng khác nhau

Trong một biểu mẫu Spring MVC, có thể có hai thuộc tính cùng kiểu `LocalDate` nhưng quy ước nhập khác nhau:

- `deliveryDate`: người dùng nhập ngày theo định dạng Việt Nam `dd/MM/uuuu`, ví dụ `31/12/2026`.
- `invoiceDate`: hệ thống xuất hóa đơn dùng định dạng ISO `uuuu-MM-dd`, ví dụ `2027-01-02`.

Nếu áp dụng **một formatter toàn cục cho mọi `LocalDate`**, một trường có thể bị parse sai hoặc format sai. Cách giải quyết là cấu hình formatter **cho đúng property name** bằng overload:

~~~java
binder.addCustomFormatter(
        new LocalDatePatternFormatter("dd/MM/uuuu"),
        "deliveryDate");

binder.addCustomFormatter(
        new LocalDatePatternFormatter("uuuu-MM-dd"),
        "invoiceDate");
~~~

Đây là snippet dùng lớp formatter tự viết (toàn bộ source chạy được ở phần 7). Hai thuộc tính đều là `LocalDate` nhưng sử dụng **hai formatter riêng** trong cùng một `WebDataBinder`. Đó là mục tiêu của `addCustomFormatter(Formatter<?> formatter, String... fields)`: **định dạng theo trường**, không chỉ theo kiểu.

Các kiến thức cần nắm:

1. `Formatter<T>` cung cấp `parse(String, Locale)` và `print(T, Locale)`.
2. `DataBinder#addCustomFormatter(...)` đăng ký formatter cho binder; `WebDataBinder` kế thừa API này.
3. Tham số `fields` là **property paths của target**, không phải tên HTTP header, tên attribute của model hay tên field trong JSON.
4. `@InitBinder` là điểm tích hợp phổ biến để cài formatter cho form/model attribute của controller.
5. `BindingResult` lưu lỗi chuyển đổi khi người dùng gửi chuỗi không phù hợp.
6. Formatter chỉ đảm nhiệm **chuyển đổi/hiển thị**, không thay thế Bean Validation, xác thực quyền hay bộ lọc field được phép bind.

## 2. Ba overload `addCustomFormatter` và phạm vi hiệu lực

Spring Framework có các overload tại `org.springframework.validation.DataBinder`:

~~~java
void addCustomFormatter(Formatter<?> formatter);

void addCustomFormatter(Formatter<?> formatter,
                        String... fields);

void addCustomFormatter(Formatter<?> formatter,
                        Class<?>... fieldTypes);
~~~

| Lời gọi | Phạm vi | Dùng khi nào? |
| --- | --- | --- |
| `addCustomFormatter(formatter)` | Áp dụng cho các field khớp kiểu generic mà `Formatter<T>` khai báo. | Mọi thuộc tính `LocalDate` của **binder này** dùng cùng quy ước. |
| **`addCustomFormatter(formatter, "deliveryDate")`** | Chỉ các property paths được nêu trong `fields` và đúng kiểu formatter hỗ trợ. | **Một vài field có định dạng đặc biệt**. |
| `addCustomFormatter(formatter, "startDate", "endDate")` | Nhiều field được nêu rõ dùng một formatter. | Nhiều trường cùng một pattern, nhưng không muốn áp dụng cho trường khác. |
| `addCustomFormatter(formatter, LocalDate.class)` | Phạm vi theo **field type** được truyền, không phải một field name. | Áp dụng theo kiểu, kể cả khi generic formatter không cung cấp đủ thông tin kiểu. |

**Lưu ý overload:** tham số `String... fields` khác `Class<?>... fieldTypes`. Hai lời gọi sau có ý nghĩa rất khác:

~~~java
// Chỉ áp dụng cho property "deliveryDate":
binder.addCustomFormatter(formatter, "deliveryDate");

// Áp dụng theo kiểu LocalDate:
binder.addCustomFormatter(formatter, LocalDate.class);
~~~

Nếu **bỏ danh sách field** khi sử dụng overload varargs, javadoc mô tả fallback sang áp dụng cho các field khớp kiểu. Để tránh nhầm overload và đảm bảo field-specific, hãy **luôn truyền tường minh tên trường cần cấu hình**. Không coi `@InitBinder("orderForm")` và `addCustomFormatter(..., "deliveryDate")` là cùng một phạm vi:

- `@InitBinder("orderForm")` giới hạn **model attribute/binder được cấu hình**.
- `"deliveryDate"` giới hạn **property nằm bên trong target của binder đó**.

### Cơ chế adapter nội bộ

Javadoc của `DataBinder#addCustomFormatter` cho biết Spring đăng ký một **`PropertyEditor` adapter** cho formatter ở phía dưới. Vì vậy, đây là **tùy chỉnh theo một binder**, không phải lời gọi tự động thêm formatter vào mọi `ConversionService` của ứng dụng.

Nói cách khác:

~~~text
HTTP parameter "deliveryDate" = "31/12/2026"
                |
                v
@ModelAttribute("orderForm")
                |
                v
WebDataBinder
  ├─ property path: deliveryDate
  ├─ target type: java.time.LocalDate
  ├─ field-specific FormatterPropertyEditorAdapter
  ├─ Formatter.parse("31/12/2026", locale)
  └─ setter / property write:
          orderForm.setDeliveryDate(LocalDate.of(2026,12,31))
                |
                v
BindingResult (thành công hoặc lỗi chuyển kiểu)
                |
                v
@Valid / @Validated nếu được yêu cầu
                |
                v
Controller
~~~

Không nên mặc định suy ra mọi converter được đăng ký qua Spring `ConversionService` đều được ưu tiên theo cách giống custom editor. Khi có nhiều cấu hình có thể cạnh tranh (editor theo field, formatter theo type, `@DateTimeFormat`), nên **chủ động chọn một nguồn định dạng cho mỗi field và kiểm thử** với version Spring đang sử dụng.

## 3. Cách viết một `Formatter<LocalDate>` đúng hợp đồng

`org.springframework.format.Formatter<T>` kết hợp hai nhiệm vụ:

- **`parse(String text, Locale locale)`**: đổi chuỗi người dùng nhập thành `T`.
- **`print(T object, Locale locale)`**: đổi `T` thành chuỗi để hiển thị hoặc render form.

Với ngày tháng, Java có `java.time.format.DateTimeFormatter`, **immutable** và thread-safe khi dùng đúng cách. Tác giả formatter nên tránh `SimpleDateFormat` dùng chung không đồng bộ hoặc state tích lũy theo request.

Ví dụ bộ chuyển đổi pattern:

~~~java
public final class LocalDatePatternFormatter
        implements Formatter<LocalDate> {

    private final DateTimeFormatter delegate;

    public LocalDatePatternFormatter(String pattern) {
        this.delegate = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, delegate);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return delegate.format(object);
    }
}
~~~

Đây là snippet cần imports `Formatter`, `LocalDate`, `DateTimeFormatter`, `ResolverStyle` và `Locale`; file đầy đủ ở phần 7.

### Vì sao `uuuu` thay vì `yyyy` với strict parsing?

Trong `DateTimeFormatter`, `u` là proleptic year, còn `y` là year-of-era. Với `ResolverStyle.STRICT`, dùng `yyyy` mà không có era có thể gây khó phân giải `LocalDate`. Ví dụ an toàn là:

- `dd/MM/uuuu` cho `31/12/2026`.
- `uuuu-MM-dd` cho `2027-01-02`.

`ResolverStyle.STRICT` giúp từ chối `31/02/2026`, `29/02/2025` và những ngày bất hợp lệ về lịch, thay vì tự điều chỉnh chúng thành ngày khác.

Trong ví dụ, các pattern **chỉ có chữ số và dấu phân cách cố định**, nên formatter chủ động **không thay đổi theo `Locale`**. Nếu cần tên tháng bằng chữ, cách viết số theo locale, dấu phân cách địa phương hoặc timezone, hãy thiết kế formatter **có xét `locale`** và test cho từng locale. Đừng nhận tham số `Locale` rồi bỏ qua một cách vô thức.

### Parse/print đối xứng

Cùng một `Formatter<T>` nên thỏa:

~~~text
value = LocalDate.of(2026, 12, 31)
formatted = formatter.print(value, locale)  -> "31/12/2026"
parsed = formatter.parse(formatted, locale) -> 2026-12-31
~~~

Điều này hữu ích khi HTML form **hiển thị lại** giá trị đã có (print) và **nhận** form submit (parse). Nếu parse và print không tương thích, form có thể hiển thị một dạng ngày nhưng không đọc lại đúng dạng đó sau khi người dùng lưu.

Với `String` rỗng, whitespace, `null`, giá trị không hợp lệ hoặc input lạ, nên xác định chính sách:

- Để `@NotNull` kiểm tra field bắt buộc sau khi bind nếu giá trị thiếu.
- Với chuỗi không parse được, báo lỗi chuyển kiểu qua `BindingResult`; không tự gán ngày mặc định im lặng.
- Nếu cần trim khoảng trắng, làm rõ đó là một phần của input contract, rồi test; ví dụ đầy đủ giữ quy tắc **khớp pattern đã chọn**.
- Không trả `LocalDate.now()` khi parse lỗi: điều đó che lỗi và làm dữ liệu nghiệp vụ sai.

## 4. Dùng `@InitBinder` để đặt formatter theo đúng model attribute

Trong Spring MVC, một controller có thể có:

~~~java
@InitBinder("orderForm")
void configureDates(WebDataBinder binder) {
    binder.setAllowedFields(
            "deliveryDate", "invoiceDate", "note");

    binder.addCustomFormatter(
            new LocalDatePatternFormatter("dd/MM/uuuu"),
            "deliveryDate");

    binder.addCustomFormatter(
            new LocalDatePatternFormatter("uuuu-MM-dd"),
            "invoiceDate");
}

@PostMapping("/orders/form")
ResponseEntity<String> save(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body("FORM_INVALID");
    }
    return ResponseEntity.ok("OK");
}
~~~

Đây là snippet thuộc controller có imports và các type `OrderForm`, `LocalDatePatternFormatter`; phần 7 có source đầy đủ.

**Luồng xử lý:**

1. Spring MVC nhận form/query parameters cho model attribute tên `orderForm`.
2. Tạo/lấy `OrderForm`, chuẩn bị `WebDataBinder` và gọi `@InitBinder("orderForm")` để cấu hình.
3. Binder đọc `deliveryDate`, `invoiceDate` và chuyển String vào `LocalDate` qua formatter **ứng với từng field**.
4. Binder gán giá trị vào JavaBean properties, tạo `BindingResult` nếu conversion fail.
5. Nếu có `@Valid` và Bean Validation provider, Spring kiểm tra các constraint trên `OrderForm`.
6. Vì `BindingResult` nằm **ngay sau** form, controller nhận lỗi và quyết định response.

**Ranh giới bảo mật:** `setAllowedFields(...)` quy định các property có thể được ghi bằng property binding; `addCustomFormatter(...)` **không có chức năng whitelist**. Dù formatter chỉ được gắn cho `deliveryDate`, attacker vẫn có thể gửi `isAdmin=true` vào field khác nếu model có setter và không có giới hạn binding.

### Phạm vi và vòng đời của `@InitBinder`

`@InitBinder` trong controller thường chỉ có tác dụng với binder của controller đó. `@ControllerAdvice` có thể cung cấp cấu hình chung cho nhiều controller. `@InitBinder("orderForm")` chỉ áp dụng cho model attribute phù hợp tên, nên nếu trong handler dùng `@ModelAttribute("order")` thì cấu hình dự kiến cho `orderForm` **sẽ không được áp dụng**.

Đối với request DTO khác cũng có field `deliveryDate` nhưng không dùng binder tương ứng, nó không tự nhận formatter này. Vì thế đặt cấu hình theo **đúng object name** và **đúng property path** là hai kiểm tra quan trọng.

**WebFlux:** `@InitBinder` và `WebDataBinder` cũng được dùng cho model attribute trong Spring WebFlux. Tuy nhiên request parsing/argument resolution của WebFlux không trùng Servlet MVC. Nếu một ứng dụng dùng WebFlux, hãy viết `WebTestClient` để kiểm tra cụ thể; đừng giả định `@RequestParam` trong WebFlux đọc form-urlencoded giống Servlet MVC.

## 5. Phân biệt `addCustomFormatter` với các phương pháp khác

| Cách cấu hình | Áp dụng điển hình | Khi nên chọn |
| --- | --- | --- |
| `binder.addCustomFormatter(formatter, "deliveryDate")` | Cục bộ cho **một field** trên binder hiện tại. | Một thuộc tính có quy ước khác các field cùng kiểu. |
| `binder.addCustomFormatter(formatter)` | Cục bộ cho các field của một kiểu trên binder hiện tại. | Các field cùng kiểu của form này chia sẻ quy tắc. |
| `binder.addCustomFormatter(formatter, LocalDate.class)` | Cục bộ theo field type khai báo. | Khai báo type rõ thay vì dựa vào generic formatter. |
| `@DateTimeFormat(pattern = "dd/MM/uuuu")` | Gắn trên field/parameter. | Format có thể diễn tả bằng annotation chuẩn, không cần custom code. |
| `WebMvcConfigurer#addFormatters(FormatterRegistry)` | Dùng converter/formatter có phạm vi application MVC. | Quy tắc dùng chung nhiều controllers. |
| `FormattingConversionService` | Conversion/formatting cấp service/ứng dụng. | Thiết lập chính sách dùng chung, annotation formatters. |
| `binder.registerCustomEditor(type, path, editor)` | PropertyEditor theo type/path, API cũ hơn. | Tích hợp legacy editor; cân nhắc Formatter trước. |
| Jackson `@JsonFormat` hoặc `ObjectMapper` | JSON body qua `@RequestBody`. | API JSON, không phải HTTP form/query binding. |

Trong ví dụ chỉ cần pattern cho một field, giải pháp đơn giản hơn có thể là:

~~~java
public class OrderForm {
    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate deliveryDate;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate invoiceDate;
}
~~~

Đây là snippet về ý tưởng, chưa bao gồm getters/setters hoặc import. Khi định dạng tĩnh, `@DateTimeFormat` thường gọn và dễ bảo trì. **`addCustomFormatter` hữu ích khi phải chọn implementation hoặc phạm vi định dạng ngay tại binder** (ví dụ form đặc biệt, policy của một controller hoặc cách định dạng dùng chung có logic custom). Không nên thêm custom formatter chỉ để thay một annotation đã đáp ứng yêu cầu.

### Tại sao addCustomFormatter không tự thay đổi JSON?

Giả sử client gửi:

~~~http
POST /orders/json
Content-Type: application/json

{"deliveryDate":"31/12/2026","invoiceDate":"2027-01-02"}
~~~

`@RequestBody` thường dùng `HttpMessageConverter`/Jackson để đọc JSON. Jackson **không gọi custom `Formatter` của `WebDataBinder` để parse từng JSON property**. Nếu Java property `LocalDate` chưa có Jackson custom deserializer/`@JsonFormat`, JSON ISO thường được hỗ trợ bởi module Java Time, còn `31/12/2026` có thể dẫn đến lỗi deserialize.

Ngược lại, cùng cặp chuỗi ở body `application/x-www-form-urlencoded` được `@ModelAttribute` bind qua `WebDataBinder` như cấu hình trong bài. Đừng dùng `setAllowedFields`/`addCustomFormatter` như một giải pháp chung cho Jackson JSON.

## 6. Lỗi chuyển kiểu: `BindingResult`, `FieldError` và validation

Một formatter không thể parse `deliveryDate=31/02/2026`. Khi binding form, Spring thường chuyển lỗi thành `FieldError` với mã liên quan `typeMismatch`.

~~~java
BindingResult result = binder.getBindingResult();

if (result.hasFieldErrors("deliveryDate")) {
    FieldError error = result.getFieldError("deliveryDate");

    System.out.println(error.getField());
    System.out.println(error.getCode());
}
~~~

Đây là snippet minh họa trong ngữ cảnh có biến `binder`. Trong code thực tế, khi `FieldError` tồn tại, `getCode()` thường là `"typeMismatch"`, còn `getCodes()` có thể chứa nhiều mã để message resolution theo object/field/type. Không dùng exact exception message của Java DateTimeFormatter hoặc Hibernate Validator làm API contract vì nó có thể thay đổi.

### Binding và validation là hai bước

- **Binding/conversion:** `"31/12/2026"` thành `LocalDate.of(2026,12,31)`; nếu không parse được thì có lỗi binding.
- **Bean Validation:** `@NotNull` kiểm tra field không null sau khi bind. `@Future` hoặc class-level constraint có thể kiểm tra quy tắc ngày, nhưng chúng là **kiểm tra giá trị**, không thay thế parse.
- **Business validation:** `deliveryDate` phải không sau `invoiceDate`, hoặc hợp đồng phải được phép xuất hóa đơn trước ngày giao, phụ thuộc yêu cầu; kiểm tra bằng service/custom validator phù hợp.

Không ném `ValidationException` hay `IllegalStateException` cho dữ liệu đầu vào chỉ sai định dạng trong formatter. Khi parse không được, ném `IllegalArgumentException` hoặc exception của parser được Spring hỗ trợ, để binder có cơ hội tạo field error. Không trả một ngày bất kỳ để làm cho form trông hợp lệ.

### Khác biệt giữa lỗi form và lỗi JSON

| Đầu vào | Pipeline | Lỗi thường gặp |
| --- | --- | --- |
| `application/x-www-form-urlencoded` + `@ModelAttribute` | `WebDataBinder` và Formatter | `FieldError` mã `typeMismatch`; nếu không có `BindingResult` cục bộ, MVC có thể ném `MethodArgumentNotValidException`. |
| `application/json` + `@RequestBody` | `HttpMessageConverter`/Jackson | `HttpMessageNotReadableException` khi không deserialize được JSON, thường HTTP 400. |
| Form parse được nhưng `@NotNull`/`@Future` không đạt | Bean Validation | Field/object validation errors trong `BindingResult`. |
| URL query và `@ModelAttribute` | Property binding theo property names | Formatter đã đăng ký trong binder có thể được dùng tương tự form fields. |
| `@RequestParam LocalDate date` riêng lẻ | Argument conversion | Không nên mặc định áp dụng formatter đã đăng ký **chỉ với field property `deliveryDate` trên một model attribute**; dùng formatter/`@DateTimeFormat` phù hợp với method argument. |

**Tránh nhầm mục tiêu:** `addCustomFormatter(...,"deliveryDate")` áp dụng vào **property path** của binder; không phải mọi argument có tên `deliveryDate` ở bất kỳ controller.

## 7. Ví dụ chạy được: Spring Boot 3.x + Java 17+ + MockMvc

Tạo project Maven với Spring Boot **3.x**, Java 17+ và Jakarta Validation. Các dependencies trong `pom.xml` (BOM/parent của Spring Boot quản lý version):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tạo các file dưới `src/main/java/com/example/fieldformatter/` và `src/test/java/com/example/fieldformatter/`. Tất cả các class public có tên trùng file. Không cần database.

### 7.1. File `FieldFormatterApplication.java`

~~~java
package com.example.fieldformatter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FieldFormatterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FieldFormatterApplication.class, args);
    }
}
~~~

### 7.2. File `StrictLocalDateFormatter.java`

~~~java
package com.example.fieldformatter;

import org.springframework.format.Formatter;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public final class StrictLocalDateFormatter
        implements Formatter<LocalDate> {

    private final DateTimeFormatter delegate;

    public StrictLocalDateFormatter(String pattern) {
        this.delegate = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, delegate);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return delegate.format(object);
    }
}
~~~

`DateTimeFormatter` bất biến và thread-safe; formatter này chỉ giữ một trường `final`. Vì pattern chỉ có số, implementation không phụ thuộc locale. Nếu thêm tên tháng bằng chữ, sử dụng `locale` khi xây `DateTimeFormatter` hoặc chọn parser/formatter phù hợp theo request locale.

### 7.3. File `OrderForm.java`

~~~java
package com.example.fieldformatter;

import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;

public class OrderForm {

    @NotNull
    private LocalDate deliveryDate;

    @NotNull
    private LocalDate invoiceDate;

    private String note;

    public OrderForm() {
    }

    public LocalDate getDeliveryDate() {
        return deliveryDate;
    }

    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public LocalDate getInvoiceDate() {
        return invoiceDate;
    }

    public void setInvoiceDate(LocalDate invoiceDate) {
        this.invoiceDate = invoiceDate;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Hai field cùng `LocalDate`, nhưng `@NotNull` chỉ kiểm tra null; nó không quyết định cú pháp của text input. Việc parse do formatter trong binder thực hiện.

### 7.4. File `OrdersController.java`

~~~java
package com.example.fieldformatter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "deliveryDate", "invoiceDate", "note");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("dd/MM/uuuu"),
                "deliveryDate");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("uuuu-MM-dd"),
                "invoiceDate");
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + form.getDeliveryDate()
                + "|" + form.getInvoiceDate());
    }

    @GetMapping("/preview")
    public ResponseEntity<String> preview(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body("PREVIEW_INVALID");
        }

        return ResponseEntity.ok(
                "PREVIEW:" + form.getDeliveryDate()
                + "|" + form.getInvoiceDate());
    }

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> json(
            @Valid @RequestBody OrderJson input) {

        return ResponseEntity.ok(
                "JSON:" + input.deliveryDate()
                + "|" + input.invoiceDate());
    }

    public record OrderJson(
            @NotNull LocalDate deliveryDate,
            @NotNull LocalDate invoiceDate) {
    }
}
~~~

**Điều gì diễn ra ở từng endpoint?**

- `POST /orders/form`: Spring MVC bind form values vào `OrderForm`; `@InitBinder("orderForm")` thêm **hai formatter field-specific**; `@Valid` kiểm tra `@NotNull`; controller bắt lỗi bằng `BindingResult`. Body thành công dùng `LocalDate#toString()`, luôn in ISO `uuuu-MM-dd`, không phải chuỗi gốc người dùng nhập.
- `GET /orders/preview`: query parameters được bind vào cùng model attribute `orderForm` nên cũng được formatter áp dụng.
- `POST /orders/json`: Jackson đọc JSON vào record `OrderJson`, **không** sử dụng hai field-specific formatters của `WebDataBinder`. Với default Boot JSON Java Time support, ngày ISO đọc được; ngày `31/12/2026` thường bị từ chối nếu không cấu hình Jackson.
- `setAllowedFields(...)` chặn các property ngoài hợp đồng form. Trong thực tế, dùng request DTO riêng cho phép kiểm soát model an toàn; `@Valid` không phải authorization.

### 7.5. File `StrictLocalDateFormatterTest.java` — unit test formatter và DataBinder

Tạo tại `src/test/java/com/example/fieldformatter/StrictLocalDateFormatterTest.java`:

~~~java
package com.example.fieldformatter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.time.LocalDate;
import java.util.Locale;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class StrictLocalDateFormatterTest {

    private DataBinder newBinder(OrderForm target) {
        DataBinder binder = new DataBinder(target, "orderForm");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("dd/MM/uuuu"),
                "deliveryDate");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("uuuu-MM-dd"),
                "invoiceDate");

        return binder;
    }

    @Test
    void formatAndParseRoundTrip() {
        var formatter =
                new StrictLocalDateFormatter("dd/MM/uuuu");

        var date = LocalDate.of(2026, 12, 31);
        assertEquals("31/12/2026",
                formatter.print(date, Locale.ROOT));
        assertEquals(date,
                formatter.parse("31/12/2026", Locale.ROOT));
    }

    @Test
    void bindsTwoLocalDatesWithDifferentPatterns() {
        var target = new OrderForm();
        var binder = newBinder(target);

        binder.bind(new MutablePropertyValues(Map.of(
                "deliveryDate", "31/12/2026",
                "invoiceDate", "2027-01-02"
        )));

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals(LocalDate.of(2026, 12, 31),
                target.getDeliveryDate());
        assertEquals(LocalDate.of(2027, 1, 2),
                target.getInvoiceDate());
    }

    @Test
    void invalidDateIsFieldBindingError() {
        var target = new OrderForm();
        var binder = newBinder(target);

        binder.bind(new MutablePropertyValues(Map.of(
                "deliveryDate", "31/02/2026",
                "invoiceDate", "2027-01-02"
        )));

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("deliveryDate"));
        assertEquals("typeMismatch",
                binder.getBindingResult()
                        .getFieldError("deliveryDate").getCode());
        assertEquals(LocalDate.of(2027, 1, 2),
                target.getInvoiceDate());
    }

    @Test
    void datePatternIsSpecificToEachField() {
        var target = new OrderForm();
        var binder = newBinder(target);

        // Chuỗi dùng pattern của deliveryDate
        // nhưng lại gửi vào invoiceDate.
        binder.bind(new MutablePropertyValues(Map.of(
                "invoiceDate", "31/12/2026"
        )));

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("invoiceDate"));
        assertNull(target.getInvoiceDate());
    }

    @Test
    void strictParserRejectsInvalidLeapDay() {
        var formatter =
                new StrictLocalDateFormatter("dd/MM/uuuu");

        assertThrows(RuntimeException.class, () ->
                formatter.parse("29/02/2025", Locale.ROOT));
    }
}
~~~

Các test dùng `DataBinder` trực tiếp, không mở web server. Chúng khẳng định hai trường `LocalDate` có formatter riêng, ngày sai được ghi vào `BindingResult`, và `parse/print` đối xứng. `assertThrows(RuntimeException.class)` giữ test không phụ thuộc subclass của parser; trong implementation này, `LocalDate.parse` thường ném `DateTimeParseException` khi ngày sai.

`DataBinder.bind(...)` **không tự chạy Bean Validation**; vì unit test chỉ kiểm tra conversion, `@NotNull` chưa phải nguyên nhân của errors trong các test đó. Nếu cần test validator, đăng ký `Validator` cho binder rồi gọi `validate()`, hoặc kiểm thử MVC endpoint có `@Valid` như phần tiếp theo.

### 7.6. File `OrdersControllerTest.java` — 9 bài kiểm thử MockMvc

Tạo tại `src/test/java/com/example/fieldformatter/OrdersControllerTest.java`:

~~~java
package com.example.fieldformatter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsFormFieldsUsingTheirOwnPatterns() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "FORM:2026-12-31|2027-01-02"));
    }

    @Test
    void canBindQueryToTheSameModelAttribute() throws Exception {
        mvc.perform(get("/orders/preview")
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "PREVIEW:2026-12-31|2027-01-02"));
    }

    @Test
    void rejectsWrongPatternForDeliveryDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "2026-12-31")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsWrongPatternForInvoiceDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "02/01/2027"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsImpossibleDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/02/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsMissingRequiredField() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void jsonIsoDatesDoNotNeedFieldFormatter() throws Exception {
        mvc.perform(post("/orders/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "deliveryDate":"2026-12-31",
                              "invoiceDate":"2027-01-02"
                            }
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "JSON:2026-12-31|2027-01-02"));
    }

    @Test
    void jsonSlashDateIsNotChangedByFormFormatter()
            throws Exception {
        mvc.perform(post("/orders/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "deliveryDate":"31/12/2026",
                              "invoiceDate":"2027-01-02"
                            }
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void endpointDeclaresItsInputMediaType() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"deliveryDate\":\"2026-12-31\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Chạy toàn bộ kiểm thử của hai file:

~~~bash
./mvnw test -Dtest=StrictLocalDateFormatterTest,OrdersControllerTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=StrictLocalDateFormatterTest,OrdersControllerTest`, hoặc gọi `mvn test` nếu project Maven đã được cấu hình phù hợp.

Với Spring Boot 3.x Web + Validation + Test như trên, **14 test được thiết kế để pass** (5 unit test và 9 MockMvc test). Các trường hợp chính:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Form `deliveryDate=31/12/2026`, `invoiceDate=2027-01-02` | HTTP 200, `FORM:2026-12-31\|2027-01-02`. |
| Query tương tự vào `/orders/preview` | HTTP 200, `PREVIEW:2026-12-31\|2027-01-02`. |
| Form gửi ISO cho `deliveryDate` | HTTP 400 và body `FORM_INVALID`. |
| Form gửi slash-date cho `invoiceDate` | HTTP 400 và body `FORM_INVALID`. |
| Ngày `31/02/2026` | HTTP 400 do parse lỗi. |
| Thiếu `invoiceDate` | HTTP 400 do `@NotNull`. |
| JSON hai ngày ISO | HTTP 200, `JSON:2026-12-31\|2027-01-02`. |
| JSON `deliveryDate` theo slash-date | HTTP 400 ở JSON decoder; không đi qua field formatter. |
| Gửi JSON đến endpoint chỉ nhận form | HTTP 415. |

**Giới hạn:** đây là test thiết kế cho dự án Boot 3.x được tạo đúng như dependencies ở trên, không có Spring Security hoặc handler lỗi tùy chỉnh. Nếu thêm CSRF, custom `@ControllerAdvice`, đổi ObjectMapper/validation configuration hoặc dùng Spring Boot version khác, HTTP status/schema cần test lại. Không hardcode message parse lỗi do Java/Spring tạo; chỉ assert status/body do controller quyết định.

### 7.7. Thử bằng curl

Sau khi chạy `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "deliveryDate=31%2F12%2F2026&invoiceDate=2027-01-02"

curl -i "http://localhost:8080/orders/preview?deliveryDate=31%2F12%2F2026&invoiceDate=2027-01-02"

curl -i -X POST "http://localhost:8080/orders/json" \
  -H "Content-Type: application/json" \
  -d '{"deliveryDate":"2026-12-31","invoiceDate":"2027-01-02"}'
~~~

Lệnh trên dành cho shell Unix. Dấu slash trong ngày được URL-encode ở form/query để minh họa rằng HTTP parameter decoding diễn ra trước formatter. Trong PowerShell có thể dùng `curl.exe`, chỉnh quoting/line continuation theo shell. Các response thành công sẽ in ngày theo `LocalDate#toString()` ở dạng ISO.

## 8. Tên trường và property path: cấu hình đúng đối tượng

`fields` trong `addCustomFormatter(formatter, String... fields)` là **property paths**. Với class lồng nhau:

~~~java
public class BookingForm {
    private DateRange dates;

    public DateRange getDates() { return dates; }
    public void setDates(DateRange dates) { this.dates = dates; }
}

public class DateRange {
    private LocalDate start;

    public LocalDate getStart() { return start; }
    public void setStart(LocalDate start) {
        this.start = start;
    }
}
~~~

Đây là hai class minh họa; đặt trong hai file khác nhau hoặc bỏ modifier public nếu đặt cùng file. Nếu input form dùng `dates.start=31/12/2026` thì formatter path tương ứng:

~~~java
binder.addCustomFormatter(
        new StrictLocalDateFormatter("dd/MM/uuuu"),
        "dates.start");
~~~

**Không viết `"start"`** nếu target binder là `BookingForm` và property thực sự nằm tại `dates.start`. Việc resolve nested property cũng yêu cầu các getter/setter và target object lồng nhau phù hợp; có thể cần cấu hình auto-grow nested path theo Spring `DataBinder` nếu property đang null.

Với collection paths như `items[0].shipDate`, cần biết cách Spring canonicalize/index property, kiểm soát kích thước collection và test thực tế. Đừng sử dụng một pattern wildcard tùy ý trong `fields` và mặc định nó sẽ match mọi phần tử: API `registerCustomEditor(Class, String, PropertyEditor)` là về property path, không phải cơ chế matching giống `setAllowedFields`. Nếu nhiều phần tử cần cùng formatter, cân nhắc dùng `Formatter` theo type/annotation hoặc cấu trúc DTO thích hợp.

### Tại sao không chỉ dựa vào tên Java parameter?

`@ModelAttribute("orderForm")` đặt tên **model object**, còn `"deliveryDate"` là tên **property**. Nếu handler có argument riêng `@RequestParam("deliveryDate") LocalDate date`, binder cho model attribute không nhất thiết được dùng để convert argument đó. Khi API là một argument đơn, dùng `@DateTimeFormat(pattern="dd/MM/uuuu")` ngay trên argument hoặc cấu hình formatter phạm vi phù hợp với argument resolution.

## 9. Locale, lỗi định dạng và thread-safety

`Formatter<T>` nhận `Locale` để hỗ trợ chuẩn hiển thị/ngôn ngữ của người dùng. Ví dụ formatter tiền tệ:

~~~java
public final class MoneyFormatter implements Formatter<BigDecimal> {
    @Override
    public BigDecimal parse(String text, Locale locale)
            throws ParseException {
        // Parse số theo locale với NumberFormat và kiểm tra độ chính xác.
        throw new UnsupportedOperationException(
                "Chỉ là skeleton minh họa");
    }

    @Override
    public String print(BigDecimal amount, Locale locale) {
        // Tùy locale: 1.234,56 hoặc 1,234.56.
        throw new UnsupportedOperationException(
                "Chỉ là skeleton minh họa");
    }
}
~~~

Đây **không phải implementation sử dụng được**, chỉ minh họa rằng formatter có hai chiều và tham số `Locale`. Để dùng tiền tệ thực tế, cần parse thận trọng với `NumberFormat`, xét scale, symbol/currency và ngăn rounding không mong muốn. Không nên copy skeleton này vào production.

Trường hợp `StrictLocalDateFormatter` của ví dụ không phụ thuộc locale vì định dạng là protocol cố định. Nếu form cần `01 Jan 2027` theo ngôn ngữ, hãy sử dụng formatter có locale tương ứng. `DateTimeFormatter.ofPattern(pattern, locale)` cho phép tạo formatter có locale khi cần; nên dùng cấu hình bất biến hoặc đối tượng tạo theo lần gọi nếu xử lý dynamic locale.

**Thread-safety:** Controller/binder có thể dùng lại các thành phần formatter trong nhiều request. Formatter nên **stateless hoặc immutable**, không giữ `Locale`, text đang parse hoặc `DateFormat` mutable chia sẻ ở field. `DateTimeFormatter` immutable là lựa chọn phù hợp; một `SimpleDateFormat` singleton không an toàn khi có nhiều threads.

### Bắt lỗi thế nào?

- Parse lỗi: để Spring tạo `BindingResult`/`FieldError`, không tự trả về giá trị hợp lệ giả.
- Field bắt buộc: `@NotNull`/Bean Validation nếu có.
- Không kết nối mạng hoặc truy vấn database trong formatter: `parse/print` là API đồng bộ; tác vụ blocking có thể khiến argument binding chậm, đặc biệt trong Spring WebFlux.
- Không đưa raw user input và stack trace vào error response nếu chứa thông tin nhạy cảm.

## 10. Các lỗi phổ biến và checklist

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Hai `LocalDate` cùng bị parse theo một pattern | Đăng ký formatter theo type thay vì theo field. | Dùng overload `addCustomFormatter(formatter, "fieldName")`. |
| Formatter không áp dụng | `@InitBinder` trỏ sai object name hoặc field path sai. | Đối chiếu `@ModelAttribute("orderForm")` và `"deliveryDate"`. |
| Gửi `31/02/2026` nhưng không báo lỗi | Parser mặc định lenient hoặc formatter tự sửa ngày. | Dùng strict date parsing, thêm test ngày không hợp lệ. |
| JSON `31/12/2026` không đọc được | Jackson không dùng `WebDataBinder` field formatter. | Dùng ISO JSON hoặc cấu hình Jackson/`@JsonFormat` riêng. |
| `@RequestParam LocalDate date` không dùng formatter của form | Formatter đăng ký theo property path của model attribute. | Dùng `@DateTimeFormat` trên argument hoặc formatter phạm vi thích hợp. |
| `getFieldError("deliveryDate")` có `typeMismatch` | Chuỗi không parse được thành `LocalDate`. | Trả form lỗi/HTTP 400, không che bằng một ngày giả. |
| Lỗi `@NotNull` không xuất hiện khi gọi `DataBinder.bind` thủ công | Binding khác validation. | Đăng ký/gọi validator hoặc dùng `@Valid` trong MVC. |
| Form có field nhạy cảm bị bind | Formatter không phải allowlist. | Dùng form DTO và `setAllowedFields(...)`. |
| Cùng một formatter bị lỗi race | Lưu mutable parser/state dùng chung. | Dùng `DateTimeFormatter` immutable; không dùng shared `SimpleDateFormat`. |
| Dùng `yyyy` với strict parser nhưng ngày không parse | Year-of-era thiếu era khi strict resolving. | Dùng `uuuu` cho ngày ISO/proleptic year. |

### Checklist trước khi triển khai

- [ ] Đã xác định đúng field cần formatter riêng, thay vì áp dụng cho cả type.
- [ ] `@InitBinder` áp dụng đúng model attribute name; `fields` là property paths chính xác.
- [ ] Formatter implement đầy đủ `parse` và `print`, hai chiều đối xứng.
- [ ] Pattern, locale và strictness có hợp đồng rõ ràng; test cả ngày hợp lệ và ngày bất hợp lệ.
- [ ] Có `BindingResult` đặt ngay sau `@ModelAttribute` nếu muốn xử lý lỗi tại controller.
- [ ] Có Bean Validation cho required/range/business rules khi cần; không coi formatter là validator.
- [ ] Dùng DTO và allowlist để ngăn mass assignment; không bind thẳng entity chứa server-only fields.
- [ ] Không giả định formatter của form được dùng cho `@RequestBody` JSON hoặc mọi `@RequestParam`.
- [ ] Test cả field khác **cùng kiểu** để chứng minh phạm vi riêng của formatter.
- [ ] Formatter thread-safe, không giữ request-specific mutable state và không thực hiện blocking I/O.
- [ ] Nếu quy tắc đủ đơn giản, cân nhắc `@DateTimeFormat` trước khi tạo custom formatter.

**Ghi nhớ:** `addCustomFormatter(formatter, "deliveryDate")` là cách điều chỉnh **conversion/formatting cho một property cụ thể của binder**. Nó cho phép cùng một model có nhiều field `LocalDate` nhưng mỗi field dùng một quy ước. Ghép đúng ba yếu tố — tên model attribute, tên property path và kiểu formatter — rồi dùng `BindingResult` và test để xác minh hành vi.

## Tài liệu tham khảo

- Spring Framework Javadoc — `DataBinder#addCustomFormatter(Formatter, String...)` và các overload: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — `@InitBinder` trong MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — Spring Field Formatting (`Formatter<T>`, `Parser`, `Printer`): https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — MVC Data Binding và bảo mật model: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — `@ModelAttribute` trong controller: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — `@InitBinder` trong WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html
