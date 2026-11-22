# Test broken function authorization

## 1. Mục tiêu của bài kiểm thử

Broken Function Level Authorization (BFLA) xảy ra khi một principal gọi được chức năng mà principal đó không được phép sử dụng. Ví dụ, user thông thường gọi endpoint quản trị, partner gọi chức năng nội bộ, hoặc service chỉ được đọc dữ liệu nhưng lại gọi được thao tác xóa.

Lỗi này thường xuất hiện khi hệ thống:

- Chỉ kiểm tra user đã đăng nhập mà không kiểm tra quyền của function.
- Dựa vào việc ẩn nút hoặc menu trên giao diện.
- Bảo vệ một HTTP method nhưng bỏ sót method khác trên cùng route.
- Áp dụng role ở một số controller nhưng quên endpoint mới hoặc endpoint cũ.
- Có route admin, export, bulk operation hoặc internal API không nằm trong ma trận quyền.
- Dùng gateway policy nhưng service vẫn mở đường gọi trực tiếp.
- Cho phép service account hoặc partner dùng quyền rộng hơn nhu cầu.
- Kiểm tra quyền ở request ban đầu nhưng không kiểm tra lại khi chạy job bất đồng bộ.

Mục tiêu kiểm thử là chứng minh mỗi function chỉ được gọi bởi principal có permission phù hợp, trên đúng bề mặt API và trong đúng ngữ cảnh. Kiểm thử phải chứng minh cả hai phía: principal được phép có thể thực hiện chức năng hợp lệ; principal không được phép bị từ chối và không tạo side effect.

Trong OWASP API Security Top 10 2023, Broken Function Level Authorization được xếp ở API5. Đây là lỗi authorization ở cấp chức năng. Cần phân biệt nó với Broken Object Level Authorization (BOLA), nơi caller được gọi function nhưng truy cập object không thuộc quyền của mình. Một request có thể đồng thời mắc cả hai lỗi, vì vậy test suite nên kiểm tra hai chiều độc lập.

## 2. Phân biệt authentication, function authorization và object authorization

Ba câu hỏi cần được kiểm tra riêng:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi? | Token xác định user Alice |
| Function authorization | Principal có được gọi hành động này không? | Alice có permission users:read nhưng không có users:delete |
| Object authorization | Principal có được thực hiện hành động trên object này không? | Alice được xem user trong tenant A nhưng không được sửa user của tenant B |

Một token hợp lệ chỉ chứng minh danh tính hoặc client identity theo cơ chế xác thực. Nó không tự cấp quyền gọi mọi endpoint.

Ví dụ:

- GET /api/users có thể yêu cầu users:read.
- POST /api/users có thể yêu cầu users:create.
- DELETE /api/users/{id} có thể yêu cầu users:delete.
- POST /api/admin/users/{id}/disable có thể yêu cầu users:admin:disable.

Không suy ra quyền chỉ từ việc user có role USER, ADMIN hoặc đã đăng nhập. Role phải được ánh xạ tới permission cụ thể và policy phải được thực thi ở server.

## 3. Xác định phạm vi kiểm thử và quy tắc an toàn

Trước khi test, xác nhận:

- Host, environment, API version và service thuộc phạm vi được phép.
- Các principal/test account và role được cấp.
- Endpoint có thể tạo dữ liệu thật, gửi email, hoàn tiền, khóa tài khoản hoặc gọi hệ thống ngoài hay không.
- Giới hạn request rate và khối lượng test.
- Cách tạo fixture, cleanup và theo dõi side effect.
- Endpoint nào là admin/internal và cần test trong môi trường riêng.
- Có được phép kiểm thử trực tiếp upstream hoặc broker hay chỉ qua gateway.

Ưu tiên staging hoặc test tenant với dữ liệu giả. Không thử chức năng phá hủy trên production nếu chưa có kế hoạch và phê duyệt riêng. Với chức năng gửi email, thanh toán, xóa dữ liệu hoặc phát event, dùng sandbox/fake provider và xác minh không có side effect ngoài ý muốn.

Kết quả test cần ghi rõ thời gian, environment, route, principal, permission set và request ID. Không lưu access token, password, API key hoặc dữ liệu cá nhân thật trong test report.

## 4. Lập inventory function trước khi kiểm thử

Không thể test đầy đủ nếu chỉ có danh sách URL. Cần lập danh mục function/action mà API thực hiện:

| Trường | Nội dung |
|---|---|
| Service và API version | Service sở hữu function, version được expose |
| Operation ID | Định danh ổn định trong contract |
| Method và route | HTTP method + path template |
| Function/action | Ý nghĩa nghiệp vụ, không chỉ tên URL |
| Required permission | Permission cần để gọi function |
| Allowed principal | User, admin, partner, service account hoặc system |
| Exposure | Public, partner, internal, admin |
| Object/tenant scope | Phạm vi dữ liệu áp dụng sau function authorization |
| Side effect | Read, write, delete, export, payment, event hoặc job |
| Owner | Nhóm chịu trách nhiệm và người phê duyệt |
| Lifecycle | Active, deprecated, retired |

Ví dụ inventory:

| Operation | Method/path | Permission | Principal được phép |
|---|---|---|---|
| listUsers | GET /api/users | users:read | Support, Admin |
| createUser | POST /api/users | users:create | Admin |
| disableUser | POST /api/users/{id}/disable | users:disable | Admin, SecurityOperator |
| exportUsers | POST /api/users/export | users:export | ComplianceAdmin |
| viewAudit | GET /api/audit | audit:read | Auditor, SecurityAdmin |
| rotateClientSecret | POST /api/clients/{id}/rotate-secret | clients:secret:rotate | SecurityAdmin |

Inventory cần lấy từ contract, gateway route, source/runtime mapping và business owner. Chỉ lấy từ OpenAPI có thể bỏ sót route không được document; chỉ lấy từ UI có thể bỏ sót function mà client có thể gọi trực tiếp.

## 5. Xây dựng permission model có thể kiểm thử

Permission nên mô tả hành động rõ ràng trên resource:

~~~text
users:read
users:create
users:update
users:disable
users:delete
users:export
audit:read
clients:secret:rotate
payments:refund
roles:assign
~~~

Role là tập permission được gán cho principal. Ví dụ:

| Role | Permission tiêu biểu |
|---|---|
| Viewer | users:read |
| Support | users:read, tickets:read, tickets:update |
| Admin | users:read, users:create, users:update, users:disable |
| ComplianceAdmin | users:read, users:export, audit:read |
| SecurityAdmin | audit:read, clients:secret:rotate, roles:assign |
| ServiceAccount | Chỉ các permission dành riêng cho workload đó |

Không dùng role name như một chuỗi tự do trong nhiều nơi rồi giả định semantics giống nhau. Có một policy registry hoặc một nguồn định nghĩa permission rõ ràng. Test phải kiểm tra mapping role-to-permission và việc mapping đó được thực thi ở API.

Với ABAC, permission còn phụ thuộc attribute như tenant, environment, resource classification, approval state hoặc thời gian. Khi đó test case cần cố định attribute để chứng minh policy decision có thể tái lập.

## 6. Ma trận principal và function

Ma trận là nền tảng cho negative testing:

| Principal | Read | Create | Update | Disable/Delete | Export | Admin/Secret |
|---|---:|---:|---:|---:|---:|---:|
| Anonymous | Deny | Deny | Deny | Deny | Deny | Deny |
| BasicUser | Theo policy | Deny | Chỉ self nếu cho phép | Deny | Deny | Deny |
| Support | Allow giới hạn | Deny | Ticket/profile giới hạn | Deny | Deny | Deny |
| Admin | Allow | Allow | Allow | Theo policy | Không mặc định | Không mặc định |
| ComplianceAdmin | Allow theo scope | Deny | Deny | Deny | Allow | Audit read |
| SecurityAdmin | Theo policy | Theo policy | Theo policy | Theo policy | Theo policy | Allow có kiểm soát |
| ServiceAccount A | Chỉ function của service | Chỉ action được cấp | Chỉ action được cấp | Deny mặc định | Deny mặc định | Deny mặc định |

Các ô “theo policy” phải được thay bằng permission cụ thể trước khi test. Không dùng bảng ma trận mơ hồ làm tiêu chí pass/fail.

Với mỗi cặp principal-function, xác định expected allow/deny. Test ít nhất:

1. Principal không có permission.
2. Principal có permission đúng.
3. Principal có permission gần giống nhưng không đủ, ví dụ users:read không được thay cho users:delete.
4. Principal có role khác nhưng cùng đăng nhập.
5. Service account của service khác.
6. Token thiếu scope hoặc có audience không đúng.

## 7. Tạo test principal có quyền khác nhau

Chuẩn bị account/credential test riêng:

- Anonymous: không có credential.
- Basic user: chỉ có quyền người dùng thông thường.
- Support: có một số quyền hỗ trợ.
- Admin: quyền quản trị được giới hạn theo test fixture.
- Compliance/Auditor: chỉ có quyền đọc hoặc export được phê duyệt.
- Service account A/B: đại diện hai workload khác nhau.
- Partner client: chỉ có permission trong hợp đồng tích hợp.
- Revoked/expired principal: credential đã hết hạn hoặc bị thu hồi.

Không dùng một admin token cho toàn bộ test rồi chỉ thay header role. Credential phải được phát hành bởi test identity provider hoặc test fixture đáng tin cậy. Nếu test tự ký JWT, khóa test chỉ được dùng trong môi trường kiểm thử và verifier phải chạy qua cùng code path với production.

Ghi lại principal ID giả lập, role, permission, tenant fixture và trạng thái credential. Tạo test độc lập để tránh một test cấp role làm ảnh hưởng test tiếp theo.

## 8. Kiểm thử truy cập function quản trị bằng principal thường

Đây là negative test cốt lõi của BFLA:

1. Đăng nhập bằng BasicUser hoặc Support.
2. Gọi trực tiếp admin endpoint đã được inventory.
3. Thử các method được route hỗ trợ.
4. Quan sát status, body và header.
5. Xác minh database, queue, audit record và downstream không có side effect trái phép.
6. Lặp lại bằng Admin để chứng minh test endpoint hoạt động và policy cho phép đúng principal.

Ví dụ:

~~~http
POST /api/admin/users/42/disable HTTP/1.1
Authorization: Bearer <basic-user-test-token>
Content-Type: application/json
~~~

Kết quả mong đợi là request bị từ chối theo contract, thường là 403 hoặc 404 nếu hệ thống có chính sách che giấu function/resource. Quan trọng hơn, user 42 không bị disable, không có job được tạo và không có event nghiệp vụ được publish.

Không chỉ kiểm tra endpoint có chữ admin trong path. Function đặc quyền có thể nằm ở route thông thường như POST /api/users/{id}/reset-password hoặc PATCH /api/settings.

## 9. Kiểm thử từng HTTP method trên cùng route

Một route có thể expose nhiều method với quyền khác nhau:

~~~text
GET    /api/users/{id}       -> users:read
PATCH  /api/users/{id}       -> users:update
DELETE /api/users/{id}       -> users:delete
POST   /api/users/{id}/reset -> users:password:reset
~~~

Test từng method độc lập. Không giả định bảo vệ GET đồng nghĩa đã bảo vệ PATCH/DELETE. Cũng không giả định method không có trong contract chắc chắn bị từ chối nếu framework hoặc proxy có route fallback.

Các tình huống cần thử:

- Method được phép nhưng thiếu permission.
- Method đặc quyền với principal thường.
- Method không được công bố.
- HEAD/OPTIONS và CORS preflight theo policy.
- Method override qua header/query nếu stack có hỗ trợ.
- Content-Type hoặc route rewrite khiến request đi vào handler khác.

Xác minh method không được hỗ trợ không tạo side effect. 405 là response thường gặp khi path tồn tại nhưng method không được phép; 404 có thể được dùng theo contract để che route. Không đánh giá chỉ bằng status nếu body hoặc state cho thấy handler vẫn chạy.

## 10. Kiểm thử alias, route biến thể và route precedence

Một function có thể được expose qua nhiều route:

- /admin/users và /api/users/admin.
- /v1/users/{id}/disable và /v2/users/{id}/status.
- Route legacy, alias hoặc compatibility endpoint.
- Route nội bộ qua ingress/service mesh.
- Route có trailing slash, case variation hoặc encoded path.

Tìm mọi đường gọi tới cùng function và xác minh policy tương đương. Nếu một alias cũ thiếu authorization annotation hoặc gateway rule, attacker có thể đi vòng route mới.

Kiểm tra:

- Static path và parameter path có collision không.
- Trailing slash/case/percent encoding có map sang handler khác không.
- Route rewrite có bỏ prefix hoặc đổi method không.
- Gateway và application có cùng cách canonicalize path không.
- Route deprecated/legacy có còn gọi được không.

Không fuzz tùy tiện trên production. Dùng staging, route inventory và giới hạn request để kiểm tra các biến thể đã xác định.

## 11. Kiểm thử quyền trên function ẩn khỏi UI

Ẩn menu hoặc nút trên giao diện không phải authorization control. Client có thể gọi API bằng curl, Postman, script, mobile proxy hoặc sửa JavaScript.

Test:

1. Lấy request hợp lệ từ browser/app bằng principal thường.
2. Gọi trực tiếp endpoint chức năng bị ẩn.
3. Thử sửa method, path và body để kích hoạt action.
4. Gọi endpoint từ client không dùng UI.
5. Xác minh server từ chối và không tạo side effect.

Các function thường bị bỏ quên:

- User/role administration.
- Export/download dữ liệu hàng loạt.
- Impersonate hoặc switch account.
- Reset password, revoke session, rotate secret.
- Approve/reject/refund/close transaction.
- Restore/archive/delete.
- Feature flag hoặc configuration management.
- Audit log và security report.

UI có thể tiếp tục ẩn chức năng để cải thiện trải nghiệm, nhưng quyền phải được kiểm tra ở server cho mọi request.

## 12. Kiểm thử bulk operation và export

Bulk endpoint thường có quyền rộng hơn endpoint đơn:

~~~http
POST /api/users/bulk-disable
POST /api/reports/export
POST /api/payments/bulk-refund
~~~

Không suy ra quyền bulk từ quyền thao tác trên một object. Export có thể làm lộ nhiều dữ liệu; bulk disable có thể ảnh hưởng nhiều account; bulk refund có thể tạo side effect tài chính.

Test:

- Principal có users:read nhưng không có users:export.
- Principal có users:disable trên phạm vi hẹp nhưng không có bulk-disable permission.
- Request chứa danh sách ID vượt phạm vi được phép.
- Một phần tử không được phép trong batch.
- Batch có kích thước lớn hoặc nhiều tenant.
- Retry cùng request hoặc job.

Xác định rõ semantics all-or-nothing hay partial success. Nếu partial, response phải chỉ rõ item nào bị từ chối mà không tiết lộ object ngoài quyền; các item bị từ chối không được thay đổi. Nếu all-or-nothing, không item nào được commit khi authorization của một item thất bại.

## 13. Kiểm thử function thay đổi trạng thái nghiệp vụ

Một function có thể yêu cầu permission và trạng thái trước đó:

~~~text
Draft -> Submitted -> Approved -> Paid
                  \-> Rejected
~~~

Ví dụ, user có quyền tạo request nhưng không có quyền approve. Một approver có thể approve nhưng không được tự duyệt request do chính mình tạo nếu policy yêu cầu separation of duties.

Test:

- Principal thường gọi approve/reject.
- Approver gọi function trên object ngoài phạm vi.
- Người tạo request tự approve.
- Approver gọi action khi trạng thái không hợp lệ.
- Principal đã bị revoke role nhưng token/session cũ còn tồn tại.
- Hai request đồng thời thực hiện cùng action.

Authorization phải được kiểm tra tại thời điểm thực hiện transition, không chỉ khi hiển thị nút hoặc tạo draft. Với approval nhạy cảm, test cả quyền theo amount, tenant, risk tier và delegated authority.

## 14. Kiểm thử function trên GraphQL, RPC và WebSocket

Function không phải lúc nào cũng là REST endpoint:

| Kiểu API | Điểm cần kiểm thử |
|---|---|
| GraphQL | Query field, mutation, nested resolver, batch/alias và introspection theo policy |
| gRPC | Service/method authorization, metadata và interceptor |
| WebSocket | Authentication lúc handshake và authorization cho từng message/action |
| JSON-RPC | Method name, parameter và permission cho từng method |
| Webhook receiver | Sender identity, signature và quyền phát sinh action |

Với GraphQL, không chỉ bảo vệ route /graphql. Một endpoint có thể cho phép mọi request tới cùng path nhưng resolver mutation có quyền khác query field. Test trực tiếp từng resolver/action, kể cả khi được gọi qua nested field hoặc alias.

Với WebSocket, quyền tại handshake không tự động cho phép mọi message sau đó. Kiểm tra session expiry/revocation, subscription scope và mỗi action thay đổi trạng thái.

Với gRPC, kiểm tra từng method trong service definition và interceptor; không chỉ kiểm tra một route gateway đại diện.

## 15. Kiểm thử function bất đồng bộ và background job

Một request có thể tạo job để worker thực hiện sau:

~~~text
HTTP request
   |
   v
Authenticate + authorize command
   |
   v
Create job/outbox record
   |
   v
Queue
   |
   v
Worker executes privileged action
~~~

Nếu chỉ kiểm tra quyền lúc tạo job nhưng job có thể bị sửa, replay hoặc chạy sau khi quyền đã bị thu hồi, cần xác định policy rõ:

- Quyền được đánh giá tại thời điểm submit, execute hay cả hai?
- Job có gắn actor, tenant, requested action và authorization context đã xác minh không?
- Worker có allowlist job type và queue riêng không?
- Client có thể tự chọn job type hoặc queue không?
- Job ID có thể bị đoán để gọi chức năng khác không?
- Job có kiểm tra object/tenant/state trước side effect không?
- Quyền đã bị revoke thì job pending xử lý thế nào?

Test user thường submit admin job, sửa job payload, replay job, gọi endpoint execute job và truy cập job của tenant khác. Xác minh worker không thực hiện action trái phép và audit giữ được actor ban đầu cùng workload thực thi.

## 16. Kiểm thử internal endpoint và đường bypass gateway

Endpoint được gọi là internal vẫn có thể bị truy cập bởi workload khác, SSRF, pod bị xâm nhập hoặc cấu hình network sai.

Test trong môi trường được phép:

- Gọi trực tiếp upstream bỏ qua gateway.
- Gọi qua ingress/service mesh bằng service account khác.
- Gọi endpoint admin/debug/actuator.
- Dùng credential của service không liên quan.
- Thử route nội bộ không có trong public API spec.

Kết quả mong đợi là network policy và service authentication giới hạn caller; application vẫn enforce function authorization. Không dùng private IP hoặc header do gateway gửi làm bằng chứng duy nhất rằng caller được quyền.

## 17. Kiểm thử principal và credential có scope khác nhau

Một client có thể được xác thực nhưng scope không đủ. Test các trường hợp:

- Token hợp lệ, đúng issuer/audience nhưng thiếu permission.
- Token có scope users:read gọi users:delete.
- Token dành cho service A gọi API của service B.
- Token hết hạn, revoked hoặc session đã logout.
- API key của partner gọi function chỉ dành cho admin.
- Service account có quyền publish/read nhưng thử gọi function quản trị.
- Token có role cũ sau khi role đã bị thu hồi.

Không chỉ test role. Kiểm tra permission thực tế được resolve từ token, database, policy engine hoặc identity provider. Nếu hệ thống cache permission, test thời gian propagation khi revoke và giới hạn chấp nhận được.

## 18. Kiểm thử bằng Java và Spring Security

Có thể dùng request-level integration test để đi qua security filter chain và kiểm tra endpoint thực tế:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AdminFunctionAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void basicUserCannotDisableAnotherUser() throws Exception {
        mvc.perform(post("/api/admin/users/{id}/disable", 42)
                .with(user("basic-user")
                    .authorities(new SimpleGrantedAuthority("users:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"test\"}"))
            .andExpect(status().isForbidden());

        // Kiểm tra thêm database/job/event không bị thay đổi.
    }

    @Test
    void adminWithPermissionCanDisableUser() throws Exception {
        mvc.perform(post("/api/admin/users/{id}/disable", 42)
                .with(user("admin")
                    .authorities(new SimpleGrantedAuthority("users:disable")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"approved test\"}"))
            .andExpect(status().isNoContent());
    }
}
~~~

Đây là ví dụ cấu trúc; cần import, fixture và status phù hợp API thực tế. Nếu production dùng JWT/OAuth2, nên có integration test với JwtDecoder/test issuer để xác minh scope mapping và filter chain thật.

### 18.1 Test method-level authorization

Service method có thể được bảo vệ bằng permission:

~~~java
@PreAuthorize("hasAuthority('users:disable')")
public void disableUser(UserId id, DisableReason reason) {
    // Load object trong tenant scope và kiểm tra object policy.
}
~~~

Kiểm tra method security đã được bật trong application context và test gọi qua Spring proxy. Gọi trực tiếp instance hoặc self-invocation có thể bỏ qua proxy-based method security, khiến test tạo kết quả sai.

### 18.2 Test request matcher và method security cùng nhau

Request matcher ở SecurityFilterChain có thể chặn route trước controller; method security có thể bảo vệ service function. Cả hai cần có test:

- Anonymous request bị chặn ở filter chain.
- Authenticated principal thiếu authority bị chặn.
- Principal đủ authority qua được function check.
- Object/tenant policy vẫn từ chối truy cập sai phạm vi.

Không dựa hoàn toàn vào @WithMockUser hoặc request post-processor để kết luận JWT verification đúng. Các helper này thường tạo Authentication trực tiếp, bỏ qua token parsing, signature, issuer và audience. Hãy test authentication riêng qua filter/JWT decoder thực tế.

## 19. Xác minh side effect khi authorization bị từ chối

Một response 403 không đủ chứng minh request an toàn. Code có thể thực hiện một phần thao tác trước khi phát hiện thiếu quyền.

Với mỗi negative test, kiểm tra:

- Database row và trạng thái aggregate không đổi.
- Không có file export hoặc object storage artifact mới.
- Không có job/outbox/event được tạo.
- Không có email, webhook, payment hoặc downstream call.
- Không có cache invalidation hoặc permission update ngoài ý muốn.
- Audit ghi nhận deny decision nhưng không ghi secret.

Đối với thao tác nhiều bước, đặt assertion sau request và sau khi worker/job đã hoàn tất hoặc hết timeout kiểm thử. Dùng fake clock, fake broker hoặc test container khi phù hợp để xác định side effect chính xác.

## 20. Status code và response không phải bằng chứng duy nhất

Thông thường:

- 401: thiếu hoặc credential không hợp lệ.
- 403: đã xác thực nhưng không có quyền.
- 404: có thể được dùng để che giấu function/resource theo policy.
- 405: method không được hỗ trợ cho route.

Contract có thể chọn cách trả khác để conceal resource hoặc chuẩn hóa lỗi. Vì vậy, test phải kiểm tra cả:

1. Status và error code.
2. Response body/header không tiết lộ policy nội bộ.
3. Handler/side effect không chạy.
4. Audit decision phản ánh đúng principal và permission.

Không chấp nhận response 200 có body báo lỗi authorization. Không coi redirect về login là pass nếu endpoint vẫn có thể thực hiện side effect trước redirect.

## 21. Tự động hóa test từ API inventory

Có thể tạo test matrix từ operation registry:

~~~text
for each operation:
    required_permissions = policy(operation)
    for each test_principal:
        expected = permission_model(
            test_principal,
            operation,
            fixed_attributes
        )
        response = invoke(operation, test_principal)
        assert response matches expected
        assert side_effects match expected
~~~

Test generator cần biết:

- Method/path/operation ID.
- Permission yêu cầu.
- Principal fixture và permission set.
- Tenant/object attributes.
- Request fixture hợp lệ.
- Side effect cần quan sát.
- Expected status/error code.

Không suy permission từ tên endpoint hoặc tag một cách tự động rồi coi đó là nguồn chuẩn. Policy registry hoặc owner review phải cung cấp expected decision.

## 22. Coverage và tiêu chí hoàn thành

Đo coverage theo function và permission, không chỉ line coverage:

| Coverage | Câu hỏi |
|---|---|
| Endpoint coverage | Mọi route/operation đã được test chưa? |
| Method coverage | Mọi HTTP method đã expose được kiểm tra chưa? |
| Function coverage | Mọi business action nhạy cảm có negative test không? |
| Principal coverage | Anonymous, user, admin, partner và service account đã được đại diện chưa? |
| Permission coverage | Đã thử permission đúng, thiếu và gần giống chưa? |
| Alternate path coverage | Alias, legacy, internal, GraphQL/RPC và async path đã được kiểm tra chưa? |
| Side-effect coverage | Negative request có chứng minh không tạo thay đổi không? |
| Lifecycle coverage | Revoked/expired role và version cũ đã được kiểm tra chưa? |

Các chỉ số hữu ích:

- Tỷ lệ function có owner và required permission.
- Tỷ lệ operation có allow/deny test.
- Số route không có mapping permission.
- Số admin/internal function thiếu negative test.
- Số test chứng minh side effect không xảy ra.
- Số authorization regression được phát hiện trong CI.

Line coverage cao không đảm bảo function authorization được bảo vệ. Một controller có thể được chạy 100% nhưng chưa từng được gọi bằng principal không có quyền.

## 23. Các lỗi kiểm thử thường gặp

1. **Chỉ test UI:** bỏ qua khả năng gọi API trực tiếp.
2. **Chỉ test anonymous:** không phát hiện user đã đăng nhập nhưng thiếu quyền.
3. **Chỉ test role Admin:** không có negative matrix cho role thường và service account.
4. **Chỉ test một method:** bỏ sót DELETE/PATCH/POST trên cùng route.
5. **Chỉ test route mới:** bỏ sót alias, legacy và internal route.
6. **Chỉ assert 403:** không kiểm tra database, job, event hoặc downstream side effect.
7. **Mock security quá sâu:** bỏ qua filter chain, JWT mapping hoặc method proxy.
8. **Dùng role thay permission:** test không phát hiện scope quá rộng hoặc sai mapping.
9. **Không test bulk/export:** bỏ sót function có blast radius lớn.
10. **Không test async worker:** quyền ở request không được enforce khi job thực thi.
11. **Tin private network:** bỏ qua direct upstream access và service identity.
12. **Không test revoke:** principal đã mất quyền vẫn gọi được bằng token/cache cũ.
13. **Dùng fixture dùng chung:** test order làm thay đổi role hoặc state của test khác.
14. **Không cập nhật inventory:** endpoint mới xuất hiện nhưng không có test authorization.

## 24. Phân loại phát hiện và khắc phục

Khi test tìm thấy function truy cập trái phép, ghi nhận:

- Function/operation và route/method/version.
- Principal/role/permission thực tế.
- Permission đáng lẽ phải có.
- Request tối thiểu tái hiện và response.
- Side effect đã xảy ra hoặc bằng chứng không xảy ra.
- Object/tenant/data classification bị ảnh hưởng.
- Các alias/route khác có cùng function.
- Gateway và direct-upstream behavior.
- Mức độ ảnh hưởng, điều kiện khai thác và owner.

Mức độ nghiêm trọng phụ thuộc function:

| Function bị gọi trái phép | Tác động có thể có |
|---|---|
| Read public metadata | Thấp hơn, tùy dữ liệu |
| Export user/customer data | Lộ dữ liệu quy mô lớn |
| Assign role hoặc grant permission | Privilege escalation |
| Disable/revoke account | Gián đoạn dịch vụ hoặc khóa user |
| Rotate/reveal secret | Compromise credential |
| Refund/approve/payment | Thiệt hại tài chính |
| Delete/restore/configure system | Mất dữ liệu hoặc kiểm soát hệ thống |

Khắc phục:

1. Xác định permission rõ cho từng function.
2. Enforce deny-by-default ở server.
3. Bảo vệ mọi route/method/alias dẫn tới function.
4. Kiểm tra quyền ở service layer cho action nhạy cảm.
5. Giữ object/tenant authorization riêng.
6. Chặn direct upstream hoặc xác thực service caller.
7. Thu hồi credential/permission nếu có khả năng đã bị lạm dụng.
8. Thêm regression test allow và deny cùng side-effect assertion.
9. Kiểm tra audit và dữ liệu đã bị thay đổi.
10. Theo dõi sau deploy để phát hiện route hoặc policy còn drift.

## 25. Checklist kiểm thử broken function authorization

- [ ] Có inventory đầy đủ operation/function, method, route, version và owner.
- [ ] Mỗi function nhạy cảm có required permission rõ ràng.
- [ ] Có ma trận principal-role-permission với expected allow/deny cụ thể.
- [ ] Có test anonymous và authenticated principal thiếu quyền.
- [ ] Có test permission gần giống nhưng không đủ.
- [ ] Admin, support, auditor, partner và service account có fixture riêng.
- [ ] Mọi HTTP method trên cùng route được test độc lập.
- [ ] Alias, legacy, route rewrite và version cũ đã được kiểm tra.
- [ ] Function ẩn khỏi UI vẫn bị server bảo vệ.
- [ ] Bulk, export, approval, delete, secret và admin function có negative test.
- [ ] GraphQL/RPC/WebSocket/webhook/async function được kiểm tra theo action.
- [ ] Internal endpoint và direct upstream path được kiểm tra trong phạm vi cho phép.
- [ ] Token scope, audience, expiry, revoke và permission propagation được test.
- [ ] Negative test xác minh không có database/job/event/file/payment side effect.
- [ ] Test đi qua filter chain và method security thật; mock được dùng có chủ đích.
- [ ] Có allow test để chứng minh principal hợp lệ vẫn thực hiện được function.
- [ ] Có audit evidence và request ID cho từng quyết định deny.
- [ ] CI phát hiện operation mới chưa có policy hoặc authorization test.
- [ ] Báo cáo ghi rõ function, principal, permission, impact và remediation.

Kiểm thử broken function authorization phải chứng minh quyền được thực thi tại server cho từng hành động, không phụ thuộc vào giao diện hoặc việc caller đã đăng nhập. Khi inventory function được nối với permission matrix, negative test theo nhiều loại principal, kiểm tra tất cả đường gọi và assertion về side effect, nhóm phát triển có thể phát hiện sớm privilege escalation và ngăn endpoint đặc quyền bị sử dụng ngoài phạm vi cho phép.
