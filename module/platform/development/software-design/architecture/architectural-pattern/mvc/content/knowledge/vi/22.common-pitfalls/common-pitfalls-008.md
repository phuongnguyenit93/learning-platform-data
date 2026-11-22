# Lặp lại logic kiểm tra và ánh xạ ở nhiều Controller

## Mục tiêu

Trong ứng dụng MVC, Controller là ranh giới tiếp nhận HTTP request và chuyển dữ liệu đầu vào thành lời gọi use case. Khi nhiều Controller tự viết lại cùng một nhóm thao tác như kiểm tra dữ liệu, xác minh quyền, tìm tài nguyên, chuyển DTO, bắt exception hoặc tạo response, mã nguồn nhanh chóng trở nên khó bảo trì. Một thay đổi nhỏ có thể phải sửa nhiều nơi; nếu bỏ sót một Controller, các endpoint sẽ xử lý cùng tình huống theo cách khác nhau.

Tuy nhiên, không phải mọi đoạn code giống nhau đều cần gom vào một hàm dùng chung. Hai use case có thể trông giống nhau nhưng mang quy tắc nghiệp vụ khác nhau. Tái sử dụng sai chỗ có thể tạo ra một lớp trừu tượng khó hiểu, che giấu chính sách hoặc buộc các Controller phụ thuộc vào một helper quá tổng quát.

Bài học này phân tích nguyên nhân và hậu quả của logic lặp trong Controller, cách nhận diện phần thực sự dùng chung, và cách phân chia trách nhiệm giữa Controller, application service, policy, validator, mapper và exception handler. Ví dụ sử dụng Java và Spring MVC.

Sau khi học, người học có thể:

- Nhận diện logic kiểm tra và ánh xạ bị lặp giữa nhiều Controller.
- Phân biệt duplication có thể tái sử dụng với quy tắc riêng của từng use case.
- Chuyển orchestration và nghiệp vụ ra khỏi Controller đúng tầng.
- Dùng application service, access policy, validator và mapper có ranh giới rõ.
- Tập trung xử lý exception và response lỗi mà vẫn giữ ngữ cảnh phù hợp.
- Tránh BaseController, utility class hoặc abstraction tổng quát quá mức.
- Refactor từng bước mà không thay đổi hợp đồng HTTP ngoài ý muốn.
- Viết test để bảo đảm hành vi giữa các endpoint nhất quán.

## 1. Logic lặp trong Controller là gì?

Logic lặp xuất hiện khi nhiều Controller hoặc nhiều method Controller tự triển khai lại cùng một trách nhiệm. Ví dụ, mỗi endpoint đều:

- Kiểm tra request có đủ trường bắt buộc hay không.
- Tìm user hiện tại từ SecurityContext.
- Tải một tài nguyên theo ID rồi kiểm tra owner.
- Chuyển request DTO thành command.
- Chuyển domain object thành response DTO.
- Bắt cùng loại exception và tạo cùng một thông báo.
- Tạo pagination metadata theo cùng quy ước.
- Ghi log hoặc gắn request ID theo cùng cách.

Ví dụ hai Controller cùng tìm một đơn hàng và kiểm tra quyền sở hữu:

    @GetMapping("/orders/{id}")
    public OrderResponse detail(
            @PathVariable UUID id,
            Principal principal) {

        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Order not found"));

        if (!order.getOwnerUsername().equals(principal.getName())) {
            throw new AccessDeniedException("Not allowed");
        }

        return OrderResponse.from(order);
    }

    @GetMapping("/invoices/{id}/order")
    public OrderResponse orderForInvoice(
            @PathVariable UUID id,
            Principal principal) {

        Order order = orderRepository.findByInvoiceId(id)
                .orElseThrow(() -> new NotFoundException("Order not found"));

        if (!order.getOwnerUsername().equals(principal.getName())) {
            throw new AccessDeniedException("Not allowed");
        }

        return OrderResponse.from(order);
    }

Hai method có cùng một chuỗi thao tác: tìm order, kiểm tra owner và chuyển response. Khi chính sách truy cập thay đổi, cả hai nơi phải được cập nhật. Nếu một nơi quên kiểm tra, ứng dụng có thể tạo lỗ hổng phân quyền.

### Dấu hiệu thường gặp

- Nhiều Controller có các khối if/else gần như giống nhau.
- Cùng một exception được bắt và ánh xạ thành các response khác nhau.
- Một DTO được tạo thủ công theo cùng cách ở nhiều endpoint.
- Các Controller truy cập repository trực tiếp để thực hiện cùng quy trình.
- Khi sửa một quy tắc, nhóm phát triển phải tìm kiếm và sửa nhiều file.
- Test phải lặp cùng một bộ setup cho nhiều endpoint.
- Các endpoint có cùng ý nghĩa nhưng trả status, error code hoặc format khác nhau.

Không nên chỉ dựa vào số dòng code giống nhau. Cần xem mục đích, dữ liệu đầu vào, điều kiện và kết quả của từng đoạn.

## 2. Vì sao logic lặp xuất hiện?

### Controller dần trở thành nơi chứa nghiệp vụ

Khi Controller vừa đọc request, vừa tìm dữ liệu, vừa kiểm tra quyền, vừa thực hiện quy tắc domain, vừa ghi database và tạo response, các method dễ sao chép lẫn nhau. Controller mới thường được tạo bằng cách copy một Controller cũ rồi đổi path hoặc tên DTO.

### Chưa có ranh giới use case rõ ràng

Nếu ứng dụng không có application service hoặc use case cụ thể, Controller phải tự điều phối các bước. Các bước này được lặp lại ở mọi endpoint cần cùng hành vi.

### Hợp đồng dữ liệu không được chuẩn hóa

Mỗi Controller tự chuyển entity sang response DTO, tự đặt tên trường và tự quyết định cách biểu diễn lỗi. Kết quả là cùng một khái niệm có thể được biểu diễn khác nhau giữa các endpoint.

### Chính sách dùng chung bị đặt sai chỗ

Quy tắc truy cập tài nguyên có thể được copy vào Controller vì chưa có access policy. Logic xử lý exception có thể được viết lại vì chưa có ControllerAdvice. Quy tắc validation có thể bị nhân bản vì chưa xác định validation thuộc request boundary hay domain.

### Copy-and-paste là cách nhanh nhất trước mắt

Khi deadline gấp, sao chép một method có vẻ tiết kiệm thời gian. Chi phí xuất hiện về sau: sửa nhiều nơi, kiểm thử nhiều biến thể và khó xác định đâu là hành vi chuẩn.

## 3. Hậu quả của việc lặp logic

| Hậu quả | Biểu hiện | Rủi ro |
|---|---|---|
| Không nhất quán | Cùng lỗi nhưng endpoint trả status/message khác nhau | Client khó xử lý, trải nghiệm không đồng đều |
| Lỗi bảo mật | Một Controller thiếu kiểm tra owner hoặc tenant | IDOR/BOLA, truy cập trái phép |
| Chi phí thay đổi cao | Một chính sách phải sửa ở nhiều file | Bỏ sót nơi cần cập nhật |
| Test trùng lặp | Nhiều test kiểm tra cùng một quy tắc theo cách thủ công | Test dài và khó bảo trì |
| Khó đọc | Controller có nhiều đoạn plumbing | Khó nhìn ra use case chính |
| Khó quan sát | Logging và error mapping mỗi nơi một kiểu | Khó điều tra sự cố |
| Phụ thuộc chặt | Controller biết repository, entity và chi tiết hạ tầng | Thay đổi persistence ảnh hưởng nhiều endpoint |

Logic lặp đặc biệt nguy hiểm khi liên quan đến authorization, tenant isolation, validation nghiệp vụ và transaction. Một khác biệt nhỏ giữa hai bản sao có thể tạo ra lỗi khó phát hiện.

## 4. Không phải mọi đoạn code giống nhau đều là duplication cần loại bỏ

Hai đoạn code có thể giống cú pháp nhưng khác ý nghĩa. Ví dụ, kiểm tra “người tạo được hủy đơn hàng trong 15 phút” và “quản trị viên được hủy đơn hàng bất kỳ lúc nào” có thể đều chứa điều kiện thời gian hoặc role, nhưng đó là hai chính sách nghiệp vụ khác nhau.

Trước khi trích xuất, hãy hỏi:

1. Hai đoạn có cùng mục đích nghiệp vụ không?
2. Chúng có cùng điều kiện và cùng cách xử lý lỗi không?
3. Khi chính sách thay đổi, hai nơi có cần thay đổi cùng nhau không?
4. Dữ liệu đầu vào và kết quả có cùng hợp đồng không?
5. Thành phần dùng chung có tên gọi rõ ràng theo domain không?
6. Việc dùng chung có làm một use case phụ thuộc vào chi tiết không liên quan không?

### Ba trường hợp cần phân biệt

**Duplication thật:** Cùng một quy tắc được copy ở nhiều nơi, và mọi nơi phải tuân theo một chính sách duy nhất. Nên đặt quy tắc ở một nơi có thẩm quyền.

**Cấu trúc giống nhau nhưng ý nghĩa khác:** Hai use case tình cờ có cùng vài dòng code nhưng có thể thay đổi độc lập. Giữ riêng hoặc trích xuất phần kỹ thuật nhỏ nếu điều đó làm rõ trách nhiệm.

**Abstraction chưa đủ ổn định:** Hai đoạn hiện tại giống nhau nhưng chưa biết chúng có cùng lý do thay đổi hay không. Có thể chờ thêm một trường hợp thực tế trước khi tạo abstraction.

Mục tiêu là giảm số nơi phải duy trì cùng một quy tắc, không phải làm cho số dòng code giống nhau bằng không.

## 5. Phân chia trách nhiệm đúng trong MVC

Một luồng MVC có thể được tổ chức như sau:

    HTTP Request
         |
         v
    Filter / Security
         |
         v
    Controller
    - bind input
    - request validation
    - HTTP mapping
         |
         v
    Application Service / Use Case
    - điều phối nghiệp vụ
    - transaction boundary
         |
         +------> Access Policy
         |
         +------> Domain Model
         |
         +------> Repository / Gateway
         |
         v
    Application Result
         |
         v
    Response Mapper / View Model
         |
         v
    Controller / Response Handler
         |
         v
    HTTP Response / View

Mỗi thành phần có một trách nhiệm:

| Thành phần | Trách nhiệm chính |
|---|---|
| Filter / Spring Security | Xác thực và bảo vệ request ở ranh giới web |
| Controller | Binding, điều phối endpoint, chọn HTTP response hoặc View |
| Request DTO / Validator | Kiểm tra cấu trúc và ràng buộc đầu vào |
| Application Service | Điều phối một use case |
| Access Policy | Đánh giá quyền trên actor, resource và ngữ cảnh |
| Domain Model | Bảo vệ bất biến và hành vi nghiệp vụ |
| Repository / Gateway | Truy cập persistence hoặc hệ thống ngoài |
| Mapper / Assembler | Chuyển đổi giữa các representation |
| ControllerAdvice | Ánh xạ exception thành response lỗi phù hợp |

Không nhất thiết phải tạo một class riêng cho mọi dòng logic. Hãy chọn ranh giới theo trách nhiệm và lý do thay đổi.

## 6. Đưa quy trình nghiệp vụ ra khỏi Controller

Controller nên thể hiện rõ request đang yêu cầu use case nào. Nó không nên tự tải nhiều entity, kiểm tra nhiều điều kiện domain rồi phối hợp ghi dữ liệu.

### Trước khi refactor

    @PostMapping("/orders/{id}/cancel")
    public ResponseEntity<?> cancel(
            @PathVariable UUID id,
            Principal principal) {

        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Order not found"));

        if (!order.getOwnerUsername().equals(principal.getName())) {
            throw new AccessDeniedException("Not allowed");
        }

        if (!order.canBeCancelled()) {
            throw new ConflictException("Order cannot be cancelled");
        }

        order.cancel();
        orderRepository.save(order);

        return ResponseEntity.ok(OrderResponse.from(order));
    }

Nếu một endpoint khác cũng hủy đơn hàng, đoạn tải dữ liệu, kiểm tra quyền, kiểm tra trạng thái và lưu có thể bị lặp.

### Sau khi refactor

    @PostMapping("/orders/{id}/cancel")
    public ResponseEntity<OrderResponse> cancel(
            @PathVariable UUID id,
            @AuthenticationPrincipal AppPrincipal principal) {

        OrderResult result = cancelOrder.execute(
                new CancelOrderCommand(principal.userId(), id));

        return ResponseEntity.ok(orderMapper.toResponse(result));
    }

Use case điều phối quy trình:

    @Service
    public class CancelOrder {
        private final OrderRepository orders;
        private final OrderAccessPolicy accessPolicy;

        public CancelOrder(
                OrderRepository orders,
                OrderAccessPolicy accessPolicy) {
            this.orders = orders;
            this.accessPolicy = accessPolicy;
        }

        @Transactional
        public OrderResult execute(CancelOrderCommand command) {
            Order order = orders.findById(command.orderId())
                    .orElseThrow(OrderNotFoundException::new);

            accessPolicy.checkCanCancel(command.actorId(), order);
            order.cancel();

            return OrderResult.from(orders.save(order));
        }
    }

Hai endpoint có thể gọi cùng use case hoặc cùng policy nếu thực sự yêu cầu cùng một hành vi. Controller giữ phần HTTP; use case giữ luồng nghiệp vụ và transaction.

### Không biến Application Service thành một Controller khác

Application service không nên nhận HttpServletRequest, HttpSession, ResponseEntity hoặc Model. Nó nên nhận command/query có kiểu rõ và trả result hoặc phát sinh application/domain exception. Nhờ đó, use case có thể được gọi từ MVC, REST API, job hoặc message handler.

## 7. Tập trung validation đúng tầng

Validation thường bị lặp vì mỗi Controller tự kiểm tra cùng trường hoặc copy cùng điều kiện.

Cần phân biệt ba loại:

### Validation cấu trúc request

Kiểm tra dữ liệu đầu vào có đúng định dạng và ràng buộc cơ bản không:

- Trường bắt buộc.
- Độ dài chuỗi.
- Định dạng email.
- Giá trị số nằm trong phạm vi.
- Kiểu dữ liệu và cấu trúc request.

Có thể dùng Jakarta Bean Validation:

    public record CreateCourseRequest(
            @NotBlank
            @Size(max = 120)
            String title,

            @Min(1)
            @Max(100)
            int capacity) {
    }

    @PostMapping("/courses")
    public ResponseEntity<CourseResponse> create(
            @Valid @RequestBody CreateCourseRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(courseMapper.toResponse(
                        createCourse.execute(
                                new CreateCourseCommand(
                                        request.title(),
                                        request.capacity()))));
    }

Controller không cần viết lại điều kiện title rỗng hoặc capacity ngoài phạm vi ở mọi endpoint nếu cùng DTO hoặc validator được dùng.

### Validation liên trường hoặc theo ngữ cảnh request

Ví dụ ngày bắt đầu phải trước ngày kết thúc, hoặc ít nhất một trong hai trường phải có giá trị. Có thể dùng class-level constraint hoặc validator chuyên biệt nếu đó là quy tắc của hợp đồng request.

Nếu hai form có cấu trúc khác nhau, không nên ép chúng dùng một DTO chỉ để tái sử dụng annotation. Dùng DTO riêng và chia sẻ constraint hoặc validator thực sự chung.

### Quy tắc nghiệp vụ

Các điều kiện như “không thể hủy đơn đã giao”, “không thể đăng ký khi khóa học đã đủ chỗ” hoặc “chỉ chủ sở hữu được đổi thông tin thanh toán” thuộc use case/domain policy. Chúng phải được kiểm tra ở server trong application/domain layer, không chỉ ở form hoặc JavaScript.

Không dùng Bean Validation để thay thế invariant của domain. Một request hợp lệ về cấu trúc vẫn có thể vi phạm trạng thái nghiệp vụ hiện tại.

## 8. Tránh lặp kiểm tra quyền truy cập

Kiểm tra quyền thường bị copy vào từng Controller:

    if (!resource.getOwnerId().equals(currentUser.id())) {
        throw new AccessDeniedException("Forbidden");
    }

Nếu một resource được truy cập từ nhiều endpoint, có nguy cơ một endpoint quên kiểm tra. Có thể trích xuất access policy:

    @Component
    public class DocumentAccessPolicy {

        public void checkCanRead(AppPrincipal actor, Document document) {
            if (!document.getOwnerId().equals(actor.userId())
                    && !actor.hasAuthority("document:read:any")) {
                throw new AccessDeniedException("Access denied");
            }
        }

        public void checkCanEdit(AppPrincipal actor, Document document) {
            if (!document.getOwnerId().equals(actor.userId())
                    && !actor.hasAuthority("document:edit:any")) {
                throw new AccessDeniedException("Access denied");
            }
        }
    }

Policy thể hiện rõ actor, resource và action. Nó có thể được gọi từ application service để bảo đảm mọi adapter đều tuân theo cùng quy tắc.

### Chọn nơi kiểm tra quyền

- URL-level authorization phù hợp với quy tắc chung theo route hoặc nhóm endpoint.
- Method security phù hợp với quyền gọi một phương thức hoặc use case.
- Object-level policy cần resource cụ thể, owner, tenant và trạng thái.
- Domain invariant bảo vệ điều kiện nghiệp vụ ngay cả khi actor đã có quyền gọi use case.

Có thể dùng nhiều lớp, nhưng tránh lặp cùng một policy bằng các bản sao khác nhau. Kiểm tra ở Controller không đủ nếu use case còn được gọi từ job hoặc adapter khác.

### Tối ưu truy vấn theo quyền

Với một số use case, repository có thể tải dữ liệu theo cả ID và owner/tenant:

    Optional<Document> findByIdAndOwnerId(
            UUID documentId,
            UUID ownerId);

Cách này giảm khả năng tải nhầm tài nguyên. Tuy nhiên, semantics 403 hay 404 cần được quyết định theo chính sách bảo mật. Không dùng ID do client gửi làm bằng chứng ownership.

## 9. Tách ánh xạ DTO khỏi từng Controller

Controller thường lặp code chuyển entity hoặc application result sang response DTO. Ví dụ nhiều endpoint cùng gọi constructor response và chọn các trường tương tự.

### Ánh xạ thủ công có thể trở nên không nhất quán

    return new CourseResponse(
            course.getId(),
            course.getTitle(),
            course.getStatus().name(),
            course.getInstructor().getDisplayName());

Ở một Controller khác, người viết có thể quên trường instructor hoặc biểu diễn status theo cách khác.

### Dùng mapper có mục đích rõ

    @Component
    public class CourseMapper {

        public CourseResponse toResponse(CourseDetails course) {
            return new CourseResponse(
                    course.id(),
                    course.title(),
                    course.status().name(),
                    course.instructorName());
        }
    }

Controller dùng mapper:

    @GetMapping("/courses/{id}")
    public CourseResponse detail(@PathVariable UUID id) {
        return courseMapper.toResponse(
                courseQuery.getDetails(id));
    }

Mapper giúp tập trung quy tắc chuyển đổi representation. Có thể dùng MapStruct khi mapping lớn và ổn định; mapping thủ công vẫn phù hợp khi ít trường hoặc cần logic rõ ràng.

### Không ánh xạ trực tiếp toàn bộ entity ra API

Response DTO cần kiểm soát dữ liệu được công khai. Không trả entity persistence trực tiếp chỉ để tránh viết mapper. Entity có thể chứa password hash, internal flags, quan hệ lazy hoặc trường chưa được phép công khai.

### Request mapper và response mapper có mục đích khác nhau

- Request DTO → Command: chuyển input HTTP thành ý định use case.
- Domain/Application Result → Response DTO: chuyển kết quả nghiệp vụ thành representation.
- Domain/Application Result → View Model: tạo dữ liệu phù hợp cho template.

Không nên dùng một DTO duy nhất cho database entity, request body, response JSON và View. Các hợp đồng này thay đổi vì những lý do khác nhau.

## 10. Tập trung xử lý exception và error response

Nếu nhiều Controller cùng bắt exception và trả một cấu trúc lỗi giống nhau, có thể dùng ControllerAdvice hoặc RestControllerAdvice.

### Trước khi tập trung

    @GetMapping("/courses/{id}")
    public ResponseEntity<?> detail(@PathVariable UUID id) {
        try {
            return ResponseEntity.ok(courseService.get(id));
        } catch (CourseNotFoundException ex) {
            return ResponseEntity.status(404)
                    .body(Map.of("message", "Không tìm thấy khóa học"));
        }
    }

Một Controller khác có thể trả 400 cho cùng exception hoặc dùng key khác như errorMessage. Client phải xử lý nhiều format.

### Sau khi tập trung

    public record ApiError(
            String code,
            String message,
            String requestId) {
    }

    @RestControllerAdvice
    public class ApiExceptionHandler {

        @ExceptionHandler(CourseNotFoundException.class)
        ResponseEntity<ApiError> handleNotFound(
                CourseNotFoundException exception,
                HttpServletRequest request) {

            String requestId =
                    String.valueOf(request.getAttribute("requestId"));

            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiError(
                            "COURSE_NOT_FOUND",
                            "Không tìm thấy khóa học.",
                            requestId));
        }
    }

Các endpoint API nhận cùng error contract. HTML controller có thể dùng một ControllerAdvice khác hoặc handler phù hợp để render error View.

### Đừng tập trung mọi lỗi vào một message chung

ControllerAdvice nên ánh xạ exception đã được phân loại. Validation error có thể cần danh sách lỗi theo field; conflict có thể cần hướng dẫn tải lại dữ liệu; lỗi không dự kiến cần message chung và request ID.

Không trả stack trace, SQL hoặc exception message thô cho client. Diagnostic information được ghi log ở ranh giới phù hợp.

### Khi nào giữ xử lý cục bộ?

Nếu một endpoint có thể phục hồi theo cách riêng, chẳng hạn form cần render lại với dữ liệu người dùng đã nhập và lỗi cạnh từng trường, xử lý cục bộ có thể phù hợp. Tập trung xử lý các quy tắc chung; giữ hành vi đặc thù ở endpoint hoặc View khi cần.

## 11. Tái sử dụng logic mapping và validation qua component, không qua copy-paste

Một component dùng chung nên có tên thể hiện mục đích:

- CourseMapper.
- DocumentAccessPolicy.
- CreateCourseValidator.
- PageRequestNormalizer.
- ApiExceptionHandler.
- CurrentActorProvider nếu cần chuẩn hóa việc truy xuất principal.

Tên như CommonUtil, GeneralHelper hoặc BaseManager thường không cho biết thành phần chịu trách nhiệm gì.

### Component nên nhận đầu vào tường minh

Tốt:

    pageNormalizer.normalize(page, size)

Kém rõ ràng:

    commonUtil.prepareEverything(request, response, session)

Hàm đầu tiên thể hiện mục đích và dữ liệu cần xử lý. Hàm thứ hai che giấu nhiều phụ thuộc và có thể làm component trở thành nơi chứa logic không liên quan.

### Ưu tiên composition

Controller hoặc application service có thể nhận component qua constructor injection:

    @RestController
    public class CourseController {
        private final CourseQuery courseQuery;
        private final CourseMapper mapper;

        public CourseController(
                CourseQuery courseQuery,
                CourseMapper mapper) {
            this.courseQuery = courseQuery;
            this.mapper = mapper;
        }
    }

Composition giúp mỗi Controller chỉ phụ thuộc vào những khả năng nó cần. Không cần kế thừa một BaseController chỉ để dùng mapper hoặc helper.

## 12. Vì sao BaseController tổng quát thường là một bẫy?

Một cách phản ứng với duplication là tạo BaseController chứa nhiều helper:

    public abstract class BaseController {
        protected User currentUser() { ... }
        protected PageRequest pageRequest() { ... }
        protected <T> ResponseEntity<?> success(T value) { ... }
        protected void checkOwner(Object resource) { ... }
        protected ModelAndView renderError(Exception ex) { ... }
    }

Sau một thời gian, BaseController có thể chứa nhiều logic không liên quan. Controller con phụ thuộc vào method protected và trạng thái thừa kế mà người đọc không thấy ở constructor.

Vấn đề thường gặp:

- Tất cả Controller bị buộc vào một lớp cha.
- Helper thay đổi vì một use case nhưng ảnh hưởng nhiều lớp con.
- Tên method chung chung che giấu policy cụ thể.
- Khó test độc lập và khó thay thế từng hành vi.
- Có thể xuất hiện protected mutable state.
- Controller con có quyền truy cập nhiều khả năng không cần thiết.

### Khi nào base class có thể hợp lý?

Base class nhỏ có thể hữu ích khi framework hoặc ứng dụng có một lifecycle thật sự chung và quan hệ kế thừa có ý nghĩa. Tuy nhiên, đừng tạo base class chỉ vì hai Controller có vài dòng giống nhau.

Thông thường, một mapper, policy hoặc service được inject qua constructor dễ hiểu và dễ kiểm thử hơn.

## 13. Tránh utility class trở thành “ngăn kéo chung”

Một class CommonUtils chứa validation, date conversion, authorization, pagination, exception mapping và logging không có một trách nhiệm rõ ràng.

Khi mọi logic được chuyển vào một utility class:

- Controller có vẻ mỏng hơn nhưng độ phức tạp chỉ bị dời chỗ.
- Các hàm có thể phụ thuộc ngầm vào static context.
- Unit test khó thay thế dependency.
- Thay đổi một chức năng có thể ảnh hưởng các chức năng không liên quan.
- Tên hàm và tham số khó diễn đạt chính sách nghiệp vụ.

Hãy tách theo lý do thay đổi:

| Logic | Thành phần phù hợp |
|---|---|
| Parse và normalize page/size | Pagination argument resolver hoặc helper chuyên biệt |
| Kiểm tra format request | Bean Validation / request validator |
| Kiểm tra owner và quyền hành động | Access policy |
| Kiểm tra trạng thái domain | Domain model / domain service |
| Chuyển object sang DTO | Mapper/assembler |
| Ánh xạ exception thành HTTP error | ControllerAdvice |
| Điều phối nhiều bước use case | Application service |
| Xác thực request | Spring Security/filter chain |

Không cần tạo một class mới cho từng hàm nhỏ. Nhóm các hàm khi chúng cùng một khái niệm và có cùng lý do thay đổi.

## 14. Không lặp validation nhưng cũng không bỏ qua kiểm tra ở server

Một sai lầm khác là xóa validation ở Controller sau khi đã thêm kiểm tra ở frontend. Frontend validation chỉ hỗ trợ trải nghiệm; request có thể được gửi trực tiếp hoặc dữ liệu có thể bị sửa.

Phân chia hợp lý:

- Frontend: phản hồi nhanh cho người dùng.
- Controller/request boundary: kiểm tra cấu trúc và kiểu dữ liệu.
- Application/domain: kiểm tra quy tắc nghiệp vụ và trạng thái hiện tại.
- Database: constraint bảo vệ tính toàn vẹn cuối cùng.

Các lớp có thể kiểm tra cùng một thuộc tính vì chúng bảo vệ các ranh giới khác nhau. Ví dụ, UI kiểm tra trường bắt buộc để hướng dẫn; server kiểm tra lại để bảo đảm request hợp lệ; database có NOT NULL để giữ toàn vẹn dữ liệu.

Đây không phải duplication xấu nếu mỗi lớp có một lý do bảo vệ riêng. Duplication xấu là copy cùng một quy tắc vào nhiều Controller nhưng không có nguồn định nghĩa duy nhất.

## 15. Chuẩn hóa pagination và query parameter

Nhiều Controller có thể lặp code kiểm tra page, size, sort và direction. Có thể dùng Pageable của Spring Data hoặc một request abstraction thống nhất.

Ví dụ:

    @GetMapping("/courses")
    public Page<CourseResponse> list(
            @PageableDefault(size = 20, sort = "createdAt",
                    direction = Sort.Direction.DESC)
            Pageable pageable) {

        return courseQuery.list(pageable)
                .map(courseMapper::toResponse);
    }

Nếu ứng dụng cần giới hạn size tối đa hoặc quy ước sort riêng, hãy đặt ở cấu hình hoặc component chuyên biệt. Không sao chép cùng một đoạn Math.max và Math.min vào mọi Controller.

Tuy nhiên, danh sách sort field được phép có thể khác nhau theo endpoint. Không nên tạo một danh sách sort toàn cục nếu các query có ngữ nghĩa khác nhau. Hãy giữ whitelist theo use case hoặc query service.

## 16. Chuẩn hóa current actor và tenant context

Controller có thể lặp việc lấy principal và chuyển thành actor ID. Một cách là dùng @AuthenticationPrincipal trực tiếp; cách khác là tạo một abstraction như CurrentActorProvider nếu nhiều lớp cần actor hiện tại.

Ví dụ:

    public interface CurrentActorProvider {
        ActorId currentActorId();
    }

    @Component
    public class SecurityCurrentActorProvider
            implements CurrentActorProvider {

        @Override
        public ActorId currentActorId() {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()) {
                throw new UnauthenticatedException();
            }

            AppPrincipal principal =
                    (AppPrincipal) authentication.getPrincipal();

            return new ActorId(principal.userId());
        }
    }

Cách này có ích khi nhiều use case thực sự cần actor hiện tại và muốn tránh truyền principal qua nhiều lớp. Tuy nhiên, không nên ẩn nguồn actor nếu việc truyền actor tường minh làm luồng nghiệp vụ rõ hơn.

Đặc biệt với tác vụ nền hoặc message handler, không có HTTP request và SecurityContext hiện tại. Khi đó actor/tenant cần được truyền trong command hoặc message theo hợp đồng rõ, không dựa vào provider lấy principal từ thread.

## 17. Kiểm thử sau khi loại bỏ duplication

Refactor có thể thay đổi cách tổ chức nhưng phải giữ hành vi công khai, trừ khi có thay đổi hợp đồng được chủ ý.

### Test component dùng chung

- Mapper chuyển đúng các trường và không làm lộ dữ liệu nội bộ.
- Access policy cho phép actor hợp lệ và từ chối actor không hợp lệ.
- Validator xử lý đúng biên và thông báo.
- Exception handler trả đúng status, error code và format.
- Pagination helper giới hạn giá trị theo chính sách.

### Test từng Controller

Mỗi Controller vẫn cần test mapping, binding, response và việc gọi đúng use case. Việc dùng chung policy không có nghĩa bỏ test cho endpoint.

### Test tích hợp

Kiểm tra nhiều endpoint cùng sử dụng component có hành vi nhất quán. Với authorization, dùng ít nhất hai user và tài nguyên thuộc các owner/tenant khác nhau. Xác nhận request bị từ chối không gây side effect.

### Ví dụ policy test

    @Test
    void deniesEditingAnotherUsersDocument() {
        AppPrincipal alice = principal("alice");
        Document document = documentOwnedBy("bob");

        assertThrows(
                AccessDeniedException.class,
                () -> policy.checkCanEdit(alice, document));
    }

### Ví dụ mapper test

    @Test
    void doesNotExposeInternalFields() {
        Document document = documentWithInternalNotes("private note");

        DocumentResponse response = mapper.toResponse(document);

        assertEquals(document.getId(), response.id());
        assertFalse(response.toString().contains("private note"));
    }

Test mapper nên kiểm tra hợp đồng response, đặc biệt các trường nhạy cảm. Không nhất thiết phải kiểm tra chi tiết triển khai hoặc mọi getter.

## 18. Refactor an toàn theo từng bước

Không cần viết lại toàn bộ Controller cùng lúc. Có thể refactor theo quy trình:

1. Tìm các khối code lặp bằng search và so sánh hành vi, không chỉ so sánh cú pháp.
2. Ghi lại hợp đồng hiện tại: status, response body, error code, redirect và side effect.
3. Xác định phần thực sự có cùng lý do thay đổi.
4. Chọn abstraction theo trách nhiệm: policy, mapper, validator, application service hoặc advice.
5. Viết unit test cho component mới.
6. Thay một endpoint trước và chạy test MVC/integration liên quan.
7. Chuyển các endpoint còn lại sang component dùng chung.
8. Tìm lại các bản sao cũ và xóa chúng khi không còn caller.
9. Chạy test bảo mật và xác nhận dữ liệu không bị thay đổi ngoài ý muốn.
10. Review tên class, dependency và phạm vi của abstraction.

### Refactor ví dụ: kiểm tra owner

Trước:

    if (!document.getOwnerId().equals(actorId)) {
        throw new AccessDeniedException("Forbidden");
    }

Đoạn này xuất hiện trong ba Controller.

Sau:

    documentAccessPolicy.checkCanEdit(actorId, document);

Điểm quan trọng là policy được gọi từ use case hoặc tầng bảo vệ resource phù hợp. Nếu chỉ tạo helper rồi gọi từ ba Controller, các adapter khác như job hoặc API mới vẫn có thể bỏ qua kiểm tra.

### Refactor ví dụ: response mapping

Trước:

    return new DocumentResponse(
            document.getId(),
            document.getTitle(),
            document.getCreatedAt());

Sau:

    return documentMapper.toResponse(document);

Sau khi chuyển, cần xác nhận mapper không vô tình thêm trường nội bộ hoặc thay đổi timezone/format trong response.

## 19. Các sai lầm thường gặp khi tái sử dụng

### Gom mọi logic vào BaseController

BaseController trở thành lớp cha quá lớn và khiến Controller phụ thuộc chặt. Dùng composition và component có trách nhiệm rõ.

### Tạo CommonUtil cho mọi thứ

Utility class chỉ che giấu duplication. Tách theo khái niệm và lý do thay đổi.

### Dùng một DTO cho mọi endpoint

Request, response và View Model có hợp đồng khác nhau. Chia sẻ DTO chỉ khi cấu trúc và semantics thực sự giống nhau.

### Dùng một validator cho mọi use case

Hai use case có thể có quy tắc khác nhau dù dùng cùng entity. Chia sẻ constraint chung nhưng giữ business rule theo use case.

### Chỉ chuyển code ra helper mà không xác định nguồn có thẩm quyền

Nếu Controller A gọi policy còn Controller B vẫn kiểm tra riêng, duplication chưa được loại bỏ. Xác định nơi bắt buộc phải thực thi quy tắc.

### Lặp authorization ở nhiều nơi nhưng không thống nhất

Một endpoint kiểm tra role, endpoint khác kiểm tra owner, endpoint thứ ba bỏ qua tenant. Cần một policy thể hiện actor, resource và action; các lớp web vẫn có thể có quy tắc route-level bổ sung.

### Tập trung exception quá mức

Một handler chung trả cùng message cho mọi lỗi có thể làm mất thông tin field validation hoặc ngữ cảnh của HTML form. Tập trung phần format chung và giữ mapping theo loại lỗi/client.

### Tối ưu quá sớm

Không tạo framework generic khi chỉ có một use case. Chờ một pattern ổn định hoặc một quy tắc có nguy cơ lệch giữa nhiều nơi.

### Xóa validation vì đã có kiểm tra frontend

Client không đáng tin cậy. Server vẫn phải validate input và domain rule.

## 20. Ví dụ tổng hợp: hai endpoint dùng chung policy và mapper

Giả sử ứng dụng có hai đường truy cập tài liệu:

- GET /documents/{id} hiển thị trang chi tiết.
- GET /api/documents/{id} trả JSON.

Cả hai cần kiểm tra người dùng được xem tài liệu và dùng cùng một response representation cho API. Có thể tổ chức:

    @Service
    public class GetDocument {
        private final DocumentRepository documents;
        private final DocumentAccessPolicy accessPolicy;

        public GetDocument(
                DocumentRepository documents,
                DocumentAccessPolicy accessPolicy) {
            this.documents = documents;
            this.accessPolicy = accessPolicy;
        }

        public DocumentDetails execute(
                ActorId actorId,
                UUID documentId) {

            Document document = documents.findById(documentId)
                    .orElseThrow(DocumentNotFoundException::new);

            accessPolicy.checkCanRead(actorId, document);

            return DocumentDetails.from(document);
        }
    }

Controller HTML:

    @Controller
    @RequestMapping("/documents")
    public class DocumentPageController {
        private final GetDocument getDocument;

        @GetMapping("/{id}")
        public String detail(
                @PathVariable UUID id,
                @AuthenticationPrincipal AppPrincipal principal,
                Model model) {

            model.addAttribute(
                    "document",
                    getDocument.execute(
                            new ActorId(principal.userId()),
                            id));

            return "documents/detail";
        }
    }

Controller API:

    @RestController
    @RequestMapping("/api/documents")
    public class DocumentApiController {
        private final GetDocument getDocument;
        private final DocumentMapper mapper;

        @GetMapping("/{id}")
        public DocumentResponse detail(
                @PathVariable UUID id,
                @AuthenticationPrincipal AppPrincipal principal) {

            return mapper.toResponse(
                    getDocument.execute(
                            new ActorId(principal.userId()),
                            id));
        }
    }

Cả hai adapter gọi cùng use case nên không thể vô tình bỏ qua policy đọc tài liệu ở một đường. Controller HTML tạo Model cho View; Controller API chuyển result thành DTO. Nếu hai client có hợp đồng khác nhau, chúng có thể dùng mapper hoặc View Model riêng mà vẫn chia sẻ use case.

## 21. Checklist nhận diện và refactor logic lặp

- Các Controller có lặp cùng quy tắc nghiệp vụ hoặc kiểm tra quyền không?
- Cùng một lỗi có đang được ánh xạ thành nhiều response khác nhau không?
- DTO mapping có bị copy và bỏ sót trường không?
- Controller có truy cập repository để lặp lại cùng quy trình use case không?
- Validation đang nằm đúng ranh giới request và domain chưa?
- Quy tắc owner/tenant có một nơi thực thi có thẩm quyền không?
- Mapper có kiểm soát trường được công khai không?
- Component dùng chung có tên và trách nhiệm cụ thể không?
- Có tránh được BaseController hoặc CommonUtil quá lớn không?
- Khác biệt nghiệp vụ giữa các use case có được giữ lại không?
- Test dương và âm có bao phủ các endpoint dùng chung policy không?
- Refactor có giữ nguyên status, error contract, redirect và side effect không?
- Các bản sao cũ đã được loại bỏ sau khi chuyển caller chưa?

## Kết luận

Lặp lại logic kiểm tra và ánh xạ ở nhiều Controller làm tăng nguy cơ thiếu nhất quán, lỗi bảo mật và chi phí thay đổi. Cách giải quyết là xác định quy tắc nào thực sự có cùng ý nghĩa, rồi đặt nó ở thành phần có trách nhiệm phù hợp: application service điều phối use case, access policy kiểm tra quyền, validator kiểm tra input, mapper chuyển representation và ControllerAdvice chuẩn hóa lỗi.

Controller sau refactor nên cho thấy rõ request được chuyển thành use case nào và kết quả được trả dưới dạng HTTP hoặc View ra sao. Tái sử dụng có giá trị khi làm rõ trách nhiệm và tạo một nguồn thực thi nhất quán; nó trở thành gánh nặng khi gom các hành vi khác nhau vào một abstraction tổng quát. Refactor từng bước, giữ hợp đồng endpoint và kiểm thử cả đường được phép lẫn bị từ chối sẽ giúp kiến trúc MVC dễ thay đổi mà vẫn an toàn.
