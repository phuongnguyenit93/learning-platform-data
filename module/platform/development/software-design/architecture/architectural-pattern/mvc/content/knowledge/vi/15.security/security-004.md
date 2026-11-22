# Vị trí đặt kiểm tra quyền để bảo vệ nhiều loại giao diện

Một ứng dụng MVC có thể tiếp nhận thao tác từ nhiều loại giao diện: trang HTML, REST API, ứng dụng di động, tác vụ nền, message consumer hoặc kết nối thời gian thực. Dù điểm vào khác nhau, các quy tắc về ai được phép xem hoặc thay đổi dữ liệu phải được thực thi nhất quán.

Nếu chỉ kiểm tra quyền trong Controller của một trang web, một API hoặc tác vụ khác có thể vô tình bỏ qua kiểm tra đó. Nếu chỉ ẩn nút trên giao diện, người dùng vẫn có thể gửi request trực tiếp. Vì vậy, cần đặt chính sách và điểm thực thi quyền ở những ranh giới phù hợp, để mọi đường gọi đều được bảo vệ.

Bài học này giải thích cách phân chia xác thực và phân quyền, cách đặt kiểm tra quyền trong MVC, cách bảo vệ tài nguyên theo người sở hữu và tenant, cũng như cách kiểm thử quyền trên nhiều loại giao diện.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt authentication (xác thực) và authorization (phân quyền).
- Giải thích vì sao kiểm tra quyền chỉ ở View hoặc Controller là chưa đủ.
- Xác định vị trí thực thi quyền ở tầng HTTP, application service và Domain Model.
- Thiết kế policy theo vai trò, quyền, thuộc tính và ngữ cảnh tài nguyên.
- Bảo vệ dữ liệu theo người sở hữu và tenant để ngăn truy cập chéo.
- Áp dụng method security trong Spring Security khi phù hợp.
- Giữ quy tắc phân quyền nhất quán giữa HTML, API, tác vụ nền và realtime.
- Kiểm thử cả trường hợp được phép lẫn bị từ chối.

## 2. Xác thực và phân quyền là hai việc khác nhau

**Authentication** trả lời câu hỏi: người gọi là ai? Hệ thống có thể xác thực bằng session cookie, mật khẩu, token, chứng thư hoặc một cơ chế danh tính khác.

**Authorization** trả lời câu hỏi: người gọi có được phép thực hiện hành động này trên tài nguyên cụ thể trong ngữ cảnh hiện tại không?

Ví dụ:

- Người dùng đã đăng nhập là một nhân viên.
- Nhân viên có quyền xem đơn hàng được giao cho mình.
- Nhân viên không được xem đơn hàng của bộ phận khác.
- Quản lý có thể duyệt đơn trong phạm vi đơn vị mình phụ trách.
- Chỉ một số người có quyền mới được hủy đơn đã xác nhận.

Đăng nhập thành công không đồng nghĩa với việc được phép truy cập mọi tài nguyên. Một request có danh tính hợp lệ vẫn phải được kiểm tra quyền cho hành động và đối tượng cụ thể.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi? | User ID 42 đã đăng nhập |
| Authorization | Có quyền làm gì? | Có quyền order:read |
| Resource scope | Có quyền trên tài nguyên nào? | Chỉ đơn hàng thuộc user 42 hoặc tenant của họ |
| Business rule | Trạng thái có cho phép hành động không? | Đơn đã giao không thể hủy |

Phân quyền và quy tắc nghiệp vụ có liên quan nhưng không hoàn toàn giống nhau. Quyền có thể cho phép người dùng yêu cầu hủy đơn; Domain Model vẫn cần xác nhận đơn đang ở trạng thái có thể hủy.

## 3. Vì sao không thể chỉ kiểm tra ở giao diện?

Ẩn nút, khóa trường hoặc không hiển thị liên kết có ích cho trải nghiệm. Người dùng không bị hướng đến thao tác mà họ không có quyền. Tuy nhiên, những thay đổi trên giao diện không tạo ra ranh giới bảo mật.

Người dùng có thể:

- Gõ URL trực tiếp.
- Sửa request bằng công cụ của trình duyệt.
- Gọi REST API mà không mở trang HTML.
- Thay ID trong path hoặc query parameter.
- Gửi lại request cũ sau khi quyền đã bị thu hồi.
- Gọi cùng nghiệp vụ từ ứng dụng di động hoặc một client khác.

Vì vậy, máy chủ phải thực thi quyền mỗi khi nhận một yêu cầu cần bảo vệ. View chỉ nên phản ánh quyền để cải thiện trải nghiệm, ví dụ ẩn nút chỉnh sửa hoặc hiển thị thông báo không có quyền.

Một nguyên tắc quan trọng là **deny by default**: nếu không có chính sách rõ ràng cho phép hành động, hệ thống phải từ chối. Không coi việc thiếu thông tin quyền là được phép.

## 4. Các lớp bảo vệ trong ứng dụng MVC

Không có một điểm kiểm tra duy nhất phù hợp cho mọi loại quyền. Một thiết kế tốt thường kết hợp các lớp bảo vệ có mục đích khác nhau.

~~~mermaid
flowchart TD
    Client["HTML / REST API / Mobile / Job / Message"]
    Edge["HTTP Security Filter / Authentication"]
    Controller["Controller / Adapter"]
    App["Application Use Case"]
    Policy["Authorization Policy"]
    Domain["Domain Model"]
    Data["Repository / Database"]

    Client --> Edge
    Edge -->|"Danh tính đã xác thực"| Controller
    Controller --> App
    App --> Policy
    Policy -->|"Cho phép theo ngữ cảnh"| Domain
    App --> Data
    Domain --> App
    App --> Controller
~~~

Các lớp này có trách nhiệm khác nhau:

- **Security filter / HTTP boundary:** xác thực, kiểm tra quyền ở mức URL hoặc endpoint và chặn request không phù hợp trước khi vào Controller.
- **Controller:** chuyển request thành lời gọi ứng dụng; có thể kiểm tra quyền ở mức endpoint hoặc điều phối, nhưng không nên là nơi duy nhất bảo vệ nghiệp vụ.
- **Application service / use case:** kiểm tra người gọi có được phép thực hiện mục tiêu nghiệp vụ trên tài nguyên cụ thể hay không.
- **Authorization policy:** đóng gói quy tắc quyền có thể được dùng chung, nhất là quy tắc phụ thuộc người gọi, tài nguyên và ngữ cảnh.
- **Domain Model:** bảo vệ bất biến và trạng thái hợp lệ của nghiệp vụ; có thể từ chối hành động không hợp lệ dù người gọi có quyền chung.
- **Repository / database:** hỗ trợ truy vấn có phạm vi, tenant isolation và ràng buộc dữ liệu; không thay thế chính sách quyền ở application.

Không phải mọi thao tác đều cần gọi một policy service riêng. Với quy tắc đơn giản, một method security annotation hoặc một điều kiện trong use case có thể đủ. Khi quy tắc được dùng ở nhiều điểm vào hoặc phụ thuộc nhiều thuộc tính, tách policy giúp tránh sao chép và dễ kiểm thử hơn.

## 5. Đặt quyền ở tầng HTTP và Controller

Tầng HTTP phù hợp với những chính sách gắn trực tiếp với endpoint, ví dụ:

- Chỉ người đã đăng nhập mới được truy cập /account/**.
- Chỉ người có quyền quản trị mới được vào /admin/**.
- API quản lý yêu cầu scope orders:write.
- Endpoint công khai chỉ cho phép đọc một số tài nguyên đã công bố.

Spring Security có thể cấu hình quyền theo request matcher:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("order:read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("order:create")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Đây là ví dụ minh họa. Ứng dụng cần cấu hình authentication, CSRF, session hoặc token phù hợp với loại client và threat model của mình.

Request-level authorization có ưu điểm là từ chối sớm, nhất quán và không buộc từng Controller lặp lại điều kiện chung. Tuy nhiên, URL matcher thường chưa đủ thông tin để quyết định quyền trên một bản ghi cụ thể. Ví dụ, order:read không tự động cho phép người dùng xem mọi đơn hàng.

Trong Spring Security, hasRole("ADMIN") thường kiểm tra authority có tiền tố ROLE_ (tức ROLE_ADMIN), còn hasAuthority so sánh authority theo đúng chuỗi được cấu hình. Cần thống nhất cách đặt tên role và permission để tránh kiểm tra nhầm.

Controller có thể dùng method security cho một số action:

~~~java
@PreAuthorize("hasAuthority('order:read')")
@GetMapping("/orders")
public String list(Model model) {
    model.addAttribute("orders", orderQueries.listVisibleToCurrentUser());
    return "orders/list";
}
~~~

Kiểm tra này bảo vệ quyền truy cập chức năng liệt kê. Query vẫn cần giới hạn dữ liệu theo người dùng hoặc tenant nếu người dùng chỉ được xem một phần danh sách.

## 6. Đặt quyền ở Application Service hoặc Use Case

Application service là điểm phù hợp để bảo vệ mục tiêu nghiệp vụ vì nhiều loại giao diện có thể cùng gọi nó.

Ví dụ, hủy đơn hàng có thể được kích hoạt từ:

- Nút trên trang chi tiết đơn.
- REST API của ứng dụng di động.
- Một tác vụ vận hành nội bộ.
- Một workflow được khởi chạy từ hệ thống khác.

Nếu mỗi Controller tự kiểm tra người gọi có phải chủ đơn hay không, các điểm vào có thể triển khai khác nhau. Đặt kiểm tra quyền trong use case giúp mọi adapter phải đi qua cùng quy tắc.

~~~java
public class CancelOrderService implements CancelOrderUseCase {
    private final OrderRepository orders;
    private final OrderAuthorization authorization;
    private final CurrentActor currentActor;

    public CancelOrderService(
            OrderRepository orders,
            OrderAuthorization authorization,
            CurrentActor currentActor) {
        this.orders = orders;
        this.authorization = authorization;
        this.currentActor = currentActor;
    }

    @Override
    public void handle(CancelOrderCommand command) {
        Actor actor = currentActor.requireActor();

        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        authorization.requireCanCancel(actor, order);
        order.cancel();
        orders.save(order);
    }
}
~~~

Các interface CurrentActor, OrderAuthorization, OrderRepository và các kiểu command/domain là ví dụ minh họa. Application không cần biết danh tính được lấy từ session, JWT hay message header; adapter xác thực cung cấp ngữ cảnh actor theo hợp đồng nội bộ.

Application service cần thực hiện kiểm tra quyền trước khi thay đổi trạng thái hoặc ghi dữ liệu. Không nên dựa vào việc Controller đã kiểm tra, vì use case có thể được gọi từ một adapter khác.

### 6.1. Khi nào dùng method security?

Spring Security hỗ trợ method authorization qua các annotation như @PreAuthorize, @PostAuthorize và @Secured khi được bật cấu hình phù hợp.

Ví dụ:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Có thể bảo vệ service:

~~~java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public ReportData loadReport(ReportId id) {
        // Tải dữ liệu báo cáo.
        return reportRepository.load(id);
    }
}
~~~

Method security hữu ích cho các quyền đơn giản và rõ ràng. Với quy tắc phụ thuộc vào chủ sở hữu, tenant, trạng thái hoặc nhiều thuộc tính, có thể gọi policy service trong use case hoặc dùng bean trong biểu thức method security.

Lưu ý rằng method security dựa trên proxy trong cấu hình Spring thông thường. Lời gọi nội bộ giữa các phương thức trong cùng instance có thể không đi qua proxy và không kích hoạt interceptor như một lời gọi từ bean khác. Không nên xem annotation là cơ chế tự động bảo vệ mọi đường gọi; hãy kiểm thử cách service thực sự được gọi.

## 7. Kiểm tra quyền theo tài nguyên (object-level authorization)

Một lỗi phổ biến là chỉ kiểm tra vai trò hoặc authority chung mà quên kiểm tra tài nguyên cụ thể. Đây là nguyên nhân thường gặp của IDOR/BOLA: người dùng thay ID trong request và truy cập dữ liệu của người khác.

Ví dụ endpoint:

~~~text
GET /api/orders/1001
~~~

Người dùng có quyền order:read nhưng đơn 1001 có thể thuộc tài khoản khác. Nếu Controller chỉ kiểm tra authority rồi gọi findById(1001), hệ thống có thể tiết lộ dữ liệu.

Quyền nên được quyết định dựa trên cả actor và tài nguyên:

~~~java
public void requireCanRead(Actor actor, Order order) {
    boolean isOwner = order.customerId().equals(actor.customerId());
    boolean isSupport = actor.hasAuthority("order:support:read");

    if (!isOwner && !isSupport) {
        throw new AuthorizationDeniedException("Not allowed to read this order");
    }
}
~~~

Không nên chỉ dựa vào UUID khó đoán hoặc ID tăng dần để bảo vệ tài nguyên. Định danh không phải cơ chế phân quyền.

### 7.1. Tải tài nguyên trong phạm vi được phép

Một cách hữu ích là giới hạn query ngay từ đầu:

~~~java
public interface OrderRepository {
    Optional<Order> findByIdAndCustomerId(
        OrderId orderId,
        CustomerId customerId
    );
}
~~~

Use case lấy customer ID từ actor đã xác thực rồi truy vấn theo cả hai điều kiện:

~~~java
Order order = orders.findByIdAndCustomerId(
        command.orderId(),
        actor.customerId())
    .orElseThrow(OrderNotFoundException::new);
~~~

Cách này giảm nguy cơ quên kiểm tra chủ sở hữu sau khi tải dữ liệu. Tuy nhiên, nếu có vai trò hỗ trợ hoặc quản trị được phép truy cập ngoài phạm vi chủ sở hữu, cần thiết kế policy và query riêng cho quyền đó.

Tùy chính sách bảo mật, tài nguyên không tồn tại và tài nguyên tồn tại nhưng người gọi không được phép có thể trả cùng HTTP 404 để tránh tiết lộ sự tồn tại. Hoặc hệ thống có thể trả 403 nếu hợp đồng cần phân biệt rõ. Quyết định phải nhất quán và không làm rò rỉ thông tin ngoài ý muốn.

## 8. Quyền theo tenant và phạm vi dữ liệu

Trong hệ thống multi-tenant, cùng một ứng dụng phục vụ nhiều tổ chức hoặc khách hàng. Mọi truy vấn và thao tác cần được giới hạn trong tenant mà actor đang hoạt động.

Ví dụ, actor thuộc tenant A không được xem đơn hàng của tenant B dù có quyền order:read ở tenant A.

Một command có thể chứa định danh tài nguyên nhưng không nên tin tenant ID do client gửi:

~~~java
public record ViewOrderCommand(OrderId orderId) {}
~~~

Application lấy tenant từ ngữ cảnh xác thực:

~~~java
TenantId tenantId = currentActor.requireActor().tenantId();

Order order = orders.findByIdAndTenantId(
        command.orderId(),
        tenantId)
    .orElseThrow(OrderNotFoundException::new);
~~~

Một số biện pháp bảo vệ:

- Lấy tenant từ danh tính hoặc context đã được server xác minh.
- Áp dụng tenant predicate trong query đọc và ghi.
- Kiểm tra tenant khi tham chiếu đối tượng liên quan.
- Không cho phép client tự chọn tenant chỉ bằng query parameter hoặc hidden field.
- Dùng database constraint hoặc row-level security khi phù hợp với kiến trúc.
- Kiểm thử truy cập chéo tenant cho mọi chức năng dữ liệu nhạy cảm.

Không nên chỉ lọc tenant ở màn hình danh sách. Endpoint chi tiết, export, cập nhật, xóa, báo cáo và tác vụ nền đều cần cùng phạm vi dữ liệu.

## 9. Policy: RBAC, ABAC và quyền theo quan hệ

Một ứng dụng có thể dùng một hoặc kết hợp nhiều mô hình phân quyền.

### 9.1. RBAC — quyền dựa trên vai trò

RBAC gán quyền cho vai trò; người dùng được gán một hoặc nhiều vai trò.

Ví dụ:

| Vai trò | Quyền |
|---|---|
| CUSTOMER | order:read-own, order:create, order:cancel-own |
| SUPPORT | order:read, customer:assist |
| MANAGER | order:read-team, order:approve |
| ADMIN | user:manage, policy:manage |

RBAC dễ quản lý khi quyền tương đối ổn định và được gom thành nhóm. Tuy nhiên, role MANAGER không nên tự động có quyền trên mọi đơn hàng; phạm vi team hoặc tenant vẫn cần được kiểm tra.

### 9.2. ABAC — quyền dựa trên thuộc tính

ABAC đánh giá thuộc tính của actor, resource, action và environment.

Ví dụ, quản lý được duyệt đơn khi:

- Actor có vai trò quản lý.
- Đơn thuộc đơn vị mà actor phụ trách.
- Giá trị đơn không vượt hạn mức duyệt của actor.
- Đơn đang ở trạng thái chờ duyệt.
- Thời điểm thao tác nằm trong chính sách cho phép nếu có.

Policy có thể được biểu diễn bằng code:

~~~java
public boolean canApprove(Actor actor, Order order) {
    return actor.hasAuthority("order:approve")
        && actor.departmentId().equals(order.departmentId())
        && order.status() == OrderStatus.PENDING_APPROVAL
        && order.total().compareTo(actor.approvalLimit()) <= 0;
}
~~~

Đây là ví dụ minh họa; chính sách thực tế có thể cần nhiều điều kiện hơn và cần được quản lý tập trung.

### 9.3. Quyền theo quan hệ

Một số hệ thống quyết định quyền dựa trên quan hệ giữa actor và tài nguyên:

- Người tạo hồ sơ có thể sửa hồ sơ khi còn ở trạng thái nháp.
- Thành viên dự án có thể xem tài liệu của dự án.
- Người được giao xử lý ticket có thể cập nhật ticket đó.
- Người quản lý có thể xem các thành viên trong cây tổ chức của mình.

Loại quyền này thường cần truy vấn quan hệ hoặc một policy service. Không nên biến toàn bộ quan hệ thành role tĩnh nếu chúng thay đổi theo tài nguyên.

## 10. Phân biệt quyền chức năng và quy tắc trạng thái

Có quyền thực hiện một loại hành động không có nghĩa hành động luôn hợp lệ.

Ví dụ, người dùng có authority order:cancel nhưng:

- Đơn đã giao.
- Đơn đang hoàn tiền.
- Đơn đã bị hủy.
- Hạn hủy đã qua.

Application policy xác định người gọi có quyền yêu cầu hủy. Domain Model xác định trạng thái đơn có cho phép chuyển sang CANCELLED hay không.

~~~java
public void cancel() {
    if (status != OrderStatus.DRAFT
            && status != OrderStatus.CONFIRMED) {
        throw new OrderStateException(
            "Order cannot be cancelled in its current state"
        );
    }

    status = OrderStatus.CANCELLED;
}
~~~

Cách phân chia này giúp:

- Policy tập trung vào danh tính và phạm vi truy cập.
- Domain tập trung vào bất biến và vòng đời nghiệp vụ.
- Controller chỉ chuyển kết quả thành response phù hợp.

Không đưa quyền HTTP hoặc role của Spring trực tiếp vào Domain Model. Domain có thể nhận một quyết định hoặc dữ liệu cần thiết theo hợp đồng nghiệp vụ, nhưng không nên phụ thuộc Authentication, GrantedAuthority hay Servlet API.

## 11. Bảo vệ nhiều loại giao diện và điểm vào

Một use case có thể được gọi từ nhiều adapter. Tất cả điểm vào cần đi qua cùng chính sách.

| Điểm vào | Kiểm tra ở ranh giới | Kiểm tra nghiệp vụ/tài nguyên |
|---|---|---|
| HTML Controller | Session, endpoint access, CSRF | Use case kiểm tra actor và quyền trên tài nguyên |
| REST API | Token, scope, route access | Use case/policy kiểm tra quyền và tenant |
| Mobile API | Token và quyền endpoint | Cùng use case và policy như web |
| Scheduled job | Danh tính service hoặc quyền hệ thống | Use case nhận actor hệ thống với quyền tối thiểu |
| Message consumer | Xác minh nguồn message và service identity | Kiểm tra tenant, resource và quyền của tác nhân phát sinh |
| WebSocket/STOMP | Xác thực kết nối và quyền destination | Kiểm tra quyền trên từng subscription hoặc message nhạy cảm |
| CLI/admin tool | Xác thực và quyền thao tác | Gọi cùng application service |

Không nên giả định request đến từ tác vụ nền hoặc message broker là đáng tin cậy. Các adapter này cần danh tính hệ thống hoặc actor rõ ràng, quyền tối thiểu và kiểm tra phạm vi dữ liệu.

Với một số tác vụ hệ thống, có thể không có người dùng cuối. Khi đó, use case nên nhận actor loại service/system với quyền được xác định rõ, thay vì bỏ qua mọi kiểm tra bằng cách truyền null hoặc một cờ isAdmin tùy tiện.

### 11.1. Dùng cùng use case, nhưng giữ ngữ cảnh actor

Ví dụ hai Controller có thể cùng gọi một use case:

~~~java
@PostMapping("/orders/{id}/cancel")
public String cancelFromWeb(@PathVariable UUID id) {
    cancelOrder.handle(new CancelOrderCommand(new OrderId(id)));
    return "redirect:/orders";
}
~~~

~~~java
@PostMapping("/api/orders/{id}/cancel")
public ResponseEntity<Void> cancelFromApi(@PathVariable UUID id) {
    cancelOrder.handle(new CancelOrderCommand(new OrderId(id)));
    return ResponseEntity.noContent().build();
}
~~~

Cả hai adapter gọi cùng application service. Actor được cung cấp thông qua một abstraction lấy từ security context đã xác thực hoặc được truyền tường minh trong command/context. Cách truyền nào phù hợp tùy hệ thống, nhưng phải tránh việc một điểm vào vô tình bỏ qua actor hoặc sử dụng actor giả.

## 12. Truy vấn và phân quyền phải nhất quán

Phân quyền không chỉ áp dụng cho lệnh ghi. Query cũng có thể tiết lộ dữ liệu nhạy cảm.

Các chức năng cần xem xét:

- Danh sách và tìm kiếm.
- Chi tiết một bản ghi.
- Export CSV/PDF.
- Báo cáo và dashboard.
- Autocomplete hoặc lookup.
- Download file đính kèm.
- Lịch sử và audit log.

Ví dụ, một trang danh sách đã lọc theo tenant nhưng endpoint export lại gọi query không có tenant predicate. Người dùng có thể tải dữ liệu ngoài phạm vi dù không thấy chúng trên giao diện.

Nên định nghĩa query theo phạm vi rõ ràng:

~~~java
public interface OrderQueries {
    PageResult<OrderSummary> searchVisibleTo(
        ActorId actorId,
        TenantId tenantId,
        OrderSearchCriteria criteria
    );
}
~~~

Tùy kiến trúc, query service có thể gọi policy trước, dùng repository query theo scope, hoặc kết hợp cả hai. Cần bảo đảm bộ lọc không thể bị client ghi đè bằng một tenant ID khác.

Đối với dữ liệu có nhiều cấp quyền, không nên chỉ lọc bằng một cột owner nếu chính sách còn phụ thuộc team, vai trò hỗ trợ, trạng thái hoặc quan hệ chia sẻ. Hãy mô hình hóa policy rõ ràng và kiểm thử theo ma trận quyền.

## 13. Quyền và giao dịch: tránh TOCTOU

TOCTOU (time-of-check to time-of-use) xảy ra khi điều kiện được kiểm tra ở một thời điểm nhưng trạng thái thay đổi trước lúc thao tác thực sự diễn ra.

Ví dụ:

1. Use case kiểm tra người dùng là chủ đơn.
2. Quyền sở hữu hoặc trạng thái phân công thay đổi bởi request khác.
3. Use case tiếp tục cập nhật theo dữ liệu cũ.

Với thao tác nhạy cảm, kiểm tra quyền và cập nhật cần nằm trong một ranh giới nhất quán phù hợp. Tùy hệ thống, có thể dùng:

- Transaction bao quanh việc đọc, kiểm tra và ghi.
- Optimistic locking để phát hiện version thay đổi.
- Pessimistic locking khi cần khóa tài nguyên trong thời gian ngắn.
- Query cập nhật có điều kiện theo owner/tenant/version.
- Constraint ở database để bảo vệ bất biến quan trọng.

Transaction không tự giải quyết mọi TOCTOU nếu dữ liệu quyền hoặc trạng thái nằm ở hệ thống khác. Cần xác định nguồn sự thật và chiến lược nhất quán phù hợp.

## 14. Ánh xạ lỗi phân quyền thành response

Khi quyền bị từ chối, phản hồi cần phù hợp với loại client và không làm lộ thông tin.

| Tình huống | HTTP thường dùng | Ý nghĩa |
|---|---|---|
| Chưa xác thực | 401 Unauthorized hoặc redirect đăng nhập cho web session | Cần xác thực |
| Đã xác thực nhưng không có quyền | 403 Forbidden | Không được phép thực hiện |
| Tài nguyên không tồn tại hoặc được ẩn theo chính sách | 404 Not Found | Không công bố tài nguyên |
| Request xung đột với trạng thái hiện tại | 409 Conflict | Cần làm mới hoặc xử lý trạng thái |

Không nên trả stack trace hoặc thông tin policy nội bộ. Với HTML, có thể hiển thị trang không có quyền hoặc trang không tìm thấy. Với API, trả error code ổn định và message phù hợp hợp đồng.

Không nên biến mọi lỗi thành 403. Một lỗi validation, lỗi trạng thái nghiệp vụ hoặc lỗi hệ thống cần được phân loại riêng để client biết phải làm gì tiếp theo.

## 15. Thiết kế policy có thể tái sử dụng

Khi nhiều use case dùng chung một quy tắc, hãy tách policy để tránh sao chép điều kiện.

~~~java
public interface OrderAuthorization {
    void requireCanRead(Actor actor, Order order);
    void requireCanCancel(Actor actor, Order order);
    void requireCanApprove(Actor actor, Order order);
}
~~~

Implementation:

~~~java
public class DefaultOrderAuthorization implements OrderAuthorization {

    @Override
    public void requireCanRead(Actor actor, Order order) {
        if (actor.isAdministrator()) {
            return;
        }

        if (!actor.customerId().equals(order.customerId())) {
            throw new AuthorizationDeniedException("Not allowed");
        }
    }

    @Override
    public void requireCanCancel(Actor actor, Order order) {
        if (actor.isAdministrator()) {
            return;
        }

        boolean isOwner = actor.customerId().equals(order.customerId());
        boolean hasCancelPermission =
            actor.hasAuthority("order:cancel");

        if (!isOwner || !hasCancelPermission) {
            throw new AuthorizationDeniedException("Not allowed");
        }
    }

    @Override
    public void requireCanApprove(Actor actor, Order order) {
        boolean hasPermission = actor.hasAuthority("order:approve");
        boolean sameDepartment =
            actor.departmentId().equals(order.departmentId());

        if (!hasPermission || !sameDepartment) {
            throw new AuthorizationDeniedException("Not allowed");
        }
    }
}
~~~

Trong ví dụ, AuthorizationDeniedException là exception thuộc application do dự án định nghĩa:

~~~java
public final class AuthorizationDeniedException extends RuntimeException {
    public AuthorizationDeniedException(String message) {
        super(message);
    }
}
~~~

Adapter web ánh xạ exception này thành 403 hoặc phản hồi ẩn tài nguyên theo chính sách. Không nên để Domain hoặc Application phụ thuộc trực tiếp Spring Security nếu mục tiêu là giữ chúng độc lập.

### 15.1. Tránh policy quá tổng quát

Một phương thức như hasAccess(actor, resource, action) có thể hữu ích nếu hệ thống có policy engine rõ ràng. Nhưng nếu mọi quy tắc đều bị ép vào một chuỗi action hoặc switch lớn, code sẽ khó hiểu.

Ưu tiên tên phương thức theo ngôn ngữ nghiệp vụ như requireCanCancel, requireCanApprove hoặc canViewSensitiveReport. Chỉ xây policy engine tổng quát khi số lượng quy tắc và nhu cầu quản trị thực sự cần thiết.

### 15.2. Quyền thay đổi theo thời gian

Quyền có thể bị thu hồi hoặc thay đổi khi:

- Người dùng rời nhóm.
- Vai trò bị gỡ.
- Tài nguyên chuyển chủ sở hữu.
- Hợp đồng hoặc thời hạn truy cập hết hiệu lực.
- Tenant bị khóa.

Không nên cache quyền vô thời hạn. Nếu cache authorization decision, cần xác định TTL, cách invalidation và mức chấp nhận độ trễ khi quyền bị thu hồi.

## 16. Kiểm thử phân quyền

Kiểm thử cần chứng minh cả đường được phép và đường bị từ chối. Một test chỉ xác nhận người quản trị truy cập thành công không chứng minh người dùng thường bị chặn đúng.

### 16.1. Unit test cho policy

Ví dụ:

~~~java
@Test
void ownerCanReadOwnOrder() {
    Actor owner = actorForCustomer("customer-1");
    Order order = orderForCustomer("customer-1");

    assertDoesNotThrow(
        () -> authorization.requireCanRead(owner, order)
    );
}

@Test
void differentCustomerCannotReadOrder() {
    Actor other = actorForCustomer("customer-2");
    Order order = orderForCustomer("customer-1");

    assertThrows(
        AuthorizationDeniedException.class,
        () -> authorization.requireCanRead(other, order)
    );
}
~~~

Các helper là fixture của test. Nên bổ sung trường hợp admin, support, tenant khác, trạng thái khác nhau và quyền bị thu hồi.

### 16.2. Test application service

Dùng fake repository và actor để xác nhận:

- Use case gọi policy trước khi thay đổi trạng thái.
- Người không có quyền không thể làm thay đổi dữ liệu.
- Query được giới hạn theo actor hoặc tenant.
- Không gọi repository save khi policy từ chối.
- Quy tắc trạng thái của Domain vẫn được thực thi sau khi policy cho phép.

### 16.3. Test HTTP và Controller

Với Spring Security và MockMvc, kiểm tra:

- Người chưa xác thực nhận 401 hoặc redirect theo cấu hình.
- Người đã xác thực nhưng thiếu authority nhận 403.
- Người có authority chung nhưng không sở hữu tài nguyên không đọc được tài nguyên đó.
- Người dùng tenant A không đọc hoặc sửa được tài nguyên tenant B.
- Endpoint HTML và API áp dụng chính sách tương đương.
- CSRF được yêu cầu cho các request thay đổi trạng thái khi dùng session/cookie.

Ví dụ khái quát:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .with(user("customer-2").authorities(
            new SimpleGrantedAuthority("order:read")
        )))
    .andExpect(status().isForbidden());
~~~

Test này chỉ kiểm tra một trường hợp authority có nhưng actor không có quyền trên tài nguyên. Cấu hình test thực tế cần phù hợp cách ứng dụng xác thực và cách policy tải actor.

### 16.4. Test mọi điểm vào

Nếu một use case được gọi từ REST, web, job và message consumer, hãy kiểm tra từng adapter hoặc chứng minh chúng đều gọi cùng một use case có enforcement. Đặc biệt kiểm tra các luồng nội bộ có thể gọi service mà không đi qua HTTP security filter.

### 16.5. Ma trận quyền

Một ma trận đơn giản giúp phát hiện trường hợp bị bỏ sót:

| Actor | Xem đơn của mình | Xem đơn người khác | Hủy đơn của mình | Duyệt đơn |
|---|---:|---:|---:|---:|
| Customer | Có | Không | Theo trạng thái | Không |
| Support | Theo phạm vi hỗ trợ | Theo phạm vi hỗ trợ | Theo chính sách | Không |
| Manager | Theo team | Theo team | Theo chính sách | Theo hạn mức |
| Admin | Có | Có | Theo chính sách | Theo chính sách |

Ma trận cần được cụ thể hóa bằng tenant, trạng thái, quan hệ và giới hạn dữ liệu của hệ thống thực tế.

## 17. Những lỗi thiết kế thường gặp

### Chỉ ẩn nút hoặc menu

Ẩn nút không chặn request trực tiếp. Máy chủ vẫn phải kiểm tra quyền ở endpoint và application service.

### Chỉ kiểm tra role chung

Có role USER hoặc authority order:read không có nghĩa được đọc mọi đơn. Cần kiểm tra owner, tenant, team hoặc quan hệ với tài nguyên.

### Chỉ kiểm tra trong Controller

Một use case có thể được gọi từ API khác, job hoặc message consumer. Đặt enforcement quan trọng trong application service hoặc policy mà mọi điểm vào phải sử dụng.

### Tin tenant ID hoặc owner ID từ client

Client có thể sửa path, query parameter hoặc hidden field. Lấy scope từ danh tính đã xác thực và kiểm tra lại tham chiếu tài nguyên ở server.

### Trộn quyền với trạng thái nghiệp vụ

Người dùng có quyền hủy không có nghĩa đơn ở trạng thái có thể hủy. Policy và Domain Model cần kiểm tra hai điều kiện riêng.

### Dùng một tài khoản hệ thống có toàn quyền cho mọi job

Tác vụ nền cần quyền tối thiểu theo chức năng. Ghi rõ actor hệ thống, tenant scope và hành động được phép.

### Dùng method security nhưng không kiểm tra đường gọi

Proxy, self-invocation và cấu hình method security có thể ảnh hưởng việc annotation được thực thi. Kiểm thử bằng lời gọi thực tế từ bean khác và không dựa vào annotation như một giả định.

### Cache quyền quá lâu

Quyền bị thu hồi nhưng cache chưa hết hạn có thể tạo cửa sổ truy cập ngoài ý muốn. Xác định chính sách invalidation và TTL.

### Chỉ kiểm thử trường hợp thành công

Cần test truy cập chéo người dùng, tenant, vai trò, trạng thái và các adapter khác nhau. Đường bị từ chối cũng là một phần của hợp đồng bảo mật.

## 18. Quy trình thiết kế vị trí kiểm tra quyền

Khi thêm một chức năng MVC, hãy thực hiện theo trình tự:

1. **Xác định actor.** Người dùng, service account hay hệ thống nội bộ?
2. **Xác định action và resource.** Ai muốn làm gì trên đối tượng nào?
3. **Xác định scope.** Theo owner, tenant, team, quan hệ hoặc phạm vi dữ liệu nào?
4. **Đặt kiểm tra ở HTTP boundary.** Chặn sớm endpoint cần xác thực hoặc authority chung.
5. **Đặt enforcement trong use case.** Bảo đảm mọi adapter gọi cùng nghiệp vụ đều được kiểm tra.
6. **Tách policy dùng chung.** Dùng policy/service khi quy tắc có nhiều thuộc tính hoặc được tái sử dụng.
7. **Bảo vệ bất biến trong Domain.** Kiểm tra trạng thái và điều kiện nghiệp vụ trước khi thay đổi.
8. **Giới hạn query theo scope.** Áp dụng owner/tenant predicate cho đọc, ghi, export và download.
9. **Xem xét đồng thời và cache.** Xử lý TOCTOU, version và thu hồi quyền.
10. **Kiểm thử cả allow và deny.** Bao phủ HTML, API, job, message và realtime khi có.

Trước khi hoàn thành, hãy tự hỏi:

- Nếu bỏ qua giao diện, server có còn từ chối request trái phép không?
- Một API hoặc job khác có thể gọi cùng use case mà bỏ qua policy không?
- Người có quyền chung có thể truy cập tài nguyên của người khác không?
- Tenant ID được lấy từ nguồn nào?
- Query danh sách, chi tiết, export và download có cùng scope không?
- Quyền và trạng thái nghiệp vụ có được kiểm tra riêng không?
- Quyền bị thu hồi có hiệu lực trong thời gian phù hợp không?
- Có test cho cả người được phép và người bị từ chối ở từng điểm vào không?

## 19. Kết luận

Trong ứng dụng MVC, kiểm tra quyền cần được đặt ở nhiều ranh giới với mục đích rõ ràng. HTTP security bảo vệ endpoint và xác thực request; application service hoặc policy bảo vệ mục tiêu nghiệp vụ trên tài nguyên cụ thể; Domain Model bảo vệ trạng thái và bất biến; repository query giúp giới hạn dữ liệu theo owner hoặc tenant.

View có thể ẩn thao tác không được phép để cải thiện trải nghiệm, nhưng quyết định bảo mật luôn phải được thực thi ở phía server. Khi mọi loại giao diện cùng đi qua chính sách application nhất quán, hệ thống giảm nguy cơ bỏ sót kiểm tra ở API, tác vụ nền, message consumer hoặc kết nối realtime. Kết hợp kiểm thử quyền theo actor, action, resource và scope giúp MVC bảo vệ dữ liệu mà vẫn giữ được ranh giới trách nhiệm rõ ràng.

