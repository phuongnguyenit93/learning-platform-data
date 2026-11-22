# Viết endpoint nghiệp vụ tùy chỉnh qua tầng service

Spring Data REST tự động xuất repository thành REST resource, phù hợp với các thao tác CRUD và query method thông thường. Khi nghiệp vụ cần một hành động có ý nghĩa riêng — chẳng hạn duyệt đơn hàng, xác nhận thanh toán, khóa tài khoản hoặc hoàn tất quy trình — nên tạo endpoint tùy chỉnh và chuyển phần xử lý vào service layer.

Cách tổ chức phổ biến là:

1. **Controller** nhận HTTP request, kiểm tra dữ liệu đầu vào và chuyển request thành lời gọi ứng dụng.
2. **Service** thực hiện use case, kiểm tra quy tắc nghiệp vụ, phối hợp nhiều repository và quản lý transaction.
3. **Repository** đọc hoặc lưu entity qua Spring Data.
4. **DTO/response model** định nghĩa dữ liệu API nhận và trả về, giúp contract HTTP độc lập với cấu trúc entity.

Controller nên mỏng và service không phụ thuộc vào HTTP. Nhờ vậy, cùng một nghiệp vụ có thể được gọi từ Spring Data REST, controller khác, message consumer hoặc tác vụ nền.

## 1. Khi nào cần endpoint tùy chỉnh?

Repository resource mặc định rất phù hợp khi client cần tạo, đọc, cập nhật hoặc xóa một entity theo mô hình CRUD. Query method phù hợp với truy vấn có tham số rõ ràng.

Tuy nhiên, nhiều hành động nghiệp vụ không tương đương một thao tác CRUD đơn giản:

- Duyệt đơn hàng chỉ khi đơn ở trạng thái PENDING và người duyệt có quyền.
- Xác nhận thanh toán cần kiểm tra giao dịch và cập nhật trạng thái đơn.
- Hoàn tất đơn hàng cần kiểm tra tồn kho, ghi nhận thời điểm và tạo lịch sử.
- Khóa tài khoản có thể cần thu hồi phiên đăng nhập và ghi lý do.
- Hủy đặt chỗ có thể cần tính phí, cập nhật chỗ trống và gửi sự kiện.

Trong các trường hợp này, không nên buộc client tự gọi nhiều endpoint repository theo một thứ tự để tạo thành workflow. Server cần thực hiện use case trong một service để bảo đảm các quy tắc nghiệp vụ được áp dụng nhất quán.

## 2. Kiến trúc controller → service → repository

Luồng xử lý nên có ranh giới rõ:

~~~text
HTTP request
    |
    v
Custom controller
    |  bind, validate, map input
    v
Application service
    |  authorization, business rules, transaction
    v
Domain model + repositories
    |  load, change state, persist
    v
DTO / response model
    |
    v
HTTP response
~~~

Trách nhiệm của từng lớp:

| Thành phần | Trách nhiệm |
|---|---|
| Controller | Mapping URL, HTTP method, request/response, status code |
| Request DTO | Mô tả dữ liệu client được phép gửi |
| Service | Thực hiện use case, điều phối nghiệp vụ và transaction |
| Domain entity | Bảo vệ invariant và chuyển trạng thái hợp lệ |
| Repository | Truy vấn và lưu dữ liệu |
| Response DTO | Công bố dữ liệu API theo contract |

Không đặt câu truy vấn phức tạp, quy tắc chuyển trạng thái hoặc chuỗi thao tác repository trực tiếp trong controller. Cũng không đưa `HttpServletRequest`, `ResponseEntity` hay HTTP status code vào service.

## 3. Tạo custom endpoint trong Spring Data REST

Nếu endpoint cần nằm dưới base path của Spring Data REST và dùng cơ chế tích hợp của Spring Data REST, có thể dùng **`@RepositoryRestController`**.

Ví dụ API duyệt đơn hàng:

~~~java
import jakarta.validation.Valid;

import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;

@RepositoryRestController
@RequestMapping("/orders")
public class OrderWorkflowController {

    private final OrderApplicationService orderService;

    public OrderWorkflowController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<OrderView> approve(
            @PathVariable Long id,
            @Valid @RequestBody ApproveOrderRequest request,
            Authentication authentication) {

        OrderView result = orderService.approve(
                id,
                request.getNote(),
                authentication.getName()
        );

        return ResponseEntity.ok(result);
    }
}
~~~

Với cấu hình base path mặc định, endpoint có dạng:

~~~http
POST /orders/42/approve
Content-Type: application/json
Accept: application/json
~~~

Body ví dụ:

~~~json
{
  "note": "Đã kiểm tra thông tin đơn hàng"
}
~~~

**`@RepositoryRestController`** cho phép Spring Data REST áp dụng base path và tích hợp controller theo cơ chế của nó. Nếu dùng một **`@RestController`** Spring MVC thông thường, endpoint thuộc mapping của Spring MVC; hãy tự xác định URL, base path, CORS và cách tích hợp với cấu hình ứng dụng.

Chọn annotation theo vị trí và contract mong muốn của endpoint. Không cần tạo controller tùy chỉnh nếu repository resource đã đáp ứng đầy đủ use case.

## 4. Dùng DTO để kiểm soát request và response

Không nên nhận trực tiếp entity JPA làm request body cho một hành động nghiệp vụ. DTO giúp giới hạn các trường client có thể gửi và tránh việc client ghi đè thuộc tính nội bộ.

Request DTO:

~~~java
import jakarta.validation.constraints.Size;

public class ApproveOrderRequest {

    @Size(max = 500)
    private String note;

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Response DTO:

~~~java
import java.time.Instant;

public class OrderView {

    private final Long id;
    private final String status;
    private final Instant approvedAt;
    private final String approvedBy;

    public OrderView(
            Long id,
            String status,
            Instant approvedAt,
            String approvedBy) {
        this.id = id;
        this.status = status;
        this.approvedAt = approvedAt;
        this.approvedBy = approvedBy;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }

    public String getApprovedBy() {
        return approvedBy;
    }
}
~~~

Controller dùng **`@Valid`** để kiểm tra request DTO trước khi gọi service. Các quy tắc quan trọng vẫn phải được kiểm tra trong service/domain vì use case có thể được gọi từ nhiều entry point khác nhau.

Response DTO chỉ công bố dữ liệu mà client cần. Không trả về password hash, token nội bộ, thông tin audit nhạy cảm hoặc toàn bộ object graph của entity.

## 5. Đặt nghiệp vụ và transaction trong service

Service thực hiện use case. Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderView approve(Long orderId, String note, String actor) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new OrderNotFoundException(orderId));

        order.approve(actor, note);

        return new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getApprovedAt(),
                order.getApprovedBy()
        );
    }
}
~~~

Entity chịu trách nhiệm bảo vệ quy tắc chuyển trạng thái:

~~~java
public void approve(String actor, String note) {
    if (status != OrderStatus.PENDING) {
        throw new InvalidOrderStateException(
                "Only pending orders can be approved"
        );
    }

    this.status = OrderStatus.APPROVED;
    this.approvedBy = actor;
    this.approvedAt = Instant.now();
    this.approvalNote = note;
}
~~~

Trong ví dụ:

- Service tải entity trong transaction.
- Domain method kiểm tra trạng thái hiện tại trước khi chuyển sang APPROVED.
- Transaction bao trọn thao tác đọc và thay đổi.
- JPA dirty checking ghi thay đổi khi transaction flush/commit.
- Service trả về một view, không trả `ResponseEntity`.

Nếu use case cần lưu nhiều entity, cập nhật tồn kho hoặc ghi nhận thanh toán, hãy điều phối chúng trong cùng service và xác định ranh giới transaction phù hợp.

## 6. Phối hợp nhiều repository trong một use case

Một nghiệp vụ thường liên quan đến nhiều aggregate hoặc repository. Ví dụ xác nhận đơn hàng cần kiểm tra payment, cập nhật order và ghi nhận một bản ghi audit:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;
    private final OrderHistoryRepository historyRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository,
            OrderHistoryRepository historyRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
        this.historyRepository = historyRepository;
    }

    @Transactional
    public OrderView confirmPayment(Long orderId, String actor) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        Payment payment = paymentRepository.findSuccessfulByOrderId(orderId)
                .orElseThrow(() -> new PaymentNotConfirmedException(orderId));

        order.confirmPayment(payment.getId(), actor);

        historyRepository.save(
                OrderHistory.paymentConfirmed(order, actor)
        );

        return OrderView.from(order);
    }
}
~~~

Đây là ví dụ minh họa cấu trúc; tên method và factory cần khớp với domain model thực tế.

**`@Transactional`** giúp các thay đổi database trong cùng transaction được commit hoặc rollback cùng nhau. Tuy nhiên, transaction database không tự rollback được lời gọi tới hệ thống thanh toán, email hoặc dịch vụ bên ngoài. Với side effect ngoài transaction, hãy cân nhắc outbox pattern, retry có kiểm soát hoặc saga phù hợp.

## 7. Chọn HTTP method và response status

Thiết kế endpoint theo ý nghĩa của thao tác:

| Ý định | HTTP method thường dùng | Ví dụ |
|---|---|---|
| Gửi một command để thực hiện hành động | POST | **`POST /orders/42/approve`** |
| Đặt một trạng thái/giá trị theo URI với tính idempotent | PUT | **`PUT /orders/42/approval`** |
| Đọc kết quả hoặc trạng thái | GET | **`GET /orders/42`** |
| Xóa một resource hoặc association | DELETE | **`DELETE /orders/42`** |

POST phù hợp với command tạo ra một lần thực thi nghiệp vụ. Nếu client retry do timeout, server có thể nhận cùng command nhiều lần; với thao tác thanh toán hoặc tạo giao dịch, hãy thiết kế idempotency key hoặc cơ chế chống xử lý trùng.

Chọn response status theo kết quả:

- **`200 OK`**: thao tác thành công và trả về representation kết quả.
- **`201 Created`**: thao tác tạo một resource mới; nên trả **`Location`** trỏ tới resource đó.
- **`202 Accepted`**: đã nhận command nhưng xử lý bất đồng bộ chưa hoàn tất.
- **`204 No Content`**: thao tác thành công và không cần body response.
- **`400 Bad Request`**: request không hợp lệ.
- **`404 Not Found`**: resource đích không tồn tại.
- **`409 Conflict`**: trạng thái hiện tại xung đột với thao tác được yêu cầu.
- **`403 Forbidden`**: người dùng đã xác thực nhưng không có quyền.

Không trả 200 cho mọi trường hợp. Status code giúp client hiểu kết quả mà không phải phân tích message tùy ý.

## 8. Validation, authorization và xử lý lỗi

Controller nên validate hình dạng dữ liệu đầu vào bằng Jakarta Bean Validation:

~~~java
@PostMapping("/{id}/approve")
public ResponseEntity<OrderView> approve(
        @PathVariable Long id,
        @Valid @RequestBody ApproveOrderRequest request,
        Authentication authentication) {
    // Gọi service
}
~~~

Service/domain tiếp tục kiểm tra điều kiện nghiệp vụ như:

- Đơn hàng có tồn tại không?
- Đơn có đang ở trạng thái cho phép duyệt không?
- Người gọi có quyền duyệt đơn này không?
- Payment đã thành công chưa?
- Dữ liệu liên quan có thỏa invariant không?

Có thể đặt authorization tại service method:

~~~java
@PreAuthorize("hasAuthority('order:approve')")
@Transactional
public OrderView approve(Long orderId, String note, String actor) {
    // Thực hiện use case
}
~~~

Đảm bảo method security đã được bật bằng **`@EnableMethodSecurity`**. Nếu quyền phụ thuộc vào chủ sở hữu hoặc tenant, kiểm tra phạm vi dữ liệu trong service/repository thay vì chỉ dựa vào role chung.

Dùng exception nghiệp vụ có ý nghĩa và ánh xạ chúng thành HTTP response phù hợp qua exception handler. Ví dụ:

- **`OrderNotFoundException`** → 404.
- **`InvalidOrderStateException`** → 409.
- **`PaymentNotConfirmedException`** → 409.
- **`AccessDeniedException`** → 403.

Không để controller trả stack trace hoặc chi tiết database cho client.

## 9. Tương tác với repository resource mặc định

Endpoint tùy chỉnh có thể cùng tồn tại với repository resource:

~~~http
GET  /orders
GET  /orders/42
POST /orders
PUT  /orders/42
PATCH /orders/42
POST /orders/42/approve
~~~

Các endpoint CRUD vẫn phục vụ thao tác dữ liệu tổng quát. Endpoint **`/approve`** thể hiện một command nghiệp vụ riêng.

Cần cân nhắc không cho client thay đổi trực tiếp các trường trạng thái nhạy cảm qua generic PUT/PATCH nếu điều đó có thể bỏ qua workflow. Có thể dùng DTO/projection, **`@ReadOnlyProperty`**, security rule hoặc custom repository/controller policy để bảo vệ các trường đó theo contract của API.

Không nên tạo hai endpoint có cùng mapping và method vì sẽ gây xung đột handler. Kiểm tra base path của Spring Data REST và URL mapping của controller tùy chỉnh để tránh trùng lặp.

## 10. Ghi nhận sự kiện và side effect

Một use case có thể cần gửi email, phát domain event hoặc thông báo cho hệ thống khác. Không nên đặt toàn bộ logic tích hợp bên ngoài trực tiếp trong controller.

Có thể phát application event từ service sau khi thay đổi domain state:

~~~java
public record OrderApprovedEvent(
        Long orderId,
        String approvedBy
) {
}
~~~

~~~java
@Service
public class OrderApplicationService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void approve(Long orderId, String actor) {
        // Load order, kiểm tra và cập nhật trạng thái...
        eventPublisher.publishEvent(
                new OrderApprovedEvent(orderId, actor)
        );
    }
}
~~~

Nếu listener thực hiện side effect sau commit, có thể dùng **`@TransactionalEventListener(phase = AFTER_COMMIT)`**. Với yêu cầu không được mất sự kiện khi ứng dụng dừng giữa commit và publish, cân nhắc transactional outbox thay vì chỉ dựa vào in-memory event.

Không dùng listener để che giấu logic cốt lõi mà người đọc use case cần thấy. Các quy tắc quyết định việc duyệt đơn nên nằm trong service/domain; listener phù hợp với phản ứng phụ sau sự kiện.

## 11. Kiểm thử endpoint và service

Nên kiểm tra cả lớp HTTP lẫn nghiệp vụ.

**Service unit test** xác minh quy tắc domain:

- Đơn PENDING được duyệt thành công.
- Đơn đã CANCELLED không thể duyệt.
- Payment chưa thành công không thể xác nhận.
- Repository được gọi đúng và lịch sử được ghi nhận.

**Controller integration test** xác minh contract HTTP:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderWorkflowControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void approveOrderReturnsUpdatedView() throws Exception {
        mockMvc.perform(post("/orders/42/approve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"note":"Checked"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("APPROVED"));
    }
}
~~~

Ví dụ này giả định endpoint mapping và dữ liệu kiểm thử đã được thiết lập. Nếu endpoint yêu cầu authentication hoặc authority, thêm security test context và kiểm tra cả trường hợp 401/403.

Cũng cần kiểm tra:

- Request DTO không hợp lệ bị từ chối.
- ID không tồn tại trả về 404.
- Chuyển trạng thái sai trả về 409.
- Transaction rollback khi một bước database thất bại.
- Retry command không tạo side effect trùng nếu use case cần idempotency.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Controller chứa nhiều quy tắc nghiệp vụ | Logic được đặt sai lớp | Chuyển use case vào service/domain |
| Nhiều endpoint lặp cùng một quy tắc | Business logic nằm rải rác ở controller | Tái sử dụng một service method |
| Một phần dữ liệu đã lưu khi bước sau thất bại | Transaction không bao trọn các thao tác database | Đặt ranh giới **`@Transactional`** ở service |
| Gọi service từ batch không có transaction | Transaction chỉ được đặt ở controller hoặc không qua proxy | Đặt transaction trên service method và gọi qua Spring bean |
| Client có thể tự sửa trạng thái nhạy cảm bằng PUT | Entity được bind trực tiếp hoặc generic update quá rộng | Dùng DTO, read-only field và endpoint command riêng |
| Retry làm xử lý thanh toán hai lần | Command không có idempotency strategy | Dùng idempotency key hoặc khóa/unique constraint phù hợp |
| Endpoint tùy chỉnh không nằm dưới base path | Dùng controller stereotype không phù hợp | Dùng **`@RepositoryRestController`** cho endpoint gắn với Spring Data REST hoặc cấu hình MVC riêng |
| HTTP trả thành công dù nghiệp vụ thất bại | Exception bị nuốt hoặc status code không phản ánh lỗi | Dùng exception mapping và kiểm tra response contract |

## 13. Checklist thiết kế

- Chỉ tạo custom endpoint khi repository CRUD/query resource không diễn đạt được use case.
- Chọn **`@RepositoryRestController`** nếu endpoint thuộc base path và tích hợp với Spring Data REST.
- Giữ controller mỏng: bind request, validate đầu vào, gọi service và tạo response.
- Dùng request/response DTO để kiểm soát contract và trường được phép ghi.
- Đặt quy tắc nghiệp vụ và transaction trong service/domain.
- Dùng repository để truy cập dữ liệu, không để controller điều phối nhiều repository.
- Kiểm tra authorization ở service hoặc method security khi use case cần được bảo vệ.
- Chọn HTTP method, status code và idempotency theo ý nghĩa nghiệp vụ.
- Tách side effect ngoài transaction và dùng outbox khi cần bảo đảm phát sự kiện.
- Kiểm thử service, HTTP contract, validation, authorization và rollback.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Customizing the REST API](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-api.html)
- [Spring Data REST — Customizing HTTP endpoints](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
