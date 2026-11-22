# Chuyển lỗi nghiệp vụ thành phản hồi có ý nghĩa

Trong ứng dụng quản lý công việc, người dùng có thể yêu cầu hoàn thành một công việc đã bị hủy, sửa một công việc không tồn tại hoặc phân công người không thuộc dự án. Đây là những tình huống ứng dụng hiểu request nhưng không thể thực hiện hành động theo quy tắc nghiệp vụ. Người dùng cần nhận được thông báo dễ hiểu; API client cần nhận status và mã lỗi ổn định để quyết định bước tiếp theo.

Trong mô hình Model–View–Controller (MVC), lỗi có thể xuất hiện ở nhiều lớp. Model phát hiện trạng thái không hợp lệ; Service phát hiện tài nguyên hoặc điều kiện nghiệp vụ không đáp ứng; Controller nhận lỗi và chuyển nó thành phản hồi phù hợp; View trình bày thông báo cho người dùng. Với Spring MVC, `@ControllerAdvice`, `@RestControllerAdvice` và `@ExceptionHandler` giúp tập trung việc ánh xạ lỗi mà không buộc Model phải biết HTTP.

Bài học tập trung vào cách chuyển lỗi nghiệp vụ thành phản hồi HTML hoặc JSON có ý nghĩa, chọn HTTP status phù hợp, giữ thông tin lỗi nhất quán, ghi log an toàn và kiểm thử luồng lỗi.

## 1. Lỗi nghiệp vụ và lỗi kỹ thuật

Không phải mọi lỗi đều có cùng nguyên nhân hoặc nên được trình bày giống nhau.

**Lỗi nghiệp vụ** xảy ra khi yêu cầu không thỏa quy tắc của ứng dụng. Ví dụ:

- Công việc đã hủy nên không thể hoàn thành.
- Người dùng không có quyền phân công công việc.
- Số lượng đặt hàng vượt giới hạn được phép.
- Tài khoản không đủ điều kiện thực hiện giao dịch.
- Tài nguyên không tồn tại hoặc không còn ở trạng thái có thể chỉnh sửa.

**Lỗi đầu vào hoặc giao thức** xảy ra khi request không đáp ứng hợp đồng HTTP. Ví dụ JSON sai cú pháp, ID không chuyển được sang kiểu số, thiếu trường bắt buộc hoặc gửi `Content-Type` không được hỗ trợ.

**Lỗi kỹ thuật** xuất phát từ hạ tầng hoặc sự cố ngoài dự kiến. Ví dụ database không khả dụng, timeout khi gọi dịch vụ ngoài, lỗi lập trình hoặc thiếu cấu hình.

Phân loại đúng giúp chọn phản hồi phù hợp. Người dùng có thể sửa một trường sai; họ có thể cần thay đổi trạng thái trước khi thực hiện hành động; còn lỗi database thường không thể tự khắc phục bằng cách sửa biểu mẫu.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Validation đầu vào | Tiêu đề rỗng | Giữ dữ liệu form và chỉ rõ trường cần sửa |
| Quy tắc nghiệp vụ | Không thể hoàn thành công việc đã hủy | Thông báo điều kiện hiện tại và hành động có thể làm tiếp |
| Tài nguyên | Không tìm thấy công việc | Hiển thị trang không tìm thấy hoặc response `404` |
| Xác thực / phân quyền | Chưa đăng nhập hoặc không được phép | Yêu cầu đăng nhập hoặc báo không đủ quyền theo chính sách |
| Xung đột đồng thời | Version đã thay đổi | Báo dữ liệu đã được cập nhật và yêu cầu tải lại |
| Hạ tầng / lỗi ngoài dự kiến | Database timeout | Phản hồi chung, ghi log để điều tra và không lộ chi tiết nội bộ |

## 2. Lỗi phải được diễn đạt theo ngôn ngữ của từng tầng

Một quy tắc nghiệp vụ không nên phụ thuộc vào giao thức HTTP. Model không nên ném `ResponseStatusException` chỉ vì một endpoint web muốn trả `409 Conflict`; cùng quy tắc có thể được gọi từ API khác, tác vụ nền hoặc ứng dụng dòng lệnh.

Nên phân tách:

- **Model:** bảo vệ bất biến và quy tắc trạng thái.
- **Application Service:** điều phối ca sử dụng, tải tài nguyên, kiểm tra quyền và phối hợp Model.
- **Controller:** nhận dữ liệu HTTP, gọi Service và chọn loại response.
- **Exception handler / presenter:** ánh xạ lỗi thành HTTP status, error DTO hoặc View.
- **View:** trình bày thông báo bằng ngôn ngữ và định dạng phù hợp.

Ví dụ, Model có thể phát hiện chuyển trạng thái không hợp lệ:

```java
public class InvalidTaskTransitionException extends RuntimeException {
    public InvalidTaskTransitionException(
            TaskStatus current,
            TaskStatus requested) {
        super("Cannot change task from " + current + " to " + requested);
    }
}
```

Thông điệp trong exception phục vụ chẩn đoán nội bộ. Không nên tự động gửi nguyên văn thông điệp này cho client, vì nó có thể chứa tên lớp, dữ liệu nội bộ hoặc cách diễn đạt không phù hợp với người dùng.

Model dùng exception có ý nghĩa miền để biểu đạt quy tắc. Lớp web quyết định lỗi đó tương ứng với `409 Conflict`, thông báo “Công việc đã bị hủy nên không thể hoàn thành” hoặc một phản hồi khác theo hợp đồng.

### Khi nào dùng exception, khi nào dùng kết quả nghiệp vụ?

Không phải mọi kết quả không thành công đều cần exception. Nếu một tình huống là kết quả dự kiến và thường xuyên của một thao tác, có thể trả kiểu kết quả tường minh:

```java
public sealed interface CompleteTaskResult {
    record Completed(Task task) implements CompleteTaskResult {}
    record AlreadyCompleted(Task task) implements CompleteTaskResult {}
    record Rejected(String reasonCode) implements CompleteTaskResult {}
}
```

Service có thể trả `AlreadyCompleted` nếu thao tác lặp lại được xem là thành công theo nghiệp vụ, hoặc `Rejected` nếu client cần xử lý một kết quả từ chối đã biết. Exception phù hợp hơn với luồng bất thường hoặc vi phạm không thể tiếp tục trong ngữ cảnh hiện tại. Chọn một cách nhất quán để người gọi không phải đoán khi nào kết quả nằm trong return value và khi nào nó được ném ra.

## 3. Ánh xạ lỗi thành HTTP status

HTTP status cho client biết loại kết quả ở mức giao thức. Status nên được chọn theo ý nghĩa của lỗi và hợp đồng API, không dựa vào tên exception một cách máy móc.

| Status | Ý nghĩa | Ví dụ trong MVC |
|---|---|---|
| `400 Bad Request` | Request sai cú pháp hoặc không thể bind | JSON sai, ID không chuyển được kiểu |
| `401 Unauthorized` | Request cần xác thực hợp lệ | Chưa đăng nhập hoặc thông tin xác thực không hợp lệ |
| `403 Forbidden` | Đã xác thực nhưng không có quyền | Người dùng không được phép sửa công việc |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc không muốn tiết lộ sự tồn tại | Mã công việc không tồn tại |
| `405 Method Not Allowed` | Path tồn tại nhưng HTTP method không được hỗ trợ | Gửi `PUT` đến endpoint chỉ khai báo `GET` |
| `409 Conflict` | Request xung đột với trạng thái hiện tại | Hoàn thành công việc đã hủy hoặc version đã cũ |
| `412 Precondition Failed` | Điều kiện trong request header không còn đúng | `If-Match` không khớp ETag hiện tại |
| `415 Unsupported Media Type` | Media type của request không được hỗ trợ | Gửi XML đến endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Nội dung có thể phân tích nhưng không hợp lệ theo ngữ nghĩa | API chọn status này cho validation hoặc quy tắc dữ liệu |
| `429 Too Many Requests` | Client gửi quá nhiều request trong khoảng thời gian | Vượt giới hạn rate limit |
| `500 Internal Server Error` | Lỗi ngoài dự kiến phía server | Null pointer hoặc lỗi lập trình chưa xử lý |
| `503 Service Unavailable` | Dịch vụ tạm thời không thể đáp ứng | Phụ thuộc thiết yếu đang bảo trì hoặc quá tải |

Một số quy ước cần được thống nhất:

- Validation thường trả `400`; một API có thể chọn `422` cho dữ liệu đúng cú pháp nhưng không hợp lệ theo ngữ nghĩa. Hãy dùng nhất quán.
- `409` phù hợp khi hành động xung đột với trạng thái hiện tại. `412` phù hợp khi client gửi một điều kiện HTTP như `If-Match` nhưng điều kiện đó thất bại.
- `401` và `403` có ý nghĩa khác nhau. Với ứng dụng HTML, chưa đăng nhập có thể được chuyển đến trang đăng nhập thay vì trả JSON `401`.
- `404` đôi khi được dùng có chủ đích thay cho `403` để không tiết lộ tài nguyên có tồn tại hay không. Đây là quyết định chính sách bảo mật, không phải quy tắc áp dụng cho mọi hệ thống.
- Không trả `200 OK` cho một thao tác thất bại chỉ vì muốn hiển thị thông báo trong body. Client và hệ thống giám sát cần status phản ánh đúng kết quả.

## 4. Phản hồi lỗi nên có hợp đồng ổn định

Một response lỗi hữu ích thường có hai nhóm thông tin:

1. **Thông tin dành cho máy:** mã lỗi ổn định, HTTP status, loại lỗi và các trường vi phạm để client có thể xử lý.
2. **Thông tin dành cho người dùng:** tiêu đề và mô tả dễ hiểu, có thể được bản địa hóa theo ngôn ngữ hiện tại.

Ví dụ JSON:

```json
{
  "type": "https://example.invalid/problems/task-transition",
  "title": "Không thể thực hiện thao tác",
  "status": 409,
  "detail": "Công việc đã bị hủy nên không thể hoàn thành.",
  "instance": "/api/tasks/42/complete",
  "code": "TASK_TRANSITION_NOT_ALLOWED",
  "traceId": "01J8EXAMPLE7Q2M4N9",
  "errors": []
}
```

Đây là ví dụ minh họa theo định dạng Problem Details của RFC 9457, có bổ sung các thuộc tính mở rộng `code`, `traceId` và `errors`. `type`, `title`, `status`, `detail` và `instance` giúp mô tả vấn đề; mã `code` là định danh ổn định để client quyết định hành động. Không nên để client phụ thuộc vào việc phân tích câu tiếng Việt trong `detail`.

Với lỗi validation, `errors` có thể chứa danh sách trường và mã lỗi:

```json
{
  "type": "https://example.invalid/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Vui lòng kiểm tra các trường được đánh dấu.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "title",
      "code": "NotBlank",
      "message": "Tiêu đề không được để trống."
    }
  ]
}
```

`message` là nội dung để hiển thị, còn `field` và `code` giúp frontend gắn lỗi vào đúng điều khiển. Không trả giá trị bí mật mà người dùng đã nhập trong response lỗi.

### Mã lỗi nên ổn định, thông điệp có thể thay đổi

Ví dụ, client có thể xử lý `TASK_ALREADY_COMPLETED` bằng cách tải lại dữ liệu và hiển thị trạng thái hiện tại. Nội dung thông điệp có thể được chỉnh sửa hoặc dịch sang ngôn ngữ khác mà không làm hỏng logic client.

Không dùng tên exception Java làm mã lỗi công khai. Tên lớp có thể thay đổi theo refactor và không phải một phần của hợp đồng HTTP.

## 5. Dùng ControllerAdvice để xử lý lỗi API tập trung

Trong Spring MVC, `@RestControllerAdvice` kết hợp `@ExceptionHandler` giúp ánh xạ exception từ nhiều Controller thành response body thống nhất. Với Spring Framework 6 / Spring Boot 3 trở lên, `ProblemDetail` là kiểu hỗ trợ biểu diễn Problem Details.

Giả sử Service ném các exception miền:

```java
public class TaskNotFoundException extends RuntimeException {
    public TaskNotFoundException(long taskId) {
        super("Task not found: " + taskId);
    }
}
```

`InvalidTaskTransitionException` là exception đã minh họa ở mục trước; advice dùng cùng kiểu đó để ánh xạ lỗi chuyển trạng thái.

API Controller chỉ gọi ca sử dụng:

```java
@RestController
@RequestMapping("/api/tasks")
public class TaskApiController {
    private final TaskCommandService taskCommandService;

    public TaskApiController(TaskCommandService taskCommandService) {
        this.taskCommandService = taskCommandService;
    }

    @PostMapping("/{id}/complete")
    public TaskResponse complete(
            @PathVariable long id,
            @AuthenticationPrincipal AppUserPrincipal actor) {
        return taskCommandService.complete(id, actor.userId());
    }
}
```

Advice chuyển exception thành status và body:

```java
@RestControllerAdvice(basePackages = "com.example.web.api")
public class ApiExceptionHandler {

    @ExceptionHandler(TaskNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            TaskNotFoundException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy công việc được yêu cầu.");
        problem.setType(URI.create(
                "https://example.invalid/problems/task-not-found"));
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "TASK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(InvalidTaskTransitionException.class)
    public ResponseEntity<ProblemDetail> handleInvalidTransition(
            InvalidTaskTransitionException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Công việc đang ở trạng thái không cho phép thực hiện thao tác này.");
        problem.setType(URI.create(
                "https://example.invalid/problems/task-transition"));
        problem.setTitle("Không thể thực hiện thao tác");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "TASK_TRANSITION_NOT_ALLOWED");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
```

Các URL `example.invalid` là địa chỉ minh họa; ứng dụng cần thay bằng URI tài liệu lỗi của chính mình. Thông điệp gửi client được viết riêng, không lấy nguyên văn `exception.getMessage()`. `ProblemDetail` được Spring MVC chuyển thành response body thông qua cơ chế message conversion.

`basePackages` giới hạn phạm vi advice. Nếu ứng dụng có cả Controller HTML và API, nên tổ chức phạm vi advice rõ ràng để handler không cạnh tranh hoặc vô tình trả JSON cho request trang web.

## 6. Ánh xạ lỗi validation cho API

Lỗi bind và validation thường được Spring MVC phát hiện trước khi phương thức Controller hoàn tất. Ví dụ `@Valid @RequestBody` có thể phát sinh `MethodArgumentNotValidException` khi một hoặc nhiều trường không đạt ràng buộc.

Có thể chuyển lỗi trường thành thuộc tính mở rộng:

```java
@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Vui lòng kiểm tra các trường được đánh dấu.");
    problem.setTitle("Dữ liệu không hợp lệ");
    problem.setProperty("code", "VALIDATION_FAILED");

    List<Map<String, String>> errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> Map.of(
                    "field", error.getField(),
                    "code", Objects.requireNonNullElse(
                            error.getCode(), "INVALID_VALUE"),
                    "message", Objects.requireNonNullElse(
                            error.getDefaultMessage(), "Giá trị không hợp lệ.")))
            .toList();

    problem.setProperty("errors", errors);
    return ResponseEntity.badRequest().body(problem);
}
```

Đoạn mã dùng các API Java hiện đại; với Java hoặc Spring phiên bản cũ, có thể cần điều chỉnh `toList()` hoặc kiểu Problem Details. Không nên đưa rejected value vào response một cách mặc định vì trường đó có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm.

Một số loại lỗi khác có thể cần handler riêng:

- `HttpMessageNotReadableException`: JSON sai cú pháp hoặc không thể deserialize.
- `MethodArgumentTypeMismatchException`: query/path parameter không chuyển được kiểu.
- `ConstraintViolationException`: validation ở method hoặc tầng Service, tùy cấu hình.
- `MissingServletRequestParameterException`: thiếu query parameter bắt buộc.

Nếu advice có thêm handler tổng quát `@ExceptionHandler(Exception.class)`, hãy ánh xạ tường minh các lỗi framework cần giữ status `4xx`. `ExceptionHandlerExceptionResolver` xử lý advice trước các resolver mặc định, nên handler tổng quát có thể bắt lỗi bind hoặc lỗi method trước khi resolver mặc định chuyển chúng thành `400`, `405`, `406` hay `415`.

Ví dụ hai lỗi request thường gặp:

```java
@ExceptionHandler(HttpMessageNotReadableException.class)
public ResponseEntity<ProblemDetail> handleUnreadableBody() {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Nội dung request không đúng định dạng hoặc không thể đọc.");
    problem.setTitle("Request không hợp lệ");
    problem.setProperty("code", "REQUEST_BODY_INVALID");
    return ResponseEntity.badRequest().body(problem);
}

@ExceptionHandler(MethodArgumentTypeMismatchException.class)
public ResponseEntity<ProblemDetail> handleTypeMismatch() {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Một tham số request có kiểu dữ liệu không hợp lệ.");
    problem.setTitle("Tham số không hợp lệ");
    problem.setProperty("code", "REQUEST_PARAMETER_INVALID");
    return ResponseEntity.badRequest().body(problem);
}
```

Không cần tạo một handler cho mọi exception framework. Hãy xác định những lỗi client có thể gặp thường xuyên và đưa chúng về schema thống nhất; các lỗi không dự kiến cần đi qua handler tổng quát an toàn.

Nếu dùng handler tổng quát `Exception.class`, cũng cần ánh xạ tường minh những exception framework khác mà ứng dụng muốn giữ status mặc định, chẳng hạn `HttpRequestMethodNotSupportedException` (`405`), `HttpMediaTypeNotSupportedException` (`415`) và `HttpMediaTypeNotAcceptableException` (`406`). Nếu ứng dụng chủ động dùng `ResponseStatusException`, hãy bảo toàn status của nó bằng handler cụ thể hoặc không để handler tổng quát ghi đè ngữ nghĩa đó.

## 7. Xử lý lỗi cho trang HTML

Ứng dụng MVC kết xuất phía máy chủ thường cần hiển thị một trang lỗi thay vì JSON. Có thể dùng `@ControllerAdvice` với `ModelAndView` để chọn template và HTTP status.

Ví dụ advice cho các Controller trang:

```java
@ControllerAdvice(basePackages = "com.example.web.page")
public class PageExceptionHandler {

    @ExceptionHandler(TaskNotFoundException.class)
    public ModelAndView handleTaskNotFound(
            TaskNotFoundException exception,
            HttpServletResponse response) {

        response.setStatus(HttpStatus.NOT_FOUND.value());

        ModelAndView view = new ModelAndView("errors/not-found");
        view.addObject("title", "Không tìm thấy công việc");
        view.addObject("message", "Công việc có thể đã bị xóa hoặc không còn khả dụng.");
        return view;
    }

    @ExceptionHandler(InvalidTaskTransitionException.class)
    public ModelAndView handleTransition(
            InvalidTaskTransitionException exception,
            HttpServletResponse response) {

        response.setStatus(HttpStatus.CONFLICT.value());

        ModelAndView view = new ModelAndView("errors/conflict");
        view.addObject("title", "Không thể thực hiện thao tác");
        view.addObject("message",
                "Trạng thái công việc đã thay đổi. Hãy tải lại trang và thử lại.");
        return view;
    }
}
```

Template lỗi có thể cung cấp liên kết quay lại danh sách, hướng dẫn tải lại hoặc mã tham chiếu hỗ trợ. Giữ HTTP status đúng dù trang lỗi được kết xuất thành HTML; nếu trả `200 OK` cho trang không tìm thấy, công cụ tìm kiếm, trình duyệt và hệ thống giám sát sẽ hiểu sai kết quả.

### Lỗi phát sinh ngay trong biểu mẫu

Không phải lỗi form nào cũng cần đi qua advice toàn cục. Khi validation trường thất bại, cách phù hợp thường là trả lại đúng template form với `BindingResult` và dữ liệu người dùng đã nhập:

```java
@PostMapping("/tasks")
public String create(
        @Valid @ModelAttribute("form") CreateTaskForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "tasks/form";
    }

    taskService.create(form);
    return "redirect:/tasks";
}
```

Với lỗi nghiệp vụ gắn trực tiếp với một trường hoặc một thao tác cụ thể, Controller có thể thêm lỗi toàn cục vào `BindingResult` bằng `errors.reject(...)` rồi render lại form. Với lỗi tài nguyên không tồn tại hoặc sự cố chung, advice tập trung thường phù hợp hơn.

Sau khi thao tác thành công, Post/Redirect/Get giúp điều hướng đến trang kết quả. Với một lỗi nghiệp vụ có thể xử lý bằng cách quay lại trang chi tiết, Controller có thể đưa thông báo vào flash attribute rồi redirect. Cần giữ dữ liệu form nếu người dùng phải sửa nội dung; không redirect rồi làm mất toàn bộ dữ liệu đã nhập.

## 8. Phân biệt lỗi nghiệp vụ với lỗi xác thực và phân quyền

Lỗi xác thực và phân quyền thường được xử lý ở Spring Security filter chain, trước khi request đến Controller. Vì vậy, không phải mọi `AuthenticationException` hoặc `AccessDeniedException` đều được một `@RestControllerAdvice` thông thường nhận trực tiếp.

Với API, có thể cấu hình `AuthenticationEntryPoint` cho trường hợp chưa xác thực và `AccessDeniedHandler` cho trường hợp đã xác thực nhưng không đủ quyền. Hai thành phần này có thể dùng chung error response factory để giữ schema nhất quán với `ControllerAdvice`.

Với ứng dụng HTML, `AuthenticationEntryPoint` thường điều hướng đến trang đăng nhập; `AccessDeniedHandler` có thể hiển thị trang không đủ quyền. Cần tránh redirect vòng lặp khi trang đăng nhập hoặc trang lỗi cũng nằm trong vùng được bảo vệ.

Một số nguyên tắc:

- Xác thực trả lời “người gửi là ai?”; phân quyền trả lời “người đó có được phép làm việc này không?”.
- Không tin vai trò hoặc ID người dùng do client gửi trong body.
- Kiểm tra quyền trên từng tài nguyên ở server.
- Có thể dùng `404` thay cho `403` khi chính sách yêu cầu không tiết lộ sự tồn tại của tài nguyên.
- Không trả chi tiết về tài khoản, nhóm hoặc tài nguyên nhạy cảm cho người không có quyền.

## 9. Xử lý lỗi không dự kiến và phản hồi an toàn

Lỗi ngoài dự kiến không nên làm lộ thông tin nội bộ. Ví dụ, response sau không an toàn:

```json
{
  "error": "org.postgresql.util.PSQLException",
  "message": "Connection to db-prod.internal:5432 failed",
  "stackTrace": "..."
}
```

Response phù hợp hơn:

```json
{
  "type": "https://example.invalid/problems/internal-error",
  "title": "Đã xảy ra lỗi máy chủ",
  "status": 500,
  "detail": "Hệ thống chưa thể hoàn tất yêu cầu. Vui lòng thử lại sau.",
  "code": "INTERNAL_ERROR",
  "traceId": "01J8EXAMPLE7Q2M4N9"
}
```

Phản hồi công khai chỉ cung cấp thông tin đủ để người dùng biết cần làm gì và để đội hỗ trợ tra cứu. Stack trace, câu SQL, host nội bộ, đường dẫn file, token và chi tiết cấu hình phải nằm trong log được kiểm soát quyền truy cập.

Một handler tổng quát có thể tạo phản hồi `500`:

```java
@ExceptionHandler(Exception.class)
public ResponseEntity<ProblemDetail> handleUnexpected(
        Exception exception,
        HttpServletRequest request) {

    Object traceValue = request.getAttribute("traceId");
    String traceId = traceValue instanceof String value ? value : null;
    log.error("Unhandled request failure; traceId={}", traceId, exception);

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "Hệ thống chưa thể hoàn tất yêu cầu. Vui lòng thử lại sau.");
    problem.setTitle("Lỗi máy chủ");
    problem.setProperty("code", "INTERNAL_ERROR");
    if (traceId != null && !traceId.isBlank()) {
        problem.setProperty("traceId", traceId);
    }

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(problem);
}
```

Ví dụ giả định `log` được cấu hình bằng SLF4J và một Filter hoặc thành phần tracing đáng tin cậy đã đặt thuộc tính `traceId` trên request. Không lấy trực tiếp header tùy ý từ client làm mã truy vết nếu chưa kiểm tra định dạng và quy tắc tạo mã. Tốt hơn là gateway hoặc ứng dụng tạo trace ID có cấu trúc, đưa vào logging context và trả mã đó trong response.

Handler tổng quát cần được đặt sau các handler cụ thể. Không bắt `Throwable` để che giấu lỗi nghiêm trọng của JVM. Cũng không nên trả cùng một status cho mọi exception đã biết; lỗi nghiệp vụ và lỗi giao thức phải được ánh xạ trước khi đến nhánh `500`.

## 10. Ghi log và quan sát lỗi

Một response tốt giúp client xử lý; log và metrics giúp đội phát triển tìm nguyên nhân. Hai mục đích này cần thông tin khác nhau.

Thông tin log hữu ích có thể gồm:

- Trace ID hoặc correlation ID.
- HTTP method, route template và status.
- Mã lỗi nghiệp vụ ổn định.
- Tên exception và stack trace đối với lỗi kỹ thuật.
- Thời gian xử lý, tên dependency và loại timeout.
- ID tài nguyên đã được bảo vệ phù hợp, nếu cần điều tra.

Không ghi mật khẩu, token, cookie phiên, toàn bộ request body hoặc thông tin cá nhân không cần thiết. Nếu cần ghi một phần dữ liệu đầu vào, phải lọc trường nhạy cảm và giới hạn độ dài.

Một số nguyên tắc vận hành:

- Lỗi `4xx` do client gửi sai thường không cần stack trace đầy đủ ở mức error; có thể ghi log có cấu trúc ở mức phù hợp.
- Lỗi `5xx` cần log nguyên nhân kỹ thuật và stack trace ở phía server.
- Tránh ghi cùng một exception nhiều lần ở Controller, Service và advice. Chọn một điểm ghi log có đủ ngữ cảnh.
- Theo dõi tỷ lệ lỗi theo route và mã lỗi để phát hiện thay đổi bất thường.
- Phân biệt lỗi nghiệp vụ dự kiến với lỗi hạ tầng để cảnh báo không bị nhiễu.
- Không để thông báo lỗi chứa dữ liệu nội bộ được hiển thị trực tiếp trong UI.

## 11. Bản địa hóa thông báo lỗi

Thông điệp dành cho người dùng có thể cần được hiển thị bằng ngôn ngữ họ chọn. Không nên dùng chuỗi tiếng Việt cố định trong Domain Model hoặc exception làm nguồn duy nhất cho mọi client.

Một cách làm là gắn mã lỗi hoặc message key với lỗi, sau đó dùng `MessageSource` để lấy thông điệp theo locale ở tầng trình bày:

```java
@ExceptionHandler(InvalidTaskTransitionException.class)
public ResponseEntity<ProblemDetail> handleTransition(
        InvalidTaskTransitionException exception,
        Locale locale) {

    String detail = messageSource.getMessage(
            "task.transition.not-allowed",
            null,
            "Không thể thực hiện thao tác ở trạng thái hiện tại.",
            locale);

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT, detail);
    problem.setTitle(messageSource.getMessage(
            "error.conflict.title", null, "Xung đột", locale));
    problem.setProperty("code", "TASK_TRANSITION_NOT_ALLOWED");

    return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
}
```

`messageSource` được inject qua constructor hoặc field theo cấu hình Spring. API có thể chọn trả message theo `Accept-Language`; client cũng có thể chỉ dùng `code` và tự bản địa hóa. Hợp đồng nên quy định rõ bên nào chịu trách nhiệm dịch thông báo.

Mã lỗi không thay đổi theo ngôn ngữ. Nhờ vậy, logic client vẫn ổn định khi thông điệp được chỉnh sửa.

## 12. Ranh giới transaction và thời điểm lỗi xuất hiện

Một lỗi nghiệp vụ có thể xảy ra trước khi ghi dữ liệu, trong transaction hoặc sau khi dữ liệu đã commit.

- **Trước transaction:** validation hoặc kiểm tra quyền có thể từ chối request mà chưa thay đổi dữ liệu.
- **Trong transaction:** nếu thao tác thất bại, transaction cần rollback để tránh lưu trạng thái dở dang.
- **Sau commit:** response hoặc một side effect bên ngoài có thể thất bại dù dữ liệu chính đã được lưu.

Với Spring, `@Transactional` mặc định rollback với `RuntimeException` và `Error`; checked exception không tự động rollback theo mặc định trừ khi cấu hình `rollbackFor` hoặc chính sách tương ứng. Vì vậy, kiểu exception và cấu hình transaction cần được thiết kế có chủ đích.

Không nên bắt exception trong Service rồi tiếp tục như thể transaction vẫn an toàn nếu trạng thái đã bị đánh dấu rollback-only. Nếu cần trả một kết quả thất bại dự kiến mà không rollback, hãy cân nhắc dùng result type rõ ràng hoặc đặt ranh giới transaction phù hợp.

Với side effect như gửi email hoặc gọi cổng thanh toán, transaction database không thể rollback hành động đã xảy ra ở hệ thống ngoài. Có thể dùng transactional outbox, retry có kiểm soát và quy trình đối soát để quản lý tình huống này.

## 13. Kiểm thử chuyển lỗi thành phản hồi

Kiểm thử lỗi cần xác nhận cả nguyên nhân nghiệp vụ và hợp đồng HTTP/HTML mà client nhìn thấy.

| Mức kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Unit test Model | Quy tắc ném lỗi hoặc trả kết quả đúng | Không hoàn thành công việc đã hủy |
| Unit test Service | Exception được truyền hoặc chuyển đúng | Không tìm thấy công việc; actor không có quyền |
| MVC test | Exception được ánh xạ đúng status và body | `409`, `404`, mã lỗi và trường `detail` |
| HTML controller test | Đúng template, status và thông báo | Trang `errors/not-found` với `404` |
| Security test | Entry point và access denied trả đúng response | `401`/`403` hoặc redirect đăng nhập |
| Integration test | Transaction rollback và dữ liệu không bị lưu dở | Lỗi giữa quá trình cập nhật |
| Observability test | Trace ID có trong log/response theo hợp đồng | Có thể tra cứu lỗi mà không lộ dữ liệu nhạy cảm |

Ví dụ kiểm thử API với MockMvc:

```java
@WebMvcTest(TaskApiController.class)
class TaskApiControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    TaskCommandService taskCommandService;

    @Test
    void mapsInvalidTransitionToConflictProblem() throws Exception {
        given(taskCommandService.complete(42L, 7L))
                .willThrow(new InvalidTaskTransitionException(
                        TaskStatus.CANCELLED, TaskStatus.COMPLETED));

        mockMvc.perform(post("/api/tasks/42/complete")
                        .with(authentication(testAuthenticationForUser(7L)))
                        .with(csrf()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.code")
                        .value("TASK_TRANSITION_NOT_ALLOWED"));
    }
}
```

Test này giả định cấu hình Spring MVC advice được nạp trong test slice, CSRF được bật và `testAuthenticationForUser` là helper trả về `Authentication` có principal đúng kiểu `AppUserPrincipal` mà Controller yêu cầu. Với Spring Boot phiên bản mới, có thể thay `@MockBean` bằng API mock bean tương ứng. Cần bổ sung test cho lỗi không tìm thấy, lỗi validation, exception không dự kiến và lỗi bảo mật.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Trả nguyên `exception.getMessage()` cho client | Lộ chi tiết nội bộ hoặc thông điệp khó hiểu | Ánh xạ sang thông điệp công khai và mã lỗi ổn định |
| Model phụ thuộc `HttpStatus` | Nghiệp vụ bị gắn với HTTP | Dùng exception hoặc result type thuộc miền |
| Mọi lỗi đều trả `500` | Client không phân biệt lỗi nhập, quyền và xung đột | Ánh xạ lỗi đã biết sang status phù hợp |
| Mọi lỗi đều trả `200` | Giám sát và client hiểu sai kết quả | Dùng status HTTP đúng ngữ nghĩa |
| Controller nào cũng tự bắt và định dạng lỗi | Logic lặp, response không nhất quán | Dùng `@ControllerAdvice` hoặc `@RestControllerAdvice` |
| Dùng một advice cho cả HTML và API mà không giới hạn | Trang web có thể nhận JSON hoặc API nhận HTML | Phân phạm vi advice theo package hoặc loại Controller |
| Trả stack trace cho client | Tiết lộ cấu trúc hệ thống và thông tin nhạy cảm | Ghi log nội bộ, trả lỗi chung kèm trace ID |
| Ghi log exception ở mọi tầng | Log trùng và khó tìm nguyên nhân | Chọn một điểm log có đủ ngữ cảnh |
| Coi lỗi xác thực luôn đi qua ControllerAdvice | Không xử lý được lỗi xảy ra trong Security filter chain | Cấu hình AuthenticationEntryPoint và AccessDeniedHandler |
| Bỏ qua rollback khi lỗi | Có thể lưu trạng thái dở dang | Thiết kế transaction và rollback policy rõ ràng |

## 15. Quy trình thiết kế phản hồi cho một lỗi

Khi thêm một quy tắc hoặc endpoint, hãy xác định:

1. Lỗi thuộc validation đầu vào, quy tắc nghiệp vụ, xác thực, phân quyền, xung đột hay kỹ thuật?
2. Lỗi được phát hiện ở Model, Service, Controller, filter hay tầng tích hợp?
3. Đây là kết quả dự kiến nên trả bằng result type, hay exception phù hợp hơn?
4. Với client hiện tại, HTTP status nào phản ánh đúng tình huống?
5. Client cần mã lỗi ổn định, danh sách trường sai hoặc hướng dẫn hành động nào?
6. Phản hồi là HTML hay JSON, và advice nào chịu trách nhiệm?
7. Thông điệp có cần bản địa hóa không? Có đang tiết lộ dữ liệu nội bộ không?
8. Lỗi xảy ra trước hay sau commit; dữ liệu có cần rollback hoặc đối soát không?
9. Log và trace có đủ ngữ cảnh để điều tra mà không ghi dữ liệu nhạy cảm không?
10. Có kiểm thử status, schema lỗi, template, bảo mật và transaction không?

Chuyển lỗi nghiệp vụ thành phản hồi có ý nghĩa là giữ nguyên quy tắc ở Model và Service, sau đó diễn đạt kết quả theo hợp đồng của từng client. `ControllerAdvice` giúp tập trung ánh xạ exception; HTML cần trang và hướng dẫn phù hợp; API cần status, mã lỗi và cấu trúc ổn định. Khi thông điệp công khai được tách khỏi chi tiết nội bộ, log có kiểm soát và transaction được xử lý đúng, ứng dụng MVC vừa dễ sử dụng vừa dễ vận hành.
