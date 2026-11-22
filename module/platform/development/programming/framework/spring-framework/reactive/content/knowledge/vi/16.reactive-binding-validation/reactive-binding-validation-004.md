# WebExchangeDataBinder, @InitBinder và Validator tùy biến trong Spring WebFlux

## 1. Bài toán và mục tiêu

Một endpoint WebFlux thường nhận dữ liệu từ query string, form, multipart hoặc JSON body. Ứng dụng cần chuyển những giá trị bên ngoài này thành kiểu Java, kiểm tra chúng có đúng định dạng và quy tắc nghiệp vụ hay không, rồi mới thực hiện xử lý tiếp theo.

Spring WebFlux cung cấp các cơ chế liên quan nhưng có vai trò riêng:

- **WebExchangeDataBinder**: binder chuyên cho môi trường WebFlux; lấy query parameters, form data và multipart data từ **ServerWebExchange**, chuyển chúng vào object đích.
- **@InitBinder**: điểm cấu hình binder cho một controller hoặc một nhóm controller; có thể đăng ký validator, converter, formatter, property editor và giới hạn field được phép bind.
- **org.springframework.validation.Validator**: giao diện để viết quy tắc kiểm tra dữ liệu tùy biến, độc lập với Jakarta Bean Validation.
- **@Valid / @Validated**: yêu cầu Spring áp dụng validation lên đối tượng hoặc tham số phù hợp.
- **BindingResult / Errors**: nơi chứa lỗi bind, lỗi chuyển kiểu và lỗi validation để controller có thể xử lý trực tiếp.

Luồng thường gặp:

~~~text
HTTP request
    |
    v
Query / Form / Multipart values
    |
    v
WebExchangeDataBinder
    |
    +----> chuyển đổi kiểu và bind vào DTO
    |
    v
Bean Validation + custom Validator
    |
    v
BindingResult
    |
    +----> lỗi: trả 400 / thông báo phù hợp
    |
    +----> hợp lệ: gọi service reactive
~~~

**Binding và validation là hai bước khác nhau.** Binding trả lời câu hỏi "giá trị request được chuyển vào object như thế nào?". Validation trả lời "object sau khi bind có hợp lệ theo quy tắc hay không?". Một giá trị có thể bind thành công nhưng vẫn không hợp lệ, ví dụ email có đúng kiểu String nhưng sai định dạng.

Bài học này đi từ API nền tảng đến cấu hình @InitBinder, viết Validator, phân biệt form với JSON, xử lý lỗi đúng trong WebFlux, bảo vệ mass assignment và kiểm thử bằng WebTestClient.

## 2. WebExchangeDataBinder là gì?

**WebExchangeDataBinder** nằm trong package **org.springframework.web.bind.support**. Nó kế thừa **WebDataBinder**, vốn kế thừa **DataBinder**. Đây là binder chuyên biệt cho request WebFlux, hỗ trợ bind từ:

- Query parameters trong URL.
- Form data dạng **application/x-www-form-urlencoded**.
- Multipart form data, bao gồm các part/file theo cơ chế hỗ trợ.

Các API quan trọng:

| API | Kiểu trả về | Mục đích |
| --- | --- | --- |
| **new WebExchangeDataBinder(target)** | WebExchangeDataBinder | Tạo binder cho object đích |
| **new WebExchangeDataBinder(target, objectName)** | WebExchangeDataBinder | Tạo binder có tên object rõ ràng |
| **bind(exchange)** | Mono<Void> | Bind query/form/multipart vào target theo cách reactive |
| **construct(exchange)** | Mono<Void> | Tạo target qua constructor binding; có từ Spring Framework 6.1 |
| **getValuesToBind(exchange)** | Mono<Map<String,Object>> | Lấy các giá trị sẽ dùng để bind |
| **extractValuesToBind(exchange)** | Mono<Map<String,Object>> | Tổng hợp giá trị từ query/form/multipart |
| **getBindingResult()** | BindingResult | Lấy kết quả bind và lỗi |
| **setAllowedFields(...)** | void | Chỉ cho phép bind các field được liệt kê |
| **setDisallowedFields(...)** | void | Cấm bind các field được liệt kê |
| **addValidators(...)** | void | Bổ sung validator vào binder |
| **validate(...)** | void | Chạy validator đã đăng ký |

**bind(exchange) trả Mono<Void>** vì việc đọc form hoặc multipart có thể bất đồng bộ. Hãy ghép nó vào pipeline bằng **then**, **map** hoặc **flatMap**; không gọi block trong handler.

### 2.1. Tạo binder thủ công

Ví dụ minh họa một binder cho form:

~~~java
ProfileForm target = new ProfileForm();

WebExchangeDataBinder binder =
    new WebExchangeDataBinder(target, "profileForm");

binder.setAllowedFields("displayName", "email");
binder.addValidators(profileValidator);

return binder.bind(exchange)
    .then(Mono.fromSupplier(() -> {
        binder.validate();
        return binder.getBindingResult();
    }));
~~~

Đây là snippet trong method có **ServerWebExchange exchange**, kiểu **ProfileForm** và **profileValidator** được định nghĩa ở ứng dụng. Nó thực hiện:

1. Tạo một object đích mới cho request hiện tại.
2. Tạo WebExchangeDataBinder gắn với tên object.
3. Chỉ cho phép bind hai field đã định nghĩa.
4. Đăng ký validator tùy biến.
5. Chờ bind hoàn tất.
6. Chạy validation rồi lấy BindingResult.

Khi tự tạo binder, ứng dụng phải tự đăng ký những validator cần thiết. Snippet trên chỉ đăng ký **profileValidator**; nếu muốn chạy Jakarta Bean Validation cho annotation như @NotBlank/@Email trên target, hãy đăng ký Spring Validator tương ứng với Bean Validation provider hoặc dùng đường phân giải @ModelAttribute/@Valid do framework quản lý như ví dụ hoàn chỉnh ở phần 10.

**Mỗi request phải có binder và target riêng.** Không đặt DataBinder/BindingResult trong singleton field vì chúng giữ object đích và trạng thái lỗi của từng lần bind.

### 2.2. Constructor binding trong Spring Framework 6.1+

Từ Spring Framework 6.1, WebExchangeDataBinder có thêm **construct(exchange)** để tạo target bằng constructor binding từ các giá trị request:

~~~java
WebExchangeDataBinder binder =
    new WebExchangeDataBinder(null, "profileForm");

return binder.construct(exchange)
    .then(Mono.fromSupplier(() -> {
        Object target = binder.getTarget();
        BindingResult result = binder.getBindingResult();
        return result.hasErrors() ? result : target;
    }));
~~~

Đây là snippet minh họa; trong ứng dụng thật nên dùng kiểu target cụ thể thay cho Object. Sau khi construct thành công, có thể gọi **bind(exchange)** để bind thêm các property setter cần thiết. Kiểu constructor binding phù hợp với DTO immutable/record khi contract và constructor được thiết kế rõ.

Không giả định mọi phiên bản Spring đều có construct(exchange). API này được bổ sung từ **6.1**; nếu dùng Framework cũ hơn, kiểm tra Javadoc đúng phiên bản.

### 2.3. WebExchangeDataBinder không phải JSON decoder

Một điểm dễ nhầm:

| Nguồn dữ liệu | Cơ chế thường dùng |
| --- | --- |
| Query string | WebExchangeDataBinder / @ModelAttribute / @RequestParam |
| URL-encoded form | WebExchangeDataBinder / @ModelAttribute |
| Multipart form | WebExchangeDataBinder / @ModelAttribute / @RequestPart |
| JSON request body | HttpMessageReader và HTTP message codecs qua @RequestBody |
| Validation object sau khi deserialize JSON | @Valid / @Validated và Validator tương ứng |

**JSON body được decode bởi codec**, không phải được chuyển vào target bằng cách gọi WebExchangeDataBinder.bind(exchange). Có thể dùng @Valid trên @RequestBody để Spring kiểm tra object sau khi deserialize.

## 3. Phân biệt binding, conversion và validation

Ba công việc liên quan nhưng không thay thế nhau:

1. **Binding:** lấy các giá trị đầu vào và đưa vào field/property/constructor của object.
2. **Conversion:** chuyển một giá trị từ kiểu nguồn sang kiểu đích, ví dụ String "25" thành Integer 25, hoặc chuỗi ngày thành LocalDate bằng Converter/Formatter.
3. **Validation:** kiểm tra giá trị/object theo quy tắc, ví dụ tên không rỗng, tuổi nằm trong giới hạn, email thuộc domain được chấp nhận.

Ví dụ: request gửi age=abc. Conversion sang Integer có thể thất bại; lỗi được ghi vào BindingResult. Request gửi age=-5 có thể chuyển thành Integer thành công, nhưng validation sẽ báo không hợp lệ.

| Tình huống | Binding/conversion | Validation |
| --- | --- | --- |
| age=25 | Thành công | Có thể hợp lệ |
| age=abc | Lỗi chuyển kiểu | Chưa có giá trị hợp lệ để kiểm tra tiếp |
| age=-5 | Thành công | Lỗi nếu có @Min(0) |
| email=lan@example.com | Thành công thành String | Có thể hợp lệ |
| email=not-an-email | Thành công thành String | Lỗi nếu có @Email |
| Thiếu field bắt buộc | Có thể bind null/rỗng | Lỗi nếu có @NotBlank/@NotNull |

**BindingResult** có thể chứa cả field errors và object errors. Khi cần debug, đọc **getFieldErrors()**, **getGlobalErrors()** và các mã lỗi thay vì chỉ in một thông báo chung.

## 4. @InitBinder dùng để làm gì?

**@InitBinder** đánh dấu method được gọi để cấu hình WebDataBinder trước khi Spring bind dữ liệu vào một command object hoặc chuẩn bị conversion/validation phù hợp.

Ví dụ:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
    binder.addValidators(profileValidator);
}
~~~

Method thường nhận **WebDataBinder** và trả **void**. Trong WebFlux, binder thực tế được tạo theo request exchange và có thể là **WebExchangeDataBinder**. Ta dùng kiểu WebDataBinder ở chữ ký @InitBinder để làm việc qua abstraction chung.

### 4.1. Giới hạn theo model attribute

Có thể chỉ áp dụng cho một model attribute cụ thể:

~~~java
@InitBinder("signupForm")
void initSignupBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

Khi binder được dùng cho model attribute tên **signupForm**, cấu hình này được áp dụng. Nếu không truyền tên trong @InitBinder, phương thức có thể áp dụng cho các binder phù hợp trong controller.

Tên phải khớp với model attribute được khai báo:

~~~java
@ModelAttribute("signupForm") SignupForm form
~~~

### 4.2. Phạm vi controller và @ControllerAdvice

- Đặt @InitBinder trong **@Controller** hoặc **@RestController**: cấu hình cục bộ cho controller đó.
- Đặt @InitBinder trong **@ControllerAdvice**: có thể áp dụng cho nhiều controller.
- Có thể giới hạn @ControllerAdvice bằng **basePackages**, **assignableTypes** hoặc các selector phù hợp để tránh ảnh hưởng toàn ứng dụng.

Ví dụ:

~~~java
@ControllerAdvice(basePackages = "com.example.publicapi")
public class PublicApiBindingAdvice {

    @InitBinder("signupForm")
    void initSignupForm(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }
}
~~~

Đây là snippet minh họa. Chỉ dùng global advice khi cùng một quy tắc thực sự áp dụng cho nhóm controller đó; nếu không, binder của một endpoint có thể vô tình ảnh hưởng endpoint khác.

### 4.3. Các tùy chỉnh thường dùng

~~~java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
    binder.setDisallowedFields("role", "admin", "accountStatus");
    binder.setAutoGrowCollectionLimit(64);
    binder.addValidators(signupValidator);
}
~~~

- **setAllowedFields** tạo allow-list các field được bind.
- **setDisallowedFields** cấm một số field; allow-list thường dễ kiểm soát hơn với DTO nhận dữ liệu từ bên ngoài.
- **setAutoGrowCollectionLimit** giới hạn việc tự mở rộng collection/index khi binding property path.
- **addValidators** thêm validator; không nên dùng **setValidator** nếu mục tiêu là bổ sung mà không thay validator đang có.
- **registerCustomEditor** đăng ký PropertyEditor cho kiểu cụ thể.
- **addCustomFormatter** đăng ký Formatter để parse/format kiểu dữ liệu.
- **setRequiredFields** có thể khai báo field bắt buộc ở tầng binding, nhưng validation annotation thường diễn đạt quy tắc rõ hơn cho DTO.

Không phải endpoint nào cũng cần toàn bộ cấu hình trên. Chỉ đặt giới hạn phù hợp với DTO và hợp đồng API.

## 5. Viết Validator tùy biến

Spring cung cấp interface **org.springframework.validation.Validator**:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

Hai method:

- **supports(clazz)** trả true nếu validator hiểu loại object đó.
- **validate(target, errors)** kiểm tra object và ghi lỗi vào Errors/BindingResult.

Ví dụ validator kiểm tra domain email:

~~~java
@Component
public class CompanyEmailValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null
                && email.toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.rejectValue(
                "email",
                "email.domain.blocked",
                "This email domain is not accepted."
            );
        }
    }
}
~~~

Đây là snippet dùng class **SignupForm** của ví dụ ở phần 10. **rejectValue** thêm lỗi vào field email, gồm mã lỗi và thông báo mặc định.

### 5.1. Kiểm tra class trong supports

Nếu supports trả false, Spring không dùng validator đó cho target tương ứng. Dùng:

~~~java
return SignupForm.class.isAssignableFrom(clazz);
~~~

để hỗ trợ SignupForm và lớp con của nó. Không trả true cho mọi class nếu code validate bên dưới ép kiểu cụ thể.

### 5.2. rejectValue và reject

- **errors.rejectValue("email", ...)**: lỗi gắn với field cụ thể, hữu ích để hiển thị lỗi bên cạnh input.
- **errors.reject("signup.invalid", ...)**: lỗi cấp object, không gắn với một field duy nhất.

Có thể thêm nhiều lỗi cho cùng object. Không nên dừng ở lỗi đầu tiên nếu người dùng có thể sửa nhiều trường cùng lúc và hợp đồng API cho phép trả danh sách lỗi.

### 5.3. Validator tùy biến nên đồng bộ và nhanh

Interface Validator là API đồng bộ. Nó phù hợp với quy tắc thuần dữ liệu: kiểm tra quan hệ giữa các field, chuẩn hóa logic, định dạng hoặc chính sách cục bộ.

Không gọi database/network bằng block() bên trong Validator để kiểm tra email đã tồn tại. Việc đó chặn thread và đưa I/O blocking vào bước binding. Với kiểm tra bất đồng bộ, hãy compose service reactive sau khi object đã bind và qua validation đồng bộ:

~~~java
return emailAvailability.isAvailable(form.getEmail())
    .flatMap(available -> {
        if (!available) {
            return Mono.error(
                new EmailAlreadyRegisteredException()
            );
        }
        return signupService.create(form);
    });
~~~

Đây là snippet cần service và exception ứng dụng. Quy tắc uniqueness cuối cùng vẫn nên được bảo vệ bằng unique constraint ở database vì hai request đồng thời có thể cùng vượt qua bước kiểm tra trước khi ghi.

## 6. Bean Validation và custom Validator phối hợp ra sao?

**Jakarta Bean Validation** dùng annotation như:

~~~java
@NotBlank
@Size(max = 80)
private String displayName;

@NotBlank
@Email
private String email;

@Min(18)
private int age;
~~~

Spring WebFlux có thể áp dụng Bean Validation khi handler method dùng **@Valid** hoặc **@Validated** trên command object phù hợp. Nếu binder đã có validator mặc định từ Bean Validation provider, **binder.addValidators(customValidator)** cho phép bổ sung validator tùy biến.

| Cách | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Bean Validation | Quy tắc khai báo gần field/class | @NotBlank, @Email, @Size, @Min |
| Spring Validator | Quy tắc tùy biến bằng Java | Kiểm tra domain email, quan hệ field |
| Conversion/Formatter | Chuyển kiểu và định dạng | String → LocalDate |
| Business validation reactive | Kiểm tra cần I/O | Email đã tồn tại, quota còn đủ |

**Đừng thay nhầm validator mặc định.** **addValidators(...)** bổ sung validator. **setValidator(...)** hoặc **replaceValidators(...)** có thể thay thế validator đã đăng ký; chỉ dùng khi muốn chủ động thay đổi danh sách.

### 6.1. @Valid và @Validated

- **@Valid** của Jakarta Validation kích hoạt validation lồng nhau trên object.
- **@Validated** của Spring hỗ trợ validation group và một số cách kích hoạt validation của Spring.
- **@Valid tự nó không phải constraint annotation**; nó yêu cầu kiểm tra các constraint bên trong object.
- Một constraint trực tiếp như **@NotNull** hoặc **@Min** trên tham số method có thể kích hoạt method validation ở cấp handler method.

Ví dụ:

~~~java
@PostMapping("/accounts")
public Mono<Account> create(
    @Valid @RequestBody Mono<Account> account
) {
    return account.flatMap(accountService::create);
}
~~~

WebFlux hỗ trợ reactive request body argument. Body được đọc và deserialize bằng **HttpMessageReader/codec**, sau đó object được validate. Đây là luồng khác với **WebExchangeDataBinder.bind(exchange)** dùng cho query/form/multipart.

## 7. Quy tắc xử lý lỗi validation trong WebFlux

Trong Spring Framework 6.1+, cần phân biệt hai loại exception.

### 7.1. WebExchangeBindException

Khi validation áp dụng riêng cho một tham số như @ModelAttribute, @RequestBody hoặc @RequestPart, nếu tham số là command object phù hợp, không có Errors/BindingResult ngay sau nó và không rơi vào method validation, Spring có thể ném:

**WebExchangeBindException**

Exception này chứa BindingResult, gồm lỗi field/object để ứng dụng chuyển thành response.

Ví dụ:

~~~java
@PostMapping("/accounts")
public Mono<Account> create(
    @Valid @RequestBody Account account
) {
    return accountService.create(account);
}
~~~

Nếu Account không hợp lệ, handler method có thể không được gọi; lỗi được chuyển vào exception handling của WebFlux. Thông thường lỗi bind/validation này được ánh xạ thành **400 Bad Request**.

### 7.2. BindingResult hoặc Errors ngay sau tham số

Nếu muốn tự xử lý lỗi trong handler:

~~~java
@PostMapping("/accounts")
public Mono<ResponseEntity<?>> create(
    @Valid @ModelAttribute("accountForm") AccountForm form,
    BindingResult bindingResult
) {
    if (bindingResult.hasErrors()) {
        return Mono.just(
            ResponseEntity.badRequest().body(bindingResult.getFieldErrors())
        );
    }

    return accountService.create(form)
        .map(account -> ResponseEntity.ok(account));
}
~~~

**BindingResult phải đứng ngay sau tham số cần nhận lỗi.** Khi lỗi thuộc tham số đó, Spring có thể gọi method và cung cấp BindingResult để controller quyết định response.

Nếu một tham số khác trong cùng method có lỗi validation nhưng không có Errors/BindingResult ngay sau nó, method validation vẫn có thể phát exception.

### 7.3. HandlerMethodValidationException

Khi có constraint trực tiếp trên method parameter hoặc return value, Spring có thể áp dụng **method validation** cho toàn handler method và phát:

**HandlerMethodValidationException**

Ví dụ:

~~~java
@GetMapping("/items")
public Mono<List<Item>> find(
    @RequestParam @Min(1) int page,
    @RequestParam @Max(100) int size
) {
    return itemService.find(page, size);
}
~~~

Nếu page hoặc size vi phạm constraint, lỗi thuộc method validation. Đây là cơ chế khác với validation riêng một @ModelAttribute.

Spring Framework 6.1 có hỗ trợ method validation tích hợp cho controller. Nếu controller có class-level **@Validated**, method validation có thể được thực hiện qua AOP proxy. Muốn sử dụng built-in method validation của Spring Framework 6.1 cho controller, cần bỏ @Validated cấp class theo hướng dẫn của tài liệu framework.

### 7.4. Hai exception cần xử lý thống nhất

Ứng dụng nên có chính sách cho cả:

- **WebExchangeBindException**: lỗi của một object/parameter binding.
- **HandlerMethodValidationException**: lỗi validation của các tham số/giá trị trả về ở cấp method.

Có thể xử lý bằng **@ExceptionHandler** trong controller hoặc **@ControllerAdvice**, hoặc mở rộng **ResponseEntityExceptionHandler** theo API hỗ trợ của phiên bản Spring đang dùng.

Không nên trả stack trace, tên class nội bộ hoặc raw rejected value nhạy cảm cho client. Hãy ánh xạ thành mã lỗi và thông báo ổn định.

## 8. @InitBinder với custom Validator: ví dụ cấu hình

Giả sử form đăng ký chỉ cho phép client gửi **displayName** và **email**.

~~~java
@RestController
@RequestMapping("/api")
public class SignupController {

    private final CompanyEmailValidator emailValidator;

    public SignupController(CompanyEmailValidator emailValidator) {
        this.emailValidator = emailValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
        binder.addValidators(emailValidator);
    }

    // Handler methods...
}
~~~

Ở đây:

- @InitBinder("signupForm") chỉ cấu hình binder tên signupForm.
- setAllowedFields tạo allow-list.
- addValidators thêm quy tắc domain email.
- Bean Validation annotations trên DTO vẫn có thể được thực thi qua validator tương ứng đã được cấu hình trong WebFlux.

Nếu cần đăng ký formatter:

~~~java
@InitBinder("signupForm")
void initSignupBinder(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
}
~~~

Nếu có kiểu ngày/giờ cần quy tắc phức tạp hoặc timezone rõ ràng, cân nhắc dùng **Converter** hoặc **Formatter** được quản lý bởi ConversionService thay vì tự parse chuỗi trong controller.

### 8.1. Đăng ký converter/formatter toàn cục

Nếu conversion dùng chung cho nhiều controller, có thể cấu hình qua **WebFluxConfigurer** và ConversionService thay vì lặp @InitBinder ở nhiều nơi. Ví dụ một Formatter cho LocalDate:

~~~java
public class IsoDateFormatter implements Formatter<LocalDate> {

    private final DateTimeFormatter formatter =
        DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException error) {
            ParseException exception =
                new ParseException("Expected yyyy-MM-dd", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter.format(value);
    }
}
~~~

Đây là snippet độc lập; đăng ký Formatter qua WebFlux configuration hoặc binder phù hợp. Formatter nên stateless hoặc an toàn khi dùng đồng thời. **DateTimeFormatter** là immutable và thread-safe.

## 9. Bảo mật data binding: tránh mass assignment

Data binding có thể dẫn đến lỗ hổng nếu client sửa được những field không được phép. Ví dụ entity nội bộ có các thuộc tính:

~~~java
class AccountEntity {
    private String displayName;
    private String email;
    private boolean admin;
    private String status;
    private BigDecimal balance;
}
~~~

Nếu bind trực tiếp request vào entity, client có thể cố gửi:

~~~http
POST /accounts
Content-Type: application/x-www-form-urlencoded

displayName=Lan&email=lan@example.com&admin=true&balance=999999
~~~

Nếu những property này được bind, request có thể sửa trạng thái quyền hoặc dữ liệu nhạy cảm. Đây là rủi ro **mass assignment / over-posting**.

Các biện pháp:

1. **Dùng request DTO riêng** chỉ chứa field client được phép sửa.
2. **setAllowedFields(...)** để allow-list field được bind.
3. Không dùng entity persistence làm command object cho request công khai.
4. Không tin dữ liệu role, admin, ownerId, balance, status do client gửi.
5. Kiểm tra quyền truy cập object ở service/domain layer; việc field bind hợp lệ không đồng nghĩa user có quyền sửa object đó.
6. Giới hạn độ sâu/năng lực auto-grow collection nếu có property path phức tạp.
7. Giới hạn kích thước request và multipart upload ở codec/server.
8. Kiểm tra BindingResult và các suppressed fields nếu nghiệp vụ cần phát hiện client đã cố gửi field bị cấm.
9. Dùng DTO bất biến/constructor binding khi phù hợp; tránh cho client bind trực tiếp vào graph object sâu.

### 9.1. Vì sao allow-list tốt hơn chỉ disallow một vài field?

Khi entity thêm một field mới, deny-list cũ có thể không biết field mới đó. Allow-list mặc định chỉ cho phép những field đã duyệt; field mới không tự động trở thành đầu vào được phép. Đây là cách giảm rủi ro khi model phát triển.

**getSuppressedFields()** trên BindingResult có thể giúp phát hiện các field bị chặn bởi binder. Tuy nhiên, không nhất thiết trả chi tiết suppressed field cho client; có thể ghi metric hoặc log theo chính sách bảo mật.

## 10. Ví dụ Java 17+ chạy được: form binding, @InitBinder và Validator tùy biến

Ví dụ dùng Spring Boot 3.3.5, Spring Framework 6.1.x và Java 17. Nó tạo endpoint đăng ký nhận form-urlencoded, kết hợp Jakarta Bean Validation với một Validator tùy biến để từ chối domain email không được chấp nhận.

Cấu trúc:

~~~text
webflux-binding-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/binding/
    │   │       ├── BindingApplication.java
    │   │       ├── SignupForm.java
    │   │       ├── CompanyEmailValidator.java
    │   │       └── SignupController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/binding/
                └── SignupControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. Application class

Tệp **BindingApplication.java**:

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingApplication.class, args);
    }
}
~~~

### 10.3. DTO SignupForm

Tệp **SignupForm.java**:

~~~java
package com.example.binding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank(message = "Display name is required")
    @Size(max = 80, message = "Display name is too long")
    private String displayName;

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be valid")
    private String email;

    public SignupForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

DTO chỉ có hai field được phép client nhập. Không thêm admin, role, balance hay các field nội bộ vào command object này.

### 10.4. Custom Validator

Tệp **CompanyEmailValidator.java**:

~~~java
package com.example.binding;

import java.util.Locale;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class CompanyEmailValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null
                && email.toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.rejectValue(
                "email",
                "email.domain.blocked",
                "This email domain is not accepted"
            );
        }
    }
}
~~~

Validator kiểm tra một quy tắc không tiện diễn đạt chỉ bằng annotation: domain **blocked.example** không được dùng. Nó không truy cập database hoặc mạng; validation vẫn là thao tác đồng bộ, nhanh.

### 10.5. Controller và @InitBinder

Tệp **SignupController.java**:

~~~java
package com.example.binding;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    private final CompanyEmailValidator emailValidator;

    public SignupController(CompanyEmailValidator emailValidator) {
        this.emailValidator = emailValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
        binder.addValidators(emailValidator);
    }

    @PostMapping(
        value = "/signups",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult bindingResult
    ) {
        if (bindingResult.hasErrors()) {
            List<Map<String, String>> errors =
                bindingResult.getFieldErrors().stream()
                    .map(this::toError)
                    .toList();

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("errors", errors);

            return Mono.just(
                ResponseEntity.badRequest().body(body)
            );
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "signup accepted");
        body.put("displayName", form.getDisplayName());
        body.put("email", form.getEmail());

        return Mono.just(
            ResponseEntity.accepted().body(body)
        );
    }

    private Map<String, String> toError(FieldError error) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("field", error.getField());
        result.put(
            "message",
            Objects.requireNonNullElse(
                error.getDefaultMessage(),
                "Invalid value"
            )
        );
        return result;
    }
}
~~~

Các điểm quan trọng:

- **@InitBinder("signupForm")** áp dụng cho model attribute có tên signupForm.
- **WebDataBinder** là kiểu tham số phù hợp cho method @InitBinder; WebFlux sử dụng binder chuyên biệt theo exchange.
- **setAllowedFields** giới hạn input được phép.
- **addValidators** bổ sung CompanyEmailValidator.
- **@Valid** kích hoạt Jakarta Bean Validation trên DTO.
- **BindingResult** đứng ngay sau SignupForm để controller nhận lỗi trực tiếp.
- Method vẫn trả **Mono<ResponseEntity<...>>**, giữ xử lý response trong pipeline reactive.

Nếu không có BindingResult ngay sau tham số cần validation, Spring có thể ném WebExchangeBindException khi có lỗi. Việc có BindingResult cho phép trả response lỗi theo format API của ứng dụng.

### 10.6. application.properties

~~~properties
spring.application.name=webflux-binding-demo
server.port=8080
logging.level.com.example.binding=INFO
~~~

### 10.7. Test bằng WebTestClient

Tệp **SignupControllerTest.java**:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SignupControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsValidForm() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Lan"
            ).with("email", "lan@example.com"))
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.message").isEqualTo("signup accepted")
            .jsonPath("$.email").isEqualTo("lan@example.com");
    }

    @Test
    void rejectsBeanValidationErrors() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", ""
            ).with("email", "not-an-email"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.errors").isArray();
    }

    @Test
    void rejectsCustomValidatorError() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Lan"
            ).with("email", "lan@blocked.example"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.errors[0].field").isEqualTo("email")
            .jsonPath("$.errors[0].message")
                .isEqualTo("This email domain is not accepted");
    }
}
~~~

### 10.8. Chạy ứng dụng và kiểm tra

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Gửi form hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "email=lan@example.com"
~~~

Response body:

~~~json
{
  "message": "signup accepted",
  "displayName": "Lan",
  "email": "lan@example.com"
}
~~~

Gửi email thuộc domain bị chặn:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "email=lan@blocked.example"
~~~

Response status **400 Bad Request**, body minh họa:

~~~json
{
  "errors": [
    {
      "field": "email",
      "message": "This email domain is not accepted"
    }
  ]
}
~~~

Gửi dữ liệu sai Bean Validation:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=" \
  --data-urlencode "email=not-an-email"
~~~

Response là **400 Bad Request** với danh sách field errors. Thứ tự lỗi có thể phụ thuộc validator/provider; test chỉ nên phụ thuộc field và mã/thông báo đã được định nghĩa, không dựa vào thứ tự toàn bộ danh sách nếu thứ tự không phải contract.

Chạy test:

~~~bash
mvn test
~~~

Ba test kiểm tra: bind form thành công, lỗi Bean Validation và lỗi do custom Validator. Spring Boot chạy server trên cổng ngẫu nhiên cho test.

## 11. Ví dụ binder thủ công với ServerWebExchange

Trong phần lớn controller, Spring tự tạo binder và gọi @InitBinder. Chỉ tự tạo **WebExchangeDataBinder** khi cần kiểm soát quá trình binding ở một luồng đặc biệt hoặc đang tích hợp thấp hơn controller.

Ví dụ một method xử lý query/form:

~~~java
public Mono<BindingResult> bindProfile(
    ServerWebExchange exchange,
    ProfileValidator validator
) {
    ProfileForm target = new ProfileForm();

    WebExchangeDataBinder binder =
        new WebExchangeDataBinder(target, "profileForm");

    binder.setAllowedFields("displayName", "email");
    binder.addValidators(validator);

    return binder.bind(exchange)
        .then(Mono.fromSupplier(() -> {
            binder.validate();
            return binder.getBindingResult();
        }));
}
~~~

Đây là snippet chỉ đăng ký **ProfileValidator**. Nếu target còn có annotation Jakarta như @NotBlank, binder tạo thủ công phải được bổ sung Bean Validation Spring Validator phù hợp; đoạn code không tự động kế thừa @InitBinder của một controller khác.

Có thể kiểm tra kết quả:

~~~java
return bindProfile(exchange, validator)
    .flatMap(result -> {
        if (result.hasErrors()) {
            return Mono.error(
                new InvalidProfileException(result)
            );
        }
        return profileService.save((ProfileForm) result.getTarget());
    });
~~~

Đây là snippet giả định exception và service. Trong ứng dụng thực, kiểu target nên được giữ tường minh thay vì ép kiểu Object tùy tiện. Việc chuyển lỗi thành response có thể đặt ở handler hoặc exception handler tập trung.

### 11.1. bind và construct khác nhau

- **bind(exchange)**: target đã có; lấy giá trị request và gán vào target.
- **construct(exchange)**: binder tạo target thông qua constructor binding; API có từ Spring Framework 6.1.
- Có thể **construct rồi bind** nếu muốn tạo object từ constructor arguments rồi bổ sung một số setter properties, nhưng phải giới hạn field và hiểu thứ tự xử lý.

Với DTO immutable, constructor binding giúp tránh object có trạng thái nửa khởi tạo. Với DTO JavaBean có no-arg constructor và setter, bind là cách truyền thống dễ hiểu.

## 12. JSON body và validation

Đối với JSON, dùng @RequestBody để codec đọc body thành object. Ví dụ:

~~~java
@PostMapping(
    value = "/json",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<ResponseEntity<String>> json(
    @Valid @RequestBody Mono<SignupJsonRequest> request
) {
    return request.map(value ->
        ResponseEntity.ok("accepted " + value.email())
    );
}
~~~

Đây là snippet giả định **SignupJsonRequest** có Jakarta validation constraints. WebFlux hỗ trợ reactive request-body argument, nên có thể dùng Mono<DTO>. Việc deserialize do **HttpMessageReader** và codec đảm nhiệm; validation chạy trên object đã được đọc.

Nếu dùng @RequestBody object trực tiếp thay vì Mono:

~~~java
@PostMapping("/json")
public Mono<ResponseEntity<String>> json(
    @Valid @RequestBody SignupJsonRequest request
) {
    return Mono.just(ResponseEntity.ok("accepted"));
}
~~~

Cả hai dạng đều có thể dùng trong WebFlux; dạng Mono phù hợp khi muốn compose rõ ràng với pipeline. **Nếu khai báo Errors/BindingResult để bắt lỗi tại method, request body không nên được khai báo dưới dạng Mono** theo contract validation của WebFlux; body cần được resolve trước để BindingResult có thể đứng ngay sau command object.

Không dùng WebExchangeDataBinder.bind(exchange) để đọc JSON body như form. JSON được giải mã bằng codec, và giới hạn kích thước body được quản lý qua cấu hình codec/server tương ứng.

## 13. Global Validator và local @InitBinder

Có hai phạm vi cấu hình phổ biến:

| Phạm vi | Cách đăng ký | Khi nên dùng |
| --- | --- | --- |
| Local | @InitBinder trong controller | Quy tắc chỉ áp dụng một controller hoặc model attribute |
| Nhóm controller | @ControllerAdvice + @InitBinder | Quy tắc dùng chung cho một nhóm API |
| Toàn ứng dụng | WebFluxConfigurer và Validator toàn cục | Quy tắc/validator dùng chung cho nhiều binder |
| DTO-specific | Bean Validation annotation và custom Spring Validator | Quy tắc thuộc chính DTO hoặc loại dữ liệu |

Một validator toàn cục có thể được cấu hình qua WebFlux config; có thể kết hợp nhiều validator theo chính sách. Nếu một validator chỉ dành cho SignupForm, đặt trong @InitBinder("signupForm") thường làm phạm vi dễ đọc hơn.

Không đăng ký một validator có logic ép kiểu cụ thể cho mọi object. Luôn cài **supports(...)** đúng và cân nhắc scope.

## 14. Những lỗi thường gặp và cách khắc phục

| Hiện tượng / hiểu nhầm | Cách hiểu đúng và hướng xử lý |
| --- | --- |
| Dùng WebExchangeDataBinder để parse JSON | JSON dùng HttpMessageReader/codecs qua @RequestBody; binder chủ yếu xử lý query/form/multipart |
| Nghĩ binding đồng nghĩa validation | Binding gán/chuyển kiểu; validation kiểm tra quy tắc sau đó |
| Gọi binder.bind(exchange).block() | Bind là reactive; compose Mono<Void> bằng then/map/flatMap |
| Dùng một DataBinder singleton cho mọi request | Binder giữ target và BindingResult; tạo mới theo request |
| @InitBinder không chạy | Kiểm tra model attribute name trong @InitBinder("...") và tên @ModelAttribute |
| Custom Validator không được gọi | Kiểm tra supports(clazz), scope binder và đã addValidators hay chưa |
| setValidator làm mất validator khác | Dùng addValidators khi muốn bổ sung |
| Validator gọi database bằng block | Validator là synchronous; chuyển kiểm tra I/O sang service reactive sau bind |
| Không có BindingResult ngay sau @Valid parameter | Spring có thể ném WebExchangeBindException thay vì gọi method với lỗi |
| Xử lý WebExchangeBindException nhưng bỏ qua method validation | Framework 6.1+ còn có HandlerMethodValidationException |
| Đặt @Valid lên Map/Collection rồi mong nested object luôn được kiểm tra như command object | Validation individual parameter có điều kiện; kiểm tra method validation và kiểu tham số phù hợp |
| Dùng @Valid mà không có constraint nào | @Valid chỉ kích hoạt validation lồng nhau; bản thân nó không phải constraint |
| Bind trực tiếp JPA entity | Dễ bị mass assignment; dùng request DTO và allow-list |
| Chỉ dùng deny-list cho field nhạy cảm | Field mới có thể vô tình được bind; allow-list an toàn hơn |
| Không xử lý conversion error | Kiểu dữ liệu sai được ghi trong BindingResult; trả lỗi rõ ràng |
| Đọc body hai lần qua các resolver | Body là stream; thiết kế một đường đọc và tránh consumer tranh nhau |
| Cho rằng @InitBinder tự động giới hạn quyền sửa entity | Binder chỉ giới hạn input; service vẫn phải kiểm tra authorization và business rule |
| Gọi getFormData/getMultipartData không quan tâm body lifecycle | Form và multipart có cơ chế parse/cache riêng; không đọc part content nhiều lần |
| Dùng constructor binding mà quên kiểm tra phiên bản | WebExchangeDataBinder.construct có từ Spring Framework 6.1 |
| Trả raw rejectedValue hoặc exception message nội bộ | Có thể lộ dữ liệu; trả mã lỗi và thông báo đã kiểm soát |

## 15. Checklist thiết kế binding và validation

Trước khi triển khai endpoint, hãy xác nhận:

1. Request đến từ query, form, multipart hay JSON?
2. Cơ chế phù hợp là WebExchangeDataBinder/@ModelAttribute hay codec/@RequestBody?
3. DTO chỉ chứa các field client được phép gửi?
4. Có allow-list field qua binder nếu cần?
5. Converter/Formatter có xử lý đúng định dạng và locale không?
6. Bean Validation có các constraint thiết yếu?
7. Custom Validator có supports đúng target và không thực hiện blocking I/O?
8. @InitBinder có đúng scope controller/model attribute?
9. BindingResult có đứng ngay sau tham số cần xử lý lỗi?
10. Cả WebExchangeBindException và HandlerMethodValidationException đã có chính sách xử lý?
11. Business validation bất đồng bộ đã được compose trong service reactive?
12. Authorization được kiểm tra ở tầng nghiệp vụ, không chỉ dựa vào binder?
13. Có giới hạn payload, collection auto-grow và multipart upload?
14. Có test cho thành công, lỗi conversion, lỗi bean validation, custom validation và field bị chặn?
15. Response lỗi có cấu trúc ổn định và không lộ dữ liệu nhạy cảm?

## 16. Bài tập thực hành

**Bài 1 — Binding query:** Tạo GET /api/search với @ModelAttribute SearchForm gồm keyword và page. Dùng @InitBinder để chỉ cho phép hai field này. Gửi query string và kiểm tra target.

**Bài 2 — Conversion:** Thêm LocalDate vào DTO, đăng ký Formatter cho định dạng yyyy-MM-dd. Thử ngày hợp lệ, ngày không tồn tại và định dạng sai.

**Bài 3 — Custom Validator:** Tạo validator kiểm tra startDate phải trước endDate. Dùng rejectValue cho field cụ thể và reject cho lỗi cấp object.

**Bài 4 — Validation groups:** Tạo group Create và Update. Quy định email bắt buộc khi tạo nhưng không bắt buộc khi cập nhật; dùng @Validated với group phù hợp.

**Bài 5 — BindingResult:** Tạo endpoint nhận @Valid @ModelAttribute và BindingResult ngay sau. Xác minh method được gọi khi form sai và tự trả response 400.

**Bài 6 — WebExchangeBindException:** Bỏ BindingResult khỏi endpoint thử nghiệm, gửi dữ liệu không hợp lệ và xử lý exception ở @ControllerAdvice.

**Bài 7 — Method validation:** Thêm @Min trực tiếp lên query parameter và quan sát HandlerMethodValidationException trong Spring Framework 6.1+.

**Bài 8 — Manual binder:** Tạo WebExchangeDataBinder bằng target mới, gọi bind(exchange), validate() và đọc BindingResult. So sánh với @InitBinder tự động.

**Bài 9 — Security:** Tạo entity nội bộ có field admin, gửi admin=true từ client. Đảm bảo DTO không có field này và binder chỉ cho phép displayName/email.

**Bài 10 — Reactive business rule:** Sau khi DTO qua Bean Validation và custom Validator, gọi service kiểm tra email tồn tại bằng Mono. Không block trong Validator; bảo vệ uniqueness bằng database constraint.

**Bài 11 — JSON:** Tạo @Valid @RequestBody Mono<SignupJsonRequest>, kiểm tra body sai định dạng và body vi phạm constraint. Phân biệt lỗi deserialize với lỗi validation.

**Bài 12 — Multipart:** Bind metadata form và file upload, giới hạn kích thước và xử lý part theo đúng vòng đời. Không gom file lớn vào bộ nhớ không giới hạn.

## 17. Ghi nhớ

**WebExchangeDataBinder** là binder theo ServerWebExchange, dùng cho query/form/multipart và trả kết quả bind theo reactive Mono. **@InitBinder** cấu hình binder ở phạm vi controller hoặc controller advice, bao gồm allow-list, conversion và validator. **Validator tùy biến** diễn đạt các quy tắc domain mà annotation chung không đủ.

Trong WebFlux, cần phân biệt binding/conversion với validation; dùng @Valid/@Validated đúng kiểu tham số; đặt BindingResult ngay sau tham số nếu muốn xử lý lỗi tại method; chuẩn bị cho cả WebExchangeBindException và HandlerMethodValidationException. Với JSON, dùng codec qua @RequestBody. Với kiểm tra cần I/O, giữ nó trong service reactive sau bước validation đồng bộ.

Bảo vệ DTO khỏi mass assignment, tạo binder riêng theo request, không block và kiểm thử cả dữ liệu hợp lệ lẫn các lỗi có thể xảy ra.

## 18. Tài liệu tham khảo

- Spring Framework Reference — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework Reference — WebFlux DataBinder / @InitBinder: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html
- Spring Framework API — WebExchangeDataBinder (6.1): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/bind/support/WebExchangeDataBinder.html
- Spring Framework API — WebDataBinder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework API — Validator: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Validator.html
- Spring Framework Reference — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework Reference — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/
