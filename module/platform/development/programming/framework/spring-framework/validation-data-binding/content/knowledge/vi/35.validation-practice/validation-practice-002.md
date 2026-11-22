# Thực nghiệm chuỗi bind, convert, validate và đọc BindingResult trong Spring Framework

## 1. Mục tiêu: nhìn thấy từng chặng của một request

Trong Spring MVC, khi một form HTTP được ánh xạ vào Java object, người mới thường mô tả quá đơn giản rằng “Spring đọc các fields rồi chạy `@Valid`”. Thực tế cần tách ba hoạt động và một nơi tập hợp kết quả:

~~~text
Form/query parameters (chuỗi ký tự HTTP)
        |
        v
1. BIND: xác định target object và property path cần gán
        |
        +---- 2. CONVERT: String -> Integer / LocalDate / custom type
        |             |
        |             +---- thất bại -> FieldError (bindingFailure=true)
        |
        v
3. VALIDATE: kiểm tra @NotBlank, @Min, @Email, @Valid nested...
        |
        +---- vi phạm -> FieldError / ObjectError (validation errors)
        |
        v
4. BindingResult: đọc lỗi binding + conversion + validation
        |
        +---- hasErrors(), getFieldErrors(), getGlobalErrors()
        +---- getSuppressedFields(), getErrorCount(), getFieldValue()
        |
        v
Controller quyết định 200/400 và chỉ công bố dữ liệu an toàn
~~~

**Điểm chính xác cần nhớ:** *convert không nhất thiết là một “bước chạy sau bind” độc lập*. Khi `DataBinder#bind` áp một giá trị cho property có kiểu khác `String`, Spring thực hiện type conversion **bên trong quá trình binding**, thông qua `ConversionService`, formatter, property editor hoặc các cơ chế liên quan. Sau đó, `DataBinder#validate` được gọi riêng trong ví dụ lập trình trực tiếp; ở MVC, Spring xử lý validation đối với `@Valid`/`@Validated` tại thời điểm thích hợp trong lifecycle của handler argument.

Mục tiêu thực hành:
1. Gửi form thật và quan sát Spring gán `String` vào DTO.
2. Xác nhận `"5"` chuyển thành `Integer(5)`, `"2026-12-20"` chuyển thành `LocalDate`.
3. So sánh input `"not-a-number"` với số hợp lệ nhưng vi phạm `@Min(1)`.
4. Chứng minh **binding errors đã có trước khi gọi `validate()`** trong một `WebDataBinder` dùng trực tiếp.
5. Xác nhận validation sau đó thêm lỗi vào **cùng `BindingResult`**.
6. Đọc nested paths như `address.city`, `items[0].units`.
7. Kiểm tra `getSuppressedFields()` khi người dùng gửi một field không nằm trong allowlist.
8. Đưa kết quả về public error DTO mà **không làm lộ rejected values**.
9. Kiểm thử cả tầng binder thuần và HTTP với JUnit 5 / MockMvc.
10. Biết khi nào Spring tự ném `MethodArgumentNotValidException` và khi nào controller đọc `BindingResult` tại chỗ.

Bài dùng **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Spring MVC Servlet, Jakarta Bean Validation**. Mọi đoạn thuộc dự án thực thi đều có tên file/package; các đoạn mang nhãn *minh họa* chỉ dùng giải thích API. Kết quả unit/integration tests nêu ở cuối là **kỳ vọng dựa trên mã**, không phải tuyên bố đã thực thi Maven.

## 2. Hai lớp lỗi: chuyển kiểu khác validation

### 2.1. Conversion thất bại

DTO:

~~~java
@NotNull
@Min(1)
private Integer quantity;
~~~

Request:

~~~text
quantity=abc
~~~

Spring biết property `quantity` cần `Integer`, nhưng `"abc"` không thể đổi thành số nguyên. Đây là lỗi **binding/type conversion**, thường có:
- `FieldError#getField()` bằng `"quantity"`.
- `FieldError#getCode()` bằng `"typeMismatch"`.
- `FieldError#isBindingFailure()` bằng `true`.

Một số bước validation tiếp theo có thể báo thêm lỗi liên quan hoặc bỏ qua một property có lỗi binding, tùy cách adapter/validator xử lý; **đừng mặc định tổng số lỗi luôn đúng một**. Điều ổn định cần kiểm tra là có một lỗi conversion tương ứng và giá trị không bị biến thành một số hợp lệ một cách giả tạo.

### 2.2. Conversion thành công nhưng giá trị không hợp lệ

Request:

~~~text
quantity=0
~~~

`"0"` chuyển thành `Integer(0)` thành công. Sau đó `@Min(1)` phát hiện giá trị thấp hơn ngưỡng. `FieldError` lúc này thường có mã `"Min"` và `isBindingFailure()==false`.

Một test mạnh cần chứng minh cả hai tình huống:

| Input | Bind/convert | Validate | Lỗi mong đợi |
| --- | --- | --- | --- |
| `quantity=5` | Thành công → `5` | `@Min(1)` đạt | Không lỗi ở quantity |
| `quantity=0` | Thành công → `0` | `@Min(1)` không đạt | `Min` |
| `quantity=abc` | Không chuyển được | Có thể vẫn kiểm tra phần khác | `typeMismatch` |
| Không gửi `quantity` | Giữ `null` | `@NotNull` không đạt | `NotNull` |
| `customerName=   ` | Bind chuỗi thành công | `@NotBlank` không đạt | `NotBlank` |
| `deliveryDate=2026-12-20` | Parse ngày ISO thành công | `@NotNull` đạt | Không lỗi |
| `deliveryDate=bad` | Chuyển ngày thất bại | Có thể có lỗi kèm theo | `typeMismatch` |

### 2.3. Bean Validation hoạt động sau khi có target

Annotation `@Valid` không sửa dữ liệu đầu vào, không tự cho phép bind thêm field và không phải một converter. Nó yêu cầu validation theo Jakarta provider. `@NotBlank`/`@Email`/`@Min` xác định ràng buộc. Validation cho object nested cần cascade `@Valid`.

`BindingResult` là nơi Spring kết hợp lỗi chuyển kiểu/binding và lỗi validator. Nó kế thừa `Errors`; nhờ vậy có các phương thức đọc lỗi chi tiết mà không cần bắt riêng từng exception.

## 3. API chính cần sử dụng trong thí nghiệm

| API | Công dụng |
| --- | --- |
| `DataBinder` | Bind property values vào Java target, hỗ trợ conversion và validation |
| `WebDataBinder` | Biến thể phù hợp web binding, dùng trong MVC `@InitBinder` |
| `MutablePropertyValues` | Cung cấp một tập input property paths để thí nghiệm không cần HTTP |
| `ConversionService` | Biến chuỗi và nguồn khác sang target type |
| `DefaultFormattingConversionService` | ConversionService với formatters mặc định/annotation formatting |
| `@DateTimeFormat(iso=ISO.DATE)` | Cho phép form date string theo ISO khi binding |
| `@Valid` | Kích hoạt validation và cascade đối tượng khi được hỗ trợ |
| `DataBinder#addValidators` | Đăng ký Spring `Validator` cho binder |
| `DataBinder#bind` | Áp property values và chuyển kiểu |
| `DataBinder#validate` | Gọi validators đã đăng ký, bổ sung lỗi |
| `DataBinder#getBindingResult` | Lấy lỗi hiện có, target info và suppressed fields |
| `BindingResult#hasErrors` | Có field/global error không |
| `BindingResult#getErrorCount` | Tổng số ObjectError/FieldError |
| `BindingResult#getFieldErrors` | Danh sách lỗi gắn field |
| `BindingResult#getGlobalErrors` | Lỗi cấp object, không gắn field cụ thể |
| `FieldError#getField` | Field path, gồm nested/indexed nếu có |
| `FieldError#getCode` | Mã lỗi tổng quát được chọn |
| `FieldError#isBindingFailure` | Phân biệt lỗi binding/conversion với lỗi validator |
| `BindingResult#getSuppressedFields` | Input fields bị loại khỏi binding |
| `BindingResult#getFieldValue` | Giá trị dùng cho hiển thị form, có thể là rejected input |
| `BindingResult#getModel` | Map chứa target và BindingResult cho MVC rendering |

**Cảnh báo an toàn:** `getFieldValue()`, `getRawFieldValue()`, `FieldError#getRejectedValue()`, `BindingResult#getModel()` có thể làm lộ dữ liệu nhập, kể cả thông tin riêng tư. Chúng hữu ích trong logic phía server/hiển thị form có kiểm soát, **không nên serialize nguyên vào JSON lỗi công khai**. Không coi `getDefaultMessage()` là an toàn nếu có custom validator ghép raw input vào message.

## 4. Cấu trúc project thực hành

Project chạy được với Maven:

~~~text
pom.xml
src/main/java/com/example/bindinglab/
  BindingLabApplication.java
  OrderForm.java
  AddressForm.java
  ItemForm.java
  LabIssue.java
  LabReport.java
  OrderLabController.java
src/test/java/com/example/bindinglab/
  BinderLifecycleTest.java
  OrderLabControllerTest.java
~~~

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>binding-conversion-validation-lab</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-web` cung cấp Spring MVC; `spring-boot-starter-validation` mang Jakarta provider; `spring-boot-starter-test` bao gồm JUnit Jupiter, MockMvc, JSONPath và Hamcrest. Ví dụ **không** cần database hay đăng ký filter bảo mật đặc biệt vì chỉ là phòng thí nghiệm; sản phẩm thật cần authentication/authorization và bảo vệ request size.

### 4.2. `BindingLabApplication.java`

~~~java
// src/main/java/com/example/bindinglab/BindingLabApplication.java
package com.example.bindinglab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingLabApplication.class, args);
    }
}
~~~

### 4.3. `OrderForm.java` — top-level form

~~~java
// src/main/java/com/example/bindinglab/OrderForm.java
package com.example.bindinglab;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class OrderForm {

    @NotBlank
    private String customerName;

    @NotBlank
    @Email
    private String contactEmail;

    @NotNull
    @Min(1)
    private Integer quantity;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate deliveryDate;

    @Valid
    private AddressForm address = new AddressForm();

    @Valid
    private List<ItemForm> items = new ArrayList<>();

    public OrderForm() {}

    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public String getContactEmail() { return contactEmail; }
    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public LocalDate getDeliveryDate() { return deliveryDate; }
    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public AddressForm getAddress() { return address; }
    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public List<ItemForm> getItems() { return items; }
    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}
~~~

Các annotations trong DTO có vai trò khác nhau:
- `@NotBlank`: ràng buộc chuỗi không null/rỗng/toàn whitespace.
- `@Email`: ràng buộc định dạng email.
- `@NotNull`: giá trị bắt buộc; cần kết hợp với `@Min` vì `@Min` không xem null là vi phạm.
- `@DateTimeFormat(iso=ISO.DATE)`: hỗ trợ parse ngày từ form string (formatting/conversion), **không phải** constraint Bean Validation.
- `@Valid` trên address/items: yêu cầu cascade validation vào nested object và list elements.
- `Integer`/`LocalDate` giữ được null khi input không chuyển được, tránh nhầm default primitive `int=0` với việc client có gửi hay không.

### 4.4. `AddressForm.java` — nested object

~~~java
// src/main/java/com/example/bindinglab/AddressForm.java
package com.example.bindinglab;

import jakarta.validation.constraints.NotBlank;

public class AddressForm {

    @NotBlank
    private String city;

    public AddressForm() {}

    public String getCity() { return city; }
    public void setCity(String city) {
        this.city = city;
    }
}
~~~

### 4.5. `ItemForm.java` — phần tử list có ràng buộc

~~~java
// src/main/java/com/example/bindinglab/ItemForm.java
package com.example.bindinglab;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ItemForm {

    @NotBlank
    private String sku;

    @NotNull
    @Min(1)
    private Integer units;

    public ItemForm() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Integer getUnits() { return units; }
    public void setUnits(Integer units) {
        this.units = units;
    }
}
~~~

`items[0].units=2` cần:
1. Tìm thuộc tính `items`.
2. Tạo/truy cập phần tử index 0 (nếu binder cho phép auto-grow).
3. Chuyển chuỗi `"2"` sang `Integer`.
4. Gán property `units`.
5. Cascade `@Valid` vào `ItemForm` để kiểm tra `@Min(1)`.

Nếu `items[0].sku` rỗng, `FieldError#getField()` sẽ gắn đường dẫn tương ứng. Index là thông tin cần thiết để frontend xác định dòng sai, nhưng với dynamic Map key chứa email/token phải có policy che key.

## 5. Thiết kế public response để đọc BindingResult mà không rò dữ liệu

### 5.1. `LabIssue.java`

~~~java
// src/main/java/com/example/bindinglab/LabIssue.java
package com.example.bindinglab;

public record LabIssue(
        String field,
        String code,
        String stage) {
}
~~~

`stage` do ứng dụng tự định nghĩa:
- `BIND_CONVERT`: lỗi phát sinh khi binding hoặc type conversion.
- `VALIDATE`: lỗi do constraint/custom validator.

Đây **không phải** tên field do Spring tự sinh ra. Nó được suy từ `FieldError#isBindingFailure()` để minh họa pipeline.

### 5.2. `LabReport.java`

~~~java
// src/main/java/com/example/bindinglab/LabReport.java
package com.example.bindinglab;

import java.util.List;

public record LabReport(
        String status,
        long bindingErrorCount,
        long validationErrorCount,
        int suppressedFieldCount,
        List<LabIssue> issues) {
}
~~~

Report cố ý không có `rejectedValue`, raw error arguments, exception message, target object hay suppressed field names. Trong hệ thống thật, issue code/message có thể được dịch qua `MessageSource`, nhưng bài thực hành tập trung vào **quan sát thứ tự bind–convert–validate và lỗi BindingResult**. Giữ schema tối thiểu tránh làm mất trọng tâm.

### 5.3. Vì sao phải phân biệt suppressed field?

Khi binder cấu hình:

~~~java
binder.setAllowedFields(
        "customerName", "contactEmail",
        "quantity", "deliveryDate",
        "address.city",
        "items[*].sku", "items[*].units");
~~~

và client gửi `adminApproved=true`, field ngoài allowlist bị bỏ qua. Nó có thể xuất hiện trong `BindingResult#getSuppressedFields()` nhưng **không tự động tạo `FieldError`**. Vì vậy `hasErrors()==false` chưa có nghĩa request không gửi những trường bị chặn.

Trong demo, controller sẽ trả 400 nếu `suppressedFieldCount>0`. Không xuất nguyên tên suppressed field: với Map/indexed fields, tên có thể bao gồm dữ liệu do client kiểm soát.

## 6. Controller thực nghiệm: gắn @InitBinder và BindingResult đúng chỗ

### 6.1. `OrderLabController.java`

~~~java
// src/main/java/com/example/bindinglab/OrderLabController.java
package com.example.bindinglab;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@RestController
public class OrderLabController {

    @InitBinder("orderForm")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "contactEmail",
                "quantity",
                "deliveryDate",
                "address.city",
                "items[*].sku",
                "items[*].units");
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(
            path = "/lab/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> submit(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult errors) {

        long bindingErrors = errors.getFieldErrors().stream()
                .filter(FieldError::isBindingFailure)
                .count();
        long validationErrors =
                errors.getErrorCount() - bindingErrors;
        int suppressed = errors.getSuppressedFields().length;

        List<LabIssue> issues = errors.getAllErrors().stream()
                .map(OrderLabController::toPublicIssue)
                .sorted(Comparator.comparing(LabIssue::field)
                        .thenComparing(LabIssue::stage)
                        .thenComparing(LabIssue::code))
                .toList();

        if (errors.hasErrors() || suppressed > 0) {
            return ResponseEntity.badRequest()
                    .body(new LabReport(
                            "REJECTED",
                            bindingErrors,
                            validationErrors,
                            suppressed,
                            issues));
        }

        return ResponseEntity.ok(Map.of(
                "accepted", true,
                "itemCount", form.getItems().size()));
    }

    static LabIssue toPublicIssue(ObjectError error) {
        if (error instanceof FieldError field) {
            boolean binding = field.isBindingFailure();
            return new LabIssue(
                    safeField(field.getField()),
                    binding
                            ? "TYPE_MISMATCH"
                            : publicCode(field.getCode()),
                    binding ? "BIND_CONVERT" : "VALIDATE");
        }

        return new LabIssue(
                "",
                publicCode(error.getCode()),
                "VALIDATE");
    }

    private static String publicCode(String code) {
        if (code == null) {
            return "INVALID_VALUE";
        }

        return switch (code) {
            case "NotBlank", "NotNull" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Min" -> "BELOW_MIN";
            case "Max" -> "ABOVE_MAX";
            default -> "INVALID_VALUE";
        };
    }

    // Chỉ công bố những field paths thuộc contract của lab.
    static String safeField(String raw) {
        if (raw == null) {
            return "";
        }

        if (raw.equals("customerName")
                || raw.equals("contactEmail")
                || raw.equals("quantity")
                || raw.equals("deliveryDate")
                || raw.equals("address.city")) {
            return raw;
        }

        for (int i = 0; i < 8; i++) {
            if (raw.equals("items[" + i + "].sku")
                    || raw.equals("items[" + i + "].units")) {
                return raw;
            }
        }

        return "";
    }
}
~~~

**Phân tích lifecycle của handler:**
1. Spring tạo instance `OrderForm`.
2. `WebDataBinder` áp các request properties được cho phép, thực hiện chuyển kiểu khi cần.
3. `@Valid` khiến Spring chạy validation cho `OrderForm` và nested objects.
4. Do `BindingResult` đứng **ngay sau** parameter có `@Valid @ModelAttribute`, handler nhận các lỗi tại chỗ và tự quyết định response.
5. `getFieldErrors()` và `isBindingFailure()` giúp phân loại các lỗi chuyển kiểu.
6. `getAllErrors()` bao gồm cả lỗi field và global/object.
7. `getSuppressedFields()` được đọc riêng, vì field bị chặn không nhất thiết góp vào `getErrorCount()`.
8. Response có stage/code/field đã whitelist và số lượng lỗi; **không trả raw input, target hoặc framework exception**.

Với route hiện tại không có trực tiếp `@Min` trên controller method parameter, Spring MVC dùng object validation thông thường. Nếu thêm direct method constraints như `@Min` trên `@RequestParam`, MVC 6.1+ có thể dùng built-in method validation và `HandlerMethodValidationException`; không nên đồng nhất loại exception ấy với một `BindingResult` gắn một object argument.

**Không đặt `BindingResult` cách xa validated argument.** Chữ ký đúng:

~~~java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {
    // ...
}
~~~

Nếu bỏ `BindingResult`, Spring thường ném `MethodArgumentNotValidException` khi object validation thất bại và không có handler method-validation khác chi phối. Đặt BindingResult sau tham số khác có thể khiến Spring không coi đó là local errors của form.

## 7. Thực nghiệm độc lập không cần HTTP: WebDataBinder

### 7.1. Các giai đoạn ta tự gọi

Một thí nghiệm trực tiếp:

~~~java
OrderForm target = new OrderForm();
WebDataBinder binder =
        new WebDataBinder(target, "orderForm");

// Đăng ký Spring Validator, ConversionService và policy binding.
binder.bind(propertyValues);    // BIND và CONVERT
BindingResult afterBind = binder.getBindingResult();
binder.validate();              // VALIDATE
BindingResult afterValidate = binder.getBindingResult();
~~~

Đây là **đoạn phương pháp minh họa**, không phải file Java độc lập. Hai biến `afterBind`/`afterValidate` thường tham chiếu cùng `BindingResult` đang được binder tích lũy lỗi; nếu cần so sánh trạng thái **trước và sau**, hãy lưu `getErrorCount()` hay snapshot danh sách errors tại mỗi thời điểm thay vì kỳ vọng object `afterBind` “đóng băng” ở trạng thái cũ.

Trong test dưới đây, một helper tạo binder giống policy của controller. `DefaultFormattingConversionService` có các converters/formatters mặc định và xử lý annotation `@DateTimeFormat`. Validator lấy từ Spring Boot context được đăng ký qua `addValidators`.

### 7.2. `BinderLifecycleTest.java`

~~~java
// src/test/java/com/example/bindinglab/BinderLifecycleTest.java
package com.example.bindinglab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BinderLifecycleTest {

    @Autowired
    Validator springValidator;

    private WebDataBinder newBinder(OrderForm target) {
        WebDataBinder binder =
                new WebDataBinder(target, "orderForm");

        binder.setConversionService(
                new DefaultFormattingConversionService());
        new OrderLabController().configure(binder);
        binder.addValidators(springValidator);

        return binder;
    }

    private MutablePropertyValues validValues() {
        MutablePropertyValues values =
                new MutablePropertyValues();

        values.add("customerName", "Lan");
        values.add("contactEmail", "lan@example.com");
        values.add("quantity", "2");
        values.add("deliveryDate", "2026-12-20");
        values.add("address.city", "Hanoi");
        values.add("items[0].sku", "PEN");
        values.add("items[0].units", "3");

        return values;
    }

    @Test
    void bindConvertsStringValuesBeforeValidation() {
        OrderForm target = new OrderForm();
        WebDataBinder binder = newBinder(target);

        binder.bind(validValues());
        BindingResult result = binder.getBindingResult();

        assertEquals(Integer.valueOf(2),
                target.getQuantity());
        assertEquals(LocalDate.of(2026, 12, 20),
                target.getDeliveryDate());
        assertEquals("Hanoi",
                target.getAddress().getCity());
        assertEquals(1, target.getItems().size());
        assertEquals(Integer.valueOf(3),
                target.getItems().get(0).getUnits());
        assertFalse(result.hasErrors());

        binder.validate();
        assertFalse(result.hasErrors());
    }

    @Test
    void conversionErrorExistsBeforeValidateAndIsPreserved()
            throws Exception {

        MutablePropertyValues values = validValues();
        values.add("quantity", "not-a-number");
        values.add("customerName", "   ");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);

        BindingResult result = binder.getBindingResult();
        FieldError conversion =
                result.getFieldError("quantity");

        assertNotNull(conversion);
        assertEquals("typeMismatch", conversion.getCode());
        assertTrue(conversion.isBindingFailure());

        // @NotBlank CHƯA chạy khi chỉ gọi bind().
        assertFalse(result.hasFieldErrors("customerName"));
        int beforeValidation = result.getErrorCount();

        binder.validate();

        // Sau validate, cùng BindingResult có thêm lỗi.
        assertTrue(result.getErrorCount() > beforeValidation);
        assertTrue(result.getFieldErrors("customerName").stream()
                .anyMatch(e -> "NotBlank".equals(e.getCode())));
        assertTrue(result.getFieldErrors("quantity").stream()
                .anyMatch(FieldError::isBindingFailure));
    }

    @Test
    void invalidDateIsAlsoBindingAndConversionFailure() {
        MutablePropertyValues values = validValues();
        values.add("deliveryDate", "not-a-date");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);

        assertTrue(binder.getBindingResult()
                .getFieldErrors("deliveryDate").stream()
                .anyMatch(FieldError::isBindingFailure));
    }

    @Test
    void nestedConstraintsKeepExactFieldPaths() {
        MutablePropertyValues values = validValues();
        values.add("address.city", "   ");
        values.add("items[0].units", "0");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);
        binder.validate();

        BindingResult result = binder.getBindingResult();

        assertTrue(result.getFieldErrors("address.city").stream()
                .anyMatch(e -> "NotBlank".equals(e.getCode())));
        assertTrue(result.getFieldErrors("items[0].units").stream()
                .anyMatch(e -> "Min".equals(e.getCode())));
    }

    @Test
    void suppressedInputDoesNotAutomaticallyCreateFieldError() {
        MutablePropertyValues values = validValues();
        values.add("adminApproved", "true");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);
        binder.validate();

        BindingResult result = binder.getBindingResult();
        Set<String> suppressed = Set.copyOf(Arrays.asList(
                result.getSuppressedFields()));

        assertEquals(Set.of("adminApproved"), suppressed);
        assertFalse(result.hasErrors());
    }

    @Test
    void publicIssueMappingIgnoresRawRejectedValue() {
        String sensitive = "CANARY_SECRET_VALUE";
        FieldError raw = new FieldError(
                "orderForm",
                "contactEmail",
                sensitive,
                false,
                new String[]{"Email"},
                null,
                "Unsafe message: " + sensitive);

        LabIssue issue = OrderLabController.toPublicIssue(raw);

        assertEquals("contactEmail", issue.field());
        assertEquals("INVALID_EMAIL", issue.code());
        assertEquals("VALIDATE", issue.stage());
        assertFalse(issue.toString().contains(sensitive));
    }
}
~~~

**Sáu test methods** ở class này bao phủ:
- Dữ liệu đã được chuyển kiểu trước `validate()`.
- Conversion errors có trong `BindingResult` **trước** validation.
- Gọi `validate()` bổ sung Bean Validation errors vào **cùng kết quả**.
- `@DateTimeFormat` sai tạo lỗi ở giai đoạn binding.
- Nested validation giữ exact paths `address.city` và `items[0].units`.
- Suppressed fields là một nhóm cần đọc riêng; không tự coi là validation error.
- Mapper công khai không xuất raw rejected value.

Lưu ý cụm `throws Exception` ở một test chỉ nhằm đơn giản hóa chữ ký; `binder.bind()` trong flow thông thường ghi lỗi chuyển kiểu vào `BindingResult` thay vì buộc caller phải catch một `ParseException` ở mọi field.

### 7.3. Kết quả quan sát theo thứ tự

Với input:

~~~text
customerName="   "
contactEmail="lan@example.com"
quantity="not-a-number"
deliveryDate="2026-12-20"
address.city="Hanoi"
items[0].sku="PEN"
items[0].units="3"
~~~

Quan sát logic:

| Thời điểm | Chuyện đã xảy ra | Kiểm tra |
| --- | --- | --- |
| Trước `bind` | Object có fields chưa được gán | `target.getQuantity()==null` |
| Sau `bind` | Các field hợp lệ đã được gán và chuyển kiểu | `deliveryDate` trở thành `LocalDate` |
| Sau `bind` | `quantity` không convert được | Có `FieldError` `typeMismatch` và `isBindingFailure=true` |
| Sau `bind` | `customerName` được gán chuỗi whitespace | Chưa có `NotBlank` error từ validator |
| Sau `validate` | Bean Validation thấy `customerName` chỉ whitespace | Có `NotBlank` error |
| Sau `validate` | Các lỗi binding trước đó còn lưu | `quantity` vẫn có binding failure |
| Khi đọc response | Mã/path/stage an toàn được chọn lọc | Không có rejected value |

Bảng không cam kết một **tổng số lỗi cố định** cho mọi provider và cấu hình, vì ràng buộc `@NotNull` hoặc custom validators có thể phát sinh thêm errors tùy trường hợp. Test được viết theo *đặc tính ổn định* thay vì dựa vào ordering/magic counts.

## 8. Thực nghiệm qua HTTP bằng MockMvc

### 8.1. Tại sao cần cả hai tầng?

Unit test trực tiếp trên `WebDataBinder` cho thấy rõ từng lời gọi. Nhưng chỉ integration test qua MVC mới kiểm tra:
- Parameter resolver tạo `OrderForm` đúng.
- `@InitBinder("orderForm")` được gọi đúng phạm vi.
- Form parameters được convert nhờ MVC `ConversionService`.
- `@Valid` chạy tự động.
- `BindingResult` được truyền ngay sau form argument.
- Controller chọn status 200/400 đúng.
- JSON serialization không lộ dữ liệu nhạy cảm.

### 8.2. `OrderLabControllerTest.java`

~~~java
// src/test/java/com/example/bindinglab/OrderLabControllerTest.java
package com.example.bindinglab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLabControllerTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder order(
            String name, String quantity, String deliveryDate,
            String city, String units) {

        return post("/lab/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", name)
                .param("contactEmail", "lan@example.com")
                .param("quantity", quantity)
                .param("deliveryDate", deliveryDate)
                .param("address.city", city)
                .param("items[0].sku", "PEN")
                .param("items[0].units", units);
    }

    @Test
    void validInputIsBoundConvertedAndAccepted()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted")
                        .value(true))
                .andExpect(jsonPath("$.itemCount")
                        .value(1));
    }

    @Test
    void quantityParsingFailureIsMarkedBindConvert()
            throws Exception {

        mvc.perform(order(
                    "Lan", "CANARY_BAD_NUMBER",
                    "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status")
                        .value("REJECTED"))
                .andExpect(jsonPath("$.bindingErrorCount")
                        .value(1))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("TYPE_MISMATCH")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("BIND_CONVERT")))
                .andExpect(content().string(not(
                        containsString("CANARY_BAD_NUMBER"))));
    }

    @Test
    void invalidDateAlsoTriggersBindingFailure()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "not-a-date", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("deliveryDate")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("TYPE_MISMATCH")));
    }

    @Test
    void validIntegerBelowMinimumIsValidationError()
            throws Exception {

        mvc.perform(order(
                    "Lan", "0", "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.bindingErrorCount")
                        .value(0))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("VALIDATE")));
    }

    @Test
    void nestedInvalidInputsKeepIndexedFieldPaths()
            throws Exception {

        mvc.perform(order(
                    "   ", "2", "2026-12-20", "  ", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].field",
                        hasItems(
                                "customerName",
                                "address.city",
                                "items[0].units")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("VALIDATE")));
    }

    @Test
    void unwantedFormFieldIsSuppressedAndRejected()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "2026-12-20", "Hanoi", "3")
                    .param("adminApproved", "CANARY_ADMIN_777"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.suppressedFieldCount")
                        .value(1))
                .andExpect(content().string(not(
                        containsString("CANARY_ADMIN_777"))))
                .andExpect(content().string(not(
                        containsString("adminApproved"))));
    }
}
~~~

**Đây là 6 integration test methods.** Khi chạy cùng 6 `BinderLifecycleTest` ở mục 7, dự án có **12 JUnit tests dự kiến**. Bài tập tập trung hành vi framework có thể quan sát, không khẳng định output tổng lỗi tuyệt đối ở những trường hợp validator có thể thêm issues.

Kiểm thử status 400 *và* các mã lỗi/path/stage; nếu chỉ assert HTTP 400 thì API có thể đang trả 400 do lý do khác, hoặc vứt hết metadata hữu ích.

### 8.3. Chạy tests

~~~bash
mvn test
~~~

Chạy riêng binder lifecycle:

~~~bash
mvn -Dtest=BinderLifecycleTest test
~~~

Chạy riêng HTTP integration:

~~~bash
mvn -Dtest=OrderLabControllerTest test
~~~

**Kỳ vọng:** 12 tests PASS nếu source files, package và dependencies được đặt đúng. Đây là kỳ vọng tĩnh từ mã minh họa, **không phải chứng nhận Maven đã thực thi**. Khi CI chạy, lấy kết quả thực từ JUnit/Surefire reports, xem stack trace và so sánh các field errors thực tế.

## 9. Thử bằng curl: thấy rõ khác biệt convert và validate

Chạy web server:

~~~bash
mvn spring-boot:run
~~~

### 9.1. Trường hợp hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/lab/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customerName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "quantity=2" \
  --data-urlencode "deliveryDate=2026-12-20" \
  --data-urlencode "address.city=Hanoi" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].units=3"
~~~

Response kỳ vọng:

~~~json
{"accepted":true,"itemCount":1}
~~~

Thứ tự JSON object keys không phải contract. Điểm đáng chú ý: số lượng và ngày đã được convert thành `Integer`/`LocalDate` trước khi controller xử lý, mặc dù HTTP form chỉ truyền text.

### 9.2. Type mismatch

~~~bash
curl -i -X POST http://localhost:8080/lab/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customerName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "quantity=CANARY_BAD_NUMBER" \
  --data-urlencode "deliveryDate=2026-12-20" \
  --data-urlencode "address.city=Hanoi" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].units=3"
~~~

Response HTTP 400 kỳ vọng chứa ít nhất một issue:

~~~json
{
  "field": "quantity",
  "code": "TYPE_MISMATCH",
  "stage": "BIND_CONVERT"
}
~~~

Đoạn JSON này là **một issue trích từ `issues`**, không phải toàn bộ response. Không được xuất `CANARY_BAD_NUMBER` ở bất kỳ field nào của response.

### 9.3. Constraint violation

Đổi thành:

~~~text
quantity=0
~~~

Bây giờ conversion thành công, nhưng `@Min(1)` không đạt. HTTP 400 có issue:

~~~json
{
  "field": "quantity",
  "code": "BELOW_MIN",
  "stage": "VALIDATE"
}
~~~

Sự khác biệt này cho phép client phân biệt “hãy nhập số hợp lệ” với “số phải nằm trong phạm vi cho phép”, đồng thời tránh phụ thuộc vào câu lỗi tiếng Anh của provider.

### 9.4. Ngày không parse được

~~~text
deliveryDate=2026-19-77
~~~

`@DateTimeFormat(iso=ISO.DATE)` yêu cầu ngày hợp lệ tương ứng. Parser không thể tạo `LocalDate` nên xuất hiện binding/conversion error, thường với mã `typeMismatch`. Nếu ngày ISO hợp lệ nhưng không được phép về nghiệp vụ (ví dụ phải sau hôm nay), cần **constraint hoặc service rule khác**, không nhầm lỗi parse với lỗi business.

### 9.5. Gửi field ngoài hợp đồng

~~~text
adminApproved=true
~~~

`@InitBinder` đã whitelist fields. Field ngoài danh sách bị suppress; `BindingResult#getSuppressedFields()` chứa tên đó nhưng `hasErrors()` có thể vẫn false. Controller demo chủ động trả HTTP 400 khi `suppressedFieldCount>0`, và không gửi raw field names trong body. Đây là chính sách của ứng dụng, không phải hành vi 400 tự động cho mọi suppressed field.

## 10. Đọc sâu BindingResult sau khi đã bind/validate

### 10.1. Lấy tất cả lỗi

~~~java
BindingResult result = binder.getBindingResult();

boolean hasErrors = result.hasErrors();
int total = result.getErrorCount();
int fieldCount = result.getFieldErrorCount();
int globalCount = result.getGlobalErrorCount();
~~~

Đoạn trên là **snippet trong một method**, không phải một file Java độc lập. `getErrorCount()` phản ánh các `ObjectError`/`FieldError` đã đăng ký, không tự bao gồm những field bị suppress.

### 10.2. Phân biệt field và global errors

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError field) {
        String path = field.getField();
        String code = field.getCode();
        boolean conversion = field.isBindingFailure();
        // Chỉ xử lý nội bộ hoặc chuyển sang DTO an toàn.
    } else {
        // Lỗi ở cấp object, thường không có field path riêng.
    }
}
~~~

Lỗi toàn đối tượng có thể xuất hiện khi có một class-level constraint kiểm tra nhiều properties, như `startDate <= endDate`. Nếu chỉ gọi `getFieldErrors()`, bạn có thể mất các lỗi global. Ngược lại, một lỗi form cụ thể có thể có nested path như `items[0].units`.

### 10.3. `getCode()` khác `getCodes()`

Một `FieldError` có thể chứa:
- `getCode()` = `Min`.
- `getCodes()` = danh sách chi tiết tùy `MessageCodesResolver`, ví dụ `Min.orderForm.quantity`, `Min.quantity`, `Min.java.lang.Integer`, `Min`.

Dùng `getCodes()` để Spring `MessageSource` tìm bản dịch phù hợp theo mức ưu tiên, nhưng **đừng xuất toàn bộ** codes ra public API: chúng có thể chứa tên object/class nội bộ. Với demo, `publicCode` ánh xạ `Min → BELOW_MIN`, `typeMismatch → TYPE_MISMATCH`.

### 10.4. `getFieldValue()` và rejected value

`BindingResult#getFieldValue("quantity")` có thể trả giá trị đã được format hoặc giá trị nhập bị từ chối để UI điền lại form. `FieldError#getRejectedValue()` có thể chứa chính `CANARY_BAD_NUMBER` hoặc dữ liệu nhạy cảm khác. Bài thử chỉ đọc **metadata an toàn** như `isBindingFailure`, `getCode` và một whitelist field path.

Nếu ứng dụng là một HTML server-side form, quyết định “điền lại” input phải tính tới password/token/PII và quyền truy cập; không dùng cùng cơ chế đó làm JSON error API mặc định. Đối với password/secret, không nên hiển thị lại từ server.

### 10.5. `getModel()` và MVC view rendering

`BindingResult#getModel()` tạo Map với target object và entry tương ứng cho BindingResult (với key theo quy ước `BindingResult.MODEL_KEY_PREFIX`). Nó phục vụ render form/view, **không phải một API error DTO**. Serialize nguyên Map này ra REST response có thể làm lộ toàn bộ model/target.

### 10.6. Snapshot lỗi trước/sau validate

Vì `BindingResult` là object tích lũy, muốn quan sát sự gia tăng lỗi thật:

~~~java
binder.bind(values);
int afterBind = binder.getBindingResult().getErrorCount();

binder.validate();
int afterValidate =
        binder.getBindingResult().getErrorCount();

System.out.println(afterBind);
System.out.println(afterValidate);
~~~

Đây là **snippet minh họa**, không có stdout cố định: số lỗi tùy input và constraint provider. Không lưu hai biến `BindingResult` rồi giả định một object là ảnh chụp trước validate; hãy lưu số đếm hoặc copy danh sách immutable tại thời điểm đó.

## 11. Các khác biệt quan trọng trong Spring MVC

### 11.1. `BindingResult` ngay sau `@Valid @ModelAttribute`

Đúng:

~~~java
@PostMapping("/lab/orders")
public ResponseEntity<?> save(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult result) {
    // Controller tự quyết định phản hồi lỗi.
    return ResponseEntity.ok().build();
}
~~~

Đây là chữ ký **minh họa**, không được thêm như một endpoint thứ hai trong project runnable đã có. `BindingResult` đứng ngay sau form argument liên quan.

Nếu không cung cấp local `BindingResult`, Spring MVC thường ném `MethodArgumentNotValidException` đối với lỗi object validation và framework sẽ xử lý qua exception resolver/`@ControllerAdvice`. Với phương thức có direct `@Constraint` trên parameter/return, built-in method validation từ Spring 6.1 có thể chi phối; lúc đó `HandlerMethodValidationException` mang các `ParameterValidationResult`.

### 11.2. `@RequestBody` có đường conversion khác

~~~java
@PostMapping("/lab/json")
public void saveJson(@Valid @RequestBody OrderForm input) {
    // ...
}
~~~

Đây cũng là **snippet minh họa**, không thuộc project runnable. Với JSON, Spring đọc body qua `HttpMessageConverter`/Jackson. Một input:

~~~json
{"quantity": "CANARY_BAD_NUMBER"}
~~~

có thể không deserialize được Integer và làm phát sinh `HttpMessageNotReadableException` **trước Bean Validation**. Đây không phải cùng loại FieldError `typeMismatch` của form `@ModelAttribute`. Khi JSON đã deserialize thành object và fail constraint, có thể có `MethodArgumentNotValidException`.

**Không dùng `@InitBinder#setAllowedFields` làm whitelist cho Jackson JSON**. Bảo vệ JSON bằng dedicated request DTO, Jackson configuration và service authorization.

### 11.3. `@RequestParam`/`@PathVariable` riêng

Khi controller nhận:

~~~java
@GetMapping("/units")
public int units(@RequestParam int quantity) {
    return quantity;
}
~~~

`quantity=abc` có thể dẫn tới `MethodArgumentTypeMismatchException` từ argument resolver, **không nhất thiết xuất hiện trong BindingResult của một form object**. Kiểm thử đúng con đường nhận request trước khi viết handler.

### 11.4. `@Validated` cho groups và method validation

`@Validated(Create.class)` có thể chọn nhóm constraints khi validate một argument; còn `@Validated` cấp controller class có thể đưa method validation sang AOP. Trong Spring Framework 6.1+ khi muốn built-in MVC method validation, tài liệu khuyến nghị bỏ class-level `@Validated` ở controller nếu chỉ dùng nó cho method validation. Đừng trộn kết quả một `BindingResult` của command object với `ConstraintViolationException` từ service/AOP rồi xem chúng giống nhau.

## 12. Bảo mật property binding trong phòng thí nghiệm

Ví dụ dùng **form DTO riêng** không chứa `role`/`ownerId`/`adminApproved` và `setAllowedFields` rõ ràng. Lợi ích:
- Thêm setter mới vào entity không tự mở input form.
- Các paths không được duyệt sẽ bị suppress.
- Nested/indexed fields chỉ được phép theo whitelist.
- Controller có thể reject request chứa extra fields.

Chú ý:
1. `setAllowedFields` kiểm soát property binding; **không** làm authorization.
2. Constructor binding cũng có bề mặt input theo constructor args; thêm component vào record phải review.
3. `setDeclarativeBinding(true)` có thể dùng để khóa property binding nếu không có allowed fields, nhưng **không tự whitelist constructor parameters**.
4. `setAutoGrowCollectionLimit(8)` hạn chế một số trường hợp auto-grow list; không thay HTTP body size limit hay giới hạn JSON arrays.
5. Map keys có thể chứa email/token; không log/echo raw rejected/suppressed path.
6. Validation chỉ kiểm tra hợp lệ dữ liệu; quyền cập nhật owner/status phải được service xác thực.
7. `getSuppressedFields()` có thể tiết lộ user-supplied path, vì vậy demo chỉ trả **số lượng** suppressed fields.

Nếu cần công khai message đa ngữ, dùng `MessageSource` với allowlisted public error codes; không dùng `FieldError#getDefaultMessage()` chưa được duyệt như message luôn an toàn.

## 13. Thực nghiệm mở rộng: converter và formatter tùy chỉnh

Trong ví dụ chính, Spring xử lý:
- `String → Integer` nhờ converter/editor có sẵn.
- `String → LocalDate` nhờ formatting/conversion hỗ trợ `@DateTimeFormat`.

Nếu ứng dụng có kiểu đặc thù, như `Sku` hoặc `Money`, có thể đăng ký `Converter<String,Sku>`:

~~~java
// Snippet minh họa (cần định nghĩa class Sku và registry).
import org.springframework.core.convert.converter.Converter;

final class SkuConverter implements Converter<String, Sku> {
    @Override
    public Sku convert(String source) {
        return new Sku(source.strip().toUpperCase());
    }
}
~~~

Đây **không phải file độc lập của project**; `Sku` là domain type giả định trong đoạn minh họa. Để dùng thật, định nghĩa `Sku` và đăng ký converter vào `ConversionService` hoặc MVC `FormatterRegistry`. Test cả:
- Input hợp lệ được convert như kỳ vọng.
- Input không hợp lệ tạo binding failure thay vì âm thầm biến thành giá trị khác.
- Converter không được dùng để kiểm tra quyền hoặc tự tìm dữ liệu nhạy cảm.
- Validator kiểm tra constraints trên object **sau conversion**.
- Với `Formatter<T>`, test `parse`/`print` theo `Locale` và round-trip.

Không cố gắng chuyển `Exception#getMessage()` của converter thành public error text: nó có thể chứa raw input. Công bố mã `TYPE_MISMATCH` và path an toàn là đủ cho phòng thí nghiệm.

## 14. Bảng lỗi hay gặp và cách tự chẩn đoán

| Triệu chứng | Nguyên nhân | Cách sửa/thử nghiệm |
| --- | --- | --- |
| Form quantity vẫn là String | DTO khai báo sai kiểu hoặc không bind đúng | Kiểm tra getter/setter và property name |
| `quantity=abc` trả status 500 | Exception handler sai hoặc converter ném lỗi ngoài pipeline | Test `BindingResult`/argument resolver và log bảo mật |
| `quantity=0` không có `Min` error | Chưa chạy validation hoặc thiếu `@Valid`/validator | Gọi `binder.validate()` hoặc kiểm tra MVC signature |
| `@DateTimeFormat` bị bỏ qua | Dùng conversion service không hỗ trợ formatting annotations | Dùng `DefaultFormattingConversionService` hoặc MVC config |
| `deliveryDate=bad` báo constraint thay vì parse | Nhầm type conversion với validator | Kiểm tra `FieldError#isBindingFailure()` |
| Nested `address.city` không validate | Thiếu `@Valid` trên address | Thêm cascade validation |
| Indexed `items[0].units` không xuất | Không tạo list element/thiếu setter/allowed field | Kiểm tra auto-grow, field name và whitelist |
| `result.hasErrors()` false dù gửi field lạ | Suppressed field không tự là FieldError | Đọc `getSuppressedFields()` riêng |
| Controller không nhận `BindingResult` | Đặt sai vị trí hoặc dùng method validation khác | Đặt ngay sau annotated model attribute |
| `getErrorCount()` không tăng sau validate | DataBinder chưa đăng ký validator hoặc input không vi phạm | Kiểm tra `addValidators` và test input |
| Lỗi mất index khi hiển thị | Mapper rút gọn path thành tên field cuối | Giữ nested/indexed path sau allowlist |
| JSON type error không có `FieldError` | Jackson deserialize thất bại trước validation | Xử lý `HttpMessageNotReadableException` |
| Form type error không có code public | Trả raw Spring ObjectError | Ánh xạ `typeMismatch→TYPE_MISMATCH` |
| `getDefaultMessage()` chứa raw input | Custom validator/interpolation không an toàn | Chọn message từ catalog đáng tin cậy |
| Backend echo toàn form object | Serialize target/`getModel()` vào error response | Dùng public issue DTO riêng |
| Unit binder pass, HTTP fail | `@InitBinder`/MVC config khác test setup | Thêm MockMvc integration tests |
| Duplicate errors trên một field | Conversion + constraint hoặc nhiều constraints | Xét riêng stage/code; đừng ép số lượng khi không cần |
| Locale khác gây khác thông báo | MessageSource resolve theo request locale | Test code/path ổn định, messages localized |
| Thay đổi model mở field mới | Mutable entity bind trực tiếp | Dedicated input DTO + allowlist + regression tests |

## 15. Bài tập tự luyện theo thứ tự

1. Chạy test valid binder, đặt breakpoint ngay trước/sau `binder.bind`. Quan sát type của `quantity` và `deliveryDate`, không chỉ giá trị string gốc.
2. Đổi quantity thành `"abc"`. Đọc `getFieldError("quantity").getCode()` và `isBindingFailure()` **trước `validate()`**.
3. Đổi quantity thành `"0"`, so sánh trước/sau validate để chứng minh conversion thành công còn `Min` thất bại.
4. Gửi `customerName="  "`. Chứng minh binder gán chuỗi nhưng `@NotBlank` chỉ báo lỗi sau validation.
5. Gửi `deliveryDate="2026-13-40"` và ISO date hợp lệ, so sánh `LocalDate` và binding failure.
6. Thêm `items[1].sku=""`, `items[1].units=0`; xác minh indexed paths và giới hạn auto-grow.
7. Thêm một class-level constraint cho `OrderForm` để tạo global `ObjectError`; so sánh `getAllErrors()` và `getFieldErrors()`.
8. Thêm một field ngoài allowlist trong HTTP request; kiểm tra `getSuppressedFields()` và việc controller trả mã 400 dù `hasErrors()` có thể false.
9. Bỏ `BindingResult` khỏi chữ ký handler trong nhánh thử nghiệm, kiểm tra exception MVC tạo ra, rồi khôi phục.
10. Viết một endpoint `@RequestBody` JSON và gửi `quantity="abc"` để phân biệt Jackson deserialize errors và form typeMismatch.
11. Tạo custom `Converter<String,Sku>`, kiểm thử parse thành công, parse thất bại và public error mapping.
12. Test `@DateTimeFormat` trên `en-US` và `vi-VN`; khi chọn ISO, wire format ngày phải ổn định theo contract.
13. Thêm dữ liệu nhạy cảm vào một `FieldError` giả và kiểm tra public response không có marker đó.
14. So sánh `BindingResult#getModel()` với public DTO: chỉ dùng getModel khi phục vụ view có kiểm soát, không trả nguyên target.
15. Thêm security/authorization test để bảo đảm form không thể tự đặt `adminApproved` hoặc `ownerId`.

## 16. Checklist trước khi đưa pipeline vào API production

- [ ] DTO đầu vào riêng, không bind trực tiếp JPA/domain entity.
- [ ] `@ModelAttribute` và `@RequestBody` được kiểm thử theo **hai pipeline khác nhau**.
- [ ] Converters/formatters có tests riêng cho input thành công, sai kiểu, boundary và Locale khi cần.
- [ ] `@Valid` và nested `@Valid` đã đặt đúng; `@NotNull` có khi kiểu nullable cần bắt buộc.
- [ ] Khi dùng `DataBinder` trực tiếp, gọi `bind` rồi `validate` và đọc `BindingResult`.
- [ ] Ở MVC, `BindingResult` nằm ngay sau validated form argument khi muốn xử lý cục bộ.
- [ ] Thử input `abc` vs `0` để phân biệt `typeMismatch` và `Min`.
- [ ] Không dùng `getErrorCount()` thay `getSuppressedFields()`.
- [ ] Dùng `getAllErrors()` khi cần cả field và global violations.
- [ ] Nested/indexed paths được giữ đúng, đồng thời canonicalize Map keys nếu nhạy cảm.
- [ ] Không trả rejected values, raw exception messages, target objects, `getModel()` hoặc full Spring errors.
- [ ] Public error codes ổn định; message tra từ `MessageSource` khi đa ngữ.
- [ ] Không dùng validation như authorization; quyền sửa object/role/owner ở service layer.
- [ ] Unit binder tests và HTTP integration tests đều chạy trong CI.
- [ ] Ghi nhận số test pass/fail thực từ Maven/JUnit; không coi mô tả kỳ vọng là kết quả đã chạy.
- [ ] Khi thay Spring/Jakarta provider, chạy lại regression tests cho binding order, conversion, validation và exception mapping.

## 17. Tổng kết và tài liệu tham khảo

Ba dòng có thể nhớ:

~~~text
bind(values)   = tìm field + chuyển kiểu + gán hoặc ghi binding error
validate()     = kiểm tra constraints trên target + ghi validation error
BindingResult  = một nơi đọc cả hai loại lỗi cùng suppressed fields
~~~

**Bản chất của bài:** một request HTTP không đi trực tiếp từ String sang “hợp lệ/không hợp lệ”. Spring phải tìm property, chuyển sang Java type rồi mới có thể áp những ràng buộc tương ứng. `BindingResult` giúp kiểm chứng từng sai khác mà không phải đoán theo một câu exception.

Tài liệu chính thức:
- Spring Framework 6.2 — Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html
- Spring Framework 6.2 — Java Bean Validation, Configuring a DataBinder: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — @ModelAttribute: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — @InitBinder: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework 6.2 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — BindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — FieldError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — DefaultFormattingConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
