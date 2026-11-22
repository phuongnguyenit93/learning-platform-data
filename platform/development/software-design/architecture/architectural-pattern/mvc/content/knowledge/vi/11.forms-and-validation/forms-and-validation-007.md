# Giữ dữ liệu người dùng đã nhập khi báo lỗi

Khi người dùng gửi một biểu mẫu web, họ kỳ vọng ứng dụng giữ lại những thông tin đã nhập nếu có lỗi. Nếu biểu mẫu bị xóa trắng sau khi một trường sai định dạng hoặc một quy tắc không được đáp ứng, người dùng phải nhập lại từ đầu. Với biểu mẫu dài như đăng ký tài khoản, tạo đơn hàng hoặc cập nhật hồ sơ, điều này gây khó chịu và làm tăng nguy cơ nhập sai.

Trong mô hình **Model–View–Controller (MVC)**, việc giữ dữ liệu biểu mẫu là một phần của luồng request và phản hồi. Controller tiếp nhận dữ liệu, thực hiện binding và validation, sau đó trả lại View cùng dữ liệu đã nhập và thông báo lỗi phù hợp. Khi hợp lệ, Controller gọi nghiệp vụ và chuyển sang bước tiếp theo.

Giữ lại dữ liệu không có nghĩa là tin tưởng hoặc lưu mọi giá trị client gửi lên. Ứng dụng cần phân biệt dữ liệu được phép hiển thị lại, dữ liệu nhạy cảm phải xóa, dữ liệu tham chiếu cần tải lại và dữ liệu chỉ được ghi vào Model nghiệp vụ sau khi đã được kiểm tra.

## 1. Vì sao cần giữ dữ liệu khi biểu mẫu có lỗi?

Hãy xem một biểu mẫu tạo tài khoản gồm họ tên, email, ngày sinh và mật khẩu. Người dùng nhập đầy đủ rồi gửi. Máy chủ phát hiện email đã được sử dụng. Nếu trang trả về một biểu mẫu trống, người dùng phải nhập lại họ tên, ngày sinh và các trường khác dù chúng không có lỗi.

Giữ lại dữ liệu đã nhập giúp:

- Người dùng chỉ cần sửa trường có lỗi.
- Các giá trị hợp lệ không bị mất khi một trường khác sai.
- Thông báo lỗi có thể được hiển thị ngay cạnh trường tương ứng.
- Trải nghiệm nhất quán hơn giữa các biểu mẫu dài hoặc nhiều bước.
- Giảm việc gửi lại request chỉ để phục hồi dữ liệu đã mất.

Đối với ứng dụng MVC render HTML ở máy chủ, dữ liệu biểu mẫu có thể được giữ trong đối tượng form hoặc request model rồi đưa lại cho View. Với API, máy chủ thường trả chi tiết lỗi theo hợp đồng JSON; client giữ trạng thái biểu mẫu hiện tại và hiển thị lỗi theo trường.

## 2. Luồng xử lý biểu mẫu trong MVC

Một luồng phổ biến khi người dùng gửi biểu mẫu là:

1. View hiển thị biểu mẫu và các giá trị ban đầu.
2. Người dùng nhập dữ liệu rồi gửi request POST.
3. Controller tiếp nhận request và binding dữ liệu vào đối tượng đầu vào.
4. Ứng dụng kiểm tra kiểu dữ liệu, định dạng và các ràng buộc đầu vào.
5. Nếu có lỗi, Controller trả lại View cùng đối tượng đã nhập và danh sách lỗi.
6. View hiển thị lại các giá trị có thể giữ, đồng thời đánh dấu trường sai và giải thích cách sửa.
7. Nếu dữ liệu hợp lệ, Controller gọi use case hoặc dịch vụ nghiệp vụ.
8. Khi thao tác thành công, ứng dụng chuyển hướng hoặc trả kết quả phù hợp.

~~~mermaid
flowchart TD
    U[Người dùng nhập biểu mẫu] --> V[View gửi POST]
    V --> C[Controller tiếp nhận request]
    C --> B[Binding và validation]
    B -->|Có lỗi| E[Giữ form data và lỗi]
    E --> R[Render lại View]
    R --> U
    B -->|Hợp lệ| A[Gọi use case / Model]
    A -->|Thành công| S[Redirect hoặc response thành công]
    A -->|Lỗi nghiệp vụ có thể sửa| E
~~~

Controller chịu trách nhiệm điều phối phản hồi. Quy tắc nghiệp vụ vẫn được kiểm tra ở Model hoặc dịch vụ nghiệp vụ. Ví dụ, binding có thể xác nhận số lượng là số nguyên dương, nhưng Model vẫn phải kiểm tra số lượng có thể cung cấp.

## 3. Dùng đối tượng form riêng cho dữ liệu đầu vào

Không nên mặc định bind mọi trường request trực tiếp vào entity hoặc đối tượng lưu trữ. Một entity có thể chứa trạng thái, quyền sở hữu, giá, mã nội bộ hoặc các trường mà client không được phép thay đổi.

Hãy tạo một form object hoặc request DTO chỉ gồm những trường người dùng được phép gửi.

Ví dụ biểu mẫu đăng ký:

~~~java
public class RegistrationForm {
    @NotBlank
    @Size(max = 100)
    private String fullName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @NotNull
    @Past
    private LocalDate birthDate;

    @NotBlank
    @Size(min = 12, max = 100)
    private String password;

    // Getter và setter
}
~~~

Các annotation minh họa ràng buộc định dạng đầu vào. Quy tắc thực tế về tuổi tối thiểu, độ dài mật khẩu, miền email hoặc chính sách tài khoản cần được xác định theo yêu cầu sản phẩm và có thể được kiểm tra thêm ở nghiệp vụ.

Form object có một số lợi ích:

- Nêu rõ các trường client được phép gửi.
- Tách hợp đồng biểu mẫu khỏi cấu trúc entity.
- Hỗ trợ binding và validation theo từng trường.
- Dễ giữ lại dữ liệu đã nhập khi trả về View.
- Giảm nguy cơ mass assignment, tức client gửi thêm trường ngoài ý muốn để sửa trạng thái nội bộ.

Với Spring MVC, có thể giới hạn các trường được bind bằng cấu hình binder khi cần. Dù dùng DTO riêng, vẫn phải xác định rõ trường nào được phép nhận từ client; không nên xem DTO là cơ chế phân quyền tự động.

## 4. Binding và validation trong Spring MVC

Spring MVC hỗ trợ binding tham số request vào đối tượng form và lưu lỗi binding/validation trong BindingResult.

Ví dụ Controller:

~~~java
@Controller
@RequestMapping("/registrations")
public class RegistrationController {
    private final RegistrationService registrationService;

    public RegistrationController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("form", new RegistrationForm());
        return "registrations/new";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult bindingResult,
            Model model
    ) {
        if (bindingResult.hasErrors()) {
            // Không giữ bí mật xác thực trong dữ liệu dùng để render lại.
            form.setPassword(null);
            loadReferenceData(model);
            return "registrations/new";
        }

        try {
            RegistrationCommand command = new RegistrationCommand(
                    form.getFullName(),
                    form.getEmail(),
                    form.getBirthDate(),
                    form.getPassword()
            );
            registrationService.register(command);
            form.setPassword(null);
            return "redirect:/registrations/success";
        } catch (EmailAlreadyRegisteredException ex) {
            form.setPassword(null);
            bindingResult.rejectValue(
                    "email",
                    "email.alreadyRegistered",
                    "Email này đã được sử dụng."
            );
            loadReferenceData(model);
            return "registrations/new";
        }
    }

    private void loadReferenceData(Model model) {
        model.addAttribute("countries", registrationService.getCountries());
    }
}
~~~

Use case nhận một command có cấu trúc riêng thay vì phụ thuộc trực tiếp vào form object của tầng web:

~~~java
public record RegistrationCommand(
        String fullName,
        String email,
        LocalDate birthDate,
        String rawPassword
) {}
~~~

Có một chi tiết quan trọng: tham số BindingResult phải đặt ngay sau tham số được kiểm tra bằng @Valid hoặc @Validated. Nhờ đó, Controller nhận được lỗi binding và validation tương ứng.

Khi có lỗi, phương thức trả trực tiếp tên View. Form object và BindingResult vẫn thuộc request hiện tại, nên View có thể đọc lại các giá trị người dùng đã nhập cùng lỗi của từng trường. Không cần tạo một form object mới trong nhánh lỗi vì thao tác đó sẽ làm mất dữ liệu đã bind.

Trong ví dụ, Controller cũng tải lại danh sách quốc gia. Những dữ liệu tham chiếu như danh sách lựa chọn, danh mục hoặc tùy chọn dropdown thường cần được nạp lại mỗi khi render biểu mẫu, kể cả khi có lỗi.

## 5. Hiển thị lại giá trị và lỗi trong View

Với Thymeleaf, có thể liên kết form object bằng th:object, liên kết từng trường bằng th:field và hiển thị lỗi bằng th:errors.

~~~html
<form th:action="@{/registrations}" th:object="${form}" method="post">
    <div>
        <label for="fullName">Họ và tên</label>
        <input id="fullName" type="text" th:field="*{fullName}">
        <small th:if="${#fields.hasErrors('fullName')}"
               th:errors="*{fullName}"></small>
    </div>

    <div>
        <label for="email">Email</label>
        <input id="email" type="email" th:field="*{email}">
        <small th:if="${#fields.hasErrors('email')}"
               th:errors="*{email}"></small>
    </div>

    <div>
        <label for="birthDate">Ngày sinh</label>
        <input id="birthDate" type="date" th:field="*{birthDate}">
        <small th:if="${#fields.hasErrors('birthDate')}"
               th:errors="*{birthDate}"></small>
    </div>

    <div>
        <label for="password">Mật khẩu</label>
        <input id="password" name="password" type="password">
        <small th:if="${#fields.hasErrors('password')}"
               th:errors="*{password}"></small>
    </div>

    <button type="submit">Tạo tài khoản</button>
</form>
~~~

Thymeleaf dùng BindingResult để lấy giá trị đã bind và giá trị bị từ chối khi chuyển kiểu thất bại. Vì vậy, nếu người dùng nhập một chuỗi không chuyển được thành số hoặc ngày, thông tin lỗi binding có thể được hiển thị cùng dữ liệu phù hợp để họ sửa. Riêng trường mật khẩu được render bằng input không có thuộc tính value; cách này giữ thông báo lỗi nhưng không đưa rejected value trở lại HTML.

Với trường văn bản thông thường, th:field giúp giữ lại giá trị. Với select, checkbox hoặc radio, cần liên kết đúng kiểu dữ liệu và cung cấp danh sách lựa chọn để View xác định phần tử nào được chọn. Không nên tự tạo HTML từ chuỗi dữ liệu người dùng mà bỏ qua cơ chế escape của template engine.

## 6. Phân biệt lỗi binding, validation và lỗi nghiệp vụ

Không phải mọi lỗi đều xuất hiện ở cùng một bước. Phân biệt chúng giúp quyết định dữ liệu nào cần giữ và cách hiển thị phù hợp.

| Loại lỗi | Ví dụ | Nơi phát hiện | Cách phản hồi |
|---|---|---|---|
| Binding/conversion | Ngày nhập không đúng định dạng; số lượng là chữ | Bộ binding của MVC | Giữ giá trị bị từ chối và hiển thị lỗi theo trường |
| Validation đầu vào | Email trống, tên quá dài, ngày sinh không hợp lệ | Validator trên form DTO | Trả lại form cùng các lỗi |
| Quy tắc nghiệp vụ | Email đã đăng ký; mã khuyến mãi hết hạn; sản phẩm ngừng bán | Model hoặc dịch vụ nghiệp vụ | Gắn lỗi phù hợp vào trường hoặc thông báo chung |
| Lỗi kỹ thuật | Cơ sở dữ liệu không khả dụng | Hạ tầng | Thông báo an toàn; ghi log và mã tương quan |

Binding và validation thường có thể được sửa ngay trên biểu mẫu. Lỗi nghiệp vụ cũng có thể được trình bày để người dùng điều chỉnh, nhưng không phải lúc nào cũng gắn với một trường cụ thể. Ví dụ, đơn hàng không thể tạo vì sản phẩm vừa hết hàng có thể cần thông báo chung ở đầu biểu mẫu.

Lỗi kỹ thuật như mất kết nối cơ sở dữ liệu không nên hiển thị stack trace hoặc chi tiết hạ tầng cho người dùng. Có thể giữ lại dữ liệu không nhạy cảm trong một biểu mẫu khi lỗi tạm thời xảy ra, nhưng cần thiết kế cẩn thận để không vô tình giữ dữ liệu bí mật hoặc lặp lại thao tác ghi.

## 7. Giữ dữ liệu khi có lỗi nghiệp vụ

Một biểu mẫu có thể vượt qua validation đầu vào nhưng thất bại khi thực hiện nghiệp vụ. Ví dụ email có định dạng hợp lệ nhưng đã được tài khoản khác sử dụng.

Controller có thể thêm lỗi vào BindingResult:

~~~java
bindingResult.rejectValue(
        "email",
        "email.alreadyRegistered",
        "Email này đã được sử dụng."
);
return "registrations/new";
~~~

Hoặc thêm lỗi chung cho toàn biểu mẫu:

~~~java
bindingResult.reject(
        "registration.notAvailable",
        "Hiện chưa thể tạo tài khoản. Vui lòng kiểm tra lại thông tin."
);
return "registrations/new";
~~~

View có thể hiển thị lỗi chung:

~~~html
<div th:if="${#fields.hasGlobalErrors()}">
    <p th:each="error : ${#fields.globalErrors()}"
       th:text="${error}"></p>
</div>
~~~

Lỗi nghiệp vụ nên được ánh xạ sang mã lỗi hoặc thông điệp có ý nghĩa ổn định. Không nên để View tự suy luận từ chuỗi exception kỹ thuật. Trong hệ thống đa ngôn ngữ, mã lỗi có thể được ánh xạ sang thông điệp theo locale.

## 8. Khi nào trả lại View trực tiếp, khi nào dùng Redirect?

Đây là điểm quan trọng khi muốn giữ dữ liệu biểu mẫu.

### 8.1. Khi validation thất bại: thường trả lại View trực tiếp

Sau một POST có lỗi binding hoặc validation, Controller thường render lại View ngay trong request hiện tại:

~~~java
if (bindingResult.hasErrors()) {
    return "registrations/new";
}
~~~

Cách này giữ được form object, BindingResult và giá trị bị từ chối. Nếu chuyển hướng ngay, request mới sẽ không tự mang theo những dữ liệu này.

### 8.2. Khi thao tác thành công: dùng Post/Redirect/Get

Sau khi ghi dữ liệu thành công, ứng dụng thường redirect đến trang kết quả:

~~~java
registrationService.register(form);
return "redirect:/registrations/success";
~~~

Mẫu Post/Redirect/Get (PRG) giúp việc tải lại trang kết quả không gửi lại biểu mẫu POST, từ đó giảm nguy cơ tạo thao tác lặp do refresh.

### 8.3. Nếu bắt buộc redirect khi có lỗi

Trong một số thiết kế, có thể cần redirect sau POST ngay cả khi lỗi. Khi đó phải chủ động chuyển dữ liệu cần thiết sang request kế tiếp, thường bằng flash attributes hoặc một draft được lưu ở phía máy chủ.

Với Spring MVC, có thể dùng RedirectAttributes:

~~~java
redirectAttributes.addFlashAttribute("form", form);
redirectAttributes.addFlashAttribute(
        "formErrors",
        validationMessages
);
return "redirect:/registrations/new";
~~~

Flash attribute thường được lưu tạm để dùng trong request kế tiếp rồi bị loại bỏ. Tuy nhiên, nó không tự tái tạo đầy đủ BindingResult nếu ứng dụng cần hiển thị chính xác lỗi theo trường và rejected value. Muốn giữ lỗi binding, cần lưu và phục hồi cả thông tin lỗi tương ứng, hoặc dùng một mô hình lỗi riêng có cấu trúc.

Không nên đưa toàn bộ dữ liệu biểu mẫu nhạy cảm vào URL query string. URL có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, analytics hoặc header referrer.

## 9. Các trường không nên điền lại

Giữ dữ liệu người dùng đã nhập không đồng nghĩa với việc điền lại mọi trường. Một số dữ liệu cần được xóa hoặc yêu cầu nhập lại vì lý do bảo mật.

| Loại trường | Có nên điền lại? | Lý do |
|---|---|---|
| Họ tên, địa chỉ, ghi chú | Thường có | Không phải bí mật xác thực; giúp tránh nhập lại |
| Email, số điện thoại | Thường có | Người dùng cần sửa giá trị sai hoặc xác nhận |
| Mật khẩu và xác nhận mật khẩu | Không | Không lưu hoặc phản chiếu bí mật xác thực vào HTML |
| Mã OTP, mã khôi phục | Không | Mã ngắn hạn, nhạy cảm và có thể đã hết hiệu lực |
| Số thẻ, CVV hoặc thông tin thanh toán bí mật | Không | Dữ liệu tài chính nhạy cảm; tuân thủ quy trình của cổng thanh toán |
| Token CSRF, session hoặc access token | Không đưa vào form object | Được quản lý bởi cơ chế bảo mật riêng |
| File upload | Không thể tự điền lại | Trình duyệt không cho phép đặt lại giá trị file input bằng HTML |

Đặc biệt, không ghi mật khẩu hoặc OTP vào flash attribute, log, session draft hay thông báo lỗi. Trong ví dụ Controller, mật khẩu được xóa khỏi form object trước khi render lại biểu mẫu có lỗi; View cũng để trường password trống. Khi use case thành công, mật khẩu thô cần được xử lý theo chính sách xác thực của ứng dụng (chẳng hạn băm bằng thuật toán dành cho mật khẩu) và không được lưu ở dạng rõ. Nếu người dùng nhập sai một trường nhạy cảm, yêu cầu họ nhập lại trường đó.

## 10. Bảo vệ dữ liệu khi render lại biểu mẫu

Giữ dữ liệu cũng cần bảo đảm dữ liệu không trở thành nội dung thực thi trong trình duyệt.

### 10.1. Escape đầu ra

Nếu người dùng nhập chuỗi chứa HTML hoặc JavaScript, View phải escape theo đúng ngữ cảnh. Ví dụ tên hiển thị chứa chuỗi thẻ HTML phải được coi là văn bản, không được render như markup tùy ý.

Với Thymeleaf, dùng th:text cho văn bản thông thường thay vì th:utext nếu không có nhu cầu hiển thị HTML đã được làm sạch và kiểm soát. Cơ chế escape giúp giảm nguy cơ cross-site scripting (XSS).

### 10.2. Không tin hidden field

Hidden field có thể giữ một giá trị như mã bản nháp hoặc return path, nhưng người dùng vẫn có thể sửa nó. Không dùng hidden field làm nguồn sự thật cho giá, vai trò, chủ sở hữu, trạng thái đơn hàng hoặc quyền hạn.

Nếu cần giữ một định danh, máy chủ phải xác thực rằng người dùng hiện tại được phép thao tác với tài nguyên đó.

### 10.3. Giới hạn trường được bind

Form DTO riêng là lớp bảo vệ đầu tiên. Với Spring MVC, có thể dùng WebDataBinder để giới hạn các trường được phép bind:

~~~java
@InitBinder("form")
public void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "fullName",
            "email",
            "birthDate",
            "password"
    );
}
~~~

Tên object trong @InitBinder phải khớp với tên được dùng trong @ModelAttribute. Cần kiểm tra hành vi binding của framework và không xem danh sách allowed fields là thay thế cho authorization hoặc quy tắc nghiệp vụ.

### 10.4. Giữ token CSRF bằng cơ chế bảo mật

Biểu mẫu POST cần gửi token CSRF nếu ứng dụng sử dụng cơ chế này. Framework thường cung cấp token qua model hoặc tích hợp tự động với template. Không lưu token vào DTO nghiệp vụ hoặc flash data chỉ để phục hồi biểu mẫu; hãy để cơ chế bảo mật phát hành và xác minh token theo đúng vòng đời.

## 11. Select, checkbox, radio và dữ liệu tham chiếu

Các trường lựa chọn cần được render với cả giá trị đã gửi và danh sách lựa chọn hiện hành.

Ví dụ, biểu mẫu chọn quốc gia:

~~~html
<select th:field="*{countryCode}">
    <option value="">-- Chọn quốc gia --</option>
    <option th:each="country : ${countries}"
            th:value="${country.code}"
            th:text="${country.name}">
    </option>
</select>
<small th:if="${#fields.hasErrors('countryCode')}"
       th:errors="*{countryCode}"></small>
~~~

Controller cần nạp lại countries khi render biểu mẫu có lỗi. Nếu danh sách lựa chọn không có trong model, View có thể không hiển thị được lựa chọn cũ dù form object vẫn còn giá trị.

Với checkbox nhiều lựa chọn, cần thống nhất kiểu dữ liệu là danh sách mã, tập hợp hay một giá trị boolean. Với radio, mỗi lựa chọn cần có cùng tên trường và giá trị ổn định. Không nên lưu nhãn đã dịch làm giá trị gửi lên; hãy dùng mã ổn định rồi ánh xạ sang nhãn hiển thị.

## 12. File upload và biểu mẫu nhiều bước

### 12.1. File upload

Trình duyệt không cho phép máy chủ tự điền lại giá trị của input type=file. Nếu một biểu mẫu upload ảnh có lỗi ở trường mô tả, người dùng có thể phải chọn lại file.

Một số cách giảm bất tiện:

- Hiển thị rõ file nào đã được chọn nếu request đã tải lên vùng tạm an toàn.
- Giữ file tạm bằng mã định danh ngẫu nhiên gắn với phiên hoặc người dùng đã xác thực.
- Áp dụng giới hạn kích thước, loại nội dung và thời hạn lưu file tạm.
- Xóa file tạm khi hoàn tất, hết hạn hoặc người dùng hủy biểu mẫu.
- Không tin tên file, phần mở rộng hoặc content type do client tự khai báo.

Nếu dùng upload tạm, mã định danh file phải được kiểm tra quyền sở hữu và không được cho phép truy cập file của người khác.

### 12.2. Biểu mẫu nhiều bước

Một quy trình như đặt hàng có thể gồm địa chỉ giao hàng, phương thức vận chuyển và thanh toán. Nếu mỗi bước là một request riêng, dữ liệu chưa hoàn tất có thể được giữ trong draft phía máy chủ hoặc kho lưu trữ tạm.

Các nguyên tắc cần áp dụng:

- Gắn draft với người dùng hoặc session đã xác thực.
- Có thời hạn hết hiệu lực và cơ chế xóa dữ liệu không còn cần thiết.
- Kiểm tra lại dữ liệu ở từng bước và trước khi xác nhận cuối cùng.
- Không lưu thông tin bí mật như CVV hoặc OTP trong draft.
- Không tin các trường hidden mà client gửi lại; đối chiếu với draft phía máy chủ.
- Chỉ tạo hoặc cập nhật trạng thái nghiệp vụ chính thức khi use case xác nhận thành công.

Với dữ liệu nhạy cảm, nên dùng token hoặc reference do hệ thống thanh toán cấp thay vì giữ trực tiếp dữ liệu thẻ.

## 13. Giữ dữ liệu khi dùng JSON API

Với API, máy chủ không render HTML nhưng vẫn cần trả lỗi có cấu trúc để client biết trường nào không hợp lệ.

Ví dụ response validation:

~~~json
{
  "type": "validation_error",
  "message": "Vui lòng kiểm tra lại thông tin.",
  "fieldErrors": {
    "email": "Email này đã được sử dụng.",
    "birthDate": "Ngày sinh không hợp lệ."
  }
}
~~~

Client giữ form state hiện tại, đánh dấu các trường trong fieldErrors và cho phép người dùng sửa. Máy chủ không cần gửi lại toàn bộ dữ liệu nhạy cảm mà client đã gửi.

Hợp đồng lỗi API nên có mã ổn định, tên trường nhất quán và thông điệp phù hợp. Không nên yêu cầu client phân tích chuỗi exception hoặc stack trace để xác định lỗi.

## 14. Kiểm thử việc giữ dữ liệu biểu mẫu

Kiểm thử nên xác minh cả lỗi và dữ liệu được giữ lại, không chỉ kiểm tra status code.

### Kiểm thử Controller

- Khi email sai định dạng, Controller trả lại đúng View.
- Form object vẫn chứa các trường hợp lệ đã nhập.
- BindingResult có lỗi ở đúng trường.
- Lỗi nghiệp vụ được gắn đúng field hoặc global error.
- Các danh sách tham chiếu như countries được nạp lại.
- Khi thành công, Controller chuyển hướng theo PRG.

### Kiểm thử View

- Trường văn bản hiển thị lại giá trị đã nhập.
- Select, checkbox và radio giữ đúng lựa chọn.
- Lỗi được hiển thị cạnh trường hoặc ở đầu biểu mẫu.
- Giá trị người dùng nhập được escape.
- Mật khẩu, OTP và dữ liệu thanh toán bí mật không xuất hiện trong HTML.

### Kiểm thử bảo mật

- Trường ngoài allowlist không thể bind vào đối tượng đầu vào.
- Hidden field bị sửa không vượt qua kiểm tra quyền hoặc quy tắc.
- Token CSRF được xử lý theo cấu hình bảo mật.
- File tạm không thể được truy cập bởi người dùng khác.

### Kiểm thử tích hợp

Gửi một request có nhiều trường hợp lệ và một trường sai, sau đó kiểm tra phản hồi HTML hoặc JSON. Xác minh dữ liệu hợp lệ được giữ, dữ liệu nhạy cảm không bị phản chiếu và thao tác ghi nghiệp vụ chưa được thực hiện khi validation thất bại.

## 15. Những lỗi thiết kế thường gặp

### Tạo form object mới khi có lỗi

Nếu Controller khởi tạo một đối tượng trống trước khi trả lại View, dữ liệu đã bind có thể bị mất. Hãy dùng lại đối tượng nhận từ request và BindingResult tương ứng.

### Redirect ngay sau validation lỗi mà không chuyển dữ liệu

Redirect tạo request mới. Form object và BindingResult của request POST không tự tồn tại trong request GET. Chỉ dùng redirect nếu có cơ chế flash hoặc draft được thiết kế rõ.

### Chỉ giữ giá trị mà quên nạp danh sách lựa chọn

Form object có thể còn countryCode nhưng View không có danh sách countries để render. Hãy chuẩn bị lại dữ liệu tham chiếu mỗi lần trả biểu mẫu.

### Bind trực tiếp entity

Client có thể gửi thêm các trường ngoài giao diện như status, ownerId hoặc price. Hãy dùng form DTO giới hạn trường và kiểm tra quyền ở máy chủ.

### Điền lại trường bí mật

Không đưa mật khẩu, OTP, CVV hoặc token vào HTML, log, flash data hay draft. Yêu cầu nhập lại khi cần.

### Dùng chuỗi lỗi kỹ thuật trực tiếp trong View

Exception có thể chứa thông tin nội bộ hoặc không thân thiện với người dùng. Hãy ánh xạ sang mã lỗi và thông điệp phù hợp.

### Lưu dữ liệu chưa xác nhận thành trạng thái nghiệp vụ

Giữ dữ liệu biểu mẫu trong request hoặc draft không đồng nghĩa với việc đã chấp nhận dữ liệu đó vào Model nghiệp vụ. Chỉ cập nhật trạng thái chính thức sau khi use case xác nhận hợp lệ.

## 16. Checklist review biểu mẫu

- [ ] Biểu mẫu bind vào form object hoặc DTO có trường được phép gửi.
- [ ] Controller giữ lại form object và BindingResult khi có lỗi.
- [ ] BindingResult đặt ngay sau tham số có @Valid hoặc @Validated.
- [ ] View liên kết trường bằng cơ chế binding phù hợp và hiển thị lỗi theo trường.
- [ ] Các danh sách lựa chọn được nạp lại khi render lỗi.
- [ ] Lỗi binding, validation, nghiệp vụ và kỹ thuật được phân biệt.
- [ ] Redirect chỉ được dùng khi có cơ chế chuyển dữ liệu/lỗi phù hợp.
- [ ] PRG được áp dụng sau thao tác thành công khi phù hợp.
- [ ] Mật khẩu, OTP, CVV và token không được điền lại hoặc ghi log.
- [ ] Dữ liệu động được escape khi render.
- [ ] Hidden field và dữ liệu client gửi lên vẫn được kiểm tra ở máy chủ.
- [ ] File upload và draft nhiều bước có quyền truy cập, thời hạn và cơ chế dọn dẹp.
- [ ] Có kiểm thử xác minh cả giá trị được giữ và dữ liệu không được phép phản chiếu.

## Kết luận

Giữ dữ liệu người dùng đã nhập khi báo lỗi giúp biểu mẫu dễ sửa và giảm thao tác lặp. Trong MVC, Controller nên giữ form object cùng lỗi binding/validation và trả lại View trong request hiện tại; View liên kết trường để hiển thị giá trị cũ và lỗi tương ứng. Khi thao tác thành công, PRG giúp tránh gửi lại POST khi tải lại trang. Việc giữ dữ liệu cần có giới hạn: dùng DTO riêng, nạp lại dữ liệu tham chiếu, escape đầu ra, không điền lại trường bí mật và kiểm tra mọi giá trị ở phía máy chủ trước khi cập nhật Model nghiệp vụ.
