# Ánh xạ lỗi vào từng trường và thông báo chung

Trong module **MODEL_VIEW_CONTROLLER**, Controller tiếp nhận dữ liệu biểu mẫu, kiểm tra đầu vào và điều phối use case. Khi dữ liệu không hợp lệ hoặc nghiệp vụ từ chối thao tác, ứng dụng cần giúp người dùng hiểu điều gì cần sửa. Một lỗi gắn với trường cụ thể nên xuất hiện ngay cạnh trường đó; một lỗi liên quan đến cả biểu mẫu hoặc toàn bộ thao tác nên được trình bày thành thông báo chung.

Ánh xạ lỗi đúng vị trí giúp người dùng sửa nhanh, giảm việc gửi form nhiều lần và giữ cho quy tắc nghiệp vụ nhất quán. Trong ứng dụng Spring MVC, **BindingResult** lưu các lỗi binding và validation; **FieldError** mô tả lỗi của một trường; **ObjectError** mô tả lỗi của toàn bộ đối tượng form. View nhận các lỗi này và trình bày theo cách dễ hiểu, còn Controller giữ trách nhiệm nối kết kết quả kiểm tra với response.

## 1. Phân biệt lỗi theo trường và lỗi chung

Một biểu mẫu có thể có nhiều loại lỗi:

- **Lỗi theo trường (field error):** một giá trị riêng lẻ không đúng định dạng, thiếu, quá dài hoặc vi phạm điều kiện của trường. Ví dụ email không hợp lệ hoặc mật khẩu quá ngắn.
- **Lỗi chung của biểu mẫu (global/object error):** lỗi liên quan đến nhiều trường hoặc toàn bộ đối tượng form. Ví dụ ngày kết thúc phải sau ngày bắt đầu.
- **Lỗi nghiệp vụ của thao tác:** dữ liệu có định dạng hợp lệ nhưng không thể thực hiện hành động trong trạng thái hiện tại. Ví dụ mã khuyến mãi đã hết hạn hoặc không thể đặt chỗ ở khung giờ đã kín.
- **Lỗi hệ thống:** lỗi hạ tầng hoặc lỗi ngoài dự kiến. Người dùng cần nhận thông báo an toàn, còn chi tiết kỹ thuật được ghi log phía server.

Ví dụ form đặt lịch có các trường ngày bắt đầu, ngày kết thúc và ghi chú:

| Lỗi | Vị trí trình bày phù hợp |
| --- | --- |
| Ngày bắt đầu không đúng định dạng | Ngay dưới trường ngày bắt đầu |
| Ngày kết thúc bị bỏ trống | Ngay dưới trường ngày kết thúc |
| Ngày kết thúc sớm hơn ngày bắt đầu | Thông báo chung của form hoặc gắn vào trường ngày kết thúc nếu đó là cách sửa rõ ràng |
| Khung giờ đã kín | Thông báo chung giải thích thao tác không thể hoàn tất |
| Dịch vụ đặt lịch tạm thời không khả dụng | Thông báo lỗi chung, không tiết lộ chi tiết máy chủ |

Không nên đưa mọi lỗi vào một đoạn thông báo chung. Khi người dùng có thể sửa một trường cụ thể, hãy chỉ rõ trường đó. Ngược lại, không nên gán một lỗi tổng thể vào một trường tùy tiện nếu điều kiện liên quan đến nhiều giá trị.

## 2. Tạo đối tượng nhận dữ liệu biểu mẫu

Nên dùng một form object hoặc request DTO dành cho biểu mẫu thay vì binding trực tiếp vào entity nghiệp vụ. Form object xác định các trường người dùng được phép gửi và các ràng buộc đầu vào cơ bản.

Ví dụ form đăng ký:

~~~java
public class RegistrationForm {
    @NotBlank
    @Email
    private String email;

    @NotBlank
    @Size(min = 10, max = 72)
    private String password;

    @NotBlank
    private String displayName;

    // getter và setter
}
~~~

Các annotation như **@NotBlank**, **@Email** và **@Size** mô tả điều kiện của từng trường. Khi Spring MVC binding dữ liệu form và chạy Bean Validation, lỗi sẽ được ghi nhận trong **BindingResult**.

Form object giúp kiểm soát dữ liệu đầu vào. Nó không thay thế kiểm tra quyền hoặc quy tắc nghiệp vụ. Ví dụ, form không có trường **role** thì client không thể yêu cầu đổi role qua binding thông thường; use case vẫn cần xác định vai trò nào được phép thực hiện thao tác.

## 3. BindingResult và cách đọc lỗi

Trong Spring MVC, phương thức Controller có thể nhận đối tượng form cùng **BindingResult**:

~~~java
@PostMapping("/registrations")
public String register(
        @Valid @ModelAttribute("form") RegistrationForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "registrations/new";
    }

    registrationService.register(form);
    return "redirect:/registrations/complete";
}
~~~

**BindingResult** cần được đặt ngay sau tham số được binding để nhận lỗi tương ứng. Nếu có lỗi, Controller trả lại View của form để người dùng sửa. Nếu không có lỗi, Controller tiếp tục gọi use case.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| **hasErrors()** | Có ít nhất một lỗi binding hoặc validation |
| **hasFieldErrors("email")** | Trường email có lỗi |
| **getFieldErrors("email")** | Lấy các lỗi của trường email |
| **hasGlobalErrors()** | Có lỗi áp dụng cho toàn bộ đối tượng |
| **getGlobalErrors()** | Lấy các lỗi chung |
| **rejectValue("email", code)** | Thêm lỗi vào một trường |
| **reject(code)** | Thêm lỗi chung cho đối tượng |

Lỗi binding và lỗi validation có thể cùng xuất hiện. Ví dụ người dùng nhập chữ vào trường số nguyên; framework không chuyển đổi được giá trị nên tạo lỗi binding. Khi chuyển đổi thành công, Bean Validation mới kiểm tra các ràng buộc như giá trị tối thiểu hoặc tối đa.

## 4. Hiển thị lỗi của từng trường trong View

Với Thymeleaf, **th:field** liên kết input với thuộc tính của form object và **th:errors** hiển thị lỗi của trường đó. Ví dụ:

~~~html
<form th:action="@{/registrations}"
      th:object="${form}"
      method="post">
  <div>
    <label for="email">Email</label>
    <input id="email"
           type="email"
           th:field="*{email}"
           th:attr="aria-invalid=${#fields.hasErrors('email')}" />
    <p th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}"
       id="email-error"></p>
  </div>

  <div>
    <label for="displayName">Tên hiển thị</label>
    <input id="displayName"
           type="text"
           th:field="*{displayName}" />
    <p th:if="${#fields.hasErrors('displayName')}"
       th:errors="*{displayName}"></p>
  </div>

  <button type="submit">Đăng ký</button>
</form>
~~~

Khi email sai định dạng hoặc bị bỏ trống, thông báo xuất hiện ngay dưới trường email. Người dùng có thể nhận ra trường cần sửa mà không phải đoán từ một danh sách lỗi ở đầu trang.

View chỉ trình bày lỗi mà Controller và tầng validation cung cấp. Không nên viết lại quy tắc nghiệp vụ trong template hoặc chỉ dùng JavaScript để quyết định dữ liệu có hợp lệ hay không.

## 5. Hiển thị thông báo chung của biểu mẫu

Lỗi chung thường được thêm khi điều kiện liên quan đến nhiều trường hoặc một thao tác không thể hoàn thành. Với Spring MVC, có thể dùng **BindingResult.reject(...)** để thêm lỗi ở cấp đối tượng:

~~~java
if (form.getEndDate() != null
        && form.getStartDate() != null
        && form.getEndDate().isBefore(form.getStartDate())) {
    result.reject(
            "booking.dateRange.invalid",
            "Ngày kết thúc phải sau ngày bắt đầu."
    );
}
~~~

Thymeleaf có thể hiển thị nhóm lỗi chung ở đầu form:

~~~html
<div th:if="${#fields.hasGlobalErrors()}"
     role="alert"
     aria-live="polite">
  <p th:each="error : ${#fields.globalErrors()}"
     th:text="${error}"></p>
</div>
~~~

Một form có thể có nhiều lỗi chung. Hiển thị chúng thành danh sách giúp người dùng biết các điều kiện chưa đạt. Nếu chỉ có một thông báo, vẫn nên giữ cấu trúc nhất quán để giao diện dễ mở rộng.

## 6. Ánh xạ lỗi nghiệp vụ vào trường phù hợp

Không phải mọi lỗi đều được phát hiện trước khi gọi use case. Một số lỗi chỉ có thể biết khi kiểm tra trạng thái hiện tại hoặc dữ liệu trong hệ thống. Ví dụ email đã được sử dụng, mã giảm giá đã hết hạn hoặc khung giờ vừa được người khác đặt.

Nếu lỗi có thể được sửa bằng cách thay đổi một trường, Controller có thể dùng **rejectValue**:

~~~java
try {
    registrationService.register(form);
} catch (EmailAlreadyUsedException exception) {
    result.rejectValue(
            "email",
            "registration.email.taken",
            "Email này đã được sử dụng."
    );
    return "registrations/new";
}
~~~

Nếu lỗi liên quan đến toàn bộ thao tác, dùng **reject**:

~~~java
try {
    bookingService.create(form.toCommand());
} catch (BookingUnavailableException exception) {
    result.reject(
            "booking.slot.unavailable",
            "Khung giờ này vừa hết chỗ. Vui lòng chọn thời gian khác."
    );
    return "bookings/new";
}
~~~

Ví dụ cho thấy Controller chuyển lỗi nghiệp vụ thành lỗi giao diện. Quy tắc xác định email có bị trùng hoặc khung giờ còn chỗ vẫn thuộc về use case/Model và cần được thực thi ở server. Không chỉ kiểm tra ở trình duyệt vì trạng thái có thể thay đổi giữa lúc hiển thị form và lúc gửi form.

Với luồng công khai, cần cân nhắc việc thông báo quá cụ thể có thể giúp người khác dò tìm tài khoản. Nếu việc xác nhận email tồn tại là nhạy cảm, hãy dùng thông báo trung tính phù hợp với chính sách sản phẩm.

## 7. Lỗi liên quan đến nhiều trường

Một số điều kiện không thuộc riêng một trường. Ví dụ:

- Ngày kết thúc phải sau ngày bắt đầu.
- Mật khẩu xác nhận phải trùng mật khẩu.
- Ít nhất một trong email hoặc số điện thoại phải được cung cấp.
- Khoảng số lượng tối thiểu phải nhỏ hơn hoặc bằng số lượng tối đa.

Có hai cách trình bày thường dùng:

1. **Lỗi chung:** dùng khi điều kiện liên quan đến nhiều trường và không có một trường duy nhất chịu trách nhiệm.
2. **Lỗi gắn với trường đại diện:** dùng khi có một trường cụ thể mà người dùng nên sửa, chẳng hạn ngày kết thúc không hợp lệ so với ngày bắt đầu.

Bean Validation hỗ trợ constraint ở cấp lớp để kiểm tra nhiều thuộc tính. Ví dụ, có thể tạo annotation **@ValidDateRange** trên form và validator kiểm tra quan hệ giữa hai ngày. Khi constraint ở cấp lớp thất bại, Spring thường ghi nhận một object-level error. Nếu muốn gắn lỗi vào một trường, validator có thể xây dựng violation với property node tương ứng.

Không nên tạo nhiều lỗi trùng lặp cho cùng một điều kiện, chẳng hạn vừa báo lỗi chung “ngày không hợp lệ” vừa báo hai lỗi riêng ở cả ngày bắt đầu và ngày kết thúc nếu người dùng không biết cần sửa trường nào. Thông báo nên hướng dẫn một hành động cụ thể.

## 8. Dùng mã lỗi và MessageSource cho thông báo nhất quán

Không nên rải các câu thông báo cố định trong mọi Controller và template. Dùng mã thông báo giúp tái sử dụng, thay đổi câu chữ và hỗ trợ nhiều ngôn ngữ.

Ví dụ, Controller thêm lỗi bằng mã:

~~~java
result.rejectValue(
        "email",
        "registration.email.taken"
);
~~~

Trong file message bundle tiếng Việt, có thể khai báo:

~~~properties
registration.email.taken=Email này đã được sử dụng.
booking.dateRange.invalid=Ngày kết thúc phải sau ngày bắt đầu.
booking.slot.unavailable=Khung giờ này vừa hết chỗ. Vui lòng chọn thời gian khác.
~~~

Spring sử dụng **MessageSource** và cơ chế phân giải message code để tìm thông báo phù hợp. Có thể cung cấp bundle theo locale, ví dụ **messages_vi.properties** và **messages_en.properties**. View hiển thị thông báo đã được phân giải theo locale hiện tại.

Mã lỗi nên ổn định và mô tả nguyên nhân, còn câu chữ có thể thay đổi theo ngôn ngữ và trải nghiệm sản phẩm. Không dùng mã lỗi nội bộ của database hoặc exception làm message công khai.

## 9. Giữ lại dữ liệu người dùng đã nhập

Khi form có lỗi, người dùng không nên phải nhập lại mọi trường. BindingResult và form object cho phép View hiển thị lại các giá trị đã binding thành công.

Tuy nhiên, không phải trường nào cũng nên được điền lại:

- Có thể giữ tên, email, lựa chọn danh mục hoặc ghi chú không nhạy cảm.
- Không nên hiển thị lại mật khẩu, mã xác thực, token hoặc dữ liệu nhạy cảm sau lỗi.
- Không đưa dữ liệu bị từ chối hoặc dữ liệu không đáng tin cậy vào HTML thô.
- Không ghi toàn bộ form object vào log nếu nó chứa thông tin bí mật.

Với Thymeleaf, **th:field** thường lấy giá trị từ binding result và form object để dựng lại input. Với các trường nhạy cảm như password, hãy để input trống sau khi render lại form và yêu cầu người dùng nhập lại nếu cần.

## 10. Kết hợp lỗi trường, lỗi chung và khả năng truy cập

Thông báo lỗi cần dễ nhận biết với người dùng sử dụng chuột, bàn phím hoặc công nghệ hỗ trợ:

- Đặt thông báo cạnh trường bị lỗi và dùng câu chữ cụ thể.
- Đánh dấu trường không hợp lệ bằng **aria-invalid="true"** khi có lỗi.
- Liên kết trường với thông báo bằng **aria-describedby** khi phù hợp.
- Hiển thị tóm tắt lỗi chung ở đầu form khi có nhiều lỗi hoặc lỗi toàn biểu mẫu.
- Dùng vùng thông báo phù hợp như **role="alert"** hoặc **aria-live** để công nghệ hỗ trợ nhận biết nội dung mới.
- Không chỉ dùng màu đỏ để biểu thị lỗi; cần có văn bản hoặc biểu tượng kèm ý nghĩa.
- Khi submit thất bại, cân nhắc đưa focus đến phần tóm tắt lỗi hoặc trường đầu tiên có lỗi.

Ví dụ một trường có thể liên kết tới thông báo lỗi:

~~~html
<label for="email">Email</label>
<input id="email"
       name="email"
       aria-invalid="true"
       aria-describedby="email-help email-error" />
<small id="email-help">Dùng địa chỉ email bạn có thể truy cập.</small>
<p id="email-error">Vui lòng nhập email hợp lệ.</p>
~~~

Nếu có cả tóm tắt lỗi và lỗi cạnh trường, tránh đọc lặp quá nhiều nội dung. Tóm tắt có thể liệt kê ngắn gọn các trường cần sửa và liên kết đến từng trường.

## 11. Render lại form hay redirect khi có lỗi?

Khi form không hợp lệ, cách thường dùng là render lại cùng View trong response hiện tại để giữ BindingResult, các lỗi và dữ liệu đã nhập. Nếu redirect ngay sau lỗi, request kế tiếp không tự giữ BindingResult; muốn giữ phải dùng flash attribute hoặc cơ chế lưu tạm riêng.

Sau khi xử lý thành công một thao tác POST, có thể dùng **Post/Redirect/Get** để trình duyệt chuyển sang trang kết quả. Như vậy:

| Kết quả | Phản hồi thường dùng |
| --- | --- |
| Form không hợp lệ | Render lại form cùng lỗi |
| Quy tắc nghiệp vụ từ chối nhưng người dùng có thể sửa | Render lại form cùng lỗi phù hợp |
| Thao tác thành công | Redirect đến trang hoàn tất hoặc trang chi tiết |
| Lỗi hệ thống | Trang lỗi chung hoặc response lỗi phù hợp |

Không nên redirect sau mọi lỗi theo một quy tắc cứng. Chọn cách phản hồi dựa trên việc người dùng có cần tiếp tục sửa form hay không và loại client đang gửi request.

## 12. Phân biệt lỗi form với lỗi API

HTML form thường cần lỗi gắn với trường và thông báo chung để người dùng sửa trực tiếp. API thường trả một cấu trúc lỗi có thể đọc bằng máy, gồm mã lỗi, thông báo và danh sách lỗi theo đường dẫn trường.

Ví dụ cấu trúc JSON:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu gửi lên chưa hợp lệ.",
  "fieldErrors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Vui lòng nhập email hợp lệ."
    }
  ],
  "globalErrors": [
    {
      "code": "DATE_RANGE_INVALID",
      "message": "Ngày kết thúc phải sau ngày bắt đầu."
    }
  ]
}
~~~

Đây là một hợp đồng minh họa, không phải cấu trúc bắt buộc của HTTP. Có thể dùng **400 Bad Request** hoặc **422 Unprocessable Content** theo quy ước API đã công bố. Client có thể ánh xạ **fieldErrors** vào input tương ứng và hiển thị **globalErrors** ở đầu form.

Không trả stack trace, câu SQL, tên lớp hoặc nội dung exception thô trong lỗi API. Mã lỗi công khai nên ổn định để client không phải phân tích câu chữ nhằm quyết định hành vi.

## 13. Kiểm thử ánh xạ lỗi

Kiểm thử cần xác nhận không chỉ form bị từ chối mà lỗi được gắn đúng vị trí và View nhận đủ dữ liệu cần thiết.

Các trường hợp nên kiểm tra:

- Email trống tạo field error ở **email**.
- Email sai định dạng tạo thông báo phù hợp ở trường email.
- Ngày kết thúc trước ngày bắt đầu tạo global error hoặc lỗi ở trường được chọn.
- Khung giờ hết chỗ tạo lỗi nghiệp vụ chung.
- Form được render lại với các giá trị không nhạy cảm đã nhập.
- Trường password không được điền lại sau lỗi.
- Lỗi hệ thống không tiết lộ chi tiết nội bộ.
- Response API trả mã lỗi và đường dẫn trường đúng hợp đồng.

Ví dụ kiểm thử Spring MVC:

~~~java
@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    RegistrationService registrationService;

    @Test
    void emptyEmailIsMappedToFieldError() throws Exception {
        mvc.perform(post("/registrations")
                        .param("email", "")
                        .param("password", "long-enough-password")
                        .param("displayName", "Lan"))
                .andExpect(status().isOk())
                .andExpect(view().name("registrations/new"))
                .andExpect(model().attributeHasFieldErrors("form", "email"));
    }
}
~~~

Ví dụ minh họa kiểm tra lỗi validation được ánh xạ vào đúng thuộc tính form. Tùy cấu hình Spring Security, test POST có thể cần thêm CSRF token. Với lỗi chung hoặc lỗi nghiệp vụ, có thể mock use case ném exception tương ứng và kiểm tra **BindingResult** có global error hoặc field error đúng như thiết kế.

## 14. Quy trình xử lý lỗi cho một biểu mẫu

Khi triển khai form mới, có thể đi theo trình tự:

1. Xác định các trường, kiểu dữ liệu và ràng buộc đầu vào.
2. Tạo form object riêng với validation phù hợp.
3. Phân loại điều kiện nào là lỗi trường, điều kiện nào là lỗi nhiều trường hoặc lỗi nghiệp vụ chung.
4. Trong Controller, nhận form cùng BindingResult và kiểm tra lỗi sau binding/validation.
5. Nếu use case phát hiện lỗi nghiệp vụ, ánh xạ lỗi vào trường phù hợp bằng **rejectValue** hoặc vào form bằng **reject**.
6. Khi có lỗi, cung cấp lại dữ liệu phụ cần cho View và render form.
7. Dùng message code để hỗ trợ ngôn ngữ và giữ câu chữ nhất quán.
8. Hiển thị lỗi dễ nhận biết, gắn với input và hỗ trợ công nghệ truy cập.
9. Không điền lại trường nhạy cảm và không tiết lộ chi tiết kỹ thuật.
10. Kiểm thử cả field error, global error, dữ liệu được giữ lại và response cuối cùng.

Ví dụ, form đặt lịch có thể kiểm tra định dạng ngày ở từng trường, kiểm tra khoảng ngày ở cấp form và kiểm tra chỗ trống trong use case. Controller ánh xạ từng loại lỗi thành phản hồi phù hợp; View trình bày lỗi ngay nơi người dùng có thể hành động.

## Kết luận

Lỗi theo trường cần được hiển thị cạnh input để người dùng biết chính xác giá trị nào cần sửa; lỗi chung phù hợp với điều kiện liên quan đến nhiều trường hoặc toàn bộ thao tác. Trong Spring MVC, BindingResult, FieldError, ObjectError, rejectValue và reject giúp biểu diễn các loại lỗi này. Khi Controller ánh xạ lỗi đúng vị trí, View trình bày bằng thông báo rõ ràng và kiểm thử xác nhận cả lỗi lẫn dữ liệu được giữ lại, biểu mẫu MVC trở nên dễ sử dụng và đáng tin cậy hơn.
