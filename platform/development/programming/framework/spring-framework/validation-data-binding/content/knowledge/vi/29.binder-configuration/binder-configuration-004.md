# Thứ tự và phạm vi cấu hình cục bộ hoặc toàn cục của WebDataBinder

## 1. Vấn đề cần giải quyết

Trong Spring MVC, khi một HTTP request được ánh xạ vào tham số `@ModelAttribute`, framework có thể tạo `WebDataBinder` để gán giá trị, chuyển kiểu, định dạng và kiểm tra dữ liệu. Một ứng dụng thường cần nhiều mức cấu hình:

- Chính sách dùng chung: chỉ cho phép các field hợp lệ, dùng một `ConversionService`, đăng ký validator toàn cục.
- Chính sách áp dụng cho nhiều controller: bổ sung quy tắc binding/validation vào một nhóm màn hình biểu mẫu.
- Chính sách riêng cho một controller hoặc một model attribute: thêm validator hoặc formatter chỉ phù hợp với form đó.

**Câu hỏi chính:** Nếu cùng một binder nhận cấu hình từ cả nơi toàn cục lẫn cục bộ, Spring thực thi những cấu hình ấy theo **thứ tự nào**, ở **phạm vi nào**, và chúng **cộng dồn hay ghi đè** nhau?

Với Spring MVC (Servlet stack), mô hình cần nhớ là:

1. Cấu hình nền của MVC (ví dụ converter/formatter/validator đã được khai báo qua MVC configuration) được đưa vào binder khi nó được tạo.
2. Các phương thức `@InitBinder` có hiệu lực từ `@ControllerAdvice` được áp dụng **trước** các phương thức `@InitBinder` của controller đích.
3. Nếu có nhiều `@ControllerAdvice`, thứ tự giữa những advice phù hợp được điều khiển theo cơ chế `Ordered` / `@Order`.
4. **Hành vi cuối cùng phụ thuộc từng thao tác cấu hình:** `addValidators(...)` là bổ sung, trong khi `setValidator(...)` hay `setAllowedFields(...)` có tính chất đặt/thay cấu hình hiện có.

Đừng hiểu sai rằng “local luôn thắng global” hoặc “global luôn áp đặt bất biến”. **Thứ tự áp dụng** là một phần; **ngữ nghĩa của setter/adder** là phần còn lại.

## 2. WebDataBinder là gì và nó được tạo vào lúc nào?

`org.springframework.web.bind.WebDataBinder` mở rộng `DataBinder` của Spring, dùng trong môi trường web để quản lý việc binding các thuộc tính request vào đối tượng Java và báo lỗi.

Ví dụ, request:

```text
POST /orders
Content-Type: application/x-www-form-urlencoded

code=ORD-17&quantity=3
```

có thể được ánh xạ vào `OrderForm`:

```java
public class OrderForm {
    private String code;
    private Integer quantity;

    // Public constructor, getters, setters...
}
```

Spring MVC làm các bước tổng quát:

```text
HTTP request
    │
    ▼
HandlerMapping / HandlerAdapter chọn controller method
    │
    ▼
Tạo / tìm model attribute và WebDataBinder
    │
    ├── Cấu hình binder chung của MVC
    ├── Các @InitBinder từ @ControllerAdvice phù hợp
    └── Các @InitBinder từ controller đích
    │
    ▼
Bind giá trị HTTP → property conversion/formatting
    │
    ▼
@Valid / @Validated (nếu được yêu cầu)
    │
    ▼
BindingResult / Errors hoặc nhánh exception phù hợp
    │
    ▼
Controller method và xử lý nghiệp vụ
```

Sơ đồ là cách hiểu về **luồng cấu hình cho một binder**; chi tiết thứ tự khởi tạo object, constructor binding và argument resolution có thể thay đổi theo kiểu tham số. Không dùng sơ đồ này để khẳng định tất cả `@RequestParam`, `@RequestBody` hay mọi phương thức đều dùng chính một `WebDataBinder`.

**Mỗi request/model-attribute binding dùng binder tương ứng**, không phải một `WebDataBinder` singleton để bạn thay đổi rồi dùng lại cho tất cả người dùng. Ngược lại, các class `@ControllerAdvice`, validator hoặc formatter được đăng ký làm Spring bean có thể là singleton và cần thread-safe nếu giữ state.

## 3. Ba cấp cấu hình cần phân biệt

| Cấp | Điểm cấu hình | Phạm vi chủ yếu |
| --- | --- | --- |
| MVC infrastructure | `WebMvcConfigurer#addFormatters`, `getValidator` và các điểm cấu hình MVC | Dùng chung trong cơ chế MVC conversion/validation |
| Chia sẻ giữa các controller | `@ControllerAdvice` / `@RestControllerAdvice` chứa `@InitBinder` | Mọi controller hoặc subset được advice selector chọn |
| Cục bộ một controller | `@InitBinder` trong `@Controller` hoặc `@RestController` | Controller đó; có thể giới hạn thêm theo tên model attribute |

### 3.1. Cấu hình MVC infrastructure

Ví dụ cung cấp converter dùng chung cho các tham số được bind:

```java
@Configuration
public class ConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
    }
}
```

Đây là **đoạn tích hợp minh họa**, cần import `@Configuration`, `WebMvcConfigurer`, `FormatterRegistry` và class `StringToOrderCodeConverter`. `WebMvcConfigurer` dành cho Spring MVC; đối với WebFlux reactive phải dùng `WebFluxConfigurer`.

Khi có Jakarta Bean Validation provider (ví dụ từ `spring-boot-starter-validation`), cấu hình mặc định của MVC có thể sử dụng `LocalValidatorFactoryBean` làm validator chung. Để chỉ thêm rule kiểm tra một form, thường **không cần thay `WebMvcConfigurer#getValidator()`**: thêm local validator vào binder sẽ giữ nền kiểm tra Jakarta.

Cấp này không có nghĩa một HTTP JSON field sẽ tự dùng converter được thêm vào `FormatterRegistry`. `@RequestBody` dùng HTTP message converter/Jackson để decode JSON và sau đó có thể validate object.

### 3.2. Cấu hình chia sẻ với @ControllerAdvice

```java
@ControllerAdvice
public class CommonBindingAdvice {

    @InitBinder("order")
    public void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
    }
}
```

Đây là đoạn minh họa. `@ControllerAdvice` áp dụng cho các controller trong phạm vi advice, còn `@InitBinder("order")` chỉ chọn binder của model attribute có tên `order`. Trong controller khác có `@ModelAttribute("profile")` thì method này **không áp dụng** cho binder tên `profile`.

### 3.3. Cấu hình cục bộ trong controller

```java
@RestController
public class OrdersController {

    private final OrderCodeValidator orderCodeValidator;

    public OrdersController(OrderCodeValidator orderCodeValidator) {
        this.orderCodeValidator = orderCodeValidator;
    }

    @InitBinder("order")
    void initOrder(WebDataBinder binder) {
        binder.addValidators(orderCodeValidator);
    }

    @PostMapping("/orders")
    public String submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {
        return errors.hasErrors() ? "INVALID" : "ACCEPT";
    }
}
```

Đây là đoạn minh họa tích hợp cần các class, imports và annotations tương ứng. Method `@InitBinder` chỉ có tác dụng đối với binder trong `OrdersController` và matching attribute name. Một controller khác không tự chạy method này chỉ vì có bean cùng kiểu `OrderForm`.

Lưu ý `BindingResult` phải đứng ngay sau `@ModelAttribute` để nhận lỗi binding/validation của đúng object.

## 4. Thứ tự áp dụng chính xác: global trước local

Tài liệu Spring MVC nêu rõ sự khác biệt:

- Với **`@InitBinder`** và **`@ModelAttribute`**: phương thức từ `@ControllerAdvice` được áp dụng **trước** phương thức cục bộ trên controller.
- Với **`@ExceptionHandler`**: phương thức local của controller được xem xét **trước** các exception handlers toàn cục.

Đừng mang thứ tự xử lý `@ExceptionHandler` sang `@InitBinder` — hai cơ chế không có cùng quy tắc ưu tiên.

Ví dụ:

```java
@ControllerAdvice
@Order(100)
public class GlobalBinderAdvice {

    @InitBinder("order")
    void applyGlobal(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
    }
}

@RestController
public class OrdersController {

    @InitBinder("order")
    void applyLocal(WebDataBinder binder) {
        binder.addValidators(orderCodeValidator);
    }
}
```

Đây là đoạn minh họa cấu trúc, chưa có đầy đủ constructor/field/import. Khi một binder `order` được tạo cho `OrdersController`, phương thức global đủ điều kiện được chạy **trước** phương thức local.

**Quan trọng:** `@Order(100)` trên global advice **không** đưa advice chạy sau một controller-local `@InitBinder`. Nó được dùng để sắp xếp các **advice beans** khi có nhiều advice phù hợp; local vẫn theo giai đoạn của controller.

### 4.1. Nhiều @ControllerAdvice thì @Order hoạt động thế nào?

Ví dụ:

```java
@ControllerAdvice
@Order(10)
class BaseBindingAdvice {
    @InitBinder("order")
    void base(WebDataBinder binder) {
        // Cấu hình chia sẻ có ưu tiên sớm hơn
    }
}

@ControllerAdvice
@Order(20)
class FeatureBindingAdvice {
    @InitBinder("order")
    void feature(WebDataBinder binder) {
        // Cấu hình chia sẻ áp dụng sau BaseBindingAdvice
    }
}
```

Đây là **đoạn minh họa riêng**, không ghép đồng thời vào chương trình ví dụ ở mục 7. Trong hai advice singleton thông thường có selector cùng khớp, giá trị `@Order` nhỏ hơn có ưu tiên sớm hơn. Một class hiện thực `Ordered` cũng có thể cung cấp thứ tự. Hành vi chi tiết của advice scoped như request/session scope có ngoại lệ, vì thế nên giữ advice config đơn giản, không phụ thuộc thứ tự ngầm định.

**Không nên dựa vào thứ tự của nhiều `@InitBinder` methods bên trong cùng một advice/controller khi chúng cùng sửa một property.** Một phương thức được thiết kế rõ ràng, hoặc tách thành advice có `@Order` tường minh, sẽ dễ kiểm soát và test hơn.

### 4.2. Thứ tự nền MVC và @InitBinder

Về cơ bản, `WebBindingInitializer`/infrastructure áp dụng các thiết lập dùng chung như `ConversionService`, validator và những tùy chọn binder mặc định trong quá trình khởi tạo binder; sau đó các method `@InitBinder` tùy biến binder cho handler tương ứng. Vì thế một local `@InitBinder` có thể thấy validator mặc định đã được thiết lập và bổ sung thêm validator bằng `addValidators(...)`.

Đừng hiểu rằng Spring thực hiện một lượt validation trước global advice rồi sau đó lại chạy local. Các hook cấu hình chuẩn bị binder; binder **sau đó** thực hiện binding/validation theo cơ chế xử lý argument.

## 5. Phạm vi của @ControllerAdvice và @InitBinder("name")

Có hai bộ lọc độc lập.

### 5.1. Lọc theo controller bằng @ControllerAdvice

Mặc định advice áp dụng với mọi controller được framework nhận diện. Bạn có thể thu hẹp bằng:

```java
@ControllerAdvice(annotations = RestController.class)
class RestOnlyBindingAdvice {
    // Chỉ những controller có marker RestController phù hợp.
}

@ControllerAdvice(basePackages = "demo.web.admin")
class AdminBindingAdvice {
    // Chỉ controller thuộc package được chỉ định.
}

@ControllerAdvice(assignableTypes = OrdersController.class)
class OrdersOnlyBindingAdvice {
    // Chỉ class/controller matching type.
}
```

Đây là các **ví dụ selector tách biệt**. Bạn cũng có thể dùng `basePackageClasses` để tránh string package name. Không cần tạo nhiều advice như vậy cho một form đơn giản.

Các selector được đánh giá theo phạm vi controller; không phải theo đường URL HTTP hay số lượng tham số. Nếu ứng dụng có nhiều module, hãy giữ advice selector đủ hẹp để không vô tình thêm một validator không hỗ trợ form của module khác.

### 5.2. Lọc theo object name bằng @InitBinder

`@InitBinder("order")` có hiệu lực với binder có object name `order`. Chẳng hạn:

```java
public String create(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult errors) {
    // ...
}
```

matches `"order"`.

Nhưng:

```java
public String edit(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

không matching `"order"`.

Một `@InitBinder` không truyền attribute names sẽ áp dụng cho mọi binder phù hợp **trong phạm vi controller/advice của nó**. Một `@InitBinder({"order","quote"})` có thể chỉ định nhiều tên. Cần phân biệt tên model attribute với tên class, tên biến Java hoặc URL path: chúng không nhất thiết giống nhau.

### 5.3. Ma trận phạm vi nhanh

| Vị trí method | Attribute name | Tác dụng |
| --- | --- | --- |
| Trong `OrdersController` | `@InitBinder("order")` | Chỉ binder `order` trong OrdersController |
| Trong `OrdersController` | `@InitBinder` | Các binder phù hợp của OrdersController |
| Trong `@ControllerAdvice` không selector | `@InitBinder("order")` | Các binder `order` trong mọi controller |
| Trong `@ControllerAdvice(assignableTypes=...)` | `@InitBinder("order")` | Binder `order` chỉ ở các controller được chọn |
| MVC `WebMvcConfigurer#addFormatters` | Không có binder name riêng | Converter/formatter dùng chung theo cơ chế MVC |

Nếu một controller không có `@ModelAttribute("order")` thì method `@InitBinder("order")` có thể không được gọi cho request đó. Muốn kiểm thử phạm vi, phải dùng request được MVC xử lý, không chỉ gọi Java method bằng `new Controller()`.

## 6. Khi nhiều cấu hình cùng chạm một binder: cộng dồn hay ghi đè?

Đây là phần dễ gây lỗi nhất, vì **thứ tự chạy không tự xác định chiến lược hợp nhất**.

| API | Tác dụng lên binder | Hệ quả |
| --- | --- | --- |
| `binder.addValidators(v1,v2)` | Bổ sung validator vào danh sách hiện có | Giữ được global Bean Validation khi cấu hình đúng |
| `binder.setValidator(v)` | Thay danh sách validator đang có bằng `v` | Có thể làm mất validator Jakarta mặc định |
| `binder.replaceValidators(v1,v2)` | Thay toàn bộ danh sách bằng các validator mới | Dùng khi chủ động xác định chính xác danh sách cần chạy |
| `binder.setAllowedFields("a","b")` | Thiết lập danh sách field được phép | Lời gọi sau có thể thay cấu hình trước; không tự giao nhau |
| `binder.setDisallowedFields(...)` | Đặt các field bị cấm theo mẫu | Dễ thiếu khi DTO mở rộng; ưu tiên allowlist khi phù hợp |
| `binder.setDeclarativeBinding(true)` | Bật cấu hình chỉ cho phép constructor binding và property binding được cho phép rõ ràng | Giảm việc bind property ngoài ý muốn |
| `binder.addCustomFormatter(...)` | Đăng ký formatter cục bộ cho kiểu/field | Có thể làm thay đổi hành vi so với formatter dùng chung |
| `binder.registerCustomEditor(...)` | Đăng ký property editor theo kiểu hoặc field | Có thể ảnh hưởng conversion của trường trùng phạm vi |

### 6.1. Additive: thêm validators

Giả sử MVC đã đăng ký `LocalValidatorFactoryBean` để xử lý `@NotBlank`, `@Min`.

```java
@InitBinder("order")
void configure(WebDataBinder binder) {
    binder.addValidators(globalPolicyValidator, localPolicyValidator);
}
```

Các validator bổ sung có thể ghi lỗi vào **cùng** `BindingResult`. Nếu bạn dùng `setValidator(localPolicyValidator)` thay cho `addValidators`, danh sách validator mặc định có thể bị thay thế. Khi đó annotation Jakarta trên DTO có nguy cơ không còn được kiểm tra qua lượt binder validation này.

**Quy tắc:** cần cộng thêm rule thì dùng `addValidators`; chỉ dùng `setValidator`/`replaceValidators` nếu thật sự muốn thay danh sách.

### 6.2. Replacing: allowedFields

Ví dụ global advice thiết lập:

```java
binder.setAllowedFields("code", "quantity");
```

Sau đó local lại gọi:

```java
binder.setAllowedFields("code", "quantity", "internalNote");
```

Vì đây là setter cấu hình, lời gọi sau **không phải một phép lấy giao tự động** với danh sách trước. Trong mô hình global-trước-local, controller local có thể vô tình mở rộng tập property có thể bind và **làm yếu chính sách bảo mật toàn cục**.

Nếu global đã triển khai allowlist nghiêm ngặt, chính sách local cần tránh thay thế nó bằng một danh sách rộng hơn. Nếu thực sự cần tập khác, hãy thiết kế chính sách chung rõ ràng, kết hợp/intersect ở tầng được ủy quyền và viết test request với field không được phép.

### 6.3. Formatter và PropertyEditor có khả năng chồng lấn

Một formatter chung có thể được đăng ký qua:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DateFormatter("yyyy-MM-dd"));
}
```

Trong một controller, có thể tùy biến cụ thể cho field:

```java
@InitBinder("event")
void initEvent(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("dd/MM/yyyy"), "startDate");
}
```

Đây là **hai đoạn minh họa riêng**, giả sử `startDate` có kiểu `java.util.Date` và các import tương ứng. Cấu hình cục bộ có thể thay đổi cách binder xử lý field cụ thể so với formatter chung. Không viết hai formatter xung đột cho cùng field mà không có test xác định cú pháp được chấp nhận.

### 6.4. Trùng validator hoặc @InitBinder

Nếu một validator được thêm từ cả advice toàn cục và controller local, hai lần đăng ký có thể gây hai lần validation/các lỗi trùng; không nên coi mọi danh sách API sẽ tự khử trùng theo logic nghiệp vụ. Hãy tách chủ sở hữu từng rule rõ ràng và dùng integration test xác nhận số lỗi theo field.

## 7. Ví dụ Java 17 + Spring Boot 3.5.6 chạy được

Ví dụ thiết kế hai endpoint có **cùng kiểu form và cùng tên model attribute** nhưng phạm vi local khác nhau:

- `POST /orders`: có global validation **và** local validation riêng.
- `POST /quotes`: chỉ có global validation; không nhận local policy của OrdersController.
- Global `@ControllerAdvice @InitBinder("order")` đặt allowlist `code, quantity` và thêm rule số lượng không vượt 5.
- Local `OrdersController @InitBinder("order")` thêm rule không nhận mã `BLOCKED`.
- Global Bean Validation từ `spring-boot-starter-validation` vẫn kiểm tra `@NotBlank` và `@Min(1)`.
- Field `internalNote` tồn tại trên form nhưng không được cho phép bind; nếu request cố gửi field đó, controller chủ động báo `REJECTED_FIELDS`.

Đây là ứng dụng Spring MVC Servlet stack. Không cần database hoặc template engine.

### 7.1. Cấu trúc thư mục

```text
binder-order-scope/
├── pom.xml
└── src/main/java/demo/binding/
    ├── BinderScopeApplication.java
    ├── OrderForm.java
    ├── QuantityPolicyValidator.java
    ├── BlockedCodeValidator.java
    ├── GlobalOrderBindingAdvice.java
    ├── FormResponses.java
    ├── OrdersController.java
    └── QuotesController.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>binder-order-scope</artifactId>
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

### 7.3. BinderScopeApplication.java

```java
package demo.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderScopeApplication.class, args);
    }
}
```

### 7.4. OrderForm.java

```java
package demo.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {

    @NotBlank
    private String code;

    @NotNull
    @Min(1)
    private Integer quantity;

    // Có setter nhưng cố tình KHÔNG cho bind từ HTTP request.
    private String internalNote;

    public OrderForm() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
```

`internalNote` dùng để minh họa nguy cơ **mass assignment**. Dù có public setter, global binder chỉ cho bind `code` và `quantity`. Trong thực tế, tốt hơn nữa là không đặt field nhạy cảm trong request DTO ngay từ đầu.

### 7.5. QuantityPolicyValidator.java

```java
package demo.binding;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class QuantityPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if (form.getQuantity() != null && form.getQuantity() > 5) {
            errors.rejectValue(
                "quantity", "quantityLimit",
                "Mỗi yêu cầu tối đa 5 đơn vị");
        }
    }
}
```

Validator này phù hợp cả OrdersController và QuotesController vì **global advice** sẽ gắn nó vào binder `order` của cả hai.

### 7.6. BlockedCodeValidator.java

```java
package demo.binding;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class BlockedCodeValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if ("BLOCKED".equalsIgnoreCase(form.getCode())) {
            errors.rejectValue(
                "code", "blockedCode",
                "Mã này không được dùng để đặt hàng");
        }
    }
}
```

Đây là **quy tắc local** được OrdersController thêm vào. Dùng `"BLOCKED".equalsIgnoreCase(...)` để tránh NullPointerException khi `code` không có giá trị.

### 7.7. GlobalOrderBindingAdvice.java

```java
package demo.binding;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
@Order(100)
public class GlobalOrderBindingAdvice {

    private final QuantityPolicyValidator quantityPolicy;

    public GlobalOrderBindingAdvice(QuantityPolicyValidator quantityPolicy) {
        this.quantityPolicy = quantityPolicy;
    }

    @InitBinder("order")
    public void configure(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
        binder.addValidators(quantityPolicy);
    }
}
```

Giải thích:

- `@ControllerAdvice` áp dụng cho cả hai controller, vì ví dụ không đặt selector hẹp hơn.
- `@InitBinder("order")` chỉ chọn binder thuộc attribute tên `order`.
- `setAllowedFields("code","quantity")` thiết lập allowlist chung.
- `addValidators(quantityPolicy)` thêm rule số lượng, giữ validator mặc định của MVC.
- `@Order(100)` sẽ có ý nghĩa so sánh **khi còn các advice beans khác**; không chuyển global method xuống sau local method.

Import `org.springframework.stereotype.Controller` trong file này không cần thiết và có thể bỏ; nó **không** tạo thêm một controller vì class chỉ có `@ControllerAdvice`. Phần code Java ở trên vẫn biên dịch khi import thừa, nhưng giữ import đúng mục đích sẽ sạch hơn trong dự án thực tế.

### 7.8. FormResponses.java

```java
package demo.binding;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

final class FormResponses {

    private FormResponses() {
    }

    static ResponseEntity<String> build(
            String type, OrderForm form, BindingResult errors) {

        // Không coi field bị chặn binding là request hợp lệ.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("REJECTED_FIELDS");
        }

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + shortCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                    .body("INVALID|" + details);
        }

        return ResponseEntity.ok(
            "ACCEPT|" + type
            + "|" + form.getCode()
            + "|" + form.getQuantity()
            + "|note=" + form.getInternalNote());
    }

    private static String shortCode(FieldError error) {
        String[] codes = error.getCodes();
        return codes == null || codes.length == 0
                ? "unknown"
                : codes[codes.length - 1];
    }
}
```

Helper này được hai controller sử dụng để có cùng kiểu response. Các test có thể so sánh error codes tổng quát mà không phụ thuộc thông báo tiếng Anh/Việt của provider. Chương trình chủ động từ chối mọi request có suppressed fields; điều này **không tự xảy ra** chỉ vì `setAllowedFields` được gọi. Trong ứng dụng production, bạn nên dùng error DTO và error codes ổn định thay vì ghép một chuỗi.

### 7.9. OrdersController.java

```java
package demo.binding;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    private final BlockedCodeValidator blockedCode;

    public OrdersController(BlockedCodeValidator blockedCode) {
        this.blockedCode = blockedCode;
    }

    @InitBinder("order")
    void localRules(WebDataBinder binder) {
        // Global advice đã được áp dụng. Chỉ bổ sung, không thay.
        binder.addValidators(blockedCode);
    }

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> create(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        return FormResponses.build("order", form, errors);
    }
}
```

Khi `OrdersController` xử lý binder `order`, cấu hình global từ advice áp dụng **trước**, rồi local `addValidators(blockedCode)`. Cả global Jakarta Bean Validation, global custom rule và local custom rule có thể đóng góp lỗi.

### 7.10. QuotesController.java

```java
package demo.binding;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuotesController {

    @PostMapping(
        path = "/quotes",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> quote(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        // Không có @InitBinder local của OrdersController tại đây.
        return FormResponses.build("quote", form, errors);
    }
}
```

Cả hai controller đều nhận `@ModelAttribute("order")`, vì vậy global advice sẽ tác động lên cả hai. Nhưng chỉ OrdersController có `@InitBinder` local, nên QuotesController **không tự có** rule `blockedCode`.

## 8. Chạy ví dụ và kiểm chứng thứ tự/phạm vi

Trong thư mục chứa `pom.xml`, cần Java 17+ và Maven 3.x:

```bash
mvn -q spring-boot:run
```

Server thường nghe ở `http://localhost:8080` nếu cổng trống. Gửi các lệnh từ một terminal bash/zsh/WSL khác. Các phần `text` bên dưới là **response body**, không bao gồm HTTP headers hoặc Spring/Maven logs.

### 8.1. Trường hợp A — form hợp lệ

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=3'
```

HTTP 200, body:

```text
ACCEPT|order|ORD-17|3|note=null
```

`internalNote` vẫn `null` vì không có input cho nó. Global và local validator đều không báo lỗi.

### 8.2. Trường hợp B — lỗi chỉ của local validator

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=2'
```

HTTP 400, body:

```text
INVALID|code:blockedCode
```

`BlockedCodeValidator` được gắn tại OrdersController nên từ chối mã `BLOCKED`.

Gửi **cùng dữ liệu** vào QuotesController:

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=2'
```

HTTP 200, body:

```text
ACCEPT|quote|BLOCKED|2|note=null
```

Điều này cho thấy validator local **không lan sang** controller khác, mặc dù tên model attribute của cả hai đều là `order`. Phạm vi controller và tên attribute phải được xét **đồng thời**.

### 8.3. Trường hợp C — lỗi global trên cả hai controller

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=6'
```

HTTP 400, body:

```text
INVALID|quantity:quantityLimit
```

Gửi tương tự vào `/orders` cũng có lỗi `quantityLimit`. Validator này nằm trong global advice áp dụng cho cả hai controller.

### 8.4. Trường hợp D — lỗi Jakarta Bean Validation mặc định

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=' \
  --data-urlencode 'quantity=0'
```

HTTP 400, body:

```text
INVALID|code:NotBlank,quantity:Min
```

`@NotBlank` và `@Min` chứng minh validator Jakarta vẫn được giữ vì code dùng `addValidators(...)` thay vì `setValidator(...)`.

### 8.5. Trường hợp E — cả global và local custom validators lỗi

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=6'
```

HTTP 400, body:

```text
INVALID|code:blockedCode,quantity:quantityLimit
```

Hai lỗi từ hai nguồn cùng xuất hiện trong `BindingResult`. Kết quả được sắp xếp theo `field:code` để không phụ thuộc thứ tự Spring/provider tạo lỗi.

### 8.6. Trường hợp F — chặn field không được cho phép bind

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=3' \
  --data-urlencode 'internalNote=FORGED'
```

HTTP 400, body:

```text
REJECTED_FIELDS
```

Global `setAllowedFields("code","quantity")` làm binder từ chối property `internalNote`. Helper thấy `getSuppressedFields()` không rỗng nên chủ động trả 400. Đây là ví dụ kiểm tra field-suppression: **setAllowedFields không đồng nghĩa framework tự ném một FieldError để controller trả 400.**

### 8.7. Trường hợp G — lỗi chuyển kiểu vẫn ở BindingResult

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=abc'
```

Giá trị `"abc"` không chuyển thành `Integer`; form binding thông thường ghi mã lỗi `typeMismatch` cho `quantity`. Controller trả HTTP 400 với body dự kiến:

```text
INVALID|quantity:typeMismatch
```

Đây là lỗi **binding/type conversion**, không phải do `@Min` phát hiện số nhỏ. Nếu ứng dụng đã tùy biến `BindingErrorProcessor` hoặc `MessageCodesResolver`, chi tiết mã có thể khác; khi test, cần bám vào config thực tế.

Các lệnh trên không in status code vì `curl -s` chỉ nhận body. Nếu muốn xem status/headers, dùng `curl -i` hoặc `curl -w '%{http_code}'`. Log Boot và lời nhắc terminal không thuộc response.

## 9. Những thay đổi nhỏ gây hậu quả lớn

### 9.1. Local setValidator thay cho addValidators

Giả sử thay `OrdersController.localRules` bằng:

```java
@InitBinder("order")
void localRules(WebDataBinder binder) {
    binder.setValidator(blockedCode);
}
```

Lúc này local setter có thể **thay danh sách validator đã được hạ tầng/global advice thiết lập**. Trong lượt binder validation, `@NotBlank`, `@Min` và `quantityLimit` có thể không còn chạy, dù annotations và global advice vẫn tồn tại.

Đây là **đoạn thay thế để phân tích**, không có trong source chính. Không thay thế danh sách validator vô tình; nếu muốn giữ tất cả, dùng `addValidators`.

### 9.2. Local setAllowedFields mở rộng danh sách

Giả sử local thêm:

```java
@InitBinder("order")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("code", "quantity", "internalNote");
}
```

Nếu advice trước đó giới hạn chỉ `code,quantity`, setter local có thể làm allowlist rộng hơn. Khi đó `internalNote` từ HTTP có thể được gán, làm vô hiệu ý định hạn chế global.

**Bài học bảo mật:** Không giả định mọi “global rule” là bất biến chỉ vì được áp dụng trước. Với binder options mang tính setter, code chạy sau phải được review và có test không cho binding field nhạy cảm.

### 9.3. Một advice cho nhiều kiểu form

Nếu dùng:

```java
@ControllerAdvice
class BroadAdvice {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.addValidators(new OrderOnlyValidator());
    }
}
```

thì method áp dụng cho nhiều binder hơn và có thể thất bại khi `OrderOnlyValidator.supports(targetClass)` không đúng với một DTO khác. Giải pháp là giới hạn bằng tên `@InitBinder("order")`, selector của `@ControllerAdvice`, hoặc chỉ thêm validator khi loại target phù hợp.

### 9.4. Thêm nhiều @InitBinder methods rồi phụ thuộc thứ tự ngẫu nhiên

Đừng viết hai `@InitBinder("order")` methods trong cùng một class, mỗi cái gọi `setAllowedFields(...)` khác nhau, rồi kỳ vọng tên method hoặc thứ tự source Java quyết định. Nếu cần trình tự rõ, gom logic phụ thuộc nhau vào một method hoặc tách thành hai advice có `@Order` cụ thể và có integration test.

## 10. Các khác biệt quan trọng với WebFlux, @RequestBody và method validation

### 10.1. Spring MVC khác Spring WebFlux

Bài này lấy **Spring MVC Servlet stack** làm ví dụ chính. Spring WebFlux có `WebFluxConfigurer` và binder cho controller reactive riêng, nhưng không nên copy cấu hình `WebMvcConfigurer` sang WebFlux rồi giả định cả hai áp dụng chung.

Thứ tự global advice và local binder có ý nghĩa tương tự ở annotated controllers WebFlux, nhưng các chi tiết reactive argument resolution, binding errors và cách dùng reactive wrappers có thể khác. Kiểm thử trên stack thực tế của ứng dụng.

### 10.2. @RequestBody JSON không đi qua property binding giống @ModelAttribute

`@Valid @RequestBody JsonRequest request` dùng HTTP message converter/Jackson để deserialize trước validation. Vì thế:

- `setAllowedFields(...)` của `WebDataBinder` **không phải** cơ chế mass-assignment defense cho mọi field JSON mà Jackson có thể deserialize.
- Lỗi JSON sai cú pháp có thể xảy ra trước validation, ví dụ `HttpMessageNotReadableException`.
- Muốn hạn chế field JSON cần thiết kế request DTO/Jackson visibility và boundary mapping rõ ràng.
- Các local binder settings phù hợp validation có thể được dùng ở ngữ cảnh tương ứng, nhưng đừng coi property binding của `@ModelAttribute` và JSON deserialization là cùng một pipeline.

### 10.3. @Valid và lỗi controller-level

`@Valid` hoặc `@Validated` có thể yêu cầu validator trên command object; `BindingResult` phải đứng ngay sau model attribute nếu muốn controller nhận lỗi tại chỗ.

Spring MVC từ Framework 6.1 còn có **built-in method validation** cho các constraint trực tiếp trên tham số/return value như `@Min(1)` ở `@RequestParam`. Lỗi method validation có thể phát `HandlerMethodValidationException`, không nhất thiết được xử lý bởi một `BindingResult` của form khác.

`@InitBinder` không thay thế các ngoại lệ binding converter, validation của method arguments hoặc constraint của service bean qua AOP.

## 11. Cách kiểm thử thứ tự và phạm vi chính xác

### Test theo hành vi thay vì log thứ tự

Để chứng minh global/local không lẫn phạm vi, test các hợp đồng quan sát được:

| Request | Bối cảnh | Kỳ vọng |
| --- | --- | --- |
| `POST /orders code=ORD-17 quantity=3` | Global + local | HTTP 200 |
| `POST /quotes code=ORD-17 quantity=3` | Chỉ global | HTTP 200 |
| `POST /orders code=BLOCKED quantity=2` | Local code rule | HTTP 400, `blockedCode` |
| `POST /quotes code=BLOCKED quantity=2` | Không có local code rule | HTTP 200 |
| `POST /orders code=ORD-17 quantity=6` | Global quantity rule | HTTP 400, `quantityLimit` |
| `POST /quotes code=ORD-17 quantity=6` | Global quantity rule | HTTP 400, `quantityLimit` |
| `POST /orders code= quantity=0` | Jakarta Bean Validation | HTTP 400, `NotBlank` và `Min` |
| `POST /quotes ... internalNote=FORGED` | Global allowlist | HTTP 400, `REJECTED_FIELDS` |
| `POST /orders quantity=abc` | Binding conversion | HTTP 400, `typeMismatch` |

Dùng `MockMvc` hoặc HTTP integration test để kiểm tra pipeline thật. Gọi trực tiếp `new OrdersController(...).create(form, result)` không kích hoạt `@InitBinder` hay framework binder.

### Kiểm chứng thứ tự advice khi thật sự quan trọng

Nếu có nhiều global advice với `@Order` khác nhau, kiểm thử thông qua hành vi cuối cùng của binder, không chỉ phụ thuộc log. Ví dụ một advice `setAllowedFields(...)` và advice khác cũng `setAllowedFields(...)` có thể cho thấy danh sách sau cùng được sử dụng; tuy nhiên đó là cấu hình khó bảo trì và nên tránh nếu không có nhu cầu rõ.

Nếu cần chẩn đoán, có thể log tạm trong `@InitBinder` rồi bỏ logging đi sau khi test, nhưng không để global singleton advice ghi request-specific data vào field dùng chung. Với quy tắc bảo mật, nên thêm regression test rằng những field nhạy cảm luôn bị từ chối.

## 12. Best practices: một chính sách rõ ràng, không phụ thuộc ghi đè ngầm

- **Giữ các defaults có ích:** Chỉ thay global validator/conversion service khi thật cần thiết; với rule riêng của form, thêm local validator.
- **Dùng scope hẹp nhất đủ đáp ứng:** Advice cho chính sách chung, controller-local cho nghiệp vụ riêng, `@InitBinder("name")` cho đúng object.
- **Đặt @Order khi có nhiều advice thực sự cần trật tự:** Không dựa vào thứ tự classpath scan hoặc tên class.
- **Không coi mọi cấu hình là merge:** Phân biệt setter với adder. Đặc biệt với `setAllowedFields` và `setValidator`.
- **Đặt DTO riêng cho request:** Không property-bind trực tiếp entity có field server-only.
- **Bảo vệ allowedFields trung tâm:** Một local setter không được vô ý mở khóa field mà global policy đã chặn. Test các request có field thừa.
- **Giữ validators độc lập, thread-safe:** Hạn chế state mutable vì chúng có thể được dùng trong nhiều request đồng thời.
- **Không làm blocking I/O trong converter/validator nếu có thể tránh:** Giữ conversion/validation nhanh và dễ dự đoán.
- **Không lộ giá trị bị từ chối:** `FieldError#getRejectedValue()` và field names nội bộ có thể chứa dữ liệu không nên trả ra public API.
- **Quyết định rõ HTTP status:** Có `BindingResult` tại chỗ thì chính controller chịu trách nhiệm trả view/response lỗi.
- **Phân biệt việc chọn controller và chọn attribute:** `@ControllerAdvice` selector + `@InitBinder("name")` là hai bộ lọc riêng.

## 13. Tổng kết

**Thứ tự cho cấu hình binder trong Spring MVC là cấu hình nền → global `@ControllerAdvice @InitBinder` → local `@Controller @InitBinder`** (trong luồng tạo binder áp dụng cho handler). Giữa các advice toàn cục, dùng `Ordered`/`@Order` để thiết lập ưu tiên rõ ràng. Phạm vi được điều khiển bởi vị trí method, selector của advice và tên attribute trong `@InitBinder`.

Điểm then chốt của việc kết hợp là **API có cộng dồn hay ghi đè**. `addValidators` giúp bổ sung rule mà giữ global Bean Validation; `setValidator` và `setAllowedFields` có thể thay cấu hình đã được đặt trước. Vì thế kiểm thử qua request thật và bảo vệ các field không được phép bind quan trọng không kém việc hiểu thứ tự thực thi.

## Tài liệu tham khảo

- Spring Framework 6.2 — *Controller Advice*, thứ tự global và local: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework 6.2 — `@InitBinder` và cấu hình binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — *Data Binding*, allowlist và declarative binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — *MVC Validation*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Javadoc — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 Javadoc — `@ControllerAdvice`, `@Order` và selectors: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html
- Spring Framework 6.2 Javadoc — `@InitBinder`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/annotation/InitBinder.html
- Spring Framework 6.2 Javadoc — `ConfigurableWebBindingInitializer`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/support/ConfigurableWebBindingInitializer.html