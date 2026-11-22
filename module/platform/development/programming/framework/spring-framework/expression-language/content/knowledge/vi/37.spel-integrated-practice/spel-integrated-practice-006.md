# Bind dữ liệu chuỗi vào object qua conversion và validation trong SpEL

Spring Expression Language (SpEL) có thể gán giá trị vào property của object bằng `Expression.setValue(...)`. Khi giá trị đầu vào là chuỗi nhưng property đích có kiểu khác, TypeConverter của EvaluationContext có thể chuyển đổi giá trị trước khi ghi. Sau bước binding, ứng dụng có thể chạy Bean Validation hoặc Spring Validator để kiểm tra các ràng buộc dữ liệu.

Cần tách rõ hai trách nhiệm: **conversion** biến đổi biểu diễn dữ liệu sang kiểu Java mà property yêu cầu; **validation** kiểm tra giá trị sau khi chuyển đổi có thỏa điều kiện của object và nghiệp vụ hay không. SpEL hỗ trợ truy cập và gán property, nhưng bản thân thao tác `setValue` không tự chạy Bean Validation.

## 1. Quy trình bind dữ liệu

Một quy trình cơ bản gồm các bước:

1. Tạo DTO hoặc object đích có property và setter phù hợp.
2. Tạo EvaluationContext có quyền ghi property trong phạm vi cần thiết.
3. Cấu hình ConversionService/TypeConverter để chuyển chuỗi sang kiểu đích.
4. Dùng expression đã được kiểm soát để gán các giá trị đầu vào.
5. Thu thập lỗi conversion hoặc binding.
6. Chạy Validator trên object sau khi binding thành công.
7. Chỉ chuyển object hợp lệ sang tầng nghiệp vụ sau khi kiểm tra quyền và quy tắc liên quan.

Ví dụ, dữ liệu biểu mẫu có thể đến dưới dạng:

    Map<String, String> input = Map.of(
            "fullName", "Lan Nguyen",
            "email", "lan@example.com",
            "age", "25"
    );

Object đích có thể khai báo `fullName` và `email` là String, còn `age` là Integer. SpEL có thể gán trực tiếp chuỗi vào property age nếu TypeConverter của context hỗ trợ String sang Integer.

Không nên xem việc chuyển đổi thành công là bằng chứng dữ liệu hợp lệ. Chuỗi `"-5"` có thể chuyển thành Integer nhưng vẫn vi phạm quy tắc tuổi tối thiểu.

## 2. Chuẩn bị DTO có property rõ ràng

Dùng DTO dành riêng cho dữ liệu đầu vào giúp giới hạn các field được phép bind và tránh expose toàn bộ entity hoặc object có nhiều quyền.

Ví dụ:

    public class RegistrationForm {

        private String fullName;
        private String email;
        private Integer age;

        public String getFullName() {
            return fullName;
        }

        public void setFullName(String fullName) {
            this.fullName = fullName;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

Reflective/data-binding PropertyAccessor có thể đọc và ghi các JavaBean property tương ứng. Property cần ghi phải có setter hoặc được accessor hỗ trợ theo cách khác.

Nên giữ DTO nhỏ, có kiểu dữ liệu cụ thể và chỉ chứa những field use case cần nhận. Không bind trực tiếp vào entity có quan hệ sâu, field quản trị, trạng thái thanh toán hoặc thuộc tính xác định quyền sở hữu nếu người gửi request không được phép thay đổi chúng.

## 3. Dùng SimpleEvaluationContext cho data binding

Với use case chỉ cần đọc/ghi JavaBean property, có thể dùng SimpleEvaluationContext ở chế độ data binding:

    RegistrationForm form = new RegistrationForm();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("fullName")
            .setValue(context, "Lan Nguyen");

    parser.parseExpression("age")
            .setValue(context, "25");

Trong ví dụ, root object là form. Expression `fullName` và `age` được resolve trên root object, sau đó SpEL ghi giá trị qua property accessor. Với age, TypeConverter của context chuyển chuỗi `"25"` sang Integer nếu conversion được hỗ trợ.

SimpleEvaluationContext được thiết kế với tập tính năng giới hạn hơn StandardEvaluationContext. Builder read-write data binding cho phép truy cập property theo mục đích binding, nhưng không bật toàn bộ khả năng như bean reference, type reference hoặc constructor invocation.

Nếu chỉ cần binding dữ liệu từ chuỗi, không cần đưa ApplicationContext hoặc service vào EvaluationContext.

## 4. Cấu hình ConversionService cho kiểu đích

StandardEvaluationContext và SimpleEvaluationContext có TypeConverter. StandardTypeConverter có thể sử dụng Spring ConversionService để chuyển đổi giá trị.

Ví dụ cấu hình converter cho LocalDate theo định dạng ISO:

    DefaultFormattingConversionService conversionService =
            new DefaultFormattingConversionService();

    conversionService.addConverter(
            String.class,
            LocalDate.class,
            source -> LocalDate.parse(
                    source,
                    DateTimeFormatter.ISO_LOCAL_DATE
            )
    );

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .withConversionService(conversionService)
                    .build();

Sau đó có thể gán:

    parser.parseExpression("startDate")
            .setValue(context, "2026-11-12");

ConversionService tìm converter phù hợp với kiểu nguồn String và kiểu đích LocalDate. Nếu chuỗi không theo định dạng ISO được cấu hình, conversion sẽ thất bại và property không nhận được giá trị LocalDate hợp lệ.

Spring cung cấp các converter và formatter phổ biến qua những implementation như DefaultConversionService và DefaultFormattingConversionService. Với định dạng ngày giờ riêng của ứng dụng, hãy đăng ký Converter hoặc Formatter rõ ràng thay vì phụ thuộc vào định dạng ngầm của môi trường.

## 5. Conversion khác validation

Conversion trả lời câu hỏi: “Giá trị đầu vào có thể biểu diễn thành kiểu Java đích không?”

Validation trả lời câu hỏi: “Giá trị đã có kiểu Java có thỏa ràng buộc không?”

Ví dụ:

| Chuỗi đầu vào | Conversion sang Integer | Validation với `@Min(18)` |
|---|---|---|
| `"25"` | Thành công, giá trị 25 | Hợp lệ |
| `"abc"` | Thất bại | Chưa có Integer để kiểm tra |
| `"15"` | Thành công, giá trị 15 | Không hợp lệ |
| `"-1"` | Thành công, giá trị -1 | Không hợp lệ |

Một giá trị có thể chuyển đổi được nhưng vẫn sai quy tắc nghiệp vụ. Ngược lại, nếu conversion thất bại thì bước validation không thể kiểm tra đúng giá trị kiểu đích mà người dùng dự định cung cấp.

Hãy giữ riêng lỗi binding/conversion và lỗi validation để trả thông báo chính xác. Ví dụ, `"abc"` cho field age là lỗi định dạng số; `"15"` là số hợp lệ về kiểu nhưng vi phạm giới hạn tuổi.

## 6. Khai báo ràng buộc bằng Bean Validation

DTO có thể dùng annotation Jakarta Bean Validation:

    public class RegistrationForm {

        @NotBlank
        private String fullName;

        @NotBlank
        @Email
        private String email;

        @NotNull
        @Min(18)
        @Max(120)
        private Integer age;

        // getters and setters
    }

Sau khi bind dữ liệu, chạy validator:

    ValidatorFactory factory =
            Validation.buildDefaultValidatorFactory();

    Validator validator = factory.getValidator();

    Set<ConstraintViolation<RegistrationForm>> violations =
            validator.validate(form);

    if (!violations.isEmpty()) {
        // Chuyển violations thành lỗi hiển thị hoặc lỗi API.
    }

Trong ứng dụng Spring, thường nên cấu hình và tái sử dụng `LocalValidatorFactoryBean` hoặc inject Jakarta Validator đã được Spring quản lý, thay vì tạo ValidatorFactory mới cho mỗi request. Đảm bảo dự án có Jakarta Bean Validation API và một provider tương thích, chẳng hạn Hibernate Validator.

SpEL không tự gọi `validator.validate(form)` sau khi `setValue`. Ứng dụng phải chủ động chạy validation ở bước phù hợp.

## 7. Ví dụ hoàn chỉnh: bind, convert rồi validate

Ví dụ sau bind một số field đã biết vào DTO, chuyển tuổi từ String sang Integer rồi kiểm tra ràng buộc:

    RegistrationForm form = new RegistrationForm();

    DefaultFormattingConversionService conversionService =
            new DefaultFormattingConversionService();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .withConversionService(conversionService)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("fullName")
            .setValue(context, input.get("fullName"));

    parser.parseExpression("email")
            .setValue(context, input.get("email"));

    parser.parseExpression("age")
            .setValue(context, input.get("age"));

    Set<ConstraintViolation<RegistrationForm>> violations =
            validator.validate(form);

Nếu `input.get("age")` là chuỗi số hợp lệ, TypeConverter có thể chuyển sang Integer trước khi setter được gọi. Nếu không chuyển đổi được, `setValue` phát sinh lỗi evaluation/conversion; ứng dụng cần bắt lỗi đó và ghi nhận lỗi cho field age.

Trong code production, nên tách từng field thành thao tác có xử lý lỗi riêng để một field sai định dạng không làm mất thông tin lỗi của các field còn lại. Chỉ chạy validation trên object sau khi đã xác định trạng thái binding; nếu vẫn validate object có field chưa bind do conversion thất bại, hãy phân biệt rõ violation phát sinh từ dữ liệu thiếu với lỗi conversion ban đầu.

## 8. Thu thập lỗi binding riêng với lỗi validation

Có thể tạo một helper nhận expression đã được ứng dụng định nghĩa sẵn:

    void bindValue(
            Expression expression,
            EvaluationContext context,
            Object rawValue,
            String field,
            List<String> bindingErrors) {

        try {
            expression.setValue(context, rawValue);
        }
        catch (EvaluationException ex) {
            bindingErrors.add(
                    "Không thể chuyển hoặc gán field: " + field
            );
        }
    }

Các expression được truyền vào helper nên được parse từ tên field cố định trong code hoặc lấy từ allowlist. Không nhận trực tiếp một SpEL expression hay property path tùy ý từ request.

Sau khi bind các field:

    if (bindingErrors.isEmpty()) {
        Set<ConstraintViolation<RegistrationForm>> violations =
                validator.validate(form);
    }

Ứng dụng có thể chuyển từng ConstraintViolation thành lỗi gắn với property path tương ứng. Không trả stack trace hoặc thông tin nội bộ của converter cho client; giữ cause chain trong log nội bộ đã được kiểm soát.

Trong thực tế, nên dùng kiểu lỗi có cấu trúc như field, error code và message thay vì chỉ gom thành chuỗi. Điều này giúp API hoặc giao diện hiển thị lỗi theo từng input.

## 9. Chỉ bind field nằm trong allowlist

Không dùng tên property do client gửi trực tiếp làm SpEL:

    parser.parseExpression(userSuppliedField)
            .setValue(context, userSuppliedValue);

Nếu field chứa cú pháp SpEL hoặc đường dẫn property khác dự kiến, người gửi có thể cố truy cập hoặc ghi các thuộc tính ngoài phạm vi. SimpleEvaluationContext giới hạn nhiều capability nhưng không thay thế allowlist field của ứng dụng.

Thay vào đó, ánh xạ tên input sang expression cố định:

    Map<String, Expression> writableFields = Map.of(
            "fullName", parser.parseExpression("fullName"),
            "email", parser.parseExpression("email"),
            "age", parser.parseExpression("age")
    );

    Expression expression = writableFields.get(inputField);

    if (expression == null) {
        throw new IllegalArgumentException(
                "Field is not writable"
        );
    }

    expression.setValue(context, inputValue);

Allowlist này chỉ minh họa các field được phép. Ứng dụng vẫn cần xác thực caller có quyền cập nhật object và field tương ứng. Không đưa các property như `id`, `owner`, `tenantId`, `role`, `approved` hoặc trạng thái quản trị vào allowlist nếu client không được phép kiểm soát chúng.

## 10. Binding nested path

SpEL hỗ trợ gán property lồng nhau:

    parser.parseExpression("address.city")
            .setValue(context, "Da Nang");

Để thao tác này thành công, object trung gian `address` phải tồn tại và accessor phải có quyền ghi property `city`. SpEL không tự tạo Address nếu property address đang null.

Có thể khởi tạo object trung gian trước:

    form.setAddress(new AddressForm());

    parser.parseExpression("address.city")
            .setValue(context, "Da Nang");

Nếu nested object cũng có validation constraint, khai báo `@Valid` trên property:

    public class RegistrationForm {
        @Valid
        @NotNull
        private AddressForm address;
    }

Validator sẽ kiểm tra object lồng nhau khi thực hiện validation cascade. Nếu address null, `@NotNull` phát hiện lỗi; nếu address tồn tại, các constraint bên trong AddressForm được đánh giá.

Với nested path, hãy allowlist chính xác đường dẫn được phép ghi và tránh cho client tự tạo đường dẫn tùy ý. Kiểm tra null, kiểu target và quyền cập nhật trước khi gán.

## 11. Custom Converter cho kiểu domain

Nếu field dùng kiểu riêng, có thể đăng ký Converter tường minh. Ví dụ chuyển chuỗi sang enum:

    public enum DeliveryMode {
        STANDARD,
        EXPRESS
    }

    conversionService.addConverter(
            String.class,
            DeliveryMode.class,
            source -> DeliveryMode.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            )
    );

Khi DTO có property `deliveryMode` kiểu DeliveryMode, expression có thể gán chuỗi:

    parser.parseExpression("deliveryMode")
            .setValue(context, "express");

Converter chuẩn hóa chữ hoa/thường trước khi chuyển đổi. Nếu chuỗi không khớp enum, conversion thất bại; ứng dụng nên trả lỗi field rõ ràng.

Converter nên thực hiện chuyển đổi biểu diễn dữ liệu thuần túy. Không nên gọi database, kiểm tra quyền, gửi message hoặc thay đổi trạng thái trong converter. Các quy tắc cần dữ liệu nghiệp vụ nên được kiểm tra ở service hoặc Validator chuyên biệt.

## 12. Validation theo nhóm và quy tắc liên field

Bean Validation hỗ trợ validation groups để áp dụng các constraint khác nhau theo thao tác tạo mới hoặc cập nhật:

    interface Create {}
    interface Update {}

    public class ProfileForm {

        @NotBlank(groups = Create.class)
        private String username;

        @Email(groups = {Create.class, Update.class})
        private String email;
    }

    validator.validate(form, Create.class);

Điều này hữu ích khi một field bắt buộc lúc tạo mới nhưng có thể không được gửi trong request cập nhật một phần.

Với quy tắc liên field, có thể dùng class-level constraint hoặc một Spring Validator chuyên biệt. Ví dụ, `startDate` phải trước `endDate`; kiểm tra từng field riêng lẻ không đủ để xác nhận quan hệ giữa chúng.

Conversion vẫn diễn ra trước validation. Khi cả hai ngày đã được chuyển thành LocalDate, validator mới có thể so sánh chúng theo quy tắc domain.

## 13. Khi nào nên dùng DataBinder thay vì SpEL?

SpEL có thể gán property và tận dụng TypeConverter, nhưng nó không phải framework binding form tổng quát. Nếu cần bind nhiều field từ request, quản lý field error, allowed fields, nested object và validation theo quy trình chuẩn của Spring MVC, `DataBinder` hoặc `WebDataBinder` thường phù hợp hơn.

DataBinder cung cấp các cơ chế chuyên biệt như:

- Bind property values vào target object.
- Cấu hình allowed fields và disallowed fields.
- Sử dụng ConversionService và PropertyEditor.
- Thu thập lỗi binding trong BindingResult.
- Kết hợp với Spring Validator hoặc Jakarta Bean Validation.

Dùng SpEL khi ứng dụng thực sự cần expression để chọn hoặc gán một số property đã kiểm soát. Dùng DataBinder cho luồng form/request binding thông thường để tận dụng cơ chế binding và báo lỗi được thiết kế riêng cho công việc đó.

Dù dùng công cụ nào, vẫn phải kiểm tra quyền trên object và field được phép cập nhật. Allowed fields và validation không thay thế authorization.

## 14. Lỗi thường gặp

- **Cho rằng setValue tự validate:** SpEL chỉ thực hiện truy cập/gán và conversion; ứng dụng phải gọi Validator riêng.
- **Nhầm conversion với validation:** chuỗi có thể chuyển thành số nhưng vẫn vi phạm `@Min`, `@Max` hoặc quy tắc domain.
- **Dùng context chỉ đọc để ghi:** chọn `forReadWriteDataBinding()` khi use case cần cập nhật property.
- **Property không có setter:** kiểm tra accessor và JavaBean property đích.
- **Nested object null:** khởi tạo object trung gian trước khi gán path sâu.
- **Converter không hỗ trợ định dạng:** đăng ký Converter/Formatter phù hợp và kiểm thử input sai.
- **Bind theo property path từ client:** dùng allowlist field và expression cố định.
- **Bind trực tiếp vào entity:** dùng DTO giới hạn field để tránh mass assignment.
- **Bỏ qua lỗi conversion:** ghi nhận lỗi theo field và không coi object chưa bind đầy đủ là hợp lệ.
- **Tạo ValidatorFactory mỗi request:** cấu hình và tái sử dụng validator do Spring quản lý.

## 15. Ghi nhớ

SpEL có thể bind giá trị bằng `Expression.setValue(...)`; TypeConverter của EvaluationContext chuyển dữ liệu chuỗi sang kiểu property đích khi có converter phù hợp. Dùng `SimpleEvaluationContext.forReadWriteDataBinding()` cho property binding có phạm vi giới hạn và cấu hình ConversionService cho kiểu domain hoặc định dạng riêng. Sau conversion, ứng dụng phải chủ động chạy Jakarta Bean Validation hoặc Spring Validator; `setValue` không tự validate object. Tách lỗi conversion khỏi constraint violation, khởi tạo nested object trước khi ghi, chỉ bind field nằm trong allowlist và kiểm tra quyền cập nhật. Với form/request binding nhiều field, cân nhắc DataBinder/WebDataBinder vì chúng cung cấp quy trình binding và báo lỗi chuyên dụng.
