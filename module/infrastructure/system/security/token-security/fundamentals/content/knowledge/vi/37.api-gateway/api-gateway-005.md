# Gateway authorization và resource authorization

## 1. Bài toán: một token hợp lệ có đủ để truy cập dữ liệu không?

Trong kiến trúc có **API gateway**, ứng dụng gửi yêu cầu đến gateway rồi gateway định tuyến về dịch vụ phía sau. Một yêu cầu có thể đã được xác thực đúng nhưng vẫn không được phép đọc hoặc sửa tài nguyên cụ thể. Ví dụ, tài khoản A có quyền gọi API đọc đơn hàng, song không vì thế mà được đọc đơn hàng thuộc tài khoản B.

Đây là chủ đề **Gateway authorization và resource authorization** thuộc chương **API gateway** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Để hiểu cơ chế này cần nối kết mô hình tin cậy và vòng đời token: OAuth 2.0/OIDC, access token và refresh token, JWT và opaque token, chữ ký, issuer, audience, claims, scope, kiểm tra quyền, thu hồi token và chống đánh cắp hoặc phát lại.

Ba khái niệm cần phân biệt:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Authentication (xác thực) | Ai hoặc ứng dụng nào đang gọi? Thông tin nhận dạng có đáng tin không? | Access token hợp lệ đại diện cho chủ thể user-42 |
| Gateway authorization (phân quyền tại gateway) | Chủ thể này có được phép đi qua tuyến API và thực hiện loại thao tác này không? | Token được phép gọi GET /v1/orders/** với scope orders:read |
| Resource authorization (phân quyền tài nguyên) | Chủ thể này có được phép thao tác trên **bản ghi/tài nguyên cụ thể**, trong ngữ cảnh hiện tại không? | user-42 chỉ đọc đơn hàng của mình hoặc đơn hàng được phân công trong tenant được phép |

**Nguyên tắc:** gateway thực hiện kiểm soát đầu vào và quyền ở cấp API; dịch vụ sở hữu dữ liệu phải thực thi chính sách đối với đối tượng, hành động và quan hệ nghiệp vụ cụ thể. Hai tầng có thể dùng chung công cụ chính sách, nhưng phải có ranh giới tin cậy rõ ràng. Scope đủ để vượt qua gateway **không tự động** đồng nghĩa có quyền trên mọi tài nguyên.

## 2. Các vai trò và ranh giới tin cậy

Một hệ thống điển hình gồm:

- **Client:** ứng dụng web, mobile hoặc hệ thống khác gửi yêu cầu.
- **Authorization Server / Identity Provider (AS/IdP):** xác thực và cấp token theo OAuth 2.0; OIDC bổ sung danh tính phục vụ đăng nhập.
- **API gateway:** điểm tiếp nhận API, xác thực token, áp dụng quy tắc tuyến và scope, sau đó chuyển tiếp có kiểm soát.
- **Resource server:** dịch vụ sở hữu tài nguyên như Orders API, Payments API; thực hiện kiểm soát quyền nghiệp vụ.
- **Dữ liệu và Policy Decision Point:** cơ sở dữ liệu, quyền thành viên, quan hệ sở hữu, trạng thái tài nguyên hoặc dịch vụ đánh giá chính sách.

Ví dụ luồng GET /v1/orders/O-77:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as API Gateway
    participant AS as Authorization Server
    participant S as Orders API
    participant DB as DB / Policy
    C->>G: GET /v1/orders/O-77 + access token
    G->>G: Kiểm tra token, issuer, audience, thời hạn, scope
    opt Cần JWKS hoặc introspection
        G->>AS: Lấy khóa tin cậy / tra cứu trạng thái token
        AS-->>G: JWKS / kết quả introspection
    end
    alt Token sai hoặc thiếu quyền cấp API
        G-->>C: 401 hoặc 403
    else Được đi qua gateway
        G->>S: Yêu cầu + danh tính đáng tin / access token
        S->>S: Xác minh ranh giới tin cậy từ gateway
        S->>DB: Tìm O-77 trong tenant hợp lệ; tra cứu quyền hiện hành
        DB-->>S: Dữ liệu và quan hệ sở hữu/phân công
        S->>S: Đánh giá quyền đọc đối với O-77
        S-->>G: 200 hoặc 403/404
        G-->>C: Phản hồi
    end
~~~

Phân quyền không chỉ gắn với một token, mà là quyết định trên bộ thông tin: **chủ thể (subject/principal) + hành động (action) + tài nguyên (resource) + ngữ cảnh (context) + chính sách (policy)**. Token cung cấp một phần dữ kiện; trạng thái hiện tại của tài nguyên và tổ chức thường nằm ở dịch vụ hoặc kho chính sách.

## 3. Gateway authorization kiểm tra điều gì?

Gateway thường là nơi thực thi các quy tắc tương đối ổn định theo tuyến API. Với tuyến GET /v1/orders/{id}, quy tắc có thể yêu cầu token dành cho Orders API và quyền orders:read.

### 3.1. Xác minh access token

Đối với **JWT access token**, một gateway hoạt động như resource server cần kiểm tra tối thiểu:

1. **Nguồn phát hành tin cậy:** giá trị iss phải khớp chính xác issuer được cấu hình; chỉ chấp nhận khóa công khai từ nguồn JWKS tin cậy.
2. **Chữ ký và thuật toán:** chữ ký phải hợp lệ với thuật toán được cho phép. Không tin thuật toán, địa chỉ khóa hoặc đường dẫn khóa do token tự chỉ định một cách tùy ý; từ chối token không ký nếu API yêu cầu token có chữ ký.
3. **Audience:** aud phải chứa định danh tài nguyên/API được phép sử dụng token. Token cấp cho Payments API không được dùng để gọi Orders API chỉ vì cùng issuer hoặc có scope tương tự.
4. **Thời hạn và hiệu lực:** kiểm tra exp, nbf (nếu có), các ràng buộc thời gian khác; chỉ cho phép sai lệch đồng hồ nhỏ và được cấu hình.
5. **Loại token và ngữ cảnh:** bảo đảm đây là access token theo hợp đồng của hệ thống, không nhầm với ID token, refresh token hoặc JWT có mục đích khác. Những claim như typ, azp, client_id hoặc token_use chỉ được diễn giải theo profile và issuer thực tế.
6. **Quyền cấp tuyến:** kiểm tra scope/permission được yêu cầu cho phương thức và tuyến, chẳng hạn orders:read để đọc, orders:write để sửa.

Ví dụ một **payload JWT đã được xác minh** (chỉ để minh họa; payload tự nó không chứng minh chữ ký):

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "tenant-A",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Từ token này, gateway có thể kết luận access token được trình diện có hiệu lực, đại diện cho chủ thể user-42 và mang scope orders:read cho Orders API **nếu mọi kiểm tra xác thực đều thành công**. Gateway chưa thể kết luận người đang cầm bearer token chính là user-42 hoặc chủ thể này sở hữu đơn hàng O-77.

Với **opaque access token**, gateway không tự giải mã để suy ra quyền. Gateway gọi endpoint **token introspection** của AS bằng cơ chế xác thực phù hợp, kiểm tra kết quả active và các thuộc tính được AS trả về (scope, audience, chủ thể, thời hạn...), sau đó áp dụng chính sách tuyến. Không coi chuỗi opaque là JWT chỉ vì có vẻ chứa các dấu chấm.

### 3.2. Quy tắc theo tuyến và phương thức HTTP

Bảng sau là ví dụ về chính sách cổng vào, không phải toàn bộ chính sách nghiệp vụ:

| Yêu cầu | Audience kỳ vọng | Quyền tối thiểu tại gateway | Quyết định cuối tại resource server |
| --- | --- | --- | --- |
| GET /v1/orders/{id} | orders-api | orders:read | Có quyền xem đúng đơn hàng {id}? |
| POST /v1/orders | orders-api | orders:create | Có được tạo đơn cho tenant/khách hàng đã chọn? |
| PATCH /v1/orders/{id} | orders-api | orders:write | Có quyền sửa đơn và trường được sửa ở trạng thái hiện tại? |
| POST /v1/orders/{id}/refund | orders-api | orders:refund | Có quyền hoàn tiền, đúng hạn mức và trạng thái đơn? |
| GET /v1/admin/reports | reporting-api | reports:read | Có quyền xem loại báo cáo và phạm vi dữ liệu tương ứng? |

Scope là quyền được ủy quyền ở cấp API; role (vai trò), ownership (sở hữu), relationship (quan hệ), tenant membership (thành viên tổ chức), trạng thái tài nguyên và hạn mức là những dữ kiện bổ sung. Có thể kết hợp RBAC (theo vai trò), ABAC (theo thuộc tính) và ReBAC (theo quan hệ). Một role rộng cũng không nên tự động bỏ qua giới hạn tenant hoặc kiểm tra dữ liệu nhạy cảm.

### 3.3. Gateway không nên tự suy ra quyền từ dữ liệu thiếu ngữ cảnh

Gateway thường không biết O-77 thuộc ai, trạng thái đã khóa hay chưa, người gọi đã rời tổ chức hay chưa. Đưa tất cả quyết định theo từng bản ghi lên gateway buộc gateway liên tục truy vấn cơ sở dữ liệu của dịch vụ và làm mờ quyền sở hữu nghiệp vụ. Nếu một chính sách chung cần kiểm tra sớm tại gateway, gateway có thể gọi một Policy Decision Point; **dịch vụ vẫn phải duy trì cơ chế thực thi quyền tài nguyên tại biên tin cậy của mình**.

## 4. Resource authorization: quyết định trên từng đối tượng

Với cùng access token đã qua gateway, hai yêu cầu có thể cho kết quả khác nhau:

- GET /v1/orders/O-77: O-77 thuộc user-42 trong tenant-A → cho phép.
- GET /v1/orders/O-88: O-88 thuộc user-99 dù cùng tenant-A → từ chối, trừ khi user-42 đang có quyền nghiệp vụ phù hợp.
- GET /v1/orders/O-99: O-99 thuộc tenant-B → từ chối ngay từ bước truy vấn trong phạm vi tenant, kể cả nếu ID hợp lệ.

Chính sách tài nguyên cần trả lời:

1. **Chủ thể là ai?** Phân biệt người dùng, service account và ứng dụng gọi theo client_credentials; không giả định mọi sub đều là ID người dùng.
2. **Tài nguyên nào?** Lấy ID từ tuyến, nhưng luôn truy vấn và xác minh tài nguyên thật. ID do client cung cấp không phải bằng chứng sở hữu.
3. **Tenant nào?** Xác định tenant từ ngữ cảnh được xác minh, kiểm tra membership còn hiệu lực và giới hạn truy vấn theo tenant. Với người dùng thuộc nhiều tenant, tenant được chọn phải qua kiểm tra membership.
4. **Hành động nào?** read, update, delete, refund và export có thể có chính sách khác nhau.
5. **Quyền còn hiệu lực không?** Quyền phân công, vai trò, trạng thái đơn, quy định chia sẻ dữ liệu, giới hạn tiền hoặc thời điểm có thể thay đổi sau lúc token được phát hành.
6. **Có hạn chế theo trường dữ liệu không?** Được xem đơn hàng chưa chắc được xem dữ liệu thanh toán hoặc chỉnh sửa trường giá; bảo vệ cả read/write ở cấp field khi cần.

Mẫu kiểm tra thực dụng là **scope trước, đối tượng sau**:

~~~text
allow(request, principal, resource):
  require valid access-token identity at this service boundary
  require scope permits request.action
  require principal is currently allowed in resource.tenant
  require resource exists inside authorized data boundary
  require current policy permits (principal, action, resource, context)
  return allow; otherwise deny
~~~

Đối với các API nhiều tenant, có thể truy vấn theo điều kiện (resource_id, tenant_id) trước khi lấy bản ghi. Cách này làm giảm khả năng truy xuất nhầm dữ liệu tenant khác, nhưng vẫn cần kiểm tra ownership/quan hệ và quyền theo từng hành động sau truy vấn.

## 5. Ví dụ Spring Security tại Orders API

Giả sử gateway đã yêu cầu scope orders:read. Orders API vẫn được cấu hình như một OAuth 2.0 resource server, xác minh access token phù hợp (bao gồm issuer, chữ ký, thời hạn, **audience orders-api**) trước khi tạo danh tính xác thực.

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderRepository orders;
    private final OrderPolicy policy;

    OrderController(OrderRepository orders, OrderPolicy policy) {
        this.orders = orders;
        this.policy = policy;
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    OrderResponse read(@PathVariable UUID id,
                       JwtAuthenticationToken authentication) {
        Jwt token = authentication.getToken();
        String subject = token.getSubject();
        String tenantId = token.getClaimAsString("tenant_id");

        if (tenantId == null
                || !policy.hasActiveMembership(subject, tenantId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        Order order = orders.findByIdAndTenantId(id, tenantId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));

        if (!policy.mayRead(subject, order)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        return OrderResponse.from(order);
    }
}
~~~

Đây là mã minh họa logic, cần bổ sung bean, repository và triển khai OrderPolicy trong dự án thật. Phương thức cần bật method security (chẳng hạn @EnableMethodSecurity). Quy ước SCOPE_ áp dụng khi cấu hình bộ chuyển đổi scope thành GrantedAuthority tương ứng. **Chỉ cấu hình issuer-uri chưa đủ để mặc định áp đặt audience mong muốn trong mọi cấu hình Spring Security**; cần kiểm tra/cấu hình validator audience tường minh và kiểm thử bằng token sai aud.

Các kiểm tra được tách theo trách nhiệm:

- **Spring Security / resource-server filter:** kiểm tra chữ ký token, issuer, thời hạn, audience và cơ chế xác thực; từ chối trước khi chạy controller nếu token sai.
- **@PreAuthorize:** yêu cầu quyền cấp thao tác orders:read, tạo hàng rào phòng vệ ngay tại service.
- **findByIdAndTenantId:** hạn chế dữ liệu có thể truy xuất trong tenant hợp lệ.
- **OrderPolicy:** kiểm tra quyền thành viên đang hoạt động, sở hữu, phân công, vai trò còn hiệu lực và các điều kiện nghiệp vụ.

Nếu vai trò hoặc membership có thể bị thu hồi ngay, OrderPolicy nên dựa vào nguồn quyền đang còn hiệu lực, hoặc cache có TTL và cơ chế invalidation phù hợp. Không được mặc định cho phép chỉ vì claim roles hay tenant_id còn nằm trong JWT chưa hết hạn.

## 6. Chuyển tiếp danh tính giữa gateway và service

Hai mô hình triển khai phổ biến:

| Mô hình | Cách thực hiện | Điều kiện an toàn |
| --- | --- | --- |
| **Forward access token** | Gateway chuyển access token đến backend; backend tự xác minh và phân quyền. | Backend kiểm tra issuer, chữ ký/introspection, exp, aud, scope; mọi API nội bộ đều có chính sách; hạn chế log và phát tán token. |
| **Trusted identity context** | Gateway xác minh token rồi truyền ngữ cảnh chủ thể/quyền đã xác nhận qua kênh nội bộ. | Backend chỉ nhận ngữ cảnh có bằng chứng nguồn đáng tin (ví dụ mTLS + định danh gateway, token nội bộ đã ký); gateway xóa header danh tính do client tự gửi, mạng chặn đường truy cập trực tiếp. |

Ở mô hình thứ hai, header như X-User-Id, X-Tenant-Id, X-Roles **không đáng tin chỉ vì có mặt trong request**. Client có thể tự đặt các header đó nếu gateway không xóa và tái tạo chúng. Backend cần xác minh nguồn gốc, phạm vi và tính toàn vẹn của ngữ cảnh; không cho phép truy cập thẳng vòng qua gateway. Mô hình này vẫn phải kiểm tra quyền sở hữu tài nguyên.

Nếu dịch vụ A gọi tiếp dịch vụ B, không tự động chuyển access token có aud dành riêng cho A sang B. Có thể dùng **OAuth 2.0 Token Exchange**, token đại diện phù hợp và giới hạn audience/scope, hoặc danh tính dịch vụ riêng theo thiết kế ủy quyền. Khi hành động nhân danh người dùng, quyền thực tế cần bị giới hạn bởi cả quyền của người dùng, ứng dụng gọi và chính sách của dịch vụ đích.

## 7. Vòng đời token ảnh hưởng tới phân quyền ra sao?

| Token / cơ chế | Công dụng | Điều cần lưu ý tại gateway và service |
| --- | --- | --- |
| **JWT access token** | Mang claim do AS phát hành, có thể xác minh cục bộ bằng chữ ký. | Kiểm tra issuer, audience, signature, thời hạn và scope. JWT còn hạn không đảm bảo quyền nghiệp vụ chưa bị thu hồi. |
| **Opaque access token** | Chuỗi tham chiếu có trạng thái/thuộc tính tại AS. | Dùng introspection, xác minh active, audience, scope và các điều kiện liên quan; bảo vệ thông tin xác thực khi introspect. |
| **Refresh token** | Xin access token mới từ AS khi được cho phép. | Dành cho client/AS theo flow thiết kế; **không dùng refresh token để truy cập resource API**. Hỗ trợ rotation, ràng buộc client và phát hiện reuse khi phù hợp. |
| **OIDC ID token** | Cung cấp thông tin kết quả đăng nhập cho OIDC client. | Không chấp nhận ID token làm access token tại API. audience của ID token thường là client ứng dụng. |
| **Token introspection / revocation** | AS thông báo tình trạng token, hoặc nhận yêu cầu thu hồi. | Cache kết quả introspection phải có TTL và chính sách rủi ro; token tự chứa có thể vẫn xác minh hợp lệ đến exp nếu resource server không có tín hiệu thu hồi. |

Độ trễ thu hồi quyền rất quan trọng: nhân viên bị tước quyền trong cơ sở dữ liệu nhưng JWT chứa role cũ còn hiệu lực thêm 10 phút. Biện pháp có thể phối hợp gồm access token sống ngắn, tra quyền hiện hành khi xử lý tài nguyên nhạy cảm, phiên bản quyền hoặc session, revocation/introspection, sự kiện invalidation cache và cơ chế kiểm soát phiên. Chọn giải pháp theo mức độ nhạy cảm và yêu cầu thu hồi; không hứa rằng xóa refresh token sẽ lập tức vô hiệu hóa mọi JWT access token đã cấp.

Nếu dùng cache kiểm tra quyền, khóa cache phải bao gồm đủ subject, tenant, resource, action và phiên bản chính sách có liên quan. Cache theo mỗi subject hoặc scope rất dễ khiến một quyết định cho đơn O-77 bị áp vào đơn O-88. Hạn chế TTL, xóa cache khi quyền đổi và xử lý sự cố policy service theo hướng **fail closed** với hành động cần bảo vệ.

## 8. Các lỗ hổng điển hình và cách phòng tránh

### 8.1. Broken Object Level Authorization (BOLA/IDOR)

Client thay /orders/O-77 thành /orders/O-88; gateway thấy token hợp lệ và scope orders:read nên cho qua, nhưng backend chỉ kiểm tra đăng nhập, không kiểm tra chủ sở hữu.

**Khắc phục:** với mỗi thao tác nhận ID tài nguyên từ client, kiểm tra quyền trên chính đối tượng đó. Kết hợp truy vấn trong tenant, kiểm tra ownership/assignment và policy. Không coi ID khó đoán hoặc UUID là biện pháp phân quyền.

### 8.2. Nhầm audience và nhầm loại token

Token cấp cho dịch vụ khác hoặc ID token của OIDC client bị dùng làm access token.

**Khắc phục:** cấu hình audience theo tài nguyên/tuyến, token profile và issuer tin cậy; từ chối token sai aud ngay cả khi chữ ký hợp lệ. Với nhiều resource server, xác định rõ ai là audience và liệu có cần token exchange.

### 8.3. Tin header danh tính hoặc đường vòng nội bộ

Client tự gửi X-User-Id: admin; backend tin header và bỏ qua xác thực, hoặc attacker gọi trực tiếp backend qua đường mạng.

**Khắc phục:** gateway loại bỏ các header danh tính đến từ bên ngoài, sinh lại ngữ cảnh có bảo vệ; backend xác minh định danh gateway hoặc tự xác thực token; giới hạn lưu lượng đến backend bằng mạng riêng, mTLS và chính sách service-to-service.

### 8.4. Quyền cũ vẫn còn trong token

JWT có roles=manager được cấp trước khi người dùng bị hạ quyền; service chỉ đọc claim cũ.

**Khắc phục:** kiểm tra trạng thái quyền hiện hành với nghiệp vụ nhạy cảm, có TTL/invalidation hợp lý, access token sống ngắn và quy trình thu hồi theo yêu cầu. Không coi việc JWT còn hạn là bảo đảm vai trò còn đúng.

### 8.5. Token bị đánh cắp hoặc phát lại

Access token dạng **bearer** thường có thể được người khác sử dụng nếu bị lộ. Chữ ký JWT ngăn sửa payload, **không** tự ngăn một token nguyên vẹn bị dùng lại.

**Khắc phục:** TLS toàn đường, tránh đưa token vào URL/log/analytics, giới hạn phạm vi và thời hạn, bảo vệ lưu trữ phía client, dùng DPoP hoặc mutual-TLS sender-constrained token khi hệ thống hỗ trợ và xác minh bằng chứng đúng cách. Kiểm tra DPoP có thể cần ràng buộc method/URL, độ mới và chống dùng lại proof; thêm jti vào JWT mà không theo dõi trạng thái **không tự chống replay**. Với trình duyệt, cân nhắc mô hình BFF và cookie HttpOnly/Secure/SameSite kèm CSRF protection khi phù hợp.

### 8.6. Phân quyền chỉ ở giao diện hoặc chỉ ở gateway

Ẩn nút Sửa đơn trên UI không ngăn client gọi API trực tiếp. Gateway có thể kiểm tra quyền theo tuyến nhưng backend vẫn có endpoint khác hoặc lối gọi nội bộ.

**Khắc phục:** mỗi entrypoint của service thực thi policy đúng hành động và tài nguyên; kể cả job nền, GraphQL resolver, API nội bộ và luồng service-to-service. Thử các đường vòng trực tiếp, phiên bản API cũ và thao tác hàng loạt.

## 9. Trả mã lỗi và giảm rò rỉ thông tin

| Tình huống | HTTP điển hình | Giải thích |
| --- | --- | --- |
| Thiếu, hết hạn hoặc sai access token | **401 Unauthorized** | Không có danh tính API được xác thực hợp lệ; có thể trả WWW-Authenticate theo Bearer scheme. |
| Token hợp lệ nhưng thiếu scope của tuyến | **403 Forbidden** | Đã xác thực nhưng không đủ quyền cho thao tác API; có thể dùng thông tin insufficient_scope theo chuẩn áp dụng. |
| Scope hợp lệ nhưng không có quyền trên bản ghi | **403 Forbidden** hoặc **404 Not Found** | 404 có thể được dùng nhất quán để không tiết lộ sự tồn tại tài nguyên. |
| ID không tồn tại hoặc ở tenant mà người gọi không được thấy | **404 Not Found** | Tránh tiết lộ dữ liệu xuyên tenant qua mã lỗi hoặc thời gian phản hồi khi có thể. |
| Quyền cho phép và tài nguyên hợp lệ | **200/201/204** | Mã thành công tùy phương thức và hành động. |

Không trả nội dung JWT, secret, khóa, access token hoặc lý do policy chi tiết nhạy cảm trong thông báo lỗi cho client. Hệ thống quan sát có thể ghi decision ID, tuyến, chủ thể đã được giảm định danh, mã lý do tổng quát, latency và correlation ID; cần quản lý quyền truy cập log.

## 10. Tình huống tổng hợp: quyền đọc đơn hàng trong hệ thống nhiều tenant

Giả sử user-42 đăng nhập qua OIDC, client nhận access token dành cho orders-api với scope orders:read. User này thuộc tenant-A, sở hữu đơn O-77 và không được phân công xử lý O-88. Cả hai đơn đều là dữ liệu có thật.

| Request / trạng thái | Gateway | Orders API | Kết quả |
| --- | --- | --- | --- |
| user-42 đọc O-77 | Token đúng audience, còn hạn, có orders:read | Cùng tenant, đúng chủ sở hữu | Cho phép |
| user-42 đọc O-88 | Qua bước scope | Cùng tenant nhưng không sở hữu/không được phân công | Từ chối |
| user-42 đọc đơn của tenant-B | Qua bước scope | Truy vấn tenant-A không tìm thấy bản ghi hợp lệ | Từ chối, thường 404 |
| user-42 gọi PATCH với chỉ orders:read | Không có orders:write | Không cần xử lý | 403 |
| Token có aud=payments-api gọi Orders API | Sai audience | Không cần xử lý | 401 do token không hợp lệ cho resource này |
| user-42 bị gỡ khỏi tenant-A nhưng JWT chưa hết hạn | Có thể vẫn qua nếu không kiểm tra quyền hiện hành | Membership đã bị thu hồi | Từ chối |
| Client gửi header X-Roles: admin | Gateway loại header không đáng tin | Chỉ dùng danh tính đã xác thực | Không leo thang quyền |

Nếu ứng dụng cho phép quản lý đọc tất cả đơn trong cùng tenant, quy tắc phải phát biểu rõ: user có quyền quản lý **đang hiệu lực**, thuộc cùng tenant và hành động read phù hợp. Không suy luận từ một claim role=admin bất kỳ issuer hoặc từ tên endpoint.

## 11. Thiết kế kiểm thử theo ma trận quyền

Để bảo đảm hai lớp phối hợp đúng, cần kiểm tra cả trường hợp được phép và bị từ chối:

1. **Token:** không có token; JWT sai chữ ký; issuer lạ; sai audience; hết hạn/chưa tới nbf; token thuộc loại sai; opaque token inactive hoặc introspection thất bại.
2. **Gateway policy:** đúng/sai scope với từng HTTP method và route; route chưa khai báo; bypass qua đường dẫn có encoding khác; thử gọi trực tiếp backend.
3. **Resource policy:** chính chủ/người khác, cùng tenant/khác tenant, quyền được cấp/thu hồi, đối tượng đã khóa, hành động nhạy cảm, truy cập và cập nhật từng field.
4. **Ngữ cảnh:** cố ý giả mạo X-User-Id/X-Roles, dùng token của service khác, gọi theo client_credentials, service-to-service và token exchange.
5. **Vận hành:** quay vòng khóa ký, lỗi JWKS/introspection/policy service, hết TTL cache, thay đổi membership, replay proof khi dùng DPoP, phát hiện token rò qua log.

Đặc biệt kiểm thử **ngang quyền** (user A truy cập bản ghi user B) và **xuyên tenant**, vì kiểm thử chỉ với tài khoản admin dễ che khuất lỗi BOLA. Với PATCH/PUT, cần kiểm thử cả mass assignment: người gọi chỉ được cập nhật các field được phép, dù JSON gửi thêm tenantId, ownerId hoặc status.

## 12. Quy tắc triển khai và các chuẩn nên tra cứu

Một thiết kế có thể coi là đạt yêu cầu khi:

- API chỉ nhận access token hợp lệ cho đúng issuer, audience, mục đích, thời hạn và cơ chế xác minh.
- Gateway áp dụng deny-by-default cho tuyến và scope; backend cũng kiểm soát quyền ở ranh giới riêng.
- Dịch vụ quyết định trên **chủ thể + hành động + tài nguyên + tenant + trạng thái hiện hành**, bao gồm quyền cấp trường dữ liệu khi cần.
- Không có cách giả mạo ngữ cảnh người dùng bằng header hoặc vượt gateway để đạt quyền cao hơn.
- Cache, cấp mới và thu hồi token/quyền có chính sách nhất quán với mức độ nhạy cảm; token và bằng chứng sở hữu được bảo vệ khỏi rò rỉ/phát lại.
- Kiểm thử âm tính cho từng lớp, đặc biệt BOLA/IDOR, sai audience, thiếu scope, quyền hết hiệu lực và thay đổi tenant.

Các tài liệu chuẩn liên quan để tìm hiểu sâu: **RFC 6749** (OAuth 2.0), **RFC 6750** (Bearer Token Usage), **RFC 7519** (JWT), **RFC 7662** (Token Introspection), **RFC 7009** (Token Revocation), **RFC 8725** (JWT Best Current Practices), **RFC 9068** (JWT Profile for OAuth 2.0 Access Tokens), **RFC 8693** (Token Exchange), **RFC 8707** (Resource Indicators), **RFC 9449** (DPoP) và **OpenID Connect Core**. Mỗi triển khai phải đối chiếu profile và tài liệu của Authorization Server đang dùng; cấu trúc claim và cách ánh xạ quyền không đồng nhất giữa các nhà cung cấp.

**Điểm cốt lõi:** access token cho biết chủ thể được cấp quyền gì đối với API nào, trong khoảng thời gian nào. Gateway dùng thông tin đó để quyết định yêu cầu có được vào API; resource server dùng thêm dữ liệu và chính sách hiện hành để quyết định có được thao tác trên tài nguyên cụ thể hay không.
