# Tenant hoặc organization claim

Trong ứng dụng SaaS phục vụ nhiều công ty, một người dùng có thể thuộc **nhiều tổ chức** và cùng một API có thể lưu dữ liệu của **hàng nghìn tenant**. Khi đó, biết “ai đang gọi?” là chưa đủ: API còn phải biết request được phép hoạt động **trong phạm vi tổ chức nào**, và tài nguyên được yêu cầu **thực sự thuộc về tổ chức nào**. Các claim như `tenant_id`, `org_id`, `organization` hoặc `tid` có thể giúp truyền ngữ cảnh này trong token, nhưng **tên claim và ý nghĩa của nó phải được xác định bằng hợp đồng giữa bên phát hành token và bên nhận**.

Đây là chủ đề thuộc chương **Claims** của module bảo mật token: từ mô hình tin cậy OAuth 2.0/OIDC đến JWT/opaque token, kiểm tra issuer–audience–scope, lưu trữ, thu hồi và phòng chống truy cập trái phép. Điểm cần ghi nhớ ngay từ đầu:

> **Claim về tenant/organization chỉ đáng tin sau khi token được xác minh, và không tự động cấp quyền truy cập mọi dữ liệu của tenant đó.**

## 1. Tenant và organization nghĩa là gì?

Các sản phẩm có thể dùng cùng một từ cho những khái niệm khác nhau:

- **Tenant:** ranh giới cô lập dữ liệu và cấu hình của một khách hàng trong hệ thống nhiều khách hàng. Ví dụ `tenant-acme` chỉ tập dữ liệu, khóa cấu hình và quyền của Công ty Acme.
- **Organization (org):** một thực thể nghiệp vụ mà user có thể tham gia, được mời, sở hữu hoặc quản lý. Một organization có thể tương ứng một tenant, nhiều organization có thể chung tenant, hoặc một organization có thể có các đơn vị con tùy thiết kế.
- **Identity provider (IdP) directory/realm:** miền quản lý danh tính tại nhà cung cấp xác thực. Nó **không nhất thiết** trùng với tenant nghiệp vụ của ứng dụng.
- **Workspace/project/team:** đơn vị con của tổ chức; có thể sở hữu quyền và tài nguyên riêng nhưng không mặc nhiên là tenant.
- **Membership:** quan hệ giữa principal (user hoặc service) và một organization/tenant, thường có trạng thái, vai trò và thời hạn.

Ví dụ:

~~~text
SaaS InvoiceHub
  tenant-acme
    organization: Acme Viet Nam
    project: Finance 2026
    users: user-42 (admin), user-88 (viewer)

  tenant-globex
    organization: Globex Asia
    project: Sales
    users: user-42 (viewer), user-99 (admin)
~~~

Cùng `user-42` có thể là **admin tại Acme** nhưng chỉ là **viewer tại Globex**. Nếu hệ thống chỉ kiểm tra `sub=user-42` và `role=admin` mà không gắn vai trò với tenant, user có thể được cấp sai quyền.

### 1.1. Chọn mô hình tenant trước khi chọn tên claim

| Mô hình | Diễn giải | Hệ quả với token |
| --- | --- | --- |
| Một organization tương ứng một tenant | Org là ranh giới dữ liệu | Một `org_id` có thể là tenant context nếu hợp đồng định nghĩa rõ |
| Nhiều organization trong một tenant | Org chỉ là đơn vị quản lý bên trong | `tenant_id` và `org_id` có thể cần phân biệt |
| Một user thuộc nhiều tenant | Membership phụ thuộc tenant | Không gắn `role` toàn cục rồi áp vào mọi tenant |
| Mỗi tenant có IdP riêng | Có nhiều issuer hoặc kết nối federation | Cần map issuer/external identity sang tenant nội bộ đã được tin cậy |
| B2B với tổ chức cha/con | Có phân cấp và cấp quyền xuyên đơn vị | Cần policy cho cấp cha/con; không suy ra quyền từ tiền tố ID |

**Không có claim tên `tenant_id` hay `org_id` được bắt buộc bởi JWT hoặc OIDC Core cho mọi sản phẩm.** Chúng thường là **custom claims**. Một số nhà cung cấp dùng `tid`, `org_id` hoặc tên khác với định nghĩa riêng; chẳng hạn một `tid` của nhà cung cấp có thể chỉ **directory phát hành token**, khác tenant lưu dữ liệu trong SaaS của bạn.

## 2. Tenant claim giải quyết câu hỏi nào?

Một access token có thể chứa những thông tin khác nhau nhưng bổ sung cho nhau:

| Claim | Câu hỏi trả lời | Có đủ để cho phép request không? |
| --- | --- | --- |
| `iss` | Ai phát hành token? | Không; phải là issuer tin cậy |
| `aud` | Token dành cho API/resource nào? | Không; cần scope, tenant và resource policy |
| `sub` | Principal nào được biểu diễn? | Không; principal có thể thuộc nhiều tenant |
| `client_id` hoặc claim client theo profile | Ứng dụng nào nhận/đề nghị token? | Không; client identity không tự cấp quyền tenant |
| `tenant_id` / `org_id` | Token được cấp trong ngữ cảnh tenant/org nào? | Không; vẫn phải kiểm tra membership và quyền trên tài nguyên |
| `scope` / `scp` theo profile | Client được cấp loại thao tác nào? | Không; `invoices.read` không có nghĩa đọc tất cả invoice |
| `roles` / permissions | Có những vai trò/quyền gì theo định nghĩa issuer? | Chỉ có ích khi biết **vai trò thuộc tenant nào** |
| `exp`, `nbf`, `iat` | Token hợp lệ từ/khi nào? | Không; chỉ là một phần vòng đời credential |

Ở mô hình SaaS, ba kiểm tra riêng thường cùng cần thiết:

1. **Xác thực credential:** token thật, đúng issuer, đúng API, còn hạn, có mục đích phù hợp.
2. **Xác định ngữ cảnh tenant:** tenant nào được token/chính sách tin cậy cấp cho principal ở request này?
3. **Phân quyền tài nguyên:** hành động, membership, role/permission và **tenant sở hữu tài nguyên** có khớp không?

Nếu bỏ bước 3, một token hợp lệ với `tenant_id=acme` có thể bị lạm dụng qua URL `/tenants/globex/invoices/123`. Nếu bỏ bước 1, attacker tự sửa JSON thành `tenant_id=globex` rồi được hệ thống tin tưởng.

## 3. Minh họa claim trong JWT access token

Giả sử authorization server cấp access token JWT cho API hóa đơn sau khi user chọn tổ chức Acme:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/invoices",
  "client_id": "invoice-web",
  "tenant_id": "tenant-acme",
  "scope": "invoices.read invoices.write",
  "roles": ["invoice-editor"],
  "iat": 1795410600,
  "nbf": 1795410600,
  "exp": 1795411500
}
~~~

Đây **chỉ là payload JSON minh họa**, chưa phải JWT có chữ ký. Trong một profile JWT access token cụ thể, có thể có yêu cầu về header `typ` như `at+jwt`, các trường bắt buộc và cách thể hiện client; client và API phải tuân đúng profile đã chọn.

Diễn giải **theo hợp đồng giả định**:

- `sub=user-42`: principal đăng nhập qua issuer `https://auth.example.com`.
- `tenant_id=tenant-acme`: **tenant đang được token đại diện** cho request này.
- `roles=["invoice-editor"]`: chỉ có ý nghĩa **trong tenant-acme**, không phải vai trò toàn cục.
- `scope`: client được cấp các thao tác hóa đơn; việc cho sửa hóa đơn nào vẫn phải kiểm tra tenant, quyền sở hữu, trạng thái tài nguyên và các quy tắc khác.
- `aud`: access token này **không dành** cho `https://api.example.com/payroll` nếu API đó không nằm trong audience được cấp.

Tên claim `tenant_id`, `roles` và biểu diễn scope trong ví dụ là **lựa chọn của một hệ thống minh họa**. Không sao chép chúng vào API thật khi chưa thống nhất tên, kiểu dữ liệu và ngữ nghĩa với authorization server.

### 3.1. ID token và access token có thể chứa organization khác nhau

**ID token OIDC** trả thông tin về sự kiện **xác thực user cho OIDC client**. Nó có `aud` hướng tới `client_id`; custom claim `org_id` trong ID token có thể phục vụ hiển thị UI hoặc thiết lập phiên nếu OP và RP đã ký kết ý nghĩa. **ID token không phải vé Bearer để gọi resource API**.

**Access token OAuth 2.0** dành cho **resource server**; API dựa trên token đã xác minh cùng policy để quyết định có truy cập tài nguyên tenant nào được hay không. **Refresh token** dùng với authorization server để xin token mới, không dùng trực tiếp cho API. **Opaque access token** có thể không chứa claims để client đọc được: API phải lấy metadata tin cậy qua introspection hoặc lookup.

Không đồng nhất một organization dùng để hiển thị trong ID token với tenant đã được access token cấp quyền tại API. Chúng có thể trùng **nếu hợp đồng nói vậy**, nhưng không nên tự suy đoán.

## 4. Bốn cách biểu diễn tenant context và lựa chọn phù hợp

### 4.1. Một tenant đang hoạt động trong mỗi token

~~~json
{
  "sub": "user-42",
  "tenant_id": "tenant-acme",
  "scope": "invoices.read",
  "roles": ["viewer"]
}
~~~

Đây là cách đơn giản cho ứng dụng có chức năng **chuyển tổ chức**. Mỗi access token có một ngữ cảnh tenant rõ ràng; khi user chuyển Acme sang Globex, client cần **nhận token tương ứng** qua quy trình được AS chấp thuận.

Ưu điểm: API dễ áp dụng kiểm tra `resource.tenant_id == token.tenant_id`, role được gắn với tenant rõ ràng, token nhỏ. Nhược điểm: phải quản lý chuyển ngữ cảnh, token cũ và sự đồng bộ giữa tab/request.

### 4.2. Danh sách tenants/memberships trong token

~~~json
{
  "sub": "user-42",
  "tenants": [
    {"id": "tenant-acme", "roles": ["admin"]},
    {"id": "tenant-globex", "roles": ["viewer"]}
  ]
}
~~~

Ưu điểm: giảm số lần đổi token trong những hệ thống được thiết kế cho đa ngữ cảnh. Rủi ro: token lớn, memberships/roles dễ cũ, phân quyền phải chọn **đúng phần tử tenant** theo request; càng nhiều tenant càng dễ vượt giới hạn header hoặc lộ thông tin tổ chức mà user tham gia.

Danh sách này **không đồng nghĩa một request được truy cập đồng thời mọi tài nguyên**. API vẫn phải xác định tenant đích, tìm đúng entry và kiểm tra scope/quyền cho tenant đó. Không nên nhận `roles=admin` của Acme để sửa dữ liệu Globex.

### 4.3. Token ngắn + trạng thái membership phía server

JWT chỉ mang `iss`, `sub`, `aud`, scope và tenant context tối thiểu; API hoặc authorization service tra membership/roles hiện hành trong database/cache tin cậy. Hoặc hệ thống phát **opaque access token** và API introspect để có `tenant_id`/quyền.

Ưu điểm: giảm kích thước, quyền thay đổi có thể cập nhật gần thời gian thực. Đổi lại: cần mô hình cache, độ sẵn sàng, phân vùng tenant, giới hạn độ trễ và chính sách **fail closed** cho kiểm tra quyền khi store lỗi.

### 4.4. Per-tenant issuer / federation

Một số tổ chức có IdP và `iss` riêng. Khi đó, token còn cần được ràng buộc với **issuer nào được phép đại diện tenant nào**. Không thể chấp nhận một token từ issuer mới chỉ vì `tenant_id` trong payload mang đúng tên doanh nghiệp.

Ví dụ một bảng cấu hình **được quản trị tin cậy**:

| Issuer được cấu hình | External directory ID | Tenant SaaS nội bộ |
| --- | --- | --- |
| `https://login.acme.example` | `acme-directory` | `tenant-acme` |
| `https://login.globex.example` | `globex-directory` | `tenant-globex` |

Hệ thống có thể lựa chọn dùng external claims rồi map sang `tenant_id` nội bộ tại AS. Phần **mapping IdP ↔ tenant**, quy trình thêm/sửa trust, khóa ký, domain ownership và quyền admin phải được quản lý độc lập; không lấy một domain email làm bằng chứng đủ để được nhận vào tenant.

## 5. Luồng chọn tổ chức và cấp access token theo ngữ cảnh

Giả sử `user-42` là member của Acme và Globex. User chọn **Acme** trong giao diện:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client / BFF
    participant AS as Authorization Server
    participant M as Membership store
    participant API as Invoice API
    U->>C: Đăng nhập và chọn tenant-acme
    C->>AS: Yêu cầu token trong ngữ cảnh tenant-acme
    AS->>AS: Xác thực client/authorization grant theo luồng
    AS->>M: User/client có được hoạt động ở tenant-acme?
    M-->>AS: Membership, trạng thái, role trong tenant
    AS-->>C: Access token đúng audience, tenant và scope
    C->>API: GET /tenants/tenant-acme/invoices/123 + Bearer token
    API->>API: Verify token, scope, tenant match, resource ownership
    API-->>C: 200 hoặc từ chối
~~~

Sơ đồ chỉ trình bày **logic chọn tenant và cấp token**, không quy định một tham số OAuth tiêu chuẩn tên `tenant_id`. Một nhà cung cấp có thể hỗ trợ organization parameter, token exchange, audience/resource parameter hoặc extension khác; **tên tham số, dữ liệu và cách cấp token phải theo tài liệu provider và chính sách hệ thống**.

### 5.1. Tại bước phát hành token cần kiểm tra gì?

Authorization server hoặc thành phần có thẩm quyền phát hành token cần kiểm tra:

1. **Principal/subject đã được xác thực hoặc grant hợp lệ**: user đăng nhập qua OP, hoặc service đã client-authenticate trong grant app-only.
2. **Tenant đã được đăng ký**: tenant ID tồn tại, đang hoạt động, không bị xóa/tạm khóa.
3. **Quan hệ user–tenant hoặc client–tenant**: membership còn hiệu lực, invite đã được chấp thuận nếu cần, hoặc service đã được tenant admin cấp quyền.
4. **Quyền được cấp**: scope/grant, role được giới hạn trong tenant đang chọn; không nâng quyền theo yêu cầu client tự khai.
5. **Audience và token type**: access token chỉ dành đúng API và loại tài nguyên.
6. **Vòng đời**: `iat`, `nbf`, `exp`, cơ chế refresh/revocation và hạn của membership tương ứng.

Một request chứa `tenant_id=tenant-acme` từ UI **chỉ thể hiện ý định chọn tenant**. AS phải xác minh ý định đó với nguồn thẩm quyền thay vì chép nguyên giá trị vào access token và ký.

### 5.2. Tại API cần kiểm tra gì?

API phải tự bảo vệ resource boundary:

~~~mermaid
flowchart TD
    R["Nhận Bearer access token + resource path"] --> V{"Token đúng issuer/audience,\nchữ ký hoặc introspection, còn hạn?"}
    V -->|Không| E401["Từ chối 401"]
    V -->|Có| C{"Scope và principal phù hợp?"}
    C -->|Không| E403["Từ chối quyền"]
    C -->|Có| T{"Tenant trong token\nkhớp tenant đích?"}
    T -->|Không| E403
    T -->|Có| O{"Tài nguyên thuộc tenant?\nMembership/quyền hiện tại hợp lệ?"}
    O -->|Không| E403
    O -->|Có| OK["Thực thi hành động"]
~~~

Trường hợp API che giấu việc tồn tại của tài nguyên, `404 Not Found` có thể được chọn cho một số lỗi quyền theo chính sách thay vì `403`. Điều quan trọng là **không trả dữ liệu sai tenant**; mã lỗi cụ thể phải phù hợp thiết kế API.

## 6. Tenant claim phải được xác minh như thế nào?

### 6.1. Bước 1: xác minh token, không chỉ giải mã payload

Với JWT access token, resource server cần xác minh:

- **Chữ ký và thuật toán cho phép** bằng khóa của issuer tin cậy; không tải JWKS tùy ý từ `jku`/`kid` chưa tin cậy trong token.
- **`iss`** thuộc tập issuer được cấu hình và được phép phục vụ API/tenant tương ứng.
- **`aud`** dành cho chính resource server; từ chối ID token có audience là OIDC client.
- **`exp`**, `nbf` nếu có, yêu cầu thời gian khác; giới hạn clock skew hợp lý.
- **Loại token và profile**: ví dụ JWT access token theo RFC 9068; không chấp nhận token dùng sai mục đích.
- **Scope/permissions và principal type**: token app-only và token đại diện user có thể có chính sách khác nhau.

Với **opaque token**, API dùng introspection/lookup qua kênh tin cậy để xác định trạng thái `active`, issuer, audience, scope, principal và tenant metadata; cần thiết kế cache/revocation để không chấp nhận dữ liệu quyền quá cũ.

**Khi token chưa được xác minh, mọi claim — kể cả `tenant_id` — là input không tin cậy.**

### 6.2. Bước 2: chuẩn hóa tenant identity

Một số issuer dùng `tenant_id`, số khác dùng `org_id`, `tid` hoặc URI tùy biến. API nên **chuẩn hóa** về một kiểu định danh nội bộ:

~~~text
Trusted external issuer + external tenant identity
    -> cấu hình mapping đã được kiểm soát
    -> internalTenantId = tenant-acme
~~~

Tránh so sánh `tenant_name`, email domain hay `display_name` để phân quyền: những trường này có thể thay đổi, trùng nhau hoặc bị người dùng sửa. Định danh tenant nên là **ID ổn định, duy nhất trong phạm vi được xác định**; nếu ID chỉ duy nhất trong issuer, cần kết hợp issuer khi map.

Khi dùng custom claim, hãy quy định **namespace, kiểu, độ dài và phiên bản schema**. Ví dụ một nhà cung cấp có thể dùng tên claim URI để tránh va chạm; ứng dụng khác có thể dùng `tenant_id` nội bộ. Không nên mặc định hai claim trùng tên từ hai issuer mang cùng ý nghĩa.

### 6.3. Bước 3: so quyền với tài nguyên thực tế

**Không chỉ so tenant trong URL với token.** Ví dụ request:

~~~http
GET /tenants/tenant-acme/invoices/inv-123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <verified-access-token>
~~~

API cần truy vấn có điều kiện tenant hoặc kiểm tra bản ghi:

~~~sql
-- Tham số :tenant_id và :invoice_id lấy từ ngữ cảnh đã xác minh
SELECT invoice_id, tenant_id, status, total_amount
FROM invoices
WHERE tenant_id = :tenant_id
  AND invoice_id = :invoice_id;
~~~

Nếu `inv-123` thuộc `tenant-globex`, query phải **không trả dữ liệu**, dù URL client tự điền `tenant-acme`. Việc dùng `WHERE invoice_id = :invoice_id` rồi tin `tenant_id` trong URL là một lỗi dễ dẫn đến **Broken Object Level Authorization (BOLA/IDOR)**.

Nếu cơ sở dữ liệu hỗ trợ **row-level security (RLS)**, có thể dùng thêm như lớp bảo vệ, nhưng phải thiết lập tenant context của kết nối/transaction bằng dữ liệu server đã xác minh, tránh để session database bị tái sử dụng sai tenant trong connection pool.

## 7. Ví dụ Java: kiểm tra tenant trong request

Ví dụ dưới đây minh họa **logic phân quyền sau khi middleware đã xác minh access token**. `VerifiedAccessToken` không được tạo từ JSON payload chưa kiểm tra, cookie hoặc header `X-Tenant-Id` do client tự gửi.

~~~java
import java.time.Instant;
import java.util.Set;

record VerifiedAccessToken(
    String issuer,
    String subject,
    String tenantId,
    Set<String> scopes,
    Set<String> tenantRoles,
    Instant expiresAt
) {}

record Invoice(
    String id,
    String tenantId,
    String ownerUserId
) {}

interface MembershipStore {
    boolean isActiveMember(String subject, String tenantId);
}

enum AuthorizationDecision {
    ALLOW, UNAUTHORIZED, FORBIDDEN, NOT_FOUND
}

final class InvoicePolicy {
    private static final String READ_SCOPE = "invoices.read";

    static AuthorizationDecision canRead(
        VerifiedAccessToken token,
        String tenantFromPath,
        Invoice invoice,
        MembershipStore membershipStore,
        Instant now
    ) {
        // Chỉ nhận token từ middleware đã validate chữ ký/introspection,
        // issuer, audience, token type và thời hạn.
        if (token == null || !token.expiresAt().isAfter(now)) {
            return AuthorizationDecision.UNAUTHORIZED;
        }

        // Fail closed khi tenant context thiếu hoặc sai.
        if (token.tenantId() == null ||
            !token.tenantId().equals(tenantFromPath)) {
            return AuthorizationDecision.FORBIDDEN;
        }

        if (!token.scopes().contains(READ_SCOPE)) {
            return AuthorizationDecision.FORBIDDEN;
        }

        // Không cho đọc record của tenant khác, kể cả đoán được ID.
        if (invoice == null || !invoice.tenantId().equals(token.tenantId())) {
            return AuthorizationDecision.NOT_FOUND;
        }

        // Membership có thể thay đổi sau khi token được phát.
        if (!membershipStore.isActiveMember(
            token.subject(), token.tenantId())) {
            return AuthorizationDecision.FORBIDDEN;
        }

        // Role có nghĩa trong tenant đang xét; quyền đọc
        // toàn tenant khác quyền đọc hóa đơn do mình sở hữu.
        boolean readAll = token.tenantRoles().contains("invoice-reader-all");
        boolean ownInvoice = invoice.ownerUserId().equals(token.subject());
        return (readAll || ownInvoice)
            ? AuthorizationDecision.ALLOW
            : AuthorizationDecision.FORBIDDEN;
    }
}
~~~

Lưu ý:

- Đây là **mô hình policy đơn giản cho user-delegated access token**. Với app-only token (`client_credentials`), `sub` có thể là service principal; cần policy service-specific, không ép nó thành user.
- Quyền `invoice-reader-all` phải do **issuer/nguồn quyền đáng tin** cấp trong phạm vi tenant; string trong ví dụ không phải role chuẩn OAuth.
- Ứng dụng thực cần xác minh token trước khi tạo `VerifiedAccessToken`, xử lý null/data validation, tenant-scoped query, trạng thái invoice, tenant suspension, quyền delegated admin và transaction boundary.
- Đối với dữ liệu rất nhạy cảm, membership/role đã bị thu hồi cần có **cơ chế kiểm tra hiện hành** hoặc access token rất ngắn kết hợp revocation theo policy.

**Sai lầm cần tránh:** lấy tenant do client tự gửi làm quyền mặc định:

~~~java
// SAI: tenantId trong body/header không phải bằng chứng phân quyền.
String tenantId = request.getHeader("X-Tenant-Id");
return invoiceRepository.findById(invoiceId); // Không giới hạn tenant!
~~~

Client vẫn có thể gửi tenant để **chọn ngữ cảnh hoặc route**, nhưng API phải đối chiếu với credential đã xác minh và nguồn membership tin cậy.

## 8. Chuyển tenant an toàn khi một user thuộc nhiều organization

Giả sử `user-42` đang xem Acme rồi chọn Globex:

1. **Giao diện đổi lựa chọn**, ví dụ từ `tenant-acme` sang `tenant-globex`; thao tác này chưa chứng minh user được vào Globex.
2. **Client yêu cầu token/ngữ cảnh mới** theo luồng được AS hỗ trợ; AS kiểm tra user có membership và quyền ở Globex.
3. **Client nhận token phù hợp Globex**, lưu và gửi tới API đúng audience; hạn chế nhầm token do nhiều tab/request song song.
4. **API xác minh Globex trong token**, scope/quyền của Globex và tenant sở hữu dữ liệu.
5. **Giao diện xóa cache đúng phạm vi tenant** để tránh hiển thị nhầm dữ liệu Acme ở tab Globex.

Ví dụ:

~~~text
Trước khi chuyển:
  token-A: sub=user-42, tenant_id=tenant-acme, roles=[admin]

Sau khi chuyển:
  token-B: sub=user-42, tenant_id=tenant-globex, roles=[viewer]

Không hợp lệ:
  dùng token-A để gọi /tenants/tenant-globex/...
  và yêu cầu backend giữ role admin của Acme.
~~~

### 8.1. Hai tab trình duyệt và request đang bay

Một tab có thể giữ Acme, tab khác chọn Globex. Nếu ứng dụng dùng một biến global `currentTenant` nhưng token/cookie/session không gắn với tenant được xác minh, dễ tạo **race condition** hoặc áp sai dữ liệu. Cách xử lý phụ thuộc kiến trúc:

- Với **token một tenant**, mỗi request cần mang đúng token cho tenant của nó; client không lấy lựa chọn giao diện làm chứng cứ.
- Với **BFF/session**, server giữ tenant context gắn với session hoặc request được kiểm chứng, tránh một tab đổi tenant làm tab khác vô tình có quyền khác.
- Với **cache dữ liệu**, key nên gồm tenant ID đã xác minh, principal và thông tin phạm vi; xóa hoặc cách ly cache khi chuyển tenant.

### 8.2. Tenant selection khác tenant authorization

Một endpoint `POST /active-organization` có thể đổi lựa chọn giao diện, nhưng **chỉ được cập nhật session có quyền** sau khi kiểm tra membership. Nếu backend phát JWT mới, AS không được ký nguyên `org_id` từ request mà thiếu tra cứu quyền.

Nếu user vừa bị loại khỏi Globex, một token cũ có thể còn tồn tại đến `exp`. Các thao tác rủi ro cao nên có kiểm tra membership/revocation hiện hành; không xem token đã ký là bằng chứng membership **không thể thay đổi**.

## 9. App-only token và delegated user token

OAuth 2.0 có thể cấp token trong bối cảnh **người dùng** hoặc **ứng dụng/dịch vụ**. Tenant claim cần được diễn giải theo principal type.

| Bối cảnh | Principal và quyền | Kiểm tra tenant cần có |
| --- | --- | --- |
| **User-delegated** qua authorization code | User `sub`, client, scope, role/membership | User có active membership; API đối chiếu quyền user với resource của tenant |
| **Client Credentials** | Service client `client_id`/service principal, scope app-only | Service được admin cấp quyền tới tenant nào; không mặc định có quyền mọi tenant |
| **Token exchange / on-behalf-of** theo profile | Quyền ủy quyền có ngữ cảnh actor và user tùy thiết kế | Không mở rộng tenant/scope so với grant được chấp thuận; ràng buộc delegation |
| **Admin toàn hệ thống** | Principal đặc quyền với policy riêng | Không biến một `roles=["admin"]` của tenant thành platform admin |

Ví dụ ứng dụng backup `backup-service` được Acme cho đọc hóa đơn. Token có thể được cấp `tenant_id=tenant-acme`, `scope=invoices.export` và principal ứng dụng. API **không đòi có user `sub=user-42`**, nhưng vẫn phải xác minh client, grant, tenant và tài nguyên. Token của `backup-service` không được tự dùng để export Globex.

**Không tự suy ra token đại diện user chỉ vì claim `sub` tồn tại.** Trong một số profile/grant, `sub` có thể là client/service principal. API phải dựa vào token type, grant/profile và hợp đồng issuer, không dùng heuristic từ chuỗi `sub`.

## 10. Những lỗ hổng liên quan tenant claim

### 10.1. Sửa tenant trong JWT chưa xác minh

Attacker decode JWT, sửa `tenant_id` từ `tenant-acme` thành `tenant-globex`, rồi encode lại. Nếu API chỉ decode payload, request có thể vượt ranh giới tenant.

**Phòng tránh:** kiểm tra chữ ký, thuật toán, issuer, audience, thời hạn, token type trước khi tin bất kỳ claim nào. JWT ký **không mã hóa** dữ liệu; đọc được không đồng nghĩa sửa được hợp lệ.

### 10.2. Đặt niềm tin vào `X-Tenant-Id` hoặc URL

Client gửi `X-Tenant-Id: tenant-globex` cùng token có `tenant_id=tenant-acme`. API lấy header làm bộ lọc database mà không so với token.

**Phòng tránh:** mọi tenant context do client gửi chỉ là **đích muốn truy cập**; quyền phải lấy từ token đã xác minh và nguồn membership. Query phải tenant-scoped.

### 10.3. Global role bị dùng xuyên tenant

User là `admin` tại Acme, `viewer` tại Globex. Token chứa `roles=["admin"]` nhưng không chỉ rõ role của tenant nào; API Globex tin role này và cho xóa hóa đơn.

**Phòng tránh:** roles/permissions phải gắn tenant scope hoặc nằm trong token dành cho đúng một tenant. Phân biệt platform role với tenant role.

### 10.4. Tin tenant của IdP như tenant dữ liệu SaaS

Một issuer có `tid=directory-x`. API dùng giá trị này làm `tenant_id` nội bộ mà không kiểm tra mapping, dù một directory có nhiều workspace hoặc một SaaS tenant cho phép nhiều IdP.

**Phòng tránh:** khai báo rõ mapping issuer/external org ↔ tenant nghiệp vụ. Tenant nội bộ phải được phân giải từ nguồn tin cậy do hệ thống quản trị.

### 10.5. Đoán được ID tài nguyên xuyên tenant (BOLA)

Token của Acme hợp lệ. User gọi `GET /invoices/inv-globex-123`; API chỉ kiểm tra `scope=invoices.read` rồi truy vấn bằng `invoice_id`.

**Phòng tránh:** kiểm tra ownership/tenant ngay tại truy vấn và policy. Dùng identifier UUID khó đoán **không thay thế** kiểm tra quyền.

### 10.6. Cache và search index bỏ tenant key

Cache key chỉ là `invoice:123`, hoặc search query không có tenant filter. Hai khách hàng có ID tài nguyên trùng hoặc cache chia sẻ kết quả có thể nhận dữ liệu của nhau.

**Phòng tránh:** phân vùng cache/search, dùng key gồm tenant context đã xác minh, test cả cache hit, batch endpoint, export, report và background jobs.

### 10.7. Tenant membership thay đổi nhưng token vẫn còn hiệu lực

User bị xóa khỏi Acme lúc 10:00 nhưng JWT có `exp=11:00`. Nếu API chỉ kiểm tra chữ ký và claims cũ, user có thể vẫn đọc dữ liệu.

**Phòng tránh:** hạn token ngắn, kiểm tra membership hiện hành cho thao tác nhạy cảm, token version/revocation hoặc opaque introspection theo chính sách. Logout hoặc thu hồi refresh token **không mặc nhiên vô hiệu hóa mọi access token JWT offline**.

### 10.8. Đưa mọi membership vào token rồi lộ thông tin

Token chứa danh sách tất cả tổ chức mà user tham gia, bao gồm tên khách hàng nhạy cảm. JWT ký thường đọc được; token lớn còn gây lỗi giới hạn `Authorization` header.

**Phòng tránh:** chỉ phát context/claims tối thiểu, cân nhắc một tenant/token hoặc lookup phía server. Không nhét dữ liệu riêng tư vào JWT với giả định chữ ký giúp mã hóa.

## 11. Vòng đời tenant claim, revocation và vận hành

Tenant context có thể trở nên không còn chính xác khi:

- User bị xóa khỏi organization, bị đình chỉ hoặc giảm từ `admin` xuống `viewer`.
- Organization bị vô hiệu hóa, chuyển chủ sở hữu, sáp nhập hoặc tách thành tenant khác.
- Ứng dụng/service mất quyền `client_credentials` của một khách hàng.
- Policy thay đổi, scope bị thu hẹp hoặc đối tượng bị chuyển sang tenant khác.
- IdP hoặc khóa ký bị thay đổi, mapping external org ↔ internal tenant được cập nhật.

Nên thiết kế hai loại kiểm tra:

1. **Kiểm tra tại phát hành:** AS xác nhận membership, scope, audience và tenant khi phát token, giới hạn claims và thời hạn.
2. **Kiểm tra tại sử dụng:** API xác minh token và quyền truy cập **tại thời điểm request** theo yêu cầu rủi ro, bao gồm tenant của resource và dữ liệu quyền hiện hành khi cần.

Với token tự chứa JWT được xác minh offline, quyền đã nhúng có thể cũ đến `exp` trừ khi triển khai kiểm soát bổ sung. Với opaque token, introspection/lookup thường thuận lợi hơn cho thu hồi gần thời gian thực, nhưng **cache introspection** cũng có thể làm chậm hiệu lực thay đổi quyền. Không nên kết luận một mô hình luôn thu hồi tức thì nếu thực tế có cache.

### 11.1. Refresh token và chuyển tenant

Refresh token có thể đại diện grant rộng hơn hoặc chỉ một tenant, tùy AS. **Không tự suy ra** refresh token gắn với Acme có thể cấp access token Globex; điều này phải được kiểm soát theo grant, consent và membership. Khi đổi tenant, user có thể cần authorization flow mới, chọn organization qua extension provider, hoặc cơ chế trao đổi token chính thức.

Khi cấp access token mới, AS phải kiểm tra trạng thái quyền phù hợp; **việc refresh không tạo quyền tenant mới** chỉ nhờ client gửi `tenant_id` mong muốn.

### 11.2. Ghi log và quan sát lỗi

Trong audit log, có thể ghi **internal tenant ID đã xác minh**, issuer, principal/service ID đã chuẩn hóa, route, action, kết quả policy, correlation ID và thời điểm. Tránh ghi toàn bộ JWT, refresh token, client secret hoặc danh sách tổ chức nhạy cảm không cần thiết.

Phân biệt các lỗi:

| Tình huống | Hướng xử lý HTTP thường gặp |
| --- | --- |
| Token thiếu, sai chữ ký, hết hạn, sai `iss`/`aud` | `401 Unauthorized` theo cơ chế Bearer tương ứng |
| Token hợp lệ nhưng thiếu scope hoặc membership | `403 Forbidden`; `insufficient_scope` khi lỗi scope theo RFC 6750 |
| Tài nguyên thuộc tenant khác hoặc không tồn tại | `404 Not Found` khi muốn tránh lộ resource, hoặc `403` theo policy |
| Tenant bị vô hiệu hóa | Từ chối theo policy ứng dụng; ghi audit để phân tích |
| Không có thông tin tenant đáng tin nhưng endpoint yêu cầu | Fail closed: không tự chọn tenant mặc định với quyền rộng |

## 12. Kiểm thử chống truy cập chéo tenant

Một bộ test phải bao gồm **đường thành công** và nhiều đường thất bại:

| Tình huống | Kỳ vọng |
| --- | --- |
| User Acme có `invoices.read` truy cập invoice Acme được cấp quyền | Thành công |
| User Acme dùng token Acme gọi URL Globex | Bị từ chối |
| URL Acme nhưng `invoice_id` thực tế thuộc Globex | Không trả record Globex |
| Token sai issuer nhưng ghi `tenant_id=tenant-acme` | Bị từ chối trước khi kiểm tra resource |
| Token có chữ ký hợp lệ nhưng sai audience API | Bị từ chối |
| ID token OIDC có `org_id` được gửi thay access token | Bị từ chối |
| User admin Acme, viewer Globex cố sửa invoice Globex | Bị từ chối |
| Header `X-Tenant-Id` khác tenant trong token | Bị từ chối hoặc yêu cầu chọn context đúng |
| Client giả mạo `tenant_id` khi xin token | AS từ chối nếu không có membership/grant |
| User bị xóa khỏi tenant sau khi phát token | Bị từ chối theo yêu cầu thu hồi/membership của policy |
| Cache hit từ request tenant khác | Không lộ dữ liệu |
| User chuyển tenant khi có nhiều tab | Không áp role/token/cache của tenant cũ vào tenant mới |
| Service app-only được cấp Acme thử truy cập Globex | Bị từ chối |
| Tenant ID trùng ở hai issuer khác nhau | Mapping theo issuer đúng, không nhầm tenant |
| Token có danh sách memberships nhưng request chỉ một tenant | Chọn đúng membership, không gộp toàn bộ roles |
| Quyền cần kiểm tra nhưng membership store lỗi | Không tự cho phép truy cập |

Ngoài API đọc một bản ghi, hãy kiểm tra **batch endpoints, exports, search, reports, background tasks, WebSocket/subscriptions, file downloads, audit logs và storage URLs**. Các đường không đi qua controller chính rất dễ thiếu bộ lọc tenant.

## 13. Tình huống phân tích

### Tình huống A: người dùng thuộc hai công ty

`user-42` là `admin` ở Acme và `viewer` ở Globex. Sau khi chuyển giao diện sang Globex, client vẫn dùng access token cũ với `tenant_id=tenant-acme`.

**Phân tích:** UI không thay đổi quyền của token. API Globex phải từ chối; client cần token/ngữ cảnh mới được AS xác thực, và quyền áp dụng chỉ là `viewer` ở Globex.

### Tình huống B: IdP trả `tid` của directory

User đăng nhập qua IdP của đối tác. ID token có `tid=directory-123`; ứng dụng tự sử dụng `directory-123` làm tenant dữ liệu và tạo tài khoản quản trị.

**Phân tích:** lỗi trộn **IdP directory** và **tenant SaaS**. `tid` của nhà cung cấp phải được diễn giải theo tài liệu của issuer và mapping nội bộ; tạo quyền admin cần quy trình provisioning/approval riêng.

### Tình huống C: service backup dùng client credentials

`backup-service` xin access token `client_credentials`, được cấp `scope=invoices.export` và `tenant_id=tenant-acme`. Service sửa URL sang Globex.

**Phân tích:** API phải xác minh đúng tenant context, client/principal, scope và resource. Token app-only không tạo quyền xuyên tenant và không có nghĩa user bất kỳ đã đồng ý.

### Tình huống D: JWT có tên tổ chức nhưng dữ liệu đã chuyển

Một invoice trước đây thuộc Acme, sau đó được chuyển theo quy trình nghiệp vụ sang Globex. Token JWT cũ vẫn mang `tenant_id=tenant-acme`.

**Phân tích:** quyền truy cập phải dựa trên **owner tenant hiện tại** trong dữ liệu đã được quản trị, không dựa vào metadata cũ trong URL hoặc cached object. Việc chuyển tenant là thao tác nhạy cảm cần policy riêng, audit và kiểm soát nhất quán.

### Tình huống E: tối ưu token bằng cách bỏ tenant claim

Nhóm phát triển bỏ `tenant_id` để JWT ngắn hơn nhưng API mặc định mọi request thuộc `tenant-default`, còn endpoint quản trị tự tin vào header `X-Tenant-Id`.

**Phân tích:** đây là lỗi **mất ngữ cảnh phân quyền**. Có thể dùng opaque token hoặc tra membership ngoài token để giảm kích thước, nhưng API phải lấy tenant context từ nguồn đã xác minh, không từ dữ liệu client tự khai.

## 14. Checklist thiết kế tenant/organization claim

1. **Định nghĩa nghiệp vụ:** tenant, organization, workspace, IdP directory và membership có quan hệ thế nào?
2. **Chuẩn hóa claim:** tên, kiểu dữ liệu, namespace, issuer, phiên bản và ngữ nghĩa của `tenant_id`/`org_id`; không mặc định là claim OIDC tiêu chuẩn.
3. **Xác định principal:** user-delegated, client credentials hay delegation; role/scope chỉ đúng trong phạm vi nào?
4. **Cấu hình tin cậy issuer:** xác minh chữ ký/introspection, `iss`, `aud`, loại token và hạn; quản lý per-tenant IdP mapping.
5. **Xác minh khi phát token:** membership hoặc app grant hợp lệ; tenant còn hoạt động; quyền theo tenant không bị nâng từ input của client.
6. **Giới hạn mỗi access token:** audience, scope, lifetime và tenant context phù hợp; tránh nhúng mọi membership nếu không thật sự cần.
7. **Kiểm tra tại API:** token tenant khớp tenant đích; resource owner thực tế, tenant role, membership, tenant status và business policy đều đạt.
8. **Cô lập dữ liệu:** tenant-scoped query/RLS, cache key, search index, batch, export, background jobs và storage.
9. **Quản lý chuyển tenant:** lấy token/context đúng; không mang role, cache hoặc token tenant cũ sang request tenant mới.
10. **Xử lý thu hồi:** user bị xóa khỏi org, đổi role, service mất grant, tenant bị khóa; kiểm tra nguy cơ token JWT còn hạn.
11. **Bảo vệ credential:** HTTPS, không log token, phòng XSS/CSRF theo cách lưu token, giới hạn replay và tránh token quá lớn.
12. **Kiểm thử đường âm:** tenant khác, object ID khác, role chéo tenant, issuer/audience sai, header giả, missing claim, cache leak và concurrency.

## 15. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): các claim chuẩn `iss`, `sub`, `aud`, `exp`, và khả năng dùng private claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT, profile và validation dành cho resource server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection cho opaque access token và metadata có thẩm quyền.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token, lỗi `invalid_token`, `insufficient_scope`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, subject, issuer, audience, xác thực user và UserInfo.
- [OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): lỗi phân quyền theo object ID trong API.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): yêu cầu bảo vệ token và thực hành bảo mật OAuth 2.0.

**Ghi nhớ:** `tenant_id` hoặc `org_id` trong token là **ngữ cảnh tenant/organization do issuer được tin cậy định nghĩa**, không phải chứng chỉ cho mọi quyền trong tổ chức. Resource server phải xác minh token, phân biệt danh tính user và client, đối chiếu **tenant trong token – tenant của request – tenant sở hữu tài nguyên**, rồi kiểm tra scope, role/membership và chính sách nghiệp vụ. Chính chuỗi kiểm tra này mới tạo ra ranh giới bảo mật cho ứng dụng đa tenant.
