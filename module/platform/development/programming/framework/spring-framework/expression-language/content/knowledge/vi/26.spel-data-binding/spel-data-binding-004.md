# DataBinder và vai trò của SpEL trong quá trình bind

## Mục tiêu

`DataBinder` của Spring nhận các giá trị đầu vào dạng property values và bind chúng vào các property của một object Java. Nó thường được dùng trong Spring MVC để bind request parameters vào form object, hoặc được dùng trực tiếp trong ứng dụng để chuyển dữ liệu thành object có kiểu.

SpEL và `DataBinder` có liên quan ở tầng property access và data binding, nhưng chúng thực hiện hai nhiệm vụ khác nhau. `DataBinder` điều phối việc ghi giá trị vào target, chuyển đổi kiểu và thu thập lỗi. SpEL là ngôn ngữ biểu thức có thể đọc, tính toán hoặc cập nhật property khi ứng dụng chủ động đánh giá expression. `DataBinder` không tự động parse mọi chuỗi đầu vào như một SpEL expression.

Hiểu ranh giới này giúp tránh nhầm property path như `address.city` với expression như `T(java.lang.Math).max(1, 2)`, đồng thời giúp thiết kế quy trình bind an toàn và dễ kiểm soát.

## 1. DataBinder làm nhiệm vụ gì?

`org.springframework.validation.DataBinder` bind các giá trị vào một target object. Trong một quy trình thông thường, ứng dụng cung cấp target và các property values; binder sử dụng cơ chế property access cùng type conversion để cập nhật target, sau đó lưu lỗi bind vào `BindingResult`.

Quy trình khái quát:

1. Tạo target object, thường là một form object hoặc DTO.
2. Chuẩn bị các giá trị đầu vào dưới dạng `PropertyValues`.
3. Cấu hình binder: conversion service, allowed fields, validator và các tùy chọn bind.
4. Gọi `bind(...)` để chuyển giá trị vào target.
5. Đọc `BindingResult` để xử lý lỗi chuyển đổi hoặc lỗi bind.
6. Chạy validator để kiểm tra quy tắc nghiệp vụ và xử lý các validation errors.

Trong Spring MVC, framework thường tạo và cấu hình `WebDataBinder` cho từng model attribute. Controller có thể tùy chỉnh binder bằng `@InitBinder`.

## 2. Ví dụ DataBinder cơ bản

Giả sử ứng dụng có form object:

```java
public class CustomerForm {
    private String name;
    private Integer age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
}
```

Bind các giá trị vào object:

```java
CustomerForm form = new CustomerForm();
DataBinder binder = new DataBinder(form, "customerForm");
binder.setConversionService(new DefaultConversionService());

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Lan");
values.add("age", "28");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Xử lý lỗi bind.
}
```

Giá trị `"28"` được chuyển sang `Integer` khi conversion service hỗ trợ chuyển đổi tương ứng. Sau khi bind thành công, `form.getAge()` trả về số nguyên `28`.

`DataBinder` không cần một SpEL expression để thực hiện việc chuyển chuỗi sang số. Đây là type conversion trong quá trình binding.

## 3. Property path trong binding

DataBinder sử dụng property access để xác định nơi ghi giá trị trên target. Property path có thể đi qua property lồng nhau hoặc truy cập phần tử trong collection/map:

```text
name
address.city
items[0].productName
attributes[theme]
```

Ví dụ, `address.city` có nghĩa là property `city` của object `address`; `items[0].productName` chỉ đến `productName` của phần tử đầu tiên trong `items`.

Đây là đường dẫn property dành cho binding. Chúng không phải cú pháp đầy đủ của SpEL. Các cấu trúc như `#variable`, `T(java.lang.Math)`, `new ...`, `.?[...]`, `.![...]` hoặc `#{...}` không tự động được đánh giá chỉ vì chúng xuất hiện trong tên field hay giá trị request.

Ví dụ, nếu request gửi giá trị chuỗi `T(java.lang.Math).max(1, 2)` cho một property kiểu `String`, binder xử lý nó như dữ liệu chuỗi. Ứng dụng chỉ thực thi SpEL nếu code chủ động đưa chuỗi đó vào `ExpressionParser` và gọi `getValue`.

## 4. DataBinder và SpEL: hai cơ chế khác nhau

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Bind request parameter `age=28` vào property `Integer age` | `DataBinder` và `ConversionService`. |
| Bind `address.city` vào property lồng nhau | Property path của binder/BeanWrapper. |
| Kiểm tra `price * quantity` bằng expression | SpEL được ứng dụng parse và evaluate rõ ràng. |
| Đọc `customer.name` trong một expression | SpEL property access trên evaluation context. |
| Cập nhật property bằng `expression.setValue(...)` | SpEL write access, nếu accessor cho phép. |
| Chuyển chuỗi số thành `Integer` khi bind | Type conversion của Spring. |

SpEL có thể dùng trong các phần khác của ứng dụng Spring, ví dụ `@Value`, rule evaluation hoặc expression-based configuration. Điều đó không có nghĩa `DataBinder` tự chạy SpEL trên mọi giá trị bind.

## 5. ConversionService trong quá trình bind

Binding thường nhận dữ liệu ở dạng chuỗi từ form hoặc request, trong khi target property có thể là `Integer`, `Long`, `BigDecimal`, `LocalDate`, enum hoặc kiểu domain khác. `ConversionService` chịu trách nhiệm chuyển đổi các giá trị đó khi có converter phù hợp.

Ví dụ:

```java
DefaultConversionService conversionService = new DefaultConversionService();
DataBinder binder = new DataBinder(form);
binder.setConversionService(conversionService);
```

Spring cũng hỗ trợ đăng ký converter/formatter tùy chỉnh để chuyển đổi kiểu riêng của ứng dụng. Nên đặt quy tắc conversion ở conversion layer thay vì viết SpEL expression cho mọi phép chuyển đổi dữ liệu đầu vào.

Khi conversion thất bại, binder ghi nhận lỗi trong `BindingResult`. Ví dụ chuỗi `"twenty"` không thể chuyển thành `Integer` theo converter thông thường sẽ tạo lỗi bind cho field `age`.

## 6. BindingResult và lỗi bind

`BindingResult` chứa thông tin về lỗi xảy ra trong quá trình bind và validation. Có thể kiểm tra lỗi tổng quát hoặc lỗi của một field:

```java
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    for (FieldError error : result.getFieldErrors()) {
        String field = error.getField();
        String code = error.getCode();
        // Chọn cách phản hồi phù hợp cho field và error code.
    }
}
```

Lỗi có thể đến từ nhiều nguyên nhân:

- Không chuyển được giá trị đầu vào sang kiểu property.
- Property path không hợp lệ hoặc không thể truy cập.
- Nested object hoặc collection không ở trạng thái phù hợp cho thao tác bind.
- Validator phát hiện dữ liệu không thỏa quy tắc.

Không nên đưa toàn bộ `rejectedValue` vào log hoặc phản hồi công khai nếu field có thể chứa mật khẩu, token hoặc dữ liệu cá nhân. Dùng field name và error code để tạo thông báo phù hợp.

## 7. Chạy Validator sau khi bind

Conversion chỉ đảm bảo giá trị có thể được chuyển sang kiểu đích; nó không đảm bảo dữ liệu hợp lệ về nghiệp vụ. Ví dụ, tuổi `-5` có thể chuyển thành `Integer` thành công nhưng vẫn không hợp lệ.

Có thể đăng ký Spring `Validator` rồi gọi `validate()` sau `bind(...)`:

```java
DataBinder binder = new DataBinder(form, "customerForm");
binder.setValidator(new CustomerFormValidator());

binder.bind(values);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Xử lý cả bind errors và validation errors.
}
```

Validator kiểm tra các quy tắc như trường bắt buộc, miền giá trị, quan hệ giữa nhiều field hoặc quy tắc nghiệp vụ. Trong ứng dụng dùng Bean Validation, có thể tích hợp validator tương thích với Spring validation API.

SpEL có thể tính một điều kiện hoặc giá trị dẫn xuất, nhưng không thay thế cơ chế `Validator` cho các quy tắc kiểm tra dữ liệu có cấu trúc.

## 8. Giới hạn field được phép bind

Không nên bind mọi field mà client gửi vào một domain object rộng. Đây là rủi ro mass assignment: client có thể gửi thêm property nhạy cảm như `role`, `admin`, `accountStatus` hoặc `ownerId` nếu binder cho phép ghi chúng.

DataBinder cung cấp allowlist và denylist:

```java
DataBinder binder = new DataBinder(form, "customerForm");
binder.setAllowedFields("name", "age", "address.city");
```

Hoặc chặn một số field cụ thể:

```java
binder.setDisallowedFields("role", "admin", "accountStatus");
```

Với dữ liệu từ client, allowlist thường dễ kiểm soát hơn vì chỉ những field được khai báo mới được bind. Các field bị loại khỏi binding có thể được xem qua `BindingResult.getSuppressedFields()`.

```java
String[] suppressed = binder.getBindingResult().getSuppressedFields();
```

Ưu tiên bind vào form DTO chỉ chứa các field client được phép thay đổi, sau đó service layer mới áp dụng thay đổi hợp lệ lên entity. Không dùng một entity quản lý quyền hoặc trạng thái nhạy cảm làm target trực tiếp cho dữ liệu request.

## 9. Nested paths và collection growth

Property path có thể trỏ vào object lồng nhau hoặc phần tử collection:

```text
shippingAddress.city
items[0].quantity
items[1].productCode
```

DataBinder có các tùy chọn liên quan đến nested path và collection growth, chẳng hạn `setAutoGrowNestedPaths(...)` và `setAutoGrowCollectionLimit(...)`. Chúng ảnh hưởng việc binder có thể tạo nested object hoặc mở rộng collection khi cần bind đến path hay không.

Chỉ bật hoặc đặt giới hạn phù hợp với cấu trúc target. Nếu cho phép client yêu cầu index collection rất lớn, binder có thể phải tạo nhiều phần tử và tiêu tốn bộ nhớ. Hãy đặt collection limit hợp lý, xác thực index và chỉ expose những nested paths cần thiết.

Auto-grow là hành vi property binding; nó không phải cơ chế SpEL và không làm cho các expression động trong request được thực thi.

## 10. Tùy chỉnh WebDataBinder trong Spring MVC

Trong Spring MVC, `WebDataBinder` mở rộng `DataBinder` cho web binding. Có thể dùng `@InitBinder` để cấu hình binder cho một model attribute:

```java
@Controller
public class CustomerController {

    @InitBinder("customerForm")
    void initCustomerFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age");
    }

    @PostMapping("/customers")
    String save(
            @ModelAttribute("customerForm") CustomerForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "customer-form";
        }

        // Gọi service để xử lý dữ liệu đã bind và hợp lệ.
        return "redirect:/customers";
    }
}
```

`BindingResult` được đặt ngay sau tham số `@ModelAttribute` tương ứng để controller nhận lỗi bind/validation cho object đó. `@InitBinder` là nơi thích hợp để cấu hình allowed fields, editor, formatter, conversion hoặc validator cho web binding.

Không dùng `@InitBinder` để đánh giá các chuỗi request như SpEL. Nếu ứng dụng có nhu cầu evaluate expression, hãy thực hiện rõ ràng ở một service hoặc component riêng với evaluation context được giới hạn.

## 11. Khi nào SpEL có thể tham gia một quy trình binding?

SpEL có thể được dùng bên cạnh DataBinder khi ứng dụng cần tính một giá trị dẫn xuất hoặc đánh giá một rule trên object sau khi dữ liệu đã được bind. Hai bước nên được tách rõ:

1. Dùng `DataBinder` để chuyển input thành target object có kiểu và thu thập bind errors.
2. Nếu cần, dùng SpEL để đọc/tính toán trên target đã bind bằng một `EvaluationContext` phù hợp.

Ví dụ tính tổng từ các property đã bind:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Expression totalExpression = parser.parseExpression("unitPrice * quantity");
BigDecimal total = totalExpression.getValue(context, orderForm, BigDecimal.class);
```

Ở đây SpEL đọc `unitPrice` và `quantity` từ `orderForm` rồi tính `total`. Việc bind `unitPrice` và `quantity` vẫn do DataBinder thực hiện trước đó. Nếu cần lưu kết quả, code ứng dụng có thể gọi setter hoặc service theo một bước riêng sau khi đã kiểm tra lỗi.

Với expression đến từ nguồn không tin cậy, không parse và evaluate chúng chỉ vì chúng được gửi cùng request. Dùng expression cố định do ứng dụng quản lý, context giới hạn và object view chỉ expose các property cần thiết.

## 12. Không nhầm DataBinder với SpEL trong @Value

Spring hỗ trợ SpEL trong annotation `@Value`, ví dụ:

```java
@Value("#{2 * T(java.lang.Math).PI}")
private double circumferenceFactor;
```

Ở đây Spring expression infrastructure đánh giá SpEL để tạo giá trị inject vào field. Đây là cơ chế expression evaluation của Spring, không phải quá trình bind request properties do `DataBinder` điều phối.

Tương tự, một chuỗi có dạng `#{...}` trong dữ liệu người dùng không tự động trở thành expression. Chỉ những thành phần được cấu hình để parse/evaluate SpEL mới thực thi cú pháp đó.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Chuỗi số không bind được vào property số | ConversionService thiếu converter phù hợp hoặc dữ liệu sai định dạng. | Đăng ký converter/formatter cần thiết và kiểm tra lỗi trong BindingResult. |
| Client thay đổi được field nhạy cảm | Binder cho phép bind quá nhiều property. | Dùng form DTO và `setAllowedFields(...)`; kiểm tra suppressed fields. |
| `address.city` không bind được | Nested object/path không thể truy cập hoặc không thể tự tạo. | Kiểm tra target structure, setter/constructor và cấu hình nested path phù hợp. |
| Index collection quá lớn gây tốn bộ nhớ | Auto-grow collection không có giới hạn phù hợp. | Đặt `setAutoGrowCollectionLimit(...)` và xác thực input/index. |
| Binder không thực thi chuỗi `T(...)` hoặc `#{...}` | DataBinder đang xử lý property values, không evaluate SpEL. | Nếu thực sự cần expression, gọi parser/evaluator rõ ràng ở bước riêng. |
| Bind thành công nhưng dữ liệu vẫn sai nghiệp vụ | Conversion không thay thế validation. | Chạy Validator sau bind và xử lý BindingResult. |
| SpEL expression không đọc được property | EvaluationContext/accessor không expose property hoặc target khác dự kiến. | Kiểm tra root object và property access; chỉ expose property cần thiết. |
| Log lộ dữ liệu nhạy cảm khi bind lỗi | Ghi trực tiếp rejected value vào log. | Log field và error code; che hoặc loại bỏ dữ liệu nhạy cảm. |

## Ghi nhớ

- `DataBinder` bind property values vào target object, thực hiện type conversion và ghi nhận lỗi trong `BindingResult`.
- `WebDataBinder` mở rộng DataBinder cho web binding; `@InitBinder` dùng để cấu hình binder trong Spring MVC.
- Property path như `address.city` hoặc `items[0].quantity` là cú pháp truy cập property, không phải một SpEL expression đầy đủ.
- DataBinder không tự parse mọi chuỗi request thành SpEL; chuỗi đầu vào vẫn là dữ liệu trừ khi ứng dụng chủ động evaluate nó.
- `ConversionService` chuyển kiểu; `Validator` kiểm tra quy tắc dữ liệu sau bind.
- Dùng `setAllowedFields(...)` và form DTO để giảm mass-assignment risk; kiểm tra suppressed fields khi cần.
- Đặt giới hạn auto-grow cho nested paths/collections khi phù hợp với cấu trúc target.
- SpEL có thể tính toán hoặc đánh giá rule trên object đã bind ở một bước riêng, bằng EvaluationContext được giới hạn.
- `@Value` expression evaluation là cơ chế riêng, không đồng nghĩa với DataBinder.
- Không expose domain object, getter hoặc expression evaluator rộng cho dữ liệu không tin cậy.

## Tài liệu tham khảo

- [Spring Framework Reference — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework API — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework API — WebDataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework API — BindingResult](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework Reference — EvaluationContext and SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)