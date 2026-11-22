# Checklist object, property, function và tenant authorization

Trong module `SECURITY_API_SECURITY`, authorization phải được kiểm tra theo từng operation, object, field và tenant. Việc người dùng đăng nhập thành công chỉ xác nhận principal; nó không chứng minh principal được gọi mọi chức năng, đọc mọi resource hoặc xem mọi field. Một endpoint có thể kiểm tra role đúng nhưng vẫn mắc BOLA/IDOR vì không kiểm tra owner; truy vấn object đúng nhưng vẫn lộ field nội bộ; hoặc kiểm tra tenant ở controller nhưng bỏ sót export, cache hay background worker.

Checklist này dùng trước khi triển khai API hoặc thay đổi policy. Nó giúp nhóm phát triển và vận hành xác nhận các lớp authorization đã được thiết kế, thực thi, kiểm thử và quan sát xuyên suốt request lifecycle. Hãy áp dụng checklist theo operation và luồng dữ liệu thực tế, không chỉ theo tên controller hay HTTP route.

## 1. Phân biệt bốn lớp authorization

| Lớp | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| Function authorization | Principal có được thực hiện action này không? | Customer không được refund hoặc grant role |
| Object authorization | Principal có quyền trên object cụ thể không? | User A không đọc order của User B |
| Property authorization | Principal được đọc/ghi field nào? | Customer không sửa `tenantId`, `ownerId`, `role` |
| Tenant authorization | Request có nằm trong tenant scope được xác minh không? | Tenant A không truy cập dữ liệu Tenant B |

Các lớp này bổ sung cho nhau. `hasAuthority("orders:read")` có thể chứng minh principal có quyền gọi chức năng đọc order, nhưng chưa chứng minh order cụ thể thuộc phạm vi của họ. Object authorization đúng cũng chưa đủ nếu response serialize thêm `internalNote` hoặc mutation bind field `isAdmin`.

### 1.1. Function authorization

Function authorization kiểm tra action hoặc operation. Policy có thể dựa trên role, scope, permission, relationship, resource state hoặc kết hợp các điều kiện. Tên role không nên thay thế policy chi tiết: `ADMIN` ở một tenant không mặc nhiên là platform administrator hoặc có quyền truy cập tenant khác.

### 1.2. Object authorization

Object authorization kiểm tra quan hệ giữa principal và resource đang được truy cập. Quan hệ có thể là owner, member, assignee, project collaborator, delegated support scope hoặc một rule chia sẻ cụ thể. Không dựa vào việc ID khó đoán; UUID không thay thế authorization.

### 1.3. Property authorization

Property authorization kiểm soát field được đọc hoặc ghi. Với write, dùng DTO/command allowlist theo operation và kiểm tra field server-managed. Với read, dùng response projection/DTO theo quyền, tránh trả persistence entity rồi hy vọng client không hiển thị field nhạy cảm.

### 1.4. Tenant authorization

Tenant authorization ràng buộc mọi truy vấn và side effect với tenant context đã được xác minh. Tenant context thường được lấy từ principal/token hoặc workload mapping do server kiểm soát. `tenantId` trong path, query, header hay body chỉ là input cần đối chiếu, không phải bằng chứng quyền truy cập.

## 2. Checklist trước khi triển khai

### 2.1. Inventory và phân loại operation

- [ ] Mỗi operation có `operationId` hoặc tên chức năng ổn định, method/path/version và owner.
- [ ] Đã liệt kê REST, GraphQL query/mutation/resolver, RPC, webhook, export/download, async command và internal adapter có thể gọi cùng nghiệp vụ.
- [ ] Đã xác định principal type: user, partner client, service workload, operator hoặc anonymous.
- [ ] Đã xác định exposure: public, partner, internal, admin plane và môi trường triển khai.
- [ ] Đã phân loại dữ liệu trả về và dữ liệu bị thay đổi: public, internal, confidential hoặc restricted.
- [ ] Đã liệt kê object type, parent/child relationship và tenant ownership.
- [ ] Đã liệt kê side effect: database write, queue publish, payment, email/SMS, export, file access hoặc outbound HTTP.
- [ ] Đã xác định version cũ, route alias và alternate entry point có thể gọi cùng logic.

Không kết luận một operation an toàn chỉ vì không có controller public. Một worker, GraphQL resolver hoặc endpoint nội bộ có thể truy cập cùng object và phải tuân thủ policy tương ứng.

### 2.2. Viết policy rõ ràng trước khi viết code

Với mỗi operation, trả lời:

1. Principal nào được phép gọi action?
2. Principal cần permission/scope nào?
3. Resource nào nằm trong phạm vi của principal?
4. Field nào được đọc và field nào được ghi?
5. Tenant được xác định từ đâu và quan hệ tenant-resource được xác minh thế nào?
6. Có ngoại lệ như shared resource, delegated access hoặc support access không?
7. Quyền được kiểm tra tại thời điểm enqueue hay thời điểm thực thi?
8. Khi thiếu context, policy store lỗi hoặc không xác định được quan hệ, hệ thống xử lý thế nào?

Ghi policy theo dạng dễ review, ví dụ:

```text
Operation: orders.refund
Principal: authenticated user with orders:refund
Tenant: derived from verified principal context
Object: order must belong to an account the principal may manage
State: order must be paid and refundable
Property: amount/currency are derived from stored order; caller cannot override
Side effect: one refund per idempotency key; audit event required
Default: deny when permission, tenant or ownership cannot be established
```

Policy phải mô tả cả điều kiện cho phép và điều kiện từ chối. Tránh ghi chung chung như “admin only” nếu chưa định nghĩa admin thuộc tenant nào, có quyền trên loại object nào và có thể thực hiện action nào.

## 3. Checklist function authorization

### 3.1. Quyền được gắn với operation cụ thể

- [ ] Mỗi operation có permission/action riêng hoặc mapping được tài liệu hóa.
- [ ] Quyền đọc, tạo, sửa, xóa, export, approve, refund và quản trị được tách theo rủi ro.
- [ ] Không suy ra quyền mutation từ quyền read.
- [ ] Không dùng một role rộng cho mọi endpoint nếu nghiệp vụ cần phân quyền chi tiết.
- [ ] Permission được kiểm tra ở server-side; frontend ẩn nút chỉ là UX.
- [ ] Default là deny khi không có rule rõ ràng.
- [ ] Public endpoint được khai báo tường minh và chỉ trả dữ liệu dự kiến.
- [ ] Quyền admin/platform được tách khỏi quyền admin trong tenant.
- [ ] Service-to-service operation xác minh workload identity, audience và scope.

### 3.2. Kiểm tra trạng thái nghiệp vụ và separation of duties

Có permission không đồng nghĩa action luôn hợp lệ. Ví dụ người tạo payment không được tự approve payment đó nếu quy trình yêu cầu hai người; user có quyền `orders:write` vẫn không được chuyển order từ trạng thái `CANCELLED` sang `SHIPPED`.

- [ ] Action được kiểm tra theo trạng thái hiện tại của resource.
- [ ] Approval, maker-checker và separation-of-duties được thực thi ở server.
- [ ] Không tin `approvedBy`, `createdBy` hoặc role trong request body.
- [ ] Chống race condition giữa authorization check và update; dùng transaction, version check hoặc atomic conditional update phù hợp.
- [ ] Quyền bị thu hồi có hiệu lực theo semantics đã định nghĩa; cache permission có TTL/invalidation rõ.

### 3.3. Bảo vệ các đường gọi khác nhau

- [ ] Controller và service entry point đều có policy phù hợp; không để internal caller bỏ qua policy chỉ vì không đi qua HTTP controller.
- [ ] GraphQL resolver kiểm tra permission ở field/mutation có dữ liệu nhạy cảm.
- [ ] RPC/gRPC method có authentication và authorization tương ứng.
- [ ] Webhook consumer xác minh chữ ký/producer identity và quyền của integration.
- [ ] Background job xác minh actor/delegation context hoặc service permission theo semantics nghiệp vụ.
- [ ] Admin/Actuator/diagnostic endpoint có policy riêng và không được mở chỉ vì nằm trong mạng nội bộ.

## 4. Checklist object authorization

### 4.1. Object được tải trong phạm vi principal

- [ ] Truy vấn object có predicate owner/tenant/relationship phù hợp, thay vì tải theo ID rồi quên kiểm tra quyền.
- [ ] Repository method thể hiện rõ scope, ví dụ `findByIdAndTenantId` hoặc query theo membership.
- [ ] Object authorization áp dụng cho GET, PATCH, DELETE, export, download, search, list và bulk operation.
- [ ] Nested resource kiểm tra quan hệ từ parent tới child; không chỉ xác minh child ID tồn tại.
- [ ] Shared resource có policy rõ cho người chia sẻ, người nhận, thời hạn và quyền action.
- [ ] Resource đã archive/soft-delete hoặc ở trạng thái đặc biệt vẫn tuân thủ policy.
- [ ] Nếu che giấu sự tồn tại object, response cho object ngoài scope và object không tồn tại không tạo oracle không cần thiết.

Ví dụ truy vấn có scope:

```java
public Optional<Order> findVisibleOrder(UUID orderId, UUID tenantId) {
    return orderRepository.findByIdAndTenantId(orderId, tenantId);
}
```

Pattern này giảm nguy cơ quên tenant predicate. Nếu quyền dựa trên membership hoặc delegated access phức tạp hơn, repository/query phải encode relationship tương ứng thay vì chỉ dùng tenant ID.

### 4.2. ID không phải quyền

- [ ] UUID, ULID hoặc ID khó đoán không được xem là biện pháp authorization.
- [ ] Không cho phép truy cập object chỉ vì caller biết ID.
- [ ] ID trong path, query, body và nested array đều được kiểm tra scope.
- [ ] Không suy ra owner/tenant từ prefix hoặc cấu trúc ID trừ khi đó là cơ chế được xác minh và tài liệu hóa.
- [ ] Không trả danh sách ID/resource để caller thử enumeration ngoài phạm vi.

### 4.3. Bulk, search, pagination và export

Đây là các đường dễ bỏ sót object authorization vì một request chứa nhiều object hoặc truy vấn động.

- [ ] Mọi object trong bulk request đều được kiểm tra quyền; không chỉ kiểm tra object đầu tiên.
- [ ] Định nghĩa rõ atomic behavior: toàn bộ batch bị từ chối nếu một item không hợp lệ, hoặc partial result có contract rõ và không lộ object ngoài scope.
- [ ] Search/list query áp dụng tenant/relationship predicate trước pagination và aggregation.
- [ ] Count, facet, sort và filter không tiết lộ sự tồn tại object ngoài scope.
- [ ] Export/report được kiểm tra quyền trên cả tập dữ liệu và các field xuất ra.
- [ ] Download/file endpoint xác minh owner/tenant của metadata và object storage key.
- [ ] Signed URL có method, object, expiry và scope cụ thể; không dùng URL ký sẵn làm thay authorization của mọi object.
- [ ] Pagination cursor không cho phép chuyển sang tenant hoặc query scope khác.

### 4.4. Kiểm tra race và time-of-check/time-of-use

- [ ] Quan hệ owner/membership được kiểm tra cùng transaction hoặc được bảo vệ bằng version/conditional update khi cần.
- [ ] Không thực hiện authorization trên bản object cũ rồi update object khác bằng ID do caller cung cấp.
- [ ] Với quyền có thể bị revoke đồng thời, xác định semantics và điểm linearization cần thiết.
- [ ] Side effect được tạo sau khi policy và trạng thái nghiệp vụ được xác minh; không enqueue trước rồi mới kiểm tra quyền.

## 5. Checklist property authorization

### 5.1. Write allowlist

- [ ] Request DTO chỉ chứa field caller được phép thay đổi.
- [ ] Field server-managed như `id`, `tenantId`, `ownerId`, `createdBy`, `role`, `status`, `isVerified`, `riskScore` không được bind tự do.
- [ ] Mapping từ DTO sang entity dùng allowlist rõ; không bind request trực tiếp vào persistence entity.
- [ ] Unknown field bị từ chối hoặc xử lý theo contract rõ ràng; field nhạy cảm không bị silently accepted.
- [ ] Field chỉ được sửa ở một trạng thái hoặc bởi một role cụ thể có rule riêng.
- [ ] Nested DTO/list cũng có allowlist và object authorization.
- [ ] PATCH semantics phân biệt field absent, null và giá trị mới.
- [ ] Field read-only không thể được thay đổi bằng JSON merge patch, form binding hoặc alternate content type.

Ví dụ DTO an toàn:

```java
public record UpdateProfileRequest(
    @NotBlank @Size(max = 80) String displayName,
    @Size(max = 300) String biography
) {}
```

Service chỉ cập nhật các field được phép:

```java
profile.changeDisplayName(request.displayName());
profile.changeBiography(request.biography());
```

Không dùng `BeanUtils.copyProperties(request, entity)` hoặc mapper tự động không có allowlist nếu DTO có thể chứa field ngoài quyền caller.

### 5.2. Read allowlist

- [ ] Response DTO/projection chỉ chứa field được phép cho principal và operation.
- [ ] Không serialize trực tiếp JPA entity hoặc object graph mặc định.
- [ ] Field nội bộ như `internalNote`, credential metadata, fraud signal, private contact hoặc admin flag được loại bỏ theo policy.
- [ ] Field lồng nhau và relationship collection được lọc theo quyền riêng.
- [ ] GraphQL field resolver kiểm tra property access nếu schema expose field nhạy cảm.
- [ ] Error, debug và metadata header không tiết lộ field bị ẩn.
- [ ] Field visibility không phụ thuộc vào frontend ẩn thành phần giao diện.

### 5.3. Field-level permission có thể thay đổi theo trạng thái

Một principal có thể đọc field trong một workflow nhưng không đọc sau khi record chuyển trạng thái; hoặc được cập nhật `shippingAddress` nhưng không được thay `paymentStatus`. Policy phải chỉ rõ field/action/state thay vì chỉ dựa trên role tổng quát.

## 6. Checklist tenant isolation

### 6.1. Tenant context có nguồn đáng tin

- [ ] Tenant context được lấy từ principal/token đã xác minh hoặc mapping server-side của workload.
- [ ] Không tin `tenantId` từ body, query, path hoặc header như bằng chứng quyền.
- [ ] Nếu request chứa tenant ID để chọn workspace, server kiểm tra principal là member hoặc được delegate vào tenant đó.
- [ ] Client identity được xác minh trước khi map sang tenant; không tin `X-Client-Id` hoặc `X-Tenant-Id` do caller tự khai.
- [ ] Platform operator/cross-tenant support có quyền riêng, scope rõ, lý do và audit.
- [ ] Tenant context được truyền rõ qua application boundary, transaction và async message.

### 6.2. Mọi data access đều có tenant scope

- [ ] Read/write/delete query có tenant predicate hoặc policy relationship.
- [ ] Unique constraint/index được thiết kế với tenant key khi uniqueness chỉ có ý nghĩa trong tenant.
- [ ] Foreign key/relationship không cho phép liên kết resource của tenant khác ngoài rule chia sẻ.
- [ ] Search index, analytics, data warehouse và read replica giữ tenant scope.
- [ ] Cache key chứa tenant scope và mọi dimension ảnh hưởng authorization.
- [ ] Object storage path/key và signed URL được ràng buộc với tenant/resource.
- [ ] Export, report, bulk import và background job giữ tenant scope từ lúc tạo đến lúc hoàn tất.
- [ ] Database migration/backfill không gán nhầm tenant hoặc để row thiếu tenant ngoài chính sách.

### 6.3. Tenant context trong cache

Cache có thể làm rò dữ liệu dù database query đã đúng. Nếu response của tenant A được cache bằng key chỉ chứa `/orders/123`, tenant B có thể nhận lại response đó khi key bị trùng.

- [ ] Cache key bao gồm tenant và các permission dimension ảnh hưởng kết quả.
- [ ] Cache không dùng raw user-supplied tenant ID nếu chưa xác minh.
- [ ] Cache invalidation xử lý thay đổi membership, role, ownership và field visibility.
- [ ] Shared cache không trộn public/private response hoặc principal có scope khác nhau.
- [ ] CDN/reverse proxy không cache response chứa dữ liệu riêng như public content.
- [ ] Negative/authorization decision cache có TTL và invalidation phù hợp; không giữ deny/allow sai sau khi policy thay đổi.

### 6.4. Tenant context trong async processing

- [ ] Message/command có schema và tenant reference rõ, nhưng consumer không tin tenant field chỉ vì nó nằm trong payload.
- [ ] Producer identity/ACL được xác minh và được phép publish cho tenant đó.
- [ ] Consumer xác minh tenant-resource relationship trước khi đọc/ghi.
- [ ] Command nhạy cảm kiểm tra lại quyền/trạng thái tại thời điểm thực thi theo contract.
- [ ] Retry, DLQ và redrive giữ original tenant/message reference và không cho operator sửa để vượt policy.
- [ ] Scheduled job/service account có tenant scope cụ thể, không dùng quyền platform rộng nếu không cần.

## 7. Các kiến trúc thực thi authorization

Không có một cơ chế duy nhất phù hợp mọi ứng dụng. Có thể kết hợp method security, policy service, query scoping và database defense in depth.

### 7.1. Spring Security method authorization

Ví dụ function permission:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderView getOrder(UUID orderId) {
    // Object/tenant authorization vẫn cần được thực hiện.
}
```

Annotation này chỉ kiểm tra authority trên principal. Nó không tự kiểm tra object có thuộc tenant của principal hay field nào được phép trả.

### 7.2. Object và tenant scope trong service/repository

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderView getOrder(UUID orderId, CurrentPrincipal principal) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, principal.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    orderAuthorization.requireCanRead(principal, order);
    return orderMapper.toView(order, principal);
}
```

Ví dụ cho thấy function permission, tenant-scoped lookup, object policy và response mapping là các bước riêng. `CurrentPrincipal` phải đến từ security context đã xác minh; không khởi tạo từ request DTO.

### 7.3. Policy service tập trung

Khi policy phức tạp, tạo service có method rõ nghĩa như `requireCanReadOrder`, `requireCanRefundInvoice` hoặc `visibleDocumentsFor`. Tránh một helper chung nhận `String action`, `Object resource` rồi dùng reflection hoặc default allow khi không nhận diện action.

Policy service cần:

- Input typed và principal đã xác minh.
- Kết quả deny-by-default.
- Error/decision code ổn định.
- Test matrix theo principal, action, resource và tenant.
- Không tự lấy tenant từ request body.
- Không tạo side effect.

### 7.4. Database row-level security

Row-level security (RLS) có thể là lớp defense in depth để database từ chối query không có tenant context phù hợp. Tuy nhiên, RLS không thay function/property authorization ở application và cần cấu hình cẩn thận với connection pool.

- [ ] Session/transaction context được set từ principal đã xác minh, không từ input chưa kiểm tra.
- [ ] Context được reset/clear an toàn khi connection trả về pool.
- [ ] Application role không có quyền bypass RLS ngoài thiết kế.
- [ ] Migration, background worker và admin job có policy riêng, scope rõ.
- [ ] Test cross-tenant query qua đúng database role dùng trong production.

Không bật RLS rồi mặc định mọi đường truy cập đều an toàn. Superuser, table owner hoặc role có `BYPASSRLS` có thể vượt policy tùy database và cấu hình.

## 8. Checklist dữ liệu và luồng đặc biệt

### 8.1. GraphQL và nested resolver

- [ ] Mỗi query/mutation có function authorization.
- [ ] Resolver kiểm tra object scope ở từng relationship, không chỉ ở root query.
- [ ] DataLoader/cache key có tenant/principal scope khi kết quả phụ thuộc quyền.
- [ ] Field nhạy cảm có property authorization.
- [ ] Depth/complexity/batch limit được áp dụng cùng authorization.
- [ ] Introspection/schema không làm lộ thông tin ngoài policy nếu endpoint cần giới hạn.

### 8.2. File upload, download và signed URL

- [ ] Upload target và metadata thuộc tenant/resource được xác minh.
- [ ] Download kiểm tra object authorization trước khi cấp URL hoặc stream file.
- [ ] Signed URL có object, method, content type và expiry cụ thể.
- [ ] URL không được tái sử dụng để truy cập object khác hoặc sau khi quyền bị thu hồi quá thời hạn cho phép.
- [ ] File scan/processing worker giữ tenant context và không tin object key do caller tự sửa.

### 8.3. Search, report và export

- [ ] Filter/sort/search field không cho truy vấn ngoài tenant scope.
- [ ] Aggregate/count/facet không tiết lộ dữ liệu tenant khác.
- [ ] Report snapshot có tenant và permission scope rõ.
- [ ] Export chỉ gồm field được phép; file được lưu với ACL và retention đúng.
- [ ] Download result kiểm tra lại người dùng/tenant hoặc dùng signed URL có expiry ngắn theo policy.

### 8.4. Webhook và service-to-service

- [ ] Webhook signature được verify trên raw body theo provider contract.
- [ ] Event được map tới tenant/integration đã đăng ký; không tin tenant field tự khai.
- [ ] Replay/deduplication và event ordering được kiểm soát.
- [ ] Service-to-service dùng mTLS/workload identity hoặc token audience/scope cụ thể.
- [ ] Service không được quyền platform rộng chỉ vì cùng network.
- [ ] Delegated user context được xác minh và không thể tự nâng role qua message/header.

## 9. Checklist kiểm thử authorization

Security test phải ưu tiên negative case và xác minh cả response lẫn side effect.

### 9.1. Ma trận principal × action × object

Chuẩn bị fixture ít nhất gồm hai tenant, hai user, một support principal và một service principal. Với mỗi operation, kiểm tra:

- [ ] Anonymous bị từ chối ở operation cần authentication.
- [ ] Principal đã xác thực nhưng thiếu function permission bị từ chối.
- [ ] User A truy cập object của User B bị từ chối.
- [ ] Tenant A truy cập object Tenant B bị từ chối.
- [ ] User có quyền read nhưng không có quyền update/delete/export bị từ chối.
- [ ] Role trong tenant không tự cấp platform privilege.
- [ ] Support/delegated access chỉ hoạt động trong scope, thời hạn và lý do được cấp.
- [ ] Service principal chỉ gọi được operation và tenant được grant.

### 9.2. Ma trận property

- [ ] Field được phép ghi cập nhật đúng.
- [ ] Field server-managed không thể bị mass assign.
- [ ] Field nhạy cảm không xuất hiện trong response của principal thiếu quyền.
- [ ] Nested object/array không bypass allowlist.
- [ ] PATCH phân biệt absent/null/value đúng contract.
- [ ] Error message không echo rejected value.

### 9.3. Kiểm thử đường vòng

- [ ] Thay object ID trong path, query, body và nested list.
- [ ] Gọi cùng action qua API version cũ, alias, GraphQL, RPC và internal route.
- [ ] Gọi bulk operation với một ID ngoài scope giữa các ID hợp lệ.
- [ ] Thử cache hit sau khi đổi tenant/principal/permission.
- [ ] Replay message/webhook và redrive DLQ.
- [ ] Gọi direct service route khi kiến trúc yêu cầu gateway-only network path.

### 9.4. Xác minh không có side effect

Khi request bị từ chối:

- [ ] Database row không thay đổi.
- [ ] Không tạo outbox/business event hoặc queue message trái phép.
- [ ] Không gọi payment/email/SMS/provider.
- [ ] Không tạo export/file/signed URL.
- [ ] Không cập nhật cache với dữ liệu ngoài scope.
- [ ] Security audit event được ghi theo policy nhưng không chứa secret.

Không chỉ assert `403` hoặc `404`. Một endpoint có thể trả lỗi sau khi đã enqueue job hoặc thực hiện provider call.

### 9.5. Ma trận test tổng hợp

| Lớp | Positive test | Negative test |
|---|---|---|
| Function | Permission đúng gọi được action | Thiếu scope/role bị từ chối |
| Object | Owner/member đọc object được phép | Đổi ID sang object ngoài scope bị từ chối |
| Property write | Field allowlist cập nhật được | `tenantId`, `role`, `ownerId` không bị sửa |
| Property read | Field được cấp quyền xuất hiện | Internal/restricted field bị ẩn |
| Tenant | Tenant member truy cập dữ liệu tenant mình | Tenant ID giả hoặc resource tenant khác bị từ chối |
| Cache | Cache hit trong cùng scope | Không tái sử dụng response giữa tenant/principal |
| Async | Worker xử lý command hợp lệ | Producer/tenant/actor không hợp lệ bị từ chối |
| Version | Version active tuân thủ policy | Legacy route không bypass control |
| Side effect | Action hợp lệ tạo đúng một kết quả | Denied/duplicate không tạo side effect trái phép |

## 10. Ví dụ Spring Boot Test cho object và tenant authorization

Ví dụ dưới đây minh họa cách test hai tenant. Các fixture, JWT converter và repository là thành phần của ứng dụng thực tế.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;
    @Autowired OrderFixtures fixtures;

    @Test
    void userCannotReadAnotherTenantsOrder() throws Exception {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        Order orderB = fixtures.createOrder(tenantB);

        mvc.perform(get("/v1/orders/{id}", orderB.getId())
                .with(jwt()
                    .jwt(token -> token.claim("tenant_id", tenantA.toString()))
                    .authorities(new SimpleGrantedAuthority("SCOPE_orders:read"))))
            .andExpect(status().isNotFound());
    }

    @Test
    void deniedMutationDoesNotChangeOrder() throws Exception {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        Order orderB = fixtures.createOrder(tenantB);
        String originalStatus = orderB.getStatus();

        mvc.perform(patch("/v1/orders/{id}", orderB.getId())
                .with(jwt()
                    .jwt(token -> token.claim("tenant_id", tenantA.toString()))
                    .authorities(new SimpleGrantedAuthority("SCOPE_orders:write")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""{"status":"CANCELLED"}"""))
            .andExpect(status().isNotFound());

        assertThat(orders.findById(orderB.getId()).orElseThrow().getStatus())
            .isEqualTo(originalStatus);
    }
}
```

Trong ví dụ, `jwt()` của Spring Security Test tạo authentication context giả lập; nó không kiểm tra chữ ký JWT, issuer, audience hoặc JWKS. Cần có integration test riêng cho token verification. Status `404` giả định API che giấu sự tồn tại object ngoài tenant; nếu contract dùng `403`, điều cần giữ là không có dữ liệu hoặc side effect bị lộ.

## 11. Checklist triển khai và cấu hình production

### 11.1. Spring Security và route coverage

- [ ] Mọi `SecurityFilterChain` có matcher rõ, thứ tự chain được kiểm tra và không có route rơi vào chain permissive ngoài ý muốn.
- [ ] Request không match policy cụ thể bị deny hoặc yêu cầu authentication theo thiết kế.
- [ ] Method security được bật nếu dùng `@PreAuthorize`/`@PostAuthorize`.
- [ ] Proxy/gateway không rewrite path theo cách bypass security matcher.
- [ ] CORS không được xem là authentication hoặc authorization.
- [ ] CSRF được giữ cho cookie/session-based flow theo threat model.
- [ ] Management/Actuator/admin endpoint có chain và network exposure riêng.

### 11.2. Identity và permission configuration

- [ ] JWT issuer, audience, signature algorithm, expiry và key rotation được cấu hình đúng.
- [ ] Scope/role mapping không vô tình nâng quyền do claim name collision hoặc converter mặc định.
- [ ] Client/service account chỉ có grant cần thiết.
- [ ] Credential revoke/rotation có semantics và propagation time rõ.
- [ ] Permission cache có TTL/invalidation và không giữ quyền cũ vô thời hạn.
- [ ] Emergency deny/disable policy có owner, audit và expiry/review.

### 11.3. Database và cache

- [ ] Application DB role có quyền tối thiểu; không chạy API bằng superuser.
- [ ] Tenant predicate có index phù hợp để tránh query bỏ scope vì performance workaround.
- [ ] Unique constraint/foreign key phản ánh tenant relationship.
- [ ] RLS (nếu dùng) được test bằng production-like role và connection pool.
- [ ] Cache key và invalidation giữ tenant/principal permission scope.
- [ ] Search index, replica, report store và object storage giữ isolation tương đương.

### 11.4. Async và service-to-service

- [ ] Broker ACL giới hạn producer/consumer theo topic/queue.
- [ ] Message schema và tenant/actor context được xác minh.
- [ ] Worker thực hiện authorization theo policy tại thời điểm phù hợp.
- [ ] Retry/DLQ/redrive không bỏ qua authorization hoặc expiry.
- [ ] Workload identity/mTLS/token audience được kiểm tra ở service boundary.
- [ ] Network policy ngăn direct access không được phép; network location không thay identity.

### 11.5. Deployment artifact và rollout

- [ ] Security config được đóng gói/version hóa cùng artifact hoặc config digest.
- [ ] Không có debug profile, permissive matcher hoặc test credential trong production.
- [ ] Route inventory khớp gateway, application, GraphQL/RPC và deployed listener.
- [ ] Canary test có principal hợp lệ và không hợp lệ cho từng tenant/operation rủi ro cao.
- [ ] Rollout theo batch; theo dõi 401/403/404, cross-tenant denial, error rate và side effect.
- [ ] Rollback không đưa lại version/config thiếu authorization.
- [ ] Exception/temporary bypass có owner, phạm vi, compensating control và expiry.

## 12. Monitoring và audit sau triển khai

Authorization cần quan sát được mà không log secret hoặc làm lộ dữ liệu.

- [ ] Ghi event cho permission change, role grant/revoke, cross-tenant denial, support access và privileged operation.
- [ ] Log operation ID, policy decision code, principal category và resource type theo phân loại dữ liệu.
- [ ] Không log access token, cookie, raw payload hoặc field nhạy cảm.
- [ ] Theo dõi spike `401/403/404` theo operation/client category và tenant scope đã xác minh.
- [ ] Theo dõi access denied trên object khác tenant, bulk/export và legacy version.
- [ ] Theo dõi cache hit và authorization policy version khi cần điều tra stale permission.
- [ ] Alert khi API version cũ hoặc route không có inventory tiếp tục nhận traffic.
- [ ] Audit support/admin access có actor, reason, scope và thời điểm.
- [ ] Metric dùng dimension có cardinality hữu hạn; không dùng raw user/resource ID làm label.
- [ ] Log/audit store có access control, retention, integrity và review.

Không phải mọi `403` đều là incident; người dùng hợp lệ có thể thử một thao tác ngoài quyền. Alert nên dựa trên baseline, operation sensitivity, tần suất, pattern enumeration và nhiều tín hiệu kết hợp.

## 13. Release gate: tiêu chí không được bỏ qua

Một release có thể được xem xét khi các điều kiện sau đã được chứng minh bằng test/evidence:

1. Không có operation protected nào cho anonymous hoặc principal thiếu permission truy cập.
2. Không có cross-user/cross-tenant read hoặc write trong test matrix.
3. Field server-managed không thể mass assign; field nhạy cảm không bị trả sai principal.
4. Search, bulk, export, cache, file và async path giữ cùng authorization invariant.
5. Request bị từ chối không tạo business side effect.
6. API version/alias còn hoạt động không bypass policy mới.
7. Database/cache/broker/workload identity được cấu hình theo least privilege.
8. Monitoring/audit có thể phát hiện thay đổi quyền và truy cập bất thường.
9. Không còn critical/high finding chưa được xử lý hoặc exception chưa có owner/expiry theo quy trình.
10. Evidence gắn với đúng commit, artifact digest và cấu hình được triển khai.

Nếu một invariant chưa thể xác minh, không đánh dấu release gate là pass chỉ vì unit test hoặc scanner xanh. Ghi rõ phạm vi chưa kiểm chứng, rủi ro và quyết định của người có thẩm quyền.

## 14. Lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra role ở controller | Object/tenant khác vẫn có thể bị truy cập | Function + object + tenant policy |
| Tin UUID khó đoán | BOLA/IDOR vẫn tồn tại | Kiểm tra quan hệ principal-resource |
| Lấy tenant từ body/header | Caller tự chọn tenant | Tenant context đã xác minh |
| Dùng entity làm request/response | Mass assignment và excessive data exposure | DTO/projection allowlist |
| Chỉ kiểm tra object ở GET | PATCH/DELETE/export/bulk bị bỏ sót | Policy trên mọi operation và adapter |
| Kiểm tra quyền trước rồi update sau không đồng bộ | TOCTOU/race condition | Transaction/conditional update |
| Cache key thiếu tenant | Rò dữ liệu giữa tenant | Cache key/invalidation theo scope |
| Worker tin tenant trong message | Cross-tenant background action | Producer identity + consumer policy |
| Gateway là lớp authorization duy nhất | Direct route bypass | Service boundary và network policy |
| Chỉ test status code | Side effect vẫn xảy ra | Assert database, queue và provider |
| Role admin quá rộng | Privilege escalation và blast radius lớn | Permission/action scope cụ thể |
| Bỏ qua version cũ | Legacy endpoint trở thành bypass | Security parity và sunset |

## 15. Checklist cuối cùng trước khi bật traffic

### Function

- [ ] Operation có permission/action cụ thể và default deny.
- [ ] Quyền read/write/delete/export/approve/refund/admin được tách đúng.
- [ ] Business state, approval và separation of duties được kiểm tra.
- [ ] Mọi adapter (REST, GraphQL, RPC, webhook, worker) dùng policy tương ứng.

### Object

- [ ] Object được query trong owner/tenant/relationship scope.
- [ ] ID không được coi là quyền.
- [ ] Nested, bulk, list/search, pagination, export và download đều được kiểm tra.
- [ ] Race/TOCTOU và trạng thái resource được xử lý.

### Property

- [ ] Write DTO là allowlist; field server-managed không thể bị sửa.
- [ ] Read DTO/projection chỉ trả field được phép.
- [ ] Nested field và PATCH semantics được kiểm tra.
- [ ] Error/log không echo rejected value hoặc field nhạy cảm.

### Tenant

- [ ] Tenant context lấy từ principal/workload đã xác minh.
- [ ] Mọi data store, cache, search, file, export và async path giữ tenant scope.
- [ ] Shared/delegated access có rule và audit rõ.
- [ ] Tenant ID do caller gửi không thể mở rộng quyền.

### Test và deployment

- [ ] Có negative test principal/action/object/field/tenant.
- [ ] Test chứng minh denied request không tạo side effect.
- [ ] Security parity trên version/alias đang hoạt động.
- [ ] Spring Security chain, gateway, database, cache và broker config được kiểm tra.
- [ ] Canary và monitoring có guardrail/alert.
- [ ] Release evidence gắn với artifact/config được triển khai.

## Kết luận

Authorization an toàn cần đồng thời kiểm soát chức năng, object, property và tenant. Function permission quyết định principal có được gọi action; object policy quyết định resource nào nằm trong phạm vi; property policy quyết định field nào được đọc/ghi; tenant isolation ràng buộc mọi data path với tenant context đã xác minh. Hãy áp dụng các quy tắc này cho REST, GraphQL, RPC, cache, export, file, queue và worker; kiểm thử negative case cùng side effect; sau đó xác minh cấu hình thực tế trước khi bật traffic. Một release chỉ đạt yêu cầu khi không có đường phụ nào bỏ qua các invariant đó.
