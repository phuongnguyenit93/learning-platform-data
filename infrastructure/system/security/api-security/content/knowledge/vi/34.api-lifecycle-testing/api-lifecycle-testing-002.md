# Authorization test theo role, object và tenant

## 1. Vì sao phải kiểm thử authorization theo nhiều chiều?

Authentication trả lời câu hỏi caller là ai. Authorization quyết định caller đó được phép thực hiện hành động nào, trên tài nguyên nào, trong tenant nào và với những thuộc tính dữ liệu nào. Một request có access token hợp lệ vẫn có thể truy cập sai invoice, sửa shipment của đối tác khác hoặc nâng quyền bằng cách gửi thêm field `role`.

Vì vậy, kiểm thử authorization không thể chỉ xác nhận rằng user chưa đăng nhập nhận `401` và user đã đăng nhập nhận `200`. Cần chứng minh policy đúng trên từng chiều:

- **Role/principal:** user, partner, service hoặc administrator có nhóm quyền nào?
- **Function/action:** principal được gọi chức năng nào, với HTTP method hoặc operation nào?
- **Object/resource:** principal có quan hệ hợp lệ với object cụ thể không?
- **Tenant boundary:** object thuộc tenant nào và caller có được truy cập tenant đó không?
- **Property/field:** caller được đọc hoặc sửa những thuộc tính nào?
- **Context/state:** trạng thái nghiệp vụ, approval, thời gian, ownership hoặc điều kiện khác có cho phép hành động không?

Các chiều này tương ứng với những lỗi phổ biến như Broken Function Level Authorization (BFLA), Broken Object Level Authorization (BOLA/IDOR) và Broken Object Property Level Authorization (BOPLA/mass assignment hoặc excessive data exposure). Một endpoint có thể vượt qua test role nhưng vẫn có BOLA; test object ownership nhưng bỏ sót tenant boundary; hoặc bảo vệ `GET` nhưng để `PATCH` thay đổi field nhạy cảm.

## 2. Xác định policy trước khi viết test

Test phải xuất phát từ quy tắc nghiệp vụ có thể kiểm chứng, không suy đoán quyền từ tên role hoặc cấu trúc URL. Với mỗi operation, mô tả principal, action, resource, scope và điều kiện.

Ví dụ policy cho hệ thống đơn hàng:

| Principal | Action | Resource/condition | Kết quả |
|---|---|---|---|
| Customer | `order.read` | Đơn hàng thuộc chính customer và tenant hiện tại. | Allow. |
| Customer | `order.cancel` | Đơn hàng thuộc customer, trạng thái còn cho phép hủy. | Allow nếu state hợp lệ. |
| Customer | `order.read` | Đơn hàng của customer khác. | Deny. |
| Support agent | `order.read` | Tenant nằm trong phạm vi được phân công và có purpose hợp lệ. | Allow theo policy hỗ trợ. |
| Support agent | `order.refund` | Không có permission hoàn tiền hoặc approval. | Deny. |
| Tenant admin | `member.invite` | Thành viên thuộc tenant của admin. | Allow. |
| Tenant admin | `tenant.billing.update` | Tenant khác. | Deny. |
| Fulfillment service | `shipment.update` | Shipment được giao cho service/partner đó; chỉ field trạng thái giao hàng. | Allow theo contract. |
| Fulfillment service | `order.refund` | Không thuộc chức năng của service. | Deny. |
| Anonymous | `order.read` | Bất kỳ đơn hàng riêng tư nào. | Deny. |

Một policy record nên xác định rõ:

```text
principal type + principal id + role/scope
action + HTTP method/operation
resource type + resource id
tenant id + ownership/relationship
allowed properties + forbidden properties
business state + approval/context
expected decision + expected side effects
```

Nếu policy chưa nói rõ ai được làm gì trên object nào, chưa thể viết test đáng tin cậy. Hãy làm rõ với owner nghiệp vụ/security trước khi dùng kết quả test để kết luận endpoint an toàn.

## 3. Ma trận role và function

Role/function test xác minh caller được gọi đúng nhóm thao tác. Hãy lập ma trận theo endpoint và method, không chỉ theo controller hoặc URL prefix.

| Operation | Anonymous | Customer | Support | Tenant admin | Internal service |
|---|---:|---:|---:|---:|---:|
| `GET /orders/{id}` | Deny | Own object | Assigned scope | Policy-defined | Contract-defined |
| `POST /orders` | Deny | Allow | Deny | Policy-defined | Allow nếu được giao |
| `PATCH /orders/{id}/address` | Deny | Own object, state hợp lệ | Theo policy | Theo policy | Deny nếu không cần |
| `POST /orders/{id}/refund` | Deny | Deny | Có permission + approval | Có permission + approval | Chỉ refund service |
| `POST /tenants/{id}/members` | Deny | Deny | Deny | Own tenant | Identity service |
| `DELETE /admin/users/{id}` | Deny | Deny | Theo quyền riêng | Không mặc định | Admin service |

Các giá trị “Policy-defined” cần được thay bằng quyết định cụ thể trước khi hoàn thiện test. Không để ô trống được hiểu ngầm là allow. Mặc định nên là deny khi principal, route hoặc policy không xác định.

Kiểm thử cả chiều ngang và chiều dọc:

- **Vertical privilege escalation:** user thường thử gọi chức năng admin, support hoặc operator.
- **Horizontal privilege escalation:** user cùng role thử truy cập object của user khác.
- **Cross-tenant access:** principal hợp lệ ở tenant A thử đọc/ghi object của tenant B.
- **Service identity misuse:** service hợp lệ gọi operation vượt scope hoặc giả mạo user/tenant khác.

## 4. Thiết kế test data có thể phát hiện lỗi

Test fixture cần chứa đủ đối tượng để phân biệt allow và deny. Một fixture chỉ có một user và một object thường không phát hiện được IDOR hoặc tenant isolation failure.

Ví dụ fixture tối thiểu:

| Principal | Role | Tenant | Object |
|---|---|---|---|
| `alice` | Customer | `tenant-A` | Own order `order-A1` |
| `bob` | Customer | `tenant-A` | Own order `order-A2` |
| `carol` | Customer | `tenant-B` | Own order `order-B1` |
| `support-1` | Support | Scope `tenant-A` | Assigned case `case-A1` |
| `admin-A` | Tenant admin | `tenant-A` | Members of tenant A |
| `fulfillment-A` | Service identity | `tenant-A` | Assigned shipment `ship-A1` |
| `anonymous` | None | None | None |

Với fixture này có thể test:

- Alice đọc `order-A1`: allow.
- Alice đọc `order-A2`: deny dù cùng tenant và cùng resource type.
- Alice đọc `order-B1`: deny vì khác tenant.
- Carol đọc `order-B1`: allow.
- Support đọc case được phân công: allow; đọc case ngoài scope: deny.
- Fulfillment service cập nhật trạng thái shipment được giao: allow; cập nhật payment/refund: deny.
- Anonymous đọc bất kỳ order riêng tư nào: deny.

Giữ fixture đơn giản và đặt tên thể hiện tenant/owner. Không dùng một ID ngẫu nhiên mà test author không thể nhìn ra object thuộc ai. Test cần kiểm tra cả kết quả lẫn việc database không bị thay đổi khi request bị từ chối.

## 5. Test object-level authorization và IDOR/BOLA

BOLA thường xuất hiện khi API lấy object bằng ID do client cung cấp nhưng không kiểm tra caller có quan hệ hợp lệ với object đó hay không.

Ví dụ endpoint:

```http
GET /api/orders/order-A2
Authorization: Bearer <alice-token>
```

Alice có token hợp lệ và role `CUSTOMER`, nhưng `order-A2` thuộc Bob. Test phải chứng minh request bị từ chối hoặc được che giấu theo contract, dù ID là UUID khó đoán hay số tuần tự.

Các ca cần kiểm tra:

- Thay object ID bằng ID của user khác trong cùng tenant.
- Thay object ID bằng ID của tenant khác.
- Đổi ID trong path, query, body, nested resource hoặc bulk list.
- Gọi endpoint phụ như download, export, attachment, history, comments hoặc sub-resource.
- Dùng ID trong GraphQL argument, RPC message hoặc job payload nếu cùng domain có nhiều giao thức.
- Thử object đã bị xóa, archived, transferred hoặc trạng thái không còn quyền truy cập.

Đừng chỉ test `GET`. BOLA có thể tồn tại ở `PATCH`, `DELETE`, `POST /{id}/approve`, `POST /{id}/download` và các operation tạo side effect.

## 6. Test tenant isolation trên mọi đường dữ liệu

Tenant isolation phải được kiểm tra xuyên suốt query và luồng xử lý, không chỉ ở endpoint đọc chi tiết.

| Đường truy cập | Ca test cross-tenant |
|---|---|
| Detail/read | Tenant A yêu cầu object ID thuộc B. |
| List/search | Tenant A thay filter, sort hoặc search term để tìm record của B. |
| Create | Tenant A gửi `tenantId=B` trong body hoặc header. |
| Update | Tenant A cập nhật object B hoặc đổi `tenantId` của object A thành B. |
| Delete/archive | Tenant A xóa hoặc archive object B. |
| Bulk operation | Một batch chứa cả object A và object B. |
| Export/report | Tenant A yêu cầu export với filter hoặc report scope của B. |
| Attachment/download | Tenant A dùng file ID hoặc signed URL reference của B. |
| Background job | Job được tạo bởi tenant A nhưng payload chứa resource của B. |
| Cache | Response cache của A được phục vụ cho B hoặc ngược lại. |
| Event/message | Consumer xử lý event có tenant context không khớp resource ownership. |

Tenant context phải đến từ principal/identity đã xác minh hoặc mapping do server quản lý. Không tin `tenantId` trong request body, query string hay header do caller tự đặt. Nếu API cho phép admin/service cross-tenant, phải có permission riêng, scope rõ và audit event.

Với bulk request có một object không được phép, contract cần quyết định xử lý toàn bộ batch hay chỉ bỏ qua item bị cấm. Test phải xác minh không có partial side effect ngoài quy định. Nếu fail atomically, kiểm tra tất cả record đều không đổi khi một item bị từ chối.

## 7. Test property-level authorization và mass assignment

Một caller có thể được phép sửa object nhưng chỉ được sửa một số field. Ví dụ customer được cập nhật địa chỉ giao hàng nhưng không được sửa `ownerId`, `tenantId`, `paymentStatus`, `totalAmount`, `role` hoặc `approvedBy`.

Test cần kiểm tra cả dữ liệu trả về lẫn field được ghi:

- Response không lộ field nhạy cảm mà role đó không được đọc.
- Request có field ngoài allowlist bị từ chối hoặc bỏ qua theo contract rõ ràng.
- Server-owned field không bị thay đổi qua mass assignment.
- Nested object/list cũng áp dụng property authorization.
- Field chỉ đọc không bị thay đổi khi gửi trong `PATCH`/`PUT`.
- Field nhạy cảm chỉ được sửa bởi role/approval phù hợp.

Ví dụ request độc hại:

```json
{
  "shippingAddress": "12 Example Street",
  "ownerId": "attacker-user",
  "tenantId": "tenant-B",
  "paymentStatus": "PAID",
  "totalAmount": 1,
  "approved": true
}
```

Sau khi request bị xử lý, test phải đọc lại record từ database và xác minh chỉ `shippingAddress` thay đổi. Không chỉ kiểm tra HTTP `200` hoặc `400`; một response lỗi vẫn có thể xuất hiện sau khi một phần field đã được ghi.

## 8. Test điều kiện nghiệp vụ và ABAC

Role không phải yếu tố duy nhất trong quyết định authorization. Policy có thể phụ thuộc vào trạng thái, thời gian, quan hệ, approval hoặc risk context.

Ví dụ quyền hủy đơn có thể là:

```text
ALLOW order.cancel IF
    principal.role == CUSTOMER
    AND order.owner_id == principal.user_id
    AND order.tenant_id == principal.tenant_id
    AND order.status IN [CREATED, CONFIRMED]
    AND current_time < order.cancel_deadline
```

Test từng điều kiện riêng và tổ hợp:

- Đúng owner, đúng tenant, trạng thái cho phép: allow.
- Sai owner nhưng đúng tenant: deny.
- Đúng owner nhưng sai tenant context: deny.
- Đúng owner/tenant nhưng trạng thái đã `SHIPPED`: deny.
- Đúng owner/tenant nhưng quá deadline: deny.
- Thiếu thuộc tính hoặc policy input không xác định: deny hoặc chuyển quy trình xử lý đã định nghĩa.

Với operation cần approval, test người yêu cầu không thể tự phê duyệt nếu separation of duties yêu cầu hai principal khác nhau. Test approval hết hạn, bị thu hồi, áp dụng cho object khác hoặc đã được dùng cho một operation khác.

## 9. Test policy ở API boundary và service layer

Authorization có thể được triển khai ở gateway, Spring Security filter, method security, service hoặc repository query. Test cần xác minh enforcement thực sự tại ranh giới mà hệ thống dựa vào.

Một chiến lược thường gồm:

1. **Policy/unit test:** kiểm tra hàm quyết định quyền với principal, action, resource và context cụ thể.
2. **Service test:** gọi service method với nhiều principal/role/tenant và xác minh object-level/property-level rules.
3. **API integration test:** gửi HTTP request qua security filter chain, routing, controller, service và database test.
4. **End-to-end test:** kiểm tra luồng caller thực tế qua gateway và service khi policy phân tán nhiều tầng.
5. **Regression/security test:** giữ lại các ca BOLA/BFLA/cross-tenant từng phát hiện để chạy lại ở CI.

Không chỉ test annotation `@PreAuthorize` hoặc mock `AuthorizationService`. Cần có integration test chứng minh route thật không bỏ qua filter, method mapping, object lookup hoặc transaction boundary.

## 10. Ví dụ Spring: service kiểm tra object và tenant

Một service có thể nhận principal đã xác minh và truy vấn object theo tenant, sau đó kiểm tra ownership/relationship:

```java
@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDto getOrder(CurrentPrincipal principal, UUID orderId) {
        Order order = orders
            .findByIdAndTenantId(orderId, principal.tenantId())
            .orElseThrow(OrderNotFoundException::new);

        boolean isOwner = order.getOwnerId().equals(principal.userId());
        boolean isAssignedSupport = principal.hasAuthority("order:support:read")
            && principal.assignedTenantIds().contains(order.getTenantId());

        if (!isOwner && !isAssignedSupport) {
            throw new AccessDeniedException("Order access denied");
        }

        return OrderDto.from(order);
    }
}
```

Ví dụ minh họa cần được điều chỉnh theo policy thực tế. `CurrentPrincipal` phải được tạo từ authentication context tin cậy, không map trực tiếp từ body/header do caller gửi. Query theo tenant giúp thu hẹp dữ liệu; kiểm tra owner/assigned scope quyết định quyền object-level. Việc dùng `404` thay vì `403` để che giấu object existence là lựa chọn API policy cần nhất quán.

Một repository method như `findByIdAndTenantId` không thay thế mọi authorization: trong cùng tenant vẫn có thể có nhiều owner và role khác nhau. Ngược lại, kiểm tra owner trong Java nhưng query object không giới hạn tenant có thể làm lộ dữ liệu qua exception, cache hoặc side path. Nên dùng cả query scope lẫn policy check khi phù hợp.

## 11. Ví dụ test service với JUnit

Các test sau minh họa kiểm tra owner, same-tenant user và cross-tenant user:

```java
@ExtendWith(MockitoExtension.class)
class OrderQueryServiceTest {
    @Mock OrderRepository orders;
    private OrderQueryService service;

    @BeforeEach
    void setUp() {
        service = new OrderQueryService(orders);
    }

    @Test
    void ownerCanReadOwnOrder() {
        UUID tenantA = UUID.randomUUID();
        UUID alice = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        Order order = order(orderId, tenantA, alice);
        when(orders.findByIdAndTenantId(orderId, tenantA))
            .thenReturn(Optional.of(order));

        CurrentPrincipal principal = customer(alice, tenantA);

        assertThat(service.getOrder(principal, orderId)).isNotNull();
    }

    @Test
    void anotherCustomerInSameTenantCannotReadOrder() {
        UUID tenantA = UUID.randomUUID();
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        when(orders.findByIdAndTenantId(orderId, tenantA))
            .thenReturn(Optional.of(order(orderId, tenantA, bob)));

        assertThatThrownBy(() -> service.getOrder(
            customer(alice, tenantA), orderId))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void otherTenantCannotResolveOrder() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID alice = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        when(orders.findByIdAndTenantId(orderId, tenantA))
            .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getOrder(
            customer(alice, tenantA), orderId))
            .isInstanceOf(OrderNotFoundException.class);
    }
}
```

`order(...)` và `customer(...)` là fixture helpers cần định nghĩa trong test. Trong test cross-tenant, repository mock trả empty cho tenant hiện tại để mô phỏng query có tenant scope. Nên bổ sung integration test với database thật/test container để xác minh SQL/query filter và mapping tenant hoạt động, vì mock không thể chứng minh database predicate đúng.

## 12. API integration test phải kiểm tra response và side effect

Ví dụ với Spring MockMvc, test cần gửi request như client thật và xác minh database không thay đổi khi bị deny. Cấu hình test phải dùng cùng security filter chain và method security như production.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationIT {
    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;

    @Test
    void customerCannotReadAnotherUsersOrder() throws Exception {
        TestData data = createAliceAndBobsOrder();

        mvc.perform(get("/api/orders/{id}", data.bobOrderId())
                .with(jwt().jwt(jwt -> jwt
                    .subject(data.aliceId().toString())
                    .claim("tenant_id", data.tenantA().toString())
                    .claim("roles", List.of("CUSTOMER")))))
            .andExpect(status().isForbidden());
    }
}
```

Đây là ví dụ dùng Spring Security test support; custom `JwtAuthenticationConverter` và test fixture phải khớp cấu hình ứng dụng. Nếu API cố ý trả `404` để che giấu object, assertion phải theo contract đó. Bổ sung assertion rằng record không đổi và không có event/email/payment side effect được tạo.

Không dùng `@WithMockUser` một cách máy móc nếu production authorization dựa vào JWT claims, tenant context, client identity hoặc custom principal. Mock user có thể bỏ qua lỗi mapping role/scope thực tế. Ít nhất một nhóm integration test nên đi qua cơ chế xác thực tương đương production với token test được ký bởi test issuer.

## 13. Test bulk, pagination, search và cache

Object authorization dễ bị bỏ sót ở endpoint trả nhiều record. Một detail endpoint có thể kiểm tra owner đúng, trong khi list/export dùng repository query thiếu tenant predicate.

Các test cần có:

- List chỉ trả object trong tenant và ownership scope được phép.
- Search/filter không thể suy ra object của tenant khác qua count, facet, autocomplete hoặc error detail.
- Pagination không làm rò record khi đổi cursor/page token.
- Sort field hoặc filter expression không thể truy cập field bị cấm.
- Bulk operation không thực hiện trên object ngoài scope.
- Export/report áp cùng policy như detail endpoint.
- Cache key có đủ principal/tenant/security context; response riêng tư không bị dùng chung giữa caller.
- Download/signed URL chỉ được tạo sau authorization và gắn đúng object, method, expiry.

Kiểm tra side channel khi cần: response time, record count, error differences hoặc identifier existence có thể tiết lộ object ngoài quyền. Chọn `403` hay `404` theo policy nhất quán và không để response phụ tiết lộ dữ liệu đã che giấu.

## 14. Test deny-by-default và route coverage

Khi thêm endpoint mới, lỗi thường xảy ra vì route chưa được đưa vào policy hoặc bị rule tổng quát cho phép. Hãy kiểm tra toàn bộ route/method thay vì chỉ test các endpoint đã biết.

- Request không có identity: deny ở mọi route riêng tư.
- Token hợp lệ nhưng thiếu scope: deny operation cần scope.
- Role không được biết hoặc claim malformed: deny, không map thành quyền mặc định.
- Policy engine không có rule hoặc gặp lỗi: failure mode phải rõ; với dữ liệu nhạy cảm thường fail closed.
- HTTP method mới hoặc route alias không vô tình kế thừa quyền rộng.
- `OPTIONS` preflight được xử lý đúng nhưng không cấp quyền cho actual request.
- Management/actuator/debug endpoints có policy riêng và không mở chỉ vì nằm ngoài `/api/**`.
- Route được expose qua version mới hoặc gateway alias vẫn giữ cùng authorization contract.

Có thể sinh danh sách route từ framework/OpenAPI trong CI để so sánh với policy inventory. Nếu route không có test/policy owner, yêu cầu review trước khi merge. Không coi coverage theo dòng code là coverage authorization.

## 15. Property-based và parameterized authorization tests

Parameterized tests giúp chạy cùng policy với nhiều principal/resource combinations. Property-based testing có thể sinh tenant, owner, role và ID để tìm trường hợp bị bỏ sót.

Một số invariant hữu ích:

- User không phải owner và không có permission đặc biệt không thể đọc hoặc sửa object.
- Principal ở tenant A không thể thay đổi object tenant B dù ID hợp lệ.
- Thêm field server-owned vào request không làm thay đổi field đó.
- Caller bị deny không tạo domain event hoặc downstream side effect.
- Role/scope ít quyền hơn không thể thực hiện operation mà role/scope cao hơn mới được phép.
- Khi tenant/resource context thiếu hoặc không hợp lệ, policy không chuyển thành allow.
- Một bulk request không thể vượt tenant boundary bằng cách trộn ID.

Không sinh dữ liệu hoàn toàn ngẫu nhiên mà thiếu oracle. Test phải biết expected decision từ policy model. Có thể tạo decision table rồi chạy từng row qua policy engine và API integration suite.

## 16. Ma trận test tổng hợp

Một ma trận tối thiểu cho mỗi resource/action nên bao gồm:

| Chiều | Positive case | Negative case |
|---|---|---|
| Authentication | Principal hợp lệ, issuer/audience/scope đúng. | Anonymous, token sai/hết hạn, issuer/audience sai. |
| Role/function | Role được phép gọi operation. | Role thấp hơn hoặc service sai chức năng. |
| Object | Owner/assignee được phép. | Object của user khác hoặc không có relationship. |
| Tenant | Tenant context khớp resource. | ID tenant bị thay, object thuộc tenant khác. |
| Property | Field được phép đọc/ghi. | Field nhạy cảm hoặc server-owned bị yêu cầu thay đổi. |
| Context/state | Approval, thời hạn và trạng thái hợp lệ. | Approval thiếu/hết hạn, state transition không hợp lệ. |
| Bulk/list/export | Chỉ object trong scope được trả/xử lý. | Trộn object ngoài scope hoặc filter/cursor vượt tenant. |
| Side effect | Operation hợp lệ tạo đúng một tác động. | Denied request không thay đổi DB, phát event hoặc gọi downstream. |
| Failure mode | Policy service hoạt động và quyết định rõ. | Policy input thiếu, dependency lỗi hoặc rule không tồn tại. |

Không nhất thiết mọi operation cần cùng số test. Operation có dữ liệu nhạy cảm, tài chính, quyền admin hoặc side effect lớn cần nhiều negative cases và integration coverage hơn endpoint đọc dữ liệu công khai.

## 17. Anti-pattern trong authorization testing

| Anti-pattern | Vì sao test không đủ | Cách cải thiện |
|---|---|---|
| Chỉ test anonymous nhận 401 | Không kiểm tra user hợp lệ nhưng sai quyền. | Test role, object, tenant và property. |
| Chỉ test role ở controller | Bỏ sót object ownership và tenant isolation. | Test service/repository và API với object của principal khác. |
| Chỉ dùng một tenant/one user fixture | Không thể phát hiện cross-user/cross-tenant. | Tạo ít nhất hai user cùng tenant và hai tenant. |
| Chỉ test GET | Update/delete/export/bulk có thể thiếu policy. | Ma trận theo method và side effect. |
| Chỉ assert status code | Có thể đã ghi dữ liệu trước khi trả lỗi. | Assert DB, outbox, message và downstream call. |
| Mock toàn bộ repository | Bỏ qua tenant predicate và query behavior thật. | Thêm integration test với database thật/test container. |
| Mock principal không giống production | Không phát hiện lỗi JWT claim/role mapping. | Test với security filter chain và token test thực. |
| Test policy nhưng không test route | Endpoint có thể không gọi policy service. | API integration và route coverage. |
| Dùng UUID khó đoán làm bằng chứng an toàn | ID vẫn có thể lộ qua log, URL hoặc relationship. | Authorization bắt buộc dù ID ngẫu nhiên. |
| Không kiểm tra field update | Mass assignment có thể nâng quyền hoặc đổi tenant. | Test allowlist field và đọc lại database. |
| Không test cache/bulk/job | Policy bị bỏ qua ở đường phụ. | Mở rộng test theo toàn bộ data path. |

## 18. Đưa authorization test vào CI/CD

Một pipeline có thể chia test theo tốc độ và phạm vi:

1. **Unit/policy tests:** chạy nhanh cho decision table, role mapping và condition rules.
2. **Service tests:** kiểm tra object, tenant, property và business state.
3. **API integration tests:** chạy security filters, routing, persistence và side effects.
4. **Contract/route coverage:** xác nhận mọi endpoint/method có policy và test phù hợp.
5. **Security regression suite:** giữ các case BOLA/BFLA/BOPLA, cross-tenant và privilege escalation từng phát hiện.
6. **Staging verification:** kiểm tra gateway, token issuer, service identity, cache và background worker theo môi trường gần production.

Pull request thay đổi endpoint, DTO, role, scope, repository query, tenant mapping hoặc gateway route cần chạy bộ test liên quan. Không chỉ chạy test khi sửa file security config; một thay đổi DTO hoặc list query cũng có thể tạo lỗ hổng authorization.

Đặt release gate cho các lỗi nghiêm trọng: unauthorized read/write, cross-tenant access, privilege escalation, field tampering và side effect sau deny. Test flaky cần được xử lý rõ; không bỏ qua test bảo mật chỉ để pipeline xanh.

## 19. Đo coverage và duy trì test theo vòng đời API

Coverage authorization nên đo theo policy và operation, không chỉ line coverage. Có thể theo dõi:

- Tỷ lệ route/method có owner, policy và expected deny/allow cases.
- Tỷ lệ resource/action có test owner, same-tenant other-user và cross-tenant.
- Tỷ lệ field nhạy cảm/server-owned có property-level test.
- Tỷ lệ bulk/list/export/background path được kiểm tra tenant scope.
- Tỷ lệ negative test xác minh không có side effect.
- Số regression case từ incident/security review còn chạy trong CI.
- Policy decision coverage: mỗi rule/branch quan trọng đã được test allow và deny chưa?

Khi API thay đổi lifecycle, cập nhật test cùng lúc với contract/policy. Thêm role mới cần đánh giá quyền mặc định; thêm tenant relationship cần kiểm tra data migration; thêm endpoint version mới cần kế thừa policy có chủ đích; xóa role cần xác minh token cũ và cache quyền được xử lý đúng.

## 20. Checklist authorization test theo role, object và tenant

- [ ] Mỗi endpoint/method có policy mô tả principal, action, resource và điều kiện?
- [ ] Có role/function matrix cho anonymous, user, partner, admin và service identity?
- [ ] Fixture có ít nhất hai user cùng tenant và hai tenant khác nhau?
- [ ] Test positive và negative cho owner, non-owner, assignee và support scope?
- [ ] Có BOLA/IDOR tests khi thay ID trong path, body, query, nested resource và bulk list?
- [ ] Có cross-tenant tests cho read, list, create, update, delete, export, file và background job?
- [ ] Có property-level tests cho response field, mass assignment và server-owned fields?
- [ ] Có test vertical/horizontal privilege escalation và service scope misuse?
- [ ] Có test ABAC theo state, time, approval và missing context?
- [ ] Có test deny-by-default cho route mới, method mới và policy missing/error?
- [ ] Có integration test với security filter chain, database và tenant query thật?
- [ ] Request bị deny được xác minh không tạo DB update, message hoặc downstream side effect?
- [ ] Bulk, pagination, search, cache, export và download dùng cùng authorization boundary?
- [ ] CI theo dõi route/policy coverage và giữ regression cases bảo mật?
- [ ] Có owner rà soát test khi role, tenant model, DTO hoặc API version thay đổi?

Authorization test có giá trị khi chứng minh cả người được phép lẫn người không được phép. Hãy xây dựng test matrix từ role/function, object relationship, tenant boundary, property và business context; dùng fixture nhiều user/nhiều tenant; kiểm tra mọi đường đọc/ghi và xác minh side effect. Kết hợp policy unit test với service và API integration test để phát hiện lỗi ở cả rule lẫn điểm thực thi. Khi endpoint, DTO hoặc tenant model thay đổi, test phải thay đổi cùng để ngăn BOLA, BFLA, BOPLA và privilege escalation quay trở lại.
