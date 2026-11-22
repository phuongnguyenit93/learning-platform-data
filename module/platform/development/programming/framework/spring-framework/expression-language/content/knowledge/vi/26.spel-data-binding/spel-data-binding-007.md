# Lỗi bind, conversion và validation cần tách biệt

## 1. Ba công đoạn khác nhau

Trong ứng dụng Spring, dữ liệu đầu vào thường đi qua ba công đoạn liên quan nhưng có mục đích khác nhau:

1. **Binding (gán dữ liệu):** tìm property đích trên object và đưa giá trị đầu vào vào property đó.
2. **Conversion (chuyển đổi kiểu):** chuyển giá trị từ kiểu nguồn sang kiểu mà property hoặc caller yêu cầu.
3. **Validation (kiểm tra hợp lệ):** kiểm tra giá trị sau khi bind và convert có đáp ứng quy tắc dữ liệu hoặc nghiệp vụ hay không.

Ba công đoạn có thể xảy ra trong cùng một request, nhưng không thay thế cho nhau. Một chuỗi có thể chuyển đổi thành Integer thành công nhưng vẫn không hợp lệ theo nghiệp vụ. Ngược lại, một giá trị có thể hợp lệ về mặt nghiệp vụ nhưng không thể bind vì property không tồn tại hoặc không thể ghi.

Ví dụ với form đăng ký:

- Binding: đưa giá trị `"18"` vào property `age`.
- Conversion: chuyển String `"18"` thành Integer `18`.
- Validation: kiểm tra tuổi có đạt giới hạn tối thiểu hay không.

Nếu `age = "abc"`, lỗi nằm ở conversion. Nếu `age = "15"` được chuyển thành Integer 15 nhưng quy tắc yêu cầu ít nhất 18, lỗi nằm ở validation. Nếu property `age` không tồn tại hoặc không thể ghi, lỗi nằm ở binding/property access.

## 2. Binding trong SpEL

SpEL có thể đọc hoặc ghi property trên root object thông qua PropertyAccessor. Khi gọi `setValue()`, expression xác định property đích rồi gán giá trị được cung cấp:

```java
ExpressionParser parser = new SpelExpressionParser();

RegistrationForm form = new RegistrationForm();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withRootObject(form)
                .build();

parser.parseExpression("email")
        .setValue(context, "ada@example.com");

String email = form.getEmail();
```

Trong ví dụ này, `email` là property path và `setValue()` thực hiện thao tác ghi. Property phải có thể được truy cập và ghi bởi PropertyAccessor đã cấu hình. Với data binding context, Spring hỗ trợ public property theo quy tắc data binding.

Nếu expression tham chiếu property không tồn tại, hoặc property không thể ghi, SpEL không thể hoàn tất thao tác binding. Đây là vấn đề property path/access, không phải lỗi validation của giá trị.

Ví dụ:

```java
parser.parseExpression("unknownField")
        .setValue(context, "value");
```

Nếu `RegistrationForm` không có property `unknownField`, expression không thể ghi giá trị vào object. Không nên xử lý lỗi này bằng cách nới lỏng validation; cần kiểm tra tên property, getter/setter và PropertyAccessor.

### 2.1. Binding bằng DataBinder

Ở tầng Spring data binding, `DataBinder` nhận property values và bind chúng vào target object. Đây là API thường dùng cho form object và các luồng binding do ứng dụng kiểm soát:

```java
RegistrationForm form = new RegistrationForm();

DataBinder binder = new DataBinder(form, "registrationForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("email", "ada@example.com");
values.add("age", "18");

binder.bind(values);

BindingResult result = binder.getBindingResult();
```

`DataBinder` tìm property đích và thực hiện các bước cần thiết để đưa giá trị vào object. Quá trình này có thể bao gồm conversion. Các lỗi binding/conversion được ghi vào BindingResult thay vì phải tự coi mọi lỗi là lỗi validation.

Có thể giới hạn các property được phép bind:

```java
binder.setAllowedFields("email", "age", "displayName");
```

Allow-list property giúp tránh mass assignment, ví dụ người gửi request cố gắng bind vào `role`, `admin` hoặc property nội bộ không được phép chỉnh sửa.

## 3. Conversion: chuyển giá trị sang kiểu đích

Dữ liệu từ HTTP form, query parameter hoặc cấu hình thường đến dưới dạng String. Property Java có thể cần Integer, Long, BigDecimal, Boolean, enum, ngày giờ hoặc kiểu domain khác.

SpEL dùng `TypeConverter` trong EvaluationContext để chuyển kết quả sang kiểu đích. Với cấu hình chuẩn, `StandardTypeConverter` tích hợp với Spring `ConversionService`.

Ví dụ yêu cầu kiểu đích khi đánh giá:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Integer age = parser.parseExpression("'18'")
        .getValue(context, Integer.class);

BigDecimal amount = parser.parseExpression("'125.50'")
        .getValue(context, BigDecimal.class);
```

Ví dụ gán chuỗi vào property số:

```java
RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

parser.parseExpression("age").setValue(context, "18");

Integer age = form.getAge();
// 18
```

Trong `setValue()`, SpEL biết kiểu property đích và yêu cầu TypeConverter chuyển String sang kiểu đó trước khi gán. Nếu chuỗi không biểu diễn được giá trị đích, conversion thất bại.

### 3.1. Conversion không xác nhận tính hợp lệ nghiệp vụ

Giả sử property `age` có kiểu Integer:

| Đầu vào | Conversion | Validation nếu yêu cầu age >= 18 |
|---|---|---|
| `"18"` | Thành công: Integer 18. | Hợp lệ. |
| `"15"` | Thành công: Integer 15. | Không hợp lệ. |
| `"abc"` | Thất bại: không chuyển được thành Integer. | Chưa có Integer từ đầu vào để kiểm tra quy tắc tuổi. |
| `""` | Có thể thành null tùy converter và kiểu đích. | Phụ thuộc quy tắc null/required. |

Conversion chỉ trả lời câu hỏi “giá trị này có thể biểu diễn bằng kiểu đích không?”. Nó không trả lời “giá trị này có được nghiệp vụ chấp nhận không?”.

### 3.2. Cấu hình ConversionService

Có thể dùng ConversionService mặc định hoặc đăng ký converter tùy chỉnh:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

Nếu ứng dụng cần định dạng riêng, chẳng hạn ngày theo một mẫu cụ thể hoặc alias cho enum, đăng ký converter phù hợp trong ConversionService. Converter nên xử lý định dạng đầu vào một cách tường minh và báo lỗi khi dữ liệu không đúng định dạng.

Không nên biến lỗi conversion thành một giá trị mặc định tùy tiện nếu điều đó có thể làm dữ liệu sai được lưu như dữ liệu hợp lệ.

## 4. Validation: kiểm tra quy tắc sau khi bind

Validation kiểm tra dữ liệu đã có kiểu phù hợp có đáp ứng quy tắc hay không. Các quy tắc có thể là:

- Trường bắt buộc không được null hoặc blank.
- Email phải đúng định dạng.
- Tuổi phải nằm trong phạm vi cho phép.
- Ngày kết thúc phải sau ngày bắt đầu.
- Trạng thái đơn hàng phải phù hợp với trạng thái hiện tại.

Ví dụ dùng Jakarta Bean Validation:

```java
public class RegistrationForm {

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // getters and setters
}
```

Các annotation mô tả constraint. Chúng không tự chuyển chuỗi thành Integer; việc conversion thuộc tầng binding/conversion. Validator kiểm tra object sau khi các giá trị đã được bind.

Với Spring Validator, có thể thêm validator vào DataBinder rồi gọi validation:

```java
RegistrationForm form = new RegistrationForm();

DataBinder binder = new DataBinder(form, "registrationForm");
binder.addValidators(registrationFormValidator);

MutablePropertyValues values = new MutablePropertyValues();
values.add("email", "ada@example.com");
values.add("age", "15");

binder.bind(values);
binder.validate();

BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Đọc và xử lý các lỗi trong result.
}
```

Nếu dùng Jakarta Bean Validation trong Spring, `LocalValidatorFactoryBean` có thể được đăng ký làm Spring Validator. Trong ứng dụng Spring-managed, validator thường được cấu hình qua dependency injection thay vì tự khởi tạo cho từng request.

## 5. BindingResult có thể chứa nhiều loại lỗi

`BindingResult` là nơi tập hợp lỗi phát sinh trong quá trình binding và validation. Một request có thể có nhiều lỗi cùng lúc, nhưng cần phân biệt nguồn của từng lỗi.

Với `FieldError`, phương thức `isBindingFailure()` giúp nhận biết lỗi gắn với binding/conversion:

- `true`: lỗi binding hoặc conversion của field.
- `false`: lỗi validation được ghi nhận cho field.

Ví dụ đọc lỗi:

```java
for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    Object rejectedValue = error.getRejectedValue();
    String message = error.getDefaultMessage();
    boolean bindingFailure = error.isBindingFailure();

    if (bindingFailure) {
        // Giá trị không bind/convert được vào property.
    }
    else {
        // Giá trị đã bind nhưng không đạt constraint/validation.
    }
}
```

Các thông tin hữu ích khi chẩn đoán:

| Thuộc tính | Ý nghĩa |
|---|---|
| `getField()` | Tên field có lỗi. |
| `getRejectedValue()` | Giá trị bị từ chối hoặc giá trị đầu vào liên quan đến lỗi. |
| `getCodes()` | Các message code để phân giải thông báo theo quy tắc Spring. |
| `getDefaultMessage()` | Thông báo mặc định của lỗi. |
| `isBindingFailure()` | Phân biệt binding/conversion failure với lỗi validation thông thường. |

Không chỉ kiểm tra `hasErrors()` rồi trả về một thông báo chung. Hãy xem field, mã lỗi và bindingFailure để biết phải sửa dữ liệu đầu vào, property mapping hay quy tắc nghiệp vụ.

## 6. Ví dụ: cùng một field, hai loại lỗi khác nhau

Giả sử form có `age` kiểu Integer và constraint `@Min(18)`.

### Trường hợp A: conversion thất bại

Đầu vào:

```text
age = "abc"
```

Spring không thể chuyển `"abc"` thành Integer. Property không nhận được giá trị Integer hợp lệ từ đầu vào. Trong DataBinder, lỗi được ghi vào BindingResult dưới dạng binding failure.

### Trường hợp B: conversion thành công, validation thất bại

Đầu vào:

```text
age = "15"
```

Spring chuyển thành Integer 15 thành công. Sau đó validator kiểm tra `@Min(18)` và ghi nhận lỗi validation vì tuổi nhỏ hơn 18.

Hai trường hợp cần cách xử lý khác nhau:

| Trường hợp | Lỗi | Hướng sửa |
|---|---|---|
| `"abc"` | Không phải số nguyên hợp lệ. | Yêu cầu người dùng nhập số đúng định dạng. |
| `"15"` | Là số nguyên nhưng vi phạm giới hạn tuổi. | Yêu cầu giá trị đáp ứng quy tắc nghiệp vụ. |

Nếu chỉ hiện thông báo “age không hợp lệ”, người dùng không biết cần sửa định dạng hay sửa giá trị.

## 7. Validation trong Spring MVC

Với form object được bind từ request, Spring MVC có thể thực hiện binding, conversion và validation trong quy trình xử lý controller.

Ví dụ:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "registration-form";
    }

    registrationService.register(form);
    return "redirect:/registration/success";
}
```

`@ModelAttribute` yêu cầu Spring bind request parameters vào form object. ConversionService hỗ trợ chuyển đổi giá trị sang kiểu property. `@Valid` yêu cầu validation trên object sau binding.

Nếu cần xử lý lỗi trong controller, `BindingResult` phải đặt ngay sau tham số model attribute tương ứng. Khi có BindingResult ở vị trí đó, controller có thể đọc lỗi và trả lại form. Nếu không có tham số BindingResult phù hợp, Spring MVC có thể ném exception cho lỗi validation/binding tùy loại argument và cấu hình.

Không nhầm `@Valid` với conversion: `@Valid` kích hoạt kiểm tra constraint, không chuyển `"15"` thành Integer 15.

## 8. Lỗi SpEL và lỗi DataBinder ở các tầng khác nhau

Tên exception phụ thuộc API và tầng đang thực hiện công việc. Một số nhóm thường gặp:

| Tầng | Dấu hiệu/lỗi thường gặp | Ý nghĩa |
|---|---|---|
| Parse expression | `ParseException` hoặc `SpelParseException` | Cú pháp SpEL không hợp lệ. |
| SpEL property/method evaluation | `SpelEvaluationException` | Expression không thể đánh giá, ví dụ property path sai hoặc gọi method không phù hợp. |
| Spring property binding | `NotWritablePropertyException`, `NotReadablePropertyException` hoặc lỗi access tương ứng | Property không tồn tại, không đọc được hoặc không ghi được. |
| Type conversion | `TypeMismatchException`, `ConversionFailedException` hoặc lỗi chuyển đổi được bọc trong exception tầng trên | Giá trị không chuyển được sang kiểu đích. |
| Validation | `ObjectError` / `FieldError` trong BindingResult hoặc `ConstraintViolation` | Giá trị đã được kiểm tra và vi phạm constraint. |

Trong DataBinder và Spring MVC, lỗi binding/conversion thường được giữ trong BindingResult thay vì luôn ném exception ra khỏi controller. Khi gọi SpEL trực tiếp, lỗi evaluation/conversion có thể được ném cho caller. Vì vậy, hãy chẩn đoán theo API đang dùng, không chỉ dựa vào tên exception ở một ví dụ khác.

Jakarta Bean Validation khi gọi trực tiếp `Validator.validate(object)` trả về tập `ConstraintViolation`. Nó không tự ném `ConstraintViolationException` cho mọi lỗi dữ liệu. `ConstraintViolationException` thường xuất hiện ở các cơ chế như method validation khi constraint trên tham số/giá trị trả về bị vi phạm.

## 9. SpEL setValue không tự chạy Bean Validation

Một điểm dễ nhầm là gọi `setValue()` thành công không có nghĩa object đã hợp lệ.

Ví dụ:

```java
RegistrationForm form = new RegistrationForm();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withRootObject(form)
                .build();

parser.parseExpression("age").setValue(context, "15");

// age đã được chuyển thành Integer 15.
// SpEL không tự chạy @Min(18) ở đây.
```

Sau thao tác này, nếu cần kiểm tra constraint, ứng dụng phải gọi Validator hoặc đưa object vào luồng Spring MVC/DataBinder có validation được cấu hình.

Tương tự, `getValue()` với target type chỉ thực hiện đánh giá và conversion sang kiểu đích. Nó không tự gọi Bean Validation.

## 10. Cách xử lý từng nhóm lỗi

### 10.1. Binding/property access failure

Kiểm tra:

- Tên property path có đúng không?
- Property có tồn tại trên object đích không?
- Getter/setter có phù hợp với thao tác đọc/ghi không?
- PropertyAccessor hiện tại có hỗ trợ kiểu object đó không?
- DataBinder có cho phép field đó qua allowed fields không?

Không sửa lỗi binding bằng cách thay đổi constraint validation.

### 10.2. Conversion failure

Kiểm tra:

- Kiểu nguồn thực tế là gì?
- Kiểu đích của property hoặc `getValue()` là gì?
- Chuỗi có đúng định dạng không?
- Locale/format có phù hợp với converter không?
- ConversionService của context đã đăng ký converter cần thiết chưa?

Nếu định dạng hợp lệ theo nghiệp vụ nhưng converter mặc định không hiểu, đăng ký converter riêng. Nếu dữ liệu sai định dạng, trả thông báo conversion rõ ràng.

### 10.3. Validation failure

Kiểm tra:

- Constraint nào bị vi phạm?
- Giá trị sau conversion là gì?
- Quy tắc nghiệp vụ có đúng không?
- Có cần kiểm tra liên trường (cross-field) hay không?
- Message code và thông báo hiển thị có giải thích cách sửa không?

Không nới constraint chỉ để làm biến mất một lỗi conversion. Hai loại lỗi có nguyên nhân khác nhau.

## 11. Quy trình xử lý request an toàn

Một quy trình dễ chẩn đoán thường gồm:

1. Xác định danh sách property được phép bind.
2. Bind dữ liệu đầu vào vào target object.
3. Convert từng giá trị sang kiểu property đích bằng ConversionService.
4. Thu thập lỗi binding/conversion vào BindingResult.
5. Chạy Validator trên object đã bind được.
6. Thu thập lỗi validation vào cùng BindingResult hoặc kết quả validation riêng.
7. Phân loại FieldError bằng field, error code và `isBindingFailure()`.
8. Chỉ gọi nghiệp vụ khi không còn lỗi phù hợp với chính sách xử lý.
9. Hiển thị thông báo theo đúng nguyên nhân: sai property, sai định dạng hoặc vi phạm quy tắc.
10. Ghi log mã lỗi và field cần thiết; tránh ghi dữ liệu nhạy cảm/rejected value không cần thiết.

Nếu dùng SpEL trực tiếp để gán property, hãy xem đó là thao tác property access và conversion. Gọi Validator là một bước riêng sau đó nếu ứng dụng cần bảo đảm object thỏa constraint.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `setValue()` thành công nhưng object vẫn không hợp lệ | SpEL đã bind/convert nhưng chưa chạy validation. | Gọi Validator hoặc DataBinder.validate() sau khi bind. |
| Chuỗi số bị báo lỗi | Giá trị không đúng định dạng kiểu đích. | Kiểm tra format và ConversionService. |
| Giá trị chuyển được nhưng vẫn bị từ chối | Constraint nghiệp vụ không được đáp ứng. | Đọc FieldError/ConstraintViolation và sửa giá trị. |
| FieldError khó phân loại | Chỉ kiểm tra `hasErrors()`. | Kiểm tra `isBindingFailure()`, field, codes và rejectedValue. |
| Property không ghi được | Sai path, thiếu setter hoặc accessor không hỗ trợ. | Kiểm tra target object và PropertyAccessor. |
| Validator không chạy | Chưa gọi validate hoặc chưa cấu hình validator trong MVC/DataBinder. | Đăng ký Spring Validator và kích hoạt validation. |
| Dùng @Valid nhưng conversion thất bại | @Valid chỉ kiểm tra constraint sau binding. | Xử lý lỗi binding/conversion riêng trong BindingResult. |
| Tất cả lỗi bị đổi thành “invalid input” | Không phân biệt binding, conversion và validation. | Dùng mã lỗi và nguồn lỗi để đưa thông báo cụ thể. |
| Validation chạy trên giá trị cũ sau conversion failure | Field không nhận được giá trị mới do conversion thất bại. | Xem binding failure trước; không giả định target đã chứa rejected value. |
| Cho phép bind mọi field của object | Không giới hạn property đầu vào. | Dùng form DTO riêng và allowed fields. |

## 13. Ghi nhớ

- Binding tìm property đích và gán dữ liệu vào object.
- Conversion chuyển giá trị từ kiểu nguồn sang kiểu đích; SpEL dùng TypeConverter và Spring ConversionService.
- Validation kiểm tra giá trị sau bind/convert có đáp ứng constraint và quy tắc nghiệp vụ không.
- `setValue()` có thể bind và convert nhưng không tự chạy Bean Validation.
- DataBinder thực hiện binding và ghi lỗi vào BindingResult; có thể gọi validate() để chạy validator.
- `FieldError.isBindingFailure()` giúp phân biệt lỗi binding/conversion với lỗi validation.
- Conversion thành công không đồng nghĩa dữ liệu hợp lệ; `"15"` có thể chuyển thành Integer nhưng vẫn vi phạm `@Min(18)`.
- Parse/evaluation errors của SpEL khác với binding errors, conversion errors và validation errors.
- Dùng allow-list property, form DTO và thông báo lỗi đúng nguyên nhân để xử lý dữ liệu an toàn.

## Tài liệu tham khảo

- [Spring Framework Reference — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework Reference — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html)
- [FieldError Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html)
- [DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
