# Kiểm tra cấu trúc dữ liệu tại ranh giới giao diện

## Mục tiêu

Ranh giới giao diện là nơi dữ liệu từ bên ngoài đi vào ứng dụng: người dùng gửi biểu mẫu HTML, frontend gửi JSON, hoặc một client gọi API. Dữ liệu ở ranh giới này chưa đáng tin cậy. Nó có thể thiếu trường, sai kiểu, vượt giới hạn, chứa định dạng không hợp lệ hoặc được gửi với mục đích khác với thiết kế ban đầu.

Trong MVC, Controller và các thành phần binding/validation của framework chịu trách nhiệm kiểm tra dữ liệu đầu vào ở ranh giới. Việc kiểm tra này giúp phát hiện sớm lỗi cấu trúc và trả phản hồi dễ hiểu cho client. Những quy tắc nghiệp vụ như một khóa học còn chỗ hay người dùng có quyền đăng ký hay không vẫn cần được thực thi ở application service và Model/domain.

Bài học này tập trung vào cách xác định hợp đồng đầu vào, kiểm tra kiểu và cấu trúc, xác thực nhiều trường, hiển thị lỗi, bảo vệ ranh giới và kiểm thử. Các ví dụ sử dụng Java, Spring MVC và Jakarta Bean Validation.

Sau khi học, người học có thể:

- Phân biệt parsing/binding, validation cấu trúc và quy tắc nghiệp vụ.
- Thiết kế request DTO hoặc form object với giới hạn dữ liệu rõ ràng.
- Kiểm tra kiểu, trường bắt buộc, độ dài, miền giá trị và dữ liệu lồng nhau.
- Xử lý quy tắc phụ thuộc nhiều trường mà không đưa nghiệp vụ vào template.
- Trả lỗi phù hợp cho form HTML và API JSON.
- Ngăn mass assignment và các đầu vào vượt quá phạm vi hợp đồng.
- Kiểm thử validation ở cả mức đối tượng và HTTP endpoint.

## 1. Vì sao phải kiểm tra dữ liệu tại ranh giới?

Giả sử một người học gửi biểu mẫu đăng ký khóa học với các trường:

- Mã khóa học.
- Địa chỉ email.
- Số người tham gia.
- Ngày bắt đầu.

Trình duyệt có thể kiểm tra một số điều kiện như trường bắt buộc, kiểu email hoặc giá trị số. Tuy nhiên, client có thể bị tắt JavaScript, dùng một công cụ HTTP khác, sửa HTML hoặc gửi request thủ công. Vì vậy, server phải tự kiểm tra mọi dữ liệu đến từ bên ngoài.

Dữ liệu không hợp lệ có thể gây ra nhiều vấn đề:

- Không chuyển đổi được chuỗi thành số, ngày hoặc mã định danh.
- Gây lỗi khi lưu dữ liệu do vượt độ dài cột hoặc vi phạm ràng buộc.
- Làm giao diện hiển thị sai khi trường bắt buộc bị thiếu.
- Tạo đầu vào bất thường cho các phép tính.
- Khiến endpoint xử lý những trường mà client không được phép thay đổi.
- Tăng tải hoặc tiêu tốn tài nguyên nếu request quá lớn.

Kiểm tra tại ranh giới giúp ứng dụng từ chối dữ liệu sai cấu trúc trước khi dữ liệu đi sâu vào các lớp xử lý. Nó cũng tạo ra một hợp đồng rõ ràng: client biết cần gửi trường nào, kiểu gì, giới hạn bao nhiêu và lỗi được trả ra sao.

### Client-side validation và server-side validation

Client-side validation cải thiện trải nghiệm người dùng bằng cách báo lỗi sớm, chẳng hạn đánh dấu trường email chưa đúng định dạng ngay khi nhập. Server-side validation bảo vệ ứng dụng và bảo đảm mọi client đều tuân theo cùng hợp đồng.

Hai phía có thể cùng kiểm tra một số điều kiện, nhưng kết quả từ trình duyệt không được xem là bằng chứng dữ liệu hợp lệ. Server luôn phải kiểm tra lại.

## 2. Phân biệt parsing, validation cấu trúc và quy tắc nghiệp vụ

Các bước kiểm tra đầu vào có mục đích khác nhau. Tách chúng giúp chọn đúng vị trí xử lý và trả đúng loại lỗi.

| Bước | Câu hỏi | Ví dụ | Nơi thường xử lý |
|---|---|---|---|
| Parsing / binding | Có đọc và chuyển dữ liệu thành kiểu mong muốn được không? | Chuỗi abc không chuyển được thành số nguyên; JSON sai cú pháp | HTTP message converter, data binder, Controller boundary |
| Validation cấu trúc | Giá trị có đúng ràng buộc của hợp đồng đầu vào không? | Email không rỗng; số người tham gia từ 1 đến 4; mã không vượt 20 ký tự | Request DTO, form object, Bean Validation |
| Quy tắc nghiệp vụ | Thao tác có hợp lệ trong trạng thái hiện tại của hệ thống không? | Khóa học còn chỗ; đợt đăng ký đang mở; người học chưa đăng ký trước đó | Application service, domain model hoặc domain service |
| Phân quyền | Người gọi có được thực hiện thao tác trên tài nguyên này không? | Người dùng chỉ sửa hồ sơ của chính mình | Security layer và application service |

Ví dụ, attendeeCount có thể phải là số nguyên từ 1 đến 4. Đây là ràng buộc cấu trúc. Nhưng nếu khóa học chỉ còn một chỗ, yêu cầu đăng ký bốn người có thể đúng kiểu và đúng miền giá trị biểu mẫu nhưng vẫn vi phạm nghiệp vụ. Quy tắc sức chứa phải được kiểm tra trong ca sử dụng dựa trên dữ liệu hiện tại.

Tương tự, courseCode có thể đúng định dạng nhưng khóa học không tồn tại hoặc đã đóng đăng ký. Không nên đưa truy vấn cơ sở dữ liệu vào annotation validation chỉ để kiểm tra những điều kiện phụ thuộc trạng thái hệ thống. Hãy giữ kiểm tra cấu trúc ở ranh giới và kiểm tra nghiệp vụ tại nơi thực thi ca sử dụng.

### Validation không phải là phân quyền

Một request có thể chứa mọi trường hợp lệ nhưng người gửi vẫn không có quyền thao tác. Ví dụ, một profileId đúng định dạng UUID không chứng minh người dùng được phép sửa hồ sơ đó. Server phải xác thực danh tính và kiểm tra quyền trên tài nguyên độc lập với validation dữ liệu.

## 3. Định nghĩa hợp đồng đầu vào bằng DTO hoặc form object

Không nên bind trực tiếp request vào entity lưu trữ. Entity thường có nhiều thuộc tính nội bộ như trạng thái, người tạo, thời điểm thanh toán hoặc quan hệ với các đối tượng khác. Nếu client có thể gửi những trường này, ứng dụng có nguy cơ cho phép sửa dữ liệu ngoài ý muốn.

Thay vào đó, hãy tạo một request DTO hoặc form object chỉ chứa các trường mà thao tác cụ thể cho phép.

Ví dụ:

    public record CreateRegistrationRequest(
            String courseCode,
            String email,
            Integer attendeeCount,
            LocalDate startDate) {
    }

DTO này thể hiện hợp đồng tạo đăng ký. Nó không có registrationStatus, createdBy, paidAt hoặc approvedAt, vì client không được tự quyết định những giá trị đó.

### Mỗi thao tác có thể cần một DTO riêng

Một DTO dùng chung cho tạo mới, cập nhật và quản trị có thể chứa quá nhiều trường tùy chọn và quy tắc khó hiểu. Thường nên định nghĩa theo use case:

- CreateRegistrationRequest: các trường cần khi tạo đăng ký.
- UpdateContactRequest: các trường được phép cập nhật thông tin liên hệ.
- RegistrationResponse: dữ liệu được phép trả về.
- RegistrationForm: dữ liệu mà một trang HTML cần nhận và hiển thị lỗi.

Không nhất thiết phải tạo nhiều lớp nếu biểu mẫu thực sự đơn giản và có cùng hợp đồng. Hãy chọn cấu trúc giúp giới hạn quyền ghi và làm rõ ý nghĩa từng request.

### Allowlist trường được phép nhận

Thiết kế DTO theo danh sách cho phép (allowlist): chỉ khai báo các trường mà client có quyền gửi. Không dùng một entity lớn rồi cố gắng chặn vài trường nhạy cảm bằng danh sách loại trừ.

Với JSON, chính sách về trường không được khai báo cũng cần rõ ràng. Một số cấu hình serializer bỏ qua trường lạ; cấu hình khác từ chối request. Dù chọn cách nào, ứng dụng không được âm thầm bind trường lạ vào thuộc tính nội bộ. Nếu cần từ chối trường không biết, hãy cấu hình message converter/serializer và kiểm thử hành vi đó.

## 4. Kiểm tra trường đơn bằng Jakarta Bean Validation

Jakarta Bean Validation cung cấp annotation để mô tả các ràng buộc phổ biến. Trong Spring Boot, dự án thường cần dependency validation tương ứng để các annotation được thực thi.

Một request DTO có thể khai báo:

    public record CreateRegistrationRequest(
            @NotBlank
            @Size(max = 20)
            String courseCode,

            @NotBlank
            @Email
            @Size(max = 254)
            String email,

            @NotNull
            @Min(1)
            @Max(4)
            Integer attendeeCount,

            @NotNull
            @Future
            LocalDate startDate) {
    }

Ý nghĩa:

- @NotBlank: chuỗi phải có ít nhất một ký tự không phải khoảng trắng.
- @Size(max = 20): giới hạn độ dài mã khóa học.
- @Email: kiểm tra cấu trúc địa chỉ email theo validator đang dùng.
- @NotNull: trường phải có giá trị.
- @Min và @Max: giới hạn giá trị số.
- @Future: ngày phải nằm trong tương lai.

Một số điểm cần nhớ:

- @Size, @Min, @Max, @Email thường xem null là hợp lệ; kết hợp với @NotNull hoặc @NotBlank nếu trường bắt buộc.
- @NotEmpty yêu cầu chuỗi, collection hoặc map không rỗng; với chuỗi chỉ chứa khoảng trắng, nó không thay thế @NotBlank.
- @Positive và @PositiveOrZero phù hợp với nhiều trường số.
- @DecimalMin và @DecimalMax có thể giới hạn giá trị thập phân.
- @Past, @PastOrPresent, @Future và @FutureOrPresent biểu diễn một số ràng buộc thời gian thông dụng.
- @Pattern kiểm tra chuỗi theo biểu thức chính quy, nhưng pattern phải phù hợp với quy tắc thực tế.

Không nên dùng một biểu thức chính quy quá chặt cho email hoặc số điện thoại rồi từ chối những giá trị hợp lệ theo chuẩn quốc tế. Validation cấu trúc nên kiểm tra điều ứng dụng thực sự cần, còn xác minh một địa chỉ email có nhận được thư hay không là một bước xác minh khác.

### Chọn kiểu dữ liệu phù hợp

Dùng Integer hoặc Long thay vì kiểu primitive nếu cần phân biệt trường bị thiếu với giá trị 0. Primitive không thể biểu diễn null, nên binding có thể tạo giá trị mặc định gây khó hiểu.

Dùng LocalDate cho ngày lịch và Instant hoặc OffsetDateTime cho thời điểm có offset. Chọn kiểu dữ liệu giúp giới hạn những giá trị có thể biểu diễn và tránh tự xử lý chuỗi ngày giờ trong Controller.

Với số tiền, dùng BigDecimal và quy định rõ scale, đơn vị tiền tệ cùng giới hạn. Đừng dùng double cho phép tính tiền cần độ chính xác thập phân.

## 5. Kiểm tra object lồng nhau và collection

Request thường chứa cấu trúc lồng nhau, chẳng hạn địa chỉ liên hệ hoặc danh sách mặt hàng. Để kiểm tra các trường bên trong, cần kích hoạt validation theo tầng bằng @Valid.

Ví dụ:

    public record ContactAddress(
            @NotBlank
            @Size(max = 120)
            String street,

            @NotBlank
            @Size(max = 80)
            String city,

            @NotBlank
            @Size(max = 20)
            String postalCode) {
    }

    public record RegistrationItemRequest(
            @NotBlank
            @Size(max = 30)
            String itemCode,

            @NotNull
            @Min(1)
            @Max(4)
            Integer quantity) {
    }

    public record CreateOrderRequest(
            @NotNull
            @Valid
            ContactAddress address,

            @NotEmpty
            @Size(max = 20)
            List<@NotNull @Valid RegistrationItemRequest> items) {
    }

Ở đây:

- @NotNull yêu cầu địa chỉ phải có mặt.
- @Valid yêu cầu validator đi tiếp vào các trường của ContactAddress.
- @NotEmpty yêu cầu danh sách có ít nhất một phần tử.
- @Size(max = 20) giới hạn số phần tử để request không tạo danh sách quá lớn.
- @NotNull @Valid trên phần tử kiểm tra từng item và các trường bên trong item.

Giới hạn số lượng phần tử và kích thước request là quan trọng. Một danh sách hợp lệ về kiểu vẫn có thể chứa hàng trăm nghìn phần tử và tiêu tốn bộ nhớ hoặc thời gian xử lý. Hãy kết hợp giới hạn DTO với giới hạn request body ở tầng HTTP/server.

### Kiểm tra collection

Ngoài số phần tử, có thể cần kiểm tra:

- Không có phần tử null.
- Không có mã trùng lặp trong cùng request.
- Mỗi phần tử có số lượng hợp lệ.
- Chuỗi trong mỗi phần tử không vượt giới hạn.
- Thứ tự phần tử có ý nghĩa hay không.

Nếu cần kiểm tra trùng lặp hoặc một điều kiện phụ thuộc nhiều phần tử, hãy viết một validator cấp lớp hoặc bước kiểm tra rõ ràng trước khi gọi use case. Tránh để template tự lặp và kiểm tra danh sách bằng nhiều biểu thức phức tạp.

## 6. Kiểm tra quan hệ giữa nhiều trường

Một số ràng buộc chỉ có thể xác định khi xem nhiều trường cùng lúc. Ví dụ, ngày kết thúc phải sau ngày bắt đầu; phương thức thanh toán yêu cầu một trường tương ứng; hoặc người dùng phải cung cấp ít nhất một trong hai cách liên hệ.

Với điều kiện đơn giản, có thể dùng một thuộc tính kiểm tra bổ sung:

    public record DateRangeRequest(
            @NotNull LocalDate startDate,
            @NotNull LocalDate endDate) {

        @AssertTrue(message = "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu")
        public boolean isDateRangeValid() {
            return startDate == null
                    || endDate == null
                    || !endDate.isBefore(startDate);
        }
    }

Phương thức trả về true khi một trong hai trường còn thiếu để các annotation @NotNull báo lỗi riêng. Khi cả hai trường có mặt, nó kiểm tra quan hệ ngày.

Với quy tắc phức tạp hơn, nên tạo class-level constraint riêng bằng @Constraint và ConstraintValidator. Validator có thể tạo lỗi gắn với một trường cụ thể hoặc lỗi cấp object. Điều này giúp thông báo hiển thị đúng vị trí hơn.

Không nên đặt quy tắc phụ thuộc cơ sở dữ liệu, quyền hoặc trạng thái hệ thống vào class-level Bean Validation. Ví dụ, kiểm tra “mã khóa học có tồn tại và còn mở đăng ký không” thuộc ca sử dụng. Bean Validation phù hợp nhất với những điều kiện cấu trúc và nhất quán của chính dữ liệu request.

## 7. Xử lý validation trong Spring MVC cho biểu mẫu HTML

Với biểu mẫu server-side, Spring MVC có thể bind dữ liệu request vào form object và chạy Bean Validation khi tham số được đánh dấu @Valid.

Ví dụ:

    public record RegistrationForm(
            @NotBlank
            @Size(max = 20)
            String courseCode,

            @NotBlank
            @Email
            @Size(max = 254)
            String email,

            @NotNull
            @Min(1)
            @Max(4)
            Integer attendeeCount) {
    }

    @Controller
    @RequestMapping("/registrations")
    public class RegistrationController {
        private final RegisterForCourse registerForCourse;

        public RegistrationController(RegisterForCourse registerForCourse) {
            this.registerForCourse = registerForCourse;
        }

        @GetMapping("/new")
        public String newForm(Model model) {
            model.addAttribute(
                    "form",
                    new RegistrationForm("", "", 1));
            return "registrations/new";
        }

        @PostMapping
        public String create(
                @Valid @ModelAttribute("form") RegistrationForm form,
                BindingResult errors,
                RedirectAttributes redirectAttributes) {

            if (errors.hasErrors()) {
                return "registrations/new";
            }

            registerForCourse.execute(
                    form.courseCode(),
                    form.email(),
                    form.attendeeCount());

            redirectAttributes.addFlashAttribute(
                    "message", "Đăng ký thành công");

            return "redirect:/registrations";
        }
    }

BindingResult phải đứng ngay sau tham số được đánh dấu @Valid hoặc @Validated để Controller nhận được lỗi binding và validation của đối tượng đó.

Luồng xử lý:

1. GET hiển thị form với dữ liệu ban đầu.
2. POST bind các trường vào RegistrationForm.
3. Spring thực hiện conversion và validation.
4. Nếu có lỗi, Controller trả lại cùng View để hiển thị lỗi.
5. Nếu dữ liệu hợp lệ về cấu trúc, Controller gọi use case.
6. Khi thành công, ứng dụng chuyển hướng và hiển thị thông báo.

Lỗi conversion cũng có thể xuất hiện trong BindingResult. Ví dụ, người dùng gửi chữ vào trường số nguyên. Đây là lỗi binding, không phải lỗi nghiệp vụ.

### Hiển thị lỗi trong Thymeleaf

Một template có thể liên kết input với form object và hiển thị lỗi cạnh trường:

    <form th:action="@{/registrations}"
          th:object="${form}"
          method="post">

        <label for="email">Email</label>
        <input id="email"
               type="email"
               th:field="*{email}"
               th:attr="aria-describedby='email-error'">

        <p id="email-error"
           th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}">
            Email không hợp lệ
        </p>

        <label for="courseCode">Mã khóa học</label>
        <input id="courseCode"
               type="text"
               th:field="*{courseCode}">

        <p th:if="${#fields.hasErrors('courseCode')}"
           th:errors="*{courseCode}">
            Mã khóa học không hợp lệ
        </p>

        <button type="submit">Đăng ký</button>
    </form>

th:field giữ liên kết giữa input và form object, đồng thời hỗ trợ hiển thị lại giá trị đã nhập. th:errors hiển thị lỗi gắn với trường. Với ứng dụng dùng Spring Security và session/cookie, cần giữ CSRF protection cho form thay đổi dữ liệu theo cấu hình framework.

Nên có label gắn với từng input và liên kết lỗi bằng aria-describedby hoặc cơ chế tương đương. Người dùng dùng trình đọc màn hình cần biết trường nào có lỗi và cách sửa.

## 8. Xử lý validation cho API JSON

Với API, request body được chuyển thành DTO bởi HTTP message converter. @Valid yêu cầu chạy Bean Validation sau khi body được parse thành công.

Ví dụ:

    @RestController
    @RequestMapping("/api/registrations")
    public class RegistrationApiController {
        private final RegisterForCourse registerForCourse;

        public RegistrationApiController(RegisterForCourse registerForCourse) {
            this.registerForCourse = registerForCourse;
        }

        @PostMapping
        public ResponseEntity<RegistrationResponse> create(
                @Valid @RequestBody CreateRegistrationRequest request) {

            RegistrationResult result = registerForCourse.execute(
                    request.courseCode(),
                    request.email(),
                    request.attendeeCount());

            return ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(RegistrationResponse.from(result));
        }
    }

Nếu JSON sai cú pháp hoặc không chuyển được kiểu dữ liệu, phương thức có thể chưa được gọi. Spring thường ánh xạ lỗi đọc body thành 400 Bad Request. Nếu JSON parse thành công nhưng vi phạm annotation validation, Spring thường phát sinh MethodArgumentNotValidException cho tham số @Valid @RequestBody.

### Chuẩn hóa lỗi API

Không nên để mỗi Controller tự tạo một cấu trúc lỗi khác nhau. Có thể dùng @RestControllerAdvice để ánh xạ lỗi validation thành response thống nhất.

Ví dụ:

    public record FieldViolation(
            String field,
            String message) {
    }

    public record ValidationErrorResponse(
            String code,
            String message,
            List<FieldViolation> violations) {
    }

    @RestControllerAdvice
    public class ApiValidationAdvice {

        @ExceptionHandler(MethodArgumentNotValidException.class)
        ResponseEntity<ValidationErrorResponse> handleValidation(
                MethodArgumentNotValidException exception) {

            List<FieldViolation> violations =
                    exception.getBindingResult()
                            .getFieldErrors()
                            .stream()
                            .map(error -> new FieldViolation(
                                    error.getField(),
                                    error.getDefaultMessage()))
                            .toList();

            ValidationErrorResponse body = new ValidationErrorResponse(
                    "VALIDATION_FAILED",
                    "Dữ liệu gửi lên chưa hợp lệ",
                    violations);

            return ResponseEntity.badRequest().body(body);
        }
    }

Response có thể có dạng:

    {
      "code": "VALIDATION_FAILED",
      "message": "Dữ liệu gửi lên chưa hợp lệ",
      "violations": [
        {
          "field": "email",
          "message": "phải là địa chỉ email hợp lệ"
        },
        {
          "field": "attendeeCount",
          "message": "phải nhỏ hơn hoặc bằng 4"
        }
      ]
    }

Đây là một hợp đồng lỗi minh họa. API có thể chọn Problem Details theo RFC 9457 và thêm một trường mở rộng như violations. Điều quan trọng là status, mã lỗi, tên trường và thông điệp phải nhất quán, đồng thời không tiết lộ chi tiết nội bộ.

Với lỗi parse JSON, có thể xử lý HttpMessageNotReadableException để trả mã lỗi khác như MALFORMED_REQUEST. Với lỗi method parameter validation trong các phiên bản Spring mới, cần xem xét HandlerMethodValidationException tùy chữ ký controller và phiên bản framework. Hãy kiểm thử cả lỗi body lẫn lỗi tham số path/query.

### 400 hay 422?

Nhiều ứng dụng dùng 400 Bad Request cho lỗi parsing và validation cấu trúc. Một số API chọn 422 Unprocessable Content cho nội dung hợp cú pháp nhưng không thỏa điều kiện xử lý theo hợp đồng. Cả hai cách cần được quy định rõ và dùng nhất quán. Đừng để client phải đoán loại lỗi qua nội dung chuỗi message.

## 9. Chuẩn hóa dữ liệu và kiểm tra định dạng

Validation xác định dữ liệu có đáp ứng hợp đồng hay không. Normalization chuẩn hóa cách biểu diễn dữ liệu để các giá trị tương đương được xử lý nhất quán. Hai bước này liên quan nhưng không giống nhau.

Ví dụ, tên người dùng có thể được trim khoảng trắng ở đầu và cuối. Mã định danh không phân biệt chữ hoa/thường có thể được chuẩn hóa theo quy tắc của hệ thống. Tuy nhiên, không phải trường nào cũng nên thay đổi.

Một số nguyên tắc:

- Xác định rõ trường nào được trim hoặc chuẩn hóa.
- Giữ bản gốc nếu ứng dụng cần hiển thị nguyên văn.
- Không tự động xóa ký tự có thể có ý nghĩa trong tên hoặc địa chỉ.
- Không trim, đổi chữ hoa/thường hoặc biến đổi mật khẩu.
- Không dùng regex quá chặt để giả định mọi tên, email hoặc số điện thoại đều theo một mẫu đơn giản.
- Chuẩn hóa trước khi so sánh hoặc lưu theo quy tắc miền nghiệp vụ đã công bố.
- Kiểm tra giới hạn sau khi normalization nếu giới hạn áp dụng lên giá trị chuẩn hóa.

Với Unicode, một chuỗi có thể có nhiều cách mã hóa tương đương về mặt hiển thị. Nếu hệ thống so sánh định danh hoặc chống trùng, cần xác định chính sách normalization phù hợp. Không nên tùy tiện chuẩn hóa mọi nội dung văn bản vì có thể làm thay đổi ý nghĩa hoặc dữ liệu gốc.

### Kiểm tra số điện thoại

Không nên mặc định số điện thoại chỉ có 10 chữ số hoặc luôn bắt đầu bằng một đầu số cố định. Nếu sản phẩm hỗ trợ nhiều quốc gia, hãy dùng thư viện và quy tắc phù hợp, lưu kèm mã quốc gia khi cần. Validation cấu trúc có thể kiểm tra độ dài và ký tự cho phép, còn việc số điện thoại có thực sự thuộc về người dùng cần một bước xác minh riêng.

## 10. Giới hạn request và kiểm tra tệp tải lên

Một request có thể đúng cấu trúc nhưng quá lớn. Ranh giới HTTP cần giới hạn:

- Tổng kích thước request body.
- Độ dài từng trường chuỗi.
- Số phần tử trong collection.
- Kích thước từng tệp tải lên.
- Số tệp trong một request.
- Thời gian xử lý và mức độ phức tạp của các phép kiểm tra.

Với file upload, không chỉ dựa vào tên file hoặc Content-Type do client gửi vì những giá trị này có thể bị giả mạo. Cần kiểm tra giới hạn kích thước, phần mở rộng theo allowlist, loại nội dung thực tế bằng cách phù hợp, và quét mã độc nếu rủi ro của sản phẩm yêu cầu. Tệp nên được lưu ở vị trí không thể thực thi trực tiếp như mã ứng dụng; tên lưu trữ nên do server tạo thay vì tin tên đường dẫn client gửi.

Không nên đọc toàn bộ file lớn vào bộ nhớ chỉ để kiểm tra vài thuộc tính. Dùng streaming và giới hạn tài nguyên theo cấu hình server.

## 11. Validation không thay thế các biện pháp bảo mật khác

Validation giúp giới hạn dữ liệu đầu vào nhưng không tự giải quyết mọi lỗ hổng.

### Chống mass assignment

Nếu client gửi thêm trường role, ownerId, status hoặc approved, server không được tự động bind các trường đó vào entity. DTO allowlist và việc thiết lập các trường nhạy cảm từ security context hoặc quy tắc server giúp ngăn sửa dữ liệu trái phép.

### Chống SQL injection

Kiểm tra chuỗi đầu vào theo định dạng không thay thế prepared statement hoặc parameterized query. Không nối chuỗi request trực tiếp vào SQL. Với trường sắp xếp động, chỉ cho phép các tên cột hoặc lựa chọn đã nằm trong allowlist.

### Chống XSS

Một chuỗi vượt qua validation vẫn có thể chứa HTML hoặc JavaScript độc hại. Khi hiển thị lại trong View, phải escape theo đúng ngữ cảnh. Validation không phải cơ chế output encoding.

### CSRF và quyền truy cập

Form dùng session/cookie cần cơ chế CSRF phù hợp. Endpoint vẫn phải xác thực và phân quyền trên server. Không coi việc ẩn nút hoặc kiểm tra một trường trong form là bằng chứng người dùng được phép thực hiện thao tác.

### Không trả lỗi chứa dữ liệu nhạy cảm

Thông điệp lỗi nên nêu trường nào cần sửa và quy tắc ở mức người dùng hiểu được. Tránh trả lại nguyên giá trị nhạy cảm, token, stack trace hoặc chi tiết nội bộ. Với log server, cần tránh ghi mật khẩu, token và dữ liệu cá nhân không cần thiết.

## 12. Tổ chức validation theo use case

Một số hệ thống có các nhóm thao tác với yêu cầu khác nhau. Ví dụ, tạo tài khoản cần mật khẩu; cập nhật hồ sơ không nhất thiết yêu cầu gửi lại mật khẩu. Có thể dùng validation groups, nhưng không nên lạm dụng một DTO lớn chứa nhiều trường tùy chọn chỉ để phục vụ mọi trường hợp.

Jakarta Bean Validation hỗ trợ group:

    public interface CreateOperation {}
    public interface UpdateOperation {}

    public record UserRequest(
            @NotBlank(groups = CreateOperation.class)
            String username,

            @NotBlank(groups = CreateOperation.class)
            @Size(min = 12, groups = CreateOperation.class)
            String password,

            @Size(max = 120, groups = {
                    CreateOperation.class,
                    UpdateOperation.class
            })
            String displayName) {
    }

Spring có thể kích hoạt group thông qua @Validated(CreateOperation.class) hoặc group phù hợp ở endpoint. Cần lưu ý group mặc định và group sequence nếu ứng dụng dùng nhiều tầng validation.

Nếu hai use case có hợp đồng khác nhau đáng kể, hai DTO riêng thường dễ đọc và an toàn hơn. Validation groups hữu ích khi cấu trúc dữ liệu thực sự được chia sẻ và khác biệt chỉ nằm ở một số ràng buộc.

### Validation phụ thuộc vào locale hoặc ngữ cảnh

Một số thông điệp validation cần dịch theo ngôn ngữ người dùng. Có thể dùng message key trong annotation và cấu hình message source. Không nên hardcode toàn bộ thông điệp tiếng Việt vào validator nếu ứng dụng cần đa ngôn ngữ.

Thông điệp cho người dùng nên dễ hiểu, chỉ rõ cách sửa. Mã lỗi ổn định nên được tách khỏi message để client có thể xử lý mà không phụ thuộc ngôn ngữ.

## 13. Kiểm thử validation

Validation cần được kiểm thử ở hai mức: kiểm thử DTO/validator và kiểm thử HTTP endpoint.

### Unit test cho DTO

Có thể dùng jakarta.validation.Validator để kiểm tra các constraint:

    @Test
    void rejectsInvalidRegistrationInput() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            CreateRegistrationRequest request =
                    new CreateRegistrationRequest(
                            "",
                            "not-an-email",
                            8,
                            LocalDate.now().minusDays(1));

            Set<ConstraintViolation<CreateRegistrationRequest>> violations =
                    validator.validate(request);

            assertFalse(violations.isEmpty());
        }
    }

Unit test này xác nhận constraint trên DTO hoạt động. Với custom validator hoặc cross-field constraint, cần kiểm thử cả trường hợp hợp lệ và không hợp lệ, gồm trường bị thiếu và các giá trị biên.

### Kiểm thử qua MockMvc

Một endpoint API có thể được kiểm thử bằng request JSON sai:

    mockMvc.perform(post("/api/registrations")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "courseCode": "",
                  "email": "wrong",
                  "attendeeCount": 8,
                  "startDate": "2020-01-01"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.violations").isArray());

Với form HTML, cần kiểm tra:

- Trường sai được bind vào đúng form object.
- View được render lại thay vì gọi use case.
- Giá trị hợp lệ mà người dùng đã nhập được giữ lại.
- Lỗi xuất hiện cạnh trường tương ứng.
- Request thành công gọi use case và chuyển hướng theo thiết kế.

### Các trường hợp biên nên có

| Dữ liệu | Trường hợp cần kiểm tra |
|---|---|
| Chuỗi | null, rỗng, chỉ có khoảng trắng, đúng giới hạn, vượt giới hạn, Unicode |
| Số | thiếu, sai kiểu, âm, 0, giá trị tối thiểu/tối đa, vượt giới hạn |
| Ngày giờ | sai định dạng, thiếu, quá khứ/tương lai, biên múi giờ |
| Collection | rỗng, một phần tử, tối đa, vượt tối đa, phần tử null, trùng lặp |
| Object lồng nhau | thiếu object, thiếu trường con, trường con sai |
| JSON | sai cú pháp, sai kiểu, thiếu trường, trường lạ theo chính sách |
| Quyền | ID hợp lệ nhưng người gọi không có quyền trên tài nguyên |

Không chỉ kiểm thử trường hợp sai. Cần có trường hợp hợp lệ sát giới hạn để tránh validator từ chối nhầm dữ liệu được phép.

## 14. Dấu hiệu validation đang đặt sai chỗ

Hãy xem xét thiết kế lại khi:

- Template chứa nhiều biểu thức kiểm tra định dạng hoặc giới hạn dữ liệu.
- Controller tự viết các chuỗi if lặp lại để kiểm tra mọi trường.
- Entity được bind trực tiếp từ request body.
- Một validator truy vấn database để quyết định quy tắc nghiệp vụ.
- Client-side validation là nơi duy nhất kiểm tra đầu vào.
- Lỗi validation được trả bằng một cấu trúc khác nhau ở từng endpoint.
- Một request có thể gửi collection hoặc file không giới hạn.
- Thông điệp lỗi tiết lộ dữ liệu nội bộ hoặc gây khó hiểu cho người dùng.
- Validation và phân quyền bị gộp thành một điều kiện duy nhất.

Một cách refactor:

1. Liệt kê trường đầu vào và giới hạn của từng trường theo hợp đồng.
2. Tạo request DTO/form object chỉ gồm các trường được phép gửi.
3. Chuyển ràng buộc cấu trúc thành Bean Validation hoặc validator phù hợp.
4. Chuyển điều kiện nghiệp vụ sang application/domain layer.
5. Chuẩn hóa cách ánh xạ lỗi cho HTML và JSON.
6. Bổ sung giới hạn request, collection và file ở tầng HTTP.
7. Viết test cho DTO, endpoint và các trường hợp biên.

## 15. Quy trình thiết kế kiểm tra tại ranh giới giao diện

Khi xây dựng một biểu mẫu hoặc endpoint mới, có thể đi theo trình tự:

1. Xác định client và mục đích của request: form HTML, API JSON hay một giao diện khác.
2. Liệt kê trường bắt buộc, kiểu dữ liệu, độ dài, miền giá trị và quy ước null.
3. Tạo DTO/form object theo allowlist, không bind entity lưu trữ.
4. Xác định bước parsing/binding và các lỗi chuyển đổi có thể xảy ra.
5. Thêm constraint cho trường đơn, object lồng nhau và collection.
6. Xác định quy tắc phụ thuộc nhiều trường; dùng class-level validator khi phù hợp.
7. Đưa quy tắc nghiệp vụ và phân quyền về lớp chịu trách nhiệm tương ứng.
8. Chọn cách trả lỗi phù hợp với HTML hoặc API và bảo đảm thông điệp dễ hiểu.
9. Giới hạn kích thước request, chuỗi, danh sách và tệp.
10. Kiểm thử dữ liệu hợp lệ, không hợp lệ, trường hợp biên và quyền truy cập.

## Kết luận

Kiểm tra cấu trúc dữ liệu tại ranh giới giao diện giúp ứng dụng chỉ tiếp nhận những request phù hợp với hợp đồng đã công bố. Parsing/binding chuyển dữ liệu thô thành kiểu có thể xử lý; validation kiểm tra trường bắt buộc, định dạng, độ dài, miền giá trị và cấu trúc lồng nhau. Các quy tắc phụ thuộc trạng thái nghiệp vụ và quyền truy cập cần được kiểm tra ở application/domain và security layer.

Trong MVC, Controller phối hợp binding và validation, sau đó gọi use case khi dữ liệu ở ranh giới hợp lệ. DTO giới hạn trường client được phép gửi; View hoặc API response trình bày lỗi theo cách dễ hiểu. Kết hợp kiểm tra phía client để cải thiện trải nghiệm với kiểm tra phía server để bảo vệ ứng dụng giúp dữ liệu đi vào các lớp bên trong có cấu trúc rõ ràng và đáng tin cậy hơn.
