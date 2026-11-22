# Phản hồi khi dữ liệu nhập không hợp lệ

Trong ứng dụng MVC, người dùng thường gửi dữ liệu qua biểu mẫu để tạo, cập nhật hoặc tìm kiếm thông tin. Dữ liệu có thể thiếu, sai định dạng, vượt giới hạn hoặc không còn phù hợp với trạng thái hiện tại của hệ thống. Cách ứng dụng phản hồi những tình huống này ảnh hưởng trực tiếp đến khả năng hoàn thành công việc, độ tin cậy của dữ liệu và mức độ an toàn của hệ thống.

Một phản hồi tốt cho biết điều gì cần sửa, đặt thông tin ngay cạnh vị trí liên quan, giữ lại những dữ liệu hợp lệ mà người dùng đã nhập và giúp họ tiếp tục thao tác. Trong MVC, Controller tiếp nhận và điều phối việc kiểm tra, Model bảo vệ quy tắc nghiệp vụ, còn View trình bày lỗi theo cách người dùng có thể hiểu và xử lý.

Bài học này trình bày cách thiết kế vòng đời biểu mẫu, phân chia trách nhiệm validation, ánh xạ lỗi vào giao diện, xây dựng hợp đồng lỗi cho API, bảo vệ dữ liệu và kiểm thử luồng phản hồi.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt lỗi cú pháp, lỗi ràng buộc trường, lỗi giữa nhiều trường và lỗi quy tắc nghiệp vụ.
- Giải thích vai trò của kiểm tra phía trình duyệt, Controller, ca sử dụng và Domain Model.
- Thiết kế luồng gửi biểu mẫu và trả lại trang khi dữ liệu không hợp lệ.
- Hiển thị lỗi theo trường và lỗi chung, đồng thời giữ lại dữ liệu đã nhập phù hợp.
- Xây dựng thông báo lỗi rõ ràng, có thể truy cập bằng bàn phím và công nghệ hỗ trợ.
- Thiết kế phản hồi lỗi nhất quán cho HTML form và API.
- Kiểm thử cả quy tắc nghiệp vụ lẫn cách Controller và View xử lý lỗi.

## 2. Vì sao phản hồi dữ liệu không hợp lệ quan trọng?

Một biểu mẫu là điểm giao tiếp giữa ý định của người dùng và quy tắc của ứng dụng. Người dùng có thể hiểu trường dữ liệu theo cách khác với hệ thống, bỏ sót thông tin hoặc nhập một giá trị từng hợp lệ nhưng nay không còn phù hợp.

Ví dụ, biểu mẫu đặt chỗ có các trường tên, email, số người và ngày đến. Các tình huống có thể xảy ra gồm:

- Tên bị bỏ trống.
- Email không đúng định dạng.
- Số người bằng 0 hoặc vượt giới hạn.
- Ngày đến nằm trong quá khứ.
- Số chỗ còn lại đã thay đổi sau khi người dùng mở biểu mẫu.
- Email đã được dùng cho một đăng ký khác.

Các lỗi này không cùng một loại và không nên được xử lý bằng một thông báo chung như “Dữ liệu không hợp lệ”. Người dùng cần biết trường nào cần sửa, giá trị nào được chấp nhận và liệu họ có cần thực hiện lại một bước khác hay không.

Một luồng phản hồi tốt cần đạt các mục tiêu sau:

1. **Phát hiện đúng vấn đề.** Kiểm tra phải phản ánh quy tắc thực tế và tránh báo lỗi sai.
2. **Chỉ rõ vị trí.** Lỗi của một trường nên xuất hiện cạnh trường đó; lỗi tổng thể cần được đưa vào phần tóm tắt.
3. **Hướng dẫn hành động.** Thông báo mô tả cách sửa, giới hạn hoặc bước tiếp theo.
4. **Giữ công sức đã bỏ ra.** Các trường hợp lệ vẫn được giữ lại khi biểu mẫu được hiển thị lại.
5. **Bảo vệ dữ liệu.** Dữ liệu không đáng tin cậy phải được kiểm tra ở máy chủ; lỗi không làm lộ thông tin nội bộ.
6. **Hỗ trợ mọi cách tương tác.** Người dùng bàn phím, trình đọc màn hình, thiết bị di động và API client đều nhận được phản hồi có cấu trúc.

## 3. Các loại lỗi đầu vào

Phân loại lỗi giúp chọn đúng nơi kiểm tra và cách phản hồi.

| Loại lỗi | Ví dụ | Nơi thường phát hiện |
|---|---|---|
| Thiếu dữ liệu | Bỏ trống tên bắt buộc | Trình duyệt và validation phía máy chủ |
| Sai kiểu hoặc định dạng | Email không hợp lệ, ngày không chuyển đổi được | Trình duyệt, bộ chuyển đổi dữ liệu và DTO |
| Vi phạm giới hạn trường | Số lượng âm, ghi chú quá dài | DTO và Domain Model |
| Không nhất quán giữa nhiều trường | Ngày kết thúc trước ngày bắt đầu | Validator cấp đối tượng hoặc ca sử dụng |
| Vi phạm quy tắc nghiệp vụ | Không đủ chỗ, tài khoản không được phép đặt | Ca sử dụng và Domain Model |
| Xung đột trạng thái | Dữ liệu đã bị người khác thay đổi | Ca sử dụng, persistence layer |
| Lỗi kỹ thuật | Cơ sở dữ liệu mất kết nối | Hạ tầng và lớp xử lý lỗi |

### 3.1. Lỗi cú pháp và định dạng

Lỗi cú pháp xảy ra khi dữ liệu không thể được diễn giải theo kiểu mong đợi. Ví dụ, chuỗi “năm người” không thể chuyển thành số nguyên; chuỗi ngày không đúng định dạng cũng có thể không chuyển thành LocalDate.

Đây là lỗi ở ranh giới tiếp nhận dữ liệu. Controller hoặc bộ chuyển đổi cần nhận biết chúng và trả lại biểu mẫu với thông báo phù hợp. Không nên để lỗi chuyển đổi trở thành lỗi máy chủ không được xử lý.

### 3.2. Lỗi ràng buộc của một trường

Một giá trị có thể đúng kiểu nhưng vẫn không hợp lệ. Số người là số nguyên nhưng bằng 0; chuỗi email có thể không rỗng nhưng sai định dạng; tên có thể vượt quá độ dài cho phép.

Các ràng buộc như bắt buộc, độ dài, khoảng giá trị và định dạng thường được khai báo trên request DTO hoặc form model bằng Bean Validation. Domain Model vẫn cần bảo vệ những bất biến nghiệp vụ mà mọi điểm gọi phải tuân thủ.

### 3.3. Lỗi giữa nhiều trường

Một số quy tắc chỉ có thể đánh giá khi xem nhiều trường cùng lúc. Ví dụ, ngày trả phòng phải sau ngày nhận phòng; mật khẩu xác nhận phải trùng mật khẩu; số lượng đặt không được vượt quá giới hạn của một nhóm sản phẩm.

Có thể dùng class-level constraint hoặc một validator riêng cho form object. Khi hiển thị, lỗi nên được gắn với trường người dùng có thể sửa hoặc được trình bày như một lỗi chung của biểu mẫu.

### 3.4. Lỗi quy tắc nghiệp vụ

Dữ liệu có thể hợp lệ về cấu trúc nhưng không được phép theo trạng thái hiện tại. Một ngày đặt chỗ có thể nằm trong tương lai nhưng không còn chỗ; một mã giảm giá có thể đúng định dạng nhưng đã hết hạn.

Các quy tắc này cần được kiểm tra trong ca sử dụng hoặc Domain Model, nơi có đủ dữ liệu và ngữ cảnh nghiệp vụ. Không nên chỉ kiểm tra chúng bằng JavaScript hoặc dựa vào dữ liệu đã tải trên trình duyệt, vì trạng thái có thể thay đổi trước khi máy chủ xử lý yêu cầu.

### 3.5. Lỗi nghiệp vụ và lỗi kỹ thuật

Lỗi nghiệp vụ là kết quả có thể dự đoán của một thao tác không được phép, chẳng hạn hết chỗ hoặc trạng thái không phù hợp. Lỗi kỹ thuật là sự cố khi hệ thống không thể hoàn thành công việc, chẳng hạn cơ sở dữ liệu ngừng hoạt động.

Không nên hiển thị lỗi kỹ thuật như thể người dùng nhập sai. Nếu cơ sở dữ liệu mất kết nối, yêu cầu có thể cần thông báo “Chưa thể lưu thông tin lúc này. Vui lòng thử lại sau”, thay vì yêu cầu người dùng sửa một trường không có vấn đề.

## 4. Đặt validation ở đúng ranh giới trong MVC

Validation không phải một bước duy nhất. Một hệ thống có thể kiểm tra dữ liệu ở nhiều tầng, mỗi tầng có mục tiêu riêng.

### 4.1. Kiểm tra phía trình duyệt

HTML cung cấp các thuộc tính như required, type, min, max, minlength và maxlength. JavaScript có thể bổ sung kiểm tra tức thời, ví dụ xác nhận hai trường khớp nhau hoặc hiển thị giới hạn còn lại.

Lợi ích của kiểm tra phía trình duyệt:

- Người dùng nhận phản hồi nhanh trước khi gửi request.
- Giảm những lần gửi biểu mẫu rõ ràng không hợp lệ.
- Có thể hướng dẫn định dạng ngay khi nhập.
- Tạo trải nghiệm thuận tiện trên thiết bị di động.

Tuy nhiên, trình duyệt và JavaScript nằm trong môi trường người dùng kiểm soát. Người dùng có thể tắt JavaScript, sửa HTML, gọi API trực tiếp hoặc gửi request bằng công cụ khác. Vì vậy, kiểm tra phía trình duyệt chỉ hỗ trợ trải nghiệm; máy chủ vẫn phải xác thực dữ liệu.

### 4.2. Kiểm tra cấu trúc ở Controller và form model

Controller tiếp nhận request, chuyển dữ liệu thành form model hoặc request DTO và kích hoạt Bean Validation. Những quy tắc như bắt buộc, độ dài, kiểu và định dạng là ví dụ phù hợp.

Nếu dữ liệu không thể chuyển đổi, chẳng hạn chuỗi ngày sai định dạng, Spring MVC ghi nhận lỗi binding. Nếu dữ liệu chuyển đổi được nhưng vi phạm annotation validation, lỗi được ghi nhận trong BindingResult.

Controller chịu trách nhiệm chọn phản hồi giao tiếp: hiển thị lại View, trả lỗi API hoặc chuyển hướng sau khi thao tác thành công.

### 4.3. Kiểm tra quy tắc nghiệp vụ

Ca sử dụng và Domain Model kiểm tra các điều kiện phụ thuộc vào nghiệp vụ, dữ liệu đã lưu, quyền của người gọi hoặc trạng thái hiện tại.

Ví dụ:

- Người dùng chỉ được hủy đơn khi đơn còn ở trạng thái cho phép.
- Số lượng đặt không vượt quá tồn kho có thể phân bổ.
- Mã khuyến mãi còn hiệu lực với sản phẩm và khách hàng này.
- Người dùng có quyền sửa tài nguyên đang yêu cầu.

Những điều kiện này không thể được bảo đảm bằng một thuộc tính HTML. Chúng cần được kiểm tra lại ở máy chủ trong cùng luồng thực hiện thao tác.

### 4.4. Ràng buộc ở cơ sở dữ liệu

Cơ sở dữ liệu cần bảo vệ các ràng buộc toàn vẹn như khóa duy nhất, khóa ngoại và giới hạn dữ liệu. Đây là lớp bảo vệ cuối cùng trước các thao tác đồng thời hoặc lỗi trong tầng ứng dụng.

Ví dụ, hai request có thể cùng kiểm tra một email chưa tồn tại rồi cùng cố tạo tài khoản. Chỉ kiểm tra trước khi lưu không đủ để ngăn race condition. Ràng buộc unique ở cơ sở dữ liệu vẫn cần thiết; tầng ứng dụng chuyển lỗi vi phạm unique thành phản hồi phù hợp.

### 4.5. Bảng phân công trách nhiệm

| Tầng | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Trình duyệt | Người dùng có thể sửa ngay lỗi rõ ràng không? | Trường bắt buộc, số tối thiểu |
| Controller / DTO | Request có đúng cấu trúc và hợp đồng không? | Email đúng định dạng, ngày chuyển đổi được |
| Ca sử dụng | Hành động có được phép trong ngữ cảnh hiện tại không? | Còn chỗ, người dùng có quyền |
| Domain Model | Thao tác có giữ các bất biến của đối tượng không? | Không xác nhận đơn rỗng |
| Cơ sở dữ liệu | Dữ liệu lưu có giữ toàn vẹn khi có cạnh tranh không? | Unique constraint, foreign key |

Không cần lặp lại cùng một biểu thức validation ở mọi tầng. Hãy đặt quy tắc ở nơi có đủ ngữ cảnh để quyết định và bảo đảm quy tắc quan trọng được thực thi ở phía máy chủ.

## 5. Luồng phản hồi của biểu mẫu

Một luồng MVC phổ biến gồm tiếp nhận, binding, validation, xử lý nghiệp vụ và trình bày kết quả.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as Controller
    participant Validator as Binding / Validation
    participant UseCase as Ca sử dụng
    participant Model as Domain Model
    participant View as View

    User->>Browser: Nhập dữ liệu và gửi biểu mẫu
    Browser->>Browser: Kiểm tra HTML / JavaScript
    alt Dữ liệu không qua kiểm tra trình duyệt
        Browser-->>User: Hiển thị gợi ý tại trường
    else Request được gửi
        Browser->>Controller: POST form data
        Controller->>Validator: Binding và validation
        alt Lỗi binding hoặc validation
            Validator-->>Controller: BindingResult có lỗi
            Controller->>View: Trả form và lỗi
            View-->>Browser: HTML có thông báo
            Browser-->>User: Hiển thị lỗi và dữ liệu đã nhập
        else Cấu trúc hợp lệ
            Validator-->>Controller: Dữ liệu hợp lệ
            Controller->>UseCase: Gọi ca sử dụng
            UseCase->>Model: Thực hiện quy tắc nghiệp vụ
            alt Vi phạm quy tắc nghiệp vụ
                Model-->>UseCase: Kết quả lỗi nghiệp vụ
                UseCase-->>Controller: Lỗi có thể xử lý
                Controller->>View: Gắn lỗi và trả form
                View-->>Browser: HTML có thông báo
            else Thành công
                Model-->>UseCase: Trạng thái hợp lệ
                UseCase-->>Controller: Kết quả thành công
                Controller-->>Browser: Redirect đến trang kết quả
            end
        end
    end
~~~

Có hai kiểu phản hồi chính:

- Khi dữ liệu không hợp lệ, trả lại biểu mẫu để người dùng sửa.
- Khi thao tác thành công, thường dùng Post/Redirect/Get (PRG) để chuyển sang trang kết quả.

Với biểu mẫu HTML server-rendered, phản hồi lỗi validation thường render lại View với HTTP 200 vì máy chủ đã xử lý request và trả về trang biểu mẫu. Đây là một lựa chọn giao diện phổ biến; mã trạng thái cho API hoặc giao thức khác cần theo hợp đồng riêng.

## 6. Thiết kế form model và ràng buộc đầu vào

Form model mô tả dữ liệu mà một biểu mẫu nhận. Nó có thể giống một phần với Domain Model, nhưng nên chỉ chứa các trường mà người dùng được phép gửi.

Ví dụ, biểu mẫu đặt chỗ nhận tên, email, số người, ngày đến và ghi chú. Mã minh họa sau sử dụng Jakarta Bean Validation và Spring MVC:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;

public class BookingForm {
    @NotBlank(message = "{booking.name.required}")
    @Size(max = 80, message = "{booking.name.tooLong}")
    private String fullName;

    @NotBlank(message = "{booking.email.required}")
    @Email(message = "{booking.email.invalid}")
    @Size(max = 254, message = "{booking.email.tooLong}")
    private String email;

    @NotNull(message = "{booking.guests.required}")
    @Min(value = 1, message = "{booking.guests.min}")
    @Max(value = 8, message = "{booking.guests.max}")
    private Integer guests;

    @NotNull(message = "{booking.date.required}")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate arrivalDate;

    @Size(max = 500, message = "{booking.note.tooLong}")
    private String note;

    // Getter và setter cho các trường.
}
~~~

Một vài quyết định trong thiết kế này đáng chú ý:

- Integer được dùng thay vì int cho số người để phân biệt trường chưa được nhập (null) với giá trị 0.
- @NotNull kiểm tra trường có giá trị; @Min và @Max kiểm tra khoảng giá trị.
- @NotBlank phù hợp với chuỗi bắt buộc vì chuỗi chỉ có khoảng trắng cũng bị xem là trống.
- Giới hạn độ dài giúp kiểm soát dữ liệu và giảm nguy cơ lưu hoặc xử lý nội dung quá lớn.
- Thông báo dùng message key để có thể dịch theo ngôn ngữ.

Đây là kiểm tra cấu trúc của biểu mẫu. Việc ngày đến còn chỗ hay người đặt có được phép sử dụng dịch vụ cần được kiểm tra trong ca sử dụng.

Không nên dùng Domain Entity làm trực tiếp đối tượng nhận toàn bộ request. Một request DTO riêng giúp kiểm soát các trường được bind và giảm nguy cơ mass assignment, trong đó người dùng gửi thêm trường nhạy cảm như role, status, ownerId hoặc price để thử ghi đè trạng thái nội bộ.

## 7. Xử lý lỗi trong Spring MVC

Spring MVC hỗ trợ Bean Validation và BindingResult để Controller nhận lỗi binding hoặc validation cùng với đối tượng form.

### 7.1. Controller nhận dữ liệu và trả lại biểu mẫu

Ví dụ:

~~~java
@Controller
@RequestMapping("/bookings")
public class BookingController {
    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("bookingForm", new BookingForm());
        return "bookings/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("bookingForm") BookingForm form,
            BindingResult bindingResult,
            Model model) {

        if (bindingResult.hasErrors()) {
            populateFormOptions(model);
            return "bookings/new";
        }

        try {
            BookingCommand command = new BookingCommand(
                form.getFullName(),
                form.getEmail(),
                form.getGuests(),
                form.getArrivalDate(),
                form.getNote()
            );

            BookingConfirmation result = bookingService.create(command);
            return "redirect:/bookings/" + result.id();

        } catch (EmailAlreadyUsedException ex) {
            bindingResult.rejectValue(
                "email",
                "booking.email.alreadyUsed"
            );
            populateFormOptions(model);
            return "bookings/new";

        } catch (BookingRuleViolationException ex) {
            bindingResult.reject(
                "booking.rule.invalid",
                "Không thể hoàn tất yêu cầu đặt chỗ."
            );
            populateFormOptions(model);
            return "bookings/new";
        }
    }

    private void populateFormOptions(Model model) {
        // Nạp lại danh sách lựa chọn cần thiết cho biểu mẫu.
    }
}
~~~

Có một số quy tắc quan trọng:

1. @Valid kích hoạt kiểm tra trên form model.
2. BindingResult phải đứng ngay sau tham số được kiểm tra để Spring gắn lỗi vào đúng đối tượng.
3. Khi có lỗi, Controller trả lại cùng View và giữ đối tượng form trong model.
4. Nếu View cần danh sách lựa chọn, dữ liệu phụ trợ phải được nạp lại trước khi render.
5. Lỗi nghiệp vụ có thể được ánh xạ vào một trường hoặc lỗi chung bằng rejectValue và reject.
6. Khi thành công, Controller chuyển hướng để tránh trình duyệt gửi lại POST khi người dùng tải lại trang kết quả.

Trong ví dụ, BookingCommand, BookingConfirmation, các getter/setter và phần triển khai service được lược bỏ để tập trung vào luồng phản hồi. Trong hệ thống thực tế, chỉ chuyển những trường hợp lỗi đã được phân loại và có thể trình bày an toàn thành thông báo cho người dùng. Lỗi không dự kiến cần đi qua cơ chế xử lý lỗi tập trung và được ghi log ở phía máy chủ.

### 7.2. Phân biệt lỗi theo trường và lỗi chung

BindingResult có thể chứa:

- FieldError: lỗi gắn với một trường cụ thể, chẳng hạn email sai định dạng.
- ObjectError: lỗi áp dụng cho toàn bộ đối tượng, chẳng hạn ngày kết thúc phải sau ngày bắt đầu.

Dùng rejectValue("email", ...) khi người dùng có thể sửa một trường cụ thể. Dùng reject(...) khi lỗi liên quan đến nhiều trường hoặc toàn bộ thao tác. Tránh gắn lỗi vào một trường tùy tiện chỉ để thông báo xuất hiện trên trang.

### 7.3. Lỗi chuyển đổi dữ liệu

Một trường ngày có thể gửi chuỗi không thể chuyển thành LocalDate. Khi đó, Spring ghi nhận lỗi binding. Đây không nhất thiết là lỗi do @NotNull; quá trình chuyển đổi đã thất bại trước khi validation hoàn tất.

Thông báo nên hướng dẫn định dạng mà người dùng cần nhập, chẳng hạn “Nhập ngày theo định dạng ngày/tháng/năm”. Không hiển thị tên lớp Java, stack trace hoặc thông tin chuyển đổi nội bộ.

### 7.4. Không nuốt lỗi

Không nên bắt mọi exception rồi chuyển thành “Dữ liệu không hợp lệ”. Điều này làm người dùng hiểu sai nguyên nhân và khiến nhóm phát triển khó phát hiện lỗi hệ thống.

Hãy phân loại rõ:

- Lỗi validation có thể sửa trực tiếp trên biểu mẫu.
- Lỗi nghiệp vụ có thể giải thích và yêu cầu người dùng chọn hành động khác.
- Lỗi xung đột cần tải lại dữ liệu hoặc xác nhận trạng thái mới.
- Lỗi kỹ thuật cần thông báo chung, mã tham chiếu hỗ trợ nếu phù hợp và log nội bộ.

## 8. Hiển thị lỗi trong View

View cần giúp người dùng hiểu lỗi mà không phải đoán. Một trang biểu mẫu có thể dùng hai vị trí hiển thị:

- Phần tóm tắt lỗi ở đầu biểu mẫu để người dùng biết có vấn đề và điều hướng đến trường cần sửa.
- Thông báo cạnh từng trường để giải thích cụ thể.

Không nên chỉ dùng một thông báo tổng quát ở đầu trang nếu người dùng phải tự tìm trường nào sai.

### 8.1. Tóm tắt lỗi và liên kết đến trường

Ví dụ Thymeleaf:

~~~html
<form th:action="@{/bookings}"
      th:object="${bookingForm}"
      method="post">

    <div th:if="${#fields.hasErrors('*')}"
         id="error-summary"
         class="error-summary"
         role="alert"
         tabindex="-1">
        <h2>Vui lòng kiểm tra lại thông tin</h2>
        <ul>
            <li th:if="${#fields.hasErrors('fullName')}">
                <a href="#fullName"
                   th:text="${#fields.errors('fullName')[0]}">
                    Kiểm tra họ tên
                </a>
            </li>
            <li th:if="${#fields.hasErrors('email')}">
                <a href="#email"
                   th:text="${#fields.errors('email')[0]}">
                    Kiểm tra email
                </a>
            </li>
            <li th:if="${#fields.hasErrors('guests')}">
                <a href="#guests"
                   th:text="${#fields.errors('guests')[0]}">
                    Kiểm tra số người
                </a>
            </li>
            <li th:if="${#fields.hasErrors('arrivalDate')}">
                <a href="#arrivalDate"
                   th:text="${#fields.errors('arrivalDate')[0]}">
                    Kiểm tra ngày đến
                </a>
            </li>
            <li th:each="err : ${#fields.globalErrors()}"
                th:text="${err}">
                Lỗi chung của biểu mẫu
            </li>
        </ul>
    </div>

    <!-- Các trường biểu mẫu -->
</form>
~~~

Phần tóm tắt dùng liên kết đến id của trường. Người dùng có thể chọn thông báo để chuyển đến vị trí cần sửa. Trong một biểu mẫu có nhiều trường, có thể tạo danh sách lỗi động bằng helper hoặc presenter thay vì viết từng trường thủ công.

Nếu trang render lỗi sau một lần POST, cân nhắc đưa tiêu điểm đến phần tóm tắt bằng một cách phù hợp với cấu trúc trang. Không tự động giật tiêu điểm trong mọi lần tải trang; hãy bảo đảm hành vi có thể dự đoán và không làm gián đoạn người dùng.

### 8.2. Hiển thị lỗi cạnh trường

Ví dụ cho trường email:

~~~html
<div class="form-field">
    <label for="email">Địa chỉ email</label>

    <input id="email"
           type="email"
           th:field="*{email}"
           autocomplete="email"
           required
           th:attr="
             aria-invalid=${#fields.hasErrors('email')} ? 'true' : null,
             aria-describedby=${#fields.hasErrors('email')} ? 'email-error' : null">

    <p id="email-error"
       class="field-error"
       th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}">
        Vui lòng nhập email hợp lệ.
    </p>
</div>
~~~

Một thông báo lỗi cần:

- Nằm gần trường liên quan.
- Có id ổn định để trường tham chiếu bằng aria-describedby.
- Được liên kết về mặt ngữ nghĩa với trường.
- Có nội dung dễ hiểu, nêu cách sửa.
- Không chỉ dựa vào màu sắc hoặc biểu tượng.

aria-invalid="true" cho biết trường hiện không hợp lệ. aria-describedby liên kết trường với thông báo. Khi không có lỗi, có thể bỏ các thuộc tính này thay vì gắn thông tin lỗi rỗng.

### 8.3. Giữ lại dữ liệu người dùng đã nhập

Khi biểu mẫu không hợp lệ, người dùng không nên phải nhập lại toàn bộ dữ liệu. Spring MVC giữ form object và các giá trị binding trong model; Thymeleaf th:field dùng giá trị tương ứng để render lại trường.

Ví dụ:

~~~html
<label for="fullName">Họ và tên</label>
<input id="fullName"
       type="text"
       th:field="*{fullName}"
       autocomplete="name"
       maxlength="80"
       required>

<p th:if="${#fields.hasErrors('fullName')}"
   id="fullName-error"
   th:errors="*{fullName}">
    Vui lòng nhập họ tên.
</p>
~~~

Không nên tạo một đối tượng form mới sau khi validation thất bại, vì thao tác đó làm mất dữ liệu đã nhập và trạng thái lỗi. Hãy trả lại chính form object đã bind.

Có những dữ liệu không nên điền lại vào HTML sau lỗi, chẳng hạn mật khẩu, mã xác thực một lần, thông tin thanh toán nhạy cảm hoặc dữ liệu bí mật. Với những trường này, xóa giá trị nhạy cảm và yêu cầu người dùng nhập lại nếu cần. Tương tự, không phản chiếu nội dung tải lên hoặc dữ liệu lớn vào trang lỗi một cách tùy tiện.

### 8.4. Giữ dữ liệu phụ trợ của biểu mẫu

Biểu mẫu có thể chứa danh sách quốc gia, danh mục, lựa chọn thời gian hoặc dữ liệu tham chiếu khác. Khi trả lại View, Controller cần nạp lại các dữ liệu này. Nếu không, trang lỗi có thể thiếu option hoặc không render được.

Hãy gom việc nạp dữ liệu dùng chung vào một phương thức hoặc model attribute phù hợp để tránh mỗi nhánh lỗi quên một phần dữ liệu.

## 9. Viết thông báo lỗi hữu ích

Thông báo lỗi là một phần của hợp đồng tương tác. Một thông báo tốt giúp người dùng biết vấn đề và cách giải quyết.

### 9.1. Cấu trúc thông báo

Một thông báo nên trả lời được hai câu hỏi:

- Điều gì chưa đúng?
- Người dùng cần làm gì tiếp theo?

Ví dụ:

| Thông báo mơ hồ | Thông báo hữu ích hơn |
|---|---|
| Giá trị không hợp lệ | Nhập số người từ 1 đến 8 |
| Lỗi email | Nhập địa chỉ email theo dạng ten@example.com |
| Ngày sai | Chọn ngày đến từ hôm nay trở đi |
| Không thể xử lý | Ngày trả phòng phải sau ngày nhận phòng |
| Thất bại | Khung giờ này vừa hết chỗ. Hãy chọn khung giờ khác |

Tránh đổ lỗi cho người dùng, dùng thuật ngữ kỹ thuật hoặc đưa ra thông báo không nói được cách khắc phục.

### 9.2. Dùng message code và đa ngôn ngữ

Không nên viết cứng mọi thông báo trong Controller hoặc template. Dùng message key để có thể dịch và điều chỉnh nội dung tập trung.

Ví dụ trong messages.properties:

~~~properties
booking.name.required=Vui lòng nhập họ và tên.
booking.name.tooLong=Họ và tên không được vượt quá 80 ký tự.
booking.email.required=Vui lòng nhập địa chỉ email.
booking.email.invalid=Địa chỉ email chưa đúng định dạng.
booking.email.tooLong=Địa chỉ email quá dài.
booking.guests.required=Vui lòng chọn số người.
booking.guests.min=Số người tối thiểu là 1.
booking.guests.max=Số người tối đa là 8.
booking.date.required=Vui lòng chọn ngày đến.
booking.note.tooLong=Ghi chú không được vượt quá 500 ký tự.
booking.email.alreadyUsed=Địa chỉ email này đã được sử dụng.
booking.rule.invalid=Không thể hoàn tất yêu cầu đặt chỗ.
~~~

Có thể cung cấp các file tương ứng cho từng ngôn ngữ. Ứng dụng chọn locale theo cấu hình, tùy chọn người dùng hoặc header Accept-Language, tùy chính sách sản phẩm.

Khi dùng rejectValue hoặc reject, hãy truyền message code ổn định. View và MessageSource sẽ chịu trách nhiệm lấy thông báo theo locale. Điều này giúp cùng một lỗi nghiệp vụ có thể được trình bày bằng nhiều ngôn ngữ.

### 9.3. Tránh tiết lộ thông tin

Thông báo cần đủ hữu ích nhưng không được làm lộ thông tin nội bộ. Ví dụ, thay vì hiển thị câu lệnh SQL hoặc tên bảng, hãy dùng thông báo nghiệp vụ. Trong một số luồng xác thực, thông báo “Email không tồn tại” có thể giúp kẻ tấn công dò tài khoản; hãy chọn nội dung trung tính theo yêu cầu bảo mật.

Không đưa stack trace, đường dẫn máy chủ, tên lớp, thông tin kết nối hoặc dữ liệu cá nhân của người khác vào trang lỗi. Ghi chi tiết kỹ thuật trong log có kiểm soát và tránh ghi mật khẩu, token hoặc dữ liệu nhạy cảm.

## 10. Phản hồi lỗi cho API

API JSON cũng cần hợp đồng lỗi rõ ràng. Client không thể dựa vào vị trí hiển thị trong HTML; nó cần mã trạng thái và cấu trúc dữ liệu có thể đọc bằng chương trình.

Một phản hồi validation có thể có dạng:

~~~json
{
  "type": "https://example.com/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "errors": [
    {
      "field": "email",
      "code": "booking.email.invalid",
      "message": "Địa chỉ email chưa đúng định dạng."
    },
    {
      "field": "guests",
      "code": "booking.guests.max",
      "message": "Số người tối đa là 8."
    }
  ]
}
~~~

Đây là ví dụ hợp đồng; tên trường và mã trạng thái cần được thống nhất trong API của hệ thống.

Một số quy ước thường gặp:

- 400 Bad Request: request sai cú pháp hoặc không thể binding theo hợp đồng.
- 401 Unauthorized: chưa xác thực.
- 403 Forbidden: đã xác thực nhưng không có quyền.
- 404 Not Found: tài nguyên không tồn tại hoặc không được công bố.
- 409 Conflict: trạng thái hiện tại xung đột với thao tác, ví dụ phiên bản dữ liệu đã thay đổi.
- 422 Unprocessable Content: request có cấu trúc hợp lệ nhưng nội dung không vượt qua validation ngữ nghĩa, nếu API chọn quy ước này.
- 500 Internal Server Error: lỗi ngoài dự kiến ở phía máy chủ.

Không có một cách phân loại duy nhất bắt buộc cho mọi API. Điều quan trọng là tài liệu hóa và sử dụng nhất quán để client có thể xử lý đúng.

### 10.1. Tách mã lỗi và thông báo

Client nên có thể dựa vào code hoặc field để quyết định vị trí hiển thị, thay vì phân tích chuỗi thông báo. Message có thể được dịch hoặc thay đổi; mã lỗi ổn định giúp client không phụ thuộc vào câu chữ.

Ví dụ, client có thể ánh xạ booking.email.invalid vào trường email và hiển thị thông báo theo ngôn ngữ hiện tại. Với lỗi chung, client đặt thông báo trong khu vực trạng thái của biểu mẫu.

### 10.2. Không trả chi tiết nội bộ

API không nên trả stack trace, câu truy vấn, đường dẫn file, tên máy chủ hoặc thông tin nhạy cảm. Nếu cần mã tham chiếu để hỗ trợ, hãy tạo mã theo dõi không tiết lộ dữ liệu nội bộ và ghi tương ứng trong log máy chủ.

### 10.3. Cập nhật giao diện bất đồng bộ

Với form gửi bằng fetch hoặc XMLHttpRequest, client cần xử lý cả phản hồi thành công và không thành công. Khi nhận lỗi validation, giao diện cần:

1. Xóa lỗi cũ đã không còn phù hợp.
2. Đọc danh sách lỗi theo trường và lỗi chung.
3. Gắn thông báo vào đúng trường.
4. Đánh dấu trường không hợp lệ và liên kết với thông báo.
5. Cập nhật phần tóm tắt lỗi.
6. Đưa tiêu điểm đến khu vực lỗi hoặc trường đầu tiên cần sửa theo hành vi đã thiết kế.

Không nên chỉ hiện một toast rồi để người dùng tự tìm trường sai. Nếu request thất bại do mất mạng hoặc máy chủ tạm thời không khả dụng, đó là trạng thái kỹ thuật khác với validation và cần thông báo tương ứng.

## 11. Khả năng truy cập và trải nghiệm người dùng

Phản hồi lỗi cần dùng được bằng chuột, bàn phím, trình đọc màn hình và thiết bị có kích thước khác nhau.

### 11.1. Nhãn và mô tả rõ ràng

Mỗi trường cần có label được liên kết bằng for và id. Placeholder không thay thế label vì placeholder biến mất khi người dùng nhập và thường có độ tương phản thấp.

Nếu trường có hướng dẫn, liên kết hướng dẫn bằng aria-describedby. Khi có lỗi, bổ sung id của thông báo lỗi vào quan hệ mô tả để công nghệ hỗ trợ có thể đọc cả hướng dẫn và lỗi.

### 11.2. Không chỉ dùng màu sắc

Nếu trường sai được tô viền đỏ, cần thêm nội dung hoặc biểu tượng có ý nghĩa. Người dùng không phân biệt được màu hoặc dùng chế độ tương phản cao vẫn phải nhận biết được trường lỗi.

CSS minh họa:

~~~css
.field-error {
    margin-top: 0.35rem;
    color: #b42318;
    font-size: 0.95rem;
}

input[aria-invalid="true"],
select[aria-invalid="true"],
textarea[aria-invalid="true"] {
    border: 2px solid #b42318;
}

.error-summary {
    border: 2px solid #b42318;
    padding: 1rem;
    margin-bottom: 1.5rem;
}
~~~

Trong giao diện thực tế, cần kiểm tra độ tương phản của chữ, viền và trạng thái focus theo tiêu chuẩn tiếp cận được dự án áp dụng.

### 11.3. Điều hướng bàn phím và focus

Sau khi gửi biểu mẫu không hợp lệ, người dùng cần tìm được lỗi đầu tiên một cách dễ dàng. Có thể đặt focus vào tiêu đề tóm tắt lỗi hoặc trường đầu tiên có lỗi. Liên kết trong phần tóm tắt cần đưa focus đến đúng trường.

Không làm thay đổi thứ tự tab một cách khó đoán. Tránh dùng tabindex dương; dùng thứ tự DOM hợp lý và chỉ dùng tabindex="-1" cho vùng cần nhận focus bằng script hoặc điều hướng chủ động.

### 11.4. Thông báo động

Với giao diện cập nhật lỗi mà không tải lại trang, có thể dùng vùng aria-live="polite" để thông báo kết quả cho trình đọc màn hình. Dùng role="alert" cho thông báo cần được đọc ngay, nhưng không nên gắn quá nhiều alert vì có thể làm gián đoạn người dùng.

Nếu trang được render lại hoàn toàn sau POST, cấu trúc tiêu đề, phần tóm tắt lỗi và focus có thể đã đủ để người dùng nhận biết thay đổi. Cần kiểm thử bằng trình đọc màn hình thay vì chỉ dựa vào thuộc tính ARIA.

### 11.5. Trợ giúp nhập liệu

Dùng đúng loại input và thuộc tính hỗ trợ:

- type="email" cho địa chỉ email.
- type="date" cho ngày nếu phù hợp với thiết bị và định dạng.
- inputmode="numeric" cho dữ liệu số trên bàn phím di động.
- autocomplete cho tên, email, địa chỉ và thông tin phù hợp.
- min, max, maxlength để công bố giới hạn có thể kiểm tra ngay.

Các thuộc tính này cải thiện trải nghiệm nhưng không thay thế kiểm tra phía máy chủ.

## 12. Bảo mật khi xử lý dữ liệu không hợp lệ

Request từ trình duyệt luôn phải được xem là dữ liệu không đáng tin cậy. Luồng lỗi cũng có thể tạo ra lỗ hổng nếu ứng dụng phản chiếu dữ liệu hoặc thông báo không an toàn.

### 12.1. Chỉ bind các trường được phép

Dùng form model hoặc DTO chuyên biệt với danh sách trường rõ ràng. Không bind trực tiếp request vào entity có các trường nhạy cảm như vai trò, trạng thái duyệt, giá, chủ sở hữu hoặc quyền hạn.

Khi dùng Spring DataBinder, có thể giới hạn các trường được bind như một lớp bảo vệ bổ sung. Tuy vậy, DTO chuyên biệt vẫn là cách rõ ràng để xác định hợp đồng đầu vào.

### 12.2. Escape nội dung khi render

Thông báo lỗi có thể chứa giá trị người dùng gửi lên. Không chèn dữ liệu này vào HTML bằng cơ chế render không escape. Với Thymeleaf, ưu tiên th:text cho nội dung văn bản và th:field cho binding biểu mẫu; tránh dùng th:utext với dữ liệu không đáng tin cậy.

Ví dụ, không nên nối chuỗi đầu vào trực tiếp vào HTML:

~~~java
String html = "<p>Giá trị " + userInput + " không hợp lệ</p>";
~~~

Hãy để template engine escape nội dung theo ngữ cảnh phù hợp. Việc escape đầu ra giúp giảm nguy cơ Cross-Site Scripting (XSS).

### 12.3. Chống CSRF và kiểm soát quyền

Các biểu mẫu thay đổi dữ liệu cần được bảo vệ bằng CSRF token khi ứng dụng sử dụng cơ chế session/cookie phù hợp. Kiểm tra quyền phải được thực hiện ở máy chủ cho từng tài nguyên và hành động; không dựa vào việc ẩn nút hoặc trường trên giao diện.

Một request có thể vượt qua validation nhưng vẫn không được phép thực hiện. Khi đó, phản hồi cần thể hiện lỗi quyền phù hợp, không giả dạng lỗi nhập liệu.

### 12.4. Không ghi dữ liệu nhạy cảm vào log

Không ghi mật khẩu, token, mã OTP, thông tin thẻ hoặc nội dung nhạy cảm vào log validation. Nếu cần log lỗi để chẩn đoán, chỉ ghi mã lỗi, định danh tương quan và thông tin tối thiểu đã được làm sạch.

## 13. Các tình huống khó và cách xử lý

### 13.1. Trạng thái thay đổi sau khi người dùng mở form

Người dùng mở biểu mẫu khi còn chỗ, nhưng một người khác đặt chỗ trước khi request đầu tiên được xử lý. Kiểm tra lúc render form không còn đủ giá trị.

Ca sử dụng phải kiểm tra lại số chỗ tại thời điểm thực hiện thao tác và lưu thay đổi trong một giao dịch phù hợp. Nếu không còn chỗ, trả lại form với thông báo cụ thể và giữ các trường không nhạy cảm. Nếu trạng thái đã xung đột, có thể yêu cầu người dùng tải lại lựa chọn.

### 13.2. Nhiều lỗi trên cùng một trường

Một trường có thể vi phạm nhiều ràng buộc, ví dụ vừa trống vừa không đạt định dạng. Hiển thị mọi thông báo có thể làm người dùng quá tải. Hãy xác định thứ tự ưu tiên hoặc chỉ hiển thị lỗi hữu ích nhất tại thời điểm đó.

Ví dụ, nếu email trống thì thông báo “Vui lòng nhập email” thường hữu ích hơn “Email sai định dạng”. Tránh hiển thị hai thông báo mâu thuẫn cho cùng một giá trị.

### 13.3. Lỗi giữa nhiều trường

Nếu ngày kết thúc phải sau ngày bắt đầu, lỗi cần chỉ ra quan hệ giữa hai trường. Có thể hiển thị lỗi chung ở đầu biểu mẫu và liên kết đến trường cần điều chỉnh. Nếu một trường là nguyên nhân rõ ràng, gắn lỗi vào trường đó để người dùng không phải đoán.

### 13.4. Biểu mẫu nhiều bước

Trong biểu mẫu nhiều bước, cần quyết định lỗi của bước hiện tại có làm mất dữ liệu của bước trước hay không. Lưu trạng thái tạm thời ở phía máy chủ hoặc trong một phiên làm việc có kiểm soát. Không tin dữ liệu nhiều bước chỉ vì nó đã được gửi ở bước trước; kiểm tra lại quyền và các quy tắc quan trọng khi hoàn tất.

### 13.5. Gửi biểu mẫu lặp lại

Người dùng có thể nhấn nút gửi nhiều lần hoặc trình duyệt gửi lại request. Với thao tác tạo giao dịch, cân nhắc idempotency key hoặc cơ chế chống tạo bản ghi trùng. PRG giúp tránh một số lần gửi lại do tải lại trang kết quả, nhưng không tự giải quyết mọi tình huống request lặp hoặc retry từ mạng.

### 13.6. Lỗi mạng và timeout

Khi request không nhận được phản hồi, client không biết chắc máy chủ đã xử lý thành công hay chưa. Không nên yêu cầu người dùng nhập lại toàn bộ dữ liệu mà không giải thích trạng thái. Với thao tác có thể tạo dữ liệu trùng, dùng mã idempotency hoặc cung cấp cách tra cứu trạng thái yêu cầu.

### 13.7. Lỗi upload tệp

Upload có thể thất bại vì kích thước, loại tệp, nội dung hoặc lỗi lưu trữ. Phản hồi nên nêu giới hạn có thể hiểu được và chỉ rõ tệp nào cần chọn lại. Kiểm tra MIME type và phần mở rộng ở client chỉ là hỗ trợ; máy chủ cần kiểm tra nội dung, giới hạn kích thước, tên lưu trữ và quyền truy cập. Không đưa đường dẫn lưu trữ nội bộ vào thông báo.

## 14. Kiểm thử luồng phản hồi

Kiểm thử cần xác nhận cả quy tắc validation và hành vi người dùng quan sát được.

### 14.1. Unit test cho form validation và Domain Model

Có thể kiểm tra form model bằng Jakarta Validator:

~~~java
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();

BookingForm form = new BookingForm();
form.setFullName("");
form.setEmail("not-an-email");
form.setGuests(0);

Set<ConstraintViolation<BookingForm>> violations =
    validator.validate(form);

assertFalse(violations.isEmpty());
~~~

Ví dụ minh họa cần các import và fixture phù hợp với dự án. Ngoài form model, unit test Domain Model nên kiểm tra các bất biến quan trọng và các trường hợp biên như số lượng âm, trạng thái không cho phép hoặc dữ liệu thiếu.

### 14.2. Kiểm thử Controller với MockMvc

Một kiểm thử MVC có thể gửi dữ liệu không hợp lệ và xác nhận Controller trả lại đúng View cùng lỗi:

~~~java
mockMvc.perform(post("/bookings")
        .param("fullName", "An")
        .param("email", "sai-dinh-dang")
        .param("guests", "0")
        .param("arrivalDate", "2030-04-20"))
    .andExpect(status().isOk())
    .andExpect(view().name("bookings/new"))
    .andExpect(model().attributeHasFieldErrors(
        "bookingForm", "email", "guests"
    ));
~~~

Trong test thực tế, cần thiết lập security context hoặc CSRF token nếu ứng dụng bật Spring Security. Các phụ thuộc service nên được mock để xác nhận ca sử dụng không bị gọi khi lỗi binding hoặc validation đã đủ để từ chối request.

### 14.3. Kiểm thử nghiệp vụ

Kiểm tra các trường hợp như:

- Hết chỗ sau khi người dùng mở biểu mẫu.
- Email đã tồn tại.
- Người dùng không có quyền thực hiện thao tác.
- Trạng thái tài nguyên đã thay đổi.
- Ràng buộc unique bị vi phạm trong lúc ghi dữ liệu.

Những test này xác nhận lỗi được chuyển từ ca sử dụng hoặc tầng lưu trữ thành kết quả có thể xử lý.

### 14.4. Kiểm thử View và khả năng truy cập

Kiểm tra rằng:

- Trường có label đúng.
- Lỗi xuất hiện cạnh trường liên quan.
- Phần tóm tắt có liên kết đến trường.
- Trường lỗi có aria-invalid và tham chiếu thông báo.
- Dữ liệu không nhạy cảm được giữ lại sau lỗi.
- Dữ liệu bí mật không được render lại.
- Lỗi không chỉ được biểu thị bằng màu.
- Có thể điều hướng và sửa biểu mẫu bằng bàn phím.

Có thể bổ sung kiểm thử tự động về HTML và accessibility, nhưng vẫn cần kiểm tra thủ công với bàn phím và trình đọc màn hình ở các luồng quan trọng.

### 14.5. Ma trận tình huống

| Tình huống | Kết quả mong đợi |
|---|---|
| Trường bắt buộc bị bỏ trống | Lỗi tại trường, giữ các giá trị khác |
| Sai định dạng email | Thông báo định dạng rõ ràng |
| Chuỗi ngày không chuyển đổi được | Lỗi binding, form được hiển thị lại |
| Vi phạm quy tắc giữa hai trường | Lỗi chung hoặc gắn với trường phù hợp |
| Hết chỗ ở thời điểm gửi | Thông báo nghiệp vụ, không tạo đặt chỗ |
| Request không có quyền | Phản hồi quyền truy cập phù hợp |
| Cơ sở dữ liệu gặp sự cố | Thông báo lỗi hệ thống an toàn |
| Gửi lại request thành công | Không tạo bản ghi trùng ngoài ý muốn |

## 15. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra ở trình duyệt

JavaScript có thể bị tắt hoặc bị bỏ qua. Nếu máy chủ tin rằng dữ liệu đã hợp lệ vì giao diện có required, ứng dụng có thể lưu dữ liệu sai hoặc bị khai thác. Hãy thực hiện validation ở phía máy chủ và bảo vệ bất biến trong Model.

### Đưa toàn bộ validation vào Controller

Controller dễ trở thành nơi chứa mọi quy tắc, làm logic khó tái sử dụng và khó kiểm thử. Giữ kiểm tra hợp đồng request ở ranh giới; chuyển quy tắc nghiệp vụ vào ca sử dụng hoặc Domain Model.

### Hiển thị lỗi chung cho mọi trường hợp

Thông báo “Có lỗi xảy ra” không giúp người dùng biết cần sửa gì. Phân biệt lỗi trường, lỗi chung, lỗi nghiệp vụ và lỗi hệ thống để trình bày phù hợp.

### Xóa toàn bộ dữ liệu sau một lỗi

Việc tạo form object mới hoặc redirect không giữ trạng thái có thể khiến người dùng phải nhập lại mọi thứ. Trả lại form object đã bind và giữ những dữ liệu an toàn để tái sử dụng.

### Chỉ tô đỏ trường bị lỗi

Màu sắc không đủ để truyền tải thông tin. Dùng văn bản, liên kết ngữ nghĩa và trạng thái có thể nhận biết bằng công nghệ hỗ trợ.

### Hiển thị thông báo kỹ thuật

Tên exception, stack trace, câu lệnh SQL hoặc chi tiết server không phải hướng dẫn cho người dùng. Ánh xạ lỗi sang thông báo nghiệp vụ an toàn; giữ chi tiết kỹ thuật trong log có kiểm soát.

### Bắt mọi exception rồi coi là validation

Điều này che giấu lỗi hệ thống và khiến người dùng sửa dữ liệu không liên quan. Phân loại lỗi có thể dự đoán, xung đột và sự cố kỹ thuật.

### Bind trực tiếp entity

Client có thể gửi thêm trường ngoài dự kiến để thay đổi quyền, trạng thái hoặc dữ liệu nội bộ. Dùng form model hoặc DTO chỉ chứa các trường được phép.

### Lặp validation nhưng không có nguồn quy tắc rõ ràng

Cùng một giới hạn có thể bị khai báo khác nhau ở JavaScript, DTO và Domain Model. Hãy xác định quy tắc chuẩn ở tầng phù hợp, sau đó đồng bộ thông tin hiển thị ở client. Các ràng buộc bảo mật và nghiệp vụ vẫn phải được thực thi ở máy chủ.

## 16. Quy trình thiết kế phản hồi lỗi

Khi xây dựng một biểu mẫu hoặc endpoint mới, có thể thực hiện theo trình tự sau:

1. **Xác định hợp đồng đầu vào.** Liệt kê trường được phép gửi, kiểu dữ liệu, giới hạn và trường nhạy cảm.
2. **Phân loại quy tắc.** Xác định kiểm tra nào thuộc cấu trúc, trường, nhiều trường, nghiệp vụ hoặc lưu trữ.
3. **Chọn vị trí thực thi.** Dùng HTML/JavaScript để hỗ trợ; dùng DTO, ca sử dụng và Domain Model để bảo vệ phía máy chủ.
4. **Định nghĩa mã lỗi.** Tạo message code ổn định và quy ước lỗi chung.
5. **Thiết kế phản hồi HTML.** Có tóm tắt lỗi, lỗi cạnh trường, dữ liệu được giữ lại và điều hướng rõ ràng.
6. **Thiết kế phản hồi API.** Chuẩn hóa mã trạng thái, mã lỗi, tên trường và cấu trúc dữ liệu.
7. **Xử lý dữ liệu nhạy cảm.** Xóa hoặc không render lại giá trị bí mật; escape nội dung khi hiển thị.
8. **Kiểm tra khả năng truy cập.** Bảo đảm label, focus, thông báo và điều hướng bàn phím hoạt động.
9. **Kiểm thử các tình huống biên.** Bao gồm binding, validation, lỗi nghiệp vụ, xung đột và sự cố kỹ thuật.
10. **Rà soát tính nhất quán.** Đảm bảo cùng một lỗi được diễn giải ổn định trên các điểm vào và ngôn ngữ hỗ trợ.

Trước khi hoàn tất, hãy tự hỏi:

- Máy chủ có kiểm tra lại mọi dữ liệu không đáng tin cậy không?
- Người dùng có biết trường nào cần sửa và cách sửa không?
- Dữ liệu đã nhập có được giữ lại một cách an toàn không?
- Lỗi nghiệp vụ có bị nhầm với lỗi kỹ thuật không?
- Thông báo có làm lộ thông tin nhạy cảm hoặc nội bộ không?
- Người dùng bàn phím và trình đọc màn hình có tìm thấy lỗi không?
- API client có thể xử lý lỗi bằng mã ổn định mà không phân tích câu chữ không?

## 17. Kết luận

Phản hồi khi dữ liệu nhập không hợp lệ là một phần cốt lõi của luồng tương tác trong MVC. Trình duyệt giúp phát hiện lỗi sớm; Controller và form model kiểm tra hợp đồng đầu vào; ca sử dụng và Domain Model bảo vệ quy tắc nghiệp vụ; cơ sở dữ liệu giữ toàn vẹn dữ liệu khi có thao tác đồng thời. View trình bày lỗi theo trường và lỗi chung, giữ lại dữ liệu phù hợp và hướng dẫn người dùng tiếp tục.

Khi các trách nhiệm này được đặt đúng chỗ, ứng dụng vừa bảo vệ được dữ liệu vừa tạo trải nghiệm dễ hiểu. Một luồng lỗi được thiết kế tốt giúp người dùng sửa đúng vấn đề, giúp API client xử lý kết quả nhất quán và giúp nhóm phát triển kiểm thử hành vi ở từng ranh giới.

