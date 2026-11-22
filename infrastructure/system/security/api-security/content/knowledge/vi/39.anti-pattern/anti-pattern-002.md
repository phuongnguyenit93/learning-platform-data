# Dùng ID tuần tự và không kiểm tra object authorization

Một API thường nhận object ID trong path, query hoặc request body để đọc, sửa, xóa hay thực hiện một hành động nghiệp vụ. Nếu server chỉ kiểm tra người gọi đã đăng nhập rồi tải object theo ID và trả kết quả, caller có thể thay ID của chính mình bằng ID của người khác để truy cập dữ liệu ngoài quyền. Đây là lỗi Broken Object Level Authorization (BOLA), thường được gọi là IDOR (Insecure Direct Object Reference).

ID tuần tự như 1001, 1002, 1003 khiến việc đoán và duyệt object dễ hơn, vì attacker có thể thử các giá trị lân cận hoặc tăng dần. Nhưng nguyên nhân bảo mật cốt lõi là server không kiểm tra caller có quyền trên object cụ thể hay không. Chuyển sang UUID ngẫu nhiên, ULID hoặc ID khó đoán chỉ giảm khả năng enumeration; nó không cấp quyền và không thay thế object authorization.

**Mỗi lần truy cập object phải kiểm tra quyền ở phía server theo actor, object, action và ngữ cảnh tenant/quan hệ.** Việc kiểm tra cần áp dụng cho read, update, delete, export, download, nested resource, batch request, GraphQL resolver và background job. Authentication trả lời “ai đang gọi”; object authorization trả lời “người đó được làm gì trên object này”.

## 1. ID tuần tự và object authorization là hai vấn đề khác nhau

ID tuần tự là cách cấp định danh dễ dự đoán, thường đến từ auto-increment database hoặc bộ đếm. Ví dụ:

~~~text
/api/v1/invoices/1001
/api/v1/invoices/1002
/api/v1/invoices/1003
~~~

Nếu một user đọc được invoice 1001, họ có thể thử 1002, 1003 hoặc một khoảng ID khác. Khi API trả dữ liệu mà không kiểm tra quyền, việc đoán ID trở thành con đường truy cập object của người khác.

Hai khái niệm cần tách biệt:

| Khái niệm | Ý nghĩa | Vai trò bảo mật |
|---|---|---|
| Identifier | Giá trị dùng để tham chiếu object | Giúp server tìm object |
| Object authorization | Quyết định actor có được thực hiện action trên object hay không | Ngăn truy cập trái phép |

ID không phải credential, capability hay bằng chứng sở hữu. Một ID ngẫu nhiên vẫn có thể bị lộ qua URL, log, email, browser history, referrer, analytics hoặc response của endpoint khác. Nếu server không kiểm tra quyền, attacker chỉ cần có được ID bằng bất kỳ cách nào.

## 2. Vì sao ID tuần tự làm rủi ro lớn hơn?

ID tuần tự có thể làm lộ hoặc hỗ trợ suy luận:

- Object có tồn tại hay không qua response khác nhau.
- Số lượng object gần đúng hoặc tốc độ tạo object.
- Thứ tự tạo record và hoạt động của tenant khác.
- Khả năng tìm object kế tiếp bằng cách tăng/giảm ID.
- Những endpoint nào có thể được crawl tự động.

Attacker có thể tự động hóa request, thay ID theo dãy và thu thập dữ liệu nếu endpoint có BOLA. Ngay cả khi server trả 404 cho ID không tồn tại và 403 cho object bị cấm, sự khác biệt vẫn có thể hỗ trợ enumeration.

Tuy nhiên, ID tuần tự không tự tạo ra BOLA. Nếu server luôn kiểm tra object authorization đúng, việc attacker biết ID của object khác không giúp họ đọc hoặc thay đổi object đó. Ngược lại, UUID khó đoán không cứu được API nếu một endpoint vẫn trả object cho bất kỳ ai có ID.

## 3. Anti-pattern: chỉ xác thực rồi tìm object theo ID

Ví dụ không an toàn:

~~~java
@GetMapping("/api/v1/orders/{orderId}")
public OrderEntity getOrder(@PathVariable Long orderId) {
    return orderRepository.findById(orderId)
        .orElseThrow(() -> new NotFoundException());
}
~~~

Nếu endpoint được bảo vệ bằng login, server mới chỉ biết caller đã xác thực. Đoạn code không kiểm tra order thuộc user/tenant nào, caller có membership hay được chia sẻ object hay không. Trả JPA entity trực tiếp còn có thể làm lộ thêm field và quan hệ nội bộ.

Một biến thể cũng nguy hiểm:

~~~java
if (jwt != null) {
    return orderRepository.findById(orderId).orElseThrow();
}
~~~

Điều kiện “có JWT” chỉ là authentication. Nó không chứng minh JWT subject sở hữu order hoặc có quyền đọc order.

## 4. Anti-pattern: kiểm tra quyền ở giao diện người dùng

Ẩn nút Edit, không hiển thị link hoặc chỉ gửi ID từ danh sách được lọc không phải là authorization. Attacker có thể:

- Gọi API trực tiếp bằng curl, Postman hoặc script.
- Sửa path/query/body trong browser developer tools.
- Dùng ID lấy từ email, log, file export hoặc endpoint khác.
- Gọi endpoint bằng một client tự viết không có giao diện của ứng dụng.

Frontend có thể ẩn chức năng để cải thiện trải nghiệm, nhưng server phải kiểm tra quyền mỗi lần nhận request. Không dựa vào việc client “không có nút” hoặc “không biết ID”.

## 5. Những vị trí ID có thể xuất hiện

Không chỉ path parameter mới cần kiểm tra object authorization:

| Vị trí | Ví dụ | Điều cần xác minh |
|---|---|---|
| Path | /orders/1001 | Actor được đọc/thay đổi order 1001? |
| Query | ?invoiceId=1001 | Invoice có thuộc scope của actor? |
| Request body | { "ownerId": 1001 } | Caller có quyền chọn owner đó? |
| Header | X-Account-ID: 1001 | Giá trị có được xác minh và caller có membership? |
| Nested object | /orders/1001/items/55 | Item 55 có thực sự thuộc order 1001? |
| Batch | { "ids": [1001, 1002, 1003] } | Caller có quyền trên từng object? |
| GraphQL | node(id: "...") | Resolver có kiểm tra quyền cho node/action? |
| File/object storage | /download/1001 hoặc storage key | Caller có quyền tải đúng file? |
| Async job | /exports/1001 | Người gọi có quyền xem kết quả job và dữ liệu nguồn? |

Hãy lập inventory các endpoint nhận object reference và kiểm tra mọi đường truy cập tới object, kể cả endpoint nội bộ hoặc luồng bất đồng bộ.

## 6. Nguyên tắc kiểm tra object authorization

Một quyết định authorization nên dựa trên:

- **Actor:** user, service principal hoặc workload đã xác thực.
- **Action:** read, create, update, delete, approve, export, share hoặc hành động cụ thể.
- **Object:** resource thực tế được tải từ nguồn dữ liệu đáng tin cậy.
- **Relationship:** owner, member, collaborator, assignee, project role hoặc ACL.
- **Tenant context:** tenant đã được server xác minh cho request.
- **Environment/context:** trạng thái object, purpose, delegation, thời hạn và điều kiện nghiệp vụ.

Không nên chỉ hỏi actor có role ADMIN hay không. Một role rộng có thể cho phép thao tác không phù hợp trên mọi object. Cần kiểm tra quan hệ giữa actor và object, cùng action cụ thể.

Quy tắc nên deny by default: nếu không có policy/grant rõ ràng cho action trên object, từ chối. Không suy luận “được phép” chỉ vì không tìm thấy rule từ chối.

## 7. Không tin object ID, user ID hoặc tenant ID do client khai báo

Client có thể gửi ID để chọn tài nguyên, nhưng server phải xác minh:

- ID có đúng định dạng và loại resource dự kiến không?
- Object có tồn tại trong phạm vi truy cập của actor không?
- Object thuộc tenant nào theo metadata thực tế?
- Actor có membership/relationship/grant phù hợp không?
- Action hiện tại có được phép trên trạng thái hiện tại không?

Không lấy ownerId, createdBy, tenantId hoặc role từ request body để quyết định quyền. Những giá trị này phải đến từ principal đã xác thực, tenant context đã resolve hoặc dữ liệu domain đáng tin cậy.

Nếu API có path dạng /tenants/{tenantId}/orders/{orderId}, tenantId trong path chỉ là tenant selector. Server cần xác minh actor là member hoặc được delegate vào tenant đó, rồi mới tạo tenant context. Không dùng path tenant làm bằng chứng membership.

## 8. Scope truy vấn theo tenant và object

Với resource chỉ thuộc một tenant, có thể giới hạn ngay tại repository query:

~~~java
public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Optional<OrderEntity> findByIdAndTenantId(
        UUID orderId,
        UUID tenantId
    );
}
~~~

Service dùng tenant context đã xác minh:

~~~java
OrderEntity order = orderRepository
    .findByIdAndTenantId(orderId, tenantContext.requireTenantId())
    .orElseThrow(ResourceNotFoundException::new);
~~~

Query có tenant predicate giúp object ngoài tenant không được tải qua đường truy cập thông thường. Cách này giảm nguy cơ quên kiểm tra tenant ở controller và hạn chế khác biệt response giữa object không tồn tại và object thuộc tenant khác.

Tenant scope không thay thế mọi object-level policy. Trong cùng một tenant, user A có thể được phép xem project A nhưng không được xem project B. Sau khi tải resource trong scope hợp lệ, service vẫn cần kiểm tra owner, membership, ACL hoặc relationship theo nghiệp vụ.

Với resource được chia sẻ giữa tenant, dùng query/policy thể hiện grant đã xác minh. Không mở rộng thành findById không giới hạn chỉ để hỗ trợ chia sẻ.

## 9. Kiểm tra quyền theo quan hệ thay vì chỉ role

Ví dụ một project có owner, member và viewer:

| Quan hệ | Read | Update | Delete | Manage members |
|---|---:|---:|---:|---:|
| Owner | Có | Có | Có | Có |
| Editor | Có | Có trong scope | Không | Không |
| Viewer | Có | Không | Không | Không |
| Không có membership | Không | Không | Không | Không |

Role có thể là một phần policy, nhưng cần xác định role đó gắn với tenant, project hay toàn hệ thống. Một user là ADMIN của tenant A không tự động trở thành ADMIN của tenant B.

Ví dụ policy:

~~~java
public void requireCanRead(Actor actor, Project project) {
    boolean sameTenant = actor.tenantId().equals(project.tenantId());
    boolean owner = project.ownerId().equals(actor.userId());
    boolean member = membershipRepository
        .existsByProjectIdAndUserId(project.getId(), actor.userId());
    boolean publicRead = project.isPublic();
    boolean allowed = publicRead || (sameTenant && (owner || member));

    if (!allowed) {
        throw new AccessDeniedException("Access denied");
    }
}
~~~

Đây chỉ là ví dụ đơn giản cho action read. Public read có thể cho phép đọc từ tenant khác nếu policy công khai quy định như vậy; owner/member chỉ được xét trong tenant đã xác minh. Với update/delete, phải có policy riêng. Không để public read kéo theo quyền sửa/xóa hoặc lộ field nội bộ.

## 10. Kiểm tra action riêng cho từng thao tác

Quyền đọc không tự động bao gồm quyền sửa, xóa, approve hoặc export:

| Action | Ví dụ policy cần kiểm tra |
|---|---|
| Read | Có thể xem object và các property được trả? |
| Update | Có thể sửa các field cụ thể trong trạng thái hiện tại? |
| Delete | Có quyền xóa và object có đang được bảo vệ/khóa không? |
| Approve | Có role/relationship và điều kiện phân tách nhiệm vụ không? |
| Export | Có quyền lấy tập dữ liệu và khối lượng export không? |
| Share | Có quyền cấp quyền cho principal khác không? |
| Download | Có quyền lấy file gắn với object không? |

Một endpoint dùng chung /orders/{id} cho nhiều method phải kiểm tra policy theo method/action. Không dùng một check “canAccessOrder” quá chung nếu các hành động có rủi ro khác nhau.

## 11. Ví dụ Spring Boot: kiểm tra trước khi trả object

Một service có thể kết hợp tenant-scoped lookup và object policy:

~~~java
@Service
public class OrderQueryService {
    private final OrderRepository orders;
    private final TenantContext tenantContext;
    private final OrderAuthorization authorization;
    private final OrderMapper mapper;

    public OrderQueryService(
            OrderRepository orders,
            TenantContext tenantContext,
            OrderAuthorization authorization,
            OrderMapper mapper) {
        this.orders = orders;
        this.tenantContext = tenantContext;
        this.authorization = authorization;
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    public OrderResponse get(UUID orderId, Actor actor) {
        UUID tenantId = tenantContext.requireTenantId();
        OrderEntity order = orders
            .findByIdAndTenantId(orderId, tenantId)
            .orElseThrow(ResourceNotFoundException::new);

        authorization.requireCanRead(actor, order);
        return mapper.toResponse(order);
    }
}
~~~

Controller nhận actor từ security context:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderQueryService service;
    private final ActorFactory actorFactory;

    public OrderController(
            OrderQueryService service,
            ActorFactory actorFactory) {
        this.service = service;
        this.actorFactory = actorFactory;
    }

    @GetMapping("/{orderId}")
    public OrderResponse get(
            @PathVariable UUID orderId,
            @AuthenticationPrincipal Jwt jwt) {
        Actor actor = actorFactory.fromAuthenticatedJwt(jwt);
        return service.get(orderId, actor);
    }
}
~~~

Ví dụ minh họa, cần bổ sung import, cấu hình security và implementation cho các abstraction. ActorFactory phải lấy subject từ JWT đã được Spring Security xác minh; TenantContext phải được tạo sau khi xác minh membership. Với resource có sharing/delegation, repository và authorization policy cần hỗ trợ grant tương ứng.

Điểm quan trọng là controller không tự quyết định quyền bằng cách so sánh ID do client gửi. Service tải resource đúng scope, kiểm tra policy trên object thực tế rồi mới map response.

## 12. Không chỉ kiểm tra ở controller

Controller là một điểm vào, nhưng service có thể được gọi từ:

- REST controller khác.
- GraphQL resolver.
- Message consumer.
- Scheduled job.
- Admin tool.
- Service-to-service endpoint.
- Batch import/export.

Nếu object authorization chỉ nằm trong một controller, một đường gọi khác có thể bỏ qua nó. Đặt policy tại application service/domain boundary dùng chung, hoặc tạo authorization component bắt buộc được gọi trước khi thao tác. Có thể bổ sung method security, nhưng cần bảo đảm mọi entry point đi qua method được bảo vệ.

Annotation như @PreAuthorize("hasAuthority('order:read')") thường kiểm tra quyền chức năng. Nó chưa chắc kiểm tra actor có quyền trên orderId cụ thể. Có thể dùng expression gọi bean authorization theo object ID, nhưng bean phải resolve resource an toàn, kiểm tra đúng action và không dựa trên dữ liệu client chưa xác minh.

## 13. Danh sách object phải được lọc trước khi phân trang

Một endpoint list có thể không nhận ID cụ thể nhưng vẫn làm lộ object:

~~~java
Page<OrderEntity> findAll(Pageable pageable);
~~~

Nếu query không scope theo tenant/membership, user có thể nhận object của người khác qua trang danh sách. Lọc ở frontend sau khi server đã trả dữ liệu là quá muộn.

Query phải áp dụng authorization scope trước pagination và aggregation:

~~~sql
SELECT o.id, o.reference, o.status
FROM orders o
WHERE o.tenant_id = :verified_tenant_id
  AND EXISTS (
      SELECT 1
      FROM project_memberships pm
      WHERE pm.project_id = o.project_id
        AND pm.user_id = :authenticated_user_id
  )
ORDER BY o.created_at DESC
LIMIT :page_size OFFSET :offset;
~~~

Nếu policy phức tạp, có thể tạo repository query/projection riêng hoặc authorization-aware query service. Đừng lấy toàn bộ dữ liệu rồi filter trong Java sau khi đã tiêu thụ bộ nhớ và có nguy cơ log/serialize nhầm.

Counts, facets, autocomplete, search suggestions và export cũng cần cùng authorization scope. Tổng số object hoặc tên project cũng có thể là thông tin nhạy cảm.

## 14. Nested resource phải kiểm tra quan hệ cha-con

Ví dụ endpoint:

~~~text
GET /api/v1/orders/{orderId}/items/{itemId}
~~~

Server cần xác minh:

1. Actor có quyền trên order không?
2. Item có thực sự thuộc order đó không?
3. Actor có quyền trên action đọc item không?

Không chỉ kiểm tra itemId tồn tại. Nếu item 55 thuộc order 200 nhưng caller gửi orderId 100 và itemId 55, API không được trả item chỉ vì item ID hợp lệ.

Repository có thể query cả hai điều kiện:

~~~java
Optional<OrderItemEntity> findByIdAndOrderId(
    UUID itemId,
    UUID orderId
);
~~~

Sau đó kiểm tra quyền trên parent order và action cụ thể. Với nested resource nhiều cấp, mỗi quan hệ quan trọng cần được xác minh theo domain model; không tin path hierarchy do client tự ghép.

## 15. Batch API phải authorize từng object

Một endpoint batch như:

~~~json
{
  "orderIds": ["1001", "1002", "1003"]
}
~~~

không được kiểm tra quyền trên object đầu tiên rồi xử lý tất cả. Mỗi object có thể thuộc tenant hoặc owner khác nhau.

Thiết kế an toàn:

- Giới hạn số ID mỗi batch và loại bỏ duplicate.
- Resolve tất cả object trong scope actor được phép.
- Kiểm tra action trên từng object.
- Xác định rõ semantics all-or-nothing hay partial success.
- Không trả chi tiết về object ngoài quyền nếu threat model yêu cầu che existence.
- Ghi audit cho thao tác hàng loạt và số object thành công/thất bại.
- Chống batch endpoint trở thành cách bypass rate limit hoặc enumeration.

Với thao tác nhạy cảm như chuyển tiền, xóa hàng loạt hoặc đổi quyền, thường nên dùng all-or-nothing transaction hoặc workflow có preview/approval rõ ràng. Nếu partial success được phép, response chỉ tiết lộ thông tin trong phạm vi caller có quyền.

## 16. Không tin owner/tenant trong request khi cập nhật

Ví dụ không an toàn:

~~~java
@PatchMapping("/api/v1/documents/{id}")
public DocumentEntity update(
        @PathVariable UUID id,
        @RequestBody DocumentEntity body) {
    DocumentEntity entity = repository.findById(id).orElseThrow();
    BeanUtils.copyProperties(body, entity);
    return repository.save(entity);
}
~~~

Client có thể thử thay ownerId, tenantId, createdBy hoặc visibility. Đây vừa là mass assignment vừa có thể làm hỏng object authorization về sau.

Dùng request DTO chỉ chứa field được phép sửa:

~~~java
public record UpdateDocumentRequest(
    @NotBlank @Size(max = 120) String title,
    @Size(max = 2000) String description
) {}
~~~

Service tải object, kiểm tra quyền update rồi map tường minh các field title/description. Owner, tenant, audit field và ACL được quản lý bằng use case riêng với permission cụ thể.

## 17. Kiểm tra property-level authorization

Có quyền đọc object không có nghĩa được đọc mọi field. Một user có thể xem thông tin đơn hàng nhưng không được xem internal risk note, payment token reference hoặc thông tin cá nhân của người khác.

Có quyền update object cũng không có nghĩa được cập nhật mọi thuộc tính. Ví dụ:

- User được sửa địa chỉ giao hàng nhưng không được sửa giá.
- Editor được sửa nội dung nhưng không được đổi owner.
- Nhân viên support được xem trạng thái nhưng không được đọc payment secret.
- Tenant admin được mời member nhưng không được cấp platform role.

Response DTO nên chỉ chứa field được phép xem; request DTO nên chỉ chứa field được phép sửa. Với field phụ thuộc actor/object, kiểm tra property permission trước khi map. Không trả toàn bộ object rồi ẩn field bằng JavaScript.

## 18. ID trong GraphQL và các API dạng node

GraphQL thường có resolver tải object theo ID, ví dụ node(id), order(id) hoặc nested field. Nếu resolver chỉ gọi repository.findById, GraphQL có thể tạo cùng BOLA như REST.

Kiểm tra quyền tại resolver/service cho từng object và action. DataLoader giúp gom query và tránh N+1, nhưng cache của DataLoader phải được scope theo request/principal nếu dữ liệu phụ thuộc quyền. Không chia sẻ một cache loader toàn cục giữa các user nếu nó có thể trả object đã được authorize cho caller khác.

Với mutation, kiểm tra quyền trên object mục tiêu và mọi object liên quan. Một mutation nhận sourceId và targetId phải xác minh quyền trên cả hai, cùng quy tắc chuyển dữ liệu giữa tenant/project.

Không cho rằng global ID được Base64 encode là bí mật. Encoding chỉ thay đổi biểu diễn, không làm ID khó đoán hoặc cấp quyền.

## 19. File download, object storage và signed URL

File thường có object key hoặc storage path có thể đoán được. Không cho phép caller tự truyền storage key rồi backend tải file mà không kiểm tra object authorization.

Quy trình phù hợp:

1. Caller gửi document ID qua API.
2. Server xác minh identity, tenant và quyền download trên document.
3. Server lấy storage key từ metadata đáng tin cậy.
4. Server cấp signed URL ngắn hạn, giới hạn đúng object và method nếu provider hỗ trợ.
5. Ghi audit việc cấp link và download theo policy.

Signed URL là bearer capability trong thời gian hiệu lực: ai có URL có thể dùng nó theo quyền URL đó. Không log URL đầy đủ, không để TTL quá dài và không cấp URL trước khi kiểm tra quyền. Khi cần thu hồi nhanh, dùng proxy download hoặc cơ chế revoke/version phù hợp thay vì dựa vào URL dài hạn.

## 20. Async job và export cần giữ authorization context

Một user có thể tạo export job rồi tải kết quả sau. Cần kiểm tra quyền ở cả hai thời điểm:

- Khi tạo job: actor có quyền export dữ liệu và có đủ quota không?
- Khi worker thực thi: job có còn hợp lệ, tenant/resource scope và grant có còn hiệu lực không?
- Khi đọc trạng thái/kết quả: caller có phải requester hoặc principal được phép xem job không?
- Khi tải file: quyền trên dữ liệu và file có còn hiệu lực theo policy không?

Message/job envelope không phải nguồn tin cậy chỉ vì có field userId hoặc tenantId. Ghi actor, tenant context đã xác minh, purpose, resource scope và correlation ID từ server. Worker xác thực producer/service identity và áp dụng policy đã định nghĩa; với quyền có thể bị thu hồi, cần re-check trước thao tác nhạy cảm.

Không dùng một job ID ngẫu nhiên thay cho authorization. Job ID khó đoán chỉ giảm enumeration; endpoint status/download vẫn phải kiểm tra quyền.

## 21. Cache phải tôn trọng object authorization

Cache có thể tạo ra rò rỉ cross-user nếu key chỉ dựa trên object ID:

~~~text
cache key: order:1001
~~~

Nếu response được cache sau khi user A đã authorize, user B có thể nhận lại cùng nội dung mà không chạy policy check.

Biện pháp:

- Authorize trước khi trả cache entry, trừ khi cache key/partition và policy được thiết kế chứng minh an toàn.
- Cache key bao gồm tenant/principal hoặc authorization scope khi response phụ thuộc caller.
- Không cache response private trong shared public cache.
- Tách cache domain object khỏi cache response đã lọc theo quyền.
- Invalidate khi owner, membership, ACL hoặc tenant relationship thay đổi.
- Test cache hit giữa hai user/tenant khác nhau.

Chỉ thêm tenantId vào cache key vẫn chưa đủ nếu quyền khác nhau giữa user trong cùng tenant. Cache phải phản ánh đúng phạm vi authorization hoặc luôn kiểm tra policy trước khi sử dụng.

## 22. Trả 403 hay 404 khi object ngoài quyền?

HTTP semantics thường phân biệt:

- **403 Forbidden:** server biết resource nhưng caller không được phép thực hiện action.
- **404 Not Found:** resource không tồn tại hoặc server chủ động không tiết lộ sự tồn tại với caller.

Với object nhạy cảm, có thể trả 404 nhất quán cho cả không tồn tại và ngoài scope để giảm enumeration. Với API nội bộ/administrative, 403 có thể hữu ích cho workflow hỗ trợ. Quyết định phụ thuộc threat model và contract; điều quan trọng là không tạo khác biệt vô tình tiết lộ object.

Không chỉ nhìn status. Body, error code, response size, header và timing cũng có thể tạo side channel. Message nên tối thiểu và không nêu owner/tenant khác. Dù trả 404 hay 403, server vẫn phải thực sự từ chối truy cập.

## 23. UUID, ULID và opaque ID chỉ là defense in depth

ID ngẫu nhiên hoặc khó đoán có thể giảm enumeration:

| Kiểu ID | Đặc điểm | Lưu ý |
|---|---|---|
| Auto-increment integer | Dễ đoán, có thể suy luận thứ tự/tốc độ tạo | Cần object authorization nghiêm ngặt |
| Random UUID | Khó đoán hơn nếu được tạo đúng | Không phải authorization token |
| ULID/time-sortable ID | Có thể sắp xếp theo thời gian, một phần metadata có thể suy luận | Vẫn có thể bị lộ hoặc thu thập |
| Opaque external ID | Tách ID public khỏi khóa nội bộ | Cần mapping an toàn và authorization như thường |

Nếu đổi ID tuần tự sang UUID, vẫn phải kiểm tra quyền trên object. Không thiết kế endpoint như “ai biết UUID thì được đọc”. Nếu ID được dùng làm capability có chủ đích, cần thiết kế riêng về entropy, scope, expiry, revocation, method và leakage; đó là cơ chế cấp quyền bằng token, không còn là object identifier thông thường.

## 24. Rate limit và monitoring chống enumeration

Rate limit giúp làm chậm việc thử nhiều ID, nhưng không sửa lỗi BOLA. Attacker có thể thử ít ID mỗi ngày, dùng nhiều IP hoặc nhiều account. Vì vậy, cần kết hợp:

- Rate limit theo principal, tenant, API key và endpoint.
- Giới hạn batch size, page size và export volume.
- Theo dõi số object ID khác nhau được thử trong cửa sổ thời gian.
- Theo dõi tỷ lệ 403/404 và các lần truy cập object ngoài scope.
- Phát hiện ID tuần tự hoặc pattern tăng/giảm bất thường.
- Alert khi một actor thử object của nhiều tenant/project.
- Audit các lần read/update/delete/export trên dữ liệu nhạy cảm.
- Không đưa raw secret/token vào log; bảo vệ object reference theo chính sách dữ liệu.

Một request đọc thành công trái phép là tín hiệu nghiêm trọng hơn một chuỗi request bị từ chối. Monitoring cần phân biệt denied attempts với successful cross-object access để ưu tiên incident đúng mức.

## 25. Defense in depth ở database và service boundary

Object authorization phải được kiểm tra trong ứng dụng, nhưng có thể bổ sung:

- Tenant-scoped repository query.
- Database Row-Level Security (RLS) nếu DB hỗ trợ và session context được thiết lập an toàn.
- View/projection chỉ trả field cần thiết.
- Stored procedure hoặc service boundary có policy rõ.
- Least-privilege database account.
- Tách schema/database cho tenant khi kiến trúc yêu cầu.
- Audit query/access với dữ liệu nhạy cảm.

RLS là lớp phòng thủ bổ sung, không phải lý do bỏ authorization trong application. Cần bảo đảm tenant context được set bằng server-side identity, connection pool không giữ nhầm context giữa request và transaction kết thúc phải reset session state. Nếu dùng shared DB user và cho client tự set tenant variable, RLS có thể bị bypass.

Trong service-to-service flow, service nhận request phải xác minh caller/workload identity và quyền trên resource. Không mặc định request nội bộ là đáng tin cậy hoặc đã được service trước authorize đầy đủ.

## 26. Kiểm thử BOLA với hai user và hai tenant

Test nên tạo ít nhất:

- Tenant A với user A1 và A2.
- Tenant B với user B1.
- Object thuộc riêng A1, object chia sẻ trong tenant A và object thuộc tenant B.
- Role/relationship khác nhau: owner, editor, viewer, non-member.
- Một số ID tuần tự liền kề để kiểm tra enumeration.

Ma trận test:

| Kịch bản | Kết quả mong đợi |
|---|---|
| A1 đọc object của A1 | ALLOW theo policy |
| A2 đọc object riêng tư của A1 trong cùng tenant | DENY nếu không có relationship/grant |
| A2 đọc object được share cho A2 | ALLOW theo scope share |
| A1 đọc object của tenant B | DENY/404 theo contract |
| A1 sửa hoặc xóa object tenant B | DENY, không có thay đổi |
| A1 đổi ownerId/tenantId trong body | Field bị từ chối/bỏ qua theo contract, ownership không đổi |
| A1 đọc ID kế tiếp trong dãy | Không lộ object ngoài quyền |
| A1 truy cập nested item thuộc order khác | DENY/404 |
| A1 gửi batch trộn object được phép và bị cấm | Semantics all-or-nothing/partial đúng contract, không leak |
| A1 truy cập job/export của B1 | DENY |
| A1 dùng cache key đã được A2 tạo | Không nhận response vượt quyền |
| GraphQL node ID của B1 | DENY |
| Signed URL của document B | Không được cấp |
| Grant cross-tenant hết hạn/thu hồi | DENY |
| List/search/count | Chỉ bao gồm object actor được phép |

Test không chỉ assert HTTP status. Hãy xác minh database không bị thay đổi, response không có field/object ngoài quyền, audit event phản ánh quyết định và cache không trả dữ liệu của principal khác.

Ví dụ MockMvc kiểm tra object khác tenant:

~~~java
mockMvc.perform(get("/api/v1/orders/{id}", orderOwnedByTenantB)
        .with(jwt().jwt(jwt -> jwt.subject(userAId.toString()))))
    .andExpect(status().isNotFound());

verify(orderMapper, never()).toResponse(any());
~~~

Đây là ví dụ rút gọn; cần cấu hình test tenant context cho user A và xác minh repository query dùng tenant A. Nếu API contract trả 403, điều chỉnh status assertion nhưng vẫn phải xác nhận không có dữ liệu được map/serialize.

## 27. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ kiểm tra JWT tồn tại | Authentication không phải object authorization | Kiểm tra actor-object-action |
| findById rồi trả object | Không kiểm tra owner/tenant/ACL | Scoped query và policy |
| Dùng UUID thay authorization | ID có thể bị lộ hoặc lấy từ endpoint khác | Kiểm tra quyền ở mọi lần truy cập |
| Chỉ ẩn nút ở frontend | API có thể bị gọi trực tiếp | Enforcement phía server |
| Chỉ check role ADMIN | Role không phản ánh quan hệ với từng object | Relationship/ACL/policy |
| Tin tenantId/ownerId trong body | Caller có thể đổi scope hoặc owner | Lấy context từ server và domain |
| Check ở một controller | Service có đường gọi khác | Policy tại service/domain boundary |
| Filter list sau khi query | Có thể lộ dữ liệu/count và tốn tài nguyên | Scope query trước pagination |
| Check parent nhưng không check child | Nested ID có thể trỏ sang object khác | Xác minh quan hệ cha-con |
| Batch chỉ check một ID | Các object còn lại có thể ngoài quyền | Authorize từng object |
| Cache chỉ theo object ID | Response của user này có thể sang user khác | Cache theo auth scope hoặc authorize trước |
| Job ID ngẫu nhiên được xem là bí mật | ID có thể bị lộ; endpoint status/download vẫn mở | Check quyền requester/resource |
| Log mọi object ID và response | Tạo kho dữ liệu nhạy cảm mới | Audit tối thiểu, kiểm soát quyền và retention |

## 28. Checklist chống IDOR/BOLA

- [ ] Xác định mọi endpoint/flow nhận object ID hoặc object reference.
- [ ] Không xem ID tuần tự, UUID, ULID hay opaque ID là bằng chứng quyền.
- [ ] Mỗi read/update/delete/export/download/action kiểm tra object authorization.
- [ ] Quyết định dựa trên actor đã xác thực, object thực tế, action và relationship.
- [ ] Tenant context được resolve và xác minh server-side.
- [ ] Query giới hạn tenant/scope trước khi trả object hoặc phân trang.
- [ ] Quyền trong cùng tenant được kiểm tra theo owner, membership, ACL hoặc relationship.
- [ ] Nested resource xác minh quan hệ parent-child.
- [ ] Batch request authorize từng object và có semantics rõ ràng.
- [ ] List/search/count/export áp dụng cùng authorization scope.
- [ ] Request DTO không cho sửa owner, tenant, role hoặc audit field ngoài policy.
- [ ] Property-level permission được áp dụng cho field nhạy cảm.
- [ ] GraphQL resolver, async job, cache và object storage có kiểm tra tương đương.
- [ ] Signed URL có scope và TTL phù hợp; không log URL đầy đủ.
- [ ] 403/404 và error body không tiết lộ existence ngoài threat model.
- [ ] Rate limit và monitoring phát hiện enumeration nhưng không thay authorization.
- [ ] Test hai user, hai tenant, object riêng/share, ID tuần tự và mọi action.
- [ ] Audit và database defense in depth được cấu hình phù hợp.

## Kết luận

ID tuần tự khiến attacker dễ thử và liệt kê object hơn, nhưng lỗi thực sự là API tin rằng biết ID đồng nghĩa với có quyền. UUID hoặc ID khó đoán chỉ là defense in depth. Mỗi lần đọc, sửa, xóa, export, download hoặc thực hiện action phải kiểm tra actor có quyền trên object cụ thể trong tenant và relationship phù hợp. Hãy scope query ngay tại repository, đặt policy ở service/domain boundary, lọc list trước pagination, authorize từng object trong batch và giữ kiểm tra xuyên suốt GraphQL, cache, file storage cùng background job. Khi test bằng nhiều user/tenant và ID liền kề, đội phát triển có thể phát hiện BOLA trước khi endpoint trở thành công cụ enumeration hoặc rò rỉ dữ liệu.
