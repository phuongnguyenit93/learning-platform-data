# Triển khai Spring Validator với supports và validate

Spring Framework cung cấp interface \`org.springframework.validation.Validator\` để gom các quy tắc kiểm tra dữ liệu vào một thành phần có thể tái sử dụng. Một validator triển khai hai phương thức: \`supports(Class<?> clazz)\` cho biết kiểu đối tượng mà validator xử lý, còn \`validate(Object target, Errors errors)\` kiểm tra dữ liệu thực tế và ghi nhận lỗi vào đối tượng \`Errors\`.

Trong Spring Data REST, validator có thể được đăng ký theo các repository event như \`beforeCreate\` và \`beforeSave\`. Nhờ vậy, dữ liệu gửi qua endpoint repository được kiểm tra trước khi thao tác lưu hoặc tạo tài nguyên tiếp tục. Cùng một validator cũng có thể được dùng trong Spring MVC hoặc service nếu được gọi đúng tại luồng xử lý tương ứng.

## 1. Spring Validator giải quyết vấn đề gì?

Giả sử ứng dụng quản lý sản phẩm. Một sản phẩm phải có tên, giá không âm và số lượng tồn kho không âm. Nếu viết các điều kiện này rải rác trong controller, mỗi endpoint có thể thực hiện kiểm tra khác nhau. Khi có thêm endpoint tạo, cập nhật hoặc import dữ liệu, quy tắc dễ bị lặp và thiếu nhất quán.

Spring Validator tách quy tắc kiểm tra khỏi controller và repository:

- \`supports\` xác định validator có áp dụng cho kiểu đối tượng nào.
- \`validate\` kiểm tra giá trị của một đối tượng cụ thể.
- \`Errors\` nhận các lỗi theo field hoặc lỗi tổng thể.
- Spring MVC hoặc Spring Data REST gọi validator tại thời điểm phù hợp trong vòng đời request/repository.

Validator không tự lưu dữ liệu và không tự ném lỗi HTTP. Nó ghi nhận lỗi vào \`Errors\`; thành phần tích hợp phía trên quyết định cách xử lý và trả lỗi cho client.

## 2. Interface Validator có hai phương thức cốt lõi

Interface Spring Validator nằm trong package \`org.springframework.validation\`:

~~~java
public interface Validator {

    boolean supports(Class<?> clazz);

    void validate(Object target, Errors errors);
}
~~~

Ý nghĩa của từng phương thức:

| Phương thức | Trách nhiệm | Câu hỏi cần trả lời |
|---|---|---|
| \`supports(Class<?> clazz)\` | Kiểm tra kiểu class có được validator hỗ trợ hay không. | Validator này có xử lý loại đối tượng này không? |
| \`validate(Object target, Errors errors)\` | Kiểm tra dữ liệu và thêm lỗi vào Errors. | Đối tượng hiện tại có vi phạm quy tắc nào không? |

\`supports\` chỉ nhận thông tin về kiểu, không nhận một instance cụ thể. Vì vậy, không kiểm tra giá trị name, price hay trạng thái của entity trong phương thức này.

\`validate\` nhận đối tượng cần kiểm tra và một \`Errors\` để ghi nhận kết quả. Phương thức này có thể thêm nhiều lỗi trong một lần chạy để client nhận được đầy đủ vấn đề cần sửa.

Spring thường gọi \`supports\` trước khi gọi \`validate\`. Khi tự gọi validator, cũng nên kiểm tra \`supports(target.getClass())\` để tránh truyền nhầm kiểu.

## 3. Triển khai validator cho Product

Giả sử entity Product có các thuộc tính name, price và stock:

~~~java
public class Product {

    private String name;
    private BigDecimal price;
    private Integer stock;

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Integer getStock() {
        return stock;
    }
}
~~~

Tạo validator:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

import java.math.BigDecimal;

@Component
public class ProductValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Product.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Product product = (Product) target;

        if (!StringUtils.hasText(product.getName())) {
            errors.rejectValue(
                "name",
                "product.name.required",
                "Tên sản phẩm không được để trống"
            );
        }

        BigDecimal price = product.getPrice();
        if (price == null) {
            errors.rejectValue(
                "price",
                "product.price.required",
                "Giá sản phẩm là bắt buộc"
            );
        } else if (price.compareTo(BigDecimal.ZERO) < 0) {
            errors.rejectValue(
                "price",
                "product.price.negative",
                "Giá sản phẩm không được âm"
            );
        }

        Integer stock = product.getStock();
        if (stock == null || stock < 0) {
            errors.rejectValue(
                "stock",
                "product.stock.invalid",
                "Số lượng tồn kho phải là số không âm"
            );
        }
    }
}
~~~

Validator trên kiểm tra ba trường và có thể ghi nhận nhiều lỗi cùng lúc. Nếu name rỗng, price âm và stock không hợp lệ, cả ba lỗi đều được thêm vào \`Errors\`; client không cần sửa từng lỗi qua nhiều lần gửi request.

\`Product.class.isAssignableFrom(clazz)\` chấp nhận Product và các lớp con của Product. Nếu validator chỉ được phép hỗ trợ đúng một kiểu class, có thể dùng \`Product.class.equals(clazz)\`. Chọn cách kiểm tra theo mô hình kế thừa và loại proxy mà ứng dụng sử dụng.

## 4. Hiểu đúng supports(Class<?> clazz)

\`supports\` là bước chọn validator theo kiểu đối tượng. Một validator dành cho Product không nên trả true cho mọi class, vì Spring có thể gọi nó với một đối tượng không tương thích.

Ví dụ:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return Product.class.isAssignableFrom(clazz);
}
~~~

Một số cách triển khai:

- \`Product.class.equals(clazz)\`: chỉ hỗ trợ chính xác Product.
- \`Product.class.isAssignableFrom(clazz)\`: hỗ trợ Product và các lớp kế thừa.
- \`clazz != null && Product.class.isAssignableFrom(clazz)\`: thêm kiểm tra null nếu validator được gọi từ code tùy chỉnh có thể truyền class null.

Không dùng \`target instanceof Product\` trong \`supports\`, vì tham số của phương thức là \`Class<?>\`, không phải object. Cũng không nên kiểm tra nội dung field tại đây; nội dung thuộc trách nhiệm của \`validate\`.

Nếu một validator hỗ trợ nhiều kiểu đối tượng, có thể kiểm tra nhiều class:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return Product.class.isAssignableFrom(clazz)
        || ProductVariant.class.isAssignableFrom(clazz);
}
~~~

Tuy nhiên, khi hai kiểu có quy tắc khác nhau đáng kể, tách thành các validator riêng thường giúp mã dễ hiểu và dễ đăng ký hơn.

## 5. Ghi lỗi bằng Errors và rejectValue

\`Errors\` là API để validator báo lỗi. Hai phương thức thường dùng là:

~~~java
errors.rejectValue(
    "name",
    "product.name.required",
    "Tên sản phẩm không được để trống"
);

errors.reject(
    "product.invalid",
    "Thông tin sản phẩm không hợp lệ"
);
~~~

\`rejectValue\` gắn lỗi với một field. Các tham số thường gồm:

1. Tên field trong object, ví dụ \`name\` hoặc \`price\`.
2. Error code để tra thông báo.
3. Default message nếu không tìm được message tương ứng.

\`reject\` tạo lỗi tổng thể không gắn với một field cụ thể. Dùng nó cho quy tắc liên quan nhiều thuộc tính hoặc trạng thái chung của object.

Các phương thức hữu ích khác:

- \`errors.hasErrors()\`: kiểm tra có lỗi nào hay không.
- \`errors.hasFieldErrors("price")\`: kiểm tra lỗi của một field.
- \`errors.getFieldErrors()\`: lấy danh sách lỗi theo field.
- \`errors.getGlobalErrors()\`: lấy lỗi tổng thể.
- \`errors.getAllErrors()\`: lấy toàn bộ lỗi.

Không nên dùng tên field tùy ý. Field path phải tương ứng với property mà binder hoặc API representation hiểu được; nếu dùng sai tên, client có thể không biết phải sửa trường nào.

## 6. Dùng error code và MessageSource

Thay vì viết cứng thông báo ở mọi validator, có thể dùng error code để Spring tra nội dung trong MessageSource.

Ví dụ file \`messages.properties\`:

~~~properties
product.name.required=Product name is required.
product.price.required=Product price is required.
product.price.negative=Product price must not be negative.
product.stock.invalid=Stock must be zero or greater.
product.period.invalid=The availability end date must not precede the start date.
~~~

Bản tiếng Việt có thể đặt trong \`messages_vi.properties\`:

~~~properties
product.name.required=Tên sản phẩm là bắt buộc.
product.price.required=Giá sản phẩm là bắt buộc.
product.price.negative=Giá sản phẩm không được âm.
product.stock.invalid=Số lượng tồn kho phải từ 0 trở lên.
product.period.invalid=Ngày kết thúc không được trước ngày bắt đầu.
~~~

Validator có thể truyền error code và default message:

~~~java
errors.rejectValue(
    "price",
    "product.price.negative",
    "Giá sản phẩm không được âm"
);
~~~

Khi thông báo được phân giải, Spring dùng error code và locale hiện tại để chọn message phù hợp. Default message là phương án dự phòng nếu không có message tương ứng.

Error code nên ổn định và có ý nghĩa theo domain. Không đưa trực tiếp dữ liệu nhạy cảm hoặc giá trị do client gửi vào message lỗi nếu không cần thiết.

## 7. Kiểm tra quy tắc liên quan nhiều field

Một số quy tắc không thể kiểm tra riêng từng field. Ví dụ, ngày kết thúc phải bằng hoặc sau ngày bắt đầu.

~~~java
public class Promotion {

    private LocalDate startsOn;
    private LocalDate endsOn;

    public LocalDate getStartsOn() {
        return startsOn;
    }

    public LocalDate getEndsOn() {
        return endsOn;
    }
}
~~~

Validator:

~~~java
@Component
public class PromotionValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Promotion.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Promotion promotion = (Promotion) target;

        LocalDate start = promotion.getStartsOn();
        LocalDate end = promotion.getEndsOn();

        if (start != null && end != null && end.isBefore(start)) {
            errors.rejectValue(
                "endsOn",
                "product.period.invalid",
                "Ngày kết thúc không được trước ngày bắt đầu"
            );
        }
    }
}
~~~

Lỗi được gắn vào \`endsOn\` để giao diện biết field nào cần sửa. Nếu quy tắc không thuộc riêng một field, có thể dùng \`errors.reject(...)\` để tạo global error.

Có thể kiểm tra điều kiện phụ thuộc nhiều trường trong cùng validator, nhưng nên giữ mỗi quy tắc rõ ràng và dễ đọc. Với quy tắc nghiệp vụ phức tạp cần truy vấn nhiều nguồn dữ liệu hoặc thay đổi trạng thái, cân nhắc đặt phần xử lý trong domain/service và để validator kiểm tra đầu vào ở phạm vi phù hợp.

## 8. Đăng ký validator cho Spring Data REST repository events

Spring Data REST có cơ chế repository event để gọi validator trước hoặc sau thao tác repository. Với kiểm tra dữ liệu trước khi tạo và cập nhật, hai event thường dùng là:

- \`beforeCreate\`: trước khi tạo tài nguyên mới.
- \`beforeSave\`: trước khi lưu thay đổi của tài nguyên hiện có.

Đăng ký validator qua \`RepositoryRestConfigurer\`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final ProductValidator productValidator;

    public RepositoryValidationConfiguration(
            ProductValidator productValidator) {
        this.productValidator = productValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener validatingListener) {

        validatingListener.addValidator("beforeCreate", productValidator);
        validatingListener.addValidator("beforeSave", productValidator);
    }
}
~~~

Spring quản lý \`ProductValidator\` như bean và inject vào cấu hình. Khi Spring Data REST phát event tương ứng, listener gọi validator đã đăng ký. \`supports\` giúp validator chỉ xử lý Product; nếu event phát sinh cho một domain type khác, validator không nhận kiểu đó.

Nếu chỉ đăng ký \`beforeCreate\`, dữ liệu tạo mới được kiểm tra nhưng cập nhật có thể không chạy cùng quy tắc. Nếu chỉ đăng ký \`beforeSave\`, thao tác tạo mới có thể không được kiểm tra theo cấu hình mong muốn. Hãy chọn event phù hợp với các thao tác API mà repository công bố.

Các tên event khác có thể gồm \`beforeLinkSave\`, \`afterCreate\`, \`afterSave\` và \`beforeDelete\`. Validator dữ liệu thường được gắn vào event trước khi lưu; event sau lưu phù hợp với xử lý sau thao tác hơn là ngăn dữ liệu không hợp lệ được ghi.

## 9. Phân biệt repository event validation và Spring MVC binding

Spring Validator cũng có thể được sử dụng trong Spring MVC controller thông qua \`WebDataBinder\`. Ví dụ:

~~~java
@Controller
public class ProductController {

    private final ProductValidator productValidator;

    public ProductController(ProductValidator productValidator) {
        this.productValidator = productValidator;
    }

    @InitBinder("product")
    void initProductBinder(WebDataBinder binder) {
        binder.addValidators(productValidator);
    }

    @PostMapping("/products")
    public String create(
            @ModelAttribute("product") Product product,
            BindingResult result) {

        if (result.hasErrors()) {
            return "products/form";
        }

        // Gọi service để xử lý dữ liệu hợp lệ.
        return "redirect:/products";
    }
}
~~~

Trong ví dụ, \`@InitBinder("product")\` đăng ký validator cho model attribute có tên product. Khi Spring MVC thực hiện binding và validation theo cấu hình của handler, lỗi được ghi vào \`BindingResult\`.

Hai cách tích hợp khác nhau:

| Cơ chế | Nơi đăng ký | Khi nào được gọi |
|---|---|---|
| Spring MVC | \`@InitBinder\` và \`WebDataBinder\` | Trong quá trình binding/validation của controller. |
| Spring Data REST | \`ValidatingRepositoryEventListener\` qua \`RepositoryRestConfigurer\` | Khi repository event được phát, ví dụ trước create hoặc save. |

Nếu ứng dụng có cả custom controller và repository endpoint tự động, có thể dùng chung validator ở hai nơi. Đừng giả định đăng ký trong \`@InitBinder\` tự động áp dụng cho Spring Data REST hoặc ngược lại.

## 10. Kết hợp Spring Validator với Bean Validation

Spring Validator (\`org.springframework.validation.Validator\`) khác với Bean Validation API (\`jakarta.validation.Validator\`). Hai API có mục tiêu gần nhau nhưng hợp đồng và cách tích hợp khác nhau.

Bean Validation thường dùng annotation trên field hoặc class:

~~~java
public class ProductRequest {

    @NotBlank
    private String name;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal price;
}
~~~

Spring Validator phù hợp khi cần viết quy tắc bằng Java, dùng service hoặc logic có điều kiện, hoặc muốn tích hợp trực tiếp với \`Errors\`.

Có thể dùng cả hai:

- Bean Validation xử lý các ràng buộc khai báo đơn giản như bắt buộc, độ dài, khoảng giá trị và định dạng.
- Spring Validator xử lý quy tắc nghiệp vụ hoặc điều kiện phụ thuộc nhiều thuộc tính.
- Cả hai nên trả lỗi nhất quán để client có thể hiểu và sửa dữ liệu.

Spring cung cấp adapter tích hợp Bean Validation với hệ thống validation của Spring, chẳng hạn \`LocalValidatorFactoryBean\`. Khi kết hợp nhiều validator, cần tránh đăng ký cùng một quy tắc hai lần gây thông báo trùng.

## 11. Lỗi validation được phản hồi cho client như thế nào?

Khi validator được gọi từ Spring Data REST và thêm lỗi vào \`Errors\`, luồng repository event có thể dừng thao tác và Spring Data REST xử lý lỗi validation thành response HTTP lỗi, thường là 400 Bad Request. Cấu trúc body chi tiết phụ thuộc phiên bản, exception handler và cấu hình ứng dụng.

Client nên dựa vào HTTP status và hợp đồng lỗi mà API công bố. Không nên giả định mọi ứng dụng đều trả cùng một JSON shape hoặc cùng tên field cho lỗi.

Với Spring MVC, controller có thể kiểm tra \`BindingResult\`:

~~~java
if (result.hasErrors()) {
    return ResponseEntity.badRequest().body(
        result.getFieldErrors().stream()
            .map(error -> Map.of(
                "field", error.getField(),
                "code", error.getCode(),
                "message", error.getDefaultMessage()
            ))
            .toList()
    );
}
~~~

Ví dụ này tạo một response lỗi đơn giản cho custom controller. Nếu ứng dụng có định dạng lỗi chung, nên dùng một DTO lỗi thống nhất hoặc \`@ControllerAdvice\` thay vì mỗi controller tự tạo một cấu trúc khác nhau.

Không trả stack trace, SQL, thông tin nội bộ hoặc dữ liệu nhạy cảm trong thông báo validation. Thông báo nên nêu field và điều kiện cần sửa, không tiết lộ chi tiết triển khai.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Validator không được gọi | Chưa đăng ký đúng repository event hoặc binder. | Kiểm tra nơi đăng ký và event tương ứng. |
| \`supports\` luôn trả false | So sánh sai class hoặc nhận nhầm kiểu domain. | Kiểm tra class truyền vào và dùng \`isAssignableFrom\` khi cần hỗ trợ lớp con. |
| ClassCastException trong \`validate\` | Validator được gọi trực tiếp với kiểu không tương thích. | Kiểm tra \`supports\` trước khi gọi và đăng ký validator đúng phạm vi. |
| Create có kiểm tra nhưng update không có | Chỉ đăng ký \`beforeCreate\`. | Đăng ký thêm \`beforeSave\` nếu cập nhật cũng cần quy tắc. |
| Lỗi không gắn đúng field | Truyền sai field path cho \`rejectValue\`. | Dùng tên property đúng với object đang validate. |
| Client không hiển thị thông báo phù hợp | Error code chưa có message hoặc locale không được cấu hình. | Bổ sung message properties và default message. |
| Một quy tắc chạy hai lần | Cùng logic được đăng ký qua nhiều cơ chế. | Xác định một nơi sở hữu quy tắc hoặc phối hợp rõ ràng. |
| Dữ liệu từ service không được kiểm tra | Repository event của Spring Data REST không phải cơ chế validation chung cho mọi đường gọi. | Gọi validator/service validation tại luồng ghi ngoài REST khi cần. |

## 13. Quy trình sử dụng validator

Khi triển khai validator cho một domain type:

1. Xác định các quy tắc đầu vào cần kiểm tra và field liên quan.
2. Tạo class triển khai \`org.springframework.validation.Validator\`.
3. Viết \`supports\` để chỉ chấp nhận class phù hợp.
4. Viết \`validate\` để kiểm tra dữ liệu và ghi lỗi vào \`Errors\`.
5. Dùng \`rejectValue\` cho lỗi theo field và \`reject\` cho lỗi tổng thể.
6. Đăng ký error code và message trong MessageSource nếu cần đa ngôn ngữ.
7. Đăng ký validator với \`beforeCreate\` và \`beforeSave\` cho repository event cần bảo vệ.
8. Đăng ký riêng với \`WebDataBinder\` nếu custom Spring MVC controller cũng cần dùng validator.
9. Xử lý lỗi validation theo hợp đồng HTTP của API.
10. Bảo đảm các đường ghi dữ liệu ngoài Spring Data REST cũng có validation ở service/domain phù hợp.

Spring Validator tách việc chọn kiểu đối tượng và kiểm tra dữ liệu thành hai trách nhiệm rõ ràng: \`supports\` quyết định validator có áp dụng cho class hay không; \`validate\` kiểm tra instance và ghi lỗi vào \`Errors\`. Đăng ký validator đúng repository event giúp Spring Data REST kiểm tra dữ liệu trước create/save, còn \`WebDataBinder\` phục vụ custom Spring MVC. Khi kết hợp với Bean Validation và validation ở service/domain, các quy tắc đầu vào được áp dụng nhất quán qua nhiều đường ghi dữ liệu.
