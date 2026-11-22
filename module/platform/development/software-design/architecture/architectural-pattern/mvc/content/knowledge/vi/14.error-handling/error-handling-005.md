# Xử lý lỗi tập trung và giới hạn xử lý tại từng Controller

Trong ứng dụng MVC, lỗi có thể phát sinh khi binding request, kiểm tra dữ liệu, thực hiện quy tắc nghiệp vụ, truy cập cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài. Nếu mỗi Controller tự bắt mọi exception rồi tự tạo response, cách xử lý sẽ dễ lặp lại và không nhất quán. Nếu chuyển toàn bộ lỗi vào một bộ xử lý toàn cục mà không xét ngữ cảnh, những trường hợp cần phản hồi riêng cho biểu mẫu hoặc luồng giao diện cũng trở nên khó xử lý.

Thiết kế phù hợp là phân chia trách nhiệm: **xử lý tập trung** dành cho chính sách chung như ánh xạ exception thành HTTP response, định dạng lỗi API, mã lỗi, logging và correlation ID; **xử lý tại Controller** dành cho tình huống có ý nghĩa riêng với màn hình hoặc thao tác hiện tại, chẳng hạn hiển thị lỗi ngay cạnh trường biểu mẫu, giữ lại dữ liệu người dùng nhập hoặc chọn một nhánh điều hướng có thể phục hồi.

Trong MVC, Controller tiếp nhận request và quyết định response; Model hoặc dịch vụ ứng dụng phát hiện và biểu diễn lỗi nghiệp vụ; View trình bày thông báo phù hợp. Bộ xử lý lỗi cần giữ rõ ranh giới này, tránh để lỗi kỹ thuật rò rỉ ra giao diện hoặc làm mất thông tin cần thiết để người dùng sửa dữ liệu.

## 1. Vì sao cần một chiến lược xử lý lỗi?

Một ứng dụng web có nhiều loại lỗi với nguyên nhân và cách phản hồi khác nhau:

- Request sai định dạng hoặc thiếu trường bắt buộc.
- Người dùng không có quyền thực hiện thao tác.
- Tài nguyên không tồn tại hoặc đã bị xóa.
- Thao tác không hợp lệ với trạng thái nghiệp vụ hiện tại.
- Database hoặc dịch vụ bên ngoài tạm thời không sẵn sàng.
- Lỗi lập trình không dự kiến.

Nếu tất cả lỗi đều được xử lý bằng một khối try/catch trong từng Controller, mã nguồn sẽ lặp lại việc chọn status code, tạo body lỗi, ghi log và ẩn thông tin nội bộ. Một endpoint có thể trả 404 cho tài nguyên không tồn tại, endpoint khác lại trả 500 cho cùng tình huống. Client khó xử lý nhất quán và người dùng nhận thông báo khó hiểu.

Ngược lại, một bộ xử lý toàn cục không thể tự quyết định mọi chi tiết giao diện. Khi biểu mẫu tạo công việc có lỗi ở trường tiêu đề, trang cần giữ nội dung người dùng vừa nhập và hiển thị lỗi đúng cạnh trường đó. Đây là ngữ cảnh riêng của màn hình hiện tại, Controller có thể xử lý trực tiếp.

Một chiến lược tốt cần trả lời ba câu hỏi:

1. Lỗi thuộc loại nào và thành phần nào có đủ ngữ cảnh để nhận diện?
2. Lỗi cần được chuyển thành kết quả nào cho giao thức hoặc giao diện?
3. Thông tin nào được phép gửi cho người dùng, thông tin nào chỉ được ghi log nội bộ?

## 2. Phân biệt phát hiện lỗi, lan truyền lỗi và xử lý lỗi

Ba hoạt động này có liên quan nhưng không đồng nhất:

| Hoạt động | Trách nhiệm | Ví dụ |
|---|---|---|
| **Phát hiện lỗi** | Nhận ra điều kiện không hợp lệ | Model phát hiện không thể hoàn tất công việc đã bị hủy |
| **Lan truyền lỗi** | Chuyển lỗi đến nơi có thể quyết định cách phản hồi | Service ném TaskStateConflictException |
| **Xử lý lỗi** | Chọn hành động phục hồi hoặc tạo phản hồi phù hợp | Controller trả trang chỉnh sửa với thông báo; advice trả HTTP 409 |

Model hoặc dịch vụ ứng dụng nên phát hiện các vi phạm quy tắc mà nó sở hữu. Repository hoặc adapter có thể phát hiện lỗi lưu trữ và chuyển đổi lỗi kỹ thuật thành exception phù hợp với ranh giới ứng dụng. Controller hoặc bộ xử lý tập trung quyết định cách biểu diễn lỗi cho HTTP và View.

Không nên bắt exception ở tầng thấp rồi trả về một giá trị giả như null, danh sách rỗng hoặc true nếu việc đó làm mất ý nghĩa thất bại. Khi tầng trên nhận một kết quả trông như thành công, nó có thể tạo response sai hoặc tiếp tục quy trình trên dữ liệu không hợp lệ.

### 2.1. Exception không phải là thông báo dành cho người dùng

Tên exception và message nội bộ phục vụ chẩn đoán, không phải hợp đồng giao diện. Ví dụ:

~~~java
throw new TaskStateConflictException(
    "Cannot complete task because state=CANCELLED, taskId=..."
);
~~~

Thông tin nội bộ có thể hữu ích trong log, nhưng response công khai chỉ nên nói rằng công việc không thể hoàn tất ở trạng thái hiện tại. Không trả stack trace, tên bảng, câu SQL, đường dẫn file, hostname, token hoặc message thô từ thư viện cho người dùng.

## 3. Phân loại lỗi trước khi chọn nơi xử lý

Có thể phân loại lỗi theo ranh giới nơi chúng phát sinh:

| Nhóm lỗi | Ví dụ | Phản hồi thường gặp |
|---|---|---|
| Binding / cú pháp request | JSON sai, kiểu ngày không hợp lệ | 400 Bad Request |
| Validation đầu vào | Tiêu đề rỗng hoặc vượt giới hạn | 400 hoặc 422 theo hợp đồng API |
| Xác thực | Chưa đăng nhập hoặc credential không hợp lệ | 401 Unauthorized |
| Phân quyền | Đã đăng nhập nhưng không được phép | 403 Forbidden |
| Không tìm thấy | ID không ánh xạ đến tài nguyên | 404 Not Found |
| Xung đột nghiệp vụ | Trạng thái hiện tại không cho phép thao tác | 409 Conflict |
| Giới hạn tần suất | Client gửi quá nhiều request | 429 Too Many Requests |
| Hạ tầng tạm thời không sẵn sàng | Dịch vụ phụ thuộc hoặc database không sẵn sàng | 503 Service Unavailable trong trường hợp phù hợp |
| Lỗi không dự kiến | Null dereference, bug hoặc lỗi không phân loại | 500 Internal Server Error |

Status code là một phần của hợp đồng HTTP. Không nên chọn mã chỉ dựa trên tên exception; cần xét ý nghĩa mà client cần hiểu. Ví dụ, validation dữ liệu có thể dùng 400 hoặc 422 tùy quy ước API, nhưng phải nhất quán.

### 3.1. Lỗi nghiệp vụ và lỗi kỹ thuật khác nhau

Lỗi nghiệp vụ là kết quả có thể dự đoán từ quy tắc ứng dụng: công việc đã khóa, số dư không đủ, tên đã được sử dụng hoặc trạng thái không cho phép chuyển tiếp. Những lỗi này thường cần mã lỗi ổn định để client hiển thị thông báo hoặc hướng dẫn người dùng.

Lỗi kỹ thuật là sự cố của hạ tầng hoặc chương trình: mất kết nối database, timeout dịch vụ ngoài, lỗi serialize hoặc bug. Không nên giả vờ những lỗi này là một kết quả nghiệp vụ bình thường. Cần ghi log với thông tin chẩn đoán, trả phản hồi an toàn và cho phép giám sát hệ thống nhận biết.

## 4. Luồng xử lý lỗi trong MVC

Một luồng phổ biến là lỗi phát sinh trong use case, lan truyền qua Controller và được bộ xử lý tập trung ánh xạ thành response:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Controller"]
    B --> C["Application Service / Model"]
    C --> D{"Thực hiện thành công?"}
    D -->|Có| E["Tạo ViewModel / Response"]
    E --> F["HTTP response thành công"]
    D -->|Không| G["Exception hoặc kết quả lỗi"]
    G --> H["Exception resolver / ControllerAdvice"]
    H --> I["Phân loại và ánh xạ lỗi"]
    I --> J["HTTP error response / Error View"]
    J --> K["Client hiển thị thông báo"]
~~~

Trong Spring MVC, cơ chế giải quyết exception có thể sử dụng:

- Exception handler đặt ngay trong Controller.
- Controller advice áp dụng cho một hoặc nhiều Controller.
- Các exception resolver của Spring MVC.
- Error handling ở filter, Spring Security hoặc container cho lỗi nằm ngoài luồng xử lý Controller.

Bộ xử lý tập trung là một phần của cơ chế giải quyết lỗi MVC, không phải nơi duy nhất trong toàn bộ ứng dụng có thể phát hiện hoặc xử lý lỗi.

## 5. Xử lý tập trung với Spring MVC

Spring MVC cung cấp @ControllerAdvice và @RestControllerAdvice để định nghĩa các phương thức xử lý exception dùng chung.

- **@ControllerAdvice** áp dụng cho Controller được chọn và có thể trả View, ModelAndView hoặc response.
- **@RestControllerAdvice** kết hợp ControllerAdvice với ResponseBody, phù hợp với API trả JSON hoặc dữ liệu response.
- **@ExceptionHandler** ánh xạ loại exception sang phương thức xử lý.
- **ResponseEntityExceptionHandler** cung cấp điểm mở rộng cho một số exception chuẩn do Spring MVC phát sinh.

### 5.1. Bộ xử lý lỗi API dùng chung

Ví dụ API có một cấu trúc lỗi ổn định:

~~~java
public record ApiFieldError(
    String field,
    String message
) {}

public record ApiError(
    String code,
    String message,
    List<ApiFieldError> fieldErrors,
    String traceId
) {}
~~~

Bộ xử lý tập trung:

~~~java
@RestControllerAdvice(basePackages = "com.example.tasks.api")
class ApiExceptionHandler {

    private final Logger log =
        LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(TaskNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
        TaskNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "TASK_NOT_FOUND",
            "Không tìm thấy công việc.",
            List.of(),
            MDC.get("traceId")
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(TaskStateConflictException.class)
    ResponseEntity<ApiError> handleConflict(
        TaskStateConflictException exception
    ) {
        ApiError body = new ApiError(
            "TASK_STATE_CONFLICT",
            "Trạng thái hiện tại không cho phép thao tác này.",
            List.of(),
            MDC.get("traceId")
        );

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        List<ApiFieldError> fields =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> new ApiFieldError(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        ApiError body = new ApiError(
            "VALIDATION_FAILED",
            "Dữ liệu gửi lên không hợp lệ.",
            fields,
            MDC.get("traceId")
        );

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadableBody(
        HttpMessageNotReadableException exception
    ) {
        ApiError body = new ApiError(
            "INVALID_REQUEST_BODY",
            "Nội dung request không đúng định dạng.",
            List.of(),
            MDC.get("traceId")
        );

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> handleUnexpected(Exception exception) {
        String traceId = MDC.get("traceId");

        log.error("Unhandled API error, traceId={}", traceId, exception);

        ApiError body = new ApiError(
            "INTERNAL_ERROR",
            "Đã xảy ra lỗi. Vui lòng thử lại sau.",
            List.of(),
            traceId
        );

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(body);
    }
}
~~~

Ví dụ minh họa cách tổ chức; ứng dụng thực tế cần bảo đảm các import, phiên bản Spring, cơ chế trace ID và quy ước exception phù hợp. Handler tổng quát cho Exception nên là lớp dự phòng cuối cùng trong phạm vi advice. Những lỗi đã biết cần có handler cụ thể để giữ status code và thông báo ổn định.

Không đưa exception.getMessage() vào response. Message từ database hoặc thư viện có thể chứa thông tin nội bộ. Validation field error cũng nên dùng message đã được kiểm soát; không trả rejected value nếu trường có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm.

### 5.2. Dùng Problem Details khi API cần định dạng chuẩn

Spring Framework 6 hỗ trợ ProblemDetail để biểu diễn lỗi theo định dạng Problem Details của HTTP. Cách này giúp API có cấu trúc lỗi thống nhất mà không phải tự định nghĩa mọi trường.

~~~java
@ExceptionHandler(TaskNotFoundException.class)
ResponseEntity<ProblemDetail> handleNotFound(
    TaskNotFoundException exception
) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy công việc."
    );

    problem.setTitle("Không tìm thấy tài nguyên");
    problem.setProperty("code", "TASK_NOT_FOUND");
    problem.setProperty("traceId", MDC.get("traceId"));

    return ResponseEntity
        .status(HttpStatus.NOT_FOUND)
        .body(problem);
}
~~~

Problem Details phù hợp với API cần một định dạng lỗi có thể mở rộng. Nếu dự án đã có ApiError riêng, không cần thay đổi chỉ để dùng một kiểu mới; điều quan trọng là hợp đồng nhất quán, có mã lỗi ổn định và không làm lộ thông tin nội bộ.

## 6. Phân loại exception ở tầng ứng dụng

Bộ xử lý tập trung hoạt động tốt khi application service và Model phát ra exception có ý nghĩa rõ ràng. Không nên để ControllerAdvice phải phân tích message tự do hoặc nhận biết exception cụ thể của JDBC, ORM ở khắp nơi.

Ví dụ một nhóm exception ứng dụng:

~~~java
public class TaskNotFoundException extends RuntimeException {
    public TaskNotFoundException(UUID taskId) {
        super("Task not found: " + taskId);
    }
}

public class TaskStateConflictException extends RuntimeException {
    public TaskStateConflictException(String message) {
        super(message);
    }
}

public class DuplicateTaskNameException extends RuntimeException {
    public DuplicateTaskNameException(String message) {
        super(message);
    }
}
~~~

Application service có thể chuyển lỗi repository hoặc kết quả nghiệp vụ thành exception thuộc ngôn ngữ ứng dụng. ControllerAdvice không cần biết database dùng loại constraint hay mã vendor nào để trả 409 cho xung đột tên.

Không nên tạo một class exception riêng cho mọi dòng code. Hãy tạo loại exception khi nó mang ý nghĩa mà tầng gọi cần xử lý khác nhau. Nếu các lỗi có cùng chính sách phản hồi và không cần phân biệt, có thể dùng một loại lỗi có mã hoặc thuộc tính phân loại.

### 6.1. Không dùng message để quyết định status code

Cách xử lý dễ lỗi:

~~~java
@ExceptionHandler(RuntimeException.class)
ResponseEntity<?> handle(RuntimeException exception) {
    if (exception.getMessage().contains("not found")) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.internalServerError().build();
}
~~~

Message có thể thay đổi, dịch ngôn ngữ, trùng từ hoặc chứa dữ liệu không đáng tin. Hãy dựa trên kiểu exception hoặc mã lỗi có cấu trúc, không phân tích chuỗi message để suy ra ngữ nghĩa.

### 6.2. Chuyển lỗi hạ tầng ở đúng adapter

Nếu repository dùng JDBC, JPA hoặc client ngoài, adapter có thể chuyển exception công nghệ thành exception ứng dụng có ý nghĩa. Ví dụ, vi phạm unique constraint cho email có thể trở thành DuplicateEmailException. Timeout của dịch vụ phụ thuộc có thể trở thành ExternalServiceUnavailableException.

Việc chuyển đổi cần giữ nguyên nguyên nhân làm cause để log và chẩn đoán, nhưng response công khai chỉ hiển thị thông tin đã chọn lọc. Không nên bắt mọi DataAccessException rồi đổi thành “không tìm thấy”, vì lỗi kết nối và lỗi truy vấn có ý nghĩa khác nhau.

## 7. Khi nào nên xử lý lỗi ngay tại Controller?

Không phải lỗi nào cũng nên đẩy lên bộ xử lý toàn cục. Xử lý tại Controller phù hợp khi Controller có ngữ cảnh giao diện hoặc request cụ thể để phục hồi.

Các trường hợp thường gặp:

- Binding và validation của biểu mẫu HTML cần giữ lại giá trị người dùng nhập.
- Một lỗi nghiệp vụ có thể được gắn vào trường cụ thể bằng BindingResult.
- Một thao tác phụ không bắt buộc có thể thất bại nhưng trang chính vẫn tiếp tục với thông báo cảnh báo.
- Một endpoint có hợp đồng phản hồi đặc thù mà các endpoint khác không dùng.
- Một nhánh điều hướng có thể phục hồi chỉ tồn tại trong một luồng màn hình.

Ví dụ xử lý validation tại biểu mẫu:

~~~java
@PostMapping("/tasks")
String create(
    @Valid @ModelAttribute("form") CreateTaskForm form,
    BindingResult errors,
    RedirectAttributes redirectAttributes
) {
    if (errors.hasErrors()) {
        return "tasks/new";
    }

    try {
        taskService.create(form.title());
    } catch (DuplicateTaskNameException exception) {
        errors.rejectValue(
            "title",
            "task.title.duplicate",
            "Tên công việc đã được sử dụng."
        );

        return "tasks/new";
    }

    redirectAttributes.addFlashAttribute(
        "notice",
        "Đã tạo công việc."
    );

    return "redirect:/tasks";
}
~~~

Controller có thể xử lý DuplicateTaskNameException tại chỗ vì nó biết lỗi cần xuất hiện cạnh trường title và cần render lại form. BindingResult phải đặt ngay sau đối tượng có @Valid hoặc @Validated để Spring gắn lỗi binding/validation vào đúng tham số.

Cần nạp lại các dữ liệu phụ của View nếu trang form có danh sách lựa chọn, chẳng hạn danh mục hoặc người phụ trách. Nếu trả lại template mà thiếu dữ liệu tham chiếu, trang có thể render lỗi dù lỗi nghiệp vụ đã được xử lý.

### 7.1. Xử lý kết quả nghiệp vụ có thể dự đoán

Không phải mọi tình huống không thành công đều cần exception. Nếu một thao tác thường xuyên có kết quả từ chối dự kiến, application service có thể trả một result type hoặc outcome có trạng thái rõ ràng.

Ví dụ:
- Không đủ tồn kho.
- Không thể gửi yêu cầu vì đơn đã đóng.
- Tên công việc đã tồn tại trong một thao tác kiểm tra trước.
- Người dùng chưa hoàn tất điều kiện của một bước.

Dùng result type có thể giúp luồng bình thường dễ đọc và tránh dùng exception làm điều khiển thường xuyên. Tuy nhiên, lỗi bất ngờ hoặc vi phạm không thể tiếp tục vẫn nên được thể hiện bằng exception phù hợp. Dù dùng cách nào, Controller phải chuyển kết quả thành response nhất quán.

## 8. Giới hạn của xử lý tại từng Controller

Xử lý cục bộ trở thành vấn đề khi cùng một chính sách được sao chép ở nhiều endpoint.

Những dấu hiệu cần xem xét:

- Nhiều Controller có các khối catch giống nhau để ánh xạ NotFound thành 404.
- Mỗi endpoint tạo cấu trúc JSON lỗi khác nhau.
- Có nơi ghi stack trace, nơi khác bỏ qua hoàn toàn.
- Một exception nghiệp vụ bị xử lý khác nhau dù hợp đồng API giống nhau.
- Controller phải biết chi tiết database hoặc thư viện bên ngoài.
- Một lỗi phát sinh từ nhiều use case không có cùng cách phản hồi.
- Mã lỗi và thông báo được viết rải rác, khó thay đổi đồng bộ.

Ví dụ lặp lại:

~~~java
try {
    taskService.complete(id);
} catch (TaskNotFoundException exception) {
    return ResponseEntity.notFound().build();
}
~~~

Nếu nhiều Controller đều phải viết cùng logic này, nên chuyển việc ánh xạ TaskNotFoundException sang một advice dùng chung. Controller chỉ cần gọi use case; bộ xử lý chung quyết định status và body.

Không cần loại bỏ mọi catch khỏi Controller. Mục tiêu là để xử lý cục bộ chỉ giữ phần ngữ cảnh riêng của endpoint, còn chính sách lặp lại được tập trung.

## 9. Giới hạn của xử lý tập trung

Xử lý tập trung cũng có thể bị lạm dụng. Một advice quá lớn có thể trở thành nơi chứa logic nghiệp vụ, biết mọi loại màn hình, gọi repository hoặc cố gắng phục hồi mọi lỗi.

Không nên để ControllerAdvice:
- Tự tải entity hoặc thay đổi trạng thái nghiệp vụ để “sửa” lỗi.
- Quyết định quyền truy cập tài nguyên dựa trên message exception.
- Chuyển mọi exception thành 400 hoặc 500 mà không phân loại.
- Trả HTML cho endpoint API hoặc JSON cho trang HTML theo một quy tắc cứng không xét hợp đồng.
- Nuốt lỗi và trả response thành công.
- Chứa logic đặc thù của một biểu mẫu hoặc một màn hình.
- Ghi log cùng một exception nhiều lần ở mọi tầng.
- Phụ thuộc vào request body hoặc dữ liệu nhạy cảm không cần thiết.

Advice nên tập trung vào ánh xạ và chính sách chung. Nếu logic xử lý lỗi cần truy vấn dữ liệu, thay đổi trạng thái hoặc thực hiện quy tắc, hãy đưa phần đó vào use case hoặc một dịch vụ ứng dụng rõ ràng, sau đó để Controller/advice tạo response.

## 10. Controller-local handler và ControllerAdvice: thứ tự và phạm vi

Spring MVC hỗ trợ @ExceptionHandler ngay trong Controller và trong các lớp @ControllerAdvice. Handler cục bộ của Controller được xét trước advice toàn cục cho Controller đó. Vì vậy, một handler cục bộ có thể ghi đè chính sách chung cho exception mà nó xử lý.

Điều này hữu ích khi một màn hình cần hành vi riêng, nhưng cũng có thể gây khó hiểu nếu cùng một exception bị xử lý ở nhiều nơi. Hãy giới hạn handler cục bộ vào loại lỗi thật sự cần ngữ cảnh riêng.

### 10.1. Giới hạn phạm vi advice

Có thể áp dụng advice cho toàn bộ ứng dụng hoặc chỉ một nhóm Controller. Ví dụ:

~~~java
@RestControllerAdvice(basePackages = "com.example.api")
class ApiExceptionHandler {
    // Ánh xạ lỗi API
}

@ControllerAdvice(basePackages = "com.example.web")
class WebExceptionHandler {
    // Chọn error view cho trang HTML
}
~~~

Tách advice theo loại giao diện giúp API và trang HTML có thể dùng cùng exception ứng dụng nhưng tạo response khác nhau. API có thể trả JSON với code ổn định; giao diện HTML có thể render error template hoặc redirect về trang phù hợp.

Spring cũng cho phép giới hạn advice theo controller type hoặc annotation. Khi có nhiều advice cùng áp dụng, thứ tự và độ cụ thể của handler cần được thiết kế rõ. Không nên tạo nhiều advice rộng với các handler Exception.class chồng lấn nếu chưa kiểm soát thứ tự.

### 10.2. Chọn handler cụ thể trước handler tổng quát

Một handler cho TaskNotFoundException nên rõ ràng hơn handler Exception.class. Handler tổng quát chỉ là fallback cho lỗi chưa được phân loại. Nếu một advice tổng quát có thứ tự ưu tiên cao và bắt quá rộng, nó có thể che khuất handler cụ thể ở advice khác.

Hãy tổ chức các handler theo chính sách và phạm vi Controller, đồng thời kiểm thử trường hợp một exception có thể khớp nhiều handler.

## 11. Validation và lỗi binding

Validation là nơi cần phân biệt xử lý tập trung và cục bộ rõ ràng.

### 11.1. Form HTML với BindingResult

Với @ModelAttribute và @Valid, nếu BindingResult hoặc Errors đứng ngay sau tham số được validate, Controller có thể nhận lỗi và tự quyết định render lại form:

~~~java
@PostMapping("/profile")
String update(
    @Valid @ModelAttribute("form") ProfileForm form,
    BindingResult errors
) {
    if (errors.hasErrors()) {
        return "profile/edit";
    }

    profileService.update(form);
    return "redirect:/profile";
}
~~~

Cách này phù hợp vì View cần giữ dữ liệu và hiển thị lỗi theo trường. Không nên để advice toàn cục chuyển mọi lỗi validation của form thành JSON 400 nếu người dùng đang thao tác trên trang HTML.

### 11.2. JSON API với lỗi validation tập trung

Với @RequestBody và @Valid, nếu không có BindingResult để xử lý tại phương thức, Spring MVC thường phát sinh MethodArgumentNotValidException. Advice có thể chuyển lỗi thành cấu trúc JSON thống nhất.

Ví dụ response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu gửi lên không hợp lệ.",
  "fieldErrors": [
    {
      "field": "title",
      "message": "Tiêu đề không được để trống."
    }
  ],
  "traceId": "..."
}
~~~

Không trả giá trị người dùng đã nhập trong fieldErrors nếu trường đó có thể chứa thông tin bí mật. Với lỗi binding kiểu dữ liệu, chẳng hạn chuỗi không chuyển được thành số, cần có thông báo tổng quát và an toàn.

### 11.3. Lỗi validation cấp phương thức

Ngoài validation object, Spring có thể phát sinh lỗi khi constraint được đặt trực tiếp trên tham số phương thức Controller. Ở các phiên bản Spring MVC mới, HandlerMethodValidationException có thể xuất hiện cho method validation. Cần xử lý loại lỗi phù hợp với phiên bản framework và cách bật method validation của dự án.

Không nên chỉ xử lý MethodArgumentNotValidException rồi giả định mọi lỗi validation đều đi qua cùng loại exception.

## 12. Lỗi bảo mật có thể nằm ngoài ControllerAdvice

Một điểm quan trọng: không phải mọi lỗi HTTP đều đi qua Controller.

Spring Security có thể từ chối request trong filter chain trước khi DispatcherServlet gọi Controller. Khi đó, ControllerAdvice không phải nơi phù hợp để xử lý tất cả lỗi xác thực và phân quyền.

Thông thường:
- **AuthenticationEntryPoint** tạo phản hồi khi request chưa được xác thực hoặc xác thực không thành công.
- **AccessDeniedHandler** xử lý trường hợp đã xác thực nhưng không đủ quyền.
- Method security có thể phát sinh lỗi trong quá trình gọi service/controller và cần được tích hợp với cách xử lý bảo mật của ứng dụng.

Vì vậy, hãy thống nhất cấu trúc lỗi và correlation ID giữa security handler với MVC advice, nhưng giữ đúng ranh giới của từng cơ chế. Không nên cố bắt mọi AccessDeniedException trong ControllerAdvice rồi nghĩ rằng đã bao phủ cả filter chain.

Không tiết lộ liệu một tài khoản cụ thể có tồn tại hay không nếu chính sách bảo mật yêu cầu che giấu thông tin đó. Thông báo cho người dùng cần đủ hữu ích mà không tiết lộ dữ liệu xác thực hoặc quyền nội bộ.

## 13. Lỗi ở filter, async và response đã gửi

ControllerAdvice xử lý exception trong luồng giải quyết request của Spring MVC. Một số lỗi phát sinh ngoài phạm vi đó cần cơ chế tương ứng:

- Exception trong Servlet Filter xảy ra trước hoặc sau DispatcherServlet cần được xử lý tại filter hoặc error handling của container.
- Exception trong Spring Security filter chain được xử lý bởi security handlers.
- Tác vụ nền chạy sau khi request kết thúc cần logging, retry và error channel riêng; không thể trả HTTP response mới cho request đã đóng.
- Với async request như DeferredResult hoặc Callable, lỗi được chuyển về quy trình async dispatch của Spring MVC nếu phát sinh trong vòng đời request đó; cần kiểm thử đúng cách triển khai.
- Khi response đã commit hoặc streaming đã bắt đầu, server có thể không còn khả năng đổi status code hoặc body thành một trang lỗi khác.

Không nên giả định một lớp @RestControllerAdvice có thể bắt mọi exception trong JVM. Phạm vi của nó là một phần của web request pipeline.

## 14. Logging, correlation ID và thông tin an toàn

Một phản hồi lỗi hữu ích cho người dùng không nhất thiết phải chứa chi tiết kỹ thuật. Để đội phát triển điều tra, cần log ở phía server với context phù hợp.

### 14.1. Log theo mức độ

- Lỗi đầu vào dự kiến hoặc xung đột nghiệp vụ thường không cần stack trace ở mức ERROR cho mỗi lần xảy ra.
- Lỗi hạ tầng hoặc lỗi không dự kiến cần log đủ thông tin chẩn đoán, thường kèm exception và trace ID.
- Không ghi cùng một exception ở nhiều tầng nếu điều đó tạo nhiều stack trace giống nhau.
- Không log token, mật khẩu, cookie session, dữ liệu thanh toán hoặc toàn bộ request body chứa thông tin cá nhân.

Log nên có request ID/correlation ID để liên kết log giữa Controller, service và adapter. ID cần được tạo hoặc kiểm tra ở middleware đáng tin cậy; không nên đưa trực tiếp giá trị header tùy ý vào log mà không giới hạn và làm sạch.

### 14.2. Response không nên chứa stack trace

Một response lỗi an toàn thường có:
- Mã lỗi ổn định, ví dụ TASK_NOT_FOUND.
- Thông báo ngắn, phù hợp với người dùng hoặc client.
- Danh sách lỗi trường nếu là validation.
- Trace ID để đội hỗ trợ tra log.
- Status code phản ánh ý nghĩa lỗi.

Không trả stack trace, tên class nội bộ, đường dẫn file, SQL, host database hoặc exception message thô. Những chi tiết đó giúp kẻ tấn công hiểu cấu trúc hệ thống và có thể làm lộ dữ liệu.

### 14.3. Tránh ghi log trùng lặp

Nếu repository log lỗi rồi ném exception, service log lại, ControllerAdvice tiếp tục log stack trace, một lỗi có thể xuất hiện nhiều lần. Nên xác định một nơi chịu trách nhiệm ghi stack trace đầy đủ, thường là ranh giới xử lý lỗi cuối cùng; các tầng thấp chỉ bổ sung context khi thực sự cần.

## 15. Thiết kế Error View cho ứng dụng HTML

Với ứng dụng server-rendered, bộ xử lý lỗi có thể trả một View chung cho lỗi không dự kiến hoặc một số status code cụ thể.

~~~java
@ControllerAdvice(basePackages = "com.example.web")
class WebExceptionHandler {

    @ExceptionHandler(TaskNotFoundException.class)
    ModelAndView handleNotFound(TaskNotFoundException exception) {
        ModelAndView view = new ModelAndView("errors/not-found");
        view.setStatus(HttpStatus.NOT_FOUND);
        view.addObject(
            "message",
            "Không tìm thấy công việc bạn yêu cầu."
        );
        return view;
    }

    @ExceptionHandler(Exception.class)
    ModelAndView handleUnexpected(Exception exception) {
        ModelAndView view = new ModelAndView("errors/server-error");
        view.setStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        view.addObject(
            "message",
            "Đã xảy ra lỗi. Vui lòng thử lại sau."
        );
        return view;
    }
}
~~~

Trang lỗi nên:
- Hiển thị thông báo dễ hiểu và status phù hợp.
- Có đường quay lại hoặc điều hướng an toàn.
- Không hiển thị stack trace hay thông tin nhạy cảm.
- Không phụ thuộc dữ liệu form hoặc session đã hết hạn.
- Có thể hoạt động ngay cả khi dịch vụ chính đang lỗi.

Không phải mọi lỗi đều cần một trang HTML riêng. Với lỗi validation, trả lại chính form thường tốt hơn. Với lỗi không tìm thấy, một trang 404 có thể phù hợp. Với lỗi server, trang chung giúp tránh hiển thị chi tiết nội bộ.

## 16. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Mỗi Controller tự ánh xạ cùng một exception | Response và status không nhất quán | Dùng advice cho chính sách chung |
| Đưa mọi lỗi vào một handler Exception | Mất phân biệt 400, 404, 409, 500 | Phân loại exception và handler cụ thể |
| Advice chứa logic nghiệp vụ | Ranh giới MVC bị đảo lộn, khó tái sử dụng | Để Model/use case quyết định nghiệp vụ |
| Controller không giữ lỗi validation của form | Người dùng mất dữ liệu đã nhập | Dùng BindingResult và render lại form |
| Trả exception message hoặc stack trace | Rò rỉ thông tin nội bộ | Dùng message an toàn và trace ID |
| Dùng message string để phân loại lỗi | Dễ sai khi nội dung thay đổi | Dùng exception type hoặc error code |
| Bắt Throwable hoặc Error để tiếp tục | Có thể che lỗi nghiêm trọng của runtime | Chỉ bắt loại exception có thể xử lý |
| Coi ControllerAdvice xử lý được lỗi Security filter | Một số lỗi xác thực/phân quyền không đi qua MVC | Cấu hình AuthenticationEntryPoint và AccessDeniedHandler |
| Log stack trace ở mọi tầng | Log trùng lặp, khó điều tra | Chọn một nơi log lỗi đầy đủ |
| Trả 200 cho response lỗi | Client hiểu nhầm request thành công | Chọn status code theo hợp đồng HTTP |

## 17. Kiểm thử chiến lược xử lý lỗi

Kiểm thử không chỉ xác minh handler có được gọi. Cần xác minh status, body, View, dữ liệu an toàn và việc các lỗi khác nhau không bị gộp nhầm.

| Phạm vi | Nội dung cần kiểm tra |
|---|---|
| Controller-local | Validation form, BindingResult, dữ liệu nhập được giữ, thông báo đúng trường |
| Global API advice | Exception nghiệp vụ ánh xạ đúng status, error code và body |
| Web advice | Chọn đúng error View và status |
| Security handler | Chưa đăng nhập trả 401; không đủ quyền trả 403 theo hợp đồng |
| Fallback | Lỗi không dự kiến trả 500 an toàn và có trace ID |
| Logging | Có context cần thiết, không ghi token hoặc dữ liệu nhạy cảm |
| Async/filter | Lỗi ngoài Controller được xử lý tại đúng pipeline |
| Response contract | Không trả stack trace, SQL hoặc message nội bộ |

Ví dụ kiểm thử API bằng MockMvc:

~~~java
@Test
void returnsNotFoundForMissingTask() throws Exception {
    mockMvc.perform(get("/api/tasks/{id}", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("TASK_NOT_FOUND"))
        .andExpect(jsonPath("$.message").exists());
}
~~~

Với form HTML, kiểm tra khi title rỗng:
- Response render lại đúng template.
- Lỗi được gắn vào trường title.
- Giá trị các trường khác vẫn được giữ.
- Các dữ liệu phụ của trang vẫn được nạp.
- Không gọi use case tạo mới.

Với lỗi không dự kiến, kiểm tra response chỉ chứa thông báo chung và trace ID; stack trace phải ở log nội bộ, không nằm trong body.

## 18. Quy trình quyết định xử lý lỗi ở đâu

Khi một lỗi mới xuất hiện, có thể đi theo các bước:

1. Xác định lỗi phát sinh ở binding, validation, Model, persistence, security hay adapter ngoài.
2. Phân loại lỗi thành lỗi đầu vào, nghiệp vụ, xác thực/phân quyền, hạ tầng hoặc không dự kiến.
3. Xác định lỗi có cần ngữ cảnh riêng của màn hình/request để phục hồi không.
4. Nếu chính sách phản hồi dùng chung, tạo hoặc tái sử dụng handler trong ControllerAdvice.
5. Nếu cần giữ form, gắn lỗi vào BindingResult hoặc trả một kết quả hiển thị riêng tại Controller.
6. Nếu lỗi nằm trong Security filter hoặc filter khác, cấu hình handler ở đúng pipeline.
7. Chọn status code, error code và thông báo theo hợp đồng.
8. Ghi log ở nơi phù hợp, thêm trace ID và loại bỏ dữ liệu nhạy cảm.
9. Kiểm thử cả phản hồi lỗi và hành vi dữ liệu sau lỗi.

Một nguyên tắc thực tế: nếu nhiều Controller cần cùng một cách phản hồi, hãy tập trung ánh xạ; nếu một Controller cần giữ ngữ cảnh riêng để phục hồi tương tác, xử lý cục bộ. Nếu cần thay đổi trạng thái nghiệp vụ, hãy đưa quyết định đó về Model hoặc application service.

## 19. Những điểm cần ghi nhớ

Xử lý lỗi tập trung giúp thống nhất cách ánh xạ exception thành HTTP status, error code, cấu trúc response và logging. Trong Spring MVC, @ControllerAdvice và @RestControllerAdvice phù hợp cho chính sách chung của các Controller thuộc phạm vi được chọn.

Xử lý tại Controller phù hợp với ngữ cảnh riêng của request, đặc biệt là biểu mẫu HTML cần giữ dữ liệu và hiển thị lỗi theo trường. Không nên lặp lại cùng chính sách HTTP ở nhiều Controller, nhưng cũng không nên đưa logic phục hồi riêng của một màn hình vào advice toàn cục.

Phân loại lỗi trước khi chọn phản hồi; giữ exception nghiệp vụ tách khỏi chi tiết framework; không trả message nội bộ hoặc stack trace; và nhớ rằng Security filter, Servlet Filter, tác vụ nền hoặc response đã commit có vòng đời xử lý riêng. Một chiến lược tốt đặt mỗi lỗi ở đúng ranh giới, giúp người dùng nhận thông tin có ích và giúp đội phát triển điều tra sự cố mà không làm lộ chi tiết hệ thống.
