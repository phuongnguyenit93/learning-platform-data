# BindingResult đặt ngay sau tham số được gắn dữ liệu trong Spring MVC

## 1. Quy tắc bắt buộc trong chữ ký controller

Khi Spring MVC ánh xạ dữ liệu HTTP vào một đối tượng (data binding), ví dụ qua `@ModelAttribute`, framework ghi lại lỗi chuyển kiểu và có thể thực hiện validation bằng `@Valid` hoặc `@Validated`. Nếu muốn **tự xử lý lỗi ngay trong controller**, hãy đặt tham số `BindingResult` hoặc `Errors` **liền ngay sau đối tượng vừa được gắn dữ liệu**, không chen tham số khác vào giữa:

```java
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "orderForm";
    }
    // Chỉ xử lý nghiệp vụ nếu dữ liệu đã hợp lệ.
    return "redirect:/orders/success";
}
```

Đây là đoạn minh họa, chưa phải ứng dụng Java độc lập. Cặp tham số cần nhớ:

```text
@Valid @ModelAttribute("order") OrderForm form
                         ↓ đặt NGAY SAU
                    BindingResult result
                         ↓
                    Model, Locale, các tham số khác
```

**Sai vị trí:**

```java
// Sai quy tắc do Model nằm giữa form và BindingResult.
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        Model model,
        BindingResult result) {
    // ...
}
```

Java compiler vẫn có thể biên dịch chữ ký này, nhưng Spring MVC không coi `result` là tham số xử lý lỗi đặt đúng cặp với `form`. Khi gặp binding/validation error, quá trình phân giải tham số có thể ném exception thay vì gọi handler với lỗi như dự định. **Không đủ nếu chỉ khai báo một `BindingResult` ở đâu đó trong phương thức.**

Đây là quy tắc của Spring MVC handler argument resolution, **không** phải quy tắc cú pháp Java và cũng không phải điều kiện do Jakarta Bean Validation tự đặt ra.

## 2. BindingResult là gì và lưu những lỗi nào?

`org.springframework.validation.BindingResult` kế thừa `org.springframework.validation.Errors`. Nó giữ kết quả của việc bind một object cụ thể, bao gồm lỗi:

- **Binding/type-conversion:** HTTP request gửi chuỗi `"abc"` trong khi trường Java có kiểu `Integer`; lỗi thường có mã `typeMismatch`.
- **Validation:** request bind được vào object, nhưng field vi phạm `@NotBlank`, `@Min`, `@Size` hoặc constraint khác.
- **Object-level:** rule liên quan nhiều thuộc tính cùng lúc hoặc rule do validator thêm qua `reject(...)`.
- **Lỗi thêm thủ công:** controller/service adapter có thể ghi thêm bằng `rejectValue(...)` hoặc `reject(...)` khi hợp đồng của ứng dụng yêu cầu.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `hasErrors()` | Có ít nhất một lỗi không |
| `getErrorCount()` | Số lượng lỗi |
| `getFieldErrors()` | Toàn bộ lỗi theo field (`FieldError`) |
| `getFieldError("quantity")` | Một lỗi của field `quantity` nếu có |
| `getGlobalErrors()` | Lỗi mức object (`ObjectError`) |
| `getAllErrors()` | Kết hợp lỗi field và global |
| `getObjectName()` | Tên model attribute, ví dụ `order` |
| `getFieldValue("quantity")` | Giá trị field dưới góc nhìn binding, hữu ích khi hiển thị lại form |
| `rejectValue(field, code, ...)` | Thêm lỗi cho field |
| `reject(code, ...)` | Thêm lỗi cho object |
| `getSuppressedFields()` | Danh sách field bị chặn binding bởi giới hạn allowed/disallowed field |

`FieldError` chứa field name, tập error codes, default message và thông tin về giá trị bị từ chối. Không đưa nguyên `getRejectedValue()` vào log hay response nếu đó có thể là mật khẩu, token hoặc thông tin riêng tư.

`BindingResult` không phải một đối tượng “tổng hợp lỗi của cả request”. Nó gắn với **một** command object ở vị trí ngay trước nó.

## 3. Vì sao bắt buộc đứng liền kề?

Một handler có thể nhận nhiều object cần bind. Spring MVC tạo thông tin binding và validation cho mỗi object theo thứ tự phân giải tham số handler. Việc khai báo một `BindingResult` ngay sau object cho framework biết bạn muốn lấy kết quả của chính object đó vào handler, thay vì để framework phát lỗi theo luồng mặc định.

Ví dụ hai cặp đúng:

```java
@PostMapping("/checkout")
public String checkout(
        @Valid @ModelAttribute("buyer") BuyerForm buyer,
        BindingResult buyerErrors,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult shippingErrors,
        Model model) {

    if (buyerErrors.hasErrors() || shippingErrors.hasErrors()) {
        return "checkoutForm";
    }
    return "redirect:/checkout/complete";
}
```

Đây là mã tích hợp minh họa; giả sử `BuyerForm`, `ShippingForm` và view đã tồn tại.

Chữ ký sau **không đúng**:

```java
// Hai model attribute rồi mới đến hai BindingResult: sai cặp.
@PostMapping("/checkout")
public String checkout(
        @Valid @ModelAttribute("buyer") BuyerForm buyer,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult buyerErrors,
        BindingResult shippingErrors) {
    // ...
}
```

Spring không ghép kết quả theo tên biến `buyerErrors` hay `shippingErrors`. **Vị trí kề nhau mới là hợp đồng.** Khi thêm `Model`, `Locale`, `HttpServletRequest` hoặc `Principal`, đừng chèn chúng vào giữa object và `BindingResult` của cùng cặp.

Một cách nghĩ dễ nhớ: **mỗi command object có một “khe lỗi” ngay bên phải của nó**.

## 4. Quá trình xử lý: binding trước, validation sau

Với `@ModelAttribute`, một luồng xử lý thông thường là:

1. Framework tìm hoặc khởi tạo command object; ví dụ `OrderForm` có tên `order`.
2. `WebDataBinder` nhận request parameters, chuyển kiểu bằng converter/formatter/property editor rồi gán thuộc tính tương ứng.
3. Nếu chuyển kiểu thất bại, binder ghi nhận lỗi như `typeMismatch` thay vì bắt buộc làm handler ném một `NumberFormatException`.
4. Khi có `@Valid` hoặc `@Validated` và provider/validator thích hợp, framework tiếp tục chạy validation trên object đã bind.
5. Kết quả được ghi trong `BindingResult` tương ứng.
6. Nếu có `BindingResult` đứng ngay sau object, controller được phép đọc và xử lý lỗi. Nếu không có, framework áp dụng luồng exception phù hợp với loại tham số/validation.

Giả sử DTO:

```java
public class OrderForm {

    @NotBlank
    private String itemCode;

    @Min(1)
    private Integer quantity;

    // getters/setters
}
```

Nếu request có `itemCode=` và `quantity=abc` thì:

- Chuỗi trống gán được cho `itemCode` nhưng vi phạm `@NotBlank`.
- Chuỗi `"abc"` không chuyển được sang `Integer` cho `quantity`; binder ghi `typeMismatch`.
- Cả hai lỗi có thể cùng nằm trong `BindingResult` của `OrderForm`.

Nếu request có `quantity=0`, việc chuyển kiểu thành công nhưng `@Min(1)` thất bại. Nếu `quantity` là `null`, `@Min` cho phép `null` theo hợp đồng Bean Validation; muốn bắt buộc có giá trị, thêm `@NotNull`.

**Binding error không đồng nghĩa validation error.** `BindingResult` giúp nhìn thấy cả hai, nhưng chúng có nguồn gốc khác nhau và cần thông báo phù hợp.

## 5. Ví dụ Java 17, Spring Boot 3.5.6, Maven và HTTP form

Ví dụ hoàn chỉnh này tạo endpoint `POST /orders` với `@Valid @ModelAttribute` và `BindingResult` liền sau. Nó trả mã HTTP phù hợp và body chứa các error codes được sắp xếp để kiểm tra dễ dàng. Không cần cơ sở dữ liệu hoặc template engine.

### 5.1. Cấu trúc file

```text
binding-result-demo/
├── pom.xml
└── src/main/java/demo/
    ├── BindingResultApplication.java
    └── OrderController.java
```

### 5.2. pom.xml

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
  <artifactId>binding-result-demo</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC/embedded server; `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider.

### 5.3. BindingResultApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingResultApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingResultApplication.class, args);
    }
}
```

### 5.4. OrderController.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class OrderController {

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + simpleCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest().body("INVALID|" + details);
        }

        return ResponseEntity.ok(
            "ACCEPT|" + form.getItemCode() + "|" + form.getQuantity());
    }

    // FieldError.getCodes() có thể gồm mã cụ thể theo object và field.
    // Lấy mã tổng quát cuối để output dễ so sánh.
    private static String simpleCode(FieldError error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
            ? "unknown"
            : codes[codes.length - 1];
    }

    public static class OrderForm {

        @NotBlank
        private String itemCode;

        @Min(1)
        private Integer quantity;

        public OrderForm() {
        }

        public String getItemCode() {
            return itemCode;
        }

        public void setItemCode(String itemCode) {
            this.itemCode = itemCode;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }
}
```

Để dễ quan sát, controller chủ động chuyển lỗi thành `"INVALID|..."` và trả `400 Bad Request`. **Đây là quyết định của controller**, không phải do `BindingResult` tự chọn HTTP status.

`OrderForm` là DTO dành cho web binding, có public no-arg constructor và JavaBean getters/setters. Khi dữ liệu hợp lệ, controller mới dùng các field và trả kết quả. Đoạn mã lấy mã cuối trong `FieldError#getCodes()` thay vì dùng trực tiếp `getCode()`, vì mã đầu thường có tiền tố object và field do `MessageCodesResolver` tạo ra.

### 5.5. Chạy và kiểm tra output

Trong thư mục `binding-result-demo`, với Java 17+ và Maven 3.x:

```bash
mvn -q spring-boot:run
```

Mặc định server lắng nghe `localhost:8080` nếu cổng chưa được sử dụng. Từ một terminal bash/zsh/WSL khác, gửi request:

**Dữ liệu hợp lệ:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=PEN-1' \
  --data-urlencode 'quantity=2'
```

HTTP `200 OK`, body:

```text
ACCEPT|PEN-1|2
```

**Số lượng vi phạm constraint:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=PEN-1' \
  --data-urlencode 'quantity=0'
```

HTTP `400 Bad Request`, body:

```text
INVALID|quantity:Min
```

**Một lỗi validation và một lỗi binding:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=' \
  --data-urlencode 'quantity=abc'
```

HTTP `400 Bad Request`, body:

```text
INVALID|itemCode:NotBlank,quantity:typeMismatch
```

Hai loại lỗi được chứa trong cùng `BindingResult` cho `order`. Dòng in không phụ thuộc thứ tự validator phát hiện lỗi vì controller dùng `sorted()`. `curl -s` chỉ in body, không tự thêm newline; các khối trên trình bày body riêng để dễ đọc. Log khởi động server/Maven không thuộc response.

Nếu **bỏ `BindingResult` khỏi chữ ký** trong trường hợp `@Valid @ModelAttribute`, Spring MVC thường ném `MethodArgumentNotValidException` khi có lỗi, thay vì để controller xử lý tại chỗ. Nếu muốn phản hồi tùy chỉnh trong chế độ đó, dùng `@ExceptionHandler` hoặc `@ControllerAdvice` phù hợp.

## 6. Vị trí BindingResult với @RequestBody và @RequestPart

Quy tắc “đặt ngay sau đối tượng” không chỉ xuất hiện với form binding.

### @Valid @RequestBody

`@RequestBody` dùng `HttpMessageConverter` để đọc JSON/XML thành object. Với một DTO đã deserialize thành công nhưng vi phạm constraint, có thể xử lý validation ngay trong handler:

```java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody AccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid account");
    }
    return ResponseEntity.ok().build();
}
```

Đây là **đoạn mã minh họa tích hợp**: cần DTO `AccountRequest`, imports và cấu hình Spring MVC/Jackson. Lỗi JSON **sai cú pháp**, body không đọc được hoặc không thể deserialize có thể tạo `HttpMessageNotReadableException` **trước khi** framework có DTO để validate. Một `BindingResult` liền kề không có nhiệm vụ bắt lỗi parser đó.

### @Valid @RequestPart

Với metadata của multipart request:

```java
@PostMapping("/attachments")
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") MetadataRequest metadata,
        BindingResult metadataErrors,
        @RequestPart("file") MultipartFile file) {

    if (metadataErrors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid metadata");
    }
    // ... xử lý file hợp lệ
    return ResponseEntity.ok().build();
}
```

Đây cũng là **đoạn minh họa**, không phải ví dụ chạy độc lập. `BindingResult` đứng ngay sau metadata, **trước** `file`. Thiếu part, file quá giới hạn kích thước hoặc đọc multipart thất bại có nhánh exception riêng, không biến thành `FieldError` của metadata.

### Bảng phân biệt

| Tham số handler | Dùng cặp liền kề `BindingResult`? | Lỗi tiêu biểu |
| --- | --- | --- |
| `@Valid @ModelAttribute Form form` | Có | Conversion + validation |
| `@Validated @ModelAttribute Form form` | Có | Binding + validation theo group |
| `@Valid @RequestBody Dto dto` | Có, cho lỗi validation sau deserialize | Constraint trên DTO |
| `@Valid @RequestPart Dto dto` | Có, cho validation của part được đọc | Constraint trên metadata |
| `@RequestParam Integer page` | Không theo quy tắc command-object này | Missing parameter, type conversion |
| `@PathVariable Long id` | Không | Type conversion của path variable |
| `@RequestHeader String token` | Không | Missing/invalid header theo argument resolver |

Đừng thêm `BindingResult` sau `@RequestParam` và kỳ vọng nó hoạt động như sau `@ModelAttribute`. Mỗi loại tham số có `HandlerMethodArgumentResolver` và chính sách lỗi riêng.

## 7. Method validation của Spring MVC 6.1+: giới hạn quan trọng

Từ Spring Framework 6.1, Spring MVC có **built-in method validation** cho controller với các constraint trực tiếp trên method parameters hoặc return value, ví dụ `@Min` hoặc `@NotBlank`. Khi method validation được kích hoạt, `HandlerMethodValidationException` có thể xuất hiện thay cho `MethodArgumentNotValidException`.

Ví dụ:

```java
@GetMapping("/orders")
public String list(
        @Valid @ModelAttribute("filter") FilterForm filter,
        BindingResult filterErrors,
        @RequestParam @Min(1) int page) {
    // ...
    return "orders";
}
```

Đây là ví dụ minh họa cần `FilterForm` và imports. Cặp `filter, filterErrors` đúng vị trí và có thể dùng xử lý lỗi của filter. Nhưng `@Min(1)` trên `page` là **method-level constraint** trên một tham số khác. Nếu `page` không hợp lệ, Spring MVC có thể ném `HandlerMethodValidationException` và không gọi handler, dù `filterErrors` có mặt.

Theo hợp đồng của MVC, khi method validation áp dụng và có `Errors`/`BindingResult`, handler **chỉ được gọi nếu tất cả các lỗi validation đều thuộc những tham số có `Errors` liền ngay sau**. Chỉ một lỗi trên tham số không có chỗ nhận cục bộ là đủ để exception xuất hiện.

Phân biệt:

- **Object validation thông thường:** `@Valid @ModelAttribute`, `@Valid @RequestBody` hoặc `@Valid @RequestPart` trên command object; khi không có `BindingResult` kề bên và lỗi xảy ra, thường nhận `MethodArgumentNotValidException`.
- **Method validation trực tiếp:** constraint trên method parameter/return value; lỗi không xử lý hoàn toàn tại handler thì dùng `HandlerMethodValidationException`.
- `@Valid` tự nó **không phải constraint trực tiếp**. Nó chỉ đánh dấu cascade vào object. Thêm `@NotNull` trên một tham số `@Valid` có thể khiến method validation được yêu cầu.

Spring MVC 6.1+ khuyến nghị **bỏ `@Validated` ở cấp class của controller** nếu muốn dùng cơ chế method validation built-in. `@Validated` cấp class có thể kích hoạt đường Spring AOP method validation, với kiểu exception và điểm chặn khác. `BindingResult` trên một form không tự bắt mọi lỗi từ AOP service/controller.

## 8. BindingResult trong form HTML và view model

Khi đưa dữ liệu trở lại view để người dùng sửa lỗi, model có thể chứa object và kết quả binding/validation dưới key theo quy ước:

```text
org.springframework.validation.BindingResult.<attributeName>
```

Ví dụ, với `@ModelAttribute("order")`:

```text
org.springframework.validation.BindingResult.order
```

Tiền tố được Spring cung cấp qua `BindingResult.MODEL_KEY_PREFIX`. Template engine như Thymeleaf có thể dùng `th:field` và `th:errors` để hiển thị lại giá trị và lỗi theo tên field:

```html
<!-- Fragment Thymeleaf trong form đã gắn đối tượng order -->
<input type="text" th:field="*{itemCode}">
<div th:errors="*{itemCode}">Thông báo lỗi</div>
```

Đây là **fragment template**, không phải một file HTML độc lập. BindingResult cũng lưu thông tin giúp hiển thị lại giá trị người dùng đã nhập trong trường hợp converter không tạo được giá trị Java hợp lệ.

Nếu là REST API, nên ánh xạ `FieldError` thành cấu trúc lỗi public ổn định, chẳng hạn `field`, `code`, `message`, thay vì serialize trực tiếp toàn bộ `BindingResult`; thông báo và dữ liệu đầu vào có thể nhạy cảm.

## 9. Tùy chỉnh và bảo mật binding

Controller có thể thêm lỗi domain vào đúng `BindingResult`:

```java
// Bên trong handler, sau khi binding hoàn tất và đã kiểm tra lỗi cơ bản:
if (form.getItemCode() != null &&
        form.getItemCode().startsWith("FORBIDDEN-")) {
    errors.rejectValue(
        "itemCode", "invalidItemCode", "Mã hàng không được phép");
}

if (errors.hasErrors()) {
    return "orderForm";
}
```

Đây là đoạn minh họa. Không nên thực hiện truy vấn hoặc xử lý nghiệp vụ có side effect nếu `errors.hasErrors()` đã là `true` do dữ liệu bind thất bại.

Khi thiết kế đối tượng nhận từ web:

- Ưu tiên DTO dành cho request, thay vì bind trực tiếp vào entity có field quản trị hoặc thông tin nhạy cảm.
- Khi dùng property binding, cân nhắc `WebDataBinder#setAllowedFields(...)` để hạn chế thuộc tính client được phép ghi.
- Có thể kiểm tra `getSuppressedFields()` để thấy các field binder từ chối; chúng **không tự động là `FieldError`** nếu ứng dụng không quy định.
- Không bỏ qua authentication/authorization, kiểm tra quyền sở hữu resource hoặc các ràng buộc nghiệp vụ quan trọng vì đã có `BindingResult`.
- Đừng lộ `FieldError#getRejectedValue()` hay raw `getArgument()` của các cơ chế khác cho client không đáng tin.

## 10. Lỗi hay gặp và cách sửa

| Lỗi hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Có `BindingResult` nhưng vẫn ném exception trước handler | `Model` hoặc tham số khác chen giữa object và result | Đặt `BindingResult` ngay sau bound argument |
| Hai form nhưng lỗi bị liên kết không đúng | Không khai báo mỗi cặp liền kề | `form1, errors1, form2, errors2` |
| Request lỗi nhưng endpoint vẫn trả HTTP 200 | Handler nhận lỗi nhưng không kiểm tra `hasErrors()` | Chọn view/status phản ánh lỗi |
| Không bắt được JSON sai cú pháp bằng `BindingResult` | Lỗi xảy ra tại converter trước validation | Xử lý `HttpMessageNotReadableException` riêng |
| `@Min` không từ chối `null` | `@Min` cho phép `null` | Thêm `@NotNull` khi cần |
| `hasErrors()` không có constraint dự kiến | Thiếu `@Valid`, provider, validator hoặc group đúng | Kiểm tra cấu hình và constraint metadata |
| `@RequestParam @Min` gây lỗi dù có result của form | MVC method validation có lỗi ở tham số khác | Xử lý `HandlerMethodValidationException` |
| Lỗi chuyển kiểu khiến service nhận dữ liệu sai | Không kiểm tra result trước khi dispatch | Dừng ngay khi `hasErrors()` |
| Thông báo lỗi thiếu ngữ cảnh hoặc khó dịch | Parse chuỗi exception/getMessage hoặc hardcode | Dùng `FieldError`, message codes và `MessageSource` |
| Form bind quá nhiều field | DTO quá rộng hoặc binder cho phép mass assignment | DTO riêng, allowedFields và phân quyền server-side |

## 11. Checklist kiểm thử

1. Request hợp lệ vào controller và `result.hasErrors() == false`.
2. Field string rỗng với `@NotBlank` tạo lỗi validation.
3. Field số nhận `"abc"` tạo lỗi binding/type mismatch, không làm handler xử lý dữ liệu như số hợp lệ.
4. Với nhiều object, từng `BindingResult` gắn đúng tên object.
5. Đặt `Model` chen giữa object và result phải được coi là chữ ký cần sửa, không phải cách hỗ trợ chính thức.
6. `@Valid @RequestBody` nhận JSON parse được nhưng sai constraint: có thể xử lý cục bộ qua result.
7. JSON hỏng: controller chưa thể nhận DTO; lỗi converter đi qua handler thích hợp.
8. Có constraint trực tiếp trên tham số MVC khác: kiểm thử nhánh `HandlerMethodValidationException`.
9. Khi lỗi, không gọi business service và không trả thành công ngoài ý muốn.
10. Không đưa rejected values hoặc thông tin nội bộ vào public response.

## 12. Tóm tắt

**`BindingResult` phải được khai báo ngay sau đối tượng được bind và validate, theo từng cặp.** Nó thu thập các lỗi gắn với command object đó để controller xử lý cục bộ, từ lỗi chuyển kiểu tới lỗi Bean Validation. Không chèn `Model`, `Locale`, request object hay command object thứ hai giữa hai thành viên của một cặp.

Cần phân biệt điều này với lỗi đọc JSON/multipart, lỗi `@RequestParam` riêng lẻ và built-in method validation từ Spring MVC 6.1. Việc đặt đúng vị trí giúp nhận lỗi, còn việc **chọn thông báo, HTTP status, view và có tiếp tục nghiệp vụ hay không** là trách nhiệm thiết kế handler.

## Tài liệu tham khảo

- Spring Framework 6.2 — *Method Arguments*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework 6.2 — `@ModelAttribute` và cặp `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@RequestBody` và local validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — *Validation*, `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring 6.2 Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/BindingResult.html
- Spring 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/FieldError.html