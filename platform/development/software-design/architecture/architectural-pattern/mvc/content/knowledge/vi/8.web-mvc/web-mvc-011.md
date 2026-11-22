# Trả biểu diễn dữ liệu và quan hệ với API

## Mục tiêu

Trong ứng dụng MVC trên web, Controller nhận HTTP request và quyết định cách trả kết quả cho client. Kết quả có thể là một trang HTML được render bằng View, một tài liệu JSON cho API, hoặc một biểu diễn khác theo hợp đồng HTTP. Dữ liệu nghiệp vụ và biểu diễn gửi ra ngoài có liên hệ với nhau, nhưng không nên bị đồng nhất.

Bài học này giải thích cách chọn biểu diễn phản hồi, cách MVC phối hợp với API, cách thiết kế DTO và hợp đồng JSON, cũng như cách sử dụng status code, header, liên kết tài nguyên, phân trang, cache và xử lý lỗi. Các ví dụ dùng Spring MVC để minh họa.

Sau khi học, người học có thể:

- Phân biệt dữ liệu miền nghiệp vụ với biểu diễn HTTP trả cho client.
- Giải thích quan hệ giữa Controller, View, response DTO và API.
- Chọn HTML hoặc JSON dựa trên mục đích request và hợp đồng endpoint.
- Sử dụng Accept, Content-Type và content negotiation đúng cách.
- Thiết kế response DTO ổn định, có giới hạn và an toàn.
- Trả status code, header, lỗi và liên kết tài nguyên phù hợp.
- Thiết kế danh sách có phân trang và cache HTTP.
- Kiểm thử hợp đồng biểu diễn của endpoint.

## 1. Biểu diễn dữ liệu là gì?

Biểu diễn dữ liệu (representation) là hình thức mà server dùng để truyền thông tin về một tài nguyên hoặc kết quả xử lý cho client. Cùng một dữ liệu nghiệp vụ có thể được trình bày theo nhiều cách tùy loại client và mục đích sử dụng.

Ví dụ, một khóa học có mã, tên, mô tả, lịch học và số chỗ còn lại. Ứng dụng có thể trả:

- HTML để trình duyệt hiển thị trang chi tiết khóa học.
- JSON để ứng dụng di động hoặc frontend đơn trang đọc dữ liệu.
- CSV để người dùng tải danh sách.
- Một định dạng khác nếu API có hợp đồng hỗ trợ rõ ràng.

Dữ liệu nghiệp vụ không thay đổi chỉ vì cách biểu diễn thay đổi. Một khóa học vẫn là cùng một khóa học dù được render thành HTML hay serialize thành JSON.

### Phân biệt ba khái niệm

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Domain model | Biểu diễn khái niệm, trạng thái và quy tắc nghiệp vụ | Course, Registration, Schedule |
| View model / response DTO | Chọn và tổ chức dữ liệu phù hợp cho một màn hình hoặc hợp đồng API | CourseDetailsPage, CourseResponse |
| HTTP representation | Dạng dữ liệu thực tế được gửi qua mạng, kèm media type | HTML với text/html, JSON với application/json |

Không nên trả trực tiếp entity lưu trữ chỉ vì framework có thể serialize nó. Entity thường có quan hệ nội bộ, trạng thái quản lý bởi ORM và trường không dành cho client. Một DTO tạo ranh giới rõ ràng giữa mô hình bên trong và hợp đồng công khai.

### View cũng là một cách tạo representation

Trong server-side rendering, View template nhận dữ liệu từ Controller và tạo HTML. Trong API, Controller có thể trả DTO để framework chuyển thành JSON. Cả hai đều tạo representation cho client, nhưng cách trình bày và hợp đồng khác nhau.

View không nhất thiết luôn là một file template. Với REST API, phần tạo response body thường do message converter và serializer đảm nhiệm. Controller vẫn điều phối request và quyết định loại phản hồi.

## 2. Quan hệ giữa MVC trên web và API

MVC và API giải quyết những câu hỏi khác nhau:

- MVC phân chia trách nhiệm tiếp nhận tương tác, xử lý dữ liệu và tạo phản hồi.
- API định nghĩa hợp đồng giao tiếp mà một client có thể gọi, gồm endpoint, method, request, response, status và quy tắc tương thích.

Một API web có thể được triển khai bằng MVC. Controller ánh xạ endpoint, nhận request DTO, gọi application service rồi trả response DTO. Trong trường hợp đó, JSON là representation của API.

Một ứng dụng cũng có thể cung cấp cả giao diện HTML và API JSON trên cùng miền nghiệp vụ:

    Browser
       |
       | GET /courses/42
       v
    CoursePageController
       |
       | gọi query/application service
       v
    CourseQueryService
       |
       v
    CourseDetails
       |
       v
    View Model ------> Thymeleaf View ------> HTML

    Mobile App
       |
       | GET /api/courses/42
       v
    CourseApiController
       |
       | gọi cùng query/application service
       v
    CourseQueryService
       |
       v
    CourseDetails
       |
       v
    CourseResponse DTO ------> JSON response

Hai Controller có thể dùng chung ca truy vấn hoặc application service, nhưng mỗi bên tạo representation phù hợp. HTML có thể cần nhãn, văn bản định dạng và dữ liệu điều hướng; JSON API có thể cần mã định danh, timestamp chuẩn hóa và liên kết tài nguyên.

Không nên ép một DTO dùng cho mọi client nếu nhu cầu và vòng đời hợp đồng khác nhau. Chia sẻ logic nghiệp vụ và truy vấn khi phù hợp; thiết kế representation theo mục đích của client.

### API không đồng nghĩa với JSON

API là hợp đồng giao tiếp. JSON là một định dạng phổ biến để biểu diễn dữ liệu, nhưng không phải định nghĩa của API. API có thể trả HTML, XML, CSV, ảnh, tệp nhị phân hoặc các media type chuyên biệt. Điều cần thiết là client và server thống nhất cách trao đổi.

Tương tự, không phải mọi endpoint trả JSON đều tự động là RESTful. REST còn liên quan đến tài nguyên, method, representation, trạng thái giao tiếp và các ràng buộc kiến trúc khác. Trong thực tế, nhiều hệ thống được gọi là REST API nhưng chỉ áp dụng một phần các nguyên tắc REST; hãy mô tả chính xác hợp đồng thay vì dựa vào nhãn gọi.

## 3. Chọn HTML hay JSON cho request

Một ứng dụng có thể thiết kế route riêng cho HTML và API:

- GET /courses/42 trả trang HTML.
- GET /api/courses/42 trả JSON.

Cách này dễ hiểu và thường phù hợp khi browser page và API có mục đích, quyền truy cập hoặc chu kỳ phát hành khác nhau.

Một endpoint cũng có thể hỗ trợ nhiều representation dựa trên HTTP content negotiation. Client gửi header Accept để cho biết các media type có thể nhận. Server chọn một representation được hỗ trợ hoặc từ chối nếu không có lựa chọn phù hợp.

Ví dụ:

    GET /courses/42
    Accept: text/html

Server có thể trả:

    HTTP/1.1 200 OK
    Content-Type: text/html; charset=UTF-8

Nếu client gửi:

    GET /courses/42
    Accept: application/json

Server có thể trả:

    HTTP/1.1 200 OK
    Content-Type: application/json

### Accept và Content-Type khác nhau

| Header | Hướng truyền | Ý nghĩa |
|---|---|---|
| Accept | Client gửi lên | Client muốn nhận representation thuộc media type nào |
| Content-Type | Gửi cùng body request hoặc response | Body hiện tại được mã hóa theo media type nào |

Ví dụ, khi client gửi JSON trong request body:

    POST /api/registrations
    Content-Type: application/json
    Accept: application/json

Content-Type mô tả body đăng ký mà client gửi. Accept mô tả kiểu response client muốn nhận.

Nếu server không hỗ trợ media type mà client yêu cầu qua Accept, response thường là 406 Not Acceptable. Nếu server không hỗ trợ định dạng body mà client gửi, server có thể trả 415 Unsupported Media Type.

### Khi nào nên dùng route riêng?

Route riêng thường dễ quản lý hơn khi:

- HTML và API có mô hình xác thực khác nhau.
- Hai nhóm client có hợp đồng và chu kỳ phát hành khác nhau.
- API cần versioning hoặc giới hạn truy cập riêng.
- Một representation cần dữ liệu hoàn toàn khác.
- Đội phát triển muốn tài liệu hóa và giám sát API độc lập.

Content negotiation hữu ích khi nhiều representation thực sự là các dạng thay thế của cùng một tài nguyên và có thể chia sẻ cùng semantics. Không cần thêm độ phức tạp nếu chỉ có một kiểu phản hồi.

## 4. Content negotiation trong Spring MVC

Spring MVC hỗ trợ ánh xạ endpoint theo media type thông qua thuộc tính produces và consumes.

Ví dụ một API chỉ trả JSON:

    @RestController
    @RequestMapping("/api/courses")
    public class CourseApiController {
        private final CourseQueryService courses;

        public CourseApiController(CourseQueryService courses) {
            this.courses = courses;
        }

        @GetMapping(
                value = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public CourseResponse detail(@PathVariable UUID id) {
            CourseDetails details = courses.getDetails(id);
            return CourseResponse.from(details);
        }
    }

@RestController kết hợp @Controller và @ResponseBody. Kết quả trả về được ghi vào HTTP response body qua cơ chế HttpMessageConverter; với JSON, converter thường dùng Jackson nếu dự án đã cấu hình thư viện tương ứng.

Ví dụ một controller HTML:

    @Controller
    @RequestMapping("/courses")
    public class CoursePageController {
        private final CourseQueryService courses;

        public CoursePageController(CourseQueryService courses) {
            this.courses = courses;
        }

        @GetMapping("/{id}")
        public String detail(@PathVariable UUID id, Model model) {
            CourseDetails details = courses.getDetails(id);
            model.addAttribute("page", CourseDetailsPage.from(details));
            return "courses/detail";
        }
    }

Ở đây, chuỗi courses/detail là tên View template. Nó không phải response body JSON.

### Một endpoint hỗ trợ nhiều media type

Nếu thực sự cần cùng route trả HTML hoặc JSON, có thể khai báo các handler theo produces:

    @GetMapping(value = "/{id}", produces = MediaType.TEXT_HTML_VALUE)
    public String htmlDetail(@PathVariable UUID id, Model model) {
        CourseDetails details = courses.getDetails(id);
        model.addAttribute("page", CourseDetailsPage.from(details));
        return "courses/detail";
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public CourseResponse jsonDetail(@PathVariable UUID id) {
        return CourseResponse.from(courses.getDetails(id));
    }

Spring chọn handler phù hợp với request mapping và media type. Cần kiểm tra cấu hình content negotiation và các mapping khác trong ứng dụng để tránh route trùng hoặc kết quả chọn handler khó dự đoán.

Không nên dùng tham số query tùy tiện như format=html hay format=json nếu ứng dụng đã có quy ước HTTP rõ ràng. Nếu phải hỗ trợ một cơ chế format riêng vì tương thích cũ, hãy ghi rõ trong hợp đồng.

## 5. Thiết kế response DTO thay vì trả entity

Response DTO là hợp đồng dữ liệu mà API công khai. DTO nên thể hiện thông tin client cần và tránh rò rỉ chi tiết nội bộ.

Giả sử domain model có:

- Mã khóa học.
- Tên và mô tả.
- Trạng thái mở đăng ký.
- Sức chứa tối đa.
- Danh sách học viên đã đăng ký.
- Thông tin giảng viên và quan hệ đến các thực thể khác.

API công khai có thể chỉ cần một phần:

    public record CourseResponse(
            UUID id,
            String code,
            String title,
            String description,
            boolean registrationOpen,
            int availableSeats) {

        public static CourseResponse from(CourseDetails details) {
            return new CourseResponse(
                    details.id(),
                    details.code(),
                    details.title(),
                    details.description(),
                    details.registrationOpen(),
                    details.availableSeats());
        }
    }

Controller gọi query service và chuyển kết quả sang DTO. Client không cần biết entity lưu danh sách đăng ký bằng collection nào, dùng ORM nào hoặc có quan hệ nội bộ ra sao.

### Vì sao không nên serialize entity trực tiếp?

Serialize entity có thể dẫn đến:

- Lộ trường nội bộ như ghi chú quản trị, email riêng hoặc cờ vận hành.
- Vòng lặp tham chiếu khi hai entity trỏ tới nhau.
- Truy vấn bổ sung ngoài dự kiến khi serializer truy cập quan hệ lazy.
- Phụ thuộc API vào tên cột hoặc cấu trúc entity.
- Client bị ảnh hưởng khi schema lưu trữ thay đổi.
- Khó kiểm soát chính xác trường nào được phép xuất hiện.

DTO tạo một điểm kiểm soát rõ ràng. Mỗi endpoint chỉ trả dữ liệu cần thiết cho mục đích của nó.

### DTO không phải nơi chứa nghiệp vụ

DTO có thể chứa thao tác chuyển đổi hoặc định dạng đơn giản, nhưng không nên trở thành nơi áp dụng quy tắc như tính quyền đăng ký, quyết định giá hoặc chuyển trạng thái đơn hàng. Các quyết định đó thuộc domain/application layer.

Có thể tách:

- Domain model: quy tắc và trạng thái nghiệp vụ.
- Query result: dữ liệu lấy ra từ các nguồn cần thiết.
- Response DTO: hợp đồng JSON công khai.
- View model: dữ liệu tối ưu cho một màn hình HTML.

Không nhất thiết phải có đủ bốn lớp trong mọi endpoint. Tạo lớp khi nó giúp phân định trách nhiệm và ổn định hợp đồng.

## 6. JSON representation: kiểu dữ liệu, null và thời gian

JSON có một số kiểu cơ bản: object, array, string, number, boolean và null. Khi thiết kế API, cần quy định rõ ý nghĩa của từng trường.

Ví dụ:

    {
      "id": "2f3a5e2b-2b4d-4c1f-8b0a-5c92f2c43d11",
      "code": "JAVA-101",
      "title": "Lập trình Java cơ bản",
      "registrationOpen": true,
      "availableSeats": 12,
      "startsAt": "2026-12-01T09:00:00Z"
    }

Đây là ví dụ minh họa cấu trúc, không phải dữ liệu từ một hệ thống thật.

### Quy ước null và trường bị thiếu

Trường có giá trị null và trường không xuất hiện có thể mang ý nghĩa khác nhau:

- null: thuộc tính được biết nhưng hiện không có giá trị.
- Không xuất hiện: thuộc tính không được cung cấp, không áp dụng hoặc bị lược khỏi representation theo quy ước.

Với API cập nhật một phần, sự khác biệt này có thể quan trọng: trường bị thiếu có thể có nghĩa “giữ nguyên”, trong khi null có thể có nghĩa “xóa giá trị”. Hãy định nghĩa semantics rõ ràng và kiểm thử chúng.

### Ngày giờ

Dùng format có quy ước rõ ràng, thường là ISO 8601/RFC 3339 cho timestamp. Phân biệt thời điểm tuyệt đối với ngày lịch:

- Timestamp như 2026-12-01T09:00:00Z biểu diễn một thời điểm có múi giờ/offset.
- Ngày như 2026-12-01 biểu diễn ngày lịch, không tự mang múi giờ.
- Giờ địa phương của lớp học có thể cần timezone như Asia/Ho_Chi_Minh để chuyển đổi đúng.

Không nên trả ngày giờ dưới dạng chuỗi tùy biến như 01/12/26 9h trong API nếu client cần xử lý bằng máy. Format thân thiện với người dùng phù hợp hơn ở View HTML.

### Tiền và số thập phân

Không dùng kiểu floating point để biểu diễn tiền trong nghiệp vụ nếu cần độ chính xác thập phân. API có thể biểu diễn số tiền bằng decimal JSON hoặc chuỗi decimal theo hợp đồng, kèm đơn vị tiền tệ:

    {
      "amount": "125000.00",
      "currency": "VND"
    }

Dùng chuỗi giúp tránh việc client dùng kiểu số nhị phân làm tròn ngoài ý muốn, nhưng client cần parse theo quy ước đã công bố. Điều quan trọng là định nghĩa độ chính xác, scale và currency.

### Enum và giá trị trạng thái

Nếu trả enum thành chuỗi như PENDING, CONFIRMED, hãy xem tên đó là một phần của hợp đồng. Đổi tên enum nội bộ không nên vô tình làm hỏng client. Có thể dùng mapper để ánh xạ trạng thái domain sang giá trị API ổn định.

## 7. Status code và header là một phần của representation

Response không chỉ có body. Status code và header cung cấp ngữ cảnh để client hiểu kết quả và xử lý tiếp.

### Các status thường gặp

| Tình huống | Status thường dùng | Ý nghĩa |
|---|---|---|
| Đọc tài nguyên thành công | 200 OK | Có representation trả về |
| Tạo tài nguyên thành công | 201 Created | Tài nguyên mới đã được tạo |
| Tiếp nhận tác vụ bất đồng bộ | 202 Accepted | Đã nhận yêu cầu, xử lý chưa hoàn tất |
| Cập nhật thành công không cần body | 204 No Content | Không có representation trong response |
| Request sai cấu trúc hoặc dữ liệu | 400 Bad Request | Client cần sửa request |
| Thiếu hoặc sai xác thực | 401 Unauthorized | Cần xác thực hợp lệ |
| Không đủ quyền | 403 Forbidden | Client không được phép thực hiện |
| Không tìm thấy tài nguyên | 404 Not Found | Tài nguyên không có hoặc không được tiết lộ |
| Xung đột trạng thái | 409 Conflict | Request mâu thuẫn với trạng thái hiện tại |
| Media type request không hỗ trợ | 415 Unsupported Media Type | Server không nhận định dạng body đó |
| Media type response không đáp ứng Accept | 406 Not Acceptable | Server không có representation phù hợp |

Chọn status theo ngữ nghĩa và giữ nhất quán giữa các endpoint. Đừng trả 200 cho mọi tình huống chỉ để client dễ xử lý; status sai khiến cache, công cụ giám sát và client hiểu sai kết quả.

### Location khi tạo tài nguyên

Khi tạo tài nguyên, response 201 Created thường kèm header Location chỉ đến URI của tài nguyên mới:

    @PostMapping
    public ResponseEntity<CourseResponse> create(
            @Valid @RequestBody CreateCourseRequest request) {

        CourseDetails created = createCourse.execute(request.toCommand());
        CourseResponse body = CourseResponse.from(created);

        URI location = URI.create("/api/courses/" + created.id());

        return ResponseEntity.created(location).body(body);
    }

Client có thể dùng URI đó để đọc hoặc thao tác tiếp với tài nguyên vừa tạo. Trong ứng dụng thật, nên tạo URI theo cấu hình deployment và routing phù hợp thay vì giả định host hoặc context path cố định.

### Header Content-Type

Server nên khai báo media type chính xác cho response body. Khi trả JSON, framework thường đặt Content-Type: application/json. Khi trả HTML, template rendering đặt Content-Type: text/html; charset=UTF-8.

Không nên trả JSON với Content-Type: text/plain hoặc trả nội dung HTML dưới media type JSON.

## 8. Biểu diễn lỗi cho API

Lỗi cũng là một representation và cần có hợp đồng ổn định. Client cần biết lỗi thuộc nhóm nào, có thể sửa request hay cần thực hiện hành động khác, và có mã tham chiếu nào để hỗ trợ tra cứu.

Một cấu trúc lỗi tùy chỉnh có thể là:

    public record ApiError(
            String code,
            String message,
            Map<String, String> fieldErrors,
            String traceId) {
    }

Ví dụ:

    {
      "code": "VALIDATION_FAILED",
      "message": "Dữ liệu gửi lên chưa hợp lệ",
      "fieldErrors": {
        "courseId": "Mã khóa học không được để trống"
      },
      "traceId": "req-8f21"
    }

Không trả stack trace, câu SQL, đường dẫn nội bộ hoặc nội dung exception thô cho client.

### Problem Details

HTTP có định dạng Problem Details được chuẩn hóa trong RFC 9457, với media type application/problem+json. Nó cung cấp các trường phổ biến như type, title, status, detail và instance; ứng dụng có thể bổ sung extension member khi cần.

Ví dụ:

    {
      "type": "https://api.example.test/problems/registration-conflict",
      "title": "Registration conflict",
      "status": 409,
      "detail": "Người học đã đăng ký khóa học này.",
      "instance": "/api/registrations"
    }

Spring Framework 6 cung cấp ProblemDetail để xây dựng response theo định dạng này. Ví dụ:

    @ExceptionHandler(RegistrationConflictException.class)
    ResponseEntity<ProblemDetail> handleConflict(
            RegistrationConflictException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Người học đã đăng ký khóa học này.");

        problem.setTitle("Registration conflict");
        problem.setType(URI.create(
                "https://api.example.test/problems/registration-conflict"));

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

type nên là URI định danh loại vấn đề, không nhất thiết phải là endpoint trả tài liệu, nhưng nên ổn định và có tài liệu giải thích. Nếu dự án dùng Spring phiên bản cũ hơn, có thể cần DTO và exception handler riêng.

### Lỗi form HTML và lỗi API khác nhau

Form HTML thường cần trả lại template cùng lỗi cạnh trường nhập liệu để người dùng sửa ngay. API JSON thường trả status và error representation để client tự trình bày. Cả hai có thể xuất phát từ cùng một lỗi nghiệp vụ, nhưng representation cần phù hợp với client.

Không nên trả nguyên trang HTML lỗi cho một client API đang mong đợi JSON, trừ khi hợp đồng endpoint quy định như vậy.

## 9. Liên kết tài nguyên và quan hệ với API

Một API không chỉ trả thuộc tính dữ liệu. Trong nhiều thiết kế, response còn có thể chứa liên kết giúp client tìm các tài nguyên hoặc hành động liên quan.

Ví dụ, response khóa học có thể chứa:

    {
      "id": "course-42",
      "title": "Lập trình Java cơ bản",
      "links": {
        "self": "/api/courses/course-42",
        "registrations": "/api/courses/course-42/registrations"
      }
    }

Các liên kết cho client biết URI để truy cập tài nguyên liên quan. Cách tiếp cận hypermedia (HATEOAS) đi xa hơn bằng cách biểu diễn các hành động hoặc quan hệ có thể thực hiện trong response. Đây là một ràng buộc của REST theo nghĩa chặt; không phải mọi API JSON đều phải triển khai đầy đủ HATEOAS.

### Header Link

HTTP cũng có header Link để cung cấp quan hệ liên kết. Ví dụ, một endpoint danh sách có thể trả liên kết đến trang kế tiếp hoặc trang trước. Nếu dùng header, cần tuân theo cú pháp và quan hệ đã quy định, tránh tự đặt một format không tương thích.

### Không nhầm link với quyền truy cập

Việc response có chứa link không có nghĩa client chắc chắn được phép gọi endpoint đó. Server vẫn phải kiểm tra xác thực và phân quyền trên từng request. Link giúp khám phá tài nguyên hoặc hành động; nó không phải cơ chế bảo mật.

### API có thể dùng URI ổn định

URI là một phần của hợp đồng. Hãy tránh để client phụ thuộc vào đường dẫn file nội bộ, tên bảng hoặc vị trí triển khai. Khi đổi cấu trúc bên trong, có thể giữ URI công khai hoặc cung cấp chiến lược chuyển phiên bản phù hợp.

## 10. Phân trang, lọc và sắp xếp

Danh sách lớn không nên được trả toàn bộ trong một response. API thường cung cấp phân trang để giới hạn lượng dữ liệu và giúp client điều hướng kết quả.

Ví dụ:

    GET /api/courses?page=0&size=20&sort=title,asc

Response có thể gồm:

    {
      "items": [
        {
          "id": "course-42",
          "title": "Lập trình Java cơ bản"
        }
      ],
      "page": 0,
      "size": 20,
      "totalElements": 135,
      "totalPages": 7
    }

Cấu trúc cụ thể phụ thuộc hợp đồng. Một API khác có thể dùng cursor-based pagination với nextCursor thay vì số trang.

### Offset pagination

Dạng page và size dễ hiểu và phù hợp với danh sách có thể truy cập theo trang. Tuy nhiên, nếu dữ liệu thay đổi thường xuyên, các bản ghi có thể dịch chuyển giữa các trang dẫn đến trùng hoặc bỏ sót khi người dùng đang duyệt.

### Cursor pagination

Cursor dựa trên một khóa sắp xếp ổn định, thường hữu ích với danh sách lớn hoặc dữ liệu liên tục phát sinh. Client gửi cursor nhận được ở response trước để lấy phần tiếp theo. Cursor nên được tạo và kiểm tra ở server; không để client tùy ý thay đổi điều kiện truy vấn nội bộ.

### Lọc và sắp xếp

Query parameter nên có tên và semantics rõ ràng, ví dụ status=OPEN, q=java, sort=startsAt,asc. Server cần giới hạn các trường được phép sort/filter, kiểm tra kiểu dữ liệu và áp dụng quyền truy cập trước khi trả kết quả.

Phân trang là một phần của API representation: metadata và link điều hướng giúp client hiểu tập kết quả. Không nên để View hoặc client tự tải toàn bộ dữ liệu chỉ để chia trang tại chỗ.

## 11. Cache HTTP và tính nhất quán của representation

Cache giúp giảm tải server và tăng tốc độ phản hồi, nhưng chỉ hiệu quả khi response có chính sách phù hợp.

### Cache-Control

Header Cache-Control mô tả cách response được cache. Ví dụ:

- public, max-age=60: response có thể được cache công khai trong 60 giây nếu nội dung phù hợp.
- private, max-age=60: chỉ cache riêng phía client.
- no-store: không lưu response vào cache.

Không dùng chính sách cache công khai cho dữ liệu cá nhân hoặc dữ liệu phụ thuộc quyền của người dùng. Cần xem xét cookie, authorization và các intermediary cache khi thiết kế.

### ETag và If-None-Match

ETag là validator đại diện cho một phiên bản của representation. Client có thể gửi If-None-Match ở request sau. Nếu representation chưa thay đổi, server có thể trả 304 Not Modified mà không cần gửi lại body.

Ví dụ về luồng:

    Client                         Server
      |                               |
      | GET /api/courses/42           |
      |------------------------------>|
      | 200 OK                        |
      | ETag: "course-v7"             |
      | JSON body                     |
      |<------------------------------|
      |                               |
      | GET /api/courses/42           |
      | If-None-Match: "course-v7"    |
      |------------------------------>|
      | 304 Not Modified              |
      |<------------------------------|

ETag phải được tính theo representation hoặc phiên bản dữ liệu mà server muốn xác nhận. Nếu cùng tài nguyên có nhiều representation, cần bảo đảm validator và cache key phản ánh đúng sự khác nhau; header Vary: Accept có thể cần thiết khi nội dung phụ thuộc Accept.

### Cache không thay thế phân quyền

Ngay cả khi response đã có ETag hoặc được cache, server vẫn cần thiết kế đúng quyền truy cập và chính sách cache. Một response cá nhân không được chia sẻ nhầm giữa các người dùng. Không dùng 304 để né kiểm tra quyền trên tài nguyên.

## 12. Bảo mật khi tạo representation

Mỗi response cần tuân theo nguyên tắc chỉ công khai dữ liệu mà client được phép biết.

Một số điểm cần kiểm tra:

- Chỉ đưa trường cần thiết vào DTO.
- Áp dụng phân quyền trước khi tải hoặc trả dữ liệu của tài nguyên.
- Không để client gửi trường nội bộ qua request DTO.
- Escape nội dung khi render HTML.
- Serialize JSON bằng thư viện/framework phù hợp, tránh tự nối chuỗi JSON.
- Không trả mật khẩu, access token, secret, thông tin thanh toán nhạy cảm hoặc dữ liệu riêng tư không cần thiết.
- Không tiết lộ stack trace, câu SQL và thông tin cấu hình trong error response.
- Đánh giá chính sách CORS nếu API được gọi từ origin khác; CORS không thay thế xác thực và phân quyền.
- Dùng HTTPS trong môi trường triển khai để bảo vệ dữ liệu trên đường truyền.

Đối với HTML, output encoding phải phù hợp ngữ cảnh như text, attribute, URL hoặc JavaScript. Đối với JSON, serializer giúp tạo cú pháp hợp lệ nhưng không thay thế việc lọc dữ liệu nhạy cảm và kiểm soát quyền.

## 13. Kiểm thử representation và hợp đồng API

Kiểm thử API cần xác nhận không chỉ ca sử dụng chạy đúng mà cả representation được trả đúng theo hợp đồng.

| Trường hợp | Điều cần xác nhận |
|---|---|
| GET endpoint JSON | Status 200, Content-Type đúng và body có các trường công khai |
| GET endpoint HTML | Controller chọn đúng View và model có dữ liệu cần thiết |
| Request có Accept không hỗ trợ | Server trả 406 theo cấu hình |
| Request body có Content-Type không hỗ trợ | Server trả 415 theo cấu hình |
| Tạo tài nguyên | Status 201 và Location trỏ đến tài nguyên mới |
| Không tìm thấy tài nguyên | Status 404 và error representation nhất quán |
| Vi phạm nghiệp vụ | Status và mã lỗi đúng với hợp đồng |
| Dữ liệu riêng tư | Response không chứa trường không được phép |
| Danh sách nhiều trang | Metadata, sort và link/cursor nhất quán |
| Cache validator khớp | Server trả 304 khi representation chưa đổi |

Với Spring MVC, có thể dùng MockMvc để kiểm tra header và JSON:

    mockMvc.perform(get("/api/courses/{id}", courseId)
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(courseId.toString()))
        .andExpect(jsonPath("$.title").exists());

Có thể kiểm thử HTML riêng bằng cách xác nhận tên View và model attribute:

    mockMvc.perform(get("/courses/{id}", courseId)
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().isOk())
        .andExpect(view().name("courses/detail"))
        .andExpect(model().attributeExists("page"));

Các test này xác nhận hợp đồng ở ranh giới HTTP. Quy tắc nghiệp vụ như khóa học có được mở đăng ký hay không vẫn cần unit test hoặc application test riêng.

### Contract test và tương thích client

Khi API được nhiều client sử dụng, có thể bổ sung contract test để kiểm tra cấu trúc response, kiểu trường và status theo hợp đồng đã công bố. Khi đổi tên trường, bỏ trường hoặc thay đổi semantics, cần đánh giá ảnh hưởng đến client hiện tại.

Không nên xem việc test controller pass là bằng chứng mọi client sẽ tương thích. API cần tài liệu hóa và có chính sách thay đổi rõ ràng.

## 14. Quản lý phiên bản và tiến hóa API

Khi hợp đồng đã được client sử dụng, thay đổi response có thể ảnh hưởng đến các ứng dụng đang chạy ở phiên bản cũ.

Một số thay đổi thường tương đối an toàn nếu được định nghĩa đúng:

- Thêm trường tùy chọn mà client cũ bỏ qua.
- Bổ sung một endpoint mới.
- Thêm một loại liên kết mà client không bắt buộc phải sử dụng.

Một số thay đổi có nguy cơ phá vỡ tương thích:

- Xóa hoặc đổi tên trường.
- Đổi kiểu dữ liệu.
- Thay đổi ý nghĩa của null hoặc giá trị mặc định.
- Đổi format timestamp.
- Thay đổi status code hoặc error code mà client dựa vào.
- Đổi URI hoặc semantics của endpoint.

Nếu cần thay đổi lớn, có thể dùng version trong path như /api/v2/courses hoặc một cơ chế versioning đã được thống nhất. Không có một chiến lược versioning phù hợp cho mọi hệ thống; hãy chọn cách client có thể phát hiện và chuyển đổi có kế hoạch.

Hạn chế versioning không cần thiết. Trước khi tạo phiên bản mới, hãy xem có thể mở rộng hợp đồng theo cách tương thích hay không. Dù chọn chiến lược nào, hãy ghi rõ thời hạn hỗ trợ và cách chuyển client.

## 15. Quy trình thiết kế response cho một endpoint

Khi xây dựng endpoint mới, có thể thực hiện theo trình tự:

1. Xác định client và mục đích của request: browser page, frontend, mobile app hay tích hợp hệ thống.
2. Chọn representation cần trả: HTML, JSON hoặc media type khác.
3. Định nghĩa request contract và response contract độc lập với entity lưu trữ.
4. Xác định application service/query service cung cấp dữ liệu và thực thi quy tắc.
5. Chọn status code, Content-Type, Location và các header cần thiết.
6. Thiết kế error representation cho các trường hợp thường gặp.
7. Xác định phân trang, lọc, sắp xếp và cache nếu endpoint trả tập dữ liệu.
8. Kiểm tra dữ liệu nhạy cảm, quyền truy cập và output encoding.
9. Viết test cho status, headers, body, media type và các trường hợp lỗi.
10. Tài liệu hóa hợp đồng và đánh giá ảnh hưởng khi thay đổi.

## Kết luận

Trong MVC trên web, Controller chuyển kết quả xử lý thành representation mà client có thể hiểu. Với giao diện server-side, View tạo HTML; với API, response DTO được serialize thành JSON hoặc định dạng đã thỏa thuận. Cả hai có thể dùng chung application service và domain model, nhưng representation cần phù hợp với mục đích và hợp đồng của từng client.

Một API rõ ràng định nghĩa request, response, media type, status, header, lỗi, liên kết và chính sách tiến hóa. Dùng DTO để kiểm soát dữ liệu công khai, content negotiation khi thực sự cần nhiều representation, và kiểm thử hợp đồng HTTP giúp ứng dụng giữ được ranh giới ổn định khi giao diện, client và phần bên trong thay đổi.
