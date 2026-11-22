# Giới hạn của nguyên tắc Controller mỏng

Trong MVC, Controller tiếp nhận request, chuyển dữ liệu đầu vào đến phần xử lý phù hợp và tạo response cho người gọi. Nguyên tắc **Controller mỏng (thin controller)** khuyến khích giữ phần này tập trung vào giao tiếp HTTP và điều phối ở mức cần thiết, còn quy tắc nghiệp vụ được đặt trong Model hoặc dịch vụ ứng dụng.

Nguyên tắc này giúp tránh Controller phình to, giảm việc lặp lại nghiệp vụ giữa nhiều endpoint và làm cho hành vi quan trọng có thể được kiểm thử độc lập. Tuy nhiên, “mỏng” không có nghĩa là Controller không được chứa bất kỳ logic nào, cũng không có nghĩa mọi dòng lệnh phải được chuyển sang một lớp Service mới. Nếu áp dụng máy móc, hệ thống có thể có nhiều lớp chuyển tiếp, dịch vụ quá rộng hoặc logic bị giấu ở những nơi khó tìm hơn.

Trong ứng dụng web theo MVC, Controller còn là ranh giới giữa giao thức HTTP với ứng dụng. Nó phải hiểu request, binding, mã trạng thái, header, chuyển hướng và cách biểu diễn lỗi. Một Controller tốt vì thế cần đủ trách nhiệm để tạo ra hợp đồng HTTP rõ ràng, đồng thời để quy tắc nghiệp vụ được bảo vệ ở nơi phù hợp.

## 1. Controller mỏng có nghĩa là gì?

Controller thường thực hiện một số công việc gắn trực tiếp với request:

- Nhận đường dẫn, query parameter, header, cookie và body.
- Binding dữ liệu vào đối tượng đầu vào hoặc tham số có kiểu.
- Kiểm tra định dạng và điều kiện đầu vào ở ranh giới giao tiếp.
- Lấy thông tin người dùng đã xác thực từ security context.
- Gọi use case hoặc dịch vụ ứng dụng tương ứng.
- Chuyển kết quả thành response, view name, redirect hoặc mã trạng thái HTTP.
- Chuyển lỗi ứng dụng thành phản hồi phù hợp với giao thức.

Controller không nên tự quyết định các quy tắc như đơn hàng nào được hủy, mức giảm giá được áp dụng, ai có quyền duyệt một giao dịch theo chính sách nghiệp vụ, hoặc trạng thái nào được phép chuyển tiếp. Những quyết định này cần được bảo vệ trong Model hoặc dịch vụ ứng dụng để mọi luồng gọi đều tuân thủ.

Có thể mô tả trách nhiệm bằng sơ đồ:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Controller"]
    B --> C["Binding và kiểm tra đầu vào"]
    C --> D["Application Service / Use Case"]
    D --> E["Domain Model và dữ liệu"]
    E --> D
    D --> F["Kết quả ứng dụng"]
    F --> B
    B --> G["HTTP response / View"]
~~~

Sơ đồ là cách tổ chức phổ biến, không phải chuỗi bắt buộc cho mọi framework. Một ứng dụng nhỏ có thể gọi Model trực tiếp từ Controller. Một ứng dụng lớn hơn có thể có application service, domain service, repository và cổng tích hợp. Điều quan trọng là quyết định nghiệp vụ có nơi sở hữu rõ ràng và không phụ thuộc vào việc request đến từ một trang web, API hay tác vụ nền.

### Controller mỏng không được đo bằng số dòng

Một phương thức Controller có 30 dòng xử lý binding, chọn response và thông báo lỗi có thể dễ hiểu hơn một phương thức 5 dòng gọi qua bốn lớp trung gian. Số dòng chỉ là tín hiệu để xem xét, không phải tiêu chí chất lượng.

Hãy đánh giá Controller bằng các câu hỏi:

- Nó có đang chứa quy tắc nghiệp vụ cần được dùng ở nhiều luồng không?
- Nó có thao tác trực tiếp với nhiều repository hoặc hệ thống bên ngoài không?
- Nó có tự quản lý một quy trình dài với nhiều quyết định nghiệp vụ không?
- Nó có thể được đọc như một bản mô tả ngắn gọn của request và response không?
- Những lỗi và kết quả trả về có rõ ràng đối với giao thức HTTP không?

Controller mỏng là một nguyên tắc về ranh giới trách nhiệm. Mục tiêu là làm cho luồng xử lý dễ hiểu và bảo vệ được quy tắc, không phải đạt một giới hạn số dòng tùy ý.

## 2. Lợi ích khi giữ Controller tập trung

### 2.1. Tránh lặp lại quy tắc nghiệp vụ

Giả sử ứng dụng cho phép hủy đơn hàng từ trang web, API dành cho nhân viên và một tác vụ xử lý hàng loạt. Nếu mỗi Controller tự kiểm tra trạng thái đơn hàng, các nơi có thể triển khai khác nhau. Một nơi cho phép hủy đơn đã giao, nơi khác lại từ chối.

Đặt quy tắc hủy đơn trong Model hoặc use case giúp mọi đầu vào dùng chung một hành vi. Controller chỉ chuyển yêu cầu hủy đến thao tác phù hợp.

### 2.2. Dễ kiểm thử hành vi nghiệp vụ

Use case có thể được kiểm thử với dữ liệu đầu vào và các phụ thuộc cần thiết mà không phải tạo HTTP request. Kiểm thử Controller tập trung vào định tuyến, binding, mã trạng thái và cách tạo response.

Sự phân chia này làm rõ nguyên nhân khi kiểm thử thất bại: lỗi thuộc quy tắc nghiệp vụ hay thuộc cách ứng dụng giao tiếp qua HTTP.

### 2.3. Giữ cho nhiều giao diện dùng chung nghiệp vụ

Khi ứng dụng có thêm REST API, giao diện quản trị, tác vụ nền hoặc consumer của message queue, các luồng đó có thể gọi cùng use case. Nếu nghiệp vụ nằm trong Controller của một giao diện, phần khác phải sao chép hoặc gọi vòng qua HTTP.

### 2.4. Giảm phụ thuộc vào framework web

Quy tắc nghiệp vụ không cần phụ thuộc annotation định tuyến, đối tượng HttpServletRequest, mã trạng thái hoặc template engine. Có thể thay đổi framework hoặc bổ sung một giao diện mới mà ít ảnh hưởng đến Model.

### 2.5. Làm rõ trách nhiệm và phạm vi thay đổi

Controller tập trung vào hợp đồng giao tiếp; use case điều phối thao tác; Model bảo vệ quy tắc; repository chịu trách nhiệm lưu trữ. Khi một yêu cầu thay đổi, người phát triển có thể xác định khu vực cần xem xét nhanh hơn.

## 3. Giới hạn thứ nhất: Controller vẫn cần xử lý logic thuộc HTTP

Một cách hiểu cực đoan về Controller mỏng có thể dẫn đến việc chuyển cả những quyết định gắn với giao thức sang dịch vụ ứng dụng. Điều đó làm dịch vụ biết quá nhiều về HTTP và khiến ranh giới trở nên mờ.

Controller thường là nơi phù hợp để:

- Chọn giữa trả HTML, JSON, redirect hoặc no-content.
- Chọn mã trạng thái như 200, 201, 204, 400, 404 hoặc 409 theo kết quả use case.
- Đặt header, cookie hoặc thông tin cache theo hợp đồng endpoint.
- Binding query parameter, path variable và body.
- Chuyển dữ liệu đầu vào thành command.
- Chọn View và chuẩn bị dữ liệu trình bày.
- Ánh xạ lỗi đã phân loại thành response của giao thức.

Ví dụ, sau khi tạo tài nguyên, Controller có thể trả HTTP 201 và header Location. Đây là quyết định của hợp đồng HTTP; không cần đưa vào Model chỉ để Controller có ít dòng hơn.

~~~java
@PostMapping
ResponseEntity<TaskResponse> create(
    @Valid @RequestBody CreateTaskRequest request
) {
    TaskResult result = createTask.execute(
        new CreateTaskCommand(request.title(), request.dueDate())
    );

    URI location = URI.create("/tasks/" + result.id());
    return ResponseEntity
        .created(location)
        .body(taskMapper.toResponse(result));
}
~~~

Use case xử lý thao tác tạo công việc. Controller chuyển request thành command, sau đó quyết định cách biểu diễn kết quả qua HTTP. Phần chọn status và header không phải quy tắc nghiệp vụ.

Tương tự, với ứng dụng MVC trả HTML, Controller có thể trả tên template hoặc redirect sau khi hoàn tất thao tác. Việc lựa chọn response là một phần tự nhiên của trách nhiệm Controller.

## 4. Giới hạn thứ hai: không phải mọi thao tác đều cần thêm một lớp Service

Một số dự án diễn giải Controller mỏng thành quy tắc “mỗi endpoint phải gọi một Service riêng”. Với chức năng đơn giản, điều này có thể tạo ra các lớp chỉ chuyển tiếp lời gọi:

~~~java
@Service
class TaskService {
    private final TaskRepository repository;

    TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    Task findById(long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Nếu lớp này không chứa điều phối, quy tắc, ranh giới giao dịch hay hành vi có thể tái sử dụng, nó có thể chỉ làm tăng số nơi cần mở khi đọc mã. Tuy nhiên, nếu thao tác đọc có phân quyền, lọc theo tenant, chuyển đổi kết quả hoặc cần một hợp đồng ứng dụng ổn định, dịch vụ đó có thể có giá trị.

Có thể cân nhắc ba trường hợp:

| Tình huống | Cách tổ chức có thể phù hợp |
|---|---|
| Chức năng CRUD nhỏ, một giao diện, không có quy tắc đáng kể | Controller gọi một abstraction dữ liệu đơn giản có thể đủ trong ứng dụng nhỏ |
| Một use case có nhiều bước hoặc được nhiều adapter sử dụng | Tạo application service/use case để điều phối |
| Quy tắc trạng thái, bất biến hoặc chính sách nghiệp vụ phức tạp | Đặt quy tắc trong Domain Model/domain service; application service điều phối |

Không có yêu cầu rằng mọi ứng dụng phải có cùng số tầng. Thêm một lớp khi nó tạo ra trách nhiệm hoặc ranh giới hữu ích: kiểm soát giao dịch, phối hợp nhiều thành phần, tái sử dụng một use case, cô lập framework hoặc tạo điểm kiểm thử có ý nghĩa.

## 5. Giới hạn thứ ba: chuyển hết logic sang Service có thể tạo ra Service khổng lồ

Controller phình to là vấn đề, nhưng một lớp Service chứa hàng chục use case không tự động là kiến trúc tốt hơn. Một TaskService có thể dần đảm nhận tạo công việc, phân công, duyệt, xuất báo cáo, gửi nhắc việc và đồng bộ với hệ thống bên ngoài. Khi đó, lớp này có nhiều lý do để thay đổi và trở thành điểm tập trung phụ thuộc.

Dấu hiệu một dịch vụ quá rộng:

- Có nhiều phương thức không liên quan ngoài việc cùng thao tác một loại entity.
- Constructor có quá nhiều phụ thuộc.
- Một thay đổi nhỏ ở một use case có thể ảnh hưởng đến các luồng khác.
- Các phương thức dùng chung nhiều trạng thái hoặc helper không rõ mục đích.
- Kiểm thử một hành vi cần khởi tạo rất nhiều thành phần không liên quan.

Hãy tổ chức dịch vụ theo **use case hoặc nhóm hành vi có liên quan**, thay vì chỉ theo tên bảng dữ liệu. Ví dụ, CreateTask, AssignTask và CompleteTask có thể là các thao tác ứng dụng riêng khi chúng có quy tắc và phụ thuộc khác nhau. Không nhất thiết mỗi thao tác phải có một lớp nếu chúng rất nhỏ và cùng thuộc một ranh giới rõ ràng.

Cũng không nên giấu nghiệp vụ vào một lớp Helper hoặc Mapper để làm Service trông nhỏ hơn. Vị trí của mã phải phản ánh trách nhiệm thực tế, không chỉ thay đổi hình thức.

## 6. Giới hạn thứ tư: Controller mỏng không thay thế phân chia đúng các loại validation

Validation thường là nơi dễ nhầm lẫn giữa trách nhiệm giao tiếp và nghiệp vụ. Không phải mọi kiểm tra đều nên chuyển sang một lớp duy nhất.

Có thể phân biệt:

| Loại kiểm tra | Ví dụ | Nơi phù hợp |
|---|---|---|
| Binding và định dạng | Chuỗi không chuyển được thành ngày, JSON sai cấu trúc | Framework web / Controller boundary |
| Ràng buộc đầu vào | Tiêu đề bắt buộc, độ dài tối đa, email đúng định dạng | Form Object / Request DTO và validation tại ranh giới |
| Bất biến của đối tượng | Số lượng không âm, trạng thái không thể null | Domain Model |
| Quy tắc theo trạng thái | Không thể hoàn tất công việc đã hủy | Domain Model hoặc domain service |
| Quy tắc phụ thuộc ngữ cảnh | Người dùng chỉ được duyệt đơn thuộc phạm vi được giao | Application service và chính sách phân quyền |

Spring MVC có thể dùng @Valid để kiểm tra Request DTO. Controller xử lý lỗi binding hoặc validation và chọn phản hồi phù hợp. Nhưng dữ liệu hợp lệ về định dạng vẫn có thể không hợp lệ về nghiệp vụ.

Ví dụ, tiêu đề có 40 ký tự có thể vượt qua validation, nhưng công việc đã khóa thì không được sửa. Quy tắc này phải được kiểm tra trong thao tác nghiệp vụ để không bị bỏ qua khi yêu cầu đến từ API hoặc tác vụ nền.

Không nên chuyển tất cả validation vào Controller vì Model có thể bị gọi từ nơi khác. Cũng không nên đẩy mọi kiểm tra định dạng sang Domain Model, khiến mô hình nghiệp vụ phụ thuộc vào cách biểu mẫu web thu thập dữ liệu.

## 7. Giới hạn thứ năm: phân quyền có nhiều lớp và không thể chỉ dựa vào Controller

Controller có thể tham gia xác thực và phân quyền ở mức endpoint. Ví dụ, Spring Security có thể giới hạn endpoint bằng cấu hình hoặc method security. Tuy nhiên, một quy tắc quyền phụ thuộc vào dữ liệu cụ thể thường cần được kiểm tra gần use case hoặc nghiệp vụ.

Giả sử người dùng có quyền truy cập chức năng duyệt đơn hàng, nhưng chỉ được duyệt đơn thuộc nhóm mình phụ trách. Kiểm tra một vai trò chung tại Controller là chưa đủ; ứng dụng phải xác minh mối quan hệ giữa người dùng và đơn hàng cụ thể.

Một cách tổ chức là:

- Security filter xác thực danh tính và xây dựng principal.
- Controller lấy thông tin danh tính cần thiết và chuyển vào command.
- Application service kiểm tra quyền trên tài nguyên hoặc gọi một authorization policy.
- Domain Model bảo vệ các điều kiện trạng thái không thể vi phạm.

Cờ canApprove để ẩn nút trên giao diện chỉ hỗ trợ trải nghiệm người dùng. Mọi request thực hiện thao tác vẫn phải được kiểm tra ở phía máy chủ. Giữ Controller mỏng không có nghĩa là bỏ qua bảo mật ở ranh giới; nó có nghĩa là đặt từng quyết định quyền tại nơi có đủ ngữ cảnh để đánh giá.

## 8. Giới hạn thứ sáu: giao dịch, tính nhất quán và tác dụng phụ cần ranh giới rõ

Một Controller có thể gọi nhiều dịch vụ. Nếu mỗi dịch vụ tự mở và kết thúc giao dịch riêng, một use case gồm nhiều bước có thể để lại trạng thái không nhất quán khi bước sau thất bại.

Ví dụ, thao tác phân công công việc có thể cập nhật người phụ trách, ghi lịch sử và tạo sự kiện để gửi thông báo. Ứng dụng cần xác định những thay đổi dữ liệu nào phải cùng thành công hoặc cùng rollback, và tác dụng phụ nào nên thực hiện sau khi giao dịch commit.

Ranh giới giao dịch thường phù hợp ở application service hoặc use case vì nơi đó biết toàn bộ thao tác cần phối hợp. Controller không nên điều khiển từng lệnh commit/rollback theo request. Model vẫn bảo vệ bất biến của nghiệp vụ, còn repository thực hiện lưu trữ.

Với tác dụng phụ như gửi email hoặc gọi dịch vụ ngoài, không nên giữ transaction cơ sở dữ liệu mở trong lúc chờ mạng nếu không cần thiết. Có thể ghi sự kiện trong cùng giao dịch và xử lý sau commit bằng cơ chế phù hợp, chẳng hạn transactional outbox. Đây là quyết định về tính nhất quán của ứng dụng, không phải việc làm Controller ngắn hơn.

## 9. Giới hạn thứ bảy: lỗi cần được ánh xạ ở đúng ranh giới

Use case có thể phát hiện tài nguyên không tồn tại, trạng thái xung đột hoặc thao tác bị từ chối. Controller cần tạo response phù hợp, nhưng nếu mỗi Controller tự bắt và chuyển mọi exception, mã xử lý lỗi sẽ bị lặp.

Trong Spring MVC, @ControllerAdvice và các handler có thể tập trung việc ánh xạ lỗi ứng dụng thành response HTTP:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(TaskNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
        TaskNotFoundException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("TASK_NOT_FOUND", "Không tìm thấy công việc"));
    }

    @ExceptionHandler(TaskStateConflictException.class)
    ResponseEntity<ApiError> handleConflict(
        TaskStateConflictException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("TASK_STATE_CONFLICT",
                "Trạng thái công việc không cho phép thao tác này"));
    }
}
~~~

Đây là một adapter ở ranh giới web: nó chuyển loại lỗi đã được ứng dụng phân loại thành status và body HTTP. Không nên trả stack trace, câu SQL hoặc thông tin nội bộ cho người dùng. Log kỹ thuật cần được ghi ở nơi thích hợp với quyền truy cập được kiểm soát.

Không phải mọi lỗi đều nên bị bắt rồi chuyển thành 200 với một thông báo chung. Mã trạng thái cần phản ánh hợp đồng API; lỗi validation, không tìm thấy, xung đột, không được phép và lỗi máy chủ có ý nghĩa khác nhau.

## 10. Ví dụ: Controller phình to và cách phân chia lại

Giả sử endpoint duyệt đơn hàng cần tải đơn, kiểm tra quyền, kiểm tra trạng thái, cập nhật dữ liệu và gửi thông báo. Nếu tất cả nằm trong Controller, phương thức sẽ kết hợp HTTP với quy tắc nghiệp vụ:

~~~java
@PostMapping("/{id}/approve")
ResponseEntity<?> approve(
    @PathVariable UUID id,
    @AuthenticationPrincipal AppPrincipal principal
) {
    Order order = orderRepository.findById(id).orElseThrow();

    if (!principal.hasRole("APPROVER")) {
        return ResponseEntity.status(403).build();
    }

    if (order.getStatus() != OrderStatus.PENDING) {
        return ResponseEntity.status(409).build();
    }

    order.setStatus(OrderStatus.APPROVED);
    order.setApprovedBy(principal.userId());
    orderRepository.save(order);

    notificationClient.sendApprovalNotice(order);

    return ResponseEntity.ok(order);
}
~~~

Phương thức này có nhiều vấn đề. Nó trộn truy cập dữ liệu, phân quyền, quy tắc chuyển trạng thái, tác dụng phụ và cách tạo response. Quy tắc có thể bị bỏ qua ở một luồng khác; việc gửi thông báo cũng có thể thất bại sau khi dữ liệu đã được lưu.

Có thể chuyển phần điều phối vào use case:

~~~java
public record ApproveOrderCommand(UUID orderId, UUID actorId) {}

public record OrderApprovalResult(
    UUID orderId,
    OrderStatus status,
    Instant approvedAt
) {}

@Service
class ApproveOrder {

    private final OrderRepository orders;
    private final OrderAuthorization authorization;
    private final Clock clock;

    ApproveOrder(
        OrderRepository orders,
        OrderAuthorization authorization,
        Clock clock
    ) {
        this.orders = orders;
        this.authorization = authorization;
        this.clock = clock;
    }

    @Transactional
    public OrderApprovalResult execute(ApproveOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        authorization.requireCanApprove(command.actorId(), order);
        order.approve(command.actorId(), clock.instant());

        return new OrderApprovalResult(
            order.getId(),
            order.getStatus(),
            order.getApprovedAt()
        );
    }
}
~~~

Đối tượng Order chịu trách nhiệm bảo vệ chuyển trạng thái hợp lệ. Authorization policy đánh giá quyền trên đơn cụ thể. Use case phối hợp việc tải đơn, kiểm tra quyền và thực hiện thao tác trong ranh giới giao dịch. Ví dụ đã lược bỏ phần ghi sự kiện thông báo; trong ứng dụng thật, thông báo nên được xử lý theo cơ chế bảo đảm phù hợp với giao dịch và khả năng thử lại.

Controller còn lại tập trung vào HTTP:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final ApproveOrder approveOrder;
    private final OrderResponseMapper responseMapper;

    OrderController(
        ApproveOrder approveOrder,
        OrderResponseMapper responseMapper
    ) {
        this.approveOrder = approveOrder;
        this.responseMapper = responseMapper;
    }

    @PostMapping("/{id}/approval")
    ResponseEntity<OrderResponse> approve(
        @PathVariable UUID id,
        @AuthenticationPrincipal AppPrincipal principal
    ) {
        OrderApprovalResult result = approveOrder.execute(
            new ApproveOrderCommand(id, principal.userId())
        );

        return ResponseEntity.ok(responseMapper.toResponse(result));
    }
}
~~~

Controller vẫn có logic: đọc ID, lấy danh tính, tạo command, gọi use case và ánh xạ kết quả thành response. Đó là logic điều phối và giao thức phù hợp với ranh giới HTTP. Phần quyết định đơn có được duyệt hay không nằm trong ứng dụng và Model.

## 11. Khi nào nên giữ một ít logic trong Controller?

Không cần chuyển mọi điều kiện thành use case hoặc policy. Có những logic thuộc về request và response, nên để gần Controller:

- Chuyển một query parameter thành kiểu dữ liệu chuẩn.
- Chọn giá trị mặc định của tham số giao diện.
- Kiểm tra một header bắt buộc của endpoint.
- Chọn response 204 khi use case không trả nội dung.
- Trả redirect sau thao tác biểu mẫu.
- Chọn template cho trạng thái hiển thị.
- Chuyển một kết quả ứng dụng thành mã trạng thái HTTP.
- Tạo URL hoặc Location header từ định danh tài nguyên.

Ví dụ, nếu một endpoint cho phép người dùng chọn trang và kích thước trang, Controller có thể chuẩn hóa tham số hoặc áp dụng giới hạn giao thức. Tuy nhiên, nếu quy tắc phân trang gắn với quyền truy cập hoặc chính sách nghiệp vụ, phần ứng dụng cần kiểm tra lại.

Một điều kiện thực tế để quyết định vị trí là hỏi: “Nếu cùng thao tác này được gọi từ API khác hoặc tác vụ nền, logic này có còn cần thiết không?” Nếu có, đó có thể là logic ứng dụng hoặc nghiệp vụ. Nếu logic chỉ tồn tại vì HTTP, HTML hoặc cách phản hồi của endpoint, Controller là nơi hợp lý.

## 12. Kiểm thử theo ranh giới trách nhiệm

Nguyên tắc Controller mỏng chỉ có ích khi các ranh giới được kiểm thử phù hợp. Có thể chia kiểm thử như sau:

| Phạm vi | Nội dung cần xác minh |
|---|---|
| Controller / Web layer | Định tuyến, binding, validation đầu vào, principal, mã trạng thái, header, response và redirect |
| Application service / Use case | Trình tự điều phối, quyền trên tài nguyên, gọi repository/cổng ngoài và ranh giới giao dịch |
| Domain Model | Bất biến, chuyển trạng thái, phép tính và quy tắc nghiệp vụ |
| Repository / Adapter | Truy vấn, ánh xạ và tương tác với hệ thống bên ngoài |
| Tích hợp | Luồng request thực tế, security filter, transaction, persistence và ánh xạ lỗi |

Kiểm thử Controller không cần lặp lại toàn bộ quy tắc nghiệp vụ nếu các quy tắc đó đã được kiểm thử ở use case và Model. Ngược lại, kiểm thử use case không xác minh được endpoint có trả đúng mã HTTP hoặc binding body đúng hay không.

Với Spring, có thể dùng kiểm thử MVC slice để xác minh lớp web và mock use case, sau đó kiểm thử use case độc lập với repository giả hoặc test double. Những luồng quan trọng cần thêm kiểm thử tích hợp với cấu hình bảo mật và cơ sở dữ liệu thực tế của ứng dụng.

Đừng dùng số lượng unit test làm bằng chứng duy nhất rằng Controller đã mỏng. Hãy kiểm tra liệu logic có đang nằm ở đúng nơi, các hợp đồng có rõ ràng và hành vi có thể được kiểm thử ở ranh giới tương ứng hay không.

## 13. Những dấu hiệu áp dụng nguyên tắc máy móc

Một số dấu hiệu cho thấy đội phát triển đang coi “Controller mỏng” là mục tiêu hình thức:

- Mỗi endpoint có một Service chỉ chuyển tiếp đúng một lời gọi mà không tạo ra ranh giới có ích.
- Service biết HttpServletRequest, ResponseEntity, tên template hoặc mã trạng thái HTTP dù không cần.
- Controller chỉ còn một dòng nhưng logic thực tế bị đẩy vào mapper, helper hoặc event listener khó lần theo.
- Một Service tổng hợp chứa mọi use case của cả module.
- Quy tắc nghiệp vụ được kiểm tra ở Controller để tránh làm Model phức tạp.
- Mọi lỗi đều bị bắt ở Controller và trả về cùng một response.
- Việc ẩn nút trên View được xem là đủ để bảo vệ thao tác.
- Giao dịch bị chia thành nhiều phần vì từng service tự quản lý transaction mà không có ranh giới use case.

Khi gặp các dấu hiệu này, hãy lần theo một request từ đầu đến cuối và xác định nơi quyết định thực sự được thực hiện. Sau đó đặt trách nhiệm tại ranh giới có đủ ngữ cảnh, thay vì chỉ di chuyển mã sang tệp khác.

## 14. Cách áp dụng nguyên tắc một cách linh hoạt

Có thể dùng trình tự sau khi thiết kế một endpoint:

1. Xác định hợp đồng HTTP: phương thức, đường dẫn, đầu vào, đầu ra và mã trạng thái.
2. Xác định phần nào là binding, định dạng và phản hồi giao thức.
3. Xác định use case mà request muốn thực hiện.
4. Đưa các bước điều phối nhiều thành phần và ranh giới giao dịch vào application service khi cần.
5. Đặt bất biến và quy tắc trạng thái trong Model hoặc domain service.
6. Xác định nơi kiểm tra quyền theo endpoint và nơi kiểm tra quyền trên tài nguyên.
7. Thiết kế cách chuyển lỗi ứng dụng thành phản hồi HTTP.
8. Kiểm thử từng ranh giới và kiểm thử tích hợp cho luồng quan trọng.

Không cần tạo tầng mới chỉ để tuân thủ sơ đồ. Nếu chức năng đơn giản, một Controller gọi một abstraction nhỏ có thể đủ. Khi use case phát triển, có nhiều giao diện sử dụng chung hoặc xuất hiện quy tắc quan trọng, hãy tách phần điều phối và nghiệp vụ thành những thành phần có trách nhiệm rõ ràng.

## 15. Những điểm cần ghi nhớ

Controller mỏng giúp giữ ranh giới HTTP rõ ràng, tránh lặp quy tắc nghiệp vụ và hỗ trợ nhiều giao diện dùng chung một hành vi. Nhưng “mỏng” không đồng nghĩa với không có logic, ít dòng mã hoặc bắt buộc một Service cho mỗi endpoint.

Controller vẫn cần xử lý binding, dữ liệu đầu vào ở ranh giới, danh tính request và cách tạo response. Application service phù hợp để điều phối use case và ranh giới giao dịch; Domain Model bảo vệ bất biến và chuyển trạng thái; các adapter chịu trách nhiệm giao tiếp với cơ sở dữ liệu hoặc hệ thống bên ngoài.

Nếu chỉ chuyển mã từ Controller sang Service mà không làm rõ trách nhiệm, độ phức tạp vẫn còn nguyên. Hãy đánh giá vị trí của logic theo lý do thay đổi, ngữ cảnh cần thiết và khả năng tái sử dụng. Một Controller tốt là Controller giúp người đọc hiểu request được xử lý thế nào, trong khi quy tắc quan trọng được bảo vệ ở nơi mọi luồng gọi đều phải tuân theo.
