# Thiết kế Controller nhỏ, rõ trách nhiệm và dễ kiểm thử

## Mục tiêu

Controller là điểm tiếp nhận tương tác từ bên ngoài và điều phối yêu cầu đến phần xử lý phù hợp. Trong ứng dụng web MVC, Controller thường làm việc với HTTP: nhận route, đọc path/query/form/body, phối hợp xác thực và phân quyền, gọi ca sử dụng, rồi chọn kiểu phản hồi.

Controller sẽ khó bảo trì nếu đồng thời chứa quy tắc nghiệp vụ, truy vấn cơ sở dữ liệu, tính toán, chuyển đổi dữ liệu phức tạp và xử lý mọi loại lỗi. Một Controller tốt giữ vai trò ở ranh giới giao tiếp: hiểu yêu cầu của giao diện, chuyển nó thành lời gọi có cấu trúc và chuyển kết quả thành phản hồi phù hợp.

Sau khi học, người học có thể:

- Xác định trách nhiệm phù hợp của Controller trong MVC.
- Thiết kế endpoint và hợp đồng request/response rõ ràng.
- Tách validation đầu vào khỏi quy tắc nghiệp vụ.
- Điều phối application service mà không để Controller chứa nghiệp vụ.
- Trả response, redirect và lỗi theo đúng ngữ nghĩa HTTP.
- Đặt kiểm tra bảo mật ở đúng ranh giới.
- Kiểm thử Controller độc lập với cơ sở dữ liệu và nghiệp vụ cốt lõi.

## 1. Controller là ranh giới giữa giao thức và ứng dụng

Trong một ứng dụng web, trình duyệt hoặc client gửi HTTP request. Request có thể chứa:

- HTTP method như GET, POST, PUT, PATCH hoặc DELETE.
- Đường dẫn và path variable.
- Query parameter.
- Header, cookie và thông tin xác thực.
- Dữ liệu form hoặc request body.
- Ngữ cảnh người dùng hiện tại.

Controller tiếp nhận những thông tin này và chuyển chúng thành lời gọi đến phần ứng dụng chịu trách nhiệm thực hiện ca sử dụng.

Một luồng điển hình:

    Client
      |
      | HTTP request
      v
    Router / Dispatcher
      |
      v
    Controller
      |
      | kiểm tra đầu vào ở ranh giới, tạo command/query
      v
    Application Service
      |
      | gọi domain model và các cổng cần thiết
      v
    Domain / Repository / External Adapter
      |
      | kết quả
      v
    Application Service
      |
      v
    Controller
      |
      | chọn status, header, redirect hoặc view
      v
    HTTP response

Controller không cần biết cơ sở dữ liệu được truy vấn bằng SQL, ORM hay dịch vụ từ xa. Nó cũng không nên tự quyết định một quy tắc như đơn hàng có được hủy hay không. Controller chuyển yêu cầu đến nơi sở hữu quy tắc và diễn giải kết quả thành giao thức mà client hiểu.

### Những trách nhiệm phù hợp

Một Controller thường có các trách nhiệm sau:

1. Ánh xạ route và HTTP method đến hành động phù hợp.
2. Nhận dữ liệu từ path, query, header, form hoặc body.
3. Kiểm tra hình thức và ràng buộc đầu vào ở ranh giới.
4. Lấy danh tính người dùng từ ngữ cảnh bảo mật và phối hợp kiểm tra quyền.
5. Tạo command/query hoặc gọi application service.
6. Chuyển kết quả thành View Model, response DTO, redirect hoặc status code.
7. Chuyển lỗi đã biết sang phản hồi phù hợp theo quy ước của ứng dụng.

Những việc này đều liên quan đến giao tiếp giữa client và ứng dụng. Khi Controller thực hiện nhiều công việc bên trong nghiệp vụ hoặc hạ tầng, ranh giới bắt đầu bị mờ.

## 2. Giữ Controller nhỏ bằng cách tách đúng trách nhiệm

Một Controller nhỏ không nhất thiết chỉ có vài dòng. Điều quan trọng là mỗi phương thức endpoint thể hiện rõ một hành động và không tự thực hiện những quy tắc thuộc lớp khác.

### Controller không nên chứa quy tắc nghiệp vụ

Ví dụ sau có quá nhiều trách nhiệm:

    @PostMapping("/{id}/cancel")
    public String cancel(@PathVariable UUID id, Principal principal) {
        Order order = orderRepository.findById(id).orElseThrow();

        if (order.getStatus() == OrderStatus.PAID) {
            throw new IllegalStateException("Không thể hủy");
        }

        if (!order.getCustomerEmail().equals(principal.getName())) {
            throw new AccessDeniedException("Không có quyền");
        }

        order.setStatus(OrderStatus.CANCELLED);
        orderRepository.save(order);

        emailService.sendCancellationEmail(order);

        return "redirect:/orders";
    }

Phương thức này tự tải dữ liệu, kiểm tra quyền, áp dụng quy tắc chuyển trạng thái, sửa entity, lưu trữ và gửi email. Nó khó kiểm thử độc lập và dễ bỏ sót quy tắc khi một luồng khác cũng cần hủy đơn hàng.

Hãy để Controller gọi một ca sử dụng:

    @PostMapping("/{id}/cancel")
    public String cancel(@PathVariable UUID id) {
        cancelOrder.execute(id);
        return "redirect:/orders";
    }

Trong thực tế, ca sử dụng cần nhận cả danh tính hoặc ngữ cảnh người dùng nếu việc hủy phụ thuộc vào quyền sở hữu:

    @PostMapping("/{id}/cancel")
    public String cancel(
            @PathVariable UUID id,
            @AuthenticationPrincipal AppPrincipal principal) {

        cancelOrder.execute(id, principal.userId());
        return "redirect:/orders";
    }

Application service kiểm tra quyền và điều phối thao tác. Domain model bảo vệ chuyển đổi trạng thái. Repository và adapter đảm nhiệm lưu trữ hoặc tích hợp. Controller chỉ kết nối request với ca sử dụng và chọn phản hồi.

### Controller không nên truy cập repository trực tiếp cho ca sử dụng

Một truy vấn đọc đơn giản đôi khi có thể được phục vụ qua query service. Để Controller phụ thuộc vào repository và tự ghép nhiều bảng thường làm lộ chi tiết lưu trữ vào lớp giao tiếp.

Thay vào đó, dùng một query service trả về dữ liệu phù hợp với màn hình hoặc API:

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        OrderDetailsPage page = orderQueryService.getDetailsPage(id);
        model.addAttribute("page", page);
        return "orders/detail";
    }

Query service chịu trách nhiệm lấy và chuẩn bị dữ liệu. Controller chỉ đưa kết quả vào model của View.

### Controller không nên định dạng dữ liệu phức tạp

Định dạng một giá trị đơn giản có thể thuộc presentation layer, nhưng Controller không nên chứa hàng loạt phép tính về tiền, thuế, thời gian hoặc chính sách. Hãy trả dữ liệu có cấu trúc phù hợp cho View hoặc response mapper chuyên trách.

## 3. Thiết kế endpoint theo hành động và ngữ nghĩa HTTP

Một Controller rõ ràng bắt đầu từ hợp đồng HTTP có thể hiểu được.

| Ý định | HTTP method thường dùng | Ví dụ route | Kết quả thường gặp |
|---|---|---|---|
| Đọc danh sách | GET | /orders | 200 OK |
| Đọc chi tiết | GET | /orders/{id} | 200 OK hoặc 404 Not Found |
| Tạo tài nguyên | POST | /orders | 201 Created hoặc redirect sau khi tạo |
| Thay thế toàn bộ | PUT | /orders/{id} | 200 OK hoặc 204 No Content |
| Cập nhật một phần | PATCH | /orders/{id} | 200 OK hoặc 204 No Content |
| Xóa tài nguyên | DELETE | /orders/{id} | 204 No Content hoặc 404 Not Found |

Đây là quy ước phổ biến, không phải công thức bắt buộc cho mọi API. Hãy chọn method và status theo ý nghĩa thực tế của thao tác.

### GET dùng để đọc

GET nên an toàn theo nghĩa không làm thay đổi trạng thái nghiệp vụ. Không dùng một liên kết GET để hủy đơn hàng, thanh toán hoặc xóa dữ liệu. Trình duyệt, crawler, proxy hoặc công cụ tiền tải có thể truy cập URL GET ngoài ý muốn của người dùng.

### POST, PUT, PATCH và DELETE thể hiện thay đổi

Các thao tác thay đổi dữ liệu cần được biểu diễn bằng method phù hợp. Với ứng dụng dùng session/cookie, cần cấu hình CSRF protection theo framework cho các request thay đổi trạng thái.

### Tránh route mơ hồ

Tên route nên thể hiện tài nguyên và quan hệ một cách nhất quán. Ví dụ:

- GET /courses/{courseId}/registrations đọc danh sách đăng ký của khóa học.
- POST /courses/{courseId}/registrations tạo đăng ký mới.
- DELETE /registrations/{registrationId} hủy hoặc xóa đăng ký theo chính sách API.

Nếu thao tác là một chuyển trạng thái đặc thù, route dạng /orders/{id}/cancel có thể dễ hiểu. Điều quan trọng là method, tên và hành vi phải nhất quán.

## 4. Thiết kế hợp đồng request và response

Controller là ranh giới giao tiếp, vì vậy không nên để client phụ thuộc trực tiếp vào entity hoặc cấu trúc lưu trữ nội bộ.

### Dùng request DTO cho dữ liệu đầu vào

Giả sử người học đăng ký một khóa học. Request có thể chỉ cần mã khóa học:

    public record CreateRegistrationRequest(
            @NotBlank String courseId) {
    }

Nếu dùng biểu mẫu phía máy chủ, có thể định nghĩa form object riêng. Nếu dùng API JSON, request DTO biểu diễn cấu trúc JSON mà client gửi.

Không nên nhận trực tiếp entity JPA làm request body. Nếu bind entity, client có thể gửi các trường nội bộ như status, ownerId, createdAt hoặc các quan hệ mà họ không được phép thay đổi. DTO giới hạn hợp đồng đầu vào và giúp kiểm soát dữ liệu rõ ràng.

### Dùng response DTO cho API

Response DTO chỉ chứa dữ liệu được phép công khai:

    public record RegistrationResponse(
            UUID id,
            String courseId,
            String status,
            Instant createdAt) {
    }

Không trả entity nguyên trạng. Việc trả entity có thể làm lộ trường nội bộ, gây vòng lặp serialization qua quan hệ hai chiều, tải dữ liệu ngoài dự kiến hoặc khiến thay đổi schema cơ sở dữ liệu ảnh hưởng trực tiếp đến client.

### Giữ hợp đồng ổn định

Tên trường, kiểu dữ liệu, ý nghĩa null, format ngày giờ và cách biểu diễn lỗi đều là một phần của hợp đồng API. Thay đổi chúng có thể ảnh hưởng đến client đang sử dụng.

Với ứng dụng web render server-side, View Model có thể được thiết kế theo nhu cầu màn hình. Với API, response DTO nên phản ánh hợp đồng công khai của endpoint. Hai loại này có thể dùng chung một số cấu trúc nhưng không bắt buộc là cùng một lớp.

## 5. Phân biệt binding, validation và quy tắc nghiệp vụ

Ba bước này thường bị nhầm lẫn, nhưng có mục đích khác nhau.

| Loại | Câu hỏi | Ví dụ | Nơi xử lý |
|---|---|---|---|
| Binding / parsing | Có chuyển dữ liệu request thành kiểu mong muốn được không? | UUID đúng định dạng, số lượng chuyển được thành số nguyên | Framework và Controller boundary |
| Validation đầu vào | Dữ liệu có đáp ứng ràng buộc hình thức không? | courseId không rỗng, quantity lớn hơn 0 | DTO/form validation |
| Quy tắc nghiệp vụ | Thao tác có hợp lệ trong trạng thái hiện tại không? | Khóa học còn chỗ, học viên chưa đăng ký khóa học này | Domain/application service |

Ví dụ, @NotBlank có thể xác nhận courseId không rỗng. Nó không thể chứng minh khóa học tồn tại, đang mở đăng ký hoặc người học đủ điều kiện. Những điều kiện đó cần được kiểm tra khi thực hiện ca sử dụng.

### Ví dụ Controller xử lý biểu mẫu Spring MVC

    public record RegistrationForm(
            @NotBlank String courseId) {
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
            model.addAttribute("form", new RegistrationForm(""));
            return "registrations/new";
        }

        @PostMapping
        public String create(
                @AuthenticationPrincipal AppPrincipal principal,
                @Valid @ModelAttribute("form") RegistrationForm form,
                BindingResult errors,
                RedirectAttributes redirectAttributes) {

            if (errors.hasErrors()) {
                return "registrations/new";
            }

            registerForCourse.execute(
                    new RegisterForCourseCommand(
                            principal.userId(),
                            form.courseId()));

            redirectAttributes.addFlashAttribute(
                    "message", "Đăng ký khóa học thành công");

            return "redirect:/registrations";
        }
    }

Trong ví dụ:

- GET /registrations/new tạo form để hiển thị.
- POST /registrations nhận dữ liệu form và kiểm tra validation.
- BindingResult đặt ngay sau tham số được đánh dấu @Valid để Controller có thể đọc lỗi binding/validation.
- Danh tính học viên lấy từ principal đã xác thực, không nhận studentId tùy ý từ form.
- Controller gọi ca sử dụng RegisterForCourse.
- Sau thành công, Controller chuyển hướng đến trang danh sách và gửi thông báo tạm thời.

Nếu dữ liệu không hợp lệ, Controller trả lại form cùng lỗi để người dùng sửa. Nếu dữ liệu hợp lệ về mặt cấu trúc nhưng vi phạm nghiệp vụ, ca sử dụng có thể trả một lỗi miền nghiệp vụ được ánh xạ thành thông báo phù hợp.

### Ví dụ Controller cho REST API

    @RestController
    @RequestMapping("/api/registrations")
    public class RegistrationApiController {
        private final RegisterForCourse registerForCourse;

        public RegistrationApiController(RegisterForCourse registerForCourse) {
            this.registerForCourse = registerForCourse;
        }

        @PostMapping
        public ResponseEntity<RegistrationResponse> create(
                @AuthenticationPrincipal AppPrincipal principal,
                @Valid @RequestBody CreateRegistrationRequest request) {

            RegistrationResult result = registerForCourse.execute(
                    new RegisterForCourseCommand(
                            principal.userId(),
                            request.courseId()));

            RegistrationResponse response = new RegistrationResponse(
                    result.id(),
                    result.courseId(),
                    result.status().name(),
                    result.createdAt());

            URI location = URI.create("/api/registrations/" + result.id());

            return ResponseEntity.created(location).body(response);
        }
    }

Đây là một ví dụ minh họa. Trong dự án thực tế, kiểu principal, command và result phụ thuộc vào cấu trúc ứng dụng. Điểm quan trọng là Controller chuyển đổi giữa hợp đồng HTTP và hợp đồng ca sử dụng; nó không tự thực hiện nghiệp vụ đăng ký.

## 6. Xử lý lỗi nhất quán

Một Controller không nên chứa nhiều khối try/catch giống nhau cho mọi endpoint. Nếu mọi phương thức tự chuyển lỗi thành response, quy tắc HTTP có thể không nhất quán và logic điều khiển bị phân tán.

Hãy xác định các nhóm lỗi thường gặp:

- Lỗi binding hoặc validation: request sai cấu trúc hoặc vi phạm ràng buộc đầu vào.
- Không tìm thấy tài nguyên: ID không tồn tại hoặc tài nguyên không được phép tiết lộ.
- Không có quyền: người dùng đã xác thực nhưng không được phép thực hiện hành động.
- Xung đột nghiệp vụ: trạng thái hiện tại không cho phép thao tác, hoặc dữ liệu xung đột.
- Lỗi không dự kiến: sự cố hạ tầng hoặc lỗi lập trình.

Với REST API, có thể dùng một cấu trúc lỗi thống nhất:

    public record ApiError(
            String code,
            String message,
            Map<String, String> fieldErrors) {
    }

Một lớp xử lý lỗi tập trung có thể ánh xạ exception sang status và body:

    @RestControllerAdvice
    public class ApiExceptionHandler {

        @ExceptionHandler(CourseNotFoundException.class)
        ResponseEntity<ApiError> courseNotFound(
                CourseNotFoundException exception) {

            ApiError error = new ApiError(
                    "COURSE_NOT_FOUND",
                    "Không tìm thấy khóa học",
                    Map.of());

            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
        }

        @ExceptionHandler(RegistrationConflictException.class)
        ResponseEntity<ApiError> registrationConflict(
                RegistrationConflictException exception) {

            ApiError error = new ApiError(
                    "REGISTRATION_CONFLICT",
                    "Không thể đăng ký khóa học ở trạng thái hiện tại",
                    Map.of());

            return ResponseEntity.status(HttpStatus.CONFLICT).body(error);
        }
    }

Trong ví dụ, thông tin chi tiết exception không được đưa thẳng ra client. Ứng dụng có thể ghi log với correlation ID để đội vận hành tra cứu, trong khi response chỉ cung cấp thông tin an toàn và hữu ích.

Các lỗi validation của request body có thể được framework xử lý thành 400 Bad Request. Nếu cần định dạng lỗi thống nhất, có thể bổ sung handler cho exception validation tương ứng với phiên bản Spring đang dùng.

Với ứng dụng render View, lỗi validation thường quay lại form để hiển thị cạnh trường. Lỗi không tìm thấy có thể render trang 404. Lỗi không có quyền có thể render 403 hoặc chuyển đến trang đăng nhập tùy chính sách xác thực.

Không nên bắt mọi exception rồi trả 200 OK hoặc một thông báo thành công giả. Status code phải phản ánh kết quả thực tế.

## 7. Chọn response phù hợp với loại ứng dụng

Controller cần chọn phản hồi dựa trên hợp đồng của client.

### Server-side rendering

Với form HTML, sau khi POST thành công, mô hình Post/Redirect/Get (PRG) giúp trình duyệt tải trang kết quả bằng GET. Điều này hạn chế việc gửi lại form khi người dùng refresh.

Luồng thường gặp:

    Browser
      |
      | POST /registrations
      v
    RegistrationController
      |
      | gọi ca sử dụng và lưu thành công
      v
    3xx redirect (có thể dùng 303 See Other)
      |
      | GET /registrations
      v
    HTML response

Với lỗi validation, có thể trả lại cùng View và giữ các trường người dùng đã nhập để họ sửa. Với thành công, dùng flash attribute cho thông báo chỉ tồn tại qua lần chuyển hướng tiếp theo.

### REST API

Một số status thường gặp:

- 200 OK: request thành công và có response body.
- 201 Created: đã tạo tài nguyên; thường kèm Location trỏ đến tài nguyên mới.
- 202 Accepted: đã tiếp nhận xử lý bất đồng bộ, kết quả cuối cùng chưa hoàn tất.
- 204 No Content: thao tác thành công nhưng không cần body.
- 400 Bad Request: request không hợp lệ.
- 401 Unauthorized: thiếu hoặc không hợp lệ thông tin xác thực.
- 403 Forbidden: đã xác thực nhưng không có quyền.
- 404 Not Found: không tìm thấy tài nguyên.
- 409 Conflict: xung đột với trạng thái hiện tại hoặc quy tắc nghiệp vụ.
- 422 Unprocessable Content: cú pháp request hợp lệ nhưng nội dung không thể xử lý theo ngữ nghĩa của API, nếu hợp đồng chọn dùng status này.

Chọn status nhất quán và mô tả trong tài liệu API. Không cần dùng mọi status cho mọi dự án.

### Tránh trả dữ liệu nội bộ

Không đưa stack trace, câu SQL, đường dẫn file nội bộ, token, mật khẩu hoặc chi tiết cấu hình vào response. Lỗi cần đủ thông tin để client xử lý nhưng không tiết lộ bí mật của hệ thống.

## 8. Bảo mật ở ranh giới Controller

Controller nằm tại ranh giới mà dữ liệu không đáng tin cậy đi vào ứng dụng. Vì vậy, bảo mật cần được áp dụng xuyên suốt.

### Xác thực và phân quyền

Xác thực trả lời câu hỏi “người gọi là ai?”. Phân quyền trả lời “người gọi có được thực hiện hành động này trên tài nguyên này không?”.

Không lấy userId hoặc role từ một trường request do client tự gửi rồi tin rằng đó là danh tính thật. Dùng principal hoặc security context do cơ chế xác thực của server cung cấp.

Ví dụ, một người dùng có thể được phép xem một số đơn hàng nhưng chỉ được hủy đơn hàng do chính họ sở hữu. Việc kiểm tra quyền trên tài nguyên cần được thực hiện ở phía server, thường qua method security hoặc application service có đủ ngữ cảnh. Ẩn nút trong View không phải kiểm soát truy cập.

### Validation không thay thế bảo mật

Dữ liệu hợp lệ về kiểu và độ dài vẫn có thể chứa giá trị độc hại hoặc yêu cầu thao tác trái phép. Cần kết hợp:

- Ràng buộc kiểu, độ dài, định dạng và miền giá trị đầu vào.
- Kiểm tra quyền truy cập trên tài nguyên.
- Parameterized query hoặc ORM an toàn khi truy cập dữ liệu.
- Escape dữ liệu đầu ra theo ngữ cảnh.
- CSRF protection khi dùng cookie/session cho request thay đổi trạng thái.
- Giới hạn kích thước request và tần suất gọi ở những endpoint phù hợp.

### Không bind trực tiếp entity

Client không nên được phép sửa các trường nội bộ chỉ vì framework có thể bind chúng. Request DTO chỉ nên chứa trường mà thao tác cụ thể cho phép. Ví dụ, form cập nhật địa chỉ giao hàng không nên có status, paidAt hay customerId.

## 9. Thiết kế Controller để dễ kiểm thử

Controller dễ kiểm thử khi phụ thuộc vào các hợp đồng nhỏ, nhận dữ liệu đầu vào rõ ràng và trả phản hồi xác định. Không nên cần cơ sở dữ liệu thật chỉ để kiểm tra route có nhận đúng request hay không.

Có thể chia kiểm thử thành các lớp:

| Loại kiểm thử | Phạm vi | Điều cần xác nhận |
|---|---|---|
| Unit test application service | Quy tắc và điều phối ca sử dụng | Kết quả hợp lệ, lỗi nghiệp vụ, quyền và transaction |
| Controller test | Binding, validation, status, redirect, response body | HTTP contract và lời gọi đến use case |
| MVC slice test | Controller cùng các thành phần web liên quan | Routing, serialization, validation, exception advice |
| Integration test | Kết nối thật với persistence hoặc hệ thống tích hợp | Mapping, transaction và truy vấn |

### Kiểm thử HTTP contract

Với Spring MVC, MockMvc có thể gửi request mà không cần mở server thật. Có thể dùng @WebMvcTest để chỉ nạp lớp web và mock application service, hoặc dùng standaloneSetup khi muốn kiểm thử Controller với cấu hình tối thiểu.

Ví dụ với standalone MockMvc:

    @ExtendWith(MockitoExtension.class)
    class RegistrationApiControllerTest {

        @Mock
        RegisterForCourse registerForCourse;

        private MockMvc mvc;

        @BeforeEach
        void setUp() {
            RegistrationApiController controller =
                    new RegistrationApiController(registerForCourse);

            mvc = MockMvcBuilders
                    .standaloneSetup(controller)
                    .build();
        }

        @Test
        void rejectsBlankCourseId() throws Exception {
            mvc.perform(post("/api/registrations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"courseId\":\" \"}"))
                .andExpect(status().isBadRequest());

            verifyNoInteractions(registerForCourse);
        }
    }

Ví dụ cần đăng ký validator phù hợp trong cấu hình standalone hoặc dùng cấu hình kiểm thử web slice của dự án để kiểm tra Bean Validation thực sự được kích hoạt. Khi dùng @WebMvcTest, hãy kiểm tra rằng validator và các cấu hình cần thiết đã được nạp.

Một số trường hợp nên kiểm thử:

- Request hợp lệ gọi đúng application service và trả status mong đợi.
- Request thiếu trường hoặc sai định dạng bị từ chối trước khi gọi ca sử dụng.
- ID không tồn tại được ánh xạ thành 404.
- Xung đột nghiệp vụ được ánh xạ thành 409 theo hợp đồng.
- Người dùng chưa xác thực hoặc không đủ quyền bị từ chối.
- Form HTML lỗi validation được render lại cùng lỗi.
- POST thành công chuyển hướng đúng đích.
- Response không chứa trường nội bộ hoặc thông tin nhạy cảm.

### Kiểm thử đúng lớp

Không cần viết lại toàn bộ quy tắc nghiệp vụ trong Controller test. Hãy kiểm tra rằng Controller gọi đúng use case và phản hồi đúng theo kết quả. Quy tắc nghiệp vụ được kiểm thử trong domain/application service test. Truy vấn và ánh xạ persistence được kiểm thử trong integration test.

Cách phân chia này giúp một test thất bại chỉ ra rõ vùng có vấn đề.

## 10. Dấu hiệu Controller đang phình to

Hãy xem xét refactor nếu Controller có những dấu hiệu sau:

- Một endpoint chứa nhiều nhánh if/else để quyết định chính sách nghiệp vụ.
- Controller gọi nhiều repository rồi tự ghép dữ liệu.
- Có nhiều setter trên entity được gọi trực tiếp từ Controller.
- Nhiều endpoint lặp lại cùng một khối kiểm tra quyền hoặc chuyển đổi lỗi.
- Controller gửi email, gọi cổng thanh toán hoặc phát thông điệp trực tiếp.
- Phương thức có quá nhiều tham số rời rạc hoặc nhận entity đầy đủ từ request.
- Kiểm thử endpoint buộc phải dựng database và nhiều hệ thống bên ngoài.
- Thay đổi một quy tắc nghiệp vụ làm nhiều Controller phải sửa.

Một quy trình refactor thực tế:

1. Xác định endpoint đang phục vụ ca sử dụng nào.
2. Tách request DTO và response/view model nếu hợp đồng đang dùng entity.
3. Chuyển quy tắc nghiệp vụ vào domain model hoặc domain service.
4. Chuyển việc tải/lưu dữ liệu và điều phối sang application service.
5. Đưa xử lý lỗi lặp lại về exception handler hoặc cơ chế tập trung.
6. Giữ Controller ở mức nhận request, gọi use case và tạo response.
7. Viết hoặc cập nhật test cho HTTP contract và ca sử dụng tương ứng.

Đừng đo chất lượng Controller chỉ bằng số dòng. Một phương thức dài hơn đôi chút để xử lý binding, validation và phản hồi có thể vẫn rõ ràng. Hãy đánh giá xem nó có chứa nhiều lý do thay đổi khác nhau hay không.

## 11. Checklist khi thiết kế Controller

Trước khi hoàn tất một endpoint, hãy kiểm tra:

- Route và HTTP method thể hiện đúng ý nghĩa thao tác.
- Request DTO chỉ chứa dữ liệu client được phép gửi.
- Validation hình thức diễn ra ở ranh giới.
- Quy tắc nghiệp vụ được thực thi trong domain/application layer.
- Danh tính lấy từ security context, không tin trường nhận dạng do client tự khai báo.
- Quyền trên tài nguyên được kiểm tra ở phía server.
- Controller gọi một ca sử dụng rõ ràng và không tự thao tác repository tùy tiện.
- Response DTO hoặc View Model không làm lộ entity và dữ liệu nội bộ.
- Status code, redirect và lỗi phù hợp với hợp đồng.
- Các endpoint quan trọng có kiểm thử HTTP contract.
- Các thao tác thay đổi trạng thái được bảo vệ bằng cơ chế bảo mật phù hợp như CSRF khi dùng session/cookie.

## Kết luận

Controller là bộ chuyển đổi giữa giao thức bên ngoài và ca sử dụng của ứng dụng. Nó nhận request, kiểm tra cấu trúc đầu vào, phối hợp bảo mật, gọi application service và tạo response hoặc View phù hợp.

Một Controller dễ bảo trì thể hiện rõ endpoint đang làm gì, dùng hợp đồng dữ liệu có giới hạn và không tự sở hữu quy tắc nghiệp vụ hay chi tiết lưu trữ. Khi Controller nhỏ và có ranh giới rõ ràng, nhóm phát triển có thể kiểm thử HTTP contract độc lập, kiểm thử nghiệp vụ ở đúng lớp và thay đổi giao diện mà ít ảnh hưởng đến phần lõi ứng dụng.
